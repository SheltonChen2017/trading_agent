"""Proposal validation orchestration: the read-only eligibility check.

GR-1C extraction. ``run_proposal_validation()`` is the single source of
truth for "would this proposal be allowed to execute right now" -- consumed
by BOTH execute_approved_paper_proposal() (immediately after its own atomic
claim) and preflight_allocation_batch() (read-only, no claim at all). It
reads durable state and queries the broker; it never claims, never transitions
a proposal, never reserves budget, never submits.

Dependency injection, not namespace resolution: every facade-derived runtime
name this orchestration consults arrives explicitly via
``ProposalValidationDeps``.
The facade (assistant.execution_service) constructs that contract AT CALL
TIME from its own module namespace, so a monkeypatch on
``assistant.execution_service.validate_trade_intent`` (or any other
injected runtime name) still reaches this module. That is the property that
kept this orchestration on the facade through GR-1B: moving the code while
resolving ``validate_trade_intent`` from THIS module's namespace would have
silently defeated every such patch --
tests/test_personal_assistant.py::
test_unexpected_exception_during_validation_marks_validation_failed_not_stuck
patches exactly that name, and
tests/test_execution_characterization.py freezes the seam directly. This
module therefore imports none of the injected collaborators, which also keeps
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
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from assistant.execution_telemetry import (
    FAILURE_DETERMINISTIC_POLICY,
    FAILURE_NONE,
)
from assistant.money import MoneyInput
from assistant.policy import TradingPolicy
from assistant.schemas import PortfolioSnapshot
from assistant.storage import AssistantStore
from risk.execution_gate import (
    ExecutionValidationContext,
    TradeIntent,
    ValidationResult,
)


@dataclasses.dataclass(frozen=True)
class ProposalValidationOutcome:
    """
    Read-only result of checking whether a proposal is currently eligible
    to execute -- never claims, never writes proposal status, never
    submits, never authorizes. Used by BOTH
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
        """One of the FAILURE_* constants, never None.

        Boundary note (GR-1C third round): these two fallbacks resolve from
        THIS module, not the facade, so they sit outside the
        ProposalValidationDeps injection contract, which is scoped to
        run_proposal_validation()'s body. Pre-GR-1C the class lived on the
        facade and a facade-level patch of either constant reached this
        property; it no longer does. Deliberate: injecting them would change
        this frozen dataclass's public field set, and resolving them from the
        facade would invert the kernel->facade dependency direction. Pinned
        by test_gr1c_resolved_failure_class_fallbacks_are_class_resolved.
        """
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
    """Every facade-resolved runtime name used by validation, injected.

    The facade builds this AT CALL TIME from its own module globals -- never
    at import time, never from this module's namespace -- which is the whole
    contract: assigning ``assistant.execution_service.validate_trade_intent``
    (or any other seam name below) must keep changing validation behaviour
    exactly as it did when the orchestration lived on the facade. A future
    edit that caches an instance of this class at module scope, or that
    imports one of these callables here directly, silently breaks that seam;
    tests/test_execution_characterization.py freezes each field against
    exactly that edit.

    The injection boundary is exact: ``run_proposal_validation()`` resolves
    no runtime collaborator from this module. That includes the outcome
    constructor, timezone collaborator, and behavior-bearing failure
    constants, all of which the body historically resolved from the facade
    and callers could replace there. The outcome class remains defined here
    and re-exported by the facade as the same object, but the facade still
    supplies the factory used for each construction at call time; this is
    ordinary dependency injection, not a circular dependency.

    ``test_gr1c_the_kernel_body_reads_no_module_globals`` pins the empty
    runtime-global set. Adding any module-global read to the body -- including
    quietly resolving a formerly injected dependency directly -- fails and
    requires the collaborator to join this contract.
    """
    # Deferred provider for execution.alpaca_broker, called mid-sequence at
    # the point the historical inline import ran. A provider rather than the
    # module object so an unimportable broker package cannot preempt the
    # earlier existence/expiry/policy refusals.
    import_broker: Callable[[], Any]
    outcome_factory: Callable[..., ProposalValidationOutcome]
    datetime_type: Any
    timezone_type: Any
    eastern_timezone: Any
    decimal_factory: Callable[[str], Decimal]
    trade_intent_factory: Callable[..., TradeIntent]
    to_decimal: Callable[..., Decimal]
    exact_decimal_add: Callable[..., Decimal]
    exact_decimal_multiply: Callable[..., Decimal]
    env_kill_switch_active: Callable[[], bool]
    compute_policy_fingerprint: Callable[[TradingPolicy], str]
    validate_proposal_context: Callable[
        [dict, PortfolioSnapshot, AssistantStore], str | None
    ]
    intent_from_dict: Callable[[dict], TradeIntent]
    detect_split_like_share_mismatch: Callable[..., dict[str, Any] | None]
    pending_buy_value_by_ticker: Callable[[list, Any], dict[str, Decimal]]
    resolve_earnings_days_away: Callable[[str, int | None], int | None]
    validate_trade_intent: Callable[..., ValidationResult]
    failure_data_integrity: str
    failure_infrastructure: str


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
    execution_context: ExecutionValidationContext | None = None,
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
        return deps.outcome_factory(
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
        return deps.outcome_factory(
            proposal=None, intent=None, validation=None, error=f"Unknown proposal: {proposal_id}",
            failure_class=deps.failure_data_integrity,
        )

    now_utc = deps.datetime_type.now(deps.timezone_type.utc)
    if now_utc > deps.datetime_type.fromisoformat(proposal["expires_at"]):
        return deps.outcome_factory(proposal=proposal, intent=None, validation=None, error="Proposal has expired.")
    if policy.execution_mode != "paper":
        return deps.outcome_factory(
            proposal=proposal, intent=None, validation=None,
            error="The active policy does not permit paper execution.",
        )
    if proposal["policy_version"] != policy.version:
        return deps.outcome_factory(
            proposal=proposal, intent=None, validation=None,
            error="Proposal policy version does not match the active policy.",
        )
    if proposal.get("policy_fingerprint") != deps.compute_policy_fingerprint(policy):
        return deps.outcome_factory(
            proposal=proposal, intent=None, validation=None,
            error=(
                "Proposal's policy fingerprint does not match the active policy's current content -- the "
                "policy may have been edited without a version bump (or this proposal predates fingerprint "
                "binding). Regenerate the proposal against the current policy."
            ),
        )

    context_error = deps.validate_proposal_context(
        proposal, current_portfolio, store
    )
    if context_error is not None:
        return deps.outcome_factory(
            proposal=proposal,
            intent=None,
            validation=None,
            error=context_error,
            failure_class=deps.failure_data_integrity,
        )

    broker = deps.import_broker()

    if not broker.PAPER_TRADING:
        return deps.outcome_factory(
            proposal=proposal, intent=None, validation=None,
            error="This workflow refuses live trading; PAPER_TRADING must remain True.",
        )
    if not broker.is_configured():
        return deps.outcome_factory(
            proposal=proposal, intent=None, validation=None, error="Alpaca paper credentials are not configured.",
            failure_class=deps.failure_infrastructure,
        )
    if kill_switch_active:
        reason = str(persistent_kill_switch.get("reason") or "active")
        return deps.outcome_factory(
            proposal=proposal,
            intent=None,
            validation=None,
            error=f"The execution kill switch is active ({reason}).",
        )
    if not current_portfolio.open_orders_available:
        return deps.outcome_factory(
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
        return deps.outcome_factory(
            proposal=proposal, intent=None, validation=None,
            error=f"extra_open_order_count must be a non-negative int, got {extra_open_order_count!r}.",
        )
    projected_open_orders = len(current_portfolio.open_orders) + extra_open_order_count
    if projected_open_orders >= policy.max_open_orders:
        pending_note = (
            f" (including {extra_open_order_count} earlier leg(s) of this batch)"
            if extra_open_order_count else ""
        )
        return deps.outcome_factory(
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
        return deps.outcome_factory(
            proposal=proposal, intent=None, validation=None, error=f"Malformed stored intent: {exc}",
            failure_class=deps.failure_data_integrity,
        )

    if intent.side not in policy.allowed_sides:
        return deps.outcome_factory(
            proposal=proposal, intent=intent, validation=None,
            error=f"Side '{intent.side}' is not allowed by policy.",
        )
    if intent.order_type not in policy.allowed_order_types:
        return deps.outcome_factory(
            proposal=proposal, intent=intent, validation=None,
            error=f"Order type '{intent.order_type}' is not allowed by policy.",
        )
    if intent.side == "buy" and not policy.allow_new_positions:
        held = {p.ticker.upper() for p in current_portfolio.positions}
        if intent.ticker.upper() not in held:
            return deps.outcome_factory(
                proposal=proposal, intent=intent, validation=None,
                error="Opening new positions is disabled by policy.",
            )

    expected_impact = proposal.get("expected_impact")
    if (
        isinstance(expected_impact, dict)
        and "position_shares_before" in expected_impact
    ):
        try:
            proposal_shares = deps.to_decimal(
                expected_impact["position_shares_before"],
                name="proposal.expected_impact.position_shares_before",
            )
            current_shares = deps.decimal_factory("0")
            for position in current_portfolio.positions:
                if position.ticker.upper() == intent.ticker.upper():
                    current_shares = deps.exact_decimal_add(
                        current_shares,
                        position.exact_field("shares"),
                        name=f"current {intent.ticker.upper()} shares",
                    )
            split_suspicion = deps.detect_split_like_share_mismatch(
                proposal_shares,
                current_shares,
            )
        except Exception as exc:
            return deps.outcome_factory(
                proposal=proposal,
                intent=intent,
                validation=None,
                error=(
                    "Could not verify proposal-time share identity: "
                    f"{type(exc).__name__}; refusing a potentially stale "
                    "corporate-action intent."
                ),
                failure_class=deps.failure_data_integrity,
            )
        if split_suspicion is not None:
            return deps.outcome_factory(
                proposal=proposal,
                intent=intent,
                validation=None,
                error=(
                    f"Share count for {intent.ticker.upper()} changed from "
                    f"{proposal_shares} at proposal time to {current_shares} "
                    "in the fresh broker snapshot, matching a suspected "
                    f"{split_suspicion['ratio']} "
                    f"{split_suspicion['direction']} split. Regenerate the "
                    "proposal after confirming the corporate action."
                ),
                failure_class=deps.failure_data_integrity,
            )

    try:
        broker_preflight = broker.assert_account_and_asset_ready(intent.ticker)
    except Exception as exc:
        return deps.outcome_factory(
            proposal=proposal,
            intent=intent,
            validation=None,
            error=f"Broker account/asset preflight failed: {exc}",
            failure_class=deps.failure_infrastructure,
        )

    if not policy.whole_shares_only:
        # SET1CR-003: an unreadable quantity must REFUSE here, not become
        # Decimal("0"). Substituting zero made the value integral, which
        # skipped the fractionable check below and handed the decision to the
        # gate. The gate does reject it, so nothing unsafe shipped -- but
        # "substitute a plausible default on error" is the exact shape this
        # project bans, and it silently disabled a broker-eligibility check
        # that the reader of this block would assume had run.
        try:
            requested_quantity = deps.to_decimal(
                intent.shares, name="intent.shares"
            )
        except (ValueError, TypeError, ArithmeticError) as exc:
            return deps.outcome_factory(
                proposal=proposal,
                intent=intent,
                validation=None,
                error=(
                    f"intent.shares is not an exact usable quantity "
                    f"({type(exc).__name__}); refusing before submission."
                ),
                broker_preflight=broker_preflight,
            )
        if (
            requested_quantity != requested_quantity.to_integral_value()
            and not broker_preflight.get("asset", {}).get("fractionable", False)
        ):
            return deps.outcome_factory(
                proposal=proposal,
                intent=intent,
                validation=None,
                error=(
                    f"{intent.ticker.upper()} is not marked fractionable by the "
                    "broker; refusing the fractional order before submission."
                ),
                broker_preflight=broker_preflight,
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
        return deps.outcome_factory(
            proposal=proposal, intent=intent, validation=None,
            error=f"Could not check recent order history for duplicates: malformed stored intent: {exc}",
            broker_preflight=broker_preflight,
            failure_class=deps.failure_data_integrity,
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
        if execution_context is None:
            quote = broker.get_latest_quote(intent.ticker)
        else:
            quote_getter = getattr(
                broker,
                "get_execution_validation_quote",
                None,
            )
            if not callable(quote_getter):
                raise PermissionError(
                    "Bound execution validation requires a session-owned "
                    "snapshot quote capability."
                )
            quote = quote_getter(
                intent.ticker,
                expected_snapshot_id=execution_context.snapshot_id,
            )
        quote_received_at = deps.datetime_type.now(deps.timezone_type.utc).isoformat()
        reference_price = quote.get("price_decimal", quote["price"])
        price_timestamp = quote["timestamp"]
        bid_price = quote.get("bid_decimal", quote.get("bid"))
        ask_price = quote.get("ask_decimal", quote.get("ask"))
    except Exception as exc:
        return deps.outcome_factory(
            proposal=proposal, intent=intent, validation=None,
            error=f"Could not fetch a live quote for {intent.ticker} to check price freshness: {exc}",
            broker_preflight=broker_preflight,
            failure_class=deps.failure_infrastructure,
        )

    pending_buy_value_by_ticker: dict[str, Decimal] = {}
    if intent.side == "buy":
        try:
            if execution_context is None:
                pending_quote_broker = broker
            else:
                # Local by design: ProposalValidationDeps freezes every
                # runtime collaborator and the kernel characterization test
                # rejects new module-global seams.
                class SnapshotBoundQuoteBroker:
                    __slots__ = (
                        "broker",
                        "datetime_type",
                        "eastern_timezone",
                        "max_stale_minutes",
                        "now",
                        "snapshot_id",
                    )

                    def __init__(
                        self,
                        bound_broker,
                        snapshot_id,
                        validation_now,
                        max_stale_minutes,
                        datetime_type,
                        eastern_timezone,
                    ):
                        self.broker = bound_broker
                        self.snapshot_id = snapshot_id
                        self.now = validation_now
                        self.max_stale_minutes = max_stale_minutes
                        self.datetime_type = datetime_type
                        self.eastern_timezone = eastern_timezone

                    def get_latest_quote(self, ticker):
                        getter = getattr(
                            self.broker,
                            "get_execution_validation_quote",
                            None,
                        )
                        if not callable(getter):
                            raise PermissionError(
                                "Bound execution validation requires "
                                "session-owned quote evidence."
                            )
                        quote = getter(
                            ticker,
                            expected_snapshot_id=self.snapshot_id,
                        )
                        timestamp = quote.get("timestamp")
                        if not isinstance(timestamp, self.datetime_type):
                            raise PermissionError(
                                "Pending execution quote has no typed timestamp."
                            )
                        if (
                            timestamp.tzinfo is None
                            or timestamp.utcoffset() is None
                        ):
                            raise PermissionError(
                                "Pending execution quote timestamp must be "
                                "timezone-aware."
                            )
                        if self.now.tzinfo is None:
                            comparable_timestamp = timestamp.astimezone(
                                self.eastern_timezone
                            ).replace(tzinfo=None)
                            comparable_now = self.now
                        else:
                            comparable_timestamp = timestamp
                            comparable_now = self.now
                        age_minutes = (
                            comparable_now - comparable_timestamp
                        ).total_seconds() / 60
                        if age_minutes > self.max_stale_minutes:
                            raise PermissionError(
                                f"Pending execution quote for {ticker} is "
                                f"{age_minutes:.1f} minutes old, exceeding "
                                f"the {self.max_stale_minutes:.1f}-minute "
                                "policy limit."
                            )
                        if age_minutes < -1.0:
                            raise PermissionError(
                                f"Pending execution quote for {ticker} is "
                                f"{abs(age_minutes):.1f} minutes in the future."
                            )
                        return quote

                pending_quote_broker = SnapshotBoundQuoteBroker(
                    broker,
                    execution_context.snapshot_id,
                    now_et,
                    policy.max_stale_price_minutes,
                    deps.datetime_type,
                    deps.eastern_timezone,
                )
            pending_buy_value_by_ticker = dict(
                deps.pending_buy_value_by_ticker(
                    current_portfolio.open_orders,
                    pending_quote_broker,
                )
            )
        except Exception as exc:
            return deps.outcome_factory(
                proposal=proposal, intent=intent, validation=None,
                error=(
                    f"Could not determine the dollar value of a pending buy order needed to check "
                    f"exposure/concentration limits: {exc}"
                ),
                reference_price=reference_price,
                broker_preflight=broker_preflight,
                quote=quote,
                quote_received_at=quote_received_at,
                failure_class=deps.failure_infrastructure,
            )
        try:
            for ticker, extra_value in (
                extra_pending_buy_value_by_ticker or {}
            ).items():
                key = ticker.upper()
                pending_buy_value_by_ticker[key] = deps.exact_decimal_add(
                    pending_buy_value_by_ticker.get(
                        key,
                        deps.decimal_factory("0"),
                    ),
                    deps.to_decimal(
                        extra_value,
                        name=f"extra pending buy value for {key}",
                    ),
                    name=f"combined pending buy value for {key}",
                )
        except (ArithmeticError, OverflowError, TypeError, ValueError) as exc:
            return deps.outcome_factory(
                proposal=proposal,
                intent=intent,
                validation=None,
                error=(
                    "Could not combine pending buy exposure exactly: "
                    f"{exc}"
                ),
                reference_price=reference_price,
                broker_preflight=broker_preflight,
                quote=quote,
                quote_received_at=quote_received_at,
                failure_class=deps.failure_infrastructure,
            )

    resolved_earnings_days_away = deps.resolve_earnings_days_away(
        intent.ticker, earnings_days_away
    )
    if policy.require_earnings_data and intent.side == "buy" and resolved_earnings_days_away is None:
        return deps.outcome_factory(
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
            failure_class=deps.failure_infrastructure,
        )

    try:
        max_basket_pct = deps.exact_decimal_multiply(
            policy.max_basket_pct,
            deps.decimal_factory("100"),
            name="policy max_basket_pct percent conversion",
        )
        max_leveraged_etf_pct = deps.exact_decimal_multiply(
            policy.max_leveraged_etf_pct,
            deps.decimal_factory("100"),
            name="policy max_leveraged_etf_pct percent conversion",
        )
    except (ArithmeticError, OverflowError, TypeError, ValueError) as exc:
        return deps.outcome_factory(
            proposal=proposal,
            intent=intent,
            validation=None,
            error=f"Could not convert signed policy exposure caps exactly: {exc}",
            reference_price=reference_price,
            broker_preflight=broker_preflight,
            quote=quote,
            quote_received_at=quote_received_at,
            failure_class=deps.failure_data_integrity,
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
        max_basket_pct=max_basket_pct,
        max_leveraged_etf_pct=max_leveraged_etf_pct,
        max_stale_price_minutes=policy.max_stale_price_minutes,
        max_slippage_pct=policy.max_slippage_pct,
        max_spread_pct=policy.max_spread_pct,
        earnings_blackout_days=policy.earnings_blackout_days,
        max_order_value=policy.max_order_value,
        min_cash_reserve_pct=policy.min_cash_reserve_pct,
        pending_buy_value_by_ticker=pending_buy_value_by_ticker,
        available_cash_override=available_cash_override,
        available_buying_power_override=available_buying_power_override,
        whole_shares_only=policy.whole_shares_only,
        execution_context=execution_context,
        execution_policy=(policy if execution_context is not None else None),
    )
    return deps.outcome_factory(
        proposal=proposal,
        intent=intent,
        validation=validation,
        error=None,
        reference_price=reference_price,
        broker_preflight=broker_preflight,
        quote=quote,
        quote_received_at=quote_received_at,
    )
