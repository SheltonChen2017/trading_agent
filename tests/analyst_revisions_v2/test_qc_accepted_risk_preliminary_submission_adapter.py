import ast
import dataclasses
import hashlib
import json
import shutil
import types
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_package as package_builder,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_qc_projection as projection_builder,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_qc_runtime as runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_regime_rating_evaluator as regime_evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_stock_portfolio_evaluator as stock_portfolio_evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_submission_adapter as adapter,
)
from research.analyst_revisions_v2_qc import formal_qc_transport as transport_module
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
)


_EXPECTED_LOOK_ACCOUNTING = {
    "schema": "arv2-qc-research-look-accounting-v1",
    "classification": "development_evaluation",
    "evaluation_id": "arv2-eval-stock-historical-qc-001",
    "shared_look_ledger_entry_id": "R-055",
    "accounting_stage": "reservation",
    "run_level_looks_before": 55,
    "run_level_looks_after": 55,
    "planned_run_level_looks_after_launch": 56,
    "arv2_development_evaluations_before": 2,
    "arv2_development_evaluations_after": 2,
    "planned_arv2_development_evaluations_after_launch": 3,
    "planned_maximum_preliminary_ic_cell_count": 32,
    "emitted_preliminary_ic_cell_count": 0,
    "lifetime_alpha_cell_floor_before": 484,
    "lifetime_alpha_cell_floor_after": 484,
    "aggregate_result_authenticated": False,
    "infrastructure_looks_before": 23,
    "infrastructure_looks_after": 23,
    "authenticated_infrastructure_look_count": 23,
    "infrastructure_look_ledger_id": (
        "arv2-infrastructure-look-ledger-11987a12b72d06ea612b442e"
    ),
    "infrastructure_look_ledger_hash": (
        "11987a12b72d06ea612b442e342ce0b1d2f28c503f0a3b1ca2cf721d8aaa7810"
    ),
    "infrastructure_look_ledger_artifact_sha256": (
        "b1018c54128b9cea5ff0c960e0c6adeab803b085b9dde359f323246d0f82e802"
    ),
    "permanent_looks_before": 0,
    "permanent_looks_after": 0,
    "confirmatory_looks_before": 0,
    "confirmatory_looks_after": 0,
    "confirmatory_look_spent": False,
    "execution_permit_alone_consumes_look": False,
    "pre_create_control_marks_launch_ambiguity_and_consumes_look": True,
    "backtest_create_attempt_consumes_look_on_success_failure_or_ambiguity": True,
    "technical_corrected_rerun_requires_new_ledger_entry": True,
    "retry_may_overwrite_shared_ledger_entry": False,
}


def _look_accounting_at(stage):
    result = dict(_EXPECTED_LOOK_ACCOUNTING)
    result["accounting_stage"] = stage
    if stage in {"launch", "result"}:
        result["run_level_looks_after"] = 56
        result["arv2_development_evaluations_after"] = 3
    if stage == "result":
        result["emitted_preliminary_ic_cell_count"] = 32
        result["lifetime_alpha_cell_floor_after"] = 516
        result["aggregate_result_authenticated"] = True
    return result


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _replace_closure(function, **replacements):
    cells = dict(
        zip(function.__code__.co_freevars, function.__closure__ or (), strict=True)
    )
    unknown = set(replacements) - set(cells)
    assert not unknown, unknown

    def make_cell(value):
        def close():
            return value

        return close.__closure__[0]

    closure = tuple(
        make_cell(replacements.get(name, cells[name].cell_contents))
        for name in function.__code__.co_freevars
    )
    return types.FunctionType(
        function.__code__,
        function.__globals__,
        function.__name__,
        function.__defaults__,
        closure,
    )


def _offline_signature():
    value = object.__new__(OwnerSignatureAuthority)
    object.__setattr__(value, "authority_sha256", "a" * 64)
    return value


def _fake_signature_verifier(value, _payload):
    assert value is not None
    return value


def _offline_minter(*, transport, scope, binding_record, call_budget):
    return transport_module._mint_offline_test_capability(
        transport,
        scope=scope,
        binding_record=binding_record,
        call_budget=call_budget,
    )


def _offline_action(function, *, result=False):
    replacements = {
        "action_guard": lambda _phase: None,
        "minter": _offline_minter,
        "transport_verifier": lambda value: value,
    }
    replacements[
        "result_signature_verifier" if result else "execution_signature_verifier"
    ] = _fake_signature_verifier
    return _replace_closure(function, **replacements)


def _build_plan(monkeypatch, tmp_path, evaluation_profile_id=None):
    root = (tmp_path / (evaluation_profile_id or "legacy-r055")).resolve()
    root.mkdir()
    root.chmod(0o700)
    control = root / "control"
    control.mkdir(mode=0o700)
    monkeypatch.setattr(
        evaluator,
        "load_preliminary_rating_input",
        lambda *_items: SimpleNamespace(authenticated=True),
    )
    monkeypatch.setattr(
        adapter.formal,
        "_require_concrete_transport",
        lambda value: value,
    )
    package = package_builder._materialize(
        output_root=root / "package",
        evaluator_manifest={
            "manifest_id": "manifest-one",
            "manifest_sha256": "c" * 64,
            "contribution_row_count": 1,
            "source_lineage_sha256s": {
                name: "f" * 64 for name in evaluator._SOURCE_LINEAGE_FIELDS
            },
        },
        session_records=({"session": "row"},),
        membership_records=({"membership": "row"},),
        contribution_records=({"contribution": "row"},),
        runtime_binding_records=({"binding": "row"},),
        source_disposition_sha256="d" * 64,
        contribution_census={"accepted": 1},
    )
    projection = projection_builder.build_accepted_risk_preliminary_qc_projection(
        package,
        evaluation_profile_id=evaluation_profile_id,
    )
    return adapter.build_accepted_risk_preliminary_submission_plan(
        package=package,
        projection=projection,
        organization_id="preliminary-test-organization",
        project_name="1 ARV2 ACCEPTED RISK PRELIMINARY TEST",
        backtest_name="ARV2 ACCEPTED RISK PRELIMINARY TEST",
        control_directory=control,
        worktree_root=Path(adapter.__file__).resolve().parents[2],
    )


@pytest.fixture
def plan(monkeypatch, tmp_path):
    return _build_plan(monkeypatch, tmp_path)


@pytest.fixture(params=regime_evaluator.REGIME_PROFILE_IDS)
def regime_plan(request, monkeypatch, tmp_path):
    return _build_plan(monkeypatch, tmp_path, request.param)


@pytest.fixture
def stock_portfolio_plan(monkeypatch, tmp_path):
    return _build_plan(
        monkeypatch,
        tmp_path,
        stock_portfolio_evaluator.PROFILE_ID,
    )


