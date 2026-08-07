"""
Allocation planning and proposal generation for the Watchlist "Create
purchase proposals using this split" feature: splits a user-specified
dollar amount across a user-picked cart of tickers according to
inverse-volatility weights, and produces one buy TradeProposal per
ticker that can actually afford at least 1 share.

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

from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_analytics import (
    estimate_pending_buy_value_by_ticker,  # noqa: F401 -- re-exported, scripts/personal_assistant_ui.py imports it from here
    preview_trade_impact,
)
from assistant.proposals import TradeProposal
from assistant.schemas import DecisionPacket
from risk.execution_gate import TradeIntent

EVIDENCE_STATUS = "user_directed_allocation"


@dataclasses.dataclass
class AllocationPlanEntry:
    ticker: str
    weight_pct: float
    target_dollars: float
    reference_price: float
    shares: int
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
    will do with it -- whole shares via floor(), same as proposal
    generation -- plus context needed to judge the plan: existing
    holdings, pending buy orders (or an explicit "unknown" flag if a
    pending order's value can't be determined), the projected final
    position, and the applicable policy position limit.
    """
    snapshot = packet.portfolio
    held_value_by_ticker = {p.ticker.upper(): p.market_value for p in snapshot.positions}
    total_equity = snapshot.total_equity
    pending_buy_value_by_ticker = pending_buy_value_by_ticker or {}
    pending_value_unknown_tickers = pending_value_unknown_tickers or set()
    limit_pct = policy.max_position_pct * 100

    entries: list[AllocationPlanEntry] = []
    for ticker, weight_pct in weights_pct.items():
        ticker_upper = ticker.upper()
        existing_value = held_value_by_ticker.get(ticker_upper, 0.0)
        pending_value = pending_buy_value_by_ticker.get(ticker_upper, 0.0)
        pending_unknown = ticker_upper in pending_value_unknown_tickers
        target_dollars = dollar_amount * weight_pct / 100
        price = prices.get(ticker)

        # math.isfinite, not just `<= 0`: a NaN price passes BOTH `not price`
        # (NaN is truthy) and `price <= 0` (every ordered comparison against
        # NaN is False), and then math.floor(target/NaN) raises ValueError,
        # crashing the whole Watchlist tab. Independent review, 2026-07-29 --
        # reproduced; every other bad price (0, negative, None, inf) already
        # degraded gracefully to a skipped entry, only NaN crashed. NaN is
        # reachable: get_latest_quote() builds `price` from bare
        # float(bid/ask) without a finiteness filter.
        if price is None or not math.isfinite(price) or price <= 0:
            projected_value = existing_value + pending_value
            projected_pct = (projected_value / total_equity * 100) if total_equity else 0.0
            entries.append(
                AllocationPlanEntry(
                    ticker=ticker, weight_pct=weight_pct, target_dollars=target_dollars,
                    reference_price=0.0, shares=0, planned_notional=0.0, unallocated_dollars=target_dollars,
                    existing_market_value=existing_value, pending_buy_value=pending_value,
                    pending_value_unknown=pending_unknown, projected_market_value=projected_value,
                    projected_pct_of_equity=projected_pct, position_limit_pct=limit_pct,
                    distance_to_limit_pct=limit_pct - projected_pct,
                    skipped=True, skip_reason="No current price available.",
                )
            )
            continue

        shares = math.floor(target_dollars / price)
        planned_notional = shares * price
        unallocated = target_dollars - planned_notional
        skipped = shares <= 0
        skip_reason = (
            f"${target_dollars:,.2f} allocation can't buy 1 share at ${price:,.2f}." if skipped else None
        )

        projected_value = existing_value + pending_value + planned_notional
        projected_pct = (projected_value / total_equity * 100) if total_equity else 0.0

        entries.append(
            AllocationPlanEntry(
                ticker=ticker, weight_pct=weight_pct, target_dollars=target_dollars, reference_price=price,
                shares=shares, planned_notional=planned_notional, unallocated_dollars=unallocated,
                existing_market_value=existing_value, pending_buy_value=pending_value,
                pending_value_unknown=pending_unknown, projected_market_value=projected_value,
                projected_pct_of_equity=projected_pct, position_limit_pct=limit_pct,
                distance_to_limit_pct=limit_pct - projected_pct, skipped=skipped, skip_reason=skip_reason,
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
    One buy proposal per ticker in `weights_pct` that can afford at least
    1 share, generated from build_allocation_plan() -- the SAME plan a
    caller should preview before calling this, so what gets proposed
    always exactly matches what was shown.

    Does not check `dollar_amount` against available cash itself -- the
    caller (UI) should bound the input against the account balance, and
    execution_gate independently re-checks cash sufficiency for each
    proposal at approval time regardless.
    """
    if dollar_amount <= 0 or not weights_pct:
        return []

    plan = build_allocation_plan(
        packet, policy, weights_pct, prices, dollar_amount,
        pending_buy_value_by_ticker=pending_buy_value_by_ticker,
        pending_value_unknown_tickers=pending_value_unknown_tickers,
    )

    now = datetime.now(timezone.utc)
    proposals = []
    for entry in plan:
        if entry.skipped or entry.shares <= 0:
            continue

        intent = TradeIntent(
            ticker=entry.ticker,
            side="buy",
            shares=entry.shares,
            order_type="market",
            rationale=(
                f"User-directed allocation: {entry.weight_pct:.1f}% of ${dollar_amount:,.2f} "
                f"(inverse-volatility weighted) -> {entry.shares} shares at ~${entry.reference_price:,.2f}."
            ),
        )
        proposal_id = _stable_id(packet, policy, intent, salt=f"{dollar_amount}")
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
                    f"You chose to allocate ${dollar_amount:,.2f} across your Watchlist cart; "
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
                    "Shares are rounded down, so the actual dollar amount spent per ticker may be somewhat "
                    "less than its exact allocated share.",
                    "Requires allow_new_positions=true in your policy -- off by default, so this will be "
                    "blocked at approval time unless you've explicitly enabled it.",
                    "Market orders can fill away from the displayed reference price.",
                ],
            )
        )
    return proposals
