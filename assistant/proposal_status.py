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
# UI-2d dismiss/archive: a terminal, non-executable archive state for
# proposals that never touched validation, approval, reservation, or any
# broker lifecycle. Dismissal hides the row from the default History view
# while retaining the complete database record (including the unique
# idempotency key, so the same logical proposal cannot silently be
# regenerated). It is deliberately absent from IN_FLIGHT_INTENT_STATUSES,
# UNRESOLVED_BROKER_STATE_STATUSES, ACTIVE_BROKER_ORDER_STATUSES, and
# TERMINAL_BROKER_STATUSES: it holds no ticker/side slot, implies no broker
# order, and is not a broker outcome.
DISMISSED = "dismissed"

# A broker 404 immediately after dispatch is not yet reliable evidence that an
# order was never accepted: the submit response can be lost while the broker's
# client-order-id index is still catching up. Reconciliation paths must retain
# the execution reservation until the proposal has remained unresolved for at
# least this long. Kept beside the lifecycle constants so polling and manual
# reconciliation cannot silently choose different grace periods.
BROKER_ABSENCE_GRACE_SECONDS = 60.0

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
    DISMISSED,
)

# UI-2d: the only statuses a dismissal may transition FROM. Deliberately
# narrow -- `override_available` is excluded because it proves validation
# was attempted and produced a human-reviewable policy result; blocked,
# validation_failed, approved, every submission state, and every broker
# state remain permanent audit history.
DISMISSIBLE_SOURCE_STATUSES: tuple[str, ...] = (
    PROPOSED,
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

# --- UI-2b: user-facing outcome groups (frozen 2026-08-04) ------------------
#
# The History page's primary filter groups the 19 lifecycle statuses into a
# small set of outcomes a person can reason about. The grouping rules were
# frozen in docs/ACTION_PLAN_2026-08-02.md section 8 (UI-2b) BEFORE
# implementation:
#
#   - legacy "executed" means only "the broker accepted the request", never a
#     confirmed fill, so it belongs to "Broker working / unresolved" -- an
#     unresolved order must never display as completed;
#   - "Filled" contains exactly `filled` and nothing else; and
#   - a status value this mapping has never seen (a future release adding one)
#     must display as "Other / unknown", never silently join a completed-
#     looking group. `outcome_group_for_status()` is the only lookup path and
#     enforces that fail-safe.
#
# When UI-2d introduces the `dismissed` status, the exhaustiveness contract
# (`set(STATUS_OUTCOME_GROUPS) == set(STATUSES)`, pinned in
# tests/test_proposal_outcome_groups.py) forces the same reviewed change to
# add it here, into "Closed without fill" per the frozen plan.
#
# This is deliberately NOT the same rule as the Propose & Approve page's
# `_proposal_status_category()` rendering router in
# scripts/personal_assistant_ui.py: that helper decides which CONTROLS to
# show (and lumps expired/canceled in with failures for that purpose), while
# this mapping is the user-facing outcome taxonomy (which separates
# "Refused / failed" from "Closed without fill"). Do not consolidate them.

OUTCOME_AWAITING_DECISION = "Awaiting decision"
OUTCOME_PROCESSING = "Processing"
OUTCOME_BROKER_WORKING = "Broker working / unresolved"
OUTCOME_FILLED = "Filled"
OUTCOME_REFUSED_FAILED = "Refused / failed"
OUTCOME_CLOSED_WITHOUT_FILL = "Closed without fill"
OUTCOME_OTHER_UNKNOWN = "Other / unknown"

# Display order for filter widgets: lifecycle order, catch-all last.
OUTCOME_GROUPS: tuple[str, ...] = (
    OUTCOME_AWAITING_DECISION,
    OUTCOME_PROCESSING,
    OUTCOME_BROKER_WORKING,
    OUTCOME_FILLED,
    OUTCOME_REFUSED_FAILED,
    OUTCOME_CLOSED_WITHOUT_FILL,
    OUTCOME_OTHER_UNKNOWN,
)

# Every canonical status maps to exactly one group. OUTCOME_OTHER_UNKNOWN is
# intentionally absent from the values: it exists only as the fail-safe for
# statuses outside this mapping.
STATUS_OUTCOME_GROUPS: dict[str, str] = {
    PROPOSED: OUTCOME_AWAITING_DECISION,
    POLICY_OVERRIDE_AVAILABLE: OUTCOME_AWAITING_DECISION,
    VALIDATING: OUTCOME_PROCESSING,
    APPROVED: OUTCOME_PROCESSING,
    SUBMITTING: OUTCOME_BROKER_WORKING,
    SUBMISSION_UNKNOWN: OUTCOME_BROKER_WORKING,
    RECONCILING: OUTCOME_BROKER_WORKING,
    BROKER_ACCEPTED: OUTCOME_BROKER_WORKING,
    PARTIALLY_FILLED: OUTCOME_BROKER_WORKING,
    CANCEL_PENDING: OUTCOME_BROKER_WORKING,
    EXECUTED: OUTCOME_BROKER_WORKING,
    FILLED: OUTCOME_FILLED,
    BLOCKED: OUTCOME_REFUSED_FAILED,
    VALIDATION_FAILED: OUTCOME_REFUSED_FAILED,
    SUBMISSION_FAILED: OUTCOME_REFUSED_FAILED,
    BROKER_REJECTED: OUTCOME_REFUSED_FAILED,
    CANCELED: OUTCOME_CLOSED_WITHOUT_FILL,
    BROKER_EXPIRED: OUTCOME_CLOSED_WITHOUT_FILL,
    EXPIRED: OUTCOME_CLOSED_WITHOUT_FILL,
    # UI-2d: the action plan's frozen UI-2b groups pre-assigned the future
    # dismissed status to Closed without fill.
    DISMISSED: OUTCOME_CLOSED_WITHOUT_FILL,
}


def outcome_group_for_status(status: object) -> str:
    """The one lookup path from a stored status to its outcome group.

    Fail-safe direction: anything not in the frozen mapping -- a future
    status value, None, a non-string -- is "Other / unknown". It must never
    default into a group that reads as resolved or completed.
    """
    if not isinstance(status, str):
        return OUTCOME_OTHER_UNKNOWN
    return STATUS_OUTCOME_GROUPS.get(status, OUTCOME_OTHER_UNKNOWN)


def statuses_for_outcome_groups(groups) -> tuple[str, ...]:
    """The canonical statuses belonging to the selected outcome groups, in
    STATUSES order. OUTCOME_OTHER_UNKNOWN contributes no canonical status --
    it can only be matched negatively (status NOT IN STATUSES), which the
    storage query expresses with its own explicit flag."""
    wanted = set(groups)
    return tuple(
        status
        for status in STATUSES
        if STATUS_OUTCOME_GROUPS[status] in wanted
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
