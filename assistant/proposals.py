"""Deterministic, typed trade proposals derived from portfolio policy breaches."""
from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR

from assistant.money import (
    decimal_or_none,
    exact_decimal_add,
    exact_decimal_multiply,
    exact_decimal_subtract,
    exact_decimal_sum,
    to_decimal,
)
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_analytics import preview_trade_impact
from assistant.schemas import DecisionPacket, PortfolioPosition
from assistant.tax_lots import LotLedger, TaxLotError, compare_sale_bases
from config import BASKETS
from risk.execution_gate import TradeIntent


@dataclasses.dataclass
class TradeProposal:
    proposal_id: str
    created_at: str
    expires_at: str
    status: str
    idempotency_key: str
    policy_version: str
    policy_fingerprint: str
    intent: TradeIntent
    reference_price: float
    price_timestamp: str
    reasons: list[str]
    evidence_status: str
    expected_impact: dict
    alternatives: list[str]
    uncertainties: list[str]

    def to_dict(self) -> dict:
        result = dataclasses.asdict(self)
        return result


def sellable_whole_shares(position_shares: object) -> int:
    """Whole shares of a held position that may be sold, floored EXACTLY.

    The single authority for "how many whole shares does this position
    actually have", used by every sell-proposal generator and re-exported by
    assistant/user_directed_sell.py.

    Exactness is the point, not a nicety. A broker holding of
    `10.999999999999999999` becomes `11.0` as a float, so `int(shares)`
    yields 11 -- one more share than exists. Independent review (SELREV-001,
    2026-08-13) found that this authorized an oversell end to end; the
    execution gate now compares exact decimals and refuses it. Consolidated
    here (SELCR-001) because the gate refusing is only half the fix: a
    generator that keeps proposing 11 turns a correct refusal into a
    RISK-REDUCING SELL THAT CAN NEVER BE APPROVED, leaving a position stuck
    over its cap. Prefer `PortfolioPosition.shares_exact` at every call site;
    the float field is a display value.

    Non-finite, non-positive, and unconvertible quantities yield 0 so one
    corrupt row refuses its own ticker instead of breaking the batch.
    """
    shares = decimal_or_none(position_shares)
    if shares is None or shares <= 0:
        return 0
    return int(shares.to_integral_value(rounding=ROUND_FLOOR))


def exact_position_shares(position: PortfolioPosition) -> object:
    """The exact broker quantity when present, else the display float."""
    return position.shares_exact if position.shares_exact is not None else position.shares


def _whole_units_not_exceeding(value: object, unit_price: object) -> int:
    """Floor ``value / unit_price`` exactly, independent of Decimal context."""
    amount = to_decimal(value, name="dollar value")
    price = to_decimal(unit_price, name="unit price")
    if amount <= 0 or price <= 0:
        return 0
    # Decimal.as_integer_ratio() is exact.  Integer cross-products and floor
    # division therefore cannot round a just-over-cap notional down onto the
    # authorization boundary, even if a caller lowered Decimal precision.
    amount_numerator, amount_denominator = amount.as_integer_ratio()
    price_numerator, price_denominator = price.as_integer_ratio()
    return (
        amount_numerator * price_denominator
        // (amount_denominator * price_numerator)
    )


