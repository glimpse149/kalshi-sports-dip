"""Live scores from ESPN's public scoreboard feeds (NBA by default)."""
from __future__ import annotations

import re
from datetime import date

import requests

from . import config

# ESPN abbreviation -> Kalshi abbreviation where they differ
ESPN_TO_KALSHI = {
    "GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP",
    "UTAH": "UTA", "WSH": "WAS", "BKN": "BKN", "PHX": "PHX",
}


def norm(x: str) -> str:
    x = (x or "").lower().replace("st.", "state").replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", x)


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
                "names": sorted({norm(t.get(k, "")) for k in
                                 ("location", "displayName", "shortDisplayName", "name", "nickname")} - {""}),
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


def fetch_games(day: date, session: requests.Session | None = None,
                url: str = config.ESPN_SCOREBOARD, params: dict | None = None) -> list[dict]:
    s = session or requests.Session()
    r = s.get(url, params={"dates": day.strftime("%Y%m%d"), **(params or {})}, timeout=20)
    r.raise_for_status()
    return [g for g in (normalize_event(e) for e in r.json().get("events", [])) if g]


def _names(t: dict) -> set[str]:
    return set(t.get("names") or []) | {norm(t.get("location", "")), norm(t.get("name", ""))} - {""}


def team_code_in_game(market: dict, game: dict) -> str | None:
    """Which team in this game a Kalshi market is for: code, then exact name, then unique prefix
    (Kalshi "Central Connecticut St." vs ESPN "Central Connecticut")."""
    if market["team"] in game["teams"]:
        return market["team"]
    name = norm(market.get("team_name", ""))
    if not name:
        return None
    hits = [c for c, t in game["teams"].items() if name in _names(t)]
    if len(hits) == 1:
        return hits[0]
    hits = [c for c, t in game["teams"].items()
            if any(n.startswith(name) or name.startswith(n) for n in _names(t) if len(n) >= 4)]
    return hits[0] if len(hits) == 1 else None


def match_event(markets: list[dict], games: list[dict]) -> dict | None:
    """The one game whose two teams the event's markets map onto (both of them, distinctly)."""
    found = []
    for g in games:
        codes = [team_code_in_game(m, g) for m in markets]
        if all(codes) and len(set(codes)) == len(markets) >= 2:
            found.append(g)
    return found[0] if len(found) == 1 else None


def match_game(market: dict, games: list[dict]) -> dict | None:
    """Single-market lookup (kept for compatibility): unique game containing this team."""
    hits = [g for g in games if team_code_in_game(market, g)]
    return hits[0] if len(hits) == 1 else None
