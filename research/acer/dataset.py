"""Immutable, content-addressed persistence for normalized ACER events.

The dataset is the frozen boundary between "vendor snapshot" and anything
that could ever become research. Its identity is derived from its content
and its lineage, so a dataset built from a different snapshot, a different
era rule, or a different normalization outcome is a *different dataset* with
a different directory name, and can never silently overwrite an earlier one.

Writes go through ``ml.immutable_io.publish_immutable_bytes``: atomic, and
refusing rather than replacing when a path already holds different bytes.
An exact rebuild of the same content is an idempotent no-op, which is what
makes the build safely re-runnable.

Coverage summaries live here rather than in a script so they are testable.
A summary counts rows and reports refusal reasons; it computes no return,
joins no price, and ranks nothing. It is a data-quality measurement, not a
research look.
"""
from __future__ import annotations

import collections
import dataclasses
import json
import re
from pathlib import Path

from ml.hashing import canonical_json, hash_bytes, hash_payload
from ml.immutable_io import ImmutableFileConflictError, publish_immutable_bytes

from research.acer.normalize import ERA_SPLIT_YEAR, NormalizedEvent, Refusal

DATASET_KIND = "acer-analyst-events"
DATASET_CONTRACT_VERSION = 2
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LINEAGE_KEYS = (
    "kind",
    "contract_version",
    "source_snapshot_name",
    "source_manifest_sha256",
    "era_split_year",
    "event_count",
    "refusal_count",
    "events_sha256",
    "refusals_sha256",
)


class DatasetConflictError(ValueError):
    """A dataset path exists and holds different content."""


@dataclasses.dataclass(frozen=True, init=False)
class ValidatedDatasetIdentity:
    """A legacy identity whose complete record and both blobs were verified."""

    kind: str
    contract_version: int
    source_snapshot_name: str
    source_manifest_sha256: str
    era_split_year: int
    event_count: int
    refusal_count: int
    events_sha256: str
    refusals_sha256: str
    content_hash: str
    dataset_id: str

    @classmethod
    def _from_verified(cls, identity: dict) -> "ValidatedDatasetIdentity":
        instance = object.__new__(cls)
        for field in dataclasses.fields(cls):
            object.__setattr__(instance, field.name, identity[field.name])
        return instance

    def to_record(self) -> dict:
        return {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
        }


_IDENTITY_KEYS = frozenset((*_LINEAGE_KEYS, "content_hash", "dataset_id"))


def validate_identity_record(
    identity: object,
    *,
    events_bytes: bytes,
    refusals_bytes: bytes,
    expected_directory_name: str | None = None,
) -> ValidatedDatasetIdentity:
    """Authenticate an exact legacy identity record against its full content."""
    if not isinstance(identity, dict) or set(identity) != _IDENTITY_KEYS:
        raise DatasetConflictError(
            "REFUSED: dataset identity has missing or unknown fields"
        )
    if type(events_bytes) is not bytes or type(refusals_bytes) is not bytes:
        raise DatasetConflictError("REFUSED: dataset content must be exact bytes")
    lineage = {key: identity[key] for key in _LINEAGE_KEYS}
    if lineage["kind"] != DATASET_KIND:
        raise DatasetConflictError("REFUSED: dataset identity has an unknown kind")
    if type(lineage["contract_version"]) is not int or lineage["contract_version"] != DATASET_CONTRACT_VERSION:
        raise DatasetConflictError("REFUSED: dataset contract version is unsupported")
    if type(lineage["era_split_year"]) is not int or lineage["era_split_year"] != ERA_SPLIT_YEAR:
        raise DatasetConflictError("REFUSED: dataset era boundary is unsupported")
    snapshot_name = lineage["source_snapshot_name"]
    if (
        not isinstance(snapshot_name, str)
        or not snapshot_name
        or snapshot_name != snapshot_name.strip()
    ):
        raise DatasetConflictError("REFUSED: source snapshot name is noncanonical")
    for hash_key in ("source_manifest_sha256", "events_sha256", "refusals_sha256"):
        value = lineage[hash_key]
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise DatasetConflictError(f"REFUSED: {hash_key} is invalid")
    for count_key in ("event_count", "refusal_count"):
        value = lineage[count_key]
        if type(value) is not int or value < 0:
            raise DatasetConflictError(f"REFUSED: {count_key} is invalid")
    if hash_bytes(events_bytes) != lineage["events_sha256"]:
        raise DatasetConflictError("REFUSED: events content does not match events_sha256")
    if hash_bytes(refusals_bytes) != lineage["refusals_sha256"]:
        raise DatasetConflictError("REFUSED: refusal content does not match refusals_sha256")
    if len(events_bytes.splitlines()) != lineage["event_count"]:
        raise DatasetConflictError("REFUSED: event_count does not match content")
    if len(refusals_bytes.splitlines()) != lineage["refusal_count"]:
        raise DatasetConflictError("REFUSED: refusal_count does not match content")
    content_hash = identity["content_hash"]
    if not isinstance(content_hash, str) or not _SHA256_RE.fullmatch(content_hash):
        raise DatasetConflictError("REFUSED: content_hash is invalid")
    expected_hash = hash_payload(lineage)
    if content_hash != expected_hash:
        raise DatasetConflictError("REFUSED: content_hash does not authenticate lineage")
    expected_id = f"{DATASET_KIND}-{expected_hash[:16]}"
    if identity["dataset_id"] != expected_id:
        raise DatasetConflictError("REFUSED: full dataset_id does not bind content")
    if expected_directory_name is not None and expected_directory_name != expected_id:
        raise DatasetConflictError("REFUSED: dataset directory does not match full dataset_id")
    return ValidatedDatasetIdentity._from_verified(identity)


