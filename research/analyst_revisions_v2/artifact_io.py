"""Narrow regular-file I/O for authenticated ARV2 artifacts.

This is the only module in the B2 admission and parent-reauthentication chain
allowed to import the restricted ``os`` surface for artifact reads and exact
create-if-absent persistence.  The pre-existing dataset capability importer is
separate.  This facade exposes bytes and paths plus one importer-scoped,
lane-internal child-reset registration hook; it exposes no descriptor,
directory, process-control, or network capability.  Its sole write primitive
creates one exact same-parent regular artifact atomically and never replaces
existing bytes.
"""
from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path


class ArtifactIOError(ValueError):
    """An authenticated metadata artifact is unsafe, unstable, or unreadable."""


_ATOMIC_CREATE_LOCK = threading.RLock()
_ATOMIC_LINK_SETTLE_ATTEMPTS = 50
_ATOMIC_LINK_SETTLE_SECONDS = 0.01
_PROCESS_LOCAL_AFTER_FORK_RESETS: list[object] = []


def _register_process_local_after_fork(callback: object) -> None:
    """Register one internal child reset without exporting the ``os`` module."""
    if not callable(callback) or callback in _PROCESS_LOCAL_AFTER_FORK_RESETS:
        raise ArtifactIOError("process-local child reset registration is invalid")
    _PROCESS_LOCAL_AFTER_FORK_RESETS.append(callback)


def _reset_atomic_create_lock_after_fork() -> None:
    """Discard locks and authorities whose owning process did not survive."""
    global _ATOMIC_CREATE_LOCK
    _ATOMIC_CREATE_LOCK = threading.RLock()
    for callback in tuple(_PROCESS_LOCAL_AFTER_FORK_RESETS):
        callback()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_atomic_create_lock_after_fork)


def _is_link_like(path: Path) -> bool:
    try:
        return path.is_symlink() or (
            path.is_junction() if hasattr(path, "is_junction") else False
        )
    except OSError:
        return True


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


def _bounded_descriptor_read(
    descriptor: int, *, name: str, maximum_bytes: int
) -> bytes:
    chunks: list[bytes] = []
    remaining = maximum_bytes + 1
    try:
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except OSError as exc:
        raise ArtifactIOError(f"{name} is unreadable") from exc
    payload = b"".join(chunks)
    if len(payload) > maximum_bytes:
        raise ArtifactIOError(f"{name} exceeds the authenticated artifact size limit")
    return payload


def _read_regular_once(
    path: Path, *, name: str, maximum_bytes: int
) -> tuple[bytes, tuple[int, int, int, int]]:
    flags = (
        os.O_RDONLY
        | (os.O_CLOEXEC if hasattr(os, "O_CLOEXEC") else 0)
        | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
        | (os.O_NONBLOCK if hasattr(os, "O_NONBLOCK") else 0)
        | (os.O_BINARY if hasattr(os, "O_BINARY") else 0)
    )
    try:
        descriptor = os.open(path, flags)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ArtifactIOError(f"{name} must be a regular file")
            if before.st_size > maximum_bytes:
                raise ArtifactIOError(
                    f"{name} exceeds the authenticated artifact size limit"
                )
            payload = _bounded_descriptor_read(
                descriptor, name=name, maximum_bytes=maximum_bytes
            )
            after = os.fstat(descriptor)
            named = os.stat(path, follow_symlinks=False)
        finally:
            os.close(descriptor)
    except ArtifactIOError:
        raise
    except OSError as exc:
        raise ArtifactIOError(f"{name} is unreadable") from exc
    if (
        len(payload) != before.st_size
        or not stat.S_ISREG(named.st_mode)
        or _file_identity(before) != _file_identity(after)
        or _file_identity(after) != _file_identity(named)
    ):
        raise ArtifactIOError(f"{name} changed while being read")
    return payload, _file_identity(after)


def _read_stable_regular_with_identity(
    path: Path, *, name: str, maximum_bytes: int
) -> tuple[Path, bytes, tuple[int, int, int, int]]:
    """Read one exact bounded regular file twice and retain its identity."""
    if type(maximum_bytes) is not int or maximum_bytes < 1:
        raise ArtifactIOError("artifact size limit must be a positive integer")
    candidate = Path(path)
    absolute = candidate.absolute()
    if any(_is_link_like(item) for item in (absolute, *absolute.parents)):
        raise ArtifactIOError(f"{name} must not traverse a link")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ArtifactIOError(f"{name} is unavailable") from exc
    if _is_link_like(resolved):
        raise ArtifactIOError(f"{name} must be a regular file")
    first, first_identity = _read_regular_once(
        resolved, name=name, maximum_bytes=maximum_bytes
    )
    second, second_identity = _read_regular_once(
        resolved, name=name, maximum_bytes=maximum_bytes
    )
    if first_identity != second_identity or first != second:
        raise ArtifactIOError(f"{name} changed while being read")
    return resolved, first, second_identity


