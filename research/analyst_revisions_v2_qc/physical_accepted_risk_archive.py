"""Disk-backed, byte-exact C1 accepted-risk authority for large Massive captures.

The legacy :class:`AcceptedRiskInputPair` is deliberately retained as the
small-fixture oracle.  It necessarily holds every provider page and every
derived row in memory.  This module instead receives pages from the capture
adapter's exhaustive physical visitor, copies only the authenticated provider
JSONL, and derives one source row at a time into private content-addressed
shards.  The conceptual C1 document is serialized incrementally with exactly
the same JSON rules as ``canonical_json_bytes``; its SHA-256, byte count, and
domain-separated formal-artifact SHA-256 therefore remain byte-identical to
the legacy authority without ever materializing that document.

No provider, credential, QuantConnect, outcome, result, deployment, order, or
trading capability exists here.  Filesystem access is limited to consuming an
already-captured artifact and producing an inert host-side archive.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import secrets
import sqlite3
import stat
import sys
import threading
import weakref
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping

from research.analyst_revisions_v2 import accepted_risk_input_pair as _c1
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskInputError,
    AcceptedRiskSourceRow,
    BreakdownDimension,
    CapturePageBinding,
    InputView,
    MassiveSourceRole,
    RowDisposition,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    parse_date,
    parse_utc_timestamp,
    require_exact_bool,
    require_exact_keys,
    require_identifier,
    require_int,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2_qc.formal_run_protocol import (
    ArtifactBinding,
    FormalRunProtocolError,
    require_artifact_binding,
)
from scripts import capture_arv2_massive as _massive
from scripts import build_arv2_massive_input_pair as _pair_builder
from scripts.build_arv2_massive_input_pair import (
    MAX_BRIDGE_ROW_BYTES,
    MassiveInputPairBridgeError,
    _canonical_rating_action,
    _rating_action_is_missing,
)

from .accepted_risk_pair_bridge import PAIR_ARTIFACT_DOMAIN


_PINNED_CAPTURE_PAGE_POST_INIT = CapturePageBinding.__post_init__
_PINNED_CAPTURE_PAGE_TYPE = CapturePageBinding
_PINNED_SOURCE_ROW_POST_INIT = AcceptedRiskSourceRow.__post_init__
_PINNED_SOURCE_ROW_TO_RECORD = AcceptedRiskSourceRow.to_record
_PINNED_SOURCE_ROW_TYPE = AcceptedRiskSourceRow
_PINNED_SOURCE_ROLE_TYPE = MassiveSourceRole
_PINNED_INPUT_VIEW_TYPE = InputView
_PINNED_ROW_DISPOSITION_TYPE = RowDisposition
_PINNED_BREAKDOWN_DIMENSION_TYPE = BreakdownDimension
_PINNED_DERIVE_SOURCE_ROW = _c1._derive_source_row
_PINNED_VALIDATE_REDACTED_QUERY = _c1._validate_redacted_query
_PINNED_REQUIRE_C1_STATIC_CONTRACT = _c1._require_static_contract
_PINNED_CANONICAL_RATING_ACTION = _canonical_rating_action
_PINNED_RATING_ACTION_IS_MISSING = _rating_action_is_missing
_PINNED_KNOWN_RATING_ACTIONS_OBJECT = _pair_builder._KNOWN_RATING_ACTIONS
_PINNED_KNOWN_RATING_ACTIONS = frozenset(_PINNED_KNOWN_RATING_ACTIONS_OBJECT)
_PINNED_ACTION_SPACE_RE_OBJECT = _pair_builder._ACTION_SPACE_RE
_PINNED_ACTION_SPACE_RE_PATTERN = _PINNED_ACTION_SPACE_RE_OBJECT.pattern
_PINNED_ACTION_SPACE_RE_FLAGS = _PINNED_ACTION_SPACE_RE_OBJECT.flags
_PINNED_MASSIVE_VISITOR = (
    _massive._visit_authenticated_massive_capture_pages_for_bridge
)
_PINNED_SPOOLED_CAPTURE_TYPE = _massive.SpooledMassiveCapture
_PINNED_PRODUCTION_TRANSPORT = _massive.PRODUCTION_TRANSPORT
_PINNED_TEST_TRANSPORT = _massive.TEST_TRANSPORT
_PINNED_REPOSITORY_ARTIFACTS_ROOT = _massive.REPOSITORY_ARTIFACTS_ROOT
_PINNED_ENDPOINT_PATHS_OBJECT = _massive.ENDPOINT_PATHS
_PINNED_ENDPOINT_PATHS = tuple(
    (role, _massive.ENDPOINT_PATHS[role]) for role in MassiveSourceRole
)
_PINNED_RENDER_REDACTED_QUERY = _c1.render_redacted_capture_query_bytes
_PINNED_PARSE_DATE = _c1.parse_date
_PINNED_PARSE_UTC_TIMESTAMP = _c1.parse_utc_timestamp
_PINNED_CANONICAL_JSON_BYTES = canonical_json_bytes
_PINNED_SHA256_BYTES = sha256_bytes
_PINNED_DECODE_UTF8 = decode_utf8
_PINNED_STRICT_JSON_LOADS = strict_json_loads
_PINNED_HASHLIB_SHA256 = hashlib.sha256
_PINNED_PAIR_ARTIFACT_DOMAIN = PAIR_ARTIFACT_DOMAIN
_PINNED_ARTIFACT_BINDING_TYPE = ArtifactBinding
_PINNED_REQUIRE_ARTIFACT_BINDING = require_artifact_binding
_PINNED_MAX_BRIDGE_ROW_BYTES = MAX_BRIDGE_ROW_BYTES
_PINNED_C1_SCALARS = (
    _c1.CAPTURE_PAGE_SCHEMA,
    _c1.CAPTURE_SCHEMA,
    _c1.INPUT_PAIR_SCHEMA,
    _c1.INPUT_PAIR_REPORT_SCHEMA,
    _c1.INPUT_PAIR_CONTRACT_ID,
    _c1.INPUT_PAIR_CONTRACT_SHA256,
    _c1.OWNER_DECISION_ID,
    _c1.CURRENT_VIEW_LABEL,
    _c1.CENSORED_VIEW_LABEL,
    _c1.MAX_CAPTURE_PAGE_BYTES,
    _c1.MAX_PROVIDER_ROWS_PER_PAGE,
)
(
    _PINNED_CAPTURE_PAGE_SCHEMA,
    _PINNED_CAPTURE_SCHEMA,
    _PINNED_INPUT_PAIR_SCHEMA,
    _PINNED_INPUT_PAIR_REPORT_SCHEMA,
    _PINNED_INPUT_PAIR_CONTRACT_ID,
    _PINNED_INPUT_PAIR_CONTRACT_SHA256,
    _PINNED_OWNER_DECISION_ID,
    _PINNED_CURRENT_VIEW_LABEL,
    _PINNED_CENSORED_VIEW_LABEL,
    _PINNED_MAX_CAPTURE_PAGE_BYTES,
    _PINNED_MAX_PROVIDER_ROWS_PER_PAGE,
) = _PINNED_C1_SCALARS
_PINNED_PREDECESSOR_PHYSICAL_CAPTURE_CONTRACT_SHA256 = (
    _massive.PREDECESSOR_PHYSICAL_CAPTURE_CONTRACT_SHA256
)
_PINNED_PHYSICAL_CAPTURE_CONTRACT_SHA256S = (
    _PINNED_INPUT_PAIR_CONTRACT_SHA256,
    _PINNED_PREDECESSOR_PHYSICAL_CAPTURE_CONTRACT_SHA256,
)


ARCHIVE_SCHEMA = "arv2-physical-accepted-risk-archive-v1"
ARCHIVE_MANIFEST = "manifest.json"
ARCHIVE_MANIFEST_DIGEST = "manifest.sha256"
SOURCE_DIRECTORY = "source"
ROW_DIRECTORY = "rows"
REPORT_FILENAME = "report.json"
MAX_ARCHIVE_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 4 * 1024 * 1024 * 1024
MAX_DERIVED_SHARD_BYTES = 1024 * 1024 * 1024
MAX_SQLITE_SPOOL_BYTES = 8 * 1024 * 1024 * 1024
MAX_SEMANTIC_ROW_BYTES = 2 * 1024 * 1024
IO_CHUNK_BYTES = 1024 * 1024

_ROLE_ORDER = tuple(MassiveSourceRole)
_RELOAD_MANIFEST_KEYS = (
    "accepted_risk",
    "archive_id",
    "archive_sha256",
    "capabilities",
    "capture_completed_at",
    "capture_id",
    "capture_sha256",
    "capture_started_at",
    "capture_transport",
    "censored_included_count",
    "current_included_count",
    "disagreement_count",
    "maximum_semantic_page_byte_count",
    "maximum_source_page_byte_count",
    "page_limit",
    "pair_artifact",
    "physical_capture_id",
    "physical_capture_sha256",
    "report",
    "requested_first_event_date",
    "requested_last_event_date",
    "role_row_counts",
    "schema",
    "shards",
    "source_artifact_id",
    "source_manifest_sha256",
    "source_page_count",
    "source_page_root_sha256",
    "source_row_count",
    "storage",
)
_RELOAD_ROLE_COUNT_KEYS = ("row_count", "source_role")
_RELOAD_PAIR_ARTIFACT_KEYS = (
    "artifact_id",
    "artifact_sha256",
    "byte_count",
    "content_sha256",
)
_RELOAD_REPORT_KEYS = ("byte_count", "relative_path", "sha256")
_RELOAD_SHARD_KEYS = (
    "endpoint_identifier",
    "next_cursor_sha256",
    "page_number",
    "raw_response_sha256",
    "redacted_query_sha256",
    "request_cursor_sha256",
    "response_received_at",
    "row_count",
    "semantic_byte_count",
    "semantic_relative_path",
    "semantic_sha256",
    "source_byte_count",
    "source_relative_path",
    "source_role",
    "source_sha256",
    "terminal_page",
)
_RELOAD_STORAGE = (
    ("full_capture_materialized", False),
    ("one_source_page_derived_at_a_time", True),
    ("source_pages_copied_before_derivation", True),
)
_RELOAD_ACCEPTED_RISK = (
    ("pristine_point_in_time", False),
    ("views_share_one_capture", True),
)
_RELOAD_CAPABILITIES = tuple(
    (name, False)
    for name in (
        "credential_access",
        "deployment",
        "orders",
        "outcome_access",
        "provider_access",
        "quantconnect_access",
        "result_access",
        "trading",
    )
)
_PINNED_RELOAD_CONTRACT = (
    _RELOAD_MANIFEST_KEYS,
    _RELOAD_ROLE_COUNT_KEYS,
    _RELOAD_PAIR_ARTIFACT_KEYS,
    _RELOAD_REPORT_KEYS,
    _RELOAD_SHARD_KEYS,
    _RELOAD_STORAGE,
    _RELOAD_ACCEPTED_RISK,
    _RELOAD_CAPABILITIES,
)


class PhysicalAcceptedRiskArchiveError(ValueError):
    """A physical capture or its disk-backed C1 derivation is not exact."""


class PhysicalAcceptedRiskArchiveCapacityError(
    PhysicalAcceptedRiskArchiveError
):
    """A fixed disk or per-row bound was exceeded without truncation."""


class _ArchivePublicationError(PhysicalAcceptedRiskArchiveError):
    """Internal publication failure carrying the only safe cleanup decision."""

    def __init__(self, message: str, *, preserve_stage: bool) -> None:
        super().__init__(message)
        self.preserve_stage = preserve_stage


def _require_dependency_bindings() -> None:
    try:
        _PINNED_REQUIRE_C1_STATIC_CONTRACT()
        current_scalars = (
            _c1.CAPTURE_PAGE_SCHEMA,
            _c1.CAPTURE_SCHEMA,
            _c1.INPUT_PAIR_SCHEMA,
            _c1.INPUT_PAIR_REPORT_SCHEMA,
            _c1.INPUT_PAIR_CONTRACT_ID,
            _c1.INPUT_PAIR_CONTRACT_SHA256,
            _c1.OWNER_DECISION_ID,
            _c1.CURRENT_VIEW_LABEL,
            _c1.CENSORED_VIEW_LABEL,
            _c1.MAX_CAPTURE_PAGE_BYTES,
            _c1.MAX_PROVIDER_ROWS_PER_PAGE,
        )
        changed = (
            getattr(
                _massive,
                "_visit_authenticated_massive_capture_pages_for_bridge",
                None,
            )
            is not _PINNED_MASSIVE_VISITOR
            or getattr(_massive, "SpooledMassiveCapture", None)
            is not _PINNED_SPOOLED_CAPTURE_TYPE
            or type(_massive.PRODUCTION_TRANSPORT) is not str
            or _massive.PRODUCTION_TRANSPORT != _PINNED_PRODUCTION_TRANSPORT
            or type(_massive.TEST_TRANSPORT) is not str
            or _massive.TEST_TRANSPORT != _PINNED_TEST_TRANSPORT
            or _massive.REPOSITORY_ARTIFACTS_ROOT
            is not _PINNED_REPOSITORY_ARTIFACTS_ROOT
            or type(_massive.PREDECESSOR_PHYSICAL_CAPTURE_CONTRACT_SHA256)
            is not str
            or _massive.PREDECESSOR_PHYSICAL_CAPTURE_CONTRACT_SHA256
            != _PINNED_PREDECESSOR_PHYSICAL_CAPTURE_CONTRACT_SHA256
            or _massive.ENDPOINT_PATHS is not _PINNED_ENDPOINT_PATHS_OBJECT
            or tuple(
                (role, _massive.ENDPOINT_PATHS[role]) for role in _ROLE_ORDER
            )
            != _PINNED_ENDPOINT_PATHS
            or _c1._derive_source_row is not _PINNED_DERIVE_SOURCE_ROW
            or _c1._validate_redacted_query
            is not _PINNED_VALIDATE_REDACTED_QUERY
            or _c1._require_static_contract
            is not _PINNED_REQUIRE_C1_STATIC_CONTRACT
            or _c1.render_redacted_capture_query_bytes
            is not _PINNED_RENDER_REDACTED_QUERY
            or _c1.parse_date is not _PINNED_PARSE_DATE
            or _c1.parse_utc_timestamp is not _PINNED_PARSE_UTC_TIMESTAMP
            or CapturePageBinding is not _PINNED_CAPTURE_PAGE_TYPE
            or CapturePageBinding.__post_init__ is not _PINNED_CAPTURE_PAGE_POST_INIT
            or AcceptedRiskSourceRow is not _PINNED_SOURCE_ROW_TYPE
            or AcceptedRiskSourceRow.__post_init__
            is not _PINNED_SOURCE_ROW_POST_INIT
            or AcceptedRiskSourceRow.to_record is not _PINNED_SOURCE_ROW_TO_RECORD
            or MassiveSourceRole is not _PINNED_SOURCE_ROLE_TYPE
            or InputView is not _PINNED_INPUT_VIEW_TYPE
            or RowDisposition is not _PINNED_ROW_DISPOSITION_TYPE
            or BreakdownDimension is not _PINNED_BREAKDOWN_DIMENSION_TYPE
            or ArtifactBinding is not _PINNED_ARTIFACT_BINDING_TYPE
            or require_artifact_binding is not _PINNED_REQUIRE_ARTIFACT_BINDING
            or canonical_json_bytes is not _PINNED_CANONICAL_JSON_BYTES
            or sha256_bytes is not _PINNED_SHA256_BYTES
            or decode_utf8 is not _PINNED_DECODE_UTF8
            or strict_json_loads is not _PINNED_STRICT_JSON_LOADS
            or hashlib.sha256 is not _PINNED_HASHLIB_SHA256
            or _canonical_rating_action is not _PINNED_CANONICAL_RATING_ACTION
            or _rating_action_is_missing is not _PINNED_RATING_ACTION_IS_MISSING
            or _pair_builder._KNOWN_RATING_ACTIONS
            is not _PINNED_KNOWN_RATING_ACTIONS_OBJECT
            or type(_pair_builder._KNOWN_RATING_ACTIONS) is not frozenset
            or _pair_builder._KNOWN_RATING_ACTIONS
            != _PINNED_KNOWN_RATING_ACTIONS
            or _pair_builder._ACTION_SPACE_RE
            is not _PINNED_ACTION_SPACE_RE_OBJECT
            or _pair_builder._ACTION_SPACE_RE.pattern
            != _PINNED_ACTION_SPACE_RE_PATTERN
            or _pair_builder._ACTION_SPACE_RE.flags
            != _PINNED_ACTION_SPACE_RE_FLAGS
            or MAX_BRIDGE_ROW_BYTES != _PINNED_MAX_BRIDGE_ROW_BYTES
            or PAIR_ARTIFACT_DOMAIN is not _PINNED_PAIR_ARTIFACT_DOMAIN
            or current_scalars != _PINNED_C1_SCALARS
            or _ROLE_ORDER != tuple(_PINNED_SOURCE_ROLE_TYPE)
            or (
                _RELOAD_MANIFEST_KEYS,
                _RELOAD_ROLE_COUNT_KEYS,
                _RELOAD_PAIR_ARTIFACT_KEYS,
                _RELOAD_REPORT_KEYS,
                _RELOAD_SHARD_KEYS,
                _RELOAD_STORAGE,
                _RELOAD_ACCEPTED_RISK,
                _RELOAD_CAPABILITIES,
            )
            != _PINNED_RELOAD_CONTRACT
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        changed = True
    if changed:
        raise PhysicalAcceptedRiskArchiveError(
            "physical accepted-risk dependency binding changed"
        )


@dataclasses.dataclass(frozen=True, slots=True)
class AcceptedRiskShardDescriptor:
    source_role: MassiveSourceRole
    page_number: int
    source_relative_path: str
    source_byte_count: int
    source_sha256: str
    semantic_relative_path: str
    semantic_byte_count: int
    semantic_sha256: str
    row_count: int
    endpoint_identifier: str
    redacted_query_sha256: str
    request_cursor_sha256: str | None
    next_cursor_sha256: str | None
    terminal_page: bool
    response_received_at: str
    raw_response_sha256: str

    def to_record(self) -> dict[str, object]:
        return {
            "source_role": self.source_role.value,
            "page_number": self.page_number,
            "source_relative_path": self.source_relative_path,
            "source_byte_count": self.source_byte_count,
            "source_sha256": self.source_sha256,
            "semantic_relative_path": self.semantic_relative_path,
            "semantic_byte_count": self.semantic_byte_count,
            "semantic_sha256": self.semantic_sha256,
            "row_count": self.row_count,
            "endpoint_identifier": self.endpoint_identifier,
            "redacted_query_sha256": self.redacted_query_sha256,
            "request_cursor_sha256": self.request_cursor_sha256,
            "next_cursor_sha256": self.next_cursor_sha256,
            "terminal_page": self.terminal_page,
            "response_received_at": self.response_received_at,
            "raw_response_sha256": self.raw_response_sha256,
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class PhysicalAcceptedRiskArchive:
    schema: str
    archive_id: str
    archive_sha256: str
    archive_path: Path
    source_artifact_path: Path
    source_artifact_id: str
    source_manifest_sha256: str
    capture_transport: str
    physical_capture_id: str
    physical_capture_sha256: str
    capture_started_at: str
    capture_completed_at: str
    capture_id: str
    capture_sha256: str
    requested_first_event_date: str
    requested_last_event_date: str
    page_limit: int
    source_page_root_sha256: str
    source_page_count: int
    source_row_count: int
    role_row_counts: tuple[tuple[MassiveSourceRole, int], ...]
    pair_id: str
    pair_sha256: str
    pair_artifact: ArtifactBinding
    report_sha256: str
    report_byte_count: int
    current_included_count: int
    censored_included_count: int
    disagreement_count: int
    shards: tuple[AcceptedRiskShardDescriptor, ...]
    maximum_source_page_byte_count: int
    maximum_semantic_page_byte_count: int
    full_capture_materialized: bool
    views_share_one_capture: bool
    pristine_point_in_time: bool
    provider_access: bool
    credential_access: bool
    quantconnect_access: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


@dataclasses.dataclass(frozen=True, slots=True)
class _CaptureContext:
    capture_id: str
    requested_first_event_date: str
    requested_last_event_date: str


@dataclasses.dataclass(frozen=True, slots=True)
class _PinnedArchiveLeaf:
    identity: tuple[int, int, int, int, int, int, int, int]
    maximum_bytes: int
    expected_byte_count: int
    expected_sha256: str
    name: str


@dataclasses.dataclass(frozen=True, slots=True)
class _CopiedPage:
    source_role: MassiveSourceRole
    page_number: int
    endpoint_identifier: str
    redacted_query_bytes: bytes
    redacted_query_sha256: str
    request_cursor_sha256: str | None
    next_cursor_sha256: str | None
    terminal_page: bool
    response_received_at: str
    raw_response_sha256: str
    provider_rows_sha256: str
    row_count: int
    source_relative_path: str
    source_byte_count: int
    source_sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class _RawJson:
    chunks: Callable[[], Iterator[bytes]]


@dataclasses.dataclass(frozen=True, slots=True)
class _JsonArray:
    items: Callable[[], Iterator[bytes]]


_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalAcceptedRiskArchive],
        tuple[object, ...],
        tuple[object, ...],
        tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
        int,
    ],
] = {}
_AUTHORITY_LOCK = threading.RLock()


def _forget(identity: int, reference: object) -> None:
    with _AUTHORITY_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AUTHORITIES.pop(identity, None)


def _canonical_fragment(value: object) -> bytes:
    return canonical_json_bytes(value)[:-1]


def _iter_json_value(value: object) -> Iterator[bytes]:
    if type(value) is _RawJson:
        yield from value.chunks()
        return
    if type(value) is _JsonArray:
        yield b"["
        first = True
        for item in value.items():
            if not first:
                yield b","
            yield item
            first = False
        yield b"]"
        return
    yield _canonical_fragment(value)


def _iter_canonical_object(
    values: Mapping[str, object], *, terminate: bool
) -> Iterator[bytes]:
    """Stream exactly ``json.dumps(sort_keys=True, separators=(',', ':'))``."""

    if type(values) is not dict or any(type(key) is not str for key in values):
        raise PhysicalAcceptedRiskArchiveError(
            "streamed canonical object requires an exact string-keyed dict"
        )
    yield b"{"
    for index, key in enumerate(sorted(values)):
        if index:
            yield b","
        yield _canonical_fragment(key)
        yield b":"
        yield from _iter_json_value(values[key])
    yield b"}"
    if terminate:
        yield b"\n"


def _iter_provider_rows(payload: bytes) -> Iterator[tuple[dict[str, Any], bytes]]:
    if type(payload) is not bytes or (
        payload and (not payload.endswith(b"\n") or b"\r" in payload)
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "provider rows are not exact LF-terminated bytes"
        )
    start = 0
    while start < len(payload):
        end = payload.find(b"\n", start)
        if end < 0:
            raise PhysicalAcceptedRiskArchiveError(
                "provider row page lost its LF terminator"
            )
        raw = payload[start : end + 1]
        if len(raw) > MAX_BRIDGE_ROW_BYTES or len(raw) == 1:
            raise PhysicalAcceptedRiskArchiveCapacityError(
                "provider row exceeds the fixed per-row byte bound"
            )
        try:
            value = strict_json_loads(
                decode_utf8(raw[:-1], "streamed Massive provider row"),
                "streamed Massive provider row",
            )
        except CanonicalEvidenceError as exc:
            raise PhysicalAcceptedRiskArchiveError(
                "provider row is not strict JSON"
            ) from exc
        if type(value) is not dict:
            raise PhysicalAcceptedRiskArchiveError(
                "provider row is not a JSON object"
            )
        yield value, raw
        start = end + 1


def _semantic_requires_duplicate_guidance_quarantine(payload: bytes) -> bool:
    """Recover the authenticated census decision used to build one row.

    The physical source shards are the preserved capture and the semantic
    shards are the derived C1 authority.  A duplicate decision cannot be
    recovered from one source row in isolation, so iterator reauthentication
    reads only this joint-exclusion marker from the already authenticated
    semantic shard before independently rederiving and byte-comparing the
    complete row.  New semantic authority is still created only after the
    builder's complete SQLite provider-ID census.
    """

    if type(payload) is not bytes:
        return False
    try:
        value = strict_json_loads(
            decode_utf8(payload, "accepted-risk semantic row"),
            "accepted-risk semantic row",
        )
    except CanonicalEvidenceError:
        return False
    if type(value) is not dict:
        return False
    current = value.get("current_view")
    censored = value.get("censored_view")
    if type(current) is not dict or type(censored) is not dict:
        return False
    expected = RowDisposition.DUPLICATE_PROVIDER_EVENT_ID.value
    return (
        current.get("disposition") == expected
        and censored.get("disposition") == expected
    )


def _write_private(
    path: Path, chunks: Iterable[bytes], *, maximum_bytes: int
) -> tuple[int, str]:
    if type(maximum_bytes) is not int or maximum_bytes < 0:
        raise PhysicalAcceptedRiskArchiveError(
            "archive writer byte bound is invalid"
        )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    count = 0
    digest = hashlib.sha256()
    try:
        os.fchmod(descriptor, 0o600)
        for chunk in chunks:
            if type(chunk) is not bytes:
                raise PhysicalAcceptedRiskArchiveError(
                    "archive writer received a non-bytes chunk"
                )
            if count + len(chunk) > maximum_bytes:
                raise PhysicalAcceptedRiskArchiveCapacityError(
                    "archive writer exceeded its fixed byte bound"
                )
            digest.update(chunk)
            count += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise PhysicalAcceptedRiskArchiveError(
                        "archive writer stalled"
                    )
                view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        finally:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    os.close(descriptor)
    return count, digest.hexdigest()


def _write_private_at(
    parent_fd: int,
    filename: str,
    chunks: Iterable[bytes],
    *,
    maximum_bytes: int,
) -> tuple[int, str]:
    """Durably create one private leaf beneath a held directory descriptor."""

    if (
        type(filename) is not str
        or not filename
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or type(maximum_bytes) is not int
        or maximum_bytes < 0
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "archive writer bounded child name is invalid"
        )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )
    descriptor: int | None = None
    created_identity: tuple[int, int] | None = None
    count = 0
    digest = hashlib.sha256()
    try:
        descriptor = os.open(filename, flags, 0o600, dir_fd=parent_fd)
        os.fchmod(descriptor, 0o600)
        created = os.fstat(descriptor)
        created_identity = (created.st_dev, created.st_ino)
        for chunk in chunks:
            if type(chunk) is not bytes:
                raise PhysicalAcceptedRiskArchiveError(
                    "archive writer received a non-bytes chunk"
                )
            if count + len(chunk) > maximum_bytes:
                raise PhysicalAcceptedRiskArchiveCapacityError(
                    "archive writer exceeded its fixed byte bound"
                )
            digest.update(chunk)
            count += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise PhysicalAcceptedRiskArchiveError(
                        "archive writer stalled"
                    )
                view = view[written:]
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        named = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or opened.st_size != count
            or (hasattr(os, "getuid") and opened.st_uid != os.getuid())
            or _regular_file_identity(opened) != _regular_file_identity(named)
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "archive writer leaf identity changed"
            )
    except BaseException:
        if descriptor is not None:
            try:
                opened = os.fstat(descriptor)
                try:
                    named = os.stat(
                        filename, dir_fd=parent_fd, follow_symlinks=False
                    )
                except OSError:
                    named = None
                if (
                    created_identity is not None
                    and (opened.st_dev, opened.st_ino) == created_identity
                    and named is not None
                    and (named.st_dev, named.st_ino) == created_identity
                    and stat.S_ISREG(named.st_mode)
                    and stat.S_IMODE(named.st_mode) == 0o600
                    and named.st_nlink == 1
                    and (
                        not hasattr(os, "getuid")
                        or named.st_uid == os.getuid()
                    )
                ):
                    try:
                        os.unlink(filename, dir_fd=parent_fd)
                    except OSError:
                        # The primary writer failure remains authoritative.
                        # Any cleanup uncertainty preserves the named residue.
                        pass
            except OSError:
                pass
            finally:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        raise
    assert descriptor is not None
    os.close(descriptor)
    return count, digest.hexdigest()


def _spool_bytes(connection: sqlite3.Connection) -> int:
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    return page_count * page_size


def _open_spool(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA journal_mode=MEMORY;
        PRAGMA synchronous=FULL;
        PRAGMA temp_store=FILE;
        CREATE TABLE provider_ids (
            provider_event_id TEXT PRIMARY KEY,
            source_role_ordinal INTEGER NOT NULL,
            occurrence_count INTEGER NOT NULL CHECK (occurrence_count >= 1)
        ) WITHOUT ROWID;
        CREATE TABLE breakdowns (
            dimension_ordinal INTEGER NOT NULL,
            dimension TEXT NOT NULL,
            key TEXT NOT NULL,
            total_count INTEGER NOT NULL,
            current_included_count INTEGER NOT NULL,
            censored_included_count INTEGER NOT NULL,
            disagreement_count INTEGER NOT NULL,
            PRIMARY KEY (dimension_ordinal, key)
        ) WITHOUT ROWID;
        """
    )
    return connection


