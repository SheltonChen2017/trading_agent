"""Bounded process-local replay authority for accepted-risk pre-open terminals.

This module is intentionally not a reviewed physical archive.  It accepts the
owner-approved, non-PIT QuantConnect symbol resolution and validates exact
terminal rows emitted inside the same QC process.  It retains only the smaller
scorer replay projection plus content commitments; full terminal wrappers are
not persisted.  Rows may arrive batch-major; sealing sorts one session at a
time by ``(decision_session, security_id)``, derives the logical commitment,
and permits repeatable local replay without an Object Store or host export.
"""
import dataclasses
import hashlib
import hmac
import json
import os
import re
import sqlite3
import tempfile
import threading
import weakref
import zlib
from collections.abc import Iterator, Mapping, Sequence
from enum import Enum
from pathlib import Path
from types import MappingProxyType

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import preopen_terminal_semantics as _semantics
from research.analyst_revisions_v2_qc.accepted_risk_qc_symbol_resolution import (
    AcceptedRiskQcSymbolResolution,
    require_accepted_risk_qc_symbol_resolution,
)
from research.analyst_revisions_v2_qc.in_qc_preopen_terminal_stream import (
    InQcPreopenTerminalStreamReceipt,
    require_in_qc_preopen_terminal_stream_receipt,
)


RECORDER_SCHEMA = "arv2-owner-accepted-risk-preopen-terminal-recorder-v1"
AUTHORITY_SCHEMA = "arv2-owner-accepted-risk-preopen-terminal-authority-v1"
DIRECT_SUMMARY_SCHEMA = "arv2-owner-accepted-risk-direct-preopen-emission-summary-v1"
OWNER_RISK_DECISION = (
    "accept_same_process_current_snapshot_QC_resolution_for_preliminary_backtest_"
    "without_claiming_reviewed_lifecycle_or_point_in_time_security_master"
)
MAX_TERMINAL_COUNT = 25_000_000
MAX_TERMINAL_BYTES = 128 * 1024
MAX_SPOOL_BYTES = 16 * 1024 * 1024 * 1024
MAX_PENDING_TERMINALS = 4_096
GROUP_COMMIT_INTERVAL = 128
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class AcceptedRiskPreopenTerminalRefusalReason(str, Enum):
    AUTHORITY_CHANGED = "accepted_risk_preopen_authority_changed"
    TERMINAL_SCHEMA_INVALID = "accepted_risk_preopen_terminal_schema_invalid"
    TERMINAL_HASH_CHANGED = "accepted_risk_preopen_terminal_hash_changed"
    TERMINAL_DUPLICATE = "accepted_risk_preopen_terminal_duplicate"
    SESSION_OUTSIDE_AXIS = "accepted_risk_preopen_session_outside_axis"
    SECURITY_OUTSIDE_RESOLUTION = "accepted_risk_preopen_security_outside_resolution"
    QC_SID_MISMATCH = "accepted_risk_preopen_qc_sid_mismatch"
    DISPOSITION_CONFLICTS_RESOLUTION = (
        "accepted_risk_preopen_disposition_conflicts_resolution"
    )
    STREAM_BINDING_CHANGED = "accepted_risk_preopen_stream_binding_changed"
    CENSUS_CHANGED = "accepted_risk_preopen_census_changed"
    STORAGE_CHANGED = "accepted_risk_preopen_storage_changed"
    CAPACITY_EXCEEDED = "accepted_risk_preopen_capacity_exceeded"


class AcceptedRiskPreopenTerminalError(ValueError):
    """One distinct fail-closed refusal from the accepted-risk spool."""

    def __init__(
        self, reason: AcceptedRiskPreopenTerminalRefusalReason, message: str
    ) -> None:
        self.reason = reason
        super().__init__(f"{reason.value}: {message}")


def _refuse(reason: AcceptedRiskPreopenTerminalRefusalReason, message: str) -> None:
    raise AcceptedRiskPreopenTerminalError(reason, message)


def _sha(value: object) -> bool:
    return type(value) is str and _HEX.fullmatch(value) is not None


def _session(value: object) -> str | None:
    if type(value) is not str:
        return None
    try:
        from datetime import date

        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return value if parsed.isoformat() == value else None


def _terminal_geometry_capacity(*, session_count: int, security_count: int) -> int:
    if (
        type(session_count) is not int
        or type(security_count) is not int
        or session_count < 1
        or security_count < 1
    ):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.CAPACITY_EXCEEDED,
            "terminal session/security geometry changed type or sign",
        )
    capacity = session_count * security_count
    if capacity > MAX_TERMINAL_COUNT:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.CAPACITY_EXCEEDED,
            "session-by-admitted-security terminal geometry exceeds the fixed ceiling",
        )
    return capacity


def _chain_seed() -> str:
    return hashlib.sha256(
        canonical_json_bytes({"domain": "arv2-in-qc-preopen-terminal-chain-v1"})
    ).hexdigest()


