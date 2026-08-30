"""Structural, outcome-free Analyst Revisions V2 stock-score candidate.

This module implements the PDF's pre-control stock equations from revalidated
ARV2-2 identity/ontology evidence.  It deliberately cannot publish a
production stock-score artifact: institution, catalyst, sector and measured
quality inputs are structural evidence only, every production registry remains
zero-access, and the owner-frozen QC-first control contract remains pending
independent review and implementation.
"""
from __future__ import annotations

import dataclasses
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import Enum
from fractions import Fraction
from typing import Any, Iterable

from data.exchange_calendar import (
    ExchangeCalendarError,
    is_trading_session,
    session_open_instant,
    trading_sessions,
)

from .availability import AvailabilityError, derive_event_availability
from .canonical import (
    format_utc_timestamp,
    parse_date,
    parse_utc_timestamp,
    require_identifier,
    require_sha256,
    sha256_bytes,
    canonical_json_bytes,
)
from .firm_ontology import ReviewedFirmRatingOntology
from .formulas import (
    ActivityAwareObservation,
    ActivityObservationState,
    FormulaError,
    IndependentContribution,
    VerifiedAnalystPolicy,
    analyst_decimal_context,
    independent_evidence_breadth,
    rating_decay_weight,
    require_verified_analyst_policy,
    robust_activity_group_normalize,
    stock_reliability,
)
from .ratings_ingest import (
    BenzingaIngestAudit,
    DailyRatingContributionCandidate,
    FirmRatingNormalizationResult,
    deduplicate_daily_rating_contributions,
)
from .security_master import (
    CombinedRefusalStage,
    ELIGIBLE_ISSUER_COUNTRY,
    ELIGIBLE_LISTING_EXCHANGES,
    IdentityResolvedFirmRatingResult,
    IdentityRefusalReason,
    PointInTimeSecurityMaster,
    SecurityIdentityAudit,
    SecurityType,
    revalidate_identity_resolved_firm_rating_result,
    revalidate_pit_security_master,
)


STRUCTURAL_STOCK_EVIDENCE_SCHEMA = "arv2-structural-stock-score-evidence-v1"
STRUCTURAL_STOCK_SCORE_SCHEMA = "arv2-structural-stock-score-candidate-v1"
STRUCTURAL_STOCK_DIAGNOSTICS_SCHEMA = "arv2-structural-stock-diagnostics-v1"
STRUCTURAL_ONLY_AUTHORITY = "structural_fixture_only_zero_production_authority"
RESIDUALIZATION_BLOCK = (
    "blocked_owner_frozen_control_contract_pending_review_and_implementation"
)
ELIGIBLE_HISTORY_FIRST_YEAR = 2013
PROVEN_INELIGIBLE_IDENTITY_REFUSAL_REASONS = frozenset(
    {
        IdentityRefusalReason.INELIGIBLE_ISSUER_COUNTRY.value,
        IdentityRefusalReason.INELIGIBLE_LISTING_COUNTRY.value,
        IdentityRefusalReason.INELIGIBLE_EXCHANGE.value,
        IdentityRefusalReason.INELIGIBLE_SECURITY_TYPE.value,
    }
)


class StockSignalError(ValueError):
    """Structural stock-score evidence or a derived candidate is invalid."""


class StockRawState(str, Enum):
    ACTIVE = "active"
    STRUCTURAL_ZERO = "structural_zero"


class RefusalScope(str, Enum):
    GLOBAL = "global"
    SECTOR = "sector"
    SECURITY = "security"
    EVENT = "event"


class StockScoreRefusalReason(str, Enum):
    EVIDENCE_BINDING_MISMATCH = "evidence_binding_mismatch"
    SOURCE_SNAPSHOT_NOT_DECISION_VINTAGE = (
        "source_snapshot_not_decision_vintage"
    )
    SOURCE_HISTORY_RANGE_INCOMPLETE = "source_history_range_incomplete"
    SOURCE_ROW_AFTER_CAPTURE = "source_row_after_capture"
    SOURCE_INGEST_REFUSAL = "source_ingest_refusal"
    UPSTREAM_IDENTITY_OR_ONTOLOGY_REFUSAL = (
        "upstream_identity_or_ontology_refusal"
    )
    NO_ELIGIBLE_UNIVERSE = "no_eligible_universe"
    MISSING_SECTOR_CLASSIFICATION = "missing_sector_classification"
    LATE_SECTOR_CLASSIFICATION = "late_sector_classification"
    AMBIGUOUS_SECTOR_CLASSIFICATION = "ambiguous_sector_classification"
    MISSING_INSTITUTION_MAPPING = "missing_institution_mapping"
    LATE_INSTITUTION_MAPPING = "late_institution_mapping"
    AMBIGUOUS_INSTITUTION_MAPPING = "ambiguous_institution_mapping"
    MISSING_COMMON_EVENT_EVIDENCE = "missing_common_event_evidence"
    LATE_COMMON_EVENT_EVIDENCE = "late_common_event_evidence"
    DAILY_DEDUPE_CONFLICT = "daily_dedupe_conflict"
    CONFLICTING_COMMON_EVENT_EVIDENCE = (
        "conflicting_common_event_evidence"
    )
    MISSING_DATA_QUALITY = "missing_data_quality"
    LATE_DATA_QUALITY = "late_data_quality"
    SECTOR_CONTAINS_INVALID_SECURITY = "sector_contains_invalid_security"
    INSUFFICIENT_TOTAL_NAMES = "insufficient_total_names"
    INSUFFICIENT_ACTIVE_NAMES = "insufficient_active_names"
    ZERO_MAD = "zero_mad"


class DiagnosticChannel(str, Enum):
    UNIQUE_ANALYSTS = "unique_analysts"
    CONSENSUS_NOVELTY = "consensus_novelty"
    PRICE_TARGET_REVISION = "price_target_revision"
    EPS_REVISION = "eps_revision"
    ANALYST_QUALITY = "analyst_quality"


class DiagnosticState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


def _exact_decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise StockSignalError(f"{name} must be exact and cannot be bool/float")
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, str) and value and value == value.strip():
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise StockSignalError(f"{name} must be a finite exact decimal") from exc
    else:
        raise StockSignalError(f"{name} must be a finite exact decimal")
    if not parsed.is_finite():
        raise StockSignalError(f"{name} must be finite")
    return parsed


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value, "f")


def _fraction_record(value: Fraction) -> list[int]:
    return [value.numerator, value.denominator]


def _interval_contains(valid_from: str, valid_to: str | None, when: date) -> bool:
    start = parse_date(valid_from, "valid_from")
    end = None if valid_to is None else parse_date(valid_to, "valid_to")
    return start <= when and (end is None or when < end)


def _visible_valid_to(
    *, valid_to: str | None, valid_to_available_at: str | None, decision_at
) -> str | None:
    """Apply the strict-before-open cutoff for new ARV2-3 evidence."""
    if valid_to is None or valid_to_available_at is None:
        return None
    return (
        valid_to
        if parse_utc_timestamp(valid_to_available_at, "valid_to_available_at")
        < decision_at
        else None
    )


def _master_visible_valid_to(
    *, valid_to: str | None, valid_to_available_at: str | None, decision_at
) -> str | None:
    """Mirror the reviewed ARV2-2 security-master inclusive PIT cutoff."""
    if valid_to is None or valid_to_available_at is None:
        return None
    return (
        valid_to
        if parse_utc_timestamp(valid_to_available_at, "valid_to_available_at")
        <= decision_at
        else None
    )


