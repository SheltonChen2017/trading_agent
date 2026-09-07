"""Narrow regular-file I/O for authenticated ARV2 artifacts.

This is the only module in the B2 admission and parent-reauthentication chain
allowed to import the restricted ``os`` surface for artifact reads and exact
create-if-absent persistence.  The
pre-existing dataset capability importer is separate.  This public facade
exposes bytes and paths only; it exposes no descriptor, directory, process, or
network capability.  Its sole write primitive creates one exact same-parent
regular artifact atomically and never replaces existing bytes.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path


class ArtifactIOError(ValueError):
    """An authenticated metadata artifact is unsafe, unstable, or unreadable."""


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


def read_stable_regular(
    path: Path, *, name: str, maximum_bytes: int
) -> tuple[Path, bytes]:
    """Read one exact bounded regular file twice without following a leaf link."""
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
    return resolved, first


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


def _require_private_single_link(path: Path, *, name: str) -> None:
    """Require a private regular destination owned by this POSIX process."""
    try:
        metadata = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ArtifactIOError(f"{name} destination metadata is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ArtifactIOError(f"{name} destination must be a regular file")
    # Windows st_mode reports synthesized 0666/0444 permission bits rather
    # than the file's ACL, so POSIX privacy bits are meaningful only off NT.
    if os.name != "nt" and stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ArtifactIOError(f"{name} destination permissions are not private")
    if os.name != "nt" and hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise ArtifactIOError(f"{name} destination owner changed")
    if metadata.st_nlink != 1:
        raise ArtifactIOError(f"{name} destination link count changed")


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
    writer.  Partial, different, linked-to-other-inode, or non-private residue
    is preserved.  This is bounded crash recovery, not an adversary-safe
    general-purpose directory deletion primitive.
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
                    and (is_destination_inode or is_exact_orphan)
                ):
                    try:
                        os.unlink(stale)
                    except FileNotFoundError:
                        continue
                    except OSError as exc:
                        raise ArtifactIOError(
                            f"{name} stale temporary cleanup failed"
                        ) from exc
    except OSError as exc:
        raise ArtifactIOError(f"{name} recovery inventory failed") from exc


def create_new_regular_atomically(
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
        try:
            os.unlink(temporary)
        except OSError as exc:
            raise ArtifactIOError(f"{name} temporary cleanup failed") from exc
        temporary = None
        _recover_stale_atomic_links(
            parent,
            destination,
            payload,
            candidate_name=candidate.name,
            name=name,
            maximum_bytes=maximum_bytes,
        )
        _fsync_directory(parent, name=name)
        resolved, current = read_stable_regular(
            destination, name=name, maximum_bytes=maximum_bytes
        )
        if current != payload:
            raise ArtifactIOError(f"{name} changed after atomic creation")
        _require_private_single_link(resolved, name=name)
        return resolved
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
