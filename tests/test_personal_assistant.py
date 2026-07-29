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
from assistant.allocation_proposals import generate_allocation_buy_proposals
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.execution_service import (
    PolicyOverridableBlockError,
    ProposalExecutionError,
    _shares_from_stored_value,
    execute_approved_paper_proposal,
    validate_proposal_for_execution,
)
from assistant.policy import TradingPolicy, compute_policy_fingerprint, load_policy
from assistant.proposal_status import POLICY_OVERRIDE_AVAILABLE
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


def _packet_with_cash(cash: float) -> DecisionPacket:
    # Like _packet(), but with adjustable cash (and therefore total
    # equity) -- used to produce the SAME violation code with a
    # materially DIFFERENT projected-exposure message (bigger account ->
    # same dollar buy is a smaller percentage), without touching anything
    # else about the scenario.
    snapshot = build_portfolio_snapshot(
        [{"ticker": "TQQQ", "shares": 100, "entry_price": 50.0, "current_price": 50.0}],
        cash=cash,
    )
    return DecisionPacket(
        generated_at="2026-07-26T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-07-25",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
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
    from assistant.order_lifecycle import journal_broker_order_update

    proposal = generate_risk_reduction_proposals(_packet(), _policy())[0].to_dict()
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal)
        store.update_proposal_status(proposal["proposal_id"], "submitting")
        journal_broker_order_update(
            store,
            proposal["proposal_id"],
            {
                "order_id": "paper-order-1",
                "ticker": proposal["intent"]["ticker"],
                "shares": proposal["intent"]["shares"],
                "side": "sell",
                "type": "market",
                "limit_price": None,
                "status": "accepted",
            },
            external_event_id="paper-order-1-accepted",
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


def test_execution_authorization_cannot_be_replayed_after_first_use():
    # GPT review, 2026-07-31, reproduced: ExecutionAuthorization.token is
    # generated (implying single-use, per its own docstring) but
    # verify_execution_authorization() never actually checked it -- the
    # SAME authorization object could be replayed against a broker
    # submission as many times as wanted within its TTL window. Now the
    # FIRST verification consumes the token; a second verification of the
    # exact same (valid, unexpired, correctly-bound) authorization must
    # fail.
    intent = TradeIntent(ticker="AAPL", side="sell", shares=2)
    portfolio = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}], cash=1000.0,
    )
    validation = validate_trade_intent(intent, portfolio, reference_price=100.0)
    assert validation.approved
    authorization = authorize_trade_intent(intent, validation)
    verify_execution_authorization(intent, authorization)  # first use succeeds
    try:
        verify_execution_authorization(intent, authorization)  # replay of the SAME authorization
        assert False, "expected a replayed execution authorization to be rejected"
    except PermissionError as exc:
        assert "already been consumed" in str(exc)


# --- token bound into the HMAC proof (GPT review, 2026-07-31, reproduced):
# _authorization_proof() previously signed only intent+expires_at, so the
# replay-protection token itself was entirely UNSIGNED --
# dataclasses.replace(authorization, token="anything") kept the exact
# same valid proof, letting a copy with a fresh, never-consumed token
# bypass the one-time-use check while keeping a valid intent+expiry
# binding.

def _fresh_authorization():
    intent = TradeIntent(ticker="AAPL", side="sell", shares=2)
    portfolio = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}], cash=1000.0,
    )
    validation = validate_trade_intent(intent, portfolio, reference_price=100.0)
    assert validation.approved
    return intent, authorize_trade_intent(intent, validation)


def test_replacing_only_the_token_invalidates_the_proof():
    intent, authorization = _fresh_authorization()
    replacement = dataclasses.replace(authorization, token="replacement-token-not-bound-by-proof")
    try:
        verify_execution_authorization(intent, replacement)
        assert False, "expected a swapped token to invalidate the proof"
    except PermissionError as exc:
        assert "does not match" in str(exc)


def test_replacing_only_expires_at_invalidates_the_proof():
    intent, authorization = _fresh_authorization()
    far_future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    replacement = dataclasses.replace(authorization, expires_at=far_future)
    try:
        verify_execution_authorization(intent, replacement)
        assert False, "expected a swapped expires_at to invalidate the proof"
    except PermissionError as exc:
        assert "does not match" in str(exc)


def test_replacing_the_intent_invalidates_the_proof():
    intent, authorization = _fresh_authorization()
    different_intent = TradeIntent(ticker="AAPL", side="sell", shares=3)
    try:
        verify_execution_authorization(different_intent, authorization)
        assert False, "expected a different intent to invalidate the proof"
    except PermissionError as exc:
        assert "does not match" in str(exc)


def test_empty_token_is_rejected():
    intent, authorization = _fresh_authorization()
    tokenless = dataclasses.replace(authorization, token="")
    try:
        verify_execution_authorization(intent, tokenless)
        assert False, "expected an empty token to be rejected"
    except PermissionError as exc:
        assert "empty or missing token" in str(exc)


def test_two_independently_issued_authorizations_have_different_tokens_and_proofs():
    intent = TradeIntent(ticker="AAPL", side="sell", shares=2)
    portfolio = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}], cash=1000.0,
    )
    validation = validate_trade_intent(intent, portfolio, reference_price=100.0)
    first = authorize_trade_intent(intent, validation)
    second = authorize_trade_intent(intent, validation)
    assert first.token != second.token
    assert first.proof != second.proof


def test_consuming_one_independently_issued_authorization_does_not_consume_the_other():
    intent = TradeIntent(ticker="AAPL", side="sell", shares=2)
    portfolio = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}], cash=1000.0,
    )
    validation = validate_trade_intent(intent, portfolio, reference_price=100.0)
    first = authorize_trade_intent(intent, validation)
    second = authorize_trade_intent(intent, validation)
    verify_execution_authorization(intent, first)  # consumes `first` only
    verify_execution_authorization(intent, second)  # must still succeed independently
    try:
        verify_execution_authorization(intent, second)  # NOW replaying `second` must fail
        assert False, "expected a replay of the second authorization to be rejected"
    except PermissionError as exc:
        assert "already been consumed" in str(exc)


def test_expired_consumed_tokens_are_pruned_without_re_enabling_the_original():
    from risk.execution_gate import _consumed_authorization_tokens

    intent = TradeIntent(ticker="AAPL", side="sell", shares=2)
    portfolio = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}], cash=1000.0,
    )
    validation = validate_trade_intent(intent, portfolio, reference_price=100.0)
    authorization = authorize_trade_intent(intent, validation, ttl_seconds=1)
    now = datetime.now(timezone.utc)
    verify_execution_authorization(intent, authorization, now=now)  # consumes it while still valid
    assert authorization.token in _consumed_authorization_tokens

    # The original, now-expired authorization must stay rejected (on the
    # expiry check itself, well before any pruning pass) no matter how
    # much time has passed -- never re-enabled just because its entry
    # might later be pruned from the bookkeeping dict.
    much_later = now + timedelta(seconds=10)
    try:
        verify_execution_authorization(intent, authorization, now=much_later)
        assert False, "expected an expired authorization to remain rejected"
    except PermissionError as exc:
        assert "expired" in str(exc).lower()

    # A separate, freshly-issued (still-valid) authorization verified at
    # that same later time triggers the pruning pass as a side effect --
    # confirms the bookkeeping dict actually shrinks rather than growing
    # unboundedly, without needing the original to become executable.
    fresh_validation = validate_trade_intent(intent, portfolio, reference_price=100.0)
    fresh_authorization = authorize_trade_intent(intent, fresh_validation, ttl_seconds=120)
    verify_execution_authorization(intent, fresh_authorization, now=much_later)
    assert authorization.token not in _consumed_authorization_tokens
    assert fresh_authorization.token in _consumed_authorization_tokens


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
    # Regression test (Codex review, 2026-07-27): the fingerprint alone is
    # a PUBLIC hash of the intent's own fields -- any code that imports
    # TradeIntent can compute it, so a hand-built ValidationResult with a
    # correctly-computed fingerprint used to pass authorize_trade_intent()
    # without ever calling validate_trade_intent(). Now the proof is an
    # HMAC keyed by a process-local secret, which can't be reproduced from
    # the intent's public fields alone.
    from risk.execution_gate import intent_fingerprint

    intent = TradeIntent(ticker="AAPL", side="buy", shares=1)
    forged = ValidationResult(True, (), validation_proof=intent_fingerprint(intent))
    try:
        authorize_trade_intent(intent, forged)
        assert False, "expected a hand-constructed ValidationResult to be rejected"
    except ValueError:
        pass


