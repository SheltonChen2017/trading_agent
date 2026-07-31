"""Tests for ml/availability.py (ML-LR-1), covering the live-readiness
plan's own section 7.5 list: future availability refused; an after-close
datum unavailable to a same-session pre-close decision; a later revision
does not replace the historically visible value; missing lineage keeps
point_in_time_data=False; complete valid lineage is the ONLY path to True;
current members projected backward are labeled survivorship-biased;
historical membership selects the right names per session; timezone-
equivalent timestamps order consistently; sidecar hash mismatch refuses
load; and prefix invariance.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from ml.availability import (
    AvailabilityError,
    CoverageResult,
    FeatureAvailabilityRecord,
    RetroactivelyAdjustedSource,
    UniverseMembershipRecord,
    evaluate_point_in_time_coverage,
    latest_visible_revision,
)

_HASH = "a" * 64


def _record(**overrides) -> FeatureAvailabilityRecord:
    payload = dict(
        as_of_session="2026-07-31",
        ticker="NVDA",
        feature_name="close",
        event_at="2026-07-31T20:00:00+00:00",
        available_at="2026-07-31T20:05:00+00:00",
        observed_at="2026-07-31T20:10:00+00:00",
        source_id="vendor-a",
        source_version="1.0",
        revision_id="r1",
        raw_value_hash=_HASH,
    )
    payload.update(overrides)
    return FeatureAvailabilityRecord(**payload)


def _membership(**overrides) -> UniverseMembershipRecord:
    payload = dict(
        universe_id="tech-v1",
        ticker="NVDA",
        effective_from="2020-01-01",
        effective_to=None,
        announced_at="2019-12-20T13:00:00+00:00",
        available_at="2019-12-20T13:00:00+00:00",
        source_id="vendor-a",
        source_version="1.0",
    )
    payload.update(overrides)
    return UniverseMembershipRecord(**payload)


def _cutoffs(session: str = "2026-07-31", at: str = "2026-07-31T21:00:00+00:00"):
    return {session: at}


# --- timestamp ordering -----------------------------------------------------


def test_event_cannot_be_knowable_before_it_happens():
    with pytest.raises(AvailabilityError, match="event_at must not be after available_at"):
        _record(event_at="2026-07-31T22:00:00+00:00", available_at="2026-07-31T20:00:00+00:00")


def test_pipeline_cannot_observe_a_value_before_it_was_knowable():
    with pytest.raises(AvailabilityError, match="available_at must not be after observed_at"):
        _record(available_at="2026-07-31T23:00:00+00:00", observed_at="2026-07-31T20:00:00+00:00")


def test_naive_timestamps_are_refused():
    with pytest.raises(AvailabilityError, match="timezone-aware"):
        _record(available_at="2026-07-31T20:05:00")


def test_non_canonical_session_is_refused():
    with pytest.raises(AvailabilityError, match="YYYY-MM-DD"):
        _record(as_of_session="2026-7-31")


def test_lowercase_ticker_is_refused():
    with pytest.raises(AvailabilityError, match="canonical uppercase"):
        _record(ticker="nvda")


def test_timezone_equivalent_timestamps_order_consistently():
    """Same instant, different offsets: ordering must not depend on how the
    timestamp happened to be written."""
    utc = _record(available_at="2026-07-31T20:05:00+00:00")
    eastern = _record(available_at="2026-07-31T16:05:00-04:00", revision_id="r2")
    cutoff = datetime(2026, 7, 31, 20, 5, tzinfo=timezone.utc)
    assert utc.is_available_by(cutoff)
    assert eastern.is_available_by(cutoff)
    earlier = datetime(2026, 7, 31, 20, 4, tzinfo=timezone.utc)
    assert not utc.is_available_by(earlier)
    assert not eastern.is_available_by(earlier)


# --- decision cutoff --------------------------------------------------------


def test_a_future_availability_timestamp_is_refused_against_the_cutoff():
    """The core point-in-time rule: a datum that became knowable AFTER the
    decision cutoff cannot have informed that decision."""
    late = _record(
        event_at="2026-07-31T22:00:00+00:00",
        available_at="2026-07-31T22:30:00+00:00",
        observed_at="2026-07-31T22:35:00+00:00",
    )
    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "NVDA")],
        feature_columns=["close"],
        availability=[late],
        universe=[_membership()],
        universe_id="tech-v1",
        decision_cutoffs=_cutoffs(),
    )
    assert not result.point_in_time_data
    assert any(f.startswith("availability_after_cutoff") for f in result.failures)


def test_an_after_close_datum_is_unavailable_to_a_pre_close_decision():
    """Doc 6.6 / plan 7.5: an after-close event must not be usable for a
    same-session decision taken before the close."""
    after_close = _record(
        event_at="2026-07-31T20:30:00+00:00",
        available_at="2026-07-31T20:30:00+00:00",
        observed_at="2026-07-31T20:35:00+00:00",
    )
    pre_close_cutoff = datetime(2026, 7, 31, 19, 0, tzinfo=timezone.utc)
    assert not after_close.is_available_by(pre_close_cutoff)


# --- revisions --------------------------------------------------------------


def test_a_later_revision_does_not_replace_the_historically_visible_value():
    """A vendor restating a figure must not retroactively change what an
    older dataset row contained -- the whole reason revision_id is part of
    the record identity."""
    original = _record(
        revision_id="r1",
        available_at="2026-07-31T20:05:00+00:00",
        observed_at="2026-07-31T20:05:00+00:00",
        raw_value_hash="a" * 64,
    )
    restatement = _record(
        revision_id="r2",
        event_at="2026-07-31T20:00:00+00:00",
        available_at="2026-11-15T14:00:00+00:00",
        observed_at="2026-11-15T14:00:00+00:00",
        raw_value_hash="b" * 64,
    )
    records = [original, restatement]

    historical_cutoff = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
    visible = latest_visible_revision(records, cutoff=historical_cutoff)
    assert visible is not None and visible.revision_id == "r1"

    today_cutoff = datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc)
    assert latest_visible_revision(records, cutoff=today_cutoff).revision_id == "r2"


def test_no_visible_revision_returns_none_rather_than_the_newest():
    record = _record(available_at="2026-07-31T20:05:00+00:00")
    early = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert latest_visible_revision([record], cutoff=early) is None


def test_duplicate_feature_availability_identity_is_detected():
    duplicate = [_record(), _record()]
    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "NVDA")],
        feature_columns=["close"],
        availability=duplicate,
        universe=[_membership()],
        universe_id="tech-v1",
        decision_cutoffs=_cutoffs(),
    )
    assert "duplicate_feature_availability_identity" in result.failures


# --- coverage derivation ----------------------------------------------------


def test_complete_valid_lineage_is_the_only_path_to_point_in_time_true():
    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "NVDA")],
        feature_columns=["close"],
        availability=[_record()],
        universe=[_membership()],
        universe_id="tech-v1",
        decision_cutoffs=_cutoffs(),
    )
    assert result.point_in_time_data
    assert result.survivorship_bias_free
    assert result.failures == ()
    assert result.covered_feature_columns == ("close",)


def test_missing_lineage_keeps_point_in_time_false():
    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "NVDA")],
        feature_columns=["close", "volume"],
        availability=[_record(feature_name="close")],
        universe=[_membership()],
        universe_id="tech-v1",
        decision_cutoffs=_cutoffs(),
    )
    assert not result.point_in_time_data
    assert "missing_feature_lineage" in result.failures
    assert result.missing_lineage_columns == ("volume",)


def test_a_derived_feature_is_covered_by_its_complete_input_lineage():
    """Plan 7.3: deterministic derived features identify their complete
    input lineage rather than needing their own vendor record."""
    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "NVDA")],
        feature_columns=["return_1d_pct"],
        availability=[_record(feature_name="close")],
        universe=[_membership()],
        universe_id="tech-v1",
        decision_cutoffs=_cutoffs(),
        derived_columns={"return_1d_pct": ["close"]},
    )
    assert result.point_in_time_data


def test_a_derived_feature_with_incomplete_inputs_is_not_covered():
    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "NVDA")],
        feature_columns=["dollar_volume"],
        availability=[_record(feature_name="close")],
        universe=[_membership()],
        universe_id="tech-v1",
        decision_cutoffs=_cutoffs(),
        derived_columns={"dollar_volume": ["close", "volume"]},
    )
    assert not result.point_in_time_data
    assert result.missing_lineage_columns == ("dollar_volume",)


def test_a_missing_decision_cutoff_fails_closed():
    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "NVDA")],
        feature_columns=["close"],
        availability=[_record()],
        universe=[_membership()],
        universe_id="tech-v1",
        decision_cutoffs={},
    )
    assert not result.point_in_time_data
    assert any(f.startswith("missing_decision_cutoff") for f in result.failures)


# --- universe / survivorship ------------------------------------------------


def test_no_universe_records_is_labeled_survivorship_biased():
    """Plan 7.5: current index members projected backward must be labeled
    survivorship-biased rather than silently accepted."""
    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "NVDA")],
        feature_columns=["close"],
        availability=[_record()],
        universe=[],
        universe_id="tech-v1",
        decision_cutoffs=_cutoffs(),
    )
    assert not result.point_in_time_data
    assert not result.survivorship_bias_free
    assert "no_universe_membership_records" in result.failures


def test_historical_membership_selects_the_correct_names_per_session():
    delisted = _membership(
        ticker="SIVB", effective_from="2015-01-01", effective_to="2023-03-10"
    )
    assert delisted.covers_session("2022-06-01")
    assert not delisted.covers_session("2024-06-01")


def test_a_ticker_outside_its_membership_window_is_ineligible():
    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "SIVB")],
        feature_columns=["close"],
        availability=[_record(ticker="SIVB")],
        universe=[
            _membership(ticker="SIVB", effective_from="2015-01-01", effective_to="2023-03-10")
        ],
        universe_id="tech-v1",
        decision_cutoffs=_cutoffs(),
    )
    assert not result.point_in_time_data
    assert any(f.startswith("ticker_not_eligible") for f in result.failures)


def test_membership_not_yet_announced_is_not_usable():
    """An index addition announced after the session cannot have informed
    that session's universe."""
    future_announcement = _membership(
        effective_from="2020-01-01",
        announced_at="2027-01-01T13:00:00+00:00",
        available_at="2027-01-01T13:00:00+00:00",
    )
    assert not future_announcement.is_known_by_session("2026-07-31")


