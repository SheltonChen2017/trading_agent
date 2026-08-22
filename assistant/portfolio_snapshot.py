"""Assistant-owned portfolio snapshot construction.

This module deliberately contains no signal, strategy, backtest, ML, or
research imports. Execution preflight may obtain a fresh broker snapshot here
without acquiring the broad research dependencies of ``context_builder``.
The legacy context-builder imports remain compatibility aliases.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from config import LEVERAGED_ETF_TICKERS
from assistant.money import decimal_text, to_decimal
from assistant.schemas import PortfolioPosition, PortfolioSnapshot


def _classify_leveraged(ticker: str) -> bool:
    return ticker.upper() in LEVERAGED_ETF_TICKERS


def build_portfolio_snapshot(
    positions: list[dict],
    cash: float,
    *,
    buying_power: float | None = None,
    source: str = "manual",
    account_mode: str = "manual",
    account_id: str | None = None,
    open_orders: list[dict] | None = None,
    open_orders_available: bool = True,
) -> PortfolioSnapshot:
    """Build a validated, canonical portfolio snapshot.

    Position rows are canonicalized and duplicate tickers are aggregated.
    Cash, buying power, shares, costs, and prices must be finite. Duplicate
    rows for one ticker must carry one current price; ambiguity is refused.
    """
    try:
        cash_decimal = to_decimal(cash, name="portfolio.cash")
    except ValueError:
        raise ValueError(
            f"Portfolio cash must be a finite number, got {cash!r}. Refusing to build a snapshot whose "
            "total_equity would be NaN -- every exposure check downstream would silently pass."
        ) from None
    try:
        buying_power_decimal = (
            to_decimal(buying_power, name="portfolio.buying_power")
            if buying_power is not None
            else None
        )
    except ValueError:
        raise ValueError(
            f"Portfolio buying_power must be a finite number or None, got {buying_power!r}."
        ) from None

    grouped: dict[str, dict] = {}
    order: list[str] = []
    for position in positions:
        ticker = position["ticker"].strip().upper()
        for field in ("shares", "entry_price", "current_price"):
            value = position[field]
            try:
                to_decimal(value, name=f"{ticker}.{field}")
            except ValueError:
                raise ValueError(
                    f"Position {ticker!r} has a non-finite/invalid {field}: {value!r}. Refusing to build "
                    "a portfolio snapshot from unusable data -- every exposure and proposal check "
                    "downstream would silently evaluate to False against NaN."
                ) from None
        shares_decimal = to_decimal(position["shares"], name=f"{ticker}.shares")
        entry_price_decimal = to_decimal(
            position["entry_price"], name=f"{ticker}.entry_price"
        )
        current_price_decimal = to_decimal(
            position["current_price"], name=f"{ticker}.current_price"
        )
        if ticker not in grouped:
            grouped[ticker] = {
                "shares": Decimal("0"),
                "cost": Decimal("0"),
                "current_price": current_price_decimal,
            }
            order.append(ticker)
        elif grouped[ticker]["current_price"] != current_price_decimal:
            raise ValueError(
                f"Duplicate position rows for {ticker!r} report different current_price "
                f"values ({grouped[ticker]['current_price']} vs {position['current_price']}) -- "
                "refusing to silently aggregate inconsistent prices."
            )
        grouped[ticker]["shares"] += shares_decimal
        grouped[ticker]["cost"] += shares_decimal * entry_price_decimal

    built: list[PortfolioPosition] = []
    for ticker in order:
        aggregate = grouped[ticker]
        shares = aggregate["shares"]
        current_price = aggregate["current_price"]
        cost = aggregate["cost"]
        market_value = shares * current_price
        entry_price = cost / shares if shares else Decimal("0")
        unrealized_pnl_pct = (
            (market_value - cost) / cost * Decimal("100")
            if cost
            else Decimal("0")
        )
        built.append(
            PortfolioPosition(
                ticker=ticker,
                shares=float(shares),
                entry_price=float(entry_price),
                current_price=float(current_price),
                market_value=float(round(market_value, 2)),
                unrealized_pnl_pct=float(round(unrealized_pnl_pct, 2)),
                is_leveraged_etf=_classify_leveraged(ticker),
                shares_exact=decimal_text(shares),
                entry_price_exact=decimal_text(entry_price),
                current_price_exact=decimal_text(current_price),
                market_value_exact=decimal_text(market_value),
            )
        )

    total_equity = cash_decimal + sum(
        (to_decimal(position.market_value) for position in built), Decimal("0")
    )
    exact_total_equity = cash_decimal + sum(
        (position.exact_field("market_value") for position in built), Decimal("0")
    )
    return PortfolioSnapshot(
        positions=built,
        cash=float(round(cash_decimal, 2)),
        total_equity=float(round(total_equity, 2)),
        cash_exact=decimal_text(cash_decimal),
        total_equity_exact=decimal_text(exact_total_equity),
        buying_power_exact=(
            decimal_text(buying_power_decimal)
            if buying_power_decimal is not None
            else None
        ),
        as_of=datetime.now(timezone.utc).date().isoformat(),
        buying_power=(
            float(round(buying_power_decimal, 2))
            if buying_power_decimal is not None
            else None
        ),
        source=source,
        account_mode=account_mode,
        open_orders=open_orders or [],
        open_orders_available=open_orders_available,
        account_id=account_id,
    )


def build_portfolio_snapshot_from_alpaca() -> PortfolioSnapshot:
    """Pull broker state and build the same validated snapshot shape."""
    from execution.alpaca_broker import get_account, get_open_orders, get_open_positions

    account = get_account()
    try:
        open_orders = get_open_orders()
        open_orders_available = True
    except Exception:
        # A read-only briefing can still expose positions and cash, but order
        # availability must remain explicitly unknown so execution fails closed.
        open_orders = []
        open_orders_available = False
    positions = [
        {
            "ticker": position["ticker"],
            "shares": position.get("shares_decimal", position["shares"]),
            "entry_price": position.get(
                "avg_entry_price_decimal", position["avg_entry_price"]
            ),
            "current_price": position.get(
                "current_price_decimal", position["current_price"]
            ),
        }
        for position in get_open_positions()
    ]
    return build_portfolio_snapshot(
        positions,
        cash=account.get("cash_decimal", account["cash"]),
        buying_power=account.get(
            "buying_power_decimal", account["buying_power"]
        ),
        source="alpaca",
        account_mode="paper" if account["paper"] else "live",
        account_id=account["account_id"],
        open_orders=open_orders,
        open_orders_available=open_orders_available,
    )
