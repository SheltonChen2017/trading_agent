"""Offline tests for the production-shaped ARV2 formal evaluator."""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
import threading
from collections import Counter
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN, localcontext
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import formal_evaluation as evaluation_module
from research.analyst_revisions_v2_qc.formal_report_contract import (
    build_formal_report_contract,
    formal_report_contract_record,
)

FormalEvaluationError = evaluation_module.FormalEvaluationError
MODULE = (
    Path(__file__).resolve().parents[2]
    / "research/analyst_revisions_v2_qc/formal_evaluation.py"
)


# Production-shaped evaluator successor tests.

def _sha(label: str) -> str:
    import hashlib
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _session_dates(start: str, end_exclusive: str) -> tuple[date, ...]:
    return tuple(
        item
        for item in trading_sessions(
            date.fromisoformat(start), date.fromisoformat(end_exclusive)
        )
        if item.isoformat() < end_exclusive
    )


def _authenticated_power_floor() -> evaluation_module.PowerFloorBinding:
    return evaluation_module.PowerFloorBinding(
        receipt_id="power-receipt-1",
        receipt_sha256=_sha("power"),
        required_valid_dates=50,
        required_connected_components=50,
        h20_test_session_capacity=1388,
        preoutcome_candidate_date_count=100,
        valid_h20_test_session_count=100,
        refused_h20_test_session_count=0,
        missing_h20_test_session_count=1288,
        connected_component_instance_count=100,
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("h20_test_session_capacity", True),
        ("h20_test_session_capacity", 1387),
        ("preoutcome_candidate_date_count", 99),
        ("valid_h20_test_session_count", 49),
        ("refused_h20_test_session_count", 1),
        ("missing_h20_test_session_count", 1287),
        ("connected_component_instance_count", 49),
        ("required_valid_dates", 101),
        ("required_connected_components", 101),
    ),
)
def test_power_floor_requires_exact_authenticated_h20_census(
    field: str, replacement: object,
) -> None:
    value = _authenticated_power_floor()
    assert evaluation_module._require_power_floor_binding(
        value, context="test"
    ) is value
    with pytest.raises(FormalEvaluationError):
        evaluation_module._require_power_floor_binding(
            dataclasses.replace(value, **{field: replacement}), context="test"
        )


@lru_cache(maxsize=1)
def _exact_axes() -> tuple[evaluation_module.FoldSessionAxis, ...]:
    date_sets = [
        _session_dates(item[2], item[3])
        for item in evaluation_module.FORMAL_FOLD_HORIZON_AXIS_SUMMARIES
    ]
    economic_dates = [
        (*_session_dates(item[1], item[5]), date.fromisoformat(item[5]))
        for item in evaluation_module.ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES
    ]
    positions = {
        session: index
        for index, session in enumerate(
            sorted({item for values in (*date_sets, *economic_dates) for item in values})
        )
    }
    return tuple(
        evaluation_module.FoldSessionAxis(
            frozen[0],
            frozen[1],
            tuple(
                evaluation_module.SessionPoint(session, positions[session])
                for session in sessions
            ),
        )
        for frozen, sessions in zip(
            evaluation_module.FORMAL_FOLD_HORIZON_AXIS_SUMMARIES,
            date_sets,
            strict=True,
        )
    )


@lru_cache(maxsize=1)
def _exact_economic_axes() -> tuple[evaluation_module.EconomicObservationAxis, ...]:
    positions = {
        point.session: point.session_position
        for axis in _exact_axes()
        for point in axis.sessions
    }
    # Runoff/liquidation dates can extend beyond the fold decision axes.
    all_dates = sorted(
        {
            point.session
            for axis in _exact_axes()
            for point in axis.sessions
        }
        | {
            item
            for frozen in evaluation_module.ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES
            for item in (
                *_session_dates(frozen[1], frozen[5]),
                date.fromisoformat(frozen[5]),
            )
        }
    )
    positions = {session: index for index, session in enumerate(all_dates)}
    return tuple(
        evaluation_module.EconomicObservationAxis(
            frozen[0],
            tuple(
                evaluation_module.SessionPoint(session, positions[session])
                for session in (
                    *_session_dates(frozen[1], frozen[5]),
                    date.fromisoformat(frozen[5]),
                )
            ),
        )
        for frozen in evaluation_module.ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES
    )


def _point(year: int, offset: int, fold_index: int):
    assert year == 2020 + fold_index
    axis = next(
        item
        for item in _exact_axes()
        if item.fold_id == evaluation_module.FORMAL_FOLD_IDS[fold_index]
        and item.horizon_sessions == 20
    )
    return axis.sessions[offset]


def _controls(index: int) -> tuple[tuple[Decimal, ...], tuple[int, ...]]:
    continuous = tuple(
        Decimal(1 if (index & mask).bit_count() % 2 == 0 else -1)
        for mask in range(1, 20)
    )
    binary = tuple(
        1 if (index & mask).bit_count() % 2 == 0 else 0
        for mask in range(20, 26)
    )
    return continuous, binary


def _row(fold_index: int, security_index: int, *, horizon: int = 20,
         component: str | None = None, session_offset: int = 0,
         rating_action: str | None = None,
         earnings_anchor_signed_session_distance: int | None = None,
         gross_security_total_return: Decimal | None = None,
         benchmark_total_return: Decimal | None = None):
    fold = evaluation_module.FORMAL_FOLD_IDS[fold_index]
    axis = next(
        item
        for item in _exact_axes()
        if item.fold_id == fold and item.horizon_sessions == horizon
    )
    point = axis.sessions[session_offset]
    continuous, binary = _controls(security_index)
    active = 1 if (security_index & 27).bit_count() % 2 == 0 else 0
    score = (
        Decimal((security_index % 9) - 4) / Decimal(2)
        if active else Decimal(0)
    )
    return evaluation_module.build_evaluation_row(
        source_lineage_sha256=_sha(
            f"decision:{fold_index}:{session_offset}:{security_index}"
        ),
        fold_id=fold,
        decision_session=point.session,
        session_position=point.session_position,
        security_id=f"security-{security_index:03d}",
        industry_id=(
            f"industry-{1 if (security_index & 26).bit_count() % 2 == 0 else 0}"
        ),
        common_event_component_id=(
            component
            or f"component-{fold_index}-{session_offset}-{security_index:03d}"
        ),
        horizon_sessions=horizon,
        firm_specific_score=score,
        global_score=-score,
        structural_zero=not bool(active),
        continuous_control_values=continuous,
        binary_control_values=binary,
        active_event_indicator=active,
        absolute_contribution_weighted_publication_to_entry_jump=(
            Decimal(security_index % 7) / Decimal(100) if active else Decimal(0)
        ),
        excess_total_return=(
            gross_security_total_return - benchmark_total_return
            if gross_security_total_return is not None
            and benchmark_total_return is not None
            else score / Decimal(100)
        ),
        rating_action=rating_action,
        earnings_anchor_signed_session_distance=(
            earnings_anchor_signed_session_distance
        ),
        gross_security_total_return=gross_security_total_return,
        benchmark_total_return=benchmark_total_return,
    )


