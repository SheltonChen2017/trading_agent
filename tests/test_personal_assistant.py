"""Tests for policy, persistence, proposals, and gated paper execution."""
import dataclasses
import os
import sqlite3
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

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
from assistant.portfolio_snapshot import build_portfolio_snapshot_from_alpaca
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
from tests.execution_test_support import scripted_broker_contact_boundary


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
                    "submitted_at": "2026-07-27T14:00:00+00:00",
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
        broker.submit_market_order(
            "AAPL",
            1,
            side="buy",
            idempotency_key="test-key",
            expected_policy_fingerprint="b" * 64,
        )
        assert False, "expected direct broker submission to fail"
    except PermissionError:
        pass


_FAKE_BROKER_ACCOUNT_ID = "test-paper-account"
_RECONCILIATION_SNAPSHOT_ID = "a" * 64


def _fake_broker_account(cash=5_000, *, position_market_value=5_000) -> dict:
    cash_exact = Decimal(str(cash))
    equity_exact = cash_exact + Decimal(str(position_market_value))
    return {
        "account_id": _FAKE_BROKER_ACCOUNT_ID,
        "status": "ACTIVE",
        "equity": float(equity_exact),
        "equity_decimal": _decimal_text(equity_exact),
        "cash": float(cash_exact),
        "cash_decimal": _decimal_text(cash_exact),
        "buying_power": float(cash_exact),
        "buying_power_decimal": _decimal_text(cash_exact),
        "trading_blocked": False,
        "account_blocked": False,
        "trade_suspended_by_user": False,
        "transfers_blocked": False,
        "paper": True,
    }


def _fake_broker_position() -> dict:
    return {
        "ticker": "TQQQ",
        "shares": 100.0,
        "shares_decimal": "100",
        "avg_entry_price": 50.0,
        "avg_entry_price_decimal": "50",
        "current_price": 50.0,
        "current_price_decimal": "50",
        "market_value": 5_000.0,
        "market_value_decimal": "5000",
        "unrealized_pl": 0.0,
    }


