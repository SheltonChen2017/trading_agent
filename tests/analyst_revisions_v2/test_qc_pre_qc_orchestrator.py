"""Focused offline tests for the final ARV2 pre-QC boundary."""
from __future__ import annotations

import ast
import dataclasses
import json
import os
import re
import subprocess
import sys
import types
from datetime import date
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import pre_qc_orchestrator as module
from research.analyst_revisions_v2_qc import formal_runtime_projection as runtime
from research.analyst_revisions_v2_qc import formal_streaming_input as streaming
from research.analyst_revisions_v2_qc import formal_input_composer
from research.analyst_revisions_v2_qc import production_evidence_composer
from research.analyst_revisions_v2 import (
    preopen_control_acquisition as preopen_core,
)
from research.analyst_revisions_v2 import (
    production_evidence_acquisition as evidence_core,
)
from research.analyst_revisions_v2 import production_truth_gate as truth_module
from research.analyst_revisions_v2_qc.formal_qc_transport import FormalQcTransport
from research.analyst_revisions_v2_qc.formal_economic_execution_definition import (
    build_formal_economic_execution_binding,
    build_formal_economic_execution_definition,
)
from research.analyst_revisions_v2_qc.formal_runtime_projection import (
    FORMAL_EVALUATOR_PROJECT_PATH,
)
from research.analyst_revisions_v2_qc.formal_streaming_bridge import (
    build_streamed_formal_runtime_bridge,
    build_streamed_formal_runtime_resource_candidate,
    load_streamed_formal_runtime_capacity_binding,
)
from research.analyst_revisions_v2_qc.formal_streaming_input import (
    begin_streamed_production_scoring,
    build_streamed_formal_input_candidate_from_reviewed_lifecycle,
)
from research.analyst_revisions_v2_qc.pre_qc_orchestrator import (
    AUTHORITY_GATE_IDS,
    GATE_IDS,
    PHASES,
    PHYSICAL_DATA_GATE_IDS,
    PRE_SUBMISSION_SOFTWARE_GATE_IDS,
    SOFTWARE_GATE_IDS,
    GateStatus,
    PreQcExecutionEvidence,
    PreQcOrchestrationBlocked,
    build_pre_qc_preflight_report,
    pre_qc_orchestrator_record,
    render_pre_qc_preflight_report_bytes,
    require_pre_qc_preflight_report,
)
from scripts.build_arv2_historical_preopen_bridge import (
    build_reviewed_historical_universe_to_preopen_bridge,
)
from tests.analyst_revisions_v2 import test_power_calibration_receipt as power_helpers
from tests.analyst_revisions_v2.test_historical_preopen_bridge import (
    _discovery_receipt,
    _physical_candidate,
)
from tests.analyst_revisions_v2.test_qc_formal_streaming_input import (
    _full_sparse_formal_fixture,
    _global_contract,
    _runtime_limits,
    _write_runtime_capacity_review,
    _write_streamed_bridge_review,
)
from tests.analyst_revisions_v2 import test_production_scoring as scoring_helpers
from tests.analyst_revisions_v2.test_production_scoring import (
    _offline_physical_requirer,
)
from tests.analyst_revisions_v2.test_qc_formal_economic_execution_definition import (
    _stock,
)
from research.analyst_revisions_v2 import power_calibration_receipt as power_module


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research/analyst_revisions_v2_qc/pre_qc_orchestrator.py"


def _closure_cell(value: object):
    def capture():
        return value

    assert capture.__closure__ is not None
    return capture.__closure__[0]


def _closure_value(function, name: str):
    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    return cells[name].cell_contents


