"""Builder-authenticated production scoring census for formal ARV2 QC.

The only public score admission path accepts exactly six authenticated
``ProductionScoringResult`` objects and derives the complete TEST census for
both source views. Caller-authored scores and outcome-bearing pre-run bundles
are intentionally absent. A separate builder freezes the authenticated power
calibration receipt at its filesystem-reading boundary; subsequent checks are
pure identity, topology, and content reauthentication.
"""
from __future__ import annotations

import dataclasses
import heapq
import hashlib
import itertools
import json
import os
import re
import sys
import threading
import weakref
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from enum import Enum
from fractions import Fraction

from research.analyst_revisions_v2.accepted_risk_input_pair import (
    CENSORED_VIEW_LABEL,
    CURRENT_VIEW_LABEL,
)
from research.analyst_revisions_v2.formulas import analyst_decimal_context
from data.exchange_calendar import ExchangeCalendarError, trading_sessions
from research.analyst_revisions_v2.power_calibration_receipt import (
    PowerCalibrationReceipt,
    PowerCalibrationReceiptError,
    require_loaded_power_calibration_receipt,
)
from research.analyst_revisions_v2.power_calibration_protocol import (
    ProvisionalPowerDisposition,
)
from research.analyst_revisions_v2.production_input_pipeline import (
    ProductionInputBatch,
    ProductionInputError,
    SignalArm,
    require_production_input_batch,
)
from research.analyst_revisions_v2.global_benchmark_contract import (
    GlobalBenchmarkContractError,
    GlobalRatingMapping,
    GlobalRatingMappingRefusal,
    GlobalRatingRefusalReason,
    coverage_meets_minimum,
    global_rating_delta,
    require_loaded_global_benchmark_contract,
    resolve_global_rating,
)
from research.analyst_revisions_v2.production_truth_gate import (
    ProductionTruthArtifact,
    ProductionTruthError,
    require_production_truth_artifact,
)
from research.analyst_revisions_v2.production_scoring import (
    CONTROL_COLUMNS,
    FORMAL_FOLD_BOUNDARIES as PRODUCTION_SCORING_FOLD_BOUNDARIES,
    FORMAL_HORIZON_FOLD_BOUNDARIES,
    RESULT_SCHEMA as PRODUCTION_SCORING_RESULT_SCHEMA,
    SCORING_CONTRACT_ID,
    SCORING_CONTRACT_SHA256,
    ContributionLineage,
    EligibleSecuritySession,
    EndpointLabelEvidence,
    EventScoringTerminal,
    FinalDecisionInput,
    FoldPartition,
    ProductionScoringError,
    ProductionScoringResult,
    ScoreState,
    ScoringRefusal,
    _DailyContribution,
    _daily_contributions_from_inputs,
    _decay,
    _fraction_decimal,
    _session_ordinals,
    _stable_sum,
    require_production_scoring_result,
)
from research.analyst_revisions_v2_qc.formal_run_protocol import (
    AcceptedRiskPairBinding,
    DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
    FORMAL_PRIMARY_FOLD_IDS,
    HORIZONS,
    FormalRunProtocolError,
    require_accepted_risk_pair_binding,
)


class FormalInputBundleError(ValueError):
    """A formal production-scoring or power parent is not exact."""


SCORING_CENSUS_SCHEMA = "arv2-formal-production-scoring-census-v1"
SCORING_LINEAGE_SCHEMA = "arv2-formal-production-decision-lineage-v1"
SCORING_REFUSAL_SCHEMA = "arv2-formal-production-scoring-refusal-v1"
SCORING_PROJECTION_BUILDER_SCHEMA = (
    "arv2-formal-production-scoring-projection-builder-v1"
)
SCORING_PROJECTION_SCHEMA = "arv2-formal-production-scoring-projection-v1"
SCORING_SESSION_BLOCK_SCHEMA = "arv2-formal-production-scoring-session-block-v1"
SCORING_FOLD_COMMITMENT_SCHEMA = "arv2-formal-scoring-fold-commitment-v1"
GLOBAL_COMPARATOR_COVERAGE_SCHEMA = (
    "arv2-formal-global-comparator-fold-coverage-v1"
)
GLOBAL_COMPARATOR_POOLED_COVERAGE_SCHEMA = (
    "arv2-formal-global-comparator-pooled-coverage-v1"
)
GLOBAL_COMPARATOR_COVERAGE_ACCUMULATOR_SCHEMA = (
    "arv2-formal-global-comparator-coverage-accumulator-v1"
)
GLOBAL_COMPARATOR_COVERAGE_SOURCE_SCHEMA = (
    "arv2-formal-global-comparator-coverage-source-v1"
)
SCHEMA = SCORING_CENSUS_SCHEMA
STATUS = "builder_authenticated_score_derived_test_census_no_action_authority"
AUTHORITY = (
    "score_and_power_content_authentication_only_no_qc_outcome_result_"
    "deployment_order_or_trading_authority"
)
_EXPECTED_SCORING_FOLD_GEOMETRY = tuple(PRODUCTION_SCORING_FOLD_BOUNDARIES)
_EXPECTED_HORIZON_FOLD_GEOMETRY = tuple(FORMAL_HORIZON_FOLD_BOUNDARIES)
_POST_QC_CAPABILITY_NAMES = (
    "filesystem_read", "environment_read", "credential_access",
    "provider_access", "outcome_fetch", "qc_account_access",
    "qc_object_store_read", "qc_object_store_write", "qc_project_create",
    "qc_upload", "qc_compile", "qc_launch", "result_read",
    "result_disposition", "deployment", "orders", "trading",
)
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}\Z")
_UPSTREAM_CAPACITY_DISPOSITION = (
    "blocked_pending_authenticated_truth_and_one_fold_materialization_capacity"
)
_GLOBAL_COVERAGE_LEDGER_IDS = (
    "endpoint_pair_mapping",
    "active_security_date_rows",
    "common_event_components",
    "component_member_incidence",
    "score_capable_dates",
)
_ENDPOINT_STATUS_IDS = ("mapped", "measured_refusal", "unknown", "invalid")
_DIRECTION_STATUS_IDS = ("expected_sign", "opposite_sign", "zero_delta")
_DATE_DIAGNOSTIC_IDS = (
    "firm_totalized_zero_dates",
    "global_totalized_zero_dates",
    "both_arms_constant_dates",
    "score_refused_candidate_dates",
    "preoutcome_candidate_dates",
)
_RAW_FORM_COLLISION_COUNT_IDS = (
    "canonical_keys_with_multiple_raw_forms",
    "canonical_keys_with_any_raw_form",
    "endpoint_instances_in_colliding_canonical_keys",
    "canonicalizable_endpoint_instances",
)
_NO_CANONICAL_LABEL_SHA256 = "0" * 64
_MAX_GLOBAL_LABEL_DIAGNOSTIC_ROWS = 4096
_GLOBAL_COVERAGE_ATTRIBUTION_RULE = (
    "one_C2_hash_occurrence_per_source_view_fold_when_its_lineage_is_present_"
    "in_any_firm_baseline_ACTIVE_H20_test_row_after_exact_firm_only_"
    "institution_security_session_daily_dedupe_and_before_global_map_"
    "exclusions;_pooled_counts_are_exact_integer_sums_of_the_six_fold_"
    "occurrences"
)


def _post_int(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise FormalInputBundleError(f"{name} must be an exact integer >= {minimum}")
    return value


def _post_sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise FormalInputBundleError(f"{name} must be a lowercase SHA-256")
    return value


def _post_id(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:
        raise FormalInputBundleError(f"{name} must be a bounded safe identifier")
    return value


def _post_date(value: object, name: str) -> date:
    if type(value) is not date:
        raise FormalInputBundleError(f"{name} must be an exact date")
    return value


def _post_decimal(value: object, name: str, *, nonnegative: bool = False) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise FormalInputBundleError(f"{name} must be an exact finite Decimal")
    if nonnegative and value < 0:
        raise FormalInputBundleError(f"{name} must be nonnegative")
    return value


def _post_canonical_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as exc:
        raise FormalInputBundleError("post-QC value is not canonical JSON") from exc


def _post_identified(
    *, prefix: str, schema: str, record: dict[str, object]
) -> tuple[str, str, bytes]:
    seed = {"schema": schema, **record}
    payload = _post_canonical_bytes(seed)
    digest = hashlib.sha256(payload).hexdigest()
    return f"{prefix}{digest[:24]}", digest, payload


def _source_view(signal_arm: SignalArm) -> str:
    if signal_arm is SignalArm.CURRENT_VINTAGE:
        return CURRENT_VIEW_LABEL
    if signal_arm is SignalArm.CONSERVATIVE_CENSORED:
        return CENSORED_VIEW_LABEL
    raise FormalInputBundleError("production score has an unknown signal arm")


@dataclasses.dataclass(frozen=True, slots=True)
class ScoringResultBinding:
    fold_id: str
    result_id: str
    result_sha256: str
    precontrol_batch_id: str
    precontrol_batch_sha256: str
    model_sha256s: tuple[str, str]

    def to_record(self) -> dict[str, object]:
        return {
            "fold_id": self.fold_id,
            "result_id": self.result_id,
            "result_sha256": self.result_sha256,
            "precontrol_batch_id": self.precontrol_batch_id,
            "precontrol_batch_sha256": self.precontrol_batch_sha256,
            "model_sha256s": list(self.model_sha256s),
        }


def _require_scoring_result_binding(
    value: ScoringResultBinding,
    *,
    expected_fold_id: str | None = None,
) -> ScoringResultBinding:
    """Validate the exact scalar/container shape of a result commitment."""

    if type(value) is not ScoringResultBinding:
        raise FormalInputBundleError("formal result binding changed type")
    if (
        value.fold_id not in FORMAL_PRIMARY_FOLD_IDS
        or (expected_fold_id is not None and value.fold_id != expected_fold_id)
    ):
        raise FormalInputBundleError("formal result binding fold changed")
    _post_id(value.result_id, "formal result binding result_id")
    _post_sha(value.result_sha256, "formal result binding result hash")
    _post_id(
        value.precontrol_batch_id,
        "formal result binding precontrol_batch_id",
    )
    _post_sha(
        value.precontrol_batch_sha256,
        "formal result binding precontrol batch hash",
    )
    if type(value.model_sha256s) is not tuple or len(value.model_sha256s) != 2:
        raise FormalInputBundleError("formal result binding model census changed")
    for digest in value.model_sha256s:
        _post_sha(digest, "formal result binding model hash")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class FormalCoverageLedger:
    """One exact 19/20 pre-outcome comparator-coverage ledger."""

    ledger_id: str
    numerator: int
    denominator: int
    threshold_numerator: int
    threshold_denominator: int
    passes: bool
    disposition: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.ledger_id not in _GLOBAL_COVERAGE_LEDGER_IDS:
            raise FormalInputBundleError("global coverage ledger id changed")
        if any(type(value) is not int for value in (
            self.numerator,
            self.denominator,
            self.threshold_numerator,
            self.threshold_denominator,
        )):
            raise FormalInputBundleError("global coverage counts must be exact integers")
        if (
            self.numerator < 0
            or self.denominator < 0
            or self.numerator > self.denominator
            or (self.threshold_numerator, self.threshold_denominator) != (19, 20)
            or type(self.passes) is not bool
            or type(self.reasons) is not tuple
            or any(type(item) is not str for item in self.reasons)
        ):
            raise FormalInputBundleError("global coverage ledger is outside its domain")
        expected_pass = (
            self.denominator > 0
            and self.numerator * 20 >= self.denominator * 19
        )
        expected_disposition = "PASS" if expected_pass else "INVALID_DATA"
        expected_reasons = () if expected_pass else (
            ("zero_denominator",)
            if self.denominator == 0
            else ("coverage_below_19_of_20",)
        )
        if (
            self.passes is not expected_pass
            or self.disposition != expected_disposition
            or self.reasons != expected_reasons
        ):
            raise FormalInputBundleError("global coverage disposition is not derived")

    def to_record(self) -> dict[str, object]:
        return {
            "ledger_id": self.ledger_id,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "threshold_numerator": self.threshold_numerator,
            "threshold_denominator": self.threshold_denominator,
            "passes": self.passes,
            "disposition": self.disposition,
            "reasons": list(self.reasons),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class FormalCoverageDiagnosticRatio:
    """A labeled, non-rescuing exact diagnostic ratio."""

    ratio_id: str
    numerator: int
    denominator: int
    available: bool

    def __post_init__(self) -> None:
        if type(self.ratio_id) is not str or not self.ratio_id:
            raise FormalInputBundleError("coverage diagnostic ratio id changed")
        if (
            type(self.numerator) is not int
            or type(self.denominator) is not int
            or self.numerator < 0
            or self.denominator < 0
            or self.numerator > self.denominator
            or type(self.available) is not bool
            or self.available is not (self.denominator > 0)
        ):
            raise FormalInputBundleError("coverage diagnostic ratio is invalid")

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class FormalGlobalComparatorCoverage:
    """Content-addressed fold or pooled coverage derived before outcomes."""

    coverage_id: str
    coverage_sha256: str
    schema: str
    scope_id: str
    source_view_id: str
    fold_ids: tuple[str, ...]
    result_bindings: tuple[ScoringResultBinding, ...]
    h20_test_intervals: tuple[tuple[str, str, str], ...]
    ledgers: tuple[FormalCoverageLedger, ...]
    endpoint_status_counts: tuple[tuple[str, int], ...]
    endpoint_pair_status_counts: tuple[tuple[str, int], ...]
    direction_status_counts: tuple[tuple[str, int], ...]
    raw_canonical_label_counts: tuple[tuple[str, str, str, int], ...]
    raw_label_disposition_counts: tuple[tuple[str, str, int], ...]
    canonical_label_disposition_counts: tuple[tuple[str, str, int], ...]
    raw_form_collision_counts: tuple[tuple[str, int], ...]
    date_diagnostic_counts: tuple[tuple[str, int], ...]
    diagnostic_ratios: tuple[FormalCoverageDiagnosticRatio, ...]
    ready: bool
    reasons: tuple[str, ...]
    attribution_rule: str
    outcome_free: bool
    _canonical_document: bytes = dataclasses.field(repr=False)

    def to_record(self, *, include_identity: bool = True) -> dict[str, object]:
        record: dict[str, object] = {
            "schema": self.schema,
            "scope_id": self.scope_id,
            "source_view_id": self.source_view_id,
            "fold_ids": list(self.fold_ids),
            "result_bindings": [item.to_record() for item in self.result_bindings],
            "h20_test_intervals": [list(item) for item in self.h20_test_intervals],
            "ledgers": [item.to_record() for item in self.ledgers],
            "endpoint_status_counts": [list(item) for item in self.endpoint_status_counts],
            "endpoint_pair_status_counts": [
                list(item) for item in self.endpoint_pair_status_counts
            ],
            "direction_status_counts": [list(item) for item in self.direction_status_counts],
            "raw_canonical_label_counts": [
                list(item) for item in self.raw_canonical_label_counts
            ],
            "raw_label_disposition_counts": [
                list(item) for item in self.raw_label_disposition_counts
            ],
            "canonical_label_disposition_counts": [
                list(item) for item in self.canonical_label_disposition_counts
            ],
            "raw_form_collision_counts": [
                list(item) for item in self.raw_form_collision_counts
            ],
            "date_diagnostic_counts": [list(item) for item in self.date_diagnostic_counts],
            "diagnostic_ratios": [item.to_record() for item in self.diagnostic_ratios],
            "ready": self.ready,
            "reasons": list(self.reasons),
            "attribution_rule": self.attribution_rule,
            "outcome_free": self.outcome_free,
        }
        if include_identity:
            record["coverage_id"] = self.coverage_id
            record["coverage_sha256"] = self.coverage_sha256
        return record


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalGlobalComparatorCoverageAccumulator:
    """Opaque one-fold arithmetic accumulator with no direct count channel."""

    accumulator_id: str
    schema: str
    fold_id: str
    source_view_id: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalGlobalComparatorCoverageSource:
    """Opaque, once-derived comparator/scoring source for one accepted-risk view."""

    source_id: str
    schema: str
    source_view_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class _FirmBaselineContribution:
    """One firm-arm daily contribution before global-map exclusions."""

    security_id: str
    common_event_id: str
    eligible_session: str
    linked_c2_row_sha256s: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class _GlobalLabelResolution:
    """Exact, non-text-exposing result of one authenticated label lookup."""

    raw_label: str
    raw_label_sha256: str
    canonical_label_sha256: str
    status: str
    score_numerator: int | None
    score_denominator: int | None


@dataclasses.dataclass(slots=True)
class _GlobalCoverageSourceState:
    batch_id: str
    batch_sha256: str
    global_map_id: str
    global_map_sha256: str
    signal_arm: SignalArm
    endpoint_labels: tuple[EndpointLabelEvidence, ...]
    label_by_hash: dict[str, EndpointLabelEvidence]
    action_by_hash: dict[str, str]
    label_resolutions: tuple[_GlobalLabelResolution, ...]
    firm_contributions: tuple[_FirmBaselineContribution, ...]
    contributions: tuple[_DailyContribution, ...]
    terminals: tuple[object, ...]
    firm_security_ids: tuple[str, ...]
    firm_contributions_by_security: tuple[
        tuple[_FirmBaselineContribution, ...], ...
    ]
    firm_sessions_by_security: tuple[tuple[str, ...], ...]
    contribution_security_ids: tuple[str, ...]
    contributions_by_security: tuple[tuple[_DailyContribution, ...], ...]
    contribution_sessions_by_security: tuple[tuple[str, ...], ...]
    firm_item_integrity: tuple[tuple[int, bytes], ...]
    contribution_item_integrity: tuple[tuple[int, bytes], ...]
    retained_payload_bytes: int
    fingerprint: bytes
    topology: tuple[object, ...]
    pid: int
    owner_thread_id: int


@dataclasses.dataclass(frozen=True, slots=True)
class _GlobalCoverageAccumulatorState:
    source: FormalGlobalComparatorCoverageSource
    ordinals: dict[str, int]
    expected_sessions: tuple[str, ...]
    immutable_retained_bytes: int
    next_session_index: int
    last_test_session_by_security: dict[str, str]
    last_session_payload_bytes: int
    firm_active_count: int
    paired_active_count: int
    firm_component_count: int
    retained_component_count: int
    firm_component_incidence: int
    retained_component_incidence: int
    candidate_dates: int
    capable_dates: int
    firm_totalized_dates: int
    global_totalized_dates: int
    both_constant_dates: int
    score_refused_dates: int
    pid: int
    owner_thread_id: int
    finalized: bool


_GLOBAL_COVERAGE_ACCUMULATORS: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalGlobalComparatorCoverageAccumulator],
        bytes,
        _GlobalCoverageAccumulatorState,
        tuple[object, ...],
    ],
] = {}
_GLOBAL_COVERAGE_SOURCES: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalGlobalComparatorCoverageSource],
        bytes,
        _GlobalCoverageSourceState,
        bytes,
        tuple[object, ...],
        int,
        tuple[int, ...],
    ],
] = {}
_GLOBAL_COVERAGE_ACCUMULATOR_LOCK = threading.RLock()


@dataclasses.dataclass(frozen=True, slots=True)
class ProductionScoredDecisionLineage:
    schema: str
    decision_id: str
    lineage_sha256: str
    source_view_id: str
    fold_id: str
    decision_session: date
    security_id: str
    issuer_id: str
    share_class_id: str
    listing_id: str
    historical_ticker: str
    sector_id: str
    industry_id: str
    structural_zero: bool
    firm_specific_score: Decimal
    global_score: Decimal
    transformed_controls: tuple[Decimal, ...]
    realized_volatility_60d: Decimal
    earnings_anchor_signed_session_distance: int | None
    common_event_component_id: str
    contributions: tuple[ContributionLineage, ...]
    final_scoring_row_sha256: str
    scoring_result_id: str
    scoring_result_sha256: str
    scoring_contract_id: str
    scoring_contract_sha256: str

    def to_binding_record(self, *, include_identity: bool = True) -> dict[str, object]:
        """Compact Merkle leaf; the authenticated scorer owns full row content."""

        record: dict[str, object] = {
            "schema": self.schema,
            "source_view_id": self.source_view_id,
            "fold_id": self.fold_id,
            "decision_session": self.decision_session.isoformat(),
            "security_id": self.security_id,
            "final_scoring_row_sha256": self.final_scoring_row_sha256,
            "scoring_result_id": self.scoring_result_id,
            "scoring_result_sha256": self.scoring_result_sha256,
            "scoring_contract_id": self.scoring_contract_id,
            "scoring_contract_sha256": self.scoring_contract_sha256,
        }
        if include_identity:
            record["decision_id"] = self.decision_id
            record["lineage_sha256"] = self.lineage_sha256
        return record

    def to_record(self, *, include_identity: bool = True) -> dict[str, object]:
        record: dict[str, object] = {
            "schema": self.schema,
            "source_view_id": self.source_view_id,
            "fold_id": self.fold_id,
            "decision_session": self.decision_session.isoformat(),
            "security_id": self.security_id,
            "issuer_id": self.issuer_id,
            "share_class_id": self.share_class_id,
            "listing_id": self.listing_id,
            "historical_ticker": self.historical_ticker,
            "sector_id": self.sector_id,
            "industry_id": self.industry_id,
            "structural_zero": self.structural_zero,
            "firm_specific_score": str(self.firm_specific_score),
            "global_score": str(self.global_score),
            "transformed_controls": [str(item) for item in self.transformed_controls],
            "realized_volatility_60d": str(self.realized_volatility_60d),
            "earnings_anchor_signed_session_distance": (
                self.earnings_anchor_signed_session_distance
            ),
            "common_event_component_id": self.common_event_component_id,
            "contributions": [item.to_record() for item in self.contributions],
            "final_scoring_row_sha256": self.final_scoring_row_sha256,
            "scoring_result_id": self.scoring_result_id,
            "scoring_result_sha256": self.scoring_result_sha256,
            "scoring_contract_id": self.scoring_contract_id,
            "scoring_contract_sha256": self.scoring_contract_sha256,
        }
        if include_identity:
            record["decision_id"] = self.decision_id
            record["lineage_sha256"] = self.lineage_sha256
        return record


@dataclasses.dataclass(frozen=True, slots=True)
class ProductionScoringCensusRefusal:
    schema: str
    refusal_id: str
    refusal_sha256: str
    source_view_id: str
    fold_id: str
    decision_session: date
    security_id: str
    disposition: str
    source_refusal_sha256: str
    scoring_result_id: str
    scoring_result_sha256: str

    def to_record(self, *, include_identity: bool = True) -> dict[str, object]:
        record: dict[str, object] = {
            "schema": self.schema,
            "source_view_id": self.source_view_id,
            "fold_id": self.fold_id,
            "decision_session": self.decision_session.isoformat(),
            "security_id": self.security_id,
            "disposition": self.disposition,
            "source_refusal_sha256": self.source_refusal_sha256,
            "scoring_result_id": self.scoring_result_id,
            "scoring_result_sha256": self.scoring_result_sha256,
        }
        if include_identity:
            record["refusal_id"] = self.refusal_id
            record["refusal_sha256"] = self.refusal_sha256
        return record


@dataclasses.dataclass(frozen=True, slots=True)
class FormalSourceViewScoringCensus:
    source_view_id: str
    accepted: tuple[ProductionScoredDecisionLineage, ...]
    refused: tuple[ProductionScoringCensusRefusal, ...]
    terminal_count: int
    terminal_census_sha256: str

    def to_record(self) -> dict[str, object]:
        return {
            "source_view_id": self.source_view_id,
            "accepted": [item.to_binding_record() for item in self.accepted],
            "refused": [item.to_record() for item in self.refused],
            "terminal_count": self.terminal_count,
            "terminal_census_sha256": self.terminal_census_sha256,
        }


@dataclasses.dataclass(
    frozen=True, slots=True, weakref_slot=True, init=False
)
class FormalProductionScoringCensus:
    census_id: str
    census_sha256: str
    schema: str
    scoring_contract_id: str
    scoring_contract_sha256: str
    result_bindings: tuple[ScoringResultBinding, ...]
    formal_primary_fold_ids: tuple[str, ...]
    descriptive_sensitivity_fold_ids: tuple[str, ...]
    current_view: FormalSourceViewScoringCensus
    censored_view: FormalSourceViewScoringCensus
    matched_security_session_count: int
    matched_terminal_census_sha256: str
    source_views_distinct: bool
    source_views_share_one_census: bool
    caller_supplied_scores_accepted: bool
    pre_run_action_authority: None
    capabilities: tuple[tuple[str, bool], ...]
    _results: tuple[ProductionScoringResult, ...] = dataclasses.field(repr=False)
    _canonical_document: bytes = dataclasses.field(repr=False)

    @property
    def qc_launch_available(self) -> bool:
        return False

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False

    @property
    def trading_available(self) -> bool:
        return False


_SCORING_CENSUS_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalProductionScoringCensus],
        tuple[weakref.ReferenceType[ProductionScoringResult], ...],
        bytes,
        tuple[object, ...],
    ],
] = {}
_SCORING_CENSUS_AUTHORITIES_LOCK = threading.RLock()


def _forget_scoring_census(
    identity: int,
    reference: weakref.ReferenceType[FormalProductionScoringCensus],
) -> None:
    with _SCORING_CENSUS_AUTHORITIES_LOCK:
        current = _SCORING_CENSUS_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _SCORING_CENSUS_AUTHORITIES.pop(identity, None)


