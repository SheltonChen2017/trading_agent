"""Outcome-free, disk-backed evidence packet for human firm-ontology review.

The accepted-risk archive is the only rating-row source.  This module streams
that source exactly once into a size-capped private SQLite construction spool,
then publishes only aggregate vocabulary and transition diagnostics.  It does
not infer a rating order, choose a scope, mint a reviewed ontology or
availability receipt, contact a provider or QuantConnect, inspect outcomes, or
grant production authority.

The predeclared review priority is deterministic: descending counts of
conservative-censored, 2021-01-01 through 2025-12-31 analyst rows whose action
is ``upgrades`` or ``downgrades`` and whose prior/current labels are both
retained.  Provider firm ID breaks ties.  The first 74 positive-volume firms
receive blank adjudication rows.
"""
from __future__ import annotations

import dataclasses
import ctypes
import errno
import hashlib
import os
import secrets
import shutil
import sqlite3
import stat
import sys
import threading
import weakref
from pathlib import Path
from typing import Callable, Iterator, Mapping

from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskSourceRow,
    MassiveSourceRole,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    require_exact_keys,
    require_identifier,
    require_int,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2_qc import (
    physical_accepted_risk_archive as _c1,
)
from research.analyst_revisions_v2_qc import (
    physical_preopen_seed_archive as _seed,
)
from research.analyst_revisions_v2_qc.physical_accepted_risk_archive import (
    PhysicalAcceptedRiskArchive,
)
from research.analyst_revisions_v2_qc.physical_preopen_seed_archive import (
    PhysicalPreopenSeedArchive,
)


ARCHIVE_SCHEMA = "arv2-physical-firm-ontology-review-packet-v1"
ARCHIVE_MANIFEST = "manifest.json"
ARCHIVE_MANIFEST_DIGEST = "manifest.sha256"
FIRM_ROWS_FILENAME = "firm-evidence.jsonl"
ADJUDICATION_TEMPLATE_FILENAME = "owner-adjudication-template.jsonl"
MAX_SQLITE_SPOOL_BYTES = 8 * 1024 * 1024 * 1024
MAX_ARCHIVE_MANIFEST_BYTES = 1024 * 1024
MAX_ARCHIVE_FILE_BYTES = 512 * 1024 * 1024
MAX_REVIEW_ROW_BYTES = 4 * 1024 * 1024
MAX_SOURCE_ROWS = 2_000_000
MAX_RETAINED_TEXT_CHARACTERS = 8_192
TOP_FIRM_COUNT = 74
RANKING_FIRST_DATE = "2021-01-01"
RANKING_LAST_DATE = "2025-12-31"
RANKING_METHOD = (
    "censored_admitted_2021_2025_upgrade_or_downgrade_with_exact_prior_"
    "and_current_labels_descending_volume_then_provider_firm_id"
)
_DIRECTIONAL_ACTIONS = frozenset({"upgrades", "downgrades"})
_PATH_TYPE = type(Path("."))

_PINNED_C1_TYPE = PhysicalAcceptedRiskArchive
_PINNED_C1_REQUIRE = _c1.require_physical_accepted_risk_archive
_PINNED_C1_ITERATOR = _c1.iter_physical_accepted_risk_rows
_PINNED_SEED_TYPE = PhysicalPreopenSeedArchive
_PINNED_SEED_REQUIRE = _seed.require_physical_preopen_seed_archive
_PINNED_ROW_TYPE = AcceptedRiskSourceRow
_PINNED_ROLE_TYPE = MassiveSourceRole
_PINNED_CANONICAL_JSON_BYTES = canonical_json_bytes
_PINNED_SHA256_BYTES = sha256_bytes
_PINNED_DECODE_UTF8 = decode_utf8
_PINNED_STRICT_JSON_LOADS = strict_json_loads
_PINNED_REQUIRE_EXACT_KEYS = require_exact_keys
_PINNED_REQUIRE_INT = require_int
_PINNED_REQUIRE_SHA256 = require_sha256
_PINNED_HASHLIB_SHA256 = hashlib.sha256

_CENSUS_FIELDS = (
    "source_row_count",
    "analyst_rating_source_row_count",
    "valid_firm_source_row_count",
    "invalid_firm_identity_row_count",
    "current_admitted_firm_row_count",
    "censored_admitted_firm_row_count",
    "exact_censored_source_clock_row_count",
    "firm_count",
    "observed_firm_name_count",
    "observed_label_count",
    "observed_transition_count",
    "ranked_firm_count",
    "adjudication_firm_count",
)
_FALSE_CAPABILITY_FIELDS = (
    "ordering_inferred",
    "scope_inferred",
    "ontology_reviewed",
    "availability_reviewed",
    "production_authority",
    "provider_access",
    "credential_access",
    "quantconnect_access",
    "outcome_access",
    "result_access",
    "deployment",
    "orders",
    "trading",
)
_RELOAD_STORAGE = {
    "source_rows_exhausted": True,
    "sqlite_used_only_as_bounded_construction_spool": True,
    "sqlite_retained": False,
    "raw_provider_rows_retained": False,
    "private_files": True,
    "content_addressed": True,
}
_RELOAD_FILE_CONTRACT = (
    ("firm_evidence", FIRM_ROWS_FILENAME, "provider_firm_id"),
    (
        "owner_adjudication_template",
        ADJUDICATION_TEMPLATE_FILENAME,
        "ranking_ordinal",
    ),
)
_REPOSITORY_ARTIFACTS_ROOT = Path(__file__).resolve().parents[2] / "artifacts"


class PhysicalFirmOntologyReviewPacketError(ValueError):
    """The inert packet or one of its exact source bindings is invalid."""


class PhysicalFirmOntologyReviewPacketCapacityError(
    PhysicalFirmOntologyReviewPacketError
):
    """A fixed construction or persisted-artifact bound was exceeded."""


class PhysicalFirmOntologyReviewPacketPublicationAmbiguityError(
    PhysicalFirmOntologyReviewPacketError
):
    """Publication durability is uncertain; visible residue is preserved."""


@dataclasses.dataclass(frozen=True, slots=True)
class FirmReviewFileDescriptor:
    role: str
    relative_path: str
    byte_count: int
    content_sha256: str
    row_count: int
    sort_key: str

    def to_record(self) -> dict[str, object]:
        return {
            "role": self.role,
            "relative_path": self.relative_path,
            "byte_count": self.byte_count,
            "content_sha256": self.content_sha256,
            "row_count": self.row_count,
            "sort_key": self.sort_key,
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class PhysicalFirmOntologyReviewPacket:
    schema: str
    packet_id: str
    packet_sha256: str
    archive_path: Path
    accepted_risk_archive_path: Path
    accepted_risk_archive_id: str
    accepted_risk_archive_sha256: str
    pair_id: str
    pair_sha256: str
    preopen_seed_archive_id: str | None
    preopen_seed_archive_sha256: str | None
    preopen_seed_cross_checked: bool
    source_row_count: int
    analyst_rating_source_row_count: int
    valid_firm_source_row_count: int
    invalid_firm_identity_row_count: int
    current_admitted_firm_row_count: int
    censored_admitted_firm_row_count: int
    exact_censored_source_clock_row_count: int
    firm_count: int
    observed_firm_name_count: int
    observed_label_count: int
    observed_transition_count: int
    ranked_firm_count: int
    adjudication_firm_count: int
    ranking_first_date: str
    ranking_last_date: str
    ranking_method: str
    files: tuple[FirmReviewFileDescriptor, ...]
    source_rows_exhausted: bool
    sqlite_used_only_as_bounded_construction_spool: bool
    sqlite_retained: bool
    ordering_inferred: bool
    scope_inferred: bool
    ontology_reviewed: bool
    availability_reviewed: bool
    production_authority: bool
    provider_access: bool
    credential_access: bool
    quantconnect_access: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


@dataclasses.dataclass(frozen=True, slots=True)
class _FileIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int
    mode: int
    owner: int
    links: int


_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalFirmOntologyReviewPacket],
        tuple[object, ...],
        _FileIdentity,
        tuple[tuple[str, _FileIdentity], ...],
        int,
    ],
] = {}
_AUTHORITY_LOCK = threading.RLock()
_AUTHORITY_PID = os.getpid()


def _reset_authorities_after_fork() -> None:
    """Discard inherited packet authority and an optionally orphaned lock."""

    global _AUTHORITIES, _AUTHORITY_LOCK, _AUTHORITY_PID
    _AUTHORITIES = {}
    _AUTHORITY_LOCK = threading.RLock()
    _AUTHORITY_PID = os.getpid()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_authorities_after_fork)


def _forget(identity: int, reference: object) -> None:
    with _AUTHORITY_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AUTHORITIES.pop(identity, None)


def _require_dependencies() -> None:
    changed = (
        _c1.PhysicalAcceptedRiskArchive is not _PINNED_C1_TYPE
        or _c1.require_physical_accepted_risk_archive is not _PINNED_C1_REQUIRE
        or _c1.iter_physical_accepted_risk_rows is not _PINNED_C1_ITERATOR
        or _seed.PhysicalPreopenSeedArchive is not _PINNED_SEED_TYPE
        or _seed.require_physical_preopen_seed_archive is not _PINNED_SEED_REQUIRE
        or AcceptedRiskSourceRow is not _PINNED_ROW_TYPE
        or MassiveSourceRole is not _PINNED_ROLE_TYPE
        or canonical_json_bytes is not _PINNED_CANONICAL_JSON_BYTES
        or sha256_bytes is not _PINNED_SHA256_BYTES
        or decode_utf8 is not _PINNED_DECODE_UTF8
        or strict_json_loads is not _PINNED_STRICT_JSON_LOADS
        or require_exact_keys is not _PINNED_REQUIRE_EXACT_KEYS
        or require_int is not _PINNED_REQUIRE_INT
        or require_sha256 is not _PINNED_REQUIRE_SHA256
        or hashlib.sha256 is not _PINNED_HASHLIB_SHA256
        or type(_DIRECTIONAL_ACTIONS) is not frozenset
        or _DIRECTIONAL_ACTIONS != frozenset({"upgrades", "downgrades"})
    )
    if changed:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review packet dependency binding changed"
        )


def _fingerprint(value: PhysicalFirmOntologyReviewPacket) -> tuple[object, ...]:
    return tuple(getattr(value, field.name) for field in dataclasses.fields(value))


