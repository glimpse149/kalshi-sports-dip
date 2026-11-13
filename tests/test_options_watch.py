"""Offline tests for the weekly options message (no network)."""
from datetime import date

from options_watch import watch

FSLY = {"name": "FSLY $20 Call", "ticker": "FSLY", "strike": 20, "expiry": "2027-01-15",
        "contracts": 5, "entry": 0.95, "take_profit": 1.90, "cut_loss": 0.475, "exit_by": "2026-12-28"}
SKM = {"name": "SKM $40 Call", "ticker": "SKM", "strike": 40, "expiry": "2026-12-18",
       "contracts": 5, "entry": 0.50, "take_profit": 1.00, "cut_loss": 0.25, "exit_by": "2026-12-04"}


def key(p):
    return f"{p['ticker']}-{p['strike']}-{p['expiry']}"


def test_profit_and_target_flag():
    q = {"price": 23.0, "week_ago": 20.0, "bid": 1.90, "ask": 2.10, "last": 2.0}
    msg, st = watch.build_message([FSLY], {key(FSLY): (q, None)}, {}, date(2026, 11, 16))
    assert "+$525.00" in msg          # (2.00 - 0.95) * 100 * 5
    assert "TARGET HIT" in msg
    assert "+$3.00 this week" in msg
    assert st[key(FSLY)]["mark"] == 2.0


def test_loss_cut_flag_and_exit_window():
    q = {"price": 33.0, "week_ago": 34.0, "bid": 0.20, "ask": 0.25, "last": 0.22}
    msg, _ = watch.build_message([SKM], {key(SKM): (q, None)}, {key(SKM): {"mark": 0.5}}, date(2026, 12, 7))
    assert "CUT-LOSS" in msg
    assert "EXIT WINDOW" in msg
    assert "Option vs last Monday: −$137.50" in msg


def test_expired_and_quote_error():
    msg, st = watch.build_message([SKM, FSLY], {key(FSLY): (None, "boom")}, {}, date(2026, 12, 21))
    assert "Expired" in msg and "Couldn't get a quote" in msg
    assert st == {}


def test_no_bid_uses_last_trade():
    q = {"price": 34.0, "week_ago": 34.0, "bid": 0.0, "ask": 0.0, "last": 0.60}
    msg, _ = watch.build_message([SKM], {key(SKM): (q, None)}, {}, date(2026, 11, 16))
    assert "last trade $0.60" in msg
    assert "+$50.00" in msg
