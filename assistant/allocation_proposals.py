"""
Allocation planning and proposal generation for the Watchlist "Create
purchase proposals using this split" feature: splits a user-specified
dollar amount across a user-picked cart of tickers according to
inverse-volatility weights, and produces one buy TradeProposal per
ticker that can afford the active policy's minimum quantity (one whole share
by default, or 0.000000001 share when fractional ordering is enabled).

Distinct from assistant/strategy_proposals.py: this is NOT based on any
validated research finding. The tickers are entirely user-picked -- this
project has confirmed zero signals as real edge for individual-stock
selection. The agent only sizes the split across whatever the user
chose, using the same inverse-volatility risk heuristic as the
Watchlist's combination-weighting display (assistant/stock_lookup.py).
Every proposal here is tagged evidence_status="user_directed_allocation"
-- never confirmed, never promising_unconfirmed, since no research claim
is being made about the tickers themselves.

Requires TradingPolicy.allow_new_positions=True to actually execute --
False by default (see assistant/policy.py), so this feature is inert
until the user explicitly opts in. Generating a proposal never bypasses
that gate: assistant/execution_service.py's execute_approved_paper_proposal()
independently re-checks it at approval time regardless of what this
module produces.

Every proposal still goes through the identical TradeProposal ->
"APPROVE <id>" -> execution_gate pipeline as every other proposal type
in this project -- nothing here submits an order directly.

build_allocation_plan() is the SINGLE shared source of truth for what an
allocation split actually produces -- both the UI preview and
generate_allocation_buy_proposals() consume it, so the preview can never
show something different from what actually gets proposed (GPT review,
2026-07-28: a prior version had the preview compute
`dollar_amount * weight_pct` directly, while proposal generation
independently floored to whole shares and skipped tickers that couldn't
afford 1 share -- e.g. a $50 allocation to a $200 stock showed as "+$50"
in the preview even though zero shares, and zero proposals, actually
resulted. The preview also ignored pending buy orders already in the
portfolio snapshot, understating the real eventual position.)
"""
from __future__ import annotations

import dataclasses
import hashlib
import math
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, DecimalException, ROUND_FLOOR, localcontext

from assistant.money import (
    decimal_text,
    deterministic_decimal_divide,
    deterministic_decimal_quantize,
    exact_decimal_add,
    exact_decimal_multiply,
    exact_decimal_subtract,
    exact_decimal_sum,
    to_decimal,
)
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_analytics import (
    estimate_pending_buy_value_by_ticker,  # noqa: F401 -- re-exported, scripts/personal_assistant_ui.py imports it from here
    preview_trade_impact,
)
from assistant.proposals import TradeProposal
from assistant.portfolio_snapshot import (
    PortfolioSnapshotIntegrityError,
    validate_long_only_portfolio_snapshot,
)
from assistant.schemas import DecisionPacket
from risk.execution_gate import (
    MAX_ORDER_QUANTITY,
    TradeIntent,
    canonical_order_quantity,
    is_valid_order_quantity,
    order_quantity_decimal,
)

EVIDENCE_STATUS = "user_directed_allocation"

_ONE_HUNDRED = Decimal("100")
_FRACTIONAL_QUANTUM = Decimal("0.000000001")
_MONEY_DISPLAY_QUANTUM = Decimal("0.01")
_FLOOR_CONTEXT_PRECISION = 64


def _bounded_decimal_or_none(value: object, *, name: str) -> Decimal | None:
    """Normalize one finite operand through the shared exact bound."""
    try:
        return exact_decimal_add(
            Decimal("0"),
            to_decimal(value, name=name),  # type: ignore[arg-type]
            name=f"{name} normalization",
        )
    except ValueError:
        return None


def _finite_float(value: Decimal, *, name: str) -> float:
    """Cross the legacy plan/proposal float boundary or fail closed."""
    try:
        normalized = exact_decimal_add(
            Decimal("0"), value, name=f"{name} normalization"
        )
        display = float(normalized)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} cannot be represented for display") from exc
    if not math.isfinite(display):
        raise ValueError(f"{name} cannot be represented for display")
    return display


