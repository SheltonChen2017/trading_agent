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

import math
import os

from config import PAPER_TRADING
from risk.execution_gate import (
    ExecutionAuthorization,
    TradeIntent,
    is_valid_share_quantity,
    verify_execution_authorization,
)


def _require_valid_shares(shares: object) -> None:
    """Defense in depth (GPT review, 2026-07-29): this module is the last
    line of defense before a real broker call, and must not rely solely
    on validate_trade_intent() having already run correctly -- a plain
    `shares <= 0` check does not reject NaN (every ordered comparison
    against NaN is False in Python), so a NaN share count previously
    reached client.submit_order() with zero protection here."""
    if not is_valid_share_quantity(shares):
        raise ValueError(
            f"shares must be a positive whole number (int), got {shares!r} ({type(shares).__name__})."
        )


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
    the only way to find out.

    Returns the order dict when found. Returns None ONLY when Alpaca
    definitively confirms no such order exists (HTTP 404) -- a genuine
    confirmed absence. Any other failure (network, auth, 5xx, etc.)
    PROPAGATES rather than being swallowed into None -- a prior version
    caught every exception and returned None for all of them, which made
    "the order definitely doesn't exist" indistinguishable from "I
    couldn't check." Callers need that distinction: only a confirmed
    absence justifies concluding the order was never accepted; anything
    else must stay unresolved."""
    if not is_configured():
        raise AlpacaNotConfigured(
            "APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set. Sign up for free "
            "paper trading keys at https://alpaca.markets, then set both as "
            "environment variables before calling any execution function."
        )
    client = _get_client()
    try:
        order = client.get_order_by_client_id(client_order_id)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            return None
        raise
    if order is None:
        return None
    # Normalized representation used by assistant/execution_service.py's
    # reconcile_submission() to verify the COMPLETE material order
    # identity (ticker, side, shares, order type, limit price), not just
    # ticker+side -- a prior version returned only ticker/shares/side/
    # status, so an order under the expected client_order_id for BUY 1
    # AAPL could reconcile a proposal for BUY 100 AAPL, or a market order
    # could be mistaken for a limit order, purely because reconciliation
    # never had the fields to tell them apart (GPT review, 2026-07-28).
    return {
        "order_id": str(order.id),
        "client_order_id": getattr(order, "client_order_id", None),
        "ticker": order.symbol,
        "shares": float(order.qty) if order.qty is not None else None,
        "side": getattr(order.side, "value", str(order.side)),
        "type": getattr(order.type, "value", str(order.type)),
        "limit_price": float(order.limit_price) if getattr(order, "limit_price", None) is not None else None,
        "time_in_force": getattr(order, "time_in_force", None) and getattr(
            order.time_in_force, "value", str(order.time_in_force)
        ),
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
            # Lets a caller estimate a pending order's dollar value without
            # an extra live quote for limit/notional orders (see
            # assistant/execution_service.py's _pending_buy_value_by_ticker,
            # Codex review, 2026-07-27: pending buys were invisible to
            # every exposure/concentration cap, not just the cash check).
            "limit_price": float(order.limit_price) if getattr(order, "limit_price", None) is not None else None,
            "notional": float(order.notional) if getattr(order, "notional", None) is not None else None,
        }
        for order in orders
    ]


def submit_market_order(
    ticker: str,
    shares: int,
    side: str = "buy",
    *,
    authorization: ExecutionAuthorization | None = None,
    idempotency_key: str,
) -> dict:
    """Submit a day market order. Refuses to run against a live (non-paper)
    account unless CONFIRM_LIVE_TRADING=I_UNDERSTAND is set — flipping
    PAPER_TRADING alone is not sufficient.

    `idempotency_key` is REQUIRED, not optional (GPT review, 2026-07-31):
    it's what lets a caller safely retry after an ambiguous submission
    error (see assistant/execution_service.py's reconciliation logic) --
    a broker call with no idempotency key at all has zero duplicate-order
    protection, not just "less than ideal" protection. Every real caller
    in this project's production paths (assistant/execution_service.py)
    already supplies one; this only forces any FUTURE direct caller to
    supply one too, rather than silently defaulting to none."""
    if not idempotency_key:
        raise ValueError("idempotency_key is required and must be non-empty -- it is the only duplicate-order protection at the broker layer.")
    if not PAPER_TRADING and os.environ.get("CONFIRM_LIVE_TRADING") != "I_UNDERSTAND":
        raise LiveTradingNotConfirmed(
            "config.PAPER_TRADING is False (live trading) but CONFIRM_LIVE_TRADING "
            "is not set to 'I_UNDERSTAND'. Refusing to submit a live order as a "
            "safety check — set that env var only once you truly mean to trade live."
        )
    _require_valid_shares(shares)
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
    idempotency_key: str,
) -> dict:
    """Submit a day limit order. Same live-trading confirmation gate and
    authorization check as submit_market_order -- kept as a separate
    function (not folded into submit_market_order) so a caller can never
    accidentally reconstruct a market-order intent for authorization
    purposes when the approved intent was actually a limit order.

    `idempotency_key` is REQUIRED -- see submit_market_order()'s
    docstring (GPT review, 2026-07-31)."""
    if not idempotency_key:
        raise ValueError("idempotency_key is required and must be non-empty -- it is the only duplicate-order protection at the broker layer.")
    if not PAPER_TRADING and os.environ.get("CONFIRM_LIVE_TRADING") != "I_UNDERSTAND":
        raise LiveTradingNotConfirmed(
            "config.PAPER_TRADING is False (live trading) but CONFIRM_LIVE_TRADING "
            "is not set to 'I_UNDERSTAND'. Refusing to submit a live order as a "
            "safety check — set that env var only once you truly mean to trade live."
        )
    _require_valid_shares(shares)
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
