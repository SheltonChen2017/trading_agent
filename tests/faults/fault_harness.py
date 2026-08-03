"""Shared harness for GR-3 fault-injection drills.

Every fixture here builds REAL state: a real ``AssistantStore`` on a
temporary SQLite file, real policy objects, and the real execution entry
points. Only the broker is scripted -- by patching the attributes of
``execution.alpaca_broker`` exactly the way the service's deferred
``import execution.alpaca_broker`` resolves them -- and the disk-full
fault constrains the actual SQLite database rather than faking an
exception, so the transaction/rollback behavior under test is SQLite's
own.
"""
from __future__ import annotations

import contextlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import execution.alpaca_broker as broker_module
from assistant.policy import compute_policy_fingerprint, load_policy
from assistant.schemas import PortfolioPosition, PortfolioSnapshot
from assistant.storage import AssistantStore

NOW_ET = datetime(2026, 8, 3, 14, 30, tzinfo=timezone.utc)

_PATCHED_BROKER_ATTRS = (
    "is_configured",
    "assert_account_and_asset_ready",
    "get_latest_quote",
    "submit_market_order",
    "submit_limit_order",
    "find_order_by_client_id",
    "get_order_by_id",
)


class ScriptedBroker:
    """A programmable fake broker that records every call, in order.

    Behaviours are provided per function name: an Exception instance is
    raised, a callable is invoked, anything else is returned. The
    recording lets fault tests assert the load-bearing negatives -- e.g.
    that a timeout was NEVER answered with a second submit call.
    """

    def __init__(self, **behaviours: Any) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self._behaviours = behaviours

    def set(self, name: str, behaviour: Any) -> None:
        self._behaviours[name] = behaviour

    def handler(self, name: str):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            behaviour = self._behaviours.get(name)
            if isinstance(behaviour, Exception):
                raise behaviour
            if callable(behaviour):
                return behaviour(*args, **kwargs)
            return behaviour

        return call

    @property
    def call_names(self) -> tuple[str, ...]:
        return tuple(name for name, _, _ in self.calls)

    def count(self, name: str) -> int:
        return sum(1 for called, _, _ in self.calls if called == name)


@contextlib.contextmanager
def scripted_broker(broker: ScriptedBroker):
    originals = {
        name: getattr(broker_module, name)
        for name in _PATCHED_BROKER_ATTRS
        if hasattr(broker_module, name)
    }
    try:
        for name in originals:
            setattr(broker_module, name, broker.handler(name))
        yield broker
    finally:
        for name, original in originals.items():
            setattr(broker_module, name, original)


def ready_account(ticker: str = "AAPL") -> dict:
    return {
        "account": {
            "account_id": "paper-account-1",
            "paper": True,
            "status": "ACTIVE",
        },
        "asset": {"symbol": ticker, "status": "active", "tradable": True},
    }


def fresh_quote(price: float = 100.0, *, timestamp: datetime | None = None) -> dict:
    return {
        "ticker": "AAPL",
        "price": price,
        "price_decimal": f"{price:.2f}",
        "bid": price - 0.01,
        "ask": price + 0.01,
        "bid_decimal": f"{price - 0.01:.2f}",
        "ask_decimal": f"{price + 0.01:.2f}",
        "timestamp": timestamp or NOW_ET,
    }


def accepted_order(
    order_id: str = "paper-fault-1",
    *,
    ticker: str = "AAPL",
    side: str = "buy",
    shares: int = 1,
    status: str = "accepted",
) -> dict:
    return {
        "order_id": order_id,
        "ticker": ticker,
        "shares": shares,
        "side": side,
        "type": "market",
        "limit_price": None,
        "status": status,
    }


def make_proposal(
    proposal_id: str = "p-fault",
    *,
    status: str = "proposed",
    side: str = "buy",
    shares: int = 1,
    ticker: str = "AAPL",
) -> dict:
    policy = load_policy()
    return {
        "proposal_id": proposal_id,
        "created_at": "2026-08-03T13:00:00+00:00",
        "expires_at": "2099-12-31T00:00:00+00:00",
        "status": status,
        "idempotency_key": f"idem-{proposal_id}",
        "policy_version": policy.version,
        "policy_fingerprint": compute_policy_fingerprint(policy),
        "intent": {
            "ticker": ticker,
            "side": side,
            "shares": shares,
            "order_type": "market",
            "limit_price": None,
        },
    }


