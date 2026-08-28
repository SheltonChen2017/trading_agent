"""Strict, typed ARV2 source-snapshot verification boundary."""
from __future__ import annotations

import dataclasses
import threading
import weakref
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .canonical import (
    CanonicalEvidenceError,
    decode_utf8,
    format_utc_timestamp,
    parse_utc_timestamp,
    require_canonical_json_bytes,
    require_exact_bool,
    require_exact_keys,
    require_identifier,
    require_int,
    require_relative_page_path,
    require_sha256,
    resolve_contained,
    sha256_bytes,
    strict_json_loads,
)
from .evidence import SourceRowLocator


SNAPSHOT_MANIFEST_SCHEMA = "arv2-source-snapshot-manifest-v2"
INCOMPLETE_DIAGNOSTIC_STATUS = "INVALID_INCOMPLETE_DIAGNOSTIC_ONLY"
MANIFEST_FILENAME = "manifest.json"
_MANIFEST_KEYS = frozenset(
    {
        "schema",
        "snapshot_id",
        "provider_contract_id",
        "provider_contract_sha256",
        "captured_at",
        "complete",
        "terminated_naturally",
        "requested_first_year",
        "requested_last_year",
        "partition_key",
        "source_row_count",
        "partitions",
    }
)
_PARTITION_KEYS = frozenset({"year", "row_count", "pages"})
_PAGE_KEYS = frozenset({"page_number", "filename", "sha256", "row_count"})
_SNAPSHOT_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType["VerifiedSnapshot"], Path, tuple[object, ...]]
] = {}
_SNAPSHOT_AUTHORITIES_LOCK = threading.RLock()


class SnapshotVerificationError(CanonicalEvidenceError):
    """A source snapshot cannot be authenticated as the declared artifact."""


@dataclasses.dataclass(frozen=True)
class VerifiedPage:
    partition_year: int
    page_number: int
    filename: str
    sha256: str
    row_count: int


@dataclasses.dataclass(frozen=True)
class VerifiedPartition:
    year: int
    row_count: int
    pages: tuple[VerifiedPage, ...]


@dataclasses.dataclass(frozen=True)
class VerifiedSourceRow:
    locator: SourceRowLocator
    raw_json: str

    def parsed_record(self) -> dict[str, Any]:
        try:
            raw_bytes = self.raw_json.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise SnapshotVerificationError(
                "verified source row is not strict UTF-8"
            ) from exc
        if sha256_bytes(raw_bytes) != self.locator.raw_row_sha256:
            raise SnapshotVerificationError(
                "verified source row bytes no longer match its locator"
            )
        value = strict_json_loads(self.raw_json, "verified source row")
        if not isinstance(value, dict):
            raise SnapshotVerificationError("verified source row is not an object")
        return value


@dataclasses.dataclass(frozen=True, init=False)
class VerifiedSnapshot:
    schema: str
    snapshot_id: str
    provider_contract_id: str
    provider_contract_sha256: str
    captured_at: str
    manifest_bytes: bytes
    manifest_sha256: str
    requested_first_year: int
    requested_last_year: int
    partition_key: str
    source_row_count: int
    partitions: tuple[VerifiedPartition, ...]
    rows: tuple[VerifiedSourceRow, ...]
    verified_at: str
    source_root: str

    @property
    def source_locators(self) -> tuple[SourceRowLocator, ...]:
        revalidate_verified_snapshot(self)
        return tuple(row.locator for row in self.rows)


def _snapshot_fingerprint(snapshot: VerifiedSnapshot) -> tuple[object, ...]:
    """Materialize every authoritative scalar, page and row as immutable values."""
    return (
        snapshot.schema,
        snapshot.snapshot_id,
        snapshot.provider_contract_id,
        snapshot.provider_contract_sha256,
        snapshot.captured_at,
        snapshot.manifest_bytes,
        snapshot.manifest_sha256,
        snapshot.requested_first_year,
        snapshot.requested_last_year,
        snapshot.partition_key,
        snapshot.source_row_count,
        tuple(
            (
                partition.year,
                partition.row_count,
                tuple(
                    (
                        page.partition_year,
                        page.page_number,
                        page.filename,
                        page.sha256,
                        page.row_count,
                    )
                    for page in partition.pages
                ),
            )
            for partition in snapshot.partitions
        ),
        tuple((row.locator.locator_sha256, row.raw_json) for row in snapshot.rows),
        snapshot.verified_at,
        snapshot.source_root,
    )


