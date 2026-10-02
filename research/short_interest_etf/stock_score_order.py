"""Parameter-free SI-3E-P0 exact stock score-order inventory.

This module records the sufficient order statistics needed by a later,
owner-frozen percentile and tie policy.  It deliberately makes no percentile,
seed, investability, ETF, outcome, portfolio, or trading decision.  Every row
is derived from one authenticated SI-3D covering projection and is retained in
both the pressure and covering roles, including terminal/refused rows.
"""
from __future__ import annotations

import dataclasses
import json
from enum import Enum
from typing import Any, Iterator, overload

from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.preregistration import (
    SHORT_INTEREST_RESEARCH_GATE,
    SHORT_INTEREST_RESEARCH_GATE_SHA256,
    require_short_interest_research_gate,
)
from research.short_interest_etf.stock_covering import (
    COVERING_EQUATION,
    COVERING_PROJECTION_ID,
    COVERING_BATCH_SCHEMA_VERSION,
    STRUCTURAL_COVERING_AUTHORITY,
    STRUCTURAL_COVERING_BATCH_AUTHORITY,
    StockCoveringBatch,
    StockCoveringDisposition,
    StockCoveringError,
)
from research.short_interest_etf.stock_features import ExactRational
from research.short_interest_etf.stock_normalization import (
    STOCK_NORMALIZATION_POLICY,
    RevisionSelectionState,
)
from research.short_interest_etf.stock_score_batch import (
    StockScoreBatchError,
    project_stock_score_covering_sources_v2,
)


SCORE_ORDER_INVENTORY_ID = "si-stock-score-order-inventory-v1"
SCORE_ORDER_SCHEMA_VERSION = "1.0"
SCORE_ORDER_BATCH_SCHEMA_VERSION = "1.0"
STRUCTURAL_SCORE_ORDER_AUTHORITY = (
    "synthetic_structural_score_order_inventory_only"
)
STRUCTURAL_SCORE_ORDER_BATCH_AUTHORITY = (
    "synthetic_structural_score_order_batch_only"
)

_ROLE_ORDER: tuple[StockScoreOrderRole, ...]

_SOURCE_PROJECTION_KEYS = frozenset(
    {
        "authority",
        "blueprint_equation",
        "covering_projection_id",
        "covering_record_id",
        "covering_score",
        "covering_slot_id",
        "decision_at",
        "decision_session",
        "event_id",
        "independent_return_evaluation_required",
        "normalization_cohort_sha256",
        "normalization_policy_sha256",
        "outcome_access_authorized",
        "preregistration_sha256",
        "production_authoritative",
        "refusal_reasons",
        "research_gate_sha256",
        "return_effect_symmetry_assumed",
        "revision_selection_state",
        "schema_version",
        "security_id",
        "selected_event_id",
        "settlement_date",
        "source_batch_verification_required",
        "source_disposition_sha256",
        "source_model",
        "source_normalization_slot_id",
        "source_s1_outcome_sha256",
        "source_s1_score",
        "source_score_batch_sha256",
        "standalone_source_authenticated",
    }
)

_SOURCE_BATCH_KEYS = frozenset(
    {
        "authority",
        "covering_projection_id",
        "independent_return_evaluation_required",
        "outcome_access_authorized",
        "production_authoritative",
        "projection_count",
        "projections",
        "research_gate_sha256",
        "return_effect_symmetry_assumed",
        "schema_version",
        "source_batch_verification_required",
        "source_canonical_row_list_sha256",
        "source_score_batch",
        "source_score_batch_sha256",
        "standalone_source_authenticated",
    }
)
_COVERING_BATCH_INSTANCE_FIELDS = frozenset(
    StockCoveringBatch.__dataclass_fields__
)
_COVERING_DISPOSITION_INSTANCE_FIELDS = frozenset(
    StockCoveringDisposition.__dataclass_fields__
)
_EXACT_RATIONAL_INSTANCE_FIELDS = frozenset(ExactRational.__dataclass_fields__)


class StockScoreOrderError(ValueError):
    """The structural score-order inventory failed closed."""


def _refuse(detail: str) -> StockScoreOrderError:
    return StockScoreOrderError(f"REFUSED: {detail}")


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
        raise _refuse(f"{name} must be the exact ExactRational type")
    state = object.__getattribute__(value, "__dict__")
    if not _has_exact_instance_fields(
        state,
        _EXACT_RATIONAL_INSTANCE_FIELDS,
    ):
        raise _refuse(f"{name} has unexpected instance state")
    try:
        ExactRational.__post_init__(value)
    except (TypeError, ValueError) as exc:
        raise _refuse(f"{name} is not canonical: {exc}") from exc
    return value


def _rational_payload(value: ExactRational | None) -> dict[str, int] | None:
    if value is None:
        return None
    _checked_rational(value, "score")
    return ExactRational.to_payload(value)


def _rational_from_payload(value: Any, name: str) -> ExactRational | None:
    if value is None:
        return None
    if type(value) is not dict or set(value) != {"denominator", "numerator"}:
        raise _refuse(f"{name} must be one exact rational payload")
    if (
        type(value["numerator"]) is not int
        or type(value["denominator"]) is not int
    ):
        raise _refuse(f"{name} components must be exact integers")
    try:
        return ExactRational(value["numerator"], value["denominator"])
    except (TypeError, ValueError) as exc:
        raise _refuse(f"{name} is not canonical") from exc


def _checked_json_tree(value: Any, name: str) -> None:
    stack = [(value, name)]
    while stack:
        current, path = stack.pop()
        if current is None or type(current) in (str, int, bool):
            continue
        if type(current) is list:
            stack.extend(
                (item, f"{path}[{index}]")
                for index, item in enumerate(current)
            )
            continue
        if type(current) is dict:
            if not all(type(key) is str for key in current):
                raise _refuse(f"{path} must use exact string keys")
            stack.extend(
                (item, f"{path}.{key}") for key, item in current.items()
            )
            continue
        raise _refuse(f"{path} contains a non-canonical JSON value")


def _load_json_object(value: Any, name: str) -> dict[str, Any]:
    if type(value) is not str or not value:
        raise _refuse(f"{name} must be non-empty canonical JSON text")
    try:
        payload = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise _refuse(f"{name} is not valid JSON") from exc
    if type(payload) is not dict:
        raise _refuse(f"{name} must contain one exact JSON object")
    _checked_json_tree(payload, name)
    if canonical_json(payload) != value:
        raise _refuse(f"{name} must use canonical JSON serialization")
    return payload