def _scoring_census_topology(
    value: FormalProductionScoringCensus,
) -> tuple[object, ...]:
    return (
        id(value.result_bindings),
        tuple(id(item) for item in value.result_bindings),
        id(value.formal_primary_fold_ids),
        id(value.descriptive_sensitivity_fold_ids),
        id(value.current_view),
        id(value.current_view.accepted),
        tuple(id(item) for item in value.current_view.accepted),
        id(value.current_view.refused),
        tuple(id(item) for item in value.current_view.refused),
        id(value.censored_view),
        id(value.censored_view.accepted),
        tuple(id(item) for item in value.censored_view.accepted),
        id(value.censored_view.refused),
        tuple(id(item) for item in value.censored_view.refused),
        id(value.capabilities),
        id(value._results),
        tuple(id(item) for item in value._results),
        id(value._canonical_document),
    )


def _result_binding(result: ProductionScoringResult) -> ScoringResultBinding:
    batch = result.precontrol_batch
    return ScoringResultBinding(
        fold_id=batch.fold.fold_id,
        result_id=result.result_id,
        result_sha256=result.result_sha256,
        precontrol_batch_id=batch.batch_id,
        precontrol_batch_sha256=batch.batch_sha256,
        model_sha256s=tuple(item.model_sha256 for item in result.models),
    )


def _coverage_ledger(
    ledger_id: str, numerator: int, denominator: int
) -> FormalCoverageLedger:
    try:
        passes = denominator > 0 and coverage_meets_minimum(
            numerator, denominator
        )
    except GlobalBenchmarkContractError as exc:
        raise FormalInputBundleError("global coverage counts are invalid") from exc
    return FormalCoverageLedger(
        ledger_id=ledger_id,
        numerator=numerator,
        denominator=denominator,
        threshold_numerator=19,
        threshold_denominator=20,
        passes=passes,
        disposition="PASS" if passes else "INVALID_DATA",
        reasons=() if passes else (
            ("zero_denominator",)
            if denominator == 0
            else ("coverage_below_19_of_20",)
        ),
    )


def _coverage_ratio(
    ratio_id: str, numerator: int, denominator: int
) -> FormalCoverageDiagnosticRatio:
    return FormalCoverageDiagnosticRatio(
        ratio_id=ratio_id,
        numerator=numerator,
        denominator=denominator,
        available=denominator > 0,
    )


def _is_preoutcome_candidate_date(
    census_security_ids: tuple[str, ...],
    accepted_security_ids: tuple[str, ...],
    refusal_security_ids: tuple[str, ...],
) -> bool:
    """Fix the score-capability denominator before score dispersion.

    Refused score terminals remain exact terminals for otherwise eligible
    census keys.  They therefore keep the date in the denominator while
    preventing it from entering the numerator.
    """

    for values in (
        census_security_ids,
        accepted_security_ids,
        refusal_security_ids,
    ):
        if (
            type(values) is not tuple
            or any(type(item) is not str for item in values)
            or values != tuple(sorted(set(values)))
        ):
            raise FormalInputBundleError(
                "preoutcome candidate terminal keys are not exact"
            )
    if set(accepted_security_ids) & set(refusal_security_ids):
        raise FormalInputBundleError(
            "preoutcome candidate terminals are not exclusive"
        )
    return (
        len(census_security_ids) >= 20
        and tuple(sorted((*accepted_security_ids, *refusal_security_ids)))
        == census_security_ids
    )


def _h20_geometry_for_fold(fold_id: str) -> tuple[str, int, str, str, str, str, str, str]:
    matches = tuple(
        item
        for item in _EXPECTED_HORIZON_FOLD_GEOMETRY
        if item[0] == fold_id and item[1] == 20
    )
    if len(matches) != 1:
        raise FormalInputBundleError("formal fold has no exact H20 geometry")
    return matches[0]


def _endpoint_status(value: object) -> str:
    if type(value) is GlobalRatingMapping:
        return "mapped"
    if type(value) is not GlobalRatingMappingRefusal:
        raise FormalInputBundleError("global endpoint resolver returned a hostile type")
    if value.reason is GlobalRatingRefusalReason.MEASURED_REFUSAL:
        return "measured_refusal"
    if value.reason is GlobalRatingRefusalReason.UNKNOWN_FUTURE_LABEL:
        return "unknown"
    return "invalid"


def _pair_status(previous_status: str, current_status: str) -> str:
    statuses = {previous_status, current_status}
    # Pair categories are disjoint.  Invalid dominates unknown, which dominates
    # the measured refusal list, so a mixed pair is counted exactly once.
    for status in ("invalid", "unknown", "measured_refusal"):
        if status in statuses:
            return status
    if statuses == {"mapped"}:
        return "mapped"
    raise FormalInputBundleError("global endpoint pair status is outside its census")


def _label_digest(value: str) -> str:
    if type(value) is not str:
        raise FormalInputBundleError("global label diagnostic changed type")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _raw_canonical_label_key(
    raw_label: str,
    resolved: GlobalRatingMapping | GlobalRatingMappingRefusal,
    status: str,
) -> tuple[str, str, str]:
    if status not in _ENDPOINT_STATUS_IDS:
        raise FormalInputBundleError("global label diagnostic status changed")
    canonical = resolved.canonical_label
    return (
        _label_digest(raw_label),
        (
            _NO_CANONICAL_LABEL_SHA256
            if canonical is None
            else _label_digest(canonical)
        ),
        status,
    )


def _cached_raw_canonical_label_key(
    value: _GlobalLabelResolution,
) -> tuple[str, str, str]:
    return (
        value.raw_label_sha256,
        value.canonical_label_sha256,
        value.status,
    )


def _global_label_diagnostics(
    values: tuple[tuple[str, str, str, int], ...],
) -> tuple[
    tuple[tuple[str, str, str, int], ...],
    tuple[tuple[str, str, int], ...],
    tuple[tuple[str, str, int], ...],
    tuple[tuple[str, int], ...],
]:
    """Validate and derive exact hashed raw/canonical map diagnostics."""

    if type(values) is not tuple or len(values) > _MAX_GLOBAL_LABEL_DIAGNOSTIC_ROWS:
        raise FormalInputBundleError("global label diagnostic census is unbounded")
    combined: Counter[tuple[str, str, str]] = Counter()
    raw_bindings: dict[str, tuple[str, str]] = {}
    canonical_statuses: dict[str, str] = {}
    for item in values:
        if (
            type(item) is not tuple
            or len(item) != 4
            or item[2] not in _ENDPOINT_STATUS_IDS
            or type(item[3]) is not int
            or item[3] <= 0
        ):
            raise FormalInputBundleError("global label diagnostic row changed")
        _post_sha(item[0], "raw global label hash")
        _post_sha(item[1], "canonical global label hash")
        if (
            (item[2] == "mapped" and item[1] == _NO_CANONICAL_LABEL_SHA256)
            or (item[2] == "invalid" and item[1] != _NO_CANONICAL_LABEL_SHA256)
            or (
                item[2] in {"measured_refusal", "unknown"}
                and item[1] == _NO_CANONICAL_LABEL_SHA256
            )
        ):
            raise FormalInputBundleError(
                "global label diagnostic canonical sentinel changed"
            )
        binding = (item[1], item[2])
        prior_binding = raw_bindings.setdefault(item[0], binding)
        if prior_binding != binding:
            raise FormalInputBundleError(
                "one raw global label has multiple resolver dispositions"
            )
        if item[1] != _NO_CANONICAL_LABEL_SHA256:
            prior_status = canonical_statuses.setdefault(item[1], item[2])
            if prior_status != item[2]:
                raise FormalInputBundleError(
                    "one canonical global label has multiple dispositions"
                )
        combined[(item[0], item[1], item[2])] += item[3]
    normalized = tuple(
        (*key, count) for key, count in sorted(combined.items())
    )
    if normalized != values:
        raise FormalInputBundleError(
            "global label diagnostic rows are not canonical and unique"
        )
    raw: Counter[tuple[str, str]] = Counter()
    canonical: Counter[tuple[str, str]] = Counter()
    raw_forms_by_canonical: dict[str, set[str]] = defaultdict(set)
    endpoint_instances_by_canonical: Counter[str] = Counter()
    for raw_hash, canonical_hash, status, count in normalized:
        raw[(raw_hash, status)] += count
        canonical[(canonical_hash, status)] += count
        if canonical_hash != _NO_CANONICAL_LABEL_SHA256:
            raw_forms_by_canonical[canonical_hash].add(raw_hash)
            endpoint_instances_by_canonical[canonical_hash] += count
    raw_counts = tuple((*key, count) for key, count in sorted(raw.items()))
    canonical_counts = tuple(
        (*key, count) for key, count in sorted(canonical.items())
    )
    colliding = {
        key for key, raw_forms in raw_forms_by_canonical.items()
        if len(raw_forms) > 1
    }
    collision_counts = (
        ("canonical_keys_with_multiple_raw_forms", len(colliding)),
        ("canonical_keys_with_any_raw_form", len(raw_forms_by_canonical)),
        (
            "endpoint_instances_in_colliding_canonical_keys",
            sum(endpoint_instances_by_canonical[key] for key in colliding),
        ),
        (
            "canonicalizable_endpoint_instances",
            sum(endpoint_instances_by_canonical.values()),
        ),
    )
    return normalized, raw_counts, canonical_counts, collision_counts


def _firm_baseline_contributions(
    batch: ProductionInputBatch,
) -> tuple[_FirmBaselineContribution, ...]:
    """Derive the firm-only daily dedupe baseline before global exclusions."""

    groups: dict[tuple[str, str, str], list[object]] = defaultdict(list)
    for row in batch.normalized_rows:
        groups[(
            row.institution_id,
            row.security_id,
            row.eligible_session,
        )].append(row)
    contributions: list[_FirmBaselineContribution] = []
    for key in sorted(groups):
        group = groups[key]
        signatures = {
            (row.previous_score, row.current_score, row.common_event_id)
            for row in group
        }
        # A conflicting institution/security/day is a firm-arm refusal.  It
        # cannot enter the baseline merely because a raw row exists.
        if len(signatures) != 1:
            continue
        representative = min(
            group,
            key=lambda row: (row.provider_event_id, row.row_sha256),
        )
        contributions.append(
            _FirmBaselineContribution(
                security_id=representative.security_id,
                common_event_id=representative.common_event_id,
                eligible_session=representative.eligible_session,
                linked_c2_row_sha256s=tuple(
                    sorted(row.row_sha256 for row in group)
                ),
            )
        )
    return tuple(sorted(
        contributions,
        key=lambda item: (
            item.eligible_session,
            item.security_id,
            item.common_event_id,
            item.linked_c2_row_sha256s,
        ),
    ))


def _contributions_by_security(
    values: tuple[_FirmBaselineContribution, ...] | tuple[_DailyContribution, ...],
) -> tuple[
    tuple[str, ...],
    tuple[tuple[object, ...], ...],
    tuple[tuple[str, ...], ...],
]:
    """Build one bounded, eligible-session-sorted lookup index."""

    grouped: dict[str, list[object]] = defaultdict(list)
    for item in values:
        grouped[item.security_id].append(item)
    security_ids: list[str] = []
    indexed: list[tuple[object, ...]] = []
    sessions: list[tuple[str, ...]] = []
    for security_id in sorted(grouped):
        items = tuple(sorted(
            grouped[security_id],
            key=lambda item: (
                item.eligible_session,
                getattr(item, "institution_id", ""),
                item.common_event_id,
                item.linked_c2_row_sha256s,
            ),
        ))
        security_ids.append(security_id)
        indexed.append(items)
        sessions.append(tuple(item.eligible_session for item in items))
    return tuple(security_ids), tuple(indexed), tuple(sessions)


def _component_topologies(
    security_ids: tuple[str, ...],
    event_edges: tuple[tuple[str, str], ...],
) -> tuple[
    tuple[
        tuple[str, ...],
        tuple[str, ...],
        tuple[tuple[str, str], ...],
    ],
    ...,
]:
    """Return exact security/common-event bipartite component topologies."""

    adjacency: dict[str, set[str]] = {
        f"security:{security_id}": set() for security_id in security_ids
    }
    for security_id, common_event_id in event_edges:
        security_node = f"security:{security_id}"
        if security_node not in adjacency:
            raise FormalInputBundleError("coverage event escaped its security census")
        event_node = f"event:{common_event_id}"
        adjacency[security_node].add(event_node)
        adjacency.setdefault(event_node, set()).add(security_node)
    seen: set[str] = set()
    canonical_edges = set(event_edges)
    components: list[
        tuple[
            tuple[str, ...],
            tuple[str, ...],
            tuple[tuple[str, str], ...],
        ]
    ] = []
    for security_id in security_ids:
        root = f"security:{security_id}"
        if root in seen:
            continue
        stack = [root]
        securities: list[str] = []
        events: list[str] = []
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            if node.startswith("security:"):
                securities.append(node[len("security:"):])
            else:
                events.append(node[len("event:"):])
            stack.extend(sorted(adjacency[node] - seen, reverse=True))
        component_securities = tuple(sorted(securities))
        component_events = tuple(sorted(events))
        component_security_set = set(component_securities)
        component_event_set = set(component_events)
        component_edges = tuple(sorted(
            (security_id, event_id)
            for security_id, event_id in canonical_edges
            if security_id in component_security_set
            and event_id in component_event_set
        ))
        components.append(
            (component_securities, component_events, component_edges)
        )
    return tuple(sorted(components))


def _active_component_topologies(
    visible_firm: tuple[_FirmBaselineContribution, ...],
    visible_paired: tuple[_DailyContribution, ...],
) -> tuple[
    tuple[
        tuple[
            tuple[str, ...], tuple[str, ...], tuple[tuple[str, str], ...]
        ],
        ...,
    ],
    tuple[
        tuple[
            tuple[str, ...], tuple[str, ...], tuple[tuple[str, str], ...]
        ],
        ...,
    ],
]:
    """Build component ledgers only over ACTIVE arm members, never census padding."""

    firm_active = tuple(sorted({item.security_id for item in visible_firm}))
    paired_active = tuple(sorted({item.security_id for item in visible_paired}))
    firm_edges = tuple(
        (item.security_id, item.common_event_id) for item in visible_firm
    )
    paired_edges = tuple(sorted({
        (item.security_id, item.common_event_id) for item in visible_paired
    }))
    return (
        _component_topologies(firm_active, firm_edges),
        _component_topologies(paired_active, paired_edges),
    )


def _coverage_source_topology(
    state: _GlobalCoverageSourceState,
) -> tuple[object, ...]:
    """Capture the exact opaque source container/record graph."""

    return (
        id(state.endpoint_labels),
        tuple(id(item) for item in state.endpoint_labels),
        id(state.label_by_hash),
        tuple((id(key), id(value)) for key, value in state.label_by_hash.items()),
        id(state.action_by_hash),
        tuple((id(key), id(value)) for key, value in state.action_by_hash.items()),
        id(state.label_resolutions),
        tuple(id(item) for item in state.label_resolutions),
        id(state.firm_contributions),
        tuple(
            (id(item), id(item.linked_c2_row_sha256s))
            for item in state.firm_contributions
        ),
        id(state.contributions),
        tuple(
            (id(item), id(item.linked_c2_row_sha256s))
            for item in state.contributions
        ),
        id(state.terminals),
        tuple(
            (id(item), id(item.linked_c2_row_sha256s))
            for item in state.terminals
        ),
        id(state.firm_security_ids),
        tuple(id(item) for item in state.firm_security_ids),
        id(state.firm_contributions_by_security),
        tuple(
            (id(items), tuple(id(item) for item in items))
            for items in state.firm_contributions_by_security
        ),
        id(state.firm_sessions_by_security),
        tuple(
            (id(items), tuple(id(item) for item in items))
            for items in state.firm_sessions_by_security
        ),
        id(state.contribution_security_ids),
        tuple(id(item) for item in state.contribution_security_ids),
        id(state.contributions_by_security),
        tuple(
            (id(items), tuple(id(item) for item in items))
            for items in state.contributions_by_security
        ),
        id(state.contribution_sessions_by_security),
        tuple(
            (id(items), tuple(id(item) for item in items))
            for items in state.contribution_sessions_by_security
        ),
        id(state.firm_item_integrity),
        tuple(id(item) for item in state.firm_item_integrity),
        id(state.contribution_item_integrity),
        tuple(id(item) for item in state.contribution_item_integrity),
    )


def _coverage_source_root_topology(
    state: _GlobalCoverageSourceState,
) -> tuple[int, ...]:
    """O(1) root check used by every session-level source lookup."""

    return tuple(id(getattr(state, name)) for name in (
        "endpoint_labels",
        "label_by_hash",
        "action_by_hash",
        "label_resolutions",
        "firm_contributions",
        "contributions",
        "terminals",
        "firm_security_ids",
        "firm_contributions_by_security",
        "firm_sessions_by_security",
        "contribution_security_ids",
        "contributions_by_security",
        "contribution_sessions_by_security",
        "firm_item_integrity",
        "contribution_item_integrity",
        "fingerprint",
        "topology",
    ))


def _fingerprint_update(
    hasher: object,
    kind: str,
    record: object,
) -> None:
    payload = _post_canonical_bytes({"kind": kind, "record": record})
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)


def _firm_contribution_record(
    item: _FirmBaselineContribution,
) -> dict[str, object]:
    return dataclasses.asdict(item)


def _paired_contribution_record(item: _DailyContribution) -> dict[str, object]:
    return {
        "representative_c2_row_sha256": item.representative_c2_row_sha256,
        "provider_event_id": item.provider_event_id,
        "security_id": item.security_id,
        "institution_id": item.institution_id,
        "common_event_id": item.common_event_id,
        "rating_action": item.rating_action,
        "publication_at_utc": item.publication_at_utc,
        "eligible_session": item.eligible_session,
        "firm_delta": [item.firm_delta.numerator, item.firm_delta.denominator],
        "global_delta": [item.global_delta.numerator, item.global_delta.denominator],
        "linked_c2_row_sha256s": list(item.linked_c2_row_sha256s),
    }


def _contribution_integrity(
    kind: str,
    item: _FirmBaselineContribution | _DailyContribution,
) -> bytes:
    record = (
        _firm_contribution_record(item)
        if type(item) is _FirmBaselineContribution
        else _paired_contribution_record(item)
    )
    return hashlib.sha256(
        _post_canonical_bytes({"kind": kind, "record": record})
    ).digest()


def _validate_source_index(
    *,
    security_ids: tuple[str, ...],
    indexed: tuple[tuple[object, ...], ...],
    sessions: tuple[tuple[str, ...], ...],
    values: tuple[object, ...],
    integrity: tuple[tuple[int, bytes], ...],
    expected_type: type,
    kind: str,
) -> None:
    if (
        security_ids != tuple(sorted(set(security_ids)))
        or len(security_ids) != len(indexed)
        or len(indexed) != len(sessions)
        or type(integrity) is not tuple
        or len(integrity) != len(values)
    ):
        raise FormalInputBundleError("coverage source index axis changed")
    seen: set[int] = set()
    for security_id, items, item_sessions in zip(
        security_ids, indexed, sessions, strict=True
    ):
        if (
            type(items) is not tuple
            or not items
            or type(item_sessions) is not tuple
            or item_sessions != tuple(item.eligible_session for item in items)
            or item_sessions != tuple(sorted(item_sessions))
            or any(
                type(item) is not expected_type or item.security_id != security_id
                for item in items
            )
        ):
            raise FormalInputBundleError("coverage source index content changed")
        seen.update(id(item) for item in items)
    if seen != {id(item) for item in values}:
        raise FormalInputBundleError("coverage source index is not exhaustive")
    expected_integrity = tuple(sorted(
        (id(item), _contribution_integrity(kind, item)) for item in values
    ))
    if integrity != expected_integrity:
        raise FormalInputBundleError("coverage source contribution integrity changed")


def _coverage_source_fingerprint(state: _GlobalCoverageSourceState) -> bytes:
    """Hash a source incrementally without materializing an O(N) document."""

    if (
        type(state.signal_arm) is not SignalArm
        or type(state.endpoint_labels) is not tuple
        or type(state.label_by_hash) is not dict
        or type(state.action_by_hash) is not dict
        or type(state.label_resolutions) is not tuple
        or type(state.firm_contributions) is not tuple
        or type(state.contributions) is not tuple
        or type(state.terminals) is not tuple
        or any(type(value) is not tuple for value in (
            state.firm_security_ids,
            state.firm_contributions_by_security,
            state.firm_sessions_by_security,
            state.contribution_security_ids,
            state.contributions_by_security,
            state.contribution_sessions_by_security,
            state.firm_item_integrity,
            state.contribution_item_integrity,
        ))
    ):
        raise FormalInputBundleError("coverage source graph changed type")
    hasher = hashlib.sha256()
    _fingerprint_update(
        hasher,
        "authority",
        {
            "batch_id": state.batch_id,
            "batch_sha256": state.batch_sha256,
            "global_map_id": state.global_map_id,
            "global_map_sha256": state.global_map_sha256,
            "signal_arm": state.signal_arm.value,
        },
    )
    for item in state.endpoint_labels:
        if type(item) is not EndpointLabelEvidence:
            raise FormalInputBundleError("coverage endpoint label changed type")
        item.__post_init__()
        _fingerprint_update(
            hasher,
            "endpoint_label",
            {**item.semantic_record(), "evidence_sha256": item.evidence_sha256},
        )
    if (
        tuple(state.label_by_hash) != tuple(sorted(state.label_by_hash))
        or tuple(state.action_by_hash) != tuple(sorted(state.action_by_hash))
        or tuple(state.label_by_hash) != tuple(state.action_by_hash)
        or tuple(state.label_by_hash.values()) != state.endpoint_labels
    ):
        raise FormalInputBundleError("coverage endpoint lookup topology changed")
    for digest in state.action_by_hash:
        _post_sha(digest, "coverage action row hash")
        if state.action_by_hash[digest] not in {"upgrades", "downgrades"}:
            raise FormalInputBundleError("coverage action changed")
        _fingerprint_update(
            hasher,
            "action",
            {"c2_row_sha256": digest, "raw_action": state.action_by_hash[digest]},
        )
    raw_labels: set[str] = set()
    for item in state.label_resolutions:
        if (
            type(item) is not _GlobalLabelResolution
            or item.status not in _ENDPOINT_STATUS_IDS
            or type(item.raw_label) is not str
            or item.raw_label in raw_labels
            or item.raw_label_sha256 != _label_digest(item.raw_label)
        ):
            raise FormalInputBundleError("coverage cached label resolution changed")
        raw_labels.add(item.raw_label)
        _post_sha(item.canonical_label_sha256, "cached canonical label hash")
        if item.status == "mapped":
            if (
                item.canonical_label_sha256 == _NO_CANONICAL_LABEL_SHA256
                or type(item.score_numerator) is not int
                or type(item.score_denominator) is not int
                or item.score_denominator <= 0
            ):
                raise FormalInputBundleError("mapped cached label changed")
        elif (
            item.score_numerator is not None
            or item.score_denominator is not None
            or (
                item.status == "invalid"
                and item.canonical_label_sha256 != _NO_CANONICAL_LABEL_SHA256
            )
            or (
                item.status in {"measured_refusal", "unknown"}
                and item.canonical_label_sha256 == _NO_CANONICAL_LABEL_SHA256
            )
        ):
            raise FormalInputBundleError("refused cached label changed")
        _fingerprint_update(hasher, "label_resolution", dataclasses.asdict(item))
    expected_raw_labels = {
        value
        for item in state.endpoint_labels
        for value in (item.raw_previous_label, item.raw_current_label)
    }
    if raw_labels != expected_raw_labels:
        raise FormalInputBundleError("coverage cached label census changed")
    for item in state.firm_contributions:
        if type(item) is not _FirmBaselineContribution:
            raise FormalInputBundleError("firm baseline contribution changed type")
        _fingerprint_update(hasher, "firm_contribution", _firm_contribution_record(item))
    for item in state.contributions:
        if type(item) is not _DailyContribution:
            raise FormalInputBundleError("paired contribution changed type")
        if (
            item.rating_action not in {"upgrades", "downgrades"}
            or any(
                state.action_by_hash.get(digest) != item.rating_action
                for digest in item.linked_c2_row_sha256s
            )
        ):
            raise FormalInputBundleError(
                "paired contribution action lineage changed"
            )
        _fingerprint_update(
            hasher,
            "paired_contribution",
            _paired_contribution_record(item),
        )
    for item in state.terminals:
        if type(item) is not EventScoringTerminal:
            raise FormalInputBundleError("event scoring terminal changed type")
        item.__post_init__()
        _fingerprint_update(hasher, "event_terminal", item.to_record())
    _validate_source_index(
        security_ids=state.firm_security_ids,
        indexed=state.firm_contributions_by_security,
        sessions=state.firm_sessions_by_security,
        values=state.firm_contributions,
        integrity=state.firm_item_integrity,
        expected_type=_FirmBaselineContribution,
        kind="firm_contribution",
    )
    _validate_source_index(
        security_ids=state.contribution_security_ids,
        indexed=state.contributions_by_security,
        sessions=state.contribution_sessions_by_security,
        values=state.contributions,
        integrity=state.contribution_item_integrity,
        expected_type=_DailyContribution,
        kind="paired_contribution",
    )
    return hasher.digest()


