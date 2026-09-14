"""Pure production-shaped input admission for Analyst Revisions V2.

This module bridges one authenticated ARV2-4F-C1 accepted-risk input pair to
normalized, *pre-outcome* directional rating rows.  Every C1 source row gets
exactly one named terminal disposition.  A row is admitted only when
caller-supplied, content-addressed evidence proves a unique historical
security identity, a reviewed firm-specific rating scale, a common-event
identity, point-in-time sector and control facts, and measured ``q_data``.

The bridge deliberately performs no I/O.  It cannot read a provider, a
credential, a file, QuantConnect, Object Store, a price, or an outcome.  Its
builder-authenticated objects are offline candidates only: real evidence must
later be admitted by separately reviewed production registries and run gates.
"""
from __future__ import annotations

import dataclasses
import heapq
import re
import threading
import weakref
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from typing import Any

from .accepted_risk_input_pair import (
    CENSORED_VIEW_LABEL,
    CURRENT_VIEW_LABEL,
    INPUT_PAIR_CONTRACT_ID,
    INPUT_PAIR_CONTRACT_SHA256,
    AcceptedRiskInputPair,
    AcceptedRiskSourceRow,
    CaptureRowLocator,
    InputView,
    MassiveSourceRole,
    RowDisposition,
    require_accepted_risk_input_pair,
)
from .canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    parse_date,
    parse_utc_timestamp,
    require_exact_bool,
    require_identifier,
    require_int,
    require_sha256,
    require_text,
    require_ticker,
    sha256_bytes,
    strict_json_loads,
)


PRODUCTION_INPUT_CONTRACT_SCHEMA = "arv2-production-input-contract-v1"
PRODUCTION_EVIDENCE_SCHEMA = "arv2-production-input-evidence-v1"
PRODUCTION_INPUT_BATCH_SCHEMA = "arv2-production-pre-outcome-batch-v1"
PRODUCTION_INPUT_STATUS = (
    "offline_caller_supplied_production_shaped_pending_external_registration"
)
NON_PRISTINE_DISCLOSURE = (
    "massive_current_rows_overwrite_same_id_versions_and_omit_deletion_history"
)
PROVIDER_VERSION_PREFIX = "arv2_bz_current_version_"
COMPARISON_REPORT_SCHEMA = "arv2-production-input-comparison-report-v1"
ELIGIBILITY_CROSS_SECTION_SCOPE = (
    "eligibility_session_audit_only_not_reusable_for_later_decision_sessions"
)


class ProductionInputError(CanonicalEvidenceError):
    """The evidence or pre-outcome admission result is not authoritative."""


class SignalArm(str, Enum):
    """Economic input arm; deliberately not a provider source role."""

    CURRENT_VINTAGE = "current_vintage"
    CONSERVATIVE_CENSORED = "conservative_censored"


_ARM_TO_VIEW = MappingProxyType({
    SignalArm.CURRENT_VINTAGE: InputView.CURRENT_ROW,
    SignalArm.CONSERVATIVE_CENSORED: InputView.CONSERVATIVE_CENSORED,
})
_ARM_TO_LABEL = MappingProxyType({
    SignalArm.CURRENT_VINTAGE: CURRENT_VIEW_LABEL,
    SignalArm.CONSERVATIVE_CENSORED: CENSORED_VIEW_LABEL,
})


class EvidenceSourceKind(str, Enum):
    SECURITY_MASTER = "security_master"
    FIRM_ONTOLOGY = "firm_ontology"
    COMMON_EVENT = "common_event"
    SECTOR_CLASSIFICATION = "sector_classification"
    PREOPEN_CONTROL = "preopen_control"
    DATA_QUALITY = "data_quality"


_SOURCE_ORDER = tuple(EvidenceSourceKind)


class AdmissionDisposition(str, Enum):
    INCLUDED_DIRECTIONAL_RATING_REVISION = "included_directional_rating_revision"
    SOURCE_VIEW_EXCLUDED = "source_view_excluded"
    NON_RATING_SOURCE_ROLE = "non_rating_source_role"
    GUIDANCE_CLOCK_QUARANTINED = "guidance_clock_quarantined"
    PRE_2013_QUARANTINED = "pre_2013_quarantined"
    UNSUPPORTED_RATING_ROW_SCHEMA = "unsupported_rating_row_schema"
    INVALID_RATING_ROW = "invalid_rating_row"
    NON_DIRECTIONAL_RATING_ACTION = "non_directional_rating_action"
    UNSUPPORTED_RATING_ACTION = "unsupported_rating_action"
    UNKNOWN_RATING_ACTION = "unknown_rating_action"
    MISSING_ROW_EVIDENCE = "missing_row_evidence"
    UNREVIEWED_EVIDENCE_SOURCE = "unreviewed_evidence_source"
    NON_PIT_EVIDENCE_SOURCE = "non_pit_evidence_source"
    SECURITY_IDENTITY_CURRENT_TICKER_ONLY = "security_identity_current_ticker_only"
    MISSING_PIT_SECURITY_EVIDENCE = "missing_pit_security_evidence"
    SECURITY_IDENTITY_NOT_PIT = "security_identity_not_pit"
    SECURITY_IDENTITY_AMBIGUOUS = "security_identity_ambiguous"
    SECURITY_IDENTITY_MISMATCH = "security_identity_mismatch"
    SECURITY_IDENTITY_LATE = "security_identity_late"
    FIRM_ONTOLOGY_UNREVIEWED = "firm_ontology_unreviewed"
    MISSING_FIRM_ONTOLOGY_EVIDENCE = "missing_firm_ontology_evidence"
    FIRM_LABEL_UNREVIEWED = "firm_label_unreviewed"
    FIRM_MAPPING_AMBIGUOUS = "firm_mapping_ambiguous"
    FIRM_MAPPING_MISMATCH = "firm_mapping_mismatch"
    FIRM_MAPPING_LATE = "firm_mapping_late"
    RATING_DIRECTION_MISMATCH = "rating_direction_mismatch"
    MISSING_COMMON_EVENT_EVIDENCE = "missing_common_event_evidence"
    COMMON_EVENT_AMBIGUOUS = "common_event_ambiguous"
    COMMON_EVENT_MISMATCH = "common_event_mismatch"
    COMMON_EVENT_LATE = "common_event_late"
    MISSING_PIT_SECTOR_EVIDENCE = "missing_pit_sector_evidence"
    SECTOR_AMBIGUOUS = "sector_ambiguous"
    SECTOR_NOT_PIT = "sector_not_pit"
    SECTOR_MISMATCH = "sector_mismatch"
    SECTOR_LATE = "sector_late"
    MISSING_PREOPEN_CONTROL_EVIDENCE = "missing_preopen_control_evidence"
    CONTROL_NOT_PIT = "control_not_pit"
    CONTROL_MISMATCH = "control_mismatch"
    CONTROL_LATE = "control_late"
    CONTROL_CONTAINS_OUTCOME_OR_PRICE = "control_contains_outcome_or_price"
    MISSING_Q_DATA_EVIDENCE = "missing_q_data_evidence"
    Q_DATA_NOT_PIT = "q_data_not_pit"
    Q_DATA_MISMATCH = "q_data_mismatch"
    Q_DATA_LATE = "q_data_late"


_DIRECTIONAL_ACTIONS = frozenset({"upgrades", "downgrades"})
_KNOWN_NON_DIRECTIONAL_ACTIONS = frozenset(
    {
        "initiates_coverage_on",
        "reinstates",
        "reiterates",
        "maintains",
        "terminates_coverage_on",
        "removes",
        "suspends",
        "firm_dissolved",
    }
)
_UNSUPPORTED_DOCUMENTED_ACTIONS = frozenset({"assumes"})
_KNOWN_RATING_ACTIONS = _DIRECTIONAL_ACTIONS | _KNOWN_NON_DIRECTIONAL_ACTIONS
_TARGET_ONLY_ACTION = "__price_target_only__"
_PROVIDER_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
    r"(?:\.\d{1,6})?(?:Z|[+-](?:0\d|1\d|2[0-3]):[0-5]\d)"
)


class ComparisonDimension(str, Enum):
    OVERALL = "overall"
    EVENT_YEAR = "event_year"
    ACTION = "action"
    FIRM = "firm"
    SECURITY = "security"


def _exact_decimal(value: object, name: str) -> Decimal:
    if type(value) is Decimal:
        parsed = value
    elif type(value) is int:
        parsed = Decimal(value)
    elif type(value) is str and value and value == value.strip():
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise ProductionInputError(f"{name} must be an exact decimal") from exc
    else:
        raise ProductionInputError(f"{name} must be exact and cannot be bool/float")
    if not parsed.is_finite():
        raise ProductionInputError(f"{name} must be finite")
    return parsed


def _decimal_text(value: Decimal) -> str:
    return "0" if value == 0 else format(value, "f")


def _fraction_record(value: Fraction) -> list[int]:
    return [value.numerator, value.denominator]


def _require_exact_strings(value: object, names: tuple[str, ...], context: str) -> None:
    for name in names:
        if type(getattr(value, name)) is not str:
            raise ProductionInputError(f"{context}.{name} must be an exact string")


def _require_optional_exact_string(value: object, name: str, context: str) -> None:
    item = getattr(value, name)
    if item is not None and type(item) is not str:
        raise ProductionInputError(f"{context}.{name} must be an exact string or null")


def _validate_interval(
    valid_from: str,
    valid_to: str | None,
    valid_to_available_at: str | None,
    available_at: str,
    name: str,
) -> None:
    start = parse_date(valid_from, f"{name}.valid_from")
    end = None if valid_to is None else parse_date(valid_to, f"{name}.valid_to")
    if end is not None and end <= start:
        raise ProductionInputError(f"{name} validity interval is empty/reversed")
    if (valid_to is None) != (valid_to_available_at is None):
        raise ProductionInputError(
            f"{name} valid_to and closure availability must be paired"
        )
    base_available = parse_utc_timestamp(available_at, f"{name}.available_at")
    if valid_to_available_at is not None and parse_utc_timestamp(
        valid_to_available_at, f"{name}.valid_to_available_at"
    ) < base_available:
        raise ProductionInputError(
            f"{name} closure cannot be available before its base mapping"
        )


def _contains_visible_interval(
    *,
    valid_from: str,
    valid_to: str | None,
    valid_to_available_at: str | None,
    when: str,
    cutoff: str,
) -> bool:
    start = parse_date(valid_from, "valid_from")
    end = None
    if (
        valid_to is not None
        and valid_to_available_at is not None
        and parse_utc_timestamp(valid_to_available_at, "valid_to_available_at")
        < parse_utc_timestamp(cutoff, "decision_cutoff_at")
    ):
        end = parse_date(valid_to, "valid_to")
    value = parse_date(when, "effective date")
    return start <= value and (end is None or value < end)


@dataclasses.dataclass(frozen=True)
class EvidenceSourceBinding:
    kind: EvidenceSourceKind
    artifact_id: str
    artifact_sha256: str
    reviewed: bool
    point_in_time: bool

    def __post_init__(self) -> None:
        if type(self.kind) is not EvidenceSourceKind:
            raise ProductionInputError("evidence source kind must have exact type")
        _require_exact_strings(
            self,
            ("artifact_id", "artifact_sha256"),
            "evidence_source",
        )
        require_identifier(self.artifact_id, "artifact_id")
        require_sha256(self.artifact_sha256, "artifact_sha256")
        require_exact_bool(self.reviewed, "reviewed")
        require_exact_bool(self.point_in_time, "point_in_time")

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
            "reviewed": self.reviewed,
            "point_in_time": self.point_in_time,
        }


@dataclasses.dataclass(frozen=True)
class SecurityIdentityEvidence:
    provider_event_id: str
    source_current_restated_ticker: str
    historical_ticker: str
    issuer_id: str
    security_id: str
    share_class_id: str
    listing_id: str
    security_master_id: str
    security_master_sha256: str
    mapping_version_id: str
    mapping_evidence_sha256: str
    valid_from: str
    valid_to: str | None
    valid_to_available_at: str | None
    available_at: str
    candidate_count: int
    point_in_time: bool
    current_ticker_only: bool

    def __post_init__(self) -> None:
        _require_exact_strings(
            self,
            (
                "provider_event_id",
                "source_current_restated_ticker",
                "historical_ticker",
                "issuer_id",
                "security_id",
                "share_class_id",
                "listing_id",
                "security_master_id",
                "security_master_sha256",
                "mapping_version_id",
                "mapping_evidence_sha256",
                "valid_from",
                "available_at",
            ),
            "security",
        )
        _require_optional_exact_string(self, "valid_to", "security")
        _require_optional_exact_string(
            self, "valid_to_available_at", "security"
        )
        for name in (
            "provider_event_id",
            "issuer_id",
            "security_id",
            "share_class_id",
            "listing_id",
            "security_master_id",
            "mapping_version_id",
        ):
            require_identifier(getattr(self, name), name)
        require_ticker(self.source_current_restated_ticker, "source ticker")
        require_ticker(self.historical_ticker, "historical_ticker")
        require_sha256(self.security_master_sha256, "security_master_sha256")
        require_sha256(self.mapping_evidence_sha256, "mapping_evidence_sha256")
        _validate_interval(
            self.valid_from,
            self.valid_to,
            self.valid_to_available_at,
            self.available_at,
            "security identity",
        )
        require_int(self.candidate_count, "candidate_count", minimum=0)
        require_exact_bool(self.point_in_time, "point_in_time")
        require_exact_bool(self.current_ticker_only, "current_ticker_only")

    def to_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class FirmOntologyEvidence:
    provider_event_id: str
    provider_firm_id: str
    raw_firm_name: str
    raw_current_label: str
    raw_previous_label: str
    institution_id: str
    ontology_id: str
    ontology_sha256: str
    ontology_entry_sha256: str
    valid_from: str
    valid_to: str | None
    valid_to_available_at: str | None
    available_at: str
    current_score: Fraction
    previous_score: Fraction
    candidate_count: int
    ontology_reviewed: bool
    labels_reviewed: bool

    def __post_init__(self) -> None:
        _require_exact_strings(
            self,
            (
                "provider_event_id",
                "provider_firm_id",
                "raw_firm_name",
                "raw_current_label",
                "raw_previous_label",
                "institution_id",
                "ontology_id",
                "ontology_sha256",
                "ontology_entry_sha256",
                "valid_from",
                "available_at",
            ),
            "firm",
        )
        _require_optional_exact_string(self, "valid_to", "firm")
        _require_optional_exact_string(self, "valid_to_available_at", "firm")
        for name in (
            "provider_event_id",
            "provider_firm_id",
            "institution_id",
            "ontology_id",
        ):
            require_identifier(getattr(self, name), name)
        for name in ("raw_firm_name", "raw_current_label", "raw_previous_label"):
            require_text(getattr(self, name), name)
        require_sha256(self.ontology_sha256, "ontology_sha256")
        require_sha256(self.ontology_entry_sha256, "ontology_entry_sha256")
        _validate_interval(
            self.valid_from,
            self.valid_to,
            self.valid_to_available_at,
            self.available_at,
            "firm ontology",
        )
        for name in ("current_score", "previous_score"):
            value = getattr(self, name)
            if type(value) is not Fraction or not Fraction(-1) <= value <= Fraction(1):
                raise ProductionInputError(f"{name} must be an exact Fraction in [-1,1]")
        require_int(self.candidate_count, "candidate_count", minimum=0)
        require_exact_bool(self.ontology_reviewed, "ontology_reviewed")
        require_exact_bool(self.labels_reviewed, "labels_reviewed")

    def to_record(self) -> dict[str, Any]:
        return {
            "provider_event_id": self.provider_event_id,
            "provider_firm_id": self.provider_firm_id,
            "raw_firm_name": self.raw_firm_name,
            "raw_current_label": self.raw_current_label,
            "raw_previous_label": self.raw_previous_label,
            "institution_id": self.institution_id,
            "ontology_id": self.ontology_id,
            "ontology_sha256": self.ontology_sha256,
            "ontology_entry_sha256": self.ontology_entry_sha256,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "valid_to_available_at": self.valid_to_available_at,
            "available_at": self.available_at,
            "current_score": _fraction_record(self.current_score),
            "previous_score": _fraction_record(self.previous_score),
            "candidate_count": self.candidate_count,
            "ontology_reviewed": self.ontology_reviewed,
            "labels_reviewed": self.labels_reviewed,
        }


