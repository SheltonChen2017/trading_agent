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
     the order is journaled in its real broker lifecycle state (acceptance
     is not treated as a fill). If the lookup itself can't confirm either way, the
     proposal is marked "submission_unknown" (a distinct, non-terminal
     status) instead of "submission_failed" -- and AssistantStore.
     recent_executed_intents() now also treats "submitting"/
     "submission_unknown" proposals as live duplicate-order risk, so a
     regenerated proposal for the same ticker/side is blocked until a
     human reconciles the unknown proposal against the actual Alpaca
     account. A "submitting" status is written just before the broker
     call for the same reason -- so even a crash between the call and the
     response leaves a non-terminal, duplicate-blocking status behind
     instead of nothing. A local lifecycle-projection failure AFTER a
     confirmed broker acceptance is also handled separately: the proposal still
     preserves the working broker order (without claiming it filled) with the local
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

import dataclasses
import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone

from assistant.order_lifecycle import (
    journal_broker_order_update,
    proposal_status_for_order,
    CHAIN_ERROR_IDENTITY_MISMATCH,
    resolve_replacement_chain,
)
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.proposal_status import (
    APPROVED,
    BLOCKED,
    POLICY_OVERRIDE_AVAILABLE,
    RECONCILING,
    SUBMISSION_UNKNOWN,
    SUBMITTING,
    VALIDATING,
    VALIDATION_FAILED,
)
from assistant.schemas import PortfolioSnapshot
from assistant.storage import AssistantStore
from risk.execution_gate import (
    TradeIntent,
    ValidationResult,
    authorize_overridden_trade_intent,
    authorize_trade_intent,
    intent_fingerprint,
    validate_trade_intent,
    worst_case_fill_price,
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
    violations always raises the plain ProposalExecutionError instead.

    `conditions_changed` (GPT review, 2026-07-30): True only when the
    caller DID pass override_policy_violations=True, a PRIOR reviewed-
    override record existed for this proposal, and the current
    violations no longer match that prior record -- i.e. the human's
    earlier review no longer describes what would actually be overridden
    right now. False for an ordinary first-time presentation (nothing to
    compare against yet) and for a plain non-override check. Callers
    (CLI, UI) should show a distinctly different message in this case --
    "the conditions changed, review again" rather than "every violation
    is override-eligible, rerun with --override"."""

    def __init__(self, message: str, overridable_violations: list[str], conditions_changed: bool = False):
        super().__init__(message)
        self.overridable_violations = overridable_violations
        self.conditions_changed = conditions_changed


def _review_digest(intent: TradeIntent, violation_codes: tuple[str, ...], violations: tuple[str, ...]) -> str:
    """Fingerprint over the EXACT trade intent plus the EXACT set of
    override-eligible violations (both stable codes AND human-readable
    messages, each canonically sorted so no ordering artifact can ever
    cause a spurious mismatch) that a human has been shown before
    requesting an override (GPT review, 2026-07-30: `override_policy_
    violations=True` used to be treated as blanket permission to accept
    WHATEVER override-eligible conditions happened to exist at the later
    execution instant, not specifically the ones actually reviewed).
    Hashing the messages too, not just the codes, matters: the same code
    (e.g. max_position_pct) can represent materially different severity
    as the underlying numbers change -- a position slightly over the cap
    is not the same reviewed risk as one dramatically over it, and the
    human-readable message is what carries that number."""
    payload = {
        "intent_fingerprint": intent_fingerprint(intent),
        "violation_codes": sorted(violation_codes),
        "violations": sorted(violations),
    }
    serialized = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _shares_from_stored_value(raw_shares: object) -> int:
    """Converts a stored proposal's `shares` field to an int WITHOUT ever
    silently truncating a malformed value -- a bare `int(raw["shares"])`
    used to turn a corrupted or hand-edited row's `shares: 1.9` into `1`
    with no error at all (GPT review, 2026-07-29: `int()` truncates
    toward zero rather than rejecting a non-whole value). Raises
    ValueError (caught by this module's callers, which already treat a
    malformed stored intent as a hard, fail-closed error) for anything
    that isn't a real whole-share quantity: a bool, a non-finite float, a
    fractional float, or a non-numeric value."""
    if isinstance(raw_shares, bool):
        raise ValueError(f"Stored shares value is a bool ({raw_shares!r}), not a share quantity.")
    if isinstance(raw_shares, int):
        return raw_shares
    if isinstance(raw_shares, float):
        if not math.isfinite(raw_shares):
            raise ValueError(f"Stored shares value is not finite: {raw_shares!r}.")
        if not raw_shares.is_integer():
            raise ValueError(
                f"Stored shares value {raw_shares!r} is fractional, not a whole share count -- refusing "
                "to silently truncate it."
            )
        return int(raw_shares)
    raise ValueError(f"Stored shares value {raw_shares!r} ({type(raw_shares).__name__}) is not numeric.")


def _intent_from_dict(raw: dict) -> TradeIntent:
    return TradeIntent(
        ticker=raw["ticker"],
        side=raw["side"],
        shares=_shares_from_stored_value(raw["shares"]),
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


def _authoritative_order_for(
    broker_module, order: dict, intent: TradeIntent
) -> tuple[dict | None, str | None, bool, tuple[str, ...]]:
    """
    Resolve a looked-up order through its replacement chain.

    Returns `(authoritative_order, error, is_identity_mismatch, chain)`.

    Both of this module's broker-lookup consumers need this:
    reconcile_submission() (the user-facing manual operation) and
    submit_approved_proposal()'s post-exception recovery. Neither followed
    `replaced_by`, so each validated and journaled the SUPERSEDED order --
    and because the original order still matches the stored intent (only its
    status is "replaced"), the identity check passed and nothing looked wrong.
    A human could re-run manual reconciliation indefinitely and stay pinned to
    a dead order while its replacement had already filled (independent review,
    2026-07-29, reproduced: returned order-1, status submission_unknown, zero
    replacement lookups).

    Delegates to order_lifecycle.resolve_replacement_chain() -- the same
    resolver startup polling uses, deliberately not a second implementation --
    injecting _order_matches_intent so EVERY hop is validated, not just the
    final order.
    """
    resolution = resolve_replacement_chain(
        order,
        # Lazy for the same reason as order_reconciler's adapter: never touch
        # get_order_by_id unless a replacement actually has to be fetched.
        lambda oid: broker_module.get_order_by_id(oid),
        validate=lambda candidate: _order_matches_intent(candidate, intent),
    )
    if resolution.error is not None:
        return (
            None,
            resolution.error,
            resolution.error_kind == CHAIN_ERROR_IDENTITY_MISMATCH,
            resolution.chain,
        )
    return resolution.authoritative_order, None, False, resolution.chain


def _execution_budget_notional(
    intent: TradeIntent, reference_price: float
) -> float:
    """Gross submitted notional reserved against the persistent daily cap.

    This intentionally uses the same side-aware price as the risk gate:
    an aggressive BUY limit is priced at the higher limit, while a SELL
    remains at the reference price so a risk-reducing order is not blocked
    merely because its limit is above the quote.
    """
    return float(
        intent.shares * worst_case_fill_price(intent, reference_price)
    )


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
    (Codex review, 2026-07-27). Risk-adjacent but intentionally NOT in
    risk/execution_gate.py -- see that module's "Known scatter points"
    note and docs/ARCHITECTURE_DEBT.md. Prefers exact values already on the order
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
        # Only the UNFILLED remainder is still pending. The filled portion of
        # a partially-filled buy is already sitting in portfolio.positions, so
        # counting the original quantity here double-counts it and can block
        # unrelated purchases that are actually within policy (GPT review,
        # 2026-07-29).
        #
        # A non-finite/absent filled_qty is treated as 0 -- i.e. the FULL order
        # stays counted. That is the conservative direction (it overstates
        # pending exposure and blocks more, rather than understating it and
        # permitting more), matching this function's fail-closed contract for
        # quote failures described above.
        raw_filled = order.get("filled_qty")
        try:
            filled_qty = float(raw_filled) if raw_filled else 0.0
        except (TypeError, ValueError):
            filled_qty = 0.0
        if not math.isfinite(filled_qty) or filled_qty < 0:
            filled_qty = 0.0

        notional = order.get("notional")
        if notional:
            value = float(notional)
            # A notional order carries no share count, so net out the filled
            # dollars directly. Without a usable fill price the full notional
            # stays counted (again, the conservative direction).
            raw_fill_price = order.get("filled_avg_price")
            try:
                fill_price = float(raw_fill_price) if raw_fill_price else 0.0
            except (TypeError, ValueError):
                fill_price = 0.0
            if math.isfinite(fill_price) and fill_price > 0:
                value = max(0.0, value - filled_qty * fill_price)
        else:
            shares = order.get("shares")
            if not shares:
                continue
            remaining_shares = float(shares) - filled_qty
            if not math.isfinite(remaining_shares) or remaining_shares <= 0:
                continue
            limit_price = order.get("limit_price")
            if limit_price:
                value = remaining_shares * float(limit_price)
            else:
                quote = broker_module.get_latest_quote(ticker)
                value = remaining_shares * float(quote["price"])
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


@dataclasses.dataclass(frozen=True)
class ProposalValidationOutcome:
    """
    Pure, side-effect-free result of checking whether a proposal is
    currently eligible to execute -- never claims, never writes proposal
    status, never submits, never authorizes. Used by BOTH
    execute_approved_paper_proposal() (immediately after its own atomic
    claim) and preflight_allocation_batch() (read-only, no claim at all)
    (2026-07-29, GPT review): these two had started to drift, since
    preflight only duplicated PART of the real execution path's checks
    (missing policy version/fingerprint, execution_mode, paper mode,
    open_orders_available, allowed sides/types, allow_new_positions,
    require_earnings_data) -- this function is now the single source of
    truth both consume, so they can no longer disagree.

    Deliberately does NOT check whether the proposal's CURRENT status is
    claimable ("proposed"/"override_available") -- that's inherently a
    claim-time race the caller must still resolve atomically via
    store.claim_proposal() (the real execution path) or a plain read
    filtered by status (preflight, which must never mutate anything);
    this function only answers "would every OTHER check pass right now."
    """
    proposal: dict | None
    intent: TradeIntent | None
    validation: ValidationResult | None
    # Non-None iff a hard service-level failure occurred before
    # validate_trade_intent() could even run (unknown proposal, expired,
    # policy mismatch, disallowed side, quote fetch failure, ...) --
    # `validation` is then also None. Never override-eligible.
    error: str | None
    # The live quote price actually used (None iff `error` is set before a
    # quote could be fetched). Exposed so a caller simulating a SEQUENCE
    # of proposals (assistant.allocation_batch's cumulative preflight) can
    # compute this leg's planned notional to reserve against the next
    # leg's projected portfolio, without re-fetching the same quote.
    reference_price: float | None = None

    @property
    def approved(self) -> bool:
        if self.error is not None:
            return False
        return self.validation is not None and self.validation.approved

    @property
    def overridable(self) -> bool:
        if self.error is not None:
            return False
        return self.validation is not None and self.validation.overridable

    @property
    def violation_messages(self) -> list[str]:
        if self.error is not None:
            return [self.error]
        if self.validation is not None:
            return list(self.validation.violations)
        return []


def validate_proposal_for_execution(
    proposal_id: str,
    current_portfolio: PortfolioSnapshot,
    policy: TradingPolicy,
    store: AssistantStore,
    *,
    now_et: datetime,
    kill_switch_active: bool = False,
    earnings_days_away: int | None = None,
    proposal: dict | None = None,
    extra_pending_buy_value_by_ticker: dict[str, float] | None = None,
    available_cash_override: float | None = None,
    available_buying_power_override: float | None = None,
) -> ProposalValidationOutcome:
    """
    Checks, in the same order execute_approved_paper_proposal() always
    has: existence, expiration, policy version/fingerprint, execution
    mode, paper-broker mode/configuration, open-order availability, side/
    order-type/new-position policy rules, quote freshness inputs, pending
    -order exposure, the earnings-data requirement, and finally
    validate_trade_intent() itself. Pass an already-fetched `proposal`
    dict when the caller has just claimed/read one (avoids a redundant
    re-fetch); otherwise it's loaded fresh via store.get_proposal().

    `extra_pending_buy_value_by_ticker`: additional simulated pending-buy
    value to add on top of whatever's derived from
    current_portfolio.open_orders -- lets a caller simulating a SEQUENCE
    of proposals (assistant.allocation_batch's cumulative preflight)
    reserve earlier legs' planned notional against later legs' exposure/
    concentration checks, without this function needing to know anything
    about batches itself. None/empty for the real single-proposal
    execution path (unaffected, backward compatible).

    `available_cash_override`/`available_buying_power_override`: passed
    straight through to validate_trade_intent() (see its docstring) --
    lets the SAME caller tighten cash/buying-power availability to
    reflect earlier reserved legs WITHOUT touching `current_portfolio.
    cash`/`buying_power` themselves, since those two also feed the
    exposure-side arithmetic there and must stay at their real,
    unreserved values to avoid double-counting a reservation (GPT review,
    2026-07-29: passing a `dataclasses.replace()`'d portfolio with cash
    already reduced counted each earlier leg twice -- once via the
    shrunk cash figure, once via `extra_pending_buy_value_by_ticker`).
    None (the default) for both preserves exact single-proposal-execution
    behavior.
    """
    try:
        persistent_kill_switch = store.get_kill_switch()
    except Exception as exc:
        return ProposalValidationOutcome(
            proposal=proposal,
            intent=None,
            validation=None,
            error=f"Could not verify the persistent kill switch: {exc}",
        )
    kill_switch_active = (
        kill_switch_active
        or os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1"
        or bool(persistent_kill_switch.get("active"))
    )
    if proposal is None:
        proposal = store.get_proposal(proposal_id)
    if proposal is None:
        return ProposalValidationOutcome(
            proposal=None, intent=None, validation=None, error=f"Unknown proposal: {proposal_id}"
        )

    now_utc = datetime.now(timezone.utc)
    if now_utc > datetime.fromisoformat(proposal["expires_at"]):
        return ProposalValidationOutcome(proposal=proposal, intent=None, validation=None, error="Proposal has expired.")
    if policy.execution_mode != "paper":
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None,
            error="The active policy does not permit paper execution.",
        )
    if proposal["policy_version"] != policy.version:
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None,
            error="Proposal policy version does not match the active policy.",
        )
    if proposal.get("policy_fingerprint") != compute_policy_fingerprint(policy):
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None,
            error=(
                "Proposal's policy fingerprint does not match the active policy's current content -- the "
                "policy may have been edited without a version bump (or this proposal predates fingerprint "
                "binding). Regenerate the proposal against the current policy."
            ),
        )

    import execution.alpaca_broker as broker

    if not broker.PAPER_TRADING:
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None,
            error="This workflow refuses live trading; PAPER_TRADING must remain True.",
        )
    if not broker.is_configured():
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None, error="Alpaca paper credentials are not configured.",
        )
    if kill_switch_active:
        reason = str(persistent_kill_switch.get("reason") or "active")
        return ProposalValidationOutcome(
            proposal=proposal,
            intent=None,
            validation=None,
            error=f"The execution kill switch is active ({reason}).",
        )
    if not current_portfolio.open_orders_available:
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None,
            error=(
                "Cannot verify open orders right now (the broker's order endpoint failed) -- refusing to "
                "approve since the duplicate-order check would be unreliable. Try again shortly."
            ),
        )
    if len(current_portfolio.open_orders) >= policy.max_open_orders:
        return ProposalValidationOutcome(
            proposal=proposal,
            intent=None,
            validation=None,
            error=(
                f"Open-order cap reached: {len(current_portfolio.open_orders)} active order(s), "
                f"policy maximum {policy.max_open_orders}."
            ),
        )

    try:
        intent = _intent_from_dict(proposal["intent"])
    except Exception as exc:
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None, error=f"Malformed stored intent: {exc}",
        )

    if intent.side not in policy.allowed_sides:
        return ProposalValidationOutcome(
            proposal=proposal, intent=intent, validation=None,
            error=f"Side '{intent.side}' is not allowed by policy.",
        )
    if intent.order_type not in policy.allowed_order_types:
        return ProposalValidationOutcome(
            proposal=proposal, intent=intent, validation=None,
            error=f"Order type '{intent.order_type}' is not allowed by policy.",
        )
    if intent.side == "buy" and not policy.allow_new_positions:
        held = {p.ticker.upper() for p in current_portfolio.positions}
        if intent.ticker.upper() not in held:
            return ProposalValidationOutcome(
                proposal=proposal, intent=intent, validation=None,
                error="Opening new positions is disabled by policy.",
            )

    try:
        broker.assert_account_and_asset_ready(intent.ticker)
    except Exception as exc:
        return ProposalValidationOutcome(
            proposal=proposal,
            intent=intent,
            validation=None,
            error=f"Broker account/asset preflight failed: {exc}",
        )

    try:
        recent_intents = [_intent_from_dict(raw) for raw in store.recent_executed_intents()]
    except Exception as exc:
        # A malformed HISTORICAL row (e.g. a hand-edited or corrupted
        # shares value now caught by _shares_from_stored_value()) must
        # fail this proposal closed the same way a malformed CURRENT
        # intent already does above, not raise uncaught out of this
        # read-only function (preflight_allocation_batch() calls this
        # directly, with no surrounding try/except of its own).
        return ProposalValidationOutcome(
            proposal=proposal, intent=intent, validation=None,
            error=f"Could not check recent order history for duplicates: malformed stored intent: {exc}",
        )
    for order in current_portfolio.open_orders:
        side = str(order.get("side", "")).lower()
        # See execute_approved_paper_proposal()'s own duplicate-check
        # comment: identity depends only on ticker+side, never shares.
        if side in ("buy", "sell") and order.get("ticker"):
            recent_intents.append(
                TradeIntent(
                    ticker=order["ticker"], side=side,
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
        return ProposalValidationOutcome(
            proposal=proposal, intent=intent, validation=None,
            error=f"Could not fetch a live quote for {intent.ticker} to check price freshness: {exc}",
        )

    pending_buy_value_by_ticker: dict[str, float] = {}
    if intent.side == "buy":
        try:
            pending_buy_value_by_ticker = dict(_pending_buy_value_by_ticker(current_portfolio.open_orders, broker))
        except Exception as exc:
            return ProposalValidationOutcome(
                proposal=proposal, intent=intent, validation=None,
                error=(
                    f"Could not determine the dollar value of a pending buy order needed to check "
                    f"exposure/concentration limits: {exc}"
                ),
                reference_price=reference_price,
            )
        for ticker, extra_value in (extra_pending_buy_value_by_ticker or {}).items():
            key = ticker.upper()
            pending_buy_value_by_ticker[key] = pending_buy_value_by_ticker.get(key, 0.0) + extra_value

    resolved_earnings_days_away = _resolve_earnings_days_away(intent.ticker, earnings_days_away)
    if policy.require_earnings_data and intent.side == "buy" and resolved_earnings_days_away is None:
        return ProposalValidationOutcome(
            proposal=proposal, intent=intent, validation=None,
            error=(
                f"Earnings-date data for {intent.ticker} is unavailable and your policy requires it "
                "for buys (require_earnings_data=true) -- refusing to approve rather than silently "
                "skip the earnings blackout check."
            ),
            reference_price=reference_price,
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
        available_cash_override=available_cash_override,
        available_buying_power_override=available_buying_power_override,
    )
    return ProposalValidationOutcome(
        proposal=proposal, intent=intent, validation=validation, error=None, reference_price=reference_price,
    )


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
    ValidationResult.overridable_violations), passing True proceeds --
    but ONLY if the CURRENT violations (revalidated fresh against
    `current_portfolio`/live quote, right now) exactly match a
    PREVIOUSLY-STORED reviewed-override record for this proposal (GPT
    review, 2026-07-30: passing True used to be treated as blanket
    permission to accept whatever override-eligible conditions happened
    to exist at the later execution instant, not specifically the ones a
    human actually reviewed -- a position-cap violation could become
    materially more severe, a basket/leveraged-ETF/earnings violation
    could newly appear, or one override-eligible violation could be
    replaced by another, all between an initial PolicyOverridableBlockError
    and a later `override_policy_violations=True` call, with nothing
    checking that the human saw the SAME set before accepting it).

    Concretely: every time this proposal is blocked ONLY by override-
    eligible violations, the service stores a reviewed-override record
    (the trade intent's fingerprint plus canonically-ordered violation
    codes/messages) and raises PolicyOverridableBlockError -- REGARDLESS
    of whether the caller already passed `override_policy_violations=
    True`. Only a SECOND call, with that flag set, whose freshly
    revalidated violations produce the exact same digest as the stored
    record, actually proceeds to authorization. A digest mismatch (first
    presentation, or the reviewed conditions changed) always re-stores
    the new record and raises again -- `PolicyOverridableBlockError.
    conditions_changed` distinguishes "changed since a prior review" from
    "first presentation" for caller messaging. Any non-overridable
    violation (stale price, closed market, a bad quote, a duplicate
    order, the kill switch, insufficient cash, invalid quantities) still
    hard-blocks regardless of any of this -- see
    authorize_overridden_trade_intent()'s docstring.

    Proposals are single-use, short-lived, and currently restricted to
    Alpaca paper accounts regardless of the global broker configuration.
    """
    # Enforce the environment kill switch here too, not only in callers --
    # a caller that forgets to pass kill_switch_active must not silently
    # bypass it. This makes the switch an invariant of the service itself.
    try:
        persistent_kill_switch = store.get_kill_switch()
    except Exception as exc:
        raise ProposalExecutionError(
            f"Could not verify the persistent kill switch; refusing execution: {exc}"
        ) from exc
    kill_switch_active = (
        kill_switch_active
        or os.environ.get("TRADING_ASSISTANT_KILL_SWITCH") == "1"
        or bool(persistent_kill_switch.get("active"))
    )

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
    intent = None
    reference_price = None
    try:
        validation_outcome = validate_proposal_for_execution(
            proposal_id,
            current_portfolio,
            policy,
            store,
            now_et=now_et,
            kill_switch_active=kill_switch_active,
            earnings_days_away=earnings_days_away,
            proposal=proposal,
        )
        if validation_outcome.error is not None:
            # Every check up through validate_trade_intent() lives in
            # validate_proposal_for_execution() now (2026-07-29, GPT
            # review) -- shared with preflight_allocation_batch() so the
            # two can never drift again the way they had (preflight was
            # missing several of these checks).
            raise ProposalExecutionError(validation_outcome.error)
        intent = validation_outcome.intent
        validation = validation_outcome.validation
        reference_price = validation_outcome.reference_price
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
            # Reviewed-override binding (GPT review, 2026-07-30): a
            # digest match against the LAST reviewed-override record
            # stored on this proposal is required, in addition to
            # override_policy_violations=True, before proceeding --
            # otherwise this always (re-)stores the current violations as
            # the new record to review and raises, never silently
            # escalating to an authorization based on conditions the
            # human hasn't specifically seen and accepted. `proposal`
            # here is the snapshot fetched BEFORE this call's atomic
            # claim, so `reviewed_override` reflects whatever a PRIOR
            # call stored -- claim_proposal() never touches payload_json.
            current_digest = _review_digest(intent, validation.violation_codes, validation.violations)
            previous_reviewed = proposal.get("reviewed_override")
            reviewed_matches = (
                override_policy_violations
                and previous_reviewed is not None
                and previous_reviewed.get("review_digest") == current_digest
            )
            if not reviewed_matches:
                conditions_changed = (
                    override_policy_violations
                    and previous_reviewed is not None
                    and previous_reviewed.get("review_digest") != current_digest
                )
                store.update_proposal_status(
                    proposal_id,
                    POLICY_OVERRIDE_AVAILABLE,
                    violations=list(validation.violations),
                    reviewed_override={
                        "intent_fingerprint": intent_fingerprint(intent),
                        "violation_codes": sorted(validation.violation_codes),
                        "violations": sorted(validation.violations),
                        "review_digest": current_digest,
                        # KNOWN LIMITATION (GPT review, 2026-07-31, not
                        # fixed -- dormant/architectural, not currently
                        # exploitable through either real caller): this
                        # timestamp is recorded the moment the SERVICE
                        # computes the block, not necessarily the moment
                        # a human actually saw it rendered on a screen.
                        # The two-call digest-match convention proves the
                        # SECOND call's violations exactly match what was
                        # stored on a PRIOR call, but does not
                        # cryptographically prove a human visually
                        # reviewed them in between -- a hypothetical
                        # future programmatic caller invoking this
                        # function twice in a tight loop with identical
                        # conditions would satisfy the digest match
                        # without any human ever seeing the first block.
                        # Both real callers today (the CLI, which
                        # requires a separate `approve ... --override`
                        # process re-invocation, and the UI, which
                        # requires clicking a button and then typing a
                        # distinct order-specific phrase into a text box)
                        # already require a genuine human action between
                        # the two calls, so this isn't currently
                        # exploitable -- but a fully rigorous fix would
                        # replace this convention with a signed, single-
                        # use challenge token returned to the caller after
                        # presentation and required back verbatim on the
                        # override call, rather than relying on that
                        # assumption. Revisit before exposing this
                        # override path through any new (e.g.
                        # programmatic/API) caller.
                        "presented_at": now_utc.isoformat(),
                    },
                )
                raise PolicyOverridableBlockError(
                    "Execution gate blocked this proposal, but every violation is override-eligible "
                    "(a risk-preference or earnings-calendar call, not unreliable data): "
                    + "; ".join(validation.violations),
                    overridable_violations=list(validation.violations),
                    conditions_changed=conditions_changed,
                )
            # override_policy_violations=True, every violation is
            # override-eligible, AND the current violations exactly match
            # what was previously reviewed: fall through to
            # authorize_overridden_trade_intent() below instead of the
            # normal approved path.
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

    # Enter a reconcilable state before the last local operations preceding
    # submission. If the process dies after this write, startup polling can
    # safely prove broker absence instead of leaving an "approved" proposal
    # with a stranded reservation and no recovery path.
    store.update_proposal_status(proposal_id, SUBMITTING)

    try:
        store.reserve_execution_budget(
            proposal_id,
            trading_day=now_et.date().isoformat(),
            notional=_execution_budget_notional(intent, reference_price),
            max_daily_notional=policy.max_daily_submitted_notional,
            max_daily_orders=policy.max_daily_order_count,
        )
    except Exception as exc:
        message = f"Persistent daily execution budget blocked submission: {exc}"
        store.update_proposal_status(proposal_id, BLOCKED, violations=[message])
        raise ProposalExecutionError(message) from exc

    # Dispatch explicitly rather than "limit, else market". Two upstream
    # layers already prevent anything else reaching here (policy.validate()
    # rejects an allowed_order_types outside SUPPORTED_ORDER_TYPES, and the
    # allowed_order_types check above blocks the proposal), but
    # risk/execution_gate.py's validate_trade_intent() DOES still approve
    # order_type="stop" -- it is a lower layer with no view of policy. Under
    # the old else-branch such an intent would have been silently submitted
    # as a MARKET order, i.e. an unbounded-price order where a stop was
    # intended. Fail closed instead, so adding a new order type can never
    # silently degrade into a market order (independent review, 2026-07-29).
    if intent.order_type == "limit":
        submit = broker.submit_limit_order
        submit_kwargs = {"limit_price": intent.limit_price}
    elif intent.order_type == "market":
        submit = broker.submit_market_order
        submit_kwargs = {}
    else:
        message = (
            f"No broker submission path implements order_type={intent.order_type!r}; refusing to "
            "submit rather than silently downgrading it to a market order."
        )
        store.update_proposal_status(proposal_id, BLOCKED, violations=[message])
        store.release_execution_reservation(proposal_id)
        raise ProposalExecutionError(message)
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
                reason = (
                    f"Order submission raised ({exc}), and the order found under this idempotency "
                    f"key does NOT match the intent (mismatch: {mismatch_detail}) -- refusing to "
                    "auto-resolve. Persistent kill switch activated; investigate manually."
                )
                store.update_proposal_status_if_current(
                    proposal_id,
                    expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
                    new_status=SUBMISSION_UNKNOWN,
                    error=reason,
                )
                store.set_kill_switch(True, reason=reason)
                raise ProposalExecutionError(
                    f"Order submission failed for {proposal_id}, and a MISMATCHED order was found "
                    f"under this idempotency key ({mismatch_detail}) -- left as 'submission_unknown' "
                    "for manual investigation, not auto-resolved."
                ) from exc
            # Same replacement-chain resolution as manual reconciliation: the
            # order found under our idempotency key could already have been
            # replaced out of band between the failed submit and this lookup.
            # Narrower window than reconcile_submission()'s, but the identical
            # defect -- journaling a superseded order as the outcome.
            authoritative, chain_error, is_mismatch, chain = _authoritative_order_for(
                broker, outcome, intent
            )
            if chain_error is not None:
                reason = (
                    f"Order submission raised ({exc}), and the replacement chain for the order found "
                    f"under this idempotency key could not be trusted: {chain_error}. "
                    + ("Persistent kill switch activated; investigate manually."
                       if is_mismatch else "Left retryable as 'submission_unknown'.")
                )
                store.update_proposal_status_if_current(
                    proposal_id,
                    expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
                    new_status=SUBMISSION_UNKNOWN,
                    error=reason,
                )
                if is_mismatch:
                    store.set_kill_switch(True, reason=reason)
                raise ProposalExecutionError(reason) from exc

            journal_broker_order_update(
                store,
                proposal_id,
                authoritative,
                event_type="submission_reconciled",
                clear_error=True,
                extra_updates={"reconciled_after_error": str(exc)},
                raw_event={"replacement_chain": list(chain)} if chain else None,
            )
            return authoritative
        if outcome is None:
            # Confirmed absent: the broker itself says this order was
            # never accepted, so it's safe to call it a real failure
            # rather than leaving it in limbo as "submission_unknown".
            transitioned = store.mark_submission_failed_and_release(
                proposal_id,
                expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
                error=str(exc),
            )
            if transitioned is None:
                current = store.get_proposal(proposal_id)
                if current is not None and current.get("broker_order"):
                    return current["broker_order"]
            raise ProposalExecutionError(
                f"Order submission failed for {proposal_id}, and the broker confirms no such order "
                f"exists ({exc})."
            ) from exc
        unresolved = store.update_proposal_status_if_current(
            proposal_id,
            expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
            new_status=SUBMISSION_UNKNOWN,
            error=str(exc),
        )
        if unresolved is None:
            current = store.get_proposal(proposal_id)
            if current is not None and current.get("broker_order"):
                return current["broker_order"]
        raise ProposalExecutionError(
            f"Could not confirm whether the order for {proposal_id} was accepted by the broker "
            f"after an error ({exc}). Status is 'submission_unknown' -- run "
            f"`reconcile_submission({proposal_id!r}, store)` (CLI: `reconcile {proposal_id}`) once "
            "connectivity is restored; this ticker/side is treated as a duplicate-order risk until then."
        ) from exc

    try:
        journal_broker_order_update(
            store,
            proposal_id,
            order,
            event_type="submission_response",
        )
    except Exception as exc:
        # The broker DID accept the order (we got a normal response) --
        # the failure is only in our local journal write. Do not report
        # this as a submission failure; that would misrepresent an order
        # that genuinely exists. Keep the order info in `error` so it can
        # be reconciled/re-journaled manually.
        store.update_proposal_status_if_current(
            proposal_id,
            expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN, RECONCILING),
            new_status=proposal_status_for_order(order),
            broker_order=order,
            broker_status=str(order.get("status", "unknown")),
            error=f"Order was accepted by the broker but local recording failed: {exc}",
        )
        return order

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
      - Order found and matches the proposal's intent: journaled in the
        broker's actual accepted/partial/filled/terminal state.
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
                reason = (
                    f"Reconciliation found an order under this idempotency key that does NOT match the "
                    f"proposal's intent (mismatch: {mismatch_detail}; expected {expected_desc}; broker "
                    f"returned {outcome}) -- persistent kill switch activated; investigate manually."
                )
                store.update_proposal_status_if_current(
                    proposal_id,
                    expected_statuses=(RECONCILING,),
                    new_status=SUBMISSION_UNKNOWN,
                    reconciled_at=reconciled_at,
                    error=reason,
                )
                store.set_kill_switch(True, reason=reason)
                raise ProposalExecutionError(
                    f"Reconciliation for {proposal_id} found a MISMATCHED order ({mismatch_detail}) -- left "
                    "as 'submission_unknown' for manual investigation, not auto-resolved."
                )

            # The order found under our idempotency key may have been REPLACED
            # out of band; the live state then lives on the replacement, which
            # has its own order id. Resolve before journaling, or this manual
            # operation cannot fix the very condition it exists to fix.
            authoritative, chain_error, is_mismatch, chain = _authoritative_order_for(
                broker, outcome, stored_intent
            )
            if chain_error is not None:
                reason = (
                    f"Manual reconciliation for {proposal_id} could not trust the replacement chain: "
                    f"{chain_error}. "
                    + ("Persistent kill switch activated; investigate manually."
                       if is_mismatch else "Left retryable as 'submission_unknown'.")
                )
                store.update_proposal_status_if_current(
                    proposal_id,
                    expected_statuses=(RECONCILING,),
                    new_status=SUBMISSION_UNKNOWN,
                    reconciled_at=reconciled_at,
                    error=reason,
                )
                if is_mismatch:
                    store.set_kill_switch(True, reason=reason)
                raise ProposalExecutionError(reason)

            journal_broker_order_update(
                store,
                proposal_id,
                authoritative,
                event_type="manual_reconciliation",
                event_at=reconciled_at,
                clear_error=True,
                extra_updates={"reconciled_at": reconciled_at},
                raw_event={"replacement_chain": list(chain)} if chain else None,
            )
            return authoritative

        if outcome is None:
            transitioned = store.mark_submission_failed_and_release(
                proposal_id,
                expected_statuses=(RECONCILING,),
                reconciled_at=reconciled_at,
                error="Reconciliation: the broker confirms no order exists for this idempotency key.",
            )
            if transitioned is None:
                current = store.get_proposal(proposal_id)
                if current is not None and current.get("broker_order"):
                    return current["broker_order"]
            raise ProposalExecutionError(
                f"Reconciliation for {proposal_id}: the broker confirms this order was never accepted -- "
                "marked 'submission_failed'."
            )

        # outcome is _LOOKUP_UNCONFIRMED
        unresolved = store.update_proposal_status_if_current(
            proposal_id,
            expected_statuses=(RECONCILING,),
            new_status=SUBMISSION_UNKNOWN,
            reconciled_at=reconciled_at,
            error="Reconciliation attempted but the broker lookup itself failed -- still unresolved.",
        )
        if unresolved is None:
            current = store.get_proposal(proposal_id)
            if current is not None and current.get("broker_order"):
                return current["broker_order"]
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
            recovered = store.update_proposal_status_if_current(
                proposal_id,
                expected_statuses=(RECONCILING,),
                new_status=SUBMISSION_UNKNOWN,
                reconciled_at=datetime.now(timezone.utc).isoformat(),
                error=f"Unexpected error during reconciliation: {exc}",
            )
            if recovered is None:
                current = store.get_proposal(proposal_id)
                if current is not None and current.get("broker_order"):
                    return current["broker_order"]
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

    The status transition AND the audit metadata (`recovered_at`,
    `error`) are written in ONE atomic conditional UPDATE via
    store.reclaim_stale_status()'s `extra_updates` -- not via a separate,
    later write. A prior version wrote the status here and then called
    update_proposal_status() (unconditional on current status) afterward
    to add the audit fields; in the gap between those two writes, another
    worker could have claimed the newly-retryable proposal, resolved it
    to "executed", and had that second write silently overwrite it back
    to "submission_unknown" (2026-07-29, GPT review).

    `stale_after_seconds` must be a positive int -- a zero or negative
    value makes `cutoff` equal to or later than "now", so a reconciliation
    claimed moments (or never) ago would already compare as older than
    the cutoff, defeating this function's entire concurrency guarantee
    (GPT review, 2026-07-29, independently reproduced: the CLI exposed
    this raw via --stale-after-seconds with no validation at either
    layer). Validated FIRST, before any read or mutation of proposal
    state, so a bad value can never even attempt a reclaim.
    """
    if isinstance(stale_after_seconds, bool) or not isinstance(stale_after_seconds, int) or stale_after_seconds <= 0:
        raise ValueError(
            f"stale_after_seconds must be a positive int, got {stale_after_seconds!r} "
            f"({type(stale_after_seconds).__name__}) -- zero, negative, non-integer, and bool values are "
            "never valid: they would let a genuinely in-flight reconciliation be reclaimed immediately."
        )
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)).isoformat()
    recovered_at = datetime.now(timezone.utc).isoformat()
    recovered = store.reclaim_stale_status(
        proposal_id,
        expected_status=RECONCILING,
        new_status=SUBMISSION_UNKNOWN,
        stale_before=cutoff,
        extra_updates={
            "recovered_at": recovered_at,
            "error": (
                f"Recovered from a stale 'reconciling' status (no update for at least "
                f"{stale_after_seconds}s, most likely a process crash mid-reconciliation) -- marked "
                "'submission_unknown' so it can be reconciled again."
            ),
        },
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
    return recovered
