"""Replay the favorite-dip rule on past games, for any sport in bot/sports.py.

Data:
  * ESPN scoreboard -> games and winners
  * ESPN summary play-by-play -> real start time, when each period began, final play
  * Kalshi events -> which game-winner markets belong to which game
  * Kalshi 1-minute candlesticks -> the favorite's bid/ask through the game

  python -m bot.backtest fetch nfl 2026-09-09 2026-11-15   # -> data/backtest/nfl_cache.json
  python -m bot.backtest report nfl                        # -> data/backtest/nfl_report.md
  python -m bot.backtest summary                           # one table across all sports

Limits: one-minute candle closes, not tick-by-tick quotes, so entries are approximate.
Paper fills assume paying the ask plus the taker fee, same as the live bot.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from . import config, kalshi, strategy
from .sports import ESPN_BASE, SPORTS

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "backtest"
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
EVENT_DATE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})")


def cache_path(sport: str) -> Path:
    return OUT / f"{sport}_cache.json"


# ---------------------------------------------------------------- fetching

def iso_ts(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def get(s: requests.Session, url: str, params: dict) -> dict:
    r = None
    for attempt in range(8):
        r = s.get(url, params=params, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        time.sleep(0.25)
        return r.json()
    r.raise_for_status()
    return {}


def norm(x: str) -> str:
    x = (x or "").lower().replace("st.", "state").replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", x)


def event_date(ticker: str) -> str | None:
    m = EVENT_DATE.search(ticker)
    if not m or m.group(2) not in MONTHS:
        return None
    return f"20{m.group(1)}-{MONTHS.index(m.group(2)) + 1:02d}-{m.group(3)}"


def kalshi_events(s: requests.Session, series: str, start: date, end: date) -> dict[str, list[dict]]:
    """All game events of a series, grouped by date: {date: [{event, markets:[...]}]}."""
    out: dict[str, list[dict]] = {}
    cursor = None
    for _ in range(200):
        params = {"series_ticker": series, "limit": 200, "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        js = get(s, f"{config.KALSHI_API}/events", params)
        for ev in js.get("events", []):
            d = event_date(ev.get("event_ticker", ""))
            if not d or not (str(start) <= d <= str(end)):
                continue
            mk = [m for m in ev.get("markets") or [] if not m["ticker"].endswith("-TIE")]
            out.setdefault(d, []).append({"event": ev["event_ticker"], "markets": [
                {"ticker": m["ticker"], "code": m["ticker"].rsplit("-", 1)[-1],
                 "name": m.get("yes_sub_title") or ""} for m in mk]})
        cursor = js.get("cursor")
        if not cursor:
            break
    return out


def espn_games(s: requests.Session, sport: dict, d: date) -> list[dict]:
    js = get(s, f"{ESPN_BASE}/{sport['espn']}/scoreboard", {"dates": d.strftime("%Y%m%d"), **sport["params"]})
    games = []
    for e in js.get("events", []):
        try:
            comp = e["competitions"][0]
            st = comp["status"]["type"]
            if not st.get("completed") or (e.get("season") or {}).get("type") not in (2, 3):
                continue
            teams, winner = {}, None
            for c in comp["competitors"]:
                t = c["team"]
                code = t.get("abbreviation", "")
                teams[code] = {"home": c.get("homeAway") == "home",
                               "names": {norm(t.get(k, "")) for k in
                                         ("location", "displayName", "shortDisplayName", "name", "nickname")} - {""}}
                if c.get("winner") is True:
                    winner = code
            if len(teams) == 2 and winner:
                games.append({"id": e["id"], "start": e.get("date", ""), "teams": teams, "winner": winner})
        except (KeyError, IndexError, TypeError):
            continue
    return games


ALIASES = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"}


def match(game: dict, events: list[dict]) -> dict[str, str] | None:
    """Map each ESPN team code -> Kalshi market ticker, or None if no event fits."""
    for ev in events:
        if len(ev["markets"]) != 2:
            continue
        assign = {}
        for code, t in game["teams"].items():
            hit = [m for m in ev["markets"]
                   if m["code"] in (code, ALIASES.get(code, code))
                   or norm(m["name"]) in t["names"]]
            if len(hit) != 1:   # fall back to prefix: Kalshi "Los Angeles R" vs ESPN "Los Angeles Rams"
                hit = [m for m in ev["markets"]
                       if any(n.startswith(norm(m["name"])) or norm(m["name"]).startswith(n)
                              for n in t["names"] if len(n) >= 4)]
            if len(hit) == 1:
                assign[code] = hit[0]["ticker"]
        if len(assign) == 2 and len(set(assign.values())) == 2:
            return assign
    return None


def timing(s: requests.Session, sport: dict, espn_id: str) -> dict | None:
    js = get(s, f"{ESPN_BASE}/{sport['espn']}/summary", {"event": espn_id})
    plays = js.get("plays") or []
    if not plays and js.get("drives"):   # football keeps plays inside drives
        plays = [p for dr in js["drives"].get("previous", []) for p in dr.get("plays", [])]
    starts, last = {}, None
    for p in plays:
        wc = p.get("wallclock")
        per = (p.get("period") or {}).get("number")
        if not wc or not per:
            continue
        t = iso_ts(wc)
        starts.setdefault(str(per), t)
        last = max(last or t, t)
    if "1" in starts and len(starts) >= 2 and last:
        return {"tip": starts["1"], "periods": starts, "end": last}
    return None


def candles(s: requests.Session, series: str, ticker: str, start: int, end: int) -> list[list]:
    out = []
    t0 = start
    while t0 < end:                       # chunk long games (football runs 3.5h+)
        t1 = min(end, t0 + 4 * 3600)
        js = get(s, f"{config.KALSHI_API}/series/{series}/markets/{ticker}/candlesticks",
                 {"start_ts": t0, "end_ts": t1, "period_interval": 1})
        for c in js.get("candlesticks", []):
            out.append([c.get("end_period_ts"),
                        kalshi._candle_close(c.get("yes_bid")),
                        kalshi._candle_close(c.get("yes_ask"))])
        t0 = t1
    return out


def pregame_mid(s: requests.Session, series: str, ticker: str, ts: int) -> float | None:
    js = get(s, f"{config.KALSHI_API}/series/{series}/markets/{ticker}/candlesticks",
             {"start_ts": ts - 3 * 3600, "end_ts": ts, "period_interval": 1})
    for c in reversed(js.get("candlesticks", [])):
        if (c.get("end_period_ts") or 0) > ts:
            continue
        bid, ask = kalshi._candle_close(c.get("yes_bid")), kalshi._candle_close(c.get("yes_ask"))
        if bid is not None and ask is not None and 0 < ask <= 1 and ask >= bid:
            return round((bid + ask) / 2, 4)
    return None


def fetch(sport_key: str, start: date, end: date) -> None:
    sport = SPORTS[sport_key]
    path = cache_path(sport_key)
    cache = json.loads(path.read_text()) if path.exists() else {"games": {}}
    s = requests.Session()
    s.headers["User-Agent"] = "kalshi-sports-dip/1.0 backtest"
    events = kalshi_events(s, sport["series"], start - timedelta(days=1), end + timedelta(days=1))
    print(f"{sport['name']}: {sum(len(v) for v in events.values())} Kalshi events in range")
    d = start
    while d <= end:
        try:
            games = espn_games(s, sport, d)
        except Exception as e:
            print(f"{d} scoreboard error: {e}")
            d += timedelta(days=1)
            continue
        n = 0
        for g in games:
            done = cache["games"].get(g["id"])
            if done and not done.get("skip", "").startswith("error"):
                continue
            rec = {"date": str(d), "teams": list(g["teams"]), "winner": g["winner"], "start": g["start"]}
            try:
                # Kalshi dates its events in US time; late games can carry the next/previous day
                cands = events.get(str(d), []) + events.get(str(d + timedelta(days=1)), []) \
                    + events.get(str(d - timedelta(days=1)), [])
                tickers = match(g, cands)
                if not tickers:
                    rec["skip"] = "no Kalshi market"
                else:
                    tm = timing(s, sport, g["id"])
                    if not tm:
                        rec["skip"] = "no play timing"
                    else:
                        rec.update(tm)
                        pre = {c: pregame_mid(s, sport["series"], t, tm["tip"]) for c, t in tickers.items()}
                        if any(v is None for v in pre.values()):
                            rec["skip"] = "no pre-game price"
                        else:
                            fav = max(pre, key=pre.get)
                            rec["fav"], rec["fav_pre"] = fav, pre[fav]
                            if pre[fav] >= 0.60:
                                rec["candles"] = candles(s, sport["series"], tickers[fav], tm["tip"] - 60, tm["end"])
            except Exception as e:
                rec["skip"] = f"error: {e}"[:120]
            cache["games"][g["id"]] = rec
            n += 1
        if n:
            print(f"{d}: {n} games")
            OUT.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cache, separators=(",", ":")))
        d += timedelta(days=1)
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, separators=(",", ":")))


# ---------------------------------------------------------------- simulation

def period_at(g: dict, ts: int) -> int:
    p = 1
    for k, t in g["periods"].items():
        if ts >= t:
            p = max(p, int(k))
    return p


def simulate(g: dict, dip: float, early_periods: int = 2, contracts: int = config.CONTRACTS,
             min_entry: float = config.MIN_ENTRY_PRICE, max_spread: float = config.MAX_SPREAD) -> dict | None:
    """First minute after the start where the favorite's ask is `dip` below its pre-game price."""
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
            per = period_at(g, ts)
            return {"date": g["date"], "fav": g["fav"],
                    "opp": next(t for t in g["teams"] if t != g["fav"]),
                    "fav_pre": g["fav_pre"], "entry": ask, "fee": fee, "cost": cost,
                    "period": per, "bucket": "early" if per <= early_periods else "late",
                    "minute": round((ts - g["tip"]) / 60), "won": won,
                    "pnl": round((contracts if won else 0) - cost, 2)}
    return None


