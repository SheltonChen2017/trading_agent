"""Deterministic portfolio-level metrics used by briefings and proposals."""
from __future__ import annotations

from assistant.schemas import PortfolioSnapshot


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
    trade_value = shares * reference_price
    existing_value = sum(
        p.market_value for p in snapshot.positions if p.ticker.upper() == ticker.upper()
    )
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
    }
