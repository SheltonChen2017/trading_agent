from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc.formal_run_protocol import (
    CLAIM_FILENAME,
    DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
    FORMAL_PRIMARY_FOLD_IDS,
    HORIZONS,
    OWNER_DECISION_ID,
    POWER_FEASIBLE_DISPOSITION,
    PRIMARY_HORIZON,
    SOURCE_VIEW_IDS,
    SUBMISSION_PERMIT_FILENAME,
    AcceptedRiskPairBinding,
    ArtifactBinding,
    FormalRunProtocolError,
    PowerFloorBinding,
    TerminalCensusBinding,
    begin_formal_submission_once,
    build_formal_run_candidate,
    claim_formal_run_once,
    formal_run_protocol_record,
    load_external_review_pin,
    load_reviewed_formal_run_authority,
    render_external_review_pin_candidate,
    render_formal_review_receipt_candidate,
    render_formal_run_candidate_bytes,
    require_formal_look_claim,
    require_formal_run_candidate,
    require_formal_submission_permit,
)


def _artifact(name: str, marker: str) -> ArtifactBinding:
    payload = (name + marker).encode()
    return ArtifactBinding(
        artifact_id=f"arv2-{name}-{marker}",
        content_sha256=hashlib.sha256(payload).hexdigest(),
        artifact_sha256=hashlib.sha256(payload + b"\n").hexdigest(),
        byte_count=len(payload),
    )


def _accepted_risk(**changes: object) -> AcceptedRiskPairBinding:
    values: dict[str, object] = {
        "pair": _artifact("accepted-risk-pair", "a"),
        "capture_id": "arv2-massive-capture-a",
        "capture_sha256": "1" * 64,
        "current_source_included_count": 100,
        "censored_source_included_count": 90,
        "current_admitted_decision_count": 80,
        "current_named_preoutcome_refusal_count": 20,
        "censored_admitted_decision_count": 72,
        "censored_named_preoutcome_refusal_count": 18,
        "guidance_admitted_count": 0,
        "pre_2013_admitted_count": 0,
        "pristine_point_in_time": False,
        "views_share_one_capture": True,
    }
    values.update(changes)
    return AcceptedRiskPairBinding(**values)


def _power(**changes: object) -> PowerFloorBinding:
    values: dict[str, object] = {
        "numeric_receipt": _artifact("numeric-power-receipt", "a"),
        "stock_successor": _artifact("stock-power-successor", "a"),
        "disposition": POWER_FEASIBLE_DISPOSITION,
        "required_valid_dates": 50,
        "observed_preoutcome_valid_dates": 60,
        "required_connected_components": 200,
        "observed_preoutcome_connected_components": 220,
        "h20_test_session_capacity": 1388,
        "preoutcome_candidate_date_count": 70,
        "valid_h20_test_session_count": 60,
        "refused_h20_test_session_count": 10,
        "missing_h20_test_session_count": 1318,
        "connected_component_instance_count": 220,
    }
    values.update(changes)
    return PowerFloorBinding(**values)


def _terminal(**changes: object) -> TerminalCensusBinding:
    values: dict[str, object] = {
        "census": _artifact("terminal-census", "a"),
        "terminal_policy_id": "arv2-terminal-payoff-benchmark-splice-v1",
        "security_count": 50,
        "lifecycle_coverage_count": 50,
        "terminal_requirement_count": 3,
        "terminal_payoff_count": 2,
        "benchmark_splice_continuation_count": 0,
        "named_terminal_refusal_count": 1,
        "silently_omitted_count": 0,
    }
    values.update(changes)
    return TerminalCensusBinding(**values)


def _candidate():
    return build_formal_run_candidate(
        code_projection=_artifact("code-projection", "a"),
        production_input_package=_artifact("production-input-package", "a"),
        current_view_partition_set=_artifact("current-partitions", "a"),
        censored_view_partition_set=_artifact("censored-partitions", "b"),
        accepted_risk=_accepted_risk(),
        power_floor=_power(),
        terminal_census=_terminal(),
    )


