"""Owner-frozen SI-3E-P1A exact stock percentile projection.

This module consumes only an authenticated SI-3E-P0 score-order inventory.
It computes the exact mid-distribution percentile ``(2*L+E)/(2*N)`` and an
inclusive structural threshold classification.  It deliberately does not
apply investability rules, select seeds, access outcomes, run QuantConnect,
or grant portfolio, broker, deployment, or trading authority.
"""
from __future__ import annotations

import dataclasses
import json
from enum import Enum
from typing import Any, Iterator, overload

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.preregistration import (
    PREREGISTRATION,
    SHORT_INTEREST_BLUEPRINT_PATH,
    SHORT_INTEREST_BLUEPRINT_SHA256,
    SHORT_INTEREST_RESEARCH_GATE,
    SHORT_INTEREST_RESEARCH_GATE_SHA256,
    require_short_interest_research_gate,
)
from research.short_interest_etf.stock_features import ExactRational
from research.short_interest_etf.stock_normalization import (
    STOCK_NORMALIZATION_POLICY,
    RevisionSelectionState,
)
from research.short_interest_etf.stock_score_order import (
    SCORE_ORDER_BATCH_SCHEMA_VERSION,
    SCORE_ORDER_INVENTORY_ID,
    SCORE_ORDER_SCHEMA_VERSION,
    StockScoreOrderBatch,
    StockScoreOrderDisposition,
    StockScoreOrderError,
    StockScoreOrderRole,
    _revision_state_value,
    _role_value,
)


STOCK_PERCENTILE_POLICY_ID = "si-stock-percentile-policy-v1"
STOCK_PERCENTILE_PROJECTION_ID = "si-stock-percentile-projection-v1"
STOCK_PERCENTILE_SCHEMA_VERSION = "1.0"
STOCK_PERCENTILE_BATCH_SCHEMA_VERSION = "1.0"
STRUCTURAL_STOCK_PERCENTILE_AUTHORITY = (
    "synthetic_structural_stock_percentile_only"
)
STRUCTURAL_STOCK_PERCENTILE_BATCH_AUTHORITY = (
    "synthetic_structural_stock_percentile_batch_only"
)

_OWNER_DIRECTIVE_ID = "si3ep1a-owner-approval-recorded-2026-09-26"
_OWNER_DIRECTIVE_DATE = "2026-09-26"
_OWNER_DIRECTIVE_PATH = (
    "docs/Strategy Description/SHORT_INTEREST_OWNER_DECISIONS_2026-09-26.md"
)
_OWNER_DIRECTIVE_COMMIT = "c329d6f9aa616ea48776d6fbe75c36413b81d19b"
_OWNER_DIRECTIVE_SHA256 = (
    "0172439871e3ace82cd0fe5fcd3526c7b20989185b10e334d169e16c50427bc3"
)
_PERCENTILE_FORMULA = "(2*L+E)/(2*N)"
_BOUNDARY_COMPARISON = "inclusive"
_TIE_POLICY = "exact_equivalence_group_indivisible"
_ARITHMETIC_POLICY = "exact_reduced_rational_no_float_no_rounding"
_POPULATION_SCOPE = "structural_scoreable_population_only"
_CANDIDATE_SEMANTIC = "threshold_candidate_not_seed"
_MINIMUM_PERCENTILE_POPULATION = 1
_MINIMUM_THRESHOLD_CLASSIFICATION_POPULATION = 10
_PRESSURE_CANDIDATE_MINIMUM = ExactRational(9, 10)
_COVERING_CANDIDATE_MAXIMUM_PRESSURE = ExactRational(1, 10)
_COVERING_ROLE_MINIMUM = ExactRational(9, 10)
_PREREGISTRATION_SHA256 = PREREGISTRATION.sha256
_NORMALIZATION_POLICY_SHA256 = STOCK_NORMALIZATION_POLICY.sha256

_FALSE_AUTHORITY_FIELDS = (
    "network_access_authorized",
    "finra_access_authorized",
    "provider_access_authorized",
    "source_data_request_authorized",
    "credential_access_authorized",
    "licensed_row_access_authorized",
    "outcome_access_authorized",
    "shared_holdout_access_authorized",
    "qc_upload_authorized",
    "qc_processing_authorized",
    "qc_job_authorized",
    "qc_backtest_authorized",
    "qc_research_inputs_execution_authority",
    "common_four_family_outcome_evaluation_authorized",
    "integration_authorized",
    "capital_authorized",
    "broker_access_authorized",
    "operator_database_access_authorized",
    "scheduler_access_authorized",
    "paper_trading_authorized",
    "live_trading_authorized",
    "deployment_authorized",
    "trading_authority",
)
_RATIONAL_INSTANCE_FIELDS = frozenset(ExactRational.__dataclass_fields__)
_SOURCE_RATIONAL_FIELDS = frozenset(
    {"source_s1_score", "source_covering_score", "score"}
)


class StockPercentileError(ValueError):
    """The structural stock-percentile projection failed closed."""


def _refuse(detail: str) -> StockPercentileError:
    return StockPercentileError(f"REFUSED: {detail}")


