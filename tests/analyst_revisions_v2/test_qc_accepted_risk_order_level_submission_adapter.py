from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import traceback
from decimal import Decimal, localcontext
from pathlib import Path
from types import FunctionType, SimpleNamespace

import pytest

from research.analyst_revisions_v2.canonical import canonical_json_bytes
from research.analyst_revisions_v2_qc import (
    accepted_risk_delta_order_package as delta_package_builder,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_submission_adapter as adapter,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_qc_projection as projection_builder,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_package as package_builder,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_qc_runtime as runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v12_qc_runtime as v12_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v13_qc_runtime as v13_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v14_qc_runtime as v14_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v15_qc_runtime as v15_runtime,
)
from research.analyst_revisions_v2_qc import formal_qc_transport


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _profile(profile_id):
    return (
        v15_runtime.require_qqq_order_level_profile(profile_id)
        if profile_id in v15_runtime.ACCOUNT_PROFILE_IDS
        else v14_runtime.require_qqq_order_level_profile(profile_id)
        if profile_id in v14_runtime.DIAGNOSTIC_PROFILE_IDS
        else v13_runtime.require_qqq_order_level_profile(profile_id)
        if profile_id in v13_runtime.ROLLOVER_PROFILE_IDS
        else v12_runtime.require_qqq_order_level_profile(profile_id)
        if profile_id in v12_runtime.FORCED_EXIT_PROFILE_IDS
        else runtime.require_qqq_order_level_profile(profile_id)
    )


def _expected_names(profile_id):
    return (
        v15_runtime.expected_custom_summary_statistic_names(profile_id)
        if profile_id in v15_runtime.ACCOUNT_PROFILE_IDS
        else v14_runtime.expected_custom_summary_statistic_names(profile_id)
        if profile_id in v14_runtime.DIAGNOSTIC_PROFILE_IDS
        else v13_runtime.expected_custom_summary_statistic_names(profile_id)
        if profile_id in v13_runtime.ROLLOVER_PROFILE_IDS
        else v12_runtime.expected_custom_summary_statistic_names(profile_id)
        if profile_id in v12_runtime.FORCED_EXIT_PROFILE_IDS
        else runtime.expected_custom_summary_statistic_names(profile_id)
    )


def _plan(tmp_path: Path, profile_id=runtime.PROFILE_2025_ID):
    profile = _profile(profile_id)
    activation_entry = adapter.OrderLevelUploadEntry(
        adapter.UPLOAD_SCHEMA,
        "activation_manifest",
        0,
        "arv2/order-test/transport-manifest.json",
        1,
        "5" * 64,
        "0" * 32,
        True,
    )
    expected_names = _expected_names(profile_id)
    return SimpleNamespace(
        plan_id="arv2-order-level-plan-test",
        plan_sha256="a" * 64,
        delta_lineage_sha256="9" * 64,
        package_id="arv2-package",
        package_sha256="b" * 64,
        projection_id="arv2-projection-test",
        projection_sha256="c" * 64,
        profile_id=profile_id,
        profile_sha256=profile["profile_sha256"],
        expected_custom_statistic_names=expected_names,
        expected_custom_statistic_names_sha256=hashlib.sha256(
            _canonical(list(expected_names))
        ).hexdigest(),
        control_directory=tmp_path,
        project_name="private-order-project",
        backtest_name="private-order-backtest",
        organization_id="organization-one",
        organization_id_sha256=hashlib.sha256(b"organization-one").hexdigest(),
        upload_entries=(activation_entry,),
        source_files=(),
        compile_poll_limit=2,
        status_poll_limit=2,
        maximum_backtest_submissions=1,
    )


def _test_signature(purpose: str, payload: bytes, *, mutated=False):
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    signature_sha256 = hashlib.sha256(
        (purpose + ":" + payload_sha256).encode("ascii")
    ).hexdigest()
    if mutated:
        signature_sha256 = "0" * 64
    return SimpleNamespace(
        authority_id="arv2-owner-signature-test",
        authority_sha256="1" * 64,
        public_key_blob_sha256="2" * 64,
        signature_sha256=signature_sha256,
        purpose=purpose,
        authority_payload_sha256=payload_sha256,
    )


def _test_signature_verifiers():
    def verifier(expected_purpose):
        def verify(value, *, authority_payload):
            payload_sha256 = hashlib.sha256(authority_payload).hexdigest()
            expected_signature_sha256 = hashlib.sha256(
                (expected_purpose + ":" + payload_sha256).encode("ascii")
            ).hexdigest()
            if (
                value is None
                or getattr(value, "purpose", None) != expected_purpose
                or getattr(value, "authority_payload_sha256", None)
                != payload_sha256
                or getattr(value, "signature_sha256", None)
                != expected_signature_sha256
            ):
                raise adapter.OwnerSignatureAuthorityError(
                    "detached owner signature verification failed"
                )
            return value

        return verify

    return verifier("formal_qc_execution"), verifier("formal_qc_result_read")


def _test_execution_operations():
    execution_verifier, _result_verifier = _test_signature_verifiers()
    return adapter._make_execution_authority_operations(
        signature_requirer=execution_verifier,
        plan_requirer=lambda value: value,
        exact_plan_type=SimpleNamespace,
    )


def _execution_authority(plan, monkeypatch):
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    render, load, _require = _test_execution_operations()
    payload = render(plan=plan)
    return load(
        plan=plan,
        receipt_bytes=payload,
        owner_signature=_test_signature("formal_qc_execution", payload),
    )


def _test_result_operations():
    _execution_signature, result_signature = _test_signature_verifiers()
    _render_execution, _load_execution, require_execution = (
        _test_execution_operations()
    )
    return adapter._make_result_read_authority_operations(
        signature_requirer=result_signature,
        execution_authority_requirer=require_execution,
        context_requirer=adapter._require_result_context,
        exact_plan_type=SimpleNamespace,
    )


def _result_read_authority(
    plan, execution_authority, control, launch, terminal, monkeypatch
):
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    render, load, _require = _test_result_operations()
    payload = render(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
    )
    return load(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
        receipt_bytes=payload,
        owner_signature=_test_signature("formal_qc_result_read", payload),
    )


def _launch(plan):
    return SimpleNamespace(
        backtest_id="backtest-one",
        project_id=123,
        backtest_name=plan.backtest_name,
        receipt_sha256="d" * 64,
    )


def _test_transport(client, capability, method, *args):
    return getattr(client, method)(capability, *args)


def _statistics(plan, *, meta_update=None, aggregate_update=None):
    decision_count, observation_count = {
        runtime.PROFILE_2025_ID: (91, 428),
        runtime.PROFILE_2026_ID: (39, 178),
        runtime.PROXY_PROFILE_2025_ID: (91, 428),
        runtime.PROXY_PROFILE_2026_ID: (39, 178),
        runtime.PREOPEN_PROXY_PROFILE_2025_ID: (91, 428),
        runtime.PREOPEN_PROXY_PROFILE_2026_ID: (39, 178),
        runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2025_ID: (91, 428),
        runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2026_ID: (39, 178),
        runtime.ENUM_PREOPEN_PROXY_PROFILE_2025_ID: (91, 428),
        runtime.ENUM_PREOPEN_PROXY_PROFILE_2026_ID: (39, 178),
        runtime.CASH_PREOPEN_PROXY_PROFILE_2025_ID: (91, 428),
        runtime.CASH_PREOPEN_PROXY_PROFILE_2026_ID: (39, 178),
        runtime.TICKET_PROFILE_2025_ID: (91, 428),
        runtime.TICKET_PROFILE_2026_ID: (39, 178),
        runtime.REFLECTED_TICKET_PROFILE_2025_ID: (91, 428),
        runtime.REFLECTED_TICKET_PROFILE_2026_ID: (39, 178),
        v12_runtime.FORCED_EXIT_PROFILE_2025_ID: (91, 428),
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID: (39, 178),
        v13_runtime.ROLLOVER_PROFILE_2025_ID: (91, 428),
        v13_runtime.ROLLOVER_PROFILE_2026_ID: (39, 178),
        v14_runtime.DIAGNOSTIC_PROFILE_2025_ID: (91, 428),
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID: (39, 178),
        v15_runtime.ACCOUNT_PROFILE_2025_ID: (91, 428),
        v15_runtime.ACCOUNT_PROFILE_2026_ID: (39, 178),
    }[plan.profile_id]
    aggregate = {
        "schema": runtime.SUMMARY_SCHEMA,
        "score_source_view_id": _profile(plan.profile_id)["score_source_view_id"],
        "decision_count": decision_count,
        "completed_rebalance_count": decision_count,
        "submitted_order_count": 2,
        "skipped_unpriced_decision_count": 0,
        "tilt_enabled_count": decision_count,
        "tilt_underfilled_count": 0,
        "mean_tilted_name_count": "2",
        "mean_one_way_active_share": "0.01",
        "pit_history_call_count": decision_count,
        "pit_source_row_count": 20,
        "named_figi_refusal_count": 0,
        "modeled_fee_bps_per_side": 10,
        "modeled_fee_amount": "10",
        "actual_engine_fee_amount": "10",
        "actual_engine_fee_effective_bps_per_side": "10",
        "modeled_minus_actual_fee_amount": "0",
        "fee_mismatch": False,
        "lifecycle_modeled_fee_basis": (
            "actual_fill_price_times_filled_quantity"
        ),
        "engine_fee_model_basis": (
            "current_minute_trade_bar_open_times_full_order_quantity_at_fee_assessment"
        ),
        "total_filled_notional": "10000",
        "filled_order_count_sum": 2,
        "canceled_order_count_sum": 0,
        "invalid_order_count_sum": 0,
        "orders_with_any_fill_count_sum": 2,
        "mean_reference_mark_target_weight_l1_error": "0.01",
        "maximum_reference_mark_target_weight_l1_error": "0.01",
        "execution_failure": False,
        "run_valid": True,
        "coverage_decision_count": decision_count,
        "positive_weight_member_count_sum": 100,
        "resolved_positive_weight_member_count_sum": 100,
        "mean_resolved_member_count_ratio": "1",
        "mean_resolved_constituent_weight_ratio": "1",
        "minimum_resolved_member_count_ratio": "1",
        "minimum_resolved_constituent_weight_ratio": "1",
        "minimum_required_resolved_constituent_weight_ratio": "0.95",
        "target_weight_basis": (
            "pit_qqq_reported_positive_holdings_weights_resolved_renormalized"
        ),
        "pit_target_weight_path_sha256": "9" * 64,
        "mean_positive_constituent_weight_total": "1",
        "minimum_positive_constituent_weight_total": "1",
        "maximum_positive_constituent_weight_total": "1",
        "minimum_required_positive_constituent_weight_total": "0.95",
        "maximum_allowed_positive_constituent_weight_total": "1.05",
        "maximum_constituent_snapshot_age_sessions": 1,
        "pit_coverage_path_sha256": "5" * 64,
        "starting_equity": "1000000",
        "ending_equity": "1100000",
        "strategy_total_return": "0.1",
        "strategy_maximum_drawdown": "-0.05",
        "strategy_annualized_volatility": "0.2",
        "strategy_zero_rate_sharpe": "0.5",
        "mean_gross_exposure": "0.98",
        "mean_cash_weight": "0.02",
        "strategy_equity_path_sha256": "1" * 64,
        "QQQ_total_return": "0.08",
        "QQQ_normalization_mode": "TOTAL_RETURN",
        "QQQ_observation": (
            "start_cash_then_first_execution_session_adjusted_open_entry_"
            "and_session_close_marks"
        ),
        "QQQ_first_execution_session": {
            runtime.PROFILE_2025_ID: "2025-01-03",
            runtime.PROFILE_2026_ID: "2026-01-05",
            runtime.PROXY_PROFILE_2025_ID: "2025-01-03",
            runtime.PROXY_PROFILE_2026_ID: "2026-01-05",
            runtime.PREOPEN_PROXY_PROFILE_2025_ID: "2025-01-03",
            runtime.PREOPEN_PROXY_PROFILE_2026_ID: "2026-01-05",
            runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2025_ID: "2025-01-03",
            runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2026_ID: "2026-01-05",
            runtime.ENUM_PREOPEN_PROXY_PROFILE_2025_ID: "2025-01-03",
            runtime.ENUM_PREOPEN_PROXY_PROFILE_2026_ID: "2026-01-05",
            runtime.CASH_PREOPEN_PROXY_PROFILE_2025_ID: "2025-01-03",
            runtime.CASH_PREOPEN_PROXY_PROFILE_2026_ID: "2026-01-05",
            runtime.TICKET_PROFILE_2025_ID: "2025-01-03",
            runtime.TICKET_PROFILE_2026_ID: "2026-01-05",
            runtime.REFLECTED_TICKET_PROFILE_2025_ID: "2025-01-03",
            runtime.REFLECTED_TICKET_PROFILE_2026_ID: "2026-01-05",
            v12_runtime.FORCED_EXIT_PROFILE_2025_ID: "2025-01-03",
            v12_runtime.FORCED_EXIT_PROFILE_2026_ID: "2026-01-05",
            v13_runtime.ROLLOVER_PROFILE_2025_ID: "2025-01-03",
            v13_runtime.ROLLOVER_PROFILE_2026_ID: "2026-01-05",
            v14_runtime.DIAGNOSTIC_PROFILE_2025_ID: "2025-01-03",
            v14_runtime.DIAGNOSTIC_PROFILE_2026_ID: "2026-01-05",
            v15_runtime.ACCOUNT_PROFILE_2025_ID: "2025-01-03",
            v15_runtime.ACCOUNT_PROFILE_2026_ID: "2026-01-05",
        }[plan.profile_id],
        "QQQ_target_gross_exposure": "0.98",
        "QQQ_entry_fee_bps_per_side": 10,
        "QQQ_maximum_drawdown": "-0.04",
        "QQQ_annualized_volatility": "0.18",
        "QQQ_zero_rate_sharpe": "0.44",
        "strategy_minus_QQQ_total_return": "0.02",
        "QQQ_observation_count": observation_count,
        "QQQ_return_interval_count": observation_count - 1,
        "QQQ_raw_observation_sha256": "2" * 64,
        "QQQ_return_path_sha256": "3" * 64,
        "QQQ_calendar_close_total_return": "0.081",
        "QQQ_calendar_close_observation_count": observation_count,
        "QQQ_calendar_close_raw_observation_sha256": "7" * 64,
        "QQQ_calendar_close_return_path_sha256": "8" * 64,
        "order_lifecycle_sha256": "4" * 64,
        "raw_order_rows_in_summary": False,
        "raw_security_rows_in_summary": False,
        "backtest_only": True,
        "simulated_orders": True,
        "live_orders": False,
        "trading": False,
    }
    if plan.profile_id in (
        runtime.PROXY_PROFILE_IDS
        + v12_runtime.FORCED_EXIT_PROFILE_IDS
        + v13_runtime.ROLLOVER_PROFILE_IDS
        + v14_runtime.DIAGNOSTIC_PROFILE_IDS
        + v15_runtime.ACCOUNT_PROFILE_IDS
    ):
        aggregate.update({
            "schema": runtime.PROXY_SUMMARY_SCHEMA,
            "target_weight_basis": runtime.PROXY_TARGET_WEIGHT_BASIS,
            "minimum_required_resolved_constituent_weight_ratio": "0.8",
            "mean_resolved_constituent_weight_ratio": "0.86",
            "minimum_resolved_constituent_weight_ratio": "0.86",
            "qqq_proxy_overlap_disclosure": runtime.QQQ_PROXY_OVERLAP_DISCLOSURE,
            "mean_qqq_proxy_constituent_weight_ratio": "0.14",
            "minimum_qqq_proxy_constituent_weight_ratio": "0.14",
            "maximum_qqq_proxy_constituent_weight_ratio": "0.14",
        })
    if plan.profile_id in adapter.FORCED_EXIT_PROFILE_IDS:
        aggregate.update({
            "schema": v12_runtime.FORCED_EXIT_SUMMARY_SCHEMA,
            "engine_forced_delisting": {
                "schema": "arv2-order-level-forced-delisting-summary-v1",
                "order_count": 0,
                "event_count": 0,
                "fill_event_count": 0,
                "terminal_order_count": 0,
                "absolute_filled_quantity": 0,
                "filled_notional": "0",
                "actual_engine_fee_amount": "0",
                "accounting_complete": True,
                "ledger_sha256": "e" * 64,
                "raw_order_rows_in_summary": False,
                "raw_security_rows_in_summary": False,
            },
            "forced_exit_invalidated_pending_rebalance_count": 0,
        })
    if plan.profile_id in (
        v14_runtime.DIAGNOSTIC_PROFILE_IDS
        + v15_runtime.ACCOUNT_PROFILE_IDS
    ):
        aggregate.update({
            "schema": v14_runtime.DIAGNOSTIC_SUMMARY_SCHEMA,
            "qqq_proxy_complement_policy": v14_runtime.EXACT_COMPLEMENT_POLICY,
            "skipped_unpriced_decision_evidence_policy": (
                v14_runtime.SKIPPED_UNPRICED_EVIDENCE_POLICY
            ),
            "skipped_unpriced_decision_evidence": {
                "schema": v14_runtime.SKIPPED_UNPRICED_EVIDENCE_SCHEMA,
                "skipped_decision_count": 0,
                "retained_decision_count": 0,
                "omitted_decision_count": 0,
                "records": [],
                "path_sha256": hashlib.sha256(_canonical({
                    "schema": v14_runtime.SKIPPED_UNPRICED_PATH_SCHEMA,
                    "records": [],
                })).hexdigest(),
            },
        })
    if plan.profile_id in v15_runtime.ACCOUNT_PROFILE_IDS:
        aggregate.update({
            "schema": v15_runtime.ACCOUNT_SUMMARY_SCHEMA,
            "delisted_zero_holding_target_retirement_count": 0,
            "delisted_zero_holding_target_retirement_decision_count": 0,
            "delisted_zero_holding_target_retired_weight_total": "0",
            "delisted_zero_holding_target_path_sha256": hashlib.sha256(
                _canonical({
                    "schema": v15_runtime.RETIRED_TARGET_PATH_SCHEMA,
                    "records": [],
                })
            ).hexdigest(),
            "terminal_account_observation_adjustment": "0",
            "terminal_account_observation_prior_equity": "1100000",
            "terminal_account_observation_equity": "1100000",
        })
    if aggregate_update:
        aggregate.update(aggregate_update)
    meta = {
        "schema": (
            "arv2-qqq-order-level-tilt-runtime-meta-v3"
            if plan.profile_id in (
                v14_runtime.DIAGNOSTIC_PROFILE_IDS
                + v15_runtime.ACCOUNT_PROFILE_IDS
            )
            else "arv2-qqq-order-level-tilt-runtime-meta-v2"
            if plan.profile_id in adapter.FORCED_EXIT_PROFILE_IDS
            else "arv2-qqq-order-level-tilt-runtime-meta-v1"
        ),
        "profile_id": plan.profile_id,
        "profile_sha256": plan.profile_sha256,
        "package_id": plan.package_id,
        "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": "5" * 64,
        "symbol_resolution_id": "resolution-one",
        "symbol_resolution_sha256": "6" * 64,
        "score_source_view_id": _profile(plan.profile_id)["score_source_view_id"],
        "aggregates_sha256": hashlib.sha256(_canonical(aggregate)).hexdigest(),
        "result_transport": "aggregate_only_custom_summary_statistics",
        "backtest_only": True,
        "simulated_order_submission": True,
        "live_orders": False,
        "paper_orders": False,
        "funded_orders": False,
        "deployment": False,
        "trading": False,
    }
    if meta_update:
        meta.update(meta_update)
    return {
        runtime.META_STATISTIC_NAME: _canonical(meta).decode("ascii"),
        runtime.AGGREGATES_STATISTIC_NAME: _canonical(aggregate).decode("ascii"),
    }