@lru_cache(maxsize=None)
def _input(
    *,
    rows_per_date: int = 64,
    source_view_id: str = evaluation_module.SOURCE_VIEW_IDS[0],
):
    axes = _exact_axes()
    economic_axes = _exact_economic_axes()
    rows = tuple(
        _row(fold_index, security_index)
        for fold_index in range(6)
        for security_index in range(rows_per_date)
    )
    h20 = {
        (row.fold_id, row.decision_session, row.security_id): row for row in rows
    }
    economic = []
    h20_axes = tuple(axis for axis in axes if axis.horizon_sessions == 20)
    for fold_index, axis in enumerate(economic_axes):
        active: list[evaluation_module._ActiveSleeve] = []
        decision_sessions = {
            point.session
            for candidate in h20_axes
            if candidate.fold_id == axis.fold_id
            for point in candidate.sessions
        }
        for point in axis.sessions:
            sources = tuple(
                row for (fold, session, _security_id), row in h20.items()
                if fold == axis.fold_id and session == point.session
            )
            decisions = tuple(
                evaluation_module.build_economic_decision(
                    decision_lineage_sha256=source.source_lineage_sha256,
                    security_id=source.security_id,
                    firm_specific_score=source.firm_specific_score,
                )
                for source in sorted(sources, key=lambda item: item.security_id)
            )
            selected = evaluation_module._v2_selected_sleeve(decisions)
            if point.session in decision_sessions:
                active.append(evaluation_module._v2_new_sleeve(selected))
            held = tuple(sorted(evaluation_module._v2_targets(active)))
            outcomes = tuple(
                evaluation_module.build_economic_security_outcome(
                    outcome_lineage_sha256=_sha(
                        f"economic:{fold_index}:{point.session_position}:{security_id}"
                    ),
                    security_id=security_id,
                    disposition=evaluation_module.EconomicOutcomeDisposition.RETURN,
                    gross_total_return=Decimal("0.001"),
                    reason=None,
                    terminal_payoff_applied=False,
                )
                for security_id in held
            )
            economic.append(evaluation_module.build_economic_session(
                source_lineage_sha256=_sha(
                    f"economic-session:{fold_index}:{point.session_position}"
                ),
                fold_id=axis.fold_id,
                session=point.session,
                session_position=point.session_position,
                benchmark_total_return=Decimal("0"),
                benchmark_refusal_reason=None,
                decisions=decisions,
                security_outcomes=outcomes,
            ))
            if point is not axis.sessions[-1]:
                active = evaluation_module._v2_advance_sleeves(
                    active, frozenset()
                )
    return evaluation_module.build_formal_evaluation_input(
        source_view_id=source_view_id,
        source_bundle_id="formal-bundle-1",
        source_bundle_sha256=_sha("bundle"),
        source_artifact_sha256=_sha("artifact"),
        fold_axes=axes,
        economic_observation_axes=economic_axes,
        economic_execution_definition_sha256=(
            evaluation_module.ECONOMIC_EXECUTION_DEFINITION_SHA256
        ),
        power_floor=evaluation_module.PowerFloorBinding(
            receipt_id="power-receipt-1",
            receipt_sha256=_sha("power"),
            required_valid_dates=50,
            required_connected_components=50,
            h20_test_session_capacity=1388,
            preoutcome_candidate_date_count=100,
            valid_h20_test_session_count=100,
            refused_h20_test_session_count=0,
            missing_h20_test_session_count=1288,
            connected_component_instance_count=100,
        ),
        rows=rows,
        refusals=(),
        economic_sessions=tuple(economic),
    )


def _stream_result(value, *, resamples: int = 7):
    stream = evaluation_module.begin_formal_evaluation_stream(
        source_view_id=value.source_view_id,
        input_id=value.input_id,
        input_sha256=value.input_sha256,
        fold_axes=value.fold_axes,
        economic_observation_axes=value.economic_observation_axes,
        economic_execution_definition_sha256=(
            value.economic_execution_definition_sha256
        ),
        power_floor=value.power_floor,
    )
    economic = {
        (item.fold_id, item.session): item for item in value.economic_sessions
    }
    for fold, session, session_position in evaluation_module._stream_axes(
        value.fold_axes, value.economic_observation_axes
    ):
        block = evaluation_module.build_formal_evaluation_session_block(
            fold_id=fold,
            decision_session=session,
            session_position=session_position,
            rows=tuple(
                item for item in value.rows
                if item.fold_id == fold
                and item.decision_session == session
            ),
            refusals=tuple(
                item for item in value.refusals
                if item.fold_id == fold
                and item.decision_session == session
            ),
            economic_session=economic.get((fold, session)),
        )
        evaluation_module.consume_formal_evaluation_session_block(
            stream, block
        )
    return evaluation_module.finish_formal_evaluation_stream(
        stream, resamples=resamples
    )


def _with_nonzero_benchmark_returns(value):
    terminal_sessions = {
        (axis.fold_id, axis.sessions[-1].session)
        for axis in value.economic_observation_axes
    }
    economic_sessions = tuple(
        evaluation_module.build_economic_session(
            source_lineage_sha256=_sha(
                f"nonzero-benchmark:{item.fold_id}:{item.session}"
            ),
            fold_id=item.fold_id,
            session=item.session,
            session_position=item.session_position,
            benchmark_total_return=(
                Decimal(0)
                if (item.fold_id, item.session) in terminal_sessions
                else Decimal("0.0002")
            ),
            benchmark_refusal_reason=item.benchmark_refusal_reason,
            decisions=item.decisions,
            security_outcomes=item.security_outcomes,
        )
        for item in value.economic_sessions
    )
    return evaluation_module.build_formal_evaluation_input(
        source_view_id=value.source_view_id,
        source_bundle_id=value.source_bundle_id,
        source_bundle_sha256=value.source_bundle_sha256,
        source_artifact_sha256=value.source_artifact_sha256,
        fold_axes=value.fold_axes,
        economic_observation_axes=value.economic_observation_axes,
        economic_execution_definition_sha256=(
            value.economic_execution_definition_sha256
        ),
        power_floor=value.power_floor,
        rows=value.rows,
        refusals=value.refusals,
        economic_sessions=economic_sessions,
    )


def test_streamed_report_is_byte_exact_to_materialized_reference() -> None:
    value = _input()
    expected = evaluation_module._build_formal_evaluation_report(
        value, resamples=7
    )
    streamed = _stream_result(value)

    assert streamed.report == expected
    assert streamed.report._canonical_document == expected._canonical_document
    assert streamed.accepted_row_count == len(value.rows)
    assert streamed.refused_row_count == len(value.refusals)
    assert streamed.economic_session_count == len(value.economic_sessions)
    assert len(streamed.fold_horizon_census) == 24


def test_economic_wealth_compounds_net_not_excess_and_stream_is_exact() -> None:
    value = _with_nonzero_benchmark_returns(_input())
    materialized = evaluation_module._build_formal_evaluation_report(
        value, resamples=7
    )
    streamed = _stream_result(value, resamples=7)

    assert streamed.report == materialized
    observations = tuple(
        item
        for item in streamed.economic_trial_observations
        if item.cost_bps_per_side == 10
    )
    assert observations
    assert any(item.benchmark_total_return != 0 for item in observations)
    with localcontext(evaluation_module._context()):
        net_wealth = Decimal(1)
        excess_wealth = Decimal(1)
        for item in observations:
            net_wealth = +(
                net_wealth * (Decimal(1) + item.net_portfolio_total_return)
            )
            excess_wealth = +(
                excess_wealth
                * (Decimal(1) + item.net_excess_daily_total_return)
            )
        expected_net_return = +(net_wealth - Decimal(1))
        wrong_excess_return = +(excess_wealth - Decimal(1))
    summary = next(
        item
        for item in materialized.economic_summaries
        if item.slice_id == evaluation_module.FORMAL_SLICE_ID
        and item.cost_bps_per_side == 10
    )
    assert summary.cumulative_net_total_return == expected_net_return
    assert summary.cumulative_net_total_return != wrong_excess_return


def test_stream_refuses_missing_reordered_or_replayed_session_blocks() -> None:
    value = _input()
    stream = evaluation_module.begin_formal_evaluation_stream(
        source_view_id=value.source_view_id,
        input_id=value.input_id,
        input_sha256=value.input_sha256,
        fold_axes=value.fold_axes,
        economic_observation_axes=value.economic_observation_axes,
        economic_execution_definition_sha256=(
            value.economic_execution_definition_sha256
        ),
        power_floor=value.power_floor,
    )
    with pytest.raises(FormalEvaluationError, match="incomplete"):
        evaluation_module.finish_formal_evaluation_stream(stream, resamples=7)

    ordered = evaluation_module._stream_axes(
        value.fold_axes, value.economic_observation_axes
    )
    economic = {
        (item.fold_id, item.session): item for item in value.economic_sessions
    }
    first_fold, first_date, first_position = ordered[0]
    second_fold, second_date, second_position = ordered[1]
    second = evaluation_module.build_formal_evaluation_session_block(
        fold_id=second_fold,
        decision_session=second_date,
        session_position=second_position,
        rows=(), refusals=(),
        economic_session=economic.get((second_fold, second_date)),
    )
    with pytest.raises(FormalEvaluationError, match="missing or reordered"):
        evaluation_module.consume_formal_evaluation_session_block(stream, second)

    first = evaluation_module.build_formal_evaluation_session_block(
        fold_id=first_fold,
        decision_session=first_date,
        session_position=first_position,
        rows=tuple(
            item for item in value.rows
            if item.fold_id == first_fold
            and item.decision_session == first_date
        ),
        refusals=(), economic_session=economic.get((first_fold, first_date)),
    )
    evaluation_module.consume_formal_evaluation_session_block(stream, first)
    with pytest.raises(FormalEvaluationError, match="missing or reordered"):
        evaluation_module.consume_formal_evaluation_session_block(stream, first)