def _identity_from_stat(metadata: os.stat_result) -> _FileIdentity:
    return _FileIdentity(
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        metadata.st_nlink,
    )


def _identity(path: Path, *, directory: bool) -> _FileIdentity:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review archive entry is unavailable"
        ) from exc
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(
        metadata.st_mode
    )
    required_mode = 0o700 if directory else 0o600
    if (
        not expected
        or stat.S_IMODE(metadata.st_mode) != required_mode
        or (not directory and metadata.st_nlink != 1)
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review archive entries must remain private regular objects"
        )
    return _identity_from_stat(metadata)


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("private archive write made no progress")
        offset += written


def _write_private(path: Path, payload: bytes) -> _FileIdentity:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return _identity(path, directory=False)


def _load_native_rename_noreplace():
    try:
        library = ctypes.CDLL(None, use_errno=True)
        if sys.platform == "darwin":
            function = library.renameatx_np
            flag = 0x00000004  # RENAME_EXCL
        elif sys.platform.startswith("linux"):
            function = library.renameat2
            flag = 0x00000001  # RENAME_NOREPLACE
        else:
            return None, None
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        return function, flag
    except (AttributeError, OSError, TypeError):
        return None, None


_NATIVE_RENAME_NOREPLACE, _NATIVE_RENAME_NOREPLACE_FLAG = (
    _load_native_rename_noreplace()
)


def _rename_noreplace(parent_fd: int, source: str, destination: str) -> None:
    function = _NATIVE_RENAME_NOREPLACE
    flag = _NATIVE_RENAME_NOREPLACE_FLAG
    if function is None or type(flag) is not int:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review atomic no-replace publication is unavailable"
        )
    ctypes.set_errno(0)
    result = function(
        parent_fd,
        os.fsencode(source),
        parent_fd,
        os.fsencode(destination),
        flag,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review publication destination exists"
        )
    raise PhysicalFirmOntologyReviewPacketError(
        "firm-review atomic publication failed"
    )


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _open_publication_parent(path: Path) -> int:
    _identity(path, directory=True)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags)
    except OSError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review publication parent is unavailable"
        ) from exc


def _publish_stage(stage: Path, final: Path) -> None:
    """Publish a complete stage exactly once or durably roll it back."""

    if stage.parent != final.parent:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review stage left its publication parent"
        )
    _fsync_directory(stage)
    parent_fd = _open_publication_parent(stage.parent)
    try:
        _rename_noreplace(parent_fd, stage.name, final.name)
        try:
            os.fsync(parent_fd)
        except OSError as primary:
            try:
                _rename_noreplace(parent_fd, final.name, stage.name)
                os.fsync(parent_fd)
            except Exception as rollback:
                raise PhysicalFirmOntologyReviewPacketPublicationAmbiguityError(
                    "firm-review publication rollback is ambiguous; residue preserved"
                ) from primary
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review publication sync failed and was rolled back"
            ) from primary
    finally:
        os.close(parent_fd)


def _rollback_published_stage(stage: Path, final: Path) -> None:
    """Return a visible final entry to its private stage durably."""

    if stage.parent != final.parent:
        raise PhysicalFirmOntologyReviewPacketPublicationAmbiguityError(
            "firm-review late rollback path is ambiguous; residue preserved"
        )
    parent_fd: int | None = None
    try:
        parent_fd = _open_publication_parent(stage.parent)
        _rename_noreplace(parent_fd, final.name, stage.name)
        os.fsync(parent_fd)
    except Exception as exc:
        raise PhysicalFirmOntologyReviewPacketPublicationAmbiguityError(
            "firm-review late rollback is ambiguous; residue preserved"
        ) from exc
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


def _read_private(
    path: Path, *, maximum_bytes: int, expected: _FileIdentity | None = None
) -> bytes:
    before = _identity(path, directory=False)
    if expected is not None and before != expected:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review archive entry identity changed"
        )
    if before.size > maximum_bytes:
        raise PhysicalFirmOntologyReviewPacketCapacityError(
            "firm-review archive entry exceeds its byte bound"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review archive entry is unavailable"
        ) from exc
    try:
        data = bytearray()
        while len(data) <= maximum_bytes:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        metadata = os.fstat(descriptor)
        after = _identity_from_stat(metadata)
    finally:
        os.close(descriptor)
    named_after = _identity(path, directory=False)
    if len(data) > maximum_bytes:
        raise PhysicalFirmOntologyReviewPacketCapacityError(
            "firm-review archive entry exceeds its byte bound"
        )
    if before != after or before != named_after or (expected is not None and after != expected):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review archive entry changed while read"
        )
    return bytes(data)


def _ensure_output_root(path: Path) -> Path:
    if type(path) is not _PATH_TYPE:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review output root must be an exact Path"
        )
    root = path.absolute()
    try:
        root.mkdir(parents=True, mode=0o700, exist_ok=True)
    except OSError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review output root is unavailable"
        ) from exc
    _identity(root, directory=True)
    return root


def _paths_overlap(left: Path, right: Path) -> bool:
    try:
        left = left.resolve(strict=False)
        right = right.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review source/output separation could not be established"
        ) from exc
    return left == right or left in right.parents or right in left.parents


def _sqlite_error(exc: sqlite3.Error) -> PhysicalFirmOntologyReviewPacketError:
    if getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL or "full" in str(
        exc
    ).casefold():
        return PhysicalFirmOntologyReviewPacketCapacityError(
            "firm-review SQLite spool reached its hard byte cap"
        )
    return PhysicalFirmOntologyReviewPacketError(
        "firm-review SQLite spool operation failed"
    )


def _open_spool(path: Path, maximum_bytes: int) -> sqlite3.Connection:
    if type(maximum_bytes) is not int or maximum_bytes < 4096:
        raise PhysicalFirmOntologyReviewPacketCapacityError(
            "firm-review SQLite spool cap must be at least one page"
        )
    connection: sqlite3.Connection | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        os.close(descriptor)
        connection = sqlite3.connect(path)
        _identity(path, directory=False)
        connection.execute("PRAGMA page_size=4096")
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        maximum_pages = maximum_bytes // 4096
        effective = int(
            connection.execute(f"PRAGMA max_page_count={maximum_pages}").fetchone()[0]
        )
        if effective != maximum_pages:
            raise PhysicalFirmOntologyReviewPacketCapacityError(
                "firm-review SQLite spool cap was not applied exactly"
            )
        connection.executescript(
            """
            CREATE TABLE firm_stats (
                firm_id TEXT PRIMARY KEY,
                source_row_count INTEGER NOT NULL,
                current_admitted_count INTEGER NOT NULL,
                censored_admitted_count INTEGER NOT NULL,
                exact_censored_clock_count INTEGER NOT NULL,
                invalid_current_label_count INTEGER NOT NULL,
                invalid_previous_label_count INTEGER NOT NULL,
                first_event_date TEXT NOT NULL,
                last_event_date TEXT NOT NULL,
                ranking_volume_count INTEGER NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE firm_names (
                firm_id TEXT NOT NULL,
                firm_name TEXT NOT NULL,
                observed_count INTEGER NOT NULL,
                first_event_date TEXT NOT NULL,
                last_event_date TEXT NOT NULL,
                PRIMARY KEY (firm_id, firm_name)
            ) WITHOUT ROWID;
            CREATE TABLE firm_labels (
                firm_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                raw_label TEXT NOT NULL,
                observed_count INTEGER NOT NULL,
                censored_admitted_count INTEGER NOT NULL,
                first_event_date TEXT NOT NULL,
                last_event_date TEXT NOT NULL,
                PRIMARY KEY (firm_id, field_name, raw_label)
            ) WITHOUT ROWID;
            CREATE TABLE firm_actions (
                firm_id TEXT NOT NULL,
                action_label TEXT NOT NULL,
                observed_count INTEGER NOT NULL,
                censored_admitted_count INTEGER NOT NULL,
                first_event_date TEXT NOT NULL,
                last_event_date TEXT NOT NULL,
                PRIMARY KEY (firm_id, action_label)
            ) WITHOUT ROWID;
            CREATE TABLE firm_years (
                firm_id TEXT NOT NULL,
                event_year INTEGER NOT NULL,
                observed_count INTEGER NOT NULL,
                censored_admitted_count INTEGER NOT NULL,
                PRIMARY KEY (firm_id, event_year)
            ) WITHOUT ROWID;
            CREATE TABLE firm_transitions (
                firm_id TEXT NOT NULL,
                previous_label TEXT NOT NULL,
                current_label TEXT NOT NULL,
                action_label TEXT NOT NULL,
                observed_count INTEGER NOT NULL,
                censored_admitted_count INTEGER NOT NULL,
                first_event_date TEXT NOT NULL,
                last_event_date TEXT NOT NULL,
                PRIMARY KEY (firm_id, previous_label, current_label, action_label)
            ) WITHOUT ROWID;
            CREATE TABLE earliest_exact_censored_clock (
                firm_id TEXT PRIMARY KEY,
                ordering_key TEXT NOT NULL,
                source_clock_at TEXT NOT NULL,
                event_date TEXT NOT NULL,
                raw_event_time TEXT NOT NULL,
                normalized_last_updated_at TEXT,
                eligible_session TEXT NOT NULL,
                eligible_at TEXT NOT NULL,
                decision_cutoff_at TEXT NOT NULL,
                capture_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                provider_rows_sha256 TEXT NOT NULL,
                row_offset INTEGER NOT NULL,
                raw_row_sha256 TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE rankings (
                firm_id TEXT PRIMARY KEY,
                ranking_ordinal INTEGER NOT NULL UNIQUE,
                volume_count INTEGER NOT NULL,
                selected_for_owner_adjudication INTEGER NOT NULL
            ) WITHOUT ROWID;
            """
        )
        connection.commit()
        _require_spool_capacity(connection, maximum_bytes)
        return connection
    except sqlite3.Error as exc:
        if connection is not None:
            connection.close()
        raise _sqlite_error(exc) from exc
    except OSError as exc:
        if connection is not None:
            connection.close()
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review SQLite spool could not be made private"
        ) from exc
    except PhysicalFirmOntologyReviewPacketError:
        if connection is not None:
            connection.close()
        raise