def _aggregate_statistics(plan):
    cells = []
    statistics = {}
    for window in evaluator.WINDOWS:
        for view in evaluator.SOURCE_VIEW_IDS:
            for arm in evaluator.SCORE_ARMS:
                for horizon in evaluator.HORIZONS:
                    row = {
                        "schema": evaluator.CELL_SCHEMA,
                        "source_view_id": view,
                        "score_arm": arm,
                        "horizon_sessions": horizon,
                        "window_id": window["window_id"],
                        "status": "INCONCLUSIVE_UNDERFILLED",
                        "eligible_score_row_count": 0,
                        "accepted_outcome_pair_count": 0,
                        "missing_outcome_pair_count": 0,
                        "sector_refused_row_count": 0,
                        "valid_ic_date_count": 0,
                        "invalid_ic_date_count": 0,
                        "mean_daily_spearman_ic": None,
                        "median_daily_spearman_ic": None,
                        "positive_ic_date_share": None,
                        "mean_of_daily_cross_section_mean_excess_returns": None,
                        "median_of_daily_cross_section_mean_excess_returns": None,
                        "outcome_definition": evaluator.HISTORY_OBSERVATION,
                        "formal_accept_reject_disposition": None,
                    }
                    name = evaluator._cell_summary_statistic_name(
                        view, arm, horizon, window["window_id"]
                    )
                    statistics[name] = _canonical(row).decode("ascii")
                    cells.append(row)
    summary = {
        "schema": evaluator.SUMMARY_SCHEMA,
        "contract_id": evaluator.CONTRACT_ID,
        "manifest_id": plan.evaluator_manifest_id,
        "manifest_sha256": plan.evaluator_manifest_sha256,
        "status": "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_ONLY",
        "source_lineage_sha256s": {
            name: "f" * 64 for name in evaluator._SOURCE_LINEAGE_FIELDS
        },
        "windows": [dict(item) for item in evaluator.WINDOWS],
        "source_view_ids": list(evaluator.SOURCE_VIEW_IDS),
        "score_arms": list(evaluator.SCORE_ARMS),
        "horizons": list(evaluator.HORIZONS),
        "outcome_definition": evaluator.HISTORY_OBSERVATION,
        "history_normalization_mode": "TOTAL_RETURN",
        "history_value_field": "open",
        "decay_state_method": (
            "sparse_positive_common_scale_mathematically_equivalent_"
            "not_byte_identical_to_formal_per_event_replay"
        ),
        "benchmark_role": "matching_SPY_open_to_open_total_return",
        "q_data_policy_id": evaluator.Q_DATA_POLICY_ID,
        "input_security_count": 1,
        "input_contribution_count": 1,
        "completed_callback_count": 1,
        "accepted_risk_disclosures": dict(evaluator.ACCEPTED_RISK_DISCLOSURES),
        "omitted_formal_components": list(evaluator.OMITTED_FORMAL_COMPONENTS),
        "raw_provider_rows_in_summary": False,
        "raw_security_outcome_rows_in_summary": False,
        "raw_price_rows_in_summary": False,
        "formal_result": False,
        "alpha_claim_authorized": False,
        "cells": cells,
    }
    digest = hashlib.sha256(_canonical(summary)).hexdigest()
    metadata = {
        **{key: value for key, value in summary.items() if key != "cells"},
        "summary_id": "arv2-preliminary-rating-summary-" + digest[:24],
        "summary_sha256": digest,
    }
    statistics["ARV2_PRELIMINARY_META"] = _canonical(metadata).decode("ascii")
    runtime = {
        "schema": "arv2-accepted-risk-preliminary-qc-runtime-meta-v1",
        "status": "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_ONLY_COMPLETED",
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "symbol_resolution_id": "resolution-one",
        "symbol_resolution_sha256": "e" * 64,
        "resolved_security_count": 1,
        "named_security_refusal_count": 0,
        "training_slice_count": 1,
        "result_transport": "aggregate_only_custom_summary_statistics",
        "host_object_store_export_required": False,
        "preliminary": True,
        "point_in_time": False,
        "formal": False,
        "control_residualized": False,
        "economic_portfolio": False,
        "etf_or_leverage": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    statistics["ARV2_RUNTIME_META"] = _canonical(runtime).decode("ascii")
    assert tuple(sorted(statistics)) == plan.expected_custom_statistic_names
    return statistics


def _regime_aggregate_statistics(plan):
    profile_id = plan.projection.evaluation_profile_id
    profile, meta_name, named_axes = adapter._regime_axis_inventory(profile_id)
    cells = []
    statistics = {}
    disclosures = dict(regime_evaluator.OUTCOME_AVAILABILITY_DISCLOSURES)
    for name, (view, arm, horizon) in named_axes:
        row = {
            "schema": regime_evaluator.REGIME_CELL_SCHEMA,
            "source_view_id": view,
            "score_arm": arm,
            "horizon_sessions": horizon,
            "profile_id": profile_id,
            "window_start_session": profile["start_session"],
            "window_end_session": profile["end_session"],
            "status": "INCONCLUSIVE_UNDERFILLED",
            "eligible_score_row_count": 0,
            "accepted_outcome_pair_count": 0,
            "missing_outcome_pair_count": 0,
            "benchmark_endpoint_unavailable_pair_count": 0,
            "named_figi_resolution_refusal_pair_count": 0,
            "security_entry_unavailable_pair_count": 0,
            "membership_ended_by_exit_with_exit_unavailable_pair_count": 0,
            "within_membership_exit_unavailable_pair_count": 0,
            "missing_pair_counter_sum_matches_total": True,
            "sector_refused_row_count": 0,
            "valid_ic_date_count": 0,
            "invalid_ic_date_count": profile["expected_session_count"],
            "mean_daily_spearman_ic": None,
            "median_daily_spearman_ic": None,
            "positive_ic_date_share": None,
            "mean_of_daily_cross_section_mean_excess_returns": None,
            "median_of_daily_cross_section_mean_excess_returns": None,
            "outcome_definition": evaluator.HISTORY_OBSERVATION,
            "endpoint_price_conditioning": disclosures[
                "endpoint_price_conditioning"
            ],
            "membership_ended_by_exit_interpretation": disclosures[
                "membership_ended_by_exit_interpretation"
            ],
            "formal_accept_reject_disposition": None,
        }
        statistics[name] = _canonical(row).decode("ascii")
        cells.append(row)
    summary = {
        "schema": regime_evaluator.REGIME_SUMMARY_SCHEMA,
        "contract_id": regime_evaluator.REGIME_CONTRACT_ID,
        "input_contract_id": evaluator.CONTRACT_ID,
        "manifest_id": plan.evaluator_manifest_id,
        "manifest_sha256": plan.evaluator_manifest_sha256,
        "status": "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_REGIME_ONLY",
        "source_lineage_sha256s": {
            name: "f" * 64 for name in evaluator._SOURCE_LINEAGE_FIELDS
        },
        "profile": profile,
        "source_view_ids": list(evaluator.SOURCE_VIEW_IDS),
        "score_arms": list(evaluator.SCORE_ARMS),
        "horizons": list(evaluator.HORIZONS),
        "outcome_definition": evaluator.HISTORY_OBSERVATION,
        "history_normalization_mode": "TOTAL_RETURN",
        "history_value_field": "open",
        "decay_state_method": (
            "R055_sparse_positive_common_scale_mathematically_equivalent_"
            "not_byte_identical_to_formal_per_event_replay"
        ),
        "benchmark_role": "matching_SPY_open_to_open_total_return",
        "q_data_policy_id": evaluator.Q_DATA_POLICY_ID,
        "input_security_count": 1,
        "input_contribution_count": 1,
        "named_figi_resolution_refusal_count": 0,
        "completed_callback_count": 1,
        "r055_signal_rule_changed": False,
        "outcome_availability_disclosures": disclosures,
        "accepted_risk_disclosures": dict(evaluator.ACCEPTED_RISK_DISCLOSURES),
        "raw_provider_rows_in_summary": False,
        "raw_security_outcome_rows_in_summary": False,
        "raw_price_rows_in_summary": False,
        "terminal_payoff_applied": False,
        "economic_portfolio_evaluation": False,
        "formal_result": False,
        "alpha_claim_authorized": False,
        "cells": cells,
    }
    digest = hashlib.sha256(_canonical(summary)).hexdigest()
    metadata = {
        **{key: value for key, value in summary.items() if key != "cells"},
        "summary_id": "arv2-regime-rating-summary-" + digest[:24],
        "summary_sha256": digest,
    }
    statistics[meta_name] = _canonical(metadata).decode("ascii")
    runtime_meta = {
        "schema": "arv2-accepted-risk-regime-qc-runtime-meta-v1",
        "status": "PRELIMINARY_ACCEPTED_RISK_STOCK_IC_ONLY_COMPLETED",
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "symbol_resolution_id": "resolution-one",
        "symbol_resolution_sha256": "e" * 64,
        "resolved_security_count": 1,
        "named_security_refusal_count": 0,
        "result_transport": "aggregate_only_custom_summary_statistics",
        "host_object_store_export_required": False,
        "preliminary": True,
        "point_in_time": False,
        "formal": False,
        "control_residualized": False,
        "economic_portfolio": False,
        "etf_or_leverage": False,
        "deployment": False,
        "orders": False,
        "trading": False,
        "evaluation_profile_id": profile_id,
        "evaluation_profile_sha256": profile["profile_sha256"],
        "runtime_slice_count": 1,
    }
    statistics["ARV2_RUNTIME_META"] = _canonical(runtime_meta).decode("ascii")
    assert tuple(sorted(statistics)) == plan.expected_custom_statistic_names
    assert all(len(value) <= 4_096 for value in statistics.values())
    return statistics


def _stock_portfolio_aggregate_statistics(
    plan, *, proxy=False, zero_recovery=False
):
    profile = stock_portfolio_evaluator.require_stock_portfolio_profile(
        stock_portfolio_evaluator.PROFILE_ID
    )
    status = (
        "PRELIMINARY_DESCRIPTIVE_LOWER_BOUND_WITH_ZERO_RECOVERY"
        if zero_recovery
        else (
            "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_STALE_MARK_PROXY"
            if proxy
            else (
                "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_EXPOSURE_UNDERFILL"
            )
        )
    )
    conditioning = (
        "conditioned_on_zero_recovery_lower_bound_and_possible_stale_mark_path"
        if zero_recovery
        else (
            "conditioned_on_stale_mark_path" if proxy else "no_price_proxy"
        )
    )
    signal_returns = {0: "0.10", 5: "0.09", 10: "0.08", 20: "0.06"}
    matched_returns = {0: "0.05", 5: "0.04", 10: "0.03", 20: "0.01"}
    signal_annual = {
        0: "0.02",
        5: "0.01496",
        10: "0.00992",
        20: "-0.00016",
    }
    matched_annual = {
        0: "0.009",
        5: "0.00522",
        10: "0.00144",
        20: "-0.00612",
    }
    cells = []
    statistics = {}
    for cost in stock_portfolio_evaluator.COST_BPS_SCENARIOS:
        signal_return = signal_returns[cost]
        matched_return = matched_returns[cost]
        cell = {
            "schema": stock_portfolio_evaluator.PORTFOLIO_CELL_SCHEMA,
            "profile_id": stock_portfolio_evaluator.PROFILE_ID,
            "cost_bps_per_side": cost,
            "primary_cost_scenario": cost == 10,
            "status": status,
            "return_metric_conditioning": conditioning,
            "risk_metrics_are_price_proxy_conditioned": bool(
                proxy or zero_recovery
            ),
            "exposure_underfill_present": True,
            "return_session_count": 1254,
            "invested_return_session_count": 1000,
            "cumulative_return": signal_return,
            "matched_eligible_stock_cumulative_return": matched_return,
            "spy_cumulative_return": "0.20",
            "cumulative_return_minus_matched": str(
                Decimal(signal_return) - Decimal(matched_return)
            ),
            "cumulative_return_minus_spy": str(
                Decimal(signal_return) - Decimal("0.20")
            ),
            "annualized_arithmetic_return": signal_annual[cost],
            "annualized_volatility": "0.10",
            "zero_rate_sharpe": str(Decimal(signal_annual[cost]) / Decimal("0.10")),
            "zero_rate_sortino": "-0.30" if cost == 20 else "0.30",
            "maximum_drawdown": "-0.08",
            "average_daily_two_sided_turnover": "0.04",
            "average_cash_weight": "0.02",
            "matched_annualized_arithmetic_return": matched_annual[cost],
            "matched_annualized_volatility": "0.09",
            "matched_zero_rate_sharpe": str(
                Decimal(matched_annual[cost]) / Decimal("0.09")
            ),
            "matched_zero_rate_sortino": "-0.16" if cost == 20 else "0.16",
            "matched_maximum_drawdown": "-0.07",
            "matched_average_daily_two_sided_turnover": "0.03",
            "matched_average_cash_weight": "0",
            "leverage": False,
            "orders_submitted": 0,
            "formal_accept_reject_disposition": None,
        }
        statistics[
            "ARV2_STOCK_PORTFOLIO_COST_" + str(cost)
        ] = _canonical(cell).decode("ascii")
        cells.append(cell)
    meta = {
        "schema": stock_portfolio_evaluator.SUMMARY_SCHEMA,
        "contract_id": stock_portfolio_evaluator.CONTRACT_ID,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "input_manifest_id": plan.evaluator_manifest_id,
        "input_manifest_sha256": plan.evaluator_manifest_sha256,
        "status": "PRELIMINARY_ACCEPTED_RISK_STOCK_PORTFOLIO",
        "decision_session_count": 261,
        "portfolio_return_session_count": 1254,
        "invested_return_session_count": 1000,
        "signal_selected_decision_count": 261,
        "selected_execution_count": 261 - int(proxy),
        "rebalance_execution_count": 261 - int(proxy),
        "full_target_execution_count": 0,
        "underfilled_target_execution_count": 261 - int(proxy),
        "matched_rebalance_execution_count": 261 - int(proxy),
        "matched_target_met_execution_count": 261 - int(proxy),
        "matched_underfilled_target_execution_count": 0,
        "sector_refused_decision_count": 1,
        "mean_eligible_score_count": "1",
        "mean_selected_name_count": "1",
        "mean_executed_target_gross_exposure": "0.0196",
        "matched_mean_executed_target_gross_exposure": "0.0196",
        "average_holding_count": "1",
        "entry_price_refusal_count": 0,
        "stale_mark_session_count": int(proxy),
        "deferred_rebalance_count": int(proxy),
        "membership_end_liquidation_count": int(zero_recovery),
        "membership_end_zero_recovery_count": int(zero_recovery),
        "membership_end_entry_refusal_count": 0,
        "matched_entry_price_refusal_count": 0,
        "matched_stale_mark_session_count": 0,
        "matched_deferred_rebalance_count": int(proxy),
        "matched_membership_end_liquidation_count": 0,
        "matched_membership_end_zero_recovery_count": 0,
        "matched_membership_end_entry_refusal_count": 0,
        "named_figi_resolution_refusal_count": 0,
        "history_normalization_mode": "TOTAL_RETURN",
        "history_value_field": "open",
        "r055_signal_rule_changed": False,
        "liquidity_filter_applied": False,
        "terminal_payoff_applied": False,
        "membership_end_liquidation_is_terminal_payoff": False,
        "membership_end_missing_price_policy": (
            "zero_recovery_conservative_lower_bound"
        ),
        "matched_exposure_targeted_to_signal_executed_gross": True,
        "current_vintage_non_pristine_pit_input": True,
        "raw_provider_rows_in_summary": False,
        "raw_security_outcome_rows_in_summary": False,
        "raw_price_rows_in_summary": False,
        "formal_result": False,
        "alpha_claim_authorized": False,
        "economic_portfolio_evaluation": True,
        "leverage": False,
        "deployment": False,
        "orders": False,
        "trading": False,
        "portfolio_cells": cells,
    }
    digest_record = {
        key: value
        for key, value in meta.items()
        if key not in {"profile_id", "profile_sha256"}
    }
    digest_record["profile"] = profile
    digest = hashlib.sha256(_canonical(digest_record)).hexdigest()
    metadata = {
        **{key: value for key, value in meta.items() if key != "portfolio_cells"},
        "summary_id": "arv2-stock-portfolio-summary-" + digest[:24],
        "summary_sha256": digest,
    }
    statistics["ARV2_STOCK_PORTFOLIO_META"] = _canonical(metadata).decode(
        "ascii"
    )
    runtime_meta = {
        "schema": "arv2-accepted-risk-stock-portfolio-qc-runtime-meta-v1",
        "status": "PRELIMINARY_ACCEPTED_RISK_STOCK_PORTFOLIO_COMPLETED",
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "symbol_resolution_id": "resolution-one",
        "symbol_resolution_sha256": "e" * 64,
        "resolved_security_count": 1,
        "named_security_refusal_count": 0,
        "result_transport": "aggregate_only_custom_summary_statistics",
        "host_object_store_export_required": False,
        "preliminary": True,
        "point_in_time": False,
        "formal": False,
        "control_residualized": False,
        "economic_portfolio": True,
        "etf_or_leverage": False,
        "deployment": False,
        "orders": False,
        "trading": False,
        "evaluation_profile_id": stock_portfolio_evaluator.PROFILE_ID,
        "evaluation_profile_sha256": profile["profile_sha256"],
        "runtime_slice_count": 1,
    }
    statistics["ARV2_RUNTIME_META"] = _canonical(runtime_meta).decode("ascii")
    assert tuple(sorted(statistics)) == plan.expected_custom_statistic_names
    assert all(len(value) <= 4096 for value in statistics.values())
    return statistics


def _rehash_preliminary_summary(statistics):
    metadata = json.loads(statistics["ARV2_PRELIMINARY_META"])
    cells = []
    for window in evaluator.WINDOWS:
        for view in evaluator.SOURCE_VIEW_IDS:
            for arm in evaluator.SCORE_ARMS:
                for horizon in evaluator.HORIZONS:
                    name = evaluator._cell_summary_statistic_name(
                        view, arm, horizon, window["window_id"]
                    )
                    cells.append(json.loads(statistics[name]))
    summary = {
        key: value
        for key, value in metadata.items()
        if key not in {"summary_id", "summary_sha256"}
    }
    summary["cells"] = cells
    digest = hashlib.sha256(_canonical(summary)).hexdigest()
    metadata["summary_id"] = "arv2-preliminary-rating-summary-" + digest[:24]
    metadata["summary_sha256"] = digest
    statistics["ARV2_PRELIMINARY_META"] = _canonical(metadata).decode("ascii")


def _rehash_regime_summary(plan, statistics):
    _profile, meta_name, named_axes = adapter._regime_axis_inventory(
        plan.projection.evaluation_profile_id
    )
    metadata = json.loads(statistics[meta_name])
    summary = {
        key: value
        for key, value in metadata.items()
        if key not in {"summary_id", "summary_sha256"}
    }
    summary["cells"] = [json.loads(statistics[name]) for name, _axis in named_axes]
    digest = hashlib.sha256(_canonical(summary)).hexdigest()
    metadata["summary_id"] = "arv2-regime-rating-summary-" + digest[:24]
    metadata["summary_sha256"] = digest
    statistics[meta_name] = _canonical(metadata).decode("ascii")


def _rehash_stock_portfolio_summary(statistics):
    metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
    summary = {
        key: value
        for key, value in metadata.items()
        if key
        not in {
            "profile_id",
            "profile_sha256",
            "summary_id",
            "summary_sha256",
        }
    }
    summary["profile"] = stock_portfolio_evaluator.require_stock_portfolio_profile(
        stock_portfolio_evaluator.PROFILE_ID
    )
    summary["portfolio_cells"] = [
        json.loads(statistics["ARV2_STOCK_PORTFOLIO_COST_" + str(cost)])
        for cost in stock_portfolio_evaluator.COST_BPS_SCENARIOS
    ]
    digest = hashlib.sha256(_canonical(summary)).hexdigest()
    metadata["summary_id"] = "arv2-stock-portfolio-summary-" + digest[:24]
    metadata["summary_sha256"] = digest
    statistics["ARV2_STOCK_PORTFOLIO_META"] = _canonical(metadata).decode(
        "ascii"
    )


def _mutate_first_cell(statistics, mutation):
    name = next(key for key in sorted(statistics) if key.startswith("ARV2_IC_"))
    cell = json.loads(statistics[name])
    mutation(cell)
    statistics[name] = _canonical(cell).decode("ascii")
    _rehash_preliminary_summary(statistics)


def _mutate_first_regime_cell(plan, statistics, mutation):
    _profile, _meta_name, named_axes = adapter._regime_axis_inventory(
        plan.projection.evaluation_profile_id
    )
    name = named_axes[0][0]
    cell = json.loads(statistics[name])
    mutation(cell)
    statistics[name] = _canonical(cell).decode("ascii")
    _rehash_regime_summary(plan, statistics)


def _validate_statistics(plan, statistics):
    adapter._validate_aggregate_records(
        {name: json.loads(value) for name, value in statistics.items()},
        plan,
    )


_REGIME_ACCOUNTING = {
    "arv2-stock-ic-2019-2023": ("R-057", 56, 57, 3, 4, 516, 532),
    "arv2-stock-ic-2023-2025": ("R-058", 57, 58, 4, 5, 532, 548),
    "arv2-stock-ic-2013-2019": ("R-059", 58, 59, 5, 6, 548, 564),
}


def test_regime_profile_allowlist_refuses_unknown_profile():
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="evaluation profile is not allowlisted",
    ):
        adapter._look_accounting(evaluation_profile_id="arv2-stock-ic-unregistered")