def _insert_provider_id(
    connection: sqlite3.Connection,
    row: dict[str, Any],
    source_role: MassiveSourceRole,
) -> None:
    if type(source_role) is not MassiveSourceRole:
        raise PhysicalAcceptedRiskArchiveError(
            "provider-ID census source role changed type"
        )
    try:
        provider_id = require_identifier(row.get("benzinga_id"), "benzinga_id")
    except CanonicalEvidenceError:
        return
    role_ordinal = _ROLE_ORDER.index(source_role)
    try:
        connection.execute(
            "INSERT INTO provider_ids(provider_event_id, source_role_ordinal, "
            "occurrence_count) VALUES (?, ?, 1)",
            (provider_id, role_ordinal),
        )
    except sqlite3.IntegrityError as exc:
        prior = connection.execute(
            "SELECT source_role_ordinal, occurrence_count FROM provider_ids "
            "WHERE provider_event_id = ?",
            (provider_id,),
        ).fetchone()
        guidance_ordinal = _ROLE_ORDER.index(
            MassiveSourceRole.CORPORATE_GUIDANCE
        )
        if (
            type(prior) is not tuple
            or len(prior) != 2
            or type(prior[0]) is not int
            or type(prior[1]) is not int
            or prior[0] != guidance_ordinal
            or role_ordinal != guidance_ordinal
            or prior[1] < 1
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "duplicate or conflicting benzinga_id invalidates the capture"
            ) from exc
        cursor = connection.execute(
            "UPDATE provider_ids SET occurrence_count = occurrence_count + 1 "
            "WHERE provider_event_id = ? AND source_role_ordinal = ?",
            (provider_id, guidance_ordinal),
        )
        if cursor.rowcount != 1:
            raise PhysicalAcceptedRiskArchiveError(
                "guidance duplicate-ID census update was ambiguous"
            ) from exc


def _is_duplicate_guidance_provider_id(
    connection: sqlite3.Connection,
    row: dict[str, Any],
    source_role: MassiveSourceRole,
) -> bool:
    if type(source_role) is not MassiveSourceRole:
        raise PhysicalAcceptedRiskArchiveError(
            "provider-ID lookup source role changed type"
        )
    if source_role is not MassiveSourceRole.CORPORATE_GUIDANCE:
        return False
    try:
        provider_id = require_identifier(row.get("benzinga_id"), "benzinga_id")
    except CanonicalEvidenceError:
        return False
    census = connection.execute(
        "SELECT source_role_ordinal, occurrence_count FROM provider_ids "
        "WHERE provider_event_id = ?",
        (provider_id,),
    ).fetchone()
    guidance_ordinal = _ROLE_ORDER.index(MassiveSourceRole.CORPORATE_GUIDANCE)
    if (
        type(census) is not tuple
        or len(census) != 2
        or type(census[0]) is not int
        or type(census[1]) is not int
        or census[0] != guidance_ordinal
        or census[1] < 1
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "guidance duplicate-ID census is incomplete"
        )
    return census[1] > 1


def _breakdown_keys(row: AcceptedRiskSourceRow) -> tuple[tuple[int, str, str], ...]:
    keys = {
        BreakdownDimension.OVERALL: "all_rows",
        BreakdownDimension.EVENT_YEAR: (
            str(row.event_year)
            if row.event_year is not None
            else "__invalid_event_year__"
        ),
        BreakdownDimension.SOURCE_ROLE: row.locator.source_role.value,
        BreakdownDimension.ACTION: row.action_label,
        BreakdownDimension.FIRM: row.firm_label,
        BreakdownDimension.SECURITY_LABEL: row.current_restated_security_label,
    }
    return tuple(
        (ordinal, dimension.value, keys[dimension])
        for ordinal, dimension in enumerate(BreakdownDimension)
    )


def _accumulate_row(
    connection: sqlite3.Connection,
    dispositions: Counter[tuple[InputView, RowDisposition]],
    row: AcceptedRiskSourceRow,
) -> None:
    current = int(row.current_view.included)
    censored = int(row.censored_view.included)
    disagreement = int(row.current_view.included != row.censored_view.included)
    dispositions[(InputView.CURRENT_ROW, row.current_view.disposition)] += 1
    dispositions[(InputView.CONSERVATIVE_CENSORED, row.censored_view.disposition)] += 1
    for ordinal, dimension, key in _breakdown_keys(row):
        connection.execute(
            """
            INSERT INTO breakdowns(
                dimension_ordinal, dimension, key, total_count,
                current_included_count, censored_included_count,
                disagreement_count
            ) VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(dimension_ordinal, key) DO UPDATE SET
                total_count=total_count+1,
                current_included_count=current_included_count+excluded.current_included_count,
                censored_included_count=censored_included_count+excluded.censored_included_count,
                disagreement_count=disagreement_count+excluded.disagreement_count
            """,
            (ordinal, dimension, key, current, censored, disagreement),
        )


def _breakdown_record(raw: tuple[object, ...]) -> dict[str, object]:
    _ordinal, dimension, key, total, current, censored, disagreement = raw
    return {
        "dimension": dimension,
        "key": key,
        "total_count": total,
        "current_included_count": current,
        "censored_included_count": censored,
        "disagreement_count": disagreement,
        "current_inclusion_rate": {"numerator": current, "denominator": total},
        "censored_inclusion_rate": {"numerator": censored, "denominator": total},
        "disagreement_rate": {"numerator": disagreement, "denominator": total},
    }


def _report_record_parts(
    connection: sqlite3.Connection,
    dispositions: Counter[tuple[InputView, RowDisposition]],
    *,
    total_row_count: int,
    current_included_count: int,
    censored_included_count: int,
    disagreement_count: int,
) -> dict[str, object]:
    def breakdown_items() -> Iterator[bytes]:
        cursor = connection.execute(
            "SELECT dimension_ordinal, dimension, key, total_count, "
            "current_included_count, censored_included_count, disagreement_count "
            "FROM breakdowns ORDER BY dimension_ordinal, key"
        )
        for raw in cursor:
            yield _canonical_fragment(_breakdown_record(tuple(raw)))

    disposition_records = [
        {
            "view": view.value,
            "disposition": disposition.value,
            "count": dispositions[(view, disposition)],
        }
        for view in InputView
        for disposition in RowDisposition
    ]
    return {
        "schema": _PINNED_INPUT_PAIR_REPORT_SCHEMA,
        "total_row_count": total_row_count,
        "current_included_count": current_included_count,
        "censored_included_count": censored_included_count,
        "disagreement_count": disagreement_count,
        "disposition_counts": disposition_records,
        "breakdowns": _JsonArray(breakdown_items),
        "mapping_disagreement_report": None,
        "signal_disagreement_report": None,
    }


def _pair_fields(
    *,
    capture_id: str,
    capture_sha256: str,
    row_items: Callable[[], Iterator[bytes]],
    report_items: Callable[[], Iterator[bytes]],
) -> dict[str, object]:
    return {
        "schema": _PINNED_INPUT_PAIR_SCHEMA,
        "contract_id": _PINNED_INPUT_PAIR_CONTRACT_ID,
        "contract_sha256": _PINNED_INPUT_PAIR_CONTRACT_SHA256,
        "capture_id": capture_id,
        "capture_sha256": capture_sha256,
        "rows": _JsonArray(row_items),
        "report": _RawJson(report_items),
        "current_view_label": _PINNED_CURRENT_VIEW_LABEL,
        "censored_view_label": _PINNED_CENSORED_VIEW_LABEL,
        "pristine_point_in_time": False,
        "earlier_version_imputation_performed": False,
        "views_share_one_capture": True,
        "guidance_clock_authenticated": False,
        "identity_mapping_authenticated": False,
        "rating_mapping_authenticated": False,
        "signal_rows_constructed": False,
        "production_input_authority": False,
        "outcome_gate_open": False,
        "provider_binding": None,
        "security_master_binding": None,
        "outcome_binding": None,
        "provider_io_performed": False,
        "credential_access_performed": False,
        "filesystem_io_performed": False,
        "quantconnect_io_performed": False,
        "object_store_io_performed": False,
        "market_data_access_performed": False,
        "outcome_access_performed": False,
        "deployment_performed": False,
        "order_access_performed": False,
        "trading_performed": False,
    }


def _archive_fingerprint(value: PhysicalAcceptedRiskArchive) -> tuple[object, ...]:
    return tuple(getattr(value, field.name) for field in dataclasses.fields(value))


def _archive_topology(value: PhysicalAcceptedRiskArchive) -> tuple[object, ...]:
    return (
        id(value.role_row_counts),
        tuple(id(item) for item in value.role_row_counts),
        id(value.shards),
        tuple(id(item) for item in value.shards),
        id(value.pair_artifact),
    )


def _source_page_root(pages: tuple[_CopiedPage, ...]) -> str:
    record = {
        "schema": "arv2-massive-physical-source-page-root-v1",
        "pages": [
            {
                "source_role": item.source_role.value,
                "endpoint_path": next(
                    path
                    for role, path in _PINNED_ENDPOINT_PATHS
                    if role is item.source_role
                ),
                "endpoint_identifier": item.endpoint_identifier,
                "redacted_query_sha256": item.redacted_query_sha256,
                "page_number": item.page_number,
                "request_cursor_sha256": item.request_cursor_sha256,
                "next_cursor_sha256": item.next_cursor_sha256,
                "terminal_page": item.terminal_page,
                "response_received_at": item.response_received_at,
                "raw_response_sha256": item.raw_response_sha256,
                "provider_rows_sha256": item.provider_rows_sha256,
                "row_count": item.row_count,
                "raw_response_extraction_authenticated": True,
            }
            for item in pages
        ],
    }
    return sha256_bytes(canonical_json_bytes(record))


