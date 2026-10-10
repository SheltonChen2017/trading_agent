"""Pure append-only fixture archive, not a prospective collection service.

Each entry commits its predecessor, normalized payload, bootstrap disposition
and sequence. Parsing requires a separately retained expected head to detect
truncation/reordering; the head is an integrity checkpoint, not a trust root.
No method accesses files, clocks, credentials, a provider, or operational state.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from data.hashing import canonical_json, hash_bytes
from research.guidance_revision_drift.events import (
    MAX_EVENTS, EventBook, EventError, NormalizedDisclosure, decode_fixture_object,
)

MAX_ARCHIVE_BYTES = 8_388_608
_SCHEMA = "gdr.synthetic.archive.v1"
_GENESIS = hash_bytes(b"gdr.synthetic.archive.v1:empty")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class ArchiveError(ValueError):
    """A fixture chain or its expected immutable checkpoint is invalid."""


def _digest(value: object) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ArchiveError("archive digest must be lowercase SHA-256 text")
    return value


def _entry(sequence: int, previous: str, record: NormalizedDisclosure, bootstrap: bool) -> dict:
    content = {"sequence": sequence, "previous_sha256": previous,
               "record_sha256": record.sha256, "record": record.to_dict(),
               "bootstrap": bootstrap}
    return {**content, "entry_sha256": hash_bytes(canonical_json(content).encode("utf-8"))}


@dataclass(frozen=True, slots=True)
class FixtureArchive:
    """A bounded persistent-value chain; append returns a distinct value.

    Conflicting versions remain in the archive and are quarantined by replay.
    Exact repeated deliveries are idempotent (they do not manufacture versions).
    Calling a payload synthetic does not verify its real-world origin.
    """

    entries: tuple[tuple[NormalizedDisclosure, bool], ...] = ()

    def __post_init__(self) -> None:
        try:
            checked = EventBook(self.entries)
        except EventError as exc:
            raise ArchiveError("invalid fixture archive observations") from exc
        hashes = [record.sha256 for record, _ in checked.entries]
        if len(set(hashes)) != len(hashes):
            raise ArchiveError("archive contains duplicate payloads")
        object.__setattr__(self, "entries", checked.entries)

    @property
    def book(self) -> EventBook:
        return EventBook(FixtureArchive(self.entries).entries)

    def append(self, record: NormalizedDisclosure, *, bootstrap: bool = False) -> FixtureArchive:
        checked = FixtureArchive(self.entries)
        if type(record) is not NormalizedDisclosure or type(bootstrap) is not bool:
            raise ArchiveError("append requires an exact disclosure and boolean")
        try:
            record = NormalizedDisclosure(record.canonical_bytes)
        except EventError as exc:
            raise ArchiveError("invalid normalized disclosure") from exc
        matches = [old_bootstrap for old, old_bootstrap in checked.entries
                   if old.canonical_bytes == record.canonical_bytes]
        if matches:
            if matches[0] != bootstrap:
                raise ArchiveError("duplicate cannot change its bootstrap disposition")
            return checked
        return FixtureArchive(checked.entries + ((record, bootstrap),))

    def to_dict(self) -> dict:
        checked = FixtureArchive(self.entries)
        entries = []
        previous = _GENESIS
        for sequence, (record, bootstrap) in enumerate(checked.entries, 1):
            item = _entry(sequence, previous, record, bootstrap)
            entries.append(item)
            previous = item["entry_sha256"]
        return {"schema": _SCHEMA, "provenance": "synthetic_unverified",
                "entries": entries, "head_sha256": previous}

    @property
    def head_sha256(self) -> str:
        return self.to_dict()["head_sha256"]

    def to_bytes(self) -> bytes:
        raw = canonical_json(self.to_dict()).encode("utf-8")
        if len(raw) > MAX_ARCHIVE_BYTES:
            raise ArchiveError("archive exceeds byte limit")
        return raw

    @classmethod
    def from_bytes(cls, raw: bytes, *, expected_head: str) -> FixtureArchive:
        _digest(expected_head)
        try:
            values = decode_fixture_object(raw, MAX_ARCHIVE_BYTES)
            if set(values) != {"schema", "provenance", "entries", "head_sha256"}:
                raise ArchiveError("archive has missing or unknown fields")
            if values["schema"] != _SCHEMA or values["provenance"] != "synthetic_unverified":
                raise ArchiveError("only unverified synthetic archives are supported")
            items = values["entries"]
            if type(items) is not list or len(items) > MAX_EVENTS:
                raise ArchiveError("archive entries must be a bounded list")
            previous, observations = _GENESIS, []
            seen_payloads: set[str] = set()
            for sequence, item in enumerate(items, 1):
                if type(item) is not dict or set(item) != {
                    "sequence", "previous_sha256", "record_sha256", "record", "bootstrap", "entry_sha256"
                }:
                    raise ArchiveError("entry has missing or unknown fields")
                if type(item["sequence"]) is not int or item["sequence"] != sequence:
                    raise ArchiveError("entry sequence is not contiguous")
                if type(item["bootstrap"]) is not bool:
                    raise ArchiveError("entry bootstrap must be boolean")
                for name in ("previous_sha256", "record_sha256", "entry_sha256"):
                    _digest(item[name])
                record = NormalizedDisclosure.from_dict(item["record"])
                if record.sha256 in seen_payloads:
                    raise ArchiveError("archive contains duplicate payloads")
                seen_payloads.add(record.sha256)
                if item != _entry(sequence, previous, record, item["bootstrap"]):
                    raise ArchiveError("archive chain or payload hash mismatch")
                observations.append((record, item["bootstrap"]))
                previous = item["entry_sha256"]
            if _digest(values["head_sha256"]) != previous or previous != expected_head:
                raise ArchiveError("archive does not match retained head checkpoint")
            return cls(tuple(observations))
        except EventError as exc:
            raise ArchiveError("malformed archive or normalized payload") from exc
