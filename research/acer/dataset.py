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
from pathlib import Path

from ml.hashing import canonical_json, hash_bytes, hash_payload
from ml.immutable_io import ImmutableFileConflictError, publish_immutable_bytes

from research.acer.normalize import ERA_SPLIT_YEAR, NormalizedEvent, Refusal

DATASET_KIND = "acer-analyst-events"
DATASET_CONTRACT_VERSION = 1


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
    events_bytes = _jsonl_bytes([event.to_payload() for event in events])
    refusals_bytes = _jsonl_bytes([refusal.to_payload() for refusal in refusals])
    lineage = {
        "kind": DATASET_KIND,
        "contract_version": DATASET_CONTRACT_VERSION,
        "source_snapshot_name": source_snapshot_name,
        "source_manifest_sha256": source_manifest_sha256,
        "era_split_year": ERA_SPLIT_YEAR,
        "events_sha256": hash_bytes(events_bytes),
        "refusals_sha256": hash_bytes(refusals_bytes),
    }
    content_hash = hash_payload(lineage)
    identity = {
        **lineage,
        "content_hash": content_hash,
        "dataset_id": f"{DATASET_KIND}-{content_hash[:16]}",
        "event_count": len(events),
        "refusal_count": len(refusals),
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
    """Read a dataset's identity and verify its blobs still hash correctly."""
    identity = json.loads((dataset_dir / "dataset.json").read_text(encoding="utf-8"))
    for filename, key in (
        ("events.jsonl", "events_sha256"),
        ("refusals.jsonl", "refusals_sha256"),
    ):
        actual = hash_bytes((dataset_dir / filename).read_bytes())
        if actual != identity.get(key):
            raise DatasetConflictError(
                f"REFUSED: {dataset_dir / filename} does not match {key}"
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
