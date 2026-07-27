"""Tests for policy, persistence, proposals, and gated paper execution."""
import dataclasses
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
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
    validate_trade_intent,
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
    portfolio = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}], cash=1000.0,
    )
    validation = validate_trade_intent(intent, portfolio, reference_price=100.0)
    assert validation.approved
    authorization = authorize_trade_intent(intent, validation)
    verify_execution_authorization(intent, authorization)
    try:
        verify_execution_authorization(
            TradeIntent(ticker="AAPL", side="sell", shares=3),
            authorization,
        )
        assert False, "expected mismatched quantity to fail"
    except PermissionError:
        pass


def test_authorize_trade_intent_rejects_a_validation_result_for_a_different_intent():
    # Regression test (Codex review, 2026-07-27): a ValidationResult must
    # actually have been produced by validating THIS intent -- otherwise
    # nothing stops pairing an approved result from a small, validated
    # trade with a different, never-validated (e.g. oversized) intent.
    small_intent = TradeIntent(ticker="AAPL", side="sell", shares=1)
    big_intent = TradeIntent(ticker="AAPL", side="sell", shares=1000)
    portfolio = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}], cash=1000.0,
    )
    validation_for_small_trade = validate_trade_intent(small_intent, portfolio, reference_price=100.0)
    assert validation_for_small_trade.approved
    try:
        authorize_trade_intent(big_intent, validation_for_small_trade)
        assert False, "expected a mismatched (intent, validation) pair to be rejected"
    except ValueError:
        pass


def test_hand_constructed_validation_result_cannot_forge_authorization():
    # Regression test (Codex review, 2026-07-30): the fingerprint alone is
    # a PUBLIC hash of the intent's own fields -- any code that imports
    # TradeIntent can compute it, so a hand-built ValidationResult with a
    # correctly-computed fingerprint used to pass authorize_trade_intent()
    # without ever calling validate_trade_intent(). Now the proof is an
    # HMAC keyed by a process-local secret, which can't be reproduced from
    # the intent's public fields alone.
    from risk.execution_gate import intent_fingerprint

    intent = TradeIntent(ticker="AAPL", side="buy", shares=1)
    forged = ValidationResult(True, [], validation_proof=intent_fingerprint(intent))
    try:
        authorize_trade_intent(intent, forged)
        assert False, "expected a hand-constructed ValidationResult to be rejected"
    except ValueError:
        pass


def test_hand_constructed_execution_authorization_cannot_forge_verification():
    # Same forgery attempt one level up: directly constructing an
    # ExecutionAuthorization (instead of going through
    # authorize_trade_intent()) with a guessed/public-hash `proof` must
    # not verify either (Codex review, 2026-07-30).
    from risk.execution_gate import ExecutionAuthorization, intent_fingerprint

    intent = TradeIntent(ticker="AAPL", side="buy", shares=1)
    now = datetime.now(timezone.utc)
    forged = ExecutionAuthorization(
        token="fake",
        intent_fingerprint=intent_fingerprint(intent),
        proof=intent_fingerprint(intent),
        approved_at=now.isoformat(),
        expires_at=(now + timedelta(seconds=120)).isoformat(),
    )
    try:
        verify_execution_authorization(intent, forged)
        assert False, "expected a hand-constructed ExecutionAuthorization to be rejected"
    except PermissionError:
        pass


def test_broker_rejects_direct_order_without_gate_authorization():
    broker.PAPER_TRADING = True
    try:
        broker.submit_market_order("AAPL", 1, side="buy")
        assert False, "expected direct broker submission to fail"
    except PermissionError:
        pass


def _mock_execution_dependencies(
    quote_price=50.0, quote_timestamp=None, earnings_available=False, bid=None, ask=None,
):
    """Patches broker.is_configured/get_latest_quote/submit_market_order/
    submit_limit_order/find_order_by_client_id and
    data.event_data.fetch_upcoming_earnings so execute_approved_paper_proposal()
    tests never hit the network. Returns (captured_orders, restore_fn)."""
    import data.event_data as event_data

    quote_timestamp = quote_timestamp or datetime(2026, 7, 27, 9, 59, tzinfo=timezone.utc)
    captured = []
    originals = {
        "is_configured": broker.is_configured,
        "get_latest_quote": getattr(broker, "get_latest_quote", None),
        "submit_market_order": broker.submit_market_order,
        "submit_limit_order": broker.submit_limit_order,
        "find_order_by_client_id": broker.find_order_by_client_id,
        "PAPER_TRADING": broker.PAPER_TRADING,
        "fetch_upcoming_earnings": event_data.fetch_upcoming_earnings,
    }

    broker.PAPER_TRADING = True
    broker.is_configured = lambda: True

    def fake_quote(ticker):
        quote = {"ticker": ticker, "price": quote_price, "timestamp": quote_timestamp}
        if bid is not None:
            quote["bid"] = bid
        if ask is not None:
            quote["ask"] = ask
        return quote

    broker.get_latest_quote = fake_quote
    event_data.fetch_upcoming_earnings = lambda tickers, as_of=None: {
        t: {"ticker": t, "available": earnings_available, "days_away": 1 if earnings_available else None}
        for t in tickers
    }

    def fake_submit(ticker, shares, side="buy", *, authorization=None, idempotency_key=None):
        assert authorization is not None
        captured.append((ticker, shares, side, idempotency_key))
        return {"order_id": "paper-1", "ticker": ticker, "shares": shares, "side": side, "status": "accepted"}

    def fake_submit_limit(ticker, shares, limit_price, side="buy", *, authorization=None, idempotency_key=None):
        assert authorization is not None
        captured.append((ticker, shares, side, idempotency_key, limit_price))
        return {
            "order_id": "paper-limit-1", "ticker": ticker, "shares": shares, "side": side,
            "limit_price": limit_price, "status": "accepted",
        }

    broker.submit_market_order = fake_submit
    broker.submit_limit_order = fake_submit_limit
    broker.find_order_by_client_id = lambda client_order_id: None

    def restore():
        broker.is_configured = originals["is_configured"]
        broker.submit_market_order = originals["submit_market_order"]
        broker.submit_limit_order = originals["submit_limit_order"]
        broker.find_order_by_client_id = originals["find_order_by_client_id"]
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


