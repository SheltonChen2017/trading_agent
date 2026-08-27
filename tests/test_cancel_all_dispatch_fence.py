from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest

import assistant.dispatch_fence as dispatch_fence_module
import assistant.execution_service as execution_service_module
import assistant.order_reconciler as order_reconciler_module
import execution.alpaca_broker as alpaca_broker_module
from assistant.dispatch_fence import (
    DispatchFenceTimeout,
    execution_dispatch_fence,
    record_runtime_dispatch_attempt,
    runtime_dispatch_attempts_path,
)
from assistant.order_reconciler import cancel_all_open_orders
from assistant.proposal_status import SUBMITTING
from assistant.storage import AssistantStore


@pytest.fixture(autouse=True)
def _isolated_runtime_fence_root(tmp_path, monkeypatch):
    runtime_root = (tmp_path / "runtime").resolve()
    monkeypatch.setattr(
        dispatch_fence_module,
        "_RUNTIME_FENCE_ROOT",
        runtime_root,
    )
    return runtime_root


def test_cancel_all_drains_dispatch_from_a_different_database_parent(tmp_path):
    dispatch_parent = tmp_path / "dispatch-process"
    cancel_parent = tmp_path / "cancel-process"
    dispatch_parent.mkdir()
    cancel_parent.mkdir()
    dispatch_store = AssistantStore(dispatch_parent / "assistant.db")
    cancel_store = AssistantStore(cancel_parent / "assistant.db")
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
        with execution_dispatch_fence(dispatch_store.path):
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
                cancel_store,
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
        if cancel_store.get_kill_switch().get("active"):
            break
        cancel_returned.wait(timeout=0.01)
    assert cancel_store.get_kill_switch()["active"] is True
    # The stores are deliberately independent.  Serialization therefore comes
    # from the shared runtime fence, not accidentally from shared DB state.
    assert dispatch_store.get_kill_switch()["active"] is False
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
        def get_open_order_ids_for_emergency():
            return {
                "order_ids": ["usable-id", "usable-hidden-id"],
                "complete": False,
                "errors": [
                    {
                        "row_index": 1,
                        "order_id": None,
                        "error": "strict sibling has no usable ID",
                    }
                ],
            }

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    result = cancel_all_open_orders(
        store,
        broker_module=Broker,
        reason="malformed open-book incident",
    )

    assert canceled == ["usable-id", "usable-hidden-id"]
    assert result["cancel_requested_count"] == 2
    assert result["book_stable"] is False
    assert result["final_open_order_count"] is None
    assert any("no usable ID" in error["error"] for error in result["errors"])


def test_cancel_all_does_not_report_unreadable_stops_as_observed_active(
    tmp_path, monkeypatch
):
    store = AssistantStore(tmp_path / "assistant.db")

    class Broker:
        @staticmethod
        def get_open_orders():
            return []

    def unreadable_runtime_stop(_database):
        raise OSError("runtime stop read failed")

    def unreadable_local_stop():
        raise OSError("local stop read failed")

    monkeypatch.setattr(
        "assistant.order_reconciler.get_runtime_emergency_stop",
        unreadable_runtime_stop,
    )
    monkeypatch.setattr(store, "get_kill_switch", unreadable_local_stop)

    result = cancel_all_open_orders(
        store,
        broker_module=Broker,
        reason="unreadable containment evidence",
    )

    assert result["runtime_stop_active"] is None
    assert result["runtime_stop_confirmed"] is False
    assert result["kill_switch_active"] is None
    assert result["local_stop_confirmed"] is False
    assert result["book_stable"] is False


@pytest.mark.parametrize("raw_id", [" padded-id ", 123, {}, [], "unknown"])
def test_cancel_all_rejects_noncanonical_open_order_ids(tmp_path, raw_id):
    store = AssistantStore(tmp_path / "assistant.db")
    canceled: list[str] = []

    class Broker:
        @staticmethod
        def get_open_orders():
            return [{"order_id": raw_id}]

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)

    result = cancel_all_open_orders(
        store, broker_module=Broker, reason="malformed ID incident"
    )

    assert canceled == []
    assert result["book_stable"] is False
    assert any("no usable ID" in item["error"] for item in result["errors"])


