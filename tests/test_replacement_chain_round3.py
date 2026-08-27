"""
Round-3 replacement-chain gaps: manual reconciliation, stale cancellation, and
per-hop identity validation.

Three defects, all reproduced before fixing (independent review, 2026-07-29):

1. reconcile_submission() -- the USER-FACING manual operation -- never followed
   replaced_by. It validated and journaled the superseded order, and because
   the original order still matches the stored intent (only its status is
   "replaced") the identity check passed and nothing looked wrong. A human
   could re-run reconciliation forever and stay pinned to a dead order while
   the replacement had already filled.
2. Polling resolved the chain for PROJECTION but passed the original order to
   _cancel_if_stale(), so it cancelled the superseded order, left the live
   replacement running, and still reported cancellation_requested=1 with no
   errors.
3. _resolve_replacement_chain() validated only the FINAL order, so a chain of
   10 -> 999 -> 10 shares was accepted with no error and no kill switch. An
   altered intermediate may have been live long enough to receive fills.
"""
from __future__ import annotations

import contextlib
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import assistant.dispatch_fence as dispatch_fence_module
from assistant.order_lifecycle import (
    CHAIN_ERROR_IDENTITY_MISMATCH,
    CHAIN_ERROR_UNRESOLVED,
    MAX_REPLACEMENT_CHAIN_DEPTH,
    journal_broker_order_update,
    resolve_replacement_chain,
)
from assistant.order_reconciler import (
    cancel_all_open_orders,
    cancel_assistant_order,
    reconcile_nonterminal_orders,
)
from assistant.proposal_status import (
    BROKER_ACCEPTED,
    CANCEL_PENDING,
    FILLED,
    PARTIALLY_FILLED,
    SUBMISSION_UNKNOWN,
)
from assistant.storage import AssistantStore

_INTENT = {"ticker": "AAPL", "side": "buy", "shares": 10, "order_type": "market", "limit_price": None}
_OLD = "2020-01-01T00:00:00+00:00"
_ACCOUNT_ID = "paper-account-1"
_SNAPSHOT_ID = "a" * 64
_POLICY_FINGERPRINT = "b" * 64


@pytest.fixture(autouse=True)
def _isolated_dispatch_runtime(tmp_path, monkeypatch):
    """Prevent emergency-stop latches from leaking across focused tests."""
    runtime_root = (tmp_path / "runtime").resolve()
    monkeypatch.setattr(dispatch_fence_module, "_RUNTIME_FENCE_ROOT", runtime_root)


def _broker_account() -> dict:
    return {"account_id": _ACCOUNT_ID, "paper": True}


def _proposal(status: str = "broker_accepted", pid: str = "tp-ready") -> dict:
    return {
        "proposal_id": pid,
        "created_at": "2026-07-29T14:00:00+00:00",
        "expires_at": "2026-07-30T14:00:00+00:00",
        "status": status,
        "idempotency_key": f"idem-{pid}",
        "broker_execution_context": {
            "account_id": _ACCOUNT_ID,
            "account_mode": "paper",
            "snapshot_id": _SNAPSHOT_ID,
            "policy_fingerprint": _POLICY_FINGERPRINT,
        },
        "intent": dict(_INTENT),
    }


def _order(order_id: str, status: str, **kw) -> dict:
    order = {
        "order_id": order_id,
        "client_order_id": (
            "idem-tp-ready" if order_id == "order-1" else f"c-{order_id}"
        ),
        "ticker": "AAPL", "asset_class": "us_equity", "order_class": "simple",
        "extended_hours": False, "legs": None,
        "shares": 10.0, "shares_decimal": "10", "notional": None,
        "notional_decimal": None, "side": "buy", "type": "market",
        "limit_price": None, "limit_price_decimal": None,
        "time_in_force": "day", "status": status, "filled_qty": 0.0,
        "filled_qty_decimal": "0", "filled_avg_price": None,
        "filled_avg_price_decimal": None,
        "submitted_at": "2026-07-29T14:00:00+00:00", "updated_at": None,
        "filled_at": None, "canceled_at": None, "expired_at": None,
        "failed_at": None, "replaced_by": None, "replaces": None,
        "replaced_at": None,
    }
    order.update(kw)
    order["shares_decimal"] = str(order["shares"])
    order["limit_price_decimal"] = (
        None if order["limit_price"] is None else str(order["limit_price"])
    )
    order["filled_qty_decimal"] = str(order["filled_qty"])
    order["filled_avg_price_decimal"] = (
        None
        if order["filled_avg_price"] is None
        else str(order["filled_avg_price"])
    )
    if status == "filled" and order["filled_at"] is None:
        order["filled_at"] = order["submitted_at"]
    if status == "replaced" and order["replaced_at"] is None:
        order["replaced_at"] = order["submitted_at"]
    return order


