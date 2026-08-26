from __future__ import annotations

import multiprocessing
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from assistant.dispatch_fence import (
    DispatchFenceTimeout,
    execution_dispatch_fence,
)


def _fork_fence_attempt(database: str, connection, timeout: float) -> None:
    try:
        with execution_dispatch_fence(database, timeout_seconds=timeout):
            connection.send("acquired")
    except DispatchFenceTimeout:
        connection.send("timed-out")
    finally:
        connection.close()


def test_dispatch_fence_is_reentrant_and_keeps_one_stable_lock_file(tmp_path):
    database = tmp_path / "state" / "assistant.sqlite3"
    expected = database.resolve().parent / "locks" / "execution-dispatch.lock"

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


def test_dispatch_fence_serializes_independent_processes(tmp_path):
    database = tmp_path / "assistant.sqlite3"
    repository = Path(__file__).resolve().parents[1]
    program = (
        "import sys\n"
        "from assistant.dispatch_fence import DispatchFenceTimeout, execution_dispatch_fence\n"
        "try:\n"
        "    with execution_dispatch_fence(sys.argv[1], timeout_seconds=0.1):\n"
        "        print('acquired')\n"
        "except DispatchFenceTimeout:\n"
        "    print('timed-out')\n"
    )

    with execution_dispatch_fence(database):
        completed = subprocess.run(
            [sys.executable, "-c", program, str(database)],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

    assert completed.stdout.strip() == "timed-out"


def test_dispatch_fence_is_released_when_owner_process_crashes(tmp_path):
    database = tmp_path / "assistant.sqlite3"
    repository = Path(__file__).resolve().parents[1]
    program = (
        "import os, sys\n"
        "from assistant.dispatch_fence import execution_dispatch_fence\n"
        "with execution_dispatch_fence(sys.argv[1]):\n"
        "    os._exit(23)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program, str(database)],
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