def _capture_record(
    *,
    pages: tuple[_CopiedPage, ...],
    capture_started_at: str,
    capture_completed_at: str,
    requested_first_event_date: str,
    requested_last_event_date: str,
    raw_response_extraction_verified: bool,
    contract_sha256: str,
) -> dict[str, object]:
    """Reproduce one admitted C1 capture record without retaining page bytes."""

    if (
        type(contract_sha256) is not str
        or contract_sha256 not in _PINNED_PHYSICAL_CAPTURE_CONTRACT_SHA256S
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "physical capture contract hash is not an admitted exact version"
        )

    counts: Counter[MassiveSourceRole] = Counter()
    for item in pages:
        counts[item.source_role] += item.row_count
    return {
        "schema": _PINNED_CAPTURE_SCHEMA,
        "contract_id": _PINNED_INPUT_PAIR_CONTRACT_ID,
        "contract_sha256": contract_sha256,
        "capture_started_at": capture_started_at,
        "capture_completed_at": capture_completed_at,
        "requested_first_event_date": requested_first_event_date,
        "requested_last_event_date": requested_last_event_date,
        "pages": [
            {
                "schema": _PINNED_CAPTURE_PAGE_SCHEMA,
                "source_role": item.source_role.value,
                "endpoint_identifier": item.endpoint_identifier,
                "redacted_query_sha256": item.redacted_query_sha256,
                "page_number": item.page_number,
                "request_cursor_sha256": item.request_cursor_sha256,
                "next_cursor_sha256": item.next_cursor_sha256,
                "terminal_page": item.terminal_page,
                "response_received_at": item.response_received_at,
                "raw_response_sha256": item.raw_response_sha256,
                "raw_response_extraction_verified": (
                    raw_response_extraction_verified
                ),
                "provider_rows_sha256": item.provider_rows_sha256,
                "row_count": item.row_count,
            }
            for item in pages
        ],
        "total_page_count": len(pages),
        "total_row_count": sum(item.row_count for item in pages),
        "role_row_counts": [
            {"source_role": role.value, "row_count": counts[role]}
            for role in _ROLE_ORDER
        ],
        "owner_decision_id": _PINNED_OWNER_DECISION_ID,
        "transactional_snapshot": False,
        "complete_version_history": False,
        "complete_deletion_tombstones": False,
        "point_in_time_ticker_identity": False,
        "pristine_point_in_time": False,
    }


def _capture_identity(record: dict[str, object]) -> tuple[str, str]:
    digest = sha256_bytes(canonical_json_bytes(record))
    return f"arv2-capture-{digest[:24]}", digest


def _authenticate_physical_capture_identity(
    *,
    pages: tuple[_CopiedPage, ...],
    capture_started_at: str,
    capture_completed_at: str,
    requested_first_event_date: str,
    requested_last_event_date: str,
    expected_capture_id: str,
    expected_capture_sha256: str,
) -> tuple[str, str]:
    """Authenticate physical bytes under exactly current or measured predecessor.

    This admits the predecessor only for the immutable artifact's physical
    identity.  Every successor capture and pair derived from those bytes uses
    the current C1 contract hash at its separate call site.
    """

    matches: list[tuple[str, str]] = []
    for contract_sha256 in _PINNED_PHYSICAL_CAPTURE_CONTRACT_SHA256S:
        candidate = _capture_identity(
            _capture_record(
                pages=pages,
                capture_started_at=capture_started_at,
                capture_completed_at=capture_completed_at,
                requested_first_event_date=requested_first_event_date,
                requested_last_event_date=requested_last_event_date,
                raw_response_extraction_verified=True,
                contract_sha256=contract_sha256,
            )
        )
        if candidate == (expected_capture_id, expected_capture_sha256):
            matches.append(candidate)
    if len(matches) != 1:
        raise PhysicalAcceptedRiskArchiveError(
            "physical capture identity does not match an admitted contract"
        )
    return matches[0]


def _archive_seed(
    *,
    source_artifact_id: str,
    source_manifest_sha256: str,
    capture_transport: str,
    physical_capture_id: str,
    physical_capture_sha256: str,
    capture_started_at: str,
    capture_completed_at: str,
    capture_id: str,
    capture_sha256: str,
    requested_first_event_date: str,
    requested_last_event_date: str,
    page_limit: int,
    source_page_root_sha256: str,
    source_page_count: int,
    source_row_count: int,
    role_row_counts: tuple[tuple[MassiveSourceRole, int], ...],
    pair_artifact: ArtifactBinding,
    report_sha256: str,
    report_byte_count: int,
    current_included_count: int,
    censored_included_count: int,
    disagreement_count: int,
    shards: tuple[AcceptedRiskShardDescriptor, ...],
    maximum_source_page_byte_count: int,
    maximum_semantic_page_byte_count: int,
) -> dict[str, object]:
    return {
        "schema": ARCHIVE_SCHEMA,
        "source_artifact_id": source_artifact_id,
        "source_manifest_sha256": source_manifest_sha256,
        "capture_transport": capture_transport,
        "physical_capture_id": physical_capture_id,
        "physical_capture_sha256": physical_capture_sha256,
        "capture_started_at": capture_started_at,
        "capture_completed_at": capture_completed_at,
        "capture_id": capture_id,
        "capture_sha256": capture_sha256,
        "requested_first_event_date": requested_first_event_date,
        "requested_last_event_date": requested_last_event_date,
        "page_limit": page_limit,
        "source_page_root_sha256": source_page_root_sha256,
        "source_page_count": source_page_count,
        "source_row_count": source_row_count,
        "role_row_counts": [
            {"source_role": role.value, "row_count": count}
            for role, count in role_row_counts
        ],
        "pair_artifact": pair_artifact.to_record(),
        "report": {
            "relative_path": REPORT_FILENAME,
            "sha256": report_sha256,
            "byte_count": report_byte_count,
        },
        "current_included_count": current_included_count,
        "censored_included_count": censored_included_count,
        "disagreement_count": disagreement_count,
        "shards": [item.to_record() for item in shards],
        "maximum_source_page_byte_count": maximum_source_page_byte_count,
        "maximum_semantic_page_byte_count": maximum_semantic_page_byte_count,
        "storage": {
            "source_pages_copied_before_derivation": True,
            "one_source_page_derived_at_a_time": True,
            "full_capture_materialized": False,
        },
        "accepted_risk": {
            "views_share_one_capture": True,
            "pristine_point_in_time": False,
        },
        "capabilities": {
            "provider_access": False,
            "credential_access": False,
            "quantconnect_access": False,
            "outcome_access": False,
            "result_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


class _AcceptedRiskArchiveStage:
    """Mutable construction state; it never escapes as authority."""

    def __init__(
        self,
        stage: Path,
        connection: sqlite3.Connection,
        *,
        stage_fd: int,
        source_fd: int,
        rows_fd: int,
    ) -> None:
        self.stage = stage
        self.connection = connection
        self.stage_fd = stage_fd
        self.source_fd = source_fd
        self.rows_fd = rows_fd
        self.copied_pages: list[_CopiedPage] = []
        self.expected_role_ordinal = 0
        self.expected_page_number = 1
        self.requested_first_event_date: str | None = None
        self.requested_last_event_date: str | None = None
        self.page_limit: int | None = None
        self.observed_rows = 0
        self.role_rows: Counter[MassiveSourceRole] = Counter()
        self.maximum_source_page_byte_count = 0
        self.terminal_roles: set[MassiveSourceRole] = set()
        self.seen_cursor_hashes: dict[MassiveSourceRole, set[str]] = {
            role: set() for role in _ROLE_ORDER
        }
        self.seen_response_hashes: dict[MassiveSourceRole, set[str]] = {
            role: set() for role in _ROLE_ORDER
        }

    def accept_page(self, page: CapturePageBinding) -> None:
        if type(page) is not CapturePageBinding:
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor yielded a non-authoritative page type"
            )
        # The capture-owned visitor must supply an exact raw-response binding;
        # C1 deliberately does not bless provider JSONL on its own.
        if page.raw_response_bytes is None:
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor page lacks exact raw-response authentication"
            )
        try:
            _PINNED_CAPTURE_PAGE_POST_INIT(page)
            query = _PINNED_VALIDATE_REDACTED_QUERY(
                page.redacted_query_bytes, page.source_role
            )
        except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor page changed during C1 ingestion"
            ) from exc
        role_ordinal = _ROLE_ORDER.index(page.source_role)
        if page.source_role in self.terminal_roles:
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor emitted a page after terminal"
            )
        if role_ordinal < self.expected_role_ordinal:
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor pages are not in canonical role order"
            )
        if role_ordinal > self.expected_role_ordinal:
            if role_ordinal != self.expected_role_ordinal + 1:
                raise PhysicalAcceptedRiskArchiveError(
                    "capture visitor skipped a source role"
                )
            if not self.copied_pages or not self.copied_pages[-1].terminal_page:
                raise PhysicalAcceptedRiskArchiveError(
                    "capture visitor changed roles before a terminal page"
                )
            self.expected_role_ordinal = role_ordinal
            self.expected_page_number = 1
        if page.page_number != self.expected_page_number:
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor page sequence is not contiguous"
            )
        if self.expected_page_number == 1 and page.request_cursor_sha256 is not None:
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor role begins with a cursor"
            )
        if self.expected_page_number > 1 and (
            not self.copied_pages
            or page.request_cursor_sha256
            != self.copied_pages[-1].next_cursor_sha256
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor cursor chain is discontinuous"
            )
        if (
            page.next_cursor_sha256 is not None
            and page.next_cursor_sha256
            in self.seen_cursor_hashes[page.source_role]
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor cursor chain repeats or cycles"
            )
        if page.raw_response_sha256 in self.seen_response_hashes[page.source_role]:
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor repeats a raw response page"
            )
        first = query["requested_first_event_date"]
        last = query["requested_last_event_date"]
        limit = query["limit"]
        if self.requested_first_event_date is None:
            self.requested_first_event_date = first
            self.requested_last_event_date = last
            self.page_limit = limit
        elif (
            first != self.requested_first_event_date
            or last != self.requested_last_event_date
            or limit != self.page_limit
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor pages do not share one requested range and limit"
            )
        page_rows = 0
        for row, _raw in _iter_provider_rows(page.provider_rows_bytes):
            page_rows += 1
            _insert_provider_id(self.connection, row, page.source_role)
            if page.source_role is MassiveSourceRole.ANALYST_RATINGS:
                try:
                    raw_action = row.get("rating_action")
                    if not _PINNED_RATING_ACTION_IS_MISSING(raw_action):
                        _PINNED_CANONICAL_RATING_ACTION(raw_action)
                except MassiveInputPairBridgeError as exc:
                    raise PhysicalAcceptedRiskArchiveError(
                        "rating_action is not a reviewed provider action"
                    ) from exc
        if page_rows != page.row_count:
            raise PhysicalAcceptedRiskArchiveError(
                "capture visitor row census changed"
            )
        filename = (
            f"{role_ordinal + 1:02d}-{page.source_role.value}-"
            f"page-{page.page_number:06d}.jsonl"
        )
        relative_path = f"{SOURCE_DIRECTORY}/{filename}"
        byte_count, digest = _write_private_at(
            self.source_fd,
            filename,
            (page.provider_rows_bytes,),
            maximum_bytes=_PINNED_MAX_CAPTURE_PAGE_BYTES,
        )
        if (
            byte_count != len(page.provider_rows_bytes)
            or digest != page.provider_rows_sha256
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "copied source page changed while persisted"
            )
        self.copied_pages.append(
            _CopiedPage(
                source_role=page.source_role,
                page_number=page.page_number,
                endpoint_identifier=page.endpoint_identifier,
                redacted_query_bytes=page.redacted_query_bytes,
                redacted_query_sha256=page.redacted_query_sha256,
                request_cursor_sha256=page.request_cursor_sha256,
                next_cursor_sha256=page.next_cursor_sha256,
                terminal_page=page.terminal_page,
                response_received_at=page.response_received_at,
                raw_response_sha256=page.raw_response_sha256,
                provider_rows_sha256=page.provider_rows_sha256,
                row_count=page.row_count,
                source_relative_path=relative_path,
                source_byte_count=byte_count,
                source_sha256=digest,
            )
        )
        self.observed_rows += page_rows
        self.role_rows[page.source_role] += page_rows
        self.maximum_source_page_byte_count = max(
            self.maximum_source_page_byte_count, byte_count
        )
        if page.next_cursor_sha256 is not None:
            self.seen_cursor_hashes[page.source_role].add(
                page.next_cursor_sha256
            )
        self.seen_response_hashes[page.source_role].add(
            page.raw_response_sha256
        )
        if page.terminal_page:
            self.terminal_roles.add(page.source_role)
        self.expected_page_number += 1
        if _spool_bytes(self.connection) > MAX_SQLITE_SPOOL_BYTES:
            raise PhysicalAcceptedRiskArchiveCapacityError(
                "accepted-risk duplicate-ID SQLite main file exceeded its byte bound"
            )


def _summary_exact(
    summary: object,
    *,
    source_artifact_path: Path,
    expected_transport: str,
    stage: _AcceptedRiskArchiveStage,
) -> _massive.SpooledMassiveCapture:
    if type(summary) is not _PINNED_SPOOLED_CAPTURE_TYPE:
        raise PhysicalAcceptedRiskArchiveError(
            "capture visitor did not return exact spooled authority metadata"
        )
    try:
        scalar_types_changed = (
            type(summary.artifact_path) is not _PATH_TYPE
            or type(summary.manifest_sha256) is not str
            or type(summary.capture_id) is not str
            or type(summary.capture_sha256) is not str
            or type(summary.capture_started_at) is not str
            or type(summary.capture_completed_at) is not str
            or type(summary.total_page_count) is not int
            or type(summary.total_row_count) is not int
            or type(summary.role_row_counts) is not tuple
            or type(summary.capture_transport) is not str
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not MassiveSourceRole
                or type(item[1]) is not int
                for item in summary.role_row_counts
            )
        )
    except AttributeError:
        scalar_types_changed = True
    if scalar_types_changed:
        raise PhysicalAcceptedRiskArchiveError(
            "capture visitor summary scalar types changed"
        )
    if (
        summary.artifact_path.absolute() != source_artifact_path.absolute()
        or summary.capture_transport != expected_transport
        or summary.total_page_count != len(stage.copied_pages)
        or summary.total_row_count != stage.observed_rows
        or summary.role_row_counts
        != tuple((role, stage.role_rows[role]) for role in _ROLE_ORDER)
        or stage.expected_role_ordinal != len(_ROLE_ORDER) - 1
        or not stage.copied_pages
        or not stage.copied_pages[-1].terminal_page
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "capture visitor summary does not match its exhaustive page traversal"
        )
    require_identifier(summary.capture_id, "capture_id")
    require_sha256(summary.capture_sha256, "capture_sha256")
    require_sha256(summary.manifest_sha256, "manifest_sha256")
    try:
        started = _PINNED_PARSE_UTC_TIMESTAMP(
            summary.capture_started_at, "capture_started_at"
        )
        completed = _PINNED_PARSE_UTC_TIMESTAMP(
            summary.capture_completed_at, "capture_completed_at"
        )
        receipts = tuple(
            _PINNED_PARSE_UTC_TIMESTAMP(
                item.response_received_at, "response_received_at"
            )
            for item in stage.copied_pages
        )
    except CanonicalEvidenceError as exc:
        raise PhysicalAcceptedRiskArchiveError(
            "capture visitor chronology is invalid"
        ) from exc
    if (
        started > completed
        or receipts != tuple(sorted(receipts))
        or any(item < started or item > completed for item in receipts)
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "capture visitor chronology does not contain every page receipt"
        )
    return summary


def _derive_semantic_shards(
    *,
    stage: _AcceptedRiskArchiveStage,
    derived_capture_id: str,
) -> tuple[
    tuple[AcceptedRiskShardDescriptor, ...],
    Counter[tuple[InputView, RowDisposition]],
    int,
    int,
    int,
    int,
]:
    if (
        stage.requested_first_event_date is None
        or stage.requested_last_event_date is None
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "capture traversal did not establish one requested date range"
        )
    context = _CaptureContext(
        capture_id=derived_capture_id,
        requested_first_event_date=stage.requested_first_event_date,
        requested_last_event_date=stage.requested_last_event_date,
    )
    dispositions: Counter[tuple[InputView, RowDisposition]] = Counter()
    total_rows = 0
    current_included = 0
    censored_included = 0
    disagreements = 0
    maximum_semantic = 0
    descriptors: list[AcceptedRiskShardDescriptor] = []
    for copied in stage.copied_pages:
        source_bytes = _read_private_regular_at(
            stage.source_fd,
            Path(copied.source_relative_path).name,
            maximum_bytes=_PINNED_MAX_CAPTURE_PAGE_BYTES,
            name="copied accepted-risk source page",
        )
        if (
            len(source_bytes) != copied.source_byte_count
            or sha256_bytes(source_bytes) != copied.source_sha256
            or copied.source_sha256 != copied.provider_rows_sha256
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "copied accepted-risk source page binding changed"
            )
        try:
            page = CapturePageBinding(
                schema=_PINNED_CAPTURE_PAGE_SCHEMA,
                source_role=copied.source_role,
                endpoint_identifier=copied.endpoint_identifier,
                redacted_query_bytes=copied.redacted_query_bytes,
                redacted_query_sha256=copied.redacted_query_sha256,
                page_number=copied.page_number,
                request_cursor_sha256=copied.request_cursor_sha256,
                next_cursor_sha256=copied.next_cursor_sha256,
                terminal_page=copied.terminal_page,
                response_received_at=copied.response_received_at,
                raw_response_sha256=copied.raw_response_sha256,
                provider_rows_bytes=source_bytes,
                provider_rows_sha256=copied.provider_rows_sha256,
                row_count=copied.row_count,
                raw_response_bytes=None,
            )
        except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
            raise PhysicalAcceptedRiskArchiveError(
                "copied accepted-risk source page failed rebinding"
            ) from exc
        filename = Path(copied.source_relative_path).name
        semantic_relative_path = f"{ROW_DIRECTORY}/{filename}"
        observed = 0

        def semantic_chunks() -> Iterator[bytes]:
            nonlocal observed, total_rows, current_included
            nonlocal censored_included, disagreements
            for offset, (raw, raw_bytes) in enumerate(
                _iter_provider_rows(source_bytes)
            ):
                try:
                    row = _PINNED_DERIVE_SOURCE_ROW(
                        capture=context,  # type: ignore[arg-type]
                        page=page,
                        row_offset=offset,
                        row=raw,
                        raw_row_bytes=raw_bytes,
                        duplicate_provider_event_id=(
                            _is_duplicate_guidance_provider_id(
                                stage.connection,
                                raw,
                                copied.source_role,
                            )
                        ),
                    )
                except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
                    raise PhysicalAcceptedRiskArchiveError(
                        "streamed accepted-risk row derivation failed"
                    ) from exc
                if type(row) is not AcceptedRiskSourceRow:
                    raise PhysicalAcceptedRiskArchiveError(
                        "streamed accepted-risk derivation returned the wrong row type"
                    )
                try:
                    _PINNED_SOURCE_ROW_POST_INIT(row)
                except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
                    raise PhysicalAcceptedRiskArchiveError(
                        "streamed accepted-risk row did not reauthenticate"
                    ) from exc
                _accumulate_row(stage.connection, dispositions, row)
                observed += 1
                total_rows += 1
                current_included += int(row.current_view.included)
                censored_included += int(row.censored_view.included)
                disagreements += int(
                    row.current_view.included != row.censored_view.included
                )
                yield canonical_json_bytes(_PINNED_SOURCE_ROW_TO_RECORD(row))

        semantic_byte_count, semantic_sha256 = _write_private_at(
            stage.rows_fd,
            filename,
            semantic_chunks(),
            maximum_bytes=MAX_DERIVED_SHARD_BYTES,
        )
        if observed != copied.row_count:
            raise PhysicalAcceptedRiskArchiveError(
                "streamed semantic shard row census changed"
            )
        if semantic_byte_count > MAX_DERIVED_SHARD_BYTES:
            raise PhysicalAcceptedRiskArchiveCapacityError(
                "accepted-risk semantic shard exceeded its disk bound"
            )
        maximum_semantic = max(maximum_semantic, semantic_byte_count)
        descriptors.append(
            AcceptedRiskShardDescriptor(
                source_role=copied.source_role,
                page_number=copied.page_number,
                source_relative_path=copied.source_relative_path,
                source_byte_count=copied.source_byte_count,
                source_sha256=copied.source_sha256,
                semantic_relative_path=semantic_relative_path,
                semantic_byte_count=semantic_byte_count,
                semantic_sha256=semantic_sha256,
                row_count=copied.row_count,
                endpoint_identifier=copied.endpoint_identifier,
                redacted_query_sha256=copied.redacted_query_sha256,
                request_cursor_sha256=copied.request_cursor_sha256,
                next_cursor_sha256=copied.next_cursor_sha256,
                terminal_page=copied.terminal_page,
                response_received_at=copied.response_received_at,
                raw_response_sha256=copied.raw_response_sha256,
            )
        )
        stage.connection.commit()
        if _spool_bytes(stage.connection) > MAX_SQLITE_SPOOL_BYTES:
            raise PhysicalAcceptedRiskArchiveCapacityError(
                "accepted-risk report SQLite main file exceeded its byte bound"
            )
        del page, source_bytes
    return (
        tuple(descriptors),
        dispositions,
        total_rows,
        current_included,
        censored_included,
        disagreements,
    )