def _checked_optional_count(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise _refuse(f"{name} count must be an exact non-negative integer")
    return value


def _require_gate_receipt() -> None:
    receipt = require_short_interest_research_gate(
        SHORT_INTEREST_RESEARCH_GATE
    )
    if (
        type(receipt) is not str
        or receipt != SHORT_INTEREST_RESEARCH_GATE_SHA256
    ):
        raise _refuse("SI-0M gate returned an unexpected receipt")


def _require_exact_covering_batch_instance_state(
    covering_batch: StockCoveringBatch,
) -> dict[str, Any]:
    state = object.__getattribute__(covering_batch, "__dict__")
    if not _has_exact_instance_fields(
        state,
        _COVERING_BATCH_INSTANCE_FIELDS,
    ):
        raise _refuse("source covering batch has unexpected instance state")
    return state


def _has_exact_instance_fields(
    state: Any,
    expected: frozenset[str],
) -> bool:
    if type(state) is not dict:
        return False
    keys = tuple(dict.keys(state))
    if not all(type(key) is str for key in keys):
        return False
    return frozenset(keys) == expected


def _revision_state_value(state: RevisionSelectionState) -> str:
    if state is RevisionSelectionState.SELECTED:
        expected_name, expected_sort_order, expected_value = (
            "SELECTED",
            0,
            "selected_at_release_cutoff",
        )
    elif state is RevisionSelectionState.SUPERSEDED:
        expected_name, expected_sort_order, expected_value = (
            "SUPERSEDED",
            1,
            "superseded_at_release_cutoff",
        )
    elif state is RevisionSelectionState.NOT_VISIBLE:
        expected_name, expected_sort_order, expected_value = (
            "NOT_VISIBLE",
            2,
            "not_visible_at_release_cutoff",
        )
    else:
        raise _refuse("revision state must be a canonical enum member")
    enum_fields = frozenset(
        {"__objclass__", "_name_", "_sort_order_", "_value_"}
    )
    state_values = object.__getattribute__(state, "__dict__")
    if not _has_exact_instance_fields(state_values, enum_fields):
        raise _refuse("revision state has unexpected instance state")
    if (
        type(dict.__getitem__(state_values, "_value_")) is not str
        or dict.__getitem__(state_values, "_value_") != expected_value
        or type(dict.__getitem__(state_values, "_name_")) is not str
        or dict.__getitem__(state_values, "_name_") != expected_name
        or type(dict.__getitem__(state_values, "_sort_order_")) is not int
        or dict.__getitem__(state_values, "_sort_order_") != expected_sort_order
        or dict.__getitem__(state_values, "__objclass__")
        is not RevisionSelectionState
    ):
        raise _refuse("revision state singleton is not canonical")
    return expected_value


def _revision_state_from_value(value: Any) -> RevisionSelectionState:
    if type(value) is not str:
        raise _refuse("revision state value must be exact canonical text")
    if value == "selected_at_release_cutoff":
        state = RevisionSelectionState.SELECTED
    elif value == "superseded_at_release_cutoff":
        state = RevisionSelectionState.SUPERSEDED
    elif value == "not_visible_at_release_cutoff":
        state = RevisionSelectionState.NOT_VISIBLE
    else:
        raise _refuse("revision state value is not canonical")
    _revision_state_value(state)
    return state


def _detach_exact_rational(
    value: Any,
    name: str,
) -> ExactRational | None:
    if value is None:
        return None
    if type(value) is not ExactRational:
        raise _refuse(f"{name} must be the exact ExactRational type")
    state = object.__getattribute__(value, "__dict__")
    if not _has_exact_instance_fields(
        state,
        _EXACT_RATIONAL_INSTANCE_FIELDS,
    ):
        raise _refuse(f"{name} has unexpected instance state")
    _checked_rational(value, name)
    return ExactRational(
        dict.__getitem__(state, "numerator"),
        dict.__getitem__(state, "denominator"),
    )


def _capture_covering_projection(
    projection: StockCoveringDisposition,
    index: int,
) -> dict[str, Any]:
    label = f"source covering row {index}"
    if type(projection) is not StockCoveringDisposition:
        raise _refuse(f"{label} must use the exact SI-3D type")
    state = object.__getattribute__(projection, "__dict__")
    if not _has_exact_instance_fields(
        state,
        _COVERING_DISPOSITION_INSTANCE_FIELDS,
    ):
        raise _refuse(f"{label} has unexpected instance state")
    source_s1_score = _detach_exact_rational(
        dict.__getitem__(state, "source_s1_score"),
        f"{label} source_s1_score",
    )
    covering_score = _detach_exact_rational(
        dict.__getitem__(state, "covering_score"),
        f"{label} covering_score",
    )
    revision_state = dict.__getitem__(state, "revision_selection_state")
    _revision_state_value(revision_state)
    snapshot = object.__new__(StockCoveringDisposition)
    for name in _COVERING_DISPOSITION_INSTANCE_FIELDS:
        value = dict.__getitem__(state, name)
        if name == "source_s1_score":
            value = source_s1_score
        elif name == "covering_score":
            value = covering_score
        elif name == "revision_selection_state":
            value = revision_state
        object.__setattr__(snapshot, name, value)
    try:
        StockCoveringDisposition.__post_init__(snapshot)
        return StockCoveringDisposition._to_payload_unchecked(snapshot)
    except (StockCoveringError, TypeError, ValueError) as exc:
        raise _refuse(f"{label} failed structural validation: {exc}") from exc


def _capture_covering_batch_payload(
    covering_batch: StockCoveringBatch,
) -> dict[str, Any]:
    """Capture SI-3D data without dispatch through caller-owned instances."""
    state = _require_exact_covering_batch_instance_state(covering_batch)
    projections = dict.__getitem__(state, "_projections")
    if type(projections) is not tuple:
        raise _refuse("source covering batch projections must be an exact tuple")
    captured_projections = [
        _capture_covering_projection(item, index)
        for index, item in enumerate(projections)
    ]
    source_json = dict.__getitem__(state, "_source_score_batch_payload_json")
    source_payload = (
        None
        if source_json is None
        else _load_json_object(source_json, "source score batch")
    )
    return {
        "authority": dict.__getitem__(state, "authority"),
        "covering_projection_id": COVERING_PROJECTION_ID,
        "independent_return_evaluation_required": True,
        "outcome_access_authorized": False,
        "production_authoritative": dict.__getitem__(
            state, "production_authoritative"
        ),
        "projection_count": len(captured_projections),
        "projections": captured_projections,
        "research_gate_sha256": dict.__getitem__(
            state, "research_gate_sha256"
        ),
        "return_effect_symmetry_assumed": False,
        "schema_version": dict.__getitem__(state, "schema_version"),
        "source_batch_verification_required": bool(captured_projections),
        "source_canonical_row_list_sha256": dict.__getitem__(
            state, "source_canonical_row_list_sha256"
        ),
        "source_score_batch": source_payload,
        "source_score_batch_sha256": dict.__getitem__(
            state, "source_score_batch_sha256"
        ),
        "standalone_source_authenticated": False,
    }


class StockScoreOrderRole(str, Enum):
    """The two structurally separate views of the same S1 observation."""

    PRESSURE = "pressure"
    COVERING = "covering"


_ROLE_ORDER = (
    StockScoreOrderRole.PRESSURE,
    StockScoreOrderRole.COVERING,
)
_ROLE_INSTANCE_FIELDS = frozenset(
    {"__objclass__", "_name_", "_sort_order_", "_value_"}
)
_ReleaseKey = tuple[str, str, str]
_OrderKey = tuple[_ReleaseKey, StockScoreOrderRole, Any]
_OrderStatistics = dict[_OrderKey, tuple[int, int, int, int]]
_EquivalenceGroups = dict[_OrderKey, tuple[str, tuple[str, ...]]]


def _role_value(role: StockScoreOrderRole) -> str:
    if role is StockScoreOrderRole.PRESSURE:
        expected_name, expected_sort_order, expected_value = (
            "PRESSURE",
            0,
            "pressure",
        )
    elif role is StockScoreOrderRole.COVERING:
        expected_name, expected_sort_order, expected_value = (
            "COVERING",
            1,
            "covering",
        )
    else:
        raise _refuse("score-order role must be a canonical enum member")
    state = object.__getattribute__(role, "__dict__")
    if not _has_exact_instance_fields(state, _ROLE_INSTANCE_FIELDS):
        raise _refuse("score-order role has unexpected instance state")
    if (
        type(dict.__getitem__(state, "_value_")) is not str
        or dict.__getitem__(state, "_value_") != expected_value
        or type(dict.__getitem__(state, "_name_")) is not str
        or dict.__getitem__(state, "_name_") != expected_name
        or type(dict.__getitem__(state, "_sort_order_")) is not int
        or dict.__getitem__(state, "_sort_order_") != expected_sort_order
        or dict.__getitem__(state, "__objclass__") is not StockScoreOrderRole
    ):
        raise _refuse("score-order role singleton is not canonical")
    return expected_value


def _release_key(payload: dict[str, Any]) -> _ReleaseKey:
    return (
        payload["settlement_date"],
        payload["decision_session"],
        payload["decision_at"],
    )


def _source_score(
    payload: dict[str, Any], role: StockScoreOrderRole
) -> ExactRational | None:
    key = (
        "source_s1_score"
        if role is StockScoreOrderRole.PRESSURE
        else "covering_score"
    )
    return _rational_from_payload(
        payload[key],
        f"source {_role_value(role)} score",
    )


def _equivalence_group_sha256(
    *,
    release_key: _ReleaseKey,
    role: StockScoreOrderRole,
    score: ExactRational,
    covering_record_ids: tuple[str, ...],
) -> str:
    return hash_payload(
        {
            "covering_record_ids": list(covering_record_ids),
            "decision_at": release_key[2],
            "decision_session": release_key[1],
            "role": _role_value(role),
            "score": _rational_payload(score),
            "settlement_date": release_key[0],
        }
    )


def _covering_slot_id(source: dict[str, Any]) -> str:
    return hash_payload(
        {
            "authority": STRUCTURAL_COVERING_AUTHORITY,
            "equation": COVERING_EQUATION,
            "projection_id": COVERING_PROJECTION_ID,
            "source_normalization_slot_id": source[
                "source_normalization_slot_id"
            ],
        }
    )


def _covering_record_id(source: dict[str, Any]) -> str:
    return hash_payload(
        {
            "covering_slot_id": _covering_slot_id(source),
            "event_id": source["event_id"],
            "source_s1_outcome_sha256": source[
                "source_s1_outcome_sha256"
            ],
        }
    )


def _score_order_slot_id(source: dict[str, Any], role: StockScoreOrderRole) -> str:
    return hash_payload(
        {
            "inventory_id": SCORE_ORDER_INVENTORY_ID,
            "role": _role_value(role),
            "source_covering_slot_id": source["covering_slot_id"],
        }
    )


def _score_order_record_id(
    source: dict[str, Any], role: StockScoreOrderRole
) -> str:
    return hash_payload(
        {
            "score_order_slot_id": _score_order_slot_id(source, role),
            "source_covering_record_id": source["covering_record_id"],
        }
    )


def _verify_source_covering_projection_structure(
    projection: dict[str, Any],
    label: str,
) -> tuple[ExactRational | None, ExactRational | None]:
    """Rebuild one exact SI-3D row and compare its complete public contract."""
    if set(projection) != _SOURCE_PROJECTION_KEYS:
        raise _refuse(f"{label} has an invalid shape")
    try:
        source_s1_score = _rational_from_payload(
            projection["source_s1_score"],
            f"{label} source S1 score",
        )
        covering_score = _rational_from_payload(
            projection["covering_score"],
            f"{label} covering score",
        )
        snapshot = object.__new__(StockCoveringDisposition)
        fields = {
            "source_score_batch_sha256": projection[
                "source_score_batch_sha256"
            ],
            "source_disposition_sha256": projection[
                "source_disposition_sha256"
            ],
            "source_s1_outcome_sha256": projection[
                "source_s1_outcome_sha256"
            ],
            "source_normalization_slot_id": projection[
                "source_normalization_slot_id"
            ],
            "normalization_cohort_sha256": projection[
                "normalization_cohort_sha256"
            ],
            "normalization_policy_sha256": projection[
                "normalization_policy_sha256"
            ],
            "event_id": projection["event_id"],
            "selected_event_id": projection["selected_event_id"],
            "revision_selection_state": _revision_state_from_value(
                projection["revision_selection_state"]
            ),
            "security_id": projection["security_id"],
            "settlement_date": projection["settlement_date"],
            "decision_session": projection["decision_session"],
            "decision_at": projection["decision_at"],
            "source_s1_score": source_s1_score,
            "covering_score": covering_score,
            "refusal_reasons": tuple(projection["refusal_reasons"]),
            "research_gate_sha256": projection["research_gate_sha256"],
            "schema_version": projection["schema_version"],
        }
        for name, value in fields.items():
            object.__setattr__(snapshot, name, value)
        StockCoveringDisposition.__post_init__(snapshot)
        expected = StockCoveringDisposition._to_payload_unchecked(snapshot)
    except (
        StockCoveringError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise _refuse(f"{label} failed structural validation: {exc}") from exc
    if projection != expected:
        raise _refuse(f"{label} differs from its exact SI-3D contract")
    return source_s1_score, covering_score


def _verify_source_covering_snapshot(
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    """Reauthenticate the embedded SI-3D snapshot without live-object reads."""
    if set(source) != _SOURCE_BATCH_KEYS:
        raise _refuse("source covering batch has an invalid shape")
    if (
        type(source["authority"]) is not str
        or source["authority"] != STRUCTURAL_COVERING_BATCH_AUTHORITY
        or type(source["covering_projection_id"]) is not str
        or source["covering_projection_id"] != COVERING_PROJECTION_ID
        or type(source["schema_version"]) is not str
        or source["schema_version"] != COVERING_BATCH_SCHEMA_VERSION
    ):
        raise _refuse("source covering batch has wrong structural scope")
    for name, expected in (
        ("independent_return_evaluation_required", True),
        ("outcome_access_authorized", False),
        ("production_authoritative", False),
        ("return_effect_symmetry_assumed", False),
        ("standalone_source_authenticated", False),
    ):
        if type(source[name]) is not bool or source[name] is not expected:
            raise _refuse(f"source covering batch has wrong {name}")
    _checked_sha256(
        source["research_gate_sha256"],
        "source covering batch research_gate_sha256",
    )
    if source["research_gate_sha256"] != SHORT_INTEREST_RESEARCH_GATE_SHA256:
        raise _refuse("source covering batch has a different SI-0M gate")

    projections = source["projections"]
    if type(projections) is not list or not all(
        type(item) is dict and set(item) == _SOURCE_PROJECTION_KEYS
        for item in projections
    ):
        raise _refuse("source covering batch projections are invalid")
    if type(source["projection_count"]) is not int or (
        source["projection_count"] != len(projections)
    ):
        raise _refuse("source covering batch projection count is invalid")
    expected_source_required = bool(projections)
    if (
        type(source["source_batch_verification_required"]) is not bool
        or source["source_batch_verification_required"]
        is not expected_source_required
    ):
        raise _refuse("source covering batch has wrong verification scope")

    score_batch = source["source_score_batch"]
    score_batch_sha256 = source["source_score_batch_sha256"]
    row_list_sha256 = source["source_canonical_row_list_sha256"]
    if not projections:
        if any(
            value is not None
            for value in (score_batch, score_batch_sha256, row_list_sha256)
        ):
            raise _refuse("empty source covering batch carries source evidence")
        return projections
    if type(score_batch) is not dict:
        raise _refuse("source covering batch lacks its score batch")
    _checked_sha256(score_batch_sha256, "source score batch SHA-256")
    _checked_sha256(row_list_sha256, "source score row-list SHA-256")
    if hash_payload(score_batch) != score_batch_sha256:
        raise _refuse("embedded score batch does not match its content hash")
    if score_batch.get("canonical_row_list_sha256") != row_list_sha256:
        raise _refuse("embedded score batch has a different row-list hash")
    try:
        source_rows = project_stock_score_covering_sources_v2(score_batch)
    except (StockScoreBatchError, AttributeError, TypeError, ValueError) as exc:
        raise _refuse(f"embedded score batch failed authentication: {exc}") from exc
    if len(source_rows) != len(projections):
        raise _refuse("embedded score batch has a different projection count")

    for index, (projection, source_row) in enumerate(
        zip(projections, source_rows, strict=True)
    ):
        _verify_source_covering_projection_structure(
            projection,
            f"source covering row {index}",
        )
        if projection["source_score_batch_sha256"] != score_batch_sha256:
            raise _refuse(f"source covering row {index} has another score batch")
        source_fields = (
            "decision_at",
            "decision_session",
            "event_id",
            "normalization_cohort_sha256",
            "normalization_policy_sha256",
            "refusal_reasons",
            "revision_selection_state",
            "security_id",
            "selected_event_id",
            "settlement_date",
            "source_disposition_sha256",
            "source_normalization_slot_id",
            "source_s1_outcome_sha256",
            "source_s1_score",
        )
        if any(projection[name] != source_row[name] for name in source_fields):
            raise _refuse(f"source covering row {index} detached from score batch")
    return projections


@dataclasses.dataclass(frozen=True, init=False, slots=True)
class StockScoreOrderDisposition:
    """One source projection viewed under one exact score-order role."""

    _source_covering_projection_payload_json: str = dataclasses.field(
        repr=False
    )
    _bound_source_covering_batch_sha256: str = dataclasses.field(repr=False)
    score_order_slot_id: str
    score_order_record_id: str
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
    source_s1_score: ExactRational | None
    source_covering_score: ExactRational | None
    score: ExactRational | None
    strictly_lower_count: int | None
    equal_count: int | None
    strictly_higher_count: int | None
    scoreable_count: int | None
    equivalence_group_sha256: str | None
    refusal_reasons: tuple[str, ...]
    research_gate_sha256: str = SHORT_INTEREST_RESEARCH_GATE_SHA256
    schema_version: str = SCORE_ORDER_SCHEMA_VERSION
    authority: str = STRUCTURAL_SCORE_ORDER_AUTHORITY
    production_authoritative: bool = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "StockScoreOrderDisposition is constructed only by "
            "build_stock_score_order_inventory"
        )

    def __post_init__(self) -> None:
        self._validate_structure()

    def _validate_structure(self) -> None:
        if type(self) is not StockScoreOrderDisposition:
            raise _refuse("score-order row must use the exact frozen type")
        for name in (
            "score_order_slot_id",
            "score_order_record_id",
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
        ):
            _checked_sha256(getattr(self, name), name)
        _checked_sha256(
            self._bound_source_covering_batch_sha256,
            "bound_source_covering_batch_sha256",
        )
        if self.source_covering_batch_sha256 != (
            self._bound_source_covering_batch_sha256
        ):
            raise _refuse("score-order row has wrong source covering batch")
        if self.normalization_policy_sha256 != STOCK_NORMALIZATION_POLICY.sha256:
            raise _refuse("score-order row has wrong normalization policy")
        _checked_sha256(self.research_gate_sha256, "research_gate_sha256")
        if self.research_gate_sha256 != SHORT_INTEREST_RESEARCH_GATE_SHA256:
            raise _refuse("score-order row is not bound to the SI-0M gate")
        if type(self.schema_version) is not str or (
            self.schema_version != SCORE_ORDER_SCHEMA_VERSION
        ):
            raise _refuse("unsupported score-order schema_version")
        if type(self.authority) is not str or (
            self.authority != STRUCTURAL_SCORE_ORDER_AUTHORITY
        ):
            raise _refuse("score-order row has wrong structural authority")
        if type(self.production_authoritative) is not bool or (
            self.production_authoritative
        ):
            raise _refuse("score-order row must remain non-production")
        if type(self.role) is not StockScoreOrderRole:
            raise _refuse("score-order role must be the exact enum")
        if self.selected_event_id is not None:
            _checked_sha256(self.selected_event_id, "selected_event_id")
        _checked_text(self.security_id, "security_id")
        _checked_text(self.settlement_date, "settlement_date")
        _checked_text(self.decision_session, "decision_session")
        _checked_text(self.decision_at, "decision_at")
        _revision_state_value(self.revision_selection_state)

        source = _load_json_object(
            self._source_covering_projection_payload_json,
            "source covering projection",
        )
        if hash_payload(source) != self.source_covering_disposition_sha256:
            raise _refuse("source covering disposition hash does not match")
        source_s1_score, source_covering_score = (
            _verify_source_covering_projection_structure(
                source,
                "source covering projection",
            )
        )
        if self.source_s1_score is not None:
            _checked_rational(self.source_s1_score, "source_s1_score")
        if self.source_covering_score is not None:
            _checked_rational(
                self.source_covering_score,
                "source_covering_score",
            )
        if self.source_s1_score != source_s1_score or (
            self.source_covering_score != source_covering_score
        ):
            raise _refuse("score-order row does not match its source scores")
        if self.score_order_slot_id != _score_order_slot_id(source, self.role):
            raise _refuse("score-order row has wrong slot identity")
        if self.score_order_record_id != _score_order_record_id(
            source, self.role
        ):
            raise _refuse("score-order row has wrong record identity")

        source_reasons_value = source["refusal_reasons"]
        if type(source_reasons_value) is not list or not all(
            type(item) is str for item in source_reasons_value
        ):
            raise _refuse("source covering refusal reasons are invalid")
        source_reasons = tuple(source_reasons_value)
        _checked_reasons(self.refusal_reasons, "score-order refusal reasons")
        if self.refusal_reasons != source_reasons:
            raise _refuse("score-order refusal does not match its source")

        source_fields = {
            "source_covering_record_id": "covering_record_id",
            "source_score_batch_sha256": "source_score_batch_sha256",
            "source_disposition_sha256": "source_disposition_sha256",
            "source_s1_outcome_sha256": "source_s1_outcome_sha256",
            "source_normalization_slot_id": "source_normalization_slot_id",
            "normalization_cohort_sha256": "normalization_cohort_sha256",
            "normalization_policy_sha256": "normalization_policy_sha256",
            "event_id": "event_id",
            "selected_event_id": "selected_event_id",
            "security_id": "security_id",
            "settlement_date": "settlement_date",
            "decision_session": "decision_session",
            "decision_at": "decision_at",
        }
        for field_name, source_name in source_fields.items():
            if getattr(self, field_name) != source[source_name]:
                label = field_name.replace("_", " ")
                raise _refuse(
                    f"score-order row has mismatched {label}"
                )
        source_state = _revision_state_from_value(
            source["revision_selection_state"]
        )
        if self.revision_selection_state is not source_state:
            raise _refuse("score-order row has mismatched source revision state")

        expected_score = (
            source_s1_score
            if self.role is StockScoreOrderRole.PRESSURE
            else source_covering_score
        )
        counts = (
            self.strictly_lower_count,
            self.equal_count,
            self.strictly_higher_count,
            self.scoreable_count,
        )
        if expected_score is None:
            if self.score is not None or any(
                value is not None for value in counts
            ):
                raise _refuse("terminal score-order row cannot carry a count")
            if self.equivalence_group_sha256 is not None:
                raise _refuse("terminal row cannot name an equivalence group")
            if not self.refusal_reasons:
                raise _refuse("terminal row must retain its source refusal")
            return

        _checked_rational(self.score, "source score")
        if self.score != expected_score:
            raise _refuse("score-order role does not match its source score")
        if self.refusal_reasons:
            raise _refuse("scored row cannot carry a refusal")
        lower = _checked_optional_count(
            self.strictly_lower_count, "strictly_lower"
        )
        equal = _checked_optional_count(self.equal_count, "equal")
        higher = _checked_optional_count(
            self.strictly_higher_count, "strictly_higher"
        )
        scoreable = _checked_optional_count(
            self.scoreable_count, "scoreable"
        )
        if None in (lower, equal, higher, scoreable):
            raise _refuse("scored row requires every exact count")
        assert lower is not None
        assert equal is not None
        assert higher is not None
        assert scoreable is not None
        if equal < 1 or lower + equal + higher != scoreable:
            raise _refuse("score-order count identity is invalid")
        _checked_sha256(
            self.equivalence_group_sha256,
            "equivalence_group_sha256",
        )

    def _validate(self) -> None:
        _require_gate_receipt()
        self._validate_structure()

    def _to_payload_unchecked(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "decision_at": self.decision_at,
            "decision_session": self.decision_session,
            "equal_count": self.equal_count,
            "equivalence_group_sha256": self.equivalence_group_sha256,
            "event_id": self.event_id,
            "independent_return_evaluation_required": True,
            "investability_screen_applied": False,
            "normalization_cohort_sha256": self.normalization_cohort_sha256,
            "normalization_policy_sha256": self.normalization_policy_sha256,
            "outcome_access_authorized": False,
            "percentile_policy_applied": False,
            "production_authoritative": self.production_authoritative,
            "ranking_decision_authorized": False,
            "refusal_reasons": list(self.refusal_reasons),
            "research_gate_sha256": self.research_gate_sha256,
            "return_effect_symmetry_assumed": False,
            "revision_selection_state": _revision_state_value(
                self.revision_selection_state
            ),
            "role": _role_value(self.role),
            "score_order_record_id": self.score_order_record_id,
            "score_order_slot_id": self.score_order_slot_id,
            "score_order_inventory_id": SCORE_ORDER_INVENTORY_ID,
            "schema_version": self.schema_version,
            "score": _rational_payload(self.score),
            "scoreable_count": self.scoreable_count,
            "security_id": self.security_id,
            "seed_selection_authorized": False,
            "selected_event_id": self.selected_event_id,
            "settlement_date": self.settlement_date,
            "source_batch_verification_required": True,
            "source_covering_batch_sha256": (
                self.source_covering_batch_sha256
            ),
            "source_covering_disposition_sha256": (
                self.source_covering_disposition_sha256
            ),
            "source_covering_record_id": self.source_covering_record_id,
            "source_covering_score": _rational_payload(
                self.source_covering_score
            ),
            "source_disposition_sha256": self.source_disposition_sha256,
            "source_normalization_slot_id": (
                self.source_normalization_slot_id
            ),
            "source_s1_outcome_sha256": self.source_s1_outcome_sha256,
            "source_s1_score": _rational_payload(self.source_s1_score),
            "source_score_batch_sha256": self.source_score_batch_sha256,
            "standalone_source_authenticated": False,
            "strictly_higher_count": self.strictly_higher_count,
            "strictly_lower_count": self.strictly_lower_count,
        }

    def to_payload(self) -> dict[str, Any]:
        self._validate()
        return self._to_payload_unchecked()

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


class _StockScoreOrderBatchIterator(Iterator[StockScoreOrderDisposition]):
    """Pin the full inventory and fail before every yield after sabotage."""

    __slots__ = (
        "_batch",
        "_batch_fields",
        "_disposition_sha256s",
        "_dispositions",
        "_index",
    )

    def __init__(self, batch: StockScoreOrderBatch) -> None:
        StockScoreOrderBatch._validate_structure(batch)
        self._batch = batch
        self._batch_fields = tuple(
            (name, object.__getattribute__(batch, name))
            for name in (
                "_source_covering_batch_payload_json",
                "source_covering_batch_sha256",
                "source_score_batch_sha256",
                "source_projection_count",
                "disposition_count",
                "release_count",
                "research_gate_sha256",
                "schema_version",
                "authority",
                "production_authoritative",
            )
        )
        self._dispositions = batch._dispositions
        self._disposition_sha256s = tuple(
            hash_payload(
                StockScoreOrderDisposition._to_payload_unchecked(item)
            )
            for item in self._dispositions
        )
        self._index = 0

    def __iter__(self) -> _StockScoreOrderBatchIterator:
        return self

    def _validate_snapshot(self) -> None:
        if type(self._batch) is not StockScoreOrderBatch:
            raise _refuse("score-order iterator lost its exact batch")
        StockScoreOrderBatch._validate_structure(self._batch)
        if self._batch._dispositions is not self._dispositions:
            raise _refuse("score-order batch changed after iterator creation")
        for name, expected in self._batch_fields:
            if object.__getattribute__(self._batch, name) is not expected:
                raise _refuse(
                    f"score-order batch {name} changed after iterator creation"
                )
        for disposition, expected_sha256 in zip(
            self._dispositions,
            self._disposition_sha256s,
            strict=True,
        ):
            StockScoreOrderDisposition._validate_structure(disposition)
            if hash_payload(
                StockScoreOrderDisposition._to_payload_unchecked(disposition)
            ) != (
                expected_sha256
            ):
                raise _refuse("score-order row changed after iterator creation")

    def __next__(self) -> StockScoreOrderDisposition:
        self._validate_snapshot()
        if self._index >= len(self._dispositions):
            raise StopIteration
        disposition = self._dispositions[self._index]
        self._index += 1
        return disposition


@dataclasses.dataclass(frozen=True, init=False, slots=True)
class StockScoreOrderBatch:
    """One authenticated source snapshot and its exact order inventory."""

    _dispositions: tuple[StockScoreOrderDisposition, ...] = dataclasses.field(
        repr=False
    )
    _source_covering_batch_payload_json: str = dataclasses.field(repr=False)
    source_covering_batch_sha256: str
    source_score_batch_sha256: str | None
    source_projection_count: int
    disposition_count: int
    release_count: int
    research_gate_sha256: str = SHORT_INTEREST_RESEARCH_GATE_SHA256
    schema_version: str = SCORE_ORDER_BATCH_SCHEMA_VERSION
    authority: str = STRUCTURAL_SCORE_ORDER_BATCH_AUTHORITY
    production_authoritative: bool = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "StockScoreOrderBatch is constructed only by "
            "build_stock_score_order_inventory"
        )

    def __post_init__(self) -> None:
        self._validate_structure()

    def _validate_structure(self) -> None:
        if type(self) is not StockScoreOrderBatch:
            raise _refuse("score-order batch must use the exact frozen type")
        if type(self._dispositions) is not tuple or not all(
            type(item) is StockScoreOrderDisposition
            for item in self._dispositions
        ):
            raise _refuse("score-order dispositions must be an exact tuple")
        _checked_sha256(
            self.source_covering_batch_sha256,
            "source_covering_batch_sha256",
        )
        if self.source_score_batch_sha256 is not None:
            _checked_sha256(
                self.source_score_batch_sha256,
                "source_score_batch_sha256",
            )
        _checked_sha256(self.research_gate_sha256, "research_gate_sha256")
        if self.research_gate_sha256 != SHORT_INTEREST_RESEARCH_GATE_SHA256:
            raise _refuse("score-order batch is not bound to the SI-0M gate")
        if type(self.schema_version) is not str or (
            self.schema_version != SCORE_ORDER_BATCH_SCHEMA_VERSION
        ):
            raise _refuse("unsupported score-order batch schema_version")
        if type(self.authority) is not str or (
            self.authority != STRUCTURAL_SCORE_ORDER_BATCH_AUTHORITY
        ):
            raise _refuse("score-order batch has wrong structural authority")
        if type(self.production_authoritative) is not bool or (
            self.production_authoritative
        ):
            raise _refuse("score-order batch must remain non-production")
        for row in self._dispositions:
            StockScoreOrderDisposition._validate_structure(row)

        source = _load_json_object(
            self._source_covering_batch_payload_json,
            "source covering batch",
        )
        if hash_payload(source) != self.source_covering_batch_sha256:
            raise _refuse("source covering batch hash does not match")
        projections = _verify_source_covering_snapshot(source)

        expected_source_score_batch_sha256 = source[
            "source_score_batch_sha256"
        ]
        if expected_source_score_batch_sha256 is not None:
            _checked_sha256(
                expected_source_score_batch_sha256,
                "source source_score_batch_sha256",
            )
        if self.source_score_batch_sha256 != (
            expected_source_score_batch_sha256
        ):
            raise _refuse("score-order batch has mismatched source score batch")

        expected_keys = tuple(
            (hash_payload(projection), role)
            for projection in projections
            for role in _ROLE_ORDER
        )
        actual_keys = tuple(
            (item.source_covering_disposition_sha256, item.role)
            for item in self._dispositions
        )
        if len(actual_keys) != len(set(actual_keys)):
            raise _refuse("score-order batch contains a duplicate disposition")
        if set(actual_keys) != set(expected_keys):
            raise _refuse("score-order batch does not retain the complete source")
        if actual_keys != expected_keys:
            raise _refuse("score-order batch is not canonically ordered")
        if type(self.source_projection_count) is not int or (
            self.source_projection_count != len(projections)
        ):
            raise _refuse("score-order source projection count is invalid")
        if type(self.disposition_count) is not int or (
            self.disposition_count != len(self._dispositions)
        ):
            raise _refuse("score-order disposition count is invalid")

        release_keys = {_release_key(projection) for projection in projections}
        if type(self.release_count) is not int or (
            self.release_count != len(release_keys)
        ):
            raise _refuse("score-order release count is invalid")

        stats, groups = _order_statistics(projections)
        for index, (row, source_projection) in enumerate(
            zip(
                self._dispositions,
                (
                    projection
                    for projection in projections
                    for _role in _ROLE_ORDER
                ),
                strict=True,
            )
        ):
            StockScoreOrderDisposition._validate_structure(row)
            source_json = canonical_json(source_projection)
            if row._source_covering_projection_payload_json != source_json:
                raise _refuse(
                    f"score-order row {index} has mismatched source projection"
                )
            if row.source_covering_batch_sha256 != (
                self.source_covering_batch_sha256
            ):
                raise _refuse("score-order row references another source batch")
            if row.source_score_batch_sha256 != self.source_score_batch_sha256:
                raise _refuse("score-order row references another score batch")
            expected = _expected_order_values(
                source_projection,
                row.role,
                stats,
                groups,
            )
            actual = (
                row.score,
                row.strictly_lower_count,
                row.equal_count,
                row.strictly_higher_count,
                row.scoreable_count,
                row.equivalence_group_sha256,
            )
            if actual != expected:
                raise _refuse("score-order row has incorrect exact counts")

    def _validate(self) -> None:
        _require_gate_receipt()
        self._validate_structure()

    @property
    def dispositions(self) -> tuple[StockScoreOrderDisposition, ...]:
        self._validate_structure()
        return self._dispositions

    def __len__(self) -> int:
        self._validate_structure()
        return len(self._dispositions)

    def __iter__(self) -> _StockScoreOrderBatchIterator:
        return _StockScoreOrderBatchIterator(self)

    @overload
    def __getitem__(self, index: int) -> StockScoreOrderDisposition: ...

    @overload
    def __getitem__(
        self, index: slice
    ) -> tuple[StockScoreOrderDisposition, ...]: ...

    def __getitem__(
        self, index: int | slice
    ) -> StockScoreOrderDisposition | tuple[StockScoreOrderDisposition, ...]:
        self._validate_structure()
        return self._dispositions[index]

    def to_payload(self) -> dict[str, Any]:
        self._validate()
        return {
            "authority": self.authority,
            "disposition_count": self.disposition_count,
            "dispositions": [
                StockScoreOrderDisposition._to_payload_unchecked(item)
                for item in self._dispositions
            ],
            "independent_return_evaluation_required": True,
            "investability_screen_applied": False,
            "outcome_access_authorized": False,
            "percentile_policy_applied": False,
            "production_authoritative": self.production_authoritative,
            "ranking_decision_authorized": False,
            "release_count": self.release_count,
            "research_gate_sha256": self.research_gate_sha256,
            "return_effect_symmetry_assumed": False,
            "schema_version": self.schema_version,
            "score_order_inventory_id": SCORE_ORDER_INVENTORY_ID,
            "seed_selection_authorized": False,
            "source_covering_batch": json.loads(
                self._source_covering_batch_payload_json
            ),
            "source_covering_batch_sha256": (
                self.source_covering_batch_sha256
            ),
            "source_batch_verification_required": bool(self._dispositions),
            "source_projection_count": self.source_projection_count,
            "source_score_batch_sha256": self.source_score_batch_sha256,
            "standalone_source_authenticated": False,
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def _order_statistics(
    projections: list[dict[str, Any]],
) -> tuple[_OrderStatistics, _EquivalenceGroups]:
    values: dict[
        tuple[tuple[str, str, str], StockScoreOrderRole],
        list[tuple[Any, str]],
    ] = {}
    for projection in projections:
        release_key = _release_key(projection)
        for role in _ROLE_ORDER:
            score = _source_score(projection, role)
            if score is None:
                continue
            values.setdefault((release_key, role), []).append(
                (score.to_fraction(), projection["covering_record_id"])
            )

    stats: _OrderStatistics = {}
    groups: _EquivalenceGroups = {}
    for (release_key, role), scored_rows in values.items():
        members_by_score: dict[Any, list[str]] = {}
        for score, record_id in scored_rows:
            members_by_score.setdefault(score, []).append(record_id)
        total = len(scored_rows)
        lower = 0
        for score in sorted(members_by_score):
            member_ids = tuple(sorted(members_by_score[score]))
            equal = len(member_ids)
            key = (release_key, role, score)
            stats[key] = (lower, equal, total - lower - equal, total)
            rational = ExactRational.from_fraction(score)
            groups[key] = (
                _equivalence_group_sha256(
                    release_key=release_key,
                    role=role,
                    score=rational,
                    covering_record_ids=member_ids,
                ),
                member_ids,
            )
            lower += equal
    return stats, groups


def _expected_order_values(
    projection: dict[str, Any],
    role: StockScoreOrderRole,
    stats: _OrderStatistics,
    groups: _EquivalenceGroups,
) -> tuple[
    ExactRational | None,
    int | None,
    int | None,
    int | None,
    int | None,
    str | None,
]:
    score = _source_score(projection, role)
    if score is None:
        return (None, None, None, None, None, None)
    key = (_release_key(projection), role, score.to_fraction())
    lower, equal, higher, total = stats[key]
    group_sha256, _members = groups[key]
    return (score, lower, equal, higher, total, group_sha256)


def _new_disposition(
    *,
    source: dict[str, Any],
    source_covering_batch_sha256: str,
    role: StockScoreOrderRole,
    expected: tuple[
        ExactRational | None,
        int | None,
        int | None,
        int | None,
        int | None,
        str | None,
    ],
) -> StockScoreOrderDisposition:
    score, lower, equal, higher, scoreable, group_sha256 = expected
    source_s1_score = _rational_from_payload(
        source["source_s1_score"], "source S1 score"
    )
    source_covering_score = _rational_from_payload(
        source["covering_score"], "source covering score"
    )
    row = object.__new__(StockScoreOrderDisposition)
    fields = {
        "_source_covering_projection_payload_json": canonical_json(source),
        "_bound_source_covering_batch_sha256": source_covering_batch_sha256,
        "score_order_slot_id": _score_order_slot_id(source, role),
        "score_order_record_id": _score_order_record_id(source, role),
        "source_covering_batch_sha256": source_covering_batch_sha256,
        "source_covering_disposition_sha256": hash_payload(source),
        "source_covering_record_id": source["covering_record_id"],
        "source_score_batch_sha256": source["source_score_batch_sha256"],
        "source_disposition_sha256": source["source_disposition_sha256"],
        "source_s1_outcome_sha256": source["source_s1_outcome_sha256"],
        "source_normalization_slot_id": source[
            "source_normalization_slot_id"
        ],
        "normalization_cohort_sha256": source[
            "normalization_cohort_sha256"
        ],
        "normalization_policy_sha256": source[
            "normalization_policy_sha256"
        ],
        "event_id": source["event_id"],
        "selected_event_id": source["selected_event_id"],
        "revision_selection_state": _revision_state_from_value(
            source["revision_selection_state"]
        ),
        "security_id": source["security_id"],
        "settlement_date": source["settlement_date"],
        "decision_session": source["decision_session"],
        "decision_at": source["decision_at"],
        "role": role,
        "source_s1_score": source_s1_score,
        "source_covering_score": source_covering_score,
        "score": score,
        "strictly_lower_count": lower,
        "equal_count": equal,
        "strictly_higher_count": higher,
        "scoreable_count": scoreable,
        "equivalence_group_sha256": group_sha256,
        "refusal_reasons": tuple(source["refusal_reasons"]),
        "research_gate_sha256": SHORT_INTEREST_RESEARCH_GATE_SHA256,
        "schema_version": SCORE_ORDER_SCHEMA_VERSION,
        "authority": STRUCTURAL_SCORE_ORDER_AUTHORITY,
        "production_authoritative": False,
    }
    for name, value in fields.items():
        object.__setattr__(row, name, value)
    StockScoreOrderDisposition.__post_init__(row)
    return row


def _new_batch(
    *,
    dispositions: tuple[StockScoreOrderDisposition, ...],
    source_payload_json: str,
    source_covering_batch_sha256: str,
    source_score_batch_sha256: str | None,
    source_projection_count: int,
    release_count: int,
) -> StockScoreOrderBatch:
    batch = object.__new__(StockScoreOrderBatch)
    fields = {
        "_dispositions": dispositions,
        "_source_covering_batch_payload_json": source_payload_json,
        "source_covering_batch_sha256": source_covering_batch_sha256,
        "source_score_batch_sha256": source_score_batch_sha256,
        "source_projection_count": source_projection_count,
        "disposition_count": len(dispositions),
        "release_count": release_count,
        "research_gate_sha256": SHORT_INTEREST_RESEARCH_GATE_SHA256,
        "schema_version": SCORE_ORDER_BATCH_SCHEMA_VERSION,
        "authority": STRUCTURAL_SCORE_ORDER_BATCH_AUTHORITY,
        "production_authoritative": False,
    }
    for name, value in fields.items():
        object.__setattr__(batch, name, value)
    StockScoreOrderBatch.__post_init__(batch)
    return batch


def build_stock_score_order_inventory(
    covering_batch: StockCoveringBatch,
) -> StockScoreOrderBatch:
    """Build exact release-local tie statistics without making a rank decision."""
    if type(covering_batch) is not StockCoveringBatch:
        raise _refuse("input must be the exact StockCoveringBatch type")
    _require_gate_receipt()
    _require_exact_covering_batch_instance_state(covering_batch)
    try:
        source_payload = _capture_covering_batch_payload(covering_batch)
        projections = _verify_source_covering_snapshot(source_payload)
        source_payload_json = canonical_json(source_payload)
    except (
        StockCoveringError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise _refuse(f"source covering batch failed authentication: {exc}") from exc
    source_covering_batch_sha256 = hash_payload(source_payload)
    stats, groups = _order_statistics(projections)
    dispositions = tuple(
        _new_disposition(
            source=projection,
            source_covering_batch_sha256=source_covering_batch_sha256,
            role=role,
            expected=_expected_order_values(
                projection,
                role,
                stats,
                groups,
            ),
        )
        for projection in projections
        for role in _ROLE_ORDER
    )
    return _new_batch(
        dispositions=dispositions,
        source_payload_json=source_payload_json,
        source_covering_batch_sha256=source_covering_batch_sha256,
        source_score_batch_sha256=source_payload.get(
            "source_score_batch_sha256"
        ),
        source_projection_count=len(projections),
        release_count=len({_release_key(item) for item in projections}),
    )
