from __future__ import annotations

import dataclasses
import hashlib
import multiprocessing
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

import risk.execution_gate as execution_gate_module
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_snapshot import (
    build_portfolio_snapshot,
    build_portfolio_snapshot_from_alpaca,
)
from risk.execution_gate import (
    ExecutionValidationContext,
    TradeIntent,
    authorize_overridden_trade_intent,
    authorize_trade_intent,
    validate_trade_intent,
    verify_execution_authorization,
)


_MARKET_OPEN = datetime(2026, 7, 27, 10, 0)
_ACCOUNT_ID = "paper-account-1"
_OTHER_SNAPSHOT_ID = hashlib.sha256(b"other-snapshot").hexdigest()
_OTHER_POLICY_FINGERPRINT = hashlib.sha256(b"other-policy").hexdigest()


def _verify_in_fork_child(intent, authorization, connection) -> None:
    """Report whether a pre-fork authorization retained authority in child."""
    try:
        verify_execution_authorization(intent, authorization, require_bound=True)
    except Exception as exc:  # serialized evidence for the parent assertion
        connection.send(("refused", type(exc).__name__, str(exc)))
    else:
        connection.send(("accepted", None, None))
    finally:
        connection.close()


def _paper_policy(**replacements) -> TradingPolicy:
    values = {
        "version": "binding-test-v1",
        "name": "Authorization binding test policy",
        "execution_mode": "paper",
        "max_position_pct": 0.20,
        "max_total_exposure_pct": 0.80,
        "max_basket_pct": 0.80,
        "max_leveraged_etf_pct": 0.50,
        "min_cash_reserve_pct": 0.10,
        "max_order_value": 5_000.0,
        "max_open_orders": 5,
        "allow_new_positions": True,
        "whole_shares_only": True,
    }
    values.update(replacements)
    policy = TradingPolicy(**values)
    policy.validate()
    return policy


def _policy_gate_arguments(policy: TradingPolicy) -> dict:
    """Mirror the production policy-to-gate unit conversion exactly."""
    return {
        "max_position_pct": policy.max_position_pct,
        "max_total_exposure_pct": policy.max_total_exposure_pct,
        "max_basket_pct": policy.max_basket_pct * 100,
        "max_leveraged_etf_pct": policy.max_leveraged_etf_pct * 100,
        "max_stale_price_minutes": policy.max_stale_price_minutes,
        "max_slippage_pct": policy.max_slippage_pct,
        "max_spread_pct": policy.max_spread_pct,
        "earnings_blackout_days": policy.earnings_blackout_days,
        "max_order_value": policy.max_order_value,
        "min_cash_reserve_pct": policy.min_cash_reserve_pct,
        "whole_shares_only": policy.whole_shares_only,
    }


def _broker_account(*, account_id: str = _ACCOUNT_ID) -> dict:
    return {
        "account_id": account_id,
        "status": "ACTIVE",
        "equity": 10_000.0,
        "equity_decimal": "10000.00",
        "cash": 10_000.0,
        "cash_decimal": "10000.00",
        "buying_power": 10_000.0,
        "buying_power_decimal": "10000.00",
        "trading_blocked": False,
        "account_blocked": False,
        "trade_suspended_by_user": False,
        "transfers_blocked": False,
        "paper": True,
    }