def _require_global_coverage_source_impl(
    value: FormalGlobalComparatorCoverageSource,
    *,
    deep: bool = True,
    _vault_require_source: object,
) -> tuple[FormalGlobalComparatorCoverageSource, _GlobalCoverageSourceState]:
    if type(value) is not FormalGlobalComparatorCoverageSource:
        raise FormalInputBundleError("formal coverage source changed type")
    static = _post_canonical_bytes({
        "source_id": value.source_id,
        "schema": value.schema,
        "source_view_id": value.source_view_id,
    })
    state = _vault_require_source(value, static, deep)
    return value, state


def _build_formal_global_comparator_coverage_source_impl(
    *,
    signal_arm: SignalArm,
    batch: ProductionInputBatch,
    global_contract: object,
    endpoint_labels: tuple[EndpointLabelEvidence, ...],
    _vault_initialize_source: object,
) -> FormalGlobalComparatorCoverageSource:
    """Derive one authenticated view source once for all six formal folds."""

    try:
        require_production_input_batch(batch)
        require_loaded_global_benchmark_contract(global_contract)
    except (ProductionInputError, GlobalBenchmarkContractError) as exc:
        raise FormalInputBundleError("coverage source parent is not authentic") from exc
    if (
        type(signal_arm) is not SignalArm
        or batch.signal_arm is not signal_arm
        or type(endpoint_labels) is not tuple
        or any(type(item) is not EndpointLabelEvidence for item in endpoint_labels)
    ):
        raise FormalInputBundleError("coverage source types changed")
    label_by_hash: dict[str, EndpointLabelEvidence] = {}
    for item in endpoint_labels:
        item.__post_init__()
        if item.c2_row_sha256 in label_by_hash:
            raise FormalInputBundleError("coverage endpoint label is duplicated")
        label_by_hash[item.c2_row_sha256] = item
    action_by_hash = {
        item.row_sha256: item.raw_action
        for item in sorted(batch.normalized_rows, key=lambda row: row.row_sha256)
    }
    if (
        tuple(label_by_hash) != tuple(sorted(label_by_hash))
        or tuple(action_by_hash) != tuple(sorted(action_by_hash))
        or tuple(label_by_hash) != tuple(action_by_hash)
    ):
        raise FormalInputBundleError("coverage endpoint label census is incomplete")
    distinct_labels = tuple(sorted({
        value
        for item in endpoint_labels
        for value in (item.raw_previous_label, item.raw_current_label)
    }))
    if len(distinct_labels) > _MAX_GLOBAL_LABEL_DIAGNOSTIC_ROWS:
        raise FormalInputBundleError("coverage global-label census exceeds capacity")
    try:
        resolved = {
            raw_label: resolve_global_rating(global_contract, raw_label)
            for raw_label in distinct_labels
        }
        contributions, terminals = _daily_contributions_from_inputs(
            global_contract,
            endpoint_labels,
            batch,
            resolved_labels=resolved,
        )
        firm_contributions = _firm_baseline_contributions(batch)
    except (ProductionScoringError, GlobalBenchmarkContractError) as exc:
        raise FormalInputBundleError("coverage source derivation failed") from exc
    resolutions: list[_GlobalLabelResolution] = []
    for raw_label in distinct_labels:
        value = resolved[raw_label]
        status = _endpoint_status(value)
        canonical_sha256 = (
            _NO_CANONICAL_LABEL_SHA256
            if value.canonical_label is None
            else _label_digest(value.canonical_label)
        )
        if type(value) is GlobalRatingMapping:
            numerator = value.entry.score_numerator
            denominator = value.entry.score_denominator
        else:
            numerator = None
            denominator = None
        resolutions.append(_GlobalLabelResolution(
            raw_label=raw_label,
            raw_label_sha256=_label_digest(raw_label),
            canonical_label_sha256=canonical_sha256,
            status=status,
            score_numerator=numerator,
            score_denominator=denominator,
        ))
    firm_security_ids, firm_index, firm_session_index = _contributions_by_security(
        firm_contributions
    )
    paired_security_ids, paired_index, paired_session_index = _contributions_by_security(
        contributions
    )
    state = _GlobalCoverageSourceState(
        batch_id=batch.batch_id,
        batch_sha256=batch.batch_sha256,
        global_map_id=global_contract.map_id,
        global_map_sha256=global_contract.map_hash,
        signal_arm=signal_arm,
        endpoint_labels=endpoint_labels,
        label_by_hash=label_by_hash,
        action_by_hash=action_by_hash,
        label_resolutions=tuple(resolutions),
        firm_contributions=firm_contributions,
        contributions=contributions,
        terminals=terminals,
        firm_security_ids=firm_security_ids,
        firm_contributions_by_security=firm_index,
        firm_sessions_by_security=firm_session_index,
        contribution_security_ids=paired_security_ids,
        contributions_by_security=paired_index,
        contribution_sessions_by_security=paired_session_index,
        firm_item_integrity=tuple(sorted(
            (
                id(item),
                _contribution_integrity("firm_contribution", item),
            )
            for item in firm_contributions
        )),
        contribution_item_integrity=tuple(sorted(
            (
                id(item),
                _contribution_integrity("paired_contribution", item),
            )
            for item in contributions
        )),
        retained_payload_bytes=0,
        fingerprint=b"",
        topology=(),
        pid=os.getpid(),
        owner_thread_id=threading.get_ident(),
    )
    state.fingerprint = _coverage_source_fingerprint(state)
    state.topology = _coverage_source_topology(state)
    # Include the registry state, captured topology/fingerprint, and every
    # derived payload root.  The retained-byte field is still zero during this
    # one-time traversal, avoiding self-referential accounting.
    state.retained_payload_bytes = _coverage_retained_object_graph_bytes(state)
    seed = {
        "schema": GLOBAL_COMPARATOR_COVERAGE_SOURCE_SCHEMA,
        "source_view_id": _source_view(signal_arm),
        "batch_id": state.batch_id,
        "batch_sha256": state.batch_sha256,
        "global_map_id": state.global_map_id,
        "global_map_sha256": state.global_map_sha256,
        "source_fingerprint_sha256": state.fingerprint.hex(),
        "endpoint_label_count": len(state.endpoint_labels),
        "firm_contribution_count": len(state.firm_contributions),
        "paired_contribution_count": len(state.contributions),
        "event_terminal_count": len(state.terminals),
    }
    digest = hashlib.sha256(_post_canonical_bytes(seed)).hexdigest()
    result = object.__new__(FormalGlobalComparatorCoverageSource)
    object.__setattr__(
        result,
        "source_id",
        f"arv2-formal-global-coverage-source-{digest[:24]}",
    )
    object.__setattr__(result, "schema", GLOBAL_COMPARATOR_COVERAGE_SOURCE_SCHEMA)
    object.__setattr__(result, "source_view_id", _source_view(signal_arm))
    static = _post_canonical_bytes({
        "source_id": result.source_id,
        "schema": result.schema,
        "source_view_id": result.source_view_id,
    })
    _vault_initialize_source(result, static, state)
    return _require_global_coverage_source(result)[0]


def formal_global_comparator_coverage_source_scoring_inputs(
    source: FormalGlobalComparatorCoverageSource,
) -> tuple[tuple[_DailyContribution, ...], tuple[EventScoringTerminal, ...]]:
    """Return the exact once-derived scorer inputs owned by an opaque source."""

    _value, state = _require_global_coverage_source(source)
    return state.contributions, state.terminals


def _visible_indexed_contributions(
    *,
    security_axis: tuple[str, ...],
    indexed: tuple[tuple[object, ...], ...],
    sessions: tuple[tuple[str, ...], ...],
    integrity: tuple[tuple[int, bytes], ...],
    kind: str,
    security_ids: tuple[str, ...],
    decision_session: str,
) -> tuple[object, ...]:
    if (
        type(security_ids) is not tuple
        or security_ids != tuple(sorted(set(security_ids)))
        or type(decision_session) is not str
    ):
        raise FormalInputBundleError("coverage visible-input key changed")
    try:
        date.fromisoformat(decision_session)
    except (TypeError, ValueError) as exc:
        raise FormalInputBundleError("coverage visible-input session changed") from exc
    visible: list[object] = []
    for security_id in security_ids:
        position = bisect_left(security_axis, security_id)
        if position == len(security_axis) or security_axis[position] != security_id:
            continue
        items = indexed[position]
        item_sessions = sessions[position]
        stop = bisect_right(item_sessions, decision_session)
        for item in items[:stop]:
            integrity_position = bisect_left(integrity, (id(item), b""))
            if (
                integrity_position == len(integrity)
                or integrity[integrity_position][0] != id(item)
                or integrity[integrity_position][1]
                != _contribution_integrity(kind, item)
            ):
                raise FormalInputBundleError(
                    "coverage visible contribution changed after authentication"
                )
            visible.append(item)
    return tuple(visible)


def _formal_global_comparator_coverage_source_visible_inputs(
    source: FormalGlobalComparatorCoverageSource,
    *,
    decision_session: str,
    security_ids: tuple[str, ...],
) -> tuple[
    tuple[_FirmBaselineContribution, ...],
    tuple[_DailyContribution, ...],
]:
    _value, state = _require_global_coverage_source(source, deep=False)
    firm = _visible_indexed_contributions(
        security_axis=state.firm_security_ids,
        indexed=state.firm_contributions_by_security,
        sessions=state.firm_sessions_by_security,
        integrity=state.firm_item_integrity,
        kind="firm_contribution",
        security_ids=security_ids,
        decision_session=decision_session,
    )
    paired = _visible_indexed_contributions(
        security_axis=state.contribution_security_ids,
        indexed=state.contributions_by_security,
        sessions=state.contribution_sessions_by_security,
        integrity=state.contribution_item_integrity,
        kind="paired_contribution",
        security_ids=security_ids,
        decision_session=decision_session,
    )
    return firm, paired


def formal_global_comparator_coverage_source_visible_contributions(
    source: FormalGlobalComparatorCoverageSource,
    *,
    decision_session: str,
    security_ids: tuple[str, ...],
) -> tuple[_DailyContribution, ...]:
    """Return only already-visible paired contributions for exact census keys."""

    _firm, paired = _formal_global_comparator_coverage_source_visible_inputs(
        source,
        decision_session=decision_session,
        security_ids=security_ids,
    )
    return paired


