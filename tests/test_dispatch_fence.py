from __future__ import annotations

import multiprocessing
import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import assistant.dispatch_fence as dispatch_fence_module
import assistant.storage as storage_module
from assistant.dispatch_fence import (
    DispatchFenceTimeout,
    RuntimeDispatchAttemptConflictError,
    activate_runtime_emergency_stop,
    clear_runtime_emergency_stop,
    execution_dispatch_fence,
    get_runtime_emergency_stop,
    list_runtime_dispatch_attempts,
    record_runtime_dispatch_attempt,
    runtime_emergency_stop_path,
    runtime_dispatch_attempts_path,
)
from assistant.storage import AssistantStore


@pytest.fixture(autouse=True)
def _isolated_runtime_fence_root(tmp_path, monkeypatch):
    """Keep focused tests isolated while preserving subprocess agreement."""
    runtime_root = (tmp_path / "runtime").resolve()
    monkeypatch.setattr(
        dispatch_fence_module,
        "_RUNTIME_FENCE_ROOT",
        runtime_root,
    )
    return runtime_root


def _fork_fence_attempt(database: str, connection, timeout: float) -> None:
    try:
        with execution_dispatch_fence(database, timeout_seconds=timeout):
            connection.send("acquired")
    except DispatchFenceTimeout:
        connection.send("timed-out")
    finally:
        connection.close()


def test_dispatch_fence_is_reentrant_and_keeps_one_stable_lock_file(
    tmp_path, _isolated_runtime_fence_root
):
    database = tmp_path / "state" / "assistant.sqlite3"
    expected = (
        _isolated_runtime_fence_root / "locks" / "execution-dispatch.lock"
    )

    with execution_dispatch_fence(database) as outer_path:
        with execution_dispatch_fence(database) as inner_path:
            assert outer_path == expected
            assert inner_path == expected
            assert expected.is_file()

    assert expected.is_file()
    assert expected.read_bytes() == b"\0"


def test_dispatch_fence_serializes_threads_and_honors_one_deadline(tmp_path):
    database = tmp_path / "assistant.sqlite3"
    result: list[BaseException | str] = []

    def contender() -> None:
        try:
            with execution_dispatch_fence(database, timeout_seconds=0.05):
                result.append("acquired")
        except BaseException as exc:  # captured for assertion in main thread
            result.append(exc)

    with execution_dispatch_fence(database):
        worker = threading.Thread(target=contender)
        worker.start()
        worker.join(timeout=2)

    assert not worker.is_alive()
    assert len(result) == 1
    assert isinstance(result[0], DispatchFenceTimeout)

    with execution_dispatch_fence(database, timeout_seconds=0.2):
        pass


def test_dispatch_fence_serializes_independent_processes(
    tmp_path, _isolated_runtime_fence_root
):
    owner_database = tmp_path / "owner" / "assistant.sqlite3"
    contender_database = tmp_path / "contender" / "assistant.sqlite3"
    repository = Path(__file__).resolve().parents[1]
    program = (
        "import sys\n"
        "from pathlib import Path\n"
        "import assistant.dispatch_fence as fence\n"
        "fence._RUNTIME_FENCE_ROOT = Path(sys.argv[2])\n"
        "try:\n"
        "    with fence.execution_dispatch_fence(sys.argv[1], timeout_seconds=0.1):\n"
        "        print('acquired')\n"
        "except fence.DispatchFenceTimeout:\n"
        "    print('timed-out')\n"
    )

    with execution_dispatch_fence(owner_database):
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                program,
                str(contender_database),
                str(_isolated_runtime_fence_root),
            ],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

    assert completed.stdout.strip() == "timed-out"


