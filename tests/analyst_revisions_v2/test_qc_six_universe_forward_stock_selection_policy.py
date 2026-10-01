"""The adaptive future admission freeze is declarative, not an executable strategy."""

import copy
import hashlib
import json
from types import MappingProxyType

import pytest

from research.analyst_revisions_v2_qc import (
    six_universe_forward_construction_policy as parent,
)
from research.analyst_revisions_v2_qc import (
    six_universe_forward_stock_selection_policy as subject,
)


def _raw_policy():
    return json.loads(subject.POLICY_PATH.read_bytes())


def test_exact_child_freezes_distinct_hybrid_without_action_authority():
    raw = subject.POLICY_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == subject.FROZEN_POLICY_SHA256
    assert raw == (json.dumps(_raw_policy(), sort_keys=True, indent=2) + "\n").encode("ascii")
    value = subject.load_policy()
    assert isinstance(value, MappingProxyType)
    assert value["parent_construction_policy_sha256"] == parent.FROZEN_POLICY_SHA256
    assert value["universe_ids"] == ("SPY", "QQQ", "SOXX", "XLV", "REMX", "XLE")
    assert "distinct_future_hybrid" in value["adaptive_selection_disclosure"]
    assert "not_an_untouched_holdout" in value["adaptive_selection_disclosure"]
    eligibility = value["eligibility"]
    assert eligibility == {
        "maximum_stock_slots_per_sleeve": 10,
        "maximum_total_reported_weight": "1.05",
        "minimum_cap_covered_reported_weight_ratio": "0.25",
        "minimum_claimed_valid_security_mapped_weight_ratio": "0.99",
        "minimum_sid_and_name_mapped_member_ratio": "0.25",
        "minimum_total_reported_weight": "0.95",
        "minimum_verified_cap_identity_names": 5,
        "valid_security_mapping_separate_from_analyst_coverage": True,
    }
    assert value["stock_selection_executable"] is False
    assert value["decision_ready"] is False
    assert all(flag is False for flag in value["capabilities"].values())
    assert all(binding is None for binding in value["pending_bindings"].values())
    for missing in (
        "security_name_source_sha256", "own_etf_security_identity_source_sha256",
        "independent_as_of_security_id_mapping_sha256",
        "independent_vendor_first_publication_sha256",
        "order_quantity_rounding_contract_sha256", "shared_execution_contract_sha256",
        "weight_transfer_implementation_sha256", "paper_epoch_sha256",
    ):
        assert missing in value["pending_bindings"]
    with pytest.raises(TypeError):
        value["eligibility"]["minimum_verified_cap_identity_names"] = 3


