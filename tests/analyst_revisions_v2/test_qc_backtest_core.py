"""Synthetic validation for the first Analyst V2 QC backtest code slice."""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from datetime import date
from decimal import (
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    Underflow,
    localcontext,
)
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2.import_firewall import (
    DEFAULT_FORBIDDEN_IMPORT_PREFIXES,
    ImportBoundaryError,
    _validate_import_closure,
)
from research.analyst_revisions_v2_qc.event_study import (
    BENCHMARK_LISTING_ID,
    BENCHMARK_SECURITY_ID,
    BENCHMARK_TICKER,
    BENCHMARK_TOTAL_RETURN_SERIES_ID,
    HORIZONS,
    SYNTHETIC_LIFECYCLE_SOURCE,
    SYNTHETIC_OPEN_SOURCE,
    SYNTHETIC_TERMINAL_SOURCE,
    SYNTHETIC_TERMINAL_VALUE_BASIS,
    SYNTHETIC_TOTAL_RETURN_VALUE_BASIS,
    BenchmarkOpenValue,
    DecisionRow,
    EventStudyBatch,
    EventStudyInputError,
    SecurityLifecycleCoverage,
    SecurityOpenValue,
    TerminalLifecycle,
    TerminalRequirement,
    TerminalShareholderPayoff,
    _batch_hash,
    build_synthetic_partition_binding,
    collect_synthetic_event_study,
    require_synthetic_event_study_batch,
)
from research.analyst_revisions_v2_qc import event_study as event_study_module
from research.analyst_revisions_v2_qc import run_contract as run_contract_module
from research.analyst_revisions_v2_qc.run_contract import (
    EVALUATION_WINDOWS,
    PARENT_ARTIFACTS,
    CodeFileBinding,
    QcRunContractError,
    SyntheticPartitionBinding,
    SyntheticQcRunCandidate,
    TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID,
    build_synthetic_qc_run_candidate,
    canonical_lf_python_source_bytes,
    commit_identity_shape_is_valid,
    require_synthetic_qc_run_candidate,
)


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "research" / "analyst_revisions_v2_qc" / "event_study.py"
CONTRACT = ROOT / "research" / "analyst_revisions_v2_qc" / "run_contract.py"


def _sha(character: str) -> str:
    return character * 64


@lru_cache(maxsize=1)
def _sessions() -> tuple[date, ...]:
    values = trading_sessions(date(2013, 1, 2), date(2026, 8, 28))
    assert len(values) == 3435
    return values


def _decision_index(session: date | None = None) -> int:
    return _sessions().index(date(2021, 3, 31) if session is None else session)


def _decision(
    *,
    row_id: str = "row-1",
    session: date | None = None,
    security_id: str = "security-1",
    listing_id: str = "listing-1",
    ticker: str = "AAA",
    component: str = "component-1",
    evaluation_segment_id: str = "arv2-wf-test-2021",
    fold_id: str | None = "arv2-wf-test-2021",
) -> DecisionRow:
    return DecisionRow(
        row_id=row_id,
        decision_session=date(2021, 3, 31) if session is None else session,
        security_id=security_id,
        listing_id=listing_id,
        historical_ticker=ticker,
        evaluation_segment_id=evaluation_segment_id,
        fold_id=fold_id,
        firm_specific_score=Decimal("1.25"),
        global_score=Decimal("0.75"),
        common_event_component_id=component,
        input_row_sha256=_sha("a"),
    )


def _security_open(
    session: date,
    value: str,
    *,
    security_id: str = "security-1",
    listing_id: str = "listing-1",
    ticker: str = "AAA",
    source_role: str = SYNTHETIC_OPEN_SOURCE,
    source_sha256: str = _sha("b"),
    total_return_series_id: str = "security-1-total-return-series",
    value_basis: str = SYNTHETIC_TOTAL_RETURN_VALUE_BASIS,
) -> SecurityOpenValue:
    return SecurityOpenValue(
        session=session,
        security_id=security_id,
        listing_id=listing_id,
        historical_ticker=ticker,
        total_return_open_value=Decimal(value),
        total_return_series_id=total_return_series_id,
        value_basis=value_basis,
        source_role=source_role,
        source_sha256=source_sha256,
    )


def _benchmark_open(session: date, value: str = "100") -> BenchmarkOpenValue:
    return BenchmarkOpenValue(
        session=session,
        security_id=BENCHMARK_SECURITY_ID,
        listing_id=BENCHMARK_LISTING_ID,
        historical_ticker=BENCHMARK_TICKER,
        total_return_open_value=Decimal(value),
        total_return_series_id=BENCHMARK_TOTAL_RETURN_SERIES_ID,
        value_basis=SYNTHETIC_TOTAL_RETURN_VALUE_BASIS,
        source_role=SYNTHETIC_OPEN_SOURCE,
        source_sha256=_sha("c"),
    )


def _terminal_requirement(
    *,
    session: date | None = None,
    decision_row_id: str = "row-1",
    requirement_id: str = "terminal-1",
    security_id: str = "security-1",
    terminal_listing_id: str = "listing-terminal",
    terminal_ticker: str = "AAB",
    total_return_series_id: str = "security-1-total-return-series",
    event_kind: str = "bankruptcy",
    successor_security_id: str | None = None,
    successor_listing_id: str | None = None,
    successor_historical_ticker: str | None = None,
) -> TerminalRequirement:
    return TerminalRequirement(
        decision_row_id=decision_row_id,
        security_id=security_id,
        terminal_listing_id=terminal_listing_id,
        terminal_historical_ticker=terminal_ticker,
        terminal_session=(
            _sessions()[_decision_index() + 10] if session is None else session
        ),
        requirement_id=requirement_id,
        event_kind=event_kind,
        successor_security_id=successor_security_id,
        successor_listing_id=successor_listing_id,
        successor_historical_ticker=successor_historical_ticker,
        total_return_series_id=total_return_series_id,
    )


def _terminal_payoff(
    requirement: TerminalRequirement,
    *,
    value: str = "0",
    source_role: str = SYNTHETIC_TERMINAL_SOURCE,
    valuation_session: date | None = None,
    valuation_ticker: str | None = None,
) -> TerminalShareholderPayoff:
    is_stock = requirement.event_kind in {"stock_merger", "mixed_merger"}
    valuation_security_id = (
        requirement.successor_security_id if is_stock else requirement.security_id
    )
    valuation_listing_id = (
        requirement.successor_listing_id
        if is_stock
        else requirement.terminal_listing_id
    )
    return TerminalShareholderPayoff(
        decision_row_id=requirement.decision_row_id,
        security_id=requirement.security_id,
        terminal_listing_id=requirement.terminal_listing_id,
        terminal_historical_ticker=requirement.terminal_historical_ticker,
        terminal_session=requirement.terminal_session,
        valuation_session=(
            requirement.terminal_session
            if valuation_session is None
            else valuation_session
        ),
        valuation_security_id=valuation_security_id,
        valuation_listing_id=valuation_listing_id,
        valuation_historical_ticker=(
            valuation_ticker
            if valuation_ticker is not None
            else (
                requirement.successor_historical_ticker
                if is_stock
                else requirement.terminal_historical_ticker
            )
        ),
        terminal_total_return_index_value=Decimal(value),
        total_return_series_id=requirement.total_return_series_id,
        value_basis=SYNTHETIC_TERMINAL_VALUE_BASIS,
        requirement_id=requirement.requirement_id,
        event_kind=requirement.event_kind,
        successor_security_id=requirement.successor_security_id,
        successor_listing_id=requirement.successor_listing_id,
        successor_historical_ticker=requirement.successor_historical_ticker,
        source_role=source_role,
        source_sha256=_sha("d"),
    )


def _lifecycle_coverages(
    decisions: tuple[DecisionRow, ...],
    terminal_requirements: tuple[TerminalRequirement, ...],
) -> tuple[SecurityLifecycleCoverage, ...]:
    terminal_by_security: dict[str, TerminalLifecycle] = {}
    referenced = {item.security_id for item in decisions}
    for requirement in terminal_requirements:
        lifecycle = event_study_module._terminal_lifecycle_from_requirement(
            requirement
        )
        terminal_by_security.setdefault(requirement.security_id, lifecycle)
        if requirement.successor_security_id is not None:
            referenced.add(requirement.successor_security_id)
    return tuple(
        SecurityLifecycleCoverage(
            security_id=security_id,
            observed_through_session=date(2026, 8, 28),
            terminal_lifecycle=terminal_by_security.get(security_id),
            source_role=SYNTHETIC_LIFECYCLE_SOURCE,
            source_sha256=_sha("e"),
        )
        for security_id in sorted(referenced)
    )


def _complete_price_fixture() -> tuple[
    tuple[date, ...], tuple[SecurityOpenValue, ...], tuple[BenchmarkOpenValue, ...]
]:
    sessions = _sessions()
    entry_index = _decision_index()
    exit_values = {1: "101", 5: "105", 20: "120", 60: "160"}
    security = [_security_open(sessions[entry_index], "100")]
    security.extend(
        _security_open(sessions[entry_index + horizon], value)
        for horizon, value in exit_values.items()
    )
    benchmark = [_benchmark_open(sessions[entry_index])]
    benchmark.extend(
        _benchmark_open(sessions[entry_index + horizon]) for horizon in HORIZONS
    )
    benchmark.append(_benchmark_open(sessions[entry_index + 10]))
    benchmark.sort(key=lambda item: item.session)
    return sessions, tuple(security), tuple(benchmark)


def _two_security_fixture() -> tuple[
    tuple[DecisionRow, ...],
    tuple[SecurityOpenValue, ...],
    tuple[BenchmarkOpenValue, ...],
]:
    _, first_security, benchmarks = _complete_price_fixture()
    second_decision = _decision(
        row_id="row-2",
        security_id="security-2",
        listing_id="listing-2",
        ticker="BBB",
        component="component-2",
    )
    second_security = tuple(
        dataclasses.replace(
            item,
            security_id="security-2",
            listing_id="listing-2",
            historical_ticker="BBB",
            total_return_series_id="security-2-total-return-series",
        )
        for item in first_security
    )
    return (
        (_decision(), second_decision),
        (*first_security, *second_security),
        benchmarks,
    )


def _staggered_two_security_fixture(second_offset: int) -> tuple[
    tuple[DecisionRow, ...],
    tuple[SecurityOpenValue, ...],
    tuple[BenchmarkOpenValue, ...],
]:
    sessions = _sessions()
    first_index = _decision_index()
    second_index = first_index + second_offset
    decisions = (
        _decision(),
        _decision(
            row_id="row-2",
            session=sessions[second_index],
            security_id="security-2",
            listing_id="listing-2",
            ticker="BBB",
            component="component-2",
        ),
    )
    securities = []
    benchmark_sessions = set()
    for decision, entry_index, value_prefix in (
        (decisions[0], first_index, 100),
        (decisions[1], second_index, 200),
    ):
        series_id = f"{decision.security_id}-total-return-series"
        for offset in (0, *HORIZONS):
            session = sessions[entry_index + offset]
            benchmark_sessions.add(session)
            securities.append(
                _security_open(
                    session,
                    str(value_prefix + offset),
                    security_id=decision.security_id,
                    listing_id=decision.listing_id,
                    ticker=decision.historical_ticker,
                    total_return_series_id=series_id,
                )
            )
    return (
        decisions,
        tuple(securities),
        tuple(_benchmark_open(session) for session in sorted(benchmark_sessions)),
    )


def _covered_stock_merger_fixture(event_kind: str = "stock_merger"):
    sessions, security, benchmarks = _complete_price_fixture()
    entry = _decision_index()
    predecessor = _terminal_requirement(
        event_kind=event_kind,
        successor_security_id="successor",
        successor_listing_id="successor-listing",
        successor_historical_ticker="BBB",
    )
    payoffs = (
        _terminal_payoff(
            predecessor,
            value="130",
            valuation_session=sessions[entry + 20],
            valuation_ticker="BBB",
        ),
        _terminal_payoff(
            predecessor,
            value="150",
            valuation_session=sessions[entry + 60],
            valuation_ticker="BBB",
        ),
    )
    return (
        (_decision(),),
        security,
        benchmarks,
        (predecessor,),
        payoffs,
    )


