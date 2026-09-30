"""SI-5 design choices are immutable, authenticated, and grant no data access."""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import subprocess

import pytest

from data.hashing import hash_payload
from research.short_interest_etf.preregistration import (
    SHORT_INTEREST_RESEARCH_GATE,
    SHORT_INTEREST_RESEARCH_GATE_SHA256,
)
from research.short_interest_etf.si5_offline_protocol import (
    SI5_OFFLINE_PROTOCOL,
    SI5_OFFLINE_PROTOCOL_SHA256,
    SI5OfflineProtocol,
    SI5ProtocolError,
    require_si5_offline_protocol,
)


def test_protocol_is_content_addressed_and_zero_authority():
    policy = SI5_OFFLINE_PROTOCOL
    payload = policy.to_payload()
    assert require_si5_offline_protocol(policy) == SI5_OFFLINE_PROTOCOL_SHA256
    assert hash_payload(payload) == SI5_OFFLINE_PROTOCOL_SHA256
    assert payload["source_research_gate_sha256"] == SHORT_INTEREST_RESEARCH_GATE_SHA256
    assert SHORT_INTEREST_RESEARCH_GATE.authorized_outcome_looks == 0
    assert SHORT_INTEREST_RESEARCH_GATE.consumed_outcome_looks == 0
    assert payload["candidate_lookbacks"] == [20, 60, 120, 252]
    assert payload["selected_lookback"] is None
    assert payload["primary_stock_contrast"] == "low_pressure_minus_high_pressure_R20"
    assert payload["confirmatory_role_cells"] == ["one_composite_stock_contrast"]
    assert payload["comparison_population"] == "common_release_security_intersection_all_four"
    assert payload["primary_return_semantic"] == (
        "gross_next_open_to_20th_later_XNYS_open_split_adjusted_"
        "dividend_excluded_price_return"
    )
    assert payload["release_aggregation"] == (
        "equal_weight_each_tail_then_equal_weight_release_events"
    )
    assert payload["candidate_selection_rule"] == (
        "development_only_best_release_mean_exact_tie_no_winner"
    )
    assert payload["primary_horizon_sessions"] == 20
    assert payload["order_exit_rule"] == "next_public_release_next_permitted_open"
    assert payload["diagnostic_cost_bps_per_side"] == 0
    assert payload["terminal_value_rule"] is None
    assert payload["order_cashflow_rule"] is None
    assert payload["order_cost_role"] == "next_release_order_pnl_only"
    assert payload["primary_cost_bps_per_side"] == 10
    assert payload["cost_sensitivities_bps_per_side"] == [0, 5, 20]
    assert payload["alpha_ceiling"] == {"numerator": 1, "denominator": 80}
    assert payload["allocated_alpha"] == {"numerator": 0, "denominator": 1}
    assert payload["permanent_look_ids"] == []
    assert payload["development_dates"] is None
    assert payload["validation_dates"] is None
    assert payload["source_rights_verified"] is False
    assert payload["actual_pit_coverage_verified"] is False
    assert payload["outcome_access_authorized"] is False
    assert payload["qc_backtest_authorized"] is False
    assert payload["production_authoritative"] is False
    assert payload["trading_authority"] is False