def read_stable_regular(
    path: Path, *, name: str, maximum_bytes: int
) -> tuple[Path, bytes]:
    """Read one exact bounded regular file twice without following a leaf link."""
    resolved, payload, _ = _read_stable_regular_with_identity(
        path,
        name=name,
        maximum_bytes=maximum_bytes,
    )
    return resolved, payload


def revalidate_regular(
    path: Path, payload: bytes, *, name: str, maximum_bytes: int
) -> None:
    """Re-read and compare one previously authenticated bounded artifact."""
    if type(payload) is not bytes:
        raise ArtifactIOError(f"{name} authenticated payload must be bytes")
    absolute = Path(path).absolute()
    if any(_is_link_like(item) for item in (absolute, *absolute.parents)):
        raise ArtifactIOError(f"{name} changed or disappeared")
    current, _ = _read_regular_once(
        Path(path), name=name, maximum_bytes=maximum_bytes
    )
    if current != payload:
        raise ArtifactIOError(f"{name} changed after authentication")


def _write_descriptor_all(descriptor: int, payload: bytes, *, name: str) -> None:
    offset = 0
    while offset < len(payload):
        try:
            written = os.write(descriptor, payload[offset:])
        except InterruptedError:
            continue
        except OSError as exc:
            raise ArtifactIOError(f"{name} could not be written") from exc
        if written <= 0:
            raise ArtifactIOError(f"{name} write made no progress")
        offset += written


def _fsync_directory(path: Path, *, name: str) -> None:
    # Windows does not support opening a directory descriptor for fsync.  The
    # destination file itself is fsynced before publication; retain that
    # guarantee and make the directory barrier a documented POSIX-only step.
    if os.name == "nt":
        return
    flags = os.O_RDONLY | (os.O_DIRECTORY if hasattr(os, "O_DIRECTORY") else 0)
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise ArtifactIOError(f"{name} directory sync failed") from exc


def _require_private_single_link(
    path: Path, *, name: str, settle_attempts: int = 0
) -> tuple[int, int, int, int]:
    """Require private single-link custody after a bounded writer-settle wait."""
    for attempt in range(settle_attempts + 1):
        try:
            metadata = os.stat(path, follow_symlinks=False)
        except OSError as exc:
            raise ArtifactIOError(
                f"{name} destination metadata is unavailable"
            ) from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise ArtifactIOError(f"{name} destination must be a regular file")
        # Windows st_mode reports synthesized 0666/0444 permission bits rather
        # than the file's ACL, so POSIX privacy bits are meaningful only off NT.
        if os.name != "nt" and stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ArtifactIOError(f"{name} destination permissions are not private")
        if (
            os.name != "nt"
            and hasattr(os, "getuid")
            and metadata.st_uid != os.getuid()
        ):
            raise ArtifactIOError(f"{name} destination owner changed")
        if metadata.st_nlink == 1:
            return _file_identity(metadata)
        if attempt < settle_attempts:
            time.sleep(_ATOMIC_LINK_SETTLE_SECONDS)
    raise ArtifactIOError(f"{name} destination link count changed")


def _reserved_temporary_owner_pid(
    entry_name: str, *, prefix: str, suffix: str
) -> int | None:
    body = entry_name[len(prefix) : -len(suffix)]
    pid_text, separator, attempt_text = body.partition("-")
    if (
        not separator
        or not pid_text.isascii()
        or not pid_text.isdigit()
        or len(pid_text) > 10
        or not attempt_text.isascii()
        or not attempt_text.isdigit()
        or len(attempt_text) != 4
    ):
        return None
    owner_pid = int(pid_text)
    attempt = int(attempt_text)
    return (
        owner_pid
        if (
            0 < owner_pid <= 4_294_967_295
            and pid_text == str(owner_pid)
            and 0 <= attempt < 1024
        )
        else None
    )


