"""Outcome-free ARV2-4A stock historical-evaluation definition.

The checked-in artifact authenticated here is a structural prerequisite.  It
defines the intended stock screen, reports and downstream topology gates, but
it cannot admit a source, load outcomes, launch QuantConnect, issue a result
disposition, deploy, or trade.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import weakref
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from data.exchange_calendar import ExchangeCalendarError, resolve_nth_session_after

from .qc_first_plan import QcFirstStudyPlan, load_qc_first_study_plan


class StockEvaluationContractError(ValueError):
    """The ARV2-4A definition is malformed, weakened, or falsely authoritative."""


SCHEMA = "arv2-stock-historical-evaluation-structural-v1"
STATUS = (
    "implementation_frozen_outcome_free_structural_candidate_"
    "pending_independent_review"
)
AUTHORITY = (
    "structural_definition_only_no_source_data_outcome_qc_or_deployment_authority"
)
STRATEGY_PDF_SHA256 = (
    "eae7b9954aaf94212108505c52e31a558facd744967fd2526040d5147c616193"
)
PARENT_PLAN_ID = "arv2-qc-first-plan-36e455e72b8750fe"
PARENT_PLAN_HASH = (
    "36e455e72b8750fe3f34773382870e10e62f3f40b5392ae587690bda081b85dc"
)
EVALUATION_ID = "arv2-eval-stock-historical-qc-001"
PRIMARY_OUTPUT_IDS = (
    "bullish_20_session_fama_macbeth",
    "net_20_session_sleeve",
    "firm_specific_vs_global_map_paired_20_session_ic",
)
_LOADED_CONTRACT_AUTHORITY = object()
_CONTRACT_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType["StockEvaluationContract"],
        Path,
        Path,
        tuple[object, ...],
    ],
] = {}
_CONTRACT_AUTHORITIES_LOCK = threading.RLock()


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


CONTROL_DEFINITION = {
    "source_score": "pdf_reliable_score",
    "continuous_columns": [
        "momentum_20d",
        "momentum_60d",
        "momentum_12_1",
        "sector_momentum_20d",
        "sector_momentum_60d",
        "sector_momentum_12_1",
        "industry_momentum_20d",
        "industry_momentum_60d",
        "industry_momentum_12_1",
        "market_beta_252d",
        "realized_volatility_60d",
        "value_book_to_market",
        "growth_trailing_revenue",
        "size_market_cap",
        "liquidity_dollar_volume_60d",
        "turnover_60d",
        "analyst_coverage_60d",
        "event_intensity_20d",
        "event_diversity_20d",
    ],
    "binary_columns": [
        "exact_earnings_day",
        "one_to_two_days_after_earnings",
        "three_to_five_days_after_earnings",
        "over_five_days_after_earnings",
        "pre_earnings",
        "public_guidance_proximity",
    ],
    "forbidden_pretrade_columns": [
        "active_event_indicator",
        "absolute_contribution_weighted_publication_to_entry_jump",
    ],
    "outcome_only_price_jump_vector": [
        "active_event_indicator",
        "absolute_contribution_weighted_publication_to_entry_jump",
    ],
    "detailed_control_source_definition_sha256": None,
    "transform": (
        "same_date_accepted_preopen_control_rows_after_named_refusals_"
        "median_mad_times_1_4826_no_epsilon"
    ),
    "binary_transform": "unchanged_exact_zero_or_one",
    "zero_mad": "refuse_complete_date_cross_section",
    "missing_stale_or_post_open": "refuse_row_before_fit_or_apply",
    "minimum_accepted_control_coverage": {"numerator": 19, "denominator": 20},
    "minimum_accepted_rows_per_cross_section": 20,
    "coverage_denominators": [
        "eligible_candidate_census_rows",
        "accepted_preopen_control_rows",
        "named_preopen_control_refusals",
        "adjusted_output_rows",
        "named_application_refusals",
    ],
    "fit_population": "active_rating_signal_training_rows_only",
    "census_population": (
        "enumerate_all_eligible_rows_including_structural_zeros_and_named_refusals"
    ),
    "estimator": "pooled_equal_weight_training_ols",
    "design": "intercept_then_continuous_then_binary_then_industry_dummies",
    "industry_reference": "lexicographically_first_training_level",
    "unseen_industry": "refuse_active_row_structural_zero_remains_exact_zero",
    "minimum_rows": "strictly_more_than_parameter_count_plus_20",
    "solver": "decimal_modified_gram_schmidt_qr",
    "decimal_precision": 50,
    "decimal_rounding": "ROUND_HALF_EVEN",
    "decimal_emin": -999999,
    "decimal_emax": 999999,
    "rank_relative_threshold": "1e-20",
    "validation_test_application": (
        "freeze_training_coefficients_columns_and_industry_levels_apply_unchanged"
    ),
    "structural_zero": "excluded_from_fit_and_remains_exact_zero",
    "active_residual_clip": ["-4", "4"],
    "outcomes_used": False,
}

GLOBAL_BENCHMARK_DEFINITION = {
    "role": "mandatory_non_rescuing_firm_specific_normalization_gate",
    "global_rating_map_definition_sha256": None,
    "matched_row_contract_sha256": None,
    "required_parity": [
        "same_admitted_raw_events_and_named_refusals",
        "same_point_in_time_universe_controls_costs_and_walk_forward_folds",
        "same_common_event_components_horizon_and_inference",
    ],
    "fit_rule": "fit_each_signal_separately_on_the_same_training_census",
    "primary_metric": (
        "paired_walk_forward_test_date_20_session_spearman_ic_on_identical_rows"
    ),
    "fold_scope": "walk_forward_test_dates_only",
    "comparison": "firm_specific_minus_global_map",
    "margin": {"numerator": 0, "denominator": 1},
    "uncertainty": (
        "paired_centered_moving_block_bootstrap_on_common_test_dates_"
        "length_20_19999_resamples"
    ),
    "pass_rule": (
        "observed_difference_nonnegative_and_one_sided_95pct_lower_bound_"
        "nonnegative_strict_no_worse_with_confidence"
    ),
    "minimum_paired_coverage_definition_sha256": None,
    "secondary_metrics": "registered_BH_FDR_reporting_only_never_rescue",
    "failure": "closes_family",
    "current_execution_authorized": False,
}

HISTORY_DEFINITION = {
    "history_start": "2013-01-02",
    "outcome_cutoff_session": "2026-08-28",
    "horizons_sessions": [1, 5, 20, 60],
    "primary_horizon_sessions": 20,
    "last_mature_decision_session": {
        "1": "2026-08-27",
        "5": "2026-08-21",
        "20": "2026-07-31",
        "60": "2026-06-03",
    },
    "tail": "later_decisions_are_named_immature_refusals",
    "walk_forward": {
        "train_years": 5,
        "validation_years": 2,
        "test_years": 1,
        "step_years": 1,
        "mode": "rolling",
        "intervals": "half_open_nyse_session_intervals",
        "calendar_anchor": "calendar_year_boundaries",
        "partial_2026": "exclude_from_test_fold_until_full_test_interval_exists",
        "purge_sessions_by_horizon": {"1": 1, "5": 5, "20": 20, "60": 60},
        "embargo_sessions_by_horizon": {"1": 1, "5": 5, "20": 20, "60": 60},
        "cross_boundary_common_event_components": "refuse_from_adjacent_samples",
        "fold_manifest_sha256": None,
    },
}

ANALYSIS_DEFINITION = {
    "role": "development_stop_go_not_prospective_confirmation",
    "contamination_disclosure": (
        "2019-07-16_through_2026-07-23_is_discovery_only_all_historical_"
        "inference_is_descriptive"
    ),
    "confirmatory_claim_permitted": False,
    "primary_gate_ids": PRIMARY_OUTPUT_IDS,
    "primary_gate_logic": (
        "intersection_union_conjunction_each_gate_must_pass_none_can_rescue_another"
    ),
    "primary_development_size": {"numerator": 1, "denominator": 20},
    "prospective_alpha_spent": False,
    "fama_macbeth": {
        "regressors_of_interest": {
            "bullish_primary": "maximum_final_control_adjusted_score_and_zero",
            "bearish_secondary": "minimum_final_control_adjusted_score_and_zero",
            "symmetry_assumed": False,
            "bearish_can_rescue_bullish": False,
        },
        "outcome_controls": [
            *CONTROL_DEFINITION["continuous_columns"],
            *CONTROL_DEFINITION["binary_columns"],
            "active_event_indicator",
            "absolute_contribution_weighted_publication_to_entry_jump",
        ],
        "dependent_variable": (
            "gross_security_total_return_minus_matching_SPY_total_return"
        ),
        "outcome_clock": (
            "eligible_decision_session_open_to_horizon_session_open"
        ),
        "date_cross_section": "intercept_scores_controls_and_industry_fixed_effects",
        "eligible_census": (
            "all_point_in_time_eligible_stocks_including_structural_zero_neutral_rows"
        ),
        "refusal_accounting": "exhaustive_before_model_fit_no_signal_filter",
        "invalid_date": "refuse_if_underidentified_or_rank_deficient",
        "date_weighting": "equal_weight_valid_test_dates",
        "common_event_weighting": (
            "equal_common_event_component_weight_within_date_each_row_weight_"
            "one_over_component_row_count_then_normalize_component_weights"
        ),
        "common_event_handling": {
            "membership": (
                "build_a_bipartite_graph_of_security_decision_rows_and_all_"
                "admitted_common_event_ids_then_take_deterministic_connected_components"
            ),
            "multi_event_row": "belongs_to_exactly_one_connected_component",
            "neutral_row": "singleton_component",
            "outcome_duplication": False,
            "cross_date_component": (
                "name_refuse_every_row_in_the_component_before_fold_assignment_"
                "and_report_coverage"
            ),
            "within_date_component": (
                "component_total_weight_one_rows_fractional_by_component_size"
            ),
            "resampling": (
                "complete_nyse_date_blocks_after_cross_date_components_refuse_"
                "so_no_component_can_be_split"
            ),
        },
        "outcome_duplication": False,
        "hac_lag_sessions_by_horizon": {"1": 1, "5": 5, "20": 20, "60": 60},
        "hac_axis": "actual_nyse_session_distance_never_compressed",
        "hac_kernel": "bartlett",
        "hac_pair_normalization": (
            "divide_lag_cross_product_sum_by_total_valid_coefficient_dates"
        ),
        "hac_required_report": "observed_pair_count_by_lag",
        "hac_role": "descriptive_effect_uncertainty_not_separate_pass_gate",
        "development_pass_rule": (
            "bullish_20_session_mean_beta_strictly_positive_and_centered_"
            "two_sided_complete_session_block_bootstrap_p_below_0.05"
        ),
    },
    "information_coefficient": {
        "method": "date_level_unweighted_spearman_average_ranks",
        "score": "signed_final_stock_control_adjusted_score",
        "outcome": "matching_horizon_gross_SPY_excess_open_to_open_total_return",
        "eligible_census": (
            "all_point_in_time_eligible_rows_including_structural_zeros_"
            "after_exhaustive_named_refusal_accounting"
        ),
        "row_multiplicity": "each_security_decision_outcome_exactly_once",
        "tie_rule": "average_ranks_for_score_and_outcome",
        "date_refusal": "fewer_than_20_rows_or_constant_score_or_constant_outcome",
        "fold_scope": "walk_forward_test_dates_only",
        "date_aggregation": "equal_weight_over_valid_dates",
        "common_event_policy": "same_connected_component_and_cross_date_refusal_as_FM",
        "missing_policy": "no_pairwise_imputation_named_row_or_date_refusal",
        "hac_session_axis": "actual_nyse_session_distance_never_compressed",
        "hac_lag_sessions_by_horizon": {"1": 1, "5": 5, "20": 20, "60": 60},
        "hac_kernel": "bartlett",
        "hac_pair_normalization": (
            "divide_each_lag_cross_product_sum_by_total_valid_dates"
        ),
        "hac_required_report": "observed_pair_count_by_lag",
        "required_reports_by_horizon": {
            "1": ["mean", "median", "icir", "positive_date_share", "hac_t_lag_1", "year_by_year_ic"],
            "5": ["mean", "median", "icir", "positive_date_share", "hac_t_lag_5", "year_by_year_ic"],
            "20": ["mean", "median", "icir", "positive_date_share", "hac_t_lag_20", "year_by_year_ic"],
            "60": ["mean", "median", "icir", "positive_date_share", "hac_t_lag_60", "year_by_year_ic"],
        },
        "reports": ["mean", "median", "icir", "positive_date_share", "hac_t", "by_year"],
    },
    "bootstrap": {
        "method": "centered_moving_complete_session_blocks",
        "block_sessions_by_horizon": {"1": 1, "5": 5, "20": 20, "60": 60},
        "resamples": 19999,
        "seed": "sha256_plan_hash_plus_evaluation_id",
        "null_centering": (
            "subtract_the_observed_equal_date_mean_beta_from_each_valid_date_"
            "coefficient_then_resample_centered_complete_date_blocks"
        ),
        "test_statistic": "absolute_equal_date_mean_beta",
        "p_value": (
            "one_plus_resampled_absolute_statistics_gte_observed_absolute_"
            "statistic_divided_by_resamples_plus_one"
        ),
    },
    "minimum_valid_test_dates": 50,
    "invalid_or_underfilled": "locked_inconclusive_no_blind_extension",
}

POWER_DEFINITION = {
    "calibration_source_sha256": None,
    "required_fields": [
        "primary_effect_size_bps_per_adjusted_score_unit",
        "variance_source_without_evaluation_outcomes",
        "target_power",
        "two_sided_size",
        "required_valid_dates",
        "required_connected_components",
        "minimum_row_and_component_coverage",
        "underfill_disposition",
    ],
    "underfill": "INCONCLUSIVE_locked_no_extension",
    "current_execution_authorized": False,
}

ECONOMIC_DEFINITION = {
    "economic_gate_execution_definition_sha256": None,
    "required_definition_fields": [
        "net_excess_daily_total_return_and_benchmark",
        "eligible_ranking_universe_ties_and_minimum_sleeve_size",
        "test_fold_only_sample_and_terminal_liquidation",
        "daily_return_hac_and_centered_block_statistic",
        "coverage_turnover_and_overlap_denominators",
    ],
    "portfolio": (
        "twenty_overlapping_daily_sleeves_equal_weight_top_positive_score_quintile"
    ),
    "primary_variant": "direct_stock_equal_weight",
    "ties": "deterministic_security_id_order_at_exact_score_ties",
    "minimum_sleeve_size": "must_be_frozen_in_execution_definition",
    "no_positive_or_underfilled_sleeve": "leave_sleeve_in_cash",
    "leverage": False,
    "test_folds_only": True,
    "primary_cost_bps_per_side": 10,
    "diagnostic_cost_bps_per_side": [0, 5, 20],
    "benchmark": "matching_SPY_total_return",
    "primary_statistic": "mean_net_excess_daily_total_return",
    "uncertainty": "centered_complete_session_block_bootstrap_length_20",
    "turnover": "net_security_target_change_once_per_session",
    "terminal_liquidation": "included_at_primary_cost",
    "liquidity_impact_binding_sha256": None,
    "liquidity_impact_role": "capacity_diagnostic_only_never_promotion_gate",
    "primary_pass_rule": (
        "positive_mean_net_excess_daily_return_and_centered_block_p_below_0.05"
    ),
    "current_execution_authorized": False,
}

REPORT_DEFINITION = {
    "PRIMARY": PRIMARY_OUTPUT_IDS,
    "SECONDARY": [
        "bullish_1_5_60_session_fama_macbeth",
        "bearish_1_5_20_60_session_fama_macbeth",
        "six_earnings_guidance_timing_cohorts",
        "earnings_exclusion_plus_minus_2_and_5_sessions",
        "direct_stock_inverse_volatility_and_score_weight_variants",
        "cost_0_5_20_bps_per_side",
    ],
    "EXPLORATORY": ["all_unregistered_subgroups_or_parameter_variants"],
    "required_reports": [
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
    ],
    "etf_only_plot_data": "deferred_until_ARV2_5_and_ARV2_6",
    "secondary_hypothesis_registry_sha256": None,
    "benjamini_hochberg": "fixed_order_tie_rule_and_family_required",
    "deflated_sharpe_trial_registry_sha256": None,
    "secondary_can_rescue": False,
    "contains_results": False,
    "result_sha256": None,
}

DISPOSITION_DEFINITION = {
    "allowed": ["PASS", "FAIL", "INCONCLUSIVE", "INVALID_DATA"],
    "PASS": "unlocks_ARV2_5_structural_work_only",
    "FAIL": "closes_family",
    "INCONCLUSIVE": "locked_no_blind_extension",
    "INVALID_DATA": (
        "no_retry_without_documented_content_addressed_correction_and_fresh_authority"
    ),
    "result_disposition_available": False,
}

DOWNSTREAM_DEFINITION = {
    "topology_hierarchy": ["stock", "industry", "etf"],
    "industry_aggregation_definition_sha256": None,
    "topology_comparison_definition_sha256": None,
    "direct_stock_variants": ["equal_weight", "inverse_volatility", "score_weight"],
    "holdings_lag_sensitivity_sessions": [0, 1, 5],
    "etf_must_beat": ["direct_stock", "industry"],
    "conservative_lag_failure": "blocks_etf_promotion",
    "etf_promotion_available": False,
}

EXTERNAL_BINDINGS = {
    "review_commit": None,
    "counter_review_commit": None,
    "control_source_definition_sha256": None,
    "global_rating_map_definition_sha256": None,
    "matched_global_comparison_definition_sha256": None,
    "fold_manifest_sha256": None,
    "power_calibration_source_sha256": None,
    "secondary_hypothesis_registry_sha256": None,
    "deflated_sharpe_trial_registry_sha256": None,
    "liquidity_impact_binding_sha256": None,
    "dataset_id": None,
    "code_identity": None,
    "qc_plan_sha256": None,
    "evaluation_receipt_id": None,
}

CAPABILITIES = {
    "source_access": False,
    "outcome_access": False,
    "qc_upload": False,
    "qc_compile": False,
    "qc_launch": False,
    "result_disposition": False,
    "paper_deployment": False,
    "funded_deployment": False,
    "orders": False,
}

_SECTIONS = {
    "control_definition": CONTROL_DEFINITION,
    "global_benchmark_definition": GLOBAL_BENCHMARK_DEFINITION,
    "history_definition": HISTORY_DEFINITION,
    "analysis_definition": ANALYSIS_DEFINITION,
    "power_definition": POWER_DEFINITION,
    "economic_definition": ECONOMIC_DEFINITION,
    "report_definition": REPORT_DEFINITION,
    "disposition_definition": DISPOSITION_DEFINITION,
    "downstream_definition": DOWNSTREAM_DEFINITION,
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


SECTION_HASHES = {
    name: hashlib.sha256(_canonical(value)).hexdigest()
    for name, value in _SECTIONS.items()
}

CONTROL_DEFINITION = _freeze(CONTROL_DEFINITION)
GLOBAL_BENCHMARK_DEFINITION = _freeze(GLOBAL_BENCHMARK_DEFINITION)
HISTORY_DEFINITION = _freeze(HISTORY_DEFINITION)
ANALYSIS_DEFINITION = _freeze(ANALYSIS_DEFINITION)
POWER_DEFINITION = _freeze(POWER_DEFINITION)
ECONOMIC_DEFINITION = _freeze(ECONOMIC_DEFINITION)
REPORT_DEFINITION = _freeze(REPORT_DEFINITION)
DISPOSITION_DEFINITION = _freeze(DISPOSITION_DEFINITION)
DOWNSTREAM_DEFINITION = _freeze(DOWNSTREAM_DEFINITION)
EXTERNAL_BINDINGS = _freeze(EXTERNAL_BINDINGS)
CAPABILITIES = _freeze(CAPABILITIES)
SECTION_HASHES = _freeze(SECTION_HASHES)
_SECTIONS = MappingProxyType(
    {
        "control_definition": CONTROL_DEFINITION,
        "global_benchmark_definition": GLOBAL_BENCHMARK_DEFINITION,
        "history_definition": HISTORY_DEFINITION,
        "analysis_definition": ANALYSIS_DEFINITION,
        "power_definition": POWER_DEFINITION,
        "economic_definition": ECONOMIC_DEFINITION,
        "report_definition": REPORT_DEFINITION,
        "disposition_definition": DISPOSITION_DEFINITION,
        "downstream_definition": DOWNSTREAM_DEFINITION,
    }
)

_ROOT_KEYS = frozenset(
    {
        "schema",
        "status",
        "authority",
        "spec_id",
        "spec_hash",
        "strategy_pdf_sha256",
        "parent_plan_id",
        "parent_plan_hash",
        "evaluation_id",
        *_SECTIONS,
        "section_hashes",
        "external_bindings",
        "capabilities",
    }
)


def _reject_float(value: str) -> None:
    raise StockEvaluationContractError(f"binary floating-point is forbidden: {value}")


def _reject_constant(value: str) -> None:
    raise StockEvaluationContractError(f"non-finite JSON is forbidden: {value}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StockEvaluationContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_stable_regular(path: Path, name: str) -> tuple[Path, bytes]:
    candidate = Path(path)
    absolute = candidate.absolute()
    if any(item.is_symlink() for item in (absolute, *absolute.parents)):
        raise StockEvaluationContractError(f"{name} must not traverse a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise StockEvaluationContractError(f"{name} is unavailable") from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise StockEvaluationContractError(f"{name} must be a regular file")
    try:
        first = resolved.read_bytes()
        second = resolved.read_bytes()
    except OSError as exc:
        raise StockEvaluationContractError(f"{name} is unreadable") from exc
    if first != second:
        raise StockEvaluationContractError(f"{name} changed while being read")
    return resolved, first


def _revalidate(path: Path, payload: bytes, name: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise StockEvaluationContractError(f"{name} changed or disappeared")
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise StockEvaluationContractError(f"{name} changed or disappeared") from exc
    if current != payload:
        raise StockEvaluationContractError(f"{name} changed after authentication")


def _require_exact(actual: object, expected: object, name: str) -> None:
    if isinstance(expected, Mapping):
        if type(actual) is not dict or set(actual) != set(expected):
            raise StockEvaluationContractError(f"{name} changed from the frozen definition")
        for key, expected_value in expected.items():
            _require_exact(actual[key], expected_value, f"{name}.{key}")
        return
    if type(expected) is tuple:
        if type(actual) is not list or len(actual) != len(expected):
            raise StockEvaluationContractError(f"{name} changed from the frozen definition")
        for index, (item, expected_item) in enumerate(zip(actual, expected, strict=True)):
            _require_exact(item, expected_item, f"{name}[{index}]")
        return
    if type(actual) is not type(expected) or actual != expected:
        raise StockEvaluationContractError(f"{name} changed from the frozen definition")


def _content_payload(raw: Mapping[str, Any]) -> bytes:
    payload = dict(raw)
    payload["spec_id"] = None
    payload["spec_hash"] = None
    return _canonical(payload)


def _fingerprint_value(value: object) -> object:
    if isinstance(value, Mapping):
        return tuple(
            (key, _fingerprint_value(item))
            for key, item in sorted(value.items())
        )
    if isinstance(value, tuple):
        return tuple(_fingerprint_value(item) for item in value)
    return value


@dataclasses.dataclass(frozen=True, init=False)
class StockEvaluationContract:
    """Immutable structural definition; every action capability is literal false."""

    spec_id: str
    spec_hash: str
    parent_plan_id: str
    parent_plan_hash: str
    sections: Mapping[str, Any]
    section_hashes: Mapping[str, str]
    external_bindings: Mapping[str, Any]
    _authority: object = dataclasses.field(repr=False, compare=False)

    @property
    def source_access_available(self) -> bool:
        return False

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def qc_action_available(self) -> bool:
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


def _contract_fingerprint(contract: StockEvaluationContract) -> tuple[object, ...]:
    return (
        contract.spec_id,
        contract.spec_hash,
        contract.parent_plan_id,
        contract.parent_plan_hash,
        _fingerprint_value(contract.sections),
        _fingerprint_value(contract.section_hashes),
        _fingerprint_value(contract.external_bindings),
    )


def _forget_loaded_contract(
    identity: int,
    reference: weakref.ReferenceType[StockEvaluationContract],
) -> None:
    with _CONTRACT_AUTHORITIES_LOCK:
        current = _CONTRACT_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _CONTRACT_AUTHORITIES.pop(identity, None)


def _loaded_contract(
    *,
    spec_id: str,
    spec_hash: str,
    parent_plan_id: str,
    parent_plan_hash: str,
    sections: Mapping[str, Any],
    section_hashes: Mapping[str, str],
    external_bindings: Mapping[str, Any],
    source_path: Path,
    qc_first_plan_path: Path,
) -> StockEvaluationContract:
    value = object.__new__(StockEvaluationContract)
    fields = {
        "spec_id": spec_id,
        "spec_hash": spec_hash,
        "parent_plan_id": parent_plan_id,
        "parent_plan_hash": parent_plan_hash,
        "sections": sections,
        "section_hashes": section_hashes,
        "external_bindings": external_bindings,
        "_authority": _LOADED_CONTRACT_AUTHORITY,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    fingerprint = _contract_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(
        value,
        lambda ref, key=identity: _forget_loaded_contract(key, ref),
    )
    with _CONTRACT_AUTHORITIES_LOCK:
        _CONTRACT_AUTHORITIES[identity] = (
            reference,
            source_path,
            qc_first_plan_path,
            fingerprint,
        )
    return value


def require_loaded_stock_evaluation_contract(
    contract: StockEvaluationContract,
) -> StockEvaluationContract:
    """Reauthenticate loader provenance, immutable fields, and source bytes."""
    if (
        type(contract) is not StockEvaluationContract
        or getattr(contract, "_authority", None) is not _LOADED_CONTRACT_AUTHORITY
    ):
        raise StockEvaluationContractError(
            "stock evaluation contract is not loader-authenticated"
        )
    with _CONTRACT_AUTHORITIES_LOCK:
        authority = _CONTRACT_AUTHORITIES.get(id(contract))
    if authority is None or authority[0]() is not contract:
        raise StockEvaluationContractError(
            "stock evaluation contract loader authority is absent"
        )
    _, source_path, qc_plan_path, fingerprint = authority
    if _contract_fingerprint(contract) != fingerprint:
        raise StockEvaluationContractError(
            "stock evaluation contract changed after authentication"
        )
    reloaded = load_stock_evaluation_contract(
        source_path,
        qc_first_plan_path=qc_plan_path,
    )
    if _contract_fingerprint(reloaded) != fingerprint:
        raise StockEvaluationContractError(
            "stock evaluation contract source changed after authentication"
        )
    return contract


@dataclasses.dataclass(frozen=True)
class StockReportPlan:
    """Ordered report inventory with no rows, results, or disposition surface."""

    schema: str
    authority: str
    spec_hash: str
    primary_output_ids: tuple[str, ...]
    secondary_output_ids: tuple[str, ...]
    exploratory_output_ids: tuple[str, ...]
    required_report_ids: tuple[str, ...]
    outcome_rows_consumed: int
    contains_results: bool
    result_sha256: None
    promotion_available: bool

    def __post_init__(self) -> None:
        if self.schema != "arv2-stock-report-plan-v1" or self.authority != AUTHORITY:
            raise StockEvaluationContractError("stock report plan authority changed")
        if (
            self.outcome_rows_consumed != 0
            or self.contains_results is not False
            or self.result_sha256 is not None
            or self.promotion_available is not False
        ):
            raise StockEvaluationContractError("structural report plan acquired results")
        expected = REPORT_DEFINITION
        if (
            self.primary_output_ids != expected["PRIMARY"]
            or self.secondary_output_ids != expected["SECONDARY"]
            or self.exploratory_output_ids != expected["EXPLORATORY"]
            or self.required_report_ids != expected["required_reports"]
        ):
            raise StockEvaluationContractError("stock report inventory changed")


def build_stock_report_plan(contract: StockEvaluationContract) -> StockReportPlan:
    """Materialize the frozen report inventory without accepting outcomes."""
    require_loaded_stock_evaluation_contract(contract)
    report = contract.sections["report_definition"]
    if report != REPORT_DEFINITION:
        raise StockEvaluationContractError("report definition changed")
    return StockReportPlan(
        schema="arv2-stock-report-plan-v1",
        authority=AUTHORITY,
        spec_hash=contract.spec_hash,
        primary_output_ids=tuple(report["PRIMARY"]),
        secondary_output_ids=tuple(report["SECONDARY"]),
        exploratory_output_ids=tuple(report["EXPLORATORY"]),
        required_report_ids=tuple(report["required_reports"]),
        outcome_rows_consumed=0,
        contains_results=False,
        result_sha256=None,
        promotion_available=False,
    )


def load_stock_evaluation_contract(
    path: Path,
    *,
    qc_first_plan_path: Path,
) -> StockEvaluationContract:
    """Authenticate the exact ARV2-4A structural definition and its parent."""
    resolved, payload = _read_stable_regular(path, "stock evaluation contract")
    if payload.startswith(
        (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")
    ):
        raise StockEvaluationContractError("stock evaluation contract must not contain a BOM")
    try:
        text = payload.decode("utf-8", errors="strict")
        raw = json.loads(
            text,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StockEvaluationContractError("stock evaluation contract is invalid JSON") from exc
    if type(raw) is not dict or set(raw) != _ROOT_KEYS:
        raise StockEvaluationContractError("stock evaluation contract root fields are not exact")
    canonical_file = (
        json.dumps(raw, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")
    if payload != canonical_file:
        raise StockEvaluationContractError(
            "stock evaluation contract bytes are not canonical UTF-8 JSON"
        )

    _require_exact(raw["schema"], SCHEMA, "schema")
    _require_exact(raw["status"], STATUS, "status")
    _require_exact(raw["authority"], AUTHORITY, "authority")
    _require_exact(raw["strategy_pdf_sha256"], STRATEGY_PDF_SHA256, "strategy_pdf_sha256")
    _require_exact(raw["parent_plan_id"], PARENT_PLAN_ID, "parent_plan_id")
    _require_exact(raw["parent_plan_hash"], PARENT_PLAN_HASH, "parent_plan_hash")
    _require_exact(raw["evaluation_id"], EVALUATION_ID, "evaluation_id")
    for name, expected in _SECTIONS.items():
        _require_exact(raw[name], expected, name)
    _require_exact(raw["section_hashes"], SECTION_HASHES, "section_hashes")
    _require_exact(raw["external_bindings"], EXTERNAL_BINDINGS, "external_bindings")
    _require_exact(raw["capabilities"], CAPABILITIES, "capabilities")
    for name, section in _SECTIONS.items():
        if hashlib.sha256(_canonical(raw[name])).hexdigest() != raw["section_hashes"][name]:
            raise StockEvaluationContractError(f"{name} section hash mismatch")

    declared_hash = raw["spec_hash"]
    if (
        type(declared_hash) is not str
        or len(declared_hash) != 64
        or any(character not in "0123456789abcdef" for character in declared_hash)
    ):
        raise StockEvaluationContractError("spec_hash must be a lowercase SHA-256")
    actual_hash = hashlib.sha256(_content_payload(raw)).hexdigest()
    if declared_hash != actual_hash:
        raise StockEvaluationContractError("stock evaluation contract content hash mismatch")
    if raw["spec_id"] != f"arv2-stock-historical-{actual_hash[:16]}":
        raise StockEvaluationContractError("spec_id is not content-derived")

    parent: QcFirstStudyPlan = load_qc_first_study_plan(qc_first_plan_path)
    if parent.plan_id != PARENT_PLAN_ID or parent.plan_hash != PARENT_PLAN_HASH:
        raise StockEvaluationContractError("QC-first parent identity changed")
    try:
        resolved_qc_first_plan = Path(qc_first_plan_path).resolve(strict=True)
    except OSError as exc:
        raise StockEvaluationContractError(
            "QC-first parent changed or disappeared"
        ) from exc
    history = raw["history_definition"]
    cutoff = history["outcome_cutoff_session"]
    for horizon, decision in history["last_mature_decision_session"].items():
        try:
            maturity = resolve_nth_session_after(decision, int(horizon))
        except (ExchangeCalendarError, ValueError) as exc:
            raise StockEvaluationContractError("horizon maturity cannot be resolved") from exc
        if maturity != cutoff:
            raise StockEvaluationContractError("horizon maturity does not equal cutoff")

    _revalidate(resolved, payload, "stock evaluation contract")
    sections = {name: raw[name] for name in _SECTIONS}
    return _loaded_contract(
        spec_id=raw["spec_id"],
        spec_hash=raw["spec_hash"],
        parent_plan_id=raw["parent_plan_id"],
        parent_plan_hash=raw["parent_plan_hash"],
        sections=_freeze(sections),
        section_hashes=_freeze(raw["section_hashes"]),
        external_bindings=_freeze(raw["external_bindings"]),
        source_path=resolved,
        qc_first_plan_path=resolved_qc_first_plan,
    )