def test_stock_portfolio_profile_has_one_exact_r063_look_budget(stock_portfolio_plan):
    spec = adapter._run_spec(stock_portfolio_evaluator.PROFILE_ID)
    accounting = adapter._look_accounting(
        evaluation_profile_id=stock_portfolio_evaluator.PROFILE_ID
    )
    result_accounting = adapter._look_accounting(
        stage="result",
        evaluation_profile_id=stock_portfolio_evaluator.PROFILE_ID,
    )

    assert spec.ledger_entry_id == "R-063"
    assert spec.cell_count == 4
    assert accounting["run_level_looks_before"] == 62
    assert accounting["planned_run_level_looks_after_launch"] == 63
    assert accounting["arv2_development_evaluations_before"] == 9
    assert accounting["planned_arv2_development_evaluations_after_launch"] == 10
    assert accounting["lifetime_alpha_cell_floor_before"] == 571
    assert result_accounting["lifetime_alpha_cell_floor_after"] == 575
    assert len(stock_portfolio_plan.expected_custom_statistic_names) == 6


@pytest.mark.parametrize(
    ("proxy", "zero_recovery"),
    ((False, False), (True, False), (False, True)),
)
def test_stock_portfolio_aggregate_validator_accepts_only_disclosed_price_status(
    stock_portfolio_plan, proxy, zero_recovery
):
    statistics = _stock_portfolio_aggregate_statistics(
        stock_portfolio_plan,
        proxy=proxy,
        zero_recovery=zero_recovery,
    )

    _validate_statistics(stock_portfolio_plan, statistics)

    metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
    metadata["terminal_payoff_applied"] = True
    statistics["ARV2_STOCK_PORTFOLIO_META"] = _canonical(metadata).decode("ascii")
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="stock-portfolio aggregate metadata semantics changed",
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


def test_stock_portfolio_validator_refuses_cost_or_proxy_status_relabel(
    stock_portfolio_plan,
):
    statistics = _stock_portfolio_aggregate_statistics(
        stock_portfolio_plan, proxy=True
    )
    cell_name = "ARV2_STOCK_PORTFOLIO_COST_10"
    cell = json.loads(statistics[cell_name])
    cell["status"] = "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
    statistics[cell_name] = _canonical(cell).decode("ascii")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="stock-portfolio cell semantics changed",
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("portfolio_return_session_count", 1253),
        ("named_figi_resolution_refusal_count", 1),
        ("membership_end_zero_recovery_count", 1),
    ),
)
def test_stock_portfolio_validator_isolates_geometry_and_refusal_guards(
    stock_portfolio_plan, field, value
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
    metadata[field] = value
    statistics["ARV2_STOCK_PORTFOLIO_META"] = _canonical(metadata).decode(
        "ascii"
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="stock-portfolio aggregate metadata semantics changed",
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("return_metric_conditioning", "no_price_proxy"),
        ("risk_metrics_are_price_proxy_conditioned", False),
    ),
)
def test_stock_portfolio_validator_isolates_price_conditioning_guards(
    stock_portfolio_plan, field, value
):
    statistics = _stock_portfolio_aggregate_statistics(
        stock_portfolio_plan, zero_recovery=True
    )
    cell_name = "ARV2_STOCK_PORTFOLIO_COST_10"
    cell = json.loads(statistics[cell_name])
    cell[field] = value
    statistics[cell_name] = _canonical(cell).decode("ascii")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="stock-portfolio cell semantics changed",
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


