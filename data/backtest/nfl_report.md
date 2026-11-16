# NFL — favorite-dip backtest, 2026-09-09 to 2026-11-15

148 finished games, 148 with Kalshi prices + play timing.
50 contracts per trade, buying at the ask + taker fee, held to the end. "Early" = period 1–2.

## Live rule: favorite ≥70¢, buy a 15¢+ dip (46 games had such a favorite)

| | Trades | Won | Avg buy | Edge | P&L | ROI |
|---|---|---|---|---|---|---|
| Early dips (strategy) | 14 | 57% | 60¢ | -3 pts | −$35.12 | -8.1% |
| Late dips (control) | 8 | 38% | 50¢ | -13 pts | −$58.14 | -27.9% |
| …bought in period 1 | 8 | 50% | 61¢ | -11 pts | −$49.63 | -19.9% |
| …bought in period 2 | 6 | 67% | 60¢ | +6 pts | +$14.51 | +7.8% |
| …bought in period 3 | 1 | 0% | 64¢ | -64 pts | −$32.81 | -100.0% |
| …bought in period 4 | 7 | 43% | 49¢ | -6 pts | −$25.33 | -14.4% |
| Baseline: buy every favorite at the start | 46 | 76% | 78¢ | -2 pts | −$79.69 | -4.4% |

**Edge** = how often the team won minus the price paid. Positive means the market underpriced it.

## Variations — early dips: P&L [trades]

| Favorite ≥ \ dip | 10¢ | 15¢ | 20¢ | 25¢ |
|---|---|---|---|---|
| 60¢ | +$103.71 [57] | +$58.80 [41] | +$101.41 [35] | +$86.85 [26] |
| 65¢ | +$151.15 [36] | +$83.49 [23] | +$147.27 [21] | +$105.41 [14] |
| 70¢ | +$28.89 [23] | −$35.12 [14] | +$34.22 [13] | +$62.66 [9] |
| 75¢ | −$17.95 [15] | −$17.18 [10] | +$39.24 [9] | +$87.54 [8] |
| 80¢ | −$105.00 [7] | −$66.93 [5] | −$21.39 [4] | +$13.43 [3] |

## Every trade (live rule)

| Date | Team | vs | Pre-game | Bought | Period | Result | P&L |
|---|---|---|---|---|---|---|---|
| 2026-09-13 | DET | NO | 74¢ | 59¢ | 4 | ✅ | +$19.65 |
| 2026-09-13 | LAC | ARI | 80¢ | 64¢ | 2 | ❌ | −$32.81 |
| 2026-09-20 | PHI | TEN | 74¢ | 58¢ | 4 | ✅ | +$20.14 |
| 2026-09-20 | TB | CLE | 78¢ | 63¢ | 4 | ❌ | −$32.32 |
| 2026-09-20 | BAL | NO | 78¢ | 60¢ | 4 | ❌ | −$30.84 |
| 2026-09-20 | LAC | LV | 74¢ | 57¢ | 1 | ❌ | −$29.36 |
| 2026-09-20 | KC | IND | 72¢ | 56¢ | 4 | ✅ | +$21.13 |
| 2026-09-27 | BUF | LAC | 76¢ | 60¢ | 1 | ✅ | +$19.16 |
| 2026-09-27 | SEA | WSH | 78¢ | 62¢ | 1 | ❌ | −$31.83 |
| 2026-10-04 | BUF | NE | 74¢ | 57¢ | 1 | ❌ | −$29.36 |
| 2026-10-08 | DAL | TB | 80¢ | 64¢ | 3 | ❌ | −$32.81 |
| 2026-10-11 | JAX | PHI | 76¢ | 54¢ | 2 | ✅ | +$22.13 |
| 2026-10-18 | IND | TEN | 72¢ | 35¢ | 4 | ❌ | −$18.30 |
| 2026-10-18 | LAR | ARI | 86¢ | 71¢ | 2 | ❌ | −$36.23 |
| 2026-10-25 | MIN | IND | 76¢ | 57¢ | 1 | ✅ | +$20.64 |
| 2026-10-25 | HOU | NYG | 80¢ | 64¢ | 1 | ❌ | −$32.81 |
| 2026-11-01 | CIN | TEN | 88¢ | 72¢ | 1 | ✅ | +$13.29 |
| 2026-11-01 | DAL | ARI | 76¢ | 9¢ | 4 | ❌ | −$4.79 |
| 2026-11-01 | LAR | LAC | 74¢ | 58¢ | 2 | ✅ | +$20.14 |
| 2026-11-01 | NE | MIA | 76¢ | 59¢ | 2 | ✅ | +$19.65 |
| 2026-11-08 | KC | NYJ | 80¢ | 55¢ | 2 | ✅ | +$21.63 |
| 2026-11-15 | SEA | LV | 72¢ | 57¢ | 1 | ✅ | +$20.64 |
