"""Tests for policy, persistence, proposals, and gated paper execution."""
import dataclasses
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import execution.alpaca_broker as broker
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.execution_service import ProposalExecutionError, execute_approved_paper_proposal
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


def test_claim_proposal_is_atomic_only_one_winner():
    proposal = generate_risk_reduction_proposals(_packet(), _policy())[0].to_dict()
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal)
        first = store.claim_proposal(proposal["proposal_id"])
        second = store.claim_proposal(proposal["proposal_id"])
        assert first is not None
        assert first["status"] == "validating"
        assert second is None  # the second "concurrent" caller must not also win


def test_claim_proposal_returns_none_for_unknown_id():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        assert store.claim_proposal("tp_does_not_exist") is None


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


def _mock_execution_dependencies(quote_price=50.0, quote_timestamp=None, earnings_available=False):
    """Patches broker.is_configured/get_latest_quote/submit_market_order and
    data.event_data.fetch_upcoming_earnings so execute_approved_paper_proposal()
    tests never hit the network. Returns (captured_orders, restore_fn)."""
    import data.event_data as event_data

    quote_timestamp = quote_timestamp or datetime(2026, 7, 27, 9, 59, tzinfo=timezone.utc)
    captured = []
    originals = {
        "is_configured": broker.is_configured,
        "get_latest_quote": getattr(broker, "get_latest_quote", None),
        "submit_market_order": broker.submit_market_order,
        "PAPER_TRADING": broker.PAPER_TRADING,
        "fetch_upcoming_earnings": event_data.fetch_upcoming_earnings,
    }

    broker.PAPER_TRADING = True
    broker.is_configured = lambda: True
    broker.get_latest_quote = lambda ticker: {"ticker": ticker, "price": quote_price, "timestamp": quote_timestamp}
    event_data.fetch_upcoming_earnings = lambda tickers, as_of=None: {
        t: {"ticker": t, "available": earnings_available, "days_away": 1 if earnings_available else None}
        for t in tickers
    }

    def fake_submit(ticker, shares, side="buy", *, authorization=None, idempotency_key=None):
        assert authorization is not None
        captured.append((ticker, shares, side, idempotency_key))
        return {"order_id": "paper-1", "ticker": ticker, "shares": shares, "side": side, "status": "accepted"}

    broker.submit_market_order = fake_submit

    def restore():
        broker.is_configured = originals["is_configured"]
        broker.submit_market_order = originals["submit_market_order"]
        broker.PAPER_TRADING = originals["PAPER_TRADING"]
        event_data.fetch_upcoming_earnings = originals["fetch_upcoming_earnings"]
        if originals["get_latest_quote"] is not None:
            broker.get_latest_quote = originals["get_latest_quote"]
        else:
            del broker.get_latest_quote

    return captured, restore


def test_approved_proposal_is_revalidated_and_submitted_once():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            order = execute_approved_paper_proposal(
                proposal.proposal_id,
                f"APPROVE {proposal.proposal_id}",
                packet.portfolio,
                policy,
                store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert order["order_id"] == "paper-1"
            assert store.get_proposal(proposal.proposal_id)["status"] == "executed"
            assert len(captured) == 1
    finally:
        restore()


def test_approval_fails_closed_when_open_orders_unavailable():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    unreliable_portfolio = dataclasses.replace(packet.portfolio, open_orders_available=False)
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id,
                    f"APPROVE {proposal.proposal_id}",
                    unreliable_portfolio,
                    policy,
                    store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected approval to fail closed when open orders can't be verified"
            except ProposalExecutionError as exc:
                assert "open orders" in str(exc)
            assert len(captured) == 0
            assert store.get_proposal(proposal.proposal_id)["status"] == "blocked"
    finally:
        restore()


def test_approval_blocked_when_earnings_are_near():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price, earnings_available=True)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id,
                    f"APPROVE {proposal.proposal_id}",
                    packet.portfolio,
                    policy,
                    store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected the earnings blackout to block this proposal"
            except ProposalExecutionError as exc:
                assert "earnings" in str(exc).lower()
            assert len(captured) == 0
    finally:
        restore()


