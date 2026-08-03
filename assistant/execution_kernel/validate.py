"""Proposal validation orchestration: the read-only eligibility check.

GR-1C extraction. ``run_proposal_validation()`` is the single source of
truth for "would this proposal be allowed to execute right now" -- consumed
by BOTH execute_approved_paper_proposal() (immediately after its own atomic
claim) and preflight_allocation_batch() (read-only, no claim at all). It
reads durable state and queries the broker; it never claims, never transitions
a proposal, never reserves budget, never submits.

Dependency injection, not namespace resolution: every callable seam this
orchestration consults arrives explicitly via ``ProposalValidationDeps``.
The facade (assistant.execution_service) constructs that contract AT CALL
TIME from its own module namespace, so a monkeypatch on
``assistant.execution_service.validate_trade_intent`` (or any other
injected seam name) still reaches this module. That is the property that
kept this orchestration on the facade through GR-1B: moving the code while
resolving ``validate_trade_intent`` from THIS module's namespace would have
silently defeated every such patch --
tests/test_personal_assistant.py::
test_unexpected_exception_during_validation_marks_validation_failed_not_stuck
patches exactly that name, and
tests/test_execution_characterization.py freezes the seam directly. This
module therefore imports none of the injected callables, which also keeps
GR-1 section 6.2 satisfied structurally: no private peer imports exist to
forbid.

Check ORDER is load-bearing and mirrors what execute_approved_paper_proposal()
always enforced: existence, expiration, policy execution mode, policy
version/fingerprint, paper-broker mode/configuration, kill switch,
open-order availability and cap, stored-intent parsing, side/order-type/
new-position policy rules, broker account/asset preflight, duplicate
history, live quote, pending-order exposure, the earnings-data requirement,
and finally validate_trade_intent() itself. The broker module is imported
via ``deps.import_broker()`` at the exact point the deferred
``import execution.alpaca_broker`` statement historically ran -- AFTER the
policy checks -- so an unimportable broker package still cannot mask an
earlier refusal.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from assistant.execution_telemetry import (
    FAILURE_DATA_INTEGRITY,
    FAILURE_DETERMINISTIC_POLICY,
    FAILURE_INFRASTRUCTURE,
    FAILURE_NONE,
)
from assistant.money import MoneyInput
from assistant.policy import TradingPolicy
from assistant.schemas import PortfolioSnapshot
from assistant.storage import AssistantStore
from risk.execution_gate import TradeIntent, ValidationResult


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
    reference_price: MoneyInput | None = None
    # Safe broker/market evidence captured while validating. These fields
    # remain observational only: callers must never reuse them as execution
    # authorization. They exist so a claimed attempt can be recorded before
    # an order (and therefore a broker lifecycle row) exists.
    broker_preflight: dict | None = None
    quote: dict | None = None
    quote_received_at: str | None = None
    # Why this attempt failed, classified at the raising site rather than by
    # matching error text later. An infrastructure fault recorded as a
    # policy rejection is trading-safe -- both refuse -- but it is a wrong
    # training label for any later execution-quality analysis, which would
    # learn that the policy declines trades the policy actually approved.
    # None means "not classified here"; see resolved_failure_class.
    failure_class: str | None = None

    @property
    def resolved_failure_class(self) -> str:
        """One of the FAILURE_* constants, never None."""
        if self.error is None:
            return FAILURE_NONE
        return self.failure_class or FAILURE_DETERMINISTIC_POLICY

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


@dataclasses.dataclass(frozen=True)
class ProposalValidationDeps:
    """Every callable seam run_proposal_validation() consults, injected.

    The facade builds this AT CALL TIME from its own module globals -- never
    at import time, never from this module's namespace -- which is the whole
    contract: assigning ``assistant.execution_service.validate_trade_intent``
    (or any other seam name below) must keep changing validation behaviour
    exactly as it did when the orchestration lived on the facade. A future
    edit that caches an instance of this class at module scope, or that
    imports one of these callables here directly, silently breaks that seam;
    tests/test_execution_characterization.py freezes each field against
    exactly that edit.
    """
    # Deferred provider for execution.alpaca_broker, called mid-sequence at
    # the point the historical inline import ran. A provider rather than the
    # module object so an unimportable broker package cannot preempt the
    # earlier existence/expiry/policy refusals.
    import_broker: Callable[[], Any]
    datetime_type: Any
    decimal_factory: Callable[[str], Decimal]
    trade_intent_factory: Callable[..., TradeIntent]
    to_decimal: Callable[..., Decimal]
    env_kill_switch_active: Callable[[], bool]
    compute_policy_fingerprint: Callable[[TradingPolicy], str]
    intent_from_dict: Callable[[dict], TradeIntent]
    pending_buy_value_by_ticker: Callable[[list, Any], dict[str, Decimal]]
    resolve_earnings_days_away: Callable[[str, int | None], int | None]
    validate_trade_intent: Callable[..., ValidationResult]


def run_proposal_validation(
    proposal_id: str,
    current_portfolio: PortfolioSnapshot,
    policy: TradingPolicy,
    store: AssistantStore,
    *,
    now_et: datetime,
    deps: ProposalValidationDeps,
    kill_switch_active: bool = False,
    earnings_days_away: int | None = None,
    proposal: dict | None = None,
    extra_pending_buy_value_by_ticker: dict[str, float] | None = None,
    available_cash_override: float | None = None,
    available_buying_power_override: float | None = None,
    extra_open_order_count: int = 0,
) -> ProposalValidationOutcome:
    """The validation orchestration behind the facade's
    validate_proposal_for_execution() -- see that wrapper's docstring for
    the caller-facing parameter contract, which is unchanged from before
    GR-1C. The body below moved here verbatim; the only edits are the seam
    calls now spelled ``deps.<name>``.
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
        or deps.env_kill_switch_active()
        or bool(persistent_kill_switch.get("active"))
    )
    if proposal is None:
        proposal = store.get_proposal(proposal_id)
    if proposal is None:
        return ProposalValidationOutcome(
            proposal=None, intent=None, validation=None, error=f"Unknown proposal: {proposal_id}",
            failure_class=FAILURE_DATA_INTEGRITY,
        )

    now_utc = deps.datetime_type.now(timezone.utc)
    if now_utc > deps.datetime_type.fromisoformat(proposal["expires_at"]):
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
    if proposal.get("policy_fingerprint") != deps.compute_policy_fingerprint(policy):
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None,
            error=(
                "Proposal's policy fingerprint does not match the active policy's current content -- the "
                "policy may have been edited without a version bump (or this proposal predates fingerprint "
                "binding). Regenerate the proposal against the current policy."
            ),
        )

    broker = deps.import_broker()

    if not broker.PAPER_TRADING:
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None,
            error="This workflow refuses live trading; PAPER_TRADING must remain True.",
        )
    if not broker.is_configured():
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None, error="Alpaca paper credentials are not configured.",
            failure_class=FAILURE_INFRASTRUCTURE,
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
    # `extra_open_order_count` is how many orders an in-progress batch has
    # already simulated submitting ahead of this leg. Without it a cumulative
    # preflight sees a CONSTANT open-order count across every leg and can
    # green-light a batch whose later legs the real path then rejects, breaking
    # allocation_batch's "submit none, or all" guarantee (independent review,
    # 2026-07-30). Validated rather than trusted: a negative or non-int value
    # would loosen a cap.
    if (
        isinstance(extra_open_order_count, bool)
        or not isinstance(extra_open_order_count, int)
        or extra_open_order_count < 0
    ):
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None,
            error=f"extra_open_order_count must be a non-negative int, got {extra_open_order_count!r}.",
        )
    projected_open_orders = len(current_portfolio.open_orders) + extra_open_order_count
    if projected_open_orders >= policy.max_open_orders:
        pending_note = (
            f" (including {extra_open_order_count} earlier leg(s) of this batch)"
            if extra_open_order_count else ""
        )
        return ProposalValidationOutcome(
            proposal=proposal,
            intent=None,
            validation=None,
            error=(
                f"Open-order cap reached: {projected_open_orders} active order(s){pending_note}, "
                f"policy maximum {policy.max_open_orders}."
            ),
        )

    try:
        intent = deps.intent_from_dict(proposal["intent"])
    except Exception as exc:
        return ProposalValidationOutcome(
            proposal=proposal, intent=None, validation=None, error=f"Malformed stored intent: {exc}",
            failure_class=FAILURE_DATA_INTEGRITY,
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
        broker_preflight = broker.assert_account_and_asset_ready(intent.ticker)
    except Exception as exc:
        return ProposalValidationOutcome(
            proposal=proposal,
            intent=intent,
            validation=None,
            error=f"Broker account/asset preflight failed: {exc}",
            failure_class=FAILURE_INFRASTRUCTURE,
        )

    try:
        recent_intents = [deps.intent_from_dict(raw) for raw in store.recent_executed_intents()]
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
            broker_preflight=broker_preflight,
            failure_class=FAILURE_DATA_INTEGRITY,
        )
    for order in current_portfolio.open_orders:
        side = str(order.get("side", "")).lower()
        # See execute_approved_paper_proposal()'s own duplicate-check
        # comment: identity depends only on ticker+side, never shares.
        if side in ("buy", "sell") and order.get("ticker"):
            recent_intents.append(
                deps.trade_intent_factory(
                    ticker=order["ticker"], side=side,
                    shares=int(float(order["shares"])) if order.get("shares") else 1,
                )
            )

    try:
        quote = broker.get_latest_quote(intent.ticker)
        quote_received_at = deps.datetime_type.now(timezone.utc).isoformat()
        reference_price = quote.get("price_decimal", quote["price"])
        price_timestamp = quote["timestamp"]
        bid_price = quote.get("bid_decimal", quote.get("bid"))
        ask_price = quote.get("ask_decimal", quote.get("ask"))
    except Exception as exc:
        return ProposalValidationOutcome(
            proposal=proposal, intent=intent, validation=None,
            error=f"Could not fetch a live quote for {intent.ticker} to check price freshness: {exc}",
            broker_preflight=broker_preflight,
            failure_class=FAILURE_INFRASTRUCTURE,
        )

    pending_buy_value_by_ticker: dict[str, Decimal] = {}
    if intent.side == "buy":
        try:
            pending_buy_value_by_ticker = dict(
                deps.pending_buy_value_by_ticker(current_portfolio.open_orders, broker)
            )
        except Exception as exc:
            return ProposalValidationOutcome(
                proposal=proposal, intent=intent, validation=None,
                error=(
                    f"Could not determine the dollar value of a pending buy order needed to check "
                    f"exposure/concentration limits: {exc}"
                ),
                reference_price=reference_price,
                broker_preflight=broker_preflight,
                quote=quote,
                quote_received_at=quote_received_at,
                failure_class=FAILURE_INFRASTRUCTURE,
            )
        for ticker, extra_value in (extra_pending_buy_value_by_ticker or {}).items():
            key = ticker.upper()
            pending_buy_value_by_ticker[key] = (
                pending_buy_value_by_ticker.get(key, deps.decimal_factory("0"))
                + deps.to_decimal(
                    extra_value,
                    name=f"extra pending buy value for {key}",
                )
            )

    resolved_earnings_days_away = deps.resolve_earnings_days_away(
        intent.ticker, earnings_days_away
    )
    if policy.require_earnings_data and intent.side == "buy" and resolved_earnings_days_away is None:
        return ProposalValidationOutcome(
            proposal=proposal, intent=intent, validation=None,
            error=(
                f"Earnings-date data for {intent.ticker} is unavailable and your policy requires it "
                "for buys (require_earnings_data=true) -- refusing to approve rather than silently "
                "skip the earnings blackout check."
            ),
            reference_price=reference_price,
            broker_preflight=broker_preflight,
            quote=quote,
            quote_received_at=quote_received_at,
            # Classified as infrastructure, not policy: the policy rule here
            # is fail-closed handling of a data outage, not a judgment about
            # this trade. The same trade with the data present would have
            # been evaluated normally, so labelling it a policy rejection
            # would teach a later model that the policy declines trades it
            # does not decline.
            failure_class=FAILURE_INFRASTRUCTURE,
        )

    validation = deps.validate_trade_intent(
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
        proposal=proposal,
        intent=intent,
        validation=validation,
        error=None,
        reference_price=reference_price,
        broker_preflight=broker_preflight,
        quote=quote,
        quote_received_at=quote_received_at,
    )