def _formal_global_comparator_coverage_source_retained_bytes_impl(
    source: FormalGlobalComparatorCoverageSource,
    *,
    _private_registry_bytes: object,
) -> int:
    """Return the source payload bound measured once at construction."""

    _value, state = _require_global_coverage_source(source, deep=False)
    with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
        registered = _GLOBAL_COVERAGE_SOURCES.get(id(source))
    if registered is None or registered[0]() is not source:
        raise FormalInputBundleError("coverage source authority disappeared")
    try:
        return (
            state.retained_payload_bytes
            + sys.getsizeof(source)
            + sys.getsizeof(registered)
            + sys.getsizeof(registered[0])
            + sys.getsizeof(registered[1])
            + sys.getsizeof(registered[6])
            + sum(sys.getsizeof(item) for item in registered[6])
            + sys.getsizeof(id(source))
            + sys.getsizeof(_GLOBAL_COVERAGE_SOURCES)
            + _private_registry_bytes("source", id(source))
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise FormalInputBundleError("coverage source is unmeasurable") from exc


def _require_global_coverage_accumulator_impl(
    value: FormalGlobalComparatorCoverageAccumulator,
    *,
    _vault_require_accumulator: object,
) -> tuple[
    FormalGlobalComparatorCoverageAccumulator,
    _GlobalCoverageAccumulatorState,
]:
    if type(value) is not FormalGlobalComparatorCoverageAccumulator:
        raise FormalInputBundleError("formal coverage accumulator changed type")
    state = _vault_require_accumulator(value)
    source, _source_state = _require_global_coverage_source(
        state.source,
        deep=False,
    )
    if source.source_view_id != value.source_view_id:
        raise FormalInputBundleError("formal coverage accumulator source changed")
    return value, state


def _coverage_accumulator_snapshot(
    state: _GlobalCoverageAccumulatorState,
) -> tuple[object, ...]:
    """Capture every mutable accumulator field behind the opaque handle."""

    integer_fields = (
        state.immutable_retained_bytes,
        state.next_session_index,
        state.last_session_payload_bytes,
        state.firm_active_count,
        state.paired_active_count,
        state.firm_component_count,
        state.retained_component_count,
        state.firm_component_incidence,
        state.retained_component_incidence,
        state.candidate_dates,
        state.capable_dates,
        state.firm_totalized_dates,
        state.global_totalized_dates,
        state.both_constant_dates,
        state.score_refused_dates,
        state.pid,
        state.owner_thread_id,
    )
    if (
        type(state.ordinals) is not dict
        or any(
            type(key) is not str or type(value) is not int or value < 0
            for key, value in state.ordinals.items()
        )
        or type(state.expected_sessions) is not tuple
        or any(type(item) is not str for item in state.expected_sessions)
        or type(state.last_test_session_by_security) is not dict
        or any(
            type(key) is not str or type(value) is not str
            for key, value in state.last_test_session_by_security.items()
        )
        or any(type(item) is not int or item < 0 for item in integer_fields[:-2])
        or type(state.pid) is not int
        or type(state.owner_thread_id) is not int
        or type(state.finalized) is not bool
    ):
        raise FormalInputBundleError("formal coverage accumulator state changed type")
    return (
        id(state.source),
        id(state.ordinals),
        tuple(state.ordinals.items()),
        id(state.expected_sessions),
        state.expected_sessions,
        id(state.last_test_session_by_security),
        tuple(state.last_test_session_by_security.items()),
        *integer_fields,
        state.finalized,
    )


def _coverage_retained_object_graph_bytes(*roots: object) -> int:
    """Conservatively measure accumulator-owned roots once per identity."""

    seen: set[int] = set()
    stack = list(roots)
    total = 0
    while stack:
        value = stack.pop()
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            total += sys.getsizeof(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise FormalInputBundleError(
                "coverage accumulator retained graph is unmeasurable"
            ) from exc
        if value is None or type(value) in {bool, int, str, bytes, Decimal}:
            continue
        if isinstance(value, Enum):
            continue
        if type(value) is tuple:
            stack.extend(value)
            continue
        if type(value) is dict:
            stack.extend(value.keys())
            stack.extend(value.values())
            continue
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            stack.extend(
                getattr(value, field.name) for field in dataclasses.fields(value)
            )
            continue
        # Fraction-like exact deltas expose two exact integer components.
        if type(getattr(value, "numerator", None)) is int and type(
            getattr(value, "denominator", None)
        ) is int:
            stack.extend((value.numerator, value.denominator))
            continue
        raise FormalInputBundleError(
            "coverage accumulator retained graph contains an opaque value: "
            f"{type(value).__module__}.{type(value).__qualname__}"
        )
    return total


def _formal_global_comparator_coverage_accumulator_retained_bytes_impl(
    accumulator: FormalGlobalComparatorCoverageAccumulator,
    *,
    _private_registry_bytes: object,
) -> int:
    """Return a fail-closed upper bound for the live accumulator payload.

    The batch, map, and endpoint-label parents are deliberately excluded
    because the streamed builder measures those same identities in its base
    retained graph.  Shared scalar descendants may still be counted twice,
    making this an upper bound rather than an unsafe underestimate.
    """

    _value, state = _require_global_coverage_accumulator(accumulator)
    with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
        registered = _GLOBAL_COVERAGE_ACCUMULATORS.get(id(accumulator))
    if registered is None or registered[0]() is not accumulator:
        raise FormalInputBundleError("formal coverage accumulator disappeared")
    try:
        return (
            _coverage_accumulator_steady_retained_bytes(
                accumulator=accumulator,
                state=state,
                snapshot=registered[3],
                registered=registered,
            )
            + _private_registry_bytes("accumulator", id(accumulator))
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise FormalInputBundleError(
            "coverage accumulator retained state is unmeasurable"
        ) from exc


def _coverage_accumulator_steady_retained_bytes(
    *,
    accumulator: FormalGlobalComparatorCoverageAccumulator,
    state: _GlobalCoverageAccumulatorState,
    snapshot: tuple[object, ...],
    registered: tuple[object, ...],
) -> int:
    """Measure every accumulator-owned steady-state object.

    The separately measured source graph is excluded, but the opaque handle,
    state object, registry entry, snapshot, mutable session map, and registry
    key/container overhead are all real retained objects and therefore cannot
    be replaced by the source handle's unrelated shallow size.
    """

    return (
        state.immutable_retained_bytes
        + sys.getsizeof(accumulator)
        + sys.getsizeof(state)
        + sys.getsizeof(state.last_test_session_by_security)
        + state.last_session_payload_bytes
        + _coverage_retained_object_graph_bytes(snapshot)
        + sys.getsizeof(registered)
        + sys.getsizeof(registered[0])
        + sys.getsizeof(registered[1])
        + sys.getsizeof(id(accumulator))
        + sys.getsizeof(_GLOBAL_COVERAGE_ACCUMULATORS)
    )


def _coverage_accumulator_transition_retained_bytes(
    *,
    accumulator: FormalGlobalComparatorCoverageAccumulator,
    prior_state: _GlobalCoverageAccumulatorState,
    prior_snapshot: tuple[object, ...],
    prior_registered: tuple[object, ...],
    next_state: _GlobalCoverageAccumulatorState,
    next_snapshot: tuple[object, ...],
    next_registered: tuple[object, ...],
) -> int:
    """Upper-bound the old-plus-new CAS graph while both versions are live."""

    if prior_state.immutable_retained_bytes != next_state.immutable_retained_bytes:
        raise FormalInputBundleError("coverage immutable retained state changed")
    return (
        prior_state.immutable_retained_bytes
        + sys.getsizeof(accumulator)
        + sys.getsizeof(prior_state)
        + sys.getsizeof(next_state)
        + sys.getsizeof(prior_state.last_test_session_by_security)
        + prior_state.last_session_payload_bytes
        + sys.getsizeof(next_state.last_test_session_by_security)
        + next_state.last_session_payload_bytes
        + _coverage_retained_object_graph_bytes(prior_snapshot, next_snapshot)
        + sys.getsizeof(prior_registered)
        + sys.getsizeof(next_registered)
        + sys.getsizeof(prior_registered[0])
        + sys.getsizeof(prior_registered[1])
        + sys.getsizeof(id(accumulator))
        + sys.getsizeof(_GLOBAL_COVERAGE_ACCUMULATORS)
    )


def _make_global_coverage_authority_vault(derive_session: object):
    """Keep source and accumulator authority outside public registries.

    Public entries remain inspectable compatibility views, but the exact same
    entry tuple is retained independently in this closure.  Replacing a public
    entry and recomputing its visible fingerprint/snapshot cannot mint
    authority.  Only the exact session transition and final seal can advance
    accumulator state; no generic state-reseal operation is exposed.
    """

    if not callable(derive_session):
        raise FormalInputBundleError("coverage session transition changed type")

    source_records: dict[int, tuple[object, ...]] = {}
    accumulator_records: dict[int, tuple[object, ...]] = {}

    def reset_after_fork() -> None:
        # A fork can inherit this RLock while another vanished thread owns it.
        # Replace it without touching the inherited lock, then discard every
        # process-bound authority entry.  Existing handles refuse in the child;
        # fresh child construction starts against an unlocked empty vault.
        global _GLOBAL_COVERAGE_ACCUMULATOR_LOCK
        _GLOBAL_COVERAGE_ACCUMULATOR_LOCK = threading.RLock()
        source_records.clear()
        accumulator_records.clear()
        _GLOBAL_COVERAGE_SOURCES.clear()
        _GLOBAL_COVERAGE_ACCUMULATORS.clear()

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)

    def forget_source(identity: int, reference: object) -> None:
        with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            private = source_records.get(identity)
            if private is not None and private[0] is reference:
                source_records.pop(identity, None)
                _GLOBAL_COVERAGE_SOURCES.pop(identity, None)

    def forget_accumulator(identity: int, reference: object) -> None:
        with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            private = accumulator_records.get(identity)
            if private is not None and private[0] is reference:
                accumulator_records.pop(identity, None)
                _GLOBAL_COVERAGE_ACCUMULATORS.pop(identity, None)

    def source_static(value: FormalGlobalComparatorCoverageSource) -> bytes:
        return _post_canonical_bytes({
            "source_id": value.source_id,
            "schema": value.schema,
            "source_view_id": value.source_view_id,
        })

    def source_entry_locked(
        value: FormalGlobalComparatorCoverageSource,
        *,
        deep: bool,
    ) -> tuple[_GlobalCoverageSourceState, tuple[object, ...]]:
        identity = id(value)
        private = source_records.get(identity)
        public = _GLOBAL_COVERAGE_SOURCES.get(identity)
        try:
            valid = (
                private is not None
                and public is private
                and len(private) == 7
                and private[0]() is value
                and private[1] == source_static(value)
                and type(private[2]) is _GlobalCoverageSourceState
                and private[2].fingerprint == private[3]
                and private[2].topology == private[4]
                and private[2].retained_payload_bytes == private[5]
                and _coverage_source_root_topology(private[2]) == private[6]
                and private[2].pid == os.getpid()
                and private[2].owner_thread_id == threading.get_ident()
                and value.schema == GLOBAL_COMPARATOR_COVERAGE_SOURCE_SCHEMA
                and value.source_view_id == _source_view(private[2].signal_arm)
            )
            if valid and deep:
                valid = (
                    _coverage_source_topology(private[2]) == private[4]
                    and _coverage_source_fingerprint(private[2]) == private[3]
                )
        except (AttributeError, TypeError, ValueError, IndexError):
            valid = False
        if not valid:
            raise FormalInputBundleError(
                "formal coverage source changed or is not builder-authenticated"
            )
        assert private is not None
        return private[2], private

    def initialize_source(
        value: FormalGlobalComparatorCoverageSource,
        static: bytes,
        state: _GlobalCoverageSourceState,
    ) -> None:
        if (
            type(value) is not FormalGlobalComparatorCoverageSource
            or type(static) is not bytes
            or type(state) is not _GlobalCoverageSourceState
            or static != source_static(value)
            or state.pid != os.getpid()
            or state.owner_thread_id != threading.get_ident()
            or value.schema != GLOBAL_COMPARATOR_COVERAGE_SOURCE_SCHEMA
            or value.source_view_id != _source_view(state.signal_arm)
            or type(state.retained_payload_bytes) is not int
            or state.retained_payload_bytes <= 0
            or state.fingerprint != _coverage_source_fingerprint(state)
            or state.topology != _coverage_source_topology(state)
        ):
            raise FormalInputBundleError("initial coverage source authority changed")
        expected_retained = _coverage_retained_object_graph_bytes(
            dataclasses.replace(state, retained_payload_bytes=0)
        )
        if state.retained_payload_bytes != expected_retained:
            raise FormalInputBundleError(
                "initial coverage source retained-byte authority changed"
            )
        seed = {
            "schema": GLOBAL_COMPARATOR_COVERAGE_SOURCE_SCHEMA,
            "source_view_id": value.source_view_id,
            "batch_id": state.batch_id,
            "batch_sha256": state.batch_sha256,
            "global_map_id": state.global_map_id,
            "global_map_sha256": state.global_map_sha256,
            "source_fingerprint_sha256": state.fingerprint.hex(),
            "endpoint_label_count": len(state.endpoint_labels),
            "firm_contribution_count": len(state.firm_contributions),
            "paired_contribution_count": len(state.contributions),
            "event_terminal_count": len(state.terminals),
        }
        expected_digest = hashlib.sha256(_post_canonical_bytes(seed)).hexdigest()
        if value.source_id != (
            f"arv2-formal-global-coverage-source-{expected_digest[:24]}"
        ):
            raise FormalInputBundleError("initial coverage source identity changed")
        identity = id(value)
        reference = weakref.ref(
            value,
            lambda ref, key=identity: forget_source(key, ref),
        )
        entry = (
            reference,
            static,
            state,
            state.fingerprint,
            state.topology,
            state.retained_payload_bytes,
            _coverage_source_root_topology(state),
        )
        with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            if identity in source_records or identity in _GLOBAL_COVERAGE_SOURCES:
                raise FormalInputBundleError("coverage source identity was reused")
            source_records[identity] = entry
            _GLOBAL_COVERAGE_SOURCES[identity] = entry

    def require_source(
        value: FormalGlobalComparatorCoverageSource,
        static: bytes,
        deep: bool,
    ) -> _GlobalCoverageSourceState:
        if type(static) is not bytes or static != source_static(value):
            raise FormalInputBundleError("formal coverage source changed")
        with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            return source_entry_locked(value, deep=deep)[0]

    def accumulator_static(
        value: FormalGlobalComparatorCoverageAccumulator,
        state: _GlobalCoverageAccumulatorState,
    ) -> bytes:
        return _post_canonical_bytes({
            "accumulator_id": value.accumulator_id,
            "schema": value.schema,
            "fold_id": value.fold_id,
            "source_view_id": value.source_view_id,
            "source_id": state.source.source_id,
        })

    def accumulator_entry_locked(
        value: FormalGlobalComparatorCoverageAccumulator,
    ) -> tuple[_GlobalCoverageAccumulatorState, tuple[object, ...]]:
        identity = id(value)
        private = accumulator_records.get(identity)
        public = _GLOBAL_COVERAGE_ACCUMULATORS.get(identity)
        try:
            valid = (
                private is not None
                and public is private
                and len(private) == 4
                and private[0]() is value
                and type(private[2]) is _GlobalCoverageAccumulatorState
                and private[1] == accumulator_static(value, private[2])
                and private[2].pid == os.getpid()
                and private[2].owner_thread_id == threading.get_ident()
                and private[3] == _coverage_accumulator_snapshot(private[2])
                and value.schema == GLOBAL_COMPARATOR_COVERAGE_ACCUMULATOR_SCHEMA
                and value.fold_id in FORMAL_PRIMARY_FOLD_IDS
                and value.source_view_id == private[2].source.source_view_id
            )
            if valid:
                source_entry_locked(private[2].source, deep=False)
        except (AttributeError, TypeError, ValueError, IndexError):
            valid = False
        if not valid:
            raise FormalInputBundleError(
                "formal coverage accumulator changed or is not builder-authenticated"
            )
        assert private is not None
        return private[2], private

    def initialize_accumulator(
        value: FormalGlobalComparatorCoverageAccumulator,
        static: bytes,
        state: _GlobalCoverageAccumulatorState,
    ) -> None:
        if (
            type(value) is not FormalGlobalComparatorCoverageAccumulator
            or type(static) is not bytes
            or type(state) is not _GlobalCoverageAccumulatorState
            or static != accumulator_static(value, state)
            or state.pid != os.getpid()
            or state.owner_thread_id != threading.get_ident()
            or value.schema != GLOBAL_COMPARATOR_COVERAGE_ACCUMULATOR_SCHEMA
            or value.fold_id not in FORMAL_PRIMARY_FOLD_IDS
            or value.source_view_id != state.source.source_view_id
            or state.next_session_index != 0
            or state.last_test_session_by_security != {}
            or state.last_session_payload_bytes != 0
            or any(
                getattr(state, name) != 0
                for name in (
                    "firm_active_count",
                    "paired_active_count",
                    "firm_component_count",
                    "retained_component_count",
                    "firm_component_incidence",
                    "retained_component_incidence",
                    "candidate_dates",
                    "capable_dates",
                    "firm_totalized_dates",
                    "global_totalized_dates",
                    "both_constant_dates",
                    "score_refused_dates",
                )
            )
            or state.finalized
            or state.immutable_retained_bytes
            != _coverage_retained_object_graph_bytes(
                state.ordinals, state.expected_sessions
            )
        ):
            raise FormalInputBundleError(
                "initial coverage accumulator authority changed"
            )
        with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            source_entry_locked(state.source, deep=False)
        test_start, test_end = _h20_geometry_for_fold(value.fold_id)[6:8]
        try:
            expected_sessions = tuple(
                item.isoformat()
                for item in trading_sessions(
                    date.fromisoformat(test_start), date.fromisoformat(test_end)
                )
                if item < date.fromisoformat(test_end)
            )
        except (ExchangeCalendarError, ProductionScoringError) as exc:
            raise FormalInputBundleError(
                "initial coverage accumulator NYSE axis changed"
            ) from exc
        if (
            state.expected_sessions != expected_sessions
            or any(item not in state.ordinals for item in expected_sessions)
        ):
            raise FormalInputBundleError(
                "initial coverage accumulator session axis changed"
            )
        seed = {
            "schema": GLOBAL_COMPARATOR_COVERAGE_ACCUMULATOR_SCHEMA,
            "fold_id": value.fold_id,
            "source_id": state.source.source_id,
            "source_view_id": value.source_view_id,
            "h20_test_start": test_start,
            "h20_test_end_exclusive": test_end,
        }
        expected_digest = hashlib.sha256(_post_canonical_bytes(seed)).hexdigest()
        if value.accumulator_id != (
            f"arv2-formal-global-coverage-accumulator-{expected_digest[:24]}"
        ):
            raise FormalInputBundleError(
                "initial coverage accumulator identity changed"
            )
        identity = id(value)
        reference = weakref.ref(
            value,
            lambda ref, key=identity: forget_accumulator(key, ref),
        )
        entry = (
            reference,
            static,
            state,
            _coverage_accumulator_snapshot(state),
        )
        with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            if (
                identity in accumulator_records
                or identity in _GLOBAL_COVERAGE_ACCUMULATORS
            ):
                raise FormalInputBundleError(
                    "coverage accumulator identity was reused"
                )
            accumulator_records[identity] = entry
            _GLOBAL_COVERAGE_ACCUMULATORS[identity] = entry

    def require_accumulator(
        value: FormalGlobalComparatorCoverageAccumulator,
    ) -> _GlobalCoverageAccumulatorState:
        with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            return accumulator_entry_locked(value)[0]

    def record_session(
        value: FormalGlobalComparatorCoverageAccumulator,
        *,
        decision_session: str,
        census_rows: tuple[EligibleSecuritySession, ...],
        final_rows: tuple[FinalDecisionInput, ...],
        final_refusals: tuple[ScoringRefusal, ...],
        maximum_retained_bytes: int,
    ) -> int:
        if type(maximum_retained_bytes) is not int or maximum_retained_bytes <= 0:
            raise FormalInputBundleError(
                "coverage transition retained-byte ceiling changed"
            )
        with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            prior_state, prior_entry = accumulator_entry_locked(value)
            prior_snapshot = prior_entry[3]
        next_state = derive_session(
            value,
            prior_state,
            decision_session=decision_session,
            census_rows=census_rows,
            final_rows=final_rows,
            final_refusals=final_refusals,
        )
        next_snapshot = _coverage_accumulator_snapshot(next_state)
        with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            current_state, current_entry = accumulator_entry_locked(value)
            if (
                current_state is not prior_state
                or current_entry is not prior_entry
                or _coverage_accumulator_snapshot(prior_state) != prior_snapshot
            ):
                raise FormalInputBundleError(
                    "formal coverage accumulator changed during transition"
                )
            next_entry = (
                prior_entry[0], prior_entry[1], next_state, next_snapshot,
            )
            transition_retained_bytes = (
                _coverage_accumulator_transition_retained_bytes(
                    accumulator=value,
                    prior_state=prior_state,
                    prior_snapshot=prior_snapshot,
                    prior_registered=prior_entry,
                    next_state=next_state,
                    next_snapshot=next_snapshot,
                    next_registered=next_entry,
                )
                + sys.getsizeof(accumulator_records)
                + sys.getsizeof(id(value))
            )
            if transition_retained_bytes > maximum_retained_bytes:
                raise FormalInputBundleError(
                    "coverage transition retained graph exceeded reviewed capacity"
                )
            accumulator_records[id(value)] = next_entry
            _GLOBAL_COVERAGE_ACCUMULATORS[id(value)] = next_entry
        return transition_retained_bytes

    def finalize_accumulator(
        value: FormalGlobalComparatorCoverageAccumulator,
        expected_state: _GlobalCoverageAccumulatorState,
    ) -> None:
        with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            state, entry = accumulator_entry_locked(value)
            if (
                state is not expected_state
                or state.finalized
                or state.next_session_index != len(state.expected_sessions)
            ):
                raise FormalInputBundleError(
                    "formal coverage accumulator changed during finalization"
                )
            next_state = dataclasses.replace(state, finalized=True)
            next_entry = (
                entry[0],
                entry[1],
                next_state,
                _coverage_accumulator_snapshot(next_state),
            )
            accumulator_records[id(value)] = next_entry
            _GLOBAL_COVERAGE_ACCUMULATORS[id(value)] = next_entry

    def private_registry_bytes(kind: str, identity: int) -> int:
        with _GLOBAL_COVERAGE_ACCUMULATOR_LOCK:
            if kind == "source":
                records = source_records
            elif kind == "accumulator":
                records = accumulator_records
            else:
                raise FormalInputBundleError("coverage authority kind changed")
            if identity not in records:
                raise FormalInputBundleError("coverage private authority disappeared")
            return sys.getsizeof(records) + sys.getsizeof(identity)

    return (
        initialize_source,
        require_source,
        initialize_accumulator,
        require_accumulator,
        record_session,
        finalize_accumulator,
        private_registry_bytes,
    )
def begin_formal_global_comparator_fold_coverage(
    *,
    fold_id: str,
    signal_arm: SignalArm,
    batch: ProductionInputBatch,
    global_contract: object,
    endpoint_labels: tuple[EndpointLabelEvidence, ...],
) -> FormalGlobalComparatorCoverageAccumulator:
    """Compatibility entrypoint; derive one source then open one fold."""

    source = build_formal_global_comparator_coverage_source(
        signal_arm=signal_arm,
        batch=batch,
        global_contract=global_contract,
        endpoint_labels=endpoint_labels,
    )
    return begin_formal_global_comparator_fold_coverage_from_source(
        fold_id=fold_id,
        source=source,
    )


def _begin_formal_global_comparator_fold_coverage_from_source_impl(
    *,
    fold_id: str,
    source: FormalGlobalComparatorCoverageSource,
    _vault_initialize_accumulator: object,
) -> FormalGlobalComparatorCoverageAccumulator:
    """Open one fold over an already-derived, authenticated view source."""

    source, source_state = _require_global_coverage_source(source)
    geometry = _h20_geometry_for_fold(fold_id)
    test_start, test_end = geometry[6], geometry[7]
    try:
        expected_sessions = tuple(
            item.isoformat()
            for item in trading_sessions(
                date.fromisoformat(test_start), date.fromisoformat(test_end)
            )
            if item < date.fromisoformat(test_end)
        )
        axis_start = min(
            (
                item.eligible_session
                for item in itertools.chain(
                    source_state.firm_contributions,
                    source_state.contributions,
                )
                if item.eligible_session < test_end
            ),
            default=test_start,
        )
        ordinal_sessions = tuple(
            item.isoformat()
            for item in trading_sessions(
                date.fromisoformat(min(axis_start, test_start)),
                date.fromisoformat(test_end),
            )
            if item < date.fromisoformat(test_end)
        )
    except (
        ExchangeCalendarError,
        ProductionScoringError,
        GlobalBenchmarkContractError,
    ) as exc:
        raise FormalInputBundleError("coverage NYSE or contribution axis failed") from exc
    if not expected_sessions:
        raise FormalInputBundleError("coverage H20 fold has no NYSE sessions")
    ordinals = {item: index for index, item in enumerate(ordinal_sessions)}
    if any(
        item not in ordinals
        for item in (
            *expected_sessions,
            *(
                value.eligible_session
                for value in source_state.contributions
                if value.eligible_session < test_end
            ),
        )
    ):
        raise FormalInputBundleError("coverage contribution escaped its NYSE axis")
    seed = {
        "schema": GLOBAL_COMPARATOR_COVERAGE_ACCUMULATOR_SCHEMA,
        "fold_id": fold_id,
        "source_id": source.source_id,
        "source_view_id": source.source_view_id,
        "h20_test_start": test_start,
        "h20_test_end_exclusive": test_end,
    }
    digest = hashlib.sha256(_post_canonical_bytes(seed)).hexdigest()
    value = object.__new__(FormalGlobalComparatorCoverageAccumulator)
    object.__setattr__(
        value,
        "accumulator_id",
        f"arv2-formal-global-coverage-accumulator-{digest[:24]}",
    )
    object.__setattr__(value, "schema", GLOBAL_COMPARATOR_COVERAGE_ACCUMULATOR_SCHEMA)
    object.__setattr__(value, "fold_id", fold_id)
    object.__setattr__(value, "source_view_id", source.source_view_id)
    immutable_retained_bytes = _coverage_retained_object_graph_bytes(
        ordinals,
        expected_sessions,
    )
    state = _GlobalCoverageAccumulatorState(
        source=source,
        ordinals=ordinals,
        expected_sessions=expected_sessions,
        immutable_retained_bytes=immutable_retained_bytes,
        next_session_index=0,
        last_test_session_by_security={},
        last_session_payload_bytes=0,
        firm_active_count=0,
        paired_active_count=0,
        firm_component_count=0,
        retained_component_count=0,
        firm_component_incidence=0,
        retained_component_incidence=0,
        candidate_dates=0,
        capable_dates=0,
        firm_totalized_dates=0,
        global_totalized_dates=0,
        both_constant_dates=0,
        score_refused_dates=0,
        pid=os.getpid(),
        owner_thread_id=threading.get_ident(),
        finalized=False,
    )
    static = _post_canonical_bytes({
        "accumulator_id": value.accumulator_id,
        "schema": value.schema,
        "fold_id": value.fold_id,
        "source_view_id": value.source_view_id,
        "source_id": state.source.source_id,
    })
    _vault_initialize_accumulator(value, static, state)
    return _require_global_coverage_accumulator(value)[0]


def _derive_global_coverage_session_transition(
    value: FormalGlobalComparatorCoverageAccumulator,
    state: _GlobalCoverageAccumulatorState,
    *,
    decision_session: str,
    census_rows: tuple[EligibleSecuritySession, ...],
    final_rows: tuple[FinalDecisionInput, ...],
    final_refusals: tuple[ScoringRefusal, ...],
) -> _GlobalCoverageAccumulatorState:
    """Derive the only legal next session state from authenticated inputs."""

    _source, source_state = _require_global_coverage_source(
        state.source,
        deep=False,
    )
    if state.finalized or state.next_session_index >= len(state.expected_sessions):
        raise FormalInputBundleError("formal coverage accumulator is sealed")
    expected_session = state.expected_sessions[state.next_session_index]
    if type(decision_session) is not str or decision_session != expected_session:
        raise FormalInputBundleError("formal coverage session axis changed")
    if (
        type(census_rows) is not tuple
        or any(type(item) is not EligibleSecuritySession for item in census_rows)
        or type(final_rows) is not tuple
        or any(type(item) is not FinalDecisionInput for item in final_rows)
        or type(final_refusals) is not tuple
        or any(type(item) is not ScoringRefusal for item in final_refusals)
    ):
        raise FormalInputBundleError("formal coverage session types changed")
    signal_arm = source_state.signal_arm
    for item in census_rows:
        item.__post_init__()
        if item.decision_session != decision_session:
            raise FormalInputBundleError("coverage census row crossed a session")
    for item in final_rows:
        item.__post_init__()
        if (
            item.signal_arm is not signal_arm
            or item.fold_id != value.fold_id
            or item.partition is not FoldPartition.TEST
            or item.decision_session != decision_session
        ):
            raise FormalInputBundleError("coverage final row crossed its fold/session")
    for item in final_refusals:
        item.__post_init__()
        if (
            item.signal_arm is not signal_arm
            or item.fold_id != value.fold_id
            or item.partition is not FoldPartition.TEST
            or item.decision_session != decision_session
        ):
            raise FormalInputBundleError("coverage refusal crossed its fold/session")
    security_ids = tuple(item.security_id for item in census_rows)
    if (
        security_ids != tuple(sorted(set(security_ids)))
        or tuple(item.security_id for item in final_rows)
        != tuple(sorted({item.security_id for item in final_rows}))
        or tuple(item.security_id for item in final_refusals)
        != tuple(sorted({item.security_id for item in final_refusals}))
        or set(item.security_id for item in final_rows)
        & set(item.security_id for item in final_refusals)
    ):
        raise FormalInputBundleError("coverage session terminal keys are not exact")

    visible_firm, visible_paired = (
        _formal_global_comparator_coverage_source_visible_inputs(
            state.source,
            decision_session=decision_session,
            security_ids=security_ids,
        )
    )
    firm_active = {item.security_id for item in visible_firm}
    paired_active = {item.security_id for item in visible_paired}
    if not paired_active <= firm_active:
        raise FormalInputBundleError("paired active coverage exceeds firm baseline")
    firm_topologies, paired_topologies = _active_component_topologies(
        visible_firm,
        visible_paired,
    )
    paired_security_ids = tuple(item.security_id for item in final_rows)
    paired_topology_set = set(paired_topologies)
    retained = tuple(item for item in firm_topologies if item in paired_topology_set)

    # The denominator is fixed before score dispersion.  A joint sector,
    # control, or model refusal for an otherwise complete census key is a
    # score-capability failure and remains charged to coverage; it cannot make
    # the candidate date disappear.  A missing prerequisite census terminal
    # still prevents candidacy because its key is outside ``census_rows``.
    refusal_security_ids = tuple(
        item.security_id for item in final_refusals
    )
    candidate = _is_preoutcome_candidate_date(
        security_ids,
        paired_security_ids,
        refusal_security_ids,
    )
    complete_scores = (
        candidate
        and not final_refusals
        and paired_security_ids == security_ids
    )
    capable = False
    both_constant = False
    firm_totalized = False
    global_totalized = False
    if complete_scores:
        firm_scores = {item.firm_specific_score for item in final_rows}
        global_scores = {item.global_score for item in final_rows}
        both_constant = len(firm_scores) == 1 and len(global_scores) == 1
        capable = not both_constant
    if candidate:
        by_security: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        for item in visible_paired:
            age = state.ordinals[decision_session] - state.ordinals[item.eligible_session]
            decay = _decay(age)
            with analyst_decimal_context():
                by_security[item.security_id].append((
                    _fraction_decimal(item.firm_delta) * decay,
                    _fraction_decimal(item.global_delta) * decay,
                ))
        sector_members: dict[str, list[str]] = defaultdict(list)
        for census in census_rows:
            sector_members[census.sector_id].append(census.security_id)
        for members in sector_members.values():
            if len(members) < 20 or sum(item in by_security for item in members) < 5:
                continue
            firm_values = tuple(
                _stable_sum(value[0] for value in by_security.get(item, ()))
                for item in members
            )
            global_values = tuple(
                _stable_sum(value[1] for value in by_security.get(item, ()))
                for item in members
            )
            firm_totalized = firm_totalized or min(firm_values) == max(firm_values)
            global_totalized = (
                global_totalized or min(global_values) == max(global_values)
            )

    last_sessions = dict(state.last_test_session_by_security)
    last_session_payload_bytes = state.last_session_payload_bytes
    for security_id in security_ids:
        previous_session = last_sessions.get(security_id)
        if previous_session is None:
            last_session_payload_bytes += sys.getsizeof(security_id)
        else:
            last_session_payload_bytes -= sys.getsizeof(previous_session)
        last_session_payload_bytes += sys.getsizeof(decision_session)
        last_sessions[security_id] = decision_session
    # All calculations above are side-effect free.  Commit the session only
    # after it has completely validated so a refused call cannot partly count.
    next_state = dataclasses.replace(
        state,
        last_test_session_by_security=last_sessions,
        last_session_payload_bytes=last_session_payload_bytes,
        firm_active_count=state.firm_active_count + len(firm_active),
        paired_active_count=state.paired_active_count + len(paired_active),
        firm_component_count=state.firm_component_count + len(firm_topologies),
        retained_component_count=(
            state.retained_component_count + len(retained)
        ),
        firm_component_incidence=(
            state.firm_component_incidence
            + sum(len(item[0]) for item in firm_topologies)
        ),
        retained_component_incidence=(
            state.retained_component_incidence
            + sum(len(item[0]) for item in retained)
        ),
        candidate_dates=state.candidate_dates + int(candidate),
        capable_dates=state.capable_dates + int(capable),
        firm_totalized_dates=(
            state.firm_totalized_dates + int(firm_totalized)
        ),
        global_totalized_dates=(
            state.global_totalized_dates + int(global_totalized)
        ),
        both_constant_dates=state.both_constant_dates + int(both_constant),
        score_refused_dates=(
            state.score_refused_dates + int(candidate and not complete_scores)
        ),
        next_session_index=state.next_session_index + 1,
    )
    return next_state


def _record_formal_global_comparator_coverage_session_impl(
    accumulator: FormalGlobalComparatorCoverageAccumulator,
    *,
    decision_session: str,
    census_rows: tuple[EligibleSecuritySession, ...],
    final_rows: tuple[FinalDecisionInput, ...],
    final_refusals: tuple[ScoringRefusal, ...],
    maximum_retained_bytes: int,
    _vault_record_session: object,
) -> int:
    """Consume exactly one complete H20 TEST session without retaining it."""

    if type(accumulator) is not FormalGlobalComparatorCoverageAccumulator:
        raise FormalInputBundleError("formal coverage accumulator changed type")
    return _vault_record_session(
        accumulator,
        decision_session=decision_session,
        census_rows=census_rows,
        final_rows=final_rows,
        final_refusals=final_refusals,
        maximum_retained_bytes=maximum_retained_bytes,
    )


def _coverage_record_without_identity(
    value: FormalGlobalComparatorCoverage,
) -> dict[str, object]:
    record = value.to_record(include_identity=False)
    record.pop("schema")
    return record


def _build_global_coverage_value(
    *,
    schema: str,
    scope_id: str,
    source_view_id: str,
    fold_ids: tuple[str, ...],
    result_bindings: tuple[ScoringResultBinding, ...],
    h20_test_intervals: tuple[tuple[str, str, str], ...],
    ledgers: tuple[FormalCoverageLedger, ...],
    endpoint_status_counts: tuple[tuple[str, int], ...],
    endpoint_pair_status_counts: tuple[tuple[str, int], ...],
    direction_status_counts: tuple[tuple[str, int], ...],
    raw_canonical_label_counts: tuple[tuple[str, str, str, int], ...],
    date_diagnostic_counts: tuple[tuple[str, int], ...],
    diagnostic_ratios: tuple[FormalCoverageDiagnosticRatio, ...],
) -> FormalGlobalComparatorCoverage:
    ready = all(item.passes for item in ledgers)
    reasons = tuple(
        f"{item.ledger_id}:{reason}"
        for item in ledgers
        for reason in item.reasons
    )
    (
        raw_canonical_label_counts,
        raw_label_disposition_counts,
        canonical_label_disposition_counts,
        raw_form_collision_counts,
    ) = _global_label_diagnostics(raw_canonical_label_counts)
    attribution_rule = _GLOBAL_COVERAGE_ATTRIBUTION_RULE
    placeholder = FormalGlobalComparatorCoverage(
        coverage_id="",
        coverage_sha256="",
        schema=schema,
        scope_id=scope_id,
        source_view_id=source_view_id,
        fold_ids=fold_ids,
        result_bindings=result_bindings,
        h20_test_intervals=h20_test_intervals,
        ledgers=ledgers,
        endpoint_status_counts=endpoint_status_counts,
        endpoint_pair_status_counts=endpoint_pair_status_counts,
        direction_status_counts=direction_status_counts,
        raw_canonical_label_counts=raw_canonical_label_counts,
        raw_label_disposition_counts=raw_label_disposition_counts,
        canonical_label_disposition_counts=canonical_label_disposition_counts,
        raw_form_collision_counts=raw_form_collision_counts,
        date_diagnostic_counts=date_diagnostic_counts,
        diagnostic_ratios=diagnostic_ratios,
        ready=ready,
        reasons=reasons,
        attribution_rule=attribution_rule,
        outcome_free=True,
        _canonical_document=b"",
    )
    coverage_id, digest, payload = _post_identified(
        prefix="arv2-formal-global-comparator-coverage-",
        schema=schema,
        record=_coverage_record_without_identity(placeholder),
    )
    value = dataclasses.replace(
        placeholder,
        coverage_id=coverage_id,
        coverage_sha256=digest,
        _canonical_document=payload,
    )
    return require_formal_global_comparator_coverage(value)


def _finish_formal_global_comparator_fold_coverage_impl(
    accumulator: FormalGlobalComparatorCoverageAccumulator,
    *,
    result_binding: ScoringResultBinding,
    _vault_finalize_accumulator: object,
) -> FormalGlobalComparatorCoverage:
    """Seal one complete H20 axis and derive its endpoint diagnostics."""

    value, state = _require_global_coverage_accumulator(accumulator)
    if (
        state.finalized
        or state.next_session_index != len(state.expected_sessions)
    ):
        raise FormalInputBundleError("formal coverage accumulator is incomplete or sealed")
    _require_scoring_result_binding(
        result_binding,
        expected_fold_id=value.fold_id,
    )
    _source, source_state = _require_global_coverage_source(state.source)
    label_by_hash = source_state.label_by_hash
    resolution_by_raw = {
        item.raw_label: item for item in source_state.label_resolutions
    }
    attributed_hashes = tuple(sorted({
        row_sha256
        for contribution in source_state.firm_contributions
        if contribution.security_id in state.last_test_session_by_security
        and contribution.eligible_session
        <= state.last_test_session_by_security[contribution.security_id]
        for row_sha256 in contribution.linked_c2_row_sha256s
    }))
    if set(attributed_hashes) - set(source_state.action_by_hash):
        raise FormalInputBundleError("firm baseline event lineage disappeared")
    endpoint_counts: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    direction_counts: Counter[str] = Counter()
    raw_canonical_counts: Counter[tuple[str, str, str]] = Counter()
    mapped_and_admissible = 0
    for row_sha256 in attributed_hashes:
        labels = label_by_hash.get(row_sha256)
        if labels is None:
            raise FormalInputBundleError("coverage endpoint evidence disappeared")
        previous = resolution_by_raw[labels.raw_previous_label]
        current = resolution_by_raw[labels.raw_current_label]
        previous_status = previous.status
        current_status = current.status
        endpoint_counts[previous_status] += 1
        endpoint_counts[current_status] += 1
        raw_canonical_counts[_cached_raw_canonical_label_key(previous)] += 1
        raw_canonical_counts[_cached_raw_canonical_label_key(current)] += 1
        pair_status = _pair_status(previous_status, current_status)
        pair_counts[pair_status] += 1
        if pair_status != "mapped":
            continue
        if (
            previous.score_numerator is None
            or previous.score_denominator is None
            or current.score_numerator is None
            or current.score_denominator is None
        ):
            raise FormalInputBundleError(
                "mapped endpoint pair lost its exact score"
            )
        delta = Fraction(
            current.score_numerator,
            current.score_denominator,
        ) - Fraction(
            previous.score_numerator,
            previous.score_denominator,
        )
        if delta == 0:
            direction_counts["zero_delta"] += 1
            mapped_and_admissible += 1
        elif (
            (source_state.action_by_hash[row_sha256] == "upgrades" and delta > 0)
            or (source_state.action_by_hash[row_sha256] == "downgrades" and delta < 0)
        ):
            direction_counts["expected_sign"] += 1
            mapped_and_admissible += 1
        else:
            direction_counts["opposite_sign"] += 1

    ledgers = (
        _coverage_ledger(
            "endpoint_pair_mapping", mapped_and_admissible, len(attributed_hashes)
        ),
        _coverage_ledger(
            "active_security_date_rows",
            state.paired_active_count,
            state.firm_active_count,
        ),
        _coverage_ledger(
            "common_event_components",
            state.retained_component_count,
            state.firm_component_count,
        ),
        _coverage_ledger(
            "component_member_incidence",
            state.retained_component_incidence,
            state.firm_component_incidence,
        ),
        _coverage_ledger(
            "score_capable_dates", state.capable_dates, state.candidate_dates
        ),
    )
    endpoint_status_counts = tuple(
        (name, endpoint_counts[name]) for name in _ENDPOINT_STATUS_IDS
    )
    endpoint_pair_status_counts = tuple(
        (name, pair_counts[name]) for name in _ENDPOINT_STATUS_IDS
    )
    direction_status_counts = tuple(
        (name, direction_counts[name]) for name in _DIRECTION_STATUS_IDS
    )
    date_diagnostic_counts = (
        ("firm_totalized_zero_dates", state.firm_totalized_dates),
        ("global_totalized_zero_dates", state.global_totalized_dates),
        ("both_arms_constant_dates", state.both_constant_dates),
        ("score_refused_candidate_dates", state.score_refused_dates),
        ("preoutcome_candidate_dates", state.candidate_dates),
    )
    mapped_pairs = pair_counts["mapped"]
    result = _build_global_coverage_value(
        schema=GLOBAL_COMPARATOR_COVERAGE_SCHEMA,
        scope_id=value.fold_id,
        source_view_id=value.source_view_id,
        fold_ids=(value.fold_id,),
        result_bindings=(result_binding,),
        h20_test_intervals=((
            value.fold_id,
            _h20_geometry_for_fold(value.fold_id)[6],
            _h20_geometry_for_fold(value.fold_id)[7],
        ),),
        ledgers=ledgers,
        endpoint_status_counts=endpoint_status_counts,
        endpoint_pair_status_counts=endpoint_pair_status_counts,
        direction_status_counts=direction_status_counts,
        raw_canonical_label_counts=tuple(
            (*key, count)
            for key, count in sorted(raw_canonical_counts.items())
        ),
        date_diagnostic_counts=date_diagnostic_counts,
        diagnostic_ratios=(
            _coverage_ratio(
                "global_tier_collapse_zero_share",
                direction_counts["zero_delta"], mapped_pairs,
            ),
            _coverage_ratio(
                "global_direction_conflict_share",
                direction_counts["opposite_sign"], mapped_pairs,
            ),
            _coverage_ratio(
                "firm_totalized_zero_date_share",
                state.firm_totalized_dates, state.candidate_dates,
            ),
            _coverage_ratio(
                "global_totalized_zero_date_share",
                state.global_totalized_dates, state.candidate_dates,
            ),
            _coverage_ratio(
                "both_arms_constant_date_share",
                state.both_constant_dates, state.candidate_dates,
            ),
        ),
    )
    _vault_finalize_accumulator(value, state)
    return result


def require_formal_global_comparator_coverage(
    value: FormalGlobalComparatorCoverage,
) -> FormalGlobalComparatorCoverage:
    """Validate a content-addressed, outcome-free comparator coverage record."""

    if type(value) is not FormalGlobalComparatorCoverage:
        raise FormalInputBundleError("formal comparator coverage changed type")
    if value.schema not in {
        GLOBAL_COMPARATOR_COVERAGE_SCHEMA,
        GLOBAL_COMPARATOR_POOLED_COVERAGE_SCHEMA,
    }:
        raise FormalInputBundleError("formal comparator coverage schema changed")
    _post_id(value.scope_id, "coverage scope_id")
    if value.source_view_id not in {CURRENT_VIEW_LABEL, CENSORED_VIEW_LABEL}:
        raise FormalInputBundleError("formal comparator coverage view changed")
    if (
        value.schema == GLOBAL_COMPARATOR_COVERAGE_SCHEMA
        and (len(value.fold_ids) != 1 or value.scope_id != value.fold_ids[0])
    ) or (
        value.schema == GLOBAL_COMPARATOR_POOLED_COVERAGE_SCHEMA
        and (value.scope_id != "pooled" or value.fold_ids != FORMAL_PRIMARY_FOLD_IDS)
    ):
        raise FormalInputBundleError("formal comparator coverage scope changed")
    if (
        type(value.fold_ids) is not tuple
        or not value.fold_ids
        or value.fold_ids != tuple(dict.fromkeys(value.fold_ids))
        or any(item not in FORMAL_PRIMARY_FOLD_IDS for item in value.fold_ids)
        or type(value.result_bindings) is not tuple
        or len(value.result_bindings) != len(value.fold_ids)
        or type(value.h20_test_intervals) is not tuple
        or len(value.h20_test_intervals) != len(value.fold_ids)
        or type(value.ledgers) is not tuple
        or tuple(item.ledger_id for item in value.ledgers)
        != _GLOBAL_COVERAGE_LEDGER_IDS
    ):
        raise FormalInputBundleError("formal comparator coverage fold census changed")
    for fold_id, binding, interval in zip(
        value.fold_ids,
        value.result_bindings,
        value.h20_test_intervals,
        strict=True,
    ):
        _require_scoring_result_binding(binding, expected_fold_id=fold_id)
        if (
            type(interval) is not tuple
            or len(interval) != 3
            or interval[0] != fold_id
        ):
            raise FormalInputBundleError("formal coverage result/fold binding changed")
        geometry = _h20_geometry_for_fold(fold_id)
        if interval != (fold_id, geometry[6], geometry[7]):
            raise FormalInputBundleError("formal coverage H20 interval changed")
    for item in value.ledgers:
        if type(item) is not FormalCoverageLedger:
            raise FormalInputBundleError("formal coverage ledger changed type")
        item.__post_init__()
    expected_named_counts = (
        (value.endpoint_status_counts, _ENDPOINT_STATUS_IDS),
        (value.endpoint_pair_status_counts, _ENDPOINT_STATUS_IDS),
        (value.direction_status_counts, _DIRECTION_STATUS_IDS),
        (value.date_diagnostic_counts, _DATE_DIAGNOSTIC_IDS),
    )
    for counts, names in expected_named_counts:
        if (
            type(counts) is not tuple
            or tuple(item[0] for item in counts) != names
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[1]) is not int
                or item[1] < 0
                for item in counts
            )
        ):
            raise FormalInputBundleError("formal coverage diagnostic census changed")
    (
        normalized_label_counts,
        raw_label_counts,
        canonical_label_counts,
        collision_counts,
    ) = _global_label_diagnostics(value.raw_canonical_label_counts)
    if (
        value.raw_canonical_label_counts != normalized_label_counts
        or value.raw_label_disposition_counts != raw_label_counts
        or value.canonical_label_disposition_counts != canonical_label_counts
        or value.raw_form_collision_counts != collision_counts
        or tuple(item[0] for item in value.raw_form_collision_counts)
        != _RAW_FORM_COLLISION_COUNT_IDS
    ):
        raise FormalInputBundleError("formal global-label diagnostics changed")
    if (
        type(value.diagnostic_ratios) is not tuple
        or any(type(item) is not FormalCoverageDiagnosticRatio for item in value.diagnostic_ratios)
        or type(value.ready) is not bool
        or value.ready is not all(item.passes for item in value.ledgers)
        or type(value.reasons) is not tuple
        or value.reasons != tuple(
            f"{item.ledger_id}:{reason}"
            for item in value.ledgers
            for reason in item.reasons
        )
        or value.outcome_free is not True
    ):
        raise FormalInputBundleError("formal coverage aggregate changed")
    for ratio in value.diagnostic_ratios:
        ratio.__post_init__()
    if tuple(item.ratio_id for item in value.diagnostic_ratios) != (
        "global_tier_collapse_zero_share",
        "global_direction_conflict_share",
        "firm_totalized_zero_date_share",
        "global_totalized_zero_date_share",
        "both_arms_constant_date_share",
    ):
        raise FormalInputBundleError("formal coverage diagnostic ratio census changed")
    ledgers = {item.ledger_id: item for item in value.ledgers}
    endpoint = dict(value.endpoint_status_counts)
    pairs = dict(value.endpoint_pair_status_counts)
    directions = dict(value.direction_status_counts)
    dates = dict(value.date_diagnostic_counts)
    expected_ratios = (
        (directions["zero_delta"], pairs["mapped"]),
        (directions["opposite_sign"], pairs["mapped"]),
        (dates["firm_totalized_zero_dates"], dates["preoutcome_candidate_dates"]),
        (dates["global_totalized_zero_dates"], dates["preoutcome_candidate_dates"]),
        (dates["both_arms_constant_dates"], dates["preoutcome_candidate_dates"]),
    )
    if (
        sum(endpoint.values()) != 2 * sum(pairs.values())
        or sum(item[3] for item in value.raw_canonical_label_counts)
        != sum(endpoint.values())
        or Counter({
            status: sum(
                count
                for _raw_hash, _canonical_hash, item_status, count
                in value.raw_canonical_label_counts
                if item_status == status
            )
            for status in _ENDPOINT_STATUS_IDS
        }) != Counter(endpoint)
        or sum(directions.values()) != pairs["mapped"]
        or ledgers["endpoint_pair_mapping"].denominator != sum(pairs.values())
        or ledgers["endpoint_pair_mapping"].numerator
        != directions["expected_sign"] + directions["zero_delta"]
        or ledgers["score_capable_dates"].denominator
        != dates["preoutcome_candidate_dates"]
        or (
            ledgers["score_capable_dates"].numerator
            + dates["both_arms_constant_dates"]
            + dates["score_refused_candidate_dates"]
            != dates["preoutcome_candidate_dates"]
        )
        or any(
            (item.numerator, item.denominator) != expected
            for item, expected in zip(
                value.diagnostic_ratios, expected_ratios, strict=True
            )
        )
    ):
        raise FormalInputBundleError("formal coverage diagnostic reconciliation failed")
    if value.attribution_rule != _GLOBAL_COVERAGE_ATTRIBUTION_RULE:
        raise FormalInputBundleError("formal coverage event attribution changed")
    coverage_id, digest, payload = _post_identified(
        prefix="arv2-formal-global-comparator-coverage-",
        schema=value.schema,
        record=_coverage_record_without_identity(value),
    )
    if (
        value.coverage_id != coverage_id
        or value.coverage_sha256 != digest
        or value._canonical_document != payload
    ):
        raise FormalInputBundleError("formal comparator coverage identity changed")
    return value


