"""Point-in-time market features (strategy doc section 6.2).

Every column here is computed with a rolling/trailing window ending AT
(and including) each row's own session -- "features may use that
session's finalized close but never the next session's open" (6.2). This
is a different rule than signals/scanner.py's `shift(1).rolling(...)`
z-score baseline: that shift exists specifically to keep a signal day's
OWN return out of the baseline describing what a NORMAL day looks like.
A plain rolling return/volatility/drawdown feature has no such
self-referential-baseline problem -- the current day's own close is
legitimately "known by the end of as_of_session" and belongs in the
window, exactly like signals/regime.py's `compute_trailing_market_volatility`
(`.iloc[start_idx : idx + 1]`, inclusive of `idx`).

Reuses existing, already-tested point-in-time primitives instead of
reimplementing subtly different equivalents: `market_analytics.classify_trend`
and `signals.regime.compute_trailing_market_volatility` (both purely
backward-looking by construction) for the market trend/vol-regime feature,
and `backtest.risk_metrics.max_drawdown_pct` for the rolling max-drawdown
feature.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from backtest.risk_metrics import max_drawdown_pct
from market_analytics import classify_trend
from signals.regime import compute_trailing_market_volatility

RETURN_WINDOWS: tuple[int, ...] = (1, 5, 20, 60, 126, 252)
RESIDUAL_RETURN_WINDOWS: tuple[int, ...] = (5, 20, 60)
MOVING_AVERAGE_WINDOWS: tuple[int, ...] = (20, 50, 200)
REALIZED_VOL_WINDOWS: tuple[int, ...] = (10, 20, 60)
DOWNSIDE_SEMIVOL_WINDOWS: tuple[int, ...] = (20, 60)
MAX_DRAWDOWN_WINDOWS: tuple[int, ...] = (60, 252)
BETA_CORRELATION_WINDOW = 60
DOLLAR_VOLUME_WINDOW = 20
VOLUME_RATIO_WINDOW = 20
OVERNIGHT_GAP_WINDOW = 20
REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


class FeatureError(ValueError):
    """Price data cannot support point-in-time feature construction."""


def _validate_ohlcv(df: pd.DataFrame, name: str) -> None:
    if df.empty:
        raise FeatureError(f"{name} is empty")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise FeatureError(f"{name} is missing required columns: {missing}")
    if not df.index.is_monotonic_increasing:
        raise FeatureError(f"{name} index is not sorted ascending")
    if df.index.has_duplicates:
        raise FeatureError(f"{name} index has duplicate sessions")


def _sanitize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Documented rule for zero/negative price and negative volume: treat
    as missing (NaN), never as a literal 0% return or 0 liquidity, so a
    data glitch cannot masquerade as a real observation. NaN propagates
    through the rolling windows below as "feature unavailable" for the
    sessions it touches, rather than crashing the whole computation over
    one bad row."""
    out = df.copy()
    for column in ("open", "high", "low", "close"):
        numeric = pd.to_numeric(out[column], errors="coerce")
        out[column] = numeric.where(numeric > 0)
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").where(out["volume"] >= 0)
    return out


def _downside_semivol_pct(daily_returns: pd.Series, window: int) -> pd.Series:
    downside = daily_returns.clip(upper=0.0)
    return (downside.pow(2).rolling(window).mean()).pow(0.5) * 100


def _rolling_max_drawdown_pct(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window).apply(
        lambda values: max_drawdown_pct(pd.Series(values)), raw=True
    )


def _rolling_beta_and_correlation(
    returns: pd.Series, benchmark_returns: pd.Series, window: int
) -> tuple[pd.Series, pd.Series]:
    aligned_benchmark = benchmark_returns.reindex(returns.index)
    covariance = returns.rolling(window).cov(aligned_benchmark)
    benchmark_variance = aligned_benchmark.rolling(window).var()
    beta = covariance / benchmark_variance.replace(0.0, np.nan)
    correlation = returns.rolling(window).corr(aligned_benchmark)
    return beta, correlation


def _sessions_since_last_earnings(
    index: pd.DatetimeIndex, earnings_dates: Sequence[str]
) -> pd.Series:
    """Trading-session count since the most recent earnings date <=
    as_of_session, using the ticker's own price-history session index --
    never a calendar-day count, and never a future earnings date (only
    dates already <= as_of are ever considered). 0 means the earnings date
    falls on (or the closest prior trading session to) as_of_session
    itself; NaN means no earnings date at or before as_of_session exists."""
    parsed_earnings = pd.DatetimeIndex(
        sorted(pd.Timestamp(d).normalize() for d in earnings_dates)
    )
    result = np.full(len(index), np.nan)
    if parsed_earnings.empty:
        return pd.Series(result, index=index)
    for position, session in enumerate(index):
        # count of earnings dates <= this session
        count_before = parsed_earnings.searchsorted(session, side="right")
        if count_before == 0:
            continue
        last_earnings_date = parsed_earnings[count_before - 1]
        # first session position at/after that earnings date
        earnings_session_position = index.searchsorted(last_earnings_date, side="left")
        result[position] = position - earnings_session_position
    return pd.Series(result, index=index)


