"""Strict point-in-time ETF holdings and coverage contracts."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import weakref
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
from enum import Enum
from typing import Iterable

from data.financial_primitives import to_decimal

from data.exchange_calendar import (
    ExchangeCalendarError,
    is_trading_session,
    session_open_instant,
    trading_sessions,
)

from .canonical import (
    CanonicalEvidenceError,
    require_canonical_json_bytes,
    require_exact_keys,
)
from .formulas import (
    FormulaError,
    ObservationState,
    ResearchSourceKind,
    SignalObservation,
    VerifiedAnalystPolicy,
    analyst_decimal_context,
    require_registered_source_bytes,
    require_verified_analyst_policy,
)


class HoldingsError(ValueError):
    pass


HOLDINGS_BOOK_TOLERANCE = Decimal("0.001")
MINIMUM_MAPPED_CANDIDATE_COVERAGE = Decimal("0.99")
MAXIMUM_HOLDINGS_LAG_SESSIONS = 1
_HOLDINGS_SCHEMA = "arv2-holdings-content-v1"
_VERIFIED_SNAPSHOT_TOKEN = object()
_VERIFIED_EVIDENCE_TOKEN = object()
_VERIFIED_STOCK_SCORE_TOKEN = object()
_STOCK_SCORE_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType["VerifiedStockScoreEvidence"], str]
] = {}
# Matches the snapshot/dataset/preregistration/policy registries: a weakref
# callback can fire on any thread, so registry access is uniformly locked.
_STOCK_SCORE_AUTHORITIES_LOCK = threading.RLock()
_HOLDINGS_SOURCE_SCHEMA = "arv2-holdings-source-v1"
_STOCK_SCORE_SOURCE_SCHEMA = "arv2-stock-score-source-v1"
_HOLDINGS_SOURCE_KEYS = frozenset(
    {
        "schema",
        "source_id",
        "evidence_epoch_id",
        "etf_security_id",
        "source_snapshot_id",
        "effective_at",
        "effective_session",
        "available_at",
        "declared_total_weight",
        "holdings",
    }
)
_HOLDING_SOURCE_KEYS = frozenset(
    {
        "position_id",
        "instrument_kind",
        "weight",
        "security_id",
        "share_class_id",
        "mapping_state",
        "peer_category_id",
    }
)
_STOCK_SCORE_SOURCE_KEYS = frozenset(
    {
        "schema",
        "source_id",
        "score_artifact_id",
        "evidence_epoch_id",
        "policy_sha256",
        "derived_at",
        "available_at",
        "decision_at",
        "normalized_dataset",
        "derivation",
        "scores",
    }
)
_STOCK_SCORE_DATASET_KEYS = frozenset(
    {
        "dataset_id",
        "normalization_result_sha256",
        "snapshot_id",
        "snapshot_manifest_sha256",
        "normalizer_config_sha256",
        "normalizer_code_sha256",
        "evidence_epoch_id",
        "build_recipe_id",
        "build_recipe_sha256",
        "producing_commit",
        "producing_tree",
        "events_sha256",
        "refusals_sha256",
    }
)
_STOCK_SCORE_DERIVATION_KEYS = frozenset(
    {
        "derivation_id",
        "derivation_config_sha256",
        "derivation_code_sha256",
        "producing_commit",
        "producing_tree",
    }
)
_STOCK_SCORE_RECORD_KEYS = frozenset({"security_id", "state", "value"})


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool):
        raise HoldingsError(f"{name} must be finite, not bool")
    try:
        parsed = to_decimal(value, name=name)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HoldingsError(f"{name} must be finite") from exc
    return parsed


def _instant(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HoldingsError(f"{name} must be a canonical aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HoldingsError(f"{name} must be a canonical aware ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HoldingsError(f"{name} must be timezone-aware")
    canonical = parsed.isoformat()
    if value not in {canonical, canonical.replace("+00:00", "Z")}:
        raise HoldingsError(f"{name} must use canonical ISO-8601 spelling")
    return parsed.astimezone(timezone.utc)


def _canonical_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HoldingsError(f"{name} must be canonical and non-empty")
    return value


def _sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise HoldingsError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _git_object(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise HoldingsError(f"{name} must be a lowercase Git object ID")
    return value


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


class InstrumentKind(str, Enum):
    LONG_EQUITY = "long_equity"
    CASH = "cash"
    DERIVATIVE = "derivative"


class MappingState(str, Enum):
    MAPPED = "mapped"
    UNMAPPED = "unmapped"
    NOT_APPLICABLE = "not_applicable"


@dataclasses.dataclass(frozen=True)
class Holding:
    position_id: str
    instrument_kind: InstrumentKind
    weight: Decimal | str | int | float
    security_id: str | None
    share_class_id: str | None
    mapping_state: MappingState
    peer_category_id: str | None = None

    def __post_init__(self) -> None:
        _canonical_text(self.position_id, "position_id")
        weight = _decimal(self.weight, "weight")
        if weight <= 0:
            raise HoldingsError("canonical V2 positions require positive weights")
        if not isinstance(self.instrument_kind, InstrumentKind):
            raise HoldingsError("instrument_kind must be an InstrumentKind")
        if not isinstance(self.mapping_state, MappingState):
            raise HoldingsError("mapping_state must be a MappingState")
        if self.instrument_kind is InstrumentKind.LONG_EQUITY:
            if self.mapping_state is MappingState.NOT_APPLICABLE:
                raise HoldingsError("long equity mapping cannot be not_applicable")
            if self.mapping_state is MappingState.MAPPED:
                for name in ("security_id", "share_class_id", "peer_category_id"):
                    _canonical_text(getattr(self, name), name)
            elif any(
                value is not None
                for value in (self.security_id, self.share_class_id, self.peer_category_id)
            ):
                raise HoldingsError(
                    "unmapped long equity cannot assert permanent identity or category"
                )
        elif self.mapping_state is not MappingState.NOT_APPLICABLE:
            raise HoldingsError("cash/derivatives must use not_applicable mapping")
        elif any(
            value is not None
            for value in (self.security_id, self.share_class_id, self.peer_category_id)
        ):
            raise HoldingsError("cash/derivatives cannot assert equity identity or category")
        object.__setattr__(self, "weight", weight)


def _source_decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HoldingsError(f"{name} must be a canonical exact decimal string")
    parsed = _decimal(value, name)
    canonical = format(parsed, "f")
    if "." in canonical:
        canonical = canonical.rstrip("0").rstrip(".")
    if parsed == 0:
        canonical = "0"
    if value != canonical:
        raise HoldingsError(f"{name} must use canonical decimal spelling")
    return parsed


def _effective_session_for_instant(effective: datetime, session_text: object) -> str:
    session = _canonical_text(session_text, "effective_session")
    try:
        if not is_trading_session(session):
            raise HoldingsError("effective_session must be an NYSE trading session")
        session_date = datetime.fromisoformat(session).date()
        candidates = trading_sessions(session_date, effective.date())
        started = tuple(
            value
            for value in candidates
            if session_open_instant(value.isoformat()) <= effective
        )
    except (ExchangeCalendarError, ValueError) as exc:
        raise HoldingsError("effective_session cannot be proved") from exc
    if not started or started[-1].isoformat() != session:
        raise HoldingsError(
            "effective_session must be the latest NYSE session begun by effective_at"
        )
    return session


def _parse_holdings_source(
    source_bytes: bytes,
) -> tuple[
    str,
    str,
    str,
    str,
    datetime,
    str,
    datetime,
    Decimal,
    tuple[Holding, ...],
]:
    try:
        raw = require_canonical_json_bytes(source_bytes, "holdings source")
        if not isinstance(raw, dict):
            raise HoldingsError("holdings source must be a JSON object")
        require_exact_keys(raw, _HOLDINGS_SOURCE_KEYS, "holdings source")
    except CanonicalEvidenceError as exc:
        raise HoldingsError("holdings source is not canonical evidence") from exc
    if raw["schema"] != _HOLDINGS_SOURCE_SCHEMA:
        raise HoldingsError("holdings source schema is unsupported")
    source_id = _canonical_text(raw["source_id"], "source_id")
    evidence_epoch_id = _canonical_text(
        raw["evidence_epoch_id"], "evidence_epoch_id"
    )
    etf = _canonical_text(raw["etf_security_id"], "etf_security_id")
    source_snapshot_id = _canonical_text(
        raw["source_snapshot_id"], "source_snapshot_id"
    )
    effective = _instant(raw["effective_at"], "effective_at")
    available = _instant(raw["available_at"], "available_at")
    if raw["effective_at"] != effective.isoformat() or raw["available_at"] != available.isoformat():
        raise HoldingsError("holdings source timestamps must use canonical UTC spelling")
    if available < effective:
        raise HoldingsError("holdings cannot be available before effective_at")
    effective_session = _effective_session_for_instant(
        effective, raw["effective_session"]
    )
    declared = _source_decimal(
        raw["declared_total_weight"], "declared_total_weight"
    )
    records = raw["holdings"]
    if not isinstance(records, list) or not records:
        raise HoldingsError("holdings source must contain a non-empty row list")
    holdings: list[Holding] = []
    for index, record in enumerate(records):
        try:
            require_exact_keys(record, _HOLDING_SOURCE_KEYS, f"holdings[{index}]")
        except CanonicalEvidenceError as exc:
            raise HoldingsError("holdings source row fields are not exact") from exc
        try:
            instrument_kind = InstrumentKind(record["instrument_kind"])
            mapping_state = MappingState(record["mapping_state"])
        except (TypeError, ValueError) as exc:
            raise HoldingsError("holdings source row enum is invalid") from exc
        holdings.append(
            Holding(
                position_id=record["position_id"],
                instrument_kind=instrument_kind,
                weight=_source_decimal(record["weight"], f"holdings[{index}].weight"),
                security_id=record["security_id"],
                share_class_id=record["share_class_id"],
                mapping_state=mapping_state,
                peer_category_id=record["peer_category_id"],
            )
        )
    materialized = tuple(sorted(holdings, key=lambda row: row.position_id))
    if tuple(row.position_id for row in holdings) != tuple(
        row.position_id for row in materialized
    ):
        raise HoldingsError("holdings source rows must be canonically position-sorted")
    return (
        source_id,
        evidence_epoch_id,
        etf,
        source_snapshot_id,
        effective,
        effective_session,
        available,
        declared,
        materialized,
    )


def _content_payload(
    *,
    source_id: str,
    evidence_epoch_id: str,
    etf_security_id: str,
    source_snapshot_id: str,
    effective_at: datetime,
    effective_session: str,
    available_at: datetime,
    declared_total_weight: Decimal,
    holdings: tuple[Holding, ...],
    source_hash: str,
) -> dict[str, object]:
    return {
        "schema": _HOLDINGS_SCHEMA,
        "source_id": source_id,
        "evidence_epoch_id": evidence_epoch_id,
        "etf_security_id": etf_security_id,
        "source_snapshot_id": source_snapshot_id,
        "effective_at": effective_at.isoformat(),
        "effective_session": effective_session,
        "available_at": available_at.isoformat(),
        "declared_total_weight": _decimal_text(declared_total_weight),
        "book_tolerance": _decimal_text(HOLDINGS_BOOK_TOLERANCE),
        "source_hash": source_hash,
        "holdings": [
            {
                "position_id": row.position_id,
                "instrument_kind": row.instrument_kind.value,
                "weight": _decimal_text(_decimal(row.weight, "weight")),
                "security_id": row.security_id,
                "share_class_id": row.share_class_id,
                "mapping_state": row.mapping_state.value,
                "peer_category_id": row.peer_category_id,
            }
            for row in holdings
        ],
    }


def _content_sha256(**values: object) -> str:
    payload = json.dumps(
        _content_payload(**values),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclasses.dataclass(frozen=True, init=False)
class HoldingsSnapshot:
    source_bytes: bytes = dataclasses.field(repr=False, compare=False)
    source_id: str
    evidence_epoch_id: str
    etf_security_id: str
    source_snapshot_id: str
    effective_at: str
    effective_session: str
    available_at: str
    declared_total_weight: Decimal
    holdings: tuple[Holding, ...]
    source_hash: str
    content_sha256: str
    _token: object = dataclasses.field(repr=False, compare=False)
    book_tolerance: Decimal = dataclasses.field(
        default=HOLDINGS_BOOK_TOLERANCE, init=False
    )



def _validate_holdings_book(
    declared: Decimal, materialized: tuple[Holding, ...]
) -> None:
    if declared <= 0 or not materialized:
        raise HoldingsError("holdings book and declared weight must be positive")
    ids = [row.position_id for row in materialized]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise HoldingsError("holdings must be uniquely and canonically sorted")
    permanent = [
        (row.security_id, row.share_class_id)
        for row in materialized
        if row.instrument_kind is InstrumentKind.LONG_EQUITY
        and row.mapping_state is MappingState.MAPPED
    ]
    if len(permanent) != len(set(permanent)):
        raise HoldingsError("duplicate permanent security/share-class position")
    with analyst_decimal_context():
        supplied = sum(
            (_decimal(row.weight, "weight") for row in materialized), Decimal("0")
        )
        if abs(declared - Decimal("1")) > HOLDINGS_BOOK_TOLERANCE:
            raise HoldingsError("declared holdings book must reconcile to 100%")
        if abs(supplied - Decimal("1")) > HOLDINGS_BOOK_TOLERANCE:
            raise HoldingsError(
                "supplied holdings must independently reconcile to 100%"
            )
        if abs(supplied - declared) > HOLDINGS_BOOK_TOLERANCE:
            raise HoldingsError(
                "supplied holdings do not reconcile to declared total weight"
            )


def require_verified_holdings_snapshot(value: object) -> HoldingsSnapshot:
    if (
        type(value) is not HoldingsSnapshot
        or getattr(value, "_token", None) is not _VERIFIED_SNAPSHOT_TOKEN
    ):
        raise HoldingsError(
            "HoldingsSnapshot must come from build_verified_holdings_snapshot"
        )
    try:
        source_bytes, source_digest = require_registered_source_bytes(
            ResearchSourceKind.HOLDINGS, value.source_bytes
        )
    except FormulaError as exc:
        raise HoldingsError("holdings source authority is zero-access") from exc
    parsed = _parse_holdings_source(source_bytes)
    (
        source_id,
        evidence_epoch_id,
        etf,
        source_snapshot_id,
        effective,
        effective_session,
        available,
        declared,
        materialized,
    ) = parsed
    _validate_holdings_book(declared, materialized)
    expected_content = _content_sha256(
        source_id=source_id,
        evidence_epoch_id=evidence_epoch_id,
        etf_security_id=etf,
        source_snapshot_id=source_snapshot_id,
        effective_at=effective,
        effective_session=effective_session,
        available_at=available,
        declared_total_weight=declared,
        holdings=materialized,
        source_hash=source_digest,
    )
    expected = (
        source_id,
        evidence_epoch_id,
        etf,
        source_snapshot_id,
        effective.isoformat(),
        effective_session,
        available.isoformat(),
        declared,
        materialized,
        source_digest,
        expected_content,
    )
    actual = (
        value.source_id,
        value.evidence_epoch_id,
        value.etf_security_id,
        value.source_snapshot_id,
        value.effective_at,
        value.effective_session,
        value.available_at,
        value.declared_total_weight,
        value.holdings,
        value.source_hash,
        value.content_sha256,
    )
    if actual != expected:
        raise HoldingsError("holdings snapshot differs from registered source bytes")
    return value


def build_verified_holdings_snapshot(
    *,
    source_bytes: bytes,
) -> HoldingsSnapshot:
    """Build only with future external authority; currently always zero-access."""
    try:
        immutable_source, source_digest = require_registered_source_bytes(
            ResearchSourceKind.HOLDINGS, source_bytes
        )
    except FormulaError as exc:
        raise HoldingsError("holdings source authority is zero-access") from exc
    (
        source_id,
        evidence_epoch_id,
        etf,
        source_snapshot_id,
        effective,
        effective_session,
        available,
        declared,
        materialized,
    ) = _parse_holdings_source(immutable_source)
    _validate_holdings_book(declared, materialized)
    content_sha256 = _content_sha256(
        source_id=source_id,
        evidence_epoch_id=evidence_epoch_id,
        etf_security_id=etf,
        source_snapshot_id=source_snapshot_id,
        effective_at=effective,
        effective_session=effective_session,
        available_at=available,
        declared_total_weight=declared,
        holdings=materialized,
        source_hash=source_digest,
    )
    value = object.__new__(HoldingsSnapshot)
    for name, item in {
        "source_bytes": immutable_source,
        "source_id": source_id,
        "evidence_epoch_id": evidence_epoch_id,
        "etf_security_id": etf,
        "source_snapshot_id": source_snapshot_id,
        "effective_at": effective.isoformat(),
        "effective_session": effective_session,
        "available_at": available.isoformat(),
        "declared_total_weight": declared,
        "holdings": materialized,
        "source_hash": source_digest,
        "content_sha256": content_sha256,
        "_token": _VERIFIED_SNAPSHOT_TOKEN,
        "book_tolerance": HOLDINGS_BOOK_TOLERANCE,
    }.items():
        object.__setattr__(value, name, item)
    return require_verified_holdings_snapshot(value)


@dataclasses.dataclass(frozen=True)
class CoverageResult:
    mapped_weight: Decimal
    denominator_weight: Decimal
    coverage: Decimal
    eligible: bool
    refusal_reason: str | None
    holdings_lag_sessions: int | None


def _complete_candidate_ids(snapshot: HoldingsSnapshot) -> tuple[str, ...]:
    return tuple(
        row.position_id
        for row in snapshot.holdings
        if row.instrument_kind is InstrumentKind.LONG_EQUITY
    )


def _require_complete_candidate_ids(
    snapshot: HoldingsSnapshot, candidate_position_ids: Iterable[str]
) -> tuple[str, ...]:
    candidate_ids = tuple(candidate_position_ids)
    if any(
        not isinstance(value, str) or not value or value != value.strip()
        for value in candidate_ids
    ):
        raise HoldingsError("candidate_position_ids must be canonical non-empty strings")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise HoldingsError("candidate_position_ids contain duplicates")
    expected = _complete_candidate_ids(snapshot)
    if set(candidate_ids) != set(expected) or len(candidate_ids) != len(expected):
        raise HoldingsError(
            "candidate_position_ids must exactly enumerate every long-equity position"
        )
    return candidate_ids


def _decision_session(decision: datetime) -> str:
    session = decision.date().isoformat()
    try:
        if not is_trading_session(session):
            raise HoldingsError("decision_at must fall on an NYSE trading session")
        if decision != session_open_instant(session):
            raise HoldingsError("decision_at must equal the canonical NYSE session open")
    except ExchangeCalendarError as exc:
        raise HoldingsError("decision session cannot be proved") from exc
    return session


def _derived_lag_sessions(snapshot: HoldingsSnapshot, decision_session: str) -> int:
    try:
        effective_date = datetime.fromisoformat(snapshot.effective_session).date()
        decision_date = datetime.fromisoformat(decision_session).date()
        sessions = trading_sessions(effective_date, decision_date)
    except (ExchangeCalendarError, ValueError) as exc:
        raise HoldingsError("holdings lag cannot be proved on the exchange calendar") from exc
    if (
        not sessions
        or sessions[0].isoformat() != snapshot.effective_session
        or sessions[-1].isoformat() != decision_session
    ):
        raise HoldingsError("holdings effective/decision session is not on the NYSE calendar")
    return len(sessions) - 1


def mapped_candidate_coverage(
    snapshot: HoldingsSnapshot,
    *,
    candidate_position_ids: Iterable[str],
    decision_at: str,
    policy: VerifiedAnalystPolicy,
) -> CoverageResult:
    """Coverage over the complete long-equity book, never a caller-selected subset."""
    snapshot = require_verified_holdings_snapshot(snapshot)
    try:
        verified_policy = require_verified_analyst_policy(policy)
    except FormulaError as exc:
        raise HoldingsError("holdings coverage requires verified policy") from exc
    threshold = verified_policy.minimum_mapped_candidate_weight
    maximum_holdings_lag_sessions = verified_policy.maximum_holdings_lag_sessions
    candidate_ids = _require_complete_candidate_ids(snapshot, candidate_position_ids)
    decision = _instant(decision_at, "decision_at")
    decision_session = _decision_session(decision)
    available = _instant(snapshot.available_at, "snapshot.available_at")
    if decision < available:
        return CoverageResult(
            Decimal("0"), Decimal("0"), Decimal("0"), False,
            "holdings_not_yet_available", None,
        )
    lag_sessions = _derived_lag_sessions(snapshot, decision_session)
    if lag_sessions > maximum_holdings_lag_sessions:
        return CoverageResult(
            Decimal("0"), Decimal("0"), Decimal("0"), False,
            "stale_holdings_snapshot", lag_sessions,
        )
    by_id = {row.position_id: row for row in snapshot.holdings}
    selected = [by_id[value] for value in candidate_ids]
    with analyst_decimal_context():
        denominator = sum(
            (_decimal(row.weight, "weight") for row in selected), Decimal("0")
        )
        mapped = sum(
            (
                _decimal(row.weight, "weight")
                for row in selected
                if row.mapping_state is MappingState.MAPPED
            ),
            Decimal("0"),
        )
        if denominator <= 0:
            return CoverageResult(
                mapped, denominator, Decimal("0"), False,
                "zero_candidate_weight", lag_sessions,
            )
        coverage = mapped / denominator
        if not 0 <= coverage <= 1:
            raise HoldingsError("coverage escaped [0,1]")
        # Decide eligibility exactly. ``mapped / denominator`` rounds at the
        # 50-digit context, so a book whose true coverage is just under the
        # threshold can round up to it and pass the 99% gate. Comparing
        # ``mapped`` against ``threshold * denominator`` as exact rationals
        # removes that fail-open direction entirely; ``coverage`` is still
        # reported as the rounded Decimal for diagnostics.
        eligible = Fraction(mapped) >= Fraction(threshold) * Fraction(denominator)
        return CoverageResult(
            mapped_weight=mapped,
            denominator_weight=denominator,
            coverage=coverage,
            eligible=eligible,
            refusal_reason=None if eligible else "insufficient_mapped_candidate_weight",
            holdings_lag_sessions=lag_sessions,
        )


@dataclasses.dataclass(frozen=True, init=False)
class VerifiedHoldingsEvidence:
    snapshot: HoldingsSnapshot = dataclasses.field(repr=False)
    etf_security_id: str
    snapshot_content_sha256: str
    source_sha256: str
    evidence_epoch_id: str
    decision_at: str
    decision_session: str
    policy_sha256: str
    candidate_position_ids: tuple[str, ...]
    maximum_holdings_lag_sessions: int
    minimum_coverage: Decimal
    coverage: Decimal
    holdings_lag_sessions: int | None
    eligible: bool
    refusal_reason: str | None
    _token: object = dataclasses.field(repr=False, compare=False)

def verify_holdings_evidence(
    snapshot: HoldingsSnapshot,
    *,
    decision_at: str,
    policy: VerifiedAnalystPolicy,
) -> VerifiedHoldingsEvidence:
    """Derive immutable portfolio eligibility from a verified complete snapshot."""
    snapshot = require_verified_holdings_snapshot(snapshot)
    try:
        verified_policy = require_verified_analyst_policy(policy)
    except FormulaError as exc:
        raise HoldingsError("holdings evidence requires verified policy") from exc
    candidate_ids = _complete_candidate_ids(snapshot)
    coverage = mapped_candidate_coverage(
        snapshot,
        candidate_position_ids=candidate_ids,
        decision_at=decision_at,
        policy=verified_policy,
    )
    canonical_decision = _instant(decision_at, "decision_at")
    value = object.__new__(VerifiedHoldingsEvidence)
    for name, item in {
        "snapshot": snapshot,
        "etf_security_id": snapshot.etf_security_id,
        "snapshot_content_sha256": snapshot.content_sha256,
        "source_sha256": snapshot.source_hash,
        "evidence_epoch_id": snapshot.evidence_epoch_id,
        "decision_at": canonical_decision.isoformat(),
        "decision_session": _decision_session(canonical_decision),
        "policy_sha256": verified_policy.evidence_sha256,
        "candidate_position_ids": candidate_ids,
        "maximum_holdings_lag_sessions": verified_policy.maximum_holdings_lag_sessions,
        "minimum_coverage": verified_policy.minimum_mapped_candidate_weight,
        "coverage": coverage.coverage,
        "holdings_lag_sessions": coverage.holdings_lag_sessions,
        "eligible": coverage.eligible,
        "refusal_reason": coverage.refusal_reason,
        "_token": _VERIFIED_EVIDENCE_TOKEN,
    }.items():
        object.__setattr__(value, name, item)
    return require_verified_holdings_evidence(value, policy=verified_policy)


def require_verified_holdings_evidence(
    value: object, *, policy: VerifiedAnalystPolicy
) -> VerifiedHoldingsEvidence:
    if (
        type(value) is not VerifiedHoldingsEvidence
        or value._token is not _VERIFIED_EVIDENCE_TOKEN
    ):
        raise HoldingsError("portfolio eligibility requires verified holdings evidence")
    snapshot = require_verified_holdings_snapshot(value.snapshot)
    try:
        verified_policy = require_verified_analyst_policy(policy)
    except FormulaError as exc:
        raise HoldingsError("holdings evidence requires verified policy") from exc
    expected = mapped_candidate_coverage(
        snapshot,
        candidate_position_ids=value.candidate_position_ids,
        decision_at=value.decision_at,
        policy=verified_policy,
    )
    if (
        value.maximum_holdings_lag_sessions
        != verified_policy.maximum_holdings_lag_sessions
        or value.minimum_coverage
        != verified_policy.minimum_mapped_candidate_weight
        or value.policy_sha256 != verified_policy.evidence_sha256
        or value.etf_security_id != snapshot.etf_security_id
        or value.snapshot_content_sha256 != snapshot.content_sha256
        or value.source_sha256 != snapshot.source_hash
        or value.evidence_epoch_id != snapshot.evidence_epoch_id
        or value.decision_session != _decision_session(
            _instant(value.decision_at, "decision_at")
        )
        or value.coverage != expected.coverage
        or value.holdings_lag_sessions != expected.holdings_lag_sessions
        or value.eligible is not expected.eligible
        or value.refusal_reason != expected.refusal_reason
    ):
        raise HoldingsError("verified holdings evidence no longer matches its snapshot")
    return value


@dataclasses.dataclass(frozen=True)
class StockScoreDatasetIdentity:
    dataset_id: str
    normalization_result_sha256: str
    snapshot_id: str
    snapshot_manifest_sha256: str
    normalizer_config_sha256: str
    normalizer_code_sha256: str
    evidence_epoch_id: str
    build_recipe_id: str
    build_recipe_sha256: str
    producing_commit: str
    producing_tree: str
    events_sha256: str
    refusals_sha256: str


@dataclasses.dataclass(frozen=True)
class StockScoreDerivationIdentity:
    derivation_id: str
    derivation_config_sha256: str
    derivation_code_sha256: str
    producing_commit: str
    producing_tree: str


def _parse_stock_score_source(
    source_bytes: bytes, *, policy: VerifiedAnalystPolicy
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    StockScoreDatasetIdentity,
    StockScoreDerivationIdentity,
    tuple[SignalObservation, ...],
]:
    try:
        raw = require_canonical_json_bytes(source_bytes, "stock-score source")
        if not isinstance(raw, dict):
            raise HoldingsError("stock-score source must be a JSON object")
        require_exact_keys(raw, _STOCK_SCORE_SOURCE_KEYS, "stock-score source")
        require_exact_keys(
            raw["normalized_dataset"],
            _STOCK_SCORE_DATASET_KEYS,
            "stock-score normalized_dataset",
        )
        require_exact_keys(
            raw["derivation"],
            _STOCK_SCORE_DERIVATION_KEYS,
            "stock-score derivation",
        )
    except CanonicalEvidenceError as exc:
        raise HoldingsError("stock-score source is not canonical evidence") from exc
    if raw["schema"] != _STOCK_SCORE_SOURCE_SCHEMA:
        raise HoldingsError("stock-score source schema is unsupported")
    try:
        verified_policy = require_verified_analyst_policy(policy)
    except FormulaError as exc:
        raise HoldingsError("stock-score source requires verified policy") from exc
    source_id = _canonical_text(raw["source_id"], "stock-score source_id")
    artifact_id = _canonical_text(
        raw["score_artifact_id"], "score_artifact_id"
    )
    epoch = _canonical_text(raw["evidence_epoch_id"], "evidence_epoch_id")
    policy_sha = _sha256(raw["policy_sha256"], "stock-score policy_sha256")
    if policy_sha != verified_policy.evidence_sha256:
        raise HoldingsError("stock-score artifact belongs to another policy")
    derived = _instant(raw["derived_at"], "stock-score derived_at")
    available = _instant(raw["available_at"], "stock-score available_at")
    decision = _instant(raw["decision_at"], "stock-score decision_at")
    times = (derived.isoformat(), available.isoformat(), decision.isoformat())
    if (raw["derived_at"], raw["available_at"], raw["decision_at"]) != times:
        raise HoldingsError("stock-score timestamps must use canonical UTC spelling")
    if not derived <= available <= decision:
        raise HoldingsError(
            "stock-score artifact must satisfy derived_at <= available_at <= decision_at"
        )

    dataset_raw = raw["normalized_dataset"]
    dataset = StockScoreDatasetIdentity(
        dataset_id=_canonical_text(dataset_raw["dataset_id"], "dataset_id"),
        normalization_result_sha256=_sha256(
            dataset_raw["normalization_result_sha256"],
            "normalization_result_sha256",
        ),
        snapshot_id=_canonical_text(dataset_raw["snapshot_id"], "snapshot_id"),
        snapshot_manifest_sha256=_sha256(
            dataset_raw["snapshot_manifest_sha256"],
            "snapshot_manifest_sha256",
        ),
        normalizer_config_sha256=_sha256(
            dataset_raw["normalizer_config_sha256"],
            "normalizer_config_sha256",
        ),
        normalizer_code_sha256=_sha256(
            dataset_raw["normalizer_code_sha256"], "normalizer_code_sha256"
        ),
        evidence_epoch_id=_canonical_text(
            dataset_raw["evidence_epoch_id"], "dataset evidence_epoch_id"
        ),
        build_recipe_id=_canonical_text(
            dataset_raw["build_recipe_id"], "build_recipe_id"
        ),
        build_recipe_sha256=_sha256(
            dataset_raw["build_recipe_sha256"], "build_recipe_sha256"
        ),
        producing_commit=_git_object(
            dataset_raw["producing_commit"], "dataset producing_commit"
        ),
        producing_tree=_git_object(
            dataset_raw["producing_tree"], "dataset producing_tree"
        ),
        events_sha256=_sha256(dataset_raw["events_sha256"], "events_sha256"),
        refusals_sha256=_sha256(
            dataset_raw["refusals_sha256"], "refusals_sha256"
        ),
    )
    if dataset.dataset_id not in verified_policy.authorized_normalized_dataset_ids:
        raise HoldingsError(
            "stock-score dataset is not authorized by the reviewed policy"
        )
    if dataset.evidence_epoch_id != epoch:
        raise HoldingsError(
            "stock-score and normalized dataset use different evidence epochs"
        )
    derivation_raw = raw["derivation"]
    derivation = StockScoreDerivationIdentity(
        derivation_id=_canonical_text(
            derivation_raw["derivation_id"], "derivation_id"
        ),
        derivation_config_sha256=_sha256(
            derivation_raw["derivation_config_sha256"],
            "derivation_config_sha256",
        ),
        derivation_code_sha256=_sha256(
            derivation_raw["derivation_code_sha256"],
            "derivation_code_sha256",
        ),
        producing_commit=_git_object(
            derivation_raw["producing_commit"], "derivation producing_commit"
        ),
        producing_tree=_git_object(
            derivation_raw["producing_tree"], "derivation producing_tree"
        ),
    )

    records = raw["scores"]
    if not isinstance(records, list) or not records:
        raise HoldingsError("stock-score artifact must contain score records")
    observations: list[SignalObservation] = []
    for index, record in enumerate(records):
        try:
            require_exact_keys(
                record, _STOCK_SCORE_RECORD_KEYS, f"scores[{index}]"
            )
        except CanonicalEvidenceError as exc:
            raise HoldingsError("stock-score record fields are not exact") from exc
        security_id = _canonical_text(
            record["security_id"], f"scores[{index}].security_id"
        )
        try:
            state = ObservationState(record["state"])
        except (TypeError, ValueError) as exc:
            raise HoldingsError("stock-score observation state is invalid") from exc
        if state in {ObservationState.MISSING, ObservationState.INVALID}:
            raise HoldingsError(
                "missing or invalid observations refuse the score artifact"
            )
        if state is ObservationState.STRUCTURAL_ZERO:
            if record["value"] is not None:
                raise HoldingsError(
                    "structural-zero stock-score records require null value"
                )
            observation = SignalObservation(security_id, state, None)
        else:
            value = _source_decimal(
                record["value"], f"scores[{index}].value"
            )
            if value == 0:
                raise HoldingsError(
                    "signal stock-score records require a nonzero value"
                )
            if abs(value) > verified_policy.score_clip:
                raise HoldingsError(
                    "stock-score record exceeds the verified normalization clip"
                )
            observation = SignalObservation(security_id, state, value)
        observations.append(observation)
    ordered = tuple(sorted(observations, key=lambda row: row.security_id))
    if tuple(observations) != ordered or len(ordered) != len(
        {row.security_id for row in ordered}
    ):
        raise HoldingsError(
            "stock-score records must be uniquely and canonically security-sorted"
        )
    return (
        source_id,
        artifact_id,
        epoch,
        policy_sha,
        *times,
        dataset,
        derivation,
        ordered,
    )


@dataclasses.dataclass(frozen=True, init=False)
class VerifiedStockScoreEvidence:
    """Authenticated derived-score artifact; this does not compute scores."""

    source_bytes: bytes = dataclasses.field(repr=False, compare=False)
    source_sha256: str
    source_id: str
    score_artifact_id: str
    evidence_epoch_id: str
    policy_sha256: str
    derived_at: str
    available_at: str
    decision_at: str
    normalized_dataset: StockScoreDatasetIdentity
    derivation: StockScoreDerivationIdentity
    observations: tuple[SignalObservation, ...]
    _token: object = dataclasses.field(repr=False, compare=False)


def _forget_stock_score_authority(
    identity: int, reference: weakref.ReferenceType["VerifiedStockScoreEvidence"]
) -> None:
    with _STOCK_SCORE_AUTHORITIES_LOCK:
        registered = _STOCK_SCORE_AUTHORITIES.get(identity)
        if registered is not None and registered[0] is reference:
            _STOCK_SCORE_AUTHORITIES.pop(identity, None)


def _register_stock_score_authority(value: VerifiedStockScoreEvidence) -> None:
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_stock_score_authority(key, ref)
    )
    with _STOCK_SCORE_AUTHORITIES_LOCK:
        _STOCK_SCORE_AUTHORITIES[identity] = (reference, value.source_sha256)


def build_verified_stock_score_evidence(
    *, source_bytes: bytes, policy: VerifiedAnalystPolicy
) -> VerifiedStockScoreEvidence:
    """Refuse until a reviewed external score-source authority exists."""
    try:
        verified_policy = require_verified_analyst_policy(policy)
        immutable_source, source_digest = require_registered_source_bytes(
            ResearchSourceKind.STOCK_SCORE, source_bytes
        )
    except FormulaError as exc:
        raise HoldingsError(
            "stock-score source authority is zero-access"
        ) from exc
    parsed = _parse_stock_score_source(
        immutable_source, policy=verified_policy
    )
    names = (
        "source_id",
        "score_artifact_id",
        "evidence_epoch_id",
        "policy_sha256",
        "derived_at",
        "available_at",
        "decision_at",
        "normalized_dataset",
        "derivation",
        "observations",
    )
    value = object.__new__(VerifiedStockScoreEvidence)
    for name, item in {
        "source_bytes": immutable_source,
        "source_sha256": source_digest,
        **dict(zip(names, parsed, strict=True)),
        "_token": _VERIFIED_STOCK_SCORE_TOKEN,
    }.items():
        object.__setattr__(value, name, item)
    _register_stock_score_authority(value)
    return require_verified_stock_score_evidence(value, policy=verified_policy)


def require_verified_stock_score_evidence(
    value: object, *, policy: VerifiedAnalystPolicy
) -> VerifiedStockScoreEvidence:
    if (
        type(value) is not VerifiedStockScoreEvidence
        or getattr(value, "_token", None) is not _VERIFIED_STOCK_SCORE_TOKEN
    ):
        raise HoldingsError(
            "weighted score requires loader-authenticated stock-score evidence"
        )
    with _STOCK_SCORE_AUTHORITIES_LOCK:
        authority = _STOCK_SCORE_AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != value.source_sha256
    ):
        raise HoldingsError(
            "stock-score evidence identity is not loader-authenticated"
        )
    try:
        verified_policy = require_verified_analyst_policy(policy)
        source_bytes, source_digest = require_registered_source_bytes(
            ResearchSourceKind.STOCK_SCORE, value.source_bytes
        )
    except FormulaError as exc:
        raise HoldingsError(
            "stock-score source authority is zero-access"
        ) from exc
    parsed = _parse_stock_score_source(source_bytes, policy=verified_policy)
    actual = (
        value.source_id,
        value.score_artifact_id,
        value.evidence_epoch_id,
        value.policy_sha256,
        value.derived_at,
        value.available_at,
        value.decision_at,
        value.normalized_dataset,
        value.derivation,
        value.observations,
    )
    if value.source_sha256 != source_digest or parsed != actual:
        raise HoldingsError(
            "stock-score evidence differs from its registered source artifact"
        )
    return value


def weighted_stock_score(
    holdings_evidence: VerifiedHoldingsEvidence,
    *,
    stock_score_evidence: VerifiedStockScoreEvidence,
    policy: VerifiedAnalystPolicy,
) -> Decimal:
    """Aggregate scores only from authenticated, current holdings evidence.

    The evidence constructor fixes the complete candidate book, decision instant,
    one-session lag ceiling, and 99% mapping threshold.  Accepting those values
    again here would create a weaker caller-configurable path around the portfolio
    eligibility contract.
    """
    evidence = require_verified_holdings_evidence(holdings_evidence, policy=policy)
    scores = require_verified_stock_score_evidence(
        stock_score_evidence, policy=policy
    )
    if not evidence.eligible:
        raise HoldingsError(evidence.refusal_reason or "coverage unavailable")
    if (
        scores.policy_sha256 != evidence.policy_sha256
        or scores.decision_at != evidence.decision_at
        or scores.evidence_epoch_id != evidence.evidence_epoch_id
    ):
        raise HoldingsError(
            "stock-score and holdings evidence must share policy, decision, and epoch"
        )
    snapshot = evidence.snapshot
    materialized_candidates = evidence.candidate_position_ids
    by_id = {row.position_id: row for row in snapshot.holdings}
    materialized_scores = {
        observation.security_id: observation for observation in scores.observations
    }
    mapped_security_ids = {
        by_id[value].security_id
        for value in materialized_candidates
        if by_id[value].mapping_state is MappingState.MAPPED
    }
    if set(materialized_scores) != mapped_security_ids:
        raise HoldingsError(
            "stock_scores must exactly cover every mapped holdings security"
        )
    for security_id, observation in materialized_scores.items():
        if type(observation) is not SignalObservation or observation.security_id != security_id:
            raise HoldingsError("stock score must be its matching SignalObservation")
        if observation.state in {ObservationState.MISSING, ObservationState.INVALID}:
            raise HoldingsError(
                "missing or invalid mapped stock observations refuse ETF scoring"
            )
    with analyst_decimal_context():
        weighted = Decimal("0")
        mapped_weight = Decimal("0")
        for position_id in sorted(materialized_candidates):
            row = by_id[position_id]
            if row.mapping_state is not MappingState.MAPPED:
                continue
            observation = materialized_scores[row.security_id]
            score = (
                Decimal("0")
                if observation.state is ObservationState.STRUCTURAL_ZERO
                else _decimal(observation.value, "stock_score")
            )
            weight = _decimal(row.weight, "weight")
            weighted += weight * score
            mapped_weight += weight
        if mapped_weight <= 0:
            raise HoldingsError("mapped holdings weight vanished")
        return weighted / mapped_weight
