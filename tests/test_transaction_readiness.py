from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

from assistant.execution_service import _execution_budget_notional
from assistant.dispatch_fence import (
    get_runtime_emergency_stop,
    runtime_emergency_stop_path,
)
from assistant.order_lifecycle import journal_broker_order_update
from assistant.order_reconciler import (
    apply_broker_update,
    monitor_orders,
    reconcile_nonterminal_orders,
)
from assistant.policy import TradingPolicy
from assistant.readiness import transaction_readiness
from assistant.storage import AssistantStore
from risk.execution_gate import TradeIntent

_ACCOUNT_ID = "paper-account-1"
_SNAPSHOT_ID = "a" * 64
_POLICY_FINGERPRINT = "b" * 64


def _broker_account() -> dict:
    return {"account_id": _ACCOUNT_ID, "paper": True}


def _proposal(status: str = "submitting", proposal_id: str = "tp-ready") -> dict:
    return {
        "proposal_id": proposal_id,
        "created_at": "2026-07-29T14:00:00+00:00",
        "expires_at": "2026-07-30T14:00:00+00:00",
        "status": status,
        "idempotency_key": f"idem-{proposal_id}",
        "broker_execution_context": {
            "account_id": _ACCOUNT_ID,
            "account_mode": "paper",
            "snapshot_id": _SNAPSHOT_ID,
            "policy_fingerprint": _POLICY_FINGERPRINT,
        },
        "intent": {
            "ticker": "AAPL",
            "side": "buy",
            "shares": 10,
            "order_type": "market",
            "limit_price": None,
        },
    }


def _order(status: str, *, filled_qty: float = 0.0, updated_at: str | None = None) -> dict:
    filled_price = 100.0 if filled_qty else None
    submitted_at = "2026-07-29T14:00:00+00:00"
    return {
        "order_id": "order-1",
        "client_order_id": "idem-tp-ready",
        "ticker": "AAPL",
        "asset_class": "us_equity",
        "order_class": "simple",
        "extended_hours": False,
        "legs": None,
        "shares": 10.0,
        "shares_decimal": "10",
        "notional": None,
        "notional_decimal": None,
        "side": "buy",
        "type": "market",
        "limit_price": None,
        "limit_price_decimal": None,
        "time_in_force": "day",
        "status": status,
        "filled_qty": filled_qty,
        "filled_qty_decimal": str(filled_qty),
        "filled_avg_price": filled_price,
        "filled_avg_price_decimal": None if filled_price is None else "100",
        "submitted_at": submitted_at,
        "updated_at": updated_at,
        "filled_at": submitted_at if status == "filled" else None,
        "canceled_at": submitted_at if status == "canceled" else None,
        "expired_at": submitted_at if status == "expired" else None,
        "failed_at": submitted_at if status == "rejected" else None,
        "replaced_at": submitted_at if status == "replaced" else None,
        "replaces": None,
        "replaced_by": None,
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


def test_broker_accepted_at_is_preserved_across_repeated_accepted_events():
    # Independent review, 2026-07-29: the original implementation read
    # store.get_proposal() to decide whether to preserve an existing
    # broker_accepted_at OUTSIDE project_broker_order_event()'s atomic
    # transaction -- under two near-simultaneous "accepted" events (e.g.
    # the poll loop and the trade-update stream both observing the same
    # transition), the second writer could read "not yet set" before the
    # first committed and clobber the first writer's timestamp with its
    # own. Simulated here with two accepted events carrying different
    # submitted_at values -- the first one written must win.
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal())

        first = dict(_order("accepted"), submitted_at="2026-07-29T14:00:00+00:00")
        journal_broker_order_update(store, "tp-ready", first, event_type="new", external_event_id="event-a")
        assert store.get_proposal("tp-ready")["broker_accepted_at"] == "2026-07-29T14:00:00+00:00"

        second = dict(_order("accepted"), submitted_at="2026-07-29T14:05:00+00:00")
        result = journal_broker_order_update(store, "tp-ready", second, event_type="new", external_event_id="event-b")
        assert result["broker_event_projected"] is True  # the second event did project (other fields update)...
        assert store.get_proposal("tp-ready")["broker_accepted_at"] == "2026-07-29T14:00:00+00:00"  # ...but not this one


