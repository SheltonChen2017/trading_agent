"""Declarative, outcome-free forward stock-admission and ETF-fallback child.

The owner chose a distinct future hybrid after observing historical variants:
the R232/R237-style 25% mapping/cap-coverage and five-name/score gates,
but a complete-book 95% lower bound and QCOM admission from the reviewed
forward construction. This is adaptive design, not an untouched holdout or an
exact replay of R232/R237. No source, score, name, independently mapped
as-of security ID, execution, epoch or paper authority is bound. In
particular, the existing predecision diagnostic has no security-name input
with which to execute the 25% SID/name count gate.
"""

import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from . import six_universe_forward_construction_policy as parent


class ForwardStockSelectionPolicyError(ValueError):
    """The frozen selection/fallback policy or parent changed."""


POLICY_PATH = Path(__file__).with_suffix(".json")
FROZEN_POLICY_SHA256 = "b691699baf506f8d7ef142439094527a936c73b37d3a2d39ed075315888bfcd0"
_PARENT_SHA256 = "7f1dbfe54f8179add6db9b15abdf343e55253ba50541175a5764e4c15dc644d4"
_FALSE_CAPABILITIES = {
    "confirmatory_look_commitment": False,
    "funded_deployment": False,
    "orders": False,
    "outcome_access": False,
    "paper_deployment": False,
    "qc_compile": False,
    "qc_launch": False,
    "qc_upload": False,
}
_CAP_RANK = "positive_market_cap_desc_then_exact_security_id"
_EXPECTED = {
    "adaptive_selection_disclosure": (
        "chosen_after_observed_historical_25pct_and_10pct_families_"
        "distinct_future_hybrid_not_an_untouched_holdout_or_R232_R237_replay"
    ),
    "allocation_and_overlap": {
        "cross_sleeve_redistribution": False,
        "direct_stock_aggregate_weight_cap": "0.098",
        "duplicate_security_rule": (
            "aggregate_exact_security_once_in_frozen_six_sleeve_order_"
            "cap_direct_stock_and_return_each_excess_to_contributing_own_etf"
        ),
        "equal_sleeve_budget_rule": (
            "floor_first_five_of_gross_divided_by_six_to_1e-24_"
            "assign_exact_residual_to_final_XLE_sleeve"
        ),
        "scaled_stock_slot_rule": (
            "if_scale_below_one_floor_1e-24_of_[(sleeve_budget/10)*"
            "min(1,cap_ratio*total_reported_weight)];otherwise_exact_"
            "sleeve_budget/10"
        ),
        "target_gross_exposure": "0.98",
    },
    "capabilities": _FALSE_CAPABILITIES,
    "decision_ready": False,
    "eligibility": {
        "maximum_stock_slots_per_sleeve": 10,
        "maximum_total_reported_weight": "1.05",
        "minimum_cap_covered_reported_weight_ratio": "0.25",
        "minimum_claimed_valid_security_mapped_weight_ratio": "0.99",
        "minimum_sid_and_name_mapped_member_ratio": "0.25",
        "minimum_total_reported_weight": "0.95",
        "minimum_verified_cap_identity_names": 5,
        "valid_security_mapping_separate_from_analyst_coverage": True,
    },
    "fallback": {
        "identity_or_coverage_invalid": "full_own_etf_fallback",
        "missing_verified_own_etf_sid_or_price": "named_refusal_no_target",
        "non_xle_ar_positive_count_below_five": "full_own_etf_fallback",
        "own_etf_target_requires": (
            "independently_verified_exact_own_etf_qc_sid_and_positive_tradable_"
            "predecision_reference_price_no_display_ticker_join"
        ),
        "unfilled_top_ten_slots": "residual_own_etf_fallback",
        "verified_cap_identity_names_below_five": "full_own_etf_fallback",
    },
    "parent_construction_policy_sha256": _PARENT_SHA256,
    "pending_bindings": {
        "common_predecision_input_contract_sha256": None,
        "etf_eligibility_source_sha256": None,
        "independent_as_of_security_id_mapping_sha256": None,
        "independent_holdings_security_master_sha256": None,
        "independent_vendor_first_publication_sha256": None,
        "independent_vendor_crosswalk_sha256": None,
        "own_etf_security_identity_source_sha256": None,
        "order_quantity_rounding_contract_sha256": None,
        "paper_epoch_sha256": None,
        "score_input_contract_sha256": None,
        "security_name_source_sha256": None,
        "shared_execution_contract_sha256": None,
        "weight_transfer_implementation_sha256": None,
    },
    "qcom_stock_admission": {
        "exact_qc_sid_required": True,
        "positive_cap_weight_and_tradable_reference_price_required": True,
        "special_exclusion": False,
        "ticker_alias_repair": False,
    },
    "schema": "arv2-six-universe-forward-stock-selection-policy-v1",
    "stock_selection": {
        "ar_off_control": {
            "ar_entry_count_enabled": False,
            "ar_score_economic_usage": "none_for_entry_count_or_weights",
            "candidate_id": "ARV2_FORWARD_AR_OFF",
            "non_xle_selection_count": "min_10_verified_cap_identity_names",
            "non_xle_selection_rank": _CAP_RANK,
            "positive_score_count_required": 0,
        },
        "ar_on_arms": [
            {
                "ar_entry_count_enabled": True,
                "ar_score_economic_usage": "entry_count_and_unbound_weight_transfer",
                "candidate_id": "ARV2_FORWARD_AR_100",
                "non_xle_selection_count": "min_10_eligible_positive_score_count",
                "non_xle_selection_rank": _CAP_RANK,
                "positive_score_count_required": 5,
            },
            {
                "ar_entry_count_enabled": True,
                "ar_score_economic_usage": "entry_count_and_unbound_weight_transfer",
                "candidate_id": "ARV2_FORWARD_AR_200",
                "non_xle_selection_count": "min_10_eligible_positive_score_count",
                "non_xle_selection_rank": _CAP_RANK,
                "positive_score_count_required": 5,
            },
        ],
        "eligible_positive_score_definition": (
            "strictly_positive_finite_authenticated_AR_score_for_exact_as_of_"
            "QC_SID_with_valid_security_name_and_positive_market_cap_after_"
            "reviewed_vendor_crosswalk_and_PIT_gate"
        ),
        "non_xle_selected_holdings_pool": (
            "all_verified_cap_eligible_exact_security_id_names_"
            "not_only_positive_score_names"
        ),
        "non_xle_universe": ["SPY", "QQQ", "SOXX", "XLV", "REMX"],
        "unresolved_or_ambiguous_ar_event": (
            "named_refusal_no_contribution_never_fabricated_zero"
        ),
        "xle_all_arms": {
            "candidate_ids": [
                "ARV2_FORWARD_AR_OFF", "ARV2_FORWARD_AR_100", "ARV2_FORWARD_AR_200",
            ],
            "positive_score_count_required": 0,
            "selection_count": "min_10_verified_cap_identity_names",
            "selection_rank": _CAP_RANK,
            "xle_ar_on_weight_overlay_disabled": False,
        },
    },
    "stock_selection_executable": False,
    "universe_ids": ["SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE"],
}