def _high_precision_statistics(plan):
    """Keep the full schema and hashes with production-like decimal lengths."""

    minimum_resolved = "0.8" + "5" * 99
    with localcontext() as context:
        context.prec = 256
        maximum_proxy = format(Decimal(1) - Decimal(minimum_resolved), "f")
    return _statistics(
        plan,
        aggregate_update={
            "minimum_resolved_member_count_ratio": "0." + "9" * 100,
            "minimum_resolved_constituent_weight_ratio": minimum_resolved,
            "maximum_qqq_proxy_constituent_weight_ratio": maximum_proxy,
            "mean_one_way_active_share": "0." + "2" * 100,
            "strategy_annualized_volatility": "0." + "2" * 100,
            "QQQ_annualized_volatility": "0." + "1" * 100,
            "strategy_zero_rate_sharpe": "0." + "5" * 100,
            "QQQ_zero_rate_sharpe": "0." + "4" * 100,
            "mean_tilted_name_count": "1." + "2" * 100,
            "maximum_reference_mark_target_weight_l1_error": (
                "0." + "2" * 100
            ),
        },
    )


def _v14_skipped_statistics(plan):
    statistics = _statistics(plan)
    aggregate = json.loads(statistics[runtime.AGGREGATES_STATISTIC_NAME])
    security_sha256s = ["1" * 64, "2" * 64]
    full_records = [{
        "decision_session": "2026-08-03",
        "missing_security_sha256s": security_sha256s,
    }]
    aggregate.update({
        "completed_rebalance_count": aggregate["decision_count"] - 1,
        "skipped_unpriced_decision_count": 1,
        "run_valid": False,
        "skipped_unpriced_decision_evidence": {
            "schema": v14_runtime.SKIPPED_UNPRICED_EVIDENCE_SCHEMA,
            "skipped_decision_count": 1,
            "retained_decision_count": 1,
            "omitted_decision_count": 0,
            "records": [{
                "decision_session": "2026-08-03",
                "missing_security_count": 2,
                "retained_missing_security_sha256s": security_sha256s,
                "omitted_missing_security_count": 0,
                "missing_security_path_sha256": hashlib.sha256(_canonical({
                    "schema": v14_runtime.MISSING_SECURITY_PATH_SCHEMA,
                    "security_sha256s": security_sha256s,
                })).hexdigest(),
            }],
            "path_sha256": hashlib.sha256(_canonical({
                "schema": v14_runtime.SKIPPED_UNPRICED_PATH_SCHEMA,
                "records": full_records,
            })).hexdigest(),
        },
    })
    meta = json.loads(statistics[runtime.META_STATISTIC_NAME])
    meta["aggregates_sha256"] = hashlib.sha256(_canonical(aggregate)).hexdigest()
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = _canonical(aggregate).decode(
        "ascii"
    )
    statistics[runtime.META_STATISTIC_NAME] = _canonical(meta).decode("ascii")
    return statistics


def _v15_retirement_statistics(plan):
    statistics = _statistics(plan)
    aggregate = json.loads(statistics[runtime.AGGREGATES_STATISTIC_NAME])
    forced = aggregate["engine_forced_delisting"]
    forced.update({
        "order_count": 1,
        "event_count": 1,
        "fill_event_count": 1,
        "terminal_order_count": 1,
        "absolute_filled_quantity": 5,
        "filled_notional": "62.5",
    })
    aggregate.update({
        "delisted_zero_holding_target_retirement_count": 1,
        "delisted_zero_holding_target_retirement_decision_count": 1,
        "delisted_zero_holding_target_retired_weight_total": "0.1",
        "delisted_zero_holding_target_path_sha256": hashlib.sha256(
            _canonical({
                "schema": v15_runtime.RETIRED_TARGET_PATH_SCHEMA,
                "records": [{
                    "decision_session": "2026-08-10",
                    "retired_security_sha256s": ["a" * 64],
                    "retired_target_weight": "0.1",
                }],
            })
        ).hexdigest(),
        "terminal_account_observation_adjustment": "-100",
        "terminal_account_observation_prior_equity": "1100100",
        "terminal_account_observation_equity": "1100000",
    })
    meta = json.loads(statistics[runtime.META_STATISTIC_NAME])
    meta["aggregates_sha256"] = hashlib.sha256(_canonical(aggregate)).hexdigest()
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = _canonical(aggregate).decode(
        "ascii"
    )
    statistics[runtime.META_STATISTIC_NAME] = _canonical(meta).decode("ascii")
    return statistics


def _result_response(plan, statistics):
    launch = _launch(plan)
    return launch, {
        "success": True,
        "backtest": {
            "backtestId": launch.backtest_id,
            "projectId": launch.project_id,
            "name": launch.backtest_name,
            "status": "Completed.",
            "statistics": {"Sharpe Ratio": "DO NOT SELECT", **statistics},
            "orders": object(),
            "charts": object(),
            "runtimeStatistics": object(),
        },
    }


def _persisted_launch(plan, execution_authority):
    control = adapter._spend_launch_control(
        plan, execution_authority, "2026-09-18T20:00:00Z"
    )
    launch = adapter._new_launch(
        plan, control, 123, "compile-one", "backtest-one", "Queued"
    )
    payload = adapter._launch_receipt_bytes(launch)
    adapter._write_private_once(
        adapter._launch_receipt_path(plan), payload, "launch receipt"
    )
    adapter._register_launch_authority(launch, plan, control, payload)
    return control, launch


def _persisted_terminal(plan, launch):
    record = {
        "plan_sha256": plan.plan_sha256,
        "launch_sha256": launch.receipt_sha256,
        "project_id": launch.project_id,
        "backtest_id": launch.backtest_id,
        "terminal_status": "Completed.",
        "poll_count": 1,
        "include_statistics": False,
    }
    identity, digest, _payload = adapter._identified(
        adapter.TERMINAL_SCHEMA, "arv2-order-level-terminal-", record
    )
    terminal = adapter.OrderLevelTerminalStatus(identity, digest, **record)
    payload = adapter._terminal_receipt_bytes(terminal)
    adapter._write_private_once(
        adapter._terminal_receipt_path(plan), payload, "terminal receipt"
    )
    adapter._register_terminal_authority(terminal, plan, launch, payload)
    return terminal


def _exception_graph_text(exc):
    pending = [exc]
    seen = set()
    rendered = []
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        rendered.extend(
            (
                type(current).__name__,
                str(current),
                repr(current),
                repr(vars(current)),
                "".join(
                    traceback.format_exception(
                        type(current), current, current.__traceback__
                    )
                ),
            )
        )
        pending.extend((current.__cause__, current.__context__))
    return "\n".join(rendered)


def _exception_internal_traceback_locals_text(exc):
    """Render reachable non-test traceback locals for secret-marker checks."""

    pending = [exc]
    seen = set()
    rendered = []
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        traceback_cursor = current.__traceback__
        while traceback_cursor is not None:
            frame = traceback_cursor.tb_frame
            if not frame.f_code.co_name.startswith("test_"):
                rendered.append(repr(dict(frame.f_locals)))
            traceback_cursor = traceback_cursor.tb_next
        pending.extend((current.__cause__, current.__context__))
    return "\n".join(rendered)


def test_result_parser_selects_only_exact_two_aggregate_statistics(tmp_path):
    plan = _plan(tmp_path)
    launch, response = _result_response(plan, _statistics(plan))

    pairs = adapter._parse_result(response, plan, launch)

    assert tuple(name for name, _value in pairs) == (
        runtime.AGGREGATES_STATISTIC_NAME,
        runtime.META_STATISTIC_NAME,
    )
    assert all("DO NOT SELECT" not in value for _name, value in pairs)


@pytest.mark.parametrize(
    "profile_id",
    (
        runtime.TICKET_PROFILE_2026_ID,
        runtime.REFLECTED_TICKET_PROFILE_2026_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        v13_runtime.ROLLOVER_PROFILE_2026_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    ),
)
def test_ticket_result_parser_accepts_complete_high_precision_aggregate(
    tmp_path, profile_id
):
    plan = _plan(tmp_path, profile_id)
    statistics = _high_precision_statistics(plan)
    aggregate_bytes = statistics[runtime.AGGREGATES_STATISTIC_NAME].encode("ascii")
    assert 4764 <= len(aggregate_bytes) <= adapter.MAX_TICKET_STATISTIC_BYTES
    launch, response = _result_response(plan, statistics)

    assert adapter._parse_result(response, plan, launch) == tuple(
        sorted(statistics.items())
    )


@pytest.mark.parametrize(
    "profile_id",
    (
        runtime.TICKET_PROFILE_2026_ID,
        runtime.REFLECTED_TICKET_PROFILE_2026_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        v13_runtime.ROLLOVER_PROFILE_2026_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    ),
)
def test_ticket_result_hashes_stored_aggregate_text_not_json_quoted_string(
    tmp_path, profile_id
):
    plan = _plan(tmp_path, profile_id)
    statistics = _high_precision_statistics(plan)
    stored_text = statistics[runtime.AGGREGATES_STATISTIC_NAME]
    stored_bytes = stored_text.encode("ascii")
    meta = json.loads(statistics[runtime.META_STATISTIC_NAME])
    assert len(stored_bytes) >= 4764
    assert meta["aggregates_sha256"] == hashlib.sha256(stored_bytes).hexdigest()
    assert meta["aggregates_sha256"] != hashlib.sha256(
        _canonical(stored_text)
    ).hexdigest()

    launch, response = _result_response(plan, statistics)
    assert adapter._parse_result(response, plan, launch) == tuple(
        sorted(statistics.items())
    )

    aggregate = json.loads(stored_text)
    aggregate["order_lifecycle_sha256"] = "a" * 64
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = _canonical(aggregate).decode(
        "ascii"
    )
    launch, response = _result_response(plan, statistics)
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="^order-level aggregate digest changed$",
    ):
        adapter._parse_result(response, plan, launch)


def test_legacy_result_parser_retains_4096_byte_bound(tmp_path):
    plan = _plan(tmp_path, runtime.CASH_PREOPEN_PROXY_PROFILE_2026_ID)
    statistics = _high_precision_statistics(plan)
    aggregate_bytes = statistics[runtime.AGGREGATES_STATISTIC_NAME].encode("ascii")
    assert adapter.MAX_STATISTIC_BYTES < len(aggregate_bytes) <= (
        adapter.MAX_TICKET_STATISTIC_BYTES
    )
    launch, response = _result_response(plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="^order-level custom result value exceeded its exact bound$",
    ):
        adapter._parse_result(response, plan, launch)


