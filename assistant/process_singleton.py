"""Exclusive process lock for long-running operational workers.

Task Scheduler ``MultipleInstances=IgnoreNew`` only suppresses a second
*task instance* while the scheduler still believes the first is running.
When a console-hosted worker is orphaned (process alive, task no longer
tracked as Running), a self-heal tick starts another process. IgnoreNew
does not see a conflict, so two monitors share one database.

This lock is the process-level backstop: a second worker exits before it
touches the store or broker.
"""
from __future__ import annotations

import atexit
import sys
from pathlib import Path


class ProcessSingletonError(RuntimeError):
    """Another process already holds the named singleton lock."""


def lock_path_for(database: str | Path, name: str) -> Path:
    """Place locks beside the operator database, never inside git."""
    if not name or any(ch in name for ch in ("/", "\\", "..")):
        raise ValueError(f"invalid singleton name: {name!r}")
    return Path(database).expanduser().resolve().parent / "locks" / f"{name}.lock"


class ProcessSingleton:
    """Hold an exclusive OS file lock for the lifetime of this process."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = Path(lock_path)
        self._fh = None
        self._held = False

    def acquire(self) -> None:
        if self._held:
            return
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_path, "a+b")
        try:
            fh.seek(0)
            if fh.read(1) == b"":
                fh.write(b"\0")
                fh.flush()
            fh.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            raise ProcessSingletonError(
                f"another instance already holds {self.lock_path}"
            ) from exc
        self._fh = fh
        self._held = True
        atexit.register(self.release)

    def release(self) -> None:
        if not self._held or self._fh is None:
            return
        fh = self._fh
        self._fh = None
        self._held = False
        try:
            fh.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            fh.close()


def acquire_process_singleton(database: str | Path, name: str) -> ProcessSingleton:
    """Acquire or raise ``ProcessSingletonError``."""
    lock = ProcessSingleton(lock_path_for(database, name))
    lock.acquire()
    return lock