def test_cap_selected_count_matched_ar_arms_xle_and_safe_fallback_are_exact():
    value = subject.load_policy()
    selection = value["stock_selection"]
    cap_rank = "positive_market_cap_desc_then_exact_security_id"
    assert selection["non_xle_universe"] == ("SPY", "QQQ", "SOXX", "XLV", "REMX")
    assert selection["non_xle_selected_holdings_pool"] == (
        "all_verified_cap_eligible_exact_security_id_names_"
        "not_only_positive_score_names"
    )
    assert "strictly_positive_finite_authenticated_AR_score" in (
        selection["eligible_positive_score_definition"]
    )
    assert "reviewed_vendor_crosswalk_and_PIT_gate" in (
        selection["eligible_positive_score_definition"]
    )
    assert selection["unresolved_or_ambiguous_ar_event"] == (
        "named_refusal_no_contribution_never_fabricated_zero"
    )
    off = selection["ar_off_control"]
    assert off == {
        "ar_entry_count_enabled": False,
        "ar_score_economic_usage": "none_for_entry_count_or_weights",
        "candidate_id": "ARV2_FORWARD_AR_OFF",
        "non_xle_selection_count": "min_10_verified_cap_identity_names",
        "non_xle_selection_rank": cap_rank,
        "positive_score_count_required": 0,
    }
    assert tuple(
        (arm["candidate_id"], arm["ar_entry_count_enabled"],
         arm["ar_score_economic_usage"], arm["positive_score_count_required"],
         arm["non_xle_selection_count"], arm["non_xle_selection_rank"])
        for arm in selection["ar_on_arms"]
    ) == tuple(
        (candidate, True, "entry_count_and_unbound_weight_transfer", 5,
         "min_10_eligible_positive_score_count", cap_rank)
        for candidate in ("ARV2_FORWARD_AR_100", "ARV2_FORWARD_AR_200")
    )
    assert selection["xle_all_arms"] == {
        "candidate_ids": (
            "ARV2_FORWARD_AR_OFF", "ARV2_FORWARD_AR_100", "ARV2_FORWARD_AR_200"
        ),
        "positive_score_count_required": 0,
        "selection_count": "min_10_verified_cap_identity_names",
        "selection_rank": cap_rank,
        "xle_ar_on_weight_overlay_disabled": False,
    }
    assert value["fallback"] == {
        "identity_or_coverage_invalid": "full_own_etf_fallback",
        "missing_verified_own_etf_sid_or_price": "named_refusal_no_target",
        "non_xle_ar_positive_count_below_five": "full_own_etf_fallback",
        "own_etf_target_requires": (
            "independently_verified_exact_own_etf_qc_sid_and_positive_tradable_"
            "predecision_reference_price_no_display_ticker_join"
        ),
        "unfilled_top_ten_slots": "residual_own_etf_fallback",
        "verified_cap_identity_names_below_five": "full_own_etf_fallback",
    }
    allocation = value["allocation_and_overlap"]
    assert allocation["target_gross_exposure"] == "0.98"
    assert allocation["direct_stock_aggregate_weight_cap"] == "0.098"
    assert allocation["cross_sleeve_redistribution"] is False
    assert "contributing_own_etf" in allocation["duplicate_security_rule"]
    assert allocation["scaled_stock_slot_rule"] == (
        "if_scale_below_one_floor_1e-24_of_[(sleeve_budget/10)*"
        "min(1,cap_ratio*total_reported_weight)];otherwise_exact_sleeve_budget/10"
    )
    assert value["qcom_stock_admission"] == {
        "exact_qc_sid_required": True,
        "positive_cap_weight_and_tradable_reference_price_required": True,
        "special_exclusion": False,
        "ticker_alias_repair": False,
    }


@pytest.mark.parametrize("path, replacement", (
    (("universe_ids", 0), "XLF"),
    (("eligibility", "minimum_claimed_valid_security_mapped_weight_ratio"), "0.90"),
    (("eligibility", "minimum_sid_and_name_mapped_member_ratio"), "0.10"),
    (("eligibility", "minimum_cap_covered_reported_weight_ratio"), "0.10"),
    (("eligibility", "minimum_total_reported_weight"), "0.25"),
    (("eligibility", "minimum_verified_cap_identity_names"), 3),
    (("eligibility", "valid_security_mapping_separate_from_analyst_coverage"), False),
    (("stock_selection", "non_xle_selected_holdings_pool"), "positive_names_only"),
    (("stock_selection", "eligible_positive_score_definition"), "ticker_score"),
    (("stock_selection", "unresolved_or_ambiguous_ar_event"), "zero_score"),
    (("stock_selection", "ar_off_control", "non_xle_selection_rank"), "AR_desc"),
    (("stock_selection", "ar_off_control", "ar_score_economic_usage"), "entry"),
    (("stock_selection", "ar_on_arms", 0, "positive_score_count_required"), 1),
    (("stock_selection", "ar_on_arms", 1, "non_xle_selection_rank"), "AR_desc"),
    (("stock_selection", "xle_all_arms", "xle_ar_on_weight_overlay_disabled"), True),
    (("fallback", "own_etf_target_requires"), "display_ticker"),
    (("fallback", "missing_verified_own_etf_sid_or_price"), "guess_ticker"),
    (("allocation_and_overlap", "scaled_stock_slot_rule"), "min(1,ratio)*total"),
    (("allocation_and_overlap", "direct_stock_aggregate_weight_cap"), "0.20"),
    (("allocation_and_overlap", "cross_sleeve_redistribution"), True),
    (("qcom_stock_admission", "special_exclusion"), True),
    (("pending_bindings", "security_name_source_sha256"), "0" * 64),
    (("pending_bindings", "independent_as_of_security_id_mapping_sha256"), "0" * 64),
    (("pending_bindings", "own_etf_security_identity_source_sha256"), "0" * 64),
    (("stock_selection_executable",), True),
    (("decision_ready",), True),
    (("capabilities", "qc_launch"), True),
    (("capabilities", "orders"), True),
    (("parent_construction_policy_sha256",), "0" * 64),
))
def test_changed_rule_or_authority_refuses(path, replacement):
    value = copy.deepcopy(_raw_policy())
    target = value
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = replacement
    with pytest.raises(subject.ForwardStockSelectionPolicyError, match="policy changed"):
        subject.validate_policy(value)


