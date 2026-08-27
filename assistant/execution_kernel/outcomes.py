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

from datetime import datetime, timedelta, timezone

from assistant.execution_kernel.broker_evidence import (
    canonical_order_for_proposal,
    observed_broker_account,
    validate_order_for_proposal,
)
from assistant.execution_kernel.errors import ProposalExecutionError
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


def _order_matches_intent(
    order: dict,
    intent: TradeIntent,
    *,
    proposal: dict | None = None,
    observed_account=None,
    root_order: bool = True,
    expected_replaces_order_id: str | None = None,
) -> tuple[bool, str]:
    """Compatibility verdict backed by the single strict broker boundary.

    A two-argument material-only comparison is no longer sufficient for an
    execution decision: it cannot prove client identity, account/mode, TIF,
    status/fill invariants, timestamps, or exact/legacy numeric agreement.
    Production callers therefore provide the durable proposal and observed
    account.  Missing context returns a mismatch rather than silently falling
    back to the former loose comparison.
    """
    if proposal is None or observed_account is None:
        return False, "strict broker proposal/account context is required"
    try:
        validate_order_for_proposal(
            order,
            intent,
            proposal,
            observed_account=observed_account,
            root_order=root_order,
            expected_replaces_order_id=expected_replaces_order_id,
        )
    except Exception as exc:
        return False, str(exc)
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
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise ProposalExecutionError(
            f"Submission outcome for unknown proposal {proposal_id} cannot be reconciled."
        ) from exc
    try:
        observed_account = observed_broker_account(broker_module)
    except Exception as account_exc:
        reason = (
            f"Order submission raised ({exc}), and the frozen broker session's "
            f"account identity could not be re-verified: {account_exc}. Persistent "
            "kill switch activated; the broker outcome remains ambiguous."
        )
        store.park_reconciliation_anomaly_and_halt(
            proposal_id,
            expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
            reason=reason,
            reconciled_at=datetime.now(timezone.utc).isoformat(),
            details={"path": "submit_lookup_account_binding"},
            anomaly_key="failed_submission_account_binding",
        )
        raise ProposalExecutionError(reason) from account_exc

    outcome = _lookup_order_outcome(broker_module, idempotency_key)
    if isinstance(outcome, dict):
        try:
            root_order = canonical_order_for_proposal(
                outcome,
                intent,
                proposal,
                observed_account=observed_account,
                root_order=True,
            )
        except Exception as evidence_exc:
            mismatch_detail = str(evidence_exc)
            # An order exists under our exact idempotency key but does
            # NOT match what we submitted -- never auto-resolve this;
            # it's exactly the anomaly duplicate-order protection
            # exists to catch (GPT review, 2026-07-28).
            reason = (
                f"Order submission raised ({exc}), and the order found under this idempotency "
                f"key does NOT match the intent (mismatch: {mismatch_detail}) -- refusing to "
                "auto-resolve. Persistent kill switch activated; investigate manually."
            )
            store.park_reconciliation_anomaly_and_halt(
                proposal_id,
                expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
                reason=reason,
                reconciled_at=datetime.now(timezone.utc).isoformat(),
                details={"mismatch": mismatch_detail, "path": "submit_lookup"},
                anomaly_key="failed_submission_lookup_identity_mismatch",
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
        (
            authoritative,
            chain_error,
            is_mismatch,
            chain,
            replacement_order_path,
        ) = _authoritative_order_for(
            broker_module,
            root_order,
            intent,
            proposal=proposal,
            observed_account=observed_account,
        )
        if chain_error is not None:
            reason = (
                f"Order submission raised ({exc}), and the replacement chain for the order found "
                f"under this idempotency key could not be trusted: {chain_error}. "
                + ("Persistent kill switch activated; investigate manually."
                   if is_mismatch else "Left retryable as 'submission_unknown'.")
            )
            if is_mismatch:
                store.park_reconciliation_anomaly_and_halt(
                    proposal_id,
                    expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
                    reason=reason,
                    reconciled_at=datetime.now(timezone.utc).isoformat(),
                    details={"path": "submit_replacement_chain"},
                    anomaly_key=(
                        "failed_submission_replacement_chain_identity_mismatch"
                    ),
                )
            else:
                store.update_proposal_status_if_current(
                    proposal_id,
                    expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
                    new_status=SUBMISSION_UNKNOWN,
                    error=reason,
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
            broker_order_root_id=(
                replacement_order_path[0] if replacement_order_path else None
            ),
            replacement_order_path=replacement_order_path,
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
    broker_module,
    order: dict,
    intent: TradeIntent,
    *,
    proposal: dict,
    observed_account,
) -> tuple[
    dict | None,
    str | None,
    bool,
    tuple[str, ...],
    tuple[str, ...],
]:
    """
    Resolve a looked-up order through its replacement chain.

    Returns `(authoritative_order, error, is_identity_mismatch, chain,
    replacement_order_path)`.  The final path is the durable root-to-current
    broker-order identity used by the event journal; it is distinct from the
    diagnostic replacement-chain trace.

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
        validate=lambda candidate: _order_matches_intent(
            candidate,
            intent,
            proposal=proposal,
            observed_account=observed_account,
            root_order=False,
        ),
    )
    if resolution.error is not None:
        return (
            None,
            resolution.error,
            resolution.error_kind == CHAIN_ERROR_IDENTITY_MISMATCH,
            resolution.chain,
            resolution.order_path,
        )
    assert resolution.authoritative_order is not None
    try:
        canonical = canonical_order_for_proposal(
            resolution.authoritative_order,
            intent,
            proposal,
            observed_account=observed_account,
            root_order=not resolution.followed_a_replacement,
        )
    except Exception as exc:
        return None, str(exc), True, resolution.chain, resolution.order_path
    return canonical, None, False, resolution.chain, resolution.order_path