def _merkle(records: list[dict[str, object]]) -> str:
    """Match the physical terminal Merkle commitment without host imports."""

    if not records:
        return hashlib.sha256(
            canonical_json_bytes({"domain": "arv2-empty-terminal-set-v1"})
        ).hexdigest()
    level = [
        hashlib.sha256(
            canonical_json_bytes(
                {"domain": "arv2-terminal-leaf-v1", "record": row}
            )
        ).hexdigest()
        for row in records
    ]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(
                canonical_json_bytes(
                    {
                        "domain": "arv2-terminal-node-v1",
                        "left": level[index],
                        "right": level[index + 1],
                    }
                )
            ).hexdigest()
            for index in range(0, len(level), 2)
        ]
    return level[0]


def _merkle_from_leaf_hashes(level: list[str]) -> str:
    if not level:
        return hashlib.sha256(
            canonical_json_bytes({"domain": "arv2-empty-terminal-set-v1"})
        ).hexdigest()
    level = list(level)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(
                canonical_json_bytes(
                    {
                        "domain": "arv2-terminal-node-v1",
                        "left": level[index],
                        "right": level[index + 1],
                    }
                )
            ).hexdigest()
            for index in range(0, len(level), 2)
        ]
    return level[0]


def _chain_add(previous: str, row: dict[str, object]) -> str:
    return _chain_add_record_sha(
        previous, hashlib.sha256(canonical_json_bytes(row)).hexdigest()
    )


def _chain_add_record_sha(previous: str, record_sha256: str) -> str:
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "domain": "arv2-in-qc-preopen-terminal-chain-node-v1",
                "previous_sha256": previous,
                "record_sha256": record_sha256,
            }
        )
    ).hexdigest()


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class OwnerAcceptedRiskPreopenTerminalRecorder:
    schema: str
    symbol_resolution: AcceptedRiskQcSymbolResolution = dataclasses.field(repr=False)
    symbol_resolution_sha256: str
    decision_sessions: tuple[str, ...]
    decision_session_axis_sha256: str
    maximum_terminal_count: int
    owner_risk_decision: str
    point_in_time: bool
    independently_reviewed: bool
    historical_availability_claimed: bool

    def __call__(self, row: dict[str, object]) -> None:
        record_owner_accepted_risk_preopen_terminal(self, row)

    def consume_terminal(self, row: dict[str, object]) -> None:
        record_owner_accepted_risk_preopen_terminal(self, row)

    def consume_terminal_batch(self, rows: Sequence[dict[str, object]]) -> None:
        record_owner_accepted_risk_preopen_terminal_batch(self, rows)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class OwnerAcceptedRiskPreopenTerminalAuthority:
    schema: str
    authority_id: str
    authority_sha256: str
    symbol_resolution_sha256: str
    source_stream_binding_sha256: str
    decision_session_axis_sha256: str
    decision_sessions: tuple[str, ...]
    maximum_terminal_count: int
    terminal_count: int
    accepted_terminal_count: int
    named_refusal_terminal_count: int
    logical_terminal_chain_sha256: str
    replay_passes_completed: int
    owner_risk_decision: str
    point_in_time: bool
    independently_reviewed: bool
    historical_availability_claimed: bool
    owner_accepted_current_snapshot_risk: bool
    host_object_store_export_performed: bool
    raw_terminal_rows_spooled_process_locally: bool
    terminal_replay_projections_spooled_process_locally: bool
    formal_lifecycle_authority: bool
    production_authority: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


@dataclasses.dataclass
class _RecorderState:
    reference: weakref.ReferenceType[OwnerAcceptedRiskPreopenTerminalRecorder]
    connection: sqlite3.Connection
    temporary: tempfile.TemporaryDirectory[str]
    path: Path
    pid: int
    status: str
    symbol_resolution: AcceptedRiskQcSymbolResolution
    symbol_resolution_sha256: str
    decision_sessions: tuple[str, ...]
    decision_session_axis_sha256: str
    decision_session_set: frozenset[str]
    resolved_by_security: Mapping[str, str]
    refused_security: frozenset[str]
    maximum_terminal_count: int
    spool_authentication_key: bytes
    session_counts: dict[str, int]
    pending: list[list[object]] = dataclasses.field(default_factory=list)
    group_ordinal: int = 0
    uncommitted_group_count: int = 0
    compressed_payload_bytes: int = 0
    count: int = 0
    last_ingested_key: tuple[str, str] | None = None


@dataclasses.dataclass
class _AuthorityState:
    reference: weakref.ReferenceType[OwnerAcceptedRiskPreopenTerminalAuthority]
    temporary: tempfile.TemporaryDirectory[str]
    path: Path
    path_identity: tuple[int, int, int, int]
    spool_sha256: str
    symbol_resolution: AcceptedRiskQcSymbolResolution
    session_commitments: tuple[tuple[object, ...], ...]
    spool_authentication_key: bytes
    pid: int
    replay_passes: int = 0


_RECORDERS: dict[int, _RecorderState] = {}
_AUTHORITIES: dict[int, _AuthorityState] = {}
_LOCK = threading.RLock()


