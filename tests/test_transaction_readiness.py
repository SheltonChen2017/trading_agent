from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

from assistant.order_lifecycle import journal_broker_order_update
from assistant.order_reconciler import (
    apply_broker_update,
    monitor_orders,
    reconcile_nonterminal_orders,
)
from assistant.policy import TradingPolicy
from assistant.readiness import transaction_readiness
from assistant.storage import AssistantStore


def _proposal(status: str = "submitting", proposal_id: str = "tp-ready") -> dict:
    return {
        "proposal_id": proposal_id,
        "created_at": "2026-07-29T14:00:00+00:00",
        "expires_at": "2026-07-30T14:00:00+00:00",
        "status": status,
        "idempotency_key": f"idem-{proposal_id}",
        "intent": {
            "ticker": "AAPL",
            "side": "buy",
            "shares": 10,
            "order_type": "market",
            "limit_price": None,
        },
    }


def _order(status: str, *, filled_qty: float = 0.0, updated_at: str | None = None) -> dict:
    return {
        "order_id": "order-1",
        "client_order_id": "idem-tp-ready",
        "ticker": "AAPL",
        "shares": 10.0,
        "side": "buy",
        "type": "market",
        "limit_price": None,
        "time_in_force": "day",
        "status": status,
        "filled_qty": filled_qty,
        "filled_avg_price": 100.0 if filled_qty else None,
        "submitted_at": "2026-07-29T14:00:00+00:00",
        "updated_at": updated_at,
    }


def test_order_lifecycle_is_fill_aware_idempotent_and_monotonic():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal())

        journal_broker_order_update(
            store, "tp-ready", _order("accepted"), event_type="new", external_event_id="event-new",
        )
        assert store.get_proposal("tp-ready")["status"] == "broker_accepted"

        journal_broker_order_update(
            store,
            "tp-ready",
            _order("partially_filled", filled_qty=4),
            event_type="partial_fill",
            external_event_id="event-partial",
            fill_qty=4,
            fill_price=100.0,
        )
        assert store.get_proposal("tp-ready")["status"] == "partially_filled"

        journal_broker_order_update(
            store,
            "tp-ready",
            _order("filled", filled_qty=10),
            event_type="fill",
            external_event_id="event-fill",
            fill_qty=6,
            fill_price=101.0,
        )
        assert store.get_proposal("tp-ready")["status"] == "filled"

        duplicate = journal_broker_order_update(
            store,
            "tp-ready",
            _order("filled", filled_qty=10),
            event_type="fill",
            external_event_id="event-fill",
            fill_qty=6,
            fill_price=101.0,
        )
        assert duplicate["broker_event_inserted"] is False

        stale = journal_broker_order_update(
            store,
            "tp-ready",
            _order("accepted"),
            event_type="new",
            external_event_id="late-accepted",
        )
        assert stale["broker_event_projected"] is False
        assert store.get_proposal("tp-ready")["status"] == "filled"
        assert store.list_broker_orders()[0]["order_status"] == "filled"
        assert len(store.list_broker_order_events(proposal_id="tp-ready")) == 4


def test_identity_mismatch_activates_persistent_kill_switch():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        proposal = _proposal()
        store.save_proposal(proposal)
        mismatched = {**_order("accepted"), "shares": 999}
        try:
            apply_broker_update(store, proposal, mismatched, event_type="poll")
            assert False, "expected identity mismatch"
        except Exception as exc:
            assert "mismatch" in str(exc).lower()
        assert store.get_proposal("tp-ready")["status"] == "submission_unknown"
        assert store.get_kill_switch()["active"] is True


def test_daily_budget_is_idempotent_and_confirmed_absence_releases_it():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal())
        first = store.reserve_execution_budget(
            "tp-ready",
            trading_day="2026-07-29",
            notional=1_000.0,
            max_daily_notional=1_000.0,
            max_daily_orders=1,
        )
        repeated = store.reserve_execution_budget(
            "tp-ready",
            trading_day="2026-07-29",
            notional=1_000.0,
            max_daily_notional=1_000.0,
            max_daily_orders=1,
        )
        assert first["already_reserved"] is False
        assert repeated["already_reserved"] is True
        transitioned = store.mark_submission_failed_and_release(
            "tp-ready",
            expected_statuses=("submitting",),
            error="broker confirmed absent",
        )
        assert transitioned["status"] == "submission_failed"
        assert store.get_execution_budget_usage("2026-07-29")["submitted_order_count"] == 0


