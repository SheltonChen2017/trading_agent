"""Acquire completed pre-open Object Store outputs for independent review.

The accepted acquisition receipt cannot exist until an independent reviewer
has inspected the exact output manifest and terminal shards.  This module
therefore performs only the missing earlier step: it reads the already named,
outcome-free terminal objects and freezes them as inert owner-only files.

The capture grants no research-result, deployment, order, or trading
authority.  Its durable index is loadable by a later review process and its
exact manifest/shard bytes feed the existing independent-acquisition loader.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import stat
import threading
import weakref
from pathlib import Path
from typing import Iterator

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2 import preopen_control_acquisition as core
from research.analyst_revisions_v2_qc import formal_submission_adapter as formal
from research.analyst_revisions_v2_qc import preopen_control_acquisition_io as acquisition_io
from research.analyst_revisions_v2_qc import preopen_control_submission_adapter as submission
from research.analyst_revisions_v2_qc.formal_qc_transport import FormalQcTransport
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
)


class PreopenControlPreReviewError(ValueError):
    """The terminal-output capture or its authority is invalid."""


class PreopenControlPreReviewLocked(RuntimeError):
    """A partial immutable capture exists, so the read attempt is ambiguous."""

    def __init__(self, permit_id: str, detail: str) -> None:
        super().__init__(
            f"preopen_prereview_capture: {detail}; immutable partial capture retained"
        )
        self.permit_id = permit_id


CAPTURE_SCHEMA = "arv2-preopen-control-prereview-capture-v1"
CAPTURE_INDEX_NAME = "prereview-capture.json"
TERMINAL_PACKAGE_NAME = "terminal-package.json"
SUMMARY_RECEIPT_NAME = "summary-receipt.json"
QC_EXECUTION_RECEIPT_NAME = "qc-execution-receipt.json"
MAX_CAPTURE_INDEX_BYTES = 8 * 1024 * 1024
MAX_SUPPORTING_RECEIPT_BYTES = 256 * 1024
OBJECT_ENDPOINT_ALLOWLIST = ("object/read",)
OWNER_WAIVER_CAPTURE_FIELDS = frozenset({
    "review_disposition",
    "independent_review_complete",
    "authorization_basis",
    "owner_review_waiver_id",
    "owner_review_waiver_scope",
    "post_first_formal_backtest_independent_review_required",
    "input_upload_disposition",
    "physical_upload_receipt_id",
    "physical_upload_receipt_sha256",
    "physical_upload_plan_id",
    "physical_upload_plan_sha256",
    "physical_upload_permit_id",
    "physical_upload_permit_sha256",
    "physical_stream_id",
    "physical_stream_sha256",
    "input_source_inventory_sha256",
    "preuploaded_object_inventory_sha256",
    "preuploaded_input_shard_count",
    "preuploaded_object_count",
    "preuploaded_byte_count",
    "input_objects_reuploaded",
})

_PINNED_REQUIRE_PLAN = submission.require_preopen_qc_submission_plan
_PINNED_CANONICAL_JSON_BYTES = canonical_json_bytes
_PINNED_REQUIRE_PERMIT = submission.require_preopen_qc_submission_permit
_PINNED_REQUIRE_TERMINAL = submission._require_terminal_receipt
_PINNED_REQUIRE_PACKAGE = submission.require_preopen_qc_output_package_receipt
_PINNED_BUILD_HOST_CLOSURE = submission.build_preopen_qc_host_closure_binding
_PINNED_VERIFY_HOST_CLOSURE = submission.verify_preopen_qc_host_closure_live
_PINNED_BUILD_PHYSICAL_HOST_CLOSURE = (
    submission.build_physical_preopen_qc_host_closure_binding
)
_PINNED_VERIFY_PHYSICAL_HOST_CLOSURE = (
    submission.verify_physical_preopen_qc_host_closure_live
)
_PINNED_REQUIRE_OWNER = submission._require_external_execution_trust_root
_PINNED_RENDER_OWNER_AUTHORITY = (
    submission.render_preopen_qc_execution_authority_candidate
)
_PINNED_OBJECT_PAYLOAD = submission._object_payload
_PINNED_PREPARE_ROOT = submission._prepare_output_archive
_PINNED_WRITE_PRIVATE = submission._write_private_archive_file
_PINNED_READ_PRIVATE = submission._read_private_archive_file
_PINNED_FSYNC_DIRECTORY = submission._fsync_private_directory
_PINNED_VALIDATE_MANIFEST = core._validate_manifest
_PINNED_VALIDATE_PAYLOADS = acquisition_io._validated_batch_major_output_payloads
_PINNED_RENDER_EXECUTION = acquisition_io.render_preopen_qc_execution_receipt
_PINNED_TRANSPORT_CALL = formal._transport_call
_PINNED_OWNER_REVIEW_WAIVER_ID = submission.OWNER_REVIEW_WAIVER_ID
_PINNED_OWNER_REVIEW_WAIVER_SCOPE = submission.OWNER_REVIEW_WAIVER_SCOPE
_PINNED_OWNER_REVIEW_WAIVER_BASIS = submission.OWNER_REVIEW_WAIVER_BASIS
_PINNED_OWNER_REVIEW_WAIVER_DISPOSITION = (
    submission.OWNER_REVIEW_WAIVER_DISPOSITION
)
_PINNED_PHYSICAL_INPUT_UPLOAD_DISPOSITION = (
    submission.PHYSICAL_INPUT_UPLOAD_DISPOSITION
)


def _require_review_dependency_authority() -> None:
    expected = (
        (globals(), "canonical_json_bytes", _PINNED_CANONICAL_JSON_BYTES),
        (submission, "_read_private_archive_file", _PINNED_READ_PRIVATE),
        (core, "_validate_manifest", _PINNED_VALIDATE_MANIFEST),
        (
            acquisition_io,
            "_validated_batch_major_output_payloads",
            _PINNED_VALIDATE_PAYLOADS,
        ),
        (
            acquisition_io,
            "render_preopen_qc_execution_receipt",
            _PINNED_RENDER_EXECUTION,
        ),
        (
            submission,
            "OWNER_REVIEW_WAIVER_ID",
            _PINNED_OWNER_REVIEW_WAIVER_ID,
        ),
        (
            submission,
            "OWNER_REVIEW_WAIVER_SCOPE",
            _PINNED_OWNER_REVIEW_WAIVER_SCOPE,
        ),
        (
            submission,
            "OWNER_REVIEW_WAIVER_BASIS",
            _PINNED_OWNER_REVIEW_WAIVER_BASIS,
        ),
        (
            submission,
            "OWNER_REVIEW_WAIVER_DISPOSITION",
            _PINNED_OWNER_REVIEW_WAIVER_DISPOSITION,
        ),
        (
            submission,
            "PHYSICAL_INPUT_UPLOAD_DISPOSITION",
            _PINNED_PHYSICAL_INPUT_UPLOAD_DISPOSITION,
        ),
    )
    if any(
        (
            namespace.get(name) if type(namespace) is dict
            else getattr(namespace, name, None)
        )
        is not value
        for namespace, name, value in expected
    ):
        raise PreopenControlPreReviewError(
            "pre-open prereview dependency authority changed"
        )


def _require_dependency_authority() -> None:
    _require_review_dependency_authority()
    expected = (
        (submission, "require_preopen_qc_submission_plan", _PINNED_REQUIRE_PLAN),
        (submission, "require_preopen_qc_submission_permit", _PINNED_REQUIRE_PERMIT),
        (submission, "_require_terminal_receipt", _PINNED_REQUIRE_TERMINAL),
        (
            submission,
            "require_preopen_qc_output_package_receipt",
            _PINNED_REQUIRE_PACKAGE,
        ),
        (submission, "build_preopen_qc_host_closure_binding", _PINNED_BUILD_HOST_CLOSURE),
        (submission, "verify_preopen_qc_host_closure_live", _PINNED_VERIFY_HOST_CLOSURE),
        (
            submission,
            "build_physical_preopen_qc_host_closure_binding",
            _PINNED_BUILD_PHYSICAL_HOST_CLOSURE,
        ),
        (
            submission,
            "verify_physical_preopen_qc_host_closure_live",
            _PINNED_VERIFY_PHYSICAL_HOST_CLOSURE,
        ),
        (submission, "_require_external_execution_trust_root", _PINNED_REQUIRE_OWNER),
        (
            submission,
            "render_preopen_qc_execution_authority_candidate",
            _PINNED_RENDER_OWNER_AUTHORITY,
        ),
        (submission, "_object_payload", _PINNED_OBJECT_PAYLOAD),
        (submission, "_prepare_output_archive", _PINNED_PREPARE_ROOT),
        (submission, "_write_private_archive_file", _PINNED_WRITE_PRIVATE),
        (submission, "_fsync_private_directory", _PINNED_FSYNC_DIRECTORY),
        (formal, "_transport_call", _PINNED_TRANSPORT_CALL),
    )
    if any(getattr(namespace, name, None) is not value for namespace, name, value in expected):
        raise PreopenControlPreReviewError(
            "pre-open prereview dependency authority changed"
        )


def _strict_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise PreopenControlPreReviewError(f"{name} is not nonempty bytes")

    def pairs(items):
        result: dict[str, object] = {}
        for key, value in items:
            if type(key) is not str or key in result:
                raise PreopenControlPreReviewError(
                    f"{name} has duplicate or non-string keys"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=lambda _value: (_ for _ in ()).throw(
                PreopenControlPreReviewError(f"{name} contains a float")
            ),
            parse_constant=lambda _value: (_ for _ in ()).throw(
                PreopenControlPreReviewError(
                    f"{name} contains a non-finite value"
                )
            ),
        )
    except PreopenControlPreReviewError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise PreopenControlPreReviewError(f"{name} is not strict JSON") from exc
    if type(value) is not dict or _PINNED_CANONICAL_JSON_BYTES(value) != payload:
        raise PreopenControlPreReviewError(f"{name} is not canonical JSON")
    return value


def _sha(value: object, name: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PreopenControlPreReviewError(f"{name} is not SHA-256")
    return value


def _validate_capture_scalar_types(index: dict[str, object]) -> None:
    sha_fields = (
        "capture_sha256", "plan_sha256", "permit_sha256",
        "launch_receipt_sha256", "terminal_receipt_sha256",
        "output_package_receipt_sha256", "package_sha256",
        "output_manifest_sha256", "output_shard_inventory_sha256",
        "output_shard_payload_projection_sha256",
        "universe_terminal_projection_sha256",
        "control_terminal_projection_sha256",
        "q_data_measurement_projection_sha256",
    )
    text_fields = (
        "schema", "capture_id", "permit_id", "compile_id", "backtest_id",
        "terminal_status", "package_key", "output_manifest_key",
    )
    positive_fields = (
        "project_id", "package_byte_count", "output_manifest_byte_count",
        "output_shard_count", "terminal_count",
        "downloader_object_read_count",
        "complete_preopen_output_object_read_count",
    )
    nonnegative_fields = ("accepted_count", "refusal_count")
    false_fields = (
        "independent_review_performed", "acquisition_receipt_minted",
        "outcome_result_statistics_log_order_accessed",
        "deployment_order_trading_authorized",
    )
    if (
        any(type(index.get(name)) is not str or not index[name] for name in text_fields)
        or any(
            type(index.get(name)) is not int or index[name] < 1
            for name in positive_fields
        )
        or any(
            type(index.get(name)) is not int or index[name] < 0
            for name in nonnegative_fields
        )
        or any(index.get(name) is not False for name in false_fields)
        or type(index.get("endpoint_allowlist")) is not list
        or any(type(item) is not str for item in index["endpoint_allowlist"])
        or type(index.get("object_store_key_allowlist")) is not list
        or any(
            type(item) is not str or not item
            for item in index["object_store_key_allowlist"]
        )
    ):
        raise PreopenControlPreReviewError("capture scalar types changed")
    for name in sha_fields:
        _sha(index.get(name), "capture " + name)


def _validate_owner_waiver_capture(index: dict[str, object]) -> None:
    text_fields = (
        "physical_upload_receipt_id",
        "physical_upload_plan_id",
        "physical_upload_permit_id",
        "physical_stream_id",
    )
    sha_fields = (
        "physical_upload_receipt_sha256",
        "physical_upload_plan_sha256",
        "physical_upload_permit_sha256",
        "physical_stream_sha256",
        "input_source_inventory_sha256",
        "preuploaded_object_inventory_sha256",
    )
    if (
        index.get("review_disposition")
        != submission.OWNER_REVIEW_WAIVER_DISPOSITION
        or index.get("independent_review_complete") is not False
        or index.get("authorization_basis")
        != submission.OWNER_REVIEW_WAIVER_BASIS
        or index.get("owner_review_waiver_id")
        != submission.OWNER_REVIEW_WAIVER_ID
        or index.get("owner_review_waiver_scope")
        != submission.OWNER_REVIEW_WAIVER_SCOPE
        or index.get(
            "post_first_formal_backtest_independent_review_required"
        )
        is not True
        or index.get("input_upload_disposition")
        != submission.PHYSICAL_INPUT_UPLOAD_DISPOSITION
        or index.get("input_objects_reuploaded") is not False
    ):
        raise PreopenControlPreReviewError(
            "capture owner-review waiver disposition changed"
        )
    if any(
        type(index.get(name)) is not str or not index[name]
        for name in text_fields
    ):
        raise PreopenControlPreReviewError(
            "capture physical upload identifier lineage changed"
        )
    for name in sha_fields:
        _sha(index.get(name), "capture " + name)
    if (
        type(index.get("preuploaded_input_shard_count")) is not int
        or index["preuploaded_input_shard_count"] < 1
        or type(index.get("preuploaded_object_count")) is not int
        or index["preuploaded_object_count"]
        != index["preuploaded_input_shard_count"] + 1
        or type(index.get("preuploaded_byte_count")) is not int
        or index["preuploaded_byte_count"] < 1
    ):
        raise PreopenControlPreReviewError(
            "capture physical upload census changed"
        )


def _validate_capture_file_record(
    record: dict[str, object], *, role: str, ordinal: int | None,
) -> None:
    if (
        record.get("role") != role
        or record.get("role").__class__ is not str
        or record.get("ordinal") != ordinal
        or record.get("ordinal").__class__
        is not (type(None) if ordinal is None else int)
        or type(record.get("relative_path")) is not str
        or not record["relative_path"]
        or (
            type(record.get("object_store_key")) is not str
            if role in {"terminal_package", "output_manifest", "terminal_shard"}
            else record.get("object_store_key") is not None
        )
        or type(record.get("byte_count")) is not int
        or record["byte_count"] < 1
    ):
        raise PreopenControlPreReviewError("capture file scalar types changed")
    _sha(record.get("sha256"), "capture file SHA-256")


def _directory_stat(path: Path, name: str) -> tuple[int, int, int, int, int, int]:
    if type(path) is not type(Path()) or not path.is_absolute() or path.is_symlink():
        raise PreopenControlPreReviewError(f"{name} path changed")
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise PreopenControlPreReviewError(f"{name} is unavailable") from exc
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_IMODE(observed.st_mode) != 0o700
        or (hasattr(os, "getuid") and observed.st_uid != os.getuid())
    ):
        raise PreopenControlPreReviewError(f"{name} is not owner-only")
    return (
        observed.st_dev,
        observed.st_ino,
        observed.st_mode,
        observed.st_size,
        observed.st_mtime_ns,
        observed.st_ctime_ns,
    )


def _private_file_stat(
    path: Path, name: str
) -> tuple[int, int, int, int, int, int]:
    if type(path) is not type(Path()) or not path.is_absolute() or path.is_symlink():
        raise PreopenControlPreReviewError(f"{name} path changed")
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise PreopenControlPreReviewError(f"{name} is unavailable") from exc
    if (
        not stat.S_ISREG(observed.st_mode)
        or observed.st_nlink != 1
        or stat.S_IMODE(observed.st_mode) != 0o600
        or (hasattr(os, "getuid") and observed.st_uid != os.getuid())
    ):
        raise PreopenControlPreReviewError(f"{name} is not owner-only")
    return (
        observed.st_dev,
        observed.st_ino,
        observed.st_mode,
        observed.st_size,
        observed.st_mtime_ns,
        observed.st_ctime_ns,
    )


def _read_unbound_private_file(path: Path, maximum: int, name: str) -> bytes:
    """Read a not-yet-trusted index without following links or exceeding a cap."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        descriptor = os.open(path, flags)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or not 0 < before.st_size <= maximum
                or stat.S_IMODE(before.st_mode) != 0o600
                or (hasattr(os, "getuid") and before.st_uid != os.getuid())
            ):
                raise PreopenControlPreReviewError(
                    f"{name} is not an exact private file"
                )
            chunks = []
            remaining = maximum + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except PreopenControlPreReviewError:
        raise
    except OSError as exc:
        raise PreopenControlPreReviewError(f"{name} could not be read") from exc
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if (
        len(payload) != before.st_size
        or len(payload) > maximum
        or tuple(getattr(before, field) for field in identity)
        != tuple(getattr(after, field) for field in identity)
    ):
        raise PreopenControlPreReviewError(f"{name} changed while read")
    return payload