def test_hand_constructed_execution_authorization_cannot_forge_verification():
    # Same forgery attempt one level up: directly constructing an
    # ExecutionAuthorization (instead of going through
    # authorize_trade_intent()) with a guessed/public-hash `proof` must
    # not verify either (Codex review, 2026-07-27).
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


def test_rejected_validation_proof_cannot_be_reused_as_an_approval():
    # Regression test (GPT review, 2026-07-27): the proof used to sign
    # only the intent's identity, not the approved/rejected OUTCOME -- so
    # a REJECTED validation still got a validly-signed proof for its
    # intent, and since ValidationResult was a plain mutable dataclass, a
    # caller could flip `.approved` to True (or build a fresh copy with
    # the same proof) and authorize_trade_intent() would accept it. Now
    # the outcome is part of the signed payload, so a proof signed for
    # approved=False can never verify against approved=True.
    intent = TradeIntent(ticker="AAPL", side="buy", shares=100_000)  # absurdly oversized -> guaranteed rejection
    portfolio = build_portfolio_snapshot([], cash=1_000.0)
    rejected = validate_trade_intent(intent, portfolio, reference_price=100.0)
    assert rejected.approved is False
    assert rejected.validation_proof is not None

    forged_approval = ValidationResult(True, (), validation_proof=rejected.validation_proof)
    try:
        authorize_trade_intent(intent, forged_approval)
        assert False, "expected a rejected validation's proof to be unusable as an approval"
    except ValueError:
        pass


def test_execution_authorization_expiry_cannot_be_extended_by_replacing_the_object():
    # Regression test (GPT review, 2026-07-27): the proof used to sign
    # only intent identity, not `expires_at` -- so a valid, correctly-
    # signed authorization's proof could be copied onto a new
    # ExecutionAuthorization object with a LATER expires_at (e.g. via
    # dataclasses.replace()) and still verify, defeating "short-lived"
    # entirely. Now expires_at is part of the signed payload.
    intent = TradeIntent(ticker="AAPL", side="sell", shares=2)
    portfolio = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}], cash=1000.0,
    )
    validation = validate_trade_intent(intent, portfolio, reference_price=100.0)
    authorization = authorize_trade_intent(intent, validation, ttl_seconds=1)
    far_future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    extended = dataclasses.replace(authorization, expires_at=far_future)
    try:
        verify_execution_authorization(intent, extended)
        assert False, "expected an authorization with a tampered expires_at to fail verification"
    except PermissionError:
        pass


def test_broker_rejects_direct_order_without_gate_authorization():
    broker.PAPER_TRADING = True
    try:
        broker.submit_market_order("AAPL", 1, side="buy", idempotency_key="test-key")
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
        "assert_account_and_asset_ready": broker.assert_account_and_asset_ready,
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
    broker.assert_account_and_asset_ready = lambda ticker: {
        "account": {"paper": True, "status": "ACTIVE"},
        "asset": {"ticker": ticker, "status": "active", "tradable": True},
    }
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
        broker.assert_account_and_asset_ready = originals["assert_account_and_asset_ready"]
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
                "approve",
                packet.portfolio,
                policy,
                store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert order["order_id"] == "paper-1"
            assert store.get_proposal(proposal.proposal_id)["status"] == "broker_accepted"
            assert len(captured) == 1
    finally:
        restore()


def test_unsupported_order_type_is_refused_not_downgraded_to_a_market_order():
    # Independent review, 2026-07-29: the submit dispatch used to read
    # "limit, else market", so ANY other order type would have been
    # submitted as an unbounded-price MARKET order. risk/execution_gate.py
    # still approves order_type="stop" (it has no view of policy), and
    # policy.allowed_order_types is only enforced one layer up -- so the
    # dispatch itself must fail closed rather than silently downgrade.
    # A policy permitting "stop" is constructed directly here (policy.validate()
    # would reject it) precisely to reach the dispatch.
    packet = _packet()
    permissive_policy = dataclasses.replace(
        _policy(), allowed_order_types=("market", "limit", "stop")
    )
    proposal = generate_risk_reduction_proposals(packet, permissive_policy)[0]
    stored = proposal.to_dict()
    stored["intent"] = {**stored["intent"], "order_type": "stop", "limit_price": 90.0}
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(stored)
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", packet.portfolio,
                    permissive_policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected an unsupported order type to be refused"
            except ProposalExecutionError as exc:
                assert "order_type" in str(exc)
            # The critical property: no order reached the broker at all.
            assert captured == []
            refreshed = store.get_proposal(proposal.proposal_id)
            assert refreshed["status"] == "blocked"
    finally:
        restore()


def test_approval_rejects_a_policy_with_the_same_version_but_different_content():
    # Regression test (GPT review, 2026-07-28): approval used to compare
    # only the `policy_version` string. Two policy files (e.g. a
    # hand-edited personal one copied from the default) can share the
    # same version yet have materially different risk limits -- this
    # must be rejected via the fingerprint even though the version string
    # matches.
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    edited_policy = dataclasses.replace(policy, max_position_pct=policy.max_position_pct / 2)
    assert edited_policy.version == policy.version  # same version string...
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", packet.portfolio,
                    edited_policy, store, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected a fingerprint mismatch to block approval despite matching version"
            except ProposalExecutionError as exc:
                assert "fingerprint" in str(exc).lower()
            assert len(captured) == 0
    finally:
        restore()


def test_approval_rejects_when_allow_new_positions_changed():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    edited_policy = dataclasses.replace(policy, allow_new_positions=not policy.allow_new_positions)
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", packet.portfolio,
                    edited_policy, store, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected a changed allow_new_positions to invalidate the proposal"
            except ProposalExecutionError as exc:
                assert "fingerprint" in str(exc).lower()
            assert len(captured) == 0
    finally:
        restore()


def test_approval_accepts_when_only_notes_changed():
    # `notes` is free-text/explanatory, not behavior-affecting -- the
    # fingerprint deliberately ignores it, so a notes-only edit should
    # NOT invalidate an outstanding proposal.
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    edited_policy = dataclasses.replace(policy, notes="a completely different note")
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            order = execute_approved_paper_proposal(
                proposal.proposal_id, "approve", packet.portfolio,
                edited_policy, store, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert order["order_id"] == "paper-1"
            assert len(captured) == 1
    finally:
        restore()


def test_approval_rejects_a_proposal_missing_policy_fingerprint():
    # Regression test (GPT review, 2026-07-28): a proposal predating
    # fingerprint binding (e.g. an old row already in the SQLite store)
    # has no `policy_fingerprint` key at all -- this must fail closed,
    # not be silently grandfathered in.
    packet = _packet()
    policy = _policy()
    proposal_dict = generate_risk_reduction_proposals(packet, policy)[0].to_dict()
    del proposal_dict["policy_fingerprint"]
    captured, restore = _mock_execution_dependencies(quote_price=proposal_dict["reference_price"])
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal_dict)
            try:
                execute_approved_paper_proposal(
                    proposal_dict["proposal_id"], "approve", packet.portfolio,
                    policy, store, now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected a proposal missing policy_fingerprint to fail closed"
            except ProposalExecutionError as exc:
                assert "fingerprint" in str(exc).lower()
            assert len(captured) == 0
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
                    "approve",
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
                    "approve",
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


def test_earnings_only_block_raises_overridable_error_and_leaves_proposal_re_claimable():
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
                    proposal.proposal_id, "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected an overridable earnings-blackout block"
            except PolicyOverridableBlockError as exc:
                assert any("earnings" in v.lower() for v in exc.overridable_violations)
            assert len(captured) == 0
            assert store.get_proposal(proposal.proposal_id)["status"] == POLICY_OVERRIDE_AVAILABLE
    finally:
        restore()


def test_override_flag_proceeds_past_an_earnings_only_block_and_records_it():
    # GPT review, 2026-07-30: a DIRECT override_policy_violations=True call
    # on a proposal that has never been shown to a human before must not
    # authorize immediately -- it must first become the review/
    # presentation step (storing a reviewed-override record and raising
    # PolicyOverridableBlockError), exactly like an ordinary discovery
    # call would. Only a SECOND call, once the human has (at least
    # notionally) seen that exact violation set, actually proceeds.
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
                    proposal.proposal_id, "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                    override_policy_violations=True,
                )
                assert False, "expected the first override attempt to require a review step first"
            except PolicyOverridableBlockError:
                pass
            assert len(captured) == 0

            # Second call: same portfolio/quote, so the freshly revalidated
            # violations exactly match what was just reviewed -- proceeds.
            order = execute_approved_paper_proposal(
                proposal.proposal_id, "approve", packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
                override_policy_violations=True,
            )
            assert order["status"] == "accepted"
            assert len(captured) == 1
            stored = store.get_proposal(proposal.proposal_id)
            assert stored["status"] == "broker_accepted"
            assert "policy_override" in stored
            assert any("earnings" in v.lower() for v in stored["policy_override"]["overridden_violations"])
    finally:
        restore()


