"""Deterministic production scoring between ARV2 C2 and formal QC inputs.

The C2 bridge intentionally stops at event-level, pre-score rows.  This module
adds the missing decision-session layer without accepting caller-computed
scores.  It authenticates a complete point-in-time security/control census,
binds raw endpoint labels to exact C2 row bytes, builds the firm-specific and
39-alias comparator from the same events, and performs the frozen stock-score
and training-only control-residualization arithmetic.

Everything here is pure and outcome-free.  Callers supply already captured
objects; this module has no file, provider, credential, QuantConnect, Object
Store, price, deployment, order, or trading capability.
"""
from __future__ import annotations

import dataclasses
import threading
import weakref
from collections import defaultdict
from datetime import date, timedelta
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from enum import Enum
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from .production_truth_gate import ProductionTruthArtifact

from data.exchange_calendar import (
    ExchangeCalendarError,
    is_trading_session,
    session_open_instant,
    trading_sessions,
)

from .canonical import (
    canonical_json_bytes,
    format_utc_timestamp,
    parse_date,
    parse_utc_timestamp,
    require_identifier,
    require_sha256,
    require_ticker,
    sha256_bytes,
)
from .formulas import (
    IndependentContribution,
    FormulaError,
    analyst_decimal_context,
    independent_evidence_breadth,
    stock_reliability,
)
from .global_benchmark_contract import (
    GlobalBenchmarkContract,
    GlobalBenchmarkContractError,
    GlobalRatingMapping,
    GlobalRatingMappingRefusal,
    global_rating_delta,
    require_loaded_global_benchmark_contract,
    resolve_global_rating,
)
from .production_input_pipeline import (
    NormalizedPreOutcomeRow,
    ProductionEvidenceAuthority,
    ProductionInputBatch,
    ProductionInputError,
    SignalArm,
    require_production_evidence_authority,
    require_production_input_batch,
)
from .stock_controls import BINARY_COLUMNS, CONTINUOUS_COLUMNS, CONTROL_COLUMNS


class ProductionScoringError(ValueError):
    """The scoring evidence or a deterministic scoring invariant is invalid."""


SCORING_SCHEMA = "arv2-production-paired-scoring-v1"
SCORING_CONTRACT_SCHEMA = "arv2-production-scoring-contract-v1"
CENSUS_SCHEMA = "arv2-production-eligible-security-census-v1"
MODEL_SCHEMA = "arv2-production-control-model-v1"
RESULT_SCHEMA = "arv2-production-control-adjusted-decision-inputs-v1"
HISTORY_START = "2013-01-02"
HALF_LIFE_SESSIONS = 20
MINIMUM_TOTAL_NAMES = 20
MINIMUM_ACTIVE_NAMES = 5
SCORE_CLIP = Decimal("4")
MAD_SCALE = Decimal("1.4826")
CONTROL_COVERAGE_NUMERATOR = 19
CONTROL_COVERAGE_DENOMINATOR = 20
CONTROL_MINIMUM_ROWS = 20
RANK_RELATIVE_THRESHOLD = Decimal("1e-20")
DECIMAL_PRECISION = 50
CLIP_LOW = Decimal("-4")
CLIP_HIGH = Decimal("4")
FORMAL_PRIMARY_FOLD_IDS = tuple(
    f"arv2-wf-test-{year}" for year in range(2020, 2026)
)
DESCRIPTIVE_SENSITIVITY_FOLD_IDS = tuple(
    f"arv2-wf-test-{year}" for year in range(2021, 2026)
)
FORMAL_HORIZON_FOLD_BOUNDARIES = (
    (
        "arv2-wf-test-2020", 1, "2013-01-02", "2018-01-02", "2018-01-03",
        "2020-01-02", "2020-01-03", "2021-01-04",
    ),
    (
        "arv2-wf-test-2020", 5, "2013-01-02", "2018-01-02", "2018-01-09",
        "2020-01-02", "2020-01-09", "2021-01-04",
    ),
    (
        "arv2-wf-test-2020", 20, "2013-01-02", "2018-01-02", "2018-01-31",
        "2020-01-02", "2020-01-31", "2021-01-04",
    ),
    (
        "arv2-wf-test-2020", 60, "2013-01-02", "2018-01-02", "2018-03-29",
        "2020-01-02", "2020-03-30", "2021-01-04",
    ),
    (
        "arv2-wf-test-2021", 1, "2014-01-02", "2019-01-02", "2019-01-03",
        "2021-01-04", "2021-01-05", "2022-01-03",
    ),
    (
        "arv2-wf-test-2021", 5, "2014-01-02", "2019-01-02", "2019-01-09",
        "2021-01-04", "2021-01-11", "2022-01-03",
    ),
    (
        "arv2-wf-test-2021", 20, "2014-01-02", "2019-01-02", "2019-01-31",
        "2021-01-04", "2021-02-02", "2022-01-03",
    ),
    (
        "arv2-wf-test-2021", 60, "2014-01-02", "2019-01-02", "2019-03-29",
        "2021-01-04", "2021-03-31", "2022-01-03",
    ),
    (
        "arv2-wf-test-2022", 1, "2015-01-02", "2020-01-02", "2020-01-03",
        "2022-01-03", "2022-01-04", "2023-01-03",
    ),
    (
        "arv2-wf-test-2022", 5, "2015-01-02", "2020-01-02", "2020-01-09",
        "2022-01-03", "2022-01-10", "2023-01-03",
    ),
    (
        "arv2-wf-test-2022", 20, "2015-01-02", "2020-01-02", "2020-01-31",
        "2022-01-03", "2022-02-01", "2023-01-03",
    ),
    (
        "arv2-wf-test-2022", 60, "2015-01-02", "2020-01-02", "2020-03-30",
        "2022-01-03", "2022-03-30", "2023-01-03",
    ),
    (
        "arv2-wf-test-2023", 1, "2016-01-04", "2021-01-04", "2021-01-05",
        "2023-01-03", "2023-01-04", "2024-01-02",
    ),
    (
        "arv2-wf-test-2023", 5, "2016-01-04", "2021-01-04", "2021-01-11",
        "2023-01-03", "2023-01-10", "2024-01-02",
    ),
    (
        "arv2-wf-test-2023", 20, "2016-01-04", "2021-01-04", "2021-02-02",
        "2023-01-03", "2023-02-01", "2024-01-02",
    ),
    (
        "arv2-wf-test-2023", 60, "2016-01-04", "2021-01-04", "2021-03-31",
        "2023-01-03", "2023-03-30", "2024-01-02",
    ),
    (
        "arv2-wf-test-2024", 1, "2017-01-03", "2022-01-03", "2022-01-04",
        "2024-01-02", "2024-01-03", "2025-01-02",
    ),
    (
        "arv2-wf-test-2024", 5, "2017-01-03", "2022-01-03", "2022-01-10",
        "2024-01-02", "2024-01-09", "2025-01-02",
    ),
    (
        "arv2-wf-test-2024", 20, "2017-01-03", "2022-01-03", "2022-02-01",
        "2024-01-02", "2024-01-31", "2025-01-02",
    ),
    (
        "arv2-wf-test-2024", 60, "2017-01-03", "2022-01-03", "2022-03-30",
        "2024-01-02", "2024-03-28", "2025-01-02",
    ),
    (
        "arv2-wf-test-2025", 1, "2018-01-02", "2023-01-03", "2023-01-04",
        "2025-01-02", "2025-01-03", "2026-01-02",
    ),
    (
        "arv2-wf-test-2025", 5, "2018-01-02", "2023-01-03", "2023-01-10",
        "2025-01-02", "2025-01-10", "2026-01-02",
    ),
    (
        "arv2-wf-test-2025", 20, "2018-01-02", "2023-01-03", "2023-02-01",
        "2025-01-02", "2025-02-03", "2026-01-02",
    ),
    (
        "arv2-wf-test-2025", 60, "2018-01-02", "2023-01-03", "2023-03-30",
        "2025-01-02", "2025-04-01", "2026-01-02",
    ),
)

# Scoring itself is outcome-free and uses the earliest (H1) admissible
# validation/test start.  Each outcome horizon is sliced later by the exact
# reviewed 24-boundary manifest above.  This preserves every H1/H5/H20/H60
# estimand without fitting on validation or test rows.
FORMAL_FOLD_BOUNDARIES = tuple(
    (fold_id, train_start, train_end, validation_start, validation_end,
     test_start, test_end)
    for (
        fold_id, horizon, train_start, train_end, validation_start,
        validation_end, test_start, test_end,
    ) in FORMAL_HORIZON_FOLD_BOUNDARIES
    if horizon == 1
)


