"""Outcome-free future construction successor for the owner's 100/200 rules.

This choice follows adaptive historical exploration. It binds no future input,
execution, epoch, confirmatory look, QuantConnect job, or paper order authority.
"""

import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from . import six_universe_qcom_exclusion_dual_forward_policy as parent


class ForwardConstructionPolicyError(ValueError):
    """The frozen future construction or its historical parent changed."""


POLICY_PATH = Path(__file__).with_suffix(".json")
FROZEN_POLICY_SHA256 = "7f1dbfe54f8179add6db9b15abdf343e55253ba50541175a5764e4c15dc644d4"
_PARENT_SHA256 = "668a52c2dfb541e4be92675d354a3c405f4b5689519dcd923a3e7c633675d59d"
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
_EXPECTED = {
    "adaptive_selection_disclosure": (
        "chosen_after_adaptive_historical_exploration_not_a_holdout_or_forward_efficacy_result"
    ),
    "analyst_event_identity": {
        "ar_contribution_requires": (
            "reviewed_vendor_security_to_exact_qc_sid_mapping_as_of_decision"
        ),
        "ticker_only_join_authorized": False,
        "unmapped_event_is_zero_signal": False,
        "unmapped_or_ambiguous_event": "named_refusal_no_ar_contribution",
    },
    "capabilities": _FALSE_CAPABILITIES,
    "common_eligible_cohort_required": True,
    "forward_end_session": None,
    "forward_evidence_epoch_sha256": None,
    "forward_start_session": None,
    "future_common_predecision_input_contract_sha256": None,
    "future_shared_execution_contract_sha256": None,
    "future_universe": ["SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE"],
    "independent_confirmation_authorized": False,
    "paper_algorithm_sha256": None,
    "paper_deployment_authority_sha256": None,
    "parent_dual_forward_policy_sha256": _PARENT_SHA256,
    "qcom_stock_admission": {
        "all_required": [
            "finite_positive_market_cap_for_exact_qc_sid",
            "finite_positive_etf_member_weight_for_exact_qc_sid",
            "finite_positive_tradable_reference_price_for_exact_qc_sid",
        ],
        "display_ticker_is_identity": False,
        "special_exclusion": False,
        "ticker_alias_repair": False,
    },
    "schema": "arv2-six-universe-forward-construction-policy-v1",
    "signal_semantics": {
        "arms": [
            {
                "ar_entry_count_enabled": True,
                "ar_weight_transfer_fraction": "1.00",
                "forward_candidate_id": "ARV2_FORWARD_AR_100",
            },
            {
                "ar_entry_count_enabled": True,
                "ar_weight_transfer_fraction": "2.00",
                "forward_candidate_id": "ARV2_FORWARD_AR_200",
            },
        ],
        "control": {
            "ar_entry_count_enabled": False,
            "ar_weight_transfer_fraction": "0.00",
            "forward_candidate_id": "ARV2_FORWARD_AR_OFF",
        },
    },
    "two_arm_confirmatory_multiplicity_protocol_sha256": None,
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
    """Refuse changed semantics, type aliases, unknown fields and authority."""
    if not _exact(value, _EXPECTED):
        raise ForwardConstructionPolicyError("forward construction policy changed")
    return value


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ForwardConstructionPolicyError("forward construction has duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(value):
    raise ForwardConstructionPolicyError(
        f"forward construction has nonfinite JSON value {value}"
    )


def _verify_parent(value):
    if parent.FROZEN_POLICY_SHA256 != _PARENT_SHA256:
        raise ForwardConstructionPolicyError("dual forward parent identity changed")
    try:
        ancestor = parent.load_policy()
    except parent.DualForwardPolicyError as exc:
        raise ForwardConstructionPolicyError(
            "dual forward parent failed authentication"
        ) from exc
    if (
        ancestor["capabilities"] != _FALSE_CAPABILITIES
        or ancestor["future_universe_and_exclusion_policy_sha256"] is not None
        or ancestor["future_shared_execution_contract_sha256"] is not None
        or ancestor["forward_evidence_epoch_sha256"] is not None
        or ancestor["two_arm_confirmatory_multiplicity_protocol_sha256"] is not None
    ):
        raise ForwardConstructionPolicyError("dual forward parent authority changed")
    control = ancestor["control"]
    expected_control = value["signal_semantics"]["control"]
    if (
        control["forward_candidate_id"] != expected_control["forward_candidate_id"]
        or control["tilt_fraction"] != expected_control["ar_weight_transfer_fraction"]
    ):
        raise ForwardConstructionPolicyError("dual forward control changed")
    arms = ancestor["forward_candidates"]
    expected_arms = value["signal_semantics"]["arms"]
    if len(arms) != len(expected_arms) or any(
        arm["forward_candidate_id"] != expected["forward_candidate_id"]
        or arm["tilt_fraction"] != expected["ar_weight_transfer_fraction"]
        for arm, expected in zip(arms, expected_arms, strict=True)
    ):
        raise ForwardConstructionPolicyError("dual forward arms changed")


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def load_policy():
    """Authenticate exact canonical bytes and the dual forward parent."""
    try:
        raw = POLICY_PATH.read_bytes()
    except OSError as exc:
        raise ForwardConstructionPolicyError("forward construction policy unavailable") from exc
    if len(raw) > 8192 or hashlib.sha256(raw).hexdigest() != FROZEN_POLICY_SHA256:
        raise ForwardConstructionPolicyError("forward construction policy hash changed")
    try:
        value = json.loads(
            raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ForwardConstructionPolicyError("forward construction is not JSON") from exc
    validate_policy(value)
    if raw != (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("ascii"):
        raise ForwardConstructionPolicyError("forward construction is not canonical JSON")
    _verify_parent(value)
    return _freeze(value)


__all__ = [
    "ForwardConstructionPolicyError", "FROZEN_POLICY_SHA256", "POLICY_PATH",
    "load_policy", "validate_policy",
]
