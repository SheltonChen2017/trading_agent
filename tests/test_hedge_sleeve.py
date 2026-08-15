"""The defensive hedge sleeve (HEDGE-1).

The tests that matter here are about the FAILURE DIRECTION, not the happy
path. A hedge sizer's dangerous mistake is buying too much, and it buys too
much whenever it thinks the current hedge is smaller than it really is. So an
unreadable value on a held hedge instrument must refuse the entire
computation rather than skip that row -- skipping understates the current
weight, which overstates the shortfall, which oversizes the purchase.

The second thing under test is that the module makes no protection claim it
has not measured, in either direction: every report and every proposal must
carry the disclosure that this project has confirmed nothing about drawdown
reduction, and SH's daily-reset path dependence must be named wherever SH is.
"""
from __future__ import annotations

import math
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.hedge_sleeve import (
    EVIDENCE_STATUS,
    UNMEASURED_PROTECTION_DISCLOSURE,
    evaluate_hedge_sleeve,
    generate_hedge_buy_proposals,
)
from assistant.policy import TradingPolicy
from assistant.schemas import DecisionPacket, MarketRegime


def _snapshot(positions=None, cash=10_000.0):
    return build_portfolio_snapshot(positions or [], cash=cash)


def _packet(positions=None, cash=10_000.0):
    snapshot = _snapshot(positions, cash)
    return DecisionPacket(
        generated_at="2026-08-14T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="SPY", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-08-13",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _policy(*, max_order_value=50_000.0, whole_shares_only=True):
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0,
        max_order_value=max_order_value,
        allow_new_positions=True,
        whole_shares_only=whole_shares_only,
    )


def _held(ticker, shares, price):
    return {
        "ticker": ticker, "shares": shares,
        "entry_price": price, "current_price": price,
    }


# --- the gap ---------------------------------------------------------------


def test_an_unhedged_portfolio_is_short_the_whole_target():
    report = evaluate_hedge_sleeve(_snapshot(), target_pct=10)
    assert report.usable
    assert report.current_pct == 0.0
    assert Decimal(report.shortfall_dollars_exact) == Decimal("1000")
    assert Decimal(report.surplus_dollars_exact) == 0


def test_an_existing_hedge_holding_reduces_the_shortfall():
    """$400 of GLD against a $10,000 equity and a 10% target leaves $600."""
    snapshot = _snapshot([_held("GLD", 4, 100.0)], cash=9_600.0)
    report = evaluate_hedge_sleeve(snapshot, target_pct=10)
    assert Decimal(report.hedge_value_exact) == Decimal("400")
    assert Decimal(report.shortfall_dollars_exact) == Decimal("600")
    assert report.current_pct == pytest.approx(4.0)


def test_a_sleeve_above_target_reports_surplus_and_never_a_shortfall():
    snapshot = _snapshot([_held("GLD", 20, 100.0)], cash=8_000.0)
    report = evaluate_hedge_sleeve(snapshot, target_pct=10)
    assert not report.has_shortfall
    assert Decimal(report.shortfall_dollars_exact) == 0
    assert Decimal(report.surplus_dollars_exact) == Decimal("1000")


def test_an_unreadable_held_hedge_value_refuses_instead_of_skipping():
    """THE case this module exists to get right. Skipping the unreadable row
    would understate the current hedge weight, overstate the shortfall, and
    oversize the purchase. Refusing under-hedges, which is the smaller error.
    """
    snapshot = _snapshot([_held("TLT", 10, 100.0)])
    broken = [
        p if p.ticker != "TLT"
        else __import__("dataclasses").replace(
            p, market_value=float("nan"), market_value_exact=None
        )
        for p in snapshot.positions
    ]
    snapshot = __import__("dataclasses").replace(snapshot, positions=broken)

    report = evaluate_hedge_sleeve(snapshot, target_pct=10)
    assert not report.usable
    assert not report.has_shortfall
    assert any("TLT" in reason for reason in report.refusals), report.refusals
    row = next(r for r in report.rows if r.ticker == "TLT")
    assert row.held and not row.value_available


