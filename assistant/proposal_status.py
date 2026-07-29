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