@dataclasses.dataclass(frozen=True)
class CommonEventIdentityEvidence:
    provider_event_id: str
    common_event_id: str
    source_id: str
    source_sha256: str
    evidence_sha256: str
    available_at: str
    candidate_count: int

    def __post_init__(self) -> None:
        _require_exact_strings(
            self,
            (
                "provider_event_id",
                "common_event_id",
                "source_id",
                "source_sha256",
                "evidence_sha256",
                "available_at",
            ),
            "common_event",
        )
        for name in ("provider_event_id", "common_event_id", "source_id"):
            require_identifier(getattr(self, name), name)
        require_sha256(self.source_sha256, "source_sha256")
        require_sha256(self.evidence_sha256, "evidence_sha256")
        parse_utc_timestamp(self.available_at, "common_event.available_at")
        require_int(self.candidate_count, "candidate_count", minimum=0)

    def to_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SectorClassificationEvidence:
    security_id: str
    sector_id: str
    source_id: str
    source_sha256: str
    evidence_sha256: str
    valid_from: str
    valid_to: str | None
    valid_to_available_at: str | None
    available_at: str
    candidate_count: int
    point_in_time: bool

    def __post_init__(self) -> None:
        _require_exact_strings(
            self,
            (
                "security_id",
                "sector_id",
                "source_id",
                "source_sha256",
                "evidence_sha256",
                "valid_from",
                "available_at",
            ),
            "sector",
        )
        _require_optional_exact_string(self, "valid_to", "sector")
        _require_optional_exact_string(self, "valid_to_available_at", "sector")
        for name in ("security_id", "sector_id", "source_id"):
            require_identifier(getattr(self, name), name)
        require_sha256(self.source_sha256, "source_sha256")
        require_sha256(self.evidence_sha256, "evidence_sha256")
        _validate_interval(
            self.valid_from,
            self.valid_to,
            self.valid_to_available_at,
            self.available_at,
            "sector",
        )
        require_int(self.candidate_count, "candidate_count", minimum=0)
        require_exact_bool(self.point_in_time, "point_in_time")

    def to_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class PreopenControlEvidence:
    security_id: str
    industry_id: str
    decision_session: str
    source_id: str
    source_sha256: str
    evidence_sha256: str
    available_at: str
    control_vector_sha256: str
    complete: bool
    point_in_time: bool
    contains_outcome_or_price: bool

    def __post_init__(self) -> None:
        _require_exact_strings(
            self,
            (
                "security_id",
                "industry_id",
                "decision_session",
                "source_id",
                "source_sha256",
                "evidence_sha256",
                "available_at",
                "control_vector_sha256",
            ),
            "control",
        )
        for name in ("security_id", "industry_id", "source_id"):
            require_identifier(getattr(self, name), name)
        parse_date(self.decision_session, "decision_session")
        for name in ("source_sha256", "evidence_sha256", "control_vector_sha256"):
            require_sha256(getattr(self, name), name)
        parse_utc_timestamp(self.available_at, "control.available_at")
        require_exact_bool(self.complete, "complete")
        require_exact_bool(self.point_in_time, "point_in_time")
        require_exact_bool(self.contains_outcome_or_price, "contains_outcome_or_price")

    def to_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class DataQualityEvidence:
    security_id: str
    measured_session: str
    source_id: str
    source_sha256: str
    evidence_sha256: str
    available_at: str
    measurement_method_id: str
    q_data: Decimal
    point_in_time: bool

    def __post_init__(self) -> None:
        _require_exact_strings(
            self,
            (
                "security_id",
                "measured_session",
                "source_id",
                "source_sha256",
                "evidence_sha256",
                "available_at",
                "measurement_method_id",
            ),
            "q_data",
        )
        for name in ("security_id", "source_id", "measurement_method_id"):
            require_identifier(getattr(self, name), name)
        parse_date(self.measured_session, "measured_session")
        for name in ("source_sha256", "evidence_sha256"):
            require_sha256(getattr(self, name), name)
        parse_utc_timestamp(self.available_at, "q_data.available_at")
        value = _exact_decimal(self.q_data, "q_data")
        if not Decimal("0") <= value <= Decimal("1"):
            raise ProductionInputError("q_data must be in [0,1]")
        object.__setattr__(self, "q_data", value)
        require_exact_bool(self.point_in_time, "point_in_time")

    def to_record(self) -> dict[str, Any]:
        return {
            "security_id": self.security_id,
            "measured_session": self.measured_session,
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "evidence_sha256": self.evidence_sha256,
            "available_at": self.available_at,
            "measurement_method_id": self.measurement_method_id,
            "q_data": _decimal_text(self.q_data),
            "point_in_time": self.point_in_time,
        }


@dataclasses.dataclass(frozen=True)
class ProductionRowEvidence:
    locator: CaptureRowLocator
    security: SecurityIdentityEvidence | None
    firm: FirmOntologyEvidence | None
    common_event: CommonEventIdentityEvidence | None
    sector: SectorClassificationEvidence | None
    control: PreopenControlEvidence | None
    q_data: DataQualityEvidence | None

    def __post_init__(self) -> None:
        if type(self.locator) is not CaptureRowLocator:
            raise ProductionInputError("row evidence locator must have exact type")
        typed = (
            (self.security, SecurityIdentityEvidence, "security"),
            (self.firm, FirmOntologyEvidence, "firm"),
            (self.common_event, CommonEventIdentityEvidence, "common_event"),
            (self.sector, SectorClassificationEvidence, "sector"),
            (self.control, PreopenControlEvidence, "control"),
            (self.q_data, DataQualityEvidence, "q_data"),
        )
        for value, expected, name in typed:
            if value is not None and type(value) is not expected:
                raise ProductionInputError(f"{name} evidence must have exact type or be null")

    def to_record(self) -> dict[str, Any]:
        return {
            "locator": self.locator.to_record(),
            "security": None if self.security is None else self.security.to_record(),
            "firm": None if self.firm is None else self.firm.to_record(),
            "common_event": (
                None if self.common_event is None else self.common_event.to_record()
            ),
            "sector": None if self.sector is None else self.sector.to_record(),
            "control": None if self.control is None else self.control.to_record(),
            "q_data": None if self.q_data is None else self.q_data.to_record(),
        }


def production_input_contract_record() -> dict[str, Any]:
    """Return the static, outcome-free C2 admission contract."""
    return {
        "schema": PRODUCTION_INPUT_CONTRACT_SCHEMA,
        "status": PRODUCTION_INPUT_STATUS,
        "parent": {
            "contract_id": INPUT_PAIR_CONTRACT_ID,
            "contract_sha256": INPUT_PAIR_CONTRACT_SHA256,
        },
        "input_views": [view.value for view in InputView],
        "signal_arms": [arm.value for arm in SignalArm],
        "source_roles": [role.value for role in MassiveSourceRole],
        "source_role_is_signal_arm": False,
        "accepted_risk": {
            "pristine_point_in_time": False,
            "non_pristine_disclosure": NON_PRISTINE_DISCLOSURE,
            "current_ticker_is_identity": False,
            "guidance_admitted": False,
            "pre_2013_admitted": False,
        },
        "required_evidence_sources": [kind.value for kind in _SOURCE_ORDER],
        "row_census": "one_terminal_disposition_per_c1_source_locator",
        "normalization": {
            "directional_actions": sorted(_DIRECTIONAL_ACTIONS),
            "known_non_directional_actions": sorted(
                _KNOWN_NON_DIRECTIONAL_ACTIONS
            ),
            "unsupported_documented_actions": sorted(
                _UNSUPPORTED_DOCUMENTED_ACTIONS
            ),
            "malformed_or_unknown_action_census": (
                "potential_directional_refusal_never_silently_complete"
            ),
            "rating_scores": "exact_fractions_in_closed_interval_minus_one_one",
            "rating_change": "current_score_minus_previous_score",
            "provider_version": "exact_c1_raw_row_sha256",
            "historical_identity": "unique_pit_permanent_security_and_listing",
        },
        "output_contains": "pre_outcome_event_level_normalized_rows_only",
        "cross_section_boundary": {
            "eligibility_evidence_scope": ELIGIBILITY_CROSS_SECTION_SCOPE,
            "later_decision_date_universe_sector_quality_controls_required": True,
            "later_decision_date_cross_sections_bound": False,
        },
        "comparison_report": {
            "schema": COMPARISON_REPORT_SCHEMA,
            "pre_return": True,
            "dimensions": [dimension.value for dimension in ComparisonDimension],
            "rates": [
                "current_admitted",
                "current_refused",
                "censored_admitted",
                "censored_refused",
                "mapping_disagreement",
                "signal_disagreement",
            ],
        },
        "external_bindings": {
            "production_registry_receipt": None,
            "production_truth_approval": None,
            "outcome_authority": None,
            "quantconnect_runtime": None,
        },
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


PRODUCTION_INPUT_CONTRACT_SHA256 = sha256_bytes(
    canonical_json_bytes(production_input_contract_record())
)
PRODUCTION_INPUT_CONTRACT_ID = (
    f"arv2-production-input-contract-{PRODUCTION_INPUT_CONTRACT_SHA256[:16]}"
)


def render_production_input_contract_bytes() -> bytes:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    return canonical_json_bytes(production_input_contract_record())


@dataclasses.dataclass(frozen=True, init=False)
class ProductionEvidenceAuthority:
    schema: str
    status: str
    contract_id: str
    contract_sha256: str
    authority_id: str
    authority_sha256: str
    pair: AcceptedRiskInputPair
    pair_id: str
    pair_sha256: str
    source_bindings: tuple[EvidenceSourceBinding, ...]
    row_evidence: tuple[ProductionRowEvidence, ...]
    pristine_point_in_time: bool
    current_ticker_identity_allowed: bool
    production_registry_receipt: None
    production_truth_approval: None
    outcome_authority: None
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


_EVIDENCE_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType[ProductionEvidenceAuthority], tuple[object, ...]]
] = {}
_EVIDENCE_AUTHORITIES_LOCK = threading.RLock()


def _source_map(
    sources: tuple[EvidenceSourceBinding, ...],
) -> dict[EvidenceSourceKind, EvidenceSourceBinding]:
    return {item.kind: item for item in sources}


