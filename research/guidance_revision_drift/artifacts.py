"""No-overwrite storage for explicitly supplied local synthetic JSON artifacts.

The owner must control the output directory. Content addressing detects byte
changes; this is not an authorization registry or an anti-rollback trust root.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile

from data.hashing import hash_bytes
from research.guidance_revision_drift.contracts import (
    CandidateError, MAX_CANDIDATE_BYTES, _decode, _read_regular_file,
)


class FixtureArtifactError(ValueError):
    """A synthetic artifact could not be stored or verified without overwrite."""


def _checked(raw: bytes) -> bytes:
    try:
        body = _decode(raw)
    except CandidateError as exc:
        raise FixtureArtifactError("artifact must be bounded strict JSON") from exc
    schema = body.get("schema")
    if type(schema) is not str or not schema.startswith("gdr.synthetic."):
        raise FixtureArtifactError("only explicitly synthetic GDR artifacts are supported")
    return raw


def publish_fixture(directory: Path, raw: bytes) -> Path:
    """Publish complete bytes atomically; a conflicting existing file refuses.

    A crash before publication leaves, at worst, a private staging file, never
    a partially published content-addressed artifact. No output path comes
    from an artifact field. No source/network read is initiated here.
    """
    _checked(raw)
    directory = Path(directory)
    temporary: str | None = None
    try:
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise FixtureArtifactError("existing non-symlink output directory required")
        directory = directory.resolve(strict=True)
        destination = directory / (hash_bytes(raw) + ".json")
        descriptor, temporary = tempfile.mkstemp(prefix=".gdr-fixture-", suffix=".staging", dir=directory)
        try:
            remaining = memoryview(raw)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise FixtureArtifactError("incomplete artifact write")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if _read_regular_file(destination, MAX_CANDIDATE_BYTES) != raw:
                raise FixtureArtifactError("existing artifact has different bytes")
        if _read_regular_file(destination, MAX_CANDIDATE_BYTES) != raw:
            raise FixtureArtifactError("published artifact verification failed")
        return destination
    except (OSError, CandidateError) as exc:
        raise FixtureArtifactError("cannot publish synthetic artifact") from exc
    finally:
        if temporary is not None:
            # Only this invocation's exclusive staging file is removed.
            Path(temporary).unlink(missing_ok=True)


def read_fixture(path: Path) -> bytes:
    path = Path(path)
    try:
        raw = _read_regular_file(path, MAX_CANDIDATE_BYTES)
        if path.name != hash_bytes(raw) + ".json":
            raise FixtureArtifactError("artifact filename/content hash mismatch")
        return _checked(raw)
    except CandidateError as exc:
        raise FixtureArtifactError("invalid synthetic artifact file") from exc
