# kalshi-sports-dip

Paper-trading bot that tests one question on Kalshi NBA game markets:

> When a team priced **70¢+ before tip** falls behind **in the first half** and its price
> drops **15¢ or more**, is it now underpriced?

**Paper only.** It never places orders and needs no Kalshi API key. It reads public
Kalshi prices and ESPN live scores, logs simulated trades, and reports to the
*updates* Telegram bot.

## How it works

| Step | Rule |
|---|---|
| Pre-game | Records each team's last price before tip. Games already started when the bot came online are skipped. |
| Favorite | The team at 70¢+ at tip. |
| Early dip (the strategy) | In Q1–Q2, favorite's ask is 15¢+ below its pre-game price → paper-buy 50 contracts at the ask, with the Kalshi taker fee. |
| Late dip (control group) | Same rule in Q3+. Logged separately so you can compare. Research suggests late moves tend to keep going. |
| Filters | Skips prices under 5¢ and spreads wider than 6¢. One trade per game. |
| Exit | Held to the final buzzer: $1/contract if the team wins, $0 if not. |

Fills assume paying the ask (taker) plus the fee, so results are on the conservative side.
All thresholds live in `bot/config.py`.

Rule chosen from the backtest (Oct 20 – Nov 12, 2026, 174 games): early dips at
70¢/15¢ went 18/22 at an average 60¢ buy (+$216.81 at 50 contracts); late dips went 7/13 (−$35.00).
Small sample — the live paper run is the real test.

## Schedule (GitHub Actions)

- **live** — starts ~6:37pm ET daily, watches that night's games for up to ~5¾ hours,
  sends a Telegram alert on every paper buy and on every settled game.
- **settle** — ~7:13am ET, settles anything still open and sends the daily summary
  with all-time totals for early vs late dips.

State is committed back to the repo: `state/state.json` (bot memory) and
`data/trades.csv` (every closed paper trade).

## Setup

Add two repo secrets (Settings → Secrets and variables → Actions → New repository secret):

- `UPDATES_TELEGRAM_BOT_TOKEN` — the updates bot's token from @BotFather
- `UPDATES_TELEGRAM_CHAT_ID` — your chat ID with that bot

Then Actions → **settle + daily summary** → Run workflow, to confirm a message arrives.

## Run locally

```bash
pip install -r requirements.txt pytest
pytest -q                 # offline tests
python -m bot live        # watch tonight's games (prints alerts if Telegram isn't set)
python -m bot settle
```

## Known limits

- NBA only for now. College football needs a different ESPN feed and Kalshi series.
- Late West Coast games may end after the live run stops; the morning settle run catches them,
  but late-game (control) dips after ~12:20am ET are missed.
- GitHub's scheduler can start runs 5–20 minutes late.

## Weekly options check (separate from the Kalshi bot)

`options_watch/` sends a Monday ~10:47am ET message to the same *updates* Telegram bot
on the Robinhood option positions listed in `options_watch/positions.json`
(currently FSLY $20 Call Jan 15 and SKM $40 Call Dec 18): stock price and weekly change,
option value vs what was paid, breakeven, days left, and flags when the take-profit,
cut-loss or planned exit date is reached. Quotes come from Yahoo Finance.
Edit `positions.json` to change fill prices, contracts or add/remove trades.
Workflow: `.github/workflows/options-weekly.yml` (can also be run by hand from the Actions tab).
