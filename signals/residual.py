"""
Residual (idiosyncratic) return signals.

Both scanners here work off the same primitive: the part of a stock's
daily return that is NOT explained by the market. We regress the stock's
daily returns on a benchmark's (SPY) over a trailing window and keep the
residual — so a stock that fell 4% on a day the market fell 4% has a
residual near zero (it just went along for the ride), while a stock that
fell 4% on a flat market has a large negative residual (something
happened to THAT company).

Two different hypotheses are built on top of that primitive, and they
point in OPPOSITE directions on purpose:

  scan_residual_momentum()  — SLOW horizon. Cumulative residual return
      over ~6 months, skipping the most recent month (the classic 6-1
      construction, applied to residuals instead of raw returns). Bets
      that idiosyncratic winners keep winning. The academic claim is
      that residual momentum has higher risk-adjusted returns and
      smaller crashes than raw momentum, because it strips out the
      factor-timing exposure that makes raw momentum crash.

  scan_residual_reversal() — FAST horizon. A single day's residual
      z-score exceeding a threshold, confirmed by volume. Bets that a
      large ONE-DAY idiosyncratic move partially reverses over the next
      few days (temporary price pressure / liquidity demand).

These are not contradictory: momentum is measured over months and skips
the most recent month precisely to avoid the short-term reversal effect
that scan_residual_reversal() is trying to capture.

LOOK-AHEAD DISCIPLINE. Every quantity here is causal. The regression
coefficients at row t are estimated on a trailing window that is shifted
by one row, so a day's own return never contributes to the beta it is
then measured against — the same defect (and the same fix) as the
rolling mean/std shift in signals/scanner.py's compute_features(). The
residual series can therefore be precomputed over the full history and
read off by date without leaking the future; that is what
build_residual_frames() exists for, and it is a pure speed optimization
with no effect on which rows get flagged.

Both scanners emit the same column contract as scan_dips_and_ups()
(ticker, date, close, return_pct, return_zscore, volume_zscore,
direction), so they plug into every backtest/baseline/out-of-sample/
significance tool in backtest/engine.py unchanged.

DIRECTION SEMANTICS — read before interpreting a reversal backtest.
backtest/engine.py scores every flagged signal as "go long it"; shorting
is not modeled. For scan_residual_reversal() that means only the "dip"
leg actually tests the reversal hypothesis (a large NEGATIVE residual,
bought, betting it bounces). The "up" leg — a large POSITIVE residual —
is emitted for symmetry, but going LONG it tests continuation, i.e. the
OPPOSITE of the stated hypothesis; the reversal version of that leg
would be a short, which this project does not backtest. Read a negative
edge on the reversal "up" leg as weak support FOR reversal, not against
it.
"""
from __future__ import annotations

import pandas as pd

from config import ROLLING_WINDOW

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]

# Frozen defaults for the 2026-08-03 candidate test (see
# scripts/run_residual_signal_significance.py). The regression window is
# the midpoint of the 60-120 day range the idea was specified over,
# chosen BEFORE any result was observed so it cannot be tuned afterwards.
RESIDUAL_BETA_WINDOW = 90
RESIDUAL_MOMENTUM_LOOKBACK_DAYS = 126   # ~6 trading months of residuals
RESIDUAL_MOMENTUM_SKIP_DAYS = 21        # skip the most recent ~month
RESIDUAL_MOMENTUM_TOP_PCT = 0.2
RESIDUAL_MOMENTUM_BOTTOM_PCT = 0.2
RESIDUAL_REVERSAL_Z_THRESHOLD = 2.0
RESIDUAL_REVERSAL_VOLUME_Z_THRESHOLD = 1.0

# Minimum trailing residual volatility (daily, in return units) for a
# residual z-score to mean anything. A name that tracks the benchmark
# almost exactly — an index ETF, a second share class, the benchmark
# itself if it ever enters the universe — has a residual of roughly zero
# AND a residual std of roughly zero, so the z-score becomes
# floating-point-noise divided by floating-point-noise and explodes to
# absurd magnitudes on a stock with no idiosyncratic movement at all
# (observed: |z| = 13.7 on a series constructed to move one-for-one with
# the benchmark). 1e-6 is 0.0001% daily residual vol — orders of
# magnitude below any real stock, so this only ever rejects degenerate
# near-duplicates.
RESIDUAL_STD_FLOOR = 1e-6


