"""
Sanity tests for signals/residual_momentum.py. Run with:
python -m pytest tests/ -v (or `python tests/test_residual_momentum.py`
for a quick manual check).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.calendar_utils import is_month_end_trading_day
from signals.residual_momentum import scan_residual_momentum

BETA_WINDOW = 50  # small, for fast/manageable tests -- production default is 231
SKIP_DAYS = 10    # small, for fast/manageable tests -- production default is 21


def _series_from_returns(returns: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    close = 100 * np.cumprod(1 + returns)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(len(returns), 1_000_000.0)},
        index=dates,
    )


def _benchmark_and_universe(days: int = 150, seed: int = 0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    benchmark_returns = rng.normal(0.0003, 0.005, size=days)
    benchmark_df = _series_from_returns(benchmark_returns, dates)

    # Six tickers with distinct, deterministic EXCESS (over-benchmark)
    # drift, plus small noise -- residual return should track the excess
    # drift closely (beta ~= 1 since noise is small relative to drift).
    drifts = {"WINNER1": 0.003, "WINNER2": 0.002, "MID1": 0.0002, "MID2": -0.0002, "LOSER1": -0.002, "LOSER2": -0.003}
    data = {}
    for ticker, drift in drifts.items():
        stock_returns = benchmark_returns + drift + rng.normal(0, 0.0003, size=days)
        data[ticker] = _series_from_returns(stock_returns, dates)
    return benchmark_df, data


def _last_month_end(date_index: pd.DatetimeIndex, min_idx: int) -> pd.Timestamp:
    # Uses the REAL NYSE-calendar check (signals.calendar_utils.
    # is_month_end_trading_day), matching the fix in scan_residual_
    # momentum() itself (GPT review, 2026-07-31) -- a helper duplicating
    # the old "last row, or next row is a different month" logic would
    # validate the fixed code against a date only the OLD, buggy
    # definition would call month-end.
    for i in range(len(date_index) - 1, min_idx, -1):
        if is_month_end_trading_day(date_index, date_index[i]):
            return date_index[i]
    raise AssertionError("no month-end date found")


def test_scan_residual_momentum_flags_top_and_bottom_by_residual_not_raw_return():
    benchmark_df, data = _benchmark_and_universe()
    as_of = _last_month_end(benchmark_df.index, min_idx=BETA_WINDOW + SKIP_DAYS + 5)

    result = scan_residual_momentum(
        data, benchmark_df, as_of=as_of, beta_window=BETA_WINDOW, skip_days=SKIP_DAYS, top_pct=1 / 6, bottom_pct=1 / 6,
    )
    assert not result.empty
    up_tickers = set(result.loc[result["direction"] == "up", "ticker"])
    dip_tickers = set(result.loc[result["direction"] == "dip", "ticker"])
    assert up_tickers == {"WINNER1"}
    assert dip_tickers == {"LOSER2"}


def test_scan_residual_momentum_only_fires_on_month_end():
    benchmark_df, data = _benchmark_and_universe()
    as_of = _last_month_end(benchmark_df.index, min_idx=BETA_WINDOW + SKIP_DAYS + 5)
    idx = benchmark_df.index.get_loc(as_of)
    if idx > 0:
        non_month_end = benchmark_df.index[idx - 1]
        result = scan_residual_momentum(data, benchmark_df, as_of=non_month_end, beta_window=BETA_WINDOW, skip_days=SKIP_DAYS)
        assert result.empty


def test_scan_residual_momentum_returns_empty_with_insufficient_history():
    benchmark_df, data = _benchmark_and_universe(days=30)
    as_of = benchmark_df.index[-1]
    result = scan_residual_momentum(data, benchmark_df, as_of=as_of, beta_window=BETA_WINDOW, skip_days=SKIP_DAYS)
    assert result.empty


def test_scan_residual_momentum_returns_empty_with_too_few_tickers():
    benchmark_df, data = _benchmark_and_universe()
    as_of = _last_month_end(benchmark_df.index, min_idx=BETA_WINDOW + SKIP_DAYS + 5)
    tiny_data = {"WINNER1": data["WINNER1"], "LOSER2": data["LOSER2"]}
    result = scan_residual_momentum(tiny_data, benchmark_df, as_of=as_of, beta_window=BETA_WINDOW, skip_days=SKIP_DAYS)
    assert result.empty


def test_scan_residual_momentum_returns_empty_when_as_of_is_none_or_missing():
    benchmark_df, data = _benchmark_and_universe()
    assert scan_residual_momentum(data, benchmark_df, as_of=None).empty
    missing_date = pd.Timestamp("1999-01-01")
    assert scan_residual_momentum(data, benchmark_df, as_of=missing_date).empty


if __name__ == "__main__":
    test_scan_residual_momentum_flags_top_and_bottom_by_residual_not_raw_return()
    test_scan_residual_momentum_only_fires_on_month_end()
    test_scan_residual_momentum_returns_empty_with_insufficient_history()
    test_scan_residual_momentum_returns_empty_with_too_few_tickers()
    test_scan_residual_momentum_returns_empty_when_as_of_is_none_or_missing()
    print("All residual_momentum tests passed.")