def stats(rows: list[dict]) -> dict:
    n = len(rows)
    staked = sum(r["cost"] for r in rows)
    pnl = sum(r["pnl"] for r in rows)
    wins = sum(r["won"] for r in rows)
    avg = sum(r["entry"] for r in rows) / n if n else 0
    return {"n": n, "wins": wins, "pnl": round(pnl, 2), "staked": round(staked, 2),
            "win_rate": wins / n if n else 0, "avg_entry": avg,
            "edge": (wins / n - avg) if n else 0, "roi": pnl / staked if staked else 0}


def money(x: float) -> str:
    return f"{'+' if x > 0 else '−' if x < 0 else ''}${abs(x):,.2f}"


def row(name: str, st: dict) -> str:
    if not st["n"]:
        return f"| {name} | 0 | – | – | – | – | – |"
    return (f"| {name} | {st['n']} | {st['win_rate']*100:.0f}% | {st['avg_entry']*100:.0f}¢ | "
            f"{st['edge']*100:+.0f} pts | {money(st['pnl'])} | {st['roi']*100:+.1f}% |")


HEAD = ["| | Trades | Won | Avg buy | Edge | P&L | ROI |", "|---|---|---|---|---|---|---|"]


def load(sport_key: str) -> tuple[list[dict], list[dict]]:
    games = list(json.loads(cache_path(sport_key).read_text())["games"].values())
    return games, [g for g in games if "fav_pre" in g and "tip" in g]


