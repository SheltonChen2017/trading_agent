"""Pure, outcome-free stock-control residualization for ARV2-4A.

This module can transform synthetic pre-open control evidence, fit a training-
only Decimal OLS model, and apply frozen coefficients.  Its outputs remain
structural candidates and expose no data, outcome, QC, deployment or order
authority.
"""
from __future__ import annotations

import dataclasses
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from typing import Any, Iterable

from data.exchange_calendar import (
    ExchangeCalendarError,
    is_trading_session,
    resolve_nth_session_after,
    session_open_instant,
)

from .canonical import (
    canonical_json_bytes,
    parse_date,
    parse_utc_timestamp,
    require_identifier,
    require_sha256,
    sha256_bytes,
)
from .stock_evaluation_contract import (
    CONTROL_DEFINITION,
    StockEvaluationContract,
    StockEvaluationContractError,
    require_loaded_stock_evaluation_contract,
)
from .stock_signal import (
    StockRawState,
    StockSignalError,
    StructuralStockScoreCandidate,
)


class StockControlError(ValueError):
    """Structural control evidence, fit, or application is invalid."""


STRUCTURAL_CONTROL_MODEL_SCHEMA = "arv2-structural-stock-control-model-v1"
STRUCTURAL_CONTROL_BATCH_SCHEMA = "arv2-structural-control-adjusted-stock-v1"
STRUCTURAL_CONTROL_AUTHORITY = (
    "structural_fixture_only_no_source_outcome_qc_or_execution_authority"
)

CONTINUOUS_COLUMNS = tuple(CONTROL_DEFINITION["continuous_columns"])
BINARY_COLUMNS = tuple(CONTROL_DEFINITION["binary_columns"])
CONTROL_COLUMNS = (*CONTINUOUS_COLUMNS, *BINARY_COLUMNS)
FORBIDDEN_COLUMNS = frozenset(CONTROL_DEFINITION["forbidden_pretrade_columns"])
_MAD_SCALE = Decimal("1.4826")
_RANK_RELATIVE_THRESHOLD = Decimal(
    CONTROL_DEFINITION["rank_relative_threshold"]
)
_PRECISION = int(CONTROL_DEFINITION["decimal_precision"])
_CONTEXT_EMIN = int(CONTROL_DEFINITION["decimal_emin"])
_CONTEXT_EMAX = int(CONTROL_DEFINITION["decimal_emax"])
_CLIP_LOW = Decimal(CONTROL_DEFINITION["active_residual_clip"][0])
_CLIP_HIGH = Decimal(CONTROL_DEFINITION["active_residual_clip"][1])
_COVERAGE_NUMERATOR = int(
    CONTROL_DEFINITION["minimum_accepted_control_coverage"]["numerator"]
)
_COVERAGE_DENOMINATOR = int(
    CONTROL_DEFINITION["minimum_accepted_control_coverage"]["denominator"]
)
_MINIMUM_ACCEPTED_ROWS = int(
    CONTROL_DEFINITION["minimum_accepted_rows_per_cross_section"]
)
_PREOPEN_REFUSAL_REASONS = frozenset(
    {
        "missing_control_evidence",
        "wrong_decision_session",
        "not_available_strictly_before_open",
    }
)
_APPLICATION_REFUSAL_REASONS = frozenset(
    {
        *(f"preopen_control::{value}" for value in _PREOPEN_REFUSAL_REASONS),
        "unseen_training_industry",
    }
)


def _frozen_decimal_context() -> Context:
    return Context(
        prec=_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=_CONTEXT_EMIN,
        Emax=_CONTEXT_EMAX,
        capitals=1,
        clamp=0,
    )


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise StockControlError(f"{name} must be exact and cannot be bool/float")
    if type(value) is Decimal:
        parsed = value
    elif type(value) is int:
        parsed = Decimal(value)
    elif type(value) is str and value and value == value.strip():
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise StockControlError(f"{name} must be a finite exact decimal") from exc
    else:
        raise StockControlError(f"{name} must be a finite exact decimal")
    if not parsed.is_finite():
        raise StockControlError(f"{name} must be finite")
    return parsed


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value, "f")


def _median(values: Iterable[Decimal]) -> Decimal:
    ordered = tuple(sorted(values))
    if not ordered:
        raise StockControlError("median requires at least one value")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    with localcontext(_frozen_decimal_context()):
        return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _require_contract(contract: StockEvaluationContract) -> None:
    try:
        require_loaded_stock_evaluation_contract(contract)
    except StockEvaluationContractError as exc:
        raise StockControlError("control work requires a loaded contract") from exc
    section = contract.sections.get("control_definition")
    if section != CONTROL_DEFINITION:
        raise StockControlError("stock control definition changed")
    if any(value is not None for value in contract.external_bindings.values()):
        raise StockControlError("ARV2-4A control work must remain externally unbound")
    if (
        contract.source_access_available
        or contract.outcome_access_available
        or contract.qc_action_available
        or contract.deployment_available
        or contract.orders_available
    ):
        raise StockControlError("structural control contract acquired action authority")


