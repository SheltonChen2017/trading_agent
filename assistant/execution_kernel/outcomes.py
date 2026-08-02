"""Broker outcome interpretation.

GR-1A extraction from ``assistant/execution_service.py``. Behaviour is
unchanged: these functions were moved verbatim and are re-exported from
``assistant.execution_service``, so every existing caller and test keeps
working through its original import path.

This is outcome INTERPRETATION only -- deciding what the broker's answer
means. It never submits, claims, or transitions a proposal. The sentinel
``LOOKUP_UNCONFIRMED`` is the reason the module exists: "the broker says no
order" and "we could not ask the broker" are different answers, and
collapsing them would let a failed lookup be read as durable proof of
absence.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from assistant.order_lifecycle import (
    CHAIN_ERROR_IDENTITY_MISMATCH,
    resolve_replacement_chain,
)
from assistant.proposal_status import BROKER_ABSENCE_GRACE_SECONDS
from risk.execution_gate import TradeIntent

# Distinct from None: None means the broker answered "no such order",
# this means the question could not be asked.
LOOKUP_UNCONFIRMED = object()
_LOOKUP_UNCONFIRMED = LOOKUP_UNCONFIRMED


def _broker_absence_is_old_enough(claimed: dict, *, now: datetime) -> bool:
    """Whether a just-claimed unresolved state is old enough to trust a 404.

    ``claim_proposal`` returns the prior row timestamp from inside its write
    transaction. Using that value avoids a read/claim race, while keeping the
    metadata transient rather than adding it to the persisted proposal schema.
    """
    raw = claimed.get("_claimed_from_updated_at")
    if not raw:
        return False
    try:
        started = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return now - started >= timedelta(seconds=BROKER_ABSENCE_GRACE_SECONDS)


def _lookup_order_outcome(broker_module, idempotency_key: str):
    """Classifies a broker order lookup into exactly one of three
    outcomes: the order dict (found), None (the broker returned 404), or
    _LOOKUP_UNCONFIRMED (the lookup itself failed -- still don't know).
    Callers must branch on all three, and must not treat a new 404 as
    durable proof of absence before the broker-indexing grace period."""
    try:
        return broker_module.find_order_by_client_id(idempotency_key)
    except Exception:
        return _LOOKUP_UNCONFIRMED


def _order_matches_intent(order: dict, intent: TradeIntent) -> tuple[bool, str]:
    """Verifies the COMPLETE material identity of a broker order (as
    returned by execution.alpaca_broker.find_order_by_client_id()) against
    the TradeIntent it's being reconciled against: ticker, side, shares,
    order type, and (for limit orders) limit price. A missing material
    field fails closed -- treated as a mismatch, never assumed to match
    (GPT review, 2026-07-28: a prior version compared only ticker+side, so
    an order under the expected idempotency key for BUY 1 AAPL could
    reconcile a proposal for BUY 100 AAPL, or a market order could be
    mistaken for a limit order). Returns (matches, detail); `detail`
    explains the first mismatch found, for an audit message -- empty
    string when matches is True.

    Share counts use a numeric (not string) comparison so numerically-
    equivalent representations (10 vs 10.0) count as equal; a fractional
    share count is still rejected since this workflow only ever submits
    whole-share orders.
    """
    if str(order.get("ticker", "")).upper() != intent.ticker.upper():
        return False, f"ticker: expected {intent.ticker.upper()!r}, got {order.get('ticker')!r}"
    if order.get("side") != intent.side:
        return False, f"side: expected {intent.side!r}, got {order.get('side')!r}"

    order_shares = order.get("shares")
    if order_shares is None:
        return False, "shares: missing from broker response"
    try:
        order_shares_value = float(order_shares)
    except (TypeError, ValueError):
        return False, f"shares: not numeric ({order_shares!r})"
    if not math.isclose(order_shares_value, float(intent.shares), rel_tol=0.0, abs_tol=1e-9):
        return False, f"shares: expected {intent.shares}, got {order_shares_value}"

    order_type = order.get("type")
    if order_type is None:
        return False, "order type: missing from broker response"
    if str(order_type).lower() != str(intent.order_type).lower():
        return False, f"order type: expected {intent.order_type!r}, got {order_type!r}"

    if intent.order_type == "limit":
        order_limit_price = order.get("limit_price")
        if order_limit_price is None:
            return False, "limit_price: missing from broker response for a limit order"
        try:
            order_limit_price_value = float(order_limit_price)
        except (TypeError, ValueError):
            return False, f"limit_price: not numeric ({order_limit_price!r})"
        if intent.limit_price is None or not math.isclose(
            order_limit_price_value, float(intent.limit_price), rel_tol=0.0, abs_tol=0.005
        ):
            return False, f"limit_price: expected {intent.limit_price}, got {order_limit_price_value}"

    return True, ""


def _authoritative_order_for(
    broker_module, order: dict, intent: TradeIntent
) -> tuple[dict | None, str | None, bool, tuple[str, ...]]:
    """
    Resolve a looked-up order through its replacement chain.

    Returns `(authoritative_order, error, is_identity_mismatch, chain)`.

    Both of this module's broker-lookup consumers need this:
    reconcile_submission() (the user-facing manual operation) and
    submit_approved_proposal()'s post-exception recovery. Neither followed
    `replaced_by`, so each validated and journaled the SUPERSEDED order --
    and because the original order still matches the stored intent (only its
    status is "replaced"), the identity check passed and nothing looked wrong.
    A human could re-run manual reconciliation indefinitely and stay pinned to
    a dead order while its replacement had already filled (independent review,
    2026-07-29, reproduced: returned order-1, status submission_unknown, zero
    replacement lookups).

    Delegates to order_lifecycle.resolve_replacement_chain() -- the same
    resolver startup polling uses, deliberately not a second implementation --
    injecting _order_matches_intent so EVERY hop is validated, not just the
    final order.
    """
    resolution = resolve_replacement_chain(
        order,
        # Lazy for the same reason as order_reconciler's adapter: never touch
        # get_order_by_id unless a replacement actually has to be fetched.
        lambda oid: broker_module.get_order_by_id(oid),
        validate=lambda candidate: _order_matches_intent(candidate, intent),
    )
    if resolution.error is not None:
        return (
            None,
            resolution.error,
            resolution.error_kind == CHAIN_ERROR_IDENTITY_MISMATCH,
            resolution.chain,
        )
    return resolution.authoritative_order, None, False, resolution.chain