@pytest.mark.parametrize(
    "profile_id",
    (
        runtime.TICKET_PROFILE_2026_ID,
        runtime.REFLECTED_TICKET_PROFILE_2026_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        v13_runtime.ROLLOVER_PROFILE_2026_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    ),
)
def test_ticket_result_parser_refuses_more_than_8192_bytes(tmp_path, profile_id):
    plan = _plan(tmp_path, profile_id)
    statistics = _high_precision_statistics(plan)
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = "x" * (
        adapter.MAX_TICKET_STATISTIC_BYTES + 1
    )
    launch, response = _result_response(plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="^order-level custom result value exceeded its exact bound$",
    ):
        adapter._parse_result(response, plan, launch)


@pytest.mark.parametrize(
    "profile_id",
    (
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        v13_runtime.ROLLOVER_PROFILE_2026_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    ),
)
def test_versioned_result_parser_accepts_exact_nested_forced_exit_summary(
    tmp_path, profile_id,
):
    plan = _plan(tmp_path, profile_id)
    statistics = _statistics(plan)
    launch, response = _result_response(plan, statistics)

    assert adapter._parse_result(response, plan, launch) == tuple(
        sorted(statistics.items())
    )


@pytest.mark.parametrize(
    "profile_id",
    (
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        v13_runtime.ROLLOVER_PROFILE_2026_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    ),
)
def test_versioned_result_parser_requires_v2_meta_schema(tmp_path, profile_id):
    plan = _plan(tmp_path, profile_id)
    statistics = _statistics(plan, meta_update={
        "schema": "arv2-qqq-order-level-tilt-runtime-meta-v1",
    })
    launch, response = _result_response(plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="^order-level aggregate runtime lineage changed$",
    ):
        adapter._parse_result(response, plan, launch)


def test_v15_result_parser_requires_v3_meta_schema(tmp_path):
    plan = _plan(tmp_path, v15_runtime.ACCOUNT_PROFILE_2026_ID)
    statistics = _statistics(plan, meta_update={
        "schema": "arv2-qqq-order-level-tilt-runtime-meta-v2",
    })
    launch, response = _result_response(plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="^order-level aggregate runtime lineage changed$",
    ):
        adapter._parse_result(response, plan, launch)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("extra", "order-level forced delisting summary changed"),
        ("schema", "order-level forced delisting summary changed"),
        ("incomplete", "order-level forced delisting summary changed"),
        ("bool_count", "order-level forced delisting summary changed"),
        ("negative_count", "order-level forced delisting summary changed"),
        ("raw_rows", "order-level forced delisting summary changed"),
        (
            "digest",
            "order-level forced delisting ledger digest is not an exact SHA-256",
        ),
        ("count", "order-level forced delisting accounting changed"),
        ("notional", "order-level forced delisting accounting changed"),
        ("fee", "order-level forced delisting accounting changed"),
        ("invalidation", "order-level forced delisting accounting changed"),
    ),
)
@pytest.mark.parametrize(
    "profile_id",
    (
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        v13_runtime.ROLLOVER_PROFILE_2026_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    ),
)
def test_versioned_result_parser_isolates_forced_exit_guards(
    tmp_path, mutation, message, profile_id,
):
    plan = _plan(tmp_path, profile_id)
    statistics = _statistics(plan)
    aggregates = json.loads(statistics[runtime.AGGREGATES_STATISTIC_NAME])
    forced = aggregates["engine_forced_delisting"]
    if mutation == "extra":
        forced["raw_events"] = []
    elif mutation == "schema":
        forced["schema"] = "arv2-order-level-forced-delisting-summary-v0"
    elif mutation == "incomplete":
        forced["accounting_complete"] = False
    elif mutation == "bool_count":
        forced["order_count"] = False
    elif mutation == "negative_count":
        forced["absolute_filled_quantity"] = -1
    elif mutation == "raw_rows":
        forced["raw_order_rows_in_summary"] = True
    elif mutation == "digest":
        forced["ledger_sha256"] = "g" * 64
    elif mutation == "count":
        forced["event_count"] = 1
    elif mutation == "notional":
        forced["filled_notional"] = "-1"
    elif mutation == "fee":
        forced["actual_engine_fee_amount"] = "1"
    else:
        aggregates["forced_exit_invalidated_pending_rebalance_count"] = 1
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = _canonical(
        aggregates
    ).decode("ascii")
    launch, response = _result_response(plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="^" + message + "$",
    ):
        adapter._parse_result(response, plan, launch)


@pytest.mark.parametrize(
    "profile_id",
    (
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    ),
)
def test_diagnostic_result_parser_authenticates_bounded_skipped_unpriced_evidence(
    tmp_path, profile_id,
):
    plan = _plan(tmp_path, profile_id)
    statistics = _v14_skipped_statistics(plan)
    launch, response = _result_response(plan, statistics)

    assert adapter._parse_result(response, plan, launch) == tuple(
        sorted(statistics.items())
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "policy", "extra", "bad_session", "unsorted_hashes",
        "non_string_hash", "missing_path", "path", "count", "omitted_count",
    ),
)
@pytest.mark.parametrize(
    "profile_id",
    (
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    ),
)
def test_diagnostic_result_parser_refuses_each_skipped_unpriced_evidence_mutation(
    tmp_path, mutation, profile_id,
):
    plan = _plan(tmp_path, profile_id)
    statistics = _v14_skipped_statistics(plan)
    aggregate = json.loads(statistics[runtime.AGGREGATES_STATISTIC_NAME])
    evidence = aggregate["skipped_unpriced_decision_evidence"]
    record = evidence["records"][0]
    if mutation == "policy":
        aggregate["skipped_unpriced_decision_evidence_policy"] = "changed"
    elif mutation == "extra":
        evidence["raw_security_ids"] = []
    elif mutation == "bad_session":
        record["decision_session"] = "2026-02-30"
    elif mutation == "unsorted_hashes":
        record["retained_missing_security_sha256s"].reverse()
    elif mutation == "non_string_hash":
        record["retained_missing_security_sha256s"][0] = 1
    elif mutation == "missing_path":
        record["missing_security_path_sha256"] = "0" * 64
    elif mutation == "path":
        evidence["path_sha256"] = "0" * 64
    elif mutation == "count":
        evidence["skipped_decision_count"] = 2
    else:
        record["omitted_missing_security_count"] = 1
    meta = json.loads(statistics[runtime.META_STATISTIC_NAME])
    meta["aggregates_sha256"] = hashlib.sha256(_canonical(aggregate)).hexdigest()
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = _canonical(aggregate).decode(
        "ascii"
    )
    statistics[runtime.META_STATISTIC_NAME] = _canonical(meta).decode("ascii")
    launch, response = _result_response(plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="^order-level skipped-unpriced",
    ):
        adapter._parse_result(response, plan, launch)


def test_v15_result_parser_accepts_exact_retirement_and_terminal_reconciliation(
    tmp_path,
):
    plan = _plan(tmp_path, v15_runtime.ACCOUNT_PROFILE_2026_ID)
    statistics = _v15_retirement_statistics(plan)
    launch, response = _result_response(plan, statistics)

    assert adapter._parse_result(response, plan, launch) == tuple(
        sorted(statistics.items())
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "retirement_without_forced_exit",
        "retirement_count_bound",
        "retired_weight_bound",
        "terminal_equity",
        "terminal_adjustment",
        "empty_path",
    ),
)
def test_v15_result_parser_refuses_each_account_reconciliation_mutation(
    tmp_path, mutation,
):
    plan = _plan(tmp_path, v15_runtime.ACCOUNT_PROFILE_2026_ID)
    statistics = (
        _statistics(plan)
        if mutation == "empty_path"
        else _v15_retirement_statistics(plan)
    )
    aggregate = json.loads(statistics[runtime.AGGREGATES_STATISTIC_NAME])
    if mutation == "retirement_without_forced_exit":
        forced = aggregate["engine_forced_delisting"]
        forced.update({
            "order_count": 0,
            "event_count": 0,
            "fill_event_count": 0,
            "terminal_order_count": 0,
            "absolute_filled_quantity": 0,
            "filled_notional": "0",
        })
    elif mutation == "retirement_count_bound":
        aggregate["delisted_zero_holding_target_retirement_count"] = 40
    elif mutation == "retired_weight_bound":
        aggregate["delisted_zero_holding_target_retired_weight_total"] = "0.99"
    elif mutation == "terminal_equity":
        aggregate["terminal_account_observation_equity"] = "1099999"
    elif mutation == "terminal_adjustment":
        aggregate["terminal_account_observation_adjustment"] = "-99"
    else:
        aggregate["delisted_zero_holding_target_path_sha256"] = "a" * 64
    meta = json.loads(statistics[runtime.META_STATISTIC_NAME])
    meta["aggregates_sha256"] = hashlib.sha256(_canonical(aggregate)).hexdigest()
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = _canonical(aggregate).decode(
        "ascii"
    )
    statistics[runtime.META_STATISTIC_NAME] = _canonical(meta).decode("ascii")
    launch, response = _result_response(plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match=(
            "order-level retired delisted target accounting changed"
            if mutation in {
                "retirement_without_forced_exit",
                "retirement_count_bound",
                "retired_weight_bound",
                "empty_path",
            }
            else "order-level aggregate execution or coverage invariant changed"
        ),
    ):
        adapter._parse_result(response, plan, launch)


@pytest.mark.parametrize(
    "profile_id",
    (
        runtime.PROXY_PROFILE_2026_ID,
        runtime.PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.ENUM_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.ENUM_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.CASH_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.CASH_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.TICKET_PROFILE_2025_ID,
        runtime.TICKET_PROFILE_2026_ID,
        runtime.REFLECTED_TICKET_PROFILE_2025_ID,
        runtime.REFLECTED_TICKET_PROFILE_2026_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2025_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        v13_runtime.ROLLOVER_PROFILE_2025_ID,
        v13_runtime.ROLLOVER_PROFILE_2026_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2025_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2025_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    ),
)
def test_proxy_result_parser_requires_full_weight_ratios_and_overlap_disclosure(
    tmp_path, profile_id
):
    plan = _plan(tmp_path, profile_id)
    statistics = _statistics(plan)
    assert len(
        statistics[runtime.AGGREGATES_STATISTIC_NAME].encode("ascii")
    ) <= adapter._maximum_statistic_bytes(profile_id)
    launch, response = _result_response(plan, statistics)
    assert adapter._parse_result(response, plan, launch) == tuple(
        sorted(statistics.items())
    )
    for update in (
        {"qqq_proxy_overlap_disclosure": "exact QQQ replication"},
        {"maximum_qqq_proxy_constituent_weight_ratio": "0.21"},
        {"mean_qqq_proxy_constituent_weight_ratio": "0.13"},
        {
            "mean_qqq_proxy_constituent_weight_ratio": "0.14000000000000000000000000001",
            "maximum_qqq_proxy_constituent_weight_ratio": "0.14000000000000000000000000001",
        },
        {"minimum_required_resolved_constituent_weight_ratio": "0.95"},
        {"target_weight_basis": runtime.TARGET_WEIGHT_BASIS},
        {"raw_security_rows": []},
    ):
        launch, response = _result_response(
            plan, _statistics(plan, aggregate_update=update)
        )
        with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionError):
            adapter._parse_result(response, plan, launch)


@pytest.mark.parametrize(
    "profile_id",
    (
        runtime.PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.ENUM_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.ENUM_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.CASH_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.CASH_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.TICKET_PROFILE_2025_ID,
        runtime.TICKET_PROFILE_2026_ID,
        runtime.REFLECTED_TICKET_PROFILE_2025_ID,
        runtime.REFLECTED_TICKET_PROFILE_2026_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2025_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        v13_runtime.ROLLOVER_PROFILE_2025_ID,
        v13_runtime.ROLLOVER_PROFILE_2026_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2025_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
    ),
)
def test_preopen_result_cannot_shift_first_execution_session(
    tmp_path, profile_id
):
    plan = _plan(tmp_path, profile_id)
    launch, response = _result_response(
        plan,
        _statistics(
            plan,
            aggregate_update={"QQQ_first_execution_session": "2025-01-06"},
        ),
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="order-level aggregate execution or coverage invariant changed",
    ):
        adapter._parse_result(response, plan, launch)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("extra", "order-level custom result key inventory changed"),
        ("profile", "order-level aggregate runtime lineage changed"),
        ("package", "order-level aggregate runtime lineage changed"),
        ("activation", "order-level aggregate runtime lineage changed"),
        ("digest", "order-level aggregate digest changed"),
        ("non_ascii", "order-level custom result is not ASCII JSON"),
        ("oversize", "order-level custom result value exceeded its exact bound"),
    ),
)
def test_result_parser_refusals_are_exact_and_isolated(tmp_path, mutation, message):
    plan = _plan(tmp_path)
    statistics = _statistics(plan)
    if mutation == "extra":
        statistics["ARV2_UNEXPECTED"] = "{}"
    elif mutation == "profile":
        statistics = _statistics(plan, meta_update={"profile_id": "wrong"})
    elif mutation == "package":
        statistics = _statistics(plan, meta_update={"package_sha256": "0" * 64})
    elif mutation == "activation":
        statistics = _statistics(
            plan, meta_update={"activation_manifest_sha256": "f" * 64}
        )
    elif mutation == "digest":
        statistics = _statistics(plan, meta_update={"aggregates_sha256": "0" * 64})
    elif mutation == "non_ascii":
        statistics[runtime.AGGREGATES_STATISTIC_NAME] = '{"value":"é"}'
    else:
        statistics[runtime.AGGREGATES_STATISTIC_NAME] = "x" * (
            adapter.MAX_STATISTIC_BYTES + 1
        )
    launch, response = _result_response(plan, statistics)

    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionError) as exc:
        adapter._parse_result(response, plan, launch)

    assert str(exc.value) == message