def test_conditional_status_update_refuses_when_the_proposal_moved_on():
    # Mutation testing, 2026-07-29: removing the status guard in
    # update_proposal_status_if_current() failed no test, even though every
    # submission-error path in execution_service.py relies on it (each one
    # writes SUBMISSION_UNKNOWN only `if_current` in
    # submitting/submission_unknown/reconciling).
    #
    # Without the guard, a slow error path unwinding after reconciliation
    # already proved the order filled would rewrite a genuine fill to
    # "submission_unknown".
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal())
        store.update_proposal_status("tp-ready", "filled")

        result = store.update_proposal_status_if_current(
            "tp-ready",
            expected_statuses=("submitting", "submission_unknown", "reconciling"),
            new_status="submission_unknown",
            error="late network error unwinding after the fill was already confirmed",
        )

        assert result is None, "must not transition a proposal that already left the expected states"
        refreshed = store.get_proposal("tp-ready")
        assert refreshed["status"] == "filled"
        assert "error" not in refreshed or refreshed.get("error") is None

        # Sanity: the same call DOES apply from an expected state.
        store.update_proposal_status("tp-ready", "submitting")
        applied = store.update_proposal_status_if_current(
            "tp-ready",
            expected_statuses=("submitting",),
            new_status="submission_unknown",
            error="genuine ambiguity",
        )
        assert applied is not None
        assert store.get_proposal("tp-ready")["status"] == "submission_unknown"


def test_confirmed_absence_cannot_stomp_a_proposal_that_already_filled():
    # Mutation testing, 2026-07-29: removing the status guard in
    # mark_submission_failed_and_release() failed no test. Only its happy
    # path (a proposal still "submitting") was covered.
    #
    # The guard exists for the race where a slow "broker confirms no such
    # order" conclusion lands AFTER reconciliation already proved the order
    # filled. Without it, a real fill would be rewritten to
    # "submission_failed" AND its daily-budget reservation released --
    # under-counting genuine exposure.
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal())
        store.reserve_execution_budget(
            "tp-ready", trading_day="2026-07-29", notional=1_000.0,
            max_daily_notional=10_000.0, max_daily_orders=10,
        )
        store.update_proposal_status("tp-ready", "filled")

        result = store.mark_submission_failed_and_release(
            "tp-ready",
            expected_statuses=("submitting", "submission_unknown", "reconciling"),
            error="late 'broker confirms absent' arriving after the fill",
        )

        assert result is None, "a filled proposal must not be transitioned to submission_failed"
        assert store.get_proposal("tp-ready")["status"] == "filled"
        # The reservation must survive too -- a real fill still consumes budget.
        assert store.get_execution_budget_usage("2026-07-29")["submitted_order_count"] == 1


def test_a_lower_cumulative_fill_is_journaled_but_never_projected():
    # Mutation testing, 2026-07-29: replacing storage.py's
    # `quantity_allows_projection = incoming_filled >= current_filled`
    # with `True` did not fail any test. The existing monotonicity test
    # only sends a late *accepted* event, which the STATUS guard already
    # rejects -- so the quantity guard was never exercised.
    #
    # This is the case only the quantity guard catches: a second FILLED
    # event (a status transition that IS allowed from "filled") carrying a
    # LOWER cumulative filled_qty, e.g. an out-of-order redelivery. It must
    # still be journaled for auditability, but must never walk the recorded
    # fill backwards.
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal())
        journal_broker_order_update(
            store, "tp-ready", _order("accepted"), event_type="new", external_event_id="e-new",
        )
        journal_broker_order_update(
            store, "tp-ready", _order("filled", filled_qty=10), event_type="fill",
            external_event_id="e-fill-10", fill_qty=10, fill_price=100.0,
        )
        assert store.get_proposal("tp-ready")["broker_order"]["filled_qty"] == 10

        regressed = journal_broker_order_update(
            store, "tp-ready", _order("filled", filled_qty=6), event_type="fill",
            external_event_id="e-fill-6-late", fill_qty=6, fill_price=100.0,
        )
        # Journaled (audit trail preserved) but NOT projected.
        assert regressed["broker_event_inserted"] is True
        assert regressed["broker_event_projected"] is False
        # The authoritative record still shows the higher, real fill.
        assert store.get_proposal("tp-ready")["broker_order"]["filled_qty"] == 10
        assert store.get_proposal("tp-ready")["status"] == "filled"