def build_formal_global_comparator_fold_coverage_from_inputs(
    *,
    fold_id: str,
    result_binding: ScoringResultBinding,
    signal_arm: SignalArm,
    batch: ProductionInputBatch,
    global_contract: object,
    endpoint_labels: tuple[EndpointLabelEvidence, ...],
    census_rows: tuple[EligibleSecuritySession, ...],
    final_rows: tuple[FinalDecisionInput, ...],
    final_refusals: tuple[ScoringRefusal, ...],
) -> FormalGlobalComparatorCoverage:
    """Derive one H20 fold record from exact authenticated streamed parents.

    The returned value is arithmetic evidence only.  The enclosing scoring
    projection must bind it to its own authenticated source and result roots;
    this helper grants no authority to caller-authored rows or counts.
    """

    try:
        require_production_input_batch(batch)
        require_loaded_global_benchmark_contract(global_contract)
    except (ProductionInputError, GlobalBenchmarkContractError) as exc:
        raise FormalInputBundleError("coverage source parent is not authentic") from exc
    if (
        type(signal_arm) is not SignalArm
        or batch.signal_arm is not signal_arm
        or type(endpoint_labels) is not tuple
        or any(type(item) is not EndpointLabelEvidence for item in endpoint_labels)
        or type(census_rows) is not tuple
        or any(type(item) is not EligibleSecuritySession for item in census_rows)
        or type(final_rows) is not tuple
        or any(type(item) is not FinalDecisionInput for item in final_rows)
        or type(final_refusals) is not tuple
        or any(type(item) is not ScoringRefusal for item in final_refusals)
    ):
        raise FormalInputBundleError("coverage streamed input types changed")
    _require_scoring_result_binding(result_binding, expected_fold_id=fold_id)
    for item in endpoint_labels:
        item.__post_init__()
    for item in census_rows:
        item.__post_init__()
    for item in final_rows:
        item.__post_init__()
    for item in final_refusals:
        item.__post_init__()
    source = build_formal_global_comparator_coverage_source(
        signal_arm=signal_arm,
        batch=batch,
        global_contract=global_contract,
        endpoint_labels=endpoint_labels,
    )
    _source, source_state = _require_global_coverage_source(source)
    geometry = _h20_geometry_for_fold(fold_id)
    test_start, test_end = geometry[6], geometry[7]
    source_view_id = _source_view(signal_arm)
    census_by_session: dict[str, tuple[object, ...]] = {}
    try:
        sessions = tuple(
            item.isoformat()
            for item in trading_sessions(
                date.fromisoformat(test_start), date.fromisoformat(test_end)
            )
            if item < date.fromisoformat(test_end)
        )
    except ExchangeCalendarError as exc:
        raise FormalInputBundleError("coverage H20 session axis changed") from exc
    for session in sessions:
        census_by_session[session] = tuple(
            item
            for item in census_rows
            if item.decision_session == session
        )

    label_by_hash = source_state.label_by_hash
    resolution_by_raw = {
        item.raw_label: item for item in source_state.label_resolutions
    }

    last_test_session_by_security: dict[str, str] = {}
    for session, census_rows in census_by_session.items():
        for census in census_rows:
            last_test_session_by_security[census.security_id] = max(
                session,
                last_test_session_by_security.get(census.security_id, session),
            )
    firm_contributions = tuple(
        item for item in source_state.firm_contributions
        if item.eligible_session < test_end
    )
    attributed_hashes = tuple(sorted({
        row_sha256
        for contribution in firm_contributions
        if contribution.security_id in last_test_session_by_security
        and contribution.eligible_session
        <= last_test_session_by_security[contribution.security_id]
        for row_sha256 in contribution.linked_c2_row_sha256s
    }))
    if set(attributed_hashes) - set(source_state.action_by_hash):
        raise FormalInputBundleError("firm baseline event lineage disappeared")
    endpoint_counts: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    direction_counts: Counter[str] = Counter()
    raw_canonical_counts: Counter[tuple[str, str, str]] = Counter()
    mapped_and_admissible = 0
    for row_sha256 in attributed_hashes:
        labels = label_by_hash[row_sha256]
        previous = resolution_by_raw[labels.raw_previous_label]
        current = resolution_by_raw[labels.raw_current_label]
        previous_status = previous.status
        current_status = current.status
        endpoint_counts[previous_status] += 1
        endpoint_counts[current_status] += 1
        raw_canonical_counts[_cached_raw_canonical_label_key(previous)] += 1
        raw_canonical_counts[_cached_raw_canonical_label_key(current)] += 1
        pair_status = _pair_status(previous_status, current_status)
        pair_counts[pair_status] += 1
        if pair_status != "mapped":
            continue
        if (
            previous.score_numerator is None
            or previous.score_denominator is None
            or current.score_numerator is None
            or current.score_denominator is None
        ):
            raise FormalInputBundleError(
                "mapped endpoint pair changed type after classification"
            )
        delta = Fraction(
            current.score_numerator, current.score_denominator
        ) - Fraction(previous.score_numerator, previous.score_denominator)
        if delta == 0:
            direction_counts["zero_delta"] += 1
            mapped_and_admissible += 1
        elif (
            (source_state.action_by_hash[row_sha256] == "upgrades" and delta > 0)
            or (
                source_state.action_by_hash[row_sha256] == "downgrades"
                and delta < 0
            )
        ):
            direction_counts["expected_sign"] += 1
            mapped_and_admissible += 1
        else:
            direction_counts["opposite_sign"] += 1

    result_rows = tuple(
        item
        for item in final_rows
        if item.signal_arm is signal_arm
        and item.partition is FoldPartition.TEST
        and test_start <= item.decision_session < test_end
    )
    result_refusals = tuple(
        item
        for item in final_refusals
        if item.signal_arm is signal_arm
        and item.partition is FoldPartition.TEST
        and test_start <= item.decision_session < test_end
    )
    accepted_by_session: dict[str, tuple[FinalDecisionInput, ...]] = {
        session: tuple(
            item for item in result_rows if item.decision_session == session
        )
        for session in sessions
    }
    refusals_by_session: dict[str, tuple[ScoringRefusal, ...]] = {
        session: tuple(
            item for item in result_refusals if item.decision_session == session
        )
        for session in sessions
    }

    firm_active_count = 0
    paired_active_count = 0
    firm_components: list[
        tuple[
            str,
            tuple[str, ...],
            tuple[str, ...],
            tuple[tuple[str, str], ...],
        ]
    ] = []
    paired_components: set[
        tuple[
            str,
            tuple[str, ...],
            tuple[str, ...],
            tuple[tuple[str, str], ...],
        ]
    ] = set()
    candidate_dates = 0
    capable_dates = 0
    firm_totalized_dates = 0
    global_totalized_dates = 0
    both_constant_dates = 0
    score_refused_dates = 0

    try:
        contributions = tuple(
            item for item in source_state.contributions
            if item.eligible_session < test_end
        )
        axis_start = min(
            (item.eligible_session for item in contributions),
            default=test_start,
        )
        ordinal_axis = tuple(
            item.isoformat()
            for item in trading_sessions(
                date.fromisoformat(min(axis_start, test_start)),
                date.fromisoformat(test_end),
            )
            if item < date.fromisoformat(test_end)
        )
        ordinals = {item: index for index, item in enumerate(ordinal_axis)}
        if any(
            item not in ordinals
            for item in (
                *sessions,
                *(value.eligible_session for value in contributions),
            )
        ):
            raise FormalInputBundleError(
                "coverage contribution escaped its NYSE axis"
            )
    except (
        ExchangeCalendarError,
        ProductionScoringError,
        GlobalBenchmarkContractError,
    ) as exc:
        raise FormalInputBundleError("coverage contribution census changed") from exc

    for session in sessions:
        census_rows = census_by_session[session]
        security_ids = tuple(item.security_id for item in census_rows)
        security_set = set(security_ids)
        visible_firm = tuple(
            item for item in firm_contributions
            if item.security_id in security_set and item.eligible_session <= session
        )
        firm_active = {
            item.security_id for item in visible_firm
        }
        accepted = accepted_by_session[session]
        visible_paired = tuple(
            item
            for item in contributions
            if item.security_id in security_set
            and item.eligible_session <= session
        )
        paired_active = {item.security_id for item in visible_paired}
        if not paired_active <= firm_active:
            raise FormalInputBundleError("paired active coverage exceeds firm baseline")
        firm_active_count += len(firm_active)
        paired_active_count += len(paired_active)

        firm_topologies, paired_topologies_for_session = (
            _active_component_topologies(visible_firm, visible_paired)
        )
        firm_components.extend(
            (session, securities, events, edges)
            for securities, events, edges in firm_topologies
        )
        paired_components.update(
            (session, securities, events, edges)
            for securities, events, edges in paired_topologies_for_session
        )

        accepted_security_ids = tuple(sorted(
            item.security_id for item in accepted
        ))
        refusal_security_ids = tuple(sorted(
            item.security_id for item in refusals_by_session[session]
        ))
        candidate = _is_preoutcome_candidate_date(
            security_ids,
            accepted_security_ids,
            refusal_security_ids,
        )
        complete_scores = (
            candidate
            and not refusals_by_session[session]
            and accepted_security_ids == security_ids
        )
        if candidate:
            candidate_dates += 1
            score_refused_dates += int(not complete_scores)
        if complete_scores:
            firm_scores = {item.firm_specific_score for item in accepted}
            global_scores = {item.global_score for item in accepted}
            if len(firm_scores) == 1 and len(global_scores) == 1:
                both_constant_dates += 1
            else:
                capable_dates += 1
        if candidate:
            by_security: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
            for item in visible_paired:
                age = ordinals[session] - ordinals[item.eligible_session]
                decay = _decay(age)
                with analyst_decimal_context():
                    by_security[item.security_id].append((
                        _fraction_decimal(item.firm_delta) * decay,
                        _fraction_decimal(item.global_delta) * decay,
                    ))
            sector_members: dict[str, list[str]] = defaultdict(list)
            for census in census_rows:
                sector_members[census.sector_id].append(census.security_id)
            firm_totalized = False
            global_totalized = False
            for members in sector_members.values():
                if len(members) < 20 or sum(item in by_security for item in members) < 5:
                    continue
                firm_values = tuple(
                    _stable_sum(value[0] for value in by_security.get(item, ()))
                    for item in members
                )
                global_values = tuple(
                    _stable_sum(value[1] for value in by_security.get(item, ()))
                    for item in members
                )
                firm_totalized = firm_totalized or min(firm_values) == max(firm_values)
                global_totalized = (
                    global_totalized or min(global_values) == max(global_values)
                )
            firm_totalized_dates += int(firm_totalized)
            global_totalized_dates += int(global_totalized)

    # Exact component topology, not merely member overlap, defines retention.
    retained_components = tuple(
        item for item in firm_components if item in paired_components
    )
    firm_component_incidence = sum(len(item[1]) for item in firm_components)
    retained_component_incidence = sum(len(item[1]) for item in retained_components)
    ledgers = (
        _coverage_ledger(
            "endpoint_pair_mapping", mapped_and_admissible, len(attributed_hashes)
        ),
        _coverage_ledger(
            "active_security_date_rows", paired_active_count, firm_active_count
        ),
        _coverage_ledger(
            "common_event_components", len(retained_components), len(firm_components)
        ),
        _coverage_ledger(
            "component_member_incidence",
            retained_component_incidence,
            firm_component_incidence,
        ),
        _coverage_ledger("score_capable_dates", capable_dates, candidate_dates),
    )
    endpoint_status_counts = tuple(
        (name, endpoint_counts[name]) for name in _ENDPOINT_STATUS_IDS
    )
    endpoint_pair_status_counts = tuple(
        (name, pair_counts[name]) for name in _ENDPOINT_STATUS_IDS
    )
    direction_status_counts = tuple(
        (name, direction_counts[name]) for name in _DIRECTION_STATUS_IDS
    )
    date_diagnostic_counts = (
        ("firm_totalized_zero_dates", firm_totalized_dates),
        ("global_totalized_zero_dates", global_totalized_dates),
        ("both_arms_constant_dates", both_constant_dates),
        ("score_refused_candidate_dates", score_refused_dates),
        ("preoutcome_candidate_dates", candidate_dates),
    )
    mapped_pairs = pair_counts["mapped"]
    diagnostic_ratios = (
        _coverage_ratio(
            "global_tier_collapse_zero_share",
            direction_counts["zero_delta"],
            mapped_pairs,
        ),
        _coverage_ratio(
            "global_direction_conflict_share",
            direction_counts["opposite_sign"],
            mapped_pairs,
        ),
        _coverage_ratio(
            "firm_totalized_zero_date_share", firm_totalized_dates, candidate_dates
        ),
        _coverage_ratio(
            "global_totalized_zero_date_share", global_totalized_dates, candidate_dates
        ),
        _coverage_ratio(
            "both_arms_constant_date_share", both_constant_dates, candidate_dates
        ),
    )
    return _build_global_coverage_value(
        schema=GLOBAL_COMPARATOR_COVERAGE_SCHEMA,
        scope_id=fold_id,
        source_view_id=source_view_id,
        fold_ids=(fold_id,),
        result_bindings=(result_binding,),
        h20_test_intervals=((fold_id, test_start, test_end),),
        ledgers=ledgers,
        endpoint_status_counts=endpoint_status_counts,
        endpoint_pair_status_counts=endpoint_pair_status_counts,
        direction_status_counts=direction_status_counts,
        raw_canonical_label_counts=tuple(
            (*key, count)
            for key, count in sorted(raw_canonical_counts.items())
        ),
        date_diagnostic_counts=date_diagnostic_counts,
        diagnostic_ratios=diagnostic_ratios,
    )


def _fold_global_comparator_coverage(
    result: ProductionScoringResult,
    signal_arm: SignalArm,
) -> FormalGlobalComparatorCoverage:
    require_production_scoring_result(result)
    authority = result.precontrol_batch.authority
    batch = (
        authority.current_batch
        if signal_arm is SignalArm.CURRENT_VINTAGE
        else authority.censored_batch
    )
    return build_formal_global_comparator_fold_coverage_from_inputs(
        fold_id=result.precontrol_batch.fold.fold_id,
        result_binding=_result_binding(result),
        signal_arm=signal_arm,
        batch=batch,
        global_contract=authority.global_contract,
        endpoint_labels=authority.endpoint_labels,
        census_rows=authority.census_rows,
        final_rows=result.rows,
        final_refusals=result.refusals,
    )


