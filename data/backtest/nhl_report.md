# NHL — favorite-dip backtest, 2026-10-06 to 2026-11-15

287 finished games, 287 with Kalshi prices + play timing.
50 contracts per trade, buying at the ask + taker fee, held to the end. "Early" = period 1–1.

## Live rule: favorite ≥70¢, buy a 15¢+ dip (21 games had such a favorite)

| | Trades | Won | Avg buy | Edge | P&L | ROI |
|---|---|---|---|---|---|---|
| Early dips (strategy) | 6 | 83% | 57¢ | +26 pts | +$74.34 | +42.3% |
| Late dips (control) | 0 | – | – | – | – | – |
| …bought in period 1 | 6 | 83% | 57¢ | +26 pts | +$74.34 | +42.3% |
| Baseline: buy every favorite at the start | 21 | 95% | 76¢ | +19 pts | +$190.54 | +23.5% |

**Edge** = how often the team won minus the price paid. Positive means the market underpriced it.

## Variations — early dips: P&L [trades]

| Favorite ≥ \ dip | 10¢ | 15¢ | 20¢ | 25¢ |
|---|---|---|---|---|
| 60¢ | −$66.55 [38] | −$23.63 [37] | +$67.49 [14] | +$40.67 [11] |
| 65¢ | −$64.78 [20] | −$26.91 [20] | −$24.29 [8] | +$7.21 [7] |
| 70¢ | +$60.51 [6] | +$74.34 [6] | +$3.79 [2] | +$3.79 [2] |
| 75¢ | −$15.62 [2] | −$8.70 [2] | −$26.38 [1] | −$26.38 [1] |
| 80¢ | $0.00 [0] | $0.00 [0] | $0.00 [0] | $0.00 [0] |

## Every trade (live rule)

| Date | Team | vs | Pre-game | Bought | Period | Result | P&L |
|---|---|---|---|---|---|---|---|
| 2026-10-10 | NJ | VAN | 72¢ | 57¢ | 1 | ✅ | +$20.64 |
| 2026-10-15 | TB | SEA | 72¢ | 56¢ | 1 | ✅ | +$21.13 |
| 2026-10-15 | FLA | VAN | 72¢ | 56¢ | 1 | ✅ | +$21.13 |
| 2026-10-17 | TB | VAN | 78¢ | 63¢ | 1 | ✅ | +$17.68 |
| 2026-11-07 | DAL | SJ | 74¢ | 58¢ | 1 | ✅ | +$20.14 |
| 2026-11-15 | VGK | VAN | 78¢ | 51¢ | 1 | ❌ | −$26.38 |