def test_core_service_enforces_kill_switch_env_var_even_without_the_argument():
    """A caller that forgets to pass kill_switch_active must not silently
    bypass TRADING_ASSISTANT_KILL_SWITCH -- the service itself must also
    read it, not only the CLI/UI callers."""
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    os.environ["TRADING_ASSISTANT_KILL_SWITCH"] = "1"
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
                    # kill_switch_active deliberately NOT passed
                )
                assert False, "expected the kill switch env var to block this proposal on its own"
            except ProposalExecutionError as exc:
                assert "kill switch" in str(exc).lower()
            assert len(captured) == 0
    finally:
        os.environ.pop("TRADING_ASSISTANT_KILL_SWITCH", None)
        restore()


def test_wide_spread_blocks_a_market_order():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    # bid/ask 10% apart, well over the default 0.5% max_spread_pct.
    captured, restore = _mock_execution_dependencies(
        quote_price=proposal.reference_price, bid=proposal.reference_price * 0.95, ask=proposal.reference_price * 1.05,
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
                assert False, "expected a wide bid/ask spread to block this market order"
            except ProposalExecutionError as exc:
                assert "spread" in str(exc).lower()
            assert len(captured) == 0
            assert store.get_proposal(proposal.proposal_id)["status"] == "blocked"
    finally:
        restore()


def test_limit_order_routes_to_submit_limit_order_not_market():
    packet = _packet()
    policy = _policy()
    from assistant.proposals import TradeProposal, _stable_id
    from risk.execution_gate import TradeIntent

    intent = TradeIntent(ticker="TQQQ", side="sell", shares=10, order_type="limit", limit_price=49.5)
    proposal_id = _stable_id(packet, policy, intent)
    limit_proposal = TradeProposal(
        proposal_id=proposal_id,
        created_at=packet.generated_at,
        expires_at="2026-12-31T00:00:00+00:00",
        status="proposed",
        idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
        policy_version=policy.version,
        intent=intent,
        reference_price=50.0,
        price_timestamp=packet.generated_at,
        reasons=["test limit sell"],
        evidence_status="test",
        expected_impact={"trade_value": 495.0, "position_weight_before_pct": 0, "position_weight_after_pct": 0, "cash_before": 0, "cash_after": 0, "invested_pct_after": 0},
        alternatives=[],
        uncertainties=[],
    ).to_dict()
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(limit_proposal)
            order = execute_approved_paper_proposal(
                proposal_id,
                f"APPROVE {proposal_id}",
                packet.portfolio,
                policy,
                store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert order["order_id"] == "paper-limit-1"
            assert order["limit_price"] == 49.5
            assert len(captured) == 1
            assert captured[0][:3] == ("TQQQ", 10, "sell")
            assert captured[0][4] == 49.5  # limit_price reached submit_limit_order
            assert store.get_proposal(proposal_id)["status"] == "executed"
    finally:
        restore()


def test_ambiguous_submission_failure_reconciles_to_executed_when_broker_actually_accepted():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)

    def failing_submit(ticker, shares, side="buy", *, authorization=None, idempotency_key=None):
        raise TimeoutError("simulated network timeout after the broker may have accepted the order")

    broker.submit_market_order = failing_submit
    broker.find_order_by_client_id = lambda client_order_id: {
        "order_id": "reconciled-1", "ticker": "TQQQ", "shares": 10, "side": "sell", "status": "accepted",
    }
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
            assert order["order_id"] == "reconciled-1"
            record = store.get_proposal(proposal.proposal_id)
            assert record["status"] == "executed"
            assert "reconciled_after_error" in record
    finally:
        restore()


def test_ambiguous_submission_failure_marks_submission_unknown_when_unconfirmable():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)

    def failing_submit(ticker, shares, side="buy", *, authorization=None, idempotency_key=None):
        raise TimeoutError("simulated network timeout, broker outcome unknown")

    def failing_lookup(client_order_id):
        # The lookup ITSELF fails (network/auth/etc.) -- still can't
        # confirm presence or absence. Distinct from returning None,
        # which now means the broker CONFIRMS the order doesn't exist.
        raise ConnectionError("simulated network failure during reconciliation lookup")

    broker.submit_market_order = failing_submit
    broker.find_order_by_client_id = failing_lookup
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
                assert False, "expected an unconfirmable ambiguous failure to raise"
            except ProposalExecutionError as exc:
                assert "submission_unknown" in str(exc)

            record = store.get_proposal(proposal.proposal_id)
            assert record["status"] == "submission_unknown"

            # A regenerated equivalent proposal must be treated as a
            # duplicate-order risk until this is reconciled -- the same
            # ticker/side intent should now show up as "recent".
            recent = store.recent_executed_intents()
            assert any(
                i["ticker"] == proposal.intent.ticker and i["side"] == proposal.intent.side for i in recent
            )
    finally:
        restore()


