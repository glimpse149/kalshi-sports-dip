"""The 'favorite dip' rules. Pure functions, no network, so they can be tested offline.

Idea: a team priced 75c+ before tip falls behind early and its price drops 25c+.
Research (Betfair, 260k games) suggests early-game swings get over-weighted, so the
favorite may be underpriced after an early dip. Late-game dips are logged separately
as a control group, since evidence says late-game moves tend to keep going.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from . import config
from .espn import match_game, team_code_in_game


def taker_fee(contracts: int, price: float) -> float:
    raw = config.TAKER_FEE_RATE * contracts * price * (1 - price)
    return math.ceil(round(raw * 100, 6)) / 100.0


def new_state() -> dict:
    return {"games": {}, "open": [], "closed": []}


def _game_rec(state: dict, event: str) -> dict:
    return state["games"].setdefault(event, {
        "pregame": {},        # team -> last mid seen before tip
        "favorite": None,     # locked at tip
        "fav_pregame": None,
        "entered": [],        # buckets already traded: "early" / "late"
        "espn_id": None,
        "date": None,
    })


def step(state: dict, markets: list[dict], games: list[dict], now: datetime | None = None,
         pregame_lookup=None) -> list[dict]:
    """Update state with one snapshot. Returns new paper entries (for alerts).

    pregame_lookup(market, game) -> mid price at tip, used when the bot first sees a
    game after it already started (so the favorite can still be identified).
    """
    now = now or datetime.now(timezone.utc)
    by_event: dict[str, list[dict]] = {}
    for m in markets:
        by_event.setdefault(m["event"], []).append(m)

    entries = []
    for event, mkts in by_event.items():
        game = None
        for m in mkts:
            game = match_game(m, games)
            if game:
                break
        if not game:
            continue
        rec = _game_rec(state, event)
        rec["espn_id"] = game["id"]
        rec["date"] = str(mkts[0]["date"]) if mkts[0]["date"] else rec["date"]

        # 1) before tip: keep the latest pre-game price for each team
        if game["state"] == "pre":
            for m in mkts:
                code = team_code_in_game(m, game)
                if code and m["mid"] is not None:
                    rec["pregame"][code] = round(m["mid"], 4)
            continue

        if game["state"] != "in":
            continue

        # 2) missed tip? look up the pre-game price from Kalshi's price history
        if (rec["favorite"] is None and not rec["pregame"] and pregame_lookup
                and rec.get("lookup_tries", 0) < 5):
            rec["lookup_tries"] = rec.get("lookup_tries", 0) + 1
            for m in mkts:
                code = team_code_in_game(m, game)
                if not code:
                    continue
                try:
                    p = pregame_lookup(m, game)
                except Exception as e:
                    print(f"[pregame lookup {m['ticker']}] {e}")
                    p = None
                if p is not None:
                    rec["pregame"][code] = p
            rec["pregame_source"] = "history"
            if len(rec["pregame"]) < 2:      # couldn't get both sides: try again next loop
                rec["pregame"] = {}

        # 3) at tip: lock the favorite (only if we have a pre-game price)
        if rec["favorite"] is None and rec["pregame"]:
            fav, p = max(rec["pregame"].items(), key=lambda kv: kv[1])
            rec["favorite"] = fav if p >= config.FAVORITE_MIN_PREGAME else ""
            rec["fav_pregame"] = p
        fav = rec["favorite"]
        if not fav:
            continue

        mkt = next((m for m in mkts if team_code_in_game(m, game) == fav), None)
        if not mkt or mkt["ask"] is None or mkt["bid"] is None:
            continue

        bucket = "early" if game["period"] <= config.EARLY_MAX_PERIOD else "late"
        if rec["entered"]:          # one paper trade per game: early, or late as control
            continue

        ask, bid = mkt["ask"], mkt["bid"]
        if ask < config.MIN_ENTRY_PRICE or ask - bid > config.MAX_SPREAD:
            continue
        if ask > rec["fav_pregame"] - config.DIP_SIZE:
            continue

        opp = next((c for c in game["teams"] if c != fav), "")
        fee = taker_fee(config.CONTRACTS, ask)
        pos = {
            "event": event,
            "ticker": mkt["ticker"],
            "date": rec["date"],
            "espn_id": game["id"],
            "team": fav,
            "opponent": opp,
            "bucket": bucket,
            "pregame": rec["fav_pregame"],
            "entry": ask,
            "contracts": config.CONTRACTS,
            "fee": fee,
            "cost": round(ask * config.CONTRACTS + fee, 2),
            "period": game["period"],
            "clock": game["clock"],
            "score": f'{fav} {game["teams"][fav]["score"]}-{game["teams"].get(opp, {}).get("score", 0)} {opp}',
            "opened_at": now.isoformat(timespec="seconds"),
        }
        rec["entered"].append(bucket)
        state["open"].append(pos)
        entries.append(pos)
    return entries


def settle(state: dict, finals: dict[str, str], now: datetime | None = None) -> list[dict]:
    """finals: espn_id -> winning team code. Moves finished positions to closed."""
    now = now or datetime.now(timezone.utc)
    done, still = [], []
    for p in state["open"]:
        w = finals.get(p["espn_id"])
        if not w:
            still.append(p)
            continue
        won = w == p["team"]
        payout = float(p["contracts"]) if won else 0.0
        p.update({
            "won": won,
            "payout": payout,
            "pnl": round(payout - p["cost"], 2),
            "closed_at": now.isoformat(timespec="seconds"),
        })
        done.append(p)
    state["open"] = still
    state["closed"].extend(done)
    return done


def totals(closed: list[dict], bucket: str) -> dict:
    rows = [p for p in closed if p["bucket"] == bucket]
    n = len(rows)
    wins = sum(1 for p in rows if p["won"])
    pnl = round(sum(p["pnl"] for p in rows), 2)
    staked = round(sum(p["cost"] for p in rows), 2)
    return {"n": n, "wins": wins, "pnl": pnl, "staked": staked,
            "roi": (pnl / staked) if staked else 0.0,
            "avg_entry": (sum(p["entry"] for p in rows) / n) if n else 0.0}


def prune(state: dict, keep_days: int = 3, today: str | None = None) -> None:
    """Drop old per-game scratch records (positions are kept)."""
    if not today:
        return
    from datetime import date, timedelta
    cutoff = (date.fromisoformat(today) - timedelta(days=keep_days)).isoformat()
    state["games"] = {k: v for k, v in state["games"].items() if (v.get("date") or today) >= cutoff}
