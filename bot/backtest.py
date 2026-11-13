"""Replay the favorite-dip rule on past NBA games.

Data:
  * ESPN scoreboard -> games, scheduled start, winner
  * ESPN summary play-by-play -> real tip-off time, start of Q3, final play
  * Kalshi 1-minute candlesticks -> favorite's bid/ask through the game

  python -m bot.backtest fetch 2026-10-20 2026-11-12   # download into data/backtest_cache.json
  python -m bot.backtest report                         # simulate + write data/backtest_report.md

Limits: one-minute candle closes, not tick-by-tick quotes, so entries are approximate.
Paper fills assume paying the ask plus the taker fee, same as the live bot.
"""
from __future__ import annotations

import csv
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from . import config, espn, kalshi, strategy

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "backtest_cache.json"
REPORT = ROOT / "data" / "backtest_report.md"
TRADES = ROOT / "data" / "backtest_trades.csv"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"


# ---------------------------------------------------------------- fetching

def iso_ts(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def get(s: requests.Session, url: str, params: dict) -> dict:
    for attempt in range(8):
        r = s.get(url, params=params, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        time.sleep(0.3)
        return r.json()
    r.raise_for_status()
    return {}


def season_type(s: requests.Session, d: date) -> dict[str, int]:
    js = get(s, config.ESPN_SCOREBOARD, {"dates": d.strftime("%Y%m%d")})
    return {e["id"]: (e.get("season") or {}).get("type", 0) for e in js.get("events", [])}


def timing(s: requests.Session, espn_id: str) -> dict | None:
    js = get(s, SUMMARY_URL, {"event": espn_id})
    tip = q3 = last = None
    for p in js.get("plays") or []:
        wc = p.get("wallclock")
        per = (p.get("period") or {}).get("number")
        if not wc or not per:
            continue
        t = iso_ts(wc)
        tip = tip or t
        if per >= 3 and q3 is None:
            q3 = t
        last = t
    if tip and q3 and last:
        return {"tip": tip, "q3": q3, "end": last}
    return None


def markets_for(s: requests.Session, d: date, teams: dict) -> list[dict]:
    ymd = f"{d:%y}{d:%b}".upper() + f"{d:%d}"
    away = next((c for c, t in teams.items() if not t["home"]), None)
    home = next((c for c, t in teams.items() if t["home"]), None)
    for a, b in ((away, home), (home, away)):
        js = get(s, f"{config.KALSHI_API}/markets",
                 {"event_ticker": f"{config.KALSHI_SERIES}-{ymd}{a}{b}"})
        if js.get("markets"):
            return js["markets"]
    return []


def candles(s: requests.Session, ticker: str, start: int, end: int) -> list[list]:
    js = get(s, f"{config.KALSHI_API}/series/{config.KALSHI_SERIES}/markets/{ticker}/candlesticks",
             {"start_ts": start, "end_ts": end, "period_interval": 1})
    out = []
    for c in js.get("candlesticks", []):
        out.append([c.get("end_period_ts"),
                    kalshi._candle_close(c.get("yes_bid")),
                    kalshi._candle_close(c.get("yes_ask"))])
    return out


def fetch(start: date, end: date) -> None:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {"games": {}}
    s = requests.Session()
    s.headers["User-Agent"] = "kalshi-sports-dip/1.0 backtest"
    d = start
    while d <= end:
        try:
            games = espn.fetch_games(d, s)
            stypes = season_type(s, d)
        except Exception as e:
            print(f"{d} scoreboard error: {e}")
            d += timedelta(days=1)
            continue
        n = 0
        for g in games:
            done = cache["games"].get(g["id"])
            if (done and not done.get("skip", "").startswith("error")) or not g["completed"] or stypes.get(g["id"]) not in (2, 3):
                continue
            rec = {"date": str(d), "teams": list(g["teams"]), "winner": g["winner"], "start": g["start"]}
            try:
                tm = timing(s, g["id"])
                mk = markets_for(s, d, g["teams"])
                if not tm or not mk:
                    rec["skip"] = "no play timing" if not tm else "no Kalshi market"
                else:
                    rec.update(tm)
                    pre = {}
                    for m in mk:
                        code = espn.team_code_in_game(kalshi.normalize_market(m), g)
                        if code:
                            pre[code] = (m["ticker"], kalshi.pregame_mid(m["ticker"], tm["tip"], s))
                    pre = {c: v for c, v in pre.items() if v[1] is not None}
                    if len(pre) < 2:
                        rec["skip"] = "no pre-game price"
                    else:
                        fav = max(pre, key=lambda c: pre[c][1])
                        rec["fav"], rec["fav_pre"] = fav, pre[fav][1]
                        if pre[fav][1] >= 0.60:   # keep candles only where a variant could trade
                            rec["candles"] = candles(s, pre[fav][0], tm["tip"] - 60, tm["end"])
            except Exception as e:
                rec["skip"] = f"error: {e}"[:120]
            cache["games"][g["id"]] = rec
            n += 1
        print(f"{d}: {n} games")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, separators=(",", ":")))
        d += timedelta(days=1)


