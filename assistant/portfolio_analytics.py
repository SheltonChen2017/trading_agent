"""Deterministic portfolio-level metrics used by briefings and proposals."""
from __future__ import annotations

from assistant.schemas import PortfolioSnapshot


def estimate_pending_buy_value_by_ticker(open_orders: list[dict]) -> tuple[dict[str, float], set[str]]:
    """
    Estimated dollar value of currently pending (not-yet-filled) BUY
    orders, keyed by ticker -- deliberately does NOT make a live quote call
    (unlike assistant.execution_service._pending_buy_value_by_ticker(),
    which is allowed to since it gates real order submission). A UI
    preview refreshing on every rerun shouldn't fire a network call per
    pending order; instead, a pending order whose value can't be
    determined from the order itself (a plain market order with no
    notional or limit price) is reported back in the second return value
    so the caller can show the projection as incomplete rather than
    silently treating it as zero (GPT review, 2026-07-28).

    Originally lived in assistant/allocation_proposals.py (still
    re-exported there for backward compatibility); moved here so
    preview_trade_impact() below can share it without a circular import,
    since allocation_proposals.py itself imports from this module
    (independent review, 2026-07-31).
    """
    totals: dict[str, float] = {}
    unknown: set[str] = set()
    for order in open_orders:
        if str(order.get("side", "")).lower() != "buy":
            continue
        ticker = order.get("ticker")
        if not ticker:
            continue
        ticker = ticker.upper()
        notional = order.get("notional")
        if notional:
            totals[ticker] = totals.get(ticker, 0.0) + float(notional)
            continue
        shares = order.get("shares")
        limit_price = order.get("limit_price")
        if shares and limit_price:
            totals[ticker] = totals.get(ticker, 0.0) + float(shares) * float(limit_price)
            continue
        unknown.add(ticker)
    return totals, unknown


def compute_portfolio_analytics(snapshot: PortfolioSnapshot) -> dict:
    invested = sum(position.market_value for position in snapshot.positions)
    unrealized_pnl = sum(
        position.market_value
        - (position.shares * position.entry_price)
        for position in snapshot.positions
    )
    cost_basis = sum(position.shares * position.entry_price for position in snapshot.positions)
    unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis else 0.0
    weights = {
        position.ticker: round(position.market_value / snapshot.total_equity * 100, 2)
        if snapshot.total_equity
        else 0.0
        for position in snapshot.positions
    }
    return {
        "position_count": len(snapshot.positions),
        "invested_value": round(invested, 2),
        "invested_pct": round(invested / snapshot.total_equity * 100, 2)
        if snapshot.total_equity
        else 0.0,
        "cash_value": round(snapshot.cash, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
        "position_weights_pct": weights,
        "open_order_count": len(snapshot.open_orders),
    }


def preview_trade_impact(
    snapshot: PortfolioSnapshot,
    ticker: str,
    side: str,
    shares: int,
    reference_price: float,
) -> dict:
    ticker_upper = ticker.upper()
    trade_value = shares * reference_price
    held_value = sum(
        p.market_value for p in snapshot.positions if p.ticker.upper() == ticker_upper
    )
    # Independent review, 2026-07-31: this used to compute existing_value
    # purely from snapshot.positions, with no adjustment for this ticker's
    # own pending (not-yet-filled) buy orders -- unlike
    # risk/execution_gate.py, which explicitly folds pending_buy_value_by_ticker
    # into every exposure check specifically so two proposals approved
    # back-to-back can't each look individually fine while together
    # exceeding a cap. Folding the same same-ticker pending value in here
    # makes this per-proposal preview match what the execution gate (and
    # allocation_proposals.py's own build_allocation_plan()) actually see.
    pending_buy_value_by_ticker, _ = estimate_pending_buy_value_by_ticker(snapshot.open_orders)
    pending_value = pending_buy_value_by_ticker.get(ticker_upper, 0.0)
    existing_value = held_value + pending_value
    signed_value = trade_value if side == "buy" else -trade_value
    post_position_value = max(0.0, existing_value + signed_value)
    post_cash = snapshot.cash - signed_value
    post_invested = (snapshot.total_equity - snapshot.cash) + signed_value
    total = snapshot.total_equity
    return {
        "trade_value": round(trade_value, 2),
        "position_weight_before_pct": round(existing_value / total * 100, 2) if total else 0.0,
        "position_weight_after_pct": round(post_position_value / total * 100, 2) if total else 0.0,
        "cash_before": round(snapshot.cash, 2),
        "cash_after": round(post_cash, 2),
        "invested_pct_after": round(post_invested / total * 100, 2) if total else 0.0,
        "pending_buy_value": round(pending_value, 2),
    }