def scoring_contract_record() -> dict[str, Any]:
    """Return the static, outcome-free C2-to-decision scoring contract."""

    return {
        "schema": SCORING_CONTRACT_SCHEMA,
        "history_start": HISTORY_START,
        "formal_primary_fold_ids": list(FORMAL_PRIMARY_FOLD_IDS),
        "descriptive_sensitivity_fold_ids": list(DESCRIPTIVE_SENSITIVITY_FOLD_IDS),
        "formal_scoring_fold_boundaries": [
            {
                "fold_id": fold_id,
                "train_start": train_start,
                "train_end_exclusive": train_end,
                "validation_start_after_h1_purge": validation_start,
                "validation_end_exclusive": validation_end,
                "test_start_after_h1_embargo": test_start,
                "test_end_exclusive": test_end,
            }
            for (
                fold_id,
                train_start,
                train_end,
                validation_start,
                validation_end,
                test_start,
                test_end,
            )
            in FORMAL_FOLD_BOUNDARIES
        ],
        "formal_horizon_fold_boundaries": [
            {
                "fold_id": fold_id,
                "horizon_sessions": horizon,
                "train_start": train_start,
                "train_end_exclusive": train_end,
                "validation_start": validation_start,
                "validation_end_exclusive": validation_end,
                "test_start": test_start,
                "test_end_exclusive": test_end,
            }
            for (
                fold_id,
                horizon,
                train_start,
                train_end,
                validation_start,
                validation_end,
                test_start,
                test_end,
            )
            in FORMAL_HORIZON_FOLD_BOUNDARIES
        ],
        "formal_fold_geometry": (
            "outcome_free_scoring_uses_earliest_h1_span_then_each_outcome_"
            "horizon_uses_its_exact_reviewed_purge_and_embargo_boundary"
        ),
        "fold_labels_choose_outcomes": False,
        "production_truth_gate": {
            "required": True,
            "builder_authenticated": True,
            "census": "exact_same_terminal_tuple_objects_as_truth_artifact",
            "c2_parent": "exact_same_evidence_authority_as_paired_batches",
            "q_data": "derived_component_evidence_only",
        },
        "event_processing": {
            "daily_dedupe_key": ["institution_id", "security_id", "eligible_session"],
            "daily_dedupe_conflict": "named_refusal",
            "rating_decay_half_life_sessions": HALF_LIFE_SESSIONS,
            "old_nonzero_contributions_truncated": False,
            "global_comparator": "loaded_exact_39_alias_contract",
            "common_event_components": "same_session_bipartite_security_common_event_graph",
            "contribution_lineage": (
                "one_content_addressed_record_per_deduped_daily_contribution_with_"
                "full_c2_hash_set_publication_instant_and_decayed_firm_weight"
            ),
            "deduped_publication_instant": (
                "earliest_linked_utc_instant_only_when_every_linked_row_has_one"
            ),
            "missing_publication_instant": (
                "any_missing_linked_instant_retained_as_null_for_named_outcome_jump_refusal"
            ),
        },
        "cross_section": {
            "group": "point_in_time_sector",
            "minimum_total_names": MINIMUM_TOTAL_NAMES,
            "minimum_active_names": MINIMUM_ACTIVE_NAMES,
            "location": "median",
            "scale": "mad_times_1_4826",
            "epsilon_substitution": False,
            "zero_mad": "exact_zero_range_totalizes_zero_else_named_sector_refusal",
            "fixed_score_clip": ["-4", "4"],
            "reliability": "independent_effective_n_over_n_plus_3_times_q_data",
        },
        "controls": {
            "continuous_columns": list(CONTINUOUS_COLUMNS),
            "binary_columns": list(BINARY_COLUMNS),
            "continuous_transform": "same_date_median_mad_times_1_4826",
            "binary_transform": "unchanged_exact_zero_or_one",
            "minimum_accepted_coverage": [
                CONTROL_COVERAGE_NUMERATOR,
                CONTROL_COVERAGE_DENOMINATOR,
            ],
            "minimum_accepted_rows": CONTROL_MINIMUM_ROWS,
            "fit": "pooled_equal_weight_active_training_rows_only",
            "design": "intercept_then_25_controls_then_nonreference_industry_dummies",
            "reference_industry": "lexicographically_first_training_level",
            "solver": "decimal_modified_gram_schmidt_qr",
            "decimal_precision": DECIMAL_PRECISION,
            "rank_relative_threshold": "0.00000000000000000001",
            "validation_test": "frozen_training_coefficients",
            "structural_zero": "excluded_from_fit_and_remains_exact_zero",
            "active_residual_clip": ["-4", "4"],
        },
        "output": {
            "one_terminal_per_signal_arm_fold_security_session": True,
            "contains_transformed_25_control_vector": True,
            "contains_outcome_controls": False,
            "contains_daily_returns": False,
            "contains_event_lineage": True,
            "contains_deduped_weighted_contribution_lineage": True,
            "contains_common_event_component": True,
        },
        "capabilities": {
            "filesystem": False,
            "provider": False,
            "credentials": False,
            "prices": False,
            "outcomes": False,
            "quantconnect": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


SCORING_CONTRACT_SHA256 = sha256_bytes(canonical_json_bytes(scoring_contract_record()))
SCORING_CONTRACT_ID = f"arv2-production-scoring-contract-{SCORING_CONTRACT_SHA256[:16]}"


def render_scoring_contract_bytes() -> bytes:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    return canonical_json_bytes(scoring_contract_record())


class ScoreState(str, Enum):
    ACTIVE = "active"
    STRUCTURAL_ZERO = "structural_zero"


class ScoreDisposition(str, Enum):
    INCLUDED_ACTIVE = "included_active"
    INCLUDED_STRUCTURAL_ZERO = "included_structural_zero"
    GLOBAL_LABEL_REFUSED = "global_label_refused"
    GLOBAL_DIRECTION_CONFLICT = "global_direction_conflict"
    DAILY_DEDUPE_CONFLICT = "daily_dedupe_conflict"
    SECTOR_INSUFFICIENT_TOTAL = "sector_insufficient_total"
    SECTOR_INSUFFICIENT_ACTIVE = "sector_insufficient_active"
    SECTOR_ZERO_MAD_FIRM = "sector_zero_mad_firm"
    SECTOR_ZERO_MAD_GLOBAL = "sector_zero_mad_global"
    CONTROL_DATE_UNDERFILLED = "control_date_underfilled"
    CONTROL_DATE_ZERO_MAD = "control_date_zero_mad"
    CENSUS_EVIDENCE_REFUSAL = "census_evidence_refusal"
    UNSEEN_TRAINING_INDUSTRY = "unseen_training_industry"


class FoldPartition(str, Enum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class CensusRefusalReason(str, Enum):
    MISSING_OR_AMBIGUOUS_CLASSIFICATION = "missing_or_ambiguous_classification"
    MISSING_Q_DATA = "missing_q_data"
    MISSING_PREOPEN_CONTROLS = "missing_preopen_controls"
    POST_OPEN_EVIDENCE = "post_open_evidence"
    NON_POINT_IN_TIME_EVIDENCE = "non_point_in_time_evidence"


def _decimal(value: object, name: str) -> Decimal:
    if type(value) is Decimal:
        result = value
    elif type(value) is int:
        result = Decimal(value)
    elif type(value) is str and value and value == value.strip():
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ProductionScoringError(f"{name} must be an exact decimal") from exc
    else:
        raise ProductionScoringError(f"{name} must be exact and cannot be bool/float")
    if not result.is_finite():
        raise ProductionScoringError(f"{name} must be finite")
    return result


def _decimal_text(value: Decimal) -> str:
    return "0" if value == 0 else format(value, "f")


def _fraction_decimal(value: Fraction) -> Decimal:
    if type(value) is not Fraction:
        raise ProductionScoringError("rating delta must be an exact Fraction")
    with analyst_decimal_context():
        return Decimal(value.numerator) / Decimal(value.denominator)


def _require_exact_string(value: object, name: str) -> str:
    if type(value) is not str:
        raise ProductionScoringError(f"{name} must be an exact string")
    return value


def _session_open_text(session: str) -> str:
    try:
        opened = session_open_instant(session)
    except ExchangeCalendarError as exc:
        raise ProductionScoringError(f"{session} has no NYSE session open") from exc
    return format_utc_timestamp(opened)


def _before_open(available_at: str, session: str) -> bool:
    return parse_utc_timestamp(available_at, "available_at") < parse_utc_timestamp(
        _session_open_text(session), "session open"
    )


def _median(values: Iterable[Decimal]) -> Decimal:
    with localcontext(_context()):
        ordered = tuple(sorted(values))
        if not ordered:
            raise ProductionScoringError("median requires at least one value")
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _context() -> Context:
    return Context(
        prec=DECIMAL_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


@dataclasses.dataclass(frozen=True)
class ProductionControlVector:
    """The exact 19 continuous and six binary pre-open controls."""

    values: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        if type(self.values) is not tuple or any(
            type(item) is not tuple or len(item) != 2 for item in self.values
        ):
            raise ProductionScoringError("control values must be exact name/value tuples")
        if tuple(item[0] for item in self.values) != CONTROL_COLUMNS:
            raise ProductionScoringError("control vector columns are missing, unknown, or reordered")
        for name, value in self.values[: len(CONTINUOUS_COLUMNS)]:
            if type(name) is not str or type(value) is not Decimal or not value.is_finite():
                raise ProductionScoringError(f"continuous control {name!r} must be exact Decimal")
        for name, value in self.values[len(CONTINUOUS_COLUMNS) :]:
            if type(name) is not str or type(value) is not int or value not in (0, 1):
                raise ProductionScoringError(f"binary control {name!r} must be exact zero or one")

    def decimal_values(self) -> tuple[Decimal, ...]:
        return tuple(
            value if type(value) is Decimal else Decimal(value)
            for _, value in self.values
        )

    def to_record(self) -> list[list[object]]:
        return [
            [name, value if type(value) is int else _decimal_text(value)]
            for name, value in self.values
        ]

    @property
    def vector_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_record()))


@dataclasses.dataclass(frozen=True)
class EligibleSecuritySession:
    """One complete PIT universe/control row known strictly before the open."""

    decision_session: str
    security_id: str
    issuer_id: str
    share_class_id: str
    listing_id: str
    historical_ticker: str
    sector_id: str
    industry_id: str
    q_data: Decimal
    controls: ProductionControlVector
    source_id: str
    source_sha256: str
    identity_evidence_sha256: str
    identity_available_at: str
    classification_evidence_sha256: str
    classification_available_at: str
    q_data_evidence_sha256: str
    q_data_available_at: str
    control_evidence_sha256: str
    control_available_at: str
    evidence_sha256: str
    control_vector_sha256: str
    point_in_time: bool
    earnings_anchor_signed_session_distance: int | None

    def __post_init__(self) -> None:
        for name in (
            "decision_session", "security_id", "issuer_id", "share_class_id",
            "listing_id", "historical_ticker", "sector_id", "industry_id",
            "source_id", "source_sha256", "identity_evidence_sha256",
            "identity_available_at", "classification_evidence_sha256",
            "classification_available_at", "q_data_evidence_sha256",
            "q_data_available_at", "control_evidence_sha256",
            "control_available_at", "evidence_sha256", "control_vector_sha256",
        ):
            _require_exact_string(getattr(self, name), name)
        parse_date(self.decision_session, "decision_session")
        try:
            if not is_trading_session(self.decision_session):
                raise ProductionScoringError("decision_session must be an NYSE session")
        except ExchangeCalendarError as exc:
            raise ProductionScoringError("decision_session cannot be resolved") from exc
        if self.decision_session < HISTORY_START:
            raise ProductionScoringError("eligible census predates fixed 2013 history")
        for name in (
            "security_id", "issuer_id", "share_class_id", "listing_id",
            "sector_id", "industry_id", "source_id",
        ):
            require_identifier(getattr(self, name), name)
        require_ticker(self.historical_ticker, "historical_ticker")
        for name in (
            "source_sha256", "identity_evidence_sha256",
            "classification_evidence_sha256", "q_data_evidence_sha256",
            "control_evidence_sha256", "evidence_sha256", "control_vector_sha256",
        ):
            require_sha256(getattr(self, name), name)
        if type(self.controls) is not ProductionControlVector:
            raise ProductionScoringError("controls must have the exact production vector type")
        self.controls.__post_init__()
        if self.control_vector_sha256 != self.controls.vector_sha256:
            raise ProductionScoringError("control vector hash does not match exact values")
        quality = _decimal(self.q_data, "q_data")
        if type(self.q_data) is not Decimal or not Decimal(0) <= quality <= Decimal(1):
            raise ProductionScoringError("q_data must be exact Decimal in [0,1]")
        if type(self.point_in_time) is not bool or self.point_in_time is not True:
            raise ProductionScoringError("eligible census row must be point-in-time")
        if (
            self.earnings_anchor_signed_session_distance is not None
            and type(self.earnings_anchor_signed_session_distance) is not int
        ):
            raise ProductionScoringError(
                "earnings anchor distance must be an exact integer or null"
            )
        for name in (
            "identity_available_at", "classification_available_at",
            "q_data_available_at", "control_available_at",
        ):
            parse_utc_timestamp(getattr(self, name), name)
            if not _before_open(getattr(self, name), self.decision_session):
                raise ProductionScoringError(f"{name} was not available before open")
        expected = sha256_bytes(canonical_json_bytes(self.semantic_record()))
        if self.evidence_sha256 != expected:
            raise ProductionScoringError("eligible census evidence hash is not content-derived")

    def semantic_record(self) -> dict[str, Any]:
        return {
            "decision_session": self.decision_session,
            "security_id": self.security_id,
            "issuer_id": self.issuer_id,
            "share_class_id": self.share_class_id,
            "listing_id": self.listing_id,
            "historical_ticker": self.historical_ticker,
            "sector_id": self.sector_id,
            "industry_id": self.industry_id,
            "q_data": _decimal_text(self.q_data),
            "controls": self.controls.to_record(),
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "identity_evidence_sha256": self.identity_evidence_sha256,
            "identity_available_at": self.identity_available_at,
            "classification_evidence_sha256": self.classification_evidence_sha256,
            "classification_available_at": self.classification_available_at,
            "q_data_evidence_sha256": self.q_data_evidence_sha256,
            "q_data_available_at": self.q_data_available_at,
            "control_evidence_sha256": self.control_evidence_sha256,
            "control_available_at": self.control_available_at,
            "control_vector_sha256": self.control_vector_sha256,
            "point_in_time": True,
            "earnings_anchor_signed_session_distance": (
                self.earnings_anchor_signed_session_distance
            ),
        }

    def to_record(self) -> dict[str, Any]:
        return {**self.semantic_record(), "evidence_sha256": self.evidence_sha256}


def build_eligible_security_session(
    *,
    decision_session: str,
    security_id: str,
    issuer_id: str,
    share_class_id: str,
    listing_id: str,
    historical_ticker: str,
    sector_id: str,
    industry_id: str,
    q_data: Decimal,
    controls: ProductionControlVector,
    source_id: str,
    source_sha256: str,
    identity_evidence_sha256: str,
    identity_available_at: str,
    classification_evidence_sha256: str,
    classification_available_at: str,
    q_data_evidence_sha256: str,
    q_data_available_at: str,
    control_evidence_sha256: str,
    control_available_at: str,
    earnings_anchor_signed_session_distance: int | None = None,
) -> EligibleSecuritySession:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    if type(controls) is not ProductionControlVector:
        raise ProductionScoringError("controls must have the exact production vector type")
    controls.__post_init__()
    if type(q_data) is not Decimal or not q_data.is_finite():
        raise ProductionScoringError("q_data must be an exact finite Decimal")
    if (
        earnings_anchor_signed_session_distance is not None
        and type(earnings_anchor_signed_session_distance) is not int
    ):
        raise ProductionScoringError(
            "earnings anchor distance must be an exact integer or null"
        )
    for name, value in (
        ("decision_session", decision_session),
        ("security_id", security_id),
        ("issuer_id", issuer_id),
        ("share_class_id", share_class_id),
        ("listing_id", listing_id),
        ("historical_ticker", historical_ticker),
        ("sector_id", sector_id),
        ("industry_id", industry_id),
        ("source_id", source_id),
        ("source_sha256", source_sha256),
        ("identity_evidence_sha256", identity_evidence_sha256),
        ("identity_available_at", identity_available_at),
        ("classification_evidence_sha256", classification_evidence_sha256),
        ("classification_available_at", classification_available_at),
        ("q_data_evidence_sha256", q_data_evidence_sha256),
        ("q_data_available_at", q_data_available_at),
        ("control_evidence_sha256", control_evidence_sha256),
        ("control_available_at", control_available_at),
    ):
        _require_exact_string(value, name)
    seed = {
        "decision_session": decision_session,
        "security_id": security_id,
        "issuer_id": issuer_id,
        "share_class_id": share_class_id,
        "listing_id": listing_id,
        "historical_ticker": historical_ticker,
        "sector_id": sector_id,
        "industry_id": industry_id,
        "q_data": _decimal_text(_decimal(q_data, "q_data")),
        "controls": controls.to_record(),
        "source_id": source_id,
        "source_sha256": source_sha256,
        "identity_evidence_sha256": identity_evidence_sha256,
        "identity_available_at": identity_available_at,
        "classification_evidence_sha256": classification_evidence_sha256,
        "classification_available_at": classification_available_at,
        "q_data_evidence_sha256": q_data_evidence_sha256,
        "q_data_available_at": q_data_available_at,
        "control_evidence_sha256": control_evidence_sha256,
        "control_available_at": control_available_at,
        "control_vector_sha256": controls.vector_sha256,
        "point_in_time": True,
        "earnings_anchor_signed_session_distance": (
            earnings_anchor_signed_session_distance
        ),
    }
    return EligibleSecuritySession(
        decision_session=decision_session,
        security_id=security_id,
        issuer_id=issuer_id,
        share_class_id=share_class_id,
        listing_id=listing_id,
        historical_ticker=historical_ticker,
        sector_id=sector_id,
        industry_id=industry_id,
        q_data=q_data,
        controls=controls,
        source_id=source_id,
        source_sha256=source_sha256,
        identity_evidence_sha256=identity_evidence_sha256,
        identity_available_at=identity_available_at,
        classification_evidence_sha256=classification_evidence_sha256,
        classification_available_at=classification_available_at,
        q_data_evidence_sha256=q_data_evidence_sha256,
        q_data_available_at=q_data_available_at,
        control_evidence_sha256=control_evidence_sha256,
        control_available_at=control_available_at,
        evidence_sha256=sha256_bytes(canonical_json_bytes(seed)),
        control_vector_sha256=controls.vector_sha256,
        point_in_time=True,
        earnings_anchor_signed_session_distance=(
            earnings_anchor_signed_session_distance
        ),
    )


@dataclasses.dataclass(frozen=True)
class EligibleSecuritySessionRefusal:
    """One eligible universe member whose required PIT evidence was refused."""

    decision_session: str
    security_id: str
    issuer_id: str
    share_class_id: str
    listing_id: str
    historical_ticker: str
    reason: CensusRefusalReason
    source_id: str
    source_sha256: str
    available_at: str | None
    refusal_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "decision_session", "security_id", "issuer_id", "share_class_id",
            "listing_id", "historical_ticker", "source_id", "source_sha256",
            "refusal_sha256",
        ):
            _require_exact_string(getattr(self, name), name)
        parse_date(self.decision_session, "decision_session")
        try:
            if not is_trading_session(self.decision_session):
                raise ProductionScoringError("refused census session must be an NYSE session")
        except ExchangeCalendarError as exc:
            raise ProductionScoringError("refused census session cannot be resolved") from exc
        if self.decision_session < HISTORY_START:
            raise ProductionScoringError("refused census row predates fixed 2013 history")
        for name in (
            "security_id", "issuer_id", "share_class_id", "listing_id", "source_id"
        ):
            require_identifier(getattr(self, name), name)
        require_ticker(self.historical_ticker, "historical_ticker")
        if type(self.reason) is not CensusRefusalReason:
            raise ProductionScoringError("census refusal reason has wrong type")
        require_sha256(self.source_sha256, "source_sha256")
        if self.available_at is not None:
            _require_exact_string(self.available_at, "available_at")
            parse_utc_timestamp(self.available_at, "available_at")
        require_sha256(self.refusal_sha256, "refusal_sha256")
        if self.refusal_sha256 != sha256_bytes(canonical_json_bytes(self.semantic_record())):
            raise ProductionScoringError("census refusal hash is not content-derived")

    def semantic_record(self) -> dict[str, Any]:
        return {
            "decision_session": self.decision_session,
            "security_id": self.security_id,
            "issuer_id": self.issuer_id,
            "share_class_id": self.share_class_id,
            "listing_id": self.listing_id,
            "historical_ticker": self.historical_ticker,
            "reason": self.reason.value,
            "source_id": self.source_id,
            "source_sha256": self.source_sha256,
            "available_at": self.available_at,
        }

    def to_record(self) -> dict[str, Any]:
        return {**self.semantic_record(), "refusal_sha256": self.refusal_sha256}


def build_eligible_security_session_refusal(
    *,
    decision_session: str,
    security_id: str,
    issuer_id: str,
    share_class_id: str,
    listing_id: str,
    historical_ticker: str,
    reason: CensusRefusalReason,
    source_id: str,
    source_sha256: str,
    available_at: str | None,
) -> EligibleSecuritySessionRefusal:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    if type(reason) is not CensusRefusalReason:
        raise ProductionScoringError("census refusal reason has wrong type")
    for name, value in (
        ("decision_session", decision_session),
        ("security_id", security_id),
        ("issuer_id", issuer_id),
        ("share_class_id", share_class_id),
        ("listing_id", listing_id),
        ("historical_ticker", historical_ticker),
        ("source_id", source_id),
        ("source_sha256", source_sha256),
    ):
        _require_exact_string(value, name)
    if available_at is not None:
        _require_exact_string(available_at, "available_at")
    seed = {
        "decision_session": decision_session,
        "security_id": security_id,
        "issuer_id": issuer_id,
        "share_class_id": share_class_id,
        "listing_id": listing_id,
        "historical_ticker": historical_ticker,
        "reason": reason.value,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "available_at": available_at,
    }
    return EligibleSecuritySessionRefusal(
        decision_session=decision_session,
        security_id=security_id,
        issuer_id=issuer_id,
        share_class_id=share_class_id,
        listing_id=listing_id,
        historical_ticker=historical_ticker,
        reason=reason,
        source_id=source_id,
        source_sha256=source_sha256,
        available_at=available_at,
        refusal_sha256=sha256_bytes(canonical_json_bytes(seed)),
    )


@dataclasses.dataclass(frozen=True)
class EndpointLabelEvidence:
    """Raw endpoint labels bound to one exact admitted C2 row."""

    c2_row_sha256: str
    provider_event_id: str
    raw_previous_label: str
    raw_current_label: str
    source_sha256: str
    available_at: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "c2_row_sha256", "provider_event_id", "raw_previous_label",
            "raw_current_label", "source_sha256", "available_at", "evidence_sha256",
        ):
            _require_exact_string(getattr(self, name), name)
        require_sha256(self.c2_row_sha256, "c2_row_sha256")
        require_identifier(self.provider_event_id, "provider_event_id")
        if not self.raw_previous_label or not self.raw_current_label:
            raise ProductionScoringError("endpoint rating labels cannot be empty")
        require_sha256(self.source_sha256, "source_sha256")
        require_sha256(self.evidence_sha256, "evidence_sha256")
        parse_utc_timestamp(self.available_at, "label available_at")
        expected = sha256_bytes(canonical_json_bytes(self.semantic_record()))
        if self.evidence_sha256 != expected:
            raise ProductionScoringError("endpoint label evidence is not content-derived")

    def semantic_record(self) -> dict[str, str]:
        return {
            "c2_row_sha256": self.c2_row_sha256,
            "provider_event_id": self.provider_event_id,
            "raw_previous_label": self.raw_previous_label,
            "raw_current_label": self.raw_current_label,
            "source_sha256": self.source_sha256,
            "available_at": self.available_at,
        }


def build_endpoint_label_evidence(
    *,
    c2_row_sha256: str,
    provider_event_id: str,
    raw_previous_label: str,
    raw_current_label: str,
    source_sha256: str,
    available_at: str,
) -> EndpointLabelEvidence:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    for name, value in (
        ("c2_row_sha256", c2_row_sha256),
        ("provider_event_id", provider_event_id),
        ("raw_previous_label", raw_previous_label),
        ("raw_current_label", raw_current_label),
        ("source_sha256", source_sha256),
        ("available_at", available_at),
    ):
        _require_exact_string(value, name)
    seed = {
        "c2_row_sha256": c2_row_sha256,
        "provider_event_id": provider_event_id,
        "raw_previous_label": raw_previous_label,
        "raw_current_label": raw_current_label,
        "source_sha256": source_sha256,
        "available_at": available_at,
    }
    return EndpointLabelEvidence(
        **seed,
        evidence_sha256=sha256_bytes(canonical_json_bytes(seed)),
    )


