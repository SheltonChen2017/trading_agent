"""Focused dangerous-direction tests for the pre-review output capture."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import io
import inspect
import json
import os
import stat
import types
import zipfile

import pytest

from research.analyst_revisions_v2_qc import (
    preopen_control_acquisition_io as acquisition_io,
)
from research.analyst_revisions_v2_qc import (
    preopen_control_prereview_downloader as prereview,
)
from research.analyst_revisions_v2_qc import (
    preopen_control_submission_adapter as submission,
)
from research.analyst_revisions_v2_qc import formal_qc_transport as transport_module
from research.analyst_revisions_v2.preopen_control_acquisition import (
    acquisition_output_shard_descriptor_records,
)
from tests.analyst_revisions_v2.test_qc_preopen_control_output_archive import (
    _executed_output_context,
    _output_package_bytes,
)
from tests.analyst_revisions_v2.test_qc_preopen_control_stage import (
    _offline_owner_signature,
    _offline_signed_acquisition_loader,
    _reviewed_receipt,
    _with_global_values,
)
from tests.analyst_revisions_v2.test_qc_physical_preopen_submission_adapter import (
    _physical_qc_plan,
)


def _implementation():
    action = prereview.download_preopen_control_outputs_for_review
    return next(
        cell.cell_contents
        for name, cell in zip(
            action.__code__.co_freevars,
            action.__closure__ or (),
            strict=True,
        )
        if name == "implementation"
    )


def _offline_minter(*, transport: object, scope: str, binding_record, call_budget):
    return transport_module._mint_offline_test_capability(
        transport,
        scope=scope,
        binding_record=binding_record,
        call_budget=call_budget,
    )


def _capture(monkeypatch, tmp_path, *, corrupt_shard=False):
    context = _executed_output_context(
        monkeypatch, tmp_path, corrupt_shard=corrupt_shard
    )
    monkeypatch.setattr(
        prereview,
        "_require_download_authority",
        lambda **values: values["package"],
    )
    value = _implementation()(
        plan=context["plan"],
        permit=context["permit"],
        launch=context["launch"],
        terminal=context["terminal"],
        package=context["package"],
        client=context["client"],
        owner_signature=None,
        _transport_capability_minter=_offline_minter,
    )
    return context, value


def _physical_capture(monkeypatch, tmp_path):
    physical_plan, _receipt, _upload_backend = _physical_qc_plan(
        monkeypatch, tmp_path
    )
    review_root = tmp_path / "physical-prereview-material"
    review_root.mkdir(mode=0o700)
    receipt, material = _reviewed_receipt(review_root, monkeypatch)
    package_bytes = _output_package_bytes(physical_plan, receipt)
    descriptor = acquisition_output_shard_descriptor_records(receipt)[0]
    manifest_key = (
        "arv2/preopen/output/manifests/"
        + receipt.content_sha256
        + ".json"
    )
    objects = {
        manifest_key: material["output"],
        descriptor["object_store_key"]: material["payload"],
    }
    object_reads = []

    def offline_call(_client, _capability, method, _organization_id, key):
        assert method == "_read_object_bounded"
        object_reads.append(key)
        return {
            "success": True,
            "object": {
                "key": key,
                "objectData": base64.b64encode(objects[key]).decode("ascii"),
            },
        }

    permit = types.SimpleNamespace(
        permit_id="arv2-physical-prereview-permit",
        permit_sha256="1" * 64,
    )
    launch = types.SimpleNamespace(
        receipt_sha256="2" * 64,
        project_id=731,
        compile_id="physical-prereview-compile",
        backtest_id="physical-prereview-backtest",
    )
    terminal = types.SimpleNamespace(
        receipt_sha256="3" * 64,
        terminal_status="Completed.",
    )
    package = types.SimpleNamespace(
        receipt_sha256="4" * 64,
        package_key=physical_plan.terminal_package_key,
        package_sha256=hashlib.sha256(package_bytes).hexdigest(),
        package_byte_count=len(package_bytes),
        output_manifest_key=manifest_key,
        output_manifest_sha256=receipt.content_sha256,
        output_manifest_byte_count=receipt.byte_count,
        output_shard_inventory_sha256=receipt.output_shard_inventory_sha256,
        universe_terminal_projection_sha256=(
            receipt.universe_terminal_projection_sha256
        ),
        control_terminal_projection_sha256=(
            receipt.control_terminal_projection_sha256
        ),
        q_data_measurement_projection_sha256=(
            receipt.q_data_measurement_projection_sha256
        ),
        terminal_count=receipt.control_terminal_count,
        accepted_count=receipt.control_accepted_count,
        refusal_count=receipt.control_refusal_count,
        package_bytes=package_bytes,
    )
    client = transport_module.FormalQcTransport(
        http_transport=lambda *_args: (_ for _ in ()).throw(
            AssertionError("offline transport callback executed")
        ),
        clock=lambda: 1_789_000_000,
    )
    implementation = _with_global_values(
        _implementation(),
        _require_download_authority=lambda **values: values["package"],
        _PINNED_TRANSPORT_CALL=offline_call,
    )
    value = implementation(
        plan=physical_plan,
        permit=permit,
        launch=launch,
        terminal=terminal,
        package=package,
        client=client,
        owner_signature=None,
        _transport_capability_minter=_offline_minter,
    )
    context = {
        "material": material,
        "descriptor": descriptor,
        "object_reads": object_reads,
        "permit": permit,
        "launch": launch,
        "terminal": terminal,
        "package": package,
    }
    return physical_plan, context, value


def _rewrite_capture_index(root, mutate):
    path = root / prereview.CAPTURE_INDEX_NAME
    value = json.loads(path.read_bytes())
    mutate(value)
    seed = dict(value)
    seed["capture_id"] = None
    seed["capture_sha256"] = None
    digest = hashlib.sha256(prereview.canonical_json_bytes(seed)).hexdigest()
    value["capture_id"] = "arv2-preopen-prereview-capture-" + digest[:24]
    value["capture_sha256"] = digest
    path.write_bytes(prereview.canonical_json_bytes(value))


def test_prereview_output_descriptor_key_uses_qc_portable_suffix():
    digest = "a" * 64
    expected = (
        "arv2/preopen/output/content/control_terminals/"
        "chunk-0002/security-batch-0003/"
        f"{digest}-jsonl.gz"
    )
    descriptor = {
        "decision_chunk_ordinal": 2,
        "security_batch_ordinal": 3,
        "compressed_sha256": digest,
        "object_store_key": expected,
    }

    assert prereview._output_descriptor_key(descriptor) == expected

    descriptor["object_store_key"] = expected.replace("-jsonl.gz", ".jsonl.gz")
    with pytest.raises(
        prereview.PreopenControlPreReviewError,
        match="pre-open output shard key is not content-derived",
    ):
        prereview._output_descriptor_key(descriptor)


def test_prereview_download_closes_acquisition_circle_with_only_exact_objects(
    monkeypatch, tmp_path
):
    context, value = _capture(monkeypatch, tmp_path)
    assert prereview.require_preopen_control_prereview_archive(value) is value
    assert value.endpoint_allowlist == ("object/read",)
    assert value.object_store_key_allowlist == (
        context["package"].output_manifest_key,
        context["descriptor"]["object_store_key"],
    )
    assert context["object_reads"] == [
        context["plan"].terminal_package_key,
        *value.object_store_key_allowlist,
    ]
    assert context["events"].count("object/read") == 3
    assert not {
        "backtests/read", "logs/read", "orders/read", "projects/delete"
    }.intersection(context["events"])
    assert value.independent_review_performed is False
    assert value.acquisition_receipt_minted is False
    assert value.outcome_result_statistics_log_order_accessed is False
    assert value.deployment_order_trading_authorized is False
    assert (
        "preopen_acquisition_receipt"
        not in inspect.signature(
            prereview.download_preopen_control_outputs_for_review
        ).parameters
    )


def test_prereview_capture_is_private_reloadable_and_feeds_existing_review_loader(
    monkeypatch, tmp_path
):
    context, value = _capture(monkeypatch, tmp_path)
    root = value.archive_root
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in root.rglob("*")
        if path.is_file()
    )
    reloaded = prereview.load_preopen_control_prereview_archive(root)
    manifest = prereview.read_preopen_control_prereview_manifest_bytes(reloaded)
    payloads = tuple(
        prereview.iter_preopen_control_prereview_output_shard_payloads(reloaded)
    )
    execution, summary = (
        prereview.read_preopen_control_prereview_supporting_receipts(reloaded)
    )
    assert manifest == context["material"]["output"]
    assert payloads == (context["material"]["payload"],)
    pin_bytes = acquisition_io.render_preopen_control_external_review_pin_candidate(
        output_manifest_bytes=manifest,
        output_shard_payloads=iter(payloads),
        independent_review_receipt_bytes=context["material"]["review"],
        qc_execution_receipt_bytes=execution,
        summary_receipt_bytes=summary,
    )
    pin_path = tmp_path / "review-pin.json"
    pin_path.write_bytes(pin_bytes)
    pin_path.chmod(0o600)
    receipt = _offline_signed_acquisition_loader()(
        output_manifest_bytes=manifest,
        output_shard_payloads=iter(payloads),
        independent_review_receipt_bytes=context["material"]["review"],
        qc_execution_receipt_bytes=execution,
        summary_receipt_bytes=summary,
        external_review_pin_path=pin_path,
        owner_signature=_offline_owner_signature(),
    )
    assert receipt.artifact_sha256 == hashlib.sha256(manifest).hexdigest()
    assert receipt.control_terminal_count == value.terminal_count


def test_prereview_dependency_rebind_refuses_before_callback_archive_or_read(
    monkeypatch, tmp_path
):
    context = _executed_output_context(monkeypatch, tmp_path)
    callbacks = []
    read_count = len(context["object_reads"])

    def hostile(_payload):
        callbacks.append(_payload)
        raise AssertionError("hostile output parser executed")

    monkeypatch.setattr(prereview.core, "_validate_manifest", hostile)
    with pytest.raises(
        prereview.PreopenControlPreReviewError,
        match="dependency authority changed",
    ):
        prereview.download_preopen_control_outputs_for_review(
            plan=context["plan"],
            permit=context["permit"],
            launch=context["launch"],
            terminal=context["terminal"],
            package=context["package"],
            client=context["client"],
            owner_signature=None,
        )
    assert callbacks == []
    assert len(context["object_reads"]) == read_count
    assert not context["archive_root"].exists()


def test_prereview_canonicalizer_rebind_refuses_before_filesystem_callback(
    monkeypatch,
):
    callbacks = []

    def hostile(_value):
        callbacks.append(True)
        raise AssertionError("hostile canonicalizer executed")

    monkeypatch.setattr(prereview, "canonical_json_bytes", hostile)
    with pytest.raises(
        prereview.PreopenControlPreReviewError,
        match="dependency authority changed",
    ):
        prereview.load_preopen_control_prereview_archive(
            prereview.Path("/private/tmp/not-read")
        )
    assert callbacks == []


@pytest.mark.parametrize(
    "name",
    (
        "OWNER_REVIEW_WAIVER_ID",
        "OWNER_REVIEW_WAIVER_SCOPE",
        "OWNER_REVIEW_WAIVER_BASIS",
        "OWNER_REVIEW_WAIVER_DISPOSITION",
        "PHYSICAL_INPUT_UPLOAD_DISPOSITION",
    ),
)
def test_prereview_waiver_constant_rebind_refuses_before_filesystem(
    monkeypatch, name,
):
    monkeypatch.setattr(submission, name, object())
    with pytest.raises(
        prereview.PreopenControlPreReviewError,
        match="^pre-open prereview dependency authority changed$",
    ):
        prereview.load_preopen_control_prereview_archive(
            prereview.Path("/private/tmp/not-read")
        )


def test_prereview_wrong_object_envelope_locks_and_never_publishes_index(
    monkeypatch, tmp_path
):
    context = _executed_output_context(monkeypatch, tmp_path)
    monkeypatch.setattr(
        prereview,
        "_require_download_authority",
        lambda **values: values["package"],
    )
    original = context["client"]._http

    def wrong_key_http(url, body, headers, timeout):
        status, raw = original(url, body, headers, timeout)
        if url.startswith("https://object-download.quantconnect.com/"):
            with zipfile.ZipFile(io.BytesIO(raw), "r") as source:
                members = source.infolist()
                assert len(members) == 1
                payload = source.read(members[0])
            output = io.BytesIO()
            with zipfile.ZipFile(
                output, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr(
                    "arv2/preopen/output/forbidden.json", payload
                )
            raw = output.getvalue()
        return status, raw

    context["client"]._http = wrong_key_http
    with pytest.raises(prereview.PreopenControlPreReviewLocked) as failure:
        _implementation()(
            plan=context["plan"],
            permit=context["permit"],
            launch=context["launch"],
            terminal=context["terminal"],
            package=context["package"],
            client=context["client"],
            owner_signature=None,
            _transport_capability_minter=_offline_minter,
        )
    assert failure.value.permit_id == context["permit"].permit_id
    assert context["archive_root"].is_dir()
    assert not (context["archive_root"] / prereview.CAPTURE_INDEX_NAME).exists()


def test_prereview_corrupt_shard_locks_without_complete_capture(monkeypatch, tmp_path):
    context = _executed_output_context(monkeypatch, tmp_path, corrupt_shard=True)
    monkeypatch.setattr(
        prereview,
        "_require_download_authority",
        lambda **values: values["package"],
    )
    with pytest.raises(prereview.PreopenControlPreReviewLocked):
        _implementation()(
            plan=context["plan"],
            permit=context["permit"],
            launch=context["launch"],
            terminal=context["terminal"],
            package=context["package"],
            client=context["client"],
            owner_signature=None,
            _transport_capability_minter=_offline_minter,
        )
    assert not (context["archive_root"] / prereview.CAPTURE_INDEX_NAME).exists()


def test_prereview_authority_refuses_in_place_file_change(monkeypatch, tmp_path):
    _context, value = _capture(monkeypatch, tmp_path)
    shard = prereview.preopen_control_prereview_shard_paths(value)[0]
    original = shard.read_bytes()
    shard.write_bytes(original + b"changed")
    with pytest.raises(
        prereview.PreopenControlPreReviewError,
        match="archive authority changed",
    ):
        prereview.require_preopen_control_prereview_archive(value)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda value: value.__setitem__("output_shard_count", True),
            "capture scalar types changed",
        ),
        (
            lambda value: value["files"][2].__setitem__("ordinal", False),
            "capture file scalar types changed",
        ),
    ),
)
def test_prereview_loader_refuses_bool_for_integer_type_confusion(
    monkeypatch, tmp_path, mutate, message
):
    _context, value = _capture(monkeypatch, tmp_path)
    _rewrite_capture_index(value.archive_root, mutate)
    with pytest.raises(prereview.PreopenControlPreReviewError, match=message):
        prereview.load_preopen_control_prereview_archive(value.archive_root)


def test_prereview_loader_refuses_non_path_before_filesystem_callback(monkeypatch):
    callbacks = []

    def hostile(*_args, **_kwargs):
        callbacks.append(True)
        raise AssertionError("filesystem callback executed")

    monkeypatch.setattr(prereview, "_load_capture", hostile)
    with pytest.raises(
        prereview.PreopenControlPreReviewError,
        match="archive path changed",
    ):
        prereview.load_preopen_control_prereview_archive("/private/tmp/archive")
    assert callbacks == []


def test_physical_prereview_archive_preserves_waiver_and_upload_lineage(
    monkeypatch, tmp_path,
):
    plan, context, value = _physical_capture(monkeypatch, tmp_path)
    assert prereview.require_preopen_control_prereview_archive(value) is value
    assert value.review_disposition == plan.review_disposition
    assert value.independent_review_complete is False
    assert value.authorization_basis == plan.authorization_basis
    assert value.owner_review_waiver_id == plan.owner_review_waiver_id
    assert value.owner_review_waiver_scope == (
        "SECTION_72_THROUGH_FIRST_FORMAL_BACKTEST"
    )
    assert value.post_first_formal_backtest_independent_review_required is True
    assert value.input_upload_disposition == plan.input_upload_disposition
    assert value.physical_upload_receipt_id == plan.physical_upload_receipt_id
    assert (
        value.physical_upload_receipt_sha256
        == plan.physical_upload_receipt_sha256
    )
    assert value.physical_upload_plan_sha256 == plan.physical_upload_plan_sha256
    assert value.physical_upload_permit_sha256 == plan.physical_upload_permit_sha256
    assert value.physical_stream_sha256 == plan.physical_stream_sha256
    assert value.input_source_inventory_sha256 == plan.input_source_inventory_sha256
    assert value.preuploaded_object_inventory_sha256 == (
        plan.preuploaded_object_inventory_sha256
    )
    assert value.preuploaded_input_shard_count == plan.preuploaded_input_shard_count
    assert value.preuploaded_object_count == plan.preuploaded_object_count
    assert value.preuploaded_byte_count == plan.preuploaded_byte_count
    assert value.input_objects_reuploaded is False
    assert value.independent_review_performed is False
    assert value.acquisition_receipt_minted is False
    assert value.outcome_result_statistics_log_order_accessed is False
    assert value.deployment_order_trading_authorized is False
    assert context["object_reads"] == [
        value.output_manifest_key,
        context["descriptor"]["object_store_key"],
    ]

    reloaded = prereview.load_preopen_control_prereview_archive(
        value.archive_root
    )
    assert reloaded.capture_sha256 == value.capture_sha256
    assert reloaded.owner_review_waiver_scope == value.owner_review_waiver_scope
    assert (
        prereview.read_preopen_control_prereview_manifest_bytes(reloaded)
        == context["material"]["output"]
    )
    assert tuple(
        prereview.iter_preopen_control_prereview_output_shard_payloads(
            reloaded
        )
    ) == (context["material"]["payload"],)

    original_endpoints = reloaded.endpoint_allowlist
    object.__setattr__(reloaded, "endpoint_allowlist", [])
    try:
        with pytest.raises(
            prereview.PreopenControlPreReviewError,
            match=(
                "^pre-open prereview archive container types changed$"
            ),
        ):
            prereview.require_preopen_control_prereview_archive(reloaded)
    finally:
        object.__setattr__(
            reloaded, "endpoint_allowlist", original_endpoints
        )
    assert (
        prereview.require_preopen_control_prereview_archive(reloaded)
        is reloaded
    )

    original_plan_sha256 = reloaded.plan_sha256
    object.__setattr__(reloaded, "plan_sha256", object())
    try:
        with pytest.raises(
            prereview.PreopenControlPreReviewError,
            match="^pre-open prereview archive scalar types changed$",
        ):
            prereview.require_preopen_control_prereview_archive(reloaded)
    finally:
        object.__setattr__(
            reloaded, "plan_sha256", original_plan_sha256
        )
    assert (
        prereview.require_preopen_control_prereview_archive(reloaded)
        is reloaded
    )

    clone = dataclasses.replace(reloaded)
    with pytest.raises(
        prereview.PreopenControlPreReviewError,
        match="^pre-open prereview archive authority changed$",
    ):
        prereview.require_preopen_control_prereview_archive(clone)
    if hasattr(os, "fork"):
        read_fd, write_fd = os.pipe()
        child = os.fork()
        if child == 0:  # pragma: no cover - asserted through the pipe
            os.close(read_fd)
            try:
                prereview.require_preopen_control_prereview_archive(reloaded)
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
        assert observed == "pre-open prereview archive authority changed"
        assert (
            prereview.require_preopen_control_prereview_archive(reloaded)
            is reloaded
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda index: index.__setitem__(
                "independent_review_complete", True
            ),
            "capture owner-review waiver disposition changed",
        ),
        (
            lambda index: index.__setitem__(
                "physical_upload_receipt_id", ""
            ),
            "capture physical upload identifier lineage changed",
        ),
        (
            lambda index: index.__setitem__(
                "physical_upload_receipt_sha256", "not-a-sha"
            ),
            "capture physical_upload_receipt_sha256 is not SHA-256",
        ),
        (
            lambda index: index.__setitem__(
                "preuploaded_object_count",
                index["preuploaded_input_shard_count"],
            ),
            "capture physical upload census changed",
        ),
    ),
)
def test_physical_prereview_each_waiver_guard_has_distinct_refusal(
    monkeypatch, tmp_path, mutate, message,
):
    _plan, _context, value = _physical_capture(monkeypatch, tmp_path)
    _rewrite_capture_index(value.archive_root, mutate)
    with pytest.raises(
        prereview.PreopenControlPreReviewError,
        match="^" + message + "$",
    ):
        prereview.load_preopen_control_prereview_archive(value.archive_root)
