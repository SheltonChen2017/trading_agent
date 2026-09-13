"""Offline production-truth gate for the Analyst Revisions V2 scorer.

The production scorer must not accept a caller-shaped security/session sample.
This module authenticates the complete terminal projection of a reviewed
eligible-universe artifact over the exact six-fold session geometry.  Each
universe member has exactly one accepted or named-refused terminal, each
session has a count and Merkle root, and the projection is tied to the source
artifact that produced it.

``q_data`` is also closed here.  Callers provide the three underlying,
content-addressed diagnostics, never the aggregate.  The aggregate is the
exact conservative minimum of timestamp quality, firm-label mapping quality,
and security/entity mapping quality.  Invalid timing, ontology, or identity
still belongs in a named refusal; a fractional diagnostic cannot make invalid
evidence admissible.

This module is deliberately pure.  It has no file, provider, credential,
QuantConnect, Object Store, price, return, outcome, deployment, order, or
trading capability.
"""
from __future__ import annotations

import dataclasses
import threading
import weakref
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from data.exchange_calendar import (
    ExchangeCalendarError,
    trading_sessions,
)

from .accepted_risk_input_pair import AcceptedRiskInputPair
from .canonical import (
    canonical_json_bytes,
    format_utc_timestamp,
    parse_date,
    parse_utc_timestamp,
    require_exact_bool,
    require_identifier,
    require_int,
    require_sha256,
    sha256_bytes,
)
from .production_input_pipeline import (
    DataQualityEvidence,
    EvidenceSourceKind,
    ProductionEvidenceAuthority,
    ProductionInputError,
    ProductionRowEvidence,
    require_production_evidence_authority,
)
from .preopen_control_acquisition import (
    PreopenControlAcquisitionError,
    PreopenControlAcquisitionReceipt,
    acquisition_q_data_measurement_projection_record,
    require_reviewed_preopen_control_acquisition_receipt,
)
from .production_evidence_acquisition import (
    ProductionEvidenceAcquisitionError,
    ProductionEvidenceAcquisitionReceipt,
    require_production_evidence_acquisition_receipt,
)
from .production_scoring import (
    FORMAL_FOLD_BOUNDARIES,
    HISTORY_START,
    EligibleSecuritySession,
    EligibleSecuritySessionRefusal,
)


class ProductionTruthError(ValueError):
    """The production-truth projection or one of its bindings is invalid."""


TRUTH_SCHEMA = "arv2-production-truth-artifact-v1"
TRUTH_CONTRACT_SCHEMA = "arv2-production-truth-contract-v1"
QUALITY_METHOD_ID = "arv2-qdata-conservative-min-v1"
QUALITY_MEASUREMENT_PROJECTION_SCHEMA = (
    "arv2-qdata-physical-measurement-projection-v1"
)
UNIVERSE_TERMINAL_PROJECTION_SCHEMA = "arv2-universe-terminal-projection-v1"
SESSION_SUMMARY_SCHEMA = "arv2-universe-session-summary-v1"
QUALITY_COMPONENT_PROJECTION_SCHEMA = "arv2-c2-quality-component-projection-v1"


class TruthSourceKind(str, Enum):
    ACCEPTED_RISK_CAPTURE = "accepted_risk_capture"
    ELIGIBLE_UNIVERSE = "eligible_universe"
    SECURITY_MASTER = "security_master"
    FIRM_ONTOLOGY = "firm_ontology"
    COMMON_EVENT = "common_event"
    SECTOR_CLASSIFICATION = "sector_classification"
    PREOPEN_CONTROL = "preopen_control"
    DATA_QUALITY = "data_quality"


class QualityComponentKind(str, Enum):
    TIMESTAMP_QUALITY = "timestamp_quality"
    FIRM_LABEL_MAPPING_QUALITY = "firm_label_mapping_quality"
    SECURITY_ENTITY_MAPPING_QUALITY = "security_entity_mapping_quality"


_SOURCE_ORDER = tuple(TruthSourceKind)
_QUALITY_COMPONENT_ORDER = tuple(QualityComponentKind)
_C2_SOURCE_KIND = {
    TruthSourceKind.SECURITY_MASTER: EvidenceSourceKind.SECURITY_MASTER,
    TruthSourceKind.FIRM_ONTOLOGY: EvidenceSourceKind.FIRM_ONTOLOGY,
    TruthSourceKind.COMMON_EVENT: EvidenceSourceKind.COMMON_EVENT,
    TruthSourceKind.SECTOR_CLASSIFICATION: EvidenceSourceKind.SECTOR_CLASSIFICATION,
    TruthSourceKind.PREOPEN_CONTROL: EvidenceSourceKind.PREOPEN_CONTROL,
    TruthSourceKind.DATA_QUALITY: EvidenceSourceKind.DATA_QUALITY,
}


def _exact_string(value: object, name: str) -> str:
    if type(value) is not str:
        raise ProductionTruthError(f"{name} must be an exact string")
    return value