def test_stock_portfolio_validator_refuses_rehashed_false_sharpe(
    stock_portfolio_plan,
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    cell_name = "ARV2_STOCK_PORTFOLIO_COST_10"
    cell = json.loads(statistics[cell_name])
    cell["zero_rate_sharpe"] = "999"
    statistics[cell_name] = _canonical(cell).decode("ascii")
    _rehash_stock_portfolio_summary(statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="stock-portfolio metric escaped bounds",
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


def test_stock_portfolio_validator_refuses_rehashed_wrong_sortino_sign(
    stock_portfolio_plan,
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    cell_name = "ARV2_STOCK_PORTFOLIO_COST_10"
    cell = json.loads(statistics[cell_name])
    cell["zero_rate_sortino"] = "-1"
    statistics[cell_name] = _canonical(cell).decode("ascii")
    _rehash_stock_portfolio_summary(statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="stock-portfolio metric escaped bounds",
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


def test_stock_portfolio_validator_refuses_negative_return_with_null_sortino(
    stock_portfolio_plan,
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    cell_name = "ARV2_STOCK_PORTFOLIO_COST_10"
    cell = json.loads(statistics[cell_name])
    cell["annualized_arithmetic_return"] = "-0.02"
    cell["zero_rate_sharpe"] = "-0.2"
    cell["zero_rate_sortino"] = None
    statistics[cell_name] = _canonical(cell).decode("ascii")
    _rehash_stock_portfolio_summary(statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="stock-portfolio metric escaped bounds",
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


def test_stock_portfolio_validator_accepts_matched_only_stale_deferral(
    stock_portfolio_plan,
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
    metadata["matched_rebalance_execution_count"] = 260
    metadata["matched_target_met_execution_count"] = 260
    metadata["matched_stale_mark_session_count"] = 1
    metadata["matched_deferred_rebalance_count"] = 1
    statistics["ARV2_STOCK_PORTFOLIO_META"] = _canonical(metadata).decode(
        "ascii"
    )
    for cost in stock_portfolio_evaluator.COST_BPS_SCENARIOS:
        name = "ARV2_STOCK_PORTFOLIO_COST_" + str(cost)
        cell = json.loads(statistics[name])
        cell["status"] = (
            "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_STALE_MARK_PROXY"
        )
        cell["return_metric_conditioning"] = "conditioned_on_stale_mark_path"
        cell["risk_metrics_are_price_proxy_conditioned"] = True
        statistics[name] = _canonical(cell).decode("ascii")
    _rehash_stock_portfolio_summary(statistics)

    _validate_statistics(stock_portfolio_plan, statistics)


@pytest.mark.parametrize(
    ("updates", "message"),
    (
        (
            {
                "selected_execution_count": 261,
                "rebalance_execution_count": 260,
                "underfilled_target_execution_count": 260,
                "deferred_rebalance_count": 1,
                "matched_rebalance_execution_count": 260,
                "matched_target_met_execution_count": 260,
                "matched_deferred_rebalance_count": 1,
            },
            "aggregate metadata semantics changed",
        ),
        (
            {
                "full_target_execution_count": 261,
                "underfilled_target_execution_count": 0,
                "mean_executed_target_gross_exposure": "0",
                "matched_mean_executed_target_gross_exposure": "0",
            },
            "target exposure changed",
        ),
        (
            {"matched_mean_executed_target_gross_exposure": "0.98"},
            "target exposure changed",
        ),
        (
            {"mean_executed_target_gross_exposure": "0.98"},
            "target exposure changed",
        ),
    ),
)
def test_stock_portfolio_validator_refuses_rehashed_impossible_execution_census(
    stock_portfolio_plan, updates, message
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
    metadata.update(updates)
    statistics["ARV2_STOCK_PORTFOLIO_META"] = _canonical(metadata).decode(
        "ascii"
    )
    _rehash_stock_portfolio_summary(statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match=message,
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


def test_stock_portfolio_validator_refuses_higher_cost_annual_return(
    stock_portfolio_plan,
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    cell_name = "ARV2_STOCK_PORTFOLIO_COST_20"
    cell = json.loads(statistics[cell_name])
    cell["annualized_arithmetic_return"] = "0.03"
    cell["zero_rate_sharpe"] = "0.3"
    cell["zero_rate_sortino"] = "0.3"
    statistics[cell_name] = _canonical(cell).decode("ascii")
    _rehash_stock_portfolio_summary(statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="stock-portfolio cost arithmetic changed",
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


def test_stock_portfolio_runtime_slice_ceiling_is_isolated(
    stock_portfolio_plan,
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    runtime_meta = json.loads(statistics["ARV2_RUNTIME_META"])
    runtime_meta["runtime_slice_count"] = runtime.MAX_TRAIN_SLICE_COUNT + 1
    statistics["ARV2_RUNTIME_META"] = _canonical(runtime_meta).decode("ascii")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="stock-portfolio runtime metadata changed",
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


def test_stock_contract_constant_mutation_refuses_before_network(
    stock_portfolio_plan, monkeypatch
):
    backend = _Backend(stock_portfolio_plan)
    monkeypatch.setattr(
        stock_portfolio_evaluator,
        "MINIMUM_INVESTED_RETURN_SESSIONS",
        0,
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=stock_portfolio_plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-16T20:00:00Z",
        )
    assert backend.events == []
    assert not any(stock_portfolio_plan.control_directory.iterdir())


def test_stock_contract_real_action_guard_accepts_clean_six_name_inventory(
    stock_portfolio_plan,
):
    cells = dict(
        zip(
            adapter.execute_accepted_risk_preliminary_submission_once.__code__.co_freevars,
            adapter.execute_accepted_risk_preliminary_submission_once.__closure__ or (),
            strict=True,
        )
    )

    cells["action_guard"].cell_contents("stock-clean-preflight")

    assert adapter._expected_result_names(stock_portfolio_evaluator.PROFILE_ID) == (
        stock_portfolio_plan.expected_custom_statistic_names
    )
    assert "ARV2_RUNTIME_META" in stock_portfolio_plan.expected_custom_statistic_names
    assert len(stock_portfolio_plan.expected_custom_statistic_names) == 6


def test_stock_contract_callable_reentry_refuses_before_side_effect(
    stock_portfolio_plan, monkeypatch
):
    backend = _Backend(stock_portfolio_plan)
    original = adapter._validate_stock_portfolio_aggregate_records
    called = False

    def hostile_names(_profile_id):
        nonlocal called
        called = True
        monkeypatch.setattr(
            adapter,
            "_validate_stock_portfolio_aggregate_records",
            lambda *_args, **_kwargs: None,
        )
        return adapter._PINNED_STOCK_PORTFOLIO_RESULT_NAMES

    monkeypatch.setattr(
        stock_portfolio_evaluator,
        "expected_custom_summary_statistic_names",
        hostile_names,
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=stock_portfolio_plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-16T20:00:00Z",
        )
    assert called is False
    assert adapter._validate_stock_portfolio_aggregate_records is original
    assert backend.events == []
    assert not any(stock_portfolio_plan.control_directory.iterdir())


def test_stock_projection_hostile_source_tuple_refuses_before_iteration(
    stock_portfolio_plan, monkeypatch
):
    backend = _Backend(stock_portfolio_plan)
    original_metric = adapter._cell_metric
    iterations = []

    class HostileTuple(tuple):
        def __iter__(self):
            iterations.append(True)
            monkeypatch.setattr(
                adapter,
                "_cell_metric",
                lambda *_args, **_kwargs: Decimal(0),
            )
            return super().__iter__()

    monkeypatch.setattr(
        projection_builder,
        "STOCK_PORTFOLIO_PROJECT_SOURCE_PATHS",
        HostileTuple(
            projection_builder.STOCK_PORTFOLIO_PROJECT_SOURCE_PATHS
        ),
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=stock_portfolio_plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-16T20:00:00Z",
        )
    assert iterations == []
    assert adapter._cell_metric is original_metric
    assert backend.events == []
    assert not any(stock_portfolio_plan.control_directory.iterdir())


def test_regime_expected_result_inventory_guard_is_isolated(monkeypatch):
    monkeypatch.setattr(
        adapter,
        "_PINNED_EXPECTED_RESULT_NAMES_FOR_PROFILE",
        lambda _profile_id: ("ARV2_RUNTIME_META",),
    )
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="expected result inventory changed",
    ):
        adapter._expected_result_names(regime_evaluator.REGIME_PROFILE_IDS[0])


def test_regime_exact_outcome_disclosure_contract_guard_is_isolated(monkeypatch):
    monkeypatch.setattr(
        regime_evaluator,
        "OUTCOME_AVAILABILITY_DISCLOSURES",
        {"endpoint_price_conditioning_direction": "positive"},
    )
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="outcome disclosure contract changed",
    ):
        adapter._outcome_availability_disclosures()


@pytest.mark.parametrize(
    "binding_name",
    (
        "_PINNED_EXPECTED_RESULT_NAMES_FOR_PROFILE",
        "_PINNED_REQUIRE_REGIME_PROFILE",
        "_run_spec",
        "_expected_result_names",
    ),
)
def test_new_profile_authority_binding_mutation_refuses_before_network(
    plan, monkeypatch, binding_name,
):
    backend = _Backend(plan)
    monkeypatch.setattr(adapter, binding_name, lambda *_items, **_kwargs: None)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-14T20:00:00Z",
        )
    assert backend.events == []
    assert not any(plan.control_directory.iterdir())


def test_regime_profile_names_hashes_and_look_accounting_are_exact(regime_plan):
    profile_id = regime_plan.projection.evaluation_profile_id
    profile = regime_evaluator.require_regime_profile(profile_id)
    expected = _REGIME_ACCOUNTING[profile_id]
    assert regime_plan.projection.evaluation_profile_sha256 == profile["profile_sha256"]
    assert regime_plan.evaluation_profile_id == profile_id
    assert regime_plan.evaluation_profile_sha256 == profile["profile_sha256"]
    assert regime_plan.expected_custom_statistic_names == (
        runtime.expected_custom_summary_statistic_names(profile_id)
    )
    assert len(regime_plan.expected_custom_statistic_names) == 18
    for stage in ("reservation", "launch", "result"):
        accounting = adapter._look_accounting(
            stage=stage,
            evaluation_profile_id=profile_id,
        )
        launched = stage in {"launch", "result"}
        authenticated = stage == "result"
        assert accounting["shared_look_ledger_entry_id"] == expected[0]
        assert accounting["run_level_looks_before"] == expected[1]
        assert accounting["run_level_looks_after"] == (
            expected[2] if launched else expected[1]
        )
        assert accounting["arv2_development_evaluations_before"] == expected[3]
        assert accounting["arv2_development_evaluations_after"] == (
            expected[4] if launched else expected[3]
        )
        assert accounting["planned_maximum_preliminary_ic_cell_count"] == 16
        assert accounting["emitted_preliminary_ic_cell_count"] == (
            16 if authenticated else 0
        )
        assert accounting["lifetime_alpha_cell_floor_before"] == expected[5]
        assert accounting["lifetime_alpha_cell_floor_after"] == (
            expected[6] if authenticated else expected[5]
        )
    persisted = json.loads(
        adapter.persist_accepted_risk_preliminary_submission_plan(
            regime_plan
        ).read_bytes()
    )
    assert persisted["schema"] == adapter.REGIME_PLAN_SCHEMA
    assert persisted["evaluation_profile_id"] == profile_id
    assert persisted["evaluation_profile_sha256"] == profile["profile_sha256"]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("evaluation_profile_id", "arv2-stock-ic-2019-2023-tampered"),
        ("evaluation_profile_sha256", "0" * 64),
    ),
)
def test_regime_plan_profile_binding_tamper_is_refused(regime_plan, field, value):
    original = getattr(regime_plan, field)
    object.__setattr__(regime_plan, field, value)
    try:
        with pytest.raises(
            adapter.AcceptedRiskPreliminarySubmissionError,
            match="submission plan changed",
        ):
            adapter.require_accepted_risk_preliminary_submission_plan(regime_plan)
    finally:
        object.__setattr__(regime_plan, field, original)


def test_regime_statistics_validate_with_exact_conditioning_disclosures(regime_plan):
    statistics = _regime_aggregate_statistics(regime_plan)
    _validate_statistics(regime_plan, statistics)
    records = {name: json.loads(value) for name, value in statistics.items()}
    cell = next(
        records[name]
        for name in regime_plan.expected_custom_statistic_names
        if "_H" in name
    )
    disclosures = dict(regime_evaluator.OUTCOME_AVAILABILITY_DISCLOSURES)
    assert disclosures["reported_ic_conditioned_on_endpoint_price_availability"] is True
    assert disclosures["endpoint_price_conditioning_direction"] == "unknown"
    assert disclosures["membership_ended_by_exit_is_confirmed_terminal"] is False
    assert disclosures["terminal_payoff_policy_applied"] is False
    assert cell["endpoint_price_conditioning"] == disclosures[
        "endpoint_price_conditioning"
    ]
    assert cell["membership_ended_by_exit_interpretation"] == disclosures[
        "membership_ended_by_exit_interpretation"
    ]


def test_regime_self_consistent_wrong_fixed_window_date_count_is_refused(regime_plan):
    statistics = _regime_aggregate_statistics(regime_plan)
    _profile, _meta_name, named_axes = adapter._regime_axis_inventory(
        regime_plan.projection.evaluation_profile_id
    )
    for name, _axis in named_axes:
        cell = json.loads(statistics[name])
        cell["invalid_ic_date_count"] = 1
        statistics[name] = _canonical(cell).decode("ascii")
    _rehash_regime_summary(regime_plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="aggregate cell geometry changed",
    ):
        _validate_statistics(regime_plan, statistics)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("evaluation_profile_id", "arv2-stock-ic-2019-2023-tampered"),
        ("evaluation_profile_sha256", "0" * 64),
    ),
)
def test_regime_runtime_profile_binding_mutant_is_refused(
    regime_plan, field, value
):
    statistics = _regime_aggregate_statistics(regime_plan)
    metadata = json.loads(statistics["ARV2_RUNTIME_META"])
    metadata[field] = value
    statistics["ARV2_RUNTIME_META"] = _canonical(metadata).decode("ascii")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="runtime aggregate metadata changed",
    ):
        _validate_statistics(regime_plan, statistics)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("profile_id", "arv2-stock-ic-2019-2023-tampered"),
        ("window_start_session", "2019-01-03"),
        ("window_end_session", "2023-12-28"),
    ),
)
def test_regime_cell_profile_or_window_axis_mutant_is_refused(
    regime_plan, field, value
):
    statistics = _regime_aggregate_statistics(regime_plan)
    _mutate_first_regime_cell(
        regime_plan,
        statistics,
        lambda cell: cell.__setitem__(field, value),
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="aggregate cell axis changed",
    ):
        _validate_statistics(regime_plan, statistics)


def test_regime_all_five_mutually_exclusive_missing_categories_reconcile(regime_plan):
    statistics = _regime_aggregate_statistics(regime_plan)
    _profile, meta_name, named_axes = adapter._regime_axis_inventory(
        regime_plan.projection.evaluation_profile_id
    )
    for name, _axis in named_axes:
        cell = json.loads(statistics[name])
        cell.update(
            {
                "eligible_score_row_count": 5,
                "missing_outcome_pair_count": 5,
                "benchmark_endpoint_unavailable_pair_count": 1,
                "named_figi_resolution_refusal_pair_count": 1,
                "security_entry_unavailable_pair_count": 1,
                "membership_ended_by_exit_with_exit_unavailable_pair_count": 1,
                "within_membership_exit_unavailable_pair_count": 1,
            }
        )
        statistics[name] = _canonical(cell).decode("ascii")
    runtime_meta = json.loads(statistics["ARV2_RUNTIME_META"])
    runtime_meta["resolved_security_count"] = 0
    runtime_meta["named_security_refusal_count"] = 1
    statistics["ARV2_RUNTIME_META"] = _canonical(runtime_meta).decode("ascii")
    summary_meta = json.loads(statistics[meta_name])
    summary_meta["named_figi_resolution_refusal_count"] = 1
    statistics[meta_name] = _canonical(summary_meta).decode("ascii")
    _rehash_regime_summary(regime_plan, statistics)

    _validate_statistics(regime_plan, statistics)


def test_regime_named_figi_pair_requires_a_named_resolution_refusal(regime_plan):
    statistics = _regime_aggregate_statistics(regime_plan)
    _mutate_first_regime_cell(
        regime_plan,
        statistics,
        lambda cell: cell.update(
            {
                "eligible_score_row_count": 1,
                "missing_outcome_pair_count": 1,
                "named_figi_resolution_refusal_pair_count": 1,
            }
        ),
    )
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="aggregate cell geometry changed",
    ):
        _validate_statistics(regime_plan, statistics)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        (
            "benchmark_endpoint_unavailable_pair_count",
            1,
            "missing-outcome census changed",
        ),
        (
            "missing_pair_counter_sum_matches_total",
            False,
            "missing-outcome census changed",
        ),
        (
            "endpoint_price_conditioning",
            "unconditioned",
            "outcome conditioning changed",
        ),
        (
            "membership_ended_by_exit_interpretation",
            "confirmed_terminal",
            "outcome conditioning changed",
        ),
    ),
)
def test_regime_self_consistent_missing_census_or_disclosure_mutant_is_refused(
    regime_plan, field, value, message,
):
    statistics = _regime_aggregate_statistics(regime_plan)
    _mutate_first_regime_cell(
        regime_plan,
        statistics,
        lambda cell: cell.__setitem__(field, value),
    )
    with pytest.raises(adapter.AcceptedRiskPreliminarySubmissionError, match=message):
        _validate_statistics(regime_plan, statistics)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("endpoint_price_conditioning_direction", "positive"),
        ("terminal_payoff_policy_applied", True),
        ("membership_ended_by_exit_is_confirmed_terminal", True),
    ),
)
def test_regime_summary_conditioning_or_terminal_claim_mutant_is_refused(
    regime_plan, field, value,
):
    statistics = _regime_aggregate_statistics(regime_plan)
    _profile, meta_name, _named_axes = adapter._regime_axis_inventory(
        regime_plan.projection.evaluation_profile_id
    )
    metadata = json.loads(statistics[meta_name])
    metadata["outcome_availability_disclosures"][field] = value
    statistics[meta_name] = _canonical(metadata).decode("ascii")
    _rehash_regime_summary(regime_plan, statistics)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="regime evaluator aggregate metadata changed",
    ):
        _validate_statistics(regime_plan, statistics)


