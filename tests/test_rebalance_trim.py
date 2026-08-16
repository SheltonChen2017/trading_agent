"""Tax-aware trims of overweight sleeves (REBAL-1 Stage 3).

Stage 3 is the first path where a rebalancing SELL originates from the app's
own arithmetic rather than from a computed policy breach or the owner naming
a holding. The tests here are weighted accordingly: most of them are about
refusing.

Four properties carry the safety:

* the owner chooses the sleeve, ticker, amount, and lot strategy -- the app
  chooses none of them;
* a sale larger than the target-restoration amount is refused, because
  trimming past target flips the sleeve underweight and hands the next
  steering pass a shortfall to buy back, paying spread and tax both ways;
* an incomplete tax ledger refuses the whole trim, because this stage exists
  to show the realized-gain consequence and a trim whose tax effect is
  unknown is exactly the pre-tax-looks-good trap this project has been
  caught by before; and
* a working sell already counts against the excess, so a second trim is not
  prepared for a gap the first is already closing.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.corporate_actions import tax_ledger_with_coverage
from assistant.policy import TradingPolicy
from assistant.portfolio_rebalance import evaluate_portfolio_rebalance
from assistant.rebalance_profile import (
    OWNER_APPROVED_PROFILE,
    SLEEVE_CASH,
    SLEEVE_GROWTH,
    SLEEVE_HEDGE,
    SLEEVE_OTHER,
)
from assistant.rebalance_trim import (
    EVIDENCE_STATUS,
    UNTRIMMABLE_SLEEVES,
    classify_overweight_sleeves,
    generate_trim_proposal,
    plan_trim,
)
from assistant.schemas import DecisionPacket, MarketRegime
from assistant.tax_lots import Fill, build_ledger

COVERAGE = {"complete": True, "tickers": {"MSFT": {"matched": True}}}


def _ledger(*fills):
    return build_ledger(list(fills) or [
        Fill(ticker="MSFT", side="buy", qty=500, price=8.0, fill_id="old",
             at=datetime(2024, 1, 10, tzinfo=timezone.utc)),
        Fill(ticker="MSFT", side="buy", qty=400, price=9.0, fill_id="new",
             at=datetime(2026, 7, 1, tzinfo=timezone.utc)),
    ])


def _packet(positions=None, cash=1_000.0, **kwargs):
    snapshot = build_portfolio_snapshot(
        positions or [
            {"ticker": "MSFT", "shares": 900,
             "entry_price": 8.0, "current_price": 10.0}
        ],
        cash=cash, **kwargs
    )
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
        max_order_value=500_000.0, allow_new_positions=True,
    )
    fields.update(overrides)
    return TradingPolicy(**fields)


def _plan(packet=None, sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
          lot_strategy="fifo", ledger=None, coverage=COVERAGE, policy=None,
          **kwargs):
    return plan_trim(
        packet or _packet(), OWNER_APPROVED_PROFILE, policy or _policy(),
        sleeve=sleeve, ticker=ticker, shares=shares,
        lot_strategy=lot_strategy,
        tax_lot_ledger=_ledger() if ledger is None else ledger,
        tax_lot_coverage=coverage, **kwargs
    )


# --- what may be trimmed at all ---------------------------------------------


def test_only_sleeves_above_their_upper_band_can_be_trimmed():
    report = evaluate_portfolio_rebalance(
        _packet().portfolio, OWNER_APPROVED_PROFILE, policy=_policy()
    )
    groups = classify_overweight_sleeves(report)
    assert groups.trimmable == (SLEEVE_GROWTH,)
    assert groups.untrimmable == ()


def test_overweight_classification_returns_both_groups_together():
    snapshot = build_portfolio_snapshot(
        [{
            "ticker": "MSFT", "shares": 600,
            "entry_price": 10.0, "current_price": 10.0,
        }],
        cash=4_000.0,
    )
    report = evaluate_portfolio_rebalance(
        snapshot, OWNER_APPROVED_PROFILE, policy=_policy()
    )
    groups = classify_overweight_sleeves(report)
    assert groups.trimmable == (SLEEVE_GROWTH,)
    assert groups.untrimmable == (SLEEVE_CASH,)


def test_an_unusable_rebalance_report_can_never_become_a_trim():
    """Open-order blindness makes projected weight unknowable.  Report
    refusals must survive the plan boundary instead of being collected and
    then accidentally replaced by an empty final refusal tuple."""
    packet = _packet(open_orders_available=False)
    plan = _plan(packet=packet)
    assert not plan.usable
    assert any("Open-order data is unavailable" in r for r in plan.refusals)

    result = generate_trim_proposal(
        packet, OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
        lot_strategy="fifo", tax_lot_ledger=_ledger(),
        tax_lot_coverage=COVERAGE,
    )
    assert not result["created"]


def test_a_sleeve_inside_its_band_is_refused():
    """This workflow never sells a sleeve that is inside or below its band."""
    plan = _plan(sleeve=SLEEVE_HEDGE, ticker="GLD")
    assert not plan.usable
    assert any("not above its upper band" in r for r in plan.refusals)


def test_cash_and_the_residual_can_never_be_trimmed():
    """Cash is not a holding, and absence from the profile is never a reason
    to sell -- the rule Stage 1 states about the residual."""
    assert UNTRIMMABLE_SLEEVES == {SLEEVE_CASH, SLEEVE_OTHER}
    for sleeve in (SLEEVE_CASH, SLEEVE_OTHER):
        plan = _plan(sleeve=sleeve, ticker="AAPL")
        assert not plan.usable
        assert any("not a trimmable sleeve" in r for r in plan.refusals)


def test_a_ticker_outside_the_sleeve_is_refused():
    plan = _plan(ticker="GLD")  # a hedge name against the growth sleeve
    assert not plan.usable
    assert any("not a configured member" in r for r in plan.refusals)


def test_a_ticker_that_is_not_held_is_refused():
    plan = _plan(ticker="NVDA")  # in the growth sleeve, but not held
    assert not plan.usable
    assert any("not currently held" in r for r in plan.refusals)


def test_the_app_never_chooses_the_ticker():
    plan = _plan(ticker=None)
    assert not plan.usable
    assert any("does not choose one" in r for r in plan.refusals)


# --- how much may be sold ---------------------------------------------------


def test_both_band_landmarks_are_reported():
    """The spec requires showing the amount above band AND the
    target-restoration amount, because they are different decisions."""
    plan = _plan()
    # growth is $9,000 of a $10,000 book; upper edge 50%, target 40%
    assert Decimal(plan.excess_above_band_exact) == Decimal("4000")
    assert Decimal(plan.restoration_to_target_exact) == Decimal("5000")


def test_a_sale_beyond_the_target_restoration_amount_is_refused():
    """Trimming past target does not get ahead: it flips the sleeve
    underweight and hands the next steering pass a shortfall to buy back."""
    plan = _plan(shares=600)  # $6,000 against a $5,000 restoration
    assert not plan.usable
    assert any("restores" in r and "underweight" in r for r in plan.refusals)


def test_a_sale_exactly_at_the_restoration_amount_is_allowed():
    plan = _plan(shares=500)  # exactly $5,000
    assert plan.usable, plan.refusals


def test_selling_more_than_is_held_is_refused():
    plan = _plan(shares=2_000)
    assert not plan.usable
    assert any("short the position" in r for r in plan.refusals)


@pytest.mark.parametrize("shares", [0, -5, 1.5, "abc", None])
def test_an_unusable_quantity_is_refused(shares):
    plan = _plan(shares=shares)
    assert not plan.usable


def test_a_working_sell_already_counts_against_the_excess():
    """Sizing against the current weight while an unfilled sell is
    outstanding prepares a second trim for a gap the first is closing."""
    packet = _packet(
        open_orders=[{"ticker": "MSFT", "side": "sell", "notional": 2_000.0}]
    )
    plan = _plan(packet=packet, shares=200)
    # projected growth is $7,000, so the excess and restoration both shrink
    assert Decimal(plan.excess_above_band_exact) == Decimal("2000")
    assert Decimal(plan.restoration_to_target_exact) == Decimal("3000")
    assert Decimal(plan.pending_sell_value_exact) == Decimal("2000")


def test_working_sell_display_is_gross_not_signed_net_pending():
    """The drift row needs signed net exposure, but the owner-facing field
    promises the working SELL amount.  A simultaneous buy must not turn that
    display negative or hide part of the sell."""
    packet = _packet(open_orders=[
        {"ticker": "MSFT", "side": "sell", "notional": 2_000.0},
        {"ticker": "MSFT", "side": "buy", "notional": 500.0},
    ])
    plan = _plan(packet=packet, shares=200)
    assert plan.usable, plan.refusals
    assert Decimal(plan.pending_sell_value_exact) == Decimal("2000")


# --- the tax consequence ----------------------------------------------------


def test_an_incomplete_tax_ledger_refuses_the_trim():
    """This stage exists to show the realized gain. A trim whose tax effect
    is unknown is the pre-tax-looks-good trap, so it refuses rather than
    proposing with the consequence omitted."""
    plan = _plan(coverage={"complete": False, "tickers": {}, "reason": "no fills"})
    assert not plan.usable
    assert any("realized" in r and "cannot be shown" in r for r in plan.refusals)


def test_a_missing_ledger_refuses_even_when_coverage_claims_complete():
    plan = _plan(ledger=None, coverage=COVERAGE)
    assert plan.usable  # sanity: the default ledger works
    plan = plan_trim(
        _packet(), OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200, lot_strategy="fifo",
        tax_lot_ledger=None, tax_lot_coverage=COVERAGE,
    )
    assert not plan.usable


def test_real_tax_coverage_contract_allows_a_complete_trim():
    """Integration pin: production emits per-ticker ``matched`` plus a
    global ``complete`` verdict.  A hand-written fixture with a made-up
    per-ticker ``complete`` field can make every unit test pass while the UI
    refuses every real trim."""
    store = SimpleNamespace(
        list_fills=lambda: [
            {
                "ticker": "MSFT", "side": "buy", "qty": 900,
                "price": 8.0, "fill_id": "real-contract",
                "at": "2024-01-10T12:00:00+00:00",
            }
        ],
        list_journal_postings=lambda: [],
    )
    ledger, coverage = tax_ledger_with_coverage(store, _packet().portfolio)
    assert coverage["complete"] is True
    assert coverage["tickers"]["MSFT"]["matched"] is True
    assert "complete" not in coverage["tickers"]["MSFT"]

    plan = _plan(ledger=ledger, coverage=coverage)
    assert plan.usable, plan.refusals


def test_the_lot_strategy_changes_which_lots_are_realized():
    """FIFO takes the old cheap lot; HIFO takes the newer expensive one and
    realizes less gain. The owner picks; the app never does."""
    fifo = _plan(lot_strategy="fifo")
    hifo = _plan(lot_strategy="hifo")
    assert Decimal(fifo.realized_gain_exact) > Decimal(hifo.realized_gain_exact)
    assert fifo.lots[0].lot_id != hifo.lots[0].lot_id


@pytest.mark.parametrize("strategy", ["", "average", "cheapest", None])
def test_an_unknown_lot_strategy_is_refused(strategy):
    plan = _plan(lot_strategy=strategy)
    assert not plan.usable
    assert any("Lot strategy must be one of" in r for r in plan.refusals)


def test_a_short_term_gain_is_disclosed_prominently():
    """`config` already encodes the opposite preference for the growth
    sleeve's scheduled trim, which fires only once a lot is long-term."""
    plan = _plan(lot_strategy="lifo", shares=200)  # newest lot is 2026
    assert Decimal(plan.realized_short_term_exact) > 0
    assert any("SHORT-TERM" in d for d in plan.disclosures)


