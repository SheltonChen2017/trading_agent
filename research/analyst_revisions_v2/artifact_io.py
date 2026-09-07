"""Narrow, bounded regular-file reads for authenticated ARV2 metadata.

This is the only module in the B2 admission and parent-reauthentication chain
allowed to import the restricted ``os`` surface for artifact reads.  The
pre-existing dataset capability importer is separate.  This public facade
exposes bytes and paths only; it exposes no descriptor, directory, process,
network, or write capability.
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
