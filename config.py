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
    "MP", "REMX", "TMC", "UUUU", "LAC",
    # Fintech (V/MA also live in "financials" — deliberate overlap)
    "PYPL", "XYZ", "COIN", "SOFI", "AFRM", "INTU", "FISV",
    # Confirmed by user 2026-07: SpaceX's real, current ticker post-IPO
    "SPCX",
    # 2026-07 basket expansion — added to thicken thin baskets (previously
    # 2-6 tickers each) so per-basket backtest stats are less noise-prone.
    # Additional semiconductors
    "AVGO", "MU", "AMAT", "LRCX",
    # Additional AI-narrative / high-beta names
    "PLTR", "MSTR", "RIVN",
    # Additional software
    "NOW", "WDAY", "PANW", "SNOW",
    # Additional energy
    "COP", "SLB", "OXY", "PSX", "MPC",
    # Additional industrials
    "HON", "GE", "LMT", "UPS", "DE",
    # Additional utilities
    "SO", "D", "AEP", "EXC",
    # Additional communication/media
    "CMCSA", "T", "VZ", "WBD",
    # Additional consumer staples
    "PG", "CL", "MDLZ", "KHC",
    # Additional consumer discretionary
    "LOW", "TGT", "BKNG", "ABNB", "UBER",
    # Additional healthcare
    "MRK", "TMO", "ABT", "CVS", "BMY",
    # Additional financials
    "MS", "C", "AXP", "SCHW", "BLK",
]

# Reference benchmarks — NOT part of UNIVERSE, never scanned for dip/up
# signals. Used only to check whether a basket's signals beat the broad
# market over the exact same days, a stricter bar than beating just the
# stock's own history (see backtest/engine.compare_signal_to_market_index).
MARKET_BENCHMARK_TICKERS = ["SPY", "QQQ"]  # S&P 500 / Nasdaq-100 ETFs

# --- Data -----------------------------------------------------------
# ~7 trading years (2026-07 expansion from 504 days / ~2 years), so the
# backtest spans multiple market regimes (2020 COVID crash, 2022 bear
# market, 2023-2026 bull run) instead of one mostly-continuous stretch —
# every signal tested at 2 years failed out-of-sample validation, and a
# too-short/too-narrow window was a live hypothesis for why. Tickers with
# less real history (recent IPOs) are simply scored on however much they
# have — the pipeline already handles mismatched history lengths per
# ticker (see signals/scanner.py's as_of-in-index guard).
LOOKBACK_DAYS = 1764
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
        "AVGO", "MU", "AMAT", "LRCX", "PLTR", "NOW", "WDAY", "PANW", "SNOW",
    ],
    "semiconductors": ["NVDA", "AMD", "INTC", "QCOM", "TXN", "AVGO", "MU", "AMAT", "LRCX"],
    "ai_related": [
        "NVDA", "MSFT", "GOOGL", "META", "AMD", "ORCL", "CRM", "TSLA", "SPCX",
        "PLTR", "AMZN", "IBM",
    ],
    "unstable": ["TSLA", "SPCX", "PLTR", "COIN", "MSTR", "RIVN"],  # curated per user's own
                                    # examples; cross-check against
                                    # baskets.compute_high_volatility_basket(), which is
                                    # computed from real realized volatility, not picked by hand
    "rare_earth_minerals": ["MP", "REMX", "TMC", "UUUU", "LAC"],
    "fintech": ["V", "MA", "PYPL", "XYZ", "COIN", "SOFI", "AFRM", "INTU", "FISV"],
    # Original sector groupings, expanded alongside the user-requested ones
    "mega_cap_tech": ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "AVGO"],
    "software": ["MSFT", "ORCL", "CRM", "ADBE", "IBM", "NOW", "WDAY", "PANW", "SNOW"],
    "consumer_staples": ["KO", "PEP", "WMT", "COST", "PG", "CL", "MDLZ", "KHC"],
    "consumer_discretionary": [
        "AMZN", "NKE", "MCD", "SBUX", "HD", "TSLA", "DIS", "NFLX",
        "LOW", "TGT", "BKNG", "ABNB", "UBER",
    ],
    "healthcare": ["JNJ", "PFE", "UNH", "LLY", "ABBV", "MRK", "TMO", "ABT", "CVS", "BMY"],
    "financials": ["JPM", "BAC", "WFC", "GS", "V", "MA", "MS", "C", "AXP", "SCHW", "BLK"],
    "energy": ["XOM", "CVX", "COP", "SLB", "OXY", "PSX", "MPC"],
    "industrials": ["BA", "CAT", "HON", "GE", "LMT", "UPS", "DE"],
    "communication_media": ["DIS", "NFLX", "GOOGL", "META", "CMCSA", "T", "VZ", "WBD"],
    "utilities": ["DUK", "NEE", "SO", "D", "AEP", "EXC"],
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
# Trailing window (in trading days) used for the optional market-regime
# feature — "was the broad market trending up or down heading into this
# signal?" Purely backward-looking (as-of the signal's own date), so it's
# safe to use as a feature without introducing look-ahead bias.
REGIME_LOOKBACK_DAYS = 20