@dataclasses.dataclass(frozen=True)
class PreopenControlEvidenceRow:
    security_id: str
    industry_id: str
    decision_session: str
    available_at: str
    source_evidence_sha256: str
    values: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        require_identifier(self.security_id, "security_id")
        require_identifier(self.industry_id, "industry_id")
        parse_date(self.decision_session, "decision_session")
        parse_utc_timestamp(self.available_at, "available_at")
        require_sha256(self.source_evidence_sha256, "source_evidence_sha256")
        if type(self.values) is not tuple or any(
            type(item) is not tuple or len(item) != 2 for item in self.values
        ):
            raise StockControlError("control values must be exact name/value tuples")
        names = tuple(item[0] for item in self.values)
        if len(set(names)) != len(names):
            raise StockControlError("control values contain duplicate columns")
        forbidden = set(names) & FORBIDDEN_COLUMNS
        if forbidden:
            raise StockControlError("outcome-only price-jump controls are forbidden pretrade")
        if names != CONTROL_COLUMNS:
            raise StockControlError("control columns are missing, unknown, or out of order")
        for name, value in self.values[: len(CONTINUOUS_COLUMNS)]:
            if type(value) is not Decimal:
                raise StockControlError(f"continuous control {name} must be an exact Decimal")
            _decimal(value, name)
        for name, value in self.values[len(CONTINUOUS_COLUMNS) :]:
            if type(value) is not int or value not in (0, 1):
                raise StockControlError(f"binary control {name} must be exact zero or one")

    def value_map(self) -> dict[str, Decimal]:
        result: dict[str, Decimal] = {}
        for name, value in self.values[: len(CONTINUOUS_COLUMNS)]:
            result[name] = _decimal(value, name)
        for name, value in self.values[len(CONTINUOUS_COLUMNS) :]:
            result[name] = Decimal(value)
        return result

    def to_record(self) -> dict[str, Any]:
        values: list[list[object]] = []
        for name, value in self.values:
            rendered: object = (
                value if name in BINARY_COLUMNS else _decimal_text(_decimal(value, name))
            )
            values.append([name, rendered])
        return {
            "security_id": self.security_id,
            "industry_id": self.industry_id,
            "decision_session": self.decision_session,
            "available_at": self.available_at,
            "source_evidence_sha256": self.source_evidence_sha256,
            "values": values,
        }


@dataclasses.dataclass(frozen=True)
class TransformedControlRow:
    security_id: str
    industry_id: str
    raw_state: StockRawState
    pdf_reliable_score: Decimal
    values: tuple[Decimal, ...]

    def __post_init__(self) -> None:
        require_identifier(self.security_id, "security_id")
        require_identifier(self.industry_id, "industry_id")
        if not isinstance(self.raw_state, StockRawState):
            raise StockControlError("raw_state must be typed")
        if (
            type(self.pdf_reliable_score) is not Decimal
            or not self.pdf_reliable_score.is_finite()
        ):
            raise StockControlError("pdf_reliable_score must be an exact finite Decimal")
        if type(self.values) is not tuple or len(self.values) != len(CONTROL_COLUMNS):
            raise StockControlError("transformed control vector has the wrong width")
        for index, value in enumerate(self.values):
            if type(value) is not Decimal or not value.is_finite():
                raise StockControlError(
                    f"transformed control {index} must be an exact finite Decimal"
                )

    def to_record(self) -> dict[str, Any]:
        return {
            "security_id": self.security_id,
            "industry_id": self.industry_id,
            "raw_state": self.raw_state.value,
            "pdf_reliable_score": _decimal_text(self.pdf_reliable_score),
            "values": [_decimal_text(value) for value in self.values],
        }


@dataclasses.dataclass(frozen=True)
class ControlRowRefusal:
    decision_session: str
    security_id: str
    reason: str
    source_evidence_sha256: str | None

    def __post_init__(self) -> None:
        parse_date(self.decision_session, "refusal decision_session")
        require_identifier(self.security_id, "refusal security_id")
        if self.reason not in _PREOPEN_REFUSAL_REASONS:
            raise StockControlError("pre-open control refusal reason is not frozen")
        if self.source_evidence_sha256 is not None:
            require_sha256(
                self.source_evidence_sha256,
                "refusal source_evidence_sha256",
            )

    def to_record(self) -> dict[str, Any]:
        return {
            "decision_session": self.decision_session,
            "security_id": self.security_id,
            "reason": self.reason,
            "source_evidence_sha256": self.source_evidence_sha256,
        }


@dataclasses.dataclass(frozen=True)
class PreopenControlCrossSection:
    decision_session: str
    decision_at: str
    candidate_sha256: str
    candidate_policy_sha256: str
    evidence_sha256: str
    eligible_census_count: int
    accepted_control_count: int
    rows: tuple[TransformedControlRow, ...]
    refusals: tuple[ControlRowRefusal, ...]

    def __post_init__(self) -> None:
        parse_date(self.decision_session, "decision_session")
        parse_utc_timestamp(self.decision_at, "decision_at")
        require_sha256(self.candidate_sha256, "candidate_sha256")
        require_sha256(self.candidate_policy_sha256, "candidate_policy_sha256")
        require_sha256(self.evidence_sha256, "evidence_sha256")
        if (
            type(self.eligible_census_count) is not int
            or self.eligible_census_count <= 0
            or type(self.accepted_control_count) is not int
            or self.accepted_control_count < 0
        ):
            raise StockControlError("cross-section coverage counts are invalid")
        if type(self.rows) is not tuple or any(
            type(item) is not TransformedControlRow for item in self.rows
        ):
            raise StockControlError("cross-section rows must be an exact typed tuple")
        for item in self.rows:
            item.__post_init__()
        if self.rows != tuple(sorted(self.rows, key=lambda item: item.security_id)):
            raise StockControlError("cross-section rows must be unique and sorted")
        if len({item.security_id for item in self.rows}) != len(self.rows):
            raise StockControlError("cross-section security IDs must be unique")
        if type(self.refusals) is not tuple or any(
            type(item) is not ControlRowRefusal for item in self.refusals
        ):
            raise StockControlError("cross-section refusals must be an exact typed tuple")
        for item in self.refusals:
            item.__post_init__()
        if self.refusals != tuple(sorted(self.refusals, key=lambda item: item.security_id)):
            raise StockControlError("cross-section refusals must be unique and sorted")
        if any(item.decision_session != self.decision_session for item in self.refusals):
            raise StockControlError("cross-section refusal escaped its decision session")
        accepted_ids = {item.security_id for item in self.rows}
        refusal_ids = {item.security_id for item in self.refusals}
        if len(refusal_ids) != len(self.refusals) or accepted_ids & refusal_ids:
            raise StockControlError("cross-section coverage identities overlap or repeat")
        if (
            self.accepted_control_count != len(self.rows)
            or self.eligible_census_count != len(self.rows) + len(self.refusals)
            or self.accepted_control_count < _MINIMUM_ACCEPTED_ROWS
            or self.accepted_control_count * _COVERAGE_DENOMINATOR
            < self.eligible_census_count * _COVERAGE_NUMERATOR
        ):
            raise StockControlError("cross-section accepted-control coverage is underfilled")

    @property
    def cross_section_sha256(self) -> str:
        record = {
            "decision_session": self.decision_session,
            "decision_at": self.decision_at,
            "candidate_sha256": self.candidate_sha256,
            "candidate_policy_sha256": self.candidate_policy_sha256,
            "evidence_sha256": self.evidence_sha256,
            "eligible_census_count": self.eligible_census_count,
            "accepted_control_count": self.accepted_control_count,
            "rows": [row.to_record() for row in self.rows],
            "refusals": [item.to_record() for item in self.refusals],
        }
        return sha256_bytes(canonical_json_bytes(record))


