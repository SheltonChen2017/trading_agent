"""Final fail-closed boundary immediately before one formal ARV2 QC run.

This module composes existing reviewed contracts; it cannot create data,
review, signature, or execution authority. Every positive gate is derived
from a builder-authenticated typed object. Callers cannot open a gate with a
boolean, identifier, path, mapping, callback, or status string.

Import and the default report perform no provider, credential, outcome, or
QuantConnect I/O. A real invocation authenticates every physical, review,
owner-signature, and software gate, reauthenticates the live file-backed
stack, creates the exclusive formal-look claim, and only then calls the
streamed one-shot adapter exactly once.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sys
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from scripts.build_arv2_historical_preopen_bridge import (
    HistoricalPreopenBridgeError,
    ReviewedHistoricalUniverseToPreopenBridge,
    require_reviewed_historical_universe_to_preopen_bridge,
)

from research.analyst_revisions_v2.production_evidence_acquisition import (
    ProductionEvidenceAcquisitionReceipt,
)
from research.analyst_revisions_v2.production_input_pipeline import (
    EvidenceSourceKind,
)

from .formal_qc_transport import FormalQcTransport
from .formal_run_protocol import (
    FormalLookClaim,
    FormalSubmissionPermit,
    claim_formal_run_once,
)
from .formal_streaming_bridge import (
    FormalStreamingBridgeError,
    StreamedFormalRuntimeBridge,
    require_streamed_formal_runtime_bridge,
)
from .formal_submission_adapter import (
    FormalQcLaunchReceipt,
    FormalQcSubmissionError,
    StreamedFormalSubmissionAdapterBridge,
    execute_streamed_formal_qc_submission_once,
    require_streamed_formal_submission_adapter_bridge,
    streamed_formal_post_launch_capability_record,
    verify_formal_qc_host_closure_live,
)
from .owner_signature_authority import reviewed_owner_signature_registry_status
from .formal_terminal_disposition_builder import (
    FormalTerminalDispositionBuild,
    FormalTerminalDispositionBuildError,
    require_formal_terminal_disposition_build,
)
from .power_calibration_bridge import (
    AcceptedRiskPowerCalibrationError,
    AuthenticatedPowerFloorBinding,
    require_authenticated_power_floor_binding,
)


SCHEMA = "arv2-production-pre-qc-orchestrator-v2"
REPORT_SCHEMA = "arv2-production-pre-qc-preflight-report-v2"
STREAMED_POST_LAUNCH_CAPABILITY_SCHEMA = (
    "arv2-streamed-formal-post-launch-capability-v1"
)

_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PreQcOrchestrationError(ValueError):
    """The supplied pre-QC evidence is invalid or internally inconsistent."""


class PreQcOrchestrationBlocked(RuntimeError):
    """At least one named gate remains closed before any formal claim."""

    def __init__(self, report: "PreQcPreflightReport") -> None:
        self.report = report
        super().__init__(
            "formal QC preflight is closed: " + report.first_blocking_gate_id
        )


class GateStatus(str, Enum):
    SATISFIED = "satisfied"
    MISSING_ARTIFACT = "missing_artifact"
    MISSING_REVIEW_PIN = "missing_review_pin"
    MISSING_OWNER_SIGNATURE = "missing_owner_signature"
    INVALID = "invalid"
    NOT_REACHED = "not_reached"
    ADAPTER_ENFORCED = "enforced_by_one_shot_adapter"


@dataclasses.dataclass(frozen=True, slots=True)
class _GateSpec:
    gate_id: str
    phase: str
    external: bool


_GATE_SPECS = (
    _GateSpec("massive_accepted_risk_capture_pair", "physical_sources", True),
    _GateSpec("historical_qc_universe_discovery", "physical_sources", True),
    _GateSpec("historical_universe_to_preopen_manifest", "physical_sources", False),
    _GateSpec("firm_ontology_and_q_data_review", "preopen_construction", True),
    _GateSpec("full_pit_security_session_peer_census", "preopen_construction", True),
    _GateSpec("preopen_qc_run_and_output_review", "preopen_construction", True),
    _GateSpec("formal_terminal_disposition_build", "terminal_disposition", True),
    _GateSpec("production_truth_and_evidence_review", "production_scoring", True),
    _GateSpec("accepted_risk_nuisance_power_calibration", "power_calibration", True),
    _GateSpec("streaming_capacity_review", "production_scoring", True),
    _GateSpec(
        "streamed_six_fold_scoring_and_formal_shards",
        "production_scoring",
        False,
    ),
    _GateSpec("streamed_input_to_runtime_manifest", "runtime_projection", False),
    _GateSpec("formal_runtime_capacity_review", "runtime_projection", True),
    _GateSpec("formal_runtime_projection", "runtime_projection", False),
    _GateSpec("sequential_stream_to_submission_adapter", "runtime_projection", False),
    _GateSpec(
        "formal_candidate_review_and_counterreview_pin",
        "formal_authority",
        True,
    ),
    _GateSpec("reviewed_owner_public_key_pin", "formal_authority", True),
    _GateSpec("detached_owner_execution_signature", "formal_authority", True),
    _GateSpec("live_host_source_closure", "formal_authority", False),
    _GateSpec("concrete_qc_transport_source_binding", "formal_authority", False),
    _GateSpec("exact_one_shot_submission_plan", "formal_authority", False),
    _GateSpec(
        "streamed_post_launch_outcome_path",
        "post_launch_outcome",
        False,
    ),
    _GateSpec("exclusive_formal_look_claim_ledger", "external_execution", True),
    _GateSpec("qc_credentials_and_account_authentication", "external_execution", True),
    _GateSpec("qc_project_object_compile_backtest_actions", "external_execution", True),
)
GATE_IDS = tuple(item.gate_id for item in _GATE_SPECS)
PHASES = tuple(dict.fromkeys(item.phase for item in _GATE_SPECS))

# Data, human review/signatures, and the runnable submission plan are separate
# from whether the complete streamed software path has been built.
PRE_SUBMISSION_SOFTWARE_GATE_IDS = (
    "historical_universe_to_preopen_manifest",
    "streamed_six_fold_scoring_and_formal_shards",
    "streamed_input_to_runtime_manifest",
    "formal_runtime_projection",
    "sequential_stream_to_submission_adapter",
)
SOFTWARE_GATE_IDS = PRE_SUBMISSION_SOFTWARE_GATE_IDS + (
    "streamed_post_launch_outcome_path",
)
PHYSICAL_DATA_GATE_IDS = (
    "massive_accepted_risk_capture_pair",
    "historical_qc_universe_discovery",
    "firm_ontology_and_q_data_review",
    "full_pit_security_session_peer_census",
    "preopen_qc_run_and_output_review",
    "formal_terminal_disposition_build",
    "production_truth_and_evidence_review",
    "accepted_risk_nuisance_power_calibration",
    "streaming_capacity_review",
    "formal_runtime_capacity_review",
)
AUTHORITY_GATE_IDS = (
    "formal_candidate_review_and_counterreview_pin",
    "reviewed_owner_public_key_pin",
    "detached_owner_execution_signature",
    "live_host_source_closure",
    "concrete_qc_transport_source_binding",
    "exact_one_shot_submission_plan",
)


@dataclasses.dataclass(frozen=True, slots=True)
class PreQcGateResult:
    gate_id: str
    phase: str
    status: GateStatus
    reason_code: str
    blocking: bool
    external: bool
    artifact_id: str | None = None
    artifact_sha256: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.gate_id) is not str
            or _SAFE.fullmatch(self.gate_id) is None
            or type(self.phase) is not str
            or _SAFE.fullmatch(self.phase) is None
            or type(self.status) is not GateStatus
            or type(self.reason_code) is not str
            or _SAFE.fullmatch(self.reason_code) is None
            or type(self.blocking) is not bool
            or type(self.external) is not bool
            or (
                self.artifact_id is not None
                and (
                    type(self.artifact_id) is not str
                    or _SAFE.fullmatch(self.artifact_id) is None
                )
            )
            or (
                self.artifact_sha256 is not None
                and (
                    type(self.artifact_sha256) is not str
                    or _SHA256.fullmatch(self.artifact_sha256) is None
                )
            )
        ):
            raise PreQcOrchestrationError("pre-QC gate result changed")
        if (self.artifact_id is None) != (self.artifact_sha256 is None):
            raise PreQcOrchestrationError("pre-QC gate artifact identity is partial")

    def to_record(self) -> dict[str, object]:
        return {
            "gate_id": self.gate_id,
            "phase": self.phase,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "blocking": self.blocking,
            "external": self.external,
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class PreQcPreflightReport:
    report_id: str
    report_sha256: str
    schema: str
    gates: tuple[PreQcGateResult, ...]
    pre_submission_software_build_ready: bool
    software_build_ready: bool
    physical_data_ready: bool
    review_and_owner_authority_ready: bool
    ready_for_formal_claim: bool
    ready_for_one_shot_submission: bool
    first_blocking_gate_id: str
    satisfied_gate_count: int
    blocking_gate_count: int
    provider_qc_or_outcome_io_performed: bool
    local_filesystem_reauthentication_performed: bool
    provider_credentials_inspected: bool
    qc_credentials_inspected: bool
    outcome_data_accessed: bool
    _canonical_document: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "report_id": self.report_id,
            "report_sha256": self.report_sha256,
            "gate_order": list(GATE_IDS),
            "phase_order": list(PHASES),
            "gates": [item.to_record() for item in self.gates],
            "pre_submission_software_build_ready": (
                self.pre_submission_software_build_ready
            ),
            "software_build_ready": self.software_build_ready,
            "physical_data_ready": self.physical_data_ready,
            "review_and_owner_authority_ready": self.review_and_owner_authority_ready,
            "ready_for_formal_claim": self.ready_for_formal_claim,
            "ready_for_one_shot_submission": self.ready_for_one_shot_submission,
            "first_blocking_gate_id": self.first_blocking_gate_id,
            "satisfied_gate_count": self.satisfied_gate_count,
            "blocking_gate_count": self.blocking_gate_count,
            "provider_qc_or_outcome_io_performed": (
                self.provider_qc_or_outcome_io_performed
            ),
            "local_filesystem_reauthentication_performed": (
                self.local_filesystem_reauthentication_performed
            ),
            "provider_credentials_inspected": self.provider_credentials_inspected,
            "qc_credentials_inspected": self.qc_credentials_inspected,
            "outcome_data_accessed": self.outcome_data_accessed,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class PreQcExecutionEvidence:
    """Only reviewed object graphs may be composed into pre-QC authority."""

    historical_bridge: ReviewedHistoricalUniverseToPreopenBridge | None = (
        dataclasses.field(default=None, repr=False)
    )
    terminal_disposition_build: FormalTerminalDispositionBuild | None = (
        dataclasses.field(default=None, repr=False)
    )
    authenticated_power_floor: AuthenticatedPowerFloorBinding | None = (
        dataclasses.field(default=None, repr=False)
    )
    runtime_bridge: StreamedFormalRuntimeBridge | None = dataclasses.field(
        default=None, repr=False
    )
    submission_bridge: StreamedFormalSubmissionAdapterBridge | None = (
        dataclasses.field(default=None, repr=False)
    )


def _canonical(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise PreQcOrchestrationError("pre-QC report is not canonical JSON") from exc


def _result(
    gate_id: str,
    status: GateStatus,
    reason_code: str,
    *,
    artifact_id: str | None = None,
    artifact_sha256: str | None = None,
) -> PreQcGateResult:
    spec = _GATE_SPECS[GATE_IDS.index(gate_id)]
    return PreQcGateResult(
        gate_id=gate_id,
        phase=spec.phase,
        status=status,
        reason_code=reason_code,
        blocking=status not in {GateStatus.SATISFIED, GateStatus.ADAPTER_ENFORCED},
        external=spec.external,
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
    )


def _missing(
    gate_id: str, reason_code: str = "typed_artifact_not_supplied"
) -> PreQcGateResult:
    return _result(gate_id, GateStatus.MISSING_ARTIFACT, reason_code)


def _invalid(gate_id: str, reason_code: str) -> PreQcGateResult:
    return _result(gate_id, GateStatus.INVALID, reason_code)


def _owner_key_gate() -> PreQcGateResult:
    registry = reviewed_owner_signature_registry_status()
    counts = registry.get("gate_key_counts") if type(registry) is dict else None
    if (
        type(counts) is dict
        and type(counts.get("formal_qc_execution")) is int
        and counts["formal_qc_execution"] == 1
        and type(counts.get("formal_qc_result_read")) is int
        and counts["formal_qc_result_read"] == 1
    ):
        return _result(
            "reviewed_owner_public_key_pin",
            GateStatus.SATISFIED,
            "reviewed_formal_execution_and_result_read_key_pinned",
        )
    return _result(
        "reviewed_owner_public_key_pin",
        GateStatus.MISSING_OWNER_SIGNATURE,
        "formal_execution_or_result_read_public_key_not_pinned",
    )


def _closed_default_results() -> dict[str, PreQcGateResult]:
    results = {item.gate_id: _missing(item.gate_id) for item in _GATE_SPECS}
    results["streamed_post_launch_outcome_path"] = _missing(
        "streamed_post_launch_outcome_path",
        "typed_streamed_submission_bridge_not_supplied",
    )
    results["reviewed_owner_public_key_pin"] = _owner_key_gate()
    results["exclusive_formal_look_claim_ledger"] = _result(
        "exclusive_formal_look_claim_ledger",
        GateStatus.ADAPTER_ENFORCED,
        "created_exclusively_only_after_complete_live_preflight",
    )
    results["qc_credentials_and_account_authentication"] = _result(
        "qc_credentials_and_account_authentication",
        GateStatus.ADAPTER_ENFORCED,
        "credentials_consumed_only_inside_concrete_one_shot_adapter",
    )
    results["qc_project_object_compile_backtest_actions"] = _result(
        "qc_project_object_compile_backtest_actions",
        GateStatus.ADAPTER_ENFORCED,
        "one_streamed_adapter_call_only_after_durable_claim",
    )
    return results


def _record_production_receipt(
    results: dict[str, PreQcGateResult],
    receipt: ProductionEvidenceAcquisitionReceipt,
) -> None:
    results["production_truth_and_evidence_review"] = _result(
        "production_truth_and_evidence_review",
        GateStatus.SATISFIED,
        "reviewed_production_evidence_receipt_authenticated",
        artifact_id=receipt.receipt_id,
        artifact_sha256=receipt.receipt_sha256,
    )
    bindings = {
        item.kind: item
        for item in receipt.authority.source_bindings
        if item.kind in {
            EvidenceSourceKind.FIRM_ONTOLOGY,
            EvidenceSourceKind.DATA_QUALITY,
        }
    }
    required = {
        EvidenceSourceKind.FIRM_ONTOLOGY,
        EvidenceSourceKind.DATA_QUALITY,
    }
    if set(bindings) != required:
        results["firm_ontology_and_q_data_review"] = _invalid(
            "firm_ontology_and_q_data_review",
            "firm_ontology_or_q_data_source_binding_missing",
        )
    elif any(
        type(flag) is not bool or flag is not True
        for item in bindings.values()
        for flag in (item.reviewed, item.point_in_time)
    ):
        results["firm_ontology_and_q_data_review"] = _result(
            "firm_ontology_and_q_data_review",
            GateStatus.MISSING_REVIEW_PIN,
            "firm_ontology_or_q_data_not_reviewed_point_in_time",
        )
    else:
        results["firm_ontology_and_q_data_review"] = _result(
            "firm_ontology_and_q_data_review",
            GateStatus.SATISFIED,
            "canonical_firm_ontology_and_q_data_sources_reviewed",
            artifact_id=receipt.receipt_id,
            artifact_sha256=receipt.receipt_sha256,
        )


def _historical_runtime_lineage_matches(
    historical: ReviewedHistoricalUniverseToPreopenBridge,
    runtime_bridge: StreamedFormalRuntimeBridge,
) -> bool:
    try:
        streamed = runtime_bridge.resource_candidate.streamed_input
        preopen = streamed.shards.capacity.preopen_acquisition_receipt
        accepted = runtime_bridge.formal_run_candidate.accepted_risk
        truth_sources = {
            kind: (artifact_id, artifact_sha256)
            for kind, artifact_id, artifact_sha256 in preopen.truth_source_bindings
        }
        return (
            historical.pair_id == accepted.pair.artifact_id
            and historical.pair_sha256 == accepted.pair.content_sha256
            and historical.derived_capture_id == accepted.capture_id
            and historical.derived_capture_sha256 == accepted.capture_sha256
            and preopen.input_manifest_sha256
            == historical.closed_input_manifest_sha256
            and preopen.input_source_inventory_sha256
            == historical.input_shard_inventory_sha256
            and truth_sources.get("accepted_risk_capture")
            == (
                historical.accepted_risk_bridge_id,
                historical.accepted_risk_bridge_sha256,
            )
            and truth_sources.get("eligible_universe")
            == (
                historical.discovery_eligible_universe_artifact_id,
                historical.discovery_eligible_universe_artifact_sha256,
            )
            and truth_sources.get("security_master")
            == (
                historical.security_master_artifact_id,
                historical.security_master_artifact_sha256,
            )
            and truth_sources.get("preopen_control")
            == (
                historical.physical_candidate_id,
                historical.physical_candidate_sha256,
            )
            and preopen.control_sessions[0].decision_session
            == historical.first_session
            and preopen.control_sessions[-1].decision_session
            == historical.last_session
        )
    except (AttributeError, IndexError, TypeError, ValueError):
        return False


def _record_historical_bridge(
    results: dict[str, PreQcGateResult],
    bridge: ReviewedHistoricalUniverseToPreopenBridge,
) -> None:
    results["massive_accepted_risk_capture_pair"] = _result(
        "massive_accepted_risk_capture_pair",
        GateStatus.SATISFIED,
        "accepted_risk_pair_and_one_capture_authenticated",
        artifact_id=bridge.pair_id,
        artifact_sha256=bridge.pair_sha256,
    )
    results["historical_qc_universe_discovery"] = _result(
        "historical_qc_universe_discovery",
        GateStatus.SATISFIED,
        "reviewed_historical_qc_discovery_authenticated",
        artifact_id=bridge.discovery_receipt_id,
        artifact_sha256=bridge.discovery_receipt_sha256,
    )
    results["historical_universe_to_preopen_manifest"] = _result(
        "historical_universe_to_preopen_manifest",
        GateStatus.SATISFIED,
        "reviewed_historical_preopen_bridge_authenticated",
        artifact_id=bridge.bridge_id,
        artifact_sha256=bridge.bridge_sha256,
    )


def _record_runtime_bridge(
    results: dict[str, PreQcGateResult],
    bridge: StreamedFormalRuntimeBridge,
) -> None:
    streamed = bridge.resource_candidate.streamed_input
    capacity = streamed.shards.capacity
    preopen = capacity.preopen_acquisition_receipt
    production = capacity.production_evidence_receipt
    results["preopen_qc_run_and_output_review"] = _result(
        "preopen_qc_run_and_output_review",
        GateStatus.SATISFIED,
        "reviewed_preopen_acquisition_receipt_authenticated",
        artifact_id=preopen.artifact_id,
        artifact_sha256=preopen.artifact_sha256,
    )
    _record_production_receipt(results, production)
    results["streaming_capacity_review"] = _result(
        "streaming_capacity_review",
        GateStatus.SATISFIED,
        "reviewed_streaming_capacity_authenticated",
        artifact_id=capacity.receipt_id,
        artifact_sha256=capacity.receipt_sha256,
    )
    results["streamed_six_fold_scoring_and_formal_shards"] = _result(
        "streamed_six_fold_scoring_and_formal_shards",
        GateStatus.SATISFIED,
        "six_folds_and_physical_formal_shards_authenticated",
        artifact_id=streamed.candidate_id,
        artifact_sha256=streamed.candidate_sha256,
    )
    results["streamed_input_to_runtime_manifest"] = _result(
        "streamed_input_to_runtime_manifest",
        GateStatus.SATISFIED,
        "streamed_input_runtime_manifest_bridge_authenticated",
        artifact_id=bridge.bridge_id,
        artifact_sha256=bridge.bridge_sha256,
    )
    results["formal_runtime_capacity_review"] = _result(
        "formal_runtime_capacity_review",
        GateStatus.SATISFIED,
        "reviewed_formal_runtime_capacity_authenticated",
        artifact_id=bridge.capacity.receipt_id,
        artifact_sha256=bridge.capacity.receipt_sha256,
    )
    results["formal_runtime_projection"] = _result(
        "formal_runtime_projection",
        GateStatus.SATISFIED,
        "streamed_runtime_projection_authenticated",
        artifact_id=bridge.runtime_projection.projection_id,
        artifact_sha256=bridge.runtime_projection.projection_sha256,
    )
    if (
        bridge.sequential_reopen_rehash_required is True
        and bridge.legacy_tuple_upload_compatible is False
    ):
        results["sequential_stream_to_submission_adapter"] = _result(
            "sequential_stream_to_submission_adapter",
            GateStatus.SATISFIED,
            "reviewed_sequential_reopen_rehash_interface_authenticated",
            artifact_id=bridge.bridge_id,
            artifact_sha256=bridge.bridge_sha256,
        )
    else:  # Defensive even though the runtime-bridge validator is fail-closed.
        results["sequential_stream_to_submission_adapter"] = _invalid(
            "sequential_stream_to_submission_adapter",
            "runtime_bridge_does_not_prove_sequential_nonmaterializing_upload",
        )


def _terminal_matches_runtime(
    value: FormalTerminalDispositionBuild,
    runtime_bridge: StreamedFormalRuntimeBridge,
) -> bool:
    streamed = runtime_bridge.resource_candidate.streamed_input
    return (
        streamed.terminal_build is value
        and value.terminal_package is streamed.terminal_package
        and value.terminal_census
        is runtime_bridge.formal_run_candidate.terminal_census
        and value.terminal_input_complete is True
        and value.silently_omitted_count == 0
    )


def _power_matches_runtime(
    value: AuthenticatedPowerFloorBinding,
    runtime_bridge: StreamedFormalRuntimeBridge,
) -> bool:
    streamed = runtime_bridge.resource_candidate.streamed_input
    return (
        value.power_floor is runtime_bridge.formal_run_candidate.power_floor
        and value.formal_power is streamed.formal_power
        and value.formal_census.scoring_artifact is streamed.scoring
        and value.scoring_artifact_id == streamed.scoring.artifact_id
        and value.scoring_artifact_sha256 == streamed.scoring.artifact_sha256
    )


def _submission_identities_match(
    submitted: StreamedFormalSubmissionAdapterBridge,
    runtime_bridge: StreamedFormalRuntimeBridge,
    authenticated_power_floor: AuthenticatedPowerFloorBinding | None,
) -> bool:
    return (
        authenticated_power_floor is not None
        and submitted.runtime_bridge is runtime_bridge
        and submitted.formal_run_candidate is runtime_bridge.formal_run_candidate
        and submitted.authenticated_power_floor is authenticated_power_floor
        and submitted.sequential_upload_primitive_present is True
        and submitted.full_payload_tuple_materialized is False
        and submitted.external_action_performed is False
        and submitted.plan.runtime_bridge is runtime_bridge
        and submitted.plan.execution_authority is submitted.execution_authority
        and submitted.plan.candidate_id
        == runtime_bridge.formal_run_candidate.candidate_id
        and submitted.plan.candidate_sha256
        == runtime_bridge.formal_run_candidate.candidate_sha256
        and submitted.plan.reviewed_authority_id
        == submitted.reviewed_authority.authority_id
        and submitted.execution_authority.candidate_id
        == runtime_bridge.formal_run_candidate.candidate_id
        and submitted.execution_authority.candidate_sha256
        == runtime_bridge.formal_run_candidate.candidate_sha256
        and submitted.execution_authority.runtime_bridge_id == runtime_bridge.bridge_id
        and submitted.execution_authority.runtime_bridge_sha256
        == runtime_bridge.bridge_sha256
    )


def _record_submission_bridge(
    results: dict[str, PreQcGateResult],
    submitted: StreamedFormalSubmissionAdapterBridge,
) -> None:
    authority = submitted.reviewed_authority
    execution = submitted.execution_authority
    host = execution.host_code_closure
    transport = execution.transport
    plan = submitted.plan
    results["formal_candidate_review_and_counterreview_pin"] = _result(
        "formal_candidate_review_and_counterreview_pin",
        GateStatus.SATISFIED,
        "independent_review_and_counterreview_pin_authenticated",
        artifact_id=authority.authority_id,
        artifact_sha256=authority.authority_sha256,
    )
    results["detached_owner_execution_signature"] = _result(
        "detached_owner_execution_signature",
        GateStatus.SATISFIED,
        "owner_signature_reauthenticated_over_streamed_execution_authority",
        artifact_id=execution.authority_id,
        artifact_sha256=execution.authority_sha256,
    )
    results["live_host_source_closure"] = _result(
        "live_host_source_closure",
        GateStatus.SATISFIED,
        "host_source_closure_authenticated_with_final_live_recheck_required",
        artifact_id=host.closure_id,
        artifact_sha256=host.closure_sha256,
    )
    results["concrete_qc_transport_source_binding"] = _result(
        "concrete_qc_transport_source_binding",
        GateStatus.SATISFIED,
        "concrete_qc_transport_source_authenticated",
        artifact_id=transport.transport_id,
        artifact_sha256=transport.transport_sha256,
    )
    results["exact_one_shot_submission_plan"] = _result(
        "exact_one_shot_submission_plan",
        GateStatus.SATISFIED,
        "exact_streamed_one_submission_statistics_free_plan_authenticated",
        artifact_id=plan.plan_id,
        artifact_sha256=plan.plan_sha256,
    )


def _post_launch_capability_matches(
    value: object,
    submitted: StreamedFormalSubmissionAdapterBridge,
) -> bool:
    expected = {
        "schema": STREAMED_POST_LAUNCH_CAPABILITY_SCHEMA,
        "runtime_bridge_id": submitted.runtime_bridge.bridge_id,
        "runtime_bridge_sha256": submitted.runtime_bridge.bridge_sha256,
        "submission_adapter_bridge_id": submitted.bridge_id,
        "submission_adapter_bridge_sha256": submitted.bridge_sha256,
        "authenticated_power_floor_id": (
            submitted.authenticated_power_floor.binding_id
        ),
        "authenticated_power_floor_sha256": (
            submitted.authenticated_power_floor.binding_sha256
        ),
        "economic_execution_binding_id": submitted.economic_execution.binding_id,
        "economic_execution_binding_sha256": (
            submitted.economic_execution.binding_sha256
        ),
        "economic_execution_definition_id": (
            submitted.economic_execution.definition_id
        ),
        "economic_execution_definition_sha256": (
            submitted.economic_execution.definition_sha256
        ),
        "formal_report_contract_id": submitted.report_contract.contract_id,
        "formal_report_contract_sha256": submitted.report_contract.contract_sha256,
        "formal_report_contract_artifact_sha256": (
            submitted.report_contract.artifact_sha256
        ),
        "identity_status_only_value_selection_with_include_statistics_false": True,
        "root_authenticated_26_object_report_family_read": True,
        "separate_owner_signed_result_read_gate": True,
        "one_use_selected_summary_statistics_only_read": True,
        "builder_authenticated_summary_result_receipt": True,
        "formal_evaluation_bridge_receipt_compatible": True,
        "process_bound_power_authority": True,
        "logs_charts_orders_trades_access": False,
    }
    return type(value) is dict and value == expected


def _record_post_launch_capability(
    results: dict[str, PreQcGateResult],
    submitted: StreamedFormalSubmissionAdapterBridge,
) -> None:
    try:
        capability = streamed_formal_post_launch_capability_record(submitted)
    except (FormalQcSubmissionError, OSError, TypeError, ValueError):
        results["streamed_post_launch_outcome_path"] = _invalid(
            "streamed_post_launch_outcome_path",
            "streamed_post_launch_capability_invalid_or_tampered",
        )
        return
    if not _post_launch_capability_matches(capability, submitted):
        results["streamed_post_launch_outcome_path"] = _invalid(
            "streamed_post_launch_outcome_path",
            "streamed_post_launch_capability_contract_mismatch",
        )
        return
    results["streamed_post_launch_outcome_path"] = _result(
        "streamed_post_launch_outcome_path",
        GateStatus.SATISFIED,
        "authenticated_streamed_status_result_read_and_evaluation_path",
        artifact_id=submitted.bridge_id,
        artifact_sha256=submitted.bridge_sha256,
    )


def _report(
    results: Mapping[str, PreQcGateResult],
    *,
    local_filesystem_reauthentication_performed: bool = False,
) -> PreQcPreflightReport:
    if type(results) not in (dict, MappingProxyType) or tuple(results) != GATE_IDS:
        raise PreQcOrchestrationError("pre-QC gate inventory or order changed")
    if type(local_filesystem_reauthentication_performed) is not bool:
        raise PreQcOrchestrationError("local reauthentication state changed type")
    gates = tuple(results[item] for item in GATE_IDS)
    blocking = tuple(item for item in gates if item.blocking)
    ready = not blocking
    pre_submission_software_ready = all(
        not results[item].blocking for item in PRE_SUBMISSION_SOFTWARE_GATE_IDS
    )
    software_ready = all(not results[item].blocking for item in SOFTWARE_GATE_IDS)
    physical_ready = all(not results[item].blocking for item in PHYSICAL_DATA_GATE_IDS)
    authority_ready = all(not results[item].blocking for item in AUTHORITY_GATE_IDS)
    first = blocking[0].gate_id if blocking else "none"
    seed = {
        "schema": REPORT_SCHEMA,
        "report_id": None,
        "report_sha256": None,
        "gate_order": list(GATE_IDS),
        "phase_order": list(PHASES),
        "gates": [item.to_record() for item in gates],
        "pre_submission_software_build_ready": pre_submission_software_ready,
        "software_build_ready": software_ready,
        "physical_data_ready": physical_ready,
        "review_and_owner_authority_ready": authority_ready,
        "ready_for_formal_claim": ready,
        "ready_for_one_shot_submission": ready,
        "first_blocking_gate_id": first,
        "satisfied_gate_count": sum(
            item.status is GateStatus.SATISFIED for item in gates
        ),
        "blocking_gate_count": len(blocking),
        "provider_qc_or_outcome_io_performed": False,
        "local_filesystem_reauthentication_performed": (
            local_filesystem_reauthentication_performed
        ),
        "provider_credentials_inspected": False,
        "qc_credentials_inspected": False,
        "outcome_data_accessed": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["report_sha256"] = digest
    seed["report_id"] = "arv2-pre-qc-preflight-" + digest[:24]
    return PreQcPreflightReport(
        report_id=str(seed["report_id"]),
        report_sha256=digest,
        schema=REPORT_SCHEMA,
        gates=gates,
        pre_submission_software_build_ready=pre_submission_software_ready,
        software_build_ready=software_ready,
        physical_data_ready=physical_ready,
        review_and_owner_authority_ready=authority_ready,
        ready_for_formal_claim=ready,
        ready_for_one_shot_submission=ready,
        first_blocking_gate_id=first,
        satisfied_gate_count=int(seed["satisfied_gate_count"]),
        blocking_gate_count=len(blocking),
        provider_qc_or_outcome_io_performed=False,
        local_filesystem_reauthentication_performed=(
            local_filesystem_reauthentication_performed
        ),
        provider_credentials_inspected=False,
        qc_credentials_inspected=False,
        outcome_data_accessed=False,
        _canonical_document=_canonical(seed),
    )


def build_pre_qc_preflight_report(
    evidence: PreQcExecutionEvidence | None = None,
) -> PreQcPreflightReport:
    """Authenticate supplied typed artifacts and render a redacted report."""

    results = _closed_default_results()
    if evidence is None:
        return _report(results)
    if type(evidence) is not PreQcExecutionEvidence:
        raise PreQcOrchestrationError("pre-QC evidence changed type")
    reauthenticated = False

    historical = evidence.historical_bridge
    if historical is not None:
        try:
            historical = require_reviewed_historical_universe_to_preopen_bridge(
                historical
            )
        except (HistoricalPreopenBridgeError, TypeError, ValueError, OSError):
            historical = None
            results["historical_universe_to_preopen_manifest"] = _invalid(
                "historical_universe_to_preopen_manifest",
                "historical_preopen_bridge_invalid_or_tampered",
            )
        else:
            reauthenticated = True
            _record_historical_bridge(results, historical)

    runtime_bridge = evidence.runtime_bridge
    if runtime_bridge is not None:
        try:
            runtime_bridge = require_streamed_formal_runtime_bridge(runtime_bridge)
        except (FormalStreamingBridgeError, TypeError, ValueError, OSError):
            runtime_bridge = None
            results["streamed_input_to_runtime_manifest"] = _invalid(
                "streamed_input_to_runtime_manifest",
                "streamed_runtime_bridge_invalid_or_tampered",
            )
        else:
            reauthenticated = True
            _record_runtime_bridge(results, runtime_bridge)
            if historical is None:
                results["full_pit_security_session_peer_census"] = _missing(
                    "full_pit_security_session_peer_census",
                    "historical_bridge_required_for_runtime_lineage",
                )
            elif not _historical_runtime_lineage_matches(
                historical, runtime_bridge
            ):
                results["full_pit_security_session_peer_census"] = _invalid(
                    "full_pit_security_session_peer_census",
                    "historical_and_runtime_preopen_lineage_mismatch",
                )
            else:
                results["full_pit_security_session_peer_census"] = _result(
                    "full_pit_security_session_peer_census",
                    GateStatus.SATISFIED,
                    "historical_preopen_and_runtime_lineage_authenticated",
                    artifact_id=historical.bridge_id,
                    artifact_sha256=historical.bridge_sha256,
                )

    terminal = evidence.terminal_disposition_build
    if terminal is not None:
        try:
            terminal = require_formal_terminal_disposition_build(terminal)
        except (
            FormalTerminalDispositionBuildError,
            OSError,
            TypeError,
            ValueError,
        ):
            terminal = None
            results["formal_terminal_disposition_build"] = _invalid(
                "formal_terminal_disposition_build",
                "terminal_disposition_build_invalid_or_tampered",
            )
        else:
            reauthenticated = True
            if historical is None or runtime_bridge is None:
                results["formal_terminal_disposition_build"] = _result(
                    "formal_terminal_disposition_build",
                    GateStatus.NOT_REACHED,
                    "historical_or_runtime_parent_not_authenticated",
                )
            elif (
                terminal.historical_bridge is not historical
                or not _terminal_matches_runtime(terminal, runtime_bridge)
            ):
                results["formal_terminal_disposition_build"] = _invalid(
                    "formal_terminal_disposition_build",
                    "terminal_disposition_parent_identity_mismatch",
                )
            else:
                results["formal_terminal_disposition_build"] = _result(
                    "formal_terminal_disposition_build",
                    GateStatus.SATISFIED,
                    "exhaustive_terminal_disposition_build_authenticated",
                    artifact_id=terminal.build_id,
                    artifact_sha256=terminal.build_sha256,
                )

    power = evidence.authenticated_power_floor
    if power is not None:
        try:
            power = require_authenticated_power_floor_binding(power)
        except (AcceptedRiskPowerCalibrationError, OSError, TypeError, ValueError):
            power = None
            results["accepted_risk_nuisance_power_calibration"] = _invalid(
                "accepted_risk_nuisance_power_calibration",
                "nuisance_power_chain_invalid_or_tampered",
            )
        else:
            reauthenticated = True
            if runtime_bridge is None:
                results["accepted_risk_nuisance_power_calibration"] = _result(
                    "accepted_risk_nuisance_power_calibration",
                    GateStatus.NOT_REACHED,
                    "streamed_runtime_parent_not_authenticated",
                )
            elif not _power_matches_runtime(power, runtime_bridge):
                results["accepted_risk_nuisance_power_calibration"] = _invalid(
                    "accepted_risk_nuisance_power_calibration",
                    "nuisance_power_runtime_identity_mismatch",
                )
            else:
                results["accepted_risk_nuisance_power_calibration"] = _result(
                    "accepted_risk_nuisance_power_calibration",
                    GateStatus.SATISFIED,
                    "nuisance_power_receipt_successor_and_test_census_authenticated",
                    artifact_id=power.binding_id,
                    artifact_sha256=power.binding_sha256,
                )

    submitted = evidence.submission_bridge
    if submitted is not None:
        try:
            submitted = require_streamed_formal_submission_adapter_bridge(submitted)
        except (FormalQcSubmissionError, OSError, TypeError, ValueError):
            submitted = None
            for gate_id in (
                "formal_candidate_review_and_counterreview_pin",
                "detached_owner_execution_signature",
                "live_host_source_closure",
                "concrete_qc_transport_source_binding",
                "exact_one_shot_submission_plan",
                "streamed_post_launch_outcome_path",
            ):
                results[gate_id] = _invalid(
                    gate_id, "streamed_submission_bridge_invalid_or_tampered"
                )
        else:
            reauthenticated = True
            if runtime_bridge is None or not _submission_identities_match(
                submitted,
                runtime_bridge,
                power,
            ):
                for gate_id in (
                    "formal_candidate_review_and_counterreview_pin",
                    "detached_owner_execution_signature",
                    "live_host_source_closure",
                    "concrete_qc_transport_source_binding",
                    "exact_one_shot_submission_plan",
                    "streamed_post_launch_outcome_path",
                ):
                    results[gate_id] = _invalid(
                        gate_id,
                        "submission_runtime_candidate_authority_identity_mismatch",
                    )
            else:
                _record_submission_bridge(results, submitted)
                _record_post_launch_capability(results, submitted)

    return _report(
        results,
        local_filesystem_reauthentication_performed=reauthenticated,
    )


def require_pre_qc_preflight_report(
    value: PreQcPreflightReport,
) -> PreQcPreflightReport:
    if type(value) is not PreQcPreflightReport:
        raise PreQcOrchestrationError("pre-QC report changed type")
    if (
        type(value.gates) is not tuple
        or tuple(item.gate_id for item in value.gates) != GATE_IDS
        or any(type(item) is not PreQcGateResult for item in value.gates)
    ):
        raise PreQcOrchestrationError("pre-QC report gate inventory changed")
    for spec, gate in zip(_GATE_SPECS, value.gates, strict=True):
        gate.__post_init__()
        if (
            gate.phase != spec.phase
            or gate.external is not spec.external
            or gate.blocking
            is not (
                gate.status
                not in {GateStatus.SATISFIED, GateStatus.ADAPTER_ENFORCED}
            )
        ):
            raise PreQcOrchestrationError("pre-QC gate semantics changed")
    raw = value.to_record()
    seed = dict(raw)
    seed["report_id"] = None
    seed["report_sha256"] = None
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    ready = not any(item.blocking for item in value.gates)
    first = next((item.gate_id for item in value.gates if item.blocking), "none")
    bool_fields = (
        value.pre_submission_software_build_ready,
        value.software_build_ready,
        value.physical_data_ready,
        value.review_and_owner_authority_ready,
        value.ready_for_formal_claim,
        value.ready_for_one_shot_submission,
        value.provider_qc_or_outcome_io_performed,
        value.local_filesystem_reauthentication_performed,
        value.provider_credentials_inspected,
        value.qc_credentials_inspected,
        value.outcome_data_accessed,
    )
    if (
        any(type(item) is not bool for item in bool_fields)
        or value.schema != REPORT_SCHEMA
        or value.report_sha256 != digest
        or value.report_id != "arv2-pre-qc-preflight-" + digest[:24]
        or value._canonical_document != _canonical(raw)
        or value.pre_submission_software_build_ready
        != all(
            not value.gates[GATE_IDS.index(item)].blocking
            for item in PRE_SUBMISSION_SOFTWARE_GATE_IDS
        )
        or value.software_build_ready
        != all(
            not value.gates[GATE_IDS.index(item)].blocking
            for item in SOFTWARE_GATE_IDS
        )
        or value.physical_data_ready
        != all(
            not value.gates[GATE_IDS.index(item)].blocking
            for item in PHYSICAL_DATA_GATE_IDS
        )
        or value.review_and_owner_authority_ready
        != all(
            not value.gates[GATE_IDS.index(item)].blocking
            for item in AUTHORITY_GATE_IDS
        )
        or value.ready_for_formal_claim is not ready
        or value.ready_for_one_shot_submission is not ready
        or value.first_blocking_gate_id != first
        or type(value.satisfied_gate_count) is not int
        or value.satisfied_gate_count
        != sum(item.status is GateStatus.SATISFIED for item in value.gates)
        or type(value.blocking_gate_count) is not int
        or value.blocking_gate_count != sum(item.blocking for item in value.gates)
        or value.provider_qc_or_outcome_io_performed is not False
        or value.provider_credentials_inspected is not False
        or value.qc_credentials_inspected is not False
        or value.outcome_data_accessed is not False
    ):
        raise PreQcOrchestrationError("pre-QC report identity changed")
    return value


def render_pre_qc_preflight_report_bytes(value: PreQcPreflightReport) -> bytes:
    return bytes(require_pre_qc_preflight_report(value)._canonical_document)


def _bind_pre_qc_formal_submission_boundary(
    *,
    report_builder,
    report_requirer,
    historical_requirer,
    runtime_requirer,
    terminal_requirer,
    power_requirer,
    submission_requirer,
    power_runtime_matcher,
    terminal_runtime_matcher,
    historical_runtime_matcher,
    submission_identity_matcher,
    post_launch_capability_builder,
    post_launch_capability_matcher,
    owner_registry_status,
    host_closure_verifier,
    claim_once,
    submit_once,
    evidence_type,
    transport_type,
    orchestration_error_type,
    orchestration_blocked_type,
    getpid,
    getframe,
    realpath,
):
    """Seal the irreversible claim/submit path to import-time dependencies.

    The public report builder remains a useful, non-authorizing diagnostic
    surface.  This boundary does not trust that report alone: it independently
    reauthenticates every typed root and every cross-root identity immediately
    before the claim and once more after the claim, before the first QC call.
    Imported dependency names are deliberately not resolved through mutable
    module globals on this path.
    """

    authority_pid = getpid()
    module_name = __name__
    module_path = realpath(__file__)
    module_globals_id = id(globals())
    public_execute = None
    public_execute_bindings: tuple[tuple[str, object], ...] = ()

    def require_same_process() -> None:
        if getpid() != authority_pid:
            raise orchestration_error_type(
                "pre-QC execution boundary belongs to a different process"
            )

    def evidence_roots(value):
        return (
            value.historical_bridge,
            value.terminal_disposition_build,
            value.authenticated_power_floor,
            value.runtime_bridge,
            value.submission_bridge,
        )

    def root_identity_snapshot(historical, terminal, power, runtime, submitted):
        return (
            historical.bridge_id,
            historical.bridge_sha256,
            terminal.build_id,
            terminal.build_sha256,
            power.binding_id,
            power.binding_sha256,
            runtime.bridge_id,
            runtime.bridge_sha256,
            submitted.bridge_id,
            submitted.bridge_sha256,
            submitted.formal_run_candidate.candidate_id,
            submitted.formal_run_candidate.candidate_sha256,
            submitted.reviewed_authority.authority_id,
            submitted.reviewed_authority.authority_sha256,
            submitted.execution_authority.authority_id,
            submitted.execution_authority.authority_sha256,
            submitted.execution_authority.host_code_closure.closure_id,
            submitted.execution_authority.host_code_closure.closure_sha256,
            submitted.plan.plan_id,
            submitted.plan.plan_sha256,
            submitted.authenticated_power_floor.binding_id,
            submitted.authenticated_power_floor.binding_sha256,
            submitted.economic_execution.binding_id,
            submitted.economic_execution.binding_sha256,
            submitted.economic_execution.definition_id,
            submitted.economic_execution.definition_sha256,
            submitted.report_contract.contract_id,
            submitted.report_contract.contract_sha256,
            submitted.report_contract.artifact_sha256,
        )

    def require_current_roots(value, expected=None):
        require_same_process()
        roots = evidence_roots(value)
        if any(item is None for item in roots):
            raise orchestration_error_type(
                "ready preflight omitted a typed execution parent"
            )
        historical, terminal, power, runtime, submitted = roots
        historical = historical_requirer(historical)
        runtime = runtime_requirer(runtime)
        terminal = terminal_requirer(terminal)
        power = power_requirer(power)
        submitted = submission_requirer(submitted)
        if (
            historical is not roots[0]
            or terminal is not roots[1]
            or power is not roots[2]
            or runtime is not roots[3]
            or submitted is not roots[4]
            or historical_runtime_matcher(historical, runtime) is not True
            or terminal.historical_bridge is not historical
            or terminal_runtime_matcher(terminal, runtime) is not True
            or power_runtime_matcher(power, runtime) is not True
            or submission_identity_matcher(submitted, runtime, power) is not True
        ):
            raise orchestration_error_type(
                "pre-QC execution roots changed lineage or identity"
            )
        host_closure_verifier(submitted.execution_authority.host_code_closure)
        capability = post_launch_capability_builder(submitted)
        if post_launch_capability_matcher(capability, submitted) is not True:
            raise orchestration_error_type(
                "streamed post-launch capability changed"
            )
        registry = owner_registry_status()
        counts = registry.get("gate_key_counts") if type(registry) is dict else None
        if (
            type(counts) is not dict
            or type(counts.get("formal_qc_execution")) is not int
            or counts["formal_qc_execution"] != 1
            or type(counts.get("formal_qc_result_read")) is not int
            or counts["formal_qc_result_read"] != 1
        ):
            raise orchestration_error_type(
                "reviewed formal execution or result-read key is not pinned"
            )
        current_roots = evidence_roots(value)
        if any(
            current is not original
            for current, original in zip(current_roots, roots, strict=True)
        ):
            raise orchestration_error_type(
                "pre-QC evidence roots changed during reauthentication"
            )
        snapshot = root_identity_snapshot(historical, terminal, power, runtime, submitted)
        if expected is not None:
            expected_roots, expected_snapshot = expected
            if (
                any(
                    current is not original
                    for current, original in zip(roots, expected_roots, strict=True)
                )
                or snapshot != expected_snapshot
            ):
                raise orchestration_error_type(
                    "pre-QC evidence changed across the formal claim boundary"
                )
        return submitted, (roots, snapshot)

    def exact_public_action_caller() -> None:
        caller = getframe(2)
        try:
            if (
                getpid() != authority_pid
                or public_execute is None
                or caller.f_code is not public_execute.__code__
                or id(caller.f_globals) != module_globals_id
                or caller.f_globals.get("__name__") != module_name
                or realpath(caller.f_code.co_filename) != module_path
                or caller.f_globals.get(
                    "execute_pre_qc_formal_submission_once"
                )
                is not public_execute
                or tuple(caller.f_code.co_freevars)
                != tuple(name for name, _value in public_execute_bindings)
                or any(
                    caller.f_locals.get(name) is not expected
                    for name, expected in public_execute_bindings
                )
            ):
                raise orchestration_error_type(
                    "pre-QC irreversible action caller provenance changed"
                )
        finally:
            del caller

    def invoke_claim(*, candidate, authority, claimed_at_utc):
        exact_public_action_caller()
        return claim_once(
            candidate=candidate,
            authority=authority,
            claimed_at_utc=claimed_at_utc,
        )

    def invoke_submission(
        *, submission_bridge, claim, client, submission_started_at_utc
    ):
        exact_public_action_caller()
        return submit_once(
            submission_bridge=submission_bridge,
            claim=claim,
            client=client,
            submission_started_at_utc=submission_started_at_utc,
        )

    def execute_pre_qc_formal_submission_once(
        *,
        evidence: PreQcExecutionEvidence,
        client: FormalQcTransport,
        claimed_at_utc: str,
        submission_started_at_utc: str,
    ) -> tuple[FormalLookClaim, FormalSubmissionPermit, FormalQcLaunchReceipt]:
        """Claim once and invoke the streamed adapter once after every live gate."""

        require_same_process()
        if type(evidence) is not evidence_type:
            raise orchestration_error_type("pre-QC evidence changed type")
        if type(client) is not transport_type:
            raise orchestration_error_type("exact concrete QC transport is required")

        first = report_requirer(report_builder(evidence))
        if not first.ready_for_one_shot_submission:
            raise orchestration_blocked_type(first)
        submitted, snapshot = require_current_roots(evidence)
        second = report_requirer(report_builder(evidence))
        if not second.ready_for_one_shot_submission:
            raise orchestration_blocked_type(second)
        if first.report_sha256 != second.report_sha256:
            raise orchestration_error_type(
                "pre-QC evidence changed during live reauthentication"
            )

        # Close the old second-report-to-claim TOCTOU window with another exact
        # typed-root pass at the irreversible boundary.
        submitted_before_claim, _ = require_current_roots(evidence, snapshot)
        if submitted_before_claim is not submitted:
            raise orchestration_error_type(
                "submission bridge changed immediately before claim"
            )
        claim = invoke_claim(
            candidate=submitted.formal_run_candidate,
            authority=submitted.reviewed_authority,
            claimed_at_utc=claimed_at_utc,
        )

        # A failed post-claim check intentionally consumes the look but cannot
        # reach QC.  This is the safe disposition for any mutation concurrent
        # with the exclusive filesystem claim.
        require_same_process()
        submitted_after_claim, _ = require_current_roots(evidence, snapshot)
        if submitted_after_claim is not submitted:
            raise orchestration_error_type(
                "submission bridge changed after formal claim"
            )
        permit, launch = invoke_submission(
            submission_bridge=submitted,
            claim=claim,
            client=client,
            submission_started_at_utc=submission_started_at_utc,
        )
        return claim, permit, launch

    public_execute = execute_pre_qc_formal_submission_once
    public_execute_bindings = tuple(
        (name, cell.cell_contents)
        for name, cell in zip(
            public_execute.__code__.co_freevars,
            public_execute.__closure__ or (),
            strict=True,
        )
    )
    return execute_pre_qc_formal_submission_once


execute_pre_qc_formal_submission_once = _bind_pre_qc_formal_submission_boundary(
    report_builder=build_pre_qc_preflight_report,
    report_requirer=require_pre_qc_preflight_report,
    historical_requirer=require_reviewed_historical_universe_to_preopen_bridge,
    runtime_requirer=require_streamed_formal_runtime_bridge,
    terminal_requirer=require_formal_terminal_disposition_build,
    power_requirer=require_authenticated_power_floor_binding,
    submission_requirer=require_streamed_formal_submission_adapter_bridge,
    power_runtime_matcher=_power_matches_runtime,
    terminal_runtime_matcher=_terminal_matches_runtime,
    historical_runtime_matcher=_historical_runtime_lineage_matches,
    submission_identity_matcher=_submission_identities_match,
    post_launch_capability_builder=streamed_formal_post_launch_capability_record,
    post_launch_capability_matcher=_post_launch_capability_matches,
    owner_registry_status=reviewed_owner_signature_registry_status,
    host_closure_verifier=verify_formal_qc_host_closure_live,
    claim_once=claim_formal_run_once,
    submit_once=execute_streamed_formal_qc_submission_once,
    evidence_type=PreQcExecutionEvidence,
    transport_type=FormalQcTransport,
    orchestration_error_type=PreQcOrchestrationError,
    orchestration_blocked_type=PreQcOrchestrationBlocked,
    getpid=os.getpid,
    getframe=sys._getframe,
    realpath=os.path.realpath,
)
del _bind_pre_qc_formal_submission_boundary


def pre_qc_orchestrator_record() -> Mapping[str, object]:
    """Return a static capability record without inspecting external state."""

    return MappingProxyType(
        {
            "schema": SCHEMA,
            "phase_order": PHASES,
            "gate_order": GATE_IDS,
            "deterministic_machine_readable_preflight": True,
            "caller_boolean_authority_accepted": False,
            "caller_string_authority_accepted": False,
            "caller_callback_authority_accepted": False,
            "provider_io_on_import": False,
            "credential_io_on_import": False,
            "quantconnect_io_on_import": False,
            "outcome_io_on_import": False,
            "formal_claim_before_complete_preflight": False,
            "live_file_reauthentication_before_claim": True,
            "sealed_import_time_execution_dependencies": True,
            "same_process_execution_boundary": True,
            "exact_public_action_caller_provenance": True,
            "typed_root_reauthentication_immediately_before_claim": True,
            "typed_root_reauthentication_after_claim_before_qc": True,
            "legacy_materializing_upload_bundle_dependency": False,
            "legacy_stream_iterator_tuple_materialization_permitted": False,
            "historical_universe_bridge_interface_available": True,
            "streamed_runtime_bridge_interface_available": True,
            "sequential_submission_bridge_interface_available": True,
            "streamed_post_launch_capability_requires_exact_submission_bridge": True,
            "streamed_post_launch_capability_interface_available": True,
            "static_boolean_can_satisfy_post_launch_gate": False,
            "software_build_ready_scope": (
                "typed_launch_status_separate_result_read_and_evaluation_path"
            ),
            "pre_submission_software_build_ready_scope": (
                "historical_streamed_input_and_runtime_projection_only"
            ),
            "conditional_formal_submission_available": True,
        }
    )


__all__ = (
    "AUTHORITY_GATE_IDS",
    "GATE_IDS",
    "GateStatus",
    "AuthenticatedPowerFloorBinding",
    "FormalTerminalDispositionBuild",
    "PHASES",
    "PHYSICAL_DATA_GATE_IDS",
    "PRE_SUBMISSION_SOFTWARE_GATE_IDS",
    "PreQcExecutionEvidence",
    "PreQcGateResult",
    "PreQcOrchestrationBlocked",
    "PreQcOrchestrationError",
    "PreQcPreflightReport",
    "REPORT_SCHEMA",
    "ReviewedHistoricalUniverseToPreopenBridge",
    "SCHEMA",
    "SOFTWARE_GATE_IDS",
    "STREAMED_POST_LAUNCH_CAPABILITY_SCHEMA",
    "StreamedFormalRuntimeBridge",
    "StreamedFormalSubmissionAdapterBridge",
    "build_pre_qc_preflight_report",
    "execute_pre_qc_formal_submission_once",
    "pre_qc_orchestrator_record",
    "render_pre_qc_preflight_report_bytes",
    "require_pre_qc_preflight_report",
)
