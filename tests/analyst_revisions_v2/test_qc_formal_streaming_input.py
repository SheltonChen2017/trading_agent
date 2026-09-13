from __future__ import annotations

import dataclasses
import json
import os
import select
import signal
import threading
import types
import weakref
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    sha256_bytes,
)
from research.analyst_revisions_v2.production_scoring import _solve_ols
from research.analyst_revisions_v2.production_scoring import (
    FORMAL_FOLD_BOUNDARIES,
    FORMAL_HORIZON_FOLD_BOUNDARIES,
)
from research.analyst_revisions_v2.preopen_control_acquisition import (
    PreopenControlAcquisitionError,
)
from research.analyst_revisions_v2.production_evidence_acquisition import (
    ProductionEvidenceAcquisitionError,
)
from research.analyst_revisions_v2_qc import formal_input_bundle as input_bundle_module
from research.analyst_revisions_v2_qc import formal_runtime_projection as runtime
from research.analyst_revisions_v2_qc import formal_qc_transport as transport_module
from research.analyst_revisions_v2_qc import formal_submission_adapter as submission
from research.analyst_revisions_v2_qc import formal_streaming_bridge as bridge_module
from research.analyst_revisions_v2_qc import formal_streaming_input as streaming_module
from research.analyst_revisions_v2_qc import power_calibration_bridge as power_bridge
from research.analyst_revisions_v2_qc.formal_economic_execution_definition import (
    HOLDING_SESSIONS,
    SOURCE_VIEW_IDS,
    build_formal_economic_execution_binding,
    build_formal_economic_execution_definition,
)
from research.analyst_revisions_v2_qc.formal_streaming_bridge import (
    FormalStreamingBridgeError,
    build_streamed_formal_runtime_bridge,
    build_streamed_formal_runtime_resource_candidate,
    iter_streamed_formal_qc_upload_entries,
    load_streamed_formal_runtime_capacity_binding,
    render_streamed_formal_runtime_bridge_review_candidate,
    require_streamed_formal_runtime_bridge,
)
from research.analyst_revisions_v2_qc.formal_streaming_input import (
    STREAMING_CAPACITY_LIMIT_NAMES,
    FormalStreamingInputError,
    FormalStreamingRefusalReason,
    FormalStreamingRunRefusal,
    _BoundedFormalDiskBuilder,
    _DiskBackedDecimalMgs,
    _iter_physical_terminal_sessions,
    begin_streamed_production_scoring,
    build_lifecycle_streamed_formal_input_candidate,
    build_streamed_formal_input_candidate,
    iter_streamed_production_scoring_fold,
    iter_formal_qc_compressed_shards,
    iter_physical_formal_shard_payloads,
    load_formal_streaming_capacity_binding,
    load_physical_preopen_terminal_archive,
    render_formal_streaming_capacity_review_candidate,
    require_streamed_formal_input_candidate,
)
from research.analyst_revisions_v2_qc.formal_terminal_disposition_builder import (
    begin_formal_terminal_disposition_recording,
    require_formal_terminal_disposition_build,
)
from research.analyst_revisions_v2_qc.formal_input_bundle import (
    CURRENT_VIEW_LABEL,
    FormalInputBundleError,
    build_formal_power_calibration_binding,
    formal_global_comparator_coverage_source_visible_contributions,
)
from research.analyst_revisions_v2_qc.formal_input_composer import (
    TERMINAL_OBJECT_SCHEMA,
    TERMINAL_PACKAGE_SCHEMA,
    load_formal_terminal_disposition_package,
)
from research.analyst_revisions_v2_qc.formal_run_protocol import (
    AcceptedRiskPairBinding,
    ArtifactBinding,
    FormalLookClaim,
    PowerFloorBinding,
    ReviewedFormalRunAuthority,
    TerminalCensusBinding,
    build_formal_run_candidate,
)
from research.analyst_revisions_v2_qc.formal_runtime_projection import (
    CAPACITY_LIMIT_NAMES,
    CAPACITY_REVIEW_SCHEMA,
    FORMAL_EVALUATOR_PROJECT_PATH,
    SHARD_ROLE_ORDER,
    SHARD_ROW_SCHEMAS,
    derive_formal_qc_runtime_resource_census,
)
from data.exchange_calendar import trading_sessions
import tests.analyst_revisions_v2.test_power_calibration_receipt as power_helpers
from research.analyst_revisions_v2 import power_calibration_receipt as power_module

from .test_production_scoring import (
    _c2_pair,
    _census_row,
    _truth_artifact,
    _global_contract,
    _install_offline_physical_receipt_requires,
    _offline_physical_requirer,
    _PRODUCTION_EVIDENCE_REQUIRE,
    _PRODUCTION_PREOPEN_REQUIRE,
)
from .test_qc_formal_submission_adapter import (
    _FakeClient,
    _install_offline_action_authority,
    _permit,
)
from .test_qc_formal_economic_execution_definition import _stock


ROOT = Path(__file__).resolve().parents[2]
_PRODUCTION_STREAMED_SUBMISSION_ACTION = (
    submission.execute_streamed_formal_qc_submission_once
)


@pytest.fixture(autouse=True)
def _install_streaming_offline_physical_receipt_requires(
    monkeypatch,
    _install_offline_physical_receipt_requires,
):
    """Route only this test module's imported aliases to its local vault."""

    monkeypatch.setattr(
        streaming_module,
        "require_reviewed_preopen_control_acquisition_receipt",
        lambda value: _offline_physical_requirer("preopen", value),
    )
    monkeypatch.setattr(
        streaming_module,
        "require_production_evidence_acquisition_receipt",
        lambda value: _offline_physical_requirer("evidence", value),
    )


def _closure_cell(value: object):
    def capture():
        return value

    assert capture.__closure__ is not None
    return capture.__closure__[0]


def _with_closure_value(function, name: str, value: object):
    """Clone a production wrapper with one explicit offline-only test cell."""

    assert function.__closure__ is not None
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__, strict=True)
    )
    assert name in cells
    closure = tuple(
        _closure_cell(value) if freevar == name else cells[freevar]
        for freevar in function.__code__.co_freevars
    )
    rebound = types.FunctionType(
        function.__code__, function.__globals__, function.__name__,
        function.__defaults__, closure,
    )
    rebound.__kwdefaults__ = function.__kwdefaults__
    rebound.__annotations__ = function.__annotations__
    return rebound


def test_all_fold_submission_seam_uses_only_test_local_action_authority(
    monkeypatch,
):
    _install_offline_action_authority(monkeypatch)
    local_action = submission.execute_streamed_formal_qc_submission_once
    assert local_action is not _PRODUCTION_STREAMED_SUBMISSION_ACTION
    local_cells = dict(zip(
        local_action.__code__.co_freevars,
        local_action.__closure__,
        strict=True,
    ))
    local_cells["binding_guard"].cell_contents("offline test seam")

    callbacks = []

    class Explosive:
        def __getattribute__(self, name):
            callbacks.append(name)
            raise AssertionError("production action crossed its first guard")

    value = Explosive()
    with pytest.raises(
        submission.FormalQcSubmissionError,
        match="action global authority changed",
    ):
        _PRODUCTION_STREAMED_SUBMISSION_ACTION(
            submission_bridge=value,
            claim=value,
            client=value,
            submission_started_at_utc="2026-09-12T12:01:00.000000Z",
        )
    assert callbacks == []


def _limits(**changes: int) -> dict[str, int]:
    values = {
        "max_physical_shard_count": 10,
        "max_physical_chunk_compressed_bytes": 32 * 1024 * 1024,
        "max_physical_session_terminal_count": 10_000,
        "max_physical_session_uncompressed_bytes": 32 * 1024 * 1024,
        "max_c2_normalized_row_count": 10_000,
        "max_retained_institution_count": 10_000,
        "max_retained_security_count": 10_000,
        "max_retained_minute_requirement_count": 100_000,
        "max_retained_input_graph_bytes": 2 * 1024 * 1024 * 1024,
        "max_active_contribution_count_per_arm_session": 100_000,
        "max_session_contribution_lineage_count": 100_000,
        "max_industry_level_count_per_arm_fold": 1_000,
        "max_disk_mgs_width": 2_000,
        "max_disk_mgs_live_decimal_count": 4_100_000,
        "max_disk_mgs_spool_row_count": 10_000_000,
        "max_disk_mgs_spool_byte_count": 8 * 1024 * 1024 * 1024,
        "max_disk_mgs_spool_file_count": 2_100,
        "max_formal_session_block_row_count": 100_000,
        "max_formal_session_block_uncompressed_bytes": 32 * 1024 * 1024,
        "max_formal_shard_row_count": 100_000,
        "max_formal_shard_uncompressed_bytes": 32 * 1024 * 1024,
        "max_formal_shard_count": 10_000,
        "max_formal_total_compressed_bytes": 256 * 1024 * 1024,
        "max_runtime_resource_spool_byte_count": 2 * 1024 * 1024 * 1024,
        "max_daily_requirement_sessions_retained": 64,
        "max_daily_requirement_keys_retained": 1_000_000,
        "max_archive_passes_per_fold": 3,
    }
    values.update(changes)
    assert set(values) == set(STREAMING_CAPACITY_LIMIT_NAMES)
    return values


def _runtime_limits(**changes: int) -> dict[str, int]:
    values = {name: 10_000_000 for name in CAPACITY_LIMIT_NAMES}
    values.update(
        max_project_file_count=100,
        max_project_source_character_count=2_000_000,
        max_summary_chunk_characters=4_000,
        max_summary_payload_byte_count=200_000,
        max_summary_chunk_count=100,
        max_single_object_byte_count=48 * 1024 * 1024,
        max_object_store_total_input_byte_count=256 * 1024 * 1024,
        min_object_store_available_output_byte_count=109_200_000,
        min_object_store_available_output_file_count=26,
    )
    values.update(changes)
    assert set(values) == set(CAPACITY_LIMIT_NAMES)
    return values


def _write_runtime_capacity_review(
    tmp_path: Path, resource, *, suffix: str = ""
) -> Path:
    candidate = resource.runtime_capacity_candidate_bytes
    seed = {
        "schema": CAPACITY_REVIEW_SCHEMA,
        "candidate_sha256": sha256_bytes(candidate),
        "receipt_id": None,
        "receipt_sha256": None,
        "limits": dict(resource.proposed_runtime_limits),
        "representative_full_census_verified": True,
        "target_tier_limits_observed": True,
        "cloud_evaluator_equivalence_verified": True,
        "object_store_input_transport_verified": True,
        "object_store_output_write_once_transport_verified": True,
        "summary_statistics_channel_verified": True,
        "summary_root_result_channel_verified": True,
    }
    digest = sha256_bytes(canonical_json_bytes(seed))
    seed["receipt_id"] = "arv2-formal-qc-capacity-review-" + digest
    seed["receipt_sha256"] = digest
    path = tmp_path / f"runtime-capacity-review{suffix}.json"
    path.write_bytes(canonical_json_bytes(seed))
    os.chmod(path, 0o600)
    return path


