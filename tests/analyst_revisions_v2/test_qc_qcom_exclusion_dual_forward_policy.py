"""The owner-selected 100/200 forward rules do not inherit QC authority."""

import copy
import hashlib
import json
from types import MappingProxyType

import pytest

from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_ar_range_policy as parent
from research.analyst_revisions_v2_qc import six_universe_qcom_exclusion_dual_forward_policy as subject
from research.analyst_revisions_v2.four_family_multiplicity import (
    OVERLAY_ARTIFACT_SHA256,
    PERMANENT_LANE_ALPHA,
)


def _raw_policy():
    return json.loads(subject.POLICY_PATH.read_bytes())


def test_two_named_forward_rules_are_frozen_without_result_or_paper_authority():
    raw = subject.POLICY_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == subject.FROZEN_POLICY_SHA256
    assert raw == (json.dumps(_raw_policy(), sort_keys=True, indent=2) + "\n").encode("ascii")
    loaded = subject.load_policy()
    assert isinstance(loaded, MappingProxyType)
    assert [arm["forward_candidate_id"] for arm in loaded["forward_candidates"]] == [
        "ARV2_FORWARD_AR_100", "ARV2_FORWARD_AR_200"]
    assert [arm["tilt_percent"] for arm in loaded["forward_candidates"]] == [100, 200]
    assert loaded["control"]["forward_candidate_id"] == "ARV2_FORWARD_AR_OFF"
    assert loaded["winner_selection_authorized"] is False
    assert loaded["historical_result_selection_authorized"] is False
    assert loaded["two_arm_confirmation_authorized"] is False
    assert loaded["two_arm_confirmatory_multiplicity_protocol_sha256"] is None
    assert loaded["effective_multiplicity_overlay_sha256"] == OVERLAY_ARTIFACT_SHA256
    assert loaded["formal_lane_alpha"] == str(PERMANENT_LANE_ALPHA)
    assert loaded["formal_look_budget"] == 1
    assert loaded["per_arm_confirmatory_alpha"] is None
    assert loaded["forward_evidence_epoch_sha256"] is None
    assert loaded["forward_start_session"] is None
    assert loaded["forward_end_session"] is None
    assert loaded["future_universe_and_exclusion_policy_sha256"] is None
    assert loaded["future_shared_execution_contract_sha256"] is None
    assert loaded["forward_one_blinded_epoch_required"] is True
    assert loaded["forward_shared_clock_cohort_data_cost_fill_required"] is True
    assert "not_automatically_a_future_universe_rule" in loaded["historical_provenance_rule"]
    assert all(enabled is False for enabled in loaded["capabilities"].values())
    with pytest.raises(TypeError):
        loaded["forward_candidates"][0]["tilt_percent"] = 200
    assert parent.load_policy()["primary_prospective_setting"]["state"] == "owner_decision_pending"


@pytest.mark.parametrize("change", (
    "remove_100", "swap_order", "wrong_200_fraction", "bool_percent",
    "wrong_reference", "winner", "historical_winner", "confirmation",
    "multiplicity_assumed", "two_full_alpha_looks", "two_full_alpha_cells",
    "overlay_changed", "epoch_assumed",
    "future_universe_assumed", "future_execution_assumed", "dates_assumed",
    "paper", "qc_launch", "outcome", "not_same_dates", "not_separate",
    "not_one_epoch", "not_shared_execution",
    "extra_field",
))
def test_policy_refuses_one_arm_winner_selection_and_authority_changes(change):
    value = copy.deepcopy(_raw_policy())
    if change == "remove_100":
        value["forward_candidates"].pop(0)
    elif change == "swap_order":
        value["forward_candidates"].reverse()
    elif change == "wrong_200_fraction":
        value["forward_candidates"][1]["tilt_fraction"] = "1.00"
    elif change == "bool_percent":
        value["forward_candidates"][0]["tilt_percent"] = True
    elif change == "wrong_reference":
        value["forward_candidates"][1]["historical_candidate_id"] = "R236"
    elif change == "winner":
        value["winner_selection_authorized"] = True
    elif change == "historical_winner":
        value["historical_result_selection_authorized"] = True
    elif change == "confirmation":
        value["two_arm_confirmation_authorized"] = True
    elif change == "multiplicity_assumed":
        value["two_arm_confirmatory_multiplicity_protocol_sha256"] = "0" * 64
    elif change == "two_full_alpha_looks":
        value["formal_look_budget"] = 2
    elif change == "two_full_alpha_cells":
        value["per_arm_confirmatory_alpha"] = "1/80"
    elif change == "overlay_changed":
        value["effective_multiplicity_overlay_sha256"] = "0" * 64
    elif change == "epoch_assumed":
        value["forward_evidence_epoch_sha256"] = "0" * 64
    elif change == "future_universe_assumed":
        value["future_universe_and_exclusion_policy_sha256"] = "0" * 64
    elif change == "future_execution_assumed":
        value["future_shared_execution_contract_sha256"] = "0" * 64
    elif change == "dates_assumed":
        value["forward_start_session"] = "2026-09-28"
    elif change == "paper":
        value["capabilities"]["paper_deployment"] = True
    elif change == "qc_launch":
        value["capabilities"]["qc_launch"] = True
    elif change == "outcome":
        value["capabilities"]["outcome_access"] = True
    elif change == "not_same_dates":
        value["two_arm_same_dates_universe_admission_and_costs_required"] = False
    elif change == "not_separate":
        value["two_arm_separate_reporting_required"] = False
    elif change == "not_one_epoch":
        value["forward_one_blinded_epoch_required"] = False
    elif change == "not_shared_execution":
        value["forward_shared_clock_cohort_data_cost_fill_required"] = False
    else:
        value["preferred_winner"] = "ARV2_FORWARD_AR_200"
    with pytest.raises(subject.DualForwardPolicyError, match="policy changed"):
        subject.validate_policy(value)


def test_loader_refuses_changed_bytes_and_parent_identity(tmp_path, monkeypatch):
    raw = subject.POLICY_PATH.read_bytes()
    policy = tmp_path / subject.POLICY_PATH.name
    policy.write_bytes(raw)
    monkeypatch.setattr(subject, "POLICY_PATH", policy)
    assert subject.load_policy()["forward_candidates"][0]["tilt_percent"] == 100

    policy.write_bytes(raw + b" ")
    with pytest.raises(subject.DualForwardPolicyError, match="hash changed"):
        subject.load_policy()
    policy.write_bytes(raw)
    monkeypatch.setattr(parent, "FROZEN_POLICY_SHA256", "f" * 64)
    with pytest.raises(subject.DualForwardPolicyError, match="parent identity changed"):
        subject.load_policy()
