"""
Sanity tests for data/price_target_data.py. Run with:
python tests/test_price_target_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import pytest

from data.price_target_data import (
    ConsensusMethod,
    PriceTargetContractError,
    compute_consensus_price_target,
    fetch_price_target_history,
)


def _history(entries: list[tuple[str, str, float]]) -> pd.DataFrame:
    """entries: list of (date_str, firm, price_target)"""
    dates = pd.to_datetime([e[0] for e in entries])
    return pd.DataFrame(
        {"firm": [e[1] for e in entries], "price_target": [e[2] for e in entries]},
        index=pd.DatetimeIndex(dates, name="effective_session"),
    ).sort_index()


def _install_provider_history(monkeypatch, raw: pd.DataFrame) -> None:
    class _FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker
            self.upgrades_downgrades = raw

    monkeypatch.setattr("yfinance.Ticker", _FakeTicker)


def test_drops_highest_and_lowest_before_averaging():
    # 5 firms: 100, 110, 120, 130, 1000 (outlier) -- trimmed should drop
    # 100 (lowest) and 1000 (highest), leaving 110/120/130 -> median 120.
    history = _history([
        ("2024-01-02", "A", 100.0), ("2024-01-03", "B", 110.0), ("2024-01-04", "C", 120.0),
        ("2024-01-05", "D", 130.0), ("2024-01-08", "E", 1000.0),
    ])
    result = compute_consensus_price_target(
        history,
        as_of=pd.Timestamp("2024-01-10"),
        min_analysts=5,
        method=ConsensusMethod.MEDIAN,
    )
    assert result == 120.0


def test_uses_mean_when_requested():
    history = _history([
        ("2024-01-02", "A", 100.0), ("2024-01-03", "B", 110.0), ("2024-01-04", "C", 120.0),
        ("2024-01-05", "D", 130.0), ("2024-01-08", "E", 1000.0),
    ])
    result = compute_consensus_price_target(
        history,
        as_of=pd.Timestamp("2024-01-10"),
        min_analysts=5,
        method=ConsensusMethod.MEAN,
    )
    assert abs(result - (110.0 + 120.0 + 130.0) / 3) < 1e-9


def test_never_uses_targets_dated_after_as_of():
    # Firm E's target is dated AFTER as_of -- must not be visible at all,
    # even though it would otherwise be "the most recent."
    history = _history([
        ("2024-01-02", "A", 100.0), ("2024-01-03", "B", 110.0), ("2024-01-04", "C", 120.0),
        ("2024-01-05", "D", 130.0), ("2024-06-03", "E", 9999.0),  # future relative to as_of
    ])
    result = compute_consensus_price_target(history, as_of=pd.Timestamp("2024-01-10"), min_analysts=4, method="median")
    # Only A/B/C/D visible -- trims 100 and 130, leaves 110/120 -> median 115
    assert result == 115.0


def test_stale_targets_outside_window_are_excluded():
    # Firm A's only target is 2 years old -- should be excluded from a
    # 365-day staleness window even though it's dated before as_of.
    history = _history([
        ("2022-01-03", "A", 500.0),  # stale
        ("2024-01-02", "B", 110.0), ("2024-01-03", "C", 120.0),
        ("2024-01-04", "D", 130.0), ("2024-01-05", "E", 140.0),
    ])
    result = compute_consensus_price_target(
        history, as_of=pd.Timestamp("2024-01-10"), staleness_days=365, min_analysts=4, method="median",
    )
    # A excluded -> only B/C/D/E (4 firms) -> trims 110 and 140, leaves 120/130 -> median 125
    assert result == 125.0


def test_uses_each_firms_most_recent_target_only():
    # Firm A revised their target from 100 to 200 -- only 200 should count.
    history = _history([
        ("2024-01-02", "A", 100.0), ("2024-01-08", "A", 200.0),
        ("2024-01-03", "B", 110.0), ("2024-01-04", "C", 120.0), ("2024-01-05", "D", 130.0),
    ])
    result = compute_consensus_price_target(history, as_of=pd.Timestamp("2024-01-10"), min_analysts=4, method="median")
    # 4 distinct firms (A=200, B=110, C=120, D=130) -> trims 110 and 200, leaves 120/130 -> median 125
    assert result == 125.0


def test_returns_none_below_min_analysts_threshold():
    history = _history([("2024-01-02", "A", 100.0), ("2024-01-03", "B", 110.0)])
    result = compute_consensus_price_target(history, as_of=pd.Timestamp("2024-01-10"), min_analysts=5)
    assert result is None


def test_returns_none_on_empty_history():
    empty = pd.DataFrame(
        columns=["firm", "price_target"],
        index=pd.DatetimeIndex([], name="effective_session"),
    )
    assert compute_consensus_price_target(empty, pd.Timestamp("2024-01-10")) is None


def test_fetch_price_target_history_applies_after_close_effective_date(monkeypatch):
    # A publication at/after the verified close belongs to the next exchange
    # session. The aware instant must be interpreted before it is converted to
    # the deliberately timezone-free effective-session label.
    raw = pd.DataFrame(
        {
            "Firm": ["Before Close", "After Close"],
            "currentPriceTarget": [100.0, 200.0],
        },
        index=pd.DatetimeIndex(
            ["2024-01-02 09:30:00-05:00", "2024-01-02 16:30:00-05:00"]
        ),
    )
    _install_provider_history(monkeypatch, raw)
    history = fetch_price_target_history(["AAPL"])["AAPL"]

    before_close_row = history.loc[pd.Timestamp("2024-01-02")]
    after_close_row = history.loc[pd.Timestamp("2024-01-03")]
    assert before_close_row["price_target"] == 100.0
    assert after_close_row["price_target"] == 200.0
    assert tuple(history.columns) == ("firm", "price_target")
    assert history.index.name == "effective_session"
    assert history.index.tz is None


def test_fetch_uses_actual_half_day_close_and_next_exchange_session(monkeypatch):
    raw = pd.DataFrame(
        {
            "Firm": ["Before Early Close", "After Early Close"],
            "currentPriceTarget": [100.0, 200.0],
        },
        index=pd.DatetimeIndex(
            ["2024-07-03 12:30:00-04:00", "2024-07-03 13:30:00-04:00"]
        ),
    )
    _install_provider_history(monkeypatch, raw)
    history = fetch_price_target_history(["AAPL"])["AAPL"]
    assert history.loc[pd.Timestamp("2024-07-03"), "price_target"] == 100.0
    assert history.loc[pd.Timestamp("2024-07-05"), "price_target"] == 200.0


def test_fetch_refuses_provider_instants_without_timezone_evidence(monkeypatch):
    raw = pd.DataFrame(
        {"Firm": ["Unknown Clock"], "currentPriceTarget": [100.0]},
        index=pd.to_datetime(["2024-01-02 09:30:00"]),
    )
    _install_provider_history(monkeypatch, raw)
    with pytest.raises(PriceTargetContractError, match="timezone-aware"):
        fetch_price_target_history(["AAPL"])


def test_fetch_emits_only_finite_positive_provider_targets(monkeypatch):
    raw = pd.DataFrame(
        {
            "Firm": ["Valid", "NaN", "Positive Infinity", "Zero", "Negative"],
            "currentPriceTarget": [100.0, float("nan"), float("inf"), 0.0, -1.0],
        },
        index=pd.DatetimeIndex(
            [
                "2024-01-02 10:00:00-05:00",
                "2024-01-03 10:00:00-05:00",
                "2024-01-04 10:00:00-05:00",
                "2024-01-05 10:00:00-05:00",
                "2024-01-08 10:00:00-05:00",
            ]
        ),
    )
    _install_provider_history(monkeypatch, raw)
    history = fetch_price_target_history(["AAPL"])["AAPL"]
    assert history.reset_index().to_dict("records") == [
        {
            "effective_session": pd.Timestamp("2024-01-02"),
            "firm": "Valid",
            "price_target": 100.0,
        }
    ]


@pytest.mark.parametrize("target", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0])
def test_consensus_refuses_nonfinite_or_nonpositive_target_values(target):
    history = _history(
        [
            ("2024-01-02", "A", target),
            ("2024-01-03", "B", 110.0),
            ("2024-01-04", "C", 120.0),
            ("2024-01-05", "D", 130.0),
            ("2024-01-08", "E", 140.0),
        ]
    )
    with pytest.raises(PriceTargetContractError, match="finite positive"):
        compute_consensus_price_target(history, pd.Timestamp("2024-01-10"))


@pytest.mark.parametrize("method", ["average", "MEDIAN", "", None])
def test_consensus_refuses_unknown_aggregation_semantics(method):
    history = _history(
        [
            ("2024-01-02", "A", 100.0),
            ("2024-01-03", "B", 110.0),
            ("2024-01-04", "C", 120.0),
        ]
    )
    with pytest.raises(PriceTargetContractError, match="mean.*median"):
        compute_consensus_price_target(
            history, pd.Timestamp("2024-01-10"), min_analysts=3, method=method
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda frame: frame.assign(extra="drift"),
        lambda frame: frame[["price_target", "firm"]],
        lambda frame: frame.rename_axis("date"),
    ],
)
def test_consensus_refuses_history_schema_drift(mutate):
    history = mutate(
        _history(
            [
                ("2024-01-02", "A", 100.0),
                ("2024-01-03", "B", 110.0),
                ("2024-01-04", "C", 120.0),
            ]
        )
    )
    with pytest.raises(PriceTargetContractError):
        compute_consensus_price_target(
            history, pd.Timestamp("2024-01-10"), min_analysts=3
        )


def test_consensus_refuses_timezone_bearing_as_of_instant():
    history = _history(
        [
            ("2024-01-02", "A", 100.0),
            ("2024-01-03", "B", 110.0),
            ("2024-01-04", "C", 120.0),
        ]
    )
    with pytest.raises(PriceTargetContractError, match="session label"):
        compute_consensus_price_target(
            history,
            pd.Timestamp("2024-01-10T16:00:00-05:00"),
            min_analysts=3,
        )


if __name__ == "__main__":
    test_drops_highest_and_lowest_before_averaging()
    test_uses_mean_when_requested()
    test_never_uses_targets_dated_after_as_of()
    test_stale_targets_outside_window_are_excluded()
    test_uses_each_firms_most_recent_target_only()
    test_returns_none_below_min_analysts_threshold()
    test_returns_none_on_empty_history()
    print("All price target data tests passed.")