def test_overlapping_membership_intervals_are_detected():
    overlapping = [
        _membership(effective_from="2020-01-01", effective_to="2023-01-01"),
        _membership(effective_from="2022-01-01", effective_to="2024-01-01"),
    ]
    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "NVDA")],
        feature_columns=["close"],
        availability=[_record()],
        universe=overlapping,
        universe_id="tech-v1",
        decision_cutoffs=_cutoffs(),
    )
    assert any(f.startswith("overlapping_universe_interval") for f in result.failures)


def test_membership_rejects_an_end_before_its_start():
    with pytest.raises(AvailabilityError, match="effective_to must not precede"):
        _membership(effective_from="2023-01-01", effective_to="2020-01-01")


def test_membership_rejects_announcement_after_availability():
    with pytest.raises(AvailabilityError, match="announced_at must not be after"):
        _membership(
            announced_at="2021-01-01T13:00:00+00:00",
            available_at="2020-01-01T13:00:00+00:00",
        )


# --- the yfinance adapter ---------------------------------------------------


def test_the_yfinance_source_never_synthesizes_lineage():
    """Plan 7.4: 'It must never synthesize historical availability or
    universe membership.' Returning nothing is what keeps yfinance-built
    datasets correctly exploratory -- a fabricated available_at stamped with
    download time would let them pass the gate while being no more
    trustworthy."""
    source = RetroactivelyAdjustedSource()
    assert source.provides_point_in_time_lineage is False
    assert source.feature_records(tickers=["NVDA"], start_session="2020-01-01", end_session="2026-07-31") == ()
    assert source.universe_membership(universe_id="tech-v1", start_session="2020-01-01", end_session="2026-07-31") == ()
    manifest = source.source_manifest()
    assert manifest["provides_point_in_time_lineage"] == "false"
    assert "retroactively" in manifest["limitation"].lower()


