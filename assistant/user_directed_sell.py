"""
Owner-directed sell proposals for an individual currently-held position.

Owner request, 2026-08-13: the Selling page could only propose a sell when a
deterministic policy breach demanded one, so there was no way to sell a
specific holding on the owner's own judgement without leaving the app. This
module adds exactly that -- and nothing else.

Distinct from assistant/proposals.py on purpose. That module's contract is
"proposals derived from portfolio policy breaches", and its
`deterministic_risk_policy` evidence status means the PROJECT computed a
breach. A sell chosen by the owner makes no such claim, so it carries its own
`user_directed_sell` status and lives here -- the same separation
assistant/allocation_proposals.py already draws for owner-directed BUYS.

What this module does NOT do:

* it never predicts a price decline. This project has confirmed zero signals
  as real edge for that, and nothing here implies otherwise;
* it never submits, approves, or sizes an order on its own. It produces one
  `proposed` TradeProposal that still needs the typed approval phrase and
  still passes through risk/execution_gate.py at approval time; and
* it never widens what the gate permits. Every refusal below is a REFUSAL TO
  PROPOSE, computed from the same snapshot the reader is looking at, so an
  obviously-doomed proposal is not created in the first place. The gate
  re-checks everything independently and remains the authority.

Refusing to propose can never obstruct risk reduction: the policy-breach
generator is a separate path, and a refusal here always names a smaller
share count that would work whenever one exists.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR

from assistant.money import decimal_or_none, decimal_text
from assistant.policy import TradingPolicy, compute_policy_fingerprint
from assistant.portfolio_analytics import preview_trade_impact
from assistant.proposals import (
    TradeProposal,
    attach_tax_lot_advisory,
    exact_position_shares,
    sellable_whole_shares,
)
from assistant.schemas import DecisionPacket
from assistant.tax_lots import LotLedger
from risk.execution_gate import TradeIntent, is_valid_share_quantity

EVIDENCE_STATUS = "user_directed_sell"


def remaining_shares_after_sale(
    position_shares: object, shares_to_sell: object
) -> Decimal | None:
    """Exact non-negative remainder for a valid whole-share sale.

    ``None`` means either input is unusable or the requested sale exceeds the
    holding.  This helper keeps the UI's wording and the proposal generator on
    the same exact-decimal quantity rule.
    """
    held = decimal_or_none(position_shares)
    if held is None or held <= 0 or not is_valid_share_quantity(shares_to_sell):
        return None
    remainder = held - Decimal(shares_to_sell)
    return remainder if remainder >= 0 else None


def _stable_id(
    packet: DecisionPacket, policy: TradingPolicy, intent: TradeIntent
) -> str:
    # Namespaced and built from packet.generated_at (a full timestamp, not
    # portfolio.as_of's date) for the same reason as every other generator:
    # save_proposal()'s ON CONFLICT DO NOTHING would make a same-day
    # regeneration a silent no-op against a stale or expired row.
    raw = (
        f"user_directed_sell|{packet.generated_at}|{policy.version}|"
        f"{intent.ticker.upper()}|{intent.side}|{intent.shares}"
    )
    return "tp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def generate_user_directed_sell_proposal(
    packet: DecisionPacket,
    policy: TradingPolicy,
    *,
    ticker: str,
    shares: object,
    tax_lot_ledger: LotLedger | None = None,
    tax_lot_coverage: dict | None = None,
    ttl_minutes: int = 15,
    now: datetime | None = None,
) -> dict:
    """One APPROVE-gated sell proposal for a currently-held position.

    Returns ``{"created": True, "proposal": TradeProposal}`` or
    ``{"created": False, "reason": str}``. Never raises for ordinary bad
    input, and never partially creates anything: a refusal is a sentence the
    caller can show verbatim.
    """
    snapshot = packet.portfolio
    normalized = str(ticker).strip().upper()
    if not normalized:
        return {"created": False, "reason": "A ticker is required."}

    position = next(
        (p for p in snapshot.positions if p.ticker.upper() == normalized), None
    )
    if position is None:
        return {
            "created": False,
            "reason": (
                f"{normalized} is not currently held, so there is nothing to "
                "sell. This app never opens a short position."
            ),
        }

    # The project-wide share-quantity authority, reused rather than
    # re-implemented: it rejects bools, floats (including whole-valued ones,
    # NaN, and infinity), strings, zero, and negatives. A NaN share count in
    # particular defeats every ordered comparison below it.
    if not is_valid_share_quantity(shares):
        return {
            "created": False,
            "reason": (
                f"Shares to sell must be a whole number greater than zero, "
                f"got {shares!r}."
            ),
        }

    held_input = (
        position.shares_exact
        if position.shares_exact is not None
        else position.shares
    )
    held_whole = sellable_whole_shares(held_input)
    if held_whole <= 0:
        return {
            "created": False,
            "reason": (
                f"{normalized} reports {position.shares!r} shares, which is "
                "not a usable whole-share quantity to sell."
            ),
        }
    if shares > held_whole:
        return {
            "created": False,
            "reason": (
                f"You hold {held_whole} whole share(s) of {normalized}; "
                f"selling {shares} would short the position, which this app "
                "never does."
            ),
        }

    price_input = (
        position.current_price_exact
        if position.current_price_exact is not None
        else position.current_price
    )
    price_decimal = decimal_or_none(price_input)
    if price_decimal is None or price_decimal <= 0:
        return {
            "created": False,
            "reason": (
                f"{normalized} has no usable current price ({price_input!r}), so "
                "this sale cannot be priced or previewed."
            ),
        }

    notional = Decimal(shares) * price_decimal
    max_order_value = decimal_or_none(policy.max_order_value)
    if max_order_value is None or max_order_value <= 0:
        return {
            "created": False,
            "reason": (
                "The active policy has no usable positive maximum order value "
                f"({policy.max_order_value!r})."
            ),
        }
    if notional > max_order_value:
        fits = int(max_order_value // price_decimal)
        # Stated, never silently applied: quietly shrinking the owner's
        # requested quantity would be an action-shaped edit to their own
        # instruction. The execution gate would refuse this order anyway
        # (MAX_ORDER_VALUE is side-agnostic), so refusing here just makes
        # the refusal legible before a doomed proposal exists.
        remedy = (
            f" At ${price_decimal:,.2f} per share, up to {fits} share(s) fit in one "
            "order; sell the rest in a second order."
            if fits > 0
            else " Even one share exceeds that limit at the current price."
        )
        return {
            "created": False,
            "reason": (
                f"Selling {shares} share(s) of {normalized} is "
                f"${notional:,.2f}, above your policy's ${max_order_value:,.2f} "
                f"maximum order value.{remedy}"
            ),
        }

    at = now or datetime.now(timezone.utc)
    remaining_shares = remaining_shares_after_sale(held_input, shares)
    # The oversell guard above makes None unreachable for valid state, but
    # refuse rather than manufacture a close/remaining claim if the exact
    # quantity changes or becomes unusable between those calculations.
    if remaining_shares is None:
        return {
            "created": False,
            "reason": f"The exact {normalized} share quantity is unavailable.",
        }
    closes_position = remaining_shares == 0
    price = float(price_decimal)
    intent = TradeIntent(
        ticker=normalized,
        side="sell",
        shares=shares,
        order_type="market",
        rationale=(
            f"Owner-directed sale of {shares} share(s) of {normalized} at "
            f"~${price:,.2f}"
            + (" (closes the whole position)." if closes_position else ".")
        ),
    )
    expected_impact = preview_trade_impact(
        snapshot, normalized, "sell", shares, price
    )
    uncertainties = [
        "Market orders can fill away from the displayed reference price.",
        "Policy limits are re-checked independently at approval time; this "
        "proposal is not a promise that the order will pass that check.",
        "If another proposal for this ticker and side is already in flight, "
        "approval is refused until that one resolves.",
    ]
    attach_tax_lot_advisory(
        expected_impact,
        uncertainties,
        ticker=normalized,
        shares=shares,
        price=price,
        when=at,
        tax_lot_ledger=tax_lot_ledger,
        tax_lot_coverage=tax_lot_coverage,
    )

    proposal_id = _stable_id(packet, policy, intent)
    reasons = [
        f"You chose to sell {shares} of your {held_whole} whole share(s) of "
        f"{normalized}.",
        "This is your own instruction, not a project recommendation: nothing "
        "here predicts a price decline, and this project has confirmed zero "
        "signals as real edge for that.",
    ]
    if closes_position:
        reasons.append(
            f"This closes the entire {normalized} position as reported by "
            "this snapshot."
        )
    elif remaining_shares != Decimal(held_whole - shares):
        # A fractional remainder is easy to miss because this workflow accepts
        # whole-share orders only.  Name it explicitly instead of describing
        # the sale of every whole share as a full close.
        reasons.append(
            f"{decimal_text(remaining_shares)} share(s) of {normalized} remain "
            "after this whole-share sale."
        )
    return {
        "created": True,
        "proposal": TradeProposal(
            proposal_id=proposal_id,
            created_at=at.isoformat(),
            expires_at=(at + timedelta(minutes=ttl_minutes)).isoformat(),
            status="proposed",
            idempotency_key=f"{proposal_id}-{snapshot.as_of}",
            policy_version=policy.version,
            policy_fingerprint=compute_policy_fingerprint(policy),
            intent=intent,
            reference_price=price,
            price_timestamp=at.isoformat(),
            reasons=reasons,
            evidence_status=EVIDENCE_STATUS,
            expected_impact=expected_impact,
            alternatives=[
                "Take no action -- nothing is sold until you type the "
                "approval phrase for this proposal.",
                "Sell a different number of shares.",
                "Check the policy-breach section instead, which proposes "
                "sells the project itself computed as required.",
            ],
            uncertainties=uncertainties,
        ),
    }
