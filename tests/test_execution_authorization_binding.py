from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime

import pytest

from assistant.portfolio_snapshot import build_portfolio_snapshot
from risk.execution_gate import (
    TradeIntent,
    authorize_trade_intent,
    validate_trade_intent,
    verify_execution_authorization,
)


_MARKET_OPEN = datetime(2026, 7, 27, 10, 0)
_SNAPSHOT_ID = hashlib.sha256(b"snapshot").hexdigest()
_POLICY_FINGERPRINT = hashlib.sha256(b"policy").hexdigest()


def _approved_intent_and_validation():
    intent = TradeIntent(ticker="KO", side="buy", shares=1)
    portfolio = build_portfolio_snapshot([], cash=10_000)
    validation = validate_trade_intent(
        intent,
        portfolio,
        reference_price=60,
        now=_MARKET_OPEN,
    )
    assert validation.approved
    return intent, validation


def _bound_authorization():
    intent, validation = _approved_intent_and_validation()
    authorization = authorize_trade_intent(
        intent,
        validation,
        account_id="paper-account-1",
        account_mode="paper",
        snapshot_id=_SNAPSHOT_ID,
        policy_fingerprint=_POLICY_FINGERPRINT,
    )
    return intent, authorization


def test_bound_authorization_verifies_only_for_its_account_and_mode():
    intent, authorization = _bound_authorization()

    verify_execution_authorization(
        intent,
        authorization,
        expected_account_id="paper-account-1",
        expected_account_mode="paper",
        require_bound=True,
    )


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("account_id", "paper-account-2"),
        ("account_mode", "live"),
        ("snapshot_id", hashlib.sha256(b"other-snapshot").hexdigest()),
        ("policy_fingerprint", hashlib.sha256(b"other-policy").hexdigest()),
    ],
)
def test_each_execution_context_field_is_covered_by_the_signature(
    field, replacement
):
    intent, authorization = _bound_authorization()
    tampered = dataclasses.replace(authorization, **{field: replacement})

    with pytest.raises(PermissionError, match="does not match"):
        verify_execution_authorization(intent, tampered, require_bound=True)


def test_foreign_account_refusal_does_not_consume_the_authorization():
    intent, authorization = _bound_authorization()

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
        expected_account_id="paper-account-1",
        expected_account_mode="paper",
        require_bound=True,
    )


def test_unbound_authorization_is_not_accepted_for_broker_dispatch():
    intent, validation = _approved_intent_and_validation()
    authorization = authorize_trade_intent(intent, validation)

    with pytest.raises(PermissionError, match="account-, snapshot-, and policy-bound"):
        verify_execution_authorization(
            intent,
            authorization,
            require_bound=True,
        )


@pytest.mark.parametrize(
    "missing",
    ["account_id", "account_mode", "snapshot_id", "policy_fingerprint"],
)
def test_authorizer_rejects_partial_execution_context(missing):
    intent, validation = _approved_intent_and_validation()
    binding = {
        "account_id": "paper-account-1",
        "account_mode": "paper",
        "snapshot_id": _SNAPSHOT_ID,
        "policy_fingerprint": _POLICY_FINGERPRINT,
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
def test_authorizer_rejects_noncanonical_execution_context(field, value):
    intent, validation = _approved_intent_and_validation()
    binding = {
        "account_id": "paper-account-1",
        "account_mode": "paper",
        "snapshot_id": _SNAPSHOT_ID,
        "policy_fingerprint": _POLICY_FINGERPRINT,
    }
    binding[field] = value

    with pytest.raises(ValueError):
        authorize_trade_intent(intent, validation, **binding)
