from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Lock, Thread

from assistant.dispatch_fence import execution_dispatch_fence
from assistant.order_reconciler import cancel_all_open_orders
from assistant.proposal_status import SUBMITTING
from assistant.storage import AssistantStore


def test_cancel_all_drains_inflight_dispatch_and_cancels_its_late_order(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    dispatch_entered = Event()
    release_dispatch = Event()
    cancel_returned = Event()
    broker_lock = Lock()
    open_orders: list[dict] = []
    canceled: list[str] = []
    scans = 0

    class Broker:
        @staticmethod
        def get_open_orders():
            nonlocal scans
            with broker_lock:
                scans += 1
                return [dict(order) for order in open_orders]

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    def dispatch() -> None:
        with execution_dispatch_fence(store.path):
            dispatch_entered.set()
            assert release_dispatch.wait(timeout=5)
            with broker_lock:
                # Deliberately lacks attribution/material fields. Emergency
                # cancellation needs only the external order ID.
                open_orders.append({"order_id": "late-order"})

    result: list[dict] = []

    def cancel() -> None:
        result.append(
            cancel_all_open_orders(
                store,
                broker_module=Broker,
                reason="concurrent dispatch incident",
                now=datetime(2026, 8, 26, 15, 0, tzinfo=timezone.utc),
            )
        )
        cancel_returned.set()

    dispatch_thread = Thread(target=dispatch)
    dispatch_thread.start()
    assert dispatch_entered.wait(timeout=5)
    cancel_thread = Thread(target=cancel)
    cancel_thread.start()

    for _ in range(100):
        if store.get_kill_switch().get("active"):
            break
        cancel_returned.wait(timeout=0.01)
    assert store.get_kill_switch()["active"] is True
    assert cancel_returned.is_set() is False
    assert scans == 0

    release_dispatch.set()
    dispatch_thread.join(timeout=5)
    cancel_thread.join(timeout=5)
    assert not dispatch_thread.is_alive()
    assert not cancel_thread.is_alive()
    assert canceled == ["late-order"]
    assert result[0]["cancel_requested_count"] == 1
    assert result[0]["book_stable"] is True


def test_cancel_all_still_reaches_valid_ids_when_another_row_is_malformed(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    canceled: list[str] = []

    class Broker:
        @staticmethod
        def get_open_orders():
            return [
                {"order_id": "usable-id", "ticker": None, "side": "unknown"},
                {"ticker": "AAPL", "side": "buy"},
            ]

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    result = cancel_all_open_orders(
        store,
        broker_module=Broker,
        reason="malformed open-book incident",
    )

    assert canceled == ["usable-id"]
    assert result["cancel_requested_count"] == 1
    assert result["book_stable"] is False
    assert result["final_open_order_count"] is None
    assert any("no usable ID" in error["error"] for error in result["errors"])


def test_cancel_all_rescans_until_the_order_id_set_is_stable(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    scans = 0
    canceled: list[str] = []

    class Broker:
        @staticmethod
        def get_open_orders():
            nonlocal scans
            scans += 1
            first = {"order_id": "order-1"}
            second = {"order_id": "order-2"}
            return [first] if scans == 1 else [first, second]

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    result = cancel_all_open_orders(
        store,
        broker_module=Broker,
        reason="changing open-book incident",
    )

    assert scans == 4
    assert canceled == ["order-1", "order-2"]
    assert result["book_scan_count"] == 4
    assert result["book_stable"] is True
    assert result["final_open_order_count"] == 2


def test_cancel_all_uses_durable_attempt_lookup_until_late_order_is_visible(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(
        {
            "proposal_id": "late-proposal",
            "created_at": "2026-08-26T15:00:00+00:00",
            "expires_at": "2026-08-27T15:00:00+00:00",
            "status": "proposed",
            "idempotency_key": "late-client-id",
            "intent": {
                "ticker": "AAPL",
                "side": "buy",
                "shares": 1,
                "order_type": "market",
                "limit_price": None,
            },
        }
    )
    store.update_proposal_status("late-proposal", SUBMITTING)
    lookups = 0
    canceled: list[str] = []

    class Broker:
        @staticmethod
        def get_open_orders():
            return []

        @staticmethod
        def find_order_by_client_id(client_order_id):
            nonlocal lookups
            assert client_order_id == "late-client-id"
            lookups += 1
            if lookups < 3:
                return None
            return {"order_id": "late-indexed-order"}

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    result = cancel_all_open_orders(
        store,
        broker_module=Broker,
        reason="late broker indexing incident",
    )

    assert lookups == 5
    assert canceled == ["late-indexed-order"]
    assert result["book_stable"] is True
    assert result["unresolved_attempt_count"] == 0


def test_cancel_all_retries_a_transient_cancellation_failure_before_stable(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    attempts = 0

    class Broker:
        @staticmethod
        def get_open_orders():
            return [{"order_id": "order-1"}]

        @staticmethod
        def cancel_order(order_id):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient cancellation failure")
            return {"order_id": order_id, "status": "pending_cancel"}

    result = cancel_all_open_orders(
        store,
        broker_module=Broker,
        reason="transient cancellation incident",
    )

    assert attempts == 2
    assert result["cancel_requested_count"] == 1
    assert result["book_stable"] is True


def test_cancel_all_persistent_failure_is_critical_and_never_stable(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    attempts = 0

    class Broker:
        @staticmethod
        def get_open_orders():
            return [{"order_id": "order-1"}]

        @staticmethod
        def cancel_order(_order_id):
            nonlocal attempts
            attempts += 1
            raise RuntimeError("persistent cancellation failure")

    result = cancel_all_open_orders(
        store,
        broker_module=Broker,
        reason="persistent cancellation incident",
    )

    assert attempts == 5
    assert result["cancel_requested_count"] == 0
    assert result["book_stable"] is False
    alerts = store.list_operational_alerts()
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "critical"


def test_cancel_all_default_path_uses_one_frozen_broker_session(
    tmp_path, monkeypatch
):
    import execution.alpaca_broker as broker_facade

    store = AssistantStore(tmp_path / "assistant.db")
    opened: list[object] = []

    class FrozenSession:
        def get_open_orders(self):
            return []

    session = FrozenSession()

    def open_session():
        opened.append(session)
        return session

    monkeypatch.setattr(broker_facade, "open_alpaca_broker_session", open_session)

    result = cancel_all_open_orders(
        store,
        reason="frozen emergency broker context",
    )

    assert opened == [session]
    assert result["book_stable"] is True
    assert result["cancel_requested_count"] == 0
