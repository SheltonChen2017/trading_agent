"""The future six-universe choice is immutable but creates no QC authority."""

import copy
import hashlib
import json
from types import MappingProxyType

import pytest

from research.analyst_revisions_v2_qc import (
    six_universe_forward_construction_policy as subject,
)
from research.analyst_revisions_v2_qc import (
    six_universe_qcom_exclusion_dual_forward_policy as parent,
)


def _raw_policy():
    return json.loads(subject.POLICY_PATH.read_bytes())


def test_exact_parent_cohort_qcom_and_three_signal_rules_have_no_action_authority():
    raw = subject.POLICY_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == subject.FROZEN_POLICY_SHA256
    assert raw == (json.dumps(_raw_policy(), sort_keys=True, indent=2) + "\n").encode("ascii")
    value = subject.load_policy()
    assert isinstance(value, MappingProxyType)
    assert value["parent_dual_forward_policy_sha256"] == parent.FROZEN_POLICY_SHA256
    assert value["future_universe"] == ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")
    assert value["common_eligible_cohort_required"] is True
    qcom = value["qcom_stock_admission"]
    assert qcom["all_required"] == (
        "finite_positive_market_cap_for_exact_qc_sid",
        "finite_positive_etf_member_weight_for_exact_qc_sid",
        "finite_positive_tradable_reference_price_for_exact_qc_sid",
    )
    assert qcom["display_ticker_is_identity"] is False
    assert qcom["special_exclusion"] is False
    assert qcom["ticker_alias_repair"] is False
    event_identity = value["analyst_event_identity"]
    assert event_identity["ar_contribution_requires"] == (
        "reviewed_vendor_security_to_exact_qc_sid_mapping_as_of_decision"
    )
    assert event_identity["ticker_only_join_authorized"] is False
    assert event_identity["unmapped_event_is_zero_signal"] is False
    assert event_identity["unmapped_or_ambiguous_event"] == (
        "named_refusal_no_ar_contribution"
    )
    semantics = value["signal_semantics"]
    assert semantics["control"] == {
        "ar_entry_count_enabled": False,
        "ar_weight_transfer_fraction": "0.00",
        "forward_candidate_id": "ARV2_FORWARD_AR_OFF",
    }
    assert tuple(
        (arm["forward_candidate_id"], arm["ar_entry_count_enabled"],
         arm["ar_weight_transfer_fraction"])
        for arm in semantics["arms"]
    ) == (
        ("ARV2_FORWARD_AR_100", True, "1.00"),
        ("ARV2_FORWARD_AR_200", True, "2.00"),
    )
    assert "adaptive_historical_exploration" in value["adaptive_selection_disclosure"]
    assert value["independent_confirmation_authorized"] is False
    assert all(enabled is False for enabled in value["capabilities"].values())
    for key in (
        "forward_start_session", "forward_end_session", "forward_evidence_epoch_sha256",
        "future_common_predecision_input_contract_sha256",
        "future_shared_execution_contract_sha256",
        "two_arm_confirmatory_multiplicity_protocol_sha256",
        "paper_algorithm_sha256", "paper_deployment_authority_sha256",
    ):
        assert value[key] is None
    with pytest.raises(TypeError):
        value["signal_semantics"]["arms"][0]["ar_entry_count_enabled"] = False


