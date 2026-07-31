"""Tests for ml/labels.py -- strategy doc 6.4/6.6: entry/exit recorded per
row, tail rows without a complete horizon dropped and counted, forward-only
computation, deterministic output."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from ml.labels import (
    LabelError,
    compute_forward_downside_threshold_labels,
    compute_forward_excess_return_labels,
    compute_forward_realized_vol_labels,
)


def _session_index(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2026-01-01", periods=n)


def _flat_series(n: int, value: float = 100.0) -> pd.Series:
    return pd.Series([value] * n, index=_session_index(n))


def _trending_close(n: int, daily_pct: float = 1.0) -> pd.Series:
    index = _session_index(n)
    values = [100.0 * (1 + daily_pct / 100) ** i for i in range(n)]
    return pd.Series(values, index=index)


def test_excess_return_drops_tail_rows_without_complete_horizon():
    n = 30
    horizon = 20
    close = _trending_close(n)
    open_ = close.copy()
    benchmark = _flat_series(n)

    rows, dropped = compute_forward_excess_return_labels(
        "AAA", close, open_, benchmark, horizon_sessions=horizon
    )

    # last (horizon + 1) as_of positions have no complete forward horizon
    assert dropped == horizon + 1
    assert len(rows) == n - dropped
    # every retained row's exit is strictly within the available index
    for row in rows:
        assert row.exit_session <= str(close.index[-1].date())


def test_excess_return_entry_and_exit_prices_match_next_open_and_horizon_close():
    close = _trending_close(10, daily_pct=2.0)
    open_ = close.copy()
    benchmark = _flat_series(10)

    rows, _ = compute_forward_excess_return_labels(
        "AAA", close, open_, benchmark, horizon_sessions=3
    )

    first = rows[0]
    assert first.as_of_session == str(close.index[0].date())
    assert first.entry_session == str(close.index[1].date())
    assert first.entry_price == pytest.approx(float(open_.iloc[1]))
    assert first.exit_session == str(close.index[4].date())
    assert first.exit_price == pytest.approx(float(close.iloc[4]))


def test_excess_return_subtracts_benchmark_and_cost():
    n = 10
    close = _trending_close(n, daily_pct=1.0)
    open_ = close.copy()
    benchmark = _trending_close(n, daily_pct=0.5)

    rows, _ = compute_forward_excess_return_labels(
        "AAA", close, open_, benchmark, horizon_sessions=2, round_trip_cost_bps=50.0
    )

    row = rows[0]
    expected_raw = (row.exit_price / row.entry_price - 1.0) * 100
    assert row.components["raw_return_pct"] == pytest.approx(expected_raw, abs=1e-4)
    assert row.components["round_trip_cost_pct"] == pytest.approx(0.5, abs=1e-6)
    assert row.value == pytest.approx(
        row.components["raw_return_pct"]
        - row.components["benchmark_return_pct"]
        - row.components["round_trip_cost_pct"],
        abs=1e-4,
    )


def test_excess_return_rejects_mismatched_close_open_index():
    close = _flat_series(10)
    open_ = _flat_series(9)
    benchmark = _flat_series(10)
    with pytest.raises(LabelError, match="same session index"):
        compute_forward_excess_return_labels("AAA", close, open_, benchmark, horizon_sessions=2)


def test_excess_return_rejects_unsorted_index():
    close = _flat_series(10)
    shuffled = close.iloc[::-1]
    with pytest.raises(LabelError, match="not sorted"):
        compute_forward_excess_return_labels("AAA", shuffled, shuffled, close, horizon_sessions=2)


def test_excess_return_rejects_duplicate_index():
    index = _session_index(5).append(_session_index(5)[-1:])
    close = pd.Series(range(6), index=index, dtype=float)
    with pytest.raises(LabelError, match="duplicate"):
        compute_forward_excess_return_labels("AAA", close, close, close, horizon_sessions=1)


def test_excess_return_rejects_empty_series():
    empty = pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    with pytest.raises(LabelError, match="empty"):
        compute_forward_excess_return_labels("AAA", empty, empty, empty, horizon_sessions=1)


def test_excess_return_drops_rows_where_benchmark_is_unavailable():
    n = 10
    close = _trending_close(n)
    open_ = close.copy()
    # Benchmark only covers the first half of the session index -- reindex
    # will introduce NaN for the rest, which must be dropped, not
    # propagated as a false "zero benchmark return" or similar.
    benchmark = _flat_series(n // 2)

    rows, dropped = compute_forward_excess_return_labels(
        "AAA", close, open_, benchmark, horizon_sessions=2
    )
    for row in rows:
        # only rows whose entry+exit both fall within the benchmark's
        # covered range should survive
        assert row.entry_session <= str(benchmark.index[-1].date())


def test_excess_return_rejects_negative_cost():
    close = _flat_series(10)
    with pytest.raises(LabelError, match="round_trip_cost_bps"):
        compute_forward_excess_return_labels(
            "AAA", close, close, close, horizon_sessions=2, round_trip_cost_bps=-1.0
        )


def test_excess_return_rejects_non_positive_horizon():
    close = _flat_series(10)
    with pytest.raises(LabelError, match="horizon_sessions"):
        compute_forward_excess_return_labels("AAA", close, close, close, horizon_sessions=0)


def test_realized_vol_label_values_are_finite_and_nonnegative():
    close = _trending_close(30, daily_pct=1.5)
    rows, dropped = compute_forward_realized_vol_labels("AAA", close, horizon_sessions=5)

    # last price index used is i+horizon, which must stay <= n-1, so
    # exactly `horizon` tail as_of positions have no complete window.
    assert dropped == 5
    for row in rows:
        assert row.value >= 0
        assert math.isfinite(row.value)


def test_realized_vol_label_zero_for_perfectly_flat_forward_window():
    close = _flat_series(20)
    rows, _ = compute_forward_realized_vol_labels("AAA", close, horizon_sessions=5)
    assert all(row.value == 0.0 for row in rows)


def test_realized_vol_rejects_horizon_below_two():
    close = _flat_series(10)
    with pytest.raises(LabelError, match="at least 2"):
        compute_forward_realized_vol_labels("AAA", close, horizon_sessions=1)


def test_downside_threshold_flags_rows_crossing_the_threshold():
    n = 10
    # A sharply falling ticker vs a flat benchmark should breach a 5% downside threshold.
    close = _trending_close(n, daily_pct=-3.0)
    open_ = close.copy()
    benchmark = _flat_series(n)

    rows, _ = compute_forward_downside_threshold_labels(
        "AAA", close, open_, benchmark, horizon_sessions=3, downside_threshold_pct=5.0
    )

    assert rows
    for row in rows:
        breached = row.components["excess_return_pct"] <= -5.0
        assert row.value == (1.0 if breached else 0.0)


def test_downside_threshold_never_flags_a_rising_ticker():
    n = 10
    close = _trending_close(n, daily_pct=3.0)
    open_ = close.copy()
    benchmark = _flat_series(n)

    rows, _ = compute_forward_downside_threshold_labels(
        "AAA", close, open_, benchmark, horizon_sessions=3, downside_threshold_pct=5.0
    )
    assert all(row.value == 0.0 for row in rows)


def test_downside_threshold_rejects_non_positive_threshold():
    close = _flat_series(10)
    with pytest.raises(LabelError, match="downside_threshold_pct"):
        compute_forward_downside_threshold_labels(
            "AAA", close, close, close, horizon_sessions=2, downside_threshold_pct=0.0
        )


def test_label_row_to_dict_is_json_serializable():
    import json

    close = _trending_close(10)
    rows, _ = compute_forward_excess_return_labels("AAA", close, close, close, horizon_sessions=2)
    json.dumps(rows[0].to_dict())
