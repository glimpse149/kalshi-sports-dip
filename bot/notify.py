"""Sends messages to the 'updates' Telegram bot.

Secrets (GitHub repo -> Settings -> Secrets and variables -> Actions):
  UPDATES_TELEGRAM_BOT_TOKEN, UPDATES_TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import os

import requests

from .strategy import totals


def send(text: str) -> bool:
    token = os.getenv("UPDATES_TELEGRAM_BOT_TOKEN")
    chat = os.getenv("UPDATES_TELEGRAM_CHAT_ID")
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
    except Exception as e:  # never let alerts crash the bot
        print(f"[telegram failed] {e}\n{text}")
        return False


def c(x: float) -> str:
    return f"{round(x * 100)}¢"


def money(x: float) -> str:
    return f"{'+' if x > 0 else '−' if x < 0 else ''}${abs(x):.2f}"


def entry_msg(p: dict) -> str:
    drop = p["pregame"] - p["entry"]
    tag = "DIP BUY" if p["bucket"] == "early" else "LATE DIP (control)"
    return (
        f"🏀 {tag} · paper\n"
        f"{p['team']} vs {p['opponent']} — Q{p['period']} {p['clock']}, {p['score']}\n"
        f"{p['team']} was {c(p['pregame'])} pre-game, now {c(p['entry'])} (−${drop:.2f}/contract)\n"
        f"Bought {p['contracts']} @ {c(p['entry'])} = ${p['cost']:.2f} incl. ${p['fee']:.2f} fee\n"
        f"Pays ${p['contracts']:.2f} if {p['team']} wins"
    )


def settle_msg(p: dict) -> str:
    icon = "✅" if p["won"] else "❌"
    result = "won" if p["won"] else "lost"
    return f"{icon} {p['team']} {result} vs {p['opponent']} · {money(p['pnl'])} ({p['bucket']}, bought @ {c(p['entry'])})"


def summary_msg(state: dict, settled_today: list[dict], label: str) -> str:
    lines = [f"📊 Favorite-dip paper bot — {label}"]
    if settled_today:
        lines.append("")
        lines += [settle_msg(p) for p in settled_today]
    else:
        lines.append("No trades settled.")
    if state["open"]:
        lines.append(f"\nStill open: {', '.join(p['team'] for p in state['open'])}")
    lines.append("\nAll-time:")
    for b, name in [("early", "Early dips (strategy)"), ("late", "Late dips (control)")]:
        t = totals(state["closed"], b)
        if t["n"]:
            lines.append(
                f"• {name}: {money(t['pnl'])} on ${t['staked']:.2f} staked · "
                f"{t['wins']}/{t['n']} won · avg buy {c(t['avg_entry'])} · ROI {t['roi']*100:+.1f}%"
            )
        else:
            lines.append(f"• {name}: no trades yet")
    return "\n".join(lines)
