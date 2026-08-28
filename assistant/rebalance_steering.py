"""Buy-only cash steering toward under-band sleeves (REBAL-1 Stage 2).

The owner supplies a NEW-MONEY budget and picks one ticker per sleeve. This
module allocates that budget only toward sleeves whose projected weight sits
below their lower band edge, and produces one APPROVE-gated buy proposal per
selected sleeve.

Why buy-only, stated because the omission is the design:

Stage 2 never sells. Every other sell path in this app is either a computed
policy breach or the owner's explicit instruction about a named holding;
selling to rebalance would be the app trimming a winner on its own
initiative, which is Stage 3 and needs separate authorization. An OVERWEIGHT
sleeve therefore produces nothing here at all -- not a smaller buy, not a
suggestion, nothing.

Two rules carried forward from Stage 1, for the same reasons:

* **Under-band is measured on the PROJECTED weight**, so money already
  working in an unfilled order counts. Sizing against the current weight
  would prepare a second correction for a gap the first order is already
  closing -- the duplication HEDGER-004 found in the hedge sleeve.
* **An unusable value refuses everything.** Sleeve weights share one equity
  denominator, so a single corrupt holding moves every sleeve's percentage
  and can invent an under-band sleeve to steer money into.

Sizing delegates to `assistant.allocation_proposals.build_allocation_plan`,
the same function the preview uses, so what is displayed and what is proposed
cannot drift apart. Only the ELIGIBILITY rule and the budget split are
computed here.

Nothing here approves or submits. Each proposal still needs the typed
approval phrase and an independent execution-gate pass, and there is
deliberately no submit-all: a partly-filled multi-sleeve correction is a
different portfolio from the one that was sized.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from assistant.allocation_proposals import (
    build_allocation_plan,
    buy_proposal_refusal_reason,
)
from assistant.money import (
    decimal_or_none,
    decimal_text,
    deterministic_decimal_divide,
    exact_decimal_add,
    exact_decimal_multiply,
    exact_decimal_subtract,
    exact_decimal_sum,
    to_decimal,
)
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_analytics import preview_trade_impact
from assistant.portfolio_rebalance import (
    STATUS_UNDERWEIGHT,
    RebalanceReport,
    evaluate_portfolio_rebalance,
)
from assistant.proposals import TradeProposal
from assistant.rebalance_profile import (
    SLEEVE_CASH,
    SLEEVE_LABELS,
    SLEEVE_OTHER,
    AllocationProfile,
    sleeve_membership,
)
from assistant.schemas import DecisionPacket
from risk.execution_gate import TradeIntent, is_valid_order_quantity

EVIDENCE_STATUS = "user_directed_rebalance_buy"

#: Sleeves that can never receive steered money, whatever their band says.
#: Cash is the budget's source, and the residual is by definition the set of
#: holdings the profile does not describe -- steering money into it would be
#: buying toward a target that names nothing.
INELIGIBLE_SLEEVES = frozenset({SLEEVE_CASH, SLEEVE_OTHER})

UNPROVEN_SHAPE_DISCLOSURE = (
    "Sleeve targets and band width are your stated preference, not a "
    "research result. Moving money toward them is not evidence-backed and "
    "this project has confirmed no signal as real edge."
)


@dataclasses.dataclass(frozen=True)
class SteeringLeg:
    """One sleeve's share of the budget, and the ticker chosen for it."""

    sleeve: str
    ticker: str
    shortfall_to_lower_edge_exact: str
    allocated_dollars_exact: str
    #: Exact reference price as carried by the shared allocation planner.
    #: Annotated `object` because it holds a Decimal, not a float: the
    #: planner is handed exact prices and the value is only formatted at
    #: the display edge. Claiming `float` here would be a lie the type
    #: checker cannot catch and a reader would believe.
    reference_price: object
    shares: int | str
    planned_notional_exact: str