# ---------------------------------------------------------------- simulation

def simulate(g: dict, dip: float, contracts: int = config.CONTRACTS,
             min_entry: float = config.MIN_ENTRY_PRICE, max_spread: float = config.MAX_SPREAD) -> dict | None:
    """First minute after tip where the favorite's ask is `dip` below its pre-game price."""
    target = g["fav_pre"] - dip
    for ts, bid, ask in g.get("candles", []):
        if ts is None or ts <= g["tip"] or ts > g["end"] or bid is None or ask is None:
            continue
        if ask < min_entry or ask - bid > max_spread:
            continue
        if ask <= target:
            fee = strategy.taker_fee(contracts, ask)
            cost = round(ask * contracts + fee, 2)
            won = g["winner"] == g["fav"]
            return {"date": g["date"], "fav": g["fav"],
                    "opp": next(t for t in g["teams"] if t != g["fav"]),
                    "fav_pre": g["fav_pre"], "entry": ask, "fee": fee, "cost": cost,
                    "bucket": "early" if ts < g["q3"] else "late",
                    "minute": round((ts - g["tip"]) / 60), "won": won,
                    "pnl": round((contracts if won else 0) - cost, 2)}
    return None


def stats(rows: list[dict]) -> dict:
    n = len(rows)
    staked = sum(r["cost"] for r in rows)
    pnl = sum(r["pnl"] for r in rows)
    wins = sum(r["won"] for r in rows)
    return {"n": n, "wins": wins, "pnl": round(pnl, 2), "staked": round(staked, 2),
            "win_rate": wins / n if n else 0, "avg_entry": sum(r["entry"] for r in rows) / n if n else 0,
            "roi": pnl / staked if staked else 0}


def money(x: float) -> str:
    return f"{'+' if x > 0 else '−' if x < 0 else ''}${abs(x):,.2f}"


def line(name: str, st: dict) -> str:
    if not st["n"]:
        return f"| {name} | 0 | – | – | – | – |"
    return (f"| {name} | {st['n']} | {st['win_rate']*100:.0f}% | {st['avg_entry']*100:.0f}¢ | "
            f"{money(st['pnl'])} | {st['roi']*100:+.1f}% |")