def test_the_realized_split_sums_to_the_total():
    plan = _plan(shares=500, lot_strategy="fifo")
    assert (
        Decimal(plan.realized_short_term_exact)
        + Decimal(plan.realized_long_term_exact)
        == Decimal(plan.realized_gain_exact)
    )


def test_each_lot_reports_its_holding_period():
    plan = _plan()
    assert plan.lots
    for lot in plan.lots:
        assert lot.term_if_sold_now in ("long", "short")
        assert lot.acquired_at
        assert Decimal(lot.quantity_taken) > 0


def test_proposal_time_controls_the_holding_period_everywhere():
    """A generated-at test clock must also control the plan.  Otherwise a
    lot on its one-year boundary can be displayed as short-term while the
    durable proposal advisory classifies the same sale at another instant."""
    ledger = _ledger(Fill(
        ticker="MSFT", side="buy", qty=900, price=8.0,
        fill_id="boundary", at=datetime(2025, 8, 15, 12, tzinfo=timezone.utc),
    ))
    result = generate_trim_proposal(
        _packet(), OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
        lot_strategy="fifo", tax_lot_ledger=ledger,
        tax_lot_coverage=COVERAGE,
        now=datetime(2026, 8, 16, 12, tzinfo=timezone.utc),
    )
    assert result["created"]
    plan = result["plan"]
    assert Decimal(plan.realized_short_term_exact) == 0
    assert Decimal(plan.realized_long_term_exact) > 0
    assert plan.lots[0].term_if_sold_now == "long"


