"""Strict, account-bound broker evidence used by every lifecycle ingress.

The provider's order mapping is untrusted external evidence.  This module
reconstructs the immutable account and intent expectations recorded before
dispatch, applies :mod:`execution.broker_contract`, and returns a fresh
canonical mapping.  Callers must journal only that returned mapping.

Keeping this logic separate from submission/reconciliation orchestration is
intentional: a normal submit response, an idempotency lookup, polling, a
stream event, and a replacement hop must not grow five subtly different
definitions of "the order we authorized".
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from execution.broker_contract import (
    BrokerAccountIdentity,
    BrokerOrderValidationContext,
    ValidatedBrokerOrder,
    validate_broker_order,
    validated_broker_order_mapping,
)
from risk.execution_gate import TradeIntent


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class DurableBrokerExecutionContext:
    """The broker authority persisted before the first contact attempt."""

    account: BrokerAccountIdentity
    snapshot_id: str
    policy_fingerprint: str


def durable_broker_context(proposal: Mapping[str, Any]) -> DurableBrokerExecutionContext:
    """Load and strictly validate a proposal's persisted broker binding.

    Proposals created before this binding existed cannot safely prove which
    account a later broker lookup observed.  They therefore fail closed here;
    migration must be an explicit operator decision, never an inference from
    mutable credentials or a returned order.
    """
    if not isinstance(proposal, Mapping):
        raise ValueError("proposal must be a mapping")
    raw = proposal.get("broker_execution_context")
    if not isinstance(raw, Mapping):
        raise ValueError(
            "proposal lacks durable broker_execution_context; broker evidence "
            "cannot be attributed safely"
        )
    account = BrokerAccountIdentity(
        account_id=raw.get("account_id"),  # type: ignore[arg-type]
        account_mode=raw.get("account_mode"),  # type: ignore[arg-type]
    )
    snapshot_id = raw.get("snapshot_id")
    policy_fingerprint = raw.get("policy_fingerprint")
    if not isinstance(snapshot_id, str) or _SHA256_RE.fullmatch(snapshot_id) is None:
        raise ValueError(
            "broker_execution_context.snapshot_id must be a lowercase SHA-256 digest"
        )
    if (
        not isinstance(policy_fingerprint, str)
        or _SHA256_RE.fullmatch(policy_fingerprint) is None
    ):
        raise ValueError(
            "broker_execution_context.policy_fingerprint must be a lowercase "
            "SHA-256 digest"
        )
    return DurableBrokerExecutionContext(
        account=account,
        snapshot_id=snapshot_id,
        policy_fingerprint=policy_fingerprint,
    )


def observed_broker_account(broker: Any) -> BrokerAccountIdentity:
    """Read the exact account identity from one frozen broker session."""
    if getattr(broker, "account_mode", None) not in {"paper", "live"}:
        raise ValueError(
            "broker reconciliation requires one account-scoped broker session"
        )
    get_account = getattr(broker, "get_account", None)
    if not callable(get_account):
        raise ValueError("broker session cannot report its account identity")
    account = get_account()
    if not isinstance(account, Mapping):
        raise ValueError("broker account evidence must be a mapping")
    paper = account.get("paper")
    if type(paper) is not bool:
        raise ValueError("broker account paper-mode evidence must be an actual bool")
    mode = "paper" if paper else "live"
    if mode != broker.account_mode:
        raise ValueError("broker session mode disagrees with its account evidence")
    return BrokerAccountIdentity(
        account_id=account.get("account_id"),  # type: ignore[arg-type]
        account_mode=mode,
    )


def assert_expected_broker_account(
    proposal: Mapping[str, Any],
    observed_account: BrokerAccountIdentity,
) -> DurableBrokerExecutionContext:
    """Prove a session is observing the proposal's recorded account."""
    if not isinstance(observed_account, BrokerAccountIdentity):
        raise TypeError("observed_account must be BrokerAccountIdentity")
    context = durable_broker_context(proposal)
    if observed_account != context.account:
        raise ValueError(
            "observed broker account/mode does not match the proposal's durable "
            "execution context"
        )
    return context


def durable_root_order_id(proposal: Mapping[str, Any]) -> object | None:
    """Return the broker ID that later root observations must preserve.

    New lifecycle projections persist ``broker_order_root_id`` atomically with
    the first broker observation.  For a legacy proposal whose current order
    is itself the unreplaced root, the current order ID is an equivalent safe
    fallback.  A legacy replacement is deliberately not guessed from its
    current ID: its original root must be recovered from durable lineage.

    The return type stays ``object`` so malformed persisted values reach the
    strict broker contract and fail as ``invalid_validation_expectation``
    instead of being silently treated as absent.
    """
    if not isinstance(proposal, Mapping):
        raise ValueError("proposal must be a mapping")
    if "broker_order_root_id" in proposal:
        return proposal.get("broker_order_root_id")
    current = proposal.get("broker_order")
    if isinstance(current, Mapping) and current.get("replaces") is None:
        return current.get("order_id")
    return None


def validate_order_for_proposal(
    order: Mapping[str, Any],
    intent: TradeIntent,
    proposal: Mapping[str, Any],
    *,
    observed_account: BrokerAccountIdentity,
    root_order: bool,
    expected_replaces_order_id: str | None = None,
) -> ValidatedBrokerOrder:
    """Validate one root or replacement order against durable expectations."""
    context = assert_expected_broker_account(proposal, observed_account)
    idempotency_key = proposal.get("idempotency_key")
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise ValueError("proposal has no usable idempotency_key")
    if not isinstance(intent, TradeIntent):
        raise TypeError("intent must be TradeIntent")
    expected_order_id = durable_root_order_id(proposal) if root_order else None
    return validate_broker_order(
        order,
        context=BrokerOrderValidationContext(
            expected_account=context.account,
            observed_account=observed_account,
            expected_order_id=expected_order_id,  # type: ignore[arg-type]
            expected_client_order_id=(idempotency_key if root_order else None),
            require_client_order_id=True,
            expected_replaces_order_id=expected_replaces_order_id,
            expected_ticker=intent.ticker,
            expected_side=intent.side,
            expected_order_type=intent.order_type,
            expected_quantity=intent.shares,
            expected_limit_price=(
                intent.limit_price if intent.order_type == "limit" else None
            ),
            require_exact_numerics=True,
        ),
    )


def canonical_order_for_proposal(
    order: Mapping[str, Any],
    intent: TradeIntent,
    proposal: Mapping[str, Any],
    *,
    observed_account: BrokerAccountIdentity,
    root_order: bool,
    expected_replaces_order_id: str | None = None,
) -> dict[str, Any]:
    """Return only the canonical mapping safe for lifecycle projection."""
    return validated_broker_order_mapping(
        validate_order_for_proposal(
            order,
            intent,
            proposal,
            observed_account=observed_account,
            root_order=root_order,
            expected_replaces_order_id=expected_replaces_order_id,
        )
    )


__all__ = [
    "DurableBrokerExecutionContext",
    "assert_expected_broker_account",
    "canonical_order_for_proposal",
    "durable_broker_context",
    "durable_root_order_id",
    "observed_broker_account",
    "validate_order_for_proposal",
]