def _exact_decimal(value: object, name: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise ProductionTruthError(f"{name} must be an exact finite Decimal")
    if value < Decimal(0) or value > Decimal(1):
        raise ProductionTruthError(f"{name} must be in [0,1]")
    return value


def _decimal_text(value: Decimal) -> str:
    return "0" if value == 0 else format(value, "f")


def _half_open_sessions(start: str, end_exclusive: str) -> tuple[str, ...]:
    first = parse_date(start, "fold interval start")
    end = parse_date(end_exclusive, "fold interval end")
    try:
        values = trading_sessions(first, end - timedelta(days=1))
    except ExchangeCalendarError as exc:
        raise ProductionTruthError("formal fold session geometry cannot be resolved") from exc
    return tuple(item.isoformat() for item in values)


def _formal_session_geometry() -> tuple[str, ...]:
    values: set[str] = set()
    for (
        _fold_id,
        train_start,
        train_end,
        validation_start,
        validation_end,
        test_start,
        test_end,
    ) in FORMAL_FOLD_BOUNDARIES:
        values.update(_half_open_sessions(train_start, train_end))
        values.update(_half_open_sessions(validation_start, validation_end))
        values.update(_half_open_sessions(test_start, test_end))
    result = tuple(sorted(values))
    if not result or result[0] != HISTORY_START or result[-1][:4] != "2025":
        raise ProductionTruthError("formal truth geometry escaped reviewed 2013..2025 bounds")
    return result


FORMAL_SESSION_GEOMETRY = _formal_session_geometry()
FORMAL_SESSION_GEOMETRY_SHA256 = sha256_bytes(
    canonical_json_bytes(
        {
            "fold_boundaries": [list(item) for item in FORMAL_FOLD_BOUNDARIES],
            "sessions": list(FORMAL_SESSION_GEOMETRY),
        }
    )
)


def production_truth_contract_record() -> dict[str, Any]:
    return {
        "schema": TRUTH_CONTRACT_SCHEMA,
        "history_start": HISTORY_START,
        "last_calendar_year": 2025,
        "fold_boundaries": [list(item) for item in FORMAL_FOLD_BOUNDARIES],
        "session_count": len(FORMAL_SESSION_GEOMETRY),
        "session_geometry_sha256": FORMAL_SESSION_GEOMETRY_SHA256,
        "terminal_rule": "each_declared_universe_security_session_exactly_accepted_or_named_refused",
        "session_commitment": "accepted_count_refusal_count_terminal_count_and_merkle_root",
        "universe_projection_binding": "exact_content_root_in_reviewed_source_binding",
        "universe_acquisition_authority": (
            "opaque_independently_reviewed_preopen_QC_acquisition_receipt_with_"
            "exact_source_bytes_and_per_session_terminal_commitments"
        ),
        "q_data": {
            "components": [item.value for item in _QUALITY_COMPONENT_ORDER],
            "formula": "min(timestamp_quality,firm_label_mapping_quality,security_entity_mapping_quality)",
            "caller_supplied_aggregate": False,
            "invalid_evidence_soft_admitted": False,
            "method_id": QUALITY_METHOD_ID,
            "physical_authority": (
                "exact_same_key_measurement_projection_in_reviewed_preopen_receipt"
            ),
        },
        "c2_binding": (
            "exact_physically_reviewed_content_addressed_evidence_package_receipt"
        ),
        "capabilities": {
            "provider_access": False,
            "credential_access": False,
            "filesystem_access": False,
            "quantconnect_access": False,
            "object_store_access": False,
            "price_access": False,
            "outcome_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


TRUTH_CONTRACT_BYTES = canonical_json_bytes(production_truth_contract_record())
TRUTH_CONTRACT_SHA256 = sha256_bytes(TRUTH_CONTRACT_BYTES)
TRUTH_CONTRACT_ID = f"arv2-production-truth-contract-{TRUTH_CONTRACT_SHA256[:16]}"


def render_production_truth_contract_bytes() -> bytes:
    return bytes(TRUTH_CONTRACT_BYTES)


@dataclasses.dataclass(frozen=True)
class ProductionTruthSourceBinding:
    kind: TruthSourceKind
    artifact_id: str
    artifact_sha256: str
    projection_sha256: str | None
    reviewed: bool
    point_in_time: bool
    accepted_risk_non_pristine: bool

    def __post_init__(self) -> None:
        if type(self.kind) is not TruthSourceKind:
            raise ProductionTruthError("truth source kind has wrong type")
        _exact_string(self.artifact_id, "artifact_id")
        _exact_string(self.artifact_sha256, "artifact_sha256")
        require_identifier(self.artifact_id, "artifact_id")
        require_sha256(self.artifact_sha256, "artifact_sha256")
        if self.projection_sha256 is not None:
            _exact_string(self.projection_sha256, "projection_sha256")
            require_sha256(self.projection_sha256, "projection_sha256")
        require_exact_bool(self.reviewed, "reviewed")
        require_exact_bool(self.point_in_time, "point_in_time")
        require_exact_bool(
            self.accepted_risk_non_pristine, "accepted_risk_non_pristine"
        )
        if not self.reviewed:
            raise ProductionTruthError("production truth source must be reviewed")
        if self.kind is TruthSourceKind.ACCEPTED_RISK_CAPTURE:
            if self.point_in_time or not self.accepted_risk_non_pristine:
                raise ProductionTruthError("accepted-risk capture binding flags are not exact")
        elif not self.point_in_time or self.accepted_risk_non_pristine:
            raise ProductionTruthError("production truth source must be pristine point-in-time")
        if (self.kind is TruthSourceKind.ELIGIBLE_UNIVERSE) != (
            self.projection_sha256 is not None
        ):
            raise ProductionTruthError("only eligible-universe source binds a terminal projection")

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
            "projection_sha256": self.projection_sha256,
            "reviewed": self.reviewed,
            "point_in_time": self.point_in_time,
            "accepted_risk_non_pristine": self.accepted_risk_non_pristine,
        }


@dataclasses.dataclass(frozen=True)
class QualityComponentEvidence:
    kind: QualityComponentKind
    value: Decimal
    source_id: str
    source_sha256: str
    payload_sha256: str
    available_at: str
    point_in_time: bool
    accepted_risk_non_pristine: bool
    evidence_sha256: str

    def __post_init__(self) -> None:
        if type(self.kind) is not QualityComponentKind:
            raise ProductionTruthError("quality component kind has wrong type")
        _exact_decimal(self.value, self.kind.value)
        for name in (
            "source_id",
            "source_sha256",
            "payload_sha256",
            "available_at",
            "evidence_sha256",
        ):
            _exact_string(getattr(self, name), name)
        require_identifier(self.source_id, "source_id")
        for name in ("source_sha256", "payload_sha256", "evidence_sha256"):
            require_sha256(getattr(self, name), name)
        parse_utc_timestamp(self.available_at, "quality component available_at")
        require_exact_bool(self.point_in_time, "point_in_time")
        require_exact_bool(
            self.accepted_risk_non_pristine, "accepted_risk_non_pristine"
        )
        if self.kind is QualityComponentKind.TIMESTAMP_QUALITY:
            if self.point_in_time or not self.accepted_risk_non_pristine:
                raise ProductionTruthError("timestamp-quality accepted-risk flags are not exact")
        elif not self.point_in_time or self.accepted_risk_non_pristine:
            raise ProductionTruthError("mapping-quality component must be point-in-time")
        if self.evidence_sha256 != sha256_bytes(canonical_json_bytes(self.semantic_record())):
            raise ProductionTruthError("quality component hash is not content-derived")

    def semantic_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "value": _decimal_text(self.value),
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "payload_sha256": self.payload_sha256,
            "available_at": self.available_at,
            "point_in_time": self.point_in_time,
            "accepted_risk_non_pristine": self.accepted_risk_non_pristine,
        }

    def to_record(self) -> dict[str, Any]:
        return {**self.semantic_record(), "evidence_sha256": self.evidence_sha256}


def build_quality_component_evidence(
    *,
    kind: QualityComponentKind,
    value: Decimal,
    source_id: str,
    source_sha256: str,
    payload_sha256: str,
    available_at: str,
) -> QualityComponentEvidence:
    if type(kind) is not QualityComponentKind:
        raise ProductionTruthError("quality component kind has wrong type")
    _exact_decimal(value, kind.value)
    for name, item in (
        ("source_id", source_id),
        ("source_sha256", source_sha256),
        ("payload_sha256", payload_sha256),
        ("available_at", available_at),
    ):
        _exact_string(item, name)
    point_in_time = kind is not QualityComponentKind.TIMESTAMP_QUALITY
    accepted_risk = kind is QualityComponentKind.TIMESTAMP_QUALITY
    semantic = {
        "kind": kind.value,
        "value": _decimal_text(value),
        "source_id": source_id,
        "source_sha256": source_sha256,
        "payload_sha256": payload_sha256,
        "available_at": available_at,
        "point_in_time": point_in_time,
        "accepted_risk_non_pristine": accepted_risk,
    }
    return QualityComponentEvidence(
        kind=kind,
        value=value,
        source_id=source_id,
        source_sha256=source_sha256,
        payload_sha256=payload_sha256,
        available_at=available_at,
        point_in_time=point_in_time,
        accepted_risk_non_pristine=accepted_risk,
        evidence_sha256=sha256_bytes(canonical_json_bytes(semantic)),
    )


@dataclasses.dataclass(frozen=True, init=False)
class DerivedDataQualityEvidence:
    security_id: str
    measured_session: str
    source_id: str
    source_sha256: str
    components: tuple[QualityComponentEvidence, ...]
    measurement_method_id: str
    q_data: Decimal
    available_at: str
    evidence_sha256: str
    point_in_time: bool

    def semantic_record(self) -> dict[str, Any]:
        return {
            "security_id": self.security_id,
            "measured_session": self.measured_session,
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "components": [item.to_record() for item in self.components],
            "measurement_method_id": self.measurement_method_id,
            "q_data": _decimal_text(self.q_data),
            "available_at": self.available_at,
            "point_in_time": self.point_in_time,
        }

    def to_record(self) -> dict[str, Any]:
        return {**self.semantic_record(), "evidence_sha256": self.evidence_sha256}


def _validate_derived_quality(value: DerivedDataQualityEvidence) -> None:
    if type(value) is not DerivedDataQualityEvidence:
        raise ProductionTruthError("derived q_data evidence has wrong type")
    for name in (
        "security_id",
        "measured_session",
        "source_id",
        "source_sha256",
        "measurement_method_id",
        "available_at",
        "evidence_sha256",
    ):
        _exact_string(getattr(value, name), name)
    require_identifier(value.security_id, "security_id")
    require_identifier(value.source_id, "source_id")
    parse_date(value.measured_session, "measured_session")
    require_sha256(value.source_sha256, "source_sha256")
    require_sha256(value.evidence_sha256, "evidence_sha256")
    if value.measurement_method_id != QUALITY_METHOD_ID:
        raise ProductionTruthError("q_data measurement method is not frozen")
    if type(value.components) is not tuple or tuple(
        item.kind for item in value.components
    ) != _QUALITY_COMPONENT_ORDER:
        raise ProductionTruthError("q_data components are missing, duplicated, or reordered")
    for item in value.components:
        item.__post_init__()
    expected_q = min(item.value for item in value.components)
    if type(value.q_data) is not Decimal or value.q_data != expected_q:
        raise ProductionTruthError("q_data is not the conservative component minimum")
    expected_available = format_utc_timestamp(
        max(parse_utc_timestamp(item.available_at, "component available_at") for item in value.components)
    )
    if value.available_at != expected_available:
        raise ProductionTruthError("q_data availability is not the latest component clock")
    # The enclosing accepted terminal proves this clock is strictly before the
    # exchange open. C2 independently proves it against its decision cutoff.
    require_exact_bool(value.point_in_time, "point_in_time")
    if not value.point_in_time:
        raise ProductionTruthError("derived q_data must be point-in-time measured")
    if value.evidence_sha256 != sha256_bytes(canonical_json_bytes(value.semantic_record())):
        raise ProductionTruthError("derived q_data hash is not content-derived")


def build_derived_data_quality_evidence(
    *,
    security_id: str,
    measured_session: str,
    source_id: str,
    source_sha256: str,
    components: tuple[QualityComponentEvidence, ...],
) -> DerivedDataQualityEvidence:
    _exact_string(security_id, "security_id")
    _exact_string(measured_session, "measured_session")
    _exact_string(source_id, "source_id")
    _exact_string(source_sha256, "source_sha256")
    if type(components) is not tuple or tuple(item.kind for item in components) != (
        _QUALITY_COMPONENT_ORDER
    ):
        raise ProductionTruthError("q_data components are missing, duplicated, or reordered")
    for item in components:
        item.__post_init__()
    quality = min(item.value for item in components)
    available_at = format_utc_timestamp(
        max(parse_utc_timestamp(item.available_at, "component available_at") for item in components)
    )
    values: dict[str, object] = {
        "security_id": security_id,
        "measured_session": measured_session,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "components": components,
        "measurement_method_id": QUALITY_METHOD_ID,
        "q_data": quality,
        "available_at": available_at,
        "point_in_time": True,
    }
    semantic = {
        "security_id": security_id,
        "measured_session": measured_session,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "components": [item.to_record() for item in components],
        "measurement_method_id": QUALITY_METHOD_ID,
        "q_data": _decimal_text(quality),
        "available_at": available_at,
        "point_in_time": True,
    }
    result = object.__new__(DerivedDataQualityEvidence)
    for name, item in values.items():
        object.__setattr__(result, name, item)
    object.__setattr__(result, "evidence_sha256", sha256_bytes(canonical_json_bytes(semantic)))
    _validate_derived_quality(result)
    return result


def quality_measurement_projection_sha256(
    measurements: tuple[DerivedDataQualityEvidence, ...],
) -> str:
    """Commit the exact canonical quality evidence for every accepted key.

    This projection is shared with the physical pre-open acquisition boundary.
    It prevents a caller from substituting self-consistent component values or
    payload hashes after the reviewed output terminals were produced.
    """

    if type(measurements) is not tuple or any(
        type(item) is not DerivedDataQualityEvidence for item in measurements
    ):
        raise ProductionTruthError("q_data measurements have wrong topology")
    for item in measurements:
        _validate_derived_quality(item)
    keys = tuple((item.measured_session, item.security_id) for item in measurements)
    if keys != tuple(sorted(set(keys))):
        raise ProductionTruthError("q_data measurements repeat or are not canonical")
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": QUALITY_MEASUREMENT_PROJECTION_SCHEMA,
                "measurements": [item.to_record() for item in measurements],
            }
        )
    )