def test_override_flag_does_not_bypass_a_non_overridable_violation_alongside_it():
    # Stale quote (non-overridable) + earnings blackout (overridable) together
    # -- override_policy_violations=True must still block on the stale quote.
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    stale_timestamp = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)
    captured, restore = _mock_execution_dependencies(
        quote_price=proposal.reference_price, quote_timestamp=stale_timestamp, earnings_available=True,
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                    override_policy_violations=True,
                )
                assert False, "expected the stale-quote violation to still block despite override=True"
            except PolicyOverridableBlockError:
                assert False, "a non-overridable violation must raise plain ProposalExecutionError, not the overridable variant"
            except ProposalExecutionError as exc:
                assert "staleness" in str(exc).lower()
            assert len(captured) == 0
            assert store.get_proposal(proposal.proposal_id)["status"] == "blocked"
    finally:
        restore()


# --- Reviewed-override binding (GPT review, 2026-07-30): override_
# policy_violations=True must only authorize against violations a human
# has ALREADY been shown once via a prior PolicyOverridableBlockError --
# never blanket permission to accept whatever override-eligible
# conditions happen to exist at the later execution instant.

def _tiny_cap_policy() -> TradingPolicy:
    # max_position_pct=0.001 (0.1%) guarantees a deterministic, SINGLE
    # override-eligible MAX_POSITION_PCT violation for any meaningful buy
    # -- allow_new_positions=True since these proposals open a first
    # position in a ticker ("AAA") not already held.
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=0.001, max_total_exposure_pct=1.0, max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=50_000.0,
        allow_new_positions=True,
    )


def _position_cap_buy_proposal(packet, policy, dollar_amount=2000.0, price=50.0):
    proposals = generate_allocation_buy_proposals(
        packet, policy, weights_pct={"AAA": 100.0}, prices={"AAA": price}, dollar_amount=dollar_amount,
    )
    assert len(proposals) == 1
    return proposals[0]


def test_direct_override_from_proposed_requires_a_review_step_first():
    packet = _packet()
    policy = _tiny_cap_policy()
    proposal = _position_cap_buy_proposal(packet, policy)
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                    override_policy_violations=True,
                )
                assert False, "expected a direct override from 'proposed' to require review first"
            except PolicyOverridableBlockError as exc:
                assert exc.conditions_changed is False  # nothing to compare against yet, not a "change"
            assert len(captured) == 0  # never actually submitted
            record = store.get_proposal(proposal.proposal_id)
            assert record["status"] == POLICY_OVERRIDE_AVAILABLE
            reviewed = record["reviewed_override"]
            assert reviewed["violation_codes"] == ["max_position_pct"]
            assert reviewed["review_digest"]
            assert reviewed["presented_at"]
    finally:
        restore()


def test_unchanged_retry_succeeds_with_exactly_one_broker_submission():
    packet = _packet()
    policy = _tiny_cap_policy()
    proposal = _position_cap_buy_proposal(packet, policy)
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                    override_policy_violations=True,
                )
                assert False, "expected the first attempt to establish the review"
            except PolicyOverridableBlockError:
                pass

            # Same portfolio, quote, intent, and (therefore) violations.
            order = execute_approved_paper_proposal(
                proposal.proposal_id, "approve", packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
                override_policy_violations=True,
            )
            assert order["status"] == "accepted"
            assert len(captured) == 1
    finally:
        restore()


def test_new_violation_appearing_before_retry_requires_fresh_review():
    packet = _packet()
    policy = _tiny_cap_policy()
    proposal = _position_cap_buy_proposal(packet, policy)
    captured, restore = _mock_execution_dependencies(quote_price=50.0, earnings_available=False)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            # First attempt: position-cap violation only (no earnings
            # data resolved, so no blackout check fires).
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                    override_policy_violations=True,
                )
                assert False, "expected the first attempt to establish the review"
            except PolicyOverridableBlockError:
                pass
            first_reviewed = store.get_proposal(proposal.proposal_id)["reviewed_override"]
            assert first_reviewed["violation_codes"] == ["max_position_pct"]

            # Second attempt: an earnings-blackout violation now ALSO
            # applies (earnings_days_away=1 is within the default 2-day
            # window) -- an override attempt must NOT submit, since the
            # human never reviewed this new, larger violation set.
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
                    override_policy_violations=True,
                    earnings_days_away=1,
                )
                assert False, "expected a newly-appeared violation to require fresh review"
            except PolicyOverridableBlockError as exc:
                assert exc.conditions_changed is True
                assert any("earnings" in v.lower() for v in exc.overridable_violations)
            assert len(captured) == 0  # never submitted

            second_reviewed = store.get_proposal(proposal.proposal_id)["reviewed_override"]
            assert sorted(second_reviewed["violation_codes"]) == ["earnings_blackout", "max_position_pct"]
            assert second_reviewed["review_digest"] != first_reviewed["review_digest"]
            assert store.get_proposal(proposal.proposal_id)["status"] == POLICY_OVERRIDE_AVAILABLE
    finally:
        restore()


def test_same_code_but_materially_different_severity_requires_fresh_review():
    policy = _tiny_cap_policy()
    small_account_packet = _packet_with_cash(5_000.0)
    proposal = _position_cap_buy_proposal(small_account_packet, policy)
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", small_account_packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                    override_policy_violations=True,
                )
                assert False, "expected the first attempt to establish the review"
            except PolicyOverridableBlockError:
                pass
            first_reviewed = store.get_proposal(proposal.proposal_id)["reviewed_override"]
            assert first_reviewed["violation_codes"] == ["max_position_pct"]

            # A much bigger account (materially different existing
            # equity) makes the SAME $2,000 buy a much smaller percentage
            # of the account -- same violation CODE (max_position_pct,
            # still over the 0.1% cap), but a materially different
            # projected-exposure MESSAGE.
            big_account_packet = _packet_with_cash(500_000.0)
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", big_account_packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
                    override_policy_violations=True,
                )
                assert False, "expected a materially different exposure message to require fresh review"
            except PolicyOverridableBlockError as exc:
                assert exc.conditions_changed is True
            assert len(captured) == 0

            second_reviewed = store.get_proposal(proposal.proposal_id)["reviewed_override"]
            assert second_reviewed["violation_codes"] == ["max_position_pct"]  # same code
            assert second_reviewed["violations"] != first_reviewed["violations"]  # different message
            assert second_reviewed["review_digest"] != first_reviewed["review_digest"]
    finally:
        restore()


def test_kill_switch_still_hard_blocks_regardless_of_override_flag():
    # Non-overridable regression guard: the reviewed-override binding
    # must never affect the "at least one violation isn't override-
    # eligible" branch, which is completely untouched by this feature.
    packet = _packet()
    policy = _tiny_cap_policy()
    proposal = _position_cap_buy_proposal(packet, policy)
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                    override_policy_violations=True,
                    kill_switch_active=True,
                )
                assert False, "expected the kill switch to hard-block regardless of override_policy_violations"
            except PolicyOverridableBlockError:
                assert False, "the kill switch must never be treated as override-eligible"
            except ProposalExecutionError as exc:
                assert "kill switch" in str(exc).lower()
            assert len(captured) == 0
            assert store.get_proposal(proposal.proposal_id)["status"] == "blocked"
    finally:
        restore()


