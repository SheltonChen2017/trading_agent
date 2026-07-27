"""User-approved, policy-bound, paper-only proposal execution.

2026-07-27 update (independent Codex review, verified against this code
before acting): closed 5 real gaps between this module's safety promises
and what it actually enforced --
  1. Open-order lookup failing open: a broker order-endpoint error was
     silently treated as "no open orders," which is exactly the state a
     duplicate-order check must NOT trust. Now checks
     current_portfolio.open_orders_available and fails closed.
  2. Earnings blackout was accepted as a parameter but never supplied by
     any caller, so the check in risk/execution_gate.py was always
     skipped. Now fetches it live (data/event_data.py) when the caller
     doesn't override it, same "honestly unavailable, never guessed"
     discipline the rest of this project already uses for missing data.
  3. Same-day proposal regeneration silently no-op'd against a stale row
     (see assistant/proposals.py's _stable_id docstring for the fix).
  4. Proposal claiming was read-then-later-write, not atomic -- two
     concurrent approvals could both pass the initial status check. Now
     uses AssistantStore.claim_proposal()'s single conditional UPDATE.
  5. Price staleness was asserted, not measured: price_timestamp was set
     to "now", so the check compared now against itself and could never
     fail regardless of how stale the actual quote was. Now fetches a
     real quote + its own timestamp via execution.alpaca_broker.get_latest_quote().
"""
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


def _resolve_earnings_days_away(ticker: str, override: int | None) -> int | None:
    """Caller-supplied override wins (useful for tests / explicit control).
    Otherwise fetch live -- returns None (check skipped) only when the
    data is honestly unavailable, never guessed."""
    if override is not None:
        return override
    try:
        from data.event_data import fetch_upcoming_earnings

        record = fetch_upcoming_earnings([ticker]).get(ticker, {})
        return record.get("days_away") if record.get("available") else None
    except Exception:
        return None


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

    # Atomic claim: proposed -> validating. If this returns None, someone
    # else already claimed it (concurrent approval), it's not in
    # "proposed" status, or it no longer exists -- stop unconditionally.
    claimed = store.claim_proposal(proposal_id, expected_status="proposed", new_status="validating")
    if claimed is None:
        raise ProposalExecutionError(
            f"Proposal {proposal_id} could not be claimed (already being processed, "
            "already executed, or not in a 'proposed' state)."
        )

    import execution.alpaca_broker as broker

    validation = None
    try:
        if not broker.PAPER_TRADING:
            raise ProposalExecutionError("This workflow refuses live trading; PAPER_TRADING must remain True.")
        if not broker.is_configured():
            raise ProposalExecutionError("Alpaca paper credentials are not configured.")
        if not current_portfolio.open_orders_available:
            raise ProposalExecutionError(
                "Cannot verify open orders right now (the broker's order endpoint failed) -- "
                "refusing to approve since the duplicate-order check would be unreliable. Try again shortly."
            )

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

        try:
            quote = broker.get_latest_quote(intent.ticker)
            reference_price = quote["price"]
            price_timestamp = quote["timestamp"]
        except Exception as exc:
            raise ProposalExecutionError(
                f"Could not fetch a live quote for {intent.ticker} to check price freshness: {exc}"
            )

        resolved_earnings_days_away = _resolve_earnings_days_away(intent.ticker, earnings_days_away)

        validation = validate_trade_intent(
            intent,
            current_portfolio,
            reference_price,
            price_timestamp=price_timestamp,
            now=now_et,
            recent_intents=recent_intents,
            kill_switch_active=kill_switch_active,
            earnings_days_away=resolved_earnings_days_away,
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
            raise ProposalExecutionError(
                "Execution gate blocked the proposal: " + "; ".join(validation.violations)
            )
    except ProposalExecutionError as exc:
        violations = validation.violations if validation is not None and not validation.approved else [str(exc)]
        store.update_proposal_status(proposal_id, "blocked", violations=violations)
        raise

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