def _pending_broker_order() -> dict:
    submitted = datetime.now(timezone.utc) - timedelta(seconds=2)
    return {
        "order_id": "pending-order-1",
        "client_order_id": "pending-client-1",
        "ticker": "BBB",
        "asset_class": "us_equity",
        "order_class": "simple",
        "extended_hours": False,
        "legs": None,
        "shares": 2.0,
        "shares_decimal": "2",
        "notional": None,
        "notional_decimal": None,
        "side": "buy",
        "type": "market",
        "limit_price": None,
        "limit_price_decimal": None,
        "time_in_force": "day",
        "status": "new",
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


class _CoherentAlpacaLikeSession:
    """Minimal stable paper session consumed by the real strict capturer."""

    PAPER_TRADING = True
    account_mode = "paper"

    def __init__(self, *, account_id: str, open_orders: list[dict]) -> None:
        self._account = _broker_account(account_id=account_id)
        self._open_orders = deepcopy(open_orders)
        self.calls: list[str] = []

    def get_account(self) -> dict:
        self.calls.append("account")
        return deepcopy(self._account)

    def get_open_orders(self) -> list[dict]:
        self.calls.append("orders")
        return deepcopy(self._open_orders)

    def get_open_positions(self) -> list[dict]:
        self.calls.append("positions")
        return []


def _strict_execution_portfolio(
    *,
    account_id: str = _ACCOUNT_ID,
    include_pending_order: bool = True,
):
    session = _CoherentAlpacaLikeSession(
        account_id=account_id,
        open_orders=[_pending_broker_order()] if include_pending_order else [],
    )
    snapshot = build_portfolio_snapshot_from_alpaca(
        broker_session=session,
        require_execution_coherence=True,
        expected_account_id=account_id,
    )
    assert session.calls == ["account", "orders", "positions", "orders", "account"]
    assert snapshot.broker_snapshot_id
    assert snapshot.broker_snapshot_material_json
    assert hashlib.sha256(
        snapshot.broker_snapshot_material_json.encode("utf-8")
    ).hexdigest() == snapshot.broker_snapshot_id
    return snapshot


def _context_for(snapshot, policy: TradingPolicy, **replacements):
    values = {
        "account_id": snapshot.account_id,
        "account_mode": snapshot.account_mode,
        "snapshot_id": snapshot.broker_snapshot_id,
        "policy_fingerprint": compute_policy_fingerprint(policy),
    }
    values.update(replacements)
    return ExecutionValidationContext(**values)


def _bound_evidence(*, policy: TradingPolicy | None = None):
    policy = policy or _paper_policy()
    snapshot = _strict_execution_portfolio()
    context = _context_for(snapshot, policy)
    return snapshot, policy, context


def _validate_bound(
    intent: TradeIntent,
    snapshot,
    policy: TradingPolicy,
    context: ExecutionValidationContext,
    **overrides,
):
    arguments = _policy_gate_arguments(policy)
    arguments.update(overrides)
    return validate_trade_intent(
        intent,
        snapshot,
        reference_price=60,
        now=_MARKET_OPEN,
        execution_context=context,
        execution_policy=policy,
        **arguments,
    )


def _approved_unbound():
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    validation = validate_trade_intent(
        intent,
        build_portfolio_snapshot([], cash=10_000),
        reference_price=60,
        now=_MARKET_OPEN,
    )
    assert validation.approved
    return intent, validation


def _approved_bound():
    snapshot, policy, context = _bound_evidence()
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    validation = _validate_bound(intent, snapshot, policy, context)
    assert validation.approved
    return intent, validation, snapshot, policy, context


def _bound_authorization():
    intent, validation, _snapshot, _policy, context = _approved_bound()
    return intent, authorize_trade_intent(intent, validation), context


def test_bound_authorization_verifies_for_its_full_context():
    intent, authorization, context = _bound_authorization()

    verify_execution_authorization(
        intent,
        authorization,
        expected_account_id=context.account_id,
        expected_account_mode=context.account_mode,
        expected_snapshot_id=context.snapshot_id,
        expected_policy_fingerprint=context.policy_fingerprint,
        require_bound=True,
    )


def test_after_fork_reset_rotates_secret_table_and_lock_and_invalidates_capability():
    """Platform-independent proof of the callback's complete child reset."""
    intent, authorization, _context = _bound_authorization()
    original_secret = execution_gate_module._GATE_SECRET
    original_tokens = execution_gate_module._consumed_authorization_tokens
    original_lock = execution_gate_module._consumed_authorization_tokens_lock
    try:
        execution_gate_module._reset_execution_authority_after_fork()
        assert execution_gate_module._GATE_SECRET != original_secret
        assert execution_gate_module._consumed_authorization_tokens == {}
        assert execution_gate_module._consumed_authorization_tokens is not original_tokens
        assert execution_gate_module._consumed_authorization_tokens_lock is not original_lock
        with pytest.raises(PermissionError, match="does not match"):
            verify_execution_authorization(intent, authorization, require_bound=True)
    finally:
        execution_gate_module._GATE_SECRET = original_secret
        execution_gate_module._consumed_authorization_tokens = original_tokens
        execution_gate_module._consumed_authorization_tokens_lock = original_lock


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork regression")
def test_pre_fork_authorization_is_invalid_in_child_and_parent_remains_usable():
    """A fork must not duplicate an HMAC authority or an inherited held lock."""
    intent, authorization, context = _bound_authorization()
    fork_context = multiprocessing.get_context("fork")
    parent_connection, child_connection = fork_context.Pipe(duplex=False)

    inherited_lock = execution_gate_module._consumed_authorization_tokens_lock
    inherited_lock.acquire()
    try:
        process = fork_context.Process(
            target=_verify_in_fork_child,
            args=(intent, authorization, child_connection),
        )
        process.start()
    finally:
        inherited_lock.release()
        child_connection.close()

    verify_execution_authorization(
        intent,
        authorization,
        expected_account_id=context.account_id,
        expected_account_mode=context.account_mode,
        expected_snapshot_id=context.snapshot_id,
        expected_policy_fingerprint=context.policy_fingerprint,
        require_bound=True,
    )
    assert parent_connection.poll(10), "fork child did not report authorization result"
    result = parent_connection.recv()
    parent_connection.close()
    process.join(timeout=10)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        pytest.fail("fork child hung on an inherited authorization lock")
    assert process.exitcode == 0
    assert result[0] == "refused"
    assert result[1] == "PermissionError"
    assert "does not match" in result[2]


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("account_id", "paper-account-2"),
        ("account_mode", "live"),
        ("snapshot_id", _OTHER_SNAPSHOT_ID),
        ("policy_fingerprint", _OTHER_POLICY_FINGERPRINT),
    ],
)
def test_each_execution_context_field_is_covered_by_the_signature(field, replacement):
    intent, authorization, _context = _bound_authorization()
    tampered = dataclasses.replace(authorization, **{field: replacement})

    with pytest.raises(PermissionError, match="does not match"):
        verify_execution_authorization(intent, tampered, require_bound=True)


