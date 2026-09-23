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
    accepted_risk_market_cap_stock_portfolio_evaluator as market_cap_evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_qc_runtime as market_cap_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_objective_synthetic_leverage_evaluator as leverage_evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_objective_synthetic_leverage_qc_runtime as leverage_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate as six_universe_gate,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate_evaluator as six_universe_evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate_qc_runtime as six_universe_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_submission_adapter as adapter,
)
from research.analyst_revisions_v2_qc import formal_qc_transport as transport_module
from research.analyst_revisions_v2_qc.owner_signature_authority import (
    OwnerSignatureAuthority,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_six_universe_gate_evaluator as six_evaluator_fixtures,
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
    "infrastructure_looks_before": 27,
    "infrastructure_looks_after": 27,
    "authenticated_infrastructure_look_count": 27,
    "infrastructure_look_ledger_id": (
        "arv2-infrastructure-look-ledger-4a726bcdd9b7232f34a1eaf8"
    ),
    "infrastructure_look_ledger_hash": (
        "4a726bcdd9b7232f34a1eaf891f7b8f83334002396aa48720b19abd22391305e"
    ),
    "infrastructure_look_ledger_artifact_sha256": (
        "e837946d6fe9d31f16d4a901f878e965036f6931f8ed5bb1806fdb5a1c83cdd9"
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

_PINNED_BUILD_SIX_EVALUATOR_INPUT = evaluator.load_preliminary_rating_input


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


def test_look_accounting_derives_the_authenticated_infrastructure_total(
    monkeypatch,
):
    binding = adapter._PINNED_INFRASTRUCTURE_LEDGER
    ledger = json.loads(binding.payload)
    ledger["append_only_contract"]["entry_count"] += 1
    ledger["entries"].append({"synthetic_isolation_entry": True})
    ledger["totals"]["infrastructure_research_looks_spent"] += 1
    changed_binding = dataclasses.replace(binding, payload=_canonical(ledger))
    monkeypatch.setattr(
        adapter,
        "_PINNED_REQUIRE_INFRASTRUCTURE_LEDGER",
        lambda _binding: changed_binding,
    )

    accounting = adapter._look_accounting()

    assert accounting["infrastructure_looks_before"] == 28
    assert accounting["infrastructure_looks_after"] == 28
    assert accounting["authenticated_infrastructure_look_count"] == 28


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


def _legacy_market_cap_projection_inventory(value):
    source_files = tuple(
        item
        for item in value.source_files
        if item.project_path
        != "accepted_risk_market_cap_stock_portfolio_tilt.py"
    )
    provisional = dataclasses.replace(
        value,
        projection_id="",
        projection_sha256="",
        source_files=source_files,
        total_source_byte_count=sum(item.byte_count for item in source_files),
    )
    semantic = provisional.to_record()
    semantic["projection_id"] = None
    semantic["projection_sha256"] = None
    digest = hashlib.sha256(_canonical(semantic)).hexdigest()
    return projection_builder.require_accepted_risk_preliminary_qc_projection(
        dataclasses.replace(
            provisional,
            projection_id="arv2-preliminary-qc-projection-" + digest[:24],
            projection_sha256=digest,
        )
    )


def _build_plan(
    monkeypatch,
    tmp_path,
    evaluation_profile_id=None,
    *,
    legacy_market_cap_inventory=False,
    allow_superseded_projection_for_execution_test=False,
):
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
    superseded = projection_builder.SUPERSEDED_UNSPENT_PROFILE_IDS
    if allow_superseded_projection_for_execution_test:
        monkeypatch.setattr(
            projection_builder,
            "SUPERSEDED_UNSPENT_PROFILE_IDS",
            (),
        )
    try:
        projection = (
            projection_builder.build_accepted_risk_preliminary_qc_projection(
                package,
                evaluation_profile_id=evaluation_profile_id,
            )
        )
    finally:
        if allow_superseded_projection_for_execution_test:
            monkeypatch.setattr(
                projection_builder,
                "SUPERSEDED_UNSPENT_PROFILE_IDS",
                superseded,
            )
    if legacy_market_cap_inventory:
        projection = _legacy_market_cap_projection_inventory(projection)
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


@pytest.fixture(
    params=(
        stock_portfolio_evaluator.SP500_PROFILE_ID,
        stock_portfolio_evaluator.NASDAQ100_MEMBERSHIP_ONLY_PROFILE_ID,
        stock_portfolio_evaluator.UNION_MEMBERSHIP_ONLY_PROFILE_ID,
    )
)
def stock_universe_plan(request, monkeypatch, tmp_path):
    return _build_plan(monkeypatch, tmp_path, request.param)


@pytest.fixture(params=market_cap_evaluator.PROFILE_IDS)
def market_cap_plan(request, monkeypatch, tmp_path):
    return _build_plan(monkeypatch, tmp_path, request.param)


@pytest.fixture
def market_cap_plan_2021(monkeypatch, tmp_path):
    return _build_plan(
        monkeypatch,
        tmp_path,
        market_cap_evaluator.QQQ_2021_2025_V2_PROFILE_ID,
    )


@pytest.fixture(
    params=(
        market_cap_evaluator.QQQ_2021_2025_V2_PROFILE_ID,
        market_cap_evaluator.SPY_2021_2025_V2_PROFILE_ID,
    )
)
def spent_market_cap_plan(request, monkeypatch, tmp_path):
    return _build_plan(
        monkeypatch,
        tmp_path,
        request.param,
        legacy_market_cap_inventory=True,
    )


@pytest.fixture(params=leverage_evaluator.PROFILE_IDS)
def leverage_plan(request, monkeypatch, tmp_path):
    return _build_plan(monkeypatch, tmp_path, request.param)


@pytest.fixture
def leverage_plan_qqq(monkeypatch, tmp_path):
    return _build_plan(
        monkeypatch,
        tmp_path,
        leverage_evaluator.QQQ_2021_2025_V3_PROFILE_ID,
    )


@pytest.fixture(
    params=(
        six_universe_evaluator.TOP10_PRIMARY_PROFILE.profile_id,
        six_universe_evaluator.TOP5_SENSITIVITY_PROFILE.profile_id,
    )
)
def six_universe_plan(request, monkeypatch, tmp_path):
    return _build_plan(monkeypatch, tmp_path, request.param)


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
    profile_id = plan.projection.evaluation_profile_id
    profile = stock_portfolio_evaluator.require_stock_portfolio_profile(
        profile_id
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
            "profile_id": profile_id,
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
        "selected_execution_count": 261,
        "rebalance_execution_count": 261,
        "full_target_execution_count": 0,
        "underfilled_target_execution_count": 261,
        "matched_rebalance_execution_count": 261,
        "matched_target_met_execution_count": 261,
        "matched_underfilled_target_execution_count": 0,
        "sector_refused_decision_count": 1,
        "mean_eligible_score_count": "1",
        "mean_selected_name_count": "1",
        "mean_executed_target_gross_exposure": "0.0196",
        "matched_mean_executed_target_gross_exposure": "0.0196",
        "average_holding_count": "1",
        "entry_price_refusal_count": 0,
        "stale_mark_session_count": int(proxy),
        "deferred_rebalance_count": 0,
        "partial_rebalance_decision_count": int(proxy),
        "stale_position_deferral_count": int(proxy),
        "mean_locked_gross_at_partial_decisions": "0.005" if proxy else "0",
        "locked_exposure_over_target_count": 0,
        "membership_end_liquidation_count": int(zero_recovery),
        "membership_end_zero_recovery_count": int(zero_recovery),
        "membership_end_entry_refusal_count": 0,
        "matched_entry_price_refusal_count": 0,
        "matched_stale_mark_session_count": 0,
        "matched_deferred_rebalance_count": 0,
        "matched_partial_rebalance_decision_count": 0,
        "matched_stale_position_deferral_count": 0,
        "matched_mean_locked_gross_at_partial_decisions": "0",
        "matched_locked_exposure_over_target_count": 0,
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
        "evaluation_profile_id": profile_id,
        "evaluation_profile_sha256": profile["profile_sha256"],
        "runtime_slice_count": 1,
    }
    statistics["ARV2_RUNTIME_META"] = _canonical(runtime_meta).decode("ascii")
    assert tuple(sorted(statistics)) == plan.expected_custom_statistic_names
    assert all(len(value) <= 4096 for value in statistics.values())
    return statistics


def _market_cap_aggregate_statistics(plan):
    profile_id = plan.projection.evaluation_profile_id
    tilt_profile = profile_id in market_cap_evaluator.TILT_PROFILE_IDS
    profile = market_cap_evaluator.require_market_cap_stock_portfolio_profile(
        profile_id
    )
    decisions = profile["expected_decision_session_count"]
    returns = profile["expected_return_session_count"]
    resolved = plan.package.runtime_symbol_binding_count
    assert resolved == 1
    history_calls = 2 * (
        (
            decisions
            + market_cap_runtime.HISTORY_CHUNK_DECISION_COUNT
            - 1
        )
        // market_cap_runtime.HISTORY_CHUNK_DECISION_COUNT
    )
    signal_cumulative = {0: "0.20", 5: "0.19", 10: "0.18", 20: "0.16"}
    matched_cumulative = {0: "0.10", 5: "0.09", 10: "0.08", 20: "0.06"}
    signal_annual = {}
    matched_annual = {}
    with evaluator.localcontext(evaluator._context()):
        for cost in market_cap_evaluator.COST_BPS_SCENARIOS:
            signal_annual[cost] = evaluator._decimal_text(
                +(
                    Decimal("0.10")
                    - Decimal(cost)
                    / Decimal(10000)
                    * Decimal("0.001")
                    * market_cap_evaluator.ANNUALIZATION_SESSIONS
                )
            )
            matched_annual[cost] = evaluator._decimal_text(
                +(
                    Decimal("0.09")
                    - Decimal(cost)
                    / Decimal(10000)
                    * Decimal("0.002")
                    * market_cap_evaluator.ANNUALIZATION_SESSIONS
                )
            )

    account = {
        "rebalance_execution_count": decisions,
        "full_target_execution_count": decisions,
        "underfilled_target_execution_count": 0,
        "locked_exposure_over_target_count": 0,
        "mean_executed_gross_exposure": "0.98",
        "minimum_executed_gross_exposure": "0.98",
        "maximum_executed_gross_exposure": "0.98",
        "mean_maximum_position_weight": "0.98",
        "maximum_position_weight": "0.98",
        "mean_invested_weight_hhi": "1",
        "mean_effective_holding_count": "1",
        "average_holding_count": "1",
        "average_daily_two_sided_turnover": "0.001",
        "average_cash_weight": "0.02",
        "entry_price_refusal_count": 0,
        "stale_mark_session_count": 0,
        "partial_rebalance_decision_count": 0,
        "stale_position_deferral_count": 0,
        "selection_exit_deferral_count": 0,
        "eligibility_exit_liquidation_count": 0,
        "eligibility_exit_zero_recovery_count": 0,
    }
    if tilt_profile:
        account.update(
            locked_sector_over_target_count=0,
            sector_target_underfill_count=0,
        )
    matched_account = dict(account)
    matched_account["average_daily_two_sided_turnover"] = "0.002"
    statistics = {}
    cells = []
    for cost in market_cap_evaluator.COST_BPS_SCENARIOS:
        with evaluator.localcontext(evaluator._context()):
            signal_sharpe = evaluator._decimal_text(
                +(Decimal(signal_annual[cost]) / Decimal("0.2"))
            )
            matched_sharpe = evaluator._decimal_text(
                +(Decimal(matched_annual[cost]) / Decimal("0.3"))
            )
        signal_return = signal_cumulative[cost]
        matched_return = matched_cumulative[cost]
        cell = {
            "schema": market_cap_evaluator.PORTFOLIO_CELL_SCHEMA,
            "profile_id": profile_id,
            "cost_bps_per_side": cost,
            "primary_cost_scenario": cost == 10,
            "status": "PRELIMINARY_DESCRIPTIVE_AVAILABLE",
            "return_session_count": returns,
            "invested_return_session_count": returns - 1,
            "return_metric_conditioning": (
                "zero_recovery_for_missing_eligibility_exits_and_stale_mark_"
                "carry_with_trade_deferral_within_eligibility"
            ),
            "risk_metrics_are_price_proxy_conditioned": False,
            "exposure_underfill_present": False,
            "cumulative_return": signal_return,
            "matched_eligible_stock_cumulative_return": matched_return,
            "spy_cumulative_return": "0.30",
            "cumulative_return_minus_matched": evaluator._decimal_text(
                Decimal(signal_return) - Decimal(matched_return)
            ),
            "cumulative_return_minus_spy": evaluator._decimal_text(
                Decimal(signal_return) - Decimal("0.30")
            ),
            "annualized_arithmetic_return": signal_annual[cost],
            "annualized_volatility": "0.2",
            "zero_rate_sharpe": signal_sharpe,
            "zero_rate_sortino": "1",
            "maximum_drawdown": "-0.1",
            "average_daily_two_sided_turnover": "0.001",
            "average_cash_weight": "0.02",
            "matched_annualized_arithmetic_return": matched_annual[cost],
            "matched_annualized_volatility": "0.3",
            "matched_zero_rate_sharpe": matched_sharpe,
            "matched_zero_rate_sortino": "1",
            "matched_maximum_drawdown": "-0.15",
            "matched_average_daily_two_sided_turnover": "0.002",
            "matched_average_cash_weight": "0.02",
            "leverage": False,
            "orders_submitted": 0,
            "formal_accept_reject_disposition": None,
        }
        statistics[
            "ARV2_STOCK_PORTFOLIO_COST_" + str(cost)
        ] = _canonical(cell).decode("ascii")
        cells.append(cell)
    summary = {
        "schema": market_cap_evaluator.SUMMARY_SCHEMA,
        "contract_id": market_cap_evaluator.CONTRACT_ID,
        "profile": profile,
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "input_manifest_id": plan.evaluator_manifest_id,
        "input_manifest_sha256": plan.evaluator_manifest_sha256,
        "status": "PRELIMINARY_ACCEPTED_RISK_MARKET_CAP_STOCK_PORTFOLIO",
        "decision_session_count": decisions,
        "portfolio_return_session_count": returns,
        "mean_point_in_time_eligible_count": "1",
        "mean_eligible_score_count": "1",
        "mean_selected_name_count": "1",
        "eligible_without_R055_score_count": 0,
        "sector_refused_decision_count": 0,
        "named_figi_resolution_refusal_count": 0,
        "selected_aggregates": account,
        "matched_aggregates": matched_account,
        "r055_signal_rule_changed": False,
        "point_in_time_market_cap_weighting": True,
        "selected_and_matched_target_same_gross": True,
        "market_cap_values_in_summary": False,
        "raw_security_ids_in_summary": False,
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
    if tilt_profile:
        summary.update(
            {
                "analyst_revisions_role": (
                    "bounded_helper_overlay_not_an_admission_gate"
                ),
                "benchmark_logical_id": "SPY",
                "benchmark_history_normalization_mode": "total_return",
                "benchmark_history_observation": "session_open",
                "benchmark_first_used_session": "2021-01-05",
                "benchmark_last_used_session": "2025-12-31",
                "benchmark_observation_count": 1_254,
                "benchmark_return_interval_count": 1_253,
                "benchmark_raw_observation_sha256": "1" * 64,
                "benchmark_return_path_sha256": "2" * 64,
                "tilt_aggregates": {
                    "schema": market_cap_evaluator.TILT_AGGREGATES_SCHEMA,
                    "decision_session_count": decisions,
                    "tilt_enabled_decision_count": 0,
                    "tilt_underfilled_decision_count": decisions,
                    "minimum_ranked_nonzero_score_count": 1,
                    "minimum_positive_score_count": 1,
                    "minimum_negative_score_count": 0,
                    "minimum_tilted_name_count_when_enabled": 0,
                    "minimum_point_in_time_sector_count": 1,
                    "maximum_one_way_active_share": "0",
                    "maximum_overweight": "0",
                    "maximum_hhi_ratio_to_benchmark": "0",
                    "minimum_weight_ratio_to_benchmark_when_enabled": "0",
                    "maximum_weight_ratio_to_benchmark_when_enabled": "0",
                    "maximum_absolute_sector_active_weight": "0",
                    "underfilled_exact_benchmark": True,
                    "missing_or_zero_score_exact_benchmark": True,
                    "sector_mapping_exhaustive": True,
                    "sector_neutrality_exact": True,
                    "sector_neutrality_scope": "frozen_target",
                },
            }
        )
    digest = hashlib.sha256(_canonical(summary)).hexdigest()
    metadata = {
        **{
            key: value
            for key, value in summary.items()
            if key not in {"profile", "portfolio_cells"}
        },
        "profile_id": profile_id,
        "profile_sha256": profile["profile_sha256"],
        "summary_id": "arv2-market-cap-stock-summary-" + digest[:24],
        "summary_sha256": digest,
    }
    statistics[
        market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME
    ] = _canonical(metadata.pop("selected_aggregates")).decode("ascii")
    statistics[
        market_cap_evaluator.MATCHED_AGGREGATES_STATISTIC_NAME
    ] = _canonical(metadata.pop("matched_aggregates")).decode("ascii")
    if tilt_profile:
        statistics[
            market_cap_evaluator.TILT_AGGREGATES_STATISTIC_NAME
        ] = _canonical(metadata.pop("tilt_aggregates")).decode("ascii")
    statistics["ARV2_STOCK_PORTFOLIO_META"] = _canonical(metadata).decode(
        "ascii"
    )
    runtime_meta = {
        "schema": (
            "arv2-accepted-risk-market-cap-stock-portfolio-qc-runtime-meta-v1"
        ),
        "status": (
            "PRELIMINARY_ACCEPTED_RISK_MARKET_CAP_STOCK_PORTFOLIO_COMPLETED"
        ),
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "symbol_resolution_id": "resolution-one",
        "symbol_resolution_sha256": "e" * 64,
        "resolved_security_count": resolved,
        "named_security_refusal_count": 0,
        "evaluation_profile_id": profile_id,
        "evaluation_profile_sha256": profile["profile_sha256"],
        "runtime_slice_count": history_calls + 2,
        "point_in_time_history_call_count": history_calls,
        "point_in_time_fetched_source_row_count": decisions * 2,
        "point_in_time_eligible_score_bearing_count": decisions,
        "point_in_time_market_cap_covered_count": decisions,
        "point_in_time_market_cap_uncovered_count": 0,
        "result_transport": "aggregate_only_custom_summary_statistics",
        "host_object_store_export_required": False,
        "preliminary": True,
        "point_in_time": True,
        "formal": False,
        "control_residualized": False,
        "economic_portfolio": True,
        "etf_or_leverage": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    statistics["ARV2_RUNTIME_META"] = _canonical(runtime_meta).decode("ascii")
    assert tuple(sorted(statistics)) == plan.expected_custom_statistic_names
    assert all(0 < len(value) <= 4_096 for value in statistics.values())
    return statistics


def _leverage_aggregate_statistics(plan):
    profile_id = plan.projection.evaluation_profile_id
    profile = leverage_evaluator.require_profile(profile_id)
    base_profile = market_cap_evaluator.require_profile(
        profile["base_profile_id"]
    )
    decisions = base_profile["expected_decision_session_count"]
    returns = profile["expected_return_session_count"]
    resolved = plan.package.runtime_symbol_binding_count
    assert resolved == 1
    history_calls = 2 * (
        (
            decisions
            + market_cap_runtime.HISTORY_CHUNK_DECISION_COUNT
            - 1
        )
        // market_cap_runtime.HISTORY_CHUNK_DECISION_COUNT
    )
    account = {
        "rebalance_execution_count": decisions,
        "full_target_execution_count": decisions,
        "underfilled_target_execution_count": 0,
        "locked_exposure_over_target_count": 0,
        "mean_executed_gross_exposure": "0.98",
        "minimum_executed_gross_exposure": "0.98",
        "maximum_executed_gross_exposure": "0.98",
        "mean_maximum_position_weight": "0.98",
        "maximum_position_weight": "0.98",
        "mean_invested_weight_hhi": "1",
        "mean_effective_holding_count": "1",
        "average_holding_count": "1",
        "average_daily_two_sided_turnover": "0.001",
        "average_cash_weight": "0.02",
        "entry_price_refusal_count": 0,
        "stale_mark_session_count": 0,
        "partial_rebalance_decision_count": 0,
        "stale_position_deferral_count": 0,
        "selection_exit_deferral_count": 0,
        "eligibility_exit_liquidation_count": 0,
        "eligibility_exit_zero_recovery_count": 0,
    }
    matched_account = dict(account)
    matched_account["average_daily_two_sided_turnover"] = "0.002"
    path_values = {
        (2, True): (("0.28", "0.32"), ("0.18", "0.22"), ("0.38", "0.42")),
        (2, False): (("0.22", "0.30"), ("0.12", "0.20"), ("0.34", "0.42")),
        (3, True): (("0.45", "0.52"), ("0.32", "0.38"), ("0.65", "0.72")),
        (3, False): (("0.35", "0.48"), ("0.22", "0.34"), ("0.57", "0.72")),
    }
    annuals = {
        (2, True): ("0.10", "0.07", "0.12"),
        (2, False): ("0.08", "0.05", "0.10"),
        (3, True): ("0.15", "0.10", "0.18"),
        (3, False): ("0.11", "0.07", "0.14"),
    }
    volatilities = ("0.20", "0.25", "0.22")
    drawdowns = ("-0.20", "-0.25", "-0.22")
    cells = []
    statistics = {}
    for leverage_factor in leverage_evaluator.LEVERAGE_FACTORS:
        for scenario_id, rate, cost, primary in leverage_evaluator.SCENARIOS:
            cell = {
                "schema": leverage_evaluator.CELL_SCHEMA,
                "profile_id": profile_id,
                "base_profile_id": profile["base_profile_id"],
                "scenario_id": scenario_id,
                "primary_scenario": primary,
                "leverage_factor": leverage_factor,
                "annual_financing_rate": leverage_evaluator._decimal_text(rate),
                "underlying_cost_bps_per_side": cost,
                "underlying_cost_is_already_in_base_return": True,
                "second_transaction_cost_deduction": False,
                "status": "PRELIMINARY_DESCRIPTIVE_AVAILABLE",
                "return_session_count": returns,
            }
            values = path_values[(leverage_factor, primary)]
            for index, prefix in enumerate(
                ("selected_", "matched_", "synthetic_spy_")
            ):
                cumulative, before = map(Decimal, values[index])
                annual = Decimal(annuals[(leverage_factor, primary)][index])
                volatility = Decimal(volatilities[index])
                financing_count = returns - 1
                with evaluator.localcontext(evaluator._context()):
                    debit = +(
                        (Decimal(leverage_factor) - Decimal(1))
                        * rate
                        / Decimal(252)
                        * Decimal(financing_count)
                    )
                    drag = +(before - cumulative)
                    sharpe = +(annual / volatility)
                cell.update(
                    {
                        prefix + "cumulative_return": evaluator._decimal_text(cumulative),
                        prefix + "cumulative_return_before_financing": evaluator._decimal_text(before),
                        prefix + "cumulative_financing_drag": evaluator._decimal_text(drag),
                        prefix + "arithmetic_financing_debit": evaluator._decimal_text(debit),
                        prefix + "annualized_arithmetic_return": evaluator._decimal_text(annual),
                        prefix + "annualized_volatility": evaluator._decimal_text(volatility),
                        prefix + "zero_rate_sharpe": evaluator._decimal_text(sharpe),
                        prefix + "zero_rate_sortino": "1",
                        prefix + "maximum_drawdown": drawdowns[index],
                        prefix + "financing_session_count": financing_count,
                    }
                )
            with evaluator.localcontext(evaluator._context()):
                selected = Decimal(cell["selected_cumulative_return"])
                matched = Decimal(cell["matched_cumulative_return"])
                spy = Decimal(cell["synthetic_spy_cumulative_return"])
                selected_minus_matched = +(selected - matched)
                selected_minus_spy = +(selected - spy)
            cell.update(
                {
                    "selected_minus_matched_cumulative_return": evaluator._decimal_text(selected_minus_matched),
                    "selected_minus_synthetic_spy_cumulative_return": evaluator._decimal_text(selected_minus_spy),
                    "portfolio_level_daily_reset": True,
                    "synthetic_only": True,
                    "margin_calls_modeled": False,
                    "borrow_availability_modeled": False,
                    "security_level_financing_modeled": False,
                    "broker_liquidation_modeled": False,
                    "orders_submitted": 0,
                    "formal_accept_reject_disposition": None,
                }
            )
            suffix = "PRIMARY" if primary else "ADVERSE"
            statistics[
                "ARV2_LEVERAGE_L" + str(leverage_factor) + "_" + suffix
            ] = _canonical(cell).decode("ascii")
            cells.append(cell)
    summary = {
        "schema": leverage_evaluator.SUMMARY_SCHEMA,
        "contract_id": leverage_evaluator.CONTRACT_ID,
        "profile": profile,
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "input_manifest_id": plan.evaluator_manifest_id,
        "input_manifest_sha256": plan.evaluator_manifest_sha256,
        "status": "PRELIMINARY_OBJECTIVE_SYNTHETIC_LEVERAGE",
        "base_contract_id": market_cap_evaluator.CONTRACT_ID,
        "base_profile_id": profile["base_profile_id"],
        "base_profile_sha256": profile["base_profile_sha256"],
        "base_evaluator_source_sha256": leverage_evaluator.BASE_EVALUATOR_SOURCE_SHA256,
        "decision_session_count": decisions,
        "return_session_count": returns,
        "selected_base_aggregates": account,
        "matched_base_aggregates": matched_account,
        "r055_signal_rule_changed": False,
        "base_security_selection_changed": False,
        "point_in_time_membership_and_market_cap_weighting": True,
        "matched_comparator_levered_identically": True,
        "raw_security_ids_in_summary": False,
        "raw_price_rows_in_summary": False,
        "raw_provider_rows_in_summary": False,
        "synthetic_only": True,
        "formal_result": False,
        "alpha_claim_authorized": False,
        "evaluator_io": {
            "provider": False,
            "network": False,
            "object_store": False,
        },
        "margin_calls_modeled": False,
        "borrow_availability_modeled": False,
        "orders": False,
        "deployment": False,
        "trading": False,
        "cells": cells,
    }
    digest = hashlib.sha256(_canonical(summary)).hexdigest()
    metadata = {
        **{
            key: value
            for key, value in summary.items()
            if key not in {"profile", "cells"}
        },
        "profile_id": profile_id,
        "profile_sha256": profile["profile_sha256"],
        "summary_id": "arv2-objective-leverage-summary-" + digest[:24],
        "summary_sha256": digest,
    }
    statistics[
        leverage_evaluator.SELECTED_BASE_AGGREGATES_STATISTIC_NAME
    ] = _canonical(metadata.pop("selected_base_aggregates")).decode("ascii")
    statistics[
        leverage_evaluator.MATCHED_BASE_AGGREGATES_STATISTIC_NAME
    ] = _canonical(metadata.pop("matched_base_aggregates")).decode("ascii")
    statistics["ARV2_LEVERAGE_META"] = _canonical(metadata).decode("ascii")
    runtime_meta = {
        "schema": leverage_runtime.RUNTIME_META_SCHEMA,
        "status": leverage_runtime.RUNTIME_COMPLETED_STATUS,
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "symbol_resolution_id": "resolution-one",
        "symbol_resolution_sha256": "e" * 64,
        "resolved_security_count": resolved,
        "named_security_refusal_count": 0,
        "evaluation_profile_id": profile_id,
        "evaluation_profile_sha256": profile["profile_sha256"],
        "base_market_cap_profile_id": profile["base_profile_id"],
        "base_market_cap_profile_sha256": profile["base_profile_sha256"],
        "runtime_slice_count": history_calls + 2,
        "point_in_time_history_call_count": history_calls,
        "point_in_time_fetched_source_row_count": decisions * 2,
        "point_in_time_eligible_score_bearing_count": decisions,
        "point_in_time_market_cap_covered_count": decisions,
        "point_in_time_market_cap_uncovered_count": 0,
        "leverage_factors": [2, 3],
        "scenario_ids": [row[0] for row in leverage_evaluator.SCENARIOS],
        "result_transport": "aggregate_only_custom_summary_statistics",
        "host_object_store_export_required": False,
        "preliminary": True,
        "point_in_time": True,
        "formal": False,
        "control_residualized": False,
        "economic_portfolio": True,
        "etf_or_leverage": True,
        "synthetic_leverage": True,
        "margin_calls_modeled": False,
        "borrow_availability_modeled": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    statistics["ARV2_RUNTIME_META"] = _canonical(runtime_meta).decode("ascii")
    assert tuple(sorted(statistics)) == plan.expected_custom_statistic_names
    return statistics


def _six_universe_aggregate_statistics(plan):
    profile = six_universe_evaluator.require_profile(
        plan.evaluation_profile_id
    ).to_record()
    slot_count_per_sleeve = profile["slot_count_per_sleeve"]

    def account(role, salt):
        return {
            "schema": six_universe_evaluator.ACCOUNT_SCHEMA,
            "role": role,
            "cost_bps_per_side": 10,
            "cumulative_return": "0.1",
            "annualized_arithmetic_return": "0.02",
            "annualized_volatility": "0.1",
            "zero_rate_sharpe": "0.2",
            "maximum_drawdown": "-0.1",
            "average_daily_two_sided_turnover": "0.01",
            "annualized_two_sided_turnover": "2.52",
            "average_cash_weight": "0.02",
            "mean_holding_count": "10",
            "mean_target_effective_holdings": "9",
            "maximum_target_weight": "0.098",
            "return_session_count": 1_254,
            "invested_return_session_count": 1_253,
            "rebalance_count": 261,
            "full_target_count": 261,
            "underfilled_target_count": 0,
            "locked_over_target_count": 0,
            "entry_price_refusal_count": 0,
            "stale_mark_session_count": 0,
            "stale_position_deferral_count": 0,
            "eligibility_exit_zero_recovery_count": 0,
            "return_metric_conditioning": (
                "per_name_stale_mark_carry_and_eligibility_exit_zero_recovery"
            ),
            "equity_return_path_sha256": salt * 64,
            "raw_price_rows_in_output": False,
            "raw_security_ids_in_output": False,
        }

    signal = account("signal", "1")
    matched = account("matched", "2")
    basket = account("six_etf_basket", "3")
    basket.update(
        {
            "mean_holding_count": "6",
            "mean_target_effective_holdings": "6",
            "maximum_target_weight": "0.164",
        }
    )
    sleeves = {
        "schema": six_universe_evaluator.SLEEVE_SCHEMA,
        "universes": [
            {
                "universe_id": universe_id,
                "decision_count": 261,
                "coverage_valid_count": 261,
                "signal_full_etf_fallback_count": 0,
                "signal_partial_etf_fallback_count": 0,
                "matched_full_etf_fallback_count": 0,
                "mean_positive_score_count": "20",
                "mean_signal_stock_count": str(slot_count_per_sleeve),
                "mean_matched_stock_count": str(slot_count_per_sleeve),
                "minimum_mapping_ratio": "0.95",
                "minimum_cap_weight_coverage_ratio": "0.995",
            }
            for universe_id in six_universe_gate.UNIVERSE_IDS
        ],
    }
    series = {
        "schema": six_universe_evaluator.SERIES_SCHEMA,
        "series": [
            {
                "universe_id": universe_id,
                "normalization_mode": "TOTAL_RETURN",
                "observation": "session_open",
                "expected_session_count": 1_255,
                "observation_count": 1_255,
                "raw_observation_sha256": format(index + 4, "x") * 64,
                "used_return_path_sha256": format(index + 10, "x") * 64,
            }
            for index, universe_id in enumerate(six_universe_gate.UNIVERSE_IDS)
        ],
    }
    fragments = {
        "signal": signal,
        "matched": matched,
        "six_etf_basket": basket,
        "sleeves": sleeves,
        "series": series,
    }
    fragment_digest = hashlib.sha256(
        _canonical(
            {
                "schema": "arv2-six-universe-result-fragments-v1",
                **fragments,
            }
        )
    ).hexdigest()
    pit_calls = 308
    meta = {
        "schema": six_universe_evaluator.SUMMARY_SCHEMA,
        "status": "PRELIMINARY_ACCEPTED_RISK_SIX_UNIVERSE_GATE_COMPLETED",
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "gate_profile_id": profile["gate_profile_id"],
        "gate_profile_sha256": profile["gate_profile_sha256"],
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "input_manifest_id": plan.evaluator_manifest_id,
        "input_manifest_sha256": plan.evaluator_manifest_sha256,
        "symbol_resolution_id": "resolution-one",
        "symbol_resolution_sha256": "e" * 64,
        "construction_path_sha256": "f" * 64,
        "result_fragments_sha256": fragment_digest,
        "decision_session_count": 261,
        "price_history_batch_count": 1,
        "pit_history_call_count": pit_calls,
        "pit_source_row_count": 1_000,
        "analyst_source_view": six_universe_gate.SOURCE_VIEW_ID,
        "point_in_time_etf_membership_and_market_cap": True,
        "point_in_time_analyst_archive": False,
        "current_vintage_identity_basis": True,
        "aggregate_only": True,
        "raw_rows_in_output": False,
        "orders": False,
        "deployment": False,
        "trading": False,
    }
    digest = hashlib.sha256(
        _canonical({"profile": profile, "meta": meta, **fragments})
    ).hexdigest()
    meta["summary_id"] = "arv2-six-universe-summary-" + digest[:24]
    meta["summary_sha256"] = digest
    runtime = {
        "schema": "arv2-six-universe-qc-runtime-meta-v1",
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "symbol_resolution_id": "resolution-one",
        "symbol_resolution_sha256": "e" * 64,
        "runtime_slice_count": 160,
        "pit_history_call_count": pit_calls,
        "pit_source_row_count": 1_000,
        "price_history_call_count": 1,
        "result_transport": "aggregate_only_custom_summary_statistics",
        "host_object_store_export_required": False,
        "backtest_only": True,
        "orders": False,
        "deployment": False,
        "trading": False,
    }
    records = {
        six_universe_evaluator.META_STATISTIC_NAME: meta,
        six_universe_evaluator.SIGNAL_STATISTIC_NAME: signal,
        six_universe_evaluator.MATCHED_STATISTIC_NAME: matched,
        six_universe_evaluator.ETF_BASKET_STATISTIC_NAME: basket,
        six_universe_evaluator.SLEEVES_STATISTIC_NAME: sleeves,
        six_universe_evaluator.SERIES_STATISTIC_NAME: series,
        six_universe_runtime.RUNTIME_META_STATISTIC_NAME: runtime,
    }
    statistics = {
        name: _canonical(value).decode("ascii")
        for name, value in records.items()
    }
    assert tuple(sorted(statistics)) == plan.expected_custom_statistic_names
    return statistics


def _rehash_six_universe_summary(plan, statistics):
    metadata = json.loads(
        statistics[six_universe_evaluator.META_STATISTIC_NAME]
    )
    profile = six_universe_evaluator.require_profile(
        plan.evaluation_profile_id
    ).to_record()
    fragments = {
        "signal": json.loads(statistics[six_universe_evaluator.SIGNAL_STATISTIC_NAME]),
        "matched": json.loads(statistics[six_universe_evaluator.MATCHED_STATISTIC_NAME]),
        "six_etf_basket": json.loads(
            statistics[six_universe_evaluator.ETF_BASKET_STATISTIC_NAME]
        ),
        "sleeves": json.loads(statistics[six_universe_evaluator.SLEEVES_STATISTIC_NAME]),
        "series": json.loads(statistics[six_universe_evaluator.SERIES_STATISTIC_NAME]),
    }
    fragment_digest = hashlib.sha256(
        _canonical(
            {
                "schema": "arv2-six-universe-result-fragments-v1",
                **fragments,
            }
        )
    ).hexdigest()
    metadata["result_fragments_sha256"] = fragment_digest
    summary_meta = {
        key: value
        for key, value in metadata.items()
        if key not in {"summary_id", "summary_sha256"}
    }
    digest = hashlib.sha256(
        _canonical({"profile": profile, "meta": summary_meta, **fragments})
    ).hexdigest()
    metadata["summary_id"] = "arv2-six-universe-summary-" + digest[:24]
    metadata["summary_sha256"] = digest
    statistics[six_universe_evaluator.META_STATISTIC_NAME] = _canonical(
        metadata
    ).decode("ascii")


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
        metadata["profile_id"]
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


def _rehash_market_cap_summary(statistics):
    metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
    profile = market_cap_evaluator.require_market_cap_stock_portfolio_profile(
        metadata["profile_id"]
    )
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
    summary["profile"] = profile
    summary["selected_aggregates"] = json.loads(
        statistics[
            market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME
        ]
    )
    summary["matched_aggregates"] = json.loads(
        statistics[
            market_cap_evaluator.MATCHED_AGGREGATES_STATISTIC_NAME
        ]
    )
    if metadata["profile_id"] in market_cap_evaluator.TILT_PROFILE_IDS:
        summary["tilt_aggregates"] = json.loads(
            statistics[market_cap_evaluator.TILT_AGGREGATES_STATISTIC_NAME]
        )
    summary["portfolio_cells"] = [
        json.loads(statistics["ARV2_STOCK_PORTFOLIO_COST_" + str(cost)])
        for cost in market_cap_evaluator.COST_BPS_SCENARIOS
    ]
    digest = hashlib.sha256(_canonical(summary)).hexdigest()
    metadata["summary_id"] = "arv2-market-cap-stock-summary-" + digest[:24]
    metadata["summary_sha256"] = digest
    statistics["ARV2_STOCK_PORTFOLIO_META"] = _canonical(metadata).decode(
        "ascii"
    )


def _rehash_leverage_summary(statistics):
    metadata = json.loads(statistics["ARV2_LEVERAGE_META"])
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
    summary["profile"] = leverage_evaluator.require_profile(
        metadata["profile_id"]
    )
    summary["selected_base_aggregates"] = json.loads(
        statistics[
            leverage_evaluator.SELECTED_BASE_AGGREGATES_STATISTIC_NAME
        ]
    )
    summary["matched_base_aggregates"] = json.loads(
        statistics[
            leverage_evaluator.MATCHED_BASE_AGGREGATES_STATISTIC_NAME
        ]
    )
    summary["cells"] = [
        json.loads(
            statistics[
                "ARV2_LEVERAGE_L"
                + str(leverage_factor)
                + "_"
                + ("PRIMARY" if primary else "ADVERSE")
            ]
        )
        for leverage_factor in leverage_evaluator.LEVERAGE_FACTORS
        for _scenario_id, _rate, _cost, primary in leverage_evaluator.SCENARIOS
    ]
    digest = hashlib.sha256(_canonical(summary)).hexdigest()
    metadata["summary_id"] = (
        "arv2-objective-leverage-summary-" + digest[:24]
    )
    metadata["summary_sha256"] = digest
    statistics["ARV2_LEVERAGE_META"] = _canonical(metadata).decode("ascii")


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

_STOCK_UNIVERSE_ACCOUNTING = {
    stock_portfolio_evaluator.SP500_PROFILE_ID: (
        "arv2-eval-stock-spy-holdings-intersection-qc-011",
        "R-072",
        69,
        70,
        16,
        17,
        579,
        583,
    ),
    stock_portfolio_evaluator.NASDAQ100_MEMBERSHIP_ONLY_PROFILE_ID: (
        "arv2-eval-stock-qqq-holdings-intersection-qc-016",
        "R-077",
        72,
        73,
        19,
        20,
        583,
        587,
    ),
    stock_portfolio_evaluator.UNION_MEMBERSHIP_ONLY_PROFILE_ID: (
        "arv2-eval-stock-spy-qqq-intersection-union-qc-017",
        "R-078",
        73,
        74,
        20,
        21,
        587,
        591,
    ),
}

_MARKET_CAP_ACCOUNTING = {
    market_cap_evaluator.QQQ_2021_2025_V2_PROFILE_ID: (
        "R-107", 81, 82, 24, 25, 591, 595
    ),
    market_cap_evaluator.SPY_2021_2025_V2_PROFILE_ID: (
        "R-108", 82, 83, 25, 26, 595, 599
    ),
    market_cap_evaluator.QQQ_2019_2023_V2_PROFILE_ID: (
        "R-109", 83, 84, 26, 27, 599, 603
    ),
    market_cap_evaluator.SPY_2019_2023_V2_PROFILE_ID: (
        "R-110", 84, 85, 27, 28, 603, 607
    ),
    market_cap_evaluator.QQQ_2023_2025_V2_PROFILE_ID: (
        "R-111", 85, 86, 28, 29, 607, 611
    ),
    market_cap_evaluator.SPY_2023_2025_V2_PROFILE_ID: (
        "R-112", 86, 87, 29, 30, 611, 615
    ),
    market_cap_evaluator.QQQ_2021_2025_V3_PROFILE_ID: (
        "R-115", 83, 84, 26, 27, 599, 603
    ),
    market_cap_evaluator.SPY_2021_2025_V3_PROFILE_ID: (
        "R-116", 84, 85, 27, 28, 603, 607
    ),
    market_cap_evaluator.QQQ_2021_2025_V4_PROFILE_ID: (
        "R-117", 84, 85, 27, 28, 599, 603
    ),
    market_cap_evaluator.SPY_2021_2025_V4_PROFILE_ID: (
        "R-118", 85, 86, 28, 29, 603, 607
    ),
}

_LEVERAGE_ACCOUNTING = {
    leverage_evaluator.QQQ_2021_2025_V3_PROFILE_ID: (
        "R-113", 87, 88, 30, 31, 615, 619
    ),
    leverage_evaluator.SPY_2021_2025_V3_PROFILE_ID: (
        "R-114", 88, 89, 31, 32, 619, 623
    ),
}


def test_each_market_cap_profile_has_exact_run_spec_and_result_inventory(
    market_cap_plan,
):
    profile_id = market_cap_plan.evaluation_profile_id
    expected = _MARKET_CAP_ACCOUNTING[profile_id]
    spec = adapter._run_spec(profile_id)
    reservation = adapter._look_accounting(evaluation_profile_id=profile_id)
    result = adapter._look_accounting(
        stage="result", evaluation_profile_id=profile_id
    )
    profile = market_cap_evaluator.require_market_cap_stock_portfolio_profile(
        profile_id
    )

    assert spec.ledger_entry_id == expected[0]
    assert spec.cell_count == 4
    assert reservation["run_level_looks_before"] == expected[1]
    assert reservation["planned_run_level_looks_after_launch"] == expected[2]
    assert reservation["arv2_development_evaluations_before"] == expected[3]
    assert reservation[
        "planned_arv2_development_evaluations_after_launch"
    ] == expected[4]
    assert reservation["lifetime_alpha_cell_floor_before"] == expected[5]
    assert result["lifetime_alpha_cell_floor_after"] == expected[6]
    assert market_cap_plan.evaluation_profile_sha256 == profile[
        "profile_sha256"
    ]
    assert profile["sector_neutral_execution_rule"] == (
        "execute_each_tradable_name_at_its_exact_frozen_target_preserve_"
        "each_locked_weight_never_redistribute_missing_or_locked_budget_"
        "and_count_sector_target_underfill_for_missing_or_below_frozen_"
        "locks_or_sector_gross_under_and_locked_sector_over_target_for_"
        "above_frozen_locks_or_sector_gross_over"
    )
    assert profile["portfolio_weight_quantum"] == format(
        market_cap_evaluator.PORTFOLIO_WEIGHT_QUANTUM,
        "f",
    )
    assert profile["sector_mapping_rule"].startswith(
        "exact_membership_sector_for_mapped_names"
    )
    assert profile["sector_mapping_rule"].endswith(
        "cannot_donate_or_receive_scored_unmapped_refuses"
    )
    assert market_cap_plan.expected_custom_statistic_names == (
        "ARV2_RUNTIME_META",
        "ARV2_STOCK_PORTFOLIO_COST_0",
        "ARV2_STOCK_PORTFOLIO_COST_10",
        "ARV2_STOCK_PORTFOLIO_COST_20",
        "ARV2_STOCK_PORTFOLIO_COST_5",
        "ARV2_STOCK_PORTFOLIO_MATCHED_AGGREGATES",
        "ARV2_STOCK_PORTFOLIO_META",
        "ARV2_STOCK_PORTFOLIO_SELECTED_AGGREGATES",
        "ARV2_STOCK_PORTFOLIO_TILT_AGGREGATES",
    )
    assert tuple(item.project_path for item in market_cap_plan.source_files) == (
        tuple(
            sorted(
                projection_builder.MARKET_CAP_PROJECT_SOURCE_PATHS
                + ("main.py",)
            )
        )
    )


def test_each_market_cap_profile_accepts_exact_bounded_aggregate(
    market_cap_plan,
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan)
    _validate_statistics(market_cap_plan, statistics)


def test_r107_r108_historical_market_cap_result_read_path_remains_exact(
    spent_market_cap_plan,
):
    assert all(
        item.project_path
        != "accepted_risk_market_cap_stock_portfolio_tilt.py"
        for item in spent_market_cap_plan.source_files
    )
    assert adapter.require_accepted_risk_preliminary_submission_plan(
        spent_market_cap_plan
    ) is spent_market_cap_plan
    assert len(spent_market_cap_plan.expected_custom_statistic_names) == 8
    assert (
        market_cap_evaluator.TILT_AGGREGATES_STATISTIC_NAME
        not in spent_market_cap_plan.expected_custom_statistic_names
    )
    historical = _market_cap_aggregate_statistics(spent_market_cap_plan)
    for statistic_name in (
        market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME,
        market_cap_evaluator.MATCHED_AGGREGATES_STATISTIC_NAME,
    ):
        account = json.loads(historical[statistic_name])
        assert "locked_sector_over_target_count" not in account
        assert "sector_target_underfill_count" not in account
    _validate_statistics(
        spent_market_cap_plan,
        historical,
    )


def test_market_cap_tilt_statistic_is_required(market_cap_plan):
    statistics = _market_cap_aggregate_statistics(market_cap_plan)
    statistics.pop(market_cap_evaluator.TILT_AGGREGATES_STATISTIC_NAME)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="aggregate result inventory changed",
    ):
        _validate_statistics(market_cap_plan, statistics)


def test_market_cap_tilt_fields_are_exact(market_cap_plan):
    statistics = _market_cap_aggregate_statistics(market_cap_plan)
    tilt = json.loads(
        statistics[market_cap_evaluator.TILT_AGGREGATES_STATISTIC_NAME]
    )
    tilt["unexpected"] = 0
    statistics[
        market_cap_evaluator.TILT_AGGREGATES_STATISTIC_NAME
    ] = _canonical(tilt).decode("ascii")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="tilt aggregate fields changed",
    ):
        _validate_statistics(market_cap_plan, statistics)


def test_market_cap_rehashed_tilt_count_tampering_is_refused(
    market_cap_plan,
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan)
    name = market_cap_evaluator.TILT_AGGREGATES_STATISTIC_NAME
    tilt = json.loads(statistics[name])
    tilt["tilt_underfilled_decision_count"] -= 1
    statistics[name] = _canonical(tilt).decode("ascii")
    _rehash_market_cap_summary(statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="tilt aggregate count semantics changed",
    ):
        _validate_statistics(market_cap_plan, statistics)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        (
            "sector_neutrality_exact",
            False,
            "tilt aggregate count semantics changed",
        ),
        (
            "sector_mapping_exhaustive",
            False,
            "tilt aggregate count semantics changed",
        ),
        (
            "sector_neutrality_scope",
            "executed_portfolio",
            "tilt aggregate count semantics changed",
        ),
        (
            "maximum_absolute_sector_active_weight",
            "0.0001",
            "tilt fallback metrics changed",
        ),
    ),
)
def test_market_cap_rehashed_sector_neutrality_tampering_is_refused(
    market_cap_plan, field, value, message
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan)
    name = market_cap_evaluator.TILT_AGGREGATES_STATISTIC_NAME
    tilt = json.loads(statistics[name])
    tilt[field] = value
    statistics[name] = _canonical(tilt).decode("ascii")
    _rehash_market_cap_summary(statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match=message,
    ):
        _validate_statistics(market_cap_plan, statistics)


def test_market_cap_enabled_tilt_cap_tampering_is_refused_in_isolation():
    value = {
        "schema": market_cap_evaluator.TILT_AGGREGATES_SCHEMA,
        "decision_session_count": 1,
        "tilt_enabled_decision_count": 1,
        "tilt_underfilled_decision_count": 0,
        "minimum_ranked_nonzero_score_count": 40,
        "minimum_positive_score_count": 20,
        "minimum_negative_score_count": 20,
        "minimum_tilted_name_count_when_enabled": 40,
        "minimum_point_in_time_sector_count": 2,
        "maximum_one_way_active_share": "0.0491",
        "maximum_overweight": "0.0049",
        "maximum_hhi_ratio_to_benchmark": "1.1",
        "minimum_weight_ratio_to_benchmark_when_enabled": "0.8",
        "maximum_weight_ratio_to_benchmark_when_enabled": "1.2",
        "maximum_absolute_sector_active_weight": "0",
        "underfilled_exact_benchmark": True,
        "missing_or_zero_score_exact_benchmark": True,
        "sector_mapping_exhaustive": True,
        "sector_neutrality_exact": True,
        "sector_neutrality_scope": "frozen_target",
    }

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="tilt aggregate metric escaped bounds",
    ):
        adapter._validate_market_cap_tilt_aggregate(
            value,
            decision_count=1,
            runtime_security_count=40,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        (
            "benchmark_raw_observation_sha256",
            "not-a-digest",
            "is not an exact SHA-256",
        ),
        (
            "benchmark_observation_count",
            1_253,
            "aggregate metadata semantics changed",
        ),
        (
            "benchmark_first_used_session",
            "2021-01-04",
            "aggregate metadata semantics changed",
        ),
        (
            "benchmark_last_used_session",
            "2025-12-30",
            "aggregate metadata semantics changed",
        ),
    ),
)
def test_market_cap_benchmark_lineage_guards_are_isolated(
    market_cap_plan, field, value, message
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan)
    metadata = json.loads(statistics[market_cap_evaluator.META_STATISTIC_NAME])
    metadata[field] = value
    statistics[market_cap_evaluator.META_STATISTIC_NAME] = _canonical(
        metadata
    ).decode("ascii")
    _rehash_market_cap_summary(statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match=message,
    ):
        _validate_statistics(market_cap_plan, statistics)


