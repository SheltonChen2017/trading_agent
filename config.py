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
#
# SURVIVORSHIP BIAS -- READ BEFORE INTERPRETING ANY BACKTEST FROM THIS LIST.
# These are companies that exist TODAY. Anything that was delisted, acquired,
# or went to zero inside a backtest window is structurally absent, so every
# result computed over this universe is conditioned on survival. Confirmed
# concretely: SIVB, SBNY and FRC all failed inside this project's own lookback
# window and none of them are here; SBNY's ticker was later reused by an
# unrelated listing, so it would not even be a clean stand-in. Comparing a
# signal to the same ticker's baseline may reduce some market-level distortion,
# but it does NOT remove selection bias: failed companies can have
# systematically different signals and downside tails. Absolute return figures
# are especially likely to be optimistic. Treat the magnitude as unknown until
# the research is rerun against a point-in-time constituent/delistings dataset.
#
# Before adding a ticker, verify it against real data (fetch_historical +
# yf.Ticker(t).info) rather than assuming the symbol is right --
# fetch_historical SILENTLY SKIPS tickers that return nothing, so a typo
# vanishes instead of failing. See .claude/skills/real-data-check.
# Checked 2026-07-30: SPCX (Space Exploration Technologies),
# FISV (Fiserv) and XYZ (Block, Inc.) resolve. A review
# flagged them as fabricated/renamed; that was wrong, and FI -- the symbol
# suggested as FISV's replacement -- is the one that 404s.
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

# Leveraged ETFs — used by assistant/context_builder.py to flag leveraged
# exposure as its own risk category (separate from plain sector/basket
# exposure, since a leveraged position carries daily-rebalancing decay
# risk a same-dollar unleveraged position doesn't). Not exhaustive —
# extend as needed.
LEVERAGED_ETF_TICKERS = [
    "TQQQ", "SQQQ", "QLD", "QID",           # Nasdaq-100 3x/2x, bull/bear
    "SOXL", "SOXS",                          # Semiconductors 3x
    "UPRO", "SPXU", "SSO", "SDS",            # S&P 500 3x/2x, bull/bear
    "TNA", "TZA",                             # Russell 2000 3x
    "NVDL",                                   # NVDA 2x bull (no inverse counterpart tracked here)
]

# Leveraged ETF -> its unleveraged same-index counterpart — used by
# assistant/risk_copilot.py to flag "hidden duplication" (e.g. holding
# both QQQ and TQQQ is really just a bigger, undiversified Nasdaq-100 bet,
# not two separate positions). Only mapped for pairs this project has
# actually researched (see project_leverage_rotation_strategy) — extend
# as needed rather than guessing at others.
LEVERAGED_ETF_UNDERLYING = {
    "TQQQ": "QQQ",
    "SQQQ": "QQQ",
    "QLD": "QQQ",
    "QID": "QQQ",
    "SOXL": "SOXX",
    "SOXS": "SOXX",
    "UPRO": "SPY",
    "SPXU": "SPY",
    "SSO": "SPY",
    "SDS": "SPY",
    "NVDL": "NVDA",
}

# Inverse (bear) leveraged ETFs among the tickers above -- these move
# OPPOSITE their underlying, so holding both, e.g., SPY and SPXU is a
# partial HEDGE, not a duplicated same-direction bet the way SPY+UPRO is.
# assistant/risk_copilot.py's find_correlated_clusters() excludes these
# from its "hidden duplication" warning (GPT review, 2026-07-28: SPXU was
# reproduced being described as "one amplified SPY bet," which is wrong
# in the opposite direction of what the warning claims).
INVERSE_LEVERAGED_ETF_TICKERS = {"SQQQ", "QID", "SOXS", "SPXU", "SDS", "TZA"}

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
# NOTE: this governs the scanner/backtest pipeline only. The rotation and
# vol-target research scripts under scripts/ deliberately hardcode their own
# LOOKBACK_DAYS = 4200 (~16 years) because each is a frozen, self-contained
# experiment whose window is part of its recorded result -- reading this
# value instead would silently re-scope a completed experiment. Do not
# "consolidate" them into this constant; change one only by writing a new
# experiment.
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
# ONE-WAY (per-leg) slippage/spread cost, as a fraction (0.0015 = 0.15%).
# Applied once entering and once exiting -- ~2x this for a full round trip.
# backtest/engine.py applies it as `raw_return_pct - 2 * SLIPPAGE_PCT * 100`
# (a percentage-point subtraction); backtest/portfolio_simulator.py applies
# it as a per-leg price haircut, `price * (1 +/- SLIPPAGE_PCT)`. Both
# treat the constant as one-way/per-leg -- see tests/test_slippage_parity.py
# for a regression guard against the two drifting apart again (a prior
# version's comment here called this a "round-trip cost", which read as
# contradicting the *2 in engine.py; Codex review, 2026-07-27).
SLIPPAGE_PCT = 0.0015