def _recover_stale_atomic_links(
    parent: Path,
    destination: Path,
    payload: bytes,
    *,
    candidate_name: str,
    name: str,
    maximum_bytes: int,
) -> None:
    """Clean same-owner exact residue in the helper's reserved namespace.

    The directory is already link-free and this namespace is private to this
    writer.  Canonical private residue that is already a second name for the
    destination is safe to remove regardless of its originating PID.  Once
    the exact destination exists, any canonical private same-payload
    single-link orphan is also safe to remove: a concurrent writer treats its
    missing temporary as an idempotent success only after authenticating that
    destination.  An unlink-denied single-link orphan is harmless and remains
    for its writer; post-link cleanup failure remains fatal because it blocks
    single-link custody.  Partial, different, linked-to-other-inode,
    non-private, and malformed residue is preserved.  This is bounded
    cooperative crash recovery, not an adversary-safe general-purpose
    directory deletion primitive.
    """
    try:
        destination_stat = os.stat(destination, follow_symlinks=False)
        entries = os.scandir(parent)
    except OSError as exc:
        raise ArtifactIOError(f"{name} recovery inventory is unavailable") from exc
    prefix = f".{candidate_name}.atomic-"
    suffix = ".tmp"
    matching = 0
    try:
        with entries:
            for entry in entries:
                if not entry.name.startswith(prefix) or not entry.name.endswith(suffix):
                    continue
                matching += 1
                if matching > 4096:
                    raise ArtifactIOError(
                        f"{name} recovery inventory exceeds the bounded limit"
                    )
                owner_pid = _reserved_temporary_owner_pid(
                    entry.name, prefix=prefix, suffix=suffix
                )
                if owner_pid is None:
                    continue
                stale = parent / entry.name
                try:
                    stale_stat = os.stat(stale, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise ArtifactIOError(
                        f"{name} stale temporary metadata is unavailable"
                    ) from exc
                is_destination_inode = (
                    stale_stat.st_dev == destination_stat.st_dev
                    and stale_stat.st_ino == destination_stat.st_ino
                )
                is_private = (
                    os.name == "nt"
                    or stat.S_IMODE(stale_stat.st_mode) & 0o077 == 0
                )
                is_owned = (
                    os.name == "nt"
                    or not hasattr(os, "getuid")
                    or stale_stat.st_uid == os.getuid()
                )
                if (
                    stat.S_ISREG(stale_stat.st_mode)
                    and is_private
                    and is_owned
                    and is_destination_inode
                ):
                    try:
                        os.unlink(stale)
                    except FileNotFoundError:
                        continue
                    except OSError as exc:
                        raise ArtifactIOError(
                            f"{name} stale temporary cleanup failed"
                        ) from exc
                    continue
                is_exact_orphan = False
                if (
                    stat.S_ISREG(stale_stat.st_mode)
                    and stale_stat.st_nlink == 1
                    and is_private
                    and is_owned
                ):
                    try:
                        _, stale_payload = read_stable_regular(
                            stale,
                            name=name,
                            maximum_bytes=maximum_bytes,
                        )
                    except ArtifactIOError:
                        stale_payload = b""
                    is_exact_orphan = stale_payload == payload
                if (
                    stat.S_ISREG(stale_stat.st_mode)
                    and is_private
                    and is_owned
                    and is_exact_orphan
                ):
                    try:
                        os.unlink(stale)
                    except FileNotFoundError:
                        continue
                    except OSError:
                        # A live Windows writer may not have opened its temp
                        # with delete sharing.  This nlink=1 orphan cannot
                        # weaken the already published destination's custody.
                        continue
    except OSError as exc:
        raise ArtifactIOError(f"{name} recovery inventory failed") from exc


def _finalize_published_destination(
    parent: Path,
    destination: Path,
    payload: bytes,
    *,
    candidate_name: str,
    name: str,
    maximum_bytes: int,
) -> Path:
    """Recover cooperative residue and authenticate final durable custody."""
    _recover_stale_atomic_links(
        parent,
        destination,
        payload,
        candidate_name=candidate_name,
        name=name,
        maximum_bytes=maximum_bytes,
    )
    _fsync_directory(parent, name=name)
    _require_private_single_link(
        destination,
        name=name,
        settle_attempts=_ATOMIC_LINK_SETTLE_ATTEMPTS,
    )
    # A foreign writer may have removed the last temporary hard link while
    # this process waited.  Persist that directory transition even if the
    # foreign writer crashes before reaching its own sync barrier.
    _fsync_directory(parent, name=name)
    resolved, current, read_identity = _read_stable_regular_with_identity(
        destination, name=name, maximum_bytes=maximum_bytes
    )
    if current != payload:
        raise ArtifactIOError(f"{name} changed after atomic creation")
    custody_identity = _require_private_single_link(resolved, name=name)
    if custody_identity != read_identity:
        raise ArtifactIOError(f"{name} changed after atomic creation")
    return resolved


def _create_new_regular_atomically_unlocked(
    path: Path,
    payload: bytes,
    *,
    name: str,
    maximum_bytes: int,
) -> Path:
    """Create exact bytes atomically; same bytes retry, different bytes refuse."""
    if type(payload) is not bytes or not payload:
        raise ArtifactIOError(f"{name} payload must be nonempty bytes")
    if type(maximum_bytes) is not int or maximum_bytes < 1:
        raise ArtifactIOError("artifact size limit must be a positive integer")
    if len(payload) > maximum_bytes:
        raise ArtifactIOError(f"{name} exceeds the authenticated artifact size limit")
    candidate = Path(path)
    if candidate.name in {"", ".", ".."}:
        raise ArtifactIOError(f"{name} path is invalid")
    absolute_parent = candidate.parent.absolute()
    if any(
        _is_link_like(item)
        for item in (absolute_parent, *absolute_parent.parents)
    ):
        raise ArtifactIOError(f"{name} must not traverse a link")
    try:
        parent = candidate.parent.resolve(strict=True)
        parent_stat = os.stat(parent, follow_symlinks=False)
    except OSError as exc:
        raise ArtifactIOError(f"{name} parent is unavailable") from exc
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise ArtifactIOError(f"{name} parent must be a directory")
    destination = parent / candidate.name
    try:
        os.stat(destination, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ArtifactIOError(f"{name} destination metadata is unavailable") from exc
    else:
        _, existing = read_stable_regular(
            destination,
            name=name,
            maximum_bytes=maximum_bytes,
        )
        if existing != payload:
            raise ArtifactIOError(
                f"{name} destination already contains different bytes"
            )
        return _finalize_published_destination(
            parent,
            destination,
            payload,
            candidate_name=candidate.name,
            name=name,
            maximum_bytes=maximum_bytes,
        )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | (os.O_CLOEXEC if hasattr(os, "O_CLOEXEC") else 0)
        | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
        | (os.O_BINARY if hasattr(os, "O_BINARY") else 0)
    )
    temporary: Path | None = None
    descriptor = -1
    try:
        for attempt in range(1024):
            proposed = parent / (
                f".{candidate.name}.atomic-{os.getpid()}-{attempt:04d}.tmp"
            )
            try:
                descriptor = os.open(proposed, flags, 0o600)
            except FileExistsError:
                continue
            temporary = proposed
            break
        if temporary is None or descriptor < 0:
            raise ArtifactIOError(f"{name} has no available temporary slot")
        try:
            if os.name != "nt":
                if not hasattr(os, "fchmod"):
                    raise ArtifactIOError(
                        f"{name} cannot enforce private temporary permissions"
                    )
                try:
                    os.fchmod(descriptor, 0o600)
                except OSError as exc:
                    raise ArtifactIOError(
                        f"{name} temporary permissions could not be secured"
                    ) from exc
                secured = os.fstat(descriptor)
                if stat.S_IMODE(secured.st_mode) != 0o600 or (
                    hasattr(os, "getuid") and secured.st_uid != os.getuid()
                ):
                    raise ArtifactIOError(
                        f"{name} temporary permissions are not private"
                    )
            _write_descriptor_all(descriptor, payload, name=name)
            written = os.fstat(descriptor)
            if not stat.S_ISREG(written.st_mode) or written.st_size != len(payload):
                raise ArtifactIOError(f"{name} temporary bytes are incomplete")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
            descriptor = -1
        try:
            os.link(temporary, destination, follow_symlinks=False)
        except FileExistsError:
            _, existing = read_stable_regular(
                destination, name=name, maximum_bytes=maximum_bytes
            )
            if existing != payload:
                raise ArtifactIOError(
                    f"{name} destination already contains different bytes"
                )
        except FileNotFoundError:
            # An exact same-payload writer may have cooperatively recovered
            # this fully written orphan after publishing the destination.
            try:
                _, existing = read_stable_regular(
                    destination, name=name, maximum_bytes=maximum_bytes
                )
            except ArtifactIOError as exc:
                raise ArtifactIOError(
                    f"{name} temporary disappeared before publication"
                ) from exc
            if existing != payload:
                raise ArtifactIOError(
                    f"{name} temporary disappeared before publication"
                )
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            try:
                _, published = read_stable_regular(
                    destination,
                    name=name,
                    maximum_bytes=maximum_bytes,
                )
            except ArtifactIOError as exc:
                raise ArtifactIOError(
                    f"{name} temporary cleanup failed"
                ) from exc
            if published != payload:
                raise ArtifactIOError(f"{name} temporary cleanup failed")
        except OSError as exc:
            raise ArtifactIOError(f"{name} temporary cleanup failed") from exc
        temporary = None
        return _finalize_published_destination(
            parent,
            destination,
            payload,
            candidate_name=candidate.name,
            name=name,
            maximum_bytes=maximum_bytes,
        )
    except ArtifactIOError:
        raise
    except OSError as exc:
        raise ArtifactIOError(f"{name} atomic creation failed") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def create_new_regular_atomically(
    path: Path,
    payload: bytes,
    *,
    name: str,
    maximum_bytes: int,
) -> Path:
    """Serialize and create exact bytes without replacing existing content."""
    with _ATOMIC_CREATE_LOCK:
        return _create_new_regular_atomically_unlocked(
            path,
            payload,
            name=name,
            maximum_bytes=maximum_bytes,
        )