def _float_price_round_trip(
    value: Decimal, *, name: str
) -> tuple[float, Decimal] | None:
    """Return a float-backed proposal price only when no decimal digit drifts.

    ``TradeProposal.reference_price`` is a legacy float with no exact companion.
    Accepting a Decimal that changes when serialized through that field would
    make its expected impact and stable identity describe different prices.
    """
    try:
        display = _finite_float(value, name=name)
        round_trip = to_decimal(display, name=f"{name} float round-trip")
    except ValueError:
        return None
    if round_trip != value:
        return None
    return display, round_trip


def _percentage(value: Decimal, total: Decimal, *, name: str) -> Decimal:
    if total == 0:
        return Decimal("0")
    ratio = deterministic_decimal_divide(value, total, name=f"{name} ratio")
    return exact_decimal_multiply(ratio, _ONE_HUNDRED, name=name)


def _money_display_text(value: Decimal, *, name: str) -> str:
    projected = deterministic_decimal_quantize(
        value,
        _MONEY_DISPLAY_QUANTUM,
        name=name,
    )
    return format(projected, ",.2f")


def _floor_order_quantity(
    numerator: Decimal,
    denominator: Decimal,
    *,
    whole_shares_only: bool,
    cap_at_broker_max: bool = False,
) -> Decimal | None:
    """Conservatively floor ``numerator / denominator`` independent of context.

    A half-even rounded quotient can cross upward over a whole- or
    nine-decimal-share boundary. First cross-multiply against the broker's
    maximum exact quantity, then divide in an explicit floor-rounded context
    with ample precision for at most 19 integer plus 9 fractional digits.
    """
    try:
        maximum_notional = exact_decimal_multiply(
            denominator,
            MAX_ORDER_QUANTITY,
            name="maximum broker-quantity notional",
        )
    except ValueError:
        return None
    if numerator > maximum_notional:
        return MAX_ORDER_QUANTITY if cap_at_broker_max else None
    try:
        with localcontext(
            Context(prec=_FLOOR_CONTEXT_PRECISION, rounding=ROUND_FLOOR)
        ):
            quotient = numerator / denominator
            sized = (
                quotient.to_integral_value(rounding=ROUND_FLOOR)
                if whole_shares_only
                else quotient.quantize(
                    _FRACTIONAL_QUANTUM,
                    rounding=ROUND_FLOOR,
                )
            )
    except DecimalException:
        return None
    return sized if sized >= 0 else None


def buy_proposal_refusal_reason(packet: DecisionPacket) -> str | None:
    """Return why a buy proposal cannot be measured from this packet.

    An empty active-order list is authoritative only when the broker book was
    actually observed.  Portfolio-integrity failure has the same consequence:
    the current exposure and cash available to a new buy are not measurable.
    Proposal-time refusal is required even though execution independently
    revalidates both conditions, because an approve-gated artifact and its UI
    preview must not claim a known projected position from unknown evidence.
    """
    evidence_failures: list[str] = []
    try:
        validate_long_only_portfolio_snapshot(packet.portfolio)
    except PortfolioSnapshotIntegrityError as exc:
        evidence_failures.append(
            "portfolio snapshot integrity is unavailable, so current and "
            f"projected buy exposure cannot be measured ({exc})"
        )
    if packet.portfolio.open_orders_available is not True:
        evidence_failures.append(
            "active-order data is unavailable, so pending buy exposure cannot "
            "be measured"
        )
    if packet.risk.available is not True:
        detail = packet.risk.unavailable_reason or (
            "portfolio integrity could not be proved"
        )
        evidence_failures.append(
            "portfolio risk evidence is unavailable, so current and projected "
            f"buy exposure cannot be measured ({detail})"
        )
    if not evidence_failures:
        return None
    message = "; ".join(evidence_failures)
    return message[0].upper() + message[1:] + (
        ". No buy proposal was created."
    )


