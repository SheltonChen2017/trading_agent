"""Owner-accepted current-snapshot terminal classification for a preliminary run.

The reviewed lifecycle builder remains untouched and authoritative for formal
PIT claims.  This sibling accepts only an authenticated Sharadar current-
snapshot admission.  It treats a slot as unaffected only when the admitted
price interval covers the complete slot.  Missing, refused/ambiguous identity,
and uncovered intervals become named terminal refusals; it never invents a
delisting payoff, successor, cash recovery, or reviewed lifecycle fact.
"""
import dataclasses
import hashlib
import os
import re
import sqlite3
import tempfile
import threading
import weakref
from collections import Counter
from datetime import date, datetime, timezone
from enum import Enum

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc.accepted_risk_security_master_admission import (
    AcceptedRiskSecurityMasterAdmission,
    iter_accepted_risk_security_master_mappings,
    iter_accepted_risk_security_master_refusals,
    require_accepted_risk_security_master_admission,
)
from research.analyst_revisions_v2_qc.formal_input_composer import (
    FormalTerminalDispositionPackage,
    TERMINAL_PACKAGE_SCHEMA,
    _axis,
    load_formal_terminal_disposition_package,
    require_formal_terminal_disposition_package,
)
from research.analyst_revisions_v2_qc.formal_run_protocol import (
    HORIZONS,
    TERMINAL_POLICY_ID,
    ArtifactBinding,
    TerminalCensusBinding,
    require_terminal_census_binding,
)
from research.analyst_revisions_v2_qc.formal_runtime_projection import (
    TERMINAL_OBJECT_SCHEMA,
)


RECORDER_SCHEMA = "arv2-owner-accepted-current-snapshot-terminal-recorder-v1"
BUILD_SCHEMA = "arv2-owner-accepted-current-snapshot-terminal-build-v1"
OWNER_RISK_DECISION = (
    "use_authenticated_Sharadar_current_snapshot_price_interval_only_for_"
    "preliminary_backtest_without_reviewed_or_point_in_time_lifecycle_claim"
)
MAX_SECURITY_COUNT = 100_000
MAX_SLOT_COUNT = 10_000_000
MAX_PACKAGE_ROWS = 500_000
MAX_PACKAGE_BYTES = 256 * 1024 * 1024
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}\Z")


class OwnerAcceptedTerminalRefusalReason(str, Enum):
    SECURITY_UNAVAILABLE = "owner_accepted_current_snapshot_security_unavailable"
    IDENTITY_REFUSED = "owner_accepted_current_snapshot_identity_refused"
    INTERVAL_DOES_NOT_COVER_SLOT = (
        "owner_accepted_current_snapshot_interval_does_not_cover_slot"
    )


class AcceptedRiskTerminalDispositionError(ValueError):
    """The current-snapshot recorder or package is not authoritative."""


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AcceptedRiskTerminalDispositionRecorder:
    schema: str
    security_master_admission: AcceptedRiskSecurityMasterAdmission = dataclasses.field(
        repr=False
    )
    security_master_admission_id: str
    security_master_admission_sha256: str
    source_snapshot_available_at: str
    owner_risk_decision: str
    point_in_time: bool
    independently_reviewed: bool
    historical_availability_claimed: bool
    reviewed_lifecycle_authority: bool


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class AcceptedRiskTerminalDispositionBuild:
    schema: str
    build_id: str
    build_sha256: str
    security_master_admission: AcceptedRiskSecurityMasterAdmission = dataclasses.field(
        repr=False
    )
    security_master_admission_id: str
    security_master_admission_sha256: str
    terminal_package: FormalTerminalDispositionPackage
    terminal_census: TerminalCensusBinding
    security_count: int
    actual_slot_count: int
    unaffected_slot_count: int
    terminal_requirement_count: int
    security_unavailable_refusal_count: int
    identity_refused_count: int
    interval_not_covered_refusal_count: int
    owner_risk_decision: str
    current_snapshot_identity_basis: bool
    owner_accepted_current_snapshot_risk: bool
    point_in_time: bool
    independently_reviewed: bool
    historical_availability_claimed: bool
    reviewed_lifecycle_authority: bool
    terminal_payoff_source_available: bool
    terminal_payoff_inferred: bool
    qc_delisting_price_used: bool
    successor_payoff_inferred: bool
    preliminary_evaluation_only: bool
    production_authority: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool

    def to_record(self) -> dict[str, object]:
        return _build_semantic(self)


