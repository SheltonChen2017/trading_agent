"""User-approved, policy-bound, paper-only proposal execution."""
from __future__ import annotations

from datetime import datetime, timezone

from assistant.policy import TradingPolicy
from assistant.schemas import PortfolioSnapshot
from assistant.storage import AssistantStore
from risk.execution_gate import (
    TradeIntent,
    authorize_trade_intent,
    validate_trade_intent,
)


class ProposalExecutionError(RuntimeError):
    pass


def _intent_from_dict(raw: dict) -> TradeIntent:
    return TradeIntent(
        ticker=raw["ticker"],
        side=raw["side"],
        shares=int(raw["shares"]),
        order_type=raw.get("order_type", "market"),
        limit_price=raw.get("limit_price"),
        rationale=raw.get("rationale", ""),
    )


def execute_approved_paper_proposal(
    proposal_id: str,
    confirmation: str,
    current_portfolio: PortfolioSnapshot,
    policy: TradingPolicy,
    store: AssistantStore,
    *,
    now_et: datetime,
    kill_switch_active: bool = False,
    earnings_days_away: int | None = None,
) -> dict:
    """
    Revalidate and submit one proposal.

    The exact confirmation phrase is `APPROVE <proposal_id>`. Proposals
    are single-use, short-lived, and currently restricted to Alpaca paper
    accounts regardless of the global broker configuration.
    """
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise ProposalExecutionError(f"Unknown proposal: {proposal_id}")
    if proposal["status"] != "proposed":
        raise ProposalExecutionError(
            f"Proposal {proposal_id} is {proposal['status']}, not proposed."
        )
    if confirmation != f"APPROVE {proposal_id}":
        raise ProposalExecutionError("Explicit approval phrase did not match.")
    if policy.execution_mode != "paper":
        raise ProposalExecutionError("The active policy does not permit paper execution.")
    if proposal["policy_version"] != policy.version:
        raise ProposalExecutionError("Proposal policy version does not match the active policy.")

    now_utc = datetime.now(timezone.utc)
    if now_utc > datetime.fromisoformat(proposal["expires_at"]):
        store.update_proposal_status(proposal_id, "expired")
        raise ProposalExecutionError("Proposal has expired; generate a fresh one.")

    import execution.alpaca_broker as broker

    if not broker.PAPER_TRADING:
        raise ProposalExecutionError("This workflow refuses live trading; PAPER_TRADING must remain True.")
    if not broker.is_configured():
        raise ProposalExecutionError("Alpaca paper credentials are not configured.")

    intent = _intent_from_dict(proposal["intent"])
    if intent.side not in policy.allowed_sides:
        raise ProposalExecutionError(f"Side '{intent.side}' is not allowed by policy.")
    if intent.order_type not in policy.allowed_order_types:
        raise ProposalExecutionError(f"Order type '{intent.order_type}' is not allowed by policy.")
    if intent.side == "buy" and not policy.allow_new_positions:
        held = {p.ticker.upper() for p in current_portfolio.positions}
        if intent.ticker.upper() not in held:
            raise ProposalExecutionError("Opening new positions is disabled by policy.")

    recent_intents = [_intent_from_dict(raw) for raw in store.recent_executed_intents()]
    for order in current_portfolio.open_orders:
        side = str(order.get("side", "")).lower()
        if side in ("buy", "sell") and order.get("shares"):
            recent_intents.append(
                TradeIntent(
                    ticker=order["ticker"],
                    side=side,
                    shares=int(float(order["shares"])),
                )
            )
    current_position = next(
        (p for p in current_portfolio.positions if p.ticker.upper() == intent.ticker.upper()),
        None,
    )
    reference_price = (
        current_position.current_price
        if current_position is not None
        else float(proposal["reference_price"])
    )
    validation = validate_trade_intent(
        intent,
        current_portfolio,
        reference_price,
        # The current broker snapshot was fetched immediately before this
        # call, so its reference price shares the execution clock.
        price_timestamp=now_et,
        now=now_et,
        recent_intents=recent_intents,
        kill_switch_active=kill_switch_active,
        earnings_days_away=earnings_days_away,
        max_position_pct=policy.max_position_pct,
        max_total_exposure_pct=policy.max_total_exposure_pct,
        max_basket_pct=policy.max_basket_pct * 100,
        max_leveraged_etf_pct=policy.max_leveraged_etf_pct * 100,
        max_stale_price_minutes=policy.max_stale_price_minutes,
        max_slippage_pct=policy.max_slippage_pct,
        earnings_blackout_days=policy.earnings_blackout_days,
        max_order_value=policy.max_order_value,
        min_cash_reserve_pct=policy.min_cash_reserve_pct,
    )
    if not validation.approved:
        store.update_proposal_status(
            proposal_id, "blocked", violations=validation.violations
        )
        raise ProposalExecutionError(
            "Execution gate blocked the proposal: " + "; ".join(validation.violations)
        )

    authorization = authorize_trade_intent(intent, validation)
    store.update_proposal_status(
        proposal_id,
        "approved",
        approved_at=now_utc.isoformat(),
        violations=[],
    )
    try:
        order = broker.submit_market_order(
            intent.ticker,
            intent.shares,
            side=intent.side,
            authorization=authorization,
            idempotency_key=proposal["idempotency_key"],
        )
    except Exception as exc:
        store.update_proposal_status(proposal_id, "submission_failed", error=str(exc))
        raise

    store.record_broker_order(proposal_id, order)
    store.update_proposal_status(
        proposal_id,
        "executed",
        executed_at=datetime.now(timezone.utc).isoformat(),
        broker_order=order,
    )
    return order
