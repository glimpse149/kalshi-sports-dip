# kalshi-sports-dip

Paper-trading bot that tests one question on Kalshi NBA game markets:

> When a team priced **75¢+ before tip** falls behind **in the first half** and its price
> drops **25¢ or more**, is it now underpriced?

**Paper only.** It never places orders and needs no Kalshi API key. It reads public
Kalshi prices and ESPN live scores, logs simulated trades, and reports to the
*updates* Telegram bot.

## How it works

| Step | Rule |
|---|---|
| Pre-game | Records each team's last price before tip. Games already started when the bot came online are skipped. |
| Favorite | The team at 75¢+ at tip. |
| Early dip (the strategy) | In Q1–Q2, favorite's ask is 25¢+ below its pre-game price → paper-buy 10 contracts at the ask, with the Kalshi taker fee. |
| Late dip (control group) | Same rule in Q3+. Logged separately so you can compare. Research suggests late moves tend to keep going. |
| Filters | Skips prices under 5¢ and spreads wider than 6¢. One trade per game. |
| Exit | Held to the final buzzer: $1/contract if the team wins, $0 if not. |

Fills assume paying the ask (taker) plus the fee, so results are on the conservative side.
All thresholds live in `bot/config.py`.

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