@dataclasses.dataclass
class _RecorderState:
    reference: weakref.ReferenceType[AcceptedRiskTerminalDispositionRecorder]
    connection: sqlite3.Connection
    temporary: tempfile.TemporaryDirectory[str]
    status: str
    slot_count: int = 0


_RECORDERS: dict[int, _RecorderState] = {}
_BUILDS: dict[
    int,
    tuple[
        weakref.ReferenceType[AcceptedRiskTerminalDispositionBuild],
        tuple[object, ...],
        int,
    ],
] = {}
_LOCK = threading.RLock()


def _safe(value: object, name: str) -> str:
    if type(value) is not str or _SAFE.fullmatch(value) is None:
        raise AcceptedRiskTerminalDispositionError(f"{name} is not a safe identifier")
    return value


def _canonical_utc(value: object) -> str:
    if type(value) is not str:
        raise AcceptedRiskTerminalDispositionError(
            "current-snapshot availability is not UTC text"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00") if value.endswith("Z") else datetime.fromisoformat(value)
    except ValueError as exc:
        raise AcceptedRiskTerminalDispositionError(
            "current-snapshot availability is not UTC text"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise AcceptedRiskTerminalDispositionError(
            "current-snapshot availability is not exact UTC"
        )
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _forget_recorder(identity: int, reference: object) -> None:
    with _LOCK:
        state = _RECORDERS.get(identity)
        if state is not None and state.reference is reference:
            try:
                state.connection.close()
            finally:
                state.temporary.cleanup()
                _RECORDERS.pop(identity, None)


def _forget_build(identity: int, reference: object) -> None:
    with _LOCK:
        current = _BUILDS.get(identity)
        if current is not None and current[0] is reference:
            _BUILDS.pop(identity, None)


def begin_accepted_risk_terminal_disposition_recording(
    *, security_master_admission: AcceptedRiskSecurityMasterAdmission,
) -> AcceptedRiskTerminalDispositionRecorder:
    """Ingest exact admission terminals into a portable private SQLite spool."""

    try:
        admission = require_accepted_risk_security_master_admission(
            security_master_admission
        )
        mappings = tuple(iter_accepted_risk_security_master_mappings(admission))
        refusals = tuple(iter_accepted_risk_security_master_refusals(admission))
    except Exception as exc:
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk security-master admission did not authenticate"
        ) from exc
    if (
        admission.point_in_time is not False
        or admission.independently_reviewed is not False
        or admission.historical_availability_claimed is not False
        or admission.current_snapshot_identity_basis is not True
        or admission.owner_accepted_current_snapshot_risk is not True
    ):
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk security-master disclosure changed"
        )
    temporary = tempfile.TemporaryDirectory(prefix="arv2-terminal-disposition-")
    connection = sqlite3.connect(os.path.join(temporary.name, "slots.sqlite3"))
    try:
        connection.execute(
            "CREATE TABLE source_security (security_id TEXT PRIMARY KEY, status TEXT NOT NULL, "
            "first_session TEXT, last_session TEXT, source_sha256 TEXT NOT NULL, "
            "reason_codes TEXT NOT NULL) WITHOUT ROWID"
        )
        connection.execute(
            "CREATE TABLE actual_security (security_id TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        connection.execute(
            "CREATE TABLE actual_slot (slot_kind TEXT NOT NULL, slot_id TEXT NOT NULL, "
            "horizon_key INTEGER NOT NULL, horizon INTEGER, security_id TEXT NOT NULL, "
            "first_session TEXT NOT NULL, last_session TEXT NOT NULL, "
            "PRIMARY KEY(slot_kind,slot_id,horizon_key)) WITHOUT ROWID"
        )
        for row in mappings:
            connection.execute(
                "INSERT INTO source_security VALUES (?,?,?,?,?,?)",
                (
                    row["security_id"],
                    "mapped_current_snapshot",
                    row["candidate_first_session"],
                    row["candidate_last_session"],
                    row["source_row_sha256"],
                    "[]",
                ),
            )
        for row in refusals:
            security_id = row["observed_security_id"]
            if security_id is None:
                continue
            encoded_reasons = canonical_json_bytes(row["reason_codes"]).decode("utf-8").strip()
            try:
                connection.execute(
                    "INSERT INTO source_security VALUES (?,?,?,?,?,?)",
                    (
                        security_id,
                        "identity_refused",
                        None,
                        None,
                        row["source_row_sha256"],
                        encoded_reasons,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise AcceptedRiskTerminalDispositionError(
                    "accepted-risk admission contains conflicting security terminals"
                ) from exc
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
    except Exception:
        connection.close()
        temporary.cleanup()
        raise
    value = AcceptedRiskTerminalDispositionRecorder(
        schema=RECORDER_SCHEMA,
        security_master_admission=admission,
        security_master_admission_id=admission.admission_id,
        security_master_admission_sha256=admission.admission_sha256,
        source_snapshot_available_at=_canonical_utc(
            admission.source_snapshot_available_at
        ),
        owner_risk_decision=OWNER_RISK_DECISION,
        point_in_time=False,
        independently_reviewed=False,
        historical_availability_claimed=False,
        reviewed_lifecycle_authority=False,
    )
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_recorder(key, ref)
    )
    with _LOCK:
        _RECORDERS[identity] = _RecorderState(
            reference=reference,
            connection=connection,
            temporary=temporary,
            status="recording",
        )
    return require_fresh_accepted_risk_terminal_disposition_recorder(value)


def _require_recorder(
    value: AcceptedRiskTerminalDispositionRecorder, *, fresh: bool = False
) -> tuple[AcceptedRiskTerminalDispositionRecorder, _RecorderState]:
    if type(value) is not AcceptedRiskTerminalDispositionRecorder:
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk terminal recorder changed type"
        )
    with _LOCK:
        state = _RECORDERS.get(id(value))
    if (
        state is None
        or state.reference() is not value
        or state.status != "recording"
        or value.schema != RECORDER_SCHEMA
        or value.owner_risk_decision != OWNER_RISK_DECISION
        or value.point_in_time is not False
        or value.independently_reviewed is not False
        or value.historical_availability_claimed is not False
        or value.reviewed_lifecycle_authority is not False
    ):
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk terminal recorder is not current process authority"
        )
    try:
        admission = require_accepted_risk_security_master_admission(
            value.security_master_admission
        )
    except Exception as exc:
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk security-master admission changed during recording"
        ) from exc
    if (
        admission.admission_id != value.security_master_admission_id
        or admission.admission_sha256 != value.security_master_admission_sha256
    ):
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk security-master binding changed during recording"
        )
    if fresh:
        securities = state.connection.execute(
            "SELECT COUNT(*) FROM actual_security"
        ).fetchone()[0]
        slots = state.connection.execute("SELECT COUNT(*) FROM actual_slot").fetchone()[0]
        if securities != 0 or slots != 0 or state.slot_count != 0:
            raise AcceptedRiskTerminalDispositionError(
                "accepted-risk terminal recorder must be fresh"
            )
    return value, state