def test_dispatch_fence_is_released_when_owner_process_crashes(
    tmp_path, _isolated_runtime_fence_root
):
    database = tmp_path / "assistant.sqlite3"
    repository = Path(__file__).resolve().parents[1]
    program = (
        "import os, sys\n"
        "from pathlib import Path\n"
        "import assistant.dispatch_fence as fence\n"
        "fence._RUNTIME_FENCE_ROOT = Path(sys.argv[2])\n"
        "with fence.execution_dispatch_fence(sys.argv[1]):\n"
        "    os._exit(23)\n"
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            program,
            str(database),
            str(_isolated_runtime_fence_root),
        ],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert completed.returncode == 23

    with execution_dispatch_fence(database, timeout_seconds=1):
        pass


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fork regression")
def test_fork_child_does_not_inherit_parent_fence_ownership(tmp_path):
    database = tmp_path / "assistant.sqlite3"
    context = multiprocessing.get_context("fork")

    parent_connection, child_connection = context.Pipe(duplex=False)
    with execution_dispatch_fence(database):
        contender = context.Process(
            target=_fork_fence_attempt,
            args=(str(database), child_connection, 0.1),
        )
        contender.start()
        child_connection.close()
        assert parent_connection.recv() == "timed-out"
        contender.join(timeout=5)
        assert contender.exitcode == 0
    parent_connection.close()

    parent_connection, child_connection = context.Pipe(duplex=False)
    successor = context.Process(
        target=_fork_fence_attempt,
        args=(str(database), child_connection, 1.0),
    )
    successor.start()
    child_connection.close()
    assert parent_connection.recv() == "acquired"
    successor.join(timeout=5)
    assert successor.exitcode == 0
    parent_connection.close()


@pytest.mark.parametrize(
    "keyword,value",
    [
        ("timeout_seconds", True),
        ("timeout_seconds", -1),
        ("timeout_seconds", float("nan")),
        ("timeout_seconds", threading.TIMEOUT_MAX * 2),
        ("poll_seconds", False),
        ("poll_seconds", 0),
        ("poll_seconds", float("inf")),
    ],
)
def test_dispatch_fence_rejects_invalid_timing_controls(
    tmp_path, keyword, value
):
    options = {keyword: value}
    with pytest.raises(ValueError):
        with execution_dispatch_fence(tmp_path / "assistant.sqlite3", **options):
            pass


def test_runtime_stop_is_shared_across_databases_and_generation_bound(tmp_path):
    first_database = tmp_path / "one" / "assistant.sqlite3"
    second_database = tmp_path / "two" / "assistant.sqlite3"
    activated_at = datetime.now(timezone.utc)
    active = activate_runtime_emergency_stop(
        first_database,
        incident_id="incident:first",
        reason="operator containment",
        changed_at=activated_at.isoformat(),
    )

    assert get_runtime_emergency_stop(second_database) == active
    second = activate_runtime_emergency_stop(
        second_database,
        incident_id="incident:second",
        reason="later incident",
        changed_at=(activated_at + timedelta(seconds=1)).isoformat(),
    )
    assert second["generation"] == active["generation"] + 1
    assert [item["incident_id"] for item in second["open_incidents"]] == [
        "incident:first",
        "incident:second",
    ]
    with pytest.raises(RuntimeError, match="generation changed"):
        clear_runtime_emergency_stop(
            first_database,
            incident_id="incident:first",
            expected_generation=active["generation"],
            reason="stale screen",
            changed_at=(activated_at + timedelta(seconds=2)).isoformat(),
        )
    with pytest.raises(RuntimeError, match="database that activated"):
        clear_runtime_emergency_stop(
            second_database,
            incident_id="incident:first",
            expected_generation=second["generation"],
            reason="wrong database",
            changed_at=(activated_at + timedelta(seconds=2)).isoformat(),
        )

    first_cleared = clear_runtime_emergency_stop(
        first_database,
        incident_id="incident:first",
        expected_generation=second["generation"],
        reason="operator verified containment",
        changed_at=(activated_at + timedelta(seconds=3)).isoformat(),
    )
    assert first_cleared["active"] is True
    assert [
        item["incident_id"] for item in first_cleared["open_incidents"]
    ] == ["incident:second"]
    cleared = clear_runtime_emergency_stop(
        second_database,
        incident_id="incident:second",
        expected_generation=first_cleared["generation"],
        reason="second incident verified",
        changed_at=(activated_at + timedelta(seconds=4)).isoformat(),
    )
    assert cleared["active"] is False
    assert get_runtime_emergency_stop(first_database) == cleared


