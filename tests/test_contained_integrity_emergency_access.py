"""Emergency risk reduction must survive broker-event ledger corruption.

CLAUDE.md section 1 requires that a component failure never stop reconciliation
or legitimate risk reduction, and section 5 forbids a conservative safeguard
from obstructing a risk-reducing action.

The broker-event integrity sweep is correct to refuse ordinary use of a damaged
ledger.  It must not also remove the operator's ability to run emergency
cancellation, which reads no event evidence at all.
"""
from __future__ import annotations

import gc
import sqlite3
import sys
import weakref
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import assistant.storage as storage_module
from assistant.order_reconciler import cancel_all_open_orders
from assistant.storage import (
    AssistantStore,
    JournalTransactionConflictError,
    open_contained_cancel_all_store,
)


def _corrupt_event_database(tmp_path: Path) -> Path:
    """A previously healthy, fully migrated database with one damaged row."""
    database = tmp_path / "operator.db"
    store = AssistantStore(database)
    store.save_proposal(
        {
            "proposal_id": "p-1",
            "ticker": "AAPL",
            "side": "sell",
            "shares": 1,
            "status": "proposed",
            "created_at": "2026-08-27T00:00:00+00:00",
            "expires_at": "2099-12-31T00:00:00+00:00",
            "idempotency_key": "idem-p-1",
        }
    )
    del store

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO broker_orders "
            "(order_id, proposal_id, submitted_at, status, payload_json) "
            "VALUES ('o-1', 'p-1', '2026-08-27T00:00:00+00:00', 'accepted', '{}')"
        )
        # Simulates bit rot or a partial restore: the row is present but its
        # immutable identity metadata no longer authenticates.
        connection.execute(
            "INSERT INTO broker_order_events "
            "(event_id, order_id, proposal_id, event_type, event_at, status, "
            " numeric_evidence_status, event_scope, event_content_hash, "
            " event_content_json, event_hash_version, payload_json) "
            "VALUES ('evt-corrupt', 'o-1', 'p-1', 'submission_response', "
            "'2026-08-27T00:00:00+00:00', 'accepted', 'exact', 'paper:acct-1', "
            "'" + "de" * 32 + "', '{\"a\":1}', 1, '{}')"
        )
        connection.commit()
    return database


class _NoOpenOrdersBroker:
    """Minimal emergency broker double; cancellation needs no event evidence."""

    account_mode = "paper"

    @staticmethod
    def is_configured() -> bool:
        return True

    @staticmethod
    def get_open_orders():
        return []

    @staticmethod
    def cancel_all_orders():
        return {"cancelled": [], "errors": []}


class _UnreadableOpenBookBroker(_NoOpenOrdersBroker):
    """Forces the cancel-all incomplete-alert path after containment."""

    @staticmethod
    def get_open_orders():
        raise RuntimeError("open book unavailable")


def test_ordinary_construction_still_refuses_a_damaged_event_ledger(tmp_path):
    """The strict default is unchanged: normal use must not touch a bad ledger."""
    database = _corrupt_event_database(tmp_path)

    with pytest.raises(JournalTransactionConflictError):
        AssistantStore(database)


def test_contained_construction_preserves_emergency_cancellation(tmp_path):
    """The explicit contained mode keeps the last-resort tool reachable."""
    database = _corrupt_event_database(tmp_path)

    store = open_contained_cancel_all_store(database)

    # The failure is retained, not silently discarded.
    assert store.broker_event_integrity_error is not None
    assert "integrity violation" in store.broker_event_integrity_error
    # Containment is already active, so the contained store cannot add exposure.
    assert store.get_kill_switch()["active"] is True

    result = cancel_all_open_orders(
        store,
        broker_module=_NoOpenOrdersBroker(),
        reason="review regression: emergency access under ledger corruption",
        now=datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc),
    )

    assert isinstance(result, dict)
    assert store.get_kill_switch()["active"] is True


