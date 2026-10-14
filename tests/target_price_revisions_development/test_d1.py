"""Pure D1 fixtures; no retained rows, exchange queries or outcome access.

The declared cutoff is a synthetic prior-session 18:00 New York evening.
Supplied holiday/DST opens are examples, not independently verified calendar
or public-availability evidence.
"""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError

import pytest

from research.target_price_revisions_development.events import (
    FixtureNormalizationError, normalize_fixture_events,
)

CUTOFF = "2026-10-05T18:00:00-04:00"
SESSIONS = (
    {"session_date": "2026-10-02", "open_utc": "2026-10-02T13:30:00Z"},
    {"session_date": "2026-10-05", "open_utc": "2026-10-05T13:30:00Z"},
    {"session_date": "2026-10-06", "open_utc": "2026-10-06T13:30:00Z"},
    {"session_date": "2026-10-07", "open_utc": "2026-10-07T13:30:00Z"},
)


def version(**changes):
    result = {
        "event_id": "SYNTHETIC-EVENT-A", "version_id": "SYNTHETIC-VERSION-1",
        "version_available_at_utc": "2026-10-05T16:00:00Z",
        "payload": {
            "effective_date": "2026-10-02", "public_precision": "instant",
            "public_available_at_utc": "2026-10-05T15:00:00Z",
            "public_available_date": None,
            "public_evidence_id": "SYNTHETIC-PUBLIC-EVIDENCE",
            "compatibility_evidence_id": "SYNTHETIC-COMPATIBILITY-EVIDENCE",
            "ingested_at_utc": "2026-10-05T16:10:00Z", "action": "raises",
            "new_target": "130.125", "prior_target": "100",
            "new_security_id": "SYNTHETIC-SECURITY-A", "prior_security_id": "SYNTHETIC-SECURITY-A",
            "new_share_class_id": "SYNTHETIC-CLASS-A", "prior_share_class_id": "SYNTHETIC-CLASS-A",
            "new_currency": "USD", "prior_currency": "USD",
            "new_horizon": "SYNTHETIC-12-MONTH", "prior_horizon": "SYNTHETIC-12-MONTH",
            "new_basis": "raw", "prior_basis": "raw",
            "new_adjustment_vintage": "SYNTHETIC-NO-ADJUSTMENT",
            "prior_adjustment_vintage": "SYNTHETIC-NO-ADJUSTMENT",
        },
    }
    result["payload"].update(changes)
    return result


def normalize(*versions, cutoff=CUTOFF, sessions=SESSIONS):
    return normalize_fixture_events(versions, decision_cutoff_utc=cutoff, sessions=sessions)


def only_reason(result):
    assert result.selected_events == ()
    assert len(result.dispositions) == 1
    assert result.dispositions[0].status == "refused"
    return result.dispositions[0].reasons


@pytest.mark.parametrize("action,new,prior,direction", [
    ("raises", "130.125", "100", 1), ("lowers", "99.999", "100", -1),
    ("maintains", "100", "100", 0),
    ("raises", "100.0000000000000000000000000001", "100", 1),
])
def test_eligible_fixture_preserves_exact_targets_and_has_zero_authority(action, new, prior, direction):
    result = normalize(version(action=action, new_target=new, prior_target=prior))
    event, = result.selected_events
    assert (event.new_target, event.prior_target, event.direction) == (new, prior, direction)
    assert event.eligible_open_utc == "2026-10-06T13:30:00+00:00"
    assert event.effective_date == "2026-10-02"
    assert event.public_available_at_utc == "2026-10-05T15:00:00+00:00"
    assert event.version_available_at_utc == "2026-10-05T16:00:00+00:00"
    assert event.ingested_at_utc == "2026-10-05T16:10:00+00:00"
    assert result.mode == "synthetic-fixture-only"
    assert result.authority == (("canonical_admission", False), ("point_in_time_data", False),
                                ("outcomes", False), ("qc", False), ("trading", False))
    assert result.dispositions[0].status == "selected"
    assert result.dispositions[0].reasons == (("valid_zero",) if direction == 0 else ())


@pytest.mark.parametrize("value,reason", [
    (None, "missing_new_target"), ("0", "zero_new_target"), ("-1", "negative_new_target"),
    ("NaN", "nonfinite_new_target"), ("Infinity", "nonfinite_new_target"),
    (True, "invalid_new_target"), (1.5, "invalid_new_target"),
    (" 100 ", "invalid_new_target"), ("1e1000000", "invalid_new_target"),
])
def test_invalid_targets_are_visible_refusals(value, reason):
    assert only_reason(normalize(version(new_target=value))) == (reason,)


