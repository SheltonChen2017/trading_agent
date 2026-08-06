"""Process-level singleton lock for long-running operational workers."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Mimics the PRODUCTION call sites exactly: the returned ProcessSingleton is
# discarded, not bound to a local. Every other test in this module keeps an
# explicit reference, which the real callers do not -- so only a subprocess
# shaped like the caller can prove the lock outlives collection.
_DISCARDED_REFERENCE_HOLDER = """
import gc
import sys
import time

sys.path.insert(0, sys.argv[1])
from assistant.process_singleton import acquire_process_singleton

acquire_process_singleton(sys.argv[2], sys.argv[3])  # return value discarded
gc.collect()
gc.collect()
print("READY", flush=True)
time.sleep(120)
"""

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


def test_lock_survives_a_discarded_reference_in_the_holding_process(tmp_path):
    """CCCROPS-001. The call sites discard the ProcessSingleton, so nothing
    in `command_monitor_orders` or the watchdog's `main` keeps it reachable.
    If the module does not own the lock for the process lifetime, the object
    is collected, CPython closes the file handle, and the OS releases the
    lock while the worker keeps running -- two monitors on one database
    again, silently.

    Cross-process because that is the only observation that matters: a
    same-process assertion cannot distinguish "lock held" from "handle still
    referenced by this test".
    """
    db = tmp_path / "assistant.db"
    db.write_text("", encoding="utf-8")

    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _DISCARDED_REFERENCE_HOLDER,
            str(_REPO_ROOT),
            str(db),
            "order-monitor",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # readline returns "" at EOF, so a crashed holder fails loudly here
        # rather than hanging the suite.
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "READY", (
            "holder process failed to acquire: "
            f"{holder.stderr.read() if holder.stderr else ''}"
        )
        with pytest.raises(ProcessSingletonError):
            acquire_process_singleton(db, "order-monitor")
    finally:
        holder.kill()
        holder.wait(timeout=30)


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