def _broker(orders: dict, *, lookups: list | None = None, canceled: list | None = None,
            cancel_raises: bool = False):
    class B:
        PAPER_TRADING = True
        account_mode = "paper"

        @staticmethod
        def get_account():
            return _broker_account()

        @staticmethod
        def find_order_by_client_id(key):
            return orders.get("order-1")

        @staticmethod
        def get_order_by_id(oid):
            if lookups is not None:
                lookups.append(oid)
            scripted = orders.get(oid)
            return scripted() if callable(scripted) else scripted

        @staticmethod
        def cancel_order(oid):
            if cancel_raises:
                raise RuntimeError("broker refused the cancellation")
            if canceled is not None:
                canceled.append(oid)
            return {"order_id": oid, "status": "pending_cancel"}

    return B


def _store(temp: str, status: str = "broker_accepted") -> AssistantStore:
    store = AssistantStore(Path(temp) / "a.db")
    store.save_proposal(_proposal(status))
    return store


# --------------------------------------------------------------------------
# 1. reconcile_submission() -- the manual, user-facing path
# --------------------------------------------------------------------------

@contextlib.contextmanager
def _patched_broker(fake):
    """Substitute execution.alpaca_broker for the duration of the block.

    Patches BOTH sys.modules and the parent package attribute, because
    `import execution.alpaca_broker as broker` (what reconcile_submission does)
    binds from `getattr(execution, "alpaca_broker")` when that attribute
    already exists, falling back to sys.modules only when it does not. Patching
    sys.modules alone therefore worked when this file ran on its own and was
    silently ignored in the full suite, where an earlier test had already
    imported the real module -- ten tests passed alone and failed together.
    """
    import execution

    real_module = sys.modules.get("execution.alpaca_broker")
    had_attr = hasattr(execution, "alpaca_broker")
    real_attr = getattr(execution, "alpaca_broker", None)
    sys.modules["execution.alpaca_broker"] = fake
    execution.alpaca_broker = fake
    try:
        yield
    finally:
        if real_module is not None:
            sys.modules["execution.alpaca_broker"] = real_module
        else:
            sys.modules.pop("execution.alpaca_broker", None)
        if had_attr:
            execution.alpaca_broker = real_attr
        else:
            delattr(execution, "alpaca_broker")


def _run_manual(orders: dict, lookups: list):
    """Invoke reconcile_submission() against a fake broker module."""
    from assistant.execution_service import reconcile_submission

    fake = types.ModuleType("execution.alpaca_broker")
    fake.PAPER_TRADING = True
    fake.account_mode = "paper"
    fake.get_account = _broker_account
    fake.find_order_by_client_id = lambda key: orders.get("order-1")

    def _get(oid):
        lookups.append(oid)
        scripted = orders.get(oid)
        return scripted() if callable(scripted) else scripted

    fake.get_order_by_id = _get
    with _patched_broker(fake):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = _store(temp, status="submission_unknown")
            error = None
            returned = None
            try:
                returned = reconcile_submission("tp-ready", store)
            except Exception as exc:
                error = str(exc)
            return {
                "returned": returned,
                "status": store.get_proposal("tp-ready")["status"],
                "kill_switch": store.get_kill_switch()["active"],
                "error": error,
                "reconciled_at": store.get_proposal("tp-ready").get("reconciled_at"),
            }


