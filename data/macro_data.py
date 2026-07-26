"""
Builds macro "fear proxy" series for the cross-asset macro signals
(signals/vix_spike.py, signals/credit_spread.py, signals/yield_curve.py).

Each proxy is constructed so a RISE always means increasing macro
stress — keeps the sign convention identical across all three signals
(positive return z-score spike = "dip"/expect-bounce, negative = "up"),
even though the raw tickers underneath don't share that convention on
their own (e.g. HYG/LQD ratio DROPS under stress, not rises).

Returned DataFrames match the OHLCV shape signals/scanner.compute_features()
expects (only `close` is real; open/high/low mirror it and volume is 0),
so the exact same z-scoring machinery used for individual tickers works
unchanged on these synthetic macro series.
"""
from __future__ import annotations

import pandas as pd


def _as_ohlcv(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 0.0},
        index=close.index,
    )


def build_credit_spread_proxy(hy_df: pd.DataFrame, ig_df: pd.DataFrame) -> pd.DataFrame:
    """
    LQD (investment-grade) / HYG (high-yield) price ratio. RISES when
    high-yield bonds underperform investment-grade — a "flight to
    quality" that widens real credit spreads — so this proxy behaves
    like VIX: up = more stress.
    """
    dates = hy_df.index.intersection(ig_df.index).sort_values()
    ratio = ig_df["close"].reindex(dates) / hy_df["close"].reindex(dates)
    return _as_ohlcv(ratio)


def build_yield_curve_proxy(short_df: pd.DataFrame, long_df: pd.DataFrame) -> pd.DataFrame:
    """
    Short-term yield MINUS long-term yield (both already yield*10-scaled,
    as yfinance quotes ^IRX/^TNX — the scaling cancels out in a
    difference so it doesn't matter for z-scoring). RISES as the curve
    flattens/inverts further (short rates catching up to or exceeding
    long), the classic recession-fear signal — same "up = more stress"
    convention as the other two proxies.
    """
    dates = short_df.index.intersection(long_df.index).sort_values()
    slope = short_df["close"].reindex(dates) - long_df["close"].reindex(dates)
    return _as_ohlcv(slope)