def _validate_interval(
    valid_from: str, valid_to: str | None, *, name: str
) -> None:
    start = parse_date(valid_from, f"{name}.valid_from")
    end = None if valid_to is None else parse_date(valid_to, f"{name}.valid_to")
    if end is not None and end <= start:
        raise StockSignalError(f"{name} interval is empty or reversed")


@dataclasses.dataclass(frozen=True)
class InstitutionMappingEvidence:
    provider_firm_id: str
    institution_id: str
    valid_from: str
    valid_to: str | None
    valid_to_available_at: str | None
    available_at: str
    source_evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.provider_firm_id, "provider_firm_id")
        require_identifier(self.institution_id, "institution_id")
        _validate_interval(self.valid_from, self.valid_to, name="institution mapping")
        base_available = parse_utc_timestamp(
            self.available_at, "institution.available_at"
        )
        if (self.valid_to is None) != (self.valid_to_available_at is None):
            raise StockSignalError(
                "institution valid_to and closure availability must be paired"
            )
        if self.valid_to_available_at is not None and parse_utc_timestamp(
            self.valid_to_available_at, "institution.valid_to_available_at"
        ) < base_available:
            raise StockSignalError(
                "institution closure cannot be available before its base mapping"
            )
        require_sha256(self.source_evidence_sha256, "institution evidence")

    def to_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class CommonEventEvidence:
    provider_event_id: str
    common_event_id: str
    available_at: str
    source_evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.provider_event_id, "provider_event_id")
        require_identifier(self.common_event_id, "common_event_id")
        parse_utc_timestamp(self.available_at, "common_event.available_at")
        require_sha256(self.source_evidence_sha256, "common-event evidence")

    def to_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SectorClassificationEvidence:
    security_id: str
    sector_id: str
    valid_from: str
    valid_to: str | None
    valid_to_available_at: str | None
    available_at: str
    source_evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.security_id, "security_id")
        require_identifier(self.sector_id, "sector_id")
        _validate_interval(self.valid_from, self.valid_to, name="sector classification")
        base_available = parse_utc_timestamp(
            self.available_at, "classification.available_at"
        )
        if (self.valid_to is None) != (self.valid_to_available_at is None):
            raise StockSignalError(
                "classification valid_to and closure availability must be paired"
            )
        if self.valid_to_available_at is not None and parse_utc_timestamp(
            self.valid_to_available_at, "classification.valid_to_available_at"
        ) < base_available:
            raise StockSignalError(
                "classification closure cannot be available before its base mapping"
            )
        require_sha256(self.source_evidence_sha256, "classification evidence")

    def to_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class StockDataQualityEvidence:
    security_id: str
    measured_session: str
    available_at: str
    q_data: Decimal | str | int
    measurement_method_id: str
    source_evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.security_id, "security_id")
        parse_date(self.measured_session, "measured_session")
        parse_utc_timestamp(self.available_at, "quality.available_at")
        require_identifier(self.measurement_method_id, "measurement_method_id")
        require_sha256(self.source_evidence_sha256, "quality evidence")
        value = _exact_decimal(self.q_data, "q_data")
        if not Decimal("0") <= value <= Decimal("1"):
            raise StockSignalError("q_data must be in [0,1]")
        object.__setattr__(self, "q_data", value)

    def to_record(self) -> dict[str, Any]:
        return {
            "security_id": self.security_id,
            "measured_session": self.measured_session,
            "available_at": self.available_at,
            "q_data": _decimal_text(self.q_data),
            "measurement_method_id": self.measurement_method_id,
            "source_evidence_sha256": self.source_evidence_sha256,
        }


def _overlap(
    first_from: str,
    first_to: str | None,
    second_from: str,
    second_to: str | None,
) -> bool:
    first_start = parse_date(first_from, "first.valid_from")
    first_end = (
        date.max if first_to is None else parse_date(first_to, "first.valid_to")
    )
    second_start = parse_date(second_from, "second.valid_from")
    second_end = (
        date.max
        if second_to is None
        else parse_date(second_to, "second.valid_to")
    )
    return first_start < second_end and second_start < first_end


@dataclasses.dataclass(frozen=True)
class StructuralStockScoreEvidence:
    """Content-addressed fixture evidence; never production authority."""

    schema: str
    source_audit_sha256: str
    security_master_id: str
    security_master_sha256: str
    institution_source_id: str
    catalyst_source_id: str
    classification_source_id: str
    quality_source_id: str
    institution_mappings: tuple[InstitutionMappingEvidence, ...]
    common_events: tuple[CommonEventEvidence, ...]
    sector_classifications: tuple[SectorClassificationEvidence, ...]
    data_quality: tuple[StockDataQualityEvidence, ...]

    def __post_init__(self) -> None:
        if self.schema != STRUCTURAL_STOCK_EVIDENCE_SCHEMA:
            raise StockSignalError("unsupported structural stock evidence schema")
        require_sha256(self.source_audit_sha256, "source_audit_sha256")
        require_identifier(self.security_master_id, "security_master_id")
        require_sha256(self.security_master_sha256, "security_master_sha256")
        for name in (
            "institution_source_id",
            "catalyst_source_id",
            "classification_source_id",
            "quality_source_id",
        ):
            require_identifier(getattr(self, name), name)
        typed = (
            (
                self.institution_mappings,
                InstitutionMappingEvidence,
                "institution mappings",
            ),
            (self.common_events, CommonEventEvidence, "common events"),
            (
                self.sector_classifications,
                SectorClassificationEvidence,
                "classifications",
            ),
            (self.data_quality, StockDataQualityEvidence, "data quality"),
        )
        for values, expected, name in typed:
            if type(values) is not tuple or any(
                type(item) is not expected for item in values
            ):
                raise StockSignalError(f"{name} must be an exact typed tuple")
        if self.institution_mappings != tuple(
            sorted(
                self.institution_mappings,
                key=lambda item: (
                    item.provider_firm_id,
                    item.valid_from,
                    item.institution_id,
                ),
            )
        ):
            raise StockSignalError("institution mappings are not canonical-sorted")
        if self.common_events != tuple(
            sorted(self.common_events, key=lambda item: item.provider_event_id)
        ) or len({item.provider_event_id for item in self.common_events}) != len(
            self.common_events
        ):
            raise StockSignalError("common-event evidence must be unique and sorted")
        if self.sector_classifications != tuple(
            sorted(
                self.sector_classifications,
                key=lambda item: (item.security_id, item.valid_from, item.sector_id),
            )
        ):
            raise StockSignalError("sector classifications are not canonical-sorted")
        quality_keys = [
            (item.security_id, item.measured_session) for item in self.data_quality
        ]
        if self.data_quality != tuple(
            sorted(
                self.data_quality,
                key=lambda item: (item.security_id, item.measured_session),
            )
        ) or len(quality_keys) != len(set(quality_keys)):
            raise StockSignalError("data-quality evidence must be unique and sorted")
        interval_groups: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        for item in self.institution_mappings:
            key = item.provider_firm_id
            for prior_from, prior_to in interval_groups[key]:
                if _overlap(prior_from, prior_to, item.valid_from, item.valid_to):
                    raise StockSignalError("institution mapping intervals overlap")
            interval_groups[key].append((item.valid_from, item.valid_to))
        interval_groups.clear()
        for item in self.sector_classifications:
            key = item.security_id
            for prior_from, prior_to in interval_groups[key]:
                if _overlap(prior_from, prior_to, item.valid_from, item.valid_to):
                    raise StockSignalError("sector classification intervals overlap")
            interval_groups[key].append((item.valid_from, item.valid_to))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "authority": STRUCTURAL_ONLY_AUTHORITY,
            "source_audit_sha256": self.source_audit_sha256,
            "security_master_id": self.security_master_id,
            "security_master_sha256": self.security_master_sha256,
            "institution_source_id": self.institution_source_id,
            "catalyst_source_id": self.catalyst_source_id,
            "classification_source_id": self.classification_source_id,
            "quality_source_id": self.quality_source_id,
            "institution_mappings": [
                item.to_record() for item in self.institution_mappings
            ],
            "common_events": [item.to_record() for item in self.common_events],
            "sector_classifications": [
                item.to_record() for item in self.sector_classifications
            ],
            "data_quality": [item.to_record() for item in self.data_quality],
        }

    @property
    def evidence_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_record()))


