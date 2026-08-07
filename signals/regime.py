"""
Market regime classification.

Built to test a specific finding (2026-07): momentum's edge showed a
real, statistically significant sign-flip between two multi-year eras of
the project's ~7-year test window (discovery: -0.15pp edge, p=0.000;
confirmation: +0.25pp edge, p=0.000 — both independently significant,
opposite signs). This matches the documented "momentum crashes"
phenomenon (Daniel & Moskowitz, 2016): momentum tends to perform
reasonably in steady trending markets but suffers sharp, real reversals
following periods of elevated market volatility (e.g. after a crash and
violent recovery).

`compute_trailing_market_volatility()` is purely backward-looking (only
ever uses data up to and including `as_of`), consistent with every other
feature in this project — safe to use without introducing look-ahead
bias.

The high/low-volatility THRESHOLD is deliberately not a fixed constant.
`calibrate_threshold_from_discovery()` fits it from the discovery
period's OWN volatility distribution only, so that when the same fixed
threshold is later applied to classify confirmation-period dates, the
confirmation period stays honestly out-of-sample — the threshold itself
was never tuned using confirmation data. This mirrors the same
discovery/confirmation discipline `backtest/engine.py`'s out-of-sample
functions already enforce for signal edges.
"""
from __future__ import annotations

import pandas as pd

from config import REGIME_VOLATILITY_LOOKBACK_DAYS


def compute_trailing_market_volatility(
    benchmark_df: pd.DataFrame, as_of: pd.Timestamp, lookback_days: int = REGIME_VOLATILITY_LOOKBACK_DAYS
) -> float | None:
    """
    The market benchmark's (e.g. SPY) own realized daily-return
    volatility (%, standard deviation) over the `lookback_days` trading
    days ending at (and including) `as_of`. Purely backward-looking.
    Returns None if `as_of` isn't in the benchmark's history or there
    isn't enough trailing history yet.
    """
    if as_of not in benchmark_df.index:
        return None
    idx = benchmark_df.index.get_loc(as_of)
    start_idx = idx - lookback_days
    if start_idx < 0:
        return None

    window = benchmark_df["close"].iloc[start_idx : idx + 1]
    daily_returns = window.pct_change().dropna()
    if len(daily_returns) < 2:
        return None
    return float(daily_returns.std() * 100)


def classify_regime(
    benchmark_df: pd.DataFrame,
    as_of: pd.Timestamp,
    threshold_pct: float,
    lookback_days: int = REGIME_VOLATILITY_LOOKBACK_DAYS,
) -> str | None:
    """
    "high_vol" if trailing market volatility exceeds `threshold_pct`,
    otherwise "low_vol". Returns None when volatility isn't computable
    (see compute_trailing_market_volatility()).
    """
    vol = compute_trailing_market_volatility(benchmark_df, as_of, lookback_days)
    if vol is None:
        return None
    return "high_vol" if vol > threshold_pct else "low_vol"


def calibrate_threshold_from_discovery(
    benchmark_df: pd.DataFrame,
    discovery_end_date: pd.Timestamp,
    lookback_days: int = REGIME_VOLATILITY_LOOKBACK_DAYS,
) -> float:
    """
    The median trailing volatility across every date in `benchmark_df` up
    to (and including) `discovery_end_date` — i.e. a high/low-vol
    threshold fit using ONLY the discovery period's own distribution.
    Apply the SAME fixed value to classify confirmation-period dates too,
    so confirmation's regime labels aren't tuned on confirmation data.

    Raises ValueError if there's no computable volatility in that range.
    """
    discovery_dates = benchmark_df.index[benchmark_df.index <= discovery_end_date]
    vols = [
        v
        for d in discovery_dates
        if (v := compute_trailing_market_volatility(benchmark_df, d, lookback_days)) is not None
    ]
    if not vols:
        raise ValueError("Not enough discovery-period history to calibrate a regime threshold.")
    return float(pd.Series(vols).median())