def require_preopen_control_cross_section(
    value: PreopenControlCrossSection,
) -> PreopenControlCrossSection:
    """Recompute coverage and every nested row invariant before consumption."""
    if type(value) is not PreopenControlCrossSection:
        raise StockControlError("cross-section must use the exact structural type")
    value.__post_init__()
    return value


@dataclasses.dataclass(frozen=True)
class StructuralFoldBoundary:
    """Fixture-only half-open fold boundary; never a production manifest."""

    fold_id: str
    structural_fold_sha256: str
    horizon_sessions: int
    purge_sessions: int
    embargo_sessions: int
    train_start: str
    train_end_exclusive: str
    validation_start: str
    validation_end_exclusive: str
    test_start: str
    test_end_exclusive: str

    def __post_init__(self) -> None:
        require_identifier(self.fold_id, "fold_id")
        require_sha256(self.structural_fold_sha256, "structural_fold_sha256")
        if (
            type(self.horizon_sessions) is not int
            or type(self.purge_sessions) is not int
            or type(self.embargo_sessions) is not int
            or self.horizon_sessions not in (1, 5, 20, 60)
            or self.purge_sessions != self.horizon_sessions
            or self.embargo_sessions != self.horizon_sessions
        ):
            raise StockControlError("structural fold purge/embargo must equal the horizon")
        names = (
            "train_start",
            "train_end_exclusive",
            "validation_start",
            "validation_end_exclusive",
            "test_start",
            "test_end_exclusive",
        )
        values = tuple(getattr(self, name) for name in names)
        for name, value in zip(names, values, strict=True):
            parse_date(value, name)
            try:
                valid = is_trading_session(value)
            except ExchangeCalendarError as exc:
                raise StockControlError(f"{name} cannot be calendar-resolved") from exc
            if not valid:
                raise StockControlError(f"{name} must be an NYSE session boundary")
        if not (
            self.train_start < self.train_end_exclusive
            <= self.validation_start
            < self.validation_end_exclusive
            <= self.test_start
            < self.test_end_exclusive
        ):
            raise StockControlError("structural fold intervals overlap or reverse")
        try:
            expected_validation_start = resolve_nth_session_after(
                self.train_end_exclusive,
                self.purge_sessions,
            )
            expected_test_start = resolve_nth_session_after(
                self.validation_end_exclusive,
                self.embargo_sessions,
            )
        except ExchangeCalendarError as exc:
            raise StockControlError("structural fold gaps cannot be calendar-resolved") from exc
        if (
            self.validation_start != expected_validation_start
            or self.test_start != expected_test_start
        ):
            raise StockControlError("structural fold purge/embargo gap is not exact")
        if self.structural_fold_sha256 != self.derived_sha256:
            raise StockControlError("structural fold identity is not content-derived")

    def to_record(self) -> dict[str, object]:
        return {
            "fold_id": self.fold_id,
            "horizon_sessions": self.horizon_sessions,
            "purge_sessions": self.purge_sessions,
            "embargo_sessions": self.embargo_sessions,
            "train_start": self.train_start,
            "train_end_exclusive": self.train_end_exclusive,
            "validation_start": self.validation_start,
            "validation_end_exclusive": self.validation_end_exclusive,
            "test_start": self.test_start,
            "test_end_exclusive": self.test_end_exclusive,
        }

    @property
    def derived_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_record()))

    @classmethod
    def create(
        cls,
        *,
        fold_id: str,
        horizon_sessions: int,
        purge_sessions: int,
        embargo_sessions: int,
        train_start: str,
        train_end_exclusive: str,
        validation_start: str,
        validation_end_exclusive: str,
        test_start: str,
        test_end_exclusive: str,
    ) -> "StructuralFoldBoundary":
        fields: dict[str, object] = {
            "fold_id": fold_id,
            "horizon_sessions": horizon_sessions,
            "purge_sessions": purge_sessions,
            "embargo_sessions": embargo_sessions,
            "train_start": train_start,
            "train_end_exclusive": train_end_exclusive,
            "validation_start": validation_start,
            "validation_end_exclusive": validation_end_exclusive,
            "test_start": test_start,
            "test_end_exclusive": test_end_exclusive,
        }
        digest = sha256_bytes(canonical_json_bytes(fields))
        return cls(structural_fold_sha256=digest, **fields)

    def interval(self, partition: str) -> tuple[str, str]:
        if partition == "train":
            return self.train_start, self.train_end_exclusive
        if partition == "validation":
            return self.validation_start, self.validation_end_exclusive
        if partition == "test":
            return self.test_start, self.test_end_exclusive
        raise StockControlError("partition must be train, validation, or test")

    @property
    def production_fold_authority_available(self) -> bool:
        return False


