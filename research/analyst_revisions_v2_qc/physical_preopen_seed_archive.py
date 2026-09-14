"""Disk-backed ARV2 pre-open seed archive for the full physical inputs.

The legacy pre-open composer is the semantic oracle, but its aggregate bridge
and JSON documents necessarily retain the complete accepted-risk history in
memory.  This module applies the same row rules to a loader-authenticated
``PhysicalAcceptedRiskArchive`` and the capture-owned exhaustive Sharadar row
visitor.  Intermediate joins and de-duplication live in SQLite; the durable
result contains only canonical derived JSONL shards and small manifests.

The archive is deliberately inert.  It has no provider, credential,
QuantConnect, outcome, result, deployment, order, or trading capability.  It
is a seed for the outcome-free fundamental-universe discovery and for the
later reviewed historical pre-open bridge.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import secrets
import sqlite3
import stat
import threading
import weakref
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping, NoReturn, Sequence
from zoneinfo import ZoneInfo

from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskSourceRow,
    MassiveSourceRole,
    RowDisposition,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    require_identifier,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2.preopen_control_acquisition import SOURCE_VIEW_ID
from research.analyst_revisions_v2_qc import fundamental_universe_discovery as _discovery
from research.analyst_revisions_v2_qc import physical_accepted_risk_archive as _c1
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    PhysicalAcceptedRiskArchive,
    PhysicalAcceptedRiskArchiveError,
    iter_physical_accepted_risk_rows,
    require_physical_accepted_risk_archive,
)
from research.analyst_revisions_v2_qc.preopen_control_stage import (
    EARNINGS_INPUT_SCHEMA,
    FUNDAMENTAL_INPUT_SCHEMA,
    GUIDANCE_INPUT_SCHEMA,
    RATING_INPUT_SCHEMA,
)
from scripts import build_arv2_preopen_input as _legacy
from scripts import capture_arv2_sharadar as _sharadar
from scripts.capture_arv2_sharadar import (
    ACTIONS_AVAILABILITY,
    FUNDAMENTALS_ADMITTED_DIMENSION,
    FUNDAMENTALS_AVAILABILITY,
    LoadedSharadarCapture,
    SharadarCaptureError,
    SharadarDataset,
)


ARCHIVE_SCHEMA = "arv2-physical-preopen-seed-archive-v1"
ARCHIVE_MANIFEST = "manifest.json"
ARCHIVE_MANIFEST_DIGEST = "manifest.sha256"
ROW_DIRECTORY = "rows"
ACTION_CENSUS_FILENAME = "action-census.json"
COMPOSITION_REPORT_FILENAME = "composition-report.json"
QUALITY_POLICY_FILENAME = "quality-policy.json"

MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_ACTION_CENSUS_BYTES = 8 * 1024 * 1024
MAX_SHARD_BYTES = 8 * 1024 * 1024 * 1024
MAX_SPOOL_BYTES = 32 * 1024 * 1024 * 1024
MAX_ROW_BYTES = 8 * 1024 * 1024
MAX_PHYSICAL_SOURCE_ROWS = 2_000_000
IO_CHUNK_BYTES = 1024 * 1024

_PATH_TYPE = type(Path("."))
_ROLE_NAMES = {
    MassiveSourceRole.ANALYST_RATINGS: "ratings",
    MassiveSourceRole.EARNINGS: "earnings",
    MassiveSourceRole.CORPORATE_GUIDANCE: "guidance",
}
_STRUCTURAL_REFUSALS = frozenset(
    {
        RowDisposition.INVALID_PROVIDER_EVENT_ID,
        RowDisposition.INVALID_EVENT_DATE,
        RowDisposition.INVALID_EVENT_TIME,
        RowDisposition.EVENT_OUTSIDE_REQUESTED_CAPTURE_RANGE,
        RowDisposition.EVENT_OUTSIDE_EXCHANGE_CALENDAR_AUTHORITY,
        RowDisposition.INVALID_LAST_UPDATED_EXPLICIT_OFFSET,
        RowDisposition.LAST_UPDATED_AFTER_CAPTURE,
    }
)

_PINNED_REQUIRE_C1 = require_physical_accepted_risk_archive
_PINNED_ITER_C1 = iter_physical_accepted_risk_rows
_PINNED_C1_TYPE = PhysicalAcceptedRiskArchive
_PINNED_SHARADAR_VISITOR = (
    _sharadar._visit_authenticated_sharadar_capture_rows_for_bridge
)
_PINNED_SHARADAR_TYPE = LoadedSharadarCapture
_PINNED_DISCOVERY_BUILDER = (
    _discovery.build_fundamental_universe_discovery_plan_bytes
)
_PINNED_LEGACY_HELPERS = (
    _legacy._safe_component,
    _legacy._text,
    _legacy._date_text,
    _legacy._decimal_text,
    _legacy._sharadar_cusips,
    _legacy._strict_provider_row,
    _legacy._composition_terminal,
    _legacy._event_session,
    _legacy._session_axis,
    _legacy._quality_policy_bytes,
)
_PINNED_LEGACY_CONSTANTS = (
    _legacy.COMPOSER_SCHEMA,
    _legacy.COMPOSITION_REPORT_SCHEMA,
    _legacy.FIRM_REVIEW_SCHEMA,
    _legacy.UNIVERSE_ARTIFACT_SCHEMA,
    _legacy.SOURCE_SEED_CANDIDATE_SCHEMA,
    _legacy.FUNDAMENTAL_SEED_INVENTORY_SCHEMA,
    _legacy.QUALITY_POLICY_SCHEMA,
    _legacy.FROZEN_CAPTURE_FIRST_DATE,
    _legacy.FROZEN_CAPTURE_LAST_DATE,
    _legacy.FORMAL_FIRST_SESSION,
    _legacy.FORMAL_LAST_SESSION,
    _legacy.FUNDAMENTAL_SEED_AVAILABILITY,
    _legacy.STATUS_BLOCKED,
    _legacy.FULL_PIT_UNIVERSE_REFUSAL,
    _legacy.FIRM_ONTOLOGY_REFUSAL,
    tuple(sorted(_legacy._ALLOWED_COMMON_STOCK_CATEGORIES)),
    tuple(sorted(_legacy._SHARADAR_EXCHANGE_TO_MIC.items())),
)


class PhysicalPreopenSeedArchiveError(ValueError):
    """The physical inputs cannot produce or authenticate the seed archive."""


class PhysicalPreopenSeedArchiveCapacityError(PhysicalPreopenSeedArchiveError):
    """A fixed disk, row, or census bound was exceeded without truncation."""


@dataclasses.dataclass(frozen=True, slots=True)
class SeedShardDescriptor:
    role: str
    relative_path: str
    sort_order: str
    row_count: int
    byte_count: int
    content_sha256: str

    def to_record(self) -> dict[str, object]:
        return {
            "role": self.role,
            "relative_path": self.relative_path,
            "sort_order": self.sort_order,
            "row_count": self.row_count,
            "byte_count": self.byte_count,
            "content_sha256": self.content_sha256,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class SeedArtifactBinding:
    role: str
    artifact_id: str | None
    semantic_sha256: str | None
    content_sha256: str
    byte_count: int

    def to_record(self) -> dict[str, object]:
        return {
            "role": self.role,
            "artifact_id": self.artifact_id,
            "semantic_sha256": self.semantic_sha256,
            "content_sha256": self.content_sha256,
            "byte_count": self.byte_count,
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class PhysicalPreopenSeedArchive:
    schema: str
    archive_id: str
    archive_sha256: str
    archive_path: Path
    accepted_risk_archive_path: Path
    accepted_risk_archive_id: str
    accepted_risk_archive_sha256: str
    massive_source_artifact_id: str
    massive_source_manifest_sha256: str
    massive_capture_transport: str
    physical_massive_capture_id: str
    physical_massive_capture_sha256: str
    derived_massive_capture_id: str
    derived_massive_capture_sha256: str
    pair_id: str
    pair_sha256: str
    massive_source_row_count: int
    sharadar_capture_path: Path
    sharadar_manifest_sha256: str
    sharadar_capture_id: str
    sharadar_capture_sha256: str
    sharadar_capture_transport: str
    sharadar_source_row_count: int
    first_session: str
    last_session: str
    calculation_session: str
    decision_session_count: int
    candidate_id: str
    candidate_sha256: str
    blocking_refusals: tuple[str, ...]
    source_completeness: tuple[tuple[MassiveSourceRole, bool], ...]
    candidate_security_count: int
    candidate_security_session_terminal_count: int
    source_role_row_counts: tuple[tuple[str, int], ...]
    composition_terminal_count: int
    source_order_terminal_projection_sha256: str
    canonical_terminal_projection_sha256: str
    fundamental_seed_count: int
    firm_count: int
    observed_firm_label_count: int
    action_census_byte_count: int
    action_census_sha256: str
    shards: tuple[SeedShardDescriptor, ...]
    artifacts: tuple[SeedArtifactBinding, ...]
    raw_provider_rows_retained: bool
    full_history_materialized_in_memory: bool
    raw_free_derived_identity: bool
    source_inputs_reauthenticated_after_build: bool
    provider_access: bool
    credential_access: bool
    quantconnect_access: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


@dataclasses.dataclass(frozen=True, slots=True)
class _JsonArray:
    items: Callable[[], Iterator[bytes]]


_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalPreopenSeedArchive],
        tuple[object, ...],
    ],
] = {}
_AUTHORITY_LOCK = threading.RLock()


def _forget(identity: int, reference: object) -> None:
    with _AUTHORITY_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AUTHORITIES.pop(identity, None)


def _fingerprint(value: PhysicalPreopenSeedArchive) -> tuple[object, ...]:
    return tuple(getattr(value, field.name) for field in dataclasses.fields(value))


def _require_dependencies() -> None:
    try:
        changed = (
            _c1.PhysicalAcceptedRiskArchive is not _PINNED_C1_TYPE
            or _c1.require_physical_accepted_risk_archive is not _PINNED_REQUIRE_C1
            or _c1.iter_physical_accepted_risk_rows is not _PINNED_ITER_C1
            or _sharadar.LoadedSharadarCapture is not _PINNED_SHARADAR_TYPE
            or _sharadar._visit_authenticated_sharadar_capture_rows_for_bridge
            is not _PINNED_SHARADAR_VISITOR
            or _discovery.build_fundamental_universe_discovery_plan_bytes
            is not _PINNED_DISCOVERY_BUILDER
            or _PINNED_LEGACY_HELPERS
            != (
                _legacy._safe_component,
                _legacy._text,
                _legacy._date_text,
                _legacy._decimal_text,
                _legacy._sharadar_cusips,
                _legacy._strict_provider_row,
                _legacy._composition_terminal,
                _legacy._event_session,
                _legacy._session_axis,
                _legacy._quality_policy_bytes,
            )
            or _PINNED_LEGACY_CONSTANTS
            != (
                _legacy.COMPOSER_SCHEMA,
                _legacy.COMPOSITION_REPORT_SCHEMA,
                _legacy.FIRM_REVIEW_SCHEMA,
                _legacy.UNIVERSE_ARTIFACT_SCHEMA,
                _legacy.SOURCE_SEED_CANDIDATE_SCHEMA,
                _legacy.FUNDAMENTAL_SEED_INVENTORY_SCHEMA,
                _legacy.QUALITY_POLICY_SCHEMA,
                _legacy.FROZEN_CAPTURE_FIRST_DATE,
                _legacy.FROZEN_CAPTURE_LAST_DATE,
                _legacy.FORMAL_FIRST_SESSION,
                _legacy.FORMAL_LAST_SESSION,
                _legacy.FUNDAMENTAL_SEED_AVAILABILITY,
                _legacy.STATUS_BLOCKED,
                _legacy.FULL_PIT_UNIVERSE_REFUSAL,
                _legacy.FIRM_ONTOLOGY_REFUSAL,
                tuple(sorted(_legacy._ALLOWED_COMMON_STOCK_CATEGORIES)),
                tuple(sorted(_legacy._SHARADAR_EXCHANGE_TO_MIC.items())),
            )
        )
    except (AttributeError, TypeError, ValueError):
        changed = True
    if changed:
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed dependency binding changed"
        )


def _fragment(value: object) -> bytes:
    return canonical_json_bytes(value)[:-1]


def _iter_json_value(value: object) -> Iterator[bytes]:
    if type(value) is _JsonArray:
        yield b"["
        first = True
        for item in value.items():
            if type(item) is not bytes or item.endswith(b"\n"):
                raise PhysicalPreopenSeedArchiveError(
                    "streamed array item is not a canonical JSON fragment"
                )
            if not first:
                yield b","
            yield item
            first = False
        yield b"]"
        return
    yield _fragment(value)


def _iter_canonical_object(
    values: Mapping[str, object], *, terminate: bool = True
) -> Iterator[bytes]:
    if type(values) is not dict or any(type(key) is not str for key in values):
        raise PhysicalPreopenSeedArchiveError(
            "streamed object requires an exact string-keyed dict"
        )
    yield b"{"
    for offset, key in enumerate(sorted(values)):
        if offset:
            yield b","
        yield _fragment(key)
        yield b":"
        yield from _iter_json_value(values[key])
    yield b"}"
    if terminate:
        yield b"\n"


def _hash_chunks(chunks: Iterable[bytes]) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    for chunk in chunks:
        if type(chunk) is not bytes:
            raise PhysicalPreopenSeedArchiveError(
                "streamed hash received non-bytes"
            )
        digest.update(chunk)
        byte_count += len(chunk)
    return byte_count, digest.hexdigest()


def _write_private(
    path: Path, chunks: Iterable[bytes], *, maximum_bytes: int
) -> tuple[int, str]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise PhysicalPreopenSeedArchiveError(
            "seed archive private leaf could not be created"
        ) from exc
    digest = hashlib.sha256()
    byte_count = 0
    try:
        os.fchmod(descriptor, 0o600)
        for chunk in chunks:
            if type(chunk) is not bytes:
                raise PhysicalPreopenSeedArchiveError(
                    "seed archive writer received non-bytes"
                )
            byte_count += len(chunk)
            if byte_count > maximum_bytes:
                raise PhysicalPreopenSeedArchiveCapacityError(
                    "seed archive writer exceeded its fixed byte bound"
                )
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise PhysicalPreopenSeedArchiveError(
                        "seed archive writer stalled"
                    )
                view = view[written:]
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or metadata.st_size != byte_count
        ):
            raise PhysicalPreopenSeedArchiveError(
                "seed archive leaf is not a private regular file"
            )
    finally:
        os.close(descriptor)
    return byte_count, digest.hexdigest()


def _spool_bytes(connection: sqlite3.Connection) -> int:
    pages = int(connection.execute("PRAGMA page_count").fetchone()[0])
    size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    return pages * size


def _configured_spool_bound(connection: sqlite3.Connection) -> int:
    value = getattr(connection, "arv2_maximum_bytes", None)
    if type(value) is not int or value <= 0:
        raise PhysicalPreopenSeedArchiveError(
            "pre-open seed SQLite spool has no hard byte bound"
        )
    return value


def _require_spool_capacity(
    connection: sqlite3.Connection, *, maximum_bytes: int | None = None
) -> None:
    configured = _configured_spool_bound(connection)
    bound = configured if maximum_bytes is None else maximum_bytes
    if type(bound) is not int or bound <= 0 or bound > configured:
        raise PhysicalPreopenSeedArchiveError(
            "pre-open seed SQLite capacity check changed"
        )
    if _spool_bytes(connection) > bound:
        raise PhysicalPreopenSeedArchiveCapacityError(
            "pre-open seed SQLite spool exceeds its fixed byte bound"
        )


def _raise_spool_sqlite_error(error: sqlite3.Error) -> NoReturn:
    code = getattr(error, "sqlite_errorcode", None)
    message = str(error).lower()
    if (
        type(code) is int
        and code & 0xFF == getattr(sqlite3, "SQLITE_FULL", 13)
    ) or "database or disk is full" in message or "disk full" in message:
        raise PhysicalPreopenSeedArchiveCapacityError(
            "pre-open seed SQLite spool reached its hard capacity"
        ) from error
    raise error


class _BoundedSpoolConnection(sqlite3.Connection):
    """Connection translating SQLite's hard-cap signal at every write seam."""

    arv2_maximum_bytes: int

    def execute(self, sql, parameters=(), /):
        try:
            return super().execute(sql, parameters)
        except sqlite3.Error as exc:
            _raise_spool_sqlite_error(exc)

    def executemany(self, sql, parameters, /):
        try:
            return super().executemany(sql, parameters)
        except sqlite3.Error as exc:
            _raise_spool_sqlite_error(exc)

    def executescript(self, sql_script, /):
        try:
            return super().executescript(sql_script)
        except sqlite3.Error as exc:
            _raise_spool_sqlite_error(exc)

    def commit(self):
        try:
            return super().commit()
        except sqlite3.Error as exc:
            _raise_spool_sqlite_error(exc)