@pytest.mark.parametrize(
    "hostile_value",
    (
        '{"RAW_REMOTE_MARKER":',
        '{"RAW_REMOTE_MARKER":"\N{LATIN SMALL LETTER E WITH ACUTE}"}',
        '{"RAW_REMOTE_MARKER":"\ud800"}',
    ),
)
def test_result_parser_severs_malformed_remote_content_from_exceptions(
    tmp_path, hostile_value
):
    plan = _plan(tmp_path)
    statistics = _statistics(plan)
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = hostile_value
    launch, response = _result_response(plan, statistics)

    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionError) as caught:
        adapter._parse_result(response, plan, launch)

    assert "RAW_REMOTE_MARKER" not in _exception_graph_text(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_strict_object_severs_malformed_remote_bytes_from_exceptions():
    marker = b'{"RAW_REMOTE_MARKER":\xff}'

    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionError) as caught:
        adapter._strict_object(marker, "remote object")

    assert "RAW_REMOTE_MARKER" not in _exception_graph_text(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_result_parser_severs_surrogate_safe_name_from_exceptions(tmp_path):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(
            plan,
            meta_update={
                "symbol_resolution_id": "RAW_REMOTE_NAME_MARKER_\ud800"
            },
        ),
    )

    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionError) as caught:
        adapter._parse_result(response, plan, launch)

    assert "RAW_REMOTE_NAME_MARKER" not in _exception_graph_text(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_launch_and_result_controls_are_independently_one_use(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    execution_authority = _execution_authority(plan, monkeypatch)
    launch_control = adapter._spend_launch_control(
        plan, execution_authority, "2026-09-18T20:00:00Z"
    )
    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionLocked) as exc:
        adapter._spend_launch_control(
            plan, execution_authority, "2026-09-18T20:00:00Z"
        )
    assert str(exc.value).startswith(
        "launch: control already exists or is unavailable;"
    )
    launch_raw = json.loads(launch_control.control_bytes)
    assert launch_raw["execution_authority_sha256"] == (
        execution_authority.authority_sha256
    )
    assert launch_raw["owner_signature_authority_sha256"] == (
        execution_authority.owner_signature_authority_sha256
    )
    assert launch_raw["owner_signature_sha256"] == (
        execution_authority.owner_signature_sha256
    )
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="persisted order-level launch control changed",
    ):
        adapter.load_order_level_launch_control(
            plan=plan,
            execution_authority=dataclasses.replace(
                execution_authority, authority_sha256="f" * 64
            ),
        )

    launch = adapter._new_launch(
        plan, launch_control, 123, "compile-one", "backtest-one", "Queued"
    )
    launch_payload = adapter._launch_receipt_bytes(launch)
    adapter._write_private_once(
        adapter._launch_receipt_path(plan), launch_payload, "launch receipt"
    )
    adapter._register_launch_authority(
        launch, plan, launch_control, launch_payload
    )
    terminal = _persisted_terminal(plan, launch)
    result_authority = _result_read_authority(
        plan,
        execution_authority,
        launch_control,
        launch,
        terminal,
        monkeypatch,
    )
    result_control = adapter._spend_result_control(
        plan, launch, terminal, result_authority, "2026-09-18T21:00:00Z"
    )
    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionLocked) as exc:
        adapter._spend_result_control(
            plan,
            launch,
            terminal,
            result_authority,
            "2026-09-18T21:00:00Z",
        )
    assert str(exc.value).startswith(
        "result_read: control already exists or is unavailable;"
    )
    result_raw = json.loads(result_control.control_bytes)
    assert result_raw["result_read_authority_sha256"] == (
        result_authority.authority_sha256
    )
    assert result_raw["owner_signature_authority_sha256"] == (
        result_authority.owner_signature_authority_sha256
    )
    assert result_raw["owner_signature_sha256"] == (
        result_authority.owner_signature_sha256
    )
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="persisted order-level result control changed",
    ):
        adapter.load_order_level_result_control(
            plan=plan,
            launch=launch,
            terminal=terminal,
            result_read_authority=dataclasses.replace(
                result_authority, authority_sha256="e" * 64
            ),
        )
    assert launch_control.control_path != result_control.control_path


def test_control_directory_refuses_group_or_world_access(tmp_path):
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir(mode=0o755)
    unsafe.chmod(0o755)
    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionError) as exc:
        adapter._private_directory(unsafe)
    assert str(exc.value) == "order-level control directory is not private"


def _real_plan_fixture(tmp_path, monkeypatch):
    lineage = {"schema": delta_package_builder.LINEAGE_SCHEMA, "fixture": True}
    lineage_sha = hashlib.sha256(canonical_json_bytes(lineage)).hexdigest()
    payload = b"fixture-activation"
    descriptor = SimpleNamespace(
        role="activation_manifest",
        ordinal=0,
        object_store_key="arv2/order-fixture/transport-manifest.json",
        content_sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
        activation_manifest=True,
    )
    package = SimpleNamespace(
        package_id="arv2-preliminary-qc-package-order-fixture",
        package_sha256="b" * 64,
        source_disposition_sha256=lineage_sha,
        upload_objects=(descriptor,),
    )
    delta = delta_package_builder.AcceptedRiskDeltaOrderPackage(
        package=package,
        lineage=lineage,
        lineage_sha256=lineage_sha,
        prior_contribution_count=1,
        delta_contribution_count=1,
        extended_membership_count=1,
        decision_cutoff_session=delta_package_builder.DELTA_DECISION_END_SESSION,
        final_execution_session=delta_package_builder.FINAL_EXECUTION_SESSION,
        current_snapshot_identity_only=True,
        refreshed_security_master=False,
        provider_access=False,
        quantconnect_access=False,
        outcome_access=False,
        orders=False,
        trading=False,
    )
    monkeypatch.setattr(
        package_builder,
        "require_accepted_risk_preliminary_package",
        lambda value: value,
    )
    projection = projection_builder.build_accepted_risk_order_level_qc_projection(
        delta, profile_id=runtime.PROFILE_2025_ID
    )
    monkeypatch.setattr(adapter, "_PINNED_REQUIRE_PACKAGE", lambda value: value)
    monkeypatch.setattr(adapter, "_PINNED_REQUIRE_PROJECTION", lambda value: value)
    monkeypatch.setattr(
        adapter,
        "_PINNED_ITER_UPLOADS",
        lambda _value: iter(((descriptor, payload),)),
    )
    plan = adapter.build_order_level_submission_plan(
        delta_package=delta,
        projection=projection,
        organization_id="organization-one",
        project_name="private-order-project",
        backtest_name="private-order-backtest",
        control_directory=tmp_path,
    )
    return plan, delta, projection


def _real_plan_test_execution_operations():
    execution_verifier, _result_verifier = _test_signature_verifiers()
    return adapter._make_execution_authority_operations(
        signature_requirer=execution_verifier,
        plan_requirer=adapter.require_order_level_submission_plan,
    )


def _real_plan_test_execution_authority(plan):
    render, load, _require = _real_plan_test_execution_operations()
    payload = render(plan=plan)
    return load(
        plan=plan,
        receipt_bytes=payload,
        owner_signature=_test_signature("formal_qc_execution", payload),
    )


def _real_plan_test_result_operations():
    _execution_verifier, result_verifier = _test_signature_verifiers()
    _render, _load, require_execution = (
        _real_plan_test_execution_operations()
    )
    return adapter._make_result_read_authority_operations(
        signature_requirer=result_verifier,
        execution_authority_requirer=require_execution,
        context_requirer=adapter._require_result_context,
    )


def _real_plan_test_result_authority(
    plan, execution_authority, control, launch, terminal
):
    render, load, _require = _real_plan_test_result_operations()
    payload = render(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
    )
    return load(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
        receipt_bytes=payload,
        owner_signature=_test_signature("formal_qc_result_read", payload),
    )


def test_upload_entries_preserve_role_local_zero_ordinals_and_exact_identity(
    monkeypatch,
):
    payloads = (b"manifest", b"members", b"activation")
    roles = ("evaluator_manifest", "memberships", "activation_manifest")
    descriptors = tuple(
        SimpleNamespace(
            role=role,
            ordinal=0,
            object_store_key=f"arv2/order-fixture/{index}.bin",
            byte_count=len(payload),
            content_sha256=hashlib.sha256(payload).hexdigest(),
            activation_manifest=index == len(payloads) - 1,
        )
        for index, (role, payload) in enumerate(zip(roles, payloads, strict=True))
    )
    package = SimpleNamespace(upload_objects=descriptors)
    monkeypatch.setattr(
        adapter,
        "_PINNED_ITER_UPLOADS",
        lambda value: iter(zip(value.upload_objects, payloads, strict=True)),
    )

    entries = adapter._upload_entries(package)

    assert tuple(item.role for item in entries) == roles
    assert tuple(item.ordinal for item in entries) == (0, 0, 0)
    assert tuple(item.activation_manifest for item in entries) == (
        False,
        False,
        True,
    )
    assert tuple(item.content_md5 for item in entries) == tuple(
        hashlib.md5(payload, usedforsecurity=False).hexdigest()
        for payload in payloads
    )

    copied = SimpleNamespace(**vars(descriptors[0]))
    monkeypatch.setattr(
        adapter,
        "_PINNED_ITER_UPLOADS",
        lambda _value: iter(
            (
                (copied, payloads[0]),
                *((item, payload) for item, payload in zip(
                    descriptors[1:], payloads[1:], strict=True
                )),
            )
        ),
    )
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="package upload inventory changed",
    ):
        adapter._upload_entries(package)


def test_pinned_profile_census_matches_authenticated_package_session_axis():
    axis = delta_package_builder._successor_sessions()
    assert axis[-1] == delta_package_builder.FINAL_EXECUTION_SESSION

    for binding in adapter._PINNED_RUNTIME_PROFILE_BINDINGS:
        (
            profile_id,
            _profile_sha256,
            _score_source_view_id,
            first_execution_session,
            decision_count,
            observation_count,
            return_interval_count,
            _expected_names,
        ) = binding
        start = _profile(profile_id)[
            "evaluation_start_session"
        ]
        expected_sessions = tuple(
            session
            for session in axis
            if start <= session <= delta_package_builder.FINAL_EXECUTION_SESSION
        )
        decisions, *_positions = (
            runtime.AcceptedRiskQqqOrderLevelQcRuntime._decision_axis(
                axis, start
            )
        )

        assert expected_sessions[1] == first_execution_session
        assert len(decisions) == decision_count
        assert len(expected_sessions) == observation_count
        assert len(expected_sessions) - 1 == return_interval_count


def test_preopen_profile_extension_keeps_old_bindings_and_proxy_result_gate():
    assert adapter.PROFILE_IDS == (
        runtime.PROFILE_IDS
        + v12_runtime.FORCED_EXIT_PROFILE_IDS
        + v13_runtime.ROLLOVER_PROFILE_IDS
        + v14_runtime.DIAGNOSTIC_PROFILE_IDS
        + v15_runtime.ACCOUNT_PROFILE_IDS
    ) == (
        runtime.PROFILE_2025_ID,
        runtime.PROFILE_2026_ID,
        runtime.PROXY_PROFILE_2025_ID,
        runtime.PROXY_PROFILE_2026_ID,
        runtime.PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.ENUM_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.ENUM_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.CASH_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.CASH_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.TICKET_PROFILE_2025_ID,
        runtime.TICKET_PROFILE_2026_ID,
        runtime.REFLECTED_TICKET_PROFILE_2025_ID,
        runtime.REFLECTED_TICKET_PROFILE_2026_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2025_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        v13_runtime.ROLLOVER_PROFILE_2025_ID,
        v13_runtime.ROLLOVER_PROFILE_2026_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2025_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2025_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    )
    assert adapter.PROXY_PROFILE_IDS == (
        runtime.PROXY_PROFILE_IDS
        + v12_runtime.FORCED_EXIT_PROFILE_IDS
        + v13_runtime.ROLLOVER_PROFILE_IDS
        + v14_runtime.DIAGNOSTIC_PROFILE_IDS
        + v15_runtime.ACCOUNT_PROFILE_IDS
    ) == (
        runtime.PROXY_PROFILE_2025_ID,
        runtime.PROXY_PROFILE_2026_ID,
        runtime.PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.NUMERIC_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.ENUM_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.ENUM_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.CASH_PREOPEN_PROXY_PROFILE_2025_ID,
        runtime.CASH_PREOPEN_PROXY_PROFILE_2026_ID,
        runtime.TICKET_PROFILE_2025_ID,
        runtime.TICKET_PROFILE_2026_ID,
        runtime.REFLECTED_TICKET_PROFILE_2025_ID,
        runtime.REFLECTED_TICKET_PROFILE_2026_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2025_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        v13_runtime.ROLLOVER_PROFILE_2025_ID,
        v13_runtime.ROLLOVER_PROFILE_2026_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2025_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2025_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    )
    bindings = adapter._PINNED_RUNTIME_PROFILE_BINDINGS
    assert tuple(binding[0] for binding in bindings) == adapter.PROFILE_IDS
    assert tuple(binding[1] for binding in bindings[:4]) == (
        "43ea09abd2b6eb9aef23cfb05ec7cb0c19c50451fb41ac78c3aeeac8bd60e518",
        "190637eb9145c4b3a9e844cb42eb84d24bb5b318afc56957f98bf9d413d8a3b6",
        "c3faf484e37d312de849589668b76ea68fa80b48413eb01e636f7e1a4170c86d",
        "af5e102c5dcd62878eb1046ac63f259e6c4cddf9944cd09c6a5826144a8a914a",
    )
    assert bindings[4][3:7] == ("2025-01-03", 91, 428, 427)
    assert bindings[5][3:7] == ("2026-01-05", 39, 178, 177)
    assert bindings[6][3:7] == ("2025-01-03", 91, 428, 427)
    assert bindings[7][3:7] == ("2026-01-05", 39, 178, 177)
    assert bindings[8][3:7] == ("2025-01-03", 91, 428, 427)
    assert bindings[9][3:7] == ("2026-01-05", 39, 178, 177)
    assert tuple(binding[1] for binding in bindings[-4:]) == (
        "d1367ac6dd6a7446632b381496ff02be8e602f02373b31ff6c81e9d704298200",
        "bfb77eacdaddb8566b649165eb4986ca038658bbc23d5eb95641f4cea13d0776",
        "884b61e586dd2265845e751675d3e2eaa452a4d04f3635206acd552455e81738",
        "13303b1940e3442f01d93020e62c43e196c88ec297ddace97a0f4dc024a14e7a",
    )
    assert adapter.ROLLOVER_PROFILE_IDS == v13_runtime.ROLLOVER_PROFILE_IDS
    assert adapter.FORCED_EXIT_PROFILE_IDS == (
        v12_runtime.FORCED_EXIT_PROFILE_IDS
        + v13_runtime.ROLLOVER_PROFILE_IDS
        + v14_runtime.DIAGNOSTIC_PROFILE_IDS
        + v15_runtime.ACCOUNT_PROFILE_IDS
    )
    assert adapter.DIAGNOSTIC_PROFILE_IDS == v14_runtime.DIAGNOSTIC_PROFILE_IDS
    assert adapter.ACCOUNT_PROFILE_IDS == v15_runtime.ACCOUNT_PROFILE_IDS
    assert adapter._PINNED_FORCED_EXIT_SUMMARY_SCHEMA == (
        v12_runtime.FORCED_EXIT_SUMMARY_SCHEMA
    )
    assert adapter._PINNED_DIAGNOSTIC_SUMMARY_SCHEMA == (
        v14_runtime.DIAGNOSTIC_SUMMARY_SCHEMA
    )
    assert adapter._PINNED_ACCOUNT_SUMMARY_SCHEMA == (
        v15_runtime.ACCOUNT_SUMMARY_SCHEMA
    )
    assert runtime.PROXY_SUMMARY_SCHEMA == "arv2-qqq-order-level-tilt-summary-v7"


