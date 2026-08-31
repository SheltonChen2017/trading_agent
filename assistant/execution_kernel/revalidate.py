"""Post-approval revalidation inputs.

GR-1A extraction. These compute the fresh facts an approved proposal is
rechecked against: the reviewed-override digest, the dollar value of pending
buys that must not be double-counted, and earnings proximity. They read; they
never transition a proposal or contact the broker to submit.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from assistant.money import (
    decimal_or_none,
    exact_decimal_add,
    exact_decimal_multiply,
    exact_decimal_subtract,
    to_decimal,
)
from risk.execution_gate import TradeIntent, intent_fingerprint


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


def classify_override_review(
    proposal: dict,
    intent: TradeIntent,
    violation_codes: tuple[str, ...],
    violations: tuple[str, ...],
    override_requested: bool,
) -> tuple[bool, bool, str]:
    """Decide whether an override request matches what a human reviewed.

    GR-1B extraction. Returns ``(reviewed_matches, conditions_changed,
    current_digest)``.

    Reviewed-override binding (GPT review, 2026-07-30): a digest match
    against the LAST reviewed-override record stored on this proposal is
    required, IN ADDITION to ``override_requested``, before proceeding.
    Otherwise the caller always (re-)stores the current violations as the
    new record to review and raises, never silently escalating to an
    authorization based on conditions the human has not specifically seen
    and accepted.

    ``proposal`` must be the snapshot fetched BEFORE this call's atomic
    claim, so ``reviewed_override`` reflects whatever a PRIOR call stored
    -- ``claim_proposal()`` never touches ``payload_json``. Passing a
    post-claim snapshot would not change today's behaviour but would make
    the guarantee accidental rather than structural.

    ``conditions_changed`` is True only when an override WAS requested,
    a prior record existed, and it no longer matches -- i.e. the human's
    earlier review no longer describes what would actually be overridden.
    That is a different message to the caller than a first presentation.
    """
    current_digest = _review_digest(intent, violation_codes, violations)
    previous_reviewed = proposal.get("reviewed_override")
    reviewed_matches = (
        override_requested
        and previous_reviewed is not None
        and previous_reviewed.get("review_digest") == current_digest
    )
    conditions_changed = (
        override_requested
        and previous_reviewed is not None
        and previous_reviewed.get("review_digest") != current_digest
    )
    return reviewed_matches, conditions_changed, current_digest


def build_reviewed_override_record(
    intent: TradeIntent,
    violation_codes: tuple[str, ...],
    violations: tuple[str, ...],
    review_digest: str,
    presented_at: str,
) -> dict:
    """The record a human must match on a second call to override.

    KNOWN LIMITATION (GPT review, 2026-07-31, not fixed --
    dormant/architectural, not currently exploitable through either real
    caller): ``presented_at`` is recorded the moment the SERVICE computes
    the block, not necessarily the moment a human actually saw it rendered
    on a screen. The two-call digest-match convention proves the SECOND
    call's violations exactly match what was stored on a PRIOR call, but
    does not cryptographically prove a human visually reviewed them in
    between -- a hypothetical future programmatic caller invoking
    execution twice in a tight loop with identical conditions would satisfy
    the digest match without any human ever seeing the first block.

    Both real callers today (the CLI, which requires a separate
    ``approve ... --override`` process re-invocation, and the UI, which
    requires clicking a button and then typing a distinct order-specific
    phrase into a text box) already require a genuine human action between
    the two calls, so this isn't currently exploitable -- but a fully
    rigorous fix would replace this convention with a signed, single-use
    challenge token returned to the caller after presentation and required
    back verbatim on the override call, rather than relying on that
    assumption. Revisit before exposing this override path through any new
    (e.g. programmatic/API) caller.
    """
    return {
        "intent_fingerprint": intent_fingerprint(intent),
        "violation_codes": sorted(violation_codes),
        "violations": sorted(violations),
        "review_digest": review_digest,
        "presented_at": presented_at,
    }


def _pending_buy_value_by_ticker(
    open_orders: list[dict], broker_module
) -> dict[str, Decimal]:
    """Estimated dollar value of currently pending (not-yet-filled) BUY
    orders, keyed by ticker -- fed into validate_trade_intent()'s
    exposure/concentration checks, which otherwise only see FILLED
    positions and are blind to money already committed by a pending order
    (Codex review, 2026-07-27). Risk-adjacent but intentionally NOT in
    risk/execution_gate.py -- see that module's "Known scatter points"
    note and docs/architecture/ARCHITECTURE_DEBT.md. Prefers exact values already on the order
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
    totals: dict[str, Decimal] = {}
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
        raw_filled = order.get("filled_qty_decimal")
        if raw_filled is None:
            raw_filled = order.get("filled_qty")
        filled_qty = decimal_or_none(raw_filled) if raw_filled else Decimal("0")
        if filled_qty is None or filled_qty < 0:
            filled_qty = Decimal("0")

        notional = order.get("notional_decimal")
        if notional is None:
            notional = order.get("notional")
        if notional:
            value = to_decimal(notional, name=f"{ticker} pending notional")
            # A notional order carries no share count, so net out the filled
            # dollars directly. Without a usable fill price the full notional
            # stays counted (again, the conservative direction).
            raw_fill_price = order.get("filled_avg_price_decimal")
            if raw_fill_price is None:
                raw_fill_price = order.get("filled_avg_price")
            fill_price = (
                decimal_or_none(raw_fill_price)
                if raw_fill_price
                else Decimal("0")
            )
            if fill_price is not None and fill_price > 0:
                value = max(
                    Decimal("0"),
                    exact_decimal_subtract(
                        value,
                        exact_decimal_multiply(
                            filled_qty,
                            fill_price,
                            name=f"{ticker} filled pending notional",
                        ),
                        name=f"{ticker} remaining pending notional",
                    ),
                )
        else:
            shares = order.get("shares_decimal")
            if shares is None:
                shares = order.get("shares")
            if not shares:
                continue
            remaining_shares = exact_decimal_subtract(
                to_decimal(shares, name=f"{ticker} pending shares"),
                filled_qty,
                name=f"{ticker} remaining pending shares",
            )
            if remaining_shares <= 0:
                continue
            limit_price = order.get("limit_price_decimal")
            if limit_price is None:
                limit_price = order.get("limit_price")
            if limit_price:
                value = exact_decimal_multiply(
                    remaining_shares,
                    to_decimal(
                        limit_price,
                        name=f"{ticker} pending limit_price",
                    ),
                    name=f"{ticker} pending limit-order value",
                )
            else:
                quote = broker_module.get_latest_quote(ticker)
                quote_price = quote.get("price_decimal")
                if quote_price is None:
                    quote_price = quote["price"]
                value = exact_decimal_multiply(
                    remaining_shares,
                    to_decimal(quote_price, name=f"{ticker} quote price"),
                    name=f"{ticker} pending market-order value",
                )
        totals[ticker.upper()] = exact_decimal_add(
            totals.get(ticker.upper(), Decimal("0")),
            value,
            name=f"{ticker} total pending buy value",
        )
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