def test_approval_blocked_when_quote_is_stale():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    stale_timestamp = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)  # days old, not minutes
    captured, restore = _mock_execution_dependencies(
        quote_price=proposal.reference_price, quote_timestamp=stale_timestamp
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id,
                    f"APPROVE {proposal.proposal_id}",
                    packet.portfolio,
                    policy,
                    store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected a stale quote to block this proposal"
            except ProposalExecutionError as exc:
                assert "stale" in str(exc).lower() or "minute" in str(exc).lower()
            assert len(captured) == 0
    finally:
        restore()


def test_regenerating_a_proposal_same_day_produces_a_new_id_not_a_collision():
    policy = _policy()
    # _packet()'s generated_at is a fixed literal; simulate two separate
    # `propose` invocations (same portfolio.as_of date, different
    # generated_at timestamps) the way _load_packet() actually would.
    packet_a = _packet()
    packet_b = dataclasses.replace(packet_a, generated_at="2026-07-26T15:00:00+00:00")
    first = generate_risk_reduction_proposals(packet_a, policy)[0]
    second = generate_risk_reduction_proposals(packet_b, policy)[0]
    assert first.proposal_id != second.proposal_id

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(first.to_dict())
        store.update_proposal_status(first.proposal_id, "expired")
        store.save_proposal(second.to_dict())
        # The regenerated proposal must be saved fresh as "proposed", not
        # silently no-op'd against the first (now-expired) row.
        assert store.get_proposal(second.proposal_id)["status"] == "proposed"
        assert store.get_proposal(first.proposal_id)["status"] == "expired"


def _buy_proposal_dict(packet, policy, ticker: str, shares: int) -> dict:
    """Hand-built buy TradeProposal dict -- generate_risk_reduction_proposals()
    only ever produces sells, so tests that need a buy (e.g. for
    require_earnings_data, which only applies to buys) build one directly."""
    from assistant.proposals import TradeProposal, _stable_id
    from risk.execution_gate import TradeIntent

    intent = TradeIntent(ticker=ticker, side="buy", shares=shares, order_type="market")
    proposal_id = _stable_id(packet, policy, intent)
    return TradeProposal(
        proposal_id=proposal_id,
        created_at=packet.generated_at,
        expires_at="2026-12-31T00:00:00+00:00",
        status="proposed",
        idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
        policy_version=policy.version,
        intent=intent,
        reference_price=50.0,
        price_timestamp=packet.generated_at,
        reasons=["test buy"],
        evidence_status="test",
        expected_impact={"trade_value": shares * 50.0, "position_weight_before_pct": 0, "position_weight_after_pct": 0, "cash_before": 0, "cash_after": 0, "invested_pct_after": 0},
        alternatives=[],
        uncertainties=[],
    ).to_dict()


def test_expired_approval_attempt_cannot_alter_an_executed_proposal():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            execute_approved_paper_proposal(
                proposal.proposal_id,
                f"APPROVE {proposal.proposal_id}",
                packet.portfolio,
                policy,
                store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert store.get_proposal(proposal.proposal_id)["status"] == "executed"

            # Re-invoke approval for the SAME (now executed) proposal_id,
            # far past its expires_at -- must not flip status back to
            # "expired" and must not submit a second order.
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id,
                    f"APPROVE {proposal.proposal_id}",
                    packet.portfolio,
                    policy,
                    store,
                    now_et=datetime(2026, 12, 31, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected re-approval of an executed proposal to be rejected"
            except ProposalExecutionError:
                pass
            assert store.get_proposal(proposal.proposal_id)["status"] == "executed"
            assert len(captured) == 1  # still only the one real submission
    finally:
        restore()


def test_require_earnings_data_blocks_buy_when_unavailable_but_not_sell():
    packet = _packet()
    policy = dataclasses.replace(_policy(), require_earnings_data=True)
    buy_proposal = _buy_proposal_dict(packet, policy, "TQQQ", 10)  # TQQQ already held in _packet()
    captured, restore = _mock_execution_dependencies(quote_price=50.0, earnings_available=False)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(buy_proposal)
            try:
                execute_approved_paper_proposal(
                    buy_proposal["proposal_id"],
                    f"APPROVE {buy_proposal['proposal_id']}",
                    packet.portfolio,
                    policy,
                    store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected the buy to be blocked when earnings data is unavailable"
            except ProposalExecutionError as exc:
                assert "earnings" in str(exc).lower()
            assert len(captured) == 0

        # A risk-reducing SELL must NOT be blocked by the same policy --
        # blocking a concentration-reducing sale would increase risk.
        sell_proposal = generate_risk_reduction_proposals(packet, policy)[0]
        captured2, restore2 = None, None
        with tempfile.TemporaryDirectory() as temp2:
            store2 = AssistantStore(Path(temp2) / "assistant.db")
            store2.save_proposal(sell_proposal.to_dict())
            order = execute_approved_paper_proposal(
                sell_proposal.proposal_id,
                f"APPROVE {sell_proposal.proposal_id}",
                packet.portfolio,
                policy,
                store2,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert order["order_id"] == "paper-1"
    finally:
        restore()


def test_unexpected_exception_during_validation_marks_validation_failed_not_stuck():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    import assistant.execution_service as execution_service

    original_validate = execution_service.validate_trade_intent

    def broken_validate(*args, **kwargs):
        raise ValueError("simulated unexpected bug")

    execution_service.validate_trade_intent = broken_validate
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id,
                    f"APPROVE {proposal.proposal_id}",
                    packet.portfolio,
                    policy,
                    store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected the unexpected exception to propagate"
            except ValueError:
                pass
            # Must NOT be stuck in "validating" forever, and must NOT be
            # silently reset to "proposed" either.
            status = store.get_proposal(proposal.proposal_id)["status"]
            assert status == "validation_failed", status
    finally:
        execution_service.validate_trade_intent = original_validate
        restore()
