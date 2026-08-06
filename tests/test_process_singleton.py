"""Process-level singleton lock for long-running operational workers."""
from __future__ import annotations

from pathlib import Path

import pytest

from assistant.process_singleton import (
    ProcessSingletonError,
    acquire_process_singleton,
    lock_path_for,
)


def test_lock_path_is_beside_the_database(tmp_path):
    db = tmp_path / "data" / "trading_assistant.db"
    db.parent.mkdir()
    db.write_text("", encoding="utf-8")
    assert lock_path_for(db, "order-monitor") == tmp_path / "data" / "locks" / "order-monitor.lock"


def test_second_acquire_fails_while_first_is_held(tmp_path):
    db = tmp_path / "assistant.db"
    db.write_text("", encoding="utf-8")
    first = acquire_process_singleton(db, "order-monitor")
    try:
        with pytest.raises(ProcessSingletonError, match="already holds"):
            acquire_process_singleton(db, "order-monitor")
    finally:
        first.release()


def test_lock_releases_so_a_successor_can_start(tmp_path):
    db = tmp_path / "assistant.db"
    db.write_text("", encoding="utf-8")
    first = acquire_process_singleton(db, "watchdog")
    first.release()
    second = acquire_process_singleton(db, "watchdog")
    second.release()


def test_rejects_path_traversal_in_lock_name(tmp_path):
    db = tmp_path / "assistant.db"
    db.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        lock_path_for(db, "../evil")


def test_monitor_orders_refuses_when_singleton_is_held(tmp_path, monkeypatch):
    """Wiring: the CLI must fail closed before broker work when orphaned."""
    from types import SimpleNamespace

    import scripts.run_personal_assistant as cli

    db = tmp_path / "assistant.db"
    db.write_text("", encoding="utf-8")
    held = acquire_process_singleton(db, "order-monitor")
    monkeypatch.setattr(cli, "load_policy", lambda path: (_ for _ in ()).throw(
        AssertionError("must not load policy after singleton refusal")
    ))
    try:
        with pytest.raises(SystemExit, match="already running"):
            cli.command_monitor_orders(
                SimpleNamespace(
                    database=db,
                    policy=None,
                    cancel_stale=False,
                    poll_seconds=30,
                ),
                store=object(),
            )
    finally:
        held.release()