def _code_binding() -> CodeFileBinding:
    payload = canonical_lf_python_source_bytes(CORE.read_bytes())
    return CodeFileBinding(
        role="event_study_core",
        relative_path="research/analyst_revisions_v2_qc/event_study.py",
        upload_name="event_study.py",
        byte_count=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _partition_bindings(
    *,
    sessions: tuple[date, ...],
    decisions: tuple[DecisionRow, ...],
    security_opens: tuple[SecurityOpenValue, ...],
    benchmark_opens: tuple[BenchmarkOpenValue, ...],
    security_lifecycle_coverages: tuple[SecurityLifecycleCoverage, ...],
    terminal_requirements: tuple[TerminalRequirement, ...],
    terminal_payoffs: tuple[TerminalShareholderPayoff, ...],
) -> tuple[SyntheticPartitionBinding, ...]:
    rows_by_role = (
        ("session_axis", sessions),
        ("decision_rows", decisions),
        ("security_open_values", security_opens),
        ("benchmark_open_values", benchmark_opens),
        ("security_lifecycle_coverages", security_lifecycle_coverages),
        ("terminal_requirements", terminal_requirements),
        ("terminal_shareholder_payoffs", terminal_payoffs),
    )
    return tuple(
        build_synthetic_partition_binding(
            role=role,
            partition_id=f"fixture/{index:02d}-{role}.jsonl",
            rows=rows,
        )
        for index, (role, rows) in enumerate(rows_by_role, start=1)
    )


def _candidate_for(
    *,
    sessions: tuple[date, ...],
    decisions: tuple[DecisionRow, ...],
    security_opens: tuple[SecurityOpenValue, ...],
    benchmark_opens: tuple[BenchmarkOpenValue, ...],
    security_lifecycle_coverages: tuple[SecurityLifecycleCoverage, ...],
    terminal_requirements: tuple[TerminalRequirement, ...],
    terminal_payoffs: tuple[TerminalShareholderPayoff, ...],
) -> SyntheticQcRunCandidate:
    return build_synthetic_qc_run_candidate(
        code_files=(_code_binding(),),
        synthetic_partitions=_partition_bindings(
            sessions=sessions,
            decisions=decisions,
            security_opens=security_opens,
            benchmark_opens=benchmark_opens,
            security_lifecycle_coverages=security_lifecycle_coverages,
            terminal_requirements=terminal_requirements,
            terminal_payoffs=terminal_payoffs,
        ),
    )


def _candidate() -> SyntheticQcRunCandidate:
    sessions, securities, benchmarks = _complete_price_fixture()
    decisions = (_decision(),)
    coverages = _lifecycle_coverages(decisions, ())
    return _candidate_for(
        sessions=sessions,
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
        security_lifecycle_coverages=coverages,
        terminal_requirements=(),
        terminal_payoffs=(),
    )


def _collect(
    *,
    session_axis: tuple[date, ...] | None = None,
    decisions: tuple[DecisionRow, ...] | None = None,
    security_opens: tuple[SecurityOpenValue, ...] | None = None,
    benchmark_opens: tuple[BenchmarkOpenValue, ...] | None = None,
    security_lifecycle_coverages: tuple[SecurityLifecycleCoverage, ...] | None = None,
    terminal_requirements: tuple[TerminalRequirement, ...] = (),
    terminal_payoffs: tuple[TerminalShareholderPayoff, ...] = (),
    run_candidate: SyntheticQcRunCandidate | None = None,
):
    sessions, securities, benchmarks = _complete_price_fixture()
    sessions = sessions if session_axis is None else session_axis
    decisions = (_decision(),) if decisions is None else decisions
    securities = securities if security_opens is None else security_opens
    benchmarks = benchmarks if benchmark_opens is None else benchmark_opens
    coverages = (
        _lifecycle_coverages(decisions, terminal_requirements)
        if security_lifecycle_coverages is None
        else security_lifecycle_coverages
    )
    candidate = run_candidate or _candidate_for(
        sessions=sessions,
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
        security_lifecycle_coverages=coverages,
        terminal_requirements=terminal_requirements,
        terminal_payoffs=terminal_payoffs,
    )
    return collect_synthetic_event_study(
        run_candidate=candidate,
        session_axis=sessions,
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
        security_lifecycle_coverages=coverages,
        terminal_requirements=terminal_requirements,
        terminal_payoffs=terminal_payoffs,
    )


def _self_rehash(
    batch: EventStudyBatch,
    *,
    observations=None,
    refusals=None,
    security_lifecycle_coverages=None,
    expected=None,
) -> EventStudyBatch:
    observations = batch.observations if observations is None else observations
    refusals = batch.refusals if refusals is None else refusals
    security_lifecycle_coverages = (
        batch.security_lifecycle_coverages
        if security_lifecycle_coverages is None
        else security_lifecycle_coverages
    )
    expected = (
        batch.expected_decision_horizons if expected is None else expected
    )
    digest = _batch_hash(
        candidate_hash=batch.candidate_declaration_hash,
        terminal_payoff_reinvestment_policy_id=(
            batch.terminal_payoff_reinvestment_policy_id
        ),
        partition_set_sha256=batch.input_partition_set_sha256,
        observations=observations,
        refusals=refusals,
        security_lifecycle_coverages=security_lifecycle_coverages,
        expected=expected,
    )
    return dataclasses.replace(
        batch,
        observations=observations,
        refusals=refusals,
        security_lifecycle_coverages=security_lifecycle_coverages,
        expected_decision_horizons=expected,
        batch_hash=digest,
    )


def test_kernel_uses_xnys_session_horizons_and_exact_decimal_returns():
    batch = _collect()
    assert not batch.refusals
    assert [item.horizon_sessions for item in batch.observations] == list(HORIZONS)
    entry = _decision_index()
    assert [item.exit_session for item in batch.observations] == [
        _sessions()[entry + index] for index in HORIZONS
    ]
    assert [item.security_total_return for item in batch.observations] == [
        Decimal("0.01"), Decimal("0.05"), Decimal("0.2"), Decimal("0.6")
    ]
    assert all(item.benchmark_total_return == 0 for item in batch.observations)
    assert all(
        item.excess_total_return == item.security_total_return
        for item in batch.observations
    )


def test_decimal_results_and_batch_identity_ignore_ambient_context():
    with localcontext() as context:
        context.prec = 5
        low_precision = _collect()
    with localcontext() as context:
        context.prec = 50
        high_precision = _collect()
    assert low_precision.observations == high_precision.observations
    assert low_precision.batch_hash == high_precision.batch_hash
    _, securities, benchmarks = _complete_price_fixture()
    nonterminating = (
        dataclasses.replace(securities[0], total_return_open_value=Decimal("3")),
        *securities[1:],
    )
    moving_benchmarks = (
        benchmarks[0],
        dataclasses.replace(
            benchmarks[1], total_return_open_value=Decimal("103")
        ),
        *benchmarks[2:],
    )
    with localcontext() as context:
        context.traps[Inexact] = True
        trapped_caller = _collect(
            security_opens=nonterminating, benchmark_opens=moving_benchmarks
        )
    h1 = trapped_caller.observations[0]
    assert h1.security_total_return == Decimal(
        "32.666666666666666666666666666666666666666666666667"
    )
    assert h1.benchmark_total_return == Decimal("0.03")
    assert h1.excess_total_return == Decimal(
        "32.636666666666666666666666666666666666666666666667"
    )


def test_arithmetic_context_is_fresh_and_cannot_be_mutated_globally():
    first = event_study_module._fresh_arithmetic_context()
    first.prec = 2
    first.traps[Inexact] = True
    second = event_study_module._fresh_arithmetic_context()
    assert second is not first
    assert second.prec == 50
    assert second.traps[Inexact] is False
    assert all(
        second.traps[signal]
        for signal in (DivisionByZero, InvalidOperation, Overflow, Underflow)
    )


def test_source_role_preflight_never_executes_string_subclass_comparisons():
    calls = []

    class HostileSourceRole(str):
        def __eq__(self, other):
            calls.append(("eq", other))
            raise AssertionError("hostile equality executed")

        def __ne__(self, other):
            calls.append(("ne", other))
            raise AssertionError("hostile inequality executed")

    hostile = HostileSourceRole(SYNTHETIC_OPEN_SOURCE)
    requirement = _terminal_requirement()
    cases = (
        (
            event_study_module._validate_security_open,
            dataclasses.replace(
                _security_open(_sessions()[_decision_index()], "100"),
                source_role=hostile,
            ),
        ),
        (
            event_study_module._validate_benchmark_open,
            dataclasses.replace(
                _benchmark_open(_sessions()[_decision_index()]),
                source_role=hostile,
            ),
        ),
        (
            event_study_module._validate_terminal_payoff,
            dataclasses.replace(
                _terminal_payoff(requirement),
                source_role=HostileSourceRole(SYNTHETIC_TERMINAL_SOURCE),
            ),
        ),
        (
            event_study_module._validate_security_lifecycle_coverage,
            dataclasses.replace(
                _lifecycle_coverages((_decision(),), ())[0],
                source_role=HostileSourceRole(SYNTHETIC_LIFECYCLE_SOURCE),
            ),
        ),
    )
    for validator, value in cases:
        with pytest.raises(EventStudyInputError, match="canonical string"):
            validator(value)
    assert calls == []


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        (
            {"observed_through_session": date(2026, 8, 27)},
            "incomplete before the reviewed cutoff",
        ),
        ({"source_role": "production-lifecycle"}, "production.*not enabled"),
        ({"source_sha256": "bad"}, "lowercase SHA-256"),
    ),
)
def test_lifecycle_coverage_requires_complete_synthetic_evidence(changes, message):
    coverage = _lifecycle_coverages((_decision(),), ())[0]
    with pytest.raises(EventStudyInputError, match=message):
        event_study_module._validate_security_lifecycle_coverage(
            dataclasses.replace(coverage, **changes)
        )

    requirement = _terminal_requirement()
    terminal_coverage = _lifecycle_coverages((_decision(),), (requirement,))[0]
    mismatched = dataclasses.replace(terminal_coverage, security_id="security-2")
    with pytest.raises(EventStudyInputError, match="permanent-security identity"):
        event_study_module._validate_security_lifecycle_coverage(mismatched)


def test_lifecycle_coverage_inventory_is_canonical_unique_and_exact():
    sessions, securities, benchmarks = _complete_price_fixture()
    decisions, _, _ = _two_security_fixture()
    coverages = _lifecycle_coverages(decisions, ())

    def direct_collect(candidate_coverages):
        return collect_synthetic_event_study(
            run_candidate=_candidate(),
            session_axis=sessions,
            decisions=(_decision(),),
            security_opens=securities,
            benchmark_opens=benchmarks,
            security_lifecycle_coverages=candidate_coverages,
            terminal_requirements=(),
            terminal_payoffs=(),
        )

    with pytest.raises(EventStudyInputError, match="exact SecurityLifecycleCoverage"):
        direct_collect((object(),))

    calls = []

    class HostileSecurityId(str):
        def __lt__(self, other):
            calls.append(("lt", other))
            raise AssertionError("hostile comparison executed")

    hostile = dataclasses.replace(
        _lifecycle_coverages((_decision(),), ())[0],
        security_id=HostileSecurityId("security-1"),
    )
    with pytest.raises(EventStudyInputError, match="canonical string"):
        direct_collect((hostile,))
    assert calls == []

    with pytest.raises(EventStudyInputError, match="canonical order"):
        _collect(decisions=decisions, security_lifecycle_coverages=tuple(reversed(coverages)))
    with pytest.raises(EventStudyInputError, match="keys must be unique"):
        _collect(
            decisions=decisions,
            security_lifecycle_coverages=(coverages[0], coverages[0]),
        )
    unrelated = SecurityLifecycleCoverage(
        security_id="security-9",
        observed_through_session=date(2026, 8, 28),
        terminal_lifecycle=None,
        source_role=SYNTHETIC_LIFECYCLE_SOURCE,
        source_sha256=_sha("e"),
    )
    with pytest.raises(EventStudyInputError, match="unrelated securities"):
        _collect(
            decisions=decisions,
            security_lifecycle_coverages=tuple(
                sorted((*coverages, unrelated), key=lambda item: item.security_id)
            ),
        )


def test_terminal_payoff_replaces_only_horizons_reaching_terminal_session():
    requirement = _terminal_requirement()
    payoff = _terminal_payoff(requirement)
    batch = _collect(
        terminal_requirements=(requirement,), terminal_payoffs=(payoff,)
    )
    assert not batch.refusals
    by_horizon = {item.horizon_sessions: item for item in batch.observations}
    assert by_horizon[1].terminal_payoff_used is False
    assert by_horizon[5].terminal_payoff_used is False
    assert by_horizon[20].terminal_payoff_used is True
    assert by_horizon[60].terminal_payoff_used is True
    assert by_horizon[20].security_total_return == Decimal("-1")
    assert by_horizon[20].security_exit_source_sha256 == _sha("d")
    assert by_horizon[20].terminal_requirement_id == requirement.requirement_id
    assert by_horizon[20].terminal_event_kind == "bankruptcy"
    assert by_horizon[20].terminal_session == requirement.terminal_session
    assert by_horizon[20].valuation_session == requirement.terminal_session
    assert by_horizon[20].common_event_component_id == "component-1"


@pytest.mark.parametrize("event_kind", ["bankruptcy", "cash_merger", "delisting"])
def test_final_terminal_payoff_is_reinvested_in_spy_to_each_fixed_horizon(
    event_kind,
):
    sessions, securities, benchmarks = _complete_price_fixture()
    entry = _decision_index()
    terminal_session = sessions[entry + 10]
    merger_fields = (
        {
            "successor_security_id": "successor",
            "successor_listing_id": "successor-listing",
            "successor_historical_ticker": "BBB",
        }
        if event_kind == "cash_merger"
        else {}
    )
    requirement = _terminal_requirement(
        session=terminal_session,
        event_kind=event_kind,
        **merger_fields,
    )
    payoff = _terminal_payoff(requirement, value="80")
    values = {
        sessions[entry]: Decimal("100"),
        terminal_session: Decimal("80"),
        sessions[entry + 20]: Decimal("120"),
        sessions[entry + 60]: Decimal("160"),
    }
    moving_benchmarks = tuple(
        dataclasses.replace(
            item,
            total_return_open_value=values.get(
                item.session, item.total_return_open_value
            ),
        )
        for item in benchmarks
    )
    batch = _collect(
        security_opens=securities,
        benchmark_opens=moving_benchmarks,
        terminal_requirements=(requirement,),
        terminal_payoffs=(payoff,),
    )
    assert not batch.refusals
    terminal = {
        item.horizon_sessions: item
        for item in batch.observations
        if item.terminal_payoff_used
    }
    assert terminal.keys() == {20, 60}
    assert [terminal[h].security_exit_total_return_index_value for h in (20, 60)] == [
        Decimal("80"),
        Decimal("80"),
    ]
    assert [
        terminal[h].benchmark_valuation_total_return_index_value for h in (20, 60)
    ] == [Decimal("80"), Decimal("80")]
    assert [terminal[h].security_total_return for h in (20, 60)] == [
        Decimal("0.2"),
        Decimal("0.6"),
    ]
    assert [terminal[h].benchmark_total_return for h in (20, 60)] == [
        Decimal("0.2"),
        Decimal("0.6"),
    ]
    assert all(item.excess_total_return == 0 for item in terminal.values())


def test_terminal_at_horizon_has_unit_continuation_and_later_horizon_splices():
    sessions, securities, benchmarks = _complete_price_fixture()
    entry = _decision_index()
    terminal_session = sessions[entry + 20]
    requirement = _terminal_requirement(
        session=terminal_session, event_kind="delisting"
    )
    payoff = _terminal_payoff(requirement, value="90")
    values = {
        terminal_session: Decimal("120"),
        sessions[entry + 60]: Decimal("180"),
    }
    moving_benchmarks = tuple(
        dataclasses.replace(
            item,
            total_return_open_value=values.get(
                item.session, item.total_return_open_value
            ),
        )
        for item in benchmarks
    )
    batch = _collect(
        security_opens=securities,
        benchmark_opens=moving_benchmarks,
        terminal_requirements=(requirement,),
        terminal_payoffs=(payoff,),
    )
    terminal = {
        item.horizon_sessions: item
        for item in batch.observations
        if item.terminal_payoff_used
    }
    assert terminal[20].valuation_session == terminal[20].exit_session
    assert terminal[20].security_total_return == Decimal("-0.1")
    assert terminal[60].security_total_return == Decimal("0.35")
    assert terminal[20].security_exit_total_return_index_value == Decimal("90")
    assert terminal[60].security_exit_total_return_index_value == Decimal("90")


def test_missing_horizon_benchmark_conflicts_with_later_splice_valuation_proof():
    sessions = _sessions()
    terminal_session = sessions[_decision_index() + 20]
    requirement = _terminal_requirement(
        session=terminal_session, event_kind="delisting"
    )
    batch = _collect(
        terminal_requirements=(requirement,),
        terminal_payoffs=(_terminal_payoff(requirement, value="90"),),
    )
    retained = tuple(
        item for item in batch.observations if item.horizon_sessions != 20
    )
    missing_exit = event_study_module._refusal(
        _decision(), 20, "missing_benchmark_exit_open"
    )
    rebuilt = _self_rehash(
        batch,
        observations=retained,
        refusals=(missing_exit,),
    )
    with pytest.raises(EventStudyInputError, match="benchmark exit availability"):
        require_synthetic_event_study_batch(rebuilt)