def test_market_cap_benchmark_digest_is_bound_by_summary_identity(
    market_cap_plan,
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan)
    metadata = json.loads(statistics[market_cap_evaluator.META_STATISTIC_NAME])
    metadata["benchmark_return_path_sha256"] = "3" * 64
    statistics[market_cap_evaluator.META_STATISTIC_NAME] = _canonical(
        metadata
    ).decode("ascii")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="summary identity changed",
    ):
        _validate_statistics(market_cap_plan, statistics)


def test_market_cap_benchmark_lineage_field_is_required(market_cap_plan):
    statistics = _market_cap_aggregate_statistics(market_cap_plan)
    metadata = json.loads(statistics[market_cap_evaluator.META_STATISTIC_NAME])
    del metadata["benchmark_raw_observation_sha256"]
    statistics[market_cap_evaluator.META_STATISTIC_NAME] = _canonical(
        metadata
    ).decode("ascii")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="aggregate metadata changed",
    ):
        _validate_statistics(market_cap_plan, statistics)


def test_market_cap_v3_selected_breadth_is_not_capped_at_fifty():
    value = {
        "rebalance_execution_count": 1,
        "full_target_execution_count": 1,
        "underfilled_target_execution_count": 0,
        "locked_exposure_over_target_count": 0,
        "mean_executed_gross_exposure": "0.98",
        "minimum_executed_gross_exposure": "0.98",
        "maximum_executed_gross_exposure": "0.98",
        "mean_maximum_position_weight": "0.02",
        "maximum_position_weight": "0.02",
        "mean_invested_weight_hhi": "0.02",
        "mean_effective_holding_count": "51",
        "average_holding_count": "51",
        "average_daily_two_sided_turnover": "0.001",
        "average_cash_weight": "0.02",
        "entry_price_refusal_count": 0,
        "stale_mark_session_count": 0,
        "partial_rebalance_decision_count": 0,
        "stale_position_deferral_count": 0,
        "selection_exit_deferral_count": 0,
        "eligibility_exit_liquidation_count": 0,
        "eligibility_exit_zero_recovery_count": 0,
    }
    adapter._validate_market_cap_account_aggregate(
        value,
        role="selected",
        decision_count=1,
        return_count=1,
        runtime_security_count=60,
        selected_full_universe=True,
    )
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="account metric escaped bounds",
    ):
        adapter._validate_market_cap_account_aggregate(
            value,
            role="selected",
            decision_count=1,
            return_count=1,
            runtime_security_count=60,
            selected_full_universe=False,
        )