def _review_parameters(claim_directory: Path) -> dict[str, str]:
    return {
        "claude_review_commit": "a" * 40,
        "claude_review_evidence_sha256": "b" * 64,
        "codex_counterreview_commit": "c" * 40,
        "codex_counterreview_evidence_sha256": "d" * 64,
        "owner_outcome_authority_receipt_id": "arv2-owner-formal-outcome-authority-001",
        "claim_directory": str(claim_directory),
    }


def _activate(tmp_path: Path, candidate):
    directory = (tmp_path / "claim").absolute()
    directory.mkdir(mode=0o700)
    parameters = _review_parameters(directory)
    receipt = render_formal_review_receipt_candidate(candidate, **parameters)
    pin_bytes = render_external_review_pin_candidate(
        candidate=candidate,
        review_receipt_bytes=receipt,
        **parameters,
    )
    pin_path = (tmp_path / "external-review-pin.json").absolute()
    pin_path.write_bytes(pin_bytes)
    pin_path.chmod(0o600)
    pin = load_external_review_pin(candidate, pin_path)
    authority = load_reviewed_formal_run_authority(candidate, receipt, pin)
    return authority, directory, receipt, pin, pin_path


def test_candidate_freezes_one_execution_with_primary_and_sensitivity():
    candidate = _candidate()
    require_formal_run_candidate(candidate)
    document = json.loads(render_formal_run_candidate_bytes(candidate))
    assert candidate.formal_primary_fold_ids == FORMAL_PRIMARY_FOLD_IDS
    assert candidate.descriptive_sensitivity_fold_ids == DESCRIPTIVE_SENSITIVITY_FOLD_IDS
    assert candidate.source_view_ids == SOURCE_VIEW_IDS
    assert candidate.horizons == HORIZONS
    assert candidate.primary_horizon == PRIMARY_HORIZON == 20
    assert document["execution_geometry"]["single_execution"] is True
    assert document["execution_geometry"]["maximum_backtest_submissions"] == 1
    assert document["execution_geometry"]["retry_after_ambiguity"] is False
    assert document["owner_decision_id"] == OWNER_DECISION_ID
    assert candidate.launch_available is False
    assert candidate.result_access_available is False
    assert all(value is False for _name, value in candidate.capabilities)
    assert all(value is None for _name, value in candidate.external_bindings)


def test_formal_primary_cannot_be_relabelled_as_2021_only():
    candidate = _candidate()
    object.__setattr__(candidate, "formal_primary_fold_ids", DESCRIPTIVE_SENSITIVITY_FOLD_IDS)
    with pytest.raises(FormalRunProtocolError, match="changed"):
        require_formal_run_candidate(candidate)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"current_source_included_count": 0}, "empty"),
        ({"censored_source_included_count": 101}, "exceeds"),
        ({"current_admitted_decision_count": 79}, "exhaustive"),
        ({"censored_named_preoutcome_refusal_count": 17}, "exhaustive"),
        ({"guidance_admitted_count": 1}, "guidance"),
        ({"pre_2013_admitted_count": 1}, "pre-2013"),
        ({"pristine_point_in_time": True}, "pristine"),
        ({"views_share_one_capture": False}, "share one capture"),
    ],
)
def test_accepted_risk_binding_fails_closed(changes, message):
    with pytest.raises(FormalRunProtocolError, match=message):
        _accepted_risk(**changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"disposition": "UNDERPOWERED_FIXED_DESIGN_no_launch"}, "does not permit"),
        ({"observed_preoutcome_valid_dates": 49}, "valid-date floor"),
        ({"observed_preoutcome_connected_components": 199}, "connected-component floor"),
        ({"h20_test_session_capacity": 1387}, "does not reconcile"),
        ({"preoutcome_candidate_date_count": 69}, "does not reconcile"),
        ({"valid_h20_test_session_count": 59}, "does not reconcile"),
        ({"refused_h20_test_session_count": 9}, "does not reconcile"),
        ({"missing_h20_test_session_count": 1317}, "does not reconcile"),
        ({"connected_component_instance_count": 219}, "does not reconcile"),
    ],
)
def test_power_floor_is_a_hard_prelaunch_gate(changes, message):
    with pytest.raises(FormalRunProtocolError, match=message):
        _power(**changes)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"lifecycle_coverage_count": 49}, "not exhaustive"),
        ({"terminal_payoff_count": 1}, "benchmark-splice"),
        ({"named_terminal_refusal_count": 0}, "benchmark-splice"),
        ({"silently_omitted_count": 1}, "silently omitted"),
    ],
)
def test_terminal_census_requires_payoff_or_named_refusal(changes, message):
    with pytest.raises(FormalRunProtocolError, match=message):
        _terminal(**changes)


