"""Canonical pre-outcome economic execution definition for ARV2.

This module closes the structural hole left deliberately open by the reviewed
stock evaluation contract.  It freezes how the H20 direct-stock sleeve is
formed, valued, costed, and tested before any outcome is read.  The objects are
process-local authenticated artifacts; copying their public fields or
recomputing their public hashes does not create authority.

The definition is configuration, not permission.  It cannot read a provider,
open an outcome, contact QuantConnect, inspect a result, deploy, or trade.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sys
import threading
import weakref
from datetime import date
from typing import Any

from data.exchange_calendar import resolve_nth_session_after, trading_sessions
from research.analyst_revisions_v2.stock_evaluation_contract import (
    EVALUATION_ID,
    STRATEGY_PDF_SHA256,
    StockEvaluationContract,
    StockEvaluationContractError,
    require_loaded_stock_evaluation_contract,
)


class FormalEconomicExecutionDefinitionError(ValueError):
    """The economic definition or one of its authenticated parents changed."""


DEFINITION_SCHEMA = "arv2-formal-economic-execution-definition-v1"
BINDING_SCHEMA = "arv2-formal-economic-execution-binding-v1"
STATUS = "candidate_pending_independent_review_and_counterreview"
AUTHORITY = (
    "preoutcome_economic_configuration_only_no_provider_outcome_qc_result_"
    "deployment_order_or_trading_authority"
)
SOURCE_STOCK_SPEC_ID = "arv2-stock-historical-c5ff2a6a0dcf341e"
SOURCE_STOCK_SPEC_SHA256 = (
    "c5ff2a6a0dcf341e3c7bad4ea56e4a3c00f20faab5896c0fcd3bd7c291835a0b"
)
SOURCE_ECONOMIC_SECTION_SHA256 = (
    "3b98c40dd7b470658f08a8812d816aa0eeff9f765282917e478dfe378dcc95bd"
)
SOURCE_PARENT_PLAN_ID = "arv2-qc-first-plan-36e455e72b8750fe"
SOURCE_PARENT_PLAN_SHA256 = (
    "36e455e72b8750fe3f34773382870e10e62f3f40b5392ae587690bda081b85dc"
)
SOURCE_FOLD_MANIFEST_ID = "arv2-stock-folds-1002155dbe8e3e87"
SOURCE_FOLD_MANIFEST_SHA256 = (
    "1002155dbe8e3e87b220b7419039bff95f5c0812d2306c56a8ac51b76c5d7611"
)
FORMAL_FOLD_IDS = tuple(f"arv2-wf-test-{year}" for year in range(2020, 2026))
DESCRIPTIVE_FOLD_IDS = tuple(f"arv2-wf-test-{year}" for year in range(2021, 2026))
SOURCE_VIEW_IDS = (
    "current_row_current_vintage_non_pristine_pit",
    "conservative_censored_current_vintage_non_pristine_pit",
)
PRIMARY_SOURCE_VIEW_ID = SOURCE_VIEW_IDS[0]
SENSITIVITY_SOURCE_VIEW_ID = SOURCE_VIEW_IDS[1]
PRIMARY_SLICE_ID = "formal_2020_2025_primary"
DESCRIPTIVE_SLICE_ID = "owner_2021_2025_descriptive_sensitivity"
HOLDING_SESSIONS = 20
MINIMUM_SLEEVE_SIZE = 5
COST_BPS_PER_SIDE = (0, 5, 10, 20)
PRIMARY_COST_BPS_PER_SIDE = 10
HAC_LAG_SESSIONS = 20
BOOTSTRAP_BLOCK_SESSIONS = 20
BOOTSTRAP_RESAMPLES = 19_999
BOOTSTRAP_BASE_ANCESTRY_DOMAIN = "arv2-economic-bootstrap-base-ancestry-v1"
OPERATIVE_REPORT_CONTRACT_SCHEMA = "arv2-formal-report-execution-contract-v1"
OPERATIVE_BOOTSTRAP_SEED_DOMAIN = "arv2-stock-formal-bootstrap-seed-v1"
OPERATIVE_BOOTSTRAP_DRAW_DOMAIN = (
    "arv2-stock-formal-noncircular-mbb-hash-counter-v1"
)
TERMINAL_POLICY_ID = "arv2-terminal-payoff-benchmark-splice-v1"

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}\Z")

# Each decision axis is the exact reviewed H20 test axis.  Portfolio valuation
# continues for nineteen additional return intervals after the last decision;
# the final outstanding sleeve exits at the next open, its actual liquidation
# session.  That cost is never shifted onto the prior return observation.
_FOLD_GEOMETRY = (
    (
        "arv2-wf-test-2020", "2020-01-31", "2021-01-04", 233,
        "d05d7c37f0ae3deacef369bba8bc7888b6de9295c45053fa6af4042765f7fe3b",
        "2020-12-31", "2021-02-01", 252,
        "f340decb2447196b0084f59c3ac606c3b84260dedc6a4c7afb2d8250cc507a3d",
        253, "a3315753e5b35f1562b8db5ced691bec922aac83b730f2b7e76d1f93628c19d6",
    ),
    (
        "arv2-wf-test-2021", "2021-02-02", "2022-01-03", 232,
        "d05832a87f18577559247c705bb2fa67b150704f73328a83129bec0c6bd3953f",
        "2021-12-31", "2022-01-31", 251,
        "58101ba1116e4aabd7c5834d98c1ba6a52c861602b183fad8259faec6610dc8b",
        252, "6f8172c17ba51852fbbceff4a14f38efe6f5aec6c86c7df51aa6b2d751b451f3",
    ),
    (
        "arv2-wf-test-2022", "2022-02-01", "2023-01-03", 231,
        "c20e0f699a72136b2adfbe701b7e31b8f6d634f2565086ded27d956eb2b5d1c5",
        "2022-12-30", "2023-01-31", 250,
        "203de931639379ab7dda41b3579ddebeaaff838c8ccaa6d0ba71b60fbf4e5b57",
        251, "650a1bc52ce253d5e240869e2a6aa3408fd99b6fbf438b03c070fb6150cb1dc2",
    ),
    (
        "arv2-wf-test-2023", "2023-02-01", "2024-01-02", 230,
        "e023ce427c9c6b0bb50a91c647dc6c29149483f5dee5b0275ee7c414ec867de4",
        "2023-12-29", "2024-01-30", 249,
        "a180c5b8e47568ea7e2f25047da7bcd0f02a79b70707bdb8869a222ef7daa24c",
        250, "190ca48ba3b49be18b3b14c19738be910e908a530087bfbded6b63a3aa3222a3",
    ),
    (
        "arv2-wf-test-2024", "2024-01-31", "2025-01-02", 232,
        "8e05e03d97ebd5d5b4df582754c6f93cfe64900d3c90ed7e33d85b19278ea8b8",
        "2024-12-31", "2025-01-31", 251,
        "d58d7eb723b502451084f09498e0f4ff788a91cde58b2d883a97082cfaeb578b",
        252, "8931210f30fe4812340ea42716116a6a43f22de60f7550279cf73a2c08d09a66",
    ),
    (
        "arv2-wf-test-2025", "2025-02-03", "2026-01-02", 230,
        "070c2d06e6f91432c35064c50affbb6e540ba35dd0a665f3e8e4a269bc4bf74f",
        "2025-12-31", "2026-01-30", 249,
        "fa2ee8d3a5deed8f57c8c184365fd9c00bf4958fdcda8916650fbf793ac74ca3",
        250, "45ac3285620a129beb41756aa2a3ed56d035992897d19df61be8d2aa6f512acc",
    ),
)
_PINNED_FOLD_GEOMETRY_ROOT = _FOLD_GEOMETRY
_PINNED_FOLD_GEOMETRY_VALUES = tuple(tuple(item) for item in _FOLD_GEOMETRY)
_PINNED_FORMAL_FOLD_IDS_ROOT = FORMAL_FOLD_IDS
_PINNED_FORMAL_FOLD_IDS_VALUES = tuple(FORMAL_FOLD_IDS)
_PINNED_DESCRIPTIVE_FOLD_IDS_ROOT = DESCRIPTIVE_FOLD_IDS
_PINNED_DESCRIPTIVE_FOLD_IDS_VALUES = tuple(DESCRIPTIVE_FOLD_IDS)
_PINNED_SOURCE_VIEW_IDS_ROOT = SOURCE_VIEW_IDS
_PINNED_SOURCE_VIEW_IDS_VALUES = tuple(SOURCE_VIEW_IDS)
_PINNED_TRADING_SESSIONS = trading_sessions
_PINNED_RESOLVE_NTH_SESSION_AFTER = resolve_nth_session_after
_PINNED_REQUIRE_STOCK_CONTRACT = require_loaded_stock_evaluation_contract


def _require_module_closure() -> None:
    scalar_expected = {
        "DEFINITION_SCHEMA": "arv2-formal-economic-execution-definition-v1",
        "BINDING_SCHEMA": "arv2-formal-economic-execution-binding-v1",
        "STATUS": "candidate_pending_independent_review_and_counterreview",
        "AUTHORITY": (
            "preoutcome_economic_configuration_only_no_provider_outcome_qc_result_"
            "deployment_order_or_trading_authority"
        ),
        "SOURCE_STOCK_SPEC_ID": "arv2-stock-historical-c5ff2a6a0dcf341e",
        "SOURCE_STOCK_SPEC_SHA256": (
            "c5ff2a6a0dcf341e3c7bad4ea56e4a3c00f20faab5896c0fcd3bd7c291835a0b"
        ),
        "SOURCE_ECONOMIC_SECTION_SHA256": (
            "3b98c40dd7b470658f08a8812d816aa0eeff9f765282917e478dfe378dcc95bd"
        ),
        "SOURCE_PARENT_PLAN_ID": "arv2-qc-first-plan-36e455e72b8750fe",
        "SOURCE_PARENT_PLAN_SHA256": (
            "36e455e72b8750fe3f34773382870e10e62f3f40b5392ae587690bda081b85dc"
        ),
        "SOURCE_FOLD_MANIFEST_ID": "arv2-stock-folds-1002155dbe8e3e87",
        "SOURCE_FOLD_MANIFEST_SHA256": (
            "1002155dbe8e3e87b220b7419039bff95f5c0812d2306c56a8ac51b76c5d7611"
        ),
        "PRIMARY_SOURCE_VIEW_ID": "current_row_current_vintage_non_pristine_pit",
        "SENSITIVITY_SOURCE_VIEW_ID": (
            "conservative_censored_current_vintage_non_pristine_pit"
        ),
        "PRIMARY_SLICE_ID": "formal_2020_2025_primary",
        "DESCRIPTIVE_SLICE_ID": "owner_2021_2025_descriptive_sensitivity",
        "HOLDING_SESSIONS": 20,
        "MINIMUM_SLEEVE_SIZE": 5,
        "PRIMARY_COST_BPS_PER_SIDE": 10,
        "HAC_LAG_SESSIONS": 20,
        "BOOTSTRAP_BLOCK_SESSIONS": 20,
        "BOOTSTRAP_RESAMPLES": 19_999,
        "BOOTSTRAP_BASE_ANCESTRY_DOMAIN": (
            "arv2-economic-bootstrap-base-ancestry-v1"
        ),
        "OPERATIVE_REPORT_CONTRACT_SCHEMA": (
            "arv2-formal-report-execution-contract-v1"
        ),
        "OPERATIVE_BOOTSTRAP_SEED_DOMAIN": (
            "arv2-stock-formal-bootstrap-seed-v1"
        ),
        "OPERATIVE_BOOTSTRAP_DRAW_DOMAIN": (
            "arv2-stock-formal-noncircular-mbb-hash-counter-v1"
        ),
        "TERMINAL_POLICY_ID": "arv2-terminal-payoff-benchmark-splice-v1",
        "EVALUATION_ID": "arv2-eval-stock-historical-qc-001",
        "STRATEGY_PDF_SHA256": (
            "eae7b9954aaf94212108505c52e31a558facd744967fd2526040d5147c616193"
        ),
    }
    namespace = globals()
    if any(
        type(namespace.get(name)) is not type(expected)
        or namespace.get(name) != expected
        for name, expected in scalar_expected.items()
    ):
        raise FormalEconomicExecutionDefinitionError(
            "economic definition module closure changed"
        )
    if (
        COST_BPS_PER_SIDE != (0, 5, 10, 20)
        or _FOLD_GEOMETRY is not _PINNED_FOLD_GEOMETRY_ROOT
        or _FOLD_GEOMETRY != _PINNED_FOLD_GEOMETRY_VALUES
        or FORMAL_FOLD_IDS is not _PINNED_FORMAL_FOLD_IDS_ROOT
        or FORMAL_FOLD_IDS != _PINNED_FORMAL_FOLD_IDS_VALUES
        or DESCRIPTIVE_FOLD_IDS is not _PINNED_DESCRIPTIVE_FOLD_IDS_ROOT
        or DESCRIPTIVE_FOLD_IDS != _PINNED_DESCRIPTIVE_FOLD_IDS_VALUES
        or SOURCE_VIEW_IDS is not _PINNED_SOURCE_VIEW_IDS_ROOT
        or SOURCE_VIEW_IDS != _PINNED_SOURCE_VIEW_IDS_VALUES
        or trading_sessions is not _PINNED_TRADING_SESSIONS
        or resolve_nth_session_after is not _PINNED_RESOLVE_NTH_SESSION_AFTER
        or require_loaded_stock_evaluation_contract
        is not _PINNED_REQUIRE_STOCK_CONTRACT
    ):
        raise FormalEconomicExecutionDefinitionError(
            "economic definition container closure changed"
        )


def _canonical(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise FormalEconomicExecutionDefinitionError(
            "economic definition is not canonical JSON"
        ) from exc


def _strict_object(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload or payload.startswith(b"\xef\xbb\xbf"):
        raise FormalEconomicExecutionDefinitionError(f"{name} is not exact UTF-8 bytes")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if type(key) is not str or key in result:
                raise FormalEconomicExecutionDefinitionError(
                    f"{name} has a duplicate or non-text key"
                )
            result[key] = value
        return result

    def reject_float(value: str) -> None:
        raise FormalEconomicExecutionDefinitionError(
            f"{name} contains binary floating-point: {value}"
        )

    def reject_constant(value: str) -> None:
        raise FormalEconomicExecutionDefinitionError(
            f"{name} contains a non-finite value: {value}"
        )

    try:
        decoded = payload.decode("utf-8", errors="strict")
        value = json.loads(
            decoded, object_pairs_hook=pairs, parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FormalEconomicExecutionDefinitionError(f"{name} is not strict JSON") from exc
    if type(value) is not dict or _canonical(value) != payload:
        raise FormalEconomicExecutionDefinitionError(f"{name} bytes are not canonical")
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise FormalEconomicExecutionDefinitionError(f"{name} is not SHA-256")
    return value


def _safe(value: object, name: str) -> str:
    if type(value) is not str or _SAFE.fullmatch(value) is None:
        raise FormalEconomicExecutionDefinitionError(f"{name} is not a safe identifier")
    return value


def _axis(start: str, end_exclusive: str) -> tuple[str, ...]:
    return tuple(
        item.isoformat()
        for item in trading_sessions(date.fromisoformat(start), date.fromisoformat(end_exclusive))
        if item.isoformat() < end_exclusive
    )


def _axis_sha256(axis: tuple[str, ...]) -> str:
    return hashlib.sha256(_canonical(list(axis))).hexdigest()


def _fold_geometry_record() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for (
        fold_id, start, end, decision_count, decision_hash, last_decision,
        terminal_session, return_count, return_hash, observation_count,
        observation_hash,
    ) in _FOLD_GEOMETRY:
        decision_axis = _axis(start, end)
        return_axis = _axis(start, terminal_session)
        observation_axis = (*return_axis, terminal_session)
        if (
            decision_axis[0] != start
            or decision_axis[-1] != last_decision
            or len(decision_axis) != decision_count
            or _axis_sha256(decision_axis) != decision_hash
            or len(return_axis) != return_count
            or _axis_sha256(return_axis) != return_hash
            or return_count != decision_count + HOLDING_SESSIONS - 1
            or len(observation_axis) != observation_count
            or _axis_sha256(observation_axis) != observation_hash
            or observation_count != decision_count + HOLDING_SESSIONS
            or resolve_nth_session_after(last_decision, HOLDING_SESSIONS)
            != terminal_session
        ):
            raise FormalEconomicExecutionDefinitionError(
                "reviewed H20 execution geometry changed"
            )
        result.append(
            {
                "fold_id": fold_id,
                "decision_axis_start_inclusive": start,
                "decision_axis_end_exclusive": end,
                "decision_session_count": decision_count,
                "decision_axis_sha256": decision_hash,
                "last_decision_session": last_decision,
                "return_interval_start_axis_end_exclusive": terminal_session,
                "return_interval_count": return_count,
                "return_interval_start_axis_sha256": return_hash,
                "terminal_liquidation_session": terminal_session,
                "economic_observation_count_including_terminal_cost": observation_count,
                "economic_observation_axis_sha256": observation_hash,
            }
        )
    return result


def _bootstrap_base_ancestry_record(
    stock: StockEvaluationContract,
) -> dict[str, object]:
    return {
        "schema": "arv2-formal-economic-bootstrap-base-ancestry-v1",
        "domain": BOOTSTRAP_BASE_ANCESTRY_DOMAIN,
        "role": "base_ancestry_only_not_an_operative_sampling_seed",
        "source_stock_spec_id": stock.spec_id,
        "source_stock_spec_sha256": stock.spec_hash,
        "source_evaluation_id": EVALUATION_ID,
        "source_fold_manifest_id": SOURCE_FOLD_MANIFEST_ID,
        "source_fold_manifest_sha256": SOURCE_FOLD_MANIFEST_SHA256,
        "formal_fold_ids": list(FORMAL_FOLD_IDS),
        "source_view_ids": list(SOURCE_VIEW_IDS),
        "primary_slice_id": PRIMARY_SLICE_ID,
        "block_length_sessions": BOOTSTRAP_BLOCK_SESSIONS,
        "resamples": BOOTSTRAP_RESAMPLES,
        "sampler_version": "v1",
    }


def _definition_seed(stock: StockEvaluationContract) -> dict[str, object]:
    fold_geometry = _fold_geometry_record()
    bootstrap_base = _bootstrap_base_ancestry_record(stock)
    bootstrap_base_sha256 = hashlib.sha256(_canonical(bootstrap_base)).hexdigest()
    return {
        "schema": DEFINITION_SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "definition_id": None,
        "definition_sha256": None,
        "source_definition_closure": {
            "strategy_pdf_sha256": STRATEGY_PDF_SHA256,
            "stock_spec_id": stock.spec_id,
            "stock_spec_sha256": stock.spec_hash,
            "stock_economic_section_sha256": SOURCE_ECONOMIC_SECTION_SHA256,
            "fold_manifest_id": SOURCE_FOLD_MANIFEST_ID,
            "fold_manifest_sha256": SOURCE_FOLD_MANIFEST_SHA256,
        },
        "execution_plan_ancestry": {
            "qc_first_parent_plan_id": stock.parent_plan_id,
            "qc_first_parent_plan_sha256": stock.parent_plan_hash,
            "evaluation_id": EVALUATION_ID,
            "formal_primary_fold_ids": list(FORMAL_FOLD_IDS),
            "descriptive_sensitivity_fold_ids": list(DESCRIPTIVE_FOLD_IDS),
            "source_view_ids": list(SOURCE_VIEW_IDS),
            "primary_source_view_id": PRIMARY_SOURCE_VIEW_ID,
            "sensitivity_source_view_id": SENSITIVITY_SOURCE_VIEW_ID,
            "sensitivity_cannot_replace_or_rescue_primary": True,
        },
        "sample_and_clock": {
            "primary_slice_id": PRIMARY_SLICE_ID,
            "descriptive_slice_id": DESCRIPTIVE_SLICE_ID,
            "ranking_sample": "exact_H20_walk_forward_TEST_decision_sessions_only",
            "new_sleeves_outside_decision_axes": "forbidden",
            "post_last_decision_behavior": (
                "no_new_sleeves_continue_daily_valuation_until_every_20_session_"
                "sleeve_reaches_its_actual_exit_open"
            ),
            "folds_are_independent_wealth_paths": True,
            "fold_geometry": fold_geometry,
        },
        "eligible_ranking_and_sleeves": {
            "eligible_ranking_universe": (
                "every_point_in_time_eligible_security_on_the_exact_H20_TEST_"
                "decision_session_after_exhaustive_preoutcome_disposition"
            ),
            "accepted_ranking_rows": "authenticated_scored_decision_rows_only",
            "named_preoutcome_refusals": (
                "excluded_from_ranking_but_retained_in_exact_eligible_coverage_denominator"
            ),
            "structural_zero_rows": "eligible_and_ranked_at_exact_zero",
            "source_view_isolation": "rank_and_execute_each_source_view_separately",
            "positive_definition": "final_control_adjusted_firm_specific_score_strictly_gt_0",
            "sort_key": (
                "exact_Decimal_score_descending_then_permanent_security_id_UTF8_ascending"
            ),
            "quintile_count": "ceil(strictly_positive_scored_row_count_divided_by_5)",
            "selected_names": "first_quintile_count_rows_after_exact_sort",
            "minimum_sleeve_size": MINIMUM_SLEEVE_SIZE,
            "under_minimum": "entire_new_one_twentieth_sleeve_remains_cash",
            "sleeve_capital_fraction": {"numerator": 1, "denominator": 20},
            "within_sleeve_weighting": "equal_weight",
            "holding_return_intervals": HOLDING_SESSIONS,
            "overlapping_sleeve_count_at_steady_state": HOLDING_SESSIONS,
            "cash_underfill_return": "exact_zero_no_interest",
            "cash_and_underfill_never_redistributed_to_other_sleeves": True,
        },
        "daily_arithmetic_and_naming": {
            "decimal_context": {
                "precision": 50,
                "rounding": "ROUND_HALF_EVEN",
                "emin": -999999,
                "emax": 999999,
            },
            "stable_sum_order": (
                "ascending_exact_Decimal_copy_abs_then_signed_value_tie_break"
            ),
            "portfolio_return_clock": "session_open_to_next_NYSE_session_open",
            "security_return_basis": "total_return_adjusted_open_index_ratio_minus_one",
            "benchmark_security": "SPY",
            "benchmark_return_basis": "matching_total_return_adjusted_open_index_ratio_minus_one",
            "gross_portfolio_daily_total_return": (
                "sum_posttrade_security_target_weight_times_matching_security_daily_total_return"
            ),
            "transaction_cost_fraction": (
                "sum_absolute_net_security_target_change_times_cost_bps_per_side_divided_by_10000"
            ),
            "net_portfolio_daily_total_return": (
                "gross_portfolio_daily_total_return_minus_transaction_cost_fraction"
            ),
            "benchmark_daily_total_return": "matching_SPY_daily_total_return_no_strategy_cost",
            "net_excess_daily_total_return": (
                "net_portfolio_daily_total_return_minus_benchmark_daily_total_return"
            ),
            "primary_statistic_exact_name": "mean_net_excess_daily_total_return",
            "cumulative_net_portfolio_total_return": (
                "product_over_valid_complete_path_of_one_plus_net_portfolio_daily_total_return_minus_one"
            ),
            "cumulative_benchmark_total_return": (
                "product_over_same_valid_complete_path_of_one_plus_benchmark_daily_total_return_minus_one"
            ),
            "geometric_relative_total_return": (
                "one_plus_cumulative_net_portfolio_total_return_divided_by_one_plus_"
                "cumulative_benchmark_total_return_minus_one"
            ),
            "forbidden_ambiguous_name": "cumulative_net_excess_total_return",
            "forbidden_relative_formula": (
                "product_of_one_plus_arithmetic_net_excess_daily_total_return_minus_one"
            ),
        },
        "turnover_cost_and_wealth_state": {
            "session_sequence": (
                "at_open_expire_due_sleeves_add_only_an_eligible_new_sleeve_compute_"
                "target_trade_then_measure_open_to_next_open_return"
            ),
            "target_security_weight": (
                "sum_one_twentieth_divided_by_selected_name_count_across_active_sleeves"
            ),
            "cash_target_weight": "one_minus_sum_security_target_weights",
            "pretrade_security_weight": (
                "prior_posttrade_weight_times_one_plus_security_return_divided_by_"
                "one_plus_prior_net_portfolio_return"
            ),
            "daily_turnover_exact_name": "gross_traded_notional_fraction_of_pretrade_NAV",
            "daily_turnover_formula": (
                "sum_over_union_of_pretrade_and_target_security_ids_of_absolute_"
                "target_weight_minus_pretrade_weight"
            ),
            "half_turnover_convention": False,
            "zero_target_changes_retained": True,
            "initial_entry_cost_included": True,
            "cost_bps_per_side_grid": list(COST_BPS_PER_SIDE),
            "primary_cost_bps_per_side": PRIMARY_COST_BPS_PER_SIDE,
            "primary_cost_variant_only_can_pass_gate": True,
            "post_cost_wealth_nonpositive": "INVALID_DATA_entire_independent_fold_excluded",
            "leverage": False,
            "short_positions": False,
            "borrowed_cash": False,
            "maximum_security_target_gross_exposure": "one",
        },
        "liquidity_impact_scope": {
            "liquidity_impact_binding_sha256": None,
            "binding_status": "absent",
            "role": "capacity_diagnostic_only_never_promotion_gate",
            "missing_binding_blocks_primary_execution_definition": False,
            "may_replace_rescue_or_modify_the_primary_cost_gate": False,
            "liquidity_or_market_impact_execution_authority": False,
            "provider_outcome_qc_result_or_trading_authority": False,
        },
        "terminal_and_refusal_handling": {
            "terminal_policy_id": TERMINAL_POLICY_ID,
            "terminal_disposition_precedes_ordinary_daily_bar": True,
            "qc_delisting_price_is_terminal_payoff": False,
            "audited_terminal_payoff": (
                "apply_once_on_its_actual_terminal_return_interval_then_remove_"
                "the_security_exposure_without_redistribution"
            ),
            "post_terminal_active_sleeve_treatment": (
                "remove_only_the_named_terminal_security_at_its_actual_terminal_session_"
                "and_hold_its_remaining_active_sleeve_weight_as_cash_through_scheduled_"
                "exit_without_redistribution"
            ),
            "benchmark_splice_continuation": (
                "use_matching_SPY_total_return_only_when_the_authenticated_terminal_"
                "policy_explicitly_names_that_disposition"
            ),
            "unresolved_terminal_or_missing_held_security_return": (
                "named_refusal_loses_wealth_and_weight_state_and_excludes_the_entire_"
                "independent_fold_from_point_estimates_and_resampling"
            ),
            "missing_benchmark_return": (
                "named_session_refusal_not_zero_filled_portfolio_wealth_state_may_"
                "continue_but_complete_path_and_that_sessions_net_excess_are_unavailable"
            ),
            "terminal_runoff": (
                "after_last_decision_expire_each_remaining_sleeve_on_its_actual_20th_"
                "session_exit_open_and_leave_proceeds_in_cash"
            ),
            "terminal_liquidation_cost": (
                "record_on_the_actual_terminal_liquidation_session_as_its_own_dated_"
                "cost_only_net_portfolio_and_net_excess_entry_with_zero_incremental_"
                "benchmark_return"
            ),
            "prior_session_cost_backcharge": "forbidden",
            "restart_after_state_loss": "forbidden",
            "cross_fold_wealth_or_sleeve_carry": "forbidden",
        },
        "inference": {
            "primary_series": "net_excess_daily_total_return",
            "date_weighting": "equal_weight_valid_complete_sessions",
            "hac": {
                "role": "descriptive_only_not_a_separate_gate",
                "lag_sessions": HAC_LAG_SESSIONS,
                "axis": "actual_NYSE_session_positions_never_compress_named_gaps",
                "kernel": "Bartlett",
                "lag_weight": "(20_plus_1_minus_lag)_divided_by_(20_plus_1)",
                "autocovariance_denominator": "total_valid_session_count_not_lag_pair_count",
                "observed_pair_count_by_lag_required": True,
            },
            "centered_complete_session_moving_block_bootstrap": {
                "block_length_sessions": BOOTSTRAP_BLOCK_SESSIONS,
                "resamples": BOOTSTRAP_RESAMPLES,
                "null_centering": (
                    "subtract_observed_equal_session_mean_from_each_valid_net_excess_return"
                ),
                "eligible_block_start": (
                    "within_one_fold_and_all_20_consecutive_expected_NYSE_sessions_have_"
                    "valid_net_excess_returns"
                ),
                "fold_boundaries_never_crossed": True,
                "blocks_drawn_per_fold": (
                    "ceil(original_valid_session_count_in_fold_divided_by_20)"
                ),
                "replicate_fold_length": (
                    "concatenate_drawn_blocks_in_draw_order_then_truncate_to_original_"
                    "valid_session_count_for_that_fold"
                ),
                "replicate_statistic": "absolute_equal_session_pooled_mean",
                "observed_statistic": "absolute_equal_session_pooled_mean",
                "two_sided_p_value": (
                    "one_plus_count_replicate_absolute_mean_gte_observed_absolute_mean_"
                    "divided_by_resamples_plus_one"
                ),
                "base_seed_ancestry_record": bootstrap_base,
                "base_seed_ancestry_record_encoding": (
                    "canonical_sorted_compact_UTF8_JSON_plus_one_LF"
                ),
                "base_seed_ancestry_sha256": bootstrap_base_sha256,
                "base_seed_ancestry_is_operative": False,
                "sole_operative_seed_and_draw_authority": {
                    "schema": OPERATIVE_REPORT_CONTRACT_SCHEMA,
                    "seed_record_path": "bootstrap.stock_FM_and_economic_seed_record",
                    "seed_domain": OPERATIVE_BOOTSTRAP_SEED_DOMAIN,
                    "required_seed_fields": [
                        "qc_first_plan_sha256",
                        "fold_manifest_sha256",
                        "evaluation_id",
                        "economic_execution_definition_sha256",
                        "secondary_hypothesis_registry_sha256",
                        "deflated_sharpe_trial_registry_sha256",
                        "sampler_version",
                    ],
                    "seed_digest_path": (
                        "bootstrap.stock_FM_and_economic_seed_sha256"
                    ),
                    "draw_domain_path": "bootstrap.draw_domain",
                    "draw_domain": OPERATIVE_BOOTSTRAP_DRAW_DOMAIN,
                    "economic_definition_sha256_must_equal_this_authenticated_definition": True,
                    "child_contract_must_explicitly_mark_parent_base_ancestry_only": True,
                },
                "retry_or_seed_change_after_outcome": "forbidden",
            },
            "primary_pass_rule": (
                "10_bps_per_side_mean_net_excess_daily_total_return_strictly_positive_"
                "and_centered_two_sided_block_bootstrap_p_strictly_below_0.05"
            ),
            "diagnostic_cost_variants_cannot_rescue": True,
        },
        "exact_denominators": {
            "eligible_ranking_coverage": (
                "all_point_in_time_eligible_H20_security_decision_rows_before_"
                "scored_or_named_preoutcome_disposition"
            ),
            "scored_ranking_coverage": "same_eligible_denominator",
            "positive_score_share": "authenticated_scored_decision_rows",
            "selected_name_share": "strictly_positive_scored_rows",
            "sleeve_disposition": (
                "every_expected_H20_decision_session_exactly_selected_or_cash_underfill_"
                "with_row_refusals_accounted_separately"
            ),
            "daily_return_coverage": (
                "every_expected_fold_return_interval_exactly_valid_or_named_refused_"
                "or_excluded_after_held_state_loss"
            ),
            "mean_daily_turnover": (
                "every_expected_rebalance_runoff_and_terminal_liquidation_session_"
                "including_exact_zero_turnover_sessions"
            ),
            "overlap_membership": (
                "sum_selected_security_memberships_across_all_active_sleeves"
            ),
            "overlap_duplicate_numerator": (
                "active_sleeve_security_memberships_minus_distinct_held_security_count"
            ),
            "overlap_zero_denominator": "report_named_unavailable_not_zero",
            "source_views_and_folds_reported_separately": True,
            "silent_drop_skip_imputation_or_zero_fill": "forbidden",
        },
        "capabilities": {
            "provider_access": False,
            "outcome_access": False,
            "qc_project_create": False,
            "qc_object_store_write": False,
            "qc_upload": False,
            "qc_compile": False,
            "qc_launch": False,
            "result_read": False,
            "result_disposition": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _definition_record(stock: StockEvaluationContract) -> dict[str, object]:
    seed = _definition_seed(stock)
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["definition_sha256"] = digest
    seed["definition_id"] = f"arv2-formal-economic-execution-{digest[:24]}"
    return seed


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalEconomicExecutionDefinition:
    definition_id: str
    definition_sha256: str
    payload_sha256: str
    bootstrap_base_ancestry_sha256: str
    source_stock_spec_id: str
    source_stock_spec_sha256: str
    source_evaluation_id: str
    source_parent_plan_id: str
    source_parent_plan_sha256: str
    _source_stock_contract: StockEvaluationContract = dataclasses.field(repr=False)
    _canonical_document: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        require_formal_economic_execution_definition(self)
        return _strict_object(self._canonical_document, "economic definition document")


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalEconomicExecutionBinding:
    binding_id: str
    binding_sha256: str
    schema: str
    definition: FormalEconomicExecutionDefinition
    definition_id: str
    definition_sha256: str
    definition_payload_sha256: str
    definition_byte_count: int
    source_stock_spec_id: str
    source_stock_spec_sha256: str
    source_evaluation_id: str
    source_parent_plan_id: str
    source_parent_plan_sha256: str
    source_fold_manifest_id: str
    source_fold_manifest_sha256: str
    bootstrap_base_ancestry_sha256: str
    runtime_action_authority: bool
    _canonical_document: bytes = dataclasses.field(repr=False)

    def to_record(self) -> dict[str, object]:
        require_formal_economic_execution_binding(self)
        return _strict_object(self._canonical_document, "economic execution binding")


_DEFINITIONS: dict[int, tuple[object, ...]] = {}
_BINDINGS: dict[int, tuple[object, ...]] = {}
_AUTHORITY_LOCK = threading.RLock()


def _make_economic_authority_vault():
    """Keep process authority outside the reflectively mutable mirrors.

    The module-level dictionaries remain only as cleanup/accounting mirrors so
    existing diagnostics can census them. Authentication additionally requires
    identity with an entry held in this tuple-backed lexical vault. Reflected
    insertion into either public dictionary therefore cannot authenticate a
    caller-constructed definition or binding.
    """

    private_registries: tuple[
        tuple[str, tuple[tuple[int, tuple[object, ...]], ...]], ...
    ] = (("definition", ()), ("binding", ()))
    register_provenance: tuple[
        tuple[
            str, object, object, str, str, int,
            tuple[tuple[str, object], ...],
        ], ...
    ] = ()
    authority_pid = os.getpid()
    authority_module = sys.modules.get(__name__)
    missing_global_value = object()

    def public_registry(
        kind: str,
    ) -> dict[int, tuple[object, ...]]:
        if kind == "definition":
            return _DEFINITIONS
        if kind == "binding":
            return _BINDINGS
        raise AssertionError("unknown economic authority kind")

    def private_registry(
        kind: str,
    ) -> tuple[tuple[int, tuple[object, ...]], ...]:
        return next(
            (records for name, records in private_registries if name == kind),
            (),
        )

    def replace_private_registry(
        kind: str,
        records: tuple[tuple[int, tuple[object, ...]], ...],
    ) -> None:
        nonlocal private_registries

        private_registries = tuple(
            (name, records if name == kind else current)
            for name, current in private_registries
        )

    def private_entry(
        kind: str, identity: int,
    ) -> tuple[object, ...] | None:
        return next(
            (
                entry
                for key, entry in private_registry(kind)
                if key == identity
            ),
            None,
        )

    def caller_is_exact(kind: str) -> bool:
        provenance = next(
            (
                item
                for item in register_provenance
                if item[0] == kind
            ),
            None,
        )
        if provenance is None:
            return False
        (
            _kind,
            expected_function,
            expected_code,
            expected_name,
            expected_filename,
            globals_id,
            expected_global_bindings,
        ) = provenance
        frame = sys._getframe(2)
        return (
            frame is not None
            and frame.f_code is expected_code
            and frame.f_code.co_name == expected_name
            and frame.f_code.co_filename == expected_filename
            and frame.f_globals.get("__name__") == __name__
            and id(frame.f_globals) == globals_id
            and authority_module is not None
            and sys.modules.get(__name__) is authority_module
            and vars(authority_module) is frame.f_globals
            and expected_function.__code__ is expected_code
            and expected_function.__globals__ is frame.f_globals
            and expected_function.__name__ == expected_name
            and all(
                expected_function.__globals__.get(
                    name, missing_global_value
                ) is expected
                and frame.f_globals.get(name, missing_global_value)
                is expected
                for name, expected in expected_global_bindings
            )
            and frame.f_globals.get(expected_name) is expected_function
        )

    def forget(
        kind: str, identity: int, reference: object,
    ) -> None:
        public = public_registry(kind)
        with _AUTHORITY_LOCK:
            current = private_entry(kind, identity)
            if current is not None and current[0] is reference:
                replace_private_registry(
                    kind,
                    tuple(
                        item
                        for item in private_registry(kind)
                        if item[0] != identity
                    ),
                )
            if public.get(identity) is current:
                public.pop(identity, None)

    def reset_after_fork() -> None:
        nonlocal private_registries
        global _DEFINITIONS, _BINDINGS, _AUTHORITY_LOCK

        _DEFINITIONS = {}
        _BINDINGS = {}
        _AUTHORITY_LOCK = threading.RLock()
        private_registries = (("definition", ()), ("binding", ()))

    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=reset_after_fork)

    def register(
        kind: str,
        value: object,
        entry_tail: tuple[object, ...],
    ) -> object:
        public = public_registry(kind)
        if os.getpid() != authority_pid or not caller_is_exact(kind):
            raise FormalEconomicExecutionDefinitionError(
                f"economic {kind} register caller changed"
            )
        identity = id(value)
        reference = weakref.ref(
            value,
            lambda ref, authority_kind=kind, key=identity: forget(
                authority_kind, key, ref
            ),
        )
        entry = (reference, *entry_tail, os.getpid())
        with _AUTHORITY_LOCK:
            if private_entry(kind, identity) is not None or identity in public:
                raise FormalEconomicExecutionDefinitionError(
                    f"economic {kind} authority identity was reused"
                )
            replace_private_registry(
                kind,
                (*private_registry(kind), (identity, entry)),
            )
            public[identity] = entry
        return value

    def current(
        kind: str, value: object,
    ) -> tuple[object, ...] | None:
        public = public_registry(kind)
        identity = id(value)
        with _AUTHORITY_LOCK:
            private = private_entry(kind, identity)
            mirrored = public.get(identity)
            if (
                private is None
                or mirrored is not private
                or private[0]() is not value
                or private[-1] != os.getpid()
            ):
                replace_private_registry(
                    kind,
                    tuple(
                        item
                        for item in private_registry(kind)
                        if item[0] != identity
                    ),
                )
                public.pop(identity, None)
                return None
            return private

    def seal_provenance(
        value: tuple[tuple[str, object], ...],
    ) -> None:
        nonlocal register_provenance

        if (
            register_provenance
            or type(value) is not tuple
            or tuple(item[0] for item in value) != (
                "definition", "binding",
            )
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[1]) is not type(seal_provenance)
                or authority_module is None
                or item[1].__module__ != __name__
                or item[1].__globals__ is not vars(authority_module)
                for item in value
            )
        ):
            raise FormalEconomicExecutionDefinitionError(
                "economic authority provenance changed"
            )
        try:
            register_provenance = tuple(
                (
                    kind,
                    function,
                    function.__code__,
                    function.__name__,
                    function.__code__.co_filename,
                    id(function.__globals__),
                    tuple(
                        (
                            name,
                            function.__globals__.get(
                                name, missing_global_value
                            ),
                        )
                        for name in function.__code__.co_names
                    ),
                )
                for kind, function in value
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise FormalEconomicExecutionDefinitionError(
                "economic authority provenance changed"
            ) from exc

    return register, current, seal_provenance


(
    _economic_authority_register,
    _economic_authority_current,
    _seal_economic_authority_provenance,
) = _make_economic_authority_vault()


def build_formal_economic_execution_definition(
    source_stock_contract: StockEvaluationContract,
) -> FormalEconomicExecutionDefinition:
    """Build the sole canonical definition from the authenticated stock spec."""

    _require_module_closure()
    try:
        stock = require_loaded_stock_evaluation_contract(source_stock_contract)
    except (StockEvaluationContractError, TypeError, ValueError) as exc:
        raise FormalEconomicExecutionDefinitionError(
            "source stock evaluation contract did not authenticate"
        ) from exc
    if (
        stock.spec_id != SOURCE_STOCK_SPEC_ID
        or stock.spec_hash != SOURCE_STOCK_SPEC_SHA256
        or stock.parent_plan_id != SOURCE_PARENT_PLAN_ID
        or stock.parent_plan_hash != SOURCE_PARENT_PLAN_SHA256
        or stock.section_hashes.get("economic_definition")
        != SOURCE_ECONOMIC_SECTION_SHA256
    ):
        raise FormalEconomicExecutionDefinitionError("source stock ancestry changed")
    record = _definition_record(stock)
    payload = _canonical(record)
    bootstrap_base = _bootstrap_base_ancestry_record(stock)
    bootstrap_base_sha256 = hashlib.sha256(_canonical(bootstrap_base)).hexdigest()
    value = object.__new__(FormalEconomicExecutionDefinition)
    values = {
        "definition_id": record["definition_id"],
        "definition_sha256": record["definition_sha256"],
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "bootstrap_base_ancestry_sha256": bootstrap_base_sha256,
        "source_stock_spec_id": stock.spec_id,
        "source_stock_spec_sha256": stock.spec_hash,
        "source_evaluation_id": EVALUATION_ID,
        "source_parent_plan_id": stock.parent_plan_id,
        "source_parent_plan_sha256": stock.parent_plan_hash,
        "_source_stock_contract": stock,
        "_canonical_document": payload,
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    _economic_authority_register(
        "definition",
        value,
        (weakref.ref(stock), payload),
    )
    return require_formal_economic_execution_definition(value)


def load_formal_economic_execution_definition(
    *, source_stock_contract: StockEvaluationContract, payload: bytes,
) -> FormalEconomicExecutionDefinition:
    """Authenticate exact canonical bytes, then mint a process-local object."""

    candidate = build_formal_economic_execution_definition(source_stock_contract)
    parsed = _strict_object(payload, "economic definition payload")
    if payload != candidate._canonical_document or parsed != candidate.to_record():
        raise FormalEconomicExecutionDefinitionError(
            "economic definition payload changed from the canonical candidate"
        )
    return candidate


def require_formal_economic_execution_definition(
    value: FormalEconomicExecutionDefinition,
) -> FormalEconomicExecutionDefinition:
    _require_module_closure()
    if type(value) is not FormalEconomicExecutionDefinition:
        raise FormalEconomicExecutionDefinitionError("economic definition changed type")
    registered = _economic_authority_current("definition", value)
    if registered is None or registered[0]() is not value:
        raise FormalEconomicExecutionDefinitionError(
            "economic definition is not builder-authenticated"
        )
    stock = registered[1]()
    if stock is None or value._source_stock_contract is not stock:
        raise FormalEconomicExecutionDefinitionError("source stock definition was released")
    try:
        require_loaded_stock_evaluation_contract(stock)
    except (StockEvaluationContractError, TypeError, ValueError) as exc:
        raise FormalEconomicExecutionDefinitionError("source stock definition changed") from exc
    expected = _definition_record(stock)
    payload = _canonical(expected)
    bootstrap_base_sha256 = hashlib.sha256(
        _canonical(_bootstrap_base_ancestry_record(stock))
    ).hexdigest()
    if (
        registered[2] != payload
        or registered[3] != os.getpid()
        or value._canonical_document is not registered[2]
        or value.definition_id != expected["definition_id"]
        or value.definition_sha256 != expected["definition_sha256"]
        or value.payload_sha256 != hashlib.sha256(payload).hexdigest()
        or value.bootstrap_base_ancestry_sha256 != bootstrap_base_sha256
        or value.source_stock_spec_id != stock.spec_id
        or value.source_stock_spec_sha256 != stock.spec_hash
        or value.source_evaluation_id != EVALUATION_ID
        or value.source_parent_plan_id != stock.parent_plan_id
        or value.source_parent_plan_sha256 != stock.parent_plan_hash
    ):
        raise FormalEconomicExecutionDefinitionError("economic definition changed")
    return value


def render_formal_economic_execution_definition_bytes(
    value: FormalEconomicExecutionDefinition,
) -> bytes:
    return bytes(require_formal_economic_execution_definition(value)._canonical_document)


def _binding_record(
    definition: FormalEconomicExecutionDefinition,
) -> dict[str, object]:
    seed: dict[str, object] = {
        "schema": BINDING_SCHEMA,
        "binding_id": None,
        "binding_sha256": None,
        "definition_id": definition.definition_id,
        "definition_sha256": definition.definition_sha256,
        "definition_payload_sha256": definition.payload_sha256,
        "definition_byte_count": len(definition._canonical_document),
        "source_stock_spec_id": definition.source_stock_spec_id,
        "source_stock_spec_sha256": definition.source_stock_spec_sha256,
        "source_evaluation_id": definition.source_evaluation_id,
        "source_parent_plan_id": definition.source_parent_plan_id,
        "source_parent_plan_sha256": definition.source_parent_plan_sha256,
        "source_fold_manifest_id": SOURCE_FOLD_MANIFEST_ID,
        "source_fold_manifest_sha256": SOURCE_FOLD_MANIFEST_SHA256,
        "bootstrap_base_ancestry_sha256": (
            definition.bootstrap_base_ancestry_sha256
        ),
        "status": STATUS,
        "authority": AUTHORITY,
        "runtime_action_authority": False,
    }
    digest = hashlib.sha256(_canonical(seed)).hexdigest()
    seed["binding_sha256"] = digest
    seed["binding_id"] = f"arv2-formal-economic-execution-binding-{digest[:24]}"
    return seed


def build_formal_economic_execution_binding(
    definition: FormalEconomicExecutionDefinition,
) -> FormalEconomicExecutionBinding:
    """Project the exact definition as the typed input/runtime binding."""

    _require_module_closure()
    definition = require_formal_economic_execution_definition(definition)
    seed = _binding_record(definition)
    digest = str(seed["binding_sha256"])
    payload = _canonical(seed)
    value = object.__new__(FormalEconomicExecutionBinding)
    values = {
        "binding_id": seed["binding_id"],
        "binding_sha256": digest,
        "schema": BINDING_SCHEMA,
        "definition": definition,
        "definition_id": definition.definition_id,
        "definition_sha256": definition.definition_sha256,
        "definition_payload_sha256": definition.payload_sha256,
        "definition_byte_count": len(definition._canonical_document),
        "source_stock_spec_id": definition.source_stock_spec_id,
        "source_stock_spec_sha256": definition.source_stock_spec_sha256,
        "source_evaluation_id": definition.source_evaluation_id,
        "source_parent_plan_id": definition.source_parent_plan_id,
        "source_parent_plan_sha256": definition.source_parent_plan_sha256,
        "source_fold_manifest_id": SOURCE_FOLD_MANIFEST_ID,
        "source_fold_manifest_sha256": SOURCE_FOLD_MANIFEST_SHA256,
        "bootstrap_base_ancestry_sha256": (
            definition.bootstrap_base_ancestry_sha256
        ),
        "runtime_action_authority": False,
        "_canonical_document": payload,
    }
    for name, item in values.items():
        object.__setattr__(value, name, item)
    _economic_authority_register(
        "binding",
        value,
        (weakref.ref(definition), payload),
    )
    return require_formal_economic_execution_binding(value)


def require_formal_economic_execution_binding(
    value: FormalEconomicExecutionBinding,
) -> FormalEconomicExecutionBinding:
    _require_module_closure()
    if type(value) is not FormalEconomicExecutionBinding:
        raise FormalEconomicExecutionDefinitionError("economic binding changed type")
    registered = _economic_authority_current("binding", value)
    if registered is None or registered[0]() is not value:
        raise FormalEconomicExecutionDefinitionError(
            "economic binding is not builder-authenticated"
        )
    definition = registered[1]()
    if definition is None or value.definition is not definition:
        raise FormalEconomicExecutionDefinitionError("economic definition parent was released")
    require_formal_economic_execution_definition(definition)
    expected = _binding_record(definition)
    expected_payload = _canonical(expected)
    if (
        registered[2] != expected_payload
        or registered[3] != os.getpid()
        or value._canonical_document is not registered[2]
        or value.binding_id != expected["binding_id"]
        or value.binding_sha256 != expected["binding_sha256"]
        or value.schema != BINDING_SCHEMA
        or value.definition_id != definition.definition_id
        or value.definition_sha256 != definition.definition_sha256
        or value.definition_payload_sha256 != definition.payload_sha256
        or value.definition_byte_count != len(definition._canonical_document)
        or value.source_stock_spec_id != definition.source_stock_spec_id
        or value.source_stock_spec_sha256 != definition.source_stock_spec_sha256
        or value.source_evaluation_id != definition.source_evaluation_id
        or value.source_parent_plan_id != definition.source_parent_plan_id
        or value.source_parent_plan_sha256 != definition.source_parent_plan_sha256
        or value.source_fold_manifest_id != SOURCE_FOLD_MANIFEST_ID
        or value.source_fold_manifest_sha256 != SOURCE_FOLD_MANIFEST_SHA256
        or value.bootstrap_base_ancestry_sha256
        != definition.bootstrap_base_ancestry_sha256
        or value.runtime_action_authority is not False
    ):
        raise FormalEconomicExecutionDefinitionError("economic binding changed")
    return value


_seal_economic_authority_provenance(
    (
        (
            "definition",
            build_formal_economic_execution_definition,
        ),
        (
            "binding",
            build_formal_economic_execution_binding,
        ),
    )
)


def formal_economic_execution_definition_record(
    value: FormalEconomicExecutionDefinition,
) -> dict[str, object]:
    return require_formal_economic_execution_definition(value).to_record()


def formal_economic_execution_binding_record(
    value: FormalEconomicExecutionBinding,
) -> dict[str, object]:
    return require_formal_economic_execution_binding(value).to_record()


def formal_economic_terminal_liquidation_session(
    value: FormalEconomicExecutionBinding,
) -> str:
    """Return the exact last H20 sleeve liquidation session.

    This is deliberately distinct from the enclosing four-horizon formal
    runtime end.  H20 economic accounting runs off on 2026-01-30, while the
    shared formal runtime must remain open through the later H60 exit.
    """

    binding = require_formal_economic_execution_binding(value)
    document = binding.definition.to_record()
    sample = document.get("sample_and_clock")
    if type(sample) is not dict:
        raise FormalEconomicExecutionDefinitionError(
            "economic sample/clock record changed type"
        )
    folds = sample.get("fold_geometry")
    if type(folds) is not list or len(folds) != len(FORMAL_FOLD_IDS):
        raise FormalEconomicExecutionDefinitionError(
            "economic fold geometry changed type or count"
        )
    final = folds[-1]
    if (
        type(final) is not dict
        or final.get("fold_id") != FORMAL_FOLD_IDS[-1]
        or final.get("terminal_liquidation_session") != "2026-01-30"
    ):
        raise FormalEconomicExecutionDefinitionError(
            "final H20 terminal liquidation session changed"
        )
    return "2026-01-30"


__all__ = [
    "AUTHORITY", "BINDING_SCHEMA", "BOOTSTRAP_BLOCK_SESSIONS",
    "BOOTSTRAP_BASE_ANCESTRY_DOMAIN", "BOOTSTRAP_RESAMPLES",
    "COST_BPS_PER_SIDE",
    "DEFINITION_SCHEMA", "DESCRIPTIVE_FOLD_IDS", "DESCRIPTIVE_SLICE_ID",
    "FORMAL_FOLD_IDS", "FormalEconomicExecutionBinding",
    "FormalEconomicExecutionDefinition", "FormalEconomicExecutionDefinitionError",
    "HAC_LAG_SESSIONS", "HOLDING_SESSIONS", "MINIMUM_SLEEVE_SIZE",
    "OPERATIVE_BOOTSTRAP_DRAW_DOMAIN", "OPERATIVE_BOOTSTRAP_SEED_DOMAIN",
    "OPERATIVE_REPORT_CONTRACT_SCHEMA", "PRIMARY_COST_BPS_PER_SIDE",
    "PRIMARY_SLICE_ID", "PRIMARY_SOURCE_VIEW_ID",
    "SENSITIVITY_SOURCE_VIEW_ID", "SOURCE_VIEW_IDS", "STATUS",
    "build_formal_economic_execution_binding",
    "build_formal_economic_execution_definition",
    "formal_economic_execution_binding_record",
    "formal_economic_execution_definition_record",
    "formal_economic_terminal_liquidation_session",
    "load_formal_economic_execution_definition",
    "render_formal_economic_execution_definition_bytes",
    "require_formal_economic_execution_binding",
    "require_formal_economic_execution_definition",
]