def test_absent_target_field_has_a_named_refusal():
    row = version()
    row["payload"].pop("new_target")
    assert only_reason(normalize(row)) == ("missing_new_target",)


def test_initiation_with_prior_still_does_not_become_revision():
    result = normalize(version(action="sets"))
    disposition, = result.dispositions
    assert result.selected_events == ()
    assert (disposition.status, disposition.reasons) == ("ineligible", ("initiation_not_revision",))


@pytest.mark.parametrize("action,new,reason", [
    ("raises", "90", "action_direction_conflict"),
    ("lowers", "110", "action_direction_conflict"),
    ("maintains", "110", "action_direction_conflict"),
    ("sets", "110", "initiation_without_prior"),
    ("announces", "110", "initiation_without_prior"),
])
def test_action_and_initiation_dispositions(action, new, reason):
    prior = None if action in ("sets", "announces") else "100"
    result = normalize(version(action=action, new_target=new, prior_target=prior))
    assert result.selected_events == ()
    disposition, = result.dispositions
    assert disposition.status == ("ineligible" if action in ("sets", "announces") else "refused")
    assert disposition.reasons == (reason,)


@pytest.mark.parametrize("field,value,reason", [
    ("prior_security_id", "SYNTHETIC-OTHER", "security_identity_mismatch"),
    ("prior_share_class_id", "SYNTHETIC-OTHER", "share_class_mismatch"),
    ("prior_currency", "CAD", "currency_mismatch"),
    ("prior_horizon", "SYNTHETIC-OTHER", "horizon_mismatch"),
    ("new_horizon", None, "missing_horizon"),
    ("prior_basis", "adjusted", "basis_mismatch"),
    ("new_basis", "adjusted", "basis_mismatch"),
    ("prior_adjustment_vintage", "SYNTHETIC-OTHER", "adjustment_vintage_mismatch"),
    ("new_adjustment_vintage", None, "missing_adjustment_vintage"),
    ("public_evidence_id", None, "missing_public_evidence"),
    ("compatibility_evidence_id", None, "missing_compatibility_evidence"),
])
def test_unknown_or_incompatible_evidence_is_not_repaired(field, value, reason):
    assert only_reason(normalize(version(**{field: value}))) == (reason,)


def test_future_malformed_payload_is_screened_before_payload_validation():
    future = version()
    future.update(version_id="SYNTHETIC-VERSION-2", version_available_at_utc="2026-10-06T14:00:00Z", payload=object())
    result = normalize(version(), future)
    assert len(result.selected_events) == 1
    assert result.selected_events[0].version_id == "SYNTHETIC-VERSION-1"
    assert {d.status for d in result.dispositions} == {"selected", "not_visible"}


def test_latest_visible_correction_is_selected_without_backdating():
    correction = version(new_target="140")
    correction.update(version_id="SYNTHETIC-VERSION-2", version_available_at_utc="2026-10-05T20:00:00Z")
    correction["payload"].update(public_available_at_utc="2026-10-05T19:00:00Z", ingested_at_utc="2026-10-05T20:10:00Z")
    result = normalize(version(), correction)
    assert result.selected_events[0].new_target == "140"
    assert result.selected_events[0].eligible_open_utc == "2026-10-06T13:30:00+00:00"
    assert {d.status for d in result.dispositions} == {"selected", "superseded"}


@pytest.mark.parametrize("change,reason", [
    ({"action": "withdraws"}, "visible_withdrawal"),
    ({"new_target": None}, "missing_new_target"),
    ({"ingested_at_utc": "2026-10-06T01:00:00Z"}, "uncaptured_by_cutoff"),
    ({"public_available_at_utc": "2026-10-06T01:00:00Z"}, "public_unavailable_by_cutoff"),
])
def test_visible_latest_version_never_falls_back(change, reason):
    latest = version(ingested_at_utc="2026-10-05T20:10:00Z")
    latest["payload"].update(change)
    latest.update(version_id="SYNTHETIC-VERSION-2", version_available_at_utc="2026-10-05T20:00:00Z")
    result = normalize(version(), latest)
    assert result.selected_events == ()
    assert any(reason in d.reasons for d in result.dispositions)
    assert any(d.status == "superseded" for d in result.dispositions)


def test_exact_duplicates_account_and_input_order_does_not_matter():
    a, b = version(), version()
    b["event_id"] = "SYNTHETIC-EVENT-B"
    forward = normalize(a, copy.deepcopy(a), b)
    assert forward == normalize(b, a, copy.deepcopy(a))
    assert forward.input_versions == 3 and forward.duplicate_versions == 1
    assert sum(d.occurrences for d in forward.dispositions) == 3
    assert len(forward.selected_events) == 2