# --- the remainder ----------------------------------------------------------


#: A sleeve holding one big name and one small one. Both tests below need
#: the trimmed ticker to be a MINOR holding, because the restoration cap
#: makes it arithmetically impossible to sell most of a sleeve's only
#: position: restoring a 40% target from a heavily overweight sleeve always
#: leaves far more than a sub-one-share remainder. That is correct behaviour
#: rather than a limitation to work around, and it is why these fixtures
#: look the way they do.
def _two_name_growth_sleeve(msft_shares):
    return _packet([
        {"ticker": "MSFT", "shares": msft_shares,
         "entry_price": 8.0, "current_price": 10.0},
        {"ticker": "AVGO", "shares": 900,
         "entry_price": 8.0, "current_price": 10.0},
    ], cash=895.0)


def test_a_fractional_remainder_is_disclosed():
    plan = _plan(packet=_two_name_growth_sleeve(10.5), shares=10)
    assert plan.usable, plan.refusals
    assert Decimal(plan.remaining_shares_exact) == Decimal("0.5")
    assert any("less than one whole share" in d for d in plan.disclosures)


def test_closing_the_whole_position_is_stated():
    plan = _plan(packet=_two_name_growth_sleeve(10), shares=10)
    assert plan.usable, plan.refusals
    assert plan.closes_position
    assert Decimal(plan.remaining_shares_exact) == 0