def test_an_unreadable_holding_also_suppresses_the_displayed_percentage():
    """The refusal alone is not enough. A current_pct computed while one
    holding is unreadable is an UNDERSTATED number on the screen, and an
    understated hedge weight is exactly the reading that talks someone into
    buying more. It must read zero, not a plausible wrong figure.
    """
    snapshot = _snapshot([_held("TLT", 10, 100.0), _held("GLD", 5, 100.0)])
    positions = [
        __import__("dataclasses").replace(
            p, market_value=float("nan"), market_value_exact=None
        ) if p.ticker == "TLT" else p
        for p in snapshot.positions
    ]
    snapshot = __import__("dataclasses").replace(snapshot, positions=positions)
    report = evaluate_hedge_sleeve(snapshot, target_pct=10)
    assert not report.usable
    assert report.current_pct == 0.0, (
        "a partial hedge value must not be shown as if it were the whole one"
    )


@pytest.mark.parametrize(
    "equity", [0.0, -1.0, float("nan"), float("inf")]
)
def test_unusable_total_equity_refuses(equity):
    snapshot = __import__("dataclasses").replace(
        _snapshot(), total_equity=equity, total_equity_exact=None
    )
    report = evaluate_hedge_sleeve(snapshot, target_pct=10)
    assert not report.usable
    assert Decimal(report.shortfall_dollars_exact) == 0


@pytest.mark.parametrize(
    "target", [0, -5, 100.1, 150, float("nan"), float("inf"), "", "abc"]
)
def test_an_unusable_target_refuses(target):
    """A target that WAS supplied and cannot be used is a refusal."""
    report = evaluate_hedge_sleeve(_snapshot(), target_pct=target)
    assert not report.usable
    assert Decimal(report.shortfall_dollars_exact) == 0


def test_no_target_reports_the_current_weight_without_refusing():
    """Report-only is the page's own default state. Greeting a first visit
    with a red refusal for not having typed a target yet would train the
    owner to ignore this page's errors -- so `None` reports, and only a
    supplied-but-unusable target refuses."""
    snapshot = _snapshot([_held("GLD", 4, 100.0)], cash=9_600.0)
    report = evaluate_hedge_sleeve(snapshot, target_pct=None)
    assert report.usable
    assert report.current_pct == pytest.approx(4.0)
    assert not report.has_shortfall
    assert Decimal(report.shortfall_dollars_exact) == 0
    assert Decimal(report.surplus_dollars_exact) == 0


def test_report_only_still_refuses_to_size_an_order():
    """A report is not a comparison. Falling through to the at-target
    wording would claim a check that never happened."""
    result = generate_hedge_buy_proposals(
        _packet(), _policy(), _prices(), target_pct=None
    )
    assert not result["created"]
    assert "No hedge target was supplied" in result["reason"]


def test_report_only_still_suppresses_an_unreadable_percentage():
    snapshot = _snapshot([_held("TLT", 10, 100.0)])
    positions = [
        __import__("dataclasses").replace(
            p, market_value=float("nan"), market_value_exact=None
        )
        for p in snapshot.positions
    ]
    snapshot = __import__("dataclasses").replace(snapshot, positions=positions)
    report = evaluate_hedge_sleeve(snapshot, target_pct=None)
    assert not report.usable
    assert report.current_pct == 0.0


def test_a_hundred_percent_target_is_permitted_but_not_more():
    assert evaluate_hedge_sleeve(_snapshot(), target_pct=100).usable
    assert not evaluate_hedge_sleeve(_snapshot(), target_pct=100.000001).usable


def test_the_exact_value_field_wins_over_the_float():
    """Exactness is the point: a broker value of 400.005 must not be read
    from a float that has already lost it."""
    snapshot = _snapshot([_held("GLD", 4, 100.0)], cash=9_600.0)
    positions = [
        __import__("dataclasses").replace(
            p, market_value=0.0, market_value_exact="400.005"
        )
        for p in snapshot.positions
    ]
    snapshot = __import__("dataclasses").replace(snapshot, positions=positions)
    report = evaluate_hedge_sleeve(snapshot, target_pct=10)
    assert Decimal(report.hedge_value_exact) == Decimal("400.005")
    assert Decimal(report.shortfall_dollars_exact) == Decimal("599.995")


# --- instrument selection --------------------------------------------------


def test_a_bare_string_is_refused_rather_than_iterated_per_character():
    """`tickers="GLD"` would otherwise become G, L, D -- three instruments
    that do not exist, silently."""
    report = evaluate_hedge_sleeve(_snapshot(), target_pct=10, tickers="GLD")
    assert not report.usable
    assert report.tickers == ()


def test_a_repeated_instrument_is_not_counted_twice():
    snapshot = _snapshot([_held("GLD", 4, 100.0)], cash=9_600.0)
    report = evaluate_hedge_sleeve(
        snapshot, target_pct=10, tickers=["GLD", "gld", " GLD "]
    )
    assert report.tickers == ("GLD",)
    assert Decimal(report.hedge_value_exact) == Decimal("400")