def require_structural_fold_boundary(
    fold: StructuralFoldBoundary,
) -> StructuralFoldBoundary:
    """Recompute the fixture fold identity and calendar gaps before use."""
    if type(fold) is not StructuralFoldBoundary:
        raise StockControlError("fold boundary must use the exact structural type")
    fold.__post_init__()
    return fold


def build_preopen_control_cross_section(
    contract: StockEvaluationContract,
    candidate: StructuralStockScoreCandidate,
    evidence_rows: tuple[PreopenControlEvidenceRow, ...],
) -> PreopenControlCrossSection:
    """Transform one complete same-date census without fitting coefficients."""
    _require_contract(contract)
    if type(candidate) is not StructuralStockScoreCandidate:
        raise StockControlError("control transformation requires a structural candidate")
    try:
        candidate.__post_init__()
        for score in candidate.scores:
            score.__post_init__()
    except StockSignalError as exc:
        raise StockControlError("structural stock candidate failed reauthentication") from exc
    if not candidate.pdf_formula_available or candidate.final_executable_available:
        raise StockControlError("stock candidate is refusing or falsely executable")
    score_ids = tuple(item.security_id for item in candidate.scores)
    if score_ids != candidate.universe_security_ids:
        raise StockControlError("candidate scores must cover the complete eligible universe")
    if any(
        item.raw_state is StockRawState.STRUCTURAL_ZERO
        and item.pdf_reliable_score != 0
        for item in candidate.scores
    ):
        raise StockControlError("structural-zero source scores must remain exact zero")
    if type(evidence_rows) is not tuple or any(
        type(item) is not PreopenControlEvidenceRow for item in evidence_rows
    ):
        raise StockControlError("control evidence must be an exact typed tuple")
    for item in evidence_rows:
        item.__post_init__()
    if evidence_rows != tuple(sorted(evidence_rows, key=lambda item: item.security_id)):
        raise StockControlError("control evidence rows must be unique and sorted")
    if len({item.security_id for item in evidence_rows}) != len(evidence_rows):
        raise StockControlError("control evidence security IDs must be unique")
    expected_ids = score_ids
    expected_id_set = set(expected_ids)
    evidence_ids = tuple(item.security_id for item in evidence_rows)
    unknown_ids = set(evidence_ids) - expected_id_set
    if unknown_ids:
        raise StockControlError("control evidence contains a security outside the candidate census")
    decision_at = parse_utc_timestamp(candidate.decision_at, "decision_at")
    try:
        expected_open = session_open_instant(candidate.decision_session)
    except ExchangeCalendarError as exc:
        raise StockControlError("candidate decision session has no NYSE open") from exc
    if decision_at != expected_open:
        raise StockControlError("candidate decision instant must equal the NYSE open")
    evidence_by_id = {item.security_id: item for item in evidence_rows}
    accepted_evidence: list[PreopenControlEvidenceRow] = []
    refusals: list[ControlRowRefusal] = []
    for security_id in expected_ids:
        item = evidence_by_id.get(security_id)
        if item is None:
            refusals.append(
                ControlRowRefusal(
                    decision_session=candidate.decision_session,
                    security_id=security_id,
                    reason="missing_control_evidence",
                    source_evidence_sha256=None,
                )
            )
            continue
        reason: str | None = None
        if item.decision_session != candidate.decision_session:
            reason = "wrong_decision_session"
        elif parse_utc_timestamp(item.available_at, "available_at") >= decision_at:
            reason = "not_available_strictly_before_open"
        if reason is not None:
            refusals.append(
                ControlRowRefusal(
                    decision_session=candidate.decision_session,
                    security_id=security_id,
                    reason=reason,
                    source_evidence_sha256=item.source_evidence_sha256,
                )
            )
        else:
            accepted_evidence.append(item)
    eligible_count = len(expected_ids)
    accepted_count = len(accepted_evidence)
    if (
        accepted_count < _MINIMUM_ACCEPTED_ROWS
        or accepted_count * _COVERAGE_DENOMINATOR
        < eligible_count * _COVERAGE_NUMERATOR
    ):
        raise StockControlError("pre-open control coverage is underfilled")
    value_maps: dict[str, dict[str, Decimal]] = {}
    for item in accepted_evidence:
        value_maps[item.security_id] = item.value_map()

    medians: dict[str, Decimal] = {}
    scales: dict[str, Decimal] = {}
    with localcontext(_frozen_decimal_context()):
        for name in CONTINUOUS_COLUMNS:
            median = _median(values[name] for values in value_maps.values())
            deviations = tuple(
                abs(values[name] - median) for values in value_maps.values()
            )
            mad = _median(deviations)
            if mad == 0:
                raise StockControlError(f"control {name} has zero same-date MAD")
            medians[name] = median
            scales[name] = mad * _MAD_SCALE

    score_by_id = {item.security_id: item for item in candidate.scores}
    transformed: list[TransformedControlRow] = []
    with localcontext(_frozen_decimal_context()):
        for evidence in accepted_evidence:
            values = value_maps[evidence.security_id]
            vector = tuple(
                (values[name] - medians[name]) / scales[name]
                for name in CONTINUOUS_COLUMNS
            ) + tuple(values[name] for name in BINARY_COLUMNS)
            score = score_by_id[evidence.security_id]
            transformed.append(
                TransformedControlRow(
                    security_id=evidence.security_id,
                    industry_id=evidence.industry_id,
                    raw_state=score.raw_state,
                    pdf_reliable_score=score.pdf_reliable_score,
                    values=vector,
                )
            )
    evidence_hash = sha256_bytes(
        canonical_json_bytes([item.to_record() for item in evidence_rows])
    )
    return PreopenControlCrossSection(
        decision_session=candidate.decision_session,
        decision_at=candidate.decision_at,
        candidate_sha256=candidate.candidate_sha256,
        candidate_policy_sha256=candidate.policy_sha256,
        evidence_sha256=evidence_hash,
        eligible_census_count=eligible_count,
        accepted_control_count=accepted_count,
        rows=tuple(transformed),
        refusals=tuple(refusals),
    )