def test_ambiguous_submission_failure_marks_submission_failed_when_broker_confirms_absent():
    """A confirmed-absent lookup (broker's own 404) after a submission
    error means the order genuinely never went through -- this should
    resolve straight to 'submission_failed', not sit in the more
    conservative 'submission_unknown'."""
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)

    def failing_submit(ticker, shares, side="buy", *, authorization=None, idempotency_key=None):
        raise TimeoutError("simulated network timeout")

    broker.submit_market_order = failing_submit
    broker.find_order_by_client_id = lambda client_order_id: None  # confirmed absent (broker's own 404)
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
                assert False, "expected a confirmed-absent lookup to raise"
            except ProposalExecutionError as exc:
                assert "confirms no such order exists" in str(exc)
            assert store.get_proposal(proposal.proposal_id)["status"] == "submission_failed"
    finally:
        restore()


def test_reconcile_submission_resolves_stuck_proposal_to_executed():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    broker.find_order_by_client_id = lambda client_order_id: {
        "order_id": "reconciled-2",
        "ticker": proposal.intent.ticker,
        "shares": proposal.intent.shares,
        "side": proposal.intent.side,
        "status": "accepted",
    }
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            store.update_proposal_status(proposal.proposal_id, "submission_unknown")

            order = reconcile_submission(proposal.proposal_id, store)
            assert order["order_id"] == "reconciled-2"
            record = store.get_proposal(proposal.proposal_id)
            assert record["status"] == "executed"
            assert "reconciled_at" in record
    finally:
        restore()


def test_reconcile_submission_refuses_a_mismatched_order():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]  # a SELL
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    broker.find_order_by_client_id = lambda client_order_id: {
        "order_id": "wrong-order",
        "ticker": "AAPL",  # does not match the proposal's ticker
        "shares": 999,
        "side": "buy",
        "status": "accepted",
    }
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            proposal_dict = proposal.to_dict()
            store.save_proposal(proposal_dict)
            store.update_proposal_status(proposal.proposal_id, "submission_unknown")

            try:
                reconcile_submission(proposal.proposal_id, store)
                assert False, "expected a mismatched order to be refused"
            except ProposalExecutionError as exc:
                assert "MISMATCHED" in str(exc)
            record = store.get_proposal(proposal.proposal_id)
            assert record["status"] == "submission_unknown"  # not silently trusted/executed
    finally:
        restore()


def test_reconcile_submission_marks_submission_failed_when_broker_confirms_absent():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    broker.find_order_by_client_id = lambda client_order_id: None
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            store.update_proposal_status(proposal.proposal_id, "submitting")

            try:
                reconcile_submission(proposal.proposal_id, store)
                assert False, "expected a confirmed-absent order to raise"
            except ProposalExecutionError as exc:
                assert "never accepted" in str(exc)
            assert store.get_proposal(proposal.proposal_id)["status"] == "submission_failed"
    finally:
        restore()


def test_reconcile_submission_rejects_a_non_reconcilable_status():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    from assistant.execution_service import reconcile_submission

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())  # status is "proposed", not reconcilable
        try:
            reconcile_submission(proposal.proposal_id, store)
            assert False, "expected reconciliation of a 'proposed' proposal to be rejected"
        except ProposalExecutionError as exc:
            assert "not reconcilable" in str(exc)


def test_record_broker_order_failure_after_acceptance_still_marks_executed():
    """The broker DID accept the order (a normal response came back) --
    a local journaling failure must not be reported as a lost/failed
    order; the fact that it executed must be preserved."""
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())

            def failing_record(proposal_id, order):
                raise sqlite3.OperationalError("simulated local disk/db failure")

            original_record = store.record_broker_order
            store.record_broker_order = failing_record
            try:
                order = execute_approved_paper_proposal(
                    proposal.proposal_id,
                    f"APPROVE {proposal.proposal_id}",
                    packet.portfolio,
                    policy,
                    store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert order["order_id"] == "paper-1"
            finally:
                store.record_broker_order = original_record
            record = store.get_proposal(proposal.proposal_id)
            assert record["status"] == "executed"
            assert "local recording failed" in record.get("error", "")
    finally:
        restore()