def test_missing_terminal_benchmark_valuation_is_named_and_exhaustive():
    sessions, securities, benchmarks = _complete_price_fixture()
    terminal_session = sessions[_decision_index() + 10]
    requirement = _terminal_requirement(session=terminal_session)
    without_terminal_benchmark = tuple(
        item for item in benchmarks if item.session != terminal_session
    )
    batch = _collect(
        security_opens=securities,
        benchmark_opens=without_terminal_benchmark,
        terminal_requirements=(requirement,),
        terminal_payoffs=(_terminal_payoff(requirement, value="50"),),
    )
    assert [(item.horizon_sessions, item.reason) for item in batch.refusals] == [
        (20, "missing_benchmark_valuation_open"),
        (60, "missing_benchmark_valuation_open"),
    ]
    assert [item.horizon_sessions for item in batch.observations] == [1, 5]
    assert batch.expected_decision_horizons == 4


def test_missing_terminal_benchmark_claim_conflicts_with_a_shared_proven_fact():
    decisions, securities, benchmarks = _two_security_fixture()
    first = _terminal_requirement()
    second = _terminal_requirement(
        decision_row_id="row-2",
        requirement_id="terminal-2",
        security_id="security-2",
        terminal_listing_id="listing-2-terminal",
        terminal_ticker="BBC",
        total_return_series_id="security-2-total-return-series",
    )
    complete = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
        terminal_requirements=(first, second),
        terminal_payoffs=(
            _terminal_payoff(first, value="50"),
            _terminal_payoff(second, value="50"),
        ),
    )
    retained = tuple(
        item
        for item in complete.observations
        if not (item.row_id == "row-2" and item.terminal_payoff_used)
    )
    forged_refusals = tuple(
        event_study_module._refusal(
            decisions[1], horizon, "missing_benchmark_valuation_open"
        )
        for horizon in (20, 60)
    )
    forged = _self_rehash(
        complete,
        observations=retained,
        refusals=forged_refusals,
    )
    with pytest.raises(EventStudyInputError, match="valuation availability changed"):
        require_synthetic_event_study_batch(forged)


def test_terminal_benchmark_value_source_and_policy_are_revalidated():
    requirement = _terminal_requirement(event_kind="delisting")
    batch = _collect(
        terminal_requirements=(requirement,),
        terminal_payoffs=(_terminal_payoff(requirement, value="50"),),
    )
    h20 = next(
        item for item in batch.observations if item.horizon_sessions == 20
    )
    for changed, message in (
        (
            dataclasses.replace(
                h20,
                benchmark_valuation_total_return_index_value=Decimal("0"),
            ),
            "positive finite Decimal",
        ),
        (
            dataclasses.replace(h20, benchmark_valuation_source_sha256="bad"),
            "lowercase SHA-256",
        ),
    ):
        with pytest.raises(EventStudyInputError, match=message):
            require_synthetic_event_study_batch(
                _self_rehash(
                    batch,
                    observations=tuple(
                        changed if item is h20 else item
                        for item in batch.observations
                    ),
                )
            )

    changed_value = dataclasses.replace(
        h20,
        benchmark_valuation_total_return_index_value=Decimal("101"),
    )
    with pytest.raises(EventStudyInputError, match="return arithmetic"):
        require_synthetic_event_study_batch(
            _self_rehash(
                batch,
                observations=tuple(
                    changed_value if item is h20 else item
                    for item in batch.observations
                ),
            )
        )

    changed_source = dataclasses.replace(
        h20,
        benchmark_valuation_source_sha256=_sha("f"),
    )
    with pytest.raises(
        EventStudyInputError,
        match="final terminal payoff changed|benchmark value/source fact changed",
    ):
        require_synthetic_event_study_batch(
            _self_rehash(
                batch,
                observations=tuple(
                    changed_source if item is h20 else item
                    for item in batch.observations
                ),
            )
        )

    object.__setattr__(
        batch,
        "terminal_payoff_reinvestment_policy_id",
        "arv2-terminal-payoff-benchmark-splice-v2",
    )
    with pytest.raises(EventStudyInputError, match="reinvestment policy changed"):
        require_synthetic_event_study_batch(batch)


@pytest.mark.parametrize("event_kind", ["stock_merger", "mixed_merger"])
def test_successor_valued_mergers_do_not_add_a_post_terminal_splice(event_kind):
    decisions, securities, benchmarks, requirements, payoffs = (
        _covered_stock_merger_fixture(event_kind)
    )
    batch = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
        terminal_requirements=requirements,
        terminal_payoffs=payoffs,
    )
    terminal = [item for item in batch.observations if item.terminal_payoff_used]
    assert [item.security_total_return for item in terminal] == [
        Decimal("0.3"),
        Decimal("0.5"),
    ]
    assert all(item.valuation_session == item.exit_session for item in terminal)
    assert all(
        item.benchmark_valuation_total_return_index_value
        == item.benchmark_exit_total_return_index_value
        for item in terminal
    )
    assert all(
        item.benchmark_valuation_source_sha256
        == item.benchmark_exit_source_sha256
        for item in terminal
    )


def test_positive_terminal_payoff_cannot_round_to_an_exact_total_loss():
    sessions, securities, _ = _complete_price_fixture()
    requirement = _terminal_requirement(
        session=sessions[_decision_index() + 1], event_kind="bankruptcy"
    )
    huge_entry = (
        dataclasses.replace(
            securities[0], total_return_open_value=Decimal("1e999999")
        ),
        *securities[1:],
    )
    with pytest.raises(EventStudyInputError, match="positive security value"):
        _collect(
            security_opens=huge_entry,
            terminal_requirements=(requirement,),
            terminal_payoffs=(_terminal_payoff(requirement, value="1"),),
        )


def test_exactly_equal_security_and_benchmark_wealth_cannot_create_roundoff_alpha():
    security_return, benchmark_return, excess_return = event_study_module._returns(
        entry_security=Decimal("2"),
        exit_security=Decimal("6"),
        entry_benchmark=Decimal("2"),
        valuation_benchmark=Decimal("6"),
        exit_benchmark=Decimal("1"),
    )
    assert security_return == benchmark_return == Decimal("-0.5")
    assert excess_return == 0


@pytest.mark.parametrize(
    ("entry_security", "exit_security", "valuation_benchmark", "exit_benchmark"),
    (
        ("1e-999999", "1e999999", "1", "1"),
        ("1", "1", "1e999999", "1e-999999"),
    ),
)
def test_return_arithmetic_traps_extreme_decimal_signals(
    entry_security, exit_security, valuation_benchmark, exit_benchmark
):
    with pytest.raises(EventStudyInputError, match="frozen domain"):
        event_study_module._returns(
            entry_security=Decimal(entry_security),
            exit_security=Decimal(exit_security),
            entry_benchmark=Decimal("1"),
            valuation_benchmark=Decimal(valuation_benchmark),
            exit_benchmark=Decimal(exit_benchmark),
        )


def test_terminal_lifecycle_is_permanent_security_state_across_decisions():
    sessions = _sessions()
    first_index = _decision_index()
    second_index = first_index + 1
    decisions = (
        _decision(),
        _decision(
            row_id="row-2",
            session=sessions[second_index],
            component="component-2",
        ),
    )
    terminal_session = sessions[first_index + 10]
    required_sessions = {
        sessions[first_index],
        sessions[second_index],
        terminal_session,
        *(sessions[first_index + horizon] for horizon in HORIZONS),
        *(sessions[second_index + horizon] for horizon in HORIZONS),
    }
    securities = tuple(
        _security_open(session, "100") for session in sorted(required_sessions)
    )
    benchmarks = tuple(
        _benchmark_open(session) for session in sorted(required_sessions)
    )
    first_requirement = _terminal_requirement(session=terminal_session)
    first_payoff = _terminal_payoff(first_requirement)
    incomplete = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
        terminal_requirements=(first_requirement,),
        terminal_payoffs=(first_payoff,),
    )
    assert sum(
        item.terminal_lifecycle is not None
        for item in incomplete.security_lifecycle_coverages
    ) == 1
    assert {
        (item.row_id, item.horizon_sessions, item.reason)
        for item in incomplete.refusals
    } == {
        ("row-2", 20, "missing_terminal_requirement"),
        ("row-2", 60, "missing_terminal_requirement"),
    }

    second_requirement = _terminal_requirement(
        session=terminal_session,
        decision_row_id="row-2",
        requirement_id="terminal-2",
    )
    complete = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
        terminal_requirements=(first_requirement, second_requirement),
        terminal_payoffs=(
            first_payoff,
            _terminal_payoff(second_requirement),
        ),
    )
    assert not complete.refusals
    assert {
        (item.row_id, item.horizon_sessions)
        for item in complete.observations
        if item.terminal_payoff_used
    } == {("row-1", 20), ("row-1", 60), ("row-2", 20), ("row-2", 60)}

    conflicting_payoff = _terminal_payoff(second_requirement, value="10")
    with pytest.raises(EventStudyInputError, match="conflicting terminal payoffs"):
        _collect(
            decisions=decisions,
            security_opens=securities,
            benchmark_opens=benchmarks,
            terminal_requirements=(first_requirement, second_requirement),
            terminal_payoffs=(first_payoff, conflicting_payoff),
        )

    changed_outputs = tuple(
        dataclasses.replace(
            item,
            security_exit_total_return_index_value=Decimal("10"),
            security_total_return=Decimal("-0.9"),
            excess_total_return=Decimal("-0.9"),
        )
        if item.row_id == "row-2" and item.terminal_payoff_used
        else item
        for item in complete.observations
    )
    forged_payoff = _self_rehash(complete, observations=changed_outputs)
    with pytest.raises(
        EventStudyInputError,
        match="terminal payoff fact|series-session value/source fact",
    ):
        require_synthetic_event_study_batch(forged_payoff)

    contradictory_raw_payoff = tuple(
        dataclasses.replace(
            item, security_exit_total_return_index_value=Decimal("999")
        )
        if item.row_id == "row-2" and item.horizon_sessions == 20
        else item
        for item in complete.observations
    )
    with pytest.raises(EventStudyInputError, match="return arithmetic"):
        require_synthetic_event_study_batch(
            _self_rehash(complete, observations=contradictory_raw_payoff)
        )

    reused_requirement = tuple(
        dataclasses.replace(
            item, terminal_requirement_id=first_requirement.requirement_id
        )
        if item.row_id == "row-2" and item.terminal_payoff_used
        else item
        for item in complete.observations
    )
    forged_requirement = _self_rehash(
        complete, observations=reused_requirement
    )
    with pytest.raises(EventStudyInputError, match="shared across decision rows"):
        require_synthetic_event_study_batch(forged_requirement)

    conflicting = dataclasses.replace(
        second_requirement,
        terminal_session=sessions[first_index + 11],
    )
    with pytest.raises(
        EventStudyInputError,
        match="does not match complete lifecycle inventory",
    ):
        _collect(
            decisions=decisions,
            security_opens=securities,
            benchmark_opens=benchmarks,
            terminal_requirements=(first_requirement, conflicting),
        )

    post_terminal = _decision(
        row_id="row-3",
        session=terminal_session,
        component="component-3",
    )
    with pytest.raises(EventStudyInputError, match="on or after.*terminal"):
        _collect(
            decisions=(decisions[0], post_terminal),
            security_opens=securities,
            benchmark_opens=benchmarks,
            terminal_requirements=(first_requirement,),
            terminal_payoffs=(first_payoff,),
        )

    ordinary = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
    )
    forged = _self_rehash(
        ordinary,
        security_lifecycle_coverages=complete.security_lifecycle_coverages,
    )
    with pytest.raises(EventStudyInputError, match="terminal security lifecycle"):
        require_synthetic_event_study_batch(forged)

    switched_row_series = tuple(
        dataclasses.replace(
            item,
            security_total_return_series_id="security-1-alternate-total-return-series",
        )
        if item.row_id == "row-2"
        else item
        for item in ordinary.observations
    )
    with pytest.raises(
        EventStudyInputError,
        match="permanent security identifies multiple total-return series",
    ):
        require_synthetic_event_study_batch(
            _self_rehash(ordinary, observations=switched_row_series)
        )
    assert _batch_hash(
        candidate_hash=complete.candidate_declaration_hash,
        terminal_payoff_reinvestment_policy_id=(
            complete.terminal_payoff_reinvestment_policy_id
        ),
        partition_set_sha256=complete.input_partition_set_sha256,
        observations=complete.observations,
        refusals=complete.refusals,
        security_lifecycle_coverages=(),
        expected=complete.expected_decision_horizons,
    ) != complete.batch_hash


def test_terminal_lifecycle_allows_partial_tail_geometry_without_index_error():
    decision_session = date(2026, 8, 27)
    terminal_session = date(2026, 8, 28)
    decision = _decision(
        session=decision_session,
        evaluation_segment_id="arv2-partial-2026-exploratory",
        fold_id=None,
    )
    requirement = _terminal_requirement(session=terminal_session)
    batch = _collect(
        decisions=(decision,),
        security_opens=(_security_open(decision_session, "100"),),
        benchmark_opens=(
            _benchmark_open(decision_session),
            _benchmark_open(terminal_session),
        ),
        terminal_requirements=(requirement,),
        terminal_payoffs=(_terminal_payoff(requirement),),
    )
    assert [
        (item.horizon_sessions, item.terminal_payoff_used)
        for item in batch.observations
    ] == [(1, True)]
    assert [(item.horizon_sessions, item.reason) for item in batch.refusals] == [
        (5, "immature_tail"),
        (20, "immature_tail"),
        (60, "immature_tail"),
    ]
    assert require_synthetic_event_study_batch(batch) is batch


def test_missing_terminal_payoff_is_named_and_never_silently_dropped():
    requirement = _terminal_requirement()
    batch = _collect(terminal_requirements=(requirement,))
    assert [item.horizon_sessions for item in batch.observations] == [1, 5]
    assert [(item.horizon_sessions, item.reason) for item in batch.refusals] == [
        (20, "missing_terminal_shareholder_payoff"),
        (60, "missing_terminal_shareholder_payoff"),
    ]


@pytest.mark.parametrize(
    ("reason", "message"),
    (
        (
            "missing_terminal_requirement",
            "terminal requirement availability changed across horizons",
        ),
        (
            "missing_terminal_shareholder_payoff",
            "fixed terminal payoff availability changed across horizons",
        ),
    ),
)
def test_fixed_terminal_facts_cannot_appear_selectively_across_horizons(
    reason, message
):
    requirement = _terminal_requirement()
    batch = _collect(
        terminal_requirements=(requirement,),
        terminal_payoffs=(_terminal_payoff(requirement),),
    )
    h20 = next(
        item for item in batch.observations if item.horizon_sessions == 20
    )
    refusal = event_study_module._refusal(_decision(), 20, reason)
    rebuilt = _self_rehash(
        batch,
        observations=tuple(item for item in batch.observations if item is not h20),
        refusals=(refusal,),
    )
    with pytest.raises(EventStudyInputError, match=message):
        require_synthetic_event_study_batch(rebuilt)


