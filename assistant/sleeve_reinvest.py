"""
Three-sleeve engine M3 -- dividend -> reinvest proposals with earmark
accounting (docs/reference/THREE_SLEEVE_ENGINE_PLAN.md section 5 M3, as
revised by section 1.1).

The rule, exactly as adopted: confirmed dividend income funds PENDING
DECLINE-REVIEW ADDS FIRST; only when no dip-add is waiting does it become an
APPROVE-gated buy proposal for an owner-chosen ticker from
config.DIVIDEND_REINVEST_TICKERS. Either way the money moves only through
the existing TradeProposal -> "approve" -> execution-gate pipeline --
nothing here submits, sizes on its own authority, or bypasses
`max_leveraged_etf_pct`, which remains the enforcement backstop at
approval time.

Earmark accounting makes each confirmed dividend dollar spendable exactly
once:

* earmarked atomically with proposal creation
  (AssistantStore.create_dividend_earmark_with_proposal -- the pool check,
  the proposal insert, and the earmark insert commit together or not at
  all);
* released exactly once when the proposal terminates without spending
  anything (the conditional status fence in
  resolve_dividend_earmark_if_active mirrors
  release_execution_reservation's rowcount discipline);
* consumed when a fill spends it; and
* HELD for every ambiguous state (submission_unknown, reconciling, legacy
  executed, unknown or missing rows) -- ambiguity reserves more and
  permits less, never the reverse.

A canceled or broker-expired proposal releases only when the broker order
history shows ZERO fill quantity; any recorded fill consumes the whole
earmark instead, because partially-spent dividend dollars returning to the
pool would be the double-spend this table exists to prevent. The earmark is
the proposal-time notional (shares x reference price); a market-order fill
can deviate from it, and the account's cash remains the authority for what
was actually paid -- the earmark bounds proposal creation, it does not
restate broker accounting.

Status reporting derives each active earmark's EFFECTIVE disposition from
the proposal's current status without writing, so the read-only status
surface is honest even before a durable reconcile pass runs. Durable
transitions happen only on write paths (the propose flow and the briefing's
reconcile hook), never during a read-only render.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import config
from assistant.money import decimal_text, to_decimal
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_analytics import preview_trade_impact
from assistant.portfolio_ledger import ACCOUNT_DIVIDEND_INCOME
from assistant.proposal_status import (
    BLOCKED,
    BROKER_EXPIRED,
    BROKER_REJECTED,
    CANCELED,
    DISMISSED,
    EXPIRED,
    FILLED,
    SUBMISSION_FAILED,
    VALIDATION_FAILED,
)
from assistant.proposals import TradeProposal
from assistant.schemas import DecisionPacket
from assistant.sleeve_notifications import DECLINE_REVIEW, REENTRY_DECLINE
from assistant.storage import AssistantStore
from risk.execution_gate import TradeIntent


class SleeveReinvestError(ValueError):
    """The dividend pool could not be measured safely."""


EVIDENCE_STATUS_REINVEST = "sleeve_dividend_reinvest"
EVIDENCE_STATUS_DECLINE_ADD = "sleeve_decline_review_add"

ROUTE_REINVEST = "reinvest"
ROUTE_DECLINE_ADD = "decline_review_add"

# Terminal proposal statuses that PROVE no dividend dollar was spent: policy
# refusal, validation failure, confirmed non-submission, broker rejection,
# expiry before approval, and dismissal. `canceled`/`broker_expired` are
# deliberately absent -- they are terminal but fill-dependent (a partial fill
# before cancellation spent real dollars) and are classified per proposal in
# earmark_disposition().
EARMARK_RELEASE_STATUSES: tuple[str, ...] = (
    BLOCKED,
    VALIDATION_FAILED,
    SUBMISSION_FAILED,
    BROKER_REJECTED,
    EXPIRED,
    DISMISSED,
)
EARMARK_CONSUME_STATUSES: tuple[str, ...] = (FILLED,)
EARMARK_FILL_DEPENDENT_STATUSES: tuple[str, ...] = (CANCELED, BROKER_EXPIRED)


def earmark_disposition(proposal_status: object, *, fill_evidence: bool) -> str:
    """'release', 'consume', or 'hold' for one earmark's proposal status.

    Fail-closed direction: every status this function has never seen -- a
    future lifecycle addition, None, a non-string -- HOLDS the earmark. A
    held dollar is recoverable by reconciliation; a wrongly released dollar
    is a double-spend.
    """
    if not isinstance(proposal_status, str):
        return "hold"
    if proposal_status in EARMARK_CONSUME_STATUSES:
        return "consume"
    if proposal_status in EARMARK_RELEASE_STATUSES:
        return "release"
    if proposal_status in EARMARK_FILL_DEPENDENT_STATUSES:
        return "consume" if fill_evidence else "release"
    return "hold"


def _has_fill_evidence(store: AssistantStore, proposal_id: str) -> bool:
    """True when any broker order event recorded a positive fill quantity.

    Unreadable fill quantities count as evidence (hold/consume direction):
    corrupt fill data must not release dividend dollars.
    """
    for event in store.list_broker_order_events(proposal_id=proposal_id):
        fill_qty = event.get("fill_qty")
        if fill_qty in (None, "", 0):
            continue
        try:
            if to_decimal(fill_qty, name="fill quantity") > 0:
                return True
        except ValueError:
            return True
    return False


def confirmed_dividend_income_text(journal_postings: list[dict]) -> str:
    """Exact-decimal total of broker-confirmed dividend income.

    Population: journal postings with source == "corporate_action" against
    the INCOME:DIVIDENDS account -- the same broker-confirmed population
    corporate_actions.confirmed_distributions reads, deliberately NARROWER
    than sleeve_report's income display (which shows every income posting
    regardless of source). Spendable dollars must trace to a broker-
    confirmed corporate action; anything else fails toward a smaller pool.

    Income posts negative under this ledger's sign convention. A POSITIVE
    posting on the income account is refused rather than netted or
    absolute-valued -- the same stance sleeve_report takes -- because it
    means the books hold something this module does not understand, and
    guessing either direction could mint spendable dollars.
    """
    total = Decimal(0)
    for posting in journal_postings:
        if posting.get("source") != "corporate_action":
            continue
        if posting.get("account") != ACCOUNT_DIVIDEND_INCOME:
            continue
        amount = -to_decimal(posting["amount"], name="dividend posting amount")
        if amount < 0:
            raise SleeveReinvestError(
                "a positive INCOME:DIVIDENDS posting exists "
                f"(transaction {posting.get('transaction_id')!r}); refusing to "
                "measure the dividend pool over books this module does not "
                "understand"
            )
        total += amount
    return decimal_text(total)


def pending_decline_reviews(store: AssistantStore) -> list[dict]:
    """Active dip-add watches, the states that outrank leveraged reinvestment.

    Both M2 watch kinds count: `decline_review` (a held lot at or below the
    decline threshold on its own basis) and `reentry_decline` (a flat
    candidate at or below the re-entry trigger from its last disposal
    price). Deterministic order.
    """
    rows = [
        {"ticker": row["ticker"], "kind": row["kind"], "watch_key": row["watch_key"]}
        for row in store.list_sleeve_watch_states()
        if row["kind"] in (DECLINE_REVIEW, REENTRY_DECLINE) and row["active"]
    ]
    rows.sort(key=lambda row: (row["ticker"], row["kind"], row["watch_key"]))
    return rows


def reconcile_dividend_earmarks(
    store: AssistantStore, *, now: datetime | None = None
) -> list[dict]:
    """Apply durable exactly-once transitions to every resolvable earmark.

    Idempotent and crash-safe: each transition is a conditional UPDATE
    fenced on status='active', so a retry, a concurrent caller, or a
    restart replay finds nothing left to do. A missing proposal row is
    surfaced and HELD, never released -- an earmark without its proposal is
    corrupt state, and corruption reserves more, not less.
    """
    at = (now or datetime.now(timezone.utc)).isoformat()
    transitions: list[dict] = []
    for earmark in store.list_dividend_earmarks():
        if earmark["status"] != "active":
            continue
        proposal_id = earmark["proposal_id"]
        proposal = store.get_proposal(proposal_id)
        if proposal is None:
            transitions.append(
                {
                    "proposal_id": proposal_id,
                    "action": "held",
                    "reason": "earmark has no proposal row; holding (corrupt state)",
                }
            )
            continue
        status = proposal.get("status")
        fill_evidence = (
            _has_fill_evidence(store, proposal_id)
            if status in EARMARK_FILL_DEPENDENT_STATUSES
            else False
        )
        disposition = earmark_disposition(status, fill_evidence=fill_evidence)
        if disposition == "hold":
            continue
        new_status = "released" if disposition == "release" else "consumed"
        reason = f"proposal status {status!r}" + (
            " with recorded fill quantity" if fill_evidence else ""
        )
        applied = store.resolve_dividend_earmark_if_active(
            proposal_id, new_status=new_status, resolved_reason=reason, now=at
        )
        if applied:
            transitions.append(
                {"proposal_id": proposal_id, "action": new_status, "reason": reason}
            )
    return transitions


def dividend_reinvest_status(store: AssistantStore) -> dict:
    """Read-only pool, routing, and earmark state. Writes nothing.

    Active earmarks are shown with the EFFECTIVE disposition their
    proposal's current status implies, and the available total is computed
    from effective dispositions -- so an expired proposal's dollars read as
    available here even before a durable reconcile pass records the
    release. The durable row and the effective view can therefore disagree
    briefly; both are reported.
    """
    confirmed_text = confirmed_dividend_income_text(store.list_journal_postings())
    confirmed = to_decimal(confirmed_text, name="confirmed dividend income")

    earmarks: list[dict] = []
    unavailable_total = Decimal(0)
    consumed_total = Decimal(0)
    released_total = Decimal(0)
    for row in store.list_dividend_earmarks():
        amount = to_decimal(row["amount_text"], name="stored earmark amount")
        if row["status"] == "active":
            proposal = store.get_proposal(row["proposal_id"])
            if proposal is None:
                effective = "hold"
                proposal_status = None
            else:
                proposal_status = proposal.get("status")
                fill_evidence = (
                    _has_fill_evidence(store, row["proposal_id"])
                    if proposal_status in EARMARK_FILL_DEPENDENT_STATUSES
                    else False
                )
                effective = earmark_disposition(
                    proposal_status, fill_evidence=fill_evidence
                )
        else:
            effective = row["status"]
            proposal_status = None
        if effective in ("hold", "consume", "consumed"):
            unavailable_total += amount
        if effective in ("consume", "consumed"):
            consumed_total += amount
        if effective in ("release", "released"):
            released_total += amount
        earmarks.append(
            {
                **row,
                "effective_disposition": effective,
                "proposal_status": proposal_status,
            }
        )

    pending = pending_decline_reviews(store)
    if pending:
        route = ROUTE_DECLINE_ADD
        eligible = sorted({row["ticker"] for row in pending})
        note = (
            "Confirmed dividend income funds pending decline-review adds "
            "first (plan section 1.1); leveraged reinvestment is refused "
            "while these are waiting: " + ", ".join(eligible) + "."
        )
    else:
        route = ROUTE_REINVEST
        eligible = sorted(
            {ticker.upper() for ticker in config.DIVIDEND_REINVEST_TICKERS}
        )
        note = (
            "No decline-review add is pending; the dividend pool may fund an "
            "APPROVE-gated reinvestment into an owner-chosen candidate."
        )

    available = confirmed - unavailable_total
    return {
        "confirmed_income_total": confirmed_text,
        "unavailable_total": decimal_text(unavailable_total),
        "consumed_total": decimal_text(consumed_total),
        "released_total": decimal_text(released_total),
        "available_total": decimal_text(available),
        "earmarks": earmarks,
        "pending_decline_reviews": pending,
        "route": route,
        "eligible_tickers": eligible,
        "note": note,
        "income_population_note": (
            "The pool counts broker-confirmed corporate-action dividends "
            "only; it can be smaller than the sleeve report's income "
            "display, never larger."
        ),
    }


def _stable_id(
    packet: DecisionPacket, policy: TradingPolicy, intent: TradeIntent, salt: str
) -> str:
    # Same shape and reasoning as allocation_proposals._stable_id: a full
    # timestamp so a same-day regeneration cannot collide with a stale row
    # under save_proposal's DO NOTHING semantics, namespaced so it can never
    # collide with another generator's id for the same intent.
    raw = (
        f"sleeve_reinvest|{salt}|{packet.generated_at}|{policy.version}|"
        f"{intent.ticker.upper()}|{intent.side}|{intent.shares}"
    )
    return "tp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def generate_dividend_reinvest_proposal(
    packet: DecisionPacket,
    policy: TradingPolicy,
    store: AssistantStore,
    *,
    ticker: str,
    amount: object,
    price: object,
    ttl_minutes: int = 15,
    now: datetime | None = None,
) -> dict:
    """Create one APPROVE-gated, dividend-funded buy proposal with its earmark.

    Returns {"created": True, "proposal": ..., "earmark_amount_text": ...}
    or {"created": False, "reason": ...}. Every refusal is a plain stated
    reason; nothing is partially written on any refusal path (the pool
    check, proposal insert, and earmark insert share one transaction in
    storage).

    The caller should run reconcile_dividend_earmarks() first so dollars
    from already-terminal proposals are durably back in the pool; without
    it this function still cannot over-spend -- stale active earmarks only
    make the pool check MORE conservative.
    """
    ticker_upper = str(ticker).strip().upper()
    if not ticker_upper:
        return {"created": False, "reason": "a ticker is required"}

    try:
        amount_decimal = to_decimal(amount, name="reinvest amount")
    except ValueError as exc:
        return {"created": False, "reason": str(exc)}
    if amount_decimal <= 0:
        return {"created": False, "reason": "the amount must be positive"}

    try:
        price_decimal = to_decimal(price, name=f"{ticker_upper} reference price")
    except ValueError as exc:
        return {"created": False, "reason": str(exc)}
    if price_decimal <= 0:
        return {
            "created": False,
            "reason": f"no usable reference price for {ticker_upper}",
        }

    status = dividend_reinvest_status(store)
    available = to_decimal(status["available_total"], name="available dividend pool")
    if amount_decimal > available:
        return {
            "created": False,
            "reason": (
                f"requested {decimal_text(amount_decimal)} exceeds the "
                f"available dividend pool of {status['available_total']}"
            ),
        }

    route = status["route"]
    if ticker_upper not in status["eligible_tickers"]:
        if route == ROUTE_DECLINE_ADD:
            reason = (
                f"{ticker_upper} is not eligible while decline-review adds are "
                "pending for: " + ", ".join(status["eligible_tickers"]) + " "
                "(dividend income funds pending dip-adds first, plan "
                "section 1.1)"
            )
        else:
            reason = (
                f"{ticker_upper} is not in DIVIDEND_REINVEST_TICKERS "
                f"({', '.join(status['eligible_tickers'])})"
            )
        return {"created": False, "reason": reason}

    shares = int(amount_decimal // price_decimal)
    if shares <= 0:
        return {
            "created": False,
            "reason": (
                f"{decimal_text(amount_decimal)} cannot afford one share of "
                f"{ticker_upper} at {decimal_text(price_decimal)}"
            ),
        }
    earmark_amount = price_decimal * shares
    reference_price = float(price_decimal)

    at = now or datetime.now(timezone.utc)
    if route == ROUTE_DECLINE_ADD:
        evidence_status = EVIDENCE_STATUS_DECLINE_ADD
        rationale = (
            f"Dividend-funded decline-review add: {shares} shares of "
            f"{ticker_upper} at ~${reference_price:,.2f}, funded from "
            "confirmed dividend income (three-sleeve plan section 1.1: "
            "dip-adds outrank leveraged reinvestment)."
        )
    else:
        evidence_status = EVIDENCE_STATUS_REINVEST
        rationale = (
            f"Dividend reinvestment: {shares} shares of {ticker_upper} at "
            f"~${reference_price:,.2f}, funded from confirmed dividend "
            "income (three-sleeve plan section 5 M3; no decline-review add "
            "is pending)."
        )

    intent = TradeIntent(
        ticker=ticker_upper,
        side="buy",
        shares=shares,
        order_type="market",
        rationale=rationale,
    )
    proposal_id = _stable_id(
        packet, policy, intent, salt=f"{route}|{decimal_text(earmark_amount)}"
    )
    proposal = TradeProposal(
        proposal_id=proposal_id,
        created_at=at.isoformat(),
        expires_at=(at + timedelta(minutes=ttl_minutes)).isoformat(),
        status="proposed",
        idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
        policy_version=policy.version,
        policy_fingerprint=compute_policy_fingerprint(policy),
        intent=intent,
        reference_price=reference_price,
        price_timestamp=at.isoformat(),
        reasons=[
            rationale,
            (
                f"Earmarked {decimal_text(earmark_amount)} of the "
                f"{status['available_total']} available dividend pool; the "
                "earmark is released if this proposal is rejected, cancelled "
                "unfilled, or expires."
            ),
        ],
        evidence_status=evidence_status,
        expected_impact=preview_trade_impact(
            packet.portfolio, ticker_upper, "buy", shares, reference_price
        ),
        alternatives=[
            "Take no action -- nothing is bought until you type the approval "
            "phrase for this proposal.",
            "Choose a different eligible ticker or a different amount and "
            "regenerate.",
        ],
        uncertainties=[
            "This engine is the owner's stated preference, not validated "
            "research; the paper epoch is where it earns prospective "
            "evidence.",
            "Shares are rounded down, so slightly less than the requested "
            "amount is earmarked; the remainder stays in the pool.",
            "Market orders can fill away from the displayed reference price; "
            "the earmark records the proposal-time notional, and account "
            "cash remains the authority for what was actually paid.",
            "Requires allow_new_positions=true in your policy, and "
            "max_leveraged_etf_pct is independently enforced at approval "
            "time.",
        ],
    )

    result = store.create_dividend_earmark_with_proposal(
        proposal.to_dict(),
        amount_text=decimal_text(earmark_amount),
        route=route,
        ticker=ticker_upper,
        confirmed_income_text=status["confirmed_income_total"],
        now=at.isoformat(),
    )
    if not result.get("created"):
        return {"created": False, "reason": result.get("reason", "unknown refusal")}
    return {
        "created": True,
        "proposal": proposal,
        "route": route,
        "earmark_amount_text": decimal_text(earmark_amount),
        "pool_available_after_text": result.get("available_text"),
    }
