from __future__ import annotations

import dataclasses
import types
from datetime import date

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_terminal_disposition as subject,
    formal_streaming_input as formal_streaming,
)
from research.analyst_revisions_v2_qc.accepted_risk_security_master_admission import (
    build_accepted_risk_security_master_admission,
    iter_accepted_risk_security_master_mappings,
)
from research.analyst_revisions_v2_qc.formal_input_composer import _axis
from research.analyst_revisions_v2_qc.physical_preopen_seed_archive import (
    _build_physical_preopen_seed_archive_for_test,
)
from tests.analyst_revisions_v2.test_physical_preopen_seed_archive import _sources


@pytest.fixture(scope="module")
def admission_context(tmp_path_factory):
    root = tmp_path_factory.mktemp("accepted-risk-terminal-disposition")
    _massive, c1, sharadar = _sources(root)
    seed = _build_physical_preopen_seed_archive_for_test(
        c1, sharadar, root / "preopen-seed"
    )
    admission = build_accepted_risk_security_master_admission(seed)
    mapping = next(iter_accepted_risk_security_master_mappings(admission))
    return seed, admission, mapping


def _sessions(year: int) -> tuple[date, date]:
    axis, _ = _axis()
    candidates = [item for item in axis if item.year == year]
    assert len(candidates) >= 2
    return candidates[0], candidates[1]


def _begin(admission_context):
    _seed, admission, mapping = admission_context
    recorder = subject.begin_accepted_risk_terminal_disposition_recording(
        security_master_admission=admission
    )
    return recorder, mapping


def _record_daily(recorder, security_id: str, year: int, suffix: str):
    first, last = _sessions(year)
    subject.record_accepted_risk_terminal_security(
        recorder, security_id=security_id
    )
    subject.record_accepted_risk_terminal_slot(
        recorder,
        slot_kind="economic_daily",
        slot_id="slot-" + suffix,
        horizon_sessions=None,
        security_id=security_id,
        first_session=first,
        last_session=last,
    )


def test_fully_covered_snapshot_interval_is_unaffected_but_never_reviewed(
    admission_context,
):
    recorder, mapping = _begin(admission_context)
    _record_daily(recorder, str(mapping["security_id"]), 2021, "covered")

    build = subject.finalize_accepted_risk_terminal_disposition_recording(
        recorder=recorder, calculation_as_of_date=date(2026, 9, 14)
    )

    assert build.actual_slot_count == 1
    assert build.unaffected_slot_count == 1
    assert build.terminal_requirement_count == 0
    assert build.terminal_package.rows == ()
    assert build.point_in_time is False
    assert build.independently_reviewed is False
    assert build.reviewed_lifecycle_authority is False
    assert build.owner_accepted_current_snapshot_risk is True
    assert build.terminal_payoff_source_available is False
    assert build.terminal_payoff_inferred is False
    assert subject.require_accepted_risk_terminal_disposition_build(build) is build


def test_security_unavailable_is_one_distinct_named_refusal(admission_context):
    recorder, _mapping = _begin(admission_context)
    _record_daily(recorder, "security-absent-from-admission", 2021, "unavailable")
    build = subject.finalize_accepted_risk_terminal_disposition_recording(
        recorder=recorder, calculation_as_of_date=date(2026, 9, 14)
    )

    assert build.security_unavailable_refusal_count == 1
    assert [item.reason for item in build.terminal_package.rows] == [
        subject.OwnerAcceptedTerminalRefusalReason.SECURITY_UNAVAILABLE.value
    ]


def test_identity_refusal_is_one_distinct_named_refusal(admission_context):
    recorder, mapping = _begin(admission_context)
    state = subject._RECORDERS[id(recorder)]
    security = "security-with-ambiguous-or-ticker-reuse-identity"
    state.connection.execute(
        "INSERT INTO source_security VALUES (?,?,?,?,?,?)",
        (security, "identity_refused", None, None, mapping["source_row_sha256"],
         '["ambiguous_ticker_mapping"]'),
    )
    _record_daily(recorder, security, 2021, "identity-refused")
    build = subject.finalize_accepted_risk_terminal_disposition_recording(
        recorder=recorder, calculation_as_of_date=date(2026, 9, 14)
    )

    assert build.identity_refused_count == 1
    assert [item.reason for item in build.terminal_package.rows] == [
        subject.OwnerAcceptedTerminalRefusalReason.IDENTITY_REFUSED.value
    ]


def test_interval_not_covering_complete_slot_is_one_distinct_named_refusal(
    admission_context,
):
    recorder, mapping = _begin(admission_context)
    _record_daily(recorder, str(mapping["security_id"]), 2026, "uncovered")
    build = subject.finalize_accepted_risk_terminal_disposition_recording(
        recorder=recorder, calculation_as_of_date=date(2026, 9, 14)
    )

    assert build.interval_not_covered_refusal_count == 1
    assert [item.reason for item in build.terminal_package.rows] == [
        subject.OwnerAcceptedTerminalRefusalReason.INTERVAL_DOES_NOT_COVER_SLOT.value
    ]