def attach_tax_lot_advisory(
    expected_impact: dict,
    uncertainties: list[str],
    *,
    ticker: str,
    shares: int,
    price: float,
    when: datetime,
    tax_lot_ledger: LotLedger | None,
    tax_lot_coverage: dict | None = None,
) -> None:
    """Attach the advisory FIFO/LIFO/HIFO comparison for one sell, or an
    explicit unavailability reason, mutating `expected_impact` and
    `uncertainties` in place.

    Extracted so the policy-breach generator below and the user-directed
    sell generator (assistant/user_directed_sell.py) cannot drift: this is
    the tax-consequence disclosure rule, and a second hand-copied version
    is exactly how a disclosure quietly stops matching on one surface.

    Advisory only, in both directions. It never gates, sizes, or delays a
    sell -- an unavailable advisory must still leave the sell possible,
    because a risk-reducing order must never wait on bookkeeping.
    """
    if tax_lot_ledger is not None:
        try:
            tax_advisory = compare_sale_bases(
                tax_lot_ledger, ticker, qty=shares, price=price, when=when
            )
            # Do NOT force available=True here. compare_sale_bases() sets
            # it from whether any method actually produced figures; a
            # ticker the lot ledger has never seen (there is still no
            # importer for fills predating this app) errors on every
            # method, and stamping it available made the CLI print nothing
            # at all -- skipping the "advisory unavailable" branch, so
            # missing lot history looked exactly like "no tax implications"
            # (found 2026-07-30 reviewing this feature).
            tax_advisory.setdefault("available", False)
            tax_advisory["advisory_only"] = True
            expected_impact["tax_lot_advisory"] = tax_advisory
            if tax_advisory["available"]:
                uncertainties.append(
                    "Tax-lot figures are advisory bookkeeping, never an "
                    "execution gate; broker records and Form 1099-B remain "
                    "authoritative."
                )
            else:
                uncertainties.append(
                    "Tax-lot advice is unavailable for this sale "
                    f"({tax_advisory.get('reason', 'unknown reason')}); "
                    "that never delays a risk-reducing order."
                )
        except TaxLotError as exc:
            expected_impact["tax_lot_advisory"] = {
                "available": False,
                "reason": str(exc),
                "advisory_only": True,
            }
            uncertainties.append(
                "Tax-lot advice is unavailable for this sale, but that "
                "must never delay a risk-reducing order."
            )
    else:
        reason = (
            (tax_lot_coverage or {}).get("reason")
            or "complete lot history is unavailable"
        )
        expected_impact["tax_lot_advisory"] = {
            "available": False,
            "reason": reason,
            "coverage": tax_lot_coverage or {},
            "advisory_only": True,
        }
        uncertainties.append(
            "Tax-lot advice is unavailable because complete lot coverage "
            "could not be verified; this never blocks a risk-reducing sell."
        )


def _stable_id(packet: DecisionPacket, policy: TradingPolicy, intent: TradeIntent) -> str:
    # packet.generated_at (a full timestamp, not just portfolio.as_of's
    # date) so a regenerated proposal for the SAME intent later the same
    # day gets a NEW id instead of colliding with an old, possibly-expired
    # row -- save_proposal()'s ON CONFLICT DO NOTHING previously made a
    # same-day regeneration a silent no-op against the stale row.
    raw = (
        f"{packet.generated_at}|{policy.version}|{intent.ticker.upper()}|"
        f"{intent.side}|{intent.shares}|{intent.order_type}|{intent.limit_price}"
    )
    return "tp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _add_reduction(
    reductions: dict[str, dict],
    position: PortfolioPosition,
    dollar_reduction: Decimal,
    reason: str,
) -> None:
    # The caller validates the complete snapshot first, and all sizing below
    # stays on its exact Decimal companions. A non-positive row is still
    # isolated here so one unusable position cannot abort the batch.
    current_price = position.exact_field("current_price")
    if dollar_reduction <= 0 or current_price <= 0:
        return
    # SELCR-001: floor the HELD side exactly. `int(position.shares)` rounded a
    # fractional broker quantity up, and the hardened gate then refused the
    # resulting proposal -- blocking the very risk reduction this function
    # exists to produce.
    shares = min(
        sellable_whole_shares(exact_position_shares(position)),
        max(1, _whole_units_not_exceeding(dollar_reduction, current_price)),
    )
    entry = reductions.setdefault(
        position.ticker,
        {"position": position, "shares": 0, "reasons": []},
    )
    entry["shares"] = max(entry["shares"], shares)
    if reason not in entry["reasons"]:
        entry["reasons"].append(reason)


