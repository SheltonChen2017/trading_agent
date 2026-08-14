"""Broker outcome interpretation and failed-submission resolution.

GR-1A extracted the pure lookup and identity helpers from
``assistant/execution_service.py``. GR-1B added the durable resolution of a
raising submit call behind the same unchanged facade.

This module never submits or claims a proposal. Its pure helpers decide what
the broker's answer means; ``resolve_failed_submission`` then projects that
answer into durable proposal, journal, reservation-hold, and kill-switch state.
The sentinel ``_LOOKUP_UNCONFIRMED`` is the reason the module exists: "the
broker says no order" and "we could not ask the broker" are different answers,
and collapsing them would let a failed lookup be read as durable proof of
absence.
"""
from __future__ import annotations

import math
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from assistant.execution_kernel.errors import ProposalExecutionError
from assistant.money import decimal_or_none
from assistant.order_lifecycle import (
    CHAIN_ERROR_IDENTITY_MISMATCH,
    journal_broker_order_update,
    resolve_replacement_chain,
)
from assistant.proposal_status import (
    BROKER_ABSENCE_GRACE_SECONDS,
    RECONCILING,
    SUBMISSION_UNKNOWN,
    SUBMITTING,
)
from assistant.storage import AssistantStore
from risk.execution_gate import TradeIntent

