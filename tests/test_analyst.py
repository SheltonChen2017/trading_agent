"""
Sanity tests for signals/analyst.py. Run with:
python -m pytest tests/ -v (or `python tests/test_analyst.py`).

Uses hand-built `analyst_data` dicts (bypassing the network-dependent
data.analyst_data.fetch_analyst_actions(), same pattern as
test_pead.py/test_fundamentals.py) so the matching/threshold logic is
fully testable in isolation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from signals.analyst import scan_analyst_actions


def _price_series(dates: pd.DatetimeIndex) -> pd.DataFrame:
    days = len(dates)
    rng = np.random.default_rng(0)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.005, size=days))
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )


def test_flags_net_upgrade_as_up():
    dates = pd.bdate_range("2024-01-02", periods=60)
    price_df = _price_series(dates)
    event_date = dates[30]
    actions = pd.DataFrame(
        {"net_actions": [2], "n_actions": [2], "avg_price_target_change_pct": [10.0]}, index=[event_date]
    )

    result = scan_analyst_actions({"TEST": price_df}, {"TEST": actions}, as_of=event_date)
    assert not result.empty
    assert result.iloc[0]["direction"] == "up"
    assert result.iloc[0]["return_zscore"] == 2.0


def test_flags_net_downgrade_as_dip():
    dates = pd.bdate_range("2024-01-02", periods=60)
    price_df = _price_series(dates)
    event_date = dates[30]
    actions = pd.DataFrame(
        {"net_actions": [-1], "n_actions": [1], "avg_price_target_change_pct": [-8.0]}, index=[event_date]
    )

    result = scan_analyst_actions({"TEST": price_df}, {"TEST": actions}, as_of=event_date)
    assert not result.empty
    assert result.iloc[0]["direction"] == "dip"


def test_ignores_net_zero_actions():
    # e.g. one upgrade and one downgrade the same day -> nets to zero.
    dates = pd.bdate_range("2024-01-02", periods=60)
    price_df = _price_series(dates)
    event_date = dates[30]
    actions = pd.DataFrame(
        {"net_actions": [0], "n_actions": [2], "avg_price_target_change_pct": [1.0]}, index=[event_date]
    )

    result = scan_analyst_actions({"TEST": price_df}, {"TEST": actions}, as_of=event_date)
    assert result.empty


def test_respects_min_net_actions_threshold():
    dates = pd.bdate_range("2024-01-02", periods=60)
    price_df = _price_series(dates)
    event_date = dates[30]
    actions = pd.DataFrame(
        {"net_actions": [1], "n_actions": [1], "avg_price_target_change_pct": [5.0]}, index=[event_date]
    )

    result = scan_analyst_actions({"TEST": price_df}, {"TEST": actions}, as_of=event_date, min_net_actions=2)
    assert result.empty

    result2 = scan_analyst_actions({"TEST": price_df}, {"TEST": actions}, as_of=event_date, min_net_actions=1)
    assert not result2.empty


def test_weekend_spillover_fires_once():
    dates = pd.bdate_range("2024-01-02", periods=60)
    price_df = _price_series(dates)
    monday = next(d for d in dates[20:40] if d.day_name() == "Monday")
    saturday = monday - pd.Timedelta(days=2)
    actions = pd.DataFrame(
        {"net_actions": [3], "n_actions": [3], "avg_price_target_change_pct": [12.0]}, index=[saturday]
    )

    monday_result = scan_analyst_actions({"TEST": price_df}, {"TEST": actions}, as_of=monday)
    assert not monday_result.empty

    tuesday = dates[dates.get_loc(monday) + 1]
    tuesday_result = scan_analyst_actions({"TEST": price_df}, {"TEST": actions}, as_of=tuesday)
    assert tuesday_result.empty


def test_ticker_missing_from_analyst_data_is_skipped():
    dates = pd.bdate_range("2024-01-02", periods=60)
    price_df = _price_series(dates)
    result = scan_analyst_actions({"TEST": price_df}, analyst_data={}, as_of=dates[30])
    assert result.empty


def test_returns_empty_when_as_of_is_none():
    dates = pd.bdate_range("2024-01-02", periods=60)
    price_df = _price_series(dates)
    actions = pd.DataFrame({"net_actions": [2], "n_actions": [2], "avg_price_target_change_pct": [10.0]}, index=[dates[30]])
    result = scan_analyst_actions({"TEST": price_df}, {"TEST": actions}, as_of=None)
    assert result.empty


if __name__ == "__main__":
    test_flags_net_upgrade_as_up()
    test_flags_net_downgrade_as_dip()
    test_ignores_net_zero_actions()
    test_respects_min_net_actions_threshold()
    test_weekend_spillover_fires_once()
    test_ticker_missing_from_analyst_data_is_skipped()
    test_returns_empty_when_as_of_is_none()
    print("All analyst signal tests passed.")