def _require_spool_capacity(
    connection: sqlite3.Connection, maximum_bytes: int
) -> None:
    try:
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        maximum_pages = int(
            connection.execute("PRAGMA max_page_count").fetchone()[0]
        )
    except sqlite3.Error as exc:
        raise _sqlite_error(exc) from exc
    if (
        page_size != 4096
        or maximum_pages != maximum_bytes // page_size
        or page_count * page_size > maximum_bytes
    ):
        raise PhysicalFirmOntologyReviewPacketCapacityError(
            "firm-review SQLite spool exceeded its hard byte cap"
        )


def _execute(
    connection: sqlite3.Connection, sql: str, parameters: tuple[object, ...]
) -> None:
    try:
        connection.execute(sql, parameters)
    except sqlite3.Error as exc:
        raise _sqlite_error(exc) from exc


def _provider_row(source: AcceptedRiskSourceRow) -> dict[str, object]:
    if type(source.raw_row_bytes) is not bytes or not source.raw_row_bytes.endswith(
        b"\n"
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "accepted-risk row bytes lost exact JSONL framing"
        )
    try:
        value = strict_json_loads(
            decode_utf8(source.raw_row_bytes[:-1], "firm-review source row"),
            "firm-review source row",
        )
    except CanonicalEvidenceError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "accepted-risk row is not strict provider JSON"
        ) from exc
    if type(value) is not dict:
        raise PhysicalFirmOntologyReviewPacketError(
            "accepted-risk row is not a provider object"
        )
    return value


def _firm_id(value: object) -> str | None:
    try:
        return require_identifier(value, "benzinga_firm_id")
    except CanonicalEvidenceError:
        return None


def _retained_text(value: object) -> str | None:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_RETAINED_TEXT_CHARACTERS
    ):
        return None
    return value


def _source_clock(source: AcceptedRiskSourceRow) -> str | None:
    if source.event_date is None or source.raw_event_time is None:
        return None
    return f"{source.event_date}T{source.raw_event_time}.000000Z"


def _upsert_source_row(
    connection: sqlite3.Connection,
    source: AcceptedRiskSourceRow,
    source_ordinal: int,
) -> tuple[bool, bool]:
    raw = _provider_row(source)
    firm_id = _firm_id(raw.get("benzinga_firm_id"))
    firm_name = _retained_text(raw.get("firm"))
    if firm_id is None or firm_name is None or source.event_date is None:
        return False, False
    current_label = _retained_text(raw.get("rating"))
    previous_label = _retained_text(raw.get("previous_rating"))
    current_admitted = int(source.current_view.included)
    censored_admitted = int(source.censored_view.included)
    source_clock = _source_clock(source)
    exact_censored = int(censored_admitted == 1 and source_clock is not None)
    ranked = int(
        censored_admitted == 1
        and RANKING_FIRST_DATE <= source.event_date <= RANKING_LAST_DATE
        and source.action_label in _DIRECTIONAL_ACTIONS
        and current_label is not None
        and previous_label is not None
    )
    _execute(
        connection,
        """
        INSERT INTO firm_stats(
            firm_id, source_row_count, current_admitted_count,
            censored_admitted_count, exact_censored_clock_count,
            invalid_current_label_count,
            invalid_previous_label_count, first_event_date, last_event_date,
            ranking_volume_count
        ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(firm_id) DO UPDATE SET
            source_row_count=source_row_count+1,
            current_admitted_count=current_admitted_count+excluded.current_admitted_count,
            censored_admitted_count=censored_admitted_count+excluded.censored_admitted_count,
            exact_censored_clock_count=
                exact_censored_clock_count+excluded.exact_censored_clock_count,
            invalid_current_label_count=
                invalid_current_label_count+excluded.invalid_current_label_count,
            invalid_previous_label_count=
                invalid_previous_label_count+excluded.invalid_previous_label_count,
            first_event_date=MIN(first_event_date, excluded.first_event_date),
            last_event_date=MAX(last_event_date, excluded.last_event_date),
            ranking_volume_count=ranking_volume_count+excluded.ranking_volume_count
        """,
        (
            firm_id,
            current_admitted,
            censored_admitted,
            exact_censored,
            int(current_label is None),
            int(previous_label is None),
            source.event_date,
            source.event_date,
            ranked,
        ),
    )
    _execute(
        connection,
        """
        INSERT INTO firm_names(
            firm_id, firm_name, observed_count, first_event_date, last_event_date
        ) VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(firm_id, firm_name) DO UPDATE SET
            observed_count=observed_count+1,
            first_event_date=MIN(first_event_date, excluded.first_event_date),
            last_event_date=MAX(last_event_date, excluded.last_event_date)
        """,
        (firm_id, firm_name, source.event_date, source.event_date),
    )
    for field_name, label in (
        ("previous_rating", previous_label),
        ("rating", current_label),
    ):
        if label is None:
            continue
        _execute(
            connection,
            """
            INSERT INTO firm_labels(
                firm_id, field_name, raw_label, observed_count,
                censored_admitted_count, first_event_date, last_event_date
            ) VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(firm_id, field_name, raw_label) DO UPDATE SET
                observed_count=observed_count+1,
                censored_admitted_count=censored_admitted_count+excluded.censored_admitted_count,
                first_event_date=MIN(first_event_date, excluded.first_event_date),
                last_event_date=MAX(last_event_date, excluded.last_event_date)
            """,
            (
                firm_id,
                field_name,
                label,
                censored_admitted,
                source.event_date,
                source.event_date,
            ),
        )
    _execute(
        connection,
        """
        INSERT INTO firm_actions(
            firm_id, action_label, observed_count, censored_admitted_count,
            first_event_date, last_event_date
        ) VALUES (?, ?, 1, ?, ?, ?)
        ON CONFLICT(firm_id, action_label) DO UPDATE SET
            observed_count=observed_count+1,
            censored_admitted_count=censored_admitted_count+excluded.censored_admitted_count,
            first_event_date=MIN(first_event_date, excluded.first_event_date),
            last_event_date=MAX(last_event_date, excluded.last_event_date)
        """,
        (
            firm_id,
            source.action_label,
            censored_admitted,
            source.event_date,
            source.event_date,
        ),
    )
    _execute(
        connection,
        """
        INSERT INTO firm_years(
            firm_id, event_year, observed_count, censored_admitted_count
        ) VALUES (?, ?, 1, ?)
        ON CONFLICT(firm_id, event_year) DO UPDATE SET
            observed_count=observed_count+1,
            censored_admitted_count=censored_admitted_count+excluded.censored_admitted_count
        """,
        (firm_id, int(source.event_date[:4]), censored_admitted),
    )
    if previous_label is not None and current_label is not None:
        _execute(
            connection,
            """
            INSERT INTO firm_transitions(
                firm_id, previous_label, current_label, action_label,
                observed_count, censored_admitted_count,
                first_event_date, last_event_date
            ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(firm_id, previous_label, current_label, action_label)
            DO UPDATE SET
                observed_count=observed_count+1,
                censored_admitted_count=censored_admitted_count+excluded.censored_admitted_count,
                first_event_date=MIN(first_event_date, excluded.first_event_date),
                last_event_date=MAX(last_event_date, excluded.last_event_date)
            """,
            (
                firm_id,
                previous_label,
                current_label,
                source.action_label,
                censored_admitted,
                source.event_date,
                source.event_date,
            ),
        )
    if exact_censored:
        if source_clock is None:
            raise PhysicalFirmOntologyReviewPacketError(
                "exact censored source clock disappeared"
            )
        eligible_session = source.censored_view.eligible_session
        eligible_at = source.censored_view.eligible_at
        decision_cutoff_at = source.censored_view.decision_cutoff_at
        if (
            eligible_session is None
            or eligible_at is None
            or decision_cutoff_at is None
        ):
            raise PhysicalFirmOntologyReviewPacketError(
                "censored-admitted rating lost its exact eligibility clock"
            )
        ordering_key = f"{source_clock}|{source_ordinal:020d}|{source.locator.raw_row_sha256}"
        _execute(
            connection,
            """
            INSERT INTO earliest_exact_censored_clock(
                firm_id, ordering_key, source_clock_at, event_date,
                raw_event_time, normalized_last_updated_at, eligible_session,
                eligible_at, decision_cutoff_at, capture_id, page_number,
                provider_rows_sha256, row_offset, raw_row_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(firm_id) DO UPDATE SET
                ordering_key=excluded.ordering_key,
                source_clock_at=excluded.source_clock_at,
                event_date=excluded.event_date,
                raw_event_time=excluded.raw_event_time,
                normalized_last_updated_at=excluded.normalized_last_updated_at,
                eligible_session=excluded.eligible_session,
                eligible_at=excluded.eligible_at,
                decision_cutoff_at=excluded.decision_cutoff_at,
                capture_id=excluded.capture_id,
                page_number=excluded.page_number,
                provider_rows_sha256=excluded.provider_rows_sha256,
                row_offset=excluded.row_offset,
                raw_row_sha256=excluded.raw_row_sha256
            WHERE excluded.ordering_key < ordering_key
            """,
            (
                firm_id,
                ordering_key,
                source_clock,
                source.event_date,
                source.raw_event_time,
                source.normalized_last_updated_at,
                eligible_session,
                eligible_at,
                decision_cutoff_at,
                source.locator.capture_id,
                source.locator.page_number,
                source.locator.provider_rows_sha256,
                source.locator.row_offset,
                source.locator.raw_row_sha256,
            ),
        )
    return True, exact_censored == 1


def _derive_rankings(connection: sqlite3.Connection) -> tuple[int, int]:
    ranked = 0
    selected = 0
    try:
        rows = connection.execute(
            "SELECT firm_id, ranking_volume_count FROM firm_stats "
            "WHERE ranking_volume_count > 0 "
            "ORDER BY ranking_volume_count DESC, firm_id"
        )
        for firm_id, volume in rows:
            ranked += 1
            chosen = int(ranked <= TOP_FIRM_COUNT)
            selected += chosen
            connection.execute(
                "INSERT INTO rankings(firm_id, ranking_ordinal, volume_count, "
                "selected_for_owner_adjudication) VALUES (?, ?, ?, ?)",
                (firm_id, ranked, volume, chosen),
            )
        connection.commit()
    except sqlite3.Error as exc:
        raise _sqlite_error(exc) from exc
    return ranked, selected