def test_protocol_decisions_cite_an_immutable_committed_owner_delegation():
    payload = SI5_OFFLINE_PROTOCOL.to_payload()
    source = payload["owner_decision_source"]
    root = Path(__file__).parents[1]
    committed = subprocess.run(
        ["git", "show", f"{source['commit']}:{source['path']}"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    assert sha256(committed).hexdigest() == source["sha256"]
    text = committed.decode("utf-8")
    section = text.split("## 67. SI-5 offline design precision", 1)[1]
    assert "SI-AUTH-20260928-02" in text
    for index in range(1, 6):
        assert f"SI-DEC-20260928-0{index}" in text
    for index in range(6, 10):
        assert f"SI-DEC-20260928-0{index}" in section
    for exact_clause in (
        "20th later XNYS session open",
        "split-adjusted open prices and exclude cash dividends",
        "Missing opens, suspensions, delistings, terminal proceeds",
        "Equally weight release-level contrasts",
        "maximize the mean release-level",
        "exact tie, empty cohort, or unmet power/coverage gate",
        "gross diagnostic",
        "apply only to a separately specified eventual next-release",
    ):
        assert exact_clause in section
    # The same immutable design source must include the owner's actual words
    # for the separately exercised administrative/source-qualification scope.
    for exact_owner_quote in (
        "for any steps involving owner approvals, consider i pre authorize you to proceed.",
        "for any step involving owner decisions, please use your own best judgment and make decisions on my behalf.",
        "other lanes have been using qc credentails and subscrioptions for a while. so start",
        "from now on, in this lane, anything you need my approval, consider i preauthorize it.",
        "anything you need owner decision, consider i trust your best judgment.",
        "this applies to this lane moving forward, until further notice.",
    ):
        assert exact_owner_quote in text


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_lookbacks", (20, 60)),
        ("selected_lookback", 60),
        ("primary_horizon_sessions", 21),
        ("order_exit_rule", "twenty_sessions"),
        ("primary_stock_contrast", "sector_adjusted_R20"),
        ("primary_return_semantic", "dividend_inclusive_R20"),
        ("diagnostic_cost_bps_per_side", 10),
        ("terminal_value_rule", "drop_delisted"),
        ("order_cashflow_rule", "assume_dividends"),
        ("order_cost_role", "stock_diagnostic"),
        ("confirmatory_role_cells", ("pressure", "covering")),
        ("comparison_population", "each_authentic_cohort"),
        ("allocated_alpha", (1, 80)),
        ("permanent_look_ids", ("si5-look-1",)),
        ("development_dates", ("2020-01-01", "2021-12-31")),
        ("source_rights_verified", True),
        ("actual_pit_coverage_verified", True),
        ("outcome_access_authorized", True),
        ("qc_backtest_authorized", True),
        ("production_authoritative", True),
        ("trading_authority", True),
        # The ten cases below pin fields whose construction guard was
        # previously unasserted: removing any one of those guards let
        # ``to_payload()`` serialize the altered design with no refusal,
        # leaving only the whole-payload digest in ``require_si5_offline_protocol``.
        ("release_aggregation", "value_weight_releases"),
        ("candidate_selection_rule", "pick_best_validation_window"),
        ("sector_relative_role", "second_primary_test"),
        ("primary_cost_bps_per_side", 0),
        ("alpha_ceiling", Fraction(1, 20)),
        ("prospective_power_verified", True),
        ("validation_dates", ("2026-01-01", "2026-12-31")),
        ("cost_sensitivities_bps_per_side", (0,)),
        ("version", "si5-stock-test-offline-design-v2"),
        ("owner_decision_sha256", "0" * 64),
    ],
)
def test_unapproved_choice_or_authority_cannot_be_constructed(field, value):
    with pytest.raises(SI5ProtocolError, match="REFUSED"):
        replace(SI5_OFFLINE_PROTOCOL, **{field: value})


def test_payload_is_detached_and_reauthentication_catches_caller_mutation():
    policy = SI5_OFFLINE_PROTOCOL
    payload = policy.to_payload()
    payload["candidate_lookbacks"].clear()
    payload["owner_decision_source"]["sha256"] = "0" * 64
    assert policy.to_payload()["candidate_lookbacks"] == [20, 60, 120, 252]
    assert require_si5_offline_protocol(policy) == SI5_OFFLINE_PROTOCOL_SHA256
    impostor = object.__new__(SI5OfflineProtocol)
    for name in policy.__dataclass_fields__:
        object.__setattr__(impostor, name, getattr(policy, name))
    object.__setattr__(impostor, "outcome_access_authorized", True)
    with pytest.raises(SI5ProtocolError, match="REFUSED"):
        require_si5_offline_protocol(impostor)
    with pytest.raises(SI5ProtocolError, match="exact SI5OfflineProtocol type"):
        require_si5_offline_protocol(object())
