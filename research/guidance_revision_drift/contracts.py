"""One pinned, unreviewed GDR draft - never an authorization artifact.

The semantic checksum restricts this milestone to its one reviewed-by-author
payload, including exact keys/types and all unresolved/zero-access values.
Changing that payload needs a new candidate and review; supplying a new hash
or a caller-asserted approval cannot promote this class. Source integrity is
not proof of owner approval, independent review, rights or point-in-time data.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from data.hashing import canonical_json, hash_bytes


class CandidateError(ValueError):
    """The proposed GDR contract or its source documents failed validation."""


MAX_CANDIDATE_BYTES = 65_536
MAX_SOURCE_DOCUMENT_BYTES = 1_048_576
CANDIDATE_SHA256 = "b52aedd6ca6dea4a14bc46ddb6c09a6d36bbf994fc21edb9ddb916194f03ad3c"
_SPEC_PATH = Path(__file__).parent / "specs" / "gdr0a.draft.json"


def _reject_number(_: str) -> None:
    raise CandidateError("candidate numbers must be integers or exact decimal text")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateError("duplicate candidate JSON key")
        result[key] = value
    return result


def _decode(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_CANDIDATE_BYTES:
        raise CandidateError("candidate must be nonempty bounded bytes")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CandidateError("candidate must be strict UTF-8 JSON without duplicates or floats") from exc
    if type(value) is not dict:
        raise CandidateError("candidate root must be an object")
    return value


def _canonical(raw: bytes) -> bytes:
    try:
        return canonical_json(_decode(raw)).encode("utf-8")
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CandidateError("candidate cannot be represented as strict canonical JSON") from exc


@dataclass(frozen=True, slots=True)
class Candidate:
    """Immutable canonical bytes of the sole GDR-0A draft, without a final LF."""

    canonical_bytes: bytes

    def __post_init__(self) -> None:
        canonical = _canonical(self.canonical_bytes)
        if canonical != self.canonical_bytes:
            raise CandidateError("direct construction requires canonical bytes without a final LF")
        if hash_bytes(canonical) != CANDIDATE_SHA256:
            raise CandidateError("candidate differs from the pinned GDR-0A draft")

    @classmethod
    def from_bytes(cls, raw: bytes) -> Candidate:
        """Accept JSON whitespace/key order differences, but no semantic change."""
        return cls(_canonical(raw))

    @property
    def sha256(self) -> str:
        return hash_bytes(self.canonical_bytes)

    def to_dict(self) -> dict[str, object]:
        """Return a fresh mutable projection, never a reference into the contract."""
        return _decode(self.canonical_bytes)


def _read_regular_file(path: Path, limit: int) -> bytes:
    """Bound local reads and refuse redirected/nonregular leaf files.

    The descriptor is checked again after open, including identity, so a
    replacement between stat/open cannot silently change the inspected file.
    Nonblocking/no-follow flags additionally protect that race where available.
    Content hashes, not metadata, establish the eventual byte identity.
    """
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise CandidateError("GDR input must be a bounded regular file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size > limit
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise CandidateError("GDR input changed or is not a bounded regular file")
            chunks = []
            remaining = limit + 1
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise CandidateError("cannot read a GDR input file") from exc
    if len(raw) > limit:
        raise CandidateError("GDR input exceeds its byte limit")
    return raw


def load_candidate() -> Candidate:
    """Read only the packaged proposal; no environment, credentials or providers."""
    return Candidate.from_bytes(_read_regular_file(_SPEC_PATH, MAX_CANDIDATE_BYTES))


def verify_source_documents(candidate: Candidate, repository_root: Path) -> None:
    """Check the two pinned planning files; a match grants no authority."""
    if type(candidate) is not Candidate:
        raise CandidateError("source verification requires an exact Candidate")
    checked = Candidate(candidate.canonical_bytes)
    for document in checked.to_dict()["source_documents"]:
        raw = _read_regular_file(
            repository_root / document["path"], MAX_SOURCE_DOCUMENT_BYTES,
        )
        if hash_bytes(raw) != document["sha256"]:
            raise CandidateError("GDR planning document hash mismatch")