def _graph_diagnostics(
    names: list[dict[str, object]],
    labels: list[dict[str, object]],
    transitions: list[dict[str, object]],
) -> dict[str, object]:
    nodes = sorted({str(item["raw_label"]) for item in labels})
    adjacency = {node: set() for node in nodes}
    preference_edges: set[tuple[str, str]] = set()
    self_rows = 0
    directional_rows = 0
    transition_pairs: set[tuple[str, str]] = set()
    for item in transitions:
        previous = str(item["previous_rating"])
        current = str(item["current_rating"])
        action = str(item["action_label"])
        count = int(item["observed_count"])
        if previous == current:
            self_rows += count
        else:
            adjacency.setdefault(previous, set()).add(current)
            adjacency.setdefault(current, set()).add(previous)
            transition_pairs.add((previous, current))
        if action in _DIRECTIONAL_ACTIONS:
            directional_rows += count
            if previous != current:
                preference_edges.add(
                    (previous, current) if action == "upgrades" else (current, previous)
                )
    components = 0
    remaining = set(nodes)
    while remaining:
        components += 1
        pending = [remaining.pop()]
        while pending:
            node = pending.pop()
            unseen = adjacency.get(node, set()) & remaining
            remaining.difference_update(unseen)
            pending.extend(unseen)
    conflict_pairs = {
        tuple(sorted((lower, higher)))
        for lower, higher in preference_edges
        if (higher, lower) in preference_edges
    }
    directed = {node: set() for node in nodes}
    indegree = {node: 0 for node in nodes}
    for lower, higher in preference_edges:
        if higher not in directed.setdefault(lower, set()):
            directed[lower].add(higher)
            indegree[higher] = indegree.get(higher, 0) + 1
            indegree.setdefault(lower, 0)
    pending = sorted(node for node, degree in indegree.items() if degree == 0)
    visited = 0
    while pending:
        node = pending.pop(0)
        visited += 1
        for target in sorted(directed.get(node, set())):
            indegree[target] -= 1
            if indegree[target] == 0:
                pending.append(target)
                pending.sort()
    casefold_counts: dict[str, int] = {}
    for node in nodes:
        casefold_counts[node.casefold()] = casefold_counts.get(node.casefold(), 0) + 1
    return {
        "observed_firm_name_count": len(names),
        "multiple_observed_firm_names": len(names) > 1,
        "label_node_count": len(nodes),
        "distinct_transition_pair_count": len(transition_pairs),
        "undirected_component_count": components,
        "graph_connected": bool(nodes) and components == 1,
        "isolated_label_count": sum(not adjacency.get(node) for node in nodes),
        "self_transition_row_count": self_rows,
        "directional_transition_row_count": directional_rows,
        "directional_preference_edge_count": len(preference_edges),
        "directional_preference_conflict_pair_count": len(conflict_pairs),
        "directional_preference_cycle_detected": visited != len(indegree),
        "casefold_label_collision_group_count": sum(
            count > 1 for count in casefold_counts.values()
        ),
    }


def _firm_rows(connection: sqlite3.Connection) -> Iterator[dict[str, object]]:
    firm_ids = connection.execute("SELECT firm_id FROM firm_stats ORDER BY firm_id")
    for (firm_id,) in firm_ids:
        stats = connection.execute(
            "SELECT source_row_count, current_admitted_count, "
            "censored_admitted_count, exact_censored_clock_count, "
            "invalid_current_label_count, "
            "invalid_previous_label_count, first_event_date, last_event_date, "
            "ranking_volume_count FROM firm_stats WHERE firm_id=?",
            (firm_id,),
        ).fetchone()
        names = [
            {
                "firm_name": name,
                "observed_count": count,
                "first_event_date": first,
                "last_event_date": last,
            }
            for name, count, first, last in connection.execute(
                "SELECT firm_name, observed_count, first_event_date, last_event_date "
                "FROM firm_names WHERE firm_id=? ORDER BY firm_name",
                (firm_id,),
            )
        ]
        labels = [
            {
                "field": field,
                "raw_label": label,
                "observed_count": count,
                "censored_admitted_count": censored,
                "first_event_date": first,
                "last_event_date": last,
            }
            for field, label, count, censored, first, last in connection.execute(
                "SELECT field_name, raw_label, observed_count, "
                "censored_admitted_count, first_event_date, last_event_date "
                "FROM firm_labels WHERE firm_id=? ORDER BY field_name, raw_label",
                (firm_id,),
            )
        ]
        actions = [
            {
                "action_label": action,
                "observed_count": count,
                "censored_admitted_count": censored,
                "first_event_date": first,
                "last_event_date": last,
            }
            for action, count, censored, first, last in connection.execute(
                "SELECT action_label, observed_count, censored_admitted_count, "
                "first_event_date, last_event_date FROM firm_actions "
                "WHERE firm_id=? ORDER BY action_label",
                (firm_id,),
            )
        ]
        years = [
            {
                "event_year": year,
                "observed_count": count,
                "censored_admitted_count": censored,
            }
            for year, count, censored in connection.execute(
                "SELECT event_year, observed_count, censored_admitted_count "
                "FROM firm_years WHERE firm_id=? ORDER BY event_year",
                (firm_id,),
            )
        ]
        transitions = [
            {
                "previous_rating": previous,
                "current_rating": current,
                "action_label": action,
                "observed_count": count,
                "censored_admitted_count": censored,
                "first_event_date": first,
                "last_event_date": last,
            }
            for previous, current, action, count, censored, first, last in connection.execute(
                "SELECT previous_label, current_label, action_label, observed_count, "
                "censored_admitted_count, first_event_date, last_event_date "
                "FROM firm_transitions WHERE firm_id=? "
                "ORDER BY previous_label, current_label, action_label",
                (firm_id,),
            )
        ]
        earliest_raw = connection.execute(
            "SELECT source_clock_at, event_date, raw_event_time, "
            "normalized_last_updated_at, eligible_session, eligible_at, "
            "decision_cutoff_at, capture_id, page_number, provider_rows_sha256, "
            "row_offset, raw_row_sha256 FROM earliest_exact_censored_clock "
            "WHERE firm_id=?",
            (firm_id,),
        ).fetchone()
        earliest = None
        if earliest_raw is not None:
            (
                clock,
                event_date,
                raw_time,
                last_updated,
                eligible_session,
                eligible_at,
                cutoff,
                capture_id,
                page_number,
                provider_rows_sha,
                row_offset,
                raw_sha,
            ) = earliest_raw
            earliest = {
                "source_clock_at": clock,
                "event_date": event_date,
                "raw_event_time": raw_time,
                "normalized_last_updated_at": last_updated,
                "eligible_session": eligible_session,
                "eligible_at": eligible_at,
                "decision_cutoff_at": cutoff,
                "locator": {
                    "capture_id": capture_id,
                    "source_role": MassiveSourceRole.ANALYST_RATINGS.value,
                    "page_number": page_number,
                    "provider_rows_sha256": provider_rows_sha,
                    "row_offset": row_offset,
                    "raw_row_sha256": raw_sha,
                },
                "raw_row_sha256": raw_sha,
            }
        ranking = connection.execute(
            "SELECT ranking_ordinal, volume_count, selected_for_owner_adjudication "
            "FROM rankings WHERE firm_id=?",
            (firm_id,),
        ).fetchone()
        ranking_record = None
        if ranking is not None:
            ranking_record = {
                "ranking_ordinal": ranking[0],
                "volume_count": ranking[1],
                "selected_for_owner_adjudication": bool(ranking[2]),
            }
        if stats is None:
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review aggregate row disappeared"
            )
        yield {
            "provider_firm_id": firm_id,
            "observed_firm_names": names,
            "source_row_count": stats[0],
            "current_admitted_count": stats[1],
            "censored_admitted_count": stats[2],
            "exact_censored_source_clock_count": stats[3],
            "invalid_current_label_count": stats[4],
            "invalid_previous_label_count": stats[5],
            "first_event_date": stats[6],
            "last_event_date": stats[7],
            "observed_labels": labels,
            "transition_counts": transitions,
            "action_diagnostics": actions,
            "date_diagnostics": years,
            "earliest_exact_censored_admitted_source": earliest,
            "conflict_and_connectedness_diagnostics": _graph_diagnostics(
                names, labels, transitions
            ),
            "predeclared_2021_2025_volume_ranking": ranking_record,
            "ordered_scale": None,
            "scope": None,
            "ontology_reviewed": False,
            "production_authority": False,
        }


def _template_rows(connection: sqlite3.Connection) -> Iterator[dict[str, object]]:
    for firm_id, ordinal, volume in connection.execute(
        "SELECT firm_id, ranking_ordinal, volume_count FROM rankings "
        "WHERE selected_for_owner_adjudication=1 ORDER BY ranking_ordinal"
    ):
        names = [
            name
            for (name,) in connection.execute(
                "SELECT firm_name FROM firm_names WHERE firm_id=? ORDER BY firm_name",
                (firm_id,),
            )
        ]
        yield {
            "ranking_ordinal": ordinal,
            "provider_firm_id": firm_id,
            "predeclared_2021_2025_volume_count": volume,
            "observed_firm_names": names,
            "owner_adjudication": {
                "review_status": None,
                "reviewer": None,
                "reviewed_at": None,
                "canonical_firm_name": None,
                "validity_intervals": [],
                "ordered_scale": [],
                "scope": None,
                "alias_mappings": [],
                "notes": None,
            },
            "ontology_authority_created": False,
            "availability_authority_created": False,
            "production_authority": False,
        }


def _write_jsonl(
    path: Path,
    records: Iterator[dict[str, object]],
    *,
    role: str,
    sort_key: str,
) -> tuple[FirmReviewFileDescriptor, _FileIdentity]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    digest = hashlib.sha256()
    byte_count = 0
    row_count = 0
    try:
        for record in records:
            payload = canonical_json_bytes(record)
            if len(payload) > MAX_REVIEW_ROW_BYTES:
                raise PhysicalFirmOntologyReviewPacketCapacityError(
                    "one firm-review row exceeds its byte bound"
                )
            byte_count += len(payload)
            if byte_count > MAX_ARCHIVE_FILE_BYTES:
                raise PhysicalFirmOntologyReviewPacketCapacityError(
                    "firm-review archive file exceeds its byte bound"
                )
            _write_all(descriptor, payload)
            digest.update(payload)
            row_count += 1
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    identity = _identity(path, directory=False)
    return (
        FirmReviewFileDescriptor(
            role=role,
            relative_path=path.name,
            byte_count=byte_count,
            content_sha256=digest.hexdigest(),
            row_count=row_count,
            sort_key=sort_key,
        ),
        identity,
    )