@dataclasses.dataclass
class AllocationPlanEntry:
    ticker: str
    weight_pct: float
    target_dollars: float
    reference_price: float
    shares: int | str
    planned_notional: float
    unallocated_dollars: float
    existing_market_value: float
    pending_buy_value: float
    pending_value_unknown: bool
    projected_market_value: float
    projected_pct_of_equity: float
    position_limit_pct: float
    distance_to_limit_pct: float  # positive = room left under the policy limit; negative = already over it
    skipped: bool
    skip_reason: str | None
    # Canonical decimal evidence for downstream aggregate/proposal math.
    # ``planned_notional`` remains the legacy JSON/UI float projection.
    planned_notional_exact: str | None = None


def _allocation_entry_planned_notional(
    entry: AllocationPlanEntry,
) -> Decimal:
    exact_notional = (
        _bounded_decimal_or_none(
            entry.planned_notional_exact,
            name=f"{entry.ticker} exact planned notional",
        )
        if entry.planned_notional_exact is not None
        else None
    )
    if entry.planned_notional_exact is not None and exact_notional is None:
        raise ValueError(f"{entry.ticker} exact planned notional is invalid")
    if exact_notional is not None and exact_notional < 0:
        raise ValueError(f"{entry.ticker} planned notional cannot be negative")

    if entry.skipped and entry.shares == 0:
        if exact_notional not in (None, Decimal("0")):
            raise ValueError(
                f"{entry.ticker} skipped entry has a nonzero planned notional"
            )
        return Decimal("0")

    quantity = order_quantity_decimal(
        entry.shares,
        whole_shares_only=isinstance(entry.shares, int),
    )
    if quantity is None:
        raise ValueError(
            f"{entry.ticker} plan quantity cannot be summarized exactly"
        )
    price = _bounded_decimal_or_none(
        entry.reference_price,
        name=f"{entry.ticker} plan reference price",
    )
    if price is None or price <= 0:
        raise ValueError(
            f"{entry.ticker} plan price cannot be summarized exactly"
        )
    reconstructed = exact_decimal_multiply(
        quantity,
        price,
        name=f"{entry.ticker} reconstructed planned notional",
    )
    if exact_notional is not None and exact_notional != reconstructed:
        raise ValueError(
            f"{entry.ticker} exact planned notional disagrees with quantity "
            "times reference price"
        )
    return reconstructed if exact_notional is None else exact_notional


def allocation_plan_entry_notional_display(entry: AllocationPlanEntry) -> str:
    """Deterministic two-place display of one exact planned leg."""
    return _money_display_text(
        _allocation_entry_planned_notional(entry),
        name=f"{entry.ticker} planned-notional display",
    )


def summarize_allocation_plan(
    plan: list[AllocationPlanEntry],
    *,
    dollar_amount: object,
    available_cash: object,
) -> dict[str, str]:
    """Exact, deterministic aggregate strings for the Budgeted Buying UI.

    ``AllocationPlanEntry`` retains legacy float presentation fields. New
    entries carry the canonical planned-notional text produced during sizing;
    quantity-times-price reconstruction remains only as a compatibility path
    for an older/manually-created entry that lacks that companion.
    """
    budget = _bounded_decimal_or_none(
        dollar_amount,
        name="allocation summary budget",
    )
    cash = _bounded_decimal_or_none(
        available_cash,
        name="allocation summary available cash",
    )
    if budget is None or budget < 0 or cash is None or cash < 0:
        raise ValueError("allocation summary inputs are unavailable")
    if budget > cash:
        raise ValueError("allocation budget exceeds exact available cash")

    notionals: list[Decimal] = []
    for entry in plan:
        notionals.append(_allocation_entry_planned_notional(entry))

    planned = exact_decimal_sum(notionals, name="allocation planned spend")
    if planned > budget or planned > cash:
        raise ValueError(
            "allocation planned spend exceeds its exact budget or available cash"
        )
    unallocated = exact_decimal_subtract(
        budget,
        planned,
        name="allocation unallocated amount",
    )
    remaining_cash = exact_decimal_subtract(
        cash,
        planned,
        name="allocation remaining cash",
    )
    return {
        "budget_exact": decimal_text(budget),
        "budget_display": _money_display_text(
            budget,
            name="allocation budget display",
        ),
        "planned_spend_exact": decimal_text(planned),
        "planned_spend_display": _money_display_text(
            planned,
            name="allocation planned-spend display",
        ),
        "unallocated_exact": decimal_text(unallocated),
        "unallocated_display": _money_display_text(
            unallocated,
            name="allocation unallocated display",
        ),
        "remaining_cash_exact": decimal_text(remaining_cash),
        "remaining_cash_display": _money_display_text(
            remaining_cash,
            name="allocation remaining-cash display",
        ),
    }


