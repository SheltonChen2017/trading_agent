"""Build the reviewed historical pre-open bridge from a physical seed.

The original bridge builder is the semantic oracle, but it accepts a legacy
``PhysicalPreopenInputCandidate`` whose source-seed documents retain all
derived historical rows in memory.  This additive builder consumes the same
data through ``PhysicalPreopenSeedArchive`` iterators.  SQLite owns the large
joins, sort keys, and intermediate evidence; Python retains only one source
row, one bounded output shard, and the small reviewed manifest projections.

Importing this module performs no filesystem, provider, credential,
QuantConnect, price, outcome, result, broker, order, or trading action.
"""
from __future__ import annotations

import dataclasses
import ctypes
import errno
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import stat
import sys
import tempfile
import weakref
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from data.exchange_calendar import SUPPORTED_SESSION_START, trading_sessions
from research.analyst_revisions_v2.accepted_risk_input_pair import MassiveSourceRole
from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import fundamental_universe_discovery as _discovery
from research.analyst_revisions_v2_qc import physical_preopen_seed_archive as _seed
from research.analyst_revisions_v2_qc.fundamental_universe_discovery import (
    ReviewedFundamentalUniverseDiscoveryReceipt,
)
from research.analyst_revisions_v2_qc.physical_preopen_seed_archive import (
    PhysicalPreopenSeedArchive,
)
from research.analyst_revisions_v2_qc.preopen_control_stage import (
    EARNINGS_INPUT_SCHEMA,
    FUNDAMENTAL_INPUT_SCHEMA,
    GUIDANCE_INPUT_SCHEMA,
    INPUT_ROLE_ORDER,
    MAX_BLOCK_COMPRESSED_INPUT_BYTES,
    MAX_BLOCK_INPUT_ROW_COUNT,
    MAX_BLOCK_UNCOMPRESSED_INPUT_BYTES,
    MAX_BUFFERED_MARKET_OBSERVATION_COUNT,
    MAX_UNCOMPRESSED_SHARD_BYTES,
    RATING_INPUT_SCHEMA,
    SID_MAPPING_INPUT_SCHEMA,
    UNIVERSE_INPUT_SCHEMA,
    build_preopen_input_shard,
)
from scripts import build_arv2_historical_preopen_bridge as _legacy


MAX_PHYSICAL_HISTORICAL_SPOOL_BYTES = 64 * 1024 * 1024 * 1024
SQLITE_PAGE_BYTES = 4096
SQLITE_UPDATE_BATCH_ROWS = 1024
_PATH_TYPE = type(Path("."))
_HEX64 = frozenset("0123456789abcdef")


class PhysicalHistoricalPreopenBridgeError(_legacy.HistoricalPreopenBridgeError):
    """The physical seed cannot be joined to the reviewed discovery safely."""


class PhysicalHistoricalPreopenBridgeCapacityError(
    PhysicalHistoricalPreopenBridgeError
):
    """The fixed disk or row bound was exceeded without truncation."""


class PhysicalHistoricalPreopenBridgePublicationAmbiguityError(
    PhysicalHistoricalPreopenBridgeError
):
    """Publication or rollback durability is uncertain; residue is preserved."""


def _decode(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload.endswith(b"\n"):
        raise PhysicalHistoricalPreopenBridgeError(f"{name} is not canonical JSON")
    try:
        value = json.loads(payload)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise PhysicalHistoricalPreopenBridgeError(f"{name} is not JSON") from exc
    if type(value) is not dict or canonical_json_bytes(value) != payload:
        raise PhysicalHistoricalPreopenBridgeError(f"{name} is not canonical JSON")
    return value


def _encoded(row: object, name: str) -> bytes:
    if type(row) is not dict:
        raise PhysicalHistoricalPreopenBridgeError(f"{name} changed")
    return canonical_json_bytes(row)


def _is_sha(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and not (set(value) - _HEX64)
    )


def _sqlite_full(exc: sqlite3.Error) -> bool:
    return (
        getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL
        or "database or disk is full" in str(exc).lower()
    )


def _execute(connection: sqlite3.Connection, sql: str, parameters=()):
    try:
        return connection.execute(sql, parameters)
    except sqlite3.Error as exc:
        if _sqlite_full(exc):
            raise PhysicalHistoricalPreopenBridgeCapacityError(
                "historical bridge SQLite spool reached its fixed byte bound"
            ) from exc
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge SQLite operation failed"
        ) from exc


def _open_spool(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(path)
        connection.execute(f"PRAGMA page_size={SQLITE_PAGE_BYTES}")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA temp_store=FILE")
        connection.execute("PRAGMA mmap_size=0")
        connection.execute("PRAGMA cache_size=-8192")
        requested = MAX_PHYSICAL_HISTORICAL_SPOOL_BYTES // SQLITE_PAGE_BYTES
        observed = connection.execute(
            f"PRAGMA max_page_count={requested}"
        ).fetchone()[0]
        if observed != requested:
            raise PhysicalHistoricalPreopenBridgeCapacityError(
                "historical bridge SQLite hard page cap was not installed"
            )
    except sqlite3.Error as exc:
        if _sqlite_full(exc):
            raise PhysicalHistoricalPreopenBridgeCapacityError(
                "historical bridge SQLite spool reached its fixed byte bound"
            ) from exc
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge SQLite spool is unavailable"
        ) from exc
    return connection


_SCHEMA = """
CREATE TABLE candidate(
    security_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    payload BLOB NOT NULL
) WITHOUT ROWID;
CREATE TABLE candidate_cusip(
    cusip TEXT NOT NULL,
    security_id TEXT NOT NULL,
    PRIMARY KEY(cusip, security_id)
) WITHOUT ROWID;
CREATE TABLE terminal(
    stream_ordinal INTEGER PRIMARY KEY,
    disposition TEXT NOT NULL,
    sid TEXT,
    cusip TEXT,
    display_ticker TEXT,
    session TEXT NOT NULL,
    opened TEXT,
    available_at TEXT,
    terminal_sha TEXT NOT NULL,
    payload BLOB NOT NULL
);
CREATE INDEX terminal_sid_stream ON terminal(sid, stream_ordinal);
CREATE INDEX terminal_sid_hash ON terminal(sid, terminal_sha);
CREATE INDEX terminal_sid_cusip ON terminal(sid, cusip);
CREATE INDEX terminal_sid_display ON terminal(sid, display_ticker);
CREATE INDEX terminal_disposition_stream ON terminal(disposition, stream_ordinal);
CREATE TABLE identity(
    sid TEXT PRIMARY KEY,
    cusip TEXT NOT NULL,
    first_session TEXT NOT NULL,
    last_session TEXT NOT NULL,
    first_available_at TEXT NOT NULL,
    display_ticker TEXT NOT NULL,
    terminal_projection_sha TEXT NOT NULL,
    candidate_security_id TEXT,
    candidate_payload BLOB,
    current_ticker_matches INTEGER NOT NULL,
    reason TEXT,
    logical TEXT NOT NULL UNIQUE,
    batch INTEGER
) WITHOUT ROWID;
CREATE INDEX identity_logical ON identity(logical);
CREATE INDEX identity_candidate ON identity(candidate_security_id, sid);
CREATE INDEX identity_cusip ON identity(cusip, sid);
CREATE TABLE mapping(
    sid TEXT PRIMARY KEY,
    logical TEXT NOT NULL UNIQUE,
    batch INTEGER NOT NULL,
    accepted INTEGER NOT NULL,
    issuer_id TEXT NOT NULL,
    share_class_id TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    payload BLOB NOT NULL
) WITHOUT ROWID;
CREATE INDEX mapping_batch_logical ON mapping(batch, logical);
CREATE TABLE full_session(
    session TEXT PRIMARY KEY,
    ordinal INTEGER NOT NULL UNIQUE
) WITHOUT ROWID;
CREATE TABLE role_seed(
    role TEXT NOT NULL,
    source_ordinal INTEGER NOT NULL,
    security_id TEXT NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY(role, source_ordinal)
) WITHOUT ROWID;
CREATE INDEX role_seed_security ON role_seed(role, security_id, source_ordinal);
CREATE TABLE rating(
    source_ordinal INTEGER PRIMARY KEY,
    security_id TEXT NOT NULL,
    common_event_id TEXT NOT NULL,
    eligible_ordinal INTEGER NOT NULL,
    admitted INTEGER NOT NULL,
    payload BLOB NOT NULL
);
CREATE INDEX rating_key ON rating(security_id, common_event_id, source_ordinal);
CREATE TABLE requested_quality(
    security_id TEXT NOT NULL,
    session TEXT NOT NULL,
    PRIMARY KEY(security_id, session)
) WITHOUT ROWID;
CREATE TABLE composition_terminal(
    source_ordinal INTEGER PRIMARY KEY,
    source_role TEXT NOT NULL,
    physical_id TEXT,
    provider_id TEXT,
    payload BLOB NOT NULL
);
CREATE INDEX composition_role_order ON composition_terminal(source_role, source_ordinal);
CREATE TABLE input_row(
    role TEXT NOT NULL,
    batch INTEGER NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY(role, batch, payload)
) WITHOUT ROWID;
CREATE INDEX input_row_batch_role_payload ON input_row(batch, role, payload);
CREATE TABLE universe_key(
    session TEXT NOT NULL,
    security_id TEXT NOT NULL,
    PRIMARY KEY(session, security_id)
) WITHOUT ROWID;
CREATE TABLE batch_session(
    batch INTEGER NOT NULL,
    session TEXT NOT NULL,
    PRIMARY KEY(batch, session)
) WITHOUT ROWID;
CREATE TABLE batch_counts(
    batch INTEGER PRIMARY KEY,
    terminal_count INTEGER NOT NULL DEFAULT 0,
    accepted_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE batch_session_accepted(
    batch INTEGER NOT NULL,
    session TEXT NOT NULL,
    accepted_count INTEGER NOT NULL,
    PRIMARY KEY(batch, session)
) WITHOUT ROWID;
CREATE TABLE session_geometry(
    session TEXT PRIMARY KEY,
    opened TEXT NOT NULL,
    full_ordinal INTEGER NOT NULL,
    terminal_count INTEGER NOT NULL
) WITHOUT ROWID;
CREATE TABLE peer_key(
    session TEXT NOT NULL,
    axis TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY(session, axis, value)
) WITHOUT ROWID;
CREATE TABLE quality(
    security_id TEXT NOT NULL,
    session TEXT NOT NULL,
    q_data TEXT NOT NULL,
    evidence_sha TEXT NOT NULL,
    PRIMARY KEY(security_id, session)
) WITHOUT ROWID;
CREATE TABLE evidence(
    role TEXT NOT NULL,
    source_ordinal INTEGER NOT NULL,
    payload BLOB NOT NULL,
    PRIMARY KEY(role, source_ordinal)
) WITHOUT ROWID;
CREATE INDEX evidence_role_order ON evidence(role, source_ordinal);
"""