@pytest.mark.parametrize(
    "statistic_name",
    (
        market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME,
        market_cap_evaluator.MATCHED_AGGREGATES_STATISTIC_NAME,
    ),
)
def test_market_cap_split_account_statistic_is_required(
    market_cap_plan_2021, statistic_name
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan_2021)
    statistics.pop(statistic_name)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="aggregate result inventory changed",
    ):
        _validate_statistics(market_cap_plan_2021, statistics)


def test_market_cap_split_account_fields_are_exact(market_cap_plan_2021):
    statistics = _market_cap_aggregate_statistics(market_cap_plan_2021)
    selected = json.loads(
        statistics[market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME]
    )
    selected["unexpected"] = 0
    statistics[
        market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME
    ] = _canonical(selected).decode("ascii")
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="account aggregate fields changed",
    ):
        _validate_statistics(market_cap_plan_2021, statistics)


@pytest.mark.parametrize(
    "statistic_name",
    (
        market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME,
        market_cap_evaluator.MATCHED_AGGREGATES_STATISTIC_NAME,
    ),
)
def test_market_cap_v3_sector_execution_counters_are_required(
    market_cap_plan, statistic_name
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan)
    account = json.loads(statistics[statistic_name])
    del account["sector_target_underfill_count"]
    statistics[statistic_name] = _canonical(account).decode("ascii")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="account aggregate fields changed",
    ):
        _validate_statistics(market_cap_plan, statistics)


