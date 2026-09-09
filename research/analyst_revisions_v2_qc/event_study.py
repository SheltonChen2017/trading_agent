"""Deterministic synthetic stock event-study outcome kernel.

This is QC-facing arithmetic, not a cloud adapter. It accepts only exact
synthetic fixtures that are bound to a :class:`SyntheticQcRunCandidate` and
emits one observation or one named refusal for every decision/horizon pair.
The kernel has no file, network, provider, QuantConnect, result-publication,
order, or trading surface. Its run-candidate hash identifies a caller-declared
synthetic manifest; it is explicitly not proof of loaded code or a QC compile.

Production transport and the LEAN ``QCAlgorithm`` adapter remain a later
reviewed milestone because the real source/right/terminal-payoff, numeric
power, reviewed-run, and one-shot evaluation bindings are not present yet.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import Counter
from datetime import date
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from functools import lru_cache
from types import MappingProxyType
from typing import Mapping

from data.exchange_calendar import ExchangeCalendarError, trading_sessions

from .run_contract import (
    HORIZONS,
    PARTITION_SCHEMAS,
    QcRunContractError,
    SyntheticPartitionBinding,
    SyntheticQcRunCandidate,
    require_synthetic_qc_run_candidate,
)


class EventStudyInputError(ValueError):
    """Synthetic event-study input is malformed, ambiguous, or noncanonical."""


REVIEWED_AXIS_START = date(2013, 1, 2)
REVIEWED_AXIS_END = date(2026, 8, 28)
REVIEWED_AXIS_SESSION_COUNT = 3435
REVIEWED_AXIS_SHA256 = (
    "b303555af32bda7d3f2caf6c43f3ae1c43723613086ab3dc848cfb86ab88d732"
)
SYNTHETIC_OPEN_SOURCE = "synthetic_qc_total_return_open"
SYNTHETIC_TERMINAL_SOURCE = "synthetic_total_shareholder_payoff"
SYNTHETIC_LIFECYCLE_SOURCE = "synthetic_complete_security_lifecycle_inventory"
SYNTHETIC_TOTAL_RETURN_VALUE_BASIS = (
    "synthetic_split_distribution_adjusted_total_return_index_same_vintage"
)
SYNTHETIC_TERMINAL_VALUE_BASIS = SYNTHETIC_TOTAL_RETURN_VALUE_BASIS
BENCHMARK_SECURITY_ID = "synthetic-benchmark-security-spy"
BENCHMARK_LISTING_ID = "synthetic-benchmark-listing-spy"
BENCHMARK_TICKER = "SPY"
BENCHMARK_TOTAL_RETURN_SERIES_ID = "synthetic-spy-total-return-series"
_TERMINAL_EVENT_KINDS = frozenset(
    {"delisting", "bankruptcy", "cash_merger", "stock_merger", "mixed_merger"}
)
_PARTIAL_2026_SEGMENT_ID = "arv2-partial-2026-exploratory"
_REFUSAL_REASONS = frozenset(
    {
        "cross_date_common_event_component",
        "outside_horizon_fold_test_interval",
        "immature_tail",
        "missing_security_entry_open",
        "security_entry_identity_mismatch",
        "missing_benchmark_entry_open",
        "missing_benchmark_exit_open",
        "missing_terminal_requirement",
        "missing_terminal_shareholder_payoff",
        "missing_security_exit_open",
    }
)

_ROW_INVARIANT_REFUSAL_REASONS = frozenset(
    {
        "missing_security_entry_open",
        "security_entry_identity_mismatch",
        "missing_benchmark_entry_open",
    }
)
_GEOMETRY_REFUSAL_REASONS = frozenset(
    {"outside_horizon_fold_test_interval", "immature_tail"}
)


def _fold_bounds(
    *values: tuple[str, str],
) -> Mapping[int, tuple[date, date]]:
    horizons = {}
    for horizon, (start, end) in zip(HORIZONS, values, strict=True):
        horizons[horizon] = (date.fromisoformat(start), date.fromisoformat(end))
    return MappingProxyType(horizons)


_EVALUATION_SEGMENT_HORIZON_BOUNDS = MappingProxyType(
    {
        "arv2-wf-test-2020": _fold_bounds(
            ("2020-01-03", "2021-01-04"),
            ("2020-01-09", "2021-01-04"),
            ("2020-01-31", "2021-01-04"),
            ("2020-03-30", "2021-01-04"),
        ),
        "arv2-wf-test-2021": _fold_bounds(
            ("2021-01-05", "2022-01-03"),
            ("2021-01-11", "2022-01-03"),
            ("2021-02-02", "2022-01-03"),
            ("2021-03-31", "2022-01-03"),
        ),
        "arv2-wf-test-2022": _fold_bounds(
            ("2022-01-04", "2023-01-03"),
            ("2022-01-10", "2023-01-03"),
            ("2022-02-01", "2023-01-03"),
            ("2022-03-30", "2023-01-03"),
        ),
        "arv2-wf-test-2023": _fold_bounds(
            ("2023-01-04", "2024-01-02"),
            ("2023-01-10", "2024-01-02"),
            ("2023-02-01", "2024-01-02"),
            ("2023-03-30", "2024-01-02"),
        ),
        "arv2-wf-test-2024": _fold_bounds(
            ("2024-01-03", "2025-01-02"),
            ("2024-01-09", "2025-01-02"),
            ("2024-01-31", "2025-01-02"),
            ("2024-03-28", "2025-01-02"),
        ),
        "arv2-wf-test-2025": _fold_bounds(
            ("2025-01-03", "2026-01-02"),
            ("2025-01-10", "2026-01-02"),
            ("2025-02-03", "2026-01-02"),
            ("2025-04-01", "2026-01-02"),
        ),
        "arv2-partial-2026-exploratory": _fold_bounds(
            ("2026-01-05", "2026-08-28"),
            ("2026-01-09", "2026-08-24"),
            ("2026-02-02", "2026-08-03"),
            ("2026-03-31", "2026-06-04"),
        ),
    }
)


@lru_cache(maxsize=1)
def _reviewed_session_axis() -> tuple[date, ...]:
    """Rebuild and authenticate the exact parent fold-manifest session axis."""

    try:
        axis = trading_sessions(REVIEWED_AXIS_START, REVIEWED_AXIS_END)
    except ExchangeCalendarError as exc:
        raise EventStudyInputError("reviewed session axis cannot be rebuilt") from exc
    encoded = json.dumps(
        tuple(item.isoformat() for item in axis),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if (
        len(axis) != REVIEWED_AXIS_SESSION_COUNT
        or hashlib.sha256(encoded).hexdigest() != REVIEWED_AXIS_SHA256
    ):
        raise EventStudyInputError("reviewed session axis identity changed")
    return axis


@lru_cache(maxsize=1)
def _reviewed_session_index() -> Mapping[date, int]:
    return MappingProxyType(
        {session: index for index, session in enumerate(_reviewed_session_axis())}
    )


@dataclasses.dataclass(frozen=True, slots=True)
class DecisionRow:
    row_id: str
    decision_session: date
    security_id: str
    listing_id: str
    historical_ticker: str
    evaluation_segment_id: str
    fold_id: str | None
    firm_specific_score: Decimal
    global_score: Decimal
    common_event_component_id: str
    input_row_sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class SecurityOpenValue:
    session: date
    security_id: str
    listing_id: str
    historical_ticker: str
    total_return_open_value: Decimal
    total_return_series_id: str
    value_basis: str
    source_role: str
    source_sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class BenchmarkOpenValue:
    session: date
    security_id: str
    listing_id: str
    historical_ticker: str
    total_return_open_value: Decimal
    total_return_series_id: str
    value_basis: str
    source_role: str
    source_sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class TerminalRequirement:
    decision_row_id: str
    security_id: str
    terminal_listing_id: str
    terminal_historical_ticker: str
    terminal_session: date
    requirement_id: str
    event_kind: str
    successor_security_id: str | None
    successor_listing_id: str | None
    successor_historical_ticker: str | None
    total_return_series_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class TerminalLifecycle:
    security_id: str
    terminal_listing_id: str
    terminal_historical_ticker: str
    terminal_session: date
    event_kind: str
    successor_security_id: str | None
    successor_listing_id: str | None
    successor_historical_ticker: str | None
    total_return_series_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class SecurityLifecycleCoverage:
    security_id: str
    observed_through_session: date
    terminal_lifecycle: TerminalLifecycle | None
    source_role: str
    source_sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class TerminalShareholderPayoff:
    decision_row_id: str
    security_id: str
    terminal_listing_id: str
    terminal_historical_ticker: str
    terminal_session: date
    valuation_session: date
    valuation_security_id: str
    valuation_listing_id: str
    valuation_historical_ticker: str
    terminal_total_return_index_value: Decimal
    total_return_series_id: str
    value_basis: str
    requirement_id: str
    event_kind: str
    successor_security_id: str | None
    successor_listing_id: str | None
    successor_historical_ticker: str | None
    source_role: str
    source_sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class EventStudyObservation:
    row_id: str
    decision_session: date
    exit_session: date
    horizon_sessions: int
    security_id: str
    entry_listing_id: str
    entry_historical_ticker: str
    exit_listing_id: str
    exit_historical_ticker: str
    evaluation_segment_id: str
    fold_id: str | None
    common_event_component_id: str
    firm_specific_score: Decimal
    global_score: Decimal
    security_total_return: Decimal
    benchmark_total_return: Decimal
    excess_total_return: Decimal
    security_entry_total_return_index_value: Decimal
    security_exit_total_return_index_value: Decimal
    benchmark_entry_total_return_index_value: Decimal
    benchmark_exit_total_return_index_value: Decimal
    terminal_payoff_used: bool
    terminal_requirement_id: str | None
    terminal_event_kind: str | None
    terminal_session: date | None
    terminal_listing_id: str | None
    terminal_historical_ticker: str | None
    valuation_session: date
    valuation_security_id: str
    successor_security_id: str | None
    successor_listing_id: str | None
    successor_historical_ticker: str | None
    decision_input_sha256: str
    security_entry_source_sha256: str
    security_exit_source_sha256: str
    benchmark_entry_source_sha256: str
    benchmark_exit_source_sha256: str
    security_total_return_series_id: str
    benchmark_total_return_series_id: str
    total_return_value_basis: str


@dataclasses.dataclass(frozen=True, slots=True)
class EventStudyRefusal:
    row_id: str
    decision_session: date
    horizon_sessions: int
    security_id: str
    listing_id: str
    historical_ticker: str
    evaluation_segment_id: str
    fold_id: str | None
    common_event_component_id: str
    firm_specific_score: Decimal
    global_score: Decimal
    decision_input_sha256: str
    reason: str


@dataclasses.dataclass(frozen=True, slots=True)
class EventStudyBatch:
    observations: tuple[EventStudyObservation, ...]
    refusals: tuple[EventStudyRefusal, ...]
    security_lifecycle_coverages: tuple[SecurityLifecycleCoverage, ...]
    expected_decision_horizons: int
    candidate_declaration_hash: str
    input_partition_set_sha256: str
    batch_hash: str

    def aggregate_census(self) -> Mapping[str, object]:
        """Return counts and identities only, never security-level outcomes."""

        require_synthetic_event_study_batch(self)
        reasons = Counter(item.reason for item in self.refusals)
        return MappingProxyType(
            {
                "candidate_declaration_hash": self.candidate_declaration_hash,
                "input_partition_set_sha256": self.input_partition_set_sha256,
                "batch_hash": self.batch_hash,
                "expected_decision_horizons": self.expected_decision_horizons,
                "accepted_observations": len(self.observations),
                "named_refusals": len(self.refusals),
                "terminal_payoff_observations": sum(
                    item.terminal_payoff_used for item in self.observations
                ),
                "security_lifecycle_coverage_count": len(
                    self.security_lifecycle_coverages
                ),
                "terminal_lifecycle_count": sum(
                    item.terminal_lifecycle is not None
                    for item in self.security_lifecycle_coverages
                ),
                "refusals_by_reason": MappingProxyType(dict(sorted(reasons.items()))),
            }
        )

    @property
    def result_publication_available(self) -> bool:
        return False

    @property
    def execution_code_authenticated(self) -> bool:
        # Runtime/upload identity is established only at the later reviewed
        # LEAN compile boundary, never by this in-process synthetic object.
        return False

    @property
    def orders_available(self) -> bool:
        return False

    @property
    def trading_available(self) -> bool:
        return False


def _require_text(value: object, name: str) -> None:
    if type(value) is not str or not value or value != value.strip():
        raise EventStudyInputError(f"{name} must be a nonempty canonical string")


def _require_optional_text(value: object, name: str) -> None:
    if value is not None:
        _require_text(value, name)


def _require_sha256(value: object, name: str) -> None:
    _require_text(value, name)
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise EventStudyInputError(f"{name} must be a lowercase SHA-256")


def _require_date(value: object, name: str) -> None:
    if type(value) is not date:
        raise EventStudyInputError(f"{name} must be an exact date")


def _require_positive_decimal(value: object, name: str) -> None:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise EventStudyInputError(f"{name} must be a positive finite Decimal")


def _require_nonnegative_decimal(value: object, name: str) -> None:
    if type(value) is not Decimal or not value.is_finite() or value < 0:
        raise EventStudyInputError(f"{name} must be a nonnegative finite Decimal")


def _require_finite_decimal(value: object, name: str) -> None:
    if type(value) is not Decimal or not value.is_finite():
        raise EventStudyInputError(f"{name} must be a finite Decimal")


def _require_nonbenchmark_identity(
    security_id: str,
    listing_id: str,
    historical_ticker: str,
    name: str,
) -> None:
    if (
        security_id == BENCHMARK_SECURITY_ID
        or listing_id == BENCHMARK_LISTING_ID
        or historical_ticker == BENCHMARK_TICKER
    ):
        raise EventStudyInputError(f"{name} uses a reserved benchmark identity")


def _validate_segment_identity(segment_id: object, fold_id: object) -> None:
    _require_text(segment_id, "evaluation_segment_id")
    if segment_id not in _EVALUATION_SEGMENT_HORIZON_BOUNDS:
        raise EventStudyInputError("evaluation segment is not in reviewed geometry")
    if segment_id == _PARTIAL_2026_SEGMENT_ID:
        if fold_id is not None:
            raise EventStudyInputError("partial 2026 is not a walk-forward fold")
    elif type(fold_id) is not str or fold_id != segment_id:
        raise EventStudyInputError("formal fold identity changed")


def _validate_decision(value: DecisionRow) -> None:
    if type(value) is not DecisionRow:
        raise EventStudyInputError("decisions must be exact DecisionRow values")
    _require_text(value.row_id, "decision row_id")
    _require_date(value.decision_session, "decision_session")
    for name in (
        "security_id",
        "listing_id",
        "historical_ticker",
        "evaluation_segment_id",
        "common_event_component_id",
    ):
        _require_text(getattr(value, name), f"decision {name}")
    _require_nonbenchmark_identity(
        value.security_id,
        value.listing_id,
        value.historical_ticker,
        "decision",
    )
    _validate_segment_identity(value.evaluation_segment_id, value.fold_id)
    _require_finite_decimal(value.firm_specific_score, "firm_specific_score")
    _require_finite_decimal(value.global_score, "global_score")
    _require_sha256(value.input_row_sha256, "input_row_sha256")


def _validate_security_open(value: SecurityOpenValue) -> None:
    if type(value) is not SecurityOpenValue:
        raise EventStudyInputError(
            "security opens must be exact SecurityOpenValue values"
        )
    _require_date(value.session, "security open session")
    for name in (
        "security_id",
        "listing_id",
        "historical_ticker",
        "total_return_series_id",
        "value_basis",
        "source_role",
    ):
        _require_text(getattr(value, name), f"security open {name}")
    _require_nonbenchmark_identity(
        value.security_id,
        value.listing_id,
        value.historical_ticker,
        "security open",
    )
    if value.total_return_series_id == BENCHMARK_TOTAL_RETURN_SERIES_ID:
        raise EventStudyInputError("security open uses the reserved benchmark series")
    _require_positive_decimal(
        value.total_return_open_value, "security total-return open value"
    )
    if value.source_role != SYNTHETIC_OPEN_SOURCE:
        raise EventStudyInputError("production security-open sources are not enabled")
    if value.value_basis != SYNTHETIC_TOTAL_RETURN_VALUE_BASIS:
        raise EventStudyInputError("security-open value basis is not comparable")
    _require_sha256(value.source_sha256, "security open source_sha256")


def _validate_benchmark_open(value: BenchmarkOpenValue) -> None:
    if type(value) is not BenchmarkOpenValue:
        raise EventStudyInputError(
            "benchmark opens must be exact BenchmarkOpenValue values"
        )
    _require_date(value.session, "benchmark open session")
    for name in (
        "security_id",
        "listing_id",
        "historical_ticker",
        "total_return_series_id",
        "value_basis",
        "source_role",
    ):
        _require_text(getattr(value, name), f"benchmark open {name}")
    if (
        value.security_id != BENCHMARK_SECURITY_ID
        or value.listing_id != BENCHMARK_LISTING_ID
        or value.historical_ticker != BENCHMARK_TICKER
    ):
        raise EventStudyInputError("benchmark identity must be the exact synthetic SPY")
    if value.total_return_series_id != BENCHMARK_TOTAL_RETURN_SERIES_ID:
        raise EventStudyInputError("benchmark total-return series identity changed")
    if value.value_basis != SYNTHETIC_TOTAL_RETURN_VALUE_BASIS:
        raise EventStudyInputError("benchmark value basis is not comparable")
    _require_positive_decimal(
        value.total_return_open_value, "benchmark total-return open value"
    )
    if value.source_role != SYNTHETIC_OPEN_SOURCE:
        raise EventStudyInputError("production benchmark-open sources are not enabled")
    _require_sha256(value.source_sha256, "benchmark open source_sha256")


def _validate_successor_fields(
    original_security_id: str,
    event_kind: str,
    successor_security_id: str | None,
    successor_listing_id: str | None,
    successor_historical_ticker: str | None,
) -> None:
    if event_kind not in _TERMINAL_EVENT_KINDS:
        raise EventStudyInputError("terminal event_kind is unknown")
    _require_optional_text(successor_security_id, "successor_security_id")
    _require_optional_text(successor_listing_id, "successor_listing_id")
    _require_optional_text(
        successor_historical_ticker, "successor_historical_ticker"
    )
    successor_fields = (
        successor_security_id,
        successor_listing_id,
        successor_historical_ticker,
    )
    has_successor = any(item is not None for item in successor_fields)
    if has_successor and any(item is None for item in successor_fields):
        raise EventStudyInputError("terminal successor identity must be complete")
    needs_successor = event_kind in {
        "cash_merger",
        "stock_merger",
        "mixed_merger",
    }
    if needs_successor != has_successor:
        raise EventStudyInputError("terminal successor identity disagrees with event_kind")
    if has_successor and successor_security_id == original_security_id:
        raise EventStudyInputError("merger successor must be a distinct security")
    if has_successor:
        _require_nonbenchmark_identity(
            successor_security_id,
            successor_listing_id,
            successor_historical_ticker,
            "merger successor",
        )


def _validate_terminal_requirement(value: TerminalRequirement) -> None:
    if type(value) is not TerminalRequirement:
        raise EventStudyInputError(
            "terminal requirements must be exact TerminalRequirement values"
        )
    for name in (
        "decision_row_id",
        "security_id",
        "terminal_listing_id",
        "terminal_historical_ticker",
        "requirement_id",
        "event_kind",
        "total_return_series_id",
    ):
        _require_text(getattr(value, name), f"terminal requirement {name}")
    _require_nonbenchmark_identity(
        value.security_id,
        value.terminal_listing_id,
        value.terminal_historical_ticker,
        "terminal requirement",
    )
    if value.total_return_series_id == BENCHMARK_TOTAL_RETURN_SERIES_ID:
        raise EventStudyInputError(
            "terminal requirement uses the reserved benchmark series"
        )
    _require_date(value.terminal_session, "terminal requirement session")
    _validate_successor_fields(
        value.security_id,
        value.event_kind,
        value.successor_security_id,
        value.successor_listing_id,
        value.successor_historical_ticker,
    )


def _terminal_lifecycle_from_requirement(
    value: TerminalRequirement,
) -> TerminalLifecycle:
    return TerminalLifecycle(
        security_id=value.security_id,
        terminal_listing_id=value.terminal_listing_id,
        terminal_historical_ticker=value.terminal_historical_ticker,
        terminal_session=value.terminal_session,
        event_kind=value.event_kind,
        successor_security_id=value.successor_security_id,
        successor_listing_id=value.successor_listing_id,
        successor_historical_ticker=value.successor_historical_ticker,
        total_return_series_id=value.total_return_series_id,
    )


def _terminal_lifecycle_from_observation(
    value: EventStudyObservation,
) -> TerminalLifecycle:
    return TerminalLifecycle(
        security_id=value.security_id,
        terminal_listing_id=value.terminal_listing_id,
        terminal_historical_ticker=value.terminal_historical_ticker,
        terminal_session=value.terminal_session,
        event_kind=value.terminal_event_kind,
        successor_security_id=value.successor_security_id,
        successor_listing_id=value.successor_listing_id,
        successor_historical_ticker=value.successor_historical_ticker,
        total_return_series_id=value.security_total_return_series_id,
    )


def _validate_terminal_lifecycle(value: TerminalLifecycle) -> None:
    if type(value) is not TerminalLifecycle:
        raise EventStudyInputError(
            "terminal lifecycles must be exact TerminalLifecycle values"
        )
    for name in (
        "security_id",
        "terminal_listing_id",
        "terminal_historical_ticker",
        "event_kind",
        "total_return_series_id",
    ):
        _require_text(getattr(value, name), f"terminal lifecycle {name}")
    _require_nonbenchmark_identity(
        value.security_id,
        value.terminal_listing_id,
        value.terminal_historical_ticker,
        "terminal lifecycle",
    )
    if value.total_return_series_id == BENCHMARK_TOTAL_RETURN_SERIES_ID:
        raise EventStudyInputError("terminal lifecycle uses the reserved benchmark series")
    _require_date(value.terminal_session, "terminal lifecycle session")
    if value.terminal_session not in _reviewed_session_index():
        raise EventStudyInputError("terminal lifecycle session is outside reviewed axis")
    _validate_successor_fields(
        value.security_id,
        value.event_kind,
        value.successor_security_id,
        value.successor_listing_id,
        value.successor_historical_ticker,
    )


def _validate_security_lifecycle_coverage(
    value: SecurityLifecycleCoverage,
) -> None:
    if type(value) is not SecurityLifecycleCoverage:
        raise EventStudyInputError(
            "security lifecycle coverages must be exact SecurityLifecycleCoverage values"
        )
    _require_text(value.security_id, "security lifecycle coverage security_id")
    if value.security_id == BENCHMARK_SECURITY_ID:
        raise EventStudyInputError(
            "security lifecycle coverage uses the reserved benchmark security"
        )
    _require_date(
        value.observed_through_session,
        "security lifecycle coverage observed_through_session",
    )
    if value.observed_through_session != REVIEWED_AXIS_END:
        raise EventStudyInputError(
            "security lifecycle coverage is incomplete before the reviewed cutoff"
        )
    _require_text(value.source_role, "security lifecycle coverage source_role")
    if value.source_role != SYNTHETIC_LIFECYCLE_SOURCE:
        raise EventStudyInputError(
            "production security lifecycle sources are not enabled"
        )
    _require_sha256(
        value.source_sha256,
        "security lifecycle coverage source_sha256",
    )
    if value.terminal_lifecycle is None:
        return
    _validate_terminal_lifecycle(value.terminal_lifecycle)
    if value.terminal_lifecycle.security_id != value.security_id:
        raise EventStudyInputError(
            "security lifecycle coverage changes permanent-security identity"
        )


def _validate_successor_lifecycle_order(
    coverage_by_security: Mapping[str, SecurityLifecycleCoverage],
) -> None:
    for coverage in coverage_by_security.values():
        lifecycle = coverage.terminal_lifecycle
        if lifecycle is None:
            continue
        if lifecycle.successor_security_id is None:
            continue
        successor_coverage = coverage_by_security.get(
            lifecycle.successor_security_id
        )
        if successor_coverage is None:
            raise EventStudyInputError(
                "merger successor lifecycle coverage is absent"
            )
        successor = successor_coverage.terminal_lifecycle
        if (
            successor is not None
            and successor.terminal_session <= lifecycle.terminal_session
        ):
            raise EventStudyInputError(
                "merger successor terminal lifecycle is not later than its predecessor"
            )


def _validate_terminal_payoff(value: TerminalShareholderPayoff) -> None:
    if type(value) is not TerminalShareholderPayoff:
        raise EventStudyInputError(
            "terminal payoffs must be exact TerminalShareholderPayoff values"
        )
    for name in (
        "decision_row_id",
        "security_id",
        "terminal_listing_id",
        "terminal_historical_ticker",
        "requirement_id",
        "event_kind",
        "value_basis",
        "total_return_series_id",
        "valuation_security_id",
        "valuation_listing_id",
        "valuation_historical_ticker",
        "source_role",
    ):
        _require_text(getattr(value, name), f"terminal payoff {name}")
    _require_nonbenchmark_identity(
        value.security_id,
        value.terminal_listing_id,
        value.terminal_historical_ticker,
        "terminal payoff",
    )
    _require_nonbenchmark_identity(
        value.valuation_security_id,
        value.valuation_listing_id,
        value.valuation_historical_ticker,
        "terminal payoff valuation",
    )
    if value.total_return_series_id == BENCHMARK_TOTAL_RETURN_SERIES_ID:
        raise EventStudyInputError("terminal payoff uses the reserved benchmark series")
    _require_date(value.terminal_session, "terminal payoff session")
    _require_date(value.valuation_session, "terminal payoff valuation session")
    if value.valuation_session < value.terminal_session:
        raise EventStudyInputError("terminal payoff valuation precedes terminal event")
    _require_nonnegative_decimal(
        value.terminal_total_return_index_value,
        "terminal total-return index value",
    )
    if value.value_basis != SYNTHETIC_TERMINAL_VALUE_BASIS:
        raise EventStudyInputError("terminal payoff value basis is not entry-compatible")
    _validate_successor_fields(
        value.security_id,
        value.event_kind,
        value.successor_security_id,
        value.successor_listing_id,
        value.successor_historical_ticker,
    )
    if value.event_kind in {"stock_merger", "mixed_merger"}:
        if value.valuation_session == value.terminal_session:
            raise EventStudyInputError(
                "stock consideration requires a post-event valuation session"
            )
        if (
            value.valuation_security_id != value.successor_security_id
            or value.valuation_listing_id != value.successor_listing_id
            or value.valuation_historical_ticker
            != value.successor_historical_ticker
        ):
            raise EventStudyInputError(
                "stock consideration must be valued through the successor identity"
            )
    elif value.valuation_session != value.terminal_session:
        raise EventStudyInputError(
            "final cash or delisting payoff must be valued at terminal session"
        )
    elif (
        value.valuation_security_id != value.security_id
        or value.valuation_listing_id != value.terminal_listing_id
        or value.valuation_historical_ticker != value.terminal_historical_ticker
    ):
        raise EventStudyInputError(
            "final cash or delisting payoff valuation identity changed"
        )
    if value.source_role != SYNTHETIC_TERMINAL_SOURCE:
        raise EventStudyInputError(
            "QC delisting price or another unreviewed terminal source is prohibited"
        )
    _require_sha256(value.source_sha256, "terminal payoff source_sha256")


def _terminal_lineage(value: TerminalRequirement | TerminalShareholderPayoff) -> tuple:
    return (
        value.decision_row_id,
        value.security_id,
        value.terminal_listing_id,
        value.terminal_historical_ticker,
        value.terminal_session,
        value.requirement_id,
        value.event_kind,
        value.successor_security_id,
        value.successor_listing_id,
        value.successor_historical_ticker,
        value.total_return_series_id,
    )


def _canonical_value(value: object) -> object:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            "$dataclass": type(value).__qualname__,
            "$fields": {
                field.name: _canonical_value(getattr(value, field.name))
                for field in dataclasses.fields(value)
            },
        }
    if type(value) is date:
        return {"$date": value.isoformat()}
    if type(value) is Decimal:
        if not value.is_finite():
            raise EventStudyInputError("partition contains a nonfinite Decimal")
        return {"$decimal": str(value)}
    if type(value) in (str, int, bool) or value is None:
        return value
    if type(value) is tuple:
        return {"$tuple": [_canonical_value(item) for item in value]}
    if type(value) is list:
        return {"$list": [_canonical_value(item) for item in value]}
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise EventStudyInputError("partition object keys must be exact strings")
        return {
            "$object": {
                key: _canonical_value(item) for key, item in value.items()
            }
        }
    raise EventStudyInputError("partition contains a noncanonical value")


def _canonical_json_line(value: object) -> bytes:
    try:
        return (
            json.dumps(
                _canonical_value(value),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise EventStudyInputError("partition row is not canonical JSON") from exc


def _partition_payload(role: str, rows: tuple) -> bytes:
    if type(rows) is not tuple:
        raise EventStudyInputError(f"{role} must be an exact tuple")
    if role == "session_axis":
        return b"".join(_canonical_json_line({"session": item}) for item in rows)
    return b"".join(_canonical_json_line(item) for item in rows)


def build_synthetic_partition_binding(
    *, role: str, partition_id: str, rows: tuple
) -> SyntheticPartitionBinding:
    """Content-identify one in-memory fixture partition without file access."""

    if type(role) is not str or role not in PARTITION_SCHEMAS:
        raise EventStudyInputError("partition role is unknown")
    _require_text(partition_id, "partition_id")
    payload = _partition_payload(role, rows)
    return SyntheticPartitionBinding(
        role=role,
        partition_id=partition_id,
        schema=PARTITION_SCHEMAS[role],
        byte_count=len(payload),
        row_count=len(rows),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _bind_partitions(
    candidate: SyntheticQcRunCandidate,
    role_rows: tuple[tuple[str, tuple], ...],
) -> str:
    expected = {item.role: item for item in candidate.synthetic_partitions}
    actual = []
    for role, rows in role_rows:
        binding = expected.get(role)
        if binding is None:
            raise EventStudyInputError("run candidate is missing an input partition")
        computed = build_synthetic_partition_binding(
            role=role,
            partition_id=binding.partition_id,
            rows=rows,
        )
        if computed != binding:
            raise EventStudyInputError(f"{role} partition does not match run candidate")
        actual.append(computed)
    document = tuple(sorted(actual, key=lambda item: item.role))
    return hashlib.sha256(_canonical_json_line(document)).hexdigest()


def _refusal(decision: DecisionRow, horizon: int, reason: str) -> EventStudyRefusal:
    return EventStudyRefusal(
        row_id=decision.row_id,
        decision_session=decision.decision_session,
        horizon_sessions=horizon,
        security_id=decision.security_id,
        listing_id=decision.listing_id,
        historical_ticker=decision.historical_ticker,
        evaluation_segment_id=decision.evaluation_segment_id,
        fold_id=decision.fold_id,
        common_event_component_id=decision.common_event_component_id,
        firm_specific_score=decision.firm_specific_score,
        global_score=decision.global_score,
        decision_input_sha256=decision.input_row_sha256,
        reason=reason,
    )


def _returns(
    *, entry_security: Decimal, exit_security: Decimal,
    entry_benchmark: Decimal, exit_benchmark: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    # Construct, rather than copy, the arithmetic context on every call so
    # neither caller state nor a mutable module-global Context can alter math.
    context = _fresh_arithmetic_context()
    with localcontext(context):
        security_return = +(exit_security / entry_security - Decimal(1))
        benchmark_return = +(exit_benchmark / entry_benchmark - Decimal(1))
        excess_return = +(security_return - benchmark_return)
    return security_return, benchmark_return, excess_return


def _fresh_arithmetic_context() -> Context:
    return Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[],
    )


def _batch_hash(
    *, candidate_hash: str, partition_set_sha256: str,
    observations: tuple[EventStudyObservation, ...],
    refusals: tuple[EventStudyRefusal, ...],
    security_lifecycle_coverages: tuple[SecurityLifecycleCoverage, ...],
    expected: int,
) -> str:
    document = {
        "candidate_declaration_hash": candidate_hash,
        "input_partition_set_sha256": partition_set_sha256,
        "expected_decision_horizons": expected,
        "observations": observations,
        "refusals": refusals,
        "security_lifecycle_coverages": security_lifecycle_coverages,
    }
    return hashlib.sha256(_canonical_json_line(document)).hexdigest()


def _validate_output_horizon(value: object) -> int:
    if type(value) is not int or value not in HORIZONS:
        raise EventStudyInputError("output horizon is not one of the reviewed horizons")
    return value


def _validate_observation(value: EventStudyObservation) -> None:
    if type(value) is not EventStudyObservation:
        raise EventStudyInputError("event-study observations changed type")
    for name in (
        "row_id",
        "security_id",
        "entry_listing_id",
        "entry_historical_ticker",
        "exit_listing_id",
        "exit_historical_ticker",
        "evaluation_segment_id",
        "common_event_component_id",
        "valuation_security_id",
        "security_total_return_series_id",
        "benchmark_total_return_series_id",
        "total_return_value_basis",
    ):
        _require_text(getattr(value, name), f"observation {name}")
    _require_nonbenchmark_identity(
        value.security_id,
        value.entry_listing_id,
        value.entry_historical_ticker,
        "observation entry",
    )
    _require_nonbenchmark_identity(
        value.valuation_security_id,
        value.exit_listing_id,
        value.exit_historical_ticker,
        "observation exit",
    )
    if value.security_total_return_series_id == BENCHMARK_TOTAL_RETURN_SERIES_ID:
        raise EventStudyInputError("observation uses the reserved benchmark series")
    _validate_segment_identity(value.evaluation_segment_id, value.fold_id)
    _require_date(value.decision_session, "observation decision_session")
    _require_date(value.exit_session, "observation exit_session")
    _require_date(value.valuation_session, "observation valuation_session")
    horizon = _validate_output_horizon(value.horizon_sessions)
    session_index = _reviewed_session_index()
    entry_index = session_index.get(value.decision_session)
    exit_index = session_index.get(value.exit_session)
    if entry_index is None or exit_index is None:
        raise EventStudyInputError("observation session is outside reviewed axis")
    if exit_index - entry_index != horizon:
        raise EventStudyInputError("observation exit is not the exact session horizon")
    lower, upper = _EVALUATION_SEGMENT_HORIZON_BOUNDS[
        value.evaluation_segment_id
    ][horizon]
    if not lower <= value.decision_session < upper:
        raise EventStudyInputError("observation is outside its reviewed segment bound")
    for name in (
        "firm_specific_score",
        "global_score",
        "security_total_return",
        "benchmark_total_return",
        "excess_total_return",
    ):
        _require_finite_decimal(getattr(value, name), f"observation {name}")
    _require_positive_decimal(
        value.security_entry_total_return_index_value,
        "observation security entry total-return index value",
    )
    if type(value.terminal_payoff_used) is not bool:
        raise EventStudyInputError("terminal_payoff_used must be an exact boolean")
    if value.terminal_payoff_used:
        _require_nonnegative_decimal(
            value.security_exit_total_return_index_value,
            "observation security exit total-return index value",
        )
    else:
        _require_positive_decimal(
            value.security_exit_total_return_index_value,
            "observation security exit total-return index value",
        )
    _require_positive_decimal(
        value.benchmark_entry_total_return_index_value,
        "observation benchmark entry total-return index value",
    )
    _require_positive_decimal(
        value.benchmark_exit_total_return_index_value,
        "observation benchmark exit total-return index value",
    )
    expected_returns = _returns(
        entry_security=value.security_entry_total_return_index_value,
        exit_security=value.security_exit_total_return_index_value,
        entry_benchmark=value.benchmark_entry_total_return_index_value,
        exit_benchmark=value.benchmark_exit_total_return_index_value,
    )
    if expected_returns != (
        value.security_total_return,
        value.benchmark_total_return,
        value.excess_total_return,
    ):
        raise EventStudyInputError("observation return arithmetic changed")
    if value.benchmark_total_return <= Decimal("-1"):
        raise EventStudyInputError("benchmark total return cannot lose all value")
    if value.security_total_return < Decimal("-1") or (
        not value.terminal_payoff_used
        and value.security_total_return == Decimal("-1")
    ):
        raise EventStudyInputError("security total return violates payoff bounds")
    for name in (
        "decision_input_sha256",
        "security_entry_source_sha256",
        "security_exit_source_sha256",
        "benchmark_entry_source_sha256",
        "benchmark_exit_source_sha256",
    ):
        _require_sha256(getattr(value, name), f"observation {name}")
    if value.benchmark_total_return_series_id != BENCHMARK_TOTAL_RETURN_SERIES_ID:
        raise EventStudyInputError("observation benchmark series identity changed")
    if value.total_return_value_basis != SYNTHETIC_TOTAL_RETURN_VALUE_BASIS:
        raise EventStudyInputError("observation return value basis changed")
    if not value.terminal_payoff_used:
        if any(
            item is not None
            for item in (
                value.terminal_requirement_id,
                value.terminal_event_kind,
                value.terminal_session,
                value.terminal_listing_id,
                value.terminal_historical_ticker,
                value.successor_security_id,
                value.successor_listing_id,
                value.successor_historical_ticker,
            )
        ):
            raise EventStudyInputError("ordinary observation acquired terminal lineage")
        if (
            value.valuation_session != value.exit_session
            or value.valuation_security_id != value.security_id
        ):
            raise EventStudyInputError("ordinary observation valuation identity changed")
        return

    for name in (
        "terminal_requirement_id",
        "terminal_event_kind",
        "terminal_listing_id",
        "terminal_historical_ticker",
    ):
        _require_text(getattr(value, name), f"observation {name}")
    _require_date(value.terminal_session, "observation terminal_session")
    _require_nonbenchmark_identity(
        value.security_id,
        value.terminal_listing_id,
        value.terminal_historical_ticker,
        "observation terminal",
    )
    if value.terminal_session not in _reviewed_session_index():
        raise EventStudyInputError("observation terminal session is outside reviewed axis")
    if not value.decision_session < value.terminal_session <= value.exit_session:
        raise EventStudyInputError("observation terminal session is out of order")
    _validate_successor_fields(
        value.security_id,
        value.terminal_event_kind,
        value.successor_security_id,
        value.successor_listing_id,
        value.successor_historical_ticker,
    )
    if value.terminal_event_kind in {"stock_merger", "mixed_merger"}:
        if (
            value.valuation_session != value.exit_session
            or value.valuation_security_id != value.successor_security_id
            or value.exit_listing_id != value.successor_listing_id
            or value.exit_historical_ticker != value.successor_historical_ticker
        ):
            raise EventStudyInputError("stock-merger observation valuation changed")
    elif (
        value.valuation_session != value.terminal_session
        or value.valuation_security_id != value.security_id
        or value.exit_listing_id != value.terminal_listing_id
        or value.exit_historical_ticker != value.terminal_historical_ticker
    ):
        raise EventStudyInputError("final-payoff observation valuation changed")


def _validate_refusal(value: EventStudyRefusal) -> None:
    if type(value) is not EventStudyRefusal:
        raise EventStudyInputError("event-study refusals changed type")
    for name in (
        "row_id",
        "security_id",
        "listing_id",
        "historical_ticker",
        "evaluation_segment_id",
        "common_event_component_id",
        "reason",
    ):
        _require_text(getattr(value, name), f"refusal {name}")
    _require_nonbenchmark_identity(
        value.security_id,
        value.listing_id,
        value.historical_ticker,
        "refusal",
    )
    _validate_segment_identity(value.evaluation_segment_id, value.fold_id)
    _require_date(value.decision_session, "refusal decision_session")
    if value.decision_session not in _reviewed_session_index():
        raise EventStudyInputError("refusal decision session is outside reviewed axis")
    horizon = _validate_output_horizon(value.horizon_sessions)
    _require_finite_decimal(value.firm_specific_score, "refusal firm_specific_score")
    _require_finite_decimal(value.global_score, "refusal global_score")
    _require_sha256(value.decision_input_sha256, "refusal decision_input_sha256")
    if value.reason not in _REFUSAL_REASONS:
        raise EventStudyInputError("refusal reason is not in the closed vocabulary")
    lower, upper = _EVALUATION_SEGMENT_HORIZON_BOUNDS[
        value.evaluation_segment_id
    ][horizon]
    if value.reason == "immature_tail" and not (
        value.evaluation_segment_id == _PARTIAL_2026_SEGMENT_ID
        and value.decision_session >= upper
    ):
        raise EventStudyInputError("immature-tail refusal is not a partial-2026 tail")
    if value.reason == "outside_horizon_fold_test_interval" and not (
        value.decision_session < lower
        or (
            value.evaluation_segment_id != _PARTIAL_2026_SEGMENT_ID
            and value.decision_session >= upper
        )
    ):
        raise EventStudyInputError("outside-fold refusal is inside its segment bound")
    if value.reason not in {
        "outside_horizon_fold_test_interval",
        "immature_tail",
        "cross_date_common_event_component",
    } and not (lower <= value.decision_session < upper):
        raise EventStudyInputError("input refusal is outside its segment bound")


def _output_identity(value: EventStudyObservation | EventStudyRefusal) -> tuple:
    listing_id = (
        value.entry_listing_id
        if type(value) is EventStudyObservation
        else value.listing_id
    )
    historical_ticker = (
        value.entry_historical_ticker
        if type(value) is EventStudyObservation
        else value.historical_ticker
    )
    return (
        value.decision_session,
        value.security_id,
        listing_id,
        historical_ticker,
        value.evaluation_segment_id,
        value.fold_id,
        value.common_event_component_id,
        value.firm_specific_score,
        value.global_score,
        value.decision_input_sha256,
    )


def require_synthetic_event_study_batch(batch: EventStudyBatch) -> EventStudyBatch:
    """Recompute the synthetic batch identity; this grants no result authority."""

    if type(batch) is not EventStudyBatch:
        raise EventStudyInputError("event-study batch type changed")
    if type(batch.observations) is not tuple:
        raise EventStudyInputError("event-study observations changed type")
    if type(batch.refusals) is not tuple:
        raise EventStudyInputError("event-study refusals changed type")
    if type(batch.security_lifecycle_coverages) is not tuple:
        raise EventStudyInputError("security lifecycle coverages changed type")
    for item in batch.observations:
        _validate_observation(item)
    for item in batch.refusals:
        _validate_refusal(item)
    for item in batch.security_lifecycle_coverages:
        _validate_security_lifecycle_coverage(item)
    if batch.security_lifecycle_coverages != tuple(
        sorted(
            batch.security_lifecycle_coverages,
            key=lambda item: item.security_id,
        )
    ):
        raise EventStudyInputError(
            "security lifecycle coverages are not canonical order"
        )
    coverage_by_security: dict[str, SecurityLifecycleCoverage] = {}
    lifecycle_by_security: dict[str, TerminalLifecycle] = {}
    for item in batch.security_lifecycle_coverages:
        if item.security_id in coverage_by_security:
            raise EventStudyInputError(
                "security lifecycle coverage keys are not unique"
            )
        coverage_by_security[item.security_id] = item
        if item.terminal_lifecycle is not None:
            lifecycle_by_security[item.security_id] = item.terminal_lifecycle
    _validate_successor_lifecycle_order(coverage_by_security)
    if type(batch.expected_decision_horizons) is not int or (
        batch.expected_decision_horizons
        != len(batch.observations) + len(batch.refusals)
    ):
        raise EventStudyInputError("event-study census changed")
    output_rows = (*batch.observations, *batch.refusals)
    keys = [(item.row_id, item.horizon_sessions) for item in output_rows]
    if len(keys) != len(set(keys)):
        raise EventStudyInputError("event-study row/horizon keys are not unique")
    identities: dict[str, tuple] = {}
    horizons_by_row: dict[str, set[int]] = {}
    outputs_by_row: dict[
        str, list[EventStudyObservation | EventStudyRefusal]
    ] = {}
    for item in output_rows:
        identity = _output_identity(item)
        if item.row_id in identities and identities[item.row_id] != identity:
            raise EventStudyInputError("event-study decision identity changed across horizons")
        identities[item.row_id] = identity
        horizons_by_row.setdefault(item.row_id, set()).add(item.horizon_sessions)
        outputs_by_row.setdefault(item.row_id, []).append(item)
    if any(horizons != set(HORIZONS) for horizons in horizons_by_row.values()):
        raise EventStudyInputError("event-study decision horizons are incomplete")
    if batch.expected_decision_horizons != len(identities) * len(HORIZONS):
        raise EventStudyInputError("event-study decision count changed")
    decision_keys = {(value[0], value[1]) for value in identities.values()}
    if len(decision_keys) != len(identities):
        raise EventStudyInputError(
            "decision session/permanent-security key is duplicated"
        )
    output_order = lambda item: (
        item.decision_session,
        item.security_id,
        (
            item.entry_listing_id
            if type(item) is EventStudyObservation
            else item.listing_id
        ),
        item.row_id,
        item.horizon_sessions,
    )
    if batch.observations != tuple(sorted(batch.observations, key=output_order)):
        raise EventStudyInputError("event-study observations are not canonical order")
    if batch.refusals != tuple(sorted(batch.refusals, key=output_order)):
        raise EventStudyInputError("event-study refusals are not canonical order")

    terminal_refusal_reasons = {
        "missing_terminal_requirement",
        "missing_terminal_shareholder_payoff",
    }
    pre_terminal_gate_refusal_reasons = (
        _GEOMETRY_REFUSAL_REASONS
        | _ROW_INVARIANT_REFUSAL_REASONS
        | {"cross_date_common_event_component", "missing_benchmark_exit_open"}
    )
    outputs_by_security: dict[
        str, list[EventStudyObservation | EventStudyRefusal]
    ] = {}
    for item in output_rows:
        outputs_by_security.setdefault(item.security_id, []).append(item)
    referenced_security_ids = set(outputs_by_security)
    pending_security_ids = list(referenced_security_ids)
    while pending_security_ids:
        security_id = pending_security_ids.pop()
        coverage = coverage_by_security.get(security_id)
        if coverage is None:
            raise EventStudyInputError(
                "decision or successor security has no complete lifecycle coverage"
            )
        lifecycle = coverage.terminal_lifecycle
        if (
            lifecycle is not None
            and lifecycle.successor_security_id is not None
            and lifecycle.successor_security_id not in referenced_security_ids
        ):
            referenced_security_ids.add(lifecycle.successor_security_id)
            pending_security_ids.append(lifecycle.successor_security_id)
    if set(coverage_by_security) != referenced_security_ids:
        raise EventStudyInputError(
            "security lifecycle coverage inventory contains unrelated securities"
        )
    reviewed_axis = _reviewed_session_axis()
    reviewed_index = _reviewed_session_index()
    for security_id, rows in outputs_by_security.items():
        lifecycle = lifecycle_by_security.get(security_id)
        for item in rows:
            if lifecycle is None:
                if (
                    type(item) is EventStudyObservation
                    and item.terminal_payoff_used
                ) or (
                    type(item) is EventStudyRefusal
                    and item.reason in terminal_refusal_reasons
                ):
                    raise EventStudyInputError(
                        "terminal output has no security lifecycle"
                    )
                continue
            if item.decision_session >= lifecycle.terminal_session:
                raise EventStudyInputError(
                    "decision is on or after its security terminal session"
                )
            if (
                type(item) is EventStudyRefusal
                and item.reason
                in _GEOMETRY_REFUSAL_REASONS
                | {"cross_date_common_event_component"}
            ):
                continue
            exit_session = (
                item.exit_session
                if type(item) is EventStudyObservation
                else reviewed_axis[
                    reviewed_index[item.decision_session]
                    + item.horizon_sessions
                ]
            )
            reaches_terminal = exit_session >= lifecycle.terminal_session
            if not reaches_terminal:
                if (
                    type(item) is EventStudyRefusal
                    and item.reason in terminal_refusal_reasons
                ):
                    raise EventStudyInputError(
                        "terminal refusal precedes the security lifecycle"
                    )
                continue
            if type(item) is EventStudyObservation:
                if not item.terminal_payoff_used or (
                    _terminal_lifecycle_from_observation(item) != lifecycle
                ):
                    raise EventStudyInputError(
                        "ordinary observation follows or changes a terminal security lifecycle"
                    )
                if item.terminal_event_kind in {"stock_merger", "mixed_merger"}:
                    successor = lifecycle_by_security.get(item.successor_security_id)
                    if (
                        successor is not None
                        and successor.terminal_session <= item.valuation_session
                    ):
                        raise EventStudyInputError(
                            "stock-merger payoff traverses a terminal successor"
                        )
                continue
            if item.reason not in (
                pre_terminal_gate_refusal_reasons | terminal_refusal_reasons
            ):
                raise EventStudyInputError(
                    "ordinary observation/security path follows a terminal lifecycle"
                )

    for row in outputs_by_row.values():
        invariant_reasons = {
            item.reason
            for item in row
            if type(item) is EventStudyRefusal
            and item.reason in _ROW_INVARIANT_REFUSAL_REASONS
        }
        if len(invariant_reasons) > 1:
            raise EventStudyInputError(
                "row-invariant input refusal changed across horizons"
            )
        if invariant_reasons:
            invariant_reason = next(iter(invariant_reasons))
            for item in row:
                if (
                    type(item) is EventStudyRefusal
                    and item.reason in _GEOMETRY_REFUSAL_REASONS
                ):
                    continue
                if (
                    type(item) is not EventStudyRefusal
                    or item.reason != invariant_reason
                ):
                    raise EventStudyInputError(
                        "row-invariant input refusal is selectively applied"
                    )

        terminal_path_seen = False
        for item in sorted(row, key=lambda value: value.horizon_sessions):
            is_terminal_path = (
                type(item) is EventStudyObservation and item.terminal_payoff_used
            ) or (
                type(item) is EventStudyRefusal
                and item.reason
                in {
                    "missing_terminal_requirement",
                    "missing_terminal_shareholder_payoff",
                }
            )
            if is_terminal_path:
                terminal_path_seen = True
                continue
            if terminal_path_seen and not (
                type(item) is EventStudyRefusal
                and item.reason
                in _GEOMETRY_REFUSAL_REASONS | {"missing_benchmark_exit_open"}
            ):
                raise EventStudyInputError(
                    "ordinary observation follows a terminal path"
                )

        lifecycle = lifecycle_by_security.get(row[0].security_id)
        if lifecycle is None:
            continue
        terminal_stage_items = []
        for item in row:
            if (
                type(item) is EventStudyRefusal
                and item.reason in pre_terminal_gate_refusal_reasons
            ):
                continue
            exit_session = (
                item.exit_session
                if type(item) is EventStudyObservation
                else reviewed_axis[
                    reviewed_index[item.decision_session]
                    + item.horizon_sessions
                ]
            )
            if exit_session >= lifecycle.terminal_session:
                terminal_stage_items.append(item)
        terminal_reasons = {
            item.reason
            for item in terminal_stage_items
            if type(item) is EventStudyRefusal
        }
        if "missing_terminal_requirement" in terminal_reasons and any(
            type(item) is not EventStudyRefusal
            or item.reason != "missing_terminal_requirement"
            for item in terminal_stage_items
        ):
            raise EventStudyInputError(
                "terminal requirement availability changed across horizons"
            )
        if lifecycle.event_kind not in {"stock_merger", "mixed_merger"}:
            refused = [
                item
                for item in terminal_stage_items
                if type(item) is EventStudyRefusal
            ]
            if refused and (
                len(refused) != len(terminal_stage_items)
                or len({item.reason for item in refused}) != 1
            ):
                raise EventStudyInputError(
                    "fixed terminal payoff availability changed across horizons"
                )

    listing_identities: dict[str, tuple[str, str]] = {}

    def bind_output_listing(
        listing_id: str, security_id: str, historical_ticker: str
    ) -> None:
        identity = (security_id, historical_ticker)
        bound = listing_identities.setdefault(listing_id, identity)
        if bound != identity:
            raise EventStudyInputError(
                "output listing identifies multiple security/ticker identities"
            )

    series_identities = {BENCHMARK_TOTAL_RETURN_SERIES_ID: BENCHMARK_SECURITY_ID}
    security_series_identities = {
        BENCHMARK_SECURITY_ID: BENCHMARK_TOTAL_RETURN_SERIES_ID
    }
    for coverage in batch.security_lifecycle_coverages:
        lifecycle = coverage.terminal_lifecycle
        if lifecycle is None:
            continue
        bind_output_listing(
            lifecycle.terminal_listing_id,
            lifecycle.security_id,
            lifecycle.terminal_historical_ticker,
        )
        if lifecycle.successor_listing_id is not None:
            bind_output_listing(
                lifecycle.successor_listing_id,
                lifecycle.successor_security_id,
                lifecycle.successor_historical_ticker,
            )
        bound_security = series_identities.setdefault(
            lifecycle.total_return_series_id, lifecycle.security_id
        )
        if bound_security != lifecycle.security_id:
            raise EventStudyInputError(
                "terminal lifecycle series identifies multiple securities"
            )
        bound_series = security_series_identities.setdefault(
            lifecycle.security_id, lifecycle.total_return_series_id
        )
        if bound_series != lifecycle.total_return_series_id:
            raise EventStudyInputError(
                "terminal lifecycle security identifies multiple series"
            )
    for item in output_rows:
        if type(item) is EventStudyRefusal:
            bind_output_listing(
                item.listing_id,
                item.security_id,
                item.historical_ticker,
            )
            continue
        bind_output_listing(
            item.entry_listing_id,
            item.security_id,
            item.entry_historical_ticker,
        )
        bind_output_listing(
            item.exit_listing_id,
            item.valuation_security_id,
            item.exit_historical_ticker,
        )
        bound_security = series_identities.setdefault(
            item.security_total_return_series_id, item.security_id
        )
        if bound_security != item.security_id:
            raise EventStudyInputError(
                "output total-return series identifies multiple securities"
            )
        bound_series = security_series_identities.setdefault(
            item.security_id, item.security_total_return_series_id
        )
        if bound_series != item.security_total_return_series_id:
            raise EventStudyInputError(
                "output permanent security identifies multiple total-return series"
            )
        if item.terminal_payoff_used:
            bind_output_listing(
                item.terminal_listing_id,
                item.security_id,
                item.terminal_historical_ticker,
            )
            if item.successor_listing_id is not None:
                bind_output_listing(
                    item.successor_listing_id,
                    item.successor_security_id,
                    item.successor_historical_ticker,
                )

    observations_by_row: dict[str, list[EventStudyObservation]] = {}
    security_facts_by_series_session: dict[tuple[str, date], tuple] = {}
    security_availability_proofs: set[tuple[str, date]] = set()
    terminal_payoff_facts: dict[tuple[str, date], tuple] = {}
    terminal_requirement_rows: dict[str, str] = {}
    for item in batch.observations:
        observations_by_row.setdefault(item.row_id, []).append(item)
        security_availability_proofs.add(
            (item.security_id, item.decision_session)
        )
        if not item.terminal_payoff_used:
            security_availability_proofs.add((item.security_id, item.exit_session))
        for session, raw_value, source_sha256 in (
            (
                item.decision_session,
                item.security_entry_total_return_index_value,
                item.security_entry_source_sha256,
            ),
            (
                item.valuation_session,
                item.security_exit_total_return_index_value,
                item.security_exit_source_sha256,
            ),
        ):
            fact_key = (item.security_total_return_series_id, session)
            fact = (raw_value, source_sha256)
            bound_fact = security_facts_by_series_session.setdefault(
                fact_key, fact
            )
            if bound_fact != fact:
                raise EventStudyInputError(
                    "security series-session value/source fact changed"
                )
        if item.terminal_payoff_used:
            bound_row = terminal_requirement_rows.setdefault(
                item.terminal_requirement_id, item.row_id
            )
            if bound_row != item.row_id:
                raise EventStudyInputError(
                    "terminal requirement identity is shared across decision rows"
                )
            payoff_key = (
                item.security_total_return_series_id,
                item.valuation_session,
            )
            payoff_fact = (
                item.security_exit_total_return_index_value,
                item.security_exit_source_sha256,
                item.valuation_security_id,
                item.exit_listing_id,
                item.exit_historical_ticker,
                item.terminal_event_kind,
            )
            bound_payoff = terminal_payoff_facts.setdefault(
                payoff_key, payoff_fact
            )
            if bound_payoff != payoff_fact:
                raise EventStudyInputError(
                    "terminal payoff fact changed across decision rows"
                )

    entry_security_proof_reasons = (
        _REFUSAL_REASONS
        - _GEOMETRY_REFUSAL_REASONS
        - {"cross_date_common_event_component", "missing_security_entry_open"}
    )
    reviewed_axis = _reviewed_session_axis()
    reviewed_index = _reviewed_session_index()
    for item in batch.refusals:
        if item.reason in entry_security_proof_reasons:
            security_availability_proofs.add(
                (item.security_id, item.decision_session)
            )
    for item in batch.refusals:
        if (
            item.reason == "missing_security_entry_open"
            and (item.security_id, item.decision_session)
            in security_availability_proofs
        ):
            raise EventStudyInputError(
                "security entry availability changed across decisions"
            )
        if item.reason == "missing_security_exit_open":
            exit_session = reviewed_axis[
                reviewed_index[item.decision_session] + item.horizon_sessions
            ]
            if (item.security_id, exit_session) in security_availability_proofs:
                raise EventStudyInputError(
                    "security exit availability changed across decisions"
                )
    for row in observations_by_row.values():
        entry_lineages = {
            (
                item.security_entry_total_return_index_value,
                item.security_entry_source_sha256,
                item.benchmark_entry_source_sha256,
                item.security_total_return_series_id,
            )
            for item in row
        }
        if len(entry_lineages) != 1:
            raise EventStudyInputError(
                "entry source or return-series lineage changed across horizons"
            )
        terminal_seen = False
        terminal_lineage = None
        fixed_payoff_identity = None
        for item in sorted(row, key=lambda value: value.horizon_sessions):
            if not item.terminal_payoff_used:
                if terminal_seen:
                    raise EventStudyInputError(
                        "ordinary observation follows a terminal observation"
                    )
                continue
            terminal_seen = True
            lineage = (
                item.terminal_requirement_id,
                item.terminal_event_kind,
                item.terminal_session,
                item.terminal_listing_id,
                item.terminal_historical_ticker,
                item.successor_security_id,
                item.successor_listing_id,
                item.successor_historical_ticker,
                item.security_total_return_series_id,
            )
            if terminal_lineage is not None and lineage != terminal_lineage:
                raise EventStudyInputError(
                    "terminal lineage changed across decision horizons"
                )
            terminal_lineage = lineage
            if item.terminal_event_kind not in {"stock_merger", "mixed_merger"}:
                payoff_identity = (
                    item.security_total_return,
                    item.security_exit_source_sha256,
                    item.valuation_session,
                    item.valuation_security_id,
                    item.exit_listing_id,
                    item.exit_historical_ticker,
                )
                if (
                    fixed_payoff_identity is not None
                    and payoff_identity != fixed_payoff_identity
                ):
                    raise EventStudyInputError(
                        "final terminal payoff changed across decision horizons"
                    )
                fixed_payoff_identity = payoff_identity

    benchmark_identities: dict[tuple[date, int], tuple] = {}
    benchmark_entry_sources: dict[date, str] = {}
    benchmark_exit_sources: dict[date, str] = {}
    benchmark_facts_by_session: dict[date, tuple] = {}
    for item in batch.observations:
        key = (item.decision_session, item.horizon_sessions)
        identity = (
            item.exit_session,
            item.benchmark_entry_total_return_index_value,
            item.benchmark_exit_total_return_index_value,
            item.benchmark_total_return,
            item.benchmark_entry_source_sha256,
            item.benchmark_exit_source_sha256,
            item.benchmark_total_return_series_id,
            item.total_return_value_basis,
        )
        bound = benchmark_identities.setdefault(key, identity)
        if bound != identity:
            raise EventStudyInputError(
                "shared benchmark outcome changed across security rows"
            )
        bound_entry_source = benchmark_entry_sources.setdefault(
            item.decision_session, item.benchmark_entry_source_sha256
        )
        if bound_entry_source != item.benchmark_entry_source_sha256:
            raise EventStudyInputError(
                "shared benchmark entry source changed across horizons"
            )
        bound_exit_source = benchmark_exit_sources.setdefault(
            item.exit_session, item.benchmark_exit_source_sha256
        )
        if bound_exit_source != item.benchmark_exit_source_sha256:
            raise EventStudyInputError(
                "shared benchmark exit source changed across decision horizons"
            )
        for session, raw_value, source_sha256 in (
            (
                item.decision_session,
                item.benchmark_entry_total_return_index_value,
                item.benchmark_entry_source_sha256,
            ),
            (
                item.exit_session,
                item.benchmark_exit_total_return_index_value,
                item.benchmark_exit_source_sha256,
            ),
        ):
            fact = (raw_value, source_sha256)
            bound_fact = benchmark_facts_by_session.setdefault(session, fact)
            if bound_fact != fact:
                raise EventStudyInputError(
                    "benchmark value/source fact changed across entry and exit roles"
                )
    benchmark_entry_proof_reasons = {
        "missing_benchmark_exit_open",
        "missing_terminal_requirement",
        "missing_terminal_shareholder_payoff",
        "missing_security_exit_open",
    }
    benchmark_exit_proof_reasons = {
        "missing_terminal_requirement",
        "missing_terminal_shareholder_payoff",
        "missing_security_exit_open",
    }
    observed_sessions = {item.decision_session for item in batch.observations}
    observed_sessions.update(
        item.decision_session
        for item in batch.refusals
        if item.reason in benchmark_entry_proof_reasons
    )
    observed_horizons = set(benchmark_identities)
    observed_horizons.update(
        (item.decision_session, item.horizon_sessions)
        for item in batch.refusals
        if item.reason in benchmark_exit_proof_reasons
    )
    for item in batch.refusals:
        if (
            item.reason == "missing_benchmark_entry_open"
            and item.decision_session in observed_sessions
        ):
            raise EventStudyInputError(
                "benchmark entry availability changed across security rows"
            )
        if (
            item.reason == "missing_benchmark_exit_open"
            and (item.decision_session, item.horizon_sessions) in observed_horizons
        ):
            raise EventStudyInputError(
                "benchmark exit availability changed across security rows"
            )

    component_outputs: dict[
        str, list[EventStudyObservation | EventStudyRefusal]
    ] = {}
    for item in output_rows:
        component_outputs.setdefault(item.common_event_component_id, []).append(item)
    cross_date_components = {
        component
        for component, items in component_outputs.items()
        if len({item.decision_session for item in items}) > 1
    }
    claimed_cross_date_components = {
        item.common_event_component_id
        for item in batch.refusals
        if item.reason == "cross_date_common_event_component"
    }
    if claimed_cross_date_components != cross_date_components:
        raise EventStudyInputError("cross-date component refusal claim changed")
    for component in cross_date_components:
        items = component_outputs[component]
        if any(
            type(item) is not EventStudyRefusal
            or item.reason != "cross_date_common_event_component"
            for item in items
        ):
            raise EventStudyInputError(
                "cross-date component refusal is not complete and auditable"
            )
    _require_sha256(
        batch.candidate_declaration_hash, "candidate_declaration_hash"
    )
    _require_sha256(batch.input_partition_set_sha256, "input_partition_set_sha256")
    _require_sha256(batch.batch_hash, "batch_hash")
    expected_hash = _batch_hash(
        candidate_hash=batch.candidate_declaration_hash,
        partition_set_sha256=batch.input_partition_set_sha256,
        observations=batch.observations,
        refusals=batch.refusals,
        security_lifecycle_coverages=batch.security_lifecycle_coverages,
        expected=batch.expected_decision_horizons,
    )
    if expected_hash != batch.batch_hash:
        raise EventStudyInputError("event-study batch changed after construction")
    return batch


def collect_synthetic_event_study(
    *,
    run_candidate: SyntheticQcRunCandidate,
    session_axis: tuple[date, ...],
    decisions: tuple[DecisionRow, ...],
    security_opens: tuple[SecurityOpenValue, ...],
    benchmark_opens: tuple[BenchmarkOpenValue, ...],
    security_lifecycle_coverages: tuple[SecurityLifecycleCoverage, ...],
    terminal_requirements: tuple[TerminalRequirement, ...],
    terminal_payoffs: tuple[TerminalShareholderPayoff, ...],
) -> EventStudyBatch:
    """Build exhaustive synthetic open-to-open observations and refusals.

    Horizons are positions on a complete XNYS session axis, never elapsed
    calendar days. A decision-specific terminal requirement inside a horizon
    replaces the ordinary exit only when an exact, entry-compatible total-
    shareholder-payoff record is present. QC delisting prices have no accepted
    representation here.
    """

    try:
        require_synthetic_qc_run_candidate(run_candidate)
    except QcRunContractError as exc:
        raise EventStudyInputError("run candidate is not authenticated") from exc
    inputs = (
        (session_axis, "session_axis"),
        (decisions, "decisions"),
        (security_opens, "security_opens"),
        (benchmark_opens, "benchmark_opens"),
        (security_lifecycle_coverages, "security_lifecycle_coverages"),
        (terminal_requirements, "terminal_requirements"),
        (terminal_payoffs, "terminal_payoffs"),
    )
    for value, name in inputs:
        if type(value) is not tuple:
            raise EventStudyInputError(f"{name} must be an exact tuple")
    if not session_axis:
        raise EventStudyInputError("session_axis cannot be empty")
    for session in session_axis:
        _require_date(session, "session_axis item")
    if tuple(sorted(session_axis)) != session_axis or len(set(session_axis)) != len(
        session_axis
    ):
        raise EventStudyInputError("session_axis must be strictly increasing and unique")
    if session_axis != _reviewed_session_axis():
        raise EventStudyInputError(
            "session_axis must equal the exact reviewed 2013-2026 XNYS axis"
        )
    session_index = {session: index for index, session in enumerate(session_axis)}

    listing_to_identity: dict[str, tuple[str, str]] = {}

    def bind_listing(
        listing_id: str, security_id: str, historical_ticker: str
    ) -> None:
        identity = (security_id, historical_ticker)
        bound = listing_to_identity.setdefault(listing_id, identity)
        if bound != identity:
            raise EventStudyInputError(
                "one listing_id cannot identify multiple security/ticker identities"
            )

    series_to_security: dict[str, str] = {}
    security_to_series: dict[str, str] = {}

    def bind_series(total_return_series_id: str, security_id: str) -> None:
        bound = series_to_security.setdefault(total_return_series_id, security_id)
        if bound != security_id:
            raise EventStudyInputError(
                "one total-return series cannot identify multiple securities"
            )
        bound_series = security_to_series.setdefault(
            security_id, total_return_series_id
        )
        if bound_series != total_return_series_id:
            raise EventStudyInputError(
                "one permanent security cannot identify multiple total-return series"
            )

    decision_rows: dict[str, DecisionRow] = {}
    decision_keys: set[tuple[date, str]] = set()
    component_sessions: dict[str, set[date]] = {}
    for decision in decisions:
        _validate_decision(decision)
        if decision.row_id in decision_rows:
            raise EventStudyInputError("decision row_id must be unique")
        decision_key = (decision.decision_session, decision.security_id)
        if decision_key in decision_keys:
            raise EventStudyInputError(
                "decision session/permanent-security key must be unique"
            )
        if decision.decision_session not in session_index:
            raise EventStudyInputError("decision session is absent from session_axis")
        decision_rows[decision.row_id] = decision
        decision_keys.add(decision_key)
        bind_listing(
            decision.listing_id,
            decision.security_id,
            decision.historical_ticker,
        )
        component_sessions.setdefault(decision.common_event_component_id, set()).add(
            decision.decision_session
        )
    cross_date_components = {
        component
        for component, sessions in component_sessions.items()
        if len(sessions) > 1
    }

    security_by_key: dict[tuple[str, date], SecurityOpenValue] = {}
    for item in security_opens:
        _validate_security_open(item)
        key = (item.security_id, item.session)
        if key in security_by_key:
            raise EventStudyInputError("security-open keys must be unique")
        if item.session not in session_index:
            raise EventStudyInputError("security-open session is absent from session_axis")
        bind_listing(item.listing_id, item.security_id, item.historical_ticker)
        bind_series(item.total_return_series_id, item.security_id)
        security_by_key[key] = item

    benchmark_by_session: dict[date, BenchmarkOpenValue] = {}
    for item in benchmark_opens:
        _validate_benchmark_open(item)
        if item.session in benchmark_by_session:
            raise EventStudyInputError("benchmark-open sessions must be unique")
        if item.session not in session_index:
            raise EventStudyInputError("benchmark-open session is absent from session_axis")
        bind_listing(item.listing_id, item.security_id, item.historical_ticker)
        bind_series(item.total_return_series_id, item.security_id)
        benchmark_by_session[item.session] = item

    for coverage in security_lifecycle_coverages:
        _validate_security_lifecycle_coverage(coverage)
    if security_lifecycle_coverages != tuple(
        sorted(security_lifecycle_coverages, key=lambda item: item.security_id)
    ):
        raise EventStudyInputError(
            "security lifecycle coverages must be in canonical order"
        )
    coverage_by_security: dict[str, SecurityLifecycleCoverage] = {}
    lifecycle_by_security: dict[str, TerminalLifecycle] = {}
    for coverage in security_lifecycle_coverages:
        if coverage.security_id in coverage_by_security:
            raise EventStudyInputError(
                "security lifecycle coverage keys must be unique"
            )
        coverage_by_security[coverage.security_id] = coverage
        lifecycle = coverage.terminal_lifecycle
        if lifecycle is None:
            continue
        lifecycle_by_security[coverage.security_id] = lifecycle
        bind_listing(
            lifecycle.terminal_listing_id,
            lifecycle.security_id,
            lifecycle.terminal_historical_ticker,
        )
        bind_series(lifecycle.total_return_series_id, lifecycle.security_id)
        if lifecycle.successor_listing_id is not None:
            bind_listing(
                lifecycle.successor_listing_id,
                lifecycle.successor_security_id,
                lifecycle.successor_historical_ticker,
            )
    _validate_successor_lifecycle_order(coverage_by_security)

    referenced_security_ids = {item.security_id for item in decisions}
    pending_security_ids = list(referenced_security_ids)
    while pending_security_ids:
        security_id = pending_security_ids.pop()
        coverage = coverage_by_security.get(security_id)
        if coverage is None:
            raise EventStudyInputError(
                "decision or successor security has no complete lifecycle coverage"
            )
        lifecycle = coverage.terminal_lifecycle
        if (
            lifecycle is not None
            and lifecycle.successor_security_id is not None
            and lifecycle.successor_security_id not in referenced_security_ids
        ):
            referenced_security_ids.add(lifecycle.successor_security_id)
            pending_security_ids.append(lifecycle.successor_security_id)
    if set(coverage_by_security) != referenced_security_ids:
        raise EventStudyInputError(
            "security lifecycle coverage inventory contains unrelated securities"
        )

    requirement_by_decision: dict[str, TerminalRequirement] = {}
    requirement_by_id: dict[str, TerminalRequirement] = {}
    for item in terminal_requirements:
        _validate_terminal_requirement(item)
        if item.decision_row_id in requirement_by_decision:
            raise EventStudyInputError("terminal requirement decision must be unique")
        if item.requirement_id in requirement_by_id:
            raise EventStudyInputError("terminal requirement_id must be unique")
        decision = decision_rows.get(item.decision_row_id)
        if decision is None:
            raise EventStudyInputError("terminal requirement has no decision row")
        if item.security_id != decision.security_id:
            raise EventStudyInputError("terminal requirement security lineage changed")
        lifecycle = _terminal_lifecycle_from_requirement(item)
        if lifecycle_by_security.get(item.security_id) != lifecycle:
            raise EventStudyInputError(
                "terminal requirement does not match complete lifecycle inventory"
            )
        if item.terminal_session not in session_index:
            raise EventStudyInputError("terminal requirement session is absent from axis")
        if session_index[item.terminal_session] <= session_index[decision.decision_session]:
            raise EventStudyInputError("terminal requirement does not follow entry")
        bind_listing(
            item.terminal_listing_id,
            item.security_id,
            item.terminal_historical_ticker,
        )
        bind_series(item.total_return_series_id, item.security_id)
        if item.successor_listing_id is not None:
            bind_listing(
                item.successor_listing_id,
                item.successor_security_id,
                item.successor_historical_ticker,
            )
        requirement_by_decision[item.decision_row_id] = item
        requirement_by_id[item.requirement_id] = item

    for decision in decisions:
        lifecycle = lifecycle_by_security.get(decision.security_id)
        if (
            lifecycle is not None
            and decision.decision_session >= lifecycle.terminal_session
        ):
            raise EventStudyInputError(
                "decision is on or after its security terminal session"
            )

    payoff_by_key: dict[tuple[str, date], TerminalShareholderPayoff] = {}
    payoff_fact_by_series_session: dict[tuple[str, date], tuple] = {}
    for item in terminal_payoffs:
        _validate_terminal_payoff(item)
        payoff_key = (item.requirement_id, item.valuation_session)
        if payoff_key in payoff_by_key:
            raise EventStudyInputError(
                "terminal payoff requirement/valuation key must be unique"
            )
        requirement = requirement_by_id.get(item.requirement_id)
        if requirement is None:
            raise EventStudyInputError("terminal payoff has no matching requirement")
        if _terminal_lineage(item) != _terminal_lineage(requirement):
            raise EventStudyInputError("terminal payoff does not match its requirement")
        payoff_fact_key = (item.total_return_series_id, item.valuation_session)
        payoff_fact = (
            item.terminal_total_return_index_value,
            item.value_basis,
            item.source_role,
            item.source_sha256,
            item.valuation_security_id,
            item.valuation_listing_id,
            item.valuation_historical_ticker,
            item.event_kind,
        )
        bound_payoff_fact = payoff_fact_by_series_session.setdefault(
            payoff_fact_key, payoff_fact
        )
        if bound_payoff_fact != payoff_fact:
            raise EventStudyInputError(
                "one security valuation session has conflicting terminal payoffs"
            )
        if item.valuation_session not in session_index:
            raise EventStudyInputError("terminal payoff valuation session is absent from axis")
        bind_listing(
            item.terminal_listing_id,
            item.security_id,
            item.terminal_historical_ticker,
        )
        bind_series(item.total_return_series_id, item.security_id)
        bind_listing(
            item.valuation_listing_id,
            item.valuation_security_id,
            item.valuation_historical_ticker,
        )
        if item.successor_listing_id is not None:
            bind_listing(
                item.successor_listing_id,
                item.successor_security_id,
                item.successor_historical_ticker,
            )
        if item.event_kind in {"stock_merger", "mixed_merger"}:
            successor = lifecycle_by_security.get(item.successor_security_id)
            if (
                successor is not None
                and successor.terminal_session <= item.valuation_session
            ):
                raise EventStudyInputError(
                    "stock-merger payoff traverses a terminal successor"
                )
            decision = decision_rows[item.decision_row_id]
            entry_index = session_index[decision.decision_session]
            terminal_index = session_index[requirement.terminal_session]
            allowed_valuations = {
                session_axis[entry_index + horizon]
                for horizon in HORIZONS
                if entry_index + horizon < len(session_axis)
                and terminal_index <= entry_index + horizon
            }
            if item.valuation_session not in allowed_valuations:
                raise EventStudyInputError(
                    "stock consideration valuation is not a decision horizon"
                )
        payoff_by_key[payoff_key] = item

    role_rows = (
        ("session_axis", session_axis),
        ("decision_rows", decisions),
        ("security_open_values", security_opens),
        ("benchmark_open_values", benchmark_opens),
        ("security_lifecycle_coverages", security_lifecycle_coverages),
        ("terminal_requirements", terminal_requirements),
        ("terminal_shareholder_payoffs", terminal_payoffs),
    )
    partition_set_sha256 = _bind_partitions(run_candidate, role_rows)

    observations: list[EventStudyObservation] = []
    refusals: list[EventStudyRefusal] = []
    ordered_decisions = sorted(
        decisions,
        key=lambda item: (
            item.decision_session,
            item.security_id,
            item.listing_id,
            item.row_id,
        ),
    )
    for decision in ordered_decisions:
        entry_index = session_index[decision.decision_session]
        requirement = requirement_by_decision.get(decision.row_id)
        lifecycle = lifecycle_by_security.get(decision.security_id)
        if decision.common_event_component_id in cross_date_components:
            refusals.extend(
                _refusal(decision, horizon, "cross_date_common_event_component")
                for horizon in HORIZONS
            )
            continue

        entry_security = security_by_key.get(
            (decision.security_id, decision.decision_session)
        )
        entry_benchmark = benchmark_by_session.get(decision.decision_session)
        for horizon in HORIZONS:
            lower, upper = _EVALUATION_SEGMENT_HORIZON_BOUNDS[
                decision.evaluation_segment_id
            ][horizon]
            if decision.decision_session < lower:
                refusals.append(
                    _refusal(decision, horizon, "outside_horizon_fold_test_interval")
                )
                continue
            if decision.decision_session >= upper:
                reason = (
                    "immature_tail"
                    if decision.evaluation_segment_id
                    == "arv2-partial-2026-exploratory"
                    else "outside_horizon_fold_test_interval"
                )
                refusals.append(_refusal(decision, horizon, reason))
                continue
            exit_index = entry_index + horizon
            if exit_index >= len(session_axis):
                raise EventStudyInputError(
                    "reviewed axis cannot mature an eligible decision horizon"
                )
            exit_session = session_axis[exit_index]
            if entry_security is None:
                refusals.append(
                    _refusal(decision, horizon, "missing_security_entry_open")
                )
                continue
            if (
                entry_security.listing_id != decision.listing_id
                or entry_security.historical_ticker != decision.historical_ticker
            ):
                refusals.append(
                    _refusal(decision, horizon, "security_entry_identity_mismatch")
                )
                continue
            if entry_benchmark is None:
                refusals.append(
                    _refusal(decision, horizon, "missing_benchmark_entry_open")
                )
                continue
            if entry_security.value_basis != entry_benchmark.value_basis:
                raise EventStudyInputError(
                    "validated security/benchmark value basis changed after preflight"
                )
            exit_benchmark = benchmark_by_session.get(exit_session)
            if exit_benchmark is None:
                refusals.append(
                    _refusal(decision, horizon, "missing_benchmark_exit_open")
                )
                continue

            terminal_used = False
            terminal_requirement_id = None
            terminal_event_kind = None
            terminal_session = None
            terminal_listing_id = None
            terminal_historical_ticker = None
            successor_security_id = None
            successor_listing_id = None
            successor_historical_ticker = None
            valuation_session = exit_session
            valuation_security_id = decision.security_id
            if lifecycle is not None and (
                session_index[lifecycle.terminal_session] <= exit_index
            ):
                if requirement is None:
                    refusals.append(
                        _refusal(
                            decision,
                            horizon,
                            "missing_terminal_requirement",
                        )
                    )
                    continue
                valuation_session = (
                    exit_session
                    if requirement.event_kind in {"stock_merger", "mixed_merger"}
                    else requirement.terminal_session
                )
                payoff = payoff_by_key.get(
                    (requirement.requirement_id, valuation_session)
                )
                if payoff is None:
                    refusals.append(
                        _refusal(decision, horizon, "missing_terminal_shareholder_payoff")
                    )
                    continue
                if payoff.total_return_series_id != entry_security.total_return_series_id:
                    raise EventStudyInputError(
                        "validated terminal return-series lineage changed after preflight"
                    )
                exit_security_value = payoff.terminal_total_return_index_value
                exit_listing_id = payoff.valuation_listing_id
                exit_ticker = payoff.valuation_historical_ticker
                exit_source_sha256 = payoff.source_sha256
                terminal_used = True
                terminal_requirement_id = requirement.requirement_id
                terminal_event_kind = requirement.event_kind
                terminal_session = requirement.terminal_session
                terminal_listing_id = requirement.terminal_listing_id
                terminal_historical_ticker = requirement.terminal_historical_ticker
                valuation_security_id = payoff.valuation_security_id
                successor_security_id = requirement.successor_security_id
                successor_listing_id = requirement.successor_listing_id
                successor_historical_ticker = (
                    requirement.successor_historical_ticker
                )
            else:
                exit_security = security_by_key.get((decision.security_id, exit_session))
                if exit_security is None:
                    refusals.append(
                        _refusal(decision, horizon, "missing_security_exit_open")
                    )
                    continue
                if (
                    exit_security.total_return_series_id
                    != entry_security.total_return_series_id
                    or exit_security.value_basis != entry_security.value_basis
                ):
                    raise EventStudyInputError(
                        "validated security return-series lineage changed after preflight"
                    )
                exit_security_value = exit_security.total_return_open_value
                exit_listing_id = exit_security.listing_id
                exit_ticker = exit_security.historical_ticker
                exit_source_sha256 = exit_security.source_sha256

            security_return, benchmark_return, excess_return = _returns(
                entry_security=entry_security.total_return_open_value,
                exit_security=exit_security_value,
                entry_benchmark=entry_benchmark.total_return_open_value,
                exit_benchmark=exit_benchmark.total_return_open_value,
            )
            observations.append(
                EventStudyObservation(
                    row_id=decision.row_id,
                    decision_session=decision.decision_session,
                    exit_session=exit_session,
                    horizon_sessions=horizon,
                    security_id=decision.security_id,
                    entry_listing_id=decision.listing_id,
                    entry_historical_ticker=decision.historical_ticker,
                    exit_listing_id=exit_listing_id,
                    exit_historical_ticker=exit_ticker,
                    evaluation_segment_id=decision.evaluation_segment_id,
                    fold_id=decision.fold_id,
                    common_event_component_id=decision.common_event_component_id,
                    firm_specific_score=decision.firm_specific_score,
                    global_score=decision.global_score,
                    security_total_return=security_return,
                    benchmark_total_return=benchmark_return,
                    excess_total_return=excess_return,
                    security_entry_total_return_index_value=(
                        entry_security.total_return_open_value
                    ),
                    security_exit_total_return_index_value=exit_security_value,
                    benchmark_entry_total_return_index_value=(
                        entry_benchmark.total_return_open_value
                    ),
                    benchmark_exit_total_return_index_value=(
                        exit_benchmark.total_return_open_value
                    ),
                    terminal_payoff_used=terminal_used,
                    terminal_requirement_id=terminal_requirement_id,
                    terminal_event_kind=terminal_event_kind,
                    terminal_session=terminal_session,
                    terminal_listing_id=terminal_listing_id,
                    terminal_historical_ticker=terminal_historical_ticker,
                    valuation_session=valuation_session,
                    valuation_security_id=valuation_security_id,
                    successor_security_id=successor_security_id,
                    successor_listing_id=successor_listing_id,
                    successor_historical_ticker=successor_historical_ticker,
                    decision_input_sha256=decision.input_row_sha256,
                    security_entry_source_sha256=entry_security.source_sha256,
                    security_exit_source_sha256=exit_source_sha256,
                    benchmark_entry_source_sha256=entry_benchmark.source_sha256,
                    benchmark_exit_source_sha256=exit_benchmark.source_sha256,
                    security_total_return_series_id=(
                        entry_security.total_return_series_id
                    ),
                    benchmark_total_return_series_id=(
                        entry_benchmark.total_return_series_id
                    ),
                    total_return_value_basis=entry_security.value_basis,
                )
            )

    expected = len(decisions) * len(HORIZONS)
    if len(observations) + len(refusals) != expected:
        raise EventStudyInputError("decision/horizon census is not exhaustive")
    frozen_observations = tuple(observations)
    frozen_refusals = tuple(refusals)
    frozen_security_lifecycle_coverages = tuple(security_lifecycle_coverages)
    batch_hash = _batch_hash(
        candidate_hash=run_candidate.candidate_hash,
        partition_set_sha256=partition_set_sha256,
        observations=frozen_observations,
        refusals=frozen_refusals,
        security_lifecycle_coverages=frozen_security_lifecycle_coverages,
        expected=expected,
    )
    batch = EventStudyBatch(
        observations=frozen_observations,
        refusals=frozen_refusals,
        security_lifecycle_coverages=frozen_security_lifecycle_coverages,
        expected_decision_horizons=expected,
        candidate_declaration_hash=run_candidate.candidate_hash,
        input_partition_set_sha256=partition_set_sha256,
        batch_hash=batch_hash,
    )
    return require_synthetic_event_study_batch(batch)
