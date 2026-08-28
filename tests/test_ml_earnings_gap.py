"""Tests for ml/earnings_gap.py (ML-5) -- doc 9.2's event-time mapping is
the correctness heart, so it gets the most coverage."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.earnings_gap import (
    EarningsGapError,
    GapObservation,
    check_event_support,
    classify_release_timing,
    compute_gap_observations,
    fit_gap_magnitude_quantiles,
    fit_gap_threshold_classifier,
    map_gap_window,
    median_absolute_gap_baseline,
)


def _sessions(start: str = "2026-01-05", n: int = 30) -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _price_frame(index: pd.DatetimeIndex) -> pd.DataFrame:
    n = len(index)
    return pd.DataFrame(
        {
            "open": np.linspace(100, 130, n),
            "high": np.linspace(101, 131, n),
            "low": np.linspace(99, 129, n),
            "close": np.linspace(100.5, 130.5, n),
            "volume": [1_000_000] * n,
        },
        index=index,
    )


# --- release-timing classification -----------------------------------------


@pytest.mark.parametrize(
    "timestamp, expected",
    [
        ("2026-01-06 16:30-05:00", "after_close"),
        ("2026-01-06 21:00-05:00", "after_close"),
        ("2026-01-06 07:00-05:00", "before_open"),
        ("2026-01-06 09:00-05:00", "before_open"),
        ("2026-01-06 11:00-05:00", "intraday"),
        ("2026-01-06 09:30-05:00", "intraday"),
    ],
)
def test_release_timing_classification(timestamp, expected):
    assert classify_release_timing(pd.Timestamp(timestamp)) == expected


def test_release_timing_converts_utc_to_eastern_before_classifying():
    # 12:00 UTC in January is 07:00 ET, not an intraday noon release.
    assert classify_release_timing(pd.Timestamp("2026-01-06T12:00:00Z")) == "before_open"


# --- gap window mapping (doc 9.2) ------------------------------------------


def test_after_close_release_maps_close_to_next_session_open():
    sessions = _sessions()
    window = map_gap_window("2026-01-06 16:30-05:00", session_index=sessions)

    assert window.available
    assert window.release_timing == "after_close"
    assert window.from_session == "2026-01-06"
    assert window.from_price_field == "close"
    assert window.to_session == "2026-01-07"
    assert window.to_price_field == "open"


def test_before_open_release_maps_prior_close_to_release_day_open():
    sessions = _sessions()
    window = map_gap_window("2026-01-07 07:00-05:00", session_index=sessions)

    assert window.available
    assert window.release_timing == "before_open"
    assert window.from_session == "2026-01-06"
    assert window.from_price_field == "close"
    assert window.to_session == "2026-01-07"
    assert window.to_price_field == "open"


def test_intraday_release_is_unavailable_not_guessed():
    sessions = _sessions()
    window = map_gap_window("2026-01-06 11:00-05:00", session_index=sessions)

    assert not window.available
    assert window.release_timing == "intraday"
    assert "intraday" in window.reason


def test_friday_after_close_release_gaps_into_monday_not_saturday():
    # 2026-01-09 is a Friday; the next SESSION is Monday 2026-01-12.
    sessions = _sessions()
    window = map_gap_window("2026-01-09 16:30-05:00", session_index=sessions)

    assert window.available
    assert window.from_session == "2026-01-09"
    assert window.to_session == "2026-01-12"
    assert pd.Timestamp(window.to_session).dayofweek == 0  # Monday


def test_monday_before_open_release_gaps_from_the_previous_friday():
    sessions = _sessions()
    window = map_gap_window("2026-01-12 07:00-05:00", session_index=sessions)

    assert window.available
    assert window.from_session == "2026-01-09"
    assert pd.Timestamp(window.from_session).dayofweek == 4  # Friday


def test_release_on_a_non_trading_day_is_unavailable():
    sessions = _sessions()
    # 2026-01-10 is a Saturday -- not a session for this ticker.
    window = map_gap_window("2026-01-10 16:30-05:00", session_index=sessions)
    assert not window.available
    assert "not a trading session" in window.reason


def test_after_close_release_on_the_last_known_session_has_no_gap_target():
    sessions = _sessions(n=5)
    window = map_gap_window(f"{sessions[-1].date()} 16:30-05:00", session_index=sessions)
    assert not window.available
    assert "no subsequent session" in window.reason


def test_before_open_release_on_the_first_known_session_has_no_gap_source():
    sessions = _sessions(n=5)
    window = map_gap_window(f"{sessions[0].date()} 07:00-05:00", session_index=sessions)
    assert not window.available
    assert "no prior session" in window.reason


def test_unparseable_timestamp_is_unavailable():
    window = map_gap_window("not-a-date", session_index=_sessions())
    assert not window.available
    assert window.release_timing == "unknown"


def test_timezone_naive_timestamp_is_unavailable():
    window = map_gap_window("2026-01-06 16:30", session_index=_sessions())
    assert not window.available
    assert "timezone-naive" in window.reason


# --- observations ----------------------------------------------------------


def test_compute_gap_observations_uses_the_mapped_price_fields():
    index = _sessions()
    price = _price_frame(index)
    observations, skipped = compute_gap_observations(
        "AAA", price, ["2026-01-06 16:30-05:00"]
    )

    assert len(observations) == 1
    assert not skipped
    observation = observations[0]
    expected_from = float(price.loc[pd.Timestamp("2026-01-06"), "close"])
    expected_to = float(price.loc[pd.Timestamp("2026-01-07"), "open"])
    assert observation.from_price == pytest.approx(expected_from)
    assert observation.to_price == pytest.approx(expected_to)
    assert observation.gap_pct == pytest.approx(
        (expected_to / expected_from - 1) * 100, abs=1e-6
    )


def test_compute_gap_observations_deduplicates_the_same_instant():
    price = _price_frame(_sessions())
    observations, skipped = compute_gap_observations(
        "AAA", price,
        ["2026-01-06T21:30:00Z", "2026-01-06T16:30:00-05:00"],
    )
    assert len(observations) == 1
    assert skipped[0]["reason"] == "duplicate earnings event"


def test_skipped_events_carry_their_reason():
    price = _price_frame(_sessions())
    observations, skipped = compute_gap_observations(
        "AAA", price, ["2026-01-06 11:00-05:00", "not-a-date"]
    )
    assert not observations
    assert len(skipped) == 2
    assert all(s["reason"] for s in skipped)


def test_compute_gap_observations_requires_open_and_close_columns():
    index = _sessions()
    price = _price_frame(index).drop(columns=["open"])
    with pytest.raises(EarningsGapError, match="open"):
        compute_gap_observations("AAA", price, ["2026-01-06 16:30-05:00"])


# --- baseline and support checks -------------------------------------------


def _observations(gaps: list[float]) -> list[GapObservation]:
    timestamps = pd.bdate_range("2026-01-05", periods=len(gaps))
    return [
        GapObservation(
            ticker="AAA", announced_at=f"{timestamps[i].date()}T21:30:00+00:00",
            release_timing="after_close", from_session="2026-01-01",
            to_session="2026-01-02", from_price=100.0, to_price=100.0 * (1 + g / 100),
            gap_pct=g,
        )
        for i, g in enumerate(gaps)
    ]


def test_median_absolute_gap_baseline_is_robust_to_one_extreme_event():
    typical = _observations([3.0, -2.0, 4.0, -3.0, 2.0])
    with_outlier = _observations([3.0, -2.0, 4.0, -3.0, 2.0, -60.0])
    assert median_absolute_gap_baseline(typical) == pytest.approx(3.0)
    # The median barely moves; a mean would have been dragged far away.
    assert abs(median_absolute_gap_baseline(with_outlier) - 3.0) < 1.0


def test_median_baseline_is_none_with_no_observations():
    assert median_absolute_gap_baseline([]) is None


def test_event_support_refuses_a_thin_sample_and_explains_why():
    support = check_event_support(_observations([1.0, 2.0, -1.0]), threshold_pct=5.0)
    assert not support["sufficient"]
    assert support["event_count"] == 3
    assert support["insufficiency_reasons"]
    assert support["ticker_count"] == 1


def test_event_support_counts_distinct_events_not_duplicate_rows():
    observation = _observations([8.0])[0]
    support = check_event_support([observation] * 30, threshold_pct=5.0)
    assert support["event_count"] == 1
    assert not support["sufficient"]


def test_event_support_reports_both_tails_separately():
    gaps = [8.0] * 10 + [-8.0] * 10 + [0.5] * 20
    support = check_event_support(_observations(gaps), threshold_pct=5.0)
    assert support["positive_tail_events"] == 10
    assert support["negative_tail_events"] == 10
    assert support["sufficient"]


def test_event_support_refuses_when_only_one_tail_is_populated():
    gaps = [8.0] * 20 + [0.5] * 20
    support = check_event_support(_observations(gaps), threshold_pct=5.0)
    assert not support["sufficient"]
    assert any("downside" in r for r in support["insufficiency_reasons"])


# --- model fits ------------------------------------------------------------


def test_threshold_classifier_refuses_a_single_class_target():
    x = np.random.default_rng(0).normal(size=(50, 2))
    y = np.zeros(50)
    with pytest.raises(EarningsGapError, match="both classes"):
        fit_gap_threshold_classifier(x, y)


def test_threshold_classifier_refuses_a_thin_sample():
    x = np.random.default_rng(0).normal(size=(10, 2))
    y = np.array([0, 1] * 5)
    with pytest.raises(EarningsGapError, match="at least"):
        fit_gap_threshold_classifier(x, y)


def test_threshold_classifier_learns_a_planted_separation():
    rng = np.random.default_rng(0)
    x = np.vstack([rng.normal(-2, 0.5, (50, 1)), rng.normal(2, 0.5, (50, 1))])
    y = np.array([0] * 50 + [1] * 50)
    model = fit_gap_threshold_classifier(x, y)
    probabilities = model.predict_proba(x)[:, 1]
    assert probabilities[:50].mean() < probabilities[50:].mean()


def test_quantile_models_are_ordered_and_refuse_bad_quantiles():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(120, 2))
    y = np.abs(rng.normal(5, 2, 120))
    models = fit_gap_magnitude_quantiles(x, y, quantiles=(0.1, 0.5, 0.9))
    assert set(models) == {0.1, 0.5, 0.9}
    low = models[0.1].predict(x).mean()
    high = models[0.9].predict(x).mean()
    assert low < high

    with pytest.raises(EarningsGapError, match="quantiles"):
        fit_gap_magnitude_quantiles(x, y, quantiles=(1.5,))


def test_release_timing_uses_the_real_session_close_on_an_early_close_day():
    """A 14:30 ET release on a 13:00 ET half day is after_close, not intraday.

    The classifier previously compared against a fixed 16:00 ET hour, so on
    roughly nine early-close sessions a year it placed a genuinely
    after-close release inside the session and misaligned its event window.
    """
    import pandas as pd

    from ml.earnings_gap import classify_release_timing

    # 2024-07-03 is the July 3rd half day: NYSE closes at 13:00 ET.
    assert classify_release_timing(pd.Timestamp("2024-07-03T14:30:00-04:00")) == "after_close"
    assert classify_release_timing(pd.Timestamp("2024-07-03T13:00:00-04:00")) == "after_close"
    # Just before that real close it is still intraday.
    assert classify_release_timing(pd.Timestamp("2024-07-03T12:59:00-04:00")) == "intraday"

    # A full session keeps the 16:00 ET boundary exactly as before, so the
    # calendar lookup cannot silently reclassify ordinary sessions.
    assert classify_release_timing(pd.Timestamp("2024-01-02T15:59:00-05:00")) == "intraday"
    assert classify_release_timing(pd.Timestamp("2024-01-02T16:00:00-05:00")) == "after_close"
    assert classify_release_timing(pd.Timestamp("2024-01-02T09:00:00-05:00")) == "before_open"

    # A non-session date has no real close and keeps the fixed-hour fallback.
    assert classify_release_timing(pd.Timestamp("2024-01-06T17:00:00-05:00")) == "after_close"
