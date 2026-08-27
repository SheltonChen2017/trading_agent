from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier, Event, Thread

import pytest

from assistant.dispatch_fence import (
    execution_dispatch_fence,
    get_runtime_emergency_stop,
)
from assistant.order_lifecycle import broker_event_id, journal_broker_order_update
from assistant.storage import AssistantStore, JournalTransactionConflictError
from execution.alpaca_broker import (
    BrokerPreflightError,
    _normalized_trade_update_numbers,
)


_AT = "2026-01-05T15:00:00+00:00"


def _proposal(status: str = "broker_accepted") -> dict:
    return {
        "proposal_id": "proposal-1",
        "created_at": "2026-01-05T14:59:00+00:00",
        "expires_at": "2026-01-06T14:59:00+00:00",
        "status": status,
        "idempotency_key": "idem-proposal-1",
        "intent": {
            "ticker": "AAPL",
            "side": "buy",
            "shares": 1,
            "order_type": "market",
            "limit_price": None,
        },
        "broker_execution_context": {
            "account_id": "paper-account-1",
            "account_mode": "paper",
            "snapshot_id": "a" * 64,
            "policy_fingerprint": "b" * 64,
        },
    }


def _order(
    status: str,
    *,
    filled_qty_decimal: str,
    filled_avg_price_decimal: str,
    updated_at: str = _AT,
) -> dict:
    return {
        "order_id": "order-1",
        "client_order_id": "idem-proposal-1",
        "ticker": "AAPL",
        "shares": 1.0,
        "shares_decimal": "1",
        "side": "buy",
        "type": "market",
        "limit_price": None,
        "time_in_force": "day",
        "status": status,
        "filled_qty": float(filled_qty_decimal),
        "filled_qty_decimal": filled_qty_decimal,
        "filled_avg_price": float(filled_avg_price_decimal),
        "filled_avg_price_decimal": filled_avg_price_decimal,
        "submitted_at": "2026-01-05T14:59:30+00:00",
        "updated_at": updated_at,
        "filled_at": updated_at if status == "filled" else None,
    }


def _journal_exact(
    store: AssistantStore,
    order: dict,
    *,
    event_id: str,
    event_at: str = _AT,
    fill_qty_decimal: str | None = None,
    fill_price_decimal: str | None = None,
    extra_raw: dict | None = None,
):
    raw = {
        "event": "fill",
        "event_id": event_id,
        "event_at": event_at,
        "fill_qty": (
            None if fill_qty_decimal is None else float(fill_qty_decimal)
        ),
        "fill_qty_decimal": fill_qty_decimal,
        "fill_price": (
            None if fill_price_decimal is None else float(fill_price_decimal)
        ),
        "fill_price_decimal": fill_price_decimal,
        "order": order,
        **(extra_raw or {}),
    }
    return journal_broker_order_update(
        store,
        "proposal-1",
        order,
        event_type="fill",
        event_at=event_at,
        external_event_id=event_id,
        fill_qty=raw["fill_qty"],
        fill_price=raw["fill_price"],
        raw_event=raw,
    )


@pytest.fixture
def store(tmp_path: Path) -> AssistantStore:
    result = AssistantStore(tmp_path / "assistant.db")
    result.save_proposal(_proposal())
    return result


def test_fallback_event_id_normalizes_equivalent_timestamp_spellings(
    store: AssistantStore,
):
    order = _order(
        "partially_filled",
        filled_qty_decimal="0.5",
        filled_avg_price_decimal="100",
    )
    utc_z = "2026-01-05T15:00:00Z"
    eastern_offset = "2026-01-05T10:00:00-05:00"

    assert broker_event_id(order, event_type="partial_fill", event_at=utc_z) == (
        broker_event_id(order, event_type="partial_fill", event_at=eastern_offset)
    )

    first = journal_broker_order_update(
        store,
        "proposal-1",
        order,
        event_type="partial_fill",
        event_at=utc_z,
        fill_qty="0.5",
        fill_price="100",
    )
    replay = journal_broker_order_update(
        store,
        "proposal-1",
        order,
        event_type="partial_fill",
        event_at=eastern_offset,
        fill_qty="0.5",
        fill_price="100",
    )

    assert first["broker_event_inserted"] is True
    assert replay["broker_event_inserted"] is False
    assert replay["broker_event_replay"] is True
    assert len(store.list_broker_order_events()) == 1


