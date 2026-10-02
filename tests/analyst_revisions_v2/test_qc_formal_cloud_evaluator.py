from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import formal_cloud_evaluator as cloud
from research.analyst_revisions_v2_qc import formal_evaluation as host
from research.analyst_revisions_v2_qc.formal_report_contract import (
    build_formal_report_contract,
    formal_report_contract_record,
)


def _closure_value(function, name):
    values = dict(zip(function.__code__.co_freevars, function.__closure__ or ()))
    return values[name].cell_contents


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _session_dates(start: str, end_exclusive: str) -> tuple[date, ...]:
    return tuple(
        item
        for item in trading_sessions(
            date.fromisoformat(start), date.fromisoformat(end_exclusive)
        )
        if item.isoformat() < end_exclusive
    )


@lru_cache(maxsize=1)
def _axes():
    date_sets = [
        _session_dates(item[2], item[3])
        for item in host.FORMAL_FOLD_HORIZON_AXIS_SUMMARIES
    ]
    economic_dates = [
        (*_session_dates(item[1], item[5]), date.fromisoformat(item[5]))
        for item in host.ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES
    ]
    positions = {
        session: index
        for index, session in enumerate(
            sorted({item for values in (*date_sets, *economic_dates) for item in values})
        )
    }
    return tuple(
        host.FoldSessionAxis(
            fold_id=frozen[0],
            horizon_sessions=frozen[1],
            sessions=tuple(
                host.SessionPoint(session, positions[session])
                for session in sessions
            ),
        )
        for frozen, sessions in zip(
            host.FORMAL_FOLD_HORIZON_AXIS_SUMMARIES, date_sets, strict=True
        )
    )


@lru_cache(maxsize=1)
def _economic_axes():
    all_dates = sorted(
        {
            point.session
            for axis in _axes()
            for point in axis.sessions
        }
        | {
            item
            for frozen in host.ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES
            for item in (
                *_session_dates(frozen[1], frozen[5]),
                date.fromisoformat(frozen[5]),
            )
        }
    )
    positions = {session: index for index, session in enumerate(all_dates)}
    return tuple(
        host.EconomicObservationAxis(
            fold_id=frozen[0],
            sessions=tuple(
                host.SessionPoint(session, positions[session])
                for session in (
                    *_session_dates(frozen[1], frozen[5]),
                    date.fromisoformat(frozen[5]),
                )
            ),
        )
        for frozen in host.ECONOMIC_FOLD_OBSERVATION_AXIS_SUMMARIES
    )


def _bindings():
    return cloud.FormalCloudEvaluationBindings(
        input_manifest_sha256=_sha("manifest"),
        production_scoring_census_sha256=_sha("scoring-census"),
        evaluation_input_bundle_id="evaluation-input-bundle-1",
        evaluation_input_bundle_sha256=_sha("evaluation-input-bundle"),
        terminal_disposition_package_sha256=_sha("terminals"),
        shared_market_panel_sha256=_sha("market-panel"),
        shared_market_panel_observation_count=99,
        formal_evaluator_source_sha256=_sha("formal-evaluator-source"),
        evaluator_source_closure_sha256=_sha("evaluator-source-closure"),
        execution_plan_sha256=_sha("execution-plan"),
        capacity_plan_sha256=_sha("capacity-plan"),
    )


def _input(source_view_id: str):
    axes = _axes()
    economic_axes = _economic_axes()
    point = next(
        axis.sessions[0]
        for axis in axes
        if axis.fold_id == host.FORMAL_FOLD_IDS[0]
        and axis.horizon_sessions == 60
    )
    controls = tuple(Decimal(index) / Decimal(100) for index in range(19))
    binaries = (0, 1, 0, 0, 0, 0)
    rows = tuple(
        host.build_evaluation_row(
            source_lineage_sha256=_sha(f"lineage:{source_view_id}"),
            fold_id=host.FORMAL_FOLD_IDS[0],
            decision_session=point.session,
            session_position=point.session_position,
            security_id="security-001",
            industry_id="industry-001",
            common_event_component_id="component-001",
            horizon_sessions=horizon,
            firm_specific_score=Decimal("1"),
            global_score=Decimal("0.5"),
            structural_zero=False,
            continuous_control_values=controls,
            binary_control_values=binaries,
            active_event_indicator=1,
            absolute_contribution_weighted_publication_to_entry_jump=Decimal("0.01"),
            excess_total_return=Decimal("0.02"),
        )
        for horizon in host.HORIZONS
    )
    economic = []
    for axis in economic_axes:
        for item in axis.sessions:
            decisions = ()
            if axis.fold_id == host.FORMAL_FOLD_IDS[0] and item == point:
                decisions = (
                    host.build_economic_decision(
                        decision_lineage_sha256=rows[0].source_lineage_sha256,
                        security_id="security-001",
                        firm_specific_score=Decimal("1"),
                    ),
                )
            economic.append(
                host.build_economic_session(
                    source_lineage_sha256=_sha(
                        f"economic:{source_view_id}:{axis.fold_id}:{item.session_position}"
                    ),
                    fold_id=axis.fold_id,
                    session=item.session,
                    session_position=item.session_position,
                    benchmark_total_return=Decimal("0"),
                    benchmark_refusal_reason=None,
                    decisions=decisions,
                    security_outcomes=(),
                )
            )
    bindings = _bindings()
    return host.build_formal_evaluation_input(
        source_view_id=source_view_id,
        source_bundle_id=bindings.evaluation_input_bundle_id,
        source_bundle_sha256=bindings.evaluation_input_bundle_sha256,
        source_artifact_sha256=bindings.shared_market_panel_sha256,
        fold_axes=axes,
        economic_observation_axes=economic_axes,
        economic_execution_definition_sha256=(
            host.ECONOMIC_EXECUTION_DEFINITION_SHA256
        ),
        power_floor=host.PowerFloorBinding(
            receipt_id="power-receipt-1",
            receipt_sha256=_sha("power"),
            required_valid_dates=50,
            required_connected_components=50,
            h20_test_session_capacity=1388,
            preoutcome_candidate_date_count=50,
            valid_h20_test_session_count=50,
            refused_h20_test_session_count=0,
            missing_h20_test_session_count=1338,
            connected_component_instance_count=50,
        ),
        rows=rows,
        refusals=(),
        economic_sessions=tuple(economic),
    )


def _terminals():
    return cloud.FormalCloudTerminalCensus(
        terminal_policy_id=cloud.TERMINAL_POLICY_ID,
        terminal_requirement_count=2,
        terminal_payoff_count=1,
        benchmark_splice_continuation_count=1,
        named_terminal_refusal_count=0,
        used_terminal_disposition_count=2,
        unused_terminal_disposition_count=0,
        silently_omitted_terminal_count=0,
    )


@lru_cache(maxsize=1)
def _report_contract():
    return formal_report_contract_record(build_formal_report_contract(
        economic_execution_definition_sha256=(
            host.ECONOMIC_EXECUTION_DEFINITION_SHA256
        )
    ))