def test_audit_record_matches_the_reviewed_set_after_a_successful_retry():
    packet = _packet()
    policy = _tiny_cap_policy()
    proposal = _position_cap_buy_proposal(packet, policy)
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                    override_policy_violations=True,
                )
                assert False, "expected the first attempt to establish the review"
            except PolicyOverridableBlockError:
                pass
            reviewed = store.get_proposal(proposal.proposal_id)["reviewed_override"]

            execute_approved_paper_proposal(
                proposal.proposal_id, "approve", packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
                override_policy_violations=True,
            )
            stored = store.get_proposal(proposal.proposal_id)
            assert stored["status"] == "broker_accepted"
            assert sorted(stored["policy_override"]["overridden_violations"]) == sorted(reviewed["violations"])
    finally:
        restore()


def test_confirmation_phrase_is_case_insensitive_and_whitespace_tolerant():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            order = execute_approved_paper_proposal(
                proposal.proposal_id, "  Approve  ", packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert order["status"] == "accepted"
            assert len(captured) == 1
    finally:
        restore()


def test_confirmation_phrase_rejects_the_old_approve_plus_id_format():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, f"APPROVE {proposal.proposal_id}", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "the old 'APPROVE <id>' phrase should no longer be accepted"
            except ProposalExecutionError as exc:
                assert "approve" in str(exc).lower()
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
                    "approve",
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
        policy_fingerprint=compute_policy_fingerprint(policy),
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
                "approve",
                packet.portfolio,
                policy,
                store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert store.get_proposal(proposal.proposal_id)["status"] == "broker_accepted"

            # Re-invoke approval for the SAME (now executed) proposal_id,
            # far past its expires_at -- must not flip status back to
            # "expired" and must not submit a second order.
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id,
                    "approve",
                    packet.portfolio,
                    policy,
                    store,
                    now_et=datetime(2026, 12, 31, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected re-approval of an executed proposal to be rejected"
            except ProposalExecutionError:
                pass
            assert store.get_proposal(proposal.proposal_id)["status"] == "broker_accepted"
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
                    "approve",
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
                "approve",
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
                    "approve",
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
                    "approve",
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
                    "approve",
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


def _buy_proposal_with_a_pending_order_on_another_ticker(side: str):
    """Shared setup for the pending-buy-value fail-closed tests: TQQQ
    already held (so a buy on it isn't blocked by allow_new_positions),
    plus one pending market BUY order on NVDA with no notional/limit_price
    -- forces _pending_buy_value_by_ticker() down the live-quote fallback
    path for NVDA specifically."""
    from assistant.proposals import TradeProposal, _stable_id
    from risk.execution_gate import TradeIntent

    snapshot = build_portfolio_snapshot(
        [{"ticker": "TQQQ", "shares": 100, "entry_price": 50.0, "current_price": 50.0}],
        cash=10_000.0,
        open_orders=[
            {
                "order_id": "o1", "ticker": "NVDA", "shares": 10, "side": "buy", "type": "market",
                "status": "new", "submitted_at": None, "limit_price": None, "notional": None,
            },
        ],
    )
    packet = DecisionPacket(
        generated_at="2026-07-26T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-07-25",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )
    policy = dataclasses.replace(_policy(), allow_new_positions=True)

    intent = TradeIntent(ticker="TQQQ", side=side, shares=1)
    proposal_id = _stable_id(packet, policy, intent)
    proposal = TradeProposal(
        proposal_id=proposal_id,
        created_at=packet.generated_at,
        expires_at="2026-12-31T00:00:00+00:00",
        status="proposed",
        idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
        policy_version=policy.version,
        policy_fingerprint=compute_policy_fingerprint(policy),
        intent=intent,
        reference_price=50.0,
        price_timestamp=packet.generated_at,
        reasons=["test"],
        evidence_status="test",
        expected_impact={
            "trade_value": 50.0, "position_weight_before_pct": 0, "position_weight_after_pct": 0,
            "cash_before": 0, "cash_after": 0, "invested_pct_after": 0,
        },
        alternatives=[],
        uncertainties=[],
    ).to_dict()
    return packet, policy, proposal_id, proposal


def test_pending_buy_value_lookup_failure_blocks_a_buy_approval():
    # Regression test (GPT review, 2026-07-27): an earlier version
    # silently dropped a pending order's value to zero when its price
    # couldn't be determined (e.g. a plain market order needing a live
    # quote that fails), undercounting exposure exactly like the bug this
    # mechanism exists to fix. A buy must fail closed instead.
    packet, policy, proposal_id, proposal = _buy_proposal_with_a_pending_order_on_another_ticker("buy")
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    original_get_latest_quote = broker.get_latest_quote

    def flaky_quote(ticker):
        if ticker == "NVDA":
            raise ConnectionError("simulated quote outage")
        return original_get_latest_quote(ticker)

    broker.get_latest_quote = flaky_quote
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal)
            try:
                execute_approved_paper_proposal(
                    proposal_id, "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected the pending-order quote failure to block this buy"
            except ProposalExecutionError as exc:
                assert "pending buy" in str(exc).lower()
            assert len(captured) == 0
    finally:
        restore()


def test_pending_buy_value_lookup_failure_does_not_block_a_sell_approval():
    # A risk-reducing sell never consults pending_buy_value_by_ticker, so
    # an unrelated pending buy's quote failure shouldn't block it.
    packet, policy, proposal_id, proposal = _buy_proposal_with_a_pending_order_on_another_ticker("sell")
    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    original_get_latest_quote = broker.get_latest_quote

    def flaky_quote(ticker):
        if ticker == "NVDA":
            raise ConnectionError("simulated quote outage")
        return original_get_latest_quote(ticker)

    broker.get_latest_quote = flaky_quote
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal)
            order = execute_approved_paper_proposal(
                proposal_id, "approve", packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert order["order_id"] == "paper-1"
            assert len(captured) == 1
    finally:
        restore()


def test_pending_buy_value_by_ticker_uses_notional_without_requiring_shares():
    # Regression test (GPT review, 2026-07-27): Alpaca lets a buy order be
    # submitted as a dollar amount instead of a share count (shares=None,
    # notional=<dollar value>). The function used to check `shares` before
    # `notional`, so a valid notional value was never read and the order
    # was skipped entirely. ticker/notional are now checked first; a quote
    # lookup should never even be attempted when notional is available.
    from assistant.execution_service import _pending_buy_value_by_ticker

    class _FakeBroker:
        @staticmethod
        def get_latest_quote(ticker):
            raise AssertionError(f"quote lookup should not be called when notional is available (ticker={ticker})")

    open_orders = [{"side": "buy", "ticker": "NVDA", "shares": None, "notional": 4000.0}]
    assert _pending_buy_value_by_ticker(open_orders, _FakeBroker()) == {"NVDA": 4000.0}


def test_pending_buy_value_by_ticker_share_based_quote_fallback_still_works():
    # Existing share-based / quote-fallback behavior is unchanged by the
    # notional fix above.
    from assistant.execution_service import _pending_buy_value_by_ticker

    class _FakeBroker:
        @staticmethod
        def get_latest_quote(ticker):
            return {"ticker": ticker, "price": 25.0}

    open_orders = [{"side": "buy", "ticker": "AMD", "shares": 10, "notional": None, "limit_price": None}]
    assert _pending_buy_value_by_ticker(open_orders, _FakeBroker()) == {"AMD": 250.0}


def test_pending_buy_value_by_ticker_limit_price_still_works_without_notional():
    # Existing limit-order behavior is unchanged: shares * limit_price,
    # no quote lookup needed.
    from assistant.execution_service import _pending_buy_value_by_ticker

    class _FakeBroker:
        @staticmethod
        def get_latest_quote(ticker):
            raise AssertionError("quote lookup should not be called when limit_price is available")

    open_orders = [{"side": "buy", "ticker": "AMD", "shares": 10, "notional": None, "limit_price": 30.0}]
    assert _pending_buy_value_by_ticker(open_orders, _FakeBroker()) == {"AMD": 300.0}


def test_pending_buy_value_by_ticker_still_ignores_sell_orders():
    # Existing sell-side behavior is unchanged: a sell order (notional or
    # otherwise) never contributes to pending BUY exposure.
    from assistant.execution_service import _pending_buy_value_by_ticker

    class _FakeBroker:
        @staticmethod
        def get_latest_quote(ticker):
            raise AssertionError("should not be called for a sell order")

    open_orders = [{"side": "sell", "ticker": "AMD", "shares": None, "notional": 4000.0}]
    assert _pending_buy_value_by_ticker(open_orders, _FakeBroker()) == {}


def test_notional_only_pending_order_blocks_a_duplicate_proposal_on_the_same_ticker_and_side():
    # Regression test (GPT review, 2026-07-27): a notional-only open order
    # (shares=None) used to be excluded from recent_intents because the
    # loop required `shares` truthy -- duplicate identity only depends on
    # ticker+side, never shares, so this should still block a new proposal
    # for the same ticker/side.
    from assistant.proposals import TradeProposal, _stable_id
    from risk.execution_gate import TradeIntent

    snapshot = build_portfolio_snapshot(
        [{"ticker": "TQQQ", "shares": 100, "entry_price": 50.0, "current_price": 50.0}],
        cash=5_000.0,
        open_orders=[
            {
                "order_id": "o1", "ticker": "TQQQ", "side": "sell", "shares": None, "notional": 500.0,
                "type": "market", "status": "new", "submitted_at": None, "limit_price": None,
            },
        ],
    )
    packet = DecisionPacket(
        generated_at="2026-07-26T12:00:00+00:00",
        portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(
            benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
            trailing_volatility_pct=1.0, as_of="2026-07-25",
        ),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )
    policy = _policy()

    intent = TradeIntent(ticker="TQQQ", side="sell", shares=10)
    proposal_id = _stable_id(packet, policy, intent)
    proposal = TradeProposal(
        proposal_id=proposal_id,
        created_at=packet.generated_at,
        expires_at="2026-12-31T00:00:00+00:00",
        status="proposed",
        idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
        policy_version=policy.version,
        policy_fingerprint=compute_policy_fingerprint(policy),
        intent=intent,
        reference_price=50.0,
        price_timestamp=packet.generated_at,
        reasons=["test"],
        evidence_status="test",
        expected_impact={
            "trade_value": 500.0, "position_weight_before_pct": 0, "position_weight_after_pct": 0,
            "cash_before": 0, "cash_after": 0, "invested_pct_after": 0,
        },
        alternatives=[],
        uncertainties=[],
    ).to_dict()

    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal)
            try:
                execute_approved_paper_proposal(
                    proposal_id, "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected the notional-only pending order to be detected as a duplicate"
            except ProposalExecutionError as exc:
                assert "duplicate" in str(exc).lower()
            assert len(captured) == 0
            assert store.get_proposal(proposal_id)["status"] == "blocked"
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
        policy_fingerprint=compute_policy_fingerprint(policy),
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
                "approve",
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
            assert store.get_proposal(proposal_id)["status"] == "broker_accepted"
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
        "order_id": "reconciled-1", "ticker": proposal.intent.ticker, "shares": proposal.intent.shares,
        "side": proposal.intent.side, "type": proposal.intent.order_type,
        "limit_price": proposal.intent.limit_price, "status": "accepted",
    }
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            order = execute_approved_paper_proposal(
                proposal.proposal_id,
                "approve",
                packet.portfolio,
                policy,
                store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert order["order_id"] == "reconciled-1"
            record = store.get_proposal(proposal.proposal_id)
            assert record["status"] == "broker_accepted"
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
                    "approve",
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
                    "approve",
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
        "type": proposal.intent.order_type,
        "limit_price": proposal.intent.limit_price,
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
            assert record["status"] == "broker_accepted"
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


def _reconcile_mismatch_case(order_overrides: dict, expected_mismatch_substring: str):
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]  # a market SELL
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    order = {
        "order_id": "candidate-order",
        "ticker": proposal.intent.ticker,
        "shares": proposal.intent.shares,
        "side": proposal.intent.side,
        "type": proposal.intent.order_type,
        "limit_price": proposal.intent.limit_price,
        "status": "accepted",
    }
    order.update(order_overrides)
    broker.find_order_by_client_id = lambda client_order_id: order
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            store.update_proposal_status(proposal.proposal_id, "submission_unknown")
            try:
                reconcile_submission(proposal.proposal_id, store)
                assert False, f"expected a mismatch on {order_overrides!r} to be refused"
            except ProposalExecutionError as exc:
                assert "MISMATCHED" in str(exc)
            record = store.get_proposal(proposal.proposal_id)
            assert record["status"] == "submission_unknown"
            assert expected_mismatch_substring in record["error"]
    finally:
        restore()


def test_reconcile_submission_refuses_mismatched_quantity():
    _reconcile_mismatch_case({"shares": 1}, "shares:")


def test_reconcile_submission_refuses_mismatched_order_type():
    _reconcile_mismatch_case({"type": "limit", "limit_price": 50.0}, "order type:")


def test_reconcile_submission_refuses_mismatched_side():
    _reconcile_mismatch_case({"side": "buy"}, "side:")


def test_reconcile_submission_refuses_missing_quantity():
    _reconcile_mismatch_case({"shares": None}, "shares:")


def test_reconcile_submission_refuses_missing_order_type():
    _reconcile_mismatch_case({"type": None}, "order type:")


def test_reconcile_submission_accepts_numerically_equivalent_share_counts():
    # 10 and 10.0 must be treated as equal -- only the actual quantity
    # matters, not whether the broker returned an int or a float.
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    broker.find_order_by_client_id = lambda client_order_id: {
        "order_id": "candidate-order",
        "ticker": proposal.intent.ticker,
        "shares": float(proposal.intent.shares),  # equivalent, not identical, representation
        "side": proposal.intent.side,
        "type": proposal.intent.order_type,
        "limit_price": proposal.intent.limit_price,
        "status": "accepted",
    }
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            store.update_proposal_status(proposal.proposal_id, "submission_unknown")
            order = reconcile_submission(proposal.proposal_id, store)
            assert order["order_id"] == "candidate-order"
            assert store.get_proposal(proposal.proposal_id)["status"] == "broker_accepted"
    finally:
        restore()


def test_reconcile_submission_refuses_mismatched_limit_price():
    packet = _packet()
    policy = _policy()
    from assistant.proposals import TradeProposal, _stable_id
    from assistant.execution_service import reconcile_submission
    from risk.execution_gate import TradeIntent

    intent = TradeIntent(ticker="TQQQ", side="sell", shares=10, order_type="limit", limit_price=49.5)
    proposal_id = _stable_id(packet, policy, intent)
    limit_proposal = TradeProposal(
        proposal_id=proposal_id, created_at=packet.generated_at, expires_at="2026-12-31T00:00:00+00:00",
        status="proposed", idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
        policy_version=policy.version, policy_fingerprint=compute_policy_fingerprint(policy),
        intent=intent, reference_price=50.0, price_timestamp=packet.generated_at,
        reasons=["test limit sell"], evidence_status="test",
        expected_impact={"trade_value": 495.0, "position_weight_before_pct": 0, "position_weight_after_pct": 0, "cash_before": 0, "cash_after": 0, "invested_pct_after": 0},
        alternatives=[], uncertainties=[],
    ).to_dict()
    _, restore = _mock_execution_dependencies(quote_price=50.0)
    broker.find_order_by_client_id = lambda client_order_id: {
        "order_id": "candidate-order", "ticker": "TQQQ", "shares": 10, "side": "sell",
        "type": "limit", "limit_price": 45.0,  # does NOT match the proposal's 49.5
        "status": "accepted",
    }
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(limit_proposal)
            store.update_proposal_status(proposal_id, "submission_unknown")
            try:
                reconcile_submission(proposal_id, store)
                assert False, "expected a mismatched limit price to be refused"
            except ProposalExecutionError as exc:
                assert "MISMATCHED" in str(exc)
            record = store.get_proposal(proposal_id)
            assert record["status"] == "submission_unknown"
            assert "limit_price:" in record["error"]
    finally:
        restore()


def test_reconcile_submission_accepts_a_correctly_matching_limit_order():
    packet = _packet()
    policy = _policy()
    from assistant.proposals import TradeProposal, _stable_id
    from assistant.execution_service import reconcile_submission
    from risk.execution_gate import TradeIntent

    intent = TradeIntent(ticker="TQQQ", side="sell", shares=10, order_type="limit", limit_price=49.5)
    proposal_id = _stable_id(packet, policy, intent)
    limit_proposal = TradeProposal(
        proposal_id=proposal_id, created_at=packet.generated_at, expires_at="2026-12-31T00:00:00+00:00",
        status="proposed", idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
        policy_version=policy.version, policy_fingerprint=compute_policy_fingerprint(policy),
        intent=intent, reference_price=50.0, price_timestamp=packet.generated_at,
        reasons=["test limit sell"], evidence_status="test",
        expected_impact={"trade_value": 495.0, "position_weight_before_pct": 0, "position_weight_after_pct": 0, "cash_before": 0, "cash_after": 0, "invested_pct_after": 0},
        alternatives=[], uncertainties=[],
    ).to_dict()
    _, restore = _mock_execution_dependencies(quote_price=50.0)
    broker.find_order_by_client_id = lambda client_order_id: {
        "order_id": "candidate-order", "ticker": "TQQQ", "shares": 10, "side": "sell",
        "type": "limit", "limit_price": 49.5,
        "status": "accepted",
    }
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(limit_proposal)
            store.update_proposal_status(proposal_id, "submission_unknown")
            order = reconcile_submission(proposal_id, store)
            assert order["order_id"] == "candidate-order"
            assert store.get_proposal(proposal_id)["status"] == "broker_accepted"
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


def test_reconcile_submission_recovers_from_a_malformed_stored_intent():
    # GPT review, 2026-07-28: _intent_from_dict() raising (a corrupted
    # stored intent) used to leave the proposal stranded in "reconciling"
    # -- there was no catch-all around the post-claim logic.
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            proposal_dict = proposal.to_dict()
            store.save_proposal(proposal_dict)
            store.update_proposal_status(proposal.proposal_id, "submitting")
            # Corrupt the stored intent so _intent_from_dict() raises (missing "shares").
            corrupted_intent = dict(proposal_dict["intent"])
            del corrupted_intent["shares"]
            store.update_proposal_status(proposal.proposal_id, "submitting", intent=corrupted_intent)

            try:
                reconcile_submission(proposal.proposal_id, store)
                assert False, "expected the malformed intent to raise"
            except ProposalExecutionError as exc:
                assert "unexpectedly" in str(exc)
            record = store.get_proposal(proposal.proposal_id)
            assert record["status"] == "submission_unknown"  # retryable, not stranded
            assert "Unexpected error" in record["error"]
    finally:
        restore()


# --- _shares_from_stored_value() -- GPT review, 2026-07-29: a bare
# int(raw["shares"]) used to silently truncate a corrupted/hand-edited
# fractional stored value (e.g. 1.9 -> 1) instead of failing closed.

def test_shares_from_stored_value_accepts_a_plain_int():
    assert _shares_from_stored_value(10) == 10


def test_shares_from_stored_value_accepts_a_whole_valued_float():
    assert _shares_from_stored_value(10.0) == 10


def test_shares_from_stored_value_rejects_a_fractional_float():
    try:
        _shares_from_stored_value(1.9)
        assert False, "expected a fractional stored shares value to raise"
    except ValueError as exc:
        assert "fractional" in str(exc)


def test_shares_from_stored_value_rejects_nan():
    try:
        _shares_from_stored_value(float("nan"))
        assert False, "expected a NaN stored shares value to raise"
    except ValueError as exc:
        assert "not finite" in str(exc)


def test_shares_from_stored_value_rejects_infinity():
    try:
        _shares_from_stored_value(float("inf"))
        assert False, "expected an infinite stored shares value to raise"
    except ValueError as exc:
        assert "not finite" in str(exc)


def test_shares_from_stored_value_rejects_bool():
    try:
        _shares_from_stored_value(True)
        assert False, "expected a bool stored shares value to raise"
    except ValueError as exc:
        assert "bool" in str(exc)


def test_shares_from_stored_value_rejects_a_non_numeric_string():
    try:
        _shares_from_stored_value("10")
        assert False, "expected a string stored shares value to raise"
    except ValueError as exc:
        assert "not numeric" in str(exc)


def test_validate_proposal_for_execution_fails_closed_on_fractional_stored_shares():
    # Integration-level check that a corrupted stored proposal (shares:
    # 1.9) is rejected as a malformed intent by validate_proposal_for_
    # execution(), not silently coerced to 1 share and validated as if
    # nothing were wrong.
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            proposal_dict = proposal.to_dict()
            corrupted_intent = dict(proposal_dict["intent"])
            corrupted_intent["shares"] = 1.9
            proposal_dict["intent"] = corrupted_intent
            store.save_proposal(proposal_dict)
            outcome = validate_proposal_for_execution(
                proposal.proposal_id, packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert not outcome.approved
            assert "malformed stored intent" in outcome.error.lower()
            assert "fractional" in outcome.error.lower()
    finally:
        restore()


def test_reconcile_submission_recovers_when_broker_lookup_itself_raises():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    def failing_lookup(client_order_id):
        raise ConnectionError("simulated network failure")

    broker.find_order_by_client_id = failing_lookup
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            store.update_proposal_status(proposal.proposal_id, "submitting")
            try:
                reconcile_submission(proposal.proposal_id, store)
                assert False, "expected the unconfirmed lookup to raise"
            except ProposalExecutionError as exc:
                assert "could not confirm" in str(exc).lower()
            assert store.get_proposal(proposal.proposal_id)["status"] == "submission_unknown"
    finally:
        restore()


def test_reconcile_submission_recovers_when_atomic_journal_fails():
    # GPT review, 2026-07-28: unlike execute_approved_paper_proposal()'s
    # own local-journal failure handling preserves a fresh broker response,
    # while reconciliation's
    # equivalent failure must leave the proposal RETRYABLE
    # (submission_unknown) rather than assume success without ever having
    # journaled the order.
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    broker.find_order_by_client_id = lambda client_order_id: {
        "order_id": "candidate-order", "ticker": proposal.intent.ticker, "shares": proposal.intent.shares,
        "side": proposal.intent.side, "type": proposal.intent.order_type,
        "limit_price": proposal.intent.limit_price, "status": "accepted",
    }
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            store.update_proposal_status(proposal.proposal_id, "submitting")

            original_record = store.project_broker_order_event

            def failing_record(*args, **kwargs):
                raise sqlite3.OperationalError("simulated disk write failure")

            store.project_broker_order_event = failing_record
            try:
                reconcile_submission(proposal.proposal_id, store)
                assert False, "expected the journal-write failure to raise"
            except ProposalExecutionError as exc:
                assert "unexpectedly" in str(exc)
            store.project_broker_order_event = original_record
            record = store.get_proposal(proposal.proposal_id)
            assert record["status"] == "submission_unknown"
    finally:
        restore()


def test_reconcile_submission_recovers_when_the_atomic_projection_fails():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    broker.find_order_by_client_id = lambda client_order_id: {
        "order_id": "candidate-order", "ticker": proposal.intent.ticker, "shares": proposal.intent.shares,
        "side": proposal.intent.side, "type": proposal.intent.order_type,
        "limit_price": proposal.intent.limit_price, "status": "accepted",
    }
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            store.update_proposal_status(proposal.proposal_id, "submitting")

            original_projection = store.project_broker_order_event

            def failing_projection(*args, **kwargs):
                raise sqlite3.OperationalError("simulated atomic projection failure")

            store.project_broker_order_event = failing_projection
            try:
                reconcile_submission(proposal.proposal_id, store)
                assert False, "expected the broker-state projection failure to raise"
            except ProposalExecutionError as exc:
                assert "unexpectedly" in str(exc)
            store.project_broker_order_event = original_projection
            record = store.get_proposal(proposal.proposal_id)
            # Retryable, not stranded, and never falsely projected as filled.
            assert record["status"] == "submission_unknown"
    finally:
        restore()


def test_reconcile_submission_raises_critical_when_even_the_recovery_write_fails():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    def failing_lookup(client_order_id):
        raise ConnectionError("simulated network failure")

    broker.find_order_by_client_id = failing_lookup
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            store.update_proposal_status(proposal.proposal_id, "submitting")

            def always_failing_update(pid, status, **updates):
                raise sqlite3.OperationalError("database is locked")

            def always_failing_conditional(*args, **kwargs):
                raise sqlite3.OperationalError("database is locked")

            store.update_proposal_status = always_failing_update
            store.update_proposal_status_if_current = always_failing_conditional
            try:
                reconcile_submission(proposal.proposal_id, store)
                assert False, "expected a CRITICAL RuntimeError"
            except RuntimeError as exc:
                assert "CRITICAL" in str(exc)
    finally:
        restore()


def test_recover_stale_reconciliation_resolves_a_crash_stranded_proposal():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    from assistant.execution_service import recover_stale_reconciliation

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())
        store.update_proposal_status(proposal.proposal_id, "submitting")
        claimed = store.claim_proposal(
            proposal.proposal_id, expected_status=("submitting", "submission_unknown"), new_status="reconciling",
        )
        assert claimed is not None
        # Backdate updated_at to simulate a crash long ago -- no public API
        # sets this directly, since only the store itself should normally
        # touch it.
        old_timestamp = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()
        conn = sqlite3.connect(store.path)
        try:
            conn.execute(
                "UPDATE trade_proposals SET updated_at = ? WHERE proposal_id = ?",
                (old_timestamp, proposal.proposal_id),
            )
            conn.commit()
        finally:
            conn.close()

        recovered = recover_stale_reconciliation(proposal.proposal_id, store, stale_after_seconds=300)
        assert recovered["status"] == "submission_unknown"
        record = store.get_proposal(proposal.proposal_id)
        assert record["status"] == "submission_unknown"
        assert "stale" in record["error"].lower()


# --- stale_after_seconds validation (GPT review, 2026-07-29): a zero or
# negative window makes `cutoff` >= "now", so a reconciliation claimed
# moments ago (or never) would already compare as stale, defeating the
# entire concurrency guard the CLI exposed with no validation at all.

def test_recover_stale_reconciliation_rejects_zero_with_no_mutation():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    from assistant.execution_service import recover_stale_reconciliation

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())
        store.update_proposal_status(proposal.proposal_id, "submitting")
        store.claim_proposal(
            proposal.proposal_id, expected_status=("submitting", "submission_unknown"), new_status="reconciling",
        )
        try:
            recover_stale_reconciliation(proposal.proposal_id, store, stale_after_seconds=0)
            assert False, "expected a zero stale_after_seconds to raise"
        except ValueError as exc:
            assert "positive int" in str(exc)
        record = store.get_proposal(proposal.proposal_id)
        assert record["status"] == "reconciling"  # untouched