def _open_spool(
    path: Path, *, maximum_bytes: int = MAX_SPOOL_BYTES
) -> sqlite3.Connection:
    if type(maximum_bytes) is not int or maximum_bytes <= 0:
        raise PhysicalPreopenSeedArchiveError(
            "pre-open seed SQLite maximum must be a positive byte count"
        )
    try:
        connection = sqlite3.connect(path, factory=_BoundedSpoolConnection)
        os.chmod(path, 0o600)
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        if (
            page_size < 512
            or page_size > 65_536
            or page_size & (page_size - 1)
        ):
            raise PhysicalPreopenSeedArchiveError(
                "pre-open seed SQLite page size changed"
            )
        maximum_pages = maximum_bytes // page_size
        if maximum_pages <= 0:
            raise PhysicalPreopenSeedArchiveCapacityError(
                "pre-open seed SQLite bound cannot hold one page"
            )
        effective_bound = maximum_pages * page_size
        connection.arv2_maximum_bytes = effective_bound
        cache_kib = max(64, min(8192, effective_bound // 1024))
        journal_mode = connection.execute("PRAGMA journal_mode=OFF").fetchone()[0]
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA temp_store=FILE")
        connection.execute("PRAGMA mmap_size=0")
        connection.execute(f"PRAGMA cache_size=-{cache_kib}")
        installed_pages = int(
            connection.execute(
                f"PRAGMA max_page_count={maximum_pages}"
            ).fetchone()[0]
        )
        if (
            journal_mode != "off"
            or int(connection.execute("PRAGMA temp_store").fetchone()[0]) != 1
            or int(connection.execute("PRAGMA mmap_size").fetchone()[0]) != 0
            or installed_pages != maximum_pages
            or installed_pages * page_size > maximum_bytes
        ):
            raise PhysicalPreopenSeedArchiveError(
                "pre-open seed SQLite hard-bound configuration changed"
            )
        connection.executescript(
        """
        CREATE TABLE ticker_rows (
            ticker TEXT NOT NULL,
            security_id TEXT NOT NULL,
            issuer_id TEXT NOT NULL,
            payload BLOB NOT NULL,
            occurrences INTEGER NOT NULL,
            PRIMARY KEY (ticker, payload)
        ) WITHOUT ROWID;
        CREATE TABLE ticker_refusals (
            reason TEXT PRIMARY KEY,
            count INTEGER NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE securities (
            ticker TEXT PRIMARY KEY,
            security_id TEXT NOT NULL UNIQUE,
            issuer_id TEXT NOT NULL,
            payload BLOB NOT NULL,
            formal_first_session TEXT NOT NULL,
            formal_last_session TEXT NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE actions (
            label TEXT PRIMARY KEY,
            count INTEGER NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE facts (
            security_id TEXT NOT NULL,
            period_end TEXT NOT NULL,
            payload BLOB NOT NULL,
            occurrences INTEGER NOT NULL,
            PRIMARY KEY (security_id, period_end, payload)
        ) WITHOUT ROWID;
        CREATE TABLE fundamental_rows (
            payload BLOB PRIMARY KEY
        ) WITHOUT ROWID;
        CREATE TABLE role_rows (
            role TEXT NOT NULL,
            payload BLOB NOT NULL,
            PRIMARY KEY (role, payload)
        ) WITHOUT ROWID;
        CREATE TABLE terminals (
            source_ordinal INTEGER PRIMARY KEY,
            payload BLOB NOT NULL
        );
        CREATE INDEX terminals_payload ON terminals(payload);
        CREATE TABLE rating_sessions (
            security_id TEXT NOT NULL,
            decision_session TEXT NOT NULL,
            raw_row_sha256 TEXT NOT NULL,
            PRIMARY KEY (security_id, decision_session)
        ) WITHOUT ROWID;
        CREATE TABLE firm_names (
            firm_id TEXT NOT NULL,
            firm_name TEXT NOT NULL,
            PRIMARY KEY (firm_id, firm_name)
        ) WITHOUT ROWID;
        CREATE TABLE firm_events (
            source_ordinal INTEGER PRIMARY KEY,
            firm_id TEXT NOT NULL,
            event_date TEXT NOT NULL,
            raw_row_sha256 TEXT NOT NULL
        );
        CREATE INDEX firm_events_firm ON firm_events(firm_id, raw_row_sha256);
        CREATE TABLE firm_labels (
            firm_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            label TEXT NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY (firm_id, field_name, label)
        ) WITHOUT ROWID;
        CREATE TABLE firm_rows (
            firm_id TEXT PRIMARY KEY,
            payload BLOB NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE universe_rows (
            security_id TEXT PRIMARY KEY,
            payload BLOB NOT NULL
        ) WITHOUT ROWID;
        CREATE TABLE session_rows (
            session_ordinal INTEGER PRIMARY KEY,
            payload BLOB NOT NULL
        );
        """
        )
        _require_spool_capacity(connection)
        return connection
    except sqlite3.Error as exc:
        if "connection" in locals():
            connection.close()
        _raise_spool_sqlite_error(exc)
    except BaseException:
        if "connection" in locals():
            connection.close()
        raise


def _increment(
    connection: sqlite3.Connection, table: str, key: str, amount: int = 1
) -> None:
    if table not in {"ticker_refusals", "actions"}:
        raise PhysicalPreopenSeedArchiveError("internal census table changed")
    column = "reason" if table == "ticker_refusals" else "label"
    connection.execute(
        f"INSERT INTO {table}({column}, count) VALUES (?, ?) "
        f"ON CONFLICT({column}) DO UPDATE SET count=count+excluded.count",
        (key, amount),
    )


def _row_payload(value: Mapping[str, object]) -> bytes:
    payload = canonical_json_bytes(dict(value))
    if len(payload) > MAX_ROW_BYTES:
        raise PhysicalPreopenSeedArchiveCapacityError(
            "derived seed row exceeds its fixed byte bound"
        )
    return payload


def _sqlite_fragments(
    connection: sqlite3.Connection, query: str, parameters: Sequence[object] = ()
) -> Iterator[bytes]:
    for (payload,) in connection.execute(query, tuple(parameters)):
        if type(payload) is not bytes or not payload.endswith(b"\n"):
            raise PhysicalPreopenSeedArchiveError(
                "seed spool row is not canonical LF-terminated bytes"
            )
        yield payload[:-1]


def _sqlite_lines(
    connection: sqlite3.Connection, query: str, parameters: Sequence[object] = ()
) -> Iterator[bytes]:
    for (payload,) in connection.execute(query, tuple(parameters)):
        if type(payload) is not bytes or not payload.endswith(b"\n"):
            raise PhysicalPreopenSeedArchiveError(
                "seed spool row is not canonical LF-terminated bytes"
            )
        yield payload


def _semantic_binding(
    role: str,
    semantic: dict[str, object],
    *,
    identity_prefix: str | None,
) -> SeedArtifactBinding:
    _semantic_bytes, semantic_sha = _hash_chunks(
        _iter_canonical_object(semantic)
    )
    if identity_prefix is None:
        final = semantic
        artifact_id = None
        semantic_hash: str | None = None
    else:
        artifact_id = f"{identity_prefix}{semantic_sha[:24]}"
        semantic_hash = semantic_sha
        final = {
            **semantic,
            "artifact_id": artifact_id,
            "semantic_sha256": semantic_sha,
        }
    byte_count, content_sha = _hash_chunks(_iter_canonical_object(final))
    return SeedArtifactBinding(
        role=role,
        artifact_id=artifact_id,
        semantic_sha256=semantic_hash,
        content_sha256=content_sha,
        byte_count=byte_count,
    )


def _simple_binding(role: str, payload: bytes) -> SeedArtifactBinding:
    return SeedArtifactBinding(
        role=role,
        artifact_id=None,
        semantic_sha256=None,
        content_sha256=sha256_bytes(payload),
        byte_count=len(payload),
    )


class _BuildState:
    """Mutable, construction-only state backed by one private SQLite spool."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        c1: PhysicalAcceptedRiskArchive,
        sharadar: LoadedSharadarCapture,
    ) -> None:
        self.connection = connection
        self.c1 = c1
        self.sharadar = sharadar
        self.session_ordinals, self.session_set = _legacy._session_axis(
            _legacy.FORMAL_LAST_SESSION
        )
        self.formal_sessions = tuple(
            item
            for item in sorted(self.session_ordinals)
            if _legacy.FORMAL_FIRST_SESSION
            <= item
            <= _legacy.FORMAL_LAST_SESSION
        )
        if (
            not self.formal_sessions
            or self.formal_sessions[0] != _legacy.FORMAL_FIRST_SESSION
            or self.formal_sessions[-1] != _legacy.FORMAL_LAST_SESSION
        ):
            raise PhysicalPreopenSeedArchiveError(
                "formal NYSE session endpoints changed"
            )
        self.ticker_observed = 0
        self.tickers_finalized = False
        self.all_security_by_ticker: dict[str, dict[str, object]] = {}
        self.security_by_ticker: dict[str, dict[str, object]] = {}
        self.ticker_ambiguity_count = 0
        self.universe_interval_refusals: Counter[str] = Counter()
        self.candidate_security_session_terminal_count = 0
        self.action_invalid_count = 0
        self.action_matched_count = 0
        self.fundamental_source_rows = 0
        self.fundamental_refusals: Counter[str] = Counter()
        self.fundamental_seed_count = 0
        self.source_row_count = 0
        self.role_seen: Counter[MassiveSourceRole] = Counter()
        self.role_structural: set[MassiveSourceRole] = set()
        self.semantic_incomplete: set[MassiveSourceRole] = set()
        self.composition_dispositions: Counter[str] = Counter()
        self.terminal_hasher = hashlib.sha256(b"[")
        self.terminal_first = True
        self.terminal_projection_sha256: str | None = None
        self.firm_name_count = 0
        self.firm_label_count = 0

    def _insert_ticker(self, row: dict[str, str]) -> None:
        self.ticker_observed += 1
        if self.ticker_observed > _legacy.MAX_RETAINED_TICKER_ROWS:
            raise PhysicalPreopenSeedArchiveCapacityError(
                "TICKERS exceeds composer row bound"
            )
        try:
            table = _legacy._text(row.get("table"), "Sharadar table")
            assert table is not None
            if table.casefold() != "fundamentals":
                raise _legacy.PhysicalPreopenInputError(
                    "ticker row is outside the Sharadar fundamentals table"
                )
            ticker = _legacy._text(row.get("ticker"), "Sharadar ticker")
            assert ticker is not None
            if _legacy._TICKER.fullmatch(ticker) is None:
                raise _legacy.PhysicalPreopenInputError(
                    "Sharadar ticker is unsupported"
                )
            cusips = _legacy._sharadar_cusips(row.get("cusips"))
            permaticker = _legacy._text(
                row.get("permaticker"), "Sharadar permaticker"
            )
            category = _legacy._text(row.get("category"), "Sharadar category")
            exchange = _legacy._text(row.get("exchange"), "Sharadar exchange")
            assert permaticker is not None and category is not None
            assert exchange is not None
            if category.casefold() not in _legacy._ALLOWED_COMMON_STOCK_CATEGORIES:
                raise _legacy.PhysicalPreopenInputError(
                    "not reviewed domestic common stock"
                )
            exchange_id = _legacy._SHARADAR_EXCHANGE_TO_MIC.get(exchange.upper())
            if exchange_id is None:
                raise _legacy.PhysicalPreopenInputError(
                    "listing exchange is outside frozen XASE/XNAS/XNYS universe"
                )
            sector = _legacy._text(row.get("sector"), "Sharadar sector")
            industry = _legacy._text(row.get("industry"), "Sharadar industry")
            first = _legacy._date_text(
                row.get("firstpricedate"), "firstpricedate"
            )
            last_raw = _legacy._text(
                row.get("lastpricedate"), "lastpricedate", required=False
            )
            last = (
                None
                if last_raw is None
                else _legacy._date_text(last_raw, "lastpricedate")
            )
            figi = _legacy._text(
                row.get("figi"), "Sharadar composite FIGI", required=False
            )
            if figi is None:
                raise _legacy.PhysicalPreopenInputError(
                    "Sharadar composite FIGI is absent"
                )
            assert sector is not None and industry is not None
            source_hash = sha256_bytes(canonical_json_bytes(row))
            identity = {
                "permaticker": permaticker,
                "composite_figi": figi,
                "source_table": table,
                "ticker": ticker,
                "cusips": list(cusips),
                "exchange": exchange,
                "exchange_mic": exchange_id,
                "firstpricedate": first,
                "lastpricedate": last,
                "source_row_sha256": source_hash,
                "availability_semantics": _sharadar.TICKERS_AVAILABILITY,
            }
            classification = {
                "permaticker": permaticker,
                "sector": sector,
                "industry": industry,
                "source_row_sha256": source_hash,
                "availability_semantics": _sharadar.TICKERS_AVAILABILITY,
            }
            candidate = {
                "security_id": _legacy._safe_component(
                    "sharadar-composite-figi", figi
                ),
                "issuer_id": _legacy._safe_component(
                    "sharadar-permaticker", permaticker
                ),
                "composite_figi": figi,
                "listing_id": "sharadar-listing-"
                + sha256_bytes(canonical_json_bytes(identity))[:24],
                "ticker": ticker,
                "cusips": list(cusips),
                "exchange_id": exchange_id,
                "sector_id": _legacy._safe_component("sharadar-sector", sector),
                "industry_id": _legacy._safe_component(
                    "sharadar-industry", industry
                ),
                "first_priced_date": first,
                "last_priced_date": last,
                "source_row_sha256": source_hash,
                "identity_evidence_sha256": sha256_bytes(
                    canonical_json_bytes(identity)
                ),
                "classification_evidence_sha256": sha256_bytes(
                    canonical_json_bytes(classification)
                ),
                "non_pristine_current_snapshot": True,
            }
        except _legacy.PhysicalPreopenInputError as exc:
            _increment(self.connection, "ticker_refusals", str(exc))
            return
        payload = _row_payload(candidate)
        self.connection.execute(
            "INSERT INTO ticker_rows(ticker, security_id, issuer_id, payload, occurrences) "
            "VALUES (?, ?, ?, ?, 1) ON CONFLICT(ticker, payload) DO UPDATE SET "
            "occurrences=occurrences+1",
            (ticker, candidate["security_id"], candidate["issuer_id"], payload),
        )

    def _finalize_tickers(self) -> None:
        if self.tickers_finalized:
            return
        provisional: dict[str, tuple[dict[str, object], int]] = {}
        cursor = self.connection.execute(
            "SELECT ticker, payload, occurrences FROM ticker_rows "
            "ORDER BY ticker, payload"
        )
        current_ticker: str | None = None
        candidates: list[tuple[bytes, int]] = []

        def finish() -> None:
            nonlocal candidates, current_ticker
            if current_ticker is None:
                return
            if len(candidates) != 1:
                total = sum(item[1] for item in candidates)
                _increment(
                    self.connection,
                    "ticker_refusals",
                    "ambiguous_current_snapshot_ticker",
                    total,
                )
                self.ticker_ambiguity_count += 1
            else:
                parsed = strict_json_loads(
                    decode_utf8(candidates[0][0], "ticker candidate"),
                    "ticker candidate",
                )
                if type(parsed) is not dict:
                    raise PhysicalPreopenSeedArchiveError(
                        "ticker candidate spool row changed"
                    )
                provisional[current_ticker] = (parsed, candidates[0][1])
            candidates = []

        for ticker, payload, occurrences in cursor:
            if current_ticker is not None and ticker != current_ticker:
                finish()
            current_ticker = ticker
            candidates.append((payload, occurrences))
        finish()

        aliases: dict[tuple[str, str], list[str]] = {}
        for ticker, (candidate, _occurrences) in provisional.items():
            aliases.setdefault(
                (str(candidate["security_id"]), str(candidate["issuer_id"])), []
            ).append(ticker)
        refused_aliases: set[str] = set()
        for tickers in aliases.values():
            if len(tickers) > 1:
                refused_aliases.update(tickers)
                _increment(
                    self.connection,
                    "ticker_refusals",
                    "cross_ticker_current_snapshot_identity_alias",
                    len(tickers),
                )
                self.ticker_ambiguity_count += len(tickers)

        differences = [0] * (len(self.formal_sessions) + 1)
        seen_security_ids: set[str] = set()
        for ticker in sorted(provisional):
            if ticker in refused_aliases:
                continue
            candidate = provisional[ticker][0]
            security_id = str(candidate["security_id"])
            if security_id in seen_security_ids:
                raise PhysicalPreopenSeedArchiveError(
                    "current-snapshot security identity repeats after collision checks"
                )
            self.all_security_by_ticker[ticker] = candidate
            start = max(
                _legacy.FORMAL_FIRST_SESSION,
                str(candidate["first_priced_date"]),
            )
            last_raw = candidate["last_priced_date"]
            end = min(
                _legacy.FORMAL_LAST_SESSION,
                _legacy.FORMAL_LAST_SESSION if last_raw is None else str(last_raw),
            )
            from bisect import bisect_left, bisect_right

            first_index = bisect_left(self.formal_sessions, start)
            last_exclusive = bisect_right(self.formal_sessions, end)
            if first_index >= last_exclusive:
                self.universe_interval_refusals[
                    "no_formal_session_intersection"
                ] += 1
                continue
            seen_security_ids.add(security_id)
            differences[first_index] += 1
            differences[last_exclusive] -= 1
            universe = {
                "security_id": security_id,
                "issuer_id": candidate["issuer_id"],
                "source_composite_figi": candidate["composite_figi"],
                "listing_id": candidate["listing_id"],
                "sharadar_cusip_join_candidates": candidate["cusips"],
                "current_snapshot_ticker_display": ticker,
                "current_snapshot_listing_exchange": candidate["exchange_id"],
                "current_snapshot_sector_id": candidate["sector_id"],
                "current_snapshot_industry_id": candidate["industry_id"],
                "candidate_first_session": self.formal_sessions[first_index],
                "candidate_last_session": self.formal_sessions[last_exclusive - 1],
                "source_row_sha256": candidate["source_row_sha256"],
                "identity_evidence_sha256": candidate[
                    "identity_evidence_sha256"
                ],
                "classification_evidence_sha256": candidate[
                    "classification_evidence_sha256"
                ],
                "source_snapshot_available_at": self.sharadar.capture_completed_at,
                "qc_security_id": None,
                "mapping_status": "requires_outcome_free_qc_discovery",
                "membership_status": "review_required_current_snapshot_not_PIT",
                "point_in_time": False,
            }
            self.connection.execute(
                "INSERT INTO securities(ticker, security_id, issuer_id, payload, "
                "formal_first_session, formal_last_session) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ticker,
                    security_id,
                    candidate["issuer_id"],
                    _row_payload(candidate),
                    self.formal_sessions[first_index],
                    self.formal_sessions[last_exclusive - 1],
                ),
            )
            self.connection.execute(
                "INSERT INTO universe_rows(security_id, payload) VALUES (?, ?)",
                (security_id, _row_payload(universe)),
            )
            self.security_by_ticker[ticker] = candidate
            if len(self.security_by_ticker) > _legacy.MAX_RETAINED_TARGET_SECURITIES:
                raise PhysicalPreopenSeedArchiveCapacityError(
                    "current-snapshot universe candidate exceeds retained security bound"
                )
        if not self.security_by_ticker:
            raise PhysicalPreopenSeedArchiveError(
                "Sharadar snapshot has no unique admissible identity candidates"
            )
        active = 0
        for offset, session in enumerate(self.formal_sessions):
            active += differences[offset]
            self.candidate_security_session_terminal_count += active
            self.connection.execute(
                "INSERT INTO session_rows(session_ordinal, payload) VALUES (?, ?)",
                (
                    offset + 1,
                    _row_payload(
                        {
                            "decision_session": session,
                            "candidate_member_count": active,
                        }
                    ),
                ),
            )
        self.tickers_finalized = True

    def _insert_action(self, row: dict[str, str]) -> None:
        action = row.get("action")
        ticker = row.get("ticker")
        if (
            type(action) is str
            and action
            and action == action.strip()
            and len(action) <= 128
        ):
            _increment(self.connection, "actions", action)
            count = int(
                self.connection.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
            )
            if count > _legacy.MAX_ACTION_VOCABULARY_ENTRIES:
                raise PhysicalPreopenSeedArchiveCapacityError(
                    "ACTIONS vocabulary exceeds reviewed bound"
                )
        else:
            self.action_invalid_count += 1
        if ticker in self.security_by_ticker:
            self.action_matched_count += 1

    def _insert_fundamental(self, row: dict[str, str]) -> None:
        self.fundamental_source_rows += 1
        if self.fundamental_source_rows > _legacy.MAX_SCANNED_FUNDAMENTAL_SOURCE_ROWS:
            raise PhysicalPreopenSeedArchiveCapacityError(
                "FUNDAMENTALS exceeds composer source-row bound"
            )
        security = self.security_by_ticker.get(row.get("ticker", ""))
        if security is None:
            return
        earliest = (
            date.fromisoformat(_legacy.FORMAL_FIRST_SESSION) - timedelta(days=800)
        ).isoformat()
        try:
            if row.get("dimension") != FUNDAMENTALS_ADMITTED_DIMENSION:
                raise _legacy.PhysicalPreopenInputError("non-ART fundamental")
            period = _legacy._date_text(row.get("calendardate"), "calendardate")
            if period < earliest or period > _legacy.FORMAL_LAST_SESSION:
                return
            filing_date = _legacy._date_text(row.get("date"), "date")
            lastupdated = _legacy._date_text(row.get("lastupdated"), "lastupdated")
            sharesbas = _legacy._decimal_text(
                row.get("sharesbas"), "sharesbas", positive=True
            )
            equity_usd = _legacy._decimal_text(row.get("equityusd"), "equityusd")
            revenue_usd = _legacy._decimal_text(
                row.get("revenueusd"), "revenueusd"
            )
        except _legacy.PhysicalPreopenInputError as exc:
            self.fundamental_refusals[str(exc)] += 1
            return
        fact = {
            "calendardate": period,
            "filing_date": filing_date,
            "lastupdated": lastupdated,
            "sharesbas": sharesbas,
            "equityusd": equity_usd,
            "revenueusd": revenue_usd,
        }
        self.connection.execute(
            "INSERT INTO facts(security_id, period_end, payload, occurrences) "
            "VALUES (?, ?, ?, 1) ON CONFLICT(security_id, period_end, payload) "
            "DO UPDATE SET occurrences=occurrences+1",
            (security["security_id"], period, _row_payload(fact)),
        )

    def accept_sharadar_row(
        self,
        dataset: SharadarDataset,
        _member: object,
        _row_ordinal: int,
        row: dict[str, str],
    ) -> None:
        if dataset is SharadarDataset.TICKERS:
            if self.tickers_finalized:
                raise PhysicalPreopenSeedArchiveError(
                    "Sharadar visitor returned to TICKERS after another dataset"
                )
            self._insert_ticker(row)
        elif dataset is SharadarDataset.ACTIONS:
            self._finalize_tickers()
            self._insert_action(row)
        elif dataset is SharadarDataset.FUNDAMENTALS:
            self._finalize_tickers()
            self._insert_fundamental(row)
        else:
            raise PhysicalPreopenSeedArchiveError(
                "Sharadar visitor yielded an unreviewed dataset"
            )
        if (self.ticker_observed + self.fundamental_source_rows) % 10_000 == 0:
            _require_spool_capacity(self.connection)

    def _insert_firm_observation(
        self, source: AcceptedRiskSourceRow, source_ordinal: int
    ) -> None:
        if source.locator.source_role is not MassiveSourceRole.ANALYST_RATINGS:
            return
        try:
            row = _legacy._strict_provider_row(source)
            firm_id = require_identifier(
                row.get("benzinga_firm_id"), "benzinga_firm_id"
            )
            firm_name = _legacy._text(row.get("firm"), "firm")
            event_date = _legacy._date_text(row.get("date"), "rating date")
            assert firm_name is not None
        except (CanonicalEvidenceError, _legacy.PhysicalPreopenInputError):
            return
        inserted = self.connection.execute(
            "INSERT OR IGNORE INTO firm_names(firm_id, firm_name) VALUES (?, ?)",
            (firm_id, firm_name),
        ).rowcount
        if inserted:
            self.firm_name_count += 1
            if self.firm_name_count > _legacy.MAX_FIRM_NAME_VOCABULARY_ENTRIES:
                raise PhysicalPreopenSeedArchiveCapacityError(
                    "observed firm-name vocabulary exceeds reviewed bound"
                )
        self.connection.execute(
            "INSERT INTO firm_events(source_ordinal, firm_id, event_date, raw_row_sha256) "
            "VALUES (?, ?, ?, ?)",
            (source_ordinal, firm_id, event_date, source.locator.raw_row_sha256),
        )
        for field in ("rating", "previous_rating"):
            label = row.get(field)
            if (
                type(label) is str
                and label
                and label == label.strip()
                and len(label) <= _legacy.MAX_RETAINED_FIELD_CHARACTERS
            ):
                inserted = self.connection.execute(
                    "INSERT INTO firm_labels(firm_id, field_name, label, count) "
                    "VALUES (?, ?, ?, 1) ON CONFLICT(firm_id, field_name, label) "
                    "DO UPDATE SET count=count+1",
                    (firm_id, field, label),
                ).rowcount
                if inserted:
                    # sqlite reports one for both insert and update.  Count the
                    # exact vocabulary below after ingestion instead.
                    pass

    def accept_source_row(self, source: AcceptedRiskSourceRow) -> None:
        if type(source) is not AcceptedRiskSourceRow:
            raise PhysicalPreopenSeedArchiveError(
                "accepted-risk iterator yielded the wrong row type"
            )
        self.source_row_count += 1
        if self.source_row_count > MAX_PHYSICAL_SOURCE_ROWS:
            raise PhysicalPreopenSeedArchiveCapacityError(
                "accepted-risk source row census exceeds physical seed bound"
            )
        source_ordinal = self.source_row_count
        role = source.locator.source_role
        self.role_seen[role] += 1
        if (
            source.current_view.disposition in _STRUCTURAL_REFUSALS
            or source.censored_view.disposition in _STRUCTURAL_REFUSALS
        ):
            self.role_structural.add(role)
        self._insert_firm_observation(source, source_ordinal)
        security = self.all_security_by_ticker.get(
            source.current_restated_security_label
        )
        eligibility = source.censored_view
        output: dict[str, object] | None = None
        reason: str | None
        security_id: str | None
        if security is None:
            reason = "no_unique_admissible_Sharadar_identity"
            security_id = None
        elif eligibility.eligible_session is None or eligibility.eligible_at is None:
            reason = "source_row_has_no_authenticated_eligibility_session"
            security_id = str(security["security_id"])
        elif (
            eligibility.eligible_session < str(security["first_priced_date"])
            or (
                security["last_priced_date"] is not None
                and eligibility.eligible_session > str(security["last_priced_date"])
            )
        ):
            reason = "event_eligibility_outside_current_snapshot_listing_interval"
            security_id = str(security["security_id"])
        else:
            security_id = str(security["security_id"])
            ordinal = self.session_ordinals.get(eligibility.eligible_session)
            if ordinal is None:
                reason = "eligibility_session_outside_formal_axis"
                terminal_disposition = "outside_composer_session_axis"
                terminal = _legacy._composition_terminal(
                    source,
                    disposition=terminal_disposition,
                    reason=reason,
                    security_id=security_id,
                )
                self._store_terminal(source_ordinal, terminal)
                return
            raw = _legacy._strict_provider_row(source)
            reason = "excluded_from_conservative_censored_view"
            if role is MassiveSourceRole.ANALYST_RATINGS:
                analyst = raw.get("benzinga_analyst_id")
                firm = raw.get("benzinga_firm_id")
                try:
                    analyst_id = require_identifier(
                        analyst, "benzinga_analyst_id"
                    )
                    firm_id = require_identifier(firm, "benzinga_firm_id")
                except CanonicalEvidenceError:
                    analyst_id = firm_id = None
                admitted = (
                    eligibility.included
                    and analyst_id is not None
                    and firm_id is not None
                    and source.provider_event_id is not None
                )
                suffix = source.locator.raw_row_sha256[:24]
                output = {
                    "schema": RATING_INPUT_SCHEMA,
                    "security_id": security_id,
                    "source_view_id": SOURCE_VIEW_ID,
                    "admitted": admitted,
                    "eligible_session_ordinal": ordinal,
                    "available_at": eligibility.eligible_at,
                    "analyst_id": (
                        analyst_id if admitted else f"refused-analyst-{suffix}"
                    ),
                    "institution_id": (
                        firm_id if admitted else f"refused-firm-{suffix}"
                    ),
                    "common_event_id": (
                        _legacy._safe_component(
                            "benzinga-event", source.provider_event_id
                        )
                        if source.provider_event_id is not None
                        else f"refused-event-{suffix}"
                    ),
                }
                if admitted:
                    reason = "emitted_admitted_rating"
                elif eligibility.included:
                    reason = (
                        "potentially_relevant_rating_missing_or_invalid_stable_"
                        "analyst_or_firm_identifier"
                    )
                    self.semantic_incomplete.add(role)
                else:
                    reason = "emitted_nonadmitted_conservative_censor_terminal"
                current = source.current_view
                if (
                    current.included
                    and current.eligible_session is not None
                    and str(security["first_priced_date"])
                    <= current.eligible_session
                    and (
                        security["last_priced_date"] is None
                        or current.eligible_session
                        <= str(security["last_priced_date"])
                    )
                ):
                    self.connection.execute(
                        "INSERT OR IGNORE INTO rating_sessions("
                        "security_id, decision_session, raw_row_sha256) "
                        "VALUES (?, ?, ?)",
                        (
                            security_id,
                            current.eligible_session,
                            source.locator.raw_row_sha256,
                        ),
                    )
            elif role is MassiveSourceRole.EARNINGS:
                if eligibility.included and source.event_date is not None:
                    try:
                        report_session = _legacy._event_session(
                            source.event_date, self.session_set
                        )
                        output = {
                            "schema": EARNINGS_INPUT_SCHEMA,
                            "security_id": security_id,
                            "report_session_ordinal": self.session_ordinals[
                                report_session
                            ],
                            "available_at": eligibility.eligible_at,
                        }
                        reason = "emitted_conservative_censored_earnings"
                    except (KeyError, _legacy.PhysicalPreopenInputError):
                        reason = "earnings_report_session_unresolved"
                        self.semantic_incomplete.add(role)
            else:
                if eligibility.included:
                    output = {
                        "schema": GUIDANCE_INPUT_SCHEMA,
                        "security_id": security_id,
                        "eligible_session_ordinal": ordinal,
                        "available_at": eligibility.eligible_at,
                    }
                    reason = "emitted_conservative_censored_guidance"
        terminal_disposition = "named_refusal"
        if output is not None:
            payload = _row_payload(output)
            inserted = self.connection.execute(
                "INSERT OR IGNORE INTO role_rows(role, payload) VALUES (?, ?)",
                (_ROLE_NAMES[role], payload),
            ).rowcount
            terminal_disposition = (
                "emitted" if inserted else "coalesced_exact_control_anchor"
            )
        terminal = _legacy._composition_terminal(
            source,
            disposition=terminal_disposition,
            reason=reason,
            security_id=security_id,
        )
        self._store_terminal(source_ordinal, terminal)
        if self.source_row_count % 10_000 == 0:
            _require_spool_capacity(self.connection)

    def _store_terminal(
        self, source_ordinal: int, terminal: dict[str, object]
    ) -> None:
        payload = _row_payload(terminal)
        self.connection.execute(
            "INSERT INTO terminals(source_ordinal, payload) VALUES (?, ?)",
            (source_ordinal, payload),
        )
        disposition = terminal["preopen_composition_disposition"]
        assert type(disposition) is str
        self.composition_dispositions[disposition] += 1
        if not self.terminal_first:
            self.terminal_hasher.update(b",")
        self.terminal_hasher.update(payload[:-1])
        self.terminal_first = False

    def finish_source_rows(self) -> None:
        if (
            self.source_row_count != self.c1.source_row_count
            or tuple((role, self.role_seen[role]) for role in MassiveSourceRole)
            != self.c1.role_row_counts
        ):
            raise PhysicalPreopenSeedArchiveError(
                "accepted-risk iterator did not exhaust its authenticated role census"
            )
        self.terminal_hasher.update(b"]\n")
        self.terminal_projection_sha256 = self.terminal_hasher.hexdigest()
        self.firm_label_count = int(
            self.connection.execute("SELECT COUNT(*) FROM firm_labels").fetchone()[0]
        )
        if self.firm_label_count > _legacy.MAX_FIRM_VOCABULARY_ENTRIES:
            raise PhysicalPreopenSeedArchiveCapacityError(
                "observed firm vocabulary exceeds reviewed bound"
            )
        self.connection.commit()
        _require_spool_capacity(self.connection)

    def derive_fundamentals(self) -> None:
        current_security: str | None = None
        period_rows: dict[str, list[tuple[bytes, int]]] = {}

        def finish_security() -> None:
            nonlocal period_rows, current_security
            if current_security is None:
                return
            unique: dict[str, dict[str, str]] = {}
            for period, candidates in period_rows.items():
                if len(candidates) != 1:
                    self.fundamental_refusals[
                        "conflicting_ART_rows_for_period"
                    ] += sum(count for _payload, count in candidates)
                    continue
                parsed = strict_json_loads(
                    decode_utf8(candidates[0][0], "ART fact"), "ART fact"
                )
                if type(parsed) is not dict or any(
                    type(item) is not str for item in parsed.values()
                ):
                    raise PhysicalPreopenSeedArchiveError(
                        "ART fact spool row changed"
                    )
                unique[period] = parsed
            for period in sorted(unique):
                current = unique[period]
                parsed_date = date.fromisoformat(period)
                try:
                    prior_key = parsed_date.replace(
                        year=parsed_date.year - 1
                    ).isoformat()
                except ValueError:
                    self.fundamental_refusals[
                        "noncomparable_prior_fiscal_year"
                    ] += 1
                    continue
                prior = unique.get(prior_key)
                if prior is None:
                    self.fundamental_refusals[
                        "missing_comparable_prior_fiscal_year"
                    ] += 1
                    continue
                available_date = date.fromisoformat(
                    max(current["filing_date"], current["lastupdated"])
                ) + timedelta(days=1)
                output = {
                    "schema": FUNDAMENTAL_INPUT_SCHEMA,
                    "security_id": current_security,
                    "period_end": period,
                    "available_at": (
                        f"{available_date.isoformat()}T12:00:00.000000Z"
                    ),
                    "shares_outstanding": _legacy._decimal_text(
                        current["sharesbas"], "sharesbas", positive=True
                    ),
                    "book_equity_usd": _legacy._decimal_text(
                        current["equityusd"], "equityusd"
                    ),
                    "revenue_ttm_usd": _legacy._decimal_text(
                        current["revenueusd"], "revenueusd"
                    ),
                    "prior_fiscal_year_revenue_ttm_usd": (
                        _legacy._decimal_text(
                            prior["revenueusd"], "prior revenueusd"
                        )
                    ),
                }
                self.connection.execute(
                    "INSERT OR IGNORE INTO fundamental_rows(payload) VALUES (?)",
                    (_row_payload(output),),
                )
            period_rows = {}

        cursor = self.connection.execute(
            "SELECT security_id, period_end, payload, occurrences FROM facts "
            "ORDER BY security_id, period_end, payload"
        )
        for security_id, period, payload, occurrences in cursor:
            if current_security is not None and security_id != current_security:
                finish_security()
            current_security = security_id
            period_rows.setdefault(period, []).append((payload, occurrences))
        finish_security()
        self.fundamental_seed_count = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM fundamental_rows"
            ).fetchone()[0]
        )
        if self.fundamental_seed_count > _legacy.MAX_RETAINED_DERIVED_ROWS:
            raise PhysicalPreopenSeedArchiveCapacityError(
                "derived fundamental rows exceed retained bound"
            )
        self.connection.commit()

    def derive_firm_rows(self) -> None:
        for (firm_id,) in self.connection.execute(
            "SELECT firm_id FROM firm_names ORDER BY firm_id"
        ):
            names = [
                name
                for (name,) in self.connection.execute(
                    "SELECT firm_name FROM firm_names WHERE firm_id=? "
                    "ORDER BY firm_name",
                    (firm_id,),
                )
            ]
            first, last, count = self.connection.execute(
                "SELECT MIN(event_date), MAX(event_date), COUNT(*) FROM firm_events "
                "WHERE firm_id=?",
                (firm_id,),
            ).fetchone()
            hashes = [
                raw_hash
                for (raw_hash,) in self.connection.execute(
                    "SELECT raw_row_sha256 FROM firm_events WHERE firm_id=? "
                    "ORDER BY raw_row_sha256",
                    (firm_id,),
                )
            ]
            labels = [
                {
                    "field": field,
                    "raw_label": label,
                    "observed_count": observed,
                }
                for field, label, observed in self.connection.execute(
                    "SELECT field_name, label, count FROM firm_labels "
                    "WHERE firm_id=? ORDER BY field_name, label",
                    (firm_id,),
                )
            ]
            row = {
                "provider_firm_id": firm_id,
                "observed_firm_names": names,
                "first_event_date": first,
                "last_event_date": last,
                "source_row_count": count,
                "source_row_projection_sha256": sha256_bytes(
                    canonical_json_bytes(hashes)
                ),
                "observed_labels": labels,
                "ordered_scale": None,
                "scope": None,
            }
            self.connection.execute(
                "INSERT INTO firm_rows(firm_id, payload) VALUES (?, ?)",
                (firm_id, _row_payload(row)),
            )
        self.connection.commit()

    def source_completeness(self) -> dict[MassiveSourceRole, bool]:
        exact_range = (
            self.c1.requested_first_event_date == _legacy.FROZEN_CAPTURE_FIRST_DATE
            and self.c1.requested_last_event_date
            == _legacy.FROZEN_CAPTURE_LAST_DATE
        )
        return {
            role: (
                exact_range
                and self.role_seen[role] > 0
                and role not in self.role_structural
                and role not in self.semantic_incomplete
            )
            for role in MassiveSourceRole
        }

    def action_census(self) -> dict[str, object]:
        return {
            "availability_semantics": ACTIONS_AVAILABILITY,
            "action_counts": {
                label: count
                for label, count in self.connection.execute(
                    "SELECT label, count FROM actions ORDER BY label"
                )
            },
            "invalid_action_label_row_count": self.action_invalid_count,
            "target_ticker_discovery_row_count": self.action_matched_count,
            "used_for_identity_or_payoff": False,
        }


def _visit_sharadar(
    state: _BuildState, *, expected_transport: str
) -> LoadedSharadarCapture:
    try:
        loaded = _PINNED_SHARADAR_VISITOR(
            state.sharadar.artifact_path,
            expected_transport=expected_transport,
            visit_row=state.accept_sharadar_row,
        )
    except SharadarCaptureError as exc:
        raise PhysicalPreopenSeedArchiveError(
            "Sharadar source failed exhaustive seed visitation"
        ) from exc
    if loaded != state.sharadar:
        raise PhysicalPreopenSeedArchiveError(
            "Sharadar capture changed after loader authentication"
        )
    state._finalize_tickers()
    state.connection.commit()
    return loaded


def _visit_c1(state: _BuildState) -> None:
    try:
        for row in _PINNED_ITER_C1(state.c1):
            state.accept_source_row(row)
    except PhysicalAcceptedRiskArchiveError as exc:
        raise PhysicalPreopenSeedArchiveError(
            "accepted-risk source failed exhaustive seed visitation"
        ) from exc
    state.finish_source_rows()


def _array_hash(items: Callable[[], Iterator[bytes]]) -> str:
    def chunks() -> Iterator[bytes]:
        yield from _iter_json_value(_JsonArray(items))
        yield b"\n"

    return _hash_chunks(chunks())[1]


def _write_shards(
    stage: Path, state: _BuildState
) -> tuple[SeedShardDescriptor, ...]:
    rows = stage / ROW_DIRECTORY
    rows.mkdir(mode=0o700)
    definitions = (
        (
            "universe_candidates",
            "universe-candidates.jsonl",
            "security_id",
            "SELECT payload FROM universe_rows ORDER BY security_id",
            (),
        ),
        (
            "session_counts",
            "session-counts.jsonl",
            "decision_session_ordinal",
            "SELECT payload FROM session_rows ORDER BY session_ordinal",
            (),
        ),
        (
            "earnings",
            "earnings.jsonl",
            "canonical_json_bytes",
            "SELECT payload FROM role_rows WHERE role=? ORDER BY payload",
            ("earnings",),
        ),
        (
            "guidance",
            "guidance.jsonl",
            "canonical_json_bytes",
            "SELECT payload FROM role_rows WHERE role=? ORDER BY payload",
            ("guidance",),
        ),
        (
            "ratings",
            "ratings.jsonl",
            "canonical_json_bytes",
            "SELECT payload FROM role_rows WHERE role=? ORDER BY payload",
            ("ratings",),
        ),
        (
            "composition_terminals",
            "composition-terminals.jsonl",
            "canonical_json_bytes",
            "SELECT payload FROM terminals ORDER BY payload",
            (),
        ),
        (
            "fundamental_seeds",
            "fundamental-seeds.jsonl",
            "canonical_json_bytes",
            "SELECT payload FROM fundamental_rows ORDER BY payload",
            (),
        ),
        (
            "firm_rows",
            "firm-rows.jsonl",
            "provider_firm_id",
            "SELECT payload FROM firm_rows ORDER BY firm_id",
            (),
        ),
    )
    descriptors: list[SeedShardDescriptor] = []
    for role, filename, sort_order, query, parameters in definitions:
        count = int(
            state.connection.execute(
                f"SELECT COUNT(*) FROM ({query})", tuple(parameters)
            ).fetchone()[0]
        )
        byte_count, digest = _write_private(
            rows / filename,
            _sqlite_lines(state.connection, query, parameters),
            maximum_bytes=MAX_SHARD_BYTES,
        )
        descriptors.append(
            SeedShardDescriptor(
                role=role,
                relative_path=f"{ROW_DIRECTORY}/{filename}",
                sort_order=sort_order,
                row_count=count,
                byte_count=byte_count,
                content_sha256=digest,
            )
        )
    return tuple(descriptors)


def _firm_binding(state: _BuildState) -> SeedArtifactBinding:
    firm_count = int(
        state.connection.execute("SELECT COUNT(*) FROM firm_rows").fetchone()[0]
    )
    semantic = {
        "schema": _legacy.FIRM_REVIEW_SCHEMA,
        "status": "review_required_not_authority",
        "massive_bridge_id": state.c1.archive_id,
        "massive_bridge_sha256": state.c1.archive_sha256,
        "firm_count": firm_count,
        "observed_label_count": state.firm_label_count,
        "firms": _JsonArray(
            lambda: _sqlite_fragments(
                state.connection,
                "SELECT payload FROM firm_rows ORDER BY firm_id",
            )
        ),
        "ordering_inferred": False,
        "ontology_reviewed": False,
        "production_authority": False,
        "outcomes_used": False,
    }
    _size, semantic_sha = _hash_chunks(_iter_canonical_object(semantic))
    artifact_id = f"arv2-firm-vocabulary-{semantic_sha[:24]}"
    final = {
        **semantic,
        "candidate_id": artifact_id,
        "candidate_semantic_sha256": semantic_sha,
    }
    byte_count, content_sha = _hash_chunks(_iter_canonical_object(final))
    return SeedArtifactBinding(
        role="firm_review_candidate",
        artifact_id=artifact_id,
        semantic_sha256=semantic_sha,
        content_sha256=content_sha,
        byte_count=byte_count,
    )


def _universe_binding(state: _BuildState) -> SeedArtifactBinding:
    security_count = len(state.security_by_ticker)
    semantic = {
        "schema": _legacy.UNIVERSE_ARTIFACT_SCHEMA,
        "status": _legacy.STATUS_BLOCKED,
        "blocking_refusal": _legacy.FULL_PIT_UNIVERSE_REFUSAL,
        "sharadar_capture_id": state.sharadar.capture_id,
        "sharadar_capture_sha256": state.sharadar.capture_sha256,
        "source_snapshot_available_at": state.sharadar.capture_completed_at,
        "tickers_availability_semantics": _sharadar.TICKERS_AVAILABILITY,
        "formal_first_session": state.formal_sessions[0],
        "formal_last_session": state.formal_sessions[-1],
        "formal_session_count": len(state.formal_sessions),
        "candidate_security_count": security_count,
        "candidate_security_session_terminal_count": (
            state.candidate_security_session_terminal_count
        ),
        "candidate_security_rows": _JsonArray(
            lambda: _sqlite_fragments(
                state.connection,
                "SELECT payload FROM universe_rows ORDER BY security_id",
            )
        ),
        "candidate_member_count_by_session": _JsonArray(
            lambda: _sqlite_fragments(
                state.connection,
                "SELECT payload FROM session_rows ORDER BY session_ordinal",
            )
        ),
        "interval_refusal_counts": dict(
            sorted(state.universe_interval_refusals.items())
        ),
        "candidate_listing_exchanges": ["XASE", "XNAS", "XNYS"],
        "candidate_category_filter": sorted(
            _legacy._ALLOWED_COMMON_STOCK_CATEGORIES
        ),
        "membership_interval_inferred_from_current_snapshot": True,
        "US_incorporation_point_in_time_established": False,
        "excluded_instrument_vocabulary_point_in_time_established": False,
        "historical_membership_availability_established": False,
        "historical_classification_availability_established": False,
        "full_market_peer_census_established": False,
        "qc_sid_values_present": False,
        "pristine_point_in_time": False,
        "outcomes_used": False,
    }
    return _semantic_binding(
        "eligible_universe_artifact",
        semantic,
        identity_prefix="arv2-universe-review-",
    )


def _source_seed_binding(
    state: _BuildState,
    completeness: Mapping[MassiveSourceRole, bool],
) -> SeedArtifactBinding:
    counts = {
        role: int(
            state.connection.execute(
                "SELECT COUNT(*) FROM role_rows WHERE role=?", (role,)
            ).fetchone()[0]
        )
        for role in ("earnings", "guidance", "ratings")
    }
    terminal_count = int(
        state.connection.execute("SELECT COUNT(*) FROM terminals").fetchone()[0]
    )
    role_values = {
        role: _JsonArray(
            lambda selected=role: _sqlite_fragments(
                state.connection,
                "SELECT payload FROM role_rows WHERE role=? ORDER BY payload",
                (selected,),
            )
        )
        for role in ("earnings", "guidance", "ratings")
    }
    semantic = {
        "schema": _legacy.SOURCE_SEED_CANDIDATE_SCHEMA,
        "status": "review_candidate_not_preopen_input_authority",
        "massive_bridge_id": state.c1.archive_id,
        "massive_bridge_sha256": state.c1.archive_sha256,
        "source_view_id": SOURCE_VIEW_ID,
        "role_candidates": role_values,
        "composition_terminals": _JsonArray(
            lambda: _sqlite_fragments(
                state.connection, "SELECT payload FROM terminals ORDER BY payload"
            )
        ),
        "role_candidate_counts": counts,
        "terminal_count": terminal_count,
        "source_completeness": {
            role.value: completeness[role] for role in MassiveSourceRole
        },
        "caller_authored_completeness_accepted": False,
        "point_in_time_claimed": False,
        "outcomes_used": False,
    }
    # _JsonArray values also occur one level beneath role_candidates.  Stream
    # that nested object explicitly so canonical ordering remains byte-exact.
    def role_candidates_chunks() -> Iterator[bytes]:
        yield from _iter_canonical_object(
            role_values, terminate=False
        )

    class _RawObject:
        pass

    # Reuse the generic stream by constructing the role-candidate object as a
    # tiny custom JSON value.  _stream_source_seed below handles this one
    # nested streaming object; all other values use _iter_json_value.
    semantic["role_candidates"] = (role_candidates_chunks, _RawObject)

    def stream(values: dict[str, object]) -> Iterator[bytes]:
        yield b"{"
        for offset, key in enumerate(sorted(values)):
            if offset:
                yield b","
            yield _fragment(key)
            yield b":"
            item = values[key]
            if (
                key == "role_candidates"
                and type(item) is tuple
                and len(item) == 2
                and item[1] is _RawObject
            ):
                yield from item[0]()  # type: ignore[index,operator]
            else:
                yield from _iter_json_value(item)
        yield b"}\n"

    _size, semantic_sha = _hash_chunks(stream(semantic))
    artifact_id = f"arv2-source-seed-review-{semantic_sha[:24]}"
    final = {
        **semantic,
        "artifact_id": artifact_id,
        "semantic_sha256": semantic_sha,
    }
    byte_count, content_sha = _hash_chunks(stream(final))
    return SeedArtifactBinding(
        role="source_seed_candidate",
        artifact_id=artifact_id,
        semantic_sha256=semantic_sha,
        content_sha256=content_sha,
        byte_count=byte_count,
    )


def _fundamental_binding(state: _BuildState) -> SeedArtifactBinding:
    projection_sha = _hash_chunks(
        _sqlite_lines(
            state.connection,
            "SELECT payload FROM fundamental_rows ORDER BY payload",
        )
    )[1]
    semantic = {
        "schema": _legacy.FUNDAMENTAL_SEED_INVENTORY_SCHEMA,
        "status": "deterministic_seed_inventory_not_preopen_input_authority",
        "sharadar_capture_id": state.sharadar.capture_id,
        "sharadar_capture_sha256": state.sharadar.capture_sha256,
        "availability_semantics": _legacy.FUNDAMENTAL_SEED_AVAILABILITY,
        "source_availability_semantics": FUNDAMENTALS_AVAILABILITY,
        "seed_count": state.fundamental_seed_count,
        "seed_projection_sha256": projection_sha,
        "seed_rows": _JsonArray(
            lambda: _sqlite_fragments(
                state.connection,
                "SELECT payload FROM fundamental_rows ORDER BY payload",
            )
        ),
        "refusal_counts": dict(sorted(state.fundamental_refusals.items())),
        "caller_authored_PIT_claim_accepted": False,
        "outcomes_used": False,
    }
    return _semantic_binding(
        "fundamental_seed_inventory",
        semantic,
        identity_prefix="arv2-fundamental-seeds-",
    )


def _rating_session_projection(state: _BuildState) -> str:
    def rows() -> Iterator[bytes]:
        for security_id, session, raw_hash in state.connection.execute(
            "SELECT security_id, decision_session, raw_row_sha256 "
            "FROM rating_sessions ORDER BY security_id, decision_session"
        ):
            yield _fragment(
                {
                    "security_id": security_id,
                    "decision_session": session,
                    "raw_row_sha256": raw_hash,
                }
            )

    return _array_hash(rows)


def _artifact_map(
    artifacts: Sequence[SeedArtifactBinding],
) -> dict[str, SeedArtifactBinding]:
    result = {item.role: item for item in artifacts}
    if len(result) != len(artifacts):
        raise PhysicalPreopenSeedArchiveError("seed artifact roles repeat")
    return result


def _composition_report(
    state: _BuildState,
    completeness: Mapping[MassiveSourceRole, bool],
    artifacts: Sequence[SeedArtifactBinding],
    action_census: dict[str, object],
) -> bytes:
    by_role = _artifact_map(artifacts)
    ticker_census = {
        reason: count
        for reason, count in state.connection.execute(
            "SELECT reason, count FROM ticker_refusals ORDER BY reason"
        )
    }
    role_counts = {
        role: int(
            state.connection.execute(
                "SELECT COUNT(*) FROM role_rows WHERE role=?", (role,)
            ).fetchone()[0]
        )
        for role in ("earnings", "guidance", "ratings")
    }
    terminal_count = int(
        state.connection.execute("SELECT COUNT(*) FROM terminals").fetchone()[0]
    )
    report = {
        "schema": _legacy.COMPOSITION_REPORT_SCHEMA,
        "status": _legacy.STATUS_BLOCKED,
        "blocking_refusals": [],  # Filled by the caller below.
        "massive_bridge_id": state.c1.archive_id,
        "massive_bridge_sha256": state.c1.archive_sha256,
        "pair_id": state.c1.pair_id,
        "pair_sha256": state.c1.pair_sha256,
        "derived_capture_id": state.c1.capture_id,
        "derived_capture_sha256": state.c1.capture_sha256,
        "sharadar_capture_id": state.sharadar.capture_id,
        "sharadar_capture_sha256": state.sharadar.capture_sha256,
        "fixed_capture_range": [
            _legacy.FROZEN_CAPTURE_FIRST_DATE,
            _legacy.FROZEN_CAPTURE_LAST_DATE,
        ],
        "formal_filter_range": [
            _legacy.FORMAL_FIRST_SESSION,
            _legacy.FORMAL_LAST_SESSION,
        ],
        "source_completeness_semantics": (
            "complete_for_exact_frozen_event_date_query_and_accepted_risk_"
            "policy_only_never_pristine_or_complete_version_history"
        ),
        "source_completeness": {
            role.value: completeness[role] for role in MassiveSourceRole
        },
        "massive_source_row_count": state.source_row_count,
        "massive_composition_terminal_count": terminal_count,
        "massive_composition_terminal_projection_sha256": (
            state.terminal_projection_sha256
        ),
        "composition_disposition_counts": dict(
            sorted(state.composition_dispositions.items())
        ),
        "rating_current_view_security_session_candidate_count": int(
            state.connection.execute(
                "SELECT COUNT(*) FROM rating_sessions"
            ).fetchone()[0]
        ),
        "rating_current_view_security_session_projection_sha256": (
            _rating_session_projection(state)
        ),
        "ticker_candidate_refusal_counts": ticker_census,
        "ticker_ambiguity_count": state.ticker_ambiguity_count,
        "universe_interval_refusal_counts": dict(
            sorted(state.universe_interval_refusals.items())
        ),
        "current_snapshot_universe_security_count": len(state.security_by_ticker),
        "current_snapshot_security_session_candidate_count": (
            state.candidate_security_session_terminal_count
        ),
        "fundamental_seed_count": state.fundamental_seed_count,
        "fundamental_refusal_counts": dict(
            sorted(state.fundamental_refusals.items())
        ),
        "action_discovery_census": action_census,
        "preopen_role_status": {
            "universe": "blocked_full_PIT_security_session_census_unavailable",
            "sid_mapping": "current_snapshot_null_QC_SID_discovery_candidates_only",
            "fundamentals": "deterministic_ART_seed_inventory_only",
            "earnings": "accepted_risk_seed_review_candidate_only",
            "guidance": "accepted_risk_seed_review_candidate_only",
            "ratings": "accepted_risk_seed_review_candidate_only",
        },
        "source_seed_candidate_sha256": by_role[
            "source_seed_candidate"
        ].content_sha256,
        "fundamental_seed_inventory_sha256": by_role[
            "fundamental_seed_inventory"
        ].content_sha256,
        "firm_review_candidate_sha256": by_role[
            "firm_review_candidate"
        ].content_sha256,
        "eligible_universe_artifact_sha256": by_role[
            "eligible_universe_artifact"
        ].content_sha256,
        "q_data_policy_sha256": by_role["quality_policy"].content_sha256,
        "q_data_value_until_reviewed_identity_and_firm_evidence": "0",
        "firm_ontology_status": "review_required_not_authority",
        "firm_ontology_order_inferred": False,
        "tickers_availability_semantics": _sharadar.TICKERS_AVAILABILITY,
        "fundamentals_availability_semantics": (
            _legacy.FUNDAMENTAL_SEED_AVAILABILITY
        ),
        "sharadar_fundamentals_source_availability_semantics": (
            FUNDAMENTALS_AVAILABILITY
        ),
        "actions_availability_semantics": ACTIONS_AVAILABILITY,
        "historical_membership_availability_established": False,
        "historical_classification_availability_established": False,
        "full_pit_universe_established": False,
        "full_market_peer_census_established": False,
        "qc_sid_values_present": False,
        "six_preopen_roles_produced": False,
        "closed_input_manifest_constructed": False,
        "run_authority_candidate_constructed": False,
        "production_preopen_input_available": False,
        "pristine_point_in_time": False,
        "outcome_access_performed": False,
        "quantconnect_io_performed": False,
    }
    report["blocking_refusals"] = list(_blocking_refusals(completeness))
    payload = canonical_json_bytes(report)
    if len(payload) > MAX_MANIFEST_BYTES:
        raise PhysicalPreopenSeedArchiveCapacityError(
            "physical composition report exceeds its fixed byte bound"
        )
    return payload


def _blocking_refusals(
    completeness: Mapping[MassiveSourceRole, bool],
) -> tuple[str, ...]:
    values = [
        _legacy.FULL_PIT_UNIVERSE_REFUSAL,
        _legacy.FIRM_ONTOLOGY_REFUSAL,
    ]
    values.extend(
        f"{role.value}_source_not_complete_for_frozen_query_and_accepted_risk_policy"
        for role in MassiveSourceRole
        if completeness[role] is not True
    )
    return tuple(values)


def _candidate_record(
    state: _BuildState,
    completeness: Mapping[MassiveSourceRole, bool],
    blocking: tuple[str, ...],
    artifacts: Sequence[SeedArtifactBinding],
) -> dict[str, object]:
    by_role = _artifact_map(artifacts)
    return {
        "schema": _legacy.COMPOSER_SCHEMA,
        "status": _legacy.STATUS_BLOCKED,
        "massive_bridge_id": state.c1.archive_id,
        "massive_bridge_sha256": state.c1.archive_sha256,
        "pair_id": state.c1.pair_id,
        "pair_sha256": state.c1.pair_sha256,
        "derived_capture_id": state.c1.capture_id,
        "derived_capture_sha256": state.c1.capture_sha256,
        "sharadar_capture_id": state.sharadar.capture_id,
        "sharadar_capture_sha256": state.sharadar.capture_sha256,
        "first_session": _legacy.FORMAL_FIRST_SESSION,
        "last_session": _legacy.FORMAL_LAST_SESSION,
        "calculation_session": _legacy.resolve_nth_session_after(
            _legacy.FORMAL_LAST_SESSION, 1
        ),
        "blocking_refusals": list(blocking),
        "closed_input_manifest_sha256": None,
        "run_authority_candidate_sha256": None,
        "firm_review_candidate_sha256": by_role[
            "firm_review_candidate"
        ].content_sha256,
        "composition_report_sha256": by_role[
            "composition_report"
        ].content_sha256,
        "eligible_universe_artifact_sha256": by_role[
            "eligible_universe_artifact"
        ].content_sha256,
        "source_seed_candidate_sha256": by_role[
            "source_seed_candidate"
        ].content_sha256,
        "fundamental_seed_inventory_sha256": by_role[
            "fundamental_seed_inventory"
        ].content_sha256,
        "quality_policy_sha256": by_role["quality_policy"].content_sha256,
        "rating_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness[MassiveSourceRole.ANALYST_RATINGS]
        ),
        "earnings_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness[MassiveSourceRole.EARNINGS]
        ),
        "guidance_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness[MassiveSourceRole.CORPORATE_GUIDANCE]
        ),
        "firm_ontology_reviewed": False,
        "sharadar_tickers_pristine_point_in_time": False,
        "full_pit_universe_established": False,
        "full_market_peer_census_established": False,
        "six_preopen_roles_produced": False,
        "production_preopen_input_available": False,
        "actions_used_for_identity_or_payoff": False,
        "outcome_access_performed": False,
        "quantconnect_io_performed": False,
    }


def _archive_seed(
    *,
    state: _BuildState,
    blocking: tuple[str, ...],
    completeness: Mapping[MassiveSourceRole, bool],
    candidate_id: str,
    candidate_sha256: str,
    action_census_byte_count: int,
    action_census_sha256: str,
    shards: Sequence[SeedShardDescriptor],
    artifacts: Sequence[SeedArtifactBinding],
    canonical_terminal_projection_sha256: str,
) -> dict[str, object]:
    role_counts = {
        role: int(
            state.connection.execute(
                "SELECT COUNT(*) FROM role_rows WHERE role=?", (role,)
            ).fetchone()[0]
        )
        for role in ("earnings", "guidance", "ratings")
    }
    sharadar_rows = sum(item.row_count for item in state.sharadar.archives)
    firm_count = int(
        state.connection.execute("SELECT COUNT(*) FROM firm_rows").fetchone()[0]
    )
    assert state.terminal_projection_sha256 is not None
    return {
        "schema": ARCHIVE_SCHEMA,
        "accepted_risk": {
            "archive_id": state.c1.archive_id,
            "archive_sha256": state.c1.archive_sha256,
            "source_artifact_id": state.c1.source_artifact_id,
            "source_manifest_sha256": state.c1.source_manifest_sha256,
            "capture_transport": state.c1.capture_transport,
            "physical_capture_id": state.c1.physical_capture_id,
            "physical_capture_sha256": state.c1.physical_capture_sha256,
            "derived_capture_id": state.c1.capture_id,
            "derived_capture_sha256": state.c1.capture_sha256,
            "pair_id": state.c1.pair_id,
            "pair_sha256": state.c1.pair_sha256,
            "source_row_count": state.source_row_count,
        },
        "sharadar": {
            "manifest_sha256": state.sharadar.manifest_sha256,
            "capture_id": state.sharadar.capture_id,
            "capture_sha256": state.sharadar.capture_sha256,
            "capture_transport": state.sharadar.capture_transport,
            "source_row_count": sharadar_rows,
        },
        "geometry": {
            "first_session": _legacy.FORMAL_FIRST_SESSION,
            "last_session": _legacy.FORMAL_LAST_SESSION,
            "calculation_session": _legacy.resolve_nth_session_after(
                _legacy.FORMAL_LAST_SESSION, 1
            ),
            "decision_session_count": len(state.formal_sessions),
        },
        "candidate": {
            "candidate_id": candidate_id,
            "candidate_sha256": candidate_sha256,
            "status": _legacy.STATUS_BLOCKED,
            "blocking_refusals": list(blocking),
        },
        "source_completeness": [
            {"source_role": role.value, "complete": completeness[role]}
            for role in MassiveSourceRole
        ],
        "census": {
            "candidate_security_count": len(state.security_by_ticker),
            "candidate_security_session_terminal_count": (
                state.candidate_security_session_terminal_count
            ),
            "source_role_row_counts": role_counts,
            "composition_terminal_count": state.source_row_count,
            "source_order_terminal_projection_sha256": (
                state.terminal_projection_sha256
            ),
            "canonical_terminal_projection_sha256": (
                canonical_terminal_projection_sha256
            ),
            "fundamental_seed_count": state.fundamental_seed_count,
            "firm_count": firm_count,
            "observed_firm_label_count": state.firm_label_count,
        },
        "action_census": {
            "relative_path": ACTION_CENSUS_FILENAME,
            "byte_count": action_census_byte_count,
            "content_sha256": action_census_sha256,
        },
        "shards": [item.to_record() for item in shards],
        "artifacts": [item.to_record() for item in artifacts],
        "storage": {
            "sqlite_used_only_as_bounded_construction_spool": True,
            "sqlite_retained": False,
            "canonical_derived_shards": True,
            "raw_provider_rows_retained": False,
            "full_history_materialized_in_memory": False,
            "raw_free_derived_identity": True,
            "legacy_aggregate_byte_bound_applied": False,
        },
        "authentication": {
            "source_inputs_reauthenticated_after_build": True,
            "accepted_risk_iterator_exhausted": True,
            "sharadar_visitor_exhausted": True,
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


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _prepare_output_root(path: Path, *, production: bool) -> Path:
    if type(path) is not _PATH_TYPE:
        raise PhysicalPreopenSeedArchiveError("output root must be an exact Path")
    root = Path(os.path.abspath(path))
    if production:
        allowed = _sharadar.REPOSITORY_ARTIFACTS_ROOT.absolute()
        try:
            within = os.path.commonpath((str(root), str(allowed))) == str(allowed)
        except ValueError:
            within = False
        if not within or root == allowed:
            raise PhysicalPreopenSeedArchiveError(
                "production seed output must be beneath repository artifacts"
            )
    existed = root.exists()
    try:
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
    except OSError as exc:
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed output root is unavailable"
        ) from exc
    if root.is_symlink() or not root.is_dir():
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed output root must not traverse a final link"
        )
    if not existed:
        os.chmod(root, 0o700)
    metadata = root.stat(follow_symlinks=False)
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed output root is not owner-only"
        )
    return root


def _make_stage(root: Path) -> Path:
    for _attempt in range(64):
        stage = root / f".arv2-preopen-seed-{secrets.token_hex(16)}"
        try:
            stage.mkdir(mode=0o700)
        except FileExistsError:
            continue
        except OSError as exc:
            raise PhysicalPreopenSeedArchiveError(
                "physical pre-open seed staging could not be created"
            ) from exc
        return stage
    raise PhysicalPreopenSeedArchiveError(
        "physical pre-open seed staging namespace is exhausted"
    )


def _publish_stage(stage: Path, root: Path, final_name: str) -> Path:
    final = root / final_name
    claim = root / f".{final_name}.publish-claim"
    try:
        claim_fd = os.open(
            claim,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
    except OSError as exc:
        raise PhysicalPreopenSeedArchiveError(
            "content-addressed seed publication is already claimed"
        ) from exc
    try:
        os.fsync(claim_fd)
    finally:
        os.close(claim_fd)
    if final.exists():
        raise PhysicalPreopenSeedArchiveError(
            "content-addressed physical pre-open seed already exists"
        )
    try:
        os.rename(stage, final)
        root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(root_fd)
        finally:
            os.close(root_fd)
        claim.unlink()
    except OSError as exc:
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed publication is ambiguous"
        ) from exc
    return final


def _build(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    sharadar_capture: LoadedSharadarCapture,
    output_root: Path,
    expected_c1_transport: str,
    expected_sharadar_transport: str,
    production: bool,
) -> PhysicalPreopenSeedArchive:
    _require_dependencies()
    if type(output_root) is not _PATH_TYPE:
        raise PhysicalPreopenSeedArchiveError("output root must be an exact Path")
    if type(accepted_risk_archive) is not PhysicalAcceptedRiskArchive:
        raise PhysicalPreopenSeedArchiveError(
            "physical seed requires exact accepted-risk archive authority"
        )
    if type(sharadar_capture) is not LoadedSharadarCapture:
        raise PhysicalPreopenSeedArchiveError(
            "physical seed requires exact Sharadar capture authority"
        )
    try:
        c1 = _PINNED_REQUIRE_C1(accepted_risk_archive)
    except PhysicalAcceptedRiskArchiveError as exc:
        raise PhysicalPreopenSeedArchiveError(
            "accepted-risk archive failed loader authentication"
        ) from exc
    if (
        c1.capture_transport != expected_c1_transport
        or sharadar_capture.capture_transport != expected_sharadar_transport
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical source transport does not match seed boundary"
        )
    root_candidate = Path(os.path.abspath(output_root))
    sources = (
        c1.archive_path.absolute(),
        c1.source_artifact_path.absolute(),
        sharadar_capture.artifact_path.absolute(),
    )
    if any(_paths_overlap(root_candidate, source) for source in sources):
        raise PhysicalPreopenSeedArchiveError(
            "physical seed sources and output must remain separate paths"
        )
    root = _prepare_output_root(output_root, production=production)
    stage = _make_stage(root)
    connection: sqlite3.Connection | None = None
    try:
        connection = _open_spool(stage / "spool.sqlite3")
        state = _BuildState(connection, c1=c1, sharadar=sharadar_capture)
        loaded_sharadar = _visit_sharadar(
            state, expected_transport=expected_sharadar_transport
        )
        _visit_c1(state)
        state.derive_fundamentals()
        state.derive_firm_rows()
        if _PINNED_REQUIRE_C1(c1) is not c1 or loaded_sharadar != sharadar_capture:
            raise PhysicalPreopenSeedArchiveError(
                "physical source authority changed after seed derivation"
            )
        completeness = state.source_completeness()
        blocking = _blocking_refusals(completeness)
        shards = _write_shards(stage, state)
        action_census = state.action_census()
        action_bytes = canonical_json_bytes(action_census)
        action_count, action_sha = _write_private(
            stage / ACTION_CENSUS_FILENAME,
            (action_bytes,),
            maximum_bytes=MAX_ACTION_CENSUS_BYTES,
        )
        quality_bytes = _legacy._quality_policy_bytes()
        quality_binding = _simple_binding("quality_policy", quality_bytes)
        _write_private(
            stage / QUALITY_POLICY_FILENAME,
            (quality_bytes,),
            maximum_bytes=MAX_ACTION_CENSUS_BYTES,
        )
        primary_artifacts = (
            _firm_binding(state),
            _universe_binding(state),
            _source_seed_binding(state, completeness),
            _fundamental_binding(state),
            quality_binding,
        )
        report_bytes = _composition_report(
            state, completeness, primary_artifacts, action_census
        )
        report_binding = _simple_binding("composition_report", report_bytes)
        _write_private(
            stage / COMPOSITION_REPORT_FILENAME,
            (report_bytes,),
            maximum_bytes=MAX_MANIFEST_BYTES,
        )
        artifacts_without_candidate = (*primary_artifacts, report_binding)
        candidate_record = _candidate_record(
            state,
            completeness,
            blocking,
            artifacts_without_candidate,
        )
        candidate_payload = canonical_json_bytes(candidate_record)
        candidate_sha = sha256_bytes(candidate_payload)
        candidate_id = f"arv2-physical-preopen-input-{candidate_sha[:24]}"
        candidate_binding = SeedArtifactBinding(
            role="candidate_record",
            artifact_id=candidate_id,
            semantic_sha256=None,
            content_sha256=candidate_sha,
            byte_count=len(candidate_payload),
        )
        artifacts = (*artifacts_without_candidate, candidate_binding)
        canonical_terminal_sha = _array_hash(
            lambda: _sqlite_fragments(
                state.connection, "SELECT payload FROM terminals ORDER BY payload"
            )
        )
        seed = _archive_seed(
            state=state,
            blocking=blocking,
            completeness=completeness,
            candidate_id=candidate_id,
            candidate_sha256=candidate_sha,
            action_census_byte_count=action_count,
            action_census_sha256=action_sha,
            shards=shards,
            artifacts=artifacts,
            canonical_terminal_projection_sha256=canonical_terminal_sha,
        )
        archive_sha = sha256_bytes(canonical_json_bytes(seed))
        archive_id = f"arv2-physical-preopen-seed-{archive_sha[:24]}"
        source_locations = {
            "accepted_risk_archive_path": str(c1.archive_path.absolute()),
            "sharadar_capture_path": str(sharadar_capture.artifact_path.absolute()),
        }
        manifest = canonical_json_bytes(
            {
                "schema": ARCHIVE_SCHEMA,
                "archive_id": archive_id,
                "archive_sha256": archive_sha,
                "archive_seed": seed,
                "source_locations": source_locations,
            }
        )
        connection.close()
        connection = None
        (stage / "spool.sqlite3").unlink()
        _write_private(
            stage / ARCHIVE_MANIFEST,
            (manifest,),
            maximum_bytes=MAX_MANIFEST_BYTES,
        )
        _write_private(
            stage / ARCHIVE_MANIFEST_DIGEST,
            ((sha256_bytes(manifest) + "\n").encode("ascii"),),
            maximum_bytes=65,
        )
        for directory in (stage / ROW_DIRECTORY, stage):
            descriptor = os.open(
                directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        final = _publish_stage(stage, root, archive_id)
        return load_physical_preopen_seed_archive(final)
    except sqlite3.Error as exc:
        if connection is not None:
            connection.close()
        _raise_spool_sqlite_error(exc)
    except BaseException:
        if connection is not None:
            connection.close()
        # Hidden staging is intentionally retained on uncertainty.  It never
        # has a content-addressed name and therefore cannot become authority.
        raise


def build_physical_preopen_seed_archive(
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    sharadar_capture: LoadedSharadarCapture,
    output_root: Path,
) -> PhysicalPreopenSeedArchive:
    """Build the production disk-backed seed from already captured sources."""

    return _build(
        accepted_risk_archive=accepted_risk_archive,
        sharadar_capture=sharadar_capture,
        output_root=output_root,
        expected_c1_transport=_c1._PINNED_PRODUCTION_TRANSPORT,
        expected_sharadar_transport=_sharadar.PRODUCTION_TRANSPORT,
        production=True,
    )


def _build_physical_preopen_seed_archive_for_test(
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    sharadar_capture: LoadedSharadarCapture,
    output_root: Path,
) -> PhysicalPreopenSeedArchive:
    """Offline seam accepting only both capture adapters' test transports."""

    return _build(
        accepted_risk_archive=accepted_risk_archive,
        sharadar_capture=sharadar_capture,
        output_root=output_root,
        expected_c1_transport=_c1._PINNED_TEST_TRANSPORT,
        expected_sharadar_transport=_sharadar.TEST_TRANSPORT,
        production=False,
    )


def _sha(value: object, name: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PhysicalPreopenSeedArchiveError(f"{name} is not SHA-256")
    return value


def _positive_int(value: object, name: str, *, zero: bool = True) -> int:
    minimum = 0 if zero else 1
    if type(value) is not int or value < minimum:
        raise PhysicalPreopenSeedArchiveError(f"{name} is not a bounded count")
    return value


def _read_private(path: Path, *, maximum_bytes: int, name: str) -> bytes:
    try:
        before = path.stat(follow_symlinks=False)
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > maximum_bytes
        ):
            raise PhysicalPreopenSeedArchiveError(
                f"{name} is not a private bounded regular file"
            )
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(
            os, "O_CLOEXEC", 0
        )
        descriptor = os.open(path, flags)
        try:
            chunks: list[bytes] = []
            observed = 0
            while True:
                chunk = os.read(descriptor, min(IO_CHUNK_BYTES, maximum_bytes + 1))
                if not chunk:
                    break
                observed += len(chunk)
                if observed > maximum_bytes:
                    raise PhysicalPreopenSeedArchiveCapacityError(
                        f"{name} exceeds its fixed byte bound"
                    )
                chunks.append(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except PhysicalPreopenSeedArchiveError:
        raise
    except OSError as exc:
        raise PhysicalPreopenSeedArchiveError(f"{name} is unavailable") from exc
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or observed != before.st_size
    ):
        raise PhysicalPreopenSeedArchiveError(f"{name} changed while read")
    return b"".join(chunks)


def _validate_jsonl(path: Path, descriptor: SeedShardDescriptor) -> str:
    try:
        before = path.stat(follow_symlinks=False)
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or before.st_size != descriptor.byte_count
            or before.st_size > MAX_SHARD_BYTES
        ):
            raise PhysicalPreopenSeedArchiveError(
                "physical pre-open seed shard is not private and bounded"
            )
        handle = path.open("rb")
    except PhysicalPreopenSeedArchiveError:
        raise
    except OSError as exc:
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed shard is unavailable"
        ) from exc
    digest = hashlib.sha256()
    array_digest = hashlib.sha256()
    array_digest.update(b"[")
    row_count = 0
    try:
        while True:
            line = handle.readline(MAX_ROW_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_ROW_BYTES or not line.endswith(b"\n") or b"\r" in line:
                raise PhysicalPreopenSeedArchiveCapacityError(
                    "physical pre-open seed shard row is not bounded canonical JSONL"
                )
            try:
                value = strict_json_loads(
                    decode_utf8(line[:-1], "physical pre-open seed shard row"),
                    "physical pre-open seed shard row",
                )
            except CanonicalEvidenceError as exc:
                raise PhysicalPreopenSeedArchiveError(
                    "physical pre-open seed shard row is not strict JSON"
                ) from exc
            if type(value) is not dict or canonical_json_bytes(value) != line:
                raise PhysicalPreopenSeedArchiveError(
                    "physical pre-open seed shard row is not canonical"
                )
            digest.update(line)
            if row_count:
                array_digest.update(b",")
            array_digest.update(line[:-1])
            row_count += 1
        after = os.fstat(handle.fileno())
    finally:
        handle.close()
    if (
        row_count != descriptor.row_count
        or digest.hexdigest() != descriptor.content_sha256
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed shard census or hash changed"
        )
    array_digest.update(b"]\n")
    return array_digest.hexdigest()


def _parse_descriptor(record: object) -> SeedShardDescriptor:
    if type(record) is not dict or set(record) != {
        "role",
        "relative_path",
        "sort_order",
        "row_count",
        "byte_count",
        "content_sha256",
    }:
        raise PhysicalPreopenSeedArchiveError("seed shard descriptor changed")
    role = record["role"]
    relative = record["relative_path"]
    sort_order = record["sort_order"]
    if (
        type(role) is not str
        or type(relative) is not str
        or type(sort_order) is not str
        or not relative.startswith(f"{ROW_DIRECTORY}/")
        or Path(relative).parts != (ROW_DIRECTORY, Path(relative).name)
    ):
        raise PhysicalPreopenSeedArchiveError("seed shard path or role changed")
    return SeedShardDescriptor(
        role=role,
        relative_path=relative,
        sort_order=sort_order,
        row_count=_positive_int(record["row_count"], "seed shard row count"),
        byte_count=_positive_int(record["byte_count"], "seed shard byte count"),
        content_sha256=_sha(record["content_sha256"], "seed shard hash"),
    )


def _parse_artifact(record: object) -> SeedArtifactBinding:
    if type(record) is not dict or set(record) != {
        "role",
        "artifact_id",
        "semantic_sha256",
        "content_sha256",
        "byte_count",
    }:
        raise PhysicalPreopenSeedArchiveError("seed artifact binding changed")
    role = record["role"]
    artifact_id = record["artifact_id"]
    semantic = record["semantic_sha256"]
    if (
        type(role) is not str
        or (artifact_id is not None and type(artifact_id) is not str)
        or (semantic is not None and type(semantic) is not str)
    ):
        raise PhysicalPreopenSeedArchiveError("seed artifact identity changed")
    return SeedArtifactBinding(
        role=role,
        artifact_id=artifact_id,
        semantic_sha256=None if semantic is None else _sha(semantic, "semantic hash"),
        content_sha256=_sha(record["content_sha256"], "artifact content hash"),
        byte_count=_positive_int(record["byte_count"], "artifact byte count"),
    )


def _archive_values(path: Path) -> dict[str, object]:
    absolute = Path(os.path.abspath(path))
    try:
        metadata = absolute.stat(follow_symlinks=False)
    except OSError as exc:
        raise PhysicalPreopenSeedArchiveError("seed archive is unavailable") from exc
    if (
        absolute.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise PhysicalPreopenSeedArchiveError(
            "seed archive is not an owner-only directory"
        )
    manifest_bytes = _read_private(
        absolute / ARCHIVE_MANIFEST,
        maximum_bytes=MAX_MANIFEST_BYTES,
        name="physical pre-open seed manifest",
    )
    digest_bytes = _read_private(
        absolute / ARCHIVE_MANIFEST_DIGEST,
        maximum_bytes=65,
        name="physical pre-open seed manifest digest",
    )
    if digest_bytes != (sha256_bytes(manifest_bytes) + "\n").encode("ascii"):
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed manifest digest changed"
        )
    try:
        manifest = strict_json_loads(
            decode_utf8(manifest_bytes, "physical pre-open seed manifest"),
            "physical pre-open seed manifest",
        )
    except CanonicalEvidenceError as exc:
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed manifest is not strict JSON"
        ) from exc
    if (
        type(manifest) is not dict
        or canonical_json_bytes(manifest) != manifest_bytes
        or set(manifest)
        != {
            "schema",
            "archive_id",
            "archive_sha256",
            "archive_seed",
            "source_locations",
        }
        or manifest["schema"] != ARCHIVE_SCHEMA
        or type(manifest["archive_seed"]) is not dict
        or type(manifest["source_locations"]) is not dict
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed manifest shape changed"
        )
    seed = manifest["archive_seed"]
    archive_sha = sha256_bytes(canonical_json_bytes(seed))
    archive_id = f"arv2-physical-preopen-seed-{archive_sha[:24]}"
    if (
        manifest["archive_sha256"] != archive_sha
        or manifest["archive_id"] != archive_id
        or absolute.name != archive_id
        or seed.get("schema") != ARCHIVE_SCHEMA
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed content address changed"
        )
    expected_seed_keys = {
        "schema",
        "accepted_risk",
        "sharadar",
        "geometry",
        "candidate",
        "source_completeness",
        "census",
        "action_census",
        "shards",
        "artifacts",
        "storage",
        "authentication",
        "capabilities",
    }
    if set(seed) != expected_seed_keys:
        raise PhysicalPreopenSeedArchiveError("physical seed semantic fields changed")
    accepted = seed["accepted_risk"]
    sharadar = seed["sharadar"]
    geometry = seed["geometry"]
    candidate = seed["candidate"]
    census = seed["census"]
    action = seed["action_census"]
    storage = seed["storage"]
    authentication = seed["authentication"]
    capabilities = seed["capabilities"]
    locations = manifest["source_locations"]
    if any(type(item) is not dict for item in (
        accepted, sharadar, geometry, candidate, census, action,
        storage, authentication, capabilities, locations,
    )):
        raise PhysicalPreopenSeedArchiveError("physical seed nested shape changed")
    nested_keys = (
        (
            accepted,
            {
                "archive_id",
                "archive_sha256",
                "source_artifact_id",
                "source_manifest_sha256",
                "capture_transport",
                "physical_capture_id",
                "physical_capture_sha256",
                "derived_capture_id",
                "derived_capture_sha256",
                "pair_id",
                "pair_sha256",
                "source_row_count",
            },
        ),
        (
            sharadar,
            {
                "manifest_sha256",
                "capture_id",
                "capture_sha256",
                "capture_transport",
                "source_row_count",
            },
        ),
        (
            geometry,
            {
                "first_session",
                "last_session",
                "calculation_session",
                "decision_session_count",
            },
        ),
        (
            candidate,
            {"candidate_id", "candidate_sha256", "status", "blocking_refusals"},
        ),
        (
            census,
            {
                "candidate_security_count",
                "candidate_security_session_terminal_count",
                "source_role_row_counts",
                "composition_terminal_count",
                "source_order_terminal_projection_sha256",
                "canonical_terminal_projection_sha256",
                "fundamental_seed_count",
                "firm_count",
                "observed_firm_label_count",
            },
        ),
        (
            action,
            {"relative_path", "byte_count", "content_sha256"},
        ),
        (
            locations,
            {"accepted_risk_archive_path", "sharadar_capture_path"},
        ),
    )
    if any(set(value) != expected for value, expected in nested_keys):
        raise PhysicalPreopenSeedArchiveError("physical seed nested fields changed")
    shard_records = seed["shards"]
    artifact_records = seed["artifacts"]
    if type(shard_records) is not list or type(artifact_records) is not list:
        raise PhysicalPreopenSeedArchiveError("physical seed role inventory changed")
    shards = tuple(_parse_descriptor(item) for item in shard_records)
    artifacts = tuple(_parse_artifact(item) for item in artifact_records)
    expected_shard_roles = {
        "universe_candidates",
        "session_counts",
        "earnings",
        "guidance",
        "ratings",
        "composition_terminals",
        "fundamental_seeds",
        "firm_rows",
    }
    expected_artifact_roles = {
        "firm_review_candidate",
        "eligible_universe_artifact",
        "source_seed_candidate",
        "fundamental_seed_inventory",
        "quality_policy",
        "composition_report",
        "candidate_record",
    }
    if (
        {item.role for item in shards} != expected_shard_roles
        or len(shards) != len(expected_shard_roles)
        or {item.role for item in artifacts} != expected_artifact_roles
        or len(artifacts) != len(expected_artifact_roles)
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed role inventory changed"
        )
    expected_shard_layout = {
        "universe_candidates": ("rows/universe-candidates.jsonl", "security_id"),
        "session_counts": ("rows/session-counts.jsonl", "decision_session_ordinal"),
        "earnings": ("rows/earnings.jsonl", "canonical_json_bytes"),
        "guidance": ("rows/guidance.jsonl", "canonical_json_bytes"),
        "ratings": ("rows/ratings.jsonl", "canonical_json_bytes"),
        "composition_terminals": (
            "rows/composition-terminals.jsonl",
            "canonical_json_bytes",
        ),
        "fundamental_seeds": (
            "rows/fundamental-seeds.jsonl",
            "canonical_json_bytes",
        ),
        "firm_rows": ("rows/firm-rows.jsonl", "provider_firm_id"),
    }
    if any(
        (item.relative_path, item.sort_order) != expected_shard_layout[item.role]
        for item in shards
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed shard layout changed"
        )
    expected_root = {
        ARCHIVE_MANIFEST,
        ARCHIVE_MANIFEST_DIGEST,
        ROW_DIRECTORY,
        ACTION_CENSUS_FILENAME,
        COMPOSITION_REPORT_FILENAME,
        QUALITY_POLICY_FILENAME,
    }
    if set(os.listdir(absolute)) != expected_root:
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed root inventory changed"
        )
    rows_path = absolute / ROW_DIRECTORY
    if (
        rows_path.is_symlink()
        or not rows_path.is_dir()
        or stat.S_IMODE(rows_path.stat(follow_symlinks=False).st_mode) != 0o700
        or set(os.listdir(rows_path))
        != {Path(item.relative_path).name for item in shards}
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed shard inventory changed"
        )
    shard_array_hashes = {
        descriptor.role: _validate_jsonl(
            absolute / descriptor.relative_path, descriptor
        )
        for descriptor in shards
    }
    action_bytes = _read_private(
        absolute / ACTION_CENSUS_FILENAME,
        maximum_bytes=MAX_ACTION_CENSUS_BYTES,
        name="physical pre-open action census",
    )
    if (
        len(action_bytes) != action.get("byte_count")
        or sha256_bytes(action_bytes) != action.get("content_sha256")
    ):
        raise PhysicalPreopenSeedArchiveError("physical action census changed")
    action_value = strict_json_loads(
        decode_utf8(action_bytes, "physical action census"),
        "physical action census",
    )
    if (
        type(action_value) is not dict
        or canonical_json_bytes(action_value) != action_bytes
        or set(action_value)
        != {
            "availability_semantics",
            "action_counts",
            "invalid_action_label_row_count",
            "target_ticker_discovery_row_count",
            "used_for_identity_or_payoff",
        }
        or action_value.get("availability_semantics") != ACTIONS_AVAILABILITY
        or type(action_value.get("action_counts")) is not dict
        or any(
            type(label) is not str
            or not label
            or type(count) is not int
            or count < 0
            for label, count in action_value.get("action_counts", {}).items()
        )
        or type(action_value.get("invalid_action_label_row_count")) is not int
        or action_value["invalid_action_label_row_count"] < 0
        or type(action_value.get("target_ticker_discovery_row_count")) is not int
        or action_value["target_ticker_discovery_row_count"] < 0
        or action_value.get("used_for_identity_or_payoff") is not False
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical action census semantics changed"
        )
    artifact_by_role = _artifact_map(artifacts)
    artifact_payloads: dict[str, bytes] = {}
    for filename, role, maximum in (
        (COMPOSITION_REPORT_FILENAME, "composition_report", MAX_MANIFEST_BYTES),
        (QUALITY_POLICY_FILENAME, "quality_policy", MAX_ACTION_CENSUS_BYTES),
    ):
        payload = _read_private(
            absolute / filename, maximum_bytes=maximum, name=role
        )
        binding = artifact_by_role[role]
        if (
            len(payload) != binding.byte_count
            or sha256_bytes(payload) != binding.content_sha256
        ):
            raise PhysicalPreopenSeedArchiveError(f"{role} bytes changed")
        artifact_payloads[role] = payload
    false_capabilities = (
        "provider_access",
        "credential_access",
        "quantconnect_access",
        "outcome_access",
        "result_access",
        "deployment",
        "orders",
        "trading",
    )
    if (
        set(capabilities) != set(false_capabilities)
        or any(capabilities[name] is not False for name in false_capabilities)
        or storage
        != {
            "sqlite_used_only_as_bounded_construction_spool": True,
            "sqlite_retained": False,
            "canonical_derived_shards": True,
            "raw_provider_rows_retained": False,
            "full_history_materialized_in_memory": False,
            "raw_free_derived_identity": True,
            "legacy_aggregate_byte_bound_applied": False,
        }
        or authentication
        != {
            "source_inputs_reauthenticated_after_build": True,
            "accepted_risk_iterator_exhausted": True,
            "sharadar_visitor_exhausted": True,
        }
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed capability or storage truth changed"
        )
    source_completeness_raw = seed["source_completeness"]
    if (
        type(source_completeness_raw) is not list
        or len(source_completeness_raw) != len(tuple(MassiveSourceRole))
    ):
        raise PhysicalPreopenSeedArchiveError("source completeness changed")
    source_completeness: list[tuple[MassiveSourceRole, bool]] = []
    for expected_role, record in zip(
        MassiveSourceRole, source_completeness_raw, strict=True
    ):
        if (
            type(record) is not dict
            or set(record) != {"source_role", "complete"}
            or record["source_role"] != expected_role.value
            or type(record["complete"]) is not bool
        ):
            raise PhysicalPreopenSeedArchiveError("source completeness changed")
        source_completeness.append((expected_role, record["complete"]))
    source_role_counts_raw = census.get("source_role_row_counts")
    if type(source_role_counts_raw) is not dict or set(source_role_counts_raw) != {
        "earnings", "guidance", "ratings"
    }:
        raise PhysicalPreopenSeedArchiveError("source role census changed")
    blocking = candidate.get("blocking_refusals")
    if (
        type(blocking) is not list
        or any(type(item) is not str for item in blocking)
        or candidate.get("status") != _legacy.STATUS_BLOCKED
        or tuple(blocking) != _blocking_refusals(dict(source_completeness))
    ):
        raise PhysicalPreopenSeedArchiveError("seed blocking refusals changed")
    accepted_path = locations.get("accepted_risk_archive_path")
    sharadar_path = locations.get("sharadar_capture_path")
    if (
        type(accepted_path) is not str
        or type(sharadar_path) is not str
        or not Path(accepted_path).is_absolute()
        or not Path(sharadar_path).is_absolute()
    ):
        raise PhysicalPreopenSeedArchiveError("seed source locations changed")
    values: dict[str, object] = {
        "schema": ARCHIVE_SCHEMA,
        "archive_id": archive_id,
        "archive_sha256": archive_sha,
        "archive_path": absolute,
        "accepted_risk_archive_path": Path(accepted_path),
        "accepted_risk_archive_id": accepted.get("archive_id"),
        "accepted_risk_archive_sha256": _sha(
            accepted.get("archive_sha256"), "accepted-risk archive hash"
        ),
        "massive_source_artifact_id": accepted.get("source_artifact_id"),
        "massive_source_manifest_sha256": _sha(
            accepted.get("source_manifest_sha256"), "Massive manifest hash"
        ),
        "massive_capture_transport": accepted.get("capture_transport"),
        "physical_massive_capture_id": accepted.get("physical_capture_id"),
        "physical_massive_capture_sha256": _sha(
            accepted.get("physical_capture_sha256"), "physical capture hash"
        ),
        "derived_massive_capture_id": accepted.get("derived_capture_id"),
        "derived_massive_capture_sha256": _sha(
            accepted.get("derived_capture_sha256"), "derived capture hash"
        ),
        "pair_id": accepted.get("pair_id"),
        "pair_sha256": _sha(accepted.get("pair_sha256"), "pair hash"),
        "massive_source_row_count": _positive_int(
            accepted.get("source_row_count"), "Massive row count"
        ),
        "sharadar_capture_path": Path(sharadar_path),
        "sharadar_manifest_sha256": _sha(
            sharadar.get("manifest_sha256"), "Sharadar manifest hash"
        ),
        "sharadar_capture_id": sharadar.get("capture_id"),
        "sharadar_capture_sha256": _sha(
            sharadar.get("capture_sha256"), "Sharadar capture hash"
        ),
        "sharadar_capture_transport": sharadar.get("capture_transport"),
        "sharadar_source_row_count": _positive_int(
            sharadar.get("source_row_count"), "Sharadar row count"
        ),
        "first_session": geometry.get("first_session"),
        "last_session": geometry.get("last_session"),
        "calculation_session": geometry.get("calculation_session"),
        "decision_session_count": _positive_int(
            geometry.get("decision_session_count"), "decision session count", zero=False
        ),
        "candidate_id": candidate.get("candidate_id"),
        "candidate_sha256": _sha(
            candidate.get("candidate_sha256"), "candidate hash"
        ),
        "blocking_refusals": tuple(blocking),
        "source_completeness": tuple(source_completeness),
        "candidate_security_count": _positive_int(
            census.get("candidate_security_count"), "security count", zero=False
        ),
        "candidate_security_session_terminal_count": _positive_int(
            census.get("candidate_security_session_terminal_count"),
            "security-session count",
            zero=False,
        ),
        "source_role_row_counts": tuple(
            (role, _positive_int(source_role_counts_raw[role], f"{role} count"))
            for role in ("earnings", "guidance", "ratings")
        ),
        "composition_terminal_count": _positive_int(
            census.get("composition_terminal_count"), "terminal count"
        ),
        "source_order_terminal_projection_sha256": _sha(
            census.get("source_order_terminal_projection_sha256"),
            "source-order terminal hash",
        ),
        "canonical_terminal_projection_sha256": _sha(
            census.get("canonical_terminal_projection_sha256"),
            "canonical terminal hash",
        ),
        "fundamental_seed_count": _positive_int(
            census.get("fundamental_seed_count"), "fundamental seed count"
        ),
        "firm_count": _positive_int(census.get("firm_count"), "firm count"),
        "observed_firm_label_count": _positive_int(
            census.get("observed_firm_label_count"), "firm label count"
        ),
        "action_census_byte_count": _positive_int(
            action.get("byte_count"), "action census bytes", zero=False
        ),
        "action_census_sha256": _sha(
            action.get("content_sha256"), "action census hash"
        ),
        "shards": shards,
        "artifacts": artifacts,
        "raw_provider_rows_retained": False,
        "full_history_materialized_in_memory": False,
        "raw_free_derived_identity": True,
        "source_inputs_reauthenticated_after_build": True,
        **{name: False for name in false_capabilities},
    }
    string_fields = (
        "accepted_risk_archive_id",
        "massive_source_artifact_id",
        "massive_capture_transport",
        "physical_massive_capture_id",
        "derived_massive_capture_id",
        "pair_id",
        "sharadar_capture_id",
        "sharadar_capture_transport",
        "first_session",
        "last_session",
        "calculation_session",
        "candidate_id",
    )
    if any(type(values[name]) is not str or not values[name] for name in string_fields):
        raise PhysicalPreopenSeedArchiveError("seed scalar identity changed")

    expected_calculation_session = _legacy.resolve_nth_session_after(
        _legacy.FORMAL_LAST_SESSION, 1
    )
    expected_decision_session_count = sum(
        _legacy.FORMAL_FIRST_SESSION <= session <= _legacy.FORMAL_LAST_SESSION
        for session in _legacy._session_axis(_legacy.FORMAL_LAST_SESSION)[0]
    )
    if (
        action.get("relative_path") != ACTION_CENSUS_FILENAME
        or values["first_session"] != _legacy.FORMAL_FIRST_SESSION
        or values["last_session"] != _legacy.FORMAL_LAST_SESSION
        or values["calculation_session"] != expected_calculation_session
        or values["decision_session_count"] != expected_decision_session_count
        or values["composition_terminal_count"]
        != values["massive_source_row_count"]
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical seed fixed geometry or source census changed"
        )

    descriptor_by_role = {item.role: item for item in shards}
    role_counts = dict(values["source_role_row_counts"])
    expected_shard_counts = {
        "universe_candidates": values["candidate_security_count"],
        "session_counts": values["decision_session_count"],
        "earnings": role_counts["earnings"],
        "guidance": role_counts["guidance"],
        "ratings": role_counts["ratings"],
        "composition_terminals": values["composition_terminal_count"],
        "fundamental_seeds": values["fundamental_seed_count"],
        "firm_rows": values["firm_count"],
    }
    if any(
        descriptor_by_role[role].row_count != count
        for role, count in expected_shard_counts.items()
    ) or (
        shard_array_hashes["composition_terminals"]
        != values["canonical_terminal_projection_sha256"]
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical seed shard census or terminal projection changed"
        )

    primary_prefixes = {
        "firm_review_candidate": "arv2-firm-vocabulary-",
        "eligible_universe_artifact": "arv2-universe-review-",
        "source_seed_candidate": "arv2-source-seed-review-",
        "fundamental_seed_inventory": "arv2-fundamental-seeds-",
    }
    if any(
        binding.semantic_sha256 is None
        or binding.artifact_id
        != prefix + binding.semantic_sha256[:24]
        for role, prefix in primary_prefixes.items()
        for binding in (artifact_by_role[role],)
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical seed conceptual artifact identity changed"
        )
    if (
        artifact_by_role["quality_policy"].artifact_id is not None
        or artifact_by_role["quality_policy"].semantic_sha256 is not None
        or artifact_by_role["composition_report"].artifact_id is not None
        or artifact_by_role["composition_report"].semantic_sha256 is not None
        or artifact_payloads["quality_policy"] != _legacy._quality_policy_bytes()
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical seed bounded artifact semantics changed"
        )

    completeness_by_role = dict(values["source_completeness"])
    expected_candidate_record = {
        "schema": _legacy.COMPOSER_SCHEMA,
        "status": _legacy.STATUS_BLOCKED,
        "massive_bridge_id": values["accepted_risk_archive_id"],
        "massive_bridge_sha256": values["accepted_risk_archive_sha256"],
        "pair_id": values["pair_id"],
        "pair_sha256": values["pair_sha256"],
        "derived_capture_id": values["derived_massive_capture_id"],
        "derived_capture_sha256": values["derived_massive_capture_sha256"],
        "sharadar_capture_id": values["sharadar_capture_id"],
        "sharadar_capture_sha256": values["sharadar_capture_sha256"],
        "first_session": values["first_session"],
        "last_session": values["last_session"],
        "calculation_session": values["calculation_session"],
        "blocking_refusals": list(values["blocking_refusals"]),
        "closed_input_manifest_sha256": None,
        "run_authority_candidate_sha256": None,
        "firm_review_candidate_sha256": artifact_by_role[
            "firm_review_candidate"
        ].content_sha256,
        "composition_report_sha256": artifact_by_role[
            "composition_report"
        ].content_sha256,
        "eligible_universe_artifact_sha256": artifact_by_role[
            "eligible_universe_artifact"
        ].content_sha256,
        "source_seed_candidate_sha256": artifact_by_role[
            "source_seed_candidate"
        ].content_sha256,
        "fundamental_seed_inventory_sha256": artifact_by_role[
            "fundamental_seed_inventory"
        ].content_sha256,
        "quality_policy_sha256": artifact_by_role["quality_policy"].content_sha256,
        "rating_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness_by_role[MassiveSourceRole.ANALYST_RATINGS]
        ),
        "earnings_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness_by_role[MassiveSourceRole.EARNINGS]
        ),
        "guidance_source_complete_for_frozen_query_and_accepted_risk_policy": (
            completeness_by_role[MassiveSourceRole.CORPORATE_GUIDANCE]
        ),
        "firm_ontology_reviewed": False,
        "sharadar_tickers_pristine_point_in_time": False,
        "full_pit_universe_established": False,
        "full_market_peer_census_established": False,
        "six_preopen_roles_produced": False,
        "production_preopen_input_available": False,
        "actions_used_for_identity_or_payoff": False,
        "outcome_access_performed": False,
        "quantconnect_io_performed": False,
    }
    candidate_payload = canonical_json_bytes(expected_candidate_record)
    candidate_binding = artifact_by_role["candidate_record"]
    if (
        candidate_binding.artifact_id != values["candidate_id"]
        or candidate_binding.semantic_sha256 is not None
        or candidate_binding.content_sha256 != values["candidate_sha256"]
        or candidate_binding.byte_count != len(candidate_payload)
        or sha256_bytes(candidate_payload) != values["candidate_sha256"]
        or values["candidate_id"]
        != f'arv2-physical-preopen-input-{values["candidate_sha256"][:24]}'
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical seed candidate binding changed"
        )

    report_payload = artifact_payloads["composition_report"]
    try:
        report = strict_json_loads(
            decode_utf8(report_payload, "physical seed composition report"),
            "physical seed composition report",
        )
    except CanonicalEvidenceError as exc:
        raise PhysicalPreopenSeedArchiveError(
            "physical seed composition report is not strict JSON"
        ) from exc
    expected_report_values = {
        "schema": _legacy.COMPOSITION_REPORT_SCHEMA,
        "status": _legacy.STATUS_BLOCKED,
        "blocking_refusals": list(values["blocking_refusals"]),
        "massive_bridge_id": values["accepted_risk_archive_id"],
        "massive_bridge_sha256": values["accepted_risk_archive_sha256"],
        "pair_id": values["pair_id"],
        "pair_sha256": values["pair_sha256"],
        "derived_capture_id": values["derived_massive_capture_id"],
        "derived_capture_sha256": values["derived_massive_capture_sha256"],
        "sharadar_capture_id": values["sharadar_capture_id"],
        "sharadar_capture_sha256": values["sharadar_capture_sha256"],
        "fixed_capture_range": [
            _legacy.FROZEN_CAPTURE_FIRST_DATE,
            _legacy.FROZEN_CAPTURE_LAST_DATE,
        ],
        "formal_filter_range": [
            _legacy.FORMAL_FIRST_SESSION,
            _legacy.FORMAL_LAST_SESSION,
        ],
        "source_completeness": {
            role.value: completeness_by_role[role] for role in MassiveSourceRole
        },
        "massive_source_row_count": values["massive_source_row_count"],
        "massive_composition_terminal_count": values[
            "composition_terminal_count"
        ],
        "massive_composition_terminal_projection_sha256": values[
            "source_order_terminal_projection_sha256"
        ],
        "current_snapshot_universe_security_count": values[
            "candidate_security_count"
        ],
        "current_snapshot_security_session_candidate_count": values[
            "candidate_security_session_terminal_count"
        ],
        "fundamental_seed_count": values["fundamental_seed_count"],
        "action_discovery_census": action_value,
        "source_seed_candidate_sha256": artifact_by_role[
            "source_seed_candidate"
        ].content_sha256,
        "fundamental_seed_inventory_sha256": artifact_by_role[
            "fundamental_seed_inventory"
        ].content_sha256,
        "firm_review_candidate_sha256": artifact_by_role[
            "firm_review_candidate"
        ].content_sha256,
        "eligible_universe_artifact_sha256": artifact_by_role[
            "eligible_universe_artifact"
        ].content_sha256,
        "q_data_policy_sha256": artifact_by_role["quality_policy"].content_sha256,
    }
    false_report_fields = {
        "firm_ontology_order_inferred",
        "historical_membership_availability_established",
        "historical_classification_availability_established",
        "full_pit_universe_established",
        "full_market_peer_census_established",
        "qc_sid_values_present",
        "six_preopen_roles_produced",
        "closed_input_manifest_constructed",
        "run_authority_candidate_constructed",
        "production_preopen_input_available",
        "pristine_point_in_time",
        "outcome_access_performed",
        "quantconnect_io_performed",
    }
    if (
        type(report) is not dict
        or canonical_json_bytes(report) != report_payload
        or any(report.get(key) != expected for key, expected in expected_report_values.items())
        or any(report.get(key) is not False for key in false_report_fields)
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical seed composition report bindings changed"
        )
    return values