def test_foreign_account_refusal_does_not_consume_the_authorization():
    intent, authorization, context = _bound_authorization()

    with pytest.raises(PermissionError, match="different broker account"):
        verify_execution_authorization(
            intent,
            authorization,
            expected_account_id="foreign-account",
            expected_account_mode="paper",
            require_bound=True,
        )

    verify_execution_authorization(
        intent,
        authorization,
        expected_account_id=context.account_id,
        expected_account_mode=context.account_mode,
        expected_snapshot_id=context.snapshot_id,
        expected_policy_fingerprint=context.policy_fingerprint,
        require_bound=True,
    )


def test_unbound_authorization_is_not_accepted_for_broker_dispatch():
    intent, validation = _approved_unbound()
    authorization = authorize_trade_intent(intent, validation)

    with pytest.raises(PermissionError, match="account-, snapshot-, and policy-bound"):
        verify_execution_authorization(intent, authorization, require_bound=True)


def test_bound_authorization_is_derived_from_signed_validation_context():
    intent, validation, _snapshot, _policy, context = _approved_bound()

    authorization = authorize_trade_intent(intent, validation)

    assert validation.execution_context is context
    assert authorization.account_id == context.account_id
    assert authorization.account_mode == context.account_mode
    assert authorization.snapshot_id == context.snapshot_id
    assert authorization.policy_fingerprint == context.policy_fingerprint


@pytest.mark.parametrize(
    "field,replacement,error",
    [
        ("account_id", "paper-account-2", "account_id"),
        ("account_mode", "live", "account_mode"),
        ("snapshot_id", _OTHER_SNAPSHOT_ID, "snapshot_id"),
    ],
)
def test_validation_refuses_context_for_different_portfolio_evidence(
    field, replacement, error
):
    snapshot, policy, context = _bound_evidence()
    mismatched_context = dataclasses.replace(context, **{field: replacement})
    intent = TradeIntent(ticker="KO", side="buy", shares=1)

    with pytest.raises(ValueError, match=error):
        _validate_bound(intent, snapshot, policy, mismatched_context)


def test_manual_portfolio_cannot_be_labeled_as_execution_evidence():
    snapshot, policy, context = _bound_evidence()
    assert snapshot.source == "alpaca"
    intent = TradeIntent(ticker="KO", side="buy", shares=1)

    with pytest.raises(ValueError, match="Alpaca execution snapshot"):
        _validate_bound(
            intent,
            build_portfolio_snapshot([], cash=10_000),
            policy,
            context,
        )


@pytest.mark.parametrize(
    "field,replacement,error",
    [
        ("captured_at", None, "capture time"),
        ("component_equity_exact", None, "component evidence"),
        ("cash_exact", None, "exact broker portfolio numerics"),
        ("open_orders_available", False, "active-order book"),
    ],
)
def test_execution_context_requires_untampered_strict_portfolio_evidence(
    field, replacement, error
):
    snapshot, policy, context = _bound_evidence()
    tampered = dataclasses.replace(snapshot, **{field: replacement})
    intent = TradeIntent(ticker="KO", side="buy", shares=1)

    with pytest.raises(ValueError, match=error):
        _validate_bound(intent, tampered, policy, context)