def portfolio(
    *,
    positions: list[PortfolioPosition] | None = None,
    open_orders: list | None = None,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        positions=positions or [],
        cash=100_000.0,
        total_equity=100_000.0,
        as_of="2026-08-03",
        buying_power=100_000.0,
        source="alpaca",
        account_mode="paper",
        account_id="paper-account-1",
        open_orders=open_orders or [],
        open_orders_available=True,
    )


def held_position(ticker: str = "AAPL", shares: float = 10.0) -> PortfolioPosition:
    return PortfolioPosition(
        ticker=ticker,
        shares=shares,
        entry_price=90.0,
        current_price=100.0,
        market_value=shares * 100.0,
        unrealized_pnl_pct=11.1,
        is_leveraged_etf=False,
    )


def observable_state(store: AssistantStore, proposal_id: str) -> dict[str, Any]:
    """Everything a caller or operator could see afterwards -- the
    'no partial state' assertions compare snapshots of this."""
    proposal = store.get_proposal(proposal_id)
    with store._connect() as connection:
        def rows(sql, *params):
            return [dict(r) for r in connection.execute(sql, params).fetchall()]

        reservations = rows(
            "SELECT proposal_id, trading_day, reserved_notional_text "
            "FROM execution_reservations WHERE proposal_id = ? ORDER BY trading_day",
            proposal_id,
        )
        orders = rows(
            "SELECT order_id, proposal_id, status FROM broker_orders "
            "WHERE proposal_id = ? ORDER BY order_id",
            proposal_id,
        )
        events = rows(
            "SELECT event_type FROM broker_order_events "
            "WHERE proposal_id = ? ORDER BY event_at, rowid",
            proposal_id,
        )
    return {
        "proposal_status": None if proposal is None else proposal.get("status"),
        "reservations": reservations,
        "broker_orders": orders,
        "order_events": [e["event_type"] for e in events],
    }


def referential_integrity_holds(store: AssistantStore) -> bool:
    """No orphan rows: every event has its order, every order its
    proposal, every reservation its proposal. This is the cross-fault
    'no partial state' invariant."""
    with store._connect() as connection:
        orphans = connection.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM broker_order_events e
                 WHERE NOT EXISTS (SELECT 1 FROM broker_orders o
                                   WHERE o.order_id = e.order_id))
            + (SELECT COUNT(*) FROM broker_orders o
                 WHERE NOT EXISTS (SELECT 1 FROM trade_proposals p
                                   WHERE p.proposal_id = o.proposal_id))
            + (SELECT COUNT(*) FROM execution_reservations r
                 WHERE NOT EXISTS (SELECT 1 FROM trade_proposals p
                                   WHERE p.proposal_id = r.proposal_id))
            """
        ).fetchone()[0]
    return orphans == 0


class _DiskFullConnection:
    """Delegates everything to a real SQLite connection but answers one
    targeted statement with SQLite's genuine disk-full error. Because the
    OTHER statements of the same transaction really executed first, the
    caller's rollback path is exercised against genuinely written-and-
    then-rolled-back state, not a no-op."""

    def __init__(self, real, needle: str) -> None:
        self._real = real
        self._needle = needle

    def execute(self, sql, *args, **kwargs):
        if self._needle in sql:
            import sqlite3

            raise sqlite3.OperationalError("database or disk is full")
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __setattr__(self, name, value):
        if name in ("_real", "_needle"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._real, name, value)


@contextlib.contextmanager
def disk_full_on_statement(needle: str):
    """Every new store connection raises a real sqlite3.OperationalError
    'database or disk is full' for statements containing ``needle``."""
    original = AssistantStore._open_database

    def constrained(path):
        return _DiskFullConnection(original(path), needle)

    AssistantStore._open_database = staticmethod(constrained)
    try:
        yield
    finally:
        AssistantStore._open_database = staticmethod(original)
