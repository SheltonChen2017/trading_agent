"""Buy-only cash steering toward under-band sleeves (REBAL-1 Stage 2).

Stage 2's dangerous directions are different from Stage 1's, because it can
now prepare orders:

* it must never sell. An overweight sleeve produces nothing at all -- not a
  smaller buy, not a suggestion. Trimming is Stage 3 and needs separate
  authorization;
* it must never steer money the owner did not direct. A sleeve with no chosen
  ticker is refused, not filled with a name this project picked; and
* it must never quietly fund a subset. A budget that funds three of four
  chosen sleeves produces a different portfolio from the one that was sized,
  so an unaffordable leg is named.

Eligibility reads the BAND, not the display status, and is measured on the
PROJECTED weight so money already working in an unfilled order counts --
sizing against the current weight is how the hedge sleeve once prepared a
duplicate correction (HEDGER-004).
"""
from __future__ import annotations

import dataclasses
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.execution_service import validate_proposal_for_execution
from assistant.policy import TradingPolicy
from assistant.rebalance_profile import (
    OWNER_APPROVED_PROFILE,
    SLEEVE_CASH,
    SLEEVE_DIVIDEND,
    SLEEVE_GROWTH,
    SLEEVE_HEDGE,
    SLEEVE_LEVERAGED,
    SLEEVE_OTHER,
    compute_profile_fingerprint,
)
from assistant.rebalance_steering import (
    EVIDENCE_STATUS,
    INELIGIBLE_SLEEVES,
    eligible_sleeves,
    generate_steering_proposals,
    plan_cash_steering,
    steering_input_fingerprint,
)
from assistant.portfolio_rebalance import evaluate_portfolio_rebalance
from assistant.schemas import DecisionPacket, MarketRegime
from assistant.storage import AssistantStore

PRICES = {"MSFT": 100.0, "SH": 40.0, "NVDL": 50.0, "JEPQ": 10.0, "GLD": 10.0}
ALL_SELECTIONS = {
    SLEEVE_GROWTH: "MSFT",
    SLEEVE_HEDGE: "SH",
    SLEEVE_LEVERAGED: "NVDL",
    SLEEVE_DIVIDEND: "JEPQ",
}


def _held(ticker, shares, price):
    return {
        "ticker": ticker, "shares": shares,
        "entry_price": price, "current_price": price,
    }