def build_allocation_plan(
    packet: DecisionPacket,
    policy: TradingPolicy,
    weights_pct: dict[str, float],
    prices: dict[str, float],
    dollar_amount: float,
    pending_buy_value_by_ticker: dict[str, float] | None = None,
    pending_value_unknown_tickers: set[str] | None = None,
) -> list[AllocationPlanEntry]:
    """
    Computes, per ticker, EXACTLY what generate_allocation_buy_proposals()
    will do with it -- whole shares or nine-decimal fractional shares under
    the active policy, same as proposal
    generation -- plus context needed to judge the plan: existing
    holdings, pending buy orders (or an explicit "unknown" flag if a
    pending order's value can't be determined), the projected final
    position, and the applicable policy position limit.
    """
    if buy_proposal_refusal_reason(packet) is not None:
        return []
    snapshot = packet.portfolio
    held_value_by_ticker = {
        p.ticker.upper(): p.exact_field("market_value")
        for p in snapshot.positions
    }
    total_equity = snapshot.total_equity_exact_decimal
    pending_buy_value_by_ticker = pending_buy_value_by_ticker or {}
    pending_value_unknown_tickers = {
        str(ticker).strip().upper()
        for ticker in (pending_value_unknown_tickers or set())
    }
    limit_ratio = _bounded_decimal_or_none(
        policy.max_position_pct,
        name="policy max_position_pct",
    )
    budget_decimal = _bounded_decimal_or_none(
        dollar_amount,
        name="allocation budget",
    )
    if limit_ratio is None or limit_ratio < 0:
        return []
    try:
        limit_pct_decimal = exact_decimal_multiply(
            limit_ratio,
            _ONE_HUNDRED,
            name="policy position-limit percentage",
        )
        limit_pct = _finite_float(
            limit_pct_decimal,
            name="policy position-limit percentage",
        )
    except ValueError:
        return []
    if budget_decimal is None or budget_decimal <= 0:
        return []

    entries: list[AllocationPlanEntry] = []
    for ticker, weight_pct in weights_pct.items():
        ticker_upper = ticker.upper()
        existing_value = held_value_by_ticker.get(ticker_upper, Decimal("0"))
        pending_unknown = ticker_upper in pending_value_unknown_tickers
        pending_value = _bounded_decimal_or_none(
            pending_buy_value_by_ticker.get(ticker_upper, Decimal("0")),
            name=f"{ticker_upper} pending buy value",
        )
        if pending_value is None or pending_value < 0:
            # Preserve the explicit incomplete-projection contract while
            # preventing a malformed/negative pending amount from reducing
            # measured exposure.
            pending_value = Decimal("0")
            pending_unknown = True
        weight_decimal = _bounded_decimal_or_none(
            weight_pct,
            name=f"{ticker_upper} allocation weight",
        )
        try:
            target_decimal = (
                exact_decimal_multiply(
                    exact_decimal_multiply(
                        budget_decimal,
                        weight_decimal,
                        name=f"{ticker_upper} weighted allocation numerator",
                    ),
                    Decimal("0.01"),
                    name=f"{ticker_upper} target allocation",
                )
                if weight_decimal is not None and weight_decimal > 0
                else None
            )
            target_dollars = (
                _finite_float(
                    target_decimal,
                    name=f"{ticker_upper} target allocation",
                )
                if target_decimal is not None
                else 0.0
            )
            weight_display = (
                _finite_float(
                    weight_decimal,
                    name=f"{ticker_upper} allocation weight",
                )
                if weight_decimal is not None
                else 0.0
            )
            existing_display = _finite_float(
                existing_value,
                name=f"{ticker_upper} existing market value",
            )
            pending_display = _finite_float(
                pending_value,
                name=f"{ticker_upper} pending buy value",
            )
            base_projected = exact_decimal_add(
                existing_value,
                pending_value,
                name=f"{ticker_upper} existing plus pending value",
            )
            base_projected_pct = _percentage(
                base_projected,
                total_equity,
                name=f"{ticker_upper} projected position percentage",
            )
            base_projected_display = _finite_float(
                base_projected,
                name=f"{ticker_upper} projected market value",
            )
            base_projected_pct_display = _finite_float(
                base_projected_pct,
                name=f"{ticker_upper} projected position percentage",
            )
            base_distance_display = _finite_float(
                exact_decimal_subtract(
                    limit_pct_decimal,
                    base_projected_pct,
                    name=f"{ticker_upper} distance to position limit",
                ),
                name=f"{ticker_upper} distance to position limit",
            )
        except ValueError:
            # No approve-gated artifact may be built from arithmetic that
            # exceeds the exact/display boundary. Refuse the whole split;
            # returning plausible zero fields would be less honest.
            return []
        price = prices.get(ticker)
        price_decimal = _bounded_decimal_or_none(
            price,
            name=f"{ticker_upper} reference price",
        )
        price_projection = (
            _float_price_round_trip(
                price_decimal,
                name=f"{ticker_upper} reference price",
            )
            if price_decimal is not None
            else None
        )

        # Guarded Decimal conversion, not just `<= 0`: float NaN passes both
        # truthiness and ordered-comparison checks, then poisons sizing. This
        # boundary also rejects infinity, bool, and malformed numeric text.
        if (
            price_decimal is None
            or price_decimal <= 0
            or price_projection is None
        ):
            entries.append(
                AllocationPlanEntry(
                    ticker=ticker, weight_pct=weight_display, target_dollars=target_dollars,
                    reference_price=0.0, shares=0, planned_notional=0.0, unallocated_dollars=target_dollars,
                    existing_market_value=existing_display, pending_buy_value=pending_display,
                    pending_value_unknown=pending_unknown, projected_market_value=base_projected_display,
                    projected_pct_of_equity=base_projected_pct_display, position_limit_pct=limit_pct,
                    distance_to_limit_pct=base_distance_display,
                    skipped=True, skip_reason="No current price available.",
                    planned_notional_exact="0",
                )
            )
            continue
        reference_price, price_decimal = price_projection

        if target_decimal is None:
            entries.append(
                AllocationPlanEntry(
                    ticker=ticker, weight_pct=weight_display, target_dollars=0.0,
                    reference_price=reference_price, shares=0,
                    planned_notional=0.0, unallocated_dollars=0.0,
                    existing_market_value=existing_display, pending_buy_value=pending_display,
                    pending_value_unknown=pending_unknown, projected_market_value=base_projected_display,
                    projected_pct_of_equity=base_projected_pct_display, position_limit_pct=limit_pct,
                    distance_to_limit_pct=base_distance_display,
                    skipped=True, skip_reason="No usable positive allocation weight.",
                    planned_notional_exact="0",
                )
            )
            continue

        sized_quantity = _floor_order_quantity(
            target_decimal,
            price_decimal,
            whole_shares_only=policy.whole_shares_only,
        )
        shares = canonical_order_quantity(
            (
                int(sized_quantity)
                if policy.whole_shares_only and sized_quantity is not None
                else sized_quantity
            ),
            whole_shares_only=policy.whole_shares_only,
        )
        quantity_decimal = order_quantity_decimal(
            shares, whole_shares_only=policy.whole_shares_only
        ) if shares is not None else Decimal("0")
        shares = shares if shares is not None else 0
        try:
            planned_notional_decimal = exact_decimal_multiply(
                quantity_decimal,
                price_decimal,
                name=f"{ticker_upper} planned notional",
            )
            unallocated_decimal = exact_decimal_subtract(
                target_decimal,
                planned_notional_decimal,
                name=f"{ticker_upper} unallocated amount",
            )
            projected_value = exact_decimal_add(
                base_projected,
                planned_notional_decimal,
                name=f"{ticker_upper} projected market value",
            )
            projected_pct = _percentage(
                projected_value,
                total_equity,
                name=f"{ticker_upper} projected position percentage",
            )
            planned_notional = _finite_float(
                planned_notional_decimal,
                name=f"{ticker_upper} planned notional",
            )
            unallocated = _finite_float(
                unallocated_decimal,
                name=f"{ticker_upper} unallocated amount",
            )
            projected_value_display = _finite_float(
                projected_value,
                name=f"{ticker_upper} projected market value",
            )
            projected_pct_display = _finite_float(
                projected_pct,
                name=f"{ticker_upper} projected position percentage",
            )
            distance_display = _finite_float(
                exact_decimal_subtract(
                    limit_pct_decimal,
                    projected_pct,
                    name=f"{ticker_upper} distance to position limit",
                ),
                name=f"{ticker_upper} distance to position limit",
            )
        except ValueError:
            return []
        skipped = quantity_decimal <= 0
        skip_reason = (
            (
                f"${target_dollars:,.2f} allocation can't buy "
                f"{'1 share' if policy.whole_shares_only else '0.000000001 share'} "
                f"at ${reference_price:,.2f}."
            ) if skipped else None
        )

        entries.append(
            AllocationPlanEntry(
                ticker=ticker, weight_pct=weight_display, target_dollars=target_dollars, reference_price=reference_price,
                shares=shares, planned_notional=planned_notional, unallocated_dollars=unallocated,
                existing_market_value=existing_display, pending_buy_value=pending_display,
                pending_value_unknown=pending_unknown, projected_market_value=projected_value_display,
                projected_pct_of_equity=projected_pct_display, position_limit_pct=limit_pct,
                distance_to_limit_pct=distance_display, skipped=skipped, skip_reason=skip_reason,
                planned_notional_exact=decimal_text(planned_notional_decimal),
            )
        )
    return entries