def project_c2_data_quality_evidence(
    value: DerivedDataQualityEvidence,
) -> DataQualityEvidence:
    """Project one derived measurement into C2's narrower evidence record."""

    _validate_derived_quality(value)
    return DataQualityEvidence(
        security_id=value.security_id,
        measured_session=value.measured_session,
        source_id=value.source_id,
        source_sha256=value.source_sha256,
        evidence_sha256=value.evidence_sha256,
        available_at=value.available_at,
        measurement_method_id=value.measurement_method_id,
        q_data=value.q_data,
        point_in_time=True,
    )


@dataclasses.dataclass(frozen=True)
class C2QualityComponentProjection:
    security_id: str
    measured_session: str
    timestamp_payload_sha256: str
    firm_label_payload_sha256: str
    security_entity_payload_sha256: str

    def __post_init__(self) -> None:
        _exact_string(self.security_id, "security_id")
        _exact_string(self.measured_session, "measured_session")
        require_identifier(self.security_id, "security_id")
        parse_date(self.measured_session, "measured_session")
        for name in (
            "timestamp_payload_sha256",
            "firm_label_payload_sha256",
            "security_entity_payload_sha256",
        ):
            _exact_string(getattr(self, name), name)
            require_sha256(getattr(self, name), name)


def _component_payload_hash(kind: str, records: list[dict[str, Any]]) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": QUALITY_COMPONENT_PROJECTION_SCHEMA,
                "kind": kind,
                "records": records,
            }
        )
    )


