"""Disk-backed lifecycle-to-formal-terminal composition for ARV2.

The historical universe bridge is the only lifecycle source admitted here.
It is reopened through its authenticated full-axis shard iterator and joined
only to outcome slots emitted by the formal streaming builder.  Ordinary
numeric or fill-forward bars are intentionally absent from this boundary.

QuantConnect's delisting object is lifecycle evidence, not a shareholder
payoff.  Until a separately reviewed CRSP-equivalent source exists, every
actual slot touched by a known, missing, or ambiguous lifecycle terminal is
therefore emitted as ``named_terminal_refusal``.  No merger, bankruptcy,
successor, cash, or zero-recovery value is inferred.

The potentially large lifecycle and slot censuses live in a private SQLite
spool.  Final package and receipt files are immutable, owner-only artifacts;
all public validators reopen them with no-follow, stat, size, inventory, and
SHA-256 checks.  Importing this module performs no filesystem, provider,
credential, QuantConnect, outcome, result, order, or trading action.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import sqlite3
import stat
import threading
import weakref
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    parse_date,
    parse_utc_timestamp,
    require_exact_bool,
    require_identifier,
    require_int,
    require_sha256,
    require_text,
    sha256_bytes,
    strict_json_loads,
)
from scripts import build_arv2_historical_preopen_bridge as historical_module

from .formal_input_composer import (
    FormalTerminalDispositionPackage,
    TERMINAL_PACKAGE_SCHEMA,
    _axis as _formal_outcome_axis,
    load_formal_terminal_disposition_package,
    render_formal_terminal_disposition_package_bytes,
    require_formal_terminal_disposition_package,
)
from .formal_run_protocol import (
    HORIZONS,
    TERMINAL_POLICY_ID,
    ArtifactBinding,
    TerminalCensusBinding,
    require_terminal_census_binding,
)
from .formal_runtime_projection import TERMINAL_OBJECT_SCHEMA


class FormalTerminalDispositionBuildError(ValueError):
    """Lifecycle evidence or its exact formal-slot census is not usable."""


class FormalTerminalDispositionCapacityRefusal(
    FormalTerminalDispositionBuildError
):
    """A fixed disk, row, security, or package ceiling was exceeded."""


RECORDER_SCHEMA = "arv2-lifecycle-terminal-slot-recorder-v1"
BUILD_SCHEMA = "arv2-lifecycle-formal-terminal-disposition-build-v1"
BUILD_STATUS = "complete_exhaustive_named_terminal_refusal_boundary"

MAX_LIFECYCLE_ROW_COUNT = 25_000_000
MAX_ACTUAL_SECURITY_COUNT = 100_000
MAX_ACTUAL_SLOT_COUNT = 10_000_000
MAX_LIFECYCLE_ROW_BYTES = 64 * 1024
MAX_SQLITE_SPOOL_BYTES = 16 * 1024 * 1024 * 1024
MAX_TERMINAL_PACKAGE_ROWS = 500_000
MAX_TERMINAL_PACKAGE_BYTES = 256 * 1024 * 1024
MAX_TERMINAL_ARTIFACT_FILE_COUNT = 3

_SPOOL_NAME = "lifecycle-terminal-slot-spool.sqlite3"
_PACKAGE_PREFIX = "formal-terminal-dispositions-"
_RECEIPT_PREFIX = "formal-terminal-build-"
_SLOT_KINDS = frozenset({"decision_horizon", "economic_daily"})
_LIFECYCLE_FIELDS = frozenset(
    {
        "schema",
        "decision_session",
        "decision_session_ordinal",
        "decision_open_utc",
        "source_ordinal",
        "discovery_disposition",
        "discovery_refusal_reason",
        "qc_security_id",
        "cusip",
        "display_ticker_non_authoritative",
        "logical_security_id",
        "issuer_id",
        "share_class_id",
        "listing_id",
        "delisting_date",
        "available_at",
        "identity_evidence_sha256",
        "source_terminal_sha256",
        "mapping_row_sha256",
        "bridge_join_disposition",
        "bridge_join_reason",
        "lifecycle_evidence_only",
        "payoff_semantics_assigned",
        "binding_sha256",
    }
)
_CAPABILITIES = (
    "provider_access",
    "credential_access",
    "quantconnect_access",
    "qc_delisting_price_access",
    "terminal_payoff_inference",
    "outcome_result_access",
    "qc_launch",
    "deployment",
    "orders",
    "trading",
)
_KNOWN_TERMINAL_REASON = "crsp_equivalent_terminal_payoff_unavailable"
_MISSING_LIFECYCLE_REASON = "missing_lifecycle_evidence_for_actual_slot"
_AMBIGUOUS_LIFECYCLE_REASON = (
    "ambiguous_or_inconsistent_lifecycle_evidence"
)


def _safe_security(value: object, name: str = "security_id") -> str:
    try:
        return require_identifier(value, name)
    except CanonicalEvidenceError as exc:
        raise FormalTerminalDispositionBuildError(
            f"{name} is not a canonical permanent identifier"
        ) from exc


def _safe_slot_id(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 512
        or value[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        or any(
            character
            not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:/-"
            for character in value
        )
    ):
        raise FormalTerminalDispositionBuildError(
            "terminal slot_id is not a bounded safe identifier"
        )
    return value


def _exact_path(value: object, name: str) -> Path:
    if (
        type(value) is not type(Path())
        or not value.is_absolute()
        or ".." in value.parts
    ):
        raise FormalTerminalDispositionBuildError(
            f"{name} must be an exact absolute Path without parent traversal"
        )
    return value


def _directory_identity(path: Path) -> tuple[int, int, int, int]:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise FormalTerminalDispositionBuildError(
            "terminal artifact directory is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_mode & 0o077
        or (
            os.name != "nt"
            and hasattr(os, "getuid")
            and observed.st_uid != os.getuid()
        )
    ):
        raise FormalTerminalDispositionBuildError(
            "terminal artifact directory is not owner-only regular storage"
        )
    return (
        observed.st_dev,
        observed.st_ino,
        stat.S_IFMT(observed.st_mode),
        stat.S_IMODE(observed.st_mode),
    )


def _file_fingerprint(path: Path, *, maximum_bytes: int) -> tuple[object, ...]:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise FormalTerminalDispositionBuildError(
            "terminal artifact file is unavailable"
        ) from exc
    if (
        not stat.S_ISREG(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_nlink != 1
        or observed.st_size <= 0
        or observed.st_size > maximum_bytes
        or observed.st_mode & 0o077
        or (
            os.name != "nt"
            and hasattr(os, "getuid")
            and observed.st_uid != os.getuid()
        )
    ):
        raise FormalTerminalDispositionBuildError(
            "terminal artifact is not an owned private bounded regular file"
        )
    return (
        str(path),
        observed.st_dev,
        observed.st_ino,
        observed.st_size,
        observed.st_mtime_ns,
        observed.st_ctime_ns,
        stat.S_IMODE(observed.st_mode),
    )


def _open_read_descriptor(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags)
    except OSError as exc:
        raise FormalTerminalDispositionBuildError(
            "terminal artifact could not be opened without following links"
        ) from exc


def _read_private_file(
    path: Path, *, maximum_bytes: int
) -> tuple[bytes, tuple[object, ...]]:
    before = _file_fingerprint(path, maximum_bytes=maximum_bytes)
    descriptor = _open_read_descriptor(path)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before[1], before[2]):
            raise FormalTerminalDispositionBuildError(
                "terminal artifact changed before open"
            )
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after_open = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = _file_fingerprint(path, maximum_bytes=maximum_bytes)
    if (
        before != after
        or (after_open.st_dev, after_open.st_ino, after_open.st_size)
        != (before[1], before[2], before[3])
        or len(payload) != before[3]
        or len(payload) > maximum_bytes
    ):
        raise FormalTerminalDispositionBuildError(
            "terminal artifact changed while read"
        )
    return payload, after


def _hash_private_file(
    path: Path, *, maximum_bytes: int
) -> tuple[str, int, tuple[object, ...]]:
    before = _file_fingerprint(path, maximum_bytes=maximum_bytes)
    descriptor = _open_read_descriptor(path)
    digest = hashlib.sha256()
    count = 0
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before[1], before[2]):
            raise FormalTerminalDispositionBuildError(
                "terminal spool changed before open"
            )
        while True:
            chunk = os.read(descriptor, 65_536)
            if not chunk:
                break
            count += len(chunk)
            if count > maximum_bytes:
                raise FormalTerminalDispositionCapacityRefusal(
                    "terminal SQLite spool exceeded its fixed byte ceiling"
                )
            digest.update(chunk)
        after_open = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = _file_fingerprint(path, maximum_bytes=maximum_bytes)
    if (
        before != after
        or count != before[3]
        or (after_open.st_dev, after_open.st_ino, after_open.st_size)
        != (before[1], before[2], before[3])
    ):
        raise FormalTerminalDispositionBuildError(
            "terminal SQLite spool changed while hashed"
        )
    return digest.hexdigest(), count, after


def _directory_names(path: Path) -> frozenset[str]:
    before = _directory_identity(path)
    try:
        names: set[str] = set()
        for item in path.iterdir():
            names.add(item.name)
            if len(names) > MAX_TERMINAL_ARTIFACT_FILE_COUNT:
                raise FormalTerminalDispositionCapacityRefusal(
                    "terminal artifact inventory exceeded its fixed ceiling"
                )
    except OSError as exc:
        raise FormalTerminalDispositionBuildError(
            "terminal artifact inventory is unavailable"
        ) from exc
    if _directory_identity(path) != before:
        raise FormalTerminalDispositionBuildError(
            "terminal artifact directory changed while inventoried"
        )
    return frozenset(names)


def _write_private_file(path: Path, payload: bytes) -> tuple[object, ...]:
    if type(payload) is not bytes or not payload:
        raise FormalTerminalDispositionBuildError(
            "terminal artifact payload must be nonempty exact bytes"
        )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short terminal artifact write")
            offset += written
        os.fsync(descriptor)
    except OSError as exc:
        raise FormalTerminalDispositionBuildError(
            "immutable terminal artifact write failed"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    reloaded, fingerprint = _read_private_file(
        path, maximum_bytes=max(1, len(payload))
    )
    if reloaded != payload:
        raise FormalTerminalDispositionBuildError(
            "immutable terminal artifact changed after write"
        )
    return fingerprint


def _sqlite_bytes(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA page_count").fetchone()
    size = connection.execute("PRAGMA page_size").fetchone()
    if (
        type(row) is not tuple
        or type(size) is not tuple
        or len(row) != 1
        or len(size) != 1
        or type(row[0]) is not int
        or type(size[0]) is not int
    ):
        raise FormalTerminalDispositionBuildError(
            "terminal SQLite capacity counters changed type"
        )
    observed = row[0] * size[0]
    if observed > MAX_SQLITE_SPOOL_BYTES:
        raise FormalTerminalDispositionCapacityRefusal(
            "terminal SQLite spool exceeded its fixed byte ceiling"
        )
    return observed


def _create_spool(root: Path) -> tuple[sqlite3.Connection, Path]:
    path = root / _SPOOL_NAME
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        created = os.fstat(descriptor)
    except OSError as exc:
        raise FormalTerminalDispositionBuildError(
            "terminal SQLite spool could not be created exclusively"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    connection = sqlite3.connect(
        "file:"
        + quote(str(path), safe="/")
        + "?mode=rw&nofollow=1",
        uri=True,
        isolation_level=None,
        check_same_thread=False,
    )
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA temp_store=FILE")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "CREATE TABLE axis("
            "session TEXT PRIMARY KEY, ordinal INTEGER NOT NULL UNIQUE, "
            "decision_open_utc TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE source_coordinate("
            "session_ordinal INTEGER NOT NULL, source_ordinal INTEGER NOT NULL, "
            "session TEXT NOT NULL, "
            "PRIMARY KEY(session_ordinal, source_ordinal))"
        )
        connection.execute(
            "CREATE TABLE lifecycle("
            "security_id TEXT NOT NULL, session TEXT NOT NULL, "
            "session_ordinal INTEGER NOT NULL, source_ordinal INTEGER NOT NULL, "
            "usable INTEGER NOT NULL, identity_token TEXT NOT NULL, "
            "terminal_date TEXT, available_at TEXT, binding_sha256 TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX lifecycle_security_order ON lifecycle("
            "security_id, session_ordinal, source_ordinal)"
        )
        connection.execute(
            "CREATE INDEX lifecycle_security_interval ON lifecycle("
            "security_id, session_ordinal, usable)"
        )
        connection.execute(
            "CREATE TABLE security_summary("
            "security_id TEXT PRIMARY KEY, status TEXT NOT NULL, reason TEXT, "
            "terminal_date TEXT, terminal_available_at TEXT, "
            "first_session TEXT NOT NULL, last_session TEXT NOT NULL, "
            "first_ordinal INTEGER NOT NULL, last_ordinal INTEGER NOT NULL, "
            "row_count INTEGER NOT NULL, distinct_session_count INTEGER NOT NULL, "
            "lineage_sha256 TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE actual_security(security_id TEXT PRIMARY KEY)"
        )
        connection.execute(
            "CREATE TABLE actual_slot("
            "slot_kind TEXT NOT NULL, slot_id TEXT NOT NULL, "
            "horizon_key INTEGER NOT NULL, horizon INTEGER, "
            "security_id TEXT NOT NULL, first_session TEXT NOT NULL, "
            "last_session TEXT NOT NULL, first_ordinal INTEGER NOT NULL, "
            "last_ordinal INTEGER NOT NULL, "
            "PRIMARY KEY(slot_kind, slot_id, horizon_key), "
            "FOREIGN KEY(security_id) REFERENCES actual_security(security_id))"
        )
    except Exception:
        connection.close()
        raise
    os.chmod(path, 0o600)
    fingerprint = _file_fingerprint(path, maximum_bytes=MAX_SQLITE_SPOOL_BYTES)
    if (fingerprint[1], fingerprint[2]) != (created.st_dev, created.st_ino):
        connection.close()
        raise FormalTerminalDispositionBuildError(
            "terminal SQLite spool changed between exclusive creation and open"
        )
    return connection, path


def _canonical_object(payload: bytes, name: str) -> dict[str, Any]:
    if type(payload) is not bytes or not payload:
        raise FormalTerminalDispositionBuildError(f"{name} is absent")
    try:
        value = strict_json_loads(payload.decode("utf-8"), name)
    except (CanonicalEvidenceError, UnicodeError, ValueError) as exc:
        raise FormalTerminalDispositionBuildError(
            f"{name} is not strict UTF-8 JSON"
        ) from exc
    if type(value) is not dict or canonical_json_bytes(value) != payload:
        raise FormalTerminalDispositionBuildError(
            f"{name} is not one canonical JSON object"
        )
    return value


def _nullable_text(value: object, name: str, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    try:
        return require_text(value, name, maximum_length=maximum)
    except CanonicalEvidenceError as exc:
        raise FormalTerminalDispositionBuildError(
            f"{name} is not bounded canonical text"
        ) from exc


def _validate_lifecycle_row(line: bytes) -> dict[str, Any]:
    if (
        type(line) is not bytes
        or not line.endswith(b"\n")
        or len(line) > MAX_LIFECYCLE_ROW_BYTES
    ):
        raise FormalTerminalDispositionBuildError(
            "lifecycle sidecar row exceeds its canonical bound"
        )
    row = _canonical_object(line, "lifecycle sidecar row")
    if set(row) != _LIFECYCLE_FIELDS:
        raise FormalTerminalDispositionBuildError(
            "lifecycle sidecar row fields changed"
        )
    semantic = dict(row)
    declared = semantic.pop("binding_sha256")
    try:
        require_sha256(declared, "lifecycle binding hash")
        require_sha256(row["source_terminal_sha256"], "source terminal hash")
        if row["identity_evidence_sha256"] is not None:
            require_sha256(
                row["identity_evidence_sha256"], "identity evidence hash"
            )
        if row["mapping_row_sha256"] is not None:
            require_sha256(row["mapping_row_sha256"], "mapping row hash")
        session = parse_date(row["decision_session"], "lifecycle session")
        opened = parse_utc_timestamp(
            row["decision_open_utc"], "lifecycle decision open"
        )
        ordinal = require_int(
            row["decision_session_ordinal"],
            "lifecycle session ordinal",
            minimum=1,
        )
        require_int(row["source_ordinal"], "lifecycle source ordinal", minimum=0)
        require_exact_bool(row["lifecycle_evidence_only"], "lifecycle evidence flag")
        require_exact_bool(row["payoff_semantics_assigned"], "payoff semantics flag")
    except CanonicalEvidenceError as exc:
        raise FormalTerminalDispositionBuildError(
            "lifecycle sidecar scalar changed"
        ) from exc
    if (
        row["schema"] != historical_module.UNIVERSE_LIFECYCLE_BINDING_SCHEMA
        or declared != sha256_bytes(canonical_json_bytes(semantic))
        or row["lifecycle_evidence_only"] is not True
        or row["payoff_semantics_assigned"] is not False
        or row["discovery_disposition"]
        not in {"accepted", "out_of_scope", "named_refusal"}
        or row["bridge_join_disposition"]
        not in {"accepted", "named_refusal", "not_applicable_discovery_terminal"}
    ):
        raise FormalTerminalDispositionBuildError(
            "lifecycle sidecar identity or disposition changed"
        )
    if opened.date() != session:
        raise FormalTerminalDispositionBuildError(
            "lifecycle session and decision-open date disagree"
        )
    terminal_date = row["delisting_date"]
    if terminal_date is not None:
        try:
            parse_date(terminal_date, "delisting date")
        except CanonicalEvidenceError as exc:
            raise FormalTerminalDispositionBuildError(
                "lifecycle delisting date changed"
            ) from exc
    available_at = row["available_at"]
    if available_at is not None:
        try:
            parse_utc_timestamp(available_at, "lifecycle availability")
        except CanonicalEvidenceError as exc:
            raise FormalTerminalDispositionBuildError(
                "lifecycle availability changed"
            ) from exc
    for name in (
        "discovery_refusal_reason",
        "qc_security_id",
        "cusip",
        "display_ticker_non_authoritative",
        "logical_security_id",
        "issuer_id",
        "share_class_id",
        "listing_id",
        "bridge_join_reason",
    ):
        _nullable_text(row[name], name)
    usable = (
        row["discovery_disposition"] == "accepted"
        and row["discovery_refusal_reason"] is None
        and row["bridge_join_disposition"] == "accepted"
        and row["bridge_join_reason"] is None
        and row["logical_security_id"] is not None
        and row["qc_security_id"] is not None
        and row["cusip"] is not None
        and row["issuer_id"] is not None
        and row["share_class_id"] is not None
        and row["listing_id"] is not None
        and row["mapping_row_sha256"] is not None
        and row["identity_evidence_sha256"] is not None
        and row["available_at"] is not None
    )
    if row["bridge_join_disposition"] == "accepted" and not usable:
        raise FormalTerminalDispositionBuildError(
            "accepted lifecycle sidecar row is structurally incomplete"
        )
    row["_usable"] = usable
    row["_identity_token"] = sha256_bytes(
        canonical_json_bytes(
            {
                "logical_security_id": row["logical_security_id"],
                "qc_security_id": row["qc_security_id"],
                "cusip": row["cusip"],
                "issuer_id": row["issuer_id"],
                "share_class_id": row["share_class_id"],
                "listing_id": row["listing_id"],
                "mapping_row_sha256": row["mapping_row_sha256"],
            }
        )
    )
    return row


def _ingest_lifecycle_sidecar(
    connection: sqlite3.Connection,
    bridge: historical_module.ReviewedHistoricalUniverseToPreopenBridge,
) -> tuple[int, int, int]:
    row_count = 0
    shard_count = 0
    logical_row_count = 0
    connection.execute("BEGIN IMMEDIATE")
    try:
        for expected_shard, shard in enumerate(
            historical_module.iter_reviewed_historical_universe_lifecycle_binding_shards(
                bridge
            )
        ):
            try:
                require_sha256(
                    shard.compressed_sha256, "lifecycle shard compressed hash"
                )
                require_sha256(
                    shard.uncompressed_sha256, "lifecycle shard uncompressed hash"
                )
            except (AttributeError, CanonicalEvidenceError) as exc:
                raise FormalTerminalDispositionBuildError(
                    "authenticated lifecycle sidecar shard hash changed"
                ) from exc
            if (
                type(shard)
                is not historical_module.ReviewedHistoricalUniverseLifecycleBindingShard
                or shard.ordinal != expected_shard
                or type(shard.row_count) is not int
                or shard.row_count < 1
                or type(shard.compressed_byte_count) is not int
                or shard.compressed_byte_count < 1
                or shard.compressed_byte_count
                > historical_module.MAX_EVIDENCE_COMPRESSED_BYTES
                or type(shard.uncompressed_byte_count) is not int
                or shard.uncompressed_byte_count < 1
                or type(shard.canonical_json_lines) is not bytes
                or len(shard.canonical_json_lines) != shard.uncompressed_byte_count
                or sha256_bytes(shard.canonical_json_lines)
                != shard.uncompressed_sha256
                or len(shard.canonical_json_lines)
                > historical_module.MAX_EVIDENCE_UNCOMPRESSED_BYTES
            ):
                raise FormalTerminalDispositionBuildError(
                    "authenticated lifecycle sidecar shard changed"
                )
            shard_rows = 0
            for line in shard.canonical_json_lines.splitlines(keepends=True):
                row = _validate_lifecycle_row(line)
                existing = connection.execute(
                    "SELECT ordinal, decision_open_utc FROM axis WHERE session = ?",
                    (row["decision_session"],),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO axis(session, ordinal, decision_open_utc) "
                        "VALUES (?, ?, ?)",
                        (
                            row["decision_session"],
                            row["decision_session_ordinal"],
                            row["decision_open_utc"],
                        ),
                    )
                elif existing != (
                    row["decision_session_ordinal"],
                    row["decision_open_utc"],
                ):
                    raise FormalTerminalDispositionBuildError(
                        "lifecycle full-axis geometry is inconsistent"
                    )
                try:
                    connection.execute(
                        "INSERT INTO source_coordinate("
                        "session_ordinal, source_ordinal, session) "
                        "VALUES (?, ?, ?)",
                        (
                            row["decision_session_ordinal"],
                            row["source_ordinal"],
                            row["decision_session"],
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise FormalTerminalDispositionBuildError(
                        "lifecycle source coordinate repeated"
                    ) from exc
                logical = row["logical_security_id"]
                if logical is not None:
                    security_id = _safe_security(logical, "lifecycle security_id")
                    connection.execute(
                        "INSERT INTO lifecycle("
                        "security_id, session, session_ordinal, source_ordinal, "
                        "usable, identity_token, terminal_date, available_at, "
                        "binding_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            security_id,
                            row["decision_session"],
                            row["decision_session_ordinal"],
                            row["source_ordinal"],
                            int(row["_usable"]),
                            row["_identity_token"],
                            row["delisting_date"],
                            row["available_at"],
                            row["binding_sha256"],
                        ),
                    )
                    logical_row_count += 1
                row_count += 1
                shard_rows += 1
                if row_count > MAX_LIFECYCLE_ROW_COUNT:
                    raise FormalTerminalDispositionCapacityRefusal(
                        "lifecycle sidecar row count exceeded its fixed ceiling"
                    )
                if row_count % 4096 == 0:
                    _sqlite_bytes(connection)
            if shard_rows != shard.row_count:
                raise FormalTerminalDispositionBuildError(
                    "lifecycle sidecar shard row census changed"
                )
            shard_count += 1
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    if (
        row_count != bridge.universe_lifecycle_binding_row_count
        or shard_count != bridge.universe_lifecycle_binding_shard_count
    ):
        raise FormalTerminalDispositionBuildError(
            "lifecycle sidecar inventory is not exhaustive"
        )
    return row_count, shard_count, logical_row_count


def _validate_full_axis(
    connection: sqlite3.Connection,
    bridge: historical_module.ReviewedHistoricalUniverseToPreopenBridge,
) -> int:
    first = parse_date(bridge.first_session, "bridge first session")
    last = parse_date(bridge.last_session, "bridge last session")
    expected = tuple(item.isoformat() for item in trading_sessions(first, last))
    observed = tuple(
        (row[0], row[1])
        for row in connection.execute(
            "SELECT session, ordinal FROM axis ORDER BY ordinal"
        )
    )
    if observed != tuple((session, index) for index, session in enumerate(expected, 1)):
        raise FormalTerminalDispositionBuildError(
            "lifecycle sidecar does not cover the exact exchange-session axis"
        )
    source_geometry = tuple(
        connection.execute(
            "SELECT session_ordinal, COUNT(*), MIN(source_ordinal), "
            "MAX(source_ordinal), COUNT(DISTINCT source_ordinal) "
            "FROM source_coordinate GROUP BY session_ordinal "
            "ORDER BY session_ordinal"
        )
    )
    if (
        len(source_geometry) != len(expected)
        or any(
            ordinal != expected_ordinal
            or count < 1
            or minimum != 0
            or maximum != count - 1
            or distinct != count
            for expected_ordinal, (
                ordinal,
                count,
                minimum,
                maximum,
                distinct,
            ) in enumerate(source_geometry, 1)
        )
    ):
        raise FormalTerminalDispositionBuildError(
            "lifecycle sidecar source-coordinate census is not exhaustive"
        )
    return len(expected)


def _new_chain(domain: str) -> Any:
    value = hashlib.sha256()
    value.update(domain.encode("ascii") + b"\0")
    return value


def _chain_add(value: Any, record: Mapping[str, object]) -> None:
    payload = canonical_json_bytes(dict(record))
    value.update(len(payload).to_bytes(8, "big"))
    value.update(payload)


def _build_security_summaries(connection: sqlite3.Connection) -> int:
    current_security: str | None = None
    count = 0
    row_count = 0
    distinct_session_count = 0
    first_session: str | None = None
    last_session: str | None = None
    first_ordinal: int | None = None
    last_ordinal: int | None = None
    prior_ordinal: int | None = None
    identity_token: str | None = None
    identity_changed = False
    all_usable = True
    terminal_date: str | None = None
    terminal_changed = False
    terminal_seen = False
    terminal_reverted = False
    first_terminal_available: str | None = None
    chain = _new_chain("arv2-lifecycle-security-row-census-v1")

    def flush() -> None:
        nonlocal count
        if current_security is None:
            return
        if (
            first_session is None
            or last_session is None
            or first_ordinal is None
            or last_ordinal is None
            or row_count < 1
            or distinct_session_count < 1
        ):
            raise FormalTerminalDispositionBuildError(
                "lifecycle security summary is empty"
            )
        reason: str | None = None
        status = "known_terminal" if terminal_date is not None else "active_observed"
        if (
            not all_usable
            or identity_changed
            or row_count != distinct_session_count
            or terminal_changed
            or terminal_reverted
            or (terminal_date is not None and terminal_date < first_session)
        ):
            status = "ambiguous"
            reason = _AMBIGUOUS_LIFECYCLE_REASON
        connection.execute(
            "INSERT INTO security_summary("
            "security_id, status, reason, terminal_date, terminal_available_at, "
            "first_session, last_session, first_ordinal, last_ordinal, row_count, "
            "distinct_session_count, lineage_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                current_security,
                status,
                reason,
                terminal_date,
                first_terminal_available,
                first_session,
                last_session,
                first_ordinal,
                last_ordinal,
                row_count,
                distinct_session_count,
                chain.hexdigest(),
            ),
        )
        count += 1
        if count > MAX_ACTUAL_SECURITY_COUNT:
            raise FormalTerminalDispositionCapacityRefusal(
                "lifecycle security count exceeded its fixed ceiling"
            )

    def reset() -> None:
        nonlocal row_count, distinct_session_count
        nonlocal first_session, last_session, first_ordinal, last_ordinal
        nonlocal prior_ordinal, identity_token, identity_changed, all_usable
        nonlocal terminal_date, terminal_changed, terminal_seen
        nonlocal terminal_reverted, first_terminal_available, chain
        row_count = 0
        distinct_session_count = 0
        first_session = None
        last_session = None
        first_ordinal = None
        last_ordinal = None
        prior_ordinal = None
        identity_token = None
        identity_changed = False
        all_usable = True
        terminal_date = None
        terminal_changed = False
        terminal_seen = False
        terminal_reverted = False
        first_terminal_available = None
        chain = _new_chain("arv2-lifecycle-security-row-census-v1")

    connection.execute("BEGIN IMMEDIATE")
    try:
        for item in connection.execute(
            "SELECT security_id, session, session_ordinal, source_ordinal, "
            "usable, identity_token, terminal_date, available_at, binding_sha256 "
            "FROM lifecycle ORDER BY security_id, session_ordinal, source_ordinal"
        ):
            security = str(item[0])
            if current_security is not None and security != current_security:
                flush()
                reset()
            current_security = security
            (
                session,
                ordinal,
                source_ordinal,
                usable,
                observed_identity,
                observed_terminal,
                available_at,
                binding_sha256,
            ) = tuple(item[1:])
            session = str(session)
            ordinal = int(ordinal)
            observed_identity = str(observed_identity)
            row_count += 1
            if prior_ordinal != ordinal:
                distinct_session_count += 1
            prior_ordinal = ordinal
            if first_session is None:
                first_session = session
                first_ordinal = ordinal
            last_session = session
            last_ordinal = ordinal
            if identity_token is None:
                identity_token = observed_identity
            elif identity_token != observed_identity:
                identity_changed = True
            all_usable = all_usable and usable == 1
            if observed_terminal is not None:
                observed_terminal = str(observed_terminal)
                terminal_seen = True
                if terminal_date is None:
                    terminal_date = observed_terminal
                elif terminal_date != observed_terminal:
                    terminal_changed = True
                if available_at is not None and (
                    first_terminal_available is None
                    or str(available_at) < first_terminal_available
                ):
                    first_terminal_available = str(available_at)
            elif terminal_seen:
                terminal_reverted = True
            _chain_add(
                chain,
                {
                    "binding_sha256": binding_sha256,
                    "session": session,
                    "session_ordinal": ordinal,
                    "source_ordinal": source_ordinal,
                },
            )
        flush()
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return count


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalTerminalDispositionRecorder:
    schema: str
    historical_bridge: historical_module.ReviewedHistoricalUniverseToPreopenBridge
    historical_bridge_id: str
    historical_bridge_sha256: str
    lifecycle_inventory_sha256: str
    lifecycle_shard_count: int
    lifecycle_row_count: int
    logical_lifecycle_row_count: int
    lifecycle_security_count: int
    session_axis_count: int
    output_directory: Path = dataclasses.field(repr=False)


@dataclasses.dataclass
class _RecorderState:
    reference: weakref.ReferenceType[FormalTerminalDispositionRecorder]
    connection: sqlite3.Connection
    spool_path: Path
    directory_identity: tuple[int, int, int, int]
    spool_fingerprint: tuple[object, ...]
    status: str
    slot_count: int = 0
    record_calls: int = 0


_RECORDERS: dict[int, _RecorderState] = {}
_RECORDER_LOCK = threading.RLock()


def _forget_recorder(identity: int, reference: object) -> None:
    with _RECORDER_LOCK:
        state = _RECORDERS.get(identity)
        if state is not None and state.reference is reference:
            try:
                state.connection.close()
            finally:
                _RECORDERS.pop(identity, None)


def _recorder_fingerprint(value: FormalTerminalDispositionRecorder) -> tuple[object, ...]:
    return (
        value.schema,
        id(value.historical_bridge),
        value.historical_bridge_id,
        value.historical_bridge_sha256,
        value.lifecycle_inventory_sha256,
        value.lifecycle_shard_count,
        value.lifecycle_row_count,
        value.logical_lifecycle_row_count,
        value.lifecycle_security_count,
        value.session_axis_count,
        id(value.output_directory),
        str(value.output_directory),
    )


def _require_recorder(
    value: FormalTerminalDispositionRecorder,
    *,
    require_fresh: bool = False,
) -> tuple[FormalTerminalDispositionRecorder, _RecorderState]:
    if type(value) is not FormalTerminalDispositionRecorder:
        raise FormalTerminalDispositionBuildError("terminal recorder changed type")
    with _RECORDER_LOCK:
        state = _RECORDERS.get(id(value))
    if state is None or state.reference() is not value:
        raise FormalTerminalDispositionBuildError(
            "terminal recorder is not builder-authenticated"
        )
    if (
        value.schema != RECORDER_SCHEMA
        or state.status != "recording"
        or _directory_identity(value.output_directory) != state.directory_identity
        or _directory_names(value.output_directory) != frozenset({_SPOOL_NAME})
        or _file_fingerprint(
            state.spool_path, maximum_bytes=MAX_SQLITE_SPOOL_BYTES
        )
        != state.spool_fingerprint
    ):
        raise FormalTerminalDispositionBuildError(
            "terminal recorder storage or lifecycle identity changed"
        )
    if require_fresh:
        security_count = state.connection.execute(
            "SELECT COUNT(*) FROM actual_security"
        ).fetchone()[0]
        slot_count = state.connection.execute(
            "SELECT COUNT(*) FROM actual_slot"
        ).fetchone()[0]
        if security_count != 0 or slot_count != 0 or state.slot_count != 0:
            raise FormalTerminalDispositionBuildError(
                "terminal recorder must be fresh before streamed slot emission"
            )
    return value, state


def require_fresh_formal_terminal_disposition_recorder(
    value: FormalTerminalDispositionRecorder,
) -> FormalTerminalDispositionRecorder:
    """Authenticate a recorder and prove no caller predeclared a slot."""

    with _RECORDER_LOCK:
        return _require_recorder(value, require_fresh=True)[0]


def begin_formal_terminal_disposition_recording(
    *,
    historical_bridge: historical_module.ReviewedHistoricalUniverseToPreopenBridge,
    output_directory: Path,
) -> FormalTerminalDispositionRecorder:
    """Authenticate and disk-spool the complete lifecycle sidecar once."""

    try:
        bridge = historical_module.require_reviewed_historical_universe_to_preopen_bridge(
            historical_bridge
        )
    except (TypeError, ValueError) as exc:
        raise FormalTerminalDispositionBuildError(
            "historical lifecycle bridge did not authenticate"
        ) from exc
    root = _exact_path(output_directory, "terminal artifact directory")
    if root.exists():
        if root.is_symlink() or _directory_names(root):
            raise FormalTerminalDispositionBuildError(
                "terminal artifact directory must be absent or empty"
            )
    else:
        try:
            root.mkdir(mode=0o700, parents=False)
        except OSError as exc:
            raise FormalTerminalDispositionBuildError(
                "terminal artifact directory could not be created"
            ) from exc
    if os.name != "nt":
        os.chmod(root, 0o700)
    directory_identity = _directory_identity(root)
    connection, spool_path = _create_spool(root)
    try:
        lifecycle_rows, lifecycle_shards, logical_rows = _ingest_lifecycle_sidecar(
            connection, bridge
        )
        axis_count = _validate_full_axis(connection, bridge)
        security_count = _build_security_summaries(connection)
        if (
            historical_module.require_reviewed_historical_universe_to_preopen_bridge(
                bridge
            )
            is not bridge
        ):
            raise FormalTerminalDispositionBuildError(
                "historical lifecycle bridge identity changed during ingestion"
            )
        _sqlite_bytes(connection)
        connection.execute("BEGIN IMMEDIATE")
    except Exception:
        connection.close()
        raise
    spool_fingerprint = _file_fingerprint(
        spool_path, maximum_bytes=MAX_SQLITE_SPOOL_BYTES
    )
    value = object.__new__(FormalTerminalDispositionRecorder)
    fields: dict[str, object] = {
        "schema": RECORDER_SCHEMA,
        "historical_bridge": bridge,
        "historical_bridge_id": bridge.bridge_id,
        "historical_bridge_sha256": bridge.bridge_sha256,
        "lifecycle_inventory_sha256": (
            bridge.universe_lifecycle_binding_inventory_sha256
        ),
        "lifecycle_shard_count": lifecycle_shards,
        "lifecycle_row_count": lifecycle_rows,
        "logical_lifecycle_row_count": logical_rows,
        "lifecycle_security_count": security_count,
        "session_axis_count": axis_count,
        "output_directory": root,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_recorder(key, ref)
    )
    state = _RecorderState(
        reference=reference,
        connection=connection,
        spool_path=spool_path,
        directory_identity=directory_identity,
        spool_fingerprint=spool_fingerprint,
        status="recording",
    )
    with _RECORDER_LOCK:
        _RECORDERS[identity] = state
    require_fresh_formal_terminal_disposition_recorder(value)
    return value


def _after_recorder_write(state: _RecorderState) -> None:
    state.record_calls += 1
    if state.record_calls % 1024 == 0:
        _sqlite_bytes(state.connection)
    state.spool_fingerprint = _file_fingerprint(
        state.spool_path, maximum_bytes=MAX_SQLITE_SPOOL_BYTES
    )


def record_formal_terminal_security(
    value: FormalTerminalDispositionRecorder,
    *,
    security_id: str,
) -> None:
    """Record one builder-derived member of the streamed security census."""

    security = _safe_security(security_id)
    with _RECORDER_LOCK:
        _, state = _require_recorder(value)
        state.connection.execute(
            "INSERT OR IGNORE INTO actual_security(security_id) VALUES (?)",
            (security,),
        )
        count = state.connection.execute(
            "SELECT COUNT(*) FROM actual_security"
        ).fetchone()[0]
        if type(count) is not int or count > MAX_ACTUAL_SECURITY_COUNT:
            raise FormalTerminalDispositionCapacityRefusal(
                "actual security census exceeded its fixed ceiling"
            )
        _after_recorder_write(state)


def _axis_ordinal(
    connection: sqlite3.Connection,
    session: date,
    name: str,
    *,
    required: bool,
) -> int | None:
    if type(session) is not date:
        raise FormalTerminalDispositionBuildError(f"{name} changed type")
    row = connection.execute(
        "SELECT ordinal FROM axis WHERE session = ?", (session.isoformat(),)
    ).fetchone()
    if row is None:
        if not required:
            return None
        raise FormalTerminalDispositionBuildError(
            f"{name} is outside the authenticated lifecycle axis"
        )
    if type(row[0]) is not int:
        raise FormalTerminalDispositionBuildError(
            f"{name} lifecycle ordinal changed type"
        )
    return row[0]


def _slot_ordinals(
    connection: sqlite3.Connection,
    *,
    first_session: date,
    last_session: date,
    expected_steps: int,
) -> tuple[int, int]:
    if (
        type(first_session) is not date
        or type(last_session) is not date
        or type(expected_steps) is not int
        or expected_steps < 1
        or last_session <= first_session
    ):
        raise FormalTerminalDispositionBuildError(
            "terminal slot session interval changed type or order"
        )
    try:
        outcome_axis, outcome_positions = _formal_outcome_axis()
    except (TypeError, ValueError) as exc:
        raise FormalTerminalDispositionBuildError(
            "reviewed formal outcome axis cannot be authenticated"
        ) from exc
    first_position = outcome_positions.get(first_session)
    last_position = outcome_positions.get(last_session)
    if (
        type(outcome_axis) is not tuple
        or type(first_position) is not int
        or type(last_position) is not int
        or last_position - first_position != expected_steps
    ):
        raise FormalTerminalDispositionBuildError(
            "terminal slot does not span the declared reviewed outcome-axis count"
        )
    first_ordinal = _axis_ordinal(
        connection,
        first_session,
        "terminal slot first_session",
        required=True,
    )
    assert first_ordinal is not None
    observed_last = _axis_ordinal(
        connection,
        last_session,
        "terminal slot last_session",
        required=False,
    )
    projected_last = first_ordinal + expected_steps
    if observed_last is not None and observed_last != projected_last:
        raise FormalTerminalDispositionBuildError(
            "terminal slot disagrees with authenticated lifecycle ordinals"
        )
    if observed_last is None:
        final_axis = connection.execute(
            "SELECT session FROM axis ORDER BY ordinal DESC LIMIT 1"
        ).fetchone()
        if (
            final_axis is None
            or type(final_axis[0]) is not str
            or last_session.isoformat() <= final_axis[0]
        ):
            raise FormalTerminalDispositionBuildError(
                "terminal slot falls into an unexplained lifecycle-axis hole"
            )
    return first_ordinal, projected_last


def record_formal_terminal_slot(
    value: FormalTerminalDispositionRecorder,
    *,
    slot_kind: str,
    slot_id: str,
    horizon_sessions: int | None,
    security_id: str,
    first_session: date,
    last_session: date,
) -> bool:
    """Record one exact slot emitted by the streamed formal builder."""

    if type(slot_kind) is not str or slot_kind not in _SLOT_KINDS:
        raise FormalTerminalDispositionBuildError("terminal slot kind changed")
    slot = _safe_slot_id(slot_id)
    security = _safe_security(security_id)
    with _RECORDER_LOCK:
        _, state = _require_recorder(value)
        if state.connection.execute(
            "SELECT 1 FROM actual_security WHERE security_id = ?", (security,)
        ).fetchone() is None:
            raise FormalTerminalDispositionBuildError(
                "terminal slot security was not emitted into the streamed census"
            )
        if slot_kind == "decision_horizon":
            if (
                type(horizon_sessions) is not int
                or horizon_sessions not in HORIZONS
            ):
                raise FormalTerminalDispositionBuildError(
                    "decision terminal slot horizon does not match the lifecycle axis"
                )
            horizon_key = horizon_sessions
            first_ordinal, last_ordinal = _slot_ordinals(
                state.connection,
                first_session=first_session,
                last_session=last_session,
                expected_steps=horizon_sessions,
            )
        else:
            if horizon_sessions is not None:
                raise FormalTerminalDispositionBuildError(
                    "economic terminal slot is not one exact session interval"
                )
            horizon_key = -1
            first_ordinal, last_ordinal = _slot_ordinals(
                state.connection,
                first_session=first_session,
                last_session=last_session,
                expected_steps=1,
            )
        record = (
            horizon_sessions,
            security,
            first_session.isoformat(),
            last_session.isoformat(),
            first_ordinal,
            last_ordinal,
        )
        existing = state.connection.execute(
            "SELECT horizon, security_id, first_session, last_session, "
            "first_ordinal, last_ordinal FROM actual_slot "
            "WHERE slot_kind = ? AND slot_id = ? AND horizon_key = ?",
            (slot_kind, slot, horizon_key),
        ).fetchone()
        if existing is not None:
            if tuple(existing) == record:
                return False
            raise FormalTerminalDispositionBuildError(
                "terminal slot repeated with different builder-derived geometry"
            )
        state.connection.execute(
            "INSERT INTO actual_slot("
            "slot_kind, slot_id, horizon_key, horizon, security_id, "
            "first_session, last_session, first_ordinal, last_ordinal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (slot_kind, slot, horizon_key, *record),
        )
        state.slot_count += 1
        if state.slot_count > MAX_ACTUAL_SLOT_COUNT:
            raise FormalTerminalDispositionCapacityRefusal(
                "actual terminal slot census exceeded its fixed ceiling"
            )
        _after_recorder_write(state)
        return True


def _summary_row(
    connection: sqlite3.Connection, security_id: str
) -> tuple[object, ...] | None:
    return connection.execute(
        "SELECT status, reason, terminal_date, terminal_available_at, "
        "first_session, last_session, first_ordinal, last_ordinal, row_count, "
        "distinct_session_count, lineage_sha256 FROM security_summary "
        "WHERE security_id = ?",
        (security_id,),
    ).fetchone()


def _security_status(summary: tuple[object, ...] | None) -> str:
    if summary is None:
        return "missing"
    if summary[0] == "ambiguous":
        return "ambiguous"
    if summary[0] == "known_terminal":
        return "known_terminal"
    if summary[0] == "active_observed":
        return "active_observed"
    raise FormalTerminalDispositionBuildError(
        "lifecycle security summary disposition changed"
    )


def _classify_slot(
    connection: sqlite3.Connection,
    row: tuple[object, ...],
    *,
    calculation_available_at: str,
) -> tuple[str | None, str | None, str | None]:
    (
        _slot_kind,
        _slot_id,
        _horizon,
        security_id,
        _first_session,
        last_session,
        first_ordinal,
        last_ordinal,
    ) = row
    summary = _summary_row(connection, str(security_id))
    status = _security_status(summary)
    if status == "missing":
        return _MISSING_LIFECYCLE_REASON, calculation_available_at, None
    assert summary is not None
    if status == "ambiguous":
        return _AMBIGUOUS_LIFECYCLE_REASON, calculation_available_at, str(summary[10])
    terminal_date = summary[2]
    terminal_available = summary[3]
    if terminal_date is not None and str(terminal_date) <= str(last_session):
        if terminal_available is None or str(terminal_available) > calculation_available_at:
            return _MISSING_LIFECYCLE_REASON, calculation_available_at, str(summary[10])
        return _KNOWN_TERMINAL_REASON, str(terminal_available), str(summary[10])
    coverage = connection.execute(
        "SELECT COUNT(*), COUNT(DISTINCT session_ordinal), "
        "COALESCE(SUM(usable), 0) FROM lifecycle "
        "WHERE security_id = ? AND session_ordinal BETWEEN ? AND ?",
        (security_id, first_ordinal, last_ordinal),
    ).fetchone()
    expected = int(last_ordinal) - int(first_ordinal) + 1
    if (
        coverage is None
        or any(type(item) is not int for item in coverage)
        or coverage != (expected, expected, expected)
    ):
        return _MISSING_LIFECYCLE_REASON, calculation_available_at, str(summary[10])
    return None, None, str(summary[10])


def _census_hash(
    connection: sqlite3.Connection, *, role: str
) -> tuple[str, int]:
    hasher = _new_chain(f"arv2-lifecycle-terminal-{role}-census-v1")
    count = 0
    if role == "security":
        query = "SELECT security_id FROM actual_security ORDER BY security_id"
        for (security_id,) in connection.execute(query):
            _chain_add(hasher, {"security_id": security_id})
            count += 1
    elif role == "slot":
        query = (
            "SELECT slot_kind, slot_id, horizon, security_id, first_session, "
            "last_session FROM actual_slot ORDER BY slot_kind, slot_id, horizon_key"
        )
        for item in connection.execute(query):
            _chain_add(
                hasher,
                {
                    "slot_kind": item[0],
                    "slot_id": item[1],
                    "horizon": item[2],
                    "security_id": item[3],
                    "first_session": item[4],
                    "last_session": item[5],
                },
            )
            count += 1
    else:
        raise FormalTerminalDispositionBuildError("terminal census role changed")
    return hasher.hexdigest(), count


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalTerminalDispositionBuild:
    build_id: str
    build_sha256: str
    schema: str
    status: str
    historical_bridge: historical_module.ReviewedHistoricalUniverseToPreopenBridge
    historical_bridge_id: str
    historical_bridge_sha256: str
    lifecycle_inventory_sha256: str
    lifecycle_shard_count: int
    lifecycle_row_count: int
    logical_lifecycle_row_count: int
    lifecycle_security_count: int
    session_axis_count: int
    terminal_package: FormalTerminalDispositionPackage
    terminal_census: TerminalCensusBinding
    security_count: int
    lifecycle_coverage_count: int
    lifecycle_active_security_count: int
    lifecycle_known_terminal_security_count: int
    lifecycle_missing_security_count: int
    lifecycle_ambiguous_security_count: int
    actual_slot_count: int
    unaffected_slot_count: int
    terminal_requirement_count: int
    known_terminal_refusal_count: int
    missing_lifecycle_refusal_count: int
    ambiguous_lifecycle_refusal_count: int
    security_census_sha256: str
    slot_census_sha256: str
    calculation_as_of_date: date
    sqlite_spool_sha256: str
    sqlite_spool_byte_count: int
    receipt_sha256: str
    receipt_byte_count: int
    terminal_input_complete: bool
    terminal_payoff_source_available: bool
    known_terminal_precedes_market_bars: bool
    qc_delisting_price_used: bool
    merger_bankruptcy_successor_payoff_inferred: bool
    silently_omitted_count: int
    capabilities: tuple[tuple[str, bool], ...]
    output_directory: Path = dataclasses.field(repr=False)
    sqlite_spool_path: Path = dataclasses.field(repr=False)
    terminal_package_path: Path = dataclasses.field(repr=False)
    receipt_path: Path = dataclasses.field(repr=False)
    _directory_identity: tuple[int, int, int, int] = dataclasses.field(repr=False)
    _spool_fingerprint: tuple[object, ...] = dataclasses.field(repr=False)
    _package_fingerprint: tuple[object, ...] = dataclasses.field(repr=False)
    _receipt_fingerprint: tuple[object, ...] = dataclasses.field(repr=False)
    _receipt_bytes: bytes = dataclasses.field(repr=False)


_BUILDS: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalTerminalDispositionBuild],
        bytes,
        tuple[object, ...],
    ],
] = {}
_BUILD_LOCK = threading.RLock()


def _forget_build(identity: int, reference: object) -> None:
    with _BUILD_LOCK:
        current = _BUILDS.get(identity)
        if current is not None and current[0] is reference:
            _BUILDS.pop(identity, None)


def _build_topology(value: FormalTerminalDispositionBuild) -> tuple[object, ...]:
    return (
        id(value.historical_bridge),
        id(value.terminal_package),
        id(value.terminal_census),
        id(value.terminal_census.census),
        id(value.capabilities),
        id(value.output_directory),
        id(value.sqlite_spool_path),
        id(value.terminal_package_path),
        id(value.receipt_path),
        id(value._receipt_bytes),
    )


def _build_semantic(
    *,
    recorder: FormalTerminalDispositionRecorder,
    package_id: str,
    package_sha256: str,
    package_byte_count: int,
    security_counts: Counter[str],
    actual_slot_count: int,
    unaffected_slot_count: int,
    refusal_counts: Counter[str],
    security_census_sha256: str,
    slot_census_sha256: str,
    calculation_as_of_date: date,
    spool_sha256: str,
    spool_byte_count: int,
) -> dict[str, object]:
    terminal_count = sum(refusal_counts.values())
    return {
        "schema": BUILD_SCHEMA,
        "status": BUILD_STATUS,
        "historical_bridge_id": recorder.historical_bridge_id,
        "historical_bridge_sha256": recorder.historical_bridge_sha256,
        "lifecycle_inventory_sha256": recorder.lifecycle_inventory_sha256,
        "lifecycle_sidecar_shard_count": recorder.lifecycle_shard_count,
        "lifecycle_sidecar_row_count": recorder.lifecycle_row_count,
        "logical_lifecycle_row_count": recorder.logical_lifecycle_row_count,
        "lifecycle_sidecar_security_count": recorder.lifecycle_security_count,
        "session_axis_count": recorder.session_axis_count,
        "terminal_package_id": package_id,
        "terminal_package_sha256": package_sha256,
        "terminal_package_byte_count": package_byte_count,
        "terminal_policy_id": TERMINAL_POLICY_ID,
        "security_count": sum(security_counts.values()),
        "lifecycle_coverage_count": sum(security_counts.values()),
        "lifecycle_active_security_count": security_counts["active_observed"],
        "lifecycle_known_terminal_security_count": security_counts["known_terminal"],
        "lifecycle_missing_security_count": security_counts["missing"],
        "lifecycle_ambiguous_security_count": security_counts["ambiguous"],
        "actual_slot_count": actual_slot_count,
        "unaffected_slot_count": unaffected_slot_count,
        "terminal_requirement_count": terminal_count,
        "terminal_payoff_count": 0,
        "benchmark_splice_continuation_count": 0,
        "named_terminal_refusal_count": terminal_count,
        "known_terminal_refusal_count": refusal_counts[_KNOWN_TERMINAL_REASON],
        "missing_lifecycle_refusal_count": refusal_counts[_MISSING_LIFECYCLE_REASON],
        "ambiguous_lifecycle_refusal_count": refusal_counts[
            _AMBIGUOUS_LIFECYCLE_REASON
        ],
        "security_census_sha256": security_census_sha256,
        "slot_census_sha256": slot_census_sha256,
        "calculation_as_of_date": calculation_as_of_date.isoformat(),
        "sqlite_spool_sha256": spool_sha256,
        "sqlite_spool_byte_count": spool_byte_count,
        "terminal_input_complete": True,
        "terminal_payoff_source_available": False,
        "known_terminal_precedes_market_bars": True,
        "qc_delisting_price_used": False,
        "merger_bankruptcy_successor_payoff_inferred": False,
        "silently_omitted_count": 0,
        "capabilities": {name: False for name in _CAPABILITIES},
    }


def formal_terminal_disposition_build_record(
    value: FormalTerminalDispositionBuild,
) -> dict[str, object]:
    """Return the exact portable identity/census surface of a live build."""

    value = require_formal_terminal_disposition_build(value)
    record = _canonical_object(value._receipt_bytes, "terminal build receipt")
    return dict(record)


def _typed_build_receipt_projection(
    value: FormalTerminalDispositionBuild,
    *,
    package_byte_count: int,
) -> dict[str, object]:
    return {
        "schema": value.schema,
        "status": value.status,
        "historical_bridge_id": value.historical_bridge_id,
        "historical_bridge_sha256": value.historical_bridge_sha256,
        "lifecycle_inventory_sha256": value.lifecycle_inventory_sha256,
        "lifecycle_sidecar_shard_count": value.lifecycle_shard_count,
        "lifecycle_sidecar_row_count": value.lifecycle_row_count,
        "logical_lifecycle_row_count": value.logical_lifecycle_row_count,
        "lifecycle_sidecar_security_count": value.lifecycle_security_count,
        "session_axis_count": value.session_axis_count,
        "terminal_package_id": value.terminal_package.package_id,
        "terminal_package_sha256": value.terminal_package.package_sha256,
        "terminal_package_byte_count": package_byte_count,
        "terminal_policy_id": value.terminal_census.terminal_policy_id,
        "security_count": value.security_count,
        "lifecycle_coverage_count": value.lifecycle_coverage_count,
        "lifecycle_active_security_count": value.lifecycle_active_security_count,
        "lifecycle_known_terminal_security_count": (
            value.lifecycle_known_terminal_security_count
        ),
        "lifecycle_missing_security_count": value.lifecycle_missing_security_count,
        "lifecycle_ambiguous_security_count": (
            value.lifecycle_ambiguous_security_count
        ),
        "actual_slot_count": value.actual_slot_count,
        "unaffected_slot_count": value.unaffected_slot_count,
        "terminal_requirement_count": value.terminal_requirement_count,
        "terminal_payoff_count": value.terminal_census.terminal_payoff_count,
        "benchmark_splice_continuation_count": (
            value.terminal_census.benchmark_splice_continuation_count
        ),
        "named_terminal_refusal_count": (
            value.terminal_census.named_terminal_refusal_count
        ),
        "known_terminal_refusal_count": value.known_terminal_refusal_count,
        "missing_lifecycle_refusal_count": (
            value.missing_lifecycle_refusal_count
        ),
        "ambiguous_lifecycle_refusal_count": (
            value.ambiguous_lifecycle_refusal_count
        ),
        "security_census_sha256": value.security_census_sha256,
        "slot_census_sha256": value.slot_census_sha256,
        "calculation_as_of_date": value.calculation_as_of_date.isoformat(),
        "sqlite_spool_sha256": value.sqlite_spool_sha256,
        "sqlite_spool_byte_count": value.sqlite_spool_byte_count,
        "terminal_input_complete": value.terminal_input_complete,
        "terminal_payoff_source_available": value.terminal_payoff_source_available,
        "known_terminal_precedes_market_bars": (
            value.known_terminal_precedes_market_bars
        ),
        "qc_delisting_price_used": value.qc_delisting_price_used,
        "merger_bankruptcy_successor_payoff_inferred": (
            value.merger_bankruptcy_successor_payoff_inferred
        ),
        "silently_omitted_count": value.silently_omitted_count,
        "capabilities": dict(value.capabilities),
    }


def finalize_formal_terminal_disposition_recording(
    *,
    recorder: FormalTerminalDispositionRecorder,
    calculation_as_of_date: date,
) -> FormalTerminalDispositionBuild:
    """Classify every recorded slot and mint exact package/census artifacts."""

    if type(calculation_as_of_date) is not date:
        raise FormalTerminalDispositionBuildError(
            "terminal calculation_as_of_date changed type"
        )
    calculation_available_at = (
        calculation_as_of_date.isoformat() + "T23:59:59.999999Z"
    )
    with _RECORDER_LOCK:
        value, state = _require_recorder(recorder)
        # From this point the recorder is single-use.  Any classification or
        # artifact failure leaves residue non-authoritative and cannot be
        # retried against a partially sealed SQLite state.
        state.status = "finalizing"
        try:
            state.connection.execute("COMMIT")
        except sqlite3.Error as exc:
            raise FormalTerminalDispositionBuildError(
                "terminal slot transaction could not be sealed"
            ) from exc
        security_hash, security_count = _census_hash(
            state.connection, role="security"
        )
        slot_hash, actual_slot_count = _census_hash(state.connection, role="slot")
        if (
            security_count < 1
            or security_count > MAX_ACTUAL_SECURITY_COUNT
            or actual_slot_count != state.slot_count
            or actual_slot_count > MAX_ACTUAL_SLOT_COUNT
        ):
            raise FormalTerminalDispositionBuildError(
                "recorded terminal security or slot census changed"
            )

        security_counts: Counter[str] = Counter()
        for (security_id,) in state.connection.execute(
            "SELECT security_id FROM actual_security ORDER BY security_id"
        ):
            security_counts[_security_status(
                _summary_row(state.connection, str(security_id))
            )] += 1
        if sum(security_counts.values()) != security_count:
            raise FormalTerminalDispositionBuildError(
                "terminal lifecycle security census is not exhaustive"
            )

        terminal_rows: list[dict[str, object]] = []
        refusal_counts: Counter[str] = Counter()
        unaffected_count = 0
        query = (
            "SELECT slot_kind, slot_id, horizon, security_id, first_session, "
            "last_session, first_ordinal, last_ordinal FROM actual_slot "
            "ORDER BY slot_kind, slot_id, horizon_key"
        )
        for slot_row in state.connection.execute(query):
            reason, available_at, security_lineage = _classify_slot(
                state.connection,
                tuple(slot_row),
                calculation_available_at=calculation_available_at,
            )
            if reason is None:
                unaffected_count += 1
                continue
            refusal_counts[reason] += 1
            lineage = sha256_bytes(
                canonical_json_bytes(
                    {
                        "domain": "arv2-lifecycle-terminal-refusal-v1",
                        "historical_bridge_id": value.historical_bridge_id,
                        "historical_bridge_sha256": value.historical_bridge_sha256,
                        "lifecycle_inventory_sha256": value.lifecycle_inventory_sha256,
                        "slot_kind": slot_row[0],
                        "slot_id": slot_row[1],
                        "horizon": slot_row[2],
                        "security_id": slot_row[3],
                        "first_session": slot_row[4],
                        "last_session": slot_row[5],
                        "reason": reason,
                        "security_lifecycle_lineage_sha256": security_lineage,
                    }
                )
            )
            terminal_rows.append(
                {
                    "schema": TERMINAL_OBJECT_SCHEMA,
                    "slot_kind": slot_row[0],
                    "slot_id": slot_row[1],
                    "horizon": slot_row[2],
                    "disposition": "named_terminal_refusal",
                    "stock_return": None,
                    "reason": reason,
                    "terminal_lineage_sha256": lineage,
                    "available_at_utc": available_at,
                }
            )
            if len(terminal_rows) > MAX_TERMINAL_PACKAGE_ROWS:
                raise FormalTerminalDispositionCapacityRefusal(
                    "terminal refusal package row count exceeded its fixed ceiling"
                )
        terminal_count = len(terminal_rows)
        if (
            actual_slot_count != unaffected_count + terminal_count
            or terminal_count != sum(refusal_counts.values())
        ):
            raise FormalTerminalDispositionBuildError(
                "actual terminal slot census was silently omitted"
            )
        package_payload = canonical_json_bytes(
            {
                "schema": TERMINAL_PACKAGE_SCHEMA,
                "terminal_policy_id": TERMINAL_POLICY_ID,
                "row_count": terminal_count,
                "rows": terminal_rows,
            }
        )
        if len(package_payload) > MAX_TERMINAL_PACKAGE_BYTES:
            raise FormalTerminalDispositionCapacityRefusal(
                "terminal refusal package exceeded its fixed byte ceiling"
            )
        package_sha = sha256_bytes(package_payload)
        package_id = f"arv2-formal-terminal-package-{package_sha[:24]}"
        _sqlite_bytes(state.connection)
        state.connection.close()
        state.status = "finalized"
        spool_sha, spool_bytes, spool_fingerprint = _hash_private_file(
            state.spool_path, maximum_bytes=MAX_SQLITE_SPOOL_BYTES
        )
        if (spool_fingerprint[1], spool_fingerprint[2]) != (
            state.spool_fingerprint[1],
            state.spool_fingerprint[2],
        ):
            raise FormalTerminalDispositionBuildError(
                "terminal SQLite spool inode changed while finalizing"
            )
        semantic = _build_semantic(
            recorder=value,
            package_id=package_id,
            package_sha256=package_sha,
            package_byte_count=len(package_payload),
            security_counts=security_counts,
            actual_slot_count=actual_slot_count,
            unaffected_slot_count=unaffected_count,
            refusal_counts=refusal_counts,
            security_census_sha256=security_hash,
            slot_census_sha256=slot_hash,
            calculation_as_of_date=calculation_as_of_date,
            spool_sha256=spool_sha,
            spool_byte_count=spool_bytes,
        )
        build_sha = sha256_bytes(canonical_json_bytes(semantic))
        build_id = f"arv2-lifecycle-terminal-build-{build_sha[:24]}"
        terminal_census = TerminalCensusBinding(
            census=ArtifactBinding(
                artifact_id=f"arv2-lifecycle-terminal-census-{build_sha[:24]}",
                content_sha256=package_sha,
                artifact_sha256=build_sha,
                byte_count=len(package_payload),
            ),
            terminal_policy_id=TERMINAL_POLICY_ID,
            security_count=security_count,
            lifecycle_coverage_count=security_count,
            terminal_requirement_count=terminal_count,
            terminal_payoff_count=0,
            benchmark_splice_continuation_count=0,
            named_terminal_refusal_count=terminal_count,
            silently_omitted_count=0,
        )
        package = load_formal_terminal_disposition_package(
            payload=package_payload, terminal_census=terminal_census
        )
        receipt = {
            "build_id": build_id,
            "build_sha256": build_sha,
            **semantic,
            "terminal_census": terminal_census.to_record(),
        }
        receipt_bytes = canonical_json_bytes(receipt)
        package_path = value.output_directory / (
            _PACKAGE_PREFIX + package_sha + ".json"
        )
        receipt_path = value.output_directory / (
            _RECEIPT_PREFIX + build_sha + ".json"
        )
        package_fingerprint = _write_private_file(package_path, package_payload)
        receipt_fingerprint = _write_private_file(receipt_path, receipt_bytes)
        expected_names = frozenset(
            {_SPOOL_NAME, package_path.name, receipt_path.name}
        )
        if (
            _directory_identity(value.output_directory) != state.directory_identity
            or _directory_names(value.output_directory) != expected_names
        ):
            raise FormalTerminalDispositionBuildError(
                "terminal artifact inventory changed while finalizing"
            )

        build = object.__new__(FormalTerminalDispositionBuild)
        fields: dict[str, object] = {
            "build_id": build_id,
            "build_sha256": build_sha,
            "schema": BUILD_SCHEMA,
            "status": BUILD_STATUS,
            "historical_bridge": value.historical_bridge,
            "historical_bridge_id": value.historical_bridge_id,
            "historical_bridge_sha256": value.historical_bridge_sha256,
            "lifecycle_inventory_sha256": value.lifecycle_inventory_sha256,
            "lifecycle_shard_count": value.lifecycle_shard_count,
            "lifecycle_row_count": value.lifecycle_row_count,
            "logical_lifecycle_row_count": value.logical_lifecycle_row_count,
            "lifecycle_security_count": value.lifecycle_security_count,
            "session_axis_count": value.session_axis_count,
            "terminal_package": package,
            "terminal_census": terminal_census,
            "security_count": security_count,
            "lifecycle_coverage_count": security_count,
            "lifecycle_active_security_count": security_counts["active_observed"],
            "lifecycle_known_terminal_security_count": security_counts[
                "known_terminal"
            ],
            "lifecycle_missing_security_count": security_counts["missing"],
            "lifecycle_ambiguous_security_count": security_counts["ambiguous"],
            "actual_slot_count": actual_slot_count,
            "unaffected_slot_count": unaffected_count,
            "terminal_requirement_count": terminal_count,
            "known_terminal_refusal_count": refusal_counts[_KNOWN_TERMINAL_REASON],
            "missing_lifecycle_refusal_count": refusal_counts[
                _MISSING_LIFECYCLE_REASON
            ],
            "ambiguous_lifecycle_refusal_count": refusal_counts[
                _AMBIGUOUS_LIFECYCLE_REASON
            ],
            "security_census_sha256": security_hash,
            "slot_census_sha256": slot_hash,
            "calculation_as_of_date": calculation_as_of_date,
            "sqlite_spool_sha256": spool_sha,
            "sqlite_spool_byte_count": spool_bytes,
            "receipt_sha256": sha256_bytes(receipt_bytes),
            "receipt_byte_count": len(receipt_bytes),
            "terminal_input_complete": True,
            "terminal_payoff_source_available": False,
            "known_terminal_precedes_market_bars": True,
            "qc_delisting_price_used": False,
            "merger_bankruptcy_successor_payoff_inferred": False,
            "silently_omitted_count": 0,
            "capabilities": tuple((name, False) for name in _CAPABILITIES),
            "output_directory": value.output_directory,
            "sqlite_spool_path": state.spool_path,
            "terminal_package_path": package_path,
            "receipt_path": receipt_path,
            "_directory_identity": state.directory_identity,
            "_spool_fingerprint": spool_fingerprint,
            "_package_fingerprint": package_fingerprint,
            "_receipt_fingerprint": receipt_fingerprint,
            "_receipt_bytes": receipt_bytes,
        }
        for name, item in fields.items():
            object.__setattr__(build, name, item)
        identity = id(build)
        reference = weakref.ref(
            build, lambda ref, key=identity: _forget_build(key, ref)
        )
        with _BUILD_LOCK:
            _BUILDS[identity] = (
                reference,
                receipt_bytes,
                _build_topology(build),
            )
        return require_formal_terminal_disposition_build(build)


def require_formal_terminal_disposition_build(
    value: FormalTerminalDispositionBuild,
) -> FormalTerminalDispositionBuild:
    """Reauthenticate the live lifecycle source and every immutable artifact."""

    if type(value) is not FormalTerminalDispositionBuild:
        raise FormalTerminalDispositionBuildError(
            "formal terminal disposition build changed type"
        )
    with _BUILD_LOCK:
        registered = _BUILDS.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalTerminalDispositionBuildError(
            "formal terminal disposition build is not builder-authenticated"
        )
    try:
        bridge = historical_module.require_reviewed_historical_universe_to_preopen_bridge(
            value.historical_bridge
        )
        package = require_formal_terminal_disposition_package(
            value.terminal_package
        )
        census = require_terminal_census_binding(value.terminal_census)
    except (TypeError, ValueError) as exc:
        raise FormalTerminalDispositionBuildError(
            "formal terminal disposition parent changed"
        ) from exc
    package_payload, package_fingerprint = _read_private_file(
        value.terminal_package_path, maximum_bytes=MAX_TERMINAL_PACKAGE_BYTES
    )
    receipt_payload, receipt_fingerprint = _read_private_file(
        value.receipt_path, maximum_bytes=MAX_LIFECYCLE_ROW_BYTES * 4
    )
    spool_sha, spool_bytes, spool_fingerprint = _hash_private_file(
        value.sqlite_spool_path, maximum_bytes=MAX_SQLITE_SPOOL_BYTES
    )
    receipt = _canonical_object(receipt_payload, "terminal build receipt")
    typed_projection = _typed_build_receipt_projection(
        value, package_byte_count=len(package_payload)
    )
    expected_names = frozenset(
        {
            value.sqlite_spool_path.name,
            value.terminal_package_path.name,
            value.receipt_path.name,
        }
    )
    if (
        registered[1] != receipt_payload
        or registered[2] != _build_topology(value)
        or receipt_payload != value._receipt_bytes
        or _directory_identity(value.output_directory) != value._directory_identity
        or _directory_names(value.output_directory) != expected_names
        or spool_fingerprint != value._spool_fingerprint
        or package_fingerprint != value._package_fingerprint
        or receipt_fingerprint != value._receipt_fingerprint
        or spool_sha != value.sqlite_spool_sha256
        or spool_bytes != value.sqlite_spool_byte_count
        or package_payload != render_formal_terminal_disposition_package_bytes(package)
        or package.terminal_census is not census
        or census.census.content_sha256 != sha256_bytes(package_payload)
        or census.census.artifact_sha256 != value.build_sha256
        or receipt.get("build_id") != value.build_id
        or receipt.get("build_sha256") != value.build_sha256
        or receipt.get("terminal_census") != census.to_record()
        or any(receipt.get(name) != item for name, item in typed_projection.items())
        or value.schema != BUILD_SCHEMA
        or value.status != BUILD_STATUS
        or value.historical_bridge_id != bridge.bridge_id
        or value.historical_bridge_sha256 != bridge.bridge_sha256
        or value.lifecycle_inventory_sha256
        != bridge.universe_lifecycle_binding_inventory_sha256
        or value.lifecycle_shard_count
        != bridge.universe_lifecycle_binding_shard_count
        or value.lifecycle_row_count
        != bridge.universe_lifecycle_binding_row_count
        or value.lifecycle_shard_count
        != receipt.get("lifecycle_sidecar_shard_count")
        or value.lifecycle_row_count
        != receipt.get("lifecycle_sidecar_row_count")
        or value.logical_lifecycle_row_count
        != receipt.get("logical_lifecycle_row_count")
        or value.lifecycle_security_count
        != receipt.get("lifecycle_sidecar_security_count")
        or value.session_axis_count != receipt.get("session_axis_count")
        or value.terminal_census is not value.terminal_package.terminal_census
        or value.security_count != value.lifecycle_coverage_count
        or value.actual_slot_count
        != value.unaffected_slot_count + value.terminal_requirement_count
        or value.terminal_requirement_count
        != (
            value.known_terminal_refusal_count
            + value.missing_lifecycle_refusal_count
            + value.ambiguous_lifecycle_refusal_count
        )
        or value.terminal_requirement_count
        != value.terminal_census.named_terminal_refusal_count
        or value.terminal_census.terminal_payoff_count != 0
        or value.terminal_census.benchmark_splice_continuation_count != 0
        or value.silently_omitted_count != 0
        or value.terminal_input_complete is not True
        or value.terminal_payoff_source_available is not False
        or value.known_terminal_precedes_market_bars is not True
        or value.qc_delisting_price_used is not False
        or value.merger_bankruptcy_successor_payoff_inferred is not False
        or value.capabilities != tuple((name, False) for name in _CAPABILITIES)
        or sha256_bytes(receipt_payload) != value.receipt_sha256
        or len(receipt_payload) != value.receipt_byte_count
    ):
        raise FormalTerminalDispositionBuildError(
            "formal terminal disposition build changed after authentication"
        )
    semantic = dict(receipt)
    supplied_id = semantic.pop("build_id", None)
    supplied_sha = semantic.pop("build_sha256", None)
    semantic.pop("terminal_census", None)
    digest = sha256_bytes(canonical_json_bytes(semantic))
    if (
        supplied_id != f"arv2-lifecycle-terminal-build-{digest[:24]}"
        or supplied_sha != digest
    ):
        raise FormalTerminalDispositionBuildError(
            "formal terminal disposition build identity changed"
        )
    return value


__all__ = (
    "BUILD_SCHEMA",
    "BUILD_STATUS",
    "FormalTerminalDispositionBuild",
    "FormalTerminalDispositionBuildError",
    "FormalTerminalDispositionCapacityRefusal",
    "FormalTerminalDispositionRecorder",
    "begin_formal_terminal_disposition_recording",
    "finalize_formal_terminal_disposition_recording",
    "formal_terminal_disposition_build_record",
    "record_formal_terminal_security",
    "record_formal_terminal_slot",
    "require_formal_terminal_disposition_build",
    "require_fresh_formal_terminal_disposition_recorder",
)