def require_fresh_accepted_risk_terminal_disposition_recorder(
    value: AcceptedRiskTerminalDispositionRecorder,
) -> AcceptedRiskTerminalDispositionRecorder:
    with _LOCK:
        return _require_recorder(value, fresh=True)[0]


def record_accepted_risk_terminal_security(
    value: AcceptedRiskTerminalDispositionRecorder, *, security_id: str
) -> None:
    security = _safe(security_id, "accepted-risk terminal security_id")
    with _LOCK:
        _, state = _require_recorder(value)
        state.connection.execute(
            "INSERT OR IGNORE INTO actual_security VALUES (?)", (security,)
        )
        count = state.connection.execute(
            "SELECT COUNT(*) FROM actual_security"
        ).fetchone()[0]
        if count > MAX_SECURITY_COUNT:
            raise AcceptedRiskTerminalDispositionError(
                "accepted-risk terminal security census exceeds its fixed ceiling"
            )


def _slot_geometry(
    *, first_session: date, last_session: date, expected_steps: int
) -> None:
    if (
        type(first_session) is not date
        or type(last_session) is not date
        or type(expected_steps) is not int
        or expected_steps < 1
        or last_session <= first_session
    ):
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk terminal slot geometry changed type or order"
        )
    try:
        axis, positions = _axis()
    except Exception as exc:
        raise AcceptedRiskTerminalDispositionError(
            "reviewed formal outcome axis did not authenticate"
        ) from exc
    first = positions.get(first_session)
    last = positions.get(last_session)
    if (
        type(axis) is not tuple
        or type(first) is not int
        or type(last) is not int
        or last - first != expected_steps
    ):
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk terminal slot does not span its declared outcome sessions"
        )