def _create_schema(connection: sqlite3.Connection) -> None:
    try:
        connection.executescript(_SCHEMA)
    except sqlite3.Error as exc:
        if _sqlite_full(exc):
            raise PhysicalHistoricalPreopenBridgeCapacityError(
                "historical bridge SQLite spool reached its fixed byte bound"
            ) from exc
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge SQLite schema could not be created"
        ) from exc


def _require_indexed_plan(
    connection: sqlite3.Connection, sql: str, parameters: tuple[object, ...]
) -> None:
    plan = " ".join(
        str(row[3]).upper()
        for row in _execute(connection, "EXPLAIN QUERY PLAN " + sql, parameters)
    )
    if "TEMP B-TREE" in plan or "INDEX" not in plan and "PRIMARY KEY" not in plan:
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge query lost its bounded indexed order"
        )


def _insert(
    connection: sqlite3.Connection, sql: str, parameters: tuple[object, ...], name: str
) -> None:
    try:
        connection.execute(sql, parameters)
    except sqlite3.IntegrityError as exc:
        raise PhysicalHistoricalPreopenBridgeError(
            f"{name} repeats or violates its exact schema"
        ) from exc
    except sqlite3.Error as exc:
        if _sqlite_full(exc):
            raise PhysicalHistoricalPreopenBridgeCapacityError(
                "historical bridge SQLite spool reached its fixed byte bound"
            ) from exc
        raise PhysicalHistoricalPreopenBridgeError(
            f"{name} could not be spooled"
        ) from exc


def _executemany_bounded(
    connection: sqlite3.Connection,
    sql: str,
    rows: list[tuple[object, ...]],
    name: str,
) -> None:
    if not rows or len(rows) > SQLITE_UPDATE_BATCH_ROWS:
        raise PhysicalHistoricalPreopenBridgeError(
            f"{name} update batch lost its fixed bound"
        )
    try:
        connection.executemany(sql, rows)
    except sqlite3.IntegrityError as exc:
        raise PhysicalHistoricalPreopenBridgeError(
            f"{name} repeats or violates its exact schema"
        ) from exc
    except sqlite3.Error as exc:
        if _sqlite_full(exc):
            raise PhysicalHistoricalPreopenBridgeCapacityError(
                "historical bridge SQLite spool reached its fixed byte bound"
            ) from exc
        raise PhysicalHistoricalPreopenBridgeError(
            f"{name} update failed"
        ) from exc


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
        raise PhysicalHistoricalPreopenBridgeError(
            "atomic no-replace publication is unavailable"
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
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge publication destination exists"
        )
    raise PhysicalHistoricalPreopenBridgeError(
        "historical bridge atomic publication failed"
    )


def _open_directory(path: Path, name: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        observed = os.fstat(descriptor)
    except OSError as exc:
        raise PhysicalHistoricalPreopenBridgeError(f"{name} is unavailable") from exc
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or observed.st_mode & 0o077
    ):
        os.close(descriptor)
        raise PhysicalHistoricalPreopenBridgeError(
            f"{name} is not an owner-only directory"
        )
    return descriptor


def _create_private_stage(final_root: Path) -> Path:
    parent_fd = _open_directory(final_root.parent, "historical bridge parent")
    try:
        for _attempt in range(32):
            name = f".arv2-historical-{os.getpid()}-{secrets.token_hex(12)}"
            try:
                os.mkdir(name, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                continue
            except OSError as exc:
                raise PhysicalHistoricalPreopenBridgeError(
                    "historical bridge staging directory could not be created"
                ) from exc
            return final_root.parent / name
    finally:
        os.close(parent_fd)
    raise PhysicalHistoricalPreopenBridgeError(
        "historical bridge staging name attempts were exhausted"
    )


def _sync_directory(path: Path, name: str) -> None:
    descriptor = _open_directory(path, name)
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise PhysicalHistoricalPreopenBridgeError(f"{name} sync failed") from exc
    finally:
        os.close(descriptor)


def _publish_stage(stage: Path, final_root: Path) -> None:
    if stage.parent != final_root.parent:
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge stage left its publication parent"
        )
    _sync_directory(
        stage / _legacy.ARCHIVE_SHARD_DIRECTORY,
        "historical bridge input shard directory",
    )
    _sync_directory(
        stage / _legacy.ARCHIVE_EVIDENCE_DIRECTORY,
        "historical bridge evidence directory",
    )
    _sync_directory(stage, "historical bridge staging directory")
    parent_fd = _open_directory(stage.parent, "historical bridge parent")
    try:
        _rename_noreplace(parent_fd, stage.name, final_root.name)
        try:
            os.fsync(parent_fd)
        except OSError as primary:
            try:
                _rename_noreplace(parent_fd, final_root.name, stage.name)
                os.fsync(parent_fd)
            except Exception as rollback:
                raise PhysicalHistoricalPreopenBridgePublicationAmbiguityError(
                    "historical bridge publication rollback is ambiguous; residue preserved"
                ) from primary
            raise PhysicalHistoricalPreopenBridgeError(
                "historical bridge publication sync failed and was rolled back"
            ) from primary
    finally:
        os.close(parent_fd)


def _rollback_published_stage(stage: Path, final_root: Path) -> None:
    """Return a published final entry to its private stage durably."""

    if stage.parent != final_root.parent:
        raise PhysicalHistoricalPreopenBridgePublicationAmbiguityError(
            "historical bridge late rollback path is ambiguous; residue preserved"
        )
    parent_fd: int | None = None
    try:
        parent_fd = _open_directory(stage.parent, "historical bridge parent")
        _rename_noreplace(parent_fd, final_root.name, stage.name)
        os.fsync(parent_fd)
    except Exception as exc:
        raise PhysicalHistoricalPreopenBridgePublicationAmbiguityError(
            "historical bridge late rollback is ambiguous; residue preserved"
        ) from exc
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


def _hash_canonical_array(rows: Iterator[dict[str, object]]) -> tuple[int, str]:
    digest = hashlib.sha256()
    digest.update(b"[")
    count = 0
    for row in rows:
        if count:
            digest.update(b",")
        digest.update(canonical_json_bytes(row)[:-1])
        count += 1
    digest.update(b"]\n")
    return count, digest.hexdigest()


def _artifact(seed: PhysicalPreopenSeedArchive, role: str):
    return _seed.physical_preopen_seed_artifact_binding(seed, role)


def _separate_output(
    archive_root: Path,
    discovery: ReviewedFundamentalUniverseDiscoveryReceipt,
    seed: PhysicalPreopenSeedArchive,
) -> Path:
    if type(archive_root) is not _PATH_TYPE:
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge archive must be exact Path"
        )
    target = archive_root.absolute()
    inputs = (
        seed.archive_path.absolute(),
        seed.accepted_risk_archive_path.absolute(),
        seed.sharadar_capture_path.absolute(),
        discovery._archive_root.absolute(),
    )
    for source in inputs:
        if target == source or source in target.parents:
            raise PhysicalHistoricalPreopenBridgeError(
                "historical bridge output must be separate from physical inputs"
            )
    if target.exists() or target.is_symlink():
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge archive must be a new Path"
        )
    return target


def _ingest_sessions(
    connection: sqlite3.Connection,
    discovery: ReviewedFundamentalUniverseDiscoveryReceipt,
    seed: PhysicalPreopenSeedArchive,
) -> None:
    full = trading_sessions(
        SUPPORTED_SESSION_START, date.fromisoformat(discovery.last_session)
    )
    for ordinal, session in enumerate(full):
        _insert(
            connection,
            "INSERT INTO full_session(session, ordinal) VALUES (?, ?)",
            (session.isoformat(), ordinal),
            "full NYSE session",
        )
    expected = iter(
        item.isoformat()
        for item in trading_sessions(
            date.fromisoformat(discovery.first_session),
            date.fromisoformat(discovery.last_session),
        )
    )
    observed = 0
    for observed, row in enumerate(_seed.iter_physical_session_counts(seed), start=1):
        if (
            type(row) is not dict
            or set(row) != {"candidate_member_count", "decision_session"}
            or type(row["candidate_member_count"]) is not int
            or row["candidate_member_count"] < 0
            or type(row["decision_session"]) is not str
            or row["decision_session"] != next(expected, None)
        ):
            raise PhysicalHistoricalPreopenBridgeError(
                "physical seed session geometry changed"
            )
    if next(expected, None) is not None or observed != seed.decision_session_count:
        raise PhysicalHistoricalPreopenBridgeError(
            "physical seed session iterator did not span the formal axis"
        )