def test_runtime_namespace_ignores_process_environment(monkeypatch):
    expected = dispatch_fence_module._canonical_runtime_root()
    for name in (
        "TRADING_ASSISTANT_RUNTIME_DIR",
        "LOCALAPPDATA",
        "XDG_RUNTIME_DIR",
        "TMP",
        "TEMP",
        "TMPDIR",
    ):
        monkeypatch.setenv(name, str(Path.cwd() / f"split-{name}"))
    assert dispatch_fence_module._canonical_runtime_root() == expected


def test_pre_runtime_local_stop_is_promoted_across_databases(tmp_path):
    first_path = tmp_path / "legacy" / "assistant.db"
    second_path = tmp_path / "other" / "assistant.db"
    first = AssistantStore(first_path)
    AssistantStore(second_path)
    first.set_system_state(
        "kill_switch",
        {
            "active": True,
            "reason": "legacy broker reconciliation incident",
            "changed_at": "2026-08-26T12:00:00+00:00",
        },
    )
    assert get_runtime_emergency_stop(second_path)["active"] is False

    AssistantStore(first_path)

    promoted = get_runtime_emergency_stop(second_path)
    assert promoted["active"] is True
    assert len(promoted["open_incidents"]) == 1
    assert promoted["open_incidents"][0]["origin_database"] == str(
        first_path.resolve()
    )
    assert promoted["open_incidents"][0]["incident_id"].startswith(
        "legacy-local-stop:"
    )


@pytest.mark.parametrize(
    "raw_state",
    [
        "not-json",
        (
            '{"version":2,"active":false,"scope":"execution_runtime",'
            '"reason":"looks inactive",'
            '"changed_at":"2026-08-26T00:00:00+00:00"}'
        ),
        (
            '{"version":true,"active":false,"scope":"execution_runtime",'
            '"reason":"boolean version",'
            '"changed_at":"2026-08-26T00:00:00+00:00",'
            '"cleared_stop_changed_at":"2026-08-25T00:00:00+00:00",'
            '"origin_database":"C:\\\\broker\\\\assistant.db"}'
        ),
    ],
    ids=("invalid-json", "incomplete-inactive", "boolean-version"),
)
def test_runtime_stop_corruption_fails_closed(tmp_path, raw_state):
    database = tmp_path / "assistant.sqlite3"
    path = runtime_emergency_stop_path(database)
    path.parent.mkdir(parents=True)
    path.write_text(raw_state, encoding="utf-8")

    state = get_runtime_emergency_stop(database)
    assert state["active"] is True
    assert "integrity_error" in state
    with pytest.raises(RuntimeError, match="unreadable"):
        activate_runtime_emergency_stop(
            database,
            incident_id="incident:corrupt",
            reason="must not overwrite corruption",
            changed_at=datetime.now(timezone.utc).isoformat(),
        )


def test_runtime_dispatch_attempts_are_visible_across_databases(tmp_path):
    first_database = tmp_path / "one" / "assistant.sqlite3"
    second_database = tmp_path / "two" / "assistant.sqlite3"
    attempted_at = datetime.now(timezone.utc).isoformat()
    recorded = record_runtime_dispatch_attempt(
        first_database,
        proposal_id="proposal-1",
        idempotency_key="client-1",
        attempted_at=attempted_at,
        account_id="paper-account-1",
        account_mode="paper",
    )

    assert list_runtime_dispatch_attempts(second_database) == [recorded]
    with pytest.raises(ValueError, match="timezone-aware"):
        record_runtime_dispatch_attempt(
            first_database,
            proposal_id="proposal-2",
            idempotency_key="client-2",
            attempted_at="2026-08-26T00:00:00",
            account_id="paper-account-1",
            account_mode="paper",
        )