@dataclasses.dataclass(frozen=True)
class CanonicalStockContribution:
    canonical_event_id: str
    provider_event_id: str
    provider_version_id: str
    linked_event_ids: tuple[str, ...]
    institution_id: str
    common_event_id: str
    security_id: str
    eligible_session: str
    age_sessions: int
    rating_change: Fraction
    decay_weight: Decimal
    decayed_value: Decimal
    identity_mapping_evidence_sha256: str
    ontology_sha256: str
    common_event_evidence_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "canonical_event_id",
            "provider_event_id",
            "provider_version_id",
            "institution_id",
            "common_event_id",
            "security_id",
        ):
            require_identifier(getattr(self, name), name)
        if (
            type(self.linked_event_ids) is not tuple
            or not self.linked_event_ids
            or self.linked_event_ids != tuple(sorted(set(self.linked_event_ids)))
            or self.canonical_event_id not in self.linked_event_ids
        ):
            raise StockSignalError("contribution linked events are not canonical")
        parse_date(self.eligible_session, "eligible_session")
        if type(self.age_sessions) is not int or self.age_sessions < 0:
            raise StockSignalError("contribution age must be a nonnegative integer")
        if type(self.rating_change) is not Fraction or self.rating_change == 0:
            raise StockSignalError("rating change must be an exact nonzero Fraction")
        for name in ("decay_weight", "decayed_value"):
            value = getattr(self, name)
            if type(value) is not Decimal or not value.is_finite():
                raise StockSignalError(f"{name} must be an exact finite Decimal")
        if not Decimal("0") < self.decay_weight <= Decimal("1"):
            raise StockSignalError("decay weight must be in (0,1]")
        for name in (
            "identity_mapping_evidence_sha256",
            "ontology_sha256",
            "common_event_evidence_sha256",
        ):
            require_sha256(getattr(self, name), name)

    def to_record(self) -> dict[str, Any]:
        return {
            "canonical_event_id": self.canonical_event_id,
            "provider_event_id": self.provider_event_id,
            "provider_version_id": self.provider_version_id,
            "linked_event_ids": list(self.linked_event_ids),
            "institution_id": self.institution_id,
            "common_event_id": self.common_event_id,
            "security_id": self.security_id,
            "eligible_session": self.eligible_session,
            "age_sessions": self.age_sessions,
            "rating_change": _fraction_record(self.rating_change),
            "decay_weight": _decimal_text(self.decay_weight),
            "decayed_value": _decimal_text(self.decayed_value),
            "identity_mapping_evidence_sha256": self.identity_mapping_evidence_sha256,
            "ontology_sha256": self.ontology_sha256,
            "common_event_evidence_sha256": self.common_event_evidence_sha256,
        }


@dataclasses.dataclass(frozen=True)
class StockScoreRow:
    security_id: str
    sector_id: str
    raw_state: StockRawState
    raw_score: Decimal
    sector_z: Decimal
    institution_effective_n: Decimal
    catalyst_effective_n: Decimal
    independent_effective_n: Decimal
    q_data: Decimal
    reliability: Decimal
    pdf_reliable_score: Decimal

    def __post_init__(self) -> None:
        require_identifier(self.security_id, "security_id")
        require_identifier(self.sector_id, "sector_id")
        if not isinstance(self.raw_state, StockRawState):
            raise StockSignalError("raw_state must be a StockRawState")
        for name in (
            "raw_score",
            "sector_z",
            "institution_effective_n",
            "catalyst_effective_n",
            "independent_effective_n",
            "q_data",
            "reliability",
            "pdf_reliable_score",
        ):
            value = getattr(self, name)
            if type(value) is not Decimal or not value.is_finite():
                raise StockSignalError(f"{name} must be an exact finite Decimal")
        if self.raw_state is StockRawState.STRUCTURAL_ZERO and self.raw_score != 0:
            raise StockSignalError("structural zero cannot carry a nonzero raw score")
        if not Decimal("0") <= self.q_data <= Decimal("1"):
            raise StockSignalError("q_data must be in [0,1]")
        if not Decimal("0") <= self.reliability <= Decimal("1"):
            raise StockSignalError("stock reliability must be in [0,1]")

    def to_record(self) -> dict[str, Any]:
        return {
            "security_id": self.security_id,
            "sector_id": self.sector_id,
            "raw_state": self.raw_state.value,
            "raw_score": _decimal_text(self.raw_score),
            "sector_z": _decimal_text(self.sector_z),
            "institution_effective_n": _decimal_text(self.institution_effective_n),
            "catalyst_effective_n": _decimal_text(self.catalyst_effective_n),
            "independent_effective_n": _decimal_text(self.independent_effective_n),
            "q_data": _decimal_text(self.q_data),
            "reliability": _decimal_text(self.reliability),
            "pdf_reliable_score": _decimal_text(self.pdf_reliable_score),
        }


@dataclasses.dataclass(frozen=True)
class SectorNormalizationRecord:
    sector_id: str
    total_names: int
    active_names: int
    median: Decimal
    mad: Decimal

    def __post_init__(self) -> None:
        require_identifier(self.sector_id, "sector_id")
        if type(self.total_names) is not int or type(self.active_names) is not int:
            raise StockSignalError("sector counts must be exact integers")
        if not 0 <= self.active_names <= self.total_names:
            raise StockSignalError("sector active count is invalid")
        if type(self.median) is not Decimal or type(self.mad) is not Decimal:
            raise StockSignalError("sector median/MAD must be exact Decimals")
        if self.mad <= 0:
            raise StockSignalError(
                "available sector normalization requires positive MAD"
            )

    def to_record(self) -> dict[str, Any]:
        return {
            "sector_id": self.sector_id,
            "total_names": self.total_names,
            "active_names": self.active_names,
            "median": _decimal_text(self.median),
            "mad": _decimal_text(self.mad),
        }


