"""
Shared rolling residual-return computation: regress a stock's daily
return against a benchmark's, using a backward-looking rolling beta, and
return what's LEFT OVER (the part of the return the benchmark doesn't
explain). Used by both signals/idio_vol.py (residual VOLATILITY) and
signals/residual_momentum.py (cumulative residual RETURN) -- factored out
here so both signals share one implementation instead of drifting apart.
"""
from __future__ import annotations

import pandas as pd


def compute_residual_returns(stock_close: pd.Series, benchmark_close: pd.Series, beta_window: int) -> pd.Series:
    """
    Rolling residual daily returns of `stock_close` against `benchmark_close`.
    Beta is estimated with a rolling (trailing-window) cov/var over
    `beta_window` -- entirely backward-looking, so every value is safe to
    read off without look-ahead. Returned series is indexed like a
    `.pct_change()` series (first value NaN).
    """
    stock_returns = stock_close.pct_change()
    benchmark_returns = benchmark_close.pct_change()
    aligned_stock, aligned_bench = stock_returns.align(benchmark_returns, join="inner")

    rolling_cov = aligned_stock.rolling(beta_window).cov(aligned_bench)
    rolling_var = aligned_bench.rolling(beta_window).var()
    beta = rolling_cov / rolling_var
    return aligned_stock - beta * aligned_bench
