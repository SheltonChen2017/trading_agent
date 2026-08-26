"""Atomic containment for broker-reconciliation identity anomalies."""
from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Thread

import pytest

from assistant.proposal_status import FILLED, SUBMISSION_UNKNOWN, SUBMITTING
from assistant.dispatch_fence import execution_dispatch_fence
from assistant.storage import AssistantStore


def _proposal(proposal_id: str = "p-anomaly", *, status: str = SUBMITTING) -> dict:
    return {
        "proposal_id": proposal_id,
        "created_at": "2026-08-26T15:00:00+00:00",
        "expires_at": "2026-08-27T15:00:00+00:00",
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


def _seed(store: AssistantStore, proposal_id: str = "p-anomaly") -> None:
    store.save_proposal(_proposal(proposal_id))
    store.reserve_execution_budget(
        proposal_id,
        trading_day="2026-08-26",
        notional="1000.00",
        max_daily_notional="10000.00",
        max_daily_orders=10,
    )


def _contain(store: AssistantStore, proposal_id: str = "p-anomaly", **overrides):
    arguments = {
        "expected_statuses": (SUBMITTING, SUBMISSION_UNKNOWN),
        "reason": "broker order identity mismatch",
        "reconciled_at": "2026-08-26T15:01:00+00:00",
        "details": {"path": "test", "mismatch": "ticker"},
        "anomaly_key": "test_identity_mismatch",
    }
    arguments.update(overrides)
    return store.park_reconciliation_anomaly_and_halt(proposal_id, **arguments)


def test_anomaly_containment_parks_and_halts_without_releasing_reservation(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    _seed(store)

    result = _contain(store)

    proposal = store.get_proposal("p-anomaly")
    assert result["proposal_parked"] is True
    assert proposal["status"] == SUBMISSION_UNKNOWN
    assert proposal["error"] == "broker order identity mismatch"
    assert proposal["reconciled_at"] == "2026-08-26T15:01:00+00:00"
    assert store.get_kill_switch() == {
        "active": True,
        "reason": "broker order identity mismatch",
        "changed_at": "2026-08-26T15:01:00+00:00",
    }
    assert store.get_execution_budget_usage("2026-08-26")[
        "submitted_notional_decimal"
    ] == "1000"
    alerts = store.list_operational_alerts()
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "critical"
    assert alerts[0]["category"] == "broker_reconciliation"
    assert alerts[0]["details"] == {
        "anomaly_key": "test_identity_mismatch",
        "mismatch": "ticker",
        "path": "test",
        "proposal_id": "p-anomaly",
    }


def test_anomaly_containment_rolls_back_proposal_and_halt_when_alert_write_fails(
    tmp_path,
):
    store = AssistantStore(tmp_path / "assistant.db")
    _seed(store)
    store.set_kill_switch(False, reason="baseline")
    with store._connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER inject_atomic_anomaly_alert_failure
            BEFORE INSERT ON operational_alerts
            BEGIN
                SELECT RAISE(ABORT, 'injected atomic anomaly alert failure');
            END
            """
        )

    with pytest.raises(
        sqlite3.IntegrityError, match="injected atomic anomaly alert failure"
    ):
        _contain(store)

    assert store.get_proposal("p-anomaly")["status"] == SUBMITTING
    assert store.get_kill_switch()["active"] is False
    assert store.list_operational_alerts() == []
    assert store.get_execution_budget_usage("2026-08-26")[
        "submitted_notional_decimal"
    ] == "1000"


def test_same_anomaly_key_is_idempotent(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    _seed(store)

    first = _contain(store)
    second = _contain(
        store,
        reconciled_at="2026-08-26T15:02:00+00:00",
    )

    assert first["proposal_parked"] is True
    assert second["proposal_parked"] is False
    alerts = store.list_operational_alerts()
    assert len(alerts) == 1
    assert alerts[0]["occurrences"] == 1
    assert alerts[0]["first_seen_at"] == "2026-08-26T15:01:00+00:00"
    assert alerts[0]["last_seen_at"] == "2026-08-26T15:01:00+00:00"
    assert store.get_proposal("p-anomaly")["reconciled_at"] == (
        "2026-08-26T15:01:00+00:00"
    )


def test_simultaneous_anomaly_writers_create_one_containment_record(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    _seed(store)
    start = Barrier(2)

    def contain() -> dict:
        start.wait(timeout=5)
        return _contain(store, expected_statuses=(SUBMITTING,))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: contain(), range(2)))

    assert sorted(result["proposal_parked"] for result in results) == [False, True]
    assert store.get_proposal("p-anomaly")["status"] == SUBMISSION_UNKNOWN
    alerts = store.list_operational_alerts()
    assert len(alerts) == 1
    assert alerts[0]["occurrences"] == 1
    assert store.get_kill_switch()["active"] is True
    assert store.get_execution_budget_usage("2026-08-26")[
        "submitted_notional_decimal"
    ] == "1000"


def test_terminal_transition_wins_but_anomaly_still_halts_execution(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    _seed(store)
    store.update_proposal_status("p-anomaly", FILLED, filled_at="2026-08-26T15:00:30+00:00")

    result = _contain(store, expected_statuses=(SUBMITTING, SUBMISSION_UNKNOWN))

    assert result["proposal_parked"] is False
    assert store.get_proposal("p-anomaly")["status"] == FILLED
    assert store.get_kill_switch()["active"] is True
    assert len(store.list_operational_alerts()) == 1


def test_anomaly_halt_is_durable_before_it_drains_an_inflight_dispatch(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    _seed(store)
    dispatch_entered = Event()
    release_dispatch = Event()
    containment_returned = Event()

    def hold_dispatch_fence() -> None:
        with execution_dispatch_fence(store.path):
            dispatch_entered.set()
            assert release_dispatch.wait(timeout=5)

    def contain_anomaly() -> None:
        _contain(store)
        containment_returned.set()

    dispatcher = Thread(target=hold_dispatch_fence)
    dispatcher.start()
    assert dispatch_entered.wait(timeout=5)
    containment = Thread(target=contain_anomaly)
    containment.start()

    # BEGIN IMMEDIATE commits the halt before the containment path waits to
    # drain the already-fenced dispatch.  A queued dispatch therefore sees the
    # switch even though the first caller has not released its fence yet.
    for _ in range(100):
        if store.get_kill_switch().get("active"):
            break
        containment_returned.wait(timeout=0.01)
    assert store.get_kill_switch()["active"] is True
    assert containment_returned.is_set() is False

    release_dispatch.set()
    dispatcher.join(timeout=5)
    containment.join(timeout=5)
    assert not dispatcher.is_alive()
    assert not containment.is_alive()
    assert containment_returned.is_set() is True


@pytest.mark.parametrize(
    "bad_timestamp",
    ["", "2026-08-26T15:01:00", "not-a-time"],
)
def test_anomaly_containment_requires_an_aware_timestamp(tmp_path, bad_timestamp):
    store = AssistantStore(tmp_path / "assistant.db")
    _seed(store)

    with pytest.raises(ValueError, match="reconciled_at"):
        _contain(store, reconciled_at=bad_timestamp)

    assert store.get_proposal("p-anomaly")["status"] == SUBMITTING
    assert store.get_kill_switch().get("active") is not True