def test_regime_summary_profile_hash_mutant_is_refused(regime_plan):
    statistics = _regime_aggregate_statistics(regime_plan)
    _profile, meta_name, _named_axes = adapter._regime_axis_inventory(
        regime_plan.projection.evaluation_profile_id
    )
    metadata = json.loads(statistics[meta_name])
    metadata["profile"]["profile_sha256"] = "0" * 64
    statistics[meta_name] = _canonical(metadata).decode("ascii")
    _rehash_regime_summary(regime_plan, statistics)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="regime evaluator aggregate metadata changed",
    ):
        _validate_statistics(regime_plan, statistics)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("terminal_payoff_applied", True),
        ("formal_result", True),
        ("raw_price_rows_in_summary", True),
    ),
)
def test_regime_top_level_scope_flag_mutant_is_refused(regime_plan, field, value):
    statistics = _regime_aggregate_statistics(regime_plan)
    _profile, meta_name, _named_axes = adapter._regime_axis_inventory(
        regime_plan.projection.evaluation_profile_id
    )
    metadata = json.loads(statistics[meta_name])
    metadata[field] = value
    statistics[meta_name] = _canonical(metadata).decode("ascii")
    _rehash_regime_summary(regime_plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="regime evaluator aggregate metadata changed",
    ):
        _validate_statistics(regime_plan, statistics)


def test_regime_source_lineage_mutant_is_refused(regime_plan):
    statistics = _regime_aggregate_statistics(regime_plan)
    _profile, meta_name, _named_axes = adapter._regime_axis_inventory(
        regime_plan.projection.evaluation_profile_id
    )
    metadata = json.loads(statistics[meta_name])
    key = next(iter(metadata["source_lineage_sha256s"]))
    metadata["source_lineage_sha256s"][key] = "0" * 64
    statistics[meta_name] = _canonical(metadata).decode("ascii")
    _rehash_regime_summary(regime_plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="source lineage changed",
    ):
        _validate_statistics(regime_plan, statistics)


def test_regime_summary_identity_mutant_is_refused(regime_plan):
    statistics = _regime_aggregate_statistics(regime_plan)
    _profile, meta_name, _named_axes = adapter._regime_axis_inventory(
        regime_plan.projection.evaluation_profile_id
    )
    metadata = json.loads(statistics[meta_name])
    metadata["summary_sha256"] = "0" * 64
    statistics[meta_name] = _canonical(metadata).decode("ascii")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="summary identity changed",
    ):
        _validate_statistics(regime_plan, statistics)


def test_regime_result_from_another_profile_is_refused(monkeypatch, tmp_path):
    first = _build_plan(
        monkeypatch, tmp_path, regime_evaluator.REGIME_PROFILE_IDS[0]
    )
    second = _build_plan(
        monkeypatch, tmp_path, regime_evaluator.REGIME_PROFILE_IDS[1]
    )
    statistics = _regime_aggregate_statistics(first)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="result inventory changed",
    ):
        _validate_statistics(second, statistics)


def test_runtime_slice_result_boundary_is_shared_with_cloud_runtime(plan):
    statistics = _aggregate_statistics(plan)
    runtime_meta = json.loads(statistics["ARV2_RUNTIME_META"])
    runtime_meta["training_slice_count"] = runtime.MAX_TRAIN_SLICE_COUNT
    statistics["ARV2_RUNTIME_META"] = _canonical(runtime_meta).decode("ascii")
    _validate_statistics(plan, statistics)

    runtime_meta["training_slice_count"] += 1
    statistics["ARV2_RUNTIME_META"] = _canonical(runtime_meta).decode("ascii")
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="runtime aggregate metadata changed",
    ):
        _validate_statistics(plan, statistics)


def _reachable_local_python_paths(root, initial_paths):
    modules = {}
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if ".git" in relative.parts or "tests" in relative.parts:
            continue
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules[".".join(parts)] = path
    pending = [root / item for item in initial_paths]
    observed = set()
    while pending:
        path = pending.pop()
        if path in observed:
            continue
        observed.add(path)
        relative = path.relative_to(root)
        parts = list(relative.with_suffix("").parts)
        package_parts = parts[:-1]
        if parts[-1] == "__init__":
            package_parts = parts[:-1]
        for parent in path.parents:
            if parent == root:
                break
            initializer = parent / "__init__.py"
            if initializer.is_file() and initializer not in observed:
                pending.append(initializer)
        tree = ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            candidates = []
            if isinstance(node, ast.Import):
                candidates.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    retained = len(package_parts) - node.level + 1
                    prefix = package_parts[: max(0, retained)]
                    base = ".".join(prefix + ([base] if base else []))
                if base:
                    candidates.append(base)
                candidates.extend(
                    base + "." + alias.name if base else alias.name
                    for alias in node.names
                )
            pending.extend(
                modules[name]
                for name in candidates
                if name in modules and modules[name] not in observed
            )
    return {str(path.relative_to(root)) for path in observed}