def test_stream_mutable_state_cannot_be_resealed_by_private_helpers() -> None:
    """Every mutable root is committed; the old reseal oracle is absent."""

    value = _input(rows_per_date=0)
    mutators = (
        lambda state: setattr(state, "creator_pid", state.creator_pid + 1),
        lambda state: setattr(
            state, "owner_thread_id", state.owner_thread_id + 1
        ),
        lambda state: setattr(state, "epoch", state.epoch + 1),
        lambda state: setattr(state, "next_block_index", 1),
        lambda state: setattr(state, "expected_blocks", ()),
        lambda state: setattr(state, "horizon_block_keys", frozenset()),
        lambda state: setattr(state, "economic_block_keys", frozenset()),
        lambda state: setattr(state, "economic_decision_keys", frozenset()),
        lambda state: setattr(state, "economic_terminal_keys", frozenset()),
        lambda state: state.date_stats.append(object()),
        lambda state: state.active_sleeves.pop(
            evaluation_module.FORMAL_FOLD_IDS[-1]
        ),
        lambda state: state.active_sleeves[
            evaluation_module.FORMAL_FOLD_IDS[0]
        ].append(evaluation_module._ActiveSleeve(1, 0, ())),
        lambda state: state.costs.pop(
            (evaluation_module.FORMAL_FOLD_IDS[-1], 20)
        ),
        lambda state: setattr(
            state.costs[(evaluation_module.FORMAL_FOLD_IDS[0], 0)],
            "cost_bps", 5,
        ),
        lambda state: state.costs[
            (evaluation_module.FORMAL_FOLD_IDS[0], 0)
        ].pretrade_weights.__setitem__("security-001", Decimal("1")),
        lambda state: state.costs[
            (evaluation_module.FORMAL_FOLD_IDS[0], 0)
        ].fold_daily.append(object()),
        lambda state: state.costs[
            (evaluation_module.FORMAL_FOLD_IDS[0], 0)
        ].fold_turnover.append(Decimal("1")),
        lambda state: state.costs[
            (evaluation_module.FORMAL_FOLD_IDS[0], 0)
        ].refusal_counts_by_session.append(
            (date(2020, 1, 3), (("forged", 1),))
        ),
        lambda state: setattr(
            state.costs[(evaluation_module.FORMAL_FOLD_IDS[0], 0)],
            "fold_state_valid", False,
        ),
        lambda state: setattr(
            state.costs[(evaluation_module.FORMAL_FOLD_IDS[0], 0)],
            "session_count", 1,
        ),
        lambda state: setattr(
            state.costs[(evaluation_module.FORMAL_FOLD_IDS[0], 0)],
            "refused_session_count", 1,
        ),
        lambda state: setattr(
            state.costs[(evaluation_module.FORMAL_FOLD_IDS[0], 0)],
            "invested_count", 1,
        ),
        lambda state: setattr(
            state.costs[(evaluation_module.FORMAL_FOLD_IDS[0], 0)],
            "cash_sleeves", 1,
        ),
        lambda state: setattr(
            state.costs[(evaluation_module.FORMAL_FOLD_IDS[0], 0)],
            "selected_sleeves", 1,
        ),
        lambda state: setattr(
            state.costs[(evaluation_module.FORMAL_FOLD_IDS[0], 0)],
            "terminal_liquidation", Decimal("1"),
        ),
        lambda state: state.costs[
            (evaluation_module.FORMAL_FOLD_IDS[0], 0)
        ].refusal_counts.__setitem__("forged", 1),
        lambda state: state.economic_folds.__setitem__(
            (evaluation_module.FORMAL_FOLD_IDS[0], 0), None
        ),
        lambda state: setattr(state, "accepted_row_count", 1),
        lambda state: setattr(state, "refused_row_count", 1),
        lambda state: setattr(state, "finished", True),
        lambda state: setattr(state, "failed", True),
    )
    assert not hasattr(evaluation_module, "_refresh_stream_state_authority")
    for mutate in mutators:
        stream = evaluation_module.begin_formal_evaluation_stream(
            source_view_id=value.source_view_id,
            input_id=value.input_id,
            input_sha256=value.input_sha256,
            fold_axes=value.fold_axes,
            economic_observation_axes=value.economic_observation_axes,
            economic_execution_definition_sha256=(
                value.economic_execution_definition_sha256
            ),
            power_floor=value.power_floor,
        )
        state = evaluation_module._STREAMS[id(stream)][3]
        mutate(state)
        with pytest.raises(FormalEvaluationError, match="mutable state changed"):
            evaluation_module._require_stream(stream)
        with pytest.raises(FormalEvaluationError, match="locked"):
            evaluation_module._require_stream(stream)

    # Deriving a same-process commitment is not an authority mutation: there
    # is no callable refresh/commit seam that can install it over a changed
    # live state.  The next validator consumes the original authority.
    stream = evaluation_module.begin_formal_evaluation_stream(
        source_view_id=value.source_view_id,
        input_id=value.input_id,
        input_sha256=value.input_sha256,
        fold_axes=value.fold_axes,
        economic_observation_axes=value.economic_observation_axes,
        economic_execution_definition_sha256=(
            value.economic_execution_definition_sha256
        ),
        power_floor=value.power_floor,
    )
    state = evaluation_module._STREAMS[id(stream)][3]
    state.accepted_row_count = 99
    forged = evaluation_module._build_stream_state_authority(state)
    assert forged.fast_sha256
    with pytest.raises(FormalEvaluationError, match="mutable state changed"):
        evaluation_module._require_stream(stream)


def test_stream_historical_item_mutation_is_caught_before_finish() -> None:
    value = _input(rows_per_date=0)
    stream = evaluation_module.begin_formal_evaluation_stream(
        source_view_id=value.source_view_id,
        input_id=value.input_id,
        input_sha256=value.input_sha256,
        fold_axes=value.fold_axes,
        economic_observation_axes=value.economic_observation_axes,
        economic_execution_definition_sha256=(
            value.economic_execution_definition_sha256
        ),
        power_floor=value.power_floor,
    )
    fold, session, position = evaluation_module._stream_axes(
        value.fold_axes, value.economic_observation_axes
    )[0]
    block = evaluation_module.build_formal_evaluation_session_block(
        fold_id=fold, decision_session=session, session_position=position,
        rows=(), refusals=(), economic_session=None,
    )
    evaluation_module.consume_formal_evaluation_session_block(stream, block)
    state = evaluation_module._STREAMS[id(stream)][3]
    object.__setattr__(state.date_stats[0], "accepted_rows", 1)
    with pytest.raises(FormalEvaluationError, match="mutable state changed"):
        evaluation_module.finish_formal_evaluation_stream(stream, resamples=7)


def test_stream_late_economic_failure_permanently_locks_retry() -> None:
    value = _input(rows_per_date=128)
    stream = evaluation_module.begin_formal_evaluation_stream(
        source_view_id=value.source_view_id,
        input_id=value.input_id,
        input_sha256=value.input_sha256,
        fold_axes=value.fold_axes,
        economic_observation_axes=value.economic_observation_axes,
        economic_execution_definition_sha256=(
            value.economic_execution_definition_sha256
        ),
        power_floor=value.power_floor,
    )
    economic = {
        (item.fold_id, item.session): item for item in value.economic_sessions
    }
    first_economic_key = next(iter(economic))
    for fold, session, position in evaluation_module._stream_axes(
        value.fold_axes, value.economic_observation_axes
    ):
        source_economic = economic.get((fold, session))
        rows = tuple(
            item for item in value.rows
            if item.fold_id == fold and item.decision_session == session
        )
        block = evaluation_module.build_formal_evaluation_session_block(
            fold_id=fold, decision_session=session, session_position=position,
            rows=rows, refusals=(), economic_session=source_economic,
        )
        if (fold, session) != first_economic_key:
            evaluation_module.consume_formal_evaluation_session_block(
                stream, block
            )
            continue
        assert source_economic is not None
        assert source_economic.security_outcomes
        incomplete_economic = evaluation_module.build_economic_session(
            source_lineage_sha256=source_economic.source_lineage_sha256,
            fold_id=fold, session=session, session_position=position,
            benchmark_total_return=source_economic.benchmark_total_return,
            benchmark_refusal_reason=None,
            decisions=source_economic.decisions,
            security_outcomes=(),
        )
        incomplete = evaluation_module.build_formal_evaluation_session_block(
            fold_id=fold, decision_session=session, session_position=position,
            rows=rows, refusals=(), economic_session=incomplete_economic,
        )
        with pytest.raises(FormalEvaluationError, match="exact active union"):
            evaluation_module.consume_formal_evaluation_session_block(
                stream, incomplete
            )
        with pytest.raises(FormalEvaluationError, match="locked"):
            evaluation_module.consume_formal_evaluation_session_block(
                stream, block
            )
        break
    else:  # pragma: no cover - frozen axes always contain H20 economics.
        raise AssertionError("the exact formal axis contained no economic block")