def _authority_semantic_record(
    *,
    pair: AcceptedRiskInputPair,
    sources: tuple[EvidenceSourceBinding, ...],
    row_evidence: tuple[ProductionRowEvidence, ...],
) -> dict[str, Any]:
    return {
        "schema": PRODUCTION_EVIDENCE_SCHEMA,
        "status": PRODUCTION_INPUT_STATUS,
        "contract_id": PRODUCTION_INPUT_CONTRACT_ID,
        "contract_sha256": PRODUCTION_INPUT_CONTRACT_SHA256,
        "pair_id": pair.pair_id,
        "pair_sha256": pair.pair_sha256,
        "source_bindings": [item.to_record() for item in sources],
        "row_evidence": [item.to_record() for item in row_evidence],
        "pristine_point_in_time": False,
        "current_ticker_identity_allowed": False,
        "production_registry_receipt": None,
        "production_truth_approval": None,
        "outcome_authority": None,
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


def _authority_fingerprint(authority: ProductionEvidenceAuthority) -> tuple[object, ...]:
    return (
        id(authority.pair),
        canonical_json_bytes(
            _authority_semantic_record(
                pair=authority.pair,
                sources=authority.source_bindings,
                row_evidence=authority.row_evidence,
            )
        ),
        authority.authority_id,
        authority.authority_sha256,
    )


def _forget_evidence_authority(
    identity: int, reference: weakref.ReferenceType[ProductionEvidenceAuthority]
) -> None:
    with _EVIDENCE_AUTHORITIES_LOCK:
        current = _EVIDENCE_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _EVIDENCE_AUTHORITIES.pop(identity, None)


def _validate_authority_surface(authority: ProductionEvidenceAuthority) -> None:
    _require_exact_strings(
        authority,
        (
            "schema",
            "status",
            "contract_id",
            "contract_sha256",
            "authority_id",
            "authority_sha256",
            "pair_id",
            "pair_sha256",
        ),
        "evidence_authority",
    )
    false_flags = (
        authority.pristine_point_in_time,
        authority.current_ticker_identity_allowed,
        authority.provider_access,
        authority.credential_access,
        authority.filesystem_access,
        authority.quantconnect_access,
        authority.object_store_access,
        authority.price_access,
        authority.outcome_access,
        authority.deployment,
        authority.orders,
        authority.trading,
    )
    if any(type(flag) is not bool or flag is not False for flag in false_flags):
        raise ProductionInputError("offline evidence authority acquired a forbidden flag")
    if any(
        value is not None
        for value in (
            authority.production_registry_receipt,
            authority.production_truth_approval,
            authority.outcome_authority,
        )
    ):
        raise ProductionInputError("offline evidence authority acquired an external binding")


def _validate_sources(sources: tuple[EvidenceSourceBinding, ...]) -> None:
    if type(sources) is not tuple or any(
        type(item) is not EvidenceSourceBinding for item in sources
    ):
        raise ProductionInputError("source bindings must be an exact typed tuple")
    if tuple(item.kind for item in sources) != _SOURCE_ORDER:
        raise ProductionInputError(
            "source bindings must contain every evidence kind once in canonical order"
        )
    for item in sources:
        item.__post_init__()


def _remember_consistent_fact(
    seen: dict[tuple[object, ...], tuple[object, ...]],
    *,
    key: tuple[object, ...],
    fact: tuple[object, ...],
    label: str,
) -> None:
    prior = seen.get(key)
    if prior is not None and prior != fact:
        raise ProductionInputError(f"conflicting cross-row {label} evidence")
    seen[key] = fact


def _reject_contradictory_interval_lineage(
    records: list[tuple[str, str | None, tuple[str, ...]]],
    *,
    label: str,
) -> None:
    """Reject different identities whose authoritative half-open intervals overlap."""

    ordered = sorted(
        {
            (
                parse_date(valid_from, f"{label}.valid_from"),
                None
                if valid_to is None
                else parse_date(valid_to, f"{label}.valid_to"),
                identity,
            )
            for valid_from, valid_to, identity in records
        },
        key=lambda item: (item[0], item[1] is None, item[1], item[2]),
    )
    active_counts: dict[tuple[str, ...], int] = {}
    finite_ends: list[tuple[object, int, tuple[str, ...]]] = []
    active_total = 0
    serial = 0
    for start, end, identity in ordered:
        while finite_ends and finite_ends[0][0] <= start:
            _expired, _serial, expired_identity = heapq.heappop(finite_ends)
            remaining = active_counts[expired_identity] - 1
            active_total -= 1
            if remaining:
                active_counts[expired_identity] = remaining
            else:
                active_counts.pop(expired_identity)
        if active_total != active_counts.get(identity, 0):
            raise ProductionInputError(
                f"contradictory overlapping {label} evidence"
            )
        active_counts[identity] = active_counts.get(identity, 0) + 1
        active_total += 1
        if end is not None:
            heapq.heappush(finite_ends, (end, serial, identity))
            serial += 1


def _validate_row_evidence_topology(
    pair: AcceptedRiskInputPair,
    rows: tuple[ProductionRowEvidence, ...],
) -> None:
    if type(rows) is not tuple or any(type(item) is not ProductionRowEvidence for item in rows):
        raise ProductionInputError("row evidence must be an exact typed tuple")
    for item in rows:
        item.__post_init__()
        for component in (
            item.security,
            item.firm,
            item.common_event,
            item.sector,
            item.control,
            item.q_data,
        ):
            if component is not None:
                component.__post_init__()
    if tuple(item.locator.sort_key for item in rows) != tuple(
        sorted(item.locator.sort_key for item in rows)
    ):
        raise ProductionInputError("row evidence must be canonical source-sorted")
    locators = tuple(item.locator for item in rows)
    if len(locators) != len(set(locators)):
        raise ProductionInputError("duplicate row-evidence disposition locator")
    candidate_locators = {
        row.locator
        for row in pair.rows
        if row.locator.source_role is MassiveSourceRole.ANALYST_RATINGS
        and row.current_view.included
    }
    if not set(locators).issubset(candidate_locators):
        raise ProductionInputError(
            "row evidence targets an excluded or non-rating C1 source locator"
        )
    source_by_locator = {row.locator: row for row in pair.rows}
    facts: dict[tuple[object, ...], tuple[object, ...]] = {}
    firm_lineage: dict[
        str, list[tuple[str, str | None, tuple[str, ...]]]
    ] = {}
    security_lineage: dict[
        tuple[str, str], list[tuple[str, str | None, tuple[str, ...]]]
    ] = {}
    for item in rows:
        source = source_by_locator[item.locator]
        session = source.current_view.eligible_session
        if source.event_date is None or session is None:
            raise ProductionInputError(
                "candidate row evidence has no event/eligibility session"
            )
        security = item.security
        if security is not None:
            security_fact = (
                security.historical_ticker,
                security.issuer_id,
                security.share_class_id,
                security.listing_id,
                security.security_master_id,
                security.security_master_sha256,
                security.mapping_version_id,
                security.mapping_evidence_sha256,
                security.valid_from,
                security.valid_to,
                security.valid_to_available_at,
                security.available_at,
                security.candidate_count,
                security.point_in_time,
                security.current_ticker_only,
            )
            _remember_consistent_fact(
                facts,
                key=("security", security.security_id, session),
                fact=security_fact,
                label="security/session",
            )
            _remember_consistent_fact(
                facts,
                key=(
                    "source_ticker",
                    security.source_current_restated_ticker,
                    source.event_date,
                ),
                fact=(security.security_id, *security_fact),
                label="source-ticker/date identity",
            )
            permanent_identity = (
                security.security_id,
                security.issuer_id,
                security.share_class_id,
                security.listing_id,
                security.security_master_id,
                security.security_master_sha256,
            )
            for namespace, identifier, identity in (
                (
                    "security_id",
                    security.security_id,
                    (
                        security.historical_ticker,
                        security.issuer_id,
                        security.share_class_id,
                        security.listing_id,
                        security.security_master_id,
                        security.security_master_sha256,
                    ),
                ),
                ("historical_ticker", security.historical_ticker, permanent_identity),
                (
                    "source_current_restated_ticker",
                    security.source_current_restated_ticker,
                    permanent_identity,
                ),
                (
                    "listing_id",
                    security.listing_id,
                    (
                        security.security_id,
                        security.issuer_id,
                        security.share_class_id,
                        security.security_master_id,
                        security.security_master_sha256,
                    ),
                ),
            ):
                security_lineage.setdefault((namespace, identifier), []).append(
                    (security.valid_from, security.valid_to, identity)
                )
        firm = item.firm
        if firm is not None:
            _remember_consistent_fact(
                facts,
                key=("firm", firm.provider_firm_id, source.event_date),
                fact=(
                    firm.institution_id,
                    firm.ontology_id,
                    firm.ontology_sha256,
                    firm.valid_from,
                    firm.valid_to,
                    firm.valid_to_available_at,
                    firm.available_at,
                    firm.candidate_count,
                    firm.ontology_reviewed,
                ),
                label="firm/date ontology",
            )
            _remember_consistent_fact(
                facts,
                key=(
                    "rating_scale",
                    firm.provider_firm_id,
                    firm.raw_current_label.casefold(),
                    firm.raw_previous_label.casefold(),
                    source.event_date,
                ),
                fact=(
                    firm.institution_id,
                    firm.current_score,
                    firm.previous_score,
                    firm.ontology_entry_sha256,
                    firm.labels_reviewed,
                ),
                label="firm/rating-scale/date",
            )
            firm_lineage.setdefault(firm.provider_firm_id, []).append(
                (
                    firm.valid_from,
                    firm.valid_to,
                    (
                        firm.institution_id,
                        firm.ontology_id,
                        firm.ontology_sha256,
                    ),
                )
            )
        common = item.common_event
        if common is not None:
            _remember_consistent_fact(
                facts,
                key=("common_event", common.common_event_id),
                fact=(
                    common.source_id,
                    common.source_sha256,
                    common.evidence_sha256,
                    common.available_at,
                    common.candidate_count,
                ),
                label="common-event identity",
            )
        sector = item.sector
        if sector is not None:
            _remember_consistent_fact(
                facts,
                key=("sector", sector.security_id, session),
                fact=(
                    sector.sector_id,
                    sector.source_id,
                    sector.source_sha256,
                    sector.evidence_sha256,
                    sector.valid_from,
                    sector.valid_to,
                    sector.valid_to_available_at,
                    sector.available_at,
                    sector.candidate_count,
                    sector.point_in_time,
                ),
                label="sector/security/session",
            )
        control = item.control
        if control is not None:
            _remember_consistent_fact(
                facts,
                key=("control", control.security_id, control.decision_session),
                fact=(
                    control.industry_id,
                    control.source_id,
                    control.source_sha256,
                    control.evidence_sha256,
                    control.available_at,
                    control.control_vector_sha256,
                    control.complete,
                    control.point_in_time,
                    control.contains_outcome_or_price,
                ),
                label="control/security/session",
            )
        quality = item.q_data
        if quality is not None:
            _remember_consistent_fact(
                facts,
                key=("q_data", quality.security_id, quality.measured_session),
                fact=(
                    quality.source_id,
                    quality.source_sha256,
                    quality.evidence_sha256,
                    quality.available_at,
                    quality.measurement_method_id,
                    quality.q_data,
                    quality.point_in_time,
                ),
                label="q_data/security/session",
            )
    for records in firm_lineage.values():
        _reject_contradictory_interval_lineage(
            records,
            label="provider-firm identity lineage",
        )
    for (namespace, _identifier), records in security_lineage.items():
        _reject_contradictory_interval_lineage(
            records,
            label=f"security {namespace} lineage",
        )


def _validate_component_source_bindings(
    sources: tuple[EvidenceSourceBinding, ...],
    rows: tuple[ProductionRowEvidence, ...],
) -> None:
    by_kind = _source_map(sources)
    for row in rows:
        security = row.security
        if security is not None:
            source = by_kind[EvidenceSourceKind.SECURITY_MASTER]
            if (
                security.security_master_id != source.artifact_id
                or security.security_master_sha256 != source.artifact_sha256
            ):
                raise ProductionInputError("security evidence source binding mismatch")
        firm = row.firm
        if firm is not None:
            source = by_kind[EvidenceSourceKind.FIRM_ONTOLOGY]
            if firm.ontology_id != source.artifact_id or firm.ontology_sha256 != source.artifact_sha256:
                raise ProductionInputError("firm evidence source binding mismatch")
        component_sources = (
            (row.common_event, EvidenceSourceKind.COMMON_EVENT),
            (row.sector, EvidenceSourceKind.SECTOR_CLASSIFICATION),
            (row.control, EvidenceSourceKind.PREOPEN_CONTROL),
            (row.q_data, EvidenceSourceKind.DATA_QUALITY),
        )
        for component, kind in component_sources:
            if component is None:
                continue
            source = by_kind[kind]
            if component.source_id != source.artifact_id or component.source_sha256 != source.artifact_sha256:
                raise ProductionInputError(f"{kind.value} evidence source binding mismatch")


def build_production_evidence_authority(
    pair: AcceptedRiskInputPair,
    *,
    source_bindings: tuple[EvidenceSourceBinding, ...],
    row_evidence: tuple[ProductionRowEvidence, ...],
) -> ProductionEvidenceAuthority:
    """Authenticate caller-supplied evidence without reading any source."""
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    require_accepted_risk_input_pair(pair)
    _validate_sources(source_bindings)
    _validate_row_evidence_topology(pair, row_evidence)
    _validate_component_source_bindings(source_bindings, row_evidence)
    semantic = _authority_semantic_record(
        pair=pair,
        sources=source_bindings,
        row_evidence=row_evidence,
    )
    digest = sha256_bytes(canonical_json_bytes(semantic))
    authority = object.__new__(ProductionEvidenceAuthority)
    values: dict[str, object] = {
        "schema": PRODUCTION_EVIDENCE_SCHEMA,
        "status": PRODUCTION_INPUT_STATUS,
        "contract_id": PRODUCTION_INPUT_CONTRACT_ID,
        "contract_sha256": PRODUCTION_INPUT_CONTRACT_SHA256,
        "authority_id": f"arv2-production-evidence-{digest[:24]}",
        "authority_sha256": digest,
        "pair": pair,
        "pair_id": pair.pair_id,
        "pair_sha256": pair.pair_sha256,
        "source_bindings": source_bindings,
        "row_evidence": row_evidence,
        "pristine_point_in_time": False,
        "current_ticker_identity_allowed": False,
        "production_registry_receipt": None,
        "production_truth_approval": None,
        "outcome_authority": None,
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
    for name, value in values.items():
        object.__setattr__(authority, name, value)
    identity = id(authority)
    reference = weakref.ref(
        authority,
        lambda ref, key=identity: _forget_evidence_authority(key, ref),
    )
    with _EVIDENCE_AUTHORITIES_LOCK:
        _EVIDENCE_AUTHORITIES[identity] = (reference, _authority_fingerprint(authority))
    return authority


def require_production_evidence_authority(
    authority: ProductionEvidenceAuthority,
) -> ProductionEvidenceAuthority:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    if type(authority) is not ProductionEvidenceAuthority:
        raise ProductionInputError("evidence authority requires the exact built type")
    with _EVIDENCE_AUTHORITIES_LOCK:
        registered = _EVIDENCE_AUTHORITIES.get(id(authority))
    if registered is None or registered[0]() is not authority:
        raise ProductionInputError("evidence authority is not builder-authenticated")
    if type(authority.pair) is not AcceptedRiskInputPair:
        raise ProductionInputError("evidence authority pair has wrong type")
    _validate_authority_surface(authority)
    require_accepted_risk_input_pair(authority.pair)
    _validate_sources(authority.source_bindings)
    _validate_row_evidence_topology(authority.pair, authority.row_evidence)
    _validate_component_source_bindings(authority.source_bindings, authority.row_evidence)
    if _authority_fingerprint(authority) != registered[1]:
        raise ProductionInputError("evidence authority changed after authentication")
    semantic = _authority_semantic_record(
        pair=authority.pair,
        sources=authority.source_bindings,
        row_evidence=authority.row_evidence,
    )
    digest = sha256_bytes(canonical_json_bytes(semantic))
    if (
        authority.schema != PRODUCTION_EVIDENCE_SCHEMA
        or authority.status != PRODUCTION_INPUT_STATUS
        or authority.contract_id != PRODUCTION_INPUT_CONTRACT_ID
        or authority.contract_sha256 != PRODUCTION_INPUT_CONTRACT_SHA256
        or authority.authority_sha256 != digest
        or authority.authority_id != f"arv2-production-evidence-{digest[:24]}"
        or authority.pair_id != authority.pair.pair_id
        or authority.pair_sha256 != authority.pair.pair_sha256
    ):
        raise ProductionInputError("evidence authority content identity is not exact")
    return authority


_RATING_PROVIDER_FIELDS = frozenset(
    {
        "adjusted_price_target",
        "analyst",
        "benzinga_analyst_id",
        "benzinga_calendar_url",
        "benzinga_firm_id",
        "benzinga_id",
        "benzinga_news_url",
        "company_name",
        "currency",
        "date",
        "firm",
        "importance",
        "last_updated",
        "notes",
        "previous_adjusted_price_target",
        "previous_price_target",
        "previous_rating",
        "price_percent_change",
        "price_target",
        "price_target_action",
        "rating",
        "rating_action",
        "ticker",
        "time",
    }
)
_RATING_NUMERIC_FIELDS = frozenset(
    {
        "adjusted_price_target",
        "previous_adjusted_price_target",
        "previous_price_target",
        "price_percent_change",
        "price_target",
    }
)
_RATING_TEXT_FIELDS = (
    _RATING_PROVIDER_FIELDS
    - _RATING_NUMERIC_FIELDS
    - {"importance", "last_updated"}
)
_RAW_EVENT_TIME_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d")

_PINNED_STATIC_SCALARS = (
    PRODUCTION_INPUT_CONTRACT_SCHEMA,
    PRODUCTION_EVIDENCE_SCHEMA,
    PRODUCTION_INPUT_BATCH_SCHEMA,
    PRODUCTION_INPUT_STATUS,
    NON_PRISTINE_DISCLOSURE,
    PROVIDER_VERSION_PREFIX,
    COMPARISON_REPORT_SCHEMA,
    ELIGIBILITY_CROSS_SECTION_SCOPE,
    PRODUCTION_INPUT_CONTRACT_ID,
    PRODUCTION_INPUT_CONTRACT_SHA256,
    INPUT_PAIR_CONTRACT_ID,
    INPUT_PAIR_CONTRACT_SHA256,
    CURRENT_VIEW_LABEL,
    CENSORED_VIEW_LABEL,
)
_PINNED_ENUMS = (
    SignalArm,
    EvidenceSourceKind,
    AdmissionDisposition,
    InputView,
    MassiveSourceRole,
    RowDisposition,
    ComparisonDimension,
)
_PINNED_ENUM_INVENTORIES = tuple(tuple(enum_type) for enum_type in _PINNED_ENUMS)
_PINNED_ARM_TO_VIEW = _ARM_TO_VIEW
_PINNED_ARM_TO_VIEW_ITEMS = tuple(_ARM_TO_VIEW.items())
_PINNED_ARM_TO_LABEL = _ARM_TO_LABEL
_PINNED_ARM_TO_LABEL_ITEMS = tuple(_ARM_TO_LABEL.items())
_PINNED_SOURCE_ORDER = _SOURCE_ORDER
_PINNED_DIRECTIONAL_ACTIONS = _DIRECTIONAL_ACTIONS
_PINNED_KNOWN_NON_DIRECTIONAL_ACTIONS = _KNOWN_NON_DIRECTIONAL_ACTIONS
_PINNED_UNSUPPORTED_DOCUMENTED_ACTIONS = _UNSUPPORTED_DOCUMENTED_ACTIONS
_PINNED_KNOWN_RATING_ACTIONS = _KNOWN_RATING_ACTIONS
_PINNED_TARGET_ONLY_ACTION = _TARGET_ONLY_ACTION
_PINNED_RATING_PROVIDER_FIELDS = _RATING_PROVIDER_FIELDS
_PINNED_RATING_NUMERIC_FIELDS = _RATING_NUMERIC_FIELDS
_PINNED_RATING_TEXT_FIELDS = _RATING_TEXT_FIELDS
_PINNED_RAW_EVENT_TIME_RE = _RAW_EVENT_TIME_RE
_PINNED_PROVIDER_TIMESTAMP_RE = _PROVIDER_TIMESTAMP_RE
_PINNED_MAPPING_PROXY_TYPE = MappingProxyType
_PINNED_CONTRACT_RECORD = production_input_contract_record
_PINNED_CONTRACT_BYTES = canonical_json_bytes(production_input_contract_record())
_PINNED_IMPORTED_CALLABLES = (
    canonical_json_bytes,
    decode_utf8,
    parse_date,
    parse_utc_timestamp,
    require_accepted_risk_input_pair,
    require_exact_bool,
    require_identifier,
    require_int,
    require_sha256,
    require_text,
    sha256_bytes,
    strict_json_loads,
)


def _require_static_contract() -> None:
    scalars = (
        PRODUCTION_INPUT_CONTRACT_SCHEMA,
        PRODUCTION_EVIDENCE_SCHEMA,
        PRODUCTION_INPUT_BATCH_SCHEMA,
        PRODUCTION_INPUT_STATUS,
        NON_PRISTINE_DISCLOSURE,
        PROVIDER_VERSION_PREFIX,
        COMPARISON_REPORT_SCHEMA,
        ELIGIBILITY_CROSS_SECTION_SCOPE,
        PRODUCTION_INPUT_CONTRACT_ID,
        PRODUCTION_INPUT_CONTRACT_SHA256,
        INPUT_PAIR_CONTRACT_ID,
        INPUT_PAIR_CONTRACT_SHA256,
        CURRENT_VIEW_LABEL,
        CENSORED_VIEW_LABEL,
    )
    imported_callables = (
        canonical_json_bytes,
        decode_utf8,
        parse_date,
        parse_utc_timestamp,
        require_accepted_risk_input_pair,
        require_exact_bool,
        require_identifier,
        require_int,
        require_sha256,
        require_text,
        sha256_bytes,
        strict_json_loads,
    )
    if (
        _require_static_contract is not _PINNED_REQUIRE_STATIC_CONTRACT
        or any(
            type(current) is not type(expected) or current != expected
            for current, expected in zip(
                scalars,
                _PINNED_STATIC_SCALARS,
                strict=True,
            )
        )
        or tuple(enum_type for enum_type in _PINNED_ENUMS)
        != (
            SignalArm,
            EvidenceSourceKind,
            AdmissionDisposition,
            InputView,
            MassiveSourceRole,
            RowDisposition,
            ComparisonDimension,
        )
        or any(
            tuple(enum_type) != inventory
            for enum_type, inventory in zip(
                _PINNED_ENUMS,
                _PINNED_ENUM_INVENTORIES,
                strict=True,
            )
        )
        or MappingProxyType is not _PINNED_MAPPING_PROXY_TYPE
        or type(_ARM_TO_VIEW) is not _PINNED_MAPPING_PROXY_TYPE
        or _ARM_TO_VIEW is not _PINNED_ARM_TO_VIEW
        or tuple(_ARM_TO_VIEW.items()) != _PINNED_ARM_TO_VIEW_ITEMS
        or type(_ARM_TO_LABEL) is not _PINNED_MAPPING_PROXY_TYPE
        or _ARM_TO_LABEL is not _PINNED_ARM_TO_LABEL
        or tuple(_ARM_TO_LABEL.items()) != _PINNED_ARM_TO_LABEL_ITEMS
        or _SOURCE_ORDER is not _PINNED_SOURCE_ORDER
        or _DIRECTIONAL_ACTIONS is not _PINNED_DIRECTIONAL_ACTIONS
        or _KNOWN_NON_DIRECTIONAL_ACTIONS
        is not _PINNED_KNOWN_NON_DIRECTIONAL_ACTIONS
        or _UNSUPPORTED_DOCUMENTED_ACTIONS
        is not _PINNED_UNSUPPORTED_DOCUMENTED_ACTIONS
        or _KNOWN_RATING_ACTIONS is not _PINNED_KNOWN_RATING_ACTIONS
        or _TARGET_ONLY_ACTION != _PINNED_TARGET_ONLY_ACTION
        or _RATING_PROVIDER_FIELDS is not _PINNED_RATING_PROVIDER_FIELDS
        or _RATING_NUMERIC_FIELDS is not _PINNED_RATING_NUMERIC_FIELDS
        or _RATING_TEXT_FIELDS is not _PINNED_RATING_TEXT_FIELDS
        or _RAW_EVENT_TIME_RE is not _PINNED_RAW_EVENT_TIME_RE
        or _PROVIDER_TIMESTAMP_RE is not _PINNED_PROVIDER_TIMESTAMP_RE
        or production_input_contract_record is not _PINNED_CONTRACT_RECORD
        or canonical_json_bytes(_PINNED_CONTRACT_RECORD())
        != _PINNED_CONTRACT_BYTES
        or len(imported_callables) != len(_PINNED_IMPORTED_CALLABLES)
        or any(
            current is not expected
            for current, expected in zip(
                imported_callables,
                _PINNED_IMPORTED_CALLABLES,
                strict=True,
            )
        )
        or _current_local_callables is not _PINNED_CURRENT_LOCAL_CALLABLES
        or len(_PINNED_CURRENT_LOCAL_CALLABLES()) != len(_PINNED_LOCAL_CALLABLES)
        or any(
            current is not expected
            for current, expected in zip(
                _PINNED_CURRENT_LOCAL_CALLABLES(),
                _PINNED_LOCAL_CALLABLES,
                strict=True,
            )
        )
        or _current_record_types is not _PINNED_CURRENT_RECORD_TYPES
        or len(_PINNED_CURRENT_RECORD_TYPES()) != len(_PINNED_RECORD_TYPES)
        or any(
            current is not expected
            for current, expected in zip(
                _PINNED_CURRENT_RECORD_TYPES(),
                _PINNED_RECORD_TYPES,
                strict=True,
            )
        )
    ):
        raise ProductionInputError("production-input static contract changed")


_PINNED_REQUIRE_STATIC_CONTRACT = _require_static_contract


@dataclasses.dataclass(frozen=True)
class _ParsedRatingRow:
    provider_event_id: str
    event_date: str
    current_restated_ticker: str
    provider_firm_id: str
    raw_firm_name: str
    raw_action: str
    current_label: str | None
    previous_label: str | None


class _RatingRowRefusal(Exception):
    def __init__(self, disposition: AdmissionDisposition):
        super().__init__(disposition.value)
        self.disposition = disposition


def _required_identifier_value(record: dict[str, Any], key: str) -> str:
    try:
        return require_identifier(record.get(key), key)
    except CanonicalEvidenceError as exc:
        raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW) from exc


def _required_text_value(record: dict[str, Any], key: str) -> str:
    try:
        return require_text(record.get(key), key)
    except CanonicalEvidenceError as exc:
        raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW) from exc