def test_slot_requires_recorded_security(admission_context):
    recorder, mapping = _begin(admission_context)
    first, last = _sessions(2021)
    with pytest.raises(
        subject.AcceptedRiskTerminalDispositionError,
        match="slot security was not recorded",
    ):
        subject.record_accepted_risk_terminal_slot(
            recorder,
            slot_kind="economic_daily",
            slot_id="slot-unrecorded",
            horizon_sessions=None,
            security_id=str(mapping["security_id"]),
            first_session=first,
            last_session=last,
        )


def test_conflicting_duplicate_slot_geometry_isolated(admission_context):
    recorder, mapping = _begin(admission_context)
    security = str(mapping["security_id"])
    axis, _ = _axis()
    sessions = [item for item in axis if item.year == 2021][:3]
    subject.record_accepted_risk_terminal_security(recorder, security_id=security)
    assert subject.record_accepted_risk_terminal_slot(
        recorder,
        slot_kind="economic_daily",
        slot_id="slot-duplicate",
        horizon_sessions=None,
        security_id=security,
        first_session=sessions[0],
        last_session=sessions[1],
    ) is True
    assert subject.record_accepted_risk_terminal_slot(
        recorder,
        slot_kind="economic_daily",
        slot_id="slot-duplicate",
        horizon_sessions=None,
        security_id=security,
        first_session=sessions[0],
        last_session=sessions[1],
    ) is False
    with pytest.raises(
        subject.AcceptedRiskTerminalDispositionError,
        match="repeated with conflicting geometry",
    ):
        subject.record_accepted_risk_terminal_slot(
            recorder,
            slot_kind="economic_daily",
            slot_id="slot-duplicate",
            horizon_sessions=None,
            security_id=security,
            first_session=sessions[1],
            last_session=sessions[2],
        )


def test_current_snapshot_after_calculation_date_cannot_be_backdated(
    admission_context,
):
    recorder, mapping = _begin(admission_context)
    _record_daily(recorder, str(mapping["security_id"]), 2021, "late-snapshot")
    with pytest.raises(
        subject.AcceptedRiskTerminalDispositionError,
        match="evidence was unavailable by calculation date",
    ):
        subject.finalize_accepted_risk_terminal_disposition_recording(
            recorder=recorder, calculation_as_of_date=date(2025, 12, 31)
        )


def test_build_risk_disclosure_mutation_is_refused(admission_context):
    recorder, mapping = _begin(admission_context)
    _record_daily(recorder, str(mapping["security_id"]), 2021, "mutated")
    build = subject.finalize_accepted_risk_terminal_disposition_recording(
        recorder=recorder, calculation_as_of_date=date(2026, 9, 14)
    )
    object.__setattr__(build, "reviewed_lifecycle_authority", True)
    with pytest.raises(
        subject.AcceptedRiskTerminalDispositionError,
        match="not current process authority",
    ):
        subject.require_accepted_risk_terminal_disposition_build(build)


@pytest.mark.parametrize("retained", ([], [object(), object()]))
def test_formal_candidate_requires_exactly_one_distinct_accepted_risk_build(
    monkeypatch, retained,
):
    monkeypatch.setattr(
        formal_streaming,
        "require_accepted_risk_terminal_disposition_build",
        lambda value: value,
    )
    candidate = types.SimpleNamespace(terminal_build=None, terminal_package=object())

    with pytest.raises(
        formal_streaming.FormalStreamingInputError,
        match="owner-accepted terminal build was not retained exactly once",
    ):
        formal_streaming._require_owner_accepted_terminal_candidate_pair(
            candidate, retained
        )


@pytest.mark.parametrize(
    "candidate_has_reviewed_build,package_matches,reviewed,preliminary",
    (
        (True, True, False, True),
        (False, False, False, True),
        (False, True, True, True),
        (False, True, False, False),
    ),
)
def test_formal_candidate_cannot_relabel_owner_risk_as_reviewed_lifecycle(
    monkeypatch,
    candidate_has_reviewed_build,
    package_matches,
    reviewed,
    preliminary,
):
    package = object()
    build = types.SimpleNamespace(
        terminal_package=package,
        reviewed_lifecycle_authority=reviewed,
        preliminary_evaluation_only=preliminary,
    )
    monkeypatch.setattr(
        formal_streaming,
        "require_accepted_risk_terminal_disposition_build",
        lambda value: value,
    )
    candidate = types.SimpleNamespace(
        terminal_build=object() if candidate_has_reviewed_build else None,
        terminal_package=package if package_matches else object(),
    )

    with pytest.raises(
        formal_streaming.FormalStreamingInputError,
        match="owner-accepted terminal build was mislabeled as reviewed lifecycle",
    ):
        formal_streaming._require_owner_accepted_terminal_candidate_pair(
            candidate, [build]
        )


def test_formal_candidate_returns_authenticated_owner_risk_build(monkeypatch):
    package = object()
    build = types.SimpleNamespace(
        terminal_package=package,
        reviewed_lifecycle_authority=False,
        preliminary_evaluation_only=True,
    )
    monkeypatch.setattr(
        formal_streaming,
        "require_accepted_risk_terminal_disposition_build",
        lambda value: value,
    )
    candidate = types.SimpleNamespace(terminal_build=None, terminal_package=package)

    assert formal_streaming._require_owner_accepted_terminal_candidate_pair(
        candidate, [build]
    ) is build