def _forget_snapshot_authority(
    identity: int, reference: weakref.ReferenceType[VerifiedSnapshot]
) -> None:
    with _SNAPSHOT_AUTHORITIES_LOCK:
        current = _SNAPSHOT_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _SNAPSHOT_AUTHORITIES.pop(identity, None)


def _verified_snapshot(
    *,
    source_root: Path,
    schema: str,
    snapshot_id: str,
    provider_contract_id: str,
    provider_contract_sha256: str,
    captured_at: str,
    manifest_bytes: bytes,
    manifest_sha256: str,
    requested_first_year: int,
    requested_last_year: int,
    partition_key: str,
    source_row_count: int,
    partitions: tuple[VerifiedPartition, ...],
    rows: tuple[VerifiedSourceRow, ...],
    verified_at: str,
) -> VerifiedSnapshot:
    """Create and register loader authority without exposing a cloneable token."""
    value = object.__new__(VerifiedSnapshot)
    fields: dict[str, object] = {
        "schema": schema,
        "snapshot_id": snapshot_id,
        "provider_contract_id": provider_contract_id,
        "provider_contract_sha256": provider_contract_sha256,
        "captured_at": captured_at,
        "manifest_bytes": manifest_bytes,
        "manifest_sha256": manifest_sha256,
        "requested_first_year": requested_first_year,
        "requested_last_year": requested_last_year,
        "partition_key": partition_key,
        "source_row_count": source_row_count,
        "partitions": partitions,
        "rows": rows,
        "verified_at": verified_at,
        "source_root": str(source_root),
    }
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    if schema != SNAPSHOT_MANIFEST_SCHEMA:
        raise SnapshotVerificationError("wrong verified snapshot schema")
    require_identifier(snapshot_id, "snapshot_id")
    require_identifier(provider_contract_id, "provider_contract_id")
    require_sha256(provider_contract_sha256, "provider_contract_sha256")
    captured = parse_utc_timestamp(captured_at, "captured_at")
    require_sha256(manifest_sha256, "manifest_sha256")
    verified = parse_utc_timestamp(verified_at, "verified_at")
    if captured > verified:
        raise SnapshotVerificationError("captured_at cannot be later than verified_at")
    if sha256_bytes(manifest_bytes) != manifest_sha256:
        raise SnapshotVerificationError("manifest bytes/hash mismatch")
    if source_row_count != len(rows) or source_row_count <= 0:
        raise SnapshotVerificationError("verified row count must be exact and positive")
    fingerprint = _snapshot_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_snapshot_authority(key, ref)
    )
    with _SNAPSHOT_AUTHORITIES_LOCK:
        _SNAPSHOT_AUTHORITIES[identity] = (reference, source_root, fingerprint)
    return value


def revalidate_verified_snapshot(snapshot: VerifiedSnapshot) -> VerifiedSnapshot:
    """Reparse the bound manifest/pages and compare all authenticated evidence.

    Object identity is registered out-of-band by the loader, so copying a
    private-looking field or using ``dataclasses.replace`` cannot mint a new
    verified value. The original absolute source root and original deep
    fingerprint are also held out-of-band, preventing in-place mutation from
    redirecting revalidation to a substituted artifact.
    """
    if type(snapshot) is not VerifiedSnapshot:
        raise SnapshotVerificationError(
            "snapshot authority requires an exact VerifiedSnapshot"
        )
    with _SNAPSHOT_AUTHORITIES_LOCK:
        authority = _SNAPSHOT_AUTHORITIES.get(id(snapshot))
    if authority is None or authority[0]() is not snapshot:
        raise SnapshotVerificationError(
            "VerifiedSnapshot is not loader-authenticated authority"
        )
    _, source_root, expected_fingerprint = authority
    if _snapshot_fingerprint(snapshot) != expected_fingerprint:
        raise SnapshotVerificationError(
            "VerifiedSnapshot changed after loader authentication"
        )
    try:
        reloaded = load_verified_snapshot(
            source_root, verified_at=snapshot.verified_at
        )
    except OSError as exc:
        raise SnapshotVerificationError(
            "bound snapshot artifact is absent or unreadable"
        ) from exc
    if _snapshot_fingerprint(reloaded) != expected_fingerprint:
        raise SnapshotVerificationError(
            "snapshot manifest, pages, rows, counts, or scalar bindings changed"
        )
    return snapshot