def _optional_text_value(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    try:
        return require_text(value, key)
    except CanonicalEvidenceError as exc:
        raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW) from exc


def _rating_action_is_missing(value: object) -> bool:
    """Treat absent and the provider's observed exact-empty value identically."""

    return value is None or (type(value) is str and value == "")


def _validate_optional_rating_values(record: dict[str, Any]) -> None:
    try:
        for key in _RATING_TEXT_FIELDS:
            value = record.get(key)
            if (
                value is not None
                and not (
                    key == "rating_action"
                    and _rating_action_is_missing(value)
                )
            ):
                require_text(
                    value,
                    key,
                    maximum_length=8192 if key == "notes" else 2048,
                )
        for key in _RATING_NUMERIC_FIELDS:
            value = record.get(key)
            if value is None:
                continue
            if type(value) not in (int, Decimal) or not Decimal(value).is_finite():
                raise ProductionInputError(f"{key} is not an exact finite number")
        importance = record.get("importance")
        if importance is not None:
            require_int(importance, "importance", minimum=0, maximum=5)
        raw_time = record.get("time")
        if raw_time is not None and (
            type(raw_time) is not str
            or _RAW_EVENT_TIME_RE.fullmatch(raw_time) is None
        ):
            raise ProductionInputError("time is not exact HH:MM:SS")
        analyst_id = record.get("benzinga_analyst_id")
        if analyst_id is not None:
            require_identifier(analyst_id, "benzinga_analyst_id")
        last_updated = record.get("last_updated")
        if last_updated is not None:
            _normalize_provider_timestamp(last_updated)
    except CanonicalEvidenceError as exc:
        raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW) from exc


def _normalize_provider_timestamp(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or _PROVIDER_TIMESTAMP_RE.fullmatch(value) is None
    ):
        raise ProductionInputError(
            "last_updated must be an exact explicit-offset RFC3339 string"
        )
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ProductionInputError("last_updated is not a real timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProductionInputError("last_updated must contain an explicit offset")
    return parsed.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _potential_directional_action(source: AcceptedRiskSourceRow) -> bool:
    """Conservatively census rows whose direction cannot be ruled out."""
    try:
        value = strict_json_loads(
            decode_utf8(source.raw_row_bytes, "potential directional rating row"),
            "potential directional rating row",
        )
    except CanonicalEvidenceError:
        return True
    if type(value) is not dict:
        return True
    raw_action = value.get("rating_action")
    if type(raw_action) is str and raw_action in _KNOWN_NON_DIRECTIONAL_ACTIONS:
        return False
    action_missing = _rating_action_is_missing(raw_action)
    price_target_action = value.get("price_target_action")
    if (
        action_missing
        and type(price_target_action) is str
        and bool(price_target_action.strip())
    ):
        return False
    return True


def _parse_rating_row(source: AcceptedRiskSourceRow) -> _ParsedRatingRow:
    try:
        text = decode_utf8(source.raw_row_bytes, "accepted-risk rating row")
        value = strict_json_loads(text, "accepted-risk rating row")
    except CanonicalEvidenceError as exc:
        raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW) from exc
    if type(value) is not dict or not set(value).issubset(_RATING_PROVIDER_FIELDS):
        raise _RatingRowRefusal(AdmissionDisposition.UNSUPPORTED_RATING_ROW_SCHEMA)
    _validate_optional_rating_values(value)
    event_id = _required_identifier_value(value, "benzinga_id")
    try:
        event_date = parse_date(value.get("date"), "date").isoformat()
        ticker = require_ticker(value.get("ticker"), "ticker")
    except CanonicalEvidenceError as exc:
        raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW) from exc
    firm_id = _required_identifier_value(value, "benzinga_firm_id")
    firm_name = _required_text_value(value, "firm")
    raw_action = value.get("rating_action")
    action_missing = _rating_action_is_missing(raw_action)
    if action_missing:
        price_target_action = _optional_text_value(value, "price_target_action")
        if price_target_action is None:
            raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW)
        action = _TARGET_ONLY_ACTION
    else:
        action = _required_text_value(value, "rating_action")
    current = _optional_text_value(value, "rating")
    previous = _optional_text_value(value, "previous_rating")
    if (
        event_id != source.provider_event_id
        or event_date != source.event_date
        or ticker != source.current_restated_security_label
        or firm_id != source.firm_label
    ):
        raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW)
    raw_last_updated = value.get("last_updated")
    if raw_last_updated is not None:
        try:
            normalized_last_updated = _normalize_provider_timestamp(raw_last_updated)
        except ProductionInputError as exc:
            raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW) from exc
        if normalized_last_updated != source.normalized_last_updated_at:
            raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW)
    if action in _DIRECTIONAL_ACTIONS and (current is None or previous is None):
        raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW)
    if (
        action in _DIRECTIONAL_ACTIONS
        and current is not None
        and previous is not None
        and current.casefold() == previous.casefold()
    ):
        raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW)
    if (
        source.normalized_last_updated_at is not None
        and parse_utc_timestamp(
            source.normalized_last_updated_at,
            "normalized_last_updated_at",
        ).date()
        < parse_date(event_date, "event_date")
    ):
        raise _RatingRowRefusal(AdmissionDisposition.INVALID_RATING_ROW)
    return _ParsedRatingRow(
        provider_event_id=event_id,
        event_date=event_date,
        current_restated_ticker=ticker,
        provider_firm_id=firm_id,
        raw_firm_name=firm_name,
        raw_action=action,
        current_label=current,
        previous_label=previous,
    )