def _path_identity(path: Path) -> tuple[int, int, int, int]:
    try:
        stat = path.lstat()
    except OSError:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
            "process-local terminal spool is unavailable",
        )
    if not path.is_file() or path.is_symlink():
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
            "process-local terminal spool is not a regular file",
        )
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _file_sha(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
    except OSError:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
            "process-local terminal spool cannot be authenticated",
        )
    return hasher.hexdigest()


def _forget_recorder(identity: int, reference: object) -> None:
    with _LOCK:
        state = _RECORDERS.get(identity)
        if state is not None and state.reference is reference:
            try:
                state.connection.close()
            finally:
                state.temporary.cleanup()
                _RECORDERS.pop(identity, None)


def _forget_authority(identity: int, reference: object) -> None:
    with _LOCK:
        state = _AUTHORITIES.get(identity)
        if state is not None and state.reference is reference:
            state.temporary.cleanup()
            _AUTHORITIES.pop(identity, None)


def begin_owner_accepted_risk_preopen_terminal_recording(
    *,
    symbol_resolution: AcceptedRiskQcSymbolResolution,
    decision_sessions: Sequence[str],
) -> OwnerAcceptedRiskPreopenTerminalRecorder:
    """Open a private compressed projection spool; no terminal leaves this process."""

    try:
        resolution = require_accepted_risk_qc_symbol_resolution(symbol_resolution)
    except Exception as exc:
        raise AcceptedRiskPreopenTerminalError(
            AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
            "accepted-risk QC symbol resolution did not authenticate",
        ) from exc
    if type(decision_sessions) not in (tuple, list):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
            "decision-session axis is not an exact sequence",
        )
    axis = tuple(decision_sessions)
    if (
        not axis
        or any(_session(item) is None for item in axis)
        or axis != tuple(sorted(set(axis)))
    ):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
            "decision-session axis is empty, repeated, reordered, or invalid",
        )
    maximum_terminal_count = _terminal_geometry_capacity(
        session_count=len(axis), security_count=resolution.input_row_count
    )
    resolved_by_security = {
        str(item["security_id"]): str(item["qc_security_id"])
        for item in resolution.resolved
    }
    refused_security = frozenset(
        str(item["security_id"]) for item in resolution.named_refusals
    )
    if (
        len(resolved_by_security) != resolution.resolved_count
        or len(refused_security) != resolution.named_refusal_count
        or set(resolved_by_security).intersection(refused_security)
        or len(resolved_by_security) + len(refused_security)
        != resolution.input_row_count
    ):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
            "accepted-risk QC symbol resolution census changed",
        )
    axis_sha = hashlib.sha256(canonical_json_bytes(list(axis))).hexdigest()
    temporary = tempfile.TemporaryDirectory(prefix="arv2-preopen-terminal-spool-")
    root = Path(temporary.name)
    if os.name != "nt":
        os.chmod(root, 0o700)
    path = root / "terminals.sqlite3"
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE terminal_group (session TEXT NOT NULL, "
            "group_ordinal INTEGER NOT NULL, record_count INTEGER NOT NULL, "
            "encoded_bytes INTEGER NOT NULL, payload BLOB NOT NULL, "
            "PRIMARY KEY(session, group_ordinal)) WITHOUT ROWID"
        )
        connection.execute("BEGIN IMMEDIATE")
    except Exception:
        connection.close()
        temporary.cleanup()
        raise
    recorder = OwnerAcceptedRiskPreopenTerminalRecorder(
        schema=RECORDER_SCHEMA,
        symbol_resolution=resolution,
        symbol_resolution_sha256=resolution.resolution_sha256,
        decision_sessions=axis,
        decision_session_axis_sha256=axis_sha,
        maximum_terminal_count=maximum_terminal_count,
        owner_risk_decision=OWNER_RISK_DECISION,
        point_in_time=False,
        independently_reviewed=False,
        historical_availability_claimed=False,
    )
    identity = id(recorder)
    reference = weakref.ref(
        recorder, lambda ref, key=identity: _forget_recorder(key, ref)
    )
    with _LOCK:
        _RECORDERS[identity] = _RecorderState(
            reference=reference,
            connection=connection,
            temporary=temporary,
            path=path,
            pid=os.getpid(),
            status="recording",
            symbol_resolution=resolution,
            symbol_resolution_sha256=resolution.resolution_sha256,
            decision_sessions=axis,
            decision_session_axis_sha256=axis_sha,
            decision_session_set=frozenset(axis),
            resolved_by_security=MappingProxyType(resolved_by_security),
            refused_security=refused_security,
            maximum_terminal_count=maximum_terminal_count,
            spool_authentication_key=os.urandom(32),
            session_counts={item: 0 for item in axis},
        )
    return recorder