def test_recover_stale_reconciliation_rejects_negative_with_no_mutation():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    from assistant.execution_service import recover_stale_reconciliation

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())
        store.update_proposal_status(proposal.proposal_id, "submitting")
        store.claim_proposal(
            proposal.proposal_id, expected_status=("submitting", "submission_unknown"), new_status="reconciling",
        )
        try:
            recover_stale_reconciliation(proposal.proposal_id, store, stale_after_seconds=-300)
            assert False, "expected a negative stale_after_seconds to raise"
        except ValueError as exc:
            assert "positive int" in str(exc)
        record = store.get_proposal(proposal.proposal_id)
        assert record["status"] == "reconciling"  # untouched


def test_recover_stale_reconciliation_rejects_bool_stale_after_seconds():
    from assistant.execution_service import recover_stale_reconciliation

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        try:
            recover_stale_reconciliation("tp_does_not_exist", store, stale_after_seconds=True)
            assert False, "expected a bool stale_after_seconds to raise"
        except ValueError as exc:
            assert "positive int" in str(exc)


def test_recover_stale_reconciliation_rejects_fractional_stale_after_seconds():
    from assistant.execution_service import recover_stale_reconciliation

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        try:
            recover_stale_reconciliation("tp_does_not_exist", store, stale_after_seconds=300.5)
            assert False, "expected a fractional stale_after_seconds to raise"
        except ValueError as exc:
            assert "positive int" in str(exc)