@pytest.mark.parametrize(
    "trigger_sql",
    [
        (
            "CREATE TRIGGER duplicate_broker_event_row "
            "AFTER INSERT ON broker_order_events "
            "WHEN NEW.event_id NOT LIKE 'shadow:%' BEGIN "
            "INSERT INTO broker_order_events("
            "event_id, order_id, proposal_id, event_type, event_at, status, payload_json"
            ") VALUES ("
            "'shadow:' || NEW.event_id, NEW.order_id, NEW.proposal_id, "
            "NEW.event_type, NEW.event_at, NEW.status, NEW.payload_json"
            "); END"
        ),
        (
            "CREATE TRIGGER mutate_event_after_projection "
            "AFTER UPDATE ON trade_proposals BEGIN "
            "UPDATE broker_order_events SET status = 'tampered' "
            "WHERE proposal_id = NEW.proposal_id; END"
        ),
    ],
    ids=("extra-ledger-row", "post-insert-mutation"),
)
def test_event_projection_rolls_back_unexpected_trigger_side_effects(
    store: AssistantStore, trigger_sql: str
):
    with sqlite3.connect(store.path) as connection:
        connection.execute(trigger_sql)
    order = _order(
        "partially_filled",
        filled_qty_decimal="0.5",
        filled_avg_price_decimal="100",
    )

    with pytest.raises(
        JournalTransactionConflictError,
        match="exactly one immutable canonical ledger row|append-only",
    ):
        _journal_exact(
            store,
            order,
            event_id="triggered-event",
            fill_qty_decimal="0.5",
            fill_price_decimal="100",
        )

    assert store.list_broker_order_events() == []
    assert store.list_broker_orders() == []
    assert store.get_proposal("proposal-1")["status"] == "broker_accepted"


def test_provider_decimal_text_survives_restart_and_drives_fill_reconstruction(
    store: AssistantStore,
):
    quantity = "0.123456789123456789"
    price = "100.000000000000000019"
    order = _order(
        "partially_filled",
        filled_qty_decimal=quantity,
        filled_avg_price_decimal=price,
    )

    _journal_exact(
        store,
        order,
        event_id="execution-1",
        fill_qty_decimal=quantity,
        fill_price_decimal=price,
    )
    reopened = AssistantStore(store.path)

    event = reopened.list_broker_order_events()[0]
    assert event["filled_qty_decimal"] == quantity
    assert event["filled_avg_price_decimal"] == price
    assert event["fill_qty_decimal"] == quantity
    assert event["fill_price_decimal"] == price
    assert event["numeric_evidence_status"] == "provider_exact"
    assert len(event["event_content_hash"]) == 64

    fill = reopened.list_fills()[0]
    assert fill["qty_decimal"] == quantity
    assert fill["price_decimal"] == price
    assert fill["numeric_evidence_status"] == "provider_exact"


def test_stream_normalizer_never_labels_binary_float_digits_as_provider_exact():
    normalized = _normalized_trade_update_numbers(
        fill_qty=0.1,
        fill_price=100.25,
    )
    assert normalized == {
        "fill_qty": 0.1,
        "fill_qty_decimal": None,
        "fill_price": 100.25,
        "fill_price_decimal": None,
    }


@pytest.mark.parametrize(
    "fill_qty,fill_price",
    [
        (None, "100"),
        ("1", None),
        ("NaN", "100"),
        ("Infinity", "100"),
        ("-1", "100"),
        ("1", "0"),
    ],
)
def test_stream_normalizer_rejects_incomplete_or_malformed_fill_evidence(
    fill_qty,
    fill_price,
):
    with pytest.raises(BrokerPreflightError):
        _normalized_trade_update_numbers(
            fill_qty=fill_qty,
            fill_price=fill_price,
        )


def test_mixed_stream_and_poll_remainder_uses_exact_decimal_text(
    store: AssistantStore,
):
    partial = _order(
        "partially_filled",
        filled_qty_decimal="0.100000000000000001",
        filled_avg_price_decimal="3.000000000000000001",
    )
    _journal_exact(
        store,
        partial,
        event_id="stream-partial",
        fill_qty_decimal="0.100000000000000001",
        fill_price_decimal="3.000000000000000001",
    )
    final = _order(
        "filled",
        filled_qty_decimal="1.000000000000000000",
        filled_avg_price_decimal="4.000000000000000000",
        updated_at="2026-01-05T15:01:00+00:00",
    )
    _journal_exact(
        store,
        final,
        event_id="poll-final",
        event_at="2026-01-05T15:01:00+00:00",
    )

    fills = store.list_fills()
    assert [fill["qty_decimal"] for fill in fills] == [
        "0.100000000000000001",
        "0.899999999999999999",
    ]
    assert fills[1]["price_decimal"] == "4.111111111111111112234567901"


