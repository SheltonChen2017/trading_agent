"""Outcome-free ARV2-4C global-comparator and matched-row authority.

The strategy's production signal uses reviewed firm-specific rating scales.
This module authenticates a deliberately naive, fixed global comparator used
only to test that the firm-specific treatment is no worse.  It also freezes
the paired comparison and deterministic block-start contract.  It cannot read
provider rows or outcomes, run QuantConnect, dispose a result, deploy, or
trade.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import threading
import weakref
from datetime import date
from enum import Enum
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from data.exchange_calendar import ExchangeCalendarError, trading_sessions

from .fold_manifest import (
    StockFoldManifest,
    StockFoldManifestError,
    load_stock_fold_manifest,
)
from .qc_first_plan import QcFirstPlanError
from .stock_evaluation_contract import (
    StockEvaluationContract,
    StockEvaluationContractError,
    load_stock_evaluation_contract,
)


class GlobalBenchmarkContractError(ValueError):
    """A global-map or paired-comparison artifact is malformed or unauthentic."""


STRATEGY_PDF_SHA256 = (
    "eae7b9954aaf94212108505c52e31a558facd744967fd2526040d5147c616193"
)
QC_PLAN_ID = "arv2-qc-first-plan-36e455e72b8750fe"
QC_PLAN_HASH = (
    "36e455e72b8750fe3f34773382870e10e62f3f40b5392ae587690bda081b85dc"
)
QC_PLAN_ARTIFACT_SHA256 = (
    "8339238dd5ce32ed7b351aab2662fb408cc7d9a3c62ff89bf8b1d14f20acd081"
)
SUPERSEDED_BASE_ARTIFACT_SHA256 = (
    "b40a76f5f2f7726f328f1e444a41ecb0670234055a7c9c7245a26ffab601af2f"
)
SUPERSEDED_BASE_ID = "arv2-round0-candidate-8d13a0a4577df322"
SUPERSEDED_BASE_HASH = (
    "8d13a0a4577df3223c96c4c11722457e059b4ade63f578ab860ce7364494e847"
)
PARENT_STOCK_SPEC_ID = "arv2-stock-historical-c5ff2a6a0dcf341e"
PARENT_STOCK_SPEC_HASH = (
    "c5ff2a6a0dcf341e3c7bad4ea56e4a3c00f20faab5896c0fcd3bd7c291835a0b"
)
PARENT_STOCK_SPEC_ARTIFACT_SHA256 = (
    "34d1e71548bc6850a02590596594944dad3fadb38954067f2cc2d00dcaa86bc8"
)
FOLD_MANIFEST_ID = "arv2-stock-folds-1002155dbe8e3e87"
FOLD_MANIFEST_HASH = (
    "1002155dbe8e3e87b220b7419039bff95f5c0812d2306c56a8ac51b76c5d7611"
)
FOLD_MANIFEST_ARTIFACT_SHA256 = (
    "fecd984ad937fed57b860b15fdcb9cc994ff59ab62c3b72d5160ab62b342953c"
)
EVALUATION_ID = "arv2-eval-stock-historical-qc-001"

MAP_SCHEMA = "arv2-global-rating-map-structural-v1"
MATCHED_SCHEMA = "arv2-global-matched-comparison-structural-v1"
SUCCESSOR_SCHEMA = "arv2-stock-historical-successor-structural-v2"
STATUS = "owner_approved_implementation_frozen_outcome_free_pending_independent_review"
MAP_AUTHORITY = (
    "global_comparator_policy_only_no_provider_data_outcome_qc_or_deployment_authority"
)
MATCHED_AUTHORITY = (
    "paired_comparison_definition_only_no_provider_data_outcome_qc_or_deployment_authority"
)
SUCCESSOR_AUTHORITY = (
    "stock_contract_successor_only_no_provider_data_outcome_qc_or_deployment_authority"
)
SAMPLER_DOMAIN = "arv2-paired-ic-noncircular-mbb-hash-counter-v1"

_EXTERNAL_BINDINGS = {
    "independent_review_commit": None,
    "counter_review_commit": None,
    "source_rights_receipt_id": None,
    "dataset_id": None,
    "outcome_artifact_sha256": None,
    "power_plan_sha256": None,
    "qc_project_id": None,
    "qc_run_id": None,
    "evaluation_receipt_id": None,
}
_CAPABILITIES = {
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

_MAPPING_LEVELS = (
    (
        5,
        1,
        1,
        (
            "strong buy",
            "conviction buy",
            "top pick",
            "action list buy",
        ),
    ),
    (
        4,
        1,
        2,
        (
            "buy",
            "outperform",
            "overweight",
            "market outperform",
            "sector outperform",
            "positive",
            "accumulate",
            "add",
            "speculative buy",
            "long-term buy",
            "outperformer",
            "above average",
        ),
    ),
    (
        3,
        0,
        1,
        (
            "neutral",
            "hold",
            "equal-weight",
            "market perform",
            "sector perform",
            "in-line",
            "sector weight",
            "perform",
            "peer perform",
            "market weight",
            "average",
        ),
    ),
    (
        2,
        -1,
        2,
        (
            "underweight",
            "underperform",
            "sector underperform",
            "market underperform",
            "reduce",
            "negative",
            "underperformer",
            "below average",
            "trim",
            "cautious",
        ),
    ),
    (1, -1, 1, ("sell", "strong sell")),
)
_MEASURED_REFUSALS = (
    "developing",
    "equalweight",
    "fair value",
    "gradually accumulate",
    "hold neutral",
    "mixed",
    "not rated",
    "performer",
    "sector overweight",
    "sector performer",
    "sector underweight",
    "speculative hold",
    "tender",
    "trading buy",
    "trading sell",
)
_EXPECTED_LEVEL_COUNTS = {5: 4, 4: 12, 3: 11, 2: 10, 1: 2}

_FOLD_AXIS_SUMMARIES = (
    {
        "fold_id": "arv2-wf-test-2020-h20",
        "test_start_inclusive": "2020-01-31",
        "test_end_exclusive": "2021-01-04",
        "session_count": 233,
        "session_axis_sha256": "6547133cb7292c1b94f0a25eb54c97b252aae3b8b273c5bf6175db92e6b218b2",
        "allowed_start_count": 214,
        "blocks_drawn": 12,
        "final_block_sessions_retained": 13,
    },
    {
        "fold_id": "arv2-wf-test-2021-h20",
        "test_start_inclusive": "2021-02-02",
        "test_end_exclusive": "2022-01-03",
        "session_count": 232,
        "session_axis_sha256": "e29e4bd66e3706bf0f339c5c3ec03f3eed59ca77345838d711cc855f010cf6d1",
        "allowed_start_count": 213,
        "blocks_drawn": 12,
        "final_block_sessions_retained": 12,
    },
    {
        "fold_id": "arv2-wf-test-2022-h20",
        "test_start_inclusive": "2022-02-01",
        "test_end_exclusive": "2023-01-03",
        "session_count": 231,
        "session_axis_sha256": "0a58fb5ac63cf6199f131ff64f558f10ca8d4f238d610cb368a5e1d6f4acdb63",
        "allowed_start_count": 212,
        "blocks_drawn": 12,
        "final_block_sessions_retained": 11,
    },
    {
        "fold_id": "arv2-wf-test-2023-h20",
        "test_start_inclusive": "2023-02-01",
        "test_end_exclusive": "2024-01-02",
        "session_count": 230,
        "session_axis_sha256": "76f0ed5e01babd1b376537e249f000fa35c1390ca9b2d1f446c54f7039111bed",
        "allowed_start_count": 211,
        "blocks_drawn": 12,
        "final_block_sessions_retained": 10,
    },
    {
        "fold_id": "arv2-wf-test-2024-h20",
        "test_start_inclusive": "2024-01-31",
        "test_end_exclusive": "2025-01-02",
        "session_count": 232,
        "session_axis_sha256": "9fab5c021d29fd02409b44a80ce770d9cb599a9432c943362e5a2365d7a235e0",
        "allowed_start_count": 213,
        "blocks_drawn": 12,
        "final_block_sessions_retained": 12,
    },
    {
        "fold_id": "arv2-wf-test-2025-h20",
        "test_start_inclusive": "2025-02-03",
        "test_end_exclusive": "2026-01-02",
        "session_count": 230,
        "session_axis_sha256": "a289bed633d8c12471dafa462c769d75fd1df0daf1f4c7c0497072421ab8722b",
        "allowed_start_count": 211,
        "blocks_drawn": 12,
        "final_block_sessions_retained": 10,
    },
)


def _freeze_constant(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze_constant(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_constant(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_constant(item) for item in value)
    return value


_EXTERNAL_BINDINGS = _freeze_constant(_EXTERNAL_BINDINGS)
_CAPABILITIES = _freeze_constant(_CAPABILITIES)
_EXPECTED_LEVEL_COUNTS = _freeze_constant(_EXPECTED_LEVEL_COUNTS)
_FOLD_AXIS_SUMMARIES = _freeze_constant(_FOLD_AXIS_SUMMARIES)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise GlobalBenchmarkContractError("noncanonical JSON value") from exc


def _render(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise GlobalBenchmarkContractError("noncanonical JSON value") from exc


def _content_identity(
    raw: Mapping[str, Any], *, id_field: str, hash_field: str, prefix: str
) -> dict[str, Any]:
    value = dict(raw)
    value[id_field] = None
    value[hash_field] = None
    digest = hashlib.sha256(_canonical(value)).hexdigest()
    value[hash_field] = digest
    value[id_field] = f"{prefix}{digest[:16]}"
    return value


def _artifact_binding(
    document: Mapping[str, Any], *, id_field: str, hash_field: str
) -> dict[str, str]:
    return {
        "artifact_id": document[id_field],
        "content_sha256": document[hash_field],
        "artifact_sha256": hashlib.sha256(_render(document)).hexdigest(),
    }


def _map_document() -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": MAP_SCHEMA,
        "status": STATUS,
        "authority": MAP_AUTHORITY,
        "map_id": None,
        "map_hash": None,
        "strategy_pdf_sha256": STRATEGY_PDF_SHA256,
        "policy_provenance": {
            "owner_decision": "2026-09-01_full_39_alias_comparator_approved",
            "role": "naive_global_benchmark_only_not_firm_semantics",
            "retained_v1_policy_path": "docs/Archive/Research/ACER_V1/ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md",
            "retained_v1_policy_git_blob_sha1": "ce3a9b12eb9e1d5abaabc9ec439d5eaebfd25ca7",
            "retained_v1_policy_repository_blob_sha256": "e3290c2a9d7a833049e1b739efc542e1e8bdc355c61e8580a78f44bf208e984b",
            "complete_inventory_origin_commit": "1eb3649048225f023c2950bf0a9379a7fef818cf",
            "complete_inventory_origin_path": "docs/research/ACER_2026-08-21_ACER0A_COMPLETION_PROPOSALS.md",
            "complete_inventory_origin_git_blob_sha1": "98e29337afba34e5a5f6abbac3fb0ced1442d917",
            "measurement_status": "historical_aggregate_context_only_no_per_string_counts_and_no_v2_data_authority",
            "PDF_named_ambiguous_aliases_retained_as_naive_policy": [
                "positive",
                "accumulate",
                "sector perform",
                "top pick",
            ],
            "semantic_disclosure": "all_39_aliases_are_comparator_policy_only_and_never_firm_specific_semantics",
        },
        "canonicalization": {
            "input": "exact_python_str_max_256_code_points",
            "character_set": "printable_ASCII_U+0020_through_U+007E_only",
            "case": "ASCII_lowercase",
            "whitespace": "trim_and_collapse_runs_of_U+0020_only",
            "unicode_normalization": "none_non_ASCII_refuses",
            "punctuation_rewrite": "none",
            "unknown_label": "named_unknown_future_label_refusal_no_default",
        },
        "score_definition": {
            "formula": "score=(legacy_level-3)/2",
            "exact_type": "reduced_rational_numerator_denominator",
            "range": [-1, 1],
            "legacy_alignment": "divide_legacy_minus2_to_plus2_scores_by_2",
            "rank_effect": "positive_affine_rescaling_is_Spearman_inert_for_fixed_membership_and_ties",
        },
        "ordered_mappings": [
            {
                "legacy_level": level,
                "score": {"numerator": numerator, "denominator": denominator},
                "aliases": list(aliases),
            }
            for level, numerator, denominator, aliases in _MAPPING_LEVELS
        ],
        "ordered_refusals": list(_MEASURED_REFUSALS),
        "inventory_contract": {
            "mapped_alias_count": 39,
            "measured_refusal_count": 15,
            "union_count": 54,
            "mapped_counts_by_level_descending": [4, 12, 11, 10, 2],
            "per_string_event_counts_available": False,
        },
        "collision_contract": {
            "artifact_post_canonicalization_collision": "INVALID_ARTIFACT",
            "map_refusal_overlap": "INVALID_ARTIFACT",
            "observed_raw_forms_same_canonical_key": "same_policy_disposition_plus_non_rescuing_collision_diagnostic",
            "equal_score_directional_pair": "global_tier_collapse_zero_active_event_zero_score_and_breadth_mass",
        },
        "diagnostics_contract": {
            "stage": "future_authenticated_pre_outcome_census_only",
            "required": [
                "exact_raw_and_canonical_label_disposition_counts",
                "mapped_refused_unknown_invalid_endpoint_counts_with_denominators",
                "endpoint_pair_disposition_counts_with_denominators",
                "raw_form_collision_counts_with_denominators",
            ],
            "role": "reporting_and_coverage_only_never_changes_mapping_or_rescues_gate",
        },
        "external_bindings": dict(_EXTERNAL_BINDINGS),
        "capabilities": dict(_CAPABILITIES),
    }
    return _content_identity(
        raw,
        id_field="map_id",
        hash_field="map_hash",
        prefix="arv2-global-rating-map-",
    )


MAP_BINDING = MappingProxyType(
    _artifact_binding(_map_document(), id_field="map_id", hash_field="map_hash")
)


def _matched_document() -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": MATCHED_SCHEMA,
        "status": STATUS,
        "authority": MATCHED_AUTHORITY,
        "contract_id": None,
        "contract_hash": None,
        "strategy_pdf_sha256": STRATEGY_PDF_SHA256,
        "evaluation_id": EVALUATION_ID,
        "parent_stock_spec": {
            "artifact_id": PARENT_STOCK_SPEC_ID,
            "content_sha256": PARENT_STOCK_SPEC_HASH,
            "artifact_sha256": PARENT_STOCK_SPEC_ARTIFACT_SHA256,
        },
        "existing_fold_manifest": {
            "artifact_id": FOLD_MANIFEST_ID,
            "content_sha256": FOLD_MANIFEST_HASH,
            "artifact_sha256": FOLD_MANIFEST_ARTIFACT_SHA256,
            "relationship": "existing_reviewed_child_of_stock_v1_bound_without_reparenting_or_byte_change",
        },
        "global_rating_map": dict(MAP_BINDING),
        "arm_contract": {
            "ordered_arm_ids": ["firm_specific", "global_legacy_39"],
            "shared_inputs": [
                "event_and_endpoint_identities",
                "point_in_time_activity_evidence",
                "q_data",
                "NYSE_event_ages_and_decay_kernel",
                "point_in_time_sector_and_industry",
                "eligible_security_decision_census",
                "common_event_graph",
                "controls_and_walk_forward_folds",
                "outcome_identity_and_value_once_separately_authorized_and_joined",
            ],
            "per_arm_derivations": [
                "mapped_rating_delta",
                "decayed_contribution_and_absolute_mass",
                "raw_stock_score",
                "institution_breadth_mass",
                "common_event_breadth_mass",
                "conservative_N_eff",
                "sector_normalization",
                "reliability",
                "training_coefficients",
                "held_out_residuals",
            ],
            "fit_rule": "fit_each_arm_separately_on_the_same_training_census",
            "global_tier_collapse_zero": {
                "event_state": "ACTIVE",
                "raw_score_mass": {"numerator": 0, "denominator": 1},
                "institution_breadth_mass": {"numerator": 0, "denominator": 1},
                "common_event_breadth_mass": {"numerator": 0, "denominator": 1},
                "can_increase_N_eff": False,
                "all_mass_zero_reliability": {"numerator": 0, "denominator": 1},
                "only_collapse_events_security_date_state": "ACTIVE_zero_row_not_STRUCTURAL_ZERO_with_zero_reliability_preserved_into_paired_sector_normalization_and_fit_census",
                "diagnostic_required": True,
            },
            "global_direction_contract": {
                "census": "firm_admitted_directional_event_instances_with_both_global_endpoints_mapped",
                "expected_sign_delta": "ACTIVE_use_exact_signed_global_delta",
                "zero_delta": "ACTIVE_global_tier_collapse_zero",
                "opposite_sign_delta": "joint_global_direction_conflict_refusal_charged_to_coverage_no_contribution_either_arm",
                "reason": "retain_legacy_direction_consistency_without_sign_flip_and_keep_joint_row_parity_through_named_refusal",
                "legacy_v1_difference": "only_exact_zero_delta_is_successor_totalized_opposite_sign_refusal_is_retained",
                "diagnostic": "pooled_and_per_fold_expected_sign_opposite_sign_and_zero_delta_event_instance_counts",
            },
        },
        "matched_row_contract": {
            "key_fields": [
                "fold_id",
                "decision_session",
                "permanent_security_id",
                "horizon_sessions",
            ],
            "required_horizon_sessions": 20,
            "parity": "exact_one_to_one_same_order_independent_membership_check",
            "duplicates": "INVALID_DATA",
            "imputation": "forbidden",
            "one_arm_row_removal": "forbidden",
            "outcome_dependent_membership": "forbidden",
            "outcome_join": "later_single_authenticated_exact_identity_join_shared_by_both_arms",
            "outcome_key_or_value_mismatch": "INVALID_DATA",
        },
        "paired_sector_normalization": {
            "minimum_total_names": 20,
            "minimum_active_names": 5,
            "minimum_failure": "joint_named_refusal_charged_to_coverage",
            "exact_zero_range_global_arm": "paired_only_all_zero_standardized_scores_preserve_ACTIVE_vs_STRUCTURAL_ZERO_state",
            "exact_zero_range_firm_arm": "paired_only_all_zero_standardized_scores_preserve_ACTIVE_vs_STRUCTURAL_ZERO_state_parent_single_arm_refusal_retained_outside_paired_gate",
            "one_arm_totalization_effect_on_other": "none",
            "nonzero_range_zero_MAD": "joint_zero_mad_nonzero_range_refusal_charged_to_coverage",
            "shared_control_zero_MAD": "parent_joint_refusal_retained",
            "epsilon_or_market_fallback": "forbidden",
        },
        "paired_metric_contract": {
            "existing_single_arm_rule": "fewer_than_20_rows_or_constant_score_or_constant_outcome_refuses",
            "scope": "firm_specific_vs_global_paired_gate_only",
            "row_floor": 20,
            "fewer_than_20_identical_rows": "joint_date_refusal",
            "constant_shared_outcome": "joint_date_refusal",
            "neither_score_constant": "ordinary_average_rank_Spearman_for_both_arms",
            "exactly_one_score_constant": "constant_arm_association_exact_zero_other_arm_ordinary_average_rank_Spearman",
            "both_scores_constant": "joint_both_arms_constant_score_refusal_no_d_t",
            "paired_totalized_zero_is_single_arm_IC": False,
            "difference": "d_t=IC_firm_specific_t-IC_global_legacy_39_t",
            "date_aggregation": "equal_weight_over_common_valid_dates",
            "ordered_primary_date_disposition": [
                "outcome_identity_invalid_or_duplicate_INVALID_DATA",
                "fewer_than_20_identical_rows_joint_date_refusal",
                "constant_shared_outcome_joint_date_refusal",
                "both_scores_constant_joint_date_refusal",
                "exactly_one_score_constant_totalize_constant_arm_to_zero",
                "neither_score_constant_compute_both_Spearman",
            ],
            "diagnostic_predicates": "independently_counted_non_rescuing_predicates_may_overlap_primary_disposition_is_exclusive_first_match",
            "numerical_contract": {
                "binary_float": "forbidden",
                "decimal_precision": 50,
                "decimal_rounding": "ROUND_HALF_EVEN",
                "decimal_Emin": -999999,
                "decimal_Emax": 999999,
                "decimal_capitals": 1,
                "decimal_clamp": 0,
                "finite_inputs_only": True,
                "ambient_decimal_context": "ignored_fresh_local_context_for_each_calculation",
                "decimal_flags": "cleared_before_each_calculation_and_never_used_as_result_authority",
                "decimal_traps": "InvalidOperation_DivisionByZero_Overflow_enabled_all_other_traps_disabled",
                "average_ranks": "exact_rational_midranks_then_convert_inside_frozen_decimal_context",
                "Spearman": "centered_rank_cross_product_sum_divided_by_square_root_of_product_of_centered_rank_sum_squares",
                "square_root": "Decimal.sqrt_under_same_50_digit_HALF_EVEN_context",
                "stable_sum": "sort_each_finite_Decimal_multiset_by_absolute_value_then_signed_value_before_sum_from_exact_zero",
                "row_order": "permanent_security_id_ascending_before_rank_construction",
                "mean_and_centering": "same_context_stable_sum_divided_by_exact_integer_count",
                "type_7_weights": "exact_Decimal_0.9_and_0.1",
                "comparison": "exact_resulting_Decimal_against_exact_zero_no_epsilon_or_tolerance",
            },
        },
        "coverage_contract": {
            "outcome_free_only_before_launch": True,
            "preoutcome_candidate_date": "test_fold_session_with_exact_arm_key_parity_at_least_20_rows_and_all_required_non_outcome_inputs_score_dispersion_does_not_remove_denominator",
            "paired_score_capable_date": "preoutcome_candidate_date_with_valid_both_arm_scores_and_not_both_arms_constant",
            "minimum_ratio": {"numerator": 19, "denominator": 20},
            "ratio_arithmetic": "exact_integer_cross_multiplication_no_rounding",
            "separate_ledgers": {
                "endpoint_pair_mapping": "both_endpoints_global_resolvable_and_direction_admissible_expected_sign_or_zero_delta_directional_event_instance_occurrences_over_all_firm_admitted_directional_event_instance_occurrences_opposite_sign_is_denominator_only",
                "active_security_date_rows": "exact_paired_arm_security_date_row_instances_over_firm_arm_eligible_active_security_date_row_instances",
                "common_event_components": "retained_paired_component_instances_over_firm_arm_component_instances",
                "component_member_incidence": "retained_paired_component_member_incidence_instances_over_firm_arm_component_member_incidence_instances",
                "score_capable_dates": "paired_score_capable_date_instances_over_preoutcome_candidate_date_instances",
            },
            "gate_aggregation": "each_separate_ledger_must_pass_19_over_20_both_pooled_globally_and_independently_in_every_nonempty_fold",
            "zero_denominator": "INVALID_DATA_not_ready",
            "preoutcome_shortfall": "INVALID_DATA_requires_new_owner_approved_content_addressed_policy_before_any_outcome_look",
            "post_join_requirements": {
                "valid_dates": "max(50,bound_power_plan.required_valid_dates)",
                "connected_components": "max(50,bound_power_plan.required_connected_components)",
                "power_plan_binding_required_before_evaluation": True,
            },
            "outcome_identity_corruption_or_mismatch": "INVALID_DATA",
            "honest_post_join_underfill": "INCONCLUSIVE_locked_no_extension",
            "outcome_informed_map_fold_period_seed_or_retry_change": "forbidden",
        },
        "bootstrap_contract": {
            "horizon_sessions": 20,
            "block_sessions": 20,
            "resamples": 19999,
            "observed_statistic": "D=equal_valid_date_mean(d_t)_pooled_across_folds",
            "centered_value": "x_t=d_t-D_on_available_valid_dates_only",
            "resampling_axis": "each_fold_complete_ordered_NYSE_h20_effective_test_session_axis_never_compressed",
            "fold_axis_summaries": [dict(item) for item in _FOLD_AXIS_SUMMARIES],
            "allowed_starts": "integer_positions_0_through_N_f_minus_20_inclusive_noncircular",
            "draws_per_fold": "ceil(N_f/20)_uniform_with_replacement",
            "position_construction": "concatenate_blocks_in_draw_order_then_truncate_to_first_N_f_positions",
            "missing_or_refused_position": "adds_neither_zero_nor_denominator",
            "sampling_multiplicity": "retained",
            "replicate_statistic": "equal_occurrence_mean_of_all_available_centered_values_pooled_across_folds_not_equal_fold_mean",
            "zero_available_replicate": "INCONCLUSIVE_locked_no_extension_no_redraw",
            "quantile": {
                "method": "Hyndman_Fan_Type_7",
                "probability": {"numerator": 19, "denominator": 20},
                "B_19999_exact": "0.9_times_ordered_18999_plus_0.1_times_ordered_19000_one_based",
            },
            "lower_bound": "LCB95=D-q95",
            "sampler": {
                "domain": SAMPLER_DOMAIN,
                "seed_record_encoding": "canonical_sorted_compact_UTF8_JSON_plus_one_LF",
                "seed_record_fields": [
                    "domain",
                    "successor_stock_spec_sha256",
                    "matched_row_contract_sha256",
                    "global_rating_map_sha256",
                    "fold_manifest_sha256",
                    "evaluation_id",
                    "sampler_version",
                ],
                "seed_digest": "SHA256(seed_record_bytes)",
                "draw_preimage": "domain_UTF8||00||seed_digest_raw32||uint64BE(resample)||uint64BE(fold)||uint64BE(block)||uint64BE(rejection)",
                "word": "unsigned_big_endian_full_SHA256_digest",
                "uniform_conversion": "reject_u_at_or_above_2^256-(2^256_mod_m)_then_u_mod_m",
                "ordinals": "zero_based_exact_nonnegative_uint64_bool_forbidden",
                "rejection_overflow": "INVALID_DATA",
            },
        },
        "gate_contract": {
            "name": "zero_margin_no_worse_with_confidence",
            "margin": {"numerator": 0, "denominator": 1},
            "interpretation": "operationally_equivalent_to_one_sided_superiority_boundary_in_nondegenerate_samples_exact_equality_passes",
            "pass": "D_greater_than_or_equal_zero_and_LCB95_greater_than_or_equal_zero",
            "adequate_sample_failure": "FAIL_closes_family",
            "structural_invalidity": "INVALID_DATA",
            "honest_underfill": "INCONCLUSIVE_locked_no_extension",
        },
        "diagnostics_contract": {
            "role": "labeled_non_rescuing_reporting_only",
            "scope": "pooled_global_and_each_fold_where_applicable",
            "required_ratios": [
                {
                    "id": "global_tier_collapse_zero_share",
                    "numerator": "paired_admitted_directional_event_instances_with_both_global_endpoints_mapped_and_zero_global_delta",
                    "denominator": "paired_admitted_directional_event_instances_with_both_global_endpoints_mapped",
                },
                {
                    "id": "global_direction_conflict_share",
                    "numerator": "paired_admitted_directional_event_instances_with_both_global_endpoints_mapped_and_opposite_sign_global_delta",
                    "denominator": "paired_admitted_directional_event_instances_with_both_global_endpoints_mapped",
                },
                {
                    "id": "firm_totalized_zero_date_share",
                    "numerator": "preoutcome_candidate_dates_with_at_least_one_firm_arm_paired_sector_exact_zero_range_totalization",
                    "denominator": "preoutcome_candidate_dates",
                },
                {
                    "id": "global_totalized_zero_date_share",
                    "numerator": "preoutcome_candidate_dates_with_at_least_one_global_arm_paired_sector_exact_zero_range_totalization",
                    "denominator": "preoutcome_candidate_dates",
                },
                {
                    "id": "both_arms_constant_date_share",
                    "numerator": "preoutcome_candidate_dates_where_both_final_arm_score_vectors_are_constant",
                    "denominator": "preoutcome_candidate_dates",
                },
                {
                    "id": "zero_available_bootstrap_replicate_share",
                    "numerator": "bootstrap_replicates_with_zero_available_centered_differences",
                    "denominator": "exactly_19999_registered_bootstrap_replicates",
                },
            ],
            "required_censuses": [
                "mapped_measured_refusal_unknown_invalid_endpoint_event_instance_counts_with_exact_denominator",
                "mapped_measured_refusal_unknown_invalid_endpoint_pair_event_instance_counts_with_exact_denominator",
                "expected_sign_opposite_sign_and_zero_global_delta_event_instance_counts_with_exact_denominator",
            ],
            "ratio_invariant": "each_numerator_and_denominator_use_identical_units_and_numerator_must_not_exceed_denominator",
        },
        "external_bindings": dict(_EXTERNAL_BINDINGS),
        "capabilities": dict(_CAPABILITIES),
    }
    return _content_identity(
        raw,
        id_field="contract_id",
        hash_field="contract_hash",
        prefix="arv2-global-matched-",
    )


MATCHED_BINDING = MappingProxyType(
    _artifact_binding(
        _matched_document(),
        id_field="contract_id",
        hash_field="contract_hash",
    )
)


def _successor_document() -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": SUCCESSOR_SCHEMA,
        "status": STATUS,
        "authority": SUCCESSOR_AUTHORITY,
        "spec_id": None,
        "spec_hash": None,
        "strategy_pdf_sha256": STRATEGY_PDF_SHA256,
        "evaluation_id": EVALUATION_ID,
        "qc_first_plan": {
            "artifact_id": QC_PLAN_ID,
            "content_sha256": QC_PLAN_HASH,
            "artifact_sha256": QC_PLAN_ARTIFACT_SHA256,
        },
        "superseded_qc_plan_base": {
            "artifact_id": SUPERSEDED_BASE_ID,
            "content_sha256": SUPERSEDED_BASE_HASH,
            "artifact_sha256": SUPERSEDED_BASE_ARTIFACT_SHA256,
        },
        "predecessor_stock_spec": {
            "artifact_id": PARENT_STOCK_SPEC_ID,
            "content_sha256": PARENT_STOCK_SPEC_HASH,
            "artifact_sha256": PARENT_STOCK_SPEC_ARTIFACT_SHA256,
        },
        "existing_fold_manifest": {
            "artifact_id": FOLD_MANIFEST_ID,
            "content_sha256": FOLD_MANIFEST_HASH,
            "artifact_sha256": FOLD_MANIFEST_ARTIFACT_SHA256,
            "bytes_and_parent_pins_changed": False,
        },
        "global_rating_map": dict(MAP_BINDING),
        "matched_comparison_contract": dict(MATCHED_BINDING),
        "inheritance_contract": {
            "predecessor_sections_retained_unless_explicitly_amended": True,
            "single_arm_information_coefficient_date_refusal_retained": "fewer_than_20_rows_or_constant_score_or_constant_outcome",
            "global_benchmark_role_retained": "mandatory_non_rescuing_firm_specific_normalization_gate",
            "new_scope": "paired_global_gate_only",
            "fold_manifest_repin_or_reparent": "forbidden",
        },
        "explicit_amendments": {
            "global_rating_map_definition_sha256": MAP_BINDING["content_sha256"],
            "matched_row_contract_sha256": MATCHED_BINDING["content_sha256"],
            "minimum_paired_coverage_definition_sha256": MATCHED_BINDING[
                "content_sha256"
            ],
            "uncertainty_successor": "paired_centered_noncircular_moving_blocks_on_each_complete_fold_test_session_axis",
            "paired_constant_arm_rule": "exactly_one_constant_arm_totalizes_to_zero_both_constant_jointly_refuse",
            "execution_authorized": False,
        },
        "acyclic_lineage": {
            "edge_direction": "child_to_parent",
            "ordered_nodes": [
                {"node": "strategy_pdf", "parents": []},
                {"node": "qc_base", "parents": ["strategy_pdf"]},
                {
                    "node": "qc_plan",
                    "parents": ["strategy_pdf", "qc_base"],
                },
                {
                    "node": "stock_v1",
                    "parents": ["strategy_pdf", "qc_plan"],
                },
                {
                    "node": "fold_manifest",
                    "parents": ["strategy_pdf", "qc_plan", "stock_v1"],
                },
                {"node": "global_map", "parents": ["strategy_pdf"]},
                {
                    "node": "matched_contract",
                    "parents": [
                        "strategy_pdf",
                        "stock_v1",
                        "fold_manifest",
                        "global_map",
                    ],
                },
                {
                    "node": "stock_v2",
                    "parents": [
                        "strategy_pdf",
                        "qc_plan",
                        "stock_v1",
                        "fold_manifest",
                        "global_map",
                        "matched_contract",
                    ],
                },
            ],
            "existing_fold_manifest_reparenting": "forbidden",
            "successor_must_not_be_parent_of_any_bound_ancestor": True,
        },
        "remaining_gates": {
            "independent_review": "required",
            "counter_review": "required",
            "content_addressed_power_plan": "required_before_evaluation",
            "authenticated_preoutcome_source_census": "required_before_coverage_claim",
            "source_and_processing_rights": "required",
            "outcome_and_QC_authority": "separate_exact_later_authority_required",
        },
        "external_bindings": dict(_EXTERNAL_BINDINGS),
        "capabilities": dict(_CAPABILITIES),
    }
    return _content_identity(
        raw,
        id_field="spec_id",
        hash_field="spec_hash",
        prefix="arv2-stock-historical-successor-",
    )


SUCCESSOR_BINDING = MappingProxyType(
    _artifact_binding(
        _successor_document(), id_field="spec_id", hash_field="spec_hash"
    )
)


def _reject_float(value: str) -> None:
    raise GlobalBenchmarkContractError(f"binary floating-point is forbidden: {value}")


def _reject_constant(value: str) -> None:
    raise GlobalBenchmarkContractError(f"non-finite JSON is forbidden: {value}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GlobalBenchmarkContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _is_link_like(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(
            getattr(path, "is_junction", lambda: False)()
        )
    except OSError:
        return True


def _read_stable_regular(path: Path, name: str) -> tuple[Path, bytes]:
    candidate = Path(path)
    absolute = candidate.absolute()
    if any(_is_link_like(item) for item in (absolute, *absolute.parents)):
        raise GlobalBenchmarkContractError(f"{name} must not traverse a link")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise GlobalBenchmarkContractError(f"{name} is unavailable") from exc
    if _is_link_like(resolved) or not resolved.is_file():
        raise GlobalBenchmarkContractError(f"{name} must be a regular file")
    try:
        before = resolved.stat()
        first = resolved.read_bytes()
        second = resolved.read_bytes()
        after = resolved.stat()
    except OSError as exc:
        raise GlobalBenchmarkContractError(f"{name} is unreadable") from exc
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity or first != second:
        raise GlobalBenchmarkContractError(f"{name} changed while being read")
    return resolved, first


def _revalidate(path: Path, payload: bytes, name: str) -> None:
    if _is_link_like(path) or not path.is_file():
        raise GlobalBenchmarkContractError(f"{name} changed or disappeared")
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise GlobalBenchmarkContractError(f"{name} changed or disappeared") from exc
    if current != payload:
        raise GlobalBenchmarkContractError(f"{name} changed after authentication")


def _parse_artifact(payload: bytes, name: str) -> dict[str, Any]:
    if payload.startswith(
        (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")
    ):
        raise GlobalBenchmarkContractError(f"{name} must not contain a BOM")
    try:
        raw = json.loads(
            payload.decode("utf-8", errors="strict"),
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object,
        )
    except UnicodeDecodeError as exc:
        raise GlobalBenchmarkContractError(f"{name} is not strict UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise GlobalBenchmarkContractError(f"{name} is invalid JSON") from exc
    if type(raw) is not dict:
        raise GlobalBenchmarkContractError(f"{name} must be a JSON object")
    if _render(raw) != payload:
        raise GlobalBenchmarkContractError(
            f"{name} bytes are not canonical sorted UTF-8 JSON"
        )
    return raw


def _validate_content_identity(
    raw: Mapping[str, Any], *, id_field: str, hash_field: str, prefix: str, name: str
) -> None:
    declared_hash = raw.get(hash_field)
    if (
        type(declared_hash) is not str
        or len(declared_hash) != 64
        or any(character not in "0123456789abcdef" for character in declared_hash)
    ):
        raise GlobalBenchmarkContractError(f"{name} content hash is invalid")
    payload = dict(raw)
    payload[id_field] = None
    payload[hash_field] = None
    actual = hashlib.sha256(_canonical(payload)).hexdigest()
    if declared_hash != actual:
        raise GlobalBenchmarkContractError(f"{name} content hash mismatch")
    if raw.get(id_field) != f"{prefix}{actual[:16]}":
        raise GlobalBenchmarkContractError(f"{name} identity is not content-derived")


def _require_exact(actual: object, expected: object, name: str) -> None:
    if isinstance(expected, dict):
        if type(actual) is not dict or set(actual) != set(expected):
            raise GlobalBenchmarkContractError(f"{name} changed from the frozen definition")
        for key, value in expected.items():
            _require_exact(actual[key], value, f"{name}.{key}")
        return
    if isinstance(expected, list):
        if type(actual) is not list or len(actual) != len(expected):
            raise GlobalBenchmarkContractError(f"{name} changed from the frozen definition")
        for index, (item, value) in enumerate(zip(actual, expected, strict=True)):
            _require_exact(item, value, f"{name}[{index}]")
        return
    if type(actual) is not type(expected) or actual != expected:
        raise GlobalBenchmarkContractError(f"{name} changed from the frozen definition")


def _canonicalize_policy_label(raw_label: str) -> str:
    return " ".join(part for part in raw_label.lower().split(" ") if part)


def _validate_map_semantics(raw: Mapping[str, Any]) -> None:
    groups = raw.get("ordered_mappings")
    refused = raw.get("ordered_refusals")
    if type(groups) is not list or type(refused) is not list:
        raise GlobalBenchmarkContractError("global map inventories must be arrays")
    mapped: list[str] = []
    counts: dict[int, int] = {}
    for group in groups:
        if type(group) is not dict:
            raise GlobalBenchmarkContractError("global map level group is invalid")
        level = group.get("legacy_level")
        score = group.get("score", {})
        aliases = group.get("aliases", [])
        if type(level) is not int or type(score) is not dict or type(aliases) is not list:
            raise GlobalBenchmarkContractError("global map level group is invalid")
        expected_score = Fraction(level - 3, 2)
        try:
            numerator = score["numerator"]
            denominator = score["denominator"]
            if (
                type(numerator) is not int
                or type(denominator) is not int
                or denominator <= 0
                or math.gcd(abs(numerator), denominator) != 1
            ):
                raise GlobalBenchmarkContractError(
                    "global map score must be a reduced rational"
                )
            actual_score = Fraction(numerator, denominator)
        except (KeyError, TypeError, ZeroDivisionError) as exc:
            raise GlobalBenchmarkContractError("global map score is invalid") from exc
        if actual_score != expected_score:
            raise GlobalBenchmarkContractError("global map score formula changed")
        counts[level] = len(aliases)
        mapped.extend(aliases)
    if counts != _EXPECTED_LEVEL_COUNTS or len(mapped) != 39 or len(refused) != 15:
        raise GlobalBenchmarkContractError("global map inventory counts changed")
    if refused != sorted(refused):
        raise GlobalBenchmarkContractError("global map refusals are not canonical-sorted")
    combined = mapped + refused
    if any(
        type(item) is not str
        or not item
        or len(item) > 256
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in item)
        for item in combined
    ):
        raise GlobalBenchmarkContractError("global map label is not printable ASCII")
    mapped_keys = set(map(_canonicalize_policy_label, mapped))
    refused_keys = set(map(_canonicalize_policy_label, refused))
    if mapped_keys & refused_keys:
        raise GlobalBenchmarkContractError("global map and refusal inventory overlap")
    canonical = [_canonicalize_policy_label(item) for item in combined]
    if len(canonical) != 54 or len(set(canonical)) != 54:
        raise GlobalBenchmarkContractError("global map contains a canonical collision")


def _lineage_graph(raw: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    try:
        nodes = raw["acyclic_lineage"]["ordered_nodes"]
    except (KeyError, TypeError) as exc:
        raise GlobalBenchmarkContractError("successor lineage graph is malformed") from exc
    if type(nodes) is not list:
        raise GlobalBenchmarkContractError("successor lineage graph is malformed")
    graph: dict[str, tuple[str, ...]] = {}
    for item in nodes:
        if type(item) is not dict or set(item) != {"node", "parents"}:
            raise GlobalBenchmarkContractError("successor lineage graph is malformed")
        node = item["node"]
        parents = item["parents"]
        if (
            type(node) is not str
            or not node
            or type(parents) is not list
            or any(type(parent) is not str or not parent for parent in parents)
            or len(parents) != len(set(parents))
        ):
            raise GlobalBenchmarkContractError("successor lineage graph is malformed")
        if node in graph:
            raise GlobalBenchmarkContractError("successor lineage graph repeats a node")
        graph[node] = tuple(parents)
    if len(graph) != len(nodes):
        raise GlobalBenchmarkContractError("successor lineage graph repeats a node")
    if any(parent not in graph for parents in graph.values() for parent in parents):
        raise GlobalBenchmarkContractError("successor lineage graph has an unknown parent")
    _assert_acyclic(graph)
    expected = {
        "strategy_pdf": (),
        "qc_base": ("strategy_pdf",),
        "qc_plan": ("strategy_pdf", "qc_base"),
        "stock_v1": ("strategy_pdf", "qc_plan"),
        "fold_manifest": ("strategy_pdf", "qc_plan", "stock_v1"),
        "global_map": ("strategy_pdf",),
        "matched_contract": (
            "strategy_pdf",
            "stock_v1",
            "fold_manifest",
            "global_map",
        ),
        "stock_v2": (
            "strategy_pdf",
            "qc_plan",
            "stock_v1",
            "fold_manifest",
            "global_map",
            "matched_contract",
        ),
    }
    if graph != expected:
        raise GlobalBenchmarkContractError(
            "successor lineage graph is incomplete or inconsistent with bindings"
        )
    return graph


def _assert_acyclic(graph: Mapping[str, Iterable[str]]) -> None:
    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise GlobalBenchmarkContractError("successor lineage graph contains a cycle")
        if node in complete:
            return
        visiting.add(node)
        for parent in graph[node]:
            visit(parent)
        visiting.remove(node)
        complete.add(node)

    for node in graph:
        visit(node)


def _load_exact_artifact(
    path: Path,
    *,
    expected: Mapping[str, Any],
    id_field: str,
    hash_field: str,
    prefix: str,
    name: str,
) -> tuple[Path, bytes, dict[str, Any]]:
    resolved, payload = _read_stable_regular(path, name)
    raw = _parse_artifact(payload, name)
    _validate_content_identity(
        raw,
        id_field=id_field,
        hash_field=hash_field,
        prefix=prefix,
        name=name,
    )
    if name == "global rating map":
        _validate_map_semantics(raw)
    if name == "stock successor":
        _assert_acyclic(_lineage_graph(raw))
    _require_exact(raw, expected, name)
    return resolved, payload, raw


def _freeze(value: Any) -> Any:
    return _freeze_constant(value)


@dataclasses.dataclass(frozen=True)
class GlobalRatingMapEntry:
    canonical_label: str
    legacy_level: int
    score_numerator: int
    score_denominator: int

    @property
    def score(self) -> Fraction:
        return Fraction(self.score_numerator, self.score_denominator)


@dataclasses.dataclass(frozen=True)
class GlobalRatingMapping:
    raw_label: str
    canonical_label: str
    entry: GlobalRatingMapEntry
    map_id: str
    map_hash: str

    @property
    def score(self) -> Fraction:
        return self.entry.score


class GlobalRatingRefusalReason(str, Enum):
    INVALID_TYPE = "invalid_type"
    EMPTY_OR_OVERLONG = "empty_or_overlong"
    NON_PRINTABLE_ASCII = "non_printable_ascii"
    MEASURED_REFUSAL = "measured_refusal"
    UNKNOWN_FUTURE_LABEL = "unknown_future_label"


@dataclasses.dataclass(frozen=True)
class GlobalRatingMappingRefusal:
    raw_label: object
    canonical_label: str | None
    reason: GlobalRatingRefusalReason
    map_id: str
    map_hash: str


class GlobalRatingTransitionDisposition(str, Enum):
    ACTIVE_EXPECTED_DIRECTION = "active_expected_direction"
    ACTIVE_TIER_COLLAPSE_ZERO = "active_tier_collapse_zero"
    JOINT_DIRECTION_CONFLICT_REFUSAL = "joint_direction_conflict_refusal"


@dataclasses.dataclass(frozen=True)
class GlobalRatingTransition:
    action: str
    previous: GlobalRatingMapping
    current: GlobalRatingMapping
    delta: Fraction
    disposition: GlobalRatingTransitionDisposition


@dataclasses.dataclass(frozen=True, init=False)
class GlobalBenchmarkContract:
    map_id: str
    map_hash: str
    matched_contract_id: str
    matched_contract_hash: str
    successor_spec_id: str
    successor_spec_hash: str
    evaluation_id: str
    entries: tuple[GlobalRatingMapEntry, ...]
    measured_refusals: tuple[str, ...]
    fold_axis_summaries: tuple[Mapping[str, Any], ...]
    lineage_graph: Mapping[str, tuple[str, ...]]
    capabilities: Mapping[str, bool]
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


_LOADED_GLOBAL_BENCHMARK_AUTHORITY = object()
_GLOBAL_BENCHMARK_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[GlobalBenchmarkContract],
        tuple[tuple[Path, bytes, str], ...],
        tuple[object, ...],
    ],
] = {}
_GLOBAL_BENCHMARK_AUTHORITIES_LOCK = threading.RLock()


def _fingerprint_value(value: object) -> object:
    """Reduce frozen authority state to exact built-in, type-tagged values."""
    if type(value) is MappingProxyType:
        pairs = []
        for key, item in value.items():
            if type(key) is not str:
                raise GlobalBenchmarkContractError(
                    "global benchmark contains a noncanonical authority key"
                )
            pairs.append((key, _fingerprint_value(item)))
        return ("mapping", tuple(sorted(pairs)))
    if type(value) is tuple:
        return ("tuple", tuple(_fingerprint_value(item) for item in value))
    if type(value) is str:
        return ("str", value)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if value is None:
        return ("none", None)
    raise GlobalBenchmarkContractError(
        "global benchmark contains noncanonical authority state"
    )


def _contract_fingerprint(contract: GlobalBenchmarkContract) -> tuple[object, ...]:
    string_fields = (
        "map_id",
        "map_hash",
        "matched_contract_id",
        "matched_contract_hash",
        "successor_spec_id",
        "successor_spec_hash",
        "evaluation_id",
    )
    if any(type(getattr(contract, name, None)) is not str for name in string_fields):
        raise GlobalBenchmarkContractError(
            "global benchmark identity fields changed type"
        )
    if type(contract.entries) is not tuple or any(
        type(entry) is not GlobalRatingMapEntry
        or type(entry.canonical_label) is not str
        or type(entry.legacy_level) is not int
        or type(entry.score_numerator) is not int
        or type(entry.score_denominator) is not int
        for entry in contract.entries
    ):
        raise GlobalBenchmarkContractError("global benchmark entries changed type")
    if type(contract.measured_refusals) is not tuple or any(
        type(item) is not str for item in contract.measured_refusals
    ):
        raise GlobalBenchmarkContractError(
            "global benchmark refusal inventory changed type"
        )
    return (
        *(getattr(contract, name) for name in string_fields),
        tuple(
            (
                entry.canonical_label,
                entry.legacy_level,
                entry.score_numerator,
                entry.score_denominator,
            )
            for entry in contract.entries
        ),
        contract.measured_refusals,
        _fingerprint_value(contract.fold_axis_summaries),
        _fingerprint_value(contract.lineage_graph),
        _fingerprint_value(contract.capabilities),
    )


def _forget_authority(
    identity: int, reference: weakref.ReferenceType[GlobalBenchmarkContract]
) -> None:
    with _GLOBAL_BENCHMARK_AUTHORITIES_LOCK:
        current = _GLOBAL_BENCHMARK_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _GLOBAL_BENCHMARK_AUTHORITIES.pop(identity, None)


def _entries_from_map(raw: Mapping[str, Any]) -> tuple[GlobalRatingMapEntry, ...]:
    entries: list[GlobalRatingMapEntry] = []
    for group in raw["ordered_mappings"]:
        for label in group["aliases"]:
            entries.append(
                GlobalRatingMapEntry(
                    canonical_label=label,
                    legacy_level=group["legacy_level"],
                    score_numerator=group["score"]["numerator"],
                    score_denominator=group["score"]["denominator"],
                )
            )
    return tuple(entries)


def _validate_fold_axes(manifest: StockFoldManifest) -> None:
    actual: list[dict[str, Any]] = []
    for fold in manifest.walk_forward_contract["folds"]:
        boundary = next(
            item
            for item in fold["horizon_boundaries"]
            if item["horizon_sessions"] == 20
        )
        start = date.fromisoformat(boundary["test_start"])
        end = date.fromisoformat(boundary["test_end_exclusive"])
        try:
            sessions = tuple(
                item.isoformat()
                for item in trading_sessions(start, end)
                if item < end
            )
        except ExchangeCalendarError as exc:
            raise GlobalBenchmarkContractError(
                "paired bootstrap fold axis cannot be resolved"
            ) from exc
        count = len(sessions)
        block = 20
        actual.append(
            {
                "fold_id": boundary["fold_id"],
                "test_start_inclusive": boundary["test_start"],
                "test_end_exclusive": boundary["test_end_exclusive"],
                "session_count": count,
                "session_axis_sha256": hashlib.sha256(_canonical(sessions)).hexdigest(),
                "allowed_start_count": count - block + 1,
                "blocks_drawn": (count + block - 1) // block,
                "final_block_sessions_retained": count % block or block,
            }
        )
    if actual != list(_FOLD_AXIS_SUMMARIES):
        raise GlobalBenchmarkContractError("paired bootstrap fold axes changed")


def load_global_benchmark_contract(
    *,
    map_path: Path,
    matched_contract_path: Path,
    successor_spec_path: Path,
    parent_stock_spec_path: Path,
    fold_manifest_path: Path,
    qc_first_plan_path: Path,
) -> GlobalBenchmarkContract:
    """Authenticate ARV2-4C and its exact acyclic, outcome-free ancestry."""
    map_resolved, map_payload, map_raw = _load_exact_artifact(
        map_path,
        expected=_map_document(),
        id_field="map_id",
        hash_field="map_hash",
        prefix="arv2-global-rating-map-",
        name="global rating map",
    )
    matched_resolved, matched_payload, matched_raw = _load_exact_artifact(
        matched_contract_path,
        expected=_matched_document(),
        id_field="contract_id",
        hash_field="contract_hash",
        prefix="arv2-global-matched-",
        name="matched comparison contract",
    )
    successor_resolved, successor_payload, successor_raw = _load_exact_artifact(
        successor_spec_path,
        expected=_successor_document(),
        id_field="spec_id",
        hash_field="spec_hash",
        prefix="arv2-stock-historical-successor-",
        name="stock successor",
    )
    parent_resolved, parent_payload = _read_stable_regular(
        parent_stock_spec_path, "predecessor stock specification"
    )
    fold_resolved, fold_payload = _read_stable_regular(
        fold_manifest_path, "existing fold manifest"
    )
    qc_resolved, qc_payload = _read_stable_regular(
        qc_first_plan_path, "QC-first plan"
    )
    base_resolved, base_payload = _read_stable_regular(
        qc_resolved.with_name("arv2_round0.draft.json"),
        "superseded QC-plan base",
    )
    if hashlib.sha256(parent_payload).hexdigest() != PARENT_STOCK_SPEC_ARTIFACT_SHA256:
        raise GlobalBenchmarkContractError("predecessor stock bytes changed")
    if hashlib.sha256(fold_payload).hexdigest() != FOLD_MANIFEST_ARTIFACT_SHA256:
        raise GlobalBenchmarkContractError("existing fold-manifest bytes changed")
    if hashlib.sha256(qc_payload).hexdigest() != QC_PLAN_ARTIFACT_SHA256:
        raise GlobalBenchmarkContractError("QC-first plan bytes changed")
    if hashlib.sha256(base_payload).hexdigest() != SUPERSEDED_BASE_ARTIFACT_SHA256:
        raise GlobalBenchmarkContractError("superseded QC-plan base bytes changed")
    try:
        parent: StockEvaluationContract = load_stock_evaluation_contract(
            parent_resolved, qc_first_plan_path=qc_resolved
        )
        manifest: StockFoldManifest = load_stock_fold_manifest(
            fold_resolved,
            stock_evaluation_path=parent_resolved,
            qc_first_plan_path=qc_resolved,
        )
    except (
        QcFirstPlanError,
        StockEvaluationContractError,
        StockFoldManifestError,
    ) as exc:
        raise GlobalBenchmarkContractError(
            "ARV2-4C predecessor authentication failed"
        ) from exc
    if parent.spec_id != PARENT_STOCK_SPEC_ID or parent.spec_hash != PARENT_STOCK_SPEC_HASH:
        raise GlobalBenchmarkContractError("predecessor stock identity changed")
    if manifest.manifest_id != FOLD_MANIFEST_ID or manifest.manifest_hash != FOLD_MANIFEST_HASH:
        raise GlobalBenchmarkContractError("existing fold identity changed")
    global_parent = parent.sections["global_benchmark_definition"]
    if any(
        global_parent[name] is not None
        for name in (
            "global_rating_map_definition_sha256",
            "matched_row_contract_sha256",
            "minimum_paired_coverage_definition_sha256",
        )
    ):
        raise GlobalBenchmarkContractError("predecessor global child slots changed")
    if any(
        parent.external_bindings[name] is not None
        for name in (
            "global_rating_map_definition_sha256",
            "matched_global_comparison_definition_sha256",
            "fold_manifest_sha256",
        )
    ):
        raise GlobalBenchmarkContractError("predecessor external child slots changed")
    if parent.sections["analysis_definition"]["information_coefficient"]["date_refusal"] != (
        "fewer_than_20_rows_or_constant_score_or_constant_outcome"
    ):
        raise GlobalBenchmarkContractError("single-arm IC refusal changed")
    if parent.sections["history_definition"]["walk_forward"]["fold_manifest_sha256"] is not None:
        raise GlobalBenchmarkContractError("predecessor acquired a circular child pin")
    if hashlib.sha256(map_payload).hexdigest() != matched_raw["global_rating_map"][
        "artifact_sha256"
    ]:
        raise GlobalBenchmarkContractError("matched contract map-byte pin changed")
    if hashlib.sha256(matched_payload).hexdigest() != successor_raw[
        "matched_comparison_contract"
    ]["artifact_sha256"]:
        raise GlobalBenchmarkContractError("successor matched-contract byte pin changed")
    if hashlib.sha256(map_payload).hexdigest() != successor_raw["global_rating_map"][
        "artifact_sha256"
    ]:
        raise GlobalBenchmarkContractError("successor map-byte pin changed")
    _validate_fold_axes(manifest)
    for path, payload, name in (
        (map_resolved, map_payload, "global rating map"),
        (matched_resolved, matched_payload, "matched comparison contract"),
        (successor_resolved, successor_payload, "stock successor"),
        (parent_resolved, parent_payload, "predecessor stock specification"),
        (fold_resolved, fold_payload, "existing fold manifest"),
        (qc_resolved, qc_payload, "QC-first plan"),
        (base_resolved, base_payload, "superseded QC-plan base"),
    ):
        _revalidate(path, payload, name)

    value = object.__new__(GlobalBenchmarkContract)
    fields: dict[str, object] = {
        "map_id": map_raw["map_id"],
        "map_hash": map_raw["map_hash"],
        "matched_contract_id": matched_raw["contract_id"],
        "matched_contract_hash": matched_raw["contract_hash"],
        "successor_spec_id": successor_raw["spec_id"],
        "successor_spec_hash": successor_raw["spec_hash"],
        "evaluation_id": successor_raw["evaluation_id"],
        "entries": _entries_from_map(map_raw),
        "measured_refusals": tuple(map_raw["ordered_refusals"]),
        "fold_axis_summaries": _freeze(
            matched_raw["bootstrap_contract"]["fold_axis_summaries"]
        ),
        "lineage_graph": _freeze(_lineage_graph(successor_raw)),
        "capabilities": _freeze(successor_raw["capabilities"]),
        "_authority": _LOADED_GLOBAL_BENCHMARK_AUTHORITY,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    fingerprint = _contract_fingerprint(value)
    sources = (
        (map_resolved, map_payload, "global rating map"),
        (matched_resolved, matched_payload, "matched comparison contract"),
        (successor_resolved, successor_payload, "stock successor"),
        (parent_resolved, parent_payload, "predecessor stock specification"),
        (fold_resolved, fold_payload, "existing fold manifest"),
        (qc_resolved, qc_payload, "QC-first plan"),
        (base_resolved, base_payload, "superseded QC-plan base"),
    )
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget_authority(key, ref))
    with _GLOBAL_BENCHMARK_AUTHORITIES_LOCK:
        _GLOBAL_BENCHMARK_AUTHORITIES[identity] = (reference, sources, fingerprint)
    return value


def require_loaded_global_benchmark_contract(
    contract: GlobalBenchmarkContract,
) -> GlobalBenchmarkContract:
    """Reauthenticate loader identity, immutable fields, and all source bytes."""
    if (
        type(contract) is not GlobalBenchmarkContract
        or getattr(contract, "_authority", None) is not _LOADED_GLOBAL_BENCHMARK_AUTHORITY
    ):
        raise GlobalBenchmarkContractError("global benchmark is not loader-authenticated")
    with _GLOBAL_BENCHMARK_AUTHORITIES_LOCK:
        authority = _GLOBAL_BENCHMARK_AUTHORITIES.get(id(contract))
    if authority is None or authority[0]() is not contract:
        raise GlobalBenchmarkContractError("global benchmark loader authority is absent")
    if _contract_fingerprint(contract) != authority[2]:
        raise GlobalBenchmarkContractError("global benchmark changed after authentication")
    for path, payload, name in authority[1]:
        _revalidate(path, payload, name)
    return contract


def resolve_global_rating(
    contract: GlobalBenchmarkContract, raw_label: object
) -> GlobalRatingMapping | GlobalRatingMappingRefusal:
    """Resolve one raw label under the approved naive comparator policy."""
    require_loaded_global_benchmark_contract(contract)
    if type(raw_label) is not str:
        return GlobalRatingMappingRefusal(
            raw_label,
            None,
            GlobalRatingRefusalReason.INVALID_TYPE,
            contract.map_id,
            contract.map_hash,
        )
    if not raw_label or len(raw_label) > 256:
        return GlobalRatingMappingRefusal(
            raw_label,
            None,
            GlobalRatingRefusalReason.EMPTY_OR_OVERLONG,
            contract.map_id,
            contract.map_hash,
        )
    if any(ord(character) < 0x20 or ord(character) > 0x7E for character in raw_label):
        return GlobalRatingMappingRefusal(
            raw_label,
            None,
            GlobalRatingRefusalReason.NON_PRINTABLE_ASCII,
            contract.map_id,
            contract.map_hash,
        )
    canonical = _canonicalize_policy_label(raw_label)
    if not canonical:
        return GlobalRatingMappingRefusal(
            raw_label,
            None,
            GlobalRatingRefusalReason.EMPTY_OR_OVERLONG,
            contract.map_id,
            contract.map_hash,
        )
    entry = next(
        (item for item in contract.entries if item.canonical_label == canonical), None
    )
    if entry is not None:
        return GlobalRatingMapping(
            raw_label,
            canonical,
            entry,
            contract.map_id,
            contract.map_hash,
        )
    reason = (
        GlobalRatingRefusalReason.MEASURED_REFUSAL
        if canonical in contract.measured_refusals
        else GlobalRatingRefusalReason.UNKNOWN_FUTURE_LABEL
    )
    return GlobalRatingMappingRefusal(
        raw_label,
        canonical,
        reason,
        contract.map_id,
        contract.map_hash,
    )


def global_rating_delta(
    contract: GlobalBenchmarkContract,
    previous: GlobalRatingMapping,
    current: GlobalRatingMapping,
) -> Fraction:
    """Return the exact current-minus-previous comparator delta."""
    require_loaded_global_benchmark_contract(contract)
    trusted_previous = _require_authentic_mapping(contract, previous)
    trusted_current = _require_authentic_mapping(contract, current)
    return trusted_current.score - trusted_previous.score


def _require_authentic_mapping(
    contract: GlobalBenchmarkContract,
    mapping: GlobalRatingMapping,
) -> GlobalRatingMapping:
    if type(mapping) is not GlobalRatingMapping:
        raise GlobalBenchmarkContractError("global rating delta requires two mappings")
    entry = mapping.entry
    if (
        type(mapping.raw_label) is not str
        or type(mapping.canonical_label) is not str
        or type(mapping.map_id) is not str
        or type(mapping.map_hash) is not str
        or type(entry) is not GlobalRatingMapEntry
        or type(entry.canonical_label) is not str
        or type(entry.legacy_level) is not int
        or type(entry.score_numerator) is not int
        or type(entry.score_denominator) is not int
    ):
        raise GlobalBenchmarkContractError(
            "global rating mapping is not resolver-authentic"
        )
    trusted = resolve_global_rating(contract, mapping.raw_label)
    if type(trusted) is not GlobalRatingMapping:
        raise GlobalBenchmarkContractError(
            "global rating mapping is not resolver-authentic"
        )
    actual = (
        mapping.raw_label,
        mapping.canonical_label,
        mapping.map_id,
        mapping.map_hash,
        entry.canonical_label,
        entry.legacy_level,
        entry.score_numerator,
        entry.score_denominator,
    )
    expected = (
        trusted.raw_label,
        trusted.canonical_label,
        trusted.map_id,
        trusted.map_hash,
        trusted.entry.canonical_label,
        trusted.entry.legacy_level,
        trusted.entry.score_numerator,
        trusted.entry.score_denominator,
    )
    if actual != expected:
        raise GlobalBenchmarkContractError(
            "global rating mapping is not resolver-authentic"
        )
    return trusted


def classify_global_rating_transition(
    contract: GlobalBenchmarkContract,
    *,
    action: str,
    previous: GlobalRatingMapping,
    current: GlobalRatingMapping,
) -> GlobalRatingTransition:
    """Classify a firm-admitted event under the frozen legacy direction rule."""
    if type(action) is not str or action not in {"upgrade", "downgrade"}:
        raise GlobalBenchmarkContractError(
            "global rating transition action must be upgrade or downgrade"
        )
    require_loaded_global_benchmark_contract(contract)
    trusted_previous = _require_authentic_mapping(contract, previous)
    trusted_current = _require_authentic_mapping(contract, current)
    delta = trusted_current.score - trusted_previous.score
    if delta == 0:
        disposition = GlobalRatingTransitionDisposition.ACTIVE_TIER_COLLAPSE_ZERO
    elif (action == "upgrade" and delta > 0) or (
        action == "downgrade" and delta < 0
    ):
        disposition = GlobalRatingTransitionDisposition.ACTIVE_EXPECTED_DIRECTION
    else:
        disposition = (
            GlobalRatingTransitionDisposition.JOINT_DIRECTION_CONFLICT_REFUSAL
        )
    return GlobalRatingTransition(
        action,
        trusted_previous,
        trusted_current,
        delta,
        disposition,
    )


def coverage_meets_minimum(
    numerator: int,
    denominator: int,
) -> bool:
    """Apply an exact non-rounded coverage threshold by cross multiplication."""
    minimum_numerator = 19
    minimum_denominator = 20
    values = (numerator, denominator)
    if any(type(value) is not int for value in values):
        raise GlobalBenchmarkContractError("coverage counts must be exact integers")
    if (
        numerator < 0
        or denominator <= 0
        or numerator > denominator
    ):
        raise GlobalBenchmarkContractError("coverage counts are outside their domain")
    return numerator * minimum_denominator >= minimum_numerator * denominator


def bootstrap_seed_record(contract: GlobalBenchmarkContract) -> Mapping[str, str]:
    """Build the exact outcome-free sampler seed record for later authorized use."""
    require_loaded_global_benchmark_contract(contract)
    return MappingProxyType(
        {
            "domain": SAMPLER_DOMAIN,
            "successor_stock_spec_sha256": contract.successor_spec_hash,
            "matched_row_contract_sha256": contract.matched_contract_hash,
            "global_rating_map_sha256": contract.map_hash,
            "fold_manifest_sha256": FOLD_MANIFEST_HASH,
            "evaluation_id": contract.evaluation_id,
            "sampler_version": "v1",
        }
    )


def _require_uint64(value: object, name: str) -> int:
    if type(value) is not int or value < 0 or value > (1 << 64) - 1:
        raise GlobalBenchmarkContractError(f"{name} must be an exact uint64")
    return value


def _unbiased_index(words: Iterable[int], modulus: int) -> int:
    if type(modulus) is not int or modulus <= 0 or modulus > (1 << 256):
        raise GlobalBenchmarkContractError("start-count modulus is invalid")
    ceiling = 1 << 256
    limit = ceiling - (ceiling % modulus)
    for word in words:
        if type(word) is not int or word < 0 or word >= ceiling:
            raise GlobalBenchmarkContractError("hash-counter word is invalid")
        if word < limit:
            return word % modulus
    raise GlobalBenchmarkContractError("hash-counter rejection counter overflow")


def hash_counter_start_index(
    contract: GlobalBenchmarkContract,
    *,
    resample_ordinal: int,
    fold_ordinal: int,
    block_ordinal: int,
) -> int:
    """Select one unbiased noncircular block start without runtime RNG state.

    This freezes only the structural start selector. It cannot consume paired
    differences or produce a bootstrap statistic or result disposition.
    """
    require_loaded_global_benchmark_contract(contract)
    resample = _require_uint64(resample_ordinal, "resample_ordinal")
    fold = _require_uint64(fold_ordinal, "fold_ordinal")
    block = _require_uint64(block_ordinal, "block_ordinal")
    if resample >= 19999:
        raise GlobalBenchmarkContractError("resample_ordinal is outside the frozen run")
    if fold >= len(contract.fold_axis_summaries):
        raise GlobalBenchmarkContractError("fold_ordinal is outside the frozen folds")
    fold_summary = contract.fold_axis_summaries[fold]
    if block >= fold_summary["blocks_drawn"]:
        raise GlobalBenchmarkContractError("block_ordinal is outside the frozen fold draw")
    start_count = fold_summary["allowed_start_count"]
    seed_bytes = _canonical(dict(bootstrap_seed_record(contract))) + b"\n"
    seed_digest = hashlib.sha256(seed_bytes).digest()

    def words() -> Iterable[int]:
        for rejection in range(1 << 64):
            preimage = (
                SAMPLER_DOMAIN.encode("utf-8")
                + b"\x00"
                + seed_digest
                + resample.to_bytes(8, "big")
                + fold.to_bytes(8, "big")
                + block.to_bytes(8, "big")
                + rejection.to_bytes(8, "big")
            )
            word_bytes = hashlib.sha256(preimage).digest()
            if type(word_bytes) is not bytes or len(word_bytes) != 32:
                raise GlobalBenchmarkContractError("digest must return exactly 32 bytes")
            yield int.from_bytes(word_bytes, "big", signed=False)

    return _unbiased_index(words(), start_count)


def render_expected_artifact(name: str) -> str:
    """Render one review artifact; intentionally grants no persistence authority."""
    documents = {
        "map": _map_document(),
        "matched": _matched_document(),
        "successor": _successor_document(),
    }
    if name not in documents:
        raise GlobalBenchmarkContractError("unknown review artifact name")
    return _render(documents[name]).decode("utf-8")