@pytest.mark.parametrize(
    "field",
    ("locked_sector_over_target_count", "sector_target_underfill_count"),
)
def test_market_cap_v3_sector_execution_counter_bounds_are_enforced(
    market_cap_plan, field
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan)
    name = market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME
    account = json.loads(statistics[name])
    account[field] = (
        market_cap_evaluator.require_market_cap_stock_portfolio_profile(
            market_cap_plan.evaluation_profile_id
        )["expected_decision_session_count"]
        * market_cap_plan.package.runtime_symbol_binding_count
        + 1
    )
    statistics[name] = _canonical(account).decode("ascii")
    _rehash_market_cap_summary(statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="account count semantics changed",
    ):
        _validate_statistics(market_cap_plan, statistics)


def test_market_cap_v3_sector_under_and_over_counts_may_cooccur(
    market_cap_plan,
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan)
    for name in (
        market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME,
        market_cap_evaluator.MATCHED_AGGREGATES_STATISTIC_NAME,
    ):
        account = json.loads(statistics[name])
        account["locked_sector_over_target_count"] = 1
        account["sector_target_underfill_count"] = 1
        statistics[name] = _canonical(account).decode("ascii")
    _rehash_market_cap_summary(statistics)

    _validate_statistics(market_cap_plan, statistics)


