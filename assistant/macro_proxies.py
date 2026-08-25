"""Assistant-private descriptive macro proxy calculations.

The strategy-research product owns the research-facing implementations in
``data.macro_data``.  The assistant uses these behavior-identical private
calculations only to describe observed macro context.  They do not produce a
forecast, trade direction, proposal, approval, position size, or execution
decision.
"""
from __future__ import annotations

import pandas as pd


def _as_ohlcv(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 0.0},
        index=close.index,
    )


def build_credit_spread_proxy(
    hy_df: pd.DataFrame,
    ig_df: pd.DataFrame,
) -> pd.DataFrame:
    """Return the descriptive LQD/HYG stress proxy on overlapping dates."""
    dates = hy_df.index.intersection(ig_df.index).sort_values()
    ratio = ig_df["close"].reindex(dates) / hy_df["close"].reindex(dates)
    return _as_ohlcv(ratio)


def build_yield_curve_proxy(
    short_df: pd.DataFrame,
    long_df: pd.DataFrame,
) -> pd.DataFrame:
    """Return the descriptive short-minus-long yield proxy."""
    dates = short_df.index.intersection(long_df.index).sort_values()
    slope = short_df["close"].reindex(dates) - long_df["close"].reindex(dates)
    return _as_ohlcv(slope)


__all__ = ["build_credit_spread_proxy", "build_yield_curve_proxy"]
