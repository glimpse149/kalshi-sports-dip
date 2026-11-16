"""Entry point.

  python -m bot live [nba|ncaaf]   # watch today's games, paper-buy dips, alert on Telegram
  python -m bot settle             # settle finished games for all live sports + daily summary
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import config, espn, kalshi, notify, strategy
from .sports import LIVE_SPORTS, SPORTS, scoreboard_url

ROOT = Path(__file__).resolve().parent.parent
ET = ZoneInfo("America/New_York")
SUMMARY_STATE = ROOT / "state" / "summary.json"
FIELDS = ["date", "team", "opponent", "bucket", "pregame", "entry", "contracts", "fee",
          "cost", "period", "clock", "score", "won", "payout", "pnl", "opened_at", "closed_at", "ticker"]
EARLY_LABEL = {"nba": "Q1–Q2", "ncaaf": "Q1"}


def state_path(sport: str) -> Path:
    # NBA keeps its original file names so its history carries on
    return ROOT / "state" / ("state.json" if sport == "nba" else f"{sport}.json")


def trades_path(sport: str) -> Path:
    return ROOT / "data" / ("trades.csv" if sport == "nba" else f"trades_{sport}.csv")


def load(sport: str) -> dict:
    p = state_path(sport)
    return json.loads(p.read_text()) if p.exists() else strategy.new_state()


def save(sport: str, state: dict) -> None:
    p = state_path(sport)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1, default=str))


def append_trades(sport: str, rows: list[dict]) -> None:
    if not rows:
        return
    p = trades_path(sport)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with p.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


def et_today() -> date:
    return datetime.now(ET).date()


def slate_date() -> date:
    """Today's slate. Before 6am ET we're still on last night's games."""
    return (datetime.now(ET) - timedelta(hours=6)).date()


def fetch_games(sport_key: str, d: date, s: requests.Session) -> list[dict]:
    sp = SPORTS[sport_key]
    return espn.fetch_games(d, s, url=scoreboard_url(sp), params=sp["params"])


def fetch_finals(sport_key: str, dates: set[str], s: requests.Session) -> dict[str, str]:
    finals = {}
    for d in dates:
        try:
            for g in fetch_games(sport_key, date.fromisoformat(d), s):
                if g["completed"] and g["winner"]:
                    finals[g["id"]] = g["winner"]
        except Exception as e:
            print(f"[espn finals {sport_key} {d}] {e}")
    return finals


def settle_open(sport_key: str, state: dict, s: requests.Session) -> list[dict]:
    if not state["open"]:
        return []
    finals = fetch_finals(sport_key, {p["date"] for p in state["open"] if p.get("date")}, s)
    done = strategy.settle(state, finals)
    append_trades(sport_key, done)
    return done


def github_output(key: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{key}={value}\n")


def live(sport_key: str = "nba") -> None:
    sp = SPORTS[sport_key]
    state = load(sport_key)
    s = requests.Session()
    s.headers["User-Agent"] = "kalshi-sports-dip/1.0 (paper trading research)"
    started = time.monotonic()
    errors = 0
    today = slate_date()          # fixed at start, even if the run goes past midnight
    print(f"{sp['name']} live run start {datetime.now(ET):%Y-%m-%d %H:%M %Z}, slate {today}")

    def lookup(market: dict, game: dict) -> float | None:
        if not game.get("start"):
            return None
        ts = int(datetime.fromisoformat(game["start"].replace("Z", "+00:00")).timestamp())
        return kalshi.pregame_mid(market["ticker"], ts, s, series=sp["series"])

    finished = False
    while (time.monotonic() - started) / 60 < config.MAX_RUN_MINUTES:
        try:
            games = fetch_games(sport_key, today, s)
            markets = [m for m in kalshi.fetch_markets(s, series=sp["series"]) if m["date"] == today]
            errors = 0
        except Exception as e:
            errors += 1
            print(f"[fetch error {errors}] {e}")
            if errors == 10:
                notify.send(f"⚠️ Favorite-dip bot ({sp['name']}): data feeds failing ({e}). Still retrying.")
            time.sleep(config.POLL_SECONDS)
            continue

        for p in strategy.step(state, markets, games, pregame_lookup=lookup,
                               early_periods=sp["live_early_periods"]):
            print("ENTRY", p)
            notify.send(notify.entry_msg(p, sp))
        for p in settle_open(sport_key, state, s):
            notify.send(notify.settle_msg(p, sp))
        save(sport_key, state)

        if not games:
            print(f"no {sp['name']} games on {today}; stopping")
            finished = True
            break
        if all(g["state"] == "post" for g in games) and not state["open"]:
            print("all games final; stopping")
            finished = True
            break
        time.sleep(config.POLL_SECONDS)

    strategy.prune(state, today=str(et_today()))
    save(sport_key, state)

    # GitHub jobs stop at 6h; a college football Saturday runs ~14h. If games are still on
    # (and it's before 6am the next morning), ask the workflow to start another run.
    cutoff = datetime.combine(today + timedelta(days=1), datetime.min.time(), ET) + timedelta(hours=6)
    if not finished and datetime.now(ET) < cutoff:
        print("time limit reached with games still on; requesting another run")
        github_output("continue", "true")


def settle_cmd() -> None:
    s = requests.Session()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
    label = (et_today() - timedelta(days=1)).strftime("%a %b %-d")
    sections, any_new = [], False
    for key in LIVE_SPORTS:
        state = load(key)
        newly = settle_open(key, state, s)
        any_new = any_new or bool(newly)
        recent = [p for p in state["closed"] if p.get("closed_at", "") >= cutoff]
        sections.append(notify.summary_section(state, recent, SPORTS[key], EARLY_LABEL.get(key, "strategy")))
        save(key, state)

    meta = json.loads(SUMMARY_STATE.read_text()) if SUMMARY_STATE.exists() else {}
    # two settle runs can fire (cron-job.org + GitHub backup); only one summary per day,
    # unless the second one settles something new
    if meta.get("last_summary") != label or any_new:
        notify.send(notify.summary_msg({}, [], label, sections=sections))
        meta["last_summary"] = label
        SUMMARY_STATE.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_STATE.write_text(json.dumps(meta))
    else:
        print(f"summary for {label} already sent")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "live"
    if cmd == "live":
        live(sys.argv[2] if len(sys.argv) > 2 else "nba")
    elif cmd == "settle":
        settle_cmd()
    else:
        sys.exit(f"unknown command {cmd}")
