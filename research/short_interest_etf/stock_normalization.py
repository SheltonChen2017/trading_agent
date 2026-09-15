"""Exact, outcome-free SI-3C stock normalization for Short Interest.

This module implements only blueprint equations 4.8, 4.9, 4.11, and 4.12
under the separately owner-frozen ``si-stock-normalization-policy-v1``.  It
consumes the complete authenticated SI-3A disposition inventory, fixes one
decision at the official release's next XNYS open, and retains every source
event as two terminal model outcomes.  It does not rank or select stocks,
read prices or outcomes, aggregate ETFs, or touch QuantConnect.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from fractions import Fraction
from typing import Any

from data.hashing import hash_payload
from research.short_interest_etf.availability import release_execution_cohort
from research.short_interest_etf.contracts import (
    DenominatorKind,
    ReleaseCalendarEntry,
    ShortInterestContractError,
    _canonical_date,
    _required_text,
    _sha256,
    parse_utc_timestamp,
)
from research.short_interest_etf.pit_eligibility import (
    SectorClassificationObservation,
)
from research.short_interest_etf.preregistration import PREREGISTRATION
from research.short_interest_etf.stock_features import (
    ExactRational,
    PitStockRawFeature,
    StockFeatureDisposition,
    StockFeatureSourceContext,
)


NORMALIZATION_POLICY_ID = "si-stock-normalization-policy-v1"
NORMALIZATION_POLICY_SCHEMA_VERSION = "1.0"
NORMALIZATION_COHORT_SCHEMA_VERSION = "1.0"
NORMALIZATION_OUTCOME_SCHEMA_VERSION = "1.0"
NORMALIZATION_DISPOSITION_SCHEMA_VERSION = "1.0"
STRUCTURAL_SCORE_AUTHORITY = "synthetic_structural_score_only"

REFUSAL_NOT_VISIBLE_AT_RELEASE_CUTOFF = "not_visible_at_release_cutoff"
REFUSAL_SUPERSEDED_AT_RELEASE_CUTOFF = "superseded_at_release_cutoff"
REFUSAL_NON_US_SECURITY = "non_us_security"
REFUSAL_NON_COMMON_STOCK_SECURITY = "non_common_stock_security"
REFUSAL_MIXED_TAXONOMY_LINEAGE = "mixed_taxonomy_lineage"
REFUSAL_INSUFFICIENT_SECTOR_PEERS = "insufficient_sector_peers"
REFUSAL_ZERO_SECTOR_MAD = "zero_sector_mad"


class StockNormalizationError(ValueError):
    """The frozen SI-3C contract or complete-batch invariant failed."""


def _refuse(detail: str) -> StockNormalizationError:
    return StockNormalizationError(f"REFUSED: {detail}")


def _checked_required(value: Any, name: str) -> str:
    try:
        return _required_text(value, name)
    except (ShortInterestContractError, TypeError, ValueError) as exc:
        raise _refuse(f"invalid {name}: {exc}") from exc


def _checked_sha256(value: Any, name: str) -> str:
    try:
        return _sha256(value, name)
    except (ShortInterestContractError, TypeError, ValueError) as exc:
        raise _refuse(f"invalid {name}: {exc}") from exc


def _checked_date(value: Any, name: str):
    try:
        return _canonical_date(value, name)
    except (ShortInterestContractError, TypeError, ValueError) as exc:
        raise _refuse(f"invalid {name}: {exc}") from exc


def _checked_timestamp(value: Any, name: str):
    try:
        return parse_utc_timestamp(value, name)
    except (ShortInterestContractError, TypeError, ValueError) as exc:
        raise _refuse(f"invalid {name}: {exc}") from exc


def _checked_reasons(value: Any, name: str) -> tuple[str, ...]:
    if type(value) is not tuple or not all(
        type(item) is str and item and item == item.strip() for item in value
    ):
        raise _refuse(f"{name} must be an exact tuple of canonical strings")
    if value != tuple(sorted(set(value))):
        raise _refuse(f"{name} must be unique and sorted")
    return value


def _rational(value: Fraction) -> ExactRational:
    return ExactRational.from_fraction(value)


def _checked_rational(value: Any, name: str) -> ExactRational:
    if type(value) is not ExactRational:
        raise _refuse(f"{name} must be the exact ExactRational type")
    try:
        value.__post_init__()
    except (TypeError, ValueError) as exc:
        raise _refuse(f"{name} is not canonical: {exc}") from exc
    return value


def _type7_quantile(values: tuple[Fraction, ...], probability: Fraction) -> Fraction:
    """Hyndman-Fan Type 7 with exact interpolation and no float conversion."""
    if type(values) is not tuple or not values:
        raise _refuse("Type-7 quantile requires a nonempty exact tuple")
    if not all(type(value) is Fraction for value in values):
        raise _refuse("Type-7 quantile values must be exact Fractions")
    if type(probability) is not Fraction or not 0 <= probability <= 1:
        raise _refuse("Type-7 probability must be an exact Fraction in [0, 1]")
    ordered = tuple(sorted(values))
    h = Fraction(len(ordered) - 1) * probability
    lower_index = h.numerator // h.denominator
    weight = h - lower_index
    upper_index = min(lower_index + 1, len(ordered) - 1)
    return ordered[lower_index] + weight * (
        ordered[upper_index] - ordered[lower_index]
    )


def _median(values: tuple[Fraction, ...]) -> Fraction:
    return _type7_quantile(values, Fraction(1, 2))


def _clip(value: Fraction, lower: Fraction, upper: Fraction) -> Fraction:
    if lower > upper:
        raise _refuse("winsor lower bound exceeds upper bound")
    return max(lower, min(value, upper))


class StockScoreModel(str, Enum):
    S0_LEVEL = "S0_level"
    S1_DELTA = "S1_delta"


class RevisionSelectionState(str, Enum):
    SELECTED = "selected_at_release_cutoff"
    SUPERSEDED = REFUSAL_SUPERSEDED_AT_RELEASE_CUTOFF
    NOT_VISIBLE = REFUSAL_NOT_VISIBLE_AT_RELEASE_CUTOFF


@dataclasses.dataclass(frozen=True)
class StockNormalizationPolicy:
    """Non-configurable owner freeze layered over the existing preregistration."""

    policy_id: str = dataclasses.field(default=NORMALIZATION_POLICY_ID, init=False)
    preregistration_sha256: str = dataclasses.field(
        default=PREREGISTRATION.sha256, init=False
    )
    models: tuple[StockScoreModel, ...] = dataclasses.field(
        default=(StockScoreModel.S0_LEVEL, StockScoreModel.S1_DELTA), init=False
    )
    ratio_unit: str = dataclasses.field(
        default="fraction_of_one_1_equals_100_percent", init=False
    )
    epsilon: ExactRational = dataclasses.field(
        default_factory=lambda: ExactRational(0, 1), init=False
    )
    winsor_lower_probability: ExactRational = dataclasses.field(
        default_factory=lambda: ExactRational(1, 100), init=False
    )
    winsor_upper_probability: ExactRational = dataclasses.field(
        default_factory=lambda: ExactRational(99, 100), init=False
    )
    minimum_sector_peers: int = dataclasses.field(default=20, init=False)
    mad_scale: ExactRational = dataclasses.field(
        default_factory=lambda: ExactRational(7413, 5000), init=False
    )
    schema_version: str = dataclasses.field(
        default=NORMALIZATION_POLICY_SCHEMA_VERSION, init=False
    )

    def __post_init__(self) -> None:
        if (
            type(self.models) is not tuple
            or not all(type(item) is StockScoreModel for item in self.models)
            or self.models
            != (StockScoreModel.S0_LEVEL, StockScoreModel.S1_DELTA)
        ):
            raise _refuse("normalization policy models are not the frozen S0/S1 pair")
        for name in (
            "epsilon",
            "winsor_lower_probability",
            "winsor_upper_probability",
            "mad_scale",
        ):
            _checked_rational(getattr(self, name), f"normalization policy {name}")
        if type(self.epsilon) is not ExactRational or self.epsilon != ExactRational(0, 1):
            raise _refuse("normalization epsilon must be exact zero")
        if (
            type(self.winsor_lower_probability) is not ExactRational
            or self.winsor_lower_probability != ExactRational(1, 100)
            or type(self.winsor_upper_probability) is not ExactRational
            or self.winsor_upper_probability != ExactRational(99, 100)
        ):
            raise _refuse("winsor probabilities must be the frozen p01/p99 pair")
        if type(self.minimum_sector_peers) is not int or self.minimum_sector_peers != 20:
            raise _refuse("minimum sector peers must be the frozen exact integer 20")
        if type(self.mad_scale) is not ExactRational or self.mad_scale != ExactRational(7413, 5000):
            raise _refuse("MAD scale must be exact 1.4826")
        if self.preregistration_sha256 != PREREGISTRATION.sha256:
            raise _refuse("normalization policy is not bound to PREREGISTRATION")
        if (
            type(self.schema_version) is not str
            or self.schema_version != NORMALIZATION_POLICY_SCHEMA_VERSION
        ):
            raise _refuse("unsupported normalization policy schema_version")

    def to_payload(self) -> dict[str, Any]:
        return {
            "authority": STRUCTURAL_SCORE_AUTHORITY,
            "canonical_denominator": DenominatorKind.POINT_IN_TIME_SHARES_OUTSTANDING.value,
            "cohort": "shared_S1_complete_release_cutoff_cohort_for_S0_and_S1",
            "decision_cutoff": "official_release_next_XNYS_open_once_per_cycle",
            "epsilon": self.epsilon.to_payload(),
            "late_correction_action": "retain_without_retroactive_rescore",
            "mad": "exact_median_absolute_deviation_after_input_clipping",
            "mad_scale": self.mad_scale.to_payload(),
            "minimum_sector_peers": self.minimum_sector_peers,
            "models": [item.value for item in self.models],
            "normalization_slot_identity": (
                "one_selected_result_per_policy_release_security_model"
            ),
            "peer_identity": "unique_stable_security_id_subject_included",
            "policy_id": self.policy_id,
            "post_score_clip": None,
            "preregistration_sha256": self.preregistration_sha256,
            "production_authoritative": False,
            "quantile_interpolation": "Hyndman_Fan_type_7_exact",
            "ratio_cap": None,
            "ratio_unit": self.ratio_unit,
            "revision_selection": (
                "latest_complete_execution_visible_revision_by_logical_id_at_cutoff"
            ),
            "schema_version": self.schema_version,
            "sector_fallback": None,
            "share_class_policy": (
                "each_stable_security_id_separately_no_issuer_aggregation"
            ),
            "taxonomy_rule": (
                "one_exact_taxonomy_id_source_id_source_version_per_release_cycle"
            ),
            "universe_country": "US",
            "universe_security_type": "COMMON_STOCK",
            "winsor_bounds_by_model": True,
            "winsor_lower_probability": self.winsor_lower_probability.to_payload(),
            "winsor_reference": "release_wide_union_of_minimum_peer_eligible_sectors",
            "winsor_upper_probability": self.winsor_upper_probability.to_payload(),
            "zero_mad_action": "refuse_complete_model_sector_cohort",
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


STOCK_NORMALIZATION_POLICY = StockNormalizationPolicy()


def require_stock_normalization_policy(
    policy: StockNormalizationPolicy,
) -> StockNormalizationPolicy:
    if type(policy) is not StockNormalizationPolicy:
        raise _refuse("policy must be the exact StockNormalizationPolicy type")
    canonical = StockNormalizationPolicy()
    policy.__post_init__()
    for field in dataclasses.fields(canonical):
        if type(getattr(policy, field.name)) is not type(
            getattr(canonical, field.name)
        ):
            raise _refuse(
                f"policy.{field.name} does not have the frozen exact field type"
            )
    if policy.to_payload() != canonical.to_payload() or policy.sha256 != canonical.sha256:
        raise _refuse("policy does not match the owner-frozen SI-3C policy")
    return policy


@dataclasses.dataclass(frozen=True)
class StockNormalizationMember:
    security_id: str
    event_id: str
    logical_id: str
    prior_event_id: str
    supersedes_event_id: str | None
    raw_feature_sha256: str
    raw_disposition_sha256: str
    readiness_sha256: str
    security_identity_sha256: str
    classification_record_id: str
    taxonomy_id: str
    taxonomy_source_id: str
    taxonomy_source_version: str
    sector_code: str
    ticker: str
    share_class: str
    s0_value: ExactRational
    s1_value: ExactRational

    def __post_init__(self) -> None:
        for name in (
            "security_id",
            "taxonomy_id",
            "taxonomy_source_id",
            "taxonomy_source_version",
            "sector_code",
            "ticker",
            "share_class",
        ):
            _checked_required(getattr(self, name), f"member.{name}")
        for name in (
            "event_id",
            "logical_id",
            "prior_event_id",
            "raw_feature_sha256",
            "raw_disposition_sha256",
            "readiness_sha256",
            "security_identity_sha256",
            "classification_record_id",
        ):
            _checked_sha256(getattr(self, name), f"member.{name}")
        if self.supersedes_event_id is not None:
            _checked_sha256(self.supersedes_event_id, "member.supersedes_event_id")
        for name in ("taxonomy_id", "sector_code", "ticker"):
            if getattr(self, name) != getattr(self, name).upper():
                raise _refuse(f"member.{name} must be canonical uppercase")
        _checked_rational(self.s0_value, "member.s0_value")
        _checked_rational(self.s1_value, "member.s1_value")

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.security_id, self.event_id)

    @property
    def taxonomy_lineage(self) -> tuple[str, str, str]:
        return (
            self.taxonomy_id,
            self.taxonomy_source_id,
            self.taxonomy_source_version,
        )

    def model_value(self, model: StockScoreModel) -> ExactRational:
        if model is StockScoreModel.S0_LEVEL:
            return self.s0_value
        if model is StockScoreModel.S1_DELTA:
            return self.s1_value
        raise _refuse("unknown stock score model")

    def to_payload(self) -> dict[str, Any]:
        return {
            "classification_record_id": self.classification_record_id,
            "event_id": self.event_id,
            "logical_id": self.logical_id,
            "prior_event_id": self.prior_event_id,
            "raw_disposition_sha256": self.raw_disposition_sha256,
            "raw_feature_sha256": self.raw_feature_sha256,
            "readiness_sha256": self.readiness_sha256,
            "s0_value": self.s0_value.to_payload(),
            "s1_value": self.s1_value.to_payload(),
            "sector_code": self.sector_code,
            "security_id": self.security_id,
            "security_identity_sha256": self.security_identity_sha256,
            "share_class": self.share_class,
            "supersedes_event_id": self.supersedes_event_id,
            "taxonomy_id": self.taxonomy_id,
            "taxonomy_source_id": self.taxonomy_source_id,
            "taxonomy_source_version": self.taxonomy_source_version,
            "ticker": self.ticker,
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def _members_digest(members: tuple[StockNormalizationMember, ...]) -> str:
    return hash_payload([item.to_payload() for item in members])


@dataclasses.dataclass(frozen=True)
class StockWinsorBounds:
    model: StockScoreModel
    lower: ExactRational
    upper: ExactRational
    reference_count: int
    reference_members_sha256: str

    def __post_init__(self) -> None:
        if type(self.model) is not StockScoreModel:
            raise _refuse("winsor model must be the exact StockScoreModel type")
        _checked_rational(self.lower, "winsor.lower")
        _checked_rational(self.upper, "winsor.upper")
        if self.lower.to_fraction() > self.upper.to_fraction():
            raise _refuse("winsor lower bound exceeds upper bound")
        if type(self.reference_count) is not int or self.reference_count <= 0:
            raise _refuse("winsor reference_count must be a positive exact integer")
        _checked_sha256(
            self.reference_members_sha256,
            "winsor.reference_members_sha256",
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "lower": self.lower.to_payload(),
            "model": self.model.value,
            "reference_count": self.reference_count,
            "reference_members_sha256": self.reference_members_sha256,
            "upper": self.upper.to_payload(),
        }


@dataclasses.dataclass(frozen=True)
class StockNormalizationCohort:
    source_dataset_id: str
    source_vintage_sha256: str
    reference_dataset_id: str
    reference_bundle_sha256: str
    source_context_sha256: str
    preregistration_sha256: str
    normalization_policy_sha256: str
    release: ReleaseCalendarEntry
    settlement_date: str
    decision_session: str
    decision_at: str
    raw_dispositions: tuple[StockFeatureDisposition, ...]
    candidate_members: tuple[StockNormalizationMember, ...] = dataclasses.field(
        init=False
    )
    eligible_members: tuple[StockNormalizationMember, ...] = dataclasses.field(
        init=False
    )
    winsor_bounds: tuple[StockWinsorBounds, ...] = dataclasses.field(init=False)
    _selection_records: tuple[
        tuple[str, RevisionSelectionState, str | None], ...
    ] = dataclasses.field(init=False, repr=False, compare=False)
    _sha256_cache: str = dataclasses.field(init=False, repr=False, compare=False)
    schema_version: str = NORMALIZATION_COHORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("source_dataset_id", "reference_dataset_id"):
            _checked_required(getattr(self, name), f"cohort.{name}")
        for name in (
            "source_vintage_sha256",
            "reference_bundle_sha256",
            "source_context_sha256",
            "preregistration_sha256",
            "normalization_policy_sha256",
        ):
            _checked_sha256(getattr(self, name), f"cohort.{name}")
        if self.preregistration_sha256 != PREREGISTRATION.sha256:
            raise _refuse("cohort is not bound to PREREGISTRATION")
        if self.normalization_policy_sha256 != STOCK_NORMALIZATION_POLICY.sha256:
            raise _refuse("cohort is not bound to the frozen normalization policy")
        if type(self.release) is not ReleaseCalendarEntry:
            raise _refuse("cohort release must be the exact ReleaseCalendarEntry type")
        if self.settlement_date != self.release.settlement_date:
            raise _refuse("cohort settlement_date does not match release evidence")
        _checked_date(self.settlement_date, "cohort.settlement_date")
        _checked_date(self.decision_session, "cohort.decision_session")
        _checked_timestamp(self.decision_at, "cohort.decision_at")
        expected_decision = release_execution_cohort(self.release)
        if (
            self.decision_session != expected_decision.session
            or self.decision_at != expected_decision.opens_at
        ):
            raise _refuse("cohort decision is not the official-release next XNYS open")

        (
            source_context,
            canonical_raw,
            selection_records,
            candidate_members,
        ) = _derive_release_selection(self.raw_dispositions, self.release)
        first_readiness = canonical_raw[0].readiness
        expected_context = {
            "source_dataset_id": first_readiness.source_dataset_id,
            "source_vintage_sha256": first_readiness.source_vintage_sha256,
            "reference_dataset_id": first_readiness.reference_dataset_id,
            "reference_bundle_sha256": first_readiness.reference_bundle_sha256,
            "source_context_sha256": source_context.sha256,
        }
        for name, value in expected_context.items():
            if getattr(self, name) != value:
                raise _refuse(f"cohort.{name} does not match raw disposition inventory")
        object.__setattr__(self, "raw_dispositions", canonical_raw)
        object.__setattr__(self, "_selection_records", selection_records)
        object.__setattr__(self, "candidate_members", candidate_members)

        candidate_ids = [item.security_id for item in candidate_members]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise _refuse("cohort candidates contain duplicate stable security_id")

        lineages = {item.taxonomy_lineage for item in candidate_members}
        expected_eligible: tuple[StockNormalizationMember, ...] = ()
        if len(lineages) == 1:
            counts: dict[str, int] = {}
            for item in candidate_members:
                counts[item.sector_code] = counts.get(item.sector_code, 0) + 1
            expected_eligible = tuple(
                item
                for item in candidate_members
                if counts[item.sector_code]
                >= STOCK_NORMALIZATION_POLICY.minimum_sector_peers
            )
        object.__setattr__(self, "eligible_members", expected_eligible)
        object.__setattr__(self, "winsor_bounds", _build_bounds(expected_eligible))
        if (
            type(self.schema_version) is not str
            or self.schema_version != NORMALIZATION_COHORT_SCHEMA_VERSION
        ):
            raise _refuse("unsupported normalization cohort schema_version")
        object.__setattr__(self, "_sha256_cache", hash_payload(self.to_payload()))

    @property
    def release_calendar_key(self) -> str:
        return self.release.key

    @property
    def release_sha256(self) -> str:
        return hash_payload(self.release.to_payload())

    @property
    def candidate_members_sha256(self) -> str:
        return _members_digest(self.candidate_members)

    @property
    def eligible_members_sha256(self) -> str:
        return _members_digest(self.eligible_members)

    @property
    def raw_disposition_inventory(self) -> tuple[dict[str, str], ...]:
        return tuple(
            {
                "event_id": item.readiness.event_id,
                "sha256": item.sha256,
            }
            for item in self.raw_dispositions
        )

    @property
    def raw_dispositions_sha256(self) -> str:
        return hash_payload(list(self.raw_disposition_inventory))

    @property
    def taxonomy_lineages(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(sorted({item.taxonomy_lineage for item in self.candidate_members}))

    def bounds_for(self, model: StockScoreModel) -> StockWinsorBounds | None:
        return next((item for item in self.winsor_bounds if item.model is model), None)

    def raw_disposition_for_event(
        self, event_id: str
    ) -> StockFeatureDisposition | None:
        return next(
            (
                item
                for item in self.raw_dispositions
                if item.readiness.event_id == event_id
            ),
            None,
        )

    def selection_for_event(
        self, event_id: str
    ) -> tuple[RevisionSelectionState, str | None] | None:
        return next(
            (
                (state, selected_event_id)
                for candidate_event_id, state, selected_event_id in self._selection_records
                if candidate_event_id == event_id
            ),
            None,
        )

    def member_for_event(self, event_id: str) -> StockNormalizationMember | None:
        return next(
            (item for item in self.candidate_members if item.event_id == event_id),
            None,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_members": [item.to_payload() for item in self.candidate_members],
            "candidate_members_sha256": self.candidate_members_sha256,
            "decision_at": self.decision_at,
            "decision_session": self.decision_session,
            "eligible_members": [item.to_payload() for item in self.eligible_members],
            "eligible_members_sha256": self.eligible_members_sha256,
            "normalization_policy_sha256": self.normalization_policy_sha256,
            "preregistration_sha256": self.preregistration_sha256,
            "reference_bundle_sha256": self.reference_bundle_sha256,
            "reference_dataset_id": self.reference_dataset_id,
            "raw_disposition_inventory": list(self.raw_disposition_inventory),
            "raw_dispositions_sha256": self.raw_dispositions_sha256,
            "release": self.release.to_payload(),
            "release_calendar_key": self.release_calendar_key,
            "release_sha256": self.release_sha256,
            "schema_version": self.schema_version,
            "settlement_date": self.settlement_date,
            "source_context_sha256": self.source_context_sha256,
            "source_dataset_id": self.source_dataset_id,
            "source_vintage_sha256": self.source_vintage_sha256,
            "taxonomy_lineages": [
                {
                    "taxonomy_id": item[0],
                    "source_id": item[1],
                    "source_version": item[2],
                }
                for item in self.taxonomy_lineages
            ],
            "winsor_bounds": [item.to_payload() for item in self.winsor_bounds],
        }

    @property
    def sha256(self) -> str:
        return self._sha256_cache


@dataclasses.dataclass(frozen=True)
class StockModelOutcome:
    model: StockScoreModel
    security_id: str
    event_id: str
    selected_event_id: str | None
    revision_selection_state: RevisionSelectionState
    raw_disposition_sha256: str
    raw_feature_sha256: str | None
    normalization_policy_sha256: str
    cohort: StockNormalizationCohort
    raw_value: ExactRational | None
    sector_code: str | None
    sector_members: tuple[StockNormalizationMember, ...]
    winsor_lower: ExactRational | None
    winsor_upper: ExactRational | None
    winsorized_value: ExactRational | None
    sector_median: ExactRational | None
    sector_mad: ExactRational | None
    scaled_mad: ExactRational | None
    score: ExactRational | None
    refusal_reasons: tuple[str, ...]
    schema_version: str = NORMALIZATION_OUTCOME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.model) is not StockScoreModel:
            raise _refuse("outcome model must be the exact StockScoreModel type")
        if type(self.revision_selection_state) is not RevisionSelectionState:
            raise _refuse("outcome revision state must be exact")
        if type(self.cohort) is not StockNormalizationCohort:
            raise _refuse("outcome cohort must be the exact StockNormalizationCohort type")
        _checked_required(self.security_id, "outcome.security_id")
        for name in (
            "event_id",
            "raw_disposition_sha256",
            "normalization_policy_sha256",
        ):
            _checked_sha256(getattr(self, name), f"outcome.{name}")
        if self.selected_event_id is not None:
            _checked_sha256(self.selected_event_id, "outcome.selected_event_id")
        if (
            self.revision_selection_state is RevisionSelectionState.SELECTED
            and self.selected_event_id != self.event_id
        ):
            raise _refuse("selected outcome must select its own event")
        if self.raw_feature_sha256 is not None:
            _checked_sha256(self.raw_feature_sha256, "outcome.raw_feature_sha256")
        if self.normalization_policy_sha256 != STOCK_NORMALIZATION_POLICY.sha256:
            raise _refuse("outcome is not bound to the frozen normalization policy")
        _checked_reasons(self.refusal_reasons, "outcome.refusal_reasons")
        if self.sector_code is not None:
            _checked_required(self.sector_code, "outcome.sector_code")
            if self.sector_code != self.sector_code.upper():
                raise _refuse("outcome.sector_code must be canonical uppercase")
        if type(self.sector_members) is not tuple or not all(
            type(item) is StockNormalizationMember for item in self.sector_members
        ):
            raise _refuse("outcome sector_members must be an exact tuple of members")
        if self.sector_members != tuple(
            sorted(self.sector_members, key=lambda item: item.sort_key)
        ):
            raise _refuse("outcome sector_members must be canonically sorted")
        if self.sector_members and (
            self.sector_code is None
            or any(item.sector_code != self.sector_code for item in self.sector_members)
        ):
            raise _refuse("outcome sector_members do not share sector_code")
        security_ids = [item.security_id for item in self.sector_members]
        if len(security_ids) != len(set(security_ids)):
            raise _refuse("outcome sector_members repeat a stable security_id")

        rational_fields = (
            "raw_value",
            "winsor_lower",
            "winsor_upper",
            "winsorized_value",
            "sector_median",
            "sector_mad",
            "scaled_mad",
            "score",
        )
        for name in rational_fields:
            value = getattr(self, name)
            if value is not None:
                _checked_rational(value, f"outcome.{name}")
        if self.raw_value is None:
            if self.raw_feature_sha256 is not None:
                raise _refuse("outcome without raw value cannot carry raw feature SHA")
            if any(getattr(self, name) is not None for name in rational_fields[1:]):
                raise _refuse("outcome without raw value cannot carry normalization values")
        elif self.raw_feature_sha256 is None:
            raise _refuse("outcome raw value requires raw feature SHA")
        if (self.winsor_lower is None) != (self.winsor_upper is None):
            raise _refuse("outcome winsor bounds must be both present or both absent")
        if self.winsor_lower is not None and (
            self.winsor_lower.to_fraction() > self.winsor_upper.to_fraction()
        ):
            raise _refuse("outcome winsor lower bound exceeds upper bound")
        statistic_fields = (
            self.winsorized_value,
            self.sector_median,
            self.sector_mad,
            self.scaled_mad,
        )
        has_statistics = all(item is not None for item in statistic_fields)
        if any(item is not None for item in statistic_fields) and not has_statistics:
            raise _refuse("outcome normalization statistics are incomplete")
        if self.score is not None and not has_statistics:
            raise _refuse("completed score requires complete normalization statistics")
        if has_statistics:
            if (
                self.raw_value is None
                or self.winsor_lower is None
                or self.winsor_upper is None
                or self.sector_code is None
                or not self.sector_members
            ):
                raise _refuse("normalization statistics lack exact input witnesses")
            targets = tuple(
                item
                for item in self.sector_members
                if item.event_id == self.event_id
            )
            if len(targets) != 1:
                raise _refuse("normalized outcome lacks one exact subject member")
            target_member = targets[0]
            if (
                target_member.security_id != self.security_id
                or target_member.raw_feature_sha256 != self.raw_feature_sha256
                or target_member.raw_disposition_sha256
                != self.raw_disposition_sha256
                or target_member.model_value(self.model) != self.raw_value
            ):
                raise _refuse("normalized subject witness does not match raw lineage")
            lower = self.winsor_lower.to_fraction()
            upper = self.winsor_upper.to_fraction()
            clipped = tuple(
                _clip(item.model_value(self.model).to_fraction(), lower, upper)
                for item in self.sector_members
            )
            target = _clip(self.raw_value.to_fraction(), lower, upper)
            median = _median(clipped)
            mad = _median(tuple(abs(value - median) for value in clipped))
            scale = mad * STOCK_NORMALIZATION_POLICY.mad_scale.to_fraction()
            expected_statistics = {
                "winsorized_value": _rational(target),
                "sector_median": _rational(median),
                "sector_mad": _rational(mad),
                "scaled_mad": _rational(scale),
            }
            for name, expected in expected_statistics.items():
                if getattr(self, name) != expected:
                    raise _refuse(
                        f"outcome.{name} does not match exact witness arithmetic"
                    )
            if mad == 0:
                if self.score is not None or self.refusal_reasons != (
                    REFUSAL_ZERO_SECTOR_MAD,
                ):
                    raise _refuse("zero-MAD outcome must refuse without epsilon")
            else:
                expected_score = _rational((target - median) / scale)
                if self.score != expected_score or self.refusal_reasons:
                    raise _refuse("normalized score does not match exact MAD equation")
        if self.score is not None and self.refusal_reasons:
            raise _refuse("completed score cannot carry refusal reasons")
        if self.score is None and not self.refusal_reasons:
            raise _refuse("missing score requires a named refusal")
        self._validate_authenticated_terminal_path(has_statistics)
        if (
            type(self.schema_version) is not str
            or self.schema_version != NORMALIZATION_OUTCOME_SCHEMA_VERSION
        ):
            raise _refuse("unsupported normalization outcome schema_version")

    def _validate_authenticated_terminal_path(self, has_statistics: bool) -> None:
        current = self.cohort.raw_disposition_for_event(self.event_id)
        if current is None or current.sha256 != self.raw_disposition_sha256:
            raise _refuse("outcome raw disposition is not in its authenticated cohort")
        if current.readiness.security_id != self.security_id:
            raise _refuse("outcome security_id does not match authenticated readiness")
        selection = self.cohort.selection_for_event(self.event_id)
        if selection != (self.revision_selection_state, self.selected_event_id):
            raise _refuse("outcome revision state does not match release cutoff")

        feature = current.feature
        if feature is None:
            if self.raw_feature_sha256 is not None or self.raw_value is not None:
                raise _refuse("upstream refusal outcome carries raw feature data")
        else:
            expected_raw = (
                feature.current_short_ratio
                if self.model is StockScoreModel.S0_LEVEL
                else feature.delta_short_ratio
            )
            if (
                self.raw_feature_sha256 != feature.sha256
                or self.raw_value != expected_raw
            ):
                raise _refuse("outcome raw value does not match authenticated feature")

        if self.revision_selection_state is not RevisionSelectionState.SELECTED:
            expected_reason = (
                REFUSAL_SUPERSEDED_AT_RELEASE_CUTOFF
                if self.revision_selection_state is RevisionSelectionState.SUPERSEDED
                else REFUSAL_NOT_VISIBLE_AT_RELEASE_CUTOFF
            )
            if self.refusal_reasons != (expected_reason,):
                raise _refuse("non-selected outcome has wrong terminal refusal")
            self._require_no_normalization_fields()
            return
        if feature is None:
            if self.refusal_reasons != current.refusal_reasons:
                raise _refuse("selected upstream refusal was not preserved")
            self._require_no_normalization_fields()
            return

        identity = feature.current_snapshot.security
        universe_reasons = tuple(
            sorted(
                reason
                for condition, reason in (
                    (identity.country != "US", REFUSAL_NON_US_SECURITY),
                    (
                        identity.security_type != "COMMON_STOCK",
                        REFUSAL_NON_COMMON_STOCK_SECURITY,
                    ),
                )
                if condition
            )
        )
        if universe_reasons:
            if self.refusal_reasons != universe_reasons:
                raise _refuse("universe-ineligible outcome has wrong refusal")
            self._require_no_normalization_fields()
            return

        member = self.cohort.member_for_event(self.event_id)
        if member is None:
            raise _refuse("selected universe-eligible outcome lacks cohort member")
        if len(self.cohort.taxonomy_lineages) != 1:
            if self.refusal_reasons != (REFUSAL_MIXED_TAXONOMY_LINEAGE,):
                raise _refuse("mixed-taxonomy outcome has wrong refusal")
            self._require_no_normalization_fields()
            return

        expected_members = tuple(
            item
            for item in self.cohort.candidate_members
            if item.sector_code == member.sector_code
        )
        bounds = self.cohort.bounds_for(self.model)
        expected_lower = bounds.lower if bounds is not None else None
        expected_upper = bounds.upper if bounds is not None else None
        if (
            self.sector_code != member.sector_code
            or self.sector_members != expected_members
            or self.winsor_lower != expected_lower
            or self.winsor_upper != expected_upper
        ):
            raise _refuse("outcome peer or winsor witness does not match cohort")
        if len(expected_members) < STOCK_NORMALIZATION_POLICY.minimum_sector_peers:
            if self.refusal_reasons != (REFUSAL_INSUFFICIENT_SECTOR_PEERS,):
                raise _refuse("underfilled outcome has wrong refusal")
            if has_statistics or self.score is not None:
                raise _refuse("underfilled outcome cannot carry statistics")
            return
        if not has_statistics:
            raise _refuse("eligible outcome lacks complete normalization statistics")

    def _require_no_normalization_fields(self) -> None:
        if self.sector_code is not None or self.sector_members:
            raise _refuse("non-normalized outcome carries sector witnesses")
        if any(
            value is not None
            for value in (
                self.winsor_lower,
                self.winsor_upper,
                self.winsorized_value,
                self.sector_median,
                self.sector_mad,
                self.scaled_mad,
                self.score,
            )
        ):
            raise _refuse("non-normalized outcome carries normalization values")

    @property
    def normalization_cohort_sha256(self) -> str:
        return self.cohort.sha256

    @property
    def normalization_slot_id(self) -> str:
        return hash_payload(
            {
                "authority": STRUCTURAL_SCORE_AUTHORITY,
                "model": self.model.value,
                "normalization_policy_sha256": self.normalization_policy_sha256,
                "release_sha256": self.cohort.release_sha256,
                "security_id": self.security_id,
            }
        )

    @property
    def sector_members_sha256(self) -> str:
        return _members_digest(self.sector_members)

    @property
    def peer_count(self) -> int:
        return len(self.sector_members)

    def to_payload(self) -> dict[str, Any]:
        def payload(value: ExactRational | None):
            return value.to_payload() if value is not None else None

        return {
            "authority": STRUCTURAL_SCORE_AUTHORITY,
            "event_id": self.event_id,
            "model": self.model.value,
            "normalization_cohort_sha256": self.normalization_cohort_sha256,
            "normalization_policy_sha256": self.normalization_policy_sha256,
            "normalization_slot_id": self.normalization_slot_id,
            "peer_count": self.peer_count,
            "production_authoritative": False,
            "raw_disposition_sha256": self.raw_disposition_sha256,
            "raw_feature_sha256": self.raw_feature_sha256,
            "raw_value": payload(self.raw_value),
            "refusal_reasons": list(self.refusal_reasons),
            "revision_selection_state": self.revision_selection_state.value,
            "schema_version": self.schema_version,
            "score": payload(self.score),
            "sector_code": self.sector_code,
            "sector_mad": payload(self.sector_mad),
            "sector_median": payload(self.sector_median),
            "sector_members": [item.to_payload() for item in self.sector_members],
            "sector_members_sha256": self.sector_members_sha256,
            "security_id": self.security_id,
            "selected_event_id": self.selected_event_id,
            "scaled_mad": payload(self.scaled_mad),
            "winsor_lower": payload(self.winsor_lower),
            "winsor_upper": payload(self.winsor_upper),
            "winsorized_value": payload(self.winsorized_value),
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


@dataclasses.dataclass(frozen=True)
class StockScoreDisposition:
    current: StockFeatureDisposition
    cohort: StockNormalizationCohort
    outcomes: tuple[StockModelOutcome, ...]
    schema_version: str = NORMALIZATION_DISPOSITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.current) is not StockFeatureDisposition:
            raise _refuse("current must be the exact StockFeatureDisposition type")
        if type(self.cohort) is not StockNormalizationCohort:
            raise _refuse("cohort must be the exact StockNormalizationCohort type")
        if type(self.outcomes) is not tuple or not all(
            type(item) is StockModelOutcome for item in self.outcomes
        ):
            raise _refuse("outcomes must be an exact tuple of exact model outcomes")
        if tuple(item.model for item in self.outcomes) != STOCK_NORMALIZATION_POLICY.models:
            raise _refuse("disposition must contain exactly S0 then S1")
        if (
            type(self.schema_version) is not str
            or self.schema_version != NORMALIZATION_DISPOSITION_SCHEMA_VERSION
        ):
            raise _refuse("unsupported score disposition schema_version")
        self._validate_lineage_and_results()

    def _validate_lineage_and_results(self) -> None:
        source_context = self.current.source_context
        if type(source_context) is not StockFeatureSourceContext:
            raise _refuse("score disposition lacks authenticated source_context")
        authenticated_current = self.cohort.raw_disposition_for_event(
            self.current.readiness.event_id
        )
        if (
            authenticated_current is None
            or authenticated_current != self.current
            or authenticated_current.sha256 != self.current.sha256
        ):
            raise _refuse(
                "current disposition is not the exact cohort raw-inventory event"
            )
        snapshot = source_context.snapshot_for_event(self.current.readiness.event_id)
        if snapshot is None:
            raise _refuse("score event is absent from authenticated source_context")
        release_by_key = {
            item.key: item for item in source_context.source_vintage.release_calendar
        }
        release = release_by_key.get(snapshot.release_calendar_key)
        if release is None or release != self.cohort.release:
            raise _refuse("score disposition cohort has wrong release evidence")
        readiness = self.current.readiness
        expected_context = {
            "source_dataset_id": readiness.source_dataset_id,
            "source_vintage_sha256": readiness.source_vintage_sha256,
            "reference_dataset_id": readiness.reference_dataset_id,
            "reference_bundle_sha256": readiness.reference_bundle_sha256,
            "source_context_sha256": source_context.sha256,
            "preregistration_sha256": PREREGISTRATION.sha256,
            "normalization_policy_sha256": STOCK_NORMALIZATION_POLICY.sha256,
            "settlement_date": readiness.settlement_date,
        }
        for name, value in expected_context.items():
            if getattr(self.cohort, name) != value:
                raise _refuse(f"cohort.{name} does not match upstream disposition")

        raw_disposition_sha = self.current.sha256
        feature = self.current.feature
        member = self.cohort.member_for_event(self.current.readiness.event_id)
        for outcome in self.outcomes:
            if outcome.security_id != readiness.security_id:
                raise _refuse("outcome security_id does not match readiness")
            if outcome.event_id != readiness.event_id:
                raise _refuse("outcome event_id does not match readiness")
            if outcome.raw_disposition_sha256 != raw_disposition_sha:
                raise _refuse("outcome raw disposition SHA does not match current")
            if outcome.normalization_cohort_sha256 != self.cohort.sha256:
                raise _refuse("outcome normalization cohort SHA is stale")
            if outcome.normalization_policy_sha256 != STOCK_NORMALIZATION_POLICY.sha256:
                raise _refuse("outcome normalization policy SHA is stale")
            if feature is None:
                if outcome.raw_feature_sha256 is not None or outcome.raw_value is not None:
                    raise _refuse("upstream refusal cannot carry raw score data")
            else:
                expected_raw = (
                    feature.current_short_ratio
                    if outcome.model is StockScoreModel.S0_LEVEL
                    else feature.delta_short_ratio
                )
                if outcome.raw_feature_sha256 != feature.sha256:
                    raise _refuse("outcome raw feature SHA does not match current feature")
                if outcome.raw_value != expected_raw:
                    raise _refuse("outcome raw value does not match current feature")

        state = self.outcomes[0].revision_selection_state
        selected_event_id = self.outcomes[0].selected_event_id
        if any(
            item.revision_selection_state is not state
            or item.selected_event_id != selected_event_id
            for item in self.outcomes
        ):
            raise _refuse("S0/S1 outcomes disagree on revision selection")
        expected_selection = self.cohort.selection_for_event(
            self.current.readiness.event_id
        )
        if expected_selection is None or expected_selection != (
            state,
            selected_event_id,
        ):
            raise _refuse(
                "outcome revision selection does not match authenticated release cutoff"
            )
        if state is not RevisionSelectionState.SELECTED:
            expected_reason = (
                REFUSAL_SUPERSEDED_AT_RELEASE_CUTOFF
                if state is RevisionSelectionState.SUPERSEDED
                else REFUSAL_NOT_VISIBLE_AT_RELEASE_CUTOFF
            )
            for outcome in self.outcomes:
                if outcome.refusal_reasons != (expected_reason,):
                    raise _refuse("non-selected event has wrong terminal refusal")
                self._require_no_normalization(outcome)
            return
        if selected_event_id != readiness.event_id:
            raise _refuse("selected outcome does not select its own event")
        if feature is None:
            for outcome in self.outcomes:
                if outcome.refusal_reasons != self.current.refusal_reasons:
                    raise _refuse("selected upstream refusals were not preserved exactly")
                self._require_no_normalization(outcome)
            return

        identity = feature.current_snapshot.security
        universe_reasons = tuple(
            sorted(
                reason
                for condition, reason in (
                    (identity.country != "US", REFUSAL_NON_US_SECURITY),
                    (
                        identity.security_type != "COMMON_STOCK",
                        REFUSAL_NON_COMMON_STOCK_SECURITY,
                    ),
                )
                if condition
            )
        )
        if universe_reasons:
            for outcome in self.outcomes:
                if outcome.refusal_reasons != universe_reasons:
                    raise _refuse("universe-ineligible event has wrong refusal")
                self._require_no_normalization(outcome)
            return
        if (
            feature.execution_at != self.cohort.decision_at
            or feature.execution_session != self.cohort.decision_session
        ):
            raise _refuse("selected feature is not available at fixed release cutoff")
        if member is None:
            raise _refuse("selected eligible feature is absent from cohort candidates")

        if len(self.cohort.taxonomy_lineages) != 1:
            for outcome in self.outcomes:
                if outcome.refusal_reasons != (REFUSAL_MIXED_TAXONOMY_LINEAGE,):
                    raise _refuse("mixed taxonomy cohort has wrong refusal")
                self._require_no_normalization(outcome)
            return
        sector_members = tuple(
            item
            for item in self.cohort.candidate_members
            if item.sector_code == member.sector_code
        )
        if len(sector_members) < STOCK_NORMALIZATION_POLICY.minimum_sector_peers:
            for outcome in self.outcomes:
                if outcome.refusal_reasons != (REFUSAL_INSUFFICIENT_SECTOR_PEERS,):
                    raise _refuse("underfilled sector has wrong refusal")
                if outcome.sector_members != sector_members:
                    raise _refuse("underfilled outcome has wrong sector member witness")
                bounds = self.cohort.bounds_for(outcome.model)
                expected_lower = bounds.lower if bounds is not None else None
                expected_upper = bounds.upper if bounds is not None else None
                if (
                    outcome.winsor_lower != expected_lower
                    or outcome.winsor_upper != expected_upper
                ):
                    raise _refuse(
                        "underfilled outcome winsor bounds do not match cohort"
                    )
                if any(
                    value is not None
                    for value in (
                        outcome.winsorized_value,
                        outcome.sector_median,
                        outcome.sector_mad,
                        outcome.scaled_mad,
                        outcome.score,
                    )
                ):
                    raise _refuse("underfilled sector cannot carry statistics")
            return

        for outcome in self.outcomes:
            self._validate_normalized_outcome(outcome, member, sector_members)

    @staticmethod
    def _require_no_normalization(outcome: StockModelOutcome) -> None:
        if outcome.sector_members:
            raise _refuse("non-normalized outcome cannot carry sector members")
        if any(
            value is not None
            for value in (
                outcome.winsor_lower,
                outcome.winsor_upper,
                outcome.winsorized_value,
                outcome.sector_median,
                outcome.sector_mad,
                outcome.scaled_mad,
                outcome.score,
            )
        ):
            raise _refuse("non-normalized outcome carries normalization values")

    def _validate_normalized_outcome(
        self,
        outcome: StockModelOutcome,
        member: StockNormalizationMember,
        sector_members: tuple[StockNormalizationMember, ...],
    ) -> None:
        if outcome.sector_code != member.sector_code:
            raise _refuse("normalized outcome has wrong sector_code")
        if outcome.sector_members != sector_members:
            raise _refuse("normalized outcome has wrong sector member witness")
        bounds = self.cohort.bounds_for(outcome.model)
        if bounds is None:
            raise _refuse("eligible outcome has no model-specific winsor bounds")
        if outcome.winsor_lower != bounds.lower or outcome.winsor_upper != bounds.upper:
            raise _refuse("outcome winsor bounds do not match cohort")
        lower = bounds.lower.to_fraction()
        upper = bounds.upper.to_fraction()
        clipped = tuple(
            _clip(item.model_value(outcome.model).to_fraction(), lower, upper)
            for item in sector_members
        )
        target = _clip(outcome.raw_value.to_fraction(), lower, upper)
        median = _median(clipped)
        mad = _median(tuple(abs(value - median) for value in clipped))
        scale = mad * STOCK_NORMALIZATION_POLICY.mad_scale.to_fraction()
        expected = {
            "winsorized_value": _rational(target),
            "sector_median": _rational(median),
            "sector_mad": _rational(mad),
            "scaled_mad": _rational(scale),
        }
        for name, value in expected.items():
            if getattr(outcome, name) != value:
                raise _refuse(f"outcome.{name} does not match exact cohort arithmetic")
        if mad == 0:
            if outcome.score is not None or outcome.refusal_reasons != (
                REFUSAL_ZERO_SECTOR_MAD,
            ):
                raise _refuse("zero-MAD sector/model must refuse without a score")
            return
        expected_score = _rational((target - median) / scale)
        if outcome.score != expected_score or outcome.refusal_reasons:
            raise _refuse("normalized score does not match exact MAD equation")

    def to_payload(self) -> dict[str, Any]:
        return {
            "cohort": self.cohort.to_payload(),
            "current": self.current.to_payload(),
            "outcomes": [item.to_payload() for item in self.outcomes],
            "schema_version": self.schema_version,
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def _validate_raw_batch(
    raw_dispositions: tuple[StockFeatureDisposition, ...],
) -> StockFeatureSourceContext | None:
    if type(raw_dispositions) is not tuple or not all(
        type(item) is StockFeatureDisposition for item in raw_dispositions
    ):
        raise _refuse(
            "raw_dispositions must be an exact tuple of exact "
            "StockFeatureDisposition values"
        )
    if not raw_dispositions:
        return None
    event_ids = [item.readiness.event_id for item in raw_dispositions]
    if len(event_ids) != len(set(event_ids)):
        raise _refuse("raw_dispositions contain duplicate readiness event_id")
    for name in (
        "source_dataset_id",
        "source_vintage_sha256",
        "reference_dataset_id",
        "reference_bundle_sha256",
    ):
        if len({getattr(item.readiness, name) for item in raw_dispositions}) != 1:
            raise _refuse(f"raw_dispositions mix {name}")
    source_context = raw_dispositions[0].source_context
    if type(source_context) is not StockFeatureSourceContext:
        raise _refuse("raw_dispositions have no authenticated source_context")
    context_sha = source_context.sha256
    if any(
        type(item.source_context) is not StockFeatureSourceContext
        or item.source_context.sha256 != context_sha
        for item in raw_dispositions
    ):
        raise _refuse("raw_dispositions mix source_context_sha256")
    expected_event_ids = {
        item.event_id for item in source_context.source_vintage.snapshots
    }
    if set(event_ids) != expected_event_ids:
        raise _refuse("raw_dispositions event set is incomplete for source_vintage")
    release_keys_by_settlement: dict[str, set[str]] = {}
    for snapshot in source_context.source_vintage.snapshots:
        release_keys_by_settlement.setdefault(snapshot.settlement_date, set()).add(
            snapshot.release_calendar_key
        )
    if any(len(keys) != 1 for keys in release_keys_by_settlement.values()):
        raise _refuse(
            "one settlement cycle mixes multiple release-calendar lineages"
        )
    return source_context


def _classification_index(
    source_context: StockFeatureSourceContext,
) -> dict[str, SectorClassificationObservation]:
    result = {
        item.record_id: item
        for item in source_context.reference_bundle.classifications
    }
    if len(result) != len(source_context.reference_bundle.classifications):
        raise _refuse("reference bundle contains duplicate classification record_id")
    return result


def _member(
    disposition: StockFeatureDisposition,
    classification_by_id: dict[str, SectorClassificationObservation],
) -> StockNormalizationMember:
    feature = disposition.feature
    if type(feature) is not PitStockRawFeature:
        raise _refuse("normalization member requires exact raw feature")
    classification = classification_by_id.get(feature.classification_record_id)
    if classification is None:
        raise _refuse("raw feature classification record is absent from reference bundle")
    if (
        classification.security_id != feature.security_id
        or classification.taxonomy_id != feature.taxonomy_id
        or classification.sector_code != feature.sector_code
        or classification.industry_code != feature.industry_code
    ):
        raise _refuse("raw feature classification lineage does not match record")
    identity = feature.current_snapshot.security
    return StockNormalizationMember(
        security_id=feature.security_id,
        event_id=feature.event_id,
        logical_id=feature.current_snapshot.logical_id,
        prior_event_id=feature.prior_event_id,
        supersedes_event_id=feature.current_snapshot.supersedes_event_id,
        raw_feature_sha256=feature.sha256,
        raw_disposition_sha256=disposition.sha256,
        readiness_sha256=feature.readiness_sha256,
        security_identity_sha256=feature.security_identity_sha256,
        classification_record_id=feature.classification_record_id,
        taxonomy_id=feature.taxonomy_id,
        taxonomy_source_id=classification.source_id,
        taxonomy_source_version=classification.source_version,
        sector_code=feature.sector_code,
        ticker=identity.ticker,
        share_class=identity.share_class,
        s0_value=feature.current_short_ratio,
        s1_value=feature.delta_short_ratio,
    )


def _derive_release_selection(
    raw_dispositions: tuple[StockFeatureDisposition, ...],
    release: ReleaseCalendarEntry,
) -> tuple[
    StockFeatureSourceContext,
    tuple[StockFeatureDisposition, ...],
    tuple[tuple[str, RevisionSelectionState, str | None], ...],
    tuple[StockNormalizationMember, ...],
]:
    """Authenticate one fixed release cohort from the complete raw inventory."""
    source_context = _validate_raw_batch(raw_dispositions)
    if source_context is None:
        raise _refuse("normalization cohort requires a nonempty raw inventory")
    canonical_raw = tuple(
        sorted(
            raw_dispositions,
            key=lambda item: (
                item.readiness.settlement_date,
                item.readiness.security_id,
                item.readiness.event_id,
            ),
        )
    )
    release_by_key = {
        item.key: item for item in source_context.source_vintage.release_calendar
    }
    if release_by_key.get(release.key) != release:
        raise _refuse("cohort release is not exact authenticated release evidence")
    group_snapshots = tuple(
        item
        for item in source_context.source_vintage.snapshots
        if item.release_calendar_key == release.key
    )
    if not group_snapshots:
        raise _refuse("cohort release has no source snapshots")
    if any(item.settlement_date != release.settlement_date for item in group_snapshots):
        raise _refuse("cohort release snapshots mix settlement cycles")

    by_event = {item.readiness.event_id: item for item in canonical_raw}
    decision = release_execution_cohort(release)
    decision_at = _checked_timestamp(decision.opens_at, "decision.opens_at")
    selected_by_logical: dict[str, Any] = {}
    for snapshot in group_snapshots:
        disposition = by_event[snapshot.event_id]
        if _checked_timestamp(
            disposition.readiness.execution_at,
            "readiness.execution_at",
        ) > decision_at:
            continue
        previous = selected_by_logical.get(snapshot.logical_id)
        if previous is None or _checked_timestamp(
            snapshot.revision_published_at,
            "snapshot.revision_published_at",
        ) > _checked_timestamp(
            previous.revision_published_at,
            "previous.revision_published_at",
        ):
            selected_by_logical[snapshot.logical_id] = snapshot

    classification_by_id = _classification_index(source_context)
    selection_records: list[
        tuple[str, RevisionSelectionState, str | None]
    ] = []
    candidate_members: list[StockNormalizationMember] = []
    for snapshot in group_snapshots:
        disposition = by_event[snapshot.event_id]
        selected = selected_by_logical.get(snapshot.logical_id)
        if selected is not None and selected.event_id == snapshot.event_id:
            state = RevisionSelectionState.SELECTED
            selected_event_id = snapshot.event_id
        elif _checked_timestamp(
            disposition.readiness.execution_at,
            "readiness.execution_at",
        ) <= decision_at:
            state = RevisionSelectionState.SUPERSEDED
            selected_event_id = selected.event_id if selected is not None else None
        else:
            state = RevisionSelectionState.NOT_VISIBLE
            selected_event_id = selected.event_id if selected is not None else None
        selection_records.append(
            (snapshot.event_id, state, selected_event_id)
        )

        feature = disposition.feature
        if state is not RevisionSelectionState.SELECTED or feature is None:
            continue
        identity = feature.current_snapshot.security
        if identity.country != "US" or identity.security_type != "COMMON_STOCK":
            continue
        if (
            feature.execution_session != decision.session
            or feature.execution_at != decision.opens_at
        ):
            raise _refuse(
                "fixed-cutoff selected feature has a different execution cohort"
            )
        candidate_members.append(_member(disposition, classification_by_id))

    return (
        source_context,
        canonical_raw,
        tuple(sorted(selection_records, key=lambda item: item[0])),
        tuple(sorted(candidate_members, key=lambda item: item.sort_key)),
    )


def _build_bounds(
    eligible_members: tuple[StockNormalizationMember, ...],
) -> tuple[StockWinsorBounds, ...]:
    if not eligible_members:
        return ()
    digest = _members_digest(eligible_members)
    results = []
    for model in STOCK_NORMALIZATION_POLICY.models:
        values = tuple(
            item.model_value(model).to_fraction() for item in eligible_members
        )
        results.append(
            StockWinsorBounds(
                model=model,
                lower=_rational(
                    _type7_quantile(
                        values,
                        STOCK_NORMALIZATION_POLICY.winsor_lower_probability.to_fraction(),
                    )
                ),
                upper=_rational(
                    _type7_quantile(
                        values,
                        STOCK_NORMALIZATION_POLICY.winsor_upper_probability.to_fraction(),
                    )
                ),
                reference_count=len(eligible_members),
                reference_members_sha256=digest,
            )
        )
    return tuple(results)


def _make_outcome(
    *,
    disposition: StockFeatureDisposition,
    model: StockScoreModel,
    state: RevisionSelectionState,
    selected_event_id: str | None,
    cohort: StockNormalizationCohort,
    member: StockNormalizationMember | None,
) -> StockModelOutcome:
    feature = disposition.feature
    raw_value = None
    raw_feature_sha = None
    if feature is not None:
        raw_feature_sha = feature.sha256
        raw_value = (
            feature.current_short_ratio
            if model is StockScoreModel.S0_LEVEL
            else feature.delta_short_ratio
        )
    common = {
        "model": model,
        "security_id": disposition.readiness.security_id,
        "event_id": disposition.readiness.event_id,
        "selected_event_id": selected_event_id,
        "revision_selection_state": state,
        "raw_disposition_sha256": disposition.sha256,
        "raw_feature_sha256": raw_feature_sha,
        "normalization_policy_sha256": STOCK_NORMALIZATION_POLICY.sha256,
        "cohort": cohort,
        "raw_value": raw_value,
    }
    if state is not RevisionSelectionState.SELECTED:
        reason = (
            REFUSAL_SUPERSEDED_AT_RELEASE_CUTOFF
            if state is RevisionSelectionState.SUPERSEDED
            else REFUSAL_NOT_VISIBLE_AT_RELEASE_CUTOFF
        )
        return StockModelOutcome(
            **common,
            sector_code=None,
            sector_members=(),
            winsor_lower=None,
            winsor_upper=None,
            winsorized_value=None,
            sector_median=None,
            sector_mad=None,
            scaled_mad=None,
            score=None,
            refusal_reasons=(reason,),
        )
    if feature is None:
        return StockModelOutcome(
            **common,
            sector_code=None,
            sector_members=(),
            winsor_lower=None,
            winsor_upper=None,
            winsorized_value=None,
            sector_median=None,
            sector_mad=None,
            scaled_mad=None,
            score=None,
            refusal_reasons=disposition.refusal_reasons,
        )

    identity = feature.current_snapshot.security
    universe_reasons = tuple(
        sorted(
            reason
            for condition, reason in (
                (identity.country != "US", REFUSAL_NON_US_SECURITY),
                (
                    identity.security_type != "COMMON_STOCK",
                    REFUSAL_NON_COMMON_STOCK_SECURITY,
                ),
            )
            if condition
        )
    )
    if universe_reasons:
        return StockModelOutcome(
            **common,
            sector_code=None,
            sector_members=(),
            winsor_lower=None,
            winsor_upper=None,
            winsorized_value=None,
            sector_median=None,
            sector_mad=None,
            scaled_mad=None,
            score=None,
            refusal_reasons=universe_reasons,
        )
    if member is None:
        raise _refuse("selected universe-eligible event has no candidate member")
    if len(cohort.taxonomy_lineages) != 1:
        return StockModelOutcome(
            **common,
            sector_code=None,
            sector_members=(),
            winsor_lower=None,
            winsor_upper=None,
            winsorized_value=None,
            sector_median=None,
            sector_mad=None,
            scaled_mad=None,
            score=None,
            refusal_reasons=(REFUSAL_MIXED_TAXONOMY_LINEAGE,),
        )

    sector_members = tuple(
        item
        for item in cohort.candidate_members
        if item.sector_code == member.sector_code
    )
    bounds = cohort.bounds_for(model)
    if len(sector_members) < STOCK_NORMALIZATION_POLICY.minimum_sector_peers:
        return StockModelOutcome(
            **common,
            sector_code=member.sector_code,
            sector_members=sector_members,
            winsor_lower=(bounds.lower if bounds is not None else None),
            winsor_upper=(bounds.upper if bounds is not None else None),
            winsorized_value=None,
            sector_median=None,
            sector_mad=None,
            scaled_mad=None,
            score=None,
            refusal_reasons=(REFUSAL_INSUFFICIENT_SECTOR_PEERS,),
        )
    if bounds is None:
        raise _refuse("minimum-peer sector is absent from global winsor reference")
    lower = bounds.lower.to_fraction()
    upper = bounds.upper.to_fraction()
    clipped = tuple(
        _clip(item.model_value(model).to_fraction(), lower, upper)
        for item in sector_members
    )
    target = _clip(raw_value.to_fraction(), lower, upper)
    median = _median(clipped)
    mad = _median(tuple(abs(value - median) for value in clipped))
    scaled_mad = mad * STOCK_NORMALIZATION_POLICY.mad_scale.to_fraction()
    if mad == 0:
        score = None
        refusal_reasons = (REFUSAL_ZERO_SECTOR_MAD,)
    else:
        score = _rational((target - median) / scaled_mad)
        refusal_reasons = ()
    return StockModelOutcome(
        **common,
        sector_code=member.sector_code,
        sector_members=sector_members,
        winsor_lower=bounds.lower,
        winsor_upper=bounds.upper,
        winsorized_value=_rational(target),
        sector_median=_rational(median),
        sector_mad=_rational(mad),
        scaled_mad=_rational(scaled_mad),
        score=score,
        refusal_reasons=refusal_reasons,
    )


def build_pit_stock_normalized_scores(
    raw_dispositions: tuple[StockFeatureDisposition, ...],
    *,
    policy: StockNormalizationPolicy = STOCK_NORMALIZATION_POLICY,
) -> tuple[StockScoreDisposition, ...]:
    """Build exact S0/S1 terminal outcomes for one complete SI-3A batch."""
    require_stock_normalization_policy(policy)
    source_context = _validate_raw_batch(raw_dispositions)
    if source_context is None:
        return ()

    by_event = {item.readiness.event_id: item for item in raw_dispositions}
    release_by_key = {
        item.key: item for item in source_context.source_vintage.release_calendar
    }
    snapshots_by_release: dict[str, list[Any]] = {}
    for snapshot in source_context.source_vintage.snapshots:
        snapshots_by_release.setdefault(snapshot.release_calendar_key, []).append(
            snapshot
        )

    results: list[StockScoreDisposition] = []
    for release_key in sorted(snapshots_by_release):
        release = release_by_key.get(release_key)
        if release is None:
            raise _refuse("source snapshot has no release-calendar evidence")
        decision = release_execution_cohort(release)
        group_snapshots = tuple(snapshots_by_release[release_key])
        cohort = StockNormalizationCohort(
            source_dataset_id=raw_dispositions[0].readiness.source_dataset_id,
            source_vintage_sha256=raw_dispositions[0].readiness.source_vintage_sha256,
            reference_dataset_id=raw_dispositions[0].readiness.reference_dataset_id,
            reference_bundle_sha256=raw_dispositions[0].readiness.reference_bundle_sha256,
            source_context_sha256=source_context.sha256,
            preregistration_sha256=PREREGISTRATION.sha256,
            normalization_policy_sha256=STOCK_NORMALIZATION_POLICY.sha256,
            release=release,
            settlement_date=release.settlement_date,
            decision_session=decision.session,
            decision_at=decision.opens_at,
            raw_dispositions=raw_dispositions,
        )

        for snapshot in group_snapshots:
            disposition = by_event[snapshot.event_id]
            selection = cohort.selection_for_event(snapshot.event_id)
            if selection is None:
                raise _refuse("release event lacks authenticated selection state")
            state, selected_event_id = selection
            member = cohort.member_for_event(snapshot.event_id)
            outcomes = tuple(
                _make_outcome(
                    disposition=disposition,
                    model=model,
                    state=state,
                    selected_event_id=selected_event_id,
                    cohort=cohort,
                    member=member,
                )
                for model in STOCK_NORMALIZATION_POLICY.models
            )
            results.append(
                StockScoreDisposition(
                    current=disposition,
                    cohort=cohort,
                    outcomes=outcomes,
                )
            )

    ordered = tuple(
        sorted(
            results,
            key=lambda item: (
                item.current.readiness.settlement_date,
                item.current.readiness.security_id,
                item.current.readiness.event_id,
            ),
        )
    )
    scored_keys = [
        (
            item.current.readiness.settlement_date,
            item.current.readiness.security_id,
            outcome.model,
        )
        for item in ordered
        for outcome in item.outcomes
        if outcome.score is not None
    ]
    if len(scored_keys) != len(set(scored_keys)):
        raise _refuse(
            "normalization produced more than one score per settlement/security/model"
        )
    selected_slots = [
        outcome.normalization_slot_id
        for item in ordered
        for outcome in item.outcomes
        if outcome.revision_selection_state is RevisionSelectionState.SELECTED
    ]
    if len(selected_slots) != len(set(selected_slots)):
        raise _refuse(
            "normalization produced more than one selected result per cycle slot"
        )
    return ordered