@pytest.mark.parametrize("change", (
    "different_universe", "universe_order", "cohort_disabled",
    "qcom_cap_removed", "qcom_membership_removed", "qcom_price_removed",
    "ticker_alias", "display_ticker_join", "qcom_exclusion",
    "mapping_requirement", "mapping_ticker", "mapping_zero", "mapping_refusal",
    "entry_off_100", "entry_off_200", "entry_on_control",
    "fraction_100", "fraction_200", "fraction_bool", "arm_order",
    "control_name", "winner_claim", "confirmation", "qc_launch", "orders",
    "funded", "paper", "outcome", "common_input_bound", "execution_bound",
    "epoch_bound", "start_bound", "end_bound", "multiplicity_bound",
    "paper_algorithm_bound", "paper_authority_bound", "parent_changed",
    "extra_field",
))
def test_changed_construction_or_authority_is_refused(change):
    value = copy.deepcopy(_raw_policy())
    qcom = value["qcom_stock_admission"]
    mapping = value["analyst_event_identity"]
    semantics = value["signal_semantics"]
    if change == "different_universe":
        value["future_universe"][-1] = "XLF"
    elif change == "universe_order":
        value["future_universe"].reverse()
    elif change == "cohort_disabled":
        value["common_eligible_cohort_required"] = False
    elif change == "qcom_cap_removed":
        qcom["all_required"].pop(0)
    elif change == "qcom_membership_removed":
        qcom["all_required"].pop(1)
    elif change == "qcom_price_removed":
        qcom["all_required"].pop(2)
    elif change == "ticker_alias":
        qcom["ticker_alias_repair"] = True
    elif change == "display_ticker_join":
        qcom["display_ticker_is_identity"] = True
    elif change == "qcom_exclusion":
        qcom["special_exclusion"] = True
    elif change == "mapping_requirement":
        mapping["ar_contribution_requires"] = "display_ticker_join"
    elif change == "mapping_ticker":
        mapping["ticker_only_join_authorized"] = True
    elif change == "mapping_zero":
        mapping["unmapped_event_is_zero_signal"] = True
    elif change == "mapping_refusal":
        mapping["unmapped_or_ambiguous_event"] = "silently_drop"
    elif change == "entry_off_100":
        semantics["arms"][0]["ar_entry_count_enabled"] = False
    elif change == "entry_off_200":
        semantics["arms"][1]["ar_entry_count_enabled"] = False
    elif change == "entry_on_control":
        semantics["control"]["ar_entry_count_enabled"] = True
    elif change == "fraction_100":
        semantics["arms"][0]["ar_weight_transfer_fraction"] = "0.80"
    elif change == "fraction_200":
        semantics["arms"][1]["ar_weight_transfer_fraction"] = "1.20"
    elif change == "fraction_bool":
        semantics["arms"][0]["ar_weight_transfer_fraction"] = True
    elif change == "arm_order":
        semantics["arms"].reverse()
    elif change == "control_name":
        semantics["control"]["forward_candidate_id"] = "ARV2_FORWARD_AR_100"
    elif change == "winner_claim":
        value["adaptive_selection_disclosure"] = "selected_winner"
    elif change == "confirmation":
        value["independent_confirmation_authorized"] = True
    elif change == "qc_launch":
        value["capabilities"]["qc_launch"] = True
    elif change == "orders":
        value["capabilities"]["orders"] = True
    elif change == "funded":
        value["capabilities"]["funded_deployment"] = True
    elif change == "paper":
        value["capabilities"]["paper_deployment"] = True
    elif change == "outcome":
        value["capabilities"]["outcome_access"] = True
    elif change == "common_input_bound":
        value["future_common_predecision_input_contract_sha256"] = "0" * 64
    elif change == "execution_bound":
        value["future_shared_execution_contract_sha256"] = "0" * 64
    elif change == "epoch_bound":
        value["forward_evidence_epoch_sha256"] = "0" * 64
    elif change == "start_bound":
        value["forward_start_session"] = "2026-10-01"
    elif change == "end_bound":
        value["forward_end_session"] = "2027-09-30"
    elif change == "multiplicity_bound":
        value["two_arm_confirmatory_multiplicity_protocol_sha256"] = "0" * 64
    elif change == "paper_algorithm_bound":
        value["paper_algorithm_sha256"] = "0" * 64
    elif change == "paper_authority_bound":
        value["paper_deployment_authority_sha256"] = "0" * 64
    elif change == "parent_changed":
        value["parent_dual_forward_policy_sha256"] = "0" * 64
    else:
        value["winner_id"] = "ARV2_FORWARD_AR_200"
    with pytest.raises(subject.ForwardConstructionPolicyError, match="policy changed"):
        subject.validate_policy(value)


@pytest.mark.parametrize("capability", (
    "confirmatory_look_commitment", "funded_deployment", "orders",
    "outcome_access", "paper_deployment", "qc_compile", "qc_launch",
    "qc_upload",
))
def test_each_action_capability_stays_closed(capability):
    value = _raw_policy()
    value["capabilities"][capability] = True
    with pytest.raises(subject.ForwardConstructionPolicyError, match="policy changed"):
        subject.validate_policy(value)