def _jsonl_bytes(payloads: list[dict]) -> bytes:
    if not payloads:
        return b""
    return ("\n".join(canonical_json(payload) for payload in payloads) + "\n").encode(
        "utf-8"
    )


def build_identity(
    events: list[NormalizedEvent],
    refusals: list[Refusal],
    *,
    source_snapshot_name: str,
    source_manifest_sha256: str,
) -> tuple[dict, bytes, bytes]:
    """Return the dataset identity record and the two content blobs.

    Refusals are hashed into the identity alongside events. A build that
    silently started discarding rows would otherwise produce a dataset that
    looked identical to an honest one.
    """
    if not isinstance(source_snapshot_name, str) or not isinstance(
        source_manifest_sha256, str
    ):
        # The loader authenticates these on read; the constructor has to
        # refuse in the same typed way rather than raising AttributeError,
        # or the lineage boundary is only half a boundary.
        raise DatasetConflictError("REFUSED: source lineage fields must be strings")
    source_snapshot_name = source_snapshot_name.strip()
    source_manifest_sha256 = source_manifest_sha256.strip().lower()
    if not source_snapshot_name:
        raise DatasetConflictError("REFUSED: source snapshot name is empty")
    if not _SHA256_RE.fullmatch(source_manifest_sha256):
        raise DatasetConflictError(
            "REFUSED: source manifest identity is not one lowercase SHA-256"
        )

    ordered_events = sorted(
        events, key=lambda event: (event.action_date, event.benzinga_id)
    )
    ordered_refusals = sorted(
        refusals,
        key=lambda refusal: (
            refusal.action_date or "",
            refusal.benzinga_id or "",
            refusal.reason,
            refusal.detail,
        ),
    )
    event_ids = [event.benzinga_id for event in ordered_events]
    if len(event_ids) != len(set(event_ids)):
        raise DatasetConflictError(
            "REFUSED: normalized events contain duplicate benzinga_id values"
        )

    events_bytes = _jsonl_bytes([event.to_payload() for event in ordered_events])
    refusals_bytes = _jsonl_bytes(
        [refusal.to_payload() for refusal in ordered_refusals]
    )
    lineage = {
        "kind": DATASET_KIND,
        "contract_version": DATASET_CONTRACT_VERSION,
        "source_snapshot_name": source_snapshot_name,
        "source_manifest_sha256": source_manifest_sha256,
        "era_split_year": ERA_SPLIT_YEAR,
        "event_count": len(ordered_events),
        "refusal_count": len(ordered_refusals),
        "events_sha256": hash_bytes(events_bytes),
        "refusals_sha256": hash_bytes(refusals_bytes),
    }
    content_hash = hash_payload(lineage)
    identity = {
        **lineage,
        "content_hash": content_hash,
        "dataset_id": f"{DATASET_KIND}-{content_hash[:16]}",
    }
    return identity, events_bytes, refusals_bytes