def _checked_sha256(value: Any, name: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _refuse(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def _checked_text(value: Any, name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _refuse(f"{name} must be canonical non-empty text")
    return value


def _checked_count(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise _refuse(f"{name} must be an exact non-negative integer")
    return value


def _checked_reasons(value: Any, name: str) -> tuple[str, ...]:
    if type(value) is not tuple or not all(
        type(item) is str and item and item == item.strip() for item in value
    ):
        raise _refuse(f"{name} must be an exact tuple of canonical strings")
    if value != tuple(sorted(set(value))):
        raise _refuse(f"{name} must be unique and sorted")
    return value


def _checked_rational(value: Any, name: str) -> ExactRational:
    if type(value) is not ExactRational:
        raise _refuse(f"{name} must use the exact ExactRational type")
    state = object.__getattribute__(value, "__dict__")
    keys = tuple(dict.keys(state)) if type(state) is dict else ()
    if (
        type(state) is not dict
        or not all(type(key) is str for key in keys)
        or frozenset(keys) != _RATIONAL_INSTANCE_FIELDS
    ):
        raise _refuse(f"{name} has unexpected instance state")
    try:
        ExactRational.__post_init__(value)
    except (TypeError, ValueError) as exc:
        raise _refuse(f"{name} is not canonical: {exc}") from exc
    return value


def _detach_rational(value: Any, name: str) -> ExactRational | None:
    if value is None:
        return None
    _checked_rational(value, name)
    state = object.__getattribute__(value, "__dict__")
    return ExactRational(
        dict.__getitem__(state, "numerator"),
        dict.__getitem__(state, "denominator"),
    )


def _rational_payload(
    value: ExactRational | None,
) -> dict[str, int] | None:
    if value is None:
        return None
    _checked_rational(value, "rational payload value")
    return ExactRational.to_payload(value)


def _rational_at_least(left: ExactRational, right: ExactRational) -> bool:
    _checked_rational(left, "left comparison value")
    _checked_rational(right, "right comparison value")
    return left.numerator * right.denominator >= (
        right.numerator * left.denominator
    )


def _require_gate_receipt() -> None:
    receipt = require_short_interest_research_gate(
        SHORT_INTEREST_RESEARCH_GATE
    )
    if (
        type(receipt) is not str
        or receipt != SHORT_INTEREST_RESEARCH_GATE_SHA256
    ):
        raise _refuse("SI-0M gate returned an unexpected receipt")


@dataclasses.dataclass(frozen=True, slots=True)
class StockPercentilePolicy:
    """The exact owner-approved SI-3E-P1A percentile semantics."""

    policy_id: str
    owner_directive_id: str
    owner_directive_date: str
    owner_directive_path: str
    owner_directive_commit: str
    owner_directive_sha256: str
    blueprint_path: str
    blueprint_sha256: str
    preregistration_sha256: str
    research_gate_sha256: str
    normalization_policy_sha256: str
    source_score_order_inventory_id: str
    source_score_order_row_schema_version: str
    source_score_order_batch_schema_version: str
    percentile_formula: str
    minimum_percentile_population: int
    minimum_threshold_classification_population: int
    pressure_candidate_minimum_percentile: ExactRational
    covering_candidate_maximum_pressure_percentile: ExactRational
    covering_role_minimum_percentile: ExactRational
    boundary_comparison: str
    tie_policy: str
    arithmetic: str
    population_scope: str
    candidate_semantic: str
    mechanical_percentile_complement_required: bool
    independent_return_evaluation_required: bool
    return_effect_symmetry_assumed: bool
    investability_screen_applied: bool
    seed_selection_authorized: bool
    outcome_access_authorized: bool
    production_authoritative: bool

    def __post_init__(self) -> None:
        self._validate_structure()

    def _validate_structure(self) -> None:
        if type(self) is not StockPercentilePolicy:
            raise _refuse("percentile policy must use the exact frozen type")
        expected_scalars = {
            "policy_id": STOCK_PERCENTILE_POLICY_ID,
            "owner_directive_id": _OWNER_DIRECTIVE_ID,
            "owner_directive_date": _OWNER_DIRECTIVE_DATE,
            "owner_directive_path": _OWNER_DIRECTIVE_PATH,
            "owner_directive_commit": _OWNER_DIRECTIVE_COMMIT,
            "owner_directive_sha256": _OWNER_DIRECTIVE_SHA256,
            "blueprint_path": SHORT_INTEREST_BLUEPRINT_PATH,
            "blueprint_sha256": SHORT_INTEREST_BLUEPRINT_SHA256,
            "preregistration_sha256": _PREREGISTRATION_SHA256,
            "research_gate_sha256": SHORT_INTEREST_RESEARCH_GATE_SHA256,
            "normalization_policy_sha256": _NORMALIZATION_POLICY_SHA256,
            "source_score_order_inventory_id": SCORE_ORDER_INVENTORY_ID,
            "source_score_order_row_schema_version": SCORE_ORDER_SCHEMA_VERSION,
            "source_score_order_batch_schema_version": (
                SCORE_ORDER_BATCH_SCHEMA_VERSION
            ),
            "percentile_formula": _PERCENTILE_FORMULA,
            "minimum_percentile_population": (
                _MINIMUM_PERCENTILE_POPULATION
            ),
            "minimum_threshold_classification_population": (
                _MINIMUM_THRESHOLD_CLASSIFICATION_POPULATION
            ),
            "boundary_comparison": _BOUNDARY_COMPARISON,
            "tie_policy": _TIE_POLICY,
            "arithmetic": _ARITHMETIC_POLICY,
            "population_scope": "structural_scoreable_population_only",
            "candidate_semantic": "threshold_candidate_not_seed",
        }
        for name, expected in expected_scalars.items():
            value = object.__getattribute__(self, name)
            if type(value) is not type(expected) or value != expected:
                label = name.replace("_", " ")
                if name == "minimum_threshold_classification_population":
                    label = "minimum classification population"
                raise _refuse(f"percentile policy has wrong {label}")
        expected_rationals = {
            "pressure_candidate_minimum_percentile": (
                _PRESSURE_CANDIDATE_MINIMUM
            ),
            "covering_candidate_maximum_pressure_percentile": (
                _COVERING_CANDIDATE_MAXIMUM_PRESSURE
            ),
            "covering_role_minimum_percentile": _COVERING_ROLE_MINIMUM,
        }
        for name, expected in expected_rationals.items():
            value = object.__getattribute__(self, name)
            _checked_rational(value, name)
            if value != expected:
                raise _refuse(
                    f"percentile policy has wrong {name.replace('_', ' ')}"
                )
        expected_flags = {
            "mechanical_percentile_complement_required": True,
            "independent_return_evaluation_required": True,
            "return_effect_symmetry_assumed": False,
            "investability_screen_applied": False,
            "seed_selection_authorized": False,
            "outcome_access_authorized": False,
            "production_authoritative": False,
        }
        for name, expected in expected_flags.items():
            value = object.__getattribute__(self, name)
            if type(value) is not bool or value is not expected:
                raise _refuse(
                    f"percentile policy has wrong {name.replace('_', ' ')}"
                )

    def _to_payload_unchecked(self) -> dict[str, Any]:
        return {
            "arithmetic": self.arithmetic,
            "blueprint_path": self.blueprint_path,
            "blueprint_sha256": self.blueprint_sha256,
            "boundary_comparison": self.boundary_comparison,
            "candidate_semantic": self.candidate_semantic,
            "covering_candidate_maximum_pressure_percentile": (
                _rational_payload(
                    self.covering_candidate_maximum_pressure_percentile
                )
            ),
            "covering_role_minimum_percentile": _rational_payload(
                self.covering_role_minimum_percentile
            ),
            "independent_return_evaluation_required": (
                self.independent_return_evaluation_required
            ),
            "investability_screen_applied": self.investability_screen_applied,
            "mechanical_percentile_complement_required": (
                self.mechanical_percentile_complement_required
            ),
            "minimum_percentile_population": (
                self.minimum_percentile_population
            ),
            "minimum_threshold_classification_population": (
                self.minimum_threshold_classification_population
            ),
            "normalization_policy_sha256": self.normalization_policy_sha256,
            "outcome_access_authorized": self.outcome_access_authorized,
            "owner_directive_date": self.owner_directive_date,
            "owner_directive_id": self.owner_directive_id,
            "owner_directive_path": self.owner_directive_path,
            "owner_directive_commit": self.owner_directive_commit,
            "owner_directive_sha256": self.owner_directive_sha256,
            "percentile_formula": self.percentile_formula,
            "policy_id": self.policy_id,
            "population_scope": self.population_scope,
            "preregistration_sha256": self.preregistration_sha256,
            "pressure_candidate_minimum_percentile": _rational_payload(
                self.pressure_candidate_minimum_percentile
            ),
            "production_authoritative": self.production_authoritative,
            "research_gate_sha256": self.research_gate_sha256,
            "return_effect_symmetry_assumed": (
                self.return_effect_symmetry_assumed
            ),
            "seed_selection_authorized": self.seed_selection_authorized,
            "source_score_order_batch_schema_version": (
                self.source_score_order_batch_schema_version
            ),
            "source_score_order_inventory_id": (
                self.source_score_order_inventory_id
            ),
            "source_score_order_row_schema_version": (
                self.source_score_order_row_schema_version
            ),
            "tie_policy": self.tie_policy,
        }

    def to_payload(self) -> dict[str, Any]:
        self._validate_structure()
        return self._to_payload_unchecked()

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


STOCK_PERCENTILE_POLICY = StockPercentilePolicy(
    policy_id=STOCK_PERCENTILE_POLICY_ID,
    owner_directive_id=_OWNER_DIRECTIVE_ID,
    owner_directive_date=_OWNER_DIRECTIVE_DATE,
    owner_directive_path=_OWNER_DIRECTIVE_PATH,
    owner_directive_commit=_OWNER_DIRECTIVE_COMMIT,
    owner_directive_sha256=_OWNER_DIRECTIVE_SHA256,
    blueprint_path=SHORT_INTEREST_BLUEPRINT_PATH,
    blueprint_sha256=SHORT_INTEREST_BLUEPRINT_SHA256,
    preregistration_sha256=_PREREGISTRATION_SHA256,
    research_gate_sha256=SHORT_INTEREST_RESEARCH_GATE_SHA256,
    normalization_policy_sha256=_NORMALIZATION_POLICY_SHA256,
    source_score_order_inventory_id=SCORE_ORDER_INVENTORY_ID,
    source_score_order_row_schema_version=SCORE_ORDER_SCHEMA_VERSION,
    source_score_order_batch_schema_version=SCORE_ORDER_BATCH_SCHEMA_VERSION,
    percentile_formula=_PERCENTILE_FORMULA,
    minimum_percentile_population=_MINIMUM_PERCENTILE_POPULATION,
    minimum_threshold_classification_population=(
        _MINIMUM_THRESHOLD_CLASSIFICATION_POPULATION
    ),
    pressure_candidate_minimum_percentile=_PRESSURE_CANDIDATE_MINIMUM,
    covering_candidate_maximum_pressure_percentile=(
        _COVERING_CANDIDATE_MAXIMUM_PRESSURE
    ),
    covering_role_minimum_percentile=_COVERING_ROLE_MINIMUM,
    boundary_comparison=_BOUNDARY_COMPARISON,
    tie_policy=_TIE_POLICY,
    arithmetic=_ARITHMETIC_POLICY,
    population_scope=_POPULATION_SCOPE,
    candidate_semantic=_CANDIDATE_SEMANTIC,
    mechanical_percentile_complement_required=True,
    independent_return_evaluation_required=True,
    return_effect_symmetry_assumed=False,
    investability_screen_applied=False,
    seed_selection_authorized=False,
    outcome_access_authorized=False,
    production_authoritative=False,
)
STOCK_PERCENTILE_POLICY_SHA256 = hash_payload(
    StockPercentilePolicy._to_payload_unchecked(STOCK_PERCENTILE_POLICY)
)


def require_stock_percentile_policy(policy: StockPercentilePolicy) -> str:
    """Validate the owner-frozen policy and return its semantic receipt."""
    if type(policy) is not StockPercentilePolicy:
        raise _refuse("percentile policy must use the exact frozen type")
    StockPercentilePolicy._validate_structure(policy)
    payload = StockPercentilePolicy._to_payload_unchecked(policy)
    receipt = hash_payload(payload)
    if receipt != STOCK_PERCENTILE_POLICY_SHA256:
        raise _refuse("percentile policy differs from the owner freeze")
    return receipt


class StockPercentileCandidateState(str, Enum):
    """Closed structural threshold-classification outcomes."""

    SOURCE_TERMINAL = "source_terminal"
    INSUFFICIENT_SCOREABLE_POPULATION = (
        "insufficient_scoreable_population"
    )
    NOT_THRESHOLD_CANDIDATE = "not_threshold_candidate"
    THRESHOLD_CANDIDATE = "threshold_candidate"


def _candidate_state_value(state: StockPercentileCandidateState) -> str:
    if state is StockPercentileCandidateState.SOURCE_TERMINAL:
        expected_name, expected_order, expected_value = (
            "SOURCE_TERMINAL",
            0,
            "source_terminal",
        )
    elif state is (
        StockPercentileCandidateState.INSUFFICIENT_SCOREABLE_POPULATION
    ):
        expected_name, expected_order, expected_value = (
            "INSUFFICIENT_SCOREABLE_POPULATION",
            1,
            "insufficient_scoreable_population",
        )
    elif state is StockPercentileCandidateState.NOT_THRESHOLD_CANDIDATE:
        expected_name, expected_order, expected_value = (
            "NOT_THRESHOLD_CANDIDATE",
            2,
            "not_threshold_candidate",
        )
    elif state is StockPercentileCandidateState.THRESHOLD_CANDIDATE:
        expected_name, expected_order, expected_value = (
            "THRESHOLD_CANDIDATE",
            3,
            "threshold_candidate",
        )
    else:
        raise _refuse("candidate state must be a canonical enum member")
    state_values = object.__getattribute__(state, "__dict__")
    expected_fields = frozenset(
        {"__objclass__", "_name_", "_sort_order_", "_value_"}
    )
    keys = tuple(dict.keys(state_values)) if type(state_values) is dict else ()
    if (
        type(state_values) is not dict
        or not all(type(key) is str for key in keys)
        or frozenset(keys) != expected_fields
    ):
        raise _refuse("candidate state has unexpected instance state")
    if (
        type(dict.__getitem__(state_values, "_value_")) is not str
        or dict.__getitem__(state_values, "_value_") != expected_value
        or type(dict.__getitem__(state_values, "_name_")) is not str
        or dict.__getitem__(state_values, "_name_") != expected_name
        or type(dict.__getitem__(state_values, "_sort_order_")) is not int
        or dict.__getitem__(state_values, "_sort_order_") != expected_order
        or dict.__getitem__(state_values, "__objclass__")
        is not StockPercentileCandidateState
    ):
        raise _refuse("candidate state singleton is not canonical")
    return expected_value


def _evaluate_order_counts(
    *,
    role: StockScoreOrderRole,
    strictly_lower_count: int,
    equal_count: int,
    strictly_higher_count: int,
    scoreable_count: int,
) -> tuple[
    ExactRational,
    ExactRational,
    StockPercentileCandidateState,
    bool | None,
]:
    """Apply the exact owner-frozen formula to one authenticated count row."""
    try:
        _role_value(role)
    except (StockScoreOrderError, AttributeError, TypeError, ValueError) as exc:
        raise _refuse(f"score-order role is invalid: {exc}") from exc
    lower = _checked_count(strictly_lower_count, "strictly_lower_count")
    equal = _checked_count(equal_count, "equal_count")
    higher = _checked_count(strictly_higher_count, "strictly_higher_count")
    total = _checked_count(scoreable_count, "scoreable_count")
    if total < _MINIMUM_PERCENTILE_POPULATION:
        raise _refuse("scoreable population is below the percentile minimum")
    if equal < 1 or lower + equal + higher != total:
        raise _refuse("score-order count identity is invalid")

    role_percentile = ExactRational.from_values(
        2 * lower + equal,
        2 * total,
    )
    if role is StockScoreOrderRole.PRESSURE:
        pressure_percentile = ExactRational(
            role_percentile.numerator,
            role_percentile.denominator,
        )
    else:
        pressure_percentile = ExactRational.from_values(
            role_percentile.denominator - role_percentile.numerator,
            role_percentile.denominator,
        )

    if total < _MINIMUM_THRESHOLD_CLASSIFICATION_POPULATION:
        return (
            role_percentile,
            pressure_percentile,
            StockPercentileCandidateState.INSUFFICIENT_SCOREABLE_POPULATION,
            None,
        )

    candidate = _rational_at_least(
        role_percentile,
        _PRESSURE_CANDIDATE_MINIMUM,
    )
    state = (
        StockPercentileCandidateState.THRESHOLD_CANDIDATE
        if candidate
        else StockPercentileCandidateState.NOT_THRESHOLD_CANDIDATE
    )
    return role_percentile, pressure_percentile, state, candidate


def _detach_source_row(
    source: StockScoreOrderDisposition,
    *,
    source_already_authenticated: bool = False,
) -> StockScoreOrderDisposition:
    if type(source) is not StockScoreOrderDisposition:
        raise _refuse("source score-order row must use the exact type")
    if not source_already_authenticated:
        StockScoreOrderDisposition._validate_structure(source)
    clone = object.__new__(StockScoreOrderDisposition)
    for name in StockScoreOrderDisposition.__dataclass_fields__:
        value = object.__getattribute__(source, name)
        if name in _SOURCE_RATIONAL_FIELDS:
            value = _detach_rational(value, f"source score-order {name}")
        elif name == "refusal_reasons":
            value = tuple(value)
        object.__setattr__(clone, name, value)
    if not source_already_authenticated:
        StockScoreOrderDisposition._validate_structure(clone)
    return clone


def _source_row_payload(
    source: StockScoreOrderDisposition,
    *,
    source_already_authenticated: bool = False,
) -> dict[str, Any]:
    if type(source) is not StockScoreOrderDisposition:
        raise _refuse("source score-order row must use the exact type")
    if not source_already_authenticated:
        StockScoreOrderDisposition._validate_structure(source)
    return StockScoreOrderDisposition._to_payload_unchecked(source)


def _source_batch_payload(
    source: StockScoreOrderBatch,
    *,
    source_already_authenticated: bool = False,
) -> dict[str, Any]:
    """Serialize an exact validated P0 object without instance dispatch."""
    if type(source) is not StockScoreOrderBatch:
        raise _refuse("source score-order batch must use the exact type")
    if not source_already_authenticated:
        StockScoreOrderBatch._validate_structure(source)
    rows = object.__getattribute__(source, "_dispositions")
    covering_json = object.__getattribute__(
        source,
        "_source_covering_batch_payload_json",
    )
    return {
        "authority": object.__getattribute__(source, "authority"),
        "disposition_count": object.__getattribute__(
            source,
            "disposition_count",
        ),
        "dispositions": [
            _source_row_payload(
                item,
                source_already_authenticated=True,
            )
            for item in rows
        ],
        "independent_return_evaluation_required": True,
        "investability_screen_applied": False,
        "outcome_access_authorized": False,
        "percentile_policy_applied": False,
        "production_authoritative": object.__getattribute__(
            source,
            "production_authoritative",
        ),
        "ranking_decision_authorized": False,
        "release_count": object.__getattribute__(source, "release_count"),
        "research_gate_sha256": object.__getattribute__(
            source,
            "research_gate_sha256",
        ),
        "return_effect_symmetry_assumed": False,
        "schema_version": object.__getattribute__(source, "schema_version"),
        "score_order_inventory_id": SCORE_ORDER_INVENTORY_ID,
        "seed_selection_authorized": False,
        "source_covering_batch": json.loads(covering_json),
        "source_covering_batch_sha256": object.__getattribute__(
            source,
            "source_covering_batch_sha256",
        ),
        "source_batch_verification_required": bool(rows),
        "source_projection_count": object.__getattribute__(
            source,
            "source_projection_count",
        ),
        "source_score_batch_sha256": object.__getattribute__(
            source,
            "source_score_batch_sha256",
        ),
        "standalone_source_authenticated": False,
    }


def _detach_source_batch(source: StockScoreOrderBatch) -> StockScoreOrderBatch:
    """Capture one callback-free, exact, internally consistent P0 snapshot."""
    if type(source) is not StockScoreOrderBatch:
        raise _refuse("input must be the exact StockScoreOrderBatch type")
    try:
        StockScoreOrderBatch._validate_structure(source)
        source_rows = object.__getattribute__(source, "_dispositions")
        rows = tuple(
            _detach_source_row(
                item,
                source_already_authenticated=True,
            )
            for item in source_rows
        )
        clone = object.__new__(StockScoreOrderBatch)
        for name in StockScoreOrderBatch.__dataclass_fields__:
            value = object.__getattribute__(source, name)
            if name == "_dispositions":
                value = rows
            object.__setattr__(clone, name, value)
        StockScoreOrderBatch._validate_structure(clone)
        StockScoreOrderBatch._validate_structure(source)
        if _source_batch_payload(
            source,
            source_already_authenticated=True,
        ) != _source_batch_payload(
            clone,
            source_already_authenticated=True,
        ):
            raise _refuse("source score-order batch changed during capture")
        return clone
    except StockPercentileError:
        raise
    except (
        StockScoreOrderError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise _refuse(
            f"source score-order batch failed authentication: {exc}"
        ) from exc


@dataclasses.dataclass(frozen=True, init=False, slots=True)
class StockPercentileDisposition:
    """One exact structural percentile row derived from SI-3E-P0."""

    _source_score_order_disposition: StockScoreOrderDisposition = (
        dataclasses.field(repr=False, compare=False)
    )
    _source_score_order_disposition_payload_json: str = dataclasses.field(
        repr=False,
        compare=False,
    )
    _bound_source_score_order_batch_sha256: str = dataclasses.field(
        repr=False,
        compare=False,
    )
    percentile_slot_id: str
    percentile_record_id: str
    source_score_order_batch_sha256: str
    source_score_order_disposition_sha256: str
    source_score_order_slot_id: str
    source_score_order_record_id: str
    source_covering_batch_sha256: str
    source_covering_disposition_sha256: str
    source_covering_record_id: str
    source_score_batch_sha256: str
    source_disposition_sha256: str
    source_s1_outcome_sha256: str
    source_normalization_slot_id: str
    normalization_cohort_sha256: str
    normalization_policy_sha256: str
    event_id: str
    selected_event_id: str | None
    revision_selection_state: RevisionSelectionState
    security_id: str
    settlement_date: str
    decision_session: str
    decision_at: str
    role: StockScoreOrderRole
    score: ExactRational | None
    strictly_lower_count: int | None
    equal_count: int | None
    strictly_higher_count: int | None
    scoreable_count: int | None
    source_equivalence_group_sha256: str | None
    role_percentile: ExactRational | None
    pressure_percentile: ExactRational | None
    candidate_state: StockPercentileCandidateState
    threshold_candidate: bool | None
    refusal_reasons: tuple[str, ...]
    percentile_policy_sha256: str
    research_gate_sha256: str
    schema_version: str
    authority: str
    network_access_authorized: bool
    finra_access_authorized: bool
    provider_access_authorized: bool
    source_data_request_authorized: bool
    credential_access_authorized: bool
    licensed_row_access_authorized: bool
    outcome_access_authorized: bool
    shared_holdout_access_authorized: bool
    qc_upload_authorized: bool
    qc_processing_authorized: bool
    qc_job_authorized: bool
    qc_backtest_authorized: bool
    qc_research_inputs_execution_authority: bool
    common_four_family_outcome_evaluation_authorized: bool
    integration_authorized: bool
    capital_authorized: bool
    broker_access_authorized: bool
    operator_database_access_authorized: bool
    scheduler_access_authorized: bool
    paper_trading_authorized: bool
    live_trading_authorized: bool
    deployment_authorized: bool
    trading_authority: bool
    production_authoritative: bool

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "StockPercentileDisposition is constructed only by "
            "build_stock_percentile_projection"
        )

    def __post_init__(self) -> None:
        self._validate_structure()

    def _validate_structure(
        self,
        authenticated_source: StockScoreOrderDisposition | None = None,
    ) -> None:
        if type(self) is not StockPercentileDisposition:
            raise _refuse("percentile row must use the exact frozen type")
        if authenticated_source is None:
            require_stock_percentile_policy(STOCK_PERCENTILE_POLICY)
        for name in (
            "percentile_slot_id",
            "percentile_record_id",
            "source_score_order_batch_sha256",
            "source_score_order_disposition_sha256",
            "source_score_order_slot_id",
            "source_score_order_record_id",
            "source_covering_batch_sha256",
            "source_covering_disposition_sha256",
            "source_covering_record_id",
            "source_score_batch_sha256",
            "source_disposition_sha256",
            "source_s1_outcome_sha256",
            "source_normalization_slot_id",
            "normalization_cohort_sha256",
            "normalization_policy_sha256",
            "event_id",
            "percentile_policy_sha256",
            "research_gate_sha256",
            "_bound_source_score_order_batch_sha256",
        ):
            _checked_sha256(object.__getattribute__(self, name), name)
        if self.selected_event_id is not None:
            _checked_sha256(self.selected_event_id, "selected_event_id")
        for name in (
            "security_id",
            "settlement_date",
            "decision_session",
            "decision_at",
        ):
            _checked_text(object.__getattribute__(self, name), name)
        try:
            _role_value(self.role)
            _revision_state_value(self.revision_selection_state)
        except (
            StockScoreOrderError,
            AttributeError,
            TypeError,
            ValueError,
        ) as exc:
            raise _refuse(f"source score-order enum is invalid: {exc}") from exc
        _candidate_state_value(self.candidate_state)
        if self.normalization_policy_sha256 != _NORMALIZATION_POLICY_SHA256:
            raise _refuse("percentile row has another normalization policy")
        if self.percentile_policy_sha256 != STOCK_PERCENTILE_POLICY_SHA256:
            raise _refuse("percentile row has another percentile policy")
        if self.research_gate_sha256 != SHORT_INTEREST_RESEARCH_GATE_SHA256:
            raise _refuse("percentile row is not bound to the SI-0M gate")
        if type(self.schema_version) is not str or (
            self.schema_version != STOCK_PERCENTILE_SCHEMA_VERSION
        ):
            raise _refuse("unsupported percentile row schema_version")
        if type(self.authority) is not str or (
            self.authority != STRUCTURAL_STOCK_PERCENTILE_AUTHORITY
        ):
            raise _refuse("percentile row has wrong structural authority")
        for name in _FALSE_AUTHORITY_FIELDS:
            value = object.__getattribute__(self, name)
            if type(value) is not bool or value:
                raise _refuse(f"{name} must remain false")
        if type(self.production_authoritative) is not bool or (
            self.production_authoritative
        ):
            raise _refuse("percentile row must remain non-production")

        _checked_reasons(self.refusal_reasons, "percentile refusal reasons")
        counts = (
            self.strictly_lower_count,
            self.equal_count,
            self.strictly_higher_count,
            self.scoreable_count,
        )
        if self.score is None:
            if any(value is not None for value in counts):
                raise _refuse("terminal percentile row cannot carry a count")
            if self.source_equivalence_group_sha256 is not None:
                raise _refuse(
                    "terminal percentile row cannot name an equivalence group"
                )
        else:
            _checked_rational(self.score, "percentile source score")
            if any(value is None for value in counts):
                raise _refuse("scored percentile row requires every exact count")
            lower = _checked_count(
                self.strictly_lower_count,
                "strictly_lower_count",
            )
            equal = _checked_count(self.equal_count, "equal_count")
            higher = _checked_count(
                self.strictly_higher_count,
                "strictly_higher_count",
            )
            scoreable = _checked_count(
                self.scoreable_count,
                "scoreable_count",
            )
            if equal < 1 or lower + equal + higher != scoreable:
                raise _refuse("percentile row count identity is invalid")
            _checked_sha256(
                self.source_equivalence_group_sha256,
                "source_equivalence_group_sha256",
            )
        if (self.role_percentile is None) != (
            self.pressure_percentile is None
        ):
            raise _refuse("percentile values must be jointly present or absent")
        if self.role_percentile is not None:
            _checked_rational(self.role_percentile, "role_percentile")
            _checked_rational(
                self.pressure_percentile,
                "pressure_percentile",
            )
        if self.threshold_candidate is not None and (
            type(self.threshold_candidate) is not bool
        ):
            raise _refuse("threshold_candidate must be an exact boolean or null")

        source = self._source_score_order_disposition
        if type(source) is not StockScoreOrderDisposition:
            raise _refuse("authenticated source row has the wrong exact type")
        if authenticated_source is not None:
            if source is not authenticated_source:
                raise _refuse("percentile row references another source row")
            source_payload = _source_row_payload(
                source,
                source_already_authenticated=True,
            )
        else:
            try:
                StockScoreOrderDisposition._validate_structure(source)
                source_payload = _source_row_payload(
                    source,
                    source_already_authenticated=True,
                )
            except (
                StockScoreOrderError,
                AttributeError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise _refuse(
                    f"authenticated source row is invalid: {exc}"
                ) from exc
        source_json = canonical_json(source_payload)
        if type(self._source_score_order_disposition_payload_json) is not str or (
            self._source_score_order_disposition_payload_json != source_json
        ):
            raise _refuse("authenticated source row payload changed")
        source_sha256 = hash_payload(source_payload)
        if self.source_score_order_disposition_sha256 != source_sha256:
            raise _refuse("authenticated source row hash changed")
        if self.source_score_order_batch_sha256 != (
            self._bound_source_score_order_batch_sha256
        ):
            raise _refuse("percentile row references another source batch")

        expected_slot = hash_payload(
            {
                "percentile_policy_sha256": STOCK_PERCENTILE_POLICY_SHA256,
                "projection_id": STOCK_PERCENTILE_PROJECTION_ID,
                "source_score_order_slot_id": source.score_order_slot_id,
            }
        )
        expected_record = hash_payload(
            {
                "percentile_slot_id": expected_slot,
                "source_score_order_batch_sha256": (
                    self.source_score_order_batch_sha256
                ),
                "source_score_order_disposition_sha256": source_sha256,
            }
        )
        if self.percentile_slot_id != expected_slot:
            raise _refuse("percentile row has wrong slot identity")
        if self.percentile_record_id != expected_record:
            raise _refuse("percentile row has wrong record identity")

        field_map = {
            "source_score_order_slot_id": "score_order_slot_id",
            "source_score_order_record_id": "score_order_record_id",
            "source_covering_batch_sha256": "source_covering_batch_sha256",
            "source_covering_disposition_sha256": (
                "source_covering_disposition_sha256"
            ),
            "source_covering_record_id": "source_covering_record_id",
            "source_score_batch_sha256": "source_score_batch_sha256",
            "source_disposition_sha256": "source_disposition_sha256",
            "source_s1_outcome_sha256": "source_s1_outcome_sha256",
            "source_normalization_slot_id": "source_normalization_slot_id",
            "normalization_cohort_sha256": "normalization_cohort_sha256",
            "normalization_policy_sha256": "normalization_policy_sha256",
            "event_id": "event_id",
            "selected_event_id": "selected_event_id",
            "revision_selection_state": "revision_selection_state",
            "security_id": "security_id",
            "settlement_date": "settlement_date",
            "decision_session": "decision_session",
            "decision_at": "decision_at",
            "role": "role",
            "score": "score",
            "strictly_lower_count": "strictly_lower_count",
            "equal_count": "equal_count",
            "strictly_higher_count": "strictly_higher_count",
            "scoreable_count": "scoreable_count",
            "source_equivalence_group_sha256": "equivalence_group_sha256",
            "refusal_reasons": "refusal_reasons",
        }
        for output_name, source_name in field_map.items():
            if object.__getattribute__(self, output_name) != (
                object.__getattribute__(source, source_name)
            ):
                raise _refuse(
                    "percentile row differs from its authenticated source "
                    f"{source_name}"
                )

        if source.score is None:
            if self.role_percentile is not None or (
                self.pressure_percentile is not None
            ):
                raise _refuse("terminal source row cannot carry a percentile")
            if self.threshold_candidate is not None:
                raise _refuse("terminal source row cannot be classified")
            if self.candidate_state is not (
                StockPercentileCandidateState.SOURCE_TERMINAL
            ):
                raise _refuse("terminal source row has wrong candidate state")
            return

        if self.role_percentile is None or self.pressure_percentile is None:
            raise _refuse("scored source row requires exact percentiles")
        assert source.strictly_lower_count is not None
        assert source.equal_count is not None
        assert source.strictly_higher_count is not None
        assert source.scoreable_count is not None
        expected = _evaluate_order_counts(
            role=source.role,
            strictly_lower_count=source.strictly_lower_count,
            equal_count=source.equal_count,
            strictly_higher_count=source.strictly_higher_count,
            scoreable_count=source.scoreable_count,
        )
        actual = (
            self.role_percentile,
            self.pressure_percentile,
            self.candidate_state,
            self.threshold_candidate,
        )
        if actual != expected:
            raise _refuse(
                "percentile row differs from its authenticated source formula"
            )

    def _validate(self) -> None:
        _require_gate_receipt()
        self._validate_structure()

    def _to_payload_unchecked(self) -> dict[str, Any]:
        payload = {
            "authority": self.authority,
            "candidate_semantic": STOCK_PERCENTILE_POLICY.candidate_semantic,
            "candidate_state": _candidate_state_value(self.candidate_state),
            "decision_at": self.decision_at,
            "decision_session": self.decision_session,
            "equal_count": self.equal_count,
            "event_id": self.event_id,
            "independent_return_evaluation_required": True,
            "investability_screen_applied": False,
            "normalization_cohort_sha256": self.normalization_cohort_sha256,
            "normalization_policy_sha256": self.normalization_policy_sha256,
            "percentile_policy_applied": True,
            "percentile_policy_sha256": self.percentile_policy_sha256,
            "percentile_projection_id": STOCK_PERCENTILE_PROJECTION_ID,
            "percentile_record_id": self.percentile_record_id,
            "percentile_slot_id": self.percentile_slot_id,
            "population_scope": STOCK_PERCENTILE_POLICY.population_scope,
            "pressure_percentile": _rational_payload(
                self.pressure_percentile
            ),
            "production_authoritative": self.production_authoritative,
            "ranking_decision_authorized": False,
            "refusal_reasons": list(self.refusal_reasons),
            "research_gate_sha256": self.research_gate_sha256,
            "return_effect_symmetry_assumed": False,
            "revision_selection_state": _revision_state_value(
                self.revision_selection_state
            ),
            "role": _role_value(self.role),
            "role_percentile": _rational_payload(self.role_percentile),
            "schema_version": self.schema_version,
            "score": _rational_payload(self.score),
            "scoreable_count": self.scoreable_count,
            "security_id": self.security_id,
            "seed_selection_authorized": False,
            "selected_event_id": self.selected_event_id,
            "settlement_date": self.settlement_date,
            "source_batch_verification_required": True,
            "source_covering_batch_sha256": self.source_covering_batch_sha256,
            "source_covering_disposition_sha256": (
                self.source_covering_disposition_sha256
            ),
            "source_covering_record_id": self.source_covering_record_id,
            "source_disposition_sha256": self.source_disposition_sha256,
            "source_equivalence_group_sha256": (
                self.source_equivalence_group_sha256
            ),
            "source_normalization_slot_id": (
                self.source_normalization_slot_id
            ),
            "source_s1_outcome_sha256": self.source_s1_outcome_sha256,
            "source_score_batch_sha256": self.source_score_batch_sha256,
            "source_score_order_batch_sha256": (
                self.source_score_order_batch_sha256
            ),
            "source_score_order_disposition_sha256": (
                self.source_score_order_disposition_sha256
            ),
            "source_score_order_record_id": (
                self.source_score_order_record_id
            ),
            "source_score_order_slot_id": self.source_score_order_slot_id,
            "standalone_source_authenticated": False,
            "strictly_higher_count": self.strictly_higher_count,
            "strictly_lower_count": self.strictly_lower_count,
            "structural_percentile_calculation_applied": (
                self.role_percentile is not None
            ),
            "structural_threshold_classification_applied": (
                self.threshold_candidate is not None
            ),
            "threshold_candidate": self.threshold_candidate,
        }
        for name in _FALSE_AUTHORITY_FIELDS:
            payload[name] = object.__getattribute__(self, name)
        return payload

    def to_payload(self) -> dict[str, Any]:
        self._validate()
        return self._to_payload_unchecked()

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


class _StockPercentileBatchIterator(Iterator[StockPercentileDisposition]):
    """Pin the full projection and refuse before a yield after sabotage."""

    __slots__ = (
        "_batch",
        "_batch_fields",
        "_disposition_sha256s",
        "_dispositions",
        "_index",
        "_source_rows",
    )

    def __init__(self, batch: StockPercentileBatch) -> None:
        StockPercentileBatch._validate_structure(batch)
        self._batch = batch
        self._batch_fields = tuple(
            (name, object.__getattribute__(batch, name))
            for name in StockPercentileBatch.__dataclass_fields__
            if name not in {"_dispositions", "_source_score_order_batch"}
        )
        self._dispositions = object.__getattribute__(batch, "_dispositions")
        source = object.__getattribute__(batch, "_source_score_order_batch")
        self._source_rows = object.__getattribute__(source, "_dispositions")
        self._disposition_sha256s = tuple(
            hash_payload(item._to_payload_unchecked())
            for item in self._dispositions
        )
        self._index = 0

    def __iter__(self) -> _StockPercentileBatchIterator:
        return self

    def _validate_snapshot(self) -> None:
        if type(self._batch) is not StockPercentileBatch:
            raise _refuse("percentile iterator lost its exact batch")
        StockPercentileBatch._validate_structure(self._batch)
        if object.__getattribute__(self._batch, "_dispositions") is not (
            self._dispositions
        ):
            raise _refuse("percentile batch changed after iterator creation")
        source = object.__getattribute__(
            self._batch,
            "_source_score_order_batch",
        )
        if object.__getattribute__(source, "_dispositions") is not (
            self._source_rows
        ):
            raise _refuse("percentile source changed after iterator creation")
        for name, expected in self._batch_fields:
            if object.__getattribute__(self._batch, name) is not expected:
                raise _refuse(
                    f"percentile batch {name} changed after iterator creation"
                )
        for row, expected_sha256 in zip(
            self._dispositions,
            self._disposition_sha256s,
            strict=True,
        ):
            if hash_payload(row._to_payload_unchecked()) != expected_sha256:
                raise _refuse("percentile row changed after iterator creation")

    def __next__(self) -> StockPercentileDisposition:
        self._validate_snapshot()
        if self._index >= len(self._dispositions):
            raise StopIteration
        row = self._dispositions[self._index]
        self._index += 1
        return row


@dataclasses.dataclass(frozen=True, init=False, slots=True)
class StockPercentileBatch:
    """One complete authenticated P0 snapshot and its P1A projection."""

    _dispositions: tuple[StockPercentileDisposition, ...] = dataclasses.field(
        repr=False,
    )
    _source_score_order_batch: StockScoreOrderBatch = dataclasses.field(
        repr=False,
        compare=False,
    )
    _source_score_order_batch_payload_json: str = dataclasses.field(
        repr=False,
        compare=False,
    )
    source_score_order_batch_sha256: str
    disposition_count: int
    percentile_calculation_count: int
    threshold_classification_evaluated_count: int
    threshold_candidate_count: int
    release_count: int
    percentile_policy_sha256: str
    research_gate_sha256: str
    schema_version: str
    authority: str
    network_access_authorized: bool
    finra_access_authorized: bool
    provider_access_authorized: bool
    source_data_request_authorized: bool
    credential_access_authorized: bool
    licensed_row_access_authorized: bool
    outcome_access_authorized: bool
    shared_holdout_access_authorized: bool
    qc_upload_authorized: bool
    qc_processing_authorized: bool
    qc_job_authorized: bool
    qc_backtest_authorized: bool
    qc_research_inputs_execution_authority: bool
    common_four_family_outcome_evaluation_authorized: bool
    integration_authorized: bool
    capital_authorized: bool
    broker_access_authorized: bool
    operator_database_access_authorized: bool
    scheduler_access_authorized: bool
    paper_trading_authorized: bool
    live_trading_authorized: bool
    deployment_authorized: bool
    trading_authority: bool
    production_authoritative: bool

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "StockPercentileBatch is constructed only by "
            "build_stock_percentile_projection"
        )

    def __post_init__(self) -> None:
        self._validate_structure()

    def _validate_structure(self) -> None:
        if type(self) is not StockPercentileBatch:
            raise _refuse("percentile batch must use the exact frozen type")
        require_stock_percentile_policy(STOCK_PERCENTILE_POLICY)
        if type(self._dispositions) is not tuple or not all(
            type(item) is StockPercentileDisposition
            for item in self._dispositions
        ):
            raise _refuse("percentile dispositions must be an exact tuple")
        _checked_sha256(
            self.source_score_order_batch_sha256,
            "source_score_order_batch_sha256",
        )
        _checked_sha256(
            self.percentile_policy_sha256,
            "percentile_policy_sha256",
        )
        _checked_sha256(self.research_gate_sha256, "research_gate_sha256")
        if self.percentile_policy_sha256 != STOCK_PERCENTILE_POLICY_SHA256:
            raise _refuse("percentile batch has another percentile policy")
        if self.research_gate_sha256 != SHORT_INTEREST_RESEARCH_GATE_SHA256:
            raise _refuse("percentile batch is not bound to the SI-0M gate")
        if type(self.schema_version) is not str or (
            self.schema_version != STOCK_PERCENTILE_BATCH_SCHEMA_VERSION
        ):
            raise _refuse("unsupported percentile batch schema_version")
        if type(self.authority) is not str or (
            self.authority != STRUCTURAL_STOCK_PERCENTILE_BATCH_AUTHORITY
        ):
            raise _refuse("percentile batch has wrong structural authority")
        for name in _FALSE_AUTHORITY_FIELDS:
            value = object.__getattribute__(self, name)
            if type(value) is not bool or value:
                raise _refuse(f"{name} must remain false")
        if type(self.production_authoritative) is not bool or (
            self.production_authoritative
        ):
            raise _refuse("percentile batch must remain non-production")
        for name in (
            "disposition_count",
            "percentile_calculation_count",
            "threshold_classification_evaluated_count",
            "threshold_candidate_count",
            "release_count",
        ):
            _checked_count(object.__getattribute__(self, name), name)

        source = self._source_score_order_batch
        if type(source) is not StockScoreOrderBatch:
            raise _refuse("authenticated source batch has wrong exact type")
        try:
            StockScoreOrderBatch._validate_structure(source)
            source_payload = _source_batch_payload(
                source,
                source_already_authenticated=True,
            )
        except (
            StockScoreOrderError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise _refuse(
                f"authenticated source score-order batch is invalid: {exc}"
            ) from exc
        source_json = canonical_json(source_payload)
        if type(self._source_score_order_batch_payload_json) is not str or (
            self._source_score_order_batch_payload_json != source_json
        ):
            raise _refuse("authenticated source score-order payload changed")
        if hash_payload(source_payload) != self.source_score_order_batch_sha256:
            raise _refuse("authenticated source score-order hash changed")

        source_rows = object.__getattribute__(source, "_dispositions")
        if type(self.disposition_count) is not int or (
            self.disposition_count != len(self._dispositions)
        ):
            raise _refuse("percentile disposition count is invalid")
        if self.disposition_count != len(source_rows):
            raise _refuse("percentile batch does not retain every source row")
        if type(self.release_count) is not int or (
            self.release_count != source.release_count
        ):
            raise _refuse("percentile release count is invalid")
        percentile_count = 0
        classification_count = 0
        candidate_count = 0
        for index, (source_row, row) in enumerate(
            zip(source_rows, self._dispositions, strict=True)
        ):
            StockPercentileDisposition._validate_structure(row, source_row)
            if row.source_score_order_batch_sha256 != (
                self.source_score_order_batch_sha256
            ):
                raise _refuse(
                    f"percentile row {index} references another source batch"
                )
            if row.role_percentile is not None:
                percentile_count += 1
            if row.threshold_candidate is not None:
                classification_count += 1
            if row.threshold_candidate is True:
                candidate_count += 1
        if type(self.percentile_calculation_count) is not int or (
            self.percentile_calculation_count != percentile_count
        ):
            raise _refuse("percentile calculation count is invalid")
        if type(self.threshold_classification_evaluated_count) is not int or (
            self.threshold_classification_evaluated_count
            != classification_count
        ):
            raise _refuse("threshold classification count is invalid")
        if type(self.threshold_candidate_count) is not int or (
            self.threshold_candidate_count != candidate_count
        ):
            raise _refuse("percentile threshold candidate count is invalid")

    def _validate(self) -> None:
        _require_gate_receipt()
        self._validate_structure()

    @property
    def dispositions(self) -> tuple[StockPercentileDisposition, ...]:
        self._validate_structure()
        return self._dispositions

    def __len__(self) -> int:
        self._validate_structure()
        return len(self._dispositions)

    def __iter__(self) -> _StockPercentileBatchIterator:
        return _StockPercentileBatchIterator(self)

    @overload
    def __getitem__(self, index: int) -> StockPercentileDisposition: ...

    @overload
    def __getitem__(
        self,
        index: slice,
    ) -> tuple[StockPercentileDisposition, ...]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> StockPercentileDisposition | tuple[StockPercentileDisposition, ...]:
        self._validate_structure()
        return self._dispositions[index]

    def to_payload(self) -> dict[str, Any]:
        self._validate()
        payload = {
            "authority": self.authority,
            "candidate_semantic": STOCK_PERCENTILE_POLICY.candidate_semantic,
            "disposition_count": self.disposition_count,
            "dispositions": [
                item._to_payload_unchecked() for item in self._dispositions
            ],
            "independent_return_evaluation_required": True,
            "investability_screen_applied": False,
            "outcome_access_authorized": False,
            "percentile_policy": STOCK_PERCENTILE_POLICY.to_payload(),
            "percentile_policy_applied": True,
            "percentile_policy_sha256": self.percentile_policy_sha256,
            "percentile_projection_id": STOCK_PERCENTILE_PROJECTION_ID,
            "percentile_calculation_count": (
                self.percentile_calculation_count
            ),
            "population_scope": STOCK_PERCENTILE_POLICY.population_scope,
            "production_authoritative": self.production_authoritative,
            "ranking_decision_authorized": False,
            "release_count": self.release_count,
            "research_gate_sha256": self.research_gate_sha256,
            "return_effect_symmetry_assumed": False,
            "schema_version": self.schema_version,
            "seed_selection_authorized": False,
            "source_batch_verification_required": bool(self._dispositions),
            "source_score_order_batch": json.loads(
                self._source_score_order_batch_payload_json
            ),
            "source_score_order_batch_sha256": (
                self.source_score_order_batch_sha256
            ),
            "standalone_source_authenticated": False,
            "structural_percentile_calculation_applied": (
                self.percentile_calculation_count > 0
            ),
            "structural_threshold_classification_applied": (
                self.threshold_classification_evaluated_count > 0
            ),
            "threshold_classification_evaluated_count": (
                self.threshold_classification_evaluated_count
            ),
            "threshold_candidate_count": self.threshold_candidate_count,
        }
        for name in _FALSE_AUTHORITY_FIELDS:
            payload[name] = object.__getattribute__(self, name)
        return payload

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def _new_disposition(
    *,
    source: StockScoreOrderDisposition,
    source_score_order_batch_sha256: str,
) -> StockPercentileDisposition:
    source_payload = _source_row_payload(
        source,
        source_already_authenticated=True,
    )
    source_json = canonical_json(source_payload)
    source_sha256 = hash_payload(source_payload)
    slot_id = hash_payload(
        {
            "percentile_policy_sha256": STOCK_PERCENTILE_POLICY_SHA256,
            "projection_id": STOCK_PERCENTILE_PROJECTION_ID,
            "source_score_order_slot_id": source.score_order_slot_id,
        }
    )
    record_id = hash_payload(
        {
            "percentile_slot_id": slot_id,
            "source_score_order_batch_sha256": (
                source_score_order_batch_sha256
            ),
            "source_score_order_disposition_sha256": source_sha256,
        }
    )
    if source.score is None:
        role_percentile = None
        pressure_percentile = None
        state = StockPercentileCandidateState.SOURCE_TERMINAL
        candidate = None
    else:
        assert source.strictly_lower_count is not None
        assert source.equal_count is not None
        assert source.strictly_higher_count is not None
        assert source.scoreable_count is not None
        role_percentile, pressure_percentile, state, candidate = (
            _evaluate_order_counts(
                role=source.role,
                strictly_lower_count=source.strictly_lower_count,
                equal_count=source.equal_count,
                strictly_higher_count=source.strictly_higher_count,
                scoreable_count=source.scoreable_count,
            )
        )
    row = object.__new__(StockPercentileDisposition)
    fields = {
        "_source_score_order_disposition": source,
        "_source_score_order_disposition_payload_json": source_json,
        "_bound_source_score_order_batch_sha256": (
            source_score_order_batch_sha256
        ),
        "percentile_slot_id": slot_id,
        "percentile_record_id": record_id,
        "source_score_order_batch_sha256": source_score_order_batch_sha256,
        "source_score_order_disposition_sha256": source_sha256,
        "source_score_order_slot_id": source.score_order_slot_id,
        "source_score_order_record_id": source.score_order_record_id,
        "source_covering_batch_sha256": source.source_covering_batch_sha256,
        "source_covering_disposition_sha256": (
            source.source_covering_disposition_sha256
        ),
        "source_covering_record_id": source.source_covering_record_id,
        "source_score_batch_sha256": source.source_score_batch_sha256,
        "source_disposition_sha256": source.source_disposition_sha256,
        "source_s1_outcome_sha256": source.source_s1_outcome_sha256,
        "source_normalization_slot_id": source.source_normalization_slot_id,
        "normalization_cohort_sha256": source.normalization_cohort_sha256,
        "normalization_policy_sha256": source.normalization_policy_sha256,
        "event_id": source.event_id,
        "selected_event_id": source.selected_event_id,
        "revision_selection_state": source.revision_selection_state,
        "security_id": source.security_id,
        "settlement_date": source.settlement_date,
        "decision_session": source.decision_session,
        "decision_at": source.decision_at,
        "role": source.role,
        "score": _detach_rational(source.score, "source score"),
        "strictly_lower_count": source.strictly_lower_count,
        "equal_count": source.equal_count,
        "strictly_higher_count": source.strictly_higher_count,
        "scoreable_count": source.scoreable_count,
        "source_equivalence_group_sha256": source.equivalence_group_sha256,
        "role_percentile": role_percentile,
        "pressure_percentile": pressure_percentile,
        "candidate_state": state,
        "threshold_candidate": candidate,
        "refusal_reasons": tuple(source.refusal_reasons),
        "percentile_policy_sha256": STOCK_PERCENTILE_POLICY_SHA256,
        "research_gate_sha256": SHORT_INTEREST_RESEARCH_GATE_SHA256,
        "schema_version": STOCK_PERCENTILE_SCHEMA_VERSION,
        "authority": STRUCTURAL_STOCK_PERCENTILE_AUTHORITY,
        "production_authoritative": False,
    }
    for name in _FALSE_AUTHORITY_FIELDS:
        fields[name] = False
    for name, value in fields.items():
        object.__setattr__(row, name, value)
    StockPercentileDisposition._validate_structure(row, source)
    return row


def _new_batch(
    *,
    source: StockScoreOrderBatch,
    source_payload_json: str,
    source_score_order_batch_sha256: str,
    dispositions: tuple[StockPercentileDisposition, ...],
) -> StockPercentileBatch:
    batch = object.__new__(StockPercentileBatch)
    fields = {
        "_dispositions": dispositions,
        "_source_score_order_batch": source,
        "_source_score_order_batch_payload_json": source_payload_json,
        "source_score_order_batch_sha256": source_score_order_batch_sha256,
        "disposition_count": len(dispositions),
        "percentile_calculation_count": sum(
            item.role_percentile is not None for item in dispositions
        ),
        "threshold_classification_evaluated_count": sum(
            item.threshold_candidate is not None for item in dispositions
        ),
        "threshold_candidate_count": sum(
            item.threshold_candidate is True for item in dispositions
        ),
        "release_count": source.release_count,
        "percentile_policy_sha256": STOCK_PERCENTILE_POLICY_SHA256,
        "research_gate_sha256": SHORT_INTEREST_RESEARCH_GATE_SHA256,
        "schema_version": STOCK_PERCENTILE_BATCH_SCHEMA_VERSION,
        "authority": STRUCTURAL_STOCK_PERCENTILE_BATCH_AUTHORITY,
        "production_authoritative": False,
    }
    for name in _FALSE_AUTHORITY_FIELDS:
        fields[name] = False
    for name, value in fields.items():
        object.__setattr__(batch, name, value)
    StockPercentileBatch.__post_init__(batch)
    return batch


def build_stock_percentile_projection(
    score_order_batch: StockScoreOrderBatch,
) -> StockPercentileBatch:
    """Build the exact owner-frozen structural percentile projection."""
    if type(score_order_batch) is not StockScoreOrderBatch:
        raise _refuse("input must be the exact StockScoreOrderBatch type")
    _require_gate_receipt()
    require_stock_percentile_policy(STOCK_PERCENTILE_POLICY)
    source = _detach_source_batch(score_order_batch)
    source_payload = _source_batch_payload(
        source,
        source_already_authenticated=True,
    )
    source_payload_json = canonical_json(source_payload)
    source_sha256 = hash_payload(source_payload)
    source_rows = object.__getattribute__(source, "_dispositions")
    dispositions = tuple(
        _new_disposition(
            source=item,
            source_score_order_batch_sha256=source_sha256,
        )
        for item in source_rows
    )
    return _new_batch(
        source=source,
        source_payload_json=source_payload_json,
        source_score_order_batch_sha256=source_sha256,
        dispositions=dispositions,
    )