def test_exact_event_replay_is_a_noop_and_never_reprojects_caller_state(
    store: AssistantStore,
):
    order = _order(
        "partially_filled",
        filled_qty_decimal="0.4",
        filled_avg_price_decimal="100.25",
    )
    first = _journal_exact(
        store,
        order,
        event_id="same-event",
        fill_qty_decimal="0.4",
        fill_price_decimal="100.25",
    )
    before = store.get_proposal("proposal-1")

    replay = _journal_exact(
        store,
        order,
        event_id="same-event",
        fill_qty_decimal="0.4",
        fill_price_decimal="100.25",
    )

    assert first["broker_event_inserted"] is True
    assert replay["broker_event_inserted"] is False
    assert replay["broker_event_projected"] is False
    assert store.get_proposal("proposal-1") == before
    assert len(store.list_broker_order_events()) == 1


def test_broker_event_rows_are_database_append_only(store: AssistantStore):
    order = _order(
        "partially_filled",
        filled_qty_decimal="0.4",
        filled_avg_price_decimal="100.25",
    )
    _journal_exact(
        store,
        order,
        event_id="immutable-event",
        fill_qty_decimal="0.4",
        fill_price_decimal="100.25",
    )
    with sqlite3.connect(store.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE broker_order_events SET status = 'tampered' "
                "WHERE event_id = 'immutable-event'"
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM broker_order_events WHERE event_id = 'immutable-event'"
            )