def compute_point_in_time_features(
    ticker: str,
    price: pd.DataFrame,
    *,
    benchmarks: Mapping[str, pd.Series],
    market_benchmark: str = "QQQ",
    earnings_dates: Sequence[str] = (),
    context_series: Mapping[str, pd.Series] | None = None,
) -> pd.DataFrame:
    """One row per session in `price.index`, columns named per-feature.

    `benchmarks` must contain at least "QQQ" and "SOXX" (residual returns,
    6.2) plus whichever of "SPY"/"QQQ"/"SOXX" trailing beta/correlation is
    wanted, and `market_benchmark` (default "QQQ") for the trend/vol-regime
    classification. `context_series` is an optional mapping of already-
    fetched descriptive series (e.g. VIX level, the credit-spread and
    yield-curve proxies from data/macro_data.py) -- each is forward-filled
    onto `price.index` (never backward-filled, so a value is only ever
    carried from the past into a later gap, never from the future).
    """
    _validate_ohlcv(price, f"{ticker} price")
    for name, series in benchmarks.items():
        if series.empty:
            raise FeatureError(f"benchmark {name!r} is empty")
    if market_benchmark not in benchmarks:
        raise FeatureError(f"market_benchmark {market_benchmark!r} not in benchmarks")

    clean = _sanitize_ohlcv(price)
    close = clean["close"]
    daily_returns = close.pct_change()

    features: dict[str, pd.Series] = {}

    for window in RETURN_WINDOWS:
        features[f"return_{window}d_pct"] = close.pct_change(window) * 100

    benchmark_returns: dict[str, pd.Series] = {
        name: series.pct_change() for name, series in benchmarks.items()
    }
    for name in ("QQQ", "SOXX"):
        if name not in benchmarks:
            continue
        for window in RESIDUAL_RETURN_WINDOWS:
            own = close.pct_change(window) * 100
            bench = benchmarks[name].reindex(close.index).pct_change(window) * 100
            features[f"residual_return_{name.lower()}_{window}d_pct"] = own - bench

    for window in MOVING_AVERAGE_WINDOWS:
        sma = close.rolling(window).mean()
        features[f"distance_from_sma_{window}d_pct"] = (close / sma - 1.0) * 100

    for window in REALIZED_VOL_WINDOWS:
        features[f"realized_vol_{window}d_pct"] = daily_returns.rolling(window).std() * 100

    for window in DOWNSIDE_SEMIVOL_WINDOWS:
        features[f"downside_semivol_{window}d_pct"] = _downside_semivol_pct(daily_returns, window)

    for window in MAX_DRAWDOWN_WINDOWS:
        features[f"max_drawdown_{window}d_pct"] = _rolling_max_drawdown_pct(close, window)

    features[f"avg_dollar_volume_{DOLLAR_VOLUME_WINDOW}d"] = (
        close * clean["volume"]
    ).rolling(DOLLAR_VOLUME_WINDOW).mean()
    features[f"volume_ratio_{VOLUME_RATIO_WINDOW}d"] = clean["volume"] / clean[
        "volume"
    ].rolling(VOLUME_RATIO_WINDOW).mean()

    for name in ("SPY", "QQQ", "SOXX"):
        if name not in benchmarks:
            continue
        beta, correlation = _rolling_beta_and_correlation(
            daily_returns, benchmark_returns[name], BETA_CORRELATION_WINDOW
        )
        features[f"beta_{name.lower()}_{BETA_CORRELATION_WINDOW}d"] = beta
        features[f"correlation_{name.lower()}_{BETA_CORRELATION_WINDOW}d"] = correlation

    overnight_gap_pct = (clean["open"] / close.shift(1) - 1.0) * 100
    features[f"overnight_gap_mean_{OVERNIGHT_GAP_WINDOW}d_pct"] = overnight_gap_pct.rolling(
        OVERNIGHT_GAP_WINDOW
    ).mean()
    features[f"overnight_gap_std_{OVERNIGHT_GAP_WINDOW}d_pct"] = overnight_gap_pct.rolling(
        OVERNIGHT_GAP_WINDOW
    ).std()

    market_close = benchmarks[market_benchmark]
    market_df = pd.DataFrame({"close": market_close})
    market_trend: list[str | None] = []
    market_vol: list[float | None] = []
    for session in close.index:
        if session in market_close.index:
            market_trend.append(classify_trend(market_close, session, lookback_days=200))
            market_vol.append(compute_trailing_market_volatility(market_df, session))
        else:
            market_trend.append(None)
            market_vol.append(None)
    features["market_trend"] = pd.Series(market_trend, index=close.index)
    features["market_trailing_volatility_pct"] = pd.Series(market_vol, index=close.index)

    for name, series in (context_series or {}).items():
        aligned = series.reindex(close.index, method="ffill")
        features[f"context_{name}_level"] = aligned

    features["day_of_week"] = pd.Series(close.index.dayofweek, index=close.index)
    features["sessions_since_last_earnings"] = _sessions_since_last_earnings(
        close.index, earnings_dates
    )

    result = pd.DataFrame(features, index=close.index)
    result.insert(0, "ticker", ticker)
    result.insert(1, "as_of_session", [str(ts.date()) for ts in close.index])
    return result
