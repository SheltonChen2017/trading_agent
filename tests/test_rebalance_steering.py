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
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.rebalance_profile import (
    OWNER_APPROVED_PROFILE,
    SLEEVE_CASH,
    SLEEVE_DIVIDEND,
    SLEEVE_GROWTH,
    SLEEVE_HEDGE,
    SLEEVE_LEVERAGED,
    SLEEVE_OTHER,
)
from assistant.rebalance_steering import (
    EVIDENCE_STATUS,
    INELIGIBLE_SLEEVES,
    eligible_sleeves,
    generate_steering_proposals,
    plan_cash_steering,
)
from assistant.portfolio_rebalance import evaluate_portfolio_rebalance
from assistant.schemas import DecisionPacket, MarketRegime

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


def test_proposals_are_stable_for_identical_input():
    runs = [
        {p.proposal_id for p in generate_steering_proposals(
            _packet(), OWNER_APPROVED_PROFILE, _policy(),
            budget=2_000, selections=ALL_SELECTIONS, prices=PRICES,
        )["proposals"]}
        for _ in range(2)
    ]
    assert runs[0] == runs[1]


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
