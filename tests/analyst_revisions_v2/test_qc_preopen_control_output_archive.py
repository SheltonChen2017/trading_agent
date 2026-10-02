from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import stat
import types
import zipfile
from pathlib import Path

import pytest

from research.analyst_revisions_v2.preopen_control_acquisition import (
    acquisition_output_shard_descriptor_records,
)
from research.analyst_revisions_v2_qc import formal_streaming_input as streaming
from research.analyst_revisions_v2_qc import preopen_control_submission_adapter as submission
from research.analyst_revisions_v2_qc.preopen_control_stage import canonical_json_bytes

from .test_qc_preopen_control_stage import _reviewed_receipt, _submission_context


def _private_directory(path: Path) -> Path:
    path.mkdir()
    path.chmod(0o700)
    return path


def _output_package_bytes(plan, receipt) -> bytes:
    return canonical_json_bytes({
        "schema": submission.TERMINAL_PACKAGE_SCHEMA,
        "contract_id": receipt.contract_id,
        "contract_sha256": receipt.contract_sha256,
        "input_manifest": {
            "artifact_id": receipt.input_manifest_id,
            "content_sha256": receipt.input_manifest_sha256,
            "artifact_sha256": receipt.input_manifest_sha256,
            "byte_count": receipt.input_manifest_byte_count,
        },
        "project_source_set_sha256": receipt.project_source_set_sha256,
        "output_manifest": {
            "artifact_id": receipt.artifact_id,
            "content_sha256": receipt.content_sha256,
            "artifact_sha256": receipt.artifact_sha256,
            "byte_count": receipt.byte_count,
            "object_store_key": (
                "arv2/preopen/output/manifests/"
                + receipt.content_sha256
                + ".json"
            ),
        },
        "output_shard_inventory_sha256": (
            receipt.output_shard_inventory_sha256
        ),
        "universe_terminal_projection_sha256": (
            receipt.universe_terminal_projection_sha256
        ),
        "control_terminal_projection_sha256": (
            receipt.control_terminal_projection_sha256
        ),
        "q_data_measurement_projection_sha256": (
            receipt.q_data_measurement_projection_sha256
        ),
        "census": {
            "universe_terminal_count": receipt.universe_terminal_count,
            "control_accepted_count": receipt.control_accepted_count,
            "control_refusal_count": receipt.control_refusal_count,
            "control_terminal_count": receipt.control_terminal_count,
        },
        "outcome_statistics_log_order_accessed": False,
    })