@dataclasses.dataclass(frozen=True)
class SteeringPlan:
    """What a budget would do, before any proposal exists."""

    profile_version: str
    profile_fingerprint: str
    budget_exact: str
    legs: tuple[SteeringLeg, ...]
    unallocated_exact: str
    eligible_sleeves: tuple[str, ...]
    disclosures: tuple[str, ...]
    refusals: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return not self.refusals


def eligible_sleeves(report: RebalanceReport) -> list[str]:
    """Sleeves below their lower band edge that may receive new money.

    Reads `band_state`, not `status`: a sleeve can be genuinely under its
    band while displaying another label, and steering must follow the band.
    """
    return [
        row.sleeve
        for row in report.rows
        if row.sleeve not in INELIGIBLE_SLEEVES
        and row.band_state == STATUS_UNDERWEIGHT
    ]


def _shortfall_to_lower_edge(
    report: RebalanceReport, profile: AllocationProfile, sleeve: str
) -> Decimal | None:
    """Exact dollars needed to reach the LOWER EDGE, not the target.

    The band's whole purpose is that being inside it is enough. Steering to
    the target would spend more than the profile asks for and, on the next
    ordinary price move, hand back the turnover the band exists to avoid.
    """
    row = next((r for r in report.rows if r.sleeve == sleeve), None)
    equity = decimal_or_none(report.total_equity_exact)
    if row is None or equity is None or equity <= 0:
        return None
    market_value = decimal_or_none(row.market_value_exact)
    pending_value = decimal_or_none(row.pending_value_exact)
    if market_value is None or pending_value is None:
        return None
    target = decimal_or_none(profile.targets.get(sleeve))
    band_fraction = decimal_or_none(profile.band_fraction)
    if target is None or band_fraction is None:
        return None
    try:
        half_width = exact_decimal_multiply(
            target,
            band_fraction,
            name=f"{sleeve} band half-width",
        )
        lower = exact_decimal_subtract(
            target,
            half_width,
            name=f"{sleeve} lower band edge",
        )
        lower_edge_value = exact_decimal_multiply(
            exact_decimal_multiply(
                equity,
                lower,
                name=f"{sleeve} lower-edge dollar numerator",
            ),
            Decimal("0.01"),
            name=f"{sleeve} lower-edge dollar value",
        )
        shortfall = exact_decimal_subtract(
            exact_decimal_subtract(
                lower_edge_value,
                market_value,
                name=f"{sleeve} held-value shortfall",
            ),
            pending_value,
            name=f"{sleeve} projected shortfall",
        )
    except ValueError:
        return None
    return shortfall if shortfall > 0 else Decimal("0")


