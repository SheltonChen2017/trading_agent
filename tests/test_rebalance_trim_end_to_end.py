"""REBAL-1 Stage 3 against a REAL store, real fills, and the real providers.

This file exists because three consecutive rounds of this feature failed the
same way, and none of the existing tests could have caught any of them:

* Stage 2 asserted on in-memory proposal fields and never drove
  `save_proposal`, so a `Decimal` in `reference_price` crashed the only
  action path (REBAL2CR-001);
* Stage 3 asserted against a hand-written coverage fixture whose shape did
  not exist, so `tax_ledger_with_coverage` never matched and every trim was
  refused, always (ST3R-001); and
* the correction for that still required GLOBAL coverage completeness, which
  no book containing a pre-app holding can satisfy, so every trim was still
  refused (ST3CCR-001).

Every one of those was an interface-shape mistake. A fixture written from an
assumption cannot detect that the assumption is wrong, and two of the three
produced a refusal that always fired — which reads exactly like a careful
safeguard.

So nothing here invents a shape. Fills are journaled through
`journal_broker_order_update`, the ledger and coverage come from
`tax_ledger_with_coverage`, the proposal is persisted through
`AssistantStore.save_proposal`, and approval runs through
`validate_proposal_for_execution`. The only stubs are the broker seam and
the clock.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.corporate_actions import (
    tax_ledger_with_coverage,
    ticker_tax_ledger_with_coverage,
)
from assistant.order_lifecycle import journal_broker_order_update
from assistant.policy import TradingPolicy
from assistant.rebalance_profile import OWNER_APPROVED_PROFILE, SLEEVE_GROWTH
from assistant.rebalance_trim import generate_trim_proposal, plan_trim
from assistant.schemas import DecisionPacket, MarketRegime
from assistant.storage import AssistantStore

BUY_AT = datetime(2024, 1, 10, 15, 30, tzinfo=timezone.utc)


def _policy(**overrides):
    fields = dict(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0,
        max_order_value=500_000.0, allow_new_positions=True,
    )
    fields.update(overrides)
    return TradingPolicy(**fields)


def _packet(positions, cash):
    snapshot = build_portfolio_snapshot(positions, cash=cash)
    return DecisionPacket(
        generated_at="2026-08-15T12:00:00+00:00", portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="SPY", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-08-14",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _journal_real_buy(store, *, ticker, qty, price, at, suffix="1"):
    """Record a filled BUY the way the app records one.

    `list_fills` reads ticker and side from the LINKED PROPOSAL's intent
    rather than from the event row, so a fill only exists once both the
    proposal and its order event do. Seeding the table directly would
    reproduce the very assumption this file exists to stop making.
    """
    proposal_id = f"tp_seed_{ticker.lower()}_{suffix}"
    store.save_proposal({
        "proposal_id": proposal_id,
        "created_at": at.isoformat(),
        "expires_at": (at + timedelta(minutes=15)).isoformat(),
        "status": "approved",
        "idempotency_key": f"{proposal_id}-seed",
        "policy_version": "test",
        "policy_fingerprint": "seed",
        "intent": {
            "ticker": ticker, "side": "buy", "shares": qty,
            "order_type": "market", "rationale": "seeded history",
        },
        "reference_price": price,
        "price_timestamp": at.isoformat(),
        "reasons": [], "evidence_status": "user_directed_discrete_buy",
        "expected_impact": {}, "alternatives": [], "uncertainties": [],
    })
    # Keys taken from what `project_broker_order_event` actually reads
    # (`order_id`, `proposal_id`, `filled_qty`, `filled_avg_price`,
    # `submitted_at`), not from what an order dict looks like elsewhere.
    order = {
        "order_id": f"ord_{proposal_id}",
        "proposal_id": proposal_id,
        "status": "filled",
        "filled_qty": qty,
        "filled_avg_price": price,
        "filled_at": at.isoformat(),
        "submitted_at": at.isoformat(),
    }
    journal_broker_order_update(
        store, proposal_id=proposal_id, order=order,
        event_type="fill", event_at=at.isoformat(),
        fill_qty=qty, fill_price=price,
    )
    return proposal_id


@pytest.fixture()
def store(tmp_path):
    return AssistantStore(tmp_path / "assistant.db")


# --- the real journal produces real lots ------------------------------------


def test_a_journaled_fill_becomes_a_real_tax_lot(store):
    """Establishes the fixture is genuine before anything is asserted on it."""
    _journal_real_buy(store, ticker="MSFT", qty=900, price=8.0, at=BUY_AT)
    fills = store.list_fills()
    assert [f["ticker"] for f in fills] == ["MSFT"]
    assert fills[0]["side"] == "buy"
    assert fills[0]["qty"] == 900


def test_the_real_provider_reports_this_holding_as_matched(store):
    """The shape assertion that would have caught ST3R-001: per-ticker
    coverage carries `matched`, and never a `complete` key."""
    _journal_real_buy(store, ticker="MSFT", qty=900, price=8.0, at=BUY_AT)
    snapshot = build_portfolio_snapshot(
        [{"ticker": "MSFT", "shares": 900,
          "entry_price": 8.0, "current_price": 10.0}],
        cash=1_000.0,
    )
    ledger, coverage = tax_ledger_with_coverage(store, snapshot)
    assert ledger is not None
    per_ticker = coverage["tickers"]["MSFT"]
    assert per_ticker["matched"] is True
    assert "complete" not in per_ticker, (
        "Stage 3 once read a per-ticker 'complete' key that has never existed"
    )
    assert coverage["complete"] is True


# --- the whole action path, end to end --------------------------------------


def test_a_trim_can_actually_be_proposed_from_real_journaled_history(store):
    """THE test. Everything from a journaled fill to a persisted proposal,
    with no invented fixture anywhere in the chain.

    On the submitted Stage 3 this failed at `plan_trim`, because the real
    coverage shape never matched what the code read.
    """
    _journal_real_buy(store, ticker="MSFT", qty=900, price=8.0, at=BUY_AT)
    packet = _packet(
        [{"ticker": "MSFT", "shares": 900,
          "entry_price": 8.0, "current_price": 10.0}],
        cash=1_000.0,
    )
    ledger, coverage = tax_ledger_with_coverage(store, packet.portfolio)

    plan = plan_trim(
        packet, OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
        lot_strategy="fifo",
        tax_lot_ledger=ledger, tax_lot_coverage=coverage,
    )
    assert plan.usable, plan.refusals
    assert plan.lots, "the real ledger must yield real lots"
    # 200 shares bought at $8 and marked at $10
    assert Decimal(plan.realized_gain_exact) == Decimal("400")
    assert plan.lots[0].term_if_sold_now == "long"


def test_the_proposal_persists_and_reloads_unchanged(store):
    """Would have caught REBAL2CR-001: the proposal must survive the real
    JSON round trip through the real store, not merely exist in memory."""
    _journal_real_buy(store, ticker="MSFT", qty=900, price=8.0, at=BUY_AT)
    packet = _packet(
        [{"ticker": "MSFT", "shares": 900,
          "entry_price": 8.0, "current_price": 10.0}],
        cash=1_000.0,
    )
    ledger, coverage = tax_ledger_with_coverage(store, packet.portfolio)
    result = generate_trim_proposal(
        packet, OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
        lot_strategy="fifo", tax_lot_ledger=ledger, tax_lot_coverage=coverage,
    )
    assert result["created"], result.get("reason")

    payload = result["proposal"].to_dict()
    json.dumps(payload)          # the encode save_proposal performs
    store.save_proposal(payload)

    reloaded = store.get_proposal(result["proposal"].proposal_id)
    assert reloaded is not None
    assert reloaded["intent"]["side"] == "sell"
    assert reloaded["intent"]["shares"] == 200
    assert reloaded["expected_impact"]["rebalance_tax_lot_fingerprint"]
    assert reloaded["expected_impact"]["allocation_profile_fingerprint"]


def test_approval_accepts_the_proposal_it_just_created(store, monkeypatch):
    """The approval gate must not refuse a proposal generated moments earlier
    from the same journal. Both ST3R-001 and ST3CCR-001 produced exactly that
    contradiction -- a card the app made and then would not honour."""
    from assistant.execution_service import _validate_proposal_context

    _journal_real_buy(store, ticker="MSFT", qty=900, price=8.0, at=BUY_AT)
    packet = _packet(
        [{"ticker": "MSFT", "shares": 900,
          "entry_price": 8.0, "current_price": 10.0}],
        cash=1_000.0,
    )
    ledger, coverage = tax_ledger_with_coverage(store, packet.portfolio)
    result = generate_trim_proposal(
        packet, OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
        lot_strategy="fifo", tax_lot_ledger=ledger, tax_lot_coverage=coverage,
    )
    assert result["created"], result.get("reason")
    store.save_proposal(result["proposal"].to_dict())

    error = _validate_proposal_context(
        result["proposal"].to_dict(), packet.portfolio, store
    )
    assert error is None, error


def test_a_pre_app_holding_elsewhere_does_not_block_the_covered_trim(store):
    """ST3CCR-001 against the real provider rather than a fixture.

    AAPL is held but was never bought through the app, so it has no lots and
    the GLOBAL coverage flag is false -- the documented normal case. MSFT's
    own history is complete, which is what this sale's realized gain depends
    on, so the trim must still be possible.
    """
    _journal_real_buy(store, ticker="MSFT", qty=900, price=8.0, at=BUY_AT)
    packet = _packet(
        [
            {"ticker": "MSFT", "shares": 900,
             "entry_price": 8.0, "current_price": 10.0},
            {"ticker": "AAPL", "shares": 10,
             "entry_price": 100.0, "current_price": 100.0},
        ],
        cash=1_000.0,
    )
    # The portfolio-wide provider withholds the ledger ENTIRELY when any
    # holding is unreconciled -- that is its documented contract, and it is
    # why scoping only the `matched` check was not enough. Stage 3 asks the
    # narrower per-ticker question instead.
    whole_book, whole_coverage = tax_ledger_with_coverage(store, packet.portfolio)
    assert whole_book is None
    assert whole_coverage["complete"] is False

    ledger, coverage = ticker_tax_ledger_with_coverage(
        store, packet.portfolio, "MSFT"
    )
    # the premise, asserted rather than assumed
    assert ledger is not None
    assert coverage["complete"] is True
    assert coverage["portfolio_complete"] is False
    assert coverage["tickers"]["AAPL"]["matched"] is False

    plan = plan_trim(
        packet, OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
        lot_strategy="fifo", tax_lot_ledger=ledger, tax_lot_coverage=coverage,
    )
    assert plan.usable, plan.refusals
    assert any(
        "not a complete account history" in d for d in plan.disclosures
    ), "the uncovered remainder must still be disclosed"


def test_an_untracked_holding_cannot_itself_be_trimmed(store):
    """The other direction: scoping the gate to one ticker must not become a
    licence to trim a position the app has no history for."""
    _journal_real_buy(store, ticker="MSFT", qty=900, price=8.0, at=BUY_AT)
    packet = _packet(
        [
            {"ticker": "MSFT", "shares": 400,
             "entry_price": 8.0, "current_price": 10.0},
            {"ticker": "AVGO", "shares": 500,
             "entry_price": 8.0, "current_price": 10.0},
        ],
        cash=1_000.0,
    )
    ledger, coverage = tax_ledger_with_coverage(store, packet.portfolio)
    assert coverage["tickers"]["AVGO"]["matched"] is False

    plan = plan_trim(
        packet, OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="AVGO", shares=100,
        lot_strategy="fifo", tax_lot_ledger=ledger, tax_lot_coverage=coverage,
    )
    assert not plan.usable
    assert any("incomplete" in r for r in plan.refusals)


def test_a_later_real_fill_invalidates_an_earlier_proposal(store):
    """The tax-lot fingerprint must bind to the real journal: a fill recorded
    after the card was made changes the lots the sale would consume, so the
    stored card must stop being honoured."""
    from assistant.execution_service import _validate_proposal_context

    _journal_real_buy(store, ticker="MSFT", qty=900, price=8.0, at=BUY_AT)
    packet = _packet(
        [{"ticker": "MSFT", "shares": 900,
          "entry_price": 8.0, "current_price": 10.0}],
        cash=1_000.0,
    )
    ledger, coverage = tax_ledger_with_coverage(store, packet.portfolio)
    result = generate_trim_proposal(
        packet, OWNER_APPROVED_PROFILE, _policy(),
        sleeve=SLEEVE_GROWTH, ticker="MSFT", shares=200,
        lot_strategy="fifo", tax_lot_ledger=ledger, tax_lot_coverage=coverage,
    )
    assert result["created"], result.get("reason")
    store.save_proposal(result["proposal"].to_dict())

    # a genuinely new lot arrives through the same journal path
    _journal_real_buy(
        store, ticker="MSFT", qty=100, price=9.5,
        at=datetime(2026, 7, 1, 15, 30, tzinfo=timezone.utc), suffix="2",
    )
    later = _packet(
        [{"ticker": "MSFT", "shares": 1_000,
          "entry_price": 8.15, "current_price": 10.0}],
        cash=1_000.0,
    )
    error = _validate_proposal_context(
        result["proposal"].to_dict(), later.portfolio, store
    )
    assert error is not None
    assert "tax lots changed" in error.lower(), error


def test_the_scoped_provider_withholds_the_ledger_for_an_uncovered_ticker(
    store,
):
    """The provider's own contract, not just the caller's gate.

    Removing its `matched` early-return left every downstream test green,
    because `plan_trim` refuses on the coverage flag anyway. That is
    defence in depth working, but it also means the provider could hand a
    ledger back for a position it cannot account for -- and the next caller
    might read the ledger without re-checking the flag.
    """
    _journal_real_buy(store, ticker="MSFT", qty=900, price=8.0, at=BUY_AT)
    snapshot = build_portfolio_snapshot(
        [
            {"ticker": "MSFT", "shares": 900,
             "entry_price": 8.0, "current_price": 10.0},
            {"ticker": "AAPL", "shares": 10,
             "entry_price": 100.0, "current_price": 100.0},
        ],
        cash=1_000.0,
    )
    ledger, coverage = ticker_tax_ledger_with_coverage(store, snapshot, "AAPL")
    assert coverage["complete"] is False
    assert ledger is None, (
        "an uncovered ticker must not receive a ledger it cannot account for"
    )


def test_the_scoped_provider_refuses_an_empty_ticker(store):
    ledger, coverage = ticker_tax_ledger_with_coverage(store, build_portfolio_snapshot([], cash=0.0), "   ")
    assert ledger is None
    assert coverage["complete"] is False