def _solve_ols(
    design: tuple[tuple[Decimal, ...], ...],
    response: tuple[Decimal, ...],
) -> tuple[Decimal, ...]:
    width = len(design[0])
    with localcontext(_frozen_decimal_context()) as context:
        row_count = len(design)
        q_columns: list[list[Decimal]] = []
        upper = [
            [Decimal(0) for _ in range(width)]
            for _ in range(width)
        ]
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
            residual_norm_squared = sum(
                (value * value for value in vector),
                Decimal(0),
            )
            original_norm_squared = sum(
                (value * value for value in original),
                Decimal(0),
            )
            relative_floor = (
                _RANK_RELATIVE_THRESHOLD
                * _RANK_RELATIVE_THRESHOLD
                * max(Decimal(1), original_norm_squared)
            )
            if residual_norm_squared <= relative_floor:
                raise StockControlError("training control design is rank deficient")
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


def _model_payload(
    *,
    spec_hash: str,
    fold_id: str,
    structural_fold_sha256: str,
    candidate_policy_sha256: str,
    train_interval: tuple[str, str],
    training_cross_section_hashes: tuple[str, ...],
    training_sessions: tuple[str, ...],
    columns: tuple[str, ...],
    industry_levels: tuple[str, ...],
    reference_industry: str,
    coefficients: tuple[Decimal, ...],
    active_training_rows: int,
) -> dict[str, Any]:
    return {
        "schema": STRUCTURAL_CONTROL_MODEL_SCHEMA,
        "authority": STRUCTURAL_CONTROL_AUTHORITY,
        "model_id": None,
        "model_hash": None,
        "spec_hash": spec_hash,
        "fold_id": fold_id,
        "structural_fold_sha256": structural_fold_sha256,
        "candidate_policy_sha256": candidate_policy_sha256,
        "train_interval": list(train_interval),
        "training_cross_section_hashes": list(training_cross_section_hashes),
        "training_sessions": list(training_sessions),
        "columns": list(columns),
        "industry_levels": list(industry_levels),
        "reference_industry": reference_industry,
        "coefficients": [_decimal_text(value) for value in coefficients],
        "active_training_rows": active_training_rows,
    }


@dataclasses.dataclass(frozen=True)
class StructuralStockControlModel:
    schema: str
    authority: str
    model_id: str
    model_hash: str
    spec_hash: str
    fold_id: str
    structural_fold_sha256: str
    candidate_policy_sha256: str
    train_interval: tuple[str, str]
    training_cross_section_hashes: tuple[str, ...]
    training_sessions: tuple[str, ...]
    columns: tuple[str, ...]
    industry_levels: tuple[str, ...]
    reference_industry: str
    coefficients: tuple[Decimal, ...]
    active_training_rows: int

    def __post_init__(self) -> None:
        if self.schema != STRUCTURAL_CONTROL_MODEL_SCHEMA or self.authority != STRUCTURAL_CONTROL_AUTHORITY:
            raise StockControlError("control model authority or schema changed")
        require_sha256(self.spec_hash, "spec_hash")
        require_sha256(self.model_hash, "model_hash")
        require_identifier(self.fold_id, "fold_id")
        require_sha256(self.structural_fold_sha256, "structural_fold_sha256")
        require_sha256(self.candidate_policy_sha256, "candidate_policy_sha256")
        if type(self.train_interval) is not tuple or len(self.train_interval) != 2:
            raise StockControlError("model train interval must be a half-open pair")
        if not self.train_interval[0] < self.train_interval[1]:
            raise StockControlError("model train interval is reversed")
        for boundary in self.train_interval:
            parse_date(boundary, "model train boundary")
            try:
                valid_boundary = is_trading_session(boundary)
            except ExchangeCalendarError as exc:
                raise StockControlError("model train boundary cannot be resolved") from exc
            if not valid_boundary:
                raise StockControlError("model train boundary must be an NYSE session")
        if type(self.training_sessions) is not tuple or self.training_sessions != tuple(
            sorted(set(self.training_sessions))
        ):
            raise StockControlError("training sessions must be unique and sorted")
        for session in self.training_sessions:
            parse_date(session, "training session")
            try:
                valid_session = is_trading_session(session)
            except ExchangeCalendarError as exc:
                raise StockControlError("training session cannot be resolved") from exc
            if not valid_session:
                raise StockControlError("training session must be an NYSE session")
            if not self.train_interval[0] <= session < self.train_interval[1]:
                raise StockControlError("model training session escaped train interval")
        if type(self.training_cross_section_hashes) is not tuple or len(
            self.training_cross_section_hashes
        ) != len(self.training_sessions):
            raise StockControlError("training hash/session counts differ")
        for value in self.training_cross_section_hashes:
            require_sha256(value, "training cross-section hash")
        if type(self.industry_levels) is not tuple or not self.industry_levels or self.industry_levels != tuple(sorted(set(self.industry_levels))):
            raise StockControlError("training industry levels must be unique and sorted")
        if self.reference_industry != self.industry_levels[0]:
            raise StockControlError("reference industry must be lexicographically first")
        expected_columns = (
            "intercept",
            *CONTROL_COLUMNS,
            *(f"industry::{value}" for value in self.industry_levels[1:]),
        )
        if type(self.columns) is not tuple or self.columns != expected_columns:
            raise StockControlError("control model columns changed")
        if type(self.coefficients) is not tuple or len(self.coefficients) != len(self.columns):
            raise StockControlError("control model columns changed")
        for value in self.coefficients:
            if type(value) is not Decimal or not value.is_finite():
                raise StockControlError("coefficients must be exact finite Decimals")
        if type(self.active_training_rows) is not int or self.active_training_rows <= len(self.columns) + 20:
            raise StockControlError("control model violates the training row floor")
        payload = _model_payload(
            spec_hash=self.spec_hash,
            fold_id=self.fold_id,
            structural_fold_sha256=self.structural_fold_sha256,
            candidate_policy_sha256=self.candidate_policy_sha256,
            train_interval=self.train_interval,
            training_cross_section_hashes=self.training_cross_section_hashes,
            training_sessions=self.training_sessions,
            columns=self.columns,
            industry_levels=self.industry_levels,
            reference_industry=self.reference_industry,
            coefficients=self.coefficients,
            active_training_rows=self.active_training_rows,
        )
        digest = sha256_bytes(canonical_json_bytes(payload))
        if self.model_hash != digest or self.model_id != f"arv2-stock-control-{digest[:16]}":
            raise StockControlError("control model identity is not content-derived")

    @property
    def final_executable_available(self) -> bool:
        return False


