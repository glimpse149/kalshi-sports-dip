"""Offline tests: simulate a game with fake Kalshi + ESPN snapshots."""
from datetime import date

from bot import espn, kalshi, notify, strategy

EVENT = "KXNBAGAME-26NOV09NYKBOS"


def mkts(bos_bid, bos_ask):
    raw = [
        {"ticker": f"{EVENT}-BOS", "event_ticker": EVENT, "yes_sub_title": "Boston",
         "yes_bid": bos_bid, "yes_ask": bos_ask, "status": "open"},
        {"ticker": f"{EVENT}-NYK", "event_ticker": EVENT, "yes_sub_title": "New York",
         "yes_bid": 100 - bos_ask, "yes_ask": 100 - bos_bid, "status": "open"},
    ]
    return [kalshi.normalize_market(m) for m in raw]


def game(state, period=0, bos=0, ny=0, winner=None):
    ev = {"id": "401", "competitions": [{
        "status": {"period": period, "displayClock": "5:00",
                   "type": {"state": state, "completed": state == "post"}},
        "competitors": [
            {"homeAway": "home", "score": str(bos), "winner": winner == "BOS",
             "team": {"abbreviation": "BOS", "location": "Boston", "shortDisplayName": "Celtics"}},
            {"homeAway": "away", "score": str(ny), "winner": winner == "NYK",
             "team": {"abbreviation": "NY", "location": "New York", "shortDisplayName": "Knicks"}},
        ]}]}
    return [espn.normalize_event(ev)]


def test_parse_and_mapping():
    assert kalshi.parse_event_date(EVENT) == date(2026, 11, 9)
    m = kalshi.normalize_market({"ticker": "X-1-BOS", "yes_bid_dollars": "0.55", "yes_ask_dollars": "0.57"})
    assert m["bid"] == 0.55 and m["ask"] == 0.57
    assert game("pre")[0]["teams"].keys() == {"BOS", "NYK"}  # ESPN "NY" -> Kalshi "NYK"


def test_fee_matches_kalshi_table():
    assert strategy.taker_fee(100, 0.50) == 1.75
    assert strategy.taker_fee(100, 0.10) == 0.63
    assert strategy.taker_fee(10, 0.55) == 0.18


def test_early_dip_buy_and_win():
    s = strategy.new_state()
    assert strategy.step(s, mkts(81, 83), game("pre")) == []
    assert strategy.step(s, mkts(70, 72), game("in", 1, 10, 18)) == []   # dropped only 10c
    out = strategy.step(s, mkts(54, 56), game("in", 2, 40, 52))           # 26c+ below 82c
    assert len(out) == 1 and out[0]["bucket"] == "early" and out[0]["entry"] == 0.56
    assert strategy.step(s, mkts(40, 42), game("in", 2, 40, 60)) == []   # only one trade per game
    done = strategy.settle(s, {"401": "BOS"})
    assert done[0]["won"] and done[0]["pnl"] == round(10 - (5.60 + strategy.taker_fee(10, 0.56)), 2)
    msg = notify.summary_msg(s, done, "test")
    assert "Early dips" in msg and "+$" in msg


def test_late_dip_is_control_and_loss():
    s = strategy.new_state()
    strategy.step(s, mkts(84, 86), game("pre"))
    assert strategy.step(s, mkts(70, 72), game("in", 2, 50, 54)) == []
    out = strategy.step(s, mkts(45, 47), game("in", 3, 60, 72))
    assert out[0]["bucket"] == "late"
    done = strategy.settle(s, {"401": "NYK"})
    assert not done[0]["won"] and done[0]["pnl"] < 0


def test_no_favorite_no_trade():
    s = strategy.new_state()
    strategy.step(s, mkts(60, 62), game("pre"))          # 61c favorite: below 75c bar
    assert strategy.step(s, mkts(20, 22), game("in", 1, 10, 30)) == []


def test_missed_pregame_means_no_trade():
    s = strategy.new_state()
    assert strategy.step(s, mkts(20, 22), game("in", 1, 10, 30)) == []


def test_wide_spread_skipped():
    s = strategy.new_state()
    strategy.step(s, mkts(84, 86), game("pre"))
    assert strategy.step(s, mkts(40, 55), game("in", 1, 10, 25)) == []