def _pair_binding_from_stream(chunks: Iterable[bytes], pair_id: str | None = None):
    content = hashlib.sha256()
    artifact = hashlib.sha256()
    artifact.update(PAIR_ARTIFACT_DOMAIN)
    count = 0
    for chunk in chunks:
        content.update(chunk)
        artifact.update(chunk)
        count += len(chunk)
    digest = content.hexdigest()
    expected_id = f"arv2-accepted-risk-pair-{digest[:24]}"
    if pair_id is not None and pair_id != expected_id:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk pair ID does not match streamed content"
        )
    return expected_id, ArtifactBinding(
        artifact_id=expected_id,
        content_sha256=digest,
        artifact_sha256=artifact.hexdigest(),
        byte_count=count,
    )


def _build_with_capture_visitor(
    *,
    source_artifact_path: Path,
    output_root: Path,
    expected_transport: str,
    visitor: Callable[..., object],
) -> PhysicalAcceptedRiskArchive:
    _require_dependency_bindings()
    source = Path(source_artifact_path).absolute()
    (
        root,
        repository_path,
        root_name,
        repository_fd,
        root_fd,
    ) = _prepare_output_root(Path(output_root).absolute())
    stage_name, stage_fd, source_fd, rows_fd = _make_stage_at(root_fd)
    stage = root / stage_name
    spool_name = ".c1-index.sqlite3"
    connection: sqlite3.Connection | None = None
    published = False
    final_visible = False
    preserve_stage = False
    registered_identity: int | None = None
    try:
        _write_private_at(stage_fd, spool_name, (b"",), maximum_bytes=0)
        spool_before = os.stat(
            spool_name, dir_fd=stage_fd, follow_symlinks=False
        )
        _require_pinned_child_identity(
            root_fd, stage_name, stage_fd, "accepted-risk staging directory"
        )
        _require_reopened_directory_identity(
            stage,
            stage_fd,
            name="accepted-risk staging directory",
            private_final=True,
        )
        connection = _open_spool(stage / spool_name)
        _require_pinned_child_identity(
            root_fd, stage_name, stage_fd, "accepted-risk staging directory"
        )
        _require_reopened_directory_identity(
            stage,
            stage_fd,
            name="accepted-risk staging directory",
            private_final=True,
        )
        spool_metadata = os.stat(
            spool_name, dir_fd=stage_fd, follow_symlinks=False
        )
        if (
            not stat.S_ISREG(spool_metadata.st_mode)
            or stat.S_IMODE(spool_metadata.st_mode) != 0o600
            or spool_metadata.st_nlink != 1
            or (hasattr(os, "getuid") and spool_metadata.st_uid != os.getuid())
            or _regular_file_identity(spool_metadata)[:2]
            != _regular_file_identity(spool_before)[:2]
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk report spool changed during open"
            )
        state = _AcceptedRiskArchiveStage(
            stage,
            connection,
            stage_fd=stage_fd,
            source_fd=source_fd,
            rows_fd=rows_fd,
        )
        try:
            summary_raw = visitor(
                artifact_path=source,
                expected_transport=expected_transport,
                visit_page=state.accept_page,
            )
        except PhysicalAcceptedRiskArchiveError:
            raise
        except (AcceptedRiskInputError, CanonicalEvidenceError, ValueError) as exc:
            raise PhysicalAcceptedRiskArchiveError(
                "Massive capture failed exhaustive streaming authentication"
            ) from exc
        summary = _summary_exact(
            summary_raw,
            source_artifact_path=source,
            expected_transport=expected_transport,
            stage=state,
        )
        if (
            state.requested_first_event_date is None
            or state.requested_last_event_date is None
            or state.page_limit is None
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "capture traversal did not establish one query contract"
            )
        physical_capture_id, physical_capture_sha256 = (
            _authenticate_physical_capture_identity(
                pages=tuple(state.copied_pages),
                capture_started_at=summary.capture_started_at,
                capture_completed_at=summary.capture_completed_at,
                requested_first_event_date=state.requested_first_event_date,
                requested_last_event_date=state.requested_last_event_date,
                expected_capture_id=summary.capture_id,
                expected_capture_sha256=summary.capture_sha256,
            )
        )
        derived_capture_id, derived_capture_sha256 = _capture_identity(
            _capture_record(
                pages=tuple(state.copied_pages),
                capture_started_at=summary.capture_started_at,
                capture_completed_at=summary.capture_completed_at,
                requested_first_event_date=state.requested_first_event_date,
                requested_last_event_date=state.requested_last_event_date,
                raw_response_extraction_verified=False,
                contract_sha256=_PINNED_INPUT_PAIR_CONTRACT_SHA256,
            )
        )
        (
            descriptors,
            dispositions,
            total_rows,
            current_included,
            censored_included,
            disagreements,
        ) = _derive_semantic_shards(
            stage=state, derived_capture_id=derived_capture_id
        )
        if total_rows < 1:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk input pair cannot be empty"
            )
        if total_rows != summary.total_row_count:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk derivation did not exhaust the source capture"
            )
        report_parts = _report_record_parts(
            connection,
            dispositions,
            total_row_count=total_rows,
            current_included_count=current_included,
            censored_included_count=censored_included,
            disagreement_count=disagreements,
        )
        report_byte_count, report_sha256 = _write_private_at(
            stage_fd,
            REPORT_FILENAME,
            _iter_canonical_object(report_parts, terminate=True),
            maximum_bytes=MAX_REPORT_BYTES,
        )
        if report_byte_count > MAX_REPORT_BYTES:
            raise PhysicalAcceptedRiskArchiveCapacityError(
                "accepted-risk report exceeded its disk bound"
            )
        connection.close()
        connection = None
        os.unlink(spool_name, dir_fd=stage_fd)
        pair_fields = _pair_fields(
            capture_id=derived_capture_id,
            capture_sha256=derived_capture_sha256,
            row_items=lambda: (
                fragment
                for descriptor in descriptors
                for fragment in _iter_verified_jsonl_fragments_at(
                    rows_fd,
                    Path(descriptor.semantic_relative_path).name,
                    maximum_bytes=MAX_DERIVED_SHARD_BYTES,
                    maximum_line_bytes=MAX_SEMANTIC_ROW_BYTES,
                    expected_byte_count=descriptor.semantic_byte_count,
                    expected_sha256=descriptor.semantic_sha256,
                    expected_row_count=descriptor.row_count,
                    name="accepted-risk semantic shard",
                )
            ),
            report_items=lambda: _iter_verified_file_fragment_at(
                stage_fd,
                REPORT_FILENAME,
                maximum_bytes=MAX_REPORT_BYTES,
                expected_byte_count=report_byte_count,
                expected_sha256=report_sha256,
                name="accepted-risk report",
            ),
        )
        pair_id, pair_artifact = _pair_binding_from_stream(
            _iter_canonical_object(pair_fields, terminate=True)
        )
        source_page_root_sha256 = _source_page_root(tuple(state.copied_pages))
        seed = _archive_seed(
            source_artifact_id=summary.artifact_path.name,
            source_manifest_sha256=summary.manifest_sha256,
            capture_transport=summary.capture_transport,
            physical_capture_id=physical_capture_id,
            physical_capture_sha256=physical_capture_sha256,
            capture_started_at=summary.capture_started_at,
            capture_completed_at=summary.capture_completed_at,
            capture_id=derived_capture_id,
            capture_sha256=derived_capture_sha256,
            requested_first_event_date=state.requested_first_event_date,
            requested_last_event_date=state.requested_last_event_date,
            page_limit=state.page_limit,
            source_page_root_sha256=source_page_root_sha256,
            source_page_count=summary.total_page_count,
            source_row_count=summary.total_row_count,
            role_row_counts=summary.role_row_counts,
            pair_artifact=pair_artifact,
            report_sha256=report_sha256,
            report_byte_count=report_byte_count,
            current_included_count=current_included,
            censored_included_count=censored_included,
            disagreement_count=disagreements,
            shards=descriptors,
            maximum_source_page_byte_count=state.maximum_source_page_byte_count,
            maximum_semantic_page_byte_count=max(
                (item.semantic_byte_count for item in descriptors), default=0
            ),
        )
        archive_sha256 = sha256_bytes(canonical_json_bytes(seed))
        archive_id = f"arv2-physical-accepted-risk-{archive_sha256[:24]}"
        manifest = {
            **seed,
            "archive_id": archive_id,
            "archive_sha256": archive_sha256,
        }
        manifest_bytes = canonical_json_bytes(manifest)
        if len(manifest_bytes) > MAX_ARCHIVE_MANIFEST_BYTES:
            raise PhysicalAcceptedRiskArchiveCapacityError(
                "accepted-risk archive manifest exceeded its byte bound"
            )
        _write_private_at(
            stage_fd,
            ARCHIVE_MANIFEST,
            (manifest_bytes,),
            maximum_bytes=MAX_ARCHIVE_MANIFEST_BYTES,
        )
        _write_private_at(
            stage_fd,
            ARCHIVE_MANIFEST_DIGEST,
            ((sha256_bytes(manifest_bytes) + "\n").encode("ascii"),),
            maximum_bytes=65,
        )
        final = root / archive_id
        _require_dependency_bindings()
        _publish_stage_at(
            repository_path=repository_path,
            repository_fd=repository_fd,
            root_path=root,
            root_name=root_name,
            root_fd=root_fd,
            stage_fd=stage_fd,
            source_fd=source_fd,
            rows_fd=rows_fd,
            stage_name=stage_name,
            final_name=archive_id,
        )
        final_visible = True
        value = object.__new__(PhysicalAcceptedRiskArchive)
        values: dict[str, object] = {
            "schema": ARCHIVE_SCHEMA,
            "archive_id": archive_id,
            "archive_sha256": archive_sha256,
            "archive_path": final,
            "source_artifact_path": source,
            "source_artifact_id": summary.artifact_path.name,
            "source_manifest_sha256": summary.manifest_sha256,
            "capture_transport": summary.capture_transport,
            "physical_capture_id": physical_capture_id,
            "physical_capture_sha256": physical_capture_sha256,
            "capture_started_at": summary.capture_started_at,
            "capture_completed_at": summary.capture_completed_at,
            "capture_id": derived_capture_id,
            "capture_sha256": derived_capture_sha256,
            "requested_first_event_date": state.requested_first_event_date,
            "requested_last_event_date": state.requested_last_event_date,
            "page_limit": state.page_limit,
            "source_page_root_sha256": source_page_root_sha256,
            "source_page_count": summary.total_page_count,
            "source_row_count": summary.total_row_count,
            "role_row_counts": summary.role_row_counts,
            "pair_id": pair_id,
            "pair_sha256": pair_artifact.content_sha256,
            "pair_artifact": pair_artifact,
            "report_sha256": report_sha256,
            "report_byte_count": report_byte_count,
            "current_included_count": current_included,
            "censored_included_count": censored_included,
            "disagreement_count": disagreements,
            "shards": descriptors,
            "maximum_source_page_byte_count": state.maximum_source_page_byte_count,
            "maximum_semantic_page_byte_count": max(
                (item.semantic_byte_count for item in descriptors), default=0
            ),
            "full_capture_materialized": False,
            "views_share_one_capture": True,
            "pristine_point_in_time": False,
            "provider_access": False,
            "credential_access": False,
            "quantconnect_access": False,
            "outcome_access": False,
            "result_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        }
        if set(values) != {field.name for field in dataclasses.fields(value)}:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk archive field inventory changed"
            )
        for name, item in values.items():
            object.__setattr__(value, name, item)
        identity = id(value)
        registered_identity = identity
        reference = weakref.ref(value, lambda ref, key=identity: _forget(key, ref))
        with _AUTHORITY_LOCK:
            _AUTHORITIES[identity] = (
                reference,
                _archive_fingerprint(value),
                _archive_topology(value),
                (
                    _directory_identity(os.fstat(stage_fd)),
                    _directory_identity(os.fstat(source_fd)),
                    _directory_identity(os.fstat(rows_fd)),
                ),
                os.getpid(),
            )
        authenticated = require_physical_accepted_risk_archive(value)
        _require_dependency_bindings()
        _require_pinned_child_identity(
            root_fd,
            archive_id,
            stage_fd,
            "published accepted-risk archive",
        )
        _require_reopened_directory_identity(
            repository_path,
            repository_fd,
            name="accepted-risk archive repository",
            private_final=False,
        )
        _require_reopened_directory_identity(
            root,
            root_fd,
            name="accepted-risk archive root",
            private_final=True,
        )
        published = True
        return authenticated
    except _ArchivePublicationError as exc:
        preserve_stage = exc.preserve_stage
        raise
    except BaseException:
        if registered_identity is not None:
            with _AUTHORITY_LOCK:
                _AUTHORITIES.pop(registered_identity, None)
        if final_visible:
            try:
                _rollback_published_at(
                    root_path=root,
                    root_fd=root_fd,
                    stage_fd=stage_fd,
                    stage_name=stage_name,
                    final_name=archive_id,
                )
                final_visible = False
            except _ArchivePublicationError as exc:
                preserve_stage = exc.preserve_stage
                raise
        raise
    finally:
        if connection is not None:
            connection.close()
        try:
            if not published and not preserve_stage and not final_visible:
                _cleanup_stage_at(
                    repository_path=repository_path,
                    repository_fd=repository_fd,
                    root_path=root,
                    root_name=root_name,
                    root_fd=root_fd,
                    stage_name=stage_name,
                    stage_fd=stage_fd,
                    source_fd=source_fd,
                    rows_fd=rows_fd,
                )
        finally:
            for descriptor in (rows_fd, source_fd, stage_fd, root_fd, repository_fd):
                try:
                    os.close(descriptor)
                except OSError:
                    pass


_PATH_TYPE = type(Path("."))
_DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_BINARY", 0)
)


def _directory_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _regular_file_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _archive_leaf_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, int]:
    """Return every cross-read metadata field retained for archive leaves."""

    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        metadata.st_nlink,
    )


def _observe_archive_leaf(
    parent_fd: int,
    filename: str,
    *,
    maximum_bytes: int,
    name: str,
) -> tuple[int, int, int, int, int, int, int, int]:
    """Capture one stable descriptor/path identity."""

    descriptor, _metadata = _open_private_regular_at(
        parent_fd,
        filename,
        maximum_bytes=maximum_bytes,
        name=name,
    )
    try:
        for _attempt in range(4):
            before = os.fstat(descriptor)
            after = os.fstat(descriptor)
            named = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
            identities = {
                _archive_leaf_identity(before),
                _archive_leaf_identity(after),
                _archive_leaf_identity(named),
            }
            if len(identities) == 1:
                return identities.pop()
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive named leaf identity changed"
        ) from exc
    finally:
        os.close(descriptor)
    raise PhysicalAcceptedRiskArchiveError(
        "accepted-risk archive named leaf identity changed"
    )


def _without_archive_leaf_ctime(
    identity: tuple[int, int, int, int, int, int, int, int],
) -> tuple[int, int, int, int, int, int, int]:
    return (*identity[:4], *identity[5:])


def _require_safe_child_name(name: str, label: str) -> None:
    if (
        type(name) is not str
        or not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
    ):
        raise PhysicalAcceptedRiskArchiveError(
            f"{label} has an unsafe directory entry name"
        )


def _require_dirfd_support() -> None:
    required = (os.open, os.mkdir, os.rename, os.stat, os.unlink, os.rmdir)
    if (
        os.name == "nt"
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or any(call not in os.supports_dir_fd for call in required)
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "physical accepted-risk archive requires POSIX dirfd support"
        )


def _open_directory_components(
    path: Path, *, name: str, private_final: bool
) -> tuple[Path, int]:
    """Open an absolute directory without trusting any lexical parent."""

    _require_dirfd_support()
    if type(path) is not _PATH_TYPE:
        raise PhysicalAcceptedRiskArchiveError(f"{name} must be an exact Path")
    absolute = Path(os.path.abspath(path))
    if not absolute.is_absolute() or not absolute.parts:
        raise PhysicalAcceptedRiskArchiveError(f"{name} must be absolute")
    try:
        descriptor = os.open(absolute.anchor, _DIRECTORY_OPEN_FLAGS)
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} root directory is unavailable"
        ) from exc
    try:
        for component in absolute.parts[1:]:
            _require_safe_child_name(component, name)
            child = os.open(
                component, _DIRECTORY_OPEN_FLAGS, dir_fd=descriptor
            )
            opened = os.fstat(child)
            named = os.stat(
                component, dir_fd=descriptor, follow_symlinks=False
            )
            if (
                not stat.S_ISDIR(opened.st_mode)
                or _directory_identity(opened) != _directory_identity(named)
            ):
                os.close(child)
                raise PhysicalAcceptedRiskArchiveError(
                    f"{name} component identity changed"
                )
            os.close(descriptor)
            descriptor = child
        if private_final:
            _require_private_directory_metadata(os.fstat(descriptor), name)
        return absolute, descriptor
    except PhysicalAcceptedRiskArchiveError:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    except OSError as exc:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} must not traverse a link and must be a directory"
        ) from exc


def _require_pinned_child_identity(
    parent_fd: int, child: str, child_fd: int, name: str
) -> None:
    _require_safe_child_name(child, name)
    try:
        opened = os.fstat(child_fd)
        named = os.stat(child, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} identity is unavailable"
        ) from exc
    _require_private_directory_metadata(opened, name)
    _require_private_directory_metadata(named, name)
    if _directory_identity(opened) != _directory_identity(named):
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} identity changed"
        )


def _require_reopened_directory_identity(
    path: Path,
    descriptor: int,
    *,
    name: str,
    private_final: bool,
) -> None:
    reopened: int | None = None
    try:
        _absolute, reopened = _open_directory_components(
            path, name=f"{name} final path", private_final=private_final
        )
        if _directory_identity(os.fstat(reopened)) != _directory_identity(
            os.fstat(descriptor)
        ):
            raise PhysicalAcceptedRiskArchiveError(
                f"{name} path identity changed"
            )
    finally:
        if reopened is not None:
            os.close(reopened)