@pytest.mark.parametrize(
    "replacement_status,filled_qty,expected_status",
    [("accepted", 0.0, BROKER_ACCEPTED),
     ("partially_filled", 4.0, PARTIALLY_FILLED),
     ("filled", 10.0, FILLED)],
)
def test_manual_reconciliation_follows_replaced_by(replacement_status, filled_qty, expected_status):
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": _order("order-2", replacement_status, filled_qty=filled_qty,
                          filled_avg_price=100.0 if filled_qty else None, replaces="order-1"),
    }
    lookups: list = []
    out = _run_manual(orders, lookups)
    assert lookups == ["order-2"], "the replacement must actually be fetched"
    assert out["returned"]["order_id"] == "order-2", "must return the AUTHORITATIVE order"
    assert out["status"] == expected_status
    assert out["error"] is None


def test_manual_reconciliation_follows_multiple_hops():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": _order("order-2", "replaced", replaced_by="order-3", replaces="order-1"),
        "order-3": _order("order-3", "filled", filled_qty=10.0, filled_avg_price=100.0,
                          replaces="order-2"),
    }
    lookups: list = []
    out = _run_manual(orders, lookups)
    assert lookups == ["order-2", "order-3"]
    assert out["returned"]["order_id"] == "order-3"
    assert out["status"] == FILLED


def test_manual_reconciliation_leaves_a_missing_replacement_retryable():
    orders = {"order-1": _order("order-1", "replaced", replaced_by="order-2")}
    out = _run_manual(orders, [])
    assert out["status"] == SUBMISSION_UNKNOWN, "must stay retryable, not become submission_failed"
    assert out["kill_switch"] is False, "an unresolved lookup is not an authorization anomaly"
    assert "could not be found" in out["error"]
    assert out["reconciled_at"], "a reconciled_at timestamp is still recorded"


def test_manual_reconciliation_survives_a_lookup_exception():
    orders = {"order-1": _order("order-1", "replaced", replaced_by="order-2")}

    from assistant.execution_service import reconcile_submission

    fake = types.ModuleType("execution.alpaca_broker")
    fake.PAPER_TRADING = True
    fake.account_mode = "paper"
    fake.get_account = _broker_account
    fake.find_order_by_client_id = lambda key: orders["order-1"]

    def _boom(oid):
        raise RuntimeError("broker unavailable")

    fake.get_order_by_id = _boom
    with _patched_broker(fake):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = _store(temp, status="submission_unknown")
            with pytest.raises(Exception) as excinfo:
                reconcile_submission("tp-ready", store)
            assert "lookup failed" in str(excinfo.value)
            assert store.get_proposal("tp-ready")["status"] == SUBMISSION_UNKNOWN
            assert store.get_kill_switch()["active"] is False


def test_manual_reconciliation_detects_a_cycle():
    order_2_revisit = _order(
        "order-2", "replaced", replaced_by="order-5", replaces="order-4"
    )
    order_2_versions = iter(
        (
            _order("order-2", "replaced", replaced_by="order-3", replaces="order-1"),
            order_2_revisit,
        )
    )
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": lambda: next(order_2_versions),
        "order-3": _order("order-3", "replaced", replaced_by="order-4", replaces="order-2"),
        "order-4": _order("order-4", "replaced", replaced_by="order-2", replaces="order-3"),
    }
    out = _run_manual(orders, [])
    assert out["status"] == SUBMISSION_UNKNOWN
    assert "cycle" in out["error"]
    assert out["kill_switch"] is False


def test_manual_reconciliation_stops_at_the_depth_limit():
    orders = {f"order-{i}": _order(f"order-{i}", "replaced", replaced_by=f"order-{i + 1}",
                                   replaces=f"order-{i - 1}" if i > 1 else None)
              for i in range(1, 40)}
    out = _run_manual(orders, [])
    assert out["status"] == SUBMISSION_UNKNOWN
    assert "exceeded" in out["error"]