def _ingest_candidates(
    connection: sqlite3.Connection, seed: PhysicalPreopenSeedArchive
) -> None:
    count = 0
    for row in _seed.iter_physical_universe_candidates(seed):
        count += 1
        security_id = row.get("security_id")
        ticker = row.get("current_snapshot_ticker_display")
        cusips = row.get("sharadar_cusip_join_candidates")
        if (
            type(security_id) is not str
            or not security_id
            or type(ticker) is not str
            or type(cusips) is not list
            or any(
                type(cusip) is not str or _legacy._CUSIP.fullmatch(cusip) is None
                for cusip in cusips
            )
            or len(cusips) != len(set(cusips))
        ):
            raise PhysicalHistoricalPreopenBridgeError(
                "physical universe identity row changed"
            )
        payload = _encoded(row, "physical universe identity row")
        _insert(
            connection,
            "INSERT INTO candidate(security_id, ticker, payload) VALUES (?, ?, ?)",
            (security_id, ticker, payload),
            "physical universe security",
        )
        for cusip in cusips:
            _insert(
                connection,
                "INSERT INTO candidate_cusip(cusip, security_id) VALUES (?, ?)",
                (cusip, security_id),
                "physical universe CUSIP candidate",
            )
    if count != seed.candidate_security_count:
        raise PhysicalHistoricalPreopenBridgeError(
            "physical universe candidate census changed"
        )