def test_recover_stale_reconciliation_leaves_a_recent_in_flight_claim_alone():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    from assistant.execution_service import recover_stale_reconciliation

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())
        store.update_proposal_status(proposal.proposal_id, "submitting")
        claimed = store.claim_proposal(
            proposal.proposal_id, expected_status=("submitting", "submission_unknown"), new_status="reconciling",
        )
        assert claimed is not None
        # No backdating -- this claim is "recent," so recovery must not touch it.
        try:
            recover_stale_reconciliation(proposal.proposal_id, store, stale_after_seconds=300)
            assert False, "expected recovery to refuse a recent, presumably in-flight claim"
        except ProposalExecutionError as exc:
            assert "not a stale" in str(exc)
        assert store.get_proposal(proposal.proposal_id)["status"] == "reconciling"


def _backdate_updated_at(store, proposal_id, seconds_ago):
    old_timestamp = (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()
    conn = sqlite3.connect(store.path)
    try:
        conn.execute("UPDATE trade_proposals SET updated_at = ? WHERE proposal_id = ?", (old_timestamp, proposal_id))
        conn.commit()
    finally:
        conn.close()


def test_reclaim_stale_status_writes_status_and_payload_in_one_atomic_call():
    # GPT review, 2026-07-29: reclaim_stale_status() used to only write
    # the status/updated_at COLUMNS, leaving the caller
    # (recover_stale_reconciliation()) to persist audit metadata
    # (recovered_at/error) via a SEPARATE, unconditional write afterward
    # -- the exact gap that made the race possible. Now both land
    # together in the SAME conditional UPDATE.
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())
        store.update_proposal_status(proposal.proposal_id, "submitting")
        store.claim_proposal(
            proposal.proposal_id, expected_status=("submitting", "submission_unknown"), new_status="reconciling",
        )
        _backdate_updated_at(store, proposal.proposal_id, 1000)
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()

        recovered = store.reclaim_stale_status(
            proposal.proposal_id, expected_status="reconciling", new_status="submission_unknown",
            stale_before=cutoff, extra_updates={"recovered_at": "2026-07-29T00:00:00+00:00", "error": "test-error"},
        )
        assert recovered is not None
        assert recovered["status"] == "submission_unknown"
        assert recovered["recovered_at"] == "2026-07-29T00:00:00+00:00"
        assert recovered["error"] == "test-error"
        # Persisted, not just returned in-memory.
        stored = store.get_proposal(proposal.proposal_id)
        assert stored["status"] == "submission_unknown"
        assert stored["recovered_at"] == "2026-07-29T00:00:00+00:00"
        assert stored["error"] == "test-error"


