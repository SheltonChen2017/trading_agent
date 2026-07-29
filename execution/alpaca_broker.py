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

import inspect
import math
import os
from typing import Any, Callable

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


class BrokerPreflightError(RuntimeError):
    """Raised when the account or requested asset is not execution-ready."""


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


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _optional_iso(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat() if callable(isoformat) else value)


def _normalize_order(order: Any) -> dict:
    """Convert every broker order source into one lifecycle-complete shape."""
    return {
        "order_id": str(order.id),
        "client_order_id": getattr(order, "client_order_id", None),
        "ticker": order.symbol,
        "shares": _optional_float(getattr(order, "qty", None)),
        "side": str(_enum_value(getattr(order, "side", "unknown"))),
        "type": str(_enum_value(getattr(order, "type", "unknown"))),
        "limit_price": _optional_float(getattr(order, "limit_price", None)),
        "notional": _optional_float(getattr(order, "notional", None)),
        "time_in_force": (
            str(_enum_value(order.time_in_force))
            if getattr(order, "time_in_force", None) is not None
            else None
        ),
        "status": str(_enum_value(getattr(order, "status", "unknown"))),
        "filled_qty": _optional_float(getattr(order, "filled_qty", None)),
        "filled_avg_price": _optional_float(getattr(order, "filled_avg_price", None)),
        "submitted_at": _optional_iso(getattr(order, "submitted_at", None)),
        "updated_at": _optional_iso(getattr(order, "updated_at", None)),
        "filled_at": _optional_iso(getattr(order, "filled_at", None)),
        "canceled_at": _optional_iso(getattr(order, "canceled_at", None)),
        "expired_at": _optional_iso(getattr(order, "expired_at", None)),
        "failed_at": _optional_iso(getattr(order, "failed_at", None)),
    }


def get_account() -> dict:
    """Current account snapshot, including broker-side trading blocks."""
    account = _get_client().get_account()
    return {
        "account_id": str(account.id),
        "status": str(_enum_value(getattr(account, "status", "unknown"))),
        "equity": float(account.equity),
        "cash": float(account.cash),
        "buying_power": float(account.buying_power),
        "trading_blocked": bool(getattr(account, "trading_blocked", False)),
        "account_blocked": bool(getattr(account, "account_blocked", False)),
        "trade_suspended_by_user": bool(getattr(account, "trade_suspended_by_user", False)),
        "transfers_blocked": bool(getattr(account, "transfers_blocked", False)),
        "paper": PAPER_TRADING,
    }


def get_asset(ticker: str) -> dict:
    asset = _get_client().get_asset(ticker.upper())
    return {
        "ticker": str(asset.symbol).upper(),
        "status": str(_enum_value(getattr(asset, "status", "unknown"))),
        "asset_class": str(_enum_value(getattr(asset, "asset_class", "unknown"))),
        "tradable": bool(getattr(asset, "tradable", False)),
        "fractionable": bool(getattr(asset, "fractionable", False)),
    }


def assert_account_and_asset_ready(ticker: str) -> dict:
    """Fail before submission if Alpaca says trading or the asset is blocked."""
    account = get_account()
    blocked = [
        field
        for field in ("trading_blocked", "account_blocked", "trade_suspended_by_user")
        if account[field]
    ]
    if blocked:
        raise BrokerPreflightError(
            "Broker account is not trading-ready: " + ", ".join(blocked) + "."
        )
    if str(account["status"]).upper() != "ACTIVE":
        raise BrokerPreflightError(
            f"Broker account status is {account['status']!r}, not ACTIVE."
        )
    if not PAPER_TRADING:
        expected_account_id = os.environ.get("TRADING_ASSISTANT_LIVE_ACCOUNT_ID")
        if not expected_account_id:
            raise LiveTradingNotConfirmed(
                "Live account execution also requires TRADING_ASSISTANT_LIVE_ACCOUNT_ID "
                "to be set to the exact intended Alpaca account ID."
            )
        if expected_account_id != account["account_id"]:
            raise LiveTradingNotConfirmed(
                "TRADING_ASSISTANT_LIVE_ACCOUNT_ID does not match the connected Alpaca account."
            )
    asset = get_asset(ticker)
    if asset["status"].lower() != "active" or not asset["tradable"]:
        raise BrokerPreflightError(
            f"{asset['ticker']} is not broker-tradable "
            f"(status={asset['status']!r}, tradable={asset['tradable']})."
        )
    return {"account": account, "asset": asset}


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
    return _normalize_order(order)


def get_order_by_id(order_id: str) -> dict | None:
    client = _get_client()
    try:
        order = client.get_order_by_id(order_id)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 404:
            return None
        raise
    return None if order is None else _normalize_order(order)


def get_open_orders() -> list[dict]:
    """Return currently open broker orders in a JSON-friendly shape."""
    client = _get_client()
    try:
        orders = client.get_orders()
    except TypeError:
        from alpaca.trading.requests import GetOrdersRequest

        orders = client.get_orders(filter=GetOrdersRequest())
    return [_normalize_order(order) for order in orders]


def cancel_order(order_id: str) -> dict:
    """Request cancellation and return the acknowledged local transition."""
    client = _get_client()
    client.cancel_order_by_id(order_id)
    return {"order_id": str(order_id), "status": "pending_cancel"}


def run_trade_update_stream(callback: Callable[[dict], Any]) -> None:
    """Run Alpaca's authenticated trade-update stream until interrupted."""
    if not is_configured():
        raise AlpacaNotConfigured(
            "APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set."
        )
    from alpaca.trading.stream import TradingStream

    stream = TradingStream(
        os.environ["APCA_API_KEY_ID"],
        os.environ["APCA_API_SECRET_KEY"],
        paper=PAPER_TRADING,
    )

    async def handle_update(update) -> None:
        order = _normalize_order(update.order)
        normalized = {
            "event": str(_enum_value(getattr(update, "event", order["status"]))),
            "event_id": getattr(update, "execution_id", None),
            "event_at": _optional_iso(getattr(update, "timestamp", None)),
            "fill_qty": _optional_float(getattr(update, "qty", None)),
            "fill_price": _optional_float(getattr(update, "price", None)),
            "order": order,
        }
        result = callback(normalized)
        if inspect.isawaitable(result):
            await result

    stream.subscribe_trade_updates(handle_update)
    stream.run()


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
    # order_type is stated explicitly rather than relying on TradeIntent's
    # default: it is part of intent_fingerprint(), so the authorization
    # check below silently depends on it. An implicit default is the wrong
    # thing to lean on in the last-mile authorization reconstruction --
    # see submit_limit_order()'s docstring for why the two are kept apart.
    intent = TradeIntent(ticker=ticker, shares=shares, side=side, order_type="market")
    verify_execution_authorization(intent, authorization)
    assert_account_and_asset_ready(ticker)

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
    return _normalize_order(order)


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
    assert_account_and_asset_ready(ticker)

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
    return _normalize_order(order)