def derive_c2_quality_component_projections(
    pair: AcceptedRiskInputPair,
    row_evidence: tuple[ProductionRowEvidence, ...],
) -> tuple[C2QualityComponentProjection, ...]:
    """Derive q-data component payload roots without needing aggregate q_data.

    The roots cover every complete identity+firm candidate for a
    security/session, regardless of which signal arm later admits it.  That
    makes the roots constructible before C2 and stable across the paired arms.
    """

    if type(pair) is not AcceptedRiskInputPair:
        raise ProductionTruthError("quality projection requires exact accepted-risk pair")
    if type(row_evidence) is not tuple or any(
        type(item) is not ProductionRowEvidence for item in row_evidence
    ):
        raise ProductionTruthError("quality projection rows have wrong topology")
    source_by_locator = {item.locator: item for item in pair.rows}
    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]] = {}
    for evidence in row_evidence:
        source = source_by_locator.get(evidence.locator)
        if source is None or evidence.security is None or evidence.firm is None:
            continue
        session = source.current_view.eligible_session
        if session is None:
            continue
        key = (session, evidence.security.security_id)
        timestamp = {
            "locator": evidence.locator.to_record(),
            "event_date": source.event_date,
            "raw_event_time": source.raw_event_time,
            "clock_interpretation": source.clock_interpretation,
            "eligible_at": source.current_view.eligible_at,
            "decision_cutoff_at": source.current_view.decision_cutoff_at,
        }
        firm = evidence.firm.to_record()
        security = evidence.security.to_record()
        grouped.setdefault(key, []).append((timestamp, firm, security))
    result: list[C2QualityComponentProjection] = []
    for (session, security_id), values in sorted(grouped.items()):
        ordered = sorted(
            values,
            key=lambda item: canonical_json_bytes(item[0]),
        )
        result.append(
            C2QualityComponentProjection(
                security_id=security_id,
                measured_session=session,
                timestamp_payload_sha256=_component_payload_hash(
                    QualityComponentKind.TIMESTAMP_QUALITY.value,
                    [item[0] for item in ordered],
                ),
                firm_label_payload_sha256=_component_payload_hash(
                    QualityComponentKind.FIRM_LABEL_MAPPING_QUALITY.value,
                    [item[1] for item in ordered],
                ),
                security_entity_payload_sha256=_component_payload_hash(
                    QualityComponentKind.SECURITY_ENTITY_MAPPING_QUALITY.value,
                    [item[2] for item in ordered],
                ),
            )
        )
    return tuple(result)


@dataclasses.dataclass(frozen=True)
class UniverseSessionSummary:
    decision_session: str
    accepted_count: int
    refusal_count: int
    terminal_count: int
    terminal_merkle_root: str

    def __post_init__(self) -> None:
        _exact_string(self.decision_session, "decision_session")
        parse_date(self.decision_session, "decision_session")
        for name in ("accepted_count", "refusal_count", "terminal_count"):
            require_int(getattr(self, name), name, minimum=0)
        if self.terminal_count != self.accepted_count + self.refusal_count:
            raise ProductionTruthError("session terminal count does not reconcile")
        _exact_string(self.terminal_merkle_root, "terminal_merkle_root")
        require_sha256(self.terminal_merkle_root, "terminal_merkle_root")

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": SESSION_SUMMARY_SCHEMA,
            "decision_session": self.decision_session,
            "accepted_count": self.accepted_count,
            "refusal_count": self.refusal_count,
            "terminal_count": self.terminal_count,
            "terminal_merkle_root": self.terminal_merkle_root,
        }


def _merkle_root(records: list[dict[str, Any]]) -> str:
    if not records:
        return sha256_bytes(canonical_json_bytes({"domain": "arv2-empty-terminal-set-v1"}))
    level = [
        sha256_bytes(
            canonical_json_bytes({"domain": "arv2-terminal-leaf-v1", "record": item})
        )
        for item in records
    ]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            sha256_bytes(
                canonical_json_bytes(
                    {"domain": "arv2-terminal-node-v1", "left": level[index], "right": level[index + 1]}
                )
            )
            for index in range(0, len(level), 2)
        ]
    return level[0]


def _validate_terminal_topology(
    accepted_rows: tuple[EligibleSecuritySession, ...],
    refusals: tuple[EligibleSecuritySessionRefusal, ...],
) -> None:
    if type(accepted_rows) is not tuple or any(
        type(item) is not EligibleSecuritySession for item in accepted_rows
    ):
        raise ProductionTruthError("accepted universe terminals have wrong topology")
    if type(refusals) is not tuple or any(
        type(item) is not EligibleSecuritySessionRefusal for item in refusals
    ):
        raise ProductionTruthError("refused universe terminals have wrong topology")
    if not accepted_rows:
        raise ProductionTruthError("production universe must contain an accepted terminal")
    for item in accepted_rows:
        item.__post_init__()
    for item in refusals:
        item.__post_init__()
    accepted_keys = tuple((item.decision_session, item.security_id) for item in accepted_rows)
    refusal_keys = tuple((item.decision_session, item.security_id) for item in refusals)
    if accepted_keys != tuple(sorted(set(accepted_keys))):
        raise ProductionTruthError("accepted universe terminals repeat or are not canonical")
    if refusal_keys != tuple(sorted(set(refusal_keys))):
        raise ProductionTruthError("refused universe terminals repeat or are not canonical")
    if set(accepted_keys) & set(refusal_keys):
        raise ProductionTruthError("one universe security/session has multiple terminals")
    expected = set(FORMAL_SESSION_GEOMETRY)
    if any(session not in expected for session, _security_id in (*accepted_keys, *refusal_keys)):
        raise ProductionTruthError("universe terminal is outside the reviewed fold geometry")


def _session_summaries(
    accepted_rows: tuple[EligibleSecuritySession, ...],
    refusals: tuple[EligibleSecuritySessionRefusal, ...],
) -> tuple[UniverseSessionSummary, ...]:
    accepted_by_session: dict[str, list[EligibleSecuritySession]] = {}
    refused_by_session: dict[str, list[EligibleSecuritySessionRefusal]] = {}
    for item in accepted_rows:
        accepted_by_session.setdefault(item.decision_session, []).append(item)
    for item in refusals:
        refused_by_session.setdefault(item.decision_session, []).append(item)
    result: list[UniverseSessionSummary] = []
    for session in FORMAL_SESSION_GEOMETRY:
        accepted = accepted_by_session.get(session, [])
        refused = refused_by_session.get(session, [])
        records = [
            {"terminal": "accepted", "value": item.to_record()} for item in accepted
        ] + [
            {"terminal": "refused", "value": item.to_record()} for item in refused
        ]
        records.sort(key=lambda item: item["value"]["security_id"])
        result.append(
            UniverseSessionSummary(
                decision_session=session,
                accepted_count=len(accepted),
                refusal_count=len(refused),
                terminal_count=len(records),
                terminal_merkle_root=_merkle_root(records),
            )
        )
    return tuple(result)