def test_qc_delisting_price_cannot_impersonate_terminal_shareholder_payoff():
    requirement = _terminal_requirement()
    payoff = _terminal_payoff(requirement, value="50", source_role="qc_delisting_price")
    with pytest.raises(EventStudyInputError, match="delisting price"):
        _collect(terminal_requirements=(requirement,), terminal_payoffs=(payoff,))


def test_terminal_payoff_must_have_exact_decision_and_event_lineage():
    requirement = _terminal_requirement()
    payoff = dataclasses.replace(
        _terminal_payoff(requirement),
        terminal_listing_id="wrong-listing",
        valuation_listing_id="wrong-listing",
    )
    with pytest.raises(EventStudyInputError, match="does not match"):
        _collect(terminal_requirements=(requirement,), terminal_payoffs=(payoff,))


def test_orphan_or_duplicate_terminal_records_refuse():
    requirement = _terminal_requirement()
    payoff = _terminal_payoff(requirement)
    with pytest.raises(EventStudyInputError, match="no matching requirement"):
        _collect(terminal_payoffs=(payoff,))
    with pytest.raises(EventStudyInputError, match="decision must be unique"):
        _collect(terminal_requirements=(requirement, requirement))
    with pytest.raises(EventStudyInputError, match="requirement/valuation key"):
        _collect(
            terminal_requirements=(requirement,), terminal_payoffs=(payoff, payoff)
        )


def test_stock_merger_requires_a_complete_successor_identity():
    incomplete = _terminal_requirement(
        event_kind="stock_merger", successor_security_id="successor"
    )
    with pytest.raises(EventStudyInputError, match="must be complete"):
        _collect(terminal_requirements=(incomplete,))
    decisions, securities, benchmarks, requirements, payoffs = (
        _covered_stock_merger_fixture()
    )
    (complete,) = requirements
    entry = _decision_index()
    h20, h60 = payoffs
    with pytest.raises(
        EventStudyInputError,
        match="successor lifecycle coverage is absent",
    ):
        _collect(
            decisions=(decisions[0],),
            security_opens=tuple(
                item for item in securities if item.security_id == "security-1"
            ),
            benchmark_opens=benchmarks,
            security_lifecycle_coverages=tuple(
                item
                for item in _lifecycle_coverages((decisions[0],), (complete,))
                if item.security_id == "security-1"
            ),
            terminal_requirements=(complete,),
        )
    with pytest.raises(EventStudyInputError, match="successor identity"):
        _collect(
            decisions=decisions,
            security_opens=securities,
            benchmark_opens=benchmarks,
            terminal_requirements=(complete,),
            terminal_payoffs=(
                dataclasses.replace(h20, valuation_historical_ticker="BOGUS"),
                h60,
            ),
        )
    batch = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
        terminal_requirements=(complete,),
        terminal_payoffs=(h20, h60),
    )
    active_successor = next(
        item
        for item in batch.security_lifecycle_coverages
        if item.security_id == "successor"
    )
    assert active_successor.terminal_lifecycle is None
    missing_successor_coverage = tuple(
        item
        for item in batch.security_lifecycle_coverages
        if item.security_id != "successor"
    )
    with pytest.raises(EventStudyInputError, match="lifecycle coverage is absent"):
        require_synthetic_event_study_batch(
            _self_rehash(
                batch,
                security_lifecycle_coverages=missing_successor_coverage,
            )
        )
    assert sum(item.terminal_payoff_used for item in batch.observations) == 2
    terminal = [item for item in batch.observations if item.terminal_payoff_used]
    assert {item.valuation_session for item in terminal} == {
        _sessions()[entry + 20],
        _sessions()[entry + 60],
    }
    assert {item.successor_security_id for item in terminal} == {"successor"}
    assert {item.successor_historical_ticker for item in terminal} == {"BBB"}
    assert [item.security_total_return for item in terminal] == [
        Decimal("0.3"),
        Decimal("0.5"),
    ]

    reserved_terminal = tuple(
        dataclasses.replace(
            item,
            terminal_listing_id=BENCHMARK_LISTING_ID,
            terminal_historical_ticker=BENCHMARK_TICKER,
        )
        if item.terminal_payoff_used
        else item
        for item in batch.observations
    )
    with pytest.raises(EventStudyInputError, match="reserved benchmark identity"):
        require_synthetic_event_study_batch(
            _self_rehash(batch, observations=reserved_terminal)
        )

    mixed = dataclasses.replace(complete, event_kind="mixed_merger")
    mixed_h20 = dataclasses.replace(h20, event_kind="mixed_merger")
    mixed_h60 = dataclasses.replace(h60, event_kind="mixed_merger")
    mixed_batch = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
        terminal_requirements=(mixed,),
        terminal_payoffs=(mixed_h20, mixed_h60),
    )
    assert [
        item.security_total_return
        for item in mixed_batch.observations
        if item.terminal_payoff_used
    ] == [Decimal("0.3"), Decimal("0.5")]


def test_stock_merger_cannot_value_through_a_terminal_successor_lifecycle():
    sessions, first_security, benchmarks = _complete_price_fixture()
    entry = _decision_index()
    successor_decision = _decision(
        row_id="row-2",
        security_id="successor",
        listing_id="successor-listing",
        ticker="BBB",
        component="component-2",
    )
    successor_security = tuple(
        dataclasses.replace(
            item,
            security_id="successor",
            listing_id="successor-listing",
            historical_ticker="BBB",
            total_return_series_id="successor-total-return-series",
        )
        for item in first_security
    )
    predecessor = _terminal_requirement(
        event_kind="stock_merger",
        successor_security_id="successor",
        successor_listing_id="successor-listing",
        successor_historical_ticker="BBB",
    )
    successor_before_predecessor = _terminal_requirement(
        decision_row_id="row-2",
        requirement_id="terminal-2",
        security_id="successor",
        terminal_listing_id="successor-terminal-listing",
        terminal_ticker="BBC",
        total_return_series_id="successor-total-return-series",
        session=sessions[entry + 9],
    )
    with pytest.raises(
        EventStudyInputError,
        match="successor terminal lifecycle is not later",
    ):
        _collect(
            decisions=(_decision(), successor_decision),
            security_opens=(*first_security, *successor_security),
            benchmark_opens=benchmarks,
            terminal_requirements=(predecessor, successor_before_predecessor),
        )

    successor_before_h60 = dataclasses.replace(
        successor_before_predecessor,
        terminal_session=sessions[entry + 30],
    )
    h60_payoff = _terminal_payoff(
        predecessor,
        value="150",
        valuation_session=sessions[entry + 60],
        valuation_ticker="BBB",
    )
    with pytest.raises(EventStudyInputError, match="traverses a terminal successor"):
        _collect(
            decisions=(_decision(), successor_decision),
            security_opens=(*first_security, *successor_security),
            benchmark_opens=benchmarks,
            terminal_requirements=(predecessor, successor_before_h60),
            terminal_payoffs=(h60_payoff,),
        )

    successor_after_h60 = dataclasses.replace(
        successor_before_predecessor,
        terminal_session=sessions[entry + 70],
    )
    h20_payoff = _terminal_payoff(
        predecessor,
        value="130",
        valuation_session=sessions[entry + 20],
        valuation_ticker="BBB",
    )
    valid = _collect(
        decisions=(_decision(), successor_decision),
        security_opens=(*first_security, *successor_security),
        benchmark_opens=benchmarks,
        terminal_requirements=(predecessor, successor_after_h60),
        terminal_payoffs=(h20_payoff, h60_payoff),
    )
    forged_lifecycles = tuple(
        dataclasses.replace(
            item,
            terminal_lifecycle=dataclasses.replace(
                item.terminal_lifecycle,
                terminal_session=sessions[entry + 30],
            ),
        )
        if item.security_id == "successor"
        else item
        for item in valid.security_lifecycle_coverages
    )
    with pytest.raises(EventStudyInputError, match="traverses a terminal successor"):
        require_synthetic_event_study_batch(
            _self_rehash(
                valid,
                security_lifecycle_coverages=forged_lifecycles,
            )
        )


def test_every_merger_requires_a_distinct_successor_identity():
    self_successor = _terminal_requirement(
        event_kind="cash_merger",
        successor_security_id="security-1",
        successor_listing_id="successor-listing",
        successor_historical_ticker="BBB",
    )
    with pytest.raises(EventStudyInputError, match="distinct security"):
        _collect(terminal_requirements=(self_successor,))
    cash = dataclasses.replace(
        self_successor, successor_security_id="successor-security"
    )
    early_successor = TerminalLifecycle(
        security_id="successor-security",
        terminal_listing_id="successor-terminal-listing",
        terminal_historical_ticker="BBC",
        terminal_session=_sessions()[_decision_index() + 5],
        event_kind="bankruptcy",
        successor_security_id=None,
        successor_listing_id=None,
        successor_historical_ticker=None,
        total_return_series_id="successor-total-return-series",
    )
    impossible_coverages = tuple(
        dataclasses.replace(item, terminal_lifecycle=early_successor)
        if item.security_id == "successor-security"
        else item
        for item in _lifecycle_coverages((_decision(),), (cash,))
    )
    with pytest.raises(
        EventStudyInputError,
        match="successor terminal lifecycle is not later",
    ):
        _collect(
            security_lifecycle_coverages=impossible_coverages,
            terminal_requirements=(cash,),
        )
    batch = _collect(
        terminal_requirements=(cash,),
        terminal_payoffs=(_terminal_payoff(cash, value="125"),),
    )
    assert sum(item.terminal_payoff_used for item in batch.observations) == 2
    assert {
        item.security_total_return
        for item in batch.observations
        if item.terminal_payoff_used
    } == {Decimal("0.25")}


def test_missing_security_or_benchmark_exit_is_a_named_refusal():
    sessions, securities, benchmarks = _complete_price_fixture()
    entry = _decision_index()
    securities = tuple(
        item for item in securities if item.session != sessions[entry + 20]
    )
    batch = _collect(security_opens=securities, benchmark_opens=benchmarks)
    assert [(item.horizon_sessions, item.reason) for item in batch.refusals] == [
        (20, "missing_security_exit_open")
    ]
    benchmarks = tuple(
        item for item in benchmarks if item.session != sessions[entry + 5]
    )
    batch = _collect(benchmark_opens=benchmarks)
    assert [(item.horizon_sessions, item.reason) for item in batch.refusals] == [
        (5, "missing_benchmark_exit_open")
    ]


def test_missing_benchmark_entry_is_named_for_every_horizon():
    sessions, _, benchmarks = _complete_price_fixture()
    benchmarks = tuple(
        item for item in benchmarks if item.session != sessions[_decision_index()]
    )
    batch = _collect(benchmark_opens=benchmarks)
    assert len(batch.refusals) == 4
    assert {item.reason for item in batch.refusals} == {
        "missing_benchmark_entry_open"
    }


def test_benchmark_identity_is_exact_synthetic_spy():
    _, _, benchmarks = _complete_price_fixture()
    bad = (dataclasses.replace(benchmarks[0], historical_ticker="QQQ"), *benchmarks[1:])
    with pytest.raises(EventStudyInputError, match="exact synthetic SPY"):
        _collect(benchmark_opens=bad)


def test_permanent_security_identity_allows_historical_listing_transition():
    sessions, securities, benchmarks = _complete_price_fixture()
    entry = _decision_index()
    transitioned = tuple(
        item if item.session == sessions[entry] else dataclasses.replace(
            item, listing_id="listing-2", historical_ticker="AAB"
        )
        for item in securities
    )
    batch = _collect(security_opens=transitioned, benchmark_opens=benchmarks)
    assert not batch.refusals
    assert {item.exit_listing_id for item in batch.observations} == {"listing-2"}
    assert {item.exit_historical_ticker for item in batch.observations} == {"AAB"}


def test_one_listing_id_cannot_change_security_or_ticker_identity():
    _, securities, benchmarks = _complete_price_fixture()
    second_security = _decision(
        row_id="row-2",
        security_id="security-2",
        listing_id="listing-1",
        ticker="AAA",
        component="component-2",
    )
    with pytest.raises(EventStudyInputError, match="security/ticker identities"):
        _collect(
            decisions=(_decision(), second_security),
            security_opens=securities,
            benchmark_opens=benchmarks,
        )

    renamed_same_listing = tuple(
        securities[:1]
        + tuple(
            dataclasses.replace(item, historical_ticker="RENAMED")
            for item in securities[1:]
        )
    )
    with pytest.raises(EventStudyInputError, match="security/ticker identities"):
        _collect(
            security_opens=renamed_same_listing,
            benchmark_opens=benchmarks,
        )


def test_self_rehashed_output_cannot_change_a_listing_identity():
    batch = _collect()
    changed = dataclasses.replace(
        batch.observations[0], exit_historical_ticker="RENAMED"
    )
    rebuilt = _self_rehash(
        batch, observations=(changed, *batch.observations[1:])
    )
    with pytest.raises(EventStudyInputError, match="output listing"):
        require_synthetic_event_study_batch(rebuilt)


def test_return_ratio_requires_one_entry_compatible_series_identity():
    _, securities, benchmarks = _complete_price_fixture()
    changed = (
        securities[0],
        dataclasses.replace(
            securities[1], total_return_series_id="different-vintage-series"
        ),
        *securities[2:],
    )
    with pytest.raises(EventStudyInputError, match="multiple total-return series"):
        _collect(security_opens=changed, benchmark_opens=benchmarks)
    requirement = dataclasses.replace(
        _terminal_requirement(), total_return_series_id="different-vintage-series"
    )
    payoff = _terminal_payoff(requirement)
    with pytest.raises(EventStudyInputError, match="multiple total-return series"):
        _collect(terminal_requirements=(requirement,), terminal_payoffs=(payoff,))


def test_total_return_series_identity_is_functional_to_one_security():
    decisions, securities, benchmarks = _two_security_fixture()
    reused_series = tuple(
        dataclasses.replace(
            item,
            total_return_series_id="security-1-total-return-series",
        )
        if item.security_id == "security-2"
        else item
        for item in securities
    )
    with pytest.raises(EventStudyInputError, match="series.*multiple securities"):
        _collect(
            decisions=decisions,
            security_opens=reused_series,
            benchmark_opens=benchmarks,
        )

    batch = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
    )
    changed = tuple(
        dataclasses.replace(
            item,
            security_total_return_series_id="security-1-total-return-series",
        )
        if item.security_id == "security-2"
        else item
        for item in batch.observations
    )
    rebuilt = _self_rehash(batch, observations=changed)
    with pytest.raises(EventStudyInputError, match="series.*multiple securities"):
        require_synthetic_event_study_batch(rebuilt)