def test_two_concurrent_stale_recovery_attempts_only_one_succeeds():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())
        store.update_proposal_status(proposal.proposal_id, "submitting")
        store.claim_proposal(
            proposal.proposal_id, expected_status=("submitting", "submission_unknown"), new_status="reconciling",
        )
        _backdate_updated_at(store, proposal.proposal_id, 1000)
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()

        first = store.reclaim_stale_status(
            proposal.proposal_id, expected_status="reconciling", new_status="submission_unknown",
            stale_before=cutoff, extra_updates={"recovered_at": "attempt-A"},
        )
        second = store.reclaim_stale_status(
            proposal.proposal_id, expected_status="reconciling", new_status="submission_unknown",
            stale_before=cutoff, extra_updates={"recovered_at": "attempt-B"},
        )
        assert first is not None
        assert second is None  # the row was no longer "reconciling" by the time this ran
        assert store.get_proposal(proposal.proposal_id)["recovered_at"] == "attempt-A"


def test_recover_stale_reconciliation_never_touches_an_already_resolved_proposal():
    # The release-blocking regression this fix closes: an EXECUTED
    # proposal (a real terminal state reached by a different worker)
    # must never be overwritten back to "submission_unknown" by a stale-
    # recovery attempt, even one that started against genuinely stale
    # "reconciling" metadata.
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    from assistant.execution_service import recover_stale_reconciliation

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())
        store.update_proposal_status(proposal.proposal_id, "submitting")
        store.claim_proposal(
            proposal.proposal_id, expected_status=("submitting", "submission_unknown"), new_status="reconciling",
        )
        _backdate_updated_at(store, proposal.proposal_id, 1000)

        # A different worker resolves it for real in the meantime.
        store.update_proposal_status(
            proposal.proposal_id, "executed",
            executed_at=datetime.now(timezone.utc).isoformat(),
            broker_order={"order_id": "real-order"},
        )
        assert store.get_proposal(proposal.proposal_id)["status"] == "executed"

        try:
            recover_stale_reconciliation(proposal.proposal_id, store, stale_after_seconds=300)
            assert False, "expected recovery to refuse an already-resolved (executed) proposal"
        except ProposalExecutionError as exc:
            assert "not a stale" in str(exc)
        record = store.get_proposal(proposal.proposal_id)
        assert record["status"] == "executed"  # untouched
        assert record["broker_order"]["order_id"] == "real-order"