def test_terminal_census_counts_benchmark_splice_as_separate_accepted_policy():
    value = _terminal(
        terminal_payoff_count=2,
        benchmark_splice_continuation_count=1,
        named_terminal_refusal_count=0,
    )

    assert value.complete_payoffs is True
    assert value.to_record()["benchmark_splice_continuation_count"] == 1


def test_named_terminal_refusal_is_allowed_but_never_called_complete():
    assert _terminal().complete_payoffs is False
    assert _terminal(
        terminal_requirement_count=2,
        terminal_payoff_count=2,
        named_terminal_refusal_count=0,
    ).complete_payoffs is True


def test_current_and_censored_partition_sets_cannot_collapse():
    artifact = _artifact("partitions", "same")
    with pytest.raises(FormalRunProtocolError, match="collapsed"):
        build_formal_run_candidate(
            code_projection=_artifact("code", "a"),
            production_input_package=_artifact("input", "a"),
            current_view_partition_set=artifact,
            censored_view_partition_set=artifact,
            accepted_risk=_accepted_risk(),
            power_floor=_power(),
            terminal_census=_terminal(),
        )


def test_unreviewed_candidate_cannot_activate_or_spend(tmp_path: Path):
    candidate = _candidate()
    directory = (tmp_path / "claim").absolute()
    directory.mkdir(mode=0o700)
    with pytest.raises(FormalRunProtocolError, match="unavailable"):
        load_external_review_pin(candidate, (tmp_path / "missing.json").absolute())
    with pytest.raises(FormalRunProtocolError, match="authority"):
        claim_formal_run_once(
            candidate=candidate,
            authority=object(),
            claimed_at_utc="2026-09-12T00:00:00.000000Z",
        )
    assert not (directory / CLAIM_FILENAME).exists()


def test_review_receipt_is_content_addressed_and_candidate_bound(tmp_path: Path):
    first = _candidate()
    authority, _directory, receipt, pin, _pin_path = _activate(tmp_path, first)
    assert authority.candidate_id == first.candidate_id
    assert authority.maximum_submissions == 1
    assert authority.result_read_requires_separate_terminal_gate is True
    second = build_formal_run_candidate(
        code_projection=_artifact("code-projection", "changed"),
        production_input_package=first.production_input_package,
        current_view_partition_set=first.current_view_partition_set,
        censored_view_partition_set=first.censored_view_partition_set,
        accepted_risk=first.accepted_risk,
        power_floor=first.power_floor,
        terminal_census=first.terminal_census,
    )
    with pytest.raises(FormalRunProtocolError):
        load_reviewed_formal_run_authority(second, receipt, pin)


def test_duplicate_float_and_noncanonical_external_pins_refuse(tmp_path: Path):
    candidate = _candidate()
    _authority, _directory, _receipt, _pin, pin_path = _activate(tmp_path, candidate)
    canonical = pin_path.read_bytes()
    pin_path.write_bytes(canonical[:-2] + b',"maximum_submissions":1}\n')
    pin_path.chmod(0o600)
    with pytest.raises(FormalRunProtocolError, match="duplicate"):
        load_external_review_pin(candidate, pin_path)
    raw = json.loads(canonical)
    raw["maximum_submissions"] = 1.0
    pin_path.write_bytes(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    pin_path.chmod(0o600)
    with pytest.raises(FormalRunProtocolError, match="floats"):
        load_external_review_pin(candidate, pin_path)


def test_atomic_claim_and_submission_start_are_private_and_nonretryable(tmp_path: Path):
    candidate = _candidate()
    authority, directory, _receipt, _pin, _pin_path = _activate(tmp_path, candidate)
    claim = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-12T00:00:00.000000Z",
    )
    require_formal_look_claim(candidate, authority, claim)
    claim_payload = json.loads(claim.claim_path.read_bytes())
    assert claim_payload["status"] == "spent_before_submission"
    assert claim_payload["retry_authorized"] is False
    assert os.stat(claim.claim_path).st_mode & 0o077 == 0
    with pytest.raises(FormalRunProtocolError, match="already spent"):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-12T00:00:01.000000Z",
        )
    permit = begin_formal_submission_once(
        candidate=candidate,
        authority=authority,
        claim=claim,
        submission_started_at_utc="2026-09-12T00:00:02.000000Z",
    )
    require_formal_submission_permit(candidate, authority, claim, permit)
    permit_payload = json.loads(permit.permit_path.read_bytes())
    assert permit_payload["status"] == "submission_in_flight_look_consumed"
    assert permit_payload["ambiguous_submission_consumes_look"] is True
    assert permit_payload["retry_authorized"] is False
    assert permit.permit_path == directory / SUBMISSION_PERMIT_FILENAME
    with pytest.raises(FormalRunProtocolError, match="already spent"):
        begin_formal_submission_once(
            candidate=candidate,
            authority=authority,
            claim=claim,
            submission_started_at_utc="2026-09-12T00:00:03.000000Z",
        )