@pytest.mark.parametrize(
    "field,value",
    (
        ("security_id", BENCHMARK_SECURITY_ID),
        ("listing_id", BENCHMARK_LISTING_ID),
        ("ticker", BENCHMARK_TICKER),
    ),
)
def test_security_side_refuses_reserved_benchmark_identity(field, value):
    decision = _decision(**{field: value})
    with pytest.raises(EventStudyInputError, match="reserved benchmark identity"):
        _collect(decisions=(decision,))

    open_field = "historical_ticker" if field == "ticker" else field
    value_row = dataclasses.replace(
        _security_open(_sessions()[_decision_index()], "100"),
        **{open_field: value},
    )
    with pytest.raises(EventStudyInputError, match="reserved benchmark identity"):
        event_study_module._validate_security_open(value_row)


def test_security_side_refuses_reserved_benchmark_series():
    value = dataclasses.replace(
        _security_open(_sessions()[_decision_index()], "100"),
        total_return_series_id=BENCHMARK_TOTAL_RETURN_SERIES_ID,
    )
    with pytest.raises(EventStudyInputError, match="reserved benchmark series"):
        event_study_module._validate_security_open(value)


def test_entry_listing_must_match_the_decision_identity():
    _, securities, benchmarks = _complete_price_fixture()
    bad = (dataclasses.replace(securities[0], listing_id="elsewhere"), *securities[1:])
    batch = _collect(security_opens=bad, benchmark_opens=benchmarks)
    assert len(batch.refusals) == 4
    assert {item.reason for item in batch.refusals} == {
        "security_entry_identity_mismatch"
    }


def test_permanent_identity_prevents_ticker_only_price_fallback():
    _, securities, benchmarks = _complete_price_fixture()
    second = _decision(
        row_id="row-2", security_id="security-2", listing_id="listing-2",
        ticker="AAA", component="component-2",
    )
    batch = _collect(
        decisions=(_decision(), second),
        security_opens=securities,
        benchmark_opens=benchmarks,
    )
    assert {item.row_id for item in batch.observations} == {"row-1"}
    assert len(batch.refusals) == 4
    assert {item.reason for item in batch.refusals} == {"missing_security_entry_open"}


def test_cross_date_common_event_component_refuses_every_linked_horizon():
    sessions, securities, benchmarks = _complete_price_fixture()
    later = _decision(
        row_id="row-2", session=sessions[_decision_index() + 1], security_id="security-2",
        listing_id="listing-2", ticker="BBB", component="component-1",
    )
    batch = _collect(
        decisions=(_decision(), later),
        security_opens=securities,
        benchmark_opens=benchmarks,
    )
    assert not batch.observations
    assert len(batch.refusals) == 8
    assert {item.reason for item in batch.refusals} == {
        "cross_date_common_event_component"
    }


def test_immature_tail_is_exhaustively_reported():
    sessions = _sessions()
    decision = _decision(
        session=sessions[-1],
        evaluation_segment_id="arv2-partial-2026-exploratory",
        fold_id=None,
    )
    batch = _collect(
        decisions=(decision,),
        security_opens=(_security_open(sessions[-1], "100"),),
        benchmark_opens=(_benchmark_open(sessions[-1]),),
    )
    assert not batch.observations
    assert len(batch.refusals) == 4
    assert {item.reason for item in batch.refusals} == {"immature_tail"}
    assert all(item.fold_id is None for item in batch.refusals)
    assert all(
        item.evaluation_segment_id == "arv2-partial-2026-exploratory"
        for item in batch.refusals
    )


def test_partial_2026_uses_named_immaturity_not_an_invented_fold():
    sessions = _sessions()
    decision_session = date(2026, 7, 1)
    entry = sessions.index(decision_session)
    decision = _decision(
        session=decision_session,
        evaluation_segment_id="arv2-partial-2026-exploratory",
        fold_id=None,
    )
    security = (_security_open(decision_session, "100"),) + tuple(
        _security_open(sessions[entry + horizon], "101")
        for horizon in (1, 5, 20)
    )
    benchmark = (_benchmark_open(decision_session),) + tuple(
        _benchmark_open(sessions[entry + horizon])
        for horizon in (1, 5, 20)
    )
    batch = _collect(
        decisions=(decision,), security_opens=security, benchmark_opens=benchmark
    )
    assert [item.horizon_sessions for item in batch.observations] == [1, 5, 20]
    assert [(item.horizon_sessions, item.reason) for item in batch.refusals] == [
        (60, "immature_tail")
    ]
    assert all(item.fold_id is None for item in (*batch.observations, *batch.refusals))


def test_weekend_or_gap_cannot_impersonate_the_xnys_session_axis():
    sessions = _sessions()
    saturday = date(2021, 4, 3)
    with pytest.raises(EventStudyInputError, match="exact reviewed"):
        _collect(session_axis=tuple(sorted((*sessions, saturday))))
    with pytest.raises(EventStudyInputError, match="exact reviewed"):
        _collect(session_axis=sessions[:10] + sessions[11:])


def test_fold_label_must_match_each_horizon_test_interval():
    batch = _collect(decisions=(_decision(
        evaluation_segment_id="arv2-wf-test-2020",
        fold_id="arv2-wf-test-2020",
    ),))
    assert not batch.observations
    assert len(batch.refusals) == 4
    assert {item.reason for item in batch.refusals} == {
        "outside_horizon_fold_test_interval"
    }


def test_run_candidate_is_bound_to_every_exact_input_partition():
    _, securities, benchmarks = _complete_price_fixture()
    changed = (
        securities[0],
        dataclasses.replace(securities[1], source_sha256=_sha("e")),
        *securities[2:],
    )
    with pytest.raises(EventStudyInputError, match="does not match run candidate"):
        _collect(
            security_opens=changed,
            benchmark_opens=benchmarks,
            run_candidate=_candidate(),
        )

    coverage = _lifecycle_coverages((_decision(),), ())[0]
    changed_coverage = dataclasses.replace(coverage, source_sha256=_sha("f"))
    with pytest.raises(EventStudyInputError, match="does not match run candidate"):
        _collect(
            security_lifecycle_coverages=(changed_coverage,),
            run_candidate=_candidate(),
        )


def test_declared_code_hash_is_not_misrepresented_as_execution_authentication():
    candidate = _candidate()
    forged_core = dataclasses.replace(candidate.code_files[0], sha256=_sha("f"))
    forged = build_synthetic_qc_run_candidate(
        code_files=(forged_core,),
        synthetic_partitions=candidate.synthetic_partitions,
    )
    batch = _collect(run_candidate=forged)
    assert batch.candidate_declaration_hash == forged.candidate_hash
    assert batch.execution_code_authenticated is False
    assert forged.execution_code_authenticated is False


def test_batch_is_content_identified_and_aggregate_export_revalidates_it():
    batch = _collect()
    assert require_synthetic_event_study_batch(batch) is batch
    assert all(len(value) == 64 for value in (
        batch.candidate_declaration_hash,
        batch.input_partition_set_sha256,
        batch.batch_hash,
    ))
    mutated = dataclasses.replace(
        batch.observations[0], excess_total_return=Decimal("999")
    )
    object.__setattr__(batch, "observations", (mutated, *batch.observations[1:]))
    with pytest.raises(EventStudyInputError, match="return arithmetic"):
        batch.aggregate_census()


def test_batch_identity_type_tags_prevent_decimal_and_date_string_collisions():
    batch = _collect()
    changed = dataclasses.replace(
        batch.observations[0],
        security_total_return=str(batch.observations[0].security_total_return),
        decision_session=batch.observations[0].decision_session.isoformat(),
    )
    changed_observations = (changed, *batch.observations[1:])
    assert _batch_hash(
        candidate_hash=batch.candidate_declaration_hash,
        terminal_payoff_reinvestment_policy_id=(
            batch.terminal_payoff_reinvestment_policy_id
        ),
        partition_set_sha256=batch.input_partition_set_sha256,
        observations=changed_observations,
        refusals=batch.refusals,
        security_lifecycle_coverages=batch.security_lifecycle_coverages,
        expected=batch.expected_decision_horizons,
    ) != batch.batch_hash
    object.__setattr__(batch, "observations", changed_observations)
    with pytest.raises(EventStudyInputError, match="must be an exact date"):
        require_synthetic_event_study_batch(batch)


def test_batch_identity_digest_is_sensitive_to_refusal_content():
    sessions, securities, benchmarks = _complete_price_fixture()
    missing_session = sessions[_decision_index() + 20]
    incomplete = tuple(
        item for item in securities if item.session != missing_session
    )
    batch = _collect(security_opens=incomplete, benchmark_opens=benchmarks)
    assert len(batch.refusals) == 1
    changed_refusal = dataclasses.replace(
        batch.refusals[0], reason="missing_benchmark_exit_open"
    )
    assert _batch_hash(
        candidate_hash=batch.candidate_declaration_hash,
        terminal_payoff_reinvestment_policy_id=(
            batch.terminal_payoff_reinvestment_policy_id
        ),
        partition_set_sha256=batch.input_partition_set_sha256,
        observations=batch.observations,
        refusals=(changed_refusal,),
        security_lifecycle_coverages=batch.security_lifecycle_coverages,
        expected=batch.expected_decision_horizons,
    ) != batch.batch_hash


def test_batch_identity_digest_binds_candidate_partitions_and_census():
    batch = _collect()
    inputs = {
        "candidate_hash": batch.candidate_declaration_hash,
        "terminal_payoff_reinvestment_policy_id": (
            batch.terminal_payoff_reinvestment_policy_id
        ),
        "partition_set_sha256": batch.input_partition_set_sha256,
        "observations": batch.observations,
        "refusals": batch.refusals,
        "security_lifecycle_coverages": batch.security_lifecycle_coverages,
        "expected": batch.expected_decision_horizons,
    }
    for field, value in (
        ("candidate_hash", _sha("e")),
        (
            "terminal_payoff_reinvestment_policy_id",
            "arv2-terminal-payoff-benchmark-splice-v2",
        ),
        ("partition_set_sha256", _sha("f")),
        ("expected", batch.expected_decision_horizons + 1),
    ):
        changed = {**inputs, field: value}
        assert _batch_hash(**changed) != batch.batch_hash


def test_self_rehashed_batch_still_requires_financial_and_decision_invariants():
    batch = _collect()
    impossible_loss = dataclasses.replace(
        batch.observations[0],
        security_total_return=Decimal("-2"),
        excess_total_return=Decimal("-2"),
    )
    rebuilt = _self_rehash(
        batch, observations=(impossible_loss, *batch.observations[1:])
    )
    with pytest.raises(
        EventStudyInputError,
        match="return arithmetic|payoff bounds",
    ):
        require_synthetic_event_study_batch(rebuilt)

    ordinary_total_loss = dataclasses.replace(
        batch.observations[0],
        security_total_return=Decimal("-1"),
        excess_total_return=Decimal("-1"),
    )
    rebuilt = _self_rehash(
        batch, observations=(ordinary_total_loss, *batch.observations[1:])
    )
    with pytest.raises(
        EventStudyInputError,
        match="return arithmetic|payoff bounds",
    ):
        require_synthetic_event_study_batch(rebuilt)

    impossible_benchmark = dataclasses.replace(
        batch.observations[0],
        benchmark_total_return=Decimal("-1"),
        excess_total_return=Decimal("1.01"),
    )
    rebuilt = _self_rehash(
        batch, observations=(impossible_benchmark, *batch.observations[1:])
    )
    with pytest.raises(
        EventStudyInputError,
        match="return arithmetic|benchmark total return",
    ):
        require_synthetic_event_study_batch(rebuilt)

    changed_decision = dataclasses.replace(
        batch.observations[1], firm_specific_score=Decimal("999")
    )
    rebuilt = _self_rehash(
        batch,
        observations=(
            batch.observations[0],
            changed_decision,
            *batch.observations[2:],
        ),
    )
    with pytest.raises(EventStudyInputError, match="decision identity changed"):
        require_synthetic_event_study_batch(rebuilt)

    changed_entry = dataclasses.replace(
        batch.observations[1], security_entry_source_sha256=_sha("f")
    )
    rebuilt = _self_rehash(
        batch,
        observations=(
            batch.observations[0],
            changed_entry,
            *batch.observations[2:],
        ),
    )
    with pytest.raises(
        EventStudyInputError,
        match="entry source|entry fact|series-session (?:source|value/source fact)",
    ):
        require_synthetic_event_study_batch(rebuilt)


def test_self_rehashed_batch_rejects_duplicate_security_decision_keys():
    batch = _collect()
    duplicate_row = tuple(
        dataclasses.replace(
            item,
            row_id="row-2",
            decision_input_sha256=_sha("e"),
            common_event_component_id="component-2",
        )
        for item in batch.observations
    )
    rebuilt = _self_rehash(
        batch,
        observations=(*batch.observations, *duplicate_row),
        expected=8,
    )
    with pytest.raises(EventStudyInputError, match="key is duplicated"):
        require_synthetic_event_study_batch(rebuilt)


def test_self_rehashed_batch_requires_monotone_exact_terminal_lineage():
    requirement = _terminal_requirement()
    batch = _collect(
        terminal_requirements=(requirement,),
        terminal_payoffs=(_terminal_payoff(requirement),),
    )
    h60 = batch.observations[-1]
    reverted = dataclasses.replace(
        h60,
        security_total_return=Decimal("0"),
        excess_total_return=Decimal("0"),
        security_exit_total_return_index_value=Decimal("100"),
        terminal_payoff_used=False,
        terminal_requirement_id=None,
        terminal_event_kind=None,
        terminal_session=None,
        terminal_listing_id=None,
        terminal_historical_ticker=None,
        valuation_session=h60.exit_session,
        valuation_security_id=h60.security_id,
        successor_security_id=None,
        successor_listing_id=None,
        successor_historical_ticker=None,
    )
    rebuilt = _self_rehash(
        batch, observations=(*batch.observations[:-1], reverted)
    )
    with pytest.raises(EventStudyInputError, match="ordinary observation follows"):
        require_synthetic_event_study_batch(rebuilt)

    changed_lineage = dataclasses.replace(
        h60, terminal_requirement_id="different-terminal-requirement"
    )
    rebuilt = _self_rehash(
        batch, observations=(*batch.observations[:-1], changed_lineage)
    )
    with pytest.raises(EventStudyInputError, match="terminal lineage changed"):
        require_synthetic_event_study_batch(rebuilt)

    weekend = date(2021, 4, 17)
    h20 = batch.observations[-2]
    weekend_terminal = dataclasses.replace(
        h20, terminal_session=weekend, valuation_session=weekend
    )
    rebuilt = _self_rehash(
        batch,
        observations=(
            *batch.observations[:-2],
            weekend_terminal,
            batch.observations[-1],
        ),
    )
    with pytest.raises(EventStudyInputError, match="terminal session is outside"):
        require_synthetic_event_study_batch(rebuilt)