@dataclasses.dataclass(frozen=True)
class ProductionScoringFold:
    fold_id: str
    train_start: str
    train_end_exclusive: str
    validation_start: str
    validation_end_exclusive: str
    test_start: str
    test_end_exclusive: str

    def __post_init__(self) -> None:
        for name in (
            "fold_id", "train_start", "train_end_exclusive", "validation_start",
            "validation_end_exclusive", "test_start", "test_end_exclusive",
        ):
            _require_exact_string(getattr(self, name), name)
        require_identifier(self.fold_id, "fold_id")
        boundaries = (
            self.train_start, self.train_end_exclusive, self.validation_start,
            self.validation_end_exclusive, self.test_start, self.test_end_exclusive,
        )
        for value in boundaries:
            parse_date(value, "fold boundary")
            try:
                if not is_trading_session(value):
                    raise ProductionScoringError("fold boundaries must be NYSE sessions")
            except ExchangeCalendarError as exc:
                raise ProductionScoringError("fold boundary cannot be resolved") from exc
        if self.train_start < HISTORY_START:
            raise ProductionScoringError("fold training interval predates fixed history")
        if not (
            self.train_start < self.train_end_exclusive
            <= self.validation_start < self.validation_end_exclusive
            <= self.test_start < self.test_end_exclusive
        ):
            raise ProductionScoringError("fold intervals overlap, reverse, or are empty")

    def partition(self, session: str) -> FoldPartition | None:
        if self.train_start <= session < self.train_end_exclusive:
            return FoldPartition.TRAIN
        if self.validation_start <= session < self.validation_end_exclusive:
            return FoldPartition.VALIDATION
        if self.test_start <= session < self.test_end_exclusive:
            return FoldPartition.TEST
        return None

    def to_record(self) -> dict[str, str]:
        return dataclasses.asdict(self)


def _formal_fold_for_id(fold_id: str) -> ProductionScoringFold:
    matches = tuple(item for item in FORMAL_FOLD_BOUNDARIES if item[0] == fold_id)
    if len(matches) != 1:
        raise ProductionScoringError("formal fold ID is outside the frozen 2020-2025 family")
    (
        _,
        train_start,
        train_end,
        validation_start,
        validation_end,
        test_start,
        test_end,
    ) = matches[0]
    return ProductionScoringFold(
        fold_id=fold_id,
        train_start=train_start,
        train_end_exclusive=train_end,
        validation_start=validation_start,
        validation_end_exclusive=validation_end,
        test_start=test_start,
        test_end_exclusive=test_end,
    )


def formal_horizon_fold_boundary(
    fold_id: str,
    horizon_sessions: int,
) -> tuple[str, int, str, str, str, str, str, str]:
    """Return one exact reviewed fold/horizon boundary without file access."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    if type(fold_id) is not str or fold_id not in FORMAL_PRIMARY_FOLD_IDS:
        raise ProductionScoringError("formal horizon boundary has an unknown fold")
    if type(horizon_sessions) is not int or horizon_sessions not in (1, 5, 20, 60):
        raise ProductionScoringError("formal horizon must be exact 1, 5, 20, or 60")
    matches = tuple(
        item
        for item in FORMAL_HORIZON_FOLD_BOUNDARIES
        if item[0] == fold_id and item[1] == horizon_sessions
    )
    if len(matches) != 1:
        raise ProductionScoringError("formal horizon boundary is not unique")
    return matches[0]


def build_formal_production_scoring_fold(test_year: int) -> ProductionScoringFold:
    """Return the exact outcome-free H1-through-H60 scoring span for one fold."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    if type(test_year) is not int or test_year not in range(2020, 2026):
        raise ProductionScoringError("formal scoring test year must be exact 2020 through 2025")
    return _formal_fold_for_id(f"arv2-wf-test-{test_year}")


@dataclasses.dataclass(frozen=True, init=False)
class ProductionScoringAuthority:
    schema: str
    authority_id: str
    authority_sha256: str
    current_batch: ProductionInputBatch
    censored_batch: ProductionInputBatch
    global_contract: GlobalBenchmarkContract
    truth_artifact: ProductionTruthArtifact
    census_rows: tuple[EligibleSecuritySession, ...]
    census_refusals: tuple[EligibleSecuritySessionRefusal, ...]
    endpoint_labels: tuple[EndpointLabelEvidence, ...]
    provider_access: bool
    outcome_access: bool
    qc_access: bool
    orders: bool
    trading: bool


_SCORING_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType[ProductionScoringAuthority], tuple[object, ...]]
] = {}
_SCORING_AUTHORITIES_LOCK = threading.RLock()


def _authority_record(
    current: ProductionInputBatch,
    censored: ProductionInputBatch,
    contract: GlobalBenchmarkContract,
    truth_artifact: ProductionTruthArtifact,
    census: tuple[EligibleSecuritySession, ...],
    census_refusals: tuple[EligibleSecuritySessionRefusal, ...],
    labels: tuple[EndpointLabelEvidence, ...],
) -> dict[str, Any]:
    return {
        "schema": SCORING_SCHEMA,
        "current_batch_id": current.batch_id,
        "current_batch_sha256": current.batch_sha256,
        "censored_batch_id": censored.batch_id,
        "censored_batch_sha256": censored.batch_sha256,
        "accepted_risk_pair_id": current.pair_id,
        "accepted_risk_pair_sha256": current.pair_sha256,
        "global_map_id": contract.map_id,
        "global_map_sha256": contract.map_hash,
        "production_truth_artifact_id": truth_artifact.artifact_id,
        "production_truth_artifact_sha256": truth_artifact.artifact_sha256,
        "history_start": HISTORY_START,
        "half_life_sessions": HALF_LIFE_SESSIONS,
        "census_rows": [item.to_record() for item in census],
        "census_refusals": [item.to_record() for item in census_refusals],
        "endpoint_labels": [
            {**item.semantic_record(), "evidence_sha256": item.evidence_sha256}
            for item in labels
        ],
        "capabilities": {
            "provider_access": False,
            "outcome_access": False,
            "qc_access": False,
            "orders": False,
            "trading": False,
        },
    }


def _authority_fingerprint(authority: ProductionScoringAuthority) -> tuple[object, ...]:
    return (
        id(authority.current_batch),
        id(authority.censored_batch),
        id(authority.global_contract),
        id(authority.truth_artifact),
        id(authority.census_rows),
        tuple(id(item) for item in authority.census_rows),
        tuple(
            (
                id(item.controls),
                id(item.controls.values),
                tuple(id(value) for value in item.controls.values),
            )
            for item in authority.census_rows
        ),
        id(authority.census_refusals),
        tuple(id(item) for item in authority.census_refusals),
        id(authority.endpoint_labels),
        tuple(id(item) for item in authority.endpoint_labels),
        authority.authority_id,
        authority.authority_sha256,
        canonical_json_bytes(
            _authority_record(
                authority.current_batch,
                authority.censored_batch,
                authority.global_contract,
                authority.truth_artifact,
                authority.census_rows,
                authority.census_refusals,
                authority.endpoint_labels,
            )
        ),
    )


def _forget_authority(identity: int, reference: weakref.ReferenceType[ProductionScoringAuthority]) -> None:
    with _SCORING_AUTHORITIES_LOCK:
        current = _SCORING_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _SCORING_AUTHORITIES.pop(identity, None)


def _normalized_union(
    current: ProductionInputBatch, censored: ProductionInputBatch
) -> dict[str, NormalizedPreOutcomeRow]:
    result: dict[str, NormalizedPreOutcomeRow] = {}
    for row in (*current.normalized_rows, *censored.normalized_rows):
        prior = result.get(row.row_sha256)
        if prior is not None and prior.semantic_record() != row.semantic_record():
            raise ProductionScoringError("one C2 row hash has conflicting semantics")
        result[row.row_sha256] = row
    return result


def _firm_evidence_by_c2_hash(
    authority: ProductionEvidenceAuthority,
    rows: dict[str, NormalizedPreOutcomeRow],
) -> dict[str, object]:
    evidence_by_locator = {item.locator: item for item in authority.row_evidence}
    result: dict[str, object] = {}
    for row_hash, row in rows.items():
        evidence = evidence_by_locator.get(row.source_locator)
        if evidence is None or evidence.firm is None:
            raise ProductionScoringError("admitted C2 row lost firm-label evidence")
        result[row_hash] = evidence.firm
    return result


def _row_evidence_by_c2_hash(
    authority: ProductionEvidenceAuthority,
    rows: dict[str, NormalizedPreOutcomeRow],
) -> dict[str, object]:
    evidence_by_locator = {item.locator: item for item in authority.row_evidence}
    result: dict[str, object] = {}
    for row_hash, row in rows.items():
        evidence = evidence_by_locator.get(row.source_locator)
        if evidence is None:
            raise ProductionScoringError("admitted C2 row lost production evidence")
        result[row_hash] = evidence
    return result