def test_market_cap_unrehashened_split_account_mutation_refuses_identity(
    market_cap_plan_2021,
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan_2021)
    selected = json.loads(
        statistics[market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME]
    )
    selected["maximum_position_weight"] = "0.99"
    statistics[
        market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME
    ] = _canonical(selected).decode("ascii")
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="summary identity changed",
    ):
        _validate_statistics(market_cap_plan_2021, statistics)


def test_market_cap_census_accepts_context_rounded_nonterminating_mean(
    market_cap_plan_2021,
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan_2021)
    metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
    decisions = metadata["decision_session_count"]
    with evaluator.localcontext(evaluator._context()):
        metadata["mean_selected_name_count"] = evaluator._decimal_text(
            +(Decimal(130) / Decimal(decisions))
        )
    statistics["ARV2_STOCK_PORTFOLIO_META"] = _canonical(metadata).decode(
        "ascii"
    )
    _rehash_market_cap_summary(statistics)

    _validate_statistics(market_cap_plan_2021, statistics)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("point_in_time_history_call_count", 1, "runtime metadata changed"),
        (
            "point_in_time_fetched_source_row_count",
            market_cap_runtime.MAX_TOTAL_SOURCE_ROWS + 1,
            "runtime metadata changed",
        ),
        (
            "point_in_time_market_cap_uncovered_count",
            1,
            "runtime metadata changed",
        ),
    ),
)
def test_market_cap_runtime_count_guards_are_isolated(
    market_cap_plan_2021, field, value, message
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan_2021)
    runtime_meta = json.loads(statistics["ARV2_RUNTIME_META"])
    runtime_meta[field] = value
    statistics["ARV2_RUNTIME_META"] = _canonical(runtime_meta).decode("ascii")
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match=message,
    ):
        _validate_statistics(market_cap_plan_2021, statistics)


@pytest.mark.parametrize(
    ("account_name", "field", "value", "message"),
    (
        (
            "selected_aggregates",
            "mean_invested_weight_hhi",
            "1.1",
            "account metric escaped bounds",
        ),
        (
            "selected_aggregates",
            "mean_effective_holding_count",
            "51",
            "account metric escaped bounds",
        ),
        (
            "matched_aggregates",
            "selection_exit_deferral_count",
            1,
            "account count semantics changed",
        ),
    ),
)
def test_market_cap_account_guards_refuse_rehashed_mutations(
    market_cap_plan_2021, account_name, field, value, message
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan_2021)
    statistic_name = {
        "selected_aggregates": (
            market_cap_evaluator.SELECTED_AGGREGATES_STATISTIC_NAME
        ),
        "matched_aggregates": (
            market_cap_evaluator.MATCHED_AGGREGATES_STATISTIC_NAME
        ),
    }[account_name]
    account = json.loads(statistics[statistic_name])
    account[field] = value
    statistics[statistic_name] = _canonical(account).decode("ascii")
    _rehash_market_cap_summary(statistics)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match=message,
    ):
        _validate_statistics(market_cap_plan_2021, statistics)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("difference", "portfolio metric escaped bounds"),
        ("annual_cost", "cost arithmetic changed"),
        ("nonmonotone", "cost monotonicity changed"),
        ("path", "cost path invariance changed"),
        ("sortino", "portfolio metric escaped bounds"),
    ),
)
def test_market_cap_cell_arithmetic_and_path_guards_are_isolated(
    market_cap_plan_2021, mutation, message
):
    statistics = _market_cap_aggregate_statistics(market_cap_plan_2021)
    name = "ARV2_STOCK_PORTFOLIO_COST_20"
    cell = json.loads(statistics[name])
    if mutation == "difference":
        cell["cumulative_return_minus_spy"] = "0"
    elif mutation == "annual_cost":
        cell["annualized_arithmetic_return"] = "0.099"
        cell["zero_rate_sharpe"] = "0.495"
    elif mutation == "nonmonotone":
        cell["cumulative_return"] = "0.21"
        cell["cumulative_return_minus_matched"] = "0.15"
        cell["cumulative_return_minus_spy"] = "-0.09"
    elif mutation == "path":
        cell["average_cash_weight"] = "0.03"
    else:
        cell["zero_rate_sortino"] = "-1"
    statistics[name] = _canonical(cell).decode("ascii")
    _rehash_market_cap_summary(statistics)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match=message,
    ):
        _validate_statistics(market_cap_plan_2021, statistics)


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("MINIMUM_INVESTED_RETURN_SESSIONS", 0),
        ("COST_BPS_SCENARIOS", (10,)),
        ("TARGET_GROSS_EXPOSURE", Decimal("1")),
        ("PORTFOLIO_WEIGHT_QUANTUM", Decimal("1e-30")),
        ("META_STATISTIC_NAME", "ARV2_MUTATED_META"),
        (
            "SELECTED_AGGREGATES_STATISTIC_NAME",
            "ARV2_MUTATED_SELECTED",
        ),
        (
            "MATCHED_AGGREGATES_STATISTIC_NAME",
            "ARV2_MUTATED_MATCHED",
        ),
    ),
)
def test_market_cap_contract_mutation_refuses_before_network(
    market_cap_plan_2021, monkeypatch, name, value
):
    backend = _Backend(market_cap_plan_2021)
    monkeypatch.setattr(market_cap_evaluator, name, value)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=market_cap_plan_2021,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-17T20:00:00Z",
        )
    assert backend.events == []
    assert not any(market_cap_plan_2021.control_directory.iterdir())


@pytest.mark.parametrize("profile_id", leverage_evaluator.PROFILE_IDS)
def test_superseded_leverage_profiles_remain_loadable_with_frozen_identity(
    profile_id,
):
    profile = leverage_evaluator.require_profile(profile_id)
    spec = adapter._run_spec(profile_id)

    assert profile["profile_id"] == profile_id
    assert profile["profile_sha256"] == (
        projection_builder.OBJECTIVE_LEVERAGE_PROFILE_SHA256S[profile_id]
    )
    assert profile["base_evaluator_source_sha256"] == (
        leverage_evaluator.BASE_EVALUATOR_SOURCE_SHA256
    )
    assert spec.ledger_entry_id in {"R-113", "R-114"}
    assert leverage_evaluator.expected_custom_summary_statistic_names(
        profile_id
    ) == tuple(
        sorted(
            (
                "ARV2_LEVERAGE_L2_ADVERSE",
                "ARV2_LEVERAGE_L2_PRIMARY",
                "ARV2_LEVERAGE_L3_ADVERSE",
                "ARV2_LEVERAGE_L3_PRIMARY",
                "ARV2_LEVERAGE_MATCHED_BASE_AGGREGATES",
                "ARV2_LEVERAGE_META",
                "ARV2_LEVERAGE_SELECTED_BASE_AGGREGATES",
            )
        )
    )


def test_regime_profile_allowlist_refuses_unknown_profile():
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="evaluation profile is not allowlisted",
    ):
        adapter._look_accounting(evaluation_profile_id="arv2-stock-ic-unregistered")