@dataclasses.dataclass(frozen=True)
class StockScoreRefusal:
    scope: RefusalScope
    scope_id: str
    reason: StockScoreRefusalReason
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scope, RefusalScope):
            raise StockSignalError("refusal scope must be typed")
        require_identifier(self.scope_id, "scope_id")
        if not isinstance(self.reason, StockScoreRefusalReason):
            raise StockSignalError("refusal reason must be typed")
        if type(self.evidence_ids) is not tuple or self.evidence_ids != tuple(
            sorted(set(self.evidence_ids))
        ):
            raise StockSignalError("refusal evidence IDs must be unique and sorted")
        for value in self.evidence_ids:
            require_identifier(value, "refusal evidence ID")

    @property
    def sort_key(self) -> tuple[str, str, str, tuple[str, ...]]:
        return (self.scope.value, self.scope_id, self.reason.value, self.evidence_ids)

    def to_record(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "scope_id": self.scope_id,
            "reason": self.reason.value,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclasses.dataclass(frozen=True)
class StructuralStockScoreCandidate:
    schema: str
    authority: str
    decision_session: str
    decision_at: str
    policy_sha256: str
    upstream_identity_result_sha256: str
    structural_evidence_sha256: str
    universe_security_ids: tuple[str, ...]
    contributions: tuple[CanonicalStockContribution, ...]
    sector_normalizations: tuple[SectorNormalizationRecord, ...]
    scores: tuple[StockScoreRow, ...]
    refusals: tuple[StockScoreRefusal, ...]
    residualization_state: str

    def __post_init__(self) -> None:
        if self.schema != STRUCTURAL_STOCK_SCORE_SCHEMA:
            raise StockSignalError("unsupported structural stock-score schema")
        if self.authority != STRUCTURAL_ONLY_AUTHORITY:
            raise StockSignalError(
                "structural candidate cannot acquire production authority"
            )
        parse_date(self.decision_session, "decision_session")
        parse_utc_timestamp(self.decision_at, "decision_at")
        for name in (
            "policy_sha256",
            "upstream_identity_result_sha256",
            "structural_evidence_sha256",
        ):
            require_sha256(getattr(self, name), name)
        if self.universe_security_ids != tuple(
            sorted(set(self.universe_security_ids))
        ):
            raise StockSignalError("universe security IDs must be unique and sorted")
        for value in self.universe_security_ids:
            require_identifier(value, "universe security ID")
        typed = (
            (self.contributions, CanonicalStockContribution, "contributions"),
            (
                self.sector_normalizations,
                SectorNormalizationRecord,
                "sector normalizations",
            ),
            (self.scores, StockScoreRow, "scores"),
            (self.refusals, StockScoreRefusal, "refusals"),
        )
        for values, expected, name in typed:
            if type(values) is not tuple or any(
                type(item) is not expected for item in values
            ):
                raise StockSignalError(f"{name} must be an exact typed tuple")
        if self.contributions != tuple(
            sorted(
                self.contributions,
                key=lambda item: (
                    item.security_id,
                    item.eligible_session,
                    item.institution_id,
                    item.canonical_event_id,
                ),
            )
        ):
            raise StockSignalError("contributions are not canonical-sorted")
        if self.sector_normalizations != tuple(
            sorted(self.sector_normalizations, key=lambda item: item.sector_id)
        ):
            raise StockSignalError("sector normalizations are not sorted")
        if self.scores != tuple(
            sorted(self.scores, key=lambda item: item.security_id)
        ) or len({item.security_id for item in self.scores}) != len(self.scores):
            raise StockSignalError("stock scores must be unique and sorted")
        if self.refusals != tuple(
            sorted(self.refusals, key=lambda item: item.sort_key)
        ):
            raise StockSignalError("stock-score refusals are not canonical-sorted")
        if self.refusals and (self.scores or self.sector_normalizations):
            raise StockSignalError(
                "a refusing cross-section cannot emit a partial score artifact"
            )
        if self.residualization_state != RESIDUALIZATION_BLOCK:
            raise StockSignalError(
                "mandatory-control residualization state was weakened"
            )

    @property
    def pdf_formula_available(self) -> bool:
        return bool(self.scores) and not self.refusals

    @property
    def final_executable_available(self) -> bool:
        return False

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "authority": self.authority,
            "decision_session": self.decision_session,
            "decision_at": self.decision_at,
            "policy_sha256": self.policy_sha256,
            "upstream_identity_result_sha256": self.upstream_identity_result_sha256,
            "structural_evidence_sha256": self.structural_evidence_sha256,
            "universe_security_ids": list(self.universe_security_ids),
            "contributions": [item.to_record() for item in self.contributions],
            "sector_normalizations": [
                item.to_record() for item in self.sector_normalizations
            ],
            "scores": [item.to_record() for item in self.scores],
            "refusals": [item.to_record() for item in self.refusals],
            "residualization_state": self.residualization_state,
        }

    @property
    def candidate_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_record()))


@dataclasses.dataclass(frozen=True)
class StockDiagnosticRow:
    security_id: str
    state: DiagnosticState
    upgrade_count: int
    downgrade_count: int
    directional_breadth: Decimal
    raw_event_count: int
    distinct_institutions: int
    distinct_common_events: int
    event_diversity: int
    institution_effective_n: Decimal
    catalyst_effective_n: Decimal

    def __post_init__(self) -> None:
        require_identifier(self.security_id, "security_id")
        if self.state is not DiagnosticState.AVAILABLE:
            raise StockSignalError("safe structural diagnostics must be available")
        for name in (
            "upgrade_count",
            "downgrade_count",
            "raw_event_count",
            "distinct_institutions",
            "distinct_common_events",
            "event_diversity",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise StockSignalError(f"{name} must be a nonnegative integer")
        for name in (
            "directional_breadth",
            "institution_effective_n",
            "catalyst_effective_n",
        ):
            value = getattr(self, name)
            if type(value) is not Decimal or not value.is_finite():
                raise StockSignalError(f"{name} must be a finite Decimal")

    def to_record(self) -> dict[str, Any]:
        return {
            "security_id": self.security_id,
            "state": self.state.value,
            "upgrade_count": self.upgrade_count,
            "downgrade_count": self.downgrade_count,
            "directional_breadth": _decimal_text(self.directional_breadth),
            "raw_event_count": self.raw_event_count,
            "distinct_institutions": self.distinct_institutions,
            "distinct_common_events": self.distinct_common_events,
            "event_diversity": self.event_diversity,
            "institution_effective_n": _decimal_text(self.institution_effective_n),
            "catalyst_effective_n": _decimal_text(self.catalyst_effective_n),
        }


@dataclasses.dataclass(frozen=True)
class UnavailableDiagnostic:
    channel: DiagnosticChannel
    state: DiagnosticState
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.channel, DiagnosticChannel):
            raise StockSignalError("diagnostic channel must be typed")
        if self.state is not DiagnosticState.UNAVAILABLE:
            raise StockSignalError("deferred diagnostic must remain unavailable")
        require_identifier(self.reason, "diagnostic reason")

    def to_record(self) -> dict[str, str]:
        return {
            "channel": self.channel.value,
            "state": self.state.value,
            "reason": self.reason,
        }


@dataclasses.dataclass(frozen=True)
class StructuralStockDiagnostics:
    schema: str
    canonical_candidate_sha256: str
    rows: tuple[StockDiagnosticRow, ...]
    unavailable: tuple[UnavailableDiagnostic, ...]

    def __post_init__(self) -> None:
        if self.schema != STRUCTURAL_STOCK_DIAGNOSTICS_SCHEMA:
            raise StockSignalError("unsupported structural diagnostics schema")
        require_sha256(self.canonical_candidate_sha256, "canonical candidate hash")
        if type(self.rows) is not tuple or any(
            type(item) is not StockDiagnosticRow for item in self.rows
        ):
            raise StockSignalError("diagnostic rows must be an exact typed tuple")
        if type(self.unavailable) is not tuple or any(
            type(item) is not UnavailableDiagnostic for item in self.unavailable
        ):
            raise StockSignalError(
                "unavailable diagnostics must be an exact typed tuple"
            )
        if self.rows != tuple(sorted(self.rows, key=lambda item: item.security_id)):
            raise StockSignalError("diagnostic rows are not sorted")
        if len({item.security_id for item in self.rows}) != len(self.rows):
            raise StockSignalError("diagnostic rows must have unique security IDs")
        if self.unavailable != tuple(
            sorted(self.unavailable, key=lambda item: item.channel.value)
        ):
            raise StockSignalError("unavailable diagnostics are not sorted")
        unavailable_channels = [item.channel for item in self.unavailable]
        if (
            len(unavailable_channels) != len(set(unavailable_channels))
            or set(unavailable_channels) != set(DiagnosticChannel)
        ):
            raise StockSignalError(
                "unavailable diagnostics must cover each deferred channel once"
            )

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "canonical_candidate_sha256": self.canonical_candidate_sha256,
            "rows": [item.to_record() for item in self.rows],
            "unavailable": [item.to_record() for item in self.unavailable],
        }

    @property
    def diagnostics_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_record()))