def _require_recorder(
    value: OwnerAcceptedRiskPreopenTerminalRecorder,
    *,
    deep: bool = False,
) -> tuple[OwnerAcceptedRiskPreopenTerminalRecorder, _RecorderState]:
    if type(value) is not OwnerAcceptedRiskPreopenTerminalRecorder:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
            "terminal recorder changed type",
        )
    with _LOCK:
        state = _RECORDERS.get(id(value))
    if (
        state is None
        or state.reference() is not value
        or state.pid != os.getpid()
        or state.status != "recording"
        or value.schema != RECORDER_SCHEMA
        or value.owner_risk_decision != OWNER_RISK_DECISION
        or value.point_in_time is not False
        or value.independently_reviewed is not False
        or value.historical_availability_claimed is not False
        or value.symbol_resolution is not state.symbol_resolution
        or value.symbol_resolution_sha256 != state.symbol_resolution_sha256
        or value.decision_sessions is not state.decision_sessions
        or value.decision_session_axis_sha256
        != state.decision_session_axis_sha256
        or value.maximum_terminal_count != state.maximum_terminal_count
    ):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
            "terminal recorder is not current process authority",
        )
    if deep or state.count % 65_536 == 0:
        try:
            resolution = require_accepted_risk_qc_symbol_resolution(
                value.symbol_resolution
            )
        except Exception as exc:
            raise AcceptedRiskPreopenTerminalError(
                AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
                "accepted-risk symbol resolution changed during recording",
            ) from exc
        if (
            resolution.resolution_sha256 != value.symbol_resolution_sha256
            or {
                str(item["security_id"]): str(item["qc_security_id"])
                for item in resolution.resolved
            }
            != state.resolved_by_security
            or frozenset(
                str(item["security_id"])
                for item in resolution.named_refusals
            )
            != state.refused_security
        ):
            _refuse(
                AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
                "accepted-risk symbol resolution binding changed",
            )
    return value, state


def record_owner_accepted_risk_preopen_terminal(
    recorder: OwnerAcceptedRiskPreopenTerminalRecorder,
    row: dict[str, object],
) -> None:
    """Validate and buffer one exact row; arrival order is intentionally free."""

    with _LOCK:
        _value, state = _require_recorder(recorder)
        _append_terminal(state, row)


def record_owner_accepted_risk_preopen_terminal_batch(
    recorder: OwnerAcceptedRiskPreopenTerminalRecorder,
    rows: Sequence[dict[str, object]],
) -> None:
    """Authenticate once and spool one bounded direct-runtime decision chunk."""

    if type(rows) not in (list, tuple) or not rows:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_SCHEMA_INVALID,
            "terminal batch is not a nonempty exact sequence",
        )
    with _LOCK:
        _value, state = _require_recorder(recorder)
        for row in rows:
            _append_terminal(state, row)
        _flush_pending(state)


def _compact_terminal(
    state: _RecorderState, row: object
) -> list[object]:
    if type(row) is not dict:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_SCHEMA_INVALID,
            "terminal is not an exact object",
        )
    copied = dict(row)
    if set(copied) != set(_semantics.TERMINAL_FIELDS):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_SCHEMA_INVALID,
            "terminal fields changed",
        )
    semantic = dict(copied)
    declared = semantic.pop("terminal_sha256", None)
    if not _sha(declared) or hashlib.sha256(
        canonical_json_bytes(semantic)
    ).hexdigest() != declared:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_HASH_CHANGED,
            "terminal content hash changed",
        )
    try:
        copied = _semantics.validate_preopen_terminal_semantics(copied)
    except Exception as exc:
        raise AcceptedRiskPreopenTerminalError(
            AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_SCHEMA_INVALID,
            "terminal semantic schema did not authenticate",
        ) from exc
    session = str(copied["decision_session"])
    security_id = str(copied["security_id"])
    if session not in state.decision_session_set:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.SESSION_OUTSIDE_AXIS,
            "terminal escaped the exact decision-session axis",
        )
    if (
        security_id not in state.resolved_by_security
        and security_id not in state.refused_security
    ):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.SECURITY_OUTSIDE_RESOLUTION,
            "terminal escaped accepted-risk symbol resolution",
        )
    if copied["disposition"] == "accepted":
        if security_id not in state.resolved_by_security:
            _refuse(
                AcceptedRiskPreopenTerminalRefusalReason.DISPOSITION_CONFLICTS_RESOLUTION,
                "runtime-unresolved security appeared accepted",
            )
        if copied["qc_security_id"] != state.resolved_by_security[security_id]:
            _refuse(
                AcceptedRiskPreopenTerminalRefusalReason.QC_SID_MISMATCH,
                "accepted terminal QC SID differs from runtime resolution",
            )
        value = copied["eligible_security_session"]
    else:
        if (
            security_id in state.refused_security
            and copied["qc_security_id"] is not None
        ):
            _refuse(
                AcceptedRiskPreopenTerminalRefusalReason.QC_SID_MISMATCH,
                "runtime-unresolved refusal unexpectedly carries a QC SID",
            )
        value = copied["census_refusal"]
    payload = canonical_json_bytes(copied)
    if len(payload) > MAX_TERMINAL_BYTES:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.CAPACITY_EXCEEDED,
            "one terminal exceeds the byte ceiling",
        )
    universe_row = {
        "terminal": (
            "accepted" if copied["disposition"] == "accepted" else "refused"
        ),
        "value": value,
    }
    compact: list[object] = [
        session,
        security_id,
        copied["disposition"],
        len(payload),
        hashlib.sha256(payload).hexdigest(),
        hashlib.sha256(
            canonical_json_bytes(
                {"domain": "arv2-terminal-leaf-v1", "record": copied}
            )
        ).hexdigest(),
        hashlib.sha256(
            canonical_json_bytes(
                {"domain": "arv2-terminal-leaf-v1", "record": universe_row}
            )
        ).hexdigest(),
        value,
    ]
    compact.append(
        hmac.new(
            state.spool_authentication_key,
            canonical_json_bytes(compact),
            hashlib.sha256,
        ).hexdigest()
    )
    return compact