def _write_streamed_bridge_review(
    tmp_path: Path,
    resource,
    runtime_review_path: Path,
    *,
    suffix: str = "",
) -> Path:
    candidate = render_streamed_formal_runtime_bridge_review_candidate(
        resource_candidate=resource,
        runtime_capacity_reviewed_receipt_path=runtime_review_path,
    )
    raw = json.loads(candidate)
    raw["status"] = (
        "independently_reviewed_streamed_runtime_bridge_capacity_affirmative"
    )
    for name in (
        "whole_graph_retained_byte_measurement_verified",
        "disk_backed_resource_census_verified",
        "sequential_reopen_rehash_upload_verified",
        "one_fold_streaming_projection_verified",
        "production_truth_materialization_avoided",
        "representative_full_census_verified",
        "runtime_capacity_reviewed",
    ):
        raw[name] = True
    digest = sha256_bytes(canonical_json_bytes(raw))
    raw["receipt_id"] = f"arv2-streamed-runtime-capacity-{digest[:24]}"
    raw["receipt_sha256"] = digest
    path = tmp_path / f"streamed-bridge-review{suffix}.json"
    path.write_bytes(canonical_json_bytes(raw))
    os.chmod(path, 0o600)
    return path


def _affirmative_capacity(tmp_path: Path, truth, limits):
    candidate = render_formal_streaming_capacity_review_candidate(
        preopen_acquisition_receipt=truth.preopen_acquisition_receipt,
        production_evidence_receipt=truth.production_evidence_receipt,
        limits=limits,
    )
    raw = json.loads(candidate)
    raw["status"] = "independently_reviewed_streaming_capacity_affirmative"
    for name in (
        "representative_full_census_verified",
        "physical_replay_geometry_verified",
        "disk_spooled_mgs_peak_model_verified",
        "bounded_formal_shard_builder_verified",
        "no_caller_authored_score_or_peak_claim_verified",
        "retained_input_graph_peak_verified",
    ):
        raw[name] = True
    digest = sha256_bytes(canonical_json_bytes(raw))
    raw["receipt_id"] = f"arv2-formal-streaming-capacity-{digest[:24]}"
    raw["receipt_sha256"] = digest
    path = tmp_path / "streaming-capacity-review.json"
    path.write_bytes(canonical_json_bytes(raw))
    os.chmod(path, 0o600)
    return load_formal_streaming_capacity_binding(
        preopen_acquisition_receipt=truth.preopen_acquisition_receipt,
        production_evidence_receipt=truth.production_evidence_receipt,
        limits=limits,
        reviewed_receipt_path=path,
    )


def _physical_archive(tmp_path: Path, limits=None):
    current, censored, _labels = _c2_pair()
    census = tuple(_census_row("2020-01-06", index) for index in range(20))
    truth, payload = _truth_artifact(
        current, censored, census, return_payload=True
    )
    capacity = _affirmative_capacity(tmp_path, truth, limits or _limits())
    shard_path = tmp_path / "physical-preopen-0000.jsonl.gz"
    shard_path.write_bytes(payload)
    os.chmod(shard_path, 0o600)
    archive = load_physical_preopen_terminal_archive(
        preopen_acquisition_receipt=truth.preopen_acquisition_receipt,
        capacity=capacity,
        shard_paths=(shard_path,),
    )
    return archive, shard_path


def _full_sparse_formal_fixture(tmp_path: Path):
    current, censored, _labels = _c2_pair(
        event_date="2013-01-03",
        last_updated="2013-01-03T12:00:00Z",
        decision_session="2013-01-07",
        evidence_available_at="2013-01-07T13:00:00.000000Z",
        refresh_event_date="2024-01-29",
        refresh_last_updated="2024-01-29T12:00:00Z",
        refresh_decision_session="2024-01-31",
        refresh_evidence_available_at="2024-01-31T13:00:00.000000Z",
    )
    sessions = {"2013-01-07"}
    h20_test_starts = {
        fold_id: test_start
        for (
            fold_id,
            horizon,
            _train_start,
            _train_end,
            _validation_start,
            _validation_end,
            test_start,
            _test_end,
        ) in FORMAL_HORIZON_FOLD_BOUNDARIES
        if horizon == 20
    }
    for (
        fold_id,
        train_start,
        train_end,
        _validation_start,
        _validation_end,
        test_start,
        test_end,
    ) in FORMAL_FOLD_BOUNDARIES:
        sessions.update(
            item.isoformat()
            for item in trading_sessions(
                date.fromisoformat(train_start),
                date.fromisoformat(train_end) - timedelta(days=1),
            )[:3]
        )
        assert test_start <= h20_test_starts[fold_id] < test_end
        sessions.add(h20_test_starts[fold_id])
    census = tuple(
        _census_row(session, index)
        for session in sorted(sessions)
        for index in range(20)
    )
    truth, payload = _truth_artifact(
        current, censored, census, return_payload=True
    )
    capacity = _affirmative_capacity(tmp_path, truth, _limits())
    physical_path = tmp_path / "physical-preopen-full-sparse.jsonl.gz"
    physical_path.write_bytes(payload)
    os.chmod(physical_path, 0o600)
    archive = load_physical_preopen_terminal_archive(
        preopen_acquisition_receipt=truth.preopen_acquisition_receipt,
        capacity=capacity,
        shard_paths=(physical_path,),
    )
    pair = current.evidence_authority.pair
    accepted = AcceptedRiskPairBinding(
        pair=ArtifactBinding(
            artifact_id=pair.pair_id,
            content_sha256=pair.pair_sha256,
            artifact_sha256="1" * 64,
            byte_count=1,
        ),
        capture_id=pair.capture.capture_id,
        capture_sha256=pair.capture.capture_sha256,
        current_source_included_count=current.source_view_included_count,
        censored_source_included_count=censored.source_view_included_count,
        current_admitted_decision_count=current.normalized_row_count,
        current_named_preoutcome_refusal_count=(
            current.source_view_included_count - current.normalized_row_count
        ),
        censored_admitted_decision_count=censored.normalized_row_count,
        censored_named_preoutcome_refusal_count=(
            censored.source_view_included_count - censored.normalized_row_count
        ),
        guidance_admitted_count=0,
        pre_2013_admitted_count=0,
        pristine_point_in_time=False,
        views_share_one_capture=True,
    )
    parents = power_helpers.parents.__wrapped__()
    power_inputs = power_helpers._write_authorized_inputs(
        tmp_path / "power", parents
    )
    computed = power_helpers._compute(parents, power_inputs)
    receipt_path = (
        tmp_path / "power" / power_module.power_calibration_receipt_filename(computed)
    )
    receipt_path.write_bytes(
        power_module.render_power_calibration_receipt(computed).encode("utf-8")
    )
    loaded = power_module.load_power_calibration_receipt(
        receipt_path,
        content_contract=parents.content_contract,
        manifest_candidate=power_inputs.candidate,
        input_authority=power_inputs.input_authority,
        beta_series_path=power_inputs.beta_path,
        component_count_path=power_inputs.component_path,
    )
    formal_power = build_formal_power_calibration_binding(loaded)
    power_floor = PowerFloorBinding(
        numeric_receipt=ArtifactBinding(
            artifact_id=formal_power.receipt_id,
            content_sha256=formal_power.receipt_sha256,
            artifact_sha256="2" * 64,
            byte_count=1,
        ),
        stock_successor=ArtifactBinding(
            artifact_id="fixture-stock-power-successor",
            content_sha256="3" * 64,
            artifact_sha256="4" * 64,
            byte_count=1,
        ),
        disposition=formal_power.disposition,
        required_valid_dates=formal_power.required_valid_dates,
        observed_preoutcome_valid_dates=formal_power.required_valid_dates,
        required_connected_components=formal_power.required_connected_components,
        observed_preoutcome_connected_components=(
            formal_power.required_connected_components
        ),
        h20_test_session_capacity=1388,
        preoutcome_candidate_date_count=formal_power.required_valid_dates,
        valid_h20_test_session_count=formal_power.required_valid_dates,
        refused_h20_test_session_count=0,
        missing_h20_test_session_count=(
            1388 - formal_power.required_valid_dates
        ),
        connected_component_instance_count=(
            formal_power.required_connected_components
        ),
    )
    terminal_payload = canonical_json_bytes(
        {
            "schema": TERMINAL_PACKAGE_SCHEMA,
            "terminal_policy_id": "arv2-terminal-payoff-benchmark-splice-v1",
            "row_count": 0,
            "rows": [],
        }
    )
    terminal_binding = TerminalCensusBinding(
        census=ArtifactBinding(
            artifact_id="fixture-empty-terminal-census",
            content_sha256=sha256_bytes(terminal_payload),
            artifact_sha256="5" * 64,
            byte_count=len(terminal_payload),
        ),
        terminal_policy_id="arv2-terminal-payoff-benchmark-splice-v1",
        security_count=20,
        lifecycle_coverage_count=20,
        terminal_requirement_count=0,
        terminal_payoff_count=0,
        benchmark_splice_continuation_count=0,
        named_terminal_refusal_count=0,
        silently_omitted_count=0,
    )
    terminal_package = load_formal_terminal_disposition_package(
        payload=terminal_payload, terminal_census=terminal_binding
    )
    return (
        archive, accepted, formal_power, power_floor, terminal_package,
        loaded, (parents, power_inputs),
    )