def _decision_context(decision_session: str) -> tuple[str, Any, date]:
    try:
        if not is_trading_session(decision_session):
            raise StockSignalError("decision_session is not an NYSE session")
        instant = session_open_instant(decision_session)
    except ExchangeCalendarError as exc:
        raise StockSignalError("decision_session is not an NYSE session") from exc
    return (
        format_utc_timestamp(instant),
        instant,
        parse_date(decision_session, "decision_session"),
    )


def _active_as_of(record: object, *, decision_date: date, decision_at) -> bool:
    if (
        parse_utc_timestamp(getattr(record, "available_at"), "available_at")
        > decision_at
    ):
        return False
    visible_to = _master_visible_valid_to(
        valid_to=getattr(record, "valid_to"),
        valid_to_available_at=getattr(record, "valid_to_available_at"),
        decision_at=decision_at,
    )
    return _interval_contains(
        getattr(record, "valid_from"), visible_to, decision_date
    )


def _evidence_interval_active_as_of(
    record: InstitutionMappingEvidence | SectorClassificationEvidence,
    *,
    effective_date: date,
    decision_at,
) -> bool:
    """Use evidence known strictly before the decision-open instant."""
    if parse_utc_timestamp(record.available_at, "evidence.available_at") >= decision_at:
        return False
    visible_to = _visible_valid_to(
        valid_to=record.valid_to,
        valid_to_available_at=record.valid_to_available_at,
        decision_at=decision_at,
    )
    return _interval_contains(record.valid_from, visible_to, effective_date)


def _eligible_universe(
    master: PointInTimeSecurityMaster, *, decision_date: date, decision_at
) -> tuple[str, ...]:
    revalidate_pit_security_master(master)
    issuers = {item.issuer_id: item for item in master.issuers}
    listings_by_security: dict[str, list[object]] = defaultdict(list)
    for listing in master.listings:
        listings_by_security[listing.security_id].append(listing)
    eligible: list[str] = []
    for security in master.securities:
        issuer = issuers[security.issuer_id]
        if (
            security.security_type is not SecurityType.COMMON_STOCK
            or issuer.incorporation_country != ELIGIBLE_ISSUER_COUNTRY
            or not _active_as_of(
                issuer,
                decision_date=decision_date,
                decision_at=decision_at,
            )
            or not _active_as_of(
                security,
                decision_date=decision_date,
                decision_at=decision_at,
            )
        ):
            continue
        active_listing = any(
            listing.country == ELIGIBLE_ISSUER_COUNTRY
            and listing.exchange in ELIGIBLE_LISTING_EXCHANGES
            and _active_as_of(
                listing, decision_date=decision_date, decision_at=decision_at
            )
            for listing in listings_by_security.get(security.security_id, ())
        )
        if active_listing:
            eligible.append(security.security_id)
    return tuple(sorted(eligible))


def _session_age_map(
    eligible_sessions: Iterable[str], decision_session: str
) -> dict[str, int]:
    unique_sessions = tuple(sorted(set(eligible_sessions)))
    if not unique_sessions:
        return {}
    eligible_dates = {
        session: parse_date(session, "eligible_session")
        for session in unique_sessions
    }
    decision_date = parse_date(decision_session, "decision_session")
    if any(value > decision_date for value in eligible_dates.values()):
        raise StockSignalError("future eligible session has no nonnegative age")
    try:
        sessions = trading_sessions(
            min(eligible_dates.values()), decision_date
        )
    except ExchangeCalendarError as exc:
        raise StockSignalError(
            "event age cannot be derived from NYSE sessions"
        ) from exc
    if not sessions or sessions[-1] != decision_date:
        raise StockSignalError("decision date is not an NYSE session")
    index_by_date = {session: index for index, session in enumerate(sessions)}
    if any(value not in index_by_date for value in eligible_dates.values()):
        raise StockSignalError("event date is not an NYSE session")
    decision_index = len(sessions) - 1
    return {
        text: decision_index - index_by_date[value]
        for text, value in eligible_dates.items()
    }


def _fraction_decimal(value: Fraction) -> Decimal:
    with analyst_decimal_context():
        return Decimal(value.numerator) / Decimal(value.denominator)


def _stable_sum(values: Iterable[Decimal]) -> Decimal:
    return sum(sorted(values, key=lambda value: (abs(value), value)), Decimal("0"))


def _refusal(
    scope: RefusalScope,
    scope_id: str,
    reason: StockScoreRefusalReason,
    *evidence_ids: str,
) -> StockScoreRefusal:
    return StockScoreRefusal(
        scope,
        scope_id,
        reason,
        tuple(sorted(set(evidence_ids))),
    )


def _candidate(
    *,
    decision_session: str,
    decision_at: str,
    policy: VerifiedAnalystPolicy,
    upstream: IdentityResolvedFirmRatingResult,
    evidence: StructuralStockScoreEvidence,
    universe: tuple[str, ...],
    contributions: tuple[CanonicalStockContribution, ...] = (),
    sectors: tuple[SectorNormalizationRecord, ...] = (),
    scores: tuple[StockScoreRow, ...] = (),
    refusals: Iterable[StockScoreRefusal] = (),
) -> StructuralStockScoreCandidate:
    canonical_refusals = tuple(sorted(set(refusals), key=lambda item: item.sort_key))
    if canonical_refusals:
        sectors = ()
        scores = ()
    return StructuralStockScoreCandidate(
        schema=STRUCTURAL_STOCK_SCORE_SCHEMA,
        authority=STRUCTURAL_ONLY_AUTHORITY,
        decision_session=decision_session,
        decision_at=decision_at,
        policy_sha256=policy.evidence_sha256,
        upstream_identity_result_sha256=upstream.result_sha256,
        structural_evidence_sha256=evidence.evidence_sha256,
        universe_security_ids=universe,
        contributions=tuple(
            sorted(
                contributions,
                key=lambda item: (
                    item.security_id,
                    item.eligible_session,
                    item.institution_id,
                    item.canonical_event_id,
                ),
            )
        ),
        sector_normalizations=tuple(sorted(sectors, key=lambda item: item.sector_id)),
        scores=tuple(sorted(scores, key=lambda item: item.security_id)),
        refusals=canonical_refusals,
        residualization_state=RESIDUALIZATION_BLOCK,
    )