def test_stream_cross_thread_resume_and_finish_deregister_authority() -> None:
    value = _input(rows_per_date=0)

    def new_stream():
        return evaluation_module.begin_formal_evaluation_stream(
            source_view_id=value.source_view_id,
            input_id=value.input_id,
            input_sha256=value.input_sha256,
            fold_axes=value.fold_axes,
            economic_observation_axes=value.economic_observation_axes,
            economic_execution_definition_sha256=(
                value.economic_execution_definition_sha256
            ),
            power_floor=value.power_floor,
        )

    fold, session, position = evaluation_module._stream_axes(
        value.fold_axes, value.economic_observation_axes
    )[0]
    block = evaluation_module.build_formal_evaluation_session_block(
        fold_id=fold, decision_session=session, session_position=position,
        rows=(), refusals=(), economic_session=None,
    )
    for action in (
        lambda stream: evaluation_module.consume_formal_evaluation_session_block(
            stream, block
        ),
        lambda stream: evaluation_module.finish_formal_evaluation_stream(
            stream, resamples=7
        ),
    ):
        stream = new_stream()
        errors: list[BaseException] = []

        def invoke() -> None:
            try:
                action(stream)
            except BaseException as exc:  # exact type asserted below
                errors.append(exc)

        worker = threading.Thread(target=invoke)
        worker.start()
        worker.join()
        assert len(errors) == 1
        assert type(errors[0]) is FormalEvaluationError
        assert "owner thread changed" in str(errors[0])
        with pytest.raises(FormalEvaluationError, match="locked"):
            evaluation_module._require_stream(stream)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork boundary")
def test_stream_authority_rejects_fork_before_and_after_partial_consume() -> None:
    value = _input(rows_per_date=0)

    def new_stream():
        return evaluation_module.begin_formal_evaluation_stream(
            source_view_id=value.source_view_id,
            input_id=value.input_id,
            input_sha256=value.input_sha256,
            fold_axes=value.fold_axes,
            economic_observation_axes=value.economic_observation_axes,
            economic_execution_definition_sha256=(
                value.economic_execution_definition_sha256
            ),
            power_floor=value.power_floor,
        )

    fold, session, position = evaluation_module._stream_axes(
        value.fold_axes, value.economic_observation_axes
    )[0]
    block = evaluation_module.build_formal_evaluation_session_block(
        fold_id=fold, decision_session=session, session_position=position,
        rows=(), refusals=(), economic_session=None,
    )
    for partially_consumed in (False, True):
        stream = new_stream()
        if partially_consumed:
            evaluation_module.consume_formal_evaluation_session_block(
                stream, block
            )
        read_fd, write_fd = os.pipe()
        child = os.fork()
        if child == 0:  # pragma: no cover - result crosses the pipe.
            os.close(read_fd)
            try:
                evaluation_module._require_stream(stream)
            except FormalEvaluationError:
                empty = not (
                    evaluation_module._STREAMS
                    or evaluation_module._LOCKED_STREAMS
                )
                os.write(write_fd, b"refused" if empty else b"not-cleared")
            else:
                os.write(write_fd, b"accepted")
            os.close(write_fd)
            os._exit(0)
        os.close(write_fd)
        outcome = os.read(read_fd, 64)
        os.close(read_fd)
        _pid, status = os.waitpid(child, 0)
        assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
        assert outcome == b"refused"
        assert evaluation_module._require_stream(stream)[0] is stream


def test_stream_does_not_retain_high_cardinality_component_history() -> None:
    """Component memory is per block, not cumulative across historical dates."""

    empty = _input(rows_per_date=0)
    stream = evaluation_module.begin_formal_evaluation_stream(
        source_view_id=empty.source_view_id,
        input_id=empty.input_id,
        input_sha256=empty.input_sha256,
        fold_axes=empty.fold_axes,
        economic_observation_axes=empty.economic_observation_axes,
        economic_execution_definition_sha256=(
            empty.economic_execution_definition_sha256
        ),
        power_floor=empty.power_floor,
    )

    for session_offset in range(2):
        axis = next(
            item for item in empty.fold_axes
            if item.fold_id == evaluation_module.FORMAL_FOLD_IDS[0]
            and item.horizon_sessions == 1
        )
        point = axis.sessions[session_offset]
        rows = tuple(
            _row(
                0,
                security_index,
                horizon=1,
                session_offset=session_offset,
                component=(
                    f"high-cardinality-component-{session_offset}-"
                    f"{security_index:03d}"
                ),
            )
            for security_index in range(256)
        )
        block = evaluation_module.build_formal_evaluation_session_block(
            fold_id=evaluation_module.FORMAL_FOLD_IDS[0],
            decision_session=point.session,
            session_position=point.session_position,
            rows=rows,
            refusals=(),
            economic_session=None,
        )
        evaluation_module.consume_formal_evaluation_session_block(stream, block)

    state = evaluation_module._STREAMS[id(stream)][3]
    assert "component_dates" not in evaluation_module._StreamState.__slots__
    assert not hasattr(state, "component_dates")
    assert len(state.date_stats) == 2
    assert state.accepted_row_count == 512
    assert "high-cardinality-component" not in repr(state)


def test_v2_freezes_all_controls_periods_and_primary_arithmetic() -> None:
    assert len(evaluation_module.CONTINUOUS_CONTROL_NAMES) == 19
    assert len(evaluation_module.BINARY_CONTROL_NAMES) == 6
    assert len(evaluation_module.OUTCOME_ONLY_CONTROL_NAMES) == 2
    assert len(evaluation_module.ALL_CONTROL_NAMES) == 27
    assert evaluation_module.FORMAL_FOLD_IDS == tuple(
        f"arv2-wf-test-{year}" for year in range(2020, 2026)
    )
    assert evaluation_module.DESCRIPTIVE_FOLD_IDS == tuple(
        f"arv2-wf-test-{year}" for year in range(2021, 2026)
    )
    assert evaluation_module.BOOTSTRAP_RESAMPLES == 19_999
    assert evaluation_module.PRIMARY_SIZE == Fraction(1, 20)
    assert evaluation_module.COST_BPS_GRID == (0, 5, 10, 20)
    assert evaluation_module.MINIMUM_SLEEVE_SIZE == 5


def test_v2_row_and_root_are_deterministic_and_content_addressed() -> None:
    first = _input()
    second = _input()
    assert first == second
    assert first.input_id.endswith(first.input_sha256[:24])
    assert len(first.rows[0].continuous_controls) == 19
    assert len(first.rows[0].binary_controls) == 6
    assert evaluation_module.require_formal_evaluation_input(first) is first
    assert first.filesystem_available is False
    assert first.network_available is False
    assert first.outcome_access_available is False
    assert first.quantconnect_available is False


def test_v2_extended_outcome_and_decision_fields_are_exactly_validated() -> None:
    row = _row(
        0, 8,
        rating_action="upgrades",
        earnings_anchor_signed_session_distance=-3,
        gross_security_total_return=Decimal("0.031"),
        benchmark_total_return=Decimal("0.011"),
    )
    assert row.excess_total_return == Decimal("0.020")
    assert evaluation_module._require_evaluation_row(row) is row

    with pytest.raises(FormalEvaluationError, match="rating_action"):
        _row(0, 8, rating_action="maintains")
    with pytest.raises(FormalEvaluationError, match="signed session distance"):
        _row(0, 8, earnings_anchor_signed_session_distance=True)
    with pytest.raises(FormalEvaluationError, match="presence differs"):
        _row(
            0, 8,
            gross_security_total_return=Decimal("0.01"),
        )
    with pytest.raises(FormalEvaluationError, match="below -1"):
        _row(
            0, 8,
            gross_security_total_return=Decimal("-1.01"),
            benchmark_total_return=Decimal("0"),
        )
    with pytest.raises(FormalEvaluationError, match="gross minus benchmark"):
        evaluation_module._require_evaluation_row(dataclasses.replace(
            row, gross_security_total_return=Decimal("0.032")
        ))

    for volatility in (Decimal("0"), Decimal("-0.01"), Decimal("0.2")):
        decision = evaluation_module.build_economic_decision(
            decision_lineage_sha256=_sha(f"volatility:{volatility}"),
            security_id="security-001",
            firm_specific_score=Decimal("1"),
            realized_volatility_60d=volatility,
        )
        assert decision.realized_volatility_60d == volatility
    with pytest.raises(FormalEvaluationError, match="finite Decimal"):
        evaluation_module.build_economic_decision(
            decision_lineage_sha256=_sha("volatility:nan"),
            security_id="security-001",
            firm_specific_score=Decimal("1"),
            realized_volatility_60d=Decimal("NaN"),
        )