def test_manual_reconciliation_kill_switches_on_a_mismatched_replacement():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": _order("order-2", "accepted", shares=999.0, replaces="order-1"),
    }
    out = _run_manual(orders, [])
    assert out["kill_switch"] is True, "an altered replacement is an authorization anomaly"
    assert out["status"] == SUBMISSION_UNKNOWN
    assert "does not match the stored intent" in out["error"]


def test_manual_and_polling_reconciliation_reach_the_same_state():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": _order("order-2", "filled", filled_qty=10.0, filled_avg_price=100.0,
                          replaces="order-1"),
    }
    manual = _run_manual(orders, [])["status"]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        reconcile_nonterminal_orders(store, broker_module=_broker(orders))
        polled = store.get_proposal("tp-ready")["status"]
    assert manual == polled == FILLED, f"manual={manual} polled={polled}"


# --------------------------------------------------------------------------
# 2. stale cancellation must target the authoritative order
# --------------------------------------------------------------------------

def test_stale_cancellation_cancels_the_replacement_not_the_superseded_order():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2", submitted_at=_OLD),
        "order-2": _order("order-2", "accepted", replaces="order-1", submitted_at=_OLD),
    }
    canceled: list = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(
            store, broker_module=_broker(orders, canceled=canceled),
            cancel_stale=True, max_order_age_minutes=1.0,
        )
        assert canceled == ["order-2"], f"must cancel the LIVE order, got {canceled}"
        assert result["cancellation_requested"] == 1
        assert store.get_proposal("tp-ready")["status"] == CANCEL_PENDING


def test_stale_cancellation_targets_the_final_order_in_a_multi_hop_chain():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2", submitted_at=_OLD),
        "order-2": _order("order-2", "replaced", replaced_by="order-3", replaces="order-1",
                          submitted_at=_OLD),
        "order-3": _order("order-3", "accepted", replaces="order-2", submitted_at=_OLD),
    }
    canceled: list = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        reconcile_nonterminal_orders(
            store, broker_module=_broker(orders, canceled=canceled),
            cancel_stale=True, max_order_age_minutes=1.0,
        )
        assert canceled == ["order-3"]


def test_operator_cancel_follows_the_replacement_chain():
    orders = {
        "order-1": _order(
            "order-1", "replaced", replaced_by="order-2"
        ),
        "order-2": _order(
            "order-2", "accepted", replaces="order-1"
        ),
    }
    canceled: list[str] = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = cancel_assistant_order(
            store,
            "tp-ready",
            broker_module=_broker(orders, canceled=canceled),
            now=datetime(2026, 7, 30, 15, 0, tzinfo=timezone.utc),
        )

        assert canceled == ["order-2"]
        assert result["order_id"] == "order-2"
        # The shared resolver records the replacement IDs it followed; the
        # original order is available separately through the proposal/order
        # journal.
        assert result["replacement_chain"] == ["order-2"]
        assert store.get_proposal("tp-ready")["status"] == CANCEL_PENDING


