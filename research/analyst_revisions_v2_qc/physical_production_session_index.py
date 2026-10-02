"""Disk/session index for owner-reviewed physical ARV2 C2 evidence.

Formal scoring consumes the C2 events by decision session while the physical
C2 archive is ordered by source lineage.  The legacy scorer solves that join
with retained dictionaries containing the complete normalized union and row
evidence.  This adapter performs the sort on bounded private SQLite storage,
then replays one session at a time.  Its production entry point accepts only
the owner-reviewed physical production-evidence receipt.

The index contains only pre-outcome C2 rows and their exact endpoint labels.
It grants no provider, outcome, QuantConnect, object-store, deployment, order,
or trading authority.  It is the direct input boundary for a later replacement
of ``formal_streaming_input._begin_streamed_production_scoring_impl``; the
legacy scorer itself is intentionally not weakened to accept it implicitly.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import sqlite3
import stat
import tempfile
import threading
import weakref
from bisect import bisect_left
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    decode_utf8,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2.production_input_pipeline import SignalArm
from research.analyst_revisions_v2.production_scoring import (
    build_endpoint_label_evidence,
)
from research.analyst_revisions_v2_qc import (
    physical_production_evidence_acquisition as _acquisition,
)
from research.analyst_revisions_v2_qc import (
    physical_production_evidence_bridge as _bridge,
)
from research.analyst_revisions_v2_qc import (
    physical_production_input_archive as _c2,
)
from research.analyst_revisions_v2_qc import formal_streaming_input as _streaming
from research.analyst_revisions_v2_qc.formal_run_protocol import (
    AcceptedRiskPairBinding,
    require_accepted_risk_pair_binding,
)
from research.analyst_revisions_v2_qc.physical_production_evidence_acquisition import (
    PhysicalProductionEvidenceAcquisitionReceipt,
)
from research.analyst_revisions_v2_qc.physical_production_evidence_bridge import (
    PhysicalProductionScoringRow,
)


INDEX_SCHEMA = "arv2-physical-production-session-index-v1"
SESSION_BLOCK_SCHEMA = "arv2-physical-production-session-block-v1"
MAX_INDEX_BYTES = 16 * 1024 * 1024 * 1024
MAX_INDEX_ROWS = 40_000_000
MAX_INDEX_SESSIONS = 10_000
MAX_SESSION_ROWS_PER_ARM = 2_000_000
MAX_SESSION_ROWS = 2_000_000
MAX_SESSION_PAYLOAD_BYTES = 128 * 1024 * 1024
MAX_INDEX_RECORD_BYTES = 16 * 1024 * 1024
INDEX_CAPACITY_CHECK_INTERVAL = 1_024
_ARM_ORDER = (
    SignalArm.CURRENT_VINTAGE,
    SignalArm.CONSERVATIVE_CENSORED,
)
_CREATE_ROWS_SQL = (
    "CREATE TABLE scoring_rows("
    "decision_session TEXT NOT NULL, arm_rank INTEGER NOT NULL, "
    "row_sha256 TEXT NOT NULL, payload BLOB NOT NULL, "
    "PRIMARY KEY(decision_session, arm_rank, row_sha256)) WITHOUT ROWID"
)
_CREATE_METADATA_SQL = (
    "CREATE TABLE metadata(key TEXT PRIMARY KEY, payload BLOB NOT NULL) "
    "WITHOUT ROWID"
)
_ORDERED_ROWS_SQL = (
    "SELECT decision_session, arm_rank, row_sha256, payload "
    "FROM scoring_rows ORDER BY decision_session, arm_rank, row_sha256"
)


class PhysicalProductionSessionIndexError(ValueError):
    """The physical scoring index or one session replay is invalid."""


class PhysicalProductionSessionIndexCapacityError(
    PhysicalProductionSessionIndexError
):
    """A fixed physical scoring-index capacity was exceeded."""


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalProductionSessionBlock:
    schema: str
    decision_session: str
    current_rows: tuple[PhysicalProductionScoringRow, ...]
    censored_rows: tuple[PhysicalProductionScoringRow, ...]
    current_row_count: int
    censored_row_count: int
    block_sha256: str

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "decision_session": self.decision_session,
            "current_row_sha256s": [
                item.normalized_evidence.normalized_row.row_sha256
                for item in self.current_rows
            ],
            "censored_row_sha256s": [
                item.normalized_evidence.normalized_row.row_sha256
                for item in self.censored_rows
            ],
            "current_row_count": self.current_row_count,
            "censored_row_count": self.censored_row_count,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalProductionScoringSessionInput:
    """One exact preopen terminal block joined to both physical C2 arms."""

    decision_session: str
    terminal_block: object
    current_event_rows: tuple[PhysicalProductionScoringRow, ...]
    censored_event_rows: tuple[PhysicalProductionScoringRow, ...]
    input_sha256: str

    def to_record(self) -> dict[str, object]:
        return {
            "decision_session": self.decision_session,
            "control_terminal_merkle_root": (
                self.terminal_block.control_terminal_merkle_root
            ),
            "universe_terminal_merkle_root": (
                self.terminal_block.universe_terminal_merkle_root
            ),
            "physical_terminal_count": self.terminal_block.terminal_count,
            "current_event_row_sha256s": [
                item.normalized_evidence.normalized_row.row_sha256
                for item in self.current_event_rows
            ],
            "censored_event_row_sha256s": [
                item.normalized_evidence.normalized_row.row_sha256
                for item in self.censored_event_rows
            ],
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class PhysicalProductionSessionIndex:
    schema: str
    index_id: str
    index_sha256: str
    production_evidence_receipt: PhysicalProductionEvidenceAcquisitionReceipt = (
        dataclasses.field(repr=False)
    )
    accepted_risk_binding: AcceptedRiskPairBinding | None = dataclasses.field(
        repr=False
    )
    index_path: Path = dataclasses.field(repr=False)
    path_fingerprint: tuple[object, ...] = dataclasses.field(repr=False)
    review_mode: str
    owner_waived_firm_admission_id: str | None
    owner_waived_firm_admission_sha256: str | None
    firm_owner_decision_id: str | None
    firm_owner_decision_sha256: str | None
    firm_refusal_ledger_id: str | None
    firm_refusal_ledger_sha256: str | None
    owner_waiver_scope: str | None
    production_evidence_receipt_id: str
    production_evidence_receipt_sha256: str
    production_input_archive_id: str
    production_input_archive_sha256: str
    accepted_risk_binding_sha256: str | None
    index_file_sha256: str
    index_file_byte_count: int
    session_axis_sha256: str
    session_count: int
    current_row_count: int
    censored_row_count: int
    total_index_row_count: int
    session_projection_sha256: str
    source_epoch_receipt_sha256: str
    fixture_only: bool
    independently_reviewed: bool
    owner_review_waived: bool
    historical_availability_claimed: bool
    post_first_formal_backtest_independent_review_required: bool
    disk_backed: bool
    full_pair_materialized: bool
    full_batch_materialized: bool
    full_union_materialized: bool
    full_row_evidence_map_materialized: bool
    filesystem_access_retained: bool
    provider_access: bool
    credential_access: bool
    outcome_access: bool
    quantconnect_access: bool
    object_store_access: bool
    deployment: bool
    orders: bool
    trading: bool

    def to_record(self) -> dict[str, object]:
        return _index_record(self)


_INDEXES: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalProductionSessionIndex],
        bytes,
        tuple[object, ...],
        int,
    ],
] = {}
_LOCK = threading.RLock()
_MISSING = object()


def _forget(identity: int, reference: object) -> None:
    with _LOCK:
        current = _INDEXES.get(identity)
        if current is not None and current[0] is reference:
            _INDEXES.pop(identity, None)


_PINNED_DEPENDENCIES = (
    (
        _acquisition,
        "require_physical_production_evidence_receipt",
        _acquisition.require_physical_production_evidence_receipt,
    ),
    (
        _acquisition,
        "require_reviewed_physical_production_evidence_receipt",
        _acquisition.require_reviewed_physical_production_evidence_receipt,
    ),
    (
        _acquisition,
        "require_section72_owner_waived_production_evidence_receipt",
        _acquisition.require_section72_owner_waived_production_evidence_receipt,
    ),
    (
        _bridge,
        "begin_physical_production_evidence_epoch",
        _bridge.begin_physical_production_evidence_epoch,
    ),
    (
        _bridge,
        "iter_physical_production_scoring_rows",
        _bridge.iter_physical_production_scoring_rows,
    ),
    (
        _bridge,
        "finish_physical_production_evidence_epoch",
        _bridge.finish_physical_production_evidence_epoch,
    ),
    (
        _bridge,
        "iter_section72_owner_waived_preopen_terminal_sessions",
        _bridge.iter_section72_owner_waived_preopen_terminal_sessions,
    ),
    (
        _bridge,
        "section72_owner_waived_preopen_session_axis",
        _bridge.section72_owner_waived_preopen_session_axis,
    ),
    (
        _c2,
        "build_physical_formal_accepted_risk_pair_binding",
        _c2.build_physical_formal_accepted_risk_pair_binding,
    ),
    (_c2, "_decode_normalized_record", _c2._decode_normalized_record),
    (_c2, "_decode_evidence_record", _c2._decode_evidence_record),
    (
        _streaming,
        "require_physical_preopen_terminal_archive",
        _streaming.require_physical_preopen_terminal_archive,
    ),
    (
        _streaming,
        "iter_physical_preopen_terminal_sessions",
        _streaming.iter_physical_preopen_terminal_sessions,
    ),
)
_PINNED_LOCALS = (
    ("canonical_json_bytes", canonical_json_bytes),
    ("decode_utf8", decode_utf8),
    ("require_sha256", require_sha256),
    ("sha256_bytes", sha256_bytes),
    ("strict_json_loads", strict_json_loads),
    ("build_endpoint_label_evidence", build_endpoint_label_evidence),
    ("require_accepted_risk_pair_binding", require_accepted_risk_pair_binding),
)
_PINNED_CAPACITY_CONTRACT = (
    MAX_INDEX_BYTES,
    MAX_INDEX_ROWS,
    MAX_INDEX_SESSIONS,
    MAX_SESSION_ROWS_PER_ARM,
    MAX_SESSION_ROWS,
    MAX_SESSION_PAYLOAD_BYTES,
    MAX_INDEX_RECORD_BYTES,
    INDEX_CAPACITY_CHECK_INTERVAL,
)


def _require_dependencies() -> None:
    if any(
        getattr(module, name, _MISSING) is not expected
        for module, name, expected in _PINNED_DEPENDENCIES
    ) or any(
        globals().get(name, _MISSING) is not expected
        for name, expected in _PINNED_LOCALS
    ) or (
        MAX_INDEX_BYTES,
        MAX_INDEX_ROWS,
        MAX_INDEX_SESSIONS,
        MAX_SESSION_ROWS_PER_ARM,
        MAX_SESSION_ROWS,
        MAX_SESSION_PAYLOAD_BYTES,
        MAX_INDEX_RECORD_BYTES,
        INDEX_CAPACITY_CHECK_INTERVAL,
    ) != _PINNED_CAPACITY_CONTRACT:
        raise PhysicalProductionSessionIndexError(
            "physical production session-index dependency changed"
        )


def _axis(receipt: PhysicalProductionEvidenceAcquisitionReceipt) -> tuple[str, ...]:
    try:
        sessions = receipt.session_axis
    except (AttributeError, TypeError) as exc:
        raise PhysicalProductionSessionIndexError(
            "physical production session axis is unavailable"
        ) from exc
    if (
        not sessions
        or len(sessions) > MAX_INDEX_SESSIONS
        or type(sessions) is not tuple
        or any(type(item) is not str for item in sessions)
    ):
        raise PhysicalProductionSessionIndexCapacityError(
            "physical production session axis changed or exceeded capacity"
        )
    if sessions != tuple(sorted(set(sessions))):
        raise PhysicalProductionSessionIndexError(
            "physical production session axis is not unique canonical order"
        )
    return sessions


def _axis_contains(axis: tuple[str, ...], value: str) -> bool:
    position = bisect_left(axis, value)
    return position < len(axis) and axis[position] == value


def _label_record(row: PhysicalProductionScoringRow) -> dict[str, object]:
    label = row.endpoint_label
    return {**label.semantic_record(), "evidence_sha256": label.evidence_sha256}


def _row_payload(row: PhysicalProductionScoringRow) -> bytes:
    if type(row) is not PhysicalProductionScoringRow:
        raise PhysicalProductionSessionIndexError(
            "physical production epoch yielded the wrong scoring-row type"
        )
    row.__post_init__()
    payload = canonical_json_bytes(
        {
            "normalized": row.normalized_evidence.normalized_row.to_record(),
            "evidence": row.normalized_evidence.evidence.to_record(),
            "endpoint_label": _label_record(row),
        }
    )
    if len(payload) > MAX_INDEX_RECORD_BYTES:
        raise PhysicalProductionSessionIndexCapacityError(
            "physical production scoring row exceeded fixed byte capacity"
        )
    return payload


def _strict_payload(payload: bytes) -> dict[str, Any]:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_INDEX_RECORD_BYTES:
        raise PhysicalProductionSessionIndexCapacityError(
            "physical production index row exceeded fixed byte capacity"
        )
    try:
        raw = strict_json_loads(
            decode_utf8(payload, "physical production index row"),
            "physical production index row",
        )
    except (TypeError, ValueError) as exc:
        raise PhysicalProductionSessionIndexError(
            "physical production index row is not strict UTF-8 JSON"
        ) from exc
    if (
        type(raw) is not dict
        or set(raw) != {"normalized", "evidence", "endpoint_label"}
        or canonical_json_bytes(raw) != payload
    ):
        raise PhysicalProductionSessionIndexError(
            "physical production index row is not canonical"
        )
    return raw


def _decode_row(payload: bytes) -> PhysicalProductionScoringRow:
    raw = _strict_payload(payload)
    try:
        normalized = _c2._decode_normalized_record(raw["normalized"])
        evidence = _c2._decode_evidence_record(raw["evidence"])
        label_raw = raw["endpoint_label"]
        if type(label_raw) is not dict or set(label_raw) != {
            "c2_row_sha256",
            "provider_event_id",
            "raw_previous_label",
            "raw_current_label",
            "source_sha256",
            "available_at",
            "evidence_sha256",
        }:
            raise PhysicalProductionSessionIndexError(
                "physical production endpoint-label fields changed"
            )
        label = build_endpoint_label_evidence(
            c2_row_sha256=label_raw["c2_row_sha256"],
            provider_event_id=label_raw["provider_event_id"],
            raw_previous_label=label_raw["raw_previous_label"],
            raw_current_label=label_raw["raw_current_label"],
            source_sha256=label_raw["source_sha256"],
            available_at=label_raw["available_at"],
        )
        if label.evidence_sha256 != label_raw["evidence_sha256"]:
            raise PhysicalProductionSessionIndexError(
                "physical production endpoint-label identity changed"
            )
        return PhysicalProductionScoringRow(
            normalized_evidence=_c2.PhysicalNormalizedEvidenceRow(
                normalized_row=normalized,
                evidence=evidence,
            ),
            endpoint_label=label,
        )
    except PhysicalProductionSessionIndexError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise PhysicalProductionSessionIndexError(
            "physical production index row could not be decoded"
        ) from exc


def _sqlite_bytes(connection: sqlite3.Connection) -> int:
    page_count = connection.execute("PRAGMA page_count").fetchone()[0]
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    if type(page_count) is not int or type(page_size) is not int:
        raise PhysicalProductionSessionIndexError(
            "physical production index SQLite counters changed type"
        )
    observed = page_count * page_size
    if observed > MAX_INDEX_BYTES:
        raise PhysicalProductionSessionIndexCapacityError(
            "physical production session index exceeded fixed byte capacity"
        )
    return observed


def _sqlite_is_full(error: BaseException) -> bool:
    code = getattr(error, "sqlite_errorcode", None)
    if type(code) is int and code & 0xFF == sqlite3.SQLITE_FULL:
        return True
    return str(error).casefold() == "database or disk is full"


def _open_builder(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=FILE")
        connection.execute("PRAGMA foreign_keys=ON")
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        maximum = MAX_INDEX_BYTES // page_size
        installed = connection.execute(
            f"PRAGMA max_page_count={maximum}"
        ).fetchone()[0]
        if installed != maximum:
            raise PhysicalProductionSessionIndexCapacityError(
                "physical production index hard SQLite capacity was not installed"
            )
        connection.execute(_CREATE_ROWS_SQL)
        connection.execute(_CREATE_METADATA_SQL)
    except BaseException:
        connection.close()
        raise
    os.chmod(path, 0o600)
    return connection


def _require_output_root(path: Path) -> Path:
    if type(path) is not type(Path()) or not path.is_absolute() or ".." in path.parts:
        raise PhysicalProductionSessionIndexError(
            "physical production index output root must be exact absolute Path"
        )
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise PhysicalProductionSessionIndexError(
            "physical production index output root is unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or (os.name != "nt" and stat.S_IMODE(metadata.st_mode) & 0o077)
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise PhysicalProductionSessionIndexError(
            "physical production index output root is not private directory"
        )
    return path


def _file_fingerprint(path: Path) -> tuple[object, ...]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PhysicalProductionSessionIndexError(
            "physical production index file is unavailable"
        ) from exc
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > MAX_INDEX_BYTES
            or (os.name != "nt" and stat.S_IMODE(before.st_mode) != 0o600)
            or (hasattr(os, "getuid") and before.st_uid != os.getuid())
        ):
            raise PhysicalProductionSessionIndexError(
                "physical production index is not bounded private regular file"
            )
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise PhysicalProductionSessionIndexError(
                    "physical production index ended during authentication"
                )
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise PhysicalProductionSessionIndexError(
                "physical production index grew during authentication"
            )
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    fields = (
        "st_dev",
        "st_ino",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
        "st_mode",
        "st_uid",
        "st_nlink",
    )
    if any(getattr(before, name) != getattr(after, name) for name in fields):
        raise PhysicalProductionSessionIndexError(
            "physical production index changed during authentication"
        )
    return (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_mode,
        before.st_uid,
        before.st_nlink,
        digest.hexdigest(),
    )


def _open_reader(path: Path) -> sqlite3.Connection:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro&immutable=1", uri=True, isolation_level=None
        )
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
    except (OSError, sqlite3.Error, ValueError) as exc:
        if connection is not None:
            connection.close()
        raise PhysicalProductionSessionIndexError(
            "physical production index could not be opened read-only"
        ) from exc
    return connection


def _projection(connection: sqlite3.Connection) -> tuple[int, tuple[int, int], str]:
    hasher = hashlib.sha256()
    hasher.update(b"[")
    count = 0
    arm_counts = [0, 0]
    try:
        for session, rank, row_sha256, payload in connection.execute(
            _ORDERED_ROWS_SQL
        ):
            if (
                type(session) is not str
                or type(rank) is not int
                or rank not in (0, 1)
                or type(row_sha256) is not str
            ):
                raise PhysicalProductionSessionIndexError(
                    "physical production index key changed type"
                )
            require_sha256(row_sha256, "physical production index row SHA-256")
            raw = bytes(payload)
            row = _decode_row(raw)
            if (
                row.normalized_evidence.normalized_row.eligible_session != session
                or row.normalized_evidence.normalized_row.row_sha256 != row_sha256
            ):
                raise PhysicalProductionSessionIndexError(
                    "physical production index key differs from row lineage"
                )
            if count:
                hasher.update(b",")
            hasher.update(raw[:-1])
            count += 1
            arm_counts[rank] += 1
            if count > MAX_INDEX_ROWS:
                raise PhysicalProductionSessionIndexCapacityError(
                    "physical production index row census exceeded capacity"
                )
    except sqlite3.Error as exc:
        raise PhysicalProductionSessionIndexError(
            "physical production index projection could not be read"
        ) from exc
    hasher.update(b"]\n")
    return count, (arm_counts[0], arm_counts[1]), hasher.hexdigest()


def _metadata_record(
    *,
    receipt: PhysicalProductionEvidenceAcquisitionReceipt,
    accepted_risk_sha256: str | None,
    axis_sha256: str,
    session_count: int,
    arm_counts: tuple[int, int],
    projection_sha256: str,
    epoch_receipt_sha256: str,
    fixture_only: bool,
) -> dict[str, object]:
    return {
        "schema": INDEX_SCHEMA,
        "review_mode": receipt.review_mode,
        "owner_waived_firm_admission_id": (
            receipt.owner_waived_firm_admission_id
        ),
        "owner_waived_firm_admission_sha256": (
            receipt.owner_waived_firm_admission_sha256
        ),
        "firm_owner_decision_id": receipt.firm_owner_decision_id,
        "firm_owner_decision_sha256": receipt.firm_owner_decision_sha256,
        "firm_refusal_ledger_id": receipt.firm_refusal_ledger_id,
        "firm_refusal_ledger_sha256": receipt.firm_refusal_ledger_sha256,
        "owner_waiver_scope": receipt.owner_waiver_scope,
        "production_evidence_receipt_id": receipt.receipt_id,
        "production_evidence_receipt_sha256": receipt.receipt_sha256,
        "production_input_archive_id": receipt.production_input_archive_id,
        "production_input_archive_sha256": receipt.production_input_archive_sha256,
        "accepted_risk_binding_sha256": accepted_risk_sha256,
        "session_axis_sha256": axis_sha256,
        "session_count": session_count,
        "current_row_count": arm_counts[0],
        "censored_row_count": arm_counts[1],
        "total_index_row_count": sum(arm_counts),
        "session_projection_sha256": projection_sha256,
        "source_epoch_receipt_sha256": epoch_receipt_sha256,
        "fixture_only": fixture_only,
        "independently_reviewed": receipt.independently_reviewed,
        "owner_review_waived": receipt.owner_review_waived,
        "historical_availability_claimed": (
            receipt.historical_availability_claimed
        ),
        "post_first_formal_backtest_independent_review_required": (
            receipt.post_first_formal_backtest_independent_review_required
        ),
        "disk_backed": True,
        "full_pair_materialized": False,
        "full_batch_materialized": False,
        "full_union_materialized": False,
        "full_row_evidence_map_materialized": False,
        "capabilities": {
            "filesystem_access_retained": False,
            "provider_access": False,
            "credential_access": False,
            "outcome_access": False,
            "quantconnect_access": False,
            "object_store_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _index_record(value: PhysicalProductionSessionIndex) -> dict[str, object]:
    return {
        **_metadata_record(
            receipt=value.production_evidence_receipt,
            accepted_risk_sha256=value.accepted_risk_binding_sha256,
            axis_sha256=value.session_axis_sha256,
            session_count=value.session_count,
            arm_counts=(value.current_row_count, value.censored_row_count),
            projection_sha256=value.session_projection_sha256,
            epoch_receipt_sha256=value.source_epoch_receipt_sha256,
            fixture_only=value.fixture_only,
        ),
        "index_file_sha256": value.index_file_sha256,
        "index_file_byte_count": value.index_file_byte_count,
    }


def _index_topology(value: PhysicalProductionSessionIndex) -> tuple[object, ...]:
    return (
        id(value.production_evidence_receipt),
        id(value.accepted_risk_binding),
        id(value.index_path),
        id(value.path_fingerprint),
    )


def _remove_failed_index(path: Path | None, directory: Path | None) -> None:
    if path is not None:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
    if directory is not None:
        try:
            os.rmdir(directory)
        except (FileNotFoundError, OSError):
            pass


def _build_index(
    *,
    receipt: PhysicalProductionEvidenceAcquisitionReceipt,
    output_root: Path,
    permit_fixture: bool,
    permit_section72_owner_waiver: bool = False,
) -> PhysicalProductionSessionIndex:
    _require_dependencies()
    if permit_fixture and permit_section72_owner_waiver:
        raise PhysicalProductionSessionIndexError(
            "physical production session-index admission modes overlap"
        )
    if permit_fixture:
        receipt = _acquisition.require_physical_production_evidence_receipt(receipt)
    elif permit_section72_owner_waiver:
        receipt = (
            _acquisition
            .require_section72_owner_waived_production_evidence_receipt(receipt)
        )
    else:
        receipt = _acquisition.require_reviewed_physical_production_evidence_receipt(
            receipt
        )
    if receipt.fixture_only is not permit_fixture:
        raise PhysicalProductionSessionIndexError(
            "physical production session-index fixture eligibility changed"
        )
    root = _require_output_root(output_root)
    c1_parent = getattr(receipt.bridge, "accepted_risk_archive", None)
    immutable_directories = tuple(
        item
        for item in (
            getattr(receipt.production_input_archive, "archive_path", None),
            getattr(c1_parent, "archive_path", None),
            getattr(c1_parent, "source_artifact_path", None),
        )
        if type(item) is type(Path())
    )
    for immutable in immutable_directories:
        try:
            root.relative_to(immutable.absolute())
        except ValueError:
            continue
        raise PhysicalProductionSessionIndexError(
            "physical production index output overlaps immutable input"
        )
    axis = _axis(receipt)
    axis_sha256 = sha256_bytes(canonical_json_bytes(list(axis)))
    accepted_risk: AcceptedRiskPairBinding | None
    if permit_fixture:
        accepted_risk = None
        accepted_risk_sha256 = None
    else:
        try:
            accepted_risk = _c2.build_physical_formal_accepted_risk_pair_binding(
                receipt.bridge.accepted_risk_archive,
                receipt.production_input_archive,
            )
            require_accepted_risk_pair_binding(accepted_risk)
        except (AttributeError, TypeError, ValueError) as exc:
            raise PhysicalProductionSessionIndexError(
                "physical production accepted-risk binding did not authenticate"
            ) from exc
        accepted_risk_sha256 = sha256_bytes(
            canonical_json_bytes(accepted_risk.to_record())
        )

    directory: Path | None = None
    path: Path | None = None
    connection: sqlite3.Connection | None = None
    try:
        directory = Path(
            tempfile.mkdtemp(prefix="arv2-physical-session-index-", dir=root)
        )
        os.chmod(directory, 0o700)
        path = directory / "session-index.sqlite3"
        connection = _open_builder(path)
        epoch = _bridge.begin_physical_production_evidence_epoch(receipt.bridge)
        observed_counts = [0, 0]
        connection.execute("BEGIN")
        for rank, arm in enumerate(_ARM_ORDER):
            for row in _bridge.iter_physical_production_scoring_rows(epoch, arm):
                normalized = row.normalized_evidence.normalized_row
                session = normalized.eligible_session
                if not _axis_contains(axis, session):
                    raise PhysicalProductionSessionIndexError(
                        "physical C2 row session is outside reviewed preopen axis"
                    )
                payload = _row_payload(row)
                try:
                    connection.execute(
                        "INSERT INTO scoring_rows("
                        "decision_session, arm_rank, row_sha256, payload"
                        ") VALUES (?, ?, ?, ?)",
                        (
                            session,
                            rank,
                            normalized.row_sha256,
                            sqlite3.Binary(payload),
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise PhysicalProductionSessionIndexError(
                        "physical production index repeated a session/arm/row key"
                    ) from exc
                observed_counts[rank] += 1
                if sum(observed_counts) > MAX_INDEX_ROWS:
                    raise PhysicalProductionSessionIndexCapacityError(
                        "physical production index row census exceeded capacity"
                    )
                if sum(observed_counts) % INDEX_CAPACITY_CHECK_INTERVAL == 0:
                    _sqlite_bytes(connection)
        source_epoch_receipt = _bridge.finish_physical_production_evidence_epoch(
            epoch
        )
        connection.execute("COMMIT")
        count, projected_counts, projection = _projection(connection)
        declared_counts = tuple(
            dict(source_epoch_receipt.arm_row_counts)[arm.value]
            for arm in _ARM_ORDER
        )
        if (
            count != sum(observed_counts)
            or tuple(observed_counts) != projected_counts
            or projected_counts != declared_counts
        ):
            raise PhysicalProductionSessionIndexError(
                "physical production index census differs from source epoch"
            )
        metadata = _metadata_record(
            receipt=receipt,
            accepted_risk_sha256=accepted_risk_sha256,
            axis_sha256=axis_sha256,
            session_count=len(axis),
            arm_counts=projected_counts,
            projection_sha256=projection,
            epoch_receipt_sha256=source_epoch_receipt.receipt_sha256,
            fixture_only=permit_fixture,
        )
        connection.execute(
            "INSERT INTO metadata(key, payload) VALUES ('authority', ?)",
            (sqlite3.Binary(canonical_json_bytes(metadata)),),
        )
        _sqlite_bytes(connection)
        connection.execute("PRAGMA optimize")
        connection.close()
        connection = None
        fingerprint = _file_fingerprint(path)
        file_sha256 = fingerprint[-1]
        file_bytes = fingerprint[2]
        value = object.__new__(PhysicalProductionSessionIndex)
        fields: dict[str, object] = {
            "schema": INDEX_SCHEMA,
            "index_id": "",
            "index_sha256": "",
            "production_evidence_receipt": receipt,
            "accepted_risk_binding": accepted_risk,
            "index_path": path,
            "path_fingerprint": fingerprint,
            "review_mode": receipt.review_mode,
            "owner_waived_firm_admission_id": (
                receipt.owner_waived_firm_admission_id
            ),
            "owner_waived_firm_admission_sha256": (
                receipt.owner_waived_firm_admission_sha256
            ),
            "firm_owner_decision_id": receipt.firm_owner_decision_id,
            "firm_owner_decision_sha256": receipt.firm_owner_decision_sha256,
            "firm_refusal_ledger_id": receipt.firm_refusal_ledger_id,
            "firm_refusal_ledger_sha256": receipt.firm_refusal_ledger_sha256,
            "owner_waiver_scope": receipt.owner_waiver_scope,
            "production_evidence_receipt_id": receipt.receipt_id,
            "production_evidence_receipt_sha256": receipt.receipt_sha256,
            "production_input_archive_id": receipt.production_input_archive_id,
            "production_input_archive_sha256": receipt.production_input_archive_sha256,
            "accepted_risk_binding_sha256": accepted_risk_sha256,
            "index_file_sha256": file_sha256,
            "index_file_byte_count": file_bytes,
            "session_axis_sha256": axis_sha256,
            "session_count": len(axis),
            "current_row_count": projected_counts[0],
            "censored_row_count": projected_counts[1],
            "total_index_row_count": count,
            "session_projection_sha256": projection,
            "source_epoch_receipt_sha256": source_epoch_receipt.receipt_sha256,
            "fixture_only": permit_fixture,
            "independently_reviewed": receipt.independently_reviewed,
            "owner_review_waived": receipt.owner_review_waived,
            "historical_availability_claimed": (
                receipt.historical_availability_claimed
            ),
            "post_first_formal_backtest_independent_review_required": (
                receipt.post_first_formal_backtest_independent_review_required
            ),
            "disk_backed": True,
            "full_pair_materialized": False,
            "full_batch_materialized": False,
            "full_union_materialized": False,
            "full_row_evidence_map_materialized": False,
            "filesystem_access_retained": False,
            "provider_access": False,
            "credential_access": False,
            "outcome_access": False,
            "quantconnect_access": False,
            "object_store_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        }
        if set(fields) != {item.name for item in dataclasses.fields(value)}:
            raise PhysicalProductionSessionIndexError(
                "physical production session-index field inventory changed"
            )
        for name, item in fields.items():
            object.__setattr__(value, name, item)
        digest = sha256_bytes(canonical_json_bytes(_index_record(value)))
        object.__setattr__(value, "index_sha256", digest)
        object.__setattr__(
            value, "index_id", f"arv2-physical-session-index-{digest[:24]}"
        )
        identity = id(value)
        reference = weakref.ref(value, lambda ref, key=identity: _forget(key, ref))
        with _LOCK:
            _INDEXES[identity] = (
                reference,
                canonical_json_bytes(_index_record(value)),
                _index_topology(value),
                os.getpid(),
            )
        return require_physical_production_session_index(value)
    except sqlite3.Error as exc:
        if connection is not None:
            connection.close()
        _remove_failed_index(path, directory)
        if _sqlite_is_full(exc):
            raise PhysicalProductionSessionIndexCapacityError(
                "physical production session index reached SQLite capacity"
            ) from exc
        raise PhysicalProductionSessionIndexError(
            "physical production session-index SQLite operation failed"
        ) from exc
    except BaseException:
        if connection is not None:
            connection.close()
        _remove_failed_index(path, directory)
        raise


def build_physical_production_session_index(
    *,
    receipt: PhysicalProductionEvidenceAcquisitionReceipt,
    output_root: Path,
) -> PhysicalProductionSessionIndex:
    """Build the production session index from an owner-reviewed physical C2."""

    return _build_index(receipt=receipt, output_root=output_root, permit_fixture=False)


def build_section72_owner_waived_physical_production_session_index(
    *,
    receipt: PhysicalProductionEvidenceAcquisitionReceipt,
    output_root: Path,
) -> PhysicalProductionSessionIndex:
    """Build the exact owner-waived index without claiming independent review."""

    return _build_index(
        receipt=receipt,
        output_root=output_root,
        permit_fixture=False,
        permit_section72_owner_waiver=True,
    )


def _build_test_fixture_physical_production_session_index(
    *,
    receipt: PhysicalProductionEvidenceAcquisitionReceipt,
    output_root: Path,
) -> PhysicalProductionSessionIndex:
    """Offline oracle seam; the resulting index is never formally eligible."""

    return _build_index(receipt=receipt, output_root=output_root, permit_fixture=True)


def _validate_index_surface(value: PhysicalProductionSessionIndex) -> None:
    string_fields = (
        "schema",
        "review_mode",
        "index_id",
        "index_sha256",
        "production_evidence_receipt_id",
        "production_evidence_receipt_sha256",
        "production_input_archive_id",
        "production_input_archive_sha256",
        "index_file_sha256",
        "session_axis_sha256",
        "session_projection_sha256",
        "source_epoch_receipt_sha256",
    )
    if any(type(getattr(value, name)) is not str for name in string_fields):
        raise PhysicalProductionSessionIndexError(
            "physical production session-index scalar type changed"
        )
    optional_strings = (
        "owner_waived_firm_admission_id",
        "owner_waived_firm_admission_sha256",
        "firm_owner_decision_id",
        "firm_owner_decision_sha256",
        "firm_refusal_ledger_id",
        "firm_refusal_ledger_sha256",
        "owner_waiver_scope",
    )
    if any(
        getattr(value, name) is not None
        and type(getattr(value, name)) is not str
        for name in optional_strings
    ):
        raise PhysicalProductionSessionIndexError(
            "physical production session-index waiver scalar changed type"
        )
    if value.accepted_risk_binding_sha256 is not None and (
        type(value.accepted_risk_binding_sha256) is not str
    ):
        raise PhysicalProductionSessionIndexError(
            "physical production accepted-risk hash changed type"
        )
    count_fields = (
        "index_file_byte_count",
        "session_count",
        "current_row_count",
        "censored_row_count",
        "total_index_row_count",
    )
    if any(
        type(getattr(value, name)) is not int or getattr(value, name) < 0
        for name in count_fields
    ):
        raise PhysicalProductionSessionIndexError(
            "physical production session-index count type changed"
        )
    bool_fields = (
        "fixture_only",
        "independently_reviewed",
        "owner_review_waived",
        "historical_availability_claimed",
        "post_first_formal_backtest_independent_review_required",
        "disk_backed",
        "full_pair_materialized",
        "full_batch_materialized",
        "full_union_materialized",
        "full_row_evidence_map_materialized",
        "filesystem_access_retained",
        "provider_access",
        "credential_access",
        "outcome_access",
        "quantconnect_access",
        "object_store_access",
        "deployment",
        "orders",
        "trading",
    )
    if any(type(getattr(value, name)) is not bool for name in bool_fields):
        raise PhysicalProductionSessionIndexError(
            "physical production session-index flag type changed"
        )
    if (
        type(value.index_path) is not type(Path())
        or type(value.path_fingerprint) is not tuple
    ):
        raise PhysicalProductionSessionIndexError(
            "physical production session-index path authority changed type"
        )


def require_physical_production_session_index(
    value: PhysicalProductionSessionIndex,
) -> PhysicalProductionSessionIndex:
    _require_dependencies()
    if type(value) is not PhysicalProductionSessionIndex:
        raise PhysicalProductionSessionIndexError(
            "physical production session-index changed type"
        )
    _validate_index_surface(value)
    with _LOCK:
        registered = _INDEXES.get(id(value))
    if (
        registered is None
        or registered[0]() is not value
        or registered[1] != canonical_json_bytes(_index_record(value))
        or registered[2] != _index_topology(value)
        or registered[3] != os.getpid()
    ):
        raise PhysicalProductionSessionIndexError(
            "physical production session-index lost builder authority"
        )
    try:
        if value.review_mode == _acquisition.FIXTURE_REVIEW_MODE:
            receipt = _acquisition.require_physical_production_evidence_receipt(
                value.production_evidence_receipt
            )
        elif value.review_mode == _acquisition.NORMAL_REVIEW_MODE:
            receipt = (
                _acquisition.require_reviewed_physical_production_evidence_receipt(
                    value.production_evidence_receipt
                )
            )
        elif value.review_mode == _acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE:
            receipt = (
                _acquisition
                .require_section72_owner_waived_production_evidence_receipt(
                    value.production_evidence_receipt
                )
            )
        else:
            raise PhysicalProductionSessionIndexError(
                "physical production session-index review mode changed"
            )
    except (AttributeError, TypeError, ValueError) as exc:
        raise PhysicalProductionSessionIndexError(
            "physical production session-index receipt changed"
        ) from exc
    fingerprint = _file_fingerprint(value.index_path)
    if fingerprint != value.path_fingerprint:
        raise PhysicalProductionSessionIndexError(
            "physical production session-index file changed"
        )
    digest = sha256_bytes(canonical_json_bytes(_index_record(value)))
    waiver_fields_are_exact = (
        value.review_mode == receipt.review_mode
        and value.owner_waived_firm_admission_id
        == receipt.owner_waived_firm_admission_id
        and value.owner_waived_firm_admission_sha256
        == receipt.owner_waived_firm_admission_sha256
        and value.firm_owner_decision_id == receipt.firm_owner_decision_id
        and value.firm_owner_decision_sha256
        == receipt.firm_owner_decision_sha256
        and value.firm_refusal_ledger_id == receipt.firm_refusal_ledger_id
        and value.firm_refusal_ledger_sha256
        == receipt.firm_refusal_ledger_sha256
        and value.owner_waiver_scope == receipt.owner_waiver_scope
        and value.independently_reviewed is receipt.independently_reviewed
        and value.owner_review_waived is receipt.owner_review_waived
        and value.historical_availability_claimed
        is receipt.historical_availability_claimed
        and value.post_first_formal_backtest_independent_review_required
        is receipt.post_first_formal_backtest_independent_review_required
    )
    false_flags = (
        value.full_pair_materialized,
        value.full_batch_materialized,
        value.full_union_materialized,
        value.full_row_evidence_map_materialized,
        value.filesystem_access_retained,
        value.provider_access,
        value.credential_access,
        value.outcome_access,
        value.quantconnect_access,
        value.object_store_access,
        value.deployment,
        value.orders,
        value.trading,
    )
    if (
        any(type(item) is not bool or item for item in false_flags)
        or not waiver_fields_are_exact
        or value.disk_backed is not True
        or value.fixture_only is not receipt.fixture_only
        or value.production_evidence_receipt is not receipt
        or value.production_evidence_receipt_id != receipt.receipt_id
        or value.production_evidence_receipt_sha256 != receipt.receipt_sha256
        or value.production_input_archive_id != receipt.production_input_archive_id
        or value.production_input_archive_sha256
        != receipt.production_input_archive_sha256
        or value.index_file_sha256 != fingerprint[-1]
        or value.index_file_byte_count != fingerprint[2]
        or value.total_index_row_count
        != value.current_row_count + value.censored_row_count
        or value.total_index_row_count > MAX_INDEX_ROWS
        or value.session_count > MAX_INDEX_SESSIONS
        or value.index_file_byte_count > MAX_INDEX_BYTES
        or value.index_sha256 != digest
        or value.index_id != f"arv2-physical-session-index-{digest[:24]}"
    ):
        raise PhysicalProductionSessionIndexError(
            "physical production session-index semantic binding changed"
        )
    if value.fixture_only:
        if (
            value.accepted_risk_binding is not None
            or value.accepted_risk_binding_sha256 is not None
        ):
            raise PhysicalProductionSessionIndexError(
                "fixture session index acquired formal accepted-risk binding"
            )
    else:
        try:
            binding = require_accepted_risk_pair_binding(value.accepted_risk_binding)
        except (TypeError, ValueError) as exc:
            raise PhysicalProductionSessionIndexError(
                "physical production accepted-risk binding changed"
            ) from exc
        if value.accepted_risk_binding_sha256 != sha256_bytes(
            canonical_json_bytes(binding.to_record())
        ):
            raise PhysicalProductionSessionIndexError(
                "physical production accepted-risk binding hash changed"
            )
    connection = _open_reader(value.index_path)
    try:
        rows_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='scoring_rows'"
        ).fetchone()
        metadata_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='metadata'"
        ).fetchone()
        metadata_row = connection.execute(
            "SELECT payload FROM metadata WHERE key='authority'"
        ).fetchone()
        if (
            rows_sql != (_CREATE_ROWS_SQL,)
            or metadata_sql != (_CREATE_METADATA_SQL,)
            or metadata_row is None
            or len(metadata_row) != 1
        ):
            raise PhysicalProductionSessionIndexError(
                "physical production session-index SQLite schema changed"
            )
        metadata = bytes(metadata_row[0])
        if metadata != canonical_json_bytes(
            _metadata_record(
                receipt=receipt,
                accepted_risk_sha256=value.accepted_risk_binding_sha256,
                axis_sha256=value.session_axis_sha256,
                session_count=value.session_count,
                arm_counts=(value.current_row_count, value.censored_row_count),
                projection_sha256=value.session_projection_sha256,
                epoch_receipt_sha256=value.source_epoch_receipt_sha256,
                fixture_only=value.fixture_only,
            )
        ):
            raise PhysicalProductionSessionIndexError(
                "physical production session-index metadata changed"
            )
    except sqlite3.Error as exc:
        raise PhysicalProductionSessionIndexError(
            "physical production session-index metadata could not be read"
        ) from exc
    finally:
        connection.close()
    return value


def require_formal_physical_production_session_index(
    value: PhysicalProductionSessionIndex,
) -> PhysicalProductionSessionIndex:
    index = require_physical_production_session_index(value)
    valid_review_mode = (
        index.review_mode == _acquisition.NORMAL_REVIEW_MODE
        and index.independently_reviewed is True
        and index.owner_review_waived is False
        and index.historical_availability_claimed is True
        and index.post_first_formal_backtest_independent_review_required is False
    ) or (
        index.review_mode == _acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE
        and index.independently_reviewed is False
        and index.owner_review_waived is True
        and index.historical_availability_claimed is False
        and index.post_first_formal_backtest_independent_review_required is True
        and index.owner_waiver_scope == _bridge.SECTION72_OWNER_WAIVER_SCOPE
    )
    if (
        index.fixture_only
        or index.accepted_risk_binding is None
        or not valid_review_mode
    ):
        raise PhysicalProductionSessionIndexError(
            "physical production session-index is not formally eligible"
        )
    return index


def _build_session_block(
    session: str,
    current: list[PhysicalProductionScoringRow],
    censored: list[PhysicalProductionScoringRow],
) -> PhysicalProductionSessionBlock:
    record = {
        "schema": SESSION_BLOCK_SCHEMA,
        "decision_session": session,
        "current_row_sha256s": [
            item.normalized_evidence.normalized_row.row_sha256 for item in current
        ],
        "censored_row_sha256s": [
            item.normalized_evidence.normalized_row.row_sha256 for item in censored
        ],
        "current_row_count": len(current),
        "censored_row_count": len(censored),
    }
    value = PhysicalProductionSessionBlock(
        schema=SESSION_BLOCK_SCHEMA,
        decision_session=session,
        current_rows=tuple(current),
        censored_rows=tuple(censored),
        current_row_count=len(current),
        censored_row_count=len(censored),
        block_sha256=sha256_bytes(canonical_json_bytes(record)),
    )
    if value.to_record() != record:
        raise PhysicalProductionSessionIndexError(
            "physical production session block changed during construction"
        )
    return value


def iter_physical_production_session_blocks(
    value: PhysicalProductionSessionIndex,
) -> Iterator[PhysicalProductionSessionBlock]:
    """Replay every reviewed session, retaining only the active session rows."""

    index = require_physical_production_session_index(value)
    axis = _axis(index.production_evidence_receipt)
    if sha256_bytes(canonical_json_bytes(list(axis))) != index.session_axis_sha256:
        raise PhysicalProductionSessionIndexError(
            "physical production session-index axis changed"
        )
    connection = _open_reader(index.index_path)
    try:
        authenticated_count, authenticated_arm_counts, authenticated_projection = (
            _projection(connection)
        )
    except BaseException:
        connection.close()
        raise
    if (
        authenticated_count != index.total_index_row_count
        or authenticated_arm_counts
        != (index.current_row_count, index.censored_row_count)
        or authenticated_projection != index.session_projection_sha256
    ):
        connection.close()
        raise PhysicalProductionSessionIndexError(
            "physical production session-index pre-replay projection changed"
        )
    try:
        cursor = connection.execute(_ORDERED_ROWS_SQL)
        pending = cursor.fetchone()
    except sqlite3.Error as exc:
        connection.close()
        raise PhysicalProductionSessionIndexError(
            "physical production session-index replay failed"
        ) from exc
    count = 0
    arm_counts = [0, 0]
    hasher = hashlib.sha256()
    hasher.update(b"[")
    completed = False
    try:
        for session in axis:
            _require_dependencies()
            by_arm: tuple[list[PhysicalProductionScoringRow], ...] = ([], [])
            session_row_count = 0
            session_payload_bytes = 0
            while pending is not None and pending[0] == session:
                _require_dependencies()
                observed_session, rank, row_sha256, payload = pending
                if (
                    type(observed_session) is not str
                    or type(rank) is not int
                    or rank not in (0, 1)
                    or type(row_sha256) is not str
                ):
                    raise PhysicalProductionSessionIndexError(
                        "physical production session-index key changed type"
                    )
                require_sha256(row_sha256, "physical production index row SHA-256")
                raw = bytes(payload)
                session_row_count += 1
                session_payload_bytes += len(raw)
                if session_row_count > MAX_SESSION_ROWS:
                    raise PhysicalProductionSessionIndexCapacityError(
                        "physical production session aggregate row census "
                        "exceeded capacity"
                    )
                if session_payload_bytes > MAX_SESSION_PAYLOAD_BYTES:
                    raise PhysicalProductionSessionIndexCapacityError(
                        "physical production session aggregate payload exceeded "
                        "byte capacity"
                    )
                row = _decode_row(raw)
                if (
                    row.normalized_evidence.normalized_row.eligible_session
                    != observed_session
                    or row.normalized_evidence.normalized_row.row_sha256
                    != row_sha256
                ):
                    raise PhysicalProductionSessionIndexError(
                        "physical production session-index row key changed"
                    )
                by_arm[rank].append(row)
                if len(by_arm[rank]) > MAX_SESSION_ROWS_PER_ARM:
                    raise PhysicalProductionSessionIndexCapacityError(
                        "physical production session row census exceeded capacity"
                    )
                if count:
                    hasher.update(b",")
                hasher.update(raw[:-1])
                count += 1
                arm_counts[rank] += 1
                pending = cursor.fetchone()
            if pending is not None and pending[0] < session:
                raise PhysicalProductionSessionIndexError(
                    "physical production session-index contains an undeclared session"
                )
            yield _build_session_block(session, by_arm[0], by_arm[1])
        _require_dependencies()
        if pending is not None:
            raise PhysicalProductionSessionIndexError(
                "physical production session-index contains an undeclared session"
            )
        hasher.update(b"]\n")
        if (
            count != index.total_index_row_count
            or tuple(arm_counts)
            != (index.current_row_count, index.censored_row_count)
            or hasher.hexdigest() != index.session_projection_sha256
        ):
            raise PhysicalProductionSessionIndexError(
                "physical production session-index replay census changed"
            )
        completed = True
    except sqlite3.Error as exc:
        raise PhysicalProductionSessionIndexError(
            "physical production session-index replay failed"
        ) from exc
    finally:
        cursor.close()
        connection.close()
        if completed and _file_fingerprint(index.index_path) != index.path_fingerprint:
            raise PhysicalProductionSessionIndexError(
                "physical production session-index changed during replay"
            )


def _scoring_session_input(
    block: PhysicalProductionSessionBlock,
    terminal: object,
) -> PhysicalProductionScoringSessionInput:
    if (
        type(block) is not PhysicalProductionSessionBlock
        or type(getattr(terminal, "decision_session", None)) is not str
        or terminal.decision_session != block.decision_session
        or type(getattr(terminal, "terminal_count", None)) is not int
        or type(getattr(terminal, "control_terminal_merkle_root", None)) is not str
        or type(getattr(terminal, "universe_terminal_merkle_root", None)) is not str
    ):
        raise PhysicalProductionSessionIndexError(
            "physical production scoring session parents differ"
        )
    seed = {
        "decision_session": block.decision_session,
        "control_terminal_merkle_root": terminal.control_terminal_merkle_root,
        "universe_terminal_merkle_root": terminal.universe_terminal_merkle_root,
        "physical_terminal_count": terminal.terminal_count,
        "current_event_row_sha256s": [
            item.normalized_evidence.normalized_row.row_sha256
            for item in block.current_rows
        ],
        "censored_event_row_sha256s": [
            item.normalized_evidence.normalized_row.row_sha256
            for item in block.censored_rows
        ],
    }
    value = PhysicalProductionScoringSessionInput(
        decision_session=block.decision_session,
        terminal_block=terminal,
        current_event_rows=block.current_rows,
        censored_event_rows=block.censored_rows,
        input_sha256=sha256_bytes(canonical_json_bytes(seed)),
    )
    if value.to_record() != seed:
        raise PhysicalProductionSessionIndexError(
            "physical production scoring session changed during construction"
        )
    return value


def _iter_scoring_session_inputs(
    value: PhysicalProductionSessionIndex,
    terminal_archive: object,
    *,
    permit_fixture: bool,
) -> Iterator[PhysicalProductionScoringSessionInput]:
    owner_waived = False
    if permit_fixture:
        index = require_physical_production_session_index(value)
    else:
        index = require_formal_physical_production_session_index(value)
        owner_waived = (
            index.review_mode
            == _acquisition.SECTION72_OWNER_WAIVED_REVIEW_MODE
        )
        if owner_waived:
            if (
                terminal_archive
                is not index.production_evidence_receipt.preopen_acquisition_receipt
            ):
                raise PhysicalProductionSessionIndexError(
                    "owner-waived production index and prereview archive parents differ"
                )
            try:
                _bridge.section72_owner_waived_preopen_session_axis(
                    index.production_evidence_receipt.bridge
                )
            except (AttributeError, TypeError, ValueError) as exc:
                raise PhysicalProductionSessionIndexError(
                    "owner-waived physical terminal archive did not authenticate"
                ) from exc
        else:
            if type(terminal_archive) is not _streaming.PhysicalPreopenTerminalArchive:
                raise PhysicalProductionSessionIndexError(
                    "formal physical scoring requires exact reviewed terminal archive"
                )
            try:
                terminal_archive = _streaming.require_physical_preopen_terminal_archive(
                    terminal_archive
                )
            except (AttributeError, TypeError, ValueError) as exc:
                raise PhysicalProductionSessionIndexError(
                    "formal physical terminal archive did not authenticate"
                ) from exc
    if not owner_waived and (
        getattr(terminal_archive, "preopen_acquisition_receipt", None)
        is not index.production_evidence_receipt.preopen_acquisition_receipt
    ):
        raise PhysicalProductionSessionIndexError(
            "physical production index and terminal archive parents differ"
        )
    event_blocks = iter_physical_production_session_blocks(index)
    terminal_blocks = (
        _bridge.iter_section72_owner_waived_preopen_terminal_sessions(
            index.production_evidence_receipt.bridge
        )
        if owner_waived
        else _streaming.iter_physical_preopen_terminal_sessions(terminal_archive)
    )
    sentinel = object()
    event = next(event_blocks, sentinel)
    terminal = next(terminal_blocks, sentinel)
    observed = 0
    while event is not sentinel or terminal is not sentinel:
        if event is sentinel or terminal is sentinel:
            raise PhysicalProductionSessionIndexError(
                "physical production scoring session censuses differ"
            )
        if type(event) is not PhysicalProductionSessionBlock:
            raise PhysicalProductionSessionIndexError(
                "physical production scoring event block changed type"
            )
        if event.decision_session != terminal.decision_session:
            raise PhysicalProductionSessionIndexError(
                "physical production scoring session order differs"
            )
        yield _scoring_session_input(event, terminal)
        observed += 1
        event = next(event_blocks, sentinel)
        terminal = next(terminal_blocks, sentinel)
    if observed != index.session_count:
        raise PhysicalProductionSessionIndexError(
            "physical production scoring session census changed"
        )


def iter_physical_production_scoring_session_inputs(
    value: PhysicalProductionSessionIndex,
    terminal_archive: object,
) -> Iterator[PhysicalProductionScoringSessionInput]:
    """Join a formal index replay to its reviewed physical terminal sessions.

    A physical replacement for ``begin_streamed_production_scoring`` can use
    this iterator directly; every yielded value owns only one session's event
    rows plus its matching universe/control terminal block.
    """

    yield from _iter_scoring_session_inputs(
        value, terminal_archive, permit_fixture=False
    )


def _iter_test_fixture_physical_production_scoring_session_inputs(
    value: PhysicalProductionSessionIndex,
    terminal_archive: object,
) -> Iterator[PhysicalProductionScoringSessionInput]:
    """Offline merge oracle; it does not make a fixture index formal."""

    yield from _iter_scoring_session_inputs(
        value, terminal_archive, permit_fixture=True
    )


__all__ = (
    "INDEX_SCHEMA",
    "MAX_INDEX_BYTES",
    "MAX_INDEX_RECORD_BYTES",
    "MAX_INDEX_ROWS",
    "MAX_INDEX_SESSIONS",
    "MAX_SESSION_PAYLOAD_BYTES",
    "MAX_SESSION_ROWS",
    "MAX_SESSION_ROWS_PER_ARM",
    "SESSION_BLOCK_SCHEMA",
    "PhysicalProductionSessionBlock",
    "PhysicalProductionScoringSessionInput",
    "PhysicalProductionSessionIndex",
    "PhysicalProductionSessionIndexCapacityError",
    "PhysicalProductionSessionIndexError",
    "build_physical_production_session_index",
    "build_section72_owner_waived_physical_production_session_index",
    "iter_physical_production_scoring_session_inputs",
    "iter_physical_production_session_blocks",
    "require_formal_physical_production_session_index",
    "require_physical_production_session_index",
)
