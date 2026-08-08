"""Deterministic portfolio-level metrics used by briefings and proposals."""
from __future__ import annotations

from decimal import Decimal

from assistant.money import decimal_text, to_decimal
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
    totals_decimal: dict[str, Decimal] = {}
    unknown: set[str] = set()
    for order in open_orders:
        if str(order.get("side", "")).lower() != "buy":
            continue
        ticker = order.get("ticker")
        if not ticker:
            continue
        ticker = ticker.upper()
        raw_filled = order.get("filled_qty")
        try:
            filled_qty = (
                to_decimal(raw_filled, name=f"{ticker} pending filled_qty")
                if raw_filled is not None
                else Decimal("0")
            )
        except ValueError:
            # Retain the full order when progress is malformed, and mark the
            # result incomplete so it cannot be published as exact.
            filled_qty = Decimal("0")
            unknown.add(ticker)
        if filled_qty < 0:
            filled_qty = Decimal("0")
            unknown.add(ticker)

        notional = order.get("notional")
        if notional is not None:
            try:
                value = to_decimal(notional, name=f"{ticker} pending notional")
            except ValueError:
                unknown.add(ticker)
                continue
            if value <= 0:
                unknown.add(ticker)
                continue
            raw_fill_price = order.get("filled_avg_price")
            if filled_qty > 0 and raw_fill_price is not None:
                try:
                    fill_price = to_decimal(
                        raw_fill_price, name=f"{ticker} pending filled_avg_price"
                    )
                except ValueError:
                    fill_price = Decimal("0")
                    unknown.add(ticker)
                if fill_price > 0:
                    value = max(Decimal("0"), value - filled_qty * fill_price)
                else:
                    unknown.add(ticker)
            totals_decimal[ticker] = totals_decimal.get(ticker, Decimal("0")) + value
            continue

        raw_shares = order.get("shares")
        if raw_shares is None:
            unknown.add(ticker)
            continue
        try:
            shares = to_decimal(raw_shares, name=f"{ticker} pending shares")
        except ValueError:
            unknown.add(ticker)
            continue
        remaining_shares = shares - filled_qty
        if shares <= 0:
            unknown.add(ticker)
            continue
        if remaining_shares <= 0:
            continue

        raw_limit_price = order.get("limit_price")
        if raw_limit_price is None:
            unknown.add(ticker)
            continue
        try:
            limit_price = to_decimal(
                raw_limit_price, name=f"{ticker} pending limit_price"
            )
        except ValueError:
            unknown.add(ticker)
            continue
        if limit_price <= 0:
            unknown.add(ticker)
            continue
        totals_decimal[ticker] = (
            totals_decimal.get(ticker, Decimal("0"))
            + remaining_shares * limit_price
        )
    return ({ticker: float(value) for ticker, value in totals_decimal.items()}, unknown)


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
    held_shares = sum(
        (
            p.exact_field("shares")
            for p in snapshot.positions
            if p.ticker.upper() == ticker_upper
        ),
        Decimal("0"),
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
    pending_buy_value_by_ticker, pending_unknown_tickers = (
        estimate_pending_buy_value_by_ticker(snapshot.open_orders)
    )
    pending_value = pending_buy_value_by_ticker.get(ticker_upper, 0.0)
    total_pending_value = sum(pending_buy_value_by_ticker.values())
    existing_value = held_value + pending_value
    signed_value = trade_value if side == "buy" else -trade_value
    post_position_value = max(0.0, existing_value + signed_value)
    post_cash = snapshot.cash - total_pending_value - signed_value
    # Independent review, 2026-07-31 (P2 #3): this used to back out current
    # invested value as (total_equity - cash) -- a different formula from
    # compute_portfolio_analytics()'s direct sum(position.market_value).
    # Both are mathematically equal by the snapshot's own construction
    # invariant (see context_builder.py), but as two independently-rounded
    # float computations they can drift by a cent of float epsilon. Reusing
    # the exact same direct-sum formula here removes the drift instead of
    # merely making it rare.
    current_invested = sum(p.market_value for p in snapshot.positions)
    post_invested = current_invested + total_pending_value + signed_value
    total = snapshot.total_equity
    return {
        "trade_value": round(trade_value, 2),
        # Proposal-time share identity lets execution detect a split-shaped
        # broker snapshot change even in the fail-open direction where a
        # forward split leaves MORE than enough shares to submit the old
        # quantity. Stored as decimal text, never reconstructed from display
        # rounding.
        "position_shares_before": decimal_text(held_shares),
        "position_weight_before_pct": round(existing_value / total * 100, 2) if total else 0.0,
        "position_weight_after_pct": round(post_position_value / total * 100, 2) if total else 0.0,
        "cash_before": round(snapshot.cash, 2),
        "cash_after": round(post_cash, 2),
        "invested_pct_after": round(post_invested / total * 100, 2) if total else 0.0,
        "pending_buy_value": round(pending_value, 2),
        "pending_buy_total_value": round(total_pending_value, 2),
        "pending_buy_unknown_tickers": sorted(pending_unknown_tickers),
        "projection_complete": not pending_unknown_tickers,
    }
