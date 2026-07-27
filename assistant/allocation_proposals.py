"""
Proposal generator for the Watchlist "Buy with recommended allocation"
feature: splits a user-specified dollar amount across a user-picked cart
of tickers according to inverse-volatility weights, and produces one
buy TradeProposal per ticker.

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
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone

from assistant.policy import TradingPolicy
from assistant.portfolio_analytics import preview_trade_impact
from assistant.proposals import TradeProposal
from assistant.schemas import DecisionPacket
from risk.execution_gate import TradeIntent

EVIDENCE_STATUS = "user_directed_allocation"


def _stable_id(packet: DecisionPacket, policy: TradingPolicy, intent: TradeIntent, salt: str) -> str:
    raw = (
        f"watchlist_allocation|{salt}|{packet.portfolio.as_of}|{policy.version}|{intent.ticker.upper()}|"
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
) -> list[TradeProposal]:
    """
    One buy proposal per ticker in `weights_pct`, sized at
    dollar_amount * weight_pct / 100 / price, rounded DOWN to whole
    shares (fractional shares aren't supported by TradeIntent). Skips
    any ticker whose allocated dollar amount can't buy at least 1 share,
    or that has no known price.

    Does not check `dollar_amount` against available cash itself -- the
    caller (UI) should bound the input against the account balance, and
    execution_gate independently re-checks cash sufficiency for each
    proposal at approval time regardless.
    """
    if dollar_amount <= 0 or not weights_pct:
        return []

    now = datetime.now(timezone.utc)
    proposals = []
    for ticker, weight_pct in weights_pct.items():
        price = prices.get(ticker)
        if not price or price <= 0:
            continue
        allocated_dollars = dollar_amount * weight_pct / 100
        shares = math.floor(allocated_dollars / price)
        if shares <= 0:
            continue

        intent = TradeIntent(
            ticker=ticker,
            side="buy",
            shares=shares,
            order_type="market",
            rationale=(
                f"User-directed allocation: {weight_pct:.1f}% of ${dollar_amount:,.2f} "
                f"(inverse-volatility weighted) -> {shares} shares at ~${price:,.2f}."
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
                intent=intent,
                reference_price=price,
                price_timestamp=now.isoformat(),
                reasons=[
                    f"You chose to allocate ${dollar_amount:,.2f} across your Watchlist cart; "
                    f"{ticker} received {weight_pct:.1f}% by inverse-volatility weighting."
                ],
                evidence_status=EVIDENCE_STATUS,
                expected_impact=preview_trade_impact(packet.portfolio, ticker, "buy", shares, price),
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
