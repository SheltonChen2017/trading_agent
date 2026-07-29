"""
Sequential, resumable batch execution for a Watchlist allocation split's
"submit all proposals in this split" action.

Explicitly NOT an atomic transaction: paper (and real) broker orders
cannot generally be rolled back once submitted, so a batch of N
independent buy proposals can legitimately end up partially filled (e.g.
3 of 5 legs submitted, a 4th blocked, a 5th never attempted). Every piece
of user-facing text for this feature must say so plainly -- GPT review,
2026-07-28: the prior "Execute all proposals in this split" wording, and
the fact that it lived entirely in Streamlit callback code with no
persisted record, made a page refresh mid-batch lose track of which legs
had already been attempted, risking a double-submission on blind retry.

Two-phase by design:
  1. preflight_allocation_batch() -- a read-only dry run against a
     PROJECTED, cumulatively-reserved portfolio state: each leg's check
     includes every EARLIER leg's planned notional already reserved
     against cash/buying-power and pending exposure, using the shared
     assistant.execution_service.validate_proposal_for_execution() (the
     same checks the real execution path enforces -- policy version/
     fingerprint, execution mode, paper mode, open-orders availability,
     allowed sides/types, allow_new_positions, earnings requirement, and
     validate_trade_intent() itself) so preflight can no longer approve a
     batch the real execution path would reject for a reason preflight
     never checked (2026-07-29, GPT review). If ANY leg fails, the caller
     should refuse to create/start the batch at all ("submit none").
  2. execute_allocation_batch() -- the actual sequential submission,
     against a batch record persisted via AssistantStore.create_
     allocation_batch()/update_allocation_batch(). Safe to call again
     after a UI refresh or process restart: the PROPOSAL's own status is
     always treated as authoritative and re-synced onto the batch leg
     before deciding anything (2026-07-29, GPT review: a leg that had
     gone LEG_UNKNOWN used to stay that way forever even after the
     underlying proposal was reconciled to a terminal state, so a batch
     could never resume after the exact recovery step the UI told the
     user to perform; a crash between the proposal becoming "executed"
     and the batch leg being updated used to cause a duplicate-submission
     attempt on retry). A leg left "unknown" from a prior attempt STOPS
     the batch again (never blindly retried -- an ambiguous broker
     outcome must be resolved via assistant.execution_service.
     reconcile_submission()/recover_stale_reconciliation() first).

Deliberately does NOT support a batch-level policy override: each leg
that's blocked only by an override-eligible violation still requires its
own individual, per-proposal override control (see
assistant.execution_service.PolicyOverridableBlockError and
risk.execution_gate.authorize_overridden_trade_intent()) -- a human
reviewing and consciously accepting ONE specific ticker's concentration
cap or earnings-date block is a different act than blanket-approving
every override in a whole batch at once (GPT review, 2026-07-28: "do not
allow bulk policy overrides").
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from assistant.context_builder import build_portfolio_snapshot_from_alpaca
from assistant.execution_service import (
    PolicyOverridableBlockError,
    ProposalExecutionError,
    execute_approved_paper_proposal,
    validate_proposal_for_execution,
)
from assistant.policy import TradingPolicy
from assistant.proposal_status import POLICY_OVERRIDE_AVAILABLE
from assistant.schemas import PortfolioSnapshot
from assistant.storage import AssistantStore
from risk.execution_gate import ValidationResult

# Leg states. "submitted"/"failed" are terminal for that leg (a failed
# leg does not block the rest of the batch -- each proposal is
# independent); "unknown" halts the WHOLE batch until a human resolves
# it; "blocked_overridable" is also terminal for the batch's automatic
# pass -- resolving it requires the per-proposal override control, not
# anything batch-level.
LEG_UNATTEMPTED = "unattempted"
LEG_SUBMITTED = "submitted"
LEG_FAILED = "failed"
LEG_UNKNOWN = "unknown"
LEG_BLOCKED_OVERRIDABLE = "blocked_overridable"

BATCH_CREATED = "created"
BATCH_COMPLETED = "completed"
BATCH_STOPPED = "stopped"
BATCH_STOPPED_UNKNOWN = "stopped_unknown"

# Proposal statuses that map directly to a terminal-for-this-leg batch
# state, independent of anything the batch itself has recorded. "proposed"
# is handled separately (it means "eligible to attempt," not terminal).
# "validating"/"approved" are deliberately NOT here -- see
# _sync_leg_from_proposal()'s docstring.
_TERMINAL_FAILURE_STATUSES = frozenset({
    "submission_failed",
    "blocked",
    "validation_failed",
    "expired",
    "canceled",
    "broker_rejected",
    "broker_expired",
})
_UNKNOWN_STATUSES = frozenset({"submitting", "submission_unknown", "reconciling"})
_BROKER_ORDER_STATUSES = frozenset({
    "broker_accepted",
    "partially_filled",
    "cancel_pending",
    "filled",
    # Legacy rows used this for broker acceptance.
    "executed",
})


def new_batch_id() -> str:
    return "batch_" + uuid.uuid4().hex[:16]


def _sync_leg_from_proposal(leg: dict, proposal: dict | None) -> dict:
    """
    The proposal record is the authoritative source of execution truth;
    a batch leg is a resumable orchestration PROJECTION of it, never the
    other way around. Called before deciding what to do with any
    nonterminal leg, so a leg's stale in-memory state can never override
    what the proposal has since become (e.g. after a human ran
    reconcile_submission() on it, or after a crash left the proposal
    "executed" while the leg was never updated).

    Statuses "validating"/"approved" are treated the same as an
    unresolved broker state (mapped to LEG_UNKNOWN, stopping the batch)
    rather than assumed retryable -- these mean a PRIOR attempt is (or
    recently was) actively in progress; blindly resubmitting risks a
    duplicate order, so this stops for investigation rather than
    guessing (GPT review, 2026-07-29).
    """
    if proposal is None:
        return {
            **leg,
            "state": LEG_FAILED,
            "error": "Proposal record missing entirely -- failing closed.",
        }

    status = proposal["status"]
    if status in _BROKER_ORDER_STATUSES:
        new_state = LEG_SUBMITTED
    elif status in _TERMINAL_FAILURE_STATUSES:
        new_state = LEG_FAILED
    elif status == POLICY_OVERRIDE_AVAILABLE:
        new_state = LEG_BLOCKED_OVERRIDABLE
    elif status in _UNKNOWN_STATUSES:
        new_state = LEG_UNKNOWN
    elif status == "proposed":
        new_state = LEG_UNATTEMPTED
    elif status in ("validating", "approved"):
        new_state = LEG_UNKNOWN
    else:
        new_state = leg.get("state", LEG_UNATTEMPTED)

    synced = dict(leg)
    synced["state"] = new_state
    synced["proposal_status_seen"] = status
    if new_state == LEG_SUBMITTED and not synced.get("order"):
        broker_order = proposal.get("broker_order")
        if broker_order:
            synced["order"] = broker_order
    proposal_error = proposal.get("error")
    if proposal_error and proposal_error != synced.get("error"):
        history = list(synced.get("error_history") or [])
        if synced.get("error"):
            history.append(synced["error"])
        synced["error_history"] = history
        synced["error"] = proposal_error
    elif not proposal_error and new_state == LEG_SUBMITTED and synced.get("error"):
        # The authoritative proposal has no CURRENT error (a clean
        # "executed"), but the leg still carries a stale message from an
        # earlier attempt (e.g. "blocked by cap" from a prior
        # blocked_overridable state, before it was resolved via that
        # proposal's own individual override control) -- that message
        # must not keep showing next to a now-successful order (GPT
        # review, 2026-07-30, reproduced: the Streamlit batch table's
        # Detail column kept showing the old block reason alongside a
        # successfully submitted order_id). Preserved in error_history
        # for auditability, never silently discarded. Does NOT run when
        # the proposal itself still has an active error (e.g. "broker
        # accepted the order but local journal recording failed") --
        # that case is handled by the branch above instead, which keeps
        # it as the current error rather than clearing it.
        history = list(synced.get("error_history") or [])
        history.append(synced["error"])
        synced["error_history"] = history
        synced["error"] = None
    return synced


def preflight_allocation_batch(
    proposal_ids: list[str],
    store: AssistantStore,
    policy: TradingPolicy,
    current_portfolio: PortfolioSnapshot,
    now_et: datetime,
    kill_switch_active: bool = False,
) -> dict[str, ValidationResult]:
    """
    Revalidates every proposal in a prospective batch WITHOUT claiming or
    submitting anything -- a read-only, CUMULATIVE dry run: each leg's
    check reserves every earlier (passing) leg's planned notional before
    validating the next leg, so two individually-safe proposals that
    would collectively exceed a cap correctly fail preflight together
    (GPT review, 2026-07-29 -- previously each leg was checked
    independently against the SAME starting snapshot, so preflight could
    approve a batch that execution would then partially reject).

    This cross-leg reservation math is risk-adjacent but intentionally NOT
    in risk/execution_gate.py -- see that module's "Known scatter points"
    note and docs/ARCHITECTURE_DEBT.md.

    Accounting invariant (GPT review, 2026-07-29 follow-up -- a second
    bug in the FIRST fix for the above): each existing position, real
    pending order, and simulated earlier batch leg must contribute
    EXACTLY ONCE to projected exposure. The original fix reserved earlier
    legs' notional in two places at once -- reduced `cash` on a
    `dataclasses.replace()`'d portfolio (affecting the cash-availability
    checks) AND `extra_pending_buy_value_by_ticker` (affecting the
    exposure/concentration checks) -- but validate_trade_intent()'s
    `existing_invested` is derived from `total_equity - cash`, so the
    SAME reservation was ALSO counted there via the shrunk cash figure,
    double-counting every earlier leg (e.g. two $4,000 buys against a
    $10,000/80%-exposure-cap account: real cumulative exposure is exactly
    80%, but the double-counted math reported 120% and rejected a batch
    that should have passed). Fixed by never mutating `current_portfolio`
    at all: it's passed to validate_proposal_for_execution() UNCHANGED
    (so `existing_invested` always derives from the real, unreserved
    cash/equity), while reserved cash is instead passed via
    `available_cash_override`/`available_buying_power_override` --
    parameters validate_trade_intent() consults ONLY for the cash-
    availability checks (INSUFFICIENT_CASH, MIN_CASH_RESERVE), never for
    exposure. `extra_pending_buy_value_by_ticker` remains the sole place
    a reservation enters exposure math, so it's counted there once and
    never again via cash.

    The caller MUST refuse to create/start the batch if any result is
    not approved ("if any proposal fails preflight, default to submitting
    none"). Proposal order is deterministic: exactly the order of
    `proposal_ids` as given by the caller (the UI passes them in the
    order the allocation split was generated).
    """
    results: dict[str, ValidationResult] = {}
    reserved_cash = 0.0
    reserved_pending_by_ticker: dict[str, float] = {}

    for proposal_id in proposal_ids:
        available_cash_override = current_portfolio.cash - reserved_cash
        available_buying_power_override = (
            current_portfolio.buying_power - reserved_cash
            if current_portfolio.buying_power is not None
            else None
        )
        outcome = validate_proposal_for_execution(
            proposal_id,
            current_portfolio,
            policy,
            store,
            now_et=now_et,
            kill_switch_active=kill_switch_active,
            extra_pending_buy_value_by_ticker=dict(reserved_pending_by_ticker),
            available_cash_override=available_cash_override,
            available_buying_power_override=available_buying_power_override,
        )
        if outcome.error is not None:
            results[proposal_id] = ValidationResult(
                approved=False, violations=(outcome.error,), violation_codes=("preflight_error",),
            )
            continue
        results[proposal_id] = outcome.validation
        if (
            outcome.validation is not None
            and outcome.validation.approved
            and outcome.intent is not None
            and outcome.reference_price is not None
            and outcome.intent.side == "buy"
        ):
            planned_notional = outcome.intent.shares * outcome.reference_price
            reserved_cash += planned_notional
            key = outcome.intent.ticker.upper()
            reserved_pending_by_ticker[key] = reserved_pending_by_ticker.get(key, 0.0) + planned_notional

    return results


def execute_allocation_batch(
    batch_id: str,
    store: AssistantStore,
    policy: TradingPolicy,
    *,
    now_et: datetime | None = None,
    now_provider: Callable[[], datetime] | None = None,
    kill_switch_active: bool = False,
) -> dict:
    """
    Submits every eligible leg of a persisted batch, in order, re-fetching
    the live portfolio before each leg so an earlier fill in this same
    batch is reflected in the next leg's cash/exposure checks.

    Resumable and idempotent: safe to call again (e.g. after a UI refresh
    or process restart) -- before touching any nonterminal leg, its state
    is re-derived from the PROPOSAL's own current status via
    _sync_leg_from_proposal(), never trusted from stale batch metadata
    alone. A leg whose proposal is "executed" is recognized as already
    submitted (no second broker call); a leg reconciled to "submission_
    failed"/"blocked"/"expired" is recognized as failed and does not
    block the rest of the batch; a leg still "submitting"/"submission_
    unknown"/"reconciling" (or "validating"/"approved", an uncertain
    in-progress state after a restart) stops the whole batch again until
    a human resolves it via assistant.execution_service.
    reconcile_submission() (or recover_stale_reconciliation() if it's
    also stuck) -- resolve it, then call this function again to continue.
    A leg blocked only by an override-eligible policy violation is
    recorded as "blocked_overridable" and does NOT stop the batch (it's
    terminal for that leg, not ambiguous) -- resolve it individually via
    the proposal's own approval card.

    `now_provider`, when given, is called FRESH for every leg attempted
    in this batch, rather than one timestamp being reused across the
    whole batch (GPT review, 2026-07-31, independently reproduced: this
    function already re-fetches the live PORTFOLIO before each leg
    specifically so an earlier fill is reflected, but reused the exact
    same `now_et` for every leg's staleness/future-timestamp/trading-
    session check -- a slow batch spanning several broker round-trips
    could compare a genuinely fresh quote against an increasingly stale
    `now_et`, either wrongly flagging it as impossibly "in the future" or
    evaluating a later leg against the wrong trading-session boundary).
    `now_et` (a single fixed timestamp, the prior interface) is still
    accepted for backward compatibility and test determinism -- when
    `now_provider` is omitted, it's wrapped into a provider that returns
    that exact fixed value every time, preserving the previous single-
    timestamp-for-the-whole-batch behavior exactly. Pass `now_provider`
    explicitly (a real per-call clock function in production, or a fake/
    advancing clock in tests) to get genuinely fresh per-leg timestamps.
    Exactly one of `now_et`/`now_provider` must be supplied.
    """
    if now_provider is None:
        if now_et is None:
            raise TypeError("execute_allocation_batch() requires either now_et or now_provider.")
        fixed_now_et = now_et
        now_provider = lambda: fixed_now_et  # noqa: E731 -- trivial, deliberately local

    batch = store.get_allocation_batch(batch_id)
    if batch is None:
        raise ProposalExecutionError(f"Unknown batch: {batch_id}")
    if batch["status"] == BATCH_COMPLETED:
        # A "completed" batch is a resumable PROJECTION, never assumed
        # frozen -- a leg left "blocked_overridable" here can still be
        # resolved later via that proposal's OWN individual override
        # control (the UI tells the user to do exactly this), and this
        # module's stated invariant is that the proposal record is
        # always authoritative over the batch leg, not the other way
        # around. Re-sync every leg from its proposal before returning,
        # so a batch the UI displays as "completed" doesn't keep showing
        # a leg as blocked forever after the underlying proposal has
        # since been executed via that path (GPT review, 2026-07-29).
        # Never calls execute_approved_paper_proposal() here -- this is
        # a read/display refresh only, never a broker submission.
        legs = batch["legs"]
        changed = False
        for proposal_id in batch["proposal_ids"]:
            leg = legs.get(proposal_id, {"state": LEG_UNATTEMPTED, "order": None, "error": None})
            current_proposal = store.get_proposal(proposal_id)
            synced = _sync_leg_from_proposal(leg, current_proposal)
            # Compare only the fields that matter for correctness/display
            # (state, order, error) -- _sync_leg_from_proposal() also
            # always adds bookkeeping metadata (proposal_status_seen,
            # error_history) that a leg written by the normal execution
            # path below never had to begin with, which would otherwise
            # make EVERY completed batch look "changed" on its very first
            # resync even when nothing meaningful happened.
            if (
                synced.get("state") != leg.get("state")
                or synced.get("order") != leg.get("order")
                or synced.get("error") != leg.get("error")
            ):
                changed = True
                legs[proposal_id] = synced
        if not changed:
            return batch  # idempotent: nothing to persist, no-op read
        all_terminal = all(
            legs.get(pid, {"state": LEG_UNATTEMPTED})["state"] in (LEG_SUBMITTED, LEG_FAILED, LEG_BLOCKED_OVERRIDABLE)
            for pid in batch["proposal_ids"]
        )
        # Still all terminal (the common case: a blocked_overridable leg
        # became submitted) -- stays "completed", just with fresh leg
        # data. If a resync instead produced an unresolved state
        # (LEG_UNKNOWN, e.g. a leg's proposal is mid-flight via its
        # individual override control right now), the batch must
        # honestly stop reporting "completed" the same way the main
        # execution loop below would.
        final_status = BATCH_COMPLETED if all_terminal else BATCH_STOPPED_UNKNOWN
        return store.update_allocation_batch(batch_id, status=final_status, legs=legs)

    legs = batch["legs"]
    for proposal_id in batch["proposal_ids"]:
        leg = legs.get(proposal_id, {"state": LEG_UNATTEMPTED, "order": None, "error": None})
        current_proposal = store.get_proposal(proposal_id)
        leg = _sync_leg_from_proposal(leg, current_proposal)
        legs[proposal_id] = leg

        if leg["state"] in (LEG_SUBMITTED, LEG_FAILED, LEG_BLOCKED_OVERRIDABLE):
            continue
        if leg["state"] == LEG_UNKNOWN:
            return store.update_allocation_batch(batch_id, status=BATCH_STOPPED_UNKNOWN, legs=legs)

        # leg["state"] == LEG_UNATTEMPTED and the proposal is genuinely
        # still "proposed" -- eligible to attempt. now_provider() is
        # called FRESH for THIS leg specifically (see docstring) -- never
        # a single timestamp reused across the whole batch.
        portfolio = build_portfolio_snapshot_from_alpaca()
        try:
            order = execute_approved_paper_proposal(
                proposal_id, "approve", portfolio, policy, store,
                now_et=now_provider(), kill_switch_active=kill_switch_active,
            )
            legs[proposal_id] = {"state": LEG_SUBMITTED, "order": order, "error": None}
        except PolicyOverridableBlockError as exc:
            legs[proposal_id] = {"state": LEG_BLOCKED_OVERRIDABLE, "order": None, "error": str(exc)}
        except ProposalExecutionError as exc:
            current = store.get_proposal(proposal_id)
            if current is not None and current["status"] == "submission_unknown":
                legs[proposal_id] = {"state": LEG_UNKNOWN, "order": None, "error": str(exc)}
                return store.update_allocation_batch(batch_id, status=BATCH_STOPPED_UNKNOWN, legs=legs)
            legs[proposal_id] = {"state": LEG_FAILED, "order": None, "error": str(exc)}
        store.update_allocation_batch(batch_id, legs=legs)

    all_terminal = all(
        legs.get(pid, {"state": LEG_UNATTEMPTED})["state"] in (LEG_SUBMITTED, LEG_FAILED, LEG_BLOCKED_OVERRIDABLE)
        for pid in batch["proposal_ids"]
    )
    final_status = BATCH_COMPLETED if all_terminal else BATCH_STOPPED
    return store.update_allocation_batch(batch_id, status=final_status, legs=legs)