def test_an_empty_selection_refuses():
    assert not evaluate_hedge_sleeve(_snapshot(), target_pct=10, tickers=[]).usable


# --- what the report is allowed to claim -----------------------------------


def test_every_report_carries_the_unmeasured_protection_disclosure():
    report = evaluate_hedge_sleeve(_snapshot(), target_pct=10)
    assert UNMEASURED_PROTECTION_DISCLOSURE in report.disclosures


def test_the_daily_reset_instrument_is_disclosed_only_where_it_is_selected():
    with_sh = evaluate_hedge_sleeve(_snapshot(), target_pct=10, tickers=["SH"])
    without = evaluate_hedge_sleeve(_snapshot(), target_pct=10, tickers=["GLD"])
    assert any("SINGLE day" in d for d in with_sh.disclosures)
    assert not any("SINGLE day" in d for d in without.disclosures)


def test_the_report_is_immutable():
    report = evaluate_hedge_sleeve(_snapshot(), target_pct=10)
    with pytest.raises(Exception):
        report.target_pct = 50  # type: ignore[misc]
    with pytest.raises(Exception):
        report.rows[0].ticker = "X"  # type: ignore[misc]


# --- proposals -------------------------------------------------------------


def _prices(**overrides):
    prices = {"SH": 40.0, "BTAL": 20.0, "TLT": 100.0, "GLD": 200.0}
    prices.update(overrides)
    return prices


def test_a_shortfall_produces_approve_gated_buy_proposals():
    result = generate_hedge_buy_proposals(
        _packet(), _policy(), _prices(), target_pct=10
    )
    assert result["created"]
    proposals = result["proposals"]
    assert proposals, result
    for proposal in proposals:
        assert proposal.status == "proposed"
        assert proposal.intent.side == "buy"
        assert proposal.evidence_status == EVIDENCE_STATUS
        assert proposal.policy_fingerprint
        assert UNMEASURED_PROTECTION_DISCLOSURE in proposal.uncertainties


def test_the_split_is_equal_weight_not_inverse_volatility():
    """Deliberate departure from allocation_proposals: inverse-volatility
    weighting would starve the instrument that actually moves."""
    result = generate_hedge_buy_proposals(
        _packet(), _policy(), _prices(), target_pct=10
    )
    weights = {
        p.intent.ticker: round(float(p.reasons[1].split("takes ")[1].split("%")[0]), 2)
        for p in result["proposals"]
    }
    assert set(weights.values()) == {25.0}, weights


def test_sizing_never_lands_above_the_target():
    """$1,000 shortfall, equal quarters of $250. Whole-share flooring must
    leave the hedge UNDER target, never over it."""
    result = generate_hedge_buy_proposals(
        _packet(), _policy(), _prices(), target_pct=10
    )
    spent = sum(
        Decimal(str(p.intent.shares)) * Decimal(str(p.reference_price))
        for p in result["proposals"]
    )
    assert spent <= Decimal("1000")


def test_an_unpriced_instrument_is_excluded_and_the_rest_reweighted():
    result = generate_hedge_buy_proposals(
        _packet(), _policy(), _prices(BTAL=float("nan")), target_pct=10
    )
    tickers = {p.intent.ticker for p in result["proposals"]}
    assert "BTAL" not in tickers
    weights = {
        p.reasons[1].split("takes ")[1].split("%")[0] for p in result["proposals"]
    }
    assert weights == {"33.3"}, weights


def test_no_usable_price_anywhere_refuses_without_proposing():
    result = generate_hedge_buy_proposals(
        _packet(), _policy(),
        {"SH": 0.0, "BTAL": -1.0, "TLT": float("inf"), "GLD": "abc"},
        target_pct=10,
    )
    assert not result["created"]
    assert "usable current price" in result["reason"]


def test_a_sleeve_already_at_target_refuses_and_never_proposes_a_sell():
    packet = _packet([_held("GLD", 20, 100.0)], cash=8_000.0)
    result = generate_hedge_buy_proposals(
        packet, _policy(), _prices(), target_pct=10
    )
    assert not result["created"]
    assert "already at" in result["reason"]
    assert "does not sell to rebalance" in result["reason"]