def _prepare_output_root(
    path: Path,
) -> tuple[Path, Path, str, int, int]:
    """Return pinned parent/output descriptors, creating only the final root."""

    absolute = Path(os.path.abspath(path))
    root_name = absolute.name
    _require_safe_child_name(root_name, "accepted-risk archive root")
    parent_path, parent_fd = _open_directory_components(
        absolute.parent,
        name="accepted-risk archive repository",
        private_final=False,
    )
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(
                root_name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd
            )
        except FileNotFoundError:
            os.mkdir(root_name, 0o700, dir_fd=parent_fd)
            descriptor = os.open(
                root_name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd
            )
            os.fchmod(descriptor, 0o700)
            os.fsync(parent_fd)
        _require_pinned_child_identity(
            parent_fd,
            root_name,
            descriptor,
            "accepted-risk archive root",
        )
        return absolute, parent_path, root_name, parent_fd, descriptor
    except BaseException:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        os.close(parent_fd)
        raise


def _make_stage_at(
    root_fd: int,
) -> tuple[str, int, int, int]:
    """Create and pin the staging tree without resolving the root again."""

    for _attempt in range(64):
        stage_name = f".arv2-c1-{secrets.token_hex(16)}"
        try:
            os.mkdir(stage_name, 0o700, dir_fd=root_fd)
        except FileExistsError:
            continue
        except OSError as exc:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk staging directory could not be created"
            ) from exc
        break
    else:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk staging name space is exhausted"
        )
    stage_fd: int | None = None
    source_fd: int | None = None
    rows_fd: int | None = None
    try:
        stage_fd = _open_private_child_directory(root_fd, stage_name)
        os.mkdir(SOURCE_DIRECTORY, 0o700, dir_fd=stage_fd)
        os.mkdir(ROW_DIRECTORY, 0o700, dir_fd=stage_fd)
        source_fd = _open_private_child_directory(stage_fd, SOURCE_DIRECTORY)
        rows_fd = _open_private_child_directory(stage_fd, ROW_DIRECTORY)
        _require_pinned_child_identity(
            root_fd, stage_name, stage_fd, "accepted-risk staging directory"
        )
        _require_pinned_child_identity(
            stage_fd,
            SOURCE_DIRECTORY,
            source_fd,
            "accepted-risk source directory",
        )
        _require_pinned_child_identity(
            stage_fd,
            ROW_DIRECTORY,
            rows_fd,
            "accepted-risk row directory",
        )
        return stage_name, stage_fd, source_fd, rows_fd
    except BaseException:
        for descriptor in (rows_fd, source_fd, stage_fd):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        raise


def _entry_exists_at(parent_fd: int, name: str) -> bool:
    _require_safe_child_name(name, "accepted-risk archive entry")
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive entry could not be inspected"
        ) from exc
    return True


def _fsync_directory(
    descriptor: int,
    name: str,
    *,
    fsync: Callable[[int], None] = os.fsync,
) -> None:
    try:
        fsync(descriptor)
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} directory sync failed"
        ) from exc


def _rollback_published_at(
    *,
    root_path: Path,
    root_fd: int,
    stage_fd: int,
    stage_name: str,
    final_name: str,
    fsync: Callable[[int], None] = os.fsync,
    rename: Callable[..., None] = os.rename,
) -> None:
    """Move a visible final back to its hidden stage and sync that rollback."""

    try:
        _require_pinned_child_identity(
            root_fd, final_name, stage_fd, "published accepted-risk archive"
        )
        rename(
            final_name,
            stage_name,
            src_dir_fd=root_fd,
            dst_dir_fd=root_fd,
        )
    except (OSError, PhysicalAcceptedRiskArchiveError) as exc:
        raise _ArchivePublicationError(
            "accepted-risk archive publication state is ambiguous; "
            "published entry preserved",
            preserve_stage=True,
        ) from exc
    try:
        _require_pinned_child_identity(
            root_fd,
            stage_name,
            stage_fd,
            "accepted-risk staging directory",
        )
        fsync(root_fd)
        _require_reopened_directory_identity(
            root_path,
            root_fd,
            name="accepted-risk archive root",
            private_final=True,
        )
    except (OSError, PhysicalAcceptedRiskArchiveError) as exc:
        raise _ArchivePublicationError(
            "accepted-risk archive publication rollback is ambiguous; "
            "hidden staging preserved",
            preserve_stage=True,
        ) from exc


def _publish_stage_at(
    *,
    repository_path: Path,
    repository_fd: int,
    root_path: Path,
    root_name: str,
    root_fd: int,
    stage_fd: int,
    source_fd: int,
    rows_fd: int,
    stage_name: str,
    final_name: str,
    fsync: Callable[[int], None] = os.fsync,
    rename: Callable[..., None] = os.rename,
) -> None:
    """Sync every directory, publish once, and durably bind the rename."""

    _require_pinned_child_identity(
        repository_fd, root_name, root_fd, "accepted-risk archive root"
    )
    _require_reopened_directory_identity(
        repository_path,
        repository_fd,
        name="accepted-risk archive repository",
        private_final=False,
    )
    _require_reopened_directory_identity(
        root_path,
        root_fd,
        name="accepted-risk archive root",
        private_final=True,
    )
    _require_pinned_child_identity(
        root_fd, stage_name, stage_fd, "accepted-risk staging directory"
    )
    _require_pinned_child_identity(
        stage_fd,
        SOURCE_DIRECTORY,
        source_fd,
        "accepted-risk source directory",
    )
    _require_pinned_child_identity(
        stage_fd,
        ROW_DIRECTORY,
        rows_fd,
        "accepted-risk row directory",
    )
    if _entry_exists_at(root_fd, final_name):
        raise PhysicalAcceptedRiskArchiveError(
            "content-addressed accepted-risk archive already exists"
        )
    _fsync_directory(source_fd, "accepted-risk source", fsync=fsync)
    _fsync_directory(rows_fd, "accepted-risk rows", fsync=fsync)
    _fsync_directory(stage_fd, "accepted-risk staging", fsync=fsync)
    _require_pinned_child_identity(
        root_fd, stage_name, stage_fd, "accepted-risk staging directory"
    )
    renamed = False
    try:
        rename(
            stage_name,
            final_name,
            src_dir_fd=root_fd,
            dst_dir_fd=root_fd,
        )
        renamed = True
        _require_pinned_child_identity(
            root_fd, final_name, stage_fd, "published accepted-risk archive"
        )
        _require_reopened_directory_identity(
            root_path,
            root_fd,
            name="accepted-risk archive root",
            private_final=True,
        )
        fsync(root_fd)
    except (OSError, PhysicalAcceptedRiskArchiveError) as exc:
        if not renamed:
            raise _ArchivePublicationError(
                "accepted-risk archive publication rename failed",
                preserve_stage=False,
            ) from exc
        try:
            _rollback_published_at(
                root_path=root_path,
                root_fd=root_fd,
                stage_fd=stage_fd,
                stage_name=stage_name,
                final_name=final_name,
                fsync=fsync,
                rename=rename,
            )
        except _ArchivePublicationError:
            raise
        raise _ArchivePublicationError(
            "accepted-risk archive publication could not be synchronized",
            preserve_stage=False,
        ) from exc


def _unlink_private_files_at(descriptor: int, name: str) -> None:
    try:
        entries = tuple(os.listdir(descriptor))
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} cleanup inventory is unavailable"
        ) from exc
    for entry in entries:
        _require_safe_child_name(entry, name)
        leaf_fd: int | None = None
        try:
            metadata = os.stat(
                entry, dir_fd=descriptor, follow_symlinks=False
            )
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
                or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
            ):
                raise PhysicalAcceptedRiskArchiveError(
                    f"{name} cleanup encountered an unexpected entry"
                )
            leaf_fd = os.open(
                entry,
                os.O_RDONLY
                | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_BINARY", 0),
                dir_fd=descriptor,
            )
            held = os.fstat(leaf_fd)
            named = os.stat(
                entry, dir_fd=descriptor, follow_symlinks=False
            )
            if (
                _regular_file_identity(metadata)
                != _regular_file_identity(held)
                or _regular_file_identity(held)
                != _regular_file_identity(named)
            ):
                raise PhysicalAcceptedRiskArchiveError(
                    f"{name} cleanup is ambiguous"
                )
            os.unlink(entry, dir_fd=descriptor)
        except PhysicalAcceptedRiskArchiveError:
            raise
        except OSError as exc:
            raise PhysicalAcceptedRiskArchiveError(
                f"{name} cleanup is ambiguous"
            ) from exc
        finally:
            if leaf_fd is not None:
                try:
                    os.close(leaf_fd)
                except OSError:
                    pass
    _fsync_directory(descriptor, name)


def _cleanup_stage_at(
    *,
    repository_path: Path,
    repository_fd: int,
    root_path: Path,
    root_name: str,
    root_fd: int,
    stage_name: str,
    stage_fd: int,
    source_fd: int,
    rows_fd: int,
) -> None:
    """Remove only the held hidden tree; any identity doubt preserves it."""

    try:
        _require_pinned_child_identity(
            repository_fd, root_name, root_fd, "accepted-risk archive root"
        )
        _require_reopened_directory_identity(
            repository_path,
            repository_fd,
            name="accepted-risk archive repository",
            private_final=False,
        )
        _require_reopened_directory_identity(
            root_path,
            root_fd,
            name="accepted-risk archive root",
            private_final=True,
        )
        _require_pinned_child_identity(
            root_fd, stage_name, stage_fd, "accepted-risk staging directory"
        )
        _require_pinned_child_identity(
            stage_fd,
            SOURCE_DIRECTORY,
            source_fd,
            "accepted-risk source directory",
        )
        _require_pinned_child_identity(
            stage_fd,
            ROW_DIRECTORY,
            rows_fd,
            "accepted-risk row directory",
        )
        _unlink_private_files_at(source_fd, "accepted-risk source directory")
        _unlink_private_files_at(rows_fd, "accepted-risk row directory")
        os.rmdir(SOURCE_DIRECTORY, dir_fd=stage_fd)
        os.rmdir(ROW_DIRECTORY, dir_fd=stage_fd)
        _unlink_private_files_at(stage_fd, "accepted-risk staging directory")
        _require_pinned_child_identity(
            root_fd, stage_name, stage_fd, "accepted-risk staging directory"
        )
        os.rmdir(stage_name, dir_fd=root_fd)
        _fsync_directory(root_fd, "accepted-risk archive root")
    except PhysicalAcceptedRiskArchiveError:
        raise
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk staging cleanup is ambiguous; residue preserved"
        ) from exc


def _require_private_directory_metadata(
    metadata: os.stat_result, name: str
) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} is not an owner-private directory"
        )


def _open_private_directory(path: Path, name: str) -> int:
    _absolute, descriptor = _open_directory_components(
        path, name=name, private_final=True
    )
    return descriptor


def _open_private_child_directory(parent_fd: int, name: str) -> int:
    try:
        descriptor = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
        metadata = os.fstat(descriptor)
        _require_private_directory_metadata(metadata, name)
        entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except PhysicalAcceptedRiskArchiveError:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
        raise
    except OSError as exc:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} directory is unavailable"
        ) from exc
    if (metadata.st_dev, metadata.st_ino) != (entry.st_dev, entry.st_ino):
        os.close(descriptor)
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} directory identity changed while opened"
        )
    return descriptor


def _open_private_regular_at(
    parent_fd: int,
    filename: str,
    *,
    maximum_bytes: int,
    name: str,
) -> tuple[int, os.stat_result]:
    if (
        type(filename) is not str
        or not filename
        or "/" in filename
        or filename in {".", ".."}
        or type(maximum_bytes) is not int
        or maximum_bytes < 0
    ):
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} has an invalid bounded child name"
        )
    try:
        descriptor = os.open(filename, _FILE_OPEN_FLAGS, dir_fd=parent_fd)
        metadata = os.fstat(descriptor)
        entry = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
        raise PhysicalAcceptedRiskArchiveError(f"{name} is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or metadata.st_size < 0
        or metadata.st_size > maximum_bytes
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        or (metadata.st_dev, metadata.st_ino) != (entry.st_dev, entry.st_ino)
    ):
        os.close(descriptor)
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} is not a bounded owner-held private regular file"
        )
    return descriptor, metadata


def _read_private_regular_at(
    parent_fd: int,
    filename: str,
    *,
    maximum_bytes: int,
    name: str,
) -> bytes:
    descriptor, before = _open_private_regular_at(
        parent_fd, filename, maximum_bytes=maximum_bytes, name=name
    )
    chunks: list[bytes] = []
    count = 0
    try:
        while True:
            chunk = os.read(descriptor, IO_CHUNK_BYTES)
            if not chunk:
                break
            count += len(chunk)
            if count > maximum_bytes:
                raise PhysicalAcceptedRiskArchiveCapacityError(
                    f"{name} exceeded its read bound"
                )
            chunks.append(chunk)
        after = os.fstat(descriptor)
        named = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(f"{name} could not be read") from exc
    finally:
        os.close(descriptor)
    if (
        count != before.st_size
        or len(
            {
                _regular_file_identity(before),
                _regular_file_identity(after),
                _regular_file_identity(named),
            }
        )
        != 1
        or not stat.S_ISREG(named.st_mode)
        or stat.S_IMODE(named.st_mode) != 0o600
        or named.st_nlink != 1
    ):
        raise PhysicalAcceptedRiskArchiveError(f"{name} changed while read")
    return b"".join(chunks)


def _hash_private_regular_at(
    parent_fd: int,
    filename: str,
    *,
    maximum_bytes: int,
    expected_byte_count: int,
    expected_sha256: str,
    name: str,
) -> None:
    descriptor, before = _open_private_regular_at(
        parent_fd, filename, maximum_bytes=maximum_bytes, name=name
    )
    digest = hashlib.sha256()
    count = 0
    try:
        while True:
            chunk = os.read(descriptor, IO_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            count += len(chunk)
            if count > maximum_bytes:
                raise PhysicalAcceptedRiskArchiveCapacityError(
                    f"{name} exceeded its hash bound"
                )
        after = os.fstat(descriptor)
        named = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(f"{name} could not be hashed") from exc
    finally:
        os.close(descriptor)
    if (
        count != before.st_size
        or count != expected_byte_count
        or digest.hexdigest() != expected_sha256
        or len(
            {
                _regular_file_identity(before),
                _regular_file_identity(after),
                _regular_file_identity(named),
            }
        )
        != 1
        or not stat.S_ISREG(named.st_mode)
        or stat.S_IMODE(named.st_mode) != 0o600
        or named.st_nlink != 1
    ):
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} byte count, hash, or identity changed"
        )


def _iter_verified_jsonl_fragments_at(
    parent_fd: int,
    filename: str,
    *,
    maximum_bytes: int,
    maximum_line_bytes: int,
    expected_byte_count: int,
    expected_sha256: str,
    expected_row_count: int,
    name: str,
) -> Iterator[bytes]:
    descriptor, before = _open_private_regular_at(
        parent_fd, filename, maximum_bytes=maximum_bytes, name=name
    )
    digest = hashlib.sha256()
    count = 0
    rows = 0
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            while True:
                line = handle.readline(maximum_line_bytes + 1)
                if not line:
                    break
                count += len(line)
                digest.update(line)
                rows += 1
                if (
                    len(line) > maximum_line_bytes
                    or not line.endswith(b"\n")
                    or line == b"\n"
                    or count > maximum_bytes
                ):
                    raise PhysicalAcceptedRiskArchiveCapacityError(
                        f"{name} contains an oversized, blank, or unterminated row"
                    )
                yield line[:-1]
            after = os.fstat(handle.fileno())
            named = os.stat(
                filename, dir_fd=parent_fd, follow_symlinks=False
            )
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(f"{name} could not be read") from exc
    if count != before.st_size:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} streamed byte count changed from opened size"
        )
    if count != expected_byte_count:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} streamed byte count does not match expected byte count"
        )
    if rows != expected_row_count:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} row count does not match expected row count"
        )
    if digest.hexdigest() != expected_sha256:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} content SHA-256 does not match expected SHA-256"
        )
    if not stat.S_ISREG(after.st_mode):
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} exhausted descriptor is not a regular file"
        )
    if not stat.S_ISREG(named.st_mode):
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} named entry is not a regular file"
        )
    if stat.S_IMODE(after.st_mode) != 0o600:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} exhausted descriptor mode is not 0600"
        )
    if stat.S_IMODE(named.st_mode) != 0o600:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} named entry mode is not 0600"
        )
    if after.st_nlink != 1:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} exhausted descriptor link count is not one"
        )
    if named.st_nlink != 1:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} named entry link count is not one"
        )
    if hasattr(os, "getuid") and named.st_uid != os.getuid():
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} named entry is not owner-held"
        )
    opened_identity = _regular_file_identity(before)
    after_identity = _regular_file_identity(after)
    named_identity = _regular_file_identity(named)
    opened_ctime_only = (
        sys.platform == "darwin"
        and opened_identity[:4] == after_identity[:4]
        and opened_identity[4] != after_identity[4]
    )
    if opened_identity != after_identity and not opened_ctime_only:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} opened descriptor identity changed during iteration"
        )
    named_ctime_only = (
        sys.platform == "darwin"
        and after_identity[:4] == named_identity[:4]
        and after_identity[4] != named_identity[4]
    )
    if after_identity != named_identity and not named_ctime_only:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} named entry identity changed during iteration"
        )


def _iter_verified_file_fragment_at(
    parent_fd: int,
    filename: str,
    *,
    maximum_bytes: int,
    expected_byte_count: int,
    expected_sha256: str,
    name: str,
) -> Iterator[bytes]:
    descriptor, before = _open_private_regular_at(
        parent_fd, filename, maximum_bytes=maximum_bytes, name=name
    )
    digest = hashlib.sha256()
    count = 0
    tail = b""
    try:
        while True:
            chunk = os.read(descriptor, IO_CHUNK_BYTES)
            if not chunk:
                break
            count += len(chunk)
            digest.update(chunk)
            if count > maximum_bytes:
                raise PhysicalAcceptedRiskArchiveCapacityError(
                    f"{name} exceeded its stream bound"
                )
            combined = tail + chunk
            if len(combined) > 1:
                yield combined[:-1]
                tail = combined[-1:]
            else:
                tail = combined
        after = os.fstat(descriptor)
        named = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(f"{name} could not be read") from exc
    finally:
        os.close(descriptor)
    if (
        count != before.st_size
        or count != expected_byte_count
        or tail != b"\n"
        or digest.hexdigest() != expected_sha256
        or len(
            {
                _regular_file_identity(before),
                _regular_file_identity(after),
                _regular_file_identity(named),
            }
        )
        != 1
        or not stat.S_ISREG(named.st_mode)
        or stat.S_IMODE(named.st_mode) != 0o600
        or named.st_nlink != 1
    ):
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} byte count, hash, LF terminator, or identity changed"
        )


def _descriptor_filename(
    role: MassiveSourceRole, page_number: int
) -> str:
    return (
        f"{_ROLE_ORDER.index(role) + 1:02d}-{role.value}-"
        f"page-{page_number:06d}.jsonl"
    )


