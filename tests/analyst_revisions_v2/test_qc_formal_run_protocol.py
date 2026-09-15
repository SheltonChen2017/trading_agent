from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import types
from pathlib import Path

import pytest

from research.analyst_revisions_v2 import preregistration as look_accounting
from research.analyst_revisions_v2_qc import formal_run_protocol as protocol

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


OWNER_PLAN_ID = "arv2-streamed-formal-plan-test"
OWNER_PLAN_SHA256 = "a" * 64


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


def _activate_owner_review_waiver(tmp_path: Path, candidate):
    directory = (tmp_path / "waiver-claim").absolute()
    directory.mkdir(mode=0o700)
    owner_authority_id = "arv2-owner-waived-formal-execution-authority-test"
    receipt = protocol.render_formal_owner_review_waiver_receipt_candidate(
        candidate,
        owner_outcome_authority_receipt_id=owner_authority_id,
        claim_directory=str(directory),
    )
    pin_bytes = protocol.render_owner_review_waiver_external_pin_candidate(
        candidate=candidate,
        review_receipt_bytes=receipt,
        owner_outcome_authority_receipt_id=owner_authority_id,
        claim_directory=str(directory),
    )
    pin_path = (tmp_path / "owner-review-waiver-pin.json").absolute()
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
    authority, _directory, receipt, pin, pin_path = _activate(tmp_path, first)
    assert authority.candidate_id == first.candidate_id
    assert authority.maximum_submissions == 1
    assert authority.result_read_requires_separate_terminal_gate is True
    receipt_raw = json.loads(receipt)
    pin_raw = json.loads(pin_path.read_bytes())
    expected_ledger = look_accounting.load_infrastructure_look_ledger()
    for raw in (receipt_raw, pin_raw):
        assert raw["infrastructure_look_ledger_id"] == expected_ledger.ledger_id
        assert raw["infrastructure_look_ledger_hash"] == expected_ledger.ledger_hash
        assert raw["infrastructure_look_ledger_artifact_sha256"] == (
            expected_ledger.artifact_sha256
        )
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


def test_infrastructure_look_ledger_mutation_blocks_formal_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger_path = tmp_path / look_accounting.INFRASTRUCTURE_LOOK_LEDGER_FILENAME
    ledger_path.write_bytes(
        look_accounting.INFRASTRUCTURE_LOOK_LEDGER_PATH.read_bytes()
    )
    monkeypatch.setattr(
        look_accounting, "INFRASTRUCTURE_LOOK_LEDGER_PATH", ledger_path
    )
    candidate = _candidate()
    authority, directory, _receipt, _pin, _pin_path = _activate(tmp_path, candidate)

    ledger_path.write_bytes(b"{}\n")
    with pytest.raises(
        FormalRunProtocolError,
        match="infrastructure-look ledger reconciliation failed",
    ):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-12T00:00:00.000000Z",
        )
    assert not (directory / CLAIM_FILENAME).exists()


