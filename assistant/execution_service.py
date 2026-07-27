"""User-approved, policy-bound, paper-only proposal execution.

2026-07-27 update (independent Codex review, verified against this code
before acting): closed 5 real gaps between this module's safety promises
and what it actually enforced --
  1. Open-order lookup failing open: a broker order-endpoint error was
     silently treated as "no open orders," which is exactly the state a
     duplicate-order check must NOT trust. Now checks
     current_portfolio.open_orders_available and fails closed.
  2. Earnings blackout was accepted as a parameter but never supplied by
     any caller, so the check in risk/execution_gate.py was always
     skipped. Now fetches it live (data/event_data.py) when the caller
     doesn't override it, same "honestly unavailable, never guessed"
     discipline the rest of this project already uses for missing data.
  3. Same-day proposal regeneration silently no-op'd against a stale row
     (see assistant/proposals.py's _stable_id docstring for the fix).
  4. Proposal claiming was read-then-later-write, not atomic -- two
     concurrent approvals could both pass the initial status check. Now
     uses AssistantStore.claim_proposal()'s single conditional UPDATE.
  5. Price staleness was asserted, not measured: price_timestamp was set
     to "now", so the check compared now against itself and could never
     fail regardless of how stale the actual quote was. Now fetches a
     real quote + its own timestamp via execution.alpaca_broker.get_latest_quote().

2026-07-27 follow-up (second independent review of the above fix, again
verified before acting): found one real regression the first pass
introduced, plus two smaller gaps --
  6. The expiry check ran BEFORE the atomic claim and used an
     unconditional status write, so re-invoking approval on an
     already-executed proposal after its expiry window had passed could
     silently flip its status back to "expired" -- and could race an
     in-flight claim. Fixed: expiry is now folded into the same atomic
     conditional UPDATE as the claim (AssistantStore.claim_proposal()'s
     `not_expired_after`), and the fallback "mark expired" write is
     itself conditioned on the row still being "proposed" at that
     moment, so it can never clobber a terminal/in-flight status.
  7. Missing earnings data silently skipped the blackout check with no
     way to require otherwise. Added TradingPolicy.require_earnings_data
     (default False, preserving the existing "honestly unavailable,
     never guessed" behavior) -- when enabled, a BUY is blocked if
     earnings data can't be resolved; risk-reducing SELLs are exempt.
  8. Only ProposalExecutionError was caught around the validation stage,
     so a genuinely unexpected exception (a bug, a malformed stored
     intent, etc.) left the claimed proposal stranded in "validating"
     forever. Added a catch-all that marks a distinct "validation_failed"
     status and re-raises -- never silently swallowed, never auto-reset
     to "proposed".

2026-07-28 update (independent GPT review, verified against this code
before acting) -- closed the remaining execution-safety gaps:
  9. Submission reconciliation: an exception during broker.submit_*_order
     no longer assumes rejection. Alpaca might have accepted the order
     and only the response was lost (a network timeout, for example) --
     in that case treating it as "submission_failed" would let a later
     retry submit a genuine duplicate real order. Now, on any submission
     exception, this module queries the broker BY THE SAME idempotency
     key (client_order_id) via broker.find_order_by_client_id(). If found,
     the order is journaled and the proposal is marked "executed" same as
     a normal success. If the lookup itself can't confirm either way, the
     proposal is marked "submission_unknown" (a distinct, non-terminal
     status) instead of "submission_failed" -- and AssistantStore.
     recent_executed_intents() now also treats "submitting"/
     "submission_unknown" proposals as live duplicate-order risk, so a
     regenerated proposal for the same ticker/side is blocked until a
     human reconciles the unknown proposal against the actual Alpaca
     account. A "submitting" status is written just before the broker
     call for the same reason -- so even a crash between the call and the
     response leaves a non-terminal, duplicate-blocking status behind
     instead of nothing. record_broker_order() failing AFTER a confirmed
     broker acceptance is also handled separately: the proposal is still
     marked "executed" (the order really was accepted) with the local
     journaling failure recorded in its `error` field, rather than losing
     the fact that a real order exists.
 10. The kill switch was only enforced by callers reading
     TRADING_ASSISTANT_KILL_SWITCH and passing kill_switch_active=True --
     a caller that forgot to pass it silently bypassed the switch. Now
     this function itself also reads the environment variable and ORs it
     in, so the kill switch is an invariant of the execution service
     itself, not a presentation-layer convention every caller must
     remember to honor.
 11. Market orders (the only order type any built-in proposal generator
     creates) had no protection against a wide bid/ask spread -- the
     existing max_slippage_pct check only fired for limit orders compared
     against their own limit price. broker.get_latest_quote() now returns
     bid/ask separately (not just a collapsed mid), and validate_trade_
     intent() gained a bid/ask spread check (TradingPolicy.max_spread_pct)
     that applies to every order type.
 12. Approved intents with order_type="limit" were always submitted via
     submit_market_order() regardless -- broker-side authorization would
     actually reject the mismatch (the reconstructed intent used inside
     submit_market_order never matches a limit-order authorization's
     fingerprint), so this was a dormant bug rather than a live one (no
     generator in this repo creates limit intents yet), but it made the
     policy's allowed_order_types=["market","limit"] advertise unsupported
     behavior. This module now routes by intent.order_type to the correct
     broker function.

2026-07-29 update (third independent GPT review, verified against this
code before acting) -- closed the remaining gaps in the round-2 fixes:
 13. broker.find_order_by_client_id() used to catch every exception and
     return None, making "the order definitely doesn't exist" (a genuine
     404) indistinguishable from "the lookup itself failed" (network/
     auth/5xx). Now it only returns None on a confirmed HTTP 404 and lets
     any other exception propagate. This module's own submission-error
     handling (and the new reconcile_submission() below) both now use
     _lookup_order_outcome() to get a real three-way answer: found /
     confirmed-absent / unconfirmed -- a confirmed-absent result after a
     submission error now correctly resolves straight to
     "submission_failed" (the broker is telling us it was never
     accepted) instead of the more conservative "submission_unknown".
 14. There was no way to ever resolve a proposal stuck in "submitting"
     or "submission_unknown" -- re-running approval can't help (the
     proposal is no longer "proposed"), so short of hand-editing SQLite
     it could block that ticker/side's duplicate check forever. Added
     reconcile_submission(), exposed as
     `python scripts/run_personal_assistant.py reconcile <proposal_id>`,
     which atomically claims the proposal, re-queries the broker by the
     same idempotency key, cross-checks the returned order's ticker/side
     against the proposal's own intent before trusting it (a mismatch is
     left unresolved rather than silently accepted), and only then
     transitions to a terminal state -- recording `reconciled_at` on
     every outcome as an audit trail.
 15. A limit intent with limit_price=None/0/negative/non-finite could
     pass validate_trade_intent() (only the slippage check, which is
     skipped when limit_price is None, guarded it) and reach
     submit_limit_order(), where it would fail at the broker and could
     land in "submission_unknown" for no good reason. The gate now
     requires a positive, finite limit_price whenever order_type ==
     "limit", and separately rejects non-finite reference prices and
     one-sided/crossed bid-ask quotes instead of silently skipping the
     spread check on them (see risk/execution_gate.py).

2026-07-30 update (fourth independent GPT review, verified against this
code before acting):
 16. Pending (not-yet-filled) BUY orders were invisible to every
     exposure/concentration check (per-position, total, basket,
     leveraged-ETF) -- those only look at portfolio.positions, which a
     pending order doesn't appear in yet. _pending_buy_value_by_ticker()
     below estimates each pending buy's dollar value (from the order's
     own notional/limit_price, falling back to one live quote per
     market-type pending order) and feeds it into validate_trade_intent()
     via the new pending_buy_value_by_ticker parameter (see
     risk/execution_gate.py).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from assistant.policy import TradingPolicy
from assistant.proposal_status import (
    APPROVED,
    BLOCKED,
    EXECUTED,
    RECONCILING,
    SUBMISSION_FAILED,
    SUBMISSION_UNKNOWN,
    SUBMITTING,
    VALIDATING,
    VALIDATION_FAILED,
)
from assistant.schemas import PortfolioSnapshot
from assistant.storage import AssistantStore
from risk.execution_gate import (
    TradeIntent,
    authorize_trade_intent,
    validate_trade_intent,
)

# Sentinel: the broker lookup itself failed (network/auth/5xx/etc.), so
# presence or absence of the order still can't be determined. Distinct
# from `None`, which _lookup_order_outcome() reserves for a CONFIRMED
# absence (the broker's own 404).
_LOOKUP_UNCONFIRMED = object()


class ProposalExecutionError(RuntimeError):
    pass


def _intent_from_dict(raw: dict) -> TradeIntent:
    return TradeIntent(
        ticker=raw["ticker"],
        side=raw["side"],
        shares=int(raw["shares"]),
        order_type=raw.get("order_type", "market"),
        limit_price=raw.get("limit_price"),
        rationale=raw.get("rationale", ""),
    )


def _lookup_order_outcome(broker_module, idempotency_key: str):
    """Classifies a broker order lookup into exactly one of three
    outcomes: the order dict (found), None (the broker CONFIRMS no such
    order exists), or _LOOKUP_UNCONFIRMED (the lookup itself failed --
    still don't know). Callers must branch on all three; treating
    "confirmed absent" and "unconfirmed" the same way was the bug in the
    previous round of fixes."""
    try:
        return broker_module.find_order_by_client_id(idempotency_key)
    except Exception:
        return _LOOKUP_UNCONFIRMED


def _pending_buy_value_by_ticker(open_orders: list[dict], broker_module) -> dict[str, float]:
    """Estimated dollar value of currently pending (not-yet-filled) BUY
    orders, keyed by ticker -- fed into validate_trade_intent()'s
    exposure/concentration checks, which otherwise only see FILLED
    positions and are blind to money already committed by a pending order
    (Codex review, 2026-07-27). Prefers exact values already on the order
    (notional, or shares * limit_price for a limit order); for a plain
    market buy order (no price on the order itself) falls back to one
    live quote per such order. If even that fails, the order is honestly
    skipped (undercounts exposure rather than guessing) -- same "honestly
    unavailable, never guessed" discipline this module already uses for
    earnings data."""
    totals: dict[str, float] = {}
    for order in open_orders:
        if str(order.get("side", "")).lower() != "buy":
            continue
        shares = order.get("shares")
        ticker = order.get("ticker")
        if not shares or not ticker:
            continue
        notional = order.get("notional")
        if notional:
            value = float(notional)
        else:
            limit_price = order.get("limit_price")
            if limit_price:
                value = float(shares) * float(limit_price)
            else:
                try:
                    quote = broker_module.get_latest_quote(ticker)
                    value = float(shares) * float(quote["price"])
                except Exception:
                    continue
        totals[ticker.upper()] = totals.get(ticker.upper(), 0.0) + value
    return totals


def _resolve_earnings_days_away(ticker: str, override: int | None) -> int | None:
    """Caller-supplied override wins (useful for tests / explicit control).
    Otherwise fetch live -- returns None (check skipped) only when the
    data is honestly unavailable, never guessed."""
    if override is not None:
        return override
    try:
        from data.event_data import fetch_upcoming_earnings

        record = fetch_upcoming_earnings([ticker]).get(ticker, {})
        return record.get("days_away") if record.get("available") else None
    except Exception:
        return None


def execute_approved_paper_proposal(
    proposal_id: str,
    confirmation: str,
    current_portfolio: PortfolioSnapshot,
    policy: TradingPolicy,
    store: AssistantStore,
    *,
    now_et: datetime,
    kill_switch_active: bool = False,
    earnings_days_away: int | None = None,
) -> dict:
    """
    Revalidate and submit one proposal.

    The exact confirmation phrase is `APPROVE <proposal_id>`. Proposals
    are single-use, short-lived, and currently restricted to Alpaca paper
    accounts regardless of the global broker configuration.
    """
    # Enforce the environment kill switch here too, not only in callers --
    # a caller that forgets to pass kill_switch_active must not silently
    # bypass it. This makes the switch an invariant of the service itself.
    kill_switch_active = kill_switch_active or os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1"

    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise ProposalExecutionError(f"Unknown proposal: {proposal_id}")
    if confirmation != f"APPROVE {proposal_id}":
        raise ProposalExecutionError("Explicit approval phrase did not match.")
    if policy.execution_mode != "paper":
        raise ProposalExecutionError("The active policy does not permit paper execution.")
    if proposal["policy_version"] != policy.version:
        raise ProposalExecutionError("Proposal policy version does not match the active policy.")

    now_utc = datetime.now(timezone.utc)

    # Atomic claim: proposed -> validating, ONLY if not already expired.
    # Both the claim and the expiry write below are conditioned on the
    # row still being "proposed" at the moment they run, so neither can
    # ever clobber an "executed"/"approved"/"validating"/"submission_failed"
    # status -- a prior version checked expiry with an unconditional write
    # before claiming, which could silently flip an already-executed
    # proposal back to "expired" if approval was invoked again past its
    # expiry window (or race an in-flight claim into "expired" out from
    # under it).
    claimed = store.claim_proposal(
        proposal_id, expected_status="proposed", new_status=VALIDATING, not_expired_after=now_utc.isoformat()
    )
    if claimed is None:
        current = store.get_proposal(proposal_id)
        if (
            current is not None
            and current["status"] == "proposed"
            and now_utc > datetime.fromisoformat(current["expires_at"])
        ):
            store.claim_proposal(proposal_id, expected_status="proposed", new_status="expired")
            raise ProposalExecutionError("Proposal has expired; generate a fresh one.")
        raise ProposalExecutionError(
            f"Proposal {proposal_id} could not be claimed (already being processed, "
            "already executed, or not in a 'proposed' state)."
        )

    import execution.alpaca_broker as broker

    validation = None
    try:
        if not broker.PAPER_TRADING:
            raise ProposalExecutionError("This workflow refuses live trading; PAPER_TRADING must remain True.")
        if not broker.is_configured():
            raise ProposalExecutionError("Alpaca paper credentials are not configured.")
        if not current_portfolio.open_orders_available:
            raise ProposalExecutionError(
                "Cannot verify open orders right now (the broker's order endpoint failed) -- "
                "refusing to approve since the duplicate-order check would be unreliable. Try again shortly."
            )

        intent = _intent_from_dict(proposal["intent"])
        if intent.side not in policy.allowed_sides:
            raise ProposalExecutionError(f"Side '{intent.side}' is not allowed by policy.")
        if intent.order_type not in policy.allowed_order_types:
            raise ProposalExecutionError(f"Order type '{intent.order_type}' is not allowed by policy.")
        if intent.side == "buy" and not policy.allow_new_positions:
            held = {p.ticker.upper() for p in current_portfolio.positions}
            if intent.ticker.upper() not in held:
                raise ProposalExecutionError("Opening new positions is disabled by policy.")

        recent_intents = [_intent_from_dict(raw) for raw in store.recent_executed_intents()]
        for order in current_portfolio.open_orders:
            side = str(order.get("side", "")).lower()
            if side in ("buy", "sell") and order.get("shares"):
                recent_intents.append(
                    TradeIntent(
                        ticker=order["ticker"],
                        side=side,
                        shares=int(float(order["shares"])),
                    )
                )

        try:
            quote = broker.get_latest_quote(intent.ticker)
            reference_price = quote["price"]
            price_timestamp = quote["timestamp"]
            bid_price = quote.get("bid")
            ask_price = quote.get("ask")
        except Exception as exc:
            raise ProposalExecutionError(
                f"Could not fetch a live quote for {intent.ticker} to check price freshness: {exc}"
            )

        resolved_earnings_days_away = _resolve_earnings_days_away(intent.ticker, earnings_days_away)
        if policy.require_earnings_data and intent.side == "buy" and resolved_earnings_days_away is None:
            # A risk-REDUCING sell is exempt: refusing it because earnings
            # data is unavailable would block the very thing that lowers
            # risk. Only opt-in (require_earnings_data=true, off by
            # default) and only for buys. Note: "unavailable" here also
            # covers a ticker whose last known earnings date has simply
            # passed with nothing new scheduled yet, not only a genuine
            # fetch failure -- data/event_data.py doesn't distinguish the
            # two, so this errs toward over-blocking, not under-blocking.
            raise ProposalExecutionError(
                f"Earnings-date data for {intent.ticker} is unavailable and your policy requires it "
                "for buys (require_earnings_data=true) -- refusing to approve rather than silently "
                "skip the earnings blackout check."
            )

        validation = validate_trade_intent(
            intent,
            current_portfolio,
            reference_price,
            price_timestamp=price_timestamp,
            now=now_et,
            recent_intents=recent_intents,
            kill_switch_active=kill_switch_active,
            earnings_days_away=resolved_earnings_days_away,
            bid_price=bid_price,
            ask_price=ask_price,
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
            pending_buy_value_by_ticker=_pending_buy_value_by_ticker(current_portfolio.open_orders, broker),
        )
        if not validation.approved:
            raise ProposalExecutionError(
                "Execution gate blocked the proposal: " + "; ".join(validation.violations)
            )
    except ProposalExecutionError as exc:
        violations = validation.violations if validation is not None and not validation.approved else [str(exc)]
        store.update_proposal_status(proposal_id, BLOCKED, violations=violations)
        raise
    except Exception as exc:
        # Something genuinely unexpected (not a validation/policy
        # rejection) -- do not leave the claimed proposal stranded in
        # "validating" forever with no record of why. Distinct status
        # from "blocked" so this is visibly different from an ordinary
        # policy rejection in the History tab / store.
        store.update_proposal_status(proposal_id, VALIDATION_FAILED, error=str(exc))
        raise

    authorization = authorize_trade_intent(intent, validation)
    store.update_proposal_status(
        proposal_id,
        APPROVED,
        approved_at=now_utc.isoformat(),
        violations=[],
    )

    # "submitting" is written BEFORE the broker call (not just around it)
    # so that even a crash between sending the request and receiving a
    # response leaves a non-terminal status behind, one that the
    # duplicate-order check treats as unresolved broker state rather than
    # silently vanishing back to nothing.
    store.update_proposal_status(proposal_id, SUBMITTING)
    submit = broker.submit_limit_order if intent.order_type == "limit" else broker.submit_market_order
    submit_kwargs = (
        {"limit_price": intent.limit_price} if intent.order_type == "limit" else {}
    )
    try:
        order = submit(
            intent.ticker,
            intent.shares,
            side=intent.side,
            authorization=authorization,
            idempotency_key=proposal["idempotency_key"],
            **submit_kwargs,
        )
    except Exception as exc:
        # An exception here does NOT prove the broker rejected the order --
        # a network timeout, for example, can lose the response after the
        # order was actually accepted. Reconcile by looking the order up
        # under the same idempotency key (client_order_id) before
        # concluding anything -- and treat "confirmed absent" differently
        # from "still don't know" (see _lookup_order_outcome).
        outcome = _lookup_order_outcome(broker, proposal["idempotency_key"])
        if isinstance(outcome, dict):
            store.record_broker_order(proposal_id, outcome)
            store.update_proposal_status(
                proposal_id,
                EXECUTED,
                executed_at=datetime.now(timezone.utc).isoformat(),
                broker_order=outcome,
                reconciled_after_error=str(exc),
            )
            return outcome
        if outcome is None:
            # Confirmed absent: the broker itself says this order was
            # never accepted, so it's safe to call it a real failure
            # rather than leaving it in limbo as "submission_unknown".
            store.update_proposal_status(proposal_id, SUBMISSION_FAILED, error=str(exc))
            raise ProposalExecutionError(
                f"Order submission failed for {proposal_id}, and the broker confirms no such order "
                f"exists ({exc})."
            ) from exc
        store.update_proposal_status(proposal_id, SUBMISSION_UNKNOWN, error=str(exc))
        raise ProposalExecutionError(
            f"Could not confirm whether the order for {proposal_id} was accepted by the broker "
            f"after an error ({exc}). Status is 'submission_unknown' -- run "
            f"`reconcile_submission({proposal_id!r}, store)` (CLI: `reconcile {proposal_id}`) once "
            "connectivity is restored; this ticker/side is treated as a duplicate-order risk until then."
        ) from exc

    try:
        store.record_broker_order(proposal_id, order)
    except Exception as exc:
        # The broker DID accept the order (we got a normal response) --
        # the failure is only in our local journal write. Do not report
        # this as a submission failure; that would misrepresent an order
        # that genuinely exists. Keep the order info in `error` so it can
        # be reconciled/re-journaled manually.
        store.update_proposal_status(
            proposal_id,
            EXECUTED,
            executed_at=datetime.now(timezone.utc).isoformat(),
            broker_order=order,
            error=f"Order was accepted by the broker but local recording failed: {exc}",
        )
        return order

    store.update_proposal_status(
        proposal_id,
        EXECUTED,
        executed_at=datetime.now(timezone.utc).isoformat(),
        broker_order=order,
    )
    return order


def reconcile_submission(proposal_id: str, store: AssistantStore) -> dict:
    """
    Manually resolve a proposal stuck in "submitting" or
    "submission_unknown" -- the only two states a submission-time
    reconciliation attempt can leave behind when it couldn't confirm the
    broker's outcome. Re-running execute_approved_paper_proposal() cannot
    help here: the proposal is no longer "proposed", so it would just be
    rejected as unclaimable. This is the sole path forward short of
    hand-editing the database.

    Re-queries the broker for the same idempotency key (client_order_id)
    and, since a look-alike order under the right key should never
    legitimately have the wrong ticker/side, cross-checks the result
    against the proposal's own stored intent before trusting it -- a
    mismatch is left unresolved (still "submission_unknown") rather than
    silently journaled, since blindly trusting it could misattribute
    someone else's order.

    Outcomes (every one records `reconciled_at` as an audit trail):
      - Order found and matches the proposal's intent: journaled, marked
        "executed".
      - Order found but does NOT match (ticker/side mismatch -- should
        never happen with unique idempotency keys, but this is exactly
        the kind of anomaly that must not be auto-resolved): stays
        "submission_unknown" with the mismatch recorded; raises.
      - Broker confirms (HTTP 404) no such order exists: marked
        "submission_failed" -- it genuinely never went through.
      - The lookup itself still can't confirm either way (network/auth/
        etc.): returned to "submission_unknown", unchanged, safe to
        retry again later.
    """
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise ProposalExecutionError(f"Unknown proposal: {proposal_id}")

    claimed = store.claim_proposal(
        proposal_id, expected_status=(SUBMITTING, SUBMISSION_UNKNOWN), new_status=RECONCILING
    )
    if claimed is None:
        current_status = proposal["status"]
        raise ProposalExecutionError(
            f"Proposal {proposal_id} is not reconcilable (status={current_status!r}) -- reconciliation "
            "only applies to proposals stuck in 'submitting' or 'submission_unknown'."
        )

    import execution.alpaca_broker as broker

    stored_intent = _intent_from_dict(proposal["intent"])
    outcome = _lookup_order_outcome(broker, proposal["idempotency_key"])
    reconciled_at = datetime.now(timezone.utc).isoformat()

    if isinstance(outcome, dict):
        ticker_matches = str(outcome.get("ticker", "")).upper() == stored_intent.ticker.upper()
        side_matches = outcome.get("side") == stored_intent.side
        if not (ticker_matches and side_matches):
            store.update_proposal_status(
                proposal_id,
                SUBMISSION_UNKNOWN,
                reconciled_at=reconciled_at,
                error=(
                    f"Reconciliation found an order under this idempotency key that does NOT match the "
                    f"proposal's intent ({stored_intent.side} {stored_intent.shares} {stored_intent.ticker} "
                    f"expected; broker returned {outcome}) -- refusing to auto-resolve. Investigate manually."
                ),
            )
            raise ProposalExecutionError(
                f"Reconciliation for {proposal_id} found a MISMATCHED order -- left as "
                "'submission_unknown' for manual investigation, not auto-resolved."
            )
        store.record_broker_order(proposal_id, outcome)
        store.update_proposal_status(
            proposal_id, EXECUTED, executed_at=reconciled_at, broker_order=outcome, reconciled_at=reconciled_at,
        )
        return outcome

    if outcome is None:
        store.update_proposal_status(
            proposal_id,
            SUBMISSION_FAILED,
            reconciled_at=reconciled_at,
            error="Reconciliation: the broker confirms no order exists for this idempotency key.",
        )
        raise ProposalExecutionError(
            f"Reconciliation for {proposal_id}: the broker confirms this order was never accepted -- "
            "marked 'submission_failed'."
        )

    # outcome is _LOOKUP_UNCONFIRMED
    store.update_proposal_status(
        proposal_id,
        SUBMISSION_UNKNOWN,
        reconciled_at=reconciled_at,
        error="Reconciliation attempted but the broker lookup itself failed -- still unresolved.",
    )
    raise ProposalExecutionError(
        f"Reconciliation for {proposal_id} could not confirm the broker's outcome (the lookup itself "
        "failed) -- still 'submission_unknown'. Try again once connectivity is restored."
    )
