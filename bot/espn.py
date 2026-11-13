"""Live NBA scores from ESPN's public scoreboard feed."""
from __future__ import annotations

from datetime import date

import requests

from . import config

# ESPN abbreviation -> Kalshi abbreviation where they differ
ESPN_TO_KALSHI = {
    "GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP",
    "UTAH": "UTA", "WSH": "WAS", "BKN": "BKN", "PHX": "PHX",
}


def k_abbr(espn_abbr: str) -> str:
    a = (espn_abbr or "").upper()
    return ESPN_TO_KALSHI.get(a, a)


def normalize_event(ev: dict) -> dict | None:
    try:
        comp = ev["competitions"][0]
        status = comp.get("status") or ev.get("status") or {}
        stype = status.get("type", {})
        teams = {}
        winner = None
        for c in comp["competitors"]:
            t = c["team"]
            code = k_abbr(t.get("abbreviation", ""))
            teams[code] = {
                "home": c.get("homeAway") == "home",
                "score": int(c.get("score") or 0),
                "location": t.get("location", ""),
                "name": t.get("shortDisplayName") or t.get("name", ""),
            }
            if c.get("winner") is True:
                winner = code
        return {
            "id": ev.get("id"),
            "start": ev.get("date") or comp.get("date") or "",   # scheduled tip, ISO UTC
            "teams": teams,
            "state": stype.get("state", ""),        # "pre" | "in" | "post"
            "completed": bool(stype.get("completed")),
            "period": int(status.get("period") or 0),
            "clock": status.get("displayClock", ""),
            "winner": winner,
        }
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def fetch_games(day: date, session: requests.Session | None = None) -> list[dict]:
    s = session or requests.Session()
    r = s.get(config.ESPN_SCOREBOARD, params={"dates": day.strftime("%Y%m%d")}, timeout=20)
    r.raise_for_status()
    return [g for g in (normalize_event(e) for e in r.json().get("events", [])) if g]


def match_game(market: dict, games: list[dict]) -> dict | None:
    """Find the ESPN game for a Kalshi market by team code, falling back to city name."""
    for g in games:
        if market["team"] in g["teams"]:
            return g
    name = market["team_name"].lower()
    if name:
        for g in games:
            for t in g["teams"].values():
                if t["location"].lower() == name or t["name"].lower() == name:
                    return g
    return None


def team_code_in_game(market: dict, game: dict) -> str | None:
    if market["team"] in game["teams"]:
        return market["team"]
    name = market["team_name"].lower()
    for code, t in game["teams"].items():
        if t["location"].lower() == name or t["name"].lower() == name:
            return code
    return None