def test_retained_hash_snapshot_rejects_pending_order_removal():
    snapshot, policy, context = _bound_evidence()
    retained_id = snapshot.broker_snapshot_id
    retained_material = snapshot.broker_snapshot_material_json
    assert snapshot.open_orders

    snapshot.open_orders.clear()
    assert snapshot.broker_snapshot_id == retained_id
    assert snapshot.broker_snapshot_material_json == retained_material

    with pytest.raises(ValueError, match="active orders changed after capture"):
        _validate_bound(
            TradeIntent(ticker="KO", side="buy", shares=1),
            snapshot,
            policy,
            context,
        )


@pytest.mark.parametrize(
    "clock_offset,error",
    [
        (timedelta(minutes=1), "freshly captured"),
        (-timedelta(minutes=1), "future"),
    ],
)
def test_execution_context_refuses_stale_or_future_snapshot(
    monkeypatch, clock_offset, error
):
    snapshot, policy, context = _bound_evidence()
    real_datetime = datetime

    class ShiftedDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            shifted = real_datetime.now(timezone.utc) + clock_offset
            return shifted.replace(tzinfo=None) if tz is None else shifted.astimezone(tz)

    monkeypatch.setattr(execution_gate_module, "datetime", ShiftedDateTime)

    with pytest.raises(ValueError, match=error):
        _validate_bound(
            TradeIntent(ticker="KO", side="buy", shares=1),
            snapshot,
            policy,
            context,
        )


def test_weakened_policy_scalar_cannot_keep_the_real_policy_label():
    snapshot, policy, context = _bound_evidence()
    intent = TradeIntent(ticker="KO", side="buy", shares=1)

    with pytest.raises(ValueError, match="max_position_pct.*signed policy"):
        _validate_bound(
            intent,
            snapshot,
            policy,
            context,
            max_position_pct=1.0,
        )


def test_different_policy_object_cannot_keep_the_original_fingerprint():
    snapshot, policy, context = _bound_evidence()
    altered_policy = dataclasses.replace(policy, max_position_pct=0.30)
    altered_policy.validate()

    with pytest.raises(ValueError, match="policy fingerprint"):
        _validate_bound(
            TradeIntent(ticker="KO", side="buy", shares=1),
            snapshot,
            altered_policy,
            context,
        )


def test_authorizer_rejects_unbound_to_bound_promotion():
    intent, validation = _approved_unbound()
    snapshot, policy, context = _bound_evidence()
    assert snapshot.broker_snapshot_id == context.snapshot_id
    assert compute_policy_fingerprint(policy) == context.policy_fingerprint

    with pytest.raises(ValueError, match="cannot be promoted"):
        authorize_trade_intent(intent, validation, **dataclasses.asdict(context))


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("account_id", "paper-account-2"),
        ("account_mode", "live"),
        ("snapshot_id", _OTHER_SNAPSHOT_ID),
        ("policy_fingerprint", _OTHER_POLICY_FINGERPRINT),
    ],
)
def test_authorizer_rejects_relabeling_signed_validation_context(field, replacement):
    intent, validation, _snapshot, _policy, context = _approved_bound()
    asserted_binding = dataclasses.asdict(context)
    asserted_binding[field] = replacement

    with pytest.raises(ValueError, match="does not match the signed"):
        authorize_trade_intent(intent, validation, **asserted_binding)


def test_replacing_context_on_validation_invalidates_proof():
    intent, validation, _snapshot, _policy, context = _approved_bound()
    relabeled = dataclasses.replace(
        validation,
        execution_context=dataclasses.replace(context, account_id="paper-account-2"),
    )

    with pytest.raises(ValueError, match="was not produced by validate_trade_intent"):
        authorize_trade_intent(intent, relabeled)


def test_exact_explicit_binding_is_only_a_compatibility_assertion():
    intent, validation, _snapshot, _policy, context = _approved_bound()

    authorization = authorize_trade_intent(
        intent,
        validation,
        **dataclasses.asdict(context),
    )

    assert authorization.account_id == context.account_id