def _ingest_discovery(
    connection: sqlite3.Connection,
    discovery: ReviewedFundamentalUniverseDiscoveryReceipt,
) -> None:
    count = 0
    for count, row in enumerate(_legacy._terminal_rows(discovery), start=1):
        required = (
            "disposition",
            "decision_session",
            "decision_open_utc",
            "available_at",
            "terminal_sha256",
        )
        if any(key not in row for key in required):
            raise PhysicalHistoricalPreopenBridgeError(
                "discovery terminal fields changed"
            )
        sid = row.get("qc_security_id")
        cusip = row.get("cusip")
        if sid is not None and type(sid) is not str:
            raise PhysicalHistoricalPreopenBridgeError("discovery QC SID changed")
        if cusip is not None and type(cusip) is not str:
            raise PhysicalHistoricalPreopenBridgeError("discovery CUSIP changed")
        if not _is_sha(row["terminal_sha256"]):
            raise PhysicalHistoricalPreopenBridgeError(
                "discovery terminal hash changed"
            )
        normalized_cusip = cusip
        if row["disposition"] == "accepted" and (
            type(cusip) is not str or _legacy._CUSIP.fullmatch(cusip) is None
        ):
            normalized_cusip = ""
        _insert(
            connection,
            """INSERT INTO terminal(
                   stream_ordinal, disposition, sid, cusip, display_ticker,
                   session, opened, available_at, terminal_sha, payload
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                count - 1,
                row["disposition"],
                sid,
                normalized_cusip,
                row.get("display_ticker_non_authoritative"),
                row["decision_session"],
                row["decision_open_utc"],
                row["available_at"],
                row["terminal_sha256"],
                _encoded(row, "discovery terminal"),
            ),
            "discovery terminal ordinal",
        )
    if count != discovery.terminal_count:
        raise PhysicalHistoricalPreopenBridgeError(
            "discovery terminal iterator census changed"
        )


_ROLE_SPECS = (
    ("fundamentals", FUNDAMENTAL_INPUT_SCHEMA, None),
    ("earnings", EARNINGS_INPUT_SCHEMA, MassiveSourceRole.EARNINGS),
    ("guidance", GUIDANCE_INPUT_SCHEMA, MassiveSourceRole.CORPORATE_GUIDANCE),
    ("ratings", RATING_INPUT_SCHEMA, MassiveSourceRole.ANALYST_RATINGS),
)


def _role_iterator(seed: PhysicalPreopenSeedArchive, source_role):
    if source_role is None:
        return _seed.iter_physical_fundamental_seeds(seed)
    return _seed.iter_physical_source_role_seeds(seed, source_role)


def _ingest_role_seeds(
    connection: sqlite3.Connection, seed: PhysicalPreopenSeedArchive
) -> None:
    declared = dict(seed.source_role_row_counts)
    for role, schema, source_role in _ROLE_SPECS:
        count = 0
        for count, row in enumerate(_role_iterator(seed, source_role), start=1):
            security_id = row.get("security_id")
            if (
                type(row) is not dict
                or row.get("schema") != schema
                or type(security_id) is not str
            ):
                raise PhysicalHistoricalPreopenBridgeError(
                    f"physical {role} seed row changed"
                )
            payload = _encoded(row, f"physical {role} seed row")
            _insert(
                connection,
                """INSERT INTO role_seed(
                       role, source_ordinal, security_id, payload
                   ) VALUES (?, ?, ?, ?)""",
                (role, count - 1, security_id, payload),
                f"physical {role} seed ordinal",
            )
            if role == "ratings":
                common = row.get("common_event_id")
                eligible = row.get("eligible_session_ordinal")
                admitted = row.get("admitted")
                if (
                    type(common) is not str
                    or type(eligible) is not int
                    or type(admitted) is not bool
                ):
                    raise PhysicalHistoricalPreopenBridgeError(
                        "physical rating seed row changed"
                    )
                _insert(
                    connection,
                    """INSERT INTO rating(
                           source_ordinal, security_id, common_event_id,
                           eligible_ordinal, admitted, payload
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (count - 1, security_id, common, eligible, admitted, payload),
                    "physical rating seed ordinal",
                )
                session_row = _execute(
                    connection,
                    "SELECT session FROM full_session WHERE ordinal=?",
                    (eligible,),
                ).fetchone()
                if session_row is not None:
                    _execute(
                        connection,
                        """INSERT OR IGNORE INTO requested_quality(
                               security_id, session
                           ) VALUES (?, ?)""",
                        (security_id, session_row[0]),
                    )
        expected = seed.fundamental_seed_count if role == "fundamentals" else declared[role]
        if count != expected:
            raise PhysicalHistoricalPreopenBridgeError(
                f"physical {role} seed iterator census changed"
            )


_COMPOSITION_FIELDS = {
    "locator_sha256",
    "source_role",
    "provider_event_id",
    "raw_row_sha256",
    "current_view_disposition",
    "censored_view_disposition",
    "preopen_composition_disposition",
    "reason",
    "security_id",
    "terminal_sha256",
}


def _ingest_composition_terminals(
    connection: sqlite3.Connection, seed: PhysicalPreopenSeedArchive
) -> None:
    count = 0
    for count, row in enumerate(
        _seed.iter_physical_composition_terminals(seed), start=1
    ):
        if type(row) is not dict or set(row) != _COMPOSITION_FIELDS:
            raise PhysicalHistoricalPreopenBridgeError(
                "physical composition terminal changed"
            )
        semantic = dict(row)
        declared = semantic.pop("terminal_sha256")
        if (
            not _is_sha(declared)
            or hashlib.sha256(canonical_json_bytes(semantic)).hexdigest() != declared
        ):
            raise PhysicalHistoricalPreopenBridgeError(
                "physical composition terminal hash changed"
            )
        physical = row["security_id"]
        provider = row["provider_event_id"]
        if physical is not None and type(physical) is not str:
            raise PhysicalHistoricalPreopenBridgeError(
                "physical composition security changed"
            )
        if provider is not None and type(provider) is not str:
            raise PhysicalHistoricalPreopenBridgeError(
                "physical composition provider id changed"
            )
        _insert(
            connection,
            """INSERT INTO composition_terminal(
                   source_ordinal, source_role, physical_id, provider_id, payload
               ) VALUES (?, ?, ?, ?, ?)""",
            (
                count - 1,
                row["source_role"],
                physical,
                provider,
                _encoded(row, "physical composition terminal"),
            ),
            "physical composition terminal ordinal",
        )
    if count != seed.composition_terminal_count:
        raise PhysicalHistoricalPreopenBridgeError(
            "physical composition terminal iterator census changed"
        )


def _canonical_array_hash_from_values(values: Iterator[str]) -> str:
    digest = hashlib.sha256()
    digest.update(b"[")
    count = 0
    for value in values:
        if count:
            digest.update(b",")
        digest.update(canonical_json_bytes(value)[:-1])
        count += 1
    digest.update(b"]\n")
    return digest.hexdigest()


def _derive_identities(
    connection: sqlite3.Connection,
) -> tuple[int, int]:
    rows = _execute(
        connection,
        """SELECT sid, MIN(stream_ordinal), MIN(session), MAX(session),
                  MIN(available_at), MIN(cusip), MAX(cusip)
             FROM terminal INDEXED BY terminal_sid_stream
            WHERE disposition='accepted'
            GROUP BY sid
            ORDER BY sid""",
    )
    identity_count = 0
    eligible_terminal_count = _execute(
        connection,
        "SELECT COUNT(*) FROM terminal WHERE disposition='accepted'",
    ).fetchone()[0]
    if eligible_terminal_count > _legacy.MAX_BRIDGE_UNIVERSE_TERMINALS:
        raise PhysicalHistoricalPreopenBridgeError(
            "eligible discovery census exceeds bridge bound"
        )
    for (
        sid,
        first_stream,
        first_session,
        last_session,
        first_available,
        minimum_cusip,
        maximum_cusip,
    ) in rows:
        if type(sid) is not str or _legacy._QC_SID.fullmatch(sid) is None:
            raise PhysicalHistoricalPreopenBridgeError(
                "accepted discovery QC SID changed"
            )
        first = _execute(
            connection,
            "SELECT cusip FROM terminal WHERE stream_ordinal=?",
            (first_stream,),
        ).fetchone()
        raw_cusip = first[0] if first is not None else None
        cusip = (
            raw_cusip
            if type(raw_cusip) is str and _legacy._CUSIP.fullmatch(raw_cusip)
            else ""
        )
        displays = (
            row[0]
            for row in _execute(
                connection,
                """SELECT DISTINCT display_ticker
                     FROM terminal
                    WHERE disposition='accepted' AND sid=?
                      AND display_ticker IS NOT NULL
                    ORDER BY display_ticker""",
                (sid,),
            )
        )
        display = next(displays, "UNKNOWN")
        terminal_projection = _canonical_array_hash_from_values(
            row[0]
            for row in _execute(
                connection,
                """SELECT terminal_sha FROM terminal
                    WHERE disposition='accepted' AND sid=?
                    ORDER BY terminal_sha""",
                (sid,),
            )
        )
        match_count = _execute(
            connection,
            "SELECT COUNT(*) FROM candidate_cusip WHERE cusip=?",
            (cusip,),
        ).fetchone()[0]
        match = (
            _execute(
                connection,
                """SELECT c.security_id, c.ticker, c.payload
                      FROM candidate_cusip AS x
                      JOIN candidate AS c ON c.security_id=x.security_id
                     WHERE x.cusip=? LIMIT 1""",
                (cusip,),
            ).fetchone()
            if match_count == 1
            else None
        )
        candidate_security_id = match[0] if match is not None else None
        candidate_payload = match[2] if match is not None else None
        current_match = bool(
            candidate_security_id is not None and display == match[1]
        )
        # The reason and logical id are assigned after cross-SID multiplicities
        # are known.  A deterministic placeholder cannot collide with a real id.
        placeholder = "pending-" + hashlib.sha256(sid.encode()).hexdigest()
        _insert(
            connection,
            """INSERT INTO identity(
                   sid, cusip, first_session, last_session, first_available_at,
                   display_ticker, terminal_projection_sha,
                   candidate_security_id, candidate_payload,
                   current_ticker_matches, reason, logical, batch
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL)""",
            (
                sid,
                cusip,
                first_session,
                last_session,
                first_available,
                display,
                terminal_projection,
                candidate_security_id,
                candidate_payload,
                current_match,
                placeholder,
            ),
            "discovery identity",
        )
        identity_count += 1
    if identity_count == 0:
        raise PhysicalHistoricalPreopenBridgeError(
            "discovery has no eligible terminal rows"
        )
    if identity_count > _legacy.MAX_BRIDGE_SECURITY_COUNT:
        raise PhysicalHistoricalPreopenBridgeError(
            "bridge security census exceeds bound"
        )

    cursor = _execute(
        connection,
        "SELECT sid, cusip, candidate_security_id FROM identity ORDER BY sid",
    )
    while True:
        selected = cursor.fetchmany(SQLITE_UPDATE_BATCH_ROWS)
        if not selected:
            break
        updates: list[tuple[object, ...]] = []
        for sid, cusip, candidate_id in selected:
            distinct_cusips = _execute(
                connection,
                """SELECT COUNT(DISTINCT cusip)
                     FROM terminal WHERE disposition='accepted' AND sid=?""",
                (sid,),
            ).fetchone()[0]
            cusip_sids = _execute(
                connection,
                "SELECT COUNT(*) FROM identity WHERE cusip=?",
                (cusip,),
            ).fetchone()[0]
            match_count = _execute(
                connection,
                "SELECT COUNT(*) FROM candidate_cusip WHERE cusip=?",
                (cusip,),
            ).fetchone()[0]
            candidate_sids = (
                _execute(
                    connection,
                    """SELECT COUNT(*) FROM identity
                        WHERE candidate_security_id=?""",
                    (candidate_id,),
                ).fetchone()[0]
                if candidate_id is not None
                else 0
            )
            reason = None
            if distinct_cusips != 1:
                reason = "QC_SID_exposed_conflicting_CUSIPs"
            elif not cusip:
                reason = "missing_QC_CUSIP"
            elif cusip_sids != 1:
                reason = "CUSIP_reused_by_multiple_QC_SIDs"
            elif match_count == 0:
                reason = "CUSIP_missing_from_Sharadar_identity_seeds"
            elif match_count != 1:
                reason = "CUSIP_ambiguous_across_Sharadar_identities"
            elif candidate_sids != 1:
                reason = "Sharadar_share_class_maps_to_multiple_QC_SIDs"
            logical = (
                candidate_id
                if reason is None
                else "qc-join-refusal-"
                + hashlib.sha256(sid.encode()).hexdigest()[:24]
            )
            updates.append((reason, logical, sid))
        _executemany_bounded(
            connection,
            "UPDATE identity SET reason=?, logical=? WHERE sid=?",
            updates,
            "discovery identity classification",
        )
    return identity_count, eligible_terminal_count


def _identity_projection_rows(
    connection: sqlite3.Connection,
) -> Iterator[dict[str, object]]:
    for (
        sid,
        cusip,
        logical,
        reason,
        terminal_projection,
        current_match,
    ) in _execute(
        connection,
        """SELECT sid, cusip, logical, reason, terminal_projection_sha,
                  current_ticker_matches
             FROM identity ORDER BY sid""",
    ):
        yield {
            "qc_security_id": sid,
            "cusip": cusip,
            "logical_security_id": logical,
            "join_disposition": "accepted" if reason is None else "named_refusal",
            "reason": reason,
            "terminal_projection_sha256": terminal_projection,
            "current_ticker_matches": bool(current_match),
        }


def _security_master(
    connection: sqlite3.Connection,
    discovery: ReviewedFundamentalUniverseDiscoveryReceipt,
    seed: PhysicalPreopenSeedArchive,
) -> tuple[str, str, int]:
    identity_count, projection_sha = _hash_canonical_array(
        _identity_projection_rows(connection)
    )
    record = {
        "schema": "arv2-qc-cusip-sharadar-security-master-projection-v1",
        "discovery_receipt_id": discovery.receipt_id,
        "discovery_receipt_sha256": discovery.receipt_sha256,
        "physical_candidate_id": seed.candidate_id,
        "physical_candidate_sha256": seed.candidate_sha256,
        "identity_count": identity_count,
        "identity_projection_sha256": projection_sha,
        "current_ticker_used_as_identity": False,
        "human_reviewed": False,
    }
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    return "arv2-qc-cusip-security-master-" + digest[:24], digest, identity_count


def _info(
    *,
    sid: str,
    cusip: str,
    first_session: str,
    last_session: str,
    first_available: str,
    display: str,
    terminal_projection: str,
    candidate_payload: bytes | None,
    current_match: int,
    reason: str | None,
    logical: str,
) -> dict[str, object]:
    candidate = (
        _decode(candidate_payload, "physical universe candidate")
        if candidate_payload is not None
        else None
    )
    return {
        "qc_security_id": sid,
        "cusip": cusip,
        "first_session": first_session,
        "last_session": last_session,
        "first_available_at": first_available,
        "display_ticker": display,
        "terminal_projection_sha256": terminal_projection,
        "candidate": candidate,
        "current_ticker_matches": bool(current_match),
        "reason": reason,
        "logical_security_id": logical,
    }


def _build_mappings(
    connection: sqlite3.Connection,
    security_master_id: str,
    security_master_sha: str,
) -> tuple[int, int, int]:
    batch = -1
    accepted = 0
    mismatches = 0
    for index, row in enumerate(
        _execute(
            connection,
            """SELECT sid, cusip, first_session, last_session,
                      first_available_at, display_ticker,
                      terminal_projection_sha, candidate_payload,
                      current_ticker_matches, reason, logical
                 FROM identity ORDER BY logical""",
        )
    ):
        batch = index // _legacy.SECURITY_BATCH_SIZE
        info = _info(
            sid=row[0],
            cusip=row[1],
            first_session=row[2],
            last_session=row[3],
            first_available=row[4],
            display=row[5],
            terminal_projection=row[6],
            candidate_payload=row[7],
            current_match=row[8],
            reason=row[9],
            logical=row[10],
        )
        mapping = _legacy._mapping_row(
            info, security_master_id, security_master_sha
        )
        mapping["row_sha256"] = hashlib.sha256(
            canonical_json_bytes(mapping)
        ).hexdigest()
        is_accepted = info["reason"] is None
        if is_accepted:
            accepted += 1
            mismatches += info["current_ticker_matches"] is False
        _insert(
            connection,
            """INSERT INTO mapping(
                   sid, logical, batch, accepted, issuer_id, share_class_id,
                   listing_id, payload
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                info["qc_security_id"],
                info["logical_security_id"],
                batch,
                is_accepted,
                mapping["issuer_id"],
                mapping["share_class_id"],
                mapping["listing_id"],
                canonical_json_bytes(mapping),
            ),
            "QC SID mapping",
        )
        _execute(
            connection,
            "UPDATE identity SET batch=? WHERE sid=?",
            (batch, info["qc_security_id"]),
        )
    return batch + 1, accepted, mismatches


def _quality_measurement(
    *,
    logical: str,
    session: str,
    available_at: str,
    seed: PhysicalPreopenSeedArchive,
    identity_hash: str,
    firm_hash: str,
    quality_hash: str,
) -> dict[str, object]:
    sources = (
        (
            "timestamp_quality",
            seed.accepted_risk_archive_id,
            seed.accepted_risk_archive_sha256,
            False,
            True,
        ),
        (
            "firm_label_mapping_quality",
            "unreviewed-firm-ontology",
            firm_hash,
            True,
            False,
        ),
        (
            "security_entity_mapping_quality",
            "qc-cusip-sharadar-join",
            identity_hash,
            True,
            False,
        ),
    )
    components = []
    for kind, source_id, source_hash, point_in_time, accepted_risk in sources:
        semantic = {
            "kind": kind,
            "value": "0",
            "source_id": source_id,
            "source_sha256": source_hash,
            "payload_sha256": source_hash,
            "available_at": available_at,
            "point_in_time": point_in_time,
            "accepted_risk_non_pristine": accepted_risk,
        }
        components.append(
            {
                **semantic,
                "evidence_sha256": hashlib.sha256(
                    canonical_json_bytes(semantic)
                ).hexdigest(),
            }
        )
    semantic = {
        "security_id": logical,
        "measured_session": session,
        "source_id": "arv2-unreviewed-zero-quality-bridge",
        "source_sha256": quality_hash,
        "components": components,
        "measurement_method_id": "arv2-qdata-conservative-min-v1",
        "q_data": "0",
        "available_at": available_at,
        "point_in_time": True,
    }
    return {
        **semantic,
        "evidence_sha256": hashlib.sha256(
            canonical_json_bytes(semantic)
        ).hexdigest(),
    }


def _mapping_and_info(
    connection: sqlite3.Connection, sid: str
) -> tuple[dict[str, object], dict[str, object], int]:
    row = _execute(
        connection,
        """SELECT i.cusip, i.first_session, i.last_session,
                  i.first_available_at, i.display_ticker,
                  i.terminal_projection_sha, i.candidate_payload,
                  i.current_ticker_matches, i.reason, i.logical,
                  m.batch, m.payload
             FROM identity AS i JOIN mapping AS m ON m.sid=i.sid
            WHERE i.sid=?""",
        (sid,),
    ).fetchone()
    if row is None:
        raise PhysicalHistoricalPreopenBridgeError(
            "accepted discovery identity is missing from bridge"
        )
    return (
        _info(
            sid=sid,
            cusip=row[0],
            first_session=row[1],
            last_session=row[2],
            first_available=row[3],
            display=row[4],
            terminal_projection=row[5],
            candidate_payload=row[6],
            current_match=row[7],
            reason=row[8],
            logical=row[9],
        ),
        _decode(row[11], "QC SID mapping"),
        row[10],
    )


def _increment_batch(
    connection: sqlite3.Connection, batch: int, session: str, accepted: bool
) -> None:
    _execute(
        connection,
        "INSERT OR IGNORE INTO batch_counts(batch) VALUES (?)",
        (batch,),
    )
    _execute(
        connection,
        """UPDATE batch_counts
              SET terminal_count=terminal_count+1,
                  accepted_count=accepted_count+?
            WHERE batch=?""",
        (int(accepted), batch),
    )
    _execute(
        connection,
        "INSERT OR IGNORE INTO batch_session(batch, session) VALUES (?, ?)",
        (batch, session),
    )
    if accepted:
        _execute(
            connection,
            """INSERT INTO batch_session_accepted(batch, session, accepted_count)
               VALUES (?, ?, 1)
               ON CONFLICT(batch, session) DO UPDATE
               SET accepted_count=accepted_count+1""",
            (batch, session),
        )


def _build_universe_rows(
    connection: sqlite3.Connection,
    discovery: ReviewedFundamentalUniverseDiscoveryReceipt,
    seed: PhysicalPreopenSeedArchive,
    firm_hash: str,
    quality_hash: str,
) -> None:
    for (payload,) in _execute(
        connection,
        """SELECT payload FROM terminal
            WHERE disposition='accepted' ORDER BY stream_ordinal""",
    ):
        source = _decode(payload, "discovery terminal")
        info, mapping, batch = _mapping_and_info(
            connection, source["qc_security_id"]
        )
        ordinal_row = _execute(
            connection,
            "SELECT ordinal FROM full_session WHERE session=?",
            (source["decision_session"],),
        ).fetchone()
        if ordinal_row is None:
            raise PhysicalHistoricalPreopenBridgeError(
                "discovery session is outside full NYSE axis"
            )
        common = {
            "schema": UNIVERSE_INPUT_SCHEMA,
            "decision_session": source["decision_session"],
            "decision_session_ordinal": ordinal_row[0],
            "decision_open_utc": source["decision_open_utc"],
            "security_id": info["logical_security_id"],
            "qc_security_id": source["qc_security_id"],
            "issuer_id": mapping["issuer_id"],
            "share_class_id": mapping["share_class_id"],
            "listing_id": mapping["listing_id"],
            "historical_ticker": info["display_ticker"],
            "security_master_row_sha256": mapping[
                "ticker_interval_evidence_sha256"
            ],
            "qc_sid_mapping_row_sha256": mapping["row_sha256"],
        }
        accepted = info["reason"] is None
        if accepted:
            measurement = _quality_measurement(
                logical=info["logical_security_id"],
                session=source["decision_session"],
                available_at=source["available_at"],
                seed=seed,
                identity_hash=source["identity_evidence_sha256"],
                firm_hash=firm_hash,
                quality_hash=quality_hash,
            )
            universe = {
                **common,
                "disposition": "accepted",
                "sector_id": "morningstar-sector-"
                + str(source["morningstar_sector_code"]),
                "industry_id": "morningstar-industry-"
                + str(source["morningstar_industry_code"]),
                "q_data": "0",
                "source_id": discovery.receipt_id,
                "q_data_measurement": measurement,
                "source_sha256": discovery.receipt_sha256,
                "identity_evidence_sha256": source["identity_evidence_sha256"],
                "identity_available_at": source["available_at"],
                "classification_evidence_sha256": source[
                    "classification_evidence_sha256"
                ],
                "classification_available_at": source["available_at"],
                "q_data_evidence_sha256": measurement["evidence_sha256"],
                "q_data_available_at": source["available_at"],
            }
            requested = _execute(
                connection,
                """SELECT 1 FROM requested_quality
                    WHERE security_id=? AND session=?""",
                (info["logical_security_id"], source["decision_session"]),
            ).fetchone()
            if requested is not None:
                _insert(
                    connection,
                    """INSERT INTO quality(
                           security_id, session, q_data, evidence_sha
                       ) VALUES (?, ?, ?, ?)""",
                    (
                        info["logical_security_id"],
                        source["decision_session"],
                        "0",
                        measurement["evidence_sha256"],
                    ),
                    "same-session quality binding",
                )
            for axis, value in (
                ("sector", universe["sector_id"]),
                ("industry", universe["industry_id"]),
            ):
                _execute(
                    connection,
                    """INSERT OR IGNORE INTO peer_key(session, axis, value)
                       VALUES (?, ?, ?)""",
                    (source["decision_session"], axis, value),
                )
        else:
            universe = {
                **common,
                "disposition": "named_refusal",
                "census_refusal": _legacy._refusal(
                    info["logical_security_id"], mapping, source, info["reason"]
                ),
            }
        encoded = canonical_json_bytes(universe)
        _insert(
            connection,
            "INSERT INTO input_row(role, batch, payload) VALUES ('universe', ?, ?)",
            (batch, encoded),
            "universe input row",
        )
        _insert(
            connection,
            "INSERT INTO universe_key(session, security_id) VALUES (?, ?)",
            (source["decision_session"], info["logical_security_id"]),
            "universe security/session",
        )
        _increment_batch(
            connection, batch, source["decision_session"], accepted
        )
        current = _execute(
            connection,
            """SELECT opened, full_ordinal FROM session_geometry
                WHERE session=?""",
            (source["decision_session"],),
        ).fetchone()
        if current is not None and (
            current[0] != source["decision_open_utc"]
            or current[1] != ordinal_row[0]
        ):
            raise PhysicalHistoricalPreopenBridgeError(
                "discovery session open changed"
            )
        _execute(
            connection,
            """INSERT INTO session_geometry(
                   session, opened, full_ordinal, terminal_count
               ) VALUES (?, ?, ?, 1)
               ON CONFLICT(session) DO UPDATE
               SET terminal_count=terminal_count+1""",
            (
                source["decision_session"],
                source["decision_open_utc"],
                ordinal_row[0],
            ),
        )


def _select_control_rows(connection: sqlite3.Connection) -> int:
    excluded = 0
    for role, _schema, _source in _ROLE_SPECS:
        for security_id, payload in _execute(
            connection,
            """SELECT security_id, payload FROM role_seed
                WHERE role=? ORDER BY source_ordinal""",
            (role,),
        ):
            mapping = _execute(
                connection,
                """SELECT batch FROM mapping
                    WHERE logical=? AND accepted=1""",
                (security_id,),
            ).fetchone()
            if mapping is None:
                excluded += 1
                continue
            _insert(
                connection,
                "INSERT INTO input_row(role, batch, payload) VALUES (?, ?, ?)",
                (role, mapping[0], payload),
                f"{role} input row",
            )
    for batch, payload in _execute(
        connection,
        "SELECT batch, payload FROM mapping ORDER BY batch, logical",
    ):
        _insert(
            connection,
            "INSERT INTO input_row(role, batch, payload) VALUES ('sid_mapping', ?, ?)",
            (batch, payload),
            "SID mapping input row",
        )
    return excluded


def _analyst_evidence_rows(
    connection: sqlite3.Connection,
) -> Iterator[dict[str, object]]:
    for ordinal, payload in _execute(
        connection,
        """SELECT source_ordinal, payload FROM composition_terminal
            WHERE source_role='analyst_ratings' ORDER BY source_ordinal""",
    ):
        terminal = _decode(payload, "analyst composition terminal")
        physical_id = terminal["security_id"]
        provider_id = terminal["provider_event_id"]
        common_id = (
            _legacy._common_event_id(provider_id)
            if type(provider_id) is str
            else "refused-event-" + terminal["raw_row_sha256"][:24]
        )
        rating_cursor = (
            _execute(
                connection,
                """SELECT eligible_ordinal, admitted, payload
                      FROM rating
                     WHERE security_id=? AND common_event_id=?
                     ORDER BY source_ordinal LIMIT 2""",
                (physical_id, common_id),
            )
            if type(physical_id) is str
            else None
        )
        ratings = rating_cursor.fetchmany(2) if rating_cursor is not None else []
        rating_row = ratings[0] if len(ratings) == 1 else None
        rating = (
            _decode(rating_row[2], "analyst rating seed")
            if rating_row is not None
            else None
        )
        decision_session_row = (
            _execute(
                connection,
                "SELECT session FROM full_session WHERE ordinal=?",
                (rating_row[0],),
            ).fetchone()
            if rating_row is not None
            else None
        )
        decision_session = (
            decision_session_row[0] if decision_session_row is not None else None
        )
        joined_cursor = (
            _execute(
                connection,
                """SELECT sid, reason, cusip FROM identity
                    WHERE candidate_security_id=? ORDER BY sid LIMIT 2""",
                (physical_id,),
            )
            if type(physical_id) is str
            else None
        )
        joined = joined_cursor.fetchmany(2) if joined_cursor is not None else []
        identity = joined[0] if len(joined) == 1 else None
        mapping = (
            _execute(
                connection,
                """SELECT payload FROM mapping WHERE sid=?""",
                (identity[0],),
            ).fetchone()
            if identity is not None
            else None
        )
        mapping_row = (
            _decode(mapping[0], "analyst QC SID mapping")
            if mapping is not None
            else None
        )
        reason = None
        if terminal["preopen_composition_disposition"] not in {
            "emitted",
            "coalesced_exact_control_anchor",
        }:
            reason = "analyst_event_was_not_emitted_to_the_control_seed"
        elif type(physical_id) is not str:
            reason = "analyst_event_has_no_physical_security_identity"
        elif len(joined) != 1:
            reason = "analyst_event_security_join_is_missing_or_ambiguous"
        elif identity[1] is not None:
            reason = identity[1]
        elif len(ratings) != 1:
            reason = "analyst_event_has_no_unique_rating_seed"
        elif rating["admitted"] is not True:
            reason = "analyst_event_rating_seed_is_not_admitted"
        elif decision_session is None:
            reason = "analyst_event_session_is_outside_bridge_geometry"
        quality = (
            _execute(
                connection,
                """SELECT q_data, evidence_sha FROM quality
                    WHERE security_id=? AND session=?""",
                (physical_id, decision_session),
            ).fetchone()
            if type(physical_id) is str and decision_session is not None
            else None
        )
        if reason is None and quality is None:
            reason = "analyst_event_has_no_same_session_universe_quality_binding"
        semantic = {
            "schema": _legacy.ANALYST_EVENT_BINDING_SCHEMA,
            "locator_sha256": terminal["locator_sha256"],
            "raw_row_sha256": terminal["raw_row_sha256"],
            "provider_event_id": provider_id,
            "common_event_id": common_id,
            "source_role": terminal["source_role"],
            "current_view_disposition": terminal["current_view_disposition"],
            "censored_view_disposition": terminal["censored_view_disposition"],
            "preopen_composition_disposition": terminal[
                "preopen_composition_disposition"
            ],
            "preopen_composition_reason": terminal["reason"],
            "physical_security_id": physical_id,
            "decision_session": decision_session,
            "decision_session_ordinal": (
                rating["eligible_session_ordinal"] if rating is not None else None
            ),
            "available_at": rating["available_at"] if rating is not None else None,
            "rating_admitted": rating["admitted"] if rating is not None else None,
            "rating_seed_row_sha256": (
                hashlib.sha256(canonical_json_bytes(rating)).hexdigest()
                if rating is not None
                else None
            ),
            "binding_disposition": "accepted" if reason is None else "named_refusal",
            "binding_reason": reason,
            "qc_security_id": identity[0] if identity is not None else None,
            "cusip": identity[2] if identity is not None else None,
            "issuer_id": mapping_row["issuer_id"] if mapping_row is not None else None,
            "share_class_id": (
                mapping_row["share_class_id"] if mapping_row is not None else None
            ),
            "listing_id": mapping_row["listing_id"] if mapping_row is not None else None,
            "historical_ticker": (
                mapping_row["historical_ticker"] if mapping_row is not None else None
            ),
            "mapping_first_session": (
                mapping_row["first_session"] if mapping_row is not None else None
            ),
            "mapping_last_session": (
                mapping_row["last_session"] if mapping_row is not None else None
            ),
            "mapping_available_at": (
                mapping_row["available_at"] if mapping_row is not None else None
            ),
            "mapping_closure_available_at": None,
            "mapping_row_sha256": (
                mapping_row["row_sha256"] if mapping_row is not None else None
            ),
            "q_data": quality[0] if reason is None else None,
            "q_data_evidence_sha256": quality[1] if reason is None else None,
        }
        yield {
            **semantic,
            "binding_sha256": hashlib.sha256(
                canonical_json_bytes(semantic)
            ).hexdigest(),
        }


def _lifecycle_evidence_rows(
    connection: sqlite3.Connection,
) -> Iterator[dict[str, object]]:
    for _ordinal, payload in _execute(
        connection,
        "SELECT stream_ordinal, payload FROM terminal ORDER BY stream_ordinal",
    ):
        source = _decode(payload, "discovery lifecycle terminal")
        sid = source.get("qc_security_id")
        identity_row = (
            _execute(
                connection,
                "SELECT logical, reason FROM identity WHERE sid=?",
                (sid,),
            ).fetchone()
            if type(sid) is str
            else None
        )
        mapping = (
            _execute(
                connection,
                "SELECT payload FROM mapping WHERE sid=?",
                (sid,),
            ).fetchone()
            if identity_row is not None
            else None
        )
        mapping_row = (
            _decode(mapping[0], "lifecycle QC SID mapping")
            if mapping is not None
            else None
        )
        if source["disposition"] != "accepted":
            join_disposition = "not_applicable_discovery_terminal"
            join_reason = source["refusal_reason"]
        elif identity_row is None:
            join_disposition = "named_refusal"
            join_reason = "accepted_discovery_identity_missing_from_bridge"
        elif identity_row[1] is not None:
            join_disposition = "named_refusal"
            join_reason = identity_row[1]
        else:
            join_disposition = "accepted"
            join_reason = None
        semantic = {
            "schema": _legacy.UNIVERSE_LIFECYCLE_BINDING_SCHEMA,
            "decision_session": source["decision_session"],
            "decision_session_ordinal": source["decision_session_ordinal"],
            "decision_open_utc": source["decision_open_utc"],
            "source_ordinal": source["source_ordinal"],
            "discovery_disposition": source["disposition"],
            "discovery_refusal_reason": source["refusal_reason"],
            "qc_security_id": source["qc_security_id"],
            "cusip": source["cusip"],
            "display_ticker_non_authoritative": source[
                "display_ticker_non_authoritative"
            ],
            "logical_security_id": (
                identity_row[0] if identity_row is not None else None
            ),
            "issuer_id": (
                mapping_row["issuer_id"]
                if mapping_row is not None
                else source["issuer_id"]
            ),
            "share_class_id": (
                mapping_row["share_class_id"]
                if mapping_row is not None
                else source["share_class_id"]
            ),
            "listing_id": (
                mapping_row["listing_id"]
                if mapping_row is not None
                else source["listing_id"]
            ),
            "delisting_date": source["delisting_date"],
            "available_at": source["available_at"],
            "identity_evidence_sha256": source["identity_evidence_sha256"],
            "source_terminal_sha256": source["terminal_sha256"],
            "mapping_row_sha256": (
                mapping_row["row_sha256"] if mapping_row is not None else None
            ),
            "bridge_join_disposition": join_disposition,
            "bridge_join_reason": join_reason,
            "lifecycle_evidence_only": True,
            "payoff_semantics_assigned": False,
        }
        yield {
            **semantic,
            "binding_sha256": hashlib.sha256(
                canonical_json_bytes(semantic)
            ).hexdigest(),
        }


def _spool_evidence(connection: sqlite3.Connection) -> None:
    for role, rows in (
        ("analyst_event_binding", _analyst_evidence_rows(connection)),
        ("universe_lifecycle_binding", _lifecycle_evidence_rows(connection)),
    ):
        count = 0
        for count, row in enumerate(rows, start=1):
            _insert(
                connection,
                "INSERT INTO evidence(role, source_ordinal, payload) VALUES (?, ?, ?)",
                (role, count - 1, canonical_json_bytes(row)),
                f"{role} evidence ordinal",
            )


def _write_role_shards(
    *,
    connection: sqlite3.Connection,
    root: Path,
    role: str,
    batch: int,
    first_session: str,
    last_session: str,
) -> tuple[list[dict[str, object]], list[_legacy._ArchiveBinding]]:
    sql = """SELECT payload FROM input_row
             WHERE batch=? AND role=? ORDER BY payload"""
    _require_indexed_plan(connection, sql, (batch, role))
    cursor = _execute(connection, sql, (batch, role))
    descriptors: list[dict[str, object]] = []
    bindings: list[_legacy._ArchiveBinding] = []
    rows: list[dict[str, object]] = []
    retained_bytes = 0

    def flush() -> None:
        nonlocal rows, retained_bytes
        ordinal = len(descriptors)
        shard = build_preopen_input_shard(
            role=role,
            security_batch_ordinal=batch,
            ordinal=ordinal,
            partition_first_session=first_session,
            partition_last_session=last_session,
            rows=rows,
        )
        relative = _legacy._archive_shard_path(shard)
        binding = _legacy._ArchiveBinding(
            role=role,
            batch=batch,
            ordinal=ordinal,
            relative_path=relative,
            sha256=shard.compressed_sha256,
            byte_count=shard.compressed_byte_count,
            uncompressed_sha256=shard.uncompressed_sha256,
            uncompressed_byte_count=shard.uncompressed_byte_count,
            row_count=shard.row_count,
            stat_identity=_legacy._write_private(root / relative, shard.payload),
        )
        descriptors.append(shard.descriptor())
        bindings.append(binding)
        rows = []
        retained_bytes = 0

    for (payload,) in cursor:
        if rows and len(rows) >= _legacy.MAX_ROLE_ROWS_PER_SHARD:
            flush()
        retained_bytes += len(payload)
        if retained_bytes > MAX_UNCOMPRESSED_SHARD_BYTES:
            raise PhysicalHistoricalPreopenBridgeCapacityError(
                f"{role} input shard exceeds its fixed uncompressed byte bound"
            )
        rows.append(_decode(payload, f"{role} spooled input row"))
    if rows or not descriptors:
        flush()
    return descriptors, bindings


def _batch_metrics(
    connection: sqlite3.Connection,
    batch: int,
    descriptors: list[dict[str, object]],
    first_session: str,
    last_session: str,
) -> dict[str, object]:
    logicals = list(
        _execute(
            connection,
            "SELECT logical, accepted FROM mapping WHERE batch=? ORDER BY logical",
            (batch,),
        )
    )
    if not logicals or len(logicals) > _legacy.SECURITY_BATCH_SIZE:
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge security batch geometry changed"
        )
    accepted = sum(bool(item[1]) for item in logicals)
    counts = _execute(
        connection,
        "SELECT terminal_count, accepted_count FROM batch_counts WHERE batch=?",
        (batch,),
    ).fetchone()
    if counts is None:
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge universe batch is absent"
        )
    maximum_session_accepted = _execute(
        connection,
        """SELECT COALESCE(MAX(accepted_count), 0)
            FROM batch_session_accepted WHERE batch=?""",
        (batch,),
    ).fetchone()[0]
    decision_session_count = _execute(
        connection,
        "SELECT COUNT(*) FROM batch_session WHERE batch=?",
        (batch,),
    ).fetchone()[0]
    compressed = sum(item["compressed_byte_count"] for item in descriptors)
    uncompressed = sum(item["uncompressed_byte_count"] for item in descriptors)
    row_count = sum(item["row_count"] for item in descriptors)
    observations = (
        date.fromisoformat(last_session) - date.fromisoformat(first_session)
    ).days + _legacy.HISTORY_LOOKBACK_CALENDAR_DAYS + 1
    buffered = (accepted * 2 + 1) * observations
    if (
        compressed > MAX_BLOCK_COMPRESSED_INPUT_BYTES
        or uncompressed > MAX_BLOCK_UNCOMPRESSED_INPUT_BYTES
        or row_count > MAX_BLOCK_INPUT_ROW_COUNT
        or buffered > MAX_BUFFERED_MARKET_OBSERVATION_COUNT
    ):
        raise PhysicalHistoricalPreopenBridgeError(
            "one bridge security batch exceeds stage capacity"
        )
    return {
        "security_batch_ordinal": batch,
        "first_session": first_session,
        "last_session": last_session,
        "first_security_id": logicals[0][0],
        "last_security_id": logicals[-1][0],
        "decision_session_count": decision_session_count,
        "universe_terminal_count": counts[0],
        "distinct_security_count": len(logicals),
        "distinct_accepted_security_count": accepted,
        "distinct_accepted_history_symbol_count": accepted,
        "projected_history_call_count": 4 if accepted else 0,
        "projected_total_market_observation_count": accepted * 4 * observations,
        "maximum_buffered_market_observation_count": buffered,
        "maximum_derived_market_summary_count": maximum_session_accepted,
        "compressed_input_byte_count": compressed,
        "uncompressed_input_byte_count": uncompressed,
        "input_row_count": row_count,
    }


class _SqlSessionGeometry(Mapping[str, dict[str, object]]):
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def __iter__(self):
        for (session,) in _execute(
            self._connection,
            "SELECT session FROM session_geometry ORDER BY session",
        ):
            yield session

    def __len__(self):
        return _execute(
            self._connection, "SELECT COUNT(*) FROM session_geometry"
        ).fetchone()[0]

    def __getitem__(self, session: str):
        row = _execute(
            self._connection,
            """SELECT opened, full_ordinal, terminal_count
                FROM session_geometry WHERE session=?""",
            (session,),
        ).fetchone()
        if row is None:
            raise KeyError(session)
        return {
            "decision_session": session,
            "decision_open_utc": row[0],
            "decision_session_ordinal": row[1],
            "terminal_count": row[2],
        }


class _SqlBatchMemberships:
    def __init__(self, connection: sqlite3.Connection, batch_count: int):
        self._connection = connection
        self._batch_count = batch_count

    def values(self):
        for batch in range(self._batch_count):
            yield (
                row[0]
                for row in _execute(
                    self._connection,
                    """SELECT session FROM batch_session
                        WHERE batch=? ORDER BY session""",
                    (batch,),
                )
            )


class _SqlPeerKeys:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection

    def __len__(self):
        return _execute(
            self._connection, "SELECT COUNT(*) FROM peer_key"
        ).fetchone()[0]


def _iter_evidence(
    connection: sqlite3.Connection, role: str
) -> Iterator[dict[str, object]]:
    for (payload,) in _execute(
        connection,
        """SELECT payload FROM evidence
            WHERE role=? ORDER BY source_ordinal""",
        (role,),
    ):
        yield _decode(payload, f"{role} evidence row")


def _truth_bindings(
    seed: PhysicalPreopenSeedArchive,
    discovery: ReviewedFundamentalUniverseDiscoveryReceipt,
    security_master_id: str,
    security_master_sha: str,
) -> list[dict[str, object]]:
    discovery_binding = _discovery.fundamental_discovery_artifact_binding_record(
        discovery
    )["eligible_universe_source"]
    firm = _artifact(seed, "firm_review_candidate")
    common = _artifact(seed, "source_seed_candidate")
    quality = _artifact(seed, "quality_policy")
    values = {
        "accepted_risk_capture": (
            seed.accepted_risk_archive_id,
            seed.accepted_risk_archive_sha256,
        ),
        "eligible_universe": (
            discovery_binding["artifact_id"],
            discovery_binding["artifact_sha256"],
        ),
        "security_master": (security_master_id, security_master_sha),
        "firm_ontology": (firm.artifact_id, firm.content_sha256),
        "common_event": (common.artifact_id, common.content_sha256),
        "sector_classification": (
            discovery_binding["artifact_id"],
            discovery_binding["artifact_sha256"],
        ),
        "preopen_control": (seed.candidate_id, seed.candidate_sha256),
        "data_quality": (
            "arv2-zero-quality-policy-" + quality.content_sha256[:24],
            quality.content_sha256,
        ),
    }
    return [
        {
            "kind": kind,
            "artifact_id": values[kind][0],
            "artifact_sha256": values[kind][1],
        }
        for kind in _legacy.TRUTH_SOURCE_ROLE_ORDER
    ]


def _manifest_candidate(seed: PhysicalPreopenSeedArchive):
    completeness = dict(seed.source_completeness)
    return SimpleNamespace(
        calculation_session=seed.calculation_session,
        massive_bridge_id=seed.accepted_risk_archive_id,
        massive_bridge_sha256=seed.accepted_risk_archive_sha256,
        candidate_id=seed.candidate_id,
        candidate_sha256=seed.candidate_sha256,
        source_seed_candidate_bytes=canonical_json_bytes(
            {"artifact_id": "temporary-manifest-facade"}
        ),
        firm_review_candidate_bytes=canonical_json_bytes(
            {"candidate_id": "temporary-manifest-facade"}
        ),
        quality_policy_bytes=canonical_json_bytes({"facade": True}),
        rating_source_complete_for_frozen_query_and_accepted_risk_policy=(
            completeness[MassiveSourceRole.ANALYST_RATINGS]
        ),
        earnings_source_complete_for_frozen_query_and_accepted_risk_policy=(
            completeness[MassiveSourceRole.EARNINGS]
        ),
        guidance_source_complete_for_frozen_query_and_accepted_risk_policy=(
            completeness[MassiveSourceRole.CORPORATE_GUIDANCE]
        ),
    )


def _mint(
    *,
    record: dict[str, object],
    archive_root: Path,
    root_stat,
    shard_stat,
    evidence_stat,
    bindings: list[_legacy._ArchiveBinding],
    manifest_bytes: bytes,
) -> _legacy.ReviewedHistoricalUniverseToPreopenBridge:
    digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    value = object.__new__(_legacy.ReviewedHistoricalUniverseToPreopenBridge)
    values = {
        **record,
        "bridge_id": "arv2-reviewed-historical-preopen-" + digest[:24],
        "bridge_sha256": digest,
        "closed_input_manifest_bytes": manifest_bytes,
        "_archive_root": archive_root,
        "_archive_root_stat": root_stat,
        "_archive_shard_dir_stat": shard_stat,
        "_archive_evidence_dir_stat": evidence_stat,
        "_archive_bindings": tuple(bindings),
    }
    if set(values) != {
        field.name for field in dataclasses.fields(value)
    }:
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge authority field inventory changed"
        )
    for name, item in values.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _legacy._forget(key, ref)
    )
    with _legacy._AUTHORITY_LOCK:
        _legacy._AUTHORITIES[identity] = (
            reference,
            _legacy._fingerprint(value),
        )
    return _legacy.require_reviewed_historical_universe_to_preopen_bridge(value)


def build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed(
    discovery_receipt: ReviewedFundamentalUniverseDiscoveryReceipt,
    physical_seed: PhysicalPreopenSeedArchive,
    archive_root: Path,
) -> _legacy.ReviewedHistoricalUniverseToPreopenBridge:
    """Build the exact legacy bridge authority through bounded disk joins."""

    if type(discovery_receipt) is not ReviewedFundamentalUniverseDiscoveryReceipt:
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge requires exact discovery receipt type"
        )
    if type(physical_seed) is not PhysicalPreopenSeedArchive:
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge requires exact physical seed type"
        )
    try:
        discovery = _discovery.require_reviewed_fundamental_universe_discovery_receipt(
            discovery_receipt
        )
        seed = _seed.require_physical_preopen_seed_archive(physical_seed)
    except Exception as exc:
        raise PhysicalHistoricalPreopenBridgeError(
            "historical bridge parent authority revalidation failed"
        ) from exc
    if (
        discovery.first_session != seed.first_session
        or discovery.last_session != seed.last_session
    ):
        raise PhysicalHistoricalPreopenBridgeError(
            "discovery and physical seed geometry differ"
        )
    final_root = _separate_output(archive_root, discovery, seed)
    firm = _artifact(seed, "firm_review_candidate")
    quality = _artifact(seed, "quality_policy")
    source_seed = _artifact(seed, "source_seed_candidate")
    if firm.artifact_id is None or source_seed.artifact_id is None:
        raise PhysicalHistoricalPreopenBridgeError(
            "physical seed conceptual artifact identity changed"
        )

    with tempfile.TemporaryDirectory(prefix="arv2-physical-historical-") as temporary:
        spool = Path(temporary) / "bridge.sqlite3"
        connection = _open_spool(spool)
        stage_root: Path | None = None
        published = False
        preserve_stage = False
        try:
            _create_schema(connection)
            _ingest_sessions(connection, discovery, seed)
            _ingest_candidates(connection, seed)
            _ingest_discovery(connection, discovery)
            _ingest_role_seeds(connection, seed)
            _ingest_composition_terminals(connection, seed)
            identity_count, eligible_terminal_count = _derive_identities(connection)
            security_master_id, security_master_sha, projection_count = (
                _security_master(connection, discovery, seed)
            )
            if projection_count != identity_count:
                raise PhysicalHistoricalPreopenBridgeError(
                    "security-master identity projection census changed"
                )
            batch_count, accepted_count, mismatch_count = _build_mappings(
                connection, security_master_id, security_master_sha
            )
            excluded_seed_rows = _select_control_rows(connection)
            _build_universe_rows(
                connection,
                discovery,
                seed,
                firm.content_sha256,
                quality.content_sha256,
            )
            _spool_evidence(connection)
            try:
                connection.commit()
            except sqlite3.Error as exc:
                if _sqlite_full(exc):
                    raise PhysicalHistoricalPreopenBridgeCapacityError(
                        "historical bridge SQLite spool reached its fixed byte bound"
                    ) from exc
                raise PhysicalHistoricalPreopenBridgeError(
                    "historical bridge SQLite spool could not be committed"
                ) from exc

            if batch_count < 1:
                raise PhysicalHistoricalPreopenBridgeError(
                    "historical bridge has no security batch"
                )
            try:
                stage_root = _create_private_stage(final_root)
                root = stage_root
                shard_dir = root / _legacy.ARCHIVE_SHARD_DIRECTORY
                shard_dir.mkdir(mode=0o700)
                evidence_dir = root / _legacy.ARCHIVE_EVIDENCE_DIRECTORY
                evidence_dir.mkdir(mode=0o700)
            except OSError as exc:
                raise PhysicalHistoricalPreopenBridgeError(
                    "historical bridge archive directories could not be created"
                ) from exc
            _legacy._stat(root, directory=True)
            _legacy._stat(shard_dir, directory=True)
            _legacy._stat(evidence_dir, directory=True)

            descriptors: list[dict[str, object]] = []
            bindings: list[_legacy._ArchiveBinding] = []
            batch_metrics: list[dict[str, object]] = []
            for batch in range(batch_count):
                before = len(descriptors)
                for role in INPUT_ROLE_ORDER:
                    built, physical = _write_role_shards(
                        connection=connection,
                        root=root,
                        role=role,
                        batch=batch,
                        first_session=discovery.first_session,
                        last_session=discovery.last_session,
                    )
                    descriptors.extend(built)
                    bindings.extend(physical)
                batch_metrics.append(
                    _batch_metrics(
                        connection,
                        batch,
                        descriptors[before:],
                        discovery.first_session,
                        discovery.last_session,
                    )
                )

            bindings.extend(
                _legacy._write_evidence_shards(
                    root=root,
                    role="analyst_event_binding",
                    rows=_iter_evidence(connection, "analyst_event_binding"),
                )
            )
            bindings.extend(
                _legacy._write_evidence_shards(
                    root=root,
                    role="universe_lifecycle_binding",
                    rows=_iter_evidence(connection, "universe_lifecycle_binding"),
                )
            )
            if (
                len(descriptors) > _legacy.MAX_ARCHIVE_SHARD_COUNT
                or len(bindings) > _legacy.MAX_ARCHIVE_SHARD_COUNT
            ):
                raise PhysicalHistoricalPreopenBridgeError(
                    "historical bridge physical shard inventory exceeds bound"
                )

            manifest = _legacy._manifest(
                descriptors=descriptors,
                batch_metrics=batch_metrics,
                batch_session_memberships=_SqlBatchMemberships(
                    connection, batch_count
                ),
                session_geometry=_SqlSessionGeometry(connection),
                peer_keys=_SqlPeerKeys(connection),
                candidate=_manifest_candidate(seed),
                discovery=discovery,
                security_master_id=security_master_id,
                security_master_sha=security_master_sha,
            )
            manifest["truth_source_bindings"] = _truth_bindings(
                seed, discovery, security_master_id, security_master_sha
            )
            manifest_bytes = canonical_json_bytes(manifest)
            if len(manifest_bytes) > _legacy.MAX_ARCHIVE_MANIFEST_BYTES:
                raise PhysicalHistoricalPreopenBridgeCapacityError(
                    "closed input manifest exceeds byte bound"
                )
            manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
            manifest_stat = _legacy._write_private(
                root / _legacy.ARCHIVE_MANIFEST_NAME, manifest_bytes
            )
            bindings.insert(
                0,
                _legacy._ArchiveBinding(
                    role="closed_input_manifest",
                    batch=None,
                    ordinal=None,
                    relative_path=_legacy.ARCHIVE_MANIFEST_NAME,
                    sha256=manifest_hash,
                    byte_count=len(manifest_bytes),
                    uncompressed_sha256=None,
                    uncompressed_byte_count=None,
                    row_count=None,
                    stat_identity=manifest_stat,
                ),
            )

            analyst_inventory, analyst_shards, analyst_rows = (
                _legacy._binding_inventory(bindings, "analyst_event_binding")
            )
            lifecycle_inventory, lifecycle_shards, lifecycle_rows = (
                _legacy._binding_inventory(bindings, "universe_lifecycle_binding")
            )
            discovery_binding = (
                _discovery.fundamental_discovery_artifact_binding_record(discovery)
            )
            accepted_universe = _execute(
                connection,
                "SELECT COALESCE(SUM(accepted_count), 0) FROM batch_counts",
            ).fetchone()[0]
            record = {
                "schema": _legacy.BRIDGE_SCHEMA,
                "discovery_receipt_id": discovery.receipt_id,
                "discovery_receipt_sha256": discovery.receipt_sha256,
                "physical_candidate_id": seed.candidate_id,
                "physical_candidate_sha256": seed.candidate_sha256,
                "accepted_risk_bridge_id": seed.accepted_risk_archive_id,
                "accepted_risk_bridge_sha256": seed.accepted_risk_archive_sha256,
                "pair_id": seed.pair_id,
                "pair_sha256": seed.pair_sha256,
                "derived_capture_id": seed.derived_massive_capture_id,
                "derived_capture_sha256": seed.derived_massive_capture_sha256,
                "sharadar_capture_id": seed.sharadar_capture_id,
                "sharadar_capture_sha256": seed.sharadar_capture_sha256,
                "discovery_eligible_universe_artifact_id": discovery_binding[
                    "eligible_universe_source"
                ]["artifact_id"],
                "discovery_eligible_universe_artifact_sha256": discovery_binding[
                    "eligible_universe_source"
                ]["artifact_sha256"],
                "discovery_qc_sid_mapping_artifact_id": discovery_binding[
                    "qc_sid_mapping_source"
                ]["artifact_id"],
                "discovery_qc_sid_mapping_artifact_sha256": discovery_binding[
                    "qc_sid_mapping_source"
                ]["artifact_sha256"],
                "firm_review_candidate_sha256": firm.content_sha256,
                "quality_policy_sha256": quality.content_sha256,
                "security_master_artifact_id": security_master_id,
                "security_master_artifact_sha256": security_master_sha,
                "closed_input_manifest_sha256": manifest_hash,
                "closed_input_manifest_byte_count": len(manifest_bytes),
                "input_shard_inventory_sha256": manifest[
                    "input_source_inventory_sha256"
                ],
                "input_shard_count": len(descriptors),
                "analyst_event_binding_inventory_sha256": analyst_inventory,
                "analyst_event_binding_shard_count": analyst_shards,
                "analyst_event_binding_row_count": analyst_rows,
                "universe_lifecycle_binding_inventory_sha256": lifecycle_inventory,
                "universe_lifecycle_binding_shard_count": lifecycle_shards,
                "universe_lifecycle_binding_row_count": lifecycle_rows,
                "first_session": discovery.first_session,
                "last_session": discovery.last_session,
                "security_count": identity_count,
                "accepted_security_count": accepted_count,
                "named_refusal_security_count": identity_count - accepted_count,
                "universe_terminal_count": eligible_terminal_count,
                "accepted_universe_terminal_count": accepted_universe,
                "named_refusal_universe_terminal_count": (
                    eligible_terminal_count - accepted_universe
                ),
                "current_ticker_match_count": accepted_count - mismatch_count,
                "current_ticker_mismatch_count": mismatch_count,
                "excluded_control_seed_row_count": excluded_seed_rows,
                "six_preopen_roles_produced": True,
                "exact_qc_sid_prebound": True,
                "current_ticker_used_as_identity": False,
                "full_pit_universe_established_within_qc_source_scope": True,
                "firm_ontology_human_reviewed": False,
                "data_quality_human_reviewed": False,
                "target_qc_capacity_human_reviewed": False,
                "production_preopen_input_available": False,
                "provider_or_credential_access_performed": False,
                "quantconnect_access_performed": False,
                "price_or_outcome_or_result_access_performed": False,
                "order_or_trading_access_performed": False,
            }
            try:
                _discovery.require_reviewed_fundamental_universe_discovery_receipt(
                    discovery
                )
                _seed.require_physical_preopen_seed_archive(seed)
            except Exception as exc:
                raise PhysicalHistoricalPreopenBridgeError(
                    "historical bridge parent changed during construction"
                ) from exc
            try:
                _publish_stage(root, final_root)
            except PhysicalHistoricalPreopenBridgePublicationAmbiguityError:
                preserve_stage = True
                raise
            published = True
            root = final_root
            try:
                shard_dir = root / _legacy.ARCHIVE_SHARD_DIRECTORY
                evidence_dir = root / _legacy.ARCHIVE_EVIDENCE_DIRECTORY
                root_stat = _legacy._stat(root, directory=True)
                shard_stat = _legacy._stat(shard_dir, directory=True)
                evidence_stat = _legacy._stat(evidence_dir, directory=True)
                return _mint(
                    record=record,
                    archive_root=root,
                    root_stat=root_stat,
                    shard_stat=shard_stat,
                    evidence_stat=evidence_stat,
                    bindings=bindings,
                    manifest_bytes=manifest_bytes,
                )
            except Exception:
                try:
                    _rollback_published_stage(stage_root, final_root)
                except PhysicalHistoricalPreopenBridgePublicationAmbiguityError:
                    preserve_stage = True
                    raise
                published = False
                raise
        finally:
            connection.close()
            if (
                stage_root is not None
                and not published
                and not preserve_stage
                and stage_root.exists()
            ):
                shutil.rmtree(stage_root)


__all__ = [
    "MAX_PHYSICAL_HISTORICAL_SPOOL_BYTES",
    "PhysicalHistoricalPreopenBridgeCapacityError",
    "PhysicalHistoricalPreopenBridgeError",
    "PhysicalHistoricalPreopenBridgePublicationAmbiguityError",
    "build_reviewed_historical_universe_to_preopen_bridge_from_physical_seed",
]
