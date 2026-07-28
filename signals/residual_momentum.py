"""
Residual momentum signal.

Standard 12-1 month cross-sectional momentum was already tested and
REJECTED in this project (signals/momentum.py -- see memory:
project_signal_findings.md: significant under a naive row-level
bootstrap, but the "significance" evaporated under by-date and by-block
resampling, and the direction sign-flipped between periods -- three
independent statistical traps caught on that one signal alone).

Residual momentum is a deliberately narrow, "one final momentum-family
test" (per the source recommendation): instead of ranking stocks by their
RAW trailing return, first regress each stock's daily return against a
broad benchmark (QQQ) to strip out market-wide movement, then rank by the
CUMULATIVE RESIDUAL return over the classic 12-1 formation window
(months t-12 to t-1, skipping the most recent month). Published research
(residual momentum literature) reports this reduces the unstable factor
exposures embedded in conventional momentum -- motivation, not a
guarantee this survives this project's universe/costs/rigor bar.

Shares its rolling-beta/residual machinery with signals/idio_vol.py (see
signals/residual_returns.py) -- same regression, different summary
statistic (cumulative return here, volatility there) and a different
ranking mechanic (cross-sectional, like signals/momentum.py, not a
time-series regime split).

PRE-REGISTERED before running against real data (do not re-tune after
seeing a result -- see config.py):
  - benchmark: QQQ (RESIDUAL_MOMENTUM_BENCHMARK_TICKER)
  - formation window: ~11 months (231 trading days), ALSO used as the
    rolling beta-estimation window (RESIDUAL_MOMENTUM_BETA_WINDOW_DAYS)
  - skip: ~1 month (21 trading days) immediately before `as_of`
    (RESIDUAL_MOMENTUM_SKIP_DAYS) -- the classic "12-1" construction
  - rebalance: monthly
  - ranking: top/bottom 20% of the universe by cumulative residual return
    over the formation window
  - direction: top residual-momentum quintile = "up" (continuation
    expected, the well-evidenced leg, matching signals/momentum.py's own
    convention); bottom quintile = "dip" (included for symmetry only)
  - hold period: ~1 month (21 trading days) forward (RESIDUAL_MOMENTUM_HOLD_DAYS)

Same output column contract as every other signal, so it plugs into
backtest/engine.py's full toolkit unchanged. `return_zscore` is
repurposed to hold the cumulative residual return over the formation
window (a percentage, not a z-score) -- same convention idio_vol.py and
momentum.py already use for a non-zscore numeric feature.
"""
from __future__ import annotations

import pandas as pd

from config import (
    RESIDUAL_MOMENTUM_BETA_WINDOW_DAYS,
    RESIDUAL_MOMENTUM_BOTTOM_PCT,
    RESIDUAL_MOMENTUM_SKIP_DAYS,
    RESIDUAL_MOMENTUM_TOP_PCT,
)
from signals.residual_returns import compute_residual_returns

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def _is_month_end(date_index: pd.DatetimeIndex, as_of: pd.Timestamp) -> bool:
    idx = date_index.get_loc(as_of)
    if idx == len(date_index) - 1:
        return True
    return date_index[idx + 1].month != as_of.month


def scan_residual_momentum(
    data: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    beta_window: int = RESIDUAL_MOMENTUM_BETA_WINDOW_DAYS,
    skip_days: int = RESIDUAL_MOMENTUM_SKIP_DAYS,
    top_pct: float = RESIDUAL_MOMENTUM_TOP_PCT,
    bottom_pct: float = RESIDUAL_MOMENTUM_BOTTOM_PCT,
) -> pd.DataFrame:
    """
    Monthly-rebalance-only scan: returns empty on every date that isn't
    the last trading day of a calendar month (per `benchmark_df`'s own
    index). On a rebalance date, ranks every ticker in `data` by
    cumulative residual return (vs `benchmark_df`) over the formation
    window ending `skip_days` before `as_of`, and flags the top `top_pct`
    as "up", bottom `bottom_pct` as "dip".
    """
    empty = pd.DataFrame(columns=RESULT_COLUMNS)
    if as_of is None or as_of not in benchmark_df.index:
        return empty
    if not _is_month_end(benchmark_df.index, as_of):
        return empty

    residual_momentum: dict[str, float] = {}
    as_of_close: dict[str, float] = {}
    for ticker, df in data.items():
        if as_of not in df.index:
            continue
        residuals = compute_residual_returns(df["close"], benchmark_df["close"], beta_window=beta_window)
        if as_of not in residuals.index:
            continue
        idx = residuals.index.get_loc(as_of)
        end_idx = idx - skip_days
        start_idx = end_idx - beta_window
        if start_idx < 0:
            continue
        window_residuals = residuals.iloc[start_idx:end_idx]
        if window_residuals.empty or window_residuals.isna().any():
            continue

        cumulative_return_pct = float((1.0 + window_residuals).prod() - 1.0) * 100
        residual_momentum[ticker] = cumulative_return_pct
        as_of_close[ticker] = float(df.loc[as_of, "close"])

    if len(residual_momentum) < 5:
        return empty

    ranked = pd.Series(residual_momentum).sort_values(ascending=False)  # descending: best residual momentum first
    n_top = max(1, int(len(ranked) * top_pct))
    n_bottom = max(1, int(len(ranked) * bottom_pct))
    top_tickers = set(ranked.index[:n_top])
    bottom_tickers = set(ranked.index[-n_bottom:])

    rows = []
    for ticker in top_tickers | bottom_tickers:
        rows.append(
            {
                "ticker": ticker,
                "date": as_of,
                "close": round(as_of_close[ticker], 2),
                "return_pct": round(residual_momentum[ticker], 2),
                "return_zscore": round(residual_momentum[ticker], 2),
                "volume_zscore": float("nan"),
                "direction": "up" if ticker in top_tickers else "dip",
            }
        )

    if not rows:
        return empty
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)