def _stable_id(packet: DecisionPacket, policy: TradingPolicy, intent: TradeIntent, salt: str) -> str:
    # See assistant/proposals.py's _stable_id for why generated_at (a full
    # timestamp) is used instead of portfolio.as_of (just a date) -- a
    # same-day regeneration must not collide with a stale/expired row.
    raw = (
        f"watchlist_allocation|{salt}|{packet.generated_at}|{policy.version}|{intent.ticker.upper()}|"
        f"{intent.side}|{intent.shares}"
    )
    return "tp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def generate_allocation_buy_proposals(
    packet: DecisionPacket,
    policy: TradingPolicy,
    weights_pct: dict[str, float],
    prices: dict[str, float],
    dollar_amount: float,
    ttl_minutes: int = 15,
    pending_buy_value_by_ticker: dict[str, float] | None = None,
    pending_value_unknown_tickers: set[str] | None = None,
) -> list[TradeProposal]:
    """
    One buy proposal per ticker in `weights_pct` that can afford the active
    policy's minimum order quantity, generated from build_allocation_plan() -- the SAME plan a
    caller should preview before calling this, so what gets proposed
    always exactly matches what was shown.

    Does not check `dollar_amount` against available cash itself -- the
    caller (UI) should bound the input against the account balance, and
    execution_gate independently re-checks cash sufficiency for each
    proposal at approval time regardless.
    """
    budget_decimal = _bounded_decimal_or_none(
        dollar_amount,
        name="allocation budget",
    )
    if (
        buy_proposal_refusal_reason(packet) is not None
        or budget_decimal is None
        or budget_decimal <= 0
        or not weights_pct
    ):
        return []
    try:
        budget_display = _finite_float(
            budget_decimal,
            name="allocation budget",
        )
    except ValueError:
        return []

    plan = build_allocation_plan(
        packet, policy, weights_pct, prices, dollar_amount,
        pending_buy_value_by_ticker=pending_buy_value_by_ticker,
        pending_value_unknown_tickers=pending_value_unknown_tickers,
    )

    now = datetime.now(timezone.utc)
    proposals = []
    for entry in plan:
        if entry.skipped or not is_valid_order_quantity(
            entry.shares, whole_shares_only=policy.whole_shares_only
        ):
            continue

        intent = TradeIntent(
            ticker=entry.ticker,
            side="buy",
            shares=entry.shares,
            order_type="market",
                rationale=(
                f"User-directed allocation: {entry.weight_pct:.1f}% of ${budget_display:,.2f} "
                f"(inverse-volatility weighted) -> {entry.shares} shares at ~${entry.reference_price:,.2f}."
            ),
        )
        proposal_id = _stable_id(
            packet,
            policy,
            intent,
            salt=decimal_text(budget_decimal),
        )
        proposals.append(
            TradeProposal(
                proposal_id=proposal_id,
                created_at=now.isoformat(),
                expires_at=(now + timedelta(minutes=ttl_minutes)).isoformat(),
                status="proposed",
                idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
                policy_version=policy.version,
                policy_fingerprint=compute_policy_fingerprint(policy),
                intent=intent,
                reference_price=entry.reference_price,
                price_timestamp=now.isoformat(),
                reasons=[
                    f"You chose to allocate ${budget_display:,.2f} across your Watchlist cart; "
                    f"{entry.ticker} received {entry.weight_pct:.1f}% by inverse-volatility weighting."
                ],
                evidence_status=EVIDENCE_STATUS,
                expected_impact=preview_trade_impact(
                    packet.portfolio, entry.ticker, "buy", entry.shares, entry.reference_price
                ),
                alternatives=[
                    "Take no action -- nothing is bought until you type the approval phrase for each ticker.",
                    "Adjust the dollar amount or the cart and check again before approving.",
                ],
                uncertainties=[
                    "This is a user-directed purchase, not a research-backed recommendation -- this project "
                    "has confirmed zero signals as real edge for individual-stock selection.",
                    "The allocation weighting only sizes risk by trailing volatility; it says nothing about "
                    "which stock is more likely to go up.",
                    "Share quantity is rounded down to the granularity allowed by your policy, so the actual "
                    "dollar amount spent per ticker may be less than its exact allocated share.",
                    "Requires allow_new_positions=true in your policy -- off by default, so this will be "
                    "blocked at approval time unless you've explicitly enabled it.",
                    "Market orders can fill away from the displayed reference price.",
                ],
            )
        )
    return proposals