def report(sport_key: str) -> str:
    sport = SPORTS[sport_key]
    ep = sport["early_periods"]
    games, usable = load(sport_key)
    dates = sorted(g["date"] for g in games) or ["–"]
    skips: dict[str, int] = {}
    for g in games:
        if g.get("skip"):
            k = g["skip"].split(":")[0]
            skips[k] = skips.get(k, 0) + 1

    th, dip = config.FAVORITE_MIN_PREGAME, config.DIP_SIZE
    fav = [g for g in usable if g["fav_pre"] >= th]
    trades = [t for t in (simulate(g, dip, ep) for g in fav) if t]
    out = [f"# {sport['name']} — favorite-dip backtest, {dates[0]} to {dates[-1]}", "",
           f"{len(games)} finished games, {len(usable)} with Kalshi prices + play timing"
           + (f" (skipped: {', '.join(f'{v} {k}' for k, v in skips.items())})" if skips else "") + ".",
           f"{config.CONTRACTS} contracts per trade, buying at the ask + taker fee, held to the end. "
           f"\"Early\" = period 1–{ep}.", "",
           f"## Live rule: favorite ≥{th*100:.0f}¢, buy a {dip*100:.0f}¢+ dip ({len(fav)} games had such a favorite)", "",
           *HEAD,
           row("Early dips (strategy)", stats([t for t in trades if t["bucket"] == "early"])),
           row("Late dips (control)", stats([t for t in trades if t["bucket"] == "late"]))]
    for p in sorted({t["period"] for t in trades}):
        out.append(row(f"…bought in period {p}", stats([t for t in trades if t["period"] == p])))

    base = []
    for g in fav:
        a = next((a for ts, b, a in g.get("candles", []) if ts and ts >= g["tip"] and a), None)
        if a:
            fee = strategy.taker_fee(config.CONTRACTS, a)
            won = g["winner"] == g["fav"]
            base.append({"entry": a, "cost": a * config.CONTRACTS + fee, "won": won,
                         "pnl": (config.CONTRACTS if won else 0) - a * config.CONTRACTS - fee})
    out += [row("Baseline: buy every favorite at the start", stats(base)), "",
            "**Edge** = how often the team won minus the price paid. Positive means the market underpriced it.", "",
            "## Variations — early dips: P&L [trades]", "",
            "| Favorite ≥ \\ dip | 10¢ | 15¢ | 20¢ | 25¢ |", "|---|---|---|---|---|"]
    for t2 in (0.60, 0.65, 0.70, 0.75, 0.80):
        cells = []
        for d2 in (0.10, 0.15, 0.20, 0.25):
            ts = [t for t in (simulate(g, d2, ep) for g in usable if g["fav_pre"] >= t2) if t]
            e = stats([t for t in ts if t["bucket"] == "early"])
            cells.append(f"{money(e['pnl'])} [{e['n']}]")
        out.append(f"| {t2*100:.0f}¢ | " + " | ".join(cells) + " |")

    out += ["", "## Every trade (live rule)", "",
            "| Date | Team | vs | Pre-game | Bought | Period | Result | P&L |", "|---|---|---|---|---|---|---|---|"]
    for t in sorted(trades, key=lambda t: t["date"]):
        out.append(f"| {t['date']} | {t['fav']} | {t['opp']} | {t['fav_pre']*100:.0f}¢ | {t['entry']*100:.0f}¢ | "
                   f"{t['period']} | {'✅' if t['won'] else '❌'} | {money(t['pnl'])} |")
    text = "\n".join(out) + "\n"
    (OUT / f"{sport_key}_report.md").write_text(text)
    return text


def summary() -> str:
    th, dip = config.FAVORITE_MIN_PREGAME, config.DIP_SIZE
    out = [f"# All sports — favorite ≥{th*100:.0f}¢, {dip*100:.0f}¢+ dip, {config.CONTRACTS} contracts", "",
           "| Sport | Bucket | Trades | Won | Avg buy | Edge | P&L | ROI |", "|---|---|---|---|---|---|---|---|"]
    for key, sport in SPORTS.items():
        if not cache_path(key).exists():
            continue
        _, usable = load(key)
        ts = [t for t in (simulate(g, dip, sport["early_periods"]) for g in usable if g["fav_pre"] >= th) if t]
        for b in ("early", "late"):
            st = stats([t for t in ts if t["bucket"] == b])
            out.append(f"| {sport['name']} ({len(usable)} games) | {b} " + row("", st)[3:])
    text = "\n".join(out) + "\n"
    (OUT / "summary.md").write_text(text)
    return text


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "fetch":
        fetch(sys.argv[2], date.fromisoformat(sys.argv[3]), date.fromisoformat(sys.argv[4]))
    elif cmd == "report":
        print(report(sys.argv[2]))
    else:
        print(summary())