def test_delayed_partial_fill_never_regresses_cancel_pending_state_or_event_time():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal())
        journal_broker_order_update(
            store,
            "tp-ready",
            _order(
                "partially_filled",
                filled_qty=4,
                updated_at="2026-07-29T15:00:00+00:00",
            ),
            event_type="partial_fill",
            external_event_id="partial-4",
        )
        journal_broker_order_update(
            store,
            "tp-ready",
            _order(
                "pending_cancel",
                filled_qty=4,
                updated_at="2026-07-29T15:02:00+00:00",
            ),
            event_type="pending_cancel",
            external_event_id="cancel-pending",
        )

        equal_late = journal_broker_order_update(
            store,
            "tp-ready",
            _order(
                "partially_filled",
                filled_qty=4,
                updated_at="2026-07-29T15:01:00+00:00",
            ),
            event_type="partial_fill",
            external_event_id="partial-4-delayed",
        )
        after_equal = store.get_proposal("tp-ready")
        assert equal_late["broker_event_inserted"] is True
        assert equal_late["broker_event_projected"] is False
        assert after_equal["status"] == "cancel_pending"
        assert after_equal["last_broker_event_at"] == "2026-07-29T15:02:00+00:00"

        # A genuinely larger cumulative fill still advances the quantity, but
        # it cannot erase the outstanding cancellation request or move the
        # last-event clock backward merely because delivery was delayed.
        greater_late = journal_broker_order_update(
            store,
            "tp-ready",
            _order(
                "partially_filled",
                filled_qty=6,
                updated_at="2026-07-29T15:01:30+00:00",
            ),
            event_type="partial_fill",
            external_event_id="partial-6-delayed",
        )
        final = store.get_proposal("tp-ready")
        assert greater_late["broker_event_projected"] is True
        assert final["status"] == "cancel_pending"
        assert final["broker_order"]["filled_qty"] == 6
        assert final["last_broker_event_at"] == "2026-07-29T15:02:00+00:00"


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


def test_execution_budget_uses_the_gate_price_for_buy_and_sell_limits():
    buy = TradeIntent(
        ticker="AAPL",
        side="buy",
        shares=10,
        order_type="limit",
        limit_price=110.0,
    )
    sell = TradeIntent(
        ticker="AAPL",
        side="sell",
        shares=10,
        order_type="limit",
        limit_price=110.0,
    )

    assert _execution_budget_notional(buy, 100.0) == 1_100.0
    assert _execution_budget_notional(sell, 100.0) == 1_000.0


def test_broker_rejection_keeps_the_submitted_order_budget_consumed():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal())
        store.reserve_execution_budget(
            "tp-ready",
            trading_day="2026-07-29",
            notional=1_000.0,
            max_daily_notional=10_000.0,
            max_daily_orders=10,
        )

        journal_broker_order_update(
            store,
            "tp-ready",
            _order("rejected"),
            event_type="rejected",
            external_event_id="rejected-order-event",
        )

        usage = store.get_execution_budget_usage("2026-07-29")
        assert store.get_proposal("tp-ready")["status"] == "broker_rejected"
        assert usage["submitted_order_count"] == 1
        assert usage["submitted_notional"] == 1_000.0


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
        PAPER_TRADING = True
        account_mode = "paper"
        canceled = []

        @staticmethod
        def get_account():
            return _broker_account()

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
        PAPER_TRADING = True
        account_mode = "paper"
        lookups = 0

        @staticmethod
        def get_account():
            return _broker_account()

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


