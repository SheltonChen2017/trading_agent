"""Outcome-free execution contract for the ARV2 formal result report.

This module freezes *what* a later formal evaluator must aggregate before any
outcome is read.  It deliberately does not evaluate a row, open a provider,
contact QuantConnect, or authorize a result read.  The economic execution
definition remains a separately reviewed parent and is therefore supplied by
its exact SHA-256 when this child is built; an unresolved placeholder can never
produce a valid contract.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import threading
import weakref
from typing import Any


SCHEMA = "arv2-formal-report-execution-contract-v1"
STATUS = "outcome_free_candidate_pending_independent_review"
AUTHORITY = (
    "report_execution_definition_only_no_input_outcome_qc_result_deployment_"
    "order_or_trading_authority"
)
EVALUATION_ID = "arv2-eval-stock-historical-qc-001"
QC_FIRST_PLAN_SHA256 = (
    "36e455e72b8750fe3f34773382870e10e62f3f40b5392ae587690bda081b85dc"
)
FOLD_MANIFEST_SHA256 = (
    "1002155dbe8e3e87b220b7419039bff95f5c0812d2306c56a8ac51b76c5d7611"
)
STOCK_SUCCESSOR_SHA256 = (
    "a9a2210b8f6582bc3ce9e533ce33e9b51ffc0a0b3203b62ad21d9d373ce06f95"
)
MATCHED_COMPARISON_SHA256 = (
    "b94a3457b848c4dc1f6dee77ef366002362573431eb9cc2fc3b8f530ec7f89c9"
)
MAX_CONTRACT_BYTES = 131_072
MAXIMUM_ENCODED_BYTES_PER_REPORT_ROW = 16_384
REPORT_FAMILY_OBJECT_UNCOMPRESSED_BYTE_CEILING = 4_194_304
REPORT_FAMILY_OBJECT_COMPRESSED_BYTE_CEILING = 4_200_000
SUMMARY_ROOT_COMPRESSED_BYTE_CEILING = 200_000
SUMMARY_ROOT_DECOMPRESSED_BYTE_CEILING = 4_194_304

FORMAL_FOLD_IDS = tuple(f"arv2-wf-test-{year}" for year in range(2020, 2026))
DESCRIPTIVE_FOLD_IDS = tuple(
    f"arv2-wf-test-{year}" for year in range(2021, 2026)
)
SOURCE_VIEW_IDS = (
    "current_row_current_vintage_non_pristine_pit",
    "conservative_censored_current_vintage_non_pristine_pit",
)
SLICE_IDS = (
    "formal_2020_2025_primary",
    "owner_2021_2025_descriptive_sensitivity",
)
HORIZONS = (1, 5, 20, 60)
RATING_ACTIONS = ("upgrades", "downgrades")
COHORT_IDS = (
    "all",
    "exact_earnings_day",
    "one_to_two_days_after_earnings",
    "three_to_five_days_after_earnings",
    "over_five_days_after_earnings",
    "pre_earnings",
)
EARNINGS_EXCLUSION_IDS = ("earnings_exclusion_pm2", "earnings_exclusion_pm5")
PORTFOLIO_VARIANT_IDS = (
    "direct_stock_equal_weight",
    "direct_stock_inverse_volatility",
    "direct_stock_score_weight",
)
COST_BPS_PER_SIDE = (0, 5, 10, 20)
REPORT_FAMILY_IDS = (
    "event_returns_by_rating_action_horizon_and_cohort",
    "event_time_cumulative_abnormal_returns_by_rating_action",
    "information_coefficient_summary_by_horizon_and_year",
    "fama_macbeth_coefficients_hac_and_pair_counts",
    "firm_vs_global_paired_comparison_and_coverage",
    "direct_stock_gross_net_turnover_and_overlap",
    "refusal_coverage_component_and_power_accounting",
    "plot_data_percentile_vs_future_return",
    "plot_data_rolling_ic_and_sharpe",
    "plot_data_year_by_year_out_of_sample_alpha",
    "plot_data_signal_decay",
    "plot_data_turnover_vs_net_return",
    "plot_data_drawdown_and_time_underwater",
)
PRIMARY_OUTPUT_IDS = (
    "bullish_20_session_fama_macbeth",
    "net_20_session_sleeve",
    "firm_specific_vs_global_map_paired_20_session_ic",
)
COMPARATOR_LEDGER_IDS = (
    "endpoint_pair_mapping",
    "active_security_date_rows",
    "common_event_components",
    "component_member_incidence",
    "score_capable_dates",
)
F6_ACCOUNTING_AXIS = (
    {
        "accounting_kind": "preoutcome_decision_terminal",
        "reason_or_component_ids": ("all",),
        "scope": "each_declared_slice_fold_and_its_POOLED_scope",
        "expected_count_authority": (
            "unique_authenticated_physical_decision_keys_before_any_outcome_read"
        ),
    },
    {
        "accounting_kind": "horizon_outcome_terminal",
        "reason_or_component_ids": tuple(f"h{item}" for item in HORIZONS),
        "scope": "each_declared_slice_fold_and_its_POOLED_scope",
        "expected_count_authority": (
            "preoutcome_decision_keys_on_the_exact_fold_and_horizon_axis"
        ),
    },
    {
        "accounting_kind": "economic_trial_terminal",
        "reason_or_component_ids": "exact_six_strategy_trial_registry_ids",
        "scope": "each_declared_slice_fold_and_its_POOLED_scope",
        "expected_count_authority": (
            "exact_economic_observation_axis_including_terminal_liquidation"
        ),
    },
    {
        "accounting_kind": "lifecycle_terminal_disposition",
        "reason_or_component_ids": ("all",),
        "scope": "each_attributed_source_view_slice_fold_and_POOLED_scope",
        "expected_count_authority": (
            "authenticated_terminal_package_slots_attributed_at_use_key_construction"
        ),
    },
    {
        "accounting_kind": "global_comparator_coverage_ledger",
        "reason_or_component_ids": COMPARATOR_LEDGER_IDS,
        "scope": "formal_folds_and_formal_POOLED_scope",
        "expected_count_authority": "authenticated_ledger_denominator",
    },
    {
        "accounting_kind": "report_family_terminal",
        "reason_or_component_ids": REPORT_FAMILY_IDS,
        "scope": "each_scope_on_which_the_named_family_declares_an_expected_key_grid",
        "expected_count_authority": (
            "predeclared_contract_key_grid_frozen_before_any_family_row_is_built"
        ),
    },
    {
        "accounting_kind": "power_floor",
        "reason_or_component_ids": (
            "valid_h20_fm_dates",
            "connected_h20_components",
        ),
        "scope": "formal_POOLED_scope_only",
        "expected_count_authority": (
            "authenticated_preoutcome_H20_date_or_component_census"
        ),
    },
)

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_ZERO_SHA256 = "0" * 64
_CONTRACT_PREFIX = "arv2-formal-report-contract-"
_SECONDARY_PREFIX = "arv2-secondary-hypothesis-registry-"
_TRIAL_PREFIX = "arv2-strategy-trial-registry-"


class FormalReportContractError(ValueError):
    """Raised when the outcome-free report contract is incomplete or altered."""


def _sha256(value: object, name: str, *, allow_zero: bool = False) -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise FormalReportContractError(f"{name} must be an exact lowercase SHA-256")
    if not allow_zero and value == _ZERO_SHA256:
        raise FormalReportContractError(f"{name} is unresolved")
    return value


def _canonical(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("ascii")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise FormalReportContractError("contract is not canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _secondary_hypotheses() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    def add(
        hypothesis_id: str,
        *,
        metric: str,
        horizon: int = 20,
        coefficient: str | None = None,
        cohort: str = "all",
        exclusion: str = "none",
        portfolio_variant: str = "none",
        cost_bps_per_side: int | None = None,
        score_arm: str = "firm_specific",
    ) -> None:
        rows.append(
            {
                "hypothesis_id": hypothesis_id,
                "registry_ordinal": len(rows),
                "metric": metric,
                "score_arm_id": score_arm,
                "direction": "positive",
                "horizon_sessions": horizon,
                "coefficient": coefficient,
                "cohort_id": cohort,
                "earnings_exclusion_id": exclusion,
                "portfolio_variant_id": portfolio_variant,
                "cost_bps_per_side": cost_bps_per_side,
                "p_value": "centered_two_sided_complete_session_block_bootstrap",
                "classification": "SECONDARY_non_rescuing",
            }
        )

    for horizon in (1, 5, 60):
        add(
            f"secondary_fm_bullish_h{horizon}",
            metric="fama_macbeth_beta",
            horizon=horizon,
            coefficient="bullish",
        )
    for horizon in HORIZONS:
        add(
            f"secondary_fm_bearish_h{horizon}",
            metric="fama_macbeth_beta",
            horizon=horizon,
            coefficient="bearish",
        )
    # ``all`` is the required cohort baseline and is emitted, but is identical
    # to the primary H20 population and therefore is not counted a second time
    # in the secondary multiplicity family.
    for cohort in COHORT_IDS[1:]:
        add(
            f"secondary_fm_bullish_h20_cohort_{cohort}",
            metric="fama_macbeth_beta",
            coefficient="bullish",
            cohort=cohort,
        )
    for exclusion in EARNINGS_EXCLUSION_IDS:
        add(
            f"secondary_fm_bullish_h20_{exclusion}",
            metric="fama_macbeth_beta",
            coefficient="bullish",
            exclusion=exclusion,
        )
    for variant in PORTFOLIO_VARIANT_IDS[1:]:
        add(
            f"secondary_economic_{variant}_cost10",
            metric="mean_net_excess_daily_total_return",
            portfolio_variant=variant,
            cost_bps_per_side=10,
        )
    for cost in (0, 5, 20):
        add(
            f"secondary_economic_direct_stock_equal_weight_cost{cost}",
            metric="mean_net_excess_daily_total_return",
            portfolio_variant="direct_stock_equal_weight",
            cost_bps_per_side=cost,
        )
    return rows


def _secondary_registry() -> dict[str, object]:
    hypotheses = _secondary_hypotheses()
    seed = {
        "schema": "arv2-secondary-hypothesis-registry-v1",
        "evaluation_id": EVALUATION_ID,
        "ordered_hypotheses": hypotheses,
        "required_cohort_baseline": {
            "cohort_id": "all",
            "duplicates_primary_population": True,
            "included_in_bh_family": False,
        },
        "required_reporting_bindings": {
            "direction_horizon_cohort_metric_mapping": (
                "each_ordered_hypothesis_record_names_its_exact_direction_"
                "horizon_cohort_exclusion_metric_portfolio_variant_and_cost"
            ),
            "stock_event_returns_by_rating_action": {
                "report_family_id": REPORT_FAMILY_IDS[0],
                "rating_actions": list(RATING_ACTIONS),
                "horizons_sessions": list(HORIZONS),
                "cohort_ids": list(COHORT_IDS),
                "role": "required_descriptive_output_not_an_extra_BH_hypothesis",
            },
            "event_time_cumulative_abnormal_return_by_rating_action": {
                "report_family_id": REPORT_FAMILY_IDS[1],
                "rating_actions": list(RATING_ACTIONS),
                "event_time_sessions": [0, 1, 5, 20, 60],
                "role": "required_descriptive_output_not_an_extra_BH_hypothesis",
            },
            "benjamini_hochberg_q_value": (
                "one_exact_q_value_and_rejection_boolean_for_every_registry_slot"
            ),
            "p_value_tie_and_order_rule": (
                "ascending_exact_p_value_then_registry_ordinal"
            ),
        },
        "benjamini_hochberg": {
            "family_size": len(hypotheses),
            "scope": (
                "one_independent_19_slot_family_per_source_view_for_the_"
                "formal_2020_2025_primary_POOLED_scope_only"
            ),
            "input_p_values": "exact_reduced_nonnegative_Fraction_or_named_missing",
            "missing_or_refused_p_value": "retain_slot_and_use_exact_one_for_adjustment",
            "rank_order": "ascending_exact_p_value_then_registry_ordinal",
            "rank": "one_based_after_deterministic_tie_order",
            "raw_adjustment": "min(1,family_size_times_p_value_divided_by_rank)",
            "monotonicity": "reverse_cumulative_minimum_in_rank_order",
            "output_order": "registry_ordinal",
            "q_value_encoding": "exact_reduced_nonnegative_Fraction",
            "output_fields": [
                "hypothesis_id",
                "registry_ordinal",
                "p_value_status",
                "p_value_numerator",
                "p_value_denominator",
                "rank",
                "raw_adjusted_numerator",
                "raw_adjusted_denominator",
                "q_value_numerator",
                "q_value_denominator",
                "rejected_at_q_lte_0_05",
                "reasons",
            ],
            "maximum_output_rows_per_source_view": len(hypotheses),
            "rejection_threshold": {"numerator": 1, "denominator": 20},
            "role": "reporting_only_never_replaces_or_rescues_any_primary_gate",
        },
    }
    digest = _digest(seed)
    return {
        "registry_id": _SECONDARY_PREFIX + digest[:24],
        "registry_sha256": digest,
        **seed,
    }


def _strategy_trial_registry() -> dict[str, object]:
    trials = [
        {
            "trial_id": f"direct_stock_equal_weight_cost{cost}",
            "registry_ordinal": ordinal,
            "portfolio_variant_id": "direct_stock_equal_weight",
            "cost_bps_per_side": cost,
            "benchmark": "matching_SPY_total_return",
        }
        for ordinal, cost in enumerate(COST_BPS_PER_SIDE)
    ]
    first_variant_ordinal = len(trials)
    trials.extend(
        {
            "trial_id": f"{variant}_cost10",
            "registry_ordinal": first_variant_ordinal + offset,
            "portfolio_variant_id": variant,
            "cost_bps_per_side": 10,
            "benchmark": "matching_SPY_total_return",
        }
        for offset, variant in enumerate(PORTFOLIO_VARIANT_IDS[1:])
    )
    seed = {
        "schema": "arv2-strategy-trial-registry-v1",
        "evaluation_id": EVALUATION_ID,
        "ordered_trials": trials,
        "sample": (
            "formal_2020_2025_primary_complete_common_valid_daily_sessions_"
            "separately_within_each_source_view"
        ),
        "daily_value": "net_portfolio_total_return_minus_matching_SPY_total_return",
        "common_session_rule": (
            "all_six_trials_must_have_the_same_complete_session_axis_or_the_"
            "deflated_sharpe_report_is_named_unavailable_without_shrinking_N"
        ),
        "annualization_sessions": 252,
        "sharpe": {
            "risk_free_rate": "zero_because_input_is_already_SPY_excess_return",
            "mean": "stable_Decimal_sum_divided_by_T",
            "standard_deviation": "sample_standard_deviation_denominator_T_minus_1",
            "daily": "mean_divided_by_standard_deviation",
            "annualized": "daily_sharpe_times_sqrt_Decimal_252",
            "minimum_T": 50,
            "zero_variance": "named_unavailable",
        },
        "deflated_sharpe": {
            "definition": "Bailey_Lopez_de_Prado_probabilistic_Sharpe_deflated_for_fixed_trials",
            "trial_count_N": len(trials),
            "unit": "daily_Sharpe_for_threshold_and_z_annualized_Sharpe_is_report_only",
            "trial_sharpe_variance": "sample_variance_of_the_six_daily_trial_Sharpes",
            "expected_maximum_multiplier": "1.300140787845584",
            "expected_maximum_sharpe": (
                "sqrt(trial_sharpe_variance)*Decimal_1.300140787845584"
            ),
            "moment_convention": (
                "m_k=stable_sum((x-mean)^k)/T_skewness=m3/m2^(3/2)_"
                "kurtosis=m4/m2^2_not_excess"
            ),
            "z": (
                "(daily_sharpe-expected_maximum_sharpe)*sqrt(T-1)/"
                "sqrt(1-skewness*daily_sharpe+((kurtosis-1)/4)*"
                "daily_sharpe^2)"
            ),
            "normal_cdf": {
                "decimal_precision": 80,
                "rounding": "ROUND_HALF_EVEN",
                "pi": (
                    "3.14159265358979323846264338327950288419716939937510"
                    "58209749445923078164"
                ),
                "algorithm": (
                    "Phi(z)=one_half*(one+erf(z/sqrt(2))); erf uses the signed_"
                    "power_series_2_over_sqrt_pi_times_sum_n_ge_0_of_"
                    "minus_one_pow_n_x_pow_2n_plus_1_over_n_factorial_times_"
                    "2n_plus_1"
                ),
                "termination": (
                    "for_abs_z_below_8_stop_after_the_first_term_with_abs_less_"
                    "than_1e-70_or_refuse_after_10000_terms; z_lte_minus8_is_0;_"
                    "z_gte_8_is_1; final_result_rounded_to_50_significant_digits"
                ),
            },
            "input_fields": [
                "source_view_id",
                "trial_id",
                "registry_ordinal",
                "formal_complete_common_session_ids",
                "daily_net_portfolio_total_return",
                "daily_matching_SPY_total_return",
                "daily_net_excess_total_return",
            ],
            "output_fields": [
                "source_view_id",
                "trial_id",
                "T",
                "daily_sharpe",
                "annualized_sharpe",
                "skewness",
                "kurtosis",
                "trial_sharpe_variance",
                "expected_maximum_sharpe",
                "deflated_sharpe_z",
                "deflated_sharpe_probability",
                "status",
                "reasons",
            ],
            "maximum_output_rows_per_source_view": len(trials),
            "winner_selection": "none_report_all_six_registry_trials",
            "role": "reporting_only_never_replaces_or_rescues_any_primary_gate",
        },
    }
    digest = _digest(seed)
    return {
        "registry_id": _TRIAL_PREFIX + digest[:24],
        "registry_sha256": digest,
        **seed,
    }


def _cell_schema(
    family_id: str,
    *,
    keys: tuple[str, ...],
    values: tuple[str, ...],
    maximum_rows: int,
    rule: str,
) -> dict[str, object]:
    return {
        "family_id": family_id,
        "ordered_key_fields": list(keys),
        "ordered_value_fields": list(values),
        "maximum_rows_per_source_view": maximum_rows,
        "canonical_order": "lexicographic_by_declared_dimension_order_then_exact_key",
        "missing_rule": "retain_expected_cell_with_named_status_and_reason_never_zero_fill",
        "execution_rule": rule,
        "raw_security_event_or_market_rows_permitted": False,
    }


def _report_schemas() -> list[dict[str, object]]:
    common = ("source_view_id", "slice_id", "fold_id")
    return [
        _cell_schema(
            REPORT_FAMILY_IDS[0],
            keys=common + ("rating_action", "horizon_sessions", "cohort_id"),
            values=(
                "status", "accepted_event_count", "refused_event_count",
                "connected_component_count", "mean_gross_security_total_return",
                "mean_SPY_total_return", "mean_gross_excess_total_return",
                "median_gross_excess_total_return", "hac_lag_sessions",
                "hac_pair_counts", "hac_standard_error", "hac_t", "reasons",
            ),
            maximum_rows=4096,
            rule=(
                "each_admitted_directional_event_is_counted_once_per_horizon;_"
                "cohort_all_plus_one_exact_mutually_exclusive_timing_cohort;_"
                "equal_component_weight_then_equal_event_weight_within_component"
            ),
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[1],
            keys=common + ("rating_action", "event_time_session"),
            values=(
                "status", "accepted_event_count", "refused_event_count",
                "mean_security_total_return", "mean_SPY_total_return",
                "mean_cumulative_abnormal_return", "reasons",
            ),
            maximum_rows=1024,
            rule=(
                "event_time_sessions_are_exactly_0_1_5_20_60;_at_0_all_returns_"
                "are_exact_zero;_later_cells_use_matching_open_to_open_total_"
                "returns_and_CAR_is_their_security_minus_SPY_difference_not_a_"
                "sum_of_overlapping_horizon_returns"
            ),
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[2],
            keys=common + ("horizon_sessions", "score_arm"),
            values=(
                "status", "valid_date_count", "invalid_date_count",
                "invalid_dates_by_reason", "mean", "median",
                "positive_date_share", "icir", "hac_lag_sessions",
                "hac_pair_counts", "hac_standard_error", "hac_t", "reasons",
            ),
            maximum_rows=128,
            rule="fold_rows_are_year_rows_and_pooled_rows_equal_weight_valid_dates",
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[3],
            keys=common + ("horizon_sessions", "coefficient"),
            values=(
                "status", "valid_date_count", "invalid_date_count",
                "invalid_dates_by_reason", "parameter_count_by_date",
                "mean_beta", "median_beta", "hac_lag_sessions",
                "hac_pair_counts", "hac_standard_error", "hac_t",
                "bootstrap_resamples", "centered_two_sided_p_value", "reasons",
            ),
            maximum_rows=128,
            rule=(
                "firm_specific_score_arm_only;_coefficients_are_exactly_bullish_"
                "and_bearish_with_equal_valid_date_weight"
            ),
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[4],
            keys=common + ("record_kind", "record_id"),
            values=(
                "status", "numerator", "denominator", "passes_19_of_20",
                "valid_date_count", "mean_firm_ic", "mean_global_ic",
                "observed_difference", "one_sided_q95", "one_sided_lcb95",
                "diagnostic_counts", "reasons",
            ),
            maximum_rows=512,
            rule=(
                "five_preoutcome_ledgers_are_separate_exact_integer_gates_per_"
                "fold_and_pooled;_paired_IC_uses_the_separately_reviewed_"
                "matched_comparison_sampler"
            ),
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[5],
            keys=common + ("trial_id",),
            values=(
                "status", "portfolio_variant_id", "cost_bps_per_side",
                "session_count", "valid_return_session_count",
                "refused_return_session_count", "invested_session_count",
                "cash_sleeve_count", "selected_sleeve_count",
                "mean_gross_portfolio_total_return", "mean_SPY_total_return",
                "mean_net_portfolio_total_return", "mean_net_excess_daily_total_return",
                "cumulative_net_portfolio_total_return",
                "cumulative_SPY_total_return", "geometric_relative_total_return",
                "mean_daily_turnover", "terminal_liquidation_turnover",
                "sleeve_security_incidence_count", "duplicate_sleeve_security_incidence_count",
                "sleeve_overlap_share", "hac_lag_sessions", "hac_pair_counts",
                "bootstrap_resamples", "centered_two_sided_p_value", "reasons",
            ),
            maximum_rows=128,
            rule=(
                "emit_only_the_six_exact_strategy_trial_registry_combinations;_"
                "economic_parent_owns_selection_and_liquidation;_variants_change_"
                "only_within_selected_sleeve_weights;_inverse_vol_requires_all_"
                "positive_finite_preopen_60d_volatilities;_score_weight_uses_"
                "positive_scores;_a_missing_weight_input_leaves_that_sleeve_in_cash"
            ),
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[6],
            keys=common + ("accounting_kind", "reason_or_component"),
            values=(
                "status", "expected_count", "accepted_count", "refused_count",
                "terminal_count", "connected_component_count",
                "component_member_incidence_count", "power_floor",
                "reconciles_exactly", "reasons",
            ),
            maximum_rows=2048,
            rule=(
                "emit_the_exact_frozen_F6_accounting_axis;_all_expected_"
                "preoutcome_outcome_economic_lifecycle_coverage_report_and_power_"
                "slots_end_in_exactly_one_accepted_or_named_refused_terminal;_"
                "expected_equals_terminal_equals_accepted_plus_refused;_any_key_"
                "or_count_mismatch_refuses_the_complete_report;_a_complete_"
                "accounting_row_is_AVAILABLE_even_when_refused_count_is_nonzero_"
                "or_a_power_floor_is_not_met"
            ),
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[7],
            keys=common + ("horizon_sessions", "score_arm", "percentile_decile"),
            values=(
                "status", "row_count", "mean_score", "mean_future_gross_excess_return",
                "median_future_gross_excess_return", "reasons",
            ),
            maximum_rows=2048,
            rule=(
                "within_each_date_sort_exact_score_then_security_id_compute_"
                "one_based_average_rank_for_each_exact_score_tie_group_then_bin_"
                "equals_1_plus_floor(10_times_(average_rank_minus_1)_divided_by_n);_"
                "ties_share_one_bin_empty_bins_are_retained_as_named_missing_cells"
            ),
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[8],
            keys=common + ("window_end_session", "series_id"),
            values=(
                "status", "axis_session_count", "valid_observation_count",
                "rolling_mean", "rolling_sample_standard_deviation",
                "annualized_sharpe_or_icir", "reasons",
            ),
            maximum_rows=12000,
            rule=(
                "POOLED_fold_scope_only_for_each_declared_rolling_series;_trailing_"
                "60_complete_XNYS_sessions_including_window_end_with_at_"
                "least_50_valid_observations;_missing_positions_remain_in_axis;_"
                "portfolio_Sharpe_uses_sample_standard_deviation_and_sqrt_Decimal_"
                "252;_ICIR_uses_sample_standard_deviation_and_sqrt_Decimal_252;_"
                "a_zero_standard_deviation_is_named_unavailable"
            ),
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[9],
            keys=("source_view_id", "slice_id", "fold_id", "calendar_year"),
            values=(
                "status", "valid_session_count", "mean_net_excess_daily_total_return",
                "annualized_arithmetic_net_excess_return", "hac_lag_sessions",
                "hac_pair_counts", "hac_standard_error", "hac_t", "reasons",
            ),
            maximum_rows=64,
            rule=(
                "primary_direct_stock_equal_weight_10bps_trial_only;_alpha_plot_"
                "label_means_252_times_mean_daily_net_excess_and_is_"
                "not_a_factor_regression_intercept"
            ),
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[10],
            keys=common + ("rating_action", "score_arm", "horizon_sessions"),
            values=(
                "status", "valid_date_count", "mean_ic", "mean_gross_excess_return",
                "ratio_to_h1_effect", "reasons",
            ),
            maximum_rows=512,
            rule="fixed_horizon_order_1_5_20_60_with_no_interpolation_or_posthoc_half_life_fit",
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[11],
            keys=common + ("trial_id", "turnover_decile"),
            values=(
                "status", "portfolio_variant_id", "cost_bps_per_side",
                "session_count", "mean_turnover", "mean_net_total_return",
                "mean_net_excess_total_return", "reasons",
            ),
            maximum_rows=128,
            rule=(
                "POOLED_fold_scope_only_for_each_of_the_six_exact_strategy_trials;_"
                "within_each_source_view_slice_sort_exact_session_turnover_then_"
                "session_compute_one_based_average_rank_for_each_exact_tie_group_then_"
                "bin_equals_1_plus_floor(10_times_(average_rank_minus_1)_divided_by_n);_"
                "ties_share_one_bin_empty_bins_and_missing_sessions_are_named_not_zero"
            ),
        ),
        _cell_schema(
            REPORT_FAMILY_IDS[12],
            keys=("source_view_id", "slice_id", "fold_id", "session"),
            values=(
                "status", "net_portfolio_wealth", "SPY_wealth", "drawdown",
                "underwater_session_count", "maximum_drawdown_to_date",
                "maximum_underwater_sessions_to_date", "reasons",
            ),
            maximum_rows=4096,
            rule=(
                "primary_equal_weight_10bps_only;_each_fold_starts_wealth_at_one;_"
                "wealth_compounds_net_portfolio_returns_not_excess_differences;_"
                "drawdown=wealth_over_running_peak_minus_one;_underwater_count_"
                "increments_below_peak_and_resets_at_peak"
            ),
        ),
    ]


def _report_family_object_capacities(
    schemas: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            "family_id": item["family_id"],
            "maximum_row_count_per_source_view": item[
                "maximum_rows_per_source_view"
            ],
            "maximum_encoded_bytes_per_row": (
                MAXIMUM_ENCODED_BYTES_PER_REPORT_ROW
            ),
            "uncompressed_byte_ceiling": (
                REPORT_FAMILY_OBJECT_UNCOMPRESSED_BYTE_CEILING
            ),
            "compressed_byte_ceiling": (
                REPORT_FAMILY_OBJECT_COMPRESSED_BYTE_CEILING
            ),
        }
        for item in schemas
    ]


def _coverage_contract() -> dict[str, object]:
    definitions = {
        "endpoint_pair_mapping": (
            "denominator_each_firm_admitted_directional_C2_event_once_per_fold_"
            "when_its_lineage_is_present_in_at_least_one_firm_baseline_ACTIVE_"
            "test_row;_numerator_same_event_only_if_both_global_endpoints_map_and_"
            "delta_is_expected_sign_or_exact_zero;_opposite_sign_measured_refusal_"
            "unknown_and_invalid_pairs_are_denominator_only"
        ),
        "active_security_date_rows": (
            "numerator_exact_paired_retained_fold_test_session_security_key_over_"
            "denominator_firm_baseline_eligible_ACTIVE_key_after_shared_nonoutcome_"
            "eligibility_and_before_comparator_exclusion"
        ),
        "common_event_components": (
            "numerator_exact_topology_identical_retained_paired_fold_test_session_"
            "component_instance_over_denominator_firm_baseline_component_instance;_"
            "partial_or_fragmented_components_are_not_retained"
        ),
        "component_member_incidence": (
            "numerator_exact_retained_fold_test_session_component_security_"
            "incidence_over_denominator_firm_baseline_incidence"
        ),
        "score_capable_dates": (
            "numerator_preoutcome_candidate_date_with_valid_both_arm_scores_and_"
            "not_both_constant_over_denominator_test_date_with_exact_arm_key_"
            "parity_at_least_20_rows_and_all_required_nonoutcome_inputs;_score_"
            "dispersion_does_not_remove_the_denominator"
        ),
    }
    return {
        "ordered_ledger_ids": list(COMPARATOR_LEDGER_IDS),
        "definitions": definitions,
        "source_view_scope": "each_source_view_is_gated_separately",
        "fold_scope": "each_exact_H20_test_fold_then_pooled_as_integer_sum_of_fold_rows",
        "event_fold_attribution": (
            "one_C2_hash_occurrence_per_source_view_fold_when_its_lineage_is_"
            "present_in_any_firm_baseline_ACTIVE_H20_test_row_after_exact_firm_"
            "only_institution_security_session_daily_dedupe_and_before_global_"
            "map_exclusions;_pooled_counts_are_exact_integer_sums_of_the_six_"
            "fold_occurrences"
        ),
        "threshold": {"numerator": 19, "denominator": 20},
        "comparison": "numerator_times_20_greater_than_or_equal_denominator_times_19",
        "zero_denominator": "INVALID_DATA_not_ready",
        "gate": "all_five_ledgers_each_fold_and_pooled_must_pass_none_can_rescue_another",
        "outcome_inputs_permitted": False,
        "diagnostic_censuses": [
            "mapped_measured_refusal_unknown_invalid_endpoint_event_instances",
            "mapped_measured_refusal_unknown_invalid_endpoint_pair_instances",
            "expected_sign_opposite_sign_zero_delta_event_instances",
            "firm_totalized_zero_candidate_dates",
            "global_totalized_zero_candidate_dates",
            "both_arms_constant_candidate_dates",
            "score_refused_candidate_dates",
            "exact_hashed_raw_and_canonical_label_disposition_counts",
            "raw_form_collision_key_and_endpoint_instance_counts_with_denominators",
            "zero_available_paired_bootstrap_replicates",
        ],
    }


def _semantic_template() -> dict[str, object]:
    secondary = _secondary_registry()
    trials = _strategy_trial_registry()
    report_schemas = _report_schemas()
    family_capacities = _report_family_object_capacities(report_schemas)
    seed_record = {
        "domain": "arv2-stock-formal-bootstrap-seed-v1",
        "qc_first_plan_sha256": QC_FIRST_PLAN_SHA256,
        "fold_manifest_sha256": FOLD_MANIFEST_SHA256,
        "evaluation_id": EVALUATION_ID,
        "economic_execution_definition_sha256": _ZERO_SHA256,
        "secondary_hypothesis_registry_sha256": secondary["registry_sha256"],
        "deflated_sharpe_trial_registry_sha256": trials["registry_sha256"],
        "sampler_version": "v1",
    }
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "evaluation_id": EVALUATION_ID,
        "contains_results": False,
        "result_sha256": None,
        "current_execution_authorized": False,
        "parents": {
            "qc_first_plan_sha256": QC_FIRST_PLAN_SHA256,
            "fold_manifest_sha256": FOLD_MANIFEST_SHA256,
            "stock_successor_sha256": STOCK_SUCCESSOR_SHA256,
            "matched_comparison_sha256": MATCHED_COMPARISON_SHA256,
            "economic_execution_definition_sha256": _ZERO_SHA256,
        },
        "dimensions": {
            "source_view_ids": list(SOURCE_VIEW_IDS),
            "primary_source_view_id": SOURCE_VIEW_IDS[0],
            "sensitivity_source_view_id": SOURCE_VIEW_IDS[1],
            "sensitivity_source_view_can_replace_or_rescue_primary": False,
            "slices": [
                {
                    "slice_id": SLICE_IDS[0],
                    "fold_ids": list(FORMAL_FOLD_IDS),
                    "report_fold_scope_ids": list(FORMAL_FOLD_IDS) + ["POOLED"],
                    "classification": "PRIMARY_development",
                    "may_be_rescued_by_other_slice": False,
                },
                {
                    "slice_id": SLICE_IDS[1],
                    "fold_ids": list(DESCRIPTIVE_FOLD_IDS),
                    "report_fold_scope_ids": list(DESCRIPTIVE_FOLD_IDS) + ["POOLED"],
                    "classification": "DESCRIPTIVE_sensitivity",
                    "may_replace_or_rescue_primary": False,
                },
            ],
            "horizons_sessions": list(HORIZONS),
            "primary_horizon_sessions": 20,
            "minimum_valid_test_dates": 50,
            "hac_lag_sessions_by_horizon": {"1": 1, "5": 5, "20": 20, "60": 60},
            "hac_session_axis": (
                "actual_XNYS_session_distance_never_compress_missing_or_refused_dates"
            ),
            "hac_kernel": "Bartlett",
            "hac_pair_normalization": (
                "divide_each_lag_cross_product_sum_by_total_valid_observation_count_"
                "and_report_the_observed_pair_count_at_every_lag"
            ),
            "rating_actions": list(RATING_ACTIONS),
            "score_arm_ids": ["firm_specific", "global_map"],
            "fama_macbeth_coefficient_ids": ["bullish", "bearish"],
            "report_fold_scope_token": "POOLED",
            "earnings_cohort_anchor": (
                "among_point_in_time_known_earnings_sessions_choose_minimum_absolute_"
                "XNYS_session_distance_from_the_rating_event;_an_exact_absolute_"
                "distance_tie_chooses_the_earlier_earnings_session;_signed_distance_"
                "is_rating_event_session_minus_selected_earnings_session"
            ),
            "cohorts": [
                {"cohort_id": "all", "distance_rule": "all_admitted_directional_events"},
                {
                    "cohort_id": "exact_earnings_day",
                    "distance_rule": "selected_anchor_signed_distance_equal_0",
                },
                {
                    "cohort_id": "one_to_two_days_after_earnings",
                    "distance_rule": "selected_anchor_signed_distance_in_1_2",
                },
                {
                    "cohort_id": "three_to_five_days_after_earnings",
                    "distance_rule": "selected_anchor_signed_distance_in_3_4_5",
                },
                {
                    "cohort_id": "over_five_days_after_earnings",
                    "distance_rule": "selected_anchor_signed_distance_at_least_6",
                },
                {
                    "cohort_id": "pre_earnings",
                    "distance_rule": "selected_anchor_signed_distance_less_than_0",
                },
            ],
            "cohort_assignment": (
                "all_plus_exactly_one_nonall_cohort;_no_point_in_time_earnings_"
                "anchor_is_named_cohort_unavailable;_guidance_proximity_remains_"
                "a_control_not_a_seventh_cohort"
            ),
            "earnings_exclusions": [
                {
                    "exclusion_id": "earnings_exclusion_pm2",
                    "inclusive_session_distances": [-2, -1, 0, 1, 2],
                },
                {
                    "exclusion_id": "earnings_exclusion_pm5",
                    "inclusive_session_distances": list(range(-5, 6)),
                },
            ],
            "earnings_exclusion_scope": (
                "bullish_H20_Fama_MacBeth_rows_with_point_in_time_known_earnings_"
                "anchor;_unknown_anchor_is_named_refusal_not_automatic_inclusion"
            ),
            "portfolio_variant_ids": list(PORTFOLIO_VARIANT_IDS),
            "portfolio_leverage": False,
            "portfolio_variant_definitions": {
                "direct_stock_equal_weight": (
                    "same_economic_parent_selected_names_each_receives_exact_equal_"
                    "weight_within_its_one_twentieth_sleeve"
                ),
                "direct_stock_inverse_volatility": (
                    "same_selected_names_weight_proportional_to_one_divided_by_the_"
                    "strictly_preopen_finite_positive_60_session_realized_volatility_"
                    "then_exactly_normalized;_any_missing_nonpositive_or_nonfinite_"
                    "member_input_leaves_the_entire_new_sleeve_in_cash"
                ),
                "direct_stock_score_weight": (
                    "same_selected_names_weight_proportional_to_strictly_positive_"
                    "final_stock_control_adjusted_score_then_exactly_normalized;_any_"
                    "missing_nonpositive_or_nonfinite_member_input_leaves_the_entire_"
                    "new_sleeve_in_cash"
                ),
            },
            "cost_bps_per_side": list(COST_BPS_PER_SIDE),
            "event_time_sessions": [0, 1, 5, 20, 60],
            "percentile_bins": list(range(1, 11)),
            "rolling_window_sessions": 60,
            "rolling_minimum_valid_observations": 50,
            "rolling_series_ids": [
                "firm_specific_H20_daily_IC",
                "global_map_H20_daily_IC",
                "direct_stock_equal_weight_cost10_daily_net_excess_return",
            ],
            "rolling_plot_fold_scope": "POOLED_only",
            "annualization_sessions": 252,
            "f6_accounting_axis": [
                {
                    **item,
                    "reason_or_component_ids": (
                        list(item["reason_or_component_ids"])
                        if type(item["reason_or_component_ids"]) is tuple
                        else item["reason_or_component_ids"]
                    ),
                }
                for item in F6_ACCOUNTING_AXIS
            ],
            "f6_accounting_equality": (
                "expected_count_equals_terminal_count_equals_accepted_count_plus_"
                "refused_count_for_every_exact_F6_key"
            ),
            "f6_self_accounting": (
                "freeze_the_complete_expected_F6_key_tuple_including_the_F6_family_"
                "terminal_row_before_constructing_any_F6_row_never_derive_expected_"
                "count_from_the_post_emission_row_list"
            ),
        },
        "classification": {
            "PRIMARY": list(PRIMARY_OUTPUT_IDS),
            "SECONDARY": [
                "bullish_1_5_60_session_fama_macbeth",
                "bearish_1_5_20_60_session_fama_macbeth",
                "six_earnings_guidance_timing_cohorts",
                "earnings_exclusion_plus_minus_2_and_5_sessions",
                "direct_stock_inverse_volatility_and_score_weight_variants",
                "cost_0_5_20_bps_per_side",
            ],
            "EXPLORATORY": ["all_unregistered_subgroups_or_parameter_variants"],
            "secondary_can_replace_or_rescue_primary": False,
            "exploratory_can_replace_or_rescue_primary": False,
        },
        "primary_gate_composition": {
            "scope": (
                "formal_2020_2025_primary_POOLED_for_current_row_current_vintage_"
                "non_pristine_pit_only"
            ),
            "sensitivity_scope": (
                "conservative_censored_current_vintage_non_pristine_pit_repeats_"
                "the_same_named_gate_calculations_for_reporting_only_and_cannot_"
                "replace_or_rescue_the_primary_source_view"
            ),
            "bullish_H20_Fama_MacBeth": (
                "at_least_50_valid_test_dates_and_mean_beta_strictly_positive_and_"
                "centered_two_sided_complete_session_block_p_strictly_below_0_05"
            ),
            "equal_weight_10bps_economic": (
                "complete_valid_fold_paths_and_mean_net_excess_daily_return_strictly_"
                "positive_and_centered_two_sided_complete_session_block_p_strictly_"
                "below_0_05"
            ),
            "firm_specific_vs_global_H20_IC": (
                "all_five_19_of_20_coverage_ledgers_pass_each_fold_and_pooled_and_"
                "observed_paired_difference_nonnegative_and_one_sided_95pct_lower_"
                "confidence_bound_nonnegative"
            ),
            "power_floor": "authenticated_nuisance_only_floor_must_pass_without_outcomes",
            "combination": "all_primary_and_power_gates_conjunctive_no_rescue",
            "output_fields": [
                "gate_id", "status", "observed_metric", "threshold", "reasons"
            ],
        },
        "required_report_family_ids": list(REPORT_FAMILY_IDS),
        "report_schemas": report_schemas,
        "global_comparator_coverage": _coverage_contract(),
        "secondary_hypothesis_registry": secondary,
        "strategy_trial_registry": trials,
        "bootstrap": {
            "stock_FM_and_economic_seed_record": seed_record,
            "stock_FM_and_economic_seed_sha256": _digest(seed_record),
            "operative_seed_precedence": (
                "this_authenticated_child_seed_and_draw_contract_is_the_sole_"
                "operative_formal_FM_and_economic_sampler;_the_economic_parent_"
                "base_seed_digest_is_ancestry_only_and_must_not_draw"
            ),
            "seed_record_encoding": "canonical_sorted_compact_ASCII_JSON_plus_one_LF",
            "draw_domain": "arv2-stock-formal-noncircular-mbb-hash-counter-v1",
            "metric_ids": (
                ["primary_fm_bullish_h20", "primary_economic_equal_weight_cost10"]
                + [item["hypothesis_id"] for item in secondary["ordered_hypotheses"]]
            ),
            "metric_encoding": "uint16BE_ASCII_byte_length_then_exact_ASCII_bytes",
            "source_view_encoding": "uint16BE_ASCII_byte_length_then_exact_ASCII_bytes",
            "slice_encoding": "uint16BE_ASCII_byte_length_then_exact_ASCII_bytes",
            "draw_preimage": (
                "draw_domain_ASCII||00||seed_digest_raw32||source_view_length_uint16BE||"
                "source_view_ASCII||slice_length_uint16BE||slice_ASCII||metric_length_"
                "uint16BE||metric_ASCII||resample_uint64BE||global_fold_ordinal_uint64BE||"
                "block_uint64BE||rejection_uint64BE"
            ),
            "fold_ordinal": (
                "zero_based_position_0_through_5_in_the_six_FORMAL_fold_ids_even_"
                "for_the_2021_2025_descriptive_subset_never_subset_renumbered;_"
                "pooled_formal_ordinal_6;_pooled_descriptive_ordinal_7"
            ),
            "uniform_conversion": (
                "interpret_SHA256_as_unsigned_big_endian_u;_for_m_possible_starts_"
                "reject_u_at_or_above_2^256_minus_(2^256_mod_m)_then_take_u_mod_m;_"
                "increment_only_rejection_uint64BE_and_refuse_on_counter_overflow"
            ),
            "block_start_domain": (
                "0_through_complete_axis_length_minus_block_length_inclusive"
            ),
            "block_length": "equal_to_horizon_for_FM_and_20_for_economic",
            "noncircular_complete_axis": True,
            "fold_boundaries_crossed": False,
            "eligible_block_start": (
                "within_one_fold_and_every_consecutive_expected_XNYS_session_in_"
                "the_metric_specific_block_has_a_valid_centered_observation"
            ),
            "blocks_drawn_per_fold": (
                "ceiling(original_valid_observation_count_in_fold_divided_by_"
                "metric_specific_block_length)"
            ),
            "replicate_fold_length": (
                "concatenate_drawn_blocks_in_draw_order_then_truncate_to_the_"
                "original_valid_observation_count_for_that_fold"
            ),
            "pooled_replicate_statistic": (
                "absolute_equal_observation_mean_after_concatenating_each_exact_"
                "fold_replicate_in_FORMAL_fold_order"
            ),
            "resamples": 19999,
            "resample_ordinal": "zero_based_0_through_19998",
            "null_centering": (
                "subtract_observed_equal_date_mean_from_each_valid_FM_coefficient;_"
                "subtract_observed_equal_session_mean_from_each_valid_economic_return"
            ),
            "test_statistic": "absolute_equal_observation_mean",
            "two_sided_p_value": (
                "(1_plus_count_resampled_absolute_statistic_gte_observed_absolute_"
                "statistic)_divided_by_20000_as_reduced_Fraction"
            ),
            "empty_replicate": "INCONCLUSIVE_locked_no_redraw",
            "paired_IC_sampler": (
                "unchanged_separately_reviewed_arv2_paired_ic_noncircular_mbb_"
                "hash_counter_v1_not_this_stock_seed"
            ),
        },
        "numeric_and_output_rules": {
            "binary_float_or_nonfinite": "forbidden",
            "decimal_precision": 50,
            "decimal_rounding": "ROUND_HALF_EVEN",
            "stable_sum": "sort_by_exact_absolute_value_then_signed_value",
            "fraction_encoding": "reduced_integer_numerator_and_positive_denominator",
            "decimal_encoding": "finite_plain_decimal_string_no_exponent",
            "decimal_maximum_significant_digits": 80,
            "status_encoding": [
                "AVAILABLE", "UNAVAILABLE", "REFUSED", "INCONCLUSIVE", "INVALID_DATA"
            ],
            "gate_status_encoding": ["PASS", "FAIL", "INCONCLUSIVE", "INVALID_DATA"],
            "count_encoding": "exact_nonnegative_JSON_integer_not_boolean",
            "boolean_encoding": "exact_JSON_boolean",
            "reason_id_encoding": (
                "sorted_unique_ASCII_lower_snake_case_1_to_96_bytes_maximum_32_per_cell"
            ),
            "count_map_encoding": (
                "sorted_unique_reason_id_and_nonnegative_integer_pairs_maximum_64"
            ),
            "hac_pair_count_encoding": (
                "ordered_lag_0_through_declared_horizon_nonnegative_integer_pairs"
            ),
            "unknown_field_or_cell": "refuse_complete_report",
            "duplicate_key_or_cell": "refuse_complete_report",
            "report_container_encoding": (
                "each_family_is_one_object_with_the_exact_family_id_exact_ordered_"
                "key_and_value_field_arrays_and_rows_as_JSON_arrays_aligned_to_the_"
                "concatenated_declared_fields_never_repeated_per_row_object_keys"
            ),
            "maximum_encoded_bytes_per_cell": 8192,
            "maximum_encoded_bytes_per_report_row": (
                MAXIMUM_ENCODED_BYTES_PER_REPORT_ROW
            ),
            "summary_root_compressed_byte_ceiling": (
                SUMMARY_ROOT_COMPRESSED_BYTE_CEILING
            ),
            "summary_root_decompressed_byte_ceiling": (
                SUMMARY_ROOT_DECOMPRESSED_BYTE_CEILING
            ),
            "aggregate_compressed_byte_ceiling": (
                SUMMARY_ROOT_COMPRESSED_BYTE_CEILING
            ),
            "aggregate_decompressed_byte_ceiling": (
                SUMMARY_ROOT_DECOMPRESSED_BYTE_CEILING
            ),
            "report_family_object_count": 2 * len(REPORT_FAMILY_IDS),
            "report_family_object_capacities": family_capacities,
            "report_family_object_total_uncompressed_byte_ceiling": (
                2 * len(REPORT_FAMILY_IDS)
                * REPORT_FAMILY_OBJECT_UNCOMPRESSED_BYTE_CEILING
            ),
            "report_family_object_total_compressed_byte_ceiling": (
                2 * len(REPORT_FAMILY_IDS)
                * REPORT_FAMILY_OBJECT_COMPRESSED_BYTE_CEILING
            ),
            "report_family_operational_capacity_precedence": (
                "the_fixed_per_family_and_total_object_byte_ceilings_are_the_"
                "authoritative_first_formal_run_admission_caps_and_supersede_"
                "the_larger_combinatorial_row_envelope;_an_oversize_family_"
                "refuses_the_run_before_any_root_manifest_is_published"
            ),
            "report_family_object_transport": (
                "twenty_six_canonical_gzip_objects_under_actual_project_id_"
                "and_hash_derived_suffix;_write_once_accept_only_exact_existing_"
                "bytes;_save_then_reopen_and_rehash_every_object;_summary_carries_"
                "only_the_canonical_root_manifest_and_object_inventory"
            ),
            "raw_security_event_market_order_trade_or_log_rows_exported": False,
            "reports_for_source_views_are_separate": True,
            "descriptive_slice_cannot_replace_or_rescue_formal": True,
        },
        "capabilities": {
            "filesystem": False,
            "network": False,
            "credentials": False,
            "provider": False,
            "input_read": False,
            "outcome_access": False,
            "quantconnect": False,
            "upload": False,
            "compile": False,
            "launch": False,
            "result_read": False,
            "result_disposition": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


# Seal the complete policy template as immutable bytes.  Runtime construction
# replaces only the two explicit economic-parent placeholders and the seed hash
# derived from them; changing a public convenience constant cannot silently
# rewrite the contract.
_STATIC_TEMPLATE_BYTES = _canonical(_semantic_template())
_STATIC_TEMPLATE_SHA256 = hashlib.sha256(_STATIC_TEMPLATE_BYTES).hexdigest()


def _reject_float(value: str) -> None:
    raise FormalReportContractError(f"binary floating-point is forbidden: {value}")


def _reject_constant(value: str) -> None:
    raise FormalReportContractError(f"non-finite JSON token is forbidden: {value}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FormalReportContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse(payload: bytes, name: str) -> dict[str, object]:
    if type(payload) is not bytes or not payload or payload.startswith(b"\xef\xbb\xbf"):
        raise FormalReportContractError(f"{name} must be exact non-BOM bytes")
    if len(payload) > MAX_CONTRACT_BYTES:
        raise FormalReportContractError(f"{name} exceeds the byte ceiling")
    if b"\r" in payload or b"\x00" in payload:
        raise FormalReportContractError(f"{name} has forbidden framing bytes")
    try:
        decoded = payload.decode("ascii")
        value = json.loads(
            decoded,
            object_pairs_hook=_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FormalReportContractError(f"{name} is not strict ASCII JSON") from exc
    if type(value) is not dict or _canonical(value) != payload:
        raise FormalReportContractError(f"{name} is not canonical")
    return value


def _semantic(
    economic_sha256: str,
    _sealed_template: bytes = _STATIC_TEMPLATE_BYTES,
    _sealed_template_sha256: str = _STATIC_TEMPLATE_SHA256,
) -> dict[str, object]:
    economic = _sha256(
        economic_sha256, "economic execution definition SHA-256"
    )
    if hashlib.sha256(_sealed_template).hexdigest() != _sealed_template_sha256:
        raise FormalReportContractError("sealed report template changed")
    value = _parse(_sealed_template, "sealed report template")
    parents = value["parents"]
    bootstrap = value["bootstrap"]
    if type(parents) is not dict or type(bootstrap) is not dict:
        raise FormalReportContractError("sealed report template changed")
    seed = bootstrap["stock_FM_and_economic_seed_record"]
    if type(seed) is not dict:
        raise FormalReportContractError("sealed bootstrap seed changed")
    if (
        parents.get("economic_execution_definition_sha256") != _ZERO_SHA256
        or seed.get("economic_execution_definition_sha256") != _ZERO_SHA256
    ):
        raise FormalReportContractError("economic parent placeholder changed")
    parents["economic_execution_definition_sha256"] = economic
    seed["economic_execution_definition_sha256"] = economic
    bootstrap["stock_FM_and_economic_seed_sha256"] = _digest(seed)
    return value


def _document(
    economic_sha256: str,
    _contract_prefix: str = _CONTRACT_PREFIX,
) -> tuple[dict[str, object], bytes, str, str]:
    semantic = _semantic(economic_sha256)
    digest = _digest(semantic)
    document = {
        "contract_id": _contract_prefix + digest[:24],
        "contract_sha256": digest,
        **semantic,
    }
    payload = _canonical(document)
    return document, payload, digest, hashlib.sha256(payload).hexdigest()


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class FormalReportContract:
    """Builder-authenticated identity for one exact economic-parent binding."""

    contract_id: str
    contract_sha256: str
    artifact_sha256: str
    schema: str
    status: str
    authority: str
    evaluation_id: str
    economic_execution_definition_sha256: str
    secondary_hypothesis_registry_sha256: str
    deflated_sharpe_trial_registry_sha256: str
    stock_bootstrap_seed_sha256: str
    report_family_count: int
    secondary_hypothesis_count: int
    strategy_trial_count: int
    _canonical_document: bytes = dataclasses.field(repr=False)

    @property
    def input_read_available(self) -> bool:
        return False

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def quantconnect_available(self) -> bool:
        return False

    @property
    def result_read_available(self) -> bool:
        return False

    @property
    def result_disposition_available(self) -> bool:
        return False

    @property
    def deployment_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False

    @property
    def trading_available(self) -> bool:
        return False


_CONTRACTS: dict[
    int,
    tuple[
        weakref.ReferenceType[FormalReportContract],
        bytes,
        tuple[object, ...],
    ],
] = {}
_CONTRACTS_LOCK = threading.RLock()


def _fingerprint(value: FormalReportContract) -> tuple[object, ...]:
    return tuple(
        getattr(value, field.name)
        for field in dataclasses.fields(FormalReportContract)
        if field.name != "_canonical_document"
    ) + (value._canonical_document,)


def _forget(
    identity: int, reference: weakref.ReferenceType[FormalReportContract]
) -> None:
    with _CONTRACTS_LOCK:
        current = _CONTRACTS.get(identity)
        if current is not None and current[0] is reference:
            _CONTRACTS.pop(identity, None)


def _build(economic_sha256: str) -> FormalReportContract:
    document, payload, digest, artifact = _document(economic_sha256)
    secondary = document["secondary_hypothesis_registry"]
    trials = document["strategy_trial_registry"]
    bootstrap = document["bootstrap"]
    if not all(type(item) is dict for item in (secondary, trials, bootstrap)):
        raise FormalReportContractError("report contract registries changed type")
    value = object.__new__(FormalReportContract)
    fields = {
        "contract_id": document["contract_id"],
        "contract_sha256": digest,
        "artifact_sha256": artifact,
        "schema": document["schema"],
        "status": document["status"],
        "authority": document["authority"],
        "evaluation_id": document["evaluation_id"],
        "economic_execution_definition_sha256": document["parents"][
            "economic_execution_definition_sha256"
        ],
        "secondary_hypothesis_registry_sha256": secondary["registry_sha256"],
        "deflated_sharpe_trial_registry_sha256": trials["registry_sha256"],
        "stock_bootstrap_seed_sha256": bootstrap[
            "stock_FM_and_economic_seed_sha256"
        ],
        "report_family_count": len(document["required_report_family_ids"]),
        "secondary_hypothesis_count": len(secondary["ordered_hypotheses"]),
        "strategy_trial_count": len(trials["ordered_trials"]),
        "_canonical_document": payload,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget(key, ref))
    with _CONTRACTS_LOCK:
        _CONTRACTS[identity] = (reference, payload, _fingerprint(value))
    return require_formal_report_contract(
        value,
        expected_economic_execution_definition_sha256=economic_sha256,
    )


def build_formal_report_contract(
    *, economic_execution_definition_sha256: str
) -> FormalReportContract:
    """Build the exact outcome-free report child of a reviewed economic hash."""

    return _build(
        _sha256(
            economic_execution_definition_sha256,
            "economic execution definition SHA-256",
        )
    )


def require_formal_report_contract(
    value: FormalReportContract,
    *,
    expected_economic_execution_definition_sha256: str | None = None,
) -> FormalReportContract:
    """Reauthenticate identity, exact bytes, registries, and closed authority."""

    if type(value) is not FormalReportContract:
        raise FormalReportContractError("formal report contract changed type")
    with _CONTRACTS_LOCK:
        registered = _CONTRACTS.get(id(value))
    if registered is None or registered[0]() is not value:
        raise FormalReportContractError("formal report contract is not builder-authenticated")
    economic = _sha256(
        value.economic_execution_definition_sha256,
        "economic execution definition SHA-256",
    )
    if expected_economic_execution_definition_sha256 is not None and economic != _sha256(
        expected_economic_execution_definition_sha256,
        "expected economic execution definition SHA-256",
    ):
        raise FormalReportContractError("formal report contract binds another economic parent")
    document, payload, digest, artifact = _document(economic)
    secondary = document["secondary_hypothesis_registry"]
    trials = document["strategy_trial_registry"]
    bootstrap = document["bootstrap"]
    if not all(type(item) is dict for item in (secondary, trials, bootstrap)):
        raise FormalReportContractError("formal report contract registries changed type")
    if (
        registered[1] != payload
        or registered[2] != _fingerprint(value)
        or value._canonical_document != payload
        or value.contract_id != document["contract_id"]
        or value.contract_sha256 != digest
        or value.artifact_sha256 != artifact
        or value.schema != document["schema"]
        or value.status != document["status"]
        or value.authority != document["authority"]
        or value.evaluation_id != document["evaluation_id"]
        or value.secondary_hypothesis_registry_sha256
        != secondary["registry_sha256"]
        or value.deflated_sharpe_trial_registry_sha256
        != trials["registry_sha256"]
        or value.stock_bootstrap_seed_sha256
        != bootstrap["stock_FM_and_economic_seed_sha256"]
        or type(value.report_family_count) is not int
        or value.report_family_count != len(document["required_report_family_ids"])
        or type(value.secondary_hypothesis_count) is not int
        or value.secondary_hypothesis_count != len(secondary["ordered_hypotheses"])
        or type(value.strategy_trial_count) is not int
        or value.strategy_trial_count != len(trials["ordered_trials"])
        or any(
            getattr(value, name) is not False
            for name in (
                "input_read_available",
                "outcome_access_available",
                "quantconnect_available",
                "result_read_available",
                "result_disposition_available",
                "deployment_available",
                "orders_available",
                "trading_available",
            )
        )
    ):
        raise FormalReportContractError("formal report contract changed after authentication")
    return value


def render_formal_report_contract_bytes(value: FormalReportContract) -> bytes:
    """Return the exact canonical candidate bytes without persisting them."""

    require_formal_report_contract(value)
    return bytes(value._canonical_document)


def load_formal_report_contract_bytes(
    payload: bytes,
    *,
    expected_economic_execution_definition_sha256: str,
) -> FormalReportContract:
    """Load only the byte-exact contract for the separately supplied parent."""

    economic = _sha256(
        expected_economic_execution_definition_sha256,
        "expected economic execution definition SHA-256",
    )
    observed = _parse(payload, "formal report contract")
    expected, expected_payload, _digest_value, _artifact = _document(economic)
    if observed != expected or payload != expected_payload:
        raise FormalReportContractError(
            "formal report contract is unknown, incomplete, or binds another parent"
        )
    return _build(economic)


def formal_report_contract_record(value: FormalReportContract) -> dict[str, object]:
    """Return a detached exact record for pre-QC manifest composition."""

    require_formal_report_contract(value)
    return _parse(value._canonical_document, "formal report contract")


__all__ = (
    "AUTHORITY",
    "COHORT_IDS",
    "COMPARATOR_LEDGER_IDS",
    "COST_BPS_PER_SIDE",
    "DESCRIPTIVE_FOLD_IDS",
    "EARNINGS_EXCLUSION_IDS",
    "EVALUATION_ID",
    "F6_ACCOUNTING_AXIS",
    "FOLD_MANIFEST_SHA256",
    "FORMAL_FOLD_IDS",
    "FormalReportContract",
    "FormalReportContractError",
    "HORIZONS",
    "MATCHED_COMPARISON_SHA256",
    "MAX_CONTRACT_BYTES",
    "PORTFOLIO_VARIANT_IDS",
    "PRIMARY_OUTPUT_IDS",
    "QC_FIRST_PLAN_SHA256",
    "RATING_ACTIONS",
    "REPORT_FAMILY_IDS",
    "SCHEMA",
    "SLICE_IDS",
    "SOURCE_VIEW_IDS",
    "STATUS",
    "STOCK_SUCCESSOR_SHA256",
    "build_formal_report_contract",
    "formal_report_contract_record",
    "load_formal_report_contract_bytes",
    "render_formal_report_contract_bytes",
    "require_formal_report_contract",
)