def _preflight_archive_shape(value: PhysicalAcceptedRiskArchive) -> None:
    if type(value) is not PhysicalAcceptedRiskArchive:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive authority requires its exact type"
        )
    string_fields = (
        "schema",
        "archive_id",
        "archive_sha256",
        "source_artifact_id",
        "source_manifest_sha256",
        "capture_transport",
        "physical_capture_id",
        "physical_capture_sha256",
        "capture_started_at",
        "capture_completed_at",
        "capture_id",
        "capture_sha256",
        "requested_first_event_date",
        "requested_last_event_date",
        "source_page_root_sha256",
        "pair_id",
        "pair_sha256",
        "report_sha256",
    )
    try:
        for name in string_fields:
            if type(getattr(value, name)) is not str:
                raise PhysicalAcceptedRiskArchiveError(
                    f"{name} must remain an exact string"
                )
        if (
            type(value.archive_path) is not _PATH_TYPE
            or type(value.source_artifact_path) is not _PATH_TYPE
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk archive paths changed type"
            )
        for name in (
            "page_limit",
            "source_page_count",
            "source_row_count",
            "report_byte_count",
            "current_included_count",
            "censored_included_count",
            "disagreement_count",
            "maximum_source_page_byte_count",
            "maximum_semantic_page_byte_count",
        ):
            if type(getattr(value, name)) is not int:
                raise PhysicalAcceptedRiskArchiveError(
                    f"{name} must remain an exact integer"
                )
        for name in (
            "full_capture_materialized",
            "views_share_one_capture",
            "pristine_point_in_time",
            "provider_access",
            "credential_access",
            "quantconnect_access",
            "outcome_access",
            "result_access",
            "deployment",
            "orders",
            "trading",
        ):
            if type(getattr(value, name)) is not bool:
                raise PhysicalAcceptedRiskArchiveError(
                    f"{name} must remain an exact boolean"
                )
        if type(value.role_row_counts) is not tuple or type(value.shards) is not tuple:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk archive containers changed type"
            )
    except AttributeError as exc:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive state is incomplete"
        ) from exc
    if value.schema != ARCHIVE_SCHEMA:
        raise PhysicalAcceptedRiskArchiveError("accepted-risk archive schema changed")
    for name in (
        "archive_sha256",
        "source_manifest_sha256",
        "physical_capture_sha256",
        "capture_sha256",
        "source_page_root_sha256",
        "pair_sha256",
        "report_sha256",
    ):
        try:
            require_sha256(getattr(value, name), name)
        except CanonicalEvidenceError as exc:
            raise PhysicalAcceptedRiskArchiveError(
                f"{name} is not a SHA-256 digest"
            ) from exc
    try:
        require_identifier(value.archive_id, "archive_id")
        require_identifier(value.source_artifact_id, "source_artifact_id")
        require_identifier(value.physical_capture_id, "physical_capture_id")
        require_identifier(value.capture_id, "capture_id")
        require_identifier(value.pair_id, "pair_id")
        started = _PINNED_PARSE_UTC_TIMESTAMP(
            value.capture_started_at, "capture_started_at"
        )
        completed = _PINNED_PARSE_UTC_TIMESTAMP(
            value.capture_completed_at, "capture_completed_at"
        )
        first = _PINNED_PARSE_DATE(
            value.requested_first_event_date, "requested_first_event_date"
        )
        last = _PINNED_PARSE_DATE(
            value.requested_last_event_date, "requested_last_event_date"
        )
        require_int(
            value.page_limit,
            "page_limit",
            minimum=1,
            maximum=_PINNED_MAX_PROVIDER_ROWS_PER_PAGE,
        )
    except CanonicalEvidenceError as exc:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive scalar is invalid"
        ) from exc
    if first > last:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive requested range is reversed"
        )
    if started > completed:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive capture chronology is reversed"
        )
    try:
        require_artifact_binding(value.pair_artifact)
    except (FormalRunProtocolError, AttributeError, TypeError, ValueError) as exc:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk pair artifact binding changed"
        ) from exc
    if (
        value.pair_artifact.artifact_id != value.pair_id
        or value.pair_artifact.content_sha256 != value.pair_sha256
        or value.archive_id
        != f"arv2-physical-accepted-risk-{value.archive_sha256[:24]}"
        or value.archive_path.name != value.archive_id
        or value.source_artifact_path.name != value.source_artifact_id
        or value.source_page_count < len(_ROLE_ORDER)
        or value.source_row_count < 1
        or value.report_byte_count < 1
        or not (
            0
            <= value.censored_included_count
            <= value.current_included_count
            <= value.source_row_count
        )
        or value.disagreement_count
        != value.current_included_count - value.censored_included_count
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive aggregate semantics changed"
        )
    if (
        value.full_capture_materialized is not False
        or value.views_share_one_capture is not True
        or value.pristine_point_in_time is not False
        or any(
            getattr(value, name) is not False
            for name in (
                "provider_access",
                "credential_access",
                "quantconnect_access",
                "outcome_access",
                "result_access",
                "deployment",
                "orders",
                "trading",
            )
        )
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive capability or risk classification changed"
        )
    if len(value.role_row_counts) != len(_ROLE_ORDER):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive role census is incomplete"
        )
    for index, item in enumerate(value.role_row_counts):
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not MassiveSourceRole
            or item[0] is not _ROLE_ORDER[index]
            or type(item[1]) is not int
            or item[1] < 0
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk archive role census changed"
            )
    if sum(count for _role, count in value.role_row_counts) != value.source_row_count:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive role rows do not exhaust its source"
        )
    if len(value.shards) != value.source_page_count:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive shard inventory is incomplete"
        )
    role_rows: Counter[MassiveSourceRole] = Counter()
    expected_role_ordinal = 0
    expected_page_number = 1
    copied: list[_CopiedPage] = []
    prior: AcceptedRiskShardDescriptor | None = None
    source_names: set[str] = set()
    semantic_names: set[str] = set()
    terminal_roles: set[MassiveSourceRole] = set()
    seen_cursor_hashes: dict[MassiveSourceRole, set[str]] = {
        role: set() for role in _ROLE_ORDER
    }
    seen_response_hashes: dict[MassiveSourceRole, set[str]] = {
        role: set() for role in _ROLE_ORDER
    }
    for descriptor in value.shards:
        if type(descriptor) is not AcceptedRiskShardDescriptor:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard descriptor type changed"
            )
        for name in (
            "source_relative_path",
            "source_sha256",
            "semantic_relative_path",
            "semantic_sha256",
            "endpoint_identifier",
            "redacted_query_sha256",
            "response_received_at",
            "raw_response_sha256",
        ):
            if type(getattr(descriptor, name)) is not str:
                raise PhysicalAcceptedRiskArchiveError(
                    "accepted-risk shard scalar type changed"
                )
        if type(descriptor.source_role) is not MassiveSourceRole:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard source role changed type"
            )
        if descriptor.source_role in terminal_roles:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard follows a terminal page"
            )
        for name in (
            "page_number",
            "source_byte_count",
            "semantic_byte_count",
            "row_count",
        ):
            if type(getattr(descriptor, name)) is not int:
                raise PhysicalAcceptedRiskArchiveError(
                    "accepted-risk shard integer changed type"
                )
        if type(descriptor.terminal_page) is not bool:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard terminal flag changed type"
            )
        for name in ("request_cursor_sha256", "next_cursor_sha256"):
            cursor = getattr(descriptor, name)
            if type(cursor) not in (str, type(None)):
                raise PhysicalAcceptedRiskArchiveError(
                    "accepted-risk shard cursor changed type"
                )
            if cursor is not None:
                try:
                    require_sha256(cursor, name)
                except CanonicalEvidenceError as exc:
                    raise PhysicalAcceptedRiskArchiveError(
                        "accepted-risk shard cursor is invalid"
                    ) from exc
        try:
            require_sha256(descriptor.source_sha256, "source_sha256")
            require_sha256(descriptor.semantic_sha256, "semantic_sha256")
            require_sha256(descriptor.redacted_query_sha256, "redacted_query_sha256")
            require_sha256(descriptor.raw_response_sha256, "raw_response_sha256")
            _PINNED_PARSE_UTC_TIMESTAMP(
                descriptor.response_received_at, "response_received_at"
            )
            require_int(descriptor.page_number, "page_number", minimum=1)
            require_int(
                descriptor.source_byte_count,
                "source_byte_count",
                minimum=0,
                maximum=_PINNED_MAX_CAPTURE_PAGE_BYTES,
            )
            require_int(
                descriptor.semantic_byte_count,
                "semantic_byte_count",
                minimum=0,
                maximum=MAX_DERIVED_SHARD_BYTES,
            )
            require_int(
                descriptor.row_count,
                "row_count",
                minimum=0,
                maximum=value.page_limit,
            )
        except CanonicalEvidenceError as exc:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard field is invalid"
            ) from exc
        role_ordinal = _ROLE_ORDER.index(descriptor.source_role)
        if role_ordinal != expected_role_ordinal:
            if (
                role_ordinal != expected_role_ordinal + 1
                or prior is None
                or prior.terminal_page is not True
            ):
                raise PhysicalAcceptedRiskArchiveError(
                    "accepted-risk shards are not in complete canonical role order"
                )
            expected_role_ordinal = role_ordinal
            expected_page_number = 1
        if descriptor.page_number != expected_page_number:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard pages are not contiguous from one"
            )
        if expected_page_number == 1:
            if descriptor.request_cursor_sha256 is not None:
                raise PhysicalAcceptedRiskArchiveError(
                    "accepted-risk shard role begins with a cursor"
                )
        elif prior is None or descriptor.request_cursor_sha256 != prior.next_cursor_sha256:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard cursor chain is discontinuous"
            )
        if descriptor.terminal_page != (descriptor.next_cursor_sha256 is None):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard terminal flag and cursor disagree"
            )
        if (
            descriptor.next_cursor_sha256 is not None
            and descriptor.next_cursor_sha256
            in seen_cursor_hashes[descriptor.source_role]
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard cursor chain repeats or cycles"
            )
        if (
            descriptor.raw_response_sha256
            in seen_response_hashes[descriptor.source_role]
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard pagination replays a response"
            )
        filename = _descriptor_filename(
            descriptor.source_role, descriptor.page_number
        )
        if (
            descriptor.source_relative_path != f"{SOURCE_DIRECTORY}/{filename}"
            or descriptor.semantic_relative_path != f"{ROW_DIRECTORY}/{filename}"
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard filename is not canonical"
            )
        source_names.add(filename)
        semantic_names.add(filename)
        query = _PINNED_RENDER_REDACTED_QUERY(
            source_role=descriptor.source_role,
            requested_first_event_date=value.requested_first_event_date,
            requested_last_event_date=value.requested_last_event_date,
            limit=value.page_limit,
        )
        if sha256_bytes(query) != descriptor.redacted_query_sha256:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk shard query hash changed"
            )
        copied.append(
            _CopiedPage(
                source_role=descriptor.source_role,
                page_number=descriptor.page_number,
                endpoint_identifier=descriptor.endpoint_identifier,
                redacted_query_bytes=query,
                redacted_query_sha256=descriptor.redacted_query_sha256,
                request_cursor_sha256=descriptor.request_cursor_sha256,
                next_cursor_sha256=descriptor.next_cursor_sha256,
                terminal_page=descriptor.terminal_page,
                response_received_at=descriptor.response_received_at,
                raw_response_sha256=descriptor.raw_response_sha256,
                provider_rows_sha256=descriptor.source_sha256,
                row_count=descriptor.row_count,
                source_relative_path=descriptor.source_relative_path,
                source_byte_count=descriptor.source_byte_count,
                source_sha256=descriptor.source_sha256,
            )
        )
        role_rows[descriptor.source_role] += descriptor.row_count
        if descriptor.next_cursor_sha256 is not None:
            seen_cursor_hashes[descriptor.source_role].add(
                descriptor.next_cursor_sha256
            )
        seen_response_hashes[descriptor.source_role].add(
            descriptor.raw_response_sha256
        )
        if descriptor.terminal_page:
            terminal_roles.add(descriptor.source_role)
        expected_page_number += 1
        prior = descriptor
    if (
        expected_role_ordinal != len(_ROLE_ORDER) - 1
        or prior is None
        or prior.terminal_page is not True
        or tuple((role, role_rows[role]) for role in _ROLE_ORDER)
        != value.role_row_counts
        or value.maximum_source_page_byte_count
        != max(item.source_byte_count for item in value.shards)
        or value.maximum_semantic_page_byte_count
        != max(item.semantic_byte_count for item in value.shards)
        or _source_page_root(tuple(copied)) != value.source_page_root_sha256
        or len(source_names) != len(value.shards)
        or len(semantic_names) != len(value.shards)
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk shard aggregate or source root changed"
        )
    physical_capture_id, physical_capture_sha256 = (
        _authenticate_physical_capture_identity(
            pages=tuple(copied),
            capture_started_at=value.capture_started_at,
            capture_completed_at=value.capture_completed_at,
            requested_first_event_date=value.requested_first_event_date,
            requested_last_event_date=value.requested_last_event_date,
            expected_capture_id=value.physical_capture_id,
            expected_capture_sha256=value.physical_capture_sha256,
        )
    )
    derived_capture_id, derived_capture_sha256 = _capture_identity(
        _capture_record(
            pages=tuple(copied),
            capture_started_at=value.capture_started_at,
            capture_completed_at=value.capture_completed_at,
            requested_first_event_date=value.requested_first_event_date,
            requested_last_event_date=value.requested_last_event_date,
            raw_response_extraction_verified=False,
            contract_sha256=_PINNED_INPUT_PAIR_CONTRACT_SHA256,
        )
    )
    receipts = tuple(
        _PINNED_PARSE_UTC_TIMESTAMP(
            item.response_received_at, "response_received_at"
        )
        for item in copied
    )
    if (
        physical_capture_id != value.physical_capture_id
        or physical_capture_sha256 != value.physical_capture_sha256
        or derived_capture_id != value.capture_id
        or derived_capture_sha256 != value.capture_sha256
        or receipts != tuple(sorted(receipts))
        or any(item < started or item > completed for item in receipts)
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "physical or derived capture identity changed"
        )


def _archive_seed_from_value(
    value: PhysicalAcceptedRiskArchive,
) -> dict[str, object]:
    return _archive_seed(
        source_artifact_id=value.source_artifact_id,
        source_manifest_sha256=value.source_manifest_sha256,
        capture_transport=value.capture_transport,
        physical_capture_id=value.physical_capture_id,
        physical_capture_sha256=value.physical_capture_sha256,
        capture_started_at=value.capture_started_at,
        capture_completed_at=value.capture_completed_at,
        capture_id=value.capture_id,
        capture_sha256=value.capture_sha256,
        requested_first_event_date=value.requested_first_event_date,
        requested_last_event_date=value.requested_last_event_date,
        page_limit=value.page_limit,
        source_page_root_sha256=value.source_page_root_sha256,
        source_page_count=value.source_page_count,
        source_row_count=value.source_row_count,
        role_row_counts=value.role_row_counts,
        pair_artifact=value.pair_artifact,
        report_sha256=value.report_sha256,
        report_byte_count=value.report_byte_count,
        current_included_count=value.current_included_count,
        censored_included_count=value.censored_included_count,
        disagreement_count=value.disagreement_count,
        shards=value.shards,
        maximum_source_page_byte_count=value.maximum_source_page_byte_count,
        maximum_semantic_page_byte_count=value.maximum_semantic_page_byte_count,
    )


def _reload_exact_object(
    value: object,
    keys: tuple[str, ...],
    name: str,
) -> dict[str, Any]:
    if type(value) is not dict or tuple(sorted(value)) != keys:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} has unknown, missing, or non-string keys"
        )
    return value


def _reload_exact_flags(
    value: object,
    expected: tuple[tuple[str, bool], ...],
    name: str,
) -> dict[str, Any]:
    raw = _reload_exact_object(value, tuple(key for key, _ in expected), name)
    if any(
        type(raw[key]) is not bool or raw[key] is not item
        for key, item in expected
    ):
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} changed type or immutable value"
        )
    return raw


def _strict_reload_json_object(payload: bytes, name: str) -> dict[str, Any]:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_ARCHIVE_MANIFEST_BYTES:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} is not bounded exact bytes"
        )
    try:
        value = strict_json_loads(decode_utf8(payload, name), name)
        canonical = canonical_json_bytes(value)
    except (RecursionError, TypeError, UnicodeError, ValueError) as exc:
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} is not strict UTF-8 JSON"
        ) from exc
    if type(value) is not dict or canonical != payload:
        raise PhysicalAcceptedRiskArchiveError(f"{name} is not canonical JSON")
    return value