def universe_terminal_projection_sha256(
    accepted_rows: tuple[EligibleSecuritySession, ...],
    refusals: tuple[EligibleSecuritySessionRefusal, ...] = (),
) -> str:
    _validate_terminal_topology(accepted_rows, refusals)
    summaries = _session_summaries(accepted_rows, refusals)
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": UNIVERSE_TERMINAL_PROJECTION_SCHEMA,
                "session_geometry_sha256": FORMAL_SESSION_GEOMETRY_SHA256,
                "session_summaries": [item.to_record() for item in summaries],
            }
        )
    )


def build_production_truth_source_binding(
    *,
    kind: TruthSourceKind,
    artifact_id: str,
    artifact_sha256: str,
    accepted_rows: tuple[EligibleSecuritySession, ...] = (),
    refusals: tuple[EligibleSecuritySessionRefusal, ...] = (),
) -> ProductionTruthSourceBinding:
    if type(kind) is not TruthSourceKind:
        raise ProductionTruthError("truth source kind has wrong type")
    projection: str | None = None
    if kind is TruthSourceKind.ELIGIBLE_UNIVERSE:
        projection = universe_terminal_projection_sha256(accepted_rows, refusals)
    elif accepted_rows or refusals:
        raise ProductionTruthError("only eligible-universe source accepts terminal rows")
    accepted_risk = kind is TruthSourceKind.ACCEPTED_RISK_CAPTURE
    return ProductionTruthSourceBinding(
        kind=kind,
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
        projection_sha256=projection,
        reviewed=True,
        point_in_time=not accepted_risk,
        accepted_risk_non_pristine=accepted_risk,
    )


@dataclasses.dataclass(frozen=True, init=False)
class ProductionTruthArtifact:
    schema: str
    contract_id: str
    contract_sha256: str
    artifact_id: str
    artifact_sha256: str
    c2_evidence_authority: ProductionEvidenceAuthority
    c2_authority_id: str
    c2_authority_sha256: str
    production_evidence_receipt: ProductionEvidenceAcquisitionReceipt
    production_evidence_receipt_id: str
    production_evidence_receipt_sha256: str
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt
    preopen_acquisition_id: str
    preopen_acquisition_sha256: str
    source_bindings: tuple[ProductionTruthSourceBinding, ...]
    accepted_rows: tuple[EligibleSecuritySession, ...]
    refusals: tuple[EligibleSecuritySessionRefusal, ...]
    q_data_measurements: tuple[DerivedDataQualityEvidence, ...]
    session_summaries: tuple[UniverseSessionSummary, ...]
    terminal_projection_sha256: str
    session_geometry_sha256: str
    provider_access: bool
    credential_access: bool
    filesystem_access: bool
    quantconnect_access: bool
    object_store_access: bool
    price_access: bool
    outcome_access: bool
    deployment: bool
    orders: bool
    trading: bool


_PRODUCTION_TRUTH_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType[ProductionTruthArtifact], tuple[object, ...]]
] = {}
_PRODUCTION_TRUTH_AUTHORITIES_LOCK = threading.RLock()