def write_dataset(
    events: list[NormalizedEvent],
    refusals: list[Refusal],
    out_root: Path,
    *,
    source_snapshot_name: str,
    source_manifest_sha256: str,
) -> dict:
    """Write the dataset immutably and return its identity record.

    Layout: ``<out_root>/<dataset_id>/{events.jsonl,refusals.jsonl,dataset.json}``.

    Re-running with identical content is a no-op that returns the same
    identity. Any pre-existing file with different bytes refuses, including
    the case where only one of the three files differs -- a half-written or
    hand-edited dataset must not be mistaken for a clean rebuild.
    """
    identity, events_bytes, refusals_bytes = build_identity(
        events,
        refusals,
        source_snapshot_name=source_snapshot_name,
        source_manifest_sha256=source_manifest_sha256,
    )
    target = Path(out_root) / identity["dataset_id"]
    identity_bytes = (canonical_json(identity) + "\n").encode("utf-8")
    try:
        for filename, data in (
            ("events.jsonl", events_bytes),
            ("refusals.jsonl", refusals_bytes),
            ("dataset.json", identity_bytes),
        ):
            publish_immutable_bytes(target / filename, data)
    except ImmutableFileConflictError as exc:
        raise DatasetConflictError(
            f"REFUSED: {target} exists with different content: {exc}"
        ) from exc
    return identity


def load_validated_identity(dataset_dir: Path) -> ValidatedDatasetIdentity:
    """Read and authenticate an exact identity plus both complete blobs."""
    dataset_dir = Path(dataset_dir)
    identity_path = dataset_dir / "dataset.json"
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        raise DatasetConflictError(
            f"REFUSED: {identity_path} is missing or invalid: {exc}"
        ) from exc
    try:
        events_bytes = (dataset_dir / "events.jsonl").read_bytes()
        refusals_bytes = (dataset_dir / "refusals.jsonl").read_bytes()
    except OSError as exc:
        raise DatasetConflictError(
            f"REFUSED: normalized dataset content is missing or unreadable: {exc}"
        ) from exc
    return validate_identity_record(
        identity,
        events_bytes=events_bytes,
        refusals_bytes=refusals_bytes,
        expected_directory_name=dataset_dir.name,
    )


def load_identity(dataset_dir: Path) -> dict:
    """Compatibility view backed by the strict typed loader."""
    return load_validated_identity(dataset_dir).to_record()


def summarize(events: list[NormalizedEvent], refusals: list[Refusal]) -> dict:
    """Return coverage and refusal facts about a normalization result.

    Deliberately limited to counting: no outcome, return, or ranking is
    computed anywhere in this module.

    ``availability_deferred_beyond_action_date`` is the count of events whose
    conservative availability bound is later than the action date itself --
    the price, in rows, of the frozen restatement-safe rule.
    """
    by_year: collections.Counter = collections.Counter()
    deferred = 0
    era_counts: collections.Counter = collections.Counter()
    tickers: set[str] = set()
    firms: set[str] = set()
    missing_company_name = 0

    for event in events:
        by_year[event.action_date[:4]] += 1
        era_counts[event.time_field_era] += 1
        tickers.add(event.ticker)
        firms.add(event.firm)
        if event.available_date != event.action_date:
            deferred += 1
        if event.company_name is None:
            missing_company_name += 1

    refusal_counts: collections.Counter = collections.Counter(
        refusal.reason for refusal in refusals
    )
    total_rows = len(events) + len(refusals)
    return {
        "input_rows": total_rows,
        "event_count": len(events),
        "refusal_count": len(refusals),
        "retention_rate": (len(events) / total_rows) if total_rows else 0.0,
        "distinct_tickers": len(tickers),
        "distinct_firms": len(firms),
        "events_missing_company_name": missing_company_name,
        "availability_deferred_beyond_action_date": deferred,
        "events_by_action_year": dict(sorted(by_year.items())),
        "events_by_time_field_era": dict(sorted(era_counts.items())),
        "refusals_by_reason": dict(sorted(refusal_counts.items())),
    }
