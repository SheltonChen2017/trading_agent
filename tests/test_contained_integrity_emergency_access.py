"""Emergency risk reduction must survive broker-event ledger corruption.

CLAUDE.md section 1 requires that a component failure never stop reconciliation
or legitimate risk reduction, and section 5 forbids a conservative safeguard
from obstructing a risk-reducing action.

The broker-event integrity sweep is correct to refuse ordinary use of a damaged
ledger.  It must not also remove the operator's ability to run emergency
cancellation, which reads no event evidence at all.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from assistant.order_reconciler import cancel_all_open_orders
from assistant.storage import AssistantStore, JournalTransactionConflictError


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


def test_ordinary_construction_still_refuses_a_damaged_event_ledger(tmp_path):
    """The strict default is unchanged: normal use must not touch a bad ledger."""
    database = _corrupt_event_database(tmp_path)

    with pytest.raises(JournalTransactionConflictError):
        AssistantStore(database)


def test_contained_construction_preserves_emergency_cancellation(tmp_path):
    """The explicit contained mode keeps the last-resort tool reachable."""
    database = _corrupt_event_database(tmp_path)

    store = AssistantStore(database, permit_contained_integrity_failure=True)

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


def test_healthy_database_records_no_integrity_failure(tmp_path):
    """The new attribute must not become a permanently-set flag."""
    store = AssistantStore(tmp_path / "healthy.db")

    assert store.broker_event_integrity_error is None


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
            if defaults.get("permits_contained_integrity_failure"):
                opted_in.append(name)

    assert opted_in == ["cancel-all-orders"], (
        "contained construction bypasses a fail-closed integrity refusal and "
        f"must remain limited to emergency cancellation; got {opted_in}"
    )