def build_structural_stock_score_candidate(
    upstream: IdentityResolvedFirmRatingResult,
    evidence: StructuralStockScoreEvidence,
    *,
    decision_session: str,
    policy: VerifiedAnalystPolicy,
    firm_result: FirmRatingNormalizationResult,
    identity_audit: SecurityIdentityAudit,
    ingest_audit: BenzingaIngestAudit,
    ontology: ReviewedFirmRatingOntology,
    master: PointInTimeSecurityMaster,
) -> StructuralStockScoreCandidate:
    """Build a revalidatable fixture-only PDF stock-score candidate.

    All event timing, security identity, exact rating changes and daily dedupe
    keys are derived inside this function. Caller-supplied age, event session,
    security and economic deltas are never accepted.
    """
    verified_policy = require_verified_analyst_policy(policy)
    revalidate_identity_resolved_firm_rating_result(
        upstream,
        firm_result=firm_result,
        identity_audit=identity_audit,
        ingest_audit=ingest_audit,
        ontology=ontology,
        master=master,
    )
    if type(evidence) is not StructuralStockScoreEvidence:
        raise StockSignalError("score evidence must be exact structural evidence")
    decision_at_text, decision_at, decision_date = _decision_context(decision_session)
    universe = _eligible_universe(
        master, decision_date=decision_date, decision_at=decision_at
    )
    global_refusals: list[StockScoreRefusal] = []
    if (
        evidence.source_audit_sha256 != upstream.source_audit_sha256
        or evidence.security_master_id != upstream.security_master_id
        or evidence.security_master_sha256 != upstream.security_master_sha256
    ):
        global_refusals.append(
            _refusal(
                RefusalScope.GLOBAL,
                "cross-section",
                StockScoreRefusalReason.EVIDENCE_BINDING_MISMATCH,
                evidence.evidence_sha256,
            )
        )
    snapshot = ingest_audit.snapshot
    if parse_utc_timestamp(snapshot.captured_at, "captured_at") != decision_at:
        global_refusals.append(
            _refusal(
                RefusalScope.GLOBAL,
                "source-vintage",
                StockScoreRefusalReason.SOURCE_SNAPSHOT_NOT_DECISION_VINTAGE,
                snapshot.snapshot_id,
            )
        )
    if (
        snapshot.requested_first_year != ELIGIBLE_HISTORY_FIRST_YEAR
        or snapshot.requested_last_year != decision_date.year
    ):
        global_refusals.append(
            _refusal(
                RefusalScope.GLOBAL,
                "source-history",
                StockScoreRefusalReason.SOURCE_HISTORY_RANGE_INCOMPLETE,
                snapshot.snapshot_id,
            )
        )
    late_rows = tuple(
        record.provider_event_id
        for record in ingest_audit.records
        if parse_utc_timestamp(record.last_updated_at, "last_updated_at")
        > decision_at
    )
    if late_rows:
        global_refusals.append(
            _refusal(
                RefusalScope.GLOBAL,
                "source-chronology",
                StockScoreRefusalReason.SOURCE_ROW_AFTER_CAPTURE,
                *late_rows,
            )
        )
    if ingest_audit.refusals:
        global_refusals.append(
            _refusal(
                RefusalScope.GLOBAL,
                "source-ingest",
                StockScoreRefusalReason.SOURCE_INGEST_REFUSAL,
                *(item.evidence_sha256 for item in ingest_audit.refusals),
            )
        )
    blocking_upstream_refusals = tuple(
        item
        for item in upstream.refusals
        if not (
            item.stage is CombinedRefusalStage.IDENTITY
            and item.reason in PROVEN_INELIGIBLE_IDENTITY_REFUSAL_REASONS
        )
    )
    if blocking_upstream_refusals:
        global_refusals.append(
            _refusal(
                RefusalScope.GLOBAL,
                "identity-ontology",
                StockScoreRefusalReason.UPSTREAM_IDENTITY_OR_ONTOLOGY_REFUSAL,
                *(
                    item.source_event.provider_event_id
                    for item in blocking_upstream_refusals
                ),
            )
        )
    if not universe:
        global_refusals.append(
            _refusal(
                RefusalScope.GLOBAL,
                "eligible-universe",
                StockScoreRefusalReason.NO_ELIGIBLE_UNIVERSE,
                master.security_master_id,
            )
        )

    classifications_by_security: dict[
        str, list[SectorClassificationEvidence]
    ] = defaultdict(list)
    for item in evidence.sector_classifications:
        classifications_by_security[item.security_id].append(item)
    sector_by_security: dict[str, str] = {}
    for security_id in universe:
        rows = classifications_by_security.get(security_id, ())
        visible = [
            item
            for item in rows
            if _evidence_interval_active_as_of(
                item, effective_date=decision_date, decision_at=decision_at
            )
        ]
        late = [
            item
            for item in rows
            if _interval_contains(item.valid_from, item.valid_to, decision_date)
            if parse_utc_timestamp(item.available_at, "classification.available_at")
            >= decision_at
        ]
        if not visible and not late:
            global_refusals.append(
                _refusal(
                    RefusalScope.GLOBAL,
                    security_id,
                    StockScoreRefusalReason.MISSING_SECTOR_CLASSIFICATION,
                    security_id,
                )
            )
        elif not visible:
            global_refusals.append(
                _refusal(
                    RefusalScope.GLOBAL,
                    security_id,
                    StockScoreRefusalReason.LATE_SECTOR_CLASSIFICATION,
                    *(item.source_evidence_sha256 for item in late),
                )
            )
        elif len(visible) != 1:
            global_refusals.append(
                _refusal(
                    RefusalScope.GLOBAL,
                    security_id,
                    StockScoreRefusalReason.AMBIGUOUS_SECTOR_CLASSIFICATION,
                    *(item.source_evidence_sha256 for item in visible),
                )
            )
        else:
            sector_by_security[security_id] = visible[0].sector_id
    if global_refusals:
        return _candidate(
            decision_session=decision_session,
            decision_at=decision_at_text,
            policy=verified_policy,
            upstream=upstream,
            evidence=evidence,
            universe=universe,
            refusals=global_refusals,
        )

    institutions_by_firm: dict[
        str, list[InstitutionMappingEvidence]
    ] = defaultdict(list)
    for item in evidence.institution_mappings:
        institutions_by_firm[item.provider_firm_id].append(item)
    catalysts_by_event = {
        item.provider_event_id: item for item in evidence.common_events
    }
    bridge: dict[
        str,
        tuple[object, InstitutionMappingEvidence, CommonEventEvidence, str],
    ] = {}
    candidates: list[DailyRatingContributionCandidate] = []
    refusals: list[StockScoreRefusal] = []
    invalid_security_ids: set[str] = set()
    for item in upstream.events:
        event = item.firm_event
        if event.rating_change is None:
            continue
        if item.identity.security_id not in sector_by_security:
            continue
        source = event.source_event
        try:
            availability = derive_event_availability(
                evidence_id=source.provider_version_id,
                public_date=source.conservative_public_date,
            )
        except AvailabilityError as exc:
            raise StockSignalError("source availability cannot be re-derived") from exc
        if (
            parse_date(availability.eligible_session, "eligible_session")
            > decision_date
        ):
            continue
        firm_mappings = institutions_by_firm.get(source.provider_firm_id, ())
        visible_mappings = [
            mapping
            for mapping in firm_mappings
            if _evidence_interval_active_as_of(
                mapping,
                effective_date=parse_date(source.action_date, "action_date"),
                decision_at=decision_at,
            )
        ]
        late_mappings = [
            mapping
            for mapping in firm_mappings
            if _interval_contains(
                mapping.valid_from,
                mapping.valid_to,
                parse_date(source.action_date, "action_date"),
            )
            if parse_utc_timestamp(mapping.available_at, "institution.available_at")
            >= decision_at
        ]
        event_identity = {
            "provider_version_id": source.provider_version_id,
            "source_locator": source.source_locator.to_record(),
            "identity_evidence": (
                item.identity.identity_mapping_evidence_sha256
            ),
            "ontology_sha256": event.ontology_sha256,
        }
        event_id = (
            "arv2-score-event-"
            f"{sha256_bytes(canonical_json_bytes(event_identity))}"
        )
        if not visible_mappings and not late_mappings:
            reason = StockScoreRefusalReason.MISSING_INSTITUTION_MAPPING
        elif not visible_mappings:
            reason = StockScoreRefusalReason.LATE_INSTITUTION_MAPPING
        elif len(visible_mappings) != 1:
            reason = StockScoreRefusalReason.AMBIGUOUS_INSTITUTION_MAPPING
        else:
            reason = None
        if reason is not None:
            invalid_security_ids.add(item.identity.security_id)
            refusals.append(
                _refusal(
                    RefusalScope.EVENT,
                    event_id,
                    reason,
                    source.provider_event_id,
                    *(
                        mapping.source_evidence_sha256
                        for mapping in (*visible_mappings, *late_mappings)
                    ),
                )
            )
            continue
        catalyst = catalysts_by_event.get(source.provider_event_id)
        if catalyst is None:
            invalid_security_ids.add(item.identity.security_id)
            refusals.append(
                _refusal(
                    RefusalScope.EVENT,
                    event_id,
                    StockScoreRefusalReason.MISSING_COMMON_EVENT_EVIDENCE,
                    source.provider_event_id,
                )
            )
            continue
        if (
            parse_utc_timestamp(
                catalyst.available_at, "common_event.available_at"
            )
            >= decision_at
        ):
            invalid_security_ids.add(item.identity.security_id)
            refusals.append(
                _refusal(
                    RefusalScope.EVENT,
                    event_id,
                    StockScoreRefusalReason.LATE_COMMON_EVENT_EVIDENCE,
                    catalyst.source_evidence_sha256,
                )
            )
            continue
        mapping = visible_mappings[0]
        previous = event.previous_mapping
        current = event.current_mapping
        if previous is None or current is None:
            raise StockSignalError("directional event lost exact firm mappings")
        candidates.append(
            DailyRatingContributionCandidate(
                canonical_event_id=event_id,
                institution_id=mapping.institution_id,
                security_id=item.identity.security_id,
                trading_day=availability.eligible_session,
                previous_score=previous.score,
                current_score=current.score,
            )
        )
        bridge[event_id] = (item, mapping, catalyst, availability.eligible_session)

    dedupe = deduplicate_daily_rating_contributions(tuple(candidates))
    for refusal in dedupe.refusals:
        invalid_security_ids.add(refusal.security_id)
        refusals.append(
            _refusal(
                RefusalScope.SECURITY,
                refusal.security_id,
                StockScoreRefusalReason.DAILY_DEDUPE_CONFLICT,
                *refusal.linked_event_ids,
            )
        )
    age_by_session = _session_age_map(
        (
            bridge[daily.contributing_event_id][3]
            for daily in dedupe.contributions
        ),
        decision_session,
    )
    decay_by_age: dict[int, Decimal] = {}
    contributions: list[CanonicalStockContribution] = []
    for daily in dedupe.contributions:
        linked = [bridge[event_id] for event_id in daily.linked_event_ids]
        catalysts = {value[2].common_event_id for value in linked}
        if len(catalysts) != 1:
            invalid_security_ids.add(daily.security_id)
            refusals.append(
                _refusal(
                    RefusalScope.SECURITY,
                    daily.security_id,
                    StockScoreRefusalReason.CONFLICTING_COMMON_EVENT_EVIDENCE,
                    *daily.linked_event_ids,
                )
            )
            continue
        source_item, _, catalyst, eligible_session = bridge[daily.contributing_event_id]
        age = age_by_session[eligible_session]
        decay = decay_by_age.get(age)
        if decay is None:
            decay = rating_decay_weight(age, policy=verified_policy)
            decay_by_age[age] = decay
        with analyst_decimal_context():
            decayed = _fraction_decimal(daily.rating_change) * decay
        source_event = source_item.firm_event.source_event
        contributions.append(
            CanonicalStockContribution(
                canonical_event_id=daily.contributing_event_id,
                provider_event_id=source_event.provider_event_id,
                provider_version_id=source_event.provider_version_id,
                linked_event_ids=daily.linked_event_ids,
                institution_id=daily.institution_id,
                common_event_id=next(iter(catalysts)),
                security_id=daily.security_id,
                eligible_session=eligible_session,
                age_sessions=age,
                rating_change=daily.rating_change,
                decay_weight=decay,
                decayed_value=decayed,
                identity_mapping_evidence_sha256=(
                    source_item.identity.identity_mapping_evidence_sha256
                ),
                ontology_sha256=source_item.firm_event.ontology_sha256,
                common_event_evidence_sha256=catalyst.source_evidence_sha256,
            )
        )

    contributions_by_security: dict[
        str, list[CanonicalStockContribution]
    ] = defaultdict(list)
    for item in contributions:
        contributions_by_security[item.security_id].append(item)
    quality_by_key = {
        (item.security_id, item.measured_session): item
        for item in evidence.data_quality
    }
    for security_id in universe:
        quality = quality_by_key.get((security_id, decision_session))
        sector_id = sector_by_security[security_id]
        if quality is None:
            invalid_security_ids.add(security_id)
            refusals.append(
                _refusal(
                    RefusalScope.SECURITY,
                    security_id,
                    StockScoreRefusalReason.MISSING_DATA_QUALITY,
                    evidence.quality_source_id,
                )
            )
        elif (
            parse_utc_timestamp(quality.available_at, "quality.available_at")
            >= decision_at
        ):
            invalid_security_ids.add(security_id)
            refusals.append(
                _refusal(
                    RefusalScope.SECURITY,
                    security_id,
                    StockScoreRefusalReason.LATE_DATA_QUALITY,
                    quality.source_evidence_sha256,
                )
            )
        if security_id in invalid_security_ids:
            refusals.append(
                _refusal(
                    RefusalScope.SECTOR,
                    sector_id,
                    StockScoreRefusalReason.SECTOR_CONTAINS_INVALID_SECURITY,
                    security_id,
                )
            )

    raw_scores: dict[str, Decimal] = {}
    raw_states: dict[str, StockRawState] = {}
    breadth_by_security = {}
    for security_id in universe:
        rows = contributions_by_security.get(security_id, ())
        with analyst_decimal_context():
            raw_scores[security_id] = _stable_sum(item.decayed_value for item in rows)
        raw_states[security_id] = (
            StockRawState.ACTIVE if rows else StockRawState.STRUCTURAL_ZERO
        )
        breadth_by_security[security_id] = independent_evidence_breadth(
            IndependentContribution(
                item.institution_id,
                item.common_event_id,
                abs(item.decayed_value),
            )
            for item in rows
        )

    sectors_by_id: dict[str, list[str]] = defaultdict(list)
    for security_id, sector_id in sector_by_security.items():
        sectors_by_id[sector_id].append(security_id)
    sector_records: list[SectorNormalizationRecord] = []
    score_rows: list[StockScoreRow] = []
    refusing_sector_ids = {
        item.scope_id for item in refusals if item.scope is RefusalScope.SECTOR
    }
    normalization_by_sector = {}
    for sector_id in sorted(sectors_by_id):
        if sector_id in refusing_sector_ids:
            continue
        observations = tuple(
            ActivityAwareObservation(
                security_id,
                (
                    ActivityObservationState.ACTIVE
                    if raw_states[security_id] is StockRawState.ACTIVE
                    else ActivityObservationState.STRUCTURAL_ZERO
                ),
                raw_scores[security_id],
            )
            for security_id in sorted(sectors_by_id[sector_id])
        )
        try:
            normalized = robust_activity_group_normalize(
                observations, policy=verified_policy
            )
        except FormulaError as exc:
            raise StockSignalError("sector normalization input is invalid") from exc
        if not normalized.available:
            reason_by_formula = {
                "insufficient_total_names": (
                    StockScoreRefusalReason.INSUFFICIENT_TOTAL_NAMES
                ),
                "insufficient_active_names": (
                    StockScoreRefusalReason.INSUFFICIENT_ACTIVE_NAMES
                ),
                "zero_mad": StockScoreRefusalReason.ZERO_MAD,
            }
            refusals.append(
                _refusal(
                    RefusalScope.SECTOR,
                    sector_id,
                    reason_by_formula[normalized.reason],
                    sector_id,
                )
            )
            continue
        normalization_by_sector[sector_id] = normalized
        sector_records.append(
            SectorNormalizationRecord(
                sector_id,
                normalized.total_names,
                normalized.active_names,
                normalized.median,
                normalized.mad,
            )
        )
    if not refusals:
        for security_id in universe:
            sector_id = sector_by_security[security_id]
            normalized = normalization_by_sector[sector_id]
            breadth = breadth_by_security[security_id]
            quality = quality_by_key[(security_id, decision_session)]
            reliability = stock_reliability(
                independent_effective_n=breadth.independent_effective_n,
                quality=quality.q_data,
            )
            with analyst_decimal_context():
                reliable = normalized.standardized[security_id] * reliability
            score_rows.append(
                StockScoreRow(
                    security_id=security_id,
                    sector_id=sector_id,
                    raw_state=raw_states[security_id],
                    raw_score=raw_scores[security_id],
                    sector_z=normalized.standardized[security_id],
                    institution_effective_n=breadth.institution_effective_n,
                    catalyst_effective_n=breadth.catalyst_effective_n,
                    independent_effective_n=breadth.independent_effective_n,
                    q_data=quality.q_data,
                    reliability=reliability,
                    pdf_reliable_score=reliable,
                )
            )
    return _candidate(
        decision_session=decision_session,
        decision_at=decision_at_text,
        policy=verified_policy,
        upstream=upstream,
        evidence=evidence,
        universe=universe,
        contributions=tuple(contributions),
        sectors=tuple(sector_records),
        scores=tuple(score_rows),
        refusals=refusals,
    )


