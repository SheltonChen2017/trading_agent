"""
Tests for the consecutive-earnings-surprise persistence signal.

The signal reads a ticker's WHOLE earnings history to count a streak,
while being evaluated as of one historical date — so the one defect that
would invalidate every backtest number is counting an earnings event
that hadn't happened yet. That is the first test here, and it is
asserted by construction (append later events, demand no earlier result
moves) rather than by inspection.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

from signals.pead_persistence import (
    compute_surprise_streak,
    scan_pead_persistence,
)


def _prices(days: int = 400) -> pd.DataFrame:
    close = 100 * np.cumprod(1 + np.random.default_rng(0).normal(0.0003, 0.01, days))
    dates = pd.bdate_range(end=pd.Timestamp("2026-01-02"), periods=days)
    return pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99,
         "close": close, "volume": np.full(days, 1_000_000.0)},
        index=dates,
    )


def _earnings(dates: list[pd.Timestamp], surprises: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"surprise_pct": surprises, "reported_eps": [1.0] * len(surprises)},
                        index=pd.DatetimeIndex(dates))


def _quarterly_dates(price_index: pd.DatetimeIndex, count: int, step: int = 63) -> list[pd.Timestamp]:
    """Pick `count` trading days ~a quarter apart, oldest first."""
    positions = [len(price_index) - 1 - step * i for i in range(count)]
    return [price_index[p] for p in reversed(positions)]


# --------------------------------------------------------------------------
# Causality
# --------------------------------------------------------------------------

def test_streak_never_counts_future_earnings():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 6)
    # Four beats, then two more beats AFTER the date we evaluate at.
    surprises = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
    full = _earnings(dates, surprises)

    evaluate_at = dates[3]
    streak_full, _ = compute_surprise_streak(full, evaluate_at)
    truncated = full.loc[:evaluate_at]
    streak_truncated, _ = compute_surprise_streak(truncated, evaluate_at)

    assert streak_full == streak_truncated == 4, (
        f"streak at {evaluate_at.date()} must count only the 4 events up to it, "
        f"got full={streak_full} truncated={streak_truncated}"
    )


def test_scan_result_is_unchanged_by_later_earnings_events():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 6)
    early = _earnings(dates[:4], [4.0] * 4)
    late = _earnings(dates, [4.0] * 6)

    as_of = dates[3]
    from_early = scan_pead_persistence({"T": prices}, {"T": early}, as_of=as_of)
    from_late = scan_pead_persistence({"T": prices}, {"T": late}, as_of=as_of)

    pd.testing.assert_frame_equal(
        from_early, from_late,
        obj="a later earnings event changed an earlier date's signal (look-ahead leak)",
    )


def test_a_future_beat_cannot_rescue_a_broken_streak():
    """
    A run broken by a miss must stay broken at that date, even though the
    company went on to beat repeatedly afterwards.
    """
    prices = _prices()
    dates = _quarterly_dates(prices.index, 6)
    surprises = [6.0, 6.0, -6.0, 6.0, 6.0, 6.0]  # miss in the middle
    frame = _earnings(dates, surprises)

    streak, current = compute_surprise_streak(frame, dates[3])

    assert streak == 1, f"streak should reset to 1 after the miss, got {streak}"
    assert current == 6.0
    assert scan_pead_persistence({"T": prices}, {"T": frame}, as_of=dates[3]).empty


# --------------------------------------------------------------------------
# Streak semantics
# --------------------------------------------------------------------------

def test_four_consecutive_beats_fire_as_up():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 4)
    frame = _earnings(dates, [7.0, 7.0, 7.0, 7.0])

    result = scan_pead_persistence({"T": prices}, {"T": frame}, as_of=dates[-1])

    assert len(result) == 1, f"expected one signal, got:\n{result}"
    assert result.iloc[0]["direction"] == "up"
    assert result.iloc[0]["return_zscore"] == 4.0, "return_zscore carries the streak length"


def test_four_consecutive_misses_fire_as_dip():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 4)
    frame = _earnings(dates, [-7.0, -7.0, -7.0, -7.0])

    result = scan_pead_persistence({"T": prices}, {"T": frame}, as_of=dates[-1])

    assert len(result) == 1
    assert result.iloc[0]["direction"] == "dip"


def test_three_beats_is_below_the_gate():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 4)
    # The oldest is a miss, so the run ending at the last event is only 3.
    frame = _earnings(dates, [-7.0, 7.0, 7.0, 7.0])

    assert scan_pead_persistence({"T": prices}, {"T": frame}, as_of=dates[-1]).empty


def test_streak_is_capped_at_max_quarters():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 12)
    frame = _earnings(dates, [5.0] * 12)

    streak, _ = compute_surprise_streak(frame, dates[-1], max_streak_quarters=8)

    assert streak == 8, f"streak must not exceed the 8-quarter window, got {streak}"


def test_exact_consensus_breaks_the_streak():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 5)
    frame = _earnings(dates, [5.0, 5.0, 0.0, 5.0, 5.0])

    streak, _ = compute_surprise_streak(frame, dates[-1])

    assert streak == 2, f"a 0% surprise must break the run, got streak={streak}"


def test_small_current_surprise_is_rejected_even_with_a_long_streak():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 6)
    # Long run of beats, but the latest one is a rounding-error beat.
    frame = _earnings(dates, [8.0, 8.0, 8.0, 8.0, 8.0, 0.01])

    result = scan_pead_persistence({"T": prices}, {"T": frame}, as_of=dates[-1])

    assert result.empty, f"a negligible current surprise must not fire, got:\n{result}"


def test_unsorted_earnings_frame_is_handled():
    """
    A frame arriving newest-first would make a naive .loc[:event] slice
    mean 'everything from the newest down to this one' — i.e. the future.
    """
    prices = _prices()
    dates = _quarterly_dates(prices.index, 5)
    ordered = _earnings(dates, [-9.0, 9.0, 9.0, 9.0, 9.0])
    shuffled = ordered.iloc[::-1]

    ordered_streak, _ = compute_surprise_streak(ordered, dates[-1])
    shuffled_streak, _ = compute_surprise_streak(shuffled, dates[-1])

    assert ordered_streak == shuffled_streak == 4, (
        f"row order must not change the streak; ordered={ordered_streak} shuffled={shuffled_streak}"
    )


# --------------------------------------------------------------------------
# Degenerate inputs
# --------------------------------------------------------------------------

def test_fires_only_on_the_reaction_day():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 4)
    frame = _earnings(dates, [7.0] * 4)

    non_event = prices.index[-30]
    assert non_event not in frame.index
    assert scan_pead_persistence({"T": prices}, {"T": frame}, as_of=non_event).empty


def test_missing_or_empty_earnings_is_skipped_not_guessed():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 4)

    empty = pd.DataFrame(columns=["surprise_pct", "reported_eps"], index=pd.DatetimeIndex([]))
    assert scan_pead_persistence({"T": prices}, {"T": empty}, as_of=dates[-1]).empty
    assert scan_pead_persistence({"T": prices}, {}, as_of=dates[-1]).empty
    assert scan_pead_persistence({"T": prices}, {"T": None}, as_of=dates[-1]).empty


def test_nan_surprise_breaks_the_streak_rather_than_being_treated_as_a_beat():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 5)
    frame = _earnings(dates, [6.0, 6.0, float("nan"), 6.0, 6.0])

    streak, _ = compute_surprise_streak(frame, dates[-1])

    assert streak == 2, f"a missing surprise must break the run, got {streak}"


def test_as_of_none_returns_empty():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 4)
    frame = _earnings(dates, [7.0] * 4)
    assert scan_pead_persistence({"T": prices}, {"T": frame}, as_of=None).empty


def test_invalid_streak_bounds_are_rejected():
    prices = _prices()
    dates = _quarterly_dates(prices.index, 4)
    frame = _earnings(dates, [7.0] * 4)

    with pytest.raises(ValueError):
        scan_pead_persistence({"T": prices}, {"T": frame}, as_of=dates[-1], min_streak_quarters=0)
    with pytest.raises(ValueError, match="cannot exceed"):
        scan_pead_persistence(
            {"T": prices}, {"T": frame}, as_of=dates[-1],
            min_streak_quarters=9, max_streak_quarters=8,
        )
    with pytest.raises(ValueError):
        compute_surprise_streak(frame, dates[-1], max_streak_quarters=0)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