def test_runtime_dispatch_attempt_rejects_padded_terminal_order_id(tmp_path):
    database = tmp_path / "assistant.db"
    attempted_at = datetime.now(timezone.utc).isoformat()
    record_runtime_dispatch_attempt(
        database,
        proposal_id="proposal-1",
        idempotency_key="client-1",
        attempted_at=attempted_at,
        account_id="paper-account-1",
        account_mode="paper",
    )

    with pytest.raises(ValueError, match="canonical"):
        record_runtime_dispatch_attempt(
            database,
            proposal_id="proposal-1",
            idempotency_key="client-1",
            attempted_at=attempted_at,
            account_id="paper-account-1",
            account_mode="paper",
            state="broker_accepted",
            order_id=" padded-order-id ",
        )

    [retained] = list_runtime_dispatch_attempts(database)
    assert retained["state"] == "pre_contact"
    assert retained["order_id"] is None


def test_dispatch_attempt_containment_republishes_after_clear_race(
    tmp_path, monkeypatch
):
    database = tmp_path / "assistant.db"
    reason = "shared dispatch-attempt identity collision"
    original_activate = dispatch_fence_module.activate_runtime_emergency_stop
    calls = 0

    def activate_then_clear(*args, **kwargs):
        nonlocal calls
        calls += 1
        state = original_activate(*args, **kwargs)
        if calls == 1:
            clear_runtime_emergency_stop(
                database,
                incident_id=kwargs["incident_id"],
                expected_generation=state["generation"],
                reason="simulated operator clear race",
                changed_at=datetime.now(timezone.utc).isoformat(),
            )
        return state

    monkeypatch.setattr(
        dispatch_fence_module,
        "activate_runtime_emergency_stop",
        activate_then_clear,
    )
    dispatch_fence_module._contain_runtime_dispatch_attempt_integrity(
        database, reason
    )

    observed = get_runtime_emergency_stop(database)
    assert calls == 2
    assert observed["active"] is True
    assert observed["open_incidents"][0]["reason"] == reason


def test_storage_containment_republishes_after_clear_race(tmp_path):
    database = tmp_path / "assistant.db"
    incident_id = "broker-integrity:clear-race"
    reason = "broker event integrity collision"
    changed_at = datetime.now(timezone.utc).isoformat()
    active = activate_runtime_emergency_stop(
        database,
        incident_id=incident_id,
        reason=reason,
        changed_at=changed_at,
    )
    clear_runtime_emergency_stop(
        database,
        incident_id=incident_id,
        expected_generation=active["generation"],
        reason="simulated operator clear race",
        changed_at=datetime.now(timezone.utc).isoformat(),
    )

    retry_error = storage_module._drain_and_retry_runtime_incident(
        database,
        incident_id=incident_id,
        reason=reason,
        changed_at=changed_at,
        activation_error=None,
    )

    assert retry_error is None
    observed = get_runtime_emergency_stop(database)
    assert observed["active"] is True
    assert observed["open_incidents"][0]["incident_id"] == incident_id


def test_containment_latches_when_publication_and_dispatch_fence_fail(
    tmp_path, monkeypatch
):
    database = tmp_path / "assistant.db"

    def publication_failure(*_args, **_kwargs):
        raise OSError("runtime state write failed")

    @contextmanager
    def fence_failure(*_args, **_kwargs):
        raise DispatchFenceTimeout("dispatch drain timed out")
        yield

    monkeypatch.setattr(
        dispatch_fence_module,
        "activate_runtime_emergency_stop",
        publication_failure,
    )
    monkeypatch.setattr(
        dispatch_fence_module, "execution_dispatch_fence", fence_failure
    )

    dispatch_fence_module._contain_runtime_dispatch_attempt_integrity(
        database, "attempt ledger is corrupt"
    )

    observed = get_runtime_emergency_stop(database)
    assert observed["active"] is True
    assert "dispatch drain timed out" in observed["integrity_error"]