def revalidate_structural_stock_score_candidate(
    candidate: StructuralStockScoreCandidate,
    upstream: IdentityResolvedFirmRatingResult,
    evidence: StructuralStockScoreEvidence,
    *,
    policy: VerifiedAnalystPolicy,
    firm_result: FirmRatingNormalizationResult,
    identity_audit: SecurityIdentityAudit,
    ingest_audit: BenzingaIngestAudit,
    ontology: ReviewedFirmRatingOntology,
    master: PointInTimeSecurityMaster,
) -> StructuralStockScoreCandidate:
    if type(candidate) is not StructuralStockScoreCandidate:
        raise StockSignalError("candidate revalidation requires the exact result type")
    rebuilt = build_structural_stock_score_candidate(
        upstream,
        evidence,
        decision_session=candidate.decision_session,
        policy=policy,
        firm_result=firm_result,
        identity_audit=identity_audit,
        ingest_audit=ingest_audit,
        ontology=ontology,
        master=master,
    )
    if rebuilt != candidate:
        raise StockSignalError("structural stock-score candidate is not source-derived")
    return candidate


def build_structural_stock_diagnostics(
    candidate: StructuralStockScoreCandidate,
    upstream: IdentityResolvedFirmRatingResult,
    evidence: StructuralStockScoreEvidence,
    *,
    policy: VerifiedAnalystPolicy,
    firm_result: FirmRatingNormalizationResult,
    identity_audit: SecurityIdentityAudit,
    ingest_audit: BenzingaIngestAudit,
    ontology: ReviewedFirmRatingOntology,
    master: PointInTimeSecurityMaster,
) -> StructuralStockDiagnostics:
    """Build isolated diagnostics from a fully revalidated structural candidate."""
    candidate = revalidate_structural_stock_score_candidate(
        candidate,
        upstream,
        evidence,
        policy=policy,
        firm_result=firm_result,
        identity_audit=identity_audit,
        ingest_audit=ingest_audit,
        ontology=ontology,
        master=master,
    )
    if candidate.refusals:
        raise StockSignalError(
            "diagnostics are unavailable for a refusing structural candidate"
        )
    by_security: dict[str, list[CanonicalStockContribution]] = defaultdict(list)
    for item in candidate.contributions:
        by_security[item.security_id].append(item)
    rows: list[StockDiagnosticRow] = []
    for security_id in candidate.universe_security_ids:
        contributions = by_security.get(security_id, ())
        upgrades = sum(item.rating_change > 0 for item in contributions)
        downgrades = sum(item.rating_change < 0 for item in contributions)
        with analyst_decimal_context():
            directional = Decimal(upgrades - downgrades) / Decimal(
                max(upgrades + downgrades, 1)
            )
        raw_events = sum(len(item.linked_event_ids) for item in contributions)
        institutions = {item.institution_id for item in contributions}
        catalysts = {item.common_event_id for item in contributions}
        breadth = independent_evidence_breadth(
            IndependentContribution(
                item.institution_id,
                item.common_event_id,
                abs(item.decayed_value),
            )
            for item in contributions
        )
        rows.append(
            StockDiagnosticRow(
                security_id=security_id,
                state=DiagnosticState.AVAILABLE,
                upgrade_count=upgrades,
                downgrade_count=downgrades,
                directional_breadth=directional,
                raw_event_count=raw_events,
                distinct_institutions=len(institutions),
                distinct_common_events=len(catalysts),
                event_diversity=len(catalysts),
                institution_effective_n=breadth.institution_effective_n,
                catalyst_effective_n=breadth.catalyst_effective_n,
            )
        )
    unavailable = tuple(
        sorted(
            (
                UnavailableDiagnostic(
                    DiagnosticChannel.UNIQUE_ANALYSTS,
                    DiagnosticState.UNAVAILABLE,
                    "requires_authenticated_permanent_analyst_identity",
                ),
                UnavailableDiagnostic(
                    DiagnosticChannel.CONSENSUS_NOVELTY,
                    DiagnosticState.UNAVAILABLE,
                    "requires_pit_consensus_state",
                ),
                UnavailableDiagnostic(
                    DiagnosticChannel.PRICE_TARGET_REVISION,
                    DiagnosticState.UNAVAILABLE,
                    "requires_price_target_family_and_pre_event_price",
                ),
                UnavailableDiagnostic(
                    DiagnosticChannel.EPS_REVISION,
                    DiagnosticState.UNAVAILABLE,
                    "requires_pit_eps_estimate_family",
                ),
                UnavailableDiagnostic(
                    DiagnosticChannel.ANALYST_QUALITY,
                    DiagnosticState.UNAVAILABLE,
                    "requires_outcomes_and_later_stage_authority",
                ),
            ),
            key=lambda item: item.channel.value,
        )
    )
    return StructuralStockDiagnostics(
        schema=STRUCTURAL_STOCK_DIAGNOSTICS_SCHEMA,
        canonical_candidate_sha256=candidate.candidate_sha256,
        rows=tuple(rows),
        unavailable=unavailable,
    )