def report() -> str:
    cache = json.loads(CACHE.read_text())
    games = list(cache["games"].values())
    usable = [g for g in games if "fav_pre" in g and "tip" in g]
    dates = sorted(g["date"] for g in games)
    skips = {}
    for g in games:
        if g.get("skip"):
            k = g["skip"].split(":")[0]
            skips[k] = skips.get(k, 0) + 1

    out = [f"# Favorite-dip backtest — {dates[0]} to {dates[-1]}", "",
           f"{len(games)} games found, {len(usable)} with full price + timing data"
           + (f" (skipped: {', '.join(f'{v} {k}' for k, v in skips.items())})" if skips else "") + ".",
           f"{config.CONTRACTS} contracts per trade, buying at the ask + Kalshi taker fee, held to the final buzzer.", ""]

    # main rule
    fav = [g for g in usable if g["fav_pre"] >= config.FAVORITE_MIN_PREGAME]
    trades = [t for t in (simulate(g, config.DIP_SIZE) for g in fav) if t]
    out += [f"## Main rule: favorite ≥{config.FAVORITE_MIN_PREGAME*100:.0f}¢, buy a {config.DIP_SIZE*100:.0f}¢+ dip",
            f"{len(fav)} games had a favorite at that level.", "",
            "| Bucket | Trades | Won | Avg buy | P&L | ROI |", "|---|---|---|---|---|---|",
            line("Early (Q1–Q2) — strategy", stats([t for t in trades if t["bucket"] == "early"])),
            line("Late (Q3–Q4) — control", stats([t for t in trades if t["bucket"] == "late"])),
            line("All", stats(trades)), "",
            "A buy has an edge when **Won %** is higher than **Avg buy** (the price is the market's implied chance).", ""]

    # baseline: just buy the favorite at tip
    base = []
    for g in fav:
        first = next(((b, a) for ts, b, a in g.get("candles", []) if ts and ts >= g["tip"] and a), None)
        if first:
            a = first[1]
            fee = strategy.taker_fee(config.CONTRACTS, a)
            cost = a * config.CONTRACTS + fee
            won = g["winner"] == g["fav"]
            base.append({"entry": a, "cost": cost, "won": won, "pnl": (config.CONTRACTS if won else 0) - cost})
    out += ["## Baseline: just buy the favorite at tip-off", "",
            "| Rule | Trades | Won | Avg buy | P&L | ROI |", "|---|---|---|---|---|---|",
            line("Buy favorite at tip", stats(base)), ""]

    # sensitivity grid
    out += ["## Variations (early-dip P&L / late-dip P&L, trades in brackets)", "",
            "| Favorite ≥ \\ dip | 15¢ | 20¢ | 25¢ | 30¢ |", "|---|---|---|---|---|"]
    for th in (0.65, 0.70, 0.75, 0.80):
        cells = []
        for dip in (0.15, 0.20, 0.25, 0.30):
            ts = [t for t in (simulate(g, dip) for g in usable if g["fav_pre"] >= th) if t]
            e = stats([t for t in ts if t["bucket"] == "early"])
            l = stats([t for t in ts if t["bucket"] == "late"])
            cells.append(f"{money(e['pnl'])} [{e['n']}] / {money(l['pnl'])} [{l['n']}]")
        out.append(f"| {th*100:.0f}¢ | " + " | ".join(cells) + " |")
    out.append("")

    # trade list for the main rule
    out += ["## Every trade (main rule)", "", "| Date | Team | vs | Pre-game | Bought | Min after tip | Bucket | Result | P&L |",
            "|---|---|---|---|---|---|---|---|---|"]
    for t in sorted(trades, key=lambda t: t["date"]):
        out.append(f"| {t['date']} | {t['fav']} | {t['opp']} | {t['fav_pre']*100:.0f}¢ | {t['entry']*100:.0f}¢ | "
                   f"{t['minute']} | {t['bucket']} | {'✅ won' if t['won'] else '❌ lost'} | {money(t['pnl'])} |")

    text = "\n".join(out) + "\n"
    REPORT.write_text(text)
    with TRADES.open("w", newline="") as f:
        if trades:
            w = csv.DictWriter(f, fieldnames=list(trades[0]))
            w.writeheader()
            w.writerows(trades)
    return text


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "fetch":
        fetch(date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3]))
    else:
        print(report())