def compute_residual_features(
    df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    beta_window: int = RESIDUAL_BETA_WINDOW,
    zscore_window: int = ROLLING_WINDOW,
    momentum_lookback_days: int = RESIDUAL_MOMENTUM_LOOKBACK_DAYS,
    momentum_skip_days: int = RESIDUAL_MOMENTUM_SKIP_DAYS,
) -> pd.DataFrame:
    """
    Add residual-return columns to one ticker's OHLCV frame, using only
    trailing data at every row.

    Columns added:
      market_return_pct      — the benchmark's return on the same date
      beta                   — trailing OLS slope vs the benchmark,
                               estimated on data STRICTLY BEFORE this row
      residual               — this row's return minus (alpha + beta*market):
                               the full OLS residual, i.e. the SURPRISE
                               relative to how this stock normally behaves
      market_adjusted_return — this row's return minus (beta*market), with
                               NO alpha subtracted: the stock's total
                               idiosyncratic return, drift included
      residual_zscore        — `residual` scored against its own trailing
                               mean/std, again excluding this row
      residual_momentum      — cumulative MARKET-ADJUSTED return over the
                               momentum lookback window, ending
                               `momentum_skip_days` ago
      volume_zscore          — same definition as scanner.compute_features()

    WHY MOMENTUM USES market_adjusted_return AND NOT residual. Summing
    full OLS residuals over a window LONGER than the estimation window
    measures almost nothing: the rolling alpha is refit every day on the
    trailing `beta_window` days, so any persistent idiosyncratic drift is
    absorbed into alpha and subtracted right back out of the residual. A
    stock grinding out a steady -0.15%/day of company-specific
    underperformance ends up with residuals centred near zero and no
    residual momentum at all — which is precisely backwards, since that
    steady underperformance is the signal. (Caught by
    test_residual_momentum_ranks_the_strongest_idiosyncratic_winner_top,
    which failed against the first implementation.) The idea as
    specified — fit over 60-120 days, accumulate over 126 — has this
    defect built in, because the estimation window is shorter than the
    accumulation window. Removing beta exposure while KEEPING the
    idiosyncratic drift is what residual momentum is supposed to mean, so
    `residual_momentum` accumulates `market_adjusted_return`.

    The one-day reversal signal is unaffected either way: its z-score
    subtracts a trailing mean, so whether alpha was already removed
    changes the level, not the standardized surprise.

    Rows whose date is missing from the benchmark are kept but carry NaN
    residuals; callers skip NaN rows rather than silently imputing, so a
    benchmark gap can never manufacture a signal.
    """
    if beta_window < 2:
        raise ValueError(f"beta_window must be at least 2, got {beta_window!r}.")
    if zscore_window < 2:
        raise ValueError(f"zscore_window must be at least 2, got {zscore_window!r}.")
    if momentum_lookback_days < 1:
        raise ValueError(f"momentum_lookback_days must be positive, got {momentum_lookback_days!r}.")
    if momentum_skip_days < 0:
        raise ValueError(f"momentum_skip_days must be non-negative, got {momentum_skip_days!r}.")

    out = df.copy()
    out["return_pct"] = out["close"].pct_change()

    # Align the benchmark onto this ticker's calendar. reindex (not a
    # join) so the ticker keeps all of its own rows; dates the benchmark
    # lacks become NaN and propagate to NaN residuals rather than
    # borrowing a neighbouring day's market move.
    market_return = benchmark_df["close"].pct_change().reindex(out.index)
    out["market_return_pct"] = market_return

    stock = out["return_pct"]
    # .shift(1) BEFORE rolling: every moment below is computed from rows
    # strictly earlier than the row it will be applied to, so today's
    # move never helps estimate the beta today is measured against.
    stock_prior = stock.shift(1)
    market_prior = market_return.shift(1)

    stock_mean = stock_prior.rolling(beta_window).mean()
    market_mean = market_prior.rolling(beta_window).mean()
    # Population moments (ddof=0) keep cov/var consistent with each other;
    # the ratio is what matters and any common ddof cancels.
    covariance = stock_prior.rolling(beta_window).cov(market_prior, ddof=0)
    market_variance = market_prior.rolling(beta_window).var(ddof=0)

    # A zero-variance market window (a frozen benchmark series) gives no
    # information about beta. Leave it NaN rather than dividing by zero
    # and producing an infinite beta that would swamp every residual.
    beta = covariance / market_variance.where(market_variance > 0)
    alpha = stock_mean - beta * market_mean

    out["beta"] = beta
    out["residual"] = stock - (alpha + beta * market_return)
    # Beta exposure removed, idiosyncratic drift retained — see the
    # docstring for why momentum must accumulate this and not `residual`.
    out["market_adjusted_return"] = stock - beta * market_return

    residual_prior = out["residual"].shift(1)
    residual_mean = residual_prior.rolling(zscore_window).mean()
    residual_std = residual_prior.rolling(zscore_window).std()
    out["residual_zscore"] = (
        (out["residual"] - residual_mean) / residual_std.where(residual_std > RESIDUAL_STD_FLOOR)
    )

    # Cumulative idiosyncratic return over the lookback window that ENDS
    # skip_days ago — the 6-1 construction. Summing daily market-adjusted
    # returns is the standard additive approximation for a cumulative
    # idiosyncratic return.
    out["residual_momentum"] = (
        out["market_adjusted_return"].rolling(momentum_lookback_days).sum().shift(momentum_skip_days)
    )

    # NOTE — deliberate divergence from scanner.compute_features(): a
    # zero-variance trailing window yields NaN here (via .where) rather
    # than the +/-inf that plain division produces there. An infinite
    # z-score silently passes every `>= threshold` gate, which is the
    # failure direction this project treats as unacceptable; NaN is
    # skipped by both scanners below. Real volume series never have zero
    # trailing variance, so this only bites on synthetic constant-volume
    # fixtures — where failing closed is the behaviour we want.
    vol_mean = out["volume"].shift(1).rolling(zscore_window).mean()
    vol_std = out["volume"].shift(1).rolling(zscore_window).std()
    out["volume_zscore"] = (out["volume"] - vol_mean) / vol_std.where(vol_std > 0)

    return out