def build_production_scoring_authority(
    current_batch: ProductionInputBatch,
    censored_batch: ProductionInputBatch,
    global_contract: GlobalBenchmarkContract,
    *,
    truth_artifact: ProductionTruthArtifact,
    census_rows: tuple[EligibleSecuritySession, ...],
    endpoint_labels: tuple[EndpointLabelEvidence, ...],
    census_refusals: tuple[EligibleSecuritySessionRefusal, ...] = (),
) -> ProductionScoringAuthority:
    """Authenticate the complete decision-session census and label bridge."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    from .production_truth_gate import (
        ProductionTruthArtifact as ExactProductionTruthArtifact,
        ProductionTruthError,
        require_production_truth_artifact,
    )

    try:
        require_production_input_batch(current_batch)
        require_production_input_batch(censored_batch)
        require_loaded_global_benchmark_contract(global_contract)
        require_production_truth_artifact(truth_artifact)
    except (ProductionInputError, GlobalBenchmarkContractError, ProductionTruthError) as exc:
        raise ProductionScoringError("scoring parent authority did not authenticate") from exc
    if type(truth_artifact) is not ExactProductionTruthArtifact:
        raise ProductionScoringError("scoring truth artifact has wrong type")
    if current_batch.signal_arm is not SignalArm.CURRENT_VINTAGE or (
        censored_batch.signal_arm is not SignalArm.CONSERVATIVE_CENSORED
    ):
        raise ProductionScoringError("scoring batches are not the exact current/censored pair")
    if current_batch.evidence_authority is not censored_batch.evidence_authority or (
        current_batch.pair_id != censored_batch.pair_id
        or current_batch.pair_sha256 != censored_batch.pair_sha256
    ):
        raise ProductionScoringError("scoring arms do not share one accepted-risk capture")
    if (
        truth_artifact.c2_evidence_authority is not current_batch.evidence_authority
        or census_rows is not truth_artifact.accepted_rows
        or census_refusals is not truth_artifact.refusals
    ):
        raise ProductionScoringError(
            "scoring census or C2 parent is not the exact authenticated production truth"
        )
    if type(census_rows) is not tuple or not census_rows or any(
        type(item) is not EligibleSecuritySession for item in census_rows
    ):
        raise ProductionScoringError("eligible census must be a nonempty exact typed tuple")
    for item in census_rows:
        item.__post_init__()
    keys = tuple((item.decision_session, item.security_id) for item in census_rows)
    if keys != tuple(sorted(set(keys))):
        raise ProductionScoringError("eligible census rows must be unique and canonical-sorted")
    if type(census_refusals) is not tuple or any(
        type(item) is not EligibleSecuritySessionRefusal for item in census_refusals
    ):
        raise ProductionScoringError("census refusals must be an exact typed tuple")
    for item in census_refusals:
        item.__post_init__()
    refusal_keys = tuple(
        (item.decision_session, item.security_id) for item in census_refusals
    )
    if refusal_keys != tuple(sorted(set(refusal_keys))) or set(keys) & set(refusal_keys):
        raise ProductionScoringError("census terminals overlap, repeat, or are not sorted")
    if type(endpoint_labels) is not tuple or any(
        type(item) is not EndpointLabelEvidence for item in endpoint_labels
    ):
        raise ProductionScoringError("endpoint labels must be an exact typed tuple")
    for item in endpoint_labels:
        item.__post_init__()
    if tuple(item.c2_row_sha256 for item in endpoint_labels) != tuple(
        sorted(item.c2_row_sha256 for item in endpoint_labels)
    ) or len({item.c2_row_sha256 for item in endpoint_labels}) != len(endpoint_labels):
        raise ProductionScoringError("endpoint label evidence must be unique and hash-sorted")
    union = _normalized_union(current_batch, censored_batch)
    if {item.c2_row_sha256 for item in endpoint_labels} != set(union):
        raise ProductionScoringError("endpoint labels do not exhaust the exact C2 row union")
    firm_evidence = _firm_evidence_by_c2_hash(current_batch.evidence_authority, union)
    row_evidence = _row_evidence_by_c2_hash(
        current_batch.evidence_authority, union
    )
    for item in endpoint_labels:
        row = union[item.c2_row_sha256]
        firm = firm_evidence[item.c2_row_sha256]
        if (
            item.provider_event_id != row.provider_event_id
            or item.raw_previous_label != firm.raw_previous_label
            or item.raw_current_label != firm.raw_current_label
            or item.source_sha256 != row.source_locator.raw_row_sha256
            or item.available_at != firm.available_at
            or parse_utc_timestamp(item.available_at, "label available_at")
            >= parse_utc_timestamp(row.decision_cutoff_at, "decision cutoff")
        ):
            raise ProductionScoringError("endpoint labels are not exact, pre-open C2 evidence")
    census_by_key: dict[
        tuple[str, str], EligibleSecuritySession | EligibleSecuritySessionRefusal
    ] = {
        (item.decision_session, item.security_id): item
        for item in (*census_rows, *census_refusals)
    }
    for row in union.values():
        key = (row.eligible_session, row.security_id)
        census = census_by_key.get(key)
        if census is None:
            raise ProductionScoringError("C2 event has no matching eligible-session census row")
        if (
            census.issuer_id != row.issuer_id
            or census.share_class_id != row.share_class_id
            or census.listing_id != row.listing_id
            or census.historical_ticker != row.historical_ticker
        ):
            raise ProductionScoringError("C2 event and permanent census identity disagree")
        if type(census) is EligibleSecuritySessionRefusal:
            raise ProductionScoringError(
                "admitted C2 event has a refused eligible-session census terminal"
            )
        if type(census) is EligibleSecuritySession:
            evidence = row_evidence[row.row_sha256]
            security = evidence.security
            sector = evidence.sector
            control = evidence.control
            quality = evidence.q_data
            if any(
                item is None for item in (security, sector, control, quality)
            ):
                raise ProductionScoringError(
                    "admitted C2 row lost complete cross-section evidence"
                )
            assert security is not None and sector is not None
            assert control is not None and quality is not None
            if (
                census.sector_id != row.sector_id
                or census.industry_id != row.industry_id
                or census.q_data != row.q_data
                or census.identity_evidence_sha256
                != row.identity_mapping_evidence_sha256
                or census.identity_available_at != security.available_at
                or census.classification_evidence_sha256
                != row.sector_evidence_sha256
                or census.classification_available_at != sector.available_at
                or census.q_data_evidence_sha256
                != row.q_data_evidence_sha256
                or census.q_data_available_at != quality.available_at
                or census.control_evidence_sha256
                != row.control_evidence_sha256
                or census.control_available_at != control.available_at
                or census.control_vector_sha256 != row.control_vector_sha256
            ):
                raise ProductionScoringError(
                    "C2 event and eligible census evidence disagree"
                )
    record = _authority_record(
        current_batch,
        censored_batch,
        global_contract,
        truth_artifact,
        census_rows,
        census_refusals,
        endpoint_labels,
    )
    digest = sha256_bytes(canonical_json_bytes(record))
    value = object.__new__(ProductionScoringAuthority)
    fields: dict[str, object] = {
        "schema": SCORING_SCHEMA,
        "authority_id": f"arv2-production-scoring-{digest[:24]}",
        "authority_sha256": digest,
        "current_batch": current_batch,
        "censored_batch": censored_batch,
        "global_contract": global_contract,
        "truth_artifact": truth_artifact,
        "census_rows": census_rows,
        "census_refusals": census_refusals,
        "endpoint_labels": endpoint_labels,
        "provider_access": False,
        "outcome_access": False,
        "qc_access": False,
        "orders": False,
        "trading": False,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget_authority(key, ref))
    with _SCORING_AUTHORITIES_LOCK:
        _SCORING_AUTHORITIES[identity] = (reference, _authority_fingerprint(value))
    return require_production_scoring_authority(value)


def require_production_scoring_authority(
    authority: ProductionScoringAuthority,
) -> ProductionScoringAuthority:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    from .production_truth_gate import (
        ProductionTruthError,
        require_production_truth_artifact,
    )

    if type(authority) is not ProductionScoringAuthority:
        raise ProductionScoringError("scoring authority requires exact built type")
    with _SCORING_AUTHORITIES_LOCK:
        registered = _SCORING_AUTHORITIES.get(id(authority))
    if registered is None or registered[0]() is not authority:
        raise ProductionScoringError("scoring authority is not builder-authenticated")
    if authority.schema != SCORING_SCHEMA or any(
        type(getattr(authority, name)) is not bool or getattr(authority, name)
        for name in ("provider_access", "outcome_access", "qc_access", "orders", "trading")
    ):
        raise ProductionScoringError("scoring authority surface changed or gained capability")
    try:
        require_production_input_batch(authority.current_batch)
        require_production_input_batch(authority.censored_batch)
        require_loaded_global_benchmark_contract(authority.global_contract)
        require_production_truth_artifact(authority.truth_artifact)
    except (ProductionInputError, GlobalBenchmarkContractError, ProductionTruthError) as exc:
        raise ProductionScoringError("scoring parent changed after authentication") from exc
    if (
        authority.truth_artifact.c2_evidence_authority
        is not authority.current_batch.evidence_authority
        or authority.census_rows is not authority.truth_artifact.accepted_rows
        or authority.census_refusals is not authority.truth_artifact.refusals
    ):
        raise ProductionScoringError("scoring truth binding changed after authentication")
    if type(authority.census_rows) is not tuple or any(
        type(item) is not EligibleSecuritySession for item in authority.census_rows
    ) or type(authority.census_refusals) is not tuple or any(
        type(item) is not EligibleSecuritySessionRefusal
        for item in authority.census_refusals
    ) or type(authority.endpoint_labels) is not tuple or any(
        type(item) is not EndpointLabelEvidence for item in authority.endpoint_labels
    ):
        raise ProductionScoringError("scoring evidence container topology changed")
    for item in authority.census_rows:
        item.__post_init__()
    for item in authority.census_refusals:
        item.__post_init__()
    for item in authority.endpoint_labels:
        item.__post_init__()
    if _authority_fingerprint(authority) != registered[1]:
        raise ProductionScoringError("scoring authority changed after authentication")
    record = _authority_record(
        authority.current_batch,
        authority.censored_batch,
        authority.global_contract,
        authority.truth_artifact,
        authority.census_rows,
        authority.census_refusals,
        authority.endpoint_labels,
    )
    digest = sha256_bytes(canonical_json_bytes(record))
    if authority.authority_sha256 != digest or authority.authority_id != (
        f"arv2-production-scoring-{digest[:24]}"
    ):
        raise ProductionScoringError("scoring authority identity is not content-derived")
    return authority


@dataclasses.dataclass(frozen=True)
class EventScoringTerminal:
    signal_arm: SignalArm
    c2_row_sha256: str
    provider_event_id: str
    disposition: ScoreDisposition
    linked_c2_row_sha256s: tuple[str, ...]
    terminal_sha256: str

    def __post_init__(self) -> None:
        if type(self.signal_arm) is not SignalArm or type(self.disposition) is not ScoreDisposition:
            raise ProductionScoringError("event terminal enum has wrong type")
        require_sha256(self.c2_row_sha256, "c2_row_sha256")
        require_identifier(self.provider_event_id, "provider_event_id")
        if type(self.linked_c2_row_sha256s) is not tuple or (
            self.linked_c2_row_sha256s != tuple(sorted(set(self.linked_c2_row_sha256s)))
        ):
            raise ProductionScoringError("linked C2 row hashes must be unique and sorted")
        for value in self.linked_c2_row_sha256s:
            require_sha256(value, "linked_c2_row_sha256")
        require_sha256(self.terminal_sha256, "terminal_sha256")
        if self.terminal_sha256 != sha256_bytes(canonical_json_bytes(self.semantic_record())):
            raise ProductionScoringError("event terminal hash is not content-derived")

    def semantic_record(self) -> dict[str, Any]:
        return {
            "signal_arm": self.signal_arm.value,
            "c2_row_sha256": self.c2_row_sha256,
            "provider_event_id": self.provider_event_id,
            "disposition": self.disposition.value,
            "linked_c2_row_sha256s": list(self.linked_c2_row_sha256s),
        }

    def to_record(self) -> dict[str, Any]:
        return {**self.semantic_record(), "terminal_sha256": self.terminal_sha256}


@dataclasses.dataclass(frozen=True)
class ContributionLineage:
    """One deduped contribution and the exact pre-outcome inputs to its weight."""

    representative_c2_row_sha256: str
    linked_c2_row_sha256s: tuple[str, ...]
    representative_provider_event_id: str
    decision_session: str
    security_id: str
    institution_id: str
    common_event_id: str
    rating_action: str
    publication_at_utc: str | None
    eligible_session: str
    age_sessions: int
    decay_weight: Decimal
    firm_absolute_decayed_weight: Decimal
    lineage_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "representative_c2_row_sha256",
            "representative_provider_event_id",
            "decision_session",
            "security_id",
            "institution_id",
            "common_event_id",
            "rating_action",
            "eligible_session",
            "lineage_sha256",
        ):
            _require_exact_string(getattr(self, name), name)
        require_sha256(self.representative_c2_row_sha256, "representative C2 row hash")
        require_sha256(self.lineage_sha256, "contribution lineage_sha256")
        for name in (
            "representative_provider_event_id",
            "security_id",
            "institution_id",
            "common_event_id",
        ):
            require_identifier(getattr(self, name), name)
        if self.rating_action not in ("upgrades", "downgrades"):
            raise ProductionScoringError("contribution rating action changed")
        parse_date(self.decision_session, "contribution decision_session")
        parse_date(self.eligible_session, "contribution eligible_session")
        if self.eligible_session > self.decision_session:
            raise ProductionScoringError("contribution lineage contains a future event")
        if self.publication_at_utc is not None:
            _require_exact_string(self.publication_at_utc, "publication_at_utc")
            publication = parse_utc_timestamp(self.publication_at_utc, "publication_at_utc")
            if publication >= parse_utc_timestamp(
                _session_open_text(self.eligible_session), "eligible session open"
            ):
                raise ProductionScoringError("publication instant is not before eligible open")
        if type(self.linked_c2_row_sha256s) is not tuple or (
            not self.linked_c2_row_sha256s
            or self.linked_c2_row_sha256s
            != tuple(sorted(set(self.linked_c2_row_sha256s)))
            or self.representative_c2_row_sha256 not in self.linked_c2_row_sha256s
        ):
            raise ProductionScoringError("deduped contribution C2 lineage is not exhaustive")
        for digest in self.linked_c2_row_sha256s:
            require_sha256(digest, "linked C2 row hash")
        if type(self.age_sessions) is not int or self.age_sessions < 0:
            raise ProductionScoringError("contribution age must be a nonnegative exact integer")
        for name in ("decay_weight", "firm_absolute_decayed_weight"):
            value = getattr(self, name)
            if type(value) is not Decimal or not value.is_finite():
                raise ProductionScoringError(f"{name} must be an exact finite Decimal")
        if not Decimal(0) < self.decay_weight <= Decimal(1):
            raise ProductionScoringError("contribution decay weight must be in (0,1]")
        if self.firm_absolute_decayed_weight <= 0:
            raise ProductionScoringError(
                "firm absolute decayed contribution weight must be positive"
            )
        if self.lineage_sha256 != sha256_bytes(canonical_json_bytes(self.semantic_record())):
            raise ProductionScoringError("contribution lineage hash is not content-derived")

    def semantic_record(self) -> dict[str, Any]:
        return {
            "representative_c2_row_sha256": self.representative_c2_row_sha256,
            "linked_c2_row_sha256s": list(self.linked_c2_row_sha256s),
            "representative_provider_event_id": self.representative_provider_event_id,
            "decision_session": self.decision_session,
            "security_id": self.security_id,
            "institution_id": self.institution_id,
            "common_event_id": self.common_event_id,
            "rating_action": self.rating_action,
            "publication_at_utc": self.publication_at_utc,
            "eligible_session": self.eligible_session,
            "age_sessions": self.age_sessions,
            "decay_weight": _decimal_text(self.decay_weight),
            "firm_absolute_decayed_weight": _decimal_text(
                self.firm_absolute_decayed_weight
            ),
        }

    def to_record(self) -> dict[str, Any]:
        return {**self.semantic_record(), "lineage_sha256": self.lineage_sha256}


@dataclasses.dataclass(frozen=True)
class _DailyContribution:
    representative_c2_row_sha256: str
    provider_event_id: str
    security_id: str
    institution_id: str
    common_event_id: str
    rating_action: str
    publication_at_utc: str | None
    eligible_session: str
    firm_delta: Fraction
    global_delta: Fraction
    linked_c2_row_sha256s: tuple[str, ...]


def _contribution_lineage(
    decision_session: str,
    contribution: _DailyContribution,
    age_sessions: int,
    decay_weight: Decimal,
    firm_decayed_contribution: Decimal,
) -> ContributionLineage:
    seed = {
        "representative_c2_row_sha256": contribution.representative_c2_row_sha256,
        "linked_c2_row_sha256s": list(contribution.linked_c2_row_sha256s),
        "representative_provider_event_id": contribution.provider_event_id,
        "decision_session": decision_session,
        "security_id": contribution.security_id,
        "institution_id": contribution.institution_id,
        "common_event_id": contribution.common_event_id,
        "rating_action": contribution.rating_action,
        "publication_at_utc": contribution.publication_at_utc,
        "eligible_session": contribution.eligible_session,
        "age_sessions": age_sessions,
        "decay_weight": _decimal_text(decay_weight),
        "firm_absolute_decayed_weight": _decimal_text(
            firm_decayed_contribution.copy_abs()
        ),
    }
    return ContributionLineage(
        representative_c2_row_sha256=contribution.representative_c2_row_sha256,
        linked_c2_row_sha256s=contribution.linked_c2_row_sha256s,
        representative_provider_event_id=contribution.provider_event_id,
        decision_session=decision_session,
        security_id=contribution.security_id,
        institution_id=contribution.institution_id,
        common_event_id=contribution.common_event_id,
        rating_action=contribution.rating_action,
        publication_at_utc=contribution.publication_at_utc,
        eligible_session=contribution.eligible_session,
        age_sessions=age_sessions,
        decay_weight=decay_weight,
        firm_absolute_decayed_weight=firm_decayed_contribution.copy_abs(),
        lineage_sha256=sha256_bytes(canonical_json_bytes(seed)),
    )


def _contribution_lineage_topology(
    values: tuple[ContributionLineage, ...],
) -> tuple[object, ...]:
    return (
        id(values),
        tuple(
            (id(item), id(item.linked_c2_row_sha256s))
            for item in values
        ),
    )


def _terminal(
    arm: SignalArm,
    row: NormalizedPreOutcomeRow,
    disposition: ScoreDisposition,
    linked: tuple[str, ...],
) -> EventScoringTerminal:
    seed = {
        "signal_arm": arm.value,
        "c2_row_sha256": row.row_sha256,
        "provider_event_id": row.provider_event_id,
        "disposition": disposition.value,
        "linked_c2_row_sha256s": list(linked),
    }
    return EventScoringTerminal(
        signal_arm=arm,
        c2_row_sha256=row.row_sha256,
        provider_event_id=row.provider_event_id,
        disposition=disposition,
        linked_c2_row_sha256s=linked,
        terminal_sha256=sha256_bytes(canonical_json_bytes(seed)),
    )


def _global_delta(
    contract: GlobalBenchmarkContract,
    label: EndpointLabelEvidence,
    row: NormalizedPreOutcomeRow,
    *,
    resolved_labels: dict[
        str, GlobalRatingMapping | GlobalRatingMappingRefusal
    ] | None = None,
) -> Fraction | ScoreDisposition:
    previous = (
        resolve_global_rating(contract, label.raw_previous_label)
        if resolved_labels is None
        else resolved_labels[label.raw_previous_label]
    )
    current = (
        resolve_global_rating(contract, label.raw_current_label)
        if resolved_labels is None
        else resolved_labels[label.raw_current_label]
    )
    if type(previous) is GlobalRatingMappingRefusal or type(current) is GlobalRatingMappingRefusal:
        return ScoreDisposition.GLOBAL_LABEL_REFUSED
    if type(previous) is not GlobalRatingMapping or type(current) is not GlobalRatingMapping:
        raise ProductionScoringError("global resolver returned a hostile result type")
    if resolved_labels is None:
        try:
            delta = global_rating_delta(contract, previous, current)
        except GlobalBenchmarkContractError as exc:
            raise ProductionScoringError("global mapping failed reauthentication") from exc
    else:
        # The cache is populated only by ``resolve_global_rating`` after the
        # exact contract has authenticated at this helper boundary.  Avoiding
        # another filesystem-backed contract authentication for every event is
        # essential at production scale; the enclosing source reauthenticates
        # the derived graph before it can be sealed.
        delta = current.score - previous.score
    if (row.raw_action == "upgrades" and delta < 0) or (
        row.raw_action == "downgrades" and delta > 0
    ):
        return ScoreDisposition.GLOBAL_DIRECTION_CONFLICT
    return delta


def _daily_contributions_from_inputs(
    global_contract: GlobalBenchmarkContract,
    endpoint_labels: tuple[EndpointLabelEvidence, ...],
    batch: ProductionInputBatch,
    *,
    resolved_labels: dict[
        str, GlobalRatingMapping | GlobalRatingMappingRefusal
    ] | None = None,
) -> tuple[tuple[_DailyContribution, ...], tuple[EventScoringTerminal, ...]]:
    """Build the exact event contribution census from authenticated parents.

    The production-scale successor cannot construct a ``ProductionScoringAuthority``
    because that legacy object retains the complete production-truth graph.  This
    helper freezes the smaller operation the legacy builder actually needs.  Its
    callers remain responsible for authenticating the contract, label evidence,
    and input batch before entering this internal boundary.
    """

    labels = {item.c2_row_sha256: item for item in endpoint_labels}
    terminals: dict[str, EventScoringTerminal] = {}
    groups: dict[
        tuple[str, str, str], list[NormalizedPreOutcomeRow]
    ] = defaultdict(list)
    for row in batch.normalized_rows:
        groups[(row.institution_id, row.security_id, row.eligible_session)].append(row)
    contributions: list[_DailyContribution] = []
    for key in sorted(groups):
        firm_group = groups[key]
        firm_linked = tuple(sorted(item.row_sha256 for item in firm_group))
        firm_signatures = {
            (
                item.previous_score,
                item.current_score,
                item.common_event_id,
                item.raw_action,
            )
            for item in firm_group
        }
        # Firm-arm daily dedupe is upstream of every global-map exclusion.
        # Otherwise an unmapped sibling could disappear and let a conflicting
        # mapped row enter the paired scorer even though the firm baseline
        # correctly refused the institution/security/day.
        if len(firm_signatures) != 1:
            for row in firm_group:
                terminals[row.row_sha256] = _terminal(
                    batch.signal_arm,
                    row,
                    ScoreDisposition.DAILY_DEDUPE_CONFLICT,
                    firm_linked,
                )
            continue
        paired_group: list[tuple[NormalizedPreOutcomeRow, Fraction]] = []
        for row in firm_group:
            delta = _global_delta(
                global_contract,
                labels[row.row_sha256],
                row,
                resolved_labels=resolved_labels,
            )
            if type(delta) is ScoreDisposition:
                terminals[row.row_sha256] = _terminal(
                    batch.signal_arm, row, delta, (row.row_sha256,)
                )
            else:
                paired_group.append((row, delta))
        if not paired_group:
            continue
        linked = tuple(sorted(item[0].row_sha256 for item in paired_group))
        paired_signatures = {
            (item[1], item[0].common_event_id, item[0].raw_action)
            for item in paired_group
        }
        if len(paired_signatures) != 1:
            for row, _ in paired_group:
                terminals[row.row_sha256] = _terminal(
                    batch.signal_arm,
                    row,
                    ScoreDisposition.DAILY_DEDUPE_CONFLICT,
                    linked,
                )
            continue
        representative = min(
            paired_group,
            key=lambda item: (item[0].provider_event_id, item[0].row_sha256),
        )
        row, global_delta_value = representative
        publication_at_utc = (
            None
            if any(item[0].publication_at_utc is None for item in paired_group)
            else min(
                item[0].publication_at_utc
                for item in paired_group
                if item[0].publication_at_utc is not None
            )
        )
        contributions.append(
            _DailyContribution(
                representative_c2_row_sha256=row.row_sha256,
                provider_event_id=row.provider_event_id,
                security_id=row.security_id,
                institution_id=row.institution_id,
                common_event_id=row.common_event_id,
                rating_action=row.raw_action,
                publication_at_utc=publication_at_utc,
                eligible_session=row.eligible_session,
                firm_delta=row.rating_change,
                global_delta=global_delta_value,
                linked_c2_row_sha256s=linked,
            )
        )
        for member, _ in paired_group:
            terminals[member.row_sha256] = _terminal(
                batch.signal_arm,
                member,
                ScoreDisposition.INCLUDED_ACTIVE,
                linked,
            )
    if set(terminals) != {row.row_sha256 for row in batch.normalized_rows}:
        raise ProductionScoringError("event scoring census is not exhaustive")
    return (
        tuple(sorted(contributions, key=lambda item: (item.eligible_session, item.security_id, item.institution_id))),
        tuple(terminals[key] for key in sorted(terminals)),
    )


def _daily_contributions(
    authority: ProductionScoringAuthority,
    batch: ProductionInputBatch,
) -> tuple[tuple[_DailyContribution, ...], tuple[EventScoringTerminal, ...]]:
    return _daily_contributions_from_inputs(
        authority.global_contract,
        authority.endpoint_labels,
        batch,
    )


def _session_ordinals(
    census: tuple[EligibleSecuritySession, ...],
    contributions: tuple[_DailyContribution, ...],
) -> dict[str, int]:
    values = [item.decision_session for item in census]
    values.extend(item.eligible_session for item in contributions)
    start = min(values)
    end = date.fromisoformat(max(values)) + timedelta(days=8)
    try:
        sessions = tuple(
            item.isoformat()
            for item in trading_sessions(date.fromisoformat(start), end)
            if item <= date.fromisoformat(max(values))
        )
    except ExchangeCalendarError as exc:
        raise ProductionScoringError("scoring session axis cannot be resolved") from exc
    ordinals = {value: index for index, value in enumerate(sessions)}
    if any(value not in ordinals for value in values):
        raise ProductionScoringError("event or census date escaped the NYSE axis")
    return ordinals


def _decay(age: int) -> Decimal:
    if type(age) is not int or age < 0:
        raise ProductionScoringError("event age must be a nonnegative session count")
    with analyst_decimal_context():
        whole, remainder = divmod(age, HALF_LIFE_SESSIONS)
        weight = Decimal("0.5") ** whole
        if remainder:
            exponent = -Decimal(remainder) / Decimal(HALF_LIFE_SESSIONS)
            weight *= (exponent * Decimal(2).ln()).exp()
        return +weight


def _stable_sum(values: Iterable[Decimal]) -> Decimal:
    with localcontext(_context()):
        return sum(sorted(values, key=lambda item: (abs(item), item)), Decimal(0))


def _normalize_sector(
    raw: dict[str, Decimal],
    active: set[str],
    members: tuple[str, ...],
) -> tuple[dict[str, Decimal] | None, ScoreDisposition | None]:
    if len(members) < MINIMUM_TOTAL_NAMES:
        return None, ScoreDisposition.SECTOR_INSUFFICIENT_TOTAL
    active_count = sum(item in active for item in members)
    if active_count < MINIMUM_ACTIVE_NAMES:
        return None, ScoreDisposition.SECTOR_INSUFFICIENT_ACTIVE
    with analyst_decimal_context():
        median = _median(raw[item] for item in members)
        mad = _median(abs(raw[item] - median) for item in members)
        if mad == 0:
            if min(raw[item] for item in members) == max(raw[item] for item in members):
                return {item: Decimal(0) for item in members}, None
            return None, ScoreDisposition.SECTOR_ZERO_MAD_FIRM
        scale = MAD_SCALE * mad
        return {
            item: max(-SCORE_CLIP, min(SCORE_CLIP, (raw[item] - median) / scale))
            for item in members
        }, None


def _transform_controls(
    rows: tuple[EligibleSecuritySession, ...],
    eligible_count: int,
) -> tuple[dict[str, tuple[Decimal, ...]] | None, ScoreDisposition | None]:
    if type(eligible_count) is not int or eligible_count < len(rows):
        raise ProductionScoringError("control coverage denominator is invalid")
    if len(rows) < CONTROL_MINIMUM_ROWS or (
        len(rows) * CONTROL_COVERAGE_DENOMINATOR
        < eligible_count * CONTROL_COVERAGE_NUMERATOR
    ):
        return None, ScoreDisposition.CONTROL_DATE_UNDERFILLED
    raw = {item.security_id: item.controls.decimal_values() for item in rows}
    medians: list[Decimal] = []
    scales: list[Decimal] = []
    for index in range(len(CONTINUOUS_COLUMNS)):
        median = _median(values[index] for values in raw.values())
        mad = _median(abs(values[index] - median) for values in raw.values())
        if mad == 0:
            return None, ScoreDisposition.CONTROL_DATE_ZERO_MAD
        medians.append(median)
        with localcontext(_context()):
            scales.append(mad * MAD_SCALE)
    transformed: dict[str, tuple[Decimal, ...]] = {}
    with localcontext(_context()):
        for security_id, values in raw.items():
            transformed[security_id] = (
                *(
                    (values[index] - medians[index]) / scales[index]
                    for index in range(len(CONTINUOUS_COLUMNS))
                ),
                *values[len(CONTINUOUS_COLUMNS) :],
            )
    return transformed, None


def _component_ids(
    session: str,
    security_ids: tuple[str, ...],
    contributions: tuple[_DailyContribution, ...],
) -> dict[str, str]:
    adjacency: dict[str, set[str]] = {f"s:{value}": set() for value in security_ids}
    for item in contributions:
        security_node = f"s:{item.security_id}"
        event_node = f"e:{item.common_event_id}"
        adjacency.setdefault(security_node, set()).add(event_node)
        adjacency.setdefault(event_node, set()).add(security_node)
    result: dict[str, str] = {}
    seen: set[str] = set()
    for security_id in security_ids:
        root = f"s:{security_id}"
        if root in seen:
            continue
        stack = [root]
        nodes: list[str] = []
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            nodes.append(node)
            stack.extend(sorted(adjacency[node] - seen, reverse=True))
        digest = sha256_bytes(canonical_json_bytes({
            "decision_session": session,
            "nodes": sorted(nodes),
        }))
        component = f"arv2_component_{digest[:24]}"
        for node in nodes:
            if node.startswith("s:"):
                result[node[2:]] = component
    if set(result) != set(security_ids):
        raise ProductionScoringError("common-event component graph is incomplete")
    return result


@dataclasses.dataclass(frozen=True)
class PrecontrolDecisionRow:
    signal_arm: SignalArm
    fold_id: str
    partition: FoldPartition
    decision_session: str
    security_id: str
    issuer_id: str
    share_class_id: str
    listing_id: str
    historical_ticker: str
    sector_id: str
    industry_id: str
    state: ScoreState
    firm_reliable_score: Decimal
    global_reliable_score: Decimal
    transformed_controls: tuple[Decimal, ...]
    realized_volatility_60d: Decimal
    earnings_anchor_signed_session_distance: int | None
    common_event_component_id: str
    contributing_c2_row_sha256s: tuple[str, ...]
    contributions: tuple[ContributionLineage, ...]
    census_evidence_sha256: str
    row_sha256: str

    def __post_init__(self) -> None:
        if type(self.signal_arm) is not SignalArm or type(self.partition) is not FoldPartition or type(self.state) is not ScoreState:
            raise ProductionScoringError("precontrol row enum has wrong type")
        for name in (
            "fold_id", "decision_session", "security_id", "issuer_id", "share_class_id",
            "listing_id", "historical_ticker", "sector_id", "industry_id",
            "common_event_component_id", "census_evidence_sha256", "row_sha256",
        ):
            _require_exact_string(getattr(self, name), name)
        require_identifier(self.fold_id, "fold_id")
        parse_date(self.decision_session, "decision_session")
        for name in ("security_id", "issuer_id", "share_class_id", "listing_id", "sector_id", "industry_id", "common_event_component_id"):
            require_identifier(getattr(self, name), name)
        require_ticker(self.historical_ticker, "historical_ticker")
        for name in ("firm_reliable_score", "global_reliable_score"):
            value = getattr(self, name)
            if type(value) is not Decimal or not value.is_finite():
                raise ProductionScoringError(f"{name} must be exact finite Decimal")
        if (
            type(self.realized_volatility_60d) is not Decimal
            or not self.realized_volatility_60d.is_finite()
        ):
            raise ProductionScoringError(
                "raw realized_volatility_60d must be exact finite Decimal"
            )
        if (
            self.earnings_anchor_signed_session_distance is not None
            and type(self.earnings_anchor_signed_session_distance) is not int
        ):
            raise ProductionScoringError(
                "earnings anchor distance must be an exact integer or null"
            )
        if type(self.transformed_controls) is not tuple or len(self.transformed_controls) != len(CONTROL_COLUMNS) or any(
            type(value) is not Decimal or not value.is_finite() for value in self.transformed_controls
        ):
            raise ProductionScoringError("transformed controls have wrong exact shape")
        if self.contributing_c2_row_sha256s != tuple(sorted(set(self.contributing_c2_row_sha256s))):
            raise ProductionScoringError("precontrol lineage hashes must be unique and sorted")
        for value in (*self.contributing_c2_row_sha256s, self.census_evidence_sha256, self.row_sha256):
            require_sha256(value, "precontrol hash")
        if type(self.contributions) is not tuple or any(
            type(item) is not ContributionLineage for item in self.contributions
        ):
            raise ProductionScoringError("precontrol contribution lineage changed type")
        for item in self.contributions:
            item.__post_init__()
            if (
                item.decision_session != self.decision_session
                or item.security_id != self.security_id
            ):
                raise ProductionScoringError("contribution lineage crossed a decision row")
        if self.contributions != tuple(
            sorted(self.contributions, key=lambda item: item.lineage_sha256)
        ) or len({item.lineage_sha256 for item in self.contributions}) != len(
            self.contributions
        ):
            raise ProductionScoringError("contribution lineage is duplicated or unordered")
        linked = tuple(
            sorted(
                {
                    digest
                    for item in self.contributions
                    for digest in item.linked_c2_row_sha256s
                }
            )
        )
        if linked != self.contributing_c2_row_sha256s:
            raise ProductionScoringError("contribution lineage does not exhaust C2 row hashes")
        if (self.state is ScoreState.STRUCTURAL_ZERO) != (not self.contributing_c2_row_sha256s):
            raise ProductionScoringError("structural-zero state and event lineage disagree")
        if self.state is ScoreState.STRUCTURAL_ZERO and (
            self.firm_reliable_score != 0 or self.global_reliable_score != 0
        ):
            raise ProductionScoringError("structural zero must remain exact zero before controls")
        if self.row_sha256 != sha256_bytes(canonical_json_bytes(self.semantic_record())):
            raise ProductionScoringError("precontrol row hash is not content-derived")

    def semantic_record(self) -> dict[str, Any]:
        return {
            "signal_arm": self.signal_arm.value,
            "fold_id": self.fold_id,
            "partition": self.partition.value,
            "decision_session": self.decision_session,
            "security_id": self.security_id,
            "issuer_id": self.issuer_id,
            "share_class_id": self.share_class_id,
            "listing_id": self.listing_id,
            "historical_ticker": self.historical_ticker,
            "sector_id": self.sector_id,
            "industry_id": self.industry_id,
            "state": self.state.value,
            "firm_reliable_score": _decimal_text(self.firm_reliable_score),
            "global_reliable_score": _decimal_text(self.global_reliable_score),
            "transformed_controls": [_decimal_text(item) for item in self.transformed_controls],
            "realized_volatility_60d": _decimal_text(
                self.realized_volatility_60d
            ),
            "earnings_anchor_signed_session_distance": (
                self.earnings_anchor_signed_session_distance
            ),
            "common_event_component_id": self.common_event_component_id,
            "contributing_c2_row_sha256s": list(self.contributing_c2_row_sha256s),
            "contributions": [
                item.to_record() for item in self.contributions
            ],
            "census_evidence_sha256": self.census_evidence_sha256,
        }

    def to_record(self) -> dict[str, Any]:
        return {**self.semantic_record(), "row_sha256": self.row_sha256}


@dataclasses.dataclass(frozen=True)
class ScoringRefusal:
    signal_arm: SignalArm
    fold_id: str
    partition: FoldPartition
    decision_session: str
    security_id: str
    disposition: ScoreDisposition
    evidence_sha256: str
    refusal_sha256: str

    def __post_init__(self) -> None:
        if type(self.signal_arm) is not SignalArm or type(self.partition) is not FoldPartition or type(self.disposition) is not ScoreDisposition:
            raise ProductionScoringError("scoring refusal enum has wrong type")
        require_identifier(self.fold_id, "fold_id")
        parse_date(self.decision_session, "decision_session")
        require_identifier(self.security_id, "security_id")
        require_sha256(self.evidence_sha256, "evidence_sha256")
        require_sha256(self.refusal_sha256, "refusal_sha256")
        if self.refusal_sha256 != sha256_bytes(canonical_json_bytes(self.semantic_record())):
            raise ProductionScoringError("scoring refusal is not content-derived")

    def semantic_record(self) -> dict[str, str]:
        return {
            "signal_arm": self.signal_arm.value,
            "fold_id": self.fold_id,
            "partition": self.partition.value,
            "decision_session": self.decision_session,
            "security_id": self.security_id,
            "disposition": self.disposition.value,
            "evidence_sha256": self.evidence_sha256,
        }

    def to_record(self) -> dict[str, str]:
        return {**self.semantic_record(), "refusal_sha256": self.refusal_sha256}


@dataclasses.dataclass(frozen=True, init=False)
class PrecontrolScoringBatch:
    batch_id: str
    batch_sha256: str
    authority: ProductionScoringAuthority
    fold: ProductionScoringFold
    rows: tuple[PrecontrolDecisionRow, ...]
    refusals: tuple[ScoringRefusal, ...]
    event_terminals: tuple[EventScoringTerminal, ...]
    eligible_census_count: int
    exhaustive_coverage: bool


_PRECONTROL_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType[PrecontrolScoringBatch], bytes, tuple[object, ...]]
] = {}
_PRECONTROL_AUTHORITIES_LOCK = threading.RLock()


def _refusal(
    arm: SignalArm,
    fold: ProductionScoringFold,
    partition: FoldPartition,
    row: EligibleSecuritySession,
    disposition: ScoreDisposition,
) -> ScoringRefusal:
    seed = {
        "signal_arm": arm.value,
        "fold_id": fold.fold_id,
        "partition": partition.value,
        "decision_session": row.decision_session,
        "security_id": row.security_id,
        "disposition": disposition.value,
        "evidence_sha256": row.evidence_sha256,
    }
    return ScoringRefusal(
        signal_arm=arm,
        fold_id=fold.fold_id,
        partition=partition,
        decision_session=row.decision_session,
        security_id=row.security_id,
        disposition=disposition,
        evidence_sha256=row.evidence_sha256,
        refusal_sha256=sha256_bytes(canonical_json_bytes(seed)),
    )


def _census_refusal(
    arm: SignalArm,
    fold: ProductionScoringFold,
    partition: FoldPartition,
    row: EligibleSecuritySessionRefusal,
) -> ScoringRefusal:
    seed = {
        "signal_arm": arm.value,
        "fold_id": fold.fold_id,
        "partition": partition.value,
        "decision_session": row.decision_session,
        "security_id": row.security_id,
        "disposition": ScoreDisposition.CENSUS_EVIDENCE_REFUSAL.value,
        "evidence_sha256": row.refusal_sha256,
    }
    return ScoringRefusal(
        signal_arm=arm,
        fold_id=fold.fold_id,
        partition=partition,
        decision_session=row.decision_session,
        security_id=row.security_id,
        disposition=ScoreDisposition.CENSUS_EVIDENCE_REFUSAL,
        evidence_sha256=row.refusal_sha256,
        refusal_sha256=sha256_bytes(canonical_json_bytes(seed)),
    )


def _precontrol_record(
    authority: ProductionScoringAuthority,
    fold: ProductionScoringFold,
    rows: tuple[PrecontrolDecisionRow, ...],
    refusals: tuple[ScoringRefusal, ...],
    terminals: tuple[EventScoringTerminal, ...],
    eligible: int,
) -> dict[str, Any]:
    return {
        "schema": CENSUS_SCHEMA,
        "authority_id": authority.authority_id,
        "authority_sha256": authority.authority_sha256,
        "fold": fold.to_record(),
        "rows": [item.to_record() for item in rows],
        "refusals": [item.to_record() for item in refusals],
        "event_terminals": [item.to_record() for item in terminals],
        "eligible_census_count": eligible,
        "exhaustive_coverage": True,
    }


def _forget_precontrol(identity: int, reference: weakref.ReferenceType[PrecontrolScoringBatch]) -> None:
    with _PRECONTROL_AUTHORITIES_LOCK:
        current = _PRECONTROL_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _PRECONTROL_AUTHORITIES.pop(identity, None)


def _precontrol_topology(batch: PrecontrolScoringBatch) -> tuple[object, ...]:
    return (
        id(batch.authority),
        id(batch.fold),
        id(batch.rows),
        tuple(id(item) for item in batch.rows),
        tuple(
            (
                id(item.transformed_controls),
                id(item.contributing_c2_row_sha256s),
                _contribution_lineage_topology(item.contributions),
            )
            for item in batch.rows
        ),
        id(batch.refusals),
        tuple(id(item) for item in batch.refusals),
        id(batch.event_terminals),
        tuple(id(item) for item in batch.event_terminals),
        tuple(id(item.linked_c2_row_sha256s) for item in batch.event_terminals),
    )


def _build_precontrol_session_terminals(
    *,
    batch: ProductionInputBatch,
    fold: ProductionScoringFold,
    partition: FoldPartition,
    session: str,
    census_rows: tuple[EligibleSecuritySession, ...],
    refused_census_rows: tuple[EligibleSecuritySessionRefusal, ...],
    contributions: tuple[_DailyContribution, ...],
    ordinals: dict[str, int],
) -> tuple[tuple[PrecontrolDecisionRow, ...], tuple[ScoringRefusal, ...]]:
    """Score one complete security-sorted session without retaining a fold graph."""

    refusals: list[ScoringRefusal] = [
        _census_refusal(batch.signal_arm, fold, partition, item)
        for item in refused_census_rows
    ]
    if not census_rows:
        return (), tuple(refusals)
    security_ids = tuple(item.security_id for item in census_rows)
    if tuple(sorted(security_ids)) != security_ids:
        raise ProductionScoringError("session census is not security-sorted")
    session_security_ids = set(security_ids)
    visible = tuple(
        item
        for item in contributions
        if item.eligible_session <= session
        and item.security_id in session_security_ids
    )
    by_security: dict[
        str,
        list[tuple[_DailyContribution, int, Decimal, Decimal, Decimal]],
    ] = defaultdict(list)
    for item in visible:
        age = ordinals[session] - ordinals[item.eligible_session]
        if age < 0:
            raise ProductionScoringError("future event entered decision session")
        decay = _decay(age)
        with localcontext(_context()):
            firm_value = _fraction_decimal(item.firm_delta) * decay
            global_value = _fraction_decimal(item.global_delta) * decay
        by_security[item.security_id].append(
            (item, age, decay, firm_value, global_value)
        )
    raw_firm: dict[str, Decimal] = {}
    raw_global: dict[str, Decimal] = {}
    active = set(by_security)
    for security_id in security_ids:
        values = by_security.get(security_id, ())
        raw_firm[security_id] = _stable_sum(item[3] for item in values)
        raw_global[security_id] = _stable_sum(item[4] for item in values)
    sector_members: dict[str, list[str]] = defaultdict(list)
    for item in census_rows:
        sector_members[item.sector_id].append(item.security_id)
    firm_z: dict[str, Decimal] = {}
    global_z: dict[str, Decimal] = {}
    sector_refusals: dict[str, ScoreDisposition] = {}
    for sector_id in sorted(sector_members):
        members = tuple(sorted(sector_members[sector_id]))
        normalized_firm, reason = _normalize_sector(raw_firm, active, members)
        if reason is not None:
            sector_refusals[sector_id] = reason
            continue
        normalized_global, global_reason = _normalize_sector(
            raw_global, active, members
        )
        if global_reason is not None:
            sector_refusals[sector_id] = (
                ScoreDisposition.SECTOR_ZERO_MAD_GLOBAL
                if global_reason is ScoreDisposition.SECTOR_ZERO_MAD_FIRM
                else global_reason
            )
            continue
        assert normalized_firm is not None and normalized_global is not None
        firm_z.update(normalized_firm)
        global_z.update(normalized_global)
    transformed, control_reason = _transform_controls(
        census_rows, len(census_rows) + len(refused_census_rows)
    )
    components = _component_ids(session, security_ids, visible)
    built_rows: list[PrecontrolDecisionRow] = []
    for census in census_rows:
        reason = control_reason or sector_refusals.get(census.sector_id)
        if reason is not None:
            refusals.append(
                _refusal(batch.signal_arm, fold, partition, census, reason)
            )
            continue
        assert transformed is not None
        events = by_security.get(census.security_id, ())
        lineage = tuple(
            sorted(
                {
                    value
                    for item, _, _, _, _ in events
                    for value in item.linked_c2_row_sha256s
                }
            )
        )
        contributions_for_row = tuple(
            sorted(
                (
                    _contribution_lineage(
                        session,
                        item,
                        age,
                        decay,
                        firm_value,
                    )
                    for item, age, decay, firm_value, _global_value in events
                ),
                key=lambda item: item.lineage_sha256,
            )
        )
        state = ScoreState.ACTIVE if events else ScoreState.STRUCTURAL_ZERO
        if state is ScoreState.STRUCTURAL_ZERO:
            firm_reliable = global_reliable = Decimal(0)
        else:
            try:
                firm_breadth = independent_evidence_breadth(
                    IndependentContribution(
                        item.institution_id,
                        item.common_event_id,
                        abs(firm_value),
                    )
                    for item, _, _, firm_value, _ in events
                )
                global_breadth = independent_evidence_breadth(
                    IndependentContribution(
                        item.institution_id,
                        item.common_event_id,
                        abs(global_value),
                    )
                    for item, _, _, _, global_value in events
                )
                firm_reliability = stock_reliability(
                    independent_effective_n=firm_breadth.independent_effective_n,
                    quality=census.q_data,
                )
                global_reliability = stock_reliability(
                    independent_effective_n=global_breadth.independent_effective_n,
                    quality=census.q_data,
                )
            except FormulaError as exc:
                raise ProductionScoringError(
                    "evidence breadth/reliability failed"
                ) from exc
            with analyst_decimal_context():
                firm_reliable = firm_z[census.security_id] * firm_reliability
                global_reliable = global_z[census.security_id] * global_reliability
        seed = {
            "signal_arm": batch.signal_arm.value,
            "fold_id": fold.fold_id,
            "partition": partition.value,
            "decision_session": session,
            "security_id": census.security_id,
            "issuer_id": census.issuer_id,
            "share_class_id": census.share_class_id,
            "listing_id": census.listing_id,
            "historical_ticker": census.historical_ticker,
            "sector_id": census.sector_id,
            "industry_id": census.industry_id,
            "state": state.value,
            "firm_reliable_score": _decimal_text(firm_reliable),
            "global_reliable_score": _decimal_text(global_reliable),
            "transformed_controls": [
                _decimal_text(item)
                for item in transformed[census.security_id]
            ],
            "realized_volatility_60d": _decimal_text(
                dict(census.controls.values)["realized_volatility_60d"]
            ),
            "earnings_anchor_signed_session_distance": (
                census.earnings_anchor_signed_session_distance
            ),
            "common_event_component_id": components[census.security_id],
            "contributing_c2_row_sha256s": list(lineage),
            "contributions": [
                item.to_record() for item in contributions_for_row
            ],
            "census_evidence_sha256": census.evidence_sha256,
        }
        built_rows.append(
            PrecontrolDecisionRow(
                signal_arm=batch.signal_arm,
                fold_id=fold.fold_id,
                partition=partition,
                decision_session=session,
                security_id=census.security_id,
                issuer_id=census.issuer_id,
                share_class_id=census.share_class_id,
                listing_id=census.listing_id,
                historical_ticker=census.historical_ticker,
                sector_id=census.sector_id,
                industry_id=census.industry_id,
                state=state,
                firm_reliable_score=firm_reliable,
                global_reliable_score=global_reliable,
                transformed_controls=transformed[census.security_id],
                realized_volatility_60d=dict(census.controls.values)[
                    "realized_volatility_60d"
                ],
                earnings_anchor_signed_session_distance=(
                    census.earnings_anchor_signed_session_distance
                ),
                common_event_component_id=components[census.security_id],
                contributing_c2_row_sha256s=lineage,
                contributions=contributions_for_row,
                census_evidence_sha256=census.evidence_sha256,
                row_sha256=sha256_bytes(canonical_json_bytes(seed)),
            )
        )
    return tuple(built_rows), tuple(refusals)


def build_precontrol_scoring_batch(
    authority: ProductionScoringAuthority,
    fold: ProductionScoringFold,
) -> PrecontrolScoringBatch:
    """Build paired firm/global reliable scores on every in-fold census row."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    require_production_scoring_authority(authority)
    if type(fold) is not ProductionScoringFold:
        raise ProductionScoringError("fold must have exact type")
    fold.__post_init__()
    selected = tuple(
        item for item in authority.census_rows if fold.partition(item.decision_session) is not None
    )
    selected_refusals = tuple(
        item
        for item in authority.census_refusals
        if fold.partition(item.decision_session) is not None
    )
    if not selected and not selected_refusals:
        raise ProductionScoringError("fold has no eligible census terminals")
    if not selected:
        raise ProductionScoringError("fold has no accepted census rows for scoring")
    by_session: dict[str, tuple[EligibleSecuritySession, ...]] = {}
    by_session_refusals: dict[str, tuple[EligibleSecuritySessionRefusal, ...]] = {}
    sessions = sorted(
        {
            item.decision_session
            for item in (*selected, *selected_refusals)
        }
    )
    for session in sessions:
        by_session[session] = tuple(item for item in selected if item.decision_session == session)
        by_session_refusals[session] = tuple(
            item for item in selected_refusals if item.decision_session == session
        )
    built_rows: list[PrecontrolDecisionRow] = []
    refusals: list[ScoringRefusal] = []
    all_terminals: list[EventScoringTerminal] = []
    for batch in (authority.current_batch, authority.censored_batch):
        contributions, terminals = _daily_contributions(authority, batch)
        all_terminals.extend(terminals)
        ordinals = _session_ordinals(selected, contributions)
        for session, census_rows in by_session.items():
            partition = fold.partition(session)
            assert partition is not None
            refused_census_rows = by_session_refusals[session]
            session_rows, session_refusals = _build_precontrol_session_terminals(
                batch=batch,
                fold=fold,
                partition=partition,
                session=session,
                census_rows=census_rows,
                refused_census_rows=refused_census_rows,
                contributions=contributions,
                ordinals=ordinals,
            )
            built_rows.extend(session_rows)
            refusals.extend(session_refusals)
    rows_tuple = tuple(sorted(built_rows, key=lambda item: (item.signal_arm.value, item.decision_session, item.security_id)))
    refusals_tuple = tuple(sorted(refusals, key=lambda item: (item.signal_arm.value, item.decision_session, item.security_id)))
    terminals_tuple = tuple(sorted(all_terminals, key=lambda item: (item.signal_arm.value, item.c2_row_sha256)))
    eligible = (len(selected) + len(selected_refusals)) * 2
    terminal_keys = {
        (item.signal_arm, item.decision_session, item.security_id) for item in rows_tuple
    } | {
        (item.signal_arm, item.decision_session, item.security_id) for item in refusals_tuple
    }
    expected_keys = {
        (arm, item.decision_session, item.security_id)
        for arm in SignalArm
        for item in (*selected, *selected_refusals)
    }
    if terminal_keys != expected_keys or len(rows_tuple) + len(refusals_tuple) != eligible:
        raise ProductionScoringError("precontrol census is not exhaustive and exclusive")
    record = _precontrol_record(
        authority, fold, rows_tuple, refusals_tuple, terminals_tuple, eligible
    )
    digest = sha256_bytes(canonical_json_bytes(record))
    value = object.__new__(PrecontrolScoringBatch)
    for name, item in {
        "batch_id": f"arv2-precontrol-scoring-{digest[:24]}",
        "batch_sha256": digest,
        "authority": authority,
        "fold": fold,
        "rows": rows_tuple,
        "refusals": refusals_tuple,
        "event_terminals": terminals_tuple,
        "eligible_census_count": eligible,
        "exhaustive_coverage": True,
    }.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget_precontrol(key, ref))
    with _PRECONTROL_AUTHORITIES_LOCK:
        _PRECONTROL_AUTHORITIES[identity] = (
            reference,
            canonical_json_bytes(record),
            _precontrol_topology(value),
        )
    return require_precontrol_scoring_batch(value)


