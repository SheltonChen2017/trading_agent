"""Pre-broker claim state transitions.

GR-1A extraction. The ATOMIC claim itself is not here and must not move:
``AssistantStore.claim_proposal()`` performs it as a single conditional
UPDATE, and splitting that into read-then-write across a module boundary
would reintroduce the race it exists to close (GR-1 section 6.2). This module
owns the transitions AROUND that claim -- fencing a claimed proposal forward
and recognising a stranded one.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from assistant.execution_kernel.errors import ProposalClaimLostError
from assistant.proposal_status import APPROVED, VALIDATING
from assistant.storage import AssistantStore


# Statuses a proposal can be stranded in BEFORE anything was ever handed to the
# broker. submit_approved_proposal() writes "submitting" and only then calls
# out, so a row still sitting in "validating"/"approved" provably has no broker
# order behind it -- which is what makes recovering them safe, unlike every
# post-submission status.
PRE_BROKER_STRANDED_STATUSES: tuple[str, ...] = (VALIDATING, APPROVED)


def _transition_pre_broker_claim(
    store: AssistantStore,
    proposal_id: str,
    *,
    expected_status: str,
    new_status: str,
    **updates: Any,
) -> dict[str, Any]:
    """Advance a proposal only while this worker still owns its claim.

    Stale-claim recovery can move a long-running worker's proposal to
    ``validation_failed`` and release its ticker/side slot. The worker may
    merely have been paused rather than dead, so every later pre-broker
    transition must be conditional. Once recovery wins, this fences the old
    worker out before it can reserve budget or contact the broker.
    """
    transitioned = store.update_proposal_status_if_current(
        proposal_id,
        expected_statuses=(expected_status,),
        new_status=new_status,
        **updates,
    )
    if transitioned is not None:
        return transitioned
    current = store.get_proposal(proposal_id)
    current_status = None if current is None else current.get("status")
    raise ProposalClaimLostError(
        f"Proposal {proposal_id} lost its execution claim while transitioning "
        f"{expected_status!r} -> {new_status!r} (current status={current_status!r}). "
        "Refusing to continue, reserve execution budget, or contact the broker."
    )


def _parse_recovery_timestamp(store: AssistantStore, proposal_id: str) -> datetime | None:
    """The row's `updated_at` as a datetime, or None if it cannot be read."""
    rows = store.list_proposals_by_statuses(PRE_BROKER_STRANDED_STATUSES)
    raw = next(
        (row.get("updated_at") for row in rows if row.get("proposal_id") == proposal_id),
        None,
    )
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