def test_external_pin_cannot_rebind_the_spent_infrastructure_look(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    _authority, _directory, _receipt, _pin, pin_path = _activate(
        tmp_path, candidate
    )
    raw = json.loads(pin_path.read_bytes())
    raw["infrastructure_look_ledger_artifact_sha256"] = "0" * 64
    raw["pin_id"] = None
    raw["pin_sha256"] = None
    digest = hashlib.sha256(protocol._canonical_bytes(raw)).hexdigest()
    raw["pin_sha256"] = digest
    raw["pin_id"] = f"arv2-formal-external-pin-{digest[:24]}"
    pin_path.write_bytes(protocol._canonical_bytes(raw))
    pin_path.chmod(0o600)

    with pytest.raises(FormalRunProtocolError, match="external review pin content changed"):
        load_external_review_pin(candidate, pin_path)


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


def test_owner_review_waiver_is_truthful_and_false_review_claim_refuses(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, directory, receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    raw = json.loads(receipt)
    assert raw["independent_review_complete"] is False
    assert raw["review_disposition"] == "NOT_PERFORMED_OWNER_WAIVED"
    assert raw["owner_review_waiver_scope"] == (
        "SECTION_72_THROUGH_FIRST_FORMAL_BACKTEST"
    )
    assert raw[
        "waiver_ends_after_first_technically_completed_formal_backtest"
    ] is True
    assert raw["post_first_formal_backtest_independent_review_required"] is True
    assert raw["result_read_requires_separate_terminal_gate"] is True
    assert raw["deployment_orders_trading_authorized"] is False
    assert "claude_review_commit" not in raw
    assert "codex_counterreview_commit" not in raw
    assert authority.claude_review_commit is None
    assert authority.codex_counterreview_commit is None

    falsely_reviewed = dataclasses.replace(
        authority,
        independent_review_complete=True,
    )
    with pytest.raises(FormalRunProtocolError, match="review authorization changed"):
        claim_formal_run_once(
            candidate=candidate,
            authority=falsely_reviewed,
            claimed_at_utc="2026-09-14T00:00:00.000000Z",
            attempt_ordinal=1,
            retry_lineage_sha256="e" * 64,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )
    assert list(directory.iterdir()) == []


def test_owner_review_waiver_tamper_refuses_before_attempt_is_spent(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, directory, _receipt, _pin, pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    raw = json.loads(pin_path.read_bytes())
    raw["owner_review_waiver_scope"] = "UNBOUNDED"
    raw["pin_id"] = None
    raw["pin_sha256"] = None
    digest = hashlib.sha256(protocol._canonical_bytes(raw)).hexdigest()
    raw["pin_sha256"] = digest
    raw["pin_id"] = f"arv2-formal-owner-waiver-pin-{digest[:24]}"
    pin_path.write_bytes(protocol._canonical_bytes(raw))
    pin_path.chmod(0o600)

    with pytest.raises(FormalRunProtocolError, match="external review pin content changed"):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:00.000000Z",
            attempt_ordinal=1,
            retry_lineage_sha256="e" * 64,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )
    assert list(directory.iterdir()) == []


def test_definite_pre_submission_failure_spends_no_outcome_and_allows_fresh_retry(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    lineage = "e" * 64
    first = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    failure = protocol.record_definite_pre_submission_failure(
        candidate=candidate,
        authority=authority,
        claim=first,
        phase="pre_qc_reauthentication",
        failure_class="FormalQcSubmissionError",
        recorded_at_utc="2026-09-14T00:00:01.000000Z",
    )
    protocol.require_definite_pre_submission_failure(
        candidate, authority, first, failure
    )
    failure_raw = json.loads(failure.failure_path.read_bytes())
    assert failure_raw["backtests_create_attempted"] is False
    assert failure_raw["outcome_look_consumed"] is False
    assert failure_raw["retry_with_fresh_attempt_authorized"] is True

    second = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:02.000000Z",
        attempt_ordinal=2,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    second_raw = json.loads(second.claim_path.read_bytes())
    assert second_raw["prior_attempt_count"] == 1
    assert second_raw["prior_no_outcome_failure_count"] == 1
    assert second_raw["prior_consumed_attempt_count"] == 0
    assert second_raw["outcome_look_consumed"] is False
    assert {path.name for path in directory.iterdir()} == {
        "arv2-formal-attempt-000001-claim.json",
        "arv2-formal-attempt-000001-definite-pre-submission-failure.json",
        "arv2-formal-attempt-000001.lock",
        "arv2-formal-attempt-000002-claim.json",
        "arv2-formal-attempt-000002.lock",
    }


def test_interruption_immediately_after_claim_publish_resumes_exact_open_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    candidate = _candidate()
    authority, directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    original_write = protocol._exclusive_private_write
    published: dict[str, bytes] = {}

    def interrupt_after_claim_publish(
        actual_directory: Path,
        filename: str,
        payload: bytes,
    ) -> Path:
        target = original_write(actual_directory, filename, payload)
        if filename == "arv2-formal-attempt-000001-claim.json":
            published["claim"] = target.read_bytes()
            raise RuntimeError("simulated interruption after claim publication")
        return target

    monkeypatch.setattr(
        protocol,
        "_exclusive_private_write",
        interrupt_after_claim_publish,
    )
    with pytest.raises(RuntimeError, match="after claim publication"):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:00.000000Z",
            attempt_ordinal=1,
            retry_lineage_sha256="e" * 64,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )
    monkeypatch.setattr(protocol, "_exclusive_private_write", original_write)

    resumed = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:09.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256="e" * 64,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    assert resumed.resumed_after_interruption is True
    assert resumed.claimed_at_utc == "2026-09-14T00:00:00.000000Z"
    assert resumed._claim_bytes == published["claim"]
    assert resumed.claim_path.read_bytes() == published["claim"]
    protocol.record_definite_pre_submission_failure(
        candidate=candidate,
        authority=authority,
        claim=resumed,
        phase="post_claim_process_interruption",
        failure_class="RuntimeError",
        recorded_at_utc="2026-09-14T00:00:10.000000Z",
    )
    assert not any(".pending-" in path.name for path in directory.iterdir())


def test_live_open_claim_cannot_be_concurrently_resumed(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, _directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    first = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256="e" * 64,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    original = first.claim_path.read_bytes()

    with pytest.raises(
        FormalRunProtocolError,
        match="active in another execution",
    ):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:01.000000Z",
            attempt_ordinal=1,
            retry_lineage_sha256="e" * 64,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )
    assert first.claim_path.read_bytes() == original
    protocol.record_definite_pre_submission_failure(
        candidate=candidate,
        authority=authority,
        claim=first,
        phase="concurrency_test_cleanup",
        failure_class="FormalRunProtocolError",
        recorded_at_utc="2026-09-14T00:00:02.000000Z",
    )


def test_interrupted_failure_write_retains_lease_then_resumes_after_process_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    candidate = _candidate()
    authority, directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    first = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256="e" * 64,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    original_os_write = protocol.os.write
    interrupted = False

    def interrupt_staging_write(descriptor: int, payload: bytes) -> int:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            original_os_write(descriptor, payload[: max(1, len(payload) // 2)])
            raise OSError("simulated process loss during failure write")
        return original_os_write(descriptor, payload)

    monkeypatch.setattr(protocol.os, "write", interrupt_staging_write)
    with pytest.raises(
        FormalRunProtocolError,
        match="staging write failed before publication",
    ):
        protocol.record_definite_pre_submission_failure(
            candidate=candidate,
            authority=authority,
            claim=first,
            phase="pre_qc_reauthentication",
            failure_class="FormalQcSubmissionError",
            recorded_at_utc="2026-09-14T00:00:01.000000Z",
        )
    monkeypatch.setattr(protocol.os, "write", original_os_write)
    assert not (
        directory
        / "arv2-formal-attempt-000001-definite-pre-submission-failure.json"
    ).exists()
    assert not any(".pending-" in path.name for path in directory.iterdir())
    with pytest.raises(
        FormalRunProtocolError,
        match="active in another execution",
    ):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:02.000000Z",
            attempt_ordinal=1,
            retry_lineage_sha256="e" * 64,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )

    protocol._release_retry_attempt_lock(first)
    resumed = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:03.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256="e" * 64,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    assert resumed.resumed_after_interruption is True
    failure = protocol.record_definite_pre_submission_failure(
        candidate=candidate,
        authority=authority,
        claim=resumed,
        phase="pre_qc_reauthentication",
        failure_class="FormalQcSubmissionError",
        recorded_at_utc="2026-09-14T00:00:04.000000Z",
    )
    protocol.require_definite_pre_submission_failure(
        candidate,
        authority,
        resumed,
        failure,
    )


def test_open_claim_resume_refuses_changed_plan_and_persisted_tamper(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, _directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    first = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256="e" * 64,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    original = first.claim_path.read_bytes()
    protocol._release_retry_attempt_lock(first)

    with pytest.raises(FormalRunProtocolError, match="changed lineage or plan"):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:01.000000Z",
            attempt_ordinal=1,
            retry_lineage_sha256="e" * 64,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256="b" * 64,
        )
    assert first.claim_path.read_bytes() == original

    raw = json.loads(original)
    raw["submission_plan_id"] = "arv2-tampered-plan"
    first.claim_path.write_bytes(protocol._canonical_bytes(raw))
    first.claim_path.chmod(0o600)
    with pytest.raises(FormalRunProtocolError, match="changed lineage or plan"):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:02.000000Z",
            attempt_ordinal=1,
            retry_lineage_sha256="e" * 64,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )


def test_open_claim_process_lease_refuses_forked_or_reconstructed_pid(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, _directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    claim = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256="e" * 64,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    changed_pid = dataclasses.replace(
        claim,
        _attempt_lock_pid=claim._attempt_lock_pid + 1,
    )
    with pytest.raises(
        FormalRunProtocolError,
        match="process lease changed",
    ):
        require_formal_look_claim(candidate, authority, changed_pid)
    protocol.record_definite_pre_submission_failure(
        candidate=candidate,
        authority=authority,
        claim=claim,
        phase="fork_test_cleanup",
        failure_class="FormalRunProtocolError",
        recorded_at_utc="2026-09-14T00:00:01.000000Z",
    )


def test_backtests_create_permit_alone_cannot_authorize_a_fresh_attempt(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, _directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    lineage = "e" * 64
    first = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    permit = begin_formal_submission_once(
        candidate=candidate,
        authority=authority,
        claim=first,
        submission_started_at_utc="2026-09-14T00:00:01.000000Z",
        consumption_reason="backtests_create_attempt",
    )
    require_formal_submission_permit(candidate, authority, first, permit)
    permit_raw = json.loads(permit.permit_path.read_bytes())
    assert permit_raw["backtests_create_attempted"] is True
    assert permit_raw["outcome_look_consumed"] is True
    assert permit_raw["current_attempt_reuse_authorized"] is False
    assert permit_raw["attempt_deletion_authorized"] is False
    with pytest.raises(FormalRunProtocolError, match="already spent"):
        begin_formal_submission_once(
            candidate=candidate,
            authority=authority,
            claim=first,
            submission_started_at_utc="2026-09-14T00:00:02.000000Z",
        )

    with pytest.raises(
        FormalRunProtocolError,
        match="lacks an authenticated terminal failure",
    ):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:03.000000Z",
            attempt_ordinal=2,
            retry_lineage_sha256=lineage,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )


def test_ambiguous_external_state_is_consumed_but_cannot_start_parallel_retry(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, _directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    lineage = "e" * 64
    first = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    permit = begin_formal_submission_once(
        candidate=candidate,
        authority=authority,
        claim=first,
        submission_started_at_utc="2026-09-14T00:00:01.000000Z",
        consumption_reason="external_state_ambiguous",
    )
    raw = json.loads(permit.permit_path.read_bytes())
    assert raw["backtests_create_attempted"] is False
    assert raw["external_state_ambiguous"] is True
    assert raw["submission_attempt_count"] == 0
    assert raw["outcome_look_consumed"] is True
    assert raw["attempt_deletion_authorized"] is False

    with pytest.raises(
        FormalRunProtocolError,
        match="lacks an authenticated terminal failure",
    ):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:02.000000Z",
            attempt_ordinal=2,
            retry_lineage_sha256=lineage,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )


def test_only_successful_completed_status_ends_waiver_and_blocks_retry(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, _directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    lineage = "e" * 64
    claim = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    permit = begin_formal_submission_once(
        candidate=candidate,
        authority=authority,
        claim=claim,
        submission_started_at_utc="2026-09-14T00:00:01.000000Z",
    )
    raw = protocol._retry_attempt_success_document(
        candidate,
        authority,
        claim,
        permit_id=permit.permit_id,
        permit_sha256=permit.permit_sha256,
        launch_receipt_id="arv2-launch-receipt-test",
        launch_receipt_sha256="1" * 64,
        backtest_id="arv2-backtest-test",
        terminal_receipt_id="arv2-terminal-receipt-test",
        terminal_receipt_sha256="2" * 64,
        recorded_at_utc="2026-09-14T00:00:02.000000Z",
    )
    completion_path = protocol._exclusive_private_write(
        authority.claim_directory,
        protocol._retry_attempt_path(
            authority.claim_directory,
            protocol._RETRY_ATTEMPT_SUCCESS_TEMPLATE,
            claim.attempt_ordinal,
        ).name,
        protocol._canonical_bytes(raw),
    )
    completion_raw = json.loads(completion_path.read_bytes())
    assert completion_raw["qc_terminal_status"] == "Completed."
    assert completion_raw["runtime_error_ends_owner_review_waiver"] is False
    assert completion_raw["owner_review_waiver_ended"] is True
    assert completion_raw["fresh_retry_authorized"] is False
    with pytest.raises(FormalRunProtocolError, match="waiver ended"):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:03.000000Z",
            attempt_ordinal=2,
            retry_lineage_sha256=lineage,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )


def test_runtime_error_does_not_end_waiver_and_fresh_attempt_opens(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, _directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    lineage = "e" * 64
    first = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    permit = begin_formal_submission_once(
        candidate=candidate,
        authority=authority,
        claim=first,
        submission_started_at_utc="2026-09-14T00:00:01.000000Z",
    )
    launch = types.SimpleNamespace(
        receipt_id="arv2-launch-receipt-test",
        receipt_sha256="1" * 64,
        permit_id=permit.permit_id,
        permit_sha256=permit.permit_sha256,
        backtest_id="arv2-backtest-test",
    )
    terminal = types.SimpleNamespace(
        receipt_id="arv2-terminal-receipt-test",
        receipt_sha256="2" * 64,
        launch_receipt_id=launch.receipt_id,
        launch_receipt_sha256=launch.receipt_sha256,
        permit_id=permit.permit_id,
        permit_sha256=permit.permit_sha256,
        backtest_id=launch.backtest_id,
        terminal_status="Runtime Error",
    )
    disposition = protocol._record_authenticated_formal_backtest_terminal_failure(
        candidate=candidate,
        authority=authority,
        claim=first,
        permit=permit,
        launch_receipt=launch,
        terminal_receipt=terminal,
        recorded_at_utc="2026-09-14T00:00:02.000000Z",
    )
    disposition_raw = json.loads(disposition.disposition_path.read_bytes())
    assert disposition_raw["qc_terminal_status"] == "Runtime Error"
    assert disposition_raw["fresh_retry_authorized"] is True
    assert disposition_raw[
        "queued_running_unknown_or_ambiguous_retry_authorized"
    ] is False
    second = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:03.000000Z",
        attempt_ordinal=2,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    assert second.attempt_ordinal == 2
    assert second.outcome_look_consumed is False


def _consumed_owner_waiver_attempt(tmp_path: Path):
    candidate = _candidate()
    authority, directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    lineage = "e" * 64
    claim = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    permit = begin_formal_submission_once(
        candidate=candidate,
        authority=authority,
        claim=claim,
        submission_started_at_utc="2026-09-14T00:00:01.000000Z",
        consumption_reason="backtests_create_attempt",
    )
    return candidate, authority, directory, lineage, claim, permit


def _load_consumed_owner_waiver_attempt(candidate, authority, lineage: str):
    return protocol.load_consumed_formal_retry_attempt(
        candidate=candidate,
        authority=authority,
        attempt_ordinal=1,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork")
def test_consumed_attempt_reauthenticates_in_a_fork_without_in_memory_identity(
    tmp_path: Path,
):
    candidate, authority, _directory, lineage, claim, permit = (
        _consumed_owner_waiver_attempt(tmp_path)
    )
    read_descriptor, write_descriptor = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:
        os.close(read_descriptor)
        try:
            recovered_claim, recovered_permit = (
                _load_consumed_owner_waiver_attempt(
                    candidate,
                    authority,
                    lineage,
                )
            )
            payload = protocol._canonical_bytes(
                {
                    "claim_id": recovered_claim.claim_id,
                    "claim_sha256": recovered_claim.claim_sha256,
                    "permit_id": recovered_permit.permit_id,
                    "permit_sha256": recovered_permit.permit_sha256,
                    "claim_has_process_lock": (
                        recovered_claim._attempt_lock_descriptor is not None
                        or recovered_claim._attempt_lock_pid is not None
                    ),
                }
            )
            os.write(write_descriptor, payload)
            os.close(write_descriptor)
            os._exit(0)
        except BaseException as exc:
            os.write(
                write_descriptor,
                f"{type(exc).__name__}: {exc}".encode("utf-8"),
            )
            os.close(write_descriptor)
            os._exit(1)
    os.close(write_descriptor)
    child_payload = b""
    while True:
        chunk = os.read(read_descriptor, 4096)
        if not chunk:
            break
        child_payload += chunk
    os.close(read_descriptor)
    _waited_pid, child_status = os.waitpid(child_pid, 0)

    assert os.waitstatus_to_exitcode(child_status) == 0, child_payload.decode()
    recovered = json.loads(child_payload)
    assert recovered == {
        "claim_has_process_lock": False,
        "claim_id": claim.claim_id,
        "claim_sha256": claim.claim_sha256,
        "permit_id": permit.permit_id,
        "permit_sha256": permit.permit_sha256,
    }


@pytest.mark.parametrize(
    ("artifact", "field", "replacement", "message"),
    (
        (
            "claim",
            "submission_plan_id",
            "arv2-tampered-recovery-plan",
            "recoverable formal retry claim changed lineage or plan",
        ),
        (
            "permit",
            "consumption_reason",
            "external_state_ambiguous",
            "recoverable formal submission permit changed",
        ),
    ),
)
def test_consumed_attempt_recovery_refuses_persisted_identity_tamper(
    tmp_path: Path,
    artifact: str,
    field: str,
    replacement: str,
    message: str,
):
    candidate, authority, _directory, lineage, claim, permit = (
        _consumed_owner_waiver_attempt(tmp_path)
    )
    path = claim.claim_path if artifact == "claim" else permit.permit_path
    raw = json.loads(path.read_bytes())
    raw[field] = replacement
    path.write_bytes(protocol._canonical_bytes(raw))
    path.chmod(0o600)

    with pytest.raises(FormalRunProtocolError, match=message):
        _load_consumed_owner_waiver_attempt(candidate, authority, lineage)


def test_consumed_attempt_recovery_refuses_missing_or_nonexact_run_authority(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, _directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    lineage = "e" * 64
    open_claim = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    with pytest.raises(
        FormalRunProtocolError,
        match="recoverable formal submission permit",
    ):
        _load_consumed_owner_waiver_attempt(candidate, authority, lineage)

    ambiguity_permit = begin_formal_submission_once(
        candidate=candidate,
        authority=authority,
        claim=open_claim,
        submission_started_at_utc="2026-09-14T00:00:01.000000Z",
        consumption_reason="external_state_ambiguous",
    )
    assert ambiguity_permit.submission_attempt_count == 0
    with pytest.raises(
        FormalRunProtocolError,
        match="external-state ambiguity has no recoverable exact QC run",
    ):
        _load_consumed_owner_waiver_attempt(candidate, authority, lineage)


def test_recovered_attempt_cannot_resubmit_or_be_relabelled_no_outcome(
    tmp_path: Path,
):
    candidate, authority, _directory, lineage, _claim, _permit = (
        _consumed_owner_waiver_attempt(tmp_path)
    )
    recovered_claim, _recovered_permit = _load_consumed_owner_waiver_attempt(
        candidate,
        authority,
        lineage,
    )

    with pytest.raises(FormalRunProtocolError, match="already spent"):
        begin_formal_submission_once(
            candidate=candidate,
            authority=authority,
            claim=recovered_claim,
            submission_started_at_utc="2026-09-14T00:00:02.000000Z",
            consumption_reason="backtests_create_attempt",
        )
    with pytest.raises(
        FormalRunProtocolError,
        match="consumed formal attempt cannot become a no-outcome failure",
    ):
        protocol.record_definite_pre_submission_failure(
            candidate=candidate,
            authority=authority,
            claim=recovered_claim,
            phase="forbidden_reclassification",
            failure_class="FormalQcSubmissionError",
            recorded_at_utc="2026-09-14T00:00:03.000000Z",
        )


def test_no_outcome_attempt_has_no_consumed_run_to_recover(tmp_path: Path):
    candidate = _candidate()
    authority, _directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    lineage = "e" * 64
    claim = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    protocol.record_definite_pre_submission_failure(
        candidate=candidate,
        authority=authority,
        claim=claim,
        phase="known_no_run",
        failure_class="FormalQcSubmissionError",
        recorded_at_utc="2026-09-14T00:00:01.000000Z",
    )
    with pytest.raises(
        FormalRunProtocolError,
        match="no-outcome formal attempt has no consumed run to recover",
    ):
        _load_consumed_owner_waiver_attempt(candidate, authority, lineage)


def _terminal_receipt_pair(permit, terminal_status: str):
    launch = types.SimpleNamespace(
        receipt_id="arv2-launch-receipt-test",
        receipt_sha256="1" * 64,
        permit_id=permit.permit_id,
        permit_sha256=permit.permit_sha256,
        backtest_id="arv2-backtest-test",
    )
    terminal = types.SimpleNamespace(
        receipt_id="arv2-terminal-receipt-test",
        receipt_sha256="2" * 64,
        launch_receipt_id=launch.receipt_id,
        launch_receipt_sha256=launch.receipt_sha256,
        permit_id=permit.permit_id,
        permit_sha256=permit.permit_sha256,
        backtest_id=launch.backtest_id,
        terminal_status=terminal_status,
    )
    return launch, terminal


def test_runtime_error_disposition_remints_exactly_and_allows_next_ordinal(
    tmp_path: Path,
):
    candidate, authority, _directory, lineage, claim, permit = (
        _consumed_owner_waiver_attempt(tmp_path)
    )
    launch, terminal = _terminal_receipt_pair(permit, "Runtime Error")
    first = protocol._record_authenticated_formal_backtest_terminal_failure(
        candidate=candidate,
        authority=authority,
        claim=claim,
        permit=permit,
        launch_receipt=launch,
        terminal_receipt=terminal,
        recorded_at_utc="2026-09-14T00:00:02.000000Z",
    )
    recovered_claim, recovered_permit = _load_consumed_owner_waiver_attempt(
        candidate,
        authority,
        lineage,
    )
    reminted = protocol._record_authenticated_formal_backtest_terminal_failure(
        candidate=candidate,
        authority=authority,
        claim=recovered_claim,
        permit=recovered_permit,
        launch_receipt=launch,
        terminal_receipt=terminal,
        recorded_at_utc="2026-09-14T00:00:09.000000Z",
    )
    assert reminted == first
    assert reminted.recorded_at_utc == "2026-09-14T00:00:02.000000Z"

    next_claim = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:10.000000Z",
        attempt_ordinal=2,
        retry_lineage_sha256=lineage,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    assert next_claim.attempt_ordinal == 2


def test_completed_disposition_remints_exactly_and_keeps_waiver_closed(
    tmp_path: Path,
):
    candidate, authority, _directory, lineage, claim, permit = (
        _consumed_owner_waiver_attempt(tmp_path)
    )
    launch, terminal = _terminal_receipt_pair(permit, "Completed.")
    first = protocol._record_authenticated_formal_backtest_completion(
        candidate=candidate,
        authority=authority,
        claim=claim,
        permit=permit,
        launch_receipt=launch,
        terminal_receipt=terminal,
        recorded_at_utc="2026-09-14T00:00:02.000000Z",
    )
    recovered_claim, recovered_permit = _load_consumed_owner_waiver_attempt(
        candidate,
        authority,
        lineage,
    )
    reminted = protocol._record_authenticated_formal_backtest_completion(
        candidate=candidate,
        authority=authority,
        claim=recovered_claim,
        permit=recovered_permit,
        launch_receipt=launch,
        terminal_receipt=terminal,
        recorded_at_utc="2026-09-14T00:00:09.000000Z",
    )
    assert reminted == first
    assert reminted.recorded_at_utc == "2026-09-14T00:00:02.000000Z"
    with pytest.raises(FormalRunProtocolError, match="waiver ended"):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:10.000000Z",
            attempt_ordinal=2,
            retry_lineage_sha256=lineage,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )


def test_successful_completion_recorder_is_not_a_public_protocol_action():
    assert not hasattr(protocol, "record_successful_formal_backtest_completion")
    assert "record_successful_formal_backtest_completion" not in protocol.__all__


def test_retry_requires_identical_frozen_lineage_and_sequential_identity(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, directory, _receipt, _pin, _pin_path = (
        _activate_owner_review_waiver(tmp_path, candidate)
    )
    first = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-14T00:00:00.000000Z",
        attempt_ordinal=1,
        retry_lineage_sha256="e" * 64,
        submission_plan_id=OWNER_PLAN_ID,
        submission_plan_sha256=OWNER_PLAN_SHA256,
    )
    protocol.record_definite_pre_submission_failure(
        candidate=candidate,
        authority=authority,
        claim=first,
        phase="pre_qc_reauthentication",
        failure_class="FormalQcSubmissionError",
        recorded_at_utc="2026-09-14T00:00:01.000000Z",
    )
    with pytest.raises(FormalRunProtocolError, match="crossed lineage"):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:02.000000Z",
            attempt_ordinal=2,
            retry_lineage_sha256="f" * 64,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )
    with pytest.raises(FormalRunProtocolError, match="unavailable"):
        claim_formal_run_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc="2026-09-14T00:00:03.000000Z",
            attempt_ordinal=3,
            retry_lineage_sha256="e" * 64,
            submission_plan_id=OWNER_PLAN_ID,
            submission_plan_sha256=OWNER_PLAN_SHA256,
        )
    assert not (directory / "arv2-formal-attempt-000002-claim.json").exists()
    assert not (directory / "arv2-formal-attempt-000003-claim.json").exists()


def test_static_record_discloses_unreviewed_zero_authority():
    record = formal_run_protocol_record()
    assert record["reviewed_authority_artifact_sha256"] is None
    assert record["review_pin_is_external_owner_controlled"] is True
    assert record["infrastructure_look_ledger_bound_in_review_authority"] is True
    assert record["infrastructure_look_ledger_reauthenticated_before_claim"] is True
    assert record["maximum_submissions"] == 1
    assert record["retry_after_ambiguity"] is False
    assert record["owner_waiver_fresh_attempt_after_counted_ambiguity"] is True
    assert record["same_attempt_reuse_or_deletion_authorized"] is False
    assert record["owner_review_waiver"]["independent_review_complete"] is False
    assert record["owner_standing_retry_policy"][
        "automatic_retry_loop_authorized"
    ] is False
    assert record["owner_standing_retry_policy"][
        "fresh_retry_requires_authenticated_terminal_failure"
    ] is True
    assert record["owner_standing_retry_policy"][
        "transport_ambiguity_authorizes_fresh_retry"
    ] is False
    assert record["result_read_requires_separate_terminal_gate"] is True


def test_exact_scalar_types_refuse_bool_counts():
    with pytest.raises(FormalRunProtocolError, match="integer census"):
        dataclasses.replace(_artifact("x", "a"), byte_count=True)
    with pytest.raises(FormalRunProtocolError, match="integer census"):
        _power(required_valid_dates=True)
    with pytest.raises(FormalRunProtocolError, match="integer census"):
        _power(h20_test_session_capacity=True)


def test_c1_accepted_risk_binding_exactly_refuses_pristine_pit():
    message = "accepted-risk input cannot claim pristine PIT"
    with pytest.raises(FormalRunProtocolError, match=re.escape(message)):
        _accepted_risk(pristine_point_in_time=True)


@pytest.mark.parametrize(
    ("failure", "message"),
    (
        ("create", "formal ledger entry could not be created"),
        ("stall", "formal ledger write stalled"),
        (
            "reauthenticate",
            "formal ledger entry cannot be reauthenticated after creation",
        ),
        ("changed", "formal ledger entry changed after creation"),
    ),
)
def test_exclusive_ledger_write_isolates_each_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    message: str,
):
    directory = (tmp_path / failure).absolute()
    directory.mkdir(mode=0o700)

    if failure == "create":
        monkeypatch.setattr(
            protocol.os,
            "open",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
        )
    elif failure == "stall":
        monkeypatch.setattr(protocol.os, "write", lambda *_args: 0)
    elif failure == "reauthenticate":
        monkeypatch.setattr(
            protocol,
            "_read_private_regular",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
        )
    else:
        monkeypatch.setattr(
            protocol,
            "_read_private_regular",
            lambda *_args, **_kwargs: b"different",
        )

    with pytest.raises(FormalRunProtocolError, match=re.escape(message)):
        protocol._exclusive_private_write(directory, "ledger.json", b"payload\n")
    target = directory / "ledger.json"
    if failure in {"create", "stall"}:
        assert not target.exists()
    else:
        assert target.read_bytes() == b"payload\n"
    assert not any(".pending-" in path.name for path in directory.iterdir())


def test_claim_type_path_unavailable_and_change_have_distinct_refusals(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, directory, _receipt, _pin, _pin_path = _activate(tmp_path, candidate)
    claim = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-12T00:00:00.000000Z",
    )

    with pytest.raises(
        FormalRunProtocolError,
        match=re.escape("formal look claim type changed"),
    ):
        require_formal_look_claim(candidate, authority, object())  # type: ignore[arg-type]
    wrong_path = dataclasses.replace(
        claim,
        claim_path=directory / "wrong-claim.json",
    )
    with pytest.raises(
        FormalRunProtocolError,
        match=re.escape("formal look claim path changed"),
    ):
        require_formal_look_claim(candidate, authority, wrong_path)

    claim.claim_path.unlink()
    with pytest.raises(
        FormalRunProtocolError,
        match=re.escape("formal look claim is unavailable"),
    ):
        require_formal_look_claim(candidate, authority, claim)

    claim.claim_path.write_bytes(claim._claim_bytes)
    claim.claim_path.chmod(0o600)
    changed = dataclasses.replace(claim, claim_sha256="0" * 64)
    with pytest.raises(
        FormalRunProtocolError,
        match=re.escape("formal look claim changed"),
    ):
        require_formal_look_claim(candidate, authority, changed)


def test_permit_type_path_unavailable_and_change_have_distinct_refusals(
    tmp_path: Path,
):
    candidate = _candidate()
    authority, directory, _receipt, _pin, _pin_path = _activate(tmp_path, candidate)
    claim = claim_formal_run_once(
        candidate=candidate,
        authority=authority,
        claimed_at_utc="2026-09-12T00:00:00.000000Z",
    )
    permit = begin_formal_submission_once(
        candidate=candidate,
        authority=authority,
        claim=claim,
        submission_started_at_utc="2026-09-12T00:00:01.000000Z",
    )

    with pytest.raises(
        FormalRunProtocolError,
        match=re.escape("formal submission permit type changed"),
    ):
        require_formal_submission_permit(
            candidate,
            authority,
            claim,
            object(),  # type: ignore[arg-type]
        )
    wrong_path = dataclasses.replace(
        permit,
        permit_path=directory / "wrong-permit.json",
    )
    with pytest.raises(
        FormalRunProtocolError,
        match=re.escape("formal submission permit path changed"),
    ):
        require_formal_submission_permit(candidate, authority, claim, wrong_path)

    permit.permit_path.unlink()
    with pytest.raises(
        FormalRunProtocolError,
        match=re.escape("formal submission permit is unavailable"),
    ):
        require_formal_submission_permit(candidate, authority, claim, permit)

    permit.permit_path.write_bytes(permit._permit_bytes)
    permit.permit_path.chmod(0o600)
    changed = dataclasses.replace(permit, permit_sha256="0" * 64)
    with pytest.raises(
        FormalRunProtocolError,
        match=re.escape("formal submission permit changed"),
    ):
        require_formal_submission_permit(candidate, authority, claim, changed)
