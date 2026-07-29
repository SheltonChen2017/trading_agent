"""Deterministic, typed trade proposals derived from portfolio policy breaches."""
from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime, timedelta, timezone

from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_analytics import preview_trade_impact
from assistant.schemas import DecisionPacket, PortfolioPosition
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
    dollar_reduction: float,
    reason: str,
) -> None:
    if dollar_reduction <= 0 or position.current_price <= 0:
        return
    shares = min(int(position.shares), max(1, int(dollar_reduction / position.current_price)))
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
    docs/ARCHITECTURE_DEBT.md). By design: any proposal generated here
    still passes through the real gate before it can ever execute, so this
    duplication can under- or over-suggest relative to what the gate would
    actually allow without being unsafe -- but it is a second source of
    concentration-limit logic worth knowing about.
    """
    snapshot = packet.portfolio
    if snapshot.total_equity <= 0:
        return []

    reductions: dict[str, dict] = {}
    position_by_ticker = {p.ticker.upper(): p for p in snapshot.positions}
    max_position_value = snapshot.total_equity * policy.max_position_pct
    for position in snapshot.positions:
        if position.market_value > max_position_value:
            _add_reduction(
                reductions,
                position,
                position.market_value - max_position_value,
                f"Position exceeds the {policy.max_position_pct * 100:.1f}% policy limit.",
            )

    leveraged = sorted(
        (p for p in snapshot.positions if p.is_leveraged_etf),
        key=lambda p: p.market_value,
        reverse=True,
    )
    leveraged_excess = (
        sum(p.market_value for p in leveraged)
        - snapshot.total_equity * policy.max_leveraged_etf_pct
    )
    for position in leveraged:
        if leveraged_excess <= 0:
            break
        reduction = min(position.market_value, leveraged_excess)
        _add_reduction(
            reductions,
            position,
            reduction,
            f"Leveraged-ETF exposure exceeds the {policy.max_leveraged_etf_pct * 100:.1f}% policy limit.",
        )
        leveraged_excess -= reduction

    # Iterates config.BASKETS directly and computes each basket's EXACT
    # market value here, rather than reading packet.risk.basket_exposure_pct
    # (a value ALREADY rounded to 1 decimal place by build_risk_exposure()
    # for display purposes) -- a true exposure just above the boundary
    # (e.g. 40.04%) could round down to exactly the limit (40.0%) and
    # silently evade proposal generation entirely (GPT review, 2026-07-31).
    max_basket_value = snapshot.total_equity * policy.max_basket_pct
    for basket_name, basket_tickers in BASKETS.items():
        basket_value = sum(p.market_value for p in snapshot.positions if p.ticker.upper() in basket_tickers)
        if basket_value <= max_basket_value:
            continue
        basket_positions = sorted(
            (position_by_ticker[t] for t in basket_tickers if t in position_by_ticker),
            key=lambda p: p.market_value,
            reverse=True,
        )
        if not basket_positions:
            continue
        excess = basket_value - max_basket_value
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
    def _planned_dollars(ticker: str) -> float:
        entry = reductions.get(ticker)
        if entry is None:
            return 0.0
        return entry["shares"] * entry["position"].current_price

    invested_value = sum(p.market_value for p in snapshot.positions)
    max_total_exposure_value = snapshot.total_equity * policy.max_total_exposure_pct
    already_closed = sum(_planned_dollars(p.ticker) for p in snapshot.positions)
    remaining_gap = (invested_value - max_total_exposure_value) - already_closed
    if remaining_gap > 0:
        for position in sorted(
            snapshot.positions,
            key=lambda p: p.market_value - _planned_dollars(p.ticker),
            reverse=True,
        ):
            if remaining_gap <= 0:
                break
            planned_so_far = _planned_dollars(position.ticker)
            remaining_value = position.market_value - planned_so_far
            if remaining_value <= 0 or position.current_price <= 0:
                continue
            incremental = min(remaining_value, remaining_gap)
            _add_reduction(
                reductions,
                position,
                planned_so_far + incremental,
                f"Total invested exposure exceeds the {policy.max_total_exposure_pct * 100:.1f}% policy limit.",
            )
            remaining_gap -= incremental

    now = datetime.now(timezone.utc)
    proposals = []
    for ticker, reduction in sorted(reductions.items()):
        position = reduction["position"]
        max_order_shares = int(policy.max_order_value / position.current_price)
        if max_order_shares <= 0:
            continue
        shares = min(reduction["shares"], max_order_shares)
        if shares <= 0:
            continue
        intent = TradeIntent(
            ticker=ticker,
            side="sell",
            shares=shares,
            order_type="market",
            rationale=" ".join(reduction["reasons"]),
        )
        proposal_id = _stable_id(packet, policy, intent)
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
                expected_impact=preview_trade_impact(
                    snapshot, ticker, "sell", shares, position.current_price
                ),
                alternatives=[
                    "Take no action and explicitly accept the policy breach.",
                    "Reduce a different position contributing to the same exposure.",
                    "Update the versioned policy before generating a new proposal.",
                ],
                uncertainties=[
                    "Market orders can fill away from the displayed reference price.",
                    "Tax-lot and realized-tax optimization are not yet integrated.",
                ],
            )
        )
    return proposals
