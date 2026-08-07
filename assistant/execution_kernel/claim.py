"""Admission control and pre-broker claim state transitions.

GR-1A extraction, extended in GR-1B with the admission phases that run
before and during the claim. The ATOMIC claim itself is not here and must
not move: ``AssistantStore.claim_proposal()`` performs it as a single
conditional UPDATE, and splitting that into read-then-write across a module
boundary would reintroduce the race it exists to close (GR-1 section 6.2).
This module orchestrates that call and owns the transitions around it --
fencing a claimed proposal forward and recognising a stranded one.

Phase order is load-bearing and is the reason these are separate functions
rather than one: the kill switch is resolved before anything is read,
preconditions refuse before anything is written, and only then is a claim
attempted. Nothing here contacts the broker.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from assistant.execution_kernel.errors import (
    ProposalClaimLostError,
    ProposalExecutionError,
)
from assistant.kill_switch import env_kill_switch_active
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.proposal_status import (
    APPROVED,
    IN_FLIGHT_INTENT_STATUSES,
    POLICY_OVERRIDE_AVAILABLE,
    VALIDATING,
)
from assistant.storage import AssistantStore, DuplicateIntentConflict


# Statuses a proposal can be stranded in BEFORE anything was ever handed to the
# broker. execute_approved_paper_proposal() writes "submitting" and only then calls
# out, so a row still sitting in "validating"/"approved" provably has no broker
# order behind it -- which is what makes recovering them safe, unlike every
# post-submission status.
PRE_BROKER_STRANDED_STATUSES: tuple[str, ...] = (VALIDATING, APPROVED)


def transition_pre_broker_claim(
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


# Legacy private name, kept as an alias to the SAME function object so
# assistant.execution_service and tests/test_stranded_claim_recovery.py keep
# their existing import path while kernel peers use the public name (GR-1
# section 6.2: no module may import another's private helpers). Same pattern
# as ProposalClaimLostError in errors.py.
_transition_pre_broker_claim = transition_pre_broker_claim


def resolve_kill_switch(store: AssistantStore, caller_flag: bool) -> bool:
    """Combine the caller's flag with the environment and persistent switches.

    Enforced here, not only in callers -- a caller that forgets to pass
    ``kill_switch_active`` must not silently bypass it. That makes the switch
    an invariant of the service rather than a convention. An unreadable
    persistent switch refuses: an unknown emergency-stop state is not "off".
    """
    try:
        persistent_kill_switch = store.get_kill_switch()
    except Exception as exc:
        raise ProposalExecutionError(
            f"Could not verify the persistent kill switch; refusing execution: {exc}"
        ) from exc
    return (
        caller_flag
        or env_kill_switch_active()
        or bool(persistent_kill_switch.get("active"))
    )


def verify_execution_preconditions(
    store: AssistantStore,
    proposal_id: str,
    confirmation: str,
    policy: TradingPolicy,
) -> dict[str, Any]:
    """Refuse anything that disqualifies this proposal before it is claimed.

    Returns the stored proposal so the caller does not re-read it. This
    snapshot is taken BEFORE the atomic claim, which is what makes its
    ``reviewed_override`` field reflect a PRIOR call rather than this one --
    ``claim_proposal()`` never touches ``payload_json``.
    """
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise ProposalExecutionError(f"Unknown proposal: {proposal_id}")
    if confirmation.strip().lower() != "approve":
        raise ProposalExecutionError('Explicit approval phrase did not match -- type "approve".')
    if policy.execution_mode != "paper":
        raise ProposalExecutionError("The active policy does not permit paper execution.")
    if proposal["policy_version"] != policy.version:
        raise ProposalExecutionError("Proposal policy version does not match the active policy.")
    # A manually-maintained version string alone can't catch an edited-
    # but-not-rebumped policy file: two policy files (e.g. a personal one
    # copied from the default) can share the same version yet have
    # materially different limits (GPT review, 2026-07-28). The
    # fingerprint covers every behavior-affecting field, so it changes
    # even when version doesn't. A proposal predating fingerprinting
    # (missing the field entirely) fails closed here rather than being
    # grandfathered in -- regenerate it instead.
    if proposal.get("policy_fingerprint") != compute_policy_fingerprint(policy):
        raise ProposalExecutionError(
            "Proposal's policy fingerprint does not match the active policy's current content -- the "
            "policy may have been edited without a version bump (or this proposal predates fingerprint "
            "binding). Regenerate the proposal against the current policy."
        )
    return proposal


def claim_for_execution(
    store: AssistantStore, proposal_id: str, now_utc: datetime
) -> dict[str, Any]:
    """Take exclusive ownership of a proposal, or refuse with the reason.

    Atomic claim: proposed -> validating, ONLY if not already expired.
    Both the claim and the expiry write below are conditioned on the
    row still being "proposed" at the moment they run, so neither can
    ever clobber an "executed"/"approved"/"validating"/"submission_failed"
    status -- a prior version checked expiry with an unconditional write
    before claiming, which could silently flip an already-executed
    proposal back to "expired" if approval was invoked again past its
    expiry window (or race an in-flight claim into "expired" out from
    under it).

    Also claimable from POLICY_OVERRIDE_AVAILABLE: that status means a
    PRIOR call found only override-eligible violations and is waiting on
    a human decision, not a terminal rejection -- re-invoking (with
    override_policy_violations=True to actually proceed past them, or
    without it to just re-check) must be able to pick it back up.

    conflicting_intent_statuses makes the ticker+side duplicate rule part of
    the SAME serialized claim as the status check. The snapshot-based
    duplicate check in revalidation still runs (it also covers recent fills
    and broker orders this process never proposed); this closes the narrower
    window where two concurrent approvals of DIFFERENT proposals for the same
    ticker/side both read "no duplicate" before either order reached the
    broker (independent review, 2026-07-30).
    """
    try:
        claimed = store.claim_proposal(
            proposal_id,
            expected_status=("proposed", POLICY_OVERRIDE_AVAILABLE),
            new_status=VALIDATING,
            not_expired_after=now_utc.isoformat(),
            conflicting_intent_statuses=IN_FLIGHT_INTENT_STATUSES,
        )
    except DuplicateIntentConflict as exc:
        raise ProposalExecutionError(f"Duplicate-order protection: {exc}") from exc
    if claimed is not None:
        return claimed
    current = store.get_proposal(proposal_id)
    if (
        current is not None
        and current["status"] in ("proposed", POLICY_OVERRIDE_AVAILABLE)
        and now_utc > datetime.fromisoformat(current["expires_at"])
    ):
        store.claim_proposal(
            proposal_id, expected_status=("proposed", POLICY_OVERRIDE_AVAILABLE), new_status="expired"
        )
        raise ProposalExecutionError("Proposal has expired; generate a fresh one.")
    raise ProposalExecutionError(
        f"Proposal {proposal_id} could not be claimed (already being processed, "
        "already executed, or not in a 'proposed' or 'override_available' state)."
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