def _with_closure_values(function, **replacements):
    """Clone one sealed wrapper with explicit offline-only test cells."""

    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    assert set(replacements).issubset(cells)
    rebound = types.FunctionType(
        function.__code__,
        function.__globals__,
        function.__name__,
        function.__defaults__,
        tuple(
            _closure_cell(replacements[freevar])
            if freevar in replacements
            else cells[freevar]
            for freevar in function.__code__.co_freevars
        ),
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = function.__annotations__
    return rebound


def _gate(report, gate_id):
    return report.gates[GATE_IDS.index(gate_id)]


def _fully_open_report():
    results = module._closed_default_results()
    for gate_id in GATE_IDS:
        if results[gate_id].status is GateStatus.ADAPTER_ENFORCED:
            continue
        results[gate_id] = module._result(
            gate_id,
            GateStatus.SATISFIED,
            "authenticated_test_fixture",
        )
    return module._report(
        results,
        local_filesystem_reauthentication_performed=True,
    )


def _post_launch_capability(submitted, **overrides):
    record = {
        "schema": module.STREAMED_POST_LAUNCH_CAPABILITY_SCHEMA,
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
    record.update(overrides)
    return record


def _build_offline_physical_preflight_report(evidence, monkeypatch):
    """Reauthenticate synthetic receipts only through the test-local vault."""

    require_preopen = lambda value: _offline_physical_requirer(
        "preopen", value
    )
    require_evidence = lambda value: _offline_physical_requirer(
        "evidence", value
    )
    with monkeypatch.context() as patches:
        patches.setattr(
            preopen_core,
            "require_reviewed_preopen_control_acquisition_receipt",
            require_preopen,
        )
        patches.setattr(
            evidence_core,
            "require_reviewed_preopen_control_acquisition_receipt",
            require_preopen,
        )
        patches.setattr(
            truth_module,
            "require_reviewed_preopen_control_acquisition_receipt",
            require_preopen,
        )
        patches.setattr(
            truth_module,
            "require_production_evidence_acquisition_receipt",
            require_evidence,
        )
        patches.setattr(
            streaming,
            "require_reviewed_preopen_control_acquisition_receipt",
            require_preopen,
        )
        patches.setattr(
            streaming,
            "require_production_evidence_acquisition_receipt",
            require_evidence,
        )
        patches.setattr(
            formal_input_composer,
            "require_reviewed_preopen_control_acquisition_receipt",
            require_preopen,
        )
        patches.setattr(
            production_evidence_composer,
            "require_reviewed_preopen_control_acquisition_receipt",
            require_preopen,
        )
        return build_pre_qc_preflight_report(evidence)


@pytest.fixture(scope="module")
def authentic_software_stack(tmp_path_factory):
    """Build the real reviewed historical -> streamed runtime object graph."""

    root = tmp_path_factory.mktemp("pre-qc-authentic-software")
    patches = pytest.MonkeyPatch()
    power_parents = power_helpers.parents.__wrapped__()
    retained_power_parents = {}
    original_load = power_module.load_power_calibration_receipt
    physical_lifecycle = (
        scoring_helpers._install_offline_physical_receipt_requires.__wrapped__(
            patches
        )
    )
    next(physical_lifecycle)
    patches.setattr(
        streaming,
        "require_reviewed_preopen_control_acquisition_receipt",
        lambda value: _offline_physical_requirer("preopen", value),
    )
    patches.setattr(
        streaming,
        "require_production_evidence_acquisition_receipt",
        lambda value: _offline_physical_requirer("evidence", value),
    )

    patches.setattr(
        power_helpers.parents,
        "__wrapped__",
        lambda: power_parents,
    )

    def retain_loaded_power_parents(*args, **kwargs):
        retained_power_parents.update(kwargs)
        loaded = original_load(*args, **kwargs)
        retained_power_parents["loaded_receipt"] = loaded
        return loaded

    patches.setattr(
        power_module,
        "load_power_calibration_receipt",
        retain_loaded_power_parents,
    )
    try:
        historical_root = root / "historical"
        historical_root.mkdir()
        discovery = _discovery_receipt(patches, historical_root)
        physical = _physical_candidate(patches, historical_root)
        historical = build_reviewed_historical_universe_to_preopen_bridge(
            discovery,
            physical,
            historical_root / "bridge",
        )

        runtime_root = root / "runtime"
        runtime_root.mkdir()
        (
            archive,
            accepted_risk,
            formal_power,
            power_floor,
            _legacy_terminal_package,
            loaded_power,
            loaded_power_parents,
        ) = _full_sparse_formal_fixture(runtime_root)
        scorer = begin_streamed_production_scoring(
            archive=archive,
            production_evidence_receipt=(
                archive.capacity.production_evidence_receipt
            ),
            global_contract=_global_contract(),
        )
        streamed_input = (
                build_streamed_formal_input_candidate_from_reviewed_lifecycle(
                    scoring_builder=scorer,
                    accepted_risk=accepted_risk,
                    formal_power=formal_power,
                    power_floor=power_floor,
                    economic_execution=build_formal_economic_execution_binding(
                        build_formal_economic_execution_definition(_stock())
                    ),
                    historical_bridge=historical,
                terminal_output_directory=runtime_root / "terminal",
                benchmark_security_id="security-00",
                calculation_as_of_date=date(2026, 9, 12),
                output_directory=runtime_root / "formal-shards",
            )
        )
        resource = build_streamed_formal_runtime_resource_candidate(
            streamed_input=streamed_input,
            maximum_dynamic_subscription_count=2,
            proposed_runtime_limits=_runtime_limits(
                max_dynamic_subscription_count=2,
                max_node_memory_byte_count=4_000_000_000,
            ),
        )
        runtime_review = _write_runtime_capacity_review(runtime_root, resource)
        bridge_review = _write_streamed_bridge_review(
            runtime_root,
            resource,
            runtime_review,
        )
        capacity = load_streamed_formal_runtime_capacity_binding(
            resource_candidate=resource,
            runtime_capacity_reviewed_receipt_path=runtime_review,
            streamed_bridge_reviewed_receipt_path=bridge_review,
        )
        runtime_bridge = build_streamed_formal_runtime_bridge(
            resource_candidate=resource,
            capacity=capacity,
            formal_evaluator_source=(ROOT / FORMAL_EVALUATOR_PROJECT_PATH).read_bytes(),
            cloud_evaluator_source=(
                ROOT / runtime.CLOUD_EVALUATOR_PROJECT_PATH
            ).read_bytes(),
        )
    except BaseException:
        try:
            next(physical_lifecycle)
        except StopIteration:
            pass
        patches.undo()
        raise
    patches.undo()

    # These references are intentionally retained: every public validator uses
    # weak registries so a child cannot survive after an authenticated parent is
    # released.
    keepalive = (
        power_parents,
        retained_power_parents,
        loaded_power,
        loaded_power_parents,
        discovery,
        physical,
        archive,
        accepted_risk,
        formal_power,
        power_floor,
        resource,
        capacity,
    )
    try:
        yield types.SimpleNamespace(
            historical=historical,
            terminal=streamed_input.terminal_build,
            runtime=runtime_bridge,
            keepalive=keepalive,
        )
    finally:
        try:
            next(physical_lifecycle)
        except StopIteration:
            pass


def test_default_preflight_is_deterministic_canonical_and_names_every_gate():
    first = build_pre_qc_preflight_report()
    second = build_pre_qc_preflight_report()

    assert first == second
    assert require_pre_qc_preflight_report(first) is first
    payload = render_pre_qc_preflight_report_bytes(first)
    raw = json.loads(payload)
    assert payload.endswith(b"\n")
    assert payload == (
        json.dumps(
            raw,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    assert tuple(raw["gate_order"]) == GATE_IDS
    assert tuple(raw["phase_order"]) == PHASES
    assert tuple(item["gate_id"] for item in raw["gates"]) == GATE_IDS
    assert first.first_blocking_gate_id == "massive_accepted_risk_capture_pair"
    assert first.pre_submission_software_build_ready is False
    assert first.software_build_ready is False
    assert first.physical_data_ready is False
    assert first.review_and_owner_authority_ready is False
    assert first.ready_for_formal_claim is False
    assert first.ready_for_one_shot_submission is False
    assert first.provider_qc_or_outcome_io_performed is False
    assert first.local_filesystem_reauthentication_performed is False
    assert first.provider_credentials_inspected is False
    assert first.qc_credentials_inspected is False
    assert first.outcome_data_accessed is False


def test_default_report_separates_software_physical_and_authority_gates():
    report = build_pre_qc_preflight_report()

    assert set(SOFTWARE_GATE_IDS).issubset(GATE_IDS)
    assert set(PRE_SUBMISSION_SOFTWARE_GATE_IDS).issubset(SOFTWARE_GATE_IDS)
    assert set(PHYSICAL_DATA_GATE_IDS).issubset(GATE_IDS)
    assert set(AUTHORITY_GATE_IDS).issubset(GATE_IDS)
    for gate_id in (
        "historical_universe_to_preopen_manifest",
        "formal_terminal_disposition_build",
        "accepted_risk_nuisance_power_calibration",
        "streamed_input_to_runtime_manifest",
        "sequential_stream_to_submission_adapter",
        "streamed_post_launch_outcome_path",
        "formal_candidate_review_and_counterreview_pin",
        "detached_owner_execution_signature",
        "exact_one_shot_submission_plan",
    ):
        assert _gate(report, gate_id).status is GateStatus.MISSING_ARTIFACT
    assert _gate(
        report, "streamed_post_launch_outcome_path"
    ).reason_code == "typed_streamed_submission_bridge_not_supplied"
    assert _gate(
        report, "reviewed_owner_public_key_pin"
    ).status is GateStatus.SATISFIED
    for gate_id in (
        "exclusive_formal_look_claim_ledger",
        "qc_credentials_and_account_authentication",
        "qc_project_object_compile_backtest_actions",
    ):
        assert _gate(report, gate_id).status is GateStatus.ADAPTER_ENFORCED


def test_execution_evidence_exposes_only_typed_object_graph_roots():
    fields = {
        item.name: item.type
        for item in dataclasses.fields(PreQcExecutionEvidence)
    }

    assert tuple(fields) == (
        "historical_bridge",
        "terminal_disposition_build",
        "authenticated_power_floor",
        "runtime_bridge",
        "submission_bridge",
    )
    with pytest.raises(TypeError):
        PreQcExecutionEvidence(approved=True)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        PreQcExecutionEvidence(organization_id="caller")  # type: ignore[call-arg]


def test_unauthenticated_objects_cannot_open_any_gate():
    evidence = PreQcExecutionEvidence(
        historical_bridge=object(),  # type: ignore[arg-type]
        terminal_disposition_build=object(),  # type: ignore[arg-type]
        authenticated_power_floor=object(),  # type: ignore[arg-type]
        runtime_bridge=object(),  # type: ignore[arg-type]
        submission_bridge=object(),  # type: ignore[arg-type]
    )
    report = build_pre_qc_preflight_report(evidence)

    assert report.ready_for_formal_claim is False
    assert report.ready_for_one_shot_submission is False
    assert _gate(
        report, "historical_universe_to_preopen_manifest"
    ).status is GateStatus.INVALID
    assert _gate(
        report, "formal_terminal_disposition_build"
    ).status is GateStatus.INVALID
    assert _gate(
        report, "accepted_risk_nuisance_power_calibration"
    ).status is GateStatus.INVALID
    assert _gate(
        report, "streamed_input_to_runtime_manifest"
    ).status is GateStatus.INVALID
    assert _gate(
        report, "exact_one_shot_submission_plan"
    ).status is GateStatus.INVALID
    assert _gate(
        report, "streamed_post_launch_outcome_path"
    ).status is GateStatus.INVALID


def test_authentic_synthetic_stack_makes_pre_submission_software_ready(
    authentic_software_stack,
    monkeypatch,
):
    legacy_calls = []

    def forbidden_legacy_materializer(*_args, **_kwargs):
        legacy_calls.append(True)
        raise AssertionError("legacy tuple materializer must not be called")

    monkeypatch.setattr(
        streaming,
        "iter_formal_qc_compressed_shards",
        forbidden_legacy_materializer,
    )
    report = _build_offline_physical_preflight_report(
        PreQcExecutionEvidence(
            historical_bridge=authentic_software_stack.historical,
            terminal_disposition_build=authentic_software_stack.terminal,
            runtime_bridge=authentic_software_stack.runtime,
        ),
        monkeypatch,
    )

    assert require_pre_qc_preflight_report(report) is report
    assert report.pre_submission_software_build_ready is True
    assert report.software_build_ready is False
    assert report.local_filesystem_reauthentication_performed is True
    assert all(
        _gate(report, gate_id).status is GateStatus.SATISFIED
        for gate_id in PRE_SUBMISSION_SOFTWARE_GATE_IDS
    )
    assert _gate(
        report, "streamed_post_launch_outcome_path"
    ).status is GateStatus.MISSING_ARTIFACT
    assert _gate(
        report, "formal_terminal_disposition_build"
    ).status is GateStatus.SATISFIED
    assert _gate(
        report, "accepted_risk_nuisance_power_calibration"
    ).status is GateStatus.MISSING_ARTIFACT
    assert _gate(
        report, "formal_candidate_review_and_counterreview_pin"
    ).status is GateStatus.MISSING_ARTIFACT
    assert report.physical_data_ready is False
    assert report.review_and_owner_authority_ready is False
    assert report.ready_for_formal_claim is False
    assert report.ready_for_one_shot_submission is False
    assert legacy_calls == []


@pytest.mark.parametrize("supply_different_power", (False, True))
def test_submission_power_identity_mismatch_closes_launch_before_claim_or_transport(
    authentic_software_stack,
    monkeypatch,
    supply_different_power,
):
    runtime_bridge = authentic_software_stack.runtime
    streamed = runtime_bridge.resource_candidate.streamed_input
    different_power = types.SimpleNamespace(
        binding_id="different-authenticated-power",
        binding_sha256="d" * 64,
        power_floor=runtime_bridge.formal_run_candidate.power_floor,
        formal_power=streamed.formal_power,
        formal_census=types.SimpleNamespace(scoring_artifact=streamed.scoring),
        scoring_artifact_id=streamed.scoring.artifact_id,
        scoring_artifact_sha256=streamed.scoring.artifact_sha256,
    )
    submission_power = object()
    authority = types.SimpleNamespace(
        authority_id="reviewed-authority",
        authority_sha256="a" * 64,
    )
    execution = types.SimpleNamespace(
        candidate_id=runtime_bridge.formal_run_candidate.candidate_id,
        candidate_sha256=runtime_bridge.formal_run_candidate.candidate_sha256,
        runtime_bridge_id=runtime_bridge.bridge_id,
        runtime_bridge_sha256=runtime_bridge.bridge_sha256,
    )
    plan = types.SimpleNamespace(
        runtime_bridge=runtime_bridge,
        execution_authority=execution,
        candidate_id=runtime_bridge.formal_run_candidate.candidate_id,
        candidate_sha256=runtime_bridge.formal_run_candidate.candidate_sha256,
        reviewed_authority_id=authority.authority_id,
    )
    submitted = types.SimpleNamespace(
        runtime_bridge=runtime_bridge,
        formal_run_candidate=runtime_bridge.formal_run_candidate,
        reviewed_authority=authority,
        execution_authority=execution,
        authenticated_power_floor=submission_power,
        plan=plan,
        sequential_upload_primitive_present=True,
        full_payload_tuple_materialized=False,
        external_action_performed=False,
    )
    monkeypatch.setattr(
        module,
        "require_streamed_formal_submission_adapter_bridge",
        lambda value: submitted if value is submitted else None,
    )
    monkeypatch.setattr(
        module,
        "streamed_formal_post_launch_capability_record",
        lambda _value: pytest.fail(
            "post-launch capability must not run for mismatched parents"
        ),
    )
    if supply_different_power:
        monkeypatch.setattr(
            module,
            "require_authenticated_power_floor_binding",
            lambda value: different_power if value is different_power else None,
        )
    evidence = PreQcExecutionEvidence(
        historical_bridge=authentic_software_stack.historical,
        terminal_disposition_build=authentic_software_stack.terminal,
        authenticated_power_floor=(
            different_power if supply_different_power else None
        ),  # type: ignore[arg-type]
        runtime_bridge=runtime_bridge,
        submission_bridge=submitted,  # type: ignore[arg-type]
    )

    report = _build_offline_physical_preflight_report(evidence, monkeypatch)
    launch_gates = (
        "formal_candidate_review_and_counterreview_pin",
        "detached_owner_execution_signature",
        "live_host_source_closure",
        "concrete_qc_transport_source_binding",
        "exact_one_shot_submission_plan",
        "streamed_post_launch_outcome_path",
    )
    assert all(
        _gate(report, gate_id).status is GateStatus.INVALID
        for gate_id in launch_gates
    )
    assert _gate(
        report, "accepted_risk_nuisance_power_calibration"
    ).status is (
        GateStatus.SATISFIED
        if supply_different_power
        else GateStatus.MISSING_ARTIFACT
    )
    assert report.ready_for_formal_claim is False
    assert report.ready_for_one_shot_submission is False

    calls = {"claim": 0, "adapter": 0, "http": 0}

    def forbidden_claim(**_kwargs):
        calls["claim"] += 1
        raise AssertionError("mismatched power must not spend claim")

    def forbidden_adapter(**_kwargs):
        calls["adapter"] += 1
        raise AssertionError("mismatched power must not submit")

    def forbidden_http(*_args):
        calls["http"] += 1
        raise AssertionError("mismatched power must not reach transport")

    monkeypatch.setattr(module, "claim_formal_run_once", forbidden_claim)
    monkeypatch.setattr(
        module,
        "execute_streamed_formal_qc_submission_once",
        forbidden_adapter,
    )
    client = FormalQcTransport(http_transport=forbidden_http, clock=lambda: 1)
    with pytest.raises(PreQcOrchestrationBlocked):
        module.execute_pre_qc_formal_submission_once(
            evidence=evidence,
            client=client,
            claimed_at_utc="2026-09-12T12:00:00Z",
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )
    assert calls == {"claim": 0, "adapter": 0, "http": 0}


@pytest.mark.parametrize(
    "overrides",
    (
        {"schema": "changed-capability-schema"},
        {"runtime_bridge_id": "different-runtime"},
        {"submission_adapter_bridge_sha256": "d" * 64},
        {"authenticated_power_floor_id": "different-power"},
        {"economic_execution_binding_sha256": "2" * 64},
        {"economic_execution_definition_id": "different-definition"},
        {"formal_report_contract_sha256": "3" * 64},
        {"formal_report_contract_artifact_sha256": "4" * 64},
        {
            "identity_status_only_value_selection_with_include_statistics_false": (
                False
            )
        },
        {"root_authenticated_26_object_report_family_read": False},
        {"separate_owner_signed_result_read_gate": False},
        {"one_use_selected_summary_statistics_only_read": False},
        {"builder_authenticated_summary_result_receipt": False},
        {"formal_evaluation_bridge_receipt_compatible": False},
        {"process_bound_power_authority": False},
        {"logs_charts_orders_trades_access": True},
        {"unexpected_capability": True},
    ),
)
def test_post_launch_capability_requires_exact_bound_contract(
    monkeypatch,
    overrides,
):
    submitted = types.SimpleNamespace(
        bridge_id="streamed-submission-bridge",
        bridge_sha256="a" * 64,
        runtime_bridge=types.SimpleNamespace(
            bridge_id="streamed-runtime-bridge",
            bridge_sha256="b" * 64,
        ),
        authenticated_power_floor=types.SimpleNamespace(
            binding_id="authenticated-power-floor",
            binding_sha256="c" * 64,
        ),
        economic_execution=types.SimpleNamespace(
            binding_id="economic-execution",
            binding_sha256="d" * 64,
            definition_id="economic-definition",
            definition_sha256="e" * 64,
        ),
        report_contract=types.SimpleNamespace(
            contract_id="formal-report-contract",
            contract_sha256="f" * 64,
            artifact_sha256="1" * 64,
        ),
    )
    monkeypatch.setattr(
        module,
        "streamed_formal_post_launch_capability_record",
        lambda actual: _post_launch_capability(actual, **overrides),
    )
    results = module._closed_default_results()

    module._record_post_launch_capability(results, submitted)

    assert _gate(
        module._report(results), "streamed_post_launch_outcome_path"
    ).status is GateStatus.INVALID


def test_exact_post_launch_capability_completes_full_software_gate(monkeypatch):
    submitted = types.SimpleNamespace(
        bridge_id="streamed-submission-bridge",
        bridge_sha256="a" * 64,
        runtime_bridge=types.SimpleNamespace(
            bridge_id="streamed-runtime-bridge",
            bridge_sha256="b" * 64,
        ),
        authenticated_power_floor=types.SimpleNamespace(
            binding_id="authenticated-power-floor",
            binding_sha256="c" * 64,
        ),
        economic_execution=types.SimpleNamespace(
            binding_id="economic-execution",
            binding_sha256="d" * 64,
            definition_id="economic-definition",
            definition_sha256="e" * 64,
        ),
        report_contract=types.SimpleNamespace(
            contract_id="formal-report-contract",
            contract_sha256="f" * 64,
            artifact_sha256="1" * 64,
        ),
    )
    calls = []

    def capability(actual):
        calls.append(actual)
        return _post_launch_capability(actual)

    monkeypatch.setattr(
        module,
        "streamed_formal_post_launch_capability_record",
        capability,
    )
    results = module._closed_default_results()
    for gate_id in PRE_SUBMISSION_SOFTWARE_GATE_IDS:
        results[gate_id] = module._result(
            gate_id,
            GateStatus.SATISFIED,
            "authenticated_test_fixture",
        )

    module._record_post_launch_capability(results, submitted)
    report = module._report(results)

    assert calls == [submitted]
    assert report.pre_submission_software_build_ready is True
    assert report.software_build_ready is True
    assert _gate(
        report, "streamed_post_launch_outcome_path"
    ).status is GateStatus.SATISFIED
    assert report.ready_for_formal_claim is False


def test_post_launch_gate_blocks_claim_and_adapter(monkeypatch):
    results = module._closed_default_results()
    for gate_id in GATE_IDS:
        if (
            gate_id == "streamed_post_launch_outcome_path"
            or results[gate_id].status is GateStatus.ADAPTER_ENFORCED
        ):
            continue
        results[gate_id] = module._result(
            gate_id,
            GateStatus.SATISFIED,
            "authenticated_test_fixture",
        )
    report = module._report(results)
    assert report.first_blocking_gate_id == "streamed_post_launch_outcome_path"
    assert report.pre_submission_software_build_ready is True
    assert report.software_build_ready is False

    calls = {"claim": 0, "adapter": 0, "http": 0}
    monkeypatch.setattr(
        module,
        "build_pre_qc_preflight_report",
        lambda _evidence: report,
    )

    def forbidden_claim(**_kwargs):
        calls["claim"] += 1
        raise AssertionError("closed post-launch path must not spend claim")

    def forbidden_adapter(**_kwargs):
        calls["adapter"] += 1
        raise AssertionError("closed post-launch path must not submit")

    def forbidden_http(*_args):
        calls["http"] += 1
        raise AssertionError("closed post-launch path must not use transport")

    monkeypatch.setattr(module, "claim_formal_run_once", forbidden_claim)
    monkeypatch.setattr(
        module,
        "execute_streamed_formal_qc_submission_once",
        forbidden_adapter,
    )
    client = FormalQcTransport(http_transport=forbidden_http, clock=lambda: 1)
    with pytest.raises(PreQcOrchestrationBlocked) as raised:
        module.execute_pre_qc_formal_submission_once(
            evidence=PreQcExecutionEvidence(),
            client=client,
            claimed_at_utc="2026-09-12T12:00:00Z",
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )
    # The production action captured the real report builder at import.  The
    # rebound diagnostic global above is inert on the irreversible path.
    assert raised.value.report.first_blocking_gate_id == (
        "massive_accepted_risk_capture_pair"
    )
    assert calls == {"claim": 0, "adapter": 0, "http": 0}


def test_authentic_runtime_object_tamper_closes_the_software_path(
    authentic_software_stack,
):
    runtime_bridge = authentic_software_stack.runtime
    original_id = runtime_bridge.bridge_id
    object.__setattr__(runtime_bridge, "bridge_id", original_id + "-tampered")
    try:
        report = build_pre_qc_preflight_report(
            PreQcExecutionEvidence(
                historical_bridge=authentic_software_stack.historical,
                terminal_disposition_build=authentic_software_stack.terminal,
                runtime_bridge=runtime_bridge,
            )
        )
    finally:
        object.__setattr__(runtime_bridge, "bridge_id", original_id)

    assert report.software_build_ready is False
    assert report.ready_for_formal_claim is False
    assert _gate(
        report, "streamed_input_to_runtime_manifest"
    ).status is GateStatus.INVALID


def test_live_physical_shard_tamper_is_reauthenticated_before_readiness(
    authentic_software_stack,
):
    runtime_bridge = authentic_software_stack.runtime
    shard_path = (
        runtime_bridge.resource_candidate.streamed_input.shards.shard_paths[0]
    )
    payload = bytearray(shard_path.read_bytes())
    payload[-1] ^= 1
    shard_path.write_bytes(payload)

    report = build_pre_qc_preflight_report(
        PreQcExecutionEvidence(
            historical_bridge=authentic_software_stack.historical,
            terminal_disposition_build=authentic_software_stack.terminal,
            runtime_bridge=runtime_bridge,
        )
    )

    assert report.software_build_ready is False
    assert report.ready_for_formal_claim is False
    assert _gate(
        report,
        "streamed_input_to_runtime_manifest",
    ).status is GateStatus.INVALID


def test_closed_preflight_refuses_before_claim_adapter_or_transport(monkeypatch):
    calls = {"claim": 0, "adapter": 0, "http": 0}

    def forbidden_claim(**_kwargs):
        calls["claim"] += 1
        raise AssertionError("formal look must not be claimed")

    def forbidden_adapter(**_kwargs):
        calls["adapter"] += 1
        raise AssertionError("one-shot adapter must not be called")

    def forbidden_http(*_args):
        calls["http"] += 1
        raise AssertionError("transport must remain inert")

    monkeypatch.setattr(module, "claim_formal_run_once", forbidden_claim)
    monkeypatch.setattr(
        module,
        "execute_streamed_formal_qc_submission_once",
        forbidden_adapter,
    )
    transport = FormalQcTransport(http_transport=forbidden_http, clock=lambda: 1)

    with pytest.raises(PreQcOrchestrationBlocked) as raised:
        module.execute_pre_qc_formal_submission_once(
            evidence=PreQcExecutionEvidence(),
            client=transport,
            claimed_at_utc="2026-09-12T12:00:00Z",
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )
    assert raised.value.report.first_blocking_gate_id == (
        "massive_accepted_risk_capture_pair"
    )
    assert calls == {"claim": 0, "adapter": 0, "http": 0}


def test_fully_open_preflight_reauthenticates_then_calls_streamed_adapter_once():
    trace = []
    historical = object()
    terminal = object()
    power = object()
    runtime_bridge = object()
    candidate = object()
    reviewed_authority = object()
    submitted = types.SimpleNamespace(
        runtime_bridge=runtime_bridge,
        formal_run_candidate=candidate,
        reviewed_authority=reviewed_authority,
        authenticated_power_floor=power,
        execution_authority=object(),
    )
    evidence = PreQcExecutionEvidence(
        historical_bridge=historical,  # type: ignore[arg-type]
        terminal_disposition_build=terminal,  # type: ignore[arg-type]
        authenticated_power_floor=power,  # type: ignore[arg-type]
        runtime_bridge=runtime_bridge,  # type: ignore[arg-type]
        submission_bridge=submitted,  # type: ignore[arg-type]
    )
    report = _fully_open_report()
    assert report.pre_submission_software_build_ready is True
    assert report.software_build_ready is True
    snapshot = (
        (historical, terminal, power, runtime_bridge, submitted),
        ("offline-test-identity",),
    )

    def report_builder(actual):
        assert actual is evidence
        trace.append("report")
        return report

    def require_roots(actual, expected=None):
        assert actual is evidence
        if expected is not None:
            assert expected == snapshot
        trace.append("roots")
        return submitted, snapshot

    claim = object()
    permit = object()
    launch = object()

    def claim_once(**kwargs):
        assert kwargs["candidate"] is candidate
        assert kwargs["authority"] is reviewed_authority
        trace.append("claim")
        return claim

    def streamed_once(**kwargs):
        assert kwargs["submission_bridge"] is submitted
        assert kwargs["claim"] is claim
        trace.append("streamed_adapter")
        return permit, launch

    action = _with_closure_values(
        module.execute_pre_qc_formal_submission_once,
        report_builder=report_builder,
        require_current_roots=require_roots,
        invoke_claim=claim_once,
        invoke_submission=streamed_once,
    )
    http_calls = []
    transport = FormalQcTransport(
        http_transport=lambda *args: http_calls.append(args),
        clock=lambda: 1,
    )

    actual = action(
        evidence=evidence,
        client=transport,
        claimed_at_utc="2026-09-12T12:00:00Z",
        submission_started_at_utc="2026-09-12T12:00:01Z",
    )

    assert actual == (claim, permit, launch)
    assert trace == [
        "report",
        "roots",
        "report",
        "roots",
        "claim",
        "roots",
        "streamed_adapter",
    ]
    assert trace.count("claim") == trace.count("streamed_adapter") == 1
    assert http_calls == []


def test_rebound_report_and_action_globals_cannot_open_closed_evidence(monkeypatch):
    report = _fully_open_report()
    open_results = {item.gate_id: item for item in report.gates}
    calls = {"claim": 0, "adapter": 0, "http": 0}

    # The captured real report builder still resolves some diagnostic helpers
    # through its module.  Even if that diagnostic surface is made to report an
    # open gate set, the sealed action performs its own captured typed-root pass.
    monkeypatch.setattr(
        module,
        "_closed_default_results",
        lambda: dict(open_results),
    )

    def fake_claim(**_kwargs):
        calls["claim"] += 1
        return object()

    def fake_adapter(**_kwargs):
        calls["adapter"] += 1
        return object(), object()

    monkeypatch.setattr(module, "claim_formal_run_once", fake_claim)
    monkeypatch.setattr(
        module,
        "execute_streamed_formal_qc_submission_once",
        fake_adapter,
    )
    transport = FormalQcTransport(
        http_transport=lambda *_args: calls.__setitem__("http", calls["http"] + 1),
        clock=lambda: 1,
    )

    with pytest.raises(
        module.PreQcOrchestrationError,
        match="omitted a typed execution parent",
    ):
        module.execute_pre_qc_formal_submission_once(
            evidence=PreQcExecutionEvidence(),
            client=transport,
            claimed_at_utc="2026-09-12T12:00:00Z",
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )
    assert calls == {"claim": 0, "adapter": 0, "http": 0}


def test_root_change_after_second_report_refuses_before_claim_or_transport():
    report = _fully_open_report()
    original_submission = object()
    replacement_submission = object()
    evidence = PreQcExecutionEvidence(
        historical_bridge=object(),  # type: ignore[arg-type]
        terminal_disposition_build=object(),  # type: ignore[arg-type]
        authenticated_power_floor=object(),  # type: ignore[arg-type]
        runtime_bridge=object(),  # type: ignore[arg-type]
        submission_bridge=original_submission,  # type: ignore[arg-type]
    )
    submitted = types.SimpleNamespace(
        formal_run_candidate=object(),
        reviewed_authority=object(),
    )
    calls = {"report": 0, "roots": 0, "claim": 0, "adapter": 0}

    def report_builder(actual):
        assert actual is evidence
        calls["report"] += 1
        if calls["report"] == 2:
            object.__setattr__(
                evidence,
                "submission_bridge",
                replacement_submission,
            )
        return report

    def require_roots(actual, expected=None):
        assert actual is evidence
        calls["roots"] += 1
        roots = (
            actual.historical_bridge,
            actual.terminal_disposition_build,
            actual.authenticated_power_floor,
            actual.runtime_bridge,
            actual.submission_bridge,
        )
        current = (roots, ("stable-content",))
        if expected is not None and any(
            observed is not pinned
            for observed, pinned in zip(roots, expected[0], strict=True)
        ):
            raise module.PreQcOrchestrationError(
                "pre-QC evidence changed across the formal claim boundary"
            )
        return submitted, current

    def forbidden_claim(**_kwargs):
        calls["claim"] += 1
        raise AssertionError("changed roots must not consume the claim")

    def forbidden_adapter(**_kwargs):
        calls["adapter"] += 1
        raise AssertionError("changed roots must not reach QC")

    action = _with_closure_values(
        module.execute_pre_qc_formal_submission_once,
        report_builder=report_builder,
        require_current_roots=require_roots,
        invoke_claim=forbidden_claim,
        invoke_submission=forbidden_adapter,
    )
    transport = FormalQcTransport(
        http_transport=lambda *_args: pytest.fail("transport must remain inert"),
        clock=lambda: 1,
    )

    with pytest.raises(module.PreQcOrchestrationError, match="claim boundary"):
        action(
            evidence=evidence,
            client=transport,
            claimed_at_utc="2026-09-12T12:00:00Z",
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )
    assert calls == {"report": 2, "roots": 2, "claim": 0, "adapter": 0}


def test_root_change_while_claim_is_written_consumes_claim_but_refuses_qc():
    report = _fully_open_report()
    original_submission = object()
    replacement_submission = object()
    evidence = PreQcExecutionEvidence(
        historical_bridge=object(),  # type: ignore[arg-type]
        terminal_disposition_build=object(),  # type: ignore[arg-type]
        authenticated_power_floor=object(),  # type: ignore[arg-type]
        runtime_bridge=object(),  # type: ignore[arg-type]
        submission_bridge=original_submission,  # type: ignore[arg-type]
    )
    submitted = types.SimpleNamespace(
        formal_run_candidate=object(),
        reviewed_authority=object(),
    )
    claim = object()
    calls = {"roots": 0, "claim": 0, "adapter": 0}

    def require_roots(actual, expected=None):
        calls["roots"] += 1
        roots = (
            actual.historical_bridge,
            actual.terminal_disposition_build,
            actual.authenticated_power_floor,
            actual.runtime_bridge,
            actual.submission_bridge,
        )
        current = (roots, ("stable-content",))
        if expected is not None and any(
            observed is not pinned
            for observed, pinned in zip(roots, expected[0], strict=True)
        ):
            raise module.PreQcOrchestrationError(
                "pre-QC evidence changed across the formal claim boundary"
            )
        return submitted, current

    def claim_and_mutate(**_kwargs):
        calls["claim"] += 1
        object.__setattr__(
            evidence,
            "submission_bridge",
            replacement_submission,
        )
        return claim

    def forbidden_adapter(**_kwargs):
        calls["adapter"] += 1
        raise AssertionError("post-claim mutation must not reach QC")

    action = _with_closure_values(
        module.execute_pre_qc_formal_submission_once,
        report_builder=lambda actual: report,
        require_current_roots=require_roots,
        invoke_claim=claim_and_mutate,
        invoke_submission=forbidden_adapter,
    )
    transport = FormalQcTransport(
        http_transport=lambda *_args: pytest.fail("transport must remain inert"),
        clock=lambda: 1,
    )

    with pytest.raises(module.PreQcOrchestrationError, match="claim boundary"):
        action(
            evidence=evidence,
            client=transport,
            claimed_at_utc="2026-09-12T12:00:00Z",
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )
    assert calls == {"roots": 3, "claim": 1, "adapter": 0}


def _isolated_launch_evidence():
    historical = types.SimpleNamespace(
        bridge_id="historical-bridge",
        bridge_sha256="1" * 64,
    )
    terminal = types.SimpleNamespace(
        build_id="terminal-build",
        build_sha256="2" * 64,
        historical_bridge=historical,
    )
    power = types.SimpleNamespace(
        binding_id="power-binding",
        binding_sha256="3" * 64,
    )
    runtime = types.SimpleNamespace(
        bridge_id="runtime-bridge",
        bridge_sha256="4" * 64,
    )
    candidate = types.SimpleNamespace(
        candidate_id="formal-candidate",
        candidate_sha256="5" * 64,
    )
    authority = types.SimpleNamespace(
        authority_id="reviewed-authority",
        authority_sha256="6" * 64,
    )
    host = types.SimpleNamespace(
        closure_id="host-closure",
        closure_sha256="7" * 64,
    )
    execution = types.SimpleNamespace(
        authority_id="execution-authority",
        authority_sha256="8" * 64,
        host_code_closure=host,
    )
    plan = types.SimpleNamespace(
        plan_id="submission-plan",
        plan_sha256="9" * 64,
    )
    economic = types.SimpleNamespace(
        binding_id="economic-binding",
        binding_sha256="a" * 64,
        definition_id="economic-definition",
        definition_sha256="b" * 64,
    )
    report = types.SimpleNamespace(
        contract_id="report-contract",
        contract_sha256="c" * 64,
        artifact_sha256="d" * 64,
    )
    submitted = types.SimpleNamespace(
        bridge_id="submission-bridge",
        bridge_sha256="e" * 64,
        formal_run_candidate=candidate,
        reviewed_authority=authority,
        execution_authority=execution,
        plan=plan,
        authenticated_power_floor=power,
        economic_execution=economic,
        report_contract=report,
    )
    evidence = PreQcExecutionEvidence(
        historical_bridge=historical,  # type: ignore[arg-type]
        terminal_disposition_build=terminal,  # type: ignore[arg-type]
        authenticated_power_floor=power,  # type: ignore[arg-type]
        runtime_bridge=runtime,  # type: ignore[arg-type]
        submission_bridge=submitted,  # type: ignore[arg-type]
    )
    return evidence, submitted


def _isolated_current_roots(*, registry_status, **replacements):
    require_roots = _closure_value(
        module.execute_pre_qc_formal_submission_once,
        "require_current_roots",
    )
    defaults = {
        "historical_requirer": lambda value: value,
        "runtime_requirer": lambda value: value,
        "terminal_requirer": lambda value: value,
        "power_requirer": lambda value: value,
        "submission_requirer": lambda value: value,
        "historical_runtime_matcher": lambda *_args: True,
        "terminal_runtime_matcher": lambda *_args: True,
        "power_runtime_matcher": lambda *_args: True,
        "submission_identity_matcher": lambda *_args: True,
        "host_closure_verifier": lambda _value: None,
        "post_launch_capability_builder": lambda _value: object(),
        "post_launch_capability_matcher": lambda *_args: True,
        "owner_registry_status": lambda: registry_status,
    }
    defaults.update(replacements)
    return _with_closure_values(require_roots, **defaults)


@pytest.mark.parametrize(
    "gate_key_counts",
    (
        {"formal_qc_execution": 0, "formal_qc_result_read": 1},
        {"formal_qc_execution": 1, "formal_qc_result_read": 2},
        {"formal_qc_execution": True, "formal_qc_result_read": 1},
    ),
)
def test_launch_requires_exactly_one_execution_and_result_read_key(
    gate_key_counts,
):
    evidence, _submitted = _isolated_launch_evidence()
    require_roots = _isolated_current_roots(
        registry_status={"gate_key_counts": gate_key_counts}
    )
    message = "reviewed formal execution or result-read key is not pinned"

    with pytest.raises(module.PreQcOrchestrationError, match=re.escape(message)):
        require_roots(evidence)


def test_launch_isolates_lineage_and_live_root_reauthentication_changes():
    registry = {
        "gate_key_counts": {
            "formal_qc_execution": 1,
            "formal_qc_result_read": 1,
        }
    }
    evidence, _submitted = _isolated_launch_evidence()
    original_historical = evidence.historical_bridge
    replacement = types.SimpleNamespace(
        bridge_id="other-historical",
        bridge_sha256="f" * 64,
    )

    lineage_requirer = _isolated_current_roots(
        registry_status=registry,
        historical_requirer=lambda _value: replacement,
    )
    with pytest.raises(
        module.PreQcOrchestrationError,
        match=re.escape("pre-QC execution roots changed lineage or identity"),
    ):
        lineage_requirer(evidence)

    def mutate_but_return_original(value):
        object.__setattr__(evidence, "historical_bridge", replacement)
        return value

    live_requirer = _isolated_current_roots(
        registry_status=registry,
        historical_requirer=mutate_but_return_original,
    )
    object.__setattr__(evidence, "historical_bridge", original_historical)
    with pytest.raises(
        module.PreQcOrchestrationError,
        match=re.escape("pre-QC evidence roots changed during reauthentication"),
    ):
        live_requirer(evidence)

    object.__setattr__(evidence, "historical_bridge", original_historical)
    stable_requirer = _isolated_current_roots(registry_status=registry)
    _submitted, snapshot = stable_requirer(evidence)
    original_id = original_historical.bridge_id
    original_historical.bridge_id = "changed-historical-id"
    try:
        with pytest.raises(
            module.PreQcOrchestrationError,
            match=re.escape(
                "pre-QC evidence changed across the formal claim boundary"
            ),
        ):
            stable_requirer(evidence, snapshot)
    finally:
        original_historical.bridge_id = original_id


def test_launch_requires_exact_concrete_transport_before_preflight():
    message = "exact concrete QC transport is required"
    with pytest.raises(module.PreQcOrchestrationError, match=re.escape(message)):
        module.execute_pre_qc_formal_submission_once(
            evidence=PreQcExecutionEvidence(),
            client=object(),  # type: ignore[arg-type]
            claimed_at_utc="2026-09-12T12:00:00Z",
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )


def test_launch_isolates_report_and_submission_bridge_toctou_guards():
    evidence = PreQcExecutionEvidence()
    client = FormalQcTransport(http_transport=lambda *_args: None, clock=lambda: 1)
    report = _fully_open_report()
    changed_report = dataclasses.replace(report, report_sha256="0" * 64)
    submitted = types.SimpleNamespace(
        formal_run_candidate=object(),
        reviewed_authority=object(),
    )
    replacement = types.SimpleNamespace(
        formal_run_candidate=object(),
        reviewed_authority=object(),
    )

    reports = iter((report, changed_report))
    report_action = _with_closure_values(
        module.execute_pre_qc_formal_submission_once,
        report_builder=lambda _value: next(reports),
        report_requirer=lambda value: value,
        require_current_roots=lambda *_args: (submitted, ((), ())),
    )
    with pytest.raises(
        module.PreQcOrchestrationError,
        match=re.escape("pre-QC evidence changed during live reauthentication"),
    ):
        report_action(
            evidence=evidence,
            client=client,
            claimed_at_utc="2026-09-12T12:00:00Z",
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )

    root_calls = 0

    def before_claim_roots(*_args):
        nonlocal root_calls
        root_calls += 1
        return (
            submitted if root_calls == 1 else replacement,
            ((), ()),
        )

    before_action = _with_closure_values(
        module.execute_pre_qc_formal_submission_once,
        report_builder=lambda _value: report,
        report_requirer=lambda value: value,
        require_current_roots=before_claim_roots,
        invoke_claim=lambda **_kwargs: pytest.fail("claim must remain unspent"),
    )
    with pytest.raises(
        module.PreQcOrchestrationError,
        match=re.escape("submission bridge changed immediately before claim"),
    ):
        before_action(
            evidence=evidence,
            client=client,
            claimed_at_utc="2026-09-12T12:00:00Z",
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )

    root_calls = 0
    claim = object()

    def after_claim_roots(*_args):
        nonlocal root_calls
        root_calls += 1
        return (
            submitted if root_calls < 3 else replacement,
            ((), ()),
        )

    after_action = _with_closure_values(
        module.execute_pre_qc_formal_submission_once,
        report_builder=lambda _value: report,
        report_requirer=lambda value: value,
        require_current_roots=after_claim_roots,
        invoke_claim=lambda **_kwargs: claim,
        invoke_submission=lambda **_kwargs: pytest.fail("QC must remain inert"),
    )
    with pytest.raises(
        module.PreQcOrchestrationError,
        match=re.escape("submission bridge changed after formal claim"),
    ):
        after_action(
            evidence=evidence,
            client=client,
            claimed_at_utc="2026-09-12T12:00:00Z",
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )


def test_reflected_irreversible_invokers_refuse_direct_calls():
    action = module.execute_pre_qc_formal_submission_once
    invoke_claim = _closure_value(action, "invoke_claim")
    invoke_submission = _closure_value(action, "invoke_submission")

    with pytest.raises(module.PreQcOrchestrationError, match="caller provenance"):
        invoke_claim(
            candidate=object(),
            authority=object(),
            claimed_at_utc="2026-09-12T12:00:00Z",
        )
    with pytest.raises(module.PreQcOrchestrationError, match="caller provenance"):
        invoke_submission(
            submission_bridge=object(),
            claim=object(),
            client=object(),
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )


def test_sealed_action_closure_exposes_no_mutable_authority_container():
    pending = [module.execute_pre_qc_formal_submission_once]
    observed = set()
    while pending:
        function = pending.pop()
        if id(function) in observed:
            continue
        observed.add(id(function))
        for name, cell in zip(
            function.__code__.co_freevars,
            function.__closure__ or (),
            strict=True,
        ):
            value = cell.cell_contents
            # Exact namespace objects are immutable identity anchors for the
            # guard, never an authority or receipt storage container.
            if name == "module_globals" and value is function.__globals__:
                continue
            if name == "module_registry" and value is sys.modules:
                continue
            assert type(value) not in (dict, list, set, bytearray)
            assert not (
                not isinstance(value, type) and dataclasses.is_dataclass(value)
            )
            if type(value) is types.FunctionType:
                pending.append(value)

    assert not hasattr(module, "_bind_pre_qc_formal_submission_boundary")
    assert not hasattr(module, "_require_current_execution_evidence")


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork required")
def test_inherited_execution_boundary_refuses_in_child_and_parent_survives():
    transport = FormalQcTransport(
        http_transport=lambda *_args: pytest.fail("transport must remain inert"),
        clock=lambda: 1,
    )
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - asserted through the pipe and status
        os.close(read_descriptor)
        try:
            module.execute_pre_qc_formal_submission_once(
                evidence=PreQcExecutionEvidence(),
                client=transport,
                claimed_at_utc="2026-09-12T12:00:00Z",
                submission_started_at_utc="2026-09-12T12:00:01Z",
            )
        except module.PreQcOrchestrationError as exc:
            payload = (
                b"refused"
                if "different process" in str(exc)
                else ("wrong:" + str(exc)).encode("utf-8")
            )
        except BaseException as exc:
            payload = ("unexpected:" + type(exc).__name__).encode("utf-8")
        else:
            payload = b"accepted"
        os.write(write_descriptor, payload)
        os.close(write_descriptor)
        os._exit(0)

    os.close(write_descriptor)
    payload = os.read(read_descriptor, 4096)
    os.close(read_descriptor)
    waited, status = os.waitpid(child, 0)
    assert waited == child
    assert os.waitstatus_to_exitcode(status) == 0
    assert payload == b"refused"

    with pytest.raises(PreQcOrchestrationBlocked):
        module.execute_pre_qc_formal_submission_once(
            evidence=PreQcExecutionEvidence(),
            client=transport,
            claimed_at_utc="2026-09-12T12:00:00Z",
            submission_started_at_utc="2026-09-12T12:00:01Z",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("ready_for_formal_claim", True),
        ("ready_for_one_shot_submission", True),
        ("pre_submission_software_build_ready", True),
        ("software_build_ready", True),
        ("provider_qc_or_outcome_io_performed", True),
        ("local_filesystem_reauthentication_performed", True),
        ("provider_credentials_inspected", True),
        ("qc_credentials_inspected", True),
        ("outcome_data_accessed", True),
        ("report_sha256", "0" * 64),
    ),
)
def test_report_identity_refuses_tampering(field, value):
    report = build_pre_qc_preflight_report()
    with pytest.raises(module.PreQcOrchestrationError, match="identity"):
        require_pre_qc_preflight_report(dataclasses.replace(report, **{field: value}))


def test_source_has_no_legacy_materializing_bundle_or_adapter_dependency():
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "FormalQcUploadBundle" not in imported
    assert "build_formal_qc_upload_bundle" not in imported | called
    assert "execute_formal_qc_submission_once" not in imported | called
    assert "execute_streamed_formal_qc_submission_once" in imported | called
    assert "streamed_formal_post_launch_capability_record" in imported | called
    assert "standard_statistics_accessed" not in source
    assert "one_use_summary_statistics_only_read" not in source


def test_static_record_discloses_conditional_nonmaterializing_path():
    record = pre_qc_orchestrator_record()

    assert record["deterministic_machine_readable_preflight"] is True
    assert record["caller_boolean_authority_accepted"] is False
    assert record["caller_string_authority_accepted"] is False
    assert record["caller_callback_authority_accepted"] is False
    assert record["formal_claim_before_complete_preflight"] is False
    assert record["live_file_reauthentication_before_claim"] is True
    assert record["sealed_import_time_execution_dependencies"] is True
    assert record["same_process_execution_boundary"] is True
    assert record["exact_public_action_caller_provenance"] is True
    assert record["typed_root_reauthentication_immediately_before_claim"] is True
    assert record["typed_root_reauthentication_after_claim_before_qc"] is True
    assert record["legacy_materializing_upload_bundle_dependency"] is False
    assert record["legacy_stream_iterator_tuple_materialization_permitted"] is False
    assert record["historical_universe_bridge_interface_available"] is True
    assert record["streamed_runtime_bridge_interface_available"] is True
    assert record["sequential_submission_bridge_interface_available"] is True
    assert (
        record[
            "streamed_post_launch_capability_requires_exact_submission_bridge"
        ]
        is True
    )
    assert (
        record["streamed_post_launch_capability_interface_available"]
        is True
    )
    assert record["static_boolean_can_satisfy_post_launch_gate"] is False
    assert record["software_build_ready_scope"] == (
        "typed_launch_status_separate_result_read_and_evaluation_path"
    )
    assert record["conditional_formal_submission_available"] is True


def test_cli_emits_only_the_same_canonical_closed_report():
    command = [sys.executable, "scripts/run_arv2_pre_qc.py"]
    environment = dict(os.environ)
    environment["PYTHONPYCACHEPREFIX"] = "/private/tmp/arv2-preqc-cli-pycache"
    normal = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=environment,
    )
    required = subprocess.run(
        [*command, "--require-ready"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=environment,
    )
    expected = render_pre_qc_preflight_report_bytes(build_pre_qc_preflight_report())
    assert normal.returncode == 0
    assert required.returncode == 2
    assert normal.stdout == required.stdout == expected
    assert normal.stderr == required.stderr == b""


def test_fresh_import_performs_no_credential_network_or_outcome_io():
    probe = r'''\
import urllib.request
import research.quantconnect as qc

def denied(*args, **kwargs):
    raise AssertionError("external capability touched during import")

urllib.request.urlopen = denied
qc.QuantConnectCredentials.from_env = classmethod(denied)
import research.analyst_revisions_v2_qc.pre_qc_orchestrator as target
record = target.pre_qc_orchestrator_record()
assert record["provider_io_on_import"] is False
assert record["quantconnect_io_on_import"] is False
assert record["credential_io_on_import"] is False
assert record["outcome_io_on_import"] is False
'''
    environment = dict(os.environ)
    environment["PYTHONPYCACHEPREFIX"] = "/private/tmp/arv2-preqc-import-pycache"
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8")
    assert completed.stdout == completed.stderr == b""