def _mint(values: Mapping[str, object]) -> PhysicalPreopenSeedArchive:
    value = object.__new__(PhysicalPreopenSeedArchive)
    expected = {field.name for field in dataclasses.fields(value)}
    if set(values) != expected:
        raise PhysicalPreopenSeedArchiveError("seed authority fields changed")
    for name, item in values.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget(key, ref))
    with _AUTHORITY_LOCK:
        _AUTHORITIES[identity] = (reference, _fingerprint(value))
    return value


def load_physical_preopen_seed_archive(path: Path) -> PhysicalPreopenSeedArchive:
    """Load and authenticate every persisted seed byte without source I/O."""

    _require_dependencies()
    if type(path) is not _PATH_TYPE:
        raise PhysicalPreopenSeedArchiveError("seed archive path must be exact Path")
    return _mint(_archive_values(path))


def _require_registered_archive(
    value: PhysicalPreopenSeedArchive,
) -> PhysicalPreopenSeedArchive:
    _require_dependencies()
    if type(value) is not PhysicalPreopenSeedArchive:
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed requires exact authority type"
        )
    with _AUTHORITY_LOCK:
        authority = _AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != _fingerprint(value)
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed is not current loader authority"
        )
    return value


def require_physical_preopen_seed_archive(
    value: PhysicalPreopenSeedArchive,
) -> PhysicalPreopenSeedArchive:
    """Reauthenticate a loader-issued seed and every persisted leaf."""

    value = _require_registered_archive(value)
    current = _archive_values(value.archive_path)
    if any(current[field.name] != getattr(value, field.name) for field in dataclasses.fields(value)):
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open seed changed after loading"
        )
    return value


