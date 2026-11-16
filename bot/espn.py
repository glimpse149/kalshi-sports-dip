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


SUFFIXES = ("state", "st", "university", "univ")


def _quality(market: dict, t: dict, code: str) -> int:
    """2 = same code or exact name, 1 = safe prefix match, 0 = no match."""
    if market["team"] == code:
        return 2
    name = norm(market.get("team_name", ""))
    if not name:
        return 0
    names = _names(t)
    if name in names:
        return 2
    for n in names:
        if len(n) < 4:
            continue
        # Kalshi shortens ESPN's name: "Los Angeles R" vs "Los Angeles Rams"
        if n.startswith(name) and len(name) >= 6:
            return 1
        # Kalshi adds only "St.": "Central Connecticut St." vs "Central Connecticut"
        # (never "Texas Southern" vs "Texas")
        if name.startswith(n) and name[len(n):] in SUFFIXES:
            return 1
    return 0


def team_code_in_game(market: dict, game: dict) -> str | None:
    """Which team in this game a Kalshi market is for (best unique match)."""
    scored = [(_quality(market, t, c), c) for c, t in game["teams"].items()]
    best = max((q for q, _ in scored), default=0)
    hits = [c for q, c in scored if q == best and q > 0]
    return hits[0] if len(hits) == 1 else None


def event_quality(markets: list[dict], game: dict) -> int:
    """Sum of match quality if every market maps to a distinct team of this game, else 0."""
    codes = [team_code_in_game(m, game) for m in markets]
    if not all(codes) or len(set(codes)) != len(markets) or len(markets) < 2:
        return 0
    return sum(_quality(m, game["teams"][c], c) for m, c in zip(markets, codes))


def match_event(markets: list[dict], games: list[dict]) -> dict | None:
    """The one game whose two teams the event's markets map onto (both of them, distinctly)."""
    found = [g for g in games if event_quality(markets, g)]
    return found[0] if len(found) == 1 else None


def assign_events(events: dict[str, list[dict]], games: list[dict]) -> dict[str, dict]:
    """event ticker -> game. If two events claim one game, keep only the better match
    (and neither if they tie), so a market is never traded against the wrong game."""
    claims: dict[str, list[tuple[int, str]]] = {}
    out: dict[str, dict] = {}
    for ev, mk in events.items():
        g = match_event(mk, games)
        if g:
            claims.setdefault(g["id"], []).append((event_quality(mk, g), ev))
            out[ev] = g
    for gid, lst in claims.items():
        if len(lst) > 1:
            lst.sort(reverse=True)
            keep = lst[0][1] if lst[0][0] > lst[1][0] else None
            for _, ev in lst:
                if ev != keep:
                    out.pop(ev, None)
    return out


def match_game(market: dict, games: list[dict]) -> dict | None:
    """Single-market lookup (kept for compatibility): unique game containing this team."""
    hits = [g for g in games if team_code_in_game(market, g)]
    return hits[0] if len(hits) == 1 else None