def _artifact_record(
    *,
    authority: ProductionEvidenceAuthority,
    evidence_receipt: ProductionEvidenceAcquisitionReceipt,
    acquisition: PreopenControlAcquisitionReceipt,
    sources: tuple[ProductionTruthSourceBinding, ...],
    accepted: tuple[EligibleSecuritySession, ...],
    refusals: tuple[EligibleSecuritySessionRefusal, ...],
    measurements: tuple[DerivedDataQualityEvidence, ...],
    summaries: tuple[UniverseSessionSummary, ...],
    projection_sha256: str,
) -> dict[str, Any]:
    return {
        "schema": TRUTH_SCHEMA,
        "contract_id": TRUTH_CONTRACT_ID,
        "contract_sha256": TRUTH_CONTRACT_SHA256,
        "c2_authority_id": authority.authority_id,
        "c2_authority_sha256": authority.authority_sha256,
        "production_evidence_acquisition": {
            "receipt_id": evidence_receipt.receipt_id,
            "receipt_sha256": evidence_receipt.receipt_sha256,
            "package_sha256": evidence_receipt.package_sha256,
            "package_byte_count": evidence_receipt.package_byte_count,
            "package_row_count": evidence_receipt.package_row_count,
            "source_projection_sha256": evidence_receipt.source_projection_sha256,
            "row_projection_sha256": evidence_receipt.row_projection_sha256,
            "review_pin_id": evidence_receipt.review_pin_id,
            "review_pin_sha256": evidence_receipt.review_pin_sha256,
            "q_data_measurement_projection_sha256": (
                evidence_receipt.q_data_measurement_projection_sha256
            ),
        },
        "preopen_acquisition": {
            "artifact_id": acquisition.artifact_id,
            "content_sha256": acquisition.content_sha256,
            "artifact_sha256": acquisition.artifact_sha256,
            "byte_count": acquisition.byte_count,
            "review_receipt_id": acquisition.review_receipt_id,
            "review_receipt_sha256": acquisition.review_receipt_sha256,
            "input_source_inventory_sha256": acquisition.input_source_inventory_sha256,
            "project_source_set_sha256": acquisition.project_source_set_sha256,
            "universe_terminal_projection_sha256": (
                acquisition.universe_terminal_projection_sha256
            ),
            "control_terminal_projection_sha256": (
                acquisition.control_terminal_projection_sha256
            ),
            "q_data_measurement_count": acquisition.q_data_measurement_count,
            "q_data_measurement_projection_sha256": (
                acquisition.q_data_measurement_projection_sha256
            ),
        },
        "source_bindings": [item.to_record() for item in sources],
        "accepted_rows": [item.to_record() for item in accepted],
        "refusals": [item.to_record() for item in refusals],
        "q_data_measurements": [item.to_record() for item in measurements],
        "session_summaries": [item.to_record() for item in summaries],
        "terminal_projection_sha256": projection_sha256,
        "session_geometry_sha256": FORMAL_SESSION_GEOMETRY_SHA256,
        "capabilities": {
            "provider_access": False,
            "credential_access": False,
            "filesystem_access": False,
            "quantconnect_access": False,
            "object_store_access": False,
            "price_access": False,
            "outcome_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _artifact_fingerprint(value: ProductionTruthArtifact) -> tuple[object, ...]:
    return (
        id(value.c2_evidence_authority),
        id(value.production_evidence_receipt),
        id(value.preopen_acquisition_receipt),
        id(value.source_bindings),
        tuple(id(item) for item in value.source_bindings),
        id(value.accepted_rows),
        tuple(id(item) for item in value.accepted_rows),
        id(value.refusals),
        tuple(id(item) for item in value.refusals),
        id(value.q_data_measurements),
        tuple(
            (id(item), id(item.components), tuple(id(component) for component in item.components))
            for item in value.q_data_measurements
        ),
        id(value.session_summaries),
        tuple(id(item) for item in value.session_summaries),
        value.artifact_id,
        value.artifact_sha256,
        canonical_json_bytes(
            _artifact_record(
                authority=value.c2_evidence_authority,
                evidence_receipt=value.production_evidence_receipt,
                acquisition=value.preopen_acquisition_receipt,
                sources=value.source_bindings,
                accepted=value.accepted_rows,
                refusals=value.refusals,
                measurements=value.q_data_measurements,
                summaries=value.session_summaries,
                projection_sha256=value.terminal_projection_sha256,
            )
        ),
    )


def _forget_artifact(
    identity: int, reference: weakref.ReferenceType[ProductionTruthArtifact]
) -> None:
    with _PRODUCTION_TRUTH_AUTHORITIES_LOCK:
        current = _PRODUCTION_TRUTH_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _PRODUCTION_TRUTH_AUTHORITIES.pop(identity, None)


def _validate_sources(
    authority: ProductionEvidenceAuthority,
    acquisition: PreopenControlAcquisitionReceipt,
    sources: tuple[ProductionTruthSourceBinding, ...],
    accepted: tuple[EligibleSecuritySession, ...],
    refusals: tuple[EligibleSecuritySessionRefusal, ...],
) -> dict[TruthSourceKind, ProductionTruthSourceBinding]:
    try:
        require_reviewed_preopen_control_acquisition_receipt(acquisition)
    except PreopenControlAcquisitionError as exc:
        raise ProductionTruthError(
            "eligible-universe/control acquisition did not authenticate"
        ) from exc
    if not (
        acquisition.rating_source_complete
        and acquisition.earnings_source_complete
        and acquisition.guidance_source_complete
    ):
        raise ProductionTruthError(
            "pre-open source completeness remains a named formal-readiness refusal"
        )
    if type(sources) is not tuple or tuple(item.kind for item in sources) != _SOURCE_ORDER:
        raise ProductionTruthError("truth sources are missing, duplicated, or reordered")
    for item in sources:
        item.__post_init__()
    by_kind = {item.kind: item for item in sources}
    acquired_sources = {
        kind: (artifact_id, artifact_sha256)
        for kind, artifact_id, artifact_sha256
        in acquisition.truth_source_bindings
    }
    if set(acquired_sources) != {item.value for item in TruthSourceKind}:
        raise ProductionTruthError("acquisition truth source inventory changed")
    for item in sources:
        if acquired_sources[item.kind.value] != (
            item.artifact_id, item.artifact_sha256
        ):
            raise ProductionTruthError(
                f"{item.kind.value} is not the physically reviewed acquisition source"
            )
    capture = by_kind[TruthSourceKind.ACCEPTED_RISK_CAPTURE]
    if capture.artifact_id != authority.pair_id or capture.artifact_sha256 != authority.pair_sha256:
        raise ProductionTruthError("accepted-risk capture source binding mismatch")
    c2_sources = {item.kind: item for item in authority.source_bindings}
    for truth_kind, c2_kind in _C2_SOURCE_KIND.items():
        truth_source = by_kind[truth_kind]
        c2_source = c2_sources[c2_kind]
        if (
            truth_source.artifact_id != c2_source.artifact_id
            or truth_source.artifact_sha256 != c2_source.artifact_sha256
        ):
            raise ProductionTruthError(f"{truth_kind.value} source binding mismatch")
    universe = by_kind[TruthSourceKind.ELIGIBLE_UNIVERSE]
    if (
        universe.artifact_id != acquisition.eligible_universe_artifact_id
        or universe.artifact_sha256
        != acquisition.eligible_universe_artifact_sha256
    ):
        raise ProductionTruthError(
            "eligible-universe source is not the independently reviewed acquisition source"
        )
    projection = universe_terminal_projection_sha256(accepted, refusals)
    if universe.projection_sha256 != projection:
        raise ProductionTruthError("eligible-universe terminal projection mismatch")
    for item in (*accepted, *refusals):
        if item.source_id != universe.artifact_id or item.source_sha256 != universe.artifact_sha256:
            raise ProductionTruthError("universe terminal source binding mismatch")
    return by_kind


def _validate_measurements(
    measurements: tuple[DerivedDataQualityEvidence, ...],
    accepted: tuple[EligibleSecuritySession, ...],
    sources: dict[TruthSourceKind, ProductionTruthSourceBinding],
    authority: ProductionEvidenceAuthority,
) -> None:
    if type(measurements) is not tuple or any(
        type(item) is not DerivedDataQualityEvidence for item in measurements
    ):
        raise ProductionTruthError("q_data measurements have wrong topology")
    for item in measurements:
        _validate_derived_quality(item)
    keys = tuple((item.measured_session, item.security_id) for item in measurements)
    if keys != tuple(sorted(set(keys))):
        raise ProductionTruthError("q_data measurements repeat or are not canonical")
    accepted_keys = tuple((item.decision_session, item.security_id) for item in accepted)
    if keys != accepted_keys:
        raise ProductionTruthError("q_data measurements do not exhaust accepted universe terminals")
    quality_source = sources[TruthSourceKind.DATA_QUALITY]
    capture_source = sources[TruthSourceKind.ACCEPTED_RISK_CAPTURE]
    firm_source = sources[TruthSourceKind.FIRM_ONTOLOGY]
    identity_source = sources[TruthSourceKind.SECURITY_MASTER]
    expected_component_sources = (
        (capture_source, False, True),
        (firm_source, True, False),
        (identity_source, True, False),
    )
    for terminal, measurement in zip(accepted, measurements, strict=True):
        if (
            measurement.source_id != quality_source.artifact_id
            or measurement.source_sha256 != quality_source.artifact_sha256
            or terminal.q_data != measurement.q_data
            or terminal.q_data_evidence_sha256 != measurement.evidence_sha256
            or terminal.q_data_available_at != measurement.available_at
        ):
            raise ProductionTruthError("accepted terminal q_data is not exact derived evidence")
        for component, (source, pit, accepted_risk) in zip(
            measurement.components, expected_component_sources, strict=True
        ):
            if (
                component.source_id != source.artifact_id
                or component.source_sha256 != source.artifact_sha256
                or component.point_in_time is not pit
                or component.accepted_risk_non_pristine is not accepted_risk
            ):
                raise ProductionTruthError("q_data component source binding mismatch")
    projections = {
        (item.measured_session, item.security_id): item
        for item in derive_c2_quality_component_projections(
            authority.pair, authority.row_evidence
        )
    }
    measurement_by_key = {
        (item.measured_session, item.security_id): item for item in measurements
    }
    for key, projection in projections.items():
        measurement = measurement_by_key.get(key)
        if measurement is None:
            continue
        expected_payloads = (
            projection.timestamp_payload_sha256,
            projection.firm_label_payload_sha256,
            projection.security_entity_payload_sha256,
        )
        if tuple(item.payload_sha256 for item in measurement.components) != expected_payloads:
            raise ProductionTruthError("derived q_data components do not bind exact C2 evidence")
    source_by_locator = {item.locator: item for item in authority.pair.rows}
    for row in authority.row_evidence:
        if row.security is None or row.q_data is None:
            continue
        source = source_by_locator.get(row.locator)
        if source is None or source.current_view.eligible_session is None:
            continue
        key = (source.current_view.eligible_session, row.security.security_id)
        measurement = measurement_by_key.get(key)
        if measurement is None:
            continue
        quality = row.q_data
        if (
            quality.security_id != measurement.security_id
            or quality.measured_session != measurement.measured_session
            or quality.source_id != measurement.source_id
            or quality.source_sha256 != measurement.source_sha256
            or quality.evidence_sha256 != measurement.evidence_sha256
            or quality.available_at != measurement.available_at
            or quality.measurement_method_id != measurement.measurement_method_id
            or quality.q_data != measurement.q_data
            or type(quality.point_in_time) is not bool
            or not quality.point_in_time
        ):
            raise ProductionTruthError("derived q_data does not match exact C2 quality evidence")


def _validate_acquisition_sessions(
    acquisition: PreopenControlAcquisitionReceipt,
    summaries: tuple[UniverseSessionSummary, ...],
) -> None:
    """Cross-check caller objects against the independently reviewed census."""

    try:
        require_reviewed_preopen_control_acquisition_receipt(acquisition)
    except PreopenControlAcquisitionError as exc:
        raise ProductionTruthError("pre-open acquisition receipt did not authenticate") from exc
    if tuple(item.decision_session for item in acquisition.universe_sessions) != tuple(
        item.decision_session for item in summaries
    ):
        raise ProductionTruthError("acquisition omitted or added a formal decision session")
    for acquired, expected in zip(
        acquisition.universe_sessions, summaries, strict=True
    ):
        if (
            acquired.accepted_count != expected.accepted_count
            or acquired.refusal_count != expected.refusal_count
            or acquired.terminal_count != expected.terminal_count
            or acquired.terminal_merkle_root != expected.terminal_merkle_root
        ):
            raise ProductionTruthError(
                "caller universe differs from independently reviewed session terminal"
            )
    if tuple(item.decision_session for item in acquisition.control_sessions) != tuple(
        item.decision_session for item in summaries
    ):
        raise ProductionTruthError("control acquisition session geometry changed")
    for acquired, expected in zip(
        acquisition.control_sessions, summaries, strict=True
    ):
        if (
            acquired.accepted_count != expected.accepted_count
            or acquired.refusal_count != expected.refusal_count
            or acquired.terminal_count != expected.terminal_count
        ):
            raise ProductionTruthError(
                "production truth does not match reviewed control terminals"
            )


def _validate_physical_evidence_authority(
    *,
    receipt: ProductionEvidenceAcquisitionReceipt,
    authority: ProductionEvidenceAuthority,
    acquisition: PreopenControlAcquisitionReceipt,
    measurements: tuple[DerivedDataQualityEvidence, ...],
) -> None:
    """Require exact physical C2 members and same-key q-data measurements."""

    try:
        require_production_evidence_acquisition_receipt(receipt)
    except ProductionEvidenceAcquisitionError as exc:
        raise ProductionTruthError(
            "physical production evidence receipt did not authenticate"
        ) from exc
    if receipt.authority is not authority:
        raise ProductionTruthError(
            "C2 authority is not the authority retained by the physical package receipt"
        )
    if receipt.preopen_acquisition_receipt is not acquisition:
        raise ProductionTruthError(
            "production evidence and truth do not retain the same pre-open acquisition"
        )
    try:
        physical = acquisition_q_data_measurement_projection_record(acquisition)
    except PreopenControlAcquisitionError as exc:
        raise ProductionTruthError(
            "physical q_data measurement projection did not authenticate"
        ) from exc
    expected_projection = quality_measurement_projection_sha256(measurements)
    if (
        physical
        != {
            "schema": QUALITY_MEASUREMENT_PROJECTION_SCHEMA,
            "measurement_count": len(measurements),
            "projection_sha256": expected_projection,
        }
        or receipt.q_data_measurement_projection_sha256 != expected_projection
    ):
        raise ProductionTruthError(
            "q_data measurements are not the exact physically acquired same-key evidence"
        )


def build_production_truth_artifact(
    c2_evidence_authority: ProductionEvidenceAuthority,
    *,
    production_evidence_receipt: ProductionEvidenceAcquisitionReceipt,
    preopen_acquisition_receipt: PreopenControlAcquisitionReceipt,
    source_bindings: tuple[ProductionTruthSourceBinding, ...],
    accepted_rows: tuple[EligibleSecuritySession, ...],
    refusals: tuple[EligibleSecuritySessionRefusal, ...],
    q_data_measurements: tuple[DerivedDataQualityEvidence, ...],
) -> ProductionTruthArtifact:
    """Authenticate a physically serializable, outcome-free production truth."""

    try:
        require_production_evidence_authority(c2_evidence_authority)
    except ProductionInputError as exc:
        raise ProductionTruthError("C2 evidence authority did not authenticate") from exc
    _validate_terminal_topology(accepted_rows, refusals)
    by_source = _validate_sources(
        c2_evidence_authority,
        preopen_acquisition_receipt,
        source_bindings,
        accepted_rows,
        refusals,
    )
    _validate_measurements(
        q_data_measurements, accepted_rows, by_source, c2_evidence_authority
    )
    _validate_physical_evidence_authority(
        receipt=production_evidence_receipt,
        authority=c2_evidence_authority,
        acquisition=preopen_acquisition_receipt,
        measurements=q_data_measurements,
    )
    summaries = _session_summaries(accepted_rows, refusals)
    _validate_acquisition_sessions(preopen_acquisition_receipt, summaries)
    projection = universe_terminal_projection_sha256(accepted_rows, refusals)
    semantic = _artifact_record(
        authority=c2_evidence_authority,
        evidence_receipt=production_evidence_receipt,
        acquisition=preopen_acquisition_receipt,
        sources=source_bindings,
        accepted=accepted_rows,
        refusals=refusals,
        measurements=q_data_measurements,
        summaries=summaries,
        projection_sha256=projection,
    )
    digest = sha256_bytes(canonical_json_bytes(semantic))
    result = object.__new__(ProductionTruthArtifact)
    values: dict[str, object] = {
        "schema": TRUTH_SCHEMA,
        "contract_id": TRUTH_CONTRACT_ID,
        "contract_sha256": TRUTH_CONTRACT_SHA256,
        "artifact_id": f"arv2-production-truth-{digest[:24]}",
        "artifact_sha256": digest,
        "c2_evidence_authority": c2_evidence_authority,
        "c2_authority_id": c2_evidence_authority.authority_id,
        "c2_authority_sha256": c2_evidence_authority.authority_sha256,
        "production_evidence_receipt": production_evidence_receipt,
        "production_evidence_receipt_id": production_evidence_receipt.receipt_id,
        "production_evidence_receipt_sha256": production_evidence_receipt.receipt_sha256,
        "preopen_acquisition_receipt": preopen_acquisition_receipt,
        "preopen_acquisition_id": preopen_acquisition_receipt.artifact_id,
        "preopen_acquisition_sha256": preopen_acquisition_receipt.artifact_sha256,
        "source_bindings": source_bindings,
        "accepted_rows": accepted_rows,
        "refusals": refusals,
        "q_data_measurements": q_data_measurements,
        "session_summaries": summaries,
        "terminal_projection_sha256": projection,
        "session_geometry_sha256": FORMAL_SESSION_GEOMETRY_SHA256,
        "provider_access": False,
        "credential_access": False,
        "filesystem_access": False,
        "quantconnect_access": False,
        "object_store_access": False,
        "price_access": False,
        "outcome_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    for name, item in values.items():
        object.__setattr__(result, name, item)
    identity = id(result)
    reference = weakref.ref(result, lambda ref, key=identity: _forget_artifact(key, ref))
    with _PRODUCTION_TRUTH_AUTHORITIES_LOCK:
        _PRODUCTION_TRUTH_AUTHORITIES[identity] = (
            reference,
            _artifact_fingerprint(result),
        )
    return require_production_truth_artifact(result)


def require_production_truth_artifact(
    value: ProductionTruthArtifact,
) -> ProductionTruthArtifact:
    if type(value) is not ProductionTruthArtifact:
        raise ProductionTruthError("production truth requires exact built type")
    with _PRODUCTION_TRUTH_AUTHORITIES_LOCK:
        registered = _PRODUCTION_TRUTH_AUTHORITIES.get(id(value))
    if registered is None or registered[0]() is not value:
        raise ProductionTruthError("production truth is not builder-authenticated")
    try:
        require_production_evidence_authority(value.c2_evidence_authority)
    except ProductionInputError as exc:
        raise ProductionTruthError("production truth C2 parent changed") from exc
    _validate_physical_evidence_authority(
        receipt=value.production_evidence_receipt,
        authority=value.c2_evidence_authority,
        acquisition=value.preopen_acquisition_receipt,
        measurements=value.q_data_measurements,
    )
    _validate_terminal_topology(value.accepted_rows, value.refusals)
    sources = _validate_sources(
        value.c2_evidence_authority,
        value.preopen_acquisition_receipt,
        value.source_bindings,
        value.accepted_rows,
        value.refusals,
    )
    _validate_measurements(
        value.q_data_measurements,
        value.accepted_rows,
        sources,
        value.c2_evidence_authority,
    )
    expected_summaries = _session_summaries(value.accepted_rows, value.refusals)
    _validate_acquisition_sessions(
        value.preopen_acquisition_receipt, expected_summaries
    )
    expected_projection = universe_terminal_projection_sha256(
        value.accepted_rows, value.refusals
    )
    false_flags = (
        value.provider_access,
        value.credential_access,
        value.filesystem_access,
        value.quantconnect_access,
        value.object_store_access,
        value.price_access,
        value.outcome_access,
        value.deployment,
        value.orders,
        value.trading,
    )
    if any(type(item) is not bool or item for item in false_flags):
        raise ProductionTruthError("production truth acquired a forbidden capability")
    if (
        value.schema != TRUTH_SCHEMA
        or value.contract_id != TRUTH_CONTRACT_ID
        or value.contract_sha256 != TRUTH_CONTRACT_SHA256
        or value.c2_authority_id != value.c2_evidence_authority.authority_id
        or value.c2_authority_sha256 != value.c2_evidence_authority.authority_sha256
        or value.production_evidence_receipt_id
        != value.production_evidence_receipt.receipt_id
        or value.production_evidence_receipt_sha256
        != value.production_evidence_receipt.receipt_sha256
        or value.preopen_acquisition_id
        != value.preopen_acquisition_receipt.artifact_id
        or value.preopen_acquisition_sha256
        != value.preopen_acquisition_receipt.artifact_sha256
        or value.session_geometry_sha256 != FORMAL_SESSION_GEOMETRY_SHA256
        or value.session_summaries != expected_summaries
        or value.terminal_projection_sha256 != expected_projection
    ):
        raise ProductionTruthError("production truth semantic binding changed")
    semantic = _artifact_record(
        authority=value.c2_evidence_authority,
        evidence_receipt=value.production_evidence_receipt,
        acquisition=value.preopen_acquisition_receipt,
        sources=value.source_bindings,
        accepted=value.accepted_rows,
        refusals=value.refusals,
        measurements=value.q_data_measurements,
        summaries=value.session_summaries,
        projection_sha256=value.terminal_projection_sha256,
    )
    digest = sha256_bytes(canonical_json_bytes(semantic))
    if (
        value.artifact_sha256 != digest
        or value.artifact_id != f"arv2-production-truth-{digest[:24]}"
        or _artifact_fingerprint(value) != registered[1]
    ):
        raise ProductionTruthError("production truth changed after authentication")
    return value


def render_production_truth_artifact_bytes(value: ProductionTruthArtifact) -> bytes:
    require_production_truth_artifact(value)
    return canonical_json_bytes(
        {
            "artifact_id": value.artifact_id,
            "artifact_sha256": value.artifact_sha256,
            **_artifact_record(
                authority=value.c2_evidence_authority,
                evidence_receipt=value.production_evidence_receipt,
                acquisition=value.preopen_acquisition_receipt,
                sources=value.source_bindings,
                accepted=value.accepted_rows,
                refusals=value.refusals,
                measurements=value.q_data_measurements,
                summaries=value.session_summaries,
                projection_sha256=value.terminal_projection_sha256,
            ),
        }
    )


def require_preopen_control_truth_equivalence(
    acquisition: PreopenControlAcquisitionReceipt,
    truth: ProductionTruthArtifact,
) -> PreopenControlAcquisitionReceipt:
    """Prove that formal truth is the exact physically acquired control census."""

    require_production_truth_artifact(truth)
    if truth.preopen_acquisition_receipt is not acquisition:
        raise ProductionTruthError("truth does not retain this acquisition authority")
    _validate_acquisition_sessions(acquisition, truth.session_summaries)
    return require_reviewed_preopen_control_acquisition_receipt(acquisition)


__all__ = [
    "C2QualityComponentProjection",
    "DerivedDataQualityEvidence",
    "FORMAL_SESSION_GEOMETRY",
    "FORMAL_SESSION_GEOMETRY_SHA256",
    "ProductionTruthArtifact",
    "ProductionTruthError",
    "ProductionTruthSourceBinding",
    "QUALITY_MEASUREMENT_PROJECTION_SCHEMA",
    "QUALITY_METHOD_ID",
    "QualityComponentEvidence",
    "QualityComponentKind",
    "TRUTH_CONTRACT_ID",
    "TRUTH_CONTRACT_SHA256",
    "TRUTH_SCHEMA",
    "TruthSourceKind",
    "UniverseSessionSummary",
    "build_derived_data_quality_evidence",
    "build_production_truth_artifact",
    "build_production_truth_source_binding",
    "build_quality_component_evidence",
    "derive_c2_quality_component_projections",
    "production_truth_contract_record",
    "project_c2_data_quality_evidence",
    "quality_measurement_projection_sha256",
    "render_production_truth_artifact_bytes",
    "render_production_truth_contract_bytes",
    "require_production_truth_artifact",
    "require_preopen_control_truth_equivalence",
    "universe_terminal_projection_sha256",
]