def test_loader_refuses_changed_bytes_even_when_rehashed(tmp_path, monkeypatch):
    raw = subject.POLICY_PATH.read_bytes()
    policy = tmp_path / subject.POLICY_PATH.name
    policy.write_bytes(raw + b" ")
    monkeypatch.setattr(subject, "POLICY_PATH", policy)
    with pytest.raises(subject.ForwardConstructionPolicyError, match="hash changed"):
        subject.load_policy()
    monkeypatch.setattr(subject, "FROZEN_POLICY_SHA256", hashlib.sha256(raw + b" ").hexdigest())
    with pytest.raises(subject.ForwardConstructionPolicyError, match="not canonical JSON"):
        subject.load_policy()


@pytest.mark.parametrize("raw, reason", (
    (b'{"schema":"one","schema":"two"}', "duplicate JSON key"),
    (b'{"schema":NaN}', "nonfinite JSON value"),
))
def test_rehashed_duplicate_or_nonfinite_json_is_refused(raw, reason, tmp_path, monkeypatch):
    policy = tmp_path / subject.POLICY_PATH.name
    policy.write_bytes(raw)
    monkeypatch.setattr(subject, "POLICY_PATH", policy)
    monkeypatch.setattr(subject, "FROZEN_POLICY_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(subject.ForwardConstructionPolicyError, match=reason):
        subject.load_policy()


def test_parent_identity_and_rule_mismatch_refuse(tmp_path, monkeypatch):
    raw = subject.POLICY_PATH.read_bytes()
    policy = tmp_path / subject.POLICY_PATH.name
    policy.write_bytes(raw)
    monkeypatch.setattr(subject, "POLICY_PATH", policy)
    monkeypatch.setattr(parent, "FROZEN_POLICY_SHA256", "0" * 64)
    with pytest.raises(subject.ForwardConstructionPolicyError, match="parent identity changed"):
        subject.load_policy()
    monkeypatch.undo()

    ancestor = json.loads(parent.POLICY_PATH.read_bytes())
    ancestor["forward_candidates"][0]["tilt_fraction"] = "0.80"
    monkeypatch.setattr(parent, "load_policy", lambda: ancestor)
    with pytest.raises(subject.ForwardConstructionPolicyError, match="arms changed"):
        subject.load_policy()


def test_parent_cannot_claim_future_authority_by_mocked_loader(monkeypatch):
    ancestor = json.loads(parent.POLICY_PATH.read_bytes())
    ancestor["future_shared_execution_contract_sha256"] = "0" * 64
    monkeypatch.setattr(parent, "load_policy", lambda: ancestor)
    with pytest.raises(subject.ForwardConstructionPolicyError, match="parent authority changed"):
        subject.load_policy()


@pytest.mark.parametrize("path, alias", (
    (("capabilities", "orders"), 0),
    (("capabilities", "qc_launch"), 0),
    (("common_eligible_cohort_required",), 1),
    (("analyst_event_identity", "ticker_only_join_authorized"), 0),
))
def test_numeric_aliases_of_booleans_are_refused(path, alias):
    """0 == False and 1 == True in Python; only the exact-type check refuses them."""
    value = _raw_policy()
    target = value
    for key in path[:-1]:
        target = target[key]
    assert target[path[-1]] == alias
    target[path[-1]] = alias
    with pytest.raises(subject.ForwardConstructionPolicyError, match="policy changed"):
        subject.validate_policy(value)


@pytest.mark.parametrize("field, changed", (
    ("forward_candidate_id", "ARV2_FORWARD_AR_OFF_RENAMED"),
    ("tilt_fraction", "0.10"),
))
def test_parent_control_mismatch_refuses(monkeypatch, field, changed):
    ancestor = json.loads(parent.POLICY_PATH.read_bytes())
    assert ancestor["control"][field] != changed
    ancestor["control"][field] = changed
    monkeypatch.setattr(parent, "load_policy", lambda: ancestor)
    with pytest.raises(subject.ForwardConstructionPolicyError, match="control changed"):
        subject.load_policy()