def require_structural_stock_control_model(
    model: StructuralStockControlModel,
) -> StructuralStockControlModel:
    """Recompute every model invariant before coefficients can be consumed."""
    if type(model) is not StructuralStockControlModel:
        raise StockControlError("control model must use the exact structural type")
    model.__post_init__()
    return model


def fit_structural_stock_control_model(
    contract: StockEvaluationContract,
    fold: StructuralFoldBoundary,
    training_cross_sections: tuple[PreopenControlCrossSection, ...],
) -> StructuralStockControlModel:
    """Fit one deterministic pooled OLS using active training rows only."""
    _require_contract(contract)
    require_structural_fold_boundary(fold)
    if fold.production_fold_authority_available:
        raise StockControlError("fit requires an exact fixture-only fold boundary")
    if type(training_cross_sections) is not tuple or not training_cross_sections or any(
        type(item) is not PreopenControlCrossSection for item in training_cross_sections
    ):
        raise StockControlError("training cross-sections must be a nonempty typed tuple")
    for item in training_cross_sections:
        require_preopen_control_cross_section(item)
    sessions = tuple(item.decision_session for item in training_cross_sections)
    if sessions != tuple(sorted(set(sessions))):
        raise StockControlError("training cross-sections must be unique and chronological")
    policies = {item.candidate_policy_sha256 for item in training_cross_sections}
    if len(policies) != 1:
        raise StockControlError("training cross-sections must share one candidate policy")
    candidate_policy_sha256 = next(iter(policies))
    train_start, train_end = fold.interval("train")
    if any(not train_start <= session < train_end for session in sessions):
        raise StockControlError("training cross-section escaped the half-open train interval")
    active = tuple(
        row
        for cross_section in training_cross_sections
        for row in cross_section.rows
        if row.raw_state is StockRawState.ACTIVE
    )
    industry_levels = tuple(sorted({row.industry_id for row in active}))
    if not industry_levels:
        raise StockControlError("training fit has no active industry levels")
    reference = industry_levels[0]
    columns = (
        "intercept",
        *CONTROL_COLUMNS,
        *(f"industry::{value}" for value in industry_levels[1:]),
    )
    if len(active) <= len(columns) + 20:
        raise StockControlError("training fit has too few active rows")
    design = tuple(
        (
            Decimal(1),
            *row.values,
            *(
                Decimal(1) if row.industry_id == value else Decimal(0)
                for value in industry_levels[1:]
            ),
        )
        for row in active
    )
    response = tuple(row.pdf_reliable_score for row in active)
    coefficients = _solve_ols(design, response)
    hashes = tuple(item.cross_section_sha256 for item in training_cross_sections)
    payload = _model_payload(
        spec_hash=contract.spec_hash,
        fold_id=fold.fold_id,
        structural_fold_sha256=fold.structural_fold_sha256,
        candidate_policy_sha256=candidate_policy_sha256,
        train_interval=(train_start, train_end),
        training_cross_section_hashes=hashes,
        training_sessions=sessions,
        columns=columns,
        industry_levels=industry_levels,
        reference_industry=reference,
        coefficients=coefficients,
        active_training_rows=len(active),
    )
    digest = sha256_bytes(canonical_json_bytes(payload))
    return StructuralStockControlModel(
        schema=STRUCTURAL_CONTROL_MODEL_SCHEMA,
        authority=STRUCTURAL_CONTROL_AUTHORITY,
        model_id=f"arv2-stock-control-{digest[:16]}",
        model_hash=digest,
        spec_hash=contract.spec_hash,
        fold_id=fold.fold_id,
        structural_fold_sha256=fold.structural_fold_sha256,
        candidate_policy_sha256=candidate_policy_sha256,
        train_interval=(train_start, train_end),
        training_cross_section_hashes=hashes,
        training_sessions=sessions,
        columns=columns,
        industry_levels=industry_levels,
        reference_industry=reference,
        coefficients=coefficients,
        active_training_rows=len(active),
    )


