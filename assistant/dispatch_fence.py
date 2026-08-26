"""Cross-process serialization for broker dispatch and emergency containment.

The durable kill switch answers *whether* a submission may proceed.  This
module closes the separate time-of-check/time-of-use race by giving every
broker-contacting dispatch and every containment operation the same exclusive
OS-backed fence.  A process-local re-entrant lock is paired with the file lock
because POSIX ``flock`` locks are process-scoped and therefore do not serialize
threads in one process by themselves.

The lock file is permanent and contains no state.  Ownership lives entirely in
the open file descriptor, so the operating system releases it after an
unexpected process exit.  Callers must not delete the file: replacing its inode
would allow two processes to believe they hold the same named fence.
"""
from __future__ import annotations

import math
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator


DEFAULT_DISPATCH_FENCE_TIMEOUT_SECONDS = 30.0
DEFAULT_DISPATCH_FENCE_POLL_SECONDS = 0.01


class DispatchFenceTimeout(TimeoutError):
    """The execution dispatch fence could not be acquired in time."""


def dispatch_fence_path(database: str | Path) -> Path:
    """Return the stable lock path associated with one assistant database."""
    database_path = Path(database).expanduser().resolve()
    return database_path.parent / "locks" / "execution-dispatch.lock"


def _finite_nonnegative_seconds(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative real number")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{name} must be a finite non-negative real number")
    return parsed


def _try_lock_file(handle: BinaryIO) -> None:
    """Acquire one byte non-blockingly or raise ``OSError``."""
    handle.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle: BinaryIO) -> None:
    handle.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@dataclass
class _ProcessFenceState:
    gate: threading.RLock = field(default_factory=threading.RLock)
    depth: int = 0
    handle: BinaryIO | None = None


_STATES_GUARD = threading.Lock()
_STATES: dict[Path, _ProcessFenceState] = {}


def _state_for(path: Path) -> _ProcessFenceState:
    with _STATES_GUARD:
        return _STATES.setdefault(path, _ProcessFenceState())


def _open_lock_file(path: Path) -> BinaryIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    try:
        # Do not read byte zero to decide whether initialization is needed.
        # On Windows an existing owner has locked that byte, and a contender's
        # read would fail before it ever reaches the non-blocking lock/retry
        # loop.  Seeking to the end inspects only the file offset/size.
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        return handle
    except BaseException:
        handle.close()
        raise


def _acquire_os_lock(
    path: Path,
    *,
    deadline: float,
    poll_seconds: float,
) -> BinaryIO:
    handle = _open_lock_file(path)
    try:
        while True:
            try:
                _try_lock_file(handle)
                return handle
            except OSError as exc:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DispatchFenceTimeout(
                        f"timed out waiting for execution dispatch fence {path}"
                    ) from exc
                time.sleep(min(poll_seconds, remaining))
    except BaseException:
        handle.close()
        raise


@contextmanager
def execution_dispatch_fence(
    database: str | Path,
    *,
    timeout_seconds: float = DEFAULT_DISPATCH_FENCE_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_DISPATCH_FENCE_POLL_SECONDS,
) -> Iterator[Path]:
    """Hold the database's re-entrant, crash-released execution fence.

    The timeout covers both a competing thread in this process and a competing
    process.  Nested acquisition by the owning thread reuses the same OS lock,
    which lets a fenced dispatch invoke fail-closed containment without
    deadlocking itself.
    """
    timeout = _finite_nonnegative_seconds(
        timeout_seconds, name="timeout_seconds"
    )
    poll = _finite_nonnegative_seconds(poll_seconds, name="poll_seconds")
    if poll == 0:
        raise ValueError("poll_seconds must be greater than zero")

    path = dispatch_fence_path(database)
    state = _state_for(path)
    deadline = time.monotonic() + timeout
    if not state.gate.acquire(timeout=max(0.0, deadline - time.monotonic())):
        raise DispatchFenceTimeout(
            f"timed out waiting for execution dispatch fence {path}"
        )

    entered = False
    try:
        if state.depth == 0:
            state.handle = _acquire_os_lock(
                path,
                deadline=deadline,
                poll_seconds=poll,
            )
        elif state.handle is None:
            raise RuntimeError("dispatch fence re-entry has no OS lock handle")
        state.depth += 1
        entered = True
        yield path
    finally:
        try:
            if entered:
                state.depth -= 1
                if state.depth == 0:
                    handle = state.handle
                    state.handle = None
                    if handle is None:
                        raise RuntimeError("dispatch fence lost its OS lock handle")
                    try:
                        _unlock_file(handle)
                    finally:
                        handle.close()
        finally:
            state.gate.release()
