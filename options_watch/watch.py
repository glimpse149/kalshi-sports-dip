"""Weekly Monday check on the Robinhood option positions in positions.json.

Pulls the stock price and the option's bid/ask from Yahoo Finance (yfinance),
works out what the position is worth against what was paid, flags the exit
plan, and sends one message to the 'updates' Telegram bot.

Run:  python -m options_watch.watch
Edit positions.json to change contracts, fill price, targets or add a trade.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).parent
POSITIONS = HERE / "positions.json"
STATE = HERE / "state.json"


# ---------- formatting (dollars first, percent second) ----------

def usd(x: float) -> str:
    return f"${x:,.2f}"


def signed(x: float) -> str:
    sign = "+" if x > 0 else "−" if x < 0 else ""
    return f"{sign}${abs(x):,.2f}"


def pct(x: float) -> str:
    return f"{x * 100:+.0f}%"


# ---------- data ----------

def fetch_quote(ticker: str, expiry: str, strike: float) -> dict:
    """Stock price, its change over ~1 week, and the option's bid/ask/last."""
    import yfinance as yf

    t = yf.Ticker(ticker)
    hist = t.history(period="1mo", interval="1d")
    closes = [float(x) for x in hist["Close"].dropna().tolist()]
    if not closes:
        raise RuntimeError(f"no price history for {ticker}")
    price = closes[-1]
    week_ago = closes[-6] if len(closes) >= 6 else closes[0]

    calls = t.option_chain(expiry).calls
    row = calls[calls["strike"] == float(strike)]
    if row.empty:
        raise RuntimeError(f"no {ticker} ${strike} call for {expiry}")
    r = row.iloc[0]
    return {
        "price": price,
        "week_ago": week_ago,
        "bid": float(r.get("bid") or 0),
        "ask": float(r.get("ask") or 0),
        "last": float(r.get("lastPrice") or 0),
    }


def option_mark(q: dict) -> float:
    """Midpoint when there's a real two-sided quote, otherwise last trade."""
    if q["bid"] > 0 and q["ask"] > 0:
        return (q["bid"] + q["ask"]) / 2
    return q["last"]


# ---------- message ----------

def position_block(p: dict, q: dict | None, prev: dict | None, today: date, err: str | None = None) -> tuple[str, dict | None]:
    expiry = date.fromisoformat(p["expiry"])
    exit_by = date.fromisoformat(p["exit_by"])
    days_left = (expiry - today).days
    head = f"{p['name']} · {expiry:%b %-d} · {p['contracts']} contracts"

    if days_left < 0:
        return f"⚪ {head}\nExpired {expiry:%b %-d}. Remove it from positions.json.", None
    if err or q is None:
        return f"⚠️ {head}\nCouldn't get a quote this week ({err}). Check it in Robinhood.", None

    n = p["contracts"]
    mark = option_mark(q)
    cost = p["entry"] * 100 * n
    value = mark * 100 * n
    pnl = value - cost
    breakeven = p["strike"] + p["entry"]
    to_be = breakeven - q["price"]
    wk = q["price"] - q["week_ago"]

    lines = [f"{'🟢' if pnl >= 0 else '🔴'} {head}"]
    lines.append(
        f"{p['ticker']} {usd(q['price'])} ({signed(wk)} this week, {pct(wk / q['week_ago'])})"
    )
    spread = f"bid {usd(q['bid'])} / ask {usd(q['ask'])}" if q["bid"] > 0 else f"last trade {usd(q['last'])}"
    lines.append(f"Option: ~{usd(mark)} ({spread}) · paid {usd(p['entry'])}")
    if prev and prev.get("mark") is not None:
        lines.append(f"Option vs last Monday: {signed((mark - prev['mark']) * 100 * n)} on the position")
    lines.append(f"Position: {usd(value)} vs {usd(cost)} paid → {signed(pnl)} ({pct(pnl / cost)})")
    if to_be > 0:
        lines.append(f"Breakeven {usd(breakeven)}: needs {signed(to_be)} more by expiry")
    else:
        lines.append(f"Above breakeven {usd(breakeven)} by {usd(-to_be)}")
    lines.append(f"{days_left} days to expiry · plan to be out by {exit_by:%b %-d}")

    # exit-plan flags
    if mark >= p["take_profit"]:
        lines.append(f"🎯 TARGET HIT: at/above {usd(p['take_profit'])}. Plan was to sell at least half.")
    elif mark <= p["cut_loss"]:
        lines.append(f"✂️ CUT-LOSS LEVEL: at/below {usd(p['cut_loss'])}. Plan was to sell and keep what's left.")
    if today >= exit_by:
        lines.append("⏰ EXIT WINDOW: past your planned exit date. Time decay speeds up from here.")
    elif (exit_by - today).days <= 7:
        lines.append(f"⏰ Exit date is this week ({exit_by:%a %b %-d}).")

    return "\n".join(lines), {"mark": mark, "price": q["price"]}


def build_message(positions: list[dict], quotes: dict, state: dict, today: date) -> tuple[str, dict]:
    out = [f"📈 Weekly options check · {today:%a %b %-d}"]
    new_state: dict = {}
    total_cost = total_value = 0.0
    for p in positions:
        key = f"{p['ticker']}-{p['strike']}-{p['expiry']}"
        q, err = quotes.get(key, (None, "no data"))
        block, snap = position_block(p, q, state.get(key), today, err)
        out += ["", block]
        if snap:
            new_state[key] = snap
            total_cost += p["entry"] * 100 * p["contracts"]
            total_value += snap["mark"] * 100 * p["contracts"]
    if total_cost:
        tot = total_value - total_cost
        out += ["", f"Total: {usd(total_value)} vs {usd(total_cost)} paid → {signed(tot)} ({pct(tot / total_cost)})"]
    out += ["", "Values use the bid/ask midpoint. If a fill price differs, update options_watch/positions.json."]
    return "\n".join(out), new_state


# ---------- telegram ----------

def send(text: str) -> bool:
    token = (os.getenv("UPDATES_TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.getenv("UPDATES_TELEGRAM_CHAT_ID") or "").strip()
    if not (token and chat):
        print("[telegram not configured]\n" + text)
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True},
            timeout=20,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[telegram failed] {e}\n{text}")
        return False


def main() -> None:
    positions = json.loads(POSITIONS.read_text())
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    today = datetime.now(timezone.utc).date()

    quotes = {}
    for p in positions:
        key = f"{p['ticker']}-{p['strike']}-{p['expiry']}"
        if date.fromisoformat(p["expiry"]) < today:
            continue
        try:
            quotes[key] = (fetch_quote(p["ticker"], p["expiry"], p["strike"]), None)
        except Exception as e:  # one bad quote shouldn't block the rest
            quotes[key] = (None, str(e)[:120])

    msg, new_state = build_message(positions, quotes, state, today)
    print(msg)
    send(msg)
    if new_state:
        STATE.write_text(json.dumps(new_state, indent=2) + "\n")


if __name__ == "__main__":
    main()
