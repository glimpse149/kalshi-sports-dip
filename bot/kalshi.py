"""Read-only Kalshi market data (public endpoints, no API key needed)."""
from __future__ import annotations

import re
from datetime import date

import requests

from . import config

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

# KXNBAGAME-26NOV09LALBOS  ->  date 2026-11-09, teams "LALBOS"
EVENT_RE = re.compile(r"^[A-Z]+-(\d{2})([A-Z]{3})(\d{2})([A-Z]+)$")


def _price(m: dict, key: str) -> float | None:
    """Kalshi returns cents (yes_bid=55) and/or dollar strings (yes_bid_dollars='0.55')."""
    d = m.get(f"{key}_dollars")
    if d not in (None, ""):
        try:
            return float(d)
        except (TypeError, ValueError):
            pass
    c = m.get(key)
    if c in (None, ""):
        return None
    return float(c) / 100.0


def parse_event_date(event_ticker: str) -> date | None:
    m = EVENT_RE.match(event_ticker or "")
    if not m:
        return None
    yy, mon, dd, _ = m.groups()
    if mon not in MONTHS:
        return None
    return date(2000 + int(yy), MONTHS[mon], int(dd))


def normalize_market(m: dict) -> dict:
    ticker = m.get("ticker", "")
    event = m.get("event_ticker") or ticker.rsplit("-", 1)[0]
    team = ticker.rsplit("-", 1)[-1] if "-" in ticker else ""
    bid, ask = _price(m, "yes_bid"), _price(m, "yes_ask")
    return {
        "ticker": ticker,
        "event": event,
        "team": team,                                  # e.g. "BOS"
        "team_name": m.get("yes_sub_title") or "",     # e.g. "Boston"
        "bid": bid,
        "ask": ask,
        "mid": (bid + ask) / 2 if bid is not None and ask is not None and ask > 0 else None,
        "status": m.get("status", ""),
        "result": m.get("result", ""),
        "date": parse_event_date(event),
    }


def fetch_markets(session: requests.Session | None = None) -> list[dict]:
    """All open NBA game-winner markets, normalized."""
    s = session or requests.Session()
    out, cursor = [], None
    for _ in range(10):  # pagination guard
        params = {"series_ticker": config.KALSHI_SERIES, "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        r = s.get(f"{config.KALSHI_API}/markets", params=params, timeout=20)
        r.raise_for_status()
        js = r.json()
        out += [normalize_market(m) for m in js.get("markets", [])]
        cursor = js.get("cursor")
        if not cursor:
            break
    return out