def require_precontrol_scoring_batch(batch: PrecontrolScoringBatch) -> PrecontrolScoringBatch:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    if type(batch) is not PrecontrolScoringBatch:
        raise ProductionScoringError("precontrol batch requires exact built type")
    with _PRECONTROL_AUTHORITIES_LOCK:
        registered = _PRECONTROL_AUTHORITIES.get(id(batch))
    if registered is None or registered[0]() is not batch:
        raise ProductionScoringError("precontrol batch is not builder-authenticated")
    require_production_scoring_authority(batch.authority)
    if type(batch.fold) is not ProductionScoringFold:
        raise ProductionScoringError("precontrol fold changed type")
    batch.fold.__post_init__()
    if type(batch.rows) is not tuple or any(type(item) is not PrecontrolDecisionRow for item in batch.rows):
        raise ProductionScoringError("precontrol rows changed type")
    if type(batch.refusals) is not tuple or any(type(item) is not ScoringRefusal for item in batch.refusals):
        raise ProductionScoringError("precontrol refusals changed type")
    if type(batch.event_terminals) is not tuple or any(type(item) is not EventScoringTerminal for item in batch.event_terminals):
        raise ProductionScoringError("event terminals changed type")
    for item in batch.rows:
        item.__post_init__()
    for item in batch.refusals:
        item.__post_init__()
    for item in batch.event_terminals:
        item.__post_init__()
    if type(batch.eligible_census_count) is not int or type(batch.exhaustive_coverage) is not bool or not batch.exhaustive_coverage:
        raise ProductionScoringError("precontrol coverage scalar changed")
    record = _precontrol_record(
        batch.authority,
        batch.fold,
        batch.rows,
        batch.refusals,
        batch.event_terminals,
        batch.eligible_census_count,
    )
    encoded = canonical_json_bytes(record)
    digest = sha256_bytes(encoded)
    if (
        encoded != registered[1]
        or _precontrol_topology(batch) != registered[2]
        or batch.batch_sha256 != digest
        or batch.batch_id != f"arv2-precontrol-scoring-{digest[:24]}"
    ):
        raise ProductionScoringError("precontrol batch changed after authentication")
    return batch