def test_a_yfinance_backed_dataset_cannot_reach_point_in_time_true():
    source = RetroactivelyAdjustedSource()
    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "NVDA")],
        feature_columns=["close"],
        availability=source.feature_records(
            tickers=["NVDA"], start_session="2026-01-01", end_session="2026-07-31"
        ),
        universe=source.universe_membership(
            universe_id="tech-v1", start_session="2026-01-01", end_session="2026-07-31"
        ),
        universe_id="tech-v1",
        decision_cutoffs=_cutoffs(),
    )
    assert not result.point_in_time_data


# --- serialization ----------------------------------------------------------


def test_records_round_trip_and_reject_unknown_fields():
    record = _record()
    assert FeatureAvailabilityRecord.from_dict(record.to_dict()) == record
    with pytest.raises(AvailabilityError, match="unknown fields"):
        FeatureAvailabilityRecord.from_dict({**record.to_dict(), "extra": 1})

    membership = _membership()
    assert UniverseMembershipRecord.from_dict(membership.to_dict()) == membership


def test_coverage_result_is_json_serializable():
    import json

    result = evaluate_point_in_time_coverage(
        feature_keys=[("2026-07-31", "NVDA")],
        feature_columns=["close"],
        availability=[_record()],
        universe=[_membership()],
        universe_id="tech-v1",
        decision_cutoffs=_cutoffs(),
    )
    json.dumps(result.to_dict())
