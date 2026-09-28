"""The AR range freeze is a read-only grid, with no selected primary rule."""

import copy
import hashlib
import json
import shutil

import pytest

from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_ar_range_policy as subject


def _raw_policy():
    return json.loads(subject.POLICY_PATH.read_bytes())


def test_frozen_policy_binds_exact_grid_prior_manifests_and_no_authority():
    raw = subject.POLICY_PATH.read_bytes()
    value = _raw_policy()
    assert hashlib.sha256(raw).hexdigest() == subject.FROZEN_POLICY_SHA256
    assert raw == (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("ascii")
    assert subject.validate_policy(value) is value
    loaded = subject.load_policy()
    assert loaded["grid_percent"] == (60, 80, 100, 120, 140, 160, 180, 200)
    assert loaded["missing_unrun_percent"] == (60, 140, 160, 180)
    assert [(arm["tilt_percent"], arm["candidate_id"]) for arm in loaded["existing_arms"]] == [
        (80, "R235"), (100, "R232"), (120, "R236"), (200, "R237")]
    assert loaded["control"]["candidate_id"] == "R231"
    assert loaded["construction"]["selection_policy"].startswith("all_six_25pct_")
    assert loaded["construction"]["minimum_verified_stock_name_count"] == 5
    assert loaded["primary_prospective_setting"]["state"] == "owner_decision_pending"
    assert loaded["primary_prospective_setting"]["tilt_percent"] is None
    assert loaded["historical_result_selection_authorized"] is False
    assert loaded["interpolation_authorized"] is False
    assert loaded["study_classification"] == "adaptive_exploratory_no_confirmatory_claim"
    assert all(enabled is False for enabled in loaded["capabilities"].values())
    with pytest.raises(TypeError):
        loaded["existing_arms"][0]["candidate_id"] = "R000"


@pytest.mark.parametrize("change", (
    "grid_gap", "grid_bool", "interpolation", "winner_selection", "missing_arm", "unrun_reclassified",
    "wrong_control", "wrong_manifest", "wrong_fraction", "wrong_coverage",
    "wrong_name_floor", "wrong_cost", "wrong_slippage", "selected_primary",
    "qc_authority", "confirmation", "extra_field",
))
def test_policy_refuses_aliases_selection_and_economic_changes(change):
    value = _raw_policy()
    if change == "grid_gap":
        value["grid_percent"][4] = 150
    elif change == "grid_bool":
        value["grid_percent"][0] = True
    elif change == "interpolation":
        value["interpolation_authorized"] = True
    elif change == "winner_selection":
        value["historical_result_selection_authorized"] = True
    elif change == "missing_arm":
        value["existing_arms"].pop()
    elif change == "unrun_reclassified":
        value["missing_unrun_percent"].remove(140)
    elif change == "wrong_control":
        value["control"]["candidate_id"] = "R238"
    elif change == "wrong_manifest":
        value["existing_arms"][0]["manifest_sha256"] = "f" * 64
    elif change == "wrong_fraction":
        value["existing_arms"][1]["tilt_fraction"] = "2.00"
    elif change == "wrong_coverage":
        value["construction"]["selection_policy"] = (
            "all_six_10pct_verified_subset_top10_equal_slots_residual_own_ETF")
    elif change == "wrong_name_floor":
        value["construction"]["minimum_verified_stock_name_count"] = 3
    elif change == "wrong_cost":
        value["construction"]["cost_bps_per_side"] = "0"
    elif change == "wrong_slippage":
        value["construction"]["slippage_bps_per_side"] = 5
    elif change == "selected_primary":
        value["primary_prospective_setting"]["tilt_percent"] = 200
    elif change == "qc_authority":
        value["capabilities"]["qc_launch"] = True
    elif change == "confirmation":
        value["study_classification"] = "confirmation"
    else:
        value["return_winner"] = "R237"
    with pytest.raises(subject.ArRangePolicyError, match="policy changed"):
        subject.validate_policy(value)


def test_loader_rejects_policy_mutation_and_prior_manifest_drift(tmp_path, monkeypatch):
    original_policy = subject.POLICY_PATH.read_bytes()
    for filename in (
        subject.POLICY_PATH.name,
        "six_universe_qcom_exclusion_candidates.json",
        "six_universe_qcom_exclusion_tilt_candidates.json",
    ):
        shutil.copyfile(subject.POLICY_PATH.with_name(filename), tmp_path / filename)
    monkeypatch.setattr(subject, "POLICY_PATH", tmp_path / subject.POLICY_PATH.name)
    assert subject.load_policy()["control"]["candidate_id"] == "R231"

    changed = copy.deepcopy(_raw_policy())
    changed["primary_prospective_setting"]["tilt_percent"] = 200
    subject.POLICY_PATH.write_bytes((json.dumps(changed, sort_keys=True, indent=2) + "\n").encode("ascii"))
    with pytest.raises(subject.ArRangePolicyError, match="hash changed"):
        subject.load_policy()

    subject.POLICY_PATH.write_bytes(original_policy)
    base = tmp_path / "six_universe_qcom_exclusion_candidates.json"
    base.write_bytes(base.read_bytes() + b" ")
    with pytest.raises(subject.ArRangePolicyError, match="hash changed"):
        subject.load_policy()
