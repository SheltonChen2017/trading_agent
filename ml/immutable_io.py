"""Create-exclusive publication for immutable ML evidence files."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path


class ImmutableFileConflictError(ValueError):
    """A claimed immutable path already contains different bytes."""


_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[Path, threading.RLock] = {}


@contextmanager
def exclusive_file_lock(path: str | Path):
    """Block until an exclusive one-byte OS lock can be held."""
    lock_path = Path(path).resolve()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _THREAD_LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(lock_path, threading.RLock())
    with thread_lock:
        handle = open(lock_path, "a+b")
        try:
            handle.seek(0)
            if handle.read(1) == b"":
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if sys.platform == "win32":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def publish_immutable_bytes(destination: str | Path, data: bytes) -> bool:
    """Publish complete bytes without ever replacing an existing path.

    Returns ``True`` when this call creates the destination and ``False``
    for an exact idempotent retry. A hard link is the create-exclusive commit
    operation: the fully flushed temporary inode either acquires the final
    name atomically or loses to an already-published writer.
    """
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() == data:
            return False
        raise ImmutableFileConflictError(
            f"immutable destination already contains different bytes: {target}"
        )

    fd, tmp_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, target)
        except FileExistsError as exc:
            if target.read_bytes() == data:
                return False
            raise ImmutableFileConflictError(
                f"immutable destination already contains different bytes: {target}"
            ) from exc
        return True
    finally:
        temp.unlink(missing_ok=True)