def _descriptor_for(
    archive: PhysicalPreopenSeedArchive, role: str
) -> SeedShardDescriptor:
    matches = tuple(item for item in archive.shards if item.role == role)
    if len(matches) != 1:
        raise PhysicalPreopenSeedArchiveError("physical seed shard role changed")
    return matches[0]


def _iter_shard(
    archive: PhysicalPreopenSeedArchive, role: str
) -> Iterator[dict[str, object]]:
    value = _require_registered_archive(archive)
    descriptor = _descriptor_for(value, role)
    path = value.archive_path / descriptor.relative_path
    # Authenticate the selected shard in full before disclosing its first row.
    # The second, streaming digest below catches a change during consumption
    # without re-reading every unrelated full-history shard per iterator.
    _validate_jsonl(path, descriptor)
    digest = hashlib.sha256()
    observed = 0
    try:
        handle = path.open("rb")
    except OSError as exc:
        raise PhysicalPreopenSeedArchiveError("physical seed shard is unavailable") from exc
    try:
        while True:
            line = handle.readline(MAX_ROW_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_ROW_BYTES or not line.endswith(b"\n") or b"\r" in line:
                raise PhysicalPreopenSeedArchiveCapacityError(
                    "physical seed iterator row exceeds its canonical bound"
                )
            try:
                row = strict_json_loads(
                    decode_utf8(line[:-1], "physical seed iterator row"),
                    "physical seed iterator row",
                )
            except CanonicalEvidenceError as exc:
                raise PhysicalPreopenSeedArchiveError(
                    "physical seed iterator row is not strict JSON"
                ) from exc
            if type(row) is not dict or canonical_json_bytes(row) != line:
                raise PhysicalPreopenSeedArchiveError(
                    "physical seed iterator row is not canonical"
                )
            digest.update(line)
            observed += 1
            yield row
    finally:
        handle.close()
    if (
        observed != descriptor.row_count
        or digest.hexdigest() != descriptor.content_sha256
    ):
        raise PhysicalPreopenSeedArchiveError(
            "physical seed iterator did not exhaust its authenticated shard"
        )
    # A consumed iterator is authoritative only if the complete archive still
    # authenticates at its terminal boundary.  This also refuses an unlink or
    # replacement that an already-open descriptor could otherwise conceal.
    require_physical_preopen_seed_archive(value)


def iter_physical_universe_candidates(
    archive: PhysicalPreopenSeedArchive,
) -> Iterator[dict[str, object]]:
    """Yield current-snapshot identity/CUSIP candidates by security id."""

    yield from _iter_shard(archive, "universe_candidates")


def iter_physical_session_counts(
    archive: PhysicalPreopenSeedArchive,
) -> Iterator[dict[str, object]]:
    """Yield the formal session geometry and candidate member census."""

    yield from _iter_shard(archive, "session_counts")


def iter_physical_source_role_seeds(
    archive: PhysicalPreopenSeedArchive,
    source_role: MassiveSourceRole,
) -> Iterator[dict[str, object]]:
    """Yield one canonical accepted-risk pre-open role without aggregation."""

    if type(source_role) is not MassiveSourceRole:
        raise PhysicalPreopenSeedArchiveError(
            "source-role seed iterator requires exact MassiveSourceRole"
        )
    yield from _iter_shard(archive, _ROLE_NAMES[source_role])


def iter_physical_composition_terminals(
    archive: PhysicalPreopenSeedArchive,
) -> Iterator[dict[str, object]]:
    """Yield every terminal in legacy canonical seed ordering."""

    yield from _iter_shard(archive, "composition_terminals")


def iter_physical_fundamental_seeds(
    archive: PhysicalPreopenSeedArchive,
) -> Iterator[dict[str, object]]:
    """Yield exact ART-only fundamental seed rows."""

    yield from _iter_shard(archive, "fundamental_seeds")


def iter_physical_firm_rows(
    archive: PhysicalPreopenSeedArchive,
) -> Iterator[dict[str, object]]:
    """Yield observed firm vocabularies without inferring an order."""

    yield from _iter_shard(archive, "firm_rows")


def physical_preopen_seed_artifact_binding(
    archive: PhysicalPreopenSeedArchive, role: str
) -> SeedArtifactBinding:
    """Return one authenticated conceptual legacy-compatible binding."""

    value = require_physical_preopen_seed_archive(archive)
    if type(role) is not str:
        raise PhysicalPreopenSeedArchiveError("seed artifact role must be text")
    matches = tuple(item for item in value.artifacts if item.role == role)
    if len(matches) != 1:
        raise PhysicalPreopenSeedArchiveError("seed artifact role is unavailable")
    return matches[0]


def read_physical_preopen_composition_report(
    archive: PhysicalPreopenSeedArchive,
) -> dict[str, object]:
    """Read the bounded aggregate report; provider rows remain inaccessible."""

    value = require_physical_preopen_seed_archive(archive)
    payload = _read_private(
        value.archive_path / COMPOSITION_REPORT_FILENAME,
        maximum_bytes=MAX_MANIFEST_BYTES,
        name="physical pre-open composition report",
    )
    report = strict_json_loads(
        decode_utf8(payload, "physical pre-open composition report"),
        "physical pre-open composition report",
    )
    if type(report) is not dict or canonical_json_bytes(report) != payload:
        raise PhysicalPreopenSeedArchiveError(
            "physical pre-open composition report changed"
        )
    return report


def build_fundamental_discovery_plan_for_physical_seed(
    archive: PhysicalPreopenSeedArchive,
) -> bytes:
    """Build the outcome-free QC discovery plan from authenticated geometry."""

    value = require_physical_preopen_seed_archive(archive)
    eastern = ZoneInfo("America/New_York")
    sessions: list[dict[str, object]] = []
    for ordinal, row in enumerate(iter_physical_session_counts(value), start=1):
        session = row.get("decision_session")
        if type(session) is not str:
            raise PhysicalPreopenSeedArchiveError(
                "physical seed decision session changed"
            )
        try:
            parsed = date.fromisoformat(session)
        except ValueError as exc:
            raise PhysicalPreopenSeedArchiveError(
                "physical seed decision session is not a date"
            ) from exc
        opened = datetime.combine(parsed, time(9, 30), tzinfo=eastern)
        sessions.append(
            {
                "decision_session": session,
                "decision_session_ordinal": ordinal,
                "decision_open_utc": opened.astimezone(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
            }
        )
    if len(sessions) != value.decision_session_count:
        raise PhysicalPreopenSeedArchiveError(
            "physical seed decision session census changed"
        )
    try:
        return _PINNED_DISCOVERY_BUILDER(
            decision_sessions=sessions,
            calculation_session=value.calculation_session,
        )
    except _discovery.FundamentalUniverseDiscoveryError as exc:
        raise PhysicalPreopenSeedArchiveError(
            "physical seed could not construct the discovery plan"
        ) from exc


__all__ = [
    "ARCHIVE_SCHEMA",
    "PhysicalPreopenSeedArchive",
    "PhysicalPreopenSeedArchiveCapacityError",
    "PhysicalPreopenSeedArchiveError",
    "SeedArtifactBinding",
    "SeedShardDescriptor",
    "build_fundamental_discovery_plan_for_physical_seed",
    "build_physical_preopen_seed_archive",
    "iter_physical_composition_terminals",
    "iter_physical_firm_rows",
    "iter_physical_fundamental_seeds",
    "iter_physical_session_counts",
    "iter_physical_source_role_seeds",
    "iter_physical_universe_candidates",
    "load_physical_preopen_seed_archive",
    "physical_preopen_seed_artifact_binding",
    "read_physical_preopen_composition_report",
    "require_physical_preopen_seed_archive",
]