@pytest.mark.parametrize(
    "profile_id",
    (
        runtime.PROFILE_2025_ID,
        runtime.PREOPEN_PROXY_PROFILE_2026_ID,
        v12_runtime.FORCED_EXIT_PROFILE_2026_ID,
        v13_runtime.ROLLOVER_PROFILE_2026_ID,
        v14_runtime.DIAGNOSTIC_PROFILE_2026_ID,
        v15_runtime.ACCOUNT_PROFILE_2026_ID,
    ),
)
def test_submission_plan_persists_and_reloads_against_exact_inputs(
    tmp_path, monkeypatch, profile_id
):
    lineage = {"schema": delta_package_builder.LINEAGE_SCHEMA, "fixture": True}
    lineage_sha = hashlib.sha256(canonical_json_bytes(lineage)).hexdigest()
    payload = b"fixture-activation"
    descriptor = SimpleNamespace(
        role="activation_manifest",
        ordinal=0,
        object_store_key="arv2/order-fixture/transport-manifest.json",
        content_sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
        activation_manifest=True,
    )
    package = SimpleNamespace(
        package_id="arv2-preliminary-qc-package-order-fixture",
        package_sha256="b" * 64,
        source_disposition_sha256=lineage_sha,
        upload_objects=(descriptor,),
    )
    delta = delta_package_builder.AcceptedRiskDeltaOrderPackage(
        package=package,
        lineage=lineage,
        lineage_sha256=lineage_sha,
        prior_contribution_count=1,
        delta_contribution_count=1,
        extended_membership_count=1,
        decision_cutoff_session=delta_package_builder.DELTA_DECISION_END_SESSION,
        final_execution_session=delta_package_builder.FINAL_EXECUTION_SESSION,
        current_snapshot_identity_only=True,
        refreshed_security_master=False,
        provider_access=False,
        quantconnect_access=False,
        outcome_access=False,
        orders=False,
        trading=False,
    )
    monkeypatch.setattr(
        package_builder,
        "require_accepted_risk_preliminary_package",
        lambda value: value,
    )
    projection = projection_builder.build_accepted_risk_order_level_qc_projection(
        delta, profile_id=profile_id
    )
    monkeypatch.setattr(adapter, "_PINNED_REQUIRE_PACKAGE", lambda value: value)
    monkeypatch.setattr(adapter, "_PINNED_REQUIRE_PROJECTION", lambda value: value)
    monkeypatch.setattr(
        adapter,
        "_PINNED_ITER_UPLOADS",
        lambda _value: iter(((descriptor, payload),)),
    )
    plan = adapter.build_order_level_submission_plan(
        delta_package=delta,
        projection=projection,
        organization_id="organization-one",
        project_name="private-order-project",
        backtest_name="private-order-backtest",
        control_directory=tmp_path,
    )

    path = adapter.persist_order_level_submission_plan(plan)
    loaded = adapter.load_order_level_submission_plan(
        plan_path=path,
        delta_package=delta,
        projection=projection,
        organization_id="organization-one",
    )

    assert loaded == plan
    assert path.stat().st_mode & 0o777 == 0o600

    render, load_authority, require_authority = (
        _real_plan_test_execution_operations()
    )
    authority_payload = render(plan=loaded)
    authority = load_authority(
        plan=loaded,
        receipt_bytes=authority_payload,
        owner_signature=_test_signature(
            "formal_qc_execution", authority_payload
        ),
    )
    assert require_authority(value=authority, plan=loaded) is authority


def test_unreviewed_profile_is_not_allowlisted(tmp_path, monkeypatch):
    lineage = {}
    lineage_sha256 = hashlib.sha256(canonical_json_bytes(lineage)).hexdigest()
    package = SimpleNamespace(
        package_id="package",
        package_sha256="1" * 64,
        source_disposition_sha256=lineage_sha256,
    )
    delta = object.__new__(delta_package_builder.AcceptedRiskDeltaOrderPackage)
    object.__setattr__(delta, "package", package)
    object.__setattr__(delta, "lineage", lineage)
    object.__setattr__(delta, "lineage_sha256", lineage_sha256)
    object.__setattr__(
        delta,
        "decision_cutoff_session",
        delta_package_builder.DELTA_DECISION_END_SESSION,
    )
    object.__setattr__(
        delta,
        "final_execution_session",
        delta_package_builder.FINAL_EXECUTION_SESSION,
    )
    object.__setattr__(delta, "current_snapshot_identity_only", True)
    object.__setattr__(delta, "refreshed_security_master", False)
    for field in (
        "provider_access",
        "quantconnect_access",
        "outcome_access",
        "orders",
        "trading",
    ):
        object.__setattr__(delta, field, False)
    projection = SimpleNamespace(profile_id="arv2-unreviewed-profile")
    monkeypatch.setattr(adapter, "_PINNED_REQUIRE_PACKAGE", lambda value: value)
    monkeypatch.setattr(adapter, "_PINNED_REQUIRE_PROJECTION", lambda value: value)

    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionError) as exc:
        adapter.build_order_level_submission_plan(
            delta_package=delta,
            projection=projection,
            organization_id="organization",
            project_name="project",
            backtest_name="backtest",
            control_directory=tmp_path / "private",
        )

    assert str(exc.value) == "order-level profile is not allowlisted"


def test_endpoint_budgets_have_no_live_paper_broker_or_deployment_surface():
    names = (
        adapter.EXECUTION_ENDPOINT_BUDGET_NAMES
        | adapter.STATUS_ENDPOINT_BUDGET_NAMES
        | adapter.RESULT_ENDPOINT_BUDGET_NAMES
    )
    assert not any(
        token in endpoint.casefold()
        for endpoint in names
        for token in adapter.FORBIDDEN_ENDPOINT_TOKENS
    )
    assert names == {
        "authenticate",
        "projects/read",
        "projects/create",
        "object/set",
        "object/properties",
        "files/read",
        "files/create",
        "files/update",
        "files/delete",
        "compile/create",
        "compile/read",
        "backtests/create",
        "backtests/list",
        "backtests/read",
    }


def test_transport_refuses_non_allowlisted_endpoint_before_network():
    calls = []

    def backend(*args):
        calls.append(args)
        raise AssertionError("network callback reached")

    client = formal_qc_transport.FormalQcTransport(
        http_transport=backend, clock=lambda: 1_800_000_000
    )
    capability = formal_qc_transport._mint_offline_test_capability(
        client,
        scope="submission",
        call_budget={"authenticate": 1},
    )
    with pytest.raises(formal_qc_transport.FormalQcTransportError) as exc:
        client._request_json(capability, "deploy/create", {})
    assert str(exc.value) == "QuantConnect endpoint is not allowlisted"
    assert calls == []


@pytest.mark.parametrize(
    "signature_case",
    ("missing", "wrong_purpose", "wrong_payload", "mutated_signature"),
)
def test_execution_authority_refuses_each_invalid_owner_signature(
    tmp_path, monkeypatch, signature_case
):
    plan = _plan(tmp_path)
    render, load, _require = _test_execution_operations()
    payload = render(plan=plan)
    if signature_case == "missing":
        signature = None
    elif signature_case == "wrong_purpose":
        signature = _test_signature("formal_qc_result_read", payload)
    elif signature_case == "wrong_payload":
        signature = _test_signature("formal_qc_execution", payload + b"x")
    else:
        signature = _test_signature(
            "formal_qc_execution", payload, mutated=True
        )
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="non-self-mintable owner execution signature is unavailable",
    ):
        load(
            plan=plan,
            receipt_bytes=payload,
            owner_signature=signature,
        )


def test_production_owner_signature_requirers_are_wired_fail_closed(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    render_execution, load_execution, _require_execution = (
        adapter._make_execution_authority_operations(
            signature_requirer=adapter.require_formal_execution_owner_signature,
            plan_requirer=lambda value: value,
            exact_plan_type=SimpleNamespace,
        )
    )
    execution_payload = render_execution(plan=plan)
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="non-self-mintable owner execution signature is unavailable",
    ):
        load_execution(
            plan=plan,
            receipt_bytes=execution_payload,
            owner_signature=None,
        )

    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    _render_test_execution, _load_test_execution, require_test_execution = (
        _test_execution_operations()
    )
    render_result, load_result, _require_result = (
        adapter._make_result_read_authority_operations(
            signature_requirer=adapter.require_formal_result_read_owner_signature,
            execution_authority_requirer=require_test_execution,
            context_requirer=adapter._require_result_context,
            exact_plan_type=SimpleNamespace,
        )
    )
    result_payload = render_result(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
    )
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="non-self-mintable owner result-read signature is unavailable",
    ):
        load_result(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=control,
            launch=launch,
            terminal=terminal,
            receipt_bytes=result_payload,
            owner_signature=None,
        )

@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("package_sha256", "0" * 64),
        ("projection_sha256", "0" * 64),
        ("organization_id_sha256", "0" * 64),
        ("project_name", "changed-project"),
        ("backtest_name", "changed-backtest"),
        ("status_poll_limit", 3),
        ("maximum_backtest_submissions", 2),
    ),
)
def test_execution_signature_binds_plan_and_every_external_action_limit(
    tmp_path, monkeypatch, field, changed
):
    plan = _plan(tmp_path)
    authority = _execution_authority(plan, monkeypatch)
    changed_plan = SimpleNamespace(**vars(plan))
    setattr(changed_plan, field, changed)

    _render, _load, require = _test_execution_operations()
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="execution authority receipt bytes changed",
    ):
        require(value=authority, plan=changed_plan)


def test_missing_execution_signature_refuses_before_control_or_transport(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    events = []

    class Client:
        def __getattr__(self, name):
            events.append(name)
            raise AssertionError("transport was inspected before authority")

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="exact order-level execution authority is required",
    ):
        adapter._execute_order_level_submission_once_impl(
            plan=plan,
            execution_authority=None,
            client=Client(),
            started_at_utc="2026-09-18T20:00:00Z",
            minter=lambda **_kwargs: object(),
            transport_verifier=lambda value: value,
            authority_verifier=_test_execution_operations()[2],
        )

    assert events == []
    assert not adapter._launch_control_path(plan).exists()


def test_mutated_valid_looking_execution_authority_refuses_before_control_or_transport(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    authority = dataclasses.replace(
        _execution_authority(plan, monkeypatch),
        backtest_name="different-valid-looking-backtest",
    )
    events = []

    class Client:
        def __getattr__(self, name):
            events.append(name)
            raise AssertionError("transport was inspected before authority")

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="order-level execution authority changed",
    ):
        adapter._execute_order_level_submission_once_impl(
            plan=plan,
            execution_authority=authority,
            client=Client(),
            started_at_utc="2026-09-18T20:00:00Z",
            minter=lambda **_kwargs: object(),
            transport_verifier=lambda value: value,
            authority_verifier=_test_execution_operations()[2],
        )

    assert events == []
    assert not adapter._launch_control_path(plan).exists()


def test_status_and_launch_recovery_also_require_execution_signature_first(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    events = []

    class Client:
        def __getattr__(self, name):
            events.append(name)
            raise AssertionError("transport was inspected before authority")

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="exact order-level execution authority is required",
    ):
        adapter._inspect_order_level_terminal_status_impl(
            plan=plan,
            execution_authority=None,
            launch_control=control,
            launch=launch,
            client=Client(),
            minter=lambda **_kwargs: object(),
            transport_verifier=lambda value: value,
            authority_verifier=_test_execution_operations()[2],
        )
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="exact order-level execution authority is required",
    ):
        adapter._recover_order_level_launch_receipt_once_impl(
            plan=plan,
            execution_authority=None,
            launch_control=control,
            client=Client(),
            minter=lambda **_kwargs: object(),
            transport_verifier=lambda value: value,
            authority_verifier=_test_execution_operations()[2],
        )

    assert events == []


def test_submission_refusal_severs_transport_credential_traceback_locals(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    monkeypatch.setattr(
        adapter, "persist_order_level_submission_plan", lambda _value: tmp_path
    )
    execution_authority = _execution_authority(plan, monkeypatch)

    def leaking_transport(*_args):
        credential_material = (
            "RAW_QC_USER_CREDENTIAL_MARKER",
            "RAW_QC_TOKEN_CREDENTIAL_MARKER",
        )
        assert credential_material
        raise RuntimeError("transport failed")

    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionLocked) as caught:
        adapter._execute_order_level_submission_once_impl(
            plan=plan,
            execution_authority=execution_authority,
            client=object(),
            started_at_utc="2026-09-18T20:00:00Z",
            minter=lambda **_kwargs: object(),
            transport_verifier=lambda value: value,
            authority_verifier=_test_execution_operations()[2],
            _transport=leaking_transport,
        )

    traceback_locals = _exception_internal_traceback_locals_text(caught.value)
    assert "RAW_QC_USER_CREDENTIAL_MARKER" not in traceback_locals
    assert "RAW_QC_TOKEN_CREDENTIAL_MARKER" not in traceback_locals
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_launch_recovery_refusal_severs_transport_credential_traceback_locals(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control = adapter._spend_launch_control(
        plan, execution_authority, "2026-09-18T20:00:00Z"
    )
    adapter._persist_launch_checkpoint(plan, control, 123, "compile-one")

    def leaking_transport(*_args):
        credential_material = (
            "RAW_QC_USER_CREDENTIAL_MARKER",
            "RAW_QC_TOKEN_CREDENTIAL_MARKER",
        )
        assert credential_material
        raise RuntimeError("transport failed")

    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionLocked) as caught:
        adapter._recover_order_level_launch_receipt_once_impl(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=control,
            client=object(),
            minter=lambda **_kwargs: object(),
            transport_verifier=lambda value: value,
            authority_verifier=_test_execution_operations()[2],
            _transport=leaking_transport,
        )

    traceback_locals = _exception_internal_traceback_locals_text(caught.value)
    assert "RAW_QC_USER_CREDENTIAL_MARKER" not in traceback_locals
    assert "RAW_QC_TOKEN_CREDENTIAL_MARKER" not in traceback_locals
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_status_poll_budget_is_cumulative_across_calls_and_errors(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    calls = []
    minted = []

    class Client:
        def _request_json(self, _capability, endpoint, request):
            calls.append((endpoint, request))
            if len(calls) == 1:
                credential_material = (
                    "RAW_STATUS_USER_CREDENTIAL_MARKER",
                    "RAW_STATUS_TOKEN_CREDENTIAL_MARKER",
                )
                assert credential_material
                raise RuntimeError("RAW_REMOTE_STATUS_MARKER")
            return {"status": "Running"}

    monkeypatch.setattr(
        adapter,
        "_PINNED_TRANSPORT_CALL",
        lambda client, capability, method, *args: getattr(client, method)(
            capability, *args
        ),
    )
    monkeypatch.setattr(
        adapter,
        "_PINNED_PARSE_STATUS",
        lambda _response, **_kwargs: SimpleNamespace(status="Running"),
    )
    monkeypatch.setattr(adapter, "_wait", lambda _seconds: None)

    arguments = {
        "plan": plan,
        "execution_authority": execution_authority,
        "launch_control": control,
        "launch": launch,
        "client": Client(),
        "minter": lambda **kwargs: minted.append(kwargs) or object(),
        "transport_verifier": lambda value: value,
        "authority_verifier": _test_execution_operations()[2],
        "_transport": _test_transport,
    }
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionLocked,
        match="terminal_status: RuntimeError;",
    ) as caught:
        adapter._inspect_order_level_terminal_status_impl(**arguments)
    assert "RAW_REMOTE_STATUS_MARKER" not in _exception_graph_text(caught.value)
    traceback_locals = _exception_internal_traceback_locals_text(caught.value)
    assert "RAW_STATUS_USER_CREDENTIAL_MARKER" not in traceback_locals
    assert "RAW_STATUS_TOKEN_CREDENTIAL_MARKER" not in traceback_locals
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionLocked,
        match="poll limit exhausted",
    ):
        adapter._inspect_order_level_terminal_status_impl(**arguments)
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionLocked,
        match="status poll budget exhausted",
    ):
        adapter._inspect_order_level_terminal_status_impl(**arguments)

    checkpoints = adapter._load_status_poll_checkpoints(
        plan, execution_authority, control, launch
    )
    assert tuple(item.poll_count for item in checkpoints) == (1, 2)
    assert len(calls) == 2
    assert [entry["call_budget"] for entry in minted] == [
        {"backtests/list": 1},
        {"backtests/list": 1},
    ]