def build_formal_global_comparator_fold_coverages(
    result: ProductionScoringResult,
) -> tuple[FormalGlobalComparatorCoverage, FormalGlobalComparatorCoverage]:
    """Derive both accepted-risk-view H20 ledgers from one authentic result."""

    try:
        require_production_scoring_result(result)
        return tuple(
            _fold_global_comparator_coverage(result, arm) for arm in SignalArm
        )
    except (ProductionScoringError, GlobalBenchmarkContractError) as exc:
        raise FormalInputBundleError(
            "formal global comparator coverage parent is not authentic"
        ) from exc


def pool_formal_global_comparator_coverages(
    values: tuple[FormalGlobalComparatorCoverage, ...],
) -> FormalGlobalComparatorCoverage:
    """Pool six fold records by exact integer addition, never ratio averaging."""

    if (
        type(values) is not tuple
        or len(values) != len(FORMAL_PRIMARY_FOLD_IDS)
        or any(type(item) is not FormalGlobalComparatorCoverage for item in values)
    ):
        raise FormalInputBundleError("pooled comparator coverage needs six folds")
    for item in values:
        require_formal_global_comparator_coverage(item)
        if item.schema != GLOBAL_COMPARATOR_COVERAGE_SCHEMA or len(item.fold_ids) != 1:
            raise FormalInputBundleError("pooled comparator coverage parent is not a fold")
    source_view_id = values[0].source_view_id
    if (
        tuple(item.fold_ids[0] for item in values) != FORMAL_PRIMARY_FOLD_IDS
        or any(item.source_view_id != source_view_id for item in values)
    ):
        raise FormalInputBundleError("pooled comparator coverage axis changed")
    ledger_by_id = {
        ledger_id: _coverage_ledger(
            ledger_id,
            sum(
                next(value for value in item.ledgers if value.ledger_id == ledger_id).numerator
                for item in values
            ),
            sum(
                next(value for value in item.ledgers if value.ledger_id == ledger_id).denominator
                for item in values
            ),
        )
        for ledger_id in _GLOBAL_COVERAGE_LEDGER_IDS
    }
    endpoint = Counter()
    pairs = Counter()
    directions = Counter()
    dates = Counter()
    raw_canonical = Counter()
    for item in values:
        endpoint.update(dict(item.endpoint_status_counts))
        pairs.update(dict(item.endpoint_pair_status_counts))
        directions.update(dict(item.direction_status_counts))
        dates.update(dict(item.date_diagnostic_counts))
        raw_canonical.update({
            (raw_hash, canonical_hash, status): count
            for raw_hash, canonical_hash, status, count
            in item.raw_canonical_label_counts
        })
    mapped_pairs = pairs["mapped"]
    candidate_dates = dates["preoutcome_candidate_dates"]
    return _build_global_coverage_value(
        schema=GLOBAL_COMPARATOR_POOLED_COVERAGE_SCHEMA,
        scope_id="pooled",
        source_view_id=source_view_id,
        fold_ids=FORMAL_PRIMARY_FOLD_IDS,
        result_bindings=tuple(item.result_bindings[0] for item in values),
        h20_test_intervals=tuple(item.h20_test_intervals[0] for item in values),
        ledgers=tuple(ledger_by_id[item] for item in _GLOBAL_COVERAGE_LEDGER_IDS),
        endpoint_status_counts=tuple((name, endpoint[name]) for name in _ENDPOINT_STATUS_IDS),
        endpoint_pair_status_counts=tuple((name, pairs[name]) for name in _ENDPOINT_STATUS_IDS),
        direction_status_counts=tuple((name, directions[name]) for name in _DIRECTION_STATUS_IDS),
        raw_canonical_label_counts=tuple(
            (*key, count) for key, count in sorted(raw_canonical.items())
        ),
        date_diagnostic_counts=tuple((name, dates[name]) for name in _DATE_DIAGNOSTIC_IDS),
        diagnostic_ratios=(
            _coverage_ratio(
                "global_tier_collapse_zero_share",
                directions["zero_delta"], mapped_pairs,
            ),
            _coverage_ratio(
                "global_direction_conflict_share",
                directions["opposite_sign"], mapped_pairs,
            ),
            _coverage_ratio(
                "firm_totalized_zero_date_share",
                dates["firm_totalized_zero_dates"], candidate_dates,
            ),
            _coverage_ratio(
                "global_totalized_zero_date_share",
                dates["global_totalized_zero_dates"], candidate_dates,
            ),
            _coverage_ratio(
                "both_arms_constant_date_share",
                dates["both_arms_constant_dates"], candidate_dates,
            ),
        ),
    )


def _decision_from_scoring(
    result: ProductionScoringResult,
    row: FinalDecisionInput,
) -> ProductionScoredDecisionLineage:
    if type(row.contributions) is not tuple or any(
        type(item) is not ContributionLineage for item in row.contributions
    ):
        raise FormalInputBundleError(
            "final scoring row lacks exact contribution lineage"
        )
    full_record = {
        "source_view_id": _source_view(row.signal_arm),
        "fold_id": row.fold_id,
        "decision_session": row.decision_session,
        "security_id": row.security_id,
        "issuer_id": row.issuer_id,
        "share_class_id": row.share_class_id,
        "listing_id": row.listing_id,
        "historical_ticker": row.historical_ticker,
        "sector_id": row.sector_id,
        "industry_id": row.industry_id,
        "structural_zero": row.state is ScoreState.STRUCTURAL_ZERO,
        "firm_specific_score": str(row.firm_specific_score),
        "global_score": str(row.global_score),
        "transformed_controls": [str(item) for item in row.transformed_controls],
        "realized_volatility_60d": str(row.realized_volatility_60d),
        "earnings_anchor_signed_session_distance": (
            row.earnings_anchor_signed_session_distance
        ),
        "common_event_component_id": row.common_event_component_id,
        "contributions": [item.to_record() for item in row.contributions],
        "final_scoring_row_sha256": row.row_sha256,
        "scoring_result_id": result.result_id,
        "scoring_result_sha256": result.result_sha256,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
    }
    record = {
        "source_view_id": full_record["source_view_id"],
        "fold_id": row.fold_id,
        "decision_session": row.decision_session,
        "security_id": row.security_id,
        "final_scoring_row_sha256": row.row_sha256,
        "scoring_result_id": result.result_id,
        "scoring_result_sha256": result.result_sha256,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
    }
    decision_id, digest, _ = _post_identified(
        prefix="arv2-formal-production-decision-",
        schema=SCORING_LINEAGE_SCHEMA,
        record=record,
    )
    value = ProductionScoredDecisionLineage(
        schema=SCORING_LINEAGE_SCHEMA,
        decision_id=decision_id,
        lineage_sha256=digest,
        source_view_id=str(full_record["source_view_id"]),
        fold_id=row.fold_id,
        decision_session=date.fromisoformat(row.decision_session),
        security_id=row.security_id,
        issuer_id=row.issuer_id,
        share_class_id=row.share_class_id,
        listing_id=row.listing_id,
        historical_ticker=row.historical_ticker,
        sector_id=row.sector_id,
        industry_id=row.industry_id,
        structural_zero=row.state is ScoreState.STRUCTURAL_ZERO,
        firm_specific_score=row.firm_specific_score,
        global_score=row.global_score,
        transformed_controls=row.transformed_controls,
        realized_volatility_60d=row.realized_volatility_60d,
        earnings_anchor_signed_session_distance=(
            row.earnings_anchor_signed_session_distance
        ),
        common_event_component_id=row.common_event_component_id,
        contributions=row.contributions,
        final_scoring_row_sha256=row.row_sha256,
        scoring_result_id=result.result_id,
        scoring_result_sha256=result.result_sha256,
        scoring_contract_id=SCORING_CONTRACT_ID,
        scoring_contract_sha256=SCORING_CONTRACT_SHA256,
    )
    return _require_production_scored_decision(value)


def _require_production_scored_decision(
    value: ProductionScoredDecisionLineage,
) -> ProductionScoredDecisionLineage:
    if type(value) is not ProductionScoredDecisionLineage:
        raise FormalInputBundleError("scored decision lineage changed type")
    if value.schema != SCORING_LINEAGE_SCHEMA or value.source_view_id not in {
        CURRENT_VIEW_LABEL,
        CENSORED_VIEW_LABEL,
    }:
        raise FormalInputBundleError("scored decision schema or source view changed")
    for name in (
        "decision_id", "fold_id", "security_id", "issuer_id", "share_class_id",
        "listing_id", "historical_ticker", "sector_id", "industry_id",
        "common_event_component_id", "scoring_result_id", "scoring_contract_id",
    ):
        _post_id(getattr(value, name), name)
    for name in (
        "lineage_sha256", "final_scoring_row_sha256", "scoring_result_sha256",
        "scoring_contract_sha256",
    ):
        _post_sha(getattr(value, name), name)
    _post_date(value.decision_session, "decision_session")
    if value.fold_id not in FORMAL_PRIMARY_FOLD_IDS:
        raise FormalInputBundleError("scored decision lies outside formal folds")
    if type(value.structural_zero) is not bool:
        raise FormalInputBundleError("structural_zero changed type")
    for name in ("firm_specific_score", "global_score"):
        score = _post_decimal(getattr(value, name), name)
        if score < Decimal("-4") or score > Decimal("4"):
            raise FormalInputBundleError("scored decision lies outside score clip")
    if type(value.transformed_controls) is not tuple or len(
        value.transformed_controls
    ) != len(CONTROL_COLUMNS):
        raise FormalInputBundleError("scored decision lacks all 25 controls")
    for item in value.transformed_controls:
        _post_decimal(item, "transformed control")
    _post_decimal(value.realized_volatility_60d, "realized_volatility_60d")
    if (
        value.earnings_anchor_signed_session_distance is not None
        and type(value.earnings_anchor_signed_session_distance) is not int
    ):
        raise FormalInputBundleError(
            "earnings anchor distance changed type"
        )
    if type(value.contributions) is not tuple or any(
        type(item) is not ContributionLineage for item in value.contributions
    ):
        raise FormalInputBundleError("scored decision contribution topology changed")
    for item in value.contributions:
        item.__post_init__()
    if value.structural_zero and value.contributions:
        raise FormalInputBundleError(
            "structural-zero state has contribution lineage"
        )
    if value.structural_zero and (
        value.firm_specific_score != 0 or value.global_score != 0
    ):
        raise FormalInputBundleError("structural-zero scores changed")
    if value.scoring_contract_id != SCORING_CONTRACT_ID or (
        value.scoring_contract_sha256 != SCORING_CONTRACT_SHA256
    ):
        raise FormalInputBundleError("scoring contract binding changed")
    record = value.to_binding_record(include_identity=False)
    expected_id, digest, _ = _post_identified(
        prefix="arv2-formal-production-decision-",
        schema=SCORING_LINEAGE_SCHEMA,
        record={key: item for key, item in record.items() if key != "schema"},
    )
    if value.decision_id != expected_id or value.lineage_sha256 != digest:
        raise FormalInputBundleError("scored decision identity changed")
    return value


def _refusal_from_scoring(
    result: ProductionScoringResult,
    refusal: ScoringRefusal,
) -> ProductionScoringCensusRefusal:
    record = {
        "source_view_id": _source_view(refusal.signal_arm),
        "fold_id": refusal.fold_id,
        "decision_session": refusal.decision_session,
        "security_id": refusal.security_id,
        "disposition": refusal.disposition.value,
        "source_refusal_sha256": refusal.refusal_sha256,
        "scoring_result_id": result.result_id,
        "scoring_result_sha256": result.result_sha256,
    }
    refusal_id, digest, _ = _post_identified(
        prefix="arv2-formal-production-refusal-",
        schema=SCORING_REFUSAL_SCHEMA,
        record=record,
    )
    return ProductionScoringCensusRefusal(
        schema=SCORING_REFUSAL_SCHEMA,
        refusal_id=refusal_id,
        refusal_sha256=digest,
        source_view_id=str(record["source_view_id"]),
        fold_id=refusal.fold_id,
        decision_session=date.fromisoformat(refusal.decision_session),
        security_id=refusal.security_id,
        disposition=refusal.disposition.value,
        source_refusal_sha256=refusal.refusal_sha256,
        scoring_result_id=result.result_id,
        scoring_result_sha256=result.result_sha256,
    )


def _require_production_scoring_refusal(
    value: ProductionScoringCensusRefusal,
) -> ProductionScoringCensusRefusal:
    if type(value) is not ProductionScoringCensusRefusal:
        raise FormalInputBundleError("production scoring refusal changed type")
    if value.schema != SCORING_REFUSAL_SCHEMA or value.source_view_id not in {
        CURRENT_VIEW_LABEL,
        CENSORED_VIEW_LABEL,
    }:
        raise FormalInputBundleError("production scoring refusal schema changed")
    for name in (
        "refusal_id", "fold_id", "security_id", "disposition",
        "scoring_result_id",
    ):
        _post_id(getattr(value, name), name)
    for name in (
        "refusal_sha256", "source_refusal_sha256", "scoring_result_sha256",
    ):
        _post_sha(getattr(value, name), name)
    _post_date(value.decision_session, "refusal decision_session")
    if value.fold_id not in FORMAL_PRIMARY_FOLD_IDS:
        raise FormalInputBundleError("production refusal lies outside formal folds")
    record = value.to_record(include_identity=False)
    expected_id, digest, _ = _post_identified(
        prefix="arv2-formal-production-refusal-",
        schema=SCORING_REFUSAL_SCHEMA,
        record={key: item for key, item in record.items() if key != "schema"},
    )
    if value.refusal_id != expected_id or value.refusal_sha256 != digest:
        raise FormalInputBundleError("production scoring refusal identity changed")
    return value


def _arm_terminal_key(
    item: ProductionScoredDecisionLineage | ProductionScoringCensusRefusal,
) -> tuple[str, date, str]:
    return item.fold_id, item.decision_session, item.security_id


def _build_source_view_scoring_census(
    source_view_id: str,
    accepted: tuple[ProductionScoredDecisionLineage, ...],
    refused: tuple[ProductionScoringCensusRefusal, ...],
) -> FormalSourceViewScoringCensus:
    accepted = tuple(sorted(accepted, key=_arm_terminal_key))
    refused = tuple(sorted(refused, key=_arm_terminal_key))
    accepted_keys = tuple(_arm_terminal_key(item) for item in accepted)
    refused_keys = tuple(_arm_terminal_key(item) for item in refused)
    if len(accepted_keys) != len(set(accepted_keys)) or len(refused_keys) != len(
        set(refused_keys)
    ) or set(accepted_keys) & set(refused_keys):
        raise FormalInputBundleError(
            "one source-view scoring census is not exhaustive and exclusive"
        )
    terminal_record = {
        "source_view_id": source_view_id,
        # The authenticated scorer result remains the parent of the complete
        # decision and contribution graph.  This census is a compact Merkle
        # binding to those rows, not a second (potentially enormous) copy of
        # every decayed contribution.
        "accepted": [item.to_binding_record() for item in accepted],
        "refused": [item.to_record() for item in refused],
    }
    terminal_hash = hashlib.sha256(
        _post_canonical_bytes(terminal_record)
    ).hexdigest()
    return FormalSourceViewScoringCensus(
        source_view_id=source_view_id,
        accepted=accepted,
        refused=refused,
        terminal_count=len(accepted) + len(refused),
        terminal_census_sha256=terminal_hash,
    )


def _require_source_view_scoring_census(
    value: FormalSourceViewScoringCensus,
) -> FormalSourceViewScoringCensus:
    if type(value) is not FormalSourceViewScoringCensus or (
        value.source_view_id not in {CURRENT_VIEW_LABEL, CENSORED_VIEW_LABEL}
    ):
        raise FormalInputBundleError("source-view scoring census changed type or view")
    if type(value.accepted) is not tuple or type(value.refused) is not tuple:
        raise FormalInputBundleError("source-view scoring census containers changed")
    for item in value.accepted:
        _require_production_scored_decision(item)
        if item.source_view_id != value.source_view_id:
            raise FormalInputBundleError("accepted score crossed source views")
    for item in value.refused:
        _require_production_scoring_refusal(item)
        if item.source_view_id != value.source_view_id:
            raise FormalInputBundleError("scoring refusal crossed source views")
    rebuilt = _build_source_view_scoring_census(
        value.source_view_id, value.accepted, value.refused
    )
    if value != rebuilt:
        raise FormalInputBundleError("source-view scoring census changed")
    return value


def _validate_scoring_result_set(
    results: tuple[ProductionScoringResult, ...],
) -> None:
    if type(results) is not tuple or len(results) != len(
        _EXPECTED_SCORING_FOLD_GEOMETRY
    ) or any(type(item) is not ProductionScoringResult for item in results):
        raise FormalInputBundleError(
            "formal scoring requires exactly six builder-authenticated results"
        )
    shared_authority: object | None = None
    for result, expected in zip(
        results, _EXPECTED_SCORING_FOLD_GEOMETRY, strict=True
    ):
        try:
            require_production_scoring_result(result)
        except (ProductionScoringError, AttributeError, TypeError, ValueError) as exc:
            raise FormalInputBundleError(
                "formal scoring result is not builder-authenticated"
            ) from exc
        batch = result.precontrol_batch
        fold = batch.fold
        actual = (
            fold.fold_id,
            fold.train_start,
            fold.train_end_exclusive,
            fold.validation_start,
            fold.validation_end_exclusive,
            fold.test_start,
            fold.test_end_exclusive,
        )
        if actual != expected or result.schema != PRODUCTION_SCORING_RESULT_SCHEMA:
            raise FormalInputBundleError(
                "production scoring result does not use the exact H60-safe formal fold"
            )
        if shared_authority is None:
            shared_authority = batch.authority
        elif batch.authority is not shared_authority:
            raise FormalInputBundleError(
                "six production scoring results do not share one evidence authority"
            )


def _derive_scoring_census(
    results: tuple[ProductionScoringResult, ...],
) -> tuple[
    tuple[ScoringResultBinding, ...],
    FormalSourceViewScoringCensus,
    FormalSourceViewScoringCensus,
    int,
    str,
    dict[str, object],
]:
    _validate_scoring_result_set(results)
    accepted: dict[str, list[ProductionScoredDecisionLineage]] = {
        CURRENT_VIEW_LABEL: [],
        CENSORED_VIEW_LABEL: [],
    }
    refused: dict[str, list[ProductionScoringCensusRefusal]] = {
        CURRENT_VIEW_LABEL: [],
        CENSORED_VIEW_LABEL: [],
    }
    seen_base_keys: set[tuple[str, date, str]] = set()
    for result in results:
        fold = result.precontrol_batch.fold
        expected_base_keys = {
            (fold.fold_id, date.fromisoformat(item.decision_session), item.security_id)
            for item in (
                *result.precontrol_batch.authority.census_rows,
                *result.precontrol_batch.authority.census_refusals,
            )
            if fold.partition(item.decision_session) is FoldPartition.TEST
        }
        if not expected_base_keys or seen_base_keys & expected_base_keys:
            raise FormalInputBundleError(
                "formal fold TEST censuses are empty or overlap"
            )
        seen_base_keys.update(expected_base_keys)
        actual_by_view: dict[str, set[tuple[str, date, str]]] = {
            CURRENT_VIEW_LABEL: set(),
            CENSORED_VIEW_LABEL: set(),
        }
        for row in result.rows:
            if row.partition is not FoldPartition.TEST:
                continue
            value = _decision_from_scoring(result, row)
            accepted[value.source_view_id].append(value)
            actual_by_view[value.source_view_id].add(_arm_terminal_key(value))
        for item in result.refusals:
            if item.partition is not FoldPartition.TEST:
                continue
            value = _refusal_from_scoring(result, item)
            _require_production_scoring_refusal(value)
            refused[value.source_view_id].append(value)
            actual_by_view[value.source_view_id].add(_arm_terminal_key(value))
        if any(keys != expected_base_keys for keys in actual_by_view.values()):
            raise FormalInputBundleError(
                "current/censored TEST census is not matched or named-refused"
            )
    current = _build_source_view_scoring_census(
        CURRENT_VIEW_LABEL,
        tuple(accepted[CURRENT_VIEW_LABEL]),
        tuple(refused[CURRENT_VIEW_LABEL]),
    )
    censored = _build_source_view_scoring_census(
        CENSORED_VIEW_LABEL,
        tuple(accepted[CENSORED_VIEW_LABEL]),
        tuple(refused[CENSORED_VIEW_LABEL]),
    )
    current_keys = tuple(
        sorted(_arm_terminal_key(item) for item in (*current.accepted, *current.refused))
    )
    censored_keys = tuple(
        sorted(_arm_terminal_key(item) for item in (*censored.accepted, *censored.refused))
    )
    if current_keys != censored_keys:
        raise FormalInputBundleError(
            "current/censored source views do not share one exact terminal census"
        )
    component_dates: dict[str, date] = {}
    for item in (*current.accepted, *censored.accepted):
        prior = component_dates.setdefault(
            item.common_event_component_id, item.decision_session
        )
        if prior != item.decision_session:
            raise FormalInputBundleError(
                "a scorer-authenticated common-event component crosses dates"
            )
    matched_record = [
        {
            "fold_id": fold_id,
            "decision_session": session.isoformat(),
            "security_id": security_id,
        }
        for fold_id, session, security_id in current_keys
    ]
    matched_hash = hashlib.sha256(
        _post_canonical_bytes(
            {"domain": "arv2-matched-scoring-terminal-census-v1", "keys": matched_record}
        )
    ).hexdigest()
    bindings = tuple(_result_binding(item) for item in results)
    record: dict[str, object] = {
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "result_bindings": [item.to_record() for item in bindings],
        "formal_primary_fold_ids": list(FORMAL_PRIMARY_FOLD_IDS),
        "descriptive_sensitivity_fold_ids": list(
            DESCRIPTIVE_SENSITIVITY_FOLD_IDS
        ),
        "current_view": current.to_record(),
        "censored_view": censored.to_record(),
        "matched_security_session_count": len(current_keys),
        "matched_terminal_census_sha256": matched_hash,
        "source_views_distinct": True,
        "source_views_share_one_census": True,
        "caller_supplied_scores_accepted": False,
        "pre_run_action_authority": None,
        "capabilities": {name: False for name in _POST_QC_CAPABILITY_NAMES},
    }
    return bindings, current, censored, len(current_keys), matched_hash, record


def build_formal_production_scoring_census(
    scoring_results: tuple[ProductionScoringResult, ...],
) -> FormalProductionScoringCensus:
    """Derive the exact formal TEST census without a caller score channel."""

    (
        bindings,
        current,
        censored,
        matched_count,
        matched_hash,
        record,
    ) = _derive_scoring_census(scoring_results)
    census_id, digest, payload = _post_identified(
        prefix="arv2-formal-production-scoring-census-",
        schema=SCORING_CENSUS_SCHEMA,
        record=record,
    )
    value = object.__new__(FormalProductionScoringCensus)
    values: dict[str, object] = {
        "census_id": census_id,
        "census_sha256": digest,
        "schema": SCORING_CENSUS_SCHEMA,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "result_bindings": bindings,
        "formal_primary_fold_ids": FORMAL_PRIMARY_FOLD_IDS,
        "descriptive_sensitivity_fold_ids": DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
        "current_view": current,
        "censored_view": censored,
        "matched_security_session_count": matched_count,
        "matched_terminal_census_sha256": matched_hash,
        "source_views_distinct": True,
        "source_views_share_one_census": True,
        "caller_supplied_scores_accepted": False,
        "pre_run_action_authority": None,
        "capabilities": tuple((name, False) for name in _POST_QC_CAPABILITY_NAMES),
        "_results": scoring_results,
        "_canonical_document": payload,
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_scoring_census(key, ref)
    )
    with _SCORING_CENSUS_AUTHORITIES_LOCK:
        _SCORING_CENSUS_AUTHORITIES[identity] = (
            reference,
            tuple(weakref.ref(item) for item in scoring_results),
            payload,
            _scoring_census_topology(value),
        )
    return require_formal_production_scoring_census(value)


def require_formal_production_scoring_census(
    value: FormalProductionScoringCensus,
) -> FormalProductionScoringCensus:
    """Reauthenticate the census and all six production-scoring parents."""

    if type(value) is not FormalProductionScoringCensus:
        raise FormalInputBundleError("formal scoring census changed type")
    with _SCORING_CENSUS_AUTHORITIES_LOCK:
        registered = _SCORING_CENSUS_AUTHORITIES.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalInputBundleError(
            "formal scoring census is not builder-authenticated"
        )
    if (
        type(value._results) is not tuple
        or len(registered[1]) != len(value._results)
        or any(
        reference() is not item
        for reference, item in zip(registered[1], value._results, strict=True)
        )
    ):
        raise FormalInputBundleError("formal scoring result parent changed")
    (
        bindings,
        current,
        censored,
        matched_count,
        matched_hash,
        record,
    ) = _derive_scoring_census(value._results)
    _require_source_view_scoring_census(value.current_view)
    _require_source_view_scoring_census(value.censored_view)
    census_id, digest, payload = _post_identified(
        prefix="arv2-formal-production-scoring-census-",
        schema=SCORING_CENSUS_SCHEMA,
        record=record,
    )
    expected = {
        "census_id": census_id,
        "census_sha256": digest,
        "schema": SCORING_CENSUS_SCHEMA,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "result_bindings": bindings,
        "formal_primary_fold_ids": FORMAL_PRIMARY_FOLD_IDS,
        "descriptive_sensitivity_fold_ids": DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
        "current_view": current,
        "censored_view": censored,
        "matched_security_session_count": matched_count,
        "matched_terminal_census_sha256": matched_hash,
        "source_views_distinct": True,
        "source_views_share_one_census": True,
        "caller_supplied_scores_accepted": False,
        "pre_run_action_authority": None,
        "capabilities": tuple((name, False) for name in _POST_QC_CAPABILITY_NAMES),
        "_canonical_document": payload,
    }
    if any(getattr(value, name) != item for name, item in expected.items()):
        raise FormalInputBundleError("formal scoring census content changed")
    if payload != registered[2] or _scoring_census_topology(value) != registered[3]:
        raise FormalInputBundleError("formal scoring census topology changed")
    for name in (
        "qc_launch_available", "outcome_access_available", "orders_available",
        "trading_available",
    ):
        if getattr(value, name) is not False:
            raise FormalInputBundleError("formal scoring census acquired authority")
    return value


