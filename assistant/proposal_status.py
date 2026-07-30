"""
Single source of truth for trade-proposal lifecycle statuses.

Previously these strings were duplicated (and drifted) across
execution_service.py, the UI's History filter, README.md, and tests --
GPT's review flagged that the UI filter dropdown was missing three
statuses the service had started emitting (validating, validation_failed,
submission_failed), plus a stale "rejected" status that no code path had
ever actually written. Import STATUSES here everywhere a status list is
needed instead of re-typing one.
"""
from __future__ import annotations

PROPOSED = "proposed"
VALIDATING = "validating"
POLICY_OVERRIDE_AVAILABLE = "override_available"
BLOCKED = "blocked"
VALIDATION_FAILED = "validation_failed"
APPROVED = "approved"
SUBMITTING = "submitting"
SUBMISSION_UNKNOWN = "submission_unknown"
SUBMISSION_FAILED = "submission_failed"
RECONCILING = "reconciling"
# Broker acceptance is not execution. These states mirror the broker's
# post-submission lifecycle and remain nonterminal until a fill, rejection,
# cancellation, or expiry is confirmed.
BROKER_ACCEPTED = "broker_accepted"
PARTIALLY_FILLED = "partially_filled"
CANCEL_PENDING = "cancel_pending"
FILLED = "filled"
CANCELED = "canceled"
BROKER_REJECTED = "broker_rejected"
BROKER_EXPIRED = "broker_expired"
# Legacy rows created before fill-aware lifecycle tracking used "executed"
# to mean only "the broker accepted the request." Keep the value readable
# for migration/reconciliation, but never emit it for a new submission.
EXECUTED = "executed"
EXPIRED = "expired"

# Ordered roughly by where a proposal sits in its lifecycle.
STATUSES: tuple[str, ...] = (
    PROPOSED,
    VALIDATING,
    POLICY_OVERRIDE_AVAILABLE,
    BLOCKED,
    VALIDATION_FAILED,
    APPROVED,
    SUBMITTING,
    SUBMISSION_UNKNOWN,
    RECONCILING,
    SUBMISSION_FAILED,
    BROKER_ACCEPTED,
    PARTIALLY_FILLED,
    CANCEL_PENDING,
    FILLED,
    CANCELED,
    BROKER_REJECTED,
    BROKER_EXPIRED,
    EXECUTED,
    EXPIRED,
)

# Statuses where a broker order may exist (or might exist) even though the
# proposal hasn't reached a clean terminal state -- used to widen the
# duplicate-order check so a regenerated proposal for the same
# ticker/side is blocked until an unresolved submission is reconciled.
UNRESOLVED_BROKER_STATE_STATUSES: tuple[str, ...] = (
    SUBMITTING,
    SUBMISSION_UNKNOWN,
    RECONCILING,
    BROKER_ACCEPTED,
    PARTIALLY_FILLED,
    CANCEL_PENDING,
    # A legacy "executed" row may still represent an accepted-but-unfilled
    # order. Reconciliation must keep treating it as exposure until migrated.
    EXECUTED,
)

# Statuses during which a proposal HOLDS its ticker/side slot against any
# other proposal -- used by claim_proposal()'s cross-proposal duplicate guard.
#
# This is deliberately wider than UNRESOLVED_BROKER_STATE_STATUSES. That set
# answers "might an order exist at the broker?", which is the right question
# once a submission has been attempted. But the claim happens at the START of
# the approval flow, long before "submitting" is written, so a guard using only
# that set lets two concurrent approvals of different proposals for the same
# ticker/side BOTH claim -- each one looks at the other and sees a proposal
# that has not tried to submit yet. Verified by an actual two-thread test,
# which the narrower version failed (2026-07-30). The slot must therefore be
# held from the moment of the claim through to a terminal state.
#
# "override_available" is excluded on purpose: it means validation stopped and
# is waiting on a human, with no order pending and no submission attempted, so
# it must not block an unrelated proposal indefinitely.
#
# Fail-closed cost: a process that dies mid-validation leaves a proposal in
# "validating" and that ticker/side stays blocked until the row is resolved.
# That is the intended direction -- refusing a second order is recoverable,
# sending one is not.
IN_FLIGHT_INTENT_STATUSES: tuple[str, ...] = (
    VALIDATING,
    APPROVED,
    SUBMITTING,
    SUBMISSION_UNKNOWN,
    RECONCILING,
    BROKER_ACCEPTED,
    PARTIALLY_FILLED,
    CANCEL_PENDING,
    EXECUTED,
)

TERMINAL_BROKER_STATUSES: tuple[str, ...] = (
    FILLED,
    CANCELED,
    BROKER_REJECTED,
    BROKER_EXPIRED,
    SUBMISSION_FAILED,
)

ACTIVE_BROKER_ORDER_STATUSES: tuple[str, ...] = (
    BROKER_ACCEPTED,
    PARTIALLY_FILLED,
    CANCEL_PENDING,
)

MANUAL_RECONCILIATION_STATUSES: tuple[str, ...] = (
    SUBMITTING,
    SUBMISSION_UNKNOWN,
)
