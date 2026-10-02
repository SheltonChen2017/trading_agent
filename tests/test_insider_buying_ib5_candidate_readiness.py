"""Synthetic-only dangerous-direction tests for the unregistered IB-5 candidate."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from fractions import Fraction

import pytest

from research.insider_buying.ib5_candidate_readiness import (
    IB5_CANDIDATE_POLICY,
    IB5_PARENT_GATE_SHA256,
    IB5_STOCK_LOOK_ID_CANDIDATE,
    Ib5CallerDeclaredInputs,
    Ib5CandidateError,
    assess_ib5_candidate_inputs,
)
from research.insider_buying.preregistration import (
    INSIDER_BUYING_RESEARCH_GATE,
    INSIDER_BUYING_RESEARCH_GATE_SHA256,
)


def _complete_synthetic_declarations() -> Ib5CallerDeclaredInputs:
    # Every identity and digest here is invented, not a source or rights claim.
    return Ib5CallerDeclaredInputs(
        outcome_dataset_id="synthetic-equity-total-return",
        outcome_vintage_id="synthetic-vintage-001",
        outcome_manifest_sha256="a" * 64,
        outcome_rights_artifact_id="synthetic-rights-record",
        outcome_rights_artifact_sha256="b" * 64,
        outcome_first_session=date(2006, 1, 3),
        outcome_last_session=date(2026, 9, 25),
        pit_security_master_id="synthetic-security-master",
        pit_security_master_sha256="c" * 64,
        pit_calendar_id="synthetic-calendar",
        pit_calendar_sha256="d" * 64,
        delisting_return_semantics_id="synthetic-terminal-return-rules",
        delisting_return_semantics_sha256="e" * 64,
        adjustment_semantics_id="synthetic-asof-split-dividend-rules",
        adjustment_semantics_sha256="f" * 64,
        immutable_signal_manifest_id="synthetic-signal-epoch",
        immutable_signal_manifest_sha256="1" * 64,
        qc_processing_entitlement_id="synthetic-qc-processing-rights",
        qc_processing_entitlement_sha256="2" * 64,
    )


def test_policy_freezes_delegated_choices_without_spending_alpha_or_a_look() -> None:
    policy = IB5_CANDIDATE_POLICY
    gate = INSIDER_BUYING_RESEARCH_GATE
    assert policy.parent_gate_sha256 == IB5_PARENT_GATE_SHA256
    assert policy.parent_gate_sha256 == INSIDER_BUYING_RESEARCH_GATE_SHA256
    assert policy.stock_primary_horizon_sessions == 20
    assert policy.descriptive_horizons_sessions == (5, 60)
    assert policy.stock_confirmatory_alpha == Fraction(1, 160)
    assert policy.etf_alpha_reserve == Fraction(1, 160)
    assert policy.stock_confirmatory_alpha + policy.etf_alpha_reserve == (
        gate.permanent_lane_alpha_maximum
    )
    assert gate.permanent_lane_alpha_maximum == Fraction(1, 80)
    assert policy.alpha_spent == Fraction(0, 1)
    assert policy.etf_cell_executable is False
    assert policy.valid_stock_null_closes_family is True
    assert policy.etf_can_rescue_stock_null is False
    assert policy.qc_can_rescue_stock_null is False
    assert policy.shared_cutoff == date(2027, 8, 31)
    assert policy.holdout_start == date(2027, 9, 1)
    assert policy.holdout_end == date(2029, 8, 31)
    assert policy.stock_look_id_candidate == IB5_STOCK_LOOK_ID_CANDIDATE
    assert policy.to_payload()["stock_look_registered"] is False
    assert len(policy.semantic_sha256) == 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("stock_primary_horizon_sessions", 5),
        ("stock_primary_horizon_sessions", 20.0),
        ("descriptive_horizons_sessions", (5, 20)),
        ("stock_confirmatory_alpha", Fraction(1, 80)),
        ("stock_confirmatory_alpha", 1 / 160),
        ("etf_alpha_reserve", Fraction(0, 1)),
        ("alpha_spent", Fraction(1, 160)),
        ("etf_cell_executable", True),
        ("valid_stock_null_closes_family", False),
        ("etf_can_rescue_stock_null", True),
        ("qc_can_rescue_stock_null", True),
        ("shared_cutoff", date(2029, 8, 31)),
        ("stock_look_id_candidate", "registered-look"),
    ],
)
def test_policy_mutations_refuse(field: str, value: object) -> None:
    with pytest.raises(Ib5CandidateError, match="REFUSED: candidate"):
        replace(IB5_CANDIDATE_POLICY, **{field: value})


def test_empty_inputs_name_all_missing_evidence_and_keep_authority_zero() -> None:
    report = assess_ib5_candidate_inputs(Ib5CallerDeclaredInputs())
    assert report.caller_declarations_complete is False
    assert "missing_outcome_dataset_id" in report.blockers
    assert "missing_outcome_vintage_id" in report.blockers
    assert "missing_outcome_manifest_sha256" in report.blockers
    assert "missing_outcome_rights_artifact_sha256" in report.blockers
    assert "missing_pit_security_master_sha256" in report.blockers
    assert "missing_pit_calendar_sha256" in report.blockers
    assert "missing_delisting_return_semantics_sha256" in report.blockers
    assert "missing_adjustment_semantics_sha256" in report.blockers
    assert "missing_immutable_signal_manifest_sha256" in report.blockers
    assert "missing_qc_processing_entitlement_sha256" in report.blockers
    assert "missing_outcome_first_session" in report.blockers
    assert "missing_outcome_last_session" in report.blockers
    assert report.authorized_outcome_looks == 0
    assert report.consumed_outcome_looks == 0
    assert report.real_study_ready is False
    assert report.qc_parity_ready is False


def test_complete_synthetic_declarations_never_grant_real_authority() -> None:
    report = assess_ib5_candidate_inputs(_complete_synthetic_declarations())
    assert report.blockers == ()
    assert report.caller_declarations_complete is True
    assert report.source_evidence_independently_verified is False
    assert report.stock_look_registered is False
    assert report.authorized_outcome_looks == 0
    assert report.consumed_outcome_looks == 0
    assert report.outcome_access_authorized is False
    assert report.qc_processing_authorized is False
    assert report.qc_job_authorized is False
    assert report.real_study_ready is False
    assert report.qc_parity_ready is False
    assert report.to_payload()["real_study_ready"] is False
    assert report.semantic_sha256 == (
        assess_ib5_candidate_inputs(_complete_synthetic_declarations()).semantic_sha256
    )


@pytest.mark.parametrize(
    "field",
    (
        "outcome_dataset_id",
        "outcome_vintage_id",
        "outcome_manifest_sha256",
        "outcome_rights_artifact_id",
        "outcome_rights_artifact_sha256",
        "outcome_first_session",
        "outcome_last_session",
        "pit_security_master_id",
        "pit_security_master_sha256",
        "pit_calendar_id",
        "pit_calendar_sha256",
        "delisting_return_semantics_id",
        "delisting_return_semantics_sha256",
        "adjustment_semantics_id",
        "adjustment_semantics_sha256",
        "immutable_signal_manifest_id",
        "immutable_signal_manifest_sha256",
        "qc_processing_entitlement_id",
        "qc_processing_entitlement_sha256",
    ),
)
def test_each_required_declaration_has_its_own_blocker(field: str) -> None:
    inputs = replace(_complete_synthetic_declarations(), **{field: None})
    report = assess_ib5_candidate_inputs(inputs)
    assert report.caller_declarations_complete is False
    assert report.blockers == (f"missing_{field}",)
    assert report.real_study_ready is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("outcome_dataset_id", ""),
        ("outcome_vintage_id", " synthetic "),
        ("pit_calendar_id", "bad\nname"),
        ("outcome_manifest_sha256", "A" * 64),
        ("outcome_rights_artifact_sha256", "a" * 63),
        ("qc_processing_entitlement_sha256", 10),
        ("outcome_first_session", datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ],
)
def test_malformed_declarations_refuse_typed(field: str, value: object) -> None:
    with pytest.raises(Ib5CandidateError, match=f"REFUSED: {field}"):
        replace(_complete_synthetic_declarations(), **{field: value})


@pytest.mark.parametrize(
    "first,last,expected",
    [
        (date(2026, 9, 26), date(2026, 9, 25), "outcome_window_reversed"),
        (
            date(2026, 9, 25),
            date(2027, 9, 1),
            "outcome_window_crosses_shared_cutoff",
        ),
        (
            date(2026, 9, 25),
            date(2029, 8, 31),
            "outcome_window_crosses_shared_cutoff",
        ),
    ],
)
def test_future_or_reversed_outcome_window_is_incomplete(
    first: date, last: date, expected: str
) -> None:
    inputs = replace(
        _complete_synthetic_declarations(),
        outcome_first_session=first,
        outcome_last_session=last,
    )
    report = assess_ib5_candidate_inputs(inputs)
    assert expected in report.blockers
    assert report.caller_declarations_complete is False
    assert report.real_study_ready is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_evidence_independently_verified", True),
        ("stock_look_registered", True),
        ("authorized_outcome_looks", 1),
        ("consumed_outcome_looks", 1),
        ("outcome_access_authorized", True),
        ("qc_processing_authorized", True),
        ("qc_job_authorized", True),
        ("real_study_ready", True),
        ("qc_parity_ready", True),
    ],
)
def test_report_cannot_be_promoted_by_replacement(field: str, value: object) -> None:
    report = assess_ib5_candidate_inputs(_complete_synthetic_declarations())
    with pytest.raises(Ib5CandidateError, match=f"REFUSED: {field}"):
        replace(report, **{field: value})


def test_report_replays_inputs_and_blockers_instead_of_trusting_caller() -> None:
    report = assess_ib5_candidate_inputs(_complete_synthetic_declarations())
    with pytest.raises(Ib5CandidateError, match="blockers drifted"):
        replace(report, inputs=Ib5CallerDeclaredInputs())
    with pytest.raises(Ib5CandidateError, match="completeness drifted"):
        replace(report, caller_declarations_complete=False)
    with pytest.raises(Ib5CandidateError, match="policy identity drifted"):
        replace(report, policy_sha256="a" * 64)
    with pytest.raises(Ib5CandidateError, match="exact declarations"):
        assess_ib5_candidate_inputs({})  # type: ignore[arg-type]


def test_direct_mutation_cannot_serialize_positive_authority() -> None:
    report = assess_ib5_candidate_inputs(Ib5CallerDeclaredInputs())
    object.__setattr__(report, "real_study_ready", True)
    with pytest.raises(Ib5CandidateError, match="real_study_ready"):
        report.to_payload()