def record_accepted_risk_terminal_slot(
    value: AcceptedRiskTerminalDispositionRecorder,
    *,
    slot_kind: str,
    slot_id: str,
    horizon_sessions: int | None,
    security_id: str,
    first_session: date,
    last_session: date,
) -> bool:
    if slot_kind not in {"decision_horizon", "economic_daily"}:
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk terminal slot kind changed"
        )
    slot = _safe(slot_id, "accepted-risk terminal slot_id")
    security = _safe(security_id, "accepted-risk terminal security_id")
    if slot_kind == "decision_horizon":
        if type(horizon_sessions) is not int or horizon_sessions not in HORIZONS:
            raise AcceptedRiskTerminalDispositionError(
                "accepted-risk decision terminal horizon changed"
            )
        horizon_key = horizon_sessions
        steps = horizon_sessions
    else:
        if horizon_sessions is not None:
            raise AcceptedRiskTerminalDispositionError(
                "accepted-risk economic terminal gained a horizon"
            )
        horizon_key = -1
        steps = 1
    _slot_geometry(
        first_session=first_session, last_session=last_session, expected_steps=steps
    )
    record = (
        horizon_sessions,
        security,
        first_session.isoformat(),
        last_session.isoformat(),
    )
    with _LOCK:
        _, state = _require_recorder(value)
        if state.connection.execute(
            "SELECT 1 FROM actual_security WHERE security_id=?", (security,)
        ).fetchone() is None:
            raise AcceptedRiskTerminalDispositionError(
                "accepted-risk terminal slot security was not recorded"
            )
        existing = state.connection.execute(
            "SELECT horizon,security_id,first_session,last_session FROM actual_slot "
            "WHERE slot_kind=? AND slot_id=? AND horizon_key=?",
            (slot_kind, slot, horizon_key),
        ).fetchone()
        if existing is not None:
            if tuple(existing) == record:
                return False
            raise AcceptedRiskTerminalDispositionError(
                "accepted-risk terminal slot repeated with conflicting geometry"
            )
        state.connection.execute(
            "INSERT INTO actual_slot VALUES (?,?,?,?,?,?,?)",
            (
                slot_kind,
                slot,
                horizon_key,
                horizon_sessions,
                security,
                first_session.isoformat(),
                last_session.isoformat(),
            ),
        )
        state.slot_count += 1
        if state.slot_count > MAX_SLOT_COUNT:
            raise AcceptedRiskTerminalDispositionError(
                "accepted-risk terminal slot census exceeds its fixed ceiling"
            )
    return True