def test_filled_notional_buckets_by_eastern_trading_day_not_utc_date():
    # Independent review, 2026-07-29: `trading_day` is an EASTERN market
    # date, but event_at is an absolute (normally UTC) timestamp. Matching
    # them by string prefix pushed any fill after 8:00pm Eastern onto the
    # next trading day, because that instant is already past midnight UTC.
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal(status="broker_accepted"))

        def record(event_id: str, event_at: str, qty: float, expected: tuple[str, ...]) -> None:
            store.project_broker_order_event(
                event_id=event_id,
                proposal_id="tp-ready",
                order={"order_id": "o1", "status": "filled", "filled_qty": qty, "filled_avg_price": 100.0},
                event_type="fill",
                event_at=event_at,
                new_proposal_status="filled",
                expected_current_statuses=expected,
                proposal_updates={},
                fill_qty=qty,
                fill_price=100.0,
            )

        # 21:00 Eastern on 2026-07-29 is 01:00 UTC on 2026-07-30.
        record("e-extended", "2026-07-30T01:00:00+00:00", 10.0, ("broker_accepted",))
        # 10:00 Eastern the same day is 14:00 UTC the same day.
        record("e-regular", "2026-07-29T14:00:00+00:00", 5.0, ("broker_accepted", "filled"))

        assert store.get_execution_budget_usage("2026-07-29")["filled_notional"] == 1_500.0
        assert store.get_execution_budget_usage("2026-07-30")["filled_notional"] == 0.0


def test_filled_notional_tolerates_an_unparseable_trading_day():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        assert store.get_execution_budget_usage("not-a-date")["filled_notional"] == 0.0


def test_poll_reconciliation_cancels_a_stale_accepted_order_without_repricing():
    class FakeBroker:
        canceled = []

        @staticmethod
        def find_order_by_client_id(client_order_id):
            return _order("accepted")

        @classmethod
        def cancel_order(cls, order_id):
            cls.canceled.append(order_id)
            return {"order_id": order_id, "status": "pending_cancel"}

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal(status="broker_accepted"))
        result = reconcile_nonterminal_orders(
            store,
            broker_module=FakeBroker,
            now=datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc),
            cancel_stale=True,
            max_order_age_minutes=30,
        )
        assert FakeBroker.canceled == ["order-1"]
        assert result["cancellation_requested"] == 1
        proposal = store.get_proposal("tp-ready")
        assert proposal["status"] == "cancel_pending"
        assert "limit_price" not in (proposal["broker_order"].get("cancel_request") or {})


def test_monitor_keeps_poll_fallback_while_stream_is_running():
    stop = Event()

    class FakeBroker:
        lookups = 0

        @classmethod
        def find_order_by_client_id(cls, client_order_id):
            cls.lookups += 1
            return _order("accepted")

        @staticmethod
        def run_trade_update_stream(callback):
            stop.wait(0.08)

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal())

        def stop_after_polls():
            if FakeBroker.lookups >= 2:
                stop.set()

        original_set_state = store.set_system_state

        def observing_set_state(key, value):
            original_set_state(key, value)
            stop_after_polls()

        store.set_system_state = observing_set_state
        monitor_orders(
            store,
            broker_module=FakeBroker,
            poll_interval_seconds=0.01,
            reconnect_delay_seconds=0.01,
            stop_event=stop,
        )
        assert FakeBroker.lookups >= 2


def test_readiness_requires_recent_error_free_reconciliation_and_inactive_kill_switch():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        now = datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc)
        store.set_system_state(
            "last_order_reconciliation",
            {"at": now.isoformat(), "checked": 0, "updated": 0, "error_count": 0},
        )
        policy = TradingPolicy(version="test", name="test", execution_mode="paper")
        report = transaction_readiness(
            store,
            policy,
            now=now,
            check_broker=False,
        )
        assert report["ready"] is True
        store.set_kill_switch(True, reason="test")
        assert transaction_readiness(
            store, policy, now=now, check_broker=False,
        )["ready"] is False


def test_database_backup_is_consistent_and_cannot_target_the_live_database():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal())
        backup = store.backup_to(Path(temp) / "backups" / "assistant.db")
        backup_store = AssistantStore(backup)
        assert backup_store.get_proposal("tp-ready") is not None
        try:
            store.backup_to(store.path)
            assert False, "expected same-file backup to fail"
        except ValueError:
            pass