@pytest.mark.parametrize("same_version", [True, False])
def test_conflicting_version_or_availability_tie_refuses_lineage(same_version):
    conflicting = version(new_target="140")
    if not same_version:
        conflicting["version_id"] = "SYNTHETIC-VERSION-2"
    result = normalize(version(), conflicting)
    assert result.selected_events == ()
    assert all(d.reasons == ("lineage_conflict",) for d in result.dispositions)


def test_cutoff_open_equality_requires_strictly_later_open():
    cutoff = "2026-10-06T13:30:00Z"
    result = normalize(version(), cutoff=cutoff)
    assert result.selected_events[0].eligible_open_utc == "2026-10-07T13:30:00+00:00"


def test_date_only_second_open_skips_declared_weekend_and_holiday():
    sessions = (
        {"session_date": "2026-10-02", "open_utc": "2026-10-02T13:30:00Z"},
        {"session_date": "2026-10-06", "open_utc": "2026-10-06T13:30:00Z"},
        {"session_date": "2026-10-07", "open_utc": "2026-10-07T13:30:00Z"},
    )
    row = version(public_precision="date-only", public_available_at_utc=None, public_available_date="2026-10-02")
    result = normalize(row, sessions=sessions)
    assert result.selected_events[0].eligible_open_utc == "2026-10-07T13:30:00+00:00"


def test_declared_synthetic_dst_opens_and_prior_evening_cutoff():
    row = version(public_precision="date-only", public_available_at_utc=None, public_available_date="2026-10-30")
    row.update(version_available_at_utc="2026-10-30T20:00:00Z")
    row["payload"].update(ingested_at_utc="2026-10-30T20:05:00Z", effective_date="2026-10-30")
    sessions = (
        {"session_date": "2026-10-30", "open_utc": "2026-10-30T09:30:00-04:00"},
        {"session_date": "2026-11-02", "open_utc": "2026-11-02T09:30:00-05:00"},
        {"session_date": "2026-11-03", "open_utc": "2026-11-03T09:30:00-05:00"},
    )
    result = normalize(row, cutoff="2026-11-02T18:00:00-05:00", sessions=sessions)
    assert result.selected_events[0].eligible_open_utc == "2026-11-03T14:30:00+00:00"


def test_insufficient_calendar_is_a_named_refusal():
    assert only_reason(normalize(version(), sessions=SESSIONS[:2])) == ("insufficient_calendar",)


def test_caller_mutation_cannot_change_frozen_result():
    row, sessions = version(), list(copy.deepcopy(SESSIONS))
    result = normalize(row, sessions=sessions)
    row["payload"]["new_target"] = "999"
    sessions[2]["open_utc"] = "2026-10-06T23:00:00Z"
    assert result.selected_events[0].new_target == "130.125"
    with pytest.raises(FrozenInstanceError):
        result.selected_events[0].new_target = "999"


@pytest.mark.parametrize("clock", ["2026-10-05T22:00:00", None, True])
def test_invalid_cutoff_has_fixed_error(clock):
    with pytest.raises(FixtureNormalizationError, match="invalid synthetic clock"):
        normalize(version(), cutoff=clock)


def test_invalid_unsorted_calendar_is_refused():
    with pytest.raises(FixtureNormalizationError, match="invalid synthetic calendar"):
        normalize(version(), sessions=tuple(reversed(SESSIONS)))


def test_adjusted_pair_is_not_silently_used_as_raw_pair():
    assert only_reason(normalize(version(new_basis="adjusted", prior_basis="adjusted"))) == ("invalid_basis",)


def test_unknown_payload_field_is_a_fixed_refusal():
    row = version()
    row["payload"]["SYNTHETIC-PRIVATE-UNKNOWN"] = "SYNTHETIC-SECRET"
    assert only_reason(normalize(row)) == ("invalid_payload",)


@pytest.mark.parametrize("batch", [None, True, tuple(version() for _ in range(1025))])
def test_batch_type_and_resource_bounds_are_explicit(batch):
    with pytest.raises(FixtureNormalizationError, match="invalid synthetic version batch"):
        normalize_fixture_events(batch, decision_cutoff_utc=CUTOFF, sessions=SESSIONS)


def test_missing_version_clock_never_falls_back_to_older():
    broken = version()
    broken["version_available_at_utc"] = None
    with pytest.raises(FixtureNormalizationError, match="invalid synthetic clock"):
        normalize(version(), broken)