def test_strict_open_book_failure_uses_emergency_id_enumeration(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    canceled: list[str] = []

    class Broker:
        @staticmethod
        def get_open_orders():
            raise ValueError("one sibling order is malformed")

        @staticmethod
        def get_open_order_ids_for_emergency():
            return {
                "order_ids": ["usable-emergency-id"],
                "complete": False,
                "errors": [
                    {
                        "row_index": 1,
                        "order_id": None,
                        "error": "sibling has no usable ID",
                    }
                ],
            }

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    result = cancel_all_open_orders(
        store, broker_module=Broker, reason="strict normalization incident"
    )

    assert canceled == ["usable-emergency-id"]
    assert result["book_stable"] is False
    assert any(
        "emergency open-order enumeration" in item["error"]
        for item in result["errors"]
    )


def test_real_alpaca_session_emergency_enumeration_cancels_valid_uuid_sibling(
    tmp_path, monkeypatch
):
    store = AssistantStore(tmp_path / "assistant.db")
    valid_id = uuid4()
    canceled: list[str] = []

    class FakeTradingClient:
        _api_key = "test-key"
        _secret_key = "test-secret"
        _sandbox = True
        _base_url = alpaca_broker_module._TRADING_PAPER_BASE_URL
        _oauth_token = None
        _use_basic_auth = False

        @staticmethod
        def get_account():
            return SimpleNamespace(
                id="paper-account-1",
                status="ACTIVE",
                equity="1000",
                cash="1000",
                buying_power="1000",
                trading_blocked=False,
                account_blocked=False,
                trade_suspended_by_user=False,
                transfers_blocked=False,
            )

        @staticmethod
        def get_orders(*, filter):
            assert filter is not None
            return [
                SimpleNamespace(
                    id=valid_id,
                    symbol="AAPL",
                    qty="1",
                    status="new",
                ),
                SimpleNamespace(
                    id={"malformed": "order-id"},
                    symbol="MSFT",
                    qty="1",
                    status="new",
                ),
            ]

        @staticmethod
        def cancel_orders():
            raise RuntimeError("bulk cancellation unavailable")

        @staticmethod
        def cancel_order_by_id(order_id):
            canceled.append(order_id)

    client = FakeTradingClient()
    monkeypatch.setattr(
        alpaca_broker_module,
        "_capture_connection_settings",
        lambda: ("test-key", "test-secret", True),
    )
    monkeypatch.setattr(
        alpaca_broker_module,
        "_new_trading_client",
        lambda *_args, **_kwargs: client,
    )
    session = alpaca_broker_module.AlpacaBrokerSession()

    result = cancel_all_open_orders(
        store,
        broker_module=session,
        reason="real-session malformed sibling incident",
    )

    assert canceled == [str(valid_id)]
    assert result["cancel_requested_count"] == 1
    assert result["book_stable"] is False
    assert any(
        "emergency open-order enumeration" in item["error"]
        for item in result["errors"]
    )


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


def test_queued_execution_in_other_database_refuses_after_cancel_all(
    tmp_path, monkeypatch
):
    dispatch_store = AssistantStore(tmp_path / "dispatch" / "assistant.db")
    cancel_store = AssistantStore(tmp_path / "cancel" / "assistant.db")
    scan_entered = Event()
    release_scan = Event()
    execution_finished = Event()
    execution_errors: list[BaseException] = []

    class Broker:
        calls = 0

        @classmethod
        def get_open_orders(cls):
            cls.calls += 1
            if cls.calls == 1:
                scan_entered.set()
                assert release_scan.wait(timeout=5)
            return []

    monkeypatch.setattr(
        execution_service_module,
        "verify_execution_preconditions",
        lambda *_args, **_kwargs: {"idempotency_key": "queued-client-id"},
    )
    monkeypatch.setattr(
        execution_service_module, "claim_for_execution", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        execution_service_module,
        "_transition_pre_broker_claim",
        lambda *_args, **_kwargs: None,
    )

    cancel_thread = Thread(
        target=lambda: cancel_all_open_orders(
            cancel_store, broker_module=Broker, reason="cross-database incident"
        )
    )
    cancel_thread.start()
    assert scan_entered.wait(timeout=5)

    def execute() -> None:
        try:
            execution_service_module.execute_approved_paper_proposal(
                "proposal-1",
                "approve",
                object(),
                object(),
                dispatch_store,
                now_et=datetime.now(timezone.utc),
            )
        except BaseException as exc:
            execution_errors.append(exc)
        finally:
            execution_finished.set()

    execution_thread = Thread(target=execute)
    execution_thread.start()
    assert execution_finished.wait(timeout=0.1) is False
    release_scan.set()
    cancel_thread.join(timeout=5)
    execution_thread.join(timeout=5)

    assert len(execution_errors) == 1
    assert isinstance(
        execution_errors[0], execution_service_module.ProposalExecutionError
    )
    assert dispatch_store.get_kill_switch()["active"] is False


def test_cancel_all_discovers_cross_database_delayed_index_attempt(tmp_path):
    dispatch_store = AssistantStore(tmp_path / "dispatch" / "assistant.db")
    cancel_store = AssistantStore(tmp_path / "cancel" / "assistant.db")
    record_runtime_dispatch_attempt(
        dispatch_store.path,
        proposal_id="proposal-1",
        idempotency_key="delayed-client-id",
        attempted_at=datetime.now(timezone.utc).isoformat(),
        account_id="paper-account-1",
        account_mode="paper",
    )
    lookups = 0
    canceled: list[str] = []

    class Broker:
        account_mode = "paper"

        @staticmethod
        def get_account():
            return {"account_id": "paper-account-1", "paper": True}

        @staticmethod
        def get_open_orders():
            return []

        @staticmethod
        def find_order_by_client_id(client_id):
            nonlocal lookups
            assert client_id == "delayed-client-id"
            lookups += 1
            if lookups < 3:
                return None
            return {"order_id": "delayed-order"}

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    result = cancel_all_open_orders(
        cancel_store, broker_module=Broker, reason="delayed indexing incident"
    )

    assert canceled == ["delayed-order"]
    assert lookups >= 3
    assert result["book_stable"] is True


def test_incomplete_book_exact_looks_up_and_cancels_old_retained_order_id(
    tmp_path,
):
    dispatch_store = AssistantStore(tmp_path / "dispatch" / "assistant.db")
    cancel_store = AssistantStore(tmp_path / "cancel" / "assistant.db")
    old_attempted_at = "2026-08-26T12:00:00+00:00"
    record_runtime_dispatch_attempt(
        dispatch_store.path,
        proposal_id="proposal-old",
        idempotency_key="old-client-id",
        attempted_at=old_attempted_at,
        account_id="paper-account-1",
        account_mode="paper",
    )
    record_runtime_dispatch_attempt(
        dispatch_store.path,
        proposal_id="proposal-old",
        idempotency_key="old-client-id",
        attempted_at=old_attempted_at,
        account_id="paper-account-1",
        account_mode="paper",
        order_id="retained-old-order",
        state="broker_accepted",
    )
    lookups = 0
    canceled: list[str] = []

    class Broker:
        account_mode = "paper"

        @staticmethod
        def get_account():
            return {"account_id": "paper-account-1", "paper": True}

        @staticmethod
        def get_open_orders():
            raise RuntimeError("open book unavailable")

        @staticmethod
        def get_open_order_ids_for_emergency():
            return {"order_ids": [], "complete": False, "errors": []}

        @staticmethod
        def get_order_by_id(order_id):
            nonlocal lookups
            assert order_id == "retained-old-order"
            lookups += 1
            return None

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    result = cancel_all_open_orders(
        cancel_store,
        broker_module=Broker,
        reason="incomplete old-attempt scan",
        now=datetime(2026, 8, 26, 15, 0, tzinfo=timezone.utc),
    )

    assert lookups >= 1
    assert canceled == ["retained-old-order"]
    assert result["book_stable"] is False


def test_foreign_account_runtime_attempt_prevents_stable_completion(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    record_runtime_dispatch_attempt(
        store.path,
        proposal_id="foreign-proposal",
        idempotency_key="foreign-client-id",
        attempted_at=datetime.now(timezone.utc).isoformat(),
        account_id="paper-account-OTHER",
        account_mode="paper",
    )
    canceled: list[str] = []

    class Broker:
        account_mode = "paper"

        @staticmethod
        def get_account():
            return {"account_id": "paper-account-1", "paper": True}

        @staticmethod
        def get_open_orders():
            return []

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)

    result = cancel_all_open_orders(
        store, broker_module=Broker, reason="credential switch incident"
    )

    assert canceled == []
    assert result["book_stable"] is False
    assert result["unresolved_attempt_count"] >= 1
    assert any(
        "different broker account/mode" in item["error"]
        for item in result["errors"]
    )


def test_cancel_all_fence_failure_still_cancels_and_records_incomplete(
    tmp_path, monkeypatch
):
    store = AssistantStore(tmp_path / "assistant.db")
    canceled: list[str] = []

    @contextmanager
    def broken_fence(_database):
        raise DispatchFenceTimeout("simulated busy fence")
        yield

    monkeypatch.setattr(
        order_reconciler_module, "execution_dispatch_fence", broken_fence
    )

    class Broker:
        @staticmethod
        def get_open_orders():
            return [{"order_id": "risk-order"}]

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    result = cancel_all_open_orders(
        store, broker_module=Broker, reason="fence failure incident"
    )

    assert canceled == ["risk-order"]
    assert result["dispatch_fence_acquired"] is False
    assert "simulated busy fence" in result["dispatch_fence_error"]
    assert result["scan_book_stable"] is True
    assert result["book_stable"] is False
    assert store.list_operational_alerts()[0]["severity"] == "critical"


def test_cancel_all_local_stop_failure_does_not_abort_broker_cancellation(
    tmp_path, monkeypatch
):
    store = AssistantStore(tmp_path / "assistant.db")
    canceled: list[str] = []
    monkeypatch.setattr(
        store,
        "set_kill_switch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("disk fault")),
    )

    class Broker:
        @staticmethod
        def get_open_orders():
            return [{"order_id": "risk-order"}]

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    result = cancel_all_open_orders(
        store, broker_module=Broker, reason="local stop failure incident"
    )

    assert canceled == ["risk-order"]
    assert result["local_stop_error"] == "disk fault"
    assert result["book_stable"] is False


def test_malformed_shared_attempt_ledger_fails_closed(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    path = runtime_dispatch_attempts_path(store.path)
    path.parent.mkdir(parents=True)
    path.write_text('{"version":1,"attempts":[{}]}', encoding="utf-8")

    class Broker:
        @staticmethod
        def get_open_orders():
            return []

    result = cancel_all_open_orders(
        store, broker_module=Broker, reason="malformed attempt ledger"
    )

    assert result["book_stable"] is False
    assert any(
        "dispatch-attempt ledger" in error["error"] for error in result["errors"]
    )
    assert store.list_operational_alerts()[0]["severity"] == "critical"