def _solve_ols(
    design: tuple[tuple[Decimal, ...], ...],
    response: tuple[Decimal, ...],
) -> tuple[Decimal, ...]:
    if not design or len(design) != len(response):
        raise ProductionScoringError("OLS design and response are empty or mismatched")
    width = len(design[0])
    if width == 0 or any(len(row) != width for row in design):
        raise ProductionScoringError("OLS design is ragged or empty")
    if any(type(value) is not Decimal or not value.is_finite() for row in design for value in row) or any(
        type(value) is not Decimal or not value.is_finite() for value in response
    ):
        raise ProductionScoringError("OLS accepts exact finite Decimal values only")
    with localcontext(_context()) as context:
        row_count = len(design)
        q_columns: list[list[Decimal]] = []
        upper = [[Decimal(0) for _ in range(width)] for _ in range(width)]
        for column_index in range(width):
            original = [row[column_index] for row in design]
            vector = list(original)
            for prior_index, q_column in enumerate(q_columns):
                projection = sum(
                    (
                        q_column[row_index] * vector[row_index]
                        for row_index in range(row_count)
                    ),
                    Decimal(0),
                )
                upper[prior_index][column_index] = projection
                vector = [
                    vector[row_index] - projection * q_column[row_index]
                    for row_index in range(row_count)
                ]
            residual_norm_squared = sum((value * value for value in vector), Decimal(0))
            original_norm_squared = sum((value * value for value in original), Decimal(0))
            relative_floor = (
                RANK_RELATIVE_THRESHOLD
                * RANK_RELATIVE_THRESHOLD
                * max(Decimal(1), original_norm_squared)
            )
            if residual_norm_squared <= relative_floor:
                raise ProductionScoringError("training control design is rank deficient")
            norm = context.sqrt(residual_norm_squared)
            upper[column_index][column_index] = norm
            q_columns.append([value / norm for value in vector])
        q_response = [
            sum(
                (
                    q_columns[column][row_index] * response[row_index]
                    for row_index in range(row_count)
                ),
                Decimal(0),
            )
            for column in range(width)
        ]
        coefficients = [Decimal(0) for _ in range(width)]
        for row_index in range(width - 1, -1, -1):
            remainder = sum(
                (
                    upper[row_index][column] * coefficients[column]
                    for column in range(row_index + 1, width)
                ),
                Decimal(0),
            )
            coefficients[row_index] = (
                q_response[row_index] - remainder
            ) / upper[row_index][row_index]
        return tuple(coefficients)


@dataclasses.dataclass(frozen=True, init=False)
class ProductionControlModel:
    model_id: str
    model_sha256: str
    precontrol_batch_id: str
    precontrol_batch_sha256: str
    signal_arm: SignalArm
    fold_id: str
    train_start: str
    train_end_exclusive: str
    columns: tuple[str, ...]
    industry_levels: tuple[str, ...]
    reference_industry: str
    firm_coefficients: tuple[Decimal, ...]
    global_coefficients: tuple[Decimal, ...]
    active_training_rows: int
    provider_access: bool
    outcome_access: bool
    qc_access: bool


_MODEL_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[ProductionControlModel],
        weakref.ReferenceType[PrecontrolScoringBatch],
        bytes,
        tuple[object, ...],
    ],
] = {}
_MODEL_AUTHORITIES_LOCK = threading.RLock()


def _model_record(
    batch: PrecontrolScoringBatch,
    arm: SignalArm,
    columns: tuple[str, ...],
    levels: tuple[str, ...],
    reference: str,
    firm_coefficients: tuple[Decimal, ...],
    global_coefficients: tuple[Decimal, ...],
    count: int,
) -> dict[str, Any]:
    return {
        "schema": MODEL_SCHEMA,
        "precontrol_batch_id": batch.batch_id,
        "precontrol_batch_sha256": batch.batch_sha256,
        "signal_arm": arm.value,
        "fold_id": batch.fold.fold_id,
        "train_start": batch.fold.train_start,
        "train_end_exclusive": batch.fold.train_end_exclusive,
        "columns": list(columns),
        "industry_levels": list(levels),
        "reference_industry": reference,
        "firm_coefficients": [_decimal_text(item) for item in firm_coefficients],
        "global_coefficients": [_decimal_text(item) for item in global_coefficients],
        "active_training_rows": count,
        "fit_population": "active_training_rows_only",
        "structural_zeros_in_fit": False,
        "capabilities": {
            "provider_access": False,
            "outcome_access": False,
            "qc_access": False,
        },
    }


def _forget_model(identity: int, reference: weakref.ReferenceType[ProductionControlModel]) -> None:
    with _MODEL_AUTHORITIES_LOCK:
        current = _MODEL_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _MODEL_AUTHORITIES.pop(identity, None)


def _model_topology(model: ProductionControlModel) -> tuple[object, ...]:
    return (
        id(model.columns),
        id(model.industry_levels),
        id(model.firm_coefficients),
        id(model.global_coefficients),
    )