def test_the_restoration_cap_prevents_gutting_a_sleeves_only_holding():
    """Recorded because it is a consequence worth knowing rather than a bug:
    with a single position carrying the whole sleeve, no sale that leaves a
    sub-one-share remainder can ever stay inside the restoration cap."""
    plan = _plan(shares=899)  # the 900-share single-name fixture
    assert not plan.usable
    assert any("restores" in r for r in plan.refusals)


# --- proposals --------------------------------------------------------------


def test_the_proposal_is_a_gated_sell_that_persists():
    """REBAL2CR-001's lesson applied: the action path is checked end to end,
    including JSON serialization, not just the in-memory object."""
    result = generate_trim_proposal(
        _packet(), OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200, lot_strategy="fifo",
        tax_lot_ledger=_ledger(), tax_lot_coverage=COVERAGE,
    )
    assert result["created"]
    proposal = result["proposal"]
    assert proposal.status == "proposed"
    assert proposal.intent.side == "sell"
    assert proposal.evidence_status == EVIDENCE_STATUS
    json.dumps(proposal.to_dict())  # must not raise


def test_the_proposal_carries_the_profile_fingerprint_for_execution_binding():
    result = generate_trim_proposal(
        _packet(), OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200, lot_strategy="fifo",
        tax_lot_ledger=_ledger(), tax_lot_coverage=COVERAGE,
    )
    impact = result["proposal"].expected_impact
    assert impact["allocation_profile_fingerprint"]
    assert impact["rebalance_realized_gain_exact"]
    assert impact["rebalance_lot_strategy"] == "fifo"


def test_execution_refuses_a_trim_from_a_non_active_profile(tmp_path):
    """A stale trim is worse than a stale buy: it realizes gains toward a
    shape the owner has since changed, and no later edit un-realizes them."""
    from assistant.execution_service import validate_proposal_for_execution
    from assistant.storage import AssistantStore

    moved = dataclasses.replace(
        OWNER_APPROVED_PROFILE,
        targets={**dict(OWNER_APPROVED_PROFILE.targets),
                 SLEEVE_GROWTH: "35", SLEEVE_HEDGE: "15"},
    )
    packet, policy = _packet(), _policy()
    result = generate_trim_proposal(
        packet, moved, policy,
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200, lot_strategy="fifo",
        tax_lot_ledger=_ledger(), tax_lot_coverage=COVERAGE,
    )
    assert result["created"]
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(result["proposal"].to_dict())

    outcome = validate_proposal_for_execution(
        result["proposal"].proposal_id, packet.portfolio, policy, store,
        now_et=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
    )
    assert not outcome.approved
    assert "allocation profile" in str(outcome.error).lower()