@dataclasses.dataclass(frozen=True)
class ControlAdjustedStockRow:
    decision_session: str
    security_id: str
    raw_state: StockRawState
    adjusted_score: Decimal

    def __post_init__(self) -> None:
        parse_date(self.decision_session, "decision_session")
        require_identifier(self.security_id, "security_id")
        if not isinstance(self.raw_state, StockRawState):
            raise StockControlError("adjusted row raw state must be typed")
        if type(self.adjusted_score) is not Decimal or not self.adjusted_score.is_finite():
            raise StockControlError("adjusted_score must be an exact finite Decimal")
        if self.raw_state is StockRawState.STRUCTURAL_ZERO and self.adjusted_score != 0:
            raise StockControlError("structural zero did not remain exact zero")
        if self.raw_state is StockRawState.ACTIVE and not _CLIP_LOW <= self.adjusted_score <= _CLIP_HIGH:
            raise StockControlError("active adjusted score escaped the frozen clip")

    def to_record(self) -> dict[str, Any]:
        return {
            "decision_session": self.decision_session,
            "security_id": self.security_id,
            "raw_state": self.raw_state.value,
            "adjusted_score": _decimal_text(self.adjusted_score),
        }


@dataclasses.dataclass(frozen=True)
class ControlApplicationRefusal:
    decision_session: str
    security_id: str
    reason: str

    def __post_init__(self) -> None:
        parse_date(self.decision_session, "application refusal decision_session")
        require_identifier(self.security_id, "application refusal security_id")
        if self.reason not in _APPLICATION_REFUSAL_REASONS:
            raise StockControlError("application refusal reason is not frozen")

    def to_record(self) -> dict[str, str]:
        return {
            "decision_session": self.decision_session,
            "security_id": self.security_id,
            "reason": self.reason,
        }


@dataclasses.dataclass(frozen=True)
class StructuralControlAdjustedBatch:
    schema: str
    authority: str
    spec_hash: str
    model_hash: str
    fold_id: str
    structural_fold_sha256: str
    partition: str
    partition_interval: tuple[str, str]
    input_cross_section_hashes: tuple[str, ...]
    eligible_input_rows: int
    adjusted_row_count: int
    rows: tuple[ControlAdjustedStockRow, ...]
    refusals: tuple[ControlApplicationRefusal, ...]

    def __post_init__(self) -> None:
        if (
            self.schema != STRUCTURAL_CONTROL_BATCH_SCHEMA
            or self.authority != STRUCTURAL_CONTROL_AUTHORITY
        ):
            raise StockControlError("adjusted batch schema or authority changed")
        require_sha256(self.spec_hash, "spec_hash")
        require_sha256(self.model_hash, "model_hash")
        require_identifier(self.fold_id, "fold_id")
        require_sha256(self.structural_fold_sha256, "structural_fold_sha256")
        if self.partition not in ("validation", "test"):
            raise StockControlError("adjusted batch partition is invalid")
        if (
            type(self.partition_interval) is not tuple
            or len(self.partition_interval) != 2
            or not self.partition_interval[0] < self.partition_interval[1]
        ):
            raise StockControlError("adjusted batch partition interval is invalid")
        for boundary in self.partition_interval:
            parse_date(boundary, "adjusted batch partition boundary")
            try:
                valid_boundary = is_trading_session(boundary)
            except ExchangeCalendarError as exc:
                raise StockControlError(
                    "adjusted batch partition boundary cannot be resolved"
                ) from exc
            if not valid_boundary:
                raise StockControlError(
                    "adjusted batch partition boundary must be an NYSE session"
                )
        if type(self.input_cross_section_hashes) is not tuple or not self.input_cross_section_hashes:
            raise StockControlError("adjusted batch requires input cross-section hashes")
        for value in self.input_cross_section_hashes:
            require_sha256(value, "input cross-section hash")
        if len(set(self.input_cross_section_hashes)) != len(
            self.input_cross_section_hashes
        ):
            raise StockControlError("adjusted batch input hashes must be unique")
        if type(self.rows) is not tuple or any(
            type(item) is not ControlAdjustedStockRow for item in self.rows
        ):
            raise StockControlError("adjusted batch rows must be an exact typed tuple")
        for item in self.rows:
            item.__post_init__()
        if self.rows != tuple(
            sorted(self.rows, key=lambda item: (item.decision_session, item.security_id))
        ):
            raise StockControlError("adjusted batch rows must be canonical-sorted")
        row_keys = tuple((item.decision_session, item.security_id) for item in self.rows)
        if len(set(row_keys)) != len(row_keys):
            raise StockControlError("adjusted batch row identities must be unique")
        if type(self.refusals) is not tuple or any(
            type(item) is not ControlApplicationRefusal for item in self.refusals
        ):
            raise StockControlError("adjusted batch refusals must be an exact typed tuple")
        for item in self.refusals:
            item.__post_init__()
        if self.refusals != tuple(
            sorted(self.refusals, key=lambda item: (item.decision_session, item.security_id))
        ):
            raise StockControlError("adjusted batch refusals must be canonical-sorted")
        refusal_keys = tuple(
            (item.decision_session, item.security_id) for item in self.refusals
        )
        if len(set(refusal_keys)) != len(refusal_keys) or set(row_keys) & set(refusal_keys):
            raise StockControlError("adjusted batch coverage identities overlap or repeat")
        if (
            type(self.eligible_input_rows) is not int
            or type(self.adjusted_row_count) is not int
            or self.eligible_input_rows <= 0
            or self.adjusted_row_count != len(self.rows)
            or self.eligible_input_rows != len(self.rows) + len(self.refusals)
        ):
            raise StockControlError("adjusted batch coverage counts are invalid")
        represented_sessions = {
            item.decision_session for item in (*self.rows, *self.refusals)
        }
        if len(self.input_cross_section_hashes) != len(represented_sessions):
            raise StockControlError("adjusted batch hash/session lineage counts differ")
        start, end = self.partition_interval
        if any(
            not start <= item.decision_session < end
            for item in (*self.rows, *self.refusals)
        ):
            raise StockControlError("adjusted batch row escaped its partition interval")

    @property
    def batch_sha256(self) -> str:
        record = {
            "schema": self.schema,
            "authority": self.authority,
            "spec_hash": self.spec_hash,
            "model_hash": self.model_hash,
            "fold_id": self.fold_id,
            "structural_fold_sha256": self.structural_fold_sha256,
            "partition": self.partition,
            "partition_interval": list(self.partition_interval),
            "input_cross_section_hashes": list(self.input_cross_section_hashes),
            "eligible_input_rows": self.eligible_input_rows,
            "adjusted_row_count": self.adjusted_row_count,
            "rows": [row.to_record() for row in self.rows],
            "refusals": [item.to_record() for item in self.refusals],
        }
        return sha256_bytes(canonical_json_bytes(record))

    @property
    def final_executable_available(self) -> bool:
        return False