def _descriptor_seed(
    *,
    accepted_risk_archive_id: str,
    accepted_risk_archive_sha256: str,
    pair_id: str,
    pair_sha256: str,
    preopen_seed_archive_id: str | None,
    preopen_seed_archive_sha256: str | None,
    counts: Mapping[str, int],
    files: tuple[FirmReviewFileDescriptor, ...],
) -> dict[str, object]:
    capabilities = {
        "ordering_inferred": False,
        "scope_inferred": False,
        "ontology_reviewed": False,
        "availability_reviewed": False,
        "production_authority": False,
        "provider_access": False,
        "credential_access": False,
        "quantconnect_access": False,
        "outcome_access": False,
        "result_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    return {
        "schema": ARCHIVE_SCHEMA,
        "accepted_risk": {
            "archive_id": accepted_risk_archive_id,
            "archive_sha256": accepted_risk_archive_sha256,
            "pair_id": pair_id,
            "pair_sha256": pair_sha256,
        },
        "preopen_seed": None
        if preopen_seed_archive_id is None
        else {
            "archive_id": preopen_seed_archive_id,
            "archive_sha256": preopen_seed_archive_sha256,
            "cross_checked": True,
        },
        "ranking": {
            "first_date": RANKING_FIRST_DATE,
            "last_date": RANKING_LAST_DATE,
            "method": RANKING_METHOD,
            "top_firm_count": TOP_FIRM_COUNT,
            "ranked_firm_count": counts["ranked_firm_count"],
            "adjudication_firm_count": counts["adjudication_firm_count"],
        },
        "census": dict(counts),
        "files": [item.to_record() for item in files],
        "storage": {
            "source_rows_exhausted": True,
            "sqlite_used_only_as_bounded_construction_spool": True,
            "sqlite_retained": False,
            "raw_provider_rows_retained": False,
            "private_files": True,
            "content_addressed": True,
        },
        "capabilities": capabilities,
    }


def _mint(
    *,
    archive_path: Path,
    packet_sha256: str,
    c1: PhysicalAcceptedRiskArchive,
    seed: PhysicalPreopenSeedArchive | None,
    counts: Mapping[str, int],
    files: tuple[FirmReviewFileDescriptor, ...],
) -> PhysicalFirmOntologyReviewPacket:
    value = object.__new__(PhysicalFirmOntologyReviewPacket)
    false_fields = (
        "ordering_inferred",
        "scope_inferred",
        "ontology_reviewed",
        "availability_reviewed",
        "production_authority",
        "provider_access",
        "credential_access",
        "quantconnect_access",
        "outcome_access",
        "result_access",
        "deployment",
        "orders",
        "trading",
    )
    values: dict[str, object] = {
        "schema": ARCHIVE_SCHEMA,
        "packet_id": f"arv2-firm-ontology-review-{packet_sha256[:24]}",
        "packet_sha256": packet_sha256,
        "archive_path": archive_path,
        "accepted_risk_archive_path": c1.archive_path,
        "accepted_risk_archive_id": c1.archive_id,
        "accepted_risk_archive_sha256": c1.archive_sha256,
        "pair_id": c1.pair_id,
        "pair_sha256": c1.pair_sha256,
        "preopen_seed_archive_id": None if seed is None else seed.archive_id,
        "preopen_seed_archive_sha256": None
        if seed is None
        else seed.archive_sha256,
        "preopen_seed_cross_checked": seed is not None,
        **dict(counts),
        "ranking_first_date": RANKING_FIRST_DATE,
        "ranking_last_date": RANKING_LAST_DATE,
        "ranking_method": RANKING_METHOD,
        "files": files,
        "source_rows_exhausted": True,
        "sqlite_used_only_as_bounded_construction_spool": True,
        "sqlite_retained": False,
        **{name: False for name in false_fields},
    }
    if set(values) != {field.name for field in dataclasses.fields(value)}:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review packet field inventory changed"
        )
    for name, item in values.items():
        object.__setattr__(value, name, item)
    root_identity = _identity(archive_path, directory=True)
    file_identities = tuple(
        (name, _identity(archive_path / name, directory=False))
        for name in sorted(
            {
                ARCHIVE_MANIFEST,
                ARCHIVE_MANIFEST_DIGEST,
                *(item.relative_path for item in files),
            }
        )
    )
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget(key, ref))
    with _AUTHORITY_LOCK:
        _AUTHORITIES[identity] = (
            reference,
            _fingerprint(value),
            root_identity,
            file_identities,
            os.getpid(),
        )
    return value


def _build(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    output_root: Path,
    preopen_seed_archive: PhysicalPreopenSeedArchive | None,
    row_iterator: Callable[
        [PhysicalAcceptedRiskArchive], Iterator[AcceptedRiskSourceRow]
    ],
    maximum_sqlite_spool_bytes: int,
) -> PhysicalFirmOntologyReviewPacket:
    _require_dependencies()
    if type(accepted_risk_archive) is not _PINNED_C1_TYPE:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review packet requires exact accepted-risk authority"
        )
    c1 = _PINNED_C1_REQUIRE(accepted_risk_archive)
    seed = preopen_seed_archive
    if seed is not None:
        if type(seed) is not _PINNED_SEED_TYPE:
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review seed cross-check requires exact seed authority"
            )
        seed = _PINNED_SEED_REQUIRE(seed)
        if (
            seed.accepted_risk_archive_id != c1.archive_id
            or seed.accepted_risk_archive_sha256 != c1.archive_sha256
            or seed.pair_id != c1.pair_id
            or seed.pair_sha256 != c1.pair_sha256
            or seed.massive_source_row_count != c1.source_row_count
        ):
            raise PhysicalFirmOntologyReviewPacketError(
                "pre-open seed does not bind the exact accepted-risk archive"
            )
    if type(output_root) is not _PATH_TYPE:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review output root must be an exact Path"
        )
    candidate_root = output_root.absolute()
    if _paths_overlap(candidate_root, c1.archive_path) or (
        seed is not None and _paths_overlap(candidate_root, seed.archive_path)
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review sources and output must remain separate"
        )
    root = _ensure_output_root(output_root)
    stage = root / f".firm-review-stage-{secrets.token_hex(16)}"
    try:
        stage.mkdir(mode=0o700)
        _identity(stage, directory=True)
    except OSError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review private stage could not be created"
        ) from exc
    spool_path = stage / "construction.sqlite3"
    connection: sqlite3.Connection | None = None
    published = False
    preserve_stage = False
    try:
        connection = _open_spool(spool_path, maximum_sqlite_spool_bytes)
        source_count = 0
        rating_count = 0
        valid_count = 0
        invalid_firm_count = 0
        current_count = 0
        censored_count = 0
        exact_clock_count = 0
        for source in row_iterator(c1):
            if type(source) is not _PINNED_ROW_TYPE:
                raise PhysicalFirmOntologyReviewPacketError(
                    "accepted-risk iterator yielded the wrong row type"
                )
            source_count += 1
            if source_count > MAX_SOURCE_ROWS:
                raise PhysicalFirmOntologyReviewPacketCapacityError(
                    "firm-review source row census exceeds its fixed bound"
                )
            if source.locator.source_role is not MassiveSourceRole.ANALYST_RATINGS:
                continue
            rating_count += 1
            valid, exact = _upsert_source_row(
                connection, source, source_count
            )
            if not valid:
                invalid_firm_count += 1
            else:
                valid_count += 1
                current_count += int(source.current_view.included)
                censored_count += int(source.censored_view.included)
                exact_clock_count += int(exact)
            if source_count % 1000 == 0:
                connection.commit()
                _require_spool_capacity(connection, maximum_sqlite_spool_bytes)
        if source_count != c1.source_row_count:
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review iterator did not exhaust the accepted-risk census"
            )
        connection.commit()
        _require_spool_capacity(connection, maximum_sqlite_spool_bytes)
        ranked_count, selected_count = _derive_rankings(connection)
        _require_spool_capacity(connection, maximum_sqlite_spool_bytes)
        firm_count = int(
            connection.execute("SELECT COUNT(*) FROM firm_stats").fetchone()[0]
        )
        name_count = int(
            connection.execute("SELECT COUNT(*) FROM firm_names").fetchone()[0]
        )
        label_count = int(
            connection.execute("SELECT COUNT(*) FROM firm_labels").fetchone()[0]
        )
        transition_count = int(
            connection.execute("SELECT COUNT(*) FROM firm_transitions").fetchone()[0]
        )
        if seed is not None:
            role_counts = dict(seed.source_role_row_counts)
            if (
                role_counts.get("ratings") != rating_count
                or seed.firm_count != firm_count
                or seed.observed_firm_label_count != label_count
            ):
                raise PhysicalFirmOntologyReviewPacketError(
                    "pre-open seed firm census does not match accepted-risk rows"
                )
        counts = {
            "source_row_count": source_count,
            "analyst_rating_source_row_count": rating_count,
            "valid_firm_source_row_count": valid_count,
            "invalid_firm_identity_row_count": invalid_firm_count,
            "current_admitted_firm_row_count": current_count,
            "censored_admitted_firm_row_count": censored_count,
            "exact_censored_source_clock_row_count": exact_clock_count,
            "firm_count": firm_count,
            "observed_firm_name_count": name_count,
            "observed_label_count": label_count,
            "observed_transition_count": transition_count,
            "ranked_firm_count": ranked_count,
            "adjudication_firm_count": selected_count,
        }
        files_with_identities = (
            _write_jsonl(
                stage / FIRM_ROWS_FILENAME,
                _firm_rows(connection),
                role="firm_evidence",
                sort_key="provider_firm_id",
            ),
            _write_jsonl(
                stage / ADJUDICATION_TEMPLATE_FILENAME,
                _template_rows(connection),
                role="owner_adjudication_template",
                sort_key="ranking_ordinal",
            ),
        )
        files = tuple(item[0] for item in files_with_identities)
        if files[0].row_count != firm_count or files[1].row_count != selected_count:
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review persisted row census changed"
            )
        connection.close()
        connection = None
        spool_path.unlink()
        seed_record = _descriptor_seed(
            accepted_risk_archive_id=c1.archive_id,
            accepted_risk_archive_sha256=c1.archive_sha256,
            pair_id=c1.pair_id,
            pair_sha256=c1.pair_sha256,
            preopen_seed_archive_id=None if seed is None else seed.archive_id,
            preopen_seed_archive_sha256=None
            if seed is None
            else seed.archive_sha256,
            counts=counts,
            files=files,
        )
        packet_sha = sha256_bytes(canonical_json_bytes(seed_record))
        packet_id = f"arv2-firm-ontology-review-{packet_sha[:24]}"
        manifest = canonical_json_bytes(
            {
                "schema": ARCHIVE_SCHEMA,
                "packet_id": packet_id,
                "packet_sha256": packet_sha,
                "packet_seed": seed_record,
            }
        )
        if len(manifest) > MAX_ARCHIVE_MANIFEST_BYTES:
            raise PhysicalFirmOntologyReviewPacketCapacityError(
                "firm-review archive manifest exceeds its byte bound"
            )
        _write_private(stage / ARCHIVE_MANIFEST, manifest)
        _write_private(
            stage / ARCHIVE_MANIFEST_DIGEST,
            (sha256_bytes(manifest) + "\n").encode("ascii"),
        )
        _PINNED_C1_REQUIRE(c1)
        if seed is not None:
            _PINNED_SEED_REQUIRE(seed)
        final = root / packet_id
        try:
            _publish_stage(stage, final)
        except PhysicalFirmOntologyReviewPacketPublicationAmbiguityError:
            preserve_stage = True
            raise
        published = True
        try:
            value = _mint(
                archive_path=final,
                packet_sha256=packet_sha,
                c1=c1,
                seed=seed,
                counts=counts,
                files=files,
            )
            return require_physical_firm_ontology_review_packet(value)
        except Exception:
            try:
                _rollback_published_stage(stage, final)
            except PhysicalFirmOntologyReviewPacketPublicationAmbiguityError:
                preserve_stage = True
                raise
            published = False
            raise
    except sqlite3.Error as exc:
        raise _sqlite_error(exc) from exc
    finally:
        if connection is not None:
            connection.close()
        if not published and not preserve_stage and stage.exists():
            shutil.rmtree(stage)