def test_dispatch_attempt_client_id_cannot_be_rebound_across_databases(tmp_path):
    first = tmp_path / "one" / "assistant.db"
    second = tmp_path / "two" / "assistant.db"
    attempted_at = datetime.now(timezone.utc).isoformat()
    record_runtime_dispatch_attempt(
        first,
        proposal_id="proposal-1",
        idempotency_key="globally-unique-client-id",
        attempted_at=attempted_at,
        account_id="paper-account-1",
        account_mode="paper",
    )

    with pytest.raises(RuntimeDispatchAttemptConflictError, match="already bound"):
        record_runtime_dispatch_attempt(
            second,
            proposal_id="proposal-2",
            idempotency_key="globally-unique-client-id",
            attempted_at=attempted_at,
            account_id="paper-account-1",
            account_mode="paper",
        )

    attempts = list_runtime_dispatch_attempts(first)
    assert len(attempts) == 1
    assert attempts[0]["database"] == str(first.resolve())
    assert get_runtime_emergency_stop(second)["active"] is True


def test_dispatch_attempt_ledger_rejects_unknown_fields_and_contains(tmp_path):
    database = tmp_path / "assistant.db"
    attempted_at = datetime.now(timezone.utc).isoformat()
    record_runtime_dispatch_attempt(
        database,
        proposal_id="proposal-1",
        idempotency_key="client-1",
        attempted_at=attempted_at,
        account_id="paper-account-1",
        account_mode="paper",
    )
    path = runtime_dispatch_attempts_path(database)
    ledger = json.loads(path.read_text(encoding="utf-8"))
    ledger["attempts"][0]["unexpected"] = "authority bypass"
    path.write_text(json.dumps(ledger), encoding="utf-8")

    with pytest.raises(RuntimeDispatchAttemptConflictError, match="unknown fields"):
        list_runtime_dispatch_attempts(database)
    assert get_runtime_emergency_stop(database)["active"] is True


def test_fork_child_reset_discards_inherited_ownership_on_every_platform():
    """Exercise the fork-child hardening even where ``os.fork`` is absent."""
    inherited_path = Path("inherited-fence.lock")
    original_states = dispatch_fence_module._STATES
    original_states_guard = dispatch_fence_module._STATES_GUARD
    original_permits = dispatch_fence_module._DISPATCH_PERMITS
    original_permits_guard = dispatch_fence_module._DISPATCH_PERMITS_GUARD

    class _InheritedHandle:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    handle = _InheritedHandle()
    try:
        inherited_state = dispatch_fence_module._ProcessFenceState(
            depth=3, handle=handle, owner_thread_id=threading.get_ident()
        )
        dispatch_fence_module._STATES = {inherited_path: inherited_state}
        dispatch_fence_module._DISPATCH_PERMITS = {"inherited-permit": object()}

        dispatch_fence_module._reset_after_fork()

        assert handle.closed is True
        assert dispatch_fence_module._STATES == {}
        assert dispatch_fence_module._DISPATCH_PERMITS == {}
        assert dispatch_fence_module._STATES_GUARD is not original_states_guard
        assert dispatch_fence_module._DISPATCH_PERMITS_GUARD is not original_permits_guard
        assert dispatch_fence_module._STATES_GUARD.acquire(blocking=False) is True
        dispatch_fence_module._STATES_GUARD.release()
    finally:
        dispatch_fence_module._STATES = original_states
        dispatch_fence_module._STATES_GUARD = original_states_guard
        dispatch_fence_module._DISPATCH_PERMITS = original_permits
        dispatch_fence_module._DISPATCH_PERMITS_GUARD = original_permits_guard
