"""Outcome-free lock for the discrete QCOM-excluded AR transfer range.

This artifact records prior candidate identities and missing grid points. It
does not create a new QC candidate, choose a prospective rule, or read results.
"""

import hashlib
import json
from pathlib import Path
from types import MappingProxyType


class ArRangePolicyError(ValueError):
    """The range artifact or one of its frozen ancestors changed."""


POLICY_PATH = Path(__file__).with_name("six_universe_qcom_exclusion_ar_range_policy.json")
FROZEN_POLICY_SHA256 = "6de2649a80abe6660ae2399843f5b54ae24ebfcdae35ac863c0bd77ef4e4a98c"
_BASE_NAME = "six_universe_qcom_exclusion_candidates.json"
_BASE_SHA256 = "53b4ec88db97007ee9ffa4f950935df935cda68ac6f68ee7a446cbee019492c0"
_TILT_NAME = "six_universe_qcom_exclusion_tilt_candidates.json"
_TILT_SHA256 = "3a5532ebcda49695fcf29e964af5ca7c79e7c29cec773f2814d17408af0ddbb4"
_AR_ON_BASELINE_SHA256 = "f03e7f0f9669e3d5168511a9c05cf5e0b9c2c88801fc87433d990537c333615d"
_EXCLUDED_SHA256 = "12e2fb85270ad4370a284866d825f3a6cf121a92c997c3557861e6d08a7a6a1f"
_PACKAGE_SHA256 = "7803b84f0841f9685a4951de58fbccf82f3f647cef7beffce31cb4865ea14e1f"
_ACTIVATION_SHA256 = "69b663c35b245e965b2d4e1f8402b3b14432d6d713f387eacb888f6756e78a41"
_GRID = [60, 80, 100, 120, 140, 160, 180, 200]
_UNRUN = [60, 140, 160, 180]
_ARMS = [
    {"candidate_id": "R235", "manifest_sha256": _TILT_SHA256,
     "tilt_fraction": "0.80", "tilt_percent": 80},
    {"candidate_id": "R232", "manifest_sha256": _BASE_SHA256,
     "tilt_fraction": "1.00", "tilt_percent": 100},
    {"candidate_id": "R236", "manifest_sha256": _TILT_SHA256,
     "tilt_fraction": "1.20", "tilt_percent": 120},
    {"candidate_id": "R237", "manifest_sha256": _TILT_SHA256,
     "tilt_fraction": "2.00", "tilt_percent": 200},
]
_CONSTRUCTION = {
    "activation_manifest_sha256": _ACTIVATION_SHA256,
    "admission_leverage": "2",
    "cadence": "weekly_prior_session_decision_next_open_MOO",
    "cost_bps_per_side": "10",
    "decision_count": 261,
    "excluded_stock_security_id_sha256": _EXCLUDED_SHA256,
    "exclusion_rule": "qcom_stock_eligibility_after_coverage_v1",
    "first_session": "2021-01-04",
    "last_session": "2025-12-31",
    "minimum_positive_score_count": 5,
    "minimum_verified_stock_name_count": 5,
    "observation_count": 1255,
    "package_sha256": _PACKAGE_SHA256,
    "reference_repair_enabled": True,
    "selection_policy": "all_six_25pct_verified_subset_top10_equal_slots_residual_own_ETF",
    "slippage_bps_per_side": 0,
    "target_gross_exposure": "0.98",
}
_EXPECTED = {
    "authority": "outcome_free_rule_grid_only_no_qc_look_deployment_or_order_authority",
    "capabilities": {
        "confirmatory_look_commitment": False,
        "funded_deployment": False,
        "orders": False,
        "outcome_access": False,
        "paper_deployment": False,
        "qc_compile": False,
        "qc_launch": False,
        "qc_upload": False,
    },
    "construction": _CONSTRUCTION,
    "control": {"candidate_id": "R231", "manifest_sha256": _BASE_SHA256,
                "tilt_fraction": "0.00"},
    "existing_arms": _ARMS,
    "grid_percent": _GRID,
    "historical_result_selection_authorized": False,
    "interpolation_authorized": False,
    "missing_unrun_percent": _UNRUN,
    "primary_prospective_setting": {"state": "owner_decision_pending", "tilt_percent": None},
    "schema": "arv2-qcom-excluded-ar-weight-transfer-range-policy-v1",
    "study_classification": "adaptive_exploratory_no_confirmatory_claim",
    "tilt_definition": "rank_scaled_transfer_capacity_relative_to_each_stock_own_post_cap_baseline_weight",
}


