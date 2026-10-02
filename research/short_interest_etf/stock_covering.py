"""Exact, outcome-free SI-3D short-covering projection.

Blueprint equation 4.20 defines the covering signal as the exact negative of
the normalized S1 score. This module projects that identity over a complete,
authenticated SI-3C inventory. One compact V2 score-batch snapshot carries
the shared source evidence; each projection contains only content-addressed
references into that snapshot. The module does not rank or select stocks,
infer return symmetry, read prices or outcomes, aggregate ETFs, or touch
QuantConnect.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import date
from typing import Any, Iterator, overload

from data.exchange_calendar import ExchangeCalendarError, session_open_instant
from data.hashing import canonical_json, hash_payload
from research.short_interest_etf.contracts import format_utc_timestamp
from research.short_interest_etf.preregistration import (
    PREREGISTRATION,
    SHORT_INTEREST_RESEARCH_GATE,
    SHORT_INTEREST_RESEARCH_GATE_SHA256,
    require_short_interest_research_gate,
)
from research.short_interest_etf.stock_features import ExactRational
from research.short_interest_etf.stock_normalization import (
    STOCK_NORMALIZATION_POLICY,
    RevisionSelectionState,
    StockScoreDisposition,
    StockScoreModel,
)
from research.short_interest_etf.stock_score_batch import (
    StockScoreBatchError,
    build_authenticated_stock_score_batch_envelope_v2,
    project_stock_score_covering_sources_v2,
)


COVERING_PROJECTION_ID = "si-stock-covering-projection-v1"
COVERING_SCHEMA_VERSION = "1.0"
COVERING_BATCH_SCHEMA_VERSION = "1.0"
COVERING_EQUATION = "blueprint_4_20_C_equals_negative_B1"
STRUCTURAL_COVERING_AUTHORITY = "synthetic_structural_covering_projection_only"
STRUCTURAL_COVERING_BATCH_AUTHORITY = (
    "synthetic_structural_covering_batch_only"
)
_COMPACT_COVERING_SOURCE_KEYS = frozenset(
    {
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
    }
)


class StockCoveringError(ValueError):
    """The frozen SI-3D projection or complete-batch invariant failed."""


def _refuse(detail: str) -> StockCoveringError:
    return StockCoveringError(f"REFUSED: {detail}")


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


def _checked_date(value: Any, name: str) -> str:
    _checked_text(value, name)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise _refuse(f"{name} must be an ISO calendar date") from exc
    if parsed.isoformat() != value:
        raise _refuse(f"{name} must be a canonical ISO calendar date")
    return value


def _checked_rational(value: Any, name: str) -> ExactRational:
    if type(value) is not ExactRational:
        raise _refuse(f"{name} must be the exact ExactRational type")
    try:
        ExactRational.__post_init__(value)
    except (TypeError, ValueError) as exc:
        raise _refuse(f"{name} is not canonical: {exc}") from exc
    return value


def _checked_reasons(value: Any, name: str) -> tuple[str, ...]:
    if type(value) is not tuple or not all(
        type(item) is str and item and item == item.strip() for item in value
    ):
        raise _refuse(f"{name} must be an exact tuple of canonical strings")
    if value != tuple(sorted(set(value))):
        raise _refuse(f"{name} must be unique and sorted")
    return value


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


def _rational_payload(value: ExactRational | None) -> dict[str, int] | None:
    if value is None:
        return None
    _checked_rational(value, "rational")
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
        raise _refuse(f"{name} rational components must be exact integers")
    try:
        return ExactRational(value["numerator"], value["denominator"])
    except (TypeError, ValueError) as exc:
        raise _refuse(f"{name} is not a canonical rational") from exc


def _require_gate_receipt() -> None:
    receipt = require_short_interest_research_gate(
        SHORT_INTEREST_RESEARCH_GATE
    )
    if (
        type(receipt) is not str
        or receipt != SHORT_INTEREST_RESEARCH_GATE_SHA256
    ):
        raise _refuse("SI-0M admission returned an unexpected receipt")


@dataclasses.dataclass(frozen=True, init=False)
class StockCoveringDisposition:
    """One compact equation-4.20 projection into its enclosing source batch."""

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
    source_s1_score: ExactRational | None
    covering_score: ExactRational | None
    refusal_reasons: tuple[str, ...]
    research_gate_sha256: str = SHORT_INTEREST_RESEARCH_GATE_SHA256
    schema_version: str = COVERING_SCHEMA_VERSION

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "StockCoveringDisposition is constructed only by "
            "build_pit_stock_covering_scores"
        )

    def __post_init__(self) -> None:
        self._validate_structure()

    def _validate_structure(self) -> None:
        if type(self) is not StockCoveringDisposition:
            raise _refuse(
                "covering disposition must be the exact frozen contract type"
            )
        for name in (
            "source_score_batch_sha256",
            "source_disposition_sha256",
            "source_s1_outcome_sha256",
            "source_normalization_slot_id",
            "normalization_cohort_sha256",
            "normalization_policy_sha256",
            "event_id",
        ):
            _checked_sha256(getattr(self, name), name)
        if self.normalization_policy_sha256 != STOCK_NORMALIZATION_POLICY.sha256:
            raise _refuse("covering row is not bound to normalization policy v1")
        if self.selected_event_id is not None:
            _checked_sha256(self.selected_event_id, "selected_event_id")
        if type(self.revision_selection_state) is not RevisionSelectionState:
            raise _refuse("revision_selection_state must be exact")
        _checked_reasons(self.refusal_reasons, "covering.refusal_reasons")

        if self.revision_selection_state is RevisionSelectionState.SELECTED:
            if self.selected_event_id != self.event_id:
                raise _refuse("selected covering row must select its own event")
            if set(self.refusal_reasons) & {
                RevisionSelectionState.SUPERSEDED.value,
                RevisionSelectionState.NOT_VISIBLE.value,
            }:
                raise _refuse(
                    "selected covering row cannot carry a cutoff-only refusal"
                )
        else:
            if self.refusal_reasons != (self.revision_selection_state.value,):
                raise _refuse(
                    "non-selected covering row must preserve its exact "
                    "revision refusal"
                )
            if self.source_s1_score is not None or self.covering_score is not None:
                raise _refuse("non-selected covering row cannot carry a score")
            if self.selected_event_id == self.event_id:
                raise _refuse("non-selected covering row cannot select itself")
            if (
                self.revision_selection_state
                is RevisionSelectionState.SUPERSEDED
                and self.selected_event_id is None
            ):
                raise _refuse(
                    "superseded covering row requires a selected replacement"
                )

        _checked_text(self.security_id, "security_id")
        _checked_date(self.settlement_date, "settlement_date")
        _checked_date(self.decision_session, "decision_session")
        if self.decision_session <= self.settlement_date:
            raise _refuse("decision_session must follow settlement_date")
        _checked_text(self.decision_at, "decision_at")
        try:
            expected_open = format_utc_timestamp(
                session_open_instant(self.decision_session)
            )
        except (ExchangeCalendarError, TypeError, ValueError) as exc:
            raise _refuse(
                f"decision_session is not a tradable XNYS session: {exc}"
            ) from exc
        if self.decision_at != expected_open:
            raise _refuse("decision_at must equal the XNYS session open")

        _checked_sha256(self.research_gate_sha256, "research_gate_sha256")
        if self.research_gate_sha256 != SHORT_INTEREST_RESEARCH_GATE_SHA256:
            raise _refuse("covering disposition is not bound to the SI-0M gate")
        if (
            type(self.schema_version) is not str
            or self.schema_version != COVERING_SCHEMA_VERSION
        ):
            raise _refuse("unsupported covering schema_version")

        if self.source_s1_score is None:
            if self.covering_score is not None:
                raise _refuse("refused S1 source cannot produce a covering score")
            if not self.refusal_reasons:
                raise _refuse("refused S1 source must preserve terminal reasons")
        else:
            _checked_rational(self.source_s1_score, "source_s1_score")
            _checked_rational(self.covering_score, "covering.covering_score")
            expected = ExactRational.from_fraction(
                -self.source_s1_score.to_fraction()
            )
            if self.covering_score != expected:
                raise _refuse("covering score does not equal exact negative S1")
            if self.refusal_reasons:
                raise _refuse(
                    "completed covering score cannot carry refusal reasons"
                )

    def _validate(self) -> None:
        # The admission callback runs first so any callback-side mutation is
        # included in the structural validation and serialized snapshot.
        _require_gate_receipt()
        self._validate_structure()

    def _covering_slot_id_unchecked(self) -> str:
        return hash_payload(
            {
                "authority": STRUCTURAL_COVERING_AUTHORITY,
                "equation": COVERING_EQUATION,
                "projection_id": COVERING_PROJECTION_ID,
                "source_normalization_slot_id": (
                    self.source_normalization_slot_id
                ),
            }
        )

    @property
    def covering_slot_id(self) -> str:
        self._validate_structure()
        return self._covering_slot_id_unchecked()

    def _covering_record_id_unchecked(self) -> str:
        return hash_payload(
            {
                "covering_slot_id": self._covering_slot_id_unchecked(),
                "event_id": self.event_id,
                "source_s1_outcome_sha256": self.source_s1_outcome_sha256,
            }
        )

    @property
    def covering_record_id(self) -> str:
        self._validate_structure()
        return self._covering_record_id_unchecked()

    @property
    def sort_key(self) -> tuple[str, str, str]:
        self._validate_structure()
        return (self.settlement_date, self.security_id, self.event_id)

    def _to_payload_unchecked(self) -> dict[str, Any]:
        return {
            "authority": STRUCTURAL_COVERING_AUTHORITY,
            "blueprint_equation": COVERING_EQUATION,
            "covering_projection_id": COVERING_PROJECTION_ID,
            "covering_record_id": self._covering_record_id_unchecked(),
            "covering_score": _rational_payload(self.covering_score),
            "covering_slot_id": self._covering_slot_id_unchecked(),
            "decision_at": self.decision_at,
            "decision_session": self.decision_session,
            "event_id": self.event_id,
            "independent_return_evaluation_required": True,
            "normalization_cohort_sha256": self.normalization_cohort_sha256,
            "normalization_policy_sha256": self.normalization_policy_sha256,
            "outcome_access_authorized": False,
            "preregistration_sha256": PREREGISTRATION.sha256,
            "production_authoritative": False,
            "refusal_reasons": list(self.refusal_reasons),
            "research_gate_sha256": self.research_gate_sha256,
            "return_effect_symmetry_assumed": False,
            "revision_selection_state": self.revision_selection_state.value,
            "schema_version": self.schema_version,
            "security_id": self.security_id,
            "selected_event_id": self.selected_event_id,
            "settlement_date": self.settlement_date,
            "source_batch_verification_required": True,
            "source_disposition_sha256": self.source_disposition_sha256,
            "source_model": StockScoreModel.S1_DELTA.value,
            "source_normalization_slot_id": self.source_normalization_slot_id,
            "source_s1_outcome_sha256": self.source_s1_outcome_sha256,
            "source_s1_score": _rational_payload(self.source_s1_score),
            "source_score_batch_sha256": self.source_score_batch_sha256,
            "standalone_source_authenticated": False,
        }

    def to_payload(self) -> dict[str, Any]:
        self._validate()
        return self._to_payload_unchecked()

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


class _StockCoveringBatchIterator(Iterator[StockCoveringDisposition]):
    """Pin shared evidence and revalidate all rows before every yield."""

    __slots__ = (
        "_batch",
        "_batch_fields",
        "_index",
        "_projection_sha256s",
        "_projections",
    )

    def __init__(self, batch: StockCoveringBatch) -> None:
        batch._validate_structure()
        self._batch = batch
        self._batch_fields = tuple(
            (name, object.__getattribute__(batch, name))
            for name in (
                "source_score_batch_sha256",
                "source_canonical_row_list_sha256",
                "_source_score_batch_payload_json",
                "research_gate_sha256",
                "schema_version",
                "authority",
                "production_authoritative",
            )
        )
        self._index = 0
        self._projections = batch._projections
        self._projection_sha256s = tuple(
            hash_payload(item._to_payload_unchecked())
            for item in self._projections
        )

    def __iter__(self) -> _StockCoveringBatchIterator:
        return self

    def _validate_snapshot(self) -> None:
        if type(self._batch) is not StockCoveringBatch:
            raise _refuse("covering iterator lost its exact batch")
        if self._batch._projections is not self._projections:
            raise _refuse("covering batch changed after iterator creation")
        for name, expected in self._batch_fields:
            if object.__getattribute__(self._batch, name) is not expected:
                raise _refuse(
                    f"covering batch {name} changed after iterator creation"
                )
        for projection, expected_sha256 in zip(
            self._projections,
            self._projection_sha256s,
            strict=True,
        ):
            projection._validate_structure()
            if hash_payload(projection._to_payload_unchecked()) != (
                expected_sha256
            ):
                raise _refuse("covering row changed after iterator creation")

    def __next__(self) -> StockCoveringDisposition:
        self._validate_snapshot()
        if self._index >= len(self._projections):
            raise StopIteration
        projection = self._projections[self._index]
        self._index += 1
        return projection


@dataclasses.dataclass(frozen=True, init=False)
class StockCoveringBatch:
    """A compact source witness plus canonical SI-3D projections."""

    _projections: tuple[StockCoveringDisposition, ...] = dataclasses.field(
        repr=False
    )
    source_score_batch_sha256: str | None
    source_canonical_row_list_sha256: str | None
    _source_score_batch_payload_json: str | None = dataclasses.field(
        repr=False
    )
    research_gate_sha256: str = SHORT_INTEREST_RESEARCH_GATE_SHA256
    schema_version: str = COVERING_BATCH_SCHEMA_VERSION
    authority: str = STRUCTURAL_COVERING_BATCH_AUTHORITY
    production_authoritative: bool = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "StockCoveringBatch is constructed only by "
            "build_pit_stock_covering_scores"
        )

    def __post_init__(self) -> None:
        self._validate_structure()

    def _validate_structure(self) -> None:
        if type(self) is not StockCoveringBatch:
            raise _refuse("covering batch must be the exact frozen contract type")
        if type(self._projections) is not tuple or not all(
            type(item) is StockCoveringDisposition for item in self._projections
        ):
            raise _refuse(
                "covering projections must be an exact tuple of exact rows"
            )
        _checked_sha256(self.research_gate_sha256, "research_gate_sha256")
        if self.research_gate_sha256 != SHORT_INTEREST_RESEARCH_GATE_SHA256:
            raise _refuse("covering batch is not bound to the SI-0M gate")
        if (
            type(self.schema_version) is not str
            or self.schema_version != COVERING_BATCH_SCHEMA_VERSION
        ):
            raise _refuse("unsupported covering batch schema_version")
        if (
            type(self.authority) is not str
            or self.authority != STRUCTURAL_COVERING_BATCH_AUTHORITY
        ):
            raise _refuse("covering batch has wrong structural authority")
        if type(self.production_authoritative) is not bool or (
            self.production_authoritative
        ):
            raise _refuse("covering batch must remain non-production")

        if not self._projections:
            if any(
                value is not None
                for value in (
                    self.source_score_batch_sha256,
                    self.source_canonical_row_list_sha256,
                    self._source_score_batch_payload_json,
                )
            ):
                raise _refuse("empty covering batch cannot carry source evidence")
            return

        source_batch_sha256 = _checked_sha256(
            self.source_score_batch_sha256,
            "source_score_batch_sha256",
        )
        source_row_list_sha256 = _checked_sha256(
            self.source_canonical_row_list_sha256,
            "source_canonical_row_list_sha256",
        )
        source_payload = _load_json_object(
            self._source_score_batch_payload_json,
            "source_score_batch_payload",
        )
        if hash_payload(source_payload) != source_batch_sha256:
            raise _refuse("source score batch does not match its content hash")
        if source_payload.get("canonical_row_list_sha256") != (
            source_row_list_sha256
        ):
            raise _refuse("source score row-list digest does not match the batch")
        try:
            source_records = project_stock_score_covering_sources_v2(
                source_payload
            )
        except (StockScoreBatchError, AttributeError, TypeError, ValueError) as exc:
            raise _refuse(f"source score batch failed verification: {exc}") from exc
        if len(source_records) != len(self._projections):
            raise _refuse("covering projection count does not match source rows")

        sort_keys: list[tuple[str, str, str]] = []
        record_ids: list[str] = []
        selected_slots: list[str] = []
        for index, (projection, source_record) in enumerate(
            zip(self._projections, source_records, strict=True)
        ):
            projection._validate_structure()
            if projection.source_score_batch_sha256 != source_batch_sha256:
                raise _refuse("covering row references a different source batch")
            if (
                type(source_record) is not dict
                or set(source_record) != _COMPACT_COVERING_SOURCE_KEYS
            ):
                raise _refuse("compact covering source has an invalid shape")
            if source_record["source_disposition_sha256"] != (
                projection.source_disposition_sha256
            ):
                raise _refuse(
                    f"covering row {index} does not match its source disposition"
                )
            source_s1_score = _rational_from_payload(
                source_record["source_s1_score"],
                "source S1 score",
            )
            expected_source_fields = {
                "event_id": projection.event_id,
                "normalization_cohort_sha256": (
                    projection.normalization_cohort_sha256
                ),
                "normalization_policy_sha256": (
                    projection.normalization_policy_sha256
                ),
                "source_normalization_slot_id": (
                    projection.source_normalization_slot_id
                ),
                "refusal_reasons": list(projection.refusal_reasons),
                "revision_selection_state": (
                    projection.revision_selection_state.value
                ),
                "source_s1_score": _rational_payload(
                    projection.source_s1_score
                ),
                "security_id": projection.security_id,
                "selected_event_id": projection.selected_event_id,
                "decision_at": projection.decision_at,
                "decision_session": projection.decision_session,
                "settlement_date": projection.settlement_date,
            }
            for name, expected_value in expected_source_fields.items():
                if source_record[name] != expected_value:
                    raise _refuse(f"source S1 row has mismatched {name}")
            if source_s1_score != projection.source_s1_score:
                raise _refuse("source S1 score does not match covering snapshot")
            if source_record["source_s1_outcome_sha256"] != (
                projection.source_s1_outcome_sha256
            ):
                raise _refuse("source S1 row does not match its content hash")

            sort_keys.append(
                (
                    projection.settlement_date,
                    projection.security_id,
                    projection.event_id,
                )
            )
            record_ids.append(projection._covering_record_id_unchecked())
            if (
                projection.revision_selection_state
                is RevisionSelectionState.SELECTED
            ):
                selected_slots.append(projection._covering_slot_id_unchecked())

        if sort_keys != sorted(sort_keys) or len(sort_keys) != len(set(sort_keys)):
            raise _refuse("covering output is not uniquely canonically ordered")
        if len(record_ids) != len(set(record_ids)):
            raise _refuse("covering output contains duplicate record identity")
        if len(selected_slots) != len(set(selected_slots)):
            raise _refuse("covering produced multiple selected results for one slot")

    def _validate(self) -> None:
        # Gate first: callback-side mutations are validated before serialization.
        _require_gate_receipt()
        self._validate_structure()

    @property
    def projections(self) -> tuple[StockCoveringDisposition, ...]:
        self._validate_structure()
        return self._projections

    def __len__(self) -> int:
        self._validate_structure()
        return len(self._projections)

    def __iter__(self) -> Iterator[StockCoveringDisposition]:
        return _StockCoveringBatchIterator(self)

    @overload
    def __getitem__(self, index: int) -> StockCoveringDisposition: ...

    @overload
    def __getitem__(
        self, index: slice
    ) -> tuple[StockCoveringDisposition, ...]: ...

    def __getitem__(
        self, index: int | slice
    ) -> StockCoveringDisposition | tuple[StockCoveringDisposition, ...]:
        self._validate_structure()
        return self._projections[index]

    def to_payload(self) -> dict[str, Any]:
        self._validate()
        source_payload = (
            None
            if self._source_score_batch_payload_json is None
            else json.loads(self._source_score_batch_payload_json)
        )
        return {
            "authority": self.authority,
            "covering_projection_id": COVERING_PROJECTION_ID,
            "independent_return_evaluation_required": True,
            "outcome_access_authorized": False,
            "production_authoritative": self.production_authoritative,
            "projection_count": len(self._projections),
            "projections": [
                item._to_payload_unchecked() for item in self._projections
            ],
            "research_gate_sha256": self.research_gate_sha256,
            "return_effect_symmetry_assumed": False,
            "schema_version": self.schema_version,
            "source_batch_verification_required": bool(self._projections),
            "source_canonical_row_list_sha256": (
                self.source_canonical_row_list_sha256
            ),
            "source_score_batch": source_payload,
            "source_score_batch_sha256": self.source_score_batch_sha256,
            "standalone_source_authenticated": False,
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def _new_projection(
    *,
    source: dict[str, Any],
    source_score_batch_sha256: str,
) -> StockCoveringDisposition:
    source_s1_score = _rational_from_payload(
        source.get("source_s1_score"),
        "source S1 score",
    )
    covering_score = (
        None
        if source_s1_score is None
        else ExactRational.from_fraction(-source_s1_score.to_fraction())
    )
    try:
        revision_state = RevisionSelectionState(
            source["revision_selection_state"]
        )
        refusal_reasons = tuple(source["refusal_reasons"])
        snapshot_fields = {
            "source_score_batch_sha256": source_score_batch_sha256,
            "source_disposition_sha256": source[
                "source_disposition_sha256"
            ],
            "source_s1_outcome_sha256": source[
                "source_s1_outcome_sha256"
            ],
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
            "revision_selection_state": revision_state,
            "security_id": source["security_id"],
            "settlement_date": source["settlement_date"],
            "decision_session": source["decision_session"],
            "decision_at": source["decision_at"],
            "source_s1_score": source_s1_score,
            "covering_score": covering_score,
            "refusal_reasons": refusal_reasons,
            "research_gate_sha256": SHORT_INTEREST_RESEARCH_GATE_SHA256,
            "schema_version": COVERING_SCHEMA_VERSION,
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise _refuse(f"source S1 snapshot is incomplete: {exc}") from exc
    snapshot = object.__new__(StockCoveringDisposition)
    for name, value in snapshot_fields.items():
        object.__setattr__(snapshot, name, value)
    StockCoveringDisposition.__post_init__(snapshot)
    return snapshot


def _new_batch(
    *,
    projections: tuple[StockCoveringDisposition, ...],
    source_payload_json: str | None,
    source_score_batch_sha256: str | None,
    source_canonical_row_list_sha256: str | None,
) -> StockCoveringBatch:
    batch = object.__new__(StockCoveringBatch)
    fields = {
        "_projections": projections,
        "source_score_batch_sha256": source_score_batch_sha256,
        "source_canonical_row_list_sha256": (
            source_canonical_row_list_sha256
        ),
        "_source_score_batch_payload_json": source_payload_json,
        "research_gate_sha256": SHORT_INTEREST_RESEARCH_GATE_SHA256,
        "schema_version": COVERING_BATCH_SCHEMA_VERSION,
        "authority": STRUCTURAL_COVERING_BATCH_AUTHORITY,
        "production_authoritative": False,
    }
    for name, value in fields.items():
        object.__setattr__(batch, name, value)
    StockCoveringBatch.__post_init__(batch)
    return batch


def build_pit_stock_covering_scores(
    score_dispositions: tuple[StockScoreDisposition, ...],
) -> StockCoveringBatch:
    """Project equation 4.20 over one complete authenticated SI-3C batch."""
    if type(score_dispositions) is not tuple:
        raise _refuse("score_dispositions must be an exact tuple")
    _require_gate_receipt()
    if not score_dispositions:
        return _new_batch(
            projections=(),
            source_payload_json=None,
            source_score_batch_sha256=None,
            source_canonical_row_list_sha256=None,
        )
    try:
        source_envelope = build_authenticated_stock_score_batch_envelope_v2(
            score_dispositions
        )
        source_payload = source_envelope.to_payload()
        source_payload_json = canonical_json(source_payload)
        source_score_batch_sha256 = hashlib.sha256(
            source_payload_json.encode("utf-8")
        ).hexdigest()
        if source_score_batch_sha256 != source_envelope.sha256:
            raise _refuse("authenticated source envelope changed after capture")
        source_records = project_stock_score_covering_sources_v2(
            source_payload
        )
    except StockCoveringError:
        raise
    except (StockScoreBatchError, AttributeError, TypeError, ValueError) as exc:
        raise _refuse(f"covering input failed authentication: {exc}") from exc

    projections = []
    for source in source_records:
        projections.append(
            _new_projection(
                source=source,
                source_score_batch_sha256=source_score_batch_sha256,
            )
        )
    del source_records
    return _new_batch(
        projections=tuple(projections),
        source_payload_json=source_payload_json,
        source_score_batch_sha256=source_score_batch_sha256,
        source_canonical_row_list_sha256=(
            source_envelope.canonical_row_list_sha256
        ),
    )