def _empty_economic_censuses(
    overrides: dict[tuple[str, int], tuple[int, int, int, tuple[tuple[str, int], ...]]]
    | None = None,
):
    overrides = {} if overrides is None else overrides
    rows = []
    for fold in host.FORMAL_FOLD_IDS:
        for cost in host.COST_BPS_GRID:
            session_count, valid_count, refused_count, refusal_counts = (
                overrides.get((fold, cost), (0, 0, 0, ()))
            )
            rows.append(host.EconomicTrialFoldCensus(
                fold_id=fold, cost_bps_per_side=cost,
                session_count=session_count,
                valid_return_session_count=valid_count,
                refused_return_session_count=refused_count,
                invested_session_count=0, cash_sleeve_count=0,
                selected_sleeve_count=0,
                terminal_liquidation_turnover=Decimal(0),
                refusal_counts=refusal_counts,
                refusal_counts_by_session=tuple(
                    (
                        date(2020, 1, 1) + timedelta(days=index),
                        refusal_counts,
                    )
                    for index in range(refused_count)
                ),
                reasons=(),
            ))
    return tuple(rows)


def _stream_result(*, observations=(), censuses=None, daily_ic=()):
    return host.FormalEvaluationStreamingResult(
        report=None, accepted_row_count=0, refused_row_count=0,
        economic_session_count=0, fold_horizon_census=(),
        economic_trial_observations=tuple(observations),
        economic_trial_fold_census=(
            _empty_economic_censuses() if censuses is None else censuses
        ),
        daily_information_coefficient_observations=tuple(daily_ic),
    )


def test_cloud_wrapper_executes_exact_host_evaluator_for_both_views():
    inputs = tuple(_input(view) for view in host.SOURCE_VIEW_IDS)
    payload = cloud.execute_cloud_formal_evaluation(
        inputs=inputs, bindings=_bindings(), terminal_census=_terminals()
    )
    document = json.loads(payload)
    host_reports = tuple(host.build_formal_evaluation_report(evaluation_input=item)
                         for item in inputs)

    assert document["reports"] == [
        json.loads(item._canonical_document) for item in host_reports
    ]
    assert document["bootstrap_resamples"] == 19_999
    assert document["fold_horizon_axis_count"] == 24
    assert document["source_view_fold_horizon_axis_count"] == 48
    assert document["terminal_census"][
        "benchmark_splice_continuation_count"
    ] == 1
    assert document["raw_outcome_rows_exported"] is False
    assert document["orders_placed"] == 0
    assert cloud.require_formal_cloud_evaluation_aggregate_bytes(
        payload, expected_bindings=_bindings()
    ) == document


def test_cloud_wrapper_and_host_match_with_adversarial_named_refusal():
    inputs = list(_input(view) for view in host.SOURCE_VIEW_IDS)
    source = inputs[0].rows[-1]
    refusal = host.build_evaluation_refusal(
        source_lineage_sha256=source.source_lineage_sha256,
        fold_id=source.fold_id,
        decision_session=source.decision_session,
        session_position=source.session_position,
        security_id=source.security_id,
        horizon_sessions=source.horizon_sessions,
        reason=host.RefusalReason.TERMINAL_PAYOFF_UNRESOLVED,
    )
    inputs[0] = host.build_formal_evaluation_input(
        source_view_id=inputs[0].source_view_id,
        source_bundle_id=inputs[0].source_bundle_id,
        source_bundle_sha256=inputs[0].source_bundle_sha256,
        source_artifact_sha256=inputs[0].source_artifact_sha256,
        fold_axes=inputs[0].fold_axes,
        economic_observation_axes=inputs[0].economic_observation_axes,
        economic_execution_definition_sha256=(
            inputs[0].economic_execution_definition_sha256
        ),
        power_floor=inputs[0].power_floor,
        rows=inputs[0].rows[:-1],
        refusals=(refusal,),
        economic_sessions=inputs[0].economic_sessions,
    )
    payload = cloud._execute_cloud_formal_evaluation(
        inputs=tuple(inputs),
        bindings=_bindings(),
        terminal_census=_terminals(),
        resamples=31,
    )
    document = json.loads(payload)
    expected = tuple(
        host._build_formal_evaluation_report(item, resamples=31) for item in inputs
    )
    assert document["reports"] == [json.loads(item._canonical_document) for item in expected]
    assert document["source_view_census"][0]["refused_count"] == 1


def test_cloud_wrapper_rejects_cross_panel_view_and_binding_tamper():
    current, censored = tuple(_input(view) for view in host.SOURCE_VIEW_IDS)
    changed = dataclasses.replace(censored, source_artifact_sha256=_sha("other-panel"))
    with pytest.raises(cloud.FormalCloudEvaluationError, match="input changed"):
        cloud.execute_cloud_formal_evaluation(
            inputs=(current, changed),
            bindings=_bindings(),
            terminal_census=_terminals(),
        )

    with pytest.raises(cloud.FormalCloudEvaluationError, match="terminal requirements"):
        cloud.FormalCloudTerminalCensus(
            terminal_policy_id=cloud.TERMINAL_POLICY_ID,
            terminal_requirement_count=2,
            terminal_payoff_count=1,
            benchmark_splice_continuation_count=0,
            named_terminal_refusal_count=0,
            used_terminal_disposition_count=2,
            unused_terminal_disposition_count=0,
            silently_omitted_terminal_count=0,
        )