def test_execution_refuses_when_the_tax_lot_ledger_changed(
    tmp_path, monkeypatch
):
    """The feature refuses to propose without complete tax consequences, so
    a later ledger change cannot be allowed to make the approved card describe
    different lots from the ones execution is about to sell against."""
    from assistant import corporate_actions
    from assistant.execution_service import validate_proposal_for_execution
    from assistant.storage import AssistantStore

    packet, policy = _packet(), _policy()
    result = generate_trim_proposal(
        packet, OWNER_APPROVED_PROFILE, policy,
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
        lot_strategy="fifo", tax_lot_ledger=_ledger(),
        tax_lot_coverage=COVERAGE,
        now=datetime.now(timezone.utc),
    )
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(result["proposal"].to_dict())
    changed = _ledger(Fill(
        ticker="MSFT", side="buy", qty=900, price=9.0,
        fill_id="changed", at=datetime(2024, 1, 10, tzinfo=timezone.utc),
    ))
    monkeypatch.setattr(
        corporate_actions,
        "tax_ledger_with_coverage",
        lambda _store, _portfolio: (changed, COVERAGE),
    )

    outcome = validate_proposal_for_execution(
        result["proposal"].proposal_id, packet.portfolio, policy, store,
        now_et=datetime(2026, 8, 15, 12, tzinfo=timezone.utc),
    )
    assert not outcome.approved
    assert "tax lots changed" in str(outcome.error).lower()


def test_execution_refuses_a_legacy_trim_without_tax_lot_binding(
    tmp_path, monkeypatch
):
    from assistant import corporate_actions
    from assistant.execution_service import validate_proposal_for_execution
    from assistant.storage import AssistantStore

    packet, policy = _packet(), _policy()
    result = generate_trim_proposal(
        packet, OWNER_APPROVED_PROFILE, policy,
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
        lot_strategy="fifo", tax_lot_ledger=_ledger(),
        tax_lot_coverage=COVERAGE,
        now=datetime.now(timezone.utc),
    )
    stored = result["proposal"].to_dict()
    stored["expected_impact"].pop("rebalance_tax_lot_fingerprint", None)
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(stored)
    monkeypatch.setattr(
        corporate_actions,
        "tax_ledger_with_coverage",
        lambda _store, _portfolio: (_ledger(), COVERAGE),
    )

    outcome = validate_proposal_for_execution(
        stored["proposal_id"], packet.portfolio, policy, store,
        now_et=datetime(2026, 8, 15, 12, tzinfo=timezone.utc),
    )
    assert not outcome.approved
    assert "missing its tax-lot fingerprint" in str(outcome.error).lower()


def test_the_lot_strategy_is_part_of_proposal_identity():
    """Two trims of the same size under different strategies realize
    different gains and are different decisions."""
    ids = set()
    for strategy in ("fifo", "hifo"):
        ids.add(generate_trim_proposal(
            _packet(), OWNER_APPROVED_PROFILE, _policy(),
            sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
            lot_strategy=strategy,
            tax_lot_ledger=_ledger(), tax_lot_coverage=COVERAGE,
        )["proposal"].proposal_id)
    assert len(ids) == 2


def test_tax_lots_and_consequence_are_part_of_proposal_identity():
    """Reconciliation can change the complete ledger without changing the
    portfolio packet.  A regenerated card with a different tax consequence
    must not collide with the old stored proposal ID."""
    ids = set()
    for basis, fill_id in ((8.0, "cheap"), (9.0, "expensive")):
        ledger = _ledger(Fill(
            ticker="MSFT", side="buy", qty=900, price=basis,
            fill_id=fill_id, at=datetime(2024, 1, 10, tzinfo=timezone.utc),
        ))
        result = generate_trim_proposal(
            _packet(), OWNER_APPROVED_PROFILE, _policy(),
            sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
            lot_strategy="fifo", tax_lot_ledger=ledger,
            tax_lot_coverage=COVERAGE,
            now=datetime(2026, 8, 15, 12, tzinfo=timezone.utc),
        )
        ids.add(result["proposal"].proposal_id)
        lots = result["proposal"].expected_impact["rebalance_lots"]
        assert lots and lots[0]["lot_id"] == fill_id
    assert len(ids) == 2


def test_a_refused_plan_creates_no_proposal():
    result = generate_trim_proposal(
        _packet(), OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=600, lot_strategy="fifo",
        tax_lot_ledger=_ledger(), tax_lot_coverage=COVERAGE,
    )
    assert not result["created"]
    assert "proposal" not in result