def build_physical_firm_ontology_review_packet(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    output_root: Path,
    preopen_seed_archive: PhysicalPreopenSeedArchive | None = None,
) -> PhysicalFirmOntologyReviewPacket:
    """Build an inert human-review packet from exact local source authority."""

    return _build(
        accepted_risk_archive=accepted_risk_archive,
        output_root=output_root,
        preopen_seed_archive=preopen_seed_archive,
        row_iterator=_PINNED_C1_ITERATOR,
        maximum_sqlite_spool_bytes=MAX_SQLITE_SPOOL_BYTES,
    )


def _build_physical_firm_ontology_review_packet_for_test(
    *,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    output_root: Path,
    preopen_seed_archive: PhysicalPreopenSeedArchive | None = None,
    row_iterator: Callable[
        [PhysicalAcceptedRiskArchive], Iterator[AcceptedRiskSourceRow]
    ]
    | None = None,
    maximum_sqlite_spool_bytes: int = MAX_SQLITE_SPOOL_BYTES,
) -> PhysicalFirmOntologyReviewPacket:
    """Offline seam for exhaustion and hard-cap tests; sources remain exact."""

    return _build(
        accepted_risk_archive=accepted_risk_archive,
        output_root=output_root,
        preopen_seed_archive=preopen_seed_archive,
        row_iterator=_PINNED_C1_ITERATOR if row_iterator is None else row_iterator,
        maximum_sqlite_spool_bytes=maximum_sqlite_spool_bytes,
    )


def _preflight(value: PhysicalFirmOntologyReviewPacket) -> None:
    if type(value) is not PhysicalFirmOntologyReviewPacket:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review packet requires exact authority type"
        )
    false_fields = ("sqlite_retained", *_FALSE_CAPABILITY_FIELDS)
    if (
        value.schema != ARCHIVE_SCHEMA
        or value.packet_id
        != f"arv2-firm-ontology-review-{value.packet_sha256[:24]}"
        or value.ranking_first_date != RANKING_FIRST_DATE
        or value.ranking_last_date != RANKING_LAST_DATE
        or value.ranking_method != RANKING_METHOD
        or type(value.files) is not tuple
        or len(value.files) != 2
        or tuple(item.role for item in value.files)
        != ("firm_evidence", "owner_adjudication_template")
        or any(type(item) is not FirmReviewFileDescriptor for item in value.files)
        or any(
            type(getattr(value, name)) is not int or getattr(value, name) < 0
            for name in _CENSUS_FIELDS
        )
        or value.valid_firm_source_row_count + value.invalid_firm_identity_row_count
        != value.analyst_rating_source_row_count
        or value.adjudication_firm_count
        != min(TOP_FIRM_COUNT, value.ranked_firm_count)
        or type(value.source_rows_exhausted) is not bool
        or value.source_rows_exhausted is not True
        or type(value.sqlite_used_only_as_bounded_construction_spool) is not bool
        or value.sqlite_used_only_as_bounded_construction_spool is not True
        or any(
            type(getattr(value, name)) is not bool
            or getattr(value, name) is not False
            for name in false_fields
        )
        or type(value.preopen_seed_cross_checked) is not bool
        or value.preopen_seed_cross_checked
        != (value.preopen_seed_archive_id is not None)
        or (value.preopen_seed_archive_id is None)
        != (value.preopen_seed_archive_sha256 is None)
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review packet authority fields changed"
        )


def _manifest_seed_from_value(
    value: PhysicalFirmOntologyReviewPacket,
) -> dict[str, object]:
    counts = {
        name: getattr(value, name)
        for name in _CENSUS_FIELDS
    }
    return _descriptor_seed(
        accepted_risk_archive_id=value.accepted_risk_archive_id,
        accepted_risk_archive_sha256=value.accepted_risk_archive_sha256,
        pair_id=value.pair_id,
        pair_sha256=value.pair_sha256,
        preopen_seed_archive_id=value.preopen_seed_archive_id,
        preopen_seed_archive_sha256=value.preopen_seed_archive_sha256,
        counts=counts,
        files=value.files,
    )


def _require_exact_reload_path(value: object) -> Path:
    if (
        type(value) is not _PATH_TYPE
        or not value.is_absolute()
        or ".." in value.parts
        or value != Path(os.path.abspath(value))
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload path must be an exact absolute Path"
        )
    return value


def _strict_reload_object(
    value: object, keys: tuple[str, ...], name: str
) -> dict[str, object]:
    if type(value) is not dict:
        raise PhysicalFirmOntologyReviewPacketError(
            f"{name} must be an exact JSON object"
        )
    try:
        require_exact_keys(value, keys, name)
    except CanonicalEvidenceError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            f"{name} key inventory changed"
        ) from exc
    return value


def _reload_descriptor(
    raw: object,
    expected: tuple[str, str, str],
    *,
    expected_row_count: int,
) -> FirmReviewFileDescriptor:
    record = _strict_reload_object(
        raw,
        (
            "role",
            "relative_path",
            "byte_count",
            "content_sha256",
            "row_count",
            "sort_key",
        ),
        "firm-review reload file descriptor",
    )
    role, relative_path, sort_key = expected
    try:
        byte_count = require_int(
            record["byte_count"],
            "firm-review reload file byte count",
            minimum=0,
            maximum=MAX_ARCHIVE_FILE_BYTES,
        )
        row_count = require_int(
            record["row_count"],
            "firm-review reload file row count",
            minimum=0,
            maximum=MAX_SOURCE_ROWS,
        )
        content_sha256 = require_sha256(
            record["content_sha256"],
            "firm-review reload file SHA-256",
        )
    except CanonicalEvidenceError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload file descriptor is invalid"
        ) from exc
    if (
        record["role"] != role
        or record["relative_path"] != relative_path
        or record["sort_key"] != sort_key
        or row_count != expected_row_count
        or (row_count == 0) != (byte_count == 0)
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload file descriptor changed"
        )
    return FirmReviewFileDescriptor(
        role=role,
        relative_path=relative_path,
        byte_count=byte_count,
        content_sha256=content_sha256,
        row_count=row_count,
        sort_key=sort_key,
    )