def apply_structural_stock_control_model(
    contract: StockEvaluationContract,
    model: StructuralStockControlModel,
    fold: StructuralFoldBoundary,
    partition: str,
    cross_sections: tuple[PreopenControlCrossSection, ...],
) -> StructuralControlAdjustedBatch:
    """Apply the frozen training model unchanged to validation/test rows."""
    _require_contract(contract)
    require_structural_stock_control_model(model)
    require_structural_fold_boundary(fold)
    if model.spec_hash != contract.spec_hash:
        raise StockControlError("control model does not bind the loaded contract")
    if (
        fold.fold_id != model.fold_id
        or fold.structural_fold_sha256 != model.structural_fold_sha256
        or fold.interval("train") != model.train_interval
    ):
        raise StockControlError("application fold does not bind the training model")
    if partition not in ("validation", "test"):
        raise StockControlError("frozen model may apply only to validation or test")
    if model.final_executable_available:
        raise StockControlError("control model acquired executable authority")
    if type(cross_sections) is not tuple or not cross_sections or any(
        type(item) is not PreopenControlCrossSection for item in cross_sections
    ):
        raise StockControlError("application cross-sections must be a typed tuple")
    for item in cross_sections:
        require_preopen_control_cross_section(item)
    sessions = tuple(item.decision_session for item in cross_sections)
    if sessions != tuple(sorted(set(sessions))):
        raise StockControlError("application cross-sections must be unique and chronological")
    if any(
        item.candidate_policy_sha256 != model.candidate_policy_sha256
        for item in cross_sections
    ):
        raise StockControlError("application candidate policy differs from training")
    partition_start, partition_end = fold.interval(partition)
    if any(not partition_start <= session < partition_end for session in sessions):
        raise StockControlError("application cross-section escaped its half-open partition")
    coefficient_by_column = dict(zip(model.columns, model.coefficients, strict=True))
    adjusted: list[ControlAdjustedStockRow] = []
    refusals: list[ControlApplicationRefusal] = []
    with localcontext(_frozen_decimal_context()):
        for cross_section in cross_sections:
            adjusted_before = len(adjusted)
            refusals_before = len(refusals)
            refusals.extend(
                ControlApplicationRefusal(
                    decision_session=item.decision_session,
                    security_id=item.security_id,
                    reason=f"preopen_control::{item.reason}",
                )
                for item in cross_section.refusals
            )
            for row in cross_section.rows:
                if row.raw_state is StockRawState.STRUCTURAL_ZERO:
                    value = Decimal(0)
                elif row.industry_id not in model.industry_levels:
                    refusals.append(
                        ControlApplicationRefusal(
                            decision_session=cross_section.decision_session,
                            security_id=row.security_id,
                            reason="unseen_training_industry",
                        )
                    )
                    continue
                else:
                    prediction = coefficient_by_column["intercept"]
                    for name, control_value in zip(CONTROL_COLUMNS, row.values, strict=True):
                        prediction += coefficient_by_column[name] * control_value
                    if row.industry_id != model.reference_industry:
                        prediction += coefficient_by_column[f"industry::{row.industry_id}"]
                    value = row.pdf_reliable_score - prediction
                    value = max(_CLIP_LOW, min(_CLIP_HIGH, value))
                adjusted.append(
                    ControlAdjustedStockRow(
                        decision_session=cross_section.decision_session,
                        security_id=row.security_id,
                        raw_state=row.raw_state,
                        adjusted_score=value,
                    )
                )
            accepted_on_date = len(adjusted) - adjusted_before
            refused_on_date = len(refusals) - refusals_before
            if (
                accepted_on_date + refused_on_date
                != cross_section.eligible_census_count
                or accepted_on_date < _MINIMUM_ACCEPTED_ROWS
                or accepted_on_date * _COVERAGE_DENOMINATOR
                < cross_section.eligible_census_count * _COVERAGE_NUMERATOR
            ):
                raise StockControlError(
                    "application date coverage is underfilled after named refusals"
                )
    return StructuralControlAdjustedBatch(
        schema=STRUCTURAL_CONTROL_BATCH_SCHEMA,
        authority=STRUCTURAL_CONTROL_AUTHORITY,
        spec_hash=contract.spec_hash,
        model_hash=model.model_hash,
        fold_id=fold.fold_id,
        structural_fold_sha256=fold.structural_fold_sha256,
        partition=partition,
        partition_interval=(partition_start, partition_end),
        input_cross_section_hashes=tuple(
            item.cross_section_sha256 for item in cross_sections
        ),
        eligible_input_rows=sum(
            item.eligible_census_count for item in cross_sections
        ),
        adjusted_row_count=len(adjusted),
        rows=tuple(adjusted),
        refusals=tuple(
            sorted(
                refusals,
                key=lambda item: (item.decision_session, item.security_id),
            )
        ),
    )