def test_every_proposal_says_the_shape_is_unproven_and_the_tax_is_real():
    result = generate_trim_proposal(
        _packet(), OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200, lot_strategy="fifo",
        tax_lot_ledger=_ledger(), tax_lot_coverage=COVERAGE,
    )
    proposal = result["proposal"]
    joined = " ".join(proposal.uncertainties)
    assert "not a research result" in joined
    assert "lost some or all of its edge after it" in joined
    assert any("Let the sleeve run" in a for a in proposal.alternatives)


def test_the_owner_choices_are_restated_in_the_proposal():
    result = generate_trim_proposal(
        _packet(), OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200, lot_strategy="hifo",
        tax_lot_ledger=_ledger(), tax_lot_coverage=COVERAGE,
    )
    reasons = " ".join(result["proposal"].reasons)
    assert "You chose MSFT" in reasons
    assert "HIFO" in reasons
    assert "This app selects none of those" in reasons


# --- counter-review of the independent correction ---------------------------


PARTIAL_BOOK_COVERAGE = {
    # The shape `ticker_tax_ledger_with_coverage(store, portfolio, "MSFT")`
    # emits for a book holding one app-bought position and one bought before
    # the app existed: `complete` is scoped to MSFT, `portfolio_complete`
    # reports the book-wide answer for disclosure. Verified against the real
    # provider in tests/test_rebalance_trim_end_to_end.py rather than
    # asserted here -- a fixture cannot prove its own shape is real.
    "complete": True,
    "portfolio_complete": False,
    "tickers": {
        "MSFT": {"matched": True, "broker_shares": 900, "ledger_shares": 900},
        "AAPL": {"matched": False, "broker_shares": 10, "ledger_shares": 0},
    },
}


def _mixed_book_packet():
    return _packet([
        {"ticker": "MSFT", "shares": 900,
         "entry_price": 8.0, "current_price": 10.0},
        {"ticker": "AAPL", "shares": 10,
         "entry_price": 100.0, "current_price": 100.0},
    ], cash=1_000.0)


def test_an_unrelated_uncovered_holding_does_not_block_a_covered_trim():
    """ST3CCR-001. The gate belongs on the TRIMMED ticker, not the book.

    This sale realizes gains from MSFT's lots and nothing else, so MSFT's
    own `matched` flag is necessary and sufficient. Requiring the global
    `complete` flag meant a single pre-app holding anywhere refused every
    trim forever -- and `AssistantStore.list_fills` documents that positions
    "bought before the app existed, or through the Alpaca UI, produce no
    events and therefore no lots", so that is the normal case rather than an
    edge one.

    A refusal that always fires is indistinguishable from a careful
    safeguard, which is exactly how ST3R-001 stayed hidden.
    """
    plan = _plan(
        packet=_mixed_book_packet(), shares=100,
        coverage=PARTIAL_BOOK_COVERAGE,
    )
    assert plan.usable, plan.refusals
    assert Decimal(plan.realized_gain_exact) > 0


def test_the_uncovered_remainder_of_the_book_is_disclosed_not_hidden():
    """Not blocking is not the same as not mentioning: the owner should know
    the ledger is not a complete account history."""
    plan = _plan(
        packet=_mixed_book_packet(), shares=100,
        coverage=PARTIAL_BOOK_COVERAGE,
    )
    assert any(
        "not a complete account history" in d for d in plan.disclosures
    ), plan.disclosures


def test_the_trimmed_tickers_own_coverage_is_still_required():
    """The scoping must not become a licence to trim an unmatched holding."""
    # Scoped shape: `complete` false means THIS ticker is not covered.
    coverage = {
        "complete": False,
        "portfolio_complete": False,
        "tickers": {"MSFT": {"matched": False,
                             "broker_shares": 900, "ledger_shares": 0}},
    }
    plan = _plan(shares=100, coverage=coverage)
    assert not plan.usable
    assert any("incomplete" in r for r in plan.refusals)


