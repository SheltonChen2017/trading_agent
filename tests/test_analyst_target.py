"""
Sanity tests for signals/analyst_target.py. Run with:
python tests/test_analyst_target.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

from data.price_target_data import PriceTargetContractError
from signals.analyst_target import scan_analyst_target_gap


def _price_df(close: float, days: int = 30) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp("2024-01-31"), periods=days)
    closes = np.full(days, close)
    return pd.DataFrame(
        {"open": closes, "high": closes * 1.001, "low": closes * 0.999, "close": closes, "volume": 1_000_000.0},
        index=dates,
    )


def _history(entries: list[tuple[str, float]]) -> pd.DataFrame:
    dates = pd.to_datetime([e[0] for e in entries])
    return pd.DataFrame(
        {"firm": [f"firm_{i}" for i in range(len(entries))], "price_target": [e[1] for e in entries]},
        index=pd.DatetimeIndex(dates, name="effective_session"),
    ).sort_index()


def test_flags_dip_when_undervalued_beyond_threshold():
    price_df = _price_df(close=100.0)
    as_of = price_df.index[-1]
    recent_dates = pd.bdate_range(end=as_of, periods=6)[:5]
    # Consensus targets all around 130 -> ~30% above the $100 price
    history = {"AAA": _history([(d.strftime("%Y-%m-%d"), t) for d, t in zip(recent_dates, [120.0, 125.0, 130.0, 135.0, 140.0])])}
    data = {"AAA": price_df}

    result = scan_analyst_target_gap(data, price_target_history=history, as_of=as_of, gap_threshold_pct=15.0)
    assert not result.empty
    row = result.iloc[0]
    assert row["direction"] == "dip"
    assert row["return_zscore"] > 15.0  # gap % stored here


def test_flags_up_when_overvalued_beyond_threshold():
    price_df = _price_df(close=200.0)
    as_of = price_df.index[-1]
    recent_dates = pd.bdate_range(end=as_of, periods=6)[:5]
    # Consensus targets all around 140 -> well below the $200 price
    history = {"AAA": _history([(d.strftime("%Y-%m-%d"), t) for d, t in zip(recent_dates, [130.0, 135.0, 140.0, 145.0, 150.0])])}
    data = {"AAA": price_df}

    result = scan_analyst_target_gap(data, price_target_history=history, as_of=as_of, gap_threshold_pct=15.0)
    assert not result.empty
    assert result.iloc[0]["direction"] == "up"


def test_no_signal_when_gap_within_threshold():
    price_df = _price_df(close=100.0)
    as_of = price_df.index[-1]
    recent_dates = pd.bdate_range(end=as_of, periods=6)[:5]
    # Consensus targets clustered near 103 -- well within a 15% threshold
    history = {"AAA": _history([(d.strftime("%Y-%m-%d"), t) for d, t in zip(recent_dates, [101.0, 102.0, 103.0, 104.0, 105.0])])}
    data = {"AAA": price_df}

    result = scan_analyst_target_gap(data, price_target_history=history, as_of=as_of, gap_threshold_pct=15.0)
    assert result.empty


def test_no_signal_without_enough_analysts():
    price_df = _price_df(close=100.0)
    as_of = price_df.index[-1]
    recent_dates = pd.bdate_range(end=as_of, periods=3)[:2]
    # Only 2 analysts -- below the default min_analysts=5 gate
    history = {"AAA": _history([(d.strftime("%Y-%m-%d"), t) for d, t in zip(recent_dates, [150.0, 160.0])])}
    data = {"AAA": price_df}

    result = scan_analyst_target_gap(data, price_target_history=history, as_of=as_of, gap_threshold_pct=15.0)
    assert result.empty


def test_no_signal_when_no_history_for_ticker():
    price_df = _price_df(close=100.0)
    as_of = price_df.index[-1]
    result = scan_analyst_target_gap({"AAA": price_df}, price_target_history={}, as_of=as_of)
    assert result.empty


def test_returns_empty_when_as_of_is_none():
    price_df = _price_df(close=100.0)
    result = scan_analyst_target_gap({"AAA": price_df}, price_target_history={"AAA": pd.DataFrame()}, as_of=None)
    assert result.empty


@pytest.mark.parametrize(
    "close", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0]
)
def test_signal_refuses_nonfinite_or_nonpositive_close(close):
    price_df = _price_df(close=close)
    as_of = price_df.index[-1]
    recent_dates = pd.bdate_range(end=as_of, periods=6)[:5]
    history = {
        "AAA": _history(
            [
                (date.strftime("%Y-%m-%d"), target)
                for date, target in zip(
                    recent_dates, [120.0, 125.0, 130.0, 135.0, 140.0]
                )
            ]
        )
    }
    with pytest.raises(PriceTargetContractError, match="finite positive"):
        scan_analyst_target_gap(
            {"AAA": price_df},
            price_target_history=history,
            as_of=as_of,
        )


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), -1.0, 0.0, True])
def test_signal_refuses_invalid_gap_threshold(threshold):
    price_df = _price_df(close=100.0)
    with pytest.raises(PriceTargetContractError, match="gap_threshold_pct"):
        scan_analyst_target_gap(
            {"AAA": price_df},
            price_target_history={},
            as_of=price_df.index[-1],
            gap_threshold_pct=threshold,
        )


def test_signal_refuses_timezone_instant_where_session_label_is_required():
    price_df = _price_df(close=100.0)
    with pytest.raises(PriceTargetContractError, match="session label"):
        scan_analyst_target_gap(
            {"AAA": price_df},
            price_target_history={},
            as_of=pd.Timestamp("2024-01-31T16:00:00-05:00"),
        )


if __name__ == "__main__":
    test_flags_dip_when_undervalued_beyond_threshold()
    test_flags_up_when_overvalued_beyond_threshold()
    test_no_signal_when_gap_within_threshold()
    test_no_signal_without_enough_analysts()
    test_no_signal_when_no_history_for_ticker()
    test_returns_empty_when_as_of_is_none()
    print("All analyst target signal tests passed.")