def test_operator_cancel_kill_switches_even_if_mismatch_cancel_fails():
    orders = {
        "order-1": _order(
            "order-1", "replaced", replaced_by="order-2"
        ),
        "order-2": _order(
            "order-2",
            "accepted",
            replaces="order-1",
            shares=999.0,
        ),
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        with pytest.raises(Exception, match="cancellation request"):
            cancel_assistant_order(
                store,
                "tp-ready",
                broker_module=_broker(orders, cancel_raises=True),
            )

        assert store.get_kill_switch()["active"] is True
        assert store.get_proposal("tp-ready")["status"] == SUBMISSION_UNKNOWN


def test_emergency_cancel_all_engages_kill_switch_and_cancels_unmanaged_orders():
    managed = _order(
        "order-1",
        "accepted",
        client_order_id="idem-tp-ready",
    )
    unmanaged = _order(
        "outside-order",
        "accepted",
        client_order_id="outside-client-id",
    )
    canceled: list[str] = []

    class Broker:
        PAPER_TRADING = True
        account_mode = "paper"

        @staticmethod
        def get_account():
            return _broker_account()

        @staticmethod
        def get_open_orders():
            return [managed, unmanaged]

        @staticmethod
        def cancel_order(order_id):
            canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = cancel_all_open_orders(
            store,
            broker_module=Broker,
            reason="operator incident drill",
            now=datetime(2026, 7, 30, 15, 0, tzinfo=timezone.utc),
        )

        assert canceled == ["order-1", "outside-order"]
        assert result["cancel_requested_count"] == 2
        assert result["unmanaged_order_count"] == 1
        assert result["errors"] == []
        assert store.get_kill_switch()["active"] is True
        assert store.get_proposal("tp-ready")["status"] == CANCEL_PENDING


def test_emergency_cancel_all_continues_after_one_broker_rejection():
    first = _order("order-1", "accepted")
    second = _order("order-2", "accepted")
    attempted: list[str] = []

    class Broker:
        PAPER_TRADING = True
        account_mode = "paper"

        @staticmethod
        def get_account():
            return _broker_account()

        @staticmethod
        def get_open_orders():
            return [first, second]

        @staticmethod
        def cancel_order(order_id):
            attempted.append(order_id)
            if order_id == "order-1":
                raise RuntimeError("temporary broker rejection")
            return {"order_id": order_id, "status": "pending_cancel"}

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = cancel_all_open_orders(
            store,
            broker_module=Broker,
            reason="cancel-all partial failure test",
        )

        assert attempted.count("order-1") == 5
        assert attempted.count("order-2") == 1
        assert result["cancel_requested_count"] == 1
        assert len(result["errors"]) == 5
        assert result["book_stable"] is False
        assert store.get_kill_switch()["active"] is True


def test_emergency_cancel_all_records_an_open_order_query_failure():
    class Broker:
        PAPER_TRADING = True
        account_mode = "paper"

        @staticmethod
        def get_account():
            return _broker_account()

        @staticmethod
        def get_open_orders():
            raise RuntimeError("broker unavailable")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = cancel_all_open_orders(
            store,
            broker_module=Broker,
            reason="broker outage incident",
        )

        assert result["open_order_count"] is None
        assert result["cancel_requested_count"] == 0
        assert "open-order query failed" in result["errors"][0]["error"]
        assert store.get_kill_switch()["active"] is True
        assert (
            store.get_system_state("last_cancel_all_open_orders")
            == result
        )


def test_a_non_stale_replacement_is_not_cancelled_even_if_the_original_is_old():
    """Staleness must be judged on the AUTHORITATIVE order's own timestamp."""
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2", submitted_at=_OLD),
        "order-2": _order("order-2", "accepted", replaces="order-1",
                          submitted_at=datetime.now(timezone.utc).isoformat()),
    }
    canceled: list = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(
            store, broker_module=_broker(orders, canceled=canceled),
            cancel_stale=True, max_order_age_minutes=30.0,
        )
        assert canceled == [], "the fresh replacement must not be cancelled"
        assert result["cancellation_requested"] == 0


def test_a_terminal_replacement_is_never_cancelled():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2", submitted_at=_OLD),
        "order-2": _order("order-2", "filled", filled_qty=10.0, filled_avg_price=100.0,
                          replaces="order-1", submitted_at=_OLD),
    }
    canceled: list = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        reconcile_nonterminal_orders(
            store, broker_module=_broker(orders, canceled=canceled),
            cancel_stale=True, max_order_age_minutes=1.0,
        )
        assert canceled == [], "a filled order must never be cancelled"
        assert store.get_proposal("tp-ready")["status"] == FILLED


def test_a_failed_cancellation_is_not_reported_as_requested():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2", submitted_at=_OLD),
        "order-2": _order("order-2", "accepted", replaces="order-1", submitted_at=_OLD),
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(
            store, broker_module=_broker(orders, cancel_raises=True),
            cancel_stale=True, max_order_age_minutes=1.0,
        )
        assert result["cancellation_requested"] == 0, "a refused cancel must not be counted"
        assert result["errors"], "the failure must surface as an error"