def test_execution_revalidation_fails_closed_without_a_store(tmp_path):
    """The approval-time tax-lot branch is reached only once the profile
    fingerprint matches, so this uses the REAL one -- an earlier version
    passed a placeholder and never got past the profile check.

    Without a store or portfolio the trim cannot be revalidated, and the
    refusal must say that rather than passing silently.
    """
    from assistant.execution_service import _validate_proposal_context
    from assistant.rebalance_profile import compute_profile_fingerprint

    proposal = {
        "evidence_status": "user_directed_rebalance_trim",
        "intent": {"ticker": "MSFT"},
        "expected_impact": {
            "allocation_profile_fingerprint": compute_profile_fingerprint(
                OWNER_APPROVED_PROFILE
            ),
            "rebalance_tax_lot_fingerprint": "whatever",
        },
    }
    error = _validate_proposal_context(proposal)
    assert error is not None
    assert "could not be revalidated" in error, error



def test_execution_allows_a_covered_trim_on_a_partially_covered_book(
    tmp_path, monkeypatch
):
    """ST3CCR-001, approval side. The creation gate and the approval gate
    must agree on scope: an approval check that refuses every trim because
    some unrelated holding predates the app protects nothing, and would hide
    that the feature never worked -- the same way ST3R-001 hid.
    """
    from assistant import corporate_actions
    from assistant.execution_service import validate_proposal_for_execution
    from assistant.storage import AssistantStore

    packet, policy = _packet(), _policy()
    result = generate_trim_proposal(
        packet, OWNER_APPROVED_PROFILE, policy,
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
        lot_strategy="fifo", tax_lot_ledger=_ledger(),
        tax_lot_coverage=COVERAGE, now=datetime.now(timezone.utc),
    )
    assert result["created"], result.get("reason")
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(result["proposal"].to_dict())

    # Same ledger, but the book now reports an unrelated pre-app holding.
    monkeypatch.setattr(
        corporate_actions, "tax_ledger_with_coverage",
        lambda _store, _portfolio: (_ledger(), PARTIAL_BOOK_COVERAGE),
    )
    outcome = validate_proposal_for_execution(
        result["proposal"].proposal_id, packet.portfolio, policy, store,
        now_et=datetime(2026, 8, 15, 12, tzinfo=timezone.utc),
    )
    assert "tax-lot coverage" not in str(outcome.error or "").lower(), (
        outcome.error
    )

def test_an_untrimmable_overweight_sleeve_is_reported_separately():
    """REBAL3V-001. The old generic helper filtered on two independent
    conditions -- above the band AND trimmable -- so an empty result could
    not say which one failed. The owner hit this on a real book: the page
    reported six breached bands in its headline and, three sections lower,
    "No sleeve is above its upper band". Both statements cannot be true.
    """
    import assistant.context_builder as context_builder
    from assistant.policy import load_policy
    from assistant.portfolio_rebalance import evaluate_portfolio_rebalance
    from assistant.rebalance_profile import OWNER_APPROVED_PROFILE
    from assistant.rebalance_trim import (
        classify_overweight_sleeves,
    )

    # AAPL belongs to no sleeve, so it lands in the residual.
    snapshot = context_builder.build_portfolio_snapshot(
        [{
            "ticker": "AAPL", "shares": 100,
            "entry_price": 150.0, "current_price": 200.0,
        }],
        cash=20_000.0,
    )
    report = evaluate_portfolio_rebalance(
        snapshot, OWNER_APPROVED_PROFILE, policy=load_policy()
    )

    over = [r.sleeve for r in report.rows if r.band_state == "overweight"]
    assert over == ["cash", "other_unassigned"], over
    # Nothing is trimmable, which is correct and must not change...
    groups = classify_overweight_sleeves(report)
    assert groups.trimmable == ()
    # ...but the reason is returned in the same classification, not lost.
    assert groups.untrimmable == ("cash", "other_unassigned")


def test_nothing_overweight_at_all_stays_distinguishable():
    """The other cause of an empty trimmable list must stay distinct, or the
    fix would simply move the false statement to the other case."""
    import assistant.context_builder as context_builder
    from assistant.policy import load_policy
    from assistant.portfolio_rebalance import evaluate_portfolio_rebalance
    from assistant.rebalance_profile import OWNER_APPROVED_PROFILE
    from assistant.rebalance_trim import (
        classify_overweight_sleeves,
    )

    snapshot = context_builder.build_portfolio_snapshot([], cash=0.0)
    report = evaluate_portfolio_rebalance(
        snapshot, OWNER_APPROVED_PROFILE, policy=load_policy()
    )
    groups = classify_overweight_sleeves(report)
    assert groups.trimmable == ()
    assert groups.untrimmable == ()