def _exact(left, right):
    if type(left) is not type(right):
        return False
    if type(right) is dict:
        return left.keys() == right.keys() and all(
            _exact(left[key], value) for key, value in right.items()
        )
    if type(right) is list:
        return len(left) == len(right) and all(
            _exact(a, b) for a, b in zip(left, right)
        )
    return left == right


def validate_policy(value):
    """Reject changed semantics, numeric type aliases and action authority."""
    if not _exact(value, _EXPECTED):
        raise ForwardStockSelectionPolicyError("forward stock-selection policy changed")
    return value


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ForwardStockSelectionPolicyError("forward stock selection has duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(value):
    raise ForwardStockSelectionPolicyError(
        f"forward stock selection has nonfinite JSON value {value}"
    )


def _verify_parent(value):
    if parent.FROZEN_POLICY_SHA256 != _PARENT_SHA256:
        raise ForwardStockSelectionPolicyError("forward construction parent identity changed")
    try:
        ancestor = parent.load_policy()
    except parent.ForwardConstructionPolicyError as exc:
        raise ForwardStockSelectionPolicyError("forward construction parent failed authentication") from exc
    if (
        ancestor["capabilities"] != _FALSE_CAPABILITIES
        or ancestor["independent_confirmation_authorized"] is not False
        or tuple(ancestor["future_universe"]) != tuple(value["universe_ids"])
    ):
        raise ForwardStockSelectionPolicyError("forward construction parent authority or cohort changed")
    qcom = ancestor["qcom_stock_admission"]
    if (
        qcom["special_exclusion"] is not False
        or qcom["display_ticker_is_identity"] is not False
        or qcom["ticker_alias_repair"] is not False
        or tuple(qcom["all_required"]) != (
            "finite_positive_market_cap_for_exact_qc_sid",
            "finite_positive_etf_member_weight_for_exact_qc_sid",
            "finite_positive_tradable_reference_price_for_exact_qc_sid",
        )
    ):
        raise ForwardStockSelectionPolicyError("forward construction parent QCOM rule changed")
    signals = ancestor["signal_semantics"]
    control = signals["control"]
    arms = signals["arms"]
    if (
        control["forward_candidate_id"] != value["stock_selection"]["ar_off_control"]["candidate_id"]
        or control["ar_entry_count_enabled"] is not False
        or control["ar_weight_transfer_fraction"] != "0.00"
        or len(arms) != 2
        or tuple(arm["forward_candidate_id"] for arm in arms) != tuple(
            row["candidate_id"] for row in value["stock_selection"]["ar_on_arms"]
        )
        or any(
            arm["ar_entry_count_enabled"] is not True
            or arm["ar_weight_transfer_fraction"] != fraction
            for arm, fraction in zip(arms, ("1.00", "2.00"), strict=True)
        )
    ):
        raise ForwardStockSelectionPolicyError("forward construction parent signal modes changed")


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def load_policy():
    """Authenticate exact canonical bytes and the reviewed construction parent."""
    try:
        raw = POLICY_PATH.read_bytes()
    except OSError as exc:
        raise ForwardStockSelectionPolicyError("forward stock-selection policy unavailable") from exc
    if len(raw) > 16_384 or hashlib.sha256(raw).hexdigest() != FROZEN_POLICY_SHA256:
        raise ForwardStockSelectionPolicyError("forward stock-selection policy hash changed")
    try:
        value = json.loads(
            raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ForwardStockSelectionPolicyError("forward stock selection is not JSON") from exc
    validate_policy(value)
    if raw != (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("ascii"):
        raise ForwardStockSelectionPolicyError("forward stock selection is not canonical JSON")
    _verify_parent(value)
    return _freeze(value)


__all__ = [
    "ForwardStockSelectionPolicyError", "FROZEN_POLICY_SHA256", "POLICY_PATH",
    "load_policy", "validate_policy",
]