@pytest.mark.parametrize(
    "profile_id",
    (
        stock_portfolio_evaluator.NASDAQ100_PROFILE_ID,
        stock_portfolio_evaluator.UNION_PROFILE_ID,
        stock_portfolio_evaluator.NASDAQ100_STATE_UNTIL_SUPERSEDED_PROFILE_ID,
        stock_portfolio_evaluator.UNION_STATE_UNTIL_SUPERSEDED_PROFILE_ID,
    ),
)
def test_superseded_stock_universe_profiles_are_not_active_run_specs(
    profile_id,
):
    # R073 and R075 were spent failures; R074 and R076 were unspent.  All four
    # remain loadable but cannot create a fresh submission after supersession.
    stock_portfolio_evaluator.require_stock_portfolio_profile(profile_id)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="evaluation profile is not allowlisted",
    ):
        adapter._run_spec(profile_id)


def test_stock_portfolio_profile_has_one_exact_r065_look_budget(stock_portfolio_plan):
    spec = adapter._run_spec(stock_portfolio_evaluator.PROFILE_ID)
    accounting = adapter._look_accounting(
        evaluation_profile_id=stock_portfolio_evaluator.PROFILE_ID
    )
    result_accounting = adapter._look_accounting(
        stage="result",
        evaluation_profile_id=stock_portfolio_evaluator.PROFILE_ID,
    )

    assert spec.ledger_entry_id == "R-065"
    assert spec.cell_count == 4
    assert accounting["run_level_looks_before"] == 64
    assert accounting["planned_run_level_looks_after_launch"] == 65
    assert accounting["arv2_development_evaluations_before"] == 11
    assert accounting["planned_arv2_development_evaluations_after_launch"] == 12
    assert accounting["lifetime_alpha_cell_floor_before"] == 575
    assert result_accounting["lifetime_alpha_cell_floor_after"] == 579
    assert stock_portfolio_plan.expected_custom_statistic_names == (
        "ARV2_RUNTIME_META",
        "ARV2_STOCK_PORTFOLIO_COST_0",
        "ARV2_STOCK_PORTFOLIO_COST_10",
        "ARV2_STOCK_PORTFOLIO_COST_20",
        "ARV2_STOCK_PORTFOLIO_COST_5",
        "ARV2_STOCK_PORTFOLIO_META",
    )


def test_each_stock_universe_profile_has_its_exact_four_cell_run_spec(
    stock_universe_plan,
):
    profile_id = stock_universe_plan.projection.evaluation_profile_id
    (
        evaluation_id,
        ledger_entry_id,
        looks_before,
        looks_after,
        evaluations_before,
        evaluations_after,
        floor_before,
        floor_after,
    ) = _STOCK_UNIVERSE_ACCOUNTING[profile_id]
    spec = adapter._run_spec(profile_id)
    reservation = adapter._look_accounting(evaluation_profile_id=profile_id)
    result = adapter._look_accounting(
        stage="result", evaluation_profile_id=profile_id
    )
    profile = stock_portfolio_evaluator.require_stock_portfolio_profile(
        profile_id
    )

    assert spec.evaluation_id == evaluation_id
    assert spec.ledger_entry_id == ledger_entry_id
    assert spec.cell_count == 4
    assert reservation["run_level_looks_before"] == looks_before
    assert reservation["planned_run_level_looks_after_launch"] == looks_after
    assert reservation["arv2_development_evaluations_before"] == (
        evaluations_before
    )
    assert reservation[
        "planned_arv2_development_evaluations_after_launch"
    ] == evaluations_after
    assert reservation["lifetime_alpha_cell_floor_before"] == floor_before
    assert result["lifetime_alpha_cell_floor_after"] == floor_after
    assert stock_universe_plan.evaluation_profile_id == profile_id
    assert stock_universe_plan.evaluation_profile_sha256 == profile[
        "profile_sha256"
    ]
    assert stock_universe_plan.expected_custom_statistic_names == (
        "ARV2_RUNTIME_META",
        "ARV2_STOCK_PORTFOLIO_COST_0",
        "ARV2_STOCK_PORTFOLIO_COST_10",
        "ARV2_STOCK_PORTFOLIO_COST_20",
        "ARV2_STOCK_PORTFOLIO_COST_5",
        "ARV2_STOCK_PORTFOLIO_META",
    )
    assert tuple(
        item.project_path for item in stock_universe_plan.source_files
    ) == tuple(
        sorted(
            projection_builder.STOCK_PORTFOLIO_PROJECT_SOURCE_PATHS
            + ("main.py",)
        )
    )


@pytest.mark.parametrize(
    "profile_id",
    (
        "arv2-stock-long-only-spy-holdings-proxy-2021-2025-r066-v1",
        "arv2-stock-long-only-qqq-holdings-proxy-2021-2025-r067-v1",
        "arv2-stock-long-only-spy-qqq-union-2021-2025-r068-v1",
        "arv2-stock-long-only-spy-holdings-proxy-2021-2025-r069-v1",
        "arv2-stock-long-only-qqq-holdings-intersection-2021-2025-r067-v2",
        "arv2-stock-long-only-spy-qqq-intersection-union-2021-2025-r068-v2",
        "arv2-stock-long-only-spy-holdings-intersection-2021-2025-r069-v1",
        "arv2-stock-long-only-qqq-holdings-intersection-2021-2025-r070-v3",
        "arv2-stock-long-only-spy-holdings-intersection-2021-2025-r069-v2",
        "arv2-stock-long-only-qqq-holdings-intersection-2021-2025-r070-v4",
        "arv2-stock-long-only-spy-qqq-intersection-union-2021-2025-r071-v3",
    ),
)
def test_stock_shaped_profile_outside_exact_active_allowlist_refuses(profile_id):
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="evaluation profile is not allowlisted",
    ):
        adapter._run_spec(profile_id)


def test_each_stock_universe_result_binds_exact_profile_and_hash(
    stock_universe_plan,
):
    statistics = _stock_portfolio_aggregate_statistics(stock_universe_plan)
    profile_id = stock_universe_plan.evaluation_profile_id
    profile = stock_portfolio_evaluator.require_stock_portfolio_profile(
        profile_id
    )

    _validate_statistics(stock_universe_plan, statistics)

    runtime_meta = json.loads(statistics["ARV2_RUNTIME_META"])
    metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
    cells = {
        json.loads(statistics[name])["profile_id"]
        for name in statistics
        if name.startswith("ARV2_STOCK_PORTFOLIO_COST_")
    }
    assert runtime_meta["evaluation_profile_id"] == profile_id
    assert runtime_meta["evaluation_profile_sha256"] == profile[
        "profile_sha256"
    ]
    assert metadata["profile_id"] == profile_id
    assert metadata["profile_sha256"] == profile["profile_sha256"]
    assert cells == {profile_id}


@pytest.mark.parametrize(
    ("target", "message"),
    (
        ("runtime_profile_id", "stock-portfolio runtime metadata changed"),
        ("runtime_profile_sha256", "stock-portfolio runtime metadata changed"),
        ("metadata_profile_id", "aggregate metadata semantics changed"),
        ("metadata_profile_sha256", "aggregate metadata semantics changed"),
        ("cell_profile_id", "stock-portfolio cell semantics changed"),
    ),
)
def test_each_stock_universe_result_refuses_r065_profile_substitution(
    stock_universe_plan,
    target,
    message,
):
    statistics = _stock_portfolio_aggregate_statistics(stock_universe_plan)
    r065 = stock_portfolio_evaluator.require_stock_portfolio_profile(
        stock_portfolio_evaluator.PROFILE_ID
    )
    if target.startswith("runtime_"):
        runtime_meta = json.loads(statistics["ARV2_RUNTIME_META"])
        key = (
            "evaluation_profile_id"
            if target.endswith("_id")
            else "evaluation_profile_sha256"
        )
        runtime_meta[key] = (
            r065["profile_id"]
            if key.endswith("_id")
            else r065["profile_sha256"]
        )
        statistics["ARV2_RUNTIME_META"] = _canonical(runtime_meta).decode(
            "ascii"
        )
    elif target.startswith("metadata_"):
        metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
        key = "profile_id" if target.endswith("_id") else "profile_sha256"
        metadata[key] = r065[key]
        statistics["ARV2_STOCK_PORTFOLIO_META"] = _canonical(metadata).decode(
            "ascii"
        )
    else:
        name = "ARV2_STOCK_PORTFOLIO_COST_10"
        cell = json.loads(statistics[name])
        cell["profile_id"] = r065["profile_id"]
        statistics[name] = _canonical(cell).decode("ascii")

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match=message,
    ):
        _validate_statistics(stock_universe_plan, statistics)


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


