from bot import backtest


def g(winner="BOS", candles=None):
    return {"date": "2026-11-01", "teams": ["BOS", "NYK"], "winner": winner, "fav": "BOS",
            "fav_pre": 0.82, "tip": 1000, "q3": 1000 + 70 * 60, "end": 1000 + 150 * 60,
            "candles": candles or []}


def test_early_dip_win():
    c = [[1000, 0.81, 0.83], [1060, 0.70, 0.72], [1600, 0.54, 0.56], [1700, 0.40, 0.42]]
    t = backtest.simulate(g(candles=c), 0.25)
    assert t["entry"] == 0.56 and t["bucket"] == "early" and t["won"] and t["pnl"] > 0


def test_late_dip_and_filters():
    q3 = 1000 + 70 * 60
    c = [[1600, 0.40, 0.55],            # spread too wide
         [q3 + 60, 0.50, 0.52],         # first valid dip, in Q3
         [1000 + 151 * 60, 0.0, 0.01]]  # after the game: ignored
    t = backtest.simulate(g(winner="NYK", candles=c), 0.25)
    assert t["bucket"] == "late" and not t["won"] and t["pnl"] < 0


def test_no_dip():
    assert backtest.simulate(g(candles=[[1600, 0.70, 0.72]]), 0.25) is None