def test_status_poll_checkpoint_is_lineage_bound_private_and_reloadable(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    checkpoint = adapter._spend_status_poll_checkpoint(
        plan, execution_authority, control, launch, ()
    )
    path = adapter._status_poll_checkpoint_path(plan, 1)

    assert adapter._load_status_poll_checkpoints(
        plan, execution_authority, control, launch
    ) == (checkpoint,)
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="status poll checkpoint lineage changed",
    ):
        adapter._load_status_poll_checkpoints(
            plan,
            dataclasses.replace(execution_authority, authority_sha256="f" * 64),
            control,
            launch,
        )

    path.chmod(0o644)
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="stable owner-only regular file",
    ):
        adapter._load_status_poll_checkpoints(
            plan, execution_authority, control, launch
        )
    path.chmod(0o600)

    hardlink = tmp_path / "poll-checkpoint-hardlink"
    os.link(path, hardlink)
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="stable owner-only regular file",
    ):
        adapter._load_status_poll_checkpoints(
            plan, execution_authority, control, launch
        )
    hardlink.unlink()

    backing = tmp_path / "poll-checkpoint-backing"
    path.rename(backing)
    path.symlink_to(backing)
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="status poll checkpoint is unavailable",
    ):
        adapter._load_status_poll_checkpoints(
            plan, execution_authority, control, launch
        )
    path.unlink()
    backing.rename(path)

    original = path.read_bytes()
    raw = json.loads(original)
    raw["project_id"] = 999
    path.write_bytes(_canonical(raw))
    path.chmod(0o600)
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="status poll checkpoint",
    ):
        adapter._load_status_poll_checkpoints(
            plan, execution_authority, control, launch
        )


def test_terminal_status_receipt_reloads_without_minting_more_poll_budget(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    calls = []
    minted = []

    class Client:
        def _request_json(self, _capability, endpoint, request):
            calls.append((endpoint, request))
            return {"status": "Completed."}

    monkeypatch.setattr(
        adapter,
        "_PINNED_TRANSPORT_CALL",
        lambda client, capability, method, *args: getattr(client, method)(
            capability, *args
        ),
    )
    monkeypatch.setattr(
        adapter,
        "_PINNED_PARSE_STATUS",
        lambda _response, **_kwargs: SimpleNamespace(status="Completed."),
    )
    arguments = {
        "plan": plan,
        "execution_authority": execution_authority,
        "launch_control": control,
        "launch": launch,
        "client": Client(),
        "minter": lambda **kwargs: minted.append(kwargs) or object(),
        "transport_verifier": lambda value: value,
        "authority_verifier": _test_execution_operations()[2],
        "_transport": _test_transport,
    }

    terminal = adapter._inspect_order_level_terminal_status_impl(**arguments)
    reloaded = adapter._inspect_order_level_terminal_status_impl(**arguments)

    assert reloaded == terminal
    assert reloaded is not terminal
    assert len(calls) == 1
    assert len(minted) == 1


@pytest.mark.parametrize(
    "signature_case",
    ("missing", "wrong_purpose", "wrong_payload", "mutated_signature"),
)
def test_result_read_authority_refuses_each_invalid_owner_signature(
    tmp_path, monkeypatch, signature_case
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    render, load, _require = _test_result_operations()
    payload = render(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
    )
    if signature_case == "missing":
        signature = None
    elif signature_case == "wrong_purpose":
        signature = _test_signature("formal_qc_execution", payload)
    elif signature_case == "wrong_payload":
        signature = _test_signature("formal_qc_result_read", payload + b"x")
    else:
        signature = _test_signature(
            "formal_qc_result_read", payload, mutated=True
        )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="non-self-mintable owner result-read signature is unavailable",
    ):
        load(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=control,
            launch=launch,
            terminal=terminal,
            receipt_bytes=payload,
            owner_signature=signature,
        )


@pytest.mark.parametrize(
    ("profile_id", "expected_limit"),
    (
        (runtime.CASH_PREOPEN_PROXY_PROFILE_2026_ID, 4096),
        (runtime.TICKET_PROFILE_2026_ID, 8192),
        (runtime.REFLECTED_TICKET_PROFILE_2026_ID, 8192),
        (v12_runtime.FORCED_EXIT_PROFILE_2026_ID, 8192),
        (v13_runtime.ROLLOVER_PROFILE_2026_ID, 8192),
        (v14_runtime.DIAGNOSTIC_PROFILE_2026_ID, 8192),
        (v15_runtime.ACCOUNT_PROFILE_2026_ID, 8192),
    ),
)
def test_result_read_authority_binds_profile_specific_statistic_limit(
    tmp_path, monkeypatch, profile_id, expected_limit
):
    plan = _plan(tmp_path, profile_id)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    render, _load, _require = _test_result_operations()

    candidate = json.loads(render(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
    ))

    assert candidate["maximum_custom_statistic_bytes_each"] == expected_limit


def test_v14_result_read_authority_binds_diagnostic_field_inventory(
    tmp_path, monkeypatch,
):
    plan = _plan(tmp_path, v14_runtime.DIAGNOSTIC_PROFILE_2026_ID)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    render, _load, _require = _test_result_operations()

    candidate = json.loads(render(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
    ))

    assert candidate["aggregate_field_inventory_sha256"] == hashlib.sha256(
        _canonical(sorted(adapter._DIAGNOSTIC_AGGREGATE_FIELDS))
    ).hexdigest()
    assert candidate["aggregate_field_inventory_sha256"] != hashlib.sha256(
        _canonical(sorted(adapter._FORCED_EXIT_AGGREGATE_FIELDS))
    ).hexdigest()


def test_v15_result_read_authority_binds_account_field_inventory(
    tmp_path, monkeypatch,
):
    plan = _plan(tmp_path, v15_runtime.ACCOUNT_PROFILE_2026_ID)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    render, _load, _require = _test_result_operations()

    candidate = json.loads(render(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
    ))

    assert candidate["aggregate_field_inventory_sha256"] == hashlib.sha256(
        _canonical(sorted(adapter._ACCOUNT_AGGREGATE_FIELDS))
    ).hexdigest()
    assert candidate["aggregate_field_inventory_sha256"] != hashlib.sha256(
        _canonical(sorted(adapter._DIAGNOSTIC_AGGREGATE_FIELDS))
    ).hexdigest()


def test_result_read_signature_binds_only_aggregate_inventory_and_exact_run(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    payload = _test_result_operations()[0](
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
    )
    raw = json.loads(payload)

    assert raw["plan_sha256"] == plan.plan_sha256
    assert raw["execution_authority_sha256"] == execution_authority.authority_sha256
    assert raw["launch_receipt_sha256"] == launch.receipt_sha256
    assert raw["terminal_receipt_sha256"] == terminal.receipt_sha256
    assert raw["expected_custom_statistic_names"] == list(
        plan.expected_custom_statistic_names
    )
    assert raw["result_call_budget"] == {"backtests/read": 1}
    assert raw["maximum_result_reads"] == 1
    assert raw["aggregate_only"] is True
    assert raw["raw_provider_or_security_rows_authorized"] is False
    assert raw["standard_statistics_authorized"] is False
    assert raw["logs_orders_charts_runtime_statistics_authorized"] is False
    assert raw["paper_live_deployment_funded_trading_authorized"] is False
    assert raw["retry_after_ambiguity"] is False


def test_missing_result_signature_refuses_before_control_or_transport(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    events = []

    class Client:
        def __getattr__(self, name):
            events.append(name)
            raise AssertionError("transport was inspected before authority")

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="exact order-level result-read authority is required",
    ):
        adapter._read_order_level_aggregate_result_once_impl(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=control,
            launch=launch,
            terminal=terminal,
            result_read_authority=None,
            client=Client(),
            started_at_utc="2026-09-18T21:00:00Z",
            minter=lambda **_kwargs: object(),
            transport_verifier=lambda value: value,
            result_authority_verifier=_test_result_operations()[2],
            result_parser=adapter._SEALED_RESULT_PARSER,
            _transport=_test_transport,
        )

    assert events == []
    assert not adapter._result_control_path(plan).exists()


@pytest.mark.parametrize(
    "rebound_name",
    (
        "require_formal_execution_owner_signature",
        "require_formal_result_read_owner_signature",
        "render_order_level_execution_authority_candidate",
        "load_order_level_execution_authority",
        "require_order_level_execution_authority",
        "render_order_level_result_read_authority_candidate",
        "load_order_level_result_read_authority",
        "require_order_level_result_read_authority",
        "_require_result_context",
        "_execution_call_budget",
        "_execute_order_level_submission_once_impl",
        "_inspect_order_level_terminal_status_impl",
        "_recover_order_level_launch_receipt_once_impl",
        "_read_order_level_aggregate_result_once_impl",
        "_parse_result",
        "_META_FIELDS",
        "_AGGREGATE_FIELDS",
        "_spend_launch_control",
        "_spend_result_control",
        "_write_private_once",
        "_require_terminal",
        "require_order_level_submission_plan",
    ),
)
def test_public_actions_ignore_rebound_authority_and_parser_globals(
    tmp_path, monkeypatch, rebound_name
):
    plan, _delta, _projection = _real_plan_fixture(tmp_path, monkeypatch)
    execution_authority = _real_plan_test_execution_authority(plan)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    result_authority = _real_plan_test_result_authority(
        plan, execution_authority, control, launch, terminal
    )
    before = {
        path.name: path.read_bytes()
        for path in plan.control_directory.iterdir()
    }
    events = []

    class Client:
        def __getattr__(self, name):
            events.append(name)
            raise AssertionError("transport reached through rebound authority")

    if rebound_name in {"_META_FIELDS", "_AGGREGATE_FIELDS"}:
        hostile = frozenset({"hostile_raw_rows"})
    else:
        hostile = lambda *args, **kwargs: (
            kwargs.get("value")
            or kwargs.get("plan")
            or (args[0] if args else object())
        )
    monkeypatch.setattr(adapter, rebound_name, hostile)

    actions = (
        lambda: adapter.execute_order_level_submission_once(
            plan=plan,
            execution_authority=execution_authority,
            client=Client(),
            started_at_utc="2026-09-18T20:00:00Z",
        ),
        lambda: adapter.inspect_order_level_terminal_status(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=control,
            launch=launch,
            client=Client(),
        ),
        lambda: adapter.recover_order_level_launch_receipt_once(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=control,
            client=Client(),
        ),
        lambda: adapter.read_order_level_aggregate_result_once(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=control,
            launch=launch,
            terminal=terminal,
            result_read_authority=result_authority,
            client=Client(),
            started_at_utc="2026-09-18T21:00:00Z",
        ),
        lambda: adapter.load_order_level_aggregate_result(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=control,
            launch=launch,
            terminal=terminal,
            result_read_authority=result_authority,
            result_control=None,
        ),
    )
    for action in actions:
        with pytest.raises(
            (
                adapter.AcceptedRiskOrderLevelSubmissionError,
                package_builder.AcceptedRiskPreliminaryPackageError,
            )
        ) as caught:
            action()
        assert str(caught.value) in {
            "order-level aggregate loader dependency changed",
            "order-level public action dependency changed",
            "non-self-mintable owner execution signature is unavailable",
            "preliminary package type changed",
        }

    assert events == []
    assert {
        path.name: path.read_bytes()
        for path in plan.control_directory.iterdir()
    } == before


def test_signed_authorities_and_parser_ignore_coupled_json_builder_rebinding(
    tmp_path, monkeypatch
):
    plan, _delta, _projection = _real_plan_fixture(tmp_path, monkeypatch)
    execution_ops = _real_plan_test_execution_operations()
    execution_payload = execution_ops[0](plan=plan)
    execution_authority = execution_ops[1](
        plan=plan,
        receipt_bytes=execution_payload,
        owner_signature=_test_signature(
            "formal_qc_execution", execution_payload
        ),
    )
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    result_ops = _real_plan_test_result_operations()
    result_payload = result_ops[0](
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
    )
    result_authority = result_ops[1](
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
        receipt_bytes=result_payload,
        owner_signature=_test_signature(
            "formal_qc_result_read", result_payload
        ),
    )
    hostile_names = tuple(
        sorted((*plan.expected_custom_statistic_names, "ARV2_RAW_PROVIDER_ROWS"))
    )
    hostile_names_sha256 = hashlib.sha256(
        _canonical(list(hostile_names))
    ).hexdigest()
    changed_plan = dataclasses.replace(
        plan,
        expected_custom_statistic_names=hostile_names,
        expected_custom_statistic_names_sha256=hostile_names_sha256,
    )
    changed_result_authority = dataclasses.replace(
        result_authority,
        expected_custom_statistic_names_sha256=hostile_names_sha256,
    )
    original_dumps = json.dumps
    original_loads = json.loads
    original_names = list(plan.expected_custom_statistic_names)
    original_names_sha256 = plan.expected_custom_statistic_names_sha256

    class HostileJson:
        loads = staticmethod(original_loads)

        @staticmethod
        def dumps(value, **kwargs):
            if (
                type(value) is dict
                and value.get("schema")
                in {
                    adapter.EXECUTION_AUTHORITY_SCHEMA,
                    adapter.RESULT_READ_AUTHORITY_SCHEMA,
                }
            ):
                value = dict(value)
                if "expected_custom_statistic_names" in value:
                    value["expected_custom_statistic_names"] = original_names
                if "expected_custom_statistic_names_sha256" in value:
                    value["expected_custom_statistic_names_sha256"] = (
                        original_names_sha256
                    )
            return original_dumps(value, **kwargs)

    monkeypatch.setattr(adapter, "json", HostileJson)
    monkeypatch.setattr(
        adapter,
        "build_order_level_submission_plan",
        lambda **_kwargs: changed_plan,
    )
    monkeypatch.setattr(
        adapter,
        "_PINNED_EXPECTED_NAMES",
        lambda _profile_id: hostile_names,
    )

    assert execution_ops[2](value=execution_authority, plan=plan) is (
        execution_authority
    )
    assert result_ops[2](
        value=result_authority,
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
    ) is result_authority
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="submission plan identity changed",
    ):
        execution_ops[2](value=execution_authority, plan=changed_plan)
    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionError):
        result_ops[2](
            value=changed_result_authority,
            plan=changed_plan,
            execution_authority=execution_authority,
            launch_control=control,
            launch=launch,
            terminal=terminal,
        )

    statistics = _statistics(plan)
    statistics["ARV2_RAW_PROVIDER_ROWS"] = "{}"
    response = _result_response(plan, statistics)[1]
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="custom result key inventory changed",
    ):
        adapter._SEALED_RESULT_PARSER(response, changed_plan, launch)