def _exact(actual, expected):
    """Require equal values and types, so bool cannot impersonate int."""
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(
            _exact(actual[key], item) for key, item in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(
            _exact(left, right) for left, right in zip(actual, expected))
    return actual == expected


def validate_policy(value):
    """Reject additions, aliases, a chosen primary, or changed economics."""
    if not _exact(value, _EXPECTED):
        raise ArRangePolicyError("QCOM-excluded AR range policy changed")
    return value


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ArRangePolicyError("range ancestor has duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(value):
    raise ArRangePolicyError(f"range artifact has nonfinite JSON value {value}")


def _read_pinned(path, expected_sha256):
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ArRangePolicyError("range artifact or frozen ancestor unavailable") from exc
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ArRangePolicyError("range artifact or frozen ancestor hash changed")
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs,
                          parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ArRangePolicyError("range artifact or frozen ancestor is not JSON") from exc


def _candidate(manifest, candidate_id):
    rows = manifest.get("candidates") if type(manifest) is dict else None
    if type(rows) is not list:
        raise ArRangePolicyError("frozen range ancestor lacks candidates")
    matches = [row for row in rows if type(row) is dict
               and row.get("candidate_id") == candidate_id]
    if len(matches) != 1:
        raise ArRangePolicyError("frozen range candidate is missing or ambiguous")
    return matches[0]


def _verify_ancestors(value, directory):
    base = _read_pinned(directory / _BASE_NAME, _BASE_SHA256)
    tilt = _read_pinned(directory / _TILT_NAME, _TILT_SHA256)
    for manifest in (base, tilt):
        if (type(manifest) is not dict
                or manifest.get("package_sha256") != _PACKAGE_SHA256
                or manifest.get("activation_manifest_sha256") != _ACTIVATION_SHA256
                or type(manifest.get("protocol")) is not dict):
            raise ArRangePolicyError("frozen range input lineage changed")
        protocol = manifest["protocol"]
        for key in ("admission_leverage", "cadence", "cost_bps_per_side",
                    "decision_count", "excluded_stock_security_id_sha256",
                    "exclusion_rule", "first_session", "last_session",
                    "observation_count", "selection_policy", "target_gross_exposure"):
            if not _exact(protocol.get(key), value["construction"][key]):
                raise ArRangePolicyError("frozen range construction changed")
        if (type(protocol.get("slippage_bps")) is not list
                or 0 not in protocol["slippage_bps"]
                or protocol.get("confirmation") is not False
                or protocol.get("sensitivity_only") is not True):
            raise ArRangePolicyError("frozen range study class changed")
    if (tilt["protocol"].get("control_candidate_id") != "R231"
            or tilt["protocol"].get("control_manifest_sha256") != _BASE_SHA256):
        raise ArRangePolicyError("frozen range control binding changed")
    references = [value["control"], *value["existing_arms"]]
    for reference in references:
        manifest = base if reference["manifest_sha256"] == _BASE_SHA256 else tilt
        row = _candidate(manifest, reference["candidate_id"])
        if (row.get("tilt_fraction") != reference["tilt_fraction"]
                or row.get("slippage_bps") != 0
                or row.get("kind") != "order"
                or row.get("excluded_stock_security_id_sha256") != _EXCLUDED_SHA256
                or row.get("reference_repair_enabled") is not True
                or (reference is not value["control"] and
                    row.get("matched_baseline_profile_sha256") != _AR_ON_BASELINE_SHA256)):
            raise ArRangePolicyError("frozen range candidate economics changed")


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def load_policy():
    """Read only the policy and two prior manifests; return immutable fields."""
    value = validate_policy(_read_pinned(POLICY_PATH, FROZEN_POLICY_SHA256))
    _verify_ancestors(value, POLICY_PATH.parent)
    return _freeze(value)


__all__ = ["ArRangePolicyError", "FROZEN_POLICY_SHA256", "POLICY_PATH",
           "load_policy", "validate_policy"]