def _append_terminal(state: _RecorderState, row: object) -> None:
    compact = _compact_terminal(state, row)
    if state.count >= state.maximum_terminal_count:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_DUPLICATE,
            "terminal census exceeds its unique admitted session/security geometry",
        )
    session = str(compact[0])
    key = (session, str(compact[1]))
    if key == state.last_ingested_key:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_DUPLICATE,
            "terminal session/security key repeated consecutively",
        )
    if state.session_counts[session] >= len(
        state.resolved_by_security
    ) + len(state.refused_security):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_DUPLICATE,
            "one session exceeds its unique admitted security census",
        )
    state.pending.append(compact)
    state.count += 1
    state.session_counts[session] += 1
    state.last_ingested_key = key
    if len(state.pending) >= MAX_PENDING_TERMINALS:
        _flush_pending(state)


def _flush_pending(state: _RecorderState) -> None:
    if not state.pending:
        return
    groups: dict[str, list[list[object]]] = {}
    for record in state.pending:
        groups.setdefault(str(record[0]), []).append(record)
    try:
        for session in sorted(groups):
            records = groups[session]
            payload = b"".join(canonical_json_bytes(item) for item in records)
            compressed = zlib.compress(payload, level=6)
            if state.compressed_payload_bytes + len(compressed) > MAX_SPOOL_BYTES:
                _refuse(
                    AcceptedRiskPreopenTerminalRefusalReason.CAPACITY_EXCEEDED,
                    "compressed terminal projection spool exceeds the byte ceiling",
                )
            state.connection.execute(
                "INSERT INTO terminal_group(session,group_ordinal,record_count,"
                "encoded_bytes,payload) VALUES (?,?,?,?,?)",
                (
                    session,
                    state.group_ordinal,
                    len(records),
                    len(payload),
                    compressed,
                ),
            )
            state.compressed_payload_bytes += len(compressed)
            state.uncommitted_group_count += 1
        state.group_ordinal += 1
        state.pending.clear()
        if state.uncommitted_group_count >= GROUP_COMMIT_INTERVAL:
            state.connection.commit()
            state.connection.execute("BEGIN IMMEDIATE")
            state.uncommitted_group_count = 0
    except AcceptedRiskPreopenTerminalError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise AcceptedRiskPreopenTerminalError(
            AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
            "terminal projection spool write failed",
        ) from exc


def _session_compact_records(
    connection: sqlite3.Connection,
    session: str,
    *,
    authentication_key: bytes,
    maximum_session_count: int,
) -> list[list[object]]:
    records: list[list[object]] = []
    try:
        groups = connection.execute(
            "SELECT record_count,encoded_bytes,payload FROM terminal_group "
            "WHERE session=? ORDER BY group_ordinal",
            (session,),
        )
        for record_count, encoded_bytes, compressed in groups:
            payload = zlib.decompress(bytes(compressed))
            if (
                type(record_count) is not int
                or record_count < 1
                or type(encoded_bytes) is not int
                or encoded_bytes < 1
                or len(payload) != encoded_bytes
                or encoded_bytes
                > MAX_PENDING_TERMINALS * (MAX_TERMINAL_BYTES + 1_024)
            ):
                _refuse(
                    AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
                    "terminal projection group census changed",
                )
            lines = payload.splitlines(keepends=True)
            if len(lines) != record_count:
                _refuse(
                    AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
                    "terminal projection group row count changed",
                )
            for line in lines:
                value = json.loads(line.decode("utf-8"))
                if (
                    type(value) is not list
                    or len(value) != 9
                    or canonical_json_bytes(value) != line
                    or value[0] != session
                    or type(value[1]) is not str
                    or not value[1]
                    or value[2] not in {"accepted", "named_refusal"}
                    or type(value[3]) is not int
                    or not 0 < value[3] <= MAX_TERMINAL_BYTES
                    or any(not _sha(value[index]) for index in (4, 5, 6, 8))
                    or type(value[7]) is not dict
                    or not hmac.compare_digest(
                        value[8],
                        hmac.new(
                            authentication_key,
                            canonical_json_bytes(value[:8]),
                            hashlib.sha256,
                        ).hexdigest(),
                    )
                ):
                    _refuse(
                        AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
                        "terminal replay projection changed",
                    )
                records.append(value)
                if len(records) > maximum_session_count:
                    _refuse(
                        AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_DUPLICATE,
                        "one replay session exceeds its unique admitted security census",
                    )
    except AcceptedRiskPreopenTerminalError:
        raise
    except Exception as exc:
        raise AcceptedRiskPreopenTerminalError(
            AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
            "compressed terminal projection group cannot be decoded",
        ) from exc
    records.sort(key=lambda item: str(item[1]))
    if any(
        records[index - 1][1] == records[index][1]
        for index in range(1, len(records))
    ):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.TERMINAL_DUPLICATE,
            "terminal session/security key repeated",
        )
    return records