def test_readiness_refuses_corrupt_non_authoritative_fill_ledger():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        now = datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc)
        store.save_proposal(_proposal(status="broker_accepted"))
        journal_broker_order_update(
            store,
            "tp-ready",
            _order(
                "partially_filled",
                filled_qty=1,
                updated_at="2026-07-29T14:30:00+00:00",
            ),
            event_type="partial_fill",
            event_at="2026-07-29T14:30:00+00:00",
            external_event_id="readiness-corrupt-fill",
            fill_qty=1,
            fill_price=100,
        )
        with closing(sqlite3.connect(store.path)) as connection:
            connection.execute("DROP TRIGGER broker_order_events_append_only_update")
            connection.execute("DROP TRIGGER broker_order_events_append_only_delete")
            connection.execute(
                "UPDATE broker_order_events SET fill_qty_text = 'NaN' "
                "WHERE event_id = 'readiness-corrupt-fill'"
            )
            connection.commit()
        store.set_system_state(
            "last_order_reconciliation",
            {"at": now.isoformat(), "checked": 1, "updated": 1, "error_count": 0},
        )

        report = transaction_readiness(
            store,
            TradingPolicy(version="test", name="test", execution_mode="paper"),
            now=now,
            check_broker=False,
        )

        check = next(
            item for item in report["checks"]
            if item["name"] == "fill_ledger_integrity"
        )
        assert report["ready"] is False
        assert check["ok"] is False
        assert "readiness-corrupt-fill" in check["detail"]


def test_readiness_treats_unreadable_runtime_stop_as_active():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        now = datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc)
        store.set_system_state(
            "last_order_reconciliation",
            {"at": now.isoformat(), "checked": 0, "updated": 0, "error_count": 0},
        )
        path = runtime_emergency_stop_path(store.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not-json", encoding="utf-8")

        report = transaction_readiness(
            store,
            TradingPolicy(version="test", name="test", execution_mode="paper"),
            now=now,
            check_broker=False,
        )

        check = next(
            item for item in report["checks"]
            if item["name"] == "runtime_emergency_stop"
        )
        assert report["ready"] is False
        assert check["ok"] is False
        assert "unreadable" in check["detail"]


def test_database_integrity_orphan_activates_runtime_containment(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TRIGGER fk_broker_orders_proposal_insert")
        connection.execute(
            "INSERT INTO broker_orders(order_id, proposal_id, submitted_at, "
            "status, payload_json) VALUES (?, ?, ?, ?, ?)",
            (
                "orphan-order",
                "missing-proposal",
                "2026-08-26T12:00:00+00:00",
                "accepted",
                "{}",
            ),
        )

    results = store.database_integrity_check()

    assert any("broker_orders.proposal_id" in item for item in results)
    assert get_runtime_emergency_stop(store.path)["active"] is True


def test_database_integrity_scan_exception_activates_runtime_containment(
    tmp_path, monkeypatch
):
    store = AssistantStore(tmp_path / "assistant.db")

    def failed_integrity_scan(_connection):
        raise sqlite3.DatabaseError("database image is unreadable")

    monkeypatch.setattr(store, "_integrity_results", failed_integrity_scan)

    results = store.database_integrity_check()

    assert results == [
        "database integrity check could not complete: DatabaseError: "
        "database image is unreadable"
    ]
    assert store.get_kill_switch()["active"] is True
    assert get_runtime_emergency_stop(store.path)["active"] is True
    assert store.get_kill_switch()["active"] is True


def test_readiness_reports_malformed_persistent_kill_switch_as_blocked():
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        now = datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc)
        store.set_system_state(
            "last_order_reconciliation",
            {"at": now.isoformat(), "checked": 0, "updated": 0, "error_count": 0},
        )
        store.set_system_state(
            "kill_switch",
            {
                "active": "false",
                "reason": "corrupt string boolean",
                "changed_at": now.isoformat(),
            },
        )

        report = transaction_readiness(
            store,
            TradingPolicy(version="test", name="test", execution_mode="paper"),
            now=now,
            check_broker=False,
        )

        check = next(
            item for item in report["checks"]
            if item["name"] == "persistent_kill_switch"
        )
        assert report["ready"] is False
        assert check["ok"] is False
        assert "unreadable" in check["detail"]


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


def test_readiness_is_not_ready_when_the_open_order_budget_is_exactly_full():
    """Readiness answers "can ANOTHER order be submitted", and
    execution_service refuses at `>= max_open_orders`. With `<=` here,
    readiness reported ready=True at a full budget while execution would
    correctly refuse (GPT review, 2026-07-29)."""
    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        now = datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc)
        store.set_system_state(
            "last_order_reconciliation",
            {"at": now.isoformat(), "checked": 0, "updated": 0, "error_count": 0},
        )
        policy = TradingPolicy(
            version="test", name="test", execution_mode="paper", max_open_orders=1,
        )
        # No active orders yet -> ready.
        assert transaction_readiness(store, policy, now=now, check_broker=False)["ready"] is True

        store.save_proposal(_proposal(status="broker_accepted", proposal_id="tp-active"))
        report = transaction_readiness(store, policy, now=now, check_broker=False)
        budget = next(c for c in report["checks"] if c["name"] == "active_order_budget")
        assert budget["ok"] is False, (
            "1 active order against a cap of 1 leaves no room for another order, so readiness "
            "must not report ready."
        )
        assert report["ready"] is False
        assert "room for 0 more" in budget["detail"]


