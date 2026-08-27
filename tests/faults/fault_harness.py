"""Shared harness for GR-3 fault-injection drills.

Every fixture here builds REAL state: a real ``AssistantStore`` on a
temporary SQLite file, real policy objects, and the real execution entry
points. Only the account-scoped broker-session opener is patched. Legacy
module broker facades deliberately remain real so a production regression
away from the session boundary cannot be hidden by this harness. The
disk-full fault constrains the actual SQLite database rather than faking an
exception, so the transaction/rollback behavior under test is SQLite's own.
"""
from __future__ import annotations

import contextlib
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import execution.alpaca_broker as broker_module
from assistant.policy import compute_policy_fingerprint, load_policy
from assistant.schemas import PortfolioPosition, PortfolioSnapshot
from assistant.storage import AssistantStore
from tests.execution_test_support import scripted_broker_contact_boundary

NOW_ET = datetime(2026, 8, 3, 14, 30, tzinfo=timezone.utc)


@dataclass(frozen=True)
class AcceptedOrder:
    """Explicit marker for a complete broker-order fixture."""

    order_id: str
    ticker: str
    side: str
    shares: int
    status: str


class ScriptedBroker:
    """A programmable fake broker that records every call, in order.

    Behaviours are provided per function name: an Exception instance is
    raised, a callable is invoked, anything else is returned. The
    recording lets fault tests assert the load-bearing negatives -- e.g.
    that a timeout was NEVER answered with a second submit call.
    """

    PAPER_TRADING = True
    account_mode = "paper"

    def __init__(
        self,
        *,
        execution_positions: list[PortfolioPosition] | None = None,
        **behaviours: Any,
    ) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self._behaviours = behaviours
        self._execution_positions = list(
            [held_position()]
            if execution_positions is None
            else execution_positions
        )
        self._execution_snapshot_id: str | None = None

    @staticmethod
    def _materialize_accepted_order(
        value: AcceptedOrder,
        *,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        """Materialize strict evidence only from the explicit fixture marker."""
        status = value.status.lower()
        submitted_at = "2026-08-03T14:29:00+00:00"
        filled_qty = value.shares if status == "filled" else 0
        filled_price = 100 if status == "filled" else None
        return {
            "order_id": value.order_id,
            "client_order_id": idempotency_key or "idem-p-fault",
            "ticker": value.ticker,
            "asset_class": "us_equity",
            "order_class": "simple",
            "extended_hours": False,
            "legs": None,
            "shares": value.shares,
            "shares_decimal": str(value.shares),
            "notional": None,
            "notional_decimal": None,
            "side": value.side,
            "type": "market",
            "limit_price": None,
            "limit_price_decimal": None,
            "time_in_force": "day",
            "status": status,
            "filled_qty": filled_qty,
            "filled_qty_decimal": str(filled_qty),
            "filled_avg_price": filled_price,
            "filled_avg_price_decimal": (
                None if filled_price is None else str(filled_price)
            ),
            "submitted_at": submitted_at,
            "updated_at": submitted_at,
            "filled_at": submitted_at if status == "filled" else None,
            "canceled_at": submitted_at if status == "canceled" else None,
            "expired_at": submitted_at if status == "expired" else None,
            "failed_at": submitted_at if status == "rejected" else None,
            "replaced_at": submitted_at if status == "replaced" else None,
            "replaces": None,
            "replaced_by": None,
        }

    def set(self, name: str, behaviour: Any) -> None:
        self._behaviours[name] = behaviour

    def handler(self, name: str):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            behaviour = self._behaviours.get(name)
            if isinstance(behaviour, Exception):
                raise behaviour
            if callable(behaviour):
                value = behaviour(*args, **kwargs)
            else:
                value = behaviour
            if isinstance(value, AcceptedOrder) and name in {
                "submit_market_order",
                "submit_limit_order",
                "find_order_by_client_id",
                "get_order_by_id",
            }:
                idempotency_key = kwargs.get("idempotency_key")
                if idempotency_key is None and name == "find_order_by_client_id" and args:
                    idempotency_key = args[0]
                return self._materialize_accepted_order(
                    value,
                    idempotency_key=idempotency_key,
                )
            return value

        return call

    def capture_execution_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Build the same strict, account-bound snapshot production consumes."""
        from assistant.portfolio_snapshot import build_portfolio_snapshot_from_alpaca

        snapshot = build_portfolio_snapshot_from_alpaca(
            broker_session=self,
            require_execution_coherence=True,
        )
        self._execution_snapshot_id = snapshot.broker_snapshot_id
        return snapshot

    def get_account(self) -> dict:
        cash = Decimal("100000")
        equity = cash + sum(
            (position.exact_field("market_value") for position in self._execution_positions),
            Decimal("0"),
        )
        return {
            "account_id": "paper-account-1",
            "paper": True,
            "status": "ACTIVE",
            "equity": float(equity),
            "equity_decimal": str(equity),
            "cash": float(cash),
            "cash_decimal": str(cash),
            "buying_power": float(cash),
            "buying_power_decimal": str(cash),
            "trading_blocked": False,
            "account_blocked": False,
            "trade_suspended_by_user": False,
            "transfers_blocked": False,
        }

    @staticmethod
    def get_open_orders() -> list:
        return []

    def get_open_positions(self) -> list[dict]:
        return [
            {
                "ticker": position.ticker,
                "shares": position.shares,
                "shares_decimal": str(position.exact_field("shares")),
                "avg_entry_price": position.entry_price,
                "avg_entry_price_decimal": str(position.exact_field("entry_price")),
                "current_price": position.current_price,
                "current_price_decimal": str(position.exact_field("current_price")),
                "market_value": position.market_value,
                "market_value_decimal": str(position.exact_field("market_value")),
            }
            for position in self._execution_positions
        ]

    def get_execution_validation_quote(
        self,
        ticker: str,
        *,
        expected_snapshot_id: str,
    ) -> dict:
        if expected_snapshot_id != self._execution_snapshot_id:
            raise PermissionError(
                "Execution quote belongs to a different broker snapshot."
            )
        return self.handler("get_latest_quote")(ticker)

    def assert_account_and_asset_ready(self, *args, **kwargs):
        return self.handler("assert_account_and_asset_ready")(*args, **kwargs)

    def is_configured(self):
        return self.handler("is_configured")()

    def get_latest_quote(self, *args, **kwargs):
        return self.handler("get_latest_quote")(*args, **kwargs)

    def _submit(
        self,
        name: str,
        ticker,
        shares,
        *,
        side="buy",
        authorization=None,
        idempotency_key,
        dispatch_permit=None,
        expected_snapshot_id=None,
        expected_policy_fingerprint,
        limit_price=None,
        **kwargs,
    ):
        """Mirror the real adapter's one-use boundary before scripted contact."""
        with scripted_broker_contact_boundary(
            broker_session=self,
            snapshot_id_reader=lambda: self._execution_snapshot_id,
            consume_snapshot=lambda: setattr(
                self, "_execution_snapshot_id", None
            ),
            ticker=ticker,
            shares=shares,
            side=side,
            order_type="limit" if name == "submit_limit_order" else "market",
            limit_price=limit_price,
            authorization=authorization,
            idempotency_key=idempotency_key,
            dispatch_permit=dispatch_permit,
            expected_snapshot_id=expected_snapshot_id,
            expected_policy_fingerprint=expected_policy_fingerprint,
        ):
            # Match production's ordering: both capabilities are spent before
            # the network result (including a timeout) becomes observable.
            submit_kwargs = {
                "side": side,
                "authorization": authorization,
                "idempotency_key": idempotency_key,
                "dispatch_permit": dispatch_permit,
                "expected_snapshot_id": expected_snapshot_id,
                "expected_policy_fingerprint": expected_policy_fingerprint,
                **kwargs,
            }
            if name == "submit_limit_order":
                submit_kwargs["limit_price"] = limit_price
            return self.handler(name)(ticker, shares, **submit_kwargs)

    def submit_market_order(self, ticker, shares, **kwargs):
        return self._submit("submit_market_order", ticker, shares, **kwargs)

    def submit_limit_order(self, ticker, shares, **kwargs):
        return self._submit("submit_limit_order", ticker, shares, **kwargs)

    def find_order_by_client_id(self, *args, **kwargs):
        return self.handler("find_order_by_client_id")(*args, **kwargs)

    def get_order_by_id(self, *args, **kwargs):
        return self.handler("get_order_by_id")(*args, **kwargs)

    def cancel_order(self, *args, **kwargs):
        return self.handler("cancel_order")(*args, **kwargs)

    @property
    def call_names(self) -> tuple[str, ...]:
        return tuple(name for name, _, _ in self.calls)

    def count(self, name: str) -> int:
        return sum(1 for called, _, _ in self.calls if called == name)


@contextlib.contextmanager
def scripted_broker(broker: ScriptedBroker):
    original_opener = broker_module.open_alpaca_broker_session
    try:
        broker_module.open_alpaca_broker_session = lambda: broker
        yield broker
    finally:
        broker_module.open_alpaca_broker_session = original_opener


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
) -> AcceptedOrder:
    return AcceptedOrder(
        order_id=order_id,
        ticker=ticker,
        side=side,
        shares=shares,
        status=status,
    )


def make_proposal(
    proposal_id: str = "p-fault",
    *,
    status: str = "proposed",
    side: str = "buy",
    shares: int = 1,
    ticker: str = "AAPL",
) -> dict:
    policy = load_policy()
    proposal = {
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
    if status in {
        "submitting",
        "submission_unknown",
        "reconciling",
        "broker_accepted",
        "partially_filled",
        "cancel_pending",
        "executed",
    }:
        proposal["broker_execution_context"] = {
            "account_id": "paper-account-1",
            "account_mode": "paper",
            "snapshot_id": "0" * 64,
            "policy_fingerprint": compute_policy_fingerprint(policy),
        }
    return proposal


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