@dataclasses.dataclass(frozen=True)
class IncompleteDiagnosticSnapshot:
    schema: str
    snapshot_id: str
    provider_contract_id: str
    provider_contract_sha256: str
    captured_at: str
    manifest_bytes: bytes
    manifest_sha256: str
    requested_first_year: int
    requested_last_year: int
    partition_key: str
    declared_source_row_count: int
    partitions: tuple[VerifiedPartition, ...]
    rows: tuple[VerifiedSourceRow, ...]
    verified_at: str
    status: str = dataclasses.field(
        default=INCOMPLETE_DIAGNOSTIC_STATUS, init=False
    )

    def __post_init__(self) -> None:
        if self.status != INCOMPLETE_DIAGNOSTIC_STATUS:
            raise SnapshotVerificationError("incomplete snapshot status cannot be changed")


SnapshotArtifact = VerifiedSnapshot | IncompleteDiagnosticSnapshot


def _manifest_record(payload: bytes) -> dict[str, Any]:
    value = require_canonical_json_bytes(payload, "snapshot manifest")
    if not isinstance(value, dict):
        raise SnapshotVerificationError("snapshot manifest must be an object")
    require_exact_keys(value, _MANIFEST_KEYS, "snapshot manifest")
    if value["schema"] != SNAPSHOT_MANIFEST_SCHEMA:
        raise SnapshotVerificationError("unsupported snapshot manifest schema")
    require_identifier(value["snapshot_id"], "snapshot_id")
    require_identifier(value["provider_contract_id"], "provider_contract_id")
    require_sha256(value["provider_contract_sha256"], "provider_contract_sha256")
    parse_utc_timestamp(value["captured_at"], "captured_at")
    require_exact_bool(value["complete"], "complete")
    require_exact_bool(value["terminated_naturally"], "terminated_naturally")
    if value["complete"] != value["terminated_naturally"]:
        raise SnapshotVerificationError(
            "complete and terminated_naturally must agree exactly"
        )
    first = require_int(
        value["requested_first_year"],
        "requested_first_year",
        minimum=1900,
        maximum=2200,
    )
    last = require_int(
        value["requested_last_year"],
        "requested_last_year",
        minimum=1900,
        maximum=2200,
    )
    if first > last:
        raise SnapshotVerificationError("requested year bounds are reversed")
    if value["partition_key"] != "event_year":
        raise SnapshotVerificationError("partition_key must be exactly 'event_year'")
    require_int(value["source_row_count"], "source_row_count", minimum=0)
    if not isinstance(value["partitions"], list):
        raise SnapshotVerificationError("partitions must be an ordered JSON array")
    return value