@pytest.mark.parametrize(
    ("submitted_at", "expected_kind"),
    [
        (None, "missing"),
        ("not-a-timestamp", "malformed"),
        ("2026-08-26T16:00:00", "naive"),
        ("2026-08-26T16:00:05.001000+00:00", "material_future"),
    ],
)
def test_bad_stale_order_time_enters_explicit_operator_recovery(
    submitted_at, expected_kind
):
    """Ambiguous time cannot be reported as a successful stale-order pass.

    Automatic cancellation from corrupt time evidence is unsafe: the order may
    have been submitted moments ago.  The risk-reducing seam is therefore an
    explicit operator-recovery disposition backed by a durable halt/alert.
    """
    now = datetime(2026, 8, 26, 16, 0, tzinfo=timezone.utc)
    orders = {
        "order-1": _order(
            "order-1", "accepted", submitted_at=submitted_at
        )
    }
    canceled: list[str] = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(
            store,
            broker_module=_broker(orders, canceled=canceled),
            cancel_stale=True,
            max_order_age_minutes=30.0,
            now=now,
        )

        assert canceled == []
        assert result["cancellation_requested"] == 0
        assert result["timestamp_integrity_failures"] == 1
        assert len(result["errors"]) == 1
        disposition = result["cancellation_dispositions"][0]
        assert disposition["timestamp"]["kind"] == expected_kind
        assert disposition["timestamp"]["integrity_ok"] is False
        assert disposition["cancellation"] == {
            "kind": "operator_recovery_required",
            "requested": False,
        }
        assert disposition["order_id"] == "order-1"
        assert store.get_kill_switch()["active"] is True
        heartbeat = store.get_system_state("last_order_reconciliation")
        assert heartbeat["error_count"] == 1
        assert heartbeat["timestamp_integrity_error_count"] == 1
        alerts = store.list_operational_alerts()
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "critical"
        assert alerts[0]["details"]["order_id"] == "order-1"
        assert (
            alerts[0]["details"]["timestamp_disposition"]["kind"]
            == expected_kind
        )
        assert (
            alerts[0]["details"]["cancellation_disposition"]
            == "operator_recovery_required"
        )


def test_bad_authoritative_replacement_time_keeps_structured_disposition():
    now = datetime(2026, 8, 26, 16, 0, tzinfo=timezone.utc)
    orders = {
        "order-1": _order(
            "order-1",
            "replaced",
            replaced_by="order-2",
            submitted_at=(now - timedelta(hours=1)).isoformat(),
        ),
        "order-2": _order(
            "order-2",
            "accepted",
            replaces="order-1",
            submitted_at="2026-08-26T16:00:00",
        ),
    }
    canceled: list[str] = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(
            store,
            broker_module=_broker(orders, canceled=canceled),
            cancel_stale=True,
            max_order_age_minutes=30.0,
            now=now,
        )

        assert canceled == []
        assert result["timestamp_integrity_failures"] == 1
        disposition = result["cancellation_dispositions"][0]
        assert disposition["order_id"] == "order-2"
        assert disposition["timestamp"]["kind"] == "naive"
        assert (
            disposition["cancellation"]["kind"]
            == "operator_recovery_required"
        )


@pytest.mark.parametrize(
    ("offset_seconds", "expected_kind"),
    [
        (0.0, "valid"),
        (-60.0, "valid"),
        (5.0, "small_future_skew"),
    ],
)
def test_recent_order_time_and_frozen_future_skew_boundary_are_healthy(
    offset_seconds, expected_kind
):
    now = datetime(2026, 8, 26, 16, 0, tzinfo=timezone.utc)
    submitted_at = (now + timedelta(seconds=offset_seconds)).isoformat()
    orders = {
        "order-1": _order(
            "order-1", "accepted", submitted_at=submitted_at
        )
    }
    canceled: list[str] = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(
            store,
            broker_module=_broker(orders, canceled=canceled),
            cancel_stale=True,
            max_order_age_minutes=30.0,
            now=now,
        )

        assert canceled == []
        assert result["errors"] == []
        assert result["timestamp_integrity_failures"] == 0
        disposition = result["cancellation_dispositions"][0]
        assert disposition["timestamp"]["kind"] == expected_kind
        assert disposition["cancellation"]["kind"] == "recent"
        assert store.get_kill_switch()["active"] is False