def _packet(positions=None, cash=10_000.0, **kwargs):
    snapshot = build_portfolio_snapshot(positions or [], cash=cash, **kwargs)
    return DecisionPacket(
        generated_at="2026-08-15T12:00:00+00:00", portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="SPY", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-08-14",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _policy(**overrides):
    fields = dict(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0,
        max_order_value=50_000.0, allow_new_positions=True,
    )
    fields.update(overrides)
    return TradingPolicy(**fields)


def _plan(packet=None, budget=2_000, selections=None, prices=None, policy=None):
    return plan_cash_steering(
        packet or _packet(), OWNER_APPROVED_PROFILE, policy or _policy(),
        budget=budget,
        selections=ALL_SELECTIONS if selections is None else selections,
        prices=PRICES if prices is None else prices,
    )


# --- eligibility ------------------------------------------------------------


def test_only_sleeves_below_their_lower_band_receive_money():
    report = evaluate_portfolio_rebalance(
        _packet().portfolio, OWNER_APPROVED_PROFILE, policy=_policy()
    )
    eligible = eligible_sleeves(report)
    assert SLEEVE_GROWTH in eligible
    assert SLEEVE_CASH not in eligible
    assert SLEEVE_OTHER not in eligible


def test_cash_and_the_residual_are_never_steering_destinations():
    """Cash is the budget's source. The residual is by definition the set of
    holdings the profile does not describe, so buying toward it would be
    buying toward a target that names nothing."""
    assert INELIGIBLE_SLEEVES == {SLEEVE_CASH, SLEEVE_OTHER}
    # a portfolio where both are far below target
    packet = _packet([_held("MSFT", 100, 100.0)], cash=0.0)
    report = evaluate_portfolio_rebalance(
        packet.portfolio, OWNER_APPROVED_PROFILE, policy=_policy()
    )
    assert SLEEVE_CASH not in eligible_sleeves(report)
    assert SLEEVE_OTHER not in eligible_sleeves(report)


def test_an_overweight_sleeve_produces_nothing_at_all():
    """Stage 2 never sells, and never offers a smaller buy as consolation."""
    packet = _packet([_held("MSFT", 900, 10.0)], cash=1_000.0)  # growth 90%
    report = evaluate_portfolio_rebalance(
        packet.portfolio, OWNER_APPROVED_PROFILE, policy=_policy()
    )
    assert SLEEVE_GROWTH not in eligible_sleeves(report)

    # Selections are supplied for every sleeve so the refusal under test is
    # about growth being overweight, not about a missing choice elsewhere.
    plan = _plan(packet=packet, selections=ALL_SELECTIONS)
    assert plan.usable, plan.refusals
    assert all(leg.sleeve != SLEEVE_GROWTH for leg in plan.legs), (
        "an overweight sleeve receives nothing -- not even a reduced buy"
    )


def test_eligibility_uses_the_projected_weight_so_working_orders_count():
    """Sizing against the CURRENT weight prepares a second correction for a
    gap the first order is already closing -- the duplication HEDGER-004
    found in the hedge sleeve."""
    packet = _packet(
        cash=10_000.0,
        open_orders=[{"ticker": "SH", "side": "buy", "notional": 1_000.0}],
    )
    report = evaluate_portfolio_rebalance(
        packet.portfolio, OWNER_APPROVED_PROFILE, policy=_policy()
    )
    hedge = next(r for r in report.rows if r.sleeve == SLEEVE_HEDGE)
    assert hedge.current_pct == pytest.approx(0.0)
    assert hedge.projected_pct == pytest.approx(10.0)  # already at target
    assert SLEEVE_HEDGE not in eligible_sleeves(report)


# --- the owner picks the ticker ---------------------------------------------


def test_a_sleeve_without_a_chosen_ticker_is_refused_not_filled_in():
    plan = _plan(selections={SLEEVE_GROWTH: "MSFT"})
    assert not plan.usable
    assert any("no ticker was chosen" in r for r in plan.refusals)
    assert any("does not pick which name" in r for r in plan.refusals)


def test_a_ticker_outside_its_sleeve_is_refused():
    """Buying a name that is not in the sleeve would not move that sleeve."""
    selections = dict(ALL_SELECTIONS)
    selections[SLEEVE_GROWTH] = "SH"  # a hedge name
    plan = _plan(selections=selections)
    assert not plan.usable
    assert any("not a configured member" in r for r in plan.refusals)


# --- sizing -----------------------------------------------------------------


def test_money_is_sized_to_the_lower_edge_not_the_target():
    """The band's purpose is that being inside it is enough. Steering to the
    target spends more than the profile asks and hands back the turnover the
    band exists to avoid."""
    plan = _plan(budget=100_000)
    growth = next(leg for leg in plan.legs if leg.sleeve == SLEEVE_GROWTH)
    # growth target 40%, band 25% -> lower edge 30% of a $10,000 book
    assert Decimal(growth.shortfall_to_lower_edge_exact) == Decimal("3000")
    assert Decimal(growth.allocated_dollars_exact) <= Decimal("3000")


def test_lower_edge_shortfall_stays_exact_on_an_awkward_denominator():
    """The report's percentages are display floats; reconstructing dollars
    from them must not contaminate fractional-share sizing."""
    packet = _packet([_held("MSFT", 1, 1.0)], cash=6.0)
    plan = _plan(
        packet=packet,
        budget=100,
        prices={**PRICES, "MSFT": Decimal("0.1")},
        policy=_policy(whole_shares_only=False),
    )
    growth = next(leg for leg in plan.legs if leg.sleeve == SLEEVE_GROWTH)
    # Growth's lower edge is exactly 30%: 30% of $7 minus the $1 holding.
    assert growth.shortfall_to_lower_edge_exact == "1.1"


def test_leftover_money_is_reported_never_pushed_onto_another_sleeve():
    plan = _plan(budget=2_000)
    spent = sum(Decimal(leg.planned_notional_exact) for leg in plan.legs)
    assert spent + Decimal(plan.unallocated_exact) == Decimal("2000")
    assert Decimal(plan.unallocated_exact) > 0


def test_an_unaffordable_chosen_leg_is_named_not_silently_dropped():
    """A budget that quietly funds three of four chosen sleeves produces a
    different portfolio from the one the owner sized."""
    prices = dict(PRICES)
    prices["MSFT"] = 1_000_000.0  # unaffordable at any sane split
    plan = _plan(budget=1_000, prices=prices)
    assert plan.usable
    assert all(leg.ticker != "MSFT" for leg in plan.legs)
    assert any("Not funded" in d and "MSFT" in d for d in plan.disclosures)


def test_a_missing_price_refuses_rather_than_steering_around_it():
    prices = dict(PRICES)
    prices["MSFT"] = float("nan")
    plan = _plan(prices=prices)
    assert not plan.usable
    assert any("MSFT" in r for r in plan.refusals)
    assert any("Deselect" in r for r in plan.refusals)


@pytest.mark.parametrize("budget", [0, -1, "", "abc", None, float("nan")])
def test_an_unusable_budget_refuses(budget):
    plan = _plan(budget=budget)
    assert not plan.usable


def test_fractional_policy_sizes_exactly_without_floats():
    """`canonical_order_quantity` keeps an exactly-integral quantity as an
    int even in fractional mode; only a genuine fraction becomes decimal
    text. The invariant that matters is that a binary float never appears in
    a quantity, and that a fraction is preserved exactly."""
    prices = dict(PRICES)
    prices["MSFT"] = 30.0  # $1,000-ish allocations do not divide evenly
    plan = _plan(policy=_policy(whole_shares_only=False), prices=prices)
    assert plan.legs
    for leg in plan.legs:
        assert not isinstance(leg.shares, float), leg
        assert isinstance(leg.shares, (int, str))
    fractional = [leg for leg in plan.legs if isinstance(leg.shares, str)]
    assert fractional, "at least one leg should not divide evenly"
    for leg in fractional:
        assert Decimal(leg.shares) == Decimal(leg.shares)  # exact, parses


def test_whole_share_policy_never_lands_a_sleeve_above_its_edge():
    plan = _plan(budget=100_000, policy=_policy(whole_shares_only=True))
    for leg in plan.legs:
        assert Decimal(leg.planned_notional_exact) <= Decimal(
            leg.shortfall_to_lower_edge_exact
        )


def test_an_unusable_holding_refuses_the_whole_plan():
    """One corrupt value moves every sleeve's percentage and can invent an
    under-band sleeve to steer money into."""
    packet = _packet([_held("JEPQ", 100, 10.0)], cash=9_000.0)
    positions = [
        dataclasses.replace(p, market_value=float("nan"), market_value_exact=None)
        for p in packet.portfolio.positions
    ]
    snapshot = dataclasses.replace(packet.portfolio, positions=positions)
    packet = dataclasses.replace(packet, portfolio=snapshot)
    plan = _plan(packet=packet)
    assert not plan.usable


# --- proposals --------------------------------------------------------------


def test_every_proposal_is_a_gated_buy_bound_to_the_profile():
    result = generate_steering_proposals(
        _packet(), OWNER_APPROVED_PROFILE, _policy(),
        budget=2_000, selections=ALL_SELECTIONS, prices=PRICES,
    )
    assert result["created"]
    for proposal in result["proposals"]:
        assert proposal.status == "proposed"
        assert proposal.intent.side == "buy"
        assert proposal.evidence_status == EVIDENCE_STATUS
        assert proposal.policy_fingerprint
        assert proposal.expected_impact["allocation_profile_fingerprint"] == (
            compute_profile_fingerprint(OWNER_APPROVED_PROFILE)
        )
        # The UI immediately persists this dictionary as JSON. Exact Decimal
        # arithmetic belongs in sizing, not in the persistence boundary.
        json.dumps(proposal.to_dict(), sort_keys=True)


def test_changing_the_profile_changes_every_proposal_identity():
    """Proposals bind to the allocation-profile fingerprint, so a profile
    edit cannot silently reuse an order sized against targets the owner has
    since changed."""
    moved = dataclasses.replace(
        OWNER_APPROVED_PROFILE,
        targets={**dict(OWNER_APPROVED_PROFILE.targets),
                 SLEEVE_GROWTH: "35", SLEEVE_HEDGE: "15"},
    )
    base = generate_steering_proposals(
        _packet(), OWNER_APPROVED_PROFILE, _policy(),
        budget=2_000, selections=ALL_SELECTIONS, prices=PRICES,
    )["proposals"]
    after = generate_steering_proposals(
        _packet(), moved, _policy(),
        budget=2_000, selections=ALL_SELECTIONS, prices=PRICES,
    )["proposals"]
    assert {p.proposal_id for p in base}.isdisjoint({p.proposal_id for p in after})


def test_a_different_budget_produces_a_different_proposal_identity():
    ids = []
    for budget in (2_000, 3_000):
        ids.append({
            p.proposal_id for p in generate_steering_proposals(
                _packet(), OWNER_APPROVED_PROFILE, _policy(),
                budget=budget, selections=ALL_SELECTIONS, prices=PRICES,
            )["proposals"]
        })
    assert ids[0].isdisjoint(ids[1])


def test_budget_change_cannot_reuse_an_idempotency_key_for_the_same_shares():
    """The database makes idempotency_key unique. Two budgets that round to
    the same whole-share intent still need distinct keys when their proposal
    identities differ, or saving the second result raises IntegrityError."""
    proposals = []
    for budget in ("2000", "2000.01"):
        proposals.append({
            p.intent.ticker: p
            for p in generate_steering_proposals(
                _packet(), OWNER_APPROVED_PROFILE, _policy(),
                budget=budget, selections=ALL_SELECTIONS, prices=PRICES,
            )["proposals"]
        })
    common = set(proposals[0]) & set(proposals[1])
    same_quantity = [
        ticker for ticker in common
        if proposals[0][ticker].intent.shares == proposals[1][ticker].intent.shares
    ]
    assert same_quantity, "the regression needs at least one rounded-equal leg"
    for ticker in same_quantity:
        before, after = proposals[0][ticker], proposals[1][ticker]
        assert before.proposal_id != after.proposal_id
        assert before.idempotency_key != after.idempotency_key


def test_proposals_are_stable_for_identical_input():
    runs = [
        {p.proposal_id for p in generate_steering_proposals(
            _packet(), OWNER_APPROVED_PROFILE, _policy(),
            budget=2_000, selections=ALL_SELECTIONS, prices=PRICES,
        )["proposals"]}
        for _ in range(2)
    ]
    assert runs[0] == runs[1]


def test_same_day_market_value_change_invalidates_the_ui_signature():
    """Two positions can move in opposite directions while total equity,
    share counts, pending orders, and the snapshot date all stay unchanged.
    A proposal card sized from the first values must not survive the second."""
    before_packet = _packet(
        [_held("MSFT", 10, 100.0), _held("JEPQ", 100, 10.0)],
        cash=8_000.0,
    )
    after_packet = _packet(
        [_held("MSFT", 10, 120.0), _held("JEPQ", 100, 8.0)],
        cash=8_000.0,
    )
    before = evaluate_portfolio_rebalance(
        before_packet.portfolio, OWNER_APPROVED_PROFILE, policy=_policy()
    )
    after = evaluate_portfolio_rebalance(
        after_packet.portfolio, OWNER_APPROVED_PROFILE, policy=_policy()
    )
    assert before.as_of == after.as_of
    assert before.total_equity_exact == after.total_equity_exact
    assert steering_input_fingerprint(
        before_packet, before, _policy(),
        selections=ALL_SELECTIONS, budget="2000"
    ) != steering_input_fingerprint(
        after_packet, after, _policy(),
        selections=ALL_SELECTIONS, budget="2000"
    )


def test_execution_refuses_a_proposal_from_a_non_active_profile(tmp_path):
    """Changing proposal identity is not enough: a stored card is reachable
    from History after session state is gone, so the execution gate must bind
    it to the currently active owner profile before broker contact."""
    moved = dataclasses.replace(
        OWNER_APPROVED_PROFILE,
        targets={
            **dict(OWNER_APPROVED_PROFILE.targets),
            SLEEVE_GROWTH: "35",
            SLEEVE_HEDGE: "15",
        },
    )
    packet = _packet()
    policy = _policy()
    proposal = generate_steering_proposals(
        packet, moved, policy,
        budget=2_000, selections=ALL_SELECTIONS, prices=PRICES,
    )["proposals"][0]
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(proposal.to_dict())

    outcome = validate_proposal_for_execution(
        proposal.proposal_id,
        packet.portfolio,
        policy,
        store,
        now_et=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
    )

    assert not outcome.approved
    assert "allocation profile" in str(outcome.error).lower()


def test_a_refused_plan_creates_no_proposal():
    result = generate_steering_proposals(
        _packet(), OWNER_APPROVED_PROFILE, _policy(),
        budget=0, selections=ALL_SELECTIONS, prices=PRICES,
    )
    assert not result["created"]
    assert "proposals" not in result


def test_every_proposal_says_the_shape_is_not_evidence_backed():
    result = generate_steering_proposals(
        _packet(), OWNER_APPROVED_PROFILE, _policy(),
        budget=2_000, selections=ALL_SELECTIONS, prices=PRICES,
    )
    for proposal in result["proposals"]:
        assert any("not a research result" in u for u in proposal.uncertainties)
        assert any("Hold the cash" in a for a in proposal.alternatives)


# --- boundaries this stage must not cross -----------------------------------


def test_the_module_never_sells_and_never_submits():
    import ast

    source = (
        Path(__file__).resolve().parent.parent
        / "assistant" / "rebalance_steering.py"
    ).read_text(encoding="utf-8")
    called = {
        node.func.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    for forbidden in ("save_proposal", "approve_proposal", "submit_order"):
        assert forbidden not in called, forbidden
    assert 'side="sell"' not in source
    assert "'sell'" not in source.replace('"buy"', "")


def test_execution_refuses_a_rebalance_proposal_with_no_profile_fingerprint(
    tmp_path,
):
    """REBAL2CCR-001. A missing fingerprint must be refused with a message
    that says it is MISSING.

    Safety was never at risk here and the first version of this note said
    otherwise: with the missing-value branch deleted, `None != current` still
    refuses the proposal, so it fails closed either way. What was unpinned is
    the accuracy of the reason -- without the branch the owner is told the
    profile "does not match" when there is nothing to match, which sends them
    looking for a profile edit that never happened.

    The missing case is the reachable one: any steering proposal saved before
    the execution-time binding existed carries no fingerprint at all.
    """
    packet = _packet()
    policy = _policy()
    proposal = generate_steering_proposals(
        packet, OWNER_APPROVED_PROFILE, policy,
        budget=2_000, selections=ALL_SELECTIONS, prices=PRICES,
    )["proposals"][0]

    stored = proposal.to_dict()
    stored["expected_impact"] = {
        k: v for k, v in stored["expected_impact"].items()
        if k != "allocation_profile_fingerprint"
    }
    assert "allocation_profile_fingerprint" not in stored["expected_impact"]

    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(stored)

    outcome = validate_proposal_for_execution(
        proposal.proposal_id, packet.portfolio, policy, store,
        now_et=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
    )
    assert not outcome.approved
    error = str(outcome.error).lower()
    assert "missing its allocation profile" in error, error
    assert "does not match" not in error, (
        "a proposal with no fingerprint is not a mismatched one"
    )


def test_a_non_rebalance_proposal_is_unaffected_by_the_context_check(tmp_path):
    """The guard keys on `evidence_status`, so every other proposal family
    must reach its ordinary validation untouched -- including families whose
    `expected_impact` has no fingerprint at all, which is all of them."""
    from assistant.execution_service import _validate_proposal_context

    for status in (
        "deterministic_risk_policy",
        "user_directed_allocation",
        "user_directed_hedge",
        "user_directed_discrete_buy",
    ):
        assert _validate_proposal_context(
            {"evidence_status": status, "expected_impact": {}}
        ) is None, status
    # and a row with no evidence_status at all
    assert _validate_proposal_context({"expected_impact": {}}) is None