def test_public_actions_refuse_rebound_external_formal_parser_dependency(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    events = []

    class Client:
        def __getattr__(self, name):
            events.append(name)
            raise AssertionError("transport reached after external rebind")

    monkeypatch.setattr(
        adapter.formal,
        "_exact_dict",
        lambda _value, _allowed, _name: {"success": True},
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="public action dependency changed",
    ):
        adapter.execute_order_level_submission_once(
            plan=plan,
            execution_authority=object(),
            client=Client(),
            started_at_utc="2026-09-18T20:00:00Z",
        )

    assert events == []


def test_public_submission_refuses_coupled_transport_method_mutation_before_io(
    tmp_path, monkeypatch
):
    """A changed class method cannot retarget formal's private dispatch pin."""

    artifacts = []
    network_calls = []

    def forged_request(*args, **kwargs):
        network_calls.append((args, kwargs))
        return {"success": True}

    # Clone the already-bound public wrapper with only the authority and
    # dependency-test seams replaced. Its captured transport verifier and
    # dispatch remain the production bindings under test.
    public = adapter.execute_order_level_submission_once
    cells = dict(
        zip(public.__code__.co_freevars, public.__closure__ or (), strict=True)
    )
    assert {"dependency_guard", "execution_authority_verifier"} <= set(cells)

    def cell(value):
        return (lambda: value).__closure__[0]

    replacements = {
        "dependency_guard": lambda: None,
        "execution_authority_verifier": lambda *, value, plan: value,
    }
    public_execute = FunctionType(
        public.__code__,
        public.__globals__,
        public.__name__,
        public.__defaults__,
        tuple(
            cell(replacements[name]) if name in replacements else cells[name]
            for name in public.__code__.co_freevars
        ),
    )
    public_execute.__kwdefaults__ = public.__kwdefaults__
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    monkeypatch.setattr(
        adapter,
        "persist_order_level_submission_plan",
        lambda _plan: artifacts.append("plan"),
    )
    monkeypatch.setitem(
        adapter.formal._PINNED_TRANSPORT_METHODS,
        "_request_json",
        forged_request,
    )
    monkeypatch.setattr(
        formal_qc_transport.FormalQcTransport, "_request_json", forged_request
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="exact order-level transport surface changed",
    ):
        public_execute(
            plan=_plan(tmp_path),
            execution_authority=object(),
            client=formal_qc_transport.FormalQcTransport(),
            started_at_utc="2026-09-18T20:00:00Z",
        )

    assert artifacts == []
    assert network_calls == []
    assert list(tmp_path.iterdir()) == []


def test_sealed_result_parser_ignores_rebound_external_runtime_profiles(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    hostile_profiles = json.loads(json.dumps(runtime._PROFILES))
    hostile_profiles[runtime.PROFILE_2025_ID]["score_source_view_id"] = (
        "hostile-rebound-score-source"
    )
    monkeypatch.setattr(runtime, "_PROFILES", hostile_profiles)
    assert runtime.require_qqq_order_level_profile(
        runtime.PROFILE_2025_ID
    )["score_source_view_id"] == "hostile-rebound-score-source"
    launch, response = _result_response(plan, _statistics(plan))

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="aggregate runtime lineage changed",
    ):
        adapter._SEALED_RESULT_PARSER(response, plan, launch)


def test_registered_minter_refuses_an_unregistered_claimant():
    closure = dict(
        zip(
            adapter.execute_order_level_submission_once.__code__.co_freevars,
            adapter.execute_order_level_submission_once.__closure__ or (),
            strict=True,
        )
    )
    minter = closure["minter"].cell_contents
    with pytest.raises(adapter.formal.FormalQcSubmissionError) as exc:
        minter(
            transport=object(),
            scope="submission",
            binding_record={"schema": "hostile-v1"},
            call_budget={"authenticate": 1},
        )
    assert str(exc.value) == "downstream transport capability caller changed"


def test_bound_status_action_ignores_rebound_transport_globals(
    monkeypatch,
):
    closure = dict(
        zip(
            adapter.inspect_order_level_terminal_status.__code__.co_freevars,
            adapter.inspect_order_level_terminal_status.__closure__ or (),
            strict=True,
        )
    )
    transport_dispatch = closure["transport_dispatch"].cell_contents
    dispatch_closure = dict(
        zip(
            transport_dispatch.__code__.co_freevars,
            transport_dispatch.__closure__ or (),
            strict=True,
        )
    )
    pinned_transport_call = dispatch_closure["transport_call"].cell_contents
    monkeypatch.setattr(
        adapter,
        "_PINNED_TRANSPORT_CALL",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("rebound pinned transport reached")
        ),
    )
    monkeypatch.setattr(
        adapter,
        "_transport",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("rebound transport helper reached")
        ),
    )

    rebound_closure = dict(
        zip(
            adapter.inspect_order_level_terminal_status.__code__.co_freevars,
            adapter.inspect_order_level_terminal_status.__closure__ or (),
            strict=True,
        )
    )
    assert rebound_closure["transport_dispatch"].cell_contents is (
        transport_dispatch
    )
    rebound_dispatch_closure = dict(
        zip(
            transport_dispatch.__code__.co_freevars,
            transport_dispatch.__closure__ or (),
            strict=True,
        )
    )
    assert rebound_dispatch_closure["transport_call"].cell_contents is (
        pinned_transport_call
    )


def test_execution_uploads_activation_last_and_launches_once(tmp_path, monkeypatch):
    source = SimpleNamespace(
        project_path="main.py",
        source_bytes=b"VALUE = 1\n",
        content_sha256=hashlib.sha256(b"VALUE = 1\n").hexdigest(),
        to_record=lambda: {
            "project_path": "main.py",
            "content_sha256": hashlib.sha256(b"VALUE = 1\n").hexdigest(),
            "byte_count": len(b"VALUE = 1\n"),
        },
    )
    payload = b"authenticated-package"
    descriptor = SimpleNamespace(
        object_store_key="arv2/input/transport-manifest.json",
        content_sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
        activation_manifest=True,
    )
    entry = adapter.OrderLevelUploadEntry(
        adapter.UPLOAD_SCHEMA,
        "activation_manifest",
        0,
        descriptor.object_store_key,
        len(payload),
        descriptor.content_sha256,
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        True,
    )
    plan = _plan(tmp_path)
    plan.upload_entries = (entry,)
    plan.source_files = (source,)
    plan.delta_package = SimpleNamespace(package=object())
    plan.compile_poll_limit = 1
    events = []
    budget = {}

    class Client:
        def request(self, _capability, path, request):
            events.append(path)
            if path == "authenticate":
                return {"success": True}
            if path == "projects/read" and request == {}:
                return {"projects": []}
            if path == "projects/create":
                return {"projectId": 123}
            if path == "projects/read":
                return {"projects": [{"projectId": 123}]}
            if path == "files/read" and events.count("files/read") == 1:
                return {"files": {adapter.DEFAULT_NOTEBOOK: "{}"}}
            if path == "files/delete":
                return {"success": True}
            if path == "files/create":
                return {"success": True}
            if path == "files/read":
                return {"files": {"main.py": "VALUE = 1\n"}}
            if path == "compile/create":
                return {"compileId": "compile-one"}
            if path == "compile/read":
                return {"state": "BuildSuccess"}
            if path == "backtests/create":
                return {"backtestId": "backtest-one", "status": "Queued"}
            raise AssertionError(path)

        def upload(self, _capability, organization, key, exact_payload):
            events.append("object/set")
            assert organization == plan.organization_id
            assert key == descriptor.object_store_key
            assert exact_payload == payload
            return {"success": True}

        def properties(self, _capability, organization, key):
            events.append("object/properties")
            assert organization == plan.organization_id
            assert key == descriptor.object_store_key
            return {"success": True}

    def transport_call(client, capability, method, *args):
        return {
            "_request_json": client.request,
            "_set_object_multipart": client.upload,
            "_read_object_properties": client.properties,
        }[method](capability, *args)

    def minter(**kwargs):
        budget.update(kwargs["call_budget"])
        return object()

    monkeypatch.setattr(adapter, "require_order_level_submission_plan", lambda value: value)
    monkeypatch.setattr(
        adapter, "persist_order_level_submission_plan", lambda _value: tmp_path
    )
    monkeypatch.setattr(adapter, "_PINNED_TRANSPORT_CALL", transport_call)
    monkeypatch.setattr(adapter, "_PINNED_ITER_UPLOADS", lambda _package: iter(((descriptor, payload),)))
    monkeypatch.setattr(adapter, "_PINNED_SUCCESS", lambda value, *_args: value)
    monkeypatch.setattr(adapter, "_PINNED_READ_PROJECTS", lambda value: value["projects"])
    monkeypatch.setattr(adapter, "_PINNED_CREATED_PROJECT", lambda value, **_kwargs: value)
    monkeypatch.setattr(adapter, "_PINNED_PROJECT_RECORD", lambda value, **_kwargs: value)
    monkeypatch.setattr(adapter, "_PINNED_OBJECT_METADATA", lambda *_args: None)
    monkeypatch.setattr(adapter, "_PINNED_READ_FILES", lambda value, **_kwargs: value["files"])
    monkeypatch.setattr(adapter, "_PINNED_COMPILE_ID", lambda value, **_kwargs: value["compileId"])
    monkeypatch.setattr(adapter, "_PINNED_COMPILE_STATE", lambda value, _compile_id: value["state"])
    monkeypatch.setattr(
        adapter,
        "_PINNED_CREATED_BACKTEST",
        lambda value, **_kwargs: (value["backtestId"], value["status"]),
    )

    control, launch = adapter._execute_order_level_submission_once_impl(
        plan=plan,
        execution_authority=_execution_authority(plan, monkeypatch),
        client=Client(),
        started_at_utc="2026-09-18T20:00:00Z",
        minter=minter,
        transport_verifier=lambda value: value,
        authority_verifier=_test_execution_operations()[2],
        _transport=transport_call,
    )

    assert control.control_path.exists()
    assert launch.backtest_id == "backtest-one"
    assert events.count("backtests/create") == 1
    assert events.index("object/set") < events.index("files/create")
    assert set(budget) == adapter.EXECUTION_ENDPOINT_BUDGET_NAMES
    assert adapter._launch_checkpoint_path(plan).exists()
    assert adapter._launch_receipt_path(plan).exists()