def test_a_replaced_order_becomes_submission_unknown_not_cancel_pending():
    """`replaced` is terminal for that order id -- the replacement is a
    separate order. Treating it as cancel-pending parked the proposal forever
    on a state that could never change while the replacement might fill
    (GPT review, 2026-07-29)."""
    from assistant.order_lifecycle import proposal_status_for_order
    from assistant.proposal_status import SUBMISSION_UNKNOWN

    assert proposal_status_for_order(_order("replaced")) == SUBMISSION_UNKNOWN
    # pending_replace is genuinely still in-flight and stays cancel-pending.
    assert proposal_status_for_order(_order("pending_replace")) == "cancel_pending"


def test_a_replaced_order_actually_transitions_a_live_proposal():
    """The status mapping alone is not enough: SUBMISSION_UNKNOWN also has to
    be a LEGAL transition out of broker_accepted, or the conditional update
    silently no-ops and the proposal stays parked anyway."""
    from assistant.proposal_status import SUBMISSION_UNKNOWN

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal(status="broker_accepted"))
        journal_broker_order_update(
            store, "tp-ready", _order("replaced"), event_type="replaced",
        )
        assert store.get_proposal("tp-ready")["status"] == SUBMISSION_UNKNOWN


def test_reconciliation_follows_the_replacement_chain_to_the_original_proposal():
    """A replacement arrives with a NEW order id and client_order_id, so
    neither existing lookup could find the proposal it superseded and the
    update was dropped. `replaces` carries the original order id."""
    from assistant.order_reconciler import _proposal_for_update

    with tempfile.TemporaryDirectory() as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal(status="broker_accepted"))
        # Register the ORIGINAL order against the proposal.
        journal_broker_order_update(
            store, "tp-ready", _order("accepted"), event_type="accepted",
        )

        replacement = _order("accepted")
        replacement["order_id"] = "order-2"
        replacement["client_order_id"] = "some-other-client-id"
        replacement["replaces"] = "order-1"

        found = _proposal_for_update(store, replacement)
        assert found is not None, (
            "the replacement must resolve back to the proposal it superseded via `replaces`"
        )
        assert found["proposal_id"] == "tp-ready"