def test_aggregate_validator_refuses_rehashed_axis_and_report_mutations():
    inputs = tuple(_input(view) for view in host.SOURCE_VIEW_IDS)
    payload = cloud.execute_cloud_formal_evaluation(
        inputs=inputs, bindings=_bindings(), terminal_census=_terminals()
    )
    changed = json.loads(payload)
    changed["source_view_fold_horizon_census"][0]["accepted_count"] += 1
    with pytest.raises(cloud.FormalCloudEvaluationError, match="exhaustive"):
        cloud.require_formal_cloud_evaluation_aggregate_bytes(
            (
                json.dumps(changed, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode()
        )

    changed = json.loads(payload)
    changed["reports"][0]["disposition"] = "PASS"
    with pytest.raises(cloud.FormalCloudEvaluationError, match="identity"):
        cloud.require_formal_cloud_evaluation_aggregate_bytes(
            (
                json.dumps(changed, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode()
        )


def _compact_stream_fixture():
    benchmark = "SPY R735QTJ8XC9X"
    result_bindings = [
        {
            "fold_id": fold,
            "result_id": f"result-{index}",
            "result_sha256": _sha(f"result:{index}"),
            "precontrol_batch_id": f"batch-{index}",
            "precontrol_batch_sha256": _sha(f"batch:{index}"),
            "model_sha256s": [_sha(f"model:{index}:0"), _sha(f"model:{index}:1")],
        }
        for index, fold in enumerate(host.FORMAL_FOLD_IDS)
    ]
    economic = []
    points = []
    h1_axes = {
        axis.fold_id: axis.sessions for axis in _axes()
        if axis.horizon_sessions == 1
    }
    economic_axes = {axis.fold_id: axis.sessions for axis in _economic_axes()}
    for view in host.SOURCE_VIEW_IDS:
        for fold in host.FORMAL_FOLD_IDS:
            axis = tuple(sorted(
                {
                    point.session_position: point
                    for point in (*h1_axes[fold], *economic_axes[fold])
                }.values(),
                key=lambda item: item.session_position,
            ))
            for offset, point in enumerate(axis):
                session = point.session
                position = point.session_position
                if offset + 1 < len(axis):
                    next_point = axis[offset + 1]
                    next_session = next_point.session
                    next_position = next_point.session_position
                else:
                    # Legacy rows require a syntactic next-session pair.  The
                    # compact evaluator derives the final liquidation marker
                    # from the authenticated exact axis and discards this
                    # placeholder before any market observation is inspected.
                    next_session = session + timedelta(days=1)
                    next_position = position + 1
                record = {
                    "source_view_id": view,
                    "fold_id": fold,
                    "session": session.isoformat(),
                    "session_position": position,
                    "next_session": next_session.isoformat(),
                    "next_session_position": next_position,
                }
                lineage = hashlib.sha256(cloud._canonical_bytes({
                    "schema": cloud.ECONOMIC_JOIN_SCHEMA, **record,
                })).hexdigest()
                economic.append({
                    "schema": cloud.ECONOMIC_JOIN_SCHEMA,
                    **record,
                    "source_lineage_sha256": lineage,
                })
                if view == host.SOURCE_VIEW_IDS[0]:
                    points.append((fold, session.isoformat(), position))
    economic.sort(key=lambda row: cloud._role_row_key("economic_joins", row))

    decisions = []
    decision_point = next(
        axis.sessions[0] for axis in _axes()
        if axis.fold_id == host.FORMAL_FOLD_IDS[0]
        and axis.horizon_sessions == 60
    )
    position_dates = {
        point.session_position: point.session
        for axis in _axes() for point in axis.sessions
    }
    for view in host.SOURCE_VIEW_IDS:
        fold = host.FORMAL_FOLD_IDS[0]
        session = decision_point.session.isoformat()
        position = decision_point.session_position
        security = "ABC R00000000001"
        entry = cloud.build_daily_market_requirement_id(
            security_id=security, session=session
        )
        benchmark_entry = cloud.build_daily_market_requirement_id(
            security_id=benchmark, session=session
        )
        row = {
            "schema": cloud.DECISION_JOIN_SCHEMA,
            "decision_id": "placeholder",
            "decision_lineage_sha256": "0" * 64,
            "source_view_id": view,
            "fold_id": fold,
            "decision_session": session,
            "session_position": position,
            "security_id": security,
            "disposition": "scored_decision",
            "scoring_disposition": "included_structural_zero",
            "source_row_sha256": _sha(f"source:{view}"),
            "scoring_result_id": result_bindings[0]["result_id"],
            "scoring_result_sha256": result_bindings[0]["result_sha256"],
            "scoring_contract_id": cloud.SCORING_CONTRACT_ID,
            "scoring_contract_sha256": cloud.SCORING_CONTRACT_SHA256,
            "industry_id": "industry-1",
            "common_event_component_id": f"component-{view}",
            "structural_zero": True,
            "firm_specific_score": "0",
            "global_score": "0",
            "continuous_controls": ["0"] * 19,
            "binary_controls": [0] * 6,
            "realized_volatility_60d": "0.25",
            "earnings_anchor_signed_session_distance": None,
            "contribution_count": 0,
            "contribution_state_sha256": hashlib.sha256(cloud._canonical_bytes({
                "domain": cloud.CONTRIBUTION_STATE_DOMAIN,
                "contributions": [],
            })).hexdigest(),
            "entry_daily_requirement_id": entry,
            "benchmark_entry_daily_requirement_id": benchmark_entry,
            "horizon_exits": [],
        }
        for horizon in host.HORIZONS:
            exit_session = position_dates[position + horizon].isoformat()
            row["horizon_exits"].append({
                "horizon": horizon,
                "exit_session": exit_session,
                "exit_session_position": position + horizon,
                "stock_daily_requirement_id": (
                    cloud.build_daily_market_requirement_id(
                        security_id=security, session=exit_session
                    )
                ),
                "benchmark_daily_requirement_id": (
                    cloud.build_daily_market_requirement_id(
                        security_id=benchmark, session=exit_session
                    )
                ),
            })
        decision_id, lineage = cloud._decision_identity(row)
        row["decision_id"] = decision_id
        row["decision_lineage_sha256"] = lineage
        decisions.append(row)
    decisions.sort(key=lambda row: cloud._role_row_key("decision_joins", row))
    partition_key = [{
        "fold_id": host.FORMAL_FOLD_IDS[0],
        "session_position": decision_point.session_position,
        "security_id": "ABC R00000000001",
    }]
    package = {
        "artifact_id": "evaluation-input-bundle-1",
        "content_sha256": _sha("evaluation-input-bundle"),
        "artifact_sha256": _sha("evaluation-input-artifact"),
        "byte_count": 1,
    }
    preopen = {
        "artifact_id": "preopen-output-1", "content_sha256": _sha("preopen"),
        "artifact_sha256": _sha("preopen-artifact"), "byte_count": 1,
    }
    contract = {
        "schema": cloud.FORMAL_INPUT_CONTRACT_SCHEMA,
        "evaluation_id": host.EVALUATION_ID,
        "evaluation_input_bundle_id": package["artifact_id"],
        "evaluation_input_bundle_sha256": package["content_sha256"],
        "production_scoring_census_id": "scoring-census-1",
        "production_scoring_census_sha256": _sha("scoring-census"),
        "scoring_contract_id": cloud.SCORING_CONTRACT_ID,
        "scoring_contract_sha256": cloud.SCORING_CONTRACT_SHA256,
        "scoring_result_bindings": result_bindings,
        "production_truth_artifact_id": "truth-1",
        "production_truth_artifact_sha256": _sha("truth"),
        "preopen_control_stage_output": preopen,
        "formal_evaluator_source_sha256": _sha("formal-source"),
        "accepted_risk": {},
        "power_floor": {
            "receipt_id": "power-1", "receipt_sha256": _sha("power"),
            "required_valid_dates": 50,
            "required_connected_components": 50,
            "h20_test_session_capacity": 1388,
            "preoutcome_candidate_date_count": 50,
            "valid_h20_test_session_count": 50,
            "refused_h20_test_session_count": 0,
            "missing_h20_test_session_count": 1338,
            "connected_component_instance_count": 50,
        },
        "terminal_package_id": "terminal-1",
        "terminal_package_sha256": _sha("terminal"),
        "terminal_census": {
            "terminal_policy_id": cloud.TERMINAL_POLICY_ID,
            "terminal_requirement_count": 0, "terminal_payoff_count": 0,
            "benchmark_splice_continuation_count": 0,
            "named_terminal_refusal_count": 0, "silently_omitted_count": 0,
        },
        "source_view_partitions": [
            {
                "view_id": view, "decision_count": 1,
                "scored_decision_count": 1,
                "named_preoutcome_refusal_count": 0,
                "terminal_key_sha256": cloud._terminal_key_census_sha256(
                    partition_key
                ),
            }
            for view in host.SOURCE_VIEW_IDS
        ],
        "stream_layout": {
            "layout_id": cloud.STREAM_LAYOUT_ID,
            "role_sort_keys": {
                role: list(fields)
                for role, fields in cloud.STREAM_ROLE_SORT_KEYS.items()
            },
            "session_or_market_day_blocks_never_split_across_shards": True,
            "formal_contract_and_economic_axis_are_bounded_headers": True,
            "terminal_dispositions_are_the_actual_lifecycle_subset": True,
            "market_observation_collection_passes": 2,
            "maximum_horizon_session_lookahead": 60,
            "second_pass_rederives_observations": True,
            "terminal_subset_is_capacity_bounded_header": True,
        },
    }
    resource = {
        "formal_contract_count": 1, "contribution_seed_count": 0,
        "decision_join_count": 2, "economic_join_count": len(economic),
        "daily_requirement_count": 1, "minute_requirement_count": 0,
        "terminal_disposition_count": 0,
    }
    manifest = {
        "schema": cloud.INPUT_MANIFEST_SCHEMA,
        "evaluation_id": host.EVALUATION_ID,
        "production_input_package": package,
        "preopen_control_stage_output": preopen,
        "runtime_start": "2020-01-03", "runtime_end": "2026-03-30",
        "calculation_as_of_date": "2026-08-28",
        "benchmark_security_id": benchmark,
        "formal_primary_fold_ids": list(host.FORMAL_FOLD_IDS),
        "descriptive_sensitivity_fold_ids": list(host.DESCRIPTIVE_FOLD_IDS),
        "descriptive_sensitivity_cannot_replace_or_rescue_primary": True,
        "source_view_ids": list(host.SOURCE_VIEW_IDS),
        "horizons": list(host.HORIZONS), "primary_horizon": 20,
        "economic_holding_sessions": 20, "orders_authorized": False,
        "market_contract": {
            "daily_normalization": "TotalReturn",
            "daily_observation": "open_to_next_open",
            "publication_price": (
                "last_tradable_minute_strictly_before_publication"
            ),
            "positive_firm_weighted_jump": True,
            "empty_positive_firm_weight_set_jump": "0",
            "terminal_policy_id": cloud.TERMINAL_POLICY_ID,
            "qc_delisting_price_is_terminal_payoff": False,
            "failed_arm_omission_forbidden": True,
            "shared_market_panel_across_views": True,
        },
        "resource_census": resource,
        "cloud_evaluator": {
            "artifact_id": "cloud-evaluator-1",
            "content_sha256": _sha("cloud-evaluator"),
            "artifact_sha256": _sha("cloud-evaluator-artifact"),
            "byte_count": 1,
        },
        "capacity_review": {
            "candidate_sha256": _sha("capacity-candidate"),
            "receipt_id": "capacity-1", "receipt_sha256": _sha("capacity"),
            "limits": {}, "representative_full_census_verified": True,
            "target_tier_limits_observed": True,
            "cloud_evaluator_equivalence_verified": True,
            "object_store_input_transport_verified": True,
            "object_store_output_write_once_transport_verified": True,
            "summary_statistics_channel_verified": True,
            "summary_root_result_channel_verified": True,
        },
        "shards": [],
    }
    blocks = []
    for fold, session, position in sorted(
        set(points), key=lambda item: (host.FORMAL_FOLD_IDS.index(item[0]), item[2])
    ):
        block_decisions = (
            decisions
            if fold == host.FORMAL_FOLD_IDS[0]
            and position == decision_point.session_position else []
        )
        axis = tuple(sorted(
            {
                point.session_position: point
                for point in (*h1_axes[fold], *economic_axes[fold])
            }.values(),
            key=lambda item: item.session_position,
        ))
        axis_index = next(
            index for index, item in enumerate(axis)
            if item.session_position == position
        )
        used = set()
        if axis_index + 1 < len(axis):
            next_session = axis[axis_index + 1].session.isoformat()
            used.update({
                (
                    cloud.build_daily_market_requirement_id(
                        security_id=benchmark, session=session
                    ), benchmark, session,
                ),
                (
                    cloud.build_daily_market_requirement_id(
                        security_id=benchmark, session=next_session
                    ), benchmark, next_session,
                ),
            })
        for row in block_decisions:
            used.add((row["entry_daily_requirement_id"], row["security_id"], session))
            used.add((row["benchmark_entry_daily_requirement_id"], benchmark, session))
            for exit_row in row["horizon_exits"]:
                used.add((exit_row["stock_daily_requirement_id"], row["security_id"], exit_row["exit_session"]))
                used.add((exit_row["benchmark_daily_requirement_id"], benchmark, exit_row["exit_session"]))
        requirements = sorted((
            {"schema": cloud.DAILY_REQUIREMENT_SCHEMA, "requirement_id": item[0],
             "security_id": item[1], "session": item[2]}
            for item in used
        ), key=lambda row: cloud._role_row_key("daily_requirements", row))
        observations = {
            "schema": cloud.MARKET_OBSERVATION_PANEL_SCHEMA,
            "daily": [
                {"schema": cloud.DAILY_OBSERVATION_SCHEMA,
                 "requirement_id": item["requirement_id"],
                 "security_id": item["security_id"], "session": item["session"],
                 "disposition": "observation", "open": "100", "reason": None}
                for item in requirements
            ],
            "minute": [],
        }
        blocks.append((
            fold, session, position, block_decisions, requirements, observations
        ))
    return manifest, contract, economic, blocks, decisions


def _consumed_compact_stream():
    manifest, contract, economic, blocks, _decisions = _compact_stream_fixture()
    stream = cloud.begin_compact_formal_evaluation(
        manifest=manifest, formal_contract_rows=[contract],
        economic_joins=economic, terminal_dispositions=[],
        shared_market_panel_sha256=_sha("sealed-market-panel"),
        shared_market_panel_observation_count=999,
    )
    for fold, session, position, decisions, requirements, observations in blocks:
        cloud.consume_compact_formal_session_block(
            stream, fold_id=fold, session=session, session_position=position,
            decision_joins=decisions, new_contribution_seeds=[],
            daily_requirements=requirements, minute_requirements=[],
            observations=observations,
        )
    return stream


def test_compact_session_stream_is_bounded_valid_and_one_use():
    stream = _consumed_compact_stream()
    payload = cloud.finish_compact_formal_evaluation(stream, resamples=7)
    document = cloud.require_formal_cloud_evaluation_aggregate_bytes(
        payload, expected_bootstrap_resamples=7
    )
    assert document["source_view_census"][0]["accepted_count"] == 4
    assert document["source_view_census"][1]["accepted_count"] == 4
    assert document["terminal_census"]["terminal_requirement_count"] == 0
    with pytest.raises(cloud.FormalCloudEvaluationError, match="sealed"):
        cloud.finish_compact_formal_evaluation(stream, resamples=7)


def test_legacy_compact_stream_cannot_mint_streamed_multipart_output():
    with pytest.raises(
        cloud.FormalCloudEvaluationError,
        match="lacks exact streamed preknown bindings",
    ):
        cloud.finish_compact_formal_evaluation_output(
            _consumed_compact_stream(), resamples=7
        )


@pytest.mark.parametrize(
    "capacity_name",
    (
        "object_store_output_write_once_transport_verified",
        "summary_root_result_channel_verified",
    ),
)
def test_cloud_stream_requires_result_transport_capacity_before_evaluation(
    capacity_name,
):
    manifest, contract, economic, _blocks, _decisions = _compact_stream_fixture()
    manifest = {
        **manifest,
        "capacity_review": {
            **manifest["capacity_review"],
            capacity_name: False,
        },
    }
    with pytest.raises(
        cloud.FormalCloudEvaluationError,
        match="capacity/equivalence gate is not affirmative",
    ):
        cloud.begin_compact_formal_evaluation(
            manifest=manifest,
            formal_contract_rows=[contract],
            economic_joins=economic,
            terminal_dispositions=[],
            shared_market_panel_sha256=_sha("sealed-market-panel"),
            shared_market_panel_observation_count=999,
        )


def test_mutable_authority_operations_are_lexically_hidden_and_forgery_fails():
    forbidden = (
        "_build_cloud_stream_authorities",
        "_bind_cloud_evaluation_authorities",
        "_register_compact_stream_authority",
        "_lookup_compact_stream_authority",
        "_update_compact_stream_authority",
        "_register_market_panel_authority",
        "_lookup_market_panel_authority",
        "_update_market_panel_authority",
        "_register_cloud_evaluation_output_authority",
        "_lookup_cloud_evaluation_output_authority",
        "_update_cloud_evaluation_output_authority",
        "_configure_cloud_stream_authority_callers",
        "_reset_cloud_stream_authorities_after_fork",
        "_COMPACT_STREAMS",
        "_MARKET_PANEL_DIGESTS",
    )
    assert all(not hasattr(cloud, name) for name in forbidden)

    fake_panel = object.__new__(cloud.FormalMarketPanelDigest)
    object.__setattr__(fake_panel, "digest_id", "arv2-market-panel-digest-fake")
    object.__setattr__(fake_panel, "schema", cloud.MARKET_PANEL_STREAM_SCHEMA)
    with pytest.raises(cloud.FormalCloudEvaluationError, match="authenticated"):
        cloud.finish_formal_market_panel_digest(fake_panel)

    fake_output = object.__new__(cloud.FormalCloudEvaluationOutput)
    for field in dataclasses.fields(cloud.FormalCloudEvaluationOutput):
        object.__setattr__(
            fake_output,
            field.name,
            (
                cloud.FORMAL_CLOUD_EVALUATION_OUTPUT_SCHEMA
                if field.name == "schema"
                else 1 if field.type is int else "forged"
            ),
        )
    with pytest.raises(cloud.FormalCloudEvaluationError, match="authenticated"):
        cloud.require_formal_cloud_evaluation_output(fake_output)


def test_reflected_cloud_authority_cannot_register_or_reseal_mutable_state():
    producer = _closure_value(
        cloud.begin_formal_market_panel_digest, "begin_panel_impl"
    )
    registrar = _closure_value(
        cloud.begin_formal_market_panel_digest, "register_panel"
    )
    fake = object.__new__(cloud.FormalMarketPanelDigest)
    object.__setattr__(fake, "digest_id", "arv2-market-panel-digest-forged")
    object.__setattr__(fake, "schema", cloud.MARKET_PANEL_STREAM_SCHEMA)
    forged_state = cloud._MarketPanelDigestState(
        creator_pid=os.getpid(), owner_thread_id=0,
        expected_count=0, count=0, modular_sum=0, bitwise_xor=0,
        last_keys={}, finished=False, failed=False,
    )
    with pytest.raises(
        cloud.FormalCloudEvaluationError, match="registrar caller changed"
    ):
        registrar(fake, cloud._market_panel_digest_static(fake), forged_state)
    with pytest.raises(
        cloud.FormalCloudEvaluationError, match="registrar caller changed"
    ):
        producer(
            0, _authority_register=registrar,
            _authority_require=lambda value: (value, forged_state),
        )

    panel = cloud.begin_formal_market_panel_digest(0)
    require_internal = _closure_value(
        cloud.finish_formal_market_panel_digest, "require_panel_internal"
    )
    lookup = _closure_value(require_internal, "lookup_panel")
    registered = lookup(panel)
    assert registered is not None
    state = registered[1]
    state.last_keys[9] = ("reflected-injection",)
    updater = _closure_value(
        cloud.consume_formal_market_panel_digest_row, "update_panel"
    )
    with pytest.raises(
        cloud.FormalCloudEvaluationError, match="transition caller changed"
    ):
        updater(panel, state)
    assert lookup(panel) is None
    with pytest.raises(cloud.FormalCloudEvaluationError, match="authenticated"):
        cloud.finish_formal_market_panel_digest(panel)


def test_public_state_fingerprint_rebinding_cannot_reseal_cloud_authority(
    monkeypatch,
):
    panel = cloud.begin_formal_market_panel_digest(0)
    require_internal = _closure_value(
        cloud.finish_formal_market_panel_digest, "require_panel_internal"
    )
    lookup = _closure_value(require_internal, "lookup_panel")
    state = lookup(panel)[1]
    monkeypatch.setattr(cloud, "_cloud_state_sha256", lambda _value: "0" * 64)
    state.last_keys[8] = ("global-rebind-injection",)
    with pytest.raises(cloud.FormalCloudEvaluationError, match="authenticated"):
        cloud.finish_formal_market_panel_digest(panel)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork boundary")
def test_cloud_authority_parent_handle_is_invalidated_in_fork_child():
    panel = cloud.begin_formal_market_panel_digest(0)
    child = os.fork()
    if child == 0:
        try:
            cloud.finish_formal_market_panel_digest(panel)
        except cloud.FormalCloudEvaluationError:
            os._exit(0)
        os._exit(1)
    _, status = os.waitpid(child, 0)
    assert status == 0
    assert cloud.finish_formal_market_panel_digest(panel)[1] == 0


def test_compact_session_stream_refuses_reorder_and_unused_terminal():
    manifest, contract, economic, blocks, _decisions = _compact_stream_fixture()
    stream = cloud.begin_compact_formal_evaluation(
        manifest=manifest, formal_contract_rows=[contract],
        economic_joins=economic, terminal_dispositions=[],
        shared_market_panel_sha256=_sha("sealed-market-panel"),
        shared_market_panel_observation_count=999,
    )
    fold, session, position, decisions, requirements, observations = blocks[1]
    with pytest.raises(cloud.FormalCloudEvaluationError, match="reordered"):
        cloud.consume_compact_formal_session_block(
            stream, fold_id=fold, session=session, session_position=position,
            decision_joins=decisions, new_contribution_seeds=[],
            daily_requirements=requirements, minute_requirements=[],
            observations=observations,
        )


def test_market_panel_digest_is_two_pass_exact_and_role_interleavable():
    daily = {
        "schema": cloud.DAILY_REQUIREMENT_SCHEMA,
        "requirement_id": cloud.build_daily_market_requirement_id(
            security_id="SPY R735QTJ8XC9X", session="2021-01-04"
        ),
        "security_id": "SPY R735QTJ8XC9X", "session": "2021-01-04",
    }
    daily_observation = {
        "schema": cloud.DAILY_OBSERVATION_SCHEMA,
        "requirement_id": daily["requirement_id"],
        "security_id": daily["security_id"], "session": daily["session"],
        "disposition": "observation", "open": "100", "reason": None,
    }
    minute = {
        "schema": cloud.MINUTE_REQUIREMENT_SCHEMA,
        "requirement_id": cloud.build_minute_market_requirement_id(
            security_id="AAA R123", publication_at_utc="2021-01-03T15:00:00Z"
        ),
        "security_id": "AAA R123", "publication_at_utc": "2021-01-03T15:00:00Z",
        "first_active_session_position": 5,
        "last_active_session_position": 24,
    }
    minute_observation = {
        "schema": cloud.MINUTE_OBSERVATION_SCHEMA,
        "requirement_id": minute["requirement_id"],
        "security_id": minute["security_id"],
        "publication_at_utc": minute["publication_at_utc"],
        "disposition": "observation", "last_price": "10",
        "last_bar_end_utc": "2021-01-03T14:59:00Z", "reason": None,
    }
    seals = []
    for pairs in (
        ((daily, daily_observation), (minute, minute_observation)),
        ((minute, minute_observation), (daily, daily_observation)),
    ):
        digest = cloud.begin_formal_market_panel_digest(2)
        for requirement, observation in pairs:
            cloud.consume_formal_market_panel_digest_row(
                digest, requirement=requirement, observation=observation
            )
        seals.append(cloud.finish_formal_market_panel_digest(digest))
        with pytest.raises(cloud.FormalCloudEvaluationError, match="sealed"):
            cloud.finish_formal_market_panel_digest(digest)
    assert seals[0] == seals[1]


def _terminal_row(*, kind, slot_id, horizon, disposition, stock_return, reason):
    return {
        "schema": cloud.TERMINAL_OBJECT_SCHEMA,
        "slot_kind": kind,
        "slot_id": slot_id,
        "horizon": horizon,
        "disposition": disposition,
        "stock_return": stock_return,
        "reason": reason,
        "terminal_lineage_sha256": _sha(
            f"terminal:{kind}:{slot_id}:{horizon}:{disposition}"
        ),
        "available_at_utc": "2026-01-03T00:00:00Z",
    }


@pytest.mark.parametrize(
    ("disposition", "stock_return", "reason", "expected", "refused"),
    (
        ("terminal_payoff", "0.125", None, Decimal("0.125"), False),
        ("named_terminal_refusal", None, "terminal_payoff_unavailable", None, True),
    ),
)
def test_decision_terminal_disposition_precedes_numeric_daily_bars(
    disposition, stock_return, reason, expected, refused,
):
    _manifest, _contract, _economic, _blocks, decisions = _compact_stream_fixture()
    decision = next(
        row for row in decisions
        if row["source_view_id"] == host.SOURCE_VIEW_IDS[0]
    )
    requirement_rows = [
        (
            decision["entry_daily_requirement_id"], decision["security_id"],
            decision["decision_session"],
        ),
        (
            decision["benchmark_entry_daily_requirement_id"],
            "SPY R735QTJ8XC9X", decision["decision_session"],
        ),
    ]
    for exit_row in decision["horizon_exits"]:
        requirement_rows.extend((
            (
                exit_row["stock_daily_requirement_id"],
                decision["security_id"], exit_row["exit_session"],
            ),
            (
                exit_row["benchmark_daily_requirement_id"],
                "SPY R735QTJ8XC9X", exit_row["exit_session"],
            ),
        ))
    daily = {
        requirement_id: {
            "schema": cloud.DAILY_OBSERVATION_SCHEMA,
            "requirement_id": requirement_id, "security_id": security_id,
            "session": session, "disposition": "observation",
            "open": "100", "reason": None,
        }
        for requirement_id, security_id, session in requirement_rows
    }
    horizon = host.HORIZONS[0]
    slot_id = cloud.build_decision_terminal_slot_id(
        decision_id=decision["decision_id"], horizon=horizon
    )
    key = ("decision_horizon", slot_id, horizon)
    terminals = {
        key: _terminal_row(
            kind=key[0], slot_id=slot_id, horizon=horizon,
            disposition=disposition, stock_return=stock_return, reason=reason,
        )
    }
    used = set()

    accepted, refusals = cloud._event_rows(
        view=host.SOURCE_VIEW_IDS[0], decisions=(decision,), seeds={},
        daily=daily, minute={}, terminals=terminals, used_terminals=used,
        fold_axes=_axes(),
    )

    assert used == {key}
    if refused:
        assert not any(row.horizon_sessions == horizon for row in accepted)
        terminal_refusal = next(
            row for row in refusals if row.horizon_sessions == horizon
        )
        assert terminal_refusal.reason is host.RefusalReason.TERMINAL_PAYOFF_UNRESOLVED
    else:
        terminal_result = next(
            row for row in accepted if row.horizon_sessions == horizon
        )
        assert terminal_result.excess_total_return == expected
        assert not any(row.horizon_sessions == horizon for row in refusals)


@pytest.mark.parametrize(
    ("disposition", "stock_return", "reason", "expected", "terminal_applied"),
    (
        ("terminal_payoff", "0.125", None, Decimal("0.125"), True),
        ("benchmark_splice_continuation", None, None, Decimal("0.03"), False),
        ("named_terminal_refusal", None, "terminal_payoff_unavailable", None, False),
    ),
)
def test_economic_terminal_disposition_precedes_numeric_daily_bars(
    disposition, stock_return, reason, expected, terminal_applied,
):
    view = host.SOURCE_VIEW_IDS[0]
    fold = host.FORMAL_FOLD_IDS[0]
    position = 7
    session = "2020-03-02"
    next_session = "2020-03-03"
    security = "ABC R00000000001"
    start_id = cloud.build_daily_market_requirement_id(
        security_id=security, session=session
    )
    end_id = cloud.build_daily_market_requirement_id(
        security_id=security, session=next_session
    )
    daily = {
        start_id: {
            "schema": cloud.DAILY_OBSERVATION_SCHEMA,
            "requirement_id": start_id, "security_id": security,
            "session": session, "disposition": "observation", "open": "100",
            "reason": None,
        },
        end_id: {
            "schema": cloud.DAILY_OBSERVATION_SCHEMA,
            "requirement_id": end_id, "security_id": security,
            "session": next_session, "disposition": "observation", "open": "200",
            "reason": None,
        },
    }
    slot_id = cloud.build_economic_terminal_slot_id(
        view_id=view, fold_id=fold, session_position=position,
        security_id=security,
    )
    key = ("economic_daily", slot_id, None)
    terminals = {
        key: _terminal_row(
            kind=key[0], slot_id=slot_id, horizon=None,
            disposition=disposition, stock_return=stock_return, reason=reason,
        )
    }
    used = set()

    outcome = cloud._economic_security_outcome(
        view=view, fold=fold, position=position, session=session,
        next_session=next_session, security=security,
        benchmark_return=Decimal("0.03"), daily=daily,
        terminals=terminals, used_terminals=used,
    )

    assert used == {key}
    assert outcome.gross_total_return == expected
    assert outcome.terminal_payoff_applied is terminal_applied
    if expected is None:
        assert outcome.disposition is host.EconomicOutcomeDisposition.NAMED_REFUSAL
        assert outcome.reason is host.RefusalReason.TERMINAL_PAYOFF_UNRESOLVED
    else:
        assert outcome.disposition is host.EconomicOutcomeDisposition.RETURN
        assert outcome.reason is None


def test_shared_minute_fact_survives_an_inactive_session_gap():
    manifest, contract, economic, blocks, _decisions = _compact_stream_fixture()
    manifest["resource_census"]["minute_requirement_count"] = 1
    first_position = blocks[0][2]
    last_position = blocks[2][2]
    requirement = {
        "schema": cloud.MINUTE_REQUIREMENT_SCHEMA,
        "requirement_id": cloud.build_minute_market_requirement_id(
            security_id="AAA R123", publication_at_utc="2020-03-01T15:00:00Z"
        ),
        "security_id": "AAA R123", "publication_at_utc": "2020-03-01T15:00:00Z",
        "first_active_session_position": first_position,
        "last_active_session_position": last_position,
    }
    minute_observation = {
        "schema": cloud.MINUTE_OBSERVATION_SCHEMA,
        "requirement_id": requirement["requirement_id"],
        "security_id": requirement["security_id"],
        "publication_at_utc": requirement["publication_at_utc"],
        "disposition": "observation", "last_price": "10",
        "last_bar_end_utc": "2020-03-01T14:59:00Z", "reason": None,
    }
    stream = cloud.begin_compact_formal_evaluation(
        manifest=manifest, formal_contract_rows=[contract],
        economic_joins=economic, terminal_dispositions=[],
        shared_market_panel_sha256=_sha("sealed-market-panel"),
        shared_market_panel_observation_count=1000,
    )
    for index, (
        fold, session, position, decisions, requirements, observations,
    ) in enumerate(blocks[:3]):
        # The same globally deduplicated publication fact is needed again
        # after one inactive session.  Re-presenting its exact bytes proves
        # the public stream retains the authenticated commitment across the
        # gap without exposing its mutable authority state.
        minute_requirements = [requirement] if index in {0, 2} else []
        block_observations = dict(observations)
        block_observations["minute"] = (
            [minute_observation] if index in {0, 2} else []
        )
        cloud.consume_compact_formal_session_block(
            stream, fold_id=fold, session=session, session_position=position,
            decision_joins=decisions, new_contribution_seeds=[],
            daily_requirements=requirements,
            minute_requirements=minute_requirements,
            observations=block_observations,
        )

    # Once the detailed row has expired at its reviewed last-active position,
    # its immutable commitment must still reject a changed replay.  A failed
    # transition permanently locks the opaque stream.
    fold, session, position, decisions, requirements, observations = blocks[3]
    changed_observation = dict(minute_observation, last_price="11")
    changed_panel = dict(observations, minute=[changed_observation])
    with pytest.raises(cloud.FormalCloudEvaluationError, match="differs"):
        cloud.consume_compact_formal_session_block(
            stream, fold_id=fold, session=session, session_position=position,
            decision_joins=decisions, new_contribution_seeds=[],
            daily_requirements=requirements,
            minute_requirements=[requirement], observations=changed_panel,
        )
    with pytest.raises(cloud.FormalCloudEvaluationError, match="locked"):
        cloud.consume_compact_formal_session_block(
            stream, fold_id=fold, session=session, session_position=position,
            decision_joins=decisions, new_contribution_seeds=[],
            daily_requirements=requirements,
            minute_requirements=[], observations=observations,
        )


def test_rolling_window_uses_exact_xnys_positions_without_cross_fold_fill():
    axes = _axes()
    h20 = {
        axis.fold_id: axis.sessions for axis in axes
        if axis.horizon_sessions == 20
    }
    first_fold = host.FORMAL_FOLD_IDS[0]
    second_fold = host.FORMAL_FOLD_IDS[1]
    prior = h20[first_fold][-59:]
    current = h20[second_fold][0]
    daily_ic = tuple(
        host.DailyInformationCoefficientObservation(
            fold_id=first_fold, decision_session=point.session,
            session_position=point.session_position, horizon_sessions=20,
            firm_specific_ic=Decimal("0.1"), firm_specific_reason=None,
            global_map_ic=Decimal("0.2"), global_map_reason=None,
        )
        for point in prior
    ) + (
        host.DailyInformationCoefficientObservation(
            fold_id=second_fold, decision_session=current.session,
            session_position=current.session_position, horizon_sessions=20,
            firm_specific_ic=Decimal("0.3"), firm_specific_reason=None,
            global_map_ic=Decimal("0.4"), global_map_reason=None,
        ),
    )
    rows = cloud._rolling_family_rows(
        result=_stream_result(daily_ic=daily_ic),
        source_view_id=host.SOURCE_VIEW_IDS[0],
        report_contract=_report_contract(), fold_axes=axes,
    )
    cell = next(
        row for row in rows
        if row["slice_id"] == host.FORMAL_SLICE_ID
        and row["window_end_session"] == current.session.isoformat()
        and row["series_id"] == "firm_specific_H20_daily_IC"
    )
    assert cell["axis_session_count"] == 60
    assert cell["valid_observation_count"] == 1
    assert cell["rolling_mean"] == Decimal("0.3")
    assert cell["status"] == "UNAVAILABLE"


def test_dsr_incomplete_six_trial_axis_nulls_every_statistic():
    fold = host.FORMAL_FOLD_IDS[0]
    observations = []
    overrides = {}
    for cost in host.COST_BPS_GRID:
        for index in range(50):
            value = Decimal(index + 1) / Decimal("100000")
            observations.append(host.EconomicTrialObservation(
                fold_id=fold, session=date(2020, 1, 1) + timedelta(days=index),
                session_position=index, cost_bps_per_side=cost,
                gross_portfolio_total_return=value,
                benchmark_total_return=Decimal(0),
                net_portfolio_total_return=(
                    value - Decimal(cost) / Decimal("10000")
                ),
                net_excess_daily_total_return=(
                    value - Decimal(cost) / Decimal("10000")
                ),
                turnover=Decimal(1),
                sleeve_security_incidence_count=5,
                duplicate_sleeve_security_incidence_count=0,
                terminal_liquidation=False,
            ))
        overrides[(fold, cost)] = (50, 50, 0, ())
    result = _stream_result(
        observations=observations,
        censuses=_empty_economic_censuses(overrides),
    )
    registry = _report_contract()["strategy_trial_registry"]
    host_observations, host_censuses = cloud._economic_result_state(result)
    trial_observations = {}
    trial_censuses = {}
    for trial in registry["ordered_trials"]:
        trial_id = trial["trial_id"]
        variant = trial["portfolio_variant_id"]
        cost = trial["cost_bps_per_side"]
        if variant == "direct_stock_equal_weight":
            trial_observations[trial_id] = tuple(
                cloud._ReportTrialObservation(
                    trial_id=trial_id, portfolio_variant_id=variant,
                    cost_bps_per_side=cost, fold_id=item.fold_id,
                    session=item.session, session_position=item.session_position,
                    gross_portfolio_total_return=item.gross_portfolio_total_return,
                    benchmark_total_return=item.benchmark_total_return,
                    net_portfolio_total_return=item.net_portfolio_total_return,
                    net_excess_daily_total_return=(
                        item.net_excess_daily_total_return
                    ),
                    turnover=item.turnover,
                    sleeve_security_incidence_count=(
                        item.sleeve_security_incidence_count
                    ),
                    duplicate_sleeve_security_incidence_count=(
                        item.duplicate_sleeve_security_incidence_count
                    ),
                    terminal_liquidation=item.terminal_liquidation,
                )
                for item in host_observations
                if item.cost_bps_per_side == cost
            )
        else:
            trial_observations[trial_id] = ()
        for candidate_fold in host.FORMAL_FOLD_IDS:
            if variant == "direct_stock_equal_weight":
                source = host_censuses[(candidate_fold, cost)]
                trial_censuses[(trial_id, candidate_fold)] = (
                    cloud._ReportTrialFoldCensus(
                        trial_id=trial_id, portfolio_variant_id=variant,
                        cost_bps_per_side=cost, fold_id=candidate_fold,
                        session_count=source.session_count,
                        valid_return_session_count=(
                            source.valid_return_session_count
                        ),
                        refused_return_session_count=(
                            source.refused_return_session_count
                        ),
                        invested_session_count=source.invested_session_count,
                        cash_sleeve_count=source.cash_sleeve_count,
                        selected_sleeve_count=source.selected_sleeve_count,
                        terminal_liquidation_turnover=(
                            source.terminal_liquidation_turnover
                        ),
                        refusal_counts=source.refusal_counts,
                        refusal_counts_by_session=(
                            source.refusal_counts_by_session
                        ),
                    )
                )
            else:
                count = 50 if candidate_fold == fold else 0
                trial_censuses[(trial_id, candidate_fold)] = (
                    cloud._ReportTrialFoldCensus(
                        trial_id=trial_id, portfolio_variant_id=variant,
                        cost_bps_per_side=cost, fold_id=candidate_fold,
                        session_count=count, valid_return_session_count=0,
                        refused_return_session_count=count,
                        invested_session_count=0, cash_sleeve_count=0,
                        selected_sleeve_count=0,
                        terminal_liquidation_turnover=Decimal(0),
                        refusal_counts=(
                            (("missing_variant_axis", count),) if count else ()
                        ),
                        refusal_counts_by_session=tuple(
                            (
                                date(2020, 1, 1) + timedelta(days=index),
                                (("missing_variant_axis", 1),),
                            )
                            for index in range(count)
                        ),
                    )
                )
    rows = cloud._strategy_trial_reports(
        view=host.SOURCE_VIEW_IDS[0],
        registry=registry, trial_observations=trial_observations,
        trial_censuses=trial_censuses,
    )
    statistic_fields = (
        "T", "daily_sharpe", "annualized_sharpe", "skewness", "kurtosis",
        "trial_sharpe_variance", "expected_maximum_sharpe",
        "deflated_sharpe_z", "deflated_sharpe_probability",
    )
    assert len(rows) == 6
    assert all(row["status"] == "UNAVAILABLE" for row in rows)
    assert all(
        all(row[name] is None for name in statistic_fields) for row in rows
    )


def test_required_event_percentile_and_signal_decay_families_are_computed():
    view = host.SOURCE_VIEW_IDS[0]
    fold = host.FORMAL_FOLD_IDS[0]
    directional = (
        cloud._DirectionalEventReportObservation(
            source_view_id=view, fold_id=fold,
            decision_session=date(2020, 1, 3), session_position=0,
            event_id="event-1", security_id="security-1",
            common_event_component_id="component-1",
            rating_action="upgrades",
            earnings_anchor_signed_session_distance=0,
            horizon_sessions=1,
            gross_security_total_return=Decimal("0.03"),
            benchmark_total_return=Decimal("0.01"),
            gross_excess_total_return=Decimal("0.02"), refusal_reason=None,
        ),
    )
    event_rows = cloud._event_return_family_rows(
        observations=directional, source_view_id=view,
        report_contract=_report_contract(),
    )
    event_cell = next(
        row for row in event_rows
        if row["slice_id"] == host.FORMAL_SLICE_ID
        and row["fold_id"] == fold and row["rating_action"] == "upgrades"
        and row["horizon_sessions"] == 1 and row["cohort_id"] == "all"
    )
    assert event_cell["status"] == "AVAILABLE"
    assert event_cell["connected_component_count"] == 1
    assert event_cell["mean_gross_excess_total_return"] == Decimal("0.02")

    event_time = cloud._event_time_family_rows(
        observations=directional, source_view_id=view,
        report_contract=_report_contract(),
    )
    time_zero = next(
        row for row in event_time
        if row["slice_id"] == host.FORMAL_SLICE_ID
        and row["fold_id"] == fold and row["rating_action"] == "upgrades"
        and row["event_time_session"] == 0
    )
    assert time_zero["status"] == "AVAILABLE"
    assert time_zero["mean_cumulative_abnormal_return"] == 0

    decisions = tuple(
        cloud._DecisionReportObservation(
            source_view_id=view, fold_id=fold,
            decision_session=date(2020, 1, 3) + timedelta(days=index),
            session_position=index, security_id=f"security-{security}",
            common_event_component_id=f"component-{index}-{security}",
            rating_actions=("upgrades",),
            earnings_anchor_signed_session_distance=0,
            horizon_sessions=1,
            firm_specific_score=Decimal(security),
            global_score=Decimal(security),
            gross_excess_total_return=Decimal(security) / Decimal("100"),
            refusal_reason=None,
        )
        for index in range(50) for security in (1, 2)
    )
    percentile = cloud._percentile_family_rows(
        observations=decisions, source_view_id=view,
        report_contract=_report_contract(),
    )
    first_decile = next(
        row for row in percentile
        if row["slice_id"] == host.FORMAL_SLICE_ID
        and row["fold_id"] == fold and row["horizon_sessions"] == 1
        and row["score_arm"] == "firm_specific"
        and row["percentile_decile"] == 1
    )
    assert first_decile["status"] == "AVAILABLE"
    assert first_decile["row_count"] == 50

    decay = cloud._signal_decay_family_rows(
        observations=decisions, source_view_id=view,
        report_contract=_report_contract(),
    )
    h1 = next(
        row for row in decay
        if row["slice_id"] == host.FORMAL_SLICE_ID
        and row["fold_id"] == fold and row["rating_action"] == "upgrades"
        and row["score_arm"] == "firm_specific"
        and row["horizon_sessions"] == 1
    )
    assert h1["status"] == "AVAILABLE"
    assert h1["valid_date_count"] == 50
    assert h1["mean_ic"] == 1
    assert h1["ratio_to_h1_effect"] == 1


def test_six_genuine_strategy_trials_drive_turnover_and_dsr():
    contract = _report_contract()
    trials = contract["strategy_trial_registry"]["ordered_trials"]
    fold = host.FORMAL_FOLD_IDS[0]
    trial_observations = {}
    trial_censuses = {}
    for ordinal, trial in enumerate(trials):
        trial_id = trial["trial_id"]
        observations = tuple(
            cloud._ReportTrialObservation(
                trial_id=trial_id,
                portfolio_variant_id=trial["portfolio_variant_id"],
                cost_bps_per_side=trial["cost_bps_per_side"],
                fold_id=fold,
                session=date(2020, 1, 1) + timedelta(days=index),
                session_position=index,
                gross_portfolio_total_return=(
                    Decimal((index % 7) - 3) / Decimal("1000")
                    + Decimal(ordinal + 1) / Decimal("10000")
                ),
                benchmark_total_return=Decimal(0),
                net_portfolio_total_return=(
                    Decimal((index % 7) - 3) / Decimal("1000")
                    + Decimal(ordinal + 1) / Decimal("10000")
                ),
                net_excess_daily_total_return=(
                    Decimal((index % 7) - 3) / Decimal("1000")
                    + Decimal(ordinal + 1) / Decimal("10000")
                ),
                turnover=Decimal(0),
                sleeve_security_incidence_count=5,
                duplicate_sleeve_security_incidence_count=0,
                terminal_liquidation=False,
            )
            for index in range(50)
        )
        trial_observations[trial_id] = observations
        for candidate_fold in host.FORMAL_FOLD_IDS:
            count = 50 if candidate_fold == fold else 0
            trial_censuses[(trial_id, candidate_fold)] = (
                cloud._ReportTrialFoldCensus(
                    trial_id=trial_id,
                    portfolio_variant_id=trial["portfolio_variant_id"],
                    cost_bps_per_side=trial["cost_bps_per_side"],
                    fold_id=candidate_fold, session_count=count,
                    valid_return_session_count=count,
                    refused_return_session_count=0,
                    invested_session_count=count, cash_sleeve_count=0,
                    selected_sleeve_count=count,
                    terminal_liquidation_turnover=Decimal(0),
                    refusal_counts=(), refusal_counts_by_session=(),
                )
            )
    turnover = cloud._turnover_family_rows(
        source_view_id=host.SOURCE_VIEW_IDS[0], report_contract=contract,
        trial_observations=trial_observations,
        trial_censuses=trial_censuses,
    )
    variant_cells = tuple(
        row for row in turnover
        if row["slice_id"] == host.FORMAL_SLICE_ID
        and row["trial_id"] == "direct_stock_inverse_volatility_cost10"
    )
    assert sum(row["session_count"] for row in variant_cells) == 50
    assert any(row["status"] == "AVAILABLE" for row in variant_cells)

    dsr = cloud._strategy_trial_reports(
        view=host.SOURCE_VIEW_IDS[0], registry=trials and contract[
            "strategy_trial_registry"
        ], trial_observations=trial_observations,
        trial_censuses=trial_censuses,
    )
    assert len(dsr) == 6
    assert all(row["status"] == "AVAILABLE" for row in dsr)
    assert len({row["daily_sharpe"] for row in dsr}) == 6
