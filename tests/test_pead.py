"""
Sanity tests for signals/pead.py. Run with: python -m pytest tests/ -v
(or `python tests/test_pead.py` for a quick manual check).

Uses hand-built `earnings_data` dicts (bypassing the network-dependent
data.earnings_data.fetch_earnings_surprises(), same pattern as the rest
of this project not unit-testing yfinance calls directly) so the
matching/threshold logic is fully testable in isolation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.pead import scan_pead


def _price_series(dates: pd.DatetimeIndex) -> pd.DataFrame:
    days = len(dates)
    rng = np.random.default_rng(0)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.005, size=days))
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )


def test_flags_exact_day_surprise_above_threshold():
    dates = pd.bdate_range("2024-01-02", periods=60)  # a Tuesday
    price_df = _price_series(dates)
    earnings_date = dates[30]
    earnings = {"TEST": pd.DataFrame({"surprise_pct": [8.0]}, index=[earnings_date])}

    result = scan_pead({"TEST": price_df}, earnings, as_of=earnings_date)
    assert not result.empty
    assert result.iloc[0]["direction"] == "up"
    assert result.iloc[0]["return_zscore"] == 8.0


def test_ignores_surprise_below_threshold():
    dates = pd.bdate_range("2024-01-02", periods=60)
    price_df = _price_series(dates)
    earnings_date = dates[30]
    earnings = {"TEST": pd.DataFrame({"surprise_pct": [1.0]}, index=[earnings_date])}  # below default 5.0

    result = scan_pead({"TEST": price_df}, earnings, as_of=earnings_date)
    assert result.empty


def test_flags_negative_surprise_as_dip():
    dates = pd.bdate_range("2024-01-02", periods=60)
    price_df = _price_series(dates)
    earnings_date = dates[30]
    earnings = {"TEST": pd.DataFrame({"surprise_pct": [-9.0]}, index=[earnings_date])}

    result = scan_pead({"TEST": price_df}, earnings, as_of=earnings_date)
    assert not result.empty
    assert result.iloc[0]["direction"] == "dip"


def test_weekend_spillover_fires_once_on_first_trading_day_only():
    # Earnings effective_date falls on a Saturday -- should fire on the
    # following Monday (the first trading day at/after it), and NOT
    # again on Tuesday.
    dates = pd.bdate_range("2024-01-02", periods=60)  # Mon-Fri only
    price_df = _price_series(dates)

    monday = next(d for d in dates[20:40] if d.day_name() == "Monday")
    saturday = monday - pd.Timedelta(days=2)
    earnings = {"TEST": pd.DataFrame({"surprise_pct": [7.5]}, index=[saturday])}

    monday_result = scan_pead({"TEST": price_df}, earnings, as_of=monday)
    assert not monday_result.empty, "expected the Saturday event to fire on the following Monday"

    tuesday = dates[dates.get_loc(monday) + 1]
    tuesday_result = scan_pead({"TEST": price_df}, earnings, as_of=tuesday)
    assert tuesday_result.empty, "the same event shouldn't fire again on Tuesday"


def test_ticker_missing_from_earnings_data_is_skipped():
    dates = pd.bdate_range("2024-01-02", periods=60)
    price_df = _price_series(dates)
    result = scan_pead({"TEST": price_df}, earnings_data={}, as_of=dates[30])
    assert result.empty


def test_returns_empty_when_as_of_is_none():
    dates = pd.bdate_range("2024-01-02", periods=60)
    price_df = _price_series(dates)
    earnings = {"TEST": pd.DataFrame({"surprise_pct": [8.0]}, index=[dates[30]])}
    result = scan_pead({"TEST": price_df}, earnings, as_of=None)
    assert result.empty


if __name__ == "__main__":
    test_flags_exact_day_surprise_above_threshold()
    test_ignores_surprise_below_threshold()
    test_flags_negative_surprise_as_dip()
    test_weekend_spillover_fires_once_on_first_trading_day_only()
    test_ticker_missing_from_earnings_data_is_skipped()
    test_returns_empty_when_as_of_is_none()
    print("All PEAD tests passed.")