def test_an_unreadable_holding_refuses_the_proposal_too():
    packet = _packet([_held("TLT", 10, 100.0)])
    broken = [
        p if p.ticker != "TLT"
        else __import__("dataclasses").replace(
            p, market_value=float("nan"), market_value_exact=None
        )
        for p in packet.portfolio.positions
    ]
    snapshot = __import__("dataclasses").replace(packet.portfolio, positions=broken)
    packet = __import__("dataclasses").replace(packet, portfolio=snapshot)

    result = generate_hedge_buy_proposals(
        packet, _policy(), _prices(), target_pct=10
    )
    assert not result["created"]
    assert "TLT" in result["reason"]


def test_a_shortfall_too_small_to_buy_anything_refuses_rather_than_partially_proposing():
    packet = _packet(cash=100.0)  # $100 equity, 1% target -> $1 shortfall
    result = generate_hedge_buy_proposals(
        packet, _policy(), _prices(), target_pct=1
    )
    assert not result["created"]
    assert "minimum order quantity" in result["reason"]


def test_the_daily_reset_warning_reaches_the_proposal_that_buys_it():
    result = generate_hedge_buy_proposals(
        _packet(), _policy(), _prices(), target_pct=10
    )
    by_ticker = {p.intent.ticker: p for p in result["proposals"]}
    assert any("SINGLE day" in u for u in by_ticker["SH"].uncertainties)
    assert not any("SINGLE day" in u for u in by_ticker["GLD"].uncertainties)


def test_proposal_ids_are_distinct_per_ticker_and_stable_per_input():
    first = generate_hedge_buy_proposals(
        _packet(), _policy(), _prices(), target_pct=10
    )["proposals"]
    second = generate_hedge_buy_proposals(
        _packet(), _policy(), _prices(), target_pct=10
    )["proposals"]
    ids = [p.proposal_id for p in first]
    assert len(set(ids)) == len(ids)
    assert ids == [p.proposal_id for p in second]


def test_a_different_target_produces_a_different_proposal_identity():
    """save_proposal()'s ON CONFLICT DO NOTHING makes a colliding id a silent
    no-op, so a materially different order must not reuse one."""
    ten = generate_hedge_buy_proposals(
        _packet(), _policy(), _prices(), target_pct=10
    )["proposals"]
    twenty = generate_hedge_buy_proposals(
        _packet(), _policy(), _prices(), target_pct=20
    )["proposals"]
    assert {p.proposal_id for p in ten}.isdisjoint({p.proposal_id for p in twenty})


def test_fractional_policy_sizes_exactly_without_floats():
    result = generate_hedge_buy_proposals(
        _packet(), _policy(whole_shares_only=False), _prices(), target_pct=10
    )
    for proposal in result["proposals"]:
        assert isinstance(proposal.intent.shares, str)
        assert not math.isnan(float(proposal.intent.shares))


# --- boundaries this milestone must not cross ------------------------------


def test_the_hedge_instruments_are_not_registered_as_leveraged():
    """Adding SH or BTAL to LEVERAGED_ETF_TICKERS would silently change
    max_leveraged_etf_pct ENFORCEMENT, a policy behavior change config must
    not smuggle in. They are 1x; their hazard is disclosure, not leverage."""
    for ticker in config.HEDGE_SLEEVE_TICKERS:
        assert ticker not in config.LEVERAGED_ETF_TICKERS, ticker
        assert ticker not in config.INVERSE_LEVERAGED_ETF_TICKERS, ticker


def test_hedging_required_no_change_to_the_owner_approved_mandate():
    """HEDGE-1 is buildable precisely because every instrument is a long-only
    ETF, which `permitted_instruments` already allows. If a later change
    edits a mandate BEHAVIOR field to make some hedge work, the owner-approved
    fingerprint stops matching -- and that fingerprint is bound to the active
    evidence epoch, so it is not a doc edit, it is an epoch event.
    """
    from assistant.mandate import compute_mandate_fingerprint, load_mandate

    mandate = load_mandate()
    assert compute_mandate_fingerprint(mandate) == mandate.approved_fingerprint
    assert "etf" in mandate.permitted_instruments
    assert not mandate.allow_autonomous_execution


def test_the_module_never_produces_a_sell_or_submits_anything():
    source = (
        Path(__file__).resolve().parent.parent / "assistant" / "hedge_sleeve.py"
    ).read_text(encoding="utf-8")
    assert 'side="sell"' not in source
    for forbidden in ("submit_order", "execute_approved", "approve_proposal"):
        assert forbidden not in source, forbidden