# Distinct from None: None means the broker answered "no such order",
# this means the question could not be asked.
_LOOKUP_UNCONFIRMED = object()


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

    Share counts use exact Decimal comparison so numerically-equivalent
    representations (10 vs 10.0) count as equal without a tolerance that
    could accept a one-nanoshare identity mismatch.
    """
    if str(order.get("ticker", "")).upper() != intent.ticker.upper():
        return False, f"ticker: expected {intent.ticker.upper()!r}, got {order.get('ticker')!r}"
    if order.get("side") != intent.side:
        return False, f"side: expected {intent.side!r}, got {order.get('side')!r}"

    order_shares = order.get("shares_decimal", order.get("shares"))
    if order_shares is None:
        return False, "shares: missing from broker response"
    order_shares_value = decimal_or_none(order_shares)
    intent_shares_value = decimal_or_none(intent.shares)
    if order_shares_value is None or intent_shares_value is None:
        return False, f"shares: not numeric ({order_shares!r})"
    if order_shares_value != intent_shares_value:
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


def resolve_failed_submission(
    broker_module,
    store: AssistantStore,
    proposal_id: str,
    idempotency_key: str,
    intent: TradeIntent,
    exc: Exception,
) -> dict:
    """Decide what a raising submit actually meant, and never guess.

    GR-1B extraction, moved verbatim from
    ``execute_approved_paper_proposal``'s submission handler.

    An exception at submit does NOT prove the broker rejected the order --
    a network timeout, for example, can lose the response after the order
    was actually accepted. Reconcile by looking the order up under the same
    idempotency key (client_order_id) before concluding anything -- and
    distinguish a 404 from a failed lookup without trusting a new 404
    before the indexing grace period (see ``_lookup_order_outcome``).

    Returns the order dict to hand back to the caller, or raises
    ``ProposalExecutionError``. Every raising path leaves the proposal in
    ``submission_unknown`` with its reservation still held: budget is
    released only once absence is genuinely confirmed, which happens in
    delayed reconciliation, not here.
    """
    outcome = _lookup_order_outcome(broker_module, idempotency_key)
    if isinstance(outcome, dict):
        matches, mismatch_detail = _order_matches_intent(outcome, intent)
        if not matches:
            # An order exists under our exact idempotency key but does
            # NOT match what we submitted -- never auto-resolve this;
            # it's exactly the anomaly duplicate-order protection
            # exists to catch (GPT review, 2026-07-28).
            reason = (
                f"Order submission raised ({exc}), and the order found under this idempotency "
                f"key does NOT match the intent (mismatch: {mismatch_detail}) -- refusing to "
                "auto-resolve. Persistent kill switch activated; investigate manually."
            )
            store.update_proposal_status_if_current(
                proposal_id,
                expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
                new_status=SUBMISSION_UNKNOWN,
                error=reason,
            )
            store.activate_reconciliation_halt(
                proposal_id=proposal_id,
                reason=reason,
                details={"mismatch": mismatch_detail, "path": "submit_lookup"},
            )
            raise ProposalExecutionError(
                f"Order submission failed for {proposal_id}, and a MISMATCHED order was found "
                f"under this idempotency key ({mismatch_detail}) -- left as 'submission_unknown' "
                "for manual investigation, not auto-resolved."
            ) from exc
        # Same replacement-chain resolution as manual reconciliation: the
        # order found under our idempotency key could already have been
        # replaced out of band between the failed submit and this lookup.
        # Narrower window than reconcile_submission()'s, but the identical
        # defect -- journaling a superseded order as the outcome.
        authoritative, chain_error, is_mismatch, chain = _authoritative_order_for(
            broker_module, outcome, intent
        )
        if chain_error is not None:
            reason = (
                f"Order submission raised ({exc}), and the replacement chain for the order found "
                f"under this idempotency key could not be trusted: {chain_error}. "
                + ("Persistent kill switch activated; investigate manually."
                   if is_mismatch else "Left retryable as 'submission_unknown'.")
            )
            store.update_proposal_status_if_current(
                proposal_id,
                expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
                new_status=SUBMISSION_UNKNOWN,
                error=reason,
            )
            if is_mismatch:
                store.activate_reconciliation_halt(
                    proposal_id=proposal_id,
                    reason=reason,
                    details={"path": "submit_replacement_chain"},
                )
            raise ProposalExecutionError(reason) from exc

        journal_broker_order_update(
            store,
            proposal_id,
            authoritative,
            event_type="submission_reconciled",
            clear_error=True,
            extra_updates={"reconciled_after_error": str(exc)},
            raw_event={"replacement_chain": list(chain)} if chain else None,
        )
        return authoritative
    if outcome is None:
        # A 404 immediately after a timeout is not durable proof that the
        # order was never accepted: the response may have been lost before
        # the broker indexed client_order_id. Keep the reservation and the
        # duplicate-intent slot until delayed reconciliation observes
        # absence after the shared grace period.
        unresolved = store.update_proposal_status_if_current(
            proposal_id,
            expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
            new_status=SUBMISSION_UNKNOWN,
            error=(
                f"Submission raised ({exc}); an immediate broker lookup found no matching "
                "order, but absence is not trusted until the broker-indexing grace period "
                "has elapsed. Reconcile again later."
            ),
        )
        if unresolved is None:
            current = store.get_proposal(proposal_id)
            if current is not None and current.get("broker_order"):
                return current["broker_order"]
        raise ProposalExecutionError(
            f"Could not confirm whether the order for {proposal_id} was accepted after "
            f"the submission error ({exc}). The immediate lookup found no order, but the "
            "broker-indexing grace period has not elapsed; status is 'submission_unknown' "
            "and its execution reservation remains held. Reconcile again later."
        ) from exc
    unresolved = store.update_proposal_status_if_current(
        proposal_id,
        expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
        new_status=SUBMISSION_UNKNOWN,
        error=str(exc),
    )
    if unresolved is None:
        current = store.get_proposal(proposal_id)
        if current is not None and current.get("broker_order"):
            return current["broker_order"]
    raise ProposalExecutionError(
        f"Could not confirm whether the order for {proposal_id} was accepted by the broker "
        f"after an error ({exc}). Status is 'submission_unknown' -- run "
        f"`reconcile_submission({proposal_id!r}, store)` (CLI: `reconcile {proposal_id}`) once "
        "connectivity is restored; this ticker/side is treated as a duplicate-order risk until then."
    ) from exc


def _authoritative_order_for(
    broker_module, order: dict, intent: TradeIntent
) -> tuple[dict | None, str | None, bool, tuple[str, ...]]:
    """
    Resolve a looked-up order through its replacement chain.

    Returns `(authoritative_order, error, is_identity_mismatch, chain)`.

    Both of this module's broker-lookup consumers need this:
    reconcile_submission() (the user-facing manual operation) and
    execute_approved_paper_proposal()'s post-exception recovery. Neither followed
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