def _parse_page_rows(
    *,
    root: Path,
    snapshot_id: str,
    manifest_sha256: str,
    partition_year: int,
    partition_key: str,
    page: Mapping[str, Any],
) -> tuple[VerifiedPage, tuple[VerifiedSourceRow, ...]]:
    require_exact_keys(page, _PAGE_KEYS, "snapshot page")
    page_number = require_int(page["page_number"], "page_number", minimum=1)
    filename = require_relative_page_path(page["filename"])
    expected_sha256 = require_sha256(page["sha256"], "page.sha256")
    expected_count = require_int(page["row_count"], "page.row_count", minimum=0)
    path = resolve_contained(root, filename)
    if not path.is_file() or path.is_symlink():
        raise SnapshotVerificationError(f"page must be a regular file: {filename}")
    payload = path.read_bytes()
    if sha256_bytes(payload) != expected_sha256:
        raise SnapshotVerificationError(f"page hash mismatch: {filename}")
    if payload and (not payload.endswith(b"\n") or b"\r" in payload):
        raise SnapshotVerificationError(
            f"page must use LF-terminated JSONL: {filename}"
        )
    raw_lines = [] if not payload else payload[:-1].split(b"\n")
    if any(not line for line in raw_lines):
        raise SnapshotVerificationError(f"page contains a blank JSONL row: {filename}")
    if len(raw_lines) != expected_count:
        raise SnapshotVerificationError(f"page row count mismatch: {filename}")
    rows: list[VerifiedSourceRow] = []
    for offset, raw_line in enumerate(raw_lines):
        text = decode_utf8(raw_line, f"{filename}:{offset}")
        parsed = strict_json_loads(text, f"{filename}:{offset}")
        if not isinstance(parsed, dict):
            raise SnapshotVerificationError(
                f"source row must be a JSON object: {filename}:{offset}"
            )
        row_year = parsed.get(partition_key)
        if type(row_year) is not int or row_year != partition_year:
            raise SnapshotVerificationError(
                f"source row falls outside partition {partition_year}: {filename}:{offset}"
            )
        locator = SourceRowLocator(
            snapshot_id=snapshot_id,
            snapshot_manifest_sha256=manifest_sha256,
            partition_year=partition_year,
            page_number=page_number,
            page_filename=filename,
            page_sha256=expected_sha256,
            row_offset=offset,
            raw_row_sha256=sha256_bytes(raw_line),
        )
        rows.append(VerifiedSourceRow(locator=locator, raw_json=text))
    verified_page = VerifiedPage(
        partition_year=partition_year,
        page_number=page_number,
        filename=filename,
        sha256=expected_sha256,
        row_count=expected_count,
    )
    return verified_page, tuple(rows)