def generate_risk_reduction_proposals(
    packet: DecisionPacket,
    policy: TradingPolicy,
    ttl_minutes: int = 15,
    *,
    tax_lot_ledger: LotLedger | None = None,
    tax_lot_coverage: dict | None = None,
) -> list[TradeProposal]:
    """
    Generate only exposure-reducing proposals.

    No rejected or exploratory alpha signal can create a buy proposal. The
    current milestone deliberately limits automation to deterministic risk
    policy breaches.

    The max_position_value/leveraged_excess checks below are a SIMPLER,
    PROPOSAL-GENERATION-ONLY concentration check -- they decide what to
    *suggest*, not what to *permit*. They are NOT gated through
    risk/execution_gate.py's validate_trade_intent() (which decides what
    to *permit* at submission time and is the real risk governor -- see
    that module's "Known scatter points" note and
    docs/architecture/ARCHITECTURE_DEBT.md). By design: any proposal generated here
    still passes through the real gate before it can ever execute, so this
    duplication can under- or over-suggest relative to what the gate would
    actually allow without being unsafe -- but it is a second source of
    concentration-limit logic worth knowing about.
    """
    snapshot = packet.portfolio
    from assistant.portfolio_snapshot import (
        PortfolioSnapshotIntegrityError,
        validate_long_only_portfolio_snapshot,
    )

    try:
        validate_long_only_portfolio_snapshot(snapshot)
    except PortfolioSnapshotIntegrityError:
        return []
    total_equity = snapshot.total_equity_exact_decimal
    # The canonical validator above rejects non-finite and inconsistent
    # evidence before any comparison. Exact totals then drive every limit.
    if total_equity <= 0:
        return []

    reductions: dict[str, dict] = {}
    position_by_ticker = {p.ticker.upper(): p for p in snapshot.positions}
    max_position_value = exact_decimal_multiply(
        total_equity,
        to_decimal(
            policy.max_position_pct,
            name="policy.max_position_pct",
        ),
        name="maximum position value",
    )
    for position in snapshot.positions:
        market_value = position.exact_field("market_value")
        if market_value > max_position_value:
            _add_reduction(
                reductions,
                position,
                exact_decimal_subtract(
                    market_value,
                    max_position_value,
                    name=f"{position.ticker} position excess",
                ),
                f"Position exceeds the {policy.max_position_pct * 100:.1f}% policy limit.",
            )

    leveraged = sorted(
        (p for p in snapshot.positions if p.is_leveraged_etf),
        key=lambda p: p.exact_field("market_value"),
        reverse=True,
    )
    leveraged_excess = exact_decimal_subtract(
        exact_decimal_sum(
            (p.exact_field("market_value") for p in leveraged),
            name="leveraged ETF value",
        ),
        exact_decimal_multiply(
            total_equity,
            to_decimal(
                policy.max_leveraged_etf_pct,
                name="policy.max_leveraged_etf_pct",
            ),
            name="maximum leveraged ETF value",
        ),
        name="leveraged ETF excess",
    )
    for position in leveraged:
        if leveraged_excess <= 0:
            break
        reduction = min(position.exact_field("market_value"), leveraged_excess)
        _add_reduction(
            reductions,
            position,
            reduction,
            f"Leveraged-ETF exposure exceeds the {policy.max_leveraged_etf_pct * 100:.1f}% policy limit.",
        )
        leveraged_excess = exact_decimal_subtract(
            leveraged_excess,
            reduction,
            name="remaining leveraged ETF excess",
        )

    # Iterates config.BASKETS directly and computes each basket's EXACT
    # market value here, rather than reading packet.risk.basket_exposure_pct
    # (a value ALREADY rounded to 1 decimal place by build_risk_exposure()
    # for display purposes) -- a true exposure just above the boundary
    # (e.g. 40.04%) could round down to exactly the limit (40.0%) and
    # silently evade proposal generation entirely (GPT review, 2026-07-31).
    max_basket_value = exact_decimal_multiply(
        total_equity,
        to_decimal(
            policy.max_basket_pct,
            name="policy.max_basket_pct",
        ),
        name="maximum basket value",
    )
    for basket_name, basket_tickers in BASKETS.items():
        basket_value = exact_decimal_sum(
            (
                p.exact_field("market_value")
                for p in snapshot.positions
                if p.ticker.upper() in basket_tickers
            ),
            name=f"{basket_name} basket value",
        )
        if basket_value <= max_basket_value:
            continue
        basket_positions = sorted(
            (position_by_ticker[t] for t in basket_tickers if t in position_by_ticker),
            key=lambda p: p.exact_field("market_value"),
            reverse=True,
        )
        if not basket_positions:
            continue
        excess = exact_decimal_subtract(
            basket_value,
            max_basket_value,
            name=f"{basket_name} basket excess",
        )
        _add_reduction(
            reductions,
            basket_positions[0],
            excess,
            f"'{basket_name}' exposure exceeds the {policy.max_basket_pct * 100:.1f}% policy limit.",
        )

    # Total-exposure remediation: policy.max_total_exposure_pct applies
    # across the WHOLE portfolio, unlike the per-position/basket/
    # leveraged checks above, and previously had NO remediation at all --
    # a diversified portfolio could be well over this cap with every
    # individual position, basket, and leveraged-ETF check passing, and
    # this generator would silently propose nothing even though the
    # execution gate's own MAX_TOTAL_EXPOSURE_PCT check exists specifically
    # to block further buys in exactly this situation (GPT review,
    # 2026-07-31, independently reproduced with a diversified 90%-invested
    # portfolio against a 50% total-exposure cap).
    #
    # `_add_reduction()` merges reductions per ticker by taking the MAX of
    # every reason's requested share count (selling once satisfies however
    # many reasons wanted at least that much) -- so to correctly determine
    # how much MORE reduction is needed here (on top of whatever position/
    # leveraged/basket checks already planned for each ticker), this
    # computes each ticker's absolute planned-dollars-so-far, adds the
    # incremental amount needed to close the remaining gap, and passes
    # that new (larger) ABSOLUTE target back through _add_reduction() --
    # never just the marginal amount, which _add_reduction()'s max-merge
    # would otherwise silently ignore in favor of a larger existing plan.
    def _planned_dollars(ticker: str) -> Decimal:
        entry = reductions.get(ticker)
        if entry is None:
            return Decimal("0")
        return exact_decimal_multiply(
            entry["shares"],
            entry["position"].exact_field("current_price"),
            name=f"planned {ticker} reduction value",
        )

    invested_value = exact_decimal_sum(
        (p.exact_field("market_value") for p in snapshot.positions),
        name="invested portfolio value",
    )
    max_total_exposure_value = exact_decimal_multiply(
        total_equity,
        to_decimal(
            policy.max_total_exposure_pct,
            name="policy.max_total_exposure_pct",
        ),
        name="maximum total exposure value",
    )
    already_closed = exact_decimal_sum(
        (_planned_dollars(p.ticker) for p in snapshot.positions),
        name="already planned reduction value",
    )
    remaining_gap = exact_decimal_subtract(
        exact_decimal_subtract(
            invested_value,
            max_total_exposure_value,
            name="total exposure excess",
        ),
        already_closed,
        name="remaining total exposure excess",
    )
    if remaining_gap > 0:
        for position in sorted(
            snapshot.positions,
            key=lambda p: exact_decimal_subtract(
                p.exact_field("market_value"),
                _planned_dollars(p.ticker),
                name=f"remaining {p.ticker} position value",
            ),
            reverse=True,
        ):
            if remaining_gap <= 0:
                break
            planned_so_far = _planned_dollars(position.ticker)
            remaining_value = exact_decimal_subtract(
                position.exact_field("market_value"),
                planned_so_far,
                name=f"remaining {position.ticker} position value",
            )
            if (
                remaining_value <= 0
                or position.exact_field("current_price") <= 0
            ):
                continue
            incremental = min(remaining_value, remaining_gap)
            _add_reduction(
                reductions,
                position,
                exact_decimal_add(
                    planned_so_far,
                    incremental,
                    name=f"planned {position.ticker} reduction target",
                ),
                f"Total invested exposure exceeds the {policy.max_total_exposure_pct * 100:.1f}% policy limit.",
            )
            remaining_gap = exact_decimal_subtract(
                remaining_gap,
                incremental,
                name="remaining total exposure gap",
            )

    now = datetime.now(timezone.utc)
    proposals = []
    for ticker, reduction in sorted(reductions.items()):
        position = reduction["position"]
        max_order_value = to_decimal(
            policy.max_order_value,
            name="policy.max_order_value",
        )
        max_order_shares = _whole_units_not_exceeding(
            max_order_value,
            position.exact_field("current_price"),
        )
        if max_order_shares <= 0:
            continue
        shares = min(reduction["shares"], max_order_shares)
        if shares <= 0:
            continue
        try:
            proposal_value = exact_decimal_multiply(
                shares,
                position.exact_field("current_price"),
                name=f"{ticker} proposal value",
            )
        except ValueError:
            continue
        if proposal_value > max_order_value:
            # This postcondition is deliberately redundant with exact integer
            # floor sizing. It is the last fail-closed guard before emitting
            # an actionable proposal artifact.
            continue
        intent = TradeIntent(
            ticker=ticker,
            side="sell",
            shares=shares,
            order_type="market",
            rationale=" ".join(reduction["reasons"]),
        )
        proposal_id = _stable_id(packet, policy, intent)
        expected_impact = preview_trade_impact(
            snapshot, ticker, "sell", shares, position.current_price
        )
        uncertainties = [
            "Market orders can fill away from the displayed reference price.",
        ]
        attach_tax_lot_advisory(
            expected_impact,
            uncertainties,
            ticker=ticker,
            shares=shares,
            price=position.current_price,
            when=now,
            tax_lot_ledger=tax_lot_ledger,
            tax_lot_coverage=tax_lot_coverage,
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
                reference_price=position.current_price,
                price_timestamp=now.isoformat(),
                reasons=reduction["reasons"],
                evidence_status="deterministic_risk_policy",
                expected_impact=expected_impact,
                alternatives=[
                    "Take no action and explicitly accept the policy breach.",
                    "Reduce a different position contributing to the same exposure.",
                    "Update the versioned policy before generating a new proposal.",
                ],
                uncertainties=uncertainties,
            )
        )
    return proposals