# --- Additional signals (2026-07 signal diversification) ----------------
# The original dip/up scanner (signals/scanner.py) didn't hold up under
# out-of-sample validation or corrected significance testing (see README).
# These four alternative signals plug into the same backtest/baseline/
# market/out-of-sample/significance toolkit via run_backtest()'s
# scan_fn/scan_kwargs — none of them are proven either; they're
# recommendations with better academic track records, still needing the
# same rigorous testing before being trusted.

# Cross-sectional momentum (signals/momentum.py) — rank the universe by
# trailing return, skipping the most recent month to avoid short-term
# reversal contamination (the classic "12-1 month" construction).
MOMENTUM_LOOKBACK_DAYS = 126   # ~6 trading months
MOMENTUM_SKIP_DAYS = 21        # skip the most recent ~month
MOMENTUM_TOP_PCT = 0.2         # long the top 20% by trailing momentum
MOMENTUM_BOTTOM_PCT = 0.2      # "dip" leg — NOT the well-evidenced half of the
                               # momentum trade (academically usually a short);
                               # included only for symmetry with dip/up structure

# Relative/cross-sectional dip-up scanner (signals/relative.py) — same-day
# return ranked against the WHOLE UNIVERSE that day, not vs. the stock's
# own history, so a market-wide move can't by itself flag everything.
RELATIVE_Z_THRESHOLD = 2.0

# 52-week high/low breakout (signals/breakout.py)
BREAKOUT_LOOKBACK_DAYS = 252   # ~52 weeks

# Post-earnings announcement drift (signals/pead.py) — see
# data/earnings_data.py for the real data-thinness limitation.
PEAD_SURPRISE_THRESHOLD_PCT = 5.0

# Fundamentals / earnings-growth signal (signals/fundamentals.py) — YoY
# reported EPS growth, computed point-in-time from actual earnings
# report dates (data/earnings_data.py), not today's live snapshot
# fundamentals (which have no history and would be look-ahead bias if
# applied to past dates). Event-driven, same data-thinness caveat as PEAD.
FUNDAMENTALS_GROWTH_THRESHOLD_PCT = 20.0  # YoY EPS growth/decline beyond this fires a signal

# Analyst rating-change signal (signals/analyst.py) — net upgrades minus
# downgrades from institutional analysts (data/analyst_data.py), a
# genuinely different data category: third-party OPINION, not the
# company's own numbers or the stock's own trading behavior.
ANALYST_MIN_NET_ACTIONS = 1  # net upgrade/downgrade excess required to fire a signal

# Market regime classifier (signals/regime.py) — momentum showed a real,
# statistically significant sign-flip between two multi-year eras of the
# ~7-year test window (2026-07 finding), consistent with the documented
# "momentum crashes" phenomenon (elevated market volatility -> momentum
# reversal risk). Trailing window for the market's own realized
# volatility; the high/low-vol THRESHOLD is deliberately not a fixed
# config constant — it's calibrated from discovery-period data only (see
# signals/regime.py's calibrate_threshold_from_discovery()) so the
# confirmation period's regime classification stays honestly
# out-of-sample.
REGIME_VOLATILITY_LOOKBACK_DAYS = 60

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
