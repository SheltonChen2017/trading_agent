"""
Central configuration for the trading agent.
Keep every tunable knob here so scanner/backtest/live code all read
from one source of truth instead of hardcoding values in three places.
"""

# --- Universe -----------------------------------------------------------
# Widened from the original 10-name starter set to ~40 large-cap, liquid
# names spread across sectors (tech, consumer, healthcare, financials,
# energy/industrials, communication, utilities). More names -> more
# flagged signals -> less noise in the backtest's win-rate/return stats.
UNIVERSE = [
    # Original starter set
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "JPM", "XOM",
    # Tech
    "ORCL", "CRM", "ADBE", "INTC", "CSCO", "IBM", "QCOM", "TXN",
    # Consumer discretionary/staples
    "KO", "PEP", "WMT", "COST", "NKE", "MCD", "SBUX", "HD",
    # Healthcare
    "JNJ", "PFE", "UNH", "LLY", "ABBV",
    # Financials
    "BAC", "WFC", "GS", "V", "MA",
    # Energy / industrials
    "CVX", "BA", "CAT",
    # Communication
    "DIS", "NFLX",
    # Utilities (low-volatility contrast to the rest of the universe)
    "DUK", "NEE",
    # Rare earth minerals / critical materials (thin sector — few large,
    # liquid, US-listed pure plays exist)
    "MP", "REMX",
    # Fintech (V/MA also live in "financials" — deliberate overlap)
    "PYPL", "XYZ",
    # Confirmed by user 2026-07: SpaceX's real, current ticker post-IPO
    "SPCX",
]

# Reference benchmarks — NOT part of UNIVERSE, never scanned for dip/up
# signals. Used only to check whether a basket's signals beat the broad
# market over the exact same days, a stricter bar than beating just the
# stock's own history (see backtest/engine.compare_signal_to_market_index).
MARKET_BENCHMARK_TICKERS = ["SPY", "QQQ"]  # S&P 500 / Nasdaq-100 ETFs

# --- Data -----------------------------------------------------------
# ~2 trading years, so the backtest has real depth (previously 252 days /
# ~1 year) and comfortably reaches back before mid-2025.
LOOKBACK_DAYS = 504
ROLLING_WINDOW = 20          # window for rolling mean/std used in z-scores

# --- Baskets -----------------------------------------------------------
# Overlapping themed groupings of UNIVERSE tickers — a stock can (and often
# should) appear in more than one basket, e.g. TSLA is both a consumer/auto
# name and an AI-narrative name. These are curated by known sector/theme,
# NOT trained on anything — see baskets.py for the one basket that's
# computed empirically instead (HIGH_VOLATILITY_BASKET_SIZE below).
#
# Per-basket ML model training is intentionally NOT built yet: splitting
# the universe into smaller groups shrinks an already-thin per-signal
# sample size (see backtest results — ~48% model accuracy pooled across
# all 43 tickers). Basket-level backtest/baseline stats are useful now;
# training a separate model per basket should wait until there's enough
# real signal per basket to trust the result.
BASKETS = {
    # User-requested categories
    "tech": [
        "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "AMD", "INTC",
        "QCOM", "TXN", "ORCL", "CRM", "ADBE", "CSCO", "IBM", "NFLX",
    ],
    "semiconductors": ["NVDA", "AMD", "INTC", "QCOM", "TXN"],
    "ai_related": ["NVDA", "MSFT", "GOOGL", "META", "AMD", "ORCL", "CRM", "TSLA", "SPCX"],
    "unstable": ["TSLA", "SPCX"],  # curated per user's own examples; cross-check against
                                    # baskets.compute_high_volatility_basket(), which is
                                    # computed from real realized volatility, not picked by hand
    "rare_earth_minerals": ["MP", "REMX"],
    "fintech": ["V", "MA", "PYPL", "XYZ"],
    # Original sector groupings, kept for the broader universe backtests
    "mega_cap_tech": ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA"],
    "software": ["MSFT", "ORCL", "CRM", "ADBE", "IBM"],
    "consumer_staples": ["KO", "PEP", "WMT", "COST"],
    "consumer_discretionary": ["AMZN", "NKE", "MCD", "SBUX", "HD", "TSLA", "DIS", "NFLX"],
    "healthcare": ["JNJ", "PFE", "UNH", "LLY", "ABBV"],
    "financials": ["JPM", "BAC", "WFC", "GS", "V", "MA"],
    "energy": ["XOM", "CVX"],
    "industrials": ["BA", "CAT"],
    "communication_media": ["DIS", "NFLX", "GOOGL", "META"],
    "utilities": ["DUK", "NEE"],
}

# Size of the "high_volatility" basket, computed empirically from realized
# daily-return std over the lookback window (see baskets.py) rather than a
# hand-picked list — an objective stand-in for what the user called an
# "unstable" basket.
HIGH_VOLATILITY_BASKET_SIZE = 8

# --- Signal thresholds -----------------------------------------------------------
# A z-score of 2.0 means "2 standard deviations from its own recent norm" —
# roughly the top/bottom ~2.5% of daily moves for that specific stock.
RETURN_Z_THRESHOLD = 2.0
VOLUME_Z_THRESHOLD = 1.5     # require above-average volume to filter out noise

# --- Backtest -----------------------------------------------------------
BACKTEST_HOLD_DAYS = 5        # trading days to hold a flagged signal before measuring outcome
SLIPPAGE_PCT = 0.0015         # simulated round-trip cost (entry+exit slippage/spread), subtracted from returns

# Hold periods (in trading days) swept by run_multi_horizon_backtest() so a
# signal's apparent edge (or lack of it) can be checked across several exit
# timings instead of trusting one arbitrarily chosen BACKTEST_HOLD_DAYS.
HORIZON_SWEEP_DAYS = [1, 3, 5, 10, 21]   # ~1 day, 3 days, 1 week, 2 weeks, 1 month
HORIZON_LABELS = {1: "1 day", 3: "3 days", 5: "1 week", 10: "2 weeks", 21: "1 month"}

# --- ML model -----------------------------------------------------------
MODEL_PATH = "ml/model.joblib"   # where the trained classifier is persisted
MIN_WIN_PROBABILITY = 0.5        # signals scored below this by the model are not sized/traded

# --- Risk (used by the risk manager / backtester) -----------------------------------------------------------
MAX_POSITION_PCT = 0.05      # never risk more than 5% of capital on one name
STOP_LOSS_PCT = 0.03         # exit if a position moves 3% against you
MAX_TOTAL_EXPOSURE_PCT = 0.50  # never have more than 50% of capital deployed across all open positions at once
INITIAL_CAPITAL = 100_000     # default account equity used by backtest/demo sizing when no live account is connected

# --- Execution -----------------------------------------------------------
PAPER_TRADING = True         # hard default — flip only after you mean it
# Alpaca credentials are read from the APCA_API_KEY_ID / APCA_API_SECRET_KEY
# environment variables (see execution/alpaca_broker.py) — never hardcode
# API keys in this file.