def test_self_rehashed_batch_requires_complete_cross_date_component_refusal():
    sessions, securities, benchmarks = _complete_price_fixture()
    later = _decision(
        row_id="row-2",
        session=sessions[_decision_index() + 1],
        security_id="security-2",
        listing_id="listing-2",
        ticker="BBB",
        component="component-1",
    )
    batch = _collect(
        decisions=(_decision(), later),
        security_opens=securities,
        benchmark_opens=benchmarks,
    )
    changed = tuple(
        dataclasses.replace(item, reason="missing_security_entry_open")
        for item in batch.refusals
    )
    rebuilt = _self_rehash(batch, refusals=changed)
    with pytest.raises(EventStudyInputError, match="cross-date component"):
        require_synthetic_event_study_batch(rebuilt)


def test_self_rehashed_batch_cannot_selectively_apply_entry_refusal():
    batch = _collect()
    refusal = event_study_module._refusal(
        _decision(), HORIZONS[0], "missing_security_entry_open"
    )
    rebuilt = _self_rehash(
        batch,
        observations=batch.observations[1:],
        refusals=(refusal,),
    )
    with pytest.raises(EventStudyInputError, match="selectively applied"):
        require_synthetic_event_study_batch(rebuilt)


def test_self_rehashed_batch_requires_one_shared_benchmark_outcome():
    decisions, securities, benchmarks = _two_security_fixture()
    batch = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
    )
    changed = tuple(
        dataclasses.replace(
            item,
            benchmark_total_return=Decimal("0.10"),
            excess_total_return=item.security_total_return - Decimal("0.10"),
            benchmark_valuation_total_return_index_value=Decimal("110"),
            benchmark_exit_total_return_index_value=Decimal("110"),
        )
        if item.row_id == "row-2" and item.horizon_sessions == 1
        else item
        for item in batch.observations
    )
    rebuilt = _self_rehash(batch, observations=changed)
    with pytest.raises(EventStudyInputError, match="shared benchmark outcome"):
        require_synthetic_event_study_batch(rebuilt)


def test_shared_benchmark_sources_are_bound_by_entry_and_exit_session():
    decisions, securities, benchmarks = _two_security_fixture()
    batch = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
    )
    retained = tuple(
        item
        for item in batch.observations
        if (item.row_id, item.horizon_sessions) in {("row-1", 1), ("row-2", 5)}
    )
    changed = tuple(
        dataclasses.replace(item, benchmark_entry_source_sha256=_sha("f"))
        if item.row_id == "row-2"
        else item
        for item in retained
    )
    refused_keys = {
        (item.row_id, item.horizon_sessions)
        for item in batch.observations
    } - {("row-1", 1), ("row-2", 5)}
    decisions_by_id = {item.row_id: item for item in decisions}
    refusals = tuple(
        event_study_module._refusal(
            decisions_by_id[row_id], horizon, "missing_security_exit_open"
        )
        for row_id, horizon in sorted(refused_keys)
    )
    rebuilt = _self_rehash(batch, observations=changed, refusals=refusals)
    with pytest.raises(EventStudyInputError, match="benchmark entry source"):
        require_synthetic_event_study_batch(rebuilt)

    sessions = _sessions()
    first_index = _decision_index()
    second_index = first_index + 4
    staggered_decisions = (
        _decision(),
        _decision(
            row_id="row-2",
            session=sessions[second_index],
            security_id="security-2",
            listing_id="listing-2",
            ticker="BBB",
            component="component-2",
        ),
    )
    first_sessions = {sessions[first_index]} | {
        sessions[first_index + horizon] for horizon in HORIZONS
    }
    second_sessions = {sessions[second_index]} | {
        sessions[second_index + horizon] for horizon in HORIZONS
    }
    staggered_security = tuple(
        _security_open(session, "100") for session in sorted(first_sessions)
    ) + tuple(
        _security_open(
            session,
            "100",
            security_id="security-2",
            listing_id="listing-2",
            ticker="BBB",
            total_return_series_id="security-2-total-return-series",
        )
        for session in sorted(second_sessions)
    )
    staggered_benchmarks = tuple(
        _benchmark_open(session) for session in sorted(first_sessions | second_sessions)
    )
    staggered = _collect(
        decisions=staggered_decisions,
        security_opens=staggered_security,
        benchmark_opens=staggered_benchmarks,
    )
    assert (
        next(
            item for item in staggered.observations
            if item.row_id == "row-1" and item.horizon_sessions == 5
        ).exit_session
        == next(
            item for item in staggered.observations
            if item.row_id == "row-2" and item.horizon_sessions == 1
        ).exit_session
    )
    changed = tuple(
        dataclasses.replace(
            item,
            benchmark_valuation_source_sha256=_sha("f"),
            benchmark_exit_source_sha256=_sha("f"),
        )
        if item.row_id == "row-2" and item.horizon_sessions == 1
        else item
        for item in staggered.observations
    )
    rebuilt = _self_rehash(staggered, observations=changed)
    with pytest.raises(EventStudyInputError, match="benchmark exit source"):
        require_synthetic_event_study_batch(rebuilt)

    consecutive_index = first_index + 1
    consecutive_decisions = (
        _decision(),
        _decision(
            row_id="row-2",
            session=sessions[consecutive_index],
            security_id="security-2",
            listing_id="listing-2",
            ticker="BBB",
            component="component-2",
        ),
    )
    consecutive_sessions = {sessions[consecutive_index]} | {
        sessions[consecutive_index + horizon] for horizon in HORIZONS
    }
    consecutive_security = tuple(
        _security_open(session, "100") for session in sorted(first_sessions)
    ) + tuple(
        _security_open(
            session,
            "100",
            security_id="security-2",
            listing_id="listing-2",
            ticker="BBB",
            total_return_series_id="security-2-total-return-series",
        )
        for session in sorted(consecutive_sessions)
    )
    consecutive_benchmarks = tuple(
        _benchmark_open(session)
        for session in sorted(first_sessions | consecutive_sessions)
    )
    consecutive = _collect(
        decisions=consecutive_decisions,
        security_opens=consecutive_security,
        benchmark_opens=consecutive_benchmarks,
    )
    changed = tuple(
        dataclasses.replace(item, benchmark_entry_source_sha256=_sha("f"))
        if item.row_id == "row-2"
        else item
        for item in consecutive.observations
    )
    rebuilt = _self_rehash(consecutive, observations=changed)
    with pytest.raises(EventStudyInputError, match="entry and exit roles"):
        require_synthetic_event_study_batch(rebuilt)

    changed_value = tuple(
        dataclasses.replace(
            item,
            benchmark_valuation_total_return_index_value=Decimal("150"),
            benchmark_exit_total_return_index_value=Decimal("150"),
            benchmark_total_return=Decimal("0.5"),
            excess_total_return=item.security_total_return - Decimal("0.5"),
        )
        if item.row_id == "row-1" and item.horizon_sessions == 1
        else item
        for item in consecutive.observations
    )
    with pytest.raises(EventStudyInputError, match="value/source fact changed"):
        require_synthetic_event_study_batch(
            _self_rehash(consecutive, observations=changed_value)
        )


def test_security_series_source_is_bound_by_actual_valuation_session():
    sessions = _sessions()
    first_index = _decision_index()
    second_index = first_index + 1
    decisions = (
        _decision(),
        _decision(
            row_id="row-2",
            session=sessions[second_index],
            component="component-2",
        ),
    )
    required_sessions = {
        sessions[first_index],
        sessions[second_index],
        *(sessions[first_index + horizon] for horizon in HORIZONS),
        *(sessions[second_index + horizon] for horizon in HORIZONS),
    }
    securities = tuple(
        _security_open(session, "100") for session in sorted(required_sessions)
    )
    benchmarks = tuple(
        _benchmark_open(session) for session in sorted(required_sessions)
    )
    batch = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
    )
    changed = tuple(
        dataclasses.replace(item, security_entry_source_sha256=_sha("f"))
        if item.row_id == "row-2"
        else item
        for item in batch.observations
    )
    rebuilt = _self_rehash(batch, observations=changed)
    with pytest.raises(
        EventStudyInputError,
        match="series-session value/source fact",
    ):
        require_synthetic_event_study_batch(rebuilt)

    changed_value = tuple(
        dataclasses.replace(
            item,
            security_exit_total_return_index_value=Decimal("150"),
            security_total_return=Decimal("0.5"),
            excess_total_return=Decimal("0.5"),
        )
        if item.row_id == "row-1" and item.horizon_sessions == 1
        else item
        for item in batch.observations
    )
    with pytest.raises(EventStudyInputError, match="value/source fact changed"):
        require_synthetic_event_study_batch(
            _self_rehash(batch, observations=changed_value)
        )

    missing_entries = tuple(
        event_study_module._refusal(
            decisions[1], horizon, "missing_security_entry_open"
        )
        for horizon in HORIZONS
    )
    rebuilt = _self_rehash(
        batch,
        observations=tuple(
            item for item in batch.observations if item.row_id == "row-1"
        ),
        refusals=missing_entries,
    )
    with pytest.raises(EventStudyInputError, match="security entry availability"):
        require_synthetic_event_study_batch(rebuilt)

    missing_exit = event_study_module._refusal(
        decisions[0], 1, "missing_security_exit_open"
    )
    rebuilt = _self_rehash(
        batch,
        observations=tuple(
            item
            for item in batch.observations
            if not (item.row_id == "row-1" and item.horizon_sessions == 1)
        ),
        refusals=(missing_exit,),
    )
    with pytest.raises(EventStudyInputError, match="security exit availability"):
        require_synthetic_event_study_batch(rebuilt)


def test_self_rehashed_refusals_cannot_contradict_shared_benchmark_availability():
    decisions, securities, benchmarks = _two_security_fixture()
    batch = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
    )
    remaining = tuple(
        item for item in batch.observations if item.horizon_sessions != 1
    )
    exit_refusals = (
        event_study_module._refusal(
            decisions[0], 1, "missing_security_exit_open"
        ),
        event_study_module._refusal(
            decisions[1], 1, "missing_benchmark_exit_open"
        ),
    )
    rebuilt = _self_rehash(
        batch, observations=remaining, refusals=exit_refusals
    )
    with pytest.raises(EventStudyInputError, match="benchmark exit availability"):
        require_synthetic_event_study_batch(rebuilt)

    entry_refusals = tuple(
        event_study_module._refusal(
            decision,
            horizon,
            (
                "missing_security_exit_open"
                if decision.row_id == "row-1"
                else "missing_benchmark_entry_open"
            ),
        )
        for decision in decisions
        for horizon in HORIZONS
    )
    rebuilt = _self_rehash(batch, observations=(), refusals=entry_refusals)
    with pytest.raises(EventStudyInputError, match="benchmark entry availability"):
        require_synthetic_event_study_batch(rebuilt)


def test_missing_benchmark_claims_cannot_contradict_cross_role_session_proofs():
    decisions, securities, benchmarks = _staggered_two_security_fixture(1)
    batch = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
    )

    # The first decision's H1 exit is the second decision's entry. A missing
    # exit claim cannot coexist with the benchmark fact retained in the second
    # row's entry role, even though the decision/horizon keys differ.
    retained = tuple(
        item
        for item in batch.observations
        if not (item.row_id == "row-1" and item.horizon_sessions == 1)
    )
    missing_exit = event_study_module._refusal(
        decisions[0], 1, "missing_benchmark_exit_open"
    )
    rebuilt = _self_rehash(
        batch,
        observations=retained,
        refusals=(missing_exit,),
    )
    with pytest.raises(EventStudyInputError, match="benchmark exit availability"):
        require_synthetic_event_study_batch(rebuilt)

    # The same physical fact is an exit for row 1 and the entry for row 2.
    # Remove row 2 entirely and forge its four row-invariant entry refusals.
    retained = tuple(
        item for item in batch.observations if item.row_id == "row-1"
    )
    missing_entries = tuple(
        event_study_module._refusal(
            decisions[1], horizon, "missing_benchmark_entry_open"
        )
        for horizon in HORIZONS
    )
    rebuilt = _self_rehash(
        batch,
        observations=retained,
        refusals=missing_entries,
    )
    with pytest.raises(EventStudyInputError, match="benchmark entry availability"):
        require_synthetic_event_study_batch(rebuilt)


def test_missing_terminal_benchmark_claim_conflicts_with_refusal_implied_proof():
    sessions = _sessions()
    entry = _decision_index()
    terminal_session = sessions[entry + 10]
    decisions, securities, benchmarks = _staggered_two_security_fixture(9)
    requirement = _terminal_requirement(session=terminal_session)
    benchmark_sessions = {item.session for item in benchmarks}
    if terminal_session not in benchmark_sessions:
        benchmarks = tuple(
            sorted(
                (*benchmarks, _benchmark_open(terminal_session)),
                key=lambda item: item.session,
            )
        )
    batch = _collect(
        decisions=decisions,
        security_opens=securities,
        benchmark_opens=benchmarks,
        terminal_requirements=(requirement,),
        terminal_payoffs=(_terminal_payoff(requirement, value="50"),),
    )

    # Row 2's H1 security-exit refusal is reachable only after SPY at that
    # same session was found. That session is row 1's terminal valuation, so
    # row 1 cannot simultaneously claim the benchmark valuation is missing.
    retained = tuple(
        item
        for item in batch.observations
        if not (
            (item.row_id == "row-1" and item.horizon_sessions in {20, 60})
            or (item.row_id == "row-2" and item.horizon_sessions == 1)
        )
    )
    forged_refusals = (
        event_study_module._refusal(
            decisions[0], 20, "missing_benchmark_valuation_open"
        ),
        event_study_module._refusal(
            decisions[0], 60, "missing_benchmark_valuation_open"
        ),
        event_study_module._refusal(
            decisions[1], 1, "missing_security_exit_open"
        ),
    )
    rebuilt = _self_rehash(
        batch,
        observations=retained,
        refusals=forged_refusals,
    )
    with pytest.raises(EventStudyInputError, match="valuation availability changed"):
        require_synthetic_event_study_batch(rebuilt)


