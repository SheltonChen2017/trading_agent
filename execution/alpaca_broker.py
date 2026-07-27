"""
Alpaca execution layer — the only module in this repo that talks to a
real (paper or live) brokerage account.

Dormant by design: every function that needs a connection calls
_get_client(), which raises AlpacaNotConfigured until you set
APCA_API_KEY_ID / APCA_API_SECRET_KEY as environment variables. Nothing
here imports alpaca-py at module load time, so the rest of the agent
(scanner, backtest, ML, risk) runs fine without the package installed or
any credentials present.

Get free paper trading keys at https://alpaca.markets — no account
funding required. NEVER hardcode keys in this file or anywhere in the
repo; use environment variables (or a local, gitignored .env you load
yourself).

config.PAPER_TRADING selects the endpoint (paper vs live). As an extra
safety net, submit_market_order() refuses to send a LIVE order unless the
CONFIRM_LIVE_TRADING environment variable is explicitly set to
"I_UNDERSTAND" — flipping PAPER_TRADING to False alone is not enough,
on purpose.
"""
from __future__ import annotations

import os

import pandas as pd

from config import PAPER_TRADING
from risk.execution_gate import ExecutionAuthorization, TradeIntent, verify_execution_authorization


class AlpacaNotConfigured(RuntimeError):
    """Raised when Alpaca API credentials are not set in the environment."""


class LiveTradingNotConfirmed(RuntimeError):
    """Raised when live (non-paper) trading is attempted without the explicit confirmation env var."""


def is_configured() -> bool:
    return bool(os.environ.get("APCA_API_KEY_ID")) and bool(os.environ.get("APCA_API_SECRET_KEY"))


def _get_client():
    if not is_configured():
        raise AlpacaNotConfigured(
            "APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set. Sign up for free "
            "paper trading keys at https://alpaca.markets, then set both as "
            "environment variables before calling any execution function."
        )
    from alpaca.trading.client import TradingClient  # lazy import — package optional until used

    key = os.environ["APCA_API_KEY_ID"]
    secret = os.environ["APCA_API_SECRET_KEY"]
    return TradingClient(key, secret, paper=PAPER_TRADING)


def get_account() -> dict:
    """Current account snapshot: equity, cash, and buying power."""
    account = _get_client().get_account()
    return {
        "equity": float(account.equity),
        "cash": float(account.cash),
        "buying_power": float(account.buying_power),
        "paper": PAPER_TRADING,
    }


def get_open_positions() -> list[dict]:
    client = _get_client()
    return [
        {
            "ticker": p.symbol,
            "shares": float(p.qty),
            "avg_entry_price": float(p.avg_entry_price),
            "current_price": float(p.current_price),
            "unrealized_pl": float(p.unrealized_pl),
        }
        for p in client.get_all_positions()
    ]


def get_latest_quote(ticker: str) -> dict:
    """Real-time bid/ask quote with the broker's OWN timestamp -- used to
    measure actual price staleness at approval time, instead of asserting
    freshness by comparing "now" against "now" (a real bug this fixes: a
    quote fetched over a weekend can be date(s) old even though nothing
    about the code path would have noticed). Returns bid/ask separately
    (not just a collapsed mid price) so the execution gate can check
    spread width -- a market order has no limit price to compare against,
    so a wide/thin quote otherwise passes validation with zero protection.
    Mid price when both sides are quoted; falls back to whichever single
    side is nonzero (a wide or one-sided book, common outside market
    hours, still yields SOME reference price rather than crashing)."""
    if not is_configured():
        raise AlpacaNotConfigured(
            "APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set. Sign up for free "
            "paper trading keys at https://alpaca.markets, then set both as "
            "environment variables before calling any execution function."
        )
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest

    key = os.environ["APCA_API_KEY_ID"]
    secret = os.environ["APCA_API_SECRET_KEY"]
    client = StockHistoricalDataClient(key, secret)
    quotes = client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=[ticker]))
    quote = quotes[ticker]
    bid, ask = float(quote.bid_price), float(quote.ask_price)
    if bid > 0 and ask > 0:
        price = (bid + ask) / 2
    else:
        price = ask if ask > 0 else bid
    return {"ticker": ticker, "price": price, "bid": bid, "ask": ask, "timestamp": quote.timestamp}


def find_order_by_client_id(client_order_id: str) -> dict | None:
    """Look up a previously-submitted order by the client_order_id we sent
    (== our idempotency_key). Used for reconciliation after an ambiguous
    submission failure (e.g. a network timeout): Alpaca may have accepted
    the order even though we never saw a successful response, and this is
    the only way to find out. Returns None when the broker genuinely has
    no such order (never submitted) OR when the lookup itself fails (still
    can't be confirmed) -- callers must treat both the same way: "not
    confirmed", not "confirmed absent"."""
    if not is_configured():
        raise AlpacaNotConfigured(
            "APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set. Sign up for free "
            "paper trading keys at https://alpaca.markets, then set both as "
            "environment variables before calling any execution function."
        )
    client = _get_client()
    try:
        order = client.get_order_by_client_id(client_order_id)
    except Exception:
        return None
    if order is None:
        return None
    return {
        "order_id": str(order.id),
        "ticker": order.symbol,
        "shares": float(order.qty) if order.qty is not None else None,
        "side": getattr(order.side, "value", str(order.side)),
        "status": getattr(order.status, "value", str(order.status)),
    }