def _derive(
    connection: sqlite3.Connection,
    decision_sessions: tuple[str, ...],
    *,
    authentication_key: bytes,
    maximum_session_count: int,
) -> tuple[int, int, int, str, tuple[tuple[object, ...], ...]]:
    """Derive global commitments while retaining at most one session's hashes."""

    count = accepted = refused = 0
    chain = _chain_seed()
    commitments: list[tuple[object, ...]] = []
    for session in decision_sessions:
        rows = _session_compact_records(
            connection,
            session,
            authentication_key=authentication_key,
            maximum_session_count=maximum_session_count,
        )
        accepted_rows = sum(item[2] == "accepted" for item in rows)
        refused_rows = len(rows) - accepted_rows
        for item in rows:
            chain = _chain_add_record_sha(chain, str(item[4]))
        count += len(rows)
        accepted += accepted_rows
        refused += refused_rows
        commitments.append(
            (
                session,
                accepted_rows,
                refused_rows,
                len(rows),
                _merkle_from_leaf_hashes([str(item[5]) for item in rows]),
                _merkle_from_leaf_hashes([str(item[6]) for item in rows]),
                sum(int(item[3]) for item in rows),
            )
        )
        del rows
    return count, accepted, refused, chain, tuple(commitments)


def _direct_summary_record(value: object) -> dict[str, object]:
    if hasattr(value, "to_record") and callable(value.to_record):
        value = value.to_record()
    if type(value) is not dict:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.STREAM_BINDING_CHANGED,
            "direct emission summary is not an exact record",
        )
    record = dict(value)
    fields = {
        "schema",
        "summary_id",
        "summary_sha256",
        "source_input_manifest_sha256",
        "symbol_resolution_sha256",
        "terminal_emission_count",
        "peer_aggregate_projection_sha256",
        "market_session_projection_sha256",
        "emission_order",
        "object_store_terminal_writes",
        "preliminary_evaluation_only",
        "formal_security_master_authority",
        "frozen_formal_evaluation_completed",
    }
    if (
        set(record) != fields
        or record["schema"] != DIRECT_SUMMARY_SCHEMA
        or type(record["terminal_emission_count"]) is not int
        or record["terminal_emission_count"] < 0
        or record["emission_order"]
        != "security_batch_then_decision_chunk_then_decision_session_then_security_id"
        or record["object_store_terminal_writes"] != 0
        or record["preliminary_evaluation_only"] is not True
        or record["formal_security_master_authority"] is not False
        or record["frozen_formal_evaluation_completed"] is not False
        or any(
            not _sha(record[name])
            for name in (
                "summary_sha256",
                "source_input_manifest_sha256",
                "symbol_resolution_sha256",
                "peer_aggregate_projection_sha256",
                "market_session_projection_sha256",
            )
        )
    ):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.STREAM_BINDING_CHANGED,
            "direct emission summary gates or census changed",
        )
    semantic = dict(record)
    declared_id = semantic["summary_id"]
    declared_sha = semantic["summary_sha256"]
    semantic["summary_id"] = None
    semantic["summary_sha256"] = None
    digest = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    if (
        declared_sha != digest
        or declared_id != "arv2-direct-preopen-emission-" + digest[:24]
    ):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.STREAM_BINDING_CHANGED,
            "direct emission summary content address changed",
        )
    return record


