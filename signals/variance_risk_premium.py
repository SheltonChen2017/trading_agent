"""
Variance-risk-premium regime signal.

Deliberately DIFFERENT information than this project's already-rejected
z-score/momentum/breakout/PEAD family (see memory: project_signal_findings.md).
variance_risk_premium ~= VIX^2 - annualized realized benchmark variance --
the gap between what options markets are pricing in (implied volatility)
and what the market actually realized recently. Federal Reserve research
found implied-minus-realized variance carries predictive information for
aggregate market returns, particularly at multi-month horizons --
motivation, not a guarantee this survives this project's universe/costs/
rigor bar.

This is a PORTFOLIO-EXPOSURE signal, not a stock-selection signal: it
tests whether the BENCHMARK itself (QQQ) does better after high-VRP
periods, so `scan_variance_risk_premium()` expects a single-ticker `data`
dict (the tradable benchmark), not a stock universe.

PRE-REGISTERED before running against real data (do not re-tune after
seeing a result -- see config.py):
  - benchmark: QQQ (VRP_BENCHMARK_TICKER)
  - realized-variance window: 21 trading days, matching VIX's own ~30-
    calendar-day implied horizon (VRP_REALIZED_VARIANCE_WINDOW_DAYS)
  - regime classification: today's VRP level ranked against its own
    TRAILING 504-trading-day (~2yr) history (VRP_PERCENTILE_WINDOW_DAYS),
    entirely backward-looking (today's own value is excluded from its
    own ranking baseline -- same self-contamination discipline as the
    fix applied to signals/scanner.py)
  - top/bottom tercile: VRP_TOP_PCT / VRP_BOTTOM_PCT (1/3 each)
  - rebalance: monthly
  - hold period: ~2 months (42 trading days) forward (VRP_HOLD_DAYS)

Same output column contract as every other signal, so it plugs into
backtest/engine.py's full toolkit unchanged. `return_zscore` is
repurposed to hold the raw VRP value (not a z-score) for inspection --
same convention idio_vol.py/momentum.py already use for a non-zscore
numeric feature.
"""
from __future__ import annotations

import pandas as pd

from config import (
    VRP_BOTTOM_PCT,
    VRP_PERCENTILE_WINDOW_DAYS,
    VRP_REALIZED_VARIANCE_WINDOW_DAYS,
    VRP_TOP_PCT,
)

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]

_TRADING_DAYS_PER_YEAR = 252


def compute_variance_risk_premium(
    vix_close: pd.Series, benchmark_close: pd.Series, realized_window: int = VRP_REALIZED_VARIANCE_WINDOW_DAYS
) -> pd.Series:
    """
    VIX^2 minus annualized realized variance of the benchmark's own daily
    returns over the trailing `realized_window`. VIX is already quoted as
    an annualized percentage (e.g. 20.5 = 20.5%), so VIX^2 is in
    "percentage-point-squared" units; the realized side is converted to
    match: fractional daily variance * 252 (annualize) * 100^2 (convert
    fractional-variance units to percentage-point-squared units).
    Entirely backward-looking (rolling window) -- safe to read off any
    single date without look-ahead.
    """
    aligned_vix, aligned_bench = vix_close.align(benchmark_close, join="inner")
    benchmark_returns = aligned_bench.pct_change()
    realized_daily_var = benchmark_returns.rolling(realized_window).var()
    annualized_realized_var_pct2 = realized_daily_var * _TRADING_DAYS_PER_YEAR * 100**2
    return aligned_vix**2 - annualized_realized_var_pct2


def _is_month_end(date_index: pd.DatetimeIndex, as_of: pd.Timestamp) -> bool:
    idx = date_index.get_loc(as_of)
    if idx == len(date_index) - 1:
        return True
    return date_index[idx + 1].month != as_of.month


def scan_variance_risk_premium(
    data: dict[str, pd.DataFrame],
    vix_df: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    realized_window: int = VRP_REALIZED_VARIANCE_WINDOW_DAYS,
    percentile_window: int = VRP_PERCENTILE_WINDOW_DAYS,
    top_pct: float = VRP_TOP_PCT,
    bottom_pct: float = VRP_BOTTOM_PCT,
) -> pd.DataFrame:
    """
    Expects `data` to contain exactly ONE ticker -- the tradable benchmark
    (e.g. {"QQQ": qqq_df}) -- since this is a portfolio-exposure signal,
    not stock selection. Monthly-rebalance-only: returns empty on every
    date that isn't the last trading day of a calendar month. On a
    rebalance date, ranks today's VRP level against its own trailing
    `percentile_window` of history (excluding today) and flags the top
    `top_pct` as "up" (high premium), bottom `bottom_pct` as "dip" (low/
    negative premium, symmetry only) -- the middle band produces no
    signal.
    """
    empty = pd.DataFrame(columns=RESULT_COLUMNS)
    if len(data) != 1:
        raise ValueError(
            "scan_variance_risk_premium expects a single-ticker `data` dict (the tradable "
            "benchmark, e.g. {'QQQ': qqq_df}) -- this is a portfolio-exposure signal, not "
            "stock-selection."
        )
    ticker, benchmark_df = next(iter(data.items()))

    if as_of is None or as_of not in benchmark_df.index:
        return empty
    if not _is_month_end(benchmark_df.index, as_of):
        return empty

    vrp_series = compute_variance_risk_premium(vix_df["close"], benchmark_df["close"], realized_window)
    if as_of not in vrp_series.index:
        return empty
    idx = vrp_series.index.get_loc(as_of)
    start_idx = idx - percentile_window
    if start_idx < 0:
        return empty

    current_vrp = vrp_series.iloc[idx]
    if pd.isna(current_vrp):
        return empty
    trailing_window = vrp_series.iloc[start_idx:idx].dropna()  # EXCLUDES as_of itself
    if len(trailing_window) < 20:
        return empty

    percentile_rank = (trailing_window < current_vrp).mean()
    if percentile_rank >= 1 - top_pct:
        direction = "up"
    elif percentile_rank <= bottom_pct:
        direction = "dip"
    else:
        return empty  # middle band -- no signal this month

    close = float(benchmark_df.loc[as_of, "close"])
    return pd.DataFrame(
        [
            {
                "ticker": ticker,
                "date": as_of,
                "close": round(close, 2),
                "return_pct": 0.0,
                "return_zscore": round(float(current_vrp), 2),
                "volume_zscore": float("nan"),
                "direction": direction,
            }
        ],
        columns=RESULT_COLUMNS,
    )