def fit_production_control_models(
    batch: PrecontrolScoringBatch,
) -> tuple[ProductionControlModel, ProductionControlModel]:
    """Fit firm and global OLS responses separately on each arm's same design."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    require_precontrol_scoring_batch(batch)
    result: list[ProductionControlModel] = []
    for arm in SignalArm:
        active = tuple(
            item
            for item in batch.rows
            if item.signal_arm is arm
            and item.partition is FoldPartition.TRAIN
            and item.state is ScoreState.ACTIVE
        )
        levels = tuple(sorted({item.industry_id for item in active}))
        if not levels:
            raise ProductionScoringError(f"{arm.value} training fit has no active industry")
        reference = levels[0]
        columns = (
            "intercept",
            *CONTROL_COLUMNS,
            *(f"industry::{item}" for item in levels[1:]),
        )
        if len(active) <= len(columns) + 20:
            raise ProductionScoringError(
                f"{arm.value} training fit has too few rows for frozen parameter floor"
            )
        design = tuple(
            (
                Decimal(1),
                *item.transformed_controls,
                *(
                    Decimal(1) if item.industry_id == level else Decimal(0)
                    for level in levels[1:]
                ),
            )
            for item in active
        )
        firm_coefficients = _solve_ols(
            design, tuple(item.firm_reliable_score for item in active)
        )
        global_coefficients = _solve_ols(
            design, tuple(item.global_reliable_score for item in active)
        )
        record = _model_record(
            batch,
            arm,
            columns,
            levels,
            reference,
            firm_coefficients,
            global_coefficients,
            len(active),
        )
        digest = sha256_bytes(canonical_json_bytes(record))
        model = object.__new__(ProductionControlModel)
        for name, value in {
            "model_id": f"arv2-production-control-{arm.value}-{digest[:20]}",
            "model_sha256": digest,
            "precontrol_batch_id": batch.batch_id,
            "precontrol_batch_sha256": batch.batch_sha256,
            "signal_arm": arm,
            "fold_id": batch.fold.fold_id,
            "train_start": batch.fold.train_start,
            "train_end_exclusive": batch.fold.train_end_exclusive,
            "columns": columns,
            "industry_levels": levels,
            "reference_industry": reference,
            "firm_coefficients": firm_coefficients,
            "global_coefficients": global_coefficients,
            "active_training_rows": len(active),
            "provider_access": False,
            "outcome_access": False,
            "qc_access": False,
        }.items():
            object.__setattr__(model, name, value)
        identity = id(model)
        reference_weak = weakref.ref(model, lambda ref, key=identity: _forget_model(key, ref))
        with _MODEL_AUTHORITIES_LOCK:
            _MODEL_AUTHORITIES[identity] = (
                reference_weak,
                weakref.ref(batch),
                canonical_json_bytes(record),
                _model_topology(model),
            )
        result.append(require_production_control_model(model, batch))
    return tuple(result)  # type: ignore[return-value]


def require_production_control_model(
    model: ProductionControlModel,
    batch: PrecontrolScoringBatch,
) -> ProductionControlModel:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    if type(model) is not ProductionControlModel:
        raise ProductionScoringError("control model requires exact built type")
    require_precontrol_scoring_batch(batch)
    with _MODEL_AUTHORITIES_LOCK:
        registered = _MODEL_AUTHORITIES.get(id(model))
    if registered is None or registered[0]() is not model or registered[1]() is not batch:
        raise ProductionScoringError("control model is not authenticated for this precontrol batch")
    if type(model.signal_arm) is not SignalArm or any(
        type(getattr(model, name)) is not bool or getattr(model, name)
        for name in ("provider_access", "outcome_access", "qc_access")
    ):
        raise ProductionScoringError("control model enum/capability surface changed")
    if type(model.columns) is not tuple or type(model.industry_levels) is not tuple or (
        not model.industry_levels
        or model.industry_levels != tuple(sorted(set(model.industry_levels)))
        or model.reference_industry != model.industry_levels[0]
    ):
        raise ProductionScoringError("control model industry topology changed")
    expected_columns = (
        "intercept",
        *CONTROL_COLUMNS,
        *(f"industry::{item}" for item in model.industry_levels[1:]),
    )
    if model.columns != expected_columns:
        raise ProductionScoringError("control model columns changed")
    for coefficients in (model.firm_coefficients, model.global_coefficients):
        if type(coefficients) is not tuple or len(coefficients) != len(model.columns) or any(
            type(item) is not Decimal or not item.is_finite() for item in coefficients
        ):
            raise ProductionScoringError("control model coefficients changed shape/type")
    record = _model_record(
        batch,
        model.signal_arm,
        model.columns,
        model.industry_levels,
        model.reference_industry,
        model.firm_coefficients,
        model.global_coefficients,
        model.active_training_rows,
    )
    encoded = canonical_json_bytes(record)
    digest = sha256_bytes(encoded)
    if (
        encoded != registered[2]
        or _model_topology(model) != registered[3]
        or model.model_sha256 != digest
        or model.model_id != f"arv2-production-control-{model.signal_arm.value}-{digest[:20]}"
        or model.precontrol_batch_id != batch.batch_id
        or model.precontrol_batch_sha256 != batch.batch_sha256
        or model.fold_id != batch.fold.fold_id
        or model.train_start != batch.fold.train_start
        or model.train_end_exclusive != batch.fold.train_end_exclusive
        or type(model.active_training_rows) is not int
        or model.active_training_rows <= len(model.columns) + 20
    ):
        raise ProductionScoringError("control model changed after authentication")
    return model


@dataclasses.dataclass(frozen=True)
class FinalDecisionInput:
    signal_arm: SignalArm
    fold_id: str
    partition: FoldPartition
    decision_session: str
    security_id: str
    issuer_id: str
    share_class_id: str
    listing_id: str
    historical_ticker: str
    sector_id: str
    industry_id: str
    state: ScoreState
    firm_specific_score: Decimal
    global_score: Decimal
    transformed_controls: tuple[Decimal, ...]
    realized_volatility_60d: Decimal
    earnings_anchor_signed_session_distance: int | None
    common_event_component_id: str
    contributing_c2_row_sha256s: tuple[str, ...]
    contributions: tuple[ContributionLineage, ...]
    precontrol_row_sha256: str
    firm_model_sha256: str
    global_model_sha256: str
    row_sha256: str

    def __post_init__(self) -> None:
        if type(self.signal_arm) is not SignalArm or type(self.partition) is not FoldPartition or type(self.state) is not ScoreState:
            raise ProductionScoringError("final decision enum has wrong type")
        for name in ("fold_id", "security_id", "issuer_id", "share_class_id", "listing_id", "sector_id", "industry_id", "common_event_component_id"):
            require_identifier(getattr(self, name), name)
        parse_date(self.decision_session, "decision_session")
        require_ticker(self.historical_ticker, "historical_ticker")
        for name in ("firm_specific_score", "global_score"):
            value = getattr(self, name)
            if type(value) is not Decimal or not value.is_finite() or not CLIP_LOW <= value <= CLIP_HIGH:
                raise ProductionScoringError(f"{name} must be exact finite and clipped")
        if (
            type(self.realized_volatility_60d) is not Decimal
            or not self.realized_volatility_60d.is_finite()
        ):
            raise ProductionScoringError(
                "raw realized_volatility_60d must be exact finite Decimal"
            )
        if (
            self.earnings_anchor_signed_session_distance is not None
            and type(self.earnings_anchor_signed_session_distance) is not int
        ):
            raise ProductionScoringError(
                "earnings anchor distance must be an exact integer or null"
            )
        if type(self.transformed_controls) is not tuple or len(self.transformed_controls) != len(CONTROL_COLUMNS) or any(
            type(value) is not Decimal or not value.is_finite() for value in self.transformed_controls
        ):
            raise ProductionScoringError("final transformed controls changed")
        if self.contributing_c2_row_sha256s != tuple(sorted(set(self.contributing_c2_row_sha256s))):
            raise ProductionScoringError("final event lineage is not unique/sorted")
        if type(self.contributions) is not tuple or any(
            type(item) is not ContributionLineage for item in self.contributions
        ):
            raise ProductionScoringError("final contribution lineage changed type")
        for item in self.contributions:
            item.__post_init__()
            if (
                item.decision_session != self.decision_session
                or item.security_id != self.security_id
            ):
                raise ProductionScoringError("final contribution crossed a decision row")
        if self.contributions != tuple(
            sorted(self.contributions, key=lambda item: item.lineage_sha256)
        ) or tuple(
            sorted(
                {
                    digest
                    for item in self.contributions
                    for digest in item.linked_c2_row_sha256s
                }
            )
        ) != self.contributing_c2_row_sha256s:
            raise ProductionScoringError("final contribution lineage is incomplete or unordered")
        for value in (
            *self.contributing_c2_row_sha256s,
            self.precontrol_row_sha256,
            self.firm_model_sha256,
            self.global_model_sha256,
            self.row_sha256,
        ):
            require_sha256(value, "final decision hash")
        if self.state is ScoreState.STRUCTURAL_ZERO and (
            self.firm_specific_score != 0
            or self.global_score != 0
            or self.contributing_c2_row_sha256s
            or self.contributions
        ):
            raise ProductionScoringError("structural zero changed during residualization")
        if self.state is ScoreState.ACTIVE and not self.contributing_c2_row_sha256s:
            raise ProductionScoringError("active final decision lost event lineage")
        if self.row_sha256 != sha256_bytes(canonical_json_bytes(self.semantic_record())):
            raise ProductionScoringError("final decision hash is not content-derived")

    def semantic_record(self) -> dict[str, Any]:
        return {
            "signal_arm": self.signal_arm.value,
            "fold_id": self.fold_id,
            "partition": self.partition.value,
            "decision_session": self.decision_session,
            "security_id": self.security_id,
            "issuer_id": self.issuer_id,
            "share_class_id": self.share_class_id,
            "listing_id": self.listing_id,
            "historical_ticker": self.historical_ticker,
            "sector_id": self.sector_id,
            "industry_id": self.industry_id,
            "state": self.state.value,
            "firm_specific_score": _decimal_text(self.firm_specific_score),
            "global_score": _decimal_text(self.global_score),
            "transformed_controls": [_decimal_text(item) for item in self.transformed_controls],
            "realized_volatility_60d": _decimal_text(
                self.realized_volatility_60d
            ),
            "earnings_anchor_signed_session_distance": (
                self.earnings_anchor_signed_session_distance
            ),
            "common_event_component_id": self.common_event_component_id,
            "contributing_c2_row_sha256s": list(self.contributing_c2_row_sha256s),
            "contributions": [
                item.to_record() for item in self.contributions
            ],
            "precontrol_row_sha256": self.precontrol_row_sha256,
            "firm_model_sha256": self.firm_model_sha256,
            "global_model_sha256": self.global_model_sha256,
        }

    def to_record(self) -> dict[str, Any]:
        return {**self.semantic_record(), "row_sha256": self.row_sha256}


@dataclasses.dataclass(frozen=True, init=False)
class ProductionScoringResult:
    schema: str
    result_id: str
    result_sha256: str
    precontrol_batch: PrecontrolScoringBatch
    models: tuple[ProductionControlModel, ProductionControlModel]
    rows: tuple[FinalDecisionInput, ...]
    refusals: tuple[ScoringRefusal, ...]
    eligible_census_count: int
    exhaustive_coverage: bool
    provider_access: bool
    outcome_access: bool
    qc_access: bool
    deployment: bool
    orders: bool
    trading: bool


_RESULT_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[ProductionScoringResult],
        weakref.ReferenceType[PrecontrolScoringBatch],
        bytes,
        tuple[object, ...],
    ],
] = {}
_RESULT_AUTHORITIES_LOCK = threading.RLock()


def _prediction(model: ProductionControlModel, row: PrecontrolDecisionRow, response: str) -> Decimal:
    coefficients = model.firm_coefficients if response == "firm" else model.global_coefficients
    coefficient_by_column = dict(zip(model.columns, coefficients, strict=True))
    with localcontext(_context()):
        value = coefficient_by_column["intercept"]
        for name, control in zip(CONTROL_COLUMNS, row.transformed_controls, strict=True):
            value += coefficient_by_column[name] * control
        if row.industry_id != model.reference_industry:
            value += coefficient_by_column[f"industry::{row.industry_id}"]
        return value


def _result_record(
    batch: PrecontrolScoringBatch,
    models: tuple[ProductionControlModel, ProductionControlModel],
    rows: tuple[FinalDecisionInput, ...],
    refusals: tuple[ScoringRefusal, ...],
) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "precontrol_batch_id": batch.batch_id,
        "precontrol_batch_sha256": batch.batch_sha256,
        "models": [
            {"signal_arm": item.signal_arm.value, "model_id": item.model_id, "model_sha256": item.model_sha256}
            for item in models
        ],
        "rows": [item.to_record() for item in rows],
        "refusals": [item.to_record() for item in refusals],
        "eligible_census_count": batch.eligible_census_count,
        "exhaustive_coverage": True,
        "capabilities": {
            "provider_access": False,
            "outcome_access": False,
            "qc_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _forget_result(identity: int, reference: weakref.ReferenceType[ProductionScoringResult]) -> None:
    with _RESULT_AUTHORITIES_LOCK:
        current = _RESULT_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _RESULT_AUTHORITIES.pop(identity, None)


def _result_topology(result: ProductionScoringResult) -> tuple[object, ...]:
    return (
        id(result.precontrol_batch),
        id(result.models),
        tuple(id(item) for item in result.models),
        id(result.rows),
        tuple(id(item) for item in result.rows),
        tuple(
            (
                id(item.transformed_controls),
                id(item.contributing_c2_row_sha256s),
                _contribution_lineage_topology(item.contributions),
            )
            for item in result.rows
        ),
        id(result.refusals),
        tuple(id(item) for item in result.refusals),
    )


def apply_production_control_models(
    batch: PrecontrolScoringBatch,
    models: tuple[ProductionControlModel, ProductionControlModel],
) -> ProductionScoringResult:
    """Freeze training coefficients and emit exhaustive adjusted decision inputs."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    require_precontrol_scoring_batch(batch)
    if type(models) is not tuple or len(models) != 2 or tuple(item.signal_arm for item in models) != tuple(SignalArm):
        raise ProductionScoringError("models must be the exact ordered current/censored pair")
    for item in models:
        require_production_control_model(item, batch)
    by_arm = {item.signal_arm: item for item in models}
    rows: list[FinalDecisionInput] = []
    refusals = list(batch.refusals)
    for item in batch.rows:
        model = by_arm[item.signal_arm]
        if item.state is ScoreState.STRUCTURAL_ZERO:
            firm_score = global_score = Decimal(0)
        elif item.industry_id not in model.industry_levels:
            census = next(
                row
                for row in batch.authority.census_rows
                if row.decision_session == item.decision_session and row.security_id == item.security_id
            )
            refusals.append(
                _refusal(
                    item.signal_arm,
                    batch.fold,
                    item.partition,
                    census,
                    ScoreDisposition.UNSEEN_TRAINING_INDUSTRY,
                )
            )
            continue
        else:
            with localcontext(_context()):
                firm_score = item.firm_reliable_score - _prediction(model, item, "firm")
                global_score = item.global_reliable_score - _prediction(model, item, "global")
                firm_score = max(CLIP_LOW, min(CLIP_HIGH, firm_score))
                global_score = max(CLIP_LOW, min(CLIP_HIGH, global_score))
        seed = {
            "signal_arm": item.signal_arm.value,
            "fold_id": item.fold_id,
            "partition": item.partition.value,
            "decision_session": item.decision_session,
            "security_id": item.security_id,
            "issuer_id": item.issuer_id,
            "share_class_id": item.share_class_id,
            "listing_id": item.listing_id,
            "historical_ticker": item.historical_ticker,
            "sector_id": item.sector_id,
            "industry_id": item.industry_id,
            "state": item.state.value,
            "firm_specific_score": _decimal_text(firm_score),
            "global_score": _decimal_text(global_score),
            "transformed_controls": [_decimal_text(value) for value in item.transformed_controls],
            "realized_volatility_60d": _decimal_text(
                item.realized_volatility_60d
            ),
            "earnings_anchor_signed_session_distance": (
                item.earnings_anchor_signed_session_distance
            ),
            "common_event_component_id": item.common_event_component_id,
            "contributing_c2_row_sha256s": list(item.contributing_c2_row_sha256s),
            "contributions": [
                contribution.to_record() for contribution in item.contributions
            ],
            "precontrol_row_sha256": item.row_sha256,
            "firm_model_sha256": model.model_sha256,
            "global_model_sha256": model.model_sha256,
        }
        rows.append(
            FinalDecisionInput(
                signal_arm=item.signal_arm,
                fold_id=item.fold_id,
                partition=item.partition,
                decision_session=item.decision_session,
                security_id=item.security_id,
                issuer_id=item.issuer_id,
                share_class_id=item.share_class_id,
                listing_id=item.listing_id,
                historical_ticker=item.historical_ticker,
                sector_id=item.sector_id,
                industry_id=item.industry_id,
                state=item.state,
                firm_specific_score=firm_score,
                global_score=global_score,
                transformed_controls=item.transformed_controls,
                realized_volatility_60d=item.realized_volatility_60d,
                earnings_anchor_signed_session_distance=(
                    item.earnings_anchor_signed_session_distance
                ),
                common_event_component_id=item.common_event_component_id,
                contributing_c2_row_sha256s=item.contributing_c2_row_sha256s,
                contributions=item.contributions,
                precontrol_row_sha256=item.row_sha256,
                firm_model_sha256=model.model_sha256,
                global_model_sha256=model.model_sha256,
                row_sha256=sha256_bytes(canonical_json_bytes(seed)),
            )
        )
    rows_tuple = tuple(sorted(rows, key=lambda item: (item.signal_arm.value, item.decision_session, item.security_id)))
    refusals_tuple = tuple(sorted(refusals, key=lambda item: (item.signal_arm.value, item.decision_session, item.security_id)))
    if len(rows_tuple) + len(refusals_tuple) != batch.eligible_census_count:
        raise ProductionScoringError("final scoring census is not exhaustive")
    keys = [
        (item.signal_arm, item.decision_session, item.security_id)
        for item in (*rows_tuple, *refusals_tuple)
    ]
    if len(keys) != len(set(keys)):
        raise ProductionScoringError("final scoring terminals overlap")
    record = _result_record(batch, models, rows_tuple, refusals_tuple)
    digest = sha256_bytes(canonical_json_bytes(record))
    value = object.__new__(ProductionScoringResult)
    for name, item in {
        "schema": RESULT_SCHEMA,
        "result_id": f"arv2-production-scoring-result-{digest[:20]}",
        "result_sha256": digest,
        "precontrol_batch": batch,
        "models": models,
        "rows": rows_tuple,
        "refusals": refusals_tuple,
        "eligible_census_count": batch.eligible_census_count,
        "exhaustive_coverage": True,
        "provider_access": False,
        "outcome_access": False,
        "qc_access": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget_result(key, ref))
    with _RESULT_AUTHORITIES_LOCK:
        _RESULT_AUTHORITIES[identity] = (
            reference,
            weakref.ref(batch),
            canonical_json_bytes(record),
            _result_topology(value),
        )
    return require_production_scoring_result(value)