def _reload_manifest_components(
    manifest: bytes,
    *,
    expected_packet_sha256: str,
    c1: PhysicalAcceptedRiskArchive,
    seed: PhysicalPreopenSeedArchive | None,
) -> tuple[dict[str, int], tuple[FirmReviewFileDescriptor, ...]]:
    try:
        raw = strict_json_loads(
            decode_utf8(manifest, "firm-review reload manifest"),
            "firm-review reload manifest",
        )
    except CanonicalEvidenceError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload manifest is not strict JSON"
        ) from exc
    top = _strict_reload_object(
        raw,
        ("schema", "packet_id", "packet_sha256", "packet_seed"),
        "firm-review reload manifest",
    )
    if canonical_json_bytes(top) != manifest:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload manifest is not canonical"
        )
    packet_id = f"arv2-firm-ontology-review-{expected_packet_sha256[:24]}"
    if (
        top["schema"] != ARCHIVE_SCHEMA
        or top["packet_id"] != packet_id
        or top["packet_sha256"] != expected_packet_sha256
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload does not match its external trust pin"
        )
    packet_seed = _strict_reload_object(
        top["packet_seed"],
        (
            "schema",
            "accepted_risk",
            "preopen_seed",
            "ranking",
            "census",
            "files",
            "storage",
            "capabilities",
        ),
        "firm-review reload packet seed",
    )
    accepted = _strict_reload_object(
        packet_seed["accepted_risk"],
        ("archive_id", "archive_sha256", "pair_id", "pair_sha256"),
        "firm-review reload accepted-risk binding",
    )
    if accepted != {
        "archive_id": c1.archive_id,
        "archive_sha256": c1.archive_sha256,
        "pair_id": c1.pair_id,
        "pair_sha256": c1.pair_sha256,
    }:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload does not bind the exact accepted-risk archive"
        )

    raw_seed = packet_seed["preopen_seed"]
    if raw_seed is None:
        if seed is not None:
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review reload pre-open seed binding changed"
            )
    else:
        seed_record = _strict_reload_object(
            raw_seed,
            ("archive_id", "archive_sha256", "cross_checked"),
            "firm-review reload pre-open seed binding",
        )
        if seed is None or seed_record != {
            "archive_id": seed.archive_id,
            "archive_sha256": seed.archive_sha256,
            "cross_checked": True,
        }:
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review reload pre-open seed binding changed"
            )

    ranking = _strict_reload_object(
        packet_seed["ranking"],
        (
            "first_date",
            "last_date",
            "method",
            "top_firm_count",
            "ranked_firm_count",
            "adjudication_firm_count",
        ),
        "firm-review reload ranking",
    )
    census_record = _strict_reload_object(
        packet_seed["census"],
        _CENSUS_FIELDS,
        "firm-review reload census",
    )
    counts: dict[str, int] = {}
    try:
        for name in _CENSUS_FIELDS:
            counts[name] = require_int(
                census_record[name],
                f"firm-review reload {name}",
                minimum=0,
                maximum=MAX_SOURCE_ROWS,
            )
        top_firm_count = require_int(
            ranking["top_firm_count"],
            "firm-review reload top-firm count",
            minimum=TOP_FIRM_COUNT,
            maximum=TOP_FIRM_COUNT,
        )
    except CanonicalEvidenceError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload census is invalid"
        ) from exc
    if (
        packet_seed["schema"] != ARCHIVE_SCHEMA
        or ranking["first_date"] != RANKING_FIRST_DATE
        or ranking["last_date"] != RANKING_LAST_DATE
        or ranking["method"] != RANKING_METHOD
        or top_firm_count != TOP_FIRM_COUNT
        or ranking["ranked_firm_count"] != counts["ranked_firm_count"]
        or ranking["adjudication_firm_count"]
        != counts["adjudication_firm_count"]
        or counts["source_row_count"] != c1.source_row_count
        or counts["analyst_rating_source_row_count"]
        > counts["source_row_count"]
        or counts["valid_firm_source_row_count"]
        + counts["invalid_firm_identity_row_count"]
        != counts["analyst_rating_source_row_count"]
        or counts["current_admitted_firm_row_count"]
        > counts["valid_firm_source_row_count"]
        or counts["censored_admitted_firm_row_count"]
        > counts["valid_firm_source_row_count"]
        or counts["exact_censored_source_clock_row_count"]
        > counts["valid_firm_source_row_count"]
        or counts["firm_count"] > counts["valid_firm_source_row_count"]
        or counts["observed_firm_name_count"]
        > counts["valid_firm_source_row_count"]
        or counts["observed_label_count"]
        > 2 * counts["valid_firm_source_row_count"]
        or counts["observed_transition_count"]
        > counts["valid_firm_source_row_count"]
        or counts["ranked_firm_count"] > counts["firm_count"]
        or counts["adjudication_firm_count"]
        != min(TOP_FIRM_COUNT, counts["ranked_firm_count"])
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload census relationships changed"
        )

    raw_files = packet_seed["files"]
    if type(raw_files) is not list or len(raw_files) != len(_RELOAD_FILE_CONTRACT):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload file inventory changed"
        )
    files = tuple(
        _reload_descriptor(
            raw_descriptor,
            contract,
            expected_row_count=(
                counts["firm_count"]
                if index == 0
                else counts["adjudication_firm_count"]
            ),
        )
        for index, (raw_descriptor, contract) in enumerate(
            zip(raw_files, _RELOAD_FILE_CONTRACT, strict=True)
        )
    )
    storage = _strict_reload_object(
        packet_seed["storage"],
        tuple(_RELOAD_STORAGE),
        "firm-review reload storage",
    )
    capabilities = _strict_reload_object(
        packet_seed["capabilities"],
        _FALSE_CAPABILITY_FIELDS,
        "firm-review reload capabilities",
    )
    if storage != _RELOAD_STORAGE or capabilities != {
        name: False for name in _FALSE_CAPABILITY_FIELDS
    }:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload non-authorizing contract changed"
        )
    expected_seed = _descriptor_seed(
        accepted_risk_archive_id=c1.archive_id,
        accepted_risk_archive_sha256=c1.archive_sha256,
        pair_id=c1.pair_id,
        pair_sha256=c1.pair_sha256,
        preopen_seed_archive_id=None if seed is None else seed.archive_id,
        preopen_seed_archive_sha256=None
        if seed is None
        else seed.archive_sha256,
        counts=counts,
        files=files,
    )
    if (
        packet_seed != expected_seed
        or sha256_bytes(canonical_json_bytes(expected_seed))
        != expected_packet_sha256
        or top
        != {
            "schema": ARCHIVE_SCHEMA,
            "packet_id": packet_id,
            "packet_sha256": expected_packet_sha256,
            "packet_seed": expected_seed,
        }
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload manifest content root changed"
        )
    return counts, files


def _validate_jsonl(
    path: Path,
    descriptor: FirmReviewFileDescriptor,
    identity: _FileIdentity,
) -> None:
    before = _identity(path, directory=False)
    if (
        before != identity
        or identity.size != descriptor.byte_count
        or descriptor.byte_count > MAX_ARCHIVE_FILE_BYTES
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review JSONL file changed"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        raw_descriptor = os.open(path, flags)
    except OSError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review JSONL file is unavailable"
        ) from exc
    digest = hashlib.sha256()
    byte_count = 0
    row_count = 0
    prior: object | None = None
    expected_key_type = (
        str if descriptor.role == "firm_evidence" else int
    )
    handle = os.fdopen(raw_descriptor, "rb", buffering=0)
    try:
        while True:
            line = handle.readline(MAX_REVIEW_ROW_BYTES + 1)
            if not line:
                break
            if (
                len(line) > MAX_REVIEW_ROW_BYTES
                or not line.endswith(b"\n")
                or b"\r" in line
            ):
                raise PhysicalFirmOntologyReviewPacketCapacityError(
                    "one firm-review row exceeds its byte bound"
                )
            byte_count += len(line)
            row_count += 1
            if (
                byte_count > MAX_ARCHIVE_FILE_BYTES
                or byte_count > descriptor.byte_count
                or row_count > descriptor.row_count
            ):
                raise PhysicalFirmOntologyReviewPacketError(
                    "firm-review JSONL file changed"
                )
            digest.update(line)
            try:
                row = strict_json_loads(
                    decode_utf8(line[:-1], "firm-review JSONL row"),
                    "firm-review JSONL row",
                )
            except CanonicalEvidenceError as exc:
                raise PhysicalFirmOntologyReviewPacketError(
                    "firm-review JSONL row is not strict JSON"
                ) from exc
            if type(row) is not dict or canonical_json_bytes(row) != line:
                raise PhysicalFirmOntologyReviewPacketError(
                    "firm-review JSONL row is not canonical"
                )
            key = row.get(descriptor.sort_key)
            if type(key) is not expected_key_type or (
                prior is not None and key <= prior
            ):
                raise PhysicalFirmOntologyReviewPacketError(
                    "firm-review JSONL order changed"
                )
            prior = key
        after = _identity_from_stat(os.fstat(handle.fileno()))
    finally:
        handle.close()
    named_after = _identity(path, directory=False)
    if before != after or before != named_after:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review JSONL file changed while read"
        )
    if (
        byte_count != descriptor.byte_count
        or row_count != descriptor.row_count
        or digest.hexdigest() != descriptor.content_sha256
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review JSONL row census changed"
        )


def require_physical_firm_ontology_review_packet(
    value: PhysicalFirmOntologyReviewPacket,
) -> PhysicalFirmOntologyReviewPacket:
    """Reauthenticate builder authority and every inert persisted byte."""

    _require_dependencies()
    _preflight(value)
    current_pid = os.getpid()
    if current_pid != _AUTHORITY_PID:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review packet process authority changed"
        )
    with _AUTHORITY_LOCK:
        authority = _AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != _fingerprint(value)
        or authority[2] != _identity(value.archive_path, directory=True)
        or authority[4] != current_pid
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review packet is not current builder authority"
        )
    identities = dict(authority[3])
    expected_names = {
        ARCHIVE_MANIFEST,
        ARCHIVE_MANIFEST_DIGEST,
        *(item.relative_path for item in value.files),
    }
    try:
        observed_names = set(os.listdir(value.archive_path))
    except OSError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review archive inventory is unavailable"
        ) from exc
    if observed_names != expected_names or set(identities) != expected_names:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review archive inventory changed"
        )
    manifest = _read_private(
        value.archive_path / ARCHIVE_MANIFEST,
        maximum_bytes=MAX_ARCHIVE_MANIFEST_BYTES,
        expected=identities[ARCHIVE_MANIFEST],
    )
    digest = _read_private(
        value.archive_path / ARCHIVE_MANIFEST_DIGEST,
        maximum_bytes=65,
        expected=identities[ARCHIVE_MANIFEST_DIGEST],
    )
    seed_record = _manifest_seed_from_value(value)
    expected_manifest = canonical_json_bytes(
        {
            "schema": ARCHIVE_SCHEMA,
            "packet_id": value.packet_id,
            "packet_sha256": value.packet_sha256,
            "packet_seed": seed_record,
        }
    )
    if (
        manifest != expected_manifest
        or digest != (sha256_bytes(manifest) + "\n").encode("ascii")
        or sha256_bytes(canonical_json_bytes(seed_record)) != value.packet_sha256
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review archive manifest does not authenticate"
        )
    for descriptor in value.files:
        _validate_jsonl(
            value.archive_path / descriptor.relative_path,
            descriptor,
            identities[descriptor.relative_path],
        )
    return value


def _within_repository_artifacts(path: Path) -> bool:
    try:
        path.relative_to(_REPOSITORY_ARTIFACTS_ROOT)
    except ValueError:
        return False
    return path != _REPOSITORY_ARTIFACTS_ROOT


def _open_reload_directory(path: Path) -> tuple[int, _FileIdentity]:
    before = _identity(path, directory=True)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload directory is unavailable"
        ) from exc
    after = _identity_from_stat(os.fstat(descriptor))
    if before != after:
        os.close(descriptor)
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload directory identity changed"
        )
    return descriptor, before