def _build_semantic(value: AcceptedRiskTerminalDispositionBuild) -> dict[str, object]:
    return {
        field.name: (
            value.terminal_package.package_id
            if field.name == "terminal_package"
            else value.terminal_census.to_record()
            if field.name == "terminal_census"
            else value.security_master_admission_id
            if field.name == "security_master_admission"
            else getattr(value, field.name)
        )
        for field in dataclasses.fields(value)
        if field.name not in {"build_id", "build_sha256"}
    }


def finalize_accepted_risk_terminal_disposition_recording(
    *,
    recorder: AcceptedRiskTerminalDispositionRecorder,
    calculation_as_of_date: date,
) -> AcceptedRiskTerminalDispositionBuild:
    if type(calculation_as_of_date) is not date:
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk terminal calculation date changed type"
        )
    with _LOCK:
        value, state = _require_recorder(recorder)
        state.status = "finalizing"
        state.connection.commit()
        security_count = state.connection.execute(
            "SELECT COUNT(*) FROM actual_security"
        ).fetchone()[0]
        slot_count = state.connection.execute("SELECT COUNT(*) FROM actual_slot").fetchone()[0]
        if security_count < 1 or slot_count != state.slot_count:
            raise AcceptedRiskTerminalDispositionError(
                "accepted-risk terminal security or slot census changed"
            )
        calculation_available = calculation_as_of_date.isoformat() + "T23:59:59.999999Z"
        source_available = value.source_snapshot_available_at
        if source_available > calculation_available:
            raise AcceptedRiskTerminalDispositionError(
                "current-snapshot evidence was unavailable by calculation date"
            )
        rows: list[dict[str, object]] = []
        counts: Counter[str] = Counter()
        unaffected = 0
        query = (
            "SELECT a.slot_kind,a.slot_id,a.horizon,a.security_id,a.first_session,"
            "a.last_session,s.status,s.first_session,s.last_session,s.source_sha256,"
            "s.reason_codes FROM actual_slot a LEFT JOIN source_security s "
            "ON s.security_id=a.security_id ORDER BY a.slot_kind,a.slot_id,"
            "CASE WHEN a.horizon IS NULL THEN -1 ELSE a.horizon END"
        )
        for row in state.connection.execute(query):
            (
                slot_kind, slot_id, horizon, security, first, last,
                source_status, source_first, source_last, source_sha, reason_codes,
            ) = row
            if source_status is None:
                reason = OwnerAcceptedTerminalRefusalReason.SECURITY_UNAVAILABLE.value
                source_lineage = None
            elif source_status == "identity_refused":
                reason = OwnerAcceptedTerminalRefusalReason.IDENTITY_REFUSED.value
                source_lineage = hashlib.sha256(
                    canonical_json_bytes(
                        {"source_sha256": source_sha, "reason_codes": reason_codes}
                    )
                ).hexdigest()
            elif source_status == "mapped_current_snapshot":
                if source_first <= first and last <= source_last:
                    unaffected += 1
                    continue
                reason = (
                    OwnerAcceptedTerminalRefusalReason.INTERVAL_DOES_NOT_COVER_SLOT.value
                )
                source_lineage = str(source_sha)
            else:
                raise AcceptedRiskTerminalDispositionError(
                    "accepted-risk source security disposition changed"
                )
            counts[reason] += 1
            lineage = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "domain": "arv2-owner-accepted-current-snapshot-terminal-refusal-v1",
                        "security_master_admission_id": value.security_master_admission_id,
                        "security_master_admission_sha256": value.security_master_admission_sha256,
                        "slot_kind": slot_kind,
                        "slot_id": slot_id,
                        "horizon": horizon,
                        "security_id": security,
                        "first_session": first,
                        "last_session": last,
                        "reason": reason,
                        "source_lineage_sha256": source_lineage,
                        "owner_risk_decision": OWNER_RISK_DECISION,
                    }
                )
            ).hexdigest()
            rows.append(
                {
                    "schema": TERMINAL_OBJECT_SCHEMA,
                    "slot_kind": slot_kind,
                    "slot_id": slot_id,
                    "horizon": horizon,
                    "disposition": "named_terminal_refusal",
                    "stock_return": None,
                    "reason": reason,
                    "terminal_lineage_sha256": lineage,
                    "available_at_utc": source_available,
                }
            )
            if len(rows) > MAX_PACKAGE_ROWS:
                raise AcceptedRiskTerminalDispositionError(
                    "accepted-risk terminal refusal package exceeds its row ceiling"
                )
        if slot_count != unaffected + len(rows) or sum(counts.values()) != len(rows):
            raise AcceptedRiskTerminalDispositionError(
                "accepted-risk terminal slots were silently omitted"
            )
        payload = canonical_json_bytes(
            {
                "schema": TERMINAL_PACKAGE_SCHEMA,
                "terminal_policy_id": TERMINAL_POLICY_ID,
                "row_count": len(rows),
                "rows": rows,
            }
        )
        if len(payload) > MAX_PACKAGE_BYTES:
            raise AcceptedRiskTerminalDispositionError(
                "accepted-risk terminal refusal package exceeds its byte ceiling"
            )
        package_sha = hashlib.sha256(payload).hexdigest()
        census_seed = {
            "domain": "arv2-owner-accepted-current-snapshot-terminal-census-v1",
            "admission_sha256": value.security_master_admission_sha256,
            "package_sha256": package_sha,
            "security_count": security_count,
            "slot_count": slot_count,
            "unaffected_slot_count": unaffected,
            "refusal_counts": dict(sorted(counts.items())),
        }
        census_sha = hashlib.sha256(canonical_json_bytes(census_seed)).hexdigest()
        census = TerminalCensusBinding(
            census=ArtifactBinding(
                artifact_id="arv2-owner-accepted-terminal-census-" + census_sha[:24],
                content_sha256=package_sha,
                artifact_sha256=census_sha,
                byte_count=len(payload),
            ),
            terminal_policy_id=TERMINAL_POLICY_ID,
            security_count=security_count,
            lifecycle_coverage_count=security_count,
            terminal_requirement_count=len(rows),
            terminal_payoff_count=0,
            benchmark_splice_continuation_count=0,
            named_terminal_refusal_count=len(rows),
            silently_omitted_count=0,
        )
        package = load_formal_terminal_disposition_package(
            payload=payload, terminal_census=census
        )
        state.connection.close()
        state.temporary.cleanup()
        state.status = "finalized"
        preliminary = {
            "schema": BUILD_SCHEMA,
            "security_master_admission": value.security_master_admission_id,
            "security_master_admission_id": value.security_master_admission_id,
            "security_master_admission_sha256": value.security_master_admission_sha256,
            "terminal_package": package.package_id,
            "terminal_census": census.to_record(),
            "security_count": security_count,
            "actual_slot_count": slot_count,
            "unaffected_slot_count": unaffected,
            "terminal_requirement_count": len(rows),
            "security_unavailable_refusal_count": counts[
                OwnerAcceptedTerminalRefusalReason.SECURITY_UNAVAILABLE.value
            ],
            "identity_refused_count": counts[
                OwnerAcceptedTerminalRefusalReason.IDENTITY_REFUSED.value
            ],
            "interval_not_covered_refusal_count": counts[
                OwnerAcceptedTerminalRefusalReason.INTERVAL_DOES_NOT_COVER_SLOT.value
            ],
            "owner_risk_decision": OWNER_RISK_DECISION,
            "current_snapshot_identity_basis": True,
            "owner_accepted_current_snapshot_risk": True,
            "point_in_time": False,
            "independently_reviewed": False,
            "historical_availability_claimed": False,
            "reviewed_lifecycle_authority": False,
            "terminal_payoff_source_available": False,
            "terminal_payoff_inferred": False,
            "qc_delisting_price_used": False,
            "successor_payoff_inferred": False,
            "preliminary_evaluation_only": True,
            "production_authority": False,
            "outcome_access": False,
            "result_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        }
        digest = hashlib.sha256(canonical_json_bytes(preliminary)).hexdigest()
        build = AcceptedRiskTerminalDispositionBuild(
            build_id="arv2-owner-accepted-terminal-build-" + digest[:24],
            build_sha256=digest,
            security_master_admission=value.security_master_admission,
            **{name: item for name, item in preliminary.items() if name != "security_master_admission" and name not in {"terminal_package", "terminal_census"}},
            terminal_package=package,
            terminal_census=census,
        )
        identity = id(build)
        reference = weakref.ref(build, lambda ref, key=identity: _forget_build(key, ref))
        _BUILDS[identity] = (reference, tuple(_build_semantic(build).items()), os.getpid())
        _RECORDERS.pop(id(value), None)
    return require_accepted_risk_terminal_disposition_build(build)


def require_accepted_risk_terminal_disposition_build(
    value: AcceptedRiskTerminalDispositionBuild,
) -> AcceptedRiskTerminalDispositionBuild:
    if type(value) is not AcceptedRiskTerminalDispositionBuild:
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk terminal build changed type"
        )
    with _LOCK:
        registered = _BUILDS.get(id(value))
    if (
        registered is None
        or registered[0]() is not value
        or registered[2] != os.getpid()
        or registered[1] != tuple(_build_semantic(value).items())
    ):
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk terminal build is not current process authority"
        )
    try:
        admission = require_accepted_risk_security_master_admission(
            value.security_master_admission
        )
        package = require_formal_terminal_disposition_package(value.terminal_package)
        census = require_terminal_census_binding(value.terminal_census)
    except Exception as exc:
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk terminal build parent changed"
        ) from exc
    semantic = _build_semantic(value)
    digest = hashlib.sha256(canonical_json_bytes(semantic)).hexdigest()
    if (
        value.build_sha256 != digest
        or value.build_id != "arv2-owner-accepted-terminal-build-" + digest[:24]
        or admission.admission_id != value.security_master_admission_id
        or admission.admission_sha256 != value.security_master_admission_sha256
        or package.terminal_census is not census
        or value.actual_slot_count
        != value.unaffected_slot_count + value.terminal_requirement_count
        or value.terminal_requirement_count
        != (
            value.security_unavailable_refusal_count
            + value.identity_refused_count
            + value.interval_not_covered_refusal_count
        )
        or value.owner_risk_decision != OWNER_RISK_DECISION
        or value.current_snapshot_identity_basis is not True
        or value.owner_accepted_current_snapshot_risk is not True
        or value.point_in_time is not False
        or value.independently_reviewed is not False
        or value.historical_availability_claimed is not False
        or value.reviewed_lifecycle_authority is not False
        or value.terminal_payoff_source_available is not False
        or value.terminal_payoff_inferred is not False
        or value.qc_delisting_price_used is not False
        or value.successor_payoff_inferred is not False
        or value.preliminary_evaluation_only is not True
        or any(
            getattr(value, name) is not False
            for name in (
                "production_authority", "outcome_access", "result_access",
                "deployment", "orders", "trading",
            )
        )
    ):
        raise AcceptedRiskTerminalDispositionError(
            "accepted-risk terminal build disclosure or census changed"
        )
    return value


__all__ = (
    "BUILD_SCHEMA",
    "OWNER_RISK_DECISION",
    "RECORDER_SCHEMA",
    "AcceptedRiskTerminalDispositionBuild",
    "AcceptedRiskTerminalDispositionError",
    "AcceptedRiskTerminalDispositionRecorder",
    "OwnerAcceptedTerminalRefusalReason",
    "begin_accepted_risk_terminal_disposition_recording",
    "finalize_accepted_risk_terminal_disposition_recording",
    "record_accepted_risk_terminal_security",
    "record_accepted_risk_terminal_slot",
    "require_accepted_risk_terminal_disposition_build",
    "require_fresh_accepted_risk_terminal_disposition_recorder",
)