def finalize_owner_accepted_risk_preopen_terminal_recording(
    *,
    recorder: OwnerAcceptedRiskPreopenTerminalRecorder,
    stream_receipt: InQcPreopenTerminalStreamReceipt | None = None,
    direct_emission_summary: object | None = None,
) -> OwnerAcceptedRiskPreopenTerminalAuthority:
    """Seal the spool against exactly one cloud-local stream binding."""

    if (stream_receipt is None) == (direct_emission_summary is None):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.STREAM_BINDING_CHANGED,
            "exactly one stream receipt or direct-emission summary is required",
        )
    with _LOCK:
        value, state = _require_recorder(recorder, deep=True)
        state.status = "finalizing"
        try:
            _flush_pending(state)
            state.connection.commit()
            count, accepted, refused, chain, commitments = _derive(
                state.connection,
                value.decision_sessions,
                authentication_key=state.spool_authentication_key,
                maximum_session_count=(
                    len(state.resolved_by_security) + len(state.refused_security)
                ),
            )
        except AcceptedRiskPreopenTerminalError:
            raise
        except Exception as exc:
            raise AcceptedRiskPreopenTerminalError(
                AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
                "terminal spool cannot be sealed",
            ) from exc
        if count != state.count or count != sum(state.session_counts.values()):
            _refuse(
                AcceptedRiskPreopenTerminalRefusalReason.CENSUS_CHANGED,
                "sealed terminal projection census differs from ingestion",
            )
        if stream_receipt is not None:
            try:
                receipt = require_in_qc_preopen_terminal_stream_receipt(
                    stream_receipt
                )
            except Exception as exc:
                raise AcceptedRiskPreopenTerminalError(
                    AcceptedRiskPreopenTerminalRefusalReason.STREAM_BINDING_CHANGED,
                    "cloud-local terminal receipt did not authenticate",
                ) from exc
            if receipt.symbol_resolution_sha256 != value.symbol_resolution_sha256:
                _refuse(
                    AcceptedRiskPreopenTerminalRefusalReason.STREAM_BINDING_CHANGED,
                    "stream receipt symbol resolution changed",
                )
            if (
                (count, accepted, refused, chain)
                != (
                    receipt.terminal_count,
                    receipt.accepted_terminal_count,
                    receipt.named_refusal_terminal_count,
                    receipt.logical_terminal_chain_sha256,
                )
            ):
                _refuse(
                    AcceptedRiskPreopenTerminalRefusalReason.CENSUS_CHANGED,
                    "ordered spool census or chain differs from stream receipt",
                )
            source_binding = receipt.receipt_sha256
        else:
            summary = _direct_summary_record(direct_emission_summary)
            if (
                summary["symbol_resolution_sha256"]
                != value.symbol_resolution_sha256
            ):
                _refuse(
                    AcceptedRiskPreopenTerminalRefusalReason.STREAM_BINDING_CHANGED,
                    "direct-emission symbol resolution changed",
                )
            if summary["terminal_emission_count"] != count:
                _refuse(
                    AcceptedRiskPreopenTerminalRefusalReason.CENSUS_CHANGED,
                    "direct-emission count differs from ordered spool census",
                )
            source_binding = hashlib.sha256(
                canonical_json_bytes(summary)
            ).hexdigest()
        try:
            state.connection.close()
        except sqlite3.Error as exc:
            raise AcceptedRiskPreopenTerminalError(
                AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
                "terminal spool could not be made immutable",
            ) from exc
        if state.path.stat().st_size > MAX_SPOOL_BYTES:
            _refuse(
                AcceptedRiskPreopenTerminalRefusalReason.CAPACITY_EXCEEDED,
                "sealed terminal spool exceeds the byte ceiling",
            )
        path_identity = _path_identity(state.path)
        spool_sha = _file_sha(state.path)
        semantic = {
            "schema": AUTHORITY_SCHEMA,
            "symbol_resolution_sha256": value.symbol_resolution_sha256,
            "source_stream_binding_sha256": source_binding,
            "decision_session_axis_sha256": value.decision_session_axis_sha256,
            "decision_sessions": list(value.decision_sessions),
            "maximum_terminal_count": value.maximum_terminal_count,
            "terminal_count": count,
            "accepted_terminal_count": accepted,
            "named_refusal_terminal_count": refused,
            "logical_terminal_chain_sha256": chain,
            "owner_risk_decision": OWNER_RISK_DECISION,
            "point_in_time": False,
            "independently_reviewed": False,
            "historical_availability_claimed": False,
            "owner_accepted_current_snapshot_risk": True,
            "host_object_store_export_performed": False,
            "raw_terminal_rows_spooled_process_locally": False,
            "terminal_replay_projections_spooled_process_locally": True,
            "formal_lifecycle_authority": False,
            "production_authority": False,
            "outcome_access": False,
            "result_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        }
        digest = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
        authority = OwnerAcceptedRiskPreopenTerminalAuthority(
            authority_id="arv2-owner-accepted-preopen-terminals-" + digest[:24],
            authority_sha256=digest,
            replay_passes_completed=0,
            **{**semantic, "decision_sessions": value.decision_sessions},
        )
        authority_identity = id(authority)
        authority_reference = weakref.ref(
            authority,
            lambda ref, key=authority_identity: _forget_authority(key, ref),
        )
        _AUTHORITIES[authority_identity] = _AuthorityState(
            reference=authority_reference,
            temporary=state.temporary,
            path=state.path,
            path_identity=path_identity,
            spool_sha256=spool_sha,
            symbol_resolution=value.symbol_resolution,
            session_commitments=commitments,
            spool_authentication_key=state.spool_authentication_key,
            pid=os.getpid(),
        )
        _RECORDERS.pop(id(value), None)
    return require_owner_accepted_risk_preopen_terminal_authority(authority)


def require_owner_accepted_risk_preopen_terminal_authority(
    value: OwnerAcceptedRiskPreopenTerminalAuthority,
) -> OwnerAcceptedRiskPreopenTerminalAuthority:
    if type(value) is not OwnerAcceptedRiskPreopenTerminalAuthority:
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
            "terminal authority changed type",
        )
    with _LOCK:
        state = _AUTHORITIES.get(id(value))
    if state is None or state.reference() is not value or state.pid != os.getpid():
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
            "terminal authority is not current process authority",
        )
    semantic = dataclasses.asdict(value)
    semantic.pop("authority_id")
    semantic.pop("authority_sha256")
    semantic.pop("replay_passes_completed")
    if (
        value.schema != AUTHORITY_SCHEMA
        or value.owner_risk_decision != OWNER_RISK_DECISION
        or value.replay_passes_completed != state.replay_passes
        or value.point_in_time is not False
        or value.independently_reviewed is not False
        or value.historical_availability_claimed is not False
        or value.owner_accepted_current_snapshot_risk is not True
        or value.host_object_store_export_performed is not False
        or value.raw_terminal_rows_spooled_process_locally is not False
        or value.terminal_replay_projections_spooled_process_locally is not True
        or value.formal_lifecycle_authority is not False
        or any(
            getattr(value, field) is not False
            for field in (
                "production_authority",
                "outcome_access",
                "result_access",
                "deployment",
                "orders",
                "trading",
            )
        )
        or hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
        != value.authority_sha256
        or value.authority_id
        != "arv2-owner-accepted-preopen-terminals-" + value.authority_sha256[:24]
    ):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
            "terminal authority public binding changed",
        )
    try:
        require_accepted_risk_qc_symbol_resolution(state.symbol_resolution)
    except Exception as exc:
        raise AcceptedRiskPreopenTerminalError(
            AcceptedRiskPreopenTerminalRefusalReason.AUTHORITY_CHANGED,
            "terminal authority symbol resolution changed",
        ) from exc
    if (
        _path_identity(state.path) != state.path_identity
        or _file_sha(state.path) != state.spool_sha256
    ):
        _refuse(
            AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
            "sealed terminal spool changed",
        )
    return value


