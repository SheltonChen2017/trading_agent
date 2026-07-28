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
  1. preflight_allocation_batch() -- a read-only dry run against a single
     shared fresh portfolio snapshot. If ANY leg fails preflight, the
     caller should refuse to create/start the batch at all ("submit
     none" -- GPT review).
  2. execute_allocation_batch() -- the actual sequential submission,
     against a batch record persisted via AssistantStore.create_
     allocation_batch()/update_allocation_batch(). Safe to call again
     after a UI refresh or process restart: already-"submitted"/"failed"
     legs are skipped (idempotent no-op), and a leg left "unknown" from a
     prior attempt STOPS the batch again (never blindly retried -- an
     ambiguous broker outcome must be resolved via
     assistant.execution_service.reconcile_submission()/
     recover_stale_reconciliation() first, since continuing past it could
     double-submit or compute exposure/concentration checks against a
     stale assumption about what already filled).

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

from assistant.context_builder import build_portfolio_snapshot_from_alpaca
from assistant.execution_service import (
    PolicyOverridableBlockError,
    ProposalExecutionError,
    _intent_from_dict,
    _pending_buy_value_by_ticker,
    _resolve_earnings_days_away,
    execute_approved_paper_proposal,
)
from assistant.policy import TradingPolicy
from assistant.schemas import PortfolioSnapshot
from assistant.storage import AssistantStore
from risk.execution_gate import ValidationResult, validate_trade_intent

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


def new_batch_id() -> str:
    return "batch_" + uuid.uuid4().hex[:16]


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
    submitting anything -- a true read-only dry run against ONE shared
    fresh portfolio snapshot (the same snapshot for every leg, since this
    runs before any leg has actually filled). The caller MUST refuse to
    create/start the batch if any result.approved is False ("if any
    proposal fails preflight, default to submitting none" -- GPT review,
    2026-07-28).

    Deliberately duplicates a subset of execute_approved_paper_proposal()'s
    own pre-submission checks (quote fetch, pending-buy-value, earnings)
    rather than reusing that function directly: it claims and mutates
    proposal state as an inseparable part of validating, so it cannot be
    called for a side-effect-free dry run without risking exactly the
    kind of regression this project's execution-safety layer has spent
    many review rounds hardening against. Keeping this preflight small,
    read-only, and isolated in its own function is the deliberately safer
    trade-off over refactoring that hardened core path.
    """
    import execution.alpaca_broker as broker

    results: dict[str, ValidationResult] = {}
    recent_intents = [_intent_from_dict(raw) for raw in store.recent_executed_intents()]

    for proposal_id in proposal_ids:
        proposal = store.get_proposal(proposal_id)
        if proposal is None:
            results[proposal_id] = ValidationResult(
                approved=False, violations=(f"Unknown proposal: {proposal_id}",),
                violation_codes=("unknown_proposal",),
            )
            continue
        try:
            intent = _intent_from_dict(proposal["intent"])
            quote = broker.get_latest_quote(intent.ticker)
            pending_buy_value_by_ticker = {}
            if intent.side == "buy":
                pending_buy_value_by_ticker = _pending_buy_value_by_ticker(current_portfolio.open_orders, broker)
            resolved_earnings_days_away = _resolve_earnings_days_away(intent.ticker, None)
            validation = validate_trade_intent(
                intent,
                current_portfolio,
                quote["price"],
                price_timestamp=quote["timestamp"],
                now=now_et,
                recent_intents=recent_intents,
                kill_switch_active=kill_switch_active,
                earnings_days_away=resolved_earnings_days_away,
                bid_price=quote.get("bid"),
                ask_price=quote.get("ask"),
                max_position_pct=policy.max_position_pct,
                max_total_exposure_pct=policy.max_total_exposure_pct,
                max_basket_pct=policy.max_basket_pct * 100,
                max_leveraged_etf_pct=policy.max_leveraged_etf_pct * 100,
                max_stale_price_minutes=policy.max_stale_price_minutes,
                max_slippage_pct=policy.max_slippage_pct,
                max_spread_pct=policy.max_spread_pct,
                earnings_blackout_days=policy.earnings_blackout_days,
                max_order_value=policy.max_order_value,
                min_cash_reserve_pct=policy.min_cash_reserve_pct,
                pending_buy_value_by_ticker=pending_buy_value_by_ticker,
            )
            results[proposal_id] = validation
        except Exception as exc:
            results[proposal_id] = ValidationResult(
                approved=False, violations=(f"Preflight check failed: {exc}",),
                violation_codes=("preflight_error",),
            )
    return results


def execute_allocation_batch(
    batch_id: str,
    store: AssistantStore,
    policy: TradingPolicy,
    *,
    now_et: datetime,
    kill_switch_active: bool = False,
) -> dict:
    """
    Submits every unattempted leg of a persisted batch, in order,
    re-fetching the live portfolio before each leg so an earlier fill in
    this same batch is reflected in the next leg's cash/exposure checks.

    Resumable and idempotent: safe to call again (e.g. after a UI refresh
    or process restart) -- a leg already "submitted" or "failed" is
    skipped; a batch already "completed" is a no-op that just returns the
    stored record. A leg that comes back "submission_unknown" STOPS the
    whole batch (status "stopped_unknown") rather than being retried or
    having later legs attempted past it -- resolve it via
    assistant.execution_service.reconcile_submission() (or
    recover_stale_reconciliation() if it's also stuck in "reconciling"),
    then call this function again to continue. A leg blocked only by an
    override-eligible policy violation is recorded as
    "blocked_overridable" and does NOT stop the batch (it's terminal for
    that leg, not ambiguous) -- resolve it individually via the
    proposal's own approval card, then regenerate/re-run the batch for
    any remaining unattempted legs.
    """
    batch = store.get_allocation_batch(batch_id)
    if batch is None:
        raise ProposalExecutionError(f"Unknown batch: {batch_id}")
    if batch["status"] == BATCH_COMPLETED:
        return batch

    legs = batch["legs"]
    for proposal_id in batch["proposal_ids"]:
        leg = legs.get(proposal_id, {"state": LEG_UNATTEMPTED})
        if leg["state"] in (LEG_SUBMITTED, LEG_FAILED, LEG_BLOCKED_OVERRIDABLE):
            continue
        if leg["state"] == LEG_UNKNOWN:
            # An ambiguous leg from a prior attempt blocks further
            # progress until a human resolves it.
            return store.update_allocation_batch(batch_id, status=BATCH_STOPPED_UNKNOWN, legs=legs)

        portfolio = build_portfolio_snapshot_from_alpaca()
        try:
            order = execute_approved_paper_proposal(
                proposal_id, "approve", portfolio, policy, store,
                now_et=now_et, kill_switch_active=kill_switch_active,
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
