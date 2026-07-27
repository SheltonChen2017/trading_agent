"""Tests for policy, persistence, proposals, and gated paper execution."""
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import execution.alpaca_broker as broker
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.execution_service import execute_approved_paper_proposal
from assistant.policy import TradingPolicy, load_policy
from assistant.proposals import generate_risk_reduction_proposals
from assistant.schemas import DecisionPacket, MarketRegime
from assistant.storage import AssistantStore
from risk.execution_gate import (
    TradeIntent,
    ValidationResult,
    authorize_trade_intent,
    verify_execution_authorization,
)


def _packet():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "TQQQ",
                "shares": 100,
                "entry_price": 50.0,
                "current_price": 50.0,
            }
        ],
        cash=5_000.0,
    )
    return DecisionPacket(
        generated_at="2026-07-26T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ",
            trend="uptrend",
            volatility_regime="low_vol",
            trailing_volatility_pct=1.0,
            as_of="2026-07-25",
        ),
        signals=[],
        upcoming_events=[],
        warnings=[],
        policy_version="test",
    )


def _policy():
    return TradingPolicy(
        version="test",
        name="test",
        execution_mode="paper",
        max_position_pct=0.25,
        max_total_exposure_pct=0.90,
        max_basket_pct=0.90,
        max_leveraged_etf_pct=0.20,
        min_cash_reserve_pct=0.0,
        max_order_value=5_000.0,
    )


def test_default_policy_loads_and_validates():
    policy = load_policy()
    assert policy.execution_mode == "paper"
    assert policy.allow_new_positions is False
    assert policy.enable_strategy_proposals is False


def test_policy_rejects_invalid_percentages():
    policy = TradingPolicy(version="bad", name="bad", max_position_pct=1.5)
    try:
        policy.validate()
        assert False, "expected invalid policy to fail"
    except ValueError:
        pass


def test_proposals_are_risk_reducing_sells_only():
    proposals = generate_risk_reduction_proposals(_packet(), _policy())
    assert proposals
    assert all(proposal.intent.side == "sell" for proposal in proposals)
    assert all(proposal.evidence_status == "deterministic_risk_policy" for proposal in proposals)
    assert proposals[0].expected_impact["position_weight_after_pct"] < proposals[0].expected_impact["position_weight_before_pct"]


def test_store_does_not_reset_an_executed_proposal():
    proposal = generate_risk_reduction_proposals(_packet(), _policy())[0].to_dict()
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal)
        store.update_proposal_status(proposal["proposal_id"], "executed", executed_at="2026-07-26T12:00:00+00:00")
        store.save_proposal(proposal)
        assert store.get_proposal(proposal["proposal_id"])["status"] == "executed"


def test_list_broker_orders_attaches_originating_intent():
    proposal = generate_risk_reduction_proposals(_packet(), _policy())[0].to_dict()
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal)
        store.record_broker_order(
            proposal["proposal_id"],
            {"order_id": "paper-order-1", "ticker": proposal["intent"]["ticker"], "shares": proposal["intent"]["shares"], "side": "sell", "status": "accepted"},
        )
        orders = store.list_broker_orders()
        assert len(orders) == 1
        assert orders[0]["order_id"] == "paper-order-1"
        assert orders[0]["intent"]["ticker"] == proposal["intent"]["ticker"]
        assert orders[0]["evidence_status"] == proposal["evidence_status"]


def test_list_broker_orders_empty_when_none_recorded():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        assert store.list_broker_orders() == []


def test_execution_authorization_is_bound_to_exact_intent():
    intent = TradeIntent(ticker="AAPL", side="sell", shares=2)
    authorization = authorize_trade_intent(intent, ValidationResult(True, []))
    verify_execution_authorization(intent, authorization)
    try:
        verify_execution_authorization(
            TradeIntent(ticker="AAPL", side="sell", shares=3),
            authorization,
        )
        assert False, "expected mismatched quantity to fail"
    except PermissionError:
        pass


def test_broker_rejects_direct_order_without_gate_authorization():
    broker.PAPER_TRADING = True
    try:
        broker.submit_market_order("AAPL", 1, side="buy")
        assert False, "expected direct broker submission to fail"
    except PermissionError:
        pass


def test_approved_proposal_is_revalidated_and_submitted_once():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    original_is_configured = broker.is_configured
    original_submit = broker.submit_market_order
    original_paper = broker.PAPER_TRADING
    captured = []
    try:
        broker.PAPER_TRADING = True
        broker.is_configured = lambda: True

        def fake_submit(ticker, shares, side="buy", *, authorization=None, idempotency_key=None):
            assert authorization is not None
            captured.append((ticker, shares, side, idempotency_key))
            return {
                "order_id": "paper-1",
                "ticker": ticker,
                "shares": shares,
                "side": side,
                "status": "accepted",
            }

        broker.submit_market_order = fake_submit
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            order = execute_approved_paper_proposal(
                proposal.proposal_id,
                f"APPROVE {proposal.proposal_id}",
                packet.portfolio,
                policy,
                store,
                now_et=datetime(2026, 7, 27, 10, 0),
            )
            assert order["order_id"] == "paper-1"
            assert store.get_proposal(proposal.proposal_id)["status"] == "executed"
            assert len(captured) == 1
    finally:
        broker.is_configured = original_is_configured
        broker.submit_market_order = original_submit
        broker.PAPER_TRADING = original_paper