def test_physical_terminal_archive_replays_one_session_without_truth_graph(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    with pytest.raises(
        PreopenControlAcquisitionError, match="loader-authenticated"
    ):
        _PRODUCTION_PREOPEN_REQUIRE(archive.preopen_acquisition_receipt)
    with pytest.raises(
        ProductionEvidenceAcquisitionError, match="authenticated"
    ):
        _PRODUCTION_EVIDENCE_REQUIRE(
            archive.capacity.production_evidence_receipt
        )
    blocks = tuple(_iter_physical_terminal_sessions(archive))
    assert len(blocks) == len(archive.preopen_acquisition_receipt.control_sessions)
    nonempty = tuple(item for item in blocks if item.terminal_count)
    assert len(nonempty) == 1
    assert nonempty[0].decision_session == "2020-01-06"
    assert len(nonempty[0].accepted) == 20
    assert not nonempty[0].refused
    assert nonempty[0].terminal_count == 20


def test_physical_terminal_archive_refuses_post_load_corruption(tmp_path):
    archive, path = _physical_archive(tmp_path)
    payload = bytearray(path.read_bytes())
    payload[-1] ^= 1
    path.write_bytes(payload)
    os.chmod(path, 0o600)
    with pytest.raises(
        FormalStreamingRunRefusal,
        match=FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED.value,
    ):
        tuple(_iter_physical_terminal_sessions(archive))


@pytest.mark.parametrize(
    "name",
    (
        "_make_bridge_capacity_authority_vault",
        "_bridge_capacity_authority_register",
        "_bridge_capacity_authority_current",
        "_load_streamed_formal_runtime_capacity_binding_impl",
        "_require_streamed_formal_runtime_capacity_binding_impl",
    ),
)
def test_bridge_capacity_authority_primitives_are_not_module_addressable(name):
    assert not hasattr(bridge_module, name)


def _extracted_bridge_capacity_register():
    loader = bridge_module.load_streamed_formal_runtime_capacity_binding
    assert loader.__closure__ is not None
    cells = dict(zip(loader.__code__.co_freevars, loader.__closure__, strict=True))
    return cells["authority_register"].cell_contents


def _install_test_bridge_capacity_authority(monkeypatch):
    """Keep synthetic bridge-capacity receipts out of production authority."""

    private = {}

    def forget(identity, reference):
        with bridge_module._BRIDGE_CAPACITY_LOCK:
            entry = private.get(identity)
            if entry is not None and entry[0] is reference:
                private.pop(identity, None)
            if bridge_module._BRIDGE_CAPACITY_BINDINGS.get(identity) is entry:
                bridge_module._BRIDGE_CAPACITY_BINDINGS.pop(identity, None)

    def register(
        value,
        *,
        resource_candidate,
        runtime_capacity,
        review_receipt_bytes,
        review_candidate_bytes,
        topology,
    ):
        identity = id(value)
        reference = weakref.ref(
            value, lambda ref, key=identity: forget(key, ref)
        )
        entry = (
            reference,
            resource_candidate,
            runtime_capacity,
            review_receipt_bytes,
            review_candidate_bytes,
            topology,
            os.getpid(),
        )
        with bridge_module._BRIDGE_CAPACITY_LOCK:
            if (
                identity in private
                or identity in bridge_module._BRIDGE_CAPACITY_BINDINGS
            ):
                raise FormalStreamingBridgeError(
                    "test bridge capacity authority identity was reused"
                )
            private[identity] = entry
            bridge_module._BRIDGE_CAPACITY_BINDINGS[identity] = entry
        return value

    def current(value):
        identity = id(value)
        with bridge_module._BRIDGE_CAPACITY_LOCK:
            entry = private.get(identity)
            if (
                entry is None
                or bridge_module._BRIDGE_CAPACITY_BINDINGS.get(identity)
                is not entry
                or entry[0]() is not value
                or entry[6] != os.getpid()
            ):
                private.pop(identity, None)
                bridge_module._BRIDGE_CAPACITY_BINDINGS.pop(identity, None)
                return None
            return entry

    def reset_after_fork():
        private.clear()
        bridge_module._BRIDGE_CAPACITY_BINDINGS = {}
        bridge_module._BRIDGE_CAPACITY_LOCK = threading.RLock()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)

    production_loader = (
        bridge_module.load_streamed_formal_runtime_capacity_binding
    )
    production_requirer = (
        bridge_module.require_streamed_formal_runtime_capacity_binding
    )
    local_requirer = _with_closure_value(
        production_requirer, "authority_current", current
    )
    local_loader = _with_closure_value(
        production_loader, "authority_register", register
    )
    local_loader = _with_closure_value(
        local_loader,
        "require_streamed_formal_runtime_capacity_binding",
        local_requirer,
    )
    return production_loader, local_loader, local_requirer


def _load_test_bridge_capacity_authority(monkeypatch):
    """Traverse the genuine public loader with its external parents offline."""

    resource = object()
    runtime_capacity = object()
    review_receipt_bytes = b"test-review-receipt\n"
    review_candidate_bytes = b"test-review-candidate\n"
    raw = {
        "receipt_id": "arv2-streamed-runtime-capacity-test",
        "receipt_sha256": "1" * 64,
    }
    production_loader, local_loader, local_requirer = (
        _install_test_bridge_capacity_authority(monkeypatch)
    )
    monkeypatch.setattr(
        bridge_module,
        "require_streamed_formal_runtime_resource_candidate",
        lambda value: value,
    )
    monkeypatch.setattr(
        bridge_module,
        "_load_runtime_capacity",
        lambda _resource, _path: runtime_capacity,
    )
    monkeypatch.setattr(
        bridge_module,
        "_read_private_regular",
        lambda *_args, **_kwargs: (review_receipt_bytes, object()),
    )
    monkeypatch.setattr(
        bridge_module,
        "_authenticate_streamed_bridge_capacity_review",
        lambda **_kwargs: (raw, review_candidate_bytes),
    )
    monkeypatch.setattr(
        bridge_module.runtime,
        "require_formal_qc_runtime_capacity_binding",
        lambda value: value,
    )
    loader_kwargs = {
        "resource_candidate": resource,
        "runtime_capacity_reviewed_receipt_path": Path("offline-runtime.json"),
        "streamed_bridge_reviewed_receipt_path": Path("offline-bridge.json"),
    }
    prior_bindings = dict(bridge_module._BRIDGE_CAPACITY_BINDINGS)
    with pytest.raises(
        FormalStreamingBridgeError,
        match="register caller changed",
    ):
        production_loader(**loader_kwargs)
    assert bridge_module._BRIDGE_CAPACITY_BINDINGS == prior_bindings
    monkeypatch.setattr(
        bridge_module,
        "load_streamed_formal_runtime_capacity_binding",
        local_loader,
    )
    monkeypatch.setattr(
        bridge_module,
        "require_streamed_formal_runtime_capacity_binding",
        local_requirer,
    )
    return local_loader(**loader_kwargs)


def test_reflected_bridge_capacity_register_cannot_self_mint():
    register = _extracted_bridge_capacity_register()
    value = object.__new__(bridge_module.StreamedFormalRuntimeCapacityBinding)
    with pytest.raises(FormalStreamingBridgeError, match="caller changed"):
        register(
            value,
            resource_candidate=object(),
            runtime_capacity=object(),
            review_receipt_bytes=b"test-review-receipt\n",
            review_candidate_bytes=b"test-review-candidate\n",
            topology=(1, 2, 3),
        )


def test_reflected_bridge_capacity_private_registry_is_immutable():
    register = _extracted_bridge_capacity_register()
    cells = dict(
        zip(register.__code__.co_freevars, register.__closure__, strict=True)
    )
    private_entry = cells["private_entry"].cell_contents
    private_cells = dict(
        zip(
            private_entry.__code__.co_freevars,
            private_entry.__closure__,
            strict=True,
        )
    )
    state = private_cells["private_bindings"].cell_contents
    assert type(state) is tuple
    assert not hasattr(state, "append")


def test_bridge_capacity_public_mirror_cannot_reseal_private_authority(
    monkeypatch,
):
    value = _load_test_bridge_capacity_authority(monkeypatch)
    with bridge_module._BRIDGE_CAPACITY_LOCK:
        entry = bridge_module._BRIDGE_CAPACITY_BINDINGS[id(value)]
        replacement = tuple(list(entry))
        assert replacement is not entry
        bridge_module._BRIDGE_CAPACITY_BINDINGS[id(value)] = replacement
    with pytest.raises(FormalStreamingBridgeError, match="loader-authenticated"):
        bridge_module.require_streamed_formal_runtime_capacity_binding(value)
    assert id(value) not in bridge_module._BRIDGE_CAPACITY_BINDINGS
    with bridge_module._BRIDGE_CAPACITY_LOCK:
        bridge_module._BRIDGE_CAPACITY_BINDINGS[id(value)] = entry
    with pytest.raises(FormalStreamingBridgeError, match="loader-authenticated"):
        bridge_module.require_streamed_formal_runtime_capacity_binding(value)
    assert id(value) not in bridge_module._BRIDGE_CAPACITY_BINDINGS


@pytest.mark.skipif(
    not hasattr(os, "fork") or not hasattr(os, "register_at_fork"),
    reason="requires POSIX fork reset semantics",
)
def test_bridge_capacity_child_resets_inherited_lock_and_private_authority(
    monkeypatch,
):
    value = _load_test_bridge_capacity_authority(monkeypatch)
    entered = threading.Event()
    release = threading.Event()

    def hold_inherited_lock():
        with bridge_module._BRIDGE_CAPACITY_LOCK:
            entered.set()
            release.wait(15)

    holder = threading.Thread(target=hold_inherited_lock)
    holder.start()
    assert entered.wait(5)
    read_fd, write_fd = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover - assertions are returned by pipe
        os.close(read_fd)
        try:
            try:
                bridge_module.require_streamed_formal_runtime_capacity_binding(
                    value
                )
            except FormalStreamingBridgeError:
                pass
            else:
                raise AssertionError("inherited bridge capacity survived fork")
            with bridge_module._BRIDGE_CAPACITY_LOCK:
                pass
            if bridge_module._BRIDGE_CAPACITY_BINDINGS:
                raise AssertionError("inherited bridge registry survived fork")
            payload = b"ok"
        except BaseException as exc:
            payload = (f"{type(exc).__name__}:{exc}").encode("utf-8")[:1000]
        try:
            os.write(write_fd, payload)
        finally:
            os.close(write_fd)
            os._exit(0)
    os.close(write_fd)
    ready, _, _ = select.select([read_fd], [], [], 10)
    if ready:
        payload = os.read(read_fd, 1000)
    else:
        payload = b"child-timeout"
        os.kill(child_pid, signal.SIGKILL)
    os.close(read_fd)
    _, status = os.waitpid(child_pid, 0)
    release.set()
    holder.join(timeout=5)
    assert payload == b"ok"
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    assert id(value) in bridge_module._BRIDGE_CAPACITY_BINDINGS


def test_capacity_review_limits_cannot_be_raised_by_public_registry_reseal(
    tmp_path,
) -> None:
    archive, _path = _physical_archive(tmp_path)
    capacity = archive.capacity
    registered = streaming_module._CAPACITY_BINDINGS[id(capacity)]
    raised = dict(capacity.limits)
    raised["max_retained_input_graph_bytes"] += 1
    forged_limits = tuple(sorted(raised.items()))
    object.__setattr__(capacity, "limits", forged_limits)
    raw = json.loads(capacity.review_receipt_bytes.decode("utf-8"))
    streaming_module._CAPACITY_BINDINGS[id(capacity)] = (
        registered[0],
        (
            id(capacity.preopen_acquisition_receipt),
            id(capacity.production_evidence_receipt),
            id(capacity.limits),
            id(capacity.review_receipt_bytes),
            canonical_json_bytes(raw),
        ),
    )
    with pytest.raises(FormalStreamingInputError, match="loader-authenticated"):
        streaming_module.require_formal_streaming_capacity_binding(capacity)
    assert id(capacity) not in streaming_module._CAPACITY_BINDINGS