def test_unknown_matching_currency_code_is_not_an_admitted_fixture_unit():
    assert only_reason(normalize(version(new_currency="ZZZ", prior_currency="ZZZ"))) == ("invalid_currency",)


def test_capture_before_current_version_availability_is_not_eligible():
    # Conservative fixture ordering proposal, not established vendor semantics.
    assert only_reason(normalize(version(ingested_at_utc="2026-10-05T15:30:00Z"))) == ("contradictory_availability_clocks",)


@pytest.mark.parametrize("capture_day", ["2026-10-04", "2026-10-05"])
def test_date_only_public_day_cannot_follow_version_or_capture_day(capture_day):
    # This diagnostic explicitly declares UTC date semantics, not market facts.
    row = version(public_precision="date-only", public_available_at_utc=None,
                  public_available_date="2026-10-05", ingested_at_utc=capture_day + "T17:00:00Z")
    row["version_available_at_utc"] = "2026-10-04T16:00:00Z"
    assert only_reason(normalize(row)) == ("contradictory_availability_clocks",)


@pytest.mark.parametrize("action", ["sets", "announces"])
def test_initiation_without_prior_metadata_is_a_separate_ineligible_diagnostic(action):
    row = version(action=action, prior_target=None)
    for name in ("security_id", "share_class_id", "currency", "horizon", "basis", "adjustment_vintage"):
        row["payload"]["prior_" + name] = None
    result = normalize(row)
    assert result.selected_events == ()
    disposition, = result.dispositions
    assert (disposition.status, disposition.reasons) == ("ineligible", ("initiation_without_prior",))


def test_fixture_normalization_does_not_use_file_or_network_io(monkeypatch):
    import builtins
    import os
    import socket
    from pathlib import Path

    def forbidden(*args, **kwargs):
        raise AssertionError("fixture normalization attempted I/O")

    with monkeypatch.context() as isolated:
        isolated.setattr(builtins, "open", forbidden)
        isolated.setattr(os, "open", forbidden)
        isolated.setattr(socket, "socket", forbidden)
        for name in ("open", "read_bytes", "read_text"):
            isolated.setattr(Path, name, forbidden)
        result = normalize(version())
        assert len(result.selected_events) == 1
        assert all(value is False for _, value in result.authority)


def test_custom_visible_action_is_refused_without_invoking_caller_equality():
    class CustomAction:
        def __eq__(self, other):
            raise AssertionError("caller equality executed")

    assert only_reason(normalize(version(action=CustomAction()))) == ("invalid_payload",)


@pytest.mark.parametrize("framing", ["header", "calendar"])
def test_custom_framing_keys_are_rejected_before_caller_callbacks(framing):
    # Dict construction happens before arming. CPython may reuse cached hashes
    # in set(dict); the armed equality hook detects literal-set comparisons too.
    class CustomKey:
        armed = False

        def __init__(self, literal):
            self.literal = literal

        def __hash__(self):
            if self.armed:
                raise AssertionError("caller key hash executed")
            return hash(self.literal)

        def __eq__(self, other):
            if self.armed:
                raise AssertionError("caller key equality executed")
            return self.literal == other

    row, sessions = version(), list(copy.deepcopy(SESSIONS))
    key = CustomKey("payload" if framing == "header" else "open_utc")
    target = row if framing == "header" else sessions[0]
    target[key] = target.pop(key.literal)
    key.armed = True
    expected = "invalid synthetic version header" if framing == "header" else "invalid synthetic calendar"
    with pytest.raises(FixtureNormalizationError, match=expected):
        normalize(row, sessions=sessions)


# TPR-CR17-002: three guards the preceding suite left without a test. That
# suite stayed green when each guard was removed; each new case below turns
# red under its corresponding mutation.


def test_matching_but_malformed_horizon_is_not_a_comparable_horizon():
    assert only_reason(normalize(version(new_horizon="SYNTHETIC-OTHER", prior_horizon="SYNTHETIC-OTHER"))) == ("invalid_horizon",)


def test_public_instant_after_version_availability_is_contradictory():
    # Public availability later than the version we already hold is the
    # pre-release shape the conservative fixture ordering refuses.
    assert only_reason(normalize(version(public_available_at_utc="2026-10-05T16:05:00Z"))) == ("contradictory_availability_clocks",)


def test_unknown_key_in_place_of_the_optional_target_is_still_refused():
    row = version()
    row["payload"].pop("new_target")
    row["payload"]["SYNTHETIC-PRIVATE-UNKNOWN"] = "SYNTHETIC-SECRET"
    assert only_reason(normalize(row)) == ("invalid_payload",)