def build_residual_frames(
    data: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame,
    **kwargs,
) -> dict[str, pd.DataFrame]:
    """
    Precompute compute_residual_features() once per ticker.

    Pure speed: the backtester calls a scan_fn once per historical date,
    and recomputing a 90-day rolling regression over full history on
    every one of those calls is what makes a naive implementation
    unusable on a multi-year universe. Because every column is causal,
    computing them over the whole history in advance flags exactly the
    same rows as computing them per date.
    """
    return {
        ticker: compute_residual_features(df, benchmark_df, **kwargs)
        for ticker, df in data.items()
    }


def _resolve_frames(
    data: dict[str, pd.DataFrame],
    residual_frames: dict[str, pd.DataFrame] | None,
    benchmark_df: pd.DataFrame | None,
) -> dict[str, pd.DataFrame]:
    if residual_frames is not None:
        return residual_frames
    if benchmark_df is None:
        raise ValueError(
            "Pass either residual_frames (precomputed, preferred for backtests) "
            "or benchmark_df (computed on the fly)."
        )
    return build_residual_frames(data, benchmark_df)


def scan_residual_momentum(
    data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    residual_frames: dict[str, pd.DataFrame] | None = None,
    benchmark_df: pd.DataFrame | None = None,
    top_pct: float = RESIDUAL_MOMENTUM_TOP_PCT,
    bottom_pct: float = RESIDUAL_MOMENTUM_BOTTOM_PCT,
) -> pd.DataFrame:
    """
    Rank the universe cross-sectionally by cumulative residual momentum
    and flag the top `top_pct` as "up", the bottom `bottom_pct` as "dip".

    `return_zscore` carries the CROSS-SECTIONAL z-score of residual
    momentum (this ticker vs the universe that day), matching how
    signals/momentum.py reports the same field — it is NOT a z-score
    against the ticker's own history. `volume_zscore` is NaN: like raw
    momentum, this signal is not gated on volume confirmation.
    """
    frames = _resolve_frames(data, residual_frames, benchmark_df)

    momentum_by_ticker: dict[str, float] = {}
    as_of_info: dict[str, tuple] = {}

    for ticker, features in frames.items():
        if as_of is not None:
            if as_of not in features.index:
                continue  # ticker didn't trade on this date (e.g. a later IPO)
            row = features.loc[as_of]
        else:
            row = features.iloc[-1]

        value = row["residual_momentum"]
        if pd.isna(value):
            continue  # not enough trailing residual history yet
        momentum_by_ticker[ticker] = float(value)
        as_of_info[ticker] = (row.name, float(row["close"]))

    # A cross-sectional rank needs a cross-section. Below this the
    # top/bottom "quintiles" degenerate into one or two names and the
    # z-score is meaningless.
    if len(momentum_by_ticker) < 5:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    values = pd.Series(momentum_by_ticker)
    mean, std = values.mean(), values.std()
    if std == 0 or pd.isna(std):
        return pd.DataFrame(columns=RESULT_COLUMNS)
    cross_sectional_z = (values - mean) / std

    n_top = max(1, int(len(values) * top_pct))
    n_bottom = max(1, int(len(values) * bottom_pct))
    ranked = values.sort_values(ascending=False)
    top_tickers = set(ranked.index[:n_top])
    bottom_tickers = set(ranked.index[-n_bottom:])
    # With a small cross-section the two ends can overlap; the top rank
    # wins so a ticker is never emitted twice with contradictory
    # directions.
    bottom_tickers -= top_tickers

    rows = []
    for ticker in top_tickers | bottom_tickers:
        date, close = as_of_info[ticker]
        rows.append(
            {
                "ticker": ticker,
                "date": date,
                "close": round(close, 2),
                "return_pct": round(momentum_by_ticker[ticker] * 100, 2),
                "return_zscore": round(float(cross_sectional_z[ticker]), 2),
                "volume_zscore": float("nan"),
                "direction": "up" if ticker in top_tickers else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def scan_residual_reversal(
    data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    residual_frames: dict[str, pd.DataFrame] | None = None,
    benchmark_df: pd.DataFrame | None = None,
    residual_z_threshold: float = RESIDUAL_REVERSAL_Z_THRESHOLD,
    volume_z_threshold: float = RESIDUAL_REVERSAL_VOLUME_Z_THRESHOLD,
) -> pd.DataFrame:
    """
    Flag single-day idiosyncratic moves: |residual z-score| above
    `residual_z_threshold`, confirmed by volume above
    `volume_z_threshold`.

    Direction follows the SIGN OF THE MOVE, not the direction of the bet:
    a large negative residual is "dip" and a large positive residual is
    "up", exactly like scan_dips_and_ups(). See the module docstring —
    because the backtester only ever goes long, only the "dip" leg tests
    the reversal hypothesis; the "up" leg tests continuation.
    """
    frames = _resolve_frames(data, residual_frames, benchmark_df)

    rows = []
    for ticker, features in frames.items():
        if as_of is not None:
            if as_of not in features.index:
                continue
            row = features.loc[as_of]
        else:
            row = features.iloc[-1]

        residual_z = row["residual_zscore"]
        volume_z = row["volume_zscore"]
        if pd.isna(residual_z) or pd.isna(volume_z):
            continue

        is_extreme = abs(residual_z) >= residual_z_threshold
        is_confirmed_by_volume = volume_z >= volume_z_threshold

        if is_extreme and is_confirmed_by_volume:
            rows.append(
                {
                    "ticker": ticker,
                    "date": row.name,
                    "close": round(float(row["close"]), 2),
                    "return_pct": round(float(row["residual"]) * 100, 2),
                    "return_zscore": round(float(residual_z), 2),
                    "volume_zscore": round(float(volume_z), 2),
                    "direction": "up" if residual_z > 0 else "dip",
                }
            )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