def test_stock_portfolio_validator_accepts_matched_only_partial_rebalance(
    stock_portfolio_plan,
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
    metadata["matched_stale_mark_session_count"] = 1
    metadata["matched_partial_rebalance_decision_count"] = 1
    metadata["matched_stale_position_deferral_count"] = 1
    metadata["matched_mean_locked_gross_at_partial_decisions"] = "0.005"
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


def test_stock_portfolio_validator_accepts_disclosed_locked_gross_over_target(
    stock_portfolio_plan,
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    metadata = json.loads(statistics["ARV2_STOCK_PORTFOLIO_META"])
    metadata["matched_target_met_execution_count"] = 260
    metadata["matched_stale_mark_session_count"] = 1
    metadata["matched_partial_rebalance_decision_count"] = 1
    metadata["matched_stale_position_deferral_count"] = 1
    metadata["matched_mean_locked_gross_at_partial_decisions"] = "0.5"
    metadata["matched_locked_exposure_over_target_count"] = 1
    metadata["matched_mean_executed_target_gross_exposure"] = "0.02"
    statistics["ARV2_STOCK_PORTFOLIO_META"] = _canonical(metadata).decode(
        "ascii"
    )
    for cost in stock_portfolio_evaluator.COST_BPS_SCENARIOS:
        cell_name = "ARV2_STOCK_PORTFOLIO_COST_" + str(cost)
        cell = json.loads(statistics[cell_name])
        cell["status"] = (
            "PRELIMINARY_DESCRIPTIVE_AVAILABLE_WITH_STALE_MARK_PROXY"
        )
        cell["return_metric_conditioning"] = "conditioned_on_stale_mark_path"
        cell["risk_metrics_are_price_proxy_conditioned"] = True
        statistics[cell_name] = _canonical(cell).decode("ascii")
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


@pytest.mark.parametrize(
    ("updates", "message"),
    (
        (
            {
                "partial_rebalance_decision_count": 0,
                "stale_position_deferral_count": 1,
                "mean_locked_gross_at_partial_decisions": "0.005",
            },
            "aggregate metadata semantics changed",
        ),
        (
            {"stale_mark_session_count": 1255},
            "aggregate metadata semantics changed",
        ),
        (
            {
                "partial_rebalance_decision_count": 1,
                "stale_mark_session_count": 1,
                "stale_position_deferral_count": 2,
                "mean_locked_gross_at_partial_decisions": "0.005",
            },
            "aggregate metadata semantics changed",
        ),
        (
            {
                "matched_partial_rebalance_decision_count": 1,
                "matched_stale_position_deferral_count": 0,
                "matched_mean_locked_gross_at_partial_decisions": "0.005",
            },
            "aggregate metadata semantics changed",
        ),
        (
            {
                "locked_exposure_over_target_count": 1,
                "partial_rebalance_decision_count": 0,
            },
            "aggregate metadata semantics changed",
        ),
    ),
)
def test_stock_portfolio_validator_isolates_partial_rebalance_invariants(
    stock_portfolio_plan,
    updates,
    message,
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


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("spy_cumulative_return", "0.21"),
        ("average_daily_two_sided_turnover", "0.05"),
        ("average_cash_weight", "0.03"),
        ("matched_average_daily_two_sided_turnover", "0.04"),
        ("matched_average_cash_weight", "0.01"),
    ),
)
def test_stock_portfolio_validator_refuses_cross_cell_path_mutation(
    stock_portfolio_plan, field, value
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    cell_name = "ARV2_STOCK_PORTFOLIO_COST_20"
    cell = json.loads(statistics[cell_name])
    cell[field] = value
    if field == "spy_cumulative_return":
        cell["cumulative_return_minus_spy"] = "-0.15"
    statistics[cell_name] = _canonical(cell).decode("ascii")
    _rehash_stock_portfolio_summary(statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="stock-portfolio cost path invariance changed",
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


@pytest.mark.parametrize("account", ("signal", "matched"))
def test_stock_portfolio_validator_refuses_nonmonotone_cost_return(
    stock_portfolio_plan, account
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    cell_name = "ARV2_STOCK_PORTFOLIO_COST_20"
    cell = json.loads(statistics[cell_name])
    if account == "signal":
        cell["cumulative_return"] = "0.081"
        cell["cumulative_return_minus_matched"] = "0.071"
        cell["cumulative_return_minus_spy"] = "-0.119"
    else:
        cell["matched_eligible_stock_cumulative_return"] = "0.031"
        cell["cumulative_return_minus_matched"] = "0.029"
    statistics[cell_name] = _canonical(cell).decode("ascii")
    _rehash_stock_portfolio_summary(statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="stock-portfolio cost monotonicity changed",
    ):
        _validate_statistics(stock_portfolio_plan, statistics)


@pytest.mark.parametrize("account", ("signal", "matched"))
def test_stock_portfolio_validator_refuses_wrong_closed_form_cost_arithmetic(
    stock_portfolio_plan, account
):
    statistics = _stock_portfolio_aggregate_statistics(stock_portfolio_plan)
    cell_name = "ARV2_STOCK_PORTFOLIO_COST_20"
    cell = json.loads(statistics[cell_name])
    if account == "signal":
        cell["annualized_arithmetic_return"] = "0.03"
        cell["annualized_volatility"] = "0.10"
        cell["zero_rate_sharpe"] = "0.3"
        cell["zero_rate_sortino"] = "0.3"
    else:
        cell["matched_annualized_arithmetic_return"] = "0.03"
        cell["matched_annualized_volatility"] = "0.10"
        cell["matched_zero_rate_sharpe"] = "0.3"
        cell["matched_zero_rate_sortino"] = "0.3"
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


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("MINIMUM_INVESTED_RETURN_SESSIONS", 0),
        ("COST_BPS_SCENARIOS", (10,)),
        ("ANNUALIZATION_SESSIONS", Decimal("251")),
    ),
)
def test_stock_contract_constant_mutation_refuses_before_network(
    stock_portfolio_plan, monkeypatch, name, value
):
    backend = _Backend(stock_portfolio_plan)
    monkeypatch.setattr(stock_portfolio_evaluator, name, value)

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


@pytest.mark.parametrize("mutation", ("profile_ids", "profile_hash"))
def test_stock_universe_projection_identity_mutation_refuses_before_network(
    stock_universe_plan,
    monkeypatch,
    mutation,
):
    backend = _Backend(stock_universe_plan)
    profile_id = stock_universe_plan.evaluation_profile_id
    if mutation == "profile_ids":
        monkeypatch.setattr(
            projection_builder,
            "STOCK_PORTFOLIO_PROFILE_IDS",
            projection_builder.STOCK_PORTFOLIO_PROFILE_IDS
            + ("arv2-unrelated-stock-profile",),
        )
    else:
        hashes = dict(projection_builder.STOCK_PORTFOLIO_PROFILE_SHA256S)
        hashes[profile_id] = "0" * 64
        monkeypatch.setattr(
            projection_builder,
            "STOCK_PORTFOLIO_PROFILE_SHA256S",
            hashes,
        )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=stock_universe_plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-16T20:00:00Z",
        )
    assert backend.events == []
    assert not any(stock_universe_plan.control_directory.iterdir())


def test_stock_universe_runtime_profile_inventory_mutation_refuses_before_network(
    stock_universe_plan,
    monkeypatch,
):
    backend = _Backend(stock_universe_plan)
    monkeypatch.setattr(
        runtime,
        "STOCK_PORTFOLIO_PROFILE_IDS",
        runtime.STOCK_PORTFOLIO_PROFILE_IDS
        + ("arv2-unrelated-stock-profile",),
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=stock_universe_plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-16T20:00:00Z",
        )
    assert backend.events == []
    assert not any(stock_universe_plan.control_directory.iterdir())


def test_stock_universe_snapshot_age_helper_mutation_refuses_before_network(
    stock_universe_plan,
    monkeypatch,
):
    backend = _Backend(stock_universe_plan)
    monkeypatch.setattr(
        stock_portfolio_evaluator,
        "constituent_snapshot_maximum_age_calendar_days_for_profile",
        lambda _profile_id: None,
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=stock_universe_plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-16T20:00:00Z",
        )
    assert backend.events == []
    assert not any(stock_universe_plan.control_directory.iterdir())


def test_stock_universe_positive_count_helper_mutation_refuses_before_network(
    stock_universe_plan,
    monkeypatch,
):
    backend = _Backend(stock_universe_plan)
    monkeypatch.setattr(
        stock_portfolio_evaluator,
        "constituent_positive_count_bounds_for_profile",
        lambda _profile_id: (),
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=stock_universe_plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-16T20:00:00Z",
        )
    assert backend.events == []
    assert not any(stock_universe_plan.control_directory.iterdir())


def test_stock_universe_state_profile_inventory_mutation_refuses_before_network(
    stock_universe_plan,
    monkeypatch,
):
    backend = _Backend(stock_universe_plan)
    monkeypatch.setattr(
        runtime,
        "STOCK_STATE_UNTIL_SUPERSEDED_PROFILE_IDS",
        runtime.STOCK_STATE_UNTIL_SUPERSEDED_PROFILE_IDS[:-1],
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=stock_universe_plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-16T20:00:00Z",
        )
    assert backend.events == []
    assert not any(stock_universe_plan.control_directory.iterdir())


def test_stock_universe_membership_profile_inventory_mutation_refuses_before_network(
    stock_universe_plan,
    monkeypatch,
):
    backend = _Backend(stock_universe_plan)
    monkeypatch.setattr(
        runtime,
        "STOCK_MEMBERSHIP_ONLY_PROFILE_IDS",
        runtime.STOCK_MEMBERSHIP_ONLY_PROFILE_IDS[:-1],
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=stock_universe_plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-16T20:00:00Z",
        )
    assert backend.events == []
    assert not any(stock_universe_plan.control_directory.iterdir())


def test_stock_universe_evaluator_membership_profile_inventory_mutation_refuses_before_network(
    stock_universe_plan,
    monkeypatch,
):
    backend = _Backend(stock_universe_plan)
    monkeypatch.setattr(
        stock_portfolio_evaluator,
        "MEMBERSHIP_ONLY_PROFILE_IDS",
        stock_portfolio_evaluator.MEMBERSHIP_ONLY_PROFILE_IDS[:-1],
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="^preliminary action global binding changed$",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=stock_universe_plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-16T20:00:00Z",
        )
    assert backend.events == []
    assert not any(stock_universe_plan.control_directory.iterdir())


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


def test_six_universe_projection_is_exact_and_qc_prelude_safe(six_universe_plan):
    projection = six_universe_plan.projection
    assert tuple(
        item.project_path
        for item in projection.source_files
        if item.project_path != "main.py"
    ) == tuple(sorted(projection_builder.SIX_UNIVERSE_PROJECT_SOURCE_PATHS))
    assert projection.evaluation_profile_id in six_universe_evaluator.PROFILE_IDS
    assert projection.train_work_units_per_slice == (
        six_universe_runtime.TRAIN_WORK_UNITS_PER_SLICE
    )
    assert projection.maximum_train_slice_count == (
        six_universe_runtime.MAXIMUM_TRAIN_SLICE_COUNT
    )
    for source in projection.source_files:
        text = source.source_bytes.decode("ascii")
        assert "from __future__ import" not in text
        compile("QC_PRELUDE_SENTINEL = True\n" + text, source.project_path, "exec")
        compile(
            "from AlgorithmImports import *\n" + text,
            source.project_path,
            "exec",
        )
    main = next(
        item.source_bytes.decode("ascii")
        for item in projection.source_files
        if item.project_path == "main.py"
    )
    assert "AcceptedRiskSixUniverseGateQcDriver" in main
    assert "('SPY', 'QQQ', 'SOXX', 'XLV', 'REMX', 'XLE')" in main
    assert "profile_id=" + repr(projection.evaluation_profile_id) in main


def test_exploratory_six_universe_profile_preserves_legacy_submission_specs():
    assert six_universe_evaluator.PROFILE_IDS == (
        six_universe_evaluator.TOP10_PRIMARY_PROFILE.profile_id,
        six_universe_evaluator.TOP5_SENSITIVITY_PROFILE.profile_id,
        six_universe_evaluator.TOP10_CAP95_EXPLORATORY_PROFILE.profile_id,
    )
    assert adapter._six_universe_contract_bindings_are_current()
    assert (
        adapter._run_spec(
            six_universe_evaluator.TOP10_PRIMARY_PROFILE.profile_id
        ).ledger_entry_id
        == "R-121"
    )
    assert (
        adapter._run_spec(
            six_universe_evaluator.TOP5_SENSITIVITY_PROFILE.profile_id
        ).ledger_entry_id
        == "R-122"
    )
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="not allowlisted",
    ):
        adapter._run_spec(
            six_universe_evaluator.TOP10_CAP95_EXPLORATORY_PROFILE.profile_id
        )


def test_six_universe_profiles_have_exact_run_specs_and_result_inventory(
    six_universe_plan,
):
    profile_id = six_universe_plan.evaluation_profile_id
    expected = {
        six_universe_evaluator.TOP10_PRIMARY_PROFILE.profile_id: (
            "R-121", 88, 89, 31, 32, 609, 612
        ),
        six_universe_evaluator.TOP5_SENSITIVITY_PROFILE.profile_id: (
            "R-122", 89, 90, 32, 33, 612, 615
        ),
    }[profile_id]
    spec = adapter._run_spec(profile_id)
    assert (
        spec.ledger_entry_id,
        spec.run_level_looks_before,
        spec.run_level_looks_after,
        spec.development_evaluations_before,
        spec.development_evaluations_after,
        spec.lifetime_alpha_cell_floor_before,
        spec.lifetime_alpha_cell_floor_after,
    ) == expected
    assert spec.cell_count == 3
    assert six_universe_plan.expected_custom_statistic_names == tuple(
        sorted(
            (
                *six_universe_evaluator.expected_custom_summary_statistic_names(
                    profile_id
                ),
                six_universe_runtime.RUNTIME_META_STATISTIC_NAME,
            )
        )
    )
    assert len(six_universe_plan.expected_custom_statistic_names) == 7
    for stage in ("reservation", "launch", "result"):
        accounting = adapter._look_accounting(
            stage=stage, evaluation_profile_id=profile_id
        )
        assert accounting["planned_maximum_preliminary_ic_cell_count"] == 3
        assert accounting["emitted_preliminary_ic_cell_count"] == (
            3 if stage == "result" else 0
        )


def test_six_universe_exact_seven_aggregate_statistics_validate(
    six_universe_plan,
):
    statistics = _six_universe_aggregate_statistics(six_universe_plan)
    _validate_statistics(six_universe_plan, statistics)


def test_six_universe_evaluator_account_output_validates_in_host(
    six_universe_plan, monkeypatch,
):
    monkeypatch.setattr(
        evaluator,
        "load_preliminary_rating_input",
        _PINNED_BUILD_SIX_EVALUATOR_INPUT,
    )
    profile = six_universe_evaluator.require_profile(
        six_universe_plan.evaluation_profile_id
    )
    runtime = six_evaluator_fixtures._complete(
        six_evaluator_fixtures.fixtures._input(20),
        profile=profile,
    )
    statistics = runtime.custom_summary_statistics()
    assert tuple(
        json.loads(statistics[name])["role"]
        for name in (
            six_universe_evaluator.SIGNAL_STATISTIC_NAME,
            six_universe_evaluator.MATCHED_STATISTIC_NAME,
            six_universe_evaluator.ETF_BASKET_STATISTIC_NAME,
        )
    ) == ("signal", "matched", "six_etf_basket")
    meta = json.loads(statistics[six_universe_evaluator.META_STATISTIC_NAME])
    expected_pit_calls = (
        (
            six_universe_evaluator.EXPECTED_DECISION_SESSION_COUNT
            + six_universe_runtime.HISTORY_CHUNK_DECISION_COUNT
            - 1
        )
        // six_universe_runtime.HISTORY_CHUNK_DECISION_COUNT
    ) * (1 + len(six_universe_gate.UNIVERSE_IDS))
    meta.update(
        {
            "package_id": six_universe_plan.package_id,
            "package_sha256": six_universe_plan.package_sha256,
            "input_manifest_id": six_universe_plan.evaluator_manifest_id,
            "input_manifest_sha256": six_universe_plan.evaluator_manifest_sha256,
            "pit_history_call_count": expected_pit_calls,
        }
    )
    statistics[six_universe_evaluator.META_STATISTIC_NAME] = _canonical(
        meta
    ).decode("ascii")
    statistics[six_universe_runtime.RUNTIME_META_STATISTIC_NAME] = _canonical(
        {
            "schema": "arv2-six-universe-qc-runtime-meta-v1",
            "profile_id": profile.profile_id,
            "profile_sha256": profile.profile_sha256,
            "package_id": six_universe_plan.package_id,
            "package_sha256": six_universe_plan.package_sha256,
            "symbol_resolution_id": meta["symbol_resolution_id"],
            "symbol_resolution_sha256": meta["symbol_resolution_sha256"],
            "runtime_slice_count": 1,
            "pit_history_call_count": expected_pit_calls,
            "pit_source_row_count": meta["pit_source_row_count"],
            "price_history_call_count": meta["price_history_batch_count"],
            "result_transport": "aggregate_only_custom_summary_statistics",
            "host_object_store_export_required": False,
            "backtest_only": True,
            "orders": False,
            "deployment": False,
            "trading": False,
        }
    ).decode("ascii")
    _rehash_six_universe_summary(six_universe_plan, statistics)

    _validate_statistics(six_universe_plan, statistics)


