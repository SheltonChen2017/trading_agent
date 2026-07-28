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

2026-07-27 update (fourth independent GPT review, verified against this
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

2026-07-27 update (fifth independent GPT review, verified against this
code before acting):
 17. _pending_buy_value_by_ticker()'s live-quote fallback used to catch
     any lookup failure and silently drop that order's value to zero --
     undercounting exposure exactly like fix #16 above was meant to
     prevent, just one step removed. The fallback now lets the exception
     propagate, and this module fails the approval closed (for a BUY
     only -- a risk-reducing sell never consults this value) rather than
     silently proceeding with an undercounted exposure figure.

2026-07-28 update (sixth independent GPT review, verified against this
code before acting):
 18. Approval only compared proposal["policy_version"] to policy.version
     as a plain string -- two policy files (e.g. a hand-edited personal
     one copied from the default) could share the same version yet have
     materially different limits, making them silently interchangeable.
     Now also requires proposal["policy_fingerprint"] (a hash over every
     behavior-affecting policy field, see assistant/policy.py's
     compute_policy_fingerprint()) to match the active policy's CURRENT
     fingerprint -- catches an edited-but-not-rebumped policy file
     regardless of whether version was bumped, and fails closed (rather
     than being grandfathered in) for any proposal that predates
     fingerprint binding entirely.

2026-07-28 feature (user-requested, after confirming scope): a policy
block on a concentration cap (position/total-exposure/basket/leveraged-
ETF) or the earnings blackout window can now be knowingly overridden --
these are risk-preference/business-calendar calls, not data-integrity
problems, and the broker itself would still accept the order. Stale
price, closed market, a bad bid/ask quote, a duplicate order, the kill
switch, insufficient cash, and any invalid intent can NEVER be
overridden, even if they co-occur with an overridable violation --
risk.execution_gate.authorize_overridden_trade_intent() independently
re-verifies this itself rather than trusting the caller. The simplified
confirmation phrase (below) also applies: `confirmation` is just
"approve" now, not "APPROVE <proposal_id>" -- the proposal_id is already
the caller-supplied parameter, so the exact phrase no longer needs to
re-encode which proposal is being approved.

2026-07-28 update (seventh independent GPT review, verified before
acting):
 19. Reconciliation (both the submission-error path below and
     reconcile_submission()) only checked ticker+side before trusting a
     broker order found under the expected idempotency key -- so an
     order under that key for BUY 1 AAPL could reconcile a proposal for
     BUY 100 AAPL, or a market order could be mistaken for a limit
     order. execution.alpaca_broker.find_order_by_client_id() now also
     returns order type, limit price, and time_in_force;
     _order_matches_intent() below compares the COMPLETE material
     identity (ticker, side, shares, order type, limit price for limit
     orders) and fails closed on any missing field -- a mismatch is
     never auto-resolved as a match, and numerically-equivalent share
     counts (e.g. 10 vs 10.0) are treated as equal.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone

from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.proposal_status import (
    APPROVED,
    BLOCKED,
    EXECUTED,
    POLICY_OVERRIDE_AVAILABLE,
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
    authorize_overridden_trade_intent,
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


class PolicyOverridableBlockError(ProposalExecutionError):
    """Raised instead of a plain ProposalExecutionError when EVERY
    violation on the rejected validation is override-eligible (see
    risk.execution_gate.ValidationResult.overridable_violations) -- the
    proposal is left in POLICY_OVERRIDE_AVAILABLE (not BLOCKED, which is
    terminal) so a caller can re-invoke with override_policy_violations=
    True to proceed. `overridable_violations` is always the complete
    violations list here, since a mix of overridable and non-overridable
    violations always raises the plain ProposalExecutionError instead."""

    def __init__(self, message: str, overridable_violations: list[str]):
        super().__init__(message)
        self.overridable_violations = overridable_violations


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


def _order_matches_intent(order: dict, intent: TradeIntent) -> tuple[bool, str]:
    """Verifies the COMPLETE material identity of a broker order (as
    returned by execution.alpaca_broker.find_order_by_client_id()) against
    the TradeIntent it's being reconciled against: ticker, side, shares,
    order type, and (for limit orders) limit price. A missing material
    field fails closed -- treated as a mismatch, never assumed to match
    (GPT review, 2026-07-28: a prior version compared only ticker+side, so
    an order under the expected idempotency key for BUY 1 AAPL could
    reconcile a proposal for BUY 100 AAPL, or a market order could be
    mistaken for a limit order). Returns (matches, detail); `detail`
    explains the first mismatch found, for an audit message -- empty
    string when matches is True.

    Share counts use a numeric (not string) comparison so numerically-
    equivalent representations (10 vs 10.0) count as equal; a fractional
    share count is still rejected since this workflow only ever submits
    whole-share orders.
    """
    if str(order.get("ticker", "")).upper() != intent.ticker.upper():
        return False, f"ticker: expected {intent.ticker.upper()!r}, got {order.get('ticker')!r}"
    if order.get("side") != intent.side:
        return False, f"side: expected {intent.side!r}, got {order.get('side')!r}"

    order_shares = order.get("shares")
    if order_shares is None:
        return False, "shares: missing from broker response"
    try:
        order_shares_value = float(order_shares)
    except (TypeError, ValueError):
        return False, f"shares: not numeric ({order_shares!r})"
    if not math.isclose(order_shares_value, float(intent.shares), rel_tol=0.0, abs_tol=1e-9):
        return False, f"shares: expected {intent.shares}, got {order_shares_value}"

    order_type = order.get("type")
    if order_type is None:
        return False, "order type: missing from broker response"
    if str(order_type).lower() != str(intent.order_type).lower():
        return False, f"order type: expected {intent.order_type!r}, got {order_type!r}"

    if intent.order_type == "limit":
        order_limit_price = order.get("limit_price")
        if order_limit_price is None:
            return False, "limit_price: missing from broker response for a limit order"
        try:
            order_limit_price_value = float(order_limit_price)
        except (TypeError, ValueError):
            return False, f"limit_price: not numeric ({order_limit_price!r})"
        if intent.limit_price is None or not math.isclose(
            order_limit_price_value, float(intent.limit_price), rel_tol=0.0, abs_tol=0.005
        ):
            return False, f"limit_price: expected {intent.limit_price}, got {order_limit_price_value}"

    return True, ""


def _pending_buy_value_by_ticker(open_orders: list[dict], broker_module) -> dict[str, float]:
    """Estimated dollar value of currently pending (not-yet-filled) BUY
    orders, keyed by ticker -- fed into validate_trade_intent()'s
    exposure/concentration checks, which otherwise only see FILLED
    positions and are blind to money already committed by a pending order
    (Codex review, 2026-07-27). Prefers exact values already on the order
    (notional, or shares * limit_price for a limit order); for a plain
    market buy order (no price on the order itself) falls back to one
    live quote per such order.

    A notional-only order (Alpaca lets you submit a dollar amount instead
    of a share count -- `shares` is None, `notional` is the real dollar
    value) used to be skipped entirely, because `shares` was checked
    before `notional` -- so a valid notional value was never read (GPT
    review, 2026-07-27). `ticker`/`notional` are now checked first;
    `shares` is only required for the two branches that actually need it
    (shares * limit_price, shares * quote price).

    Deliberately does NOT swallow a quote-fetch failure here -- an earlier
    version caught it and silently dropped that order's value to zero,
    which undercounts real exposure exactly like the bug this function
    exists to fix, just one step removed (GPT review, 2026-07-27). The
    caller is responsible for treating a raised exception as "exposure
    can't be verified right now" and failing the approval closed, the
    same way current_portfolio.open_orders_available already does for the
    duplicate-order check."""
    totals: dict[str, float] = {}
    for order in open_orders:
        if str(order.get("side", "")).lower() != "buy":
            continue
        ticker = order.get("ticker")
        if not ticker:
            continue
        notional = order.get("notional")
        if notional:
            value = float(notional)
        else:
            shares = order.get("shares")
            if not shares:
                continue
            limit_price = order.get("limit_price")
            if limit_price:
                value = float(shares) * float(limit_price)
            else:
                quote = broker_module.get_latest_quote(ticker)
                value = float(shares) * float(quote["price"])
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
    override_policy_violations: bool = False,
) -> dict:
    """
    Revalidate and submit one proposal.

    The exact confirmation phrase is "approve" (case-insensitive). This
    is deliberately no longer "APPROVE <proposal_id>": the proposal_id is
    already a separate, caller-supplied parameter, so the confirmation
    phrase doesn't need to re-encode which proposal is being approved --
    that's chosen by which proposal_id the caller passes in, not by what
    gets typed (2026-07-28, user-requested simplification).

    `override_policy_violations`: if the ONLY reason this proposal would
    be blocked is one or more override-eligible violations (concentration
    caps or the earnings blackout -- see risk.execution_gate.
    ValidationResult.overridable_violations), passing True proceeds
    anyway instead of raising PolicyOverridableBlockError. Any other
    violation (stale price, closed market, a bad quote, a duplicate
    order, the kill switch, insufficient cash) still blocks regardless of
    this flag -- see authorize_overridden_trade_intent()'s docstring.

    Proposals are single-use, short-lived, and currently restricted to
    Alpaca paper accounts regardless of the global broker configuration.
    """
    # Enforce the environment kill switch here too, not only in callers --
    # a caller that forgets to pass kill_switch_active must not silently
    # bypass it. This makes the switch an invariant of the service itself.
    kill_switch_active = kill_switch_active or os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1"

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
    # Also claimable from POLICY_OVERRIDE_AVAILABLE: that status means a
    # PRIOR call found only override-eligible violations and is waiting on
    # a human decision, not a terminal rejection -- re-invoking (with
    # override_policy_violations=True to actually proceed past them, or
    # without it to just re-check) must be able to pick it back up.
    claimed = store.claim_proposal(
        proposal_id,
        expected_status=("proposed", POLICY_OVERRIDE_AVAILABLE),
        new_status=VALIDATING,
        not_expired_after=now_utc.isoformat(),
    )
    if claimed is None:
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
            # Duplicate identity (see validate_trade_intent()'s duplicate
            # check) only depends on ticker + side, never shares -- so a
            # notional-only order (shares=None, a real dollar amount in
            # notional) shouldn't be excluded just because it has no share
            # count. `shares` here is a required TradeIntent field but is
            # otherwise unused by the duplicate check; 1 is a harmless
            # placeholder when the real order has none (GPT review,
            # 2026-07-27: notional-only orders were invisible to duplicate
            # detection).
            if side in ("buy", "sell") and order.get("ticker"):
                recent_intents.append(
                    TradeIntent(
                        ticker=order["ticker"],
                        side=side,
                        shares=int(float(order["shares"])) if order.get("shares") else 1,
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

        # Only buys actually use pending_buy_value_by_ticker (see
        # validate_trade_intent()) -- a risk-reducing sell shouldn't be
        # blocked just because an unrelated pending buy's price couldn't
        # be fetched. For a buy, though, fail closed: an undercounted (or
        # silently zeroed) pending value would defeat the whole point of
        # this check (GPT review, 2026-07-27).
        pending_buy_value_by_ticker: dict[str, float] = {}
        if intent.side == "buy":
            try:
                pending_buy_value_by_ticker = _pending_buy_value_by_ticker(current_portfolio.open_orders, broker)
            except Exception as exc:
                raise ProposalExecutionError(
                    f"Could not determine the dollar value of a pending buy order needed to check "
                    f"exposure/concentration limits: {exc}"
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
            pending_buy_value_by_ticker=pending_buy_value_by_ticker,
        )
        if not validation.approved:
            if not validation.overridable:
                # At least one violation isn't override-eligible (or there
                # are no violations at all, which shouldn't happen for a
                # rejection) -- this is a hard block regardless of
                # override_policy_violations. `.overridable` is computed
                # fresh from validation.violation_codes (which
                # validation_proof cryptographically binds) against the
                # fixed OVERRIDABLE_VIOLATION_CODES constant -- there is
                # no separate mutable field here to trust or mistrust.
                raise ProposalExecutionError(
                    "Execution gate blocked the proposal: " + "; ".join(validation.violations)
                )
            if not override_policy_violations:
                # Every violation is override-eligible, but the caller
                # hasn't confirmed the override yet -- leave this proposal
                # in a distinct, non-terminal, re-claimable status rather
                # than BLOCKED (which is terminal) so a follow-up call
                # with override_policy_violations=True can pick it back up.
                store.update_proposal_status(
                    proposal_id, POLICY_OVERRIDE_AVAILABLE, violations=list(validation.violations)
                )
                raise PolicyOverridableBlockError(
                    "Execution gate blocked this proposal, but every violation is override-eligible "
                    "(a risk-preference or earnings-calendar call, not unreliable data): "
                    + "; ".join(validation.violations),
                    overridable_violations=list(validation.violations),
                )
            # override_policy_violations=True and every violation is
            # override-eligible: fall through to authorize_overridden_
            # trade_intent() below instead of the normal approved path.
    except PolicyOverridableBlockError:
        raise
    except ProposalExecutionError as exc:
        violations = list(validation.violations) if validation is not None and not validation.approved else [str(exc)]
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

    if validation.approved:
        authorization = authorize_trade_intent(intent, validation)
        store.update_proposal_status(
            proposal_id,
            APPROVED,
            approved_at=now_utc.isoformat(),
            violations=[],
        )
    else:
        # Only reachable when override_policy_violations=True and every
        # violation was override-eligible (the branch above already
        # raised for anything else). Audit trail: the overridden
        # violations are recorded on the proposal rather than silently
        # disappearing into an ordinary approval.
        authorization = authorize_overridden_trade_intent(intent, validation)
        store.update_proposal_status(
            proposal_id,
            APPROVED,
            approved_at=now_utc.isoformat(),
            violations=[],
            policy_override={
                "overridden_violations": list(validation.violations),
                "overridden_at": now_utc.isoformat(),
            },
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
            matches, mismatch_detail = _order_matches_intent(outcome, intent)
            if not matches:
                # An order exists under our exact idempotency key but does
                # NOT match what we submitted -- never auto-resolve this;
                # it's exactly the anomaly duplicate-order protection
                # exists to catch (GPT review, 2026-07-28).
                store.update_proposal_status(
                    proposal_id,
                    SUBMISSION_UNKNOWN,
                    error=(
                        f"Order submission raised ({exc}), and the order found under this idempotency "
                        f"key does NOT match the intent (mismatch: {mismatch_detail}) -- refusing to "
                        "auto-resolve. Investigate manually, then use reconcile_submission()."
                    ),
                )
                raise ProposalExecutionError(
                    f"Order submission failed for {proposal_id}, and a MISMATCHED order was found "
                    f"under this idempotency key ({mismatch_detail}) -- left as 'submission_unknown' "
                    "for manual investigation, not auto-resolved."
                ) from exc
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
      - Anything genuinely unexpected after the claim (a malformed
        stored intent, the broker-order journal write failing, an
        unexpected database error, ...): falls back to
        "submission_unknown" too (2026-07-28, GPT review) -- previously
        the proposal was left stranded in "reconciling" with no way to
        retry, since only "submitting"/"submission_unknown" are
        re-claimable. Never converted to "submission_failed": that
        status means the broker CONFIRMED absence, which an unexpected
        local error never establishes. If even that recovery write
        itself fails, this raises a distinct RuntimeError rather than
        silently leaving the proposal claimed with no record of why --
        see recover_stale_reconciliation() below for the crash-recovery
        path this can't cover (no in-process handler survives a crash).
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

    try:
        import execution.alpaca_broker as broker

        stored_intent = _intent_from_dict(proposal["intent"])
        outcome = _lookup_order_outcome(broker, proposal["idempotency_key"])
        reconciled_at = datetime.now(timezone.utc).isoformat()

        if isinstance(outcome, dict):
            matches, mismatch_detail = _order_matches_intent(outcome, stored_intent)
            if not matches:
                expected_desc = f"{stored_intent.side} {stored_intent.shares} {stored_intent.ticker} {stored_intent.order_type}"
                if stored_intent.order_type == "limit":
                    expected_desc += f" @ {stored_intent.limit_price}"
                store.update_proposal_status(
                    proposal_id,
                    SUBMISSION_UNKNOWN,
                    reconciled_at=reconciled_at,
                    error=(
                        f"Reconciliation found an order under this idempotency key that does NOT match the "
                        f"proposal's intent (mismatch: {mismatch_detail}; expected {expected_desc}; broker "
                        f"returned {outcome}) -- refusing to auto-resolve. Investigate manually."
                    ),
                )
                raise ProposalExecutionError(
                    f"Reconciliation for {proposal_id} found a MISMATCHED order ({mismatch_detail}) -- left "
                    "as 'submission_unknown' for manual investigation, not auto-resolved."
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
    except ProposalExecutionError:
        raise
    except Exception as exc:
        # Genuinely unexpected: a malformed stored intent, the broker-
        # order journal write failing, an unexpected database error, etc.
        # Never leave the proposal stranded in "reconciling" (unretriable
        # via the normal interface), and never claim "submission_failed"
        # -- that status specifically means the broker CONFIRMED absence,
        # which an unexpected local error never establishes.
        try:
            store.update_proposal_status(
                proposal_id,
                SUBMISSION_UNKNOWN,
                reconciled_at=datetime.now(timezone.utc).isoformat(),
                error=f"Unexpected error during reconciliation: {exc}",
            )
        except Exception as write_exc:
            raise RuntimeError(
                f"CRITICAL: reconciliation for {proposal_id} failed unexpectedly ({exc!r}), and recording "
                f"that failure ALSO failed ({write_exc!r}) -- this proposal is likely stranded in "
                "'reconciling'. The broker outcome is NOT known; do not assume success or failure. Manual "
                "database intervention, or recover_stale_reconciliation() once it's old enough, will be "
                "needed."
            ) from exc
        raise ProposalExecutionError(
            f"Reconciliation for {proposal_id} failed unexpectedly ({exc}) -- marked 'submission_unknown' "
            "rather than left stranded in 'reconciling'. The broker outcome is not known; retry once the "
            "underlying issue is fixed."
        ) from exc


def recover_stale_reconciliation(
    proposal_id: str, store: AssistantStore, stale_after_seconds: int = 300,
) -> dict:
    """
    Recovers a proposal stranded in "reconciling" after a crash left no
    in-process handler to run reconcile_submission()'s own recovery logic
    (an ordinary exception inside that function already falls back to
    "submission_unknown" itself -- see its docstring; this function only
    matters when the PROCESS died mid-reconciliation, before any handler
    could run at all).

    Only recovers a proposal that has been sitting in "reconciling" since
    before `stale_after_seconds` ago (measured against `updated_at`, which
    every status transition -- including the claim into "reconciling" --
    rewrites) -- a recent claim is presumed to be a genuinely in-flight
    attempt, not stranded, and is left untouched. Uses the same atomic
    conditional-UPDATE pattern as claim_proposal(), so two concurrent
    recovery attempts (or a recovery racing a real in-flight
    reconciliation) can never both "win" (2026-07-28, GPT review).

    Recovers to "submission_unknown" (never "submission_failed" -- a
    stranded local process proves nothing about what the broker actually
    did), leaving the proposal retryable via reconcile_submission().
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)).isoformat()
    recovered = store.reclaim_stale_status(
        proposal_id, expected_status=RECONCILING, new_status=SUBMISSION_UNKNOWN, stale_before=cutoff,
    )
    if recovered is None:
        current = store.get_proposal(proposal_id)
        if current is None:
            raise ProposalExecutionError(f"Unknown proposal: {proposal_id}")
        raise ProposalExecutionError(
            f"Proposal {proposal_id} is not a stale 'reconciling' proposal (status={current['status']!r}) "
            f"-- either it's not in 'reconciling', or it was claimed less than {stale_after_seconds}s ago "
            "and is presumed to be a genuinely in-flight reconciliation, not stranded."
        )
    recovered_at = datetime.now(timezone.utc).isoformat()
    return store.update_proposal_status(
        proposal_id,
        SUBMISSION_UNKNOWN,
        recovered_at=recovered_at,
        error=(
            f"Recovered from a stale 'reconciling' status (no update for at least "
            f"{stale_after_seconds}s, most likely a process crash mid-reconciliation) -- marked "
            "'submission_unknown' so it can be reconciled again."
        ),
    )