def get_open_orders() -> list[dict]:
    """Return currently open broker orders in a JSON-friendly shape."""
    client = _get_client()
    try:
        orders = client.get_orders()
    except TypeError:
        from alpaca.trading.requests import GetOrdersRequest

        orders = client.get_orders(filter=GetOrdersRequest())
    return [
        {
            "order_id": str(order.id),
            "ticker": order.symbol,
            "shares": float(order.qty) if order.qty is not None else None,
            "side": getattr(order.side, "value", str(order.side)),
            "type": getattr(order.type, "value", str(order.type)),
            "status": getattr(order.status, "value", str(order.status)),
            "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
        }
        for order in orders
    ]


def submit_market_order(
    ticker: str,
    shares: int,
    side: str = "buy",
    *,
    authorization: ExecutionAuthorization | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Submit a day market order. Refuses to run against a live (non-paper)
    account unless CONFIRM_LIVE_TRADING=I_UNDERSTAND is set — flipping
    PAPER_TRADING alone is not sufficient."""
    if not PAPER_TRADING and os.environ.get("CONFIRM_LIVE_TRADING") != "I_UNDERSTAND":
        raise LiveTradingNotConfirmed(
            "config.PAPER_TRADING is False (live trading) but CONFIRM_LIVE_TRADING "
            "is not set to 'I_UNDERSTAND'. Refusing to submit a live order as a "
            "safety check — set that env var only once you truly mean to trade live."
        )
    if shares <= 0:
        raise ValueError(f"shares must be positive, got {shares}")
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    intent = TradeIntent(ticker=ticker, shares=shares, side=side)
    verify_execution_authorization(intent, authorization)

    client = _get_client()
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    order = client.submit_order(
        MarketOrderRequest(
            symbol=ticker,
            qty=shares,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            client_order_id=idempotency_key,
        )
    )
    return {"order_id": str(order.id), "ticker": ticker, "shares": shares, "side": side, "status": str(order.status)}


def submit_limit_order(
    ticker: str,
    shares: int,
    limit_price: float,
    side: str = "buy",
    *,
    authorization: ExecutionAuthorization | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Submit a day limit order. Same live-trading confirmation gate and
    authorization check as submit_market_order -- kept as a separate
    function (not folded into submit_market_order) so a caller can never
    accidentally reconstruct a market-order intent for authorization
    purposes when the approved intent was actually a limit order."""
    if not PAPER_TRADING and os.environ.get("CONFIRM_LIVE_TRADING") != "I_UNDERSTAND":
        raise LiveTradingNotConfirmed(
            "config.PAPER_TRADING is False (live trading) but CONFIRM_LIVE_TRADING "
            "is not set to 'I_UNDERSTAND'. Refusing to submit a live order as a "
            "safety check — set that env var only once you truly mean to trade live."
        )
    if shares <= 0:
        raise ValueError(f"shares must be positive, got {shares}")
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    intent = TradeIntent(ticker=ticker, shares=shares, side=side, order_type="limit", limit_price=limit_price)
    verify_execution_authorization(intent, authorization)

    client = _get_client()
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest

    order = client.submit_order(
        LimitOrderRequest(
            symbol=ticker,
            qty=shares,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            client_order_id=idempotency_key,
        )
    )
    return {
        "order_id": str(order.id),
        "ticker": ticker,
        "shares": shares,
        "side": side,
        "limit_price": limit_price,
        "status": str(order.status),
    }


def submit_stop_loss_order(
    ticker: str,
    shares: int,
    stop_price: float,
    *,
    authorization: ExecutionAuthorization | None = None,
) -> dict:
    """Submit a GTC stop order to exit a long position — the execution-side
    counterpart of risk.manager's computed stop_loss_price."""
    if not PAPER_TRADING and os.environ.get("CONFIRM_LIVE_TRADING") != "I_UNDERSTAND":
        raise LiveTradingNotConfirmed(
            "config.PAPER_TRADING is False (live trading) but CONFIRM_LIVE_TRADING "
            "is not set to 'I_UNDERSTAND'. Refusing to submit a live order."
        )

    if shares <= 0:
        raise ValueError(f"shares must be positive, got {shares}")
    verify_execution_authorization(
        TradeIntent(
            ticker=ticker,
            shares=shares,
            side="sell",
            order_type="stop",
            limit_price=round(stop_price, 2),
        ),
        authorization,
    )

    client = _get_client()
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import StopOrderRequest

    order = client.submit_order(
        StopOrderRequest(
            symbol=ticker,
            qty=shares,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            stop_price=round(stop_price, 2),
        )
    )
    return {"order_id": str(order.id), "ticker": ticker, "shares": shares, "stop_price": stop_price, "status": str(order.status)}


def execute_allocation(
    sized: pd.DataFrame,
    authorizations: dict[str, ExecutionAuthorization] | None = None,
) -> list[dict]:
    """
    Take risk.manager.allocate()'s output and submit a market buy + a GTC
    stop-loss for every row with shares > 0. Rows with 0 shares (filtered
    out by confidence or the exposure cap) are skipped, not submitted.

    Raises AlpacaNotConfigured immediately if credentials aren't set —
    callers (e.g. scripts/run_agent.py) should catch that and just report
    the sized-but-unexecuted signals instead of crashing.
    """
    results = []
    authorizations = authorizations or {}
    for _, row in sized.iterrows():
        if row["shares"] <= 0:
            continue
        ticker = str(row["ticker"])
        buy = submit_market_order(
            ticker,
            int(row["shares"]),
            side="buy",
            authorization=authorizations.get(ticker),
        )
        stop = submit_stop_loss_order(
            ticker,
            int(row["shares"]),
            float(row["stop_loss_price"]),
            authorization=authorizations.get(f"{ticker}:stop"),
        )
        results.append({"ticker": row["ticker"], "buy_order": buy, "stop_order": stop})
    return results
