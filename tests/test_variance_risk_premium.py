"""
Sanity tests for signals/variance_risk_premium.py. Run with:
python -m pytest tests/ -v (or `python tests/test_variance_risk_premium.py`
for a quick manual check).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.variance_risk_premium import compute_variance_risk_premium, scan_variance_risk_premium

DAYS = 600
PERCENTILE_WINDOW = 50  # small, for fast/manageable tests -- production default is 504


def _series_from_close(close: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(len(close), 1_000_000.0)},
        index=dates,
    )


def _quiet_benchmark_and_vix(days: int = DAYS, seed: int = 0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    # Tiny, near-constant realized volatility in the benchmark -- keeps
    # the realized-variance term small and stable, so VRP tracks VIX^2
    # almost directly and is easy to control for test purposes.
    benchmark_returns = rng.normal(0.0002, 0.001, size=days)
    benchmark_df = _series_from_close(100 * np.cumprod(1 + benchmark_returns), dates)

    vix_close = np.full(days, 15.0)  # moderate, constant baseline VIX level
    vix_df = _series_from_close(vix_close, dates)
    return benchmark_df, vix_df, dates


def _last_month_end(date_index: pd.DatetimeIndex, min_idx: int, max_idx: int | None = None) -> pd.Timestamp:
    upper = max_idx if max_idx is not None else len(date_index) - 1
    for i in range(upper, min_idx, -1):
        if i == len(date_index) - 1 or date_index[i + 1].month != date_index[i].month:
            return date_index[i]
    raise AssertionError("no month-end date found in range")


def test_compute_variance_risk_premium_higher_when_vix_is_higher():
    benchmark_df, vix_df, dates = _quiet_benchmark_and_vix()
    low_vix_df = vix_df.copy()
    high_vix_df = vix_df.copy()
    high_vix_df["close"] = 40.0

    low_vrp = compute_variance_risk_premium(low_vix_df["close"], benchmark_df["close"])
    high_vrp = compute_variance_risk_premium(high_vix_df["close"], benchmark_df["close"])
    as_of = dates[-1]
    assert high_vrp.loc[as_of] > low_vrp.loc[as_of]


def test_scan_variance_risk_premium_flags_high_vrp_as_up():
    benchmark_df, vix_df, dates = _quiet_benchmark_and_vix()
    # Spike VIX (and therefore VRP) sharply higher right at the test date,
    # well above its own quiet trailing history.
    as_of = _last_month_end(dates, min_idx=PERCENTILE_WINDOW + 21 + 5)
    idx = dates.get_loc(as_of)
    vix_df.loc[dates[idx], "close"] = 60.0

    result = scan_variance_risk_premium(
        {"QQQ": benchmark_df}, vix_df, as_of=as_of, percentile_window=PERCENTILE_WINDOW,
    )
    assert not result.empty
    assert result.iloc[0]["direction"] == "up"


def test_scan_variance_risk_premium_flags_low_vrp_as_dip():
    benchmark_df, vix_df, dates = _quiet_benchmark_and_vix()
    as_of = _last_month_end(dates, min_idx=PERCENTILE_WINDOW + 21 + 5)
    idx = dates.get_loc(as_of)
    vix_df.loc[dates[idx], "close"] = 2.0  # sharply lower than the quiet baseline

    result = scan_variance_risk_premium(
        {"QQQ": benchmark_df}, vix_df, as_of=as_of, percentile_window=PERCENTILE_WINDOW,
    )
    assert not result.empty
    assert result.iloc[0]["direction"] == "dip"


def test_scan_variance_risk_premium_middle_band_produces_no_signal():
    benchmark_df, vix_df, dates = _quiet_benchmark_and_vix()
    as_of = _last_month_end(dates, min_idx=PERCENTILE_WINDOW + 21 + 5)
    # VIX unchanged from its quiet constant baseline -- current VRP should
    # sit in the middle of its own trailing (also-constant) history.
    result = scan_variance_risk_premium(
        {"QQQ": benchmark_df}, vix_df, as_of=as_of, percentile_window=PERCENTILE_WINDOW,
    )
    assert result.empty


def test_scan_variance_risk_premium_only_fires_on_month_end():
    benchmark_df, vix_df, dates = _quiet_benchmark_and_vix()
    as_of = _last_month_end(dates, min_idx=PERCENTILE_WINDOW + 21 + 5)
    idx = dates.get_loc(as_of)
    vix_df.loc[dates[idx], "close"] = 60.0
    if idx > 0:
        non_month_end = dates[idx - 1]
        result = scan_variance_risk_premium(
            {"QQQ": benchmark_df}, vix_df, as_of=non_month_end, percentile_window=PERCENTILE_WINDOW,
        )
        assert result.empty


def test_scan_variance_risk_premium_rejects_multi_ticker_data():
    benchmark_df, vix_df, dates = _quiet_benchmark_and_vix()
    as_of = dates[-1]
    try:
        scan_variance_risk_premium({"QQQ": benchmark_df, "SPY": benchmark_df}, vix_df, as_of=as_of)
        assert False, "expected a multi-ticker data dict to be rejected"
    except ValueError:
        pass


def test_scan_variance_risk_premium_returns_empty_with_insufficient_history():
    benchmark_df, vix_df, dates = _quiet_benchmark_and_vix(days=30)
    as_of = dates[-1]
    result = scan_variance_risk_premium({"QQQ": benchmark_df}, vix_df, as_of=as_of, percentile_window=PERCENTILE_WINDOW)
    assert result.empty


if __name__ == "__main__":
    test_compute_variance_risk_premium_higher_when_vix_is_higher()
    test_scan_variance_risk_premium_flags_high_vrp_as_up()
    test_scan_variance_risk_premium_flags_low_vrp_as_dip()
    test_scan_variance_risk_premium_middle_band_produces_no_signal()
    test_scan_variance_risk_premium_only_fires_on_month_end()
    test_scan_variance_risk_premium_rejects_multi_ticker_data()
    test_scan_variance_risk_premium_returns_empty_with_insufficient_history()
    print("All variance_risk_premium tests passed.")