def test_self_rehashed_batch_cannot_return_to_security_path_after_terminal():
    requirement = _terminal_requirement()
    payoff = _terminal_payoff(requirement)
    batch = _collect(
        terminal_requirements=(requirement,), terminal_payoffs=(payoff,)
    )
    h60 = batch.observations[-1]
    refusal = event_study_module._refusal(
        _decision(), h60.horizon_sessions, "missing_security_exit_open"
    )
    rebuilt = _self_rehash(
        batch,
        observations=batch.observations[:-1],
        refusals=(refusal,),
    )
    with pytest.raises(EventStudyInputError, match="ordinary observation"):
        require_synthetic_event_study_batch(rebuilt)

    h20 = batch.observations[-2]
    terminal_refusal = event_study_module._refusal(
        _decision(), h20.horizon_sessions, "missing_terminal_shareholder_payoff"
    )
    ordinary_h60 = dataclasses.replace(
        h60,
        terminal_payoff_used=False,
        security_exit_total_return_index_value=Decimal("160"),
        terminal_requirement_id=None,
        terminal_event_kind=None,
        terminal_session=None,
        terminal_listing_id=None,
        terminal_historical_ticker=None,
        valuation_session=h60.exit_session,
        valuation_security_id=h60.security_id,
        successor_security_id=None,
        successor_listing_id=None,
        successor_historical_ticker=None,
        security_total_return=Decimal("0.60"),
        excess_total_return=Decimal("0.60"),
        security_exit_source_sha256=_sha("b"),
    )
    rebuilt = _self_rehash(
        batch,
        observations=(*batch.observations[:2], ordinary_h60),
        refusals=(terminal_refusal,),
    )
    with pytest.raises(EventStudyInputError, match="ordinary observation"):
        require_synthetic_event_study_batch(rebuilt)


def test_self_rehashed_refusal_cannot_hide_geometry_or_malformed_fields():
    outside = _collect(
        decisions=(_decision(
            evaluation_segment_id="arv2-wf-test-2020",
            fold_id="arv2-wf-test-2020",
        ),)
    )
    mislabeled = tuple(
        dataclasses.replace(item, reason="missing_security_entry_open")
        for item in outside.refusals
    )
    rebuilt = _self_rehash(outside, refusals=mislabeled)
    with pytest.raises(EventStudyInputError, match="outside its segment"):
        require_synthetic_event_study_batch(rebuilt)
    malformed = dataclasses.replace(outside.refusals[0], row_id="", horizon_sessions=True)
    rebuilt = _self_rehash(
        outside, refusals=(malformed, *outside.refusals[1:])
    )
    with pytest.raises(EventStudyInputError, match="canonical string|reviewed horizons"):
        require_synthetic_event_study_batch(rebuilt)


def test_batch_census_is_aggregate_only_and_has_no_action_authority():
    batch = _collect()
    census = batch.aggregate_census()
    assert census["terminal_payoff_reinvestment_policy_id"] == (
        TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID
    )
    assert census["expected_decision_horizons"] == 4
    assert census["accepted_observations"] == 4
    assert census["named_refusals"] == 0
    assert census["terminal_payoff_observations"] == 0
    assert census["refusals_by_reason"] == {}
    assert "security_id" not in census and "return" not in census
    assert batch.result_publication_available is False
    assert batch.orders_available is False
    assert batch.trading_available is False


@pytest.mark.parametrize(
    "mutator,message",
    ((lambda rows: list(rows), "exact tuple"),
     (lambda rows: rows + (rows[0],), "keys must be unique")),
)
def test_input_container_or_duplicate_open_key_refuses(mutator, message):
    sessions, securities, benchmarks = _complete_price_fixture()
    with pytest.raises(EventStudyInputError, match=message):
        collect_synthetic_event_study(
            run_candidate=_candidate(), session_axis=sessions,
            decisions=(_decision(),), security_opens=mutator(securities),
            benchmark_opens=benchmarks,
            security_lifecycle_coverages=_lifecycle_coverages((_decision(),), ()),
            terminal_requirements=(), terminal_payoffs=(),
        )


def test_run_candidate_binds_exact_files_but_grants_no_capability():
    candidate = _candidate()
    assert require_synthetic_qc_run_candidate(candidate) is candidate
    assert candidate.candidate_id.endswith(candidate.candidate_hash[:16])
    assert all(value is None for _, value in candidate.external_bindings)
    assert all(value is False for _, value in candidate.capabilities)
    assert all(getattr(candidate, name) is False for name in (
        "upload_available", "compile_available", "launch_available",
        "result_access_available", "deployment_available", "orders_available",
        "trading_available",
    ))


def test_run_candidate_inventory_covers_the_parent_qc_phase_contract():
    names = {name for name, _ in _candidate().external_bindings}
    assert {
        "data_entitlement_audit_id", "vendor_to_qc_processing_rights_receipt_id",
        "owner_source_capture_authority_id", "immutable_snapshot_id",
        "normalization_receipt_id", "owner_qc_upload_authority_id",
        "upload_receipt_id", "owner_qc_compile_authority_id", "compile_receipt_id",
        "authority_phase_lineage_sha256", "qc_plan_sha256",
        "atomic_evaluation_receipt_id", "qc_backtest_id_or_ambiguous_submission_lock",
        "pre_outcome_power_plan_sha256",
    } <= names


def test_run_candidate_identity_is_deterministic_and_order_independent():
    forward = _candidate()
    reverse = build_synthetic_qc_run_candidate(
        code_files=(_code_binding(),),
        synthetic_partitions=tuple(reversed(forward.synthetic_partitions)),
    )
    assert reverse.candidate_hash == forward.candidate_hash
    changed_code = dataclasses.replace(_code_binding(), sha256=_sha("e"))
    changed = build_synthetic_qc_run_candidate(
        code_files=(changed_code,), synthetic_partitions=forward.synthetic_partitions
    )
    assert changed.candidate_hash != forward.candidate_hash


def test_builder_copies_caller_owned_bindings_before_authentication():
    code = _code_binding()
    partitions = _candidate().synthetic_partitions
    candidate = build_synthetic_qc_run_candidate(
        code_files=(code,), synthetic_partitions=partitions
    )
    original_hash = candidate.candidate_hash
    object.__setattr__(code, "sha256", _sha("f"))
    object.__setattr__(partitions[0], "sha256", _sha("e"))
    assert candidate.code_files[0].sha256 != _sha("f")
    assert candidate.synthetic_partitions[0].sha256 != _sha("e")
    assert require_synthetic_qc_run_candidate(candidate).candidate_hash == original_hash


def test_run_candidate_refuses_licensed_real_or_incomplete_partitions():
    partitions = _candidate().synthetic_partitions
    for field in ("synthetic_fixture", "contains_licensed_rows", "contains_real_outcomes"):
        replacement = False if field == "synthetic_fixture" else True
        bad = dataclasses.replace(partitions[0], **{field: replacement})
        with pytest.raises(QcRunContractError, match="synthetic fixture"):
            build_synthetic_qc_run_candidate(
                code_files=(_code_binding(),),
                synthetic_partitions=(bad, *partitions[1:]),
            )
    with pytest.raises(QcRunContractError, match="complete and exact"):
        build_synthetic_qc_run_candidate(
            code_files=(_code_binding(),), synthetic_partitions=partitions[:-1]
        )


def test_run_candidate_refuses_a_safe_but_wrong_partition_schema():
    partitions = _candidate().synthetic_partitions
    wrong = dataclasses.replace(partitions[0], schema="arv2-synthetic-wrong-v1")
    with pytest.raises(QcRunContractError, match="role-exact"):
        build_synthetic_qc_run_candidate(
            code_files=(_code_binding(),),
            synthetic_partitions=(wrong, *partitions[1:]),
        )


def test_run_candidate_refuses_duplicate_partition_roles_even_with_unique_ids():
    partitions = _candidate().synthetic_partitions
    duplicate = dataclasses.replace(
        partitions[0], partition_id="fixture/duplicate-role.jsonl"
    )
    with pytest.raises(QcRunContractError, match="complete and exact"):
        build_synthetic_qc_run_candidate(
            code_files=(_code_binding(),),
            synthetic_partitions=(*partitions, duplicate),
        )


@pytest.mark.parametrize(
    "field,value",
    (("relative_path", "./event_study.py"), ("relative_path", "/event_study.py"),
     ("relative_path", "research//event_study.py"),
     ("relative_path", "research/../event_study.py"),
     ("upload_name", "folder/event_study.py"), ("upload_name", "event_study.py/"),
     ("upload_name", "main.py")),
)
def test_run_candidate_refuses_unsafe_or_false_entry_paths(field, value):
    binding = dataclasses.replace(_code_binding(), **{field: value})
    message = "no LEAN main.py" if value == "main.py" else "unsafe"
    with pytest.raises(QcRunContractError, match=message):
        build_synthetic_qc_run_candidate(
            code_files=(binding,), synthetic_partitions=_candidate().synthetic_partitions
        )


def test_run_candidate_refuses_string_subclass_roles():
    class Text(str):
        pass

    code = dataclasses.replace(_code_binding(), role=Text("event_study_core"))
    with pytest.raises(QcRunContractError, match="role is unknown"):
        build_synthetic_qc_run_candidate(
            code_files=(code,), synthetic_partitions=_candidate().synthetic_partitions
        )
    partition = dataclasses.replace(
        _candidate().synthetic_partitions[0], role=Text("benchmark_open_values")
    )
    with pytest.raises(QcRunContractError, match="role is unknown"):
        build_synthetic_qc_run_candidate(
            code_files=(_code_binding(),),
            synthetic_partitions=(partition, *_candidate().synthetic_partitions[1:]),
        )


def test_run_candidate_refuses_duplicate_upload_or_mutated_identity():
    duplicate = _code_binding()
    with pytest.raises(QcRunContractError, match="relative paths"):
        build_synthetic_qc_run_candidate(
            code_files=(_code_binding(), duplicate),
            synthetic_partitions=_candidate().synthetic_partitions,
        )
    candidate = _candidate()
    object.__setattr__(candidate, "candidate_hash", _sha("f"))
    with pytest.raises(QcRunContractError, match="changed"):
        require_synthetic_qc_run_candidate(candidate)


def test_run_candidate_refuses_mutated_canonical_document_type():
    candidate = _candidate()
    object.__setattr__(
        candidate, "_canonical_document", bytearray(candidate._canonical_document)
    )
    with pytest.raises(QcRunContractError, match="container type changed"):
        require_synthetic_qc_run_candidate(candidate)


@pytest.mark.parametrize("field", ("external_bindings", "capabilities"))
def test_mapping_proxy_cannot_impersonate_immutable_candidate_state(field):
    candidate = _candidate()
    object.__setattr__(candidate, field, MappingProxyType({}))
    with pytest.raises(QcRunContractError, match="binding|capability"):
        require_synthetic_qc_run_candidate(candidate)


def test_content_equivalent_reconstruction_is_revalidated_without_authority():
    reconstructed = dataclasses.replace(_candidate())
    assert require_synthetic_qc_run_candidate(reconstructed) is reconstructed
    assert all(value is None for _, value in reconstructed.external_bindings)
    assert all(value is False for _, value in reconstructed.capabilities)


def test_candidate_subclass_cannot_impersonate_the_exact_contract_type():
    class CandidateSubclass(SyntheticQcRunCandidate):
        pass

    candidate = _candidate()
    subclass = CandidateSubclass(
        candidate_id=candidate.candidate_id, candidate_hash=candidate.candidate_hash,
        code_files=candidate.code_files,
        synthetic_partitions=candidate.synthetic_partitions,
        external_bindings=candidate.external_bindings,
        capabilities=candidate.capabilities,
        _canonical_document=candidate._canonical_document,
    )
    with pytest.raises(QcRunContractError, match="not been built"):
        require_synthetic_qc_run_candidate(subclass)


def test_mutated_candidate_order_is_not_accepted_as_canonical():
    candidate = _candidate()
    object.__setattr__(candidate, "synthetic_partitions", tuple(
        reversed(candidate.synthetic_partitions)
    ))
    with pytest.raises(QcRunContractError, match="changed"):
        require_synthetic_qc_run_candidate(candidate)


def test_parent_artifact_hashes_match_the_reviewed_files():
    for binding in PARENT_ARTIFACTS:
        path = ROOT / Path(*binding.relative_path.split("/"))
        assert path.is_file(), binding
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding.artifact_sha256


def test_exported_parent_and_evaluation_records_cannot_mutate_candidate_policy():
    parent = PARENT_ARTIFACTS[0]
    parent_hash = parent.artifact_sha256
    try:
        object.__setattr__(parent, "artifact_sha256", _sha("f"))
        with pytest.raises(QcRunContractError, match="parent artifact identity"):
            _candidate()
    finally:
        object.__setattr__(parent, "artifact_sha256", parent_hash)

    window = EVALUATION_WINDOWS[0]
    segment_ids = window.evaluation_segment_ids
    try:
        object.__setattr__(window, "evaluation_segment_ids", ("forged-segment",))
        with pytest.raises(QcRunContractError, match="evaluation-window identity"):
            _candidate()
    finally:
        object.__setattr__(window, "evaluation_segment_ids", segment_ids)

    policy_id = run_contract_module.TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID
    try:
        run_contract_module.TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID = (
            "arv2-terminal-payoff-benchmark-splice-v2"
        )
        with pytest.raises(QcRunContractError, match="reinvestment policy changed"):
            _candidate()
    finally:
        run_contract_module.TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID = policy_id
    assert require_synthetic_qc_run_candidate(_candidate())


@pytest.mark.parametrize(
    ("name", "forged"),
    [
        ("SCHEMA", "arv2-qc-stock-event-study-run-candidate-v3"),
        ("STATUS", "reviewed"),
        ("AUTHORITY", "production"),
        ("EVALUATION_ID", "arv2-eval-stock-historical-qc-002"),
        ("ALGORITHM_ID", "arv2-qc-stock-event-study-core-v3"),
        ("CORE_RELATIVE_PATH", "research/forged.py"),
        ("CORE_UPLOAD_NAME", "forged.py"),
    ],
)
def test_exported_scalar_run_identities_are_load_bearing(
    monkeypatch, name, forged
):
    monkeypatch.setattr(run_contract_module, name, forged)
    with pytest.raises(
        QcRunContractError,
        match=(
            "static run-contract identity changed|"
            "event-study core path identity changed"
        ),
    ):
        _candidate()


@pytest.mark.parametrize("name", ["CORE_RELATIVE_PATH", "CORE_UPLOAD_NAME"])
def test_static_identity_preflight_refuses_hostile_strings_without_comparison(
    monkeypatch, name
):
    calls = []

    class HostileIdentity(str):
        def __eq__(self, other):
            calls.append(("eq", other))
            raise AssertionError("hostile equality executed")

        def __ne__(self, other):
            calls.append(("ne", other))
            raise AssertionError("hostile inequality executed")

    monkeypatch.setattr(
        run_contract_module,
        name,
        HostileIdentity(getattr(run_contract_module, name)),
    )
    with pytest.raises(QcRunContractError, match="static run-contract identity changed"):
        _candidate()
    assert calls == []


def test_event_study_rejects_a_mutated_reinvestment_policy_constant(monkeypatch):
    monkeypatch.setattr(
        event_study_module,
        "TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID",
        "arv2-terminal-payoff-benchmark-splice-v2",
    )
    with pytest.raises(EventStudyInputError, match="reinvestment policy changed"):
        _collect()