class _Backend:
    def __init__(self, plan):
        self.plan = plan
        self.events = []
        self.project_id = 987
        self.files = {
            "main.py": "# default",
            "research.ipynb": '{"cells":[]}',
        }
        self.objects = {}
        self.compile_state = "BuildSuccess"
        self.terminal_status = "Completed."
        profile_id = plan.projection.evaluation_profile_id
        if profile_id is None:
            self.statistics = _aggregate_statistics(plan)
        elif profile_id == stock_portfolio_evaluator.PROFILE_ID:
            self.statistics = _stock_portfolio_aggregate_statistics(plan)
        else:
            self.statistics = _regime_aggregate_statistics(plan)
        self.extra_initial_source = None
        self.backtest_inventory = None

    def project(self):
        return {
            "projectId": self.project_id,
            "organizationId": self.plan.organization_id,
            "name": self.plan.project_name,
            "language": "Py",
            "owner": True,
            "codeRunning": False,
            "collaborators": [{"owner": True}],
        }

    def __call__(self, url, body, _headers, _timeout):
        path = url.split("/api/v2/", 1)[-1]
        self.events.append(path)
        if path == "object/set":
            marker = b'Content-Disposition: form-data; name="key"\r\n\r\n'
            key_start = body.index(marker) + len(marker)
            key_end = body.index(b"\r\n", key_start)
            key = body[key_start:key_end].decode("utf-8")
            payload_marker = b"Content-Type: application/octet-stream\r\n\r\n"
            start = body.index(payload_marker) + len(payload_marker)
            boundary = body.split(b"\r\n", 1)[0]
            payload = body[start : body.rindex(b"\r\n" + boundary + b"--\r\n")]
            self.objects[key] = payload
            return 200, _canonical({"success": True})
        request = json.loads(body.decode("utf-8"))
        if path == "authenticate":
            response = {"success": True}
        elif path == "projects/read":
            response = {
                "success": True,
                "projects": [] if "projectId" not in request else [self.project()],
                "count": 0 if "projectId" not in request else 1,
            }
        elif path == "projects/create":
            response = {
                "success": True,
                "projects": [
                    {
                        "projectId": self.project_id,
                        "organizationId": self.plan.organization_id,
                        "name": self.plan.project_name,
                        "language": "Py",
                    }
                ],
                "count": 1,
            }
        elif path == "object/properties":
            payload = self.objects[request["key"]]
            response = {
                "success": True,
                "metadata": {
                    "key": request["key"],
                    "size": len(payload),
                    "md5": hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                    "preview": "NEVER SELECT",
                },
            }
        elif path == "files/read":
            if self.extra_initial_source is not None and len(
                [item for item in self.events if item == "files/read"]
            ) == 1:
                self.files[self.extra_initial_source] = "PRIVATE"
            response = {
                "success": True,
                "files": [
                    {
                        "projectId": self.project_id,
                        "name": name,
                        "content": content,
                    }
                    for name, content in sorted(self.files.items())
                ],
            }
        elif path == "files/delete":
            del self.files[request["name"]]
            response = {"success": True}
        elif path in {"files/create", "files/update"}:
            self.files[request["name"]] = request["content"]
            response = {"success": True}
        elif path == "compile/create":
            response = {
                "success": True,
                "compileId": "compile-one",
                "state": "InQueue",
                "parameters": [],
                "projectId": self.project_id,
                "signature": "signature",
                "signatureOrder": [],
            }
        elif path == "compile/read":
            response = {
                "success": True,
                "compileId": "compile-one",
                "state": self.compile_state,
                "logs": ["DISCARD ONLY"],
            }
        elif path == "backtests/create":
            response = {
                "success": True,
                "backtest": {
                    "backtestId": "backtest-one",
                    "name": self.plan.backtest_name,
                    "projectId": self.project_id,
                    "status": "In Queue...",
                },
            }
        elif path == "backtests/list":
            backtests = self.backtest_inventory
            if backtests is None:
                backtests = [
                    {
                        "backtestId": "backtest-one",
                        "name": self.plan.backtest_name,
                        "projectId": self.project_id,
                        "status": self.terminal_status,
                        "statistics": {"FORBIDDEN": "do not inspect"},
                        "charts": {"SECRET": "do not inspect"},
                    }
                ]
            response = {
                "success": True,
                "backtests": backtests,
                "count": len(backtests),
            }
        elif path == "backtests/read":
            response = {
                "success": True,
                "backtest": {
                    "backtestId": "backtest-one",
                    "name": self.plan.backtest_name,
                    "projectId": self.project_id,
                    "status": "Completed.",
                    "statistics": {
                        "Sharpe Ratio": "IGNORED STANDARD VALUE",
                        **self.statistics,
                    },
                    "charts": {"RAW_PRICE": "NEVER SELECT"},
                    "orders": [{"RAW_ORDER": "NEVER SELECT"}],
                },
            }
        else:
            raise AssertionError(path)
        return 200, _canonical(response)


def _client(backend):
    return transport_module.FormalQcTransport(
        http_transport=backend,
        clock=lambda: 1_800_000_000,
    )


def _execute(plan, backend, signature):
    action = _offline_action(adapter.execute_accepted_risk_preliminary_submission_once)
    return action(
        plan=plan,
        owner_signature=signature,
        client=_client(backend),
        started_at_utc="2026-09-14T20:00:00Z",
    )


def _complete(plan, backend, signature, permit, launch):
    action = _offline_action(adapter.inspect_accepted_risk_preliminary_terminal_status)
    return action(
        plan=plan,
        owner_signature=signature,
        permit=permit,
        launch=launch,
        client=_client(backend),
    )


def _recover(plan, backend, signature, permit):
    action = _offline_action(
        adapter.recover_accepted_risk_preliminary_launch_once
    )
    return action(
        plan=plan,
        owner_signature=signature,
        permit=permit,
        client=_client(backend),
    )


def _read(plan, backend, signature, permit, launch, terminal):
    action = _offline_action(
        adapter.read_accepted_risk_preliminary_result_once, result=True
    )
    return action(
        plan=plan,
        execution_permit=permit,
        launch=launch,
        terminal=terminal,
        owner_signature=signature,
        client=_client(backend),
        started_at_utc="2026-09-14T21:00:00Z",
    )


