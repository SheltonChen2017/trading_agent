"""Authoritative verified loader for immutable vendor ratings snapshots.

This is the single implementation of "what makes a snapshot trustworthy".
It was consolidated here from ``scripts/audit_benzinga_ratings.py`` (where
the checks were hardened by the ACER-1 review, findings ACER1R-001/002) so
that the audit tool and the ACER research backbone cannot drift apart: a
snapshot that the audit refuses must also be a snapshot the backbone
refuses, and vice versa. The audit script now delegates to this module and
re-raises ``SnapshotError`` as ``SystemExit`` for its CLI surface.

Everything here fails closed. A snapshot whose manifest hash, page hashes,
page/partition row-count graph, page-reference uniqueness, or result shape
does not verify is refused rather than partially loaded, because a silently
truncated or edited snapshot would corrupt both the restatement measurement
and any dataset derived from it.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SnapshotError(ValueError):
    """A snapshot failed verification and must not be used as evidence."""


def _load_manifest_and_hash(snap: Path) -> tuple[dict, str]:
    """Load one manifest byte image and return it with its verified hash."""
    manifest_path = snap / "manifest.json"
    hash_path = snap / "manifest.sha256"
    try:
        manifest_bytes = manifest_path.read_bytes()
        recorded_hash = hash_path.read_text(encoding="utf-8").strip().lower()
    except OSError as exc:
        raise SnapshotError(
            f"REFUSED: snapshot manifest is missing or unreadable: {exc}"
        ) from exc
    if not SHA256_RE.fullmatch(recorded_hash):
        raise SnapshotError("REFUSED: manifest.sha256 is not one lowercase SHA-256")
    actual_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if actual_hash != recorded_hash:
        raise SnapshotError("REFUSED: manifest hash mismatch")
    try:
        manifest = json.loads(manifest_bytes)
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"REFUSED: manifest is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(
        manifest.get("partitions"), list
    ):
        raise SnapshotError("REFUSED: manifest has no partitions list")
    return manifest, recorded_hash


def load_manifest(snap: Path) -> dict:
    """Load a snapshot manifest only after its recorded hash verifies."""
    return _load_manifest_and_hash(snap)[0]


def manifest_sha256(snap: Path) -> str:
    """Return the snapshot's verified manifest hash, for lineage records."""
    return _load_manifest_and_hash(snap)[1]


def load_verified_rows(snap: Path, allow_incomplete: bool = False) -> list[dict]:
    """Return every raw vendor row in a snapshot, or refuse.

    The row-count graph is checked at both levels: each page must contain
    exactly the number of results its manifest entry declares, and each
    partition must contain exactly the number its own entry declares. A
    hash-valid manifest that disagrees with the hashed page contents is
    still a corrupt snapshot.
    """
    return load_verified_snapshot(snap, allow_incomplete)[0]


def load_verified_snapshot(
    snap: Path, allow_incomplete: bool = False
) -> tuple[list[dict], str]:
    """Return verified rows and the hash of the same manifest byte image.

    A builder must bind rows to the manifest it actually verified. Returning
    them together avoids a second manifest read that could attach lineage
    from a concurrently replaced manifest to rows loaded under the first.
    """
    manifest, verified_manifest_hash = _load_manifest_and_hash(snap)
    complete = manifest.get("complete", False)
    if not complete and not allow_incomplete:
        raise SnapshotError(
            "REFUSED: snapshot is marked incomplete (a partition did not "
            "terminate naturally). Pass --allow-incomplete to analyse anyway."
        )
    rows: list[dict] = []
    seen_files: set[str] = set()
    for partition in manifest["partitions"]:
        if not isinstance(partition, dict) or not isinstance(
            partition.get("pages"), list
        ):
            raise SnapshotError("REFUSED: malformed partition metadata")
        if complete and not partition.get("terminated_naturally", False):
            raise SnapshotError(
                "REFUSED: complete manifest contains unterminated partition"
            )
        partition_rows = 0
        for meta in partition["pages"]:
            if not isinstance(meta, dict):
                raise SnapshotError("REFUSED: malformed page metadata")
            file_name = meta.get("file")
            if not isinstance(file_name, str) or Path(file_name).name != file_name:
                raise SnapshotError("REFUSED: unsafe page filename in manifest")
            if file_name in seen_files:
                raise SnapshotError(f"REFUSED: duplicate page reference: {file_name}")
            seen_files.add(file_name)
            expected_hash = meta.get("sha256")
            if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(
                expected_hash.lower()
            ):
                raise SnapshotError(f"REFUSED: invalid page hash for {file_name}")
            try:
                payload = (snap / "raw" / file_name).read_bytes()
            except OSError as exc:
                raise SnapshotError(
                    f"REFUSED: page is missing or unreadable: {exc}"
                ) from exc
            if hashlib.sha256(payload).hexdigest() != expected_hash.lower():
                raise SnapshotError(f"REFUSED: hash mismatch for {file_name}")
            try:
                body = json.loads(payload)
            except (TypeError, ValueError) as exc:
                raise SnapshotError(
                    f"REFUSED: invalid JSON in {file_name}: {exc}"
                ) from exc
            results = body.get("results") if isinstance(body, dict) else None
            if not isinstance(results, list) or not all(
                isinstance(row, dict) for row in results
            ):
                raise SnapshotError(
                    f"REFUSED: {file_name} has a malformed results list"
                )
            if meta.get("rows") != len(results):
                raise SnapshotError(f"REFUSED: row-count mismatch for {file_name}")
            partition_rows += len(results)
            rows.extend(results)
        if partition.get("rows") != partition_rows:
            raise SnapshotError(
                f"REFUSED: row-count mismatch for partition {partition.get('year')}"
            )
    return rows, verified_manifest_hash