def test_implicit_order_clock_is_captured_after_the_broker_read(monkeypatch):
    """A slow lookup must not manufacture a materially-future timestamp."""
    import assistant.order_reconciler as reconciler_module

    started_at = datetime(2026, 8, 26, 16, 0, tzinfo=timezone.utc)
    submitted_at = started_at + timedelta(seconds=6)

    class AdvancingDateTime(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            value = started_at if cls.calls == 1 else started_at + timedelta(seconds=10)
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(reconciler_module, "datetime", AdvancingDateTime)
    orders = {
        "order-1": _order(
            "order-1", "accepted", submitted_at=submitted_at.isoformat()
        )
    }
    canceled: list[str] = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(
            store,
            broker_module=_broker(orders, canceled=canceled),
            cancel_stale=True,
            max_order_age_minutes=30.0,
        )

        assert canceled == []
        assert result["errors"] == []
        assert result["timestamp_integrity_failures"] == 0
        assert (
            result["cancellation_dispositions"][0]["timestamp"]["kind"]
            == "valid"
        )
        assert store.get_kill_switch()["active"] is False


def test_stale_boundary_requests_cancellation_and_records_its_disposition():
    now = datetime(2026, 8, 26, 16, 0, tzinfo=timezone.utc)
    orders = {
        "order-1": _order(
            "order-1",
            "accepted",
            submitted_at=(now - timedelta(minutes=30)).isoformat(),
        )
    }
    canceled: list[str] = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(
            store,
            broker_module=_broker(orders, canceled=canceled),
            cancel_stale=True,
            max_order_age_minutes=30.0,
            now=now,
        )

        assert canceled == ["order-1"]
        assert result["errors"] == []
        assert result["cancellation_requested"] == 1
        disposition = result["cancellation_dispositions"][0]
        assert disposition["timestamp"]["signed_age_seconds"] == 30.0 * 60.0
        assert disposition["cancellation"]["kind"] == "requested_for_staleness"
        assert disposition["cancellation"]["requested"] is True


def test_the_stored_broker_order_is_the_authoritative_replacement():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": _order("order-2", "accepted", replaces="order-1"),
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        reconcile_nonterminal_orders(store, broker_module=_broker(orders))
        found = store.get_proposal_by_broker_order_id("order-2")
        assert found is not None and found["proposal_id"] == "tp-ready", (
            "the authoritative replacement must be the order stored against the proposal"
        )


# --------------------------------------------------------------------------
# 3. every hop must be identity-validated, not just the last
# --------------------------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("shares", 999.0),
    ("ticker", "TSLA"),
    ("side", "sell"),
    ("type", "limit"),
])
def test_an_altered_intermediate_replacement_trips_the_kill_switch(field, value):
    """The chain ends on a MATCHING order, so only per-hop validation can catch
    the altered middle one. This is the exact 10 -> 999 -> 10 probe."""
    middle = _order("order-2", "replaced", replaced_by="order-3", replaces="order-1")
    middle[field] = value
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": middle,
        "order-3": _order("order-3", "accepted", replaces="order-2"),
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(store, broker_module=_broker(orders))
        assert store.get_kill_switch()["active"] is True, (
            f"an intermediate order with an altered {field} must not be accepted"
        )
        assert store.get_proposal("tp-ready")["status"] == SUBMISSION_UNKNOWN
        assert result["errors"]


def test_an_altered_intermediate_limit_price_trips_the_kill_switch():
    limit_intent = dict(_INTENT, order_type="limit", limit_price=100.0)
    middle = _order("order-2", "replaced", replaced_by="order-3", replaces="order-1",
                    type="limit", limit_price=999.0)
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2", type="limit",
                          limit_price=100.0),
        "order-2": middle,
        "order-3": _order("order-3", "accepted", replaces="order-2", type="limit",
                          limit_price=100.0),
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = AssistantStore(Path(temp) / "a.db")
        proposal = _proposal()
        proposal["intent"] = limit_intent
        store.save_proposal(proposal)
        reconcile_nonterminal_orders(store, broker_module=_broker(orders))
        assert store.get_kill_switch()["active"] is True


