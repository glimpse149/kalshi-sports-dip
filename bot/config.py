"""All tunable settings in one place. Prices are in dollars (0.84 = 84 cents)."""

# --- Which games count -------------------------------------------------------
FAVORITE_MIN_PREGAME = 0.75   # team must open at 75c or higher to count as "the favorite"

# --- When to buy -------------------------------------------------------------
DIP_SIZE = 0.25               # buy once the favorite's ask is 25c+ below its pre-game price
MIN_ENTRY_PRICE = 0.05        # ignore prices under 5c (game basically over / junk quotes)
MAX_SPREAD = 0.06             # skip if bid/ask spread is wider than 6c (stale or thin book)
EARLY_MAX_PERIOD = 2          # "early" = 1st half (Q1-Q2): this is the strategy being tested
                              # dips in Q3+ are logged as a "late" control group for comparison

# --- Size and costs (paper) --------------------------------------------------
CONTRACTS = 10                # contracts per paper trade
TAKER_FEE_RATE = 0.07         # Kalshi taker fee: 0.07 x C x P x (1-P), rounded up to the cent
                              # paper fills assume we pay the ask (taker) -> conservative

# --- Loop timing -------------------------------------------------------------
POLL_SECONDS = 30
MAX_RUN_MINUTES = 345         # GitHub Actions jobs die at 6h; stop a bit before that

# --- Data sources (public, no keys needed) ----------------------------------
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_SERIES = "KXNBAGAME"
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
