from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Lock, Thread

from assistant.dispatch_fence import execution_dispatch_fence
from assistant.order_reconciler import cancel_all_open_orders
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

    assert scans == 3
    assert canceled == ["order-1", "order-2"]
    assert result["book_scan_count"] == 3
    assert result["book_stable"] is True
    assert result["final_open_order_count"] == 2