def _decimal_text(value) -> str:
    amount = Decimal(str(value))
    if amount == 0:
        return "0"
    text = format(amount, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _strict_broker_order(
    *,
    client_order_id: str,
    ticker: str,
    side: str,
    shares=None,
    notional=None,
    order_type: str = "market",
    limit_price=None,
    order_id: str = "candidate-order",
    status: str = "accepted",
    **overrides,
) -> dict:
    """Complete normalized broker evidence for submit and lookup tests."""
    submitted = datetime.now(timezone.utc) - timedelta(seconds=2)
    if (shares is None) == (notional is None):
        raise ValueError("strict test orders require exactly one of shares/notional")
    shares_exact = None if shares is None else _decimal_text(shares)
    notional_exact = None if notional is None else _decimal_text(notional)
    limit_exact = None if limit_price is None else _decimal_text(limit_price)
    order = {
        "order_id": order_id,
        "client_order_id": client_order_id,
        "ticker": ticker,
        "asset_class": "us_equity",
        "order_class": "simple",
        "extended_hours": False,
        "legs": None,
        "shares": None if shares_exact is None else float(Decimal(shares_exact)),
        "shares_decimal": shares_exact,
        "notional": (
            None if notional_exact is None else float(Decimal(notional_exact))
        ),
        "notional_decimal": notional_exact,
        "side": side,
        "type": order_type,
        "limit_price": None if limit_exact is None else float(Decimal(limit_exact)),
        "limit_price_decimal": limit_exact,
        "time_in_force": "day",
        "status": status,
        "filled_qty": 0.0,
        "filled_qty_decimal": "0",
        "filled_avg_price": None,
        "filled_avg_price_decimal": None,
        "submitted_at": submitted.isoformat(),
        "updated_at": (submitted + timedelta(seconds=1)).isoformat(),
        "filled_at": None,
        "canceled_at": None,
        "expired_at": None,
        "failed_at": None,
        "replaced_at": None,
        "replaces": None,
        "replaced_by": None,
    }
    order.update(overrides)
    return order


def _valid_broker_execution_context(policy: TradingPolicy) -> dict:
    return {
        "account_id": _FAKE_BROKER_ACCOUNT_ID,
        "account_mode": "paper",
        "snapshot_id": _RECONCILIATION_SNAPSHOT_ID,
        "policy_fingerprint": compute_policy_fingerprint(policy),
    }


def _set_reconcilable_status(
    store: AssistantStore,
    proposal_id: str,
    status: str,
    policy: TradingPolicy,
    **updates,
) -> dict:
    return store.update_proposal_status(
        proposal_id,
        status,
        broker_execution_context=_valid_broker_execution_context(policy),
        **updates,
    )


def _mock_execution_dependencies(
    quote_price=50.0,
    quote_timestamp=None,
    earnings_available=False,
    bid=None,
    ask=None,
    open_orders_error=None,
    broker_cash_sequence=None,
    broker_open_orders=None,
    broker_positions=None,
):
    """Patch one frozen fake paper session and its provider seams.

    The session captures a genuine strict portfolio snapshot through the same
    production builder, while module functions remain patchable by individual
    fault tests. It supports the complete submit/lookup/cancel contract and
    consumes the expected snapshot/policy keywords at the session boundary.

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
        "get_order_by_id": broker.get_order_by_id,
        "cancel_order": broker.cancel_order,
        "assert_account_and_asset_ready": broker.assert_account_and_asset_ready,
        "open_alpaca_broker_session": broker.open_alpaca_broker_session,
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
        "account": {
            "account_id": _FAKE_BROKER_ACCOUNT_ID,
            "paper": True,
            "status": "ACTIVE",
        },
        "asset": {"ticker": ticker, "status": "active", "tradable": True},
    }
    event_data.fetch_upcoming_earnings = lambda tickers, as_of=None: {
        t: {"ticker": t, "available": earnings_available, "days_away": 1 if earnings_available else None}
        for t in tickers
    }

    def fake_submit(
        ticker,
        shares,
        side="buy",
        *,
        authorization=None,
        idempotency_key=None,
        whole_shares_only=True,
    ):
        assert authorization is not None
        captured.append((ticker, shares, side, idempotency_key))
        return _strict_broker_order(
            order_id=f"paper-{len(captured)}",
            client_order_id=idempotency_key,
            ticker=ticker,
            shares=shares,
            side=side,
        )

    def fake_submit_limit(
        ticker,
        shares,
        limit_price,
        side="buy",
        *,
        authorization=None,
        idempotency_key=None,
        whole_shares_only=True,
    ):
        assert authorization is not None
        captured.append((ticker, shares, side, idempotency_key, limit_price))
        return _strict_broker_order(
            order_id=f"paper-limit-{len(captured)}",
            client_order_id=idempotency_key,
            ticker=ticker,
            shares=shares,
            side=side,
            order_type="limit",
            limit_price=limit_price,
        )

    broker.submit_market_order = fake_submit
    broker.submit_limit_order = fake_submit_limit
    broker.find_order_by_client_id = lambda client_order_id: None
    broker.get_order_by_id = lambda order_id: None
    broker.cancel_order = lambda order_id: None

    class FakeAccountScopedBrokerSession:
        PAPER_TRADING = True
        account_mode = "paper"

        def __init__(self):
            self._latest_snapshot_id = None
            self._capture_count = 0
            self._active_cash = 5_000

        def is_configured(self):
            return True

        def get_account(self):
            position_value = sum(
                (
                    Decimal(str(position["market_value_decimal"]))
                    for position in self._position_rows()
                ),
                Decimal("0"),
            )
            return deepcopy(
                _fake_broker_account(
                    self._active_cash,
                    position_market_value=position_value,
                )
            )

        def _position_rows(self):
            return (
                [_fake_broker_position()]
                if broker_positions is None
                else broker_positions
            )

        def get_open_positions(self):
            return deepcopy(list(self._position_rows()))

        def get_open_orders(self):
            if open_orders_error is not None:
                raise open_orders_error
            return deepcopy(list(broker_open_orders or []))

        def capture_execution_portfolio_snapshot(self):
            if broker_cash_sequence:
                index = min(self._capture_count, len(broker_cash_sequence) - 1)
                self._active_cash = broker_cash_sequence[index]
            snapshot = build_portfolio_snapshot_from_alpaca(
                broker_session=self,
                require_execution_coherence=True,
                expected_account_id=_FAKE_BROKER_ACCOUNT_ID,
            )
            self._capture_count += 1
            self._latest_snapshot_id = snapshot.broker_snapshot_id
            return snapshot

        def assert_account_and_asset_ready(self, ticker):
            return broker.assert_account_and_asset_ready(ticker)

        def get_latest_quote(self, ticker):
            return broker.get_latest_quote(ticker)

        def get_execution_validation_quote(
            self, ticker, *, expected_snapshot_id
        ):
            assert expected_snapshot_id == self._latest_snapshot_id
            return broker.get_latest_quote(ticker)

        def submit_market_order(
            self,
            ticker,
            shares,
            side="buy",
            *,
            authorization=None,
            idempotency_key=None,
            dispatch_permit=None,
            expected_snapshot_id=None,
            expected_policy_fingerprint=None,
            whole_shares_only=True,
        ):
            with scripted_broker_contact_boundary(
                broker_session=self,
                snapshot_id_reader=lambda: self._latest_snapshot_id,
                consume_snapshot=lambda: setattr(
                    self, "_latest_snapshot_id", None
                ),
                ticker=ticker,
                shares=shares,
                side=side,
                order_type="market",
                limit_price=None,
                authorization=authorization,
                idempotency_key=idempotency_key,
                dispatch_permit=dispatch_permit,
                expected_snapshot_id=expected_snapshot_id,
                expected_policy_fingerprint=expected_policy_fingerprint,
            ):
                kwargs = {
                    "authorization": authorization,
                    "idempotency_key": idempotency_key,
                }
                if whole_shares_only is False:
                    kwargs["whole_shares_only"] = False
                return broker.submit_market_order(
                    ticker, shares, side=side, **kwargs
                )

        def submit_limit_order(
            self,
            ticker,
            shares,
            limit_price,
            side="buy",
            *,
            authorization=None,
            idempotency_key=None,
            dispatch_permit=None,
            expected_snapshot_id=None,
            expected_policy_fingerprint=None,
            whole_shares_only=True,
        ):
            with scripted_broker_contact_boundary(
                broker_session=self,
                snapshot_id_reader=lambda: self._latest_snapshot_id,
                consume_snapshot=lambda: setattr(
                    self, "_latest_snapshot_id", None
                ),
                ticker=ticker,
                shares=shares,
                side=side,
                order_type="limit",
                limit_price=limit_price,
                authorization=authorization,
                idempotency_key=idempotency_key,
                dispatch_permit=dispatch_permit,
                expected_snapshot_id=expected_snapshot_id,
                expected_policy_fingerprint=expected_policy_fingerprint,
            ):
                kwargs = {
                    "authorization": authorization,
                    "idempotency_key": idempotency_key,
                }
                if whole_shares_only is False:
                    kwargs["whole_shares_only"] = False
                return broker.submit_limit_order(
                    ticker, shares, limit_price, side=side, **kwargs
                )

        def find_order_by_client_id(self, client_order_id):
            return broker.find_order_by_client_id(client_order_id)

        def get_order_by_id(self, order_id):
            return broker.get_order_by_id(order_id)

        def cancel_order(self, order_id):
            return broker.cancel_order(order_id)

    fake_session = FakeAccountScopedBrokerSession()
    broker.open_alpaca_broker_session = lambda: fake_session

    def restore():
        broker.is_configured = originals["is_configured"]
        broker.submit_market_order = originals["submit_market_order"]
        broker.submit_limit_order = originals["submit_limit_order"]
        broker.find_order_by_client_id = originals["find_order_by_client_id"]
        broker.get_order_by_id = originals["get_order_by_id"]
        broker.cancel_order = originals["cancel_order"]
        broker.assert_account_and_asset_ready = originals["assert_account_and_asset_ready"]
        broker.open_alpaca_broker_session = originals["open_alpaca_broker_session"]
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
            telemetry = store.list_execution_telemetry_events(
                proposal_id=proposal.proposal_id
            )
            assert [event["event_type"] for event in telemetry] == [
                "validation_approved",
                "submission_started",
            ]
            assert len({event["attempt_id"] for event in telemetry}) == 1
            assert all(event["account_mode"] == "paper" for event in telemetry)
            assert all(
                event["broker_account_id"] == "test-paper-account"
                for event in telemetry
            )
            assert Decimal(telemetry[0]["payload"]["quote"]["price"]) == Decimal(
                str(proposal.reference_price)
            )
    finally:
        restore()


def test_malformed_padded_submission_order_id_is_never_rewritten_for_cancel():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _captured, restore = _mock_execution_dependencies(
        quote_price=proposal.reference_price
    )
    cancel_calls = []

    def padded_id_submit(
        ticker,
        shares,
        side="buy",
        *,
        authorization=None,
        idempotency_key=None,
        whole_shares_only=True,
    ):
        del whole_shares_only
        assert authorization is not None
        order = _strict_broker_order(
            order_id="accepted-but-padded",
            client_order_id=idempotency_key,
            ticker=ticker,
            shares=shares,
            side=side,
        )
        order["order_id"] = " accepted-but-padded "
        return order

    broker.submit_market_order = padded_id_submit
    broker.cancel_order = lambda order_id: cancel_calls.append(order_id)
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            with pytest.raises(
                ProposalExecutionError,
                match="failed strict identity/schema validation",
            ):
                execute_approved_paper_proposal(
                    proposal.proposal_id,
                    "approve",
                    packet.portfolio,
                    policy,
                    store,
                    now_et=datetime(
                        2026, 7, 27, 10, 0, tzinfo=timezone.utc
                    ),
                )
            assert cancel_calls == []
            assert store.get_kill_switch()["active"] is True
    finally:
        restore()


def test_fractional_policy_reaches_the_broker_as_exact_text_end_to_end():
    """SET-1 is executable authority, not a UI-only preference.

    Prove the complete path: policy-aware sizing creates exact decimal text,
    durable storage rehydrates it, fresh broker preflight confirms the asset,
    the gate authorizes it, and submission receives both the unchanged text
    and the explicit permissive flag.
    """
    packet = _packet()
    policy = dataclasses.replace(
        _policy(), allow_new_positions=True, whole_shares_only=False
    )
    proposal = generate_allocation_buy_proposals(
        packet,
        policy,
        weights_pct={"AAPL": 100.0},
        prices={"AAPL": 50.0},
        dollar_amount=25.0,
    )[0]
    assert proposal.intent.shares == "0.5"

    captured, restore = _mock_execution_dependencies(quote_price=50.0)
    submitted = []

    def fractional_submit(
        ticker,
        shares,
        side="buy",
        *,
        authorization=None,
        idempotency_key=None,
        whole_shares_only=True,
    ):
        assert authorization is not None
        submitted.append((ticker, shares, side, whole_shares_only))
        return _strict_broker_order(
            order_id="paper-fractional-1",
            client_order_id=idempotency_key,
            ticker=ticker,
            shares=shares,
            side=side,
        )

    broker.submit_market_order = fractional_submit
    broker.assert_account_and_asset_ready = lambda ticker: {
        "account": {
            "account_id": "test-paper-account",
            "paper": True,
            "status": "ACTIVE",
        },
        "asset": {
            "ticker": ticker,
            "status": "active",
            "tradable": True,
            "fractionable": True,
        },
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
            assert order["order_id"] == "paper-fractional-1"
            assert submitted == [("AAPL", "0.5", "buy", False)]
            assert store.get_proposal(proposal.proposal_id)["status"] == "broker_accepted"
    finally:
        restore()


def test_recovered_pre_broker_claim_fences_a_worker_that_resumes():
    """An old worker must not resurrect its proposal after recovery.

    Exercise both recoverable states. Recovery releases proposal A's
    ticker/side slot, proposal B immediately claims it, and then A's original
    execution resumes at its next transition. A must lose the conditional
    transition before reserving budget or contacting the broker.
    """
    from assistant.execution_service import recover_stale_claim
    from assistant.proposal_status import (
        APPROVED,
        IN_FLIGHT_INTENT_STATUSES,
        SUBMITTING,
        VALIDATING,
        VALIDATION_FAILED,
    )

    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(
        quote_price=proposal.reference_price
    )
    try:
        for recovered_status, next_status in (
            (VALIDATING, APPROVED),
            (APPROVED, SUBMITTING),
        ):
            with tempfile.TemporaryDirectory() as temp:
                store = AssistantStore(Path(temp) / "assistant.db")
                original = proposal.to_dict()
                replacement = proposal.to_dict()
                replacement["proposal_id"] = (
                    f"{proposal.proposal_id}-after-{recovered_status}"
                )
                replacement["idempotency_key"] = (
                    f"{proposal.idempotency_key}-after-{recovered_status}"
                )
                store.save_proposal(original)
                store.save_proposal(replacement)

                real_transition = store.update_proposal_status_if_current
                interleaved = {"done": False}

                def transition_with_recovery(proposal_id, **kwargs):
                    if (
                        not interleaved["done"]
                        and proposal_id == proposal.proposal_id
                        and kwargs["expected_statuses"] == (recovered_status,)
                        and kwargs["new_status"] == next_status
                    ):
                        interleaved["done"] = True
                        old_timestamp = (
                            datetime.now(timezone.utc) - timedelta(hours=2)
                        ).isoformat()
                        connection = sqlite3.connect(store.path)
                        try:
                            connection.execute(
                                "UPDATE trade_proposals SET updated_at = ? "
                                "WHERE proposal_id = ?",
                                (old_timestamp, proposal.proposal_id),
                            )
                            connection.commit()
                        finally:
                            connection.close()
                        recovered = recover_stale_claim(
                            proposal.proposal_id, store
                        )
                        assert recovered["status"] == VALIDATION_FAILED
                        competing_claim = store.claim_proposal(
                            replacement["proposal_id"],
                            expected_status="proposed",
                            new_status=VALIDATING,
                            conflicting_intent_statuses=IN_FLIGHT_INTENT_STATUSES,
                        )
                        assert competing_claim is not None
                    return real_transition(proposal_id, **kwargs)

                store.update_proposal_status_if_current = transition_with_recovery

                try:
                    execute_approved_paper_proposal(
                        proposal.proposal_id,
                        "approve",
                        packet.portfolio,
                        policy,
                        store,
                        now_et=datetime(
                            2026, 7, 27, 10, 0, tzinfo=timezone.utc
                        ),
                    )
                    assert False, "expected the recovered worker to lose its claim"
                except ProposalExecutionError as exc:
                    assert "lost its execution claim" in str(exc)

                assert interleaved["done"] is True
                assert captured == []
                assert (
                    store.get_proposal(proposal.proposal_id)["status"]
                    == VALIDATION_FAILED
                )
                assert (
                    store.get_proposal(replacement["proposal_id"])["status"]
                    == VALIDATING
                )
    finally:
        restore()


def test_unsupported_order_type_is_refused_not_downgraded_to_a_market_order():
    # Independent review, 2026-07-29: the submit dispatch used to read
    # "limit, else market", so ANY other order type would have been
    # submitted as an unbounded-price MARKET order. Bound execution now
    # validates the exact TradingPolicy inside the gate, so an unsupported
    # policy/order type is rejected even earlier and can never reach dispatch.
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
            except ValueError as exc:
                assert "Unsupported/unimplemented allowed_order_types" in str(exc)
            # The critical property: no order reached the broker at all.
            assert captured == []
            refreshed = store.get_proposal(proposal.proposal_id)
            assert refreshed["status"] == "validation_failed"
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
    captured, restore = _mock_execution_dependencies(
        quote_price=proposal.reference_price,
        open_orders_error=ConnectionError("broker open orders unavailable"),
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
                assert False, "expected approval to fail closed when open orders can't be verified"
            except ConnectionError as exc:
                assert "open orders" in str(exc)
            assert len(captured) == 0
            assert (
                store.get_proposal(proposal.proposal_id)["status"]
                == "validation_failed"
            )
    finally:
        restore()


def _earnings_buy_fixture():
    packet = _packet()
    policy = dataclasses.replace(
        _policy(),
        max_position_pct=1.0,
        max_total_exposure_pct=1.0,
        max_basket_pct=1.0,
        max_leveraged_etf_pct=1.0,
    )
    proposal = _buy_proposal_dict(packet, policy, "TQQQ", 1)
    return packet, policy, proposal


def test_approval_blocked_when_earnings_are_near_for_a_buy():
    packet, policy, proposal = _earnings_buy_fixture()
    captured, restore = _mock_execution_dependencies(
        quote_price=proposal["reference_price"], earnings_available=True
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal)
            try:
                execute_approved_paper_proposal(
                    proposal["proposal_id"],
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


def test_earnings_blackout_does_not_block_a_proved_risk_reducing_sell():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(
        quote_price=proposal.reference_price, earnings_available=True
    )
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
            assert order["status"] == "accepted"
            assert len(captured) == 1
    finally:
        restore()


def test_earnings_only_block_raises_overridable_error_and_leaves_proposal_re_claimable():
    packet, policy, proposal = _earnings_buy_fixture()
    captured, restore = _mock_execution_dependencies(
        quote_price=proposal["reference_price"], earnings_available=True
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal)
            try:
                execute_approved_paper_proposal(
                    proposal["proposal_id"], "approve", packet.portfolio, policy, store,
                    now_et=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                )
                assert False, "expected an overridable earnings-blackout block"
            except PolicyOverridableBlockError as exc:
                assert any("earnings" in v.lower() for v in exc.overridable_violations)
            assert len(captured) == 0
            assert store.get_proposal(proposal["proposal_id"])["status"] == POLICY_OVERRIDE_AVAILABLE
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
    packet, policy, proposal = _earnings_buy_fixture()
    captured, restore = _mock_execution_dependencies(
        quote_price=proposal["reference_price"], earnings_available=True
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal)
            try:
                execute_approved_paper_proposal(
                    proposal["proposal_id"], "approve", packet.portfolio, policy, store,
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
                proposal["proposal_id"], "approve", packet.portfolio, policy, store,
                now_et=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
                override_policy_violations=True,
            )
            assert order["status"] == "accepted"
            assert len(captured) == 1
            stored = store.get_proposal(proposal["proposal_id"])
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
    captured, restore = _mock_execution_dependencies(
        quote_price=50.0,
        broker_cash_sequence=(5_000.0, 500_000.0),
    )
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

            # The next broker-owned capture observes a much bigger account.
            # The same $2,000 buy is therefore a much smaller percentage --
            # same violation CODE (still over the 0.1% cap), but a materially
            # different projected-exposure MESSAGE.
            try:
                execute_approved_paper_proposal(
                    proposal.proposal_id, "approve", small_account_packet.portfolio, policy, store,
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
            telemetry = store.list_execution_telemetry_events(
                proposal_id=proposal.proposal_id
            )
            assert [event["event_type"] for event in telemetry] == [
                "validation_refused"
            ]
            assert "stale_price" in telemetry[0]["payload"]["violation_codes"]
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
            telemetry = store.list_execution_telemetry_events(
                proposal_id=proposal.proposal_id
            )
            assert [event["event_type"] for event in telemetry] == [
                "validation_failed"
            ]
            assert "simulated unexpected bug" in telemetry[0]["payload"]["error"]
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
    pending_buy = _strict_broker_order(
        order_id="o1",
        client_order_id="pending-nvda-buy",
        ticker="NVDA",
        shares=10,
        side="buy",
        status="new",
    )
    captured, restore = _mock_execution_dependencies(
        quote_price=50.0,
        broker_open_orders=[pending_buy],
    )
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


def test_stale_pending_market_buy_quote_blocks_a_buy_approval():
    packet, policy, proposal_id, proposal = (
        _buy_proposal_with_a_pending_order_on_another_ticker("buy")
    )
    pending_buy = _strict_broker_order(
        order_id="o1",
        client_order_id="pending-nvda-buy",
        ticker="NVDA",
        shares=10,
        side="buy",
        status="new",
    )
    captured, restore = _mock_execution_dependencies(
        quote_price=50.0,
        broker_open_orders=[pending_buy],
    )
    original_get_latest_quote = broker.get_latest_quote

    def stale_pending_quote(ticker):
        quote = dict(original_get_latest_quote(ticker))
        if ticker == "NVDA":
            quote["timestamp"] = datetime(
                2026, 7, 27, 8, 0, tzinfo=timezone.utc
            )
        return quote

    broker.get_latest_quote = stale_pending_quote
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal)
            with pytest.raises(ProposalExecutionError, match="pending buy") as caught:
                execute_approved_paper_proposal(
                    proposal_id,
                    "approve",
                    packet.portfolio,
                    policy,
                    store,
                    now_et=datetime(
                        2026, 7, 27, 10, 0, tzinfo=timezone.utc
                    ),
                )
            assert "minutes old" in str(caught.value)
            assert captured == []
    finally:
        restore()


def test_pending_buy_value_lookup_failure_does_not_block_a_sell_approval():
    # A risk-reducing sell never consults pending_buy_value_by_ticker, so
    # an unrelated pending buy's quote failure shouldn't block it.
    packet, policy, proposal_id, proposal = _buy_proposal_with_a_pending_order_on_another_ticker("sell")
    pending_buy = _strict_broker_order(
        order_id="o1",
        client_order_id="pending-nvda-buy",
        ticker="NVDA",
        shares=10,
        side="buy",
        status="new",
    )
    captured, restore = _mock_execution_dependencies(
        quote_price=50.0,
        broker_open_orders=[pending_buy],
    )
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

    pending_sell = _strict_broker_order(
        order_id="o1",
        client_order_id="pending-tqqq-sell",
        ticker="TQQQ",
        side="sell",
        notional=500.0,
        status="new",
    )
    captured, restore = _mock_execution_dependencies(
        quote_price=50.0,
        broker_open_orders=[pending_sell],
    )
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
            assert order["limit_price"] == "49.5"
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
    broker.find_order_by_client_id = lambda client_order_id: _strict_broker_order(
        order_id="reconciled-1",
        client_order_id=client_order_id,
        ticker=proposal.intent.ticker,
        shares=proposal.intent.shares,
        side=proposal.intent.side,
        order_type=proposal.intent.order_type,
        limit_price=proposal.intent.limit_price,
    )
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


def test_immediate_404_after_submission_error_remains_unknown_during_indexing_grace():
    """A timeout can lose an accepted response before the broker's client-id
    lookup is indexed. An immediate 404 therefore keeps both the unresolved
    state and its execution-budget reservation."""
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    captured, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)

    def failing_submit(ticker, shares, side="buy", *, authorization=None, idempotency_key=None):
        raise TimeoutError("simulated network timeout")

    broker.submit_market_order = failing_submit
    broker.find_order_by_client_id = lambda client_order_id: None  # immediate 404; indexing may lag
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
                assert False, "expected an unresolved submission to raise"
            except ProposalExecutionError as exc:
                assert "submission_unknown" in str(exc)
            assert store.get_proposal(proposal.proposal_id)["status"] == "submission_unknown"
            usage = store.get_execution_budget_usage("2026-07-27")
            assert usage["submitted_order_count"] == 1
    finally:
        restore()


def test_reconcile_submission_resolves_stuck_proposal_to_executed():
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    broker.find_order_by_client_id = lambda client_order_id: _strict_broker_order(
        order_id="reconciled-2",
        client_order_id=client_order_id,
        ticker=proposal.intent.ticker,
        shares=proposal.intent.shares,
        side=proposal.intent.side,
        order_type=proposal.intent.order_type,
        limit_price=proposal.intent.limit_price,
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            _set_reconcilable_status(
                store, proposal.proposal_id, "submission_unknown", policy
            )

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

    broker.find_order_by_client_id = lambda client_order_id: _strict_broker_order(
        order_id="wrong-order",
        client_order_id=client_order_id,
        ticker="AAPL",  # does not match the proposal's ticker
        shares=999,
        side="buy",
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            proposal_dict = proposal.to_dict()
            store.save_proposal(proposal_dict)
            _set_reconcilable_status(
                store, proposal.proposal_id, "submission_unknown", policy
            )

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

    def lookup_order(client_order_id):
        order = _strict_broker_order(
            order_id="candidate-order",
            client_order_id=client_order_id,
            ticker=proposal.intent.ticker,
            shares=proposal.intent.shares,
            side=proposal.intent.side,
            order_type=proposal.intent.order_type,
            limit_price=proposal.intent.limit_price,
        )
        order.update(order_overrides)
        if "shares" in order_overrides:
            value = order_overrides["shares"]
            order["shares_decimal"] = (
                None if value is None else _decimal_text(value)
            )
        if "limit_price" in order_overrides:
            value = order_overrides["limit_price"]
            order["limit_price_decimal"] = (
                None if value is None else _decimal_text(value)
            )
        return order

    broker.find_order_by_client_id = lookup_order
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            _set_reconcilable_status(
                store, proposal.proposal_id, "submission_unknown", policy
            )
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
    _reconcile_mismatch_case({"shares": 1}, "quantity_mismatch")


def test_reconcile_submission_refuses_mismatched_order_type():
    _reconcile_mismatch_case(
        {"type": "limit", "limit_price": 50.0}, "order_type_mismatch"
    )


def test_reconcile_submission_refuses_mismatched_side():
    _reconcile_mismatch_case({"side": "buy"}, "side_mismatch")


def test_reconcile_submission_refuses_missing_quantity():
    _reconcile_mismatch_case({"shares": None}, "invalid_order_size")


def test_reconcile_submission_refuses_missing_order_type():
    _reconcile_mismatch_case({"type": None}, "invalid_order_type")


def test_reconcile_submission_accepts_numerically_equivalent_share_counts():
    # 10 and 10.0 must be treated as equal -- only the actual quantity
    # matters, not whether the broker returned an int or a float.
    packet = _packet()
    policy = _policy()
    proposal = generate_risk_reduction_proposals(packet, policy)[0]
    _, restore = _mock_execution_dependencies(quote_price=proposal.reference_price)
    from assistant.execution_service import reconcile_submission

    broker.find_order_by_client_id = lambda client_order_id: _strict_broker_order(
        order_id="candidate-order",
        client_order_id=client_order_id,
        ticker=proposal.intent.ticker,
        # Equivalent, not identical, numeric representation.
        shares=float(proposal.intent.shares),
        side=proposal.intent.side,
        order_type=proposal.intent.order_type,
        limit_price=proposal.intent.limit_price,
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            _set_reconcilable_status(
                store, proposal.proposal_id, "submission_unknown", policy
            )
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
    broker.find_order_by_client_id = lambda client_order_id: _strict_broker_order(
        order_id="candidate-order",
        client_order_id=client_order_id,
        ticker="TQQQ",
        shares=10,
        side="sell",
        order_type="limit",
        limit_price=45.0,  # does NOT match the proposal's 49.5
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(limit_proposal)
            _set_reconcilable_status(
                store, proposal_id, "submission_unknown", policy
            )
            try:
                reconcile_submission(proposal_id, store)
                assert False, "expected a mismatched limit price to be refused"
            except ProposalExecutionError as exc:
                assert "MISMATCHED" in str(exc)
            record = store.get_proposal(proposal_id)
            assert record["status"] == "submission_unknown"
            assert "limit_price_mismatch" in record["error"]
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
    broker.find_order_by_client_id = lambda client_order_id: _strict_broker_order(
        order_id="candidate-order",
        client_order_id=client_order_id,
        ticker="TQQQ",
        shares=10,
        side="sell",
        order_type="limit",
        limit_price=49.5,
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(limit_proposal)
            _set_reconcilable_status(
                store, proposal_id, "submission_unknown", policy
            )
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
            _set_reconcilable_status(
                store, proposal.proposal_id, "submitting", policy
            )
            _backdate_updated_at(store, proposal.proposal_id, seconds_ago=120)

            try:
                reconcile_submission(proposal.proposal_id, store)
                assert False, "expected a confirmed-absent order to raise"
            except ProposalExecutionError as exc:
                assert "never accepted" in str(exc)
            assert store.get_proposal(proposal.proposal_id)["status"] == "submission_failed"
    finally:
        restore()


def test_reconcile_submission_keeps_a_recent_404_unresolved_and_reserved():
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
            _set_reconcilable_status(
                store, proposal.proposal_id, "submitting", policy
            )
            store.reserve_execution_budget(
                proposal.proposal_id,
                trading_day="2026-07-30",
                notional=100.0,
                max_daily_notional=10_000.0,
                max_daily_orders=10,
            )

            try:
                reconcile_submission(proposal.proposal_id, store)
                assert False, "expected a too-recent absence to remain unresolved"
            except ProposalExecutionError as exc:
                assert "grace period has not elapsed" in str(exc)

            assert store.get_proposal(proposal.proposal_id)["status"] == "submission_unknown"
            usage = store.get_execution_budget_usage("2026-07-30")
            assert usage["submitted_order_count"] == 1
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
            _set_reconcilable_status(
                store, proposal.proposal_id, "submitting", policy
            )
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
            _set_reconcilable_status(
                store, proposal.proposal_id, "submitting", policy
            )
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

    broker.find_order_by_client_id = lambda client_order_id: _strict_broker_order(
        order_id="candidate-order",
        client_order_id=client_order_id,
        ticker=proposal.intent.ticker,
        shares=proposal.intent.shares,
        side=proposal.intent.side,
        order_type=proposal.intent.order_type,
        limit_price=proposal.intent.limit_price,
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            _set_reconcilable_status(
                store, proposal.proposal_id, "submitting", policy
            )

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

    broker.find_order_by_client_id = lambda client_order_id: _strict_broker_order(
        order_id="candidate-order",
        client_order_id=client_order_id,
        ticker=proposal.intent.ticker,
        shares=proposal.intent.shares,
        side=proposal.intent.side,
        order_type=proposal.intent.order_type,
        limit_price=proposal.intent.limit_price,
    )
    try:
        with tempfile.TemporaryDirectory() as temp:
            store = AssistantStore(Path(temp) / "assistant.db")
            store.save_proposal(proposal.to_dict())
            _set_reconcilable_status(
                store, proposal.proposal_id, "submitting", policy
            )

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
            _set_reconcilable_status(
                store, proposal.proposal_id, "submitting", policy
            )

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


# --- validate_proposal_for_execution() -- the read-only (reads state and
# queries the broker, writes nothing) validation shared by
# execute_approved_paper_proposal() and
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


# --- Proposal-generation guards (mutation testing, 2026-07-29: each guard
# exercised below could be deleted without failing any test, even though
# they decide whether a real sell proposal is generated).

def _basket_packet(aapl_market_value: float, cash: float, equity_check: float | None = None):
    """Portfolio holding only AAPL (a member of BASKETS['tech']) at an exact
    market value, so the basket-limit boundary can be hit precisely."""
    shares = 100
    price = aapl_market_value / shares
    snapshot = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": shares, "entry_price": price, "current_price": price}], cash=cash,
    )
    if equity_check is not None:
        assert abs(snapshot.total_equity - equity_check) < 1e-6, snapshot.total_equity
    return DecisionPacket(
        generated_at="2026-07-29T12:00:00+00:00", portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(benchmark_ticker="QQQ", trend="uptrend", volatility_regime="low_vol",
                            trailing_volatility_pct=1.0, as_of="2026-07-29"),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )


def _basket_only_policy(max_basket_pct=0.40, max_order_value=50_000.0):
    # Every OTHER cap is opened up so only the basket check can fire.
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=1.0, max_total_exposure_pct=1.0, max_basket_pct=max_basket_pct,
        max_leveraged_etf_pct=1.0, min_cash_reserve_pct=0.0, max_order_value=max_order_value,
    )


def test_basket_exposure_exactly_at_the_limit_generates_no_proposal():
    # Boundary: `<=` means AT the limit is compliant. This also protects the
    # exact-value (non-rounded) basket math -- a rounded 40.0% would tie here
    # and silently evade generation.
    packet = _basket_packet(aapl_market_value=4_000.0, cash=6_000.0, equity_check=10_000.0)
    assert generate_risk_reduction_proposals(packet, _basket_only_policy(0.40)) == []


def test_basket_exposure_just_over_the_limit_generates_a_proposal():
    packet = _basket_packet(aapl_market_value=4_001.0, cash=5_999.0, equity_check=10_000.0)
    proposals = generate_risk_reduction_proposals(packet, _basket_only_policy(0.40))
    assert len(proposals) == 1
    assert proposals[0].intent.ticker == "AAPL"
    assert proposals[0].intent.side == "sell"
    assert any("exposure exceeds" in r for r in proposals[0].reasons)


def test_zero_equity_portfolio_generates_no_proposals():
    snapshot = build_portfolio_snapshot([], cash=0.0)
    packet = DecisionPacket(
        generated_at="2026-07-29T12:00:00+00:00", portfolio=snapshot,
        risk=build_risk_exposure(snapshot),
        regime=MarketRegime(benchmark_ticker="QQQ", trend=None, volatility_regime=None,
                            trailing_volatility_pct=None, as_of="2026-07-29"),
        signals=[], upcoming_events=[], warnings=[], policy_version="test",
    )
    assert generate_risk_reduction_proposals(packet, _basket_only_policy()) == []


def test_max_order_value_below_one_share_generates_no_proposal():
    # A breach exists, but the per-order cap can't afford even one share --
    # a 0-share proposal would be unexecutable forever.
    packet = _basket_packet(aapl_market_value=8_000.0, cash=2_000.0, equity_check=10_000.0)
    policy = _basket_only_policy(max_basket_pct=0.40, max_order_value=1.0)  # share price is $80
    assert generate_risk_reduction_proposals(packet, policy) == []


def test_allocation_proposals_refuse_a_non_positive_dollar_amount():
    packet = _basket_packet(aapl_market_value=1_000.0, cash=9_000.0, equity_check=10_000.0)
    policy = _basket_only_policy()
    for amount in (0.0, -100.0):
        assert generate_allocation_buy_proposals(
            packet, policy, {"AAPL": 100.0}, {"AAPL": 10.0}, amount
        ) == []
    assert generate_allocation_buy_proposals(packet, policy, {}, {"AAPL": 10.0}, 1_000.0) == []


def test_build_risk_exposure_reports_zero_equity_rather_than_dividing_by_it():
    snapshot = build_portfolio_snapshot([], cash=0.0)
    risk = build_risk_exposure(snapshot)
    assert risk.basket_exposure_pct == {}
    assert risk.leveraged_etf_exposure_pct == 0.0
    assert any("zero or negative total equity" in w for w in risk.concentration_warnings)
