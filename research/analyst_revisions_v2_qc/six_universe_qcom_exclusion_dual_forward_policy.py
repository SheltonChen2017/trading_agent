"""Read-only successor recording the owner's two AR forward-development rules.

This choice follows exploratory historical results. It does not open a QC run,
allocate the sole formal look, define a paper epoch, or permit winner picking.
"""

import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_ar_range_policy as parent


class DualForwardPolicyError(ValueError):
    """The frozen two-arm decision or its historical parent did not authenticate."""


POLICY_PATH = Path(__file__).with_suffix(".json")
FROZEN_POLICY_SHA256 = "668a52c2dfb541e4be92675d354a3c405f4b5689519dcd923a3e7c633675d59d"
_PARENT_SHA256 = "6de2649a80abe6660ae2399843f5b54ae24ebfcdae35ac863c0bd77ef4e4a98c"
_BASE_SHA256 = "53b4ec88db97007ee9ffa4f950935df935cda68ac6f68ee7a446cbee019492c0"
_TILT_SHA256 = "3a5532ebcda49695fcf29e964af5ca7c79e7c29cec773f2814d17408af0ddbb4"
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
    "authority": "owner_selected_forward_development_rules_only_no_qc_or_outcome_authority",
    "capabilities": _FALSE_CAPABILITIES,
    "control": {
        "forward_candidate_id": "ARV2_FORWARD_AR_OFF",
        "historical_candidate_id": "R231",
        "historical_manifest_sha256": _BASE_SHA256,
        "tilt_fraction": "0.00",
    },
    "effective_multiplicity_overlay_sha256": (
        "2e9f390ec54f01e6635b67972711c38212a5f853489e16c1de2a508212278648"
    ),
    "formal_lane_alpha": "1/80",
    "formal_look_budget": 1,
    "forward_candidates": [
        {
            "forward_candidate_id": "ARV2_FORWARD_AR_100",
            "historical_candidate_id": "R232",
            "historical_manifest_sha256": _BASE_SHA256,
            "tilt_fraction": "1.00",
            "tilt_percent": 100,
        },
        {
            "forward_candidate_id": "ARV2_FORWARD_AR_200",
            "historical_candidate_id": "R237",
            "historical_manifest_sha256": _TILT_SHA256,
            "tilt_fraction": "2.00",
            "tilt_percent": 200,
        },
    ],
    "forward_end_session": None,
    "forward_evidence_epoch_sha256": None,
    "forward_one_blinded_epoch_required": True,
    "forward_shared_clock_cohort_data_cost_fill_required": True,
    "forward_start_session": None,
    "future_shared_execution_contract_sha256": None,
    "future_universe_and_exclusion_policy_sha256": None,
    "historical_provenance_rule": (
        "parent_qcom_excluded_all_six_25pct_five_name_order_construction_"
        "not_automatically_a_future_universe_rule"
    ),
    "historical_result_selection_authorized": False,
    "owner_decision": "two_parallel_forward_development_candidates_no_post_hoc_winner_choice",
    "parent_range_policy_sha256": _PARENT_SHA256,
    "paper_algorithm_sha256": None,
    "per_arm_confirmatory_alpha": None,
    "schema": "arv2-qcom-excluded-dual-forward-ar-policy-v1",
    "study_classification": "forward_development_rule_selection_only_not_confirmation",
    "two_arm_confirmation_authorized": False,
    "two_arm_confirmatory_multiplicity_protocol_sha256": None,
    "two_arm_same_dates_universe_admission_and_costs_required": True,
    "two_arm_separate_reporting_required": True,
    "winner_selection_authorized": False,
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
    """Reject changed rules, added authority, unknown fields and type aliases."""
    if not _exact(value, _EXPECTED):
        raise DualForwardPolicyError("dual forward AR policy changed")
    return value


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise DualForwardPolicyError("dual forward AR policy has duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(value):
    raise DualForwardPolicyError(f"dual forward AR policy has nonfinite JSON value {value}")


def _verify_parent(value):
    if parent.FROZEN_POLICY_SHA256 != _PARENT_SHA256:
        raise DualForwardPolicyError("dual forward AR parent identity changed")
    try:
        ancestor = parent.load_policy()
    except parent.ArRangePolicyError as exc:
        raise DualForwardPolicyError("dual forward AR parent failed authentication") from exc
    if (ancestor["control"]["candidate_id"] != value["control"]["historical_candidate_id"]
            or ancestor["control"]["manifest_sha256"] != value["control"]["historical_manifest_sha256"]
            or ancestor["control"]["tilt_fraction"] != value["control"]["tilt_fraction"]):
        raise DualForwardPolicyError("dual forward AR control differs from parent")
    for arm in value["forward_candidates"]:
        matches = [candidate for candidate in ancestor["existing_arms"]
                   if candidate["candidate_id"] == arm["historical_candidate_id"]]
        if len(matches) != 1:
            raise DualForwardPolicyError("dual forward AR arm absent from parent")
        old = matches[0]
        if (old["manifest_sha256"] != arm["historical_manifest_sha256"]
                or old["tilt_fraction"] != arm["tilt_fraction"]
                or old["tilt_percent"] != arm["tilt_percent"]):
            raise DualForwardPolicyError("dual forward AR arm differs from parent")


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def load_policy():
    """Authenticate the successor and all parent manifests; return frozen data."""
    try:
        raw = POLICY_PATH.read_bytes()
    except OSError as exc:
        raise DualForwardPolicyError("dual forward AR policy unavailable") from exc
    if len(raw) > 8192 or hashlib.sha256(raw).hexdigest() != FROZEN_POLICY_SHA256:
        raise DualForwardPolicyError("dual forward AR policy hash changed")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DualForwardPolicyError("dual forward AR policy is not JSON") from exc
    validate_policy(value)
    if raw != (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("ascii"):
        raise DualForwardPolicyError("dual forward AR policy is not canonical JSON")
    _verify_parent(value)
    return _freeze(value)


__all__ = ["DualForwardPolicyError", "FROZEN_POLICY_SHA256", "POLICY_PATH",
           "load_policy", "validate_policy"]
