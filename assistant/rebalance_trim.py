"""Tax-aware trims of overweight sleeves (REBAL-1 Stage 3).

**This is the first path in this app where a rebalancing SELL originates
from the app's own arithmetic.** Every other sell here is either a computed
policy breach (`assistant/proposals.py`) or the owner's explicit instruction
about a named holding (`assistant/user_directed_sell.py`). That difference is
why the milestone plan required separate authorization naming this stage
before it could be written, and why the module refuses in more places than it
proposes.

What the owner decides, and this module never does:

* **which sleeve** to trim;
* **which ticker** inside it;
* **how much**, bounded below by nothing and above by the amount that
  restores the target; and
* **which lot strategy** (FIFO, LIFO, HIFO, or named lots).

What the module computes and shows, because the spec requires the owner to
see the consequence before approving: the amount above the band, the amount
that restores the target, the individual tax lots with holding period, the
realized gain the chosen strategy would produce split into short- and
long-term, any sell already working, and the fractional remainder left
behind.

Three refusals worth naming, because each is a direction someone could
reasonably argue the other way:

1. **A sale larger than the target-restoration amount is refused.** Trimming
   past the target does not "get ahead"; it flips the sleeve underweight and
   hands the next Stage 2 pass a shortfall to buy back, paying spread and tax
   in both directions.
2. **An incomplete tax ledger refuses the trim entirely.** The spec requires
   showing realized-gain consequences. A trim proposal that silently omits
   them because the ledger cannot cover the position is precisely the
   pre-tax-looks-good trap this project has already been caught by, and the
   fix is to refuse rather than to show a partial number as if it were whole.
3. **A working sell already reduces the excess.** Sizing against the current
   weight while an unfilled sell is outstanding prepares a second trim for a
   gap the first is already closing -- the duplication HEDGER-004 found.

Nothing here approves or submits. The result is one `proposed` sell that
still requires the typed approval phrase, an independent execution-gate
pass, and the allocation-profile binding checked at execution time.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from assistant.money import decimal_or_none, decimal_text
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_analytics import preview_trade_impact
from assistant.portfolio_rebalance import (
    STATUS_OVERWEIGHT,
    RebalanceReport,
    evaluate_portfolio_rebalance,
)
from assistant.proposals import TradeProposal, attach_tax_lot_advisory
from assistant.rebalance_profile import (
    SLEEVE_CASH,
    SLEEVE_LABELS,
    SLEEVE_OTHER,
    AllocationProfile,
    sleeve_membership,
)
from assistant.schemas import DecisionPacket
from assistant.tax_lots import (
    SELECTION_METHODS,
    LotLedger,
    TaxLotError,
    is_long_term,
    open_lot_fingerprint,
    select_lots,
    unrealized_by_lot,
)
from risk.execution_gate import (
    TradeIntent,
    canonical_order_quantity,
    order_quantity_decimal,
)

EVIDENCE_STATUS = "user_directed_rebalance_trim"

#: Sleeves that can never be trimmed by this workflow. Cash is not a holding.
#: The residual is the set of positions the profile does not describe, so a
#: "trim" there would be the app selling something it has no target for --
#: the exact reading `Stage 1` forbids when it says absence from the profile
#: is never a reason to sell.
UNTRIMMABLE_SLEEVES = frozenset({SLEEVE_CASH, SLEEVE_OTHER})

UNPROVEN_SHAPE_DISCLOSURE = (
    "Sleeve targets and band width are your stated preference, not a "
    "research result. Selling to move toward them is not evidence-backed, "
    "and this project has confirmed no signal as real edge."
)

TAX_IS_REAL_DISCLOSURE = (
    "A trim realizes gains now in exchange for a portfolio shape this "
    "project has not shown to be better. Every rotation idea tested here "
    "that looked good before tax lost some or all of its edge after it."
)


@dataclasses.dataclass(frozen=True)
class TrimLot:
    """One open lot, and what selling from it would realize."""

    lot_id: str
    quantity: str
    cost_per_share: str
    acquired_at: str
    term_if_sold_now: str
    days_to_long_term: int
    quantity_taken: str
    realized_gain_exact: str


@dataclasses.dataclass(frozen=True)
class TrimPlan:
    """What a trim would do, before any proposal exists."""

    sleeve: str
    ticker: str
    profile_version: str
    profile_fingerprint: str
    excess_above_band_exact: str
    restoration_to_target_exact: str
    pending_sell_value_exact: str
    shares: int | str
    reference_price: object
    proceeds_exact: str
    remaining_shares_exact: str
    closes_position: bool
    lot_strategy: str
    lots: tuple[TrimLot, ...]
    realized_gain_exact: str
    realized_short_term_exact: str
    realized_long_term_exact: str
    disclosures: tuple[str, ...]
    refusals: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return not self.refusals


def overweight_sleeves(report: RebalanceReport) -> list[str]:
    """Sleeves above their upper band edge that may be trimmed.

    Reads `band_state`, not `status`, for the same reason Stage 2 does: a
    sleeve can be genuinely over its band while displaying another label.
    """
    return [
        row.sleeve
        for row in report.rows
        if row.sleeve not in UNTRIMMABLE_SLEEVES
        and row.band_state == STATUS_OVERWEIGHT
    ]


def untrimmable_overweight_sleeves(report: RebalanceReport) -> list[str]:
    """Sleeves above their upper band edge that this workflow never trims.

    `overweight_sleeves` filters on TWO independent conditions at once --
    above the band, and trimmable -- so an empty result cannot tell a reader
    which of them failed. Reporting that as "no sleeve is above its upper
    band" is false whenever cash or the residual is the sleeve that is over,
    and it contradicts the breach count on the same page. The two questions
    are separated here so the refusal can state the true reason.
    """
    return [
        row.sleeve
        for row in report.rows
        if row.sleeve in UNTRIMMABLE_SLEEVES
        and row.band_state == STATUS_OVERWEIGHT
    ]


def _row(report: RebalanceReport, sleeve: str):
    return next((r for r in report.rows if r.sleeve == sleeve), None)


def _band_amounts(
    report: RebalanceReport, profile: AllocationProfile, sleeve: str
) -> tuple[Decimal, Decimal] | None:
    """Exact dollars above the UPPER edge, and dollars back to TARGET.

    Both are computed from the profile's Decimal band and the row's exact
    values rather than from the display percentages, so an awkward
    denominator cannot introduce a binary artifact into a sell size
    (REBAL2CR-005 established this rule on the buy side).

    The projected value is used, so a sell already working counts against the
    excess instead of being trimmed for a second time.
    """
    row = _row(report, sleeve)
    equity = decimal_or_none(report.total_equity_exact)
    if row is None or equity is None or equity <= 0:
        return None
    market_value = decimal_or_none(row.market_value_exact)
    pending_value = decimal_or_none(row.pending_value_exact)
    if market_value is None or pending_value is None:
        return None
    projected_value = market_value + pending_value
    _, upper = profile.band_edges(sleeve)
    target = profile.target_decimal(sleeve)
    excess = projected_value - equity * upper / Decimal("100")
    restoration = projected_value - equity * target / Decimal("100")
    return (
        excess if excess > 0 else Decimal("0"),
        restoration if restoration > 0 else Decimal("0"),
    )


def _position(packet: DecisionPacket, ticker: str):
    return next(
        (p for p in packet.portfolio.positions if p.ticker.upper() == ticker),
        None,
    )


def _working_sell_value(
    packet: DecisionPacket, sleeve: str, membership: dict[str, str]
) -> Decimal:
    """Gross priced sell orders in this sleeve, always as a positive value.

    The rebalance report deliberately stores *signed net* pending exposure so
    projected weights conserve equity.  That is not the number this field
    promises the owner: a simultaneous buy must not hide or reverse a working
    sell.  A usable report has already refused every unpriced/invalid order,
    so this helper only has to preserve that same exact arithmetic.
    """
    total = Decimal("0")
    for order in packet.portfolio.open_orders or ():
        if not isinstance(order, dict):
            continue
        ticker = str(order.get("ticker") or "").strip().upper()
        if (
            str(order.get("side") or "").strip().lower() != "sell"
            or membership.get(ticker) != sleeve
        ):
            continue
        notional = order.get("notional")
        value = decimal_or_none(notional) if notional is not None else None
        if notional is None:
            quantity = decimal_or_none(order.get("qty") or order.get("shares"))
            price = decimal_or_none(order.get("limit_price"))
            if quantity is not None and price is not None:
                value = quantity * price
        if value is not None and value > 0:
            total += value
    return total


def plan_trim(
    packet: DecisionPacket,
    profile: AllocationProfile,
    policy: TradingPolicy,
    *,
    sleeve: str,
    ticker: object,
    shares: object,
    lot_strategy: str,
    lot_ids: list[str] | None = None,
    tax_lot_ledger: LotLedger | None,
    tax_lot_coverage: dict | None = None,
    now: datetime | None = None,
) -> TrimPlan:
    """Everything the owner must see before approving a trim. Proposes nothing."""
    report = evaluate_portfolio_rebalance(packet.portfolio, profile, policy=policy)
    refusals: list[str] = list(report.refusals)
    disclosures = [UNPROVEN_SHAPE_DISCLOSURE, TAX_IS_REAL_DISCLOSURE]

    name = str(ticker).strip().upper() if ticker is not None else ""
    label = SLEEVE_LABELS.get(sleeve, sleeve)

    def _empty(extra: list[str]) -> TrimPlan:
        return TrimPlan(
            sleeve=sleeve, ticker=name,
            profile_version=report.profile_version,
            profile_fingerprint=report.profile_fingerprint,
            excess_above_band_exact="0", restoration_to_target_exact="0",
            pending_sell_value_exact="0", shares=0, reference_price=Decimal("0"),
            proceeds_exact="0", remaining_shares_exact="0", closes_position=False,
            lot_strategy=str(lot_strategy), lots=(), realized_gain_exact="0",
            realized_short_term_exact="0", realized_long_term_exact="0",
            disclosures=tuple(disclosures),
            refusals=tuple(refusals + extra),
        )

    if sleeve in UNTRIMMABLE_SLEEVES:
        return _empty([
            f"{label} is not a trimmable sleeve. Cash is not a holding, and "
            "the residual is the set of positions your profile does not "
            "describe -- absence from the profile is never a reason to sell."
        ])
    if report.usable and sleeve not in overweight_sleeves(report):
        return _empty([
            f"{label} is not above its upper band, so there is nothing to "
            "trim. This workflow never sells a sleeve that is inside or "
            "below its band."
        ])
    if not name:
        return _empty(["A ticker is required; this app does not choose one."])
    try:
        membership = sleeve_membership()
    except Exception as exc:
        return _empty([str(exc)])
    if membership.get(name) != sleeve:
        return _empty([
            f"{name} is not a configured member of {label}, so selling it "
            "would not reduce that sleeve."
        ])
    if str(lot_strategy) not in SELECTION_METHODS:
        return _empty([
            f"Lot strategy must be one of {', '.join(SELECTION_METHODS)}, "
            f"got {lot_strategy!r}."
        ])

    amounts = _band_amounts(report, profile, sleeve) if report.usable else None
    if amounts is None:
        return _empty([
            f"{label}'s band amounts could not be computed from this snapshot."
        ])
    excess, restoration = amounts

    position = _position(packet, name)
    if position is None:
        return _empty([f"{name} is not currently held, so it cannot be trimmed."])
    price = decimal_or_none(
        position.current_price_exact
        if position.current_price_exact is not None
        else position.current_price
    )
    held = decimal_or_none(
        position.shares_exact
        if position.shares_exact is not None
        else position.shares
    )
    if price is None or price <= 0 or held is None or held <= 0:
        return _empty([
            f"{name} has no usable exact price or quantity, so a trim cannot "
            "be sized or priced."
        ])

    canonical = canonical_order_quantity(
        shares, whole_shares_only=policy.whole_shares_only
    )
    if canonical is None:
        return _empty([
            "Shares to sell must be "
            + (
                "a whole number greater than zero"
                if policy.whole_shares_only
                else "a positive exact number with at most 9 decimal places"
            )
            + f", got {shares!r}."
        ])
    quantity = order_quantity_decimal(
        canonical, whole_shares_only=policy.whole_shares_only
    )
    if quantity > held:
        return _empty([
            f"You hold {decimal_text(held)} share(s) of {name}; selling "
            f"{canonical} would short the position, which this app never does."
        ])

    proceeds = quantity * price
    if proceeds > restoration:
        return _empty([
            f"Selling {canonical} share(s) raises "
            f"${float(proceeds):,.2f}, more than the "
            f"${float(restoration):,.2f} that restores {label} to its target. "
            "Trimming past the target does not get ahead -- it flips the "
            "sleeve underweight and hands the next steering pass a shortfall "
            "to buy back, paying spread and tax in both directions."
        ])

    # Realized-gain consequences are REQUIRED by this stage, so an incomplete
    # ledger refuses rather than proposing a sale whose tax effect is unknown.
    #
    # ST3CCR-001: scoped to the TRIMMED ticker, not the whole book. This sale
    # realizes gains from one ticker's lots and nothing else, so that
    # ticker's `matched` flag is exactly the necessary and sufficient
    # condition. Requiring the global flag meant one pre-app or
    # bought-outside-the-app holding anywhere in the portfolio refused every
    # trim forever -- and `list_fills()` documents that such holdings
    # "produce no events and therefore no lots", so that is the normal case
    # rather than an edge one. A refusal that always fires is
    # indistinguishable from a careful safeguard, which is the same way
    # ST3R-001 hid.
    coverage = tax_lot_coverage or {}
    ticker_coverage = (coverage.get("tickers", {}) or {}).get(name, {})
    # `ticker_tax_ledger_with_coverage` scopes `complete` to this ticker;
    # `matched` is still honoured so a portfolio-wide coverage dict works too.
    covered = (
        coverage.get("complete") is True
        or ticker_coverage.get("matched") is True
    )
    if tax_lot_ledger is None or not covered:
        reason = (
            (coverage.get("tickers", {}) or {}).get(name, {}).get("reason")
            or coverage.get("reason")
            or "the app has no confirmed fill history for this position"
        )
        return _empty([
            f"Tax lots for {name} are incomplete ({reason}), so the realized "
            "gain this sale would trigger cannot be shown. This workflow "
            "refuses rather than proposing a trim whose tax effect is unknown."
        ])

    try:
        open_lots = tax_lot_ledger.open_for(name)
        chosen = select_lots(
            open_lots, float(quantity),
            method=str(lot_strategy), lot_ids=lot_ids,
        )
    except TaxLotError as exc:
        return _empty([f"Lot selection refused for {name}: {exc}"])

    sold_at = now or datetime.now(timezone.utc)
    lots: list[TrimLot] = []
    realized = Decimal("0")
    short_term = Decimal("0")
    long_term = Decimal("0")
    detail_by_id = {
        d["lot_id"]: d
        for d in unrealized_by_lot(
            tax_lot_ledger, name, float(price), now=sold_at
        )
    }
    for lot, taken in chosen:
        taken_decimal = decimal_or_none(str(taken)) or Decimal("0")
        basis = decimal_or_none(str(lot.cost_per_share)) or Decimal("0")
        gain = (price - basis) * taken_decimal
        realized += gain
        if is_long_term(lot.acquired_at, sold_at):
            long_term += gain
        else:
            short_term += gain
        detail = detail_by_id.get(lot.lot_id, {})
        lots.append(
            TrimLot(
                lot_id=lot.lot_id,
                quantity=decimal_text(decimal_or_none(str(lot.qty)) or Decimal("0")),
                cost_per_share=decimal_text(basis),
                acquired_at=lot.acquired_at.isoformat(),
                term_if_sold_now=str(detail.get("term_if_sold_now", "")),
                days_to_long_term=int(detail.get("days_to_long_term", 0) or 0),
                quantity_taken=decimal_text(taken_decimal),
                realized_gain_exact=decimal_text(gain),
            )
        )

    if coverage.get("portfolio_complete") is False:
        # Stated rather than enforced: the rest of the book being uncovered
        # says nothing about THIS sale's tax consequence, but the owner
        # should know the ledger is not a complete account history.
        disclosures.append(
            "Other holdings have no app fill history, so this ledger is not a "
            f"complete account history -- but {name}'s own lots are complete, "
            "which is what this sale's realized gain depends on."
        )
    if short_term > 0:
        disclosures.append(
            f"${float(short_term):,.2f} of this gain is SHORT-TERM and taxed "
            "at your ordinary income rate. `config` already encodes the "
            "opposite preference elsewhere: the growth sleeve's scheduled "
            "trim fires only once a lot is long-term, so a scheduled sale "
            "can never realize a short-term gain."
        )

    remaining = held - quantity
    if remaining > 0 and remaining < 1:
        disclosures.append(
            f"{decimal_text(remaining)} share(s) of {name} remain after this "
            "sale -- less than one whole share. Under a whole-shares-only "
            "policy that remainder cannot be sold later without turning "
            "fractional orders on."
        )

    pending = _working_sell_value(packet, sleeve, membership)
    return TrimPlan(
        sleeve=sleeve, ticker=name,
        profile_version=report.profile_version,
        profile_fingerprint=report.profile_fingerprint,
        excess_above_band_exact=decimal_text(excess),
        restoration_to_target_exact=decimal_text(restoration),
        pending_sell_value_exact=decimal_text(pending),
        shares=canonical, reference_price=price,
        proceeds_exact=decimal_text(proceeds),
        remaining_shares_exact=decimal_text(remaining),
        closes_position=remaining == 0,
        lot_strategy=str(lot_strategy), lots=tuple(lots),
        realized_gain_exact=decimal_text(realized),
        realized_short_term_exact=decimal_text(short_term),
        realized_long_term_exact=decimal_text(long_term),
        disclosures=tuple(disclosures), refusals=(),
    )


def _stable_id(
    packet: DecisionPacket, policy: TradingPolicy, intent: TradeIntent, salt: str
) -> str:
    raw = (
        f"{EVIDENCE_STATUS}|{packet.generated_at}|{policy.version}|"
        f"{intent.ticker.upper()}|{intent.side}|{intent.shares}|{salt}"
    )
    return "tp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def generate_trim_proposal(
    packet: DecisionPacket,
    profile: AllocationProfile,
    policy: TradingPolicy,
    *,
    sleeve: str,
    ticker: object,
    shares: object,
    lot_strategy: str,
    lot_ids: list[str] | None = None,
    tax_lot_ledger: LotLedger | None,
    tax_lot_coverage: dict | None = None,
    ttl_minutes: int = 15,
    now: datetime | None = None,
) -> dict:
    """One APPROVE-gated sell that trims an overweight sleeve."""
    at = now or datetime.now(timezone.utc)
    plan = plan_trim(
        packet, profile, policy,
        sleeve=sleeve, ticker=ticker, shares=shares,
        lot_strategy=lot_strategy, lot_ids=lot_ids,
        tax_lot_ledger=tax_lot_ledger, tax_lot_coverage=tax_lot_coverage,
        now=at,
    )
    if not plan.usable:
        return {"created": False, "plan": plan, "reason": " ".join(plan.refusals)}

    price = plan.reference_price
    intent = TradeIntent(
        ticker=plan.ticker, side="sell", shares=plan.shares,
        order_type="market",
        rationale=(
            f"Rebalance trim: {SLEEVE_LABELS.get(sleeve, sleeve)} is "
            f"${float(plan.excess_above_band_exact):,.2f} above its upper "
            f"band; selling {plan.shares} share(s) of {plan.ticker} at "
            f"~${float(price):,.2f}"
            + (" closes the whole position." if plan.closes_position else ".")
        ),
    )
    expected_impact = preview_trade_impact(
        packet.portfolio, plan.ticker, "sell", plan.shares, float(price)
    )
    uncertainties = [
        UNPROVEN_SHAPE_DISCLOSURE,
        TAX_IS_REAL_DISCLOSURE,
        "Market orders can fill away from the displayed reference price, so "
        "the realized gain shown here is an estimate, not a settlement.",
        "Lot selection is advisory to your broker: this app records which "
        "lots the strategy would consume; it does not instruct the broker "
        "to use them.",
        "Policy limits are re-checked independently at approval time.",
    ]
    attach_tax_lot_advisory(
        expected_impact, uncertainties,
        ticker=plan.ticker, shares=float(
            order_quantity_decimal(
                plan.shares, whole_shares_only=policy.whole_shares_only
            )
        ),
        price=float(price), when=at,
        tax_lot_ledger=tax_lot_ledger, tax_lot_coverage=tax_lot_coverage,
    )
    durable_lots = [dataclasses.asdict(lot) for lot in plan.lots]
    expected_impact.update({
        "allocation_profile_version": plan.profile_version,
        "allocation_profile_fingerprint": plan.profile_fingerprint,
        "rebalance_realized_gain_exact": plan.realized_gain_exact,
        "rebalance_realized_short_term_exact": plan.realized_short_term_exact,
        "rebalance_lot_strategy": plan.lot_strategy,
        "rebalance_lots": durable_lots,
        "rebalance_tax_lot_fingerprint": open_lot_fingerprint(
            tax_lot_ledger, plan.ticker
        ),
    })

    reasons = [
        f"{SLEEVE_LABELS.get(sleeve, sleeve)} is "
        f"${float(plan.excess_above_band_exact):,.2f} above its upper band; "
        f"${float(plan.restoration_to_target_exact):,.2f} would restore its "
        "target.",
        f"You chose {plan.ticker}, {plan.shares} share(s), and the "
        f"{plan.lot_strategy.upper()} lot strategy. This app selects none of "
        "those.",
        f"Estimated realized gain ${float(plan.realized_gain_exact):,.2f}, of "
        f"which ${float(plan.realized_short_term_exact):,.2f} is short-term.",
    ]
    if plan.closes_position:
        reasons.append(f"This closes the entire {plan.ticker} position.")

    tax_decision = json.dumps(
        {
            "lots": durable_lots,
            "gain": plan.realized_gain_exact,
            "short": plan.realized_short_term_exact,
            "long": plan.realized_long_term_exact,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    proposal_id = _stable_id(
        packet, policy, intent,
        salt=(
            f"{plan.profile_fingerprint}|{plan.lot_strategy}|"
            f"{hashlib.sha256(tax_decision.encode('utf-8')).hexdigest()}"
        ),
    )
    return {
        "created": True,
        "plan": plan,
        "proposal": TradeProposal(
            proposal_id=proposal_id,
            created_at=at.isoformat(),
            expires_at=(at + timedelta(minutes=ttl_minutes)).isoformat(),
            status="proposed",
            idempotency_key=f"{proposal_id}-{packet.portfolio.as_of}",
            policy_version=policy.version,
            policy_fingerprint=compute_policy_fingerprint(policy),
            intent=intent,
            reference_price=float(price),
            price_timestamp=at.isoformat(),
            reasons=reasons,
            evidence_status=EVIDENCE_STATUS,
            expected_impact=expected_impact,
            alternatives=[
                "Take no action -- nothing is sold until you type the "
                "approval phrase.",
                "Trim less, or choose a lot strategy that realizes less gain "
                "(HIFO minimizes it).",
                "Let the sleeve run. A band exists so that being inside it is "
                "enough, and nothing here shows that being at target beats "
                "being over it.",
            ],
            uncertainties=uncertainties,
        ),
    }