def _archive_from_reload_manifest(
    *,
    manifest_bytes: bytes,
    archive_path: Path,
    source_artifact_path: Path,
) -> PhysicalAcceptedRiskArchive:
    raw = _reload_exact_object(
        _strict_reload_json_object(
            manifest_bytes, "accepted-risk reload manifest"
        ),
        _RELOAD_MANIFEST_KEYS,
        "accepted-risk reload manifest",
    )
    string_names = (
        "archive_id",
        "archive_sha256",
        "capture_completed_at",
        "capture_id",
        "capture_sha256",
        "capture_started_at",
        "capture_transport",
        "physical_capture_id",
        "physical_capture_sha256",
        "requested_first_event_date",
        "requested_last_event_date",
        "schema",
        "source_artifact_id",
        "source_manifest_sha256",
        "source_page_root_sha256",
    )
    integer_names = (
        "censored_included_count",
        "current_included_count",
        "disagreement_count",
        "maximum_semantic_page_byte_count",
        "maximum_source_page_byte_count",
        "page_limit",
        "source_page_count",
        "source_row_count",
    )
    if any(type(raw[name]) is not str for name in string_names):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload manifest scalar changed type"
        )
    if any(type(raw[name]) is not int for name in integer_names):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload manifest count changed type"
        )
    if archive_path.name != raw["archive_id"]:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload archive path does not bind the manifest"
        )
    if source_artifact_path.name != raw["source_artifact_id"]:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload source path does not bind the manifest"
        )
    if type(raw["role_row_counts"]) is not list:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload role census changed type"
        )
    role_counts: list[tuple[MassiveSourceRole, int]] = []
    for item in raw["role_row_counts"]:
        entry = _reload_exact_object(
            item,
            _RELOAD_ROLE_COUNT_KEYS,
            "accepted-risk reload role census entry",
        )
        if (
            type(entry["source_role"]) is not str
            or type(entry["row_count"]) is not int
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk reload role census entry changed type"
            )
        try:
            role = MassiveSourceRole(entry["source_role"])
        except ValueError as exc:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk reload role census has an unknown role"
            ) from exc
        role_counts.append((role, entry["row_count"]))

    artifact_raw = _reload_exact_object(
        raw["pair_artifact"],
        _RELOAD_PAIR_ARTIFACT_KEYS,
        "accepted-risk reload pair artifact",
    )
    if (
        type(artifact_raw["artifact_id"]) is not str
        or type(artifact_raw["content_sha256"]) is not str
        or type(artifact_raw["artifact_sha256"]) is not str
        or type(artifact_raw["byte_count"]) is not int
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload pair artifact changed type"
        )
    try:
        pair_artifact = ArtifactBinding(
            artifact_id=artifact_raw["artifact_id"],
            content_sha256=artifact_raw["content_sha256"],
            artifact_sha256=artifact_raw["artifact_sha256"],
            byte_count=artifact_raw["byte_count"],
        )
    except (TypeError, ValueError) as exc:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload pair artifact is invalid"
        ) from exc

    report = _reload_exact_object(
        raw["report"], _RELOAD_REPORT_KEYS, "accepted-risk reload report"
    )
    if (
        type(report["relative_path"]) is not str
        or type(report["sha256"]) is not str
        or type(report["byte_count"]) is not int
        or report["relative_path"] != REPORT_FILENAME
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload report changed type or path"
        )

    if type(raw["shards"]) is not list:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload shard inventory changed type"
        )
    shards: list[AcceptedRiskShardDescriptor] = []
    shard_string_names = (
        "endpoint_identifier",
        "raw_response_sha256",
        "redacted_query_sha256",
        "response_received_at",
        "semantic_relative_path",
        "semantic_sha256",
        "source_relative_path",
        "source_sha256",
        "source_role",
    )
    shard_integer_names = (
        "page_number",
        "row_count",
        "semantic_byte_count",
        "source_byte_count",
    )
    for item in raw["shards"]:
        entry = _reload_exact_object(
            item,
            _RELOAD_SHARD_KEYS,
            "accepted-risk reload shard entry",
        )
        if any(type(entry[name]) is not str for name in shard_string_names):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk reload shard scalar changed type"
            )
        if any(type(entry[name]) is not int for name in shard_integer_names):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk reload shard count changed type"
            )
        if type(entry["terminal_page"]) is not bool or any(
            type(entry[name]) not in (str, type(None))
            for name in ("request_cursor_sha256", "next_cursor_sha256")
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk reload shard nullable field changed type"
            )
        try:
            role = MassiveSourceRole(entry["source_role"])
        except ValueError as exc:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk reload shard has an unknown role"
            ) from exc
        shards.append(
            AcceptedRiskShardDescriptor(
                source_role=role,
                page_number=entry["page_number"],
                source_relative_path=entry["source_relative_path"],
                source_byte_count=entry["source_byte_count"],
                source_sha256=entry["source_sha256"],
                semantic_relative_path=entry["semantic_relative_path"],
                semantic_byte_count=entry["semantic_byte_count"],
                semantic_sha256=entry["semantic_sha256"],
                row_count=entry["row_count"],
                endpoint_identifier=entry["endpoint_identifier"],
                redacted_query_sha256=entry["redacted_query_sha256"],
                request_cursor_sha256=entry["request_cursor_sha256"],
                next_cursor_sha256=entry["next_cursor_sha256"],
                terminal_page=entry["terminal_page"],
                response_received_at=entry["response_received_at"],
                raw_response_sha256=entry["raw_response_sha256"],
            )
        )

    storage = _reload_exact_flags(
        raw["storage"], _RELOAD_STORAGE, "accepted-risk reload storage"
    )
    accepted_risk = _reload_exact_flags(
        raw["accepted_risk"],
        _RELOAD_ACCEPTED_RISK,
        "accepted-risk reload risk flags",
    )
    capabilities = _reload_exact_flags(
        raw["capabilities"],
        _RELOAD_CAPABILITIES,
        "accepted-risk reload capabilities",
    )
    value = object.__new__(PhysicalAcceptedRiskArchive)
    values: dict[str, object] = {
        "schema": raw["schema"],
        "archive_id": raw["archive_id"],
        "archive_sha256": raw["archive_sha256"],
        "archive_path": archive_path,
        "source_artifact_path": source_artifact_path,
        "source_artifact_id": raw["source_artifact_id"],
        "source_manifest_sha256": raw["source_manifest_sha256"],
        "capture_transport": raw["capture_transport"],
        "physical_capture_id": raw["physical_capture_id"],
        "physical_capture_sha256": raw["physical_capture_sha256"],
        "capture_started_at": raw["capture_started_at"],
        "capture_completed_at": raw["capture_completed_at"],
        "capture_id": raw["capture_id"],
        "capture_sha256": raw["capture_sha256"],
        "requested_first_event_date": raw["requested_first_event_date"],
        "requested_last_event_date": raw["requested_last_event_date"],
        "page_limit": raw["page_limit"],
        "source_page_root_sha256": raw["source_page_root_sha256"],
        "source_page_count": raw["source_page_count"],
        "source_row_count": raw["source_row_count"],
        "role_row_counts": tuple(role_counts),
        "pair_id": pair_artifact.artifact_id,
        "pair_sha256": pair_artifact.content_sha256,
        "pair_artifact": pair_artifact,
        "report_sha256": report["sha256"],
        "report_byte_count": report["byte_count"],
        "current_included_count": raw["current_included_count"],
        "censored_included_count": raw["censored_included_count"],
        "disagreement_count": raw["disagreement_count"],
        "shards": tuple(shards),
        "maximum_source_page_byte_count": raw[
            "maximum_source_page_byte_count"
        ],
        "maximum_semantic_page_byte_count": raw[
            "maximum_semantic_page_byte_count"
        ],
        "full_capture_materialized": storage["full_capture_materialized"],
        "views_share_one_capture": accepted_risk["views_share_one_capture"],
        "pristine_point_in_time": accepted_risk["pristine_point_in_time"],
        "provider_access": capabilities["provider_access"],
        "credential_access": capabilities["credential_access"],
        "quantconnect_access": capabilities["quantconnect_access"],
        "outcome_access": capabilities["outcome_access"],
        "result_access": capabilities["result_access"],
        "deployment": capabilities["deployment"],
        "orders": capabilities["orders"],
        "trading": capabilities["trading"],
    }
    if set(values) != {field.name for field in dataclasses.fields(value)}:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload field inventory changed"
        )
    for name, item in values.items():
        object.__setattr__(value, name, item)
    _preflight_archive_shape(value)
    return value


def _pin_reload_source_manifest_leaves(
    source_fd: int,
) -> dict[str, tuple[int, int, int, int, int]]:
    identities: dict[str, tuple[int, int, int, int, int]] = {}
    for filename, maximum, name in (
        (ARCHIVE_MANIFEST, MAX_ARCHIVE_MANIFEST_BYTES, "source capture manifest"),
        (ARCHIVE_MANIFEST_DIGEST, 65, "source capture manifest digest"),
    ):
        descriptor, metadata = _open_private_regular_at(
            source_fd,
            filename,
            maximum_bytes=maximum,
            name=name,
        )
        try:
            identities[filename] = _regular_file_identity(metadata)
        finally:
            os.close(descriptor)
    return identities


def _require_reload_source_manifest_leaves(
    source_fd: int,
    expected: Mapping[str, tuple[int, int, int, int, int]],
) -> None:
    for filename, identity in expected.items():
        try:
            metadata = os.stat(filename, dir_fd=source_fd, follow_symlinks=False)
        except OSError as exc:
            raise PhysicalAcceptedRiskArchiveError(
                "source capture manifest identity changed"
            ) from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or _regular_file_identity(metadata) != identity
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "source capture manifest identity changed"
            )


def _require_exact_reload_path(value: object, name: str) -> Path:
    if (
        type(value) is not _PATH_TYPE
        or not value.is_absolute()
        or ".." in value.parts
        or value != Path(os.path.abspath(value))
    ):
        raise PhysicalAcceptedRiskArchiveError(
            f"{name} must be an exact absolute Path"
        )
    return value


def _require_inventory(
    root_fd: int,
    source_fd: int,
    rows_fd: int,
    value: PhysicalAcceptedRiskArchive,
) -> None:
    expected = {
        _descriptor_filename(item.source_role, item.page_number)
        for item in value.shards
    }
    try:
        root_names = set(os.listdir(root_fd))
        source_names = set(os.listdir(source_fd))
        row_names = set(os.listdir(rows_fd))
    except OSError as exc:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive inventory is unreadable"
        ) from exc
    if (
        root_names
        != {
            SOURCE_DIRECTORY,
            ROW_DIRECTORY,
            REPORT_FILENAME,
            ARCHIVE_MANIFEST,
            ARCHIVE_MANIFEST_DIGEST,
        }
        or source_names != expected
        or row_names != expected
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive inventory changed"
        )


def _pin_archive_leaf_identities(
    root_fd: int,
    source_fd: int,
    rows_fd: int,
    value: PhysicalAcceptedRiskArchive,
) -> dict[tuple[str, str], _PinnedArchiveLeaf]:
    identities: dict[tuple[str, str], _PinnedArchiveLeaf] = {}
    expected_manifest = canonical_json_bytes(
        {
            **_archive_seed_from_value(value),
            "archive_id": value.archive_id,
            "archive_sha256": value.archive_sha256,
        }
    )
    expected_manifest_digest = (
        sha256_bytes(expected_manifest) + "\n"
    ).encode("ascii")

    def pin(
        area: str,
        parent_fd: int,
        filename: str,
        maximum_bytes: int,
        name: str,
        expected_byte_count: int,
        expected_sha256: str,
    ) -> None:
        identity = _observe_archive_leaf(
            parent_fd,
            filename,
            maximum_bytes=maximum_bytes,
            name=name,
        )
        identities[(area, filename)] = _PinnedArchiveLeaf(
            identity=identity,
            maximum_bytes=maximum_bytes,
            expected_byte_count=expected_byte_count,
            expected_sha256=expected_sha256,
            name=name,
        )

    pin(
        "root",
        root_fd,
        ARCHIVE_MANIFEST,
        MAX_ARCHIVE_MANIFEST_BYTES,
        "accepted-risk archive manifest",
        len(expected_manifest),
        sha256_bytes(expected_manifest),
    )
    pin(
        "root",
        root_fd,
        ARCHIVE_MANIFEST_DIGEST,
        65,
        "accepted-risk archive manifest digest",
        len(expected_manifest_digest),
        sha256_bytes(expected_manifest_digest),
    )
    pin(
        "root",
        root_fd,
        REPORT_FILENAME,
        MAX_REPORT_BYTES,
        "accepted-risk report",
        value.report_byte_count,
        value.report_sha256,
    )
    for descriptor in value.shards:
        filename = _descriptor_filename(
            descriptor.source_role, descriptor.page_number
        )
        pin(
            "source",
            source_fd,
            filename,
            _PINNED_MAX_CAPTURE_PAGE_BYTES,
            "accepted-risk source shard",
            descriptor.source_byte_count,
            descriptor.source_sha256,
        )
        pin(
            "rows",
            rows_fd,
            filename,
            MAX_DERIVED_SHARD_BYTES,
            "accepted-risk semantic shard",
            descriptor.semantic_byte_count,
            descriptor.semantic_sha256,
        )
    return identities


def _require_archive_leaf_identities(
    root_fd: int,
    source_fd: int,
    rows_fd: int,
    expected: dict[tuple[str, str], _PinnedArchiveLeaf],
) -> None:
    if type(expected) is not dict or any(
        type(key) is not tuple
        or len(key) != 2
        or type(pin) is not _PinnedArchiveLeaf
        for key, pin in expected.items()
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive leaf authority changed type"
        )
    parents = {"root": root_fd, "source": source_fd, "rows": rows_fd}
    for (area, filename), pin in tuple(expected.items()):
        try:
            observed_identity = _observe_archive_leaf(
                parents[area],
                filename,
                maximum_bytes=pin.maximum_bytes,
                name=pin.name,
            )
        except (KeyError, OSError, PhysicalAcceptedRiskArchiveError) as exc:
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk archive named leaf identity changed"
            ) from exc
        root_manifest_leaf = area == "root" and filename in {
            ARCHIVE_MANIFEST,
            ARCHIVE_MANIFEST_DIGEST,
        }
        if observed_identity == pin.identity:
            continue
        non_ctime_changed = (
            _without_archive_leaf_ctime(observed_identity)
            != _without_archive_leaf_ctime(pin.identity)
        )
        manifest_ctime_only = (
            root_manifest_leaf
            and not non_ctime_changed
            and observed_identity[4] != pin.identity[4]
        )
        darwin_ctime_only = (
            sys.platform == "darwin"
            and not non_ctime_changed
            and observed_identity[4] != pin.identity[4]
        )
        if not (manifest_ctime_only or darwin_ctime_only):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk archive named leaf identity changed"
            )
        try:
            _hash_private_regular_at(
                parents[area],
                filename,
                maximum_bytes=pin.maximum_bytes,
                expected_byte_count=pin.expected_byte_count,
                expected_sha256=pin.expected_sha256,
                name=pin.name,
            )
        except PhysicalAcceptedRiskArchiveError as exc:
            if root_manifest_leaf:
                raise PhysicalAcceptedRiskArchiveError(
                    "accepted-risk archive manifest does not authenticate"
                ) from exc
            raise
        final_identity = _observe_archive_leaf(
            parents[area],
            filename,
            maximum_bytes=pin.maximum_bytes,
            name=pin.name,
        )
        if (
            final_identity != observed_identity
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk archive named leaf identity changed"
            )
        expected[(area, filename)] = dataclasses.replace(
            pin,
            identity=final_identity,
        )


def _require_exact_archive_manifest_bytes(
    root_fd: int,
    expected_manifest: bytes,
) -> None:
    """Reauthenticate root manifests after allowing macOS-only ctime drift."""

    manifest = _read_private_regular_at(
        root_fd,
        ARCHIVE_MANIFEST,
        maximum_bytes=MAX_ARCHIVE_MANIFEST_BYTES,
        name="accepted-risk archive manifest",
    )
    digest = _read_private_regular_at(
        root_fd,
        ARCHIVE_MANIFEST_DIGEST,
        maximum_bytes=65,
        name="accepted-risk archive manifest digest",
    )
    if (
        manifest != expected_manifest
        or digest != (sha256_bytes(expected_manifest) + "\n").encode("ascii")
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive manifest does not authenticate"
        )


def _pair_binding_from_archive_fds(
    value: PhysicalAcceptedRiskArchive,
    *,
    root_fd: int,
    rows_fd: int,
) -> tuple[str, ArtifactBinding]:
    def row_items() -> Iterator[bytes]:
        for descriptor in value.shards:
            yield from _iter_verified_jsonl_fragments_at(
                rows_fd,
                Path(descriptor.semantic_relative_path).name,
                maximum_bytes=MAX_DERIVED_SHARD_BYTES,
                maximum_line_bytes=MAX_SEMANTIC_ROW_BYTES,
                expected_byte_count=descriptor.semantic_byte_count,
                expected_sha256=descriptor.semantic_sha256,
                expected_row_count=descriptor.row_count,
                name="accepted-risk semantic shard",
            )

    fields = _pair_fields(
        capture_id=value.capture_id,
        capture_sha256=value.capture_sha256,
        row_items=row_items,
        report_items=lambda: _iter_verified_file_fragment_at(
            root_fd,
            REPORT_FILENAME,
            maximum_bytes=MAX_REPORT_BYTES,
            expected_byte_count=value.report_byte_count,
            expected_sha256=value.report_sha256,
            name="accepted-risk report",
        ),
    )
    return _pair_binding_from_stream(
        _iter_canonical_object(fields, terminate=True), value.pair_id
    )


def require_physical_accepted_risk_archive(
    value: PhysicalAcceptedRiskArchive,
) -> PhysicalAcceptedRiskArchive:
    """Reauthenticate one builder-issued archive and every persisted byte."""

    _require_dependency_bindings()
    _preflight_archive_shape(value)
    with _AUTHORITY_LOCK:
        authority = _AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or _archive_topology(value) != authority[2]
        or _archive_fingerprint(value) != authority[1]
        or authority[4] != os.getpid()
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive is not current builder authority"
        )
    seed = _archive_seed_from_value(value)
    archive_sha256 = sha256_bytes(canonical_json_bytes(seed))
    if archive_sha256 != value.archive_sha256:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive content root changed"
        )
    expected_manifest = canonical_json_bytes(
        {
            **seed,
            "archive_id": value.archive_id,
            "archive_sha256": value.archive_sha256,
        }
    )
    root_fd = _open_private_directory(
        value.archive_path, "accepted-risk archive"
    )
    try:
        _require_reopened_directory_identity(
            value.archive_path,
            root_fd,
            name="accepted-risk archive",
            private_final=True,
        )
        source_fd = _open_private_child_directory(root_fd, SOURCE_DIRECTORY)
        try:
            rows_fd = _open_private_child_directory(root_fd, ROW_DIRECTORY)
            try:
                if (
                    _directory_identity(os.fstat(root_fd)),
                    _directory_identity(os.fstat(source_fd)),
                    _directory_identity(os.fstat(rows_fd)),
                ) != authority[3]:
                    raise PhysicalAcceptedRiskArchiveError(
                        "accepted-risk archive physical directory authority changed"
                    )
                _require_pinned_child_identity(
                    root_fd,
                    SOURCE_DIRECTORY,
                    source_fd,
                    "accepted-risk source directory",
                )
                _require_pinned_child_identity(
                    root_fd,
                    ROW_DIRECTORY,
                    rows_fd,
                    "accepted-risk row directory",
                )
                _require_inventory(root_fd, source_fd, rows_fd, value)
                leaf_identities = _pin_archive_leaf_identities(
                    root_fd, source_fd, rows_fd, value
                )
                manifest = _read_private_regular_at(
                    root_fd,
                    ARCHIVE_MANIFEST,
                    maximum_bytes=MAX_ARCHIVE_MANIFEST_BYTES,
                    name="accepted-risk archive manifest",
                )
                digest = _read_private_regular_at(
                    root_fd,
                    ARCHIVE_MANIFEST_DIGEST,
                    maximum_bytes=65,
                    name="accepted-risk archive manifest digest",
                )
                if (
                    manifest != expected_manifest
                    or digest != (sha256_bytes(manifest) + "\n").encode("ascii")
                ):
                    raise PhysicalAcceptedRiskArchiveError(
                        "accepted-risk archive manifest does not authenticate"
                    )
                for descriptor in value.shards:
                    _hash_private_regular_at(
                        source_fd,
                        Path(descriptor.source_relative_path).name,
                        maximum_bytes=_PINNED_MAX_CAPTURE_PAGE_BYTES,
                        expected_byte_count=descriptor.source_byte_count,
                        expected_sha256=descriptor.source_sha256,
                        name="accepted-risk source shard",
                    )
                pair_id, pair_artifact = _pair_binding_from_archive_fds(
                    value, root_fd=root_fd, rows_fd=rows_fd
                )
                if (
                    pair_id != value.pair_id
                    or pair_artifact != value.pair_artifact
                    or pair_artifact.content_sha256 != value.pair_sha256
                ):
                    raise PhysicalAcceptedRiskArchiveError(
                        "accepted-risk pair artifact bytes changed"
                    )
                _require_inventory(root_fd, source_fd, rows_fd, value)
                _require_archive_leaf_identities(
                    root_fd,
                    source_fd,
                    rows_fd,
                    leaf_identities,
                )
                _require_exact_archive_manifest_bytes(root_fd, expected_manifest)
                _require_pinned_child_identity(
                    root_fd,
                    SOURCE_DIRECTORY,
                    source_fd,
                    "accepted-risk source directory",
                )
                _require_pinned_child_identity(
                    root_fd,
                    ROW_DIRECTORY,
                    rows_fd,
                    "accepted-risk row directory",
                )
                _require_reopened_directory_identity(
                    value.archive_path,
                    root_fd,
                    name="accepted-risk archive",
                    private_final=True,
                )
                _require_dependency_bindings()
            finally:
                os.close(rows_fd)
        finally:
            os.close(source_fd)
    finally:
        os.close(root_fd)
    return value