DISCRETE_EVIDENCE_STATUS = "user_directed_discrete_buy"


def generate_discrete_buy_proposal(
    packet: DecisionPacket,
    policy: TradingPolicy,
    *,
    ticker: str,
    shares: object,
    price: object,
    ttl_minutes: int = 15,
    now: datetime | None = None,
) -> dict:
    """One buy proposal for an exact policy-permitted quantity of one ticker.

    The Discrete Buying tab (owner request 2026-08-14) sizes either by share
    count or by dollar budget, but both arrive here as an exact share quantity --
    the dollar path converts first, through
    `assistant.discrete_trade.size_by_dollar_amount`, in exact Decimal.

    Deliberately NOT routed through build_allocation_plan(): an explicit share
    instruction does not need budget allocation or rounding. A caller who
    names a quantity must get that quantity or a stated refusal, never a
    quietly smaller order.

    Returns ``{"created": True, "proposal": TradeProposal}`` or
    ``{"created": False, "reason": str}``.
    """
    evidence_refusal = buy_proposal_refusal_reason(packet)
    if evidence_refusal is not None:
        return {"created": False, "reason": evidence_refusal}
    normalized = str(ticker).strip().upper()
    if not normalized:
        return {"created": False, "reason": "A ticker is required."}
    canonical_shares = canonical_order_quantity(
        shares, whole_shares_only=policy.whole_shares_only
    )
    if canonical_shares is None:
        return {
            "created": False,
            "reason": (
                f"Shares to buy must be {'a whole number greater than zero' if policy.whole_shares_only else 'a positive exact number with at most 9 decimal places'}, got {shares!r}."
            ),
        }
    shares = canonical_shares
    price_decimal = _bounded_decimal_or_none(
        price,
        name=f"{normalized} reference price",
    )
    if price_decimal is None or price_decimal <= 0:
        return {
            "created": False,
            "reason": (
                f"{normalized} has no usable reference price ({price!r}), so this "
                "purchase cannot be priced or previewed."
            ),
        }

    quantity_decimal = order_quantity_decimal(
        shares, whole_shares_only=policy.whole_shares_only
    )
    if quantity_decimal is None:
        return {
            "created": False,
            "reason": "The requested share quantity cannot be represented exactly.",
        }
    price_projection = _float_price_round_trip(
        price_decimal,
        name=f"{normalized} reference price",
    )
    if price_projection is None:
        return {
            "created": False,
            "reason": (
                f"{normalized}'s exact reference price cannot be represented "
                "without changing it in the proposal artifact."
            ),
        }
    reference_price, price_decimal = price_projection
    try:
        notional = exact_decimal_multiply(
            price_decimal,
            quantity_decimal,
            name=f"{normalized} discrete-buy notional",
        )
    except ValueError:
        return {
            "created": False,
            "reason": (
                f"The notional for {normalized} cannot be represented exactly, "
                "so this purchase was not proposed."
            ),
        }
    max_order_value = _bounded_decimal_or_none(
        policy.max_order_value,
        name="policy maximum order value",
    )
    if max_order_value is None or max_order_value <= 0:
        return {
            "created": False,
            "reason": (
                "The active policy has no usable positive maximum order value "
                f"({policy.max_order_value!r})."
            ),
        }
    try:
        notional_display = _finite_float(
            notional,
            name=f"{normalized} discrete-buy notional",
        )
        max_order_value_display = _finite_float(
            max_order_value,
            name="policy maximum order value",
        )
    except ValueError:
        return {
            "created": False,
            "reason": (
                "The proposed notional or policy maximum cannot be represented "
                "safely in the proposal artifact."
            ),
        }
    if notional > max_order_value:
        fits_sized = _floor_order_quantity(
            max_order_value,
            price_decimal,
            whole_shares_only=policy.whole_shares_only,
            cap_at_broker_max=True,
        )
        fits = canonical_order_quantity(
            (
                int(fits_sized)
                if policy.whole_shares_only and fits_sized is not None
                else fits_sized
            ),
            whole_shares_only=policy.whole_shares_only,
        )
        remedy = (
            f" At ${reference_price:,.2f} per share, up to {fits} share(s) fit "
            "in one order."
            if fits is not None
            else " Even one share exceeds that limit at the current price."
        )
        return {
            "created": False,
            "reason": (
                f"Buying {shares} share(s) of {normalized} is "
                f"${notional_display:,.2f}, above your policy's "
                f"${max_order_value_display:,.2f} maximum order value.{remedy}"
            ),
        }

    at = now or datetime.now(timezone.utc)
    intent = TradeIntent(
        ticker=normalized,
        side="buy",
        shares=shares,
        order_type="market",
        rationale=(
            f"Owner-directed purchase of {shares} share(s) of {normalized} at "
            f"~${reference_price:,.2f}."
        ),
    )
    proposal_id = _stable_id(packet, policy, intent, salt=f"discrete|{decimal_text(notional)}")
    return {
        "created": True,
        "proposal": TradeProposal(
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
                f"You chose to buy {shares} share(s) of {normalized}, about "
                f"${notional_display:,.2f} at the reference price.",
                "This is your own instruction, not a project recommendation: this "
                "project has confirmed zero signals as real edge for "
                "individual-stock selection.",
            ],
            evidence_status=DISCRETE_EVIDENCE_STATUS,
            expected_impact=preview_trade_impact(
                packet.portfolio, normalized, "buy", shares, reference_price
            ),
            alternatives=[
                "Take no action -- nothing is bought until you type the approval "
                "phrase for this proposal.",
                "Buy a different number of shares, or size it by dollar amount "
                "instead.",
            ],
            uncertainties=[
                "Market orders can fill away from the displayed reference price.",
                "Policy limits are re-checked independently at approval time; this "
                "proposal is not a promise that the order will pass that check.",
                "Requires allow_new_positions=true in your policy -- off by default, "
                "so this will be blocked at approval time unless you enabled it.",
                "If another proposal for this ticker and side is already in flight, "
                "approval is refused until that one resolves.",
            ],
        ),
    }