def test_contained_capability_records_an_incomplete_cancel_all(tmp_path):
    """The restricted surface covers cancel-all's fail-loud audit path."""
    database = _corrupt_event_database(tmp_path)
    store = open_contained_cancel_all_store(database)

    result = cancel_all_open_orders(
        store,
        broker_module=_UnreadableOpenBookBroker(),
        reason="review regression: incomplete cancellation under corruption",
        now=datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc),
    )

    assert result["book_stable"] is False
    assert any(
        "open-order query failed" in item["error"] for item in result["errors"]
    )
    with sqlite3.connect(database) as connection:
        alert = connection.execute(
            "SELECT severity, category, status FROM operational_alerts "
            "WHERE fingerprint = 'broker_reconciliation:emergency-cancel-all'"
        ).fetchone()
    assert alert == ("critical", "broker_reconciliation", "open")


def test_healthy_database_records_no_integrity_failure(tmp_path):
    """The new attribute must not become a permanently-set flag."""
    store = AssistantStore(tmp_path / "healthy.db")

    assert store.broker_event_integrity_error is None


def test_contained_cancel_all_factory_refuses_a_healthy_database(tmp_path):
    """The exceptional factory never returns a normal mutable store."""
    with pytest.raises(
        RuntimeError, match="requires a broker-event integrity failure"
    ):
        open_contained_cancel_all_store(tmp_path / "healthy.db")


def test_cancel_all_cli_uses_the_normal_store_when_integrity_is_healthy(
    tmp_path, monkeypatch
):
    """Healthy cancellation retains ordinary attribution and bookkeeping."""
    import scripts.run_personal_assistant as cli

    normal_store = object()
    observed = []
    monkeypatch.setattr(cli, "AssistantStore", lambda _path: normal_store)
    monkeypatch.setattr(
        cli,
        "open_contained_cancel_all_store",
        lambda _path: pytest.fail("contained factory must not open a healthy store"),
    )
    monkeypatch.setattr(
        cli,
        "command_cancel_all_orders",
        lambda _args, store: observed.append(store),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--database",
            str(tmp_path / "healthy.db"),
            "cancel-all-orders",
            "--confirm",
            "cancel all open orders",
            "--reason",
            "operator drill",
        ],
    )

    cli.main()

    assert observed == [normal_store]


def test_cancel_all_cli_uses_the_capability_only_for_integrity_failure(
    tmp_path, monkeypatch
):
    """Only the authenticated-journal refusal selects contained access."""
    import scripts.run_personal_assistant as cli

    contained_store = object()
    observed = []

    def refuse(_path):
        raise JournalTransactionConflictError("corrupt broker-event journal")

    monkeypatch.setattr(cli, "AssistantStore", refuse)
    monkeypatch.setattr(
        cli,
        "open_contained_cancel_all_store",
        lambda _path: contained_store,
    )
    monkeypatch.setattr(
        cli,
        "command_cancel_all_orders",
        lambda _args, store: observed.append(store),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--database",
            str(tmp_path / "corrupt.db"),
            "cancel-all-orders",
            "--confirm",
            "cancel all open orders",
            "--reason",
            "operator drill",
        ],
    )

    cli.main()

    assert observed == [contained_store]


def test_general_store_has_no_contained_integrity_escape_hatch(tmp_path):
    """A caller cannot opt a full mutable store past journal authentication."""
    database = _corrupt_event_database(tmp_path)

    with pytest.raises(TypeError, match="unexpected keyword"):
        AssistantStore(database, permit_contained_integrity_failure=True)


def test_contained_cancel_all_store_exposes_no_general_mutation_or_event_api(tmp_path):
    """Contained access is a narrow capability, not a weakened full store."""
    store = open_contained_cancel_all_store(_corrupt_event_database(tmp_path))

    assert {name for name in dir(store) if not name.startswith("_")} == {
        "activate_reconciliation_halt",
        "broker_event_integrity_error",
        "get_kill_switch",
        "list_proposals_by_statuses",
        "path",
        "set_kill_switch",
        "set_system_state",
        "upsert_operational_alert",
    }
    for forbidden in (
        "claim_proposal",
        "dismiss_proposals",
        "get_proposal",
        "get_proposal_by_broker_order_id",
        "get_proposal_by_idempotency_key",
        "list_operational_alerts",
        "project_broker_order_event",
        "list_broker_order_events",
        "list_proposals",
        "save_proposal",
        "reserve_execution_budget",
        "park_reconciliation_anomaly_and_halt",
        "record_ledger_reconciliation",
        "update_proposal_status",
    ):
        assert not hasattr(store, forbidden), forbidden