def _output_descriptor_key(descriptor: dict[str, object]) -> str:
    try:
        key = (
            "arv2/preopen/output/content/control_terminals/"
            f"chunk-{descriptor['decision_chunk_ordinal']:04d}/"
            f"security-batch-{descriptor['security_batch_ordinal']:04d}/"
            f"{descriptor['compressed_sha256']}-jsonl.gz"
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PreopenControlPreReviewError(
            "pre-open output shard descriptor changed"
        ) from exc
    if descriptor.get("object_store_key") != key:
        raise PreopenControlPreReviewError(
            "pre-open output shard key is not content-derived"
        )
    return key


def _validate_package_manifest(
    *, package_bytes: bytes, manifest_bytes: bytes
) -> tuple[dict[str, object], dict[str, object]]:
    package = _strict_object(package_bytes, "terminal package")
    try:
        manifest, _universe, _controls = _PINNED_VALIDATE_MANIFEST(manifest_bytes)
    except Exception as exc:
        raise PreopenControlPreReviewError(
            "pre-open output manifest is invalid"
        ) from exc
    output = package.get("output_manifest")
    input_manifest = package.get("input_manifest")
    package_census = package.get("census")
    manifest_census = manifest.get("census")
    expected_package_fields = {
        "schema", "contract_id", "contract_sha256", "input_manifest",
        "project_source_set_sha256", "output_manifest",
        "output_shard_inventory_sha256",
        "universe_terminal_projection_sha256",
        "control_terminal_projection_sha256",
        "q_data_measurement_projection_sha256", "census",
        "outcome_statistics_log_order_accessed",
    }
    if (
        set(package) != expected_package_fields
        or package.get("schema") != submission.TERMINAL_PACKAGE_SCHEMA
        or package.get("contract_id") != core.CONTRACT_ID
        or package.get("contract_sha256") != core.CONTRACT_SHA256
        or type(input_manifest) is not dict
        or set(input_manifest)
        != {"artifact_id", "content_sha256", "artifact_sha256", "byte_count"}
        or input_manifest.get("content_sha256")
        != input_manifest.get("artifact_sha256")
        or type(output) is not dict
        or set(output)
        != {
            "artifact_id", "content_sha256", "artifact_sha256", "byte_count",
            "object_store_key",
        }
        or type(package_census) is not dict
        or set(package_census)
        != {
            "universe_terminal_count", "control_accepted_count",
            "control_refusal_count", "control_terminal_count",
        }
        or type(manifest_census) is not dict
        or package.get("outcome_statistics_log_order_accessed") is not False
        or output.get("content_sha256")
        != hashlib.sha256(manifest_bytes).hexdigest()
        or output.get("artifact_sha256") != output.get("content_sha256")
        or output.get("byte_count") != len(manifest_bytes)
        or output.get("artifact_id")
        != "arv2-preopen-control-output-" + output["content_sha256"][:24]
        or output.get("object_store_key")
        != "arv2/preopen/output/manifests/"
        + output["content_sha256"]
        + ".json"
        or input_manifest != manifest.get("input_manifest")
        or package.get("project_source_set_sha256")
        != manifest.get("project_source_set_sha256")
        or package.get("output_shard_inventory_sha256")
        != manifest.get("output_shard_inventory_sha256")
        or package.get("universe_terminal_projection_sha256")
        != manifest.get("universe_terminal_projection_sha256")
        or package.get("control_terminal_projection_sha256")
        != manifest.get("control_terminal_projection_sha256")
        or package.get("q_data_measurement_projection_sha256")
        != manifest.get("construction_intermediates", {}).get(
            "q_data_measurement_projection_sha256"
        )
        or package_census.get("universe_terminal_count")
        != manifest_census.get("universe_terminal_count")
        or package_census.get("control_accepted_count")
        != manifest_census.get("control_accepted_count")
        or package_census.get("control_refusal_count")
        != manifest_census.get("control_refusal_count")
        or package_census.get("control_terminal_count")
        != manifest_census.get("control_terminal_count")
    ):
        raise PreopenControlPreReviewError(
            "terminal package and output manifest differ"
        )
    return package, manifest


def _summary_bytes(manifest_bytes: bytes, manifest: dict[str, object]) -> bytes:
    census = manifest["census"]
    return _PINNED_CANONICAL_JSON_BYTES({
        "schema": acquisition_io.SUMMARY_SCHEMA,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest_byte_count": len(manifest_bytes),
        "source_set_sha256": manifest["project_source_set_sha256"],
        "terminal_count": census["control_terminal_count"],
        "accepted_count": census["control_accepted_count"],
        "refusal_count": census["control_refusal_count"],
        "shard_count": len(manifest["output_shards"]),
    })


def _file_record(
    *, role: str, ordinal: int | None, relative_path: str,
    object_store_key: str | None, payload: bytes,
) -> dict[str, object]:
    return {
        "role": role,
        "ordinal": ordinal,
        "relative_path": relative_path,
        "object_store_key": object_store_key,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
    }


def _capture_seed(
    *, plan, permit, launch, terminal, package, manifest: dict[str, object],
    files: list[dict[str, object]],
) -> dict[str, object]:
    descriptors = manifest["output_shards"]
    allowed_keys = [
        package.output_manifest_key,
        *[descriptor["object_store_key"] for descriptor in descriptors],
    ]
    seed = {
        "schema": CAPTURE_SCHEMA,
        "capture_id": None,
        "capture_sha256": None,
        "plan_sha256": plan.plan_sha256,
        "permit_id": permit.permit_id,
        "permit_sha256": permit.permit_sha256,
        "launch_receipt_sha256": launch.receipt_sha256,
        "terminal_receipt_sha256": terminal.receipt_sha256,
        "output_package_receipt_sha256": package.receipt_sha256,
        "project_id": launch.project_id,
        "compile_id": launch.compile_id,
        "backtest_id": launch.backtest_id,
        "terminal_status": terminal.terminal_status,
        "package_key": package.package_key,
        "package_sha256": package.package_sha256,
        "package_byte_count": package.package_byte_count,
        "output_manifest_key": package.output_manifest_key,
        "output_manifest_sha256": package.output_manifest_sha256,
        "output_manifest_byte_count": package.output_manifest_byte_count,
        "output_shard_inventory_sha256": package.output_shard_inventory_sha256,
        "universe_terminal_projection_sha256": (
            package.universe_terminal_projection_sha256
        ),
        "control_terminal_projection_sha256": (
            package.control_terminal_projection_sha256
        ),
        "q_data_measurement_projection_sha256": (
            package.q_data_measurement_projection_sha256
        ),
        "output_shard_count": len(descriptors),
        "terminal_count": package.terminal_count,
        "accepted_count": package.accepted_count,
        "refusal_count": package.refusal_count,
        "endpoint_allowlist": list(OBJECT_ENDPOINT_ALLOWLIST),
        "object_store_key_allowlist": allowed_keys,
        "downloader_object_read_count": len(allowed_keys),
        "complete_preopen_output_object_read_count": len(allowed_keys) + 1,
        "files": files,
        "independent_review_performed": False,
        "acquisition_receipt_minted": False,
        "outcome_result_statistics_log_order_accessed": False,
        "deployment_order_trading_authorized": False,
    }
    if type(plan) is submission.PhysicalPreopenQcSubmissionPlan:
        seed.update({
            "review_disposition": plan.review_disposition,
            "independent_review_complete": plan.independent_review_complete,
            "authorization_basis": plan.authorization_basis,
            "owner_review_waiver_id": plan.owner_review_waiver_id,
            "owner_review_waiver_scope": plan.owner_review_waiver_scope,
            "post_first_formal_backtest_independent_review_required": (
                plan.post_first_formal_backtest_independent_review_required
            ),
            "input_upload_disposition": plan.input_upload_disposition,
            "physical_upload_receipt_id": plan.physical_upload_receipt_id,
            "physical_upload_receipt_sha256": (
                plan.physical_upload_receipt_sha256
            ),
            "physical_upload_plan_id": plan.physical_upload_plan_id,
            "physical_upload_plan_sha256": plan.physical_upload_plan_sha256,
            "physical_upload_permit_id": plan.physical_upload_permit_id,
            "physical_upload_permit_sha256": (
                plan.physical_upload_permit_sha256
            ),
            "physical_stream_id": plan.physical_stream_id,
            "physical_stream_sha256": plan.physical_stream_sha256,
            "input_source_inventory_sha256": (
                plan.input_source_inventory_sha256
            ),
            "preuploaded_object_inventory_sha256": (
                plan.preuploaded_object_inventory_sha256
            ),
            "preuploaded_input_shard_count": (
                plan.preuploaded_input_shard_count
            ),
            "preuploaded_object_count": plan.preuploaded_object_count,
            "preuploaded_byte_count": plan.preuploaded_byte_count,
            "input_objects_reuploaded": False,
        })
    return seed


def _identified_capture(seed: dict[str, object]) -> dict[str, object]:
    digest = hashlib.sha256(_PINNED_CANONICAL_JSON_BYTES(seed)).hexdigest()
    value = dict(seed)
    value["capture_id"] = "arv2-preopen-prereview-capture-" + digest[:24]
    value["capture_sha256"] = digest
    return value


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PreopenControlPreReviewArchive:
    schema: str
    capture_id: str
    capture_sha256: str
    plan_sha256: str
    permit_id: str
    permit_sha256: str
    launch_receipt_sha256: str
    terminal_receipt_sha256: str
    output_package_receipt_sha256: str
    project_id: int
    compile_id: str
    backtest_id: str
    terminal_status: str
    package_key: str
    package_sha256: str
    package_byte_count: int
    output_manifest_key: str
    output_manifest_sha256: str
    output_manifest_byte_count: int
    output_shard_inventory_sha256: str
    output_shard_payload_projection_sha256: str
    universe_terminal_projection_sha256: str
    control_terminal_projection_sha256: str
    q_data_measurement_projection_sha256: str
    output_shard_count: int
    terminal_count: int
    accepted_count: int
    refusal_count: int
    endpoint_allowlist: tuple[str, ...]
    object_store_key_allowlist: tuple[str, ...]
    downloader_object_read_count: int
    complete_preopen_output_object_read_count: int
    independent_review_performed: bool
    acquisition_receipt_minted: bool
    outcome_result_statistics_log_order_accessed: bool
    deployment_order_trading_authorized: bool
    archive_root: Path = dataclasses.field(repr=False)
    _files: tuple[tuple[object, ...], ...] = dataclasses.field(repr=False)
    _root_stat: tuple[int, ...] = dataclasses.field(repr=False)
    _shard_directory_stat: tuple[int, ...] = dataclasses.field(repr=False)
    _index_stat: tuple[int, ...] = dataclasses.field(repr=False)
    review_disposition: str | None = None
    independent_review_complete: bool | None = None
    authorization_basis: str | None = None
    owner_review_waiver_id: str | None = None
    owner_review_waiver_scope: str | None = None
    post_first_formal_backtest_independent_review_required: bool | None = None
    input_upload_disposition: str | None = None
    physical_upload_receipt_id: str | None = None
    physical_upload_receipt_sha256: str | None = None
    physical_upload_plan_id: str | None = None
    physical_upload_plan_sha256: str | None = None
    physical_upload_permit_id: str | None = None
    physical_upload_permit_sha256: str | None = None
    physical_stream_id: str | None = None
    physical_stream_sha256: str | None = None
    input_source_inventory_sha256: str | None = None
    preuploaded_object_inventory_sha256: str | None = None
    preuploaded_input_shard_count: int | None = None
    preuploaded_object_count: int | None = None
    preuploaded_byte_count: int | None = None
    input_objects_reuploaded: bool | None = None


_ARCHIVES: dict[
    int, tuple[weakref.ReferenceType[PreopenControlPreReviewArchive], str, int]
] = {}
_ARCHIVE_LOCK = threading.RLock()
_ARCHIVE_PID = os.getpid()


def _archive_fingerprint(value: PreopenControlPreReviewArchive) -> str:
    public = {
        field.name: getattr(value, field.name)
        for field in dataclasses.fields(value)
        if field.name not in {
            "archive_root", "_files", "_root_stat", "_shard_directory_stat",
            "_index_stat",
        }
    }
    public["endpoint_allowlist"] = list(value.endpoint_allowlist)
    public["object_store_key_allowlist"] = list(value.object_store_key_allowlist)
    return hashlib.sha256(_PINNED_CANONICAL_JSON_BYTES({
        "public": public,
        "archive_root": str(value.archive_root),
        "files": [list(item) for item in value._files],
        "root_stat": list(value._root_stat),
        "shard_directory_stat": list(value._shard_directory_stat),
        "index_stat": list(value._index_stat),
    })).hexdigest()


def _load_file(
    root: Path, record: dict[str, object], *, maximum: int, name: str
) -> bytes:
    relative = record.get("relative_path")
    if (
        type(relative) is not str
        or not relative
        or relative.startswith("/")
        or any(part in ("", ".", "..") for part in relative.split("/"))
    ):
        raise PreopenControlPreReviewError(f"{name} relative path changed")
    try:
        return _PINNED_READ_PRIVATE(
            root / relative,
            expected_sha256=_sha(record.get("sha256"), name + " SHA-256"),
            expected_byte_count=record.get("byte_count"),
            maximum=maximum,
            name=name,
        )
    except Exception as exc:
        raise PreopenControlPreReviewError(f"{name} changed") from exc


def _load_capture(root: Path) -> PreopenControlPreReviewArchive:
    if (
        type(root) is not type(Path())
        or not root.is_absolute()
        or root.name != submission.OUTPUT_ARCHIVE_DIRECTORY_NAME
        or root.parent.resolve(strict=True) != root.parent
    ):
        raise PreopenControlPreReviewError("pre-open prereview archive path changed")
    root_stat = _directory_stat(root, "pre-open prereview archive")
    shard_directory = root / submission.OUTPUT_ARCHIVE_SHARD_DIRECTORY
    shard_stat = _directory_stat(
        shard_directory, "pre-open prereview shard directory"
    )
    index_path = root / CAPTURE_INDEX_NAME
    index_payload = _read_unbound_private_file(
        index_path,
        MAX_CAPTURE_INDEX_BYTES,
        "pre-open prereview capture index",
    )
    index = _strict_object(index_payload, "pre-open prereview capture index")
    expected_fields = {
        field.name
        for field in dataclasses.fields(PreopenControlPreReviewArchive)
        if field.name
        not in {
            "archive_root", "_files", "_root_stat", "_shard_directory_stat",
            "_index_stat",
        }
    } - OWNER_WAIVER_CAPTURE_FIELDS
    expected_fields.add("files")
    has_owner_waiver = set(index) == (
        expected_fields | OWNER_WAIVER_CAPTURE_FIELDS
    )
    if set(index) != expected_fields and not has_owner_waiver:
        raise PreopenControlPreReviewError("capture index fields changed")
    _validate_capture_scalar_types(index)
    if has_owner_waiver:
        _validate_owner_waiver_capture(index)
    seed = dict(index)
    declared_id = seed.pop("capture_id", None)
    declared_sha = seed.pop("capture_sha256", None)
    seed["capture_id"] = None
    seed["capture_sha256"] = None
    digest = hashlib.sha256(_PINNED_CANONICAL_JSON_BYTES(seed)).hexdigest()
    if (
        index.get("schema") != CAPTURE_SCHEMA
        or declared_sha != digest
        or declared_id != "arv2-preopen-prereview-capture-" + digest[:24]
        or index.get("terminal_status") != "Completed."
        or index.get("endpoint_allowlist") != list(OBJECT_ENDPOINT_ALLOWLIST)
        or index.get("independent_review_performed") is not False
        or index.get("acquisition_receipt_minted") is not False
        or index.get("outcome_result_statistics_log_order_accessed") is not False
        or index.get("deployment_order_trading_authorized") is not False
    ):
        raise PreopenControlPreReviewError("capture identity or gates changed")
    files = index.get("files")
    if type(files) is not list or not files:
        raise PreopenControlPreReviewError("capture file inventory changed")
    expected_file_fields = {
        "role", "ordinal", "relative_path", "object_store_key", "sha256",
        "byte_count",
    }
    if any(type(item) is not dict or set(item) != expected_file_fields for item in files):
        raise PreopenControlPreReviewError("capture file descriptor changed")
    roles = [item["role"] for item in files]
    shard_records = [item for item in files if item["role"] == "terminal_shard"]
    if (
        roles[:2] != ["terminal_package", "output_manifest"]
        or roles[-2:] != ["summary_receipt", "qc_execution_receipt"]
        or len(shard_records) != index.get("output_shard_count")
        or [item["ordinal"] for item in shard_records]
        != list(range(len(shard_records)))
    ):
        raise PreopenControlPreReviewError("capture file order changed")
    _validate_capture_file_record(
        files[0], role="terminal_package", ordinal=None
    )
    _validate_capture_file_record(
        files[1], role="output_manifest", ordinal=None
    )
    for ordinal, record in enumerate(shard_records):
        _validate_capture_file_record(
            record, role="terminal_shard", ordinal=ordinal
        )
    _validate_capture_file_record(
        files[-2], role="summary_receipt", ordinal=None
    )
    _validate_capture_file_record(
        files[-1], role="qc_execution_receipt", ordinal=None
    )
    if (
        files[0]["relative_path"] != TERMINAL_PACKAGE_NAME
        or files[0]["object_store_key"] != index.get("package_key")
        or files[0]["ordinal"] is not None
        or files[1]["relative_path"] != submission.OUTPUT_ARCHIVE_MANIFEST_NAME
        or files[1]["object_store_key"] != index.get("output_manifest_key")
        or files[1]["ordinal"] is not None
        or files[-2]["relative_path"] != SUMMARY_RECEIPT_NAME
        or files[-2]["object_store_key"] is not None
        or files[-2]["ordinal"] is not None
        or files[-1]["relative_path"] != QC_EXECUTION_RECEIPT_NAME
        or files[-1]["object_store_key"] is not None
        or files[-1]["ordinal"] is not None
    ):
        raise PreopenControlPreReviewError("capture named file binding changed")
    package_bytes = _load_file(
        root, files[0], maximum=submission.MAX_PACKAGE_BYTES,
        name="captured terminal package",
    )
    manifest_bytes = _load_file(
        root, files[1], maximum=submission.MAX_OUTPUT_MANIFEST_BYTES,
        name="captured output manifest",
    )
    package, manifest = _validate_package_manifest(
        package_bytes=package_bytes, manifest_bytes=manifest_bytes
    )
    descriptors = manifest["output_shards"]
    if len(descriptors) != len(shard_records):
        raise PreopenControlPreReviewError("capture shard census changed")
    for descriptor, file_record in zip(descriptors, shard_records, strict=True):
        key = _output_descriptor_key(descriptor)
        expected_relative = (
            submission.OUTPUT_ARCHIVE_SHARD_DIRECTORY
            + f"/{file_record['ordinal']:04d}-{descriptor['compressed_sha256']}.jsonl.gz"
        )
        if (
            file_record["object_store_key"] != key
            or file_record["relative_path"] != expected_relative
            or file_record["sha256"] != descriptor["compressed_sha256"]
            or file_record["byte_count"] != descriptor["compressed_byte_count"]
        ):
            raise PreopenControlPreReviewError("capture shard descriptor changed")
    def payloads() -> Iterator[bytes]:
        for file_record in shard_records:
            yield _load_file(
                root,
                file_record,
                maximum=submission.MAX_OUTPUT_SHARD_READ_BYTES,
                name=f"captured terminal shard {file_record['ordinal']}",
            )

    try:
        projection, totals = _PINNED_VALIDATE_PAYLOADS(
            manifest, payloads()
        )
    except Exception as exc:
        raise PreopenControlPreReviewError(
            "captured terminal shard projection changed"
        ) from exc
    if projection != index.get("output_shard_payload_projection_sha256"):
        raise PreopenControlPreReviewError("capture payload projection changed")
    if totals != {
        "terminal_count": index.get("terminal_count"),
        "accepted_count": index.get("accepted_count"),
        "refusal_count": index.get("refusal_count"),
    }:
        raise PreopenControlPreReviewError("capture terminal census changed")
    summary_record, execution_record = files[-2:]
    summary = _load_file(
        root, summary_record, maximum=MAX_SUPPORTING_RECEIPT_BYTES,
        name="captured summary receipt",
    )
    if summary != _summary_bytes(manifest_bytes, manifest):
        raise PreopenControlPreReviewError("captured summary receipt changed")
    execution = _load_file(
        root, execution_record, maximum=MAX_SUPPORTING_RECEIPT_BYTES,
        name="captured QC execution receipt",
    )
    expected_execution = _PINNED_RENDER_EXECUTION(
        project_id=str(index["project_id"]),
        compile_id=index["compile_id"],
        backtest_id=index["backtest_id"],
        input_manifest_sha256=manifest["input_manifest"]["artifact_sha256"],
        project_source_set_sha256=manifest["project_source_set_sha256"],
        output_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        summary_receipt_sha256=hashlib.sha256(summary).hexdigest(),
    )
    if execution != expected_execution:
        raise PreopenControlPreReviewError("captured QC execution receipt changed")
    allowed_keys = [
        index["output_manifest_key"],
        *[descriptor["object_store_key"] for descriptor in descriptors],
    ]
    if (
        index.get("object_store_key_allowlist") != allowed_keys
        or index.get("downloader_object_read_count") != len(allowed_keys)
        or index.get("complete_preopen_output_object_read_count")
        != len(allowed_keys) + 1
        or index.get("package_sha256") != hashlib.sha256(package_bytes).hexdigest()
        or index.get("package_byte_count") != len(package_bytes)
        or index.get("output_manifest_sha256")
        != hashlib.sha256(manifest_bytes).hexdigest()
        or index.get("output_manifest_byte_count") != len(manifest_bytes)
        or package["output_manifest"]["object_store_key"]
        != index.get("output_manifest_key")
    ):
        raise PreopenControlPreReviewError("capture lineage changed")
    expected_names = {
        CAPTURE_INDEX_NAME,
        TERMINAL_PACKAGE_NAME,
        submission.OUTPUT_ARCHIVE_MANIFEST_NAME,
        SUMMARY_RECEIPT_NAME,
        QC_EXECUTION_RECEIPT_NAME,
        submission.OUTPUT_ARCHIVE_SHARD_DIRECTORY,
    }
    if (
        {item.name for item in root.iterdir()} != expected_names
        or {item.name for item in shard_directory.iterdir()}
        != {Path(item["relative_path"]).name for item in shard_records}
    ):
        raise PreopenControlPreReviewError("capture filesystem inventory changed")
    packed_files = tuple(
        (
            item["role"], item["ordinal"], item["relative_path"],
            item["object_store_key"], item["sha256"], item["byte_count"],
            _private_file_stat(
                root / item["relative_path"],
                f"captured {item['role']} file",
            ),
        )
        for item in files
    )
    public = {name: item for name, item in index.items() if name != "files"}
    public["endpoint_allowlist"] = tuple(public["endpoint_allowlist"])
    public["object_store_key_allowlist"] = tuple(
        public["object_store_key_allowlist"]
    )
    value = PreopenControlPreReviewArchive(
        **public,
        archive_root=root,
        _files=packed_files,
        _root_stat=root_stat,
        _shard_directory_stat=shard_stat,
        _index_stat=_private_file_stat(
            index_path, "pre-open prereview capture index"
        ),
    )
    reference = weakref.ref(
        value, lambda _ref, key=id(value): _ARCHIVES.pop(key, None)
    )
    with _ARCHIVE_LOCK:
        _ARCHIVES[id(value)] = (reference, _archive_fingerprint(value), os.getpid())
    return require_preopen_control_prereview_archive(value)


def load_preopen_control_prereview_archive(
    archive_root: Path,
) -> PreopenControlPreReviewArchive:
    """Load inert review material without minting an acquisition authority."""

    _require_review_dependency_authority()
    if type(archive_root) is not type(Path()):
        raise PreopenControlPreReviewError(
            "pre-open prereview archive path changed"
        )
    try:
        root = archive_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PreopenControlPreReviewError(
            "pre-open prereview archive is unavailable"
        ) from exc
    if root != archive_root:
        raise PreopenControlPreReviewError(
            "pre-open prereview archive must be its canonical absolute path"
        )
    return _load_capture(root)


def require_preopen_control_prereview_archive(
    value: PreopenControlPreReviewArchive,
) -> PreopenControlPreReviewArchive:
    if type(value) is not PreopenControlPreReviewArchive:
        raise PreopenControlPreReviewError("pre-open prereview archive type changed")
    with _ARCHIVE_LOCK:
        registered = _ARCHIVES.get(id(value))
    if (
        os.getpid() != _ARCHIVE_PID
        or registered is None
        or registered[0]() is not value
        or registered[2] != os.getpid()
    ):
        raise PreopenControlPreReviewError(
            "pre-open prereview archive authority changed"
        )
    if (
        type(value.endpoint_allowlist) is not tuple
        or type(value.object_store_key_allowlist) is not tuple
        or type(value.archive_root) is not type(Path())
        or type(value._files) is not tuple
        or any(type(item) is not tuple for item in value._files)
        or type(value._root_stat) is not tuple
        or type(value._shard_directory_stat) is not tuple
        or type(value._index_stat) is not tuple
    ):
        raise PreopenControlPreReviewError(
            "pre-open prereview archive container types changed"
        )
    try:
        fingerprint = _archive_fingerprint(value)
    except Exception as exc:
        raise PreopenControlPreReviewError(
            "pre-open prereview archive scalar types changed"
        ) from exc
    if (
        registered[1] != fingerprint
        or _directory_stat(value.archive_root, "pre-open prereview archive")
        != value._root_stat
        or _directory_stat(
            value.archive_root / submission.OUTPUT_ARCHIVE_SHARD_DIRECTORY,
            "pre-open prereview shard directory",
        )
        != value._shard_directory_stat
        or _private_file_stat(
            value.archive_root / CAPTURE_INDEX_NAME,
            "pre-open prereview capture index",
        )
        != value._index_stat
        or any(
            _private_file_stat(
                value.archive_root / item[2], f"captured {item[0]} file"
            )
            != item[6]
            for item in value._files
        )
    ):
        raise PreopenControlPreReviewError(
            "pre-open prereview archive authority changed"
        )
    return value


def _record_for_role(
    value: PreopenControlPreReviewArchive, role: str
) -> tuple[object, ...]:
    selected = [item for item in value._files if item[0] == role]
    if len(selected) != 1:
        raise PreopenControlPreReviewError(f"captured {role} inventory changed")
    return selected[0]


def _read_record(value, record, maximum, name):
    return _PINNED_READ_PRIVATE(
        value.archive_root / record[2],
        expected_sha256=record[4],
        expected_byte_count=record[5],
        maximum=maximum,
        name=name,
    )


def read_preopen_control_prereview_manifest_bytes(
    value: PreopenControlPreReviewArchive,
) -> bytes:
    value = require_preopen_control_prereview_archive(value)
    return _read_record(
        value,
        _record_for_role(value, "output_manifest"),
        submission.MAX_OUTPUT_MANIFEST_BYTES,
        "captured output manifest",
    )


def iter_preopen_control_prereview_output_shard_payloads(
    value: PreopenControlPreReviewArchive,
) -> Iterator[bytes]:
    value = require_preopen_control_prereview_archive(value)
    records = [item for item in value._files if item[0] == "terminal_shard"]
    for ordinal, record in enumerate(records):
        require_preopen_control_prereview_archive(value)
        if record[1] != ordinal:
            raise PreopenControlPreReviewError("captured shard order changed")
        yield _read_record(
            value,
            record,
            submission.MAX_OUTPUT_SHARD_READ_BYTES,
            f"captured terminal shard {ordinal}",
        )


def preopen_control_prereview_shard_paths(
    value: PreopenControlPreReviewArchive,
) -> tuple[Path, ...]:
    value = require_preopen_control_prereview_archive(value)
    return tuple(
        value.archive_root / item[2]
        for item in value._files
        if item[0] == "terminal_shard"
    )


def read_preopen_control_prereview_supporting_receipts(
    value: PreopenControlPreReviewArchive,
) -> tuple[bytes, bytes]:
    """Return ``(QC execution receipt, summary receipt)`` for review loading."""

    value = require_preopen_control_prereview_archive(value)
    execution = _read_record(
        value,
        _record_for_role(value, "qc_execution_receipt"),
        MAX_SUPPORTING_RECEIPT_BYTES,
        "captured QC execution receipt",
    )
    summary = _read_record(
        value,
        _record_for_role(value, "summary_receipt"),
        MAX_SUPPORTING_RECEIPT_BYTES,
        "captured summary receipt",
    )
    return execution, summary


def _require_download_authority(
    *, plan, permit, launch, terminal, package,
    owner_signature: OwnerSignatureAuthority | None,
):
    _require_dependency_authority()
    _PINNED_REQUIRE_OWNER(
        owner_signature,
        _PINNED_RENDER_OWNER_AUTHORITY(plan),
    )
    if type(plan) is submission.PhysicalPreopenQcSubmissionPlan:
        closure = _PINNED_BUILD_PHYSICAL_HOST_CLOSURE()
        _PINNED_VERIFY_PHYSICAL_HOST_CLOSURE(closure)
    else:
        closure = _PINNED_BUILD_HOST_CLOSURE()
        _PINNED_VERIFY_HOST_CLOSURE(closure)
    _PINNED_REQUIRE_PLAN(plan)
    _PINNED_REQUIRE_PERMIT(permit, plan)
    _PINNED_REQUIRE_TERMINAL(terminal, plan, permit, launch)
    package = _PINNED_REQUIRE_PACKAGE(
        package, plan=plan, permit=permit, launch=launch, terminal=terminal
    )
    if terminal.terminal_status != "Completed.":
        raise PreopenControlPreReviewError(
            "completed pre-open terminal status is required"
        )
    if plan.output_archive_root is None:
        raise PreopenControlPreReviewError(
            "owner-signed prereview archive root is required"
        )
    return package


def _download_preopen_control_outputs_for_review_impl(
    *, plan: (
        submission.PreopenQcSubmissionPlan
        | submission.PhysicalPreopenQcSubmissionPlan
    ),
    permit: submission.PreopenQcSubmissionPermit,
    launch: submission.PreopenQcLaunchReceipt,
    terminal: submission.PreopenQcTerminalStatusReceipt,
    package: submission.PreopenQcOutputPackageReceipt,
    client: FormalQcTransport,
    owner_signature: OwnerSignatureAuthority | None,
    _transport_capability_minter,
) -> PreopenControlPreReviewArchive:
    """Download exact output objects once without requiring their later review."""

    package = _require_download_authority(
        plan=plan,
        permit=permit,
        launch=launch,
        terminal=terminal,
        package=package,
        owner_signature=owner_signature,
    )
    try:
        root, shard_directory = _PINNED_PREPARE_ROOT(
            plan, permit_id=permit.permit_id
        )
        _PINNED_WRITE_PRIVATE(
            root / TERMINAL_PACKAGE_NAME,
            package.package_bytes,
            "pre-open terminal package",
        )
        manifest_key = package.output_manifest_key
        manifest_capability = _transport_capability_minter(
            transport=client,
            scope="preopen_output_read",
            binding_record={
                "schema": "arv2-preopen-prereview-manifest-read-capability-v1",
                "plan_sha256": plan.plan_sha256,
                "permit_sha256": permit.permit_sha256,
                "launch_receipt_sha256": launch.receipt_sha256,
                "terminal_receipt_sha256": terminal.receipt_sha256,
                "output_package_receipt_sha256": package.receipt_sha256,
                "endpoint_allowlist": list(OBJECT_ENDPOINT_ALLOWLIST),
                "object_store_keys": [manifest_key],
            },
            call_budget={"object/read": 1},
        )
        response = _PINNED_TRANSPORT_CALL(
            client,
            manifest_capability,
            "_read_object_bounded",
            plan.organization_id,
            manifest_key,
        )
        manifest_bytes = _PINNED_OBJECT_PAYLOAD(
            response,
            key=manifest_key,
            maximum=plan.maximum_output_manifest_bytes,
            name="pre-open output manifest",
        )
        if (
            len(manifest_bytes) != package.output_manifest_byte_count
            or hashlib.sha256(manifest_bytes).hexdigest()
            != package.output_manifest_sha256
        ):
            raise PreopenControlPreReviewError(
                "pre-open output manifest identity changed"
            )
        _package_record, manifest = _validate_package_manifest(
            package_bytes=package.package_bytes,
            manifest_bytes=manifest_bytes,
        )
        descriptors = manifest["output_shards"]
        if (
            type(descriptors) is not list
            or not 1 <= len(descriptors) <= plan.maximum_output_shard_reads
            or hashlib.sha256(_PINNED_CANONICAL_JSON_BYTES(descriptors)).hexdigest()
            != package.output_shard_inventory_sha256
        ):
            raise PreopenControlPreReviewError(
                "pre-open output shard inventory changed"
            )
        shard_keys = [_output_descriptor_key(item) for item in descriptors]
        if len(set(shard_keys)) != len(shard_keys):
            raise PreopenControlPreReviewError(
                "pre-open output shard key repeats"
            )
        shard_capability = _transport_capability_minter(
            transport=client,
            scope="preopen_output_read",
            binding_record={
                "schema": "arv2-preopen-prereview-shard-read-capability-v1",
                "plan_sha256": plan.plan_sha256,
                "permit_sha256": permit.permit_sha256,
                "output_manifest_sha256": package.output_manifest_sha256,
                "output_shard_inventory_sha256": (
                    package.output_shard_inventory_sha256
                ),
                "endpoint_allowlist": list(OBJECT_ENDPOINT_ALLOWLIST),
                "object_store_keys": shard_keys,
            },
            call_budget={"object/read": len(shard_keys)},
        )
        files = [
            _file_record(
                role="terminal_package",
                ordinal=None,
                relative_path=TERMINAL_PACKAGE_NAME,
                object_store_key=package.package_key,
                payload=package.package_bytes,
            )
        ]
        payload_paths: list[Path] = []
        for ordinal, (descriptor, key) in enumerate(
            zip(descriptors, shard_keys, strict=True)
        ):
            expected_size = descriptor["compressed_byte_count"]
            if (
                type(expected_size) is not int
                or not 0 < expected_size <= plan.maximum_output_shard_read_bytes
            ):
                raise PreopenControlPreReviewError(
                    "pre-open output shard exceeds signed read bound"
                )
            response = _PINNED_TRANSPORT_CALL(
                client,
                shard_capability,
                "_read_object_bounded",
                plan.organization_id,
                key,
            )
            payload = _PINNED_OBJECT_PAYLOAD(
                response,
                key=key,
                maximum=plan.maximum_output_shard_read_bytes,
                name=f"pre-open output shard {ordinal}",
            )
            if (
                len(payload) != expected_size
                or hashlib.sha256(payload).hexdigest()
                != descriptor["compressed_sha256"]
            ):
                raise PreopenControlPreReviewError(
                    "pre-open output shard identity changed"
                )
            relative = (
                submission.OUTPUT_ARCHIVE_SHARD_DIRECTORY
                + f"/{ordinal:04d}-{descriptor['compressed_sha256']}.jsonl.gz"
            )
            path = root / relative
            _PINNED_WRITE_PRIVATE(
                path, payload, f"pre-open output shard {ordinal}"
            )
            payload_paths.append(path)
            files.append(_file_record(
                role="terminal_shard",
                ordinal=ordinal,
                relative_path=relative,
                object_store_key=key,
                payload=payload,
            ))
            del payload

        def local_payloads():
            for ordinal, (descriptor, path) in enumerate(
                zip(descriptors, payload_paths, strict=True)
            ):
                yield _PINNED_READ_PRIVATE(
                    path,
                    expected_sha256=descriptor["compressed_sha256"],
                    expected_byte_count=descriptor["compressed_byte_count"],
                    maximum=plan.maximum_output_shard_read_bytes,
                    name=f"archived pre-open output shard {ordinal}",
                )

        projection, totals = _PINNED_VALIDATE_PAYLOADS(
            manifest, local_payloads()
        )
        if (
            totals
            != {
                "terminal_count": package.terminal_count,
                "accepted_count": package.accepted_count,
                "refusal_count": package.refusal_count,
            }
        ):
            raise PreopenControlPreReviewError(
                "pre-open output terminal census changed"
            )
        _PINNED_WRITE_PRIVATE(
            root / submission.OUTPUT_ARCHIVE_MANIFEST_NAME,
            manifest_bytes,
            "pre-open output manifest",
        )
        files.insert(1, _file_record(
            role="output_manifest",
            ordinal=None,
            relative_path=submission.OUTPUT_ARCHIVE_MANIFEST_NAME,
            object_store_key=manifest_key,
            payload=manifest_bytes,
        ))
        summary_bytes = _summary_bytes(manifest_bytes, manifest)
        _PINNED_WRITE_PRIVATE(
            root / SUMMARY_RECEIPT_NAME,
            summary_bytes,
            "pre-open summary receipt",
        )
        files.append(_file_record(
            role="summary_receipt",
            ordinal=None,
            relative_path=SUMMARY_RECEIPT_NAME,
            object_store_key=None,
            payload=summary_bytes,
        ))
        execution_bytes = _PINNED_RENDER_EXECUTION(
            project_id=str(launch.project_id),
            compile_id=launch.compile_id,
            backtest_id=launch.backtest_id,
            input_manifest_sha256=manifest["input_manifest"]["artifact_sha256"],
            project_source_set_sha256=manifest["project_source_set_sha256"],
            output_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            summary_receipt_sha256=hashlib.sha256(summary_bytes).hexdigest(),
        )
        _PINNED_WRITE_PRIVATE(
            root / QC_EXECUTION_RECEIPT_NAME,
            execution_bytes,
            "pre-open QC execution receipt",
        )
        files.append(_file_record(
            role="qc_execution_receipt",
            ordinal=None,
            relative_path=QC_EXECUTION_RECEIPT_NAME,
            object_store_key=None,
            payload=execution_bytes,
        ))
        seed = _capture_seed(
            plan=plan,
            permit=permit,
            launch=launch,
            terminal=terminal,
            package=package,
            manifest=manifest,
            files=files,
        )
        seed["output_shard_payload_projection_sha256"] = projection
        capture = _identified_capture(seed)
        index_bytes = _PINNED_CANONICAL_JSON_BYTES(capture)
        if len(index_bytes) > MAX_CAPTURE_INDEX_BYTES:
            raise PreopenControlPreReviewError(
                "pre-open prereview capture index exceeds bound"
            )
        _PINNED_WRITE_PRIVATE(
            root / CAPTURE_INDEX_NAME,
            index_bytes,
            "pre-open prereview capture index",
        )
        _PINNED_FSYNC_DIRECTORY(
            shard_directory, "pre-open prereview shard directory"
        )
        _PINNED_FSYNC_DIRECTORY(root, "pre-open prereview archive")
        _PINNED_FSYNC_DIRECTORY(root.parent, "pre-open prereview archive parent")
        return _load_capture(root)
    except PreopenControlPreReviewLocked:
        raise
    except Exception as exc:
        raise PreopenControlPreReviewLocked(
            permit.permit_id, type(exc).__name__
        ) from exc


def _bind_download_action(minter, implementation):
    def download_preopen_control_outputs_for_review(
        *, plan: (
            submission.PreopenQcSubmissionPlan
            | submission.PhysicalPreopenQcSubmissionPlan
        ),
        permit: submission.PreopenQcSubmissionPermit,
        launch: submission.PreopenQcLaunchReceipt,
        terminal: submission.PreopenQcTerminalStatusReceipt,
        package: submission.PreopenQcOutputPackageReceipt,
        client: FormalQcTransport,
        owner_signature: OwnerSignatureAuthority | None,
    ) -> PreopenControlPreReviewArchive:
        return implementation(
            plan=plan,
            permit=permit,
            launch=launch,
            terminal=terminal,
            package=package,
            client=client,
            owner_signature=owner_signature,
            _transport_capability_minter=minter,
        )

    return download_preopen_control_outputs_for_review


(
    _transport_capability_minter,
    _seal_transport_capability_callers,
) = formal._claim_preopen_prereview_transport_capability_minter()
download_preopen_control_outputs_for_review = _bind_download_action(
    _transport_capability_minter,
    _download_preopen_control_outputs_for_review_impl,
)
_seal_transport_capability_callers((
    (
        "preopen_output_read",
        ((
            _download_preopen_control_outputs_for_review_impl,
            download_preopen_control_outputs_for_review,
        ),),
    ),
))
del _transport_capability_minter
del _seal_transport_capability_callers
del _download_preopen_control_outputs_for_review_impl
del _bind_download_action


__all__ = (
    "CAPTURE_INDEX_NAME",
    "CAPTURE_SCHEMA",
    "OBJECT_ENDPOINT_ALLOWLIST",
    "PreopenControlPreReviewArchive",
    "PreopenControlPreReviewError",
    "PreopenControlPreReviewLocked",
    "download_preopen_control_outputs_for_review",
    "iter_preopen_control_prereview_output_shard_payloads",
    "load_preopen_control_prereview_archive",
    "preopen_control_prereview_shard_paths",
    "read_preopen_control_prereview_manifest_bytes",
    "read_preopen_control_prereview_supporting_receipts",
    "require_preopen_control_prereview_archive",
)
