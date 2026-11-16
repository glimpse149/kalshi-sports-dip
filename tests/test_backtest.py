from bot import backtest

Q3 = 1000 + 70 * 60


def g(winner="BOS", candles=None):
    return {"date": "2026-11-01", "teams": ["BOS", "NYK"], "winner": winner, "fav": "BOS",
            "fav_pre": 0.82, "tip": 1000, "periods": {"1": 1000, "2": 1000 + 35 * 60, "3": Q3, "4": Q3 + 35 * 60},
            "end": 1000 + 150 * 60, "candles": candles or []}


def test_early_dip_win():
    c = [[1000, 0.81, 0.83], [1060, 0.70, 0.72], [1600, 0.54, 0.56], [1700, 0.40, 0.42]]
    t = backtest.simulate(g(candles=c), 0.25, early_periods=2)
    assert t["entry"] == 0.56 and t["bucket"] == "early" and t["period"] == 1 and t["won"] and t["pnl"] > 0


def test_late_dip_and_filters():
    c = [[1600, 0.40, 0.55],            # spread too wide
         [Q3 + 60, 0.50, 0.52],         # first valid dip, in Q3
         [1000 + 151 * 60, 0.0, 0.01]]  # after the game: ignored
    t = backtest.simulate(g(winner="NYK", candles=c), 0.25, early_periods=2)
    assert t["bucket"] == "late" and t["period"] == 3 and not t["won"] and t["pnl"] < 0
    # hockey-style: only period 1 counts as early
    t = backtest.simulate(g(candles=[[1000 + 40 * 60, 0.50, 0.52]]), 0.25, early_periods=1)
    assert t["period"] == 2 and t["bucket"] == "late"


def test_no_dip():
    assert backtest.simulate(g(candles=[[1600, 0.70, 0.72]]), 0.25) is None


def test_event_date():
    assert backtest.event_date("KXNFLGAME-26NOV15PITCIN") == "2026-11-15"


def team(code, *names, home=False):
    return code, {"home": home, "names": {backtest.norm(n) for n in names}}


def test_match_by_code_and_name():
    ev = [{"event": "E1", "markets": [
        {"ticker": "E1-CCSU", "code": "CCSU", "name": "Central Connecticut St."},
        {"ticker": "E1-LIU", "code": "LIU", "name": "LIU"}]},
        {"event": "E2", "markets": [
        {"ticker": "E2-LAR", "code": "LAR", "name": "Los Angeles R"},
        {"ticker": "E2-ARI", "code": "ARI", "name": "Arizona"}]}]
    game = {"teams": dict([team("CCSU", "Central Connecticut State"), team("LIU", "Long Island University", home=True)])}
    assert backtest.match(game, ev) == {"CCSU": "E1-CCSU", "LIU": "E1-LIU"}
    game = {"teams": dict([team("LA", "Los Angeles Rams", "Rams"), team("ARI", "Arizona", "Cardinals")])}
    assert backtest.match(game, ev) == {"LA": "E2-LAR", "ARI": "E2-ARI"}