@pytest.mark.parametrize(
    "mutator",
    (
        lambda row: dataclasses.replace(row, excess_total_return=Decimal("9")),
        lambda row: dataclasses.replace(row, firm_specific_score=Decimal("3")),
        lambda row: dataclasses.replace(row, industry_id="changed-industry"),
        lambda row: dataclasses.replace(row, common_event_component_id="changed-component"),
        lambda row: dataclasses.replace(
            row,
            continuous_controls=(
                dataclasses.replace(row.continuous_controls[0], value=Decimal("8")),
                *row.continuous_controls[1:],
            ),
        ),
        lambda row: dataclasses.replace(
            row,
            binary_controls=(
                dataclasses.replace(row.binary_controls[0], value=0),
                *row.binary_controls[1:],
            ),
        ),
        lambda row: dataclasses.replace(row, active_event_indicator=0),
        lambda row: dataclasses.replace(
            row,
            absolute_contribution_weighted_publication_to_entry_jump=Decimal("2"),
        ),
        lambda row: dataclasses.replace(row, source_lineage_sha256="0" * 64),
    ),
)
def test_v2_every_nested_row_semantic_tamper_is_refused(mutator) -> None:
    value = _input()
    rows = (mutator(value.rows[0]), *value.rows[1:])
    forged = dataclasses.replace(value, rows=rows)
    with pytest.raises(FormalEvaluationError):
        evaluation_module.require_formal_evaluation_input(forged)


def test_v2_axis_power_and_economic_nested_tampers_are_refused() -> None:
    value = _input()
    point = dataclasses.replace(value.fold_axes[0].sessions[0], session_position=99)
    axis = dataclasses.replace(
        value.fold_axes[0], sessions=(point, *value.fold_axes[0].sessions[1:])
    )
    with pytest.raises(FormalEvaluationError):
        evaluation_module.require_formal_evaluation_input(
            dataclasses.replace(value, fold_axes=(axis, *value.fold_axes[1:]))
        )
    with pytest.raises(FormalEvaluationError):
        evaluation_module.require_formal_evaluation_input(dataclasses.replace(
            value,
            power_floor=dataclasses.replace(
                value.power_floor, required_valid_dates=51
            ),
        ))
    session = value.economic_sessions[0]
    decision = dataclasses.replace(
        session.decisions[0], firm_specific_score=Decimal("0.2")
    )
    forged_session = dataclasses.replace(
        session, decisions=(decision, *session.decisions[1:])
    )
    with pytest.raises(FormalEvaluationError):
        evaluation_module.require_formal_evaluation_input(dataclasses.replace(
            value,
            economic_sessions=(forged_session, *value.economic_sessions[1:]),
        ))


def test_v2_economic_censuses_are_exhaustive_across_prior_sleeves() -> None:
    value = _input(rows_per_date=128)
    first, second = value.economic_sessions[:2]
    assert first.decisions
    assert second.decisions == ()
    assert second.security_outcomes  # returns for names selected one day earlier

    omitted_outcome = evaluation_module.build_economic_session(
        source_lineage_sha256=second.source_lineage_sha256,
        fold_id=second.fold_id, session=second.session,
        session_position=second.session_position,
        benchmark_total_return=second.benchmark_total_return,
        benchmark_refusal_reason=None, decisions=second.decisions,
        security_outcomes=second.security_outcomes[1:],
    )
    with pytest.raises(FormalEvaluationError, match="exact active union"):
        evaluation_module.build_formal_evaluation_input(
            source_view_id=value.source_view_id,
            source_bundle_id=value.source_bundle_id,
            source_bundle_sha256=value.source_bundle_sha256,
            source_artifact_sha256=value.source_artifact_sha256,
            fold_axes=value.fold_axes,
            economic_observation_axes=value.economic_observation_axes,
            economic_execution_definition_sha256=(
                value.economic_execution_definition_sha256
            ),
            power_floor=value.power_floor,
            rows=value.rows, refusals=value.refusals,
            economic_sessions=(
                first, omitted_outcome, *value.economic_sessions[2:]
            ),
        )

    omitted_decision = evaluation_module.build_economic_session(
        source_lineage_sha256=first.source_lineage_sha256,
        fold_id=first.fold_id, session=first.session,
        session_position=first.session_position,
        benchmark_total_return=first.benchmark_total_return,
        benchmark_refusal_reason=None, decisions=first.decisions[1:],
        security_outcomes=first.security_outcomes,
    )
    with pytest.raises(FormalEvaluationError, match="exact H20 census"):
        evaluation_module.build_formal_evaluation_input(
            source_view_id=value.source_view_id,
            source_bundle_id=value.source_bundle_id,
            source_bundle_sha256=value.source_bundle_sha256,
            source_artifact_sha256=value.source_artifact_sha256,
            fold_axes=value.fold_axes,
            economic_observation_axes=value.economic_observation_axes,
            economic_execution_definition_sha256=(
                value.economic_execution_definition_sha256
            ),
            power_floor=value.power_floor,
            rows=value.rows, refusals=value.refusals,
            economic_sessions=(omitted_decision, *value.economic_sessions[1:]),
        )


def test_v2_named_daily_return_refusal_is_disclosed_not_zero_imputed() -> None:
    value = _input(rows_per_date=128)
    session = value.economic_sessions[1]
    source = session.security_outcomes[0]
    refusal = evaluation_module.build_economic_security_outcome(
        outcome_lineage_sha256=source.outcome_lineage_sha256,
        security_id=source.security_id,
        disposition=evaluation_module.EconomicOutcomeDisposition.NAMED_REFUSAL,
        gross_total_return=None,
        reason=evaluation_module.RefusalReason.MISSING_DAILY_SECURITY_RETURN,
        terminal_payoff_applied=False,
    )
    changed = evaluation_module.build_economic_session(
        source_lineage_sha256=session.source_lineage_sha256,
        fold_id=session.fold_id, session=session.session,
        session_position=session.session_position,
        benchmark_total_return=session.benchmark_total_return,
        benchmark_refusal_reason=None, decisions=session.decisions,
        security_outcomes=(refusal, *session.security_outcomes[1:]),
    )
    changed_input = evaluation_module.build_formal_evaluation_input(
        source_view_id=value.source_view_id,
        source_bundle_id=value.source_bundle_id,
        source_bundle_sha256=value.source_bundle_sha256,
        source_artifact_sha256=value.source_artifact_sha256,
        fold_axes=value.fold_axes,
        economic_observation_axes=value.economic_observation_axes,
        economic_execution_definition_sha256=(
            value.economic_execution_definition_sha256
        ),
        power_floor=value.power_floor,
        rows=value.rows, refusals=value.refusals,
        economic_sessions=(
            value.economic_sessions[0], changed, *value.economic_sessions[2:]
        ),
    )
    summary = evaluation_module._v2_economic_cost_summary(
        value=changed_input, slice_id="test",
        folds=evaluation_module.FORMAL_FOLD_IDS,
        cost_bps=0, required_dates=1, resamples=7,
    )
    assert summary.session_count == 1508
    # A missing held-name return destroys the carried holding weights for the
    # rest of that independent fold.  The evaluator excludes that whole fold
    # instead of silently restarting from a later target portfolio.
    assert summary.valid_return_session_count == 1255
    assert summary.refused_return_session_count == 253
    assert summary.cumulative_net_total_return is None
    assert summary.status is evaluation_module.Disposition.INCONCLUSIVE
    assert (
        "arv2-wf-test-2020:economic_fold_excluded_after_holding_state_loss"
        in summary.reasons
    )
    assert "missing_daily_security_return:1" in summary.reasons

    stream = evaluation_module.begin_formal_evaluation_stream(
        source_view_id=changed_input.source_view_id,
        input_id=changed_input.input_id,
        input_sha256=changed_input.input_sha256,
        fold_axes=changed_input.fold_axes,
        economic_observation_axes=changed_input.economic_observation_axes,
        economic_execution_definition_sha256=(
            changed_input.economic_execution_definition_sha256
        ),
        power_floor=changed_input.power_floor,
    )
    economic = {
        (item.fold_id, item.session): item
        for item in changed_input.economic_sessions
    }
    first_fold = evaluation_module.FORMAL_FOLD_IDS[0]
    for fold, decision_session, position in evaluation_module._stream_axes(
        changed_input.fold_axes, changed_input.economic_observation_axes
    ):
        if fold != first_fold:
            break
        block = evaluation_module.build_formal_evaluation_session_block(
            fold_id=fold,
            decision_session=decision_session,
            session_position=position,
            rows=tuple(
                item for item in changed_input.rows
                if item.fold_id == fold
                and item.decision_session == decision_session
            ),
            refusals=(),
            economic_session=economic.get((fold, decision_session)),
        )
        evaluation_module.consume_formal_evaluation_session_block(stream, block)
    state = evaluation_module._STREAMS[id(stream)][3]
    streamed_fold = state.economic_folds[(first_fold, 0)]
    assert len(streamed_fold.refusal_counts_by_session) == 253
    refusal_by_date = dict(streamed_fold.refusal_counts_by_session)
    assert dict(refusal_by_date[session.session])[
        evaluation_module.RefusalReason.MISSING_DAILY_SECURITY_RETURN.value
    ] == 1
    stream_summary = evaluation_module._stream_economic_summary(
        stream=stream, state=state, slice_id="test", folds=(first_fold,),
        cost_bps=0, required_dates=1, resamples=7,
    )
    assert stream_summary.status is evaluation_module.Disposition.INCONCLUSIVE