def _load_physical_accepted_risk_archive(
    *,
    archive_path: Path,
    source_artifact_path: Path,
    expected_archive_sha256: str,
    expected_source_manifest_sha256: str,
    expected_transport: str,
    require_repository_paths: bool,
) -> PhysicalAcceptedRiskArchive:
    """Reauthenticate and mint process-local authority for persisted C1 bytes.

    The reload is deliberately not a derivation.  It reconstructs only the
    bounded manifest object graph, pins all archive directory and leaf
    identities, then delegates full source/hash/pair verification to
    :func:`require_physical_accepted_risk_archive` before returning authority.
    """

    _require_dependency_bindings()
    try:
        require_sha256(
            expected_archive_sha256,
            "accepted-risk reload expected archive SHA-256",
        )
        require_sha256(
            expected_source_manifest_sha256,
            "accepted-risk reload expected source-manifest SHA-256",
        )
    except (CanonicalEvidenceError, TypeError, ValueError) as exc:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload external trust pin is invalid"
        ) from exc
    if (
        type(expected_transport) is not str
        or expected_transport not in (
            _PINNED_PRODUCTION_TRANSPORT,
            _PINNED_TEST_TRANSPORT,
        )
        or type(require_repository_paths) is not bool
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload trust policy changed"
        )
    archive = _require_exact_reload_path(
        archive_path, "accepted-risk reload archive path"
    )
    source = _require_exact_reload_path(
        source_artifact_path, "accepted-risk reload source path"
    )
    if (
        archive == source
        or archive in source.parents
        or source in archive.parents
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk reload archive and source paths overlap"
        )
    if require_repository_paths and (
        not _within_repository_artifacts(archive, permit_root=False)
        or not _within_repository_artifacts(source, permit_root=False)
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "production accepted-risk reload paths must remain under artifacts"
        )

    root_fd: int | None = None
    archived_source_fd: int | None = None
    rows_fd: int | None = None
    capture_fd: int | None = None
    registered_identity: int | None = None
    registered_reference: weakref.ReferenceType[PhysicalAcceptedRiskArchive] | None = (
        None
    )
    try:
        root_fd = _open_private_directory(archive, "accepted-risk reload archive")
        _require_reopened_directory_identity(
            archive,
            root_fd,
            name="accepted-risk reload archive",
            private_final=True,
        )
        archived_source_fd = _open_private_child_directory(
            root_fd, SOURCE_DIRECTORY
        )
        rows_fd = _open_private_child_directory(root_fd, ROW_DIRECTORY)
        _require_pinned_child_identity(
            root_fd,
            SOURCE_DIRECTORY,
            archived_source_fd,
            "accepted-risk reload source directory",
        )
        _require_pinned_child_identity(
            root_fd,
            ROW_DIRECTORY,
            rows_fd,
            "accepted-risk reload row directory",
        )
        manifest = _read_private_regular_at(
            root_fd,
            ARCHIVE_MANIFEST,
            maximum_bytes=MAX_ARCHIVE_MANIFEST_BYTES,
            name="accepted-risk reload manifest",
        )
        manifest_digest = _read_private_regular_at(
            root_fd,
            ARCHIVE_MANIFEST_DIGEST,
            maximum_bytes=65,
            name="accepted-risk reload manifest digest",
        )
        if manifest_digest != (sha256_bytes(manifest) + "\n").encode("ascii"):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk reload manifest digest changed"
            )
        value = _archive_from_reload_manifest(
            manifest_bytes=manifest,
            archive_path=archive,
            source_artifact_path=source,
        )
        if (
            value.archive_sha256 != expected_archive_sha256
            or value.source_manifest_sha256
            != expected_source_manifest_sha256
            or value.capture_transport != expected_transport
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk reload does not match its external trust pin"
            )
        seed = _archive_seed_from_value(value)
        if (
            sha256_bytes(canonical_json_bytes(seed)) != value.archive_sha256
            or manifest
            != canonical_json_bytes(
                {
                    **seed,
                    "archive_id": value.archive_id,
                    "archive_sha256": value.archive_sha256,
                }
            )
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk reload manifest content root changed"
            )
        _require_inventory(root_fd, archived_source_fd, rows_fd, value)
        archive_leaf_identities = _pin_archive_leaf_identities(
            root_fd, archived_source_fd, rows_fd, value
        )

        capture_fd = _open_private_directory(
            source, "accepted-risk reload source artifact"
        )
        _require_reopened_directory_identity(
            source,
            capture_fd,
            name="accepted-risk reload source artifact",
            private_final=True,
        )
        source_leaf_identities = _pin_reload_source_manifest_leaves(capture_fd)
        source_manifest = _read_private_regular_at(
            capture_fd,
            ARCHIVE_MANIFEST,
            maximum_bytes=MAX_ARCHIVE_MANIFEST_BYTES,
            name="source capture manifest",
        )
        source_manifest_digest = _read_private_regular_at(
            capture_fd,
            ARCHIVE_MANIFEST_DIGEST,
            maximum_bytes=65,
            name="source capture manifest digest",
        )
        source_raw = _strict_reload_json_object(
            source_manifest, "source capture manifest"
        )
        expected_source_role_counts = [
            {
                "source_role": role.value,
                "page_count": sum(
                    item.source_role is role for item in value.shards
                ),
                "row_count": count,
            }
            for role, count in value.role_row_counts
        ]
        if (
            sha256_bytes(source_manifest)
            != expected_source_manifest_sha256
            or value.source_manifest_sha256
            != expected_source_manifest_sha256
            or source_manifest_digest
            != (expected_source_manifest_sha256 + "\n").encode("ascii")
            or type(source_raw.get("artifact_id")) is not str
            or source_raw["artifact_id"] != value.source_artifact_id
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk reload source manifest does not authenticate"
            )
        if (
            type(source_raw.get("capture_transport")) is not str
            or source_raw["capture_transport"] != expected_transport
            or source_raw.get("capture_id") != value.physical_capture_id
            or source_raw.get("capture_sha256")
            != value.physical_capture_sha256
            or source_raw.get("capture_started_at") != value.capture_started_at
            or source_raw.get("capture_completed_at")
            != value.capture_completed_at
            or source_raw.get("requested_first_event_date")
            != value.requested_first_event_date
            or source_raw.get("requested_last_event_date")
            != value.requested_last_event_date
            or source_raw.get("page_limit") != value.page_limit
            or source_raw.get("total_page_count") != value.source_page_count
            or source_raw.get("total_row_count") != value.source_row_count
            or source_raw.get("role_order")
            != [role.value for role in _ROLE_ORDER]
            or source_raw.get("role_counts") != expected_source_role_counts
        ):
            raise PhysicalAcceptedRiskArchiveError(
                "accepted-risk reload source manifest identity is inconsistent"
            )
        _require_reload_source_manifest_leaves(
            capture_fd, source_leaf_identities
        )

        directory_identities = (
            _directory_identity(os.fstat(root_fd)),
            _directory_identity(os.fstat(archived_source_fd)),
            _directory_identity(os.fstat(rows_fd)),
        )
        identity = id(value)
        registered_identity = identity
        registered_reference = weakref.ref(
            value, lambda ref, key=identity: _forget(key, ref)
        )
        with _AUTHORITY_LOCK:
            _AUTHORITIES[identity] = (
                registered_reference,
                _archive_fingerprint(value),
                _archive_topology(value),
                directory_identities,
                os.getpid(),
            )
        authenticated = require_physical_accepted_risk_archive(value)
        _require_inventory(root_fd, archived_source_fd, rows_fd, value)
        _require_archive_leaf_identities(
            root_fd,
            archived_source_fd,
            rows_fd,
            archive_leaf_identities,
        )
        _require_exact_archive_manifest_bytes(root_fd, manifest)
        _require_pinned_child_identity(
            root_fd,
            SOURCE_DIRECTORY,
            archived_source_fd,
            "accepted-risk reload source directory",
        )
        _require_pinned_child_identity(
            root_fd,
            ROW_DIRECTORY,
            rows_fd,
            "accepted-risk reload row directory",
        )
        _require_reopened_directory_identity(
            archive,
            root_fd,
            name="accepted-risk reload archive",
            private_final=True,
        )
        _require_reload_source_manifest_leaves(
            capture_fd, source_leaf_identities
        )
        _require_reopened_directory_identity(
            source,
            capture_fd,
            name="accepted-risk reload source artifact",
            private_final=True,
        )
        _require_dependency_bindings()
        return authenticated
    except BaseException:
        if registered_identity is not None:
            with _AUTHORITY_LOCK:
                current = _AUTHORITIES.get(registered_identity)
                if (
                    current is not None
                    and current[0] is registered_reference
                ):
                    _AUTHORITIES.pop(registered_identity, None)
        raise
    finally:
        for descriptor in (
            capture_fd,
            rows_fd,
            archived_source_fd,
            root_fd,
        ):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass


def load_physical_accepted_risk_archive(
    *,
    archive_path: Path,
    source_artifact_path: Path,
    expected_archive_sha256: str,
    expected_source_manifest_sha256: str,
) -> PhysicalAcceptedRiskArchive:
    """Load production C1 only under owner/reviewer-supplied external pins."""

    return _load_physical_accepted_risk_archive(
        archive_path=archive_path,
        source_artifact_path=source_artifact_path,
        expected_archive_sha256=expected_archive_sha256,
        expected_source_manifest_sha256=expected_source_manifest_sha256,
        expected_transport=_PINNED_PRODUCTION_TRANSPORT,
        require_repository_paths=True,
    )


def _load_test_fixture_physical_accepted_risk_archive(
    *,
    archive_path: Path,
    source_artifact_path: Path,
    expected_archive_sha256: str,
    expected_source_manifest_sha256: str,
) -> PhysicalAcceptedRiskArchive:
    """Explicit offline seam; its test transport remains production-ineligible."""

    return _load_physical_accepted_risk_archive(
        archive_path=archive_path,
        source_artifact_path=source_artifact_path,
        expected_archive_sha256=expected_archive_sha256,
        expected_source_manifest_sha256=expected_source_manifest_sha256,
        expected_transport=_PINNED_TEST_TRANSPORT,
        require_repository_paths=False,
    )


def iter_physical_accepted_risk_rows(
    value: PhysicalAcceptedRiskArchive,
) -> Iterator[AcceptedRiskSourceRow]:
    """Yield every authenticated C1 row in exact legacy ``pair.rows`` order."""

    archive = require_physical_accepted_risk_archive(value)
    archive_seed = _archive_seed_from_value(archive)
    expected_manifest = canonical_json_bytes(
        {
            **archive_seed,
            "archive_id": archive.archive_id,
            "archive_sha256": archive.archive_sha256,
        }
    )
    with _AUTHORITY_LOCK:
        physical_authority = _AUTHORITIES.get(id(archive))
    if physical_authority is None or physical_authority[0]() is not archive:
        raise PhysicalAcceptedRiskArchiveError(
            "accepted-risk archive is not current builder authority"
        )
    context = _CaptureContext(
        capture_id=archive.capture_id,
        requested_first_event_date=archive.requested_first_event_date,
        requested_last_event_date=archive.requested_last_event_date,
    )
    root_fd = _open_private_directory(
        archive.archive_path, "accepted-risk archive"
    )
    yielded = 0
    try:
        _require_reopened_directory_identity(
            archive.archive_path,
            root_fd,
            name="accepted-risk archive",
            private_final=True,
        )
        source_fd = _open_private_child_directory(root_fd, SOURCE_DIRECTORY)
        try:
            rows_fd = _open_private_child_directory(root_fd, ROW_DIRECTORY)
            try:
                if (
                    _directory_identity(os.fstat(root_fd)),
                    _directory_identity(os.fstat(source_fd)),
                    _directory_identity(os.fstat(rows_fd)),
                ) != physical_authority[3]:
                    raise PhysicalAcceptedRiskArchiveError(
                        "accepted-risk archive physical directory authority changed"
                    )
                _require_pinned_child_identity(
                    root_fd,
                    SOURCE_DIRECTORY,
                    source_fd,
                    "accepted-risk source directory",
                )
                _require_pinned_child_identity(
                    root_fd,
                    ROW_DIRECTORY,
                    rows_fd,
                    "accepted-risk row directory",
                )
                _require_inventory(root_fd, source_fd, rows_fd, archive)
                leaf_identities = _pin_archive_leaf_identities(
                    root_fd, source_fd, rows_fd, archive
                )
                for descriptor in archive.shards:
                    _require_archive_leaf_identities(
                        root_fd, source_fd, rows_fd, leaf_identities
                    )
                    source_bytes = _read_private_regular_at(
                        source_fd,
                        Path(descriptor.source_relative_path).name,
                        maximum_bytes=_PINNED_MAX_CAPTURE_PAGE_BYTES,
                        name="accepted-risk source shard",
                    )
                    if (
                        len(source_bytes) != descriptor.source_byte_count
                        or sha256_bytes(source_bytes) != descriptor.source_sha256
                    ):
                        raise PhysicalAcceptedRiskArchiveError(
                            "accepted-risk source shard changed before row derivation"
                        )
                    query = _PINNED_RENDER_REDACTED_QUERY(
                        source_role=descriptor.source_role,
                        requested_first_event_date=archive.requested_first_event_date,
                        requested_last_event_date=archive.requested_last_event_date,
                        limit=archive.page_limit,
                    )
                    try:
                        page = CapturePageBinding(
                            schema=_PINNED_CAPTURE_PAGE_SCHEMA,
                            source_role=descriptor.source_role,
                            endpoint_identifier=descriptor.endpoint_identifier,
                            redacted_query_bytes=query,
                            redacted_query_sha256=descriptor.redacted_query_sha256,
                            page_number=descriptor.page_number,
                            request_cursor_sha256=descriptor.request_cursor_sha256,
                            next_cursor_sha256=descriptor.next_cursor_sha256,
                            terminal_page=descriptor.terminal_page,
                            response_received_at=descriptor.response_received_at,
                            raw_response_sha256=descriptor.raw_response_sha256,
                            provider_rows_bytes=source_bytes,
                            provider_rows_sha256=descriptor.source_sha256,
                            row_count=descriptor.row_count,
                            raw_response_bytes=None,
                        )
                    except (AcceptedRiskInputError, CanonicalEvidenceError) as exc:
                        raise PhysicalAcceptedRiskArchiveError(
                            "accepted-risk source shard failed page rebinding"
                        ) from exc
                    if (
                        page.endpoint_identifier != descriptor.endpoint_identifier
                        or page.redacted_query_sha256
                        != descriptor.redacted_query_sha256
                        or page.row_count != descriptor.row_count
                    ):
                        raise PhysicalAcceptedRiskArchiveError(
                            "accepted-risk source shard lineage changed"
                        )
                    provider_rows = _iter_provider_rows(source_bytes)
                    semantic_rows = _iter_verified_jsonl_fragments_at(
                        rows_fd,
                        Path(descriptor.semantic_relative_path).name,
                        maximum_bytes=MAX_DERIVED_SHARD_BYTES,
                        maximum_line_bytes=MAX_SEMANTIC_ROW_BYTES,
                        expected_byte_count=descriptor.semantic_byte_count,
                        expected_sha256=descriptor.semantic_sha256,
                        expected_row_count=descriptor.row_count,
                        name="accepted-risk semantic shard",
                    )
                    observed = 0
                    offset = 0
                    end = object()
                    while True:
                        provider_item = next(provider_rows, end)
                        semantic = next(semantic_rows, end)
                        if provider_item is end or semantic is end:
                            if provider_item is not semantic:
                                raise PhysicalAcceptedRiskArchiveError(
                                    "accepted-risk source and semantic row counts diverged"
                                )
                            break
                        raw, raw_bytes = provider_item
                        try:
                            row = _PINNED_DERIVE_SOURCE_ROW(
                                capture=context,  # type: ignore[arg-type]
                                page=page,
                                row_offset=offset,
                                row=raw,
                                raw_row_bytes=raw_bytes,
                                duplicate_provider_event_id=(
                                    _semantic_requires_duplicate_guidance_quarantine(
                                        semantic
                                    )
                                ),
                            )
                        except (
                            AcceptedRiskInputError,
                            CanonicalEvidenceError,
                        ) as exc:
                            raise PhysicalAcceptedRiskArchiveError(
                                "accepted-risk row could not be rederived"
                            ) from exc
                        if type(row) is not AcceptedRiskSourceRow:
                            raise PhysicalAcceptedRiskArchiveError(
                                "accepted-risk derivation returned the wrong row type"
                            )
                        try:
                            _PINNED_SOURCE_ROW_POST_INIT(row)
                        except (
                            AcceptedRiskInputError,
                            CanonicalEvidenceError,
                        ) as exc:
                            raise PhysicalAcceptedRiskArchiveError(
                                "accepted-risk row did not reauthenticate"
                            ) from exc
                        if (
                            canonical_json_bytes(
                                _PINNED_SOURCE_ROW_TO_RECORD(row)
                            )[:-1]
                            != semantic
                        ):
                            raise PhysicalAcceptedRiskArchiveError(
                                "accepted-risk semantic row changed"
                            )
                        observed += 1
                        yielded += 1
                        offset += 1
                        yield row
                        _require_archive_leaf_identities(
                            root_fd, source_fd, rows_fd, leaf_identities
                        )
                    if observed != descriptor.row_count:
                        raise PhysicalAcceptedRiskArchiveError(
                            "accepted-risk shard row census changed"
                        )
                    del page, source_bytes
                if yielded != archive.source_row_count:
                    raise PhysicalAcceptedRiskArchiveError(
                        "accepted-risk iterator did not exhaust every source row"
                    )
                _require_inventory(root_fd, source_fd, rows_fd, archive)
                _require_archive_leaf_identities(
                    root_fd, source_fd, rows_fd, leaf_identities
                )
                _require_exact_archive_manifest_bytes(root_fd, expected_manifest)
                _require_pinned_child_identity(
                    root_fd,
                    SOURCE_DIRECTORY,
                    source_fd,
                    "accepted-risk source directory",
                )
                _require_pinned_child_identity(
                    root_fd,
                    ROW_DIRECTORY,
                    rows_fd,
                    "accepted-risk row directory",
                )
                _require_reopened_directory_identity(
                    archive.archive_path,
                    root_fd,
                    name="accepted-risk archive",
                    private_final=True,
                )
                _require_dependency_bindings()
            finally:
                os.close(rows_fd)
        finally:
            os.close(source_fd)
    finally:
        os.close(root_fd)


def _within_repository_artifacts(path: Path, *, permit_root: bool) -> bool:
    candidate = path.absolute()
    allowed = _PINNED_REPOSITORY_ARTIFACTS_ROOT.absolute()
    try:
        within = os.path.commonpath((str(candidate), str(allowed))) == str(allowed)
    except ValueError:
        return False
    return within and (permit_root or candidate != allowed)


def build_physical_accepted_risk_archive(
    *,
    source_artifact_path: Path,
    output_root: Path,
) -> PhysicalAcceptedRiskArchive:
    """Build disk-backed C1 authority from one production Massive capture."""

    _require_dependency_bindings()
    source = Path(source_artifact_path).absolute()
    root = Path(output_root).absolute()
    if (
        not _within_repository_artifacts(source, permit_root=False)
        or not _within_repository_artifacts(root, permit_root=True)
        or root == source
        or source in root.parents
    ):
        raise PhysicalAcceptedRiskArchiveError(
            "production C1 source and output must remain in separate artifacts paths"
        )
    return _build_with_capture_visitor(
        source_artifact_path=source,
        output_root=root,
        expected_transport=_PINNED_PRODUCTION_TRANSPORT,
        visitor=_PINNED_MASSIVE_VISITOR,
    )


def _build_physical_accepted_risk_archive_for_test(
    *,
    source_artifact_path: Path,
    output_root: Path,
    visitor: Callable[..., object] | None = None,
) -> PhysicalAcceptedRiskArchive:
    """Offline seam; it can consume only the capture adapter's test marker."""

    _require_dependency_bindings()
    selected = visitor
    if selected is None:
        selected = _PINNED_MASSIVE_VISITOR
    if not callable(selected):
        raise PhysicalAcceptedRiskArchiveError(
            "Massive exhaustive physical visitor is unavailable"
        )
    return _build_with_capture_visitor(
        source_artifact_path=Path(source_artifact_path).absolute(),
        output_root=Path(output_root).absolute(),
        expected_transport=_PINNED_TEST_TRANSPORT,
        visitor=selected,
    )


__all__ = [
    "ARCHIVE_SCHEMA",
    "AcceptedRiskShardDescriptor",
    "PhysicalAcceptedRiskArchive",
    "PhysicalAcceptedRiskArchiveCapacityError",
    "PhysicalAcceptedRiskArchiveError",
    "build_physical_accepted_risk_archive",
    "iter_physical_accepted_risk_rows",
    "load_physical_accepted_risk_archive",
    "require_physical_accepted_risk_archive",
]