def require_production_scoring_result(result: ProductionScoringResult) -> ProductionScoringResult:
    _PINNED_REQUIRE_STATIC_CONTRACT()
    if type(result) is not ProductionScoringResult:
        raise ProductionScoringError("scoring result requires exact built type")
    batch = result.precontrol_batch
    require_precontrol_scoring_batch(batch)
    with _RESULT_AUTHORITIES_LOCK:
        registered = _RESULT_AUTHORITIES.get(id(result))
    if registered is None or registered[0]() is not result or registered[1]() is not batch:
        raise ProductionScoringError("scoring result is not builder-authenticated")
    if type(result.models) is not tuple or len(result.models) != 2:
        raise ProductionScoringError("scoring result models changed shape")
    for item in result.models:
        require_production_control_model(item, batch)
    if type(result.rows) is not tuple or any(type(item) is not FinalDecisionInput for item in result.rows):
        raise ProductionScoringError("final decision rows changed type")
    if type(result.refusals) is not tuple or any(type(item) is not ScoringRefusal for item in result.refusals):
        raise ProductionScoringError("final refusals changed type")
    for item in result.rows:
        item.__post_init__()
    for item in result.refusals:
        item.__post_init__()
    if result.schema != RESULT_SCHEMA or any(
        type(getattr(result, name)) is not bool or getattr(result, name)
        for name in ("provider_access", "outcome_access", "qc_access", "deployment", "orders", "trading")
    ) or type(result.exhaustive_coverage) is not bool or not result.exhaustive_coverage:
        raise ProductionScoringError("scoring result surface changed or gained capability")
    record = _result_record(batch, result.models, result.rows, result.refusals)
    encoded = canonical_json_bytes(record)
    digest = sha256_bytes(encoded)
    if (
        encoded != registered[2]
        or _result_topology(result) != registered[3]
        or result.result_sha256 != digest
        or result.result_id != f"arv2-production-scoring-result-{digest[:20]}"
        or type(result.eligible_census_count) is not int
        or result.eligible_census_count != batch.eligible_census_count
        or len(result.rows) + len(result.refusals) != result.eligible_census_count
    ):
        raise ProductionScoringError("scoring result changed after authentication")
    return result


def formal_test_decision_inputs(
    result: ProductionScoringResult,
) -> tuple[FinalDecisionInput, ...]:
    """Select formal test rows only from one authenticated scoring result.

    This is intentionally a projection of existing builder-authenticated row
    objects, not a score-construction API.  The formal bridge must retain the
    parent ``ProductionScoringResult`` and separately account for its named
    test-partition refusals.
    """

    _PINNED_REQUIRE_STATIC_CONTRACT()
    require_production_scoring_result(result)
    fold = result.precontrol_batch.fold
    expected = _formal_fold_for_id(fold.fold_id)
    if fold != expected:
        raise ProductionScoringError("formal test projection requires exact nominal fold boundaries")
    return tuple(
        item for item in result.rows if item.partition is FoldPartition.TEST
    )


_PINNED_STATIC_SCALARS = (
    SCORING_SCHEMA,
    SCORING_CONTRACT_SCHEMA,
    SCORING_CONTRACT_ID,
    SCORING_CONTRACT_SHA256,
    CENSUS_SCHEMA,
    MODEL_SCHEMA,
    RESULT_SCHEMA,
    HISTORY_START,
    HALF_LIFE_SESSIONS,
    MINIMUM_TOTAL_NAMES,
    MINIMUM_ACTIVE_NAMES,
    SCORE_CLIP,
    MAD_SCALE,
    CONTROL_COVERAGE_NUMERATOR,
    CONTROL_COVERAGE_DENOMINATOR,
    CONTROL_MINIMUM_ROWS,
    RANK_RELATIVE_THRESHOLD,
    DECIMAL_PRECISION,
    CLIP_LOW,
    CLIP_HIGH,
)
_PINNED_ENUMS = (
    ScoreState,
    ScoreDisposition,
    FoldPartition,
    CensusRefusalReason,
    SignalArm,
)
_PINNED_ENUM_INVENTORIES = tuple(tuple(item) for item in _PINNED_ENUMS)
_PINNED_CONTROL_COLUMN_ROOTS = (CONTINUOUS_COLUMNS, BINARY_COLUMNS, CONTROL_COLUMNS)
_PINNED_CONTROL_COLUMN_VALUES = tuple(tuple(item) for item in _PINNED_CONTROL_COLUMN_ROOTS)
_PINNED_FOLD_ID_ROOTS = (
    FORMAL_PRIMARY_FOLD_IDS,
    DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
    FORMAL_HORIZON_FOLD_BOUNDARIES,
    FORMAL_FOLD_BOUNDARIES,
)
_PINNED_FOLD_ID_VALUES = tuple(tuple(item) for item in _PINNED_FOLD_ID_ROOTS)
_PINNED_TYPES = (
    ProductionControlVector,
    EligibleSecuritySession,
    EligibleSecuritySessionRefusal,
    EndpointLabelEvidence,
    ProductionScoringFold,
    ProductionScoringAuthority,
    EventScoringTerminal,
    ContributionLineage,
    PrecontrolDecisionRow,
    ScoringRefusal,
    PrecontrolScoringBatch,
    ProductionControlModel,
    FinalDecisionInput,
    ProductionScoringResult,
)
_PINNED_POST_INITS = tuple(getattr(item, "__post_init__", None) for item in _PINNED_TYPES)
_PINNED_IMPORTED_CALLABLES = (
    analyst_decimal_context,
    canonical_json_bytes,
    format_utc_timestamp,
    parse_date,
    parse_utc_timestamp,
    require_identifier,
    require_loaded_global_benchmark_contract,
    require_production_evidence_authority,
    require_production_input_batch,
    require_sha256,
    require_ticker,
    resolve_global_rating,
    global_rating_delta,
    independent_evidence_breadth,
    sha256_bytes,
    stock_reliability,
)
_PINNED_SCORING_CONTRACT_BYTES = canonical_json_bytes(scoring_contract_record())


def _current_local_callables() -> tuple[object, ...]:
    return (
        scoring_contract_record,
        render_scoring_contract_bytes,
        _decimal,
        _decimal_text,
        _fraction_decimal,
        _require_exact_string,
        _session_open_text,
        _before_open,
        _median,
        _context,
        ProductionControlVector.__post_init__,
        ProductionControlVector.decimal_values,
        ProductionControlVector.to_record,
        ProductionControlVector.vector_sha256,
        EligibleSecuritySession.__post_init__,
        EligibleSecuritySession.semantic_record,
        EligibleSecuritySession.to_record,
        build_eligible_security_session,
        EligibleSecuritySessionRefusal.__post_init__,
        EligibleSecuritySessionRefusal.semantic_record,
        EligibleSecuritySessionRefusal.to_record,
        build_eligible_security_session_refusal,
        EndpointLabelEvidence.__post_init__,
        EndpointLabelEvidence.semantic_record,
        build_endpoint_label_evidence,
        ProductionScoringFold.__post_init__,
        ProductionScoringFold.partition,
        ProductionScoringFold.to_record,
        _formal_fold_for_id,
        formal_horizon_fold_boundary,
        build_formal_production_scoring_fold,
        _authority_record,
        _authority_fingerprint,
        _normalized_union,
        _firm_evidence_by_c2_hash,
        _row_evidence_by_c2_hash,
        build_production_scoring_authority,
        require_production_scoring_authority,
        EventScoringTerminal.__post_init__,
        EventScoringTerminal.semantic_record,
        EventScoringTerminal.to_record,
        ContributionLineage.__post_init__,
        ContributionLineage.semantic_record,
        ContributionLineage.to_record,
        _contribution_lineage,
        _contribution_lineage_topology,
        _terminal,
        _global_delta,
        _daily_contributions,
        _session_ordinals,
        _decay,
        _stable_sum,
        _normalize_sector,
        _transform_controls,
        _component_ids,
        PrecontrolDecisionRow.__post_init__,
        PrecontrolDecisionRow.semantic_record,
        PrecontrolDecisionRow.to_record,
        ScoringRefusal.__post_init__,
        ScoringRefusal.semantic_record,
        ScoringRefusal.to_record,
        _refusal,
        _census_refusal,
        _precontrol_record,
        _precontrol_topology,
        build_precontrol_scoring_batch,
        require_precontrol_scoring_batch,
        _solve_ols,
        _model_record,
        _model_topology,
        fit_production_control_models,
        require_production_control_model,
        FinalDecisionInput.__post_init__,
        FinalDecisionInput.semantic_record,
        FinalDecisionInput.to_record,
        _prediction,
        _result_record,
        _result_topology,
        apply_production_control_models,
        require_production_scoring_result,
        formal_test_decision_inputs,
    )


_PINNED_CURRENT_LOCAL_CALLABLES = _current_local_callables
_PINNED_LOCAL_CALLABLES = _current_local_callables()


def _require_static_contract() -> None:
    scalars = (
        SCORING_SCHEMA,
        SCORING_CONTRACT_SCHEMA,
        SCORING_CONTRACT_ID,
        SCORING_CONTRACT_SHA256,
        CENSUS_SCHEMA,
        MODEL_SCHEMA,
        RESULT_SCHEMA,
        HISTORY_START,
        HALF_LIFE_SESSIONS,
        MINIMUM_TOTAL_NAMES,
        MINIMUM_ACTIVE_NAMES,
        SCORE_CLIP,
        MAD_SCALE,
        CONTROL_COVERAGE_NUMERATOR,
        CONTROL_COVERAGE_DENOMINATOR,
        CONTROL_MINIMUM_ROWS,
        RANK_RELATIVE_THRESHOLD,
        DECIMAL_PRECISION,
        CLIP_LOW,
        CLIP_HIGH,
    )
    enums = (
        ScoreState,
        ScoreDisposition,
        FoldPartition,
        CensusRefusalReason,
        SignalArm,
    )
    control_roots = (CONTINUOUS_COLUMNS, BINARY_COLUMNS, CONTROL_COLUMNS)
    fold_id_roots = (
        FORMAL_PRIMARY_FOLD_IDS,
        DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
        FORMAL_HORIZON_FOLD_BOUNDARIES,
        FORMAL_FOLD_BOUNDARIES,
    )
    types = (
        ProductionControlVector,
        EligibleSecuritySession,
        EligibleSecuritySessionRefusal,
        EndpointLabelEvidence,
        ProductionScoringFold,
        ProductionScoringAuthority,
        EventScoringTerminal,
        ContributionLineage,
        PrecontrolDecisionRow,
        ScoringRefusal,
        PrecontrolScoringBatch,
        ProductionControlModel,
        FinalDecisionInput,
        ProductionScoringResult,
    )
    imported = (
        analyst_decimal_context,
        canonical_json_bytes,
        format_utc_timestamp,
        parse_date,
        parse_utc_timestamp,
        require_identifier,
        require_loaded_global_benchmark_contract,
        require_production_evidence_authority,
        require_production_input_batch,
        require_sha256,
        require_ticker,
        resolve_global_rating,
        global_rating_delta,
        independent_evidence_breadth,
        sha256_bytes,
        stock_reliability,
    )
    if (
        any(
            type(current) is not type(expected) or current != expected
            for current, expected in zip(scalars, _PINNED_STATIC_SCALARS, strict=True)
        )
        or enums != _PINNED_ENUMS
        or any(
            tuple(item) != inventory
            for item, inventory in zip(enums, _PINNED_ENUM_INVENTORIES, strict=True)
        )
        or any(
            root is not expected
            for root, expected in zip(control_roots, _PINNED_CONTROL_COLUMN_ROOTS, strict=True)
        )
        or any(
            tuple(root) != expected
            for root, expected in zip(control_roots, _PINNED_CONTROL_COLUMN_VALUES, strict=True)
        )
        or any(
            root is not expected
            for root, expected in zip(fold_id_roots, _PINNED_FOLD_ID_ROOTS, strict=True)
        )
        or any(
            tuple(root) != expected
            for root, expected in zip(fold_id_roots, _PINNED_FOLD_ID_VALUES, strict=True)
        )
        or types != _PINNED_TYPES
        or any(
            getattr(item, "__post_init__", None) is not expected
            for item, expected in zip(types, _PINNED_POST_INITS, strict=True)
        )
        or any(
            current is not expected
            for current, expected in zip(imported, _PINNED_IMPORTED_CALLABLES, strict=True)
        )
        or _current_local_callables is not _PINNED_CURRENT_LOCAL_CALLABLES
    ):
        raise ProductionScoringError("production scoring static contract changed")
    if any(
        current is not expected
        for current, expected in zip(
            _current_local_callables(), _PINNED_LOCAL_CALLABLES, strict=True
        )
    ):
        raise ProductionScoringError("production scoring callable contract changed")
    rendered = canonical_json_bytes(scoring_contract_record())
    if (
        rendered != _PINNED_SCORING_CONTRACT_BYTES
        or sha256_bytes(rendered) != SCORING_CONTRACT_SHA256
        or SCORING_CONTRACT_ID
        != f"arv2-production-scoring-contract-{SCORING_CONTRACT_SHA256[:16]}"
    ):
        raise ProductionScoringError("production scoring content contract changed")


_PINNED_REQUIRE_STATIC_CONTRACT = _require_static_contract


__all__ = [
    "BINARY_COLUMNS",
    "CENSUS_SCHEMA",
    "CensusRefusalReason",
    "CONTINUOUS_COLUMNS",
    "CONTROL_COLUMNS",
    "ContributionLineage",
    "DESCRIPTIVE_SENSITIVITY_FOLD_IDS",
    "EligibleSecuritySession",
    "EligibleSecuritySessionRefusal",
    "EndpointLabelEvidence",
    "EventScoringTerminal",
    "FinalDecisionInput",
    "FoldPartition",
    "FORMAL_FOLD_BOUNDARIES",
    "FORMAL_HORIZON_FOLD_BOUNDARIES",
    "FORMAL_PRIMARY_FOLD_IDS",
    "HISTORY_START",
    "MODEL_SCHEMA",
    "PrecontrolDecisionRow",
    "PrecontrolScoringBatch",
    "ProductionControlModel",
    "ProductionControlVector",
    "ProductionScoringAuthority",
    "ProductionScoringError",
    "ProductionScoringFold",
    "ProductionScoringResult",
    "RESULT_SCHEMA",
    "SCORING_CONTRACT_ID",
    "SCORING_CONTRACT_SCHEMA",
    "SCORING_CONTRACT_SHA256",
    "SCORING_SCHEMA",
    "ScoreDisposition",
    "ScoreState",
    "ScoringRefusal",
    "apply_production_control_models",
    "build_eligible_security_session",
    "build_eligible_security_session_refusal",
    "build_endpoint_label_evidence",
    "build_formal_production_scoring_fold",
    "build_precontrol_scoring_batch",
    "build_production_scoring_authority",
    "fit_production_control_models",
    "formal_horizon_fold_boundary",
    "formal_test_decision_inputs",
    "require_precontrol_scoring_batch",
    "require_production_control_model",
    "require_production_scoring_authority",
    "require_production_scoring_result",
    "render_scoring_contract_bytes",
    "scoring_contract_record",
]