def test_v2_invalid_economic_status_cannot_retain_a_p_value(
    monkeypatch,
) -> None:
    value = _input(rows_per_date=128)
    session = value.economic_sessions[1]
    source = session.security_outcomes[0]
    refusal = evaluation_module.build_economic_security_outcome(
        outcome_lineage_sha256=source.outcome_lineage_sha256,
        security_id=source.security_id,
        disposition=evaluation_module.EconomicOutcomeDisposition.NAMED_REFUSAL,
        gross_total_return=None,
        reason=evaluation_module.RefusalReason.OUTCOME_IDENTITY_INVALID,
        terminal_payoff_applied=False,
    )
    changed_session = evaluation_module.build_economic_session(
        source_lineage_sha256=session.source_lineage_sha256,
        fold_id=session.fold_id,
        session=session.session,
        session_position=session.session_position,
        benchmark_total_return=session.benchmark_total_return,
        benchmark_refusal_reason=None,
        decisions=session.decisions,
        security_outcomes=(refusal, *session.security_outcomes[1:]),
    )
    changed = evaluation_module.build_formal_evaluation_input(
        source_view_id=value.source_view_id,
        source_bundle_id=value.source_bundle_id,
        source_bundle_sha256=value.source_bundle_sha256,
        source_artifact_sha256=value.source_artifact_sha256,
        fold_axes=value.fold_axes,
        economic_observation_axes=value.economic_observation_axes,
        economic_execution_definition_sha256=(
            value.economic_execution_definition_sha256
        ),
        power_floor=value.power_floor,
        rows=value.rows,
        refusals=value.refusals,
        economic_sessions=(
            value.economic_sessions[0],
            changed_session,
            *value.economic_sessions[2:],
        ),
    )
    monkeypatch.setattr(
        evaluation_module,
        "_v2_stock_centered_bootstrap",
        lambda **kwargs: (Decimal(0),) * kwargs["resamples"],
    )
    summary = evaluation_module._v2_economic_cost_summary(
        value=changed,
        slice_id=evaluation_module.FORMAL_SLICE_ID,
        folds=evaluation_module.FORMAL_FOLD_IDS,
        cost_bps=10,
        required_dates=1,
        resamples=7,
    )
    assert summary.status is evaluation_module.Disposition.INVALID_DATA
    assert summary.bootstrap_resamples == 7
    assert summary.centered_two_sided_p_value is None


def test_v2_cross_date_component_and_horizon_field_drift_refuse() -> None:
    axes = _input().fold_axes
    first = _row(0, 0, component="shared")
    second = _row(1, 0, component="shared")
    with pytest.raises(FormalEvaluationError, match="crosses dates"):
        evaluation_module.build_formal_evaluation_input(
            source_view_id=evaluation_module.SOURCE_VIEW_IDS[0],
            source_bundle_id="bundle-1", source_bundle_sha256=_sha("b"),
            source_artifact_sha256=_sha("a"), fold_axes=axes,
            economic_observation_axes=_exact_economic_axes(),
            economic_execution_definition_sha256=(
                evaluation_module.ECONOMIC_EXECUTION_DEFINITION_SHA256
            ),
            power_floor=evaluation_module.PowerFloorBinding(
                receipt_id="receipt-1",
                receipt_sha256=_sha("p"),
                required_valid_dates=50,
                required_connected_components=50,
                h20_test_session_capacity=1388,
                preoutcome_candidate_date_count=100,
                valid_h20_test_session_count=100,
                refused_h20_test_session_count=0,
                missing_h20_test_session_count=1288,
                connected_component_instance_count=100,
            ),
            rows=(first, second), refusals=(), economic_sessions=(),
        )
    base = _input()
    h20 = base.rows[0]
    h1 = evaluation_module.build_evaluation_row(
        source_lineage_sha256=_sha("cross-horizon-h1"),
        fold_id=h20.fold_id,
        decision_session=h20.decision_session,
        session_position=h20.session_position,
        security_id=h20.security_id,
        industry_id=h20.industry_id,
        common_event_component_id="different",
        horizon_sessions=1,
        firm_specific_score=h20.firm_specific_score,
        global_score=h20.global_score,
        structural_zero=h20.structural_zero,
        continuous_control_values=tuple(
            item.value for item in h20.continuous_controls
        ),
        binary_control_values=tuple(item.value for item in h20.binary_controls),
        active_event_indicator=h20.active_event_indicator,
        absolute_contribution_weighted_publication_to_entry_jump=(
            h20.absolute_contribution_weighted_publication_to_entry_jump
        ),
        excess_total_return=h20.excess_total_return,
    )
    with pytest.raises(FormalEvaluationError, match="horizon rows disagree"):
        evaluation_module.build_formal_evaluation_input(
            source_view_id=base.source_view_id,
            source_bundle_id=base.source_bundle_id,
            source_bundle_sha256=base.source_bundle_sha256,
            source_artifact_sha256=base.source_artifact_sha256,
            fold_axes=base.fold_axes,
            economic_observation_axes=base.economic_observation_axes,
            economic_execution_definition_sha256=(
                base.economic_execution_definition_sha256
            ),
            power_floor=base.power_floor,
            rows=(*base.rows, h1), refusals=base.refusals,
            economic_sessions=base.economic_sessions,
        )


def test_v2_fama_macbeth_uses_full_design_and_names_underfill() -> None:
    rows = tuple(_row(0, index) for index in range(64))
    fit = evaluation_module._weighted_fama_macbeth_date(
        rows, arm="firm_specific"
    )
    assert type(fit) is tuple
    assert fit[2] == 31  # intercept + two scores + 27 controls + one industry dummy
    assert fit[0] > 0
    underfilled = evaluation_module._weighted_fama_macbeth_date(
        rows[:50], arm="firm_specific"
    )
    assert underfilled == "not_strictly_more_than_parameter_count_plus_20"

    # Duplicating an identical member inside one component splits that
    # component's weight; it does not give the common event an extra vote.
    duplicate = dataclasses.replace(
        rows[0], row_id=rows[0].row_id, row_sha256=rows[0].row_sha256
    )
    repeated = evaluation_module._weighted_fama_macbeth_date(
        (rows[0], duplicate, *rows[1:]), arm="firm_specific"
    )
    assert type(repeated) is tuple
    assert abs(repeated[0] - fit[0]) < Decimal("1e-40")


def test_v2_invalid_fama_macbeth_status_cannot_retain_a_p_value(
    monkeypatch,
) -> None:
    value = _input()
    first_positions = {
        axis.fold_id: axis.sessions[0].session_position
        for axis in value.fold_axes
        if axis.horizon_sessions == 20
    }
    valid = tuple(
        (fold, first_positions[fold], Decimal("0.01"), Decimal("-0.01"))
        for fold in evaluation_module.FORMAL_FOLD_IDS
    )
    monkeypatch.setattr(
        evaluation_module,
        "_v2_stock_centered_bootstrap",
        lambda **kwargs: (Decimal(0),) * kwargs["resamples"],
    )
    summaries = evaluation_module._v2_fm_summaries(
        value=value,
        slice_id=evaluation_module.FORMAL_SLICE_ID,
        fold_id=None,
        folds=evaluation_module.FORMAL_FOLD_IDS,
        horizon=20,
        arm="firm_specific",
        valid=valid,
        invalid=Counter({"outcome_identity_invalid": 1}),
        parameter_counts=tuple(
            (fold, 31) for fold in evaluation_module.FORMAL_FOLD_IDS
        ),
        required_dates=1,
        resamples=7,
    )
    assert all(
        item.status is evaluation_module.Disposition.INVALID_DATA
        and item.bootstrap_resamples == 7
        and item.centered_two_sided_p_value is None
        for item in summaries
    )