def load_snapshot(
    root: str | Path,
    *,
    verified_at: str | None = None,
) -> SnapshotArtifact:
    """Authenticate one source snapshot and return a publishable or diagnostic type."""
    try:
        root_path = Path(root).expanduser().resolve(strict=True)
    except OSError as exc:
        raise SnapshotVerificationError(
            "snapshot root is absent or unreadable"
        ) from exc
    if not root_path.is_dir():
        raise SnapshotVerificationError("snapshot root must be a directory")
    manifest_path = root_path / MANIFEST_FILENAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise SnapshotVerificationError("snapshot manifest must be a regular file")
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = sha256_bytes(manifest_bytes)
    manifest = _manifest_record(manifest_bytes)
    verified_timestamp = verified_at or format_utc_timestamp(
        datetime.now(timezone.utc)
    )
    verified_instant = parse_utc_timestamp(verified_timestamp, "verified_at")
    captured_instant = parse_utc_timestamp(manifest["captured_at"], "captured_at")
    if captured_instant > verified_instant:
        raise SnapshotVerificationError("captured_at cannot be later than verified_at")

    partitions: list[VerifiedPartition] = []
    rows: list[VerifiedSourceRow] = []
    referenced_files: set[str] = set()
    years: list[int] = []
    for partition_index, raw_partition in enumerate(manifest["partitions"]):
        if not isinstance(raw_partition, dict):
            raise SnapshotVerificationError(
                f"partitions[{partition_index}] must be an object"
            )
        require_exact_keys(raw_partition, _PARTITION_KEYS, "snapshot partition")
        year = require_int(
            raw_partition["year"], "partition.year", minimum=1900, maximum=2200
        )
        if not (
            manifest["requested_first_year"]
            <= year
            <= manifest["requested_last_year"]
        ):
            raise SnapshotVerificationError("partition year is outside requested bounds")
        years.append(year)
        partition_count = require_int(
            raw_partition["row_count"], "partition.row_count", minimum=0
        )
        raw_pages = raw_partition["pages"]
        if not isinstance(raw_pages, list) or not raw_pages:
            raise SnapshotVerificationError("every declared partition needs at least one page")
        verified_pages: list[VerifiedPage] = []
        partition_rows: list[VerifiedSourceRow] = []
        for raw_page in raw_pages:
            if not isinstance(raw_page, dict):
                raise SnapshotVerificationError("page inventory entry must be an object")
            page, page_rows = _parse_page_rows(
                root=root_path,
                snapshot_id=manifest["snapshot_id"],
                manifest_sha256=manifest_sha256,
                partition_year=year,
                partition_key=manifest["partition_key"],
                page=raw_page,
            )
            if page.filename in referenced_files:
                raise SnapshotVerificationError("page filename is referenced more than once")
            referenced_files.add(page.filename)
            verified_pages.append(page)
            partition_rows.extend(page_rows)
        page_numbers = [page.page_number for page in verified_pages]
        if page_numbers != list(range(1, len(verified_pages) + 1)):
            raise SnapshotVerificationError(
                f"partition {year} pages must be unique, ordered, and contiguous from 1"
            )
        if len(partition_rows) != partition_count:
            raise SnapshotVerificationError(f"partition {year} row count mismatch")
        partitions.append(
            VerifiedPartition(year, partition_count, tuple(verified_pages))
        )
        rows.extend(partition_rows)

    if years != sorted(set(years)):
        raise SnapshotVerificationError("partition years must be unique and ordered")
    if manifest["complete"]:
        expected_years = list(
            range(
                manifest["requested_first_year"],
                manifest["requested_last_year"] + 1,
            )
        )
        if years != expected_years:
            raise SnapshotVerificationError(
                "complete snapshot partitions must exactly cover contiguous requested years"
            )
        if not rows:
            raise SnapshotVerificationError("a complete snapshot cannot contain zero rows")
    if len(rows) != manifest["source_row_count"]:
        raise SnapshotVerificationError("manifest source_row_count mismatch")

    pages_root = root_path / "pages"
    actual_files: set[str] = set()
    if pages_root.exists():
        if pages_root.is_symlink() or not pages_root.is_dir():
            raise SnapshotVerificationError("snapshot pages root must be a regular directory")
        for path in pages_root.rglob("*"):
            if path.is_symlink():
                raise SnapshotVerificationError("snapshot pages cannot contain symlinks")
            if path.is_file():
                actual_files.add(path.relative_to(root_path).as_posix())
    if actual_files != referenced_files:
        raise SnapshotVerificationError(
            "raw page inventory mismatch; "
            f"unreferenced={sorted(actual_files - referenced_files)}, "
            f"missing={sorted(referenced_files - actual_files)}"
        )

    common = dict(
        schema=manifest["schema"],
        snapshot_id=manifest["snapshot_id"],
        provider_contract_id=manifest["provider_contract_id"],
        provider_contract_sha256=manifest["provider_contract_sha256"],
        captured_at=manifest["captured_at"],
        manifest_bytes=manifest_bytes,
        manifest_sha256=manifest_sha256,
        requested_first_year=manifest["requested_first_year"],
        requested_last_year=manifest["requested_last_year"],
        partition_key=manifest["partition_key"],
        partitions=tuple(partitions),
        rows=tuple(rows),
        verified_at=verified_timestamp,
    )
    if manifest["complete"]:
        return _verified_snapshot(
            source_root=root_path,
            **common,
            source_row_count=manifest["source_row_count"],
        )
    return IncompleteDiagnosticSnapshot(
        **common,
        declared_source_row_count=manifest["source_row_count"],
    )


def load_verified_snapshot(
    root: str | Path,
    *,
    verified_at: str | None = None,
) -> VerifiedSnapshot:
    artifact = load_snapshot(root, verified_at=verified_at)
    if type(artifact) is not VerifiedSnapshot:
        raise SnapshotVerificationError(
            f"snapshot is {INCOMPLETE_DIAGNOSTIC_STATUS}, not publishable evidence"
        )
    return artifact