def _require_reload_directory_current(
    path: Path, descriptor: int, expected: _FileIdentity
) -> None:
    try:
        opened = _identity_from_stat(os.fstat(descriptor))
        named = _identity(path, directory=True)
    except OSError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload directory identity changed"
        ) from exc
    if opened != expected or named != expected:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload directory identity changed"
        )


def _require_reload_inventory(
    descriptor: int,
    expected_names: set[str],
) -> None:
    try:
        observed_names = set(os.listdir(descriptor))
    except OSError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload inventory is unavailable"
        ) from exc
    if observed_names != expected_names:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload inventory changed"
        )


def _load_physical_firm_ontology_review_packet(
    *,
    archive_path: Path,
    expected_packet_sha256: str,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    preopen_seed_archive: PhysicalPreopenSeedArchive | None,
    require_repository_path: bool,
    final_require: Callable[
        [PhysicalFirmOntologyReviewPacket], PhysicalFirmOntologyReviewPacket
    ],
) -> PhysicalFirmOntologyReviewPacket:
    """Mint process-local authority only after complete disk reauthentication."""

    _require_dependencies()
    if type(expected_packet_sha256) is not str:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload external trust pin is invalid"
        )
    try:
        require_sha256(
            expected_packet_sha256,
            "firm-review reload expected packet SHA-256",
        )
    except CanonicalEvidenceError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload external trust pin is invalid"
        ) from exc
    if (
        type(accepted_risk_archive) is not _PINNED_C1_TYPE
        or type(require_repository_path) is not bool
    ):
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload trust policy changed"
        )
    c1 = _PINNED_C1_REQUIRE(accepted_risk_archive)
    seed = preopen_seed_archive
    if seed is not None:
        if type(seed) is not _PINNED_SEED_TYPE:
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review reload requires exact pre-open seed authority"
            )
        seed = _PINNED_SEED_REQUIRE(seed)
        if (
            seed.accepted_risk_archive_id != c1.archive_id
            or seed.accepted_risk_archive_sha256 != c1.archive_sha256
            or seed.pair_id != c1.pair_id
            or seed.pair_sha256 != c1.pair_sha256
            or seed.massive_source_row_count != c1.source_row_count
        ):
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review reload pre-open seed does not bind accepted risk"
            )
    archive = _require_exact_reload_path(archive_path)
    expected_id = f"arv2-firm-ontology-review-{expected_packet_sha256[:24]}"
    if archive.name != expected_id:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review reload directory name changed"
        )
    if require_repository_path and not _within_repository_artifacts(archive):
        raise PhysicalFirmOntologyReviewPacketError(
            "production firm-review reload path must remain under artifacts"
        )
    for source_path in (
        c1.archive_path,
        None if seed is None else seed.archive_path,
    ):
        if source_path is not None and (
            archive == source_path
            or archive in source_path.parents
            or source_path in archive.parents
        ):
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review reload source and archive paths overlap"
            )

    root_fd: int | None = None
    registered_identity: int | None = None
    registered_reference: weakref.ReferenceType[
        PhysicalFirmOntologyReviewPacket
    ] | None = None
    try:
        root_fd, root_identity = _open_reload_directory(archive)
        expected_names = {
            ARCHIVE_MANIFEST,
            ARCHIVE_MANIFEST_DIGEST,
            FIRM_ROWS_FILENAME,
            ADJUDICATION_TEMPLATE_FILENAME,
        }
        _require_reload_inventory(root_fd, expected_names)
        leaf_identities = {
            name: _identity(archive / name, directory=False)
            for name in expected_names
        }
        manifest = _read_private(
            archive / ARCHIVE_MANIFEST,
            maximum_bytes=MAX_ARCHIVE_MANIFEST_BYTES,
            expected=leaf_identities[ARCHIVE_MANIFEST],
        )
        digest = _read_private(
            archive / ARCHIVE_MANIFEST_DIGEST,
            maximum_bytes=65,
            expected=leaf_identities[ARCHIVE_MANIFEST_DIGEST],
        )
        if digest != (sha256_bytes(manifest) + "\n").encode("ascii"):
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review reload manifest digest changed"
            )
        counts, files = _reload_manifest_components(
            manifest,
            expected_packet_sha256=expected_packet_sha256,
            c1=c1,
            seed=seed,
        )
        for file_descriptor in files:
            _validate_jsonl(
                archive / file_descriptor.relative_path,
                file_descriptor,
                leaf_identities[file_descriptor.relative_path],
            )
        _require_reload_inventory(root_fd, expected_names)
        if {
            name: _identity(archive / name, directory=False)
            for name in expected_names
        } != leaf_identities:
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review reload leaf identity changed"
            )
        _require_reload_directory_current(archive, root_fd, root_identity)
        _PINNED_C1_REQUIRE(c1)
        if seed is not None:
            _PINNED_SEED_REQUIRE(seed)
        value = _mint(
            archive_path=archive,
            packet_sha256=expected_packet_sha256,
            c1=c1,
            seed=seed,
            counts=counts,
            files=files,
        )
        registered_identity = id(value)
        with _AUTHORITY_LOCK:
            authority = _AUTHORITIES.get(registered_identity)
        if authority is None or authority[0]() is not value:
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review reload mint did not register exact authority"
            )
        registered_reference = authority[0]
        authenticated = final_require(value)
        if authenticated is not value:
            raise PhysicalFirmOntologyReviewPacketError(
                "firm-review reload final authenticator changed authority"
            )
        _require_reload_inventory(root_fd, expected_names)
        _require_reload_directory_current(archive, root_fd, root_identity)
        _PINNED_C1_REQUIRE(c1)
        if seed is not None:
            _PINNED_SEED_REQUIRE(seed)
        _require_dependencies()
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
        if root_fd is not None:
            try:
                os.close(root_fd)
            except OSError:
                pass


def load_physical_firm_ontology_review_packet(
    *,
    archive_path: Path,
    expected_packet_sha256: str,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    preopen_seed_archive: PhysicalPreopenSeedArchive | None = None,
) -> PhysicalFirmOntologyReviewPacket:
    """Reload a production packet under owner/reviewer and exact C1 pins."""

    return _load_physical_firm_ontology_review_packet(
        archive_path=archive_path,
        expected_packet_sha256=expected_packet_sha256,
        accepted_risk_archive=accepted_risk_archive,
        preopen_seed_archive=preopen_seed_archive,
        require_repository_path=True,
        final_require=require_physical_firm_ontology_review_packet,
    )


def _load_test_fixture_physical_firm_ontology_review_packet(
    *,
    archive_path: Path,
    expected_packet_sha256: str,
    accepted_risk_archive: PhysicalAcceptedRiskArchive,
    preopen_seed_archive: PhysicalPreopenSeedArchive | None = None,
    final_require: Callable[
        [PhysicalFirmOntologyReviewPacket], PhysicalFirmOntologyReviewPacket
    ] = require_physical_firm_ontology_review_packet,
) -> PhysicalFirmOntologyReviewPacket:
    """Offline seam; it changes only the repository-path policy/finalizer."""

    return _load_physical_firm_ontology_review_packet(
        archive_path=archive_path,
        expected_packet_sha256=expected_packet_sha256,
        accepted_risk_archive=accepted_risk_archive,
        preopen_seed_archive=preopen_seed_archive,
        require_repository_path=False,
        final_require=final_require,
    )


def _iter_file(
    value: PhysicalFirmOntologyReviewPacket, role: str
) -> Iterator[dict[str, object]]:
    packet = require_physical_firm_ontology_review_packet(value)
    descriptors = tuple(item for item in packet.files if item.role == role)
    if len(descriptors) != 1:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review file role changed"
        )
    descriptor = descriptors[0]
    path = packet.archive_path / descriptor.relative_path
    observed = 0
    digest = hashlib.sha256()
    try:
        handle = path.open("rb")
    except OSError as exc:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review JSONL file is unavailable"
        ) from exc
    try:
        while True:
            line = handle.readline(MAX_REVIEW_ROW_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_REVIEW_ROW_BYTES or not line.endswith(b"\n"):
                raise PhysicalFirmOntologyReviewPacketCapacityError(
                    "one firm-review iterator row exceeds its byte bound"
                )
            try:
                row = strict_json_loads(
                    decode_utf8(line[:-1], "firm-review iterator row"),
                    "firm-review iterator row",
                )
            except CanonicalEvidenceError as exc:
                raise PhysicalFirmOntologyReviewPacketError(
                    "firm-review iterator row is not strict JSON"
                ) from exc
            if type(row) is not dict or canonical_json_bytes(row) != line:
                raise PhysicalFirmOntologyReviewPacketError(
                    "firm-review iterator row is not canonical"
                )
            digest.update(line)
            observed += 1
            yield row
    finally:
        handle.close()
    if observed != descriptor.row_count or digest.hexdigest() != descriptor.content_sha256:
        raise PhysicalFirmOntologyReviewPacketError(
            "firm-review iterator did not exhaust its authenticated file"
        )
    require_physical_firm_ontology_review_packet(packet)


def iter_physical_firm_ontology_review_rows(
    value: PhysicalFirmOntologyReviewPacket,
) -> Iterator[dict[str, object]]:
    """Yield per-firm evidence rows in exact provider-firm-ID order."""

    yield from _iter_file(value, "firm_evidence")


def iter_physical_firm_owner_adjudication_template(
    value: PhysicalFirmOntologyReviewPacket,
) -> Iterator[dict[str, object]]:
    """Yield top-volume blank owner-adjudication rows in ranking order."""

    yield from _iter_file(value, "owner_adjudication_template")


__all__ = [
    "ADJUDICATION_TEMPLATE_FILENAME",
    "ARCHIVE_SCHEMA",
    "FIRM_ROWS_FILENAME",
    "FirmReviewFileDescriptor",
    "PhysicalFirmOntologyReviewPacket",
    "PhysicalFirmOntologyReviewPacketCapacityError",
    "PhysicalFirmOntologyReviewPacketError",
    "PhysicalFirmOntologyReviewPacketPublicationAmbiguityError",
    "RANKING_FIRST_DATE",
    "RANKING_LAST_DATE",
    "RANKING_METHOD",
    "TOP_FIRM_COUNT",
    "build_physical_firm_ontology_review_packet",
    "iter_physical_firm_ontology_review_rows",
    "iter_physical_firm_owner_adjudication_template",
    "load_physical_firm_ontology_review_packet",
    "require_physical_firm_ontology_review_packet",
]