@pytest.mark.parametrize(
    "expected_field,wrong_value,error",
    [
        ("expected_snapshot_id", _OTHER_SNAPSHOT_ID, "different broker snapshot"),
        (
            "expected_policy_fingerprint",
            _OTHER_POLICY_FINGERPRINT,
            "different trading policy",
        ),
    ],
)
def test_expected_snapshot_and_policy_mismatch_do_not_consume_authorization(
    expected_field, wrong_value, error
):
    intent, authorization, context = _bound_authorization()

    with pytest.raises(PermissionError, match=error):
        verify_execution_authorization(
            intent,
            authorization,
            require_bound=True,
            **{expected_field: wrong_value},
        )

    verify_execution_authorization(
        intent,
        authorization,
        require_bound=True,
        expected_snapshot_id=context.snapshot_id,
        expected_policy_fingerprint=context.policy_fingerprint,
    )


@pytest.mark.parametrize(
    "missing",
    ["account_id", "account_mode", "snapshot_id", "policy_fingerprint"],
)
def test_authorizer_rejects_partial_execution_context(missing):
    intent, validation = _approved_unbound()
    binding = {
        "account_id": _ACCOUNT_ID,
        "account_mode": "paper",
        "snapshot_id": _OTHER_SNAPSHOT_ID,
        "policy_fingerprint": _OTHER_POLICY_FINGERPRINT,
    }
    binding[missing] = None

    with pytest.raises(ValueError, match="requires .* together"):
        authorize_trade_intent(intent, validation, **binding)


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_id", ""),
        ("account_id", " padded "),
        ("account_mode", "PAPER"),
        ("snapshot_id", "not-a-digest"),
        ("policy_fingerprint", "A" * 64),
    ],
)
def test_context_rejects_noncanonical_execution_fields(field, value):
    binding = {
        "account_id": _ACCOUNT_ID,
        "account_mode": "paper",
        "snapshot_id": _OTHER_SNAPSHOT_ID,
        "policy_fingerprint": _OTHER_POLICY_FINGERPRINT,
    }
    binding[field] = value

    with pytest.raises(ValueError):
        ExecutionValidationContext(**binding)


def test_digest_with_python_integer_underscore_syntax_is_rejected():
    digest_with_underscore = "a" * 31 + "_" + "b" * 32
    assert len(digest_with_underscore) == 64

    with pytest.raises(ValueError, match="lowercase 64-character sha256"):
        ExecutionValidationContext(
            account_id=_ACCOUNT_ID,
            account_mode="paper",
            snapshot_id=digest_with_underscore,
            policy_fingerprint=_OTHER_POLICY_FINGERPRINT,
        )


def test_execution_validation_context_is_frozen():
    _snapshot, _policy, context = _bound_evidence()

    with pytest.raises(dataclasses.FrozenInstanceError):
        context.account_id = "paper-account-2"


def test_validate_trade_intent_rejects_untyped_execution_context():
    intent = TradeIntent(ticker="KO", side="buy", shares=1)

    with pytest.raises(TypeError, match="ExecutionValidationContext"):
        validate_trade_intent(
            intent,
            build_portfolio_snapshot([], cash=10_000),
            reference_price=60,
            now=_MARKET_OPEN,
            execution_context={"account_id": _ACCOUNT_ID},
        )


def test_override_authorization_derives_same_signed_context():
    policy = _paper_policy(max_position_pct=0.01)
    snapshot, policy, context = _bound_evidence(policy=policy)
    intent = TradeIntent(ticker="KO", side="buy", shares=2)
    validation = _validate_bound(intent, snapshot, policy, context)
    assert not validation.approved
    assert validation.overridable

    authorization = authorize_overridden_trade_intent(intent, validation)

    assert authorization.account_id == context.account_id
    assert authorization.snapshot_id == context.snapshot_id
    assert authorization.policy_fingerprint == context.policy_fingerprint


def test_override_authorizer_rejects_unbound_to_bound_promotion():
    intent = TradeIntent(ticker="KO", side="buy", shares=100)
    validation = validate_trade_intent(
        intent,
        build_portfolio_snapshot([], cash=10_000),
        reference_price=60,
        now=_MARKET_OPEN,
        max_position_pct=0.01,
        max_total_exposure_pct=1.0,
    )
    assert not validation.approved
    assert validation.overridable
    _snapshot, _policy, context = _bound_evidence()

    with pytest.raises(ValueError, match="cannot be promoted"):
        authorize_overridden_trade_intent(
            intent,
            validation,
            **dataclasses.asdict(context),
        )