def test_current_event_with_deleted_integrity_metadata_is_rejected_not_downgraded(
    store: AssistantStore,
):
    order = _order(
        "partially_filled",
        filled_qty_decimal="0.4",
        filled_avg_price_decimal="100.25",
    )
    _journal_exact(
        store,
        order,
        event_id="legacy-replay",
        fill_qty_decimal="0.4",
        fill_price_decimal="100.25",
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TRIGGER broker_order_events_append_only_update")
        connection.execute("DROP TRIGGER broker_order_events_append_only_delete")
        connection.execute(
            "UPDATE broker_order_events SET event_content_hash = NULL, "
            "event_content_json = NULL, event_hash_version = NULL "
            "WHERE event_id = 'legacy-replay'"
        )

    with pytest.raises(
        JournalTransactionConflictError,
        match="missing or unknown event_hash_version|missing event_content_json",
    ):
        AssistantStore(store.path)
    assert get_runtime_emergency_stop(store.path)["active"] is True


def test_pre_metadata_schema_receives_one_time_legacy_backfill(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE trade_proposals (
                proposal_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL, status TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE, payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE broker_orders (
                order_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL,
                submitted_at TEXT NOT NULL, status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE broker_order_events (
                event_id TEXT PRIMARY KEY, order_id TEXT NOT NULL,
                proposal_id TEXT NOT NULL, event_type TEXT NOT NULL,
                event_at TEXT NOT NULL, status TEXT NOT NULL,
                filled_qty REAL, filled_avg_price REAL, fill_qty REAL,
                fill_price REAL, payload_json TEXT NOT NULL
            );
            """
        )
        proposal = _proposal()
        connection.execute(
            "INSERT INTO trade_proposals VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                proposal["proposal_id"], proposal["created_at"],
                proposal["expires_at"], proposal["status"],
                proposal["idempotency_key"], json.dumps(proposal), _AT,
            ),
        )
        order = _order(
            "partially_filled",
            filled_qty_decimal="0.4",
            filled_avg_price_decimal="100.25",
        )
        connection.execute(
            "INSERT INTO broker_orders VALUES (?, ?, ?, ?, ?)",
            ("order-1", "proposal-1", _AT, "partially_filled", json.dumps(order)),
        )
        payload = {
            "event": "fill",
            "fill_qty_decimal": "0.4",
            "fill_price_decimal": "100.25",
            "order": order,
        }
        connection.execute(
            "INSERT INTO broker_order_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-event", "order-1", "proposal-1", "fill", _AT,
                "partially_filled", 0.4, 100.25, 0.4, 100.25,
                json.dumps(payload),
            ),
        )

    migrated = AssistantStore(path)
    event = migrated.list_broker_order_events()[0]
    assert event["event_hash_version"] == "legacy_v1"
    with sqlite3.connect(path) as connection:
        marker_count = connection.execute(
            "SELECT COUNT(*) FROM storage_migrations WHERE migration_id = ?",
            ("broker_order_event_integrity_v1",),
        ).fetchone()[0]
    assert marker_count == 1
    AssistantStore(path)


@pytest.mark.parametrize(
    "mutation",
    ("status_and_quantity", "time", "incremental_price", "normalized_payload"),
)
def test_same_event_id_with_changed_content_halts_without_projecting(
    store: AssistantStore,
    mutation: str,
):
    partial = _order(
        "partially_filled",
        filled_qty_decimal="0.4",
        filled_avg_price_decimal="100.25",
    )
    _journal_exact(
        store,
        partial,
        event_id="colliding-event",
        fill_qty_decimal="0.4",
        fill_price_decimal="100.25",
    )
    before = store.get_proposal("proposal-1")
    changed = dict(partial)
    event_at = _AT
    incremental_price = "100.25"
    extra_raw = None
    if mutation == "status_and_quantity":
        changed = _order(
            "filled",
            filled_qty_decimal="1",
            filled_avg_price_decimal="101",
        )
    elif mutation == "time":
        event_at = "2026-01-05T15:01:00+00:00"
    elif mutation == "incremental_price":
        incremental_price = "100.26"
    else:
        extra_raw = {"provider_sequence": "changed"}

    with pytest.raises(JournalTransactionConflictError, match="changed content"):
        _journal_exact(
            store,
            changed,
            event_id="colliding-event",
            event_at=event_at,
            fill_qty_decimal=(
                changed["filled_qty_decimal"]
                if mutation == "status_and_quantity"
                else "0.4"
            ),
            fill_price_decimal=incremental_price,
            extra_raw=extra_raw,
        )

    after = store.get_proposal("proposal-1")
    assert after["status"] == before["status"]
    assert after["broker_order"] == before["broker_order"]
    assert len(store.list_broker_order_events()) == 1
    assert store.get_kill_switch()["active"] is True
    alerts = store.list_operational_alerts(status="open")
    assert any(alert["category"] == "broker_event_integrity" for alert in alerts)


def test_same_provider_event_id_in_a_different_account_scope_halts(
    store: AssistantStore,
):
    first = _order(
        "partially_filled",
        filled_qty_decimal="0.4",
        filled_avg_price_decimal="100",
    )
    _journal_exact(
        store,
        first,
        event_id="provider-id",
        fill_qty_decimal="0.4",
        fill_price_decimal="100",
    )
    foreign = _proposal()
    foreign.update(
        proposal_id="proposal-2",
        idempotency_key="idem-proposal-2",
        broker_execution_context={
            **foreign["broker_execution_context"],
            "account_id": "paper-account-2",
        },
    )
    store.save_proposal(foreign)
    foreign_order = {
        **first,
        "order_id": "order-2",
        "client_order_id": "idem-proposal-2",
    }
    with pytest.raises(JournalTransactionConflictError):
        journal_broker_order_update(
            store,
            "proposal-2",
            foreign_order,
            event_type="fill",
            event_at=_AT,
            external_event_id="provider-id",
            fill_qty="0.4",
            fill_price="100",
            raw_event={
                "event": "fill",
                "event_id": "provider-id",
                "event_at": _AT,
                "fill_qty_decimal": "0.4",
                "fill_price_decimal": "100",
                "order": foreign_order,
            },
        )
    assert store.get_proposal("proposal-2")["status"] == "broker_accepted"
    assert store.get_kill_switch()["active"] is True


def test_collision_alert_failure_keeps_global_and_local_containment_active(
    store: AssistantStore,
):
    partial = _order(
        "partially_filled",
        filled_qty_decimal="0.4",
        filled_avg_price_decimal="100",
    )
    _journal_exact(
        store,
        partial,
        event_id="faulted-collision",
        fill_qty_decimal="0.4",
        fill_price_decimal="100",
    )
    before = store.get_proposal("proposal-1")
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "CREATE TRIGGER fail_broker_event_alert BEFORE INSERT ON operational_alerts "
            "WHEN NEW.category = 'broker_event_integrity' BEGIN "
            "SELECT RAISE(ABORT, 'injected alert failure'); END"
        )

    changed = _order(
        "filled",
        filled_qty_decimal="1",
        filled_avg_price_decimal="101",
    )
    with pytest.raises(
        JournalTransactionConflictError,
        match="reused with changed content",
    ):
        _journal_exact(
            store,
            changed,
            event_id="faulted-collision",
            fill_qty_decimal="1",
            fill_price_decimal="101",
        )

    assert store.get_proposal("proposal-1") == before
    assert store.get_kill_switch()["active"] is True
    assert get_runtime_emergency_stop(store.path)["active"] is True
    assert store.list_operational_alerts() == []
    assert len(store.list_broker_order_events()) == 1


def test_concurrent_changed_content_collision_keeps_one_coherent_projection(
    store: AssistantStore,
):
    barrier = Barrier(2)
    orders = (
        _order(
            "partially_filled",
            filled_qty_decimal="0.4",
            filled_avg_price_decimal="100",
        ),
        _order(
            "filled",
            filled_qty_decimal="1",
            filled_avg_price_decimal="101",
        ),
    )

    def write(order: dict):
        barrier.wait()
        return _journal_exact(
            store,
            order,
            event_id="racing-event",
            fill_qty_decimal=order["filled_qty_decimal"],
            fill_price_decimal=order["filled_avg_price_decimal"],
        )

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(write, order) for order in orders]
        for future in futures:
            try:
                outcomes.append(future.result())
            except JournalTransactionConflictError as exc:
                outcomes.append(exc)

    assert sum(isinstance(outcome, JournalTransactionConflictError) for outcome in outcomes) == 1
    event = store.list_broker_order_events()[0]
    projected = store.get_proposal("proposal-1")["broker_order"]
    assert projected["status"] == event["status"]
    assert projected["filled_qty_decimal"] == event["filled_qty_decimal"]
    assert store.get_kill_switch()["active"] is True


@pytest.mark.parametrize(
    "event_at,fill_qty,fill_price",
    [
        ("not-a-time", "1", "100"),
        ("2026-01-05T15:00:00", "1", "100"),
        ("2099-01-05T15:00:00+00:00", "1", "100"),
        (_AT, "NaN", "100"),
        (_AT, "Infinity", "100"),
        (_AT, "-1", "100"),
        (_AT, "1", "0"),
        (_AT, "1", "-100"),
    ],
)
def test_malformed_fill_or_time_is_rejected_before_any_journal_mutation(
    store: AssistantStore,
    event_at: str,
    fill_qty: str,
    fill_price: str,
):
    order = _order(
        "filled",
        filled_qty_decimal="1",
        filled_avg_price_decimal="100",
    )
    raw = {
        "event": "fill",
        "event_id": "malformed-event",
        "event_at": event_at,
        "fill_qty_decimal": fill_qty,
        "fill_price_decimal": fill_price,
        "order": order,
    }
    with pytest.raises(ValueError):
        journal_broker_order_update(
            store,
            "proposal-1",
            order,
            event_type="fill",
            event_at=event_at,
            external_event_id="malformed-event",
            fill_qty=fill_qty,
            fill_price=fill_price,
            raw_event=raw,
        )

    assert store.list_broker_order_events() == []
    assert store.get_proposal("proposal-1")["status"] == "broker_accepted"


def test_legacy_real_only_fill_is_explicitly_unrecoverable(store: AssistantStore):
    order = _order(
        "filled",
        filled_qty_decimal="1",
        filled_avg_price_decimal="100",
    )
    journal_broker_order_update(
        store,
        "proposal-1",
        order,
        event_type="fill",
        event_at=_AT,
        external_event_id="legacy-fill",
        fill_qty=1.0,
        fill_price=100.0,
        raw_event={"order": {k: v for k, v in order.items() if not k.endswith("_decimal")}},
    )

    event = store.list_broker_order_events()[0]
    assert event["fill_qty_decimal"] is None
    assert event["fill_price_decimal"] is None
    assert event["numeric_evidence_status"] == "legacy_rounded_unrecoverable"
    fill = store.list_fills()[0]
    assert fill["numeric_evidence_status"] == "legacy_rounded_unrecoverable"


def test_migration_backfills_only_decimal_text_still_present_in_payload(
    store: AssistantStore,
):
    exact_order = _order(
        "partially_filled",
        filled_qty_decimal="0.123456789123456789",
        filled_avg_price_decimal="100.000000000000000019",
    )
    _journal_exact(
        store,
        exact_order,
        event_id="recoverable",
        fill_qty_decimal="0.123456789123456789",
        fill_price_decimal="100.000000000000000019",
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TRIGGER broker_order_events_append_only_update")
        connection.execute("DROP TRIGGER broker_order_events_append_only_delete")
        connection.execute(
            "UPDATE broker_order_events SET filled_qty_text = NULL, "
            "filled_avg_price_text = NULL, fill_qty_text = NULL, "
            "fill_price_text = NULL, numeric_evidence_status = NULL"
        )
        connection.execute(
            "DELETE FROM storage_migrations WHERE migration_id = ?",
            ("broker_order_event_integrity_v1",),
        )
        connection.execute(
            "ALTER TABLE broker_order_events DROP COLUMN event_content_hash"
        )
        connection.execute(
            "ALTER TABLE broker_order_events DROP COLUMN event_content_json"
        )
        connection.execute(
            "ALTER TABLE broker_order_events DROP COLUMN event_hash_version"
        )

    reopened = AssistantStore(store.path)
    event = reopened.list_broker_order_events()[0]
    assert event["filled_qty_decimal"] == "0.123456789123456789"
    assert event["fill_price_decimal"] == "100.000000000000000019"
    assert event["numeric_evidence_status"] == "provider_exact"


def test_budget_report_discloses_corrupt_legacy_fill_evidence(
    store: AssistantStore,
):
    order = _order(
        "filled",
        filled_qty_decimal="1",
        filled_avg_price_decimal="100",
    )
    _journal_exact(
        store,
        order,
        event_id="corrupted-later",
        fill_qty_decimal="1",
        fill_price_decimal="100",
    )
    store.reserve_execution_budget(
        "proposal-1",
        trading_day="2026-01-05",
        notional="100",
        max_daily_notional="1000",
        max_daily_orders=10,
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TRIGGER broker_order_events_append_only_update")
        connection.execute("DROP TRIGGER broker_order_events_append_only_delete")
        connection.execute(
            "UPDATE broker_order_events SET event_at = 'not-a-time', "
            "fill_qty_text = 'NaN' WHERE event_id = 'corrupted-later'"
        )

    usage = store.get_execution_budget_usage("2026-01-05")
    assert usage["submitted_notional_decimal"] == "100"
    assert usage["filled_notional_decimal"] == "0"
    assert usage["evidence_status"] == "integrity_error"
    assert usage["integrity_errors"]
    assert usage["integrity_errors"][0]["event_id"] == "corrupted-later"


def test_budget_report_discloses_legacy_rounded_fill_evidence(
    store: AssistantStore,
):
    order = _order(
        "filled",
        filled_qty_decimal="1",
        filled_avg_price_decimal="100",
    )
    journal_broker_order_update(
        store,
        "proposal-1",
        order,
        event_type="fill",
        event_at=_AT,
        external_event_id="legacy-budget-fill",
        fill_qty=1.0,
        fill_price=100.0,
        raw_event={
            "event": "fill",
            "event_id": "legacy-budget-fill",
            "event_at": _AT,
            "order": {k: v for k, v in order.items() if not k.endswith("_decimal")},
        },
    )
    usage = store.get_execution_budget_usage("2026-01-05")
    assert usage["filled_notional_decimal"] == "100"
    assert usage["evidence_status"] == "legacy_rounded_unrecoverable"
    assert usage["legacy_unrecoverable_event_ids"] == ["legacy-budget-fill"]


def test_activate_reconciliation_halt_commits_before_draining_existing_dispatch(
    store: AssistantStore,
):
    holder_entered = Event()
    release_holder = Event()
    activation_returned = Event()
    activation_result: list[dict] = []

    def hold_dispatch_fence() -> None:
        with execution_dispatch_fence(store.path):
            holder_entered.set()
            assert release_holder.wait(timeout=5)

    def activate_halt() -> None:
        activation_result.append(
            store.activate_reconciliation_halt(
                proposal_id="proposal-1",
                reason="broker identity conflict",
                seen_at=_AT,
            )
        )
        activation_returned.set()

    holder = Thread(target=hold_dispatch_fence)
    holder.start()
    assert holder_entered.wait(timeout=5)

    activator = Thread(target=activate_halt)
    activator.start()
    deadline = time.monotonic() + 5
    while not store.get_system_state("kill_switch", {}).get("active"):
        assert time.monotonic() < deadline
        time.sleep(0.01)

    # The durable halt is visible, but the caller cannot report containment
    # complete until the dispatch that entered before the halt has drained.
    assert not activation_returned.is_set()
    release_holder.set()
    holder.join(timeout=5)
    activator.join(timeout=5)

    assert not holder.is_alive()
    assert not activator.is_alive()
    assert activation_returned.is_set()
    assert activation_result[0]["category"] == "broker_reconciliation"
