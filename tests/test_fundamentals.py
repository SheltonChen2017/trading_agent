"""
Sanity tests for signals/fundamentals.py. Run with:
python -m pytest tests/ -v (or `python tests/test_fundamentals.py`).

Uses hand-built `earnings_data` dicts (bypassing the network-dependent
data.earnings_data.fetch_earnings_history(), same pattern as
test_pead.py) so the YoY-growth/matching logic is fully testable in
isolation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.fundamentals import scan_fundamentals


def _price_series(dates: pd.DatetimeIndex) -> pd.DataFrame:
    days = len(dates)
    rng = np.random.default_rng(0)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.005, size=days))
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )


def _five_quarterly_dates(anchor: pd.Timestamp) -> list[pd.Timestamp]:
    """Five report dates ~1 quarter apart, ending at `anchor` — enough for
    exactly one YoY comparison (anchor vs. 4 quarters before it)."""
    return [anchor - pd.DateOffset(months=3 * i) for i in range(4, -1, -1)]


def test_flags_strong_yoy_eps_growth_as_up():
    dates = pd.bdate_range("2023-01-02", periods=900)
    price_df = _price_series(dates)
    anchor = dates[800]
    report_dates = _five_quarterly_dates(anchor)
    # EPS doubled YoY: 1.00 -> 2.00 -> well above the default 20% threshold.
    eps = [1.00, 1.05, 1.10, 1.15, 2.00]
    earnings = {"TEST": pd.DataFrame({"reported_eps": eps}, index=pd.DatetimeIndex(report_dates))}

    result = scan_fundamentals({"TEST": price_df}, earnings, as_of=anchor)
    assert not result.empty
    assert result.iloc[0]["direction"] == "up"
    assert result.iloc[0]["return_zscore"] > 20.0


def test_flags_strong_yoy_eps_decline_as_dip():
    dates = pd.bdate_range("2023-01-02", periods=900)
    price_df = _price_series(dates)
    anchor = dates[800]
    report_dates = _five_quarterly_dates(anchor)
    eps = [2.00, 1.80, 1.60, 1.40, 0.50]  # sharp YoY decline
    earnings = {"TEST": pd.DataFrame({"reported_eps": eps}, index=pd.DatetimeIndex(report_dates))}

    result = scan_fundamentals({"TEST": price_df}, earnings, as_of=anchor)
    assert not result.empty
    assert result.iloc[0]["direction"] == "dip"


def test_ignores_growth_below_threshold():
    dates = pd.bdate_range("2023-01-02", periods=900)
    price_df = _price_series(dates)
    anchor = dates[800]
    report_dates = _five_quarterly_dates(anchor)
    eps = [1.00, 1.02, 1.04, 1.06, 1.08]  # ~8% YoY growth, below default 20% threshold
    earnings = {"TEST": pd.DataFrame({"reported_eps": eps}, index=pd.DatetimeIndex(report_dates))}

    result = scan_fundamentals({"TEST": price_df}, earnings, as_of=anchor)
    assert result.empty


def test_returns_empty_without_four_prior_quarters():
    dates = pd.bdate_range("2023-01-02", periods=900)
    price_df = _price_series(dates)
    anchor = dates[800]
    # Only 2 reports total -- not enough for a YoY (4-quarters-back) comparison.
    report_dates = [anchor - pd.DateOffset(months=3), anchor]
    earnings = {"TEST": pd.DataFrame({"reported_eps": [1.0, 2.0]}, index=pd.DatetimeIndex(report_dates))}

    result = scan_fundamentals({"TEST": price_df}, earnings, as_of=anchor)
    assert result.empty


def test_ticker_missing_from_earnings_data_is_skipped():
    dates = pd.bdate_range("2023-01-02", periods=60)
    price_df = _price_series(dates)
    result = scan_fundamentals({"TEST": price_df}, earnings_data={}, as_of=dates[30])
    assert result.empty


def test_returns_empty_when_as_of_is_none():
    dates = pd.bdate_range("2023-01-02", periods=900)
    price_df = _price_series(dates)
    anchor = dates[800]
    report_dates = _five_quarterly_dates(anchor)
    earnings = {"TEST": pd.DataFrame({"reported_eps": [1, 1, 1, 1, 2]}, index=pd.DatetimeIndex(report_dates))}
    result = scan_fundamentals({"TEST": price_df}, earnings, as_of=None)
    assert result.empty


if __name__ == "__main__":
    test_flags_strong_yoy_eps_growth_as_up()
    test_flags_strong_yoy_eps_decline_as_dip()
    test_ignores_growth_below_threshold()
    test_returns_empty_without_four_prior_quarters()
    test_ticker_missing_from_earnings_data_is_skipped()
    test_returns_empty_when_as_of_is_none()
    print("All fundamentals tests passed.")