def test_run_contract_and_event_study_share_one_reviewed_horizon_contract():
    assert run_contract_module.HORIZONS is HORIZONS
    assert HORIZONS == (1, 5, 20, 60)
    assert run_contract_module.PRIMARY_HORIZON == 20
    original = run_contract_module.HORIZONS
    try:
        run_contract_module.HORIZONS = (1, 5, 20, 61)
        with pytest.raises(QcRunContractError, match="horizon contract"):
            _candidate()
    finally:
        run_contract_module.HORIZONS = original


def test_hard_coded_fold_bounds_match_both_reviewed_parent_artifacts():
    folds_path = ROOT / "research" / "analyst_revisions_v2" / "specs" / (
        "arv2_stock_walk_forward_folds.structural.json"
    )
    supplement_path = ROOT / "research" / "analyst_revisions_v2" / "specs" / (
        "arv2_stock_post_pandemic_evaluation.structural.json"
    )
    folds = json.loads(folds_path.read_text(encoding="utf-8"))
    expected: dict[str, dict[int, tuple[date, date]]] = {}
    for fold in folds["walk_forward_contract"]["folds"]:
        expected[fold["fold_id"]] = {
            item["horizon_sessions"]: (
                date.fromisoformat(item["test_start"]),
                date.fromisoformat(item["test_end_exclusive"]),
            )
            for item in fold["horizon_boundaries"]
        }
    supplement = json.loads(supplement_path.read_text(encoding="utf-8"))
    partial = supplement["partial_2026_exploratory_contract"]
    expected["arv2-partial-2026-exploratory"] = {
        item["horizon_sessions"]: (
            date.fromisoformat(item["effective_test_start"]),
            date.fromisoformat(item["test_end_exclusive"]),
        )
        for item in partial["eligible_decision_bounds"]
    }
    assert {
        fold: dict(bounds)
        for fold, bounds in (
            event_study_module._EVALUATION_SEGMENT_HORIZON_BOUNDS.items()
        )
    } == expected


def test_code_declaration_hash_recipe_is_cross_checkout_canonical_lf():
    lf = b"from __future__ import annotations\nvalue = 1\n"
    crlf = lf.replace(b"\n", b"\r\n")
    assert canonical_lf_python_source_bytes(lf) == lf
    assert canonical_lf_python_source_bytes(crlf) == lf
    with pytest.raises(QcRunContractError, match="BOM"):
        canonical_lf_python_source_bytes(b"\xef\xbb\xbf" + lf)
    with pytest.raises(QcRunContractError, match="bare carriage"):
        canonical_lf_python_source_bytes(b"value = 1\rvalue = 2\n")


def test_evaluation_windows_preserve_primary_sensitivity_and_partial_separation():
    primary, sensitivity, partial = EVALUATION_WINDOWS
    assert primary.fold_ids == tuple(f"arv2-wf-test-{year}" for year in range(2020, 2026))
    assert sensitivity.fold_ids == tuple(
        f"arv2-wf-test-{year}" for year in range(2021, 2026)
    )
    assert partial.fold_ids == ()
    assert primary.evaluation_segment_ids == primary.fold_ids
    assert sensitivity.evaluation_segment_ids == sensitivity.fold_ids
    assert partial.evaluation_segment_ids == ("arv2-partial-2026-exploratory",)
    assert sensitivity.pooled_with_primary is False
    assert partial.pooled_with_primary is False
    assert "cannot_replace_or_rescue" in sensitivity.claim
    assert "never_pooled" in partial.claim


def test_canonical_run_candidate_pins_the_exact_non_authoritative_policy():
    document = json.loads(_candidate()._canonical_document)
    assert document["schema"] == "arv2-qc-stock-event-study-run-candidate-v2"
    assert document["status"] == (
        "synthetic_fixture_only_pending_independent_review_and_production_bindings"
    )
    assert document["authority"] == (
        "structure_only_no_source_outcome_qc_result_deployment_or_trading_authority"
    )
    assert document["algorithm_id"] == "arv2-qc-stock-event-study-core-v2"
    assert document["evaluation_id"] == "arv2-eval-stock-historical-qc-001"
    assert document["horizons_sessions"] == [1, 5, 20, 60]
    assert document["primary_horizon_sessions"] == 20
    assert document["input_policy"] == {
        "transport": "future_immutable_qc_custom_data_binding",
        "vendor_api_calls_inside_algorithm": False,
        "current_ticker_identity_allowed": False,
        "permanent_security_and_listing_identity_required": True,
        "complete_decision_and_successor_lifecycle_coverage_through": (
            "2026-08-28"
        ),
        "terminal_payoff_source_required_when_inventory_marks_terminal": True,
        "qc_delisting_price_is_terminal_shareholder_payoff": False,
        "terminal_payoff_reinvestment": {
            "policy_id": TERMINAL_PAYOFF_REINVESTMENT_POLICY_ID,
            "applies_to": ["bankruptcy", "cash_merger", "delisting"],
            "reinvestment_session": (
                "terminal_valuation_session_open_with_proven_economic_availability"
            ),
            "horizon_security_value": (
                "terminal_payoff_times_spy_horizon_open_divided_by_"
                "spy_reinvestment_open"
            ),
            "post_terminal_abnormal_exposure": "zero",
            "scheduled_horizon_is_preserved": True,
            "stock_and_mixed_mergers_follow_successor_to_horizon": True,
            "terminal_date_alone_proves_economic_availability": False,
        },
        "row_or_named_refusal_for_every_decision_horizon": True,
    }
    assert document["result_policy"] == {
        "algorithm_places_orders": False,
        "security_level_prices_or_returns_exported": False,
        "aggregate_reports_only_after_separate_result_authority": True,
        "formal_primary_can_be_replaced_or_rescued_by_sensitivity": False,
        "partial_2026_can_be_pooled": False,
        "dispositions": ["PASS", "FAIL", "INCONCLUSIVE", "INVALID-DATA"],
    }
    assert document["execution_policy"] == {
        "project_name_pattern": "[number]. ARV2_STOCK_EVENT_STUDY - [YYYYMMDD]",
        "one_frozen_run_computes_primary_and_sensitivities": True,
        "lean_algorithm_entry_present": False,
        "qc_compile_candidate": False,
        "atomic_claim_required_before_backtests_create": True,
        "ambiguous_submission_blocks_retry_until_reconciled": True,
        "generic_stage0_runner_allowed": False,
        "candidate_scope": (
            "partial_synthetic_candidate_requires_a_new_reviewed_production_run_schema"
        ),
        "code_binding_recipe": "strict_utf8_without_bom_canonical_lf_bytes",
        "candidate_hash_authenticates_loaded_code": False,
    }
    expected_external_bindings = (
        "reviewed_spec_hash",
        "qc_first_plan_hash",
        "review_commit",
        "counter_review_commit",
        "data_entitlement_audit_id",
        "vendor_to_qc_processing_rights_receipt_id",
        "owner_source_capture_authority_id",
        "immutable_snapshot_id",
        "raw_inventory_sha256",
        "reviewed_source_ontology_identity_contracts",
        "owner_normalization_authority_id",
        "dataset_id",
        "normalization_receipt_id",
        "owner_qc_upload_authority_id",
        "qc_project_id",
        "custom_data_sha256",
        "upload_receipt_id",
        "algorithm_sha256",
        "config_sha256",
        "owner_qc_compile_authority_id",
        "qc_compile_id",
        "compile_receipt_id",
        "authority_phase_lineage_sha256",
        "complete_reviewed_v2_spec_and_all_definition_hashes",
        "qc_plan_sha256",
        "owner_backtest_launch_authority_id",
        "external_evaluation_authority_id",
        "atomic_evaluation_receipt_id",
        "evaluation_claimed_at",
        "owner_qc_launch_authority_id",
        "qc_backtest_id_or_ambiguous_submission_lock",
        "code_identity",
        "deterministic_backtest_name",
        "lean_engine_version",
        "qc_data_version_disclosures",
        "period",
        "controls",
        "costs",
        "pre_outcome_power_plan_sha256",
        "production_input_manifest_id",
        "production_input_manifest_sha256",
        "production_truth_approval_id",
        "numeric_power_receipt_id",
        "numeric_power_receipt_sha256",
        "stock_power_successor_v3_id",
        "stock_power_successor_v3_sha256",
        "deterministic_project_name",
    )
    expected_capabilities = (
        "production_source_access",
        "licensed_input_read",
        "real_outcome_access",
        "qc_object_store_write",
        "qc_upload",
        "qc_compile",
        "qc_launch",
        "result_access",
        "result_disposition",
        "deployment",
        "orders",
        "trading",
    )
    assert tuple(document["external_bindings"]) == tuple(
        sorted(expected_external_bindings)
    )
    assert document["external_bindings"] == {
        name: None for name in expected_external_bindings
    }
    assert _candidate().external_bindings == tuple(
        (name, None) for name in expected_external_bindings
    )
    assert tuple(document["capabilities"]) == tuple(sorted(expected_capabilities))
    assert document["capabilities"] == {
        name: False for name in expected_capabilities
    }
    assert _candidate().capabilities == tuple(
        (name, False) for name in expected_capabilities
    )


def test_future_commit_shape_helper_is_not_an_authority():
    assert commit_identity_shape_is_valid("a" * 40) is True
    assert commit_identity_shape_is_valid("A" * 40) is False
    assert commit_identity_shape_is_valid(True) is False
    assert dict(_candidate().external_bindings)["review_commit"] is None


def test_qc_contract_and_core_have_no_file_dynamic_adapter_or_action_surface():
    allowed_imports = {
        CORE: {
            "__future__", "collections", "data", "dataclasses", "datetime",
            "decimal", "functools", "hashlib", "json", "run_contract",
            "types", "typing",
        },
        CONTRACT: {
            "__future__", "dataclasses", "hashlib", "json", "re", "types",
            "typing",
        },
    }
    forbidden_call_names = {
        "set_holdings", "market_order", "limit_order", "stop_market_order",
        "liquidate", "create_backtest", "read_backtest", "update_file",
        "requests", "urlopen", "open", "__import__", "eval", "exec", "compile",
    }
    forbidden_call_attributes = forbidden_call_names - {
        "__import__", "eval", "exec", "compile"
    }
    for path, allowed_roots in allowed_imports.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_roots = {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        } | {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert imported_roots <= allowed_roots
        assert not any(
            isinstance(node, ast.ClassDef)
            and any(
                isinstance(base, ast.Name) and base.id == "QCAlgorithm"
                for base in node.bases
            )
            for node in ast.walk(tree)
        )
        called_names = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        called_attributes = {
            node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not forbidden_call_names & called_names
        assert not forbidden_call_attributes & called_attributes

    core_tree = ast.parse(CORE.read_text(encoding="utf-8"))
    absolute_imports = {
        node.module
        for node in ast.walk(core_tree)
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module
    }
    assert {name for name in absolute_imports if name.startswith("data.")} == {
        "data.exchange_calendar"
    }
    assert {
        (node.level, node.module)
        for node in ast.walk(core_tree)
        if isinstance(node, ast.ImportFrom) and node.level > 0
    } == {(1, "run_contract")}


def test_action_and_runtime_authentication_accessors_are_literal_false():
    expected = {
        CONTRACT: {
            "SyntheticQcRunCandidate": {
                "upload_available",
                "execution_code_authenticated",
                "compile_available",
                "launch_available",
                "result_access_available",
                "deployment_available",
                "orders_available",
                "trading_available",
            }
        },
        CORE: {
            "EventStudyBatch": {
                "result_publication_available",
                "execution_code_authenticated",
                "orders_available",
                "trading_available",
            }
        },
    }
    for path, class_methods in expected.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        classes = {
            node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
        }
        for class_name, method_names in class_methods.items():
            methods = {
                node.name: node
                for node in classes[class_name].body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            assert method_names <= methods.keys()
            for method_name in method_names:
                body = methods[method_name].body
                assert len(body) == 1
                assert isinstance(body[0], ast.Return)
                assert isinstance(body[0].value, ast.Constant)
                assert body[0].value.value is False


def test_output_validation_uses_constant_time_reviewed_session_lookups():
    tree = ast.parse(CORE.read_text(encoding="utf-8"))
    validators = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_validate_observation", "_validate_refusal"}
    }
    assert validators.keys() == {"_validate_observation", "_validate_refusal"}
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "index"
        for function in validators.values()
        for node in ast.walk(function)
    )
    assert not hasattr(event_study_module, "_ARITHMETIC_CONTEXT")


def test_outcome_free_core_cannot_reverse_import_the_qc_sibling(tmp_path: Path):
    assert "research.analyst_revisions_v2_qc" in DEFAULT_FORBIDDEN_IMPORT_PREFIXES
    guarded = tmp_path / "guarded"
    guarded.mkdir()
    (guarded / "__init__.py").write_text(
        "import research.analyst_revisions_v2_qc.event_study\n", encoding="utf-8"
    )
    with pytest.raises(ImportBoundaryError, match="analyst_revisions_v2_qc"):
        _validate_import_closure(tmp_path, package_name="guarded")


@pytest.mark.parametrize("event_kind", ["stock_merger", "mixed_merger"])
def test_off_horizon_stock_consideration_valuation_is_an_input_error_not_a_refusal(
    event_kind,
):
    # ARV2R31-002: a stock-consideration payoff valued on a session that is not
    # a decision horizon must be an input error; without the guard it is
    # silently unmatched and degrades to a missing-payoff refusal.
    decisions, securities, benchmarks, requirements, payoffs = (
        _covered_stock_merger_fixture(event_kind)
    )
    (requirement,) = requirements
    h20, h60 = payoffs
    off_horizon = dataclasses.replace(
        h20, valuation_session=_sessions()[_decision_index() + 21]
    )
    assert off_horizon.valuation_session > requirement.terminal_session
    with pytest.raises(EventStudyInputError, match="not a decision horizon"):
        _collect(
            decisions=decisions,
            security_opens=securities,
            benchmark_opens=benchmarks,
            terminal_requirements=requirements,
            terminal_payoffs=(off_horizon, h60),
        )


@pytest.mark.parametrize(
    "field_name", ["candidate_declaration_hash", "input_partition_set_sha256"]
)
def test_identity_tamper_without_rehash_is_caught_by_the_batch_hash_alone(field_name):
    # ARV2R31-003: these two fields are only format-checked by the validator, so
    # a tamper that keeps a valid SHA-256 shape must be refused by the batch
    # hash recomputation itself.
    batch = _collect()
    forged = "0" * 64
    assert getattr(batch, field_name) != forged
    object.__setattr__(batch, field_name, forged)
    with pytest.raises(EventStudyInputError, match="changed after construction"):
        require_synthetic_event_study_batch(batch)