@pytest.mark.skipif(
    not hasattr(os, "fork") or not hasattr(os, "register_at_fork"),
    reason="requires POSIX fork reset semantics",
)
def test_capacity_authority_child_resets_inherited_held_lock_and_vault(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    capacity = archive.capacity
    entered = threading.Event()
    release = threading.Event()

    def hold_inherited_lock():
        with streaming_module._CAPACITY_LOCK:
            entered.set()
            release.wait(15)

    holder = threading.Thread(target=hold_inherited_lock)
    holder.start()
    assert entered.wait(5)
    read_fd, write_fd = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover - assertions are returned by pipe
        os.close(read_fd)
        try:
            try:
                streaming_module.require_formal_streaming_capacity_binding(capacity)
            except FormalStreamingInputError:
                pass
            else:
                raise AssertionError("inherited capacity authority survived fork")
            with streaming_module._CAPACITY_LOCK:
                pass
            if streaming_module._CAPACITY_BINDINGS:
                raise AssertionError("inherited capacity registry survived fork")
            payload = b"ok"
        except BaseException as exc:
            payload = (f"{type(exc).__name__}:{exc}").encode("utf-8")[:1000]
        try:
            os.write(write_fd, payload)
        finally:
            os.close(write_fd)
            os._exit(0)

    os.close(write_fd)
    child_reaped = False
    try:
        ready, _writable, _exceptional = select.select([read_fd], [], [], 10)
        if not ready:
            os.kill(child_pid, signal.SIGKILL)
            pytest.fail("child blocked on the inherited capacity authority lock")
        payload = os.read(read_fd, 1000)
        _waited_pid, status = os.waitpid(child_pid, 0)
        child_reaped = True
        assert os.waitstatus_to_exitcode(status) == 0
        assert payload == b"ok", payload.decode("utf-8", errors="replace")
    finally:
        os.close(read_fd)
        release.set()
        if not child_reaped:
            os.waitpid(child_pid, 0)
        holder.join(timeout=5)
        assert not holder.is_alive()
    assert streaming_module.require_formal_streaming_capacity_binding(capacity) is capacity


def test_public_streaming_scorer_names_underfilled_training_fixture(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    with pytest.raises(
        FormalStreamingRunRefusal,
        match=FormalStreamingRefusalReason.TRAINING_FIT_UNDERFILLED.value,
    ):
        tuple(iter_streamed_production_scoring_fold(builder))


def test_stream_builder_registry_reseal_cannot_replace_private_vault_state(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    registered = streaming_module._STREAM_BUILDERS[id(builder)]
    state = registered[2]
    forged = dataclasses.replace(
        state,
        matched_test_terminal_count=1,
        matched_test_terminal_sha256="1" * 64,
    )
    streaming_module._STREAM_BUILDERS[id(builder)] = (
        registered[0],
        registered[1],
        forged,
        streaming_module._stream_state_authority(forged),
        None,
    )
    with pytest.raises(FormalStreamingInputError, match="builder-authenticated"):
        streaming_module.require_streamed_production_scoring_builder(builder)
    assert id(builder) not in streaming_module._STREAM_BUILDERS


def test_stream_artifact_public_registry_cannot_mint_authority() -> None:
    forged = object.__new__(streaming_module.StreamedProductionScoringArtifact)
    identity = id(forged)
    streaming_module._STREAM_ARTIFACTS[identity] = (
        weakref.ref(forged), b"{}", (),
    )
    try:
        with pytest.raises(FormalStreamingInputError, match="builder-authenticated"):
            streaming_module.require_streamed_production_scoring_artifact(forged)
    finally:
        streaming_module._STREAM_ARTIFACTS.pop(identity, None)
    forbidden = (
        "_make_stream_state_vault",
        "_stream_vault_finalize_artifact",
        "_stream_vault_current_artifact",
        "_require_streamed_production_scoring_artifact_impl",
    )
    assert all(not hasattr(streaming_module, name) for name in forbidden)


def test_streamed_candidate_public_registry_cannot_mint_authority() -> None:
    forged = object.__new__(streaming_module.StreamedFormalInputCandidate)
    identity = id(forged)
    streaming_module._STREAMED_FORMAL_CANDIDATES[identity] = (
        weakref.ref(forged), b"{}", (),
    )
    try:
        with pytest.raises(FormalStreamingInputError, match="builder-authenticated"):
            streaming_module.require_streamed_formal_input_candidate(forged)
    finally:
        streaming_module._STREAMED_FORMAL_CANDIDATES.pop(identity, None)
    forbidden = (
        "_make_streamed_formal_candidate_authority",
        "_candidate_authority_register",
        "_candidate_authority_current",
        "_build_streamed_formal_input_candidate_impl",
        "_build_streamed_formal_input_candidate_public_impl",
        "_build_lifecycle_streamed_formal_input_candidate_impl",
        "_build_streamed_formal_input_candidate_from_reviewed_lifecycle_impl",
        "_require_streamed_formal_input_candidate_impl",
    )
    assert all(not hasattr(streaming_module, name) for name in forbidden)


@pytest.mark.parametrize("change", ("record", "contract"))
def test_authoritative_scoring_replay_requires_full_record_and_parent_identity(
    monkeypatch, change: str,
) -> None:
    contract = object()

    def artifact(record: dict[str, object], parent: object):
        return types.SimpleNamespace(
            artifact_id="scoring-id",
            artifact_sha256="a" * 64,
            archive_id="archive-id",
            archive_sha256="b" * 64,
            production_evidence_receipt_id="evidence-id",
            production_evidence_receipt_sha256="c" * 64,
            capacity_receipt_id="capacity-id",
            capacity_receipt_sha256="d" * 64,
            global_contract=parent,
            to_record=lambda: record,
        )

    authoritative = artifact({"complete": True}, contract)
    replay = artifact(
        {"complete": False} if change == "record" else {"complete": True},
        object() if change == "contract" else contract,
    )
    monkeypatch.setattr(
        streaming_module,
        "require_streamed_production_scoring_artifact",
        lambda value: value,
    )
    with pytest.raises(FormalStreamingInputError, match="differs"):
        streaming_module._require_authoritative_scoring_replay(
            authoritative=authoritative,
            replay=replay,
            expected_global_contract=contract,
        )


@pytest.mark.skipif(
    not hasattr(os, "fork") or not hasattr(os, "register_at_fork"),
    reason="requires POSIX fork reset semantics",
)
def test_stream_authority_child_resets_inherited_held_lock_and_vault(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    entered = threading.Event()
    release = threading.Event()

    def hold_inherited_lock():
        with streaming_module._STREAM_LOCK:
            entered.set()
            release.wait(15)

    holder = threading.Thread(target=hold_inherited_lock)
    holder.start()
    assert entered.wait(5)
    read_fd, write_fd = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover - assertions are returned by pipe
        os.close(read_fd)
        try:
            try:
                streaming_module.require_streamed_production_scoring_builder(
                    builder
                )
            except FormalStreamingInputError:
                pass
            else:
                raise AssertionError("inherited stream authority survived fork")
            with streaming_module._STREAM_LOCK:
                pass
            if streaming_module._STREAM_BUILDERS or streaming_module._STREAM_ARTIFACTS:
                raise AssertionError("inherited stream registries survived fork")
            payload = b"ok"
        except BaseException as exc:
            payload = (f"{type(exc).__name__}:{exc}").encode("utf-8")[:1000]
        try:
            os.write(write_fd, payload)
        finally:
            os.close(write_fd)
            os._exit(0)

    os.close(write_fd)
    child_reaped = False
    try:
        ready, _writable, _exceptional = select.select([read_fd], [], [], 10)
        if not ready:
            os.kill(child_pid, signal.SIGKILL)
            pytest.fail("child blocked on the inherited stream authority lock")
        payload = os.read(read_fd, 1000)
        _waited_pid, status = os.waitpid(child_pid, 0)
        child_reaped = True
        assert os.waitstatus_to_exitcode(status) == 0
        assert payload == b"ok", payload.decode("utf-8", errors="replace")
    finally:
        os.close(read_fd)
        release.set()
        if not child_reaped:
            os.waitpid(child_pid, 0)
        holder.join(timeout=5)
        assert not holder.is_alive()
    assert streaming_module.require_streamed_production_scoring_builder(builder) is builder


def test_stream_builder_mutation_during_hidden_lease_permanently_revokes(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    for name in (
        "_stream_vault_acquire",
        "_stream_vault_require_lease",
        "_stream_vault_block",
        "_stream_vault_fold",
        "_acquire_stream_builder",
        "_require_stream_lease",
    ):
        assert not hasattr(streaming_module, name)

    def corrupt_state(state, _observed):
        object.__setattr__(state, "matched_test_terminal_count", 1)

    with pytest.raises(FormalStreamingInputError, match="lease or state changed"):
        streaming_module._run_accepted_risk_power_calibration_stream(
            builder, corrupt_state
        )
    assert id(builder) not in streaming_module._STREAM_BUILDERS


def test_public_streaming_scorer_names_whole_graph_capacity_refusal(tmp_path):
    archive, _path = _physical_archive(
        tmp_path, _limits(max_retained_input_graph_bytes=1)
    )
    with pytest.raises(
        FormalStreamingRunRefusal,
        match=FormalStreamingRefusalReason.RETAINED_GRAPH_CAPACITY_EXCEEDED.value,
    ):
        begin_streamed_production_scoring(
            archive=archive,
            production_evidence_receipt=(
                archive.capacity.production_evidence_receipt
            ),
            global_contract=_global_contract(),
        )


def test_visible_contribution_index_refuses_mutate_record_restore_attack(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    stream_state = streaming_module._state(builder)
    source = stream_state.current_coverage_source
    source_state = input_bundle_module._GLOBAL_COVERAGE_SOURCES[id(source)][2]
    contribution = source_state.contributions[0]
    original = contribution.global_delta
    object.__setattr__(contribution, "global_delta", original + Fraction(1))
    try:
        with pytest.raises(
            FormalInputBundleError,
            match="visible contribution changed after authentication",
        ):
            formal_global_comparator_coverage_source_visible_contributions(
                source,
                decision_session=contribution.eligible_session,
                security_ids=(contribution.security_id,),
            )
    finally:
        object.__setattr__(contribution, "global_delta", original)
    assert formal_global_comparator_coverage_source_visible_contributions(
        source,
        decision_session=contribution.eligible_session,
        security_ids=(contribution.security_id,),
    )


def test_visible_contribution_index_binds_rating_action(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    source = streaming_module._state(builder).current_coverage_source
    source_state = input_bundle_module._GLOBAL_COVERAGE_SOURCES[id(source)][2]
    contribution = source_state.contributions[0]
    original = contribution.rating_action
    opposite = "downgrades" if original == "upgrades" else "upgrades"
    object.__setattr__(contribution, "rating_action", opposite)
    try:
        with pytest.raises(
            FormalInputBundleError,
            match="visible contribution changed after authentication",
        ):
            formal_global_comparator_coverage_source_visible_contributions(
                source,
                decision_session=contribution.eligible_session,
                security_ids=(contribution.security_id,),
            )
    finally:
        object.__setattr__(contribution, "rating_action", original)


def test_coverage_source_public_registry_refingerprint_cannot_reseal(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    source = streaming_module._state(builder).current_coverage_source
    registered = input_bundle_module._GLOBAL_COVERAGE_SOURCES[id(source)]
    forged = dataclasses.replace(
        registered[2],
        batch_sha256="f" * 64,
        fingerprint=b"",
        topology=(),
    )
    forged.fingerprint = input_bundle_module._coverage_source_fingerprint(forged)
    forged.topology = input_bundle_module._coverage_source_topology(forged)
    input_bundle_module._GLOBAL_COVERAGE_SOURCES[id(source)] = (
        registered[0],
        registered[1],
        forged,
        forged.fingerprint,
        forged.topology,
        forged.retained_payload_bytes,
        input_bundle_module._coverage_source_root_topology(forged),
    )
    try:
        with pytest.raises(FormalInputBundleError, match="source changed"):
            input_bundle_module.formal_global_comparator_coverage_source_retained_bytes(
                source
            )
    finally:
        input_bundle_module._GLOBAL_COVERAGE_SOURCES[id(source)] = registered
    assert (
        input_bundle_module._require_global_coverage_source(source)[0]
        is source
    )


def test_coverage_authority_mint_and_transition_primitives_are_not_addressable(
    tmp_path,
):
    forbidden = (
        "_make_global_coverage_authority_vault",
        "_coverage_authority_initialize_source",
        "_coverage_authority_require_source",
        "_coverage_authority_initialize_accumulator",
        "_coverage_authority_require_accumulator",
        "_coverage_authority_record_session",
        "_coverage_authority_finalize_accumulator",
        "_coverage_authority_private_registry_bytes",
        "_derive_global_coverage_session_transition",
        "_build_formal_global_comparator_coverage_source_impl",
        "_begin_formal_global_comparator_fold_coverage_from_source_impl",
        "_record_formal_global_comparator_coverage_session_impl",
        "_finish_formal_global_comparator_fold_coverage_impl",
    )
    assert all(not hasattr(input_bundle_module, name) for name in forbidden)

    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    source = streaming_module._state(builder).current_coverage_source
    source_registered = input_bundle_module._GLOBAL_COVERAGE_SOURCES[id(source)]
    forged_source = object.__new__(
        input_bundle_module.FormalGlobalComparatorCoverageSource
    )
    for name in ("source_id", "schema", "source_view_id"):
        object.__setattr__(forged_source, name, getattr(source, name))
    input_bundle_module._GLOBAL_COVERAGE_SOURCES[id(forged_source)] = (
        weakref.ref(forged_source),
        source_registered[1],
        *source_registered[2:],
    )
    try:
        with pytest.raises(FormalInputBundleError, match="builder-authenticated"):
            input_bundle_module._require_global_coverage_source(forged_source)
    finally:
        input_bundle_module._GLOBAL_COVERAGE_SOURCES.pop(id(forged_source), None)

    accumulator = (
        input_bundle_module.begin_formal_global_comparator_fold_coverage_from_source(
            fold_id="arv2-wf-test-2020",
            source=source,
        )
    )
    accumulator_registered = input_bundle_module._GLOBAL_COVERAGE_ACCUMULATORS[
        id(accumulator)
    ]
    forged_accumulator = object.__new__(
        input_bundle_module.FormalGlobalComparatorCoverageAccumulator
    )
    for name in ("accumulator_id", "schema", "fold_id", "source_view_id"):
        object.__setattr__(forged_accumulator, name, getattr(accumulator, name))
    input_bundle_module._GLOBAL_COVERAGE_ACCUMULATORS[id(forged_accumulator)] = (
        weakref.ref(forged_accumulator),
        accumulator_registered[1],
        *accumulator_registered[2:],
    )
    try:
        with pytest.raises(FormalInputBundleError, match="builder-authenticated"):
            input_bundle_module._require_global_coverage_accumulator(
                forged_accumulator
            )
    finally:
        input_bundle_module._GLOBAL_COVERAGE_ACCUMULATORS.pop(
            id(forged_accumulator), None
        )


@pytest.mark.skipif(
    not hasattr(os, "fork") or not hasattr(os, "register_at_fork"),
    reason="requires POSIX fork reset semantics",
)
def test_coverage_authority_child_resets_inherited_held_lock_and_vault(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    stream_state = streaming_module._state(builder)
    source = stream_state.current_coverage_source
    source_state = input_bundle_module._GLOBAL_COVERAGE_SOURCES[id(source)][2]
    entered = threading.Event()
    release = threading.Event()

    def hold_inherited_lock():
        with input_bundle_module._GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            entered.set()
            release.wait(15)

    holder = threading.Thread(target=hold_inherited_lock)
    holder.start()
    assert entered.wait(5)
    read_fd, write_fd = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:  # pragma: no cover - assertions are returned by pipe
        os.close(read_fd)
        try:
            try:
                input_bundle_module._require_global_coverage_source(source)
            except FormalInputBundleError:
                pass
            else:
                raise AssertionError("inherited source authority survived fork")
            with input_bundle_module._GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
                pass
            fresh = (
                input_bundle_module.build_formal_global_comparator_coverage_source(
                    signal_arm=source_state.signal_arm,
                    batch=stream_state.current_batch,
                    global_contract=stream_state.global_contract,
                    endpoint_labels=source_state.endpoint_labels,
                )
            )
            input_bundle_module._require_global_coverage_source(fresh)
            payload = b"ok"
        except BaseException as exc:
            payload = (f"{type(exc).__name__}:{exc}").encode("utf-8")[:1000]
        try:
            os.write(write_fd, payload)
        finally:
            os.close(write_fd)
            os._exit(0)

    os.close(write_fd)
    try:
        ready, _writable, _exceptional = select.select([read_fd], [], [], 10)
        if not ready:
            os.kill(child_pid, signal.SIGKILL)
            pytest.fail("child blocked on the inherited coverage authority lock")
        payload = os.read(read_fd, 1000)
        _waited_pid, status = os.waitpid(child_pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        assert payload == b"ok", payload.decode("utf-8", errors="replace")
    finally:
        os.close(read_fd)
        release.set()
        holder.join(timeout=5)
        if holder.is_alive():
            pytest.fail("parent coverage lock holder did not exit")


def test_coverage_accumulator_refuses_private_counter_mutation(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    source = streaming_module._state(builder).current_coverage_source
    accumulator = (
        input_bundle_module.begin_formal_global_comparator_fold_coverage_from_source(
            fold_id="arv2-wf-test-2020",
            source=source,
        )
    )
    accumulator_state = input_bundle_module._GLOBAL_COVERAGE_ACCUMULATORS[
        id(accumulator)
    ][2]
    for name in (
        "next_session_index",
        "firm_active_count",
        "paired_active_count",
        "firm_component_count",
        "retained_component_count",
        "firm_component_incidence",
        "retained_component_incidence",
        "candidate_dates",
        "capable_dates",
    ):
        original = getattr(accumulator_state, name)
        object.__setattr__(accumulator_state, name, original + 1)
        try:
            with pytest.raises(FormalInputBundleError, match="accumulator changed"):
                input_bundle_module.formal_global_comparator_coverage_accumulator_retained_bytes(
                    accumulator
                )
        finally:
            object.__setattr__(accumulator_state, name, original)
        assert (
            input_bundle_module._require_global_coverage_accumulator(accumulator)[0]
            is accumulator
        )


def test_coverage_accumulator_public_registry_resnapshot_cannot_reseal(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    source = streaming_module._state(builder).current_coverage_source
    accumulator = (
        input_bundle_module.begin_formal_global_comparator_fold_coverage_from_source(
            fold_id="arv2-wf-test-2020",
            source=source,
        )
    )
    registered = input_bundle_module._GLOBAL_COVERAGE_ACCUMULATORS[id(accumulator)]
    forged = dataclasses.replace(registered[2], candidate_dates=1)
    input_bundle_module._GLOBAL_COVERAGE_ACCUMULATORS[id(accumulator)] = (
        registered[0],
        registered[1],
        forged,
        input_bundle_module._coverage_accumulator_snapshot(forged),
    )
    try:
        with pytest.raises(FormalInputBundleError, match="accumulator changed"):
            input_bundle_module.formal_global_comparator_coverage_accumulator_retained_bytes(
                accumulator
            )
    finally:
        input_bundle_module._GLOBAL_COVERAGE_ACCUMULATORS[id(accumulator)] = registered
    assert (
        input_bundle_module._require_global_coverage_accumulator(accumulator)[0]
        is accumulator
    )


def test_coverage_accumulator_preflights_old_plus_new_transition_graph(tmp_path):
    archive, _path = _physical_archive(tmp_path)
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    source = streaming_module._state(builder).current_coverage_source
    accumulator = (
        input_bundle_module.begin_formal_global_comparator_fold_coverage_from_source(
            fold_id="arv2-wf-test-2020",
            source=source,
        )
    )
    registered = input_bundle_module._GLOBAL_COVERAGE_ACCUMULATORS[id(accumulator)]
    state = registered[2]
    prior_snapshot = registered[3]
    next_state = dataclasses.replace(state, next_session_index=1)
    next_snapshot = input_bundle_module._coverage_accumulator_snapshot(next_state)
    next_registered = (registered[0], registered[1], next_state, next_snapshot)
    transition_bytes_without_private_vault = (
        input_bundle_module._coverage_accumulator_transition_retained_bytes(
            accumulator=accumulator,
            prior_state=state,
            prior_snapshot=prior_snapshot,
            prior_registered=registered,
            next_state=next_state,
            next_snapshot=next_snapshot,
            next_registered=next_registered,
        )
    )
    steady_bytes = (
        input_bundle_module.formal_global_comparator_coverage_accumulator_retained_bytes(
            accumulator
        )
    )
    steady_bytes_without_private_vault = (
        input_bundle_module._coverage_accumulator_steady_retained_bytes(
            accumulator=accumulator,
            state=state,
            snapshot=prior_snapshot,
            registered=registered,
        )
    )
    transition_bytes = (
        transition_bytes_without_private_vault
        + steady_bytes
        - steady_bytes_without_private_vault
    )
    assert transition_bytes > steady_bytes
    session = state.expected_sessions[0]
    with pytest.raises(
        FormalInputBundleError,
        match="transition retained graph exceeded reviewed capacity",
    ):
        input_bundle_module.record_formal_global_comparator_coverage_session(
            accumulator,
            decision_session=session,
            census_rows=(),
            final_rows=(),
            final_refusals=(),
            maximum_retained_bytes=transition_bytes - 1,
        )
    assert input_bundle_module._GLOBAL_COVERAGE_ACCUMULATORS[id(accumulator)][2] is state
    assert state.next_session_index == 0
    observed_peak = input_bundle_module.record_formal_global_comparator_coverage_session(
        accumulator,
        decision_session=session,
        census_rows=(),
        final_rows=(),
        final_refusals=(),
        maximum_retained_bytes=transition_bytes,
    )
    assert observed_peak == transition_bytes
    assert (
        input_bundle_module._GLOBAL_COVERAGE_ACCUMULATORS[id(accumulator)][2]
        .next_session_index
        == 1
    )


def test_disk_spooled_mgs_is_bounded_and_byte_identical_to_frozen_solver():
    limits = {
        "max_disk_mgs_width": 8,
        "max_disk_mgs_live_decimal_count": 128,
        "max_disk_mgs_spool_row_count": 100,
        "max_disk_mgs_spool_byte_count": 1024 * 1024,
        "max_disk_mgs_spool_file_count": 20,
    }
    design = tuple(
        (Decimal(1), Decimal(index)) for index in range(30)
    )
    response = tuple(
        Decimal(2) + Decimal(3) * Decimal(index) for index in range(30)
    )
    qr = _DiskBackedDecimalMgs(2, limits)
    for row, value in zip(design, response, strict=True):
        qr.update(row, value, value)
    streamed, mirrored = qr.solve()
    legacy = _solve_ols(design, response)
    assert streamed == mirrored
    assert streamed == legacy
    assert qr.decimal_count == 16
    with pytest.raises(
        FormalStreamingRunRefusal,
        match=FormalStreamingRefusalReason.QR_CAPACITY_EXCEEDED.value,
    ):
        _DiskBackedDecimalMgs(9, limits)


def test_disk_spooled_mgs_matches_frozen_solver_for_near_collinear_design():
    limits = {
        "max_disk_mgs_width": 8,
        "max_disk_mgs_live_decimal_count": 128,
        "max_disk_mgs_spool_row_count": 100,
        "max_disk_mgs_spool_byte_count": 1024 * 1024,
        "max_disk_mgs_spool_file_count": 20,
    }
    epsilon = Decimal("1e-15")
    design = tuple(
        (
            Decimal(1),
            Decimal(index),
            Decimal(index) + (epsilon if index % 2 else -epsilon),
        )
        for index in range(40)
    )
    firm = tuple(
        Decimal("0.25") + Decimal("1.5") * row[1] - Decimal("0.5") * row[2]
        for row in design
    )
    global_values = tuple(
        Decimal("-0.75") - Decimal("0.25") * row[1] + Decimal("2.25") * row[2]
        for row in design
    )
    fit = _DiskBackedDecimalMgs(3, limits)
    for row, firm_value, global_value in zip(
        design, firm, global_values, strict=True
    ):
        fit.update(row, firm_value, global_value)
    streamed_firm, streamed_global = fit.solve()
    assert streamed_firm == _solve_ols(design, firm)
    assert streamed_global == _solve_ols(design, global_values)


def test_disk_builder_persists_descriptors_not_payloads_and_reauthenticates(tmp_path):
    physical, _path = _physical_archive(tmp_path)
    output = tmp_path / "formal-shards"
    writer = _BoundedFormalDiskBuilder(
        output_directory=output, capacity=physical.capacity
    )
    writer.add_block(
        "decision_joins",
        [
            {
                "schema": SHARD_ROW_SCHEMAS["decision_joins"],
                "fold_id": "arv2-wf-test-2020",
                "session_position": 1,
                "source_view_id": CURRENT_VIEW_LABEL,
                "security_id": "security-00",
            }
        ],
    )
    archive = writer.finish()
    assert tuple(item.role for item in archive.descriptors) == SHARD_ROLE_ORDER
    assert not hasattr(archive.descriptors[0], "payload")
    payloads = tuple(iter_physical_formal_shard_payloads(archive))
    assert len(payloads) == len(SHARD_ROLE_ORDER)
    assert sum(len(item.payload) for item in payloads) == archive.compressed_byte_count


def test_disk_builder_refuses_reordering_and_named_block_overflow(tmp_path):
    physical, _path = _physical_archive(
        tmp_path,
        _limits(max_formal_session_block_row_count=1),
    )
    first_output = tmp_path / "formal-order"
    writer = _BoundedFormalDiskBuilder(
        output_directory=first_output, capacity=physical.capacity
    )
    row = {
        "schema": SHARD_ROW_SCHEMAS["decision_joins"],
        "fold_id": "arv2-wf-test-2020",
        "session_position": 2,
        "source_view_id": CURRENT_VIEW_LABEL,
        "security_id": "security-00",
    }
    writer.add_block("decision_joins", [row])
    reversed_row = dict(row)
    reversed_row["session_position"] = 1
    with pytest.raises(FormalStreamingInputError, match="repeated or reversed"):
        writer.add_block("decision_joins", [reversed_row])

    overflow_output = tmp_path / "formal-overflow"
    overflow = _BoundedFormalDiskBuilder(
        output_directory=overflow_output, capacity=physical.capacity
    )
    second = dict(row)
    second["security_id"] = "security-01"
    with pytest.raises(
        FormalStreamingRunRefusal,
        match=FormalStreamingRefusalReason.FORMAL_BLOCK_CAPACITY_EXCEEDED.value,
    ):
        overflow.add_block("decision_joins", [row, second])


def test_public_candidate_runs_all_folds_to_reopenable_physical_shards(
    tmp_path, monkeypatch
):
    (
        archive, accepted, formal_power, power_floor, terminal_package,
        _loaded_power, _power_parents,
    ) = (
        _full_sparse_formal_fixture(tmp_path)
    )
    economic_execution = build_formal_economic_execution_binding(
        build_formal_economic_execution_definition(_stock())
    )
    builder = begin_streamed_production_scoring(
        archive=archive,
        production_evidence_receipt=archive.capacity.production_evidence_receipt,
        global_contract=_global_contract(),
    )
    bad_accepted = dataclasses.replace(
        accepted,
        current_admitted_decision_count=(
            accepted.current_admitted_decision_count - 1
        ),
        current_named_preoutcome_refusal_count=(
            accepted.current_named_preoutcome_refusal_count + 1
        ),
    )
    rejected_directory = tmp_path / "rejected-formal-shards"
    with pytest.raises(FormalStreamingInputError, match="accepted-risk pair"):
        build_streamed_formal_input_candidate(
            scoring_builder=builder,
            accepted_risk=bad_accepted,
            formal_power=formal_power,
            power_floor=power_floor,
            economic_execution=economic_execution,
            terminal_package=terminal_package,
            benchmark_security_id="security-00",
            calculation_as_of_date=date(2026, 9, 12),
            output_directory=rejected_directory,
        )
    assert not rejected_directory.exists()

    future_row = {
        "schema": TERMINAL_OBJECT_SCHEMA,
        "slot_kind": "decision_horizon",
        "slot_id": "fixture-future-terminal",
        "horizon": 20,
        "disposition": "named_terminal_refusal",
        "stock_return": None,
        "reason": "terminal_payoff_unresolved",
        "terminal_lineage_sha256": "6" * 64,
        "available_at_utc": "2026-09-13T00:00:00Z",
    }
    future_payload = canonical_json_bytes(
        {
            "schema": TERMINAL_PACKAGE_SCHEMA,
            "terminal_policy_id": "arv2-terminal-payoff-benchmark-splice-v1",
            "row_count": 1,
            "rows": [future_row],
        }
    )
    future_census = TerminalCensusBinding(
            census=ArtifactBinding(
                artifact_id="fixture-future-terminal-census",
                content_sha256=sha256_bytes(future_payload),
                artifact_sha256="7" * 64,
                byte_count=len(future_payload),
            ),
            terminal_policy_id="arv2-terminal-payoff-benchmark-splice-v1",
            security_count=20,
            lifecycle_coverage_count=20,
            terminal_requirement_count=1,
            terminal_payoff_count=0,
            benchmark_splice_continuation_count=0,
            named_terminal_refusal_count=1,
            silently_omitted_count=0,
        )
    future_package = load_formal_terminal_disposition_package(
        payload=future_payload,
        terminal_census=future_census,
    )
    future_directory = tmp_path / "future-formal-shards"
    with pytest.raises(FormalStreamingInputError, match="calculation_as_of_date"):
        build_streamed_formal_input_candidate(
            scoring_builder=builder,
            accepted_risk=accepted,
            formal_power=formal_power,
            power_floor=power_floor,
            economic_execution=economic_execution,
            terminal_package=future_package,
            benchmark_security_id="security-00",
            calculation_as_of_date=date(2026, 9, 12),
            output_directory=future_directory,
        )
    assert not future_directory.exists()

    from .test_qc_formal_terminal_disposition_builder import _fake_bridge

    lifecycle_sessions = trading_sessions(date(2013, 1, 2), date(2025, 12, 31))
    lifecycle_bridge = _fake_bridge(
        monkeypatch,
        sessions=lifecycle_sessions,
        terminal_states={
            "axis-anchor-security": tuple(None for _ in lifecycle_sessions)
        },
    )
    terminal_recorder = begin_formal_terminal_disposition_recording(
        historical_bridge=lifecycle_bridge,
        output_directory=tmp_path / "streamed-terminal-build",
    )
    candidate = build_lifecycle_streamed_formal_input_candidate(
        scoring_builder=builder,
        accepted_risk=accepted,
        formal_power=formal_power,
        power_floor=power_floor,
        economic_execution=economic_execution,
        terminal_recorder=terminal_recorder,
        benchmark_security_id="security-00",
        calculation_as_of_date=date(2026, 9, 12),
        output_directory=tmp_path / "formal-shards-end-to-end",
    )
    assert require_streamed_formal_input_candidate(candidate) is candidate
    assert candidate.terminal_build is not None
    assert require_formal_terminal_disposition_build(candidate.terminal_build) is (
        candidate.terminal_build
    )
    assert candidate.terminal_build.terminal_package is candidate.terminal_package
    assert candidate.terminal_build.terminal_census is (
        candidate.terminal_package.terminal_census
    )
    assert candidate.terminal_build.security_count == 20
    assert candidate.terminal_build.lifecycle_missing_security_count == 20
    assert candidate.terminal_build.silently_omitted_count == 0
    assert candidate.scoring.matched_test_terminal_count == 120
    assert candidate.decision_join_count == 240
    h1_decision_session_count = sum(
        len(tuple(
            session
            for session in trading_sessions(
                date.fromisoformat(boundary[6]),
                date.fromisoformat(boundary[7]),
            )
            if session < date.fromisoformat(boundary[7])
        ))
        for boundary in FORMAL_HORIZON_FOLD_BOUNDARIES
        if boundary[1] == 1
    )
    # Every H1 TEST session has one row per source view.  Each fold then has
    # H20-1 runoff intervals plus one terminal-cost row per source view.
    expected_economic_join_count = len(SOURCE_VIEW_IDS) * (
        h1_decision_session_count
        + len(FORMAL_FOLD_BOUNDARIES) * HOLDING_SESSIONS
    )
    assert candidate.economic_join_count == expected_economic_join_count
    assert candidate.qc_launch_available is False
    reopened = tuple(iter_physical_formal_shard_payloads(candidate.shards))
    assert tuple(item.descriptor.role for item in reopened) == SHARD_ROLE_ORDER
    assert all(
        sha256_bytes(item.payload) == item.descriptor.compressed_sha256
        for item in reopened
    )
    transported = 0
    for shard, descriptor in zip(
        iter_formal_qc_compressed_shards(candidate.shards),
        candidate.shards.descriptors,
        strict=True,
    ):
        assert shard.descriptor() == descriptor.to_record()
        transported += 1
    assert transported == candidate.shards.shard_count

    runtime_limits = _runtime_limits(
        max_dynamic_subscription_count=2,
        max_node_memory_byte_count=4_000_000_000,
    )
    resource = build_streamed_formal_runtime_resource_candidate(
        streamed_input=candidate,
        maximum_dynamic_subscription_count=2,
        proposed_runtime_limits=runtime_limits,
    )
    # Test-only legacy materialization proves that the disk-backed census is
    # byte/geometry-equivalent.  The production bridge below never creates
    # this tuple.
    legacy_shards = tuple(iter_formal_qc_compressed_shards(candidate.shards))
    legacy_census = derive_formal_qc_runtime_resource_census(
        shards=legacy_shards,
        distinct_security_count=resource.resource_census.distinct_security_count,
        daily_history_batch_count=(
            resource.resource_census.daily_history_batch_count
        ),
        minute_history_batch_count=(
            resource.resource_census.minute_history_batch_count
        ),
        maximum_dynamic_subscription_count=2,
        projected_summary_payload_byte_count=(
            resource.resource_census.projected_summary_payload_byte_count
        ),
        projected_summary_chunk_count=(
            resource.resource_census.projected_summary_chunk_count
        ),
    )
    assert resource.resource_census == legacy_census
    assert resource.physical_shard_payloads_retained is False

    runtime_review = _write_runtime_capacity_review(tmp_path, resource)
    unsigned_review = tmp_path / "unsigned-streamed-bridge-review.json"
    unsigned_review.write_bytes(
        render_streamed_formal_runtime_bridge_review_candidate(
            resource_candidate=resource,
            runtime_capacity_reviewed_receipt_path=runtime_review,
        )
    )
    os.chmod(unsigned_review, 0o600)
    with pytest.raises(
        FormalStreamingBridgeError, match="independent affirmative review"
    ):
        load_streamed_formal_runtime_capacity_binding(
            resource_candidate=resource,
            runtime_capacity_reviewed_receipt_path=runtime_review,
            streamed_bridge_reviewed_receipt_path=unsigned_review,
        )

    bridge_review = _write_streamed_bridge_review(
        tmp_path, resource, runtime_review
    )
    reviewed = load_streamed_formal_runtime_capacity_binding(
        resource_candidate=resource,
        runtime_capacity_reviewed_receipt_path=runtime_review,
        streamed_bridge_reviewed_receipt_path=bridge_review,
    )
    formal_source = (ROOT / FORMAL_EVALUATOR_PROJECT_PATH).read_bytes()
    cloud_source = (ROOT / runtime.CLOUD_EVALUATOR_PROJECT_PATH).read_bytes()
    bridge = build_streamed_formal_runtime_bridge(
        resource_candidate=resource,
        capacity=reviewed,
        formal_evaluator_source=formal_source,
        cloud_evaluator_source=cloud_source,
    )
    assert require_streamed_formal_runtime_bridge(bridge) is bridge
    manifest = json.loads(bridge.input_manifest_payload)
    assert manifest["resource_census"] == resource.resource_census.to_record()
    assert manifest["upstream_scoring_materialization_capacity"][
        "launch_authorized"
    ] is True
    assert manifest["capacity_evidence_is_submission_authority"] is False
    assert reviewed.submission_authority is False
    assert reviewed.qc_launch_available is False
    assert bridge.physical_shard_payloads_retained is False
    assert bridge.legacy_tuple_upload_compatible is False
    assert bridge.qc_launch_available is False
    assert bridge.formal_run_candidate.production_input_package is (
        bridge.production_input_package
    )
    assert bridge.formal_run_candidate.current_view_partition_set is (
        resource.current_view_partition_set
    )
    assert bridge.formal_run_candidate.censored_view_partition_set is (
        resource.censored_view_partition_set
    )

    replay_records = []
    for entry in iter_streamed_formal_qc_upload_entries(bridge):
        assert sha256_bytes(entry.payload) == entry.content_sha256
        assert len(entry.payload) == entry.byte_count
        replay_records.append(entry.to_record())
        del entry
    assert replay_records == [
        item.to_record() for item in bridge.upload_descriptors
    ]
    assert replay_records[-1]["role"] == "input_manifest"

    low_resource = build_streamed_formal_runtime_resource_candidate(
        streamed_input=candidate,
        maximum_dynamic_subscription_count=2,
        proposed_runtime_limits=_runtime_limits(
            max_dynamic_subscription_count=2, max_shard_count=1
        ),
    )
    low_runtime_review = _write_runtime_capacity_review(
        tmp_path, low_resource, suffix="-low"
    )
    low_bridge_review = _write_streamed_bridge_review(
        tmp_path,
        low_resource,
        low_runtime_review,
        suffix="-low",
    )
    low_capacity = load_streamed_formal_runtime_capacity_binding(
        resource_candidate=low_resource,
        runtime_capacity_reviewed_receipt_path=low_runtime_review,
        streamed_bridge_reviewed_receipt_path=low_bridge_review,
    )
    with pytest.raises(FormalStreamingBridgeError, match="could not be built"):
        build_streamed_formal_runtime_bridge(
            resource_candidate=low_resource,
            capacity=low_capacity,
            formal_evaluator_source=formal_source,
            cloud_evaluator_source=cloud_source,
        )

    unrelated_partition = ArtifactBinding(
        artifact_id="fixture-unrelated-source-view-partition",
        content_sha256="8" * 64,
        artifact_sha256="9" * 64,
        byte_count=1,
    )
    forged_candidate = build_formal_run_candidate(
        code_projection=bridge.formal_run_candidate.code_projection,
        production_input_package=bridge.production_input_package,
        current_view_partition_set=unrelated_partition,
        censored_view_partition_set=bridge.censored_view_partition_set,
        accepted_risk=candidate.accepted_risk,
        power_floor=candidate.power_floor,
        terminal_census=candidate.terminal_package.terminal_census,
    )
    authentic_candidate = bridge.formal_run_candidate
    object.__setattr__(bridge, "formal_run_candidate", forged_candidate)
    with pytest.raises(
        FormalStreamingBridgeError, match="changed after authentication"
    ):
        require_streamed_formal_runtime_bridge(bridge)
    object.__setattr__(bridge, "formal_run_candidate", authentic_candidate)
    assert require_streamed_formal_runtime_bridge(bridge) is bridge

    # The additive submission successor consumes this exact physical bridge
    # without constructing the legacy all-payload tuple.  All trust and
    # transport substitutions below are explicit offline-only test seams.
    _install_offline_action_authority(monkeypatch)
    monkeypatch.setattr(
        submission,
        "verify_formal_qc_host_closure_live",
        _with_closure_value(
            submission.verify_formal_qc_host_closure_live,
            "binding_guard",
            lambda _kind: None,
        ),
    )
    monkeypatch.setattr(
        submission,
        "_require_non_self_mintable_execution_trust_root",
        lambda *_args, **_kwargs: None,
    )

    def offline_review_gate(*args, **kwargs):
        return (
            kwargs.get("authority")
            or kwargs.get("reviewed_authority")
            or args[-1]
        )

    monkeypatch.setattr(
        submission, "require_reviewed_formal_run_authority", offline_review_gate
    )
    monkeypatch.setattr(
        submission,
        "require_synthetic_qc_runtime_shard_projection",
        lambda value: value,
    )
    monkeypatch.setattr(
        submission, "_PINNED_PRODUCTION_TRANSPORT_CHECK", lambda _value: None
    )
    monkeypatch.setattr(submission, "require_formal_look_claim", lambda *args: args[-1])
    monkeypatch.setattr(submission, "_local_wait", lambda _seconds: None)
    fake_b5d = types.SimpleNamespace(
        projection_id="arv2-b5d-streamed-source-set",
        projection_sha256="a" * 64,
        projection_artifact_sha256="b" * 64,
        project_file_count=11,
        total_projected_source_byte_count=1000,
    )
    host_closure = submission.build_formal_qc_host_closure_binding(
        worktree_root=ROOT, b5d_project_source_set=fake_b5d
    )
    transport = submission.build_formal_qc_transport_binding(
        host_code_closure=host_closure
    )
    organization_id = "test-organization-001"
    provisional = ReviewedFormalRunAuthority(
        authority_id="arv2-reviewed-streamed-test",
        authority_sha256="c" * 64,
        candidate_id=bridge.formal_run_candidate.candidate_id,
        candidate_sha256=bridge.formal_run_candidate.candidate_sha256,
        claude_review_commit="d" * 40,
        codex_counterreview_commit="e" * 40,
        owner_decision_id="arv2-owner-streamed-test",
        owner_outcome_authority_receipt_id="placeholder",
        review_receipt_artifact_sha256="f" * 64,
        claim_directory=tmp_path / "streamed-claim",
        maximum_submissions=1,
        result_read_requires_separate_terminal_gate=True,
        _receipt_bytes=b"offline-test-only",
        _external_pin=None,  # type: ignore[arg-type]
    )
    authority_bytes = submission.render_streamed_formal_qc_execution_authority_candidate(
        runtime_bridge=bridge,
        host_code_closure=host_closure,
        transport=transport,
        organization_id=organization_id,
    )
    reviewed_authority = dataclasses.replace(
        provisional,
        owner_outcome_authority_receipt_id=json.loads(authority_bytes)[
            "authority_id"
        ],
    )
    execution_authority = submission.load_streamed_formal_qc_execution_authority(
        runtime_bridge=bridge,
        reviewed_authority=reviewed_authority,
        host_code_closure=host_closure,
        transport=transport,
        organization_id=organization_id,
        receipt_bytes=authority_bytes,
    )
    authenticated_power = types.SimpleNamespace(
        binding_id="arv2-offline-authenticated-power-floor",
        binding_sha256="7" * 64,
        power_floor=bridge.formal_run_candidate.power_floor,
        formal_power=candidate.formal_power,
        scoring_artifact_id=candidate.scoring.artifact_id,
        scoring_artifact_sha256=candidate.scoring.artifact_sha256,
        formal_census=types.SimpleNamespace(scoring_artifact=candidate.scoring),
    )

    def require_offline_authenticated_power(value):
        if value is not authenticated_power:
            raise power_bridge.AcceptedRiskPowerCalibrationError(
                "offline power-floor substitute"
            )
        return value

    monkeypatch.setattr(
        power_bridge,
        "require_authenticated_power_floor_binding",
        require_offline_authenticated_power,
    )
    submission_bridge = submission.build_streamed_formal_submission_adapter_bridge(
        runtime_bridge=bridge,
        reviewed_authority=reviewed_authority,
        execution_authority=execution_authority,
        authenticated_power_floor=authenticated_power,
        organization_id=organization_id,
    )
    assert (
        submission.require_streamed_formal_submission_adapter_bridge(
            submission_bridge
        )
        is submission_bridge
    )
    claim = FormalLookClaim(
        claim_id="arv2-streamed-claim-test",
        claim_sha256="1" * 64,
        authority_id=reviewed_authority.authority_id,
        candidate_id=bridge.formal_run_candidate.candidate_id,
        candidate_sha256=bridge.formal_run_candidate.candidate_sha256,
        claimed_at_utc="2026-09-12T12:00:00.000000Z",
        maximum_submissions=1,
        submission_count_reserved=1,
        ambiguous_submission_consumes_look=True,
        retry_authorized=False,
        claim_path=tmp_path / "streamed-claim" / "claim.json",
        _claim_bytes=b"offline-test-only",
    )
    events: list[str] = []
    client = _FakeClient(events, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        submission,
        "begin_formal_submission_once",
        lambda **_kwargs: _permit(
            bridge.formal_run_candidate,
            reviewed_authority,
            claim,
            events,
        ),
    )
    with pytest.raises(
        submission.FormalQcSubmissionError,
        match="action global authority changed",
    ):
        _PRODUCTION_STREAMED_SUBMISSION_ACTION(
            submission_bridge=submission_bridge,
            claim=claim,
            client=client,
            submission_started_at_utc="2026-09-12T12:01:00.000000Z",
        )
    assert events == []
    permit, launch = submission.execute_streamed_formal_qc_submission_once(
        submission_bridge=submission_bridge,
        claim=claim,
        client=client,
        submission_started_at_utc="2026-09-12T12:01:00.000000Z",
    )
    assert events[:2] == ["permit", "request:authenticate"]
    set_events = [event for event in events if event.startswith("set_object:")]
    assert len(set_events) == bridge.upload_entry_count
    assert set_events[-1] == (
        "set_object:" + bridge.upload_descriptors[-1].object_store_key
    )
    assert tuple(client._test_backend.objects) == tuple(
        item.object_store_key for item in bridge.upload_descriptors
    )
    assert launch.input_object_count == bridge.upload_entry_count
    assert launch.backtest_submission_count == 1
    assert submission.require_streamed_formal_qc_launch_receipt(
        value=launch, permit=permit, plan=submission_bridge.plan
    ) is launch

    monkeypatch.setattr(
        submission,
        "require_formal_submission_permit",
        lambda *_args, **_kwargs: permit,
    )
    terminal = submission.inspect_streamed_statistics_free_terminal_status(
        submission_bridge=submission_bridge,
        claim=claim,
        permit=permit,
        launch=launch,
        client=client,
    )
    assert terminal.terminal_status == "Completed."
    assert terminal.status_poll_count == 2
    assert terminal.full_status_envelope_received_and_json_parsed is True
    assert terminal.statistics_or_result_values_selected_or_inspected is False
    assert terminal.discarded_values_retained_in_receipt_or_exported is False
    assert client._test_backend.status_reads == 2
    capability = submission.streamed_formal_post_launch_capability_record(
        submission_bridge
    )
    assert capability[
        "identity_status_only_value_selection_with_include_statistics_false"
    ] is True
    assert capability["builder_authenticated_summary_result_receipt"] is True
    gate = submission.build_streamed_formal_qc_result_gate_candidate(
        terminal=terminal,
        launch=launch,
        submission_bridge=submission_bridge,
        claim=claim,
        permit=permit,
    )
    assert submission.require_streamed_formal_qc_result_gate_candidate(
        value=gate,
        terminal=terminal,
        launch=launch,
        submission_bridge=submission_bridge,
        claim=claim,
        permit=permit,
    ) is gate
    monkeypatch.setattr(
        submission,
        "_require_non_self_mintable_result_read_trust_root",
        lambda *_args, **_kwargs: None,
    )
    os.mkdir(reviewed_authority.claim_directory, 0o700)
    authority_bytes = submission.render_formal_qc_result_read_authority_candidate(
        gate,
        launch,
        terminal,
        candidate=bridge.formal_run_candidate,
        reviewed_authority=reviewed_authority,
    )
    pin_bytes = submission.render_formal_qc_result_read_external_pin_candidate(
        candidate=bridge.formal_run_candidate,
        reviewed_authority=reviewed_authority,
        gate=gate,
        launch=launch,
        terminal=terminal,
        result_authority_receipt_bytes=authority_bytes,
    )
    pin_path = (
        reviewed_authority.claim_directory
        / submission.RESULT_READ_EXTERNAL_PIN_FILENAME
    )
    pin_path.write_bytes(pin_bytes)
    os.chmod(pin_path, 0o600)
    result_authority = submission.load_formal_qc_result_read_authority(
        gate=gate,
        launch=launch,
        terminal=terminal,
        candidate=bridge.formal_run_candidate,
        reviewed_authority=reviewed_authority,
        receipt_bytes=authority_bytes,
    )
    # This all-fold test exercises the public process-authority chain.  Exact
    # root-first + 26 ordered Object Store reads and cloud payload validation
    # have their own transport test, so provide only a bounded offline result
    # package here instead of evaluating synthetic market outcomes again.
    offline_root_manifest = canonical_json_bytes(
        {"streamed_preknown_bindings": {"offline_test_only": True}}
    )
    offline_bindings_record = {
        "input_manifest_sha256": bridge.input_manifest.content_sha256,
        "formal_report_contract_sha256": bridge.report_contract.contract_sha256,
    }
    offline_bindings = types.SimpleNamespace(
        **offline_bindings_record,
        to_record=lambda: dict(offline_bindings_record),
    )
    offline_descriptors = tuple(
        types.SimpleNamespace(
            object_store_key_suffix=f"offline/result-family-{ordinal:02d}.json.gz",
            uncompressed_byte_count=len(f"family-{ordinal:02d}") + 1,
            compressed_byte_count=len(f"family-{ordinal:02d}"),
            to_record=(
                lambda index=ordinal: {
                    "ordinal": index,
                    "object_store_key_suffix": (
                        f"offline/result-family-{index:02d}.json.gz"
                    ),
                }
            ),
        )
        for ordinal in range(submission.FORMAL_RESULT_FAMILY_READ_COUNT)
    )
    offline_family_payloads = tuple(
        (
            descriptor.object_store_key_suffix,
            f"family-{descriptor_index:02d}".encode("ascii"),
        )
        for descriptor_index, descriptor in enumerate(offline_descriptors)
    )
    monkeypatch.setattr(
        submission,
        "_reconstruct_formal_result_root",
        lambda *_args, **_kwargs: (offline_root_manifest, {}),
    )
    monkeypatch.setattr(
        submission,
        "_read_streamed_formal_result_family_objects",
        lambda **_kwargs: (
            offline_bindings,
            offline_descriptors,
            offline_family_payloads,
        ),
    )
    result_receipt = submission.read_streamed_formal_qc_summary_result_once(
        result_authority=result_authority,
        result_gate=gate,
        submission_bridge=submission_bridge,
        terminal=terminal,
        launch=launch,
        claim=claim,
        submission_permit=permit,
        client=client,
        result_read_started_at_utc="2026-09-12T12:04:00Z",
    )
    assert result_receipt.full_result_envelope_received_and_json_parsed is True
    assert result_receipt.standard_statistic_values_selected_or_inspected is False
    assert result_receipt.unrelated_values_retained_in_receipt_or_exported is False
    assert submission.require_formal_qc_summary_result_read_receipt(
        result_receipt,
        result_authority=result_authority,
        terminal=terminal,
        launch=launch,
    ) is result_receipt
    first_result_read_count = events.count("request:backtests/read")
    with pytest.raises(submission.FormalQcSubmissionLocked):
        submission.read_streamed_formal_qc_summary_result_once(
            result_authority=result_authority,
            result_gate=gate,
            submission_bridge=submission_bridge,
            terminal=terminal,
            launch=launch,
            claim=claim,
            submission_permit=permit,
            client=client,
            result_read_started_at_utc="2026-09-12T12:05:00Z",
        )
    assert events.count("request:backtests/read") == first_result_read_count

    # If a shard verification becomes ambiguous after the permit, the look is
    # consumed but the manifest/index is not published.  Earlier content-
    # addressed shards may remain as unreachable, recoverable residue.
    failed_events: list[str] = []
    failed_client = _FakeClient(
        failed_events, monkeypatch=monkeypatch
    )
    original_metadata_match = submission._object_metadata_matches
    metadata_calls = 0

    def fail_first_metadata(value, entry):
        nonlocal metadata_calls
        original_metadata_match(value, entry)
        metadata_calls += 1
        if metadata_calls == 1:
            raise submission.FormalQcSubmissionError(
                "offline injected metadata ambiguity"
            )

    with monkeypatch.context() as failure_patch:
        failure_patch.setattr(
            submission, "_object_metadata_matches", fail_first_metadata
        )
        failure_patch.setattr(
            submission,
            "begin_formal_submission_once",
            lambda **_kwargs: _permit(
                bridge.formal_run_candidate,
                reviewed_authority,
                claim,
                failed_events,
            ),
        )
        with pytest.raises(submission.FormalQcSubmissionLocked):
            submission.execute_streamed_formal_qc_submission_once(
                submission_bridge=submission_bridge,
                claim=claim,
                client=failed_client,
                submission_started_at_utc="2026-09-12T12:02:00.000000Z",
            )
    assert failed_events[:2] == ["permit", "request:authenticate"]
    assert len(failed_client._test_backend.objects) == 1
    assert (
        bridge.upload_descriptors[-1].object_store_key
        not in failed_client._test_backend.objects
    )

    corrupt_path = candidate.shards.shard_paths[0]
    corrupt_payload = bytearray(corrupt_path.read_bytes())
    corrupt_payload[-1] ^= 1
    corrupt_path.write_bytes(corrupt_payload)
    os.chmod(corrupt_path, 0o600)
    with pytest.raises(
        FormalStreamingRunRefusal,
        match=FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED.value,
    ):
        next(iter_streamed_formal_qc_upload_entries(bridge))
    prepermit_events: list[str] = []
    monkeypatch.setattr(
        submission,
        "begin_formal_submission_once",
        lambda **_kwargs: prepermit_events.append("permit"),
    )
    with pytest.raises(
        FormalStreamingRunRefusal,
        match=FormalStreamingRefusalReason.PHYSICAL_SHARD_CHANGED.value,
    ):
        submission.execute_streamed_formal_qc_submission_once(
            submission_bridge=submission_bridge,
            claim=claim,
            client=_FakeClient(
                prepermit_events, monkeypatch=monkeypatch
            ),
            submission_started_at_utc="2026-09-12T12:03:00.000000Z",
        )
    assert prepermit_events == []
