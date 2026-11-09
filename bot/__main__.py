"""Entry point.

  python -m bot live     # watch tonight's games, paper-buy dips, alert on Telegram
  python -m bot settle   # settle finished games + send the daily summary
"""
from __future__ import annotations

import csv
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import config, espn, kalshi, notify, strategy

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "state.json"
TRADES = ROOT / "data" / "trades.csv"
ET = ZoneInfo("America/New_York")
FIELDS = ["date", "team", "opponent", "bucket", "pregame", "entry", "contracts", "fee",
          "cost", "period", "clock", "score", "won", "payout", "pnl", "opened_at", "closed_at", "ticker"]


def load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return strategy.new_state()


def save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, default=str))


def append_trades(rows: list[dict]) -> None:
    if not rows:
        return
    TRADES.parent.mkdir(parents=True, exist_ok=True)
    new = not TRADES.exists()
    with TRADES.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


def et_today() -> date:
    return datetime.now(ET).date()


def fetch_finals(dates: set[str], s: requests.Session) -> dict[str, str]:
    finals = {}
    for d in dates:
        try:
            for g in espn.fetch_games(date.fromisoformat(d), s):
                if g["completed"] and g["winner"]:
                    finals[g["id"]] = g["winner"]
        except Exception as e:
            print(f"[espn finals {d}] {e}")
    return finals


def settle_open(state: dict, s: requests.Session) -> list[dict]:
    if not state["open"]:
        return []
    finals = fetch_finals({p["date"] for p in state["open"] if p.get("date")}, s)
    done = strategy.settle(state, finals)
    append_trades(done)
    return done


def live() -> None:
    state = load()
    s = requests.Session()
    s.headers["User-Agent"] = "kalshi-sports-dip/1.0 (paper trading research)"
    started = time.monotonic()
    errors = 0
    print(f"live run start {datetime.now(ET):%Y-%m-%d %H:%M %Z}")

    # the slate we watch is fixed at start (run begins ~6:30pm ET), even after midnight
    today = et_today()
    while (time.monotonic() - started) / 60 < config.MAX_RUN_MINUTES:
        try:
            games = espn.fetch_games(today, s)
            markets = [m for m in kalshi.fetch_markets(s) if m["date"] == today]
            errors = 0
        except Exception as e:
            errors += 1
            print(f"[fetch error {errors}] {e}")
            if errors == 10:
                notify.send(f"⚠️ Favorite-dip bot: data feeds failing ({e}). Still retrying.")
            time.sleep(config.POLL_SECONDS)
            continue

        for p in strategy.step(state, markets, games):
            print("ENTRY", p)
            notify.send(notify.entry_msg(p))
        for p in settle_open(state, s):
            notify.send(notify.settle_msg(p))
        save(state)

        if games and all(g["state"] == "post" for g in games) and not state["open"]:
            print("all games final; stopping")
            break
        if not games:
            print("no NBA games today; stopping")
            break
        time.sleep(config.POLL_SECONDS)

    strategy.prune(state, today=str(et_today()))
    save(state)


def settle_cmd() -> None:
    state = load()
    s = requests.Session()
    settle_open(state, s)
    # everything that closed in the last ~20h counts as "last night"
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
    recent = [p for p in state["closed"] if p.get("closed_at", "") >= cutoff]
    label = (et_today() - timedelta(days=1)).strftime("%a %b %-d")
    notify.send(notify.summary_msg(state, recent, label))
    save(state)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "live"
    {"live": live, "settle": settle_cmd}[cmd]()