def test_stop_event_interrupts_a_healthy_connected_stream_promptly():
    """monitor_orders() used to call the blocking stream on its own thread, so
    a HEALTHY stream made stop_event unable to interrupt shutdown at all -- a
    stop requested at 0.05s did not return until the stream ended (GPT review,
    2026-07-29). The stream now runs on its own thread."""
    import time
    from threading import Timer

    stop = Event()
    # `release` is controlled ONLY by this test and is deliberately NOT the stop
    # event: the fake stream ignores `stop` entirely, exactly like a real
    # healthy connected stream. Because release is set only AFTER
    # monitor_orders() returns, the pre-fix inline-blocking version literally
    # cannot return before the timeout -- so the regression shows up as a full
    # STREAM_TIMEOUT wait rather than as a few milliseconds of drift. That
    # makes the assertion below insensitive to machine load, which a bare
    # wall-clock threshold against a fixed sleep was not.
    release = Event()
    STREAM_TIMEOUT = 10.0

    class BlockingStreamBroker:
        PAPER_TRADING = True
        account_mode = "paper"

        @staticmethod
        def get_account():
            return _broker_account()

        @staticmethod
        def find_order_by_client_id(client_order_id):
            return _order("accepted")

        @staticmethod
        def run_trade_update_stream(callback):
            release.wait(STREAM_TIMEOUT)

    # ignore_cleanup_errors: the stream/poll threads are daemons that may still
    # hold the SQLite file for a moment after monitor_orders() returns, and on
    # Windows that makes the temp-dir unlink fail with PermissionError -- a
    # teardown artifact, not a behaviour under test.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        store = AssistantStore(Path(temp) / "assistant.db")
        store.save_proposal(_proposal())

        Timer(0.05, stop.set).start()
        started = time.monotonic()
        try:
            monitor_orders(
                store,
                broker_module=BlockingStreamBroker,
                poll_interval_seconds=0.01,
                reconnect_delay_seconds=0.01,
                stop_event=stop,
            )
            elapsed = time.monotonic() - started
        finally:
            # Let the stream thread end so it stops holding the temp database.
            release.set()
            time.sleep(0.05)

    assert elapsed < 2.0, (
        f"monitor_orders took {elapsed:.2f}s to honour stop_event; it must not wait for the "
        "stream to end on its own."
    )


def test_partially_filled_buys_only_reserve_their_unfilled_remainder():
    """The filled portion of a partial fill is already in positions, so
    counting the ORIGINAL quantity as pending double-counts it and can block
    unrelated purchases that are within policy (GPT review, 2026-07-29)."""
    from assistant.execution_service import _pending_buy_value_by_ticker

    class NoQuoteBroker:
        @staticmethod
        def get_latest_quote(ticker):
            raise AssertionError("a limit order must not need a live quote")

    order = {
        "ticker": "AAPL", "side": "buy", "shares": 10.0,
        "filled_qty": 4.0, "filled_avg_price": 100.0, "limit_price": 100.0,
    }
    totals = _pending_buy_value_by_ticker([order], NoQuoteBroker)
    assert totals == {"AAPL": 600.0}, (
        f"only the 6 unfilled shares are still pending, expected 600.0, got {totals}"
    )


def test_a_fully_filled_order_reserves_nothing_and_nan_fails_closed():
    from assistant.execution_service import _pending_buy_value_by_ticker

    class NoQuoteBroker:
        @staticmethod
        def get_latest_quote(ticker):
            raise AssertionError("should not be reached")

    filled = {
        "ticker": "AAPL", "side": "buy", "shares": 10.0,
        "filled_qty": 10.0, "filled_avg_price": 100.0, "limit_price": 100.0,
    }
    assert _pending_buy_value_by_ticker([filled], NoQuoteBroker) == {}

    # A NaN filled_qty must fall back to counting the FULL order (conservative:
    # overstates pending exposure and blocks more), never produce a NaN total.
    corrupt = dict(filled, filled_qty=float("nan"))
    assert _pending_buy_value_by_ticker([corrupt], NoQuoteBroker) == {"AAPL": 1000.0}
