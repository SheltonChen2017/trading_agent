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


def submit_market_order(ticker: str, shares: int, side: str = "buy") -> dict:
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

    client = _get_client()
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    order = client.submit_order(
        MarketOrderRequest(
            symbol=ticker,
            qty=shares,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
    )
    return {"order_id": str(order.id), "ticker": ticker, "shares": shares, "side": side, "status": str(order.status)}


def submit_stop_loss_order(ticker: str, shares: int, stop_price: float) -> dict:
    """Submit a GTC stop order to exit a long position — the execution-side
    counterpart of risk.manager's computed stop_loss_price."""
    if not PAPER_TRADING and os.environ.get("CONFIRM_LIVE_TRADING") != "I_UNDERSTAND":
        raise LiveTradingNotConfirmed(
            "config.PAPER_TRADING is False (live trading) but CONFIRM_LIVE_TRADING "
            "is not set to 'I_UNDERSTAND'. Refusing to submit a live order."
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


def execute_allocation(sized: pd.DataFrame) -> list[dict]:
    """
    Take risk.manager.allocate()'s output and submit a market buy + a GTC
    stop-loss for every row with shares > 0. Rows with 0 shares (filtered
    out by confidence or the exposure cap) are skipped, not submitted.

    Raises AlpacaNotConfigured immediately if credentials aren't set —
    callers (e.g. scripts/run_agent.py) should catch that and just report
    the sized-but-unexecuted signals instead of crashing.
    """
    results = []
    for _, row in sized.iterrows():
        if row["shares"] <= 0:
            continue
        buy = submit_market_order(row["ticker"], int(row["shares"]), side="buy")
        stop = submit_stop_loss_order(row["ticker"], int(row["shares"]), float(row["stop_loss_price"]))
        results.append({"ticker": row["ticker"], "buy_order": buy, "stop_order": stop})
    return results