def test_contained_cancel_all_store_retains_no_unrestricted_store(
    tmp_path, monkeypatch
):
    """Each approved call gets a short-lived delegate, never a stored escape."""
    store = open_contained_cancel_all_store(_corrupt_event_database(tmp_path))

    assert not hasattr(store, "_ContainedCancelAllStore__store")
    assert "_open" not in AssistantStore.__dict__
    assert "_open_contained_for_cancel_all" not in AssistantStore.__dict__
    with pytest.raises(PermissionError, match="outside contained"):
        storage_module._invoke_contained_cancel_all_primitive(
            store.path,
            integrity_error=store.broker_event_integrity_error,
            operation="save_proposal",
            payload={"proposal": {"status": "approved"}},
        )

    delegates: list[weakref.ReferenceType[AssistantStore]] = []
    original = AssistantStore.get_kill_switch

    def record_delegate(delegate):
        delegates.append(weakref.ref(delegate))
        return original(delegate)

    monkeypatch.setattr(AssistantStore, "get_kill_switch", record_delegate)
    assert store.get_kill_switch()["active"] is True
    gc.collect()

    assert len(delegates) == 1
    assert delegates[0]() is None


def test_contained_cancel_all_store_rejects_broader_uses_of_forwarded_primitives(
    tmp_path,
):
    """Forwarded primitives cannot be repurposed beyond account-wide cancel-all."""
    store = open_contained_cancel_all_store(_corrupt_event_database(tmp_path))

    with pytest.raises(PermissionError, match="only activate"):
        store.set_kill_switch(
            False,
            reason="must not clear containment",
            incident_id="test",
            changed_at="2026-08-27T18:00:00+00:00",
        )
    with pytest.raises(PermissionError, match="general system state"):
        store.set_system_state("kill_switch", {"active": False})
    with pytest.raises(PermissionError, match="unresolved dispatches"):
        store.list_proposals_by_statuses(["proposed"])
    with pytest.raises(PermissionError, match="selective proposal"):
        store.activate_reconciliation_halt(
            proposal_id="p-1",
            reason="not an account-wide cancel-all incident",
        )
    with pytest.raises(PermissionError, match="critical alert"):
        store.upsert_operational_alert(
            fingerprint="unrelated",
            severity="info",
            category="unrelated",
            message="must not be writable through the capability",
        )


def test_only_emergency_cancellation_opts_into_contained_construction():
    """The escape hatch must stay narrow: exactly one command may use it."""
    import argparse

    from scripts.run_personal_assistant import build_parser

    parser = build_parser()
    opted_in = []
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, subparser in action.choices.items():
            defaults = subparser._defaults
            if defaults.get("uses_contained_cancel_all_store"):
                opted_in.append(name)

    assert opted_in == ["cancel-all-orders"], (
        "contained construction bypasses a fail-closed integrity refusal and "
        f"must remain limited to emergency cancellation; got {opted_in}"
    )


def test_cancel_all_cli_exits_nonzero_when_book_is_unstable_even_without_errors(
    monkeypatch, capsys
):
    import scripts.run_personal_assistant as cli

    monkeypatch.setattr(
        cli,
        "cancel_all_open_orders",
        lambda *_args, **_kwargs: {"book_stable": False, "errors": []},
    )
    args = SimpleNamespace(
        confirm="cancel all open orders",
        reason="ambiguous durable order",
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.command_cancel_all_orders(args, object())

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert '"book_stable": false' in captured.out
    assert "could not prove a stable" in captured.err


def test_cancel_all_cli_warns_but_succeeds_for_stable_diagnostics(
    monkeypatch, capsys
):
    import scripts.run_personal_assistant as cli

    monkeypatch.setattr(
        cli,
        "cancel_all_open_orders",
        lambda *_args, **_kwargs: {
            "book_stable": True,
            "errors": [{"error": "strict model path degraded; raw proof succeeded"}],
        },
    )
    args = SimpleNamespace(
        confirm="cancel all open orders",
        reason="raw enumeration recovery",
    )

    cli.command_cancel_all_orders(args, object())

    captured = capsys.readouterr()
    assert '"book_stable": true' in captured.out
    assert "WARNING: cancel-all proved stable" in captured.err
