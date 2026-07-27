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
BLOCKED = "blocked"
VALIDATION_FAILED = "validation_failed"
APPROVED = "approved"
SUBMITTING = "submitting"
SUBMISSION_UNKNOWN = "submission_unknown"
SUBMISSION_FAILED = "submission_failed"
RECONCILING = "reconciling"
EXECUTED = "executed"
EXPIRED = "expired"

# Ordered roughly by where a proposal sits in its lifecycle.
STATUSES: tuple[str, ...] = (
    PROPOSED,
    VALIDATING,
    BLOCKED,
    VALIDATION_FAILED,
    APPROVED,
    SUBMITTING,
    SUBMISSION_UNKNOWN,
    RECONCILING,
    SUBMISSION_FAILED,
    EXECUTED,
    EXPIRED,
)

# Statuses where a broker order may exist (or might exist) even though the
# proposal hasn't reached a clean terminal state -- used to widen the
# duplicate-order check so a regenerated proposal for the same
# ticker/side is blocked until an unresolved submission is reconciled.
UNRESOLVED_BROKER_STATE_STATUSES: tuple[str, ...] = (SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING)
