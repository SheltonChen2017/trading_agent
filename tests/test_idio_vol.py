"""
Sanity tests for signals/idio_vol.py. Run with: python -m pytest tests/ -v
(or `python tests/test_idio_vol.py` for a quick manual check).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.idio_vol import compute_residual_volatility, scan_idio_vol


def _series_from_returns(returns: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    close = 100 * np.cumprod(1 + returns)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(len(returns), 1_000_000.0)},
        index=dates,
    )


def _benchmark_and_universe(days: int = 200, seed: int = 0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    benchmark_returns = rng.normal(0.0003, 0.008, size=days)
    benchmark_df = _series_from_returns(benchmark_returns, dates)

    # LOW_VOL: near-perfectly tracks the benchmark (beta=1, tiny noise) -> low residual vol.
    # HIGH_VOL: benchmark plus large idiosyncratic noise -> high residual vol.
    low_vol_returns_1 = benchmark_returns + rng.normal(0, 0.0005, size=days)
    low_vol_returns_2 = benchmark_returns + rng.normal(0, 0.0005, size=days)
    high_vol_returns_1 = benchmark_returns + rng.normal(0, 0.03, size=days)
    high_vol_returns_2 = benchmark_returns + rng.normal(0, 0.03, size=days)
    mid_returns_1 = benchmark_returns + rng.normal(0, 0.005, size=days)
    mid_returns_2 = benchmark_returns + rng.normal(0, 0.005, size=days)

    data = {
        "LOW1": _series_from_returns(low_vol_returns_1, dates),
        "LOW2": _series_from_returns(low_vol_returns_2, dates),
        "MID1": _series_from_returns(mid_returns_1, dates),
        "MID2": _series_from_returns(mid_returns_2, dates),
        "HIGH1": _series_from_returns(high_vol_returns_1, dates),
        "HIGH2": _series_from_returns(high_vol_returns_2, dates),
    }
    return benchmark_df, data


def _last_month_end(date_index: pd.DatetimeIndex, min_idx: int) -> pd.Timestamp:
    for i in range(len(date_index) - 1, min_idx, -1):
        if i == len(date_index) - 1 or date_index[i + 1].month != date_index[i].month:
            return date_index[i]
    raise AssertionError("no month-end date found")


def test_compute_residual_volatility_ranks_low_vs_high_correctly():
    benchmark_df, data = _benchmark_and_universe()
    low_vol = compute_residual_volatility(data["LOW1"]["close"], benchmark_df["close"], window=90)
    high_vol = compute_residual_volatility(data["HIGH1"]["close"], benchmark_df["close"], window=90)
    as_of = benchmark_df.index[-1]
    assert low_vol.loc[as_of] < high_vol.loc[as_of]


def test_scan_idio_vol_flags_low_vol_as_up_and_high_vol_as_dip():
    benchmark_df, data = _benchmark_and_universe()
    as_of = _last_month_end(benchmark_df.index, min_idx=90)

    result = scan_idio_vol(data, benchmark_df, as_of=as_of, lookback_days=90, top_pct=1 / 3, bottom_pct=1 / 3)
    assert not result.empty
    up_tickers = set(result.loc[result["direction"] == "up", "ticker"])
    dip_tickers = set(result.loc[result["direction"] == "dip", "ticker"])
    assert up_tickers == {"LOW1", "LOW2"}
    assert dip_tickers == {"HIGH1", "HIGH2"}


def test_scan_idio_vol_only_fires_on_month_end():
    benchmark_df, data = _benchmark_and_universe()
    as_of = _last_month_end(benchmark_df.index, min_idx=90)
    idx = benchmark_df.index.get_loc(as_of)
    if idx > 0:
        non_month_end = benchmark_df.index[idx - 1]
        result = scan_idio_vol(data, benchmark_df, as_of=non_month_end, lookback_days=90)
        assert result.empty


def test_scan_idio_vol_returns_empty_with_insufficient_history():
    benchmark_df, data = _benchmark_and_universe(days=50)  # shorter than default 90-day window
    as_of = benchmark_df.index[-1]
    result = scan_idio_vol(data, benchmark_df, as_of=as_of, lookback_days=90)
    assert result.empty


def test_scan_idio_vol_returns_empty_with_too_few_tickers():
    benchmark_df, data = _benchmark_and_universe()
    as_of = _last_month_end(benchmark_df.index, min_idx=90)
    tiny_data = {"LOW1": data["LOW1"], "HIGH1": data["HIGH1"]}
    result = scan_idio_vol(tiny_data, benchmark_df, as_of=as_of, lookback_days=90)
    assert result.empty  # fewer than 5 tickers -- not enough for a meaningful cross-sectional rank


def test_scan_idio_vol_returns_empty_when_as_of_is_none_or_missing():
    benchmark_df, data = _benchmark_and_universe()
    assert scan_idio_vol(data, benchmark_df, as_of=None).empty
    missing_date = pd.Timestamp("1999-01-01")
    assert scan_idio_vol(data, benchmark_df, as_of=missing_date).empty


if __name__ == "__main__":
    test_compute_residual_volatility_ranks_low_vs_high_correctly()
    test_scan_idio_vol_flags_low_vol_as_up_and_high_vol_as_dip()
    test_scan_idio_vol_only_fires_on_month_end()
    test_scan_idio_vol_returns_empty_with_insufficient_history()
    test_scan_idio_vol_returns_empty_with_too_few_tickers()
    test_scan_idio_vol_returns_empty_when_as_of_is_none_or_missing()
    print("All idio_vol tests passed.")
