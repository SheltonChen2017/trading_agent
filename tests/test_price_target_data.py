"""
Sanity tests for data/price_target_data.py. Run with:
python tests/test_price_target_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from data.price_target_data import compute_consensus_price_target


def _history(entries: list[tuple[str, str, float]]) -> pd.DataFrame:
    """entries: list of (date_str, firm, price_target)"""
    dates = pd.to_datetime([e[0] for e in entries])
    return pd.DataFrame(
        {"firm": [e[1] for e in entries], "price_target": [e[2] for e in entries]},
        index=dates,
    ).sort_index()


def test_drops_highest_and_lowest_before_averaging():
    # 5 firms: 100, 110, 120, 130, 1000 (outlier) -- trimmed should drop
    # 100 (lowest) and 1000 (highest), leaving 110/120/130 -> median 120.
    history = _history([
        ("2024-01-01", "A", 100.0), ("2024-01-02", "B", 110.0), ("2024-01-03", "C", 120.0),
        ("2024-01-04", "D", 130.0), ("2024-01-05", "E", 1000.0),
    ])
    result = compute_consensus_price_target(history, as_of=pd.Timestamp("2024-01-10"), min_analysts=5, method="median")
    assert result == 120.0


def test_uses_mean_when_requested():
    history = _history([
        ("2024-01-01", "A", 100.0), ("2024-01-02", "B", 110.0), ("2024-01-03", "C", 120.0),
        ("2024-01-04", "D", 130.0), ("2024-01-05", "E", 1000.0),
    ])
    result = compute_consensus_price_target(history, as_of=pd.Timestamp("2024-01-10"), min_analysts=5, method="mean")
    assert abs(result - (110.0 + 120.0 + 130.0) / 3) < 1e-9


def test_never_uses_targets_dated_after_as_of():
    # Firm E's target is dated AFTER as_of -- must not be visible at all,
    # even though it would otherwise be "the most recent."
    history = _history([
        ("2024-01-01", "A", 100.0), ("2024-01-02", "B", 110.0), ("2024-01-03", "C", 120.0),
        ("2024-01-04", "D", 130.0), ("2024-06-01", "E", 9999.0),  # future relative to as_of
    ])
    result = compute_consensus_price_target(history, as_of=pd.Timestamp("2024-01-10"), min_analysts=4, method="median")
    # Only A/B/C/D visible -- trims 100 and 130, leaves 110/120 -> median 115
    assert result == 115.0


def test_stale_targets_outside_window_are_excluded():
    # Firm A's only target is 2 years old -- should be excluded from a
    # 365-day staleness window even though it's dated before as_of.
    history = _history([
        ("2022-01-01", "A", 500.0),  # stale
        ("2024-01-01", "B", 110.0), ("2024-01-02", "C", 120.0),
        ("2024-01-03", "D", 130.0), ("2024-01-04", "E", 140.0),
    ])
    result = compute_consensus_price_target(
        history, as_of=pd.Timestamp("2024-01-10"), staleness_days=365, min_analysts=4, method="median",
    )
    # A excluded -> only B/C/D/E (4 firms) -> trims 110 and 140, leaves 120/130 -> median 125
    assert result == 125.0


def test_uses_each_firms_most_recent_target_only():
    # Firm A revised their target from 100 to 200 -- only 200 should count.
    history = _history([
        ("2024-01-01", "A", 100.0), ("2024-01-05", "A", 200.0),
        ("2024-01-02", "B", 110.0), ("2024-01-03", "C", 120.0), ("2024-01-04", "D", 130.0),
    ])
    result = compute_consensus_price_target(history, as_of=pd.Timestamp("2024-01-10"), min_analysts=4, method="median")
    # 4 distinct firms (A=200, B=110, C=120, D=130) -> trims 110 and 200, leaves 120/130 -> median 125
    assert result == 125.0


def test_returns_none_below_min_analysts_threshold():
    history = _history([("2024-01-01", "A", 100.0), ("2024-01-02", "B", 110.0)])
    result = compute_consensus_price_target(history, as_of=pd.Timestamp("2024-01-10"), min_analysts=5)
    assert result is None


def test_returns_none_on_empty_history():
    assert compute_consensus_price_target(pd.DataFrame(columns=["firm", "price_target"]), pd.Timestamp("2024-01-10")) is None


if __name__ == "__main__":
    test_drops_highest_and_lowest_before_averaging()
    test_uses_mean_when_requested()
    test_never_uses_targets_dated_after_as_of()
    test_stale_targets_outside_window_are_excluded()
    test_uses_each_firms_most_recent_target_only()
    test_returns_none_below_min_analysts_threshold()
    test_returns_none_on_empty_history()
    print("All price target data tests passed.")