@dataclasses.dataclass(frozen=True)
class NormalizedPreOutcomeRow:
    row_id: str
    row_sha256: str
    source_locator: CaptureRowLocator
    source_role: MassiveSourceRole
    signal_arm: SignalArm
    source_view_label: str
    provider_event_id: str
    provider_version_id: str
    event_date: str
    publication_at_utc: str | None
    eligible_session: str
    decision_cutoff_at: str
    current_restated_ticker: str
    historical_ticker: str
    issuer_id: str
    security_id: str
    share_class_id: str
    listing_id: str
    institution_id: str
    common_event_id: str
    sector_id: str
    industry_id: str
    raw_action: str
    previous_score: Fraction
    current_score: Fraction
    rating_change: Fraction
    q_data: Decimal
    security_master_sha256: str
    identity_mapping_evidence_sha256: str
    ontology_sha256: str
    ontology_entry_sha256: str
    common_event_evidence_sha256: str
    sector_evidence_sha256: str
    control_evidence_sha256: str
    control_vector_sha256: str
    q_data_evidence_sha256: str
    cross_section_evidence_scope: str
    later_decision_date_cross_sections_bound: bool
    pristine_point_in_time: bool

    def __post_init__(self) -> None:
        _require_exact_strings(
            self,
            (
                "row_id",
                "row_sha256",
                "source_view_label",
                "provider_event_id",
                "provider_version_id",
                "event_date",
                "eligible_session",
                "decision_cutoff_at",
                "current_restated_ticker",
                "historical_ticker",
                "issuer_id",
                "security_id",
                "share_class_id",
                "listing_id",
                "institution_id",
                "common_event_id",
                "sector_id",
                "industry_id",
                "raw_action",
                "security_master_sha256",
                "identity_mapping_evidence_sha256",
                "ontology_sha256",
                "ontology_entry_sha256",
                "common_event_evidence_sha256",
                "sector_evidence_sha256",
                "control_evidence_sha256",
                "control_vector_sha256",
                "q_data_evidence_sha256",
                "cross_section_evidence_scope",
            ),
            "normalized_row",
        )
        require_identifier(self.row_id, "row_id")
        require_sha256(self.row_sha256, "row_sha256")
        if type(self.source_locator) is not CaptureRowLocator:
            raise ProductionInputError("normalized row locator has wrong type")
        if (
            self.source_role is not MassiveSourceRole.ANALYST_RATINGS
            or self.source_locator.source_role is not self.source_role
        ):
            raise ProductionInputError("only analyst ratings can become signal rows")
        if type(self.signal_arm) is not SignalArm:
            raise ProductionInputError("signal_arm has wrong type")
        if self.source_view_label != _ARM_TO_LABEL[self.signal_arm]:
            raise ProductionInputError("source view label does not match signal arm")
        for name in (
            "provider_event_id",
            "provider_version_id",
            "issuer_id",
            "security_id",
            "share_class_id",
            "listing_id",
            "institution_id",
            "common_event_id",
            "sector_id",
            "industry_id",
        ):
            require_identifier(getattr(self, name), name)
        if self.provider_version_id != (
            f"{PROVIDER_VERSION_PREFIX}{self.source_locator.raw_row_sha256}"
        ):
            raise ProductionInputError("provider version is not bound to exact C1 bytes")
        parse_date(self.event_date, "event_date")
        if self.publication_at_utc is not None:
            if type(self.publication_at_utc) is not str:
                raise ProductionInputError(
                    "publication_at_utc must be an exact string or null"
                )
            publication = parse_utc_timestamp(
                self.publication_at_utc, "publication_at_utc"
            )
            if publication.date().isoformat() != self.event_date:
                raise ProductionInputError(
                    "publication_at_utc date disagrees with provider event date"
                )
        parse_date(self.eligible_session, "eligible_session")
        parse_utc_timestamp(self.decision_cutoff_at, "decision_cutoff_at")
        require_ticker(self.current_restated_ticker, "current_restated_ticker")
        require_ticker(self.historical_ticker, "historical_ticker")
        if self.raw_action not in _DIRECTIONAL_ACTIONS:
            raise ProductionInputError("normalized row action is not directional")
        for name in ("previous_score", "current_score", "rating_change"):
            if type(getattr(self, name)) is not Fraction:
                raise ProductionInputError(f"{name} must be an exact Fraction")
        if self.rating_change != self.current_score - self.previous_score or self.rating_change == 0:
            raise ProductionInputError("rating change is not an exact nonzero delta")
        if (
            self.raw_action == "upgrades" and self.rating_change <= 0
        ) or (
            self.raw_action == "downgrades" and self.rating_change >= 0
        ):
            raise ProductionInputError("rating direction contradicts the provider action")
        value = _exact_decimal(self.q_data, "q_data")
        if not Decimal("0") <= value <= Decimal("1"):
            raise ProductionInputError("q_data must be in [0,1]")
        object.__setattr__(self, "q_data", value)
        for name in (
            "security_master_sha256",
            "identity_mapping_evidence_sha256",
            "ontology_sha256",
            "ontology_entry_sha256",
            "common_event_evidence_sha256",
            "sector_evidence_sha256",
            "control_evidence_sha256",
            "control_vector_sha256",
            "q_data_evidence_sha256",
        ):
            require_sha256(getattr(self, name), name)
        require_exact_bool(self.pristine_point_in_time, "pristine_point_in_time")
        require_exact_bool(
            self.later_decision_date_cross_sections_bound,
            "later_decision_date_cross_sections_bound",
        )
        if (
            self.cross_section_evidence_scope != ELIGIBILITY_CROSS_SECTION_SCOPE
            or self.later_decision_date_cross_sections_bound
        ):
            raise ProductionInputError(
                "event row cannot bind or persist a later decision-date cross-section"
            )
        if self.pristine_point_in_time:
            raise ProductionInputError("accepted-risk row cannot be labeled pristine PIT")
        expected_sha256 = sha256_bytes(canonical_json_bytes(self.semantic_record()))
        if self.row_sha256 != expected_sha256 or self.row_id != (
            f"arv2_preoutcome_{expected_sha256[:24]}"
        ):
            raise ProductionInputError("normalized row identity is not content-derived")

    def semantic_record(self) -> dict[str, Any]:
        return {
            "source_locator": self.source_locator.to_record(),
            "source_role": self.source_role.value,
            "signal_arm": self.signal_arm.value,
            "source_view_label": self.source_view_label,
            "provider_event_id": self.provider_event_id,
            "provider_version_id": self.provider_version_id,
            "event_date": self.event_date,
            "publication_at_utc": self.publication_at_utc,
            "eligible_session": self.eligible_session,
            "decision_cutoff_at": self.decision_cutoff_at,
            "current_restated_ticker": self.current_restated_ticker,
            "historical_ticker": self.historical_ticker,
            "issuer_id": self.issuer_id,
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "listing_id": self.listing_id,
            "institution_id": self.institution_id,
            "common_event_id": self.common_event_id,
            "sector_id": self.sector_id,
            "industry_id": self.industry_id,
            "raw_action": self.raw_action,
            "previous_score": _fraction_record(self.previous_score),
            "current_score": _fraction_record(self.current_score),
            "rating_change": _fraction_record(self.rating_change),
            "q_data": _decimal_text(self.q_data),
            "security_master_sha256": self.security_master_sha256,
            "identity_mapping_evidence_sha256": self.identity_mapping_evidence_sha256,
            "ontology_sha256": self.ontology_sha256,
            "ontology_entry_sha256": self.ontology_entry_sha256,
            "common_event_evidence_sha256": self.common_event_evidence_sha256,
            "sector_evidence_sha256": self.sector_evidence_sha256,
            "control_evidence_sha256": self.control_evidence_sha256,
            "control_vector_sha256": self.control_vector_sha256,
            "q_data_evidence_sha256": self.q_data_evidence_sha256,
            "cross_section_evidence_scope": self.cross_section_evidence_scope,
            "later_decision_date_cross_sections_bound": False,
            "pristine_point_in_time": False,
        }

    def to_record(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "row_sha256": self.row_sha256,
            **self.semantic_record(),
        }


@dataclasses.dataclass(frozen=True)
class RowAdmission:
    source_locator: CaptureRowLocator
    source_role: MassiveSourceRole
    signal_arm: SignalArm
    source_view_disposition: RowDisposition
    disposition: AdmissionDisposition
    potential_directional: bool
    evidence_sha256: str | None
    normalized_row: NormalizedPreOutcomeRow | None
    terminal_sha256: str

    def __post_init__(self) -> None:
        if type(self.terminal_sha256) is not str:
            raise ProductionInputError("admission terminal_sha256 must be exact string")
        if self.evidence_sha256 is not None and type(self.evidence_sha256) is not str:
            raise ProductionInputError("admission evidence_sha256 must be exact string or null")
        if type(self.source_locator) is not CaptureRowLocator:
            raise ProductionInputError("admission locator has wrong type")
        if type(self.source_role) is not MassiveSourceRole or self.source_role is not self.source_locator.source_role:
            raise ProductionInputError("admission source role does not match locator")
        if type(self.signal_arm) is not SignalArm:
            raise ProductionInputError("admission signal arm has wrong type")
        if type(self.source_view_disposition) is not RowDisposition:
            raise ProductionInputError("source view disposition has wrong type")
        if type(self.disposition) is not AdmissionDisposition:
            raise ProductionInputError("admission disposition has wrong type")
        require_exact_bool(self.potential_directional, "potential_directional")
        if (
            self.disposition
            is AdmissionDisposition.INCLUDED_DIRECTIONAL_RATING_REVISION
            and not self.potential_directional
        ):
            raise ProductionInputError(
                "an included directional row must be censused as potentially directional"
            )
        if self.evidence_sha256 is not None:
            require_sha256(self.evidence_sha256, "evidence_sha256")
        included = self.disposition is AdmissionDisposition.INCLUDED_DIRECTIONAL_RATING_REVISION
        if included != (self.normalized_row is not None):
            raise ProductionInputError("admission disposition and normalized row disagree")
        if self.normalized_row is not None and (
            type(self.normalized_row) is not NormalizedPreOutcomeRow
            or self.normalized_row.source_locator != self.source_locator
            or self.normalized_row.signal_arm is not self.signal_arm
        ):
            raise ProductionInputError("admission normalized row is not source-bound")
        require_sha256(self.terminal_sha256, "terminal_sha256")
        if self.terminal_sha256 != self.derived_sha256:
            raise ProductionInputError("admission terminal hash is not content-derived")

    def semantic_record(self) -> dict[str, Any]:
        return {
            "source_locator": self.source_locator.to_record(),
            "source_role": self.source_role.value,
            "signal_arm": self.signal_arm.value,
            "source_view_disposition": self.source_view_disposition.value,
            "disposition": self.disposition.value,
            "potential_directional": self.potential_directional,
            "evidence_sha256": self.evidence_sha256,
            "normalized_row_sha256": (
                None if self.normalized_row is None else self.normalized_row.row_sha256
            ),
        }

    @property
    def derived_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.semantic_record()))

    def to_record(self) -> dict[str, Any]:
        return {**self.semantic_record(), "terminal_sha256": self.terminal_sha256}


def _row_evidence_sha256(evidence: ProductionRowEvidence | None) -> str | None:
    return None if evidence is None else sha256_bytes(canonical_json_bytes(evidence.to_record()))


def _row_admission(
    *,
    source: AcceptedRiskSourceRow,
    arm: SignalArm,
    source_disposition: RowDisposition,
    disposition: AdmissionDisposition,
    potential_directional: bool,
    evidence: ProductionRowEvidence | None,
    normalized: NormalizedPreOutcomeRow | None = None,
) -> RowAdmission:
    evidence_sha256 = _row_evidence_sha256(evidence)
    semantic = {
        "source_locator": source.locator.to_record(),
        "source_role": source.locator.source_role.value,
        "signal_arm": arm.value,
        "source_view_disposition": source_disposition.value,
        "disposition": disposition.value,
        "potential_directional": potential_directional,
        "evidence_sha256": evidence_sha256,
        "normalized_row_sha256": None if normalized is None else normalized.row_sha256,
    }
    return RowAdmission(
        source_locator=source.locator,
        source_role=source.locator.source_role,
        signal_arm=arm,
        source_view_disposition=source_disposition,
        disposition=disposition,
        potential_directional=potential_directional,
        evidence_sha256=evidence_sha256,
        normalized_row=normalized,
        terminal_sha256=sha256_bytes(canonical_json_bytes(semantic)),
    )