def test_self_hashed_launch_is_refused_until_exact_durable_reload(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control = adapter._spend_launch_control(
        plan, execution_authority, "2026-09-18T20:00:00Z"
    )
    hostile = adapter._new_launch(
        plan, control, 123, "compile-one", "backtest-one", "Queued"
    )
    adapter._write_private_once(
        adapter._launch_receipt_path(plan),
        adapter._launch_receipt_bytes(hostile),
        "launch receipt",
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="lacks durable adapter provenance",
    ):
        adapter._require_launch(hostile, plan, control)

    loaded = adapter.load_order_level_launch_receipt(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
    )
    assert loaded == hostile
    assert loaded is not hostile
    assert adapter._require_launch(loaded, plan, control) is loaded


def test_self_hashed_terminal_is_refused_until_exact_durable_reload(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    record = {
        "plan_sha256": plan.plan_sha256,
        "launch_sha256": launch.receipt_sha256,
        "project_id": launch.project_id,
        "backtest_id": launch.backtest_id,
        "terminal_status": "Completed.",
        "poll_count": 1,
        "include_statistics": False,
    }
    identity, digest, _payload = adapter._identified(
        adapter.TERMINAL_SCHEMA, "arv2-order-level-terminal-", record
    )
    hostile = adapter.OrderLevelTerminalStatus(identity, digest, **record)
    adapter._write_private_once(
        adapter._terminal_receipt_path(plan),
        adapter._terminal_receipt_bytes(hostile),
        "terminal receipt",
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="lacks durable adapter provenance",
    ):
        adapter._require_terminal(hostile, plan, launch)

    loaded = adapter.load_order_level_terminal_status(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
    )
    assert loaded == hostile
    assert loaded is not hostile
    assert adapter._require_terminal(loaded, plan, launch) is loaded


def test_interrupted_launch_recovers_only_unique_existing_run(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control = adapter._spend_launch_control(
        plan, execution_authority, "2026-09-18T20:00:00Z"
    )
    adapter._persist_launch_checkpoint(
        plan, control, 123, "compile-one"
    )
    calls = []
    budgets = []

    class Client:
        def _request_json(self, _capability, endpoint, request):
            calls.append((endpoint, request))
            assert endpoint == "backtests/list"
            return {
                "success": True,
                "count": 1,
                "backtests": [
                    {
                        "backtestId": "backtest-one",
                        "projectId": 123,
                        "name": plan.backtest_name,
                        "status": "Completed.",
                    }
                ],
            }

    monkeypatch.setattr(
        adapter,
        "_PINNED_TRANSPORT_CALL",
        lambda client, capability, method, *args: getattr(client, method)(
            capability, *args
        ),
    )

    launch = adapter._recover_order_level_launch_receipt_once_impl(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        client=Client(),
        minter=lambda **kwargs: budgets.append(kwargs["call_budget"]) or object(),
        transport_verifier=lambda value: value,
        authority_verifier=_test_execution_operations()[2],
        _transport=_test_transport,
    )

    assert launch.backtest_id == "backtest-one"
    assert launch.initial_status == adapter.RECOVERED_LAUNCH_INITIAL_STATUS
    assert calls == [
        (
            "backtests/list",
            {"projectId": 123, "includeStatistics": False},
        )
    ]
    assert budgets == [{"backtests/list": 1}]
    assert adapter._launch_receipt_path(plan).exists()
    assert adapter.load_order_level_launch_receipt(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
    ) == launch


def test_result_read_uses_exact_transport_method_and_persists_reloadable_result(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    result_read_authority = _result_read_authority(
        plan,
        execution_authority,
        control,
        launch,
        terminal,
        monkeypatch,
    )
    response = _result_response(plan, _statistics(plan))[1]
    calls = []
    minted = []

    class Client:
        def _read_backtest_result(
            self, _capability, project_id, backtest_id
        ):
            calls.append((project_id, backtest_id))
            return response

        def _request_json(self, *_args):
            raise AssertionError("generic request path must not read a result")

    monkeypatch.setattr(
        adapter,
        "_PINNED_TRANSPORT_CALL",
        lambda client, capability, method, *args: getattr(client, method)(
            capability, *args
        ),
    )
    result_control, result = adapter._read_order_level_aggregate_result_once_impl(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
        result_read_authority=result_read_authority,
        client=Client(),
        started_at_utc="2026-09-18T21:00:00Z",
        minter=lambda **kwargs: minted.append(kwargs) or object(),
        transport_verifier=lambda value: value,
        result_authority_verifier=_test_result_operations()[2],
        result_parser=adapter._SEALED_RESULT_PARSER,
        _transport=_test_transport,
    )

    assert calls == [(123, "backtest-one")]
    assert minted[0]["call_budget"] == {"backtests/read": 1}
    assert result.backtests_read_call_count == 1
    assert result.persisted_path == adapter._result_receipt_path(plan)
    reloaded_control = adapter.load_order_level_result_control(
        plan=plan,
        launch=launch,
        terminal=terminal,
        result_read_authority=result_read_authority,
    )
    assert reloaded_control == result_control
    assert adapter._load_order_level_aggregate_result_impl(
        plan=plan,
        execution_authority=execution_authority,
        launch_control=control,
        launch=launch,
        terminal=terminal,
        result_read_authority=result_read_authority,
        result_control=reloaded_control,
        execution_authority_verifier=_test_execution_operations()[2],
        result_authority_verifier=_test_result_operations()[2],
        result_parser=adapter._SEALED_RESULT_PARSER,
    ) == result


def test_result_read_wrapper_severs_malformed_remote_content_from_exceptions(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    result_authority = _result_read_authority(
        plan,
        execution_authority,
        control,
        launch,
        terminal,
        monkeypatch,
    )
    statistics = _statistics(plan)
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = (
        '{"RAW_REMOTE_RESULT_MARKER":'
    )
    response = _result_response(plan, statistics)[1]

    class Client:
        def _read_backtest_result(
            self, _capability, project_id, backtest_id
        ):
            assert (project_id, backtest_id) == (123, "backtest-one")
            return response

    monkeypatch.setattr(
        adapter,
        "_PINNED_TRANSPORT_CALL",
        lambda client, capability, method, *args: getattr(client, method)(
            capability, *args
        ),
    )

    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionLocked) as caught:
        adapter._read_order_level_aggregate_result_once_impl(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=control,
            launch=launch,
            terminal=terminal,
            result_read_authority=result_authority,
            client=Client(),
            started_at_utc="2026-09-18T21:00:00Z",
            minter=lambda **_kwargs: object(),
            transport_verifier=lambda value: value,
            result_authority_verifier=_test_result_operations()[2],
            result_parser=adapter._SEALED_RESULT_PARSER,
            _transport=_test_transport,
        )

    assert "RAW_REMOTE_RESULT_MARKER" not in _exception_graph_text(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_result_late_write_refusal_severs_outcome_traceback_locals(
    tmp_path, monkeypatch
):
    outcome_marker = "987654321.123456789"
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    result_authority = _result_read_authority(
        plan,
        execution_authority,
        control,
        launch,
        terminal,
        monkeypatch,
    )
    response = _result_response(
        plan,
        _statistics(
            plan, aggregate_update={"strategy_total_return": outcome_marker}
        ),
    )[1]

    class Client:
        def _read_backtest_result(
            self, _capability, project_id, backtest_id
        ):
            assert (project_id, backtest_id) == (123, "backtest-one")
            return response

    original_write = adapter._write_private_once

    def fail_aggregate_write(path, payload, name):
        if name == "aggregate result":
            outcome_marker_payload = payload
            assert outcome_marker.encode("ascii") in outcome_marker_payload
            raise RuntimeError("late aggregate write failed")
        return original_write(path, payload, name)

    monkeypatch.setattr(adapter, "_write_private_once", fail_aggregate_write)

    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionLocked) as caught:
        adapter._read_order_level_aggregate_result_once_impl(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=control,
            launch=launch,
            terminal=terminal,
            result_read_authority=result_authority,
            client=Client(),
            started_at_utc="2026-09-18T21:00:00Z",
            minter=lambda **_kwargs: object(),
            transport_verifier=lambda value: value,
            result_authority_verifier=_test_result_operations()[2],
            result_parser=adapter._SEALED_RESULT_PARSER,
            _transport=_test_transport,
        )

    assert outcome_marker not in _exception_internal_traceback_locals_text(
        caught.value
    )
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_rebound_result_parser_and_field_inventory_cannot_widen_persisted_result(
    tmp_path, monkeypatch
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        adapter, "require_order_level_submission_plan", lambda value: value
    )
    execution_authority = _execution_authority(plan, monkeypatch)
    control, launch = _persisted_launch(plan, execution_authority)
    terminal = _persisted_terminal(plan, launch)
    result_authority = _result_read_authority(
        plan,
        execution_authority,
        control,
        launch,
        terminal,
        monkeypatch,
    )
    result_authority_verifier = _test_result_operations()[2]
    response = _result_response(
        plan, _statistics(plan, aggregate_update={"hostile_raw_rows": []})
    )[1]
    calls = []

    class Client:
        def _read_backtest_result(
            self, _capability, project_id, backtest_id
        ):
            calls.append((project_id, backtest_id))
            return response

    monkeypatch.setattr(
        adapter,
        "_PINNED_TRANSPORT_CALL",
        lambda client, capability, method, *args: getattr(client, method)(
            capability, *args
        ),
    )
    monkeypatch.setattr(adapter, "_parse_result", lambda *_args: (("raw", "x"),))
    monkeypatch.setattr(
        adapter,
        "_AGGREGATE_FIELDS",
        frozenset((*adapter._AGGREGATE_FIELDS, "hostile_raw_rows")),
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionLocked,
        match="result_read: AcceptedRiskOrderLevelSubmissionError;",
    ):
        adapter._read_order_level_aggregate_result_once_impl(
            plan=plan,
            execution_authority=execution_authority,
            launch_control=control,
            launch=launch,
            terminal=terminal,
            result_read_authority=result_authority,
            client=Client(),
            started_at_utc="2026-09-18T21:00:00Z",
            minter=lambda **_kwargs: object(),
            transport_verifier=lambda value: value,
            result_authority_verifier=result_authority_verifier,
            result_parser=adapter._SEALED_RESULT_PARSER,
            _transport=_test_transport,
        )

    closure = dict(
        zip(
            adapter.read_order_level_aggregate_result_once.__code__.co_freevars,
            adapter.read_order_level_aggregate_result_once.__closure__ or (),
            strict=True,
        )
    )
    assert closure["result_parser"].cell_contents is adapter._SEALED_RESULT_PARSER
    assert calls == [(123, "backtest-one")]
    assert not adapter._result_receipt_path(plan).exists()


@pytest.mark.parametrize(
    ("aggregate_update", "meta_update", "message"),
    (
        (
            {"raw_order_rows_in_summary": True},
            None,
            "order-level aggregate schema or safety flags changed",
        ),
        (
            {"raw_provider_rows": []},
            None,
            "order-level aggregate field inventory changed",
        ),
        (
            None,
            {"live_orders": True},
            "order-level aggregate runtime lineage changed",
        ),
        (
            None,
            {"score_source_view_id": "hostile-source-view"},
            "order-level aggregate runtime lineage changed",
        ),
        (
            {"score_source_view_id": "hostile-source-view"},
            None,
            "order-level aggregate schema or safety flags changed",
        ),
        (
            {"QQQ_observation": "session_close"},
            None,
            "order-level aggregate schema or safety flags changed",
        ),
        (
            {"QQQ_entry_fee_bps_per_side": 0},
            None,
            "order-level aggregate schema or safety flags changed",
        ),
        (
            {"QQQ_calendar_close_observation_count": 1},
            None,
            "order-level aggregate schema or safety flags changed",
        ),
    ),
)
def test_result_refuses_raw_or_live_result_disclosures(
    tmp_path, aggregate_update, meta_update, message
):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(
            plan,
            aggregate_update=aggregate_update,
            meta_update=meta_update,
        ),
    )
    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionError) as exc:
        adapter._parse_result(response, plan, launch)
    assert str(exc.value) == message


@pytest.mark.parametrize(
    "aggregate_update",
    (
        {"canceled_order_count_sum": 1},
        {"maximum_constituent_snapshot_age_sessions": 2},
        {"fee_mismatch": True},
        {"actual_engine_fee_effective_bps_per_side": "11"},
        {"QQQ_target_gross_exposure": "0.97"},
        {
            "mean_positive_constituent_weight_total": "0.1",
            "minimum_positive_constituent_weight_total": "0.1",
            "maximum_positive_constituent_weight_total": "0.1",
        },
    ),
)
def test_result_refuses_inconsistent_execution_or_coverage_claims(
    tmp_path, aggregate_update
):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(plan, aggregate_update=aggregate_update),
    )
    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="execution or coverage invariant changed",
    ):
        adapter._parse_result(response, plan, launch)


def test_result_accepts_exact_pit_etf_weight_coverage_floor(tmp_path):
    plan = _plan(tmp_path)
    statistics = _statistics(
        plan,
        aggregate_update={
            "minimum_resolved_constituent_weight_ratio": "0.95",
        },
    )
    launch, response = _result_response(plan, statistics)

    assert adapter._parse_result(response, plan, launch) == tuple(
        sorted(statistics.items())
    )


@pytest.mark.parametrize("required_floor", ("0.94", "0.96"))
def test_result_refuses_changed_exact_pit_etf_weight_coverage_floor(
    tmp_path, required_floor
):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(
            plan,
            aggregate_update={
                "minimum_required_resolved_constituent_weight_ratio": (
                    required_floor
                )
            },
        ),
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="order-level aggregate execution or coverage invariant changed",
    ):
        adapter._parse_result(response, plan, launch)


def test_result_refuses_undercovered_pit_etf_weights(tmp_path):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(
            plan,
            aggregate_update={
                "minimum_resolved_constituent_weight_ratio": "0.94"
            },
        ),
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="order-level aggregate execution or coverage invariant changed",
    ):
        adapter._parse_result(response, plan, launch)


def test_result_refuses_two_pit_history_calls_per_decision(tmp_path):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(plan, aggregate_update={"pit_history_call_count": 182}),
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="order-level aggregate execution or coverage invariant changed",
    ):
        adapter._parse_result(response, plan, launch)


def test_result_refuses_non_pit_etf_weight_target_basis(tmp_path):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(
            plan,
            aggregate_update={
                "target_weight_basis": "point_in_time_market_cap_proxy"
            },
        ),
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="order-level aggregate schema or safety flags changed",
    ):
        adapter._parse_result(response, plan, launch)


def test_result_refuses_superseded_cap_coverage_field(tmp_path):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(
            plan,
            aggregate_update={"cap_covered_positive_weight_member_count_sum": 99},
        ),
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="order-level aggregate field inventory changed",
    ):
        adapter._parse_result(response, plan, launch)


@pytest.mark.parametrize(
    ("aggregate_update", "message"),
    (
        (
            {"pit_target_weight_path_sha256": "g" * 64},
            "order-level aggregate pit_target_weight_path_sha256 "
            "is not an exact SHA-256",
        ),
        (
            {"pit_target_weight_path_sha256": None},
            "order-level aggregate pit_target_weight_path_sha256 "
            "is not an exact SHA-256",
        ),
    ),
)
def test_result_refuses_unverifiable_pit_target_weight_path_digest(
    tmp_path, aggregate_update, message
):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan, _statistics(plan, aggregate_update=aggregate_update)
    )

    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionError) as exc:
        adapter._parse_result(response, plan, launch)
    assert str(exc.value) == message


def test_result_refuses_missing_pit_target_weight_path_digest(tmp_path):
    plan = _plan(tmp_path)
    statistics = _statistics(plan)
    aggregates = json.loads(statistics[runtime.AGGREGATES_STATISTIC_NAME])
    aggregates.pop("pit_target_weight_path_sha256")
    meta = json.loads(statistics[runtime.META_STATISTIC_NAME])
    meta["aggregates_sha256"] = hashlib.sha256(_canonical(aggregates)).hexdigest()
    statistics[runtime.AGGREGATES_STATISTIC_NAME] = _canonical(
        aggregates
    ).decode("ascii")
    statistics[runtime.META_STATISTIC_NAME] = _canonical(meta).decode("ascii")
    launch, response = _result_response(plan, statistics)

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="order-level aggregate field inventory changed",
    ):
        adapter._parse_result(response, plan, launch)


def test_result_refuses_reused_coverage_digest_as_target_weight_digest(
    tmp_path,
):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(
            plan,
            aggregate_update={"pit_target_weight_path_sha256": "5" * 64},
        ),
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="order-level aggregate execution or coverage invariant changed",
    ):
        adapter._parse_result(response, plan, launch)


@pytest.mark.parametrize(
    "aggregate_update",
    (
        {"starting_equity": "2"},
        {"ending_equity": "3"},
        {"strategy_total_return": "4"},
        {"strategy_minus_QQQ_total_return": "999"},
        {"QQQ_first_execution_session": "2099-12-31"},
        {"strategy_maximum_drawdown": "0.01"},
        {"strategy_maximum_drawdown": "-1.01"},
        {"QQQ_maximum_drawdown": "0.01"},
        {"QQQ_maximum_drawdown": "-1.01"},
        {"strategy_annualized_volatility": "-0.01"},
        {"QQQ_annualized_volatility": "-0.01"},
        {
            "ending_equity": "-1000000",
            "strategy_total_return": "-2",
            "strategy_minus_QQQ_total_return": "-2.08",
        },
        {
            "QQQ_total_return": "-2",
            "strategy_minus_QQQ_total_return": "2.1",
        },
        {"QQQ_calendar_close_total_return": "-2"},
        {"mean_gross_exposure": "-1", "mean_cash_weight": "2"},
        {
            "QQQ_observation_count": 2,
            "QQQ_return_interval_count": 1,
            "QQQ_calendar_close_observation_count": 2,
        },
        {"tilt_enabled_count": 100, "tilt_underfilled_count": 100},
        {
            "mean_resolved_member_count_ratio": "0.5",
            "minimum_resolved_member_count_ratio": "0.75",
        },
        {
            "decision_count": 1,
            "completed_rebalance_count": 1,
            "coverage_decision_count": 1,
            "tilt_enabled_count": 1,
            "pit_history_call_count": 1,
        },
        {"mean_tilted_name_count": "-1"},
        {"mean_one_way_active_share": "1.01"},
        {"mean_reference_mark_target_weight_l1_error": "-0.01"},
    ),
)
def test_result_refuses_self_digested_impossible_economic_claims(
    tmp_path, aggregate_update
):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(plan, aggregate_update=aggregate_update),
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="execution or coverage invariant changed",
    ):
        adapter._parse_result(response, plan, launch)


@pytest.mark.parametrize(
    "profile_id",
    (runtime.PROFILE_2025_ID, runtime.PROFILE_2026_ID),
)
def test_result_requires_exact_profile_first_execution_session(
    tmp_path, profile_id
):
    plan = _plan(tmp_path, profile_id=profile_id)
    launch, response = _result_response(plan, _statistics(plan))

    assert adapter._parse_result(response, plan, launch) == tuple(
        sorted(_statistics(plan).items())
    )
    aggregates = json.loads(
        _statistics(plan)[runtime.AGGREGATES_STATISTIC_NAME]
    )
    assert (
        aggregates["decision_count"],
        aggregates["QQQ_observation_count"],
        aggregates["QQQ_return_interval_count"],
    ) == {
        runtime.PROFILE_2025_ID: (91, 428, 427),
        runtime.PROFILE_2026_ID: (39, 178, 177),
    }[profile_id]


def test_result_refuses_superseded_engine_fee_basis_label(tmp_path):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(
            plan,
            aggregate_update={
                "engine_fee_model_basis": (
                    "security_price_times_full_order_quantity_at_fee_assessment"
                )
            },
        ),
    )

    with pytest.raises(
        adapter.AcceptedRiskOrderLevelSubmissionError,
        match="aggregate schema or safety flags changed",
    ):
        adapter._parse_result(response, plan, launch)


def test_result_decimal_refuses_huge_exponent_before_decimal_expansion(
    tmp_path,
):
    plan = _plan(tmp_path)
    launch, response = _result_response(
        plan,
        _statistics(
            plan,
            aggregate_update={"strategy_total_return": "1e999999999"},
        ),
    )

    with pytest.raises(adapter.AcceptedRiskOrderLevelSubmissionError) as exc:
        adapter._parse_result(response, plan, launch)

    assert str(exc.value) == (
        "order-level aggregate strategy_total_return "
        "is not an exact decimal string"
    )