@pytest.mark.parametrize("path, alias", (
    (("eligibility", "minimum_verified_cap_identity_names"), 5.0),
    (("eligibility", "valid_security_mapping_separate_from_analyst_coverage"), 1),
    (("stock_selection_executable",), 0),
    (("capabilities", "orders"), 0),
))
def test_numeric_type_aliases_refuse(path, alias):
    value = _raw_policy()
    target = value
    for part in path[:-1]:
        target = target[part]
    assert target[path[-1]] == alias
    target[path[-1]] = alias
    with pytest.raises(subject.ForwardStockSelectionPolicyError, match="policy changed"):
        subject.validate_policy(value)


def test_unknown_field_and_rehashed_noncanonical_bytes_refuse(tmp_path, monkeypatch):
    value = _raw_policy()
    value["portfolio_order_permission"] = True
    with pytest.raises(subject.ForwardStockSelectionPolicyError, match="policy changed"):
        subject.validate_policy(value)
    raw = subject.POLICY_PATH.read_bytes() + b" "
    changed = tmp_path / subject.POLICY_PATH.name
    changed.write_bytes(raw)
    monkeypatch.setattr(subject, "POLICY_PATH", changed)
    with pytest.raises(subject.ForwardStockSelectionPolicyError, match="hash changed"):
        subject.load_policy()
    monkeypatch.setattr(subject, "FROZEN_POLICY_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(subject.ForwardStockSelectionPolicyError, match="not canonical JSON"):
        subject.load_policy()


@pytest.mark.parametrize("raw, reason", (
    (b'{"schema":"one","schema":"two"}', "duplicate JSON key"),
    (b'{"schema":NaN}', "nonfinite JSON value"),
))
def test_rehashed_duplicate_or_nonfinite_json_refuses(raw, reason, tmp_path, monkeypatch):
    changed = tmp_path / subject.POLICY_PATH.name
    changed.write_bytes(raw)
    monkeypatch.setattr(subject, "POLICY_PATH", changed)
    monkeypatch.setattr(subject, "FROZEN_POLICY_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(subject.ForwardStockSelectionPolicyError, match=reason):
        subject.load_policy()


def test_parent_identity_cohort_qcom_signal_and_authority_guards(monkeypatch):
    monkeypatch.setattr(parent, "FROZEN_POLICY_SHA256", "0" * 64)
    with pytest.raises(subject.ForwardStockSelectionPolicyError, match="parent identity changed"):
        subject.load_policy()
    monkeypatch.undo()

    original = json.loads(parent.POLICY_PATH.read_bytes())
    for mutate, reason in (
        (lambda item: item["capabilities"].update(orders=True), "authority or cohort"),
        (lambda item: item["future_universe"].reverse(), "authority or cohort"),
        (lambda item: item["qcom_stock_admission"].update(special_exclusion=True), "QCOM rule"),
        (lambda item: item["signal_semantics"]["control"].update(ar_entry_count_enabled=True), "signal modes"),
        (lambda item: item["signal_semantics"]["arms"][0].update(ar_weight_transfer_fraction="0.80"), "signal modes"),
    ):
        changed = copy.deepcopy(original)
        mutate(changed)
        monkeypatch.setattr(parent, "load_policy", lambda changed=changed: changed)
        with pytest.raises(subject.ForwardStockSelectionPolicyError, match=reason):
            subject.load_policy()


def test_parent_loader_failure_refuses(monkeypatch):
    def unavailable():
        raise parent.ForwardConstructionPolicyError("missing")
    monkeypatch.setattr(parent, "load_policy", unavailable)
    with pytest.raises(subject.ForwardStockSelectionPolicyError, match="failed authentication"):
        subject.load_policy()
