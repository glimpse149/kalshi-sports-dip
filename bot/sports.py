"""Per-sport settings shared by the backtest (and later the live bot).

early_periods: entries in periods 1..early_periods count as "early" (the strategy);
later periods are the "late" control group.
"""

SPORTS = {
    "nba": {
        "name": "NBA",
        "series": "KXNBAGAME",
        "espn": "basketball/nba",
        "params": {},
        "early_periods": 2,          # quarters: Q1-Q2
        "season_start": "2026-10-20",
    },
    "ncaamb": {
        "name": "College basketball (men)",
        "series": "KXNCAAMBGAME",
        "espn": "basketball/mens-college-basketball",
        "params": {"groups": "50", "limit": "500"},   # all of Division I
        "early_periods": 1,          # halves: 1st half
        "season_start": "2026-11-02",
    },
    "nfl": {
        "name": "NFL",
        "series": "KXNFLGAME",
        "espn": "football/nfl",
        "params": {},
        "early_periods": 2,          # quarters: Q1-Q2
        "season_start": "2026-09-09",
    },
    "ncaaf": {
        "name": "College football (FBS)",
        "series": "KXNCAAFGAME",
        "espn": "football/college-football",
        "params": {"groups": "80", "limit": "300"},   # FBS
        "early_periods": 2,
        "season_start": "2026-08-28",
    },
    "nhl": {
        "name": "NHL",
        "series": "KXNHLGAME",
        "espn": "hockey/nhl",
        "params": {},
        "early_periods": 1,          # periods: 1st period (2nd and 3rd reported too)
        "season_start": "2026-10-06",
    },
}

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