def test_authority_pins_one_ledger_namespace(tmp_path: Path):
    candidate = _candidate()
    authority, directory, _receipt, _pin, _pin_path = _activate(tmp_path, candidate)
    other = (tmp_path / "other-claim").absolute()
    other.mkdir(mode=0o700)
    forged = dataclasses.replace(authority, claim_directory=other)
    with pytest.raises(FormalRunProtocolError, match="authority changed"):
        claim_formal_run_once(
            candidate=candidate,
            authority=forged,
            claimed_at_utc="2026-09-12T00:00:00.000000Z",
        )
    claim = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-12T00:00:00.000000Z",
    )
    assert claim.claim_path.parent == directory
    assert not (other / CLAIM_FILENAME).exists()


def test_claim_directory_pin_and_nested_state_are_reauthenticated(tmp_path: Path):
    candidate = _candidate()
    authority, directory, _receipt, _pin, pin_path = _activate(tmp_path, candidate)
    directory.chmod(0o755)
    with pytest.raises(FormalRunProtocolError, match="private"):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-12T00:00:00.000000Z",
        )
    directory.chmod(0o700)
    pin_path.chmod(0o644)
    with pytest.raises(FormalRunProtocolError, match="private"):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-12T00:00:00.000000Z",
        )


def test_claim_and_candidate_mutations_are_detected(tmp_path: Path):
    candidate = _candidate()
    authority, _directory, _receipt, _pin, _pin_path = _activate(tmp_path, candidate)
    claim = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-12T00:00:00.000000Z",
    )
    claim.claim_path.write_bytes(b"{}\n")
    claim.claim_path.chmod(0o600)
    with pytest.raises(FormalRunProtocolError, match="changed"):
        require_formal_look_claim(candidate, authority, claim)
    object.__setattr__(candidate.accepted_risk, "guidance_admitted_count", 1)
    with pytest.raises(FormalRunProtocolError):
        require_formal_run_candidate(candidate)


def test_review_and_counterreview_must_be_distinct(tmp_path: Path):
    candidate = _candidate()
    directory = (tmp_path / "claim").absolute()
    directory.mkdir(mode=0o700)
    parameters = _review_parameters(directory)
    parameters["codex_counterreview_commit"] = parameters["claude_review_commit"]
    with pytest.raises(FormalRunProtocolError, match="must differ"):
        render_formal_review_receipt_candidate(candidate, **parameters)


def test_static_record_discloses_unreviewed_zero_authority():
    record = formal_run_protocol_record()
    assert record["reviewed_authority_artifact_sha256"] is None
    assert record["review_pin_is_external_owner_controlled"] is True
    assert record["maximum_submissions"] == 1
    assert record["retry_after_ambiguity"] is False
    assert record["result_read_requires_separate_terminal_gate"] is True


def test_exact_scalar_types_refuse_bool_counts():
    with pytest.raises(FormalRunProtocolError, match="integer census"):
        dataclasses.replace(_artifact("x", "a"), byte_count=True)
    with pytest.raises(FormalRunProtocolError, match="integer census"):
        _power(required_valid_dates=True)
    with pytest.raises(FormalRunProtocolError, match="integer census"):
        _power(h20_test_session_capacity=True)