def _normalized_row(
    *,
    source: AcceptedRiskSourceRow,
    parsed: _ParsedRatingRow,
    evidence: ProductionRowEvidence,
    arm: SignalArm,
) -> NormalizedPreOutcomeRow:
    security = evidence.security
    firm = evidence.firm
    common = evidence.common_event
    sector = evidence.sector
    control = evidence.control
    quality = evidence.q_data
    if any(
        value is None
        for value in (security, firm, common, sector, control, quality)
    ):
        raise AssertionError("normalization called before complete evidence admission")
    assert security is not None and firm is not None and common is not None
    assert sector is not None and control is not None and quality is not None
    eligibility = (
        source.current_view
        if arm is SignalArm.CURRENT_VINTAGE
        else source.censored_view
    )
    if eligibility.eligible_session is None or eligibility.decision_cutoff_at is None:
        raise AssertionError("normalization called without an eligibility clock")
    publication_at_utc = (
        None
        if source.raw_event_time is None
        else f"{parsed.event_date}T{source.raw_event_time}.000000Z"
    )
    if publication_at_utc is not None:
        parse_utc_timestamp(publication_at_utc, "publication_at_utc")
    semantic = {
        "source_locator": source.locator.to_record(),
        "source_role": MassiveSourceRole.ANALYST_RATINGS.value,
        "signal_arm": arm.value,
        "source_view_label": _ARM_TO_LABEL[arm],
        "provider_event_id": parsed.provider_event_id,
        "provider_version_id": f"{PROVIDER_VERSION_PREFIX}{source.locator.raw_row_sha256}",
        "event_date": parsed.event_date,
        "publication_at_utc": publication_at_utc,
        "eligible_session": eligibility.eligible_session,
        "decision_cutoff_at": eligibility.decision_cutoff_at,
        "current_restated_ticker": parsed.current_restated_ticker,
        "historical_ticker": security.historical_ticker,
        "issuer_id": security.issuer_id,
        "security_id": security.security_id,
        "share_class_id": security.share_class_id,
        "listing_id": security.listing_id,
        "institution_id": firm.institution_id,
        "common_event_id": common.common_event_id,
        "sector_id": sector.sector_id,
        "industry_id": control.industry_id,
        "raw_action": parsed.raw_action,
        "previous_score": _fraction_record(firm.previous_score),
        "current_score": _fraction_record(firm.current_score),
        "rating_change": _fraction_record(firm.current_score - firm.previous_score),
        "q_data": _decimal_text(quality.q_data),
        "security_master_sha256": security.security_master_sha256,
        "identity_mapping_evidence_sha256": security.mapping_evidence_sha256,
        "ontology_sha256": firm.ontology_sha256,
        "ontology_entry_sha256": firm.ontology_entry_sha256,
        "common_event_evidence_sha256": common.evidence_sha256,
        "sector_evidence_sha256": sector.evidence_sha256,
        "control_evidence_sha256": control.evidence_sha256,
        "control_vector_sha256": control.control_vector_sha256,
        "q_data_evidence_sha256": quality.evidence_sha256,
        "cross_section_evidence_scope": ELIGIBILITY_CROSS_SECTION_SCOPE,
        "later_decision_date_cross_sections_bound": False,
        "pristine_point_in_time": False,
    }
    digest = sha256_bytes(canonical_json_bytes(semantic))
    return NormalizedPreOutcomeRow(
        row_id=f"arv2_preoutcome_{digest[:24]}",
        row_sha256=digest,
        source_locator=source.locator,
        source_role=MassiveSourceRole.ANALYST_RATINGS,
        signal_arm=arm,
        source_view_label=_ARM_TO_LABEL[arm],
        provider_event_id=parsed.provider_event_id,
        provider_version_id=f"{PROVIDER_VERSION_PREFIX}{source.locator.raw_row_sha256}",
        event_date=parsed.event_date,
        publication_at_utc=publication_at_utc,
        eligible_session=eligibility.eligible_session,
        decision_cutoff_at=eligibility.decision_cutoff_at,
        current_restated_ticker=parsed.current_restated_ticker,
        historical_ticker=security.historical_ticker,
        issuer_id=security.issuer_id,
        security_id=security.security_id,
        share_class_id=security.share_class_id,
        listing_id=security.listing_id,
        institution_id=firm.institution_id,
        common_event_id=common.common_event_id,
        sector_id=sector.sector_id,
        industry_id=control.industry_id,
        raw_action=parsed.raw_action,
        previous_score=firm.previous_score,
        current_score=firm.current_score,
        rating_change=firm.current_score - firm.previous_score,
        q_data=quality.q_data,
        security_master_sha256=security.security_master_sha256,
        identity_mapping_evidence_sha256=security.mapping_evidence_sha256,
        ontology_sha256=firm.ontology_sha256,
        ontology_entry_sha256=firm.ontology_entry_sha256,
        common_event_evidence_sha256=common.evidence_sha256,
        sector_evidence_sha256=sector.evidence_sha256,
        control_evidence_sha256=control.evidence_sha256,
        control_vector_sha256=control.control_vector_sha256,
        q_data_evidence_sha256=quality.evidence_sha256,
        cross_section_evidence_scope=ELIGIBILITY_CROSS_SECTION_SCOPE,
        later_decision_date_cross_sections_bound=False,
        pristine_point_in_time=False,
    )


def _at_or_after_cutoff(value: str, cutoff: str) -> bool:
    return parse_utc_timestamp(value, "evidence.available_at") >= parse_utc_timestamp(
        cutoff, "decision_cutoff_at"
    )


def _admit_directional_rating(
    *,
    source: AcceptedRiskSourceRow,
    parsed: _ParsedRatingRow,
    evidence: ProductionRowEvidence | None,
    sources: dict[EvidenceSourceKind, EvidenceSourceBinding],
    arm: SignalArm,
    source_disposition: RowDisposition,
) -> RowAdmission:
    def refuse(disposition: AdmissionDisposition) -> RowAdmission:
        return _row_admission(
            source=source,
            arm=arm,
            source_disposition=source_disposition,
            disposition=disposition,
            potential_directional=True,
            evidence=evidence,
        )

    if evidence is None:
        return refuse(AdmissionDisposition.MISSING_ROW_EVIDENCE)
    if not sources[EvidenceSourceKind.FIRM_ONTOLOGY].reviewed:
        return refuse(AdmissionDisposition.FIRM_ONTOLOGY_UNREVIEWED)
    if any(not binding.reviewed for binding in sources.values()):
        return refuse(AdmissionDisposition.UNREVIEWED_EVIDENCE_SOURCE)
    if any(not binding.point_in_time for binding in sources.values()):
        return refuse(AdmissionDisposition.NON_PIT_EVIDENCE_SOURCE)

    security = evidence.security
    if security is None:
        return refuse(AdmissionDisposition.MISSING_PIT_SECURITY_EVIDENCE)
    if security.current_ticker_only:
        return refuse(AdmissionDisposition.SECURITY_IDENTITY_CURRENT_TICKER_ONLY)
    if not security.point_in_time:
        return refuse(AdmissionDisposition.SECURITY_IDENTITY_NOT_PIT)
    if security.candidate_count != 1:
        return refuse(AdmissionDisposition.SECURITY_IDENTITY_AMBIGUOUS)
    eligibility = (
        source.current_view
        if arm is SignalArm.CURRENT_VINTAGE
        else source.censored_view
    )
    if eligibility.eligible_session is None or eligibility.decision_cutoff_at is None:
        raise ProductionInputError("included C1 row has no exact decision clock")
    cutoff = eligibility.decision_cutoff_at
    if (
        security.provider_event_id != parsed.provider_event_id
        or security.source_current_restated_ticker != parsed.current_restated_ticker
        or not _contains_visible_interval(
            valid_from=security.valid_from,
            valid_to=security.valid_to,
            valid_to_available_at=security.valid_to_available_at,
            when=parsed.event_date,
            cutoff=cutoff,
        )
    ):
        return refuse(AdmissionDisposition.SECURITY_IDENTITY_MISMATCH)
    if _at_or_after_cutoff(security.available_at, cutoff):
        return refuse(AdmissionDisposition.SECURITY_IDENTITY_LATE)

    firm = evidence.firm
    if firm is None:
        return refuse(AdmissionDisposition.MISSING_FIRM_ONTOLOGY_EVIDENCE)
    if not firm.ontology_reviewed:
        return refuse(AdmissionDisposition.FIRM_ONTOLOGY_UNREVIEWED)
    if not firm.labels_reviewed:
        return refuse(AdmissionDisposition.FIRM_LABEL_UNREVIEWED)
    if firm.candidate_count != 1:
        return refuse(AdmissionDisposition.FIRM_MAPPING_AMBIGUOUS)
    if (
        firm.provider_event_id != parsed.provider_event_id
        or firm.provider_firm_id != parsed.provider_firm_id
        or firm.raw_firm_name != parsed.raw_firm_name
        or firm.raw_current_label != parsed.current_label
        or firm.raw_previous_label != parsed.previous_label
        or not _contains_visible_interval(
            valid_from=firm.valid_from,
            valid_to=firm.valid_to,
            valid_to_available_at=firm.valid_to_available_at,
            when=parsed.event_date,
            cutoff=cutoff,
        )
    ):
        return refuse(AdmissionDisposition.FIRM_MAPPING_MISMATCH)
    if _at_or_after_cutoff(firm.available_at, cutoff):
        return refuse(AdmissionDisposition.FIRM_MAPPING_LATE)
    change = firm.current_score - firm.previous_score
    if change == 0 or (
        parsed.raw_action == "upgrades" and change <= 0
    ) or (
        parsed.raw_action == "downgrades" and change >= 0
    ):
        return refuse(AdmissionDisposition.RATING_DIRECTION_MISMATCH)

    common = evidence.common_event
    if common is None:
        return refuse(AdmissionDisposition.MISSING_COMMON_EVENT_EVIDENCE)
    if common.candidate_count != 1:
        return refuse(AdmissionDisposition.COMMON_EVENT_AMBIGUOUS)
    if common.provider_event_id != parsed.provider_event_id:
        return refuse(AdmissionDisposition.COMMON_EVENT_MISMATCH)
    if _at_or_after_cutoff(common.available_at, cutoff):
        return refuse(AdmissionDisposition.COMMON_EVENT_LATE)

    sector = evidence.sector
    if sector is None:
        return refuse(AdmissionDisposition.MISSING_PIT_SECTOR_EVIDENCE)
    if sector.candidate_count != 1:
        return refuse(AdmissionDisposition.SECTOR_AMBIGUOUS)
    if not sector.point_in_time:
        return refuse(AdmissionDisposition.SECTOR_NOT_PIT)
    if (
        sector.security_id != security.security_id
        or not _contains_visible_interval(
            valid_from=sector.valid_from,
            valid_to=sector.valid_to,
            valid_to_available_at=sector.valid_to_available_at,
            when=eligibility.eligible_session,
            cutoff=cutoff,
        )
    ):
        return refuse(AdmissionDisposition.SECTOR_MISMATCH)
    if _at_or_after_cutoff(sector.available_at, cutoff):
        return refuse(AdmissionDisposition.SECTOR_LATE)

    control = evidence.control
    if control is None:
        return refuse(AdmissionDisposition.MISSING_PREOPEN_CONTROL_EVIDENCE)
    if control.contains_outcome_or_price:
        return refuse(AdmissionDisposition.CONTROL_CONTAINS_OUTCOME_OR_PRICE)
    if not control.point_in_time:
        return refuse(AdmissionDisposition.CONTROL_NOT_PIT)
    if (
        not control.complete
        or control.security_id != security.security_id
        or control.decision_session != eligibility.eligible_session
    ):
        return refuse(AdmissionDisposition.CONTROL_MISMATCH)
    if _at_or_after_cutoff(control.available_at, cutoff):
        return refuse(AdmissionDisposition.CONTROL_LATE)

    quality = evidence.q_data
    if quality is None:
        return refuse(AdmissionDisposition.MISSING_Q_DATA_EVIDENCE)
    if not quality.point_in_time:
        return refuse(AdmissionDisposition.Q_DATA_NOT_PIT)
    if (
        quality.security_id != security.security_id
        or quality.measured_session != eligibility.eligible_session
    ):
        return refuse(AdmissionDisposition.Q_DATA_MISMATCH)
    if _at_or_after_cutoff(quality.available_at, cutoff):
        return refuse(AdmissionDisposition.Q_DATA_LATE)

    normalized = _normalized_row(
        source=source,
        parsed=parsed,
        evidence=evidence,
        arm=arm,
    )
    return _row_admission(
        source=source,
        arm=arm,
        source_disposition=source_disposition,
        disposition=AdmissionDisposition.INCLUDED_DIRECTIONAL_RATING_REVISION,
        potential_directional=True,
        evidence=evidence,
        normalized=normalized,
    )


def _admit_source_row(
    *,
    source: AcceptedRiskSourceRow,
    evidence: ProductionRowEvidence | None,
    sources: dict[EvidenceSourceKind, EvidenceSourceBinding],
    arm: SignalArm,
) -> RowAdmission:
    eligibility = (
        source.current_view
        if arm is SignalArm.CURRENT_VINTAGE
        else source.censored_view
    )

    def terminal(
        disposition: AdmissionDisposition,
        *,
        potential_directional: bool = False,
    ) -> RowAdmission:
        return _row_admission(
            source=source,
            arm=arm,
            source_disposition=eligibility.disposition,
            disposition=disposition,
            potential_directional=potential_directional,
            evidence=evidence,
        )

    if source.locator.source_role is MassiveSourceRole.CORPORATE_GUIDANCE:
        return terminal(AdmissionDisposition.GUIDANCE_CLOCK_QUARANTINED)
    if source.event_year is not None and source.event_year < 2013:
        return terminal(AdmissionDisposition.PRE_2013_QUARANTINED)
    if not eligibility.included:
        return terminal(AdmissionDisposition.SOURCE_VIEW_EXCLUDED)
    if source.locator.source_role is not MassiveSourceRole.ANALYST_RATINGS:
        return terminal(AdmissionDisposition.NON_RATING_SOURCE_ROLE)
    potential_directional = _potential_directional_action(source)
    try:
        parsed = _parse_rating_row(source)
    except _RatingRowRefusal as exc:
        return terminal(
            exc.disposition,
            potential_directional=potential_directional,
        )
    if parsed.raw_action in _UNSUPPORTED_DOCUMENTED_ACTIONS:
        return terminal(
            AdmissionDisposition.UNSUPPORTED_RATING_ACTION,
            potential_directional=True,
        )
    if parsed.raw_action not in _KNOWN_RATING_ACTIONS | {_TARGET_ONLY_ACTION}:
        return terminal(
            AdmissionDisposition.UNKNOWN_RATING_ACTION,
            potential_directional=True,
        )
    if parsed.raw_action not in _DIRECTIONAL_ACTIONS:
        return terminal(AdmissionDisposition.NON_DIRECTIONAL_RATING_ACTION)
    return _admit_directional_rating(
        source=source,
        parsed=parsed,
        evidence=evidence,
        sources=sources,
        arm=arm,
        source_disposition=eligibility.disposition,
    )


@dataclasses.dataclass(frozen=True)
class ComparisonRate:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        require_int(self.numerator, "comparison numerator", minimum=0)
        require_int(self.denominator, "comparison denominator", minimum=1)
        if self.numerator > self.denominator:
            raise ProductionInputError("comparison numerator exceeds denominator")

    @property
    def fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    def to_record(self) -> dict[str, int]:
        return {"numerator": self.numerator, "denominator": self.denominator}