def test_offline_exact_submission_status_and_single_aggregate_read(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, launch = _execute(plan, backend, signature)
    terminal = _complete(plan, backend, signature, permit, launch)
    result_permit, result = _read(
        plan, backend, signature, permit, launch, terminal
    )

    assert terminal.terminal_status == "Completed."
    assert backend.events.count("backtests/create") == 1
    assert backend.events.count("backtests/read") == 1
    assert tuple(name for name, _value in result.custom_statistics) == (
        plan.expected_custom_statistic_names
    )
    persisted = result.persisted_path.read_text()
    assert "IGNORED STANDARD VALUE" not in persisted
    assert "RAW_PRICE" not in persisted
    assert "RAW_ORDER" not in persisted
    assert "NEVER SELECT" not in persisted
    assert backend.events[-2:] == ["backtests/list", "backtests/read"]
    assert list(backend.objects) == [
        item.object_store_key for item in plan.upload_entries
    ]
    assert plan.upload_entries[-1].activation_manifest is True
    assert set(backend.files) == {
        item.project_path for item in plan.source_files
    }
    assert adapter.require_accepted_risk_preliminary_aggregate_result(
        result,
        plan=plan,
        execution_permit=permit,
        launch=launch,
        terminal=terminal,
        result_permit=result_permit,
    ) is result


def test_stock_portfolio_offline_launch_result_read_and_reload_are_exact(
    stock_portfolio_plan,
):
    signature = _offline_signature()
    backend = _Backend(stock_portfolio_plan)

    permit, launch = _execute(stock_portfolio_plan, backend, signature)
    terminal = _complete(
        stock_portfolio_plan, backend, signature, permit, launch
    )
    result_permit, result = _read(
        stock_portfolio_plan,
        backend,
        signature,
        permit,
        launch,
        terminal,
    )
    recovered_permit = adapter.load_accepted_risk_preliminary_result_read_permit(
        plan=stock_portfolio_plan,
        execution_permit=permit,
        launch=launch,
        terminal=terminal,
    )
    recovered_result = adapter.load_accepted_risk_preliminary_aggregate_result(
        plan=stock_portfolio_plan,
        execution_permit=permit,
        launch=launch,
        terminal=terminal,
        result_permit=recovered_permit,
    )

    assert terminal.terminal_status == "Completed."
    assert backend.events.count("backtests/create") == 1
    assert backend.events.count("backtests/read") == 1
    assert len(result.custom_statistics) == 6
    assert result.custom_statistics == recovered_result.custom_statistics
    assert result_permit.permit_sha256 == recovered_permit.permit_sha256
    receipt = json.loads(result.persisted_path.read_bytes())
    accounting = receipt["look_accounting"]
    assert accounting["shared_look_ledger_entry_id"] == "R-063"
    assert accounting["run_level_looks_after"] == 63
    assert accounting["arv2_development_evaluations_after"] == 10
    assert accounting["lifetime_alpha_cell_floor_after"] == 575


def test_regime_offline_submission_reads_only_its_eighteen_statistics(regime_plan):
    signature = _offline_signature()
    backend = _Backend(regime_plan)
    profile_id = regime_plan.projection.evaluation_profile_id
    reservation_accounting = adapter._look_accounting(
        evaluation_profile_id=profile_id
    )
    launch_accounting = adapter._look_accounting(
        stage="launch", evaluation_profile_id=profile_id
    )
    result_accounting = adapter._look_accounting(
        stage="result", evaluation_profile_id=profile_id
    )
    execution_authority = json.loads(
        adapter.render_accepted_risk_preliminary_execution_authority_candidate(
            regime_plan
        )
    )
    assert execution_authority["look_accounting"] == reservation_accounting
    assert execution_authority["evaluation_profile_id"] == profile_id
    assert execution_authority["evaluation_profile_sha256"] == (
        regime_plan.evaluation_profile_sha256
    )
    permit, launch = _execute(regime_plan, backend, signature)
    terminal = _complete(regime_plan, backend, signature, permit, launch)
    result_authority = json.loads(
        adapter.render_accepted_risk_preliminary_result_read_authority_candidate(
            plan=regime_plan,
            permit=permit,
            launch=launch,
            terminal=terminal,
        )
    )
    assert result_authority["look_accounting"] == launch_accounting
    assert result_authority["evaluation_profile_id"] == profile_id
    assert result_authority["evaluation_profile_sha256"] == (
        regime_plan.evaluation_profile_sha256
    )
    result_permit, result = _read(
        regime_plan, backend, signature, permit, launch, terminal
    )

    assert terminal.terminal_status == "Completed."
    assert backend.events.count("backtests/create") == 1
    assert backend.events.count("backtests/read") == 1
    assert len(result.custom_statistics) == 18
    assert tuple(name for name, _value in result.custom_statistics) == (
        regime_plan.expected_custom_statistic_names
    )
    plan_record = json.loads(
        adapter.persist_accepted_risk_preliminary_submission_plan(
            regime_plan
        ).read_bytes()
    )
    permit_record = json.loads(permit.permit_path.read_bytes())
    precreate_record = json.loads(
        next(regime_plan.control_directory.glob("pre-create-control-*.json")).read_bytes()
    )
    launch_record = json.loads(
        next(regime_plan.control_directory.glob("launch-receipt-*.json")).read_bytes()
    )
    persisted = json.loads(result.persisted_path.read_bytes())
    assert plan_record["look_accounting"] == reservation_accounting
    assert permit_record["look_accounting"] == reservation_accounting
    assert precreate_record["look_accounting"] == launch_accounting
    assert launch_record["look_accounting"] == launch_accounting
    assert persisted["look_accounting"] == result_accounting
    expected = _REGIME_ACCOUNTING[regime_plan.projection.evaluation_profile_id]
    assert persisted["look_accounting"]["shared_look_ledger_entry_id"] == expected[0]
    assert persisted["look_accounting"]["lifetime_alpha_cell_floor_after"] == (
        expected[6]
    )
    assert adapter.require_accepted_risk_preliminary_aggregate_result(
        result,
        plan=regime_plan,
        execution_permit=permit,
        launch=launch,
        terminal=terminal,
        result_permit=result_permit,
    ) is result


def test_durable_receipts_rehydrate_every_phase_for_cross_process_recovery(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, launch = _execute(plan, backend, signature)
    terminal = _complete(plan, backend, signature, permit, launch)

    plan_path = adapter.persist_accepted_risk_preliminary_submission_plan(plan)
    recovered_plan = adapter.load_accepted_risk_preliminary_submission_plan(
        plan_path=plan_path,
        package=plan.package,
        projection=plan.projection,
        organization_id=plan.organization_id,
    )
    recovered_permit = adapter.load_accepted_risk_preliminary_submission_permit(
        plan=recovered_plan
    )
    recovered_launch = adapter.load_accepted_risk_preliminary_launch_receipt(
        plan=recovered_plan,
        permit=recovered_permit,
    )
    recovered_terminal = adapter.load_accepted_risk_preliminary_terminal_status(
        plan=recovered_plan,
        permit=recovered_permit,
        launch=recovered_launch,
    )
    authority = adapter.render_accepted_risk_preliminary_result_read_authority_candidate(
        plan=recovered_plan,
        permit=recovered_permit,
        launch=recovered_launch,
        terminal=recovered_terminal,
    )
    assert b'"signature_purpose":"formal_qc_result_read"' in authority

    result_permit, result = _read(
        recovered_plan,
        backend,
        signature,
        recovered_permit,
        recovered_launch,
        recovered_terminal,
    )
    recovered_result_permit = (
        adapter.load_accepted_risk_preliminary_result_read_permit(
            plan=recovered_plan,
            execution_permit=recovered_permit,
            launch=recovered_launch,
            terminal=recovered_terminal,
        )
    )
    recovered_result = adapter.load_accepted_risk_preliminary_aggregate_result(
        plan=recovered_plan,
        execution_permit=recovered_permit,
        launch=recovered_launch,
        terminal=recovered_terminal,
        result_permit=recovered_result_permit,
    )
    assert recovered_result.custom_statistics == result.custom_statistics
    assert recovered_result_permit.permit_sha256 == result_permit.permit_sha256
    assert adapter.require_accepted_risk_preliminary_aggregate_result(
        recovered_result,
        plan=recovered_plan,
        execution_permit=recovered_permit,
        launch=recovered_launch,
        terminal=recovered_terminal,
        result_permit=recovered_result_permit,
    ) is recovered_result
    for path in recovered_plan.control_directory.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600


def test_ambiguous_create_recovery_lists_once_and_never_creates_again(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, launched = _execute(plan, backend, signature)
    launch_path = plan.control_directory / (
        "launch-receipt-" + plan.plan_sha256[:24] + ".json"
    )
    launch_path.unlink()
    create_calls = backend.events.count("backtests/create")

    recovered = _recover(plan, backend, signature, permit)

    assert recovered.backtest_id == launched.backtest_id == "backtest-one"
    assert recovered.initial_status == adapter.RECOVERED_LAUNCH_INITIAL_STATUS
    assert backend.events.count("backtests/create") == create_calls == 1
    assert backend.events.count("backtests/list") == 1
    assert launch_path.is_file()
    assert adapter.require_accepted_risk_preliminary_launch_receipt(
        recovered, plan=plan, permit=permit
    ) is recovered


def test_existing_launch_recovery_makes_zero_network_calls(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, launched = _execute(plan, backend, signature)
    before = tuple(backend.events)

    recovered = _recover(plan, backend, signature, permit)

    assert recovered == launched
    assert tuple(backend.events) == before


@pytest.mark.parametrize("count", (0, 2))
def test_ambiguous_create_recovery_refuses_zero_or_multiple_runs(plan, count):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, _launch = _execute(plan, backend, signature)
    next(plan.control_directory.glob("launch-receipt-*.json")).unlink()
    row = {
        "backtestId": "backtest-one",
        "name": plan.backtest_name,
        "projectId": backend.project_id,
        "status": "In Queue...",
    }
    backend.backtest_inventory = [dict(row) for _index in range(count)]
    before_create = backend.events.count("backtests/create")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionLocked,
        match="launch_recovery",
    ):
        _recover(plan, backend, signature, permit)

    assert backend.events.count("backtests/list") == 1
    assert backend.events.count("backtests/create") == before_create == 1
    assert not any(plan.control_directory.glob("launch-receipt-*.json"))
    before_retry = tuple(backend.events)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionLocked,
        match="recovery permit already spent",
    ):
        _recover(plan, backend, signature, permit)
    assert tuple(backend.events) == before_retry


def test_r055_development_look_accounting_is_bound_end_to_end(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    execution_authority = json.loads(
        adapter.render_accepted_risk_preliminary_execution_authority_candidate(plan)
    )
    assert execution_authority["look_accounting"] == _EXPECTED_LOOK_ACCOUNTING
    assert "evaluation_profile_id" not in execution_authority
    assert "evaluation_profile_sha256" not in execution_authority

    permit, launch = _execute(plan, backend, signature)
    terminal = _complete(plan, backend, signature, permit, launch)
    plan_record = json.loads(
        adapter.persist_accepted_risk_preliminary_submission_plan(plan).read_bytes()
    )
    permit_record = json.loads(permit.permit_path.read_bytes())
    launch_record = json.loads(
        (plan.control_directory / (
            "launch-receipt-" + plan.plan_sha256[:24] + ".json"
        )).read_bytes()
    )
    for record in (plan_record, permit_record):
        assert record["look_accounting"] == _EXPECTED_LOOK_ACCOUNTING
    assert plan_record["schema"] == adapter.PLAN_SCHEMA
    assert "evaluation_profile_id" not in plan_record
    assert "evaluation_profile_sha256" not in plan_record
    assert launch_record["look_accounting"] == _look_accounting_at("launch")

    result_authority = json.loads(
        adapter.render_accepted_risk_preliminary_result_read_authority_candidate(
            plan=plan,
            permit=permit,
            launch=launch,
            terminal=terminal,
        )
    )
    assert result_authority["look_accounting"] == _look_accounting_at("launch")
    assert "evaluation_profile_id" not in result_authority
    assert "evaluation_profile_sha256" not in result_authority
    _result_permit, result = _read(
        plan, backend, signature, permit, launch, terminal
    )
    result_record = json.loads(result.persisted_path.read_bytes())
    assert result_record["look_accounting"] == _look_accounting_at("result")


def test_missing_execution_signature_refuses_before_network_or_permit(plan):
    backend = _Backend(plan)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="formal_qc_execution",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-14T20:00:00Z",
        )
    assert backend.events == []
    assert not any(plan.control_directory.iterdir())


def test_action_global_mutation_has_an_isolated_pre_network_refusal(
    plan, monkeypatch,
):
    backend = _Backend(plan)
    monkeypatch.setattr(adapter, "_PINNED_TRANSPORT_CALL", lambda *_items: None)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-14T20:00:00Z",
        )
    assert backend.events == []
    assert not any(plan.control_directory.iterdir())


def test_execution_project_parser_mutation_is_separately_refused_pre_network(
    plan, monkeypatch,
):
    backend = _Backend(plan)
    monkeypatch.setattr(adapter, "_PINNED_CREATED_PROJECT", lambda *_items: {})
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-14T20:00:00Z",
        )
    assert backend.events == []


def test_result_parser_mutation_is_separately_refused_before_permit_or_read(
    plan, monkeypatch,
):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, launch = _execute(plan, backend, signature)
    terminal = _complete(plan, backend, signature, permit, launch)
    monkeypatch.setattr(adapter, "_parse_custom_result", lambda *_items: ())
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.read_accepted_risk_preliminary_result_once(
            plan=plan,
            execution_permit=permit,
            launch=launch,
            terminal=terminal,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-14T21:00:00Z",
        )
    assert "backtests/read" not in backend.events
    assert not (plan.control_directory / (
        "result-read-permit-" + plan.plan_sha256[:24] + ".json"
    )).exists()


def test_recovery_parser_mutation_is_separately_refused_before_list_or_permit(
    plan, monkeypatch,
):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, _launch = _execute(plan, backend, signature)
    next(plan.control_directory.glob("launch-receipt-*.json")).unlink()
    before = tuple(backend.events)
    monkeypatch.setattr(adapter, "_PINNED_PARSE_UNIQUE_RUN", lambda *_items: None)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.recover_accepted_risk_preliminary_launch_once(
            plan=plan,
            owner_signature=None,
            permit=permit,
            client=_client(backend),
        )

    assert tuple(backend.events) == before
    assert not any(plan.control_directory.glob("launch-recovery-permit-*.json"))


def test_forged_equal_launch_receipt_lacks_process_return_authority(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, launch = _execute(plan, backend, signature)
    forged = dataclasses.replace(launch)
    assert forged == launch and forged is not launch
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="process-return authority",
    ):
        adapter.require_accepted_risk_preliminary_launch_receipt(
            forged,
            plan=plan,
            permit=permit,
        )


def test_result_require_rejects_hostile_wrong_type_before_attribute_access(plan):
    calls = []

    class Hostile:
        def __getattribute__(self, name):
            calls.append(name)
            raise AssertionError("hostile result attribute was accessed")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="result receipt type changed",
    ):
        adapter.require_accepted_risk_preliminary_aggregate_result(
            Hostile(),
            plan=plan,
            execution_permit=None,
            launch=None,
            terminal=None,
            result_permit=None,
        )
    assert calls == []


def test_execution_permit_is_one_use_and_reuse_stops_before_network(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    _execute(plan, backend, signature)
    observed = tuple(backend.events)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionLocked,
        match="permit already spent",
    ):
        _execute(plan, backend, signature)
    assert tuple(backend.events) == observed


@pytest.mark.parametrize("target", ("package", "projection"))
def test_package_or_projection_mutation_refuses_before_network(plan, target):
    signature = _offline_signature()
    backend = _Backend(plan)
    if target == "package":
        value = plan.package.upload_objects[0]
        original = value.content_sha256
        object.__setattr__(value, "content_sha256", "0" * 64)
    else:
        value = plan.projection
        original = value.projection_sha256
        object.__setattr__(value, "projection_sha256", "0" * 64)
    try:
        with pytest.raises(Exception):
            _execute(plan, backend, signature)
    finally:
        object.__setattr__(
            value,
            "content_sha256" if target == "package" else "projection_sha256",
            original,
        )
    assert backend.events == []