def iter_owner_accepted_risk_preopen_terminal_sessions(
    value: OwnerAcceptedRiskPreopenTerminalAuthority,
) -> Iterator[object]:
    """Replay every declared session, including exact empty sessions."""

    # Lazy loading keeps the QC ingestion/authority path independent of the
    # host-heavy formal composer and also permits that composer to import this
    # authority later without a module-initialization cycle.
    from research.analyst_revisions_v2_qc.formal_streaming_input import (
        PhysicalTerminalSessionBlock,
        _eligible_from_record,
        _refusal_from_record,
    )

    authority = require_owner_accepted_risk_preopen_terminal_authority(value)
    with _LOCK:
        state = _AUTHORITIES[id(authority)]
        path = state.path
        commitments = state.session_commitments
        authentication_key = state.spool_authentication_key
        maximum_session_count = (
            state.symbol_resolution.input_row_count
        )
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for commitment in commitments:
            session = str(commitment[0])
            rows = _session_compact_records(
                connection,
                session,
                authentication_key=authentication_key,
                maximum_session_count=maximum_session_count,
            )
            accepted = tuple(
                _eligible_from_record(item[7])
                for item in rows
                if item[2] == "accepted"
            )
            refused = tuple(
                _refusal_from_record(item[7])
                for item in rows
                if item[2] == "named_refusal"
            )
            observed = (
                session,
                len(accepted),
                len(refused),
                len(rows),
                _merkle_from_leaf_hashes([str(item[5]) for item in rows]),
                _merkle_from_leaf_hashes([str(item[6]) for item in rows]),
                sum(int(item[3]) for item in rows),
            )
            if observed != commitment:
                _refuse(
                    AcceptedRiskPreopenTerminalRefusalReason.STORAGE_CHANGED,
                    "replayed session differs from sealed commitment",
                )
            yield PhysicalTerminalSessionBlock(
                decision_session=session,
                accepted=accepted,
                refused=refused,
                terminal_count=len(rows),
                control_terminal_merkle_root=str(commitment[4]),
                universe_terminal_merkle_root=str(commitment[5]),
                raw_byte_count=int(commitment[6]),
            )
    finally:
        connection.close()
    require_owner_accepted_risk_preopen_terminal_authority(authority)
    with _LOCK:
        state = _AUTHORITIES[id(authority)]
        state.replay_passes += 1
        object.__setattr__(authority, "replay_passes_completed", state.replay_passes)
    return


__all__ = (
    "AUTHORITY_SCHEMA",
    "DIRECT_SUMMARY_SCHEMA",
    "OWNER_RISK_DECISION",
    "RECORDER_SCHEMA",
    "AcceptedRiskPreopenTerminalError",
    "AcceptedRiskPreopenTerminalRefusalReason",
    "OwnerAcceptedRiskPreopenTerminalAuthority",
    "OwnerAcceptedRiskPreopenTerminalRecorder",
    "begin_owner_accepted_risk_preopen_terminal_recording",
    "finalize_owner_accepted_risk_preopen_terminal_recording",
    "iter_owner_accepted_risk_preopen_terminal_sessions",
    "record_owner_accepted_risk_preopen_terminal",
    "record_owner_accepted_risk_preopen_terminal_batch",
    "require_owner_accepted_risk_preopen_terminal_authority",
)