@dataclasses.dataclass(frozen=True)
class ArmComparisonBreakdown:
    dimension: ComparisonDimension
    key: str
    total_count: int
    current_admitted_count: int
    current_refused_count: int
    censored_admitted_count: int
    censored_refused_count: int
    mapping_disagreement_count: int
    signal_disagreement_count: int
    current_admitted_rate: ComparisonRate
    current_refused_rate: ComparisonRate
    censored_admitted_rate: ComparisonRate
    censored_refused_rate: ComparisonRate
    mapping_disagreement_rate: ComparisonRate
    signal_disagreement_rate: ComparisonRate

    def __post_init__(self) -> None:
        if type(self.dimension) is not ComparisonDimension:
            raise ProductionInputError("comparison dimension has wrong type")
        require_text(self.key, "comparison key")
        for name in (
            "total_count",
            "current_admitted_count",
            "current_refused_count",
            "censored_admitted_count",
            "censored_refused_count",
            "mapping_disagreement_count",
            "signal_disagreement_count",
        ):
            require_int(getattr(self, name), name, minimum=0)
        if self.total_count <= 0:
            raise ProductionInputError("comparison breakdown cannot be empty")
        if (
            self.current_admitted_count + self.current_refused_count
            != self.total_count
            or self.censored_admitted_count + self.censored_refused_count
            != self.total_count
        ):
            raise ProductionInputError("comparison arm census is not exhaustive")
        rate_pairs = (
            (self.current_admitted_rate, self.current_admitted_count),
            (self.current_refused_rate, self.current_refused_count),
            (self.censored_admitted_rate, self.censored_admitted_count),
            (self.censored_refused_rate, self.censored_refused_count),
            (self.mapping_disagreement_rate, self.mapping_disagreement_count),
            (self.signal_disagreement_rate, self.signal_disagreement_count),
        )
        if any(
            type(rate) is not ComparisonRate
            or rate.numerator != count
            or rate.denominator != self.total_count
            for rate, count in rate_pairs
        ):
            raise ProductionInputError("comparison rates are not count-derived")

    def to_record(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension.value,
            "key": self.key,
            "total_count": self.total_count,
            "current_admitted_count": self.current_admitted_count,
            "current_refused_count": self.current_refused_count,
            "censored_admitted_count": self.censored_admitted_count,
            "censored_refused_count": self.censored_refused_count,
            "mapping_disagreement_count": self.mapping_disagreement_count,
            "signal_disagreement_count": self.signal_disagreement_count,
            "current_admitted_rate": self.current_admitted_rate.to_record(),
            "current_refused_rate": self.current_refused_rate.to_record(),
            "censored_admitted_rate": self.censored_admitted_rate.to_record(),
            "censored_refused_rate": self.censored_refused_rate.to_record(),
            "mapping_disagreement_rate": (
                self.mapping_disagreement_rate.to_record()
            ),
            "signal_disagreement_rate": self.signal_disagreement_rate.to_record(),
        }


@dataclasses.dataclass(frozen=True)
class ProductionInputComparisonReport:
    schema: str
    report_sha256: str
    pair_id: str
    pair_sha256: str
    breakdowns: tuple[ArmComparisonBreakdown, ...]
    exhaustive: bool
    pre_return: bool
    outcome_access: bool

    def __post_init__(self) -> None:
        _require_exact_strings(
            self,
            ("schema", "report_sha256", "pair_id", "pair_sha256"),
            "comparison_report",
        )
        if self.schema != COMPARISON_REPORT_SCHEMA:
            raise ProductionInputError("wrong comparison-report schema")
        require_identifier(self.pair_id, "comparison pair_id")
        require_sha256(self.pair_sha256, "comparison pair_sha256")
        require_sha256(self.report_sha256, "comparison report_sha256")
        if type(self.breakdowns) is not tuple or any(
            type(item) is not ArmComparisonBreakdown for item in self.breakdowns
        ):
            raise ProductionInputError("comparison breakdowns must be an exact tuple")
        if not self.breakdowns or self.breakdowns[0].dimension is not ComparisonDimension.OVERALL:
            raise ProductionInputError("comparison report must begin with overall")
        if {item.dimension for item in self.breakdowns} != set(ComparisonDimension):
            raise ProductionInputError("comparison dimensions are not exhaustive")
        for name in ("exhaustive", "pre_return", "outcome_access"):
            require_exact_bool(getattr(self, name), f"comparison.{name}")
        if not self.exhaustive or not self.pre_return or self.outcome_access:
            raise ProductionInputError("comparison report crossed its pre-return boundary")
        if self.report_sha256 != sha256_bytes(
            canonical_json_bytes(self.semantic_record())
        ):
            raise ProductionInputError("comparison report hash is not content-derived")

    def semantic_record(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "pair_id": self.pair_id,
            "pair_sha256": self.pair_sha256,
            "breakdowns": [item.to_record() for item in self.breakdowns],
            "exhaustive": True,
            "pre_return": True,
            "outcome_access": False,
        }

    def to_record(self) -> dict[str, Any]:
        return {"report_sha256": self.report_sha256, **self.semantic_record()}


@dataclasses.dataclass(frozen=True, init=False)
class ProductionInputBatch:
    schema: str
    status: str
    contract_id: str
    contract_sha256: str
    batch_id: str
    batch_sha256: str
    evidence_authority: ProductionEvidenceAuthority
    evidence_authority_id: str
    evidence_authority_sha256: str
    pair_id: str
    pair_sha256: str
    signal_arm: SignalArm
    source_view: InputView
    source_view_label: str
    non_pristine_disclosure: str
    total_source_row_count: int
    source_view_included_count: int
    directional_candidate_count: int
    normalized_row_count: int
    refused_directional_count: int
    admissions: tuple[RowAdmission, ...]
    normalized_rows: tuple[NormalizedPreOutcomeRow, ...]
    comparison_report: ProductionInputComparisonReport
    exhaustive_source_census: bool
    source_role_separate_from_signal_arm: bool
    event_level_only: bool
    decision_date_cross_sections_required: bool
    decision_date_cross_sections_bound: bool
    pristine_point_in_time: bool
    earlier_version_imputation_performed: bool
    production_input_authority: bool
    formal_backtest_input_ready: bool
    production_registry_receipt: None
    production_truth_approval: None
    outcome_authority: None
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

    @property
    def all_directional_rows_admitted(self) -> bool:
        _PINNED_REQUIRE_STATIC_CONTRACT()
        _require_static_contract()
        return self.directional_candidate_count > 0 and self.refused_directional_count == 0


_BATCH_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType[ProductionInputBatch], tuple[object, ...]]
] = {}
_BATCH_AUTHORITIES_LOCK = threading.RLock()