# Hold periods (in trading days) swept by run_multi_horizon_backtest() so a
# signal's apparent edge (or lack of it) can be checked across several exit
# timings instead of trusting one arbitrarily chosen BACKTEST_HOLD_DAYS.
HORIZON_SWEEP_DAYS = [1, 3, 5, 10, 21]   # ~1 day, 3 days, 1 week, 2 weeks, 1 month
HORIZON_LABELS = {1: "1 day", 3: "3 days", 5: "1 week", 10: "2 weeks", 21: "1 month"}

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

# Analyst PRICE TARGET consensus signal (signals/analyst_target.py,
# data/price_target_data.py) — genuinely different from the rating-
# direction signal above: uses the actual DOLLAR price targets analysts
# publish, aggregated into a point-in-time trimmed consensus (drop the
# highest and lowest active target, then mean/median the rest), and
# flags a stock when its current price diverges meaningfully from that
# consensus. User-proposed signal, 2026-07.
ANALYST_TARGET_GAP_THRESHOLD_PCT = 15.0  # |consensus - price| / price beyond this fires a signal
ANALYST_TARGET_MIN_ANALYSTS = 5          # minimum still-active price targets required to trust the trimmed mean/median
ANALYST_TARGET_STALENESS_DAYS = 365      # a firm's price target older than this is treated as no longer representing their current view
ANALYST_TARGET_METHOD = "median"         # "median" or "mean" of the trimmed set

# Cross-asset MACRO signals (signals/vix_spike.py, signals/credit_spread.py,
# signals/yield_curve.py; data/macro_data.py) — genuinely different data
# category from every other signal in this project: market-wide
# conditions (volatility, credit risk appetite, rate expectations), not
# any ticker's own price/volume/fundamentals/analyst data. All three
# share the same mechanism: build a "fear proxy" series constructed so
# that a RISE always means increasing macro stress, then flag the ENTIRE
# universe simultaneously when that proxy's own daily return z-score
# spikes beyond a threshold ("dip" = stress spike, expect a broad bounce)
# or collapses ("up" = stress easing sharply, included for symmetry).
# User-directed, 2026-07.
VIX_TICKER = "^VIX"
VIX_SPIKE_Z_THRESHOLD = 2.0

CREDIT_SPREAD_HY_TICKER = "HYG"   # iShares high-yield corporate bond ETF
CREDIT_SPREAD_IG_TICKER = "LQD"   # iShares investment-grade corporate bond ETF
CREDIT_SPREAD_Z_THRESHOLD = 2.0   # proxy = LQD/HYG ratio (rises when high-yield underperforms -- "flight to quality")

# Yield curve slope proxy: short (^IRX, 13-week T-bill) vs long (^TNX,
# 10-year) -- the same short/long pairing the NY Fed's own recession-
# probability model uses, chosen because a direct 2-year yield ticker
# isn't reliably available via this project's free data source.
YIELD_CURVE_SHORT_TICKER = "^IRX"
YIELD_CURVE_LONG_TICKER = "^TNX"
YIELD_CURVE_Z_THRESHOLD = 2.0      # proxy = short - long (rises as the curve flattens/inverts further)

# --- Defensive-carry research probe (docs/MANDATE.md, 2026-07-28) ------
# Candidate holdings for a defensive-carry sleeve. Deliberately NOT part
# of UNIVERSE/BASKETS -- the dip/up z-score scanner's mean-reversion/
# momentum hypothesis doesn't map onto bond/gold ETF behavior the way it
# does onto individual equities, and UNIVERSE membership implies "scanned
# for signals" (see MARKET_BENCHMARK_TICKERS above for the same
# not-scanned convention). Verified 2026-07-28 via the real-data-check
# skill: all four resolve via fetch_historical, are confirmed real/liquid
# ETFs via yf.Ticker().info (TLT/IEF/SHY = iShares Treasury ETFs, GLD =
# SPDR Gold Shares -- large AUM, real daily volume), and have 1763-1764
# of LOOKBACK_DAYS=1764 trading days of history (no underfill concern).
# Exploratory probe only -- see scripts/run_defensive_carry_probe.py and
# the corresponding `exploratory`-status entry in research_findings.json.
# Presence in this list is NOT an allocation authorization.
DEFENSIVE_CARRY_TICKERS = ["TLT", "IEF", "SHY", "GLD"]