def _executed_output_context(monkeypatch, tmp_path, *, corrupt_shard=False):
    run_directory = _private_directory(tmp_path / "run")
    review_directory = _private_directory(tmp_path / "review")
    archive_parent = _private_directory(tmp_path / "archive-parent")
    receipt, material = _reviewed_receipt(review_directory, monkeypatch)
    base_plan, client, backend, events = _submission_context(
        monkeypatch, run_directory
    )
    archive_root = (
        archive_parent / submission.OUTPUT_ARCHIVE_DIRECTORY_NAME
    )
    plan = submission.build_preopen_qc_submission_plan(
        projection=base_plan.projection,
        input_manifest_bytes=base_plan.input_manifest_bytes,
        input_shards=base_plan.input_shards,
        run_authority=base_plan.run_authority,
        organization_id=base_plan.organization_id,
        output_archive_root=archive_root,
    )
    assert receipt.input_manifest_sha256 == plan.input_manifest_sha256
    assert receipt.project_source_set_sha256 == plan.project_source_set_sha256
    package_bytes = _output_package_bytes(plan, receipt)
    manifest_key = (
        "arv2/preopen/output/manifests/" + receipt.content_sha256 + ".json"
    )
    descriptor = acquisition_output_shard_descriptor_records(receipt)[0]
    shard_payload = material["payload"]
    objects = {
        plan.terminal_package_key: package_bytes,
        manifest_key: material["output"],
        descriptor["object_store_key"]: (
            shard_payload + b"corrupt" if corrupt_shard else shard_payload
        ),
    }
    object_reads = []
    original_http = client._http
    pending_download_keys = []
    signed_download_url = (
        "https://object-download.quantconnect.com/"
        "arv2-preopen-output.zip?signature=fixture"
    )

    def http(url, body, headers, timeout):
        if not url.endswith("/object/get") and url != signed_download_url:
            return original_http(url, body, headers, timeout)
        if url == signed_download_url:
            assert body == b""
            assert headers == {}
            key = pending_download_keys.pop(0)
            output = io.BytesIO()
            with zipfile.ZipFile(
                output, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr(key, objects[key])
            return 200, output.getvalue()
        payload = json.loads(body)
        assert payload == {
            "organizationId": plan.organization_id,
            "keys": [payload["keys"][0]],
        }
        events.append("object/read")
        assert (run_directory / submission.PERMIT_FILENAME).exists()
        key = payload["keys"][0]
        object_reads.append(key)
        assert key in objects
        pending_download_keys.append(key)
        value = {
            "jobId": "2585354eb2e23cbbc4ba714332884650",
            "url": signed_download_url,
            "success": True,
            "errors": [],
        }
        return 200, json.dumps(value, separators=(",", ":")).encode("ascii")

    client._http = http
    permit, launch = submission.execute_preopen_qc_submission_once(
        plan=plan,
        client=client,
        ledger_directory=run_directory,
        started_at_utc="2026-09-12T12:00:00.000000Z",
        owner_signature=None,
    )
    terminal = submission.inspect_preopen_qc_terminal_status(
        plan=plan,
        permit=permit,
        launch=launch,
        client=client,
        owner_signature=None,
    )
    package = submission.retrieve_preopen_qc_terminal_package(
        plan=plan,
        permit=permit,
        launch=launch,
        terminal=terminal,
        client=client,
        owner_signature=None,
    )
    capacity = types.SimpleNamespace(preopen_acquisition_receipt=receipt)
    monkeypatch.setattr(
        submission,
        "require_formal_streaming_capacity_binding",
        lambda value: value,
    )
    return {
        "plan": plan,
        "client": client,
        "permit": permit,
        "launch": launch,
        "terminal": terminal,
        "package": package,
        "receipt": receipt,
        "capacity": capacity,
        "material": material,
        "descriptor": descriptor,
        "archive_root": archive_root,
        "events": events,
        "object_reads": object_reads,
    }


@pytest.mark.parametrize(
    ("namespace", "name"),
    (
        (submission.preopen_io, "_PhysicalShardCursor"),
        (streaming, "_read_private_regular"),
    ),
)
def test_output_action_refuses_rebound_transitive_parser_before_read_or_archive(
    monkeypatch, tmp_path, namespace, name,
):
    production_download = (
        submission.download_and_load_preopen_qc_terminal_archive
    )
    with pytest.MonkeyPatch.context() as setup_patch:
        context = _executed_output_context(setup_patch, tmp_path)
    callbacks = []
    reads_before = tuple(context["object_reads"])
    authorities_before = tuple(submission._OUTPUT_RECEIPT_AUTHORITIES.items())

    def hostile(*args, **values):
        callbacks.append((args, values))
        raise AssertionError("hostile pre-open parser executed")

    monkeypatch.setattr(namespace, name, hostile)
    with pytest.raises(
        submission.PreopenQcSubmissionError,
        match="action dependency authority changed",
    ):
        production_download(
            plan=context["plan"],
            permit=context["permit"],
            launch=context["launch"],
            terminal=context["terminal"],
            package=context["package"],
            preopen_acquisition_receipt=context["receipt"],
            capacity=context["capacity"],
            client=context["client"],
            owner_signature=None,
        )
    assert callbacks == []
    assert tuple(context["object_reads"]) == reads_before
    assert tuple(submission._OUTPUT_RECEIPT_AUTHORITIES.items()) == (
        authorities_before
    )
    assert not context["archive_root"].exists()


def test_output_archive_is_signed_bounded_private_and_manifest_last(
    monkeypatch, tmp_path
):
    context = _executed_output_context(monkeypatch, tmp_path)
    plan = context["plan"]
    candidate = json.loads(
        submission.render_preopen_qc_execution_authority_candidate(plan)
    )
    assert candidate["output_archive_root"] == str(context["archive_root"])
    assert candidate["maximum_output_manifest_bytes"] == (
        submission.MAX_OUTPUT_MANIFEST_BYTES
    )
    assert candidate["maximum_output_shard_reads"] == 1
    assert candidate["maximum_output_shard_read_bytes"] == (
        submission.MAX_OUTPUT_SHARD_READ_BYTES
    )
    assert candidate["manifest_persisted_last"] is True
    assert (
        "object/read_exact_output_manifest_then_content_addressed_terminal_shards_once"
        in candidate["actions"]
    )

    write_order = []
    real_write = submission._write_private_archive_file

    def observed_write(path, payload, name):
        write_order.append(path.name)
        return real_write(path, payload, name)

    sentinel = object()
    loaded = {}

    def fake_loader(**kwargs):
        loaded.update(kwargs)
        assert (
            context["archive_root"] / submission.OUTPUT_ARCHIVE_MANIFEST_NAME
        ).exists()
        return sentinel

    monkeypatch.setattr(submission, "_write_private_archive_file", observed_write)
    monkeypatch.setattr(
        submission, "load_physical_preopen_terminal_archive", fake_loader
    )
    download_impl = next(
        cell.cell_contents
        for name, cell in zip(
            submission.download_and_load_preopen_qc_terminal_archive.__code__.co_freevars,
            submission.download_and_load_preopen_qc_terminal_archive.__closure__,
            strict=True,
        )
        if name == "download_impl"
    )
    monkeypatch.setitem(
        download_impl.__globals__,
        "load_physical_preopen_terminal_archive",
        fake_loader,
    )
    monkeypatch.setitem(
        download_impl.__globals__,
        "_write_private_archive_file",
        observed_write,
    )
    result = submission.download_and_load_preopen_qc_terminal_archive(
        plan=plan,
        permit=context["permit"],
        launch=context["launch"],
        terminal=context["terminal"],
        package=context["package"],
        preopen_acquisition_receipt=context["receipt"],
        capacity=context["capacity"],
        client=context["client"],
        owner_signature=None,
    )
    assert result is sentinel
    manifest_path = (
        context["archive_root"] / submission.OUTPUT_ARCHIVE_MANIFEST_NAME
    )
    shard_path = loaded["shard_paths"][0]
    assert write_order == [shard_path.name, manifest_path.name]
    assert manifest_path.read_bytes() == context["material"]["output"]
    assert shard_path.read_bytes() == context["material"]["payload"]
    assert stat.S_IMODE(context["archive_root"].stat().st_mode) == 0o700
    assert stat.S_IMODE(shard_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(shard_path.stat().st_mode) == 0o600
    assert context["object_reads"] == [
        plan.terminal_package_key,
        context["package"].output_manifest_key,
        context["descriptor"]["object_store_key"],
    ]
    assert context["events"].count("object/read") == 3
    assert not {
        "backtests/read", "projects/delete", "orders/read", "logs/read"
    }.intersection(context["events"])


def test_output_archive_ambiguity_is_one_way_and_cannot_be_retried(
    monkeypatch, tmp_path
):
    context = _executed_output_context(
        monkeypatch, tmp_path, corrupt_shard=True
    )
    arguments = {
        "plan": context["plan"],
        "permit": context["permit"],
        "launch": context["launch"],
        "terminal": context["terminal"],
        "package": context["package"],
        "preopen_acquisition_receipt": context["receipt"],
        "capacity": context["capacity"],
        "client": context["client"],
        "owner_signature": None,
    }
    with pytest.raises(submission.PreopenQcSubmissionLocked) as first:
        submission.download_and_load_preopen_qc_terminal_archive(**arguments)
    assert first.value.permit_id == context["permit"].permit_id
    assert context["archive_root"].is_dir()
    assert not (
        context["archive_root"] / submission.OUTPUT_ARCHIVE_MANIFEST_NAME
    ).exists()
    read_count = len(context["object_reads"])
    with pytest.raises(submission.PreopenQcSubmissionLocked) as second:
        submission.download_and_load_preopen_qc_terminal_archive(**arguments)
    assert second.value.permit_id == context["permit"].permit_id
    assert len(context["object_reads"]) == read_count


def test_output_archive_plan_rejects_a_broken_symlink_leaf(monkeypatch, tmp_path):
    run_directory = _private_directory(tmp_path / "run")
    base_plan, _client, _backend, _events = _submission_context(
        monkeypatch, run_directory
    )
    archive_parent = _private_directory(tmp_path / "archive-parent")
    archive_root = archive_parent / submission.OUTPUT_ARCHIVE_DIRECTORY_NAME
    archive_root.symlink_to(tmp_path / "missing", target_is_directory=True)
    with pytest.raises(
        submission.PreopenQcSubmissionError, match="owner-only"
    ):
        submission.build_preopen_qc_submission_plan(
            projection=base_plan.projection,
            input_manifest_bytes=base_plan.input_manifest_bytes,
            input_shards=base_plan.input_shards,
            run_authority=base_plan.run_authority,
            organization_id=base_plan.organization_id,
            output_archive_root=archive_root,
        )


def test_output_archive_plan_rejects_a_symlinked_parent(monkeypatch, tmp_path):
    run_directory = _private_directory(tmp_path / "run")
    base_plan, _client, _backend, _events = _submission_context(
        monkeypatch, run_directory
    )
    real_parent = _private_directory(tmp_path / "real-parent")
    alias = tmp_path / "parent-alias"
    alias.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(
        submission.PreopenQcSubmissionError, match="canonical absolute"
    ):
        submission.build_preopen_qc_submission_plan(
            projection=base_plan.projection,
            input_manifest_bytes=base_plan.input_manifest_bytes,
            input_shards=base_plan.input_shards,
            run_authority=base_plan.run_authority,
            organization_id=base_plan.organization_id,
            output_archive_root=(
                alias / submission.OUTPUT_ARCHIVE_DIRECTORY_NAME
            ),
        )


def test_archive_directory_fsync_ambiguity_locks_before_remote_output_read(
    monkeypatch, tmp_path
):
    context = _executed_output_context(monkeypatch, tmp_path)
    package_read_count = len(context["object_reads"])
    monkeypatch.setattr(
        submission,
        "_fsync_private_directory",
        lambda *_args: (_ for _ in ()).throw(
            submission.PreopenQcSubmissionError("injected fsync ambiguity")
        ),
    )
    with pytest.raises(submission.PreopenQcSubmissionLocked) as failure:
        submission.download_and_load_preopen_qc_terminal_archive(
            plan=context["plan"],
            permit=context["permit"],
            launch=context["launch"],
            terminal=context["terminal"],
            package=context["package"],
            preopen_acquisition_receipt=context["receipt"],
            capacity=context["capacity"],
            client=context["client"],
            owner_signature=None,
        )
    assert failure.value.permit_id == context["permit"].permit_id
    assert context["archive_root"].is_dir()
    assert len(context["object_reads"]) == package_read_count


def test_physical_archive_loader_passes_one_shard_at_a_time_iterator(
    monkeypatch, tmp_path
):
    source_directory = _private_directory(tmp_path / "source")
    receipt, material = _reviewed_receipt(source_directory, monkeypatch)
    shard_path = source_directory / "physical-preopen-0000.jsonl.gz"
    shard_path.write_bytes(material["payload"])
    shard_path.chmod(0o600)
    capacity = types.SimpleNamespace(
        preopen_acquisition_receipt=receipt,
        limits=(("max_physical_shard_count", 10),),
        receipt_id="arv2-test-streaming-capacity",
        receipt_sha256="a" * 64,
    )
    monkeypatch.setattr(
        streaming, "require_formal_streaming_capacity_binding", lambda value: value
    )
    real_validate = streaming.preopen_io._validated_batch_major_output_payloads
    observed = []

    def validate(manifest, payloads):
        observed.append(payloads)
        assert not isinstance(payloads, (list, tuple))
        assert iter(payloads) is payloads
        return real_validate(manifest, payloads)

    monkeypatch.setattr(
        streaming.preopen_io, "_validated_batch_major_output_payloads", validate
    )
    loaded = streaming.load_physical_preopen_terminal_archive(
        preopen_acquisition_receipt=receipt,
        capacity=capacity,
        shard_paths=(shard_path,),
    )
    assert observed
    assert loaded.path_fingerprints
    assert loaded.physical_payload_projection_sha256 == (
        receipt.output_shard_payload_projection_sha256
    )
