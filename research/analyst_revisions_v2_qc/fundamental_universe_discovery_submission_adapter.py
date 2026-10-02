"""One-shot, outcome-free QC transport for Fundamentals discovery.

Importing and building objects in this module performs no I/O other than
explicit local authorization-pin/ledger/archive operations.  The production
path accepts only the concrete :class:`FormalQcTransport`, authenticates the
exact live host closure, requires an owner-only claim that records the narrow
section-72 review waiver truthfully plus a detached owner signature for
``PREOPEN_EXECUTION``, spends a durable one-use permit, and then executes the
exact project/upload/compile/run choreography.  The waiver does not represent
an independent review and records the independent-review debt after the first
formal backtest.

Status inspection uses ``backtests/list`` with ``includeStatistics=False``.
It never calls ``backtests/read`` or accesses results, statistics, charts,
logs, orders, trades, prices, or returns.  Output retrieval reads only the
runtime-named Object Store package, manifest, and content-addressed terminal
shards, one object at a time, into the owner-only archive consumed by the
reviewed discovery loader.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import re
import stat
import sys
import threading
import time
import weakref
from datetime import datetime
from pathlib import Path

from . import formal_submission_adapter as formal
from .formal_qc_transport import FormalQcTransport
from .fundamental_universe_discovery import (
    ARCHIVE_MANIFEST_NAME,
    ARCHIVE_PACKAGE_NAME,
    ARCHIVE_SHARD_DIRECTORY,
    CONTRACT_SHA256,
    MAX_COMPRESSED_SHARD_BYTES,
    MAX_OUTPUT_MANIFEST_BYTES,
    MAX_TERMINAL_PACKAGE_BYTES,
    MAX_TERMINAL_SHARDS,
    OUTPUT_PREFIX,
    OUTPUT_SHARD_SCHEMA,
    TERMINAL_PACKAGE_SCHEMA,
    FundamentalDiscoveryProjectSource,
    FundamentalUniverseDiscoveryQcProjection,
    ReviewedFundamentalUniverseDiscoveryReceipt,
    build_fundamental_universe_discovery_qc_projection,
    canonical_json_bytes,
    fundamental_discovery_artifact_binding_record,
    load_reviewed_fundamental_universe_discovery_receipt,
    require_fundamental_universe_discovery_qc_projection,
    require_reviewed_fundamental_universe_discovery_receipt,
)
from .owner_signature_authority import (
    OwnerSignatureAuthority,
    OwnerSignatureAuthorityError,
    require_preopen_execution_owner_signature,
)


class FundamentalDiscoverySubmissionError(ValueError):
    """A discovery claim, plan, response, or archive binding is invalid."""


class FundamentalDiscoverySubmissionLocked(RuntimeError):
    """A one-use permit was spent and the external state is ambiguous."""

    def __init__(self, phase: str, permit_id: str, detail: str) -> None:
        super().__init__(
            f"{phase}: {detail}; one-use discovery permit remains consumed"
        )
        self.phase = phase
        self.permit_id = permit_id


class FundamentalDiscoveryDiagnosticPublicationAmbiguous(RuntimeError):
    """A complete receipt was linked but directory durability is ambiguous."""


class FundamentalDiscoveryArchiveRootPublicationAmbiguous(RuntimeError):
    """The private archive root exists but parent durability is ambiguous."""


PLAN_SCHEMA = "arv2-qc-fundamental-discovery-submission-plan-v3"
REVIEW_CLAIM_SCHEMA = "arv2-qc-fundamental-discovery-review-claim-v4"
PERMIT_SCHEMA = "arv2-qc-fundamental-discovery-one-use-permit-v1"
LAUNCH_SCHEMA = "arv2-qc-fundamental-discovery-launch-receipt-v1"
TERMINAL_STATUS_SCHEMA = "arv2-qc-fundamental-discovery-terminal-status-v1"
REFUSAL_RECEIPT_SCHEMA = "arv2-qc-fundamental-discovery-refusal-receipt-v1"
PROJECT_SCHEMA_DIAGNOSTIC_RECEIPT_SCHEMA = (
    "arv2-qc-projects-read-schema-diagnostic-receipt-v1"
)
FILES_SCHEMA_DIAGNOSTIC_RECEIPT_SCHEMA = (
    "arv2-qc-files-read-schema-diagnostic-receipt-v1"
)
BACKTEST_LIST_SCHEMA_DIAGNOSTIC_RECEIPT_SCHEMA = (
    "arv2-qc-backtests-list-schema-diagnostic-receipt-v1"
)
EXECUTION_AUTHORITY_SCHEMA = "arv2-qc-fundamental-discovery-execution-authority-v4"
HOST_CLOSURE_SCHEMA = "arv2-qc-fundamental-discovery-host-closure-v1"
REVIEW_CLAIM_FILENAME = "arv2-qc-fundamental-discovery-review-claim-v4.json"
OWNER_REVIEW_WAIVER_ID = "arv2-owner-review-waiver-section-72-v1"
OWNER_REVIEW_WAIVER_SCOPE = "SECTION_72_THROUGH_FIRST_FORMAL_BACKTEST"
OWNER_REVIEW_WAIVER_BASIS = "OWNER_EXPLICIT_REVIEW_WAIVER"
PERMIT_FILENAME = "arv2-qc-fundamental-discovery-one-use-permit-v1.json"
REFUSAL_FILENAME = "named-refusal.json"
PROJECT_SCHEMA_DIAGNOSTIC_FILENAME = "projects-read-schema-diagnostic.json"
FILES_SCHEMA_DIAGNOSTIC_FILENAME = "files-read-schema-diagnostic.json"
BACKTEST_LIST_SCHEMA_DIAGNOSTIC_FILENAME = (
    "backtests-list-schema-diagnostic.json"
)
MAX_CONTROL_BYTES = 1024 * 1024
MAX_PROJECT_SCHEMA_DIAGNOSTIC_BYTES = 64 * 1024
MAX_PROJECT_SCHEMA_DIAGNOSTIC_FIELDS = 64
MAX_PROJECT_SCHEMA_DIAGNOSTIC_RECORDS = 1024
MAX_PROJECT_SCHEMA_DIAGNOSTIC_UNIQUE_SHAPES = 4
MAX_FILES_SCHEMA_DIAGNOSTIC_RECORDS = 1024
MAX_FILES_SCHEMA_DIAGNOSTIC_UNIQUE_SHAPES = 4
MAX_BACKTEST_LIST_SCHEMA_DIAGNOSTIC_RECORDS = 1024
MAX_BACKTEST_LIST_SCHEMA_DIAGNOSTIC_UNIQUE_SHAPES = 4
MAX_DISCOVERY_PROJECT_NAME_BYTES = 100
QC_DEFAULT_RESEARCH_NOTEBOOK_PATH = "research.ipynb"
MAX_DEFAULT_NOTEBOOK_DELETIONS = 1
MAX_COMPILE_POLLS = 120
MAX_STATUS_POLLS = 240
COMPILE_POLL_SECONDS = 2
STATUS_POLL_SECONDS = 30
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/ -]{0,511}\Z")
_SAFE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,1023}\Z")
_SAFE_DIAGNOSTIC_FIELD_NAME = re.compile(
    r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z"
)

EXECUTION_ACTIONS = (
    "authenticate",
    "projects/read_exact_name_inventory",
    "projects/create_private_exact_name_once",
    "object/set_exact_content_addressed_discovery_plan",
    "object/properties_verify_exact_discovery_plan",
    "files/read_exact_inventory",
    "files/delete_exact_new_project_default_research_notebook_once",
    "files/create_or_update_exact_reviewed_projection",
    "files/readback_exact_bytes",
    "compile/create_once",
    "compile/read_state_only_with_bounded_wait",
    "backtests/create_once",
    "backtests/list_identity_status_includeStatistics_false",
    "write_bounded_backtests_list_schema_diagnostic_on_refusal",
    "object/read_exact_terminal_package_manifest_and_shards_once",
    "write_owner_only_content_addressed_local_archive",
)
REQUIRED_HOST_CODE_PATHS = tuple(
    dict.fromkeys(
        (
            *formal.REQUIRED_HOST_CODE_PATHS,
            "research/analyst_revisions_v2_qc/fundamental_universe_discovery.py",
            "research/analyst_revisions_v2_qc/"
            "fundamental_universe_discovery_submission_adapter.py",
        )
    )
)

_LAUNCH_AUTHORITIES: dict[int, tuple[object, ...]] = {}
_TERMINAL_AUTHORITIES: dict[int, tuple[object, ...]] = {}
_OUTPUT_AUTHORITIES: dict[int, tuple[object, ...]] = {}
_RETURN_AUTHORITIES_LOCK = threading.RLock()


def _canonical(value: object) -> bytes:
    try:
        return canonical_json_bytes(value)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise FundamentalDiscoverySubmissionError(
            "discovery submission value is not canonical JSON"
        ) from exc


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise FundamentalDiscoverySubmissionError(f"{name} is not SHA-256")
    return value


def _safe_id(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise FundamentalDiscoverySubmissionError(f"{name} is not a safe identifier")
    return value


def _safe_key(value: object, name: str) -> str:
    if (
        type(value) is not str
        or _SAFE_KEY.fullmatch(value) is None
        or value.startswith("/")
        or "//" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise FundamentalDiscoverySubmissionError(f"{name} is not a safe key")
    return value


def _utc(value: object, name: str) -> str:
    if type(value) is not str or not value.endswith("Z"):
        raise FundamentalDiscoverySubmissionError(f"{name} is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FundamentalDiscoverySubmissionError(
            f"{name} is not canonical UTC"
        ) from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise FundamentalDiscoverySubmissionError(f"{name} is not canonical UTC")
    return value


def _identified(schema: str, prefix: str, record: dict[str, object]):
    digest = hashlib.sha256(_canonical({"schema": schema, **record})).hexdigest()
    return prefix + digest[:24], digest


def _private_directory(path: Path, name: str) -> Path:
    if type(path) is not type(Path()) or not path.is_absolute() or ".." in path.parts:
        raise FundamentalDiscoverySubmissionError(f"{name} must be an absolute Path")
    try:
        requested = path.absolute()
        observed = requested.lstat()
        resolved = requested.resolve(strict=True)
    except OSError as exc:
        raise FundamentalDiscoverySubmissionError(f"{name} is unavailable") from exc
    if (
        stat.S_ISLNK(observed.st_mode)
        or not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) != 0o700
    ):
        raise FundamentalDiscoverySubmissionError(
            f"{name} must be an owner-only nonsymlink directory"
        )
    return resolved


def _read_private_file(path: Path, name: str, maximum: int):
    try:
        before = path.lstat()
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            payload = stream.read(maximum + 1)
        after = path.lstat()
    except OSError as exc:
        raise FundamentalDiscoverySubmissionError(f"{name} is unavailable") from exc
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
        or not 0 < len(payload) <= maximum
        or len(payload) != before.st_size
        or any(
            (
                item.st_dev,
                item.st_ino,
                item.st_size,
                item.st_mtime_ns,
                item.st_ctime_ns,
            )
            != identity
            for item in (opened, after)
        )
    ):
        raise FundamentalDiscoverySubmissionError(
            f"{name} must be one stable owner-only regular file"
        )
    return payload, identity


def _write_private_file(path: Path, payload: bytes, name: str) -> None:
    if type(payload) is not bytes or not payload:
        raise FundamentalDiscoverySubmissionError(f"{name} payload is empty")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            view = memoryview(payload)
            while view:
                count = os.write(descriptor, view)
                if count <= 0:
                    raise OSError("short write")
                view = view[count:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise FundamentalDiscoverySubmissionError(f"{name} could not be created") from exc


def _write_private_file_atomically(path: Path, payload: bytes, name: str) -> None:
    """Publish one immutable owner-only file after all bytes are durable.

    The hard-link publication is the POSIX no-replace primitive available on
    every supported lane host.  A colliding final or staging name refuses; it
    never overwrites an earlier diagnostic.
    """

    parent = _private_directory(path.parent, f"{name} parent")
    if path.parent.resolve(strict=True) != parent:
        raise FundamentalDiscoverySubmissionError(f"{name} parent changed")
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise FundamentalDiscoverySubmissionError(
            f"{name} destination is unavailable"
        ) from exc
    else:
        raise FundamentalDiscoverySubmissionError(f"{name} already exists")

    staging = parent / ("." + path.name + ".staging")
    _write_private_file(staging, payload, f"{name} staging")
    try:
        os.link(staging, path, follow_symlinks=False)
    except OSError as exc:
        raise FundamentalDiscoverySubmissionError(
            f"{name} could not be published"
        ) from exc

    # From this point the final name refers to the already-fsynced complete
    # inode.  Failure to fsync either directory transition is not a partial
    # receipt, but its crash durability is unknown and must be named as such.
    try:
        directory_descriptor = os.open(
            parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        os.unlink(staging)
        directory_descriptor = os.open(
            parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise FundamentalDiscoveryDiagnosticPublicationAmbiguous(
            f"{name} was linked completely but publication durability is ambiguous"
        ) from exc

    observed, _identity = _read_private_file(
        path, name, MAX_PROJECT_SCHEMA_DIAGNOSTIC_BYTES
    )
    if observed != payload:
        raise FundamentalDiscoverySubmissionError(f"{name} bytes changed")


def _json_type_label(value: object) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) in (int, float):
        return "number"
    if type(value) is str:
        return "string"
    if type(value) is list:
        return "array"
    if type(value) is dict:
        return "object"
    raise FundamentalDiscoverySubmissionError(
        "projects/read diagnostic observed a non-JSON value"
    )


def _diagnostic_field_inventory(value: object) -> dict[str, object]:
    label = _json_type_label(value)
    if type(value) is not dict:
        return {"json_type": label, "fields": []}
    if len(value) > MAX_PROJECT_SCHEMA_DIAGNOSTIC_FIELDS:
        return {
            "json_type": "object",
            "fields": [
                {
                    "field_name": "__oversized_field_inventory_refused__",
                    "json_type": "object",
                }
            ],
        }
    fields = []
    for key, child in value.items():
        child_label = _json_type_label(child)
        if (
            type(key) is str
            and _SAFE_DIAGNOSTIC_FIELD_NAME.fullmatch(key) is not None
        ):
            field_name = key
        else:
            field_name = "__unsafe_field_name_redacted__"
        fields.append({"field_name": field_name, "json_type": child_label})
    fields.sort(key=lambda item: (item["field_name"], item["json_type"]))
    return {"json_type": "object", "fields": fields}


def _projects_read_schema_diagnostic_observation(
    response: object,
) -> dict[str, object]:
    top_level = _diagnostic_field_inventory(response)
    project_shapes = []
    if type(response) is dict and type(response.get("projects")) is list:
        projects = response["projects"]
        if len(projects) > MAX_PROJECT_SCHEMA_DIAGNOSTIC_RECORDS:
            project_shapes = [
                {
                    "json_type": "array",
                    "fields": [
                        {
                            "field_name": (
                                "__oversized_project_inventory_refused__"
                            ),
                            "json_type": "array",
                        }
                    ],
                }
            ]
        else:
            encoded_shapes = set()
            for project in projects:
                shape = _diagnostic_field_inventory(project)
                encoded = _canonical(shape)
                if encoded not in encoded_shapes:
                    if (
                        len(encoded_shapes)
                        == MAX_PROJECT_SCHEMA_DIAGNOSTIC_UNIQUE_SHAPES
                    ):
                        project_shapes = [
                            {
                                "json_type": "object",
                                "fields": [
                                    {
                                        "field_name": (
                                            "__unique_shape_limit_refused__"
                                        ),
                                        "json_type": "object",
                                    }
                                ],
                            }
                        ]
                        break
                    encoded_shapes.add(encoded)
                    project_shapes.append(shape)
            else:
                project_shapes.sort(key=_canonical)
    return {
        "top_level": top_level,
        "project_record_shapes": project_shapes,
    }


def _project_record_schema_refused(value: object) -> bool:
    return type(value) is not dict or not set(value).issubset(
        formal._PROJECT_RECORD_KEYS
    )


def _persist_projects_read_schema_diagnostic(
    *, plan, permit, phase: str, response: object,
) -> Path:
    if phase not in {"initial_inventory", "created_project_readback"}:
        raise FundamentalDiscoverySubmissionError(
            "projects/read diagnostic phase changed"
        )
    if (
        type(permit) is not FundamentalDiscoverySubmissionPermit
        or permit.plan_id != plan.plan_id
        or permit.plan_sha256 != plan.plan_sha256
    ):
        raise FundamentalDiscoverySubmissionError(
            "projects/read diagnostic permit changed"
        )
    observation = _projects_read_schema_diagnostic_observation(response)
    record = {
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "permit_id": permit.permit_id,
        "permit_sha256": permit.permit_sha256,
        "operation": "projects/read",
        "phase": phase,
        "refusal_type": "FormalQcSubmissionError",
        "observation": observation,
        "response_values_retained": False,
        "project_names_or_content_retained": False,
        "results_statistics_logs_orders_retained": False,
    }
    receipt_id, digest = _identified(
        PROJECT_SCHEMA_DIAGNOSTIC_RECEIPT_SCHEMA,
        "arv2-qc-project-schema-diagnostic-",
        record,
    )
    payload = _canonical(
        {
            "schema": PROJECT_SCHEMA_DIAGNOSTIC_RECEIPT_SCHEMA,
            "receipt_id": receipt_id,
            "receipt_sha256": digest,
            **record,
        }
    )
    if len(payload) > MAX_PROJECT_SCHEMA_DIAGNOSTIC_BYTES:
        raise FundamentalDiscoverySubmissionError(
            "projects/read diagnostic receipt is oversized"
        )
    archive_root = _prepare_archive_root(plan)
    _private_directory(archive_root, "projects/read diagnostic archive")
    path = archive_root / PROJECT_SCHEMA_DIAGNOSTIC_FILENAME
    _write_private_file_atomically(path, payload, "projects/read diagnostic")
    return path


def _files_read_schema_diagnostic_observation(
    response: object,
) -> dict[str, object]:
    top_level = _diagnostic_field_inventory(response)
    file_shapes = []
    if type(response) is dict and type(response.get("files")) is list:
        files = response["files"]
        if len(files) > MAX_FILES_SCHEMA_DIAGNOSTIC_RECORDS:
            file_shapes = [
                {
                    "json_type": "array",
                    "fields": [
                        {
                            "field_name": (
                                "__oversized_file_inventory_refused__"
                            ),
                            "json_type": "array",
                        }
                    ],
                }
            ]
        else:
            encoded_shapes = set()
            for item in files:
                shape = _diagnostic_field_inventory(item)
                encoded = _canonical(shape)
                if encoded not in encoded_shapes:
                    if (
                        len(encoded_shapes)
                        == MAX_FILES_SCHEMA_DIAGNOSTIC_UNIQUE_SHAPES
                    ):
                        file_shapes = [
                            {
                                "json_type": "object",
                                "fields": [
                                    {
                                        "field_name": (
                                            "__unique_shape_limit_refused__"
                                        ),
                                        "json_type": "object",
                                    }
                                ],
                            }
                        ]
                        break
                    encoded_shapes.add(encoded)
                    file_shapes.append(shape)
            else:
                file_shapes.sort(key=_canonical)
    return {
        "top_level": top_level,
        "file_record_shapes": file_shapes,
    }


def _backtests_list_schema_diagnostic_observation(
    response: object,
) -> dict[str, object]:
    top_level = _diagnostic_field_inventory(response)
    backtest_shapes = []
    if type(response) is dict and type(response.get("backtests")) is list:
        backtests = response["backtests"]
        if len(backtests) > MAX_BACKTEST_LIST_SCHEMA_DIAGNOSTIC_RECORDS:
            backtest_shapes = [
                {
                    "json_type": "array",
                    "fields": [
                        {
                            "field_name": (
                                "__oversized_backtest_inventory_refused__"
                            ),
                            "json_type": "array",
                        }
                    ],
                }
            ]
        else:
            encoded_shapes = set()
            for item in backtests:
                shape = _diagnostic_field_inventory(item)
                encoded = _canonical(shape)
                if encoded not in encoded_shapes:
                    if (
                        len(encoded_shapes)
                        == MAX_BACKTEST_LIST_SCHEMA_DIAGNOSTIC_UNIQUE_SHAPES
                    ):
                        backtest_shapes = [
                            {
                                "json_type": "object",
                                "fields": [
                                    {
                                        "field_name": (
                                            "__unique_shape_limit_refused__"
                                        ),
                                        "json_type": "object",
                                    }
                                ],
                            }
                        ]
                        break
                    encoded_shapes.add(encoded)
                    backtest_shapes.append(shape)
            else:
                backtest_shapes.sort(key=_canonical)
    return {
        "top_level": top_level,
        "backtest_record_shapes": backtest_shapes,
    }


def _persist_files_read_schema_diagnostic(
    *, plan, permit, phase: str, response: object,
) -> Path:
    if phase not in {"initial_source_inventory", "source_readback"}:
        raise FundamentalDiscoverySubmissionError(
            "files/read diagnostic phase changed"
        )
    if (
        type(permit) is not FundamentalDiscoverySubmissionPermit
        or permit.plan_id != plan.plan_id
        or permit.plan_sha256 != plan.plan_sha256
    ):
        raise FundamentalDiscoverySubmissionError(
            "files/read diagnostic permit changed"
        )
    record = {
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "permit_id": permit.permit_id,
        "permit_sha256": permit.permit_sha256,
        "operation": "files/read",
        "phase": phase,
        "refusal_type": "FormalQcSubmissionError",
        "observation": _files_read_schema_diagnostic_observation(response),
        "response_values_retained": False,
        "file_names_or_content_retained": False,
        "source_or_project_values_retained": False,
        "results_statistics_logs_orders_retained": False,
    }
    receipt_id, digest = _identified(
        FILES_SCHEMA_DIAGNOSTIC_RECEIPT_SCHEMA,
        "arv2-qc-file-schema-diagnostic-",
        record,
    )
    payload = _canonical(
        {
            "schema": FILES_SCHEMA_DIAGNOSTIC_RECEIPT_SCHEMA,
            "receipt_id": receipt_id,
            "receipt_sha256": digest,
            **record,
        }
    )
    if len(payload) > MAX_PROJECT_SCHEMA_DIAGNOSTIC_BYTES:
        raise FundamentalDiscoverySubmissionError(
            "files/read diagnostic receipt is oversized"
        )
    archive_root = _prepare_archive_root(plan)
    _private_directory(archive_root, "files/read diagnostic archive")
    path = archive_root / FILES_SCHEMA_DIAGNOSTIC_FILENAME
    _write_private_file_atomically(path, payload, "files/read diagnostic")
    return path


def _persist_backtests_list_schema_diagnostic(
    *, plan, permit, launch, response: object, _require_launch_receipt,
) -> Path:
    _require_launch_receipt(launch, plan, permit)
    if (
        type(permit) is not FundamentalDiscoverySubmissionPermit
        or type(launch) is not FundamentalDiscoveryLaunchReceipt
        or permit.plan_id != plan.plan_id
        or permit.plan_sha256 != plan.plan_sha256
        or launch.permit_sha256 != permit.permit_sha256
        or launch.plan_sha256 != plan.plan_sha256
    ):
        raise FundamentalDiscoverySubmissionError(
            "backtests/list diagnostic authority changed"
        )
    record = {
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "permit_id": permit.permit_id,
        "permit_sha256": permit.permit_sha256,
        "launch_receipt_id": launch.receipt_id,
        "launch_receipt_sha256": launch.receipt_sha256,
        "operation": "backtests/list",
        "phase": "terminal_status_poll",
        "refusal_type": "FormalQcSubmissionError",
        "observation": _backtests_list_schema_diagnostic_observation(response),
        "response_values_retained": False,
        "backtest_names_or_identifiers_retained": False,
        "results_statistics_logs_orders_retained": False,
    }
    receipt_id, digest = _identified(
        BACKTEST_LIST_SCHEMA_DIAGNOSTIC_RECEIPT_SCHEMA,
        "arv2-qc-backtest-list-schema-diagnostic-",
        record,
    )
    payload = _canonical(
        {
            "schema": BACKTEST_LIST_SCHEMA_DIAGNOSTIC_RECEIPT_SCHEMA,
            "receipt_id": receipt_id,
            "receipt_sha256": digest,
            **record,
        }
    )
    if len(payload) > MAX_PROJECT_SCHEMA_DIAGNOSTIC_BYTES:
        raise FundamentalDiscoverySubmissionError(
            "backtests/list diagnostic receipt is oversized"
        )
    archive_root = _prepare_archive_root(plan)
    _private_directory(archive_root, "backtests/list diagnostic archive")
    path = archive_root / BACKTEST_LIST_SCHEMA_DIAGNOSTIC_FILENAME
    _write_private_file_atomically(path, payload, "backtests/list diagnostic")
    return path


@dataclasses.dataclass(frozen=True, slots=True)
class FundamentalDiscoveryHostSourceBinding:
    path: str
    content_sha256: str
    byte_count: int

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class FundamentalDiscoveryHostClosureBinding:
    closure_id: str
    closure_sha256: str
    sources: tuple[FundamentalDiscoveryHostSourceBinding, ...]


def _read_host_sources(
    _sealed_root: Path = Path(__file__).resolve().parents[2],
    _sealed_paths: tuple[str, ...] = REQUIRED_HOST_CODE_PATHS,
) -> tuple[FundamentalDiscoveryHostSourceBinding, ...]:
    result = []
    for relative in _sealed_paths:
        try:
            path = (_sealed_root / relative).resolve(strict=True)
            path.relative_to(_sealed_root)
            payload = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise FundamentalDiscoverySubmissionError(
                "discovery host source closure is unavailable"
            ) from exc
        if not payload or b"\r" in payload or not payload.endswith(b"\n"):
            raise FundamentalDiscoverySubmissionError(
                "discovery host source is not canonical LF"
            )
        result.append(
            FundamentalDiscoveryHostSourceBinding(
                path=relative,
                content_sha256=hashlib.sha256(payload).hexdigest(),
                byte_count=len(payload),
            )
        )
    return tuple(result)


def build_fundamental_discovery_host_closure_binding():
    sources = _read_host_sources()
    seed = {
        "schema": HOST_CLOSURE_SCHEMA,
        "closure_id": None,
        "closure_sha256": None,
        "sources": [item.to_record() for item in sources],
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    return FundamentalDiscoveryHostClosureBinding(
        closure_id="arv2-qc-fundamental-discovery-host-" + digest[:24],
        closure_sha256=digest,
        sources=sources,
    )


def verify_fundamental_discovery_host_closure_live(value) -> None:
    if (
        type(value) is not FundamentalDiscoveryHostClosureBinding
        or tuple(item.path for item in value.sources) != REQUIRED_HOST_CODE_PATHS
        or any(
            type(item) is not FundamentalDiscoveryHostSourceBinding
            or _HEX.fullmatch(item.content_sha256) is None
            or type(item.byte_count) is not int
            or item.byte_count < 1
            for item in value.sources
        )
    ):
        raise FundamentalDiscoverySubmissionError("discovery host closure changed")
    seed = {
        "schema": HOST_CLOSURE_SCHEMA,
        "closure_id": None,
        "closure_sha256": None,
        "sources": [item.to_record() for item in value.sources],
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    if (
        value.closure_sha256 != digest
        or value.closure_id != "arv2-qc-fundamental-discovery-host-" + digest[:24]
        or _read_host_sources() != value.sources
    ):
        raise FundamentalDiscoverySubmissionError(
            "live discovery host closure changed"
        )


def _transport_call(closure, client, capability, method, *args, **kwargs):
    verify_fundamental_discovery_host_closure_live(closure)
    return formal._transport_call(client, capability, method, *args, **kwargs)


@dataclasses.dataclass(frozen=True, slots=True)
class FundamentalDiscoveryUploadEntry:
    role: str
    object_store_key: str
    content_sha256: str
    content_md5: str
    byte_count: int
    payload: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        return {
            "role": self.role,
            "object_store_key": self.object_store_key,
            "content_sha256": self.content_sha256,
            "content_md5": self.content_md5,
            "byte_count": self.byte_count,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class FundamentalDiscoverySubmissionPlan:
    plan_id: str
    plan_sha256: str
    organization_id: str
    organization_id_sha256: str
    attempt_ordinal: int
    attempt_binding_sha256: str
    project_name: str
    qc_default_research_notebook_path: str
    maximum_default_notebook_deletions: int
    backtest_name: str
    projection_id: str
    projection_sha256: str
    discovery_plan_id: str
    discovery_plan_sha256: str
    discovery_plan_artifact_sha256: str
    project_source_set_sha256: str
    terminal_package_key: str
    upload_entry: FundamentalDiscoveryUploadEntry
    source_files: tuple[FundamentalDiscoveryProjectSource, ...]
    review_directory: Path
    archive_root: Path
    compile_poll_limit: int
    status_poll_limit: int
    maximum_backtest_submissions: int
    maximum_output_object_reads: int
    projection: FundamentalUniverseDiscoveryQcProjection = dataclasses.field(
        repr=False
    )


def _rebuild_projection(projection):
    projection = require_fundamental_universe_discovery_qc_projection(projection)
    by_path = {item.project_path: item for item in projection.source_files}
    worker = by_path["fundamental_universe_discovery_worker.py"].content
    runtime = by_path["fundamental_universe_discovery_runtime.py"].content
    marker = b"__ARV2_FUNDAMENTAL_DISCOVERY_CONTRACT_SHA256__"
    contract = CONTRACT_SHA256.encode("ascii")
    if worker.count(contract) != 1 or runtime.count(contract) != 1:
        raise FundamentalDiscoverySubmissionError(
            "projected discovery contract marker changed"
        )
    rebuilt = build_fundamental_universe_discovery_qc_projection(
        plan_bytes=projection.plan_bytes,
        worker_source_bytes=worker.replace(contract, marker),
        runtime_source_bytes=runtime.replace(contract, marker),
    )
    if rebuilt != projection:
        raise FundamentalDiscoverySubmissionError(
            "discovery projection does not rebuild exactly"
        )
    return projection


def _plan_record(
    *, projection, organization_id_sha256: str, review_directory: Path,
    archive_root: Path, upload_entry: FundamentalDiscoveryUploadEntry,
    attempt_ordinal: int, attempt_binding_sha256: str, project_name: str,
):
    return {
        "schema": PLAN_SCHEMA,
        "plan_id": None,
        "plan_sha256": None,
        "organization_id_sha256": organization_id_sha256,
        "attempt_ordinal": attempt_ordinal,
        "attempt_binding_sha256": attempt_binding_sha256,
        "project_name": project_name,
        "qc_default_research_notebook_path": (
            QC_DEFAULT_RESEARCH_NOTEBOOK_PATH
        ),
        "maximum_default_notebook_deletions": (
            MAX_DEFAULT_NOTEBOOK_DELETIONS
        ),
        "backtest_name": projection.backtest_name,
        "projection_id": projection.projection_id,
        "projection_sha256": projection.projection_sha256,
        "discovery_plan_id": projection.plan_id,
        "discovery_plan_sha256": projection.plan_sha256,
        "discovery_plan_artifact_sha256": projection.plan_artifact_sha256,
        "project_source_set_sha256": projection.project_source_set_sha256,
        "terminal_package_key": projection.terminal_package_key,
        "upload_entry": upload_entry.to_record(),
        "source_files": [item.to_record() for item in projection.source_files],
        "review_directory": str(review_directory),
        "archive_root": str(archive_root),
        "compile_poll_limit": MAX_COMPILE_POLLS,
        "status_poll_limit": MAX_STATUS_POLLS,
        "maximum_backtest_submissions": 1,
        "maximum_output_object_reads": MAX_TERMINAL_SHARDS + 2,
        "include_statistics": False,
        "outcome_result_log_order_access": False,
        "retry_after_ambiguity": False,
    }


def build_fundamental_discovery_submission_plan(
    *, projection: FundamentalUniverseDiscoveryQcProjection,
    organization_id: str, review_directory: Path, archive_root: Path,
    attempt_ordinal: int,
) -> FundamentalDiscoverySubmissionPlan:
    projection = _rebuild_projection(projection)
    _safe_id(organization_id, "organization_id")
    review_root = _private_directory(review_directory, "discovery review directory")
    if (
        type(archive_root) is not type(Path())
        or not archive_root.is_absolute()
        or ".." in archive_root.parts
        or archive_root.parent.resolve(strict=True) != review_root
        or archive_root.name != "fundamental-universe-discovery-archive"
    ):
        raise FundamentalDiscoverySubmissionError(
            "discovery archive target must be the exact private review-directory child"
        )
    payload = projection.plan_bytes
    upload = FundamentalDiscoveryUploadEntry(
        role="discovery_plan",
        object_store_key=projection.plan_object_store_key,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        content_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        byte_count=len(payload),
        payload=payload,
    )
    organization_hash = hashlib.sha256(organization_id.encode("utf-8")).hexdigest()
    if (
        type(attempt_ordinal) is not int
        or not 1 <= attempt_ordinal <= 999_999
    ):
        raise FundamentalDiscoverySubmissionError(
            "discovery attempt ordinal changed"
        )
    attempt_binding_sha256 = hashlib.sha256(
        _canonical(
            {
                "schema": "arv2-qc-fundamental-discovery-attempt-binding-v1",
                "attempt_ordinal": attempt_ordinal,
                "projection_id": projection.projection_id,
                "projection_sha256": projection.projection_sha256,
                "organization_id_sha256": organization_hash,
                "review_directory": str(review_root),
                "archive_root": str(archive_root.absolute()),
            }
        )
    ).hexdigest()
    project_name = _safe_id(
        f"{projection.project_name}_A{attempt_ordinal:06d}_"
        f"{attempt_binding_sha256[:32]}",
        "attempt-specific discovery project name",
    )
    if len(project_name.encode("utf-8")) > MAX_DISCOVERY_PROJECT_NAME_BYTES:
        raise FundamentalDiscoverySubmissionError(
            "attempt-specific discovery project name is oversized"
        )
    record = _plan_record(
        projection=projection,
        organization_id_sha256=organization_hash,
        review_directory=review_root,
        archive_root=archive_root.absolute(),
        upload_entry=upload,
        attempt_ordinal=attempt_ordinal,
        attempt_binding_sha256=attempt_binding_sha256,
        project_name=project_name,
    )
    digest = hashlib.sha256(_canonical(record)).hexdigest()
    record["plan_id"] = "arv2-qc-fundamental-discovery-submission-" + digest[:24]
    record["plan_sha256"] = digest
    return FundamentalDiscoverySubmissionPlan(
        plan_id=record["plan_id"],
        plan_sha256=digest,
        organization_id=organization_id,
        organization_id_sha256=organization_hash,
        attempt_ordinal=attempt_ordinal,
        attempt_binding_sha256=attempt_binding_sha256,
        project_name=project_name,
        qc_default_research_notebook_path=(
            QC_DEFAULT_RESEARCH_NOTEBOOK_PATH
        ),
        maximum_default_notebook_deletions=(
            MAX_DEFAULT_NOTEBOOK_DELETIONS
        ),
        backtest_name=projection.backtest_name,
        projection_id=projection.projection_id,
        projection_sha256=projection.projection_sha256,
        discovery_plan_id=projection.plan_id,
        discovery_plan_sha256=projection.plan_sha256,
        discovery_plan_artifact_sha256=projection.plan_artifact_sha256,
        project_source_set_sha256=projection.project_source_set_sha256,
        terminal_package_key=projection.terminal_package_key,
        upload_entry=upload,
        source_files=projection.source_files,
        review_directory=review_root,
        archive_root=archive_root.absolute(),
        compile_poll_limit=MAX_COMPILE_POLLS,
        status_poll_limit=MAX_STATUS_POLLS,
        maximum_backtest_submissions=1,
        maximum_output_object_reads=MAX_TERMINAL_SHARDS + 2,
        projection=projection,
    )


def require_fundamental_discovery_submission_plan(value):
    if type(value) is not FundamentalDiscoverySubmissionPlan:
        raise FundamentalDiscoverySubmissionError("discovery submission plan type changed")
    rebuilt = build_fundamental_discovery_submission_plan(
        projection=value.projection,
        organization_id=value.organization_id,
        review_directory=value.review_directory,
        archive_root=value.archive_root,
        attempt_ordinal=value.attempt_ordinal,
    )
    if rebuilt != value:
        raise FundamentalDiscoverySubmissionError("discovery submission plan changed")
    return value


def _review_claim_document(plan):
    require_fundamental_discovery_submission_plan(plan)
    seed = {
        "schema": REVIEW_CLAIM_SCHEMA,
        "claim_id": None,
        "claim_sha256": None,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "attempt_ordinal": plan.attempt_ordinal,
        "attempt_binding_sha256": plan.attempt_binding_sha256,
        "project_name": plan.project_name,
        "qc_default_research_notebook_path": (
            plan.qc_default_research_notebook_path
        ),
        "maximum_default_notebook_deletions": (
            plan.maximum_default_notebook_deletions
        ),
        "projection_id": plan.projection_id,
        "projection_sha256": plan.projection_sha256,
        "project_source_set_sha256": plan.project_source_set_sha256,
        "discovery_plan_artifact_sha256": plan.discovery_plan_artifact_sha256,
        "review_disposition": "NOT_PERFORMED_OWNER_WAIVED",
        "independent_review_complete": False,
        "authorization_basis": OWNER_REVIEW_WAIVER_BASIS,
        "owner_review_waiver_id": OWNER_REVIEW_WAIVER_ID,
        "owner_review_waiver_scope": OWNER_REVIEW_WAIVER_SCOPE,
        "post_first_formal_backtest_independent_review_required": True,
        "private_authorization_pin": True,
        "maximum_backtest_submissions": 1,
        "full_pit_universe_claim_scoped_to_qc_source": True,
        "production_preopen_input_available": False,
        "outcome_result_statistics_log_order_access": False,
        "retry_after_ambiguity": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["claim_id"] = "arv2-qc-fundamental-discovery-review-" + digest[:24]
    seed["claim_sha256"] = digest
    return seed


def render_fundamental_discovery_review_claim_candidate(plan) -> bytes:
    """Render the exact private pin for the owner's bounded review waiver.

    These bytes expressly do not claim that independent review is complete.
    Execution still requires the owner's detached signature over an authority
    payload that repeats and binds this waiver state.
    """

    return _canonical(_review_claim_document(plan))


@dataclasses.dataclass(frozen=True, slots=True)
class FundamentalDiscoveryReviewClaim:
    claim_id: str
    claim_sha256: str
    plan_id: str
    plan_sha256: str
    review_disposition: str
    independent_review_complete: bool
    authorization_basis: str
    owner_review_waiver_id: str
    owner_review_waiver_scope: str
    post_first_formal_backtest_independent_review_required: bool
    pin_path: Path
    pin_content_sha256: str
    pin_byte_count: int
    _pin_bytes: bytes = dataclasses.field(repr=False)
    _stat_identity: tuple[int, int, int, int, int] = dataclasses.field(repr=False)


def load_fundamental_discovery_review_claim(plan):
    require_fundamental_discovery_submission_plan(plan)
    path = plan.review_directory / REVIEW_CLAIM_FILENAME
    payload, identity = _read_private_file(path, "discovery review claim", MAX_CONTROL_BYTES)
    expected = render_fundamental_discovery_review_claim_candidate(plan)
    if payload != expected:
        raise FundamentalDiscoverySubmissionError("discovery review claim changed")
    record = _review_claim_document(plan)
    return FundamentalDiscoveryReviewClaim(
        claim_id=record["claim_id"],
        claim_sha256=record["claim_sha256"],
        plan_id=plan.plan_id,
        plan_sha256=plan.plan_sha256,
        review_disposition=record["review_disposition"],
        independent_review_complete=record["independent_review_complete"],
        authorization_basis=record["authorization_basis"],
        owner_review_waiver_id=record["owner_review_waiver_id"],
        owner_review_waiver_scope=record["owner_review_waiver_scope"],
        post_first_formal_backtest_independent_review_required=(
            record["post_first_formal_backtest_independent_review_required"]
        ),
        pin_path=path,
        pin_content_sha256=hashlib.sha256(payload).hexdigest(),
        pin_byte_count=len(payload),
        _pin_bytes=payload,
        _stat_identity=identity,
    )


def require_fundamental_discovery_review_claim(value, plan):
    if type(value) is not FundamentalDiscoveryReviewClaim:
        raise FundamentalDiscoverySubmissionError("exact discovery review claim required")
    loaded = load_fundamental_discovery_review_claim(plan)
    if loaded != value:
        raise FundamentalDiscoverySubmissionError("discovery review claim changed")
    return value


def _execution_authority_candidate(plan, claim, closure):
    require_fundamental_discovery_submission_plan(plan)
    require_fundamental_discovery_review_claim(claim, plan)
    verify_fundamental_discovery_host_closure_live(closure)
    return _canonical(
        {
            "schema": EXECUTION_AUTHORITY_SCHEMA,
            "plan_id": plan.plan_id,
            "plan_sha256": plan.plan_sha256,
            "review_claim_id": claim.claim_id,
            "review_claim_sha256": claim.claim_sha256,
            "review_pin_content_sha256": claim.pin_content_sha256,
            "review_authorization": {
                "review_disposition": claim.review_disposition,
                "independent_review_complete": (
                    claim.independent_review_complete
                ),
                "authorization_basis": claim.authorization_basis,
                "owner_review_waiver_id": claim.owner_review_waiver_id,
                "owner_review_waiver_scope": claim.owner_review_waiver_scope,
                "post_first_formal_backtest_independent_review_required": (
                    claim.post_first_formal_backtest_independent_review_required
                ),
            },
            "projection_id": plan.projection_id,
            "projection_sha256": plan.projection_sha256,
            "discovery_plan_id": plan.discovery_plan_id,
            "discovery_plan_artifact_sha256": plan.discovery_plan_artifact_sha256,
            "project_source_set_sha256": plan.project_source_set_sha256,
            "organization_id_sha256": plan.organization_id_sha256,
            "attempt_ordinal": plan.attempt_ordinal,
            "attempt_binding_sha256": plan.attempt_binding_sha256,
            "project_name": plan.project_name,
            "qc_default_research_notebook_path": (
                plan.qc_default_research_notebook_path
            ),
            "maximum_default_notebook_deletions": (
                plan.maximum_default_notebook_deletions
            ),
            "backtest_name": plan.backtest_name,
            "terminal_package_key": plan.terminal_package_key,
            "archive_root": str(plan.archive_root),
            "host_closure": {
                "closure_id": closure.closure_id,
                "closure_sha256": closure.closure_sha256,
                "sources": [item.to_record() for item in closure.sources],
            },
            "actions": list(EXECUTION_ACTIONS),
            "maximum_backtest_submissions": 1,
            "maximum_output_object_reads": plan.maximum_output_object_reads,
            "include_statistics": False,
            "outcome_result_statistics_log_order_access": False,
            "retry_after_ambiguity": False,
        }
    )


def render_fundamental_discovery_execution_authority_candidate(plan, claim):
    """Render the exact bytes the owner must sign for PREOPEN_EXECUTION."""

    return _execution_authority_candidate(
        plan, claim, build_fundamental_discovery_host_closure_binding()
    )


def _require_owner_signature(value, payload):
    try:
        require_preopen_execution_owner_signature(value, authority_payload=payload)
    except OwnerSignatureAuthorityError as exc:
        raise FundamentalDiscoverySubmissionError(
            "detached owner PREOPEN_EXECUTION signature is unavailable"
        ) from exc


@dataclasses.dataclass(frozen=True, slots=True)
class FundamentalDiscoverySubmissionPermit:
    permit_id: str
    permit_sha256: str
    plan_id: str
    plan_sha256: str
    review_claim_sha256: str
    owner_signature_authority_sha256: str
    started_at_utc: str
    submission_attempt_count: int
    ambiguous_submission_consumes_permit: bool
    retry_authorized: bool
    permit_path: Path
    _permit_bytes: bytes = dataclasses.field(repr=False)


def _spend_permit(plan, claim, owner_signature, started_at_utc):
    require_fundamental_discovery_review_claim(claim, plan)
    _utc(started_at_utc, "discovery submission started_at")
    if type(owner_signature) is not OwnerSignatureAuthority:
        raise FundamentalDiscoverySubmissionError("exact owner signature authority required")
    seed = {
        "schema": PERMIT_SCHEMA,
        "permit_id": None,
        "permit_sha256": None,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "review_claim_sha256": claim.claim_sha256,
        "owner_signature_authority_sha256": owner_signature.authority_sha256,
        "started_at_utc": started_at_utc,
        "submission_attempt_count": 1,
        "ambiguous_submission_consumes_permit": True,
        "retry_authorized": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["permit_id"] = "arv2-qc-fundamental-discovery-permit-" + digest[:24]
    seed["permit_sha256"] = digest
    payload = _canonical(seed)
    path = plan.review_directory / PERMIT_FILENAME
    try:
        _write_private_file(path, payload, "discovery one-use permit")
    except FundamentalDiscoverySubmissionError as exc:
        raise FundamentalDiscoverySubmissionLocked(
            "permit", seed["permit_id"], "permit already spent or unavailable"
        ) from exc
    return FundamentalDiscoverySubmissionPermit(
        permit_id=seed["permit_id"],
        permit_sha256=digest,
        plan_id=plan.plan_id,
        plan_sha256=plan.plan_sha256,
        review_claim_sha256=claim.claim_sha256,
        owner_signature_authority_sha256=owner_signature.authority_sha256,
        started_at_utc=started_at_utc,
        submission_attempt_count=1,
        ambiguous_submission_consumes_permit=True,
        retry_authorized=False,
        permit_path=path,
        _permit_bytes=payload,
    )


def require_fundamental_discovery_submission_permit(value, plan, claim):
    require_fundamental_discovery_review_claim(claim, plan)
    if type(value) is not FundamentalDiscoverySubmissionPermit:
        raise FundamentalDiscoverySubmissionError("discovery permit type changed")
    payload, _identity = _read_private_file(
        value.permit_path, "discovery permit", MAX_CONTROL_BYTES
    )
    if (
        payload != value._permit_bytes
        or value.plan_id != plan.plan_id
        or value.plan_sha256 != plan.plan_sha256
        or value.review_claim_sha256 != claim.claim_sha256
        or value.submission_attempt_count != 1
        or value.ambiguous_submission_consumes_permit is not True
        or value.retry_authorized is not False
    ):
        raise FundamentalDiscoverySubmissionError("discovery permit changed")
    raw = json.loads(payload)
    seed = dict(raw)
    seed["permit_id"] = None
    seed["permit_sha256"] = None
    if (
        _canonical(raw) != payload
        or raw.get("permit_id") != value.permit_id
        or raw.get("permit_sha256") != value.permit_sha256
        or hashlib.sha256(_canonical(seed)).hexdigest() != value.permit_sha256
    ):
        raise FundamentalDiscoverySubmissionError("discovery permit identity changed")
    return value


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FundamentalDiscoveryLaunchReceipt:
    receipt_id: str
    receipt_sha256: str
    permit_id: str
    permit_sha256: str
    plan_id: str
    plan_sha256: str
    project_id: int
    compile_id: str
    backtest_id: str
    backtest_name: str
    initial_status: str
    uploaded_object_count: int
    uploaded_source_count: int
    submission_count: int
    include_statistics: bool
    outcome_result_log_order_accessed: bool


def _launch_record(value: FundamentalDiscoveryLaunchReceipt) -> dict[str, object]:
    return {
        "permit_id": value.permit_id,
        "permit_sha256": value.permit_sha256,
        "plan_id": value.plan_id,
        "plan_sha256": value.plan_sha256,
        "project_id": value.project_id,
        "compile_id": value.compile_id,
        "backtest_id": value.backtest_id,
        "backtest_name": value.backtest_name,
        "initial_status": value.initial_status,
        "uploaded_object_count": value.uploaded_object_count,
        "uploaded_source_count": value.uploaded_source_count,
        "submission_count": value.submission_count,
        "include_statistics": value.include_statistics,
        "outcome_result_log_order_accessed": (
            value.outcome_result_log_order_accessed
        ),
    }


def _launch(plan, permit, project_id, compile_id, backtest_id, status):
    record = {
        "permit_id": permit.permit_id,
        "permit_sha256": permit.permit_sha256,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "project_id": project_id,
        "compile_id": compile_id,
        "backtest_id": backtest_id,
        "backtest_name": plan.backtest_name,
        "initial_status": status,
        "uploaded_object_count": 1,
        "uploaded_source_count": len(plan.source_files),
        "submission_count": 1,
        "include_statistics": False,
        "outcome_result_log_order_accessed": False,
    }
    identity, digest = _identified(
        LAUNCH_SCHEMA, "arv2-qc-fundamental-discovery-launch-", record
    )
    return FundamentalDiscoveryLaunchReceipt(
        receipt_id=identity, receipt_sha256=digest, **record
    )


def _require_launch_impl(value, plan, permit, *, _authority_current):
    if type(value) is not FundamentalDiscoveryLaunchReceipt:
        raise FundamentalDiscoverySubmissionError(
            "discovery launch receipt changed type"
        )
    registered = _authority_current(value)
    if (
        registered is None
        or registered[0]() is not value
        or registered[1] is not plan
        or registered[2] is not permit
        or registered[4] != os.getpid()
        or type(value.project_id) is not int
        or value.project_id < 1
        or value != _launch(
            plan, permit, value.project_id, value.compile_id,
            value.backtest_id, value.initial_status,
        )
        or registered[3]
        != _canonical({"schema": LAUNCH_SCHEMA, **_launch_record(value)})
    ):
        raise FundamentalDiscoverySubmissionError(
            "discovery launch receipt lacks process-return authority"
        )
    return value


def _wait(seconds: int) -> None:
    if type(seconds) is not int or seconds not in {
        COMPILE_POLL_SECONDS,
        STATUS_POLL_SECONDS,
    }:
        raise FundamentalDiscoverySubmissionError("poll interval changed")
    time.sleep(seconds)


def _execution_preflight(plan, claim, owner_signature):
    closure = build_fundamental_discovery_host_closure_binding()
    payload = _execution_authority_candidate(plan, claim, closure)
    _require_owner_signature(owner_signature, payload)
    verify_fundamental_discovery_host_closure_live(closure)
    require_fundamental_discovery_submission_plan(plan)
    require_fundamental_discovery_review_claim(claim, plan)
    return closure


def _execute_fundamental_discovery_submission_once_impl(
    *, plan: FundamentalDiscoverySubmissionPlan,
    review_claim: FundamentalDiscoveryReviewClaim,
    owner_signature: OwnerSignatureAuthority | None,
    client: FormalQcTransport,
    started_at_utc: str,
    _transport_capability_minter,
    _authority_register_launch,
    _require_launch_receipt,
):
    closure = _execution_preflight(plan, review_claim, owner_signature)
    formal._require_concrete_transport(client)
    permit = _spend_permit(plan, review_claim, owner_signature, started_at_utc)
    capability = _transport_capability_minter(
        transport=client,
        scope="submission",
        binding_record={
            "schema": "arv2-qc-fundamental-discovery-submission-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "review_claim_sha256": review_claim.claim_sha256,
            "permit_sha256": permit.permit_sha256,
        },
        call_budget={
            "authenticate": 1,
            "projects/read": 2,
            "projects/create": 1,
            "object/set": 1,
            "object/properties": 1,
            "files/read": 2,
            "files/create": len(plan.source_files),
            "files/update": len(plan.source_files),
            "files/delete": plan.maximum_default_notebook_deletions,
            "compile/create": 1,
            "compile/read": plan.compile_poll_limit,
            "backtests/create": 1,
        },
    )
    try:
        _transport_call(closure, client, capability, "_request_json", "authenticate", {})
        inventory_response = _transport_call(
            closure, client, capability, "_request_json", "projects/read", {}
        )
        try:
            inventory = formal._read_project_inventory(inventory_response)
        except formal.FormalQcSubmissionError:
            _persist_projects_read_schema_diagnostic(
                plan=plan,
                permit=permit,
                phase="initial_inventory",
                response=inventory_response,
            )
            raise
        if any(
            type(item) is dict and item.get("name") == plan.project_name
            for item in inventory
        ):
            raise FundamentalDiscoverySubmissionError(
                "exact discovery project already exists"
            )
        created = formal._created_project(
            _transport_call(
                closure,
                client,
                capability,
                "_request_json",
                "projects/create",
                {"name": plan.project_name, "language": "Py"},
            ),
            name=plan.project_name,
            organization_id=plan.organization_id,
        )
        project_id = int(created["projectId"])
        exact_response = _transport_call(
            closure,
            client,
            capability,
            "_request_json",
            "projects/read",
            {"projectId": project_id},
        )
        try:
            exact = formal._read_project_inventory(exact_response)
        except formal.FormalQcSubmissionError:
            _persist_projects_read_schema_diagnostic(
                plan=plan,
                permit=permit,
                phase="created_project_readback",
                response=exact_response,
            )
            raise
        if len(exact) != 1:
            raise FundamentalDiscoverySubmissionError(
                "created discovery project identity is ambiguous"
            )
        try:
            formal._project_record(
                exact[0],
                name=plan.project_name,
                organization_id=plan.organization_id,
            )
        except formal.FormalQcSubmissionError:
            if _project_record_schema_refused(exact[0]):
                _persist_projects_read_schema_diagnostic(
                    plan=plan,
                    permit=permit,
                    phase="created_project_readback",
                    response=exact_response,
                )
            raise
        entry = plan.upload_entry
        _transport_call(
            closure,
            client,
            capability,
            "_set_object_multipart",
            plan.organization_id,
            entry.object_store_key,
            entry.payload,
        )
        formal._object_metadata_matches(
            _transport_call(
                closure,
                client,
                capability,
                "_read_object_properties",
                plan.organization_id,
                entry.object_store_key,
            ),
            entry,
        )
        initial_files_response = _transport_call(
            closure, client, capability, "_request_json", "files/read",
            {"projectId": project_id},
        )
        try:
            existing = formal._read_files(
                initial_files_response,
                expected_project_id=project_id,
            )
        except formal.FormalQcSubmissionError:
            _persist_files_read_schema_diagnostic(
                plan=plan,
                permit=permit,
                phase="initial_source_inventory",
                response=initial_files_response,
            )
            raise
        projected = {item.project_path: item for item in plan.source_files}
        unexpected = set(existing) - set(projected)
        if unexpected - {plan.qc_default_research_notebook_path}:
            raise FundamentalDiscoverySubmissionError(
                "new discovery project contains an unprojected source"
            )
        if plan.qc_default_research_notebook_path in unexpected:
            formal._success(
                _transport_call(
                    closure,
                    client,
                    capability,
                    "_request_json",
                    "files/delete",
                    {
                        "projectId": project_id,
                        "name": plan.qc_default_research_notebook_path,
                    },
                ),
                frozenset({"success", "errors", "messages"}),
                "files/delete",
            )
        for path, source in projected.items():
            endpoint = "files/update" if path in existing else "files/create"
            formal._success(
                _transport_call(
                    closure,
                    client,
                    capability,
                    "_request_json",
                    endpoint,
                    {
                        "projectId": project_id,
                        "name": path,
                        "content": source.content.decode("utf-8"),
                    },
                ),
                frozenset({"success", "errors", "messages"}),
                endpoint,
            )
        source_readback_response = _transport_call(
            closure, client, capability, "_request_json", "files/read",
            {"projectId": project_id},
        )
        try:
            observed = formal._read_files(
                source_readback_response,
                expected_project_id=project_id,
            )
        except formal.FormalQcSubmissionError:
            _persist_files_read_schema_diagnostic(
                plan=plan,
                permit=permit,
                phase="source_readback",
                response=source_readback_response,
            )
            raise
        if set(observed) != set(projected):
            raise FundamentalDiscoverySubmissionError(
                "discovery project source inventory changed"
            )
        for path, source in projected.items():
            payload = observed[path].encode("utf-8")
            if (
                len(payload) != source.byte_count
                or hashlib.sha256(payload).hexdigest() != source.content_sha256
            ):
                raise FundamentalDiscoverySubmissionError(
                    "discovery project source bytes changed"
                )
        compile_id = formal._compile_id(
            _transport_call(
                closure, client, capability, "_request_json", "compile/create",
                {"projectId": project_id},
            ),
            expected_project_id=project_id,
        )
        state = ""
        for index in range(plan.compile_poll_limit):
            state = formal._compile_state(
                _transport_call(
                    closure, client, capability, "_request_json", "compile/read",
                    {"projectId": project_id, "compileId": compile_id},
                ),
                compile_id,
            )
            if state in formal.COMPILE_TERMINAL_STATES:
                break
            if index + 1 == plan.compile_poll_limit:
                raise FundamentalDiscoverySubmissionError("compile polling exhausted")
            _wait(COMPILE_POLL_SECONDS)
        if state != "BuildSuccess":
            raise FundamentalDiscoverySubmissionError(
                "discovery project did not compile"
            )
        backtest_id, initial = formal._created_backtest(
            _transport_call(
                closure,
                client,
                capability,
                "_request_json",
                "backtests/create",
                {
                    "projectId": project_id,
                    "compileId": compile_id,
                    "backtestName": plan.backtest_name,
                },
            ),
            project_id=project_id,
            name=plan.backtest_name,
        )
        launch = _launch(
            plan, permit, project_id, compile_id, backtest_id, initial
        )
        _authority_register_launch(launch, plan=plan, permit=permit)
        return permit, _require_launch_receipt(launch, plan, permit)
    except Exception as exc:
        raise FundamentalDiscoverySubmissionLocked(
            "submission", permit.permit_id, type(exc).__name__
        ) from exc


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FundamentalDiscoveryTerminalStatusReceipt:
    receipt_id: str
    receipt_sha256: str
    permit_sha256: str
    launch_receipt_sha256: str
    plan_sha256: str
    project_id: int
    backtest_id: str
    terminal_status: str
    status_poll_count: int
    include_statistics: bool
    result_statistics_log_order_accessed: bool


def _terminal_record(
    value: FundamentalDiscoveryTerminalStatusReceipt,
) -> dict[str, object]:
    return {
        "permit_sha256": value.permit_sha256,
        "launch_receipt_sha256": value.launch_receipt_sha256,
        "plan_sha256": value.plan_sha256,
        "project_id": value.project_id,
        "backtest_id": value.backtest_id,
        "terminal_status": value.terminal_status,
        "status_poll_count": value.status_poll_count,
        "include_statistics": value.include_statistics,
        "result_statistics_log_order_accessed": (
            value.result_statistics_log_order_accessed
        ),
    }


def _terminal_receipt(plan, permit, launch, status, count):
    record = {
        "permit_sha256": permit.permit_sha256,
        "launch_receipt_sha256": launch.receipt_sha256,
        "plan_sha256": plan.plan_sha256,
        "project_id": launch.project_id,
        "backtest_id": launch.backtest_id,
        "terminal_status": status,
        "status_poll_count": count,
        "include_statistics": False,
        "result_statistics_log_order_accessed": False,
    }
    identity, digest = _identified(
        TERMINAL_STATUS_SCHEMA,
        "arv2-qc-fundamental-discovery-terminal-",
        record,
    )
    return FundamentalDiscoveryTerminalStatusReceipt(
        receipt_id=identity, receipt_sha256=digest, **record
    )


def _require_terminal_impl(
    value, plan, permit, launch, *, _authority_current,
    _require_launch_receipt,
):
    _require_launch_receipt(launch, plan, permit)
    if type(value) is not FundamentalDiscoveryTerminalStatusReceipt:
        raise FundamentalDiscoverySubmissionError(
            "terminal status receipt changed type"
        )
    registered = _authority_current(value)
    if (
        registered is None
        or registered[0]() is not value
        or registered[1] is not plan
        or registered[2] is not permit
        or registered[3] is not launch
        or registered[5] != os.getpid()
        or type(value.status_poll_count) is not int
        or not 1 <= value.status_poll_count <= plan.status_poll_limit
        or value
        != _terminal_receipt(
            plan, permit, launch, value.terminal_status, value.status_poll_count
        )
        or registered[4]
        != _canonical({"schema": TERMINAL_STATUS_SCHEMA, **_terminal_record(value)})
    ):
        raise FundamentalDiscoverySubmissionError(
            "terminal status receipt lacks process-return authority"
        )
    return value


def _inspect_fundamental_discovery_terminal_status_impl(
    *, plan, review_claim, owner_signature, permit, launch, client,
    _transport_capability_minter,
    _authority_register_terminal,
    _require_launch_receipt,
    _require_terminal_receipt,
):
    closure = _execution_preflight(plan, review_claim, owner_signature)
    require_fundamental_discovery_submission_permit(permit, plan, review_claim)
    _require_launch_receipt(launch, plan, permit)
    capability = _transport_capability_minter(
        transport=client,
        scope="status",
        binding_record={
            "schema": "arv2-qc-fundamental-discovery-status-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "launch_receipt_sha256": launch.receipt_sha256,
        },
        call_budget={"backtests/list": plan.status_poll_limit},
    )
    for index in range(plan.status_poll_limit):
        try:
            response = _transport_call(
                closure,
                client,
                capability,
                "_request_json",
                "backtests/list",
                {"projectId": launch.project_id, "includeStatistics": False},
            )
            try:
                status = formal.parse_statistics_free_backtest_list(
                    response,
                    expected_project_id=launch.project_id,
                    expected_backtest_id=launch.backtest_id,
                    expected_backtest_name=launch.backtest_name,
                )
            except formal.FormalQcSubmissionError:
                _persist_backtests_list_schema_diagnostic(
                    plan=plan,
                    permit=permit,
                    launch=launch,
                    response=response,
                    _require_launch_receipt=_require_launch_receipt,
                )
                raise
        except Exception as exc:
            raise FundamentalDiscoverySubmissionLocked(
                "terminal_status", permit.permit_id, type(exc).__name__
            ) from exc
        if status.status in formal.BACKTEST_TERMINAL_STATUSES:
            terminal = _terminal_receipt(
                plan, permit, launch, status.status, index + 1
            )
            _authority_register_terminal(
                terminal,
                plan=plan,
                permit=permit,
                launch=launch,
            )
            return _require_terminal_receipt(
                terminal, plan, permit, launch
            )
        if index + 1 == plan.status_poll_limit:
            raise FundamentalDiscoverySubmissionLocked(
                "terminal_status", permit.permit_id, "poll limit exhausted"
            )
        _wait(STATUS_POLL_SECONDS)
    raise AssertionError("unreachable discovery status loop")


def _object_payload(response, *, key: str, maximum: int, name: str) -> bytes:
    if type(response) is not dict or not set(response).issubset(
        {"success", "errors", "messages", "object"}
    ):
        raise FundamentalDiscoverySubmissionError(f"{name} response envelope changed")
    item = response.get("object")
    if (
        response.get("success") is not True
        or type(item) is not dict
        or set(item) != {"key", "objectData"}
        or item.get("key") != key
        or type(item.get("objectData")) is not str
    ):
        raise FundamentalDiscoverySubmissionError(f"{name} object envelope changed")
    try:
        payload = base64.b64decode(item["objectData"], validate=True)
    except (ValueError, TypeError) as exc:
        raise FundamentalDiscoverySubmissionError(
            f"{name} is not canonical base64"
        ) from exc
    if (
        not 0 < len(payload) <= maximum
        or base64.b64encode(payload).decode("ascii") != item["objectData"]
    ):
        raise FundamentalDiscoverySubmissionError(f"{name} exceeds its byte bound")
    return payload


def _parse_canonical(payload: bytes, name: str):
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise FundamentalDiscoverySubmissionError(f"{name} is not JSON") from exc
    if type(value) is not dict or _canonical(value) != payload:
        raise FundamentalDiscoverySubmissionError(f"{name} is not canonical JSON")
    return value


def _prepare_archive_root(plan):
    parent = _private_directory(plan.review_directory, "discovery review directory")
    if plan.archive_root.parent.resolve(strict=True) != parent:
        raise FundamentalDiscoverySubmissionError("archive parent changed")
    try:
        descriptor = os.open(
            parent,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise FundamentalDiscoverySubmissionError(
            "archive parent could not be authenticated"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        observed = parent.lstat()
        if (
            opened.st_dev != observed.st_dev
            or opened.st_ino != observed.st_ino
            or not stat.S_ISDIR(opened.st_mode)
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) != 0o700
        ):
            raise FundamentalDiscoverySubmissionError(
                "archive parent identity changed"
            )
    except (OSError, FundamentalDiscoverySubmissionError):
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    try:
        os.mkdir(plan.archive_root.name, 0o700, dir_fd=descriptor)
    except OSError as exc:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise FundamentalDiscoverySubmissionError(
            "archive already exists or could not be created; retry is forbidden"
        ) from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise FundamentalDiscoveryArchiveRootPublicationAmbiguous(
            "archive root was created but publication durability is ambiguous"
        ) from exc
    try:
        os.close(descriptor)
    except OSError as exc:
        raise FundamentalDiscoveryArchiveRootPublicationAmbiguous(
            "archive root was created but publication durability is ambiguous"
        ) from exc
    try:
        after = parent.lstat()
        if after.st_dev != opened.st_dev or after.st_ino != opened.st_ino:
            raise FundamentalDiscoverySubmissionError(
                "archive parent identity changed"
            )
        _private_directory(plan.archive_root, "discovery archive root")
    except (OSError, FundamentalDiscoverySubmissionError) as exc:
        raise FundamentalDiscoveryArchiveRootPublicationAmbiguous(
            "archive root was created but publication durability is ambiguous"
        ) from exc
    return plan.archive_root


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FundamentalDiscoveryNamedRefusalReceipt:
    receipt_id: str
    receipt_sha256: str
    permit_sha256: str
    terminal_receipt_sha256: str
    package_sha256: str
    failure_sha256: str
    safe_reason: str
    archive_root: Path
    object_read_count: int
    outcome_result_statistics_log_order_accessed: bool


def _named_refusal_record(
    value: FundamentalDiscoveryNamedRefusalReceipt,
) -> dict[str, object]:
    return {
        "permit_sha256": value.permit_sha256,
        "terminal_receipt_sha256": value.terminal_receipt_sha256,
        "package_sha256": value.package_sha256,
        "failure_sha256": value.failure_sha256,
        "safe_reason": value.safe_reason,
        "archive_root": str(value.archive_root),
        "object_read_count": value.object_read_count,
        "outcome_result_statistics_log_order_accessed": (
            value.outcome_result_statistics_log_order_accessed
        ),
    }


def _output_record(
    value: (
        ReviewedFundamentalUniverseDiscoveryReceipt
        | FundamentalDiscoveryNamedRefusalReceipt
    ),
) -> dict[str, object]:
    if type(value) is ReviewedFundamentalUniverseDiscoveryReceipt:
        return {
            "kind": "reviewed_discovery",
            "artifact": fundamental_discovery_artifact_binding_record(value),
        }
    if type(value) is FundamentalDiscoveryNamedRefusalReceipt:
        return {
            "kind": "named_refusal",
            "receipt": _named_refusal_record(value),
        }
    raise FundamentalDiscoverySubmissionError(
        "discovery output receipt changed type"
    )


def _require_output_impl(
    value, plan, permit, launch, terminal, *, _authority_current,
    _require_terminal_receipt,
):
    _require_terminal_receipt(terminal, plan, permit, launch)
    if type(value) not in {
        ReviewedFundamentalUniverseDiscoveryReceipt,
        FundamentalDiscoveryNamedRefusalReceipt,
    }:
        raise FundamentalDiscoverySubmissionError(
            "discovery output receipt changed type"
        )
    registered = _authority_current(value)
    if (
        registered is None
        or registered[0]() is not value
        or registered[1] is not plan
        or registered[2] is not permit
        or registered[3] is not launch
        or registered[4] is not terminal
        or registered[6] != os.getpid()
    ):
        raise FundamentalDiscoverySubmissionError(
            "discovery output receipt lacks process-return authority"
        )
    if type(value) is ReviewedFundamentalUniverseDiscoveryReceipt:
        require_reviewed_fundamental_universe_discovery_receipt(value)
    else:
        record = _named_refusal_record(value)
        identity, digest = _identified(
            REFUSAL_RECEIPT_SCHEMA,
            "arv2-qc-fundamental-discovery-refusal-",
            record,
        )
        package_payload, _package_identity = _read_private_file(
            value.archive_root / ARCHIVE_PACKAGE_NAME,
            "archived refusal package",
            MAX_TERMINAL_PACKAGE_BYTES,
        )
        failure_payload, _failure_identity = _read_private_file(
            value.archive_root / REFUSAL_FILENAME,
            "archived named refusal",
            MAX_TERMINAL_PACKAGE_BYTES,
        )
        failure = _parse_canonical(failure_payload, "archived named refusal")
        if (
            value.receipt_id != identity
            or value.receipt_sha256 != digest
            or value.object_read_count != 2
            or value.outcome_result_statistics_log_order_accessed is not False
            or value.permit_sha256 != permit.permit_sha256
            or value.terminal_receipt_sha256 != terminal.receipt_sha256
            or value.archive_root != plan.archive_root
            or hashlib.sha256(package_payload).hexdigest()
            != value.package_sha256
            or hashlib.sha256(failure_payload).hexdigest()
            != value.failure_sha256
            or failure.get("safe_reason") != value.safe_reason
        ):
            raise FundamentalDiscoverySubmissionError(
                "named refusal receipt changed"
            )
    if registered[5] != _canonical(_output_record(value)):
        raise FundamentalDiscoverySubmissionError(
            "discovery output receipt content changed"
        )
    return value


def _validate_success_package(payload, plan):
    package = _parse_canonical(payload, "discovery terminal package")
    expected = {
        "schema", "contract_sha256", "status", "output_manifest_key",
        "output_manifest_sha256", "output_manifest_byte_count",
        "decision_session_count", "source_member_count", "terminal_count",
        "accepted_count", "out_of_scope_count", "named_refusal_count",
        "outcome_access_performed", "price_or_return_access_performed",
        "orders_or_portfolio_actions_performed",
    }
    if (
        set(package) != expected
        or package.get("schema") != TERMINAL_PACKAGE_SCHEMA
        or package.get("contract_sha256") != CONTRACT_SHA256
        or package.get("status") != "completed"
        or package.get("outcome_access_performed") is not False
        or package.get("price_or_return_access_performed") is not False
        or package.get("orders_or_portfolio_actions_performed") is not False
        or type(package.get("output_manifest_byte_count")) is not int
        or not 0 < package["output_manifest_byte_count"] <= MAX_OUTPUT_MANIFEST_BYTES
    ):
        raise FundamentalDiscoverySubmissionError("completed terminal package changed")
    _safe_key(package["output_manifest_key"], "output manifest key")
    _sha(package["output_manifest_sha256"], "output manifest hash")
    if package["output_manifest_key"] != (
        OUTPUT_PREFIX + "manifests/" + package["output_manifest_sha256"] + ".json"
    ):
        raise FundamentalDiscoverySubmissionError("output manifest identity changed")
    for name in (
        "decision_session_count", "source_member_count", "terminal_count",
        "accepted_count", "out_of_scope_count", "named_refusal_count",
    ):
        if type(package.get(name)) is not int or package[name] < 0:
            raise FundamentalDiscoverySubmissionError("terminal package census changed")
    return package


def _validate_manifest_envelope(payload, package, plan):
    if (
        len(payload) != package["output_manifest_byte_count"]
        or hashlib.sha256(payload).hexdigest() != package["output_manifest_sha256"]
    ):
        raise FundamentalDiscoverySubmissionError("output manifest bytes changed")
    manifest = _parse_canonical(payload, "discovery output manifest")
    descriptors = manifest.get("terminal_shards")
    if (
        manifest.get("contract_sha256") != CONTRACT_SHA256
        or manifest.get("status") != "completed"
        or manifest.get("plan_id") != plan.discovery_plan_id
        or manifest.get("plan_sha256") != plan.discovery_plan_artifact_sha256
        or manifest.get("project_source_set_sha256")
        != plan.project_source_set_sha256
        or type(descriptors) is not list
        or not 1 <= len(descriptors) <= MAX_TERMINAL_SHARDS
    ):
        raise FundamentalDiscoverySubmissionError("output manifest lineage changed")
    for ordinal, descriptor in enumerate(descriptors):
        if (
            type(descriptor) is not dict
            or descriptor.get("schema") != OUTPUT_SHARD_SCHEMA
            or descriptor.get("ordinal") != ordinal
            or type(descriptor.get("compressed_byte_count")) is not int
            or not 0 < descriptor["compressed_byte_count"] <= MAX_COMPRESSED_SHARD_BYTES
        ):
            raise FundamentalDiscoverySubmissionError("terminal shard descriptor changed")
        _safe_key(descriptor.get("object_store_key"), "terminal shard key")
        _sha(descriptor.get("compressed_sha256"), "terminal shard hash")
    return manifest


def _download_and_review_fundamental_discovery_archive_impl(
    *, plan, review_claim, owner_signature, permit, launch, terminal, client,
    _transport_capability_minter,
    _authority_register_output,
    _require_terminal_receipt,
    _require_output_receipt,
) -> ReviewedFundamentalUniverseDiscoveryReceipt | FundamentalDiscoveryNamedRefusalReceipt:
    closure = _execution_preflight(plan, review_claim, owner_signature)
    require_fundamental_discovery_submission_permit(permit, plan, review_claim)
    _require_terminal_receipt(terminal, plan, permit, launch)
    archive_root = _prepare_archive_root(plan)
    capability = _transport_capability_minter(
        transport=client,
        scope="preopen_output_read",
        binding_record={
            "schema": "arv2-qc-fundamental-discovery-output-capability-v1",
            "plan_sha256": plan.plan_sha256,
            "permit_sha256": permit.permit_sha256,
            "terminal_receipt_sha256": terminal.receipt_sha256,
            "terminal_package_key": plan.terminal_package_key,
            "archive_root": str(archive_root),
        },
        call_budget={"object/read": plan.maximum_output_object_reads},
    )
    try:
        package_payload = _object_payload(
            _transport_call(
                closure, client, capability, "_read_object_bounded",
                plan.organization_id, plan.terminal_package_key,
            ),
            key=plan.terminal_package_key,
            maximum=MAX_TERMINAL_PACKAGE_BYTES,
            name="terminal package",
        )
        package = _parse_canonical(package_payload, "terminal package")
        if package.get("status") == "named_refusal":
            expected = {
                "schema", "contract_sha256", "status", "failure_key",
                "failure_sha256", "failure_byte_count",
                "outcome_access_performed", "price_or_return_access_performed",
                "orders_or_portfolio_actions_performed",
            }
            if (
                terminal.terminal_status != "Runtime Error"
                or set(package) != expected
                or package.get("schema") != TERMINAL_PACKAGE_SCHEMA
                or package.get("contract_sha256") != CONTRACT_SHA256
                or any(
                    package.get(name) is not False
                    for name in (
                        "outcome_access_performed",
                        "price_or_return_access_performed",
                        "orders_or_portfolio_actions_performed",
                    )
                )
                or type(package.get("failure_byte_count")) is not int
                or not 0 < package["failure_byte_count"] <= MAX_TERMINAL_PACKAGE_BYTES
            ):
                raise FundamentalDiscoverySubmissionError("named refusal package changed")
            _safe_key(package.get("failure_key"), "failure key")
            _sha(package.get("failure_sha256"), "failure hash")
            failure_payload = _object_payload(
                _transport_call(
                    closure, client, capability, "_read_object_bounded",
                    plan.organization_id, package["failure_key"],
                ),
                key=package["failure_key"],
                maximum=MAX_TERMINAL_PACKAGE_BYTES,
                name="named refusal",
            )
            if (
                len(failure_payload) != package["failure_byte_count"]
                or hashlib.sha256(failure_payload).hexdigest()
                != package["failure_sha256"]
            ):
                raise FundamentalDiscoverySubmissionError("named refusal bytes changed")
            failure = _parse_canonical(failure_payload, "named refusal")
            if (
                failure.get("contract_sha256") != CONTRACT_SHA256
                or failure.get("status") != "named_refusal"
                or failure.get("plan_id") != plan.discovery_plan_id
                or failure.get("plan_sha256") != plan.discovery_plan_artifact_sha256
                or type(failure.get("safe_reason")) is not str
                or _SAFE_ID.fullmatch(failure["safe_reason"]) is None
                or any(
                    failure.get(name) is not False
                    for name in (
                        "outcome_access_performed",
                        "price_or_return_access_performed",
                        "orders_or_portfolio_actions_performed",
                    )
                )
            ):
                raise FundamentalDiscoverySubmissionError("named refusal changed")
            _write_private_file(
                archive_root / ARCHIVE_PACKAGE_NAME,
                package_payload,
                "archived refusal package",
            )
            _write_private_file(
                archive_root / REFUSAL_FILENAME,
                failure_payload,
                "archived named refusal",
            )
            record = {
                "permit_sha256": permit.permit_sha256,
                "terminal_receipt_sha256": terminal.receipt_sha256,
                "package_sha256": hashlib.sha256(package_payload).hexdigest(),
                "failure_sha256": package["failure_sha256"],
                "safe_reason": failure["safe_reason"],
                "archive_root": str(archive_root),
                "object_read_count": 2,
                "outcome_result_statistics_log_order_accessed": False,
            }
            identity, digest = _identified(
                REFUSAL_RECEIPT_SCHEMA,
                "arv2-qc-fundamental-discovery-refusal-",
                record,
            )
            refusal = FundamentalDiscoveryNamedRefusalReceipt(
                receipt_id=identity,
                receipt_sha256=digest,
                permit_sha256=record["permit_sha256"],
                terminal_receipt_sha256=record["terminal_receipt_sha256"],
                package_sha256=record["package_sha256"],
                failure_sha256=record["failure_sha256"],
                safe_reason=record["safe_reason"],
                archive_root=archive_root,
                object_read_count=2,
                outcome_result_statistics_log_order_accessed=False,
            )
            _authority_register_output(
                refusal,
                plan=plan,
                permit=permit,
                launch=launch,
                terminal=terminal,
            )
            return _require_output_receipt(
                refusal, plan, permit, launch, terminal
            )

        if terminal.terminal_status != "Completed.":
            raise FundamentalDiscoverySubmissionError(
                "completed status and package are required for an archive"
            )
        package = _validate_success_package(package_payload, plan)
        manifest_payload = _object_payload(
            _transport_call(
                closure, client, capability, "_read_object_bounded",
                plan.organization_id, package["output_manifest_key"],
            ),
            key=package["output_manifest_key"],
            maximum=MAX_OUTPUT_MANIFEST_BYTES,
            name="output manifest",
        )
        manifest = _validate_manifest_envelope(manifest_payload, package, plan)
        _write_private_file(
            archive_root / ARCHIVE_PACKAGE_NAME,
            package_payload,
            "archived terminal package",
        )
        _write_private_file(
            archive_root / ARCHIVE_MANIFEST_NAME,
            manifest_payload,
            "archived output manifest",
        )
        os.mkdir(archive_root / ARCHIVE_SHARD_DIRECTORY, 0o700)
        for descriptor in manifest["terminal_shards"]:
            shard = _object_payload(
                _transport_call(
                    closure, client, capability, "_read_object_bounded",
                    plan.organization_id, descriptor["object_store_key"],
                ),
                key=descriptor["object_store_key"],
                maximum=MAX_COMPRESSED_SHARD_BYTES,
                name="terminal shard",
            )
            if (
                len(shard) != descriptor["compressed_byte_count"]
                or hashlib.sha256(shard).hexdigest()
                != descriptor["compressed_sha256"]
            ):
                raise FundamentalDiscoverySubmissionError("terminal shard bytes changed")
            path = archive_root / ARCHIVE_SHARD_DIRECTORY / (
                f'{descriptor["ordinal"]:04d}-'
                f'{descriptor["compressed_sha256"]}-jsonl.gz'
            )
            _write_private_file(path, shard, "archived terminal shard")
            del shard
        receipt = load_reviewed_fundamental_universe_discovery_receipt(
            plan_bytes=plan.projection.plan_bytes,
            projection=plan.projection,
            archive_root=archive_root,
        )
        _authority_register_output(
            receipt,
            plan=plan,
            permit=permit,
            launch=launch,
            terminal=terminal,
        )
        return _require_output_receipt(
            receipt, plan, permit, launch, terminal
        )
    except FundamentalDiscoverySubmissionLocked:
        raise
    except Exception as exc:
        raise FundamentalDiscoverySubmissionLocked(
            "output_archive", permit.permit_id, type(exc).__name__
        ) from exc


def _make_discovery_action_global_binding_guard():
    """Pin every in-process dependency used by the three QC actions."""

    expected_names: tuple[str, ...] = ()
    expected_globals: tuple[tuple[str, object, object], ...] = ()
    expected_external: tuple[tuple[object, str, object], ...] = ()
    expected_json_classes: tuple[object, ...] = ()
    expected_dependency_functions: tuple[object, ...] = ()
    expected_dependency_classes: tuple[object, ...] = ()
    expected_dependency_module_attributes: tuple[object, ...] = ()
    getpid = os.getpid
    error_type = FundamentalDiscoverySubmissionError
    authority_pid = getpid()
    module_globals = globals()
    exact_type = type
    exact_tuple = tuple
    any_true = any
    read_attribute = getattr
    read_vars = vars
    mapping_get = dict.get
    dict_type = dict
    list_type = list
    function_type = exact_type(lambda: None)
    code_type = exact_type((lambda: None).__code__)
    module_type = exact_type(sys)
    class_type = type
    static_method_type = staticmethod
    class_method_type = classmethod
    property_type = property
    length = len
    zip_strict = zip
    string_type = str
    missing = object()
    path_type = exact_type(Path())
    guarded_json_classes = (json.JSONDecoder, json.JSONEncoder)
    dependency_global_namespaces = (
        load_reviewed_fundamental_universe_discovery_receipt.__globals__,
    )
    excluded = (
        "_make_discovery_action_global_binding_guard",
        "_seal_discovery_action_global_bindings",
        "_require_discovery_action_global_bindings",
        "_make_discovery_return_authority",
        "_seal_discovery_return_producers",
        "_discovery_return_register_launch",
        "_discovery_return_current_launch",
        "_discovery_return_register_terminal",
        "_discovery_return_current_terminal",
        "_discovery_return_register_output",
        "_discovery_return_current_output",
        "_transport_capability_minter",
        "_execute_fundamental_discovery_submission_once_impl",
        "_inspect_fundamental_discovery_terminal_status_impl",
        "_download_and_review_fundamental_discovery_archive_impl",
        "_require_launch_impl",
        "_require_terminal_impl",
        "_require_output_impl",
        "_bind_transport_capability_consumers",
    )
    external_specs = (
        (
            formal,
            (
                "_require_concrete_transport",
                "_transport_call",
                "_read_project_inventory",
                "_created_project",
                "_project_record",
                "_PROJECT_RECORD_KEYS",
                "_object_metadata_matches",
                "_read_files",
                "_compile_id",
                "_compile_state",
                "COMPILE_TERMINAL_STATES",
                "_created_backtest",
                "parse_statistics_free_backtest_list",
                "BACKTEST_TERMINAL_STATUSES",
            ),
        ),
        (hashlib, ("md5", "sha256")),
        (base64, ("b64decode", "b64encode")),
        (json, ("loads",)),
        (
            os,
            (
                "O_CLOEXEC",
                "O_CREAT",
                "O_EXCL",
                "O_NOFOLLOW",
                "O_RDONLY",
                "O_WRONLY",
                "close",
                "fstat",
                "fsync",
                "getpid",
                "getuid",
                "link",
                "mkdir",
                "open",
                "unlink",
                "write",
            ),
        ),
        (stat, ("S_IMODE", "S_ISDIR", "S_ISLNK", "S_ISREG")),
        (time, ("sleep",)),
        (
            Path,
            (
                "absolute",
                "is_absolute",
                "lstat",
                "open",
                "read_bytes",
                "relative_to",
                "resolve",
            ),
        ),
        (
            path_type,
            (
                "absolute",
                "is_absolute",
                "lstat",
                "open",
                "read_bytes",
                "relative_to",
                "resolve",
            ),
        ),
    )

    def non_dunder_names() -> tuple[str, ...]:
        keys = exact_tuple(module_globals)
        if any_true(exact_type(name) is not string_type for name in keys):
            raise error_type("discovery action global census changed")
        return exact_tuple(
            name
            for name in keys
            if not name.startswith("__") and name not in excluded
        )

    def is_dependency_namespace(namespace) -> bool:
        return any_true(
            namespace is expected
            for expected in dependency_global_namespaces
        )

    def transitive_code_names(root_code) -> tuple[str, ...]:
        pending = list_type((root_code,))
        seen_codes: tuple[object, ...] = ()
        names = list_type()
        while pending:
            code = pending.pop()
            if any_true(code is item for item in seen_codes):
                continue
            seen_codes = (*seen_codes, code)
            for name in code.co_names:
                if name not in names:
                    names.append(name)
            pending.extend(
                value
                for value in code.co_consts
                if exact_type(value) is code_type
            )
        return exact_tuple(names)

    def dependency_snapshot(roots):
        """Capture the bounded reviewed-discovery loader call graph."""

        pending = list_type(roots)
        pending_classes = list_type()
        seen: tuple[object, ...] = ()
        seen_classes: tuple[object, ...] = ()
        functions = list_type()
        classes = list_type()
        module_attributes = list_type()
        while pending or pending_classes:
            if not pending:
                value_class = pending_classes.pop()
                if any_true(value_class is item for item in seen_classes):
                    continue
                seen_classes = (*seen_classes, value_class)
                namespace = read_vars(value_class)
                names = exact_tuple(namespace)
                bindings = exact_tuple(
                    (name, namespace[name]) for name in names
                )
                classes.append((value_class, names, bindings))
                for _name, attribute in bindings:
                    candidate = (
                        attribute
                        if exact_type(attribute) is function_type
                        else attribute.__func__
                        if exact_type(attribute)
                        in (static_method_type, class_method_type)
                        else None
                    )
                    if (
                        exact_type(candidate) is function_type
                        and is_dependency_namespace(candidate.__globals__)
                    ):
                        pending.append(candidate)
                    if exact_type(attribute) is property_type:
                        for candidate in (
                            attribute.fget,
                            attribute.fset,
                            attribute.fdel,
                        ):
                            if (
                                exact_type(candidate) is function_type
                                and is_dependency_namespace(
                                    candidate.__globals__
                                )
                            ):
                                pending.append(candidate)
                continue
            function = pending.pop()
            if (
                exact_type(function) is not function_type
                or not is_dependency_namespace(function.__globals__)
                or any_true(function is item for item in seen)
            ):
                continue
            seen = (*seen, function)
            code = function.__code__
            namespace = function.__globals__
            names = transitive_code_names(code)
            closure = function.__closure__ or ()
            closure_values = exact_tuple(
                cell.cell_contents for cell in closure
            )
            builtin_namespace = function.__builtins__
            builtin_mapping = (
                builtin_namespace
                if exact_type(builtin_namespace) is dict_type
                else read_vars(builtin_namespace)
            )
            global_bindings = exact_tuple(
                (name, mapping_get(namespace, name, missing))
                for name in names
            )
            builtin_bindings = exact_tuple(
                (name, mapping_get(builtin_mapping, name, missing))
                for name, value in global_bindings
                if value is missing
            )
            functions.append((
                function,
                code,
                namespace,
                names,
                exact_tuple(code.co_freevars),
                closure_values,
                builtin_namespace,
                builtin_mapping,
                global_bindings,
                builtin_bindings,
            ))
            for _name, value in global_bindings:
                if (
                    exact_type(value) is function_type
                    and is_dependency_namespace(value.__globals__)
                ):
                    pending.append(value)
                elif exact_type(value) is class_type:
                    pending_classes.append(value)
                elif exact_type(value) is module_type:
                    module_namespace = read_vars(value)
                    for name in names:
                        if name not in module_namespace:
                            continue
                        attribute = module_namespace[name]
                        module_attributes.append((
                            value,
                            module_namespace,
                            name,
                            attribute,
                        ))
                        if exact_type(attribute) is class_type:
                            pending_classes.append(attribute)
                        elif (
                            exact_type(attribute) is function_type
                            and is_dependency_namespace(
                                attribute.__globals__
                            )
                        ):
                            pending.append(attribute)
            for value in closure_values:
                if (
                    exact_type(value) is function_type
                    and is_dependency_namespace(value.__globals__)
                ):
                    pending.append(value)
                elif exact_type(value) is class_type:
                    pending_classes.append(value)
        return (
            exact_tuple(functions),
            exact_tuple(classes),
            exact_tuple(module_attributes),
        )

    def dependencies_are_current() -> bool:
        for (
            function,
            code,
            namespace,
            names,
            freevars,
            closure_values,
            builtin_namespace,
            builtin_mapping,
            global_bindings,
            builtin_bindings,
        ) in expected_dependency_functions:
            closure = function.__closure__ or ()
            current_closure_values = exact_tuple(
                cell.cell_contents for cell in closure
            )
            if (
                function.__code__ is not code
                or function.__globals__ is not namespace
                or transitive_code_names(function.__code__) != names
                or exact_tuple(function.__code__.co_freevars) != freevars
                or length(current_closure_values) != length(closure_values)
                or any_true(
                    current is not expected
                    for current, expected in zip_strict(
                        current_closure_values,
                        closure_values,
                        strict=True,
                    )
                )
                or function.__builtins__ is not builtin_namespace
                or (
                    builtin_namespace
                    if exact_type(builtin_namespace) is dict_type
                    else read_vars(builtin_namespace)
                )
                is not builtin_mapping
                or any_true(
                    mapping_get(namespace, name, missing) is not expected
                    for name, expected in global_bindings
                )
                or any_true(
                    mapping_get(builtin_mapping, name, missing) is not expected
                    for name, expected in builtin_bindings
                )
            ):
                return False
        for value_class, names, bindings in expected_dependency_classes:
            namespace = read_vars(value_class)
            if exact_tuple(namespace) != names or any_true(
                namespace[name] is not expected
                for name, expected in bindings
            ):
                return False
        return not any_true(
            read_vars(namespace) is not namespace_vars
            or mapping_get(namespace_vars, name, missing) is not expected
            for namespace, namespace_vars, name, expected
            in expected_dependency_module_attributes
        )

    def seal() -> None:
        nonlocal expected_names, expected_globals, expected_external
        nonlocal expected_json_classes
        nonlocal expected_dependency_functions, expected_dependency_classes
        nonlocal expected_dependency_module_attributes
        if expected_globals or expected_external:
            raise error_type("discovery action globals were already sealed")
        expected_names = non_dunder_names()
        expected_globals = exact_tuple(
            (
                name,
                exact_type(module_globals[name]),
                module_globals[name],
            )
            for name in expected_names
        )
        expected_external = exact_tuple(
            (namespace, name, read_attribute(namespace, name, missing))
            for namespace, names in external_specs
            for name in names
        )
        expected_json_classes = exact_tuple(
            (
                value_class,
                exact_tuple(read_vars(value_class)),
                exact_tuple(
                    (name, read_vars(value_class)[name])
                    for name in read_vars(value_class)
                ),
            )
            for value_class in guarded_json_classes
        )
        (
            expected_dependency_functions,
            expected_dependency_classes,
            expected_dependency_module_attributes,
        ) = dependency_snapshot((
            load_reviewed_fundamental_universe_discovery_receipt,
            require_reviewed_fundamental_universe_discovery_receipt,
        ))

    def require(kind: str) -> None:
        if getpid() != authority_pid or not expected_globals:
            raise error_type(
                f"discovery {kind} action global authority changed"
            )
        if non_dunder_names() != expected_names or any_true(
            exact_type(module_globals.get(name, missing)) is not expected_type
            or module_globals.get(name, missing) is not expected
            for name, expected_type, expected in expected_globals
        ):
            raise error_type(
                f"discovery {kind} action global authority changed"
            )
        if not dependencies_are_current() or any_true(
            exact_tuple(read_vars(value_class)) != names
            or any_true(
                read_vars(value_class)[name] is not expected
                for name, expected in bindings
            )
            for value_class, names, bindings in expected_json_classes
        ) or any_true(
            read_attribute(namespace, name, missing) is not value
            for namespace, name, value in expected_external
        ):
            raise error_type(
                f"discovery {kind} action dependency authority changed"
            )

    return seal, require


(
    _seal_discovery_action_global_bindings,
    _require_discovery_action_global_bindings,
) = _make_discovery_action_global_binding_guard()


def _make_discovery_return_authority(binding_guard):
    """Create immutable, producer-bound authority for all QC action returns."""

    records: tuple[tuple[str, int, tuple[object, ...]], ...] = ()
    producer_callers: tuple[
        tuple[
            str,
            tuple[
                tuple[object, int, str, tuple[tuple[str, object], ...]], ...
            ],
        ],
        ...,
    ] = ()
    rlock_factory = threading.RLock
    lock = rlock_factory()
    getpid = os.getpid
    getframe = sys._getframe
    realpath = os.path.realpath
    authority_pid = getpid()
    module_name = __name__
    module_path = realpath(__file__)
    function_type = type(lambda: None)

    def public_registry(kind: str) -> dict[int, tuple[object, ...]]:
        registry = (
            _LAUNCH_AUTHORITIES if kind == "launch"
            else _TERMINAL_AUTHORITIES if kind == "terminal"
            else _OUTPUT_AUTHORITIES if kind == "output"
            else None
        )
        if type(registry) is not dict:
            raise FundamentalDiscoverySubmissionError(
                "discovery return-authority mirror changed"
            )
        return registry

    def expected_producer(kind: str, frame: object) -> None:
        expected = next(
            (item for item in producer_callers if item[0] == kind),
            None,
        )
        chain = () if expected is None else expected[1]
        valid = bool(chain) and getpid() == authority_pid
        current_frame = frame
        for code, globals_id, path, bindings in chain:
            if (
                not valid
                or current_frame is None
                or current_frame.f_code is not code
                or id(current_frame.f_globals) != globals_id
                or realpath(current_frame.f_code.co_filename) != path
                or tuple(current_frame.f_code.co_freevars)
                != tuple(name for name, _value in bindings)
                or any(
                    current_frame.f_locals.get(name) is not value
                    for name, value in bindings
                )
            ):
                valid = False
                break
            current_frame = current_frame.f_back
        if not valid:
            raise FundamentalDiscoverySubmissionError(
                "discovery return registration producer changed"
            )

    def forget(kind: str, identity: int, reference: object) -> None:
        nonlocal records
        with lock:
            matching = next(
                (
                    item for item in records
                    if item[0] == kind and item[1] == identity
                ),
                None,
            )
            if matching is not None and matching[2][0] is reference:
                records = tuple(item for item in records if item is not matching)
                public = public_registry(kind)
                if public.get(identity) is matching[2]:
                    public.pop(identity, None)

    def register(
        kind: str,
        caller_frame: object,
        value: object,
        *lineage: object,
    ) -> None:
        nonlocal records
        expected_producer(kind, caller_frame)
        identity = id(value)
        reference = weakref.ref(
            value,
            lambda ref, category=kind, key=identity: forget(category, key, ref),
        )
        entry = (reference, *lineage, getpid())
        with lock:
            public = public_registry(kind)
            if (
                any(item[0] == kind and item[1] == identity for item in records)
                or identity in public
            ):
                raise FundamentalDiscoverySubmissionError(
                    "discovery return identity was reused"
                )
            records = (*records, (kind, identity, entry))
            public[identity] = entry

    def current(kind: str, value: object) -> tuple[object, ...] | None:
        nonlocal records
        identity = id(value)
        with lock:
            matching = next(
                (
                    item for item in records
                    if item[0] == kind and item[1] == identity
                ),
                None,
            )
            private = None if matching is None else matching[2]
            public_records = public_registry(kind)
            public = public_records.get(identity)
            if (
                private is None
                or public is not private
                or private[0]() is not value
                or private[-1] != getpid()
            ):
                if matching is not None:
                    records = tuple(item for item in records if item is not matching)
                public_records.pop(identity, None)
                return None
            return private

    def seal_producers(
        *, execute_impl: object, inspect_impl: object, download_impl: object,
        execute_public: object, inspect_public: object, download_public: object,
    ) -> None:
        nonlocal producer_callers
        specifications = (
            (
                "launch",
                (
                    (execute_impl, "_execute_fundamental_discovery_submission_once_impl"),
                    (execute_public, "execute_fundamental_discovery_submission_once"),
                ),
            ),
            (
                "terminal",
                (
                    (inspect_impl, "_inspect_fundamental_discovery_terminal_status_impl"),
                    (inspect_public, "inspect_fundamental_discovery_terminal_status"),
                ),
            ),
            (
                "output",
                (
                    (download_impl, "_download_and_review_fundamental_discovery_archive_impl"),
                    (download_public, "download_and_review_fundamental_discovery_archive"),
                ),
            ),
        )
        if producer_callers:
            raise FundamentalDiscoverySubmissionError(
                "discovery return producers were already sealed"
            )
        sealed = ()
        for kind, functions in specifications:
            chain = ()
            for function, expected_name in functions:
                if (
                    type(function) is not function_type
                    or function.__module__ != module_name
                    or function.__globals__ is not globals()
                    or function.__code__.co_name != expected_name
                    or realpath(function.__code__.co_filename) != module_path
                ):
                    raise FundamentalDiscoverySubmissionError(
                        "discovery return producer provenance changed"
                    )
                closure = function.__closure__ or ()
                if len(closure) != len(function.__code__.co_freevars):
                    raise FundamentalDiscoverySubmissionError(
                        "discovery return producer closure changed"
                    )
                chain = (*chain, (
                    function.__code__,
                    id(function.__globals__),
                    module_path,
                    tuple(
                        (name, cell.cell_contents)
                        for name, cell in zip(
                            function.__code__.co_freevars,
                            closure,
                            strict=True,
                        )
                    ),
                ))
            sealed = (*sealed, (kind, chain))
        producer_callers = sealed

    def register_launch(value, *, plan, permit) -> None:
        binding_guard("launch registration")
        caller = getframe(1)
        expected_producer("launch", caller)
        register(
            "launch",
            caller,
            value,
            plan,
            permit,
            _canonical({"schema": LAUNCH_SCHEMA, **_launch_record(value)}),
        )

    def current_launch(value):
        return current("launch", value)

    def register_terminal(value, *, plan, permit, launch) -> None:
        binding_guard("terminal registration")
        caller = getframe(1)
        expected_producer("terminal", caller)
        register(
            "terminal",
            caller,
            value,
            plan,
            permit,
            launch,
            _canonical({
                "schema": TERMINAL_STATUS_SCHEMA,
                **_terminal_record(value),
            }),
        )

    def current_terminal(value):
        return current("terminal", value)

    def register_output(value, *, plan, permit, launch, terminal) -> None:
        binding_guard("output registration")
        caller = getframe(1)
        expected_producer("output", caller)
        register(
            "output",
            caller,
            value,
            plan,
            permit,
            launch,
            terminal,
            _canonical(_output_record(value)),
        )

    def current_output(value):
        return current("output", value)

    def reset_private_after_fork() -> None:
        nonlocal lock, records
        records = ()
        lock = rlock_factory()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_private_after_fork)
    return (
        seal_producers,
        register_launch,
        current_launch,
        register_terminal,
        current_terminal,
        register_output,
        current_output,
    )


def _reset_discovery_return_authorities_after_fork() -> None:
    global _LAUNCH_AUTHORITIES, _TERMINAL_AUTHORITIES, _OUTPUT_AUTHORITIES
    global _RETURN_AUTHORITIES_LOCK

    _LAUNCH_AUTHORITIES = {}
    _TERMINAL_AUTHORITIES = {}
    _OUTPUT_AUTHORITIES = {}
    _RETURN_AUTHORITIES_LOCK = threading.RLock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_discovery_return_authorities_after_fork)


def _bind_transport_capability_consumers(
    minter, execute_impl, inspect_impl, download_impl,
    require_launch_impl, require_terminal_impl, require_output_impl,
    register_launch, current_launch,
    register_terminal, current_terminal,
    register_output, current_output,
    binding_guard,
):
    """Bind transport and return authority to the three reviewed actions."""

    def require_fundamental_discovery_launch_receipt(value, plan, permit):
        binding_guard("launch require")
        return require_launch_impl(
            value,
            plan,
            permit,
            _authority_current=current_launch,
        )

    def require_fundamental_discovery_terminal_status_receipt(
        value, plan, permit, launch,
    ):
        binding_guard("terminal require")
        return require_terminal_impl(
            value,
            plan,
            permit,
            launch,
            _authority_current=current_terminal,
            _require_launch_receipt=(
                require_fundamental_discovery_launch_receipt
            ),
        )

    def require_fundamental_discovery_action_output(
        value, plan, permit, launch, terminal,
    ):
        binding_guard("output require")
        return require_output_impl(
            value,
            plan,
            permit,
            launch,
            terminal,
            _authority_current=current_output,
            _require_terminal_receipt=(
                require_fundamental_discovery_terminal_status_receipt
            ),
        )

    def execute_fundamental_discovery_submission_once(
        *, plan: FundamentalDiscoverySubmissionPlan,
        review_claim: FundamentalDiscoveryReviewClaim,
        owner_signature: OwnerSignatureAuthority | None,
        client: FormalQcTransport,
        started_at_utc: str,
    ):
        binding_guard("submission")
        return execute_impl(
            plan=plan,
            review_claim=review_claim,
            owner_signature=owner_signature,
            client=client,
            started_at_utc=started_at_utc,
            _transport_capability_minter=minter,
            _authority_register_launch=register_launch,
            _require_launch_receipt=(
                require_fundamental_discovery_launch_receipt
            ),
        )

    def inspect_fundamental_discovery_terminal_status(
        *, plan, review_claim, owner_signature, permit, launch, client,
    ):
        binding_guard("terminal status")
        return inspect_impl(
            plan=plan,
            review_claim=review_claim,
            owner_signature=owner_signature,
            permit=permit,
            launch=launch,
            client=client,
            _transport_capability_minter=minter,
            _authority_register_terminal=register_terminal,
            _require_launch_receipt=(
                require_fundamental_discovery_launch_receipt
            ),
            _require_terminal_receipt=(
                require_fundamental_discovery_terminal_status_receipt
            ),
        )

    def download_and_review_fundamental_discovery_archive(
        *, plan, review_claim, owner_signature, permit, launch, terminal,
        client,
    ) -> (
        ReviewedFundamentalUniverseDiscoveryReceipt
        | FundamentalDiscoveryNamedRefusalReceipt
    ):
        binding_guard("output archive")
        return download_impl(
            plan=plan,
            review_claim=review_claim,
            owner_signature=owner_signature,
            permit=permit,
            launch=launch,
            terminal=terminal,
            client=client,
            _transport_capability_minter=minter,
            _authority_register_output=register_output,
            _require_terminal_receipt=(
                require_fundamental_discovery_terminal_status_receipt
            ),
            _require_output_receipt=(
                require_fundamental_discovery_action_output
            ),
        )

    return (
        execute_fundamental_discovery_submission_once,
        inspect_fundamental_discovery_terminal_status,
        download_and_review_fundamental_discovery_archive,
        require_fundamental_discovery_launch_receipt,
        require_fundamental_discovery_terminal_status_receipt,
        require_fundamental_discovery_action_output,
    )


(
    _seal_discovery_return_producers,
    _discovery_return_register_launch,
    _discovery_return_current_launch,
    _discovery_return_register_terminal,
    _discovery_return_current_terminal,
    _discovery_return_register_output,
    _discovery_return_current_output,
) = _make_discovery_return_authority(
    _require_discovery_action_global_bindings
)

(
    _transport_capability_minter,
    _seal_transport_capability_callers,
) = (
    formal._claim_fundamental_discovery_transport_capability_minter()
)


(
    execute_fundamental_discovery_submission_once,
    inspect_fundamental_discovery_terminal_status,
    download_and_review_fundamental_discovery_archive,
    require_fundamental_discovery_launch_receipt,
    require_fundamental_discovery_terminal_status_receipt,
    require_fundamental_discovery_action_output,
) = _bind_transport_capability_consumers(
    _transport_capability_minter,
    _execute_fundamental_discovery_submission_once_impl,
    _inspect_fundamental_discovery_terminal_status_impl,
    _download_and_review_fundamental_discovery_archive_impl,
    _require_launch_impl,
    _require_terminal_impl,
    _require_output_impl,
    _discovery_return_register_launch,
    _discovery_return_current_launch,
    _discovery_return_register_terminal,
    _discovery_return_current_terminal,
    _discovery_return_register_output,
    _discovery_return_current_output,
    _require_discovery_action_global_bindings,
)

_seal_discovery_return_producers(
    execute_impl=_execute_fundamental_discovery_submission_once_impl,
    inspect_impl=_inspect_fundamental_discovery_terminal_status_impl,
    download_impl=_download_and_review_fundamental_discovery_archive_impl,
    execute_public=execute_fundamental_discovery_submission_once,
    inspect_public=inspect_fundamental_discovery_terminal_status,
    download_public=download_and_review_fundamental_discovery_archive,
)

_seal_transport_capability_callers(
    (
        (
            "submission",
            ((
                _execute_fundamental_discovery_submission_once_impl,
                execute_fundamental_discovery_submission_once,
            ),),
        ),
        (
            "status",
            ((
                _inspect_fundamental_discovery_terminal_status_impl,
                inspect_fundamental_discovery_terminal_status,
            ),),
        ),
        (
            "preopen_output_read",
            ((
                _download_and_review_fundamental_discovery_archive_impl,
                download_and_review_fundamental_discovery_archive,
            ),),
        ),
    )
)

del _transport_capability_minter
del _seal_transport_capability_callers
del _execute_fundamental_discovery_submission_once_impl
del _inspect_fundamental_discovery_terminal_status_impl
del _download_and_review_fundamental_discovery_archive_impl
del _require_launch_impl
del _require_terminal_impl
del _require_output_impl
del _discovery_return_register_launch
del _discovery_return_current_launch
del _discovery_return_register_terminal
del _discovery_return_current_terminal
del _discovery_return_register_output
del _discovery_return_current_output
del _seal_discovery_return_producers
del _make_discovery_return_authority
del _bind_transport_capability_consumers

_seal_discovery_action_global_bindings()
del _make_discovery_action_global_binding_guard
del _seal_discovery_action_global_bindings
del _require_discovery_action_global_bindings


__all__ = (
    "EXECUTION_ACTIONS",
    "EXECUTION_AUTHORITY_SCHEMA",
    "OWNER_REVIEW_WAIVER_BASIS",
    "OWNER_REVIEW_WAIVER_ID",
    "OWNER_REVIEW_WAIVER_SCOPE",
    "PERMIT_FILENAME",
    "PROJECT_SCHEMA_DIAGNOSTIC_FILENAME",
    "PROJECT_SCHEMA_DIAGNOSTIC_RECEIPT_SCHEMA",
    "REQUIRED_HOST_CODE_PATHS",
    "REVIEW_CLAIM_SCHEMA",
    "REVIEW_CLAIM_FILENAME",
    "FundamentalDiscoveryHostClosureBinding",
    "FundamentalDiscoveryArchiveRootPublicationAmbiguous",
    "FundamentalDiscoveryDiagnosticPublicationAmbiguous",
    "FundamentalDiscoveryLaunchReceipt",
    "FundamentalDiscoveryNamedRefusalReceipt",
    "FundamentalDiscoveryReviewClaim",
    "FundamentalDiscoverySubmissionError",
    "FundamentalDiscoverySubmissionLocked",
    "FundamentalDiscoverySubmissionPermit",
    "FundamentalDiscoverySubmissionPlan",
    "FundamentalDiscoveryTerminalStatusReceipt",
    "build_fundamental_discovery_host_closure_binding",
    "build_fundamental_discovery_submission_plan",
    "download_and_review_fundamental_discovery_archive",
    "execute_fundamental_discovery_submission_once",
    "inspect_fundamental_discovery_terminal_status",
    "load_fundamental_discovery_review_claim",
    "render_fundamental_discovery_execution_authority_candidate",
    "render_fundamental_discovery_review_claim_candidate",
    "require_fundamental_discovery_review_claim",
    "require_fundamental_discovery_action_output",
    "require_fundamental_discovery_launch_receipt",
    "require_fundamental_discovery_submission_permit",
    "require_fundamental_discovery_submission_plan",
    "require_fundamental_discovery_terminal_status_receipt",
    "verify_fundamental_discovery_host_closure_live",
)