def test_a_later_matching_order_cannot_erase_an_earlier_mismatch():
    """Validation must fail FAST -- the traversal stops at the bad hop rather
    than continuing to a matching final order that would mask it."""
    lookups: list = []
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": _order("order-2", "replaced", shares=999.0, replaced_by="order-3",
                          replaces="order-1"),
        "order-3": _order("order-3", "accepted", replaces="order-2"),
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        reconcile_nonterminal_orders(store, broker_module=_broker(orders, lookups=lookups))
        assert lookups == ["order-2"], (
            f"traversal must stop at the mismatch, not walk on to order-3 (got {lookups})"
        )
        assert store.get_kill_switch()["active"] is True


def test_an_intermediate_partial_fill_is_still_validated():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": _order("order-2", "replaced", shares=999.0, filled_qty=5.0,
                          filled_avg_price=100.0, replaced_by="order-3", replaces="order-1"),
        "order-3": _order("order-3", "accepted", replaces="order-2"),
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        reconcile_nonterminal_orders(store, broker_module=_broker(orders))
        assert store.get_kill_switch()["active"] is True, (
            "an altered intermediate that took real fills is the worst case, not an edge case"
        )


def test_the_broker_returning_a_different_order_id_is_unresolved():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": _order("order-99", "accepted", replaces="order-1"),
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(store, broker_module=_broker(orders))
        assert store.get_proposal("tp-ready")["status"] == SUBMISSION_UNKNOWN
        assert any("when asked for replacement" in e for e in result["errors"]), result["errors"]


def test_a_replacement_pointing_at_the_wrong_predecessor_is_unresolved():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": _order("order-2", "accepted", replaces="order-77"),
    }
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = _store(temp)
        result = reconcile_nonterminal_orders(store, broker_module=_broker(orders))
        assert store.get_proposal("tp-ready")["status"] == SUBMISSION_UNKNOWN
        assert any("claims to replace" in e for e in result["errors"]), result["errors"]


# --------------------------------------------------------------------------
# the shared resolver itself
# --------------------------------------------------------------------------

def test_resolver_reports_the_traversed_orders_and_error_kinds():
    orders = {
        "order-1": _order("order-1", "replaced", replaced_by="order-2"),
        "order-2": _order("order-2", "accepted", replaces="order-1"),
    }
    ok = resolve_replacement_chain(orders["order-1"], lambda oid: orders.get(oid))
    assert ok.error is None
    assert ok.authoritative_order["order_id"] == "order-2"
    assert ok.chain == ("order-2",)
    assert [o["order_id"] for o in ok.traversed_orders] == ["order-2"]
    assert ok.followed_a_replacement is True

    missing = resolve_replacement_chain(
        {**orders["order-1"], "replaced_by": "nope"}, lambda oid: None
    )
    assert missing.error_kind == CHAIN_ERROR_UNRESOLVED

    mismatched = resolve_replacement_chain(
        orders["order-1"], lambda oid: orders.get(oid),
        validate=lambda o: (False, "shares: expected 10, got 999"),
    )
    assert mismatched.error_kind == CHAIN_ERROR_IDENTITY_MISMATCH


def test_resolver_leaves_a_non_replaced_order_untouched():
    plain = _order("order-1", "accepted")
    out = resolve_replacement_chain(plain, lambda oid: pytest.fail("no lookup expected"))
    assert out.authoritative_order is plain
    assert out.chain == ()
    assert out.followed_a_replacement is False


def test_resolver_depth_bound_is_the_documented_constant():
    orders = {f"order-{i}": _order(
                  f"order-{i}", "replaced", replaced_by=f"order-{i + 1}",
                  replaces=f"order-{i - 1}" if i > 1 else None,
              )
              for i in range(1, 60)}
    out = resolve_replacement_chain(orders["order-1"], lambda oid: orders.get(oid))
    assert out.error_kind == CHAIN_ERROR_UNRESOLVED
    assert len(out.chain) == MAX_REPLACEMENT_CHAIN_DEPTH


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
