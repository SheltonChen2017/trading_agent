"""
Low idiosyncratic-volatility signal.

Deliberately DIFFERENT information than this project's already-rejected
z-score/momentum/breakout/PEAD family (see memory: project_signal_findings.md
-- 7+ signals tested, 0 confirmed as a standalone strategy). Instead of a
stock's own raw price/volume behavior, this strips out broad market
movement first: regress each stock's daily return against a benchmark
(QQQ) over a trailing window, then measure the volatility of what's LEFT
OVER (the residual -- the part of the stock's return the market doesn't
explain). Published research (Ang, Hodrick, Xing, Zhang 2006, NBER, "The
Cross-Section of Volatility and Expected Returns") found stocks with high
idiosyncratic volatility subsequently earned LOWER average returns across
multiple markets -- motivation, not a guarantee this survives this
project's universe/costs/rigor bar.

PRE-REGISTERED before running against real data (do not re-tune after
seeing a result -- see config.py):
  - benchmark: QQQ (IDIO_VOL_BENCHMARK_TICKER)
  - lookback window: 90 trading days (IDIO_VOL_LOOKBACK_DAYS)
  - rebalance: monthly -- fires ONLY on the last trading day of each
    calendar month present in the benchmark's own index
  - ranking: bottom 20% of the universe by trailing residual volatility
    flagged "up" (the well-evidenced, expected-outperformance leg);
    top 20% flagged "dip" (expected underperformance, included for
    symmetry with every other signal in this project, not because it's
    the primary hypothesis)
  - hold period: ~1 month (21 trading days) forward (IDIO_VOL_HOLD_DAYS)

Same output column contract as every other signal in this project, so it
plugs into backtest/engine.py's full backtest/baseline/market/out-of-
sample/significance toolkit unchanged (pass scan_fn=partial(scan_idio_vol,
benchmark_df=...) to any of them, with hold_days=IDIO_VOL_HOLD_DAYS).
`return_zscore` is repurposed to hold the ticker's own trailing residual
volatility (not a z-score) -- kept in this column for pipeline
compatibility, same convention momentum.py already uses for its
cross-sectional z-score.
"""
from __future__ import annotations

import pandas as pd

from config import IDIO_VOL_BOTTOM_PCT, IDIO_VOL_LOOKBACK_DAYS, IDIO_VOL_TOP_PCT
from signals.calendar_utils import is_month_end_trading_day
from signals.residual_returns import compute_residual_returns

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def compute_residual_volatility(
    stock_close: pd.Series, benchmark_close: pd.Series, window: int = IDIO_VOL_LOOKBACK_DAYS
) -> pd.Series:
    """
    Rolling residual volatility of `stock_close` against `benchmark_close`:
    the rolling std of compute_residual_returns() (see signals/residual_returns.py)
    over the same `window` used to estimate beta. Returned series is
    indexed like a `.pct_change()` series (first value NaN); safe to read
    off any single date without look-ahead.
    """
    residuals = compute_residual_returns(stock_close, benchmark_close, beta_window=window)
    return residuals.rolling(window).std()


def scan_idio_vol(
    data: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    lookback_days: int = IDIO_VOL_LOOKBACK_DAYS,
    top_pct: float = IDIO_VOL_TOP_PCT,
    bottom_pct: float = IDIO_VOL_BOTTOM_PCT,
) -> pd.DataFrame:
    """
    Monthly-rebalance-only scan: returns empty on every date that isn't
    the last trading day of a calendar month (per `benchmark_df`'s own
    index). On a rebalance date, ranks every ticker in `data` by trailing
    residual volatility vs `benchmark_df` (see compute_residual_volatility())
    and flags the bottom `bottom_pct` (lowest vol) as "up", top `top_pct`
    (highest vol) as "dip".
    """
    if as_of is None or as_of not in benchmark_df.index:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    if not is_month_end_trading_day(benchmark_df.index, as_of):
        return pd.DataFrame(columns=RESULT_COLUMNS)

    residual_vols: dict[str, float] = {}
    as_of_close: dict[str, float] = {}
    for ticker, df in data.items():
        if as_of not in df.index:
            continue
        vol_series = compute_residual_volatility(df["close"], benchmark_df["close"], window=lookback_days)
        if as_of not in vol_series.index:
            continue
        vol = vol_series.loc[as_of]
        if pd.isna(vol):
            continue
        residual_vols[ticker] = float(vol)
        as_of_close[ticker] = float(df.loc[as_of, "close"])

    if len(residual_vols) < 5:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    ranked = pd.Series(residual_vols).sort_values()  # ascending: lowest residual vol first
    n_low = max(1, int(len(ranked) * bottom_pct))
    n_high = max(1, int(len(ranked) * top_pct))
    low_vol_tickers = set(ranked.index[:n_low])
    high_vol_tickers = set(ranked.index[-n_high:])

    rows = []
    for ticker in low_vol_tickers | high_vol_tickers:
        rows.append(
            {
                "ticker": ticker,
                "date": as_of,
                "close": round(as_of_close[ticker], 2),
                "return_pct": 0.0,
                "return_zscore": round(residual_vols[ticker], 4),
                "volume_zscore": float("nan"),
                "direction": "up" if ticker in low_vol_tickers else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)
