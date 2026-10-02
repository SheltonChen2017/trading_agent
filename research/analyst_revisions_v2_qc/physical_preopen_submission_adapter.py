"""Bounded physical-input upload for the ARV2 pre-open QC stage.

The legacy pre-open submission plan retains every compressed input payload.
The reviewed historical contract permits as much as one GiB across 20,000
shards, so that representation is fixture-compatible but not production-safe.
This adapter retains only authenticated descriptors and rereads exactly one
physical shard for each content-addressed Object Store write.  The activated
manifest is published last and no project, backtest, result, log, order, or
deployment endpoint is available here.
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

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import formal_submission_adapter as formal
from research.analyst_revisions_v2_qc import historical_preopen_input_adapter as inputs
from research.analyst_revisions_v2_qc import preopen_control_submission_adapter as submission
from research.analyst_revisions_v2_qc.formal_qc_transport import (
    FormalQcTransport,
    MAX_OBJECT_BYTES,
)
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
)
from research.analyst_revisions_v2_qc.preopen_control_stage import (
    MAX_COMPRESSED_SHARD_BYTES,
    MAX_RETAINED_INPUT_COMPRESSED_BYTES,
    PreopenControlQcProjection,
    PreopenControlRunAuthority,
    PreopenInputShard,
)
from scripts import build_arv2_historical_preopen_bridge as historical


class PhysicalPreopenSubmissionError(ValueError):
    """The physical upload plan, permit, or receipt is invalid."""


class PhysicalPreopenSubmissionLocked(RuntimeError):
    """The one-use upload permit was spent and external state is ambiguous."""

    def __init__(self, permit_id: str, detail: str) -> None:
        super().__init__(
            "physical_preopen_upload: "
            + detail
            + "; one-use upload permit remains consumed"
        )
        self.permit_id = permit_id


PLAN_SCHEMA = "arv2-physical-preopen-input-upload-plan-v1"
PERMIT_SCHEMA = "arv2-physical-preopen-input-upload-permit-v1"
RECEIPT_SCHEMA = "arv2-physical-preopen-input-upload-receipt-v1"
EXECUTION_AUTHORITY_SCHEMA = (
    "arv2-physical-preopen-input-upload-execution-authority-v1"
)
PERMIT_FILENAME = "arv2-physical-preopen-input-upload-permit-v1.json"
MAX_PERMIT_BYTES = 64 * 1024
MAX_INPUT_SHARD_COUNT = historical.MAX_ARCHIVE_SHARD_COUNT
MAX_INPUT_SHARD_BYTES = min(MAX_COMPRESSED_SHARD_BYTES, MAX_OBJECT_BYTES)
MAX_TOTAL_INPUT_BYTES = MAX_RETAINED_INPUT_COMPRESSED_BYTES
ENDPOINT_ALLOWLIST = ("authenticate", "object/set", "object/properties")
UPLOAD_ACTIONS = (
    "authenticate",
    "object/set_each_exact_content_addressed_physical_input_once",
    "object/properties_verify_each_exact_input",
    "object/set_exact_activated_manifest_last_once",
)

_PINNED_CANONICAL = canonical_json_bytes
_PINNED_STREAM_CLASS = inputs.AuthenticatedHistoricalPreopenInputStream
_PINNED_REQUIRE_STREAM = (
    inputs.require_authenticated_historical_preopen_input_stream
)
_PINNED_ITER_STREAM = inputs.iter_authenticated_historical_preopen_input_shards
_PINNED_SHARD_CLASS = PreopenInputShard
_PINNED_SHARD_DESCRIPTOR = PreopenInputShard.descriptor
_PINNED_REBUILD_PROJECTION = submission._rebuild_projection
_PINNED_SAFE = submission._safe
_PINNED_UTC = submission._utc
_PINNED_BUILD_HOST_CLOSURE = submission.build_preopen_qc_host_closure_binding
_PINNED_VERIFY_HOST_CLOSURE = submission.verify_preopen_qc_host_closure_live
_PINNED_REQUIRE_OWNER = submission._require_external_execution_trust_root
_PINNED_PREOPEN_CALL = submission._preopen_transport_call
_PINNED_FSYNC_DIRECTORY = submission._fsync_private_directory
_PINNED_READ_PRIVATE = submission._read_private_archive_file
_PINNED_BUILD_QC_PLAN = (
    submission.build_preopen_qc_submission_plan_from_physical_upload
)
_PINNED_REQUIRE_QC_PLAN = submission.require_preopen_qc_physical_submission_plan
_PINNED_RENDER_QC_AUTHORITY = (
    submission.render_preopen_qc_execution_authority_candidate
)
_PINNED_EXECUTE_QC = submission.execute_preopen_qc_submission_once
_PINNED_OWNER_REVIEW_WAIVER_ID = submission.OWNER_REVIEW_WAIVER_ID
_PINNED_OWNER_REVIEW_WAIVER_SCOPE = submission.OWNER_REVIEW_WAIVER_SCOPE
_PINNED_OWNER_REVIEW_WAIVER_BASIS = submission.OWNER_REVIEW_WAIVER_BASIS
_PINNED_OWNER_REVIEW_WAIVER_DISPOSITION = (
    submission.OWNER_REVIEW_WAIVER_DISPOSITION
)
_PINNED_PHYSICAL_INPUT_UPLOAD_DISPOSITION = (
    submission.PHYSICAL_INPUT_UPLOAD_DISPOSITION
)
_PINNED_CONCRETE_TRANSPORT = formal._require_concrete_transport
_PINNED_METADATA_MATCHES = formal._object_metadata_matches
_PINNED_MAX_SHARD_COUNT = historical.MAX_ARCHIVE_SHARD_COUNT
_PINNED_MAX_SHARD_BYTES = MAX_COMPRESSED_SHARD_BYTES
_PINNED_MAX_OBJECT_BYTES = MAX_OBJECT_BYTES
_PINNED_MAX_TOTAL_BYTES = MAX_RETAINED_INPUT_COMPRESSED_BYTES
_PINNED_INPUT_SHARD_COUNT = MAX_INPUT_SHARD_COUNT
_PINNED_INPUT_SHARD_BYTES = MAX_INPUT_SHARD_BYTES
_PINNED_TOTAL_INPUT_BYTES = MAX_TOTAL_INPUT_BYTES


def _require_dependencies() -> None:
    expected = (
        (inputs, "AuthenticatedHistoricalPreopenInputStream", _PINNED_STREAM_CLASS),
        (
            inputs,
            "require_authenticated_historical_preopen_input_stream",
            _PINNED_REQUIRE_STREAM,
        ),
        (
            inputs,
            "iter_authenticated_historical_preopen_input_shards",
            _PINNED_ITER_STREAM,
        ),
        (submission, "_rebuild_projection", _PINNED_REBUILD_PROJECTION),
        (submission, "_safe", _PINNED_SAFE),
        (submission, "_utc", _PINNED_UTC),
        (
            submission,
            "build_preopen_qc_host_closure_binding",
            _PINNED_BUILD_HOST_CLOSURE,
        ),
        (
            submission,
            "verify_preopen_qc_host_closure_live",
            _PINNED_VERIFY_HOST_CLOSURE,
        ),
        (
            submission,
            "_require_external_execution_trust_root",
            _PINNED_REQUIRE_OWNER,
        ),
        (submission, "_preopen_transport_call", _PINNED_PREOPEN_CALL),
        (submission, "_fsync_private_directory", _PINNED_FSYNC_DIRECTORY),
        (submission, "_read_private_archive_file", _PINNED_READ_PRIVATE),
        (
            submission,
            "build_preopen_qc_submission_plan_from_physical_upload",
            _PINNED_BUILD_QC_PLAN,
        ),
        (
            submission,
            "require_preopen_qc_physical_submission_plan",
            _PINNED_REQUIRE_QC_PLAN,
        ),
        (
            submission,
            "render_preopen_qc_execution_authority_candidate",
            _PINNED_RENDER_QC_AUTHORITY,
        ),
        (
            submission,
            "execute_preopen_qc_submission_once",
            _PINNED_EXECUTE_QC,
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
        (formal, "_require_concrete_transport", _PINNED_CONCRETE_TRANSPORT),
        (formal, "_object_metadata_matches", _PINNED_METADATA_MATCHES),
    )
    if (
        canonical_json_bytes is not _PINNED_CANONICAL
        or PreopenInputShard is not _PINNED_SHARD_CLASS
        or PreopenInputShard.descriptor is not _PINNED_SHARD_DESCRIPTOR
        or historical.MAX_ARCHIVE_SHARD_COUNT is not _PINNED_MAX_SHARD_COUNT
        or MAX_COMPRESSED_SHARD_BYTES is not _PINNED_MAX_SHARD_BYTES
        or MAX_OBJECT_BYTES is not _PINNED_MAX_OBJECT_BYTES
        or MAX_RETAINED_INPUT_COMPRESSED_BYTES
        is not _PINNED_MAX_TOTAL_BYTES
        or MAX_INPUT_SHARD_COUNT is not _PINNED_INPUT_SHARD_COUNT
        or MAX_INPUT_SHARD_BYTES is not _PINNED_INPUT_SHARD_BYTES
        or MAX_TOTAL_INPUT_BYTES is not _PINNED_TOTAL_INPUT_BYTES
        or any(
            getattr(namespace, name, None) is not value
            for namespace, name, value in expected
        )
    ):
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload dependency authority changed"
        )


def _canonical(value: object) -> bytes:
    try:
        return _PINNED_CANONICAL(value)
    except (TypeError, ValueError, RecursionError) as exc:
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload value is not canonical"
        ) from exc


def _strict_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload:
        raise PhysicalPreopenSubmissionError(f"{name} is not exact bytes")

    def pairs(items):
        result = {}
        for key, value in items:
            if type(key) is not str or key in result:
                raise PhysicalPreopenSubmissionError(
                    f"{name} has duplicate or non-string keys"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=lambda _value: (_ for _ in ()).throw(
                PhysicalPreopenSubmissionError(f"{name} contains a float")
            ),
            parse_constant=lambda _value: (_ for _ in ()).throw(
                PhysicalPreopenSubmissionError(
                    f"{name} contains a non-finite value"
                )
            ),
        )
    except PhysicalPreopenSubmissionError:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise PhysicalPreopenSubmissionError(f"{name} is not strict JSON") from exc
    if type(value) is not dict or _canonical(value) != payload:
        raise PhysicalPreopenSubmissionError(f"{name} is not canonical JSON")
    return value


def _sha(value: object, name: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PhysicalPreopenSubmissionError(f"{name} is not SHA-256")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalPreopenUploadObject:
    role: str
    object_store_key: str
    content_sha256: str
    content_md5: str
    byte_count: int

    def to_record(self) -> dict[str, object]:
        return {
            "role": self.role,
            "object_store_key": self.object_store_key,
            "content_sha256": self.content_sha256,
            "content_md5": self.content_md5,
            "byte_count": self.byte_count,
        }


def _upload_object(
    *, role: str, key: str, sha256: str, payload: bytes,
) -> PhysicalPreopenUploadObject:
    if (
        type(role) is not str
        or not role
        or type(key) is not str
        or not key
        or type(payload) is not bytes
        or not 0 < len(payload) <= _PINNED_MAX_OBJECT_BYTES
        or hashlib.sha256(payload).hexdigest() != _sha(sha256, role + " hash")
    ):
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload object changed"
        )
    return PhysicalPreopenUploadObject(
        role=role,
        object_store_key=key,
        content_sha256=sha256,
        content_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        byte_count=len(payload),
    )


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PhysicalPreopenUploadPlan:
    schema: str
    plan_id: str
    plan_sha256: str
    organization_id: str
    projection_id: str
    projection_sha256: str
    project_source_set_sha256: str
    run_authority_id: str
    run_authority_sha256: str
    stream_id: str
    stream_sha256: str
    closed_input_manifest_sha256: str
    input_manifest_sha256: str
    input_manifest_byte_count: int
    input_manifest_key: str
    input_source_inventory_sha256: str
    input_shard_count: int
    upload_object_count: int
    total_compressed_input_byte_count: int
    maximum_shard_compressed_byte_count: int
    upload_objects: tuple[PhysicalPreopenUploadObject, ...]
    endpoint_allowlist: tuple[str, ...]
    manifest_published_last: bool
    retains_compressed_input_payloads: bool
    outcome_result_statistics_log_order_access_authorized: bool
    deployment_order_trading_authorized: bool
    _input_manifest_bytes: bytes = dataclasses.field(repr=False)
    _stream: inputs.AuthenticatedHistoricalPreopenInputStream = (
        dataclasses.field(repr=False)
    )
    _projection: PreopenControlQcProjection = dataclasses.field(repr=False)
    _run_authority: PreopenControlRunAuthority = dataclasses.field(repr=False)


_PLAN_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType[PhysicalPreopenUploadPlan], str, int]
] = {}
_PLAN_LOCK = threading.RLock()
_PLAN_PID = os.getpid()


def _plan_seed(
    *, stream: inputs.AuthenticatedHistoricalPreopenInputStream,
    projection: PreopenControlQcProjection,
    run_authority: PreopenControlRunAuthority,
    organization_id: str,
    input_manifest_bytes: bytes,
    objects: tuple[PhysicalPreopenUploadObject, ...],
) -> dict[str, object]:
    return {
        "schema": PLAN_SCHEMA,
        "plan_id": None,
        "plan_sha256": None,
        "organization_id_sha256": hashlib.sha256(
            organization_id.encode("utf-8")
        ).hexdigest(),
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "project_source_set_sha256": projection.project_source_set_sha256,
        "run_authority_id": run_authority.pin_id,
        "run_authority_sha256": run_authority.pin_sha256,
        "stream_id": stream.stream_id,
        "stream_sha256": stream.stream_sha256,
        "closed_input_manifest_sha256": stream.closed_input_manifest_sha256,
        "input_manifest_sha256": hashlib.sha256(
            input_manifest_bytes
        ).hexdigest(),
        "input_manifest_byte_count": len(input_manifest_bytes),
        "input_manifest_key": projection.input_manifest_key,
        "input_source_inventory_sha256": stream.input_source_inventory_sha256,
        "input_shard_count": stream.input_shard_count,
        "upload_object_count": len(objects),
        "total_compressed_input_byte_count": (
            stream.total_compressed_input_byte_count
        ),
        "maximum_shard_compressed_byte_count": (
            stream.maximum_shard_compressed_byte_count
        ),
        "upload_objects": [item.to_record() for item in objects],
        "endpoint_allowlist": list(ENDPOINT_ALLOWLIST),
        "manifest_published_last": True,
        "retains_compressed_input_payloads": False,
        "outcome_result_statistics_log_order_access_authorized": False,
        "deployment_order_trading_authorized": False,
    }


def _identified_plan(seed: dict[str, object]) -> tuple[dict[str, object], str]:
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    record = dict(seed)
    record["plan_id"] = "arv2-physical-preopen-upload-" + digest[:24]
    record["plan_sha256"] = digest
    return record, digest


def _plan_fingerprint(value: PhysicalPreopenUploadPlan) -> str:
    return hashlib.sha256(_canonical({
        "public": {
            field.name: (
                [item.to_record() for item in value.upload_objects]
                if field.name == "upload_objects"
                else list(value.endpoint_allowlist)
                if field.name == "endpoint_allowlist"
                else getattr(value, field.name)
            )
            for field in dataclasses.fields(value)
            if not field.name.startswith("_")
        },
        "input_manifest_payload_sha256": hashlib.sha256(
            value._input_manifest_bytes
        ).hexdigest(),
        "stream_identity": id(value._stream),
        "projection_identity": id(value._projection),
        "run_authority_identity": id(value._run_authority),
    })).hexdigest()


def _validate_manifest_lineage(
    *, stream: inputs.AuthenticatedHistoricalPreopenInputStream,
    projection: PreopenControlQcProjection,
    run_authority: PreopenControlRunAuthority,
    input_manifest_bytes: bytes,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    try:
        _PINNED_REBUILD_PROJECTION(
            projection, input_manifest_bytes, run_authority
        )
    except Exception as exc:
        raise PhysicalPreopenSubmissionError(
            "physical pre-open projection authority changed"
        ) from exc
    activated = _strict_object(input_manifest_bytes, "activated input manifest")
    closed = _strict_object(
        stream.closed_input_manifest_bytes, "closed input manifest"
    )
    descriptors = activated.get("shards")
    if (
        type(descriptors) is not list
        or descriptors != closed.get("shards")
        or len(descriptors) != stream.input_shard_count
        or activated.get("input_source_inventory_sha256")
        != stream.input_source_inventory_sha256
        or run_authority.closed_input_manifest_sha256
        != stream.closed_input_manifest_sha256
        or projection.input_manifest_sha256
        != hashlib.sha256(input_manifest_bytes).hexdigest()
        or projection.input_manifest_byte_count != len(input_manifest_bytes)
    ):
        raise PhysicalPreopenSubmissionError(
            "physical stream and activated manifest differ"
        )
    return activated, tuple(descriptors)


def build_physical_preopen_upload_plan(
    *, stream: inputs.AuthenticatedHistoricalPreopenInputStream,
    projection: PreopenControlQcProjection,
    input_manifest_bytes: bytes,
    run_authority: PreopenControlRunAuthority,
    organization_id: str,
) -> PhysicalPreopenUploadPlan:
    """Read each physical shard once to bind metadata, retaining no payload."""

    _require_dependencies()
    try:
        stream = _PINNED_REQUIRE_STREAM(stream)
        _PINNED_SAFE(organization_id, "organization_id")
        _activated, descriptors = _validate_manifest_lineage(
            stream=stream,
            projection=projection,
            run_authority=run_authority,
            input_manifest_bytes=input_manifest_bytes,
        )
        if (
            stream.input_shard_count > _PINNED_INPUT_SHARD_COUNT
            or stream.maximum_shard_compressed_byte_count
            > _PINNED_INPUT_SHARD_BYTES
            or stream.total_compressed_input_byte_count
            > _PINNED_TOTAL_INPUT_BYTES
        ):
            raise PhysicalPreopenSubmissionError(
                "physical pre-open input exceeds upload capacity"
            )
        objects: list[PhysicalPreopenUploadObject] = []
        for ordinal, (shard, descriptor) in enumerate(
            zip(_PINNED_ITER_STREAM(stream), descriptors, strict=True)
        ):
            if (
                type(shard) is not _PINNED_SHARD_CLASS
                or _PINNED_SHARD_DESCRIPTOR(shard) != descriptor
                or shard.compressed_byte_count > _PINNED_INPUT_SHARD_BYTES
            ):
                raise PhysicalPreopenSubmissionError(
                    f"physical pre-open shard {ordinal} changed"
                )
            objects.append(_upload_object(
                role="input_" + shard.role,
                key=shard.object_store_key,
                sha256=shard.compressed_sha256,
                payload=shard.payload,
            ))
            del shard
        objects.append(_upload_object(
            role="input_manifest",
            key=projection.input_manifest_key,
            sha256=projection.input_manifest_sha256,
            payload=input_manifest_bytes,
        ))
        packed = tuple(objects)
        if (
            len(packed) != stream.input_shard_count + 1
            or len({item.object_store_key for item in packed}) != len(packed)
            or packed[-1].role != "input_manifest"
        ):
            raise PhysicalPreopenSubmissionError(
                "physical pre-open upload inventory changed"
            )
        seed = _plan_seed(
            stream=stream,
            projection=projection,
            run_authority=run_authority,
            organization_id=organization_id,
            input_manifest_bytes=input_manifest_bytes,
            objects=packed,
        )
        record, digest = _identified_plan(seed)
    except PhysicalPreopenSubmissionError:
        raise
    except Exception as exc:
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload plan construction changed"
        ) from exc
    value = PhysicalPreopenUploadPlan(
        schema=PLAN_SCHEMA,
        plan_id=record["plan_id"],
        plan_sha256=digest,
        organization_id=organization_id,
        projection_id=projection.projection_id,
        projection_sha256=projection.projection_sha256,
        project_source_set_sha256=projection.project_source_set_sha256,
        run_authority_id=run_authority.pin_id,
        run_authority_sha256=run_authority.pin_sha256,
        stream_id=stream.stream_id,
        stream_sha256=stream.stream_sha256,
        closed_input_manifest_sha256=stream.closed_input_manifest_sha256,
        input_manifest_sha256=projection.input_manifest_sha256,
        input_manifest_byte_count=len(input_manifest_bytes),
        input_manifest_key=projection.input_manifest_key,
        input_source_inventory_sha256=stream.input_source_inventory_sha256,
        input_shard_count=stream.input_shard_count,
        upload_object_count=len(packed),
        total_compressed_input_byte_count=(
            stream.total_compressed_input_byte_count
        ),
        maximum_shard_compressed_byte_count=(
            stream.maximum_shard_compressed_byte_count
        ),
        upload_objects=packed,
        endpoint_allowlist=ENDPOINT_ALLOWLIST,
        manifest_published_last=True,
        retains_compressed_input_payloads=False,
        outcome_result_statistics_log_order_access_authorized=False,
        deployment_order_trading_authorized=False,
        _input_manifest_bytes=input_manifest_bytes,
        _stream=stream,
        _projection=projection,
        _run_authority=run_authority,
    )
    reference = weakref.ref(
        value, lambda _ref, key=id(value): _PLAN_AUTHORITIES.pop(key, None)
    )
    with _PLAN_LOCK:
        _PLAN_AUTHORITIES[id(value)] = (
            reference,
            _plan_fingerprint(value),
            os.getpid(),
        )
    return require_physical_preopen_upload_plan(value)


def require_physical_preopen_upload_plan(
    value: PhysicalPreopenUploadPlan,
) -> PhysicalPreopenUploadPlan:
    if type(value) is not PhysicalPreopenUploadPlan:
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload plan type changed"
        )
    with _PLAN_LOCK:
        registered = _PLAN_AUTHORITIES.get(id(value))
    if (
        os.getpid() != _PLAN_PID
        or registered is None
        or registered[0]() is not value
        or registered[2] != os.getpid()
    ):
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload plan lacks builder authority"
        )
    try:
        _require_dependencies()
        stream = _PINNED_REQUIRE_STREAM(value._stream)
        _validate_manifest_lineage(
            stream=stream,
            projection=value._projection,
            run_authority=value._run_authority,
            input_manifest_bytes=value._input_manifest_bytes,
        )
        objects = value.upload_objects
        seed = _plan_seed(
            stream=stream,
            projection=value._projection,
            run_authority=value._run_authority,
            organization_id=value.organization_id,
            input_manifest_bytes=value._input_manifest_bytes,
            objects=objects,
        )
        record, digest = _identified_plan(seed)
        public = {
            field.name: getattr(value, field.name)
            for field in dataclasses.fields(value)
            if not field.name.startswith("_")
            and field.name not in {"upload_objects", "endpoint_allowlist"}
        }
        expected_public = {
            name: item
            for name, item in record.items()
            if name not in {"organization_id_sha256", "upload_objects"}
        }
        expected_public["organization_id"] = value.organization_id
        expected_public["upload_objects"] = objects
        expected_public["endpoint_allowlist"] = ENDPOINT_ALLOWLIST
        if (
            public != {
                name: item
                for name, item in expected_public.items()
                if name not in {"upload_objects", "endpoint_allowlist"}
            }
            or value.plan_sha256 != digest
            or value.plan_id != record["plan_id"]
            or type(objects) is not tuple
            or any(type(item) is not PhysicalPreopenUploadObject for item in objects)
            or len(objects) != stream.input_shard_count + 1
            or objects[-1].role != "input_manifest"
            or value.endpoint_allowlist != ENDPOINT_ALLOWLIST
            or registered[1] != _plan_fingerprint(value)
        ):
            raise PhysicalPreopenSubmissionError(
                "physical pre-open upload plan changed"
            )
    except PhysicalPreopenSubmissionError:
        raise
    except Exception as exc:
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload plan cannot be revalidated"
        ) from exc
    return value


def _render_execution_authority(
    plan: PhysicalPreopenUploadPlan, closure,
) -> bytes:
    plan = require_physical_preopen_upload_plan(plan)
    _PINNED_VERIFY_HOST_CLOSURE(closure)
    return _canonical({
        "schema": EXECUTION_AUTHORITY_SCHEMA,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "stream_id": plan.stream_id,
        "stream_sha256": plan.stream_sha256,
        "input_manifest_sha256": plan.input_manifest_sha256,
        "input_source_inventory_sha256": plan.input_source_inventory_sha256,
        "organization_id_sha256": hashlib.sha256(
            plan.organization_id.encode("utf-8")
        ).hexdigest(),
        "host_closure": {
            "closure_id": closure.closure_id,
            "closure_sha256": closure.closure_sha256,
            "sources": [item.to_record() for item in closure.sources],
        },
        "actions": list(UPLOAD_ACTIONS),
        "endpoint_allowlist": list(ENDPOINT_ALLOWLIST),
        "object_store_key_allowlist": [
            item.object_store_key for item in plan.upload_objects
        ],
        "maximum_upload_object_count": plan.upload_object_count,
        "maximum_input_shard_count": _PINNED_INPUT_SHARD_COUNT,
        "maximum_input_shard_bytes": _PINNED_INPUT_SHARD_BYTES,
        "maximum_total_input_bytes": _PINNED_TOTAL_INPUT_BYTES,
        "one_shard_payload_retained_at_a_time": True,
        "activated_manifest_published_last": True,
        "maximum_backtest_submissions": 0,
        "outcome_result_statistics_log_order_access_authorized": False,
        "deployment_order_trading_authorized": False,
    })


def render_physical_preopen_upload_execution_authority_candidate(
    plan: PhysicalPreopenUploadPlan,
) -> bytes:
    """Render the exact owner-signature payload for the bounded upload."""

    _require_dependencies()
    return _render_execution_authority(
        plan, _PINNED_BUILD_HOST_CLOSURE()
    )


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalPreopenUploadPermit:
    schema: str
    permit_id: str
    permit_sha256: str
    plan_id: str
    plan_sha256: str
    started_at_utc: str
    submission_attempt_count: int
    ambiguous_upload_consumes_permit: bool
    retry_authorized: bool
    permit_path: Path
    _permit_bytes: bytes = dataclasses.field(repr=False)


def _spend_permit(
    plan: PhysicalPreopenUploadPlan,
    ledger_directory: Path,
    started_at_utc: str,
) -> PhysicalPreopenUploadPermit:
    plan = require_physical_preopen_upload_plan(plan)
    try:
        _PINNED_UTC(started_at_utc, "physical upload started_at")
    except Exception as exc:
        raise PhysicalPreopenSubmissionError(
            "physical upload timestamp changed"
        ) from exc
    if type(ledger_directory) is not type(Path()) or not ledger_directory.is_absolute():
        raise PhysicalPreopenSubmissionError(
            "physical upload permit directory must be an absolute Path"
        )
    try:
        directory = ledger_directory.resolve(strict=True)
        observed = directory.stat(follow_symlinks=False)
    except OSError as exc:
        raise PhysicalPreopenSubmissionError(
            "physical upload permit directory is unavailable"
        ) from exc
    if (
        directory != ledger_directory
        or not stat.S_ISDIR(observed.st_mode)
        or stat.S_IMODE(observed.st_mode) != 0o700
        or (hasattr(os, "getuid") and observed.st_uid != os.getuid())
    ):
        raise PhysicalPreopenSubmissionError(
            "physical upload permit directory is not owner-only"
        )
    seed = {
        "schema": PERMIT_SCHEMA,
        "permit_id": None,
        "permit_sha256": None,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "started_at_utc": started_at_utc,
        "submission_attempt_count": 1,
        "ambiguous_upload_consumes_permit": True,
        "retry_authorized": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    record = dict(seed)
    record["permit_id"] = "arv2-physical-preopen-upload-permit-" + digest[:24]
    record["permit_sha256"] = digest
    payload = _canonical(record)
    path = directory / PERMIT_FILENAME
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            view = memoryview(payload)
            while view:
                count = os.write(descriptor, view)
                if count <= 0:
                    raise OSError("short permit write")
                view = view[count:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _PINNED_FSYNC_DIRECTORY(directory, "physical upload permit directory")
    except FileExistsError as exc:
        raise PhysicalPreopenSubmissionLocked(
            str(record["permit_id"]), "permit already spent"
        ) from exc
    except OSError as exc:
        raise PhysicalPreopenSubmissionLocked(
            str(record["permit_id"]), "permit publication is ambiguous"
        ) from exc
    return PhysicalPreopenUploadPermit(
        schema=PERMIT_SCHEMA,
        permit_id=str(record["permit_id"]),
        permit_sha256=digest,
        plan_id=plan.plan_id,
        plan_sha256=plan.plan_sha256,
        started_at_utc=started_at_utc,
        submission_attempt_count=1,
        ambiguous_upload_consumes_permit=True,
        retry_authorized=False,
        permit_path=path,
        _permit_bytes=payload,
    )


def require_physical_preopen_upload_permit(
    value: PhysicalPreopenUploadPermit,
    plan: PhysicalPreopenUploadPlan,
) -> PhysicalPreopenUploadPermit:
    plan = require_physical_preopen_upload_plan(plan)
    if type(value) is not PhysicalPreopenUploadPermit:
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload permit type changed"
        )
    try:
        payload = _PINNED_READ_PRIVATE(
            value.permit_path,
            expected_sha256=hashlib.sha256(value._permit_bytes).hexdigest(),
            expected_byte_count=len(value._permit_bytes),
            maximum=MAX_PERMIT_BYTES,
            name="physical pre-open upload permit",
        )
        raw = _strict_object(payload, "physical pre-open upload permit")
    except Exception as exc:
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload permit is unavailable"
        ) from exc
    seed = dict(raw)
    seed["permit_id"] = None
    seed["permit_sha256"] = None
    if (
        payload != value._permit_bytes
        or raw.get("schema") != PERMIT_SCHEMA
        or raw.get("permit_id") != value.permit_id
        or raw.get("permit_sha256") != value.permit_sha256
        or hashlib.sha256(_canonical(seed)).hexdigest() != value.permit_sha256
        or value.plan_id != plan.plan_id
        or value.plan_sha256 != plan.plan_sha256
        or value.submission_attempt_count != 1
        or value.ambiguous_upload_consumes_permit is not True
        or value.retry_authorized is not False
    ):
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload permit changed"
        )
    return value


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PhysicalPreopenUploadReceipt:
    schema: str
    receipt_id: str
    receipt_sha256: str
    plan_id: str
    plan_sha256: str
    permit_id: str
    permit_sha256: str
    stream_id: str
    stream_sha256: str
    input_manifest_sha256: str
    input_source_inventory_sha256: str
    uploaded_input_shard_count: int
    uploaded_object_count: int
    uploaded_byte_count: int
    endpoint_allowlist: tuple[str, ...]
    activated_manifest_published_last: bool
    maximum_backtest_submissions: int
    outcome_result_statistics_log_order_accessed: bool
    deployment_order_trading_authorized: bool
    _plan: PhysicalPreopenUploadPlan = dataclasses.field(repr=False)
    _permit: PhysicalPreopenUploadPermit = dataclasses.field(repr=False)


_RECEIPTS: dict[
    int, tuple[weakref.ReferenceType[PhysicalPreopenUploadReceipt], str, int]
] = {}
_RECEIPT_LOCK = threading.RLock()
_RECEIPT_PID = os.getpid()


def _receipt_record(
    plan: PhysicalPreopenUploadPlan,
    permit: PhysicalPreopenUploadPermit,
) -> dict[str, object]:
    return {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": None,
        "receipt_sha256": None,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "permit_id": permit.permit_id,
        "permit_sha256": permit.permit_sha256,
        "stream_id": plan.stream_id,
        "stream_sha256": plan.stream_sha256,
        "input_manifest_sha256": plan.input_manifest_sha256,
        "input_source_inventory_sha256": plan.input_source_inventory_sha256,
        "uploaded_input_shard_count": plan.input_shard_count,
        "uploaded_object_count": plan.upload_object_count,
        "uploaded_byte_count": sum(
            item.byte_count for item in plan.upload_objects
        ),
        "endpoint_allowlist": list(ENDPOINT_ALLOWLIST),
        "activated_manifest_published_last": True,
        "maximum_backtest_submissions": 0,
        "outcome_result_statistics_log_order_accessed": False,
        "deployment_order_trading_authorized": False,
    }


def _receipt_fingerprint(value: PhysicalPreopenUploadReceipt) -> str:
    return hashlib.sha256(_canonical({
        "record": _receipt_record(value._plan, value._permit),
        "receipt_id": value.receipt_id,
        "receipt_sha256": value.receipt_sha256,
        "plan_identity": id(value._plan),
        "permit_identity": id(value._permit),
    })).hexdigest()


def _mint_receipt(
    plan: PhysicalPreopenUploadPlan,
    permit: PhysicalPreopenUploadPermit,
) -> PhysicalPreopenUploadReceipt:
    record = _receipt_record(plan, permit)
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    record["receipt_id"] = "arv2-physical-preopen-upload-" + digest[:24]
    record["receipt_sha256"] = digest
    value = PhysicalPreopenUploadReceipt(
        **{
            name: tuple(item) if name == "endpoint_allowlist" else item
            for name, item in record.items()
        },
        _plan=plan,
        _permit=permit,
    )
    reference = weakref.ref(
        value, lambda _ref, key=id(value): _RECEIPTS.pop(key, None)
    )
    with _RECEIPT_LOCK:
        _RECEIPTS[id(value)] = (
            reference,
            _receipt_fingerprint(value),
            os.getpid(),
        )
    return require_physical_preopen_upload_receipt(value)


def require_physical_preopen_upload_receipt(
    value: PhysicalPreopenUploadReceipt,
) -> PhysicalPreopenUploadReceipt:
    if type(value) is not PhysicalPreopenUploadReceipt:
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload receipt type changed"
        )
    with _RECEIPT_LOCK:
        registered = _RECEIPTS.get(id(value))
    if (
        os.getpid() != _RECEIPT_PID
        or registered is None
        or registered[0]() is not value
        or registered[2] != os.getpid()
    ):
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload receipt lacks process authority"
        )
    plan = require_physical_preopen_upload_plan(value._plan)
    permit = require_physical_preopen_upload_permit(value._permit, plan)
    record = _receipt_record(plan, permit)
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    expected = dict(record)
    expected["receipt_id"] = "arv2-physical-preopen-upload-" + digest[:24]
    expected["receipt_sha256"] = digest
    observed = {
        field.name: (
            list(value.endpoint_allowlist)
            if field.name == "endpoint_allowlist"
            else getattr(value, field.name)
        )
        for field in dataclasses.fields(value)
        if not field.name.startswith("_")
    }
    if (
        observed != expected
        or registered[1] != _receipt_fingerprint(value)
    ):
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload receipt changed"
        )
    return value


def _iter_upload_payloads(plan: PhysicalPreopenUploadPlan):
    plan = require_physical_preopen_upload_plan(plan)
    shard_objects = plan.upload_objects[:-1]
    manifest_object = plan.upload_objects[-1]
    for ordinal, (shard, expected) in enumerate(
        zip(_PINNED_ITER_STREAM(plan._stream), shard_objects, strict=True)
    ):
        observed = _upload_object(
            role="input_" + shard.role,
            key=shard.object_store_key,
            sha256=shard.compressed_sha256,
            payload=shard.payload,
        )
        if observed != expected:
            raise PhysicalPreopenSubmissionError(
                f"physical pre-open upload shard {ordinal} changed"
            )
        yield expected, shard.payload
        del shard, observed
    observed_manifest = _upload_object(
        role="input_manifest",
        key=plan.input_manifest_key,
        sha256=plan.input_manifest_sha256,
        payload=plan._input_manifest_bytes,
    )
    if observed_manifest != manifest_object:
        raise PhysicalPreopenSubmissionError(
            "physical pre-open upload manifest changed"
        )
    yield manifest_object, plan._input_manifest_bytes


def _require_upload_authority(
    *, plan: PhysicalPreopenUploadPlan,
    client: FormalQcTransport,
    owner_signature: OwnerSignatureAuthority | None,
):
    _require_dependencies()
    closure = _PINNED_BUILD_HOST_CLOSURE()
    _PINNED_REQUIRE_OWNER(
        owner_signature, _render_execution_authority(plan, closure)
    )
    _PINNED_VERIFY_HOST_CLOSURE(closure)
    require_physical_preopen_upload_plan(plan)
    _PINNED_CONCRETE_TRANSPORT(client)
    return closure


def _execute_physical_preopen_input_upload_once_impl(
    *, plan: PhysicalPreopenUploadPlan,
    client: FormalQcTransport,
    ledger_directory: Path,
    started_at_utc: str,
    owner_signature: OwnerSignatureAuthority | None,
    _transport_capability_minter,
    _require_upload_authority_impl,
    _spend_permit_impl,
    _iter_upload_payloads_impl,
    _preopen_call_impl,
    _metadata_matches_impl,
    _mint_receipt_impl,
) -> tuple[PhysicalPreopenUploadPermit, PhysicalPreopenUploadReceipt]:
    """Upload each exact shard once and publish the activated manifest last."""

    closure = _require_upload_authority_impl(
        plan=plan,
        client=client,
        owner_signature=owner_signature,
    )
    permit = _spend_permit_impl(plan, ledger_directory, started_at_utc)
    try:
        capability = _transport_capability_minter(
            transport=client,
            scope="submission",
            binding_record={
                "schema": "arv2-physical-preopen-upload-capability-v1",
                "plan_sha256": plan.plan_sha256,
                "permit_sha256": permit.permit_sha256,
                "endpoint_allowlist": list(ENDPOINT_ALLOWLIST),
                "object_store_keys": [
                    item.object_store_key for item in plan.upload_objects
                ],
                "manifest_published_last": True,
            },
            call_budget={
                "authenticate": 1,
                "object/set": plan.upload_object_count,
                "object/properties": plan.upload_object_count,
            },
        )
        _preopen_call_impl(
            closure, client, capability, "_request_json", "authenticate", {}
        )
        for expected, payload in _iter_upload_payloads_impl(plan):
            _preopen_call_impl(
                closure,
                client,
                capability,
                "_set_object_multipart",
                plan.organization_id,
                expected.object_store_key,
                payload,
            )
            _metadata_matches_impl(
                _preopen_call_impl(
                    closure,
                    client,
                    capability,
                    "_read_object_properties",
                    plan.organization_id,
                    expected.object_store_key,
                ),
                expected,
            )
            del payload
        return permit, _mint_receipt_impl(plan, permit)
    except Exception as exc:
        raise PhysicalPreopenSubmissionLocked(
            permit.permit_id, type(exc).__name__
        ) from exc


def _bind_upload_action(
    minter,
    implementation,
    require_upload_authority,
    spend_permit,
    iter_upload_payloads,
    preopen_call,
    metadata_matches,
    mint_receipt,
):
    def execute_physical_preopen_input_upload_once(
        *, plan: PhysicalPreopenUploadPlan,
        client: FormalQcTransport,
        ledger_directory: Path,
        started_at_utc: str,
        owner_signature: OwnerSignatureAuthority | None,
    ) -> tuple[PhysicalPreopenUploadPermit, PhysicalPreopenUploadReceipt]:
        return implementation(
            plan=plan,
            client=client,
            ledger_directory=ledger_directory,
            started_at_utc=started_at_utc,
            owner_signature=owner_signature,
            _transport_capability_minter=minter,
            _require_upload_authority_impl=require_upload_authority,
            _spend_permit_impl=spend_permit,
            _iter_upload_payloads_impl=iter_upload_payloads,
            _preopen_call_impl=preopen_call,
            _metadata_matches_impl=metadata_matches,
            _mint_receipt_impl=mint_receipt,
        )

    return execute_physical_preopen_input_upload_once


(
    _transport_capability_minter,
    _seal_transport_capability_callers,
) = formal._claim_preopen_physical_upload_transport_capability_minter()
execute_physical_preopen_input_upload_once = _bind_upload_action(
    _transport_capability_minter,
    _execute_physical_preopen_input_upload_once_impl,
    _require_upload_authority,
    _spend_permit,
    _iter_upload_payloads,
    _PINNED_PREOPEN_CALL,
    _PINNED_METADATA_MATCHES,
    _mint_receipt,
)
_seal_transport_capability_callers((
    (
        "submission",
        ((
            _execute_physical_preopen_input_upload_once_impl,
            execute_physical_preopen_input_upload_once,
        ),),
    ),
))
del _transport_capability_minter
del _seal_transport_capability_callers
del _execute_physical_preopen_input_upload_once_impl
del _bind_upload_action
del _require_upload_authority
del _spend_permit
del _iter_upload_payloads
del _mint_receipt


PhysicalPreopenQcSubmissionPlan = submission.PhysicalPreopenQcSubmissionPlan


def build_physical_preopen_qc_submission_plan(
    *, physical_upload_receipt: PhysicalPreopenUploadReceipt,
    output_archive_root: Path | None = None,
) -> PhysicalPreopenQcSubmissionPlan:
    """Build the payload-free, owner-waived QC continuation plan."""

    _require_dependencies()
    return _PINNED_BUILD_QC_PLAN(
        physical_upload_receipt=physical_upload_receipt,
        output_archive_root=output_archive_root,
    )


def require_physical_preopen_qc_submission_plan(
    value: PhysicalPreopenQcSubmissionPlan,
) -> PhysicalPreopenQcSubmissionPlan:
    _require_dependencies()
    return _PINNED_REQUIRE_QC_PLAN(value)


def render_physical_preopen_qc_execution_authority_candidate(
    plan: PhysicalPreopenQcSubmissionPlan,
) -> bytes:
    _require_dependencies()
    return _PINNED_RENDER_QC_AUTHORITY(plan)


def execute_physical_preopen_qc_submission_once(
    *, plan: PhysicalPreopenQcSubmissionPlan,
    client: FormalQcTransport,
    ledger_directory: Path,
    started_at_utc: str,
    owner_signature: OwnerSignatureAuthority | None,
):
    _require_dependencies()
    return _PINNED_EXECUTE_QC(
        plan=plan,
        client=client,
        ledger_directory=ledger_directory,
        started_at_utc=started_at_utc,
        owner_signature=owner_signature,
    )


__all__ = (
    "ENDPOINT_ALLOWLIST",
    "EXECUTION_AUTHORITY_SCHEMA",
    "MAX_INPUT_SHARD_BYTES",
    "MAX_INPUT_SHARD_COUNT",
    "MAX_TOTAL_INPUT_BYTES",
    "PERMIT_FILENAME",
    "PLAN_SCHEMA",
    "PhysicalPreopenSubmissionError",
    "PhysicalPreopenSubmissionLocked",
    "PhysicalPreopenUploadObject",
    "PhysicalPreopenQcSubmissionPlan",
    "PhysicalPreopenUploadPermit",
    "PhysicalPreopenUploadPlan",
    "PhysicalPreopenUploadReceipt",
    "build_physical_preopen_upload_plan",
    "build_physical_preopen_qc_submission_plan",
    "execute_physical_preopen_qc_submission_once",
    "execute_physical_preopen_input_upload_once",
    "render_physical_preopen_upload_execution_authority_candidate",
    "render_physical_preopen_qc_execution_authority_candidate",
    "require_physical_preopen_qc_submission_plan",
    "require_physical_preopen_upload_permit",
    "require_physical_preopen_upload_plan",
    "require_physical_preopen_upload_receipt",
)