def test_v2_hac_keeps_actual_session_gaps() -> None:
    pairs, _se, _t = evaluation_module._v2_hac(
        ((0, Decimal("1")), (2, Decimal("2")), (3, Decimal("4"))), 2
    )
    assert pairs == (3, 1, 1)


def test_v2_bootstrap_is_deterministic_noncircular_and_type7_exact() -> None:
    axes = {
        fold: tuple(range(20)) for fold in evaluation_module.FORMAL_FOLD_IDS
    }
    values = tuple(
        (evaluation_module.FORMAL_FOLD_IDS[0], index, Decimal(index - 9))
        for index in range(20)
    )
    arguments = dict(
        values=values,
        axes=axes,
        block_length=20,
        source_view_id=evaluation_module.SOURCE_VIEW_IDS[0],
        slice_id=evaluation_module.FORMAL_SLICE_ID,
        metric_id="primary_fm_bullish_h20",
        resamples=31,
    )
    first = evaluation_module._v2_stock_centered_bootstrap(**arguments)
    second = evaluation_module._v2_stock_centered_bootstrap(**arguments)
    assert first == second
    assert first is not None and len(first) == 31

    report_contract = build_formal_report_contract(
        economic_execution_definition_sha256=(
            evaluation_module.ECONOMIC_EXECUTION_DEFINITION_SHA256
        )
    )
    report_record = formal_report_contract_record(report_contract)
    seed_record = report_record["bootstrap"][
        "stock_FM_and_economic_seed_record"
    ]
    canonical_preimage = (
        json.dumps(
            seed_record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
    )
    assert hashlib.sha256(canonical_preimage).hexdigest() == (
        evaluation_module.STOCK_BOOTSTRAP_SEED_SHA256
    )
    assert report_contract.stock_bootstrap_seed_sha256 == (
        evaluation_module.STOCK_BOOTSTRAP_SEED_SHA256
    )
    assert evaluation_module._v2_stock_unbiased_start(
        modulus=214,
        source_view_id=evaluation_module.SOURCE_VIEW_IDS[0],
        slice_id=evaluation_module.FORMAL_SLICE_ID,
        metric_id="primary_fm_bullish_h20",
        replicate=0,
        fold_ordinal=0,
        block_ordinal=0,
    ) == 203
    assert evaluation_module._v2_stock_unbiased_start(
        modulus=214,
        source_view_id=evaluation_module.SOURCE_VIEW_IDS[0],
        slice_id=evaluation_module.FORMAL_SLICE_ID,
        metric_id="primary_fm_bullish_h20",
        replicate=19_998,
        fold_ordinal=5,
        block_ordinal=11,
    ) == 189
    quantile = evaluation_module._v2_type7(
        tuple(Decimal(index) for index in range(19_999)), Fraction(19, 20)
    )
    assert quantile == Decimal("18998.1")


def test_v2_twenty_overlapping_sleeves_top_quintile_cost_and_liquidation() -> None:
    base = _input(rows_per_date=1)
    h20_axes = tuple(axis for axis in base.fold_axes if axis.horizon_sessions == 20)
    axis = h20_axes[0]
    decision_axes = {
        item.fold_id: {point.session for point in item.sessions}
        for item in h20_axes
    }
    rows: list[evaluation_module.EvaluationRow] = []
    sessions: list[evaluation_module.EconomicSession] = []
    for economic_axis in base.economic_observation_axes:
        active: list[evaluation_module._ActiveSleeve] = []
        for offset, point in enumerate(economic_axis.sessions):
            day_decisions: list[evaluation_module.EconomicDecision] = []
            decision_eligible = point.session in decision_axes[economic_axis.fold_id]
            if decision_eligible and economic_axis.fold_id == axis.fold_id:
                for security_index in range(25):
                    continuous, binary = _controls(security_index)
                    score = Decimal(security_index + 1) / Decimal(10)
                    decision = evaluation_module.build_evaluation_row(
                        source_lineage_sha256=_sha(
                            f"sleeve-decision:{economic_axis.fold_id}:"
                            f"{point.session}:{security_index}"
                        ),
                        fold_id=economic_axis.fold_id,
                        decision_session=point.session,
                        session_position=point.session_position,
                        security_id=f"security-{security_index:03d}",
                        industry_id="industry-0",
                        common_event_component_id=(
                            f"sleeve-component:{offset}:{security_index}"
                        ),
                        horizon_sessions=20, firm_specific_score=score,
                        global_score=-score, structural_zero=False,
                        continuous_control_values=continuous,
                        binary_control_values=binary,
                        active_event_indicator=1,
                        absolute_contribution_weighted_publication_to_entry_jump=(
                            Decimal("0")
                        ),
                        excess_total_return=score / Decimal(100),
                    )
                    rows.append(decision)
                    day_decisions.append(evaluation_module.build_economic_decision(
                        decision_lineage_sha256=decision.source_lineage_sha256,
                        security_id=decision.security_id,
                        firm_specific_score=decision.firm_specific_score,
                    ))
            if decision_eligible:
                active.append(evaluation_module._v2_new_sleeve(
                    evaluation_module._v2_selected_sleeve(tuple(day_decisions))
                ))
            held_ids = tuple(sorted(evaluation_module._v2_targets(active)))
            outcomes = tuple(
                evaluation_module.build_economic_security_outcome(
                    outcome_lineage_sha256=_sha(
                        f"sleeve-outcome:{economic_axis.fold_id}:"
                        f"{point.session}:{security_id}"
                    ),
                    security_id=security_id,
                    disposition=evaluation_module.EconomicOutcomeDisposition.RETURN,
                    gross_total_return=Decimal("0.01"), reason=None,
                    terminal_payoff_applied=False,
                )
                for security_id in held_ids
            )
            sessions.append(evaluation_module.build_economic_session(
                source_lineage_sha256=_sha(
                    f"sleeve-session:{economic_axis.fold_id}:{point.session}"
                ),
                fold_id=economic_axis.fold_id, session=point.session,
                session_position=point.session_position,
                benchmark_total_return=Decimal("0"),
                benchmark_refusal_reason=None,
                decisions=tuple(day_decisions), security_outcomes=outcomes,
            ))
            if point is not economic_axis.sessions[-1]:
                active = evaluation_module._v2_advance_sleeves(
                    active, frozenset()
                )
    value = evaluation_module.build_formal_evaluation_input(
        source_view_id=evaluation_module.SOURCE_VIEW_IDS[0],
        source_bundle_id="sleeve-bundle-1", source_bundle_sha256=_sha("sb"),
        source_artifact_sha256=_sha("sa"), fold_axes=base.fold_axes,
        economic_observation_axes=base.economic_observation_axes,
        economic_execution_definition_sha256=(
            base.economic_execution_definition_sha256
        ),
        power_floor=evaluation_module.PowerFloorBinding(
            receipt_id="sleeve-power-1",
            receipt_sha256=_sha("sp"),
            required_valid_dates=50,
            required_connected_components=50,
            h20_test_session_capacity=1388,
            preoutcome_candidate_date_count=100,
            valid_h20_test_session_count=100,
            refused_h20_test_session_count=0,
            missing_h20_test_session_count=1288,
            connected_component_instance_count=100,
        ),
        rows=tuple(rows), refusals=(), economic_sessions=tuple(sessions),
    )
    zero = evaluation_module._v2_economic_cost_summary(
        value=value, slice_id="test", folds=(axis.fold_id,), cost_bps=0,
        required_dates=1, resamples=7,
    )
    primary = evaluation_module._v2_economic_cost_summary(
        value=value, slice_id="test", folds=(axis.fold_id,), cost_bps=10,
        required_dates=1, resamples=7,
    )
    assert zero.selected_sleeve_count == len(axis.sessions)
    assert zero.cash_sleeve_count == 0
    assert zero.invested_session_count == len(axis.sessions) + 19
    assert zero.terminal_liquidation_turnover == Decimal(
        "0.05047476261869065467266366817"
    )
    assert zero.mean_net_excess_daily_return == Decimal(
        "0.0092094861660079051383399209486166007905138339920949"
    )
    # Yesterday's target is not today's pre-trade portfolio: the +1% held-name
    # returns drift the risky weights relative to cash.  The golden therefore
    # covers both that drift and the exact post-decision runoff sessions.
    assert zero.mean_daily_turnover == Decimal(
        "0.0079051383399209486166007905138339920948616600790514"
    )
    assert primary.mean_net_excess_daily_return == Decimal(
        "0.0092015807030550580781214404336873714688720713828806"
    )
    assert primary.terminal_liquidation_turnover == Decimal(
        "0.05047733084626474460892675484"
    )
    # The stock bootstrap is a pooled-six-fold formal-slice operation, not a
    # single-fold diagnostic that can silently mint another sampling family.
    assert primary.bootstrap_resamples is None


def test_v2_report_is_complete_separated_inconclusive_and_has_no_authority() -> None:
    value = _input()
    first = evaluation_module._build_formal_evaluation_report(
        value, resamples=31
    )
    second = evaluation_module._build_formal_evaluation_report(
        value, resamples=31
    )
    assert first == second
    assert first.report_id.endswith(first.report_sha256[:24])
    assert first.source_view_id == evaluation_module.SOURCE_VIEW_IDS[0]
    assert len(first.coverage) == 52
    assert len(first.ic_summaries) == 104
    assert len(first.fama_macbeth_summaries) == 208
    assert len(first.paired_ic_summaries) == 52
    assert len(first.economic_summaries) == 8
    # A valid failed gate closes the family even when another gate is
    # underfilled; the latter cannot rescue the observed failure.
    assert first.disposition is evaluation_module.Disposition.FAIL
    assert {item.slice_id for item in first.coverage} == {
        evaluation_module.FORMAL_SLICE_ID,
        evaluation_module.DESCRIPTIVE_SLICE_ID,
    }
    assert all(item.bootstrap_resamples == 31 for item in first.fama_macbeth_summaries
               if item.bootstrap_resamples is not None)
    assert first.result_read_authority_available is False
    assert first.result_disposition_authority_available is False
    assert first.deployment_available is False
    assert first.orders_available is False
    assert first.trading_available is False
    assert evaluation_module.require_formal_evaluation_report(first) is first


def test_v2_source_views_are_explicit_distinct_and_no_failure_is_rescued() -> None:
    current = _input(source_view_id=evaluation_module.SOURCE_VIEW_IDS[0])
    censored = _input(source_view_id=evaluation_module.SOURCE_VIEW_IDS[1])
    assert current.input_sha256 != censored.input_sha256
    assert current.source_view_id != censored.source_view_id
    assert evaluation_module._v2_conjunction_disposition((
        evaluation_module.Disposition.PASS,
        evaluation_module.Disposition.INCONCLUSIVE,
        evaluation_module.Disposition.FAIL,
    )) is evaluation_module.Disposition.FAIL
    assert evaluation_module._v2_conjunction_disposition((
        evaluation_module.Disposition.FAIL,
        evaluation_module.Disposition.INVALID_DATA,
        evaluation_module.Disposition.PASS,
    )) is evaluation_module.Disposition.INVALID_DATA


def test_v2_report_nested_tamper_and_status_rescue_are_refused() -> None:
    report = evaluation_module._build_formal_evaluation_report(
        _input(), resamples=7
    )
    item = dataclasses.replace(report.primary_gates[0], status=evaluation_module.Disposition.PASS)
    forged = dataclasses.replace(report, primary_gates=(item, *report.primary_gates[1:]))
    with pytest.raises(FormalEvaluationError):
        evaluation_module.require_formal_evaluation_report(forged)
    object.__setattr__(report.economic_summaries[0], "cost_bps_per_side", 11)
    with pytest.raises(FormalEvaluationError):
        evaluation_module.require_formal_evaluation_report(report)


def test_v2_public_entry_has_no_resample_override_and_module_has_no_io_or_synthetic_import() -> None:
    import inspect
    signature = inspect.signature(evaluation_module.build_formal_evaluation_report)
    assert tuple(signature.parameters) == ("evaluation_input",)
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert all("synthetic" not in name and "global_input_bundle" not in name
               for name in imported)
    assert {"pathlib", "subprocess", "socket", "urllib", "requests"}.isdisjoint(
        {name.split(".")[0] for name in imported}
    )
    # ``os`` is present only for process-origin validation and at-fork
    # authority reset; the arithmetic module still exposes no filesystem or
    # environment read surface.
    assert "os" in imported
    assert "os.environ" not in source and "os.getenv" not in source
    for forbidden in (
        "open(", "ObjectStore", "create_backtest", "compile_project",
        "SetHoldings", "MarketOrder", "LimitOrder",
    ):
        assert forbidden not in source


def test_v2_public_entry_always_dispatches_exactly_19999_resamples(monkeypatch) -> None:
    requested: list[tuple[str, int]] = []

    def controlled_stock(**kwargs):
        requested.append(("stock", kwargs["resamples"]))
        return (Decimal(0),) * kwargs["resamples"]

    def controlled_paired(**kwargs):
        requested.append(("paired", kwargs["resamples"]))
        return (Decimal(0),) * kwargs["resamples"]

    monkeypatch.setattr(
        evaluation_module, "_v2_stock_centered_bootstrap", controlled_stock
    )
    monkeypatch.setattr(
        evaluation_module, "_v2_paired_centered_bootstrap", controlled_paired
    )
    report = evaluation_module.build_formal_evaluation_report(
        evaluation_input=_input()
    )
    assert requested and {kind for kind, _count in requested} == {
        "paired", "stock"
    }
    assert {count for _kind, count in requested} == {19_999}
    assert all(
        item.bootstrap_resamples == 19_999
        for item in report.fama_macbeth_summaries
        if item.bootstrap_resamples is not None
    )


def test_v2_stable_sum_orders_wide_decimals_by_exact_magnitude() -> None:
    """The frozen tie-break must not round its sort keys to 50 digits."""
    values = (
        Decimal("1E-52"),
        Decimal("-1." + "0" * 49 + "02"),
        Decimal("1." + "0" * 49 + "01"),
    )
    with localcontext(evaluation_module._context()):
        exact_magnitude_order = evaluation_module._stable_sum(values)
        rounded_magnitude_order = Decimal(0)
        for value in sorted(values, key=lambda item: (abs(item), item)):
            rounded_magnitude_order += value

    assert exact_magnitude_order == Decimal("-2E-51")
    assert rounded_magnitude_order == Decimal("1E-51")


def test_v2_two_sided_p_compares_wide_decimal_magnitudes_exactly() -> None:
    """A replicate below the observed value cannot tie after context rounding."""
    observed = Decimal("1." + "0" * 49 + "02")
    just_below = Decimal("1." + "0" * 49 + "01")
    with localcontext(evaluation_module._context()):
        assert abs(just_below) == abs(observed)
        exact = evaluation_module._v2_two_sided_p(observed, (just_below,))

    assert exact == Fraction(1, 2)


def test_v2_report_is_independent_of_ambient_decimal_context() -> None:
    value = _input()
    with localcontext() as ambient:
        ambient.prec = 7
        ambient.rounding = ROUND_DOWN
        narrow = evaluation_module._build_formal_evaluation_report(
            value, resamples=7
        )
    with localcontext() as ambient:
        ambient.prec = 31
        ambient.rounding = ROUND_CEILING
        wide = evaluation_module._build_formal_evaluation_report(
            value, resamples=7
        )

    assert narrow == wide
    assert narrow.report_sha256 == wide.report_sha256


def test_v2_sleeve_rank_uses_exact_wide_decimal_score() -> None:
    decisions = [
        evaluation_module.build_economic_decision(
            decision_lineage_sha256=_sha("wide-rank-z"),
            security_id="security-z",
            firm_specific_score=Decimal("1." + "0" * 49 + "02"),
        ),
        evaluation_module.build_economic_decision(
            decision_lineage_sha256=_sha("wide-rank-a"),
            security_id="security-a",
            firm_specific_score=Decimal("1." + "0" * 49 + "01"),
        ),
    ]
    decisions.extend(
        evaluation_module.build_economic_decision(
            decision_lineage_sha256=_sha(f"wide-rank-{index}"),
            security_id=f"security-{index:02d}",
            firm_specific_score=Decimal("0.5"),
        )
        for index in range(23)
    )
    with localcontext() as ambient:
        ambient.prec = 7
        selected = evaluation_module._v2_selected_sleeve(tuple(decisions))

    assert selected[:2] == ("security-z", "security-a")
    assert len(selected) == 5
    held = evaluation_module._v2_new_sleeve(selected)
    assert held.original_name_count == len(selected)
    assert held.active_security_ids == tuple(sorted(selected))
    assert tuple(evaluation_module._v2_targets((held,))) == tuple(sorted(selected))