def render_formal_production_scoring_census_bytes(
    value: FormalProductionScoringCensus,
) -> bytes:
    require_formal_production_scoring_census(value)
    return bytes(value._canonical_document)


# Downstream scale-safe successor.  The legacy census above remains a
# compatibility adapter for small fixtures.  This projection itself retains
# only one TEST date cross-section while consuming a fold, but its upstream
# truth artifact and active ProductionScoringResult are still fully
# materialized.  Consequently it cannot authenticate production capacity.
@dataclasses.dataclass(frozen=True, slots=True)
class FormalScoringFoldCommitment:
    schema: str
    fold_id: str
    result_binding: ScoringResultBinding
    fold_geometry: tuple[str, ...]
    horizon_fold_geometries: tuple[tuple[object, ...], ...]
    global_comparator_coverages: tuple[FormalGlobalComparatorCoverage, ...]
    model_records: tuple[dict[str, object], ...]
    partition_terminal_counts: tuple[tuple[str, int, int], ...]
    partition_terminal_roots: tuple[tuple[str, str, str], ...]
    training_sufficient_stat_commitment_sha256: str

    def to_record(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "fold_id": self.fold_id,
            "result_binding": self.result_binding.to_record(),
            "fold_geometry": list(self.fold_geometry),
            "horizon_fold_geometries": [
                list(item) for item in self.horizon_fold_geometries
            ],
            "global_comparator_coverages": [
                item.to_record() for item in self.global_comparator_coverages
            ],
            "model_records": list(self.model_records),
            "partition_terminal_counts": [list(item) for item in self.partition_terminal_counts],
            "partition_terminal_roots": [list(item) for item in self.partition_terminal_roots],
            "training_sufficient_stat_commitment_sha256": (
                self.training_sufficient_stat_commitment_sha256
            ),
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FormalScoringSessionBlock:
    block_id: str
    block_sha256: str
    schema: str
    fold_id: str
    decision_session: date
    current_accepted: tuple[ProductionScoredDecisionLineage, ...]
    current_refused: tuple[ProductionScoringCensusRefusal, ...]
    censored_accepted: tuple[ProductionScoredDecisionLineage, ...]
    censored_refused: tuple[ProductionScoringCensusRefusal, ...]
    matched_terminal_count: int
    matched_terminal_sha256: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalProductionScoringProjectionBuilder:
    builder_id: str
    schema: str


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalProductionScoringProjection:
    projection_id: str
    projection_sha256: str
    schema: str
    scoring_contract_id: str
    scoring_contract_sha256: str
    result_bindings: tuple[ScoringResultBinding, ...]
    fold_commitments: tuple[FormalScoringFoldCommitment, ...]
    pooled_global_comparator_coverages: tuple[
        FormalGlobalComparatorCoverage, ...
    ]
    production_truth_artifact_id: str
    production_truth_artifact_sha256: str
    accepted_risk_pair_record: dict[str, object]
    matched_security_session_count: int
    matched_terminal_census_sha256: str
    current_terminal_count: int
    current_terminal_census_sha256: str
    censored_terminal_count: int
    censored_terminal_census_sha256: str
    source_views_distinct: bool
    source_views_share_one_census: bool
    caller_supplied_scores_accepted: bool
    upstream_truth_and_one_fold_materialization_capacity_authenticated: bool
    production_capacity_disposition: str
    capabilities: tuple[tuple[str, bool], ...]
    _canonical_document: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(slots=True)
class _ProjectionBuilderState:
    truth: ProductionTruthArtifact
    accepted_risk: AcceptedRiskPairBinding
    next_fold_index: int
    result_bindings: list[ScoringResultBinding]
    fold_commitments: list[FormalScoringFoldCommitment]
    matched_count: int
    current_count: int
    censored_count: int
    matched_hasher: object
    current_hasher: object
    censored_hasher: object
    active_result: bool
    finalized: bool


_PROJECTION_BUILDERS: dict[
    int, tuple[weakref.ReferenceType[FormalProductionScoringProjectionBuilder], bytes, _ProjectionBuilderState]
] = {}
_PROJECTIONS: dict[
    int, tuple[weakref.ReferenceType[FormalProductionScoringProjection], bytes, tuple[object, ...]]
] = {}
_SESSION_BLOCKS: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalScoringSessionBlock], int, bytes,
        tuple[object, ...],
    ],
] = {}
_PROJECTION_LOCK = threading.RLock()


def _chain_hasher(domain: str) -> object:
    value = hashlib.sha256()
    value.update(domain.encode("ascii") + b"\0")
    return value


def _chain_update(hasher: object, record: object) -> None:
    payload = _post_canonical_bytes(record)
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)


def _forget_projection_builder(identity: int, reference: object) -> None:
    with _PROJECTION_LOCK:
        current = _PROJECTION_BUILDERS.get(identity)
        if current is not None and current[0] is reference:
            _PROJECTION_BUILDERS.pop(identity, None)


def _forget_projection(identity: int, reference: object) -> None:
    with _PROJECTION_LOCK:
        current = _PROJECTIONS.get(identity)
        if current is not None and current[0] is reference:
            _PROJECTIONS.pop(identity, None)


def _forget_session_block(identity: int, reference: object) -> None:
    with _PROJECTION_LOCK:
        current = _SESSION_BLOCKS.get(identity)
        if current is not None and current[0] is reference:
            _SESSION_BLOCKS.pop(identity, None)


def begin_formal_production_scoring_projection(
    *, production_truth: ProductionTruthArtifact,
    accepted_risk: AcceptedRiskPairBinding,
) -> FormalProductionScoringProjectionBuilder:
    """Open an opaque sequential six-fold projection builder."""

    try:
        require_production_truth_artifact(production_truth)
        require_accepted_risk_pair_binding(accepted_risk)
    except (ProductionTruthError, FormalRunProtocolError, AttributeError, TypeError, ValueError) as exc:
        raise FormalInputBundleError(
            "stream projection parents are not builder-authenticated"
        ) from exc
    seed = {
        "schema": SCORING_PROJECTION_BUILDER_SCHEMA,
        "production_truth_artifact_id": production_truth.artifact_id,
        "production_truth_artifact_sha256": production_truth.artifact_sha256,
        "accepted_risk": accepted_risk.to_record(),
    }
    digest = hashlib.sha256(_post_canonical_bytes(seed)).hexdigest()
    value = object.__new__(FormalProductionScoringProjectionBuilder)
    object.__setattr__(value, "builder_id", f"arv2-scoring-projection-builder-{digest[:24]}")
    object.__setattr__(value, "schema", SCORING_PROJECTION_BUILDER_SCHEMA)
    state = _ProjectionBuilderState(
        production_truth, accepted_risk, 0, [], [], 0, 0, 0,
        _chain_hasher("arv2-matched-scoring-terminal-census-v2"),
        _chain_hasher("arv2-current-scoring-terminal-census-v2"),
        _chain_hasher("arv2-censored-scoring-terminal-census-v2"),
        False, False,
    )
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_projection_builder(key, ref)
    )
    static = _post_canonical_bytes({"builder_id": value.builder_id, "schema": value.schema})
    with _PROJECTION_LOCK:
        _PROJECTION_BUILDERS[identity] = (reference, static, state)
    return _require_projection_builder(value)[0]


def _require_projection_builder(
    value: FormalProductionScoringProjectionBuilder,
) -> tuple[FormalProductionScoringProjectionBuilder, _ProjectionBuilderState]:
    if type(value) is not FormalProductionScoringProjectionBuilder:
        raise FormalInputBundleError("scoring projection builder changed type")
    with _PROJECTION_LOCK:
        registered = _PROJECTION_BUILDERS.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalInputBundleError(
            "scoring projection builder is not builder-authenticated"
        )
    try:
        static = _post_canonical_bytes(
            {"builder_id": value.builder_id, "schema": value.schema}
        )
    except AttributeError as exc:
        raise FormalInputBundleError("scoring projection builder changed") from exc
    if registered[1] != static:
        raise FormalInputBundleError("scoring projection builder changed")
    return value, registered[2]


def _model_record(model: object) -> dict[str, object]:
    return {
        "model_id": model.model_id,
        "model_sha256": model.model_sha256,
        "signal_arm": model.signal_arm.value,
        "fold_id": model.fold_id,
        "train_start": model.train_start,
        "train_end_exclusive": model.train_end_exclusive,
        "columns": list(model.columns),
        "industry_levels": list(model.industry_levels),
        "reference_industry": model.reference_industry,
        "firm_coefficients": [str(item) for item in model.firm_coefficients],
        "global_coefficients": [str(item) for item in model.global_coefficients],
        "active_training_rows": model.active_training_rows,
    }


def _partition_commitments(
    result: ProductionScoringResult,
) -> tuple[tuple[tuple[str, int, int], ...], tuple[tuple[str, str, str], ...]]:
    counts: list[tuple[str, int, int]] = []
    roots: list[tuple[str, str, str]] = []
    for partition in FoldPartition:
        partition_counts = []
        partition_roots = []
        for arm in SignalArm:
            hasher = _chain_hasher(
                f"arv2-scoring-{partition.value}-{arm.value}-terminal-v1"
            )
            count = 0
            terminals = heapq.merge(
                (
                    (item.decision_session, item.security_id, "accepted", item.row_sha256)
                    for item in result.rows
                    if item.partition is partition and item.signal_arm is arm
                ),
                (
                    (item.decision_session, item.security_id, "refused", item.refusal_sha256)
                    for item in result.refusals
                    if item.partition is partition and item.signal_arm is arm
                ),
                key=lambda item: (item[0], item[1]),
            )
            for session, security, disposition, lineage in terminals:
                _chain_update(hasher, {
                    "decision_session": session, "security_id": security,
                    "disposition": disposition, "lineage_sha256": lineage,
                })
                count += 1
            partition_counts.append(count)
            partition_roots.append(hasher.hexdigest())
        counts.append((partition.value, partition_counts[0], partition_counts[1]))
        roots.append((partition.value, partition_roots[0], partition_roots[1]))
    return tuple(counts), tuple(roots)


def _view_test_groups(
    result: ProductionScoringResult, arm: SignalArm,
):
    terminals = heapq.merge(
        (
            (item.decision_session, item.security_id, 0, item)
            for item in result.rows
            if item.partition is FoldPartition.TEST and item.signal_arm is arm
        ),
        (
            (item.decision_session, item.security_id, 1, item)
            for item in result.refusals
            if item.partition is FoldPartition.TEST and item.signal_arm is arm
        ),
        key=lambda item: (item[0], item[1]),
    )
    for session, group in itertools.groupby(terminals, key=lambda item: item[0]):
        accepted: list[ProductionScoredDecisionLineage] = []
        refused: list[ProductionScoringCensusRefusal] = []
        for _session, _security, kind, item in group:
            if kind == 0:
                accepted.append(_decision_from_scoring(result, item))
            else:
                value = _refusal_from_scoring(result, item)
                _require_production_scoring_refusal(value)
                refused.append(value)
        yield date.fromisoformat(session), tuple(accepted), tuple(refused)


def _session_block_record(
    *, fold_id: str, decision_session: date,
    current_accepted: tuple[ProductionScoredDecisionLineage, ...],
    current_refused: tuple[ProductionScoringCensusRefusal, ...],
    censored_accepted: tuple[ProductionScoredDecisionLineage, ...],
    censored_refused: tuple[ProductionScoringCensusRefusal, ...],
) -> dict[str, object]:
    return {
        "fold_id": fold_id, "decision_session": decision_session.isoformat(),
        "current_accepted": [item.to_record() for item in current_accepted],
        "current_refused": [item.to_record() for item in current_refused],
        "censored_accepted": [item.to_record() for item in censored_accepted],
        "censored_refused": [item.to_record() for item in censored_refused],
    }


def _session_block_topology(
    value: FormalScoringSessionBlock,
) -> tuple[object, ...]:
    return (
        id(value.current_accepted),
        tuple(id(item) for item in value.current_accepted),
        id(value.current_refused),
        tuple(id(item) for item in value.current_refused),
        id(value.censored_accepted),
        tuple(id(item) for item in value.censored_accepted),
        id(value.censored_refused),
        tuple(id(item) for item in value.censored_refused),
    )


def require_formal_scoring_session_block(
    value: FormalScoringSessionBlock,
    *, builder: FormalProductionScoringProjectionBuilder,
) -> FormalScoringSessionBlock:
    _require_projection_builder(builder)
    if type(value) is not FormalScoringSessionBlock:
        raise FormalInputBundleError("formal scoring session block changed type")
    with _PROJECTION_LOCK:
        registered = _SESSION_BLOCKS.get(id(value))
    if registered is None or registered[0]() is not value or registered[1] != id(builder):
        raise FormalInputBundleError(
            "formal scoring session block is not builder-authenticated"
        )
    record = _session_block_record(
        fold_id=value.fold_id, decision_session=value.decision_session,
        current_accepted=value.current_accepted,
        current_refused=value.current_refused,
        censored_accepted=value.censored_accepted,
        censored_refused=value.censored_refused,
    )
    block_id, digest, payload = _post_identified(
        prefix="arv2-formal-scoring-session-block-",
        schema=SCORING_SESSION_BLOCK_SCHEMA, record=record,
    )
    if (
        value.schema != SCORING_SESSION_BLOCK_SCHEMA
        or value.block_id != block_id or value.block_sha256 != digest
        or value.matched_terminal_sha256 != hashlib.sha256(
            _post_canonical_bytes({
                "keys": [
                    {"fold_id": fold_id,
                     "decision_session": decision_session.isoformat(),
                     "security_id": security_id}
                    for fold_id, decision_session, security_id in sorted(
                        _arm_terminal_key(item)
                        for item in (*value.current_accepted, *value.current_refused)
                    )
                ]
            })
        ).hexdigest()
        or registered[2] != payload
        or registered[3] != _session_block_topology(value)
    ):
        raise FormalInputBundleError("formal scoring session block changed")
    return value


def iter_formal_production_scoring_result_blocks(
    builder: FormalProductionScoringProjectionBuilder,
    result: ProductionScoringResult,
):
    """Consume one authenticated fold result and yield one TEST date at a time.

    The caller must exhaust the iterator before submitting the next fold.  The
    result is not retained after exhaustion; upstream construction of that one
    result remains separately capacity-gated.
    """

    _, state = _require_projection_builder(builder)
    if state.finalized or state.active_result:
        raise FormalInputBundleError("scoring projection builder is busy or sealed")
    if state.next_fold_index >= len(_EXPECTED_SCORING_FOLD_GEOMETRY):
        raise FormalInputBundleError("all formal scoring folds are already consumed")
    expected = _EXPECTED_SCORING_FOLD_GEOMETRY[state.next_fold_index]
    try:
        require_production_scoring_result(result)
    except (ProductionScoringError, AttributeError, TypeError, ValueError) as exc:
        raise FormalInputBundleError("streamed scoring result is not authenticated") from exc
    fold = result.precontrol_batch.fold
    actual = (
        fold.fold_id, fold.train_start, fold.train_end_exclusive,
        fold.validation_start, fold.validation_end_exclusive,
        fold.test_start, fold.test_end_exclusive,
    )
    if actual != expected or result.precontrol_batch.authority.truth_artifact is not state.truth:
        raise FormalInputBundleError(
            "streamed scoring fold geometry or truth parent changed"
        )
    state.active_result = True
    completed = False
    try:
        current_groups = _view_test_groups(result, SignalArm.CURRENT_VINTAGE)
        censored_groups = _view_test_groups(result, SignalArm.CONSERVATIVE_CENSORED)
        for current, censored in itertools.zip_longest(current_groups, censored_groups):
            if current is None or censored is None or current[0] != censored[0]:
                raise FormalInputBundleError(
                    "current/censored TEST session axes are not matched"
                )
            session = current[0]
            current_rows, current_refusals = current[1], current[2]
            censored_rows, censored_refusals = censored[1], censored[2]
            current_keys = tuple(
                sorted(_arm_terminal_key(item) for item in (*current_rows, *current_refusals))
            )
            censored_keys = tuple(
                sorted(_arm_terminal_key(item) for item in (*censored_rows, *censored_refusals))
            )
            if not current_keys or current_keys != censored_keys:
                raise FormalInputBundleError(
                    "current/censored TEST block is omitted or unmatched"
                )
            # The component identifier is not caller-authored at this boundary:
            # every accepted row was reauthenticated against its
            # ``ProductionScoringResult`` parent, whose reviewed component
            # builder hashes ``decision_session`` into the component identity.
            # Retaining every historical component merely to rediscover that
            # invariant would make this otherwise sequential projection grow
            # with the full TEST census.
            for key in current_keys:
                key_record = {
                    "fold_id": key[0], "decision_session": key[1].isoformat(),
                    "security_id": key[2],
                }
                _chain_update(state.matched_hasher, key_record)
                state.matched_count += 1
            for view, accepted, refused, hasher in (
                (CURRENT_VIEW_LABEL, current_rows, current_refusals, state.current_hasher),
                (CENSORED_VIEW_LABEL, censored_rows, censored_refusals, state.censored_hasher),
            ):
                for item in sorted((*accepted, *refused), key=_arm_terminal_key):
                    _chain_update(hasher, (
                        item.to_binding_record() if type(item) is ProductionScoredDecisionLineage
                        else item.to_record()
                    ))
                if view == CURRENT_VIEW_LABEL:
                    state.current_count += len(accepted) + len(refused)
                else:
                    state.censored_count += len(accepted) + len(refused)
            record = _session_block_record(
                fold_id=fold.fold_id, decision_session=session,
                current_accepted=current_rows, current_refused=current_refusals,
                censored_accepted=censored_rows, censored_refused=censored_refusals,
            )
            block_id, digest, payload = _post_identified(
                prefix="arv2-formal-scoring-session-block-",
                schema=SCORING_SESSION_BLOCK_SCHEMA, record=record,
            )
            terminal_sha = hashlib.sha256(_post_canonical_bytes({
                "keys": [
                    {"fold_id": key[0], "decision_session": key[1].isoformat(),
                     "security_id": key[2]} for key in current_keys
                ]
            })).hexdigest()
            block = FormalScoringSessionBlock(
                block_id, digest, SCORING_SESSION_BLOCK_SCHEMA, fold.fold_id,
                session, current_rows, current_refusals,
                censored_rows, censored_refusals, len(current_keys), terminal_sha,
            )
            identity = id(block)
            reference = weakref.ref(
                block, lambda ref, key=identity: _forget_session_block(key, ref)
            )
            with _PROJECTION_LOCK:
                _SESSION_BLOCKS[identity] = (
                    reference, id(builder), payload,
                    _session_block_topology(block),
                )
            yield require_formal_scoring_session_block(block, builder=builder)
        counts, roots = _partition_commitments(result)
        models = tuple(_model_record(item) for item in result.models)
        training_commitment = hashlib.sha256(_post_canonical_bytes({
            "precontrol_batch_id": result.precontrol_batch.batch_id,
            "precontrol_batch_sha256": result.precontrol_batch.batch_sha256,
            "models": models,
            "train_partition_counts": counts[0],
            "train_partition_roots": roots[0],
        })).hexdigest()
        binding = _result_binding(result)
        coverage = build_formal_global_comparator_fold_coverages(result)
        horizon_geometries = tuple(
            item
            for item in _EXPECTED_HORIZON_FOLD_GEOMETRY
            if item[0] == fold.fold_id
        )
        if tuple(item[1] for item in horizon_geometries) != HORIZONS:
            raise FormalInputBundleError(
                "formal fold lost its exact horizon geometries"
            )
        state.result_bindings.append(binding)
        state.fold_commitments.append(FormalScoringFoldCommitment(
            schema=SCORING_FOLD_COMMITMENT_SCHEMA,
            fold_id=fold.fold_id,
            result_binding=binding,
            fold_geometry=tuple(actual),
            horizon_fold_geometries=horizon_geometries,
            global_comparator_coverages=coverage,
            model_records=models,
            partition_terminal_counts=counts,
            partition_terminal_roots=roots,
            training_sufficient_stat_commitment_sha256=training_commitment,
        ))
        state.next_fold_index += 1
        completed = True
    finally:
        state.active_result = not completed


def finish_formal_production_scoring_projection(
    builder: FormalProductionScoringProjectionBuilder,
) -> FormalProductionScoringProjection:
    """Seal six exhausted fold iterators into a compact authenticated root."""

    _, state = _require_projection_builder(builder)
    if (
        state.finalized or state.active_result
        or state.next_fold_index != len(_EXPECTED_SCORING_FOLD_GEOMETRY)
        or state.current_count != state.censored_count
        or state.current_count != state.matched_count
    ):
        raise FormalInputBundleError(
            "scoring projection is incomplete, busy, or unmatched"
        )
    pooled_coverages = tuple(
        pool_formal_global_comparator_coverages(tuple(
            commitment.global_comparator_coverages[index]
            for commitment in state.fold_commitments
        ))
        for index in range(2)
    )
    record = {
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "result_bindings": [item.to_record() for item in state.result_bindings],
        "fold_commitments": [item.to_record() for item in state.fold_commitments],
        "pooled_global_comparator_coverages": [
            item.to_record() for item in pooled_coverages
        ],
        "production_truth_artifact_id": state.truth.artifact_id,
        "production_truth_artifact_sha256": state.truth.artifact_sha256,
        "accepted_risk_pair_record": state.accepted_risk.to_record(),
        "matched_security_session_count": state.matched_count,
        "matched_terminal_census_sha256": state.matched_hasher.hexdigest(),
        "current_terminal_count": state.current_count,
        "current_terminal_census_sha256": state.current_hasher.hexdigest(),
        "censored_terminal_count": state.censored_count,
        "censored_terminal_census_sha256": state.censored_hasher.hexdigest(),
        "source_views_distinct": True,
        "source_views_share_one_census": True,
        "caller_supplied_scores_accepted": False,
        "upstream_truth_and_one_fold_materialization_capacity_authenticated": False,
        "production_capacity_disposition": _UPSTREAM_CAPACITY_DISPOSITION,
        "capabilities": {name: False for name in _POST_QC_CAPABILITY_NAMES},
    }
    projection_id, digest, payload = _post_identified(
        prefix="arv2-formal-production-scoring-projection-",
        schema=SCORING_PROJECTION_SCHEMA, record=record,
    )
    value = object.__new__(FormalProductionScoringProjection)
    values = {
        "projection_id": projection_id, "projection_sha256": digest,
        "schema": SCORING_PROJECTION_SCHEMA,
        "scoring_contract_id": SCORING_CONTRACT_ID,
        "scoring_contract_sha256": SCORING_CONTRACT_SHA256,
        "result_bindings": tuple(state.result_bindings),
        "fold_commitments": tuple(state.fold_commitments),
        "pooled_global_comparator_coverages": pooled_coverages,
        "production_truth_artifact_id": state.truth.artifact_id,
        "production_truth_artifact_sha256": state.truth.artifact_sha256,
        "accepted_risk_pair_record": state.accepted_risk.to_record(),
        "matched_security_session_count": state.matched_count,
        "matched_terminal_census_sha256": state.matched_hasher.hexdigest(),
        "current_terminal_count": state.current_count,
        "current_terminal_census_sha256": state.current_hasher.hexdigest(),
        "censored_terminal_count": state.censored_count,
        "censored_terminal_census_sha256": state.censored_hasher.hexdigest(),
        "source_views_distinct": True, "source_views_share_one_census": True,
        "caller_supplied_scores_accepted": False,
        "upstream_truth_and_one_fold_materialization_capacity_authenticated": False,
        "production_capacity_disposition": _UPSTREAM_CAPACITY_DISPOSITION,
        "capabilities": tuple((name, False) for name in _POST_QC_CAPABILITY_NAMES),
        "_canonical_document": payload,
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    topology = (
        id(value.result_bindings), tuple(id(item) for item in value.result_bindings),
        id(value.fold_commitments), tuple(id(item) for item in value.fold_commitments),
        id(value.pooled_global_comparator_coverages),
        tuple(id(item) for item in value.pooled_global_comparator_coverages),
        id(value.accepted_risk_pair_record), id(value.capabilities),
        id(value._canonical_document),
    )
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_projection(key, ref)
    )
    with _PROJECTION_LOCK:
        _PROJECTIONS[identity] = (reference, payload, topology)
    state.finalized = True
    return require_formal_production_scoring_projection(value)