@pytest.mark.parametrize(
    ("statistic_name", "field", "value", "message"),
    (
        (
            six_universe_runtime.RUNTIME_META_STATISTIC_NAME,
            "orders",
            True,
            "runtime semantics changed",
        ),
        (
            six_universe_evaluator.SERIES_STATISTIC_NAME,
            "observation_count",
            1_254,
            "series semantics changed",
        ),
        (
            six_universe_evaluator.SIGNAL_STATISTIC_NAME,
            "invested_return_session_count",
            49,
            "account count invariants changed",
        ),
    ),
)
def test_six_universe_dangerous_aggregate_mutations_are_refused(
    six_universe_plan, statistic_name, field, value, message
):
    statistics = _six_universe_aggregate_statistics(six_universe_plan)
    record = json.loads(statistics[statistic_name])
    if statistic_name == six_universe_evaluator.SERIES_STATISTIC_NAME:
        record["series"][0][field] = value
    else:
        record[field] = value
    statistics[statistic_name] = _canonical(record).decode("ascii")
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match=message,
    ):
        _validate_statistics(six_universe_plan, statistics)


def test_six_universe_top5_sleeve_slot_count_is_profile_bound(
    six_universe_plan,
):
    if (
        six_universe_plan.evaluation_profile_id
        != six_universe_evaluator.TOP5_SENSITIVITY_PROFILE.profile_id
    ):
        pytest.skip("top-five profile only")
    statistics = _six_universe_aggregate_statistics(six_universe_plan)
    sleeves = json.loads(statistics[six_universe_evaluator.SLEEVES_STATISTIC_NAME])
    sleeves["universes"][0]["mean_signal_stock_count"] = "10"
    statistics[six_universe_evaluator.SLEEVES_STATISTIC_NAME] = _canonical(
        sleeves
    ).decode("ascii")
    _rehash_six_universe_summary(six_universe_plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="sleeve metric escaped bounds",
    ):
        _validate_statistics(six_universe_plan, statistics)


@pytest.mark.parametrize(
    ("statistic_name", "field", "value", "message"),
    (
        (
            six_universe_evaluator.SIGNAL_STATISTIC_NAME,
            "annualized_two_sided_turnover",
            "999",
            "turnover arithmetic changed",
        ),
        (
            six_universe_evaluator.SIGNAL_STATISTIC_NAME,
            "zero_rate_sharpe",
            "999",
            "Sharpe arithmetic changed",
        ),
        (
            six_universe_evaluator.ETF_BASKET_STATISTIC_NAME,
            None,
            None,
            "ETF basket completeness changed",
        ),
    ),
)
def test_six_universe_rehashed_economic_identity_mutations_are_refused(
    six_universe_plan, statistic_name, field, value, message
):
    statistics = _six_universe_aggregate_statistics(six_universe_plan)
    account = json.loads(statistics[statistic_name])
    if field is None:
        account["full_target_count"] = 0
        account["underfilled_target_count"] = 261
    else:
        account[field] = value
    statistics[statistic_name] = _canonical(account).decode("ascii")
    _rehash_six_universe_summary(six_universe_plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match=message,
    ):
        _validate_statistics(six_universe_plan, statistics)


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("PRIMARY_COST_BPS_PER_SIDE", 11),
        ("MODELED_COST_RATE_PER_SIDE", Decimal("0.002")),
        ("ANNUALIZATION_SESSIONS", Decimal("251")),
        ("GATE_SCORE_QUANTUM", Decimal("1e-47")),
    ),
)
def test_six_universe_financial_contract_mutation_refuses_pre_network(
    six_universe_plan, monkeypatch, name, value
):
    backend = _Backend(six_universe_plan)
    monkeypatch.setattr(six_universe_evaluator, name, value)
    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="action global binding changed",
    ):
        adapter.execute_accepted_risk_preliminary_submission_once(
            plan=six_universe_plan,
            owner_signature=None,
            client=_client(backend),
            started_at_utc="2026-09-18T20:00:00Z",
        )
    assert backend.events == []
    assert not any(six_universe_plan.control_directory.iterdir())


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
        elif profile_id in six_universe_evaluator.PROFILE_IDS:
            self.statistics = _six_universe_aggregate_statistics(plan)
        elif profile_id in leverage_evaluator.PROFILE_IDS:
            self.statistics = _leverage_aggregate_statistics(plan)
        elif profile_id in market_cap_evaluator.ALL_PROFILE_IDS:
            self.statistics = _market_cap_aggregate_statistics(plan)
        elif profile_id in stock_portfolio_evaluator.PROFILE_IDS:
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


def test_six_universe_signed_path_reads_exactly_seven_aggregates_once(
    six_universe_plan,
):
    signature = _offline_signature()
    backend = _Backend(six_universe_plan)
    permit, launch = _execute(six_universe_plan, backend, signature)
    terminal = _complete(
        six_universe_plan, backend, signature, permit, launch
    )
    authority = json.loads(
        adapter.render_accepted_risk_preliminary_result_read_authority_candidate(
            plan=six_universe_plan,
            permit=permit,
            launch=launch,
            terminal=terminal,
        )
    )
    assert authority["expected_custom_statistic_names"] == list(
        six_universe_plan.expected_custom_statistic_names
    )
    result_permit, result = _read(
        six_universe_plan,
        backend,
        signature,
        permit,
        launch,
        terminal,
    )
    assert result_permit.plan_sha256 == six_universe_plan.plan_sha256
    assert tuple(name for name, _value in result.custom_statistics) == (
        six_universe_plan.expected_custom_statistic_names
    )
    assert backend.events.count("backtests/read") == 1
    persisted = result.persisted_path.read_text()
    assert "RAW_PRICE" not in persisted
    assert "RAW_ORDER" not in persisted


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


def test_market_cap_offline_launch_and_result_read_are_exact(
    market_cap_plan_2021,
):
    signature = _offline_signature()
    backend = _Backend(market_cap_plan_2021)
    permit, launch = _execute(market_cap_plan_2021, backend, signature)
    terminal = _complete(
        market_cap_plan_2021, backend, signature, permit, launch
    )
    result_permit, result = _read(
        market_cap_plan_2021,
        backend,
        signature,
        permit,
        launch,
        terminal,
    )

    assert terminal.terminal_status == "Completed."
    assert backend.events.count("backtests/create") == 1
    assert backend.events.count("backtests/read") == 1
    assert tuple(name for name, _value in result.custom_statistics) == (
        market_cap_plan_2021.expected_custom_statistic_names
    )
    persisted = json.loads(result.persisted_path.read_bytes())
    assert persisted["look_accounting"]["shared_look_ledger_entry_id"] == "R-107"
    assert persisted["look_accounting"]["lifetime_alpha_cell_floor_after"] == 595
    assert adapter.require_accepted_risk_preliminary_aggregate_result(
        result,
        plan=market_cap_plan_2021,
        execution_permit=permit,
        launch=launch,
        terminal=terminal,
        result_permit=result_permit,
    ) is result


@pytest.mark.parametrize(
    "profile_id",
    (
        market_cap_evaluator.QQQ_2019_2023_V2_PROFILE_ID,
        market_cap_evaluator.SPY_2019_2023_V2_PROFILE_ID,
        market_cap_evaluator.QQQ_2023_2025_V2_PROFILE_ID,
        market_cap_evaluator.SPY_2023_2025_V2_PROFILE_ID,
        leverage_evaluator.QQQ_2021_2025_V3_PROFILE_ID,
        leverage_evaluator.SPY_2021_2025_V3_PROFILE_ID,
        market_cap_evaluator.QQQ_2021_2025_V3_PROFILE_ID,
        market_cap_evaluator.SPY_2021_2025_V3_PROFILE_ID,
    ),
)
def test_each_r109_through_r114_fresh_execution_is_explicitly_superseded(
    profile_id,
):
    superseded_plan = SimpleNamespace(
        projection=SimpleNamespace(evaluation_profile_id=profile_id)
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="profile is superseded and cannot launch",
    ):
        adapter._require_fresh_launch_profile(superseded_plan)


@pytest.mark.parametrize("profile_id", market_cap_evaluator.V3_PROFILE_IDS)
def test_r115_r116_historical_validation_remains_exact(
    profile_id, monkeypatch, tmp_path
):
    plan = _build_plan(
        monkeypatch,
        tmp_path,
        profile_id,
        allow_superseded_projection_for_execution_test=True,
    )
    statistics = _market_cap_aggregate_statistics(plan)

    _validate_statistics(plan, statistics)

    assert plan.evaluation_profile_sha256 == (
        market_cap_evaluator.require_profile(profile_id)["profile_sha256"]
    )


@pytest.mark.parametrize(
    "profile_id",
    projection_builder.SUPERSEDED_UNSPENT_PROFILE_IDS,
)
def test_each_r109_through_r114_public_execution_refuses_before_network(
    profile_id,
    monkeypatch,
    tmp_path,
):
    superseded_plan = _build_plan(
        monkeypatch,
        tmp_path,
        profile_id,
        allow_superseded_projection_for_execution_test=True,
    )
    backend = _Backend(superseded_plan)
    action = _offline_action(
        adapter.execute_accepted_risk_preliminary_submission_once
    )

    with pytest.raises(
        adapter.AcceptedRiskPreliminarySubmissionError,
        match="profile is superseded and cannot launch",
    ):
        action(
            plan=superseded_plan,
            owner_signature=_offline_signature(),
            client=_client(backend),
            started_at_utc="2026-09-18T20:00:00Z",
        )

    assert backend.events == []
    assert not any(superseded_plan.control_directory.iterdir())


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
    assert accounting["shared_look_ledger_entry_id"] == "R-065"
    assert accounting["run_level_looks_after"] == 65
    assert accounting["arv2_development_evaluations_after"] == 12
    assert accounting["lifetime_alpha_cell_floor_after"] == 579


def test_each_stock_universe_offline_result_uses_stock_parser_and_run_spec(
    stock_universe_plan,
):
    signature = _offline_signature()
    backend = _Backend(stock_universe_plan)
    profile_id = stock_universe_plan.evaluation_profile_id
    expected = _STOCK_UNIVERSE_ACCOUNTING[profile_id]

    permit, launch = _execute(stock_universe_plan, backend, signature)
    terminal = _complete(
        stock_universe_plan, backend, signature, permit, launch
    )
    _result_permit, result = _read(
        stock_universe_plan,
        backend,
        signature,
        permit,
        launch,
        terminal,
    )

    assert backend.events.count("backtests/create") == 1
    assert backend.events.count("backtests/read") == 1
    assert len(result.custom_statistics) == 6
    receipt = json.loads(result.persisted_path.read_bytes())
    persisted_statistics = dict(receipt["custom_statistics"])
    persisted_runtime = json.loads(persisted_statistics["ARV2_RUNTIME_META"])
    persisted_meta = json.loads(
        persisted_statistics["ARV2_STOCK_PORTFOLIO_META"]
    )
    assert persisted_runtime["evaluation_profile_id"] == profile_id
    assert persisted_runtime["evaluation_profile_sha256"] == (
        stock_universe_plan.evaluation_profile_sha256
    )
    assert persisted_meta["profile_id"] == profile_id
    assert persisted_meta["profile_sha256"] == (
        stock_universe_plan.evaluation_profile_sha256
    )
    accounting = receipt["look_accounting"]
    assert accounting["shared_look_ledger_entry_id"] == expected[1]
    assert accounting["run_level_looks_after"] == expected[3]
    assert accounting["arv2_development_evaluations_after"] == expected[5]
    assert accounting["lifetime_alpha_cell_floor_after"] == expected[7]


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