# --- Three-sleeve engine (docs/reference/THREE_SLEEVE_ENGINE_PLAN.md,
# --- owner-adopted 2026-08-09) ---------------------------------------
# The owner's stated allocation preference, recorded as data. These lists
# and thresholds are NOT validated research and NOT an allocation
# authorization (same convention as DEFENSIVE_CARRY_TICKERS above);
# membership only means "the sleeve report watches this name". Verified
# 2026-08-09 via fetch_historical: all names below resolve with a full
# 400/400 requested trading sessions of real history.
#
# Sleeve 1 -- dividend income. JEPI/JEPQ are diversified covered-call
# funds; NVDY is a SINGLE-STOCK synthetic covered-call ETF on NVDA and
# behaves nothing like the other two (NAV-erosion risk, one-issuer
# exposure). The report names that overlap explicitly -- see
# SINGLE_STOCK_INCOME_ETF_UNDERLYING below.
DIVIDEND_INCOME_TICKERS = ["JEPQ", "JEPI", "NVDY"]

# Sleeve 2 -- semiconductor/tech growth rotation, per-lot thresholds.
# Five researched semis/tech names plus one diversified semiconductor ETF
# anchor (owner delegated the list to recommended defaults, 2026-08-09).
GROWTH_ROTATION_TICKERS = ["NVDA", "AMD", "AVGO", "TSM", "MSFT", "SOXX"]

# Sleeve 3 -- dividend-income reinvestment destinations. MUST stay a
# subset of LEVERAGED_ETF_TICKERS so leveraged-exposure accounting and
# the max_leveraged_etf_pct policy cap automatically cover every name
# here (regression-tested; adding a non-leveraged name would silently
# exempt it from the cap's accounting).
DIVIDEND_REINVEST_TICKERS = ["NVDL", "SOXL", "TQQQ"]

# Income ETFs whose distributions derive from ONE issuer's stock.
# Disclosure mapping only -- deliberately NOT merged into
# LEVERAGED_ETF_UNDERLYING, because that map feeds leveraged-exposure
# policy accounting and NVDY is not a leveraged ETF; adding it there
# would change max_leveraged_etf_pct enforcement, which is a policy
# behavior change this config must not smuggle in.
SINGLE_STOCK_INCOME_ETF_UNDERLYING = {"NVDY": "NVDA"}

# Engine thresholds. Exact boundaries. REVISION 2, owner-adopted
# 2026-08-09 after a measured backtest rejected revision 1's +5% any-term
# full exit (3.29% modeled after-tax-proxy CAGR vs 48.14% buy-and-hold on the same six
# names over 7y -- the rule stranded 95-99% of days in cash; see the
# dated scripts/backtest_three_sleeve_* experiment scripts and the
# research_findings.json entry). The revised gain review:
#
# - fires only at or above +50.00% unrealized on the LOT'S OWN basis;
# - fires only once the lot is LONG-TERM (the tax mechanism made binding:
#   a scheduled sale can never realize a short-term gain); and
# - proposes trimming HALF the lot, never exiting it, so a winner keeps
#   running -- measured 26.33% vs 3.29% CAGR in that descriptive run, with
#   no short-term gains observed and threshold-insensitivity (+50 vs +100
#   within 0.1 CAGR point). Dividend-adjusted prices make the tax result a
#   proxy, not an accountant-grade after-tax return; see the dated scripts.
#
# Unchanged by revision 2:
# - dividend sleeve warns below 10.00% of total equity (low end of the
#   owner's 10-15% range: max_position_pct 5% means a 15% sleeve needs
#   all three names at cap with zero slack);
# - a lot at or below -10.00% crosses the decline-review threshold
#   (measured harmless-to-good across every variant);
# - per-LOT basis (cost_per_share), never average cost -- averaging down
#   creates a new lot with its own thresholds and leaves existing lots'
#   references untouched.
DIVIDEND_SLEEVE_FLOOR_PCT = 10.0
GROWTH_GAIN_REVIEW_THRESHOLD_PCT = 50.0
GROWTH_GAIN_REVIEW_REQUIRES_LONG_TERM = True
GROWTH_GAIN_REVIEW_TRIM_FRACTION = 0.5
GROWTH_DECLINE_REVIEW_THRESHOLD_PCT = -10.0

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

# Four additional signals (idiosyncratic volatility, variance risk
# premium, residual momentum, overnight-gap reversal) were tried here on
# external (ChatGPT) recommendation and rejected under this project's full
# rigor bar -- see assistant/research_findings.json and commit 8605f0e.
# Their config constants and implementations were removed 2026-07-28;
# git history retains both.

# --- Risk (default policy caps, enforced by risk/execution_gate.py) -----
MAX_POSITION_PCT = 0.05      # never risk more than 5% of capital on one name
MAX_TOTAL_EXPOSURE_PCT = 0.50  # never have more than 50% of capital deployed across all open positions at once

# --- Execution -----------------------------------------------------------
PAPER_TRADING = True         # hard default — flip only after you mean it
# Alpaca credentials are read from the APCA_API_KEY_ID / APCA_API_SECRET_KEY
# environment variables (see execution/alpaca_broker.py) — never hardcode
# API keys in this file.