def _projection_record_from_value(
    value: FormalProductionScoringProjection,
) -> dict[str, object]:
    if (
        type(value.result_bindings) is not tuple
        or type(value.fold_commitments) is not tuple
        or type(value.pooled_global_comparator_coverages) is not tuple
    ):
        raise FormalInputBundleError("formal scoring projection containers changed")
    if (
        len(value.result_bindings) != 6
        or len(value.fold_commitments) != 6
        or len(value.pooled_global_comparator_coverages) != 2
    ):
        raise FormalInputBundleError("formal scoring projection fold census changed")
    for index, (binding, commitment, geometry) in enumerate(zip(
        value.result_bindings, value.fold_commitments,
        _EXPECTED_SCORING_FOLD_GEOMETRY, strict=True,
    )):
        expected_horizon_geometries = tuple(
            item
            for item in _EXPECTED_HORIZON_FOLD_GEOMETRY
            if item[0] == geometry[0]
        )
        _require_scoring_result_binding(binding, expected_fold_id=geometry[0])
        if (
            type(commitment) is not FormalScoringFoldCommitment
            or commitment.schema != SCORING_FOLD_COMMITMENT_SCHEMA
            or commitment.fold_id != geometry[0]
            or binding.fold_id != geometry[0]
            or commitment.result_binding != binding
            or commitment.fold_geometry != geometry
            or commitment.horizon_fold_geometries
            != expected_horizon_geometries
            or type(commitment.global_comparator_coverages) is not tuple
            or len(commitment.global_comparator_coverages) != 2
            or type(commitment.model_records) is not tuple
            or len(commitment.model_records) != 2
            or type(commitment.partition_terminal_counts) is not tuple
            or type(commitment.partition_terminal_roots) is not tuple
            or len(commitment.partition_terminal_counts) != len(FoldPartition)
            or len(commitment.partition_terminal_roots) != len(FoldPartition)
        ):
            raise FormalInputBundleError(
                f"formal fold commitment {index} changed"
            )
        for source_view_id, coverage in zip(
            (CURRENT_VIEW_LABEL, CENSORED_VIEW_LABEL),
            commitment.global_comparator_coverages,
            strict=True,
        ):
            require_formal_global_comparator_coverage(coverage)
            if (
                coverage.schema != GLOBAL_COMPARATOR_COVERAGE_SCHEMA
                or coverage.scope_id != geometry[0]
                or coverage.source_view_id != source_view_id
                or coverage.fold_ids != (geometry[0],)
                or coverage.result_bindings != (binding,)
            ):
                raise FormalInputBundleError(
                    "formal fold comparator coverage binding changed"
                )
        model_arms: list[str] = []
        for model in commitment.model_records:
            if type(model) is not dict:
                raise FormalInputBundleError("formal model commitment changed type")
            if set(model) != {
                "model_id", "model_sha256", "signal_arm", "fold_id",
                "train_start", "train_end_exclusive", "columns",
                "industry_levels", "reference_industry", "firm_coefficients",
                "global_coefficients", "active_training_rows",
            }:
                raise FormalInputBundleError("formal model commitment fields changed")
            _post_id(model["model_id"], "formal model id")
            _post_sha(model["model_sha256"], "formal model hash")
            if model["fold_id"] != geometry[0] or type(model["signal_arm"]) is not str:
                raise FormalInputBundleError("formal model geometry changed")
            model_arms.append(model["signal_arm"])
        if tuple(model_arms) != tuple(arm.value for arm in SignalArm):
            raise FormalInputBundleError("formal model arms changed")
        for partition_index, partition in enumerate(FoldPartition):
            counts = commitment.partition_terminal_counts[partition_index]
            roots = commitment.partition_terminal_roots[partition_index]
            if (
                type(counts) is not tuple or len(counts) != 3
                or counts[0] != partition.value
                or type(counts[1]) is not int or counts[1] < 0
                or type(counts[2]) is not int or counts[2] < 0
                or type(roots) is not tuple or len(roots) != 3
                or roots[0] != partition.value
            ):
                raise FormalInputBundleError("formal partition commitment changed")
            _post_sha(roots[1], "formal current partition root")
            _post_sha(roots[2], "formal censored partition root")
        _post_sha(
            commitment.training_sufficient_stat_commitment_sha256,
            "formal training commitment",
        )
    for source_view_id, coverage in zip(
        (CURRENT_VIEW_LABEL, CENSORED_VIEW_LABEL),
        value.pooled_global_comparator_coverages,
        strict=True,
    ):
        require_formal_global_comparator_coverage(coverage)
        expected = pool_formal_global_comparator_coverages(tuple(
            item.global_comparator_coverages[
                0 if source_view_id == CURRENT_VIEW_LABEL else 1
            ]
            for item in value.fold_commitments
        ))
        if (
            coverage.source_view_id != source_view_id
            or coverage.to_record() != expected.to_record()
        ):
            raise FormalInputBundleError(
                "formal pooled comparator coverage changed"
            )
    if type(value.accepted_risk_pair_record) is not dict:
        raise FormalInputBundleError("accepted-risk projection record changed type")
    return {
        "scoring_contract_id": value.scoring_contract_id,
        "scoring_contract_sha256": value.scoring_contract_sha256,
        "result_bindings": [item.to_record() for item in value.result_bindings],
        "fold_commitments": [item.to_record() for item in value.fold_commitments],
        "pooled_global_comparator_coverages": [
            item.to_record()
            for item in value.pooled_global_comparator_coverages
        ],
        "production_truth_artifact_id": value.production_truth_artifact_id,
        "production_truth_artifact_sha256": value.production_truth_artifact_sha256,
        "accepted_risk_pair_record": value.accepted_risk_pair_record,
        "matched_security_session_count": value.matched_security_session_count,
        "matched_terminal_census_sha256": value.matched_terminal_census_sha256,
        "current_terminal_count": value.current_terminal_count,
        "current_terminal_census_sha256": value.current_terminal_census_sha256,
        "censored_terminal_count": value.censored_terminal_count,
        "censored_terminal_census_sha256": value.censored_terminal_census_sha256,
        "source_views_distinct": value.source_views_distinct,
        "source_views_share_one_census": value.source_views_share_one_census,
        "caller_supplied_scores_accepted": value.caller_supplied_scores_accepted,
        "upstream_truth_and_one_fold_materialization_capacity_authenticated": (
            value.upstream_truth_and_one_fold_materialization_capacity_authenticated
        ),
        "production_capacity_disposition": value.production_capacity_disposition,
        "capabilities": dict(value.capabilities),
    }


def require_formal_production_scoring_projection(
    value: FormalProductionScoringProjection,
) -> FormalProductionScoringProjection:
    if type(value) is not FormalProductionScoringProjection:
        raise FormalInputBundleError("formal scoring projection changed type")
    with _PROJECTION_LOCK:
        registered = _PROJECTIONS.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalInputBundleError(
            "formal scoring projection is not builder-authenticated"
        )
    try:
        topology = (
            id(value.result_bindings), tuple(id(item) for item in value.result_bindings),
            id(value.fold_commitments), tuple(id(item) for item in value.fold_commitments),
            id(value.pooled_global_comparator_coverages),
            tuple(id(item) for item in value.pooled_global_comparator_coverages),
            id(value.accepted_risk_pair_record), id(value.capabilities),
            id(value._canonical_document),
        )
    except AttributeError as exc:
        raise FormalInputBundleError("formal scoring projection changed") from exc
    if (
        registered[1] != value._canonical_document
        or registered[2] != topology
        or value.schema != SCORING_PROJECTION_SCHEMA
        or value.scoring_contract_id != SCORING_CONTRACT_ID
        or value.scoring_contract_sha256 != SCORING_CONTRACT_SHA256
        or len(value.result_bindings) != 6 or len(value.fold_commitments) != 6
        or tuple(item.fold_id for item in value.result_bindings)
        != FORMAL_PRIMARY_FOLD_IDS
        or value.current_terminal_count != value.matched_security_session_count
        or value.censored_terminal_count != value.matched_security_session_count
        or value.source_views_distinct is not True
        or value.source_views_share_one_census is not True
        or value.caller_supplied_scores_accepted is not False
        or value.upstream_truth_and_one_fold_materialization_capacity_authenticated
        is not False
        or value.production_capacity_disposition != _UPSTREAM_CAPACITY_DISPOSITION
        or value.capabilities != tuple(
            (name, False) for name in _POST_QC_CAPABILITY_NAMES
        )
    ):
        raise FormalInputBundleError("formal scoring projection changed")
    for name in (
        "projection_sha256", "production_truth_artifact_sha256",
        "matched_terminal_census_sha256", "current_terminal_census_sha256",
        "censored_terminal_census_sha256",
    ):
        _post_sha(getattr(value, name), name)
    projection_id, digest, expected_payload = _post_identified(
        prefix="arv2-formal-production-scoring-projection-",
        schema=SCORING_PROJECTION_SCHEMA,
        record=_projection_record_from_value(value),
    )
    if (
        expected_payload != value._canonical_document
        or expected_payload != registered[1]
        or value.projection_sha256 != digest
        or value.projection_id != projection_id
    ):
        raise FormalInputBundleError("formal scoring projection identity changed")
    return value


def render_formal_production_scoring_projection_bytes(
    value: FormalProductionScoringProjection,
) -> bytes:
    require_formal_production_scoring_projection(value)
    return bytes(value._canonical_document)
@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalPowerCalibrationBinding:
    receipt_id: str
    receipt_sha256: str
    protocol_id: str
    protocol_sha256: str
    manifest_id: str
    manifest_content_sha256: str
    required_valid_dates: int
    required_connected_components: int
    fixed_h20_test_session_capacity: int
    disposition: str

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


_POWER_BINDING_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalPowerCalibrationBinding],
        weakref.ReferenceType[object],
        tuple[object, ...],
        tuple[object, ...],
        int,
    ],
] = {}
_POWER_BINDING_AUTHORITIES_LOCK = threading.RLock()


def _reset_power_binding_authorities_after_fork() -> None:
    global _POWER_BINDING_AUTHORITIES
    global _POWER_BINDING_AUTHORITIES_LOCK

    _POWER_BINDING_AUTHORITIES = {}
    _POWER_BINDING_AUTHORITIES_LOCK = threading.RLock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_power_binding_authorities_after_fork)


def _forget_power_binding(
    identity: int, reference: weakref.ReferenceType[FormalPowerCalibrationBinding]
) -> None:
    with _POWER_BINDING_AUTHORITIES_LOCK:
        current = _POWER_BINDING_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _POWER_BINDING_AUTHORITIES.pop(identity, None)


def _power_receipt_fingerprint(
    receipt: object,
) -> tuple[object, ...]:
    return (
        type(receipt), receipt.receipt_id, receipt.receipt_hash,
        receipt.protocol_id, receipt.protocol_hash, receipt.manifest_id,
        receipt.manifest_content_sha256, receipt.required_valid_dates,
        receipt.required_connected_components,
        receipt.fixed_h20_test_session_capacity, type(receipt.disposition),
        receipt.disposition,
    )


def _require_supported_power_receipt(receipt: object) -> object:
    """Authenticate either the frozen receipt or its accepted-risk successor."""

    if type(receipt) is PowerCalibrationReceipt:
        return require_loaded_power_calibration_receipt(receipt)
    # Lazy import preserves the existing acyclic formal-input boundary: the
    # accepted-risk bridge itself uses streamed scoring, which imports this
    # module for the compact binding types.
    from .power_calibration_bridge import (
        AcceptedRiskPowerCalibrationReceipt,
        AcceptedRiskPowerCalibrationError,
        require_accepted_risk_power_calibration_receipt,
    )

    if type(receipt) is not AcceptedRiskPowerCalibrationReceipt:
        raise FormalInputBundleError(
            "formal power floor is not a supported authenticated receipt"
        )
    try:
        return require_accepted_risk_power_calibration_receipt(receipt)
    except AcceptedRiskPowerCalibrationError as exc:
        raise FormalInputBundleError(
            "formal power floor is not an authenticated accepted-risk receipt"
        ) from exc


def _power_binding_topology(
    value: FormalPowerCalibrationBinding,
) -> tuple[object, ...]:
    return tuple(
        (field.name, id(getattr(value, field.name)))
        for field in dataclasses.fields(FormalPowerCalibrationBinding)
    )


def build_formal_power_calibration_binding(
    receipt: object,
) -> FormalPowerCalibrationBinding:
    """Freeze a real receipt; this is the sole filesystem-reading boundary."""

    try:
        receipt = _require_supported_power_receipt(receipt)
    except (PowerCalibrationReceiptError, AttributeError, TypeError, ValueError) as exc:
        raise FormalInputBundleError(
            "formal power floor is not a worker-authenticated real receipt"
        ) from exc
    if receipt.disposition is not (
        ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT
    ):
        raise FormalInputBundleError("authenticated power floor is underpowered")
    values: dict[str, object] = {
        "receipt_id": _post_id(receipt.receipt_id, "power receipt_id"),
        "receipt_sha256": _post_sha(receipt.receipt_hash, "power receipt hash"),
        "protocol_id": _post_id(receipt.protocol_id, "power protocol_id"),
        "protocol_sha256": _post_sha(receipt.protocol_hash, "power protocol hash"),
        "manifest_id": _post_id(receipt.manifest_id, "power manifest_id"),
        "manifest_content_sha256": _post_sha(
            receipt.manifest_content_sha256, "power manifest content hash"
        ),
        "required_valid_dates": _post_int(
            receipt.required_valid_dates, "required valid dates", minimum=50
        ),
        "required_connected_components": _post_int(
            receipt.required_connected_components,
            "required connected components",
            minimum=50,
        ),
        "fixed_h20_test_session_capacity": _post_int(
            receipt.fixed_h20_test_session_capacity,
            "fixed H20 capacity",
            minimum=1,
        ),
        "disposition": receipt.disposition.value,
    }
    value = object.__new__(FormalPowerCalibrationBinding)
    for name, item in values.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_power_binding(key, ref)
    )
    with _POWER_BINDING_AUTHORITIES_LOCK:
        _POWER_BINDING_AUTHORITIES[identity] = (
            reference, weakref.ref(receipt), _power_receipt_fingerprint(receipt),
            _power_binding_topology(value), os.getpid(),
        )
    return require_formal_power_calibration_binding(value)


def require_formal_power_calibration_binding(
    value: FormalPowerCalibrationBinding,
) -> FormalPowerCalibrationBinding:
    """Pure identity/topology reauthentication after the receipt freeze."""

    if type(value) is not FormalPowerCalibrationBinding:
        raise FormalInputBundleError("formal power binding changed type")
    with _POWER_BINDING_AUTHORITIES_LOCK:
        registered = _POWER_BINDING_AUTHORITIES.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalInputBundleError("formal power binding is not builder-authenticated")
    receipt = registered[1]()
    if (
        receipt is None
        or _require_supported_power_receipt(receipt) is not receipt
        or _power_receipt_fingerprint(receipt) != registered[2]
        or _power_binding_topology(value) != registered[3]
        or registered[4] != os.getpid()
    ):
        raise FormalInputBundleError("formal power binding parent/topology changed")
    expected = {
        "receipt_id": receipt.receipt_id,
        "receipt_sha256": receipt.receipt_hash,
        "protocol_id": receipt.protocol_id,
        "protocol_sha256": receipt.protocol_hash,
        "manifest_id": receipt.manifest_id,
        "manifest_content_sha256": receipt.manifest_content_sha256,
        "required_valid_dates": receipt.required_valid_dates,
        "required_connected_components": receipt.required_connected_components,
        "fixed_h20_test_session_capacity": receipt.fixed_h20_test_session_capacity,
        "disposition": (
            ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT.value
        ),
    }
    if any(getattr(value, name) != item for name, item in expected.items()):
        raise FormalInputBundleError("formal power binding content changed")
    return value


def _bind_global_coverage_authority_operations(
    *,
    require_source_impl: object,
    build_source_impl: object,
    source_retained_impl: object,
    require_accumulator_impl: object,
    accumulator_retained_impl: object,
    begin_accumulator_impl: object,
    record_session_impl: object,
    finish_accumulator_impl: object,
    initialize_source: object,
    require_source_authority: object,
    initialize_accumulator: object,
    require_accumulator_authority: object,
    record_session_authority: object,
    finalize_accumulator: object,
    private_registry_bytes: object,
) -> tuple[object, ...]:
    operations = (
        require_source_impl,
        build_source_impl,
        source_retained_impl,
        require_accumulator_impl,
        accumulator_retained_impl,
        begin_accumulator_impl,
        record_session_impl,
        finish_accumulator_impl,
        initialize_source,
        require_source_authority,
        initialize_accumulator,
        require_accumulator_authority,
        record_session_authority,
        finalize_accumulator,
        private_registry_bytes,
    )
    if any(not callable(item) for item in operations):
        raise FormalInputBundleError("coverage authority operation changed type")

    def require_source(
        value: FormalGlobalComparatorCoverageSource,
        *,
        deep: bool = True,
    ) -> tuple[FormalGlobalComparatorCoverageSource, _GlobalCoverageSourceState]:
        return require_source_impl(
            value,
            deep=deep,
            _vault_require_source=require_source_authority,
        )

    def build_source(
        *,
        signal_arm: SignalArm,
        batch: ProductionInputBatch,
        global_contract: object,
        endpoint_labels: tuple[EndpointLabelEvidence, ...],
    ) -> FormalGlobalComparatorCoverageSource:
        return build_source_impl(
            signal_arm=signal_arm,
            batch=batch,
            global_contract=global_contract,
            endpoint_labels=endpoint_labels,
            _vault_initialize_source=initialize_source,
        )

    def source_retained(
        source: FormalGlobalComparatorCoverageSource,
    ) -> int:
        return source_retained_impl(
            source,
            _private_registry_bytes=private_registry_bytes,
        )

    def require_accumulator(
        value: FormalGlobalComparatorCoverageAccumulator,
    ) -> tuple[
        FormalGlobalComparatorCoverageAccumulator,
        _GlobalCoverageAccumulatorState,
    ]:
        return require_accumulator_impl(
            value,
            _vault_require_accumulator=require_accumulator_authority,
        )

    def accumulator_retained(
        accumulator: FormalGlobalComparatorCoverageAccumulator,
    ) -> int:
        return accumulator_retained_impl(
            accumulator,
            _private_registry_bytes=private_registry_bytes,
        )

    def begin_accumulator(
        *,
        fold_id: str,
        source: FormalGlobalComparatorCoverageSource,
    ) -> FormalGlobalComparatorCoverageAccumulator:
        # The implementation filters item.eligible_session < test_end from
        # source_state.contributions before constructing its ordinal axis.
        return begin_accumulator_impl(
            fold_id=fold_id,
            source=source,
            _vault_initialize_accumulator=initialize_accumulator,
        )

    def record_session(
        accumulator: FormalGlobalComparatorCoverageAccumulator,
        *,
        decision_session: str,
        census_rows: tuple[EligibleSecuritySession, ...],
        final_rows: tuple[FinalDecisionInput, ...],
        final_refusals: tuple[ScoringRefusal, ...],
        maximum_retained_bytes: int,
    ) -> int:
        return record_session_impl(
            accumulator,
            decision_session=decision_session,
            census_rows=census_rows,
            final_rows=final_rows,
            final_refusals=final_refusals,
            maximum_retained_bytes=maximum_retained_bytes,
            _vault_record_session=record_session_authority,
        )

    def finish_accumulator(
        accumulator: FormalGlobalComparatorCoverageAccumulator,
        *,
        result_binding: ScoringResultBinding,
    ) -> FormalGlobalComparatorCoverage:
        return finish_accumulator_impl(
            accumulator,
            result_binding=result_binding,
            _vault_finalize_accumulator=finalize_accumulator,
        )

    return (
        require_source,
        build_source,
        source_retained,
        require_accumulator,
        accumulator_retained,
        begin_accumulator,
        record_session,
        finish_accumulator,
    )


(
    _coverage_authority_initialize_source,
    _coverage_authority_require_source,
    _coverage_authority_initialize_accumulator,
    _coverage_authority_require_accumulator,
    _coverage_authority_record_session,
    _coverage_authority_finalize_accumulator,
    _coverage_authority_private_registry_bytes,
) = _make_global_coverage_authority_vault(
    _derive_global_coverage_session_transition
)

(
    _require_global_coverage_source,
    build_formal_global_comparator_coverage_source,
    formal_global_comparator_coverage_source_retained_bytes,
    _require_global_coverage_accumulator,
    formal_global_comparator_coverage_accumulator_retained_bytes,
    begin_formal_global_comparator_fold_coverage_from_source,
    record_formal_global_comparator_coverage_session,
    finish_formal_global_comparator_fold_coverage,
) = _bind_global_coverage_authority_operations(
    require_source_impl=_require_global_coverage_source_impl,
    build_source_impl=_build_formal_global_comparator_coverage_source_impl,
    source_retained_impl=(
        _formal_global_comparator_coverage_source_retained_bytes_impl
    ),
    require_accumulator_impl=_require_global_coverage_accumulator_impl,
    accumulator_retained_impl=(
        _formal_global_comparator_coverage_accumulator_retained_bytes_impl
    ),
    begin_accumulator_impl=(
        _begin_formal_global_comparator_fold_coverage_from_source_impl
    ),
    record_session_impl=_record_formal_global_comparator_coverage_session_impl,
    finish_accumulator_impl=(
        _finish_formal_global_comparator_fold_coverage_impl
    ),
    initialize_source=_coverage_authority_initialize_source,
    require_source_authority=_coverage_authority_require_source,
    initialize_accumulator=_coverage_authority_initialize_accumulator,
    require_accumulator_authority=_coverage_authority_require_accumulator,
    record_session_authority=_coverage_authority_record_session,
    finalize_accumulator=_coverage_authority_finalize_accumulator,
    private_registry_bytes=_coverage_authority_private_registry_bytes,
)

# The bound consumers are the only retained references to authority-changing
# operations.  Closure-cell inspection and code mutation are outside the
# reviewed threat model; ordinary module lookup cannot initialize or reseal a
# source/accumulator, obtain a transition primitive, or clear private state.
del _bind_global_coverage_authority_operations
del _require_global_coverage_source_impl
del _build_formal_global_comparator_coverage_source_impl
del _formal_global_comparator_coverage_source_retained_bytes_impl
del _require_global_coverage_accumulator_impl
del _formal_global_comparator_coverage_accumulator_retained_bytes_impl
del _begin_formal_global_comparator_fold_coverage_from_source_impl
del _record_formal_global_comparator_coverage_session_impl
del _finish_formal_global_comparator_fold_coverage_impl
del _derive_global_coverage_session_transition
del _coverage_authority_initialize_source
del _coverage_authority_require_source
del _coverage_authority_initialize_accumulator
del _coverage_authority_require_accumulator
del _coverage_authority_record_session
del _coverage_authority_finalize_accumulator
del _coverage_authority_private_registry_bytes
del _make_global_coverage_authority_vault


__all__ = (
    "AUTHORITY", "CENSORED_VIEW_LABEL", "CURRENT_VIEW_LABEL",
    "DESCRIPTIVE_SENSITIVITY_FOLD_IDS", "FORMAL_PRIMARY_FOLD_IDS",
    "GLOBAL_COMPARATOR_COVERAGE_SCHEMA",
    "GLOBAL_COMPARATOR_COVERAGE_ACCUMULATOR_SCHEMA",
    "GLOBAL_COMPARATOR_COVERAGE_SOURCE_SCHEMA",
    "GLOBAL_COMPARATOR_POOLED_COVERAGE_SCHEMA",
    "FormalCoverageDiagnosticRatio", "FormalCoverageLedger",
    "FormalGlobalComparatorCoverage",
    "FormalGlobalComparatorCoverageAccumulator",
    "FormalGlobalComparatorCoverageSource",
    "FormalInputBundleError", "FormalPowerCalibrationBinding",
    "FormalProductionScoringCensus", "FormalSourceViewScoringCensus",
    "FormalProductionScoringProjection",
    "FormalProductionScoringProjectionBuilder",
    "FormalScoringFoldCommitment", "FormalScoringSessionBlock",
    "HORIZONS", "ProductionScoredDecisionLineage",
    "ProductionScoringCensusRefusal", "SCHEMA", "STATUS",
    "ScoringResultBinding", "build_formal_power_calibration_binding",
    "build_formal_global_comparator_fold_coverages",
    "build_formal_global_comparator_fold_coverage_from_inputs",
    "build_formal_global_comparator_coverage_source",
    "begin_formal_production_scoring_projection",
    "begin_formal_global_comparator_fold_coverage",
    "begin_formal_global_comparator_fold_coverage_from_source",
    "build_formal_production_scoring_census",
    "finish_formal_production_scoring_projection",
    "finish_formal_global_comparator_fold_coverage",
    "formal_global_comparator_coverage_accumulator_retained_bytes",
    "formal_global_comparator_coverage_source_retained_bytes",
    "formal_global_comparator_coverage_source_scoring_inputs",
    "formal_global_comparator_coverage_source_visible_contributions",
    "iter_formal_production_scoring_result_blocks",
    "pool_formal_global_comparator_coverages",
    "record_formal_global_comparator_coverage_session",
    "render_formal_production_scoring_projection_bytes",
    "render_formal_production_scoring_census_bytes",
    "require_formal_global_comparator_coverage",
    "require_formal_power_calibration_binding",
    "require_formal_production_scoring_census",
    "require_formal_production_scoring_projection",
    "require_formal_scoring_session_block",
)
