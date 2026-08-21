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


def load_identity(dataset_dir: Path) -> dict:
    """Read and authenticate a dataset identity plus its content blobs."""
    dataset_dir = Path(dataset_dir)
    identity_path = dataset_dir / "dataset.json"
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        raise DatasetConflictError(
            f"REFUSED: {identity_path} is missing or invalid: {exc}"
        ) from exc
    if not isinstance(identity, dict):
        raise DatasetConflictError(f"REFUSED: {identity_path} is not an object")

    missing = [
        key
        for key in (*_LINEAGE_KEYS, "content_hash", "dataset_id")
        if key not in identity
    ]
    if missing:
        raise DatasetConflictError(
            f"REFUSED: {identity_path} is missing identity fields: {missing}"
        )
    lineage = {key: identity[key] for key in _LINEAGE_KEYS}
    if lineage["kind"] != DATASET_KIND:
        raise DatasetConflictError(f"REFUSED: {identity_path} has an unknown kind")
    if lineage["contract_version"] != DATASET_CONTRACT_VERSION:
        raise DatasetConflictError(
            f"REFUSED: {identity_path} has an unsupported contract version"
        )
    if lineage["era_split_year"] != ERA_SPLIT_YEAR:
        raise DatasetConflictError(
            f"REFUSED: {identity_path} has an unsupported era boundary"
        )
    if not isinstance(lineage["source_snapshot_name"], str) or not lineage[
        "source_snapshot_name"
    ].strip():
        raise DatasetConflictError(
            f"REFUSED: {identity_path} has no source snapshot name"
        )
    source_manifest = lineage["source_manifest_sha256"]
    if not isinstance(source_manifest, str) or not _SHA256_RE.fullmatch(
        source_manifest
    ):
        raise DatasetConflictError(
            f"REFUSED: {identity_path} has an invalid source manifest hash"
        )
    for count_key in ("event_count", "refusal_count"):
        count = lineage[count_key]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise DatasetConflictError(
                f"REFUSED: {identity_path} has an invalid {count_key}"
            )
    expected_hash = hash_payload(lineage)
    if identity.get("content_hash") != expected_hash:
        raise DatasetConflictError(
            f"REFUSED: {identity_path} content_hash does not authenticate lineage"
        )
    expected_id = f"{DATASET_KIND}-{expected_hash[:16]}"
    if identity.get("dataset_id") != expected_id or dataset_dir.name != expected_id:
        raise DatasetConflictError(
            f"REFUSED: {identity_path} dataset_id does not match its content or path"
        )

    for filename, key in (
        ("events.jsonl", "events_sha256"),
        ("refusals.jsonl", "refusals_sha256"),
    ):
        path = dataset_dir / filename
        try:
            blob = path.read_bytes()
        except OSError as exc:
            raise DatasetConflictError(
                f"REFUSED: {path} is missing or unreadable: {exc}"
            ) from exc
        actual = hash_bytes(blob)
        if actual != identity.get(key):
            raise DatasetConflictError(
                f"REFUSED: {path} does not match {key}"
            )
        count_key = "event_count" if filename == "events.jsonl" else "refusal_count"
        line_count = len(blob.splitlines())
        if line_count != identity.get(count_key):
            raise DatasetConflictError(
                f"REFUSED: {path} row count does not match {count_key}"
            )
    return identity


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
