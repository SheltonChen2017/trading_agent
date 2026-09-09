"""Outcome-free post-pandemic evaluation supplement for Analyst Revisions V2.

This additive preregistration selects the complete 2021--2025 folds from the
already accepted stock walk-forward manifest: H20 is the sole primary
sensitivity statistic and H1/H5/H60 remain secondary descriptive horizons.
It neither replaces the 2020--2025 primary evaluation nor grants access to
sources, outcomes, QuantConnect, results, deployment, orders, or trading.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import weakref
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from data.exchange_calendar import (
    ExchangeCalendarError,
    is_trading_session,
    resolve_nth_session_after,
    trading_sessions,
)

from .fold_manifest import (
    StockFoldManifest,
    StockFoldManifestError,
    load_stock_fold_manifest,
    require_loaded_stock_fold_manifest,
)
from .qc_first_plan import SUPERSESSION_POLICY
from .artifact_io import (
    ArtifactIOError,
    read_stable_regular as _read_artifact_stable_regular,
    revalidate_regular as _revalidate_artifact_regular,
)


class PostPandemicEvaluationPlanError(ValueError):
    """The post-pandemic supplement is malformed, weakened, or unauthentic."""


SCHEMA = "arv2-stock-post-pandemic-evaluation-structural-v1"
STATUS = "outcome_free_preregistration_candidate_pending_independent_review"
AUTHORITY = "structural_supplement_only_no_data_outcome_qc_or_action_authority"
PLAN_ID_PREFIX = "arv2-stock-post-pandemic-"
MAX_ARTIFACT_BYTES = 128 * 1024

PARENT_FOLD_MANIFEST_ID = "arv2-stock-folds-1002155dbe8e3e87"
PARENT_FOLD_MANIFEST_HASH = (
    "1002155dbe8e3e87b220b7419039bff95f5c0812d2306c56a8ac51b76c5d7611"
)
PARENT_FOLD_MANIFEST_ARTIFACT_SHA256 = (
    "fecd984ad937fed57b860b15fdcb9cc994ff59ab62c3b72d5160ab62b342953c"
)
PARENT_PLAN_ID = "arv2-qc-first-plan-36e455e72b8750fe"
PARENT_PLAN_HASH = (
    "36e455e72b8750fe3f34773382870e10e62f3f40b5392ae587690bda081b85dc"
)
PARENT_PLAN_ARTIFACT_SHA256 = (
    "8339238dd5ce32ed7b351aab2662fb408cc7d9a3c62ff89bf8b1d14f20acd081"
)
PARENT_STOCK_SPEC_ID = "arv2-stock-historical-c5ff2a6a0dcf341e"
PARENT_STOCK_SPEC_HASH = (
    "c5ff2a6a0dcf341e3c7bad4ea56e4a3c00f20faab5896c0fcd3bd7c291835a0b"
)
PARENT_STOCK_SPEC_ARTIFACT_SHA256 = (
    "34d1e71548bc6850a02590596594944dad3fadb38954067f2cc2d00dcaa86bc8"
)
PARENT_HISTORY_SECTION_SHA256 = (
    "5db2a1bc09d7ecd2e8cb7e5044f0abc7f97b3eefb71803002d00f6b33cf984ca"
)
STRATEGY_PDF_SHA256 = (
    "eae7b9954aaf94212108505c52e31a558facd744967fd2526040d5147c616193"
)
PRIMARY_EVALUATION_ID = "arv2-eval-stock-historical-qc-001"

PRIMARY_ORDERED_FOLD_IDS = tuple(
    f"arv2-wf-test-{year}" for year in range(2020, 2026)
)
SELECTED_COMPLETE_H20_FOLDS = (
    {
        "test_year": 2021,
        "parent_fold_id": "arv2-wf-test-2021",
        "parent_fold_sha256": (
            "5d39393886380681e2f271e44c0dd638ee494202829a6830a5f693fb8c956a64"
        ),
        "h20_fold_id": "arv2-wf-test-2021-h20",
        "h20_structural_fold_sha256": (
            "08100307b01071fe1689e3a8414532bc7ca1f6210a1b4520b22850f658402060"
        ),
        "test_start": "2021-02-02",
        "test_end_exclusive": "2022-01-03",
    },
    {
        "test_year": 2022,
        "parent_fold_id": "arv2-wf-test-2022",
        "parent_fold_sha256": (
            "5f56a7215fa78cde28cdbee25e867ffce4ab567474bf4b907106effb631f3031"
        ),
        "h20_fold_id": "arv2-wf-test-2022-h20",
        "h20_structural_fold_sha256": (
            "663aaf425cb29796530ae830381cd38f36fbc851e98e6a4abcc7c70883bc0039"
        ),
        "test_start": "2022-02-01",
        "test_end_exclusive": "2023-01-03",
    },
    {
        "test_year": 2023,
        "parent_fold_id": "arv2-wf-test-2023",
        "parent_fold_sha256": (
            "ebed6de3e92880546ddc892438ccbcb4c017296df3a431708b23d25e71ac9b3e"
        ),
        "h20_fold_id": "arv2-wf-test-2023-h20",
        "h20_structural_fold_sha256": (
            "f7652b53db085b949f3019c2b94be90f912df3a24ea79fda08b58c228638a4f3"
        ),
        "test_start": "2023-02-01",
        "test_end_exclusive": "2024-01-02",
    },
    {
        "test_year": 2024,
        "parent_fold_id": "arv2-wf-test-2024",
        "parent_fold_sha256": (
            "9570dd6708c299df0253ea6b2326d6ab866f29f115476ed445f018e4ac398d3e"
        ),
        "h20_fold_id": "arv2-wf-test-2024-h20",
        "h20_structural_fold_sha256": (
            "51b55a161641747d6ee7de7bb4d81efe3983e71596d6136a8428c8da47754852"
        ),
        "test_start": "2024-01-31",
        "test_end_exclusive": "2025-01-02",
    },
    {
        "test_year": 2025,
        "parent_fold_id": "arv2-wf-test-2025",
        "parent_fold_sha256": (
            "0bca0526decc6b15274fe09c374d8b72e72386058700bd6384fb14872177130f"
        ),
        "h20_fold_id": "arv2-wf-test-2025-h20",
        "h20_structural_fold_sha256": (
            "65eb4913bc9f75ede4123a08a810de3666342b60521d2800e920e91fcb49c030"
        ),
        "test_start": "2025-02-03",
        "test_end_exclusive": "2026-01-02",
    },
)
LAST_MATURE_DECISION_BY_HORIZON = {
    "1": "2026-08-27",
    "5": "2026-08-21",
    "20": "2026-07-31",
    "60": "2026-06-03",
}
PARTIAL_2026_BOUNDARY_DEFINITIONS = (
    {
        "horizon_sessions": 1,
        "purge_sessions": 1,
        "embargo_sessions": 1,
        "train_start": "2019-01-02",
        "train_end_exclusive": "2024-01-02",
        "validation_start": "2024-01-03",
        "validation_end_exclusive": "2026-01-02",
        "effective_test_start": "2026-01-05",
        "last_mature_decision_session": "2026-08-27",
        "test_end_exclusive": "2026-08-28",
        "eligible_decision_session_count": 163,
    },
    {
        "horizon_sessions": 5,
        "purge_sessions": 5,
        "embargo_sessions": 5,
        "train_start": "2019-01-02",
        "train_end_exclusive": "2024-01-02",
        "validation_start": "2024-01-09",
        "validation_end_exclusive": "2026-01-02",
        "effective_test_start": "2026-01-09",
        "last_mature_decision_session": "2026-08-21",
        "test_end_exclusive": "2026-08-24",
        "eligible_decision_session_count": 155,
    },
    {
        "horizon_sessions": 20,
        "purge_sessions": 20,
        "embargo_sessions": 20,
        "train_start": "2019-01-02",
        "train_end_exclusive": "2024-01-02",
        "validation_start": "2024-01-31",
        "validation_end_exclusive": "2026-01-02",
        "effective_test_start": "2026-02-02",
        "last_mature_decision_session": "2026-07-31",
        "test_end_exclusive": "2026-08-03",
        "eligible_decision_session_count": 125,
    },
    {
        "horizon_sessions": 60,
        "purge_sessions": 60,
        "embargo_sessions": 60,
        "train_start": "2019-01-02",
        "train_end_exclusive": "2024-01-02",
        "validation_start": "2024-03-28",
        "validation_end_exclusive": "2026-01-02",
        "effective_test_start": "2026-03-31",
        "last_mature_decision_session": "2026-06-03",
        "test_end_exclusive": "2026-06-04",
        "eligible_decision_session_count": 45,
    },
)

EXTERNAL_BINDINGS = {
    "review_commit": None,
    "counter_review_commit": None,
    "source_rights_receipt_id": None,
    "source_snapshot_id": None,
    "normalized_dataset_id": None,
    "outcome_dataset_id": None,
    "terminal_return_dataset_id": None,
    "qc_project_id": None,
    "qc_upload_receipt_id": None,
    "qc_compile_id": None,
    "qc_run_id": None,
    "evaluation_receipt_id": None,
    "result_record_id": None,
    "deployment_id": None,
    "order_id": None,
}

CAPABILITIES = {
    "source_access": False,
    "outcome_access": False,
    "qc_upload": False,
    "qc_compile": False,
    "qc_launch": False,
    "result_read": False,
    "result_disposition": False,
    "paper_deployment": False,
    "funded_deployment": False,
    "orders": False,
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


SELECTED_COMPLETE_H20_FOLDS = _freeze(SELECTED_COMPLETE_H20_FOLDS)
LAST_MATURE_DECISION_BY_HORIZON = _freeze(LAST_MATURE_DECISION_BY_HORIZON)
PARTIAL_2026_BOUNDARY_DEFINITIONS = _freeze(
    PARTIAL_2026_BOUNDARY_DEFINITIONS
)
EXTERNAL_BINDINGS = _freeze(EXTERNAL_BINDINGS)
CAPABILITIES = _freeze(CAPABILITIES)


def _primary_evaluation_contract() -> dict[str, object]:
    return {
        "evaluation_id": PRIMARY_EVALUATION_ID,
        "role": "formal_primary_evaluation_unchanged_by_this_supplement",
        "ordered_complete_fold_ids": list(PRIMARY_ORDERED_FOLD_IDS),
        "ordered_horizons_sessions": [1, 5, 20, 60],
        "primary_interval": "complete_2020_through_2025_parent_folds",
        "replacement_or_reselection": False,
        "current_execution_authorized": False,
    }


def _naming_contract() -> dict[str, object]:
    return {
        "label": "post_pandemic",
        "interpretation": "owner_shorthand_for_fixed_2021_through_2026_market_slice",
        "epidemiological_regime_claim": False,
        "dynamic_rolling_now_boundary": False,
    }


def _owner_partial_2026_amendment_contract() -> dict[str, object]:
    return {
        "owner_direction_date": "2026-09-08",
        "owner_direction": (
            "start_fixed_2021_2026_post_pandemic_slice_after_counter_review"
        ),
        "parent_fold_clause": (
            "excluded_from_fixed_cutoff_evaluation_locked_no_blind_extension"
        ),
        "parent_stock_clause": (
            "exclude_from_test_fold_until_full_test_interval_exists"
        ),
        "formal_primary_parent_clauses_remain_unchanged": True,
        "parent_artifacts_remain_byte_unchanged": True,
        "semantic_override_of_parent_partial_exclusion": True,
        "semantic_override_scope": (
            "separate_non_fold_exploratory_fixed_cutoff_slice_only"
        ),
        "rewrites_parent_fold_manifest": False,
        "promotes_partial_slice_to_parent_fold": False,
        "grants_outcome_or_execution_authority": False,
    }


def _inherited_evaluation_rules_contract() -> dict[str, object]:
    return {
        "applies_to": "complete_2021_2025_and_separate_partial_2026_reporting",
        "source": "exact_authenticated_parent_stock_fold_and_QC_first_artifacts",
        "first_selected_2021_fold_uses_pre_2021_train_and_validation_inputs": True,
        "historical_point_in_time_inputs_remain_required": True,
        "post_pandemic_slice_waives_historical_point_in_time_requirements": False,
        "inherited_without_local_override": [
            "point_in_time_universe",
            "controls_and_residualization",
            "firm_specific_global_comparator",
            "costs",
            "metrics",
            "inference",
            "common_event_boundary_refusal",
            "contamination_rules",
        ],
        "local_override_permitted": False,
        "evidence_role": "development_stop_go_not_prospective_confirmation",
        "contamination_disclosure": (
            "2019-07-16_through_2026-07-23_is_discovery_only_all_historical_"
            "inference_is_descriptive"
        ),
        "post_pandemic_results_are_descriptive": True,
        "confirmatory_or_prospective_claim_permitted": False,
    }


def _power_and_sufficiency_reporting_contract() -> dict[str, object]:
    return {
        "applies_to": "complete_2021_2025_slice_and_partial_2026_separately",
        "power_floor_receipt_id": None,
        "required_independent_date_floor": None,
        "required_connected_component_floor": None,
        "current_claim_to_meet_ARV2_4D_power_date_or_component_floors": False,
        "required_floor_source": (
            "separately_authenticated_ARV2_4D_numeric_receipt_before_result_reporting"
        ),
        "each_report_required_fields": [
            "evaluation_id",
            "report_slice_id",
            "horizon_sessions",
            "independent_observation_unit",
            "observed_independent_date_count",
            "required_independent_date_count",
            "observed_connected_component_count",
            "required_connected_component_count",
            "sufficient",
            "insufficiency_reasons",
        ],
        "missing_required_floor_disposition": "insufficient_unavailable_never_infer",
        "creates_new_gate_rescue_or_selection_authority": False,
    }


def _post_pandemic_complete_contract() -> dict[str, object]:
    return {
        "role": "supplemental_calendar_selected_sensitivity_never_primary_or_rescue",
        "selection_rule": "complete_parent_folds_with_test_year_2021_through_2025",
        "implementation_outcome_rows_accessed": False,
        "selection_claimed_blind_to_market_outcomes": False,
        "selection_basis": (
            "owner_directed_calendar_regime_sensitivity_before_this_run"
        ),
        "primary_sensitivity_horizon_sessions": 20,
        "secondary_descriptive_horizons_sessions": [1, 5, 60],
        "parent_horizon_order_sessions": [1, 5, 20, 60],
        "secondary_descriptive_selection_rule": (
            "for_each_selected_parent_fold_use_its_exact_authenticated_parent_"
            "boundary_for_each_ordered_secondary_horizon"
        ),
        "ordered_parent_fold_ids": [
            item["parent_fold_id"] for item in SELECTED_COMPLETE_H20_FOLDS
        ],
        "ordered_h20_fold_ids": [
            item["h20_fold_id"] for item in SELECTED_COMPLETE_H20_FOLDS
        ],
        "selected_complete_h20_folds": [
            _thaw(item) for item in SELECTED_COMPLETE_H20_FOLDS
        ],
        "complete_fold_aggregation_contract": {
            "mode": (
                "descriptive_calendar_ordered_oos_concatenation_of_disjoint_"
                "complete_2021_2025_test_folds_only"
            ),
            "ordered_parent_fold_ids": [
                item["parent_fold_id"] for item in SELECTED_COMPLETE_H20_FOLDS
            ],
            "observation_interval_rule": (
                "for_each_horizon_use_only_exact_authenticated_parent_boundary_"
                "test_start_through_test_end_exclusive"
            ),
            "per_fold_and_calendar_year_reporting_required": True,
            "partial_2026_included": False,
            "aggregate_outputs": "descriptive_metrics_and_equity_curve_only",
            "pooled_inferential_p_value_or_gate_permitted": False,
            "gate_rescue_tuning_or_threshold_selection_permitted": False,
            "valid_structural_no_position_return": "follow_exact_parent_semantics",
            "refusal_underfill_or_missing_expected_session": (
                "retain_every_expected_session_and_refusal_in_census_and_coverage_"
                "never_silently_drop_skip_or_zero_fill_metric_denominator_"
                "exclusion_only_under_exact_parent_named_refusal_rule"
            ),
            "aggregate_completeness_and_coverage_report_required": True,
            "incomplete_aggregate_disposition": (
                "follow_exact_parent_completeness_refusal_gate_if_any_required_"
                "parent_observation_invalidates_fold_or_horizon_aggregate_is_"
                "unavailable"
            ),
            "unique_session_and_outcome_identity_required": True,
            "portfolio_return_fold_initial_and_terminal_costs_included": True,
            "fold_state_resets_disclosed": True,
            "capital_path_interpretation": "not_uninterrupted_live_capital",
        },
        "cross_horizon_pooling": "forbidden_report_each_horizon_separately",
        "primary_result_rescue": "forbidden",
        "secondary_result_rescue": "forbidden",
        "threshold_model_or_universe_tuning": "forbidden",
        "failed_fold_retries": "forbidden_owner_disposition_required",
        "current_execution_authorized": False,
    }


def _partial_2026_contract() -> dict[str, object]:
    boundaries = []
    for definition in PARTIAL_2026_BOUNDARY_DEFINITIONS:
        boundary = _thaw(definition)
        boundary["boundary_sha256"] = None
        boundary["boundary_sha256"] = hashlib.sha256(_canonical(boundary)).hexdigest()
        boundaries.append(boundary)
    partial: dict[str, object] = {
        "role": "separate_exploratory_incomplete_calendar_period_only",
        "classification": "exploratory_nonconfirmatory_not_a_complete_walk_forward_fold",
        "calendar_year": 2026,
        "rolling_or_expanding_rule": "rolling",
        "interval_semantics": "half_open_nyse_session_intervals",
        "nominal_train_interval": {
            "start_inclusive": "2019-01-02",
            "end_exclusive": "2024-01-02",
        },
        "nominal_validation_interval": {
            "start_inclusive": "2024-01-02",
            "end_exclusive": "2026-01-02",
        },
        "nominal_test_start_session": "2026-01-02",
        "effective_test_start_rule": (
            "horizon_sessions_after_nominal_start_matching_parent_embargo_semantics"
        ),
        "outcome_cutoff_session": "2026-08-28",
        "ordered_horizons_sessions": [1, 5, 20, 60],
        "last_mature_decision_session_by_horizon": dict(
            LAST_MATURE_DECISION_BY_HORIZON
        ),
        "boundary_set_sha256": hashlib.sha256(_canonical(boundaries)).hexdigest(),
        "eligible_decision_bounds": boundaries,
        "partial_window_sha256": None,
        "fit_contract": {
            "fit_scope": "training_only",
            "validation_application": "frozen_coefficients_model_and_thresholds",
            "test_application": "frozen_coefficients_model_and_thresholds",
            "validation_or_test_refit": False,
        },
        "common_event_boundary_refusal": "inherited_exactly_from_parent_manifest",
        "fold_id": None,
        "result_binding_id": None,
        "pool_with_complete_folds": False,
        "pool_with_primary_evaluation": False,
        "rescue_or_override_any_gate": False,
        "tune_or_select_from_partial_results": False,
        "blind_extension_to_later_outcomes": False,
        "later_decisions": "named_immature_refusals_never_dropped_or_filled",
        "future_completion": "requires_new_content_addressed_reviewed_supplement",
        "current_execution_authorized": False,
    }
    partial["partial_window_sha256"] = hashlib.sha256(_canonical(partial)).hexdigest()
    return partial


def _fixed_cutoff_lock_contract() -> dict[str, object]:
    return {
        "outcome_cutoff_session": "2026-08-28",
        "first_post_cutoff_session": "2026-08-31",
        "post_cutoff_data_disposition": "outside_this_supplement_no_access",
        "blind_extension": False,
        "dynamic_rolling_now_boundary": False,
        "later_use_requires_new_content_addressed_reviewed_authority": True,
    }


def _future_shared_holdout_contract() -> dict[str, object]:
    return {
        "scope": "shared_final_holdout_across_all_four_canonical_strategy_families",
        "consumption_by_this_lane_prohibited": True,
        "legacy_validation_period_start_inclusive": "2026-09-01",
        "legacy_validation_period_end_inclusive": "2027-08-31",
        "legacy_validation_period_prior_state": "planned_unbound",
        "legacy_validation_period_disposition": (
            "superseded_unspent_by_owner_qc_first_direction"
        ),
        "legacy_validation_period_looks_consumed": 0,
        "legacy_validation_period_revivable_by_this_supplement": False,
        "future_paper_period_start_inclusive": None,
        "future_paper_period_end_inclusive": None,
        "future_paper_period_authority_id": None,
        "shared_final_holdout_cutoff_inclusive": "2027-08-31",
        "shared_final_holdout_start_inclusive": "2027-09-01",
        "shared_final_holdout_end_inclusive": "2029-08-31",
        "consumed_by_this_supplement": False,
        "pool_with_historical_or_partial_results": False,
        "prospective_epoch_and_separate_review_required": True,
        "current_access_authorized": False,
    }


def _content_payload(raw: Mapping[str, Any]) -> bytes:
    payload = dict(raw)
    payload["plan_id"] = None
    payload["plan_hash"] = None
    return _canonical(payload)


def _expected_document() -> dict[str, object]:
    sections = {
        "naming_contract": _naming_contract(),
        "owner_partial_2026_amendment_contract": (
            _owner_partial_2026_amendment_contract()
        ),
        "inherited_evaluation_rules_contract": (
            _inherited_evaluation_rules_contract()
        ),
        "power_and_sufficiency_reporting_contract": (
            _power_and_sufficiency_reporting_contract()
        ),
        "primary_evaluation_contract": _primary_evaluation_contract(),
        "post_pandemic_complete_contract": _post_pandemic_complete_contract(),
        "partial_2026_exploratory_contract": _partial_2026_contract(),
        "fixed_cutoff_lock_contract": _fixed_cutoff_lock_contract(),
        "future_shared_holdout_contract": _future_shared_holdout_contract(),
    }
    raw: dict[str, object] = {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "plan_id": None,
        "plan_hash": None,
        "parent_fold_manifest": {
            "artifact_id": PARENT_FOLD_MANIFEST_ID,
            "content_sha256": PARENT_FOLD_MANIFEST_HASH,
            "artifact_sha256": PARENT_FOLD_MANIFEST_ARTIFACT_SHA256,
        },
        "parent_lineages": {
            "strategy_pdf_sha256": STRATEGY_PDF_SHA256,
            "qc_first_plan": {
                "artifact_id": PARENT_PLAN_ID,
                "content_sha256": PARENT_PLAN_HASH,
                "artifact_sha256": PARENT_PLAN_ARTIFACT_SHA256,
            },
            "stock_evaluation_contract": {
                "artifact_id": PARENT_STOCK_SPEC_ID,
                "content_sha256": PARENT_STOCK_SPEC_HASH,
                "artifact_sha256": PARENT_STOCK_SPEC_ARTIFACT_SHA256,
                "history_section_sha256": PARENT_HISTORY_SECTION_SHA256,
            },
            "evaluation_id": PRIMARY_EVALUATION_ID,
        },
        **sections,
        "section_hashes": {
            name: hashlib.sha256(_canonical(value)).hexdigest()
            for name, value in sections.items()
        },
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
    }
    digest = hashlib.sha256(_content_payload(raw)).hexdigest()
    raw["plan_hash"] = digest
    raw["plan_id"] = f"{PLAN_ID_PREFIX}{digest[:16]}"
    return raw


_SECTION_NAMES = (
    "naming_contract",
    "owner_partial_2026_amendment_contract",
    "inherited_evaluation_rules_contract",
    "power_and_sufficiency_reporting_contract",
    "primary_evaluation_contract",
    "post_pandemic_complete_contract",
    "partial_2026_exploratory_contract",
    "fixed_cutoff_lock_contract",
    "future_shared_holdout_contract",
)
_EXPECTED_DOCUMENT = _freeze(_expected_document())
_ROOT_KEYS = frozenset(_EXPECTED_DOCUMENT)


def _reject_float(value: str) -> None:
    raise PostPandemicEvaluationPlanError(
        f"binary floating-point is forbidden: {value}"
    )


def _reject_constant(value: str) -> None:
    raise PostPandemicEvaluationPlanError(f"non-finite JSON is forbidden: {value}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PostPandemicEvaluationPlanError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_stable_regular(path: Path, name: str) -> tuple[Path, bytes]:
    try:
        return _read_artifact_stable_regular(
            Path(path), name=name, maximum_bytes=MAX_ARTIFACT_BYTES
        )
    except ArtifactIOError as exc:
        raise PostPandemicEvaluationPlanError(str(exc)) from exc


def _revalidate(path: Path, payload: bytes, name: str) -> None:
    try:
        _revalidate_artifact_regular(
            path, payload, name=name, maximum_bytes=MAX_ARTIFACT_BYTES
        )
    except ArtifactIOError as exc:
        raise PostPandemicEvaluationPlanError(str(exc)) from exc


def _require_exact(actual: object, expected: object, name: str) -> None:
    if isinstance(expected, Mapping):
        if type(actual) is not dict or set(actual) != set(expected):
            raise PostPandemicEvaluationPlanError(
                f"{name} changed from the frozen definition"
            )
        for key, value in expected.items():
            _require_exact(actual[key], value, f"{name}.{key}")
        return
    if type(expected) is tuple:
        if type(actual) is not list or len(actual) != len(expected):
            raise PostPandemicEvaluationPlanError(
                f"{name} changed from the frozen definition"
            )
        for index, (item, value) in enumerate(zip(actual, expected, strict=True)):
            _require_exact(item, value, f"{name}[{index}]")
        return
    if type(actual) is not type(expected) or actual != expected:
        raise PostPandemicEvaluationPlanError(
            f"{name} changed from the frozen definition"
        )


def _parent_h20_record(fold: Mapping[str, Any]) -> dict[str, object]:
    matches = tuple(
        item
        for item in fold["horizon_boundaries"]
        if item["horizon_sessions"] == 20
    )
    if len(matches) != 1:
        raise PostPandemicEvaluationPlanError(
            "parent fold does not contain exactly one H20 boundary"
        )
    boundary = matches[0]
    return {
        "test_year": fold["test_year"],
        "parent_fold_id": fold["fold_id"],
        "parent_fold_sha256": fold["fold_sha256"],
        "h20_fold_id": boundary["fold_id"],
        "h20_structural_fold_sha256": boundary["structural_fold_sha256"],
        "test_start": boundary["test_start"],
        "test_end_exclusive": boundary["test_end_exclusive"],
    }


def _validate_parent_and_semantics(
    raw: Mapping[str, Any], parent: StockFoldManifest
) -> None:
    if (
        parent.manifest_id != PARENT_FOLD_MANIFEST_ID
        or parent.manifest_hash != PARENT_FOLD_MANIFEST_HASH
        or parent.parent_plan_id != PARENT_PLAN_ID
        or parent.parent_plan_hash != PARENT_PLAN_HASH
        or parent.parent_plan_artifact_sha256 != PARENT_PLAN_ARTIFACT_SHA256
        or parent.parent_stock_spec_id != PARENT_STOCK_SPEC_ID
        or parent.parent_stock_spec_hash != PARENT_STOCK_SPEC_HASH
        or parent.parent_stock_spec_artifact_sha256
        != PARENT_STOCK_SPEC_ARTIFACT_SHA256
        or parent.parent_history_section_sha256 != PARENT_HISTORY_SECTION_SHA256
        or parent.strategy_pdf_sha256 != STRATEGY_PDF_SHA256
        or parent.evaluation_id != PRIMARY_EVALUATION_ID
    ):
        raise PostPandemicEvaluationPlanError("parent fold lineage changed")

    parent_folds = parent.walk_forward_contract["folds"]
    if parent.walk_forward_contract["partial_2026_disposition"] != (
        "excluded_from_fixed_cutoff_evaluation_locked_no_blind_extension"
    ):
        raise PostPandemicEvaluationPlanError(
            "parent partial-2026 exclusion clause changed"
        )
    amendment = raw["owner_partial_2026_amendment_contract"]
    if (
        amendment["parent_fold_clause"]
        != parent.walk_forward_contract["partial_2026_disposition"]
        or amendment["formal_primary_parent_clauses_remain_unchanged"] is not True
        or amendment["parent_artifacts_remain_byte_unchanged"] is not True
        or amendment["semantic_override_of_parent_partial_exclusion"] is not True
        or amendment["rewrites_parent_fold_manifest"] is not False
        or amendment["promotes_partial_slice_to_parent_fold"] is not False
        or amendment["grants_outcome_or_execution_authority"] is not False
    ):
        raise PostPandemicEvaluationPlanError(
            "partial-2026 owner amendment changed parent scope"
        )
    parent_ids = tuple(item["fold_id"] for item in parent_folds)
    if parent_ids != PRIMARY_ORDERED_FOLD_IDS:
        raise PostPandemicEvaluationPlanError("parent primary fold order changed")
    primary = raw["primary_evaluation_contract"]
    if tuple(primary["ordered_complete_fold_ids"]) != parent_ids:
        raise PostPandemicEvaluationPlanError(
            "supplement changed the primary evaluation"
        )

    by_year = {item["test_year"]: item for item in parent_folds}
    for year in range(2021, 2026):
        if tuple(
            item["horizon_sessions"]
            for item in by_year[year]["horizon_boundaries"]
        ) != (1, 5, 20, 60):
            raise PostPandemicEvaluationPlanError(
                "selected parent horizon order changed"
            )
    selected = tuple(
        _parent_h20_record(by_year[year]) for year in range(2021, 2026)
    )
    if selected != tuple(
        _thaw(item)
        for item in raw["post_pandemic_complete_contract"][
            "selected_complete_h20_folds"
        ]
    ):
        raise PostPandemicEvaluationPlanError(
            "post-pandemic H20 fold selection changed"
        )
    prior_end: str | None = None
    for item in selected:
        if prior_end is not None and item["test_start"] < prior_end:
            raise PostPandemicEvaluationPlanError(
                "post-pandemic complete H20 folds overlap"
            )
        prior_end = item["test_end_exclusive"]
    aggregation = raw["post_pandemic_complete_contract"][
        "complete_fold_aggregation_contract"
    ]
    complete = raw["post_pandemic_complete_contract"]
    if (
        tuple(aggregation["ordered_parent_fold_ids"])
        != tuple(item["parent_fold_id"] for item in selected)
        or aggregation["per_fold_and_calendar_year_reporting_required"] is not True
        or aggregation["observation_interval_rule"]
        != (
            "for_each_horizon_use_only_exact_authenticated_parent_boundary_"
            "test_start_through_test_end_exclusive"
        )
        or aggregation["partial_2026_included"] is not False
        or aggregation["pooled_inferential_p_value_or_gate_permitted"] is not False
        or aggregation["gate_rescue_tuning_or_threshold_selection_permitted"]
        is not False
        or aggregation["unique_session_and_outcome_identity_required"] is not True
        or aggregation[
            "portfolio_return_fold_initial_and_terminal_costs_included"
        ] is not True
        or aggregation["fold_state_resets_disclosed"] is not True
        or aggregation["refusal_underfill_or_missing_expected_session"]
        != (
            "retain_every_expected_session_and_refusal_in_census_and_coverage_"
            "never_silently_drop_skip_or_zero_fill_metric_denominator_"
            "exclusion_only_under_exact_parent_named_refusal_rule"
        )
        or aggregation["aggregate_completeness_and_coverage_report_required"]
        is not True
        or complete["implementation_outcome_rows_accessed"] is not False
        or complete["selection_claimed_blind_to_market_outcomes"] is not False
    ):
        raise PostPandemicEvaluationPlanError(
            "post-pandemic descriptive fold aggregation changed"
        )

    partial = raw["partial_2026_exploratory_contract"]
    if (
        partial["rolling_or_expanding_rule"] != "rolling"
        or partial["nominal_train_interval"]
        != {"start_inclusive": "2019-01-02", "end_exclusive": "2024-01-02"}
        or partial["nominal_validation_interval"]
        != {"start_inclusive": "2024-01-02", "end_exclusive": "2026-01-02"}
        or partial["fit_contract"]["fit_scope"] != "training_only"
        or partial["fit_contract"]["validation_or_test_refit"] is not False
        or partial["common_event_boundary_refusal"]
        != "inherited_exactly_from_parent_manifest"
    ):
        raise PostPandemicEvaluationPlanError(
            "partial-2026 rolling geometry or fit contract changed"
        )
    window_payload = dict(partial)
    declared_window_hash = window_payload["partial_window_sha256"]
    window_payload["partial_window_sha256"] = None
    if hashlib.sha256(_canonical(window_payload)).hexdigest() != declared_window_hash:
        raise PostPandemicEvaluationPlanError(
            "partial-2026 window content hash changed"
        )
    cutoff = partial["outcome_cutoff_session"]
    try:
        if not is_trading_session(cutoff):
            raise PostPandemicEvaluationPlanError(
                "partial-2026 outcome cutoff is not an XNYS session"
            )
        for horizon, decision in partial[
            "last_mature_decision_session_by_horizon"
        ].items():
            if not is_trading_session(decision):
                raise PostPandemicEvaluationPlanError(
                    "partial-2026 maturity boundary is not an XNYS session"
                )
            if resolve_nth_session_after(decision, int(horizon)) != cutoff:
                raise PostPandemicEvaluationPlanError(
                    "partial-2026 maturity boundary changed"
                )
        bounds = partial["eligible_decision_bounds"]
        if tuple(item["horizon_sessions"] for item in bounds) != (1, 5, 20, 60):
            raise PostPandemicEvaluationPlanError(
                "partial-2026 horizon order changed"
            )
        nominal_start = partial["nominal_test_start_session"]
        boundary_set_payload = []
        for item in bounds:
            horizon = item["horizon_sessions"]
            boundary_payload = dict(item)
            declared_boundary_hash = boundary_payload["boundary_sha256"]
            boundary_payload["boundary_sha256"] = None
            if (
                hashlib.sha256(_canonical(boundary_payload)).hexdigest()
                != declared_boundary_hash
            ):
                raise PostPandemicEvaluationPlanError(
                    "partial-2026 boundary content hash changed"
                )
            boundary_set_payload.append(dict(item))
            if (
                item["train_start"]
                != partial["nominal_train_interval"]["start_inclusive"]
                or item["train_end_exclusive"]
                != partial["nominal_train_interval"]["end_exclusive"]
                or item["validation_end_exclusive"]
                != partial["nominal_validation_interval"]["end_exclusive"]
                or item["purge_sessions"] != horizon
                or item["embargo_sessions"] != horizon
            ):
                raise PostPandemicEvaluationPlanError(
                    "partial-2026 purge or embargo changed"
                )
            validation_start = resolve_nth_session_after(
                item["train_end_exclusive"], horizon
            )
            start = resolve_nth_session_after(
                item["validation_end_exclusive"], horizon
            )
            end = item["last_mature_decision_session"]
            end_exclusive = resolve_nth_session_after(end, 1)
            count = len(
                trading_sessions(date.fromisoformat(start), date.fromisoformat(end))
            )
            if (
                validation_start != item["validation_start"]
                or start != item["effective_test_start"]
                or end
                != partial["last_mature_decision_session_by_horizon"][str(horizon)]
                or end_exclusive != item["test_end_exclusive"]
                or count != item["eligible_decision_session_count"]
            ):
                raise PostPandemicEvaluationPlanError(
                    "partial-2026 eligible decision bounds changed"
                )
        if (
            hashlib.sha256(_canonical(boundary_set_payload)).hexdigest()
            != partial["boundary_set_sha256"]
        ):
            raise PostPandemicEvaluationPlanError(
                "partial-2026 boundary-set content hash changed"
            )
        first_post_cutoff = resolve_nth_session_after(cutoff, 1)
    except ExchangeCalendarError as exc:
        raise PostPandemicEvaluationPlanError(
            "partial-2026 calendar semantics cannot be authenticated"
        ) from exc
    if (
        first_post_cutoff
        != raw["fixed_cutoff_lock_contract"][
            "first_post_cutoff_session"
        ]
    ):
        raise PostPandemicEvaluationPlanError(
            "fixed post-cutoff boundary changed"
        )
    holdout = raw["future_shared_holdout_contract"]
    if (
        holdout["legacy_validation_period_start_inclusive"]
        != SUPERSESSION_POLICY["legacy_period_start"]
        or holdout["legacy_validation_period_end_inclusive"]
        != SUPERSESSION_POLICY["legacy_period_end"]
        or holdout["legacy_validation_period_prior_state"]
        != SUPERSESSION_POLICY["legacy_state_at_supersession"]
        or holdout["legacy_validation_period_disposition"]
        != SUPERSESSION_POLICY["disposition"]
        or holdout["legacy_validation_period_looks_consumed"]
        != SUPERSESSION_POLICY["looks_consumed"]
        or holdout["legacy_validation_period_revivable_by_this_supplement"]
        is not False
        or holdout["shared_final_holdout_cutoff_inclusive"] != "2027-08-31"
        or holdout["shared_final_holdout_start_inclusive"] != "2027-09-01"
        or holdout["shared_final_holdout_end_inclusive"] != "2029-08-31"
        or holdout["consumption_by_this_lane_prohibited"] is not True
        or holdout["consumed_by_this_supplement"] is not False
        or holdout["current_access_authorized"] is not False
        or any(
            holdout[name] is not None
            for name in (
                "future_paper_period_start_inclusive",
                "future_paper_period_end_inclusive",
                "future_paper_period_authority_id",
            )
        )
    ):
        raise PostPandemicEvaluationPlanError(
            "superseded validation or future paper-period boundary changed"
        )
    inherited = raw["inherited_evaluation_rules_contract"]
    if (
        inherited["local_override_permitted"] is not False
        or inherited["evidence_role"]
        != "development_stop_go_not_prospective_confirmation"
        or inherited["contamination_disclosure"]
        != (
            "2019-07-16_through_2026-07-23_is_discovery_only_all_historical_"
            "inference_is_descriptive"
        )
        or inherited["confirmatory_or_prospective_claim_permitted"] is not False
    ):
        raise PostPandemicEvaluationPlanError(
            "inherited evidence role or contamination boundary changed"
        )
    power = raw["power_and_sufficiency_reporting_contract"]
    if (
        any(
            power[name] is not None
            for name in (
                "power_floor_receipt_id",
                "required_independent_date_floor",
                "required_connected_component_floor",
            )
        )
        or power[
            "current_claim_to_meet_ARV2_4D_power_date_or_component_floors"
        ]
        is not False
        or power["missing_required_floor_disposition"]
        != "insufficient_unavailable_never_infer"
        or power["creates_new_gate_rescue_or_selection_authority"] is not False
        or "independent_observation_unit"
        not in power["each_report_required_fields"]
    ):
        raise PostPandemicEvaluationPlanError(
            "power-floor or sufficiency-reporting authority changed"
        )


def _fingerprint_value(value: object) -> object:
    # Exact-type fingerprints: an equal-comparing subclass or a lying __eq__
    # must not reauthenticate, matching the B2/receipt/successor boundaries.
    if type(value) is MappingProxyType:
        if any(type(key) is not str for key in value):
            raise PostPandemicEvaluationPlanError(
                "post-pandemic plan authority state has a non-string key"
            )
        return (
            "mapping",
            tuple(
                (key, _fingerprint_value(item))
                for key, item in sorted(value.items())
            ),
        )
    if type(value) is tuple:
        return ("tuple", tuple(_fingerprint_value(item) for item in value))
    if type(value) in (str, bool, int) or value is None:
        return (type(value).__name__, value)
    raise PostPandemicEvaluationPlanError(
        "post-pandemic plan authority state is noncanonical"
    )


@dataclasses.dataclass(frozen=True, init=False)
class PostPandemicEvaluationPlan:
    """Immutable loader-authenticated outcome-free evaluation supplement."""

    schema: str
    status: str
    authority: str
    plan_id: str
    plan_hash: str
    parent_fold_manifest: Mapping[str, str]
    parent_lineages: Mapping[str, Any]
    naming_contract: Mapping[str, Any]
    owner_partial_2026_amendment_contract: Mapping[str, Any]
    inherited_evaluation_rules_contract: Mapping[str, Any]
    power_and_sufficiency_reporting_contract: Mapping[str, Any]
    primary_evaluation_contract: Mapping[str, Any]
    post_pandemic_complete_contract: Mapping[str, Any]
    partial_2026_exploratory_contract: Mapping[str, Any]
    fixed_cutoff_lock_contract: Mapping[str, Any]
    future_shared_holdout_contract: Mapping[str, Any]
    section_hashes: Mapping[str, str]
    external_bindings: Mapping[str, Any]
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
    def result_access_available(self) -> bool:
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


def _plan_fingerprint(plan: PostPandemicEvaluationPlan) -> tuple[object, ...]:
    return (
        _fingerprint_value(plan.schema),
        _fingerprint_value(plan.status),
        _fingerprint_value(plan.authority),
        _fingerprint_value(plan.plan_id),
        _fingerprint_value(plan.plan_hash),
        _fingerprint_value(plan.parent_fold_manifest),
        _fingerprint_value(plan.parent_lineages),
        _fingerprint_value(plan.naming_contract),
        _fingerprint_value(plan.owner_partial_2026_amendment_contract),
        _fingerprint_value(plan.inherited_evaluation_rules_contract),
        _fingerprint_value(plan.power_and_sufficiency_reporting_contract),
        _fingerprint_value(plan.primary_evaluation_contract),
        _fingerprint_value(plan.post_pandemic_complete_contract),
        _fingerprint_value(plan.partial_2026_exploratory_contract),
        _fingerprint_value(plan.fixed_cutoff_lock_contract),
        _fingerprint_value(plan.future_shared_holdout_contract),
        _fingerprint_value(plan.section_hashes),
        _fingerprint_value(plan.external_bindings),
        _fingerprint_value(plan.capabilities),
    )


_LOADED_POST_PANDEMIC_PLAN_AUTHORITY = object()
_POST_PANDEMIC_PLAN_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[PostPandemicEvaluationPlan],
        Path,
        Path,
        Path,
        Path,
        bytes,
        bytes,
        bytes,
        bytes,
        tuple[object, ...],
    ],
] = {}
_POST_PANDEMIC_PLAN_AUTHORITIES_LOCK = threading.RLock()


def _forget_loaded_plan(
    identity: int,
    reference: weakref.ReferenceType[PostPandemicEvaluationPlan],
) -> None:
    with _POST_PANDEMIC_PLAN_AUTHORITIES_LOCK:
        current = _POST_PANDEMIC_PLAN_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _POST_PANDEMIC_PLAN_AUTHORITIES.pop(identity, None)


def _loaded_plan(
    raw: Mapping[str, Any],
    *,
    source_path: Path,
    fold_manifest_path: Path,
    stock_evaluation_path: Path,
    qc_first_plan_path: Path,
    source_payload: bytes,
    fold_manifest_payload: bytes,
    stock_evaluation_payload: bytes,
    qc_first_plan_payload: bytes,
) -> PostPandemicEvaluationPlan:
    value = object.__new__(PostPandemicEvaluationPlan)
    fields = {
        name: (
            raw[name]
            if name in {"schema", "status", "authority", "plan_id", "plan_hash"}
            else _freeze(raw[name])
        )
        for name in (
            "schema",
            "status",
            "authority",
            "plan_id",
            "plan_hash",
            "parent_fold_manifest",
            "parent_lineages",
            "naming_contract",
            "owner_partial_2026_amendment_contract",
            "inherited_evaluation_rules_contract",
            "power_and_sufficiency_reporting_contract",
            "primary_evaluation_contract",
            "post_pandemic_complete_contract",
            "partial_2026_exploratory_contract",
            "fixed_cutoff_lock_contract",
            "future_shared_holdout_contract",
            "section_hashes",
            "external_bindings",
            "capabilities",
        )
    }
    fields["_authority"] = _LOADED_POST_PANDEMIC_PLAN_AUTHORITY
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    fingerprint = _plan_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(
        value,
        lambda ref, key=identity: _forget_loaded_plan(key, ref),
    )
    with _POST_PANDEMIC_PLAN_AUTHORITIES_LOCK:
        _POST_PANDEMIC_PLAN_AUTHORITIES[identity] = (
            reference,
            source_path,
            fold_manifest_path,
            stock_evaluation_path,
            qc_first_plan_path,
            source_payload,
            fold_manifest_payload,
            stock_evaluation_payload,
            qc_first_plan_payload,
            fingerprint,
        )
    return value


def require_loaded_post_pandemic_evaluation_plan(
    plan: PostPandemicEvaluationPlan,
) -> PostPandemicEvaluationPlan:
    """Reauthenticate loader identity, frozen fields, lineage, and all bytes."""
    if (
        type(plan) is not PostPandemicEvaluationPlan
        or getattr(plan, "_authority", None)
        is not _LOADED_POST_PANDEMIC_PLAN_AUTHORITY
    ):
        raise PostPandemicEvaluationPlanError(
            "post-pandemic plan is not loader-authenticated"
        )
    with _POST_PANDEMIC_PLAN_AUTHORITIES_LOCK:
        authority = _POST_PANDEMIC_PLAN_AUTHORITIES.get(id(plan))
    if authority is None or authority[0]() is not plan:
        raise PostPandemicEvaluationPlanError(
            "post-pandemic plan loader authority is absent"
        )
    (
        _,
        source_path,
        fold_path,
        stock_path,
        qc_path,
        source_payload,
        fold_payload,
        stock_payload,
        qc_payload,
        fingerprint,
    ) = authority
    if _plan_fingerprint(plan) != fingerprint:
        raise PostPandemicEvaluationPlanError(
            "post-pandemic plan changed after authentication"
        )
    for path, payload, name in (
        (source_path, source_payload, "post-pandemic plan"),
        (fold_path, fold_payload, "parent fold manifest"),
        (stock_path, stock_payload, "stock-evaluation parent"),
        (qc_path, qc_payload, "QC-first parent"),
    ):
        _revalidate(path, payload, name)
    reloaded = load_post_pandemic_evaluation_plan(
        source_path,
        fold_manifest_path=fold_path,
        stock_evaluation_path=stock_path,
        qc_first_plan_path=qc_path,
    )
    if _plan_fingerprint(reloaded) != fingerprint:
        raise PostPandemicEvaluationPlanError(
            "post-pandemic plan source changed after authentication"
        )
    return plan


def _parse_plan(payload: bytes) -> dict[str, Any]:
    if payload.startswith(
        (
            b"\xef\xbb\xbf",
            b"\xff\xfe",
            b"\xfe\xff",
            b"\xff\xfe\x00\x00",
            b"\x00\x00\xfe\xff",
        )
    ):
        raise PostPandemicEvaluationPlanError(
            "post-pandemic plan must not contain a BOM"
        )
    try:
        text = payload.decode("utf-8", errors="strict")
        raw = json.loads(
            text,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object,
        )
    except PostPandemicEvaluationPlanError:
        raise
    except UnicodeDecodeError as exc:
        raise PostPandemicEvaluationPlanError(
            "post-pandemic plan is not strict UTF-8"
        ) from exc
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise PostPandemicEvaluationPlanError(
            "post-pandemic plan is invalid JSON"
        ) from exc
    if type(raw) is not dict or set(raw) != _ROOT_KEYS:
        raise PostPandemicEvaluationPlanError(
            "post-pandemic plan root fields are not exact"
        )
    try:
        canonical_file = (
            json.dumps(
                raw,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PostPandemicEvaluationPlanError(
            "post-pandemic plan contains a noncanonical JSON value"
        ) from exc
    if payload != canonical_file:
        raise PostPandemicEvaluationPlanError(
            "post-pandemic plan bytes are not canonical UTF-8 JSON"
        )
    return raw


def load_post_pandemic_evaluation_plan(
    path: Path,
    *,
    fold_manifest_path: Path,
    stock_evaluation_path: Path,
    qc_first_plan_path: Path,
) -> PostPandemicEvaluationPlan:
    """Authenticate the exact supplement and its accepted parent graph."""
    resolved, payload = _read_stable_regular(path, "post-pandemic plan")
    raw = _parse_plan(payload)

    declared_hash = raw["plan_hash"]
    if (
        type(declared_hash) is not str
        or len(declared_hash) != 64
        or any(character not in "0123456789abcdef" for character in declared_hash)
    ):
        raise PostPandemicEvaluationPlanError(
            "plan_hash must be a lowercase SHA-256"
        )
    actual_hash = hashlib.sha256(_content_payload(raw)).hexdigest()
    if actual_hash != declared_hash:
        raise PostPandemicEvaluationPlanError(
            "post-pandemic plan content hash mismatch"
        )
    if raw["plan_id"] != f"{PLAN_ID_PREFIX}{actual_hash[:16]}":
        raise PostPandemicEvaluationPlanError("plan_id is not content-derived")

    _require_exact(raw, _EXPECTED_DOCUMENT, "post-pandemic plan")
    for name in _SECTION_NAMES:
        if hashlib.sha256(_canonical(raw[name])).hexdigest() != raw[
            "section_hashes"
        ][name]:
            raise PostPandemicEvaluationPlanError(f"{name} section hash mismatch")

    resolved_fold, fold_payload = _read_stable_regular(
        fold_manifest_path, "parent fold manifest"
    )
    resolved_stock, stock_payload = _read_stable_regular(
        stock_evaluation_path, "stock-evaluation parent"
    )
    resolved_qc, qc_payload = _read_stable_regular(
        qc_first_plan_path, "QC-first parent"
    )
    if (
        hashlib.sha256(fold_payload).hexdigest()
        != PARENT_FOLD_MANIFEST_ARTIFACT_SHA256
    ):
        raise PostPandemicEvaluationPlanError(
            "parent fold manifest artifact bytes changed"
        )
    if hashlib.sha256(stock_payload).hexdigest() != PARENT_STOCK_SPEC_ARTIFACT_SHA256:
        raise PostPandemicEvaluationPlanError(
            "stock-evaluation parent artifact bytes changed"
        )
    if hashlib.sha256(qc_payload).hexdigest() != PARENT_PLAN_ARTIFACT_SHA256:
        raise PostPandemicEvaluationPlanError("QC-first parent artifact bytes changed")

    try:
        parent = load_stock_fold_manifest(
            resolved_fold,
            stock_evaluation_path=resolved_stock,
            qc_first_plan_path=resolved_qc,
        )
        require_loaded_stock_fold_manifest(parent)
    except StockFoldManifestError as exc:
        raise PostPandemicEvaluationPlanError(
            "parent fold manifest authentication failed"
        ) from exc
    _validate_parent_and_semantics(raw, parent)

    for source, source_payload, name in (
        (resolved_qc, qc_payload, "QC-first parent"),
        (resolved_stock, stock_payload, "stock-evaluation parent"),
        (resolved_fold, fold_payload, "parent fold manifest"),
        (resolved, payload, "post-pandemic plan"),
    ):
        _revalidate(source, source_payload, name)
    return _loaded_plan(
        raw,
        source_path=resolved,
        fold_manifest_path=resolved_fold,
        stock_evaluation_path=resolved_stock,
        qc_first_plan_path=resolved_qc,
        source_payload=payload,
        fold_manifest_payload=fold_payload,
        stock_evaluation_payload=stock_payload,
        qc_first_plan_payload=qc_payload,
    )


def _render_expected_document() -> str:
    """Render review bytes; intentionally grants no persistence authority."""
    return json.dumps(
        _thaw(_EXPECTED_DOCUMENT),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


if __name__ == "__main__":  # pragma: no cover - review-artifact renderer
    print(_render_expected_document(), end="")