def _batch_semantic_record(
    *,
    authority: ProductionEvidenceAuthority,
    arm: SignalArm,
    admissions: tuple[RowAdmission, ...],
    directional_candidate_count: int,
    comparison_report: ProductionInputComparisonReport,
) -> dict[str, Any]:
    view = _ARM_TO_VIEW[arm]
    normalized = tuple(
        item.normalized_row for item in admissions if item.normalized_row is not None
    )
    source_view_included = sum(
        (
            row.current_view.included
            if view is InputView.CURRENT_ROW
            else row.censored_view.included
        )
        for row in authority.pair.rows
    )
    return {
        "schema": PRODUCTION_INPUT_BATCH_SCHEMA,
        "status": PRODUCTION_INPUT_STATUS,
        "contract_id": PRODUCTION_INPUT_CONTRACT_ID,
        "contract_sha256": PRODUCTION_INPUT_CONTRACT_SHA256,
        "evidence_authority_id": authority.authority_id,
        "evidence_authority_sha256": authority.authority_sha256,
        "pair_id": authority.pair_id,
        "pair_sha256": authority.pair_sha256,
        "signal_arm": arm.value,
        "source_view": view.value,
        "source_view_label": _ARM_TO_LABEL[arm],
        "non_pristine_disclosure": NON_PRISTINE_DISCLOSURE,
        "total_source_row_count": len(authority.pair.rows),
        "source_view_included_count": source_view_included,
        "directional_candidate_count": directional_candidate_count,
        "normalized_row_count": len(normalized),
        "refused_directional_count": directional_candidate_count - len(normalized),
        "admissions": [item.to_record() for item in admissions],
        "normalized_rows": [item.to_record() for item in normalized],
        "comparison_report": comparison_report.to_record(),
        "exhaustive_source_census": True,
        "source_role_separate_from_signal_arm": True,
        "event_level_only": True,
        "decision_date_cross_sections_required": True,
        "decision_date_cross_sections_bound": False,
        "pristine_point_in_time": False,
        "earlier_version_imputation_performed": False,
        "production_input_authority": False,
        "formal_backtest_input_ready": False,
        "external_bindings": {
            "production_registry_receipt": None,
            "production_truth_approval": None,
            "outcome_authority": None,
        },
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


def _batch_fingerprint(batch: ProductionInputBatch) -> tuple[object, ...]:
    return (
        id(batch.evidence_authority),
        batch.batch_id,
        batch.batch_sha256,
        canonical_json_bytes(
            _batch_semantic_record(
                authority=batch.evidence_authority,
                arm=batch.signal_arm,
                admissions=batch.admissions,
                directional_candidate_count=batch.directional_candidate_count,
                comparison_report=batch.comparison_report,
            )
        ),
    )


def _forget_batch(
    identity: int, reference: weakref.ReferenceType[ProductionInputBatch]
) -> None:
    with _BATCH_AUTHORITIES_LOCK:
        current = _BATCH_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _BATCH_AUTHORITIES.pop(identity, None)


def _validate_batch_surface(batch: ProductionInputBatch) -> None:
    _require_exact_strings(
        batch,
        (
            "schema",
            "status",
            "contract_id",
            "contract_sha256",
            "batch_id",
            "batch_sha256",
            "evidence_authority_id",
            "evidence_authority_sha256",
            "pair_id",
            "pair_sha256",
            "source_view_label",
            "non_pristine_disclosure",
        ),
        "batch",
    )
    if type(batch.signal_arm) is not SignalArm:
        raise ProductionInputError("batch signal arm has wrong type")
    if type(batch.source_view) is not InputView:
        raise ProductionInputError("batch source view has wrong type")
    for name in (
        "total_source_row_count",
        "source_view_included_count",
        "directional_candidate_count",
        "normalized_row_count",
        "refused_directional_count",
    ):
        require_int(getattr(batch, name), f"batch.{name}", minimum=0)
    true_flags = (
        batch.exhaustive_source_census,
        batch.source_role_separate_from_signal_arm,
        batch.event_level_only,
        batch.decision_date_cross_sections_required,
    )
    if any(type(flag) is not bool or flag is not True for flag in true_flags):
        raise ProductionInputError("batch exhaustive/separation invariant changed")
    false_flags = (
        batch.pristine_point_in_time,
        batch.earlier_version_imputation_performed,
        batch.production_input_authority,
        batch.formal_backtest_input_ready,
        batch.decision_date_cross_sections_bound,
        batch.provider_access,
        batch.credential_access,
        batch.filesystem_access,
        batch.quantconnect_access,
        batch.object_store_access,
        batch.price_access,
        batch.outcome_access,
        batch.deployment,
        batch.orders,
        batch.trading,
    )
    if any(type(flag) is not bool or flag is not False for flag in false_flags):
        raise ProductionInputError("pre-outcome batch acquired a forbidden capability")
    if any(
        value is not None
        for value in (
            batch.production_registry_receipt,
            batch.production_truth_approval,
            batch.outcome_authority,
        )
    ):
        raise ProductionInputError("pre-outcome batch acquired an external binding")
    if type(batch.comparison_report) is not ProductionInputComparisonReport:
        raise ProductionInputError("batch comparison report has wrong type")
    batch.comparison_report.__post_init__()
    if (
        batch.comparison_report.pair_id != batch.pair_id
        or batch.comparison_report.pair_sha256 != batch.pair_sha256
    ):
        raise ProductionInputError("batch comparison report is not pair-bound")


def _derive_batch_parts(
    authority: ProductionEvidenceAuthority,
    arm: SignalArm,
) -> tuple[tuple[RowAdmission, ...], int]:
    evidence_by_locator = {item.locator: item for item in authority.row_evidence}
    sources = _source_map(authority.source_bindings)
    admissions: list[RowAdmission] = []
    for source in authority.pair.rows:
        admission = _admit_source_row(
            source=source,
            evidence=evidence_by_locator.get(source.locator),
            sources=sources,
            arm=arm,
        )
        admissions.append(admission)
    result = tuple(admissions)
    return result, sum(item.potential_directional for item in result)


def _mapping_signature(admission: RowAdmission) -> tuple[str, ...] | None:
    row = admission.normalized_row
    if row is None:
        return None
    return (
        row.issuer_id,
        row.security_id,
        row.share_class_id,
        row.listing_id,
        row.historical_ticker,
        row.identity_mapping_evidence_sha256,
    )


def _signal_signature(admission: RowAdmission) -> tuple[object, ...] | None:
    row = admission.normalized_row
    if row is None:
        return None
    return (
        row.provider_event_id,
        row.provider_version_id,
        row.event_date,
        row.eligible_session,
        row.security_id,
        row.institution_id,
        row.common_event_id,
        row.raw_action,
        row.previous_score,
        row.current_score,
        row.rating_change,
    )


def _comparison_dimension_key(
    *,
    dimension: ComparisonDimension,
    source: AcceptedRiskSourceRow,
    evidence: ProductionRowEvidence | None,
) -> str:
    if dimension is ComparisonDimension.OVERALL:
        return "all_rows"
    if dimension is ComparisonDimension.EVENT_YEAR:
        return (
            str(source.event_year)
            if source.event_year is not None
            else "__invalid_event_year__"
        )
    if dimension is ComparisonDimension.ACTION:
        return source.action_label
    if dimension is ComparisonDimension.FIRM:
        if evidence is not None and evidence.firm is not None:
            return evidence.firm.institution_id
        return f"unmapped:{source.firm_label}"
    if dimension is ComparisonDimension.SECURITY:
        if evidence is not None and evidence.security is not None:
            return evidence.security.security_id
        return f"unmapped:{source.current_restated_security_label}"
    raise AssertionError("unhandled comparison dimension")


def _comparison_breakdown(
    *,
    dimension: ComparisonDimension,
    key: str,
    indexes: tuple[int, ...],
    current: tuple[RowAdmission, ...],
    censored: tuple[RowAdmission, ...],
) -> ArmComparisonBreakdown:
    total = len(indexes)
    current_admitted = sum(
        current[index].normalized_row is not None for index in indexes
    )
    censored_admitted = sum(
        censored[index].normalized_row is not None for index in indexes
    )
    mapping_disagreement = sum(
        _mapping_signature(current[index])
        != _mapping_signature(censored[index])
        for index in indexes
    )
    signal_disagreement = sum(
        _signal_signature(current[index]) != _signal_signature(censored[index])
        for index in indexes
    )
    values = {
        "current_admitted": current_admitted,
        "current_refused": total - current_admitted,
        "censored_admitted": censored_admitted,
        "censored_refused": total - censored_admitted,
        "mapping_disagreement": mapping_disagreement,
        "signal_disagreement": signal_disagreement,
    }
    return ArmComparisonBreakdown(
        dimension=dimension,
        key=key,
        total_count=total,
        current_admitted_count=values["current_admitted"],
        current_refused_count=values["current_refused"],
        censored_admitted_count=values["censored_admitted"],
        censored_refused_count=values["censored_refused"],
        mapping_disagreement_count=values["mapping_disagreement"],
        signal_disagreement_count=values["signal_disagreement"],
        current_admitted_rate=ComparisonRate(values["current_admitted"], total),
        current_refused_rate=ComparisonRate(values["current_refused"], total),
        censored_admitted_rate=ComparisonRate(values["censored_admitted"], total),
        censored_refused_rate=ComparisonRate(values["censored_refused"], total),
        mapping_disagreement_rate=ComparisonRate(
            values["mapping_disagreement"], total
        ),
        signal_disagreement_rate=ComparisonRate(
            values["signal_disagreement"], total
        ),
    )


def _build_comparison_report(
    authority: ProductionEvidenceAuthority,
) -> ProductionInputComparisonReport:
    current, _ = _derive_batch_parts(authority, SignalArm.CURRENT_VINTAGE)
    censored, _ = _derive_batch_parts(authority, SignalArm.CONSERVATIVE_CENSORED)
    evidence_by_locator = {item.locator: item for item in authority.row_evidence}
    breakdowns: list[ArmComparisonBreakdown] = []
    for dimension in ComparisonDimension:
        grouped: dict[str, list[int]] = {}
        for index, source in enumerate(authority.pair.rows):
            key = _comparison_dimension_key(
                dimension=dimension,
                source=source,
                evidence=evidence_by_locator.get(source.locator),
            )
            grouped.setdefault(key, []).append(index)
        for key in sorted(grouped):
            breakdowns.append(
                _comparison_breakdown(
                    dimension=dimension,
                    key=key,
                    indexes=tuple(grouped[key]),
                    current=current,
                    censored=censored,
                )
            )
    semantic = {
        "schema": COMPARISON_REPORT_SCHEMA,
        "pair_id": authority.pair_id,
        "pair_sha256": authority.pair_sha256,
        "breakdowns": [item.to_record() for item in breakdowns],
        "exhaustive": True,
        "pre_return": True,
        "outcome_access": False,
    }
    return ProductionInputComparisonReport(
        schema=COMPARISON_REPORT_SCHEMA,
        report_sha256=sha256_bytes(canonical_json_bytes(semantic)),
        pair_id=authority.pair_id,
        pair_sha256=authority.pair_sha256,
        breakdowns=tuple(breakdowns),
        exhaustive=True,
        pre_return=True,
        outcome_access=False,
    )


def build_production_input_comparison_report(
    authority: ProductionEvidenceAuthority,
) -> ProductionInputComparisonReport:
    """Build the exhaustive current-versus-censored pre-return report."""
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    require_production_evidence_authority(authority)
    return _build_comparison_report(authority)


def build_production_input_batch(
    authority: ProductionEvidenceAuthority,
    *,
    signal_arm: SignalArm,
) -> ProductionInputBatch:
    """Build one arm's exhaustive, immutable, pre-outcome admission census."""
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    require_production_evidence_authority(authority)
    if type(signal_arm) is not SignalArm:
        raise ProductionInputError("signal_arm must have exact type")
    admissions, directional_count = _derive_batch_parts(authority, signal_arm)
    comparison_report = _build_comparison_report(authority)
    semantic = _batch_semantic_record(
        authority=authority,
        arm=signal_arm,
        admissions=admissions,
        directional_candidate_count=directional_count,
        comparison_report=comparison_report,
    )
    digest = sha256_bytes(canonical_json_bytes(semantic))
    normalized = tuple(
        item.normalized_row for item in admissions if item.normalized_row is not None
    )
    values: dict[str, object] = {
        "schema": PRODUCTION_INPUT_BATCH_SCHEMA,
        "status": PRODUCTION_INPUT_STATUS,
        "contract_id": PRODUCTION_INPUT_CONTRACT_ID,
        "contract_sha256": PRODUCTION_INPUT_CONTRACT_SHA256,
        "batch_id": f"arv2-preoutcome-batch-{digest[:24]}",
        "batch_sha256": digest,
        "evidence_authority": authority,
        "evidence_authority_id": authority.authority_id,
        "evidence_authority_sha256": authority.authority_sha256,
        "pair_id": authority.pair_id,
        "pair_sha256": authority.pair_sha256,
        "signal_arm": signal_arm,
        "source_view": _ARM_TO_VIEW[signal_arm],
        "source_view_label": _ARM_TO_LABEL[signal_arm],
        "non_pristine_disclosure": NON_PRISTINE_DISCLOSURE,
        "total_source_row_count": len(authority.pair.rows),
        "source_view_included_count": semantic["source_view_included_count"],
        "directional_candidate_count": directional_count,
        "normalized_row_count": len(normalized),
        "refused_directional_count": directional_count - len(normalized),
        "admissions": admissions,
        "normalized_rows": normalized,
        "comparison_report": comparison_report,
        "exhaustive_source_census": True,
        "source_role_separate_from_signal_arm": True,
        "event_level_only": True,
        "decision_date_cross_sections_required": True,
        "decision_date_cross_sections_bound": False,
        "pristine_point_in_time": False,
        "earlier_version_imputation_performed": False,
        "production_input_authority": False,
        "formal_backtest_input_ready": False,
        "production_registry_receipt": None,
        "production_truth_approval": None,
        "outcome_authority": None,
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
    batch = object.__new__(ProductionInputBatch)
    for name, value in values.items():
        object.__setattr__(batch, name, value)
    identity = id(batch)
    reference = weakref.ref(batch, lambda ref, key=identity: _forget_batch(key, ref))
    with _BATCH_AUTHORITIES_LOCK:
        _BATCH_AUTHORITIES[identity] = (reference, _batch_fingerprint(batch))
    return require_production_input_batch(batch)


def require_production_input_batch(batch: ProductionInputBatch) -> ProductionInputBatch:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _require_static_contract()
    if type(batch) is not ProductionInputBatch:
        raise ProductionInputError("batch authority requires the exact built type")
    with _BATCH_AUTHORITIES_LOCK:
        registered = _BATCH_AUTHORITIES.get(id(batch))
    if registered is None or registered[0]() is not batch:
        raise ProductionInputError("batch is not builder-authenticated")
    if type(batch.evidence_authority) is not ProductionEvidenceAuthority:
        raise ProductionInputError("batch evidence authority has wrong type")
    _validate_batch_surface(batch)
    require_production_evidence_authority(batch.evidence_authority)
    if type(batch.admissions) is not tuple or any(
        type(item) is not RowAdmission for item in batch.admissions
    ):
        raise ProductionInputError("batch admissions must be an exact typed tuple")
    for item in batch.admissions:
        item.__post_init__()
        if item.normalized_row is not None:
            item.normalized_row.__post_init__()
    if type(batch.normalized_rows) is not tuple or any(
        type(item) is not NormalizedPreOutcomeRow for item in batch.normalized_rows
    ):
        raise ProductionInputError("batch normalized rows must be an exact typed tuple")
    for item in batch.normalized_rows:
        item.__post_init__()
    if _batch_fingerprint(batch) != registered[1]:
        raise ProductionInputError("batch changed after authentication")
    expected_admissions, directional_count = _derive_batch_parts(
        batch.evidence_authority, batch.signal_arm
    )
    expected_comparison = _build_comparison_report(batch.evidence_authority)
    expected_semantic = _batch_semantic_record(
        authority=batch.evidence_authority,
        arm=batch.signal_arm,
        admissions=expected_admissions,
        directional_candidate_count=directional_count,
        comparison_report=expected_comparison,
    )
    digest = sha256_bytes(canonical_json_bytes(expected_semantic))
    expected_normalized = tuple(
        item.normalized_row
        for item in expected_admissions
        if item.normalized_row is not None
    )
    scalar_expectations = {
        "schema": PRODUCTION_INPUT_BATCH_SCHEMA,
        "status": PRODUCTION_INPUT_STATUS,
        "contract_id": PRODUCTION_INPUT_CONTRACT_ID,
        "contract_sha256": PRODUCTION_INPUT_CONTRACT_SHA256,
        "batch_id": f"arv2-preoutcome-batch-{digest[:24]}",
        "batch_sha256": digest,
        "evidence_authority_id": batch.evidence_authority.authority_id,
        "evidence_authority_sha256": batch.evidence_authority.authority_sha256,
        "pair_id": batch.evidence_authority.pair_id,
        "pair_sha256": batch.evidence_authority.pair_sha256,
        "source_view": _ARM_TO_VIEW[batch.signal_arm],
        "source_view_label": _ARM_TO_LABEL[batch.signal_arm],
        "non_pristine_disclosure": NON_PRISTINE_DISCLOSURE,
        "total_source_row_count": len(batch.evidence_authority.pair.rows),
        "source_view_included_count": expected_semantic["source_view_included_count"],
        "directional_candidate_count": directional_count,
        "normalized_row_count": len(expected_normalized),
        "refused_directional_count": directional_count - len(expected_normalized),
    }
    if any(getattr(batch, name) != value for name, value in scalar_expectations.items()):
        raise ProductionInputError("batch scalar or identity binding is not exact")
    if (
        batch.admissions != expected_admissions
        or batch.normalized_rows != expected_normalized
        or batch.comparison_report != expected_comparison
    ):
        raise ProductionInputError("batch rows are not exactly source-derived")
    if tuple(item.source_locator for item in batch.admissions) != tuple(
        row.locator for row in batch.evidence_authority.pair.rows
    ):
        raise ProductionInputError("batch source census is missing, duplicated, or reordered")
    return batch


def _current_local_callables() -> tuple[object, ...]:
    """Return every local callable that can affect C2 authority semantics."""
    return (
        _exact_decimal,
        _decimal_text,
        _fraction_record,
        _require_exact_strings,
        _require_optional_exact_string,
        _validate_interval,
        _contains_visible_interval,
        EvidenceSourceBinding.__post_init__,
        EvidenceSourceBinding.to_record,
        SecurityIdentityEvidence.__post_init__,
        SecurityIdentityEvidence.to_record,
        FirmOntologyEvidence.__post_init__,
        FirmOntologyEvidence.to_record,
        CommonEventIdentityEvidence.__post_init__,
        CommonEventIdentityEvidence.to_record,
        SectorClassificationEvidence.__post_init__,
        SectorClassificationEvidence.to_record,
        PreopenControlEvidence.__post_init__,
        PreopenControlEvidence.to_record,
        DataQualityEvidence.__post_init__,
        DataQualityEvidence.to_record,
        ProductionRowEvidence.__post_init__,
        ProductionRowEvidence.to_record,
        production_input_contract_record,
        render_production_input_contract_bytes,
        _source_map,
        _authority_semantic_record,
        _authority_fingerprint,
        _forget_evidence_authority,
        _validate_authority_surface,
        _validate_sources,
        _remember_consistent_fact,
        _validate_row_evidence_topology,
        _validate_component_source_bindings,
        build_production_evidence_authority,
        require_production_evidence_authority,
        _require_static_contract,
        _RatingRowRefusal.__init__,
        _required_identifier_value,
        _required_text_value,
        _optional_text_value,
        _rating_action_is_missing,
        _validate_optional_rating_values,
        _normalize_provider_timestamp,
        _potential_directional_action,
        _parse_rating_row,
        NormalizedPreOutcomeRow.__post_init__,
        NormalizedPreOutcomeRow.semantic_record,
        NormalizedPreOutcomeRow.to_record,
        RowAdmission.__post_init__,
        RowAdmission.semantic_record,
        RowAdmission.derived_sha256.fget,
        RowAdmission.to_record,
        _row_evidence_sha256,
        _row_admission,
        _normalized_row,
        _at_or_after_cutoff,
        _admit_directional_rating,
        _admit_source_row,
        ComparisonRate.__post_init__,
        ComparisonRate.fraction.fget,
        ComparisonRate.to_record,
        ArmComparisonBreakdown.__post_init__,
        ArmComparisonBreakdown.to_record,
        ProductionInputComparisonReport.__post_init__,
        ProductionInputComparisonReport.semantic_record,
        ProductionInputComparisonReport.to_record,
        ProductionInputBatch.all_directional_rows_admitted.fget,
        _batch_semantic_record,
        _batch_fingerprint,
        _forget_batch,
        _validate_batch_surface,
        _derive_batch_parts,
        _mapping_signature,
        _signal_signature,
        _comparison_dimension_key,
        _comparison_breakdown,
        _build_comparison_report,
        build_production_input_comparison_report,
        build_production_input_batch,
        require_production_input_batch,
    )


def _current_record_types() -> tuple[type[object], ...]:
    return (
        SignalArm,
        EvidenceSourceKind,
        AdmissionDisposition,
        ComparisonDimension,
        EvidenceSourceBinding,
        SecurityIdentityEvidence,
        FirmOntologyEvidence,
        CommonEventIdentityEvidence,
        SectorClassificationEvidence,
        PreopenControlEvidence,
        DataQualityEvidence,
        ProductionRowEvidence,
        ProductionEvidenceAuthority,
        _ParsedRatingRow,
        _RatingRowRefusal,
        NormalizedPreOutcomeRow,
        RowAdmission,
        ComparisonRate,
        ArmComparisonBreakdown,
        ProductionInputComparisonReport,
        ProductionInputBatch,
    )


_PINNED_CURRENT_LOCAL_CALLABLES = _current_local_callables
_PINNED_LOCAL_CALLABLES = _current_local_callables()
_PINNED_CURRENT_RECORD_TYPES = _current_record_types
_PINNED_RECORD_TYPES = _current_record_types()


__all__ = [
    "AdmissionDisposition",
    "ArmComparisonBreakdown",
    "ComparisonDimension",
    "ComparisonRate",
    "CommonEventIdentityEvidence",
    "DataQualityEvidence",
    "EvidenceSourceBinding",
    "EvidenceSourceKind",
    "FirmOntologyEvidence",
    "NON_PRISTINE_DISCLOSURE",
    "NormalizedPreOutcomeRow",
    "PRODUCTION_EVIDENCE_SCHEMA",
    "PRODUCTION_INPUT_BATCH_SCHEMA",
    "PRODUCTION_INPUT_CONTRACT_ID",
    "PRODUCTION_INPUT_CONTRACT_SCHEMA",
    "PRODUCTION_INPUT_CONTRACT_SHA256",
    "PRODUCTION_INPUT_STATUS",
    "PreopenControlEvidence",
    "ProductionEvidenceAuthority",
    "ProductionInputBatch",
    "ProductionInputComparisonReport",
    "ProductionInputError",
    "ProductionRowEvidence",
    "RowAdmission",
    "SectorClassificationEvidence",
    "SecurityIdentityEvidence",
    "SignalArm",
    "build_production_evidence_authority",
    "build_production_input_batch",
    "build_production_input_comparison_report",
    "production_input_contract_record",
    "render_production_input_contract_bytes",
    "require_production_evidence_authority",
    "require_production_input_batch",
]