def steering_input_fingerprint(
    packet: DecisionPacket,
    report: RebalanceReport,
    policy: TradingPolicy,
    *,
    selections: dict[str, str] | None,
    budget: object,
) -> str:
    """Fingerprint every input that can change a displayed steering card.

    This is deliberately broader than the values used directly for sizing.
    A card authorizes a trade against a portfolio snapshot, not just against
    its date and total equity. Hashing the complete snapshot closes the case
    where two holdings move in opposite directions on the same day while the
    old hand-built signature stays unchanged.
    """
    budget_decimal = decimal_or_none(budget)
    payload = {
        "portfolio": dataclasses.asdict(packet.portfolio),
        "report": dataclasses.asdict(report),
        "policy_fingerprint": compute_policy_fingerprint(policy),
        "selections": sorted(
            (str(sleeve), str(ticker).strip().upper())
            for sleeve, ticker in (selections or {}).items()
        ),
        "budget_exact": (
            decimal_text(budget_decimal)
            if budget_decimal is not None
            else repr(budget)
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def plan_cash_steering(
    packet: DecisionPacket,
    profile: AllocationProfile,
    policy: TradingPolicy,
    *,
    budget: object,
    selections: dict[str, str] | None,
    prices: dict[str, object],
) -> SteeringPlan:
    """Split a new-money budget across under-band sleeves. Proposes nothing.

    `selections` maps sleeve -> the ticker the owner chose for it. A sleeve
    with no selection is skipped and named; this module never picks a ticker,
    because choosing which name to buy inside a sleeve is a judgement the
    project has no evidence to make.
    """
    report = evaluate_portfolio_rebalance(packet.portfolio, profile, policy=policy)
    refusals: list[str] = list(report.refusals)
    disclosures = [UNPROVEN_SHAPE_DISCLOSURE, *report.disclosures]

    evidence_refusal = buy_proposal_refusal_reason(packet)
    if evidence_refusal is not None:
        refusals.append(evidence_refusal)

    try:
        budget_decimal = exact_decimal_add(
            Decimal("0"),
            to_decimal(budget, name="new-money budget"),  # type: ignore[arg-type]
            name="new-money budget normalization",
        )
    except ValueError:
        budget_decimal = None
    if budget_decimal is None or budget_decimal <= 0:
        refusals.append(
            f"The new-money budget must be a positive amount, got {budget!r}."
        )

    eligible = eligible_sleeves(report) if report.usable else []
    if report.usable and not eligible:
        refusals.append(
            "No sleeve is below its lower band, so there is nothing to steer "
            "new money toward. This page never sells to correct an overweight "
            "sleeve."
        )

    membership = {}
    try:
        membership = sleeve_membership()
    except Exception as exc:  # config corruption already refuses upstream
        refusals.append(str(exc))

    chosen: dict[str, str] = {}
    for sleeve in eligible:
        ticker = (selections or {}).get(sleeve)
        if ticker is None or not str(ticker).strip():
            refusals.append(
                f"{SLEEVE_LABELS.get(sleeve, sleeve)} is below its band but no "
                "ticker was chosen for it. This app does not pick which name "
                "to buy inside a sleeve."
            )
            continue
        name = str(ticker).strip().upper()
        if membership.get(name) != sleeve:
            refusals.append(
                f"{name} is not a configured member of "
                f"{SLEEVE_LABELS.get(sleeve, sleeve)}, so buying it would not "
                "move that sleeve."
            )
            continue
        chosen[sleeve] = name

    if refusals:
        refused_budget = (
            decimal_text(budget_decimal)
            if budget_decimal is not None and budget_decimal > 0
            else "0"
        )
        return SteeringPlan(
            profile_version=report.profile_version,
            profile_fingerprint=report.profile_fingerprint,
            budget_exact=refused_budget,
            legs=(), unallocated_exact=refused_budget,
            eligible_sleeves=tuple(eligible),
            disclosures=tuple(disclosures), refusals=tuple(refusals),
        )

    # Split proportionally to each sleeve's shortfall, capped so no sleeve is
    # steered past its lower edge. Money left over is REPORTED, never pushed
    # onto another sleeve to make the number come out even.
    shortfalls: dict[str, Decimal] = {}
    for sleeve in chosen:
        shortfall = _shortfall_to_lower_edge(report, profile, sleeve)
        if shortfall is None:
            refusals.append(
                f"{SLEEVE_LABELS.get(sleeve, sleeve)}'s shortfall could not be "
                "computed from this snapshot."
            )
            continue
        shortfalls[sleeve] = shortfall
    try:
        total_shortfall = exact_decimal_sum(
            shortfalls.values(),
            name="selected sleeve shortfalls",
        )
    except ValueError:
        total_shortfall = Decimal("0")
        refusals.append(
            "The selected sleeve shortfalls exceed the exact sizing boundary."
        )
    if not refusals and total_shortfall <= 0:
        refusals.append(
            "Every selected sleeve already reaches its lower band, so no new "
            "money is needed."
        )

    if refusals:
        return SteeringPlan(
            profile_version=report.profile_version,
            profile_fingerprint=report.profile_fingerprint,
            budget_exact=decimal_text(budget_decimal),
            legs=(), unallocated_exact=decimal_text(budget_decimal),
            eligible_sleeves=tuple(eligible),
            disclosures=tuple(disclosures), refusals=tuple(refusals),
        )

    allocations: dict[str, Decimal] = {}
    try:
        remaining = budget_decimal
        for sleeve in sorted(shortfalls):
            share = deterministic_decimal_divide(
                exact_decimal_multiply(
                    budget_decimal,
                    shortfalls[sleeve],
                    name=f"{sleeve} proportional allocation numerator",
                ),
                total_shortfall,
                name=f"{sleeve} proportional allocation",
            )
            allocated = min(share, shortfalls[sleeve], remaining)
            allocations[sleeve] = allocated
            remaining = exact_decimal_subtract(
                remaining,
                allocated,
                name="steering allocation remainder",
            )
    except ValueError:
        return SteeringPlan(
            profile_version=report.profile_version,
            profile_fingerprint=report.profile_fingerprint,
            budget_exact=decimal_text(budget_decimal),
            legs=(),
            unallocated_exact=decimal_text(budget_decimal),
            eligible_sleeves=tuple(eligible),
            disclosures=tuple(disclosures),
            refusals=(
                "The new-money split exceeds the exact sizing boundary, so "
                "no buy was prepared.",
            ),
        )

    tickers_to_size = {
        chosen[s] for s in allocations if allocations[s] > 0
    }
    usable_prices = {
        ticker: price
        for ticker, raw in ((t, prices.get(t)) for t in tickers_to_size)
        if (price := decimal_or_none(raw)) is not None and price > 0
    }
    missing = sorted(tickers_to_size - set(usable_prices))
    if missing:
        return SteeringPlan(
            profile_version=report.profile_version,
            profile_fingerprint=report.profile_fingerprint,
            budget_exact=decimal_text(budget_decimal), legs=(),
            unallocated_exact=decimal_text(budget_decimal),
            eligible_sleeves=tuple(eligible), disclosures=tuple(disclosures),
            refusals=(
                "Every chosen ticker needs a usable current price before the "
                f"budget can be sized. Missing: {', '.join(missing)}. Deselect "
                "that sleeve or try again once a fresh close is recorded.",
            ),
        )

    # Size each sleeve directly from its exact allocated dollars. Routing a
    # ratio through the planner's legacy percentage input would project that
    # ratio and could make the reconstructed target differ from the exact
    # sleeve allocation at a sub-cent boundary.
    plan_entries = []
    for sleeve in sorted(allocations):
        if allocations[sleeve] <= 0:
            continue
        ticker = chosen[sleeve]
        sized = build_allocation_plan(
            packet,
            policy,
            {ticker: Decimal("100")},
            {ticker: usable_prices[ticker]},
            allocations[sleeve],
        )
        if len(sized) != 1:
            return SteeringPlan(
                profile_version=report.profile_version,
                profile_fingerprint=report.profile_fingerprint,
                budget_exact=decimal_text(budget_decimal),
                legs=(),
                unallocated_exact=decimal_text(budget_decimal),
                eligible_sleeves=tuple(eligible),
                disclosures=tuple(disclosures),
                refusals=(
                    "The shared allocation planner could not prove this "
                    "steering split from current portfolio evidence, so no "
                    "buy was prepared.",
                ),
            )
        plan_entries.extend(sized)
    by_ticker = {entry.ticker: entry for entry in plan_entries}

    legs: list[SteeringLeg] = []
    unallocated = remaining
    unaffordable: list[str] = []
    for sleeve in sorted(allocations):
        ticker = chosen[sleeve]
        entry = by_ticker.get(ticker)
        if entry is None:
            continue
        if entry.skipped or not is_valid_order_quantity(
            entry.shares, whole_shares_only=policy.whole_shares_only
        ):
            # Named, never silently dropped: a budget that quietly funds three
            # of four chosen sleeves produces a different portfolio from the
            # one the owner sized.
            unaffordable.append(
                f"{ticker} ({SLEEVE_LABELS.get(sleeve, sleeve)}): "
                f"{entry.skip_reason or 'below the minimum order quantity'}"
            )
            try:
                unallocated = exact_decimal_add(
                    unallocated,
                    allocations[sleeve],
                    name="unaffordable steering allocation remainder",
                )
            except ValueError:
                return SteeringPlan(
                    profile_version=report.profile_version,
                    profile_fingerprint=report.profile_fingerprint,
                    budget_exact=decimal_text(budget_decimal),
                    legs=(),
                    unallocated_exact=decimal_text(budget_decimal),
                    eligible_sleeves=tuple(eligible),
                    disclosures=tuple(disclosures),
                    refusals=(
                        "The steering remainder could not be represented "
                        "exactly, so no buy was prepared.",
                    ),
                )
            continue
        notional = decimal_or_none(entry.planned_notional_exact)
        if (
            entry.planned_notional_exact is None
            or notional is None
            or notional < 0
            or notional > allocations[sleeve]
        ):
            return SteeringPlan(
                profile_version=report.profile_version,
                profile_fingerprint=report.profile_fingerprint,
                budget_exact=decimal_text(budget_decimal),
                legs=(),
                unallocated_exact=decimal_text(budget_decimal),
                eligible_sleeves=tuple(eligible),
                disclosures=tuple(disclosures),
                refusals=(
                    f"{ticker}'s exact planned notional could not be proved "
                    "within its sleeve allocation, so no buy was prepared.",
                ),
            )
        try:
            unallocated = exact_decimal_add(
                unallocated,
                exact_decimal_subtract(
                    allocations[sleeve],
                    notional,
                    name=f"{ticker} unspent steering allocation",
                ),
                name="steering unallocated total",
            )
        except ValueError:
            return SteeringPlan(
                profile_version=report.profile_version,
                profile_fingerprint=report.profile_fingerprint,
                budget_exact=decimal_text(budget_decimal),
                legs=(),
                unallocated_exact=decimal_text(budget_decimal),
                eligible_sleeves=tuple(eligible),
                disclosures=tuple(disclosures),
                refusals=(
                    "The steering remainder could not be represented "
                    "exactly, so no buy was prepared.",
                ),
            )
        legs.append(
            SteeringLeg(
                sleeve=sleeve, ticker=ticker,
                shortfall_to_lower_edge_exact=decimal_text(shortfalls[sleeve]),
                allocated_dollars_exact=decimal_text(allocations[sleeve]),
                reference_price=entry.reference_price,
                shares=entry.shares,
                planned_notional_exact=decimal_text(notional),
            )
        )

    if unaffordable:
        disclosures.append(
            "Not funded at the active minimum order quantity: "
            + "; ".join(unaffordable)
            + ". Raise the budget, choose a cheaper name in that sleeve, or "
            "enable fractional shares in Settings & Features."
        )

    return SteeringPlan(
        profile_version=report.profile_version,
        profile_fingerprint=report.profile_fingerprint,
        budget_exact=decimal_text(budget_decimal),
        legs=tuple(legs),
        unallocated_exact=decimal_text(unallocated),
        eligible_sleeves=tuple(eligible),
        disclosures=tuple(disclosures),
        refusals=(),
    )


def _stable_id(
    packet: DecisionPacket, policy: TradingPolicy, intent: TradeIntent, salt: str
) -> str:
    raw = (
        f"{EVIDENCE_STATUS}|{packet.generated_at}|{policy.version}|"
        f"{intent.ticker.upper()}|{intent.side}|{intent.shares}|{salt}"
    )
    return "tp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def generate_steering_proposals(
    packet: DecisionPacket,
    profile: AllocationProfile,
    policy: TradingPolicy,
    *,
    budget: object,
    selections: dict[str, str] | None,
    prices: dict[str, object],
    ttl_minutes: int = 15,
    now: datetime | None = None,
) -> dict:
    """One APPROVE-gated buy proposal per funded sleeve.

    Returns ``{"created": True, "plan": ..., "proposals": [...]}`` or
    ``{"created": False, "plan": ..., "reason": str}``.
    """
    plan = plan_cash_steering(
        packet, profile, policy,
        budget=budget, selections=selections, prices=prices,
    )
    if not plan.usable:
        return {"created": False, "plan": plan, "reason": " ".join(plan.refusals)}
    if not plan.legs:
        return {
            "created": False, "plan": plan,
            "reason": (
                "The budget cannot fund any chosen sleeve at the active "
                "minimum order quantity."
            ),
        }

    at = now or datetime.now(timezone.utc)
    proposals: list[TradeProposal] = []
    for leg in plan.legs:
        intent = TradeIntent(
            ticker=leg.ticker, side="buy", shares=leg.shares,
            order_type="market",
            rationale=(
                f"Rebalance steering: {SLEEVE_LABELS.get(leg.sleeve, leg.sleeve)} "
                f"is below its lower band by "
                f"${float(leg.shortfall_to_lower_edge_exact):,.2f}; "
                f"{leg.shares} share(s) of {leg.ticker} at "
                f"~${leg.reference_price:,.2f}."
            ),
        )
        proposal_id = _stable_id(
            packet, policy, intent,
            # The profile fingerprint is part of the identity, so a
            # profile edit cannot silently reuse a proposal sized against
            # targets the owner has since changed.
            salt=f"{plan.profile_fingerprint}|{plan.budget_exact}",
        )
        expected_impact = preview_trade_impact(
            packet.portfolio, leg.ticker, "buy",
            leg.shares, leg.reference_price,
        )
        expected_impact.update({
            "allocation_profile_version": plan.profile_version,
            "allocation_profile_fingerprint": plan.profile_fingerprint,
        })
        proposals.append(
            TradeProposal(
                proposal_id=proposal_id,
                created_at=at.isoformat(),
                expires_at=(at + timedelta(minutes=ttl_minutes)).isoformat(),
                status="proposed",
                idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
                policy_version=policy.version,
                policy_fingerprint=compute_policy_fingerprint(policy),
                intent=intent,
                # Sizing above stays Decimal-exact. TradeProposal is a JSON
                # persistence/display boundary whose established schema uses
                # a float reference price; retaining Decimal here makes
                # AssistantStore.save_proposal() fail before a card appears.
                reference_price=float(leg.reference_price),
                price_timestamp=at.isoformat(),
                reasons=[
                    f"{SLEEVE_LABELS.get(leg.sleeve, leg.sleeve)} is below its "
                    f"lower band; ${float(leg.allocated_dollars_exact):,.2f} of "
                    f"your ${float(plan.budget_exact):,.2f} new-money budget is "
                    f"allocated to it.",
                    f"You chose {leg.ticker} for that sleeve. This app does not "
                    "pick which name to buy inside a sleeve.",
                    f"Sized to reach the LOWER BAND EDGE, not the target: the "
                    "band exists so that being inside it is enough.",
                ],
                evidence_status=EVIDENCE_STATUS,
                expected_impact=expected_impact,
                alternatives=[
                    "Take no action -- nothing is bought until you type the "
                    "approval phrase for each proposal.",
                    "Lower the budget, or choose a different ticker for a "
                    "sleeve, and check again before approving.",
                    "Hold the cash. Cash is a position, and this project has "
                    "no evidence that the target shape beats holding it.",
                ],
                uncertainties=[
                    UNPROVEN_SHAPE_DISCLOSURE,
                    "Share quantity is rounded down to the granularity your "
                    "policy allows, so a sleeve lands slightly under its edge "
                    "rather than over it.",
                    "Requires allow_new_positions=true in your policy.",
                    "Market orders can fill away from the displayed price.",
                    "Policy limits are re-checked independently at approval "
                    "time; this proposal is not a promise that it will pass.",
                ],
            )
        )
    return {"created": True, "plan": plan, "proposals": proposals}
