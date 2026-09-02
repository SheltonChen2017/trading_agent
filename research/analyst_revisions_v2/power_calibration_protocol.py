"""Outcome-free ARV2-4D-A stock power-calibration protocol.

This module authenticates the owner-approved planning policy that a later,
separately authorized calibration may apply.  It deliberately cannot read
provider rows or outcomes, issue an authoritative power receipt, run
QuantConnect, dispose an evaluation, deploy, or trade.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
import weakref
from datetime import date
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_CEILING,
    ROUND_HALF_EVEN,
    localcontext,
)
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from data.exchange_calendar import (
    ExchangeCalendarError,
    resolve_nth_session_after,
    trading_sessions,
)

from .global_benchmark_contract import (
    EVALUATION_ID,
    FOLD_MANIFEST_ARTIFACT_SHA256,
    FOLD_MANIFEST_HASH,
    FOLD_MANIFEST_ID,
    MAP_BINDING,
    MATCHED_BINDING,
    PARENT_STOCK_SPEC_ARTIFACT_SHA256,
    PARENT_STOCK_SPEC_HASH,
    PARENT_STOCK_SPEC_ID,
    QC_PLAN_ARTIFACT_SHA256,
    QC_PLAN_HASH,
    QC_PLAN_ID,
    STRATEGY_PDF_SHA256,
    SUCCESSOR_BINDING,
    GlobalBenchmarkContract,
    GlobalBenchmarkContractError,
    load_global_benchmark_contract,
    require_loaded_global_benchmark_contract,
)


class PowerCalibrationProtocolError(ValueError):
    """The power protocol, its ancestry, or provisional inputs are invalid."""


PROTOCOL_SCHEMA = "arv2-stock-power-calibration-protocol-structural-v1"
PROTOCOL_STATUS = (
    "owner_approved_protocol_frozen_outcome_free_pending_independent_review"
)
PROTOCOL_AUTHORITY = (
    "calibration_method_only_no_input_data_outcome_receipt_qc_or_deployment_authority"
)
PROTOCOL_ID_PREFIX = "arv2-stock-power-calibration-protocol-"

CALIBRATION_FOLD_ID = "arv2-wf-test-2020-h20"
CALIBRATION_FOLD_HASH = (
    "9dcaa09e8f6b9b3786e016bb1db5c3d0ebfd918d49951e8de45dad3383c4fa5c"
)
CALIBRATION_START = "2018-01-31"
CALIBRATION_END_EXCLUSIVE = "2020-01-02"
CALIBRATION_LAST_SESSION = "2019-12-31"
CALIBRATION_LAST_OUTCOME_SESSION = "2020-01-30"
FIRST_TEST_SESSION = "2020-01-31"
CALIBRATION_SESSION_COUNT = 483
CALIBRATION_AXIS_SHA256 = (
    "22d38c7178f6863d4d9f5284eba9216b0f8499848b1188781316d1169b13a051"
)
TEST_SESSION_CAPACITY = 1388
HAC_MAX_LAG = 20
MINIMUM_ABSOLUTE_FLOOR = 50

Z_0975 = "1.9599639845400542355245944305205515279555500778695"
Z_0800 = "0.84162123357291420517870612136324810062629753400888"
NORMAL_SUM_SQUARED = (
    "7.8488797343490889511625145685327253191071246220413"
)

_EXTERNAL_BINDINGS = {
    "independent_review_commit": None,
    "counter_review_commit": None,
    "calibration_input_manifest_sha256": None,
    "numeric_power_receipt_sha256": None,
    "power_plan_sha256": None,
    "source_rights_receipt_id": None,
    "dataset_id": None,
    "outcome_artifact_sha256": None,
    "qc_project_id": None,
    "qc_run_id": None,
    "evaluation_receipt_id": None,
}
_CAPABILITIES = {
    "calibration_input_access": False,
    "source_access": False,
    "outcome_access": False,
    "authoritative_power_receipt": False,
    "power_plan_binding": False,
    "qc_upload": False,
    "qc_compile": False,
    "qc_launch": False,
    "result_disposition": False,
    "paper_deployment": False,
    "funded_deployment": False,
    "orders": False,
}


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
        raise PowerCalibrationProtocolError("noncanonical JSON value") from exc


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
        raise PowerCalibrationProtocolError("noncanonical JSON value") from exc


def _content_identity(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(raw)
    value["protocol_id"] = None
    value["protocol_hash"] = None
    digest = hashlib.sha256(_canonical(value)).hexdigest()
    value["protocol_hash"] = digest
    value["protocol_id"] = f"{PROTOCOL_ID_PREFIX}{digest[:16]}"
    return value


def _binding(
    *, artifact_id: str, content_sha256: str, artifact_sha256: str
) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "content_sha256": content_sha256,
        "artifact_sha256": artifact_sha256,
    }


def _lineage_nodes() -> list[dict[str, object]]:
    return [
        {"node": "strategy_pdf", "parents": []},
        {"node": "qc_base", "parents": ["strategy_pdf"]},
        {"node": "qc_plan", "parents": ["strategy_pdf", "qc_base"]},
        {"node": "stock_v1", "parents": ["strategy_pdf", "qc_plan"]},
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
        {
            "node": "power_protocol",
            "parents": [
                "strategy_pdf",
                "qc_plan",
                "stock_v1",
                "fold_manifest",
                "global_map",
                "matched_contract",
                "stock_v2",
            ],
        },
    ]


def _protocol_document() -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": PROTOCOL_SCHEMA,
        "status": PROTOCOL_STATUS,
        "authority": PROTOCOL_AUTHORITY,
        "protocol_id": None,
        "protocol_hash": None,
        "strategy_pdf_sha256": STRATEGY_PDF_SHA256,
        "evaluation_id": EVALUATION_ID,
        "owner_policy": {
            "decision": "2026-09-02_ARV2-4D-A_recommended_power_policy_approved",
            "minimum_meaningful_effect": {
                "basis_points": {"numerator": 10, "denominator": 1},
                "return_per_adjusted_score_unit": {
                    "numerator": 1,
                    "denominator": 1000,
                },
                "score_change": {"numerator": 1, "denominator": 1},
                "return_definition": "arithmetic_gross_20_session_open_to_open_SPY_excess_return",
                "not": [
                    "annualized_return",
                    "log_return",
                    "daily_return",
                    "net_sleeve_return",
                ],
            },
            "target_power": {"numerator": 4, "denominator": 5},
            "two_sided_size": {"numerator": 1, "denominator": 20},
            "minimums_are_frozen_before_calibration": True,
            "post_outcome_weakening_or_reinterpretation": "forbidden",
        },
        "claim_scope": {
            "primary_gate_id": "bullish_20_session_fama_macbeth",
            "regressor": "max(final_control_adjusted_score,0)",
            "coefficient_unit": "20_session_arithmetic_gross_SPY_excess_return_per_plus_1_adjusted_score_unit",
            "claim": "nominal_asymptotic_planning_power_for_primary_gate_only",
            "does_not_establish_power_for": [
                "economic_net_sleeve_gate",
                "firm_specific_vs_global_paired_IC_gate",
                "three_gate_conjunction",
                "exact_19999_replicate_bootstrap_test",
                "the_strategy_lane_as_a_whole",
            ],
        },
        "bound_ancestry": {
            "qc_first_plan": _binding(
                artifact_id=QC_PLAN_ID,
                content_sha256=QC_PLAN_HASH,
                artifact_sha256=QC_PLAN_ARTIFACT_SHA256,
            ),
            "predecessor_stock_spec": _binding(
                artifact_id=PARENT_STOCK_SPEC_ID,
                content_sha256=PARENT_STOCK_SPEC_HASH,
                artifact_sha256=PARENT_STOCK_SPEC_ARTIFACT_SHA256,
            ),
            "existing_fold_manifest": _binding(
                artifact_id=FOLD_MANIFEST_ID,
                content_sha256=FOLD_MANIFEST_HASH,
                artifact_sha256=FOLD_MANIFEST_ARTIFACT_SHA256,
            ),
            "global_rating_map": dict(MAP_BINDING),
            "matched_comparison_contract": dict(MATCHED_BINDING),
            "stock_successor_v2": dict(SUCCESSOR_BINDING),
        },
        "calibration_source": {
            "role": "nuisance_variance_dependence_and_preoutcome_component_calibration_only_not_an_evaluation",
            "boundary_source": {
                "fold_id": CALIBRATION_FOLD_ID,
                "structural_fold_sha256": CALIBRATION_FOLD_HASH,
                "horizon_sessions": 20,
                "validation_start_inclusive": CALIBRATION_START,
                "validation_end_exclusive": CALIBRATION_END_EXCLUSIVE,
                "first_test_session": FIRST_TEST_SESSION,
            },
            "complete_NYSE_session_axis": {
                "session_count": CALIBRATION_SESSION_COUNT,
                "session_axis_sha256": CALIBRATION_AXIS_SHA256,
                "first_session": CALIBRATION_START,
                "last_session": CALIBRATION_LAST_SESSION,
            },
            "maturity_separation": {
                "last_included_decision_session": CALIBRATION_LAST_SESSION,
                "last_included_h20_outcome_session": CALIBRATION_LAST_OUTCOME_SESSION,
                "strictly_before_first_test_session": True,
                "validation_end_boundary_h20_outcome_would_equal_first_test_session_and_is_excluded": True,
            },
            "allowed_numeric_receipt_outputs": [
                "valid_beta_date_count",
                "lag_pair_counts_0_through_20",
                "long_run_variance",
                "component_count_census_sha256",
                "component_count_census_session_count",
                "q05_components_per_date",
                "raw_required_valid_dates",
                "required_valid_dates",
                "required_connected_components",
                "fixed_capacity_disposition",
            ],
            "numeric_receipt_output_allowlist_is_closed": True,
            "all_other_computed_or_intermediate_statistics": "forbidden_to_persist_or_disclose",
            "forbidden_persisted_or_disclosed_outputs": [
                "date_level_beta_values",
                "beta_mean",
                "beta_sign",
                "information_coefficient",
                "p_value",
                "security_or_date_return",
                "portfolio_return",
                "PnL",
                "strategy_performance",
                "gate_result",
            ],
            "exclusive_use": "may_never_tune_effect_map_fold_threshold_period_seed_or_retry",
        },
        "h20_HAC_protocol": {
            "implementation_stage": "ARV2-4D-B_only_after_separate_exact_calibration_input_authority",
            "date_series": "per_date_bullish_20_session_Fama_MacBeth_coefficients_under_exact_parent_preprocessing_weights_controls_and_refusals",
            "training_only_adjustment": "same_frozen_training_only_score_adjustment_as_future_evaluation",
            "complete_axis_rule": "missing_or_refused_dates_remain_missing_at_their_exact_NYSE_axis_positions_never_compressed_or_zero_filled",
            "valid_date_count_symbol": "N",
            "minimum_valid_date_count": MINIMUM_ABSOLUTE_FLOOR,
            "centering": "compute_mean_as_same_context_stable_sum_divided_by_exact_integer_N_then_subtract_in_that_context_transiently_for_covariance_only_and_never_persist_or_disclose_it",
            "centered_value": "x_t=beta_t-transient_valid_date_mean",
            "autocovariance": "gamma_l=stable_sum(x_t*x_(t-l)_over_exact_session_distance_l_valid_pairs)/N",
            "autocovariance_denominator": "N_not_lag_pair_count",
            "maximum_lag_sessions": HAC_MAX_LAG,
            "lag_weights": "Bartlett_weight_l=(21-l)/21_for_l_1_through_20",
            "long_run_variance": "Omega=gamma_0+2*stable_sum(Bartlett_weight_l*gamma_l_for_l_1_through_20)",
            "lag_pair_requirement": "at_least_one_exact_axis_valid_pair_at_every_lag_0_through_20",
            "validity": "N_at_least_50_and_Omega_strictly_positive_and_finite_and_every_lag_pair_requirement_met",
            "invalid_disposition": "INVALID_CALIBRATION_no_fallback_no_clamp_no_epsilon_no_absolute_value_no_alternate_variance",
            "stable_sum": "sort_each_finite_Decimal_multiset_by_absolute_value_then_signed_value_before_sum_from_exact_zero",
            "arithmetic_context": {
                "precision": 50,
                "rounding": "ROUND_HALF_EVEN",
                "Emin": -999999,
                "Emax": 999999,
                "capitals": 1,
                "clamp": 0,
                "fresh_local_context": True,
                "flags_cleared_before_use": True,
                "enabled_traps": [
                    "InvalidOperation",
                    "DivisionByZero",
                    "Overflow",
                ],
                "binary_float_bool_and_nonfinite_inputs": "forbidden",
                "ambient_context_or_flags_may_not_change_result_or_leak": True,
            },
        },
        "normal_planning_formula": {
            "interpretation": "nominal_asymptotic_plugin_planning_approximation_aligned_in_effect_axis_and_dependence_not_exact_bootstrap_power",
            "z_0_975": Z_0975,
            "z_0_800": Z_0800,
            "squared_sum": NORMAL_SUM_SQUARED,
            "effect_return_per_score_unit": {"numerator": 1, "denominator": 1000},
            "raw_required_valid_dates": "ceil(Omega*squared_sum/(1/1000)^2)",
            "evaluation_order": "inside_the_fresh_context_construct_exact_Decimal_constants_compute_effect_times_effect_then_Omega_times_squared_sum_then_divide_and_apply_ROUND_CEILING",
            "required_valid_dates": "max(50,raw_required_valid_dates)",
            "fixed_h20_test_session_capacity": TEST_SESSION_CAPACITY,
            "capacity_source": "sum_of_all_six_reviewed_complete_h20_test_session_axes",
            "capacity_comparison": "required_valid_dates_less_than_or_equal_to_1388_is_within_capacity_greater_than_1388_is_underpowered",
            "within_capacity": "FEASIBLE_FIXED_DESIGN_pending_authenticated_receipt",
            "over_capacity": "UNDERPOWERED_FIXED_DESIGN_no_launch",
            "over_capacity_rescue": "forbidden_no_period_extension_effect_weakening_alternate_variance_retry_or_peek",
        },
        "component_floor_protocol": {
            "stage": "authenticated_preoutcome_complete_axis_census",
            "component_definition": "firm_specific_primary_h20_Fama_MacBeth_design_connected_component_instances_per_complete_axis_session_built_from_all_point_in_time_eligible_security_decision_rows_including_structural_zero_neutral_rows_with_no_score_or_sign_filter_after_all_required_nonoutcome_eligibility_common_event_and_cross_date_component_refusals_before_outcome_join_and_before_global_comparator_matching_with_neutral_rows_as_singletons",
            "input": "one_exact_session_and_nonnegative_integer_count_pair_for_each_of_483_sessions_ordered_by_the_complete_calibration_axis",
            "honest_zero_count": "included_as_zero",
            "missing_duplicate_or_unverifiable_count": "INVALID_CALIBRATION_not_zero_and_not_excluded",
            "quantile": {"numerator": 1, "denominator": 20},
            "method": "lower_tail_empirical_nearest_rank_without_interpolation",
            "one_based_rank": "max(1,ceil(session_count/20))",
            "fixed_rank_for_483_sessions": 25,
            "q05_components_per_date": "sorted_complete_axis_counts[24]",
            "calibrated_pooled_requirement": "required_valid_dates*q05_components_per_date",
            "required_connected_components": "max(50,required_valid_dates*q05_components_per_date)",
            "selection_role": "none_never_a_per_date_filter_and_never_drops_dates",
        },
        "coverage_and_disposition": {
            "existing_five_19_over_20_ledgers": "unchanged_pooled_and_per_fold_exact_integer_cross_multiplication",
            "coverage_inputs": "preoutcome_only_no_outcome_availability_value_or_dispersion",
            "calibration_invalid": "INVALID_CALIBRATION_no_fallback",
            "preoutcome_structural_shortfall": "INVALID_DATA_requires_new_owner_approved_content_addressed_policy_before_any_outcome_look",
            "post_join_honest_underfill": "INCONCLUSIVE_locked_no_extension",
            "adequate_sample_gate_failure": "FAIL_closes_family",
            "underfill_or_failure_rescue": "forbidden_no_alias_date_fold_period_seed_threshold_or_retry_change",
        },
        "deferred_ARV2_4D_B": {
            "separate_authority_required": True,
            "calibration_input_manifest": "future_content_addressed_child_of_this_protocol_binding_only_source_identity_hash_schema_rights_processing_lineage_exact_session_keys_and_counts_never_row_returns_or_date_level_betas",
            "exact_calibration_input_manifest_schema": "deferred_to_separately_authorized_and_independently_reviewed_ARV2-4D-B_child",
            "numeric_power_receipt": "future_content_addressed_child_of_this_protocol_and_authenticated_input_manifest",
            "stock_successor_v3": "future_child_binding_the_numeric_receipt_without_editing_or_repinning_reviewed_ARV2-4C_artifacts",
            "required_receipt_fields": [
                "protocol_id",
                "protocol_hash",
                "calibration_input_manifest_sha256",
                "valid_beta_date_count",
                "lag_pair_counts_0_through_20",
                "long_run_variance",
                "component_count_census_sha256",
                "component_count_census_session_count",
                "q05_components_per_date",
                "raw_required_valid_dates",
                "required_valid_dates",
                "required_connected_components",
                "fixed_capacity_disposition",
            ],
            "current_numeric_values": {
                "calibration_input_manifest_sha256": None,
                "component_count_census_sha256": None,
                "component_count_census_session_count": None,
                "long_run_variance": None,
                "q05_components_per_date": None,
                "raw_required_valid_dates": None,
                "required_valid_dates": None,
                "required_connected_components": None,
                "numeric_power_receipt_sha256": None,
                "stock_successor_v3_sha256": None,
            },
        },
        "acyclic_lineage": {
            "edge_direction": "child_to_parent",
            "ordered_nodes": _lineage_nodes(),
            "protocol_is_leaf": True,
            "reviewed_ARV2_4C_nodes_and_edges_unchanged": True,
            "fold_manifest_or_stock_v2_repin_or_reparent": "forbidden",
        },
        "external_bindings": dict(_EXTERNAL_BINDINGS),
        "capabilities": dict(_CAPABILITIES),
    }
    return _content_identity(raw)


def _reject_float(value: str) -> None:
    raise PowerCalibrationProtocolError(
        f"binary floating-point is forbidden: {value}"
    )


def _reject_constant(value: str) -> None:
    raise PowerCalibrationProtocolError(f"non-finite JSON is forbidden: {value}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PowerCalibrationProtocolError(f"duplicate JSON key: {key}")
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
        raise PowerCalibrationProtocolError(f"{name} must not traverse a link")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise PowerCalibrationProtocolError(f"{name} is unavailable") from exc
    if _is_link_like(resolved) or not resolved.is_file():
        raise PowerCalibrationProtocolError(f"{name} must be a regular file")
    try:
        before = resolved.stat()
        first = resolved.read_bytes()
        second = resolved.read_bytes()
        after = resolved.stat()
    except OSError as exc:
        raise PowerCalibrationProtocolError(f"{name} is unreadable") from exc
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity or first != second:
        raise PowerCalibrationProtocolError(f"{name} changed while being read")
    return resolved, first


def _revalidate(path: Path, payload: bytes, name: str) -> None:
    if _is_link_like(path) or not path.is_file():
        raise PowerCalibrationProtocolError(f"{name} changed or disappeared")
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise PowerCalibrationProtocolError(
            f"{name} changed or disappeared"
        ) from exc
    if current != payload:
        raise PowerCalibrationProtocolError(f"{name} changed after authentication")


def _parse_artifact(payload: bytes, name: str) -> dict[str, Any]:
    if payload.startswith(
        (
            b"\xef\xbb\xbf",
            b"\xff\xfe",
            b"\xfe\xff",
            b"\xff\xfe\x00\x00",
            b"\x00\x00\xfe\xff",
        )
    ):
        raise PowerCalibrationProtocolError(f"{name} must not contain a BOM")
    try:
        raw = json.loads(
            payload.decode("utf-8", errors="strict"),
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object,
        )
    except UnicodeDecodeError as exc:
        raise PowerCalibrationProtocolError(f"{name} is not strict UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise PowerCalibrationProtocolError(f"{name} is invalid JSON") from exc
    if type(raw) is not dict:
        raise PowerCalibrationProtocolError(f"{name} must be a JSON object")
    if _render(raw) != payload:
        raise PowerCalibrationProtocolError(
            f"{name} bytes are not canonical sorted UTF-8 JSON"
        )
    return raw


def _validate_content_identity(raw: Mapping[str, Any]) -> None:
    declared_hash = raw.get("protocol_hash")
    if (
        type(declared_hash) is not str
        or len(declared_hash) != 64
        or any(character not in "0123456789abcdef" for character in declared_hash)
    ):
        raise PowerCalibrationProtocolError("power protocol content hash is invalid")
    payload = dict(raw)
    payload["protocol_id"] = None
    payload["protocol_hash"] = None
    actual = hashlib.sha256(_canonical(payload)).hexdigest()
    if declared_hash != actual:
        raise PowerCalibrationProtocolError("power protocol content hash mismatch")
    if raw.get("protocol_id") != f"{PROTOCOL_ID_PREFIX}{actual[:16]}":
        raise PowerCalibrationProtocolError(
            "power protocol identity is not content-derived"
        )


def _require_exact(actual: object, expected: object, name: str) -> None:
    if isinstance(expected, dict):
        if type(actual) is not dict or set(actual) != set(expected):
            raise PowerCalibrationProtocolError(f"{name} changed from the frozen definition")
        for key, value in expected.items():
            _require_exact(actual[key], value, f"{name}.{key}")
        return
    if isinstance(expected, list):
        if type(actual) is not list or len(actual) != len(expected):
            raise PowerCalibrationProtocolError(f"{name} changed from the frozen definition")
        for index, (item, value) in enumerate(zip(actual, expected, strict=True)):
            _require_exact(item, value, f"{name}[{index}]")
        return
    if type(actual) is not type(expected) or actual != expected:
        raise PowerCalibrationProtocolError(f"{name} changed from the frozen definition")


def _lineage_graph(raw: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    try:
        nodes = raw["acyclic_lineage"]["ordered_nodes"]
    except (KeyError, TypeError) as exc:
        raise PowerCalibrationProtocolError("power lineage is malformed") from exc
    if type(nodes) is not list:
        raise PowerCalibrationProtocolError("power lineage is malformed")
    graph: dict[str, tuple[str, ...]] = {}
    for item in nodes:
        if type(item) is not dict or set(item) != {"node", "parents"}:
            raise PowerCalibrationProtocolError("power lineage is malformed")
        node = item["node"]
        parents = item["parents"]
        if (
            type(node) is not str
            or not node
            or type(parents) is not list
            or any(type(parent) is not str or not parent for parent in parents)
            or len(parents) != len(set(parents))
            or node in graph
        ):
            raise PowerCalibrationProtocolError("power lineage is malformed")
        graph[node] = tuple(parents)
    if any(parent not in graph for parents in graph.values() for parent in parents):
        raise PowerCalibrationProtocolError("power lineage has an unknown parent")
    _assert_acyclic(graph)
    expected = {
        item["node"]: tuple(item["parents"]) for item in _lineage_nodes()
    }
    if graph != expected:
        raise PowerCalibrationProtocolError(
            "power lineage changed from its exact reviewed ancestry"
        )
    return graph


def _assert_acyclic(graph: Mapping[str, Iterable[str]]) -> None:
    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise PowerCalibrationProtocolError("power lineage contains a cycle")
        if node in complete:
            return
        visiting.add(node)
        for parent in graph[node]:
            visit(parent)
        visiting.remove(node)
        complete.add(node)

    for node in graph:
        visit(node)


def _freeze(value: Any) -> Any:
    return _freeze_constant(value)


def _validate_calendar_and_capacity(
    fold_manifest_payload: bytes, parent: GlobalBenchmarkContract
) -> tuple[str, ...]:
    raw = _parse_artifact(fold_manifest_payload, "existing fold manifest")
    try:
        boundaries = [
            boundary
            for fold in raw["walk_forward_contract"]["folds"]
            for boundary in fold["horizon_boundaries"]
            if boundary["fold_id"] == CALIBRATION_FOLD_ID
        ]
    except (KeyError, TypeError) as exc:
        raise PowerCalibrationProtocolError(
            "calibration boundary cannot be derived from the fold manifest"
        ) from exc
    if len(boundaries) != 1:
        raise PowerCalibrationProtocolError(
            "calibration boundary is not unique in the fold manifest"
        )
    boundary = boundaries[0]
    expected_boundary = {
        "fold_id": CALIBRATION_FOLD_ID,
        "structural_fold_sha256": CALIBRATION_FOLD_HASH,
        "horizon_sessions": 20,
        "train_end_exclusive": "2018-01-02",
        "validation_start": CALIBRATION_START,
        "validation_end_exclusive": CALIBRATION_END_EXCLUSIVE,
        "test_start": FIRST_TEST_SESSION,
    }
    for key, value in expected_boundary.items():
        if type(boundary.get(key)) is not type(value) or boundary.get(key) != value:
            raise PowerCalibrationProtocolError(
                "calibration boundary changed in the fold manifest"
            )
    try:
        if resolve_nth_session_after(boundary["train_end_exclusive"], 20) != CALIBRATION_START:
            raise PowerCalibrationProtocolError("calibration start no longer matches its purge")
        if resolve_nth_session_after(CALIBRATION_END_EXCLUSIVE, 20) != FIRST_TEST_SESSION:
            raise PowerCalibrationProtocolError("first test session no longer matches its embargo")
        sessions = tuple(
            session.isoformat()
            for session in trading_sessions(
                date.fromisoformat(CALIBRATION_START),
                date.fromisoformat(CALIBRATION_END_EXCLUSIVE),
            )
            if session.isoformat() < CALIBRATION_END_EXCLUSIVE
        )
        if resolve_nth_session_after(CALIBRATION_LAST_SESSION, 20) != CALIBRATION_LAST_OUTCOME_SESSION:
            raise PowerCalibrationProtocolError("last calibration outcome maturity changed")
        if resolve_nth_session_after(CALIBRATION_END_EXCLUSIVE, 20) != FIRST_TEST_SESSION:
            raise PowerCalibrationProtocolError("excluded boundary maturity changed")
    except (ExchangeCalendarError, ValueError) as exc:
        if isinstance(exc, PowerCalibrationProtocolError):
            raise
        raise PowerCalibrationProtocolError(
            "calibration exchange-session axis cannot be resolved"
        ) from exc
    if (
        len(sessions) != CALIBRATION_SESSION_COUNT
        or not sessions
        or sessions[0] != CALIBRATION_START
        or sessions[-1] != CALIBRATION_LAST_SESSION
        or hashlib.sha256(_canonical(sessions)).hexdigest()
        != CALIBRATION_AXIS_SHA256
        or not CALIBRATION_LAST_OUTCOME_SESSION < FIRST_TEST_SESSION
    ):
        raise PowerCalibrationProtocolError("calibration session axis changed")
    capacity = sum(
        summary["session_count"] for summary in parent.fold_axis_summaries
    )
    if type(capacity) is not int or capacity != TEST_SESSION_CAPACITY:
        raise PowerCalibrationProtocolError("fixed h20 test capacity changed")
    return sessions


@dataclasses.dataclass(frozen=True, init=False)
class PowerCalibrationProtocol:
    protocol_id: str
    protocol_hash: str
    evaluation_id: str
    calibration_session_axis: tuple[str, ...]
    definition: Mapping[str, Any]
    lineage_graph: Mapping[str, tuple[str, ...]]
    capabilities: Mapping[str, bool]
    _authority: object = dataclasses.field(repr=False, compare=False)

    @property
    def calibration_input_access_available(self) -> bool:
        return False

    @property
    def source_access_available(self) -> bool:
        return False

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def authoritative_receipt_available(self) -> bool:
        return False

    @property
    def power_plan_binding_available(self) -> bool:
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


class ProvisionalPowerDisposition(str, Enum):
    FEASIBLE_PENDING_AUTHENTICATED_RECEIPT = (
        "FEASIBLE_FIXED_DESIGN_pending_authenticated_receipt"
    )
    UNDERPOWERED_FIXED_DESIGN_NO_LAUNCH = "UNDERPOWERED_FIXED_DESIGN_no_launch"


@dataclasses.dataclass(frozen=True, init=False)
class ProvisionalPowerRequirement:
    long_run_variance: Decimal
    raw_required_valid_dates: int
    required_valid_dates: int
    q05_components_per_date: int
    required_connected_components: int
    fixed_h20_test_session_capacity: int
    disposition: ProvisionalPowerDisposition

    def __init__(self) -> None:
        raise TypeError(
            "provisional power requirements must be derived from the frozen protocol"
        )

    @property
    def authoritative(self) -> bool:
        return False

    @property
    def power_plan_sha256(self) -> None:
        return None

    @property
    def receipt_id(self) -> None:
        return None


_LOADED_POWER_CALIBRATION_PROTOCOL_AUTHORITY = object()
_POWER_CALIBRATION_PROTOCOL_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[PowerCalibrationProtocol],
        Path,
        bytes,
        GlobalBenchmarkContract,
        tuple[object, ...],
    ],
] = {}
_POWER_CALIBRATION_PROTOCOL_AUTHORITIES_LOCK = threading.RLock()


def _fingerprint_value(value: object) -> object:
    if type(value) is MappingProxyType:
        pairs = []
        for key, item in value.items():
            if type(key) is not str:
                raise PowerCalibrationProtocolError(
                    "power protocol contains a noncanonical authority key"
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
    raise PowerCalibrationProtocolError(
        "power protocol contains noncanonical authority state"
    )


def _protocol_fingerprint(
    protocol: PowerCalibrationProtocol,
) -> tuple[object, ...]:
    for name in ("protocol_id", "protocol_hash", "evaluation_id"):
        if type(getattr(protocol, name, None)) is not str:
            raise PowerCalibrationProtocolError(
                "power protocol identity fields changed type"
            )
    if type(protocol.calibration_session_axis) is not tuple or any(
        type(item) is not str for item in protocol.calibration_session_axis
    ):
        raise PowerCalibrationProtocolError(
            "power protocol session axis changed type"
        )
    return (
        protocol.protocol_id,
        protocol.protocol_hash,
        protocol.evaluation_id,
        protocol.calibration_session_axis,
        _fingerprint_value(protocol.definition),
        _fingerprint_value(protocol.lineage_graph),
        _fingerprint_value(protocol.capabilities),
    )


def _forget_authority(
    identity: int, reference: weakref.ReferenceType[PowerCalibrationProtocol]
) -> None:
    with _POWER_CALIBRATION_PROTOCOL_AUTHORITIES_LOCK:
        current = _POWER_CALIBRATION_PROTOCOL_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _POWER_CALIBRATION_PROTOCOL_AUTHORITIES.pop(identity, None)


def load_power_calibration_protocol(
    protocol_path: Path,
    *,
    map_path: Path,
    matched_contract_path: Path,
    successor_spec_path: Path,
    parent_stock_spec_path: Path,
    fold_manifest_path: Path,
    qc_first_plan_path: Path,
) -> PowerCalibrationProtocol:
    """Authenticate ARV2-4D-A and all exact ARV2-4C ancestry."""
    resolved, payload = _read_stable_regular(protocol_path, "power protocol")
    raw = _parse_artifact(payload, "power protocol")
    _validate_content_identity(raw)
    _assert_acyclic(_lineage_graph(raw))
    _require_exact(raw, _protocol_document(), "power protocol")
    try:
        parent = load_global_benchmark_contract(
            map_path=map_path,
            matched_contract_path=matched_contract_path,
            successor_spec_path=successor_spec_path,
            parent_stock_spec_path=parent_stock_spec_path,
            fold_manifest_path=fold_manifest_path,
            qc_first_plan_path=qc_first_plan_path,
        )
    except GlobalBenchmarkContractError as exc:
        raise PowerCalibrationProtocolError(
            "ARV2-4D-A parent authentication failed"
        ) from exc
    if (
        parent.evaluation_id != EVALUATION_ID
        or parent.map_id != MAP_BINDING["artifact_id"]
        or parent.map_hash != MAP_BINDING["content_sha256"]
        or parent.matched_contract_id != MATCHED_BINDING["artifact_id"]
        or parent.matched_contract_hash != MATCHED_BINDING["content_sha256"]
        or parent.successor_spec_id != SUCCESSOR_BINDING["artifact_id"]
        or parent.successor_spec_hash != SUCCESSOR_BINDING["content_sha256"]
    ):
        raise PowerCalibrationProtocolError("ARV2-4C parent identity changed")
    fold_resolved, fold_payload = _read_stable_regular(
        fold_manifest_path, "existing fold manifest"
    )
    if hashlib.sha256(fold_payload).hexdigest() != FOLD_MANIFEST_ARTIFACT_SHA256:
        raise PowerCalibrationProtocolError("existing fold-manifest bytes changed")
    sessions = _validate_calendar_and_capacity(fold_payload, parent)
    _revalidate(fold_resolved, fold_payload, "existing fold manifest")
    _revalidate(resolved, payload, "power protocol")
    try:
        require_loaded_global_benchmark_contract(parent)
    except GlobalBenchmarkContractError as exc:
        raise PowerCalibrationProtocolError(
            "ARV2-4D-A parent changed during authentication"
        ) from exc
    _revalidate(resolved, payload, "power protocol")

    value = object.__new__(PowerCalibrationProtocol)
    fields: dict[str, object] = {
        "protocol_id": raw["protocol_id"],
        "protocol_hash": raw["protocol_hash"],
        "evaluation_id": raw["evaluation_id"],
        "calibration_session_axis": sessions,
        "definition": _freeze(raw),
        "lineage_graph": _freeze(_lineage_graph(raw)),
        "capabilities": _freeze(raw["capabilities"]),
        "_authority": _LOADED_POWER_CALIBRATION_PROTOCOL_AUTHORITY,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    fingerprint = _protocol_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget_authority(key, ref))
    with _POWER_CALIBRATION_PROTOCOL_AUTHORITIES_LOCK:
        _POWER_CALIBRATION_PROTOCOL_AUTHORITIES[identity] = (
            reference,
            resolved,
            payload,
            parent,
            fingerprint,
        )
    return value


def require_loaded_power_calibration_protocol(
    protocol: PowerCalibrationProtocol,
) -> PowerCalibrationProtocol:
    """Reauthenticate loader identity, immutable state, and every source byte."""
    if (
        type(protocol) is not PowerCalibrationProtocol
        or getattr(protocol, "_authority", None)
        is not _LOADED_POWER_CALIBRATION_PROTOCOL_AUTHORITY
    ):
        raise PowerCalibrationProtocolError(
            "power protocol is not loader-authenticated"
        )
    with _POWER_CALIBRATION_PROTOCOL_AUTHORITIES_LOCK:
        authority = _POWER_CALIBRATION_PROTOCOL_AUTHORITIES.get(id(protocol))
    if authority is None or authority[0]() is not protocol:
        raise PowerCalibrationProtocolError(
            "power protocol loader authority is absent"
        )
    if _protocol_fingerprint(protocol) != authority[4]:
        raise PowerCalibrationProtocolError(
            "power protocol changed after authentication"
        )
    _revalidate(authority[1], authority[2], "power protocol")
    try:
        require_loaded_global_benchmark_contract(authority[3])
    except GlobalBenchmarkContractError as exc:
        raise PowerCalibrationProtocolError(
            "ARV2-4D-A parent changed after authentication"
        ) from exc
    _revalidate(authority[1], authority[2], "power protocol")
    return protocol


def _fresh_decimal_context() -> Context:
    context = Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )
    for signal in context.traps:
        context.traps[signal] = False
    for signal in (InvalidOperation, DivisionByZero, Overflow):
        context.traps[signal] = True
    context.clear_flags()
    return context


def _nearest_rank_lower_fifth(counts: tuple[int, ...]) -> int:
    if not counts or any(type(value) is not int or value < 0 for value in counts):
        raise PowerCalibrationProtocolError(
            "component census must contain exact nonnegative integers"
        )
    rank = max(1, (len(counts) + 19) // 20)
    return sorted(counts)[rank - 1]


def derive_provisional_power_requirement(
    protocol: PowerCalibrationProtocol,
    *,
    long_run_variance: Decimal,
    per_session_component_counts: tuple[tuple[str, int], ...],
) -> ProvisionalPowerRequirement:
    """Apply frozen arithmetic without granting or creating receipt authority.

    The inputs are caller-supplied and unauthenticated.  The result is useful
    for deterministic testing and for the future ARV2-4D-B worker, but it is
    never a power plan, evaluation permission, or evidence receipt.
    """
    require_loaded_power_calibration_protocol(protocol)
    if (
        type(long_run_variance) is not Decimal
        or not long_run_variance.is_finite()
        or long_run_variance <= 0
    ):
        raise PowerCalibrationProtocolError(
            "long-run variance must be an exact positive finite Decimal"
        )
    if (
        type(per_session_component_counts) is not tuple
        or len(per_session_component_counts) != CALIBRATION_SESSION_COUNT
    ):
        raise PowerCalibrationProtocolError(
            "component census must cover all 483 calibration sessions"
        )
    counts: list[int] = []
    for expected_session, item in zip(
        protocol.calibration_session_axis,
        per_session_component_counts,
        strict=True,
    ):
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or item[0] != expected_session
            or type(item[1]) is not int
            or item[1] < 0
        ):
            raise PowerCalibrationProtocolError(
                "component census must pair every exact axis session with one nonnegative integer count"
            )
        counts.append(item[1])
    q05 = _nearest_rank_lower_fifth(tuple(counts))
    context = _fresh_decimal_context()
    try:
        with localcontext(context) as active:
            active.clear_flags()
            factor = Decimal(NORMAL_SUM_SQUARED)
            effect = Decimal(1) / Decimal(1000)
            planned = long_run_variance * factor / (effect * effect)
            if not planned.is_finite() or planned <= 0:
                raise PowerCalibrationProtocolError(
                    "power arithmetic did not produce a positive finite requirement"
                )
            raw_dates = int(planned.to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, DivisionByZero, Overflow) as exc:
        raise PowerCalibrationProtocolError("power arithmetic is invalid") from exc
    required_dates = max(MINIMUM_ABSOLUTE_FLOOR, raw_dates)
    required_components = max(
        MINIMUM_ABSOLUTE_FLOOR, required_dates * q05
    )
    disposition = (
        ProvisionalPowerDisposition.UNDERPOWERED_FIXED_DESIGN_NO_LAUNCH
        if required_dates > TEST_SESSION_CAPACITY
        else ProvisionalPowerDisposition.FEASIBLE_PENDING_AUTHENTICATED_RECEIPT
    )
    value = object.__new__(ProvisionalPowerRequirement)
    fields: dict[str, object] = {
        "long_run_variance": long_run_variance,
        "raw_required_valid_dates": raw_dates,
        "required_valid_dates": required_dates,
        "q05_components_per_date": q05,
        "required_connected_components": required_components,
        "fixed_h20_test_session_capacity": TEST_SESSION_CAPACITY,
        "disposition": disposition,
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    return value


def render_expected_power_calibration_protocol() -> str:
    """Return the only canonical bytes accepted for ARV2-4D-A."""
    return _render(_protocol_document()).decode("utf-8")