def test_host_source_change_invalidates_signed_plan_before_network(
    plan, tmp_path,
):
    bound_paths = {item.path for item in plan.host_closure.sources}
    assert {
        "data/__init__.py",
        "data/exchange_calendar.py",
        "data/financial_primitives.py",
        "research/__init__.py",
        "research/quantconnect.py",
        "research/analyst_revisions_v2/artifact_io.py",
        "research/analyst_revisions_v2/canonical.py",
        "research/analyst_revisions_v2_qc/accepted_risk_preliminary_package.py",
        "research/analyst_revisions_v2_qc/accepted_risk_preliminary_qc_runtime.py",
        "research/analyst_revisions_v2_qc/accepted_risk_preliminary_rating_evaluator.py",
        "research/analyst_revisions_v2_qc/accepted_risk_preliminary_submission_adapter.py",
        "research/analyst_revisions_v2_qc/formal_qc_transport.py",
        "research/analyst_revisions_v2_qc/formal_submission_adapter.py",
        "scripts/build_arv2_historical_preopen_bridge.py",
        "scripts/build_arv2_massive_input_pair.py",
        "scripts/build_arv2_preopen_input.py",
        "scripts/capture_arv2_massive.py",
        "scripts/capture_arv2_sharadar.py",
    } <= bound_paths
    empty_hash = hashlib.sha256(b"").hexdigest()
    bindings = {item.path: item for item in plan.host_closure.sources}
    for initializer in ("data/__init__.py", "research/__init__.py"):
        assert bindings[initializer].byte_count == 0
        assert bindings[initializer].content_sha256 == empty_hash
    mirror = (tmp_path / "host-mirror").resolve()
    mirror.mkdir(mode=0o700)
    for source in plan.host_closure.sources:
        destination = mirror / source.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(plan.host_closure.worktree_root) / source.path, destination)
        destination.chmod(0o644)
    control = tmp_path / "mirror-control"
    control.mkdir(mode=0o700)
    mirrored_plan = adapter.build_accepted_risk_preliminary_submission_plan(
        package=plan.package,
        projection=plan.projection,
        organization_id=plan.organization_id,
        project_name=plan.project_name,
        backtest_name=plan.backtest_name,
        control_directory=control,
        worktree_root=mirror,
    )
    candidate = adapter.render_accepted_risk_preliminary_execution_authority_candidate(
        mirrored_plan
    )
    assert json.loads(candidate)["host_code_closure"]["closure_sha256"] == (
        mirrored_plan.host_closure.closure_sha256
    )
    initializer_path = mirror / "research/__init__.py"
    initializer_path.write_bytes(b"# altered after signing\n")
    backend = _Backend(mirrored_plan)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="submission plan changed",
    ):
        _execute(mirrored_plan, backend, _offline_signature())
    assert backend.events == []
    assert not any(control.iterdir())


def test_host_source_inventory_covers_full_reachable_local_import_graph(plan):
    root = Path(plan.host_closure.worktree_root)
    bound = {item.path for item in plan.host_closure.sources}
    assert _reachable_local_python_paths(root, bound) == bound


def test_host_source_closure_rejects_an_in_tree_file_symlink(plan, tmp_path):
    mirror = (tmp_path / "symlink-file-host").resolve()
    mirror.mkdir(mode=0o700)
    for source in plan.host_closure.sources:
        destination = mirror / source.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(plan.host_closure.worktree_root) / source.path, destination)
        destination.chmod(0o644)
    target = mirror / (
        "research/analyst_revisions_v2_qc/"
        "accepted_risk_preliminary_qc_runtime.py"
    )
    peer = mirror / (
        "research/analyst_revisions_v2_qc/"
        "accepted_risk_preliminary_rating_evaluator.py"
    )
    target.unlink()
    target.symlink_to(peer)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="inventory contains a symlink",
    ):
        adapter._build_host_closure(mirror)


def test_host_source_closure_rejects_a_configured_directory_symlink(tmp_path):
    mirror = (tmp_path / "symlink-directory-host").resolve()
    (mirror / "research").mkdir(parents=True)
    real_lane = mirror / "real-lane"
    real_lane.mkdir()
    (mirror / "research" / "analyst_revisions_v2").symlink_to(real_lane)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="directory changed or uses a symlink",
    ):
        adapter._build_host_closure(mirror)


def test_host_source_closure_rejects_a_nested_directory_symlink(plan, tmp_path):
    mirror = (tmp_path / "nested-symlink-host").resolve()
    mirror.mkdir(mode=0o700)
    for source in plan.host_closure.sources:
        destination = mirror / source.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(plan.host_closure.worktree_root) / source.path, destination)
        destination.chmod(0o644)
    lane = mirror / "research/analyst_revisions_v2"
    real_helpers = lane / "real_helpers"
    real_helpers.mkdir()
    (real_helpers / "helper.py").write_text("VALUE = 1\n", encoding="ascii")
    (lane / "linked_helpers").symlink_to(real_helpers, target_is_directory=True)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="inventory contains a symlink",
    ):
        adapter._build_host_closure(mirror)


def test_extra_new_project_source_refuses_without_deleting_it_or_compiling(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    backend.extra_initial_source = "unexpected.py"
    with pytest.raises(adapter.AcceptedRiskPreliminarySubmissionLocked):
        _execute(plan, backend, signature)
    assert backend.files["unexpected.py"] == "PRIVATE"
    assert "files/delete" not in backend.events
    assert "compile/create" not in backend.events
    assert "backtests/create" not in backend.events


def test_compile_failure_refuses_before_backtest_create(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    backend.compile_state = "BuildError"
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionLocked,
        match="submission",
    ) as caught:
        _execute(plan, backend, signature)
    assert isinstance(
        caught.value.__cause__, adapter.AcceptedRiskPreliminarySubmissionError
    )
    permit_path = next(plan.control_directory.glob("execution-permit-*.json"))
    assert json.loads(permit_path.read_bytes())["look_accounting"] == (
        _EXPECTED_LOOK_ACCOUNTING
    )
    assert not any(plan.control_directory.glob("pre-create-control-*.json"))
    assert "backtests/create" not in backend.events


def test_terminal_failure_is_distinct_and_never_reads_result(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, launch = _execute(plan, backend, signature)
    backend.terminal_status = "Runtime Error"
    with pytest.raises(adapter.AcceptedRiskPreliminaryTerminalFailure) as caught:
        _complete(plan, backend, signature, permit, launch)
    assert caught.value.receipt.terminal_status == "Runtime Error"
    assert "backtests/read" not in backend.events
    launch_record = json.loads(next(
        plan.control_directory.glob("launch-receipt-*.json")
    ).read_bytes())
    assert launch_record["look_accounting"] == _look_accounting_at("launch")
    assert launch_record["look_accounting"][
        "emitted_preliminary_ic_cell_count"
    ] == 0
    assert launch_record["look_accounting"][
        "lifetime_alpha_cell_floor_after"
    ] == 484
    assert not any(plan.control_directory.glob("aggregate-result-*.json"))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("eligible_score_row_count", "0", "cell count changed"),
        ("accepted_outcome_pair_count", -1, "cell count changed"),
        ("eligible_score_row_count", 1, "count invariants changed"),
    ),
)
def test_self_consistent_cell_count_mutants_are_refused(
    plan, field, value, message,
):
    statistics = _aggregate_statistics(plan)
    _mutate_first_cell(statistics, lambda cell: cell.__setitem__(field, value))
    with pytest.raises(adapter.AcceptedRiskPreliminarySubmissionError, match=message):
        _validate_statistics(plan, statistics)


def test_self_consistent_cell_status_mutant_is_refused(plan):
    statistics = _aggregate_statistics(plan)
    _mutate_first_cell(
        statistics,
        lambda cell: cell.__setitem__(
            "status", "PRELIMINARY_DESCRIPTIVE_AVAILABLE"
        ),
    )
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="cell status changed",
    ):
        _validate_statistics(plan, statistics)


def _make_first_cell_metric_available(cell, field, value):
    cell.update(
        {
            "eligible_score_row_count": 20,
            "accepted_outcome_pair_count": 20,
            "missing_outcome_pair_count": 0,
            "sector_refused_row_count": 0,
            "valid_ic_date_count": 1,
            "invalid_ic_date_count": 0,
            "status": "INCONCLUSIVE_UNDERFILLED",
            "mean_daily_spearman_ic": "0",
            "median_daily_spearman_ic": "0",
            "positive_ic_date_share": "0",
            "mean_of_daily_cross_section_mean_excess_returns": "0",
            "median_of_daily_cross_section_mean_excess_returns": "0",
            field: value,
        }
    )


@pytest.mark.parametrize("value", ("NaN", "01", "-0"))
def test_self_consistent_noncanonical_or_nonfinite_metric_is_refused(plan, value):
    statistics = _aggregate_statistics(plan)
    _mutate_first_cell(
        statistics,
        lambda cell: _make_first_cell_metric_available(
            cell, "mean_daily_spearman_ic", value
        ),
    )
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="canonical finite Decimal",
    ):
        _validate_statistics(plan, statistics)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("mean_daily_spearman_ic", "1.1"),
        ("median_daily_spearman_ic", "-1.1"),
        ("positive_ic_date_share", "1.1"),
    ),
)
def test_self_consistent_out_of_range_metric_is_refused(plan, field, value):
    statistics = _aggregate_statistics(plan)
    _mutate_first_cell(
        statistics,
        lambda cell: _make_first_cell_metric_available(cell, field, value),
    )
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="bounded metric changed",
    ):
        _validate_statistics(plan, statistics)


def test_self_consistent_false_source_lineage_is_refused(plan):
    statistics = _aggregate_statistics(plan)
    metadata = json.loads(statistics["ARV2_PRELIMINARY_META"])
    field = evaluator._SOURCE_LINEAGE_FIELDS[0]
    metadata["source_lineage_sha256s"][field] = "0" * 64
    statistics["ARV2_PRELIMINARY_META"] = _canonical(metadata).decode("ascii")
    _rehash_preliminary_summary(statistics)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="source lineage changed",
    ):
        _validate_statistics(plan, statistics)


def test_result_key_mismatch_consumes_read_permit_and_refuses(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, launch = _execute(plan, backend, signature)
    terminal = _complete(plan, backend, signature, permit, launch)
    backend.statistics.pop(plan.expected_custom_statistic_names[0])
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionLocked,
        match="result_read",
    ) as caught:
        _read(plan, backend, signature, permit, launch, terminal)
    assert isinstance(
        caught.value.__cause__, adapter.AcceptedRiskPreliminarySubmissionError
    )
    assert backend.events.count("backtests/read") == 1
    assert (plan.control_directory / (
        "result-read-permit-" + plan.plan_sha256[:24] + ".json"
    )).is_file()


def test_result_read_permit_is_one_use_and_second_read_makes_no_call(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, launch = _execute(plan, backend, signature)
    terminal = _complete(plan, backend, signature, permit, launch)
    _read(plan, backend, signature, permit, launch, terminal)
    calls = backend.events.count("backtests/read")
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionLocked,
        match="permit already spent",
    ):
        _read(plan, backend, signature, permit, launch, terminal)
    assert backend.events.count("backtests/read") == calls == 1


def test_result_signature_is_separate_and_required_before_result_permit(plan):
    signature = _offline_signature()
    backend = _Backend(plan)
    permit, launch = _execute(plan, backend, signature)
    terminal = _complete(plan, backend, signature, permit, launch)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="formal_qc_result_read",
    ):
        adapter.read_accepted_risk_preliminary_result_once(
            plan=plan,
            execution_permit=permit,
            launch=launch,
            terminal=terminal,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-14T21:00:00Z",
        )
    assert "backtests/read" not in backend.events
    assert not (plan.control_directory / (
        "result-read-permit-" + plan.plan_sha256[:24] + ".json"
    )).exists()
