"""Focused production-memory and authority tests for physical pre-open upload."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import dis
import types
from pathlib import Path

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import formal_qc_transport as transport
from research.analyst_revisions_v2_qc import historical_preopen_input_adapter as inputs
from research.analyst_revisions_v2_qc import physical_preopen_submission_adapter as upload
from research.analyst_revisions_v2_qc import preopen_control_submission_adapter as submission
from research.analyst_revisions_v2_qc import preopen_control_stage as stage
from research.analyst_revisions_v2_qc.physical_historical_preopen_bridge import (
    build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed,
)
from scripts import build_arv2_historical_preopen_bridge as historical
from tests.analyst_revisions_v2 import (
    test_physical_historical_preopen_bridge as physical_fixture,
)
from tests.analyst_revisions_v2 import (
    test_qc_preopen_control_stage as stage_fixture,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "research" / "analyst_revisions_v2_qc"


def _physical_stream(monkeypatch, tmp_path):
    discovery, _massive, _c1, _sharadar, seed, _legacy = (
        physical_fixture._sources(monkeypatch, tmp_path)
    )
    bridge = (
        build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
            discovery, seed, tmp_path / "physical-preopen-upload-source"
        )
    )
    return inputs.build_authenticated_historical_preopen_input_stream(bridge)


def _projection(stream, tmp_path):
    closed = stream.closed_input_manifest_bytes
    candidate = json.loads(
        stage.render_preopen_control_run_authority_candidate(closed)
    )
    candidate["status"] = (
        "independently_reviewed_private_preopen_construction_authority"
    )
    candidate["target_qc_capacity_reviewed"] = True
    candidate["qc_sid_mapping_reviewed"] = True
    seed = dict(candidate)
    seed["pin_id"] = None
    seed["pin_sha256"] = None
    digest = hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    candidate["pin_id"] = "arv2-preopen-run-authority-" + digest[:24]
    candidate["pin_sha256"] = digest
    path = tmp_path / "physical-upload-run-authority.json"
    path.write_bytes(canonical_json_bytes(candidate))
    path.chmod(0o600)
    authority = stage.load_preopen_control_run_authority(closed, path)
    activated = stage.activate_preopen_input_manifest_bytes(closed, authority)
    projection = stage.build_preopen_control_qc_projection(
        input_manifest_bytes=activated,
        worker_source_bytes=(SOURCE_ROOT / "preopen_control_worker.py").read_bytes(),
        quality_worker_source_bytes=(
            SOURCE_ROOT / "preopen_quality_worker.py"
        ).read_bytes(),
        runtime_source_bytes=(
            SOURCE_ROOT / "preopen_control_runtime.py"
        ).read_bytes(),
        run_authority=authority,
    )
    return activated, authority, projection


def _plan(monkeypatch, tmp_path):
    stream = _physical_stream(monkeypatch, tmp_path)
    activated, authority, projection = _projection(stream, tmp_path)
    plan = upload.build_physical_preopen_upload_plan(
        stream=stream,
        projection=projection,
        input_manifest_bytes=activated,
        run_authority=authority,
        organization_id="physical-preopen-test-organization",
    )
    return stream, plan


class _UploadBackend:
    def __init__(self):
        self.events: list[tuple[str, str | None]] = []
        self.objects: dict[str, bytes] = {}
        self.fail_after_upload_count: int | None = None

    def http(self, url, body, headers, timeout):
        del timeout
        assert "Authorization" in headers
        endpoint = url.split("/api/v2/", 1)[1]
        if endpoint == "object/set":
            boundary = headers["Content-Type"].split("boundary=", 1)[1]
            boundary_bytes = boundary.encode("ascii")
            key = body.split(b'name="key"\r\n\r\n', 1)[1].split(
                b"\r\n--" + boundary_bytes, 1
            )[0].decode("utf-8")
            marker = (
                b'name="objectData"; filename="object.bin"\r\n'
                b"Content-Type: application/octet-stream\r\n\r\n"
            )
            payload = body.split(marker, 1)[1].rsplit(
                b"\r\n--" + boundary_bytes + b"--\r\n", 1
            )[0]
            self.events.append((endpoint, key))
            if (
                self.fail_after_upload_count is not None
                and sum(item[0] == "object/set" for item in self.events)
                > self.fail_after_upload_count
            ):
                raise RuntimeError("ambiguous injected upload failure")
            self.objects[key] = payload
            result = {"success": True}
        else:
            request = json.loads(body)
            if endpoint == "authenticate":
                self.events.append((endpoint, None))
                result = {"success": True}
            elif endpoint == "object/properties":
                key = request["key"]
                payload = self.objects[key]
                self.events.append((endpoint, key))
                result = {
                    "success": True,
                    "metadata": {
                        "key": key,
                        "size": len(payload),
                        "md5": hashlib.md5(
                            payload, usedforsecurity=False
                        ).hexdigest(),
                    },
                }
            else:  # pragma: no cover - the capability should refuse first
                raise AssertionError(endpoint)
        return 200, json.dumps(result, separators=(",", ":")).encode("utf-8")


def _offline_client(backend):
    return transport.FormalQcTransport(
        http_transport=backend.http, clock=lambda: 1_789_000_000
    )


def _offline_call(_closure, client, capability, method, *args, **kwargs):
    return getattr(transport.FormalQcTransport, method)(
        client, capability, *args, **kwargs
    )


def _execution_components():
    public = upload.execute_physical_preopen_input_upload_once
    assert public.__closure__ is not None
    return {
        name: cell.cell_contents
        for name, cell in zip(
        public.__code__.co_freevars, public.__closure__, strict=True
        )
    }


def _offline_execution():
    components = _execution_components()
    implementation = components["implementation"]
    return implementation, {
        "_require_upload_authority_impl": lambda **_values: (
            upload._PINNED_BUILD_HOST_CLOSURE()
        ),
        "_spend_permit_impl": components["spend_permit"],
        "_iter_upload_payloads_impl": components["iter_upload_payloads"],
        "_preopen_call_impl": _offline_call,
        "_metadata_matches_impl": components["metadata_matches"],
        "_mint_receipt_impl": components["mint_receipt"],
    }


def test_stream_is_payload_free_descriptor_exact_reiterable_and_exhausts(
    monkeypatch, tmp_path,
):
    stream = _physical_stream(monkeypatch, tmp_path)
    manifest = json.loads(stream.closed_input_manifest_bytes)
    assert inputs.require_authenticated_historical_preopen_input_stream(stream) is stream
    assert stream.retains_compressed_input_payloads is False
    assert "input_shards" not in {
        field.name for field in dataclasses.fields(stream)
    }
    assert stream.total_compressed_input_byte_count <= 1024 * 1024 * 1024
    assert stream.maximum_shard_compressed_byte_count <= 32 * 1024 * 1024
    assert upload.MAX_INPUT_SHARD_COUNT == historical.MAX_ARCHIVE_SHARD_COUNT == 20_000
    assert upload.MAX_INPUT_SHARD_BYTES == 32 * 1024 * 1024
    assert upload.MAX_TOTAL_INPUT_BYTES == 1024 * 1024 * 1024

    iterator = inputs.iter_authenticated_historical_preopen_input_shards(stream)
    descriptors = []
    for shard in iterator:
        descriptors.append(shard.descriptor())
    assert descriptors == manifest["shards"]
    with pytest.raises(StopIteration):
        next(iterator)
    assert sum(
        1 for _item in inputs.iter_authenticated_historical_preopen_input_shards(
            stream
        )
    ) == stream.input_shard_count


def test_physical_source_iterator_releases_prior_payload_before_next_read():
    instructions = tuple(
        dis.get_instructions(
            historical.iter_reviewed_historical_preopen_input_shards
        )
    )
    assert any(
        item.opname == "DELETE_FAST" and item.argval == "payload"
        for item in instructions
    )


@pytest.mark.parametrize(
    "name",
    (
        "_require_upload_authority",
        "_spend_permit",
        "_iter_upload_payloads",
        "_mint_receipt",
    ),
)
def test_production_upload_action_dependencies_are_closure_only(name):
    assert not hasattr(upload, name)


def test_plan_retains_metadata_only_and_capacity_rebind_refuses_before_iteration(
    monkeypatch, tmp_path,
):
    stream = _physical_stream(monkeypatch, tmp_path)
    activated, authority, projection = _projection(stream, tmp_path)
    plan = upload.build_physical_preopen_upload_plan(
        stream=stream,
        projection=projection,
        input_manifest_bytes=activated,
        run_authority=authority,
        organization_id="physical-preopen-test-organization",
    )
    assert upload.require_physical_preopen_upload_plan(plan) is plan
    assert plan.retains_compressed_input_payloads is False
    assert "input_shards" not in {
        field.name for field in dataclasses.fields(plan)
    }
    assert "payload" not in {
        field.name for field in dataclasses.fields(upload.PhysicalPreopenUploadObject)
    }
    assert plan.upload_object_count == stream.input_shard_count + 1
    assert plan.upload_objects[-1].role == "input_manifest"
    assert [item.object_store_key for item in plan.upload_objects[:-1]] == [
        item["object_store_key"]
        for item in json.loads(stream.closed_input_manifest_bytes)["shards"]
    ]

    with monkeypatch.context() as isolated:
        isolated.setattr(upload, "MAX_INPUT_SHARD_BYTES", 1)
        with pytest.raises(
            upload.PhysicalPreopenSubmissionError,
            match="dependency authority changed",
        ):
            upload.require_physical_preopen_upload_plan(plan)

    callbacks = []

    def hostile(_value):
        callbacks.append(True)
        raise AssertionError("hostile iterator executed")

    with monkeypatch.context() as isolated:
        isolated.setattr(
            inputs,
            "iter_authenticated_historical_preopen_input_shards",
            hostile,
        )
        with pytest.raises(
            upload.PhysicalPreopenSubmissionError,
            match="dependency authority changed",
        ):
            upload.require_physical_preopen_upload_plan(plan)
    assert callbacks == []


def test_upload_streams_in_exact_order_publishes_manifest_last_and_is_one_use(
    monkeypatch, tmp_path,
):
    _stream, plan = _plan(monkeypatch, tmp_path)
    tmp_path.chmod(0o700)
    backend = _UploadBackend()
    client = _offline_client(backend)
    implementation, injected = _offline_execution()
    permit, receipt = implementation(
        plan=plan,
        client=client,
        ledger_directory=tmp_path,
        started_at_utc="2026-09-14T12:00:00.000000Z",
        owner_signature=None,
        _transport_capability_minter=transport._mint_offline_test_capability,
        **injected,
    )
    assert upload.require_physical_preopen_upload_permit(permit, plan) is permit
    assert upload.require_physical_preopen_upload_receipt(receipt) is receipt
    set_keys = [key for endpoint, key in backend.events if endpoint == "object/set"]
    property_keys = [
        key for endpoint, key in backend.events if endpoint == "object/properties"
    ]
    expected_keys = [item.object_store_key for item in plan.upload_objects]
    assert set_keys == property_keys == expected_keys
    assert backend.events == [
        ("authenticate", None),
        *[
            event
            for key in expected_keys
            for event in (("object/set", key), ("object/properties", key))
        ],
    ]
    assert set_keys[-1] == plan.input_manifest_key
    assert backend.objects[plan.input_manifest_key] == plan._input_manifest_bytes
    assert receipt.activated_manifest_published_last is True
    assert receipt.maximum_backtest_submissions == 0
    assert receipt.outcome_result_statistics_log_order_accessed is False
    assert receipt.deployment_order_trading_authorized is False
    assert stat_mode(permit.permit_path) == 0o600

    with pytest.raises(
        upload.PhysicalPreopenSubmissionLocked,
        match="permit already spent",
    ):
        implementation(
            plan=plan,
            client=_offline_client(_UploadBackend()),
            ledger_directory=tmp_path,
            started_at_utc="2026-09-14T12:00:00.000000Z",
            owner_signature=None,
            _transport_capability_minter=transport._mint_offline_test_capability,
            **injected,
        )


def stat_mode(path: Path) -> int:
    return os.stat(path, follow_symlinks=False).st_mode & 0o777


def test_ambiguous_mid_stream_failure_consumes_permit_and_has_no_retry(
    monkeypatch, tmp_path,
):
    _stream, plan = _plan(monkeypatch, tmp_path)
    tmp_path.chmod(0o700)
    backend = _UploadBackend()
    backend.fail_after_upload_count = 1
    implementation, injected = _offline_execution()
    with pytest.raises(
        upload.PhysicalPreopenSubmissionLocked,
        match="one-use upload permit remains consumed",
    ):
        implementation(
            plan=plan,
            client=_offline_client(backend),
            ledger_directory=tmp_path,
            started_at_utc="2026-09-14T12:00:00.000000Z",
            owner_signature=None,
            _transport_capability_minter=transport._mint_offline_test_capability,
            **injected,
        )
    assert (tmp_path / upload.PERMIT_FILENAME).is_file()
    assert sum(endpoint == "object/set" for endpoint, _key in backend.events) == 2
    assert plan.input_manifest_key not in backend.objects


def _completed_physical_upload(monkeypatch, tmp_path):
    upload_root = tmp_path / "physical-upload"
    upload_root.mkdir(mode=0o700)
    _stream, plan = _plan(monkeypatch, upload_root)
    ledger = tmp_path / "physical-upload-ledger"
    ledger.mkdir(mode=0o700)
    backend = _UploadBackend()
    implementation, injected = _offline_execution()
    _permit, receipt = implementation(
        plan=plan,
        client=_offline_client(backend),
        ledger_directory=ledger,
        started_at_utc="2026-09-14T12:00:00.000000Z",
        owner_signature=None,
        _transport_capability_minter=transport._mint_offline_test_capability,
        **injected,
    )
    return receipt, backend


def _physical_qc_plan(monkeypatch, tmp_path):
    receipt, backend = _completed_physical_upload(monkeypatch, tmp_path)
    archive_parent = tmp_path / "physical-output-parent"
    archive_parent.mkdir(mode=0o700)
    plan = upload.build_physical_preopen_qc_submission_plan(
        physical_upload_receipt=receipt,
        output_archive_root=(
            archive_parent / submission.OUTPUT_ARCHIVE_DIRECTORY_NAME
        ),
    )
    return plan, receipt, backend


def test_physical_qc_plan_is_payload_free_exactly_waived_and_signable(
    monkeypatch, tmp_path,
):
    plan, receipt, _backend = _physical_qc_plan(monkeypatch, tmp_path)
    assert upload.require_physical_preopen_qc_submission_plan(plan) is plan
    assert plan.physical_upload_receipt_id == receipt.receipt_id
    assert plan.physical_upload_receipt_sha256 == receipt.receipt_sha256
    assert plan.preuploaded_object_count == receipt.uploaded_object_count
    assert plan.preuploaded_input_shard_count == receipt.uploaded_input_shard_count
    assert plan.preuploaded_byte_count == receipt.uploaded_byte_count
    assert plan.review_disposition == submission.OWNER_REVIEW_WAIVER_DISPOSITION
    assert plan.authorization_basis == submission.OWNER_REVIEW_WAIVER_BASIS
    assert plan.owner_review_waiver_id == submission.OWNER_REVIEW_WAIVER_ID
    assert plan.owner_review_waiver_scope == (
        "SECTION_72_THROUGH_FIRST_FORMAL_BACKTEST"
    )
    assert plan.independent_review_complete is False
    assert plan.post_first_formal_backtest_independent_review_required is True
    assert plan.outcome_result_statistics_log_order_access_authorized is False
    assert plan.deployment_order_trading_authorized is False
    fields = {item.name for item in dataclasses.fields(plan)}
    assert "input_shards" not in fields
    assert "upload_entries" not in fields
    assert "payload" not in fields

    authority = json.loads(
        upload.render_physical_preopen_qc_execution_authority_candidate(plan)
    )
    assert authority["schema"] == submission.PHYSICAL_EXECUTION_AUTHORITY_SCHEMA
    assert authority["review_authorization"] == {
        "review_disposition": submission.OWNER_REVIEW_WAIVER_DISPOSITION,
        "independent_review_complete": False,
        "authorization_basis": submission.OWNER_REVIEW_WAIVER_BASIS,
        "owner_review_waiver_id": submission.OWNER_REVIEW_WAIVER_ID,
        "owner_review_waiver_scope": (
            "SECTION_72_THROUGH_FIRST_FORMAL_BACKTEST"
        ),
        "post_first_formal_backtest_independent_review_required": True,
    }
    assert authority["input_objects_reuploaded"] is False
    assert authority["preuploaded_payloads_retained"] is False
    assert authority["outcome_result_statistics_log_order_access"] is False
    assert authority["deployment_order_trading_authorized"] is False
    assert "object/set" not in authority["actions"]
    assert authority["object_store_key_allowlist"] == [
        item.object_store_key for item in plan._preuploaded_objects
    ]


def test_physical_qc_builder_refuses_forged_receipt_before_plan_mint(
    monkeypatch, tmp_path,
):
    receipt, _backend = _completed_physical_upload(monkeypatch, tmp_path)
    forged = dataclasses.replace(receipt, stream_sha256="0" * 64)
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="^physical pre-open upload receipt is not process-authenticated$",
    ):
        submission.build_preopen_qc_submission_plan_from_physical_upload(
            physical_upload_receipt=forged
        )


def test_physical_qc_plan_type_guard_has_distinct_refusal():
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="^physical pre-open QC submission plan type changed$",
    ):
        submission.require_preopen_qc_physical_submission_plan(object())


def test_physical_qc_host_closure_is_separate_and_each_guard_is_distinct(
    tmp_path,
):
    assert submission.PREOPEN_EXECUTION_ACTIONS == (
        "authenticate",
        "projects/read_exact_name_inventory",
        "projects/create_private_exact_name_once",
        "object/set_exact_input",
        "object/properties_verify_exact_input",
        "files/read_exact_inventory",
        "files/create_exact_projection",
        "compile/create_once",
        "compile/read_state_only_with_bounded_wait",
        "backtests/create_once",
        "backtests/list_identity_status_includeStatistics_false",
        "object/read_exact_named_terminal_package_once",
        (
            "object/read_exact_output_manifest_then_content_addressed_"
            "terminal_shards_once"
        ),
        "write_owner_only_terminal_archive_manifest_last",
        "load_authenticated_physical_preopen_terminal_archive",
    )
    legacy = submission.build_preopen_qc_host_closure_binding()
    physical = submission.build_physical_preopen_qc_host_closure_binding()
    assert tuple(item.path for item in legacy.sources) == (
        submission.PREOPEN_REQUIRED_HOST_CODE_PATHS
    )
    assert tuple(item.path for item in physical.sources) == (
        submission.PHYSICAL_PREOPEN_REQUIRED_HOST_CODE_PATHS
    )
    assert physical.sources[: len(legacy.sources)] == legacy.sources
    submission.verify_preopen_qc_host_closure_live(legacy)
    submission.verify_physical_preopen_qc_host_closure_live(physical)

    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="^physical pre-open host source closure changed$",
    ):
        submission.verify_physical_preopen_qc_host_closure_live(legacy)
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="^live physical pre-open host source closure changed$",
    ):
        submission.verify_physical_preopen_qc_host_closure_live(
            dataclasses.replace(physical, closure_sha256="0" * 64)
        )
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="^physical pre-open host source closure is unavailable$",
    ):
        submission._read_physical_preopen_host_sources(
            _sealed_root=tmp_path,
            _sealed_paths=("missing.py",),
        )
    (tmp_path / "bad.py").write_bytes(b"not-canonical")
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="^physical pre-open host source is not canonical LF: bad.py$",
    ):
        submission._read_physical_preopen_host_sources(
            _sealed_root=tmp_path,
            _sealed_paths=("bad.py",),
        )


@pytest.mark.parametrize(
    "dependency_name",
    (
        "build_preopen_qc_submission_plan_from_physical_upload",
        "require_preopen_qc_physical_submission_plan",
        "render_preopen_qc_execution_authority_candidate",
        "execute_preopen_qc_submission_once",
    ),
)
def test_each_physical_qc_facade_dependency_rebind_refuses_before_callback(
    monkeypatch, tmp_path, dependency_name,
):
    plan, _receipt, _backend = _physical_qc_plan(monkeypatch, tmp_path)
    callbacks = []

    def hostile(*_args, **_kwargs):
        callbacks.append(True)
        raise AssertionError("hostile physical QC dependency executed")

    monkeypatch.setattr(submission, dependency_name, hostile)
    with pytest.raises(
        upload.PhysicalPreopenSubmissionError,
        match="^physical pre-open upload dependency authority changed$",
    ):
        upload.require_physical_preopen_qc_submission_plan(plan)
    assert callbacks == []


@pytest.mark.parametrize(
    "dependency_name",
    (
        "OWNER_REVIEW_WAIVER_ID",
        "OWNER_REVIEW_WAIVER_SCOPE",
        "OWNER_REVIEW_WAIVER_BASIS",
        "OWNER_REVIEW_WAIVER_DISPOSITION",
        "PHYSICAL_INPUT_UPLOAD_DISPOSITION",
    ),
)
def test_each_physical_qc_waiver_constant_rebind_refuses(
    monkeypatch, dependency_name,
):
    monkeypatch.setattr(submission, dependency_name, object())
    with pytest.raises(
        upload.PhysicalPreopenSubmissionError,
        match="^physical pre-open upload dependency authority changed$",
    ):
        upload._require_dependencies()


@pytest.mark.parametrize(
    ("mutation", "message", "skip_projection"),
    (
        (
            lambda receipt: dataclasses.replace(
                receipt,
                uploaded_object_count=receipt.uploaded_object_count + 1,
            ),
            "physical pre-open upload receipt census or gates changed",
            False,
        ),
        (
            lambda receipt: dataclasses.replace(
                receipt,
                _plan=dataclasses.replace(
                    receipt._plan,
                    upload_objects=(
                        dataclasses.replace(
                            receipt._plan.upload_objects[0], role="wrong_role"
                        ),
                        *receipt._plan.upload_objects[1:],
                    ),
                ),
            ),
            "physical pre-open preuploaded shard 0 lineage changed",
            False,
        ),
        (
            lambda receipt: dataclasses.replace(
                receipt,
                _plan=dataclasses.replace(
                    receipt._plan,
                    upload_objects=(
                        *receipt._plan.upload_objects[:-1],
                        dataclasses.replace(
                            receipt._plan.upload_objects[-1], role="wrong_manifest"
                        ),
                    ),
                ),
            ),
            "physical pre-open preuploaded manifest lineage changed",
            False,
        ),
        (
            lambda receipt: dataclasses.replace(
                receipt,
                _plan=dataclasses.replace(
                    receipt._plan, _input_manifest_bytes=b"{"
                ),
            ),
            "physical pre-open activated input manifest is not JSON",
            True,
        ),
    ),
)
def test_physical_qc_builder_each_lineage_guard_has_distinct_refusal(
    monkeypatch, tmp_path, mutation, message, skip_projection,
):
    receipt, _backend = _completed_physical_upload(monkeypatch, tmp_path)
    forged = mutation(receipt)
    with monkeypatch.context() as isolated:
        isolated.setattr(
            upload, "require_physical_preopen_upload_receipt", lambda value: value
        )
        if skip_projection:
            isolated.setattr(
                submission, "_rebuild_projection", lambda *_args: None
            )
        with pytest.raises(
            submission.PreopenQcSubmissionError,
            match="^" + message + "$",
        ):
            submission.build_preopen_qc_submission_plan_from_physical_upload(
                physical_upload_receipt=forged
            )


def test_physical_qc_builder_refuses_changed_manifest_census_distinctly(
    monkeypatch, tmp_path,
):
    receipt, _backend = _completed_physical_upload(monkeypatch, tmp_path)
    manifest = json.loads(receipt._plan._input_manifest_bytes)
    manifest["resource_census"]["projected_output_shard_count"] = True
    forged = dataclasses.replace(
        receipt,
        _plan=dataclasses.replace(
            receipt._plan,
            _input_manifest_bytes=canonical_json_bytes(manifest),
        ),
    )
    with monkeypatch.context() as isolated:
        isolated.setattr(
            upload, "require_physical_preopen_upload_receipt", lambda value: value
        )
        isolated.setattr(submission, "_rebuild_projection", lambda *_args: None)
        with pytest.raises(
            submission.PreopenQcSubmissionError,
            match=(
                "^physical pre-open activated manifest or output census changed$"
            ),
        ):
            submission.build_preopen_qc_submission_plan_from_physical_upload(
                physical_upload_receipt=forged
            )


def test_physical_qc_output_archive_path_guards_are_distinct(
    monkeypatch, tmp_path,
):
    receipt, _backend = _completed_physical_upload(monkeypatch, tmp_path)
    bad_parent = tmp_path / "not-private"
    bad_parent.mkdir(mode=0o755)
    bad_parent.chmod(0o755)
    missing_parent = tmp_path / "missing-parent"
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir(mode=0o700)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    cases = (
        (
            tmp_path / "wrong-name",
            "physical pre-open output archive must be the exact absolute archive child",
        ),
        (
            linked_parent / submission.OUTPUT_ARCHIVE_DIRECTORY_NAME,
            "physical pre-open output archive parent is not canonical",
        ),
        (
            missing_parent / submission.OUTPUT_ARCHIVE_DIRECTORY_NAME,
            "physical pre-open output archive parent is unavailable",
        ),
        (
            bad_parent / submission.OUTPUT_ARCHIVE_DIRECTORY_NAME,
            "physical pre-open output archive parent or leaf is not owner-only",
        ),
    )
    for path, message in cases:
        with pytest.raises(
            submission.PreopenQcSubmissionError,
            match="^" + message + "$",
        ):
            submission.build_preopen_qc_submission_plan_from_physical_upload(
                physical_upload_receipt=receipt,
                output_archive_root=path,
            )


def test_physical_qc_plan_tamper_cross_source_and_fork_refuse(
    monkeypatch, tmp_path,
):
    plan, _receipt, _backend = _physical_qc_plan(monkeypatch, tmp_path)
    original_sources = plan.source_files
    object.__setattr__(plan, "source_files", [])
    try:
        with pytest.raises(
            submission.PreopenQcSubmissionError,
            match=(
                "^physical pre-open QC submission plan container types changed$"
            ),
        ):
            submission.require_preopen_qc_physical_submission_plan(plan)
    finally:
        object.__setattr__(plan, "source_files", original_sources)
    assert submission.require_preopen_qc_physical_submission_plan(plan) is plan

    original_plan_id = plan.plan_id
    object.__setattr__(plan, "plan_id", object())
    try:
        with pytest.raises(
            submission.PreopenQcSubmissionError,
            match=(
                "^physical pre-open QC submission plan scalar types changed$"
            ),
        ):
            submission.require_preopen_qc_physical_submission_plan(plan)
    finally:
        object.__setattr__(plan, "plan_id", original_plan_id)
    assert submission.require_preopen_qc_physical_submission_plan(plan) is plan

    original = plan.independent_review_complete
    object.__setattr__(plan, "independent_review_complete", True)
    try:
        with pytest.raises(
            submission.PreopenQcSubmissionError,
            match="^physical pre-open QC submission plan changed$",
        ):
            submission.require_preopen_qc_physical_submission_plan(plan)
    finally:
        object.__setattr__(plan, "independent_review_complete", original)
    assert submission.require_preopen_qc_physical_submission_plan(plan) is plan

    original_requirer = plan._physical_receipt_requirer
    broken_upload_plan = dataclasses.replace(
        plan._physical_upload_receipt._plan,
        _input_manifest_bytes=b"{",
    )

    def authenticated_but_broken_lineage(_receipt):
        return types.SimpleNamespace(_plan=broken_upload_plan)

    object.__setattr__(
        plan,
        "_physical_receipt_requirer",
        authenticated_but_broken_lineage,
    )
    registered = submission._PHYSICAL_PLAN_AUTHORITIES[id(plan)]
    submission._PHYSICAL_PLAN_AUTHORITIES[id(plan)] = (
        registered[0],
        submission._physical_plan_fingerprint(plan),
        registered[2],
    )
    try:
        with pytest.raises(
            submission.PreopenQcSubmissionError,
            match=(
                "^physical pre-open upload lineage changed after "
                "plan construction$"
            ),
        ):
            submission.require_preopen_qc_physical_submission_plan(plan)
    finally:
        object.__setattr__(
            plan,
            "_physical_receipt_requirer",
            original_requirer,
        )
        submission._PHYSICAL_PLAN_AUTHORITIES[id(plan)] = (
            registered[0],
            submission._physical_plan_fingerprint(plan),
            registered[2],
        )
    assert submission.require_preopen_qc_physical_submission_plan(plan) is plan

    forged = dataclasses.replace(plan)
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="^physical pre-open QC submission plan lacks process authority$",
    ):
        submission.require_preopen_qc_physical_submission_plan(forged)

    second_root = tmp_path / "cross-source"
    second_root.mkdir(mode=0o700)
    other_receipt, _other_backend = _completed_physical_upload(
        monkeypatch, second_root
    )
    original_receipt = plan._physical_upload_receipt
    object.__setattr__(plan, "_physical_upload_receipt", other_receipt)
    try:
        with pytest.raises(
            submission.PreopenQcSubmissionError,
            match="^physical pre-open QC submission plan changed$",
        ):
            submission.require_preopen_qc_physical_submission_plan(plan)
    finally:
        object.__setattr__(
            plan, "_physical_upload_receipt", original_receipt
        )
    assert submission.require_preopen_qc_physical_submission_plan(plan) is plan

    original_stream_sha256 = original_receipt.stream_sha256
    object.__setattr__(original_receipt, "stream_sha256", "0" * 64)
    try:
        with pytest.raises(
            submission.PreopenQcSubmissionError,
            match=(
                "^physical pre-open upload receipt changed after plan construction$"
            ),
        ):
            submission.require_preopen_qc_physical_submission_plan(plan)
    finally:
        object.__setattr__(
            original_receipt, "stream_sha256", original_stream_sha256
        )
    assert submission.require_preopen_qc_physical_submission_plan(plan) is plan

    if not hasattr(os, "fork"):
        return
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - asserted through the pipe
        os.close(read_fd)
        try:
            submission.require_preopen_qc_physical_submission_plan(plan)
        except Exception as exc:
            os.write(write_fd, str(exc).encode("utf-8"))
        else:
            os.write(write_fd, b"NO_REFUSAL")
        finally:
            os.close(write_fd)
            os._exit(0)
    os.close(write_fd)
    observed = os.read(read_fd, 4096).decode("utf-8")
    os.close(read_fd)
    _pid, status = os.waitpid(child, 0)
    assert status == 0
    assert observed == "physical pre-open QC submission plan lacks process authority"
    assert submission.require_preopen_qc_physical_submission_plan(plan) is plan


class _PhysicalQcBackend:
    def __init__(self, plan, objects, ledger_directory):
        self.plan = plan
        self.objects = dict(objects)
        self.ledger_directory = ledger_directory
        self.files = {submission.QC_DEFAULT_RESEARCH_NOTEBOOK_PATH: "{}"}
        self.events: list[str] = []
        self.created = False
        self.already_exists = False
        self.ambiguous_created_project = False
        self.wrong_created_project_id = False
        self.inject_unprojected_source = False
        self.corrupt_source_read = False
        self.compile_state = "BuildSuccess"
        self.compile_pending_forever = False

    def _project(self):
        return {
            "projectId": 731,
            "organizationId": self.plan.organization_id,
            "name": self.plan.project_name,
            "language": "Py",
            "owner": True,
            "codeRunning": False,
            "collaborators": [{"owner": True}],
            "libraries": [],
        }

    def request(self, endpoint, request):
        self.events.append(endpoint)
        assert (self.ledger_directory / submission.PERMIT_FILENAME).exists()
        if endpoint == "authenticate":
            return {"success": True}
        if endpoint == "projects/read":
            if not request:
                projects = [self._project()] if self.already_exists else []
            elif self.created:
                projects = [self._project()]
                if self.wrong_created_project_id:
                    projects[0]["projectId"] += 1
                if self.ambiguous_created_project:
                    projects.append(dict(self._project()))
            else:
                projects = []
            return {"success": True, "projects": projects}
        if endpoint == "projects/create":
            self.created = True
            return {"success": True, "projects": [self._project()]}
        if endpoint == "files/read":
            observed = dict(self.files)
            if self.corrupt_source_read and self.created:
                source = self.plan.source_files[0].project_path
                if source in observed:
                    observed[source] += "#changed\n"
            return {
                "success": True,
                "files": [
                    {"name": name, "content": content}
                    for name, content in sorted(observed.items())
                ],
            }
        if endpoint == "files/delete":
            del self.files[request["name"]]
            return {"success": True}
        if endpoint == "files/create":
            self.files[request["name"]] = request["content"]
            if (
                self.inject_unprojected_source
                and request["name"] == self.plan.source_files[-1].project_path
            ):
                self.files["unprojected.py"] = "pass\n"
            return {"success": True}
        if endpoint == "compile/create":
            return {
                "success": True,
                "compileId": "physical-preopen-compile",
                "state": "InQueue",
                "parameters": [],
                "projectId": 731,
                "signature": "physical-fixture-signature",
                "signatureOrder": [],
            }
        if endpoint == "compile/read":
            return {
                "success": True,
                "compileId": "physical-preopen-compile",
                "state": (
                    "InQueue"
                    if self.compile_pending_forever
                    else self.compile_state
                ),
                "logs": ["discard-only physical compile fixture"],
            }
        if endpoint == "backtests/create":
            return {
                "success": True,
                "backtest": {
                    "backtestId": "physical-preopen-backtest",
                    "name": request["backtestName"],
                    "projectId": 731,
                    "status": "In Queue...",
                },
            }
        raise AssertionError(endpoint)

    def http(self, url, body, headers, timeout):
        del timeout
        assert "Authorization" in headers
        endpoint = url.split("/api/v2/", 1)[1]
        if endpoint == "object/set":
            self.events.append(endpoint)
            raise AssertionError("physical continuation must not re-upload inputs")
        request = json.loads(body)
        if endpoint == "object/properties":
            key = request["key"]
            payload = self.objects[key]
            self.events.append(endpoint)
            response = {
                "success": True,
                "metadata": {
                    "key": key,
                    "size": len(payload),
                    "md5": hashlib.md5(
                        payload, usedforsecurity=False
                    ).hexdigest(),
                },
            }
        else:
            response = self.request(endpoint, request)
        return 200, json.dumps(response, separators=(",", ":")).encode("utf-8")


def _offline_physical_qc_action():
    original = submission.execute_preopen_qc_submission_once
    implementation = stage_fixture._closure_value(original, "execute_impl")
    preuploaded = stage_fixture._closure_value(
        original, "execute_preuploaded_impl"
    )
    preuploaded = stage_fixture._with_global_values(
        preuploaded,
        _preopen_transport_call=_offline_call,
        _wait=lambda _seconds: None,
    )
    formal_gate = types.SimpleNamespace(
        _require_concrete_transport=lambda value: value
    )
    implementation = stage_fixture._with_global_values(
        implementation,
        _require_external_execution_trust_root=lambda *_args, **_kwargs: None,
        formal=formal_gate,
        _register_launch_process_return=lambda value: value,
    )

    transport_module = transport

    def offline_minter(*, transport: object, scope: str,
                       binding_record: object, call_budget: object):
        return transport_module._mint_offline_test_capability(
            transport,
            scope=scope,
            binding_record=binding_record,
            call_budget=call_budget,
        )

    action = stage_fixture._with_closure_value(
        original, "execute_impl", implementation
    )
    action = stage_fixture._with_closure_value(
        action, "execute_preuploaded_impl", preuploaded
    )
    for name, value in (
        ("execute_preuploaded_code", preuploaded.__code__),
        ("execute_preuploaded_globals", preuploaded.__globals__),
        ("execute_preuploaded_defaults", preuploaded.__defaults__),
        ("execute_preuploaded_kwdefaults", preuploaded.__kwdefaults__),
    ):
        action = stage_fixture._with_closure_value(action, name, value)
    action = stage_fixture._with_closure_value(
        action, "minter", offline_minter
    )
    return stage_fixture._with_closure_value(
        action, "binding_guard", lambda _operation: None
    )


def _physical_qc_context(monkeypatch, tmp_path, configure=None):
    plan, _receipt, uploaded = _physical_qc_plan(monkeypatch, tmp_path)
    ledger = tmp_path / "physical-qc-ledger"
    ledger.mkdir(mode=0o700)
    backend = _PhysicalQcBackend(plan, uploaded.objects, ledger)
    if configure is not None:
        configure(backend)
    return plan, ledger, backend, _offline_physical_qc_action()


def _execute_physical_qc_context(plan, ledger, backend, action):
    return action(
        plan=plan,
        client=_offline_client(backend),
        ledger_directory=ledger,
        started_at_utc="2026-09-14T13:00:00.000000Z",
        owner_signature=None,
    )


def test_physical_qc_execution_reuses_objects_deletes_only_default_and_launches(
    monkeypatch, tmp_path,
):
    plan, ledger, backend, action = _physical_qc_context(
        monkeypatch, tmp_path
    )
    permit, launch = _execute_physical_qc_context(
        plan, ledger, backend, action
    )
    assert submission.require_preopen_qc_submission_permit(permit, plan) is permit
    assert launch.uploaded_object_count == 0
    assert launch.uploaded_source_count == len(plan.source_files)
    assert launch.submission_count == 1
    assert backend.events.count("object/properties") == (
        plan.preuploaded_object_count
    )
    assert "object/set" not in backend.events
    assert backend.events.count("files/delete") == 1
    assert set(backend.files) == {
        item.project_path for item in plan.source_files
    }
    assert backend.events[-1] == "backtests/create"


def test_physical_qc_owner_signature_precedes_permit_and_transport(
    monkeypatch, tmp_path,
):
    plan, ledger, backend, _action = _physical_qc_context(
        monkeypatch, tmp_path
    )
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match=(
            "^non-self-mintable owner/reviewer pre-open execution trust root "
            "is unavailable$"
        ),
    ):
        upload.execute_physical_preopen_qc_submission_once(
            plan=plan,
            client=_offline_client(backend),
            ledger_directory=ledger,
            started_at_utc="2026-09-14T13:00:00.000000Z",
            owner_signature=None,
        )
    assert not (ledger / submission.PERMIT_FILENAME).exists()
    assert backend.events == []


@pytest.mark.parametrize(
    ("configure", "message", "forbidden_endpoint"),
    (
        (
            lambda backend: backend.objects.__setitem__(
                backend.plan._preuploaded_objects[0].object_store_key,
                b"changed",
            ),
            "physical pre-open preuploaded object 0 metadata changed",
            "projects/create",
        ),
        (
            lambda backend: setattr(backend, "already_exists", True),
            "exact physical pre-open project already exists",
            "projects/create",
        ),
        (
            lambda backend: setattr(
                backend, "ambiguous_created_project", True
            ),
            "created physical pre-open project identity is ambiguous",
            "files/read",
        ),
        (
            lambda backend: setattr(
                backend, "wrong_created_project_id", True
            ),
            "created physical pre-open project identifier changed",
            "files/read",
        ),
        (
            lambda backend: backend.files.__setitem__(
                "unexpected.py", "pass\n"
            ),
            "new physical pre-open project contains an unprojected source",
            "files/delete",
        ),
        (
            lambda backend: setattr(
                backend, "inject_unprojected_source", True
            ),
            "physical pre-open project source inventory changed",
            "compile/create",
        ),
        (
            lambda backend: setattr(backend, "corrupt_source_read", True),
            "physical pre-open project source bytes changed",
            "compile/create",
        ),
        (
            lambda backend: setattr(
                backend, "compile_pending_forever", True
            ),
            "physical pre-open compile polling exhausted",
            "backtests/create",
        ),
        (
            lambda backend: setattr(backend, "compile_state", "BuildError"),
            "physical pre-open project did not compile",
            "backtests/create",
        ),
    ),
)
def test_each_physical_qc_execution_guard_is_named_and_consumes_once(
    monkeypatch, tmp_path, configure, message, forbidden_endpoint,
):
    plan, ledger, backend, action = _physical_qc_context(
        monkeypatch, tmp_path, configure
    )
    with pytest.raises(
        submission.PreopenQcSubmissionLocked,
        match=message + "; one-use pre-open permit remains consumed$",
    ):
        _execute_physical_qc_context(plan, ledger, backend, action)
    assert (ledger / submission.PERMIT_FILENAME).is_file()
    assert forbidden_endpoint not in backend.events
    assert "object/set" not in backend.events


def test_missing_physical_execution_dependency_refuses_before_permit(
    monkeypatch, tmp_path,
):
    plan, _receipt, uploaded = _physical_qc_plan(monkeypatch, tmp_path)
    ledger = tmp_path / "missing-helper-ledger"
    ledger.mkdir(mode=0o700)
    backend = _PhysicalQcBackend(plan, uploaded.objects, ledger)
    production_action = submission.execute_preopen_qc_submission_once
    production_helper = stage_fixture._closure_value(
        production_action, "execute_preuploaded_impl"
    )
    production_code = production_helper.__code__
    production_helper.__code__ = (lambda: None).__code__
    try:
        with pytest.raises(
            submission.PreopenQcSubmissionError,
            match="^physical pre-open execution dependency changed$",
        ):
            production_action(
                plan=plan,
                client=_offline_client(backend),
                ledger_directory=ledger,
                started_at_utc="2026-09-14T13:00:00.000000Z",
                owner_signature=None,
            )
    finally:
        production_helper.__code__ = production_code
    assert not (ledger / submission.PERMIT_FILENAME).exists()
    assert backend.events == []

    action = _offline_physical_qc_action()
    direct_implementation = stage_fixture._closure_value(
        action, "execute_impl"
    )
    changed_action = stage_fixture._with_closure_value(
        action,
        "execute_preuploaded_impl",
        None,
    )
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="^physical pre-open execution dependency changed$",
    ):
        changed_action(
            plan=plan,
            client=_offline_client(backend),
            ledger_directory=ledger,
            started_at_utc="2026-09-14T13:00:00.000000Z",
            owner_signature=None,
        )
    assert not (ledger / submission.PERMIT_FILENAME).exists()
    assert backend.events == []

    direct_ledger = tmp_path / "missing-direct-helper-ledger"
    direct_ledger.mkdir(mode=0o700)
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="^physical pre-open execution authority is unavailable$",
    ):
        direct_implementation(
            plan=plan,
            client=_offline_client(backend),
            ledger_directory=direct_ledger,
            started_at_utc="2026-09-14T13:00:00.000000Z",
            owner_signature=None,
            _transport_capability_minter=lambda **_values: None,
            _execute_preuploaded_impl=None,
        )
    assert not (direct_ledger / submission.PERMIT_FILENAME).exists()
    assert backend.events == []