def test_concurrent_reconciliation_claims_only_one_wins():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())
        store.update_proposal_status(proposal.proposal_id, "submission_unknown")

        first = store.claim_proposal(
            proposal.proposal_id, expected_status=("submitting", "submission_unknown"), new_status="reconciling",
        )
        second = store.claim_proposal(
            proposal.proposal_id, expected_status=("submitting", "submission_unknown"), new_status="reconciling",
        )
        assert first is not None
        assert second is None  # the second "concurrent" caller must not also win


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


# --- validate_proposal_for_execution() -- the pure, side-effect-free
# validation shared by execute_approved_paper_proposal() and
# preflight_allocation_batch() (GPT review, 2026-07-29: preflight used to
# duplicate only PART of this, so it could approve a batch the real
# execution path would then reject for a reason preflight never checked).

def test_validate_proposal_for_execution_rejects_expired_proposal():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    proposal_dict = proposal.to_dict()
    proposal_dict["expires_at"] = "2020-01-01T00:00:00+00:00"
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal_dict)
        outcome = validate_proposal_for_execution(
            proposal.proposal_id, packet.portfolio, policy, store,
            now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
        )
        assert not outcome.approved
        assert "expired" in outcome.error.lower()


def test_validate_proposal_for_execution_rejects_policy_version_mismatch():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    other_policy = dataclasses.replace(policy, version="different-version")
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())
        outcome = validate_proposal_for_execution(
            proposal.proposal_id, packet.portfolio, other_policy, store,
            now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
        )
        assert not outcome.approved
        assert "policy version" in outcome.error.lower()


def test_validate_proposal_for_execution_rejects_policy_fingerprint_mismatch():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    # Same version, DIFFERENT content -- the fingerprint must catch this
    # even though the version string alone would not.
    edited_policy = dataclasses.replace(policy, max_position_pct=0.01)
    edited_policy = dataclasses.replace(edited_policy, version=policy.version)
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())
        outcome = validate_proposal_for_execution(
            proposal.proposal_id, packet.portfolio, edited_policy, store,
            now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
        )
        assert not outcome.approved
        assert "fingerprint" in outcome.error.lower()


def test_validate_proposal_for_execution_rejects_read_only_execution_mode():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    read_only_policy = dataclasses.replace(policy, execution_mode="read_only")
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(proposal.to_dict())
        outcome = validate_proposal_for_execution(
            proposal.proposal_id, packet.portfolio, read_only_policy, store,
            now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
        )
        assert not outcome.approved
        assert "paper execution" in outcome.error.lower()


def test_validate_proposal_for_execution_rejects_disallowed_side():
    # dataclasses.replace() on allowed_sides also changes the policy's
    # fingerprint, so the proposal's STORED fingerprint must be
    # recomputed against the modified policy for this test to actually
    # reach the allowed_sides check rather than failing earlier on a
    # fingerprint mismatch.
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    assert proposal.intent.side == "sell"
    no_sell_policy = dataclasses.replace(policy, allowed_sides=("buy",))
    proposal_dict = proposal.to_dict()
    proposal_dict["policy_fingerprint"] = compute_policy_fingerprint(no_sell_policy)
    # Mock broker.is_configured() etc. explicitly: relying on the ambient
    # environment's real credential state is fragile -- a DIFFERENT test
    # file (test_alpaca_broker.py) deliberately clears the real
    # APCA_API_KEY_ID/SECRET env vars as part of its own tests and never
    # restores them, which would otherwise make this test order-dependent
    # on suite-wide execution order.
    _, restore = _mock_execution_dependencies(quote_price=10.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal_dict)
            outcome = validate_proposal_for_execution(
                proposal.proposal_id, packet.portfolio, no_sell_policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert not outcome.approved
            assert "not allowed by policy" in outcome.error.lower()
    finally:
        restore()


def test_validate_proposal_for_execution_rejects_disallowed_order_type():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    no_market_policy = dataclasses.replace(policy, allowed_order_types=("limit",))
    proposal_dict = proposal.to_dict()
    proposal_dict["policy_fingerprint"] = compute_policy_fingerprint(no_market_policy)
    _, restore = _mock_execution_dependencies(quote_price=10.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal_dict)
            outcome = validate_proposal_for_execution(
                proposal.proposal_id, packet.portfolio, no_market_policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert not outcome.approved
            assert "order type" in outcome.error.lower()
    finally:
        restore()


def test_validate_proposal_for_execution_rejects_new_position_when_disallowed():
    from assistant.proposals import TradeProposal, _stable_id
    from risk.execution_gate import TradeIntent

    packet = _packet()
    policy = _policy()  # allow_new_positions=False by default
    intent = TradeIntent(ticker="NEWCO", side="buy", shares=1)
    proposal_id = _stable_id(packet, policy, intent)
    proposal_dict = TradeProposal(
        proposal_id=proposal_id, created_at=packet.generated_at, expires_at="2026-12-31T00:00:00+00:00",
        status="proposed", idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
        policy_version=policy.version, policy_fingerprint=compute_policy_fingerprint(policy),
        intent=intent, reference_price=10.0, price_timestamp=packet.generated_at,
        reasons=["test"], evidence_status="test",
        expected_impact={"trade_value": 10.0, "position_weight_before_pct": 0, "position_weight_after_pct": 0, "cash_before": 0, "cash_after": 0, "invested_pct_after": 0},
        alternatives=[], uncertainties=[],
    ).to_dict()
    _, restore = _mock_execution_dependencies(quote_price=10.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal_dict)
            outcome = validate_proposal_for_execution(
                proposal_id, packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert not outcome.approved
            assert "new positions is disabled" in outcome.error.lower()
    finally:
        restore()


def test_validate_proposal_for_execution_rejects_missing_earnings_data_when_required():
    packet = _packet()
    policy = dataclasses.replace(_policy(), allow_new_positions=True, require_earnings_data=True)
    from assistant.proposals import TradeProposal, _stable_id
    from risk.execution_gate import TradeIntent

    intent = TradeIntent(ticker="ZZZZNOPE", side="buy", shares=1)
    proposal_id = _stable_id(packet, policy, intent)
    proposal_dict = TradeProposal(
        proposal_id=proposal_id, created_at=packet.generated_at, expires_at="2026-12-31T00:00:00+00:00",
        status="proposed", idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
        policy_version=policy.version, policy_fingerprint=compute_policy_fingerprint(policy),
        intent=intent, reference_price=10.0, price_timestamp=packet.generated_at,
        reasons=["test"], evidence_status="test",
        expected_impact={"trade_value": 10.0, "position_weight_before_pct": 0, "position_weight_after_pct": 0, "cash_before": 0, "cash_after": 0, "invested_pct_after": 0},
        alternatives=[], uncertainties=[],
    ).to_dict()
    # Mock the quote fetch (so the check under test is actually reached,
    # not masked by an unrelated "can't fetch a quote for this fake
    # ticker" failure) and leave earnings unavailable (the default).
    _, restore = _mock_execution_dependencies(quote_price=10.0)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal_dict)
            outcome = validate_proposal_for_execution(
                proposal_id, packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert not outcome.approved
            assert "earnings-date data" in outcome.error.lower()
    finally:
        restore()


def test_validate_proposal_for_execution_agrees_with_batch_preflight():
    # Parity check: given the SAME state and inputs, batch preflight and
    # this shared validation must produce the same pass/fail decision --
    # they now literally share the same underlying function, but this
    # guards against a future regression reintroducing drift.
    from assistant.allocation_batch import preflight_allocation_batch

    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            direct_outcome = validate_proposal_for_execution(
                proposal.proposal_id, packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            batch_results = preflight_allocation_batch(
                [proposal.proposal_id], store, policy, packet.portfolio,
                now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            )
            assert direct_outcome.approved == batch_results[proposal.proposal_id].approved
            assert direct_outcome.validation is not None
            assert list(direct_outcome.validation.violation_codes) == list(
                batch_results[proposal.proposal_id].violation_codes
            )
    finally:
        restore()


def test_atomic_journal_failure_after_acceptance_still_marks_accepted():
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

            original_record = store.project_broker_order_event
            store.project_broker_order_event = failing_record
            try:
                order = execute_approved_paper_proposal(
                    proposal.proposal_id,
                    "approve",
                    packet.portfolio,
                    policy,
                    store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert order["order_id"] == "paper-1"
            finally:
                store.project_broker_order_event = original_record
            record = store.get_proposal(proposal.proposal_id)
            assert record["status"] == "broker_accepted"
            assert "local recording failed" in record.get("error", "")
    finally:
        restore()
