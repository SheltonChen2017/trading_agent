"""Validated, content-addressed synthetic vintages for short interest.

The dataset contains source facts, release evidence, and named refusals only.
It imports no price, return, ETF, broker, or execution surface and cannot run a
research look. Every correction remains a distinct event in immutable storage.
"""
from __future__ import annotations

import json
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from data.hashing import canonical_json, hash_bytes, hash_payload
from ml.immutable_io import ImmutableFileConflictError, publish_immutable_bytes
from research.short_interest_etf.availability import (
    ExecutionCohort,
    snapshot_execution_cohort,
)
from research.short_interest_etf.contracts import (
    CollectionManifest,
    ReleaseCalendarEntry,
    ReleasePrecision,
    ShortInterestContractError,
    ShortInterestSnapshot,
    SourceEntitlement,
    _canonical_date,
    parse_utc_timestamp,
)
from research.short_interest_etf.normalize import (
    SnapshotRefusal,
    normalize_snapshot_payloads,
)
from research.short_interest_etf.preregistration import PREREGISTRATION

DATASET_KIND = "short-interest-official-snapshot-vintage"
DATASET_CONTRACT_VERSION = 1
SYNTHETIC_FIXTURE_KIND = "synthetic-short-interest-official-style-v1"
_EASTERN = ZoneInfo("America/New_York")
_DATA_FILES = (
    "source_manifest.json",
    "release_calendar.jsonl",
    "snapshots.jsonl",
    "refusals.jsonl",
)
_ALL_ARTIFACT_FILES = frozenset((*_DATA_FILES, "dataset.json"))
_LINEAGE_KEYS = (
    "kind",
    "contract_version",
    "preregistration_sha256",
    "source_manifest_sha256",
    "release_count",
    "snapshot_count",
    "refusal_count",
    "release_calendar_sha256",
    "snapshots_sha256",
    "refusals_sha256",
)


class ShortInterestDatasetError(ValueError):
    """A vintage is incomplete, inconsistent, mutable, or unauthenticated."""


def _refuse(detail: str) -> ShortInterestDatasetError:
    return ShortInterestDatasetError(f"REFUSED: {detail}")


def _jsonl_bytes(payloads: Sequence[Mapping[str, Any]]) -> bytes:
    if not payloads:
        return b""
    return (
        "\n".join(canonical_json(payload) for payload in payloads) + "\n"
    ).encode("utf-8")


def _manifest_bytes(manifest: CollectionManifest) -> bytes:
    return (canonical_json(manifest.to_payload()) + "\n").encode("utf-8")


def fixture_source_payload_sha256(
    release_calendar: Sequence[Mapping[str, Any]],
    snapshot_rows: Sequence[Mapping[str, Any]],
) -> str:
    """Authenticate the synthetic source body without circular manifest data."""
    return hash_payload(
        {
            "release_calendar": list(release_calendar),
            "snapshot_rows": list(snapshot_rows),
        }
    )


@dataclass(frozen=True)
class _PriorRevisionSeries:
    revision_times: tuple[datetime, ...]
    snapshots: tuple[ShortInterestSnapshot, ...]


def _snapshot_prior_identity(
    snapshot: ShortInterestSnapshot,
) -> tuple[str, str]:
    return snapshot.security.security_id, snapshot.settlement_date


def _group_prior_revisions(
    snapshots: Sequence[ShortInterestSnapshot],
) -> dict[
    tuple[str, str],
    list[tuple[datetime, ShortInterestSnapshot]],
]:
    grouped: dict[
        tuple[str, str],
        list[tuple[datetime, ShortInterestSnapshot]],
    ] = {}
    for snapshot in snapshots:
        grouped.setdefault(_snapshot_prior_identity(snapshot), []).append(
            (
                parse_utc_timestamp(
                    snapshot.revision_published_at,
                    "snapshot.revision_published_at",
                ),
                snapshot,
            )
        )
    return grouped


def _build_prior_revision_index(
    snapshots: Sequence[ShortInterestSnapshot],
) -> dict[tuple[str, str], _PriorRevisionSeries]:
    grouped = _group_prior_revisions(snapshots)

    index: dict[tuple[str, str], _PriorRevisionSeries] = {}
    for identity, versions in grouped.items():
        ordered = sorted(versions, key=lambda item: (item[0], item[1].event_id))
        index[identity] = _PriorRevisionSeries(
            revision_times=tuple(item[0] for item in ordered),
            snapshots=tuple(item[1] for item in ordered),
        )
    return index


def _latest_visible_prior(
    series: _PriorRevisionSeries | None,
    cutoff: datetime,
) -> ShortInterestSnapshot | None:
    if series is None:
        return None
    visible_index = bisect_right(series.revision_times, cutoff) - 1
    if visible_index < 0:
        return None
    return series.snapshots[visible_index]


def _build_settlement_ordinal(
    release_settlements: Sequence[str],
) -> dict[str, int]:
    return {
        settlement: index
        for index, settlement in enumerate(release_settlements)
    }


@dataclass(frozen=True)
class ShortInterestVintage:
    manifest: CollectionManifest
    release_calendar: tuple[ReleaseCalendarEntry, ...]
    snapshots: tuple[ShortInterestSnapshot, ...]
    refusals: tuple[SnapshotRefusal, ...]

    def __post_init__(self) -> None:
        if type(self.manifest) is not CollectionManifest:
            raise _refuse("manifest must be the exact CollectionManifest type")
        if type(self.release_calendar) is not tuple or not all(
            type(item) is ReleaseCalendarEntry for item in self.release_calendar
        ):
            raise _refuse(
                "release_calendar must be an exact tuple of exact "
                "ReleaseCalendarEntry values"
            )
        if type(self.snapshots) is not tuple or not all(
            type(item) is ShortInterestSnapshot for item in self.snapshots
        ):
            raise _refuse(
                "snapshots must be an exact tuple of exact "
                "ShortInterestSnapshot values; "
                "daily short-sale volume is forbidden"
            )
        if type(self.refusals) is not tuple or not all(
            type(item) is SnapshotRefusal for item in self.refusals
        ):
            raise _refuse(
                "refusals must be an exact tuple of exact SnapshotRefusal values"
            )

        releases = tuple(
            sorted(self.release_calendar, key=lambda item: item.key)
        )
        snapshots = tuple(
            sorted(
                self.snapshots,
                key=lambda item: (
                    item.settlement_date,
                    item.security.security_id,
                    parse_utc_timestamp(
                        item.revision_published_at, "revision_published_at"
                    ),
                    item.event_id,
                ),
            )
        )
        refusals = tuple(
            sorted(
                self.refusals,
                key=lambda item: (
                    item.settlement_date or "",
                    item.source_record_id or "",
                    item.reason,
                    item.detail,
                ),
            )
        )
        object.__setattr__(self, "release_calendar", releases)
        object.__setattr__(self, "snapshots", snapshots)
        object.__setattr__(self, "refusals", refusals)
        self._validate()

    def _validate(self) -> None:
        if self.manifest.accepted_record_count != len(self.snapshots):
            raise _refuse("manifest accepted_record_count does not match snapshots")
        if self.manifest.refusal_count != len(self.refusals):
            raise _refuse("manifest refusal_count does not match named refusals")

        retrieved = parse_utc_timestamp(self.manifest.retrieved_at, "retrieved_at")
        range_start = _canonical_date(
            self.manifest.settlement_start, "settlement_start"
        )
        range_end = _canonical_date(self.manifest.settlement_end, "settlement_end")

        release_by_key: dict[str, ReleaseCalendarEntry] = {}
        for release in self.release_calendar:
            if release.key in release_by_key:
                raise _refuse(f"duplicate release-calendar key {release.key!r}")
            if parse_utc_timestamp(release.observed_at, "release.observed_at") > retrieved:
                raise _refuse(
                    f"release {release.key!r} was observed after manifest retrieval"
                )
            release_by_key[release.key] = release

        event_ids: set[str] = set()
        record_versions: set[tuple[str, str]] = set()
        revision_groups: dict[str, list[ShortInterestSnapshot]] = {}
        for snapshot in self.snapshots:
            if snapshot.source_id != self.manifest.source_id:
                raise _refuse("snapshot source_id does not match manifest")
            if snapshot.source_version != self.manifest.source_version:
                raise _refuse("snapshot source_version does not match manifest")
            settlement = _canonical_date(snapshot.settlement_date, "settlement_date")
            if settlement < range_start or settlement > range_end:
                raise _refuse(
                    f"snapshot settlement {snapshot.settlement_date} is outside manifest bounds"
                )
            if snapshot.event_id in event_ids:
                raise _refuse(f"duplicate immutable event_id {snapshot.event_id}")
            event_ids.add(snapshot.event_id)
            record_version = (snapshot.source_record_id, snapshot.revision_id)
            if record_version in record_versions:
                raise _refuse(
                    "duplicate source_record_id/revision_id pair "
                    f"{record_version!r}"
                )
            record_versions.add(record_version)
            release = release_by_key.get(snapshot.release_calendar_key)
            if release is None:
                raise _refuse(
                    f"snapshot has no release evidence {snapshot.release_calendar_key!r}"
                )
            if release.settlement_date != snapshot.settlement_date:
                raise _refuse("release settlement does not match snapshot settlement")
            revision_at = parse_utc_timestamp(
                snapshot.revision_published_at, "revision_published_at"
            )
            if release.precision is ReleasePrecision.EXACT_TIMESTAMP:
                published = parse_utc_timestamp(
                    release.public_release_at, "public_release_at"
                )
                if revision_at < published:
                    raise _refuse(
                        "snapshot revision cannot be public before the source release"
                    )
            elif revision_at.astimezone(_EASTERN).date() < _canonical_date(
                release.public_release_date, "public_release_date"
            ):
                raise _refuse(
                    "snapshot revision cannot be public before a date-only release"
                )
            for observed_name, observed_text in (
                ("snapshot", snapshot.observed_at),
                ("volume basis", snapshot.volume_basis.observed_at),
                ("denominator", snapshot.denominator.observed_at),
            ):
                if parse_utc_timestamp(observed_text, f"{observed_name}.observed_at") > retrieved:
                    raise _refuse(
                        f"{observed_name} was observed after manifest retrieval"
                    )
            revision_groups.setdefault(snapshot.logical_id, []).append(snapshot)

        release_settlements = tuple(
            sorted(
                {
                    release.settlement_date
                    for release in self.release_calendar
                    if range_start
                    <= _canonical_date(release.settlement_date, "settlement_date")
                    <= range_end
                }
            )
        )
        self._validate_revision_groups(revision_groups)
        self._validate_prior_links(range_start, release_settlements)

    @staticmethod
    def _validate_revision_groups(
        groups: Mapping[str, Sequence[ShortInterestSnapshot]],
    ) -> None:
        for logical_id, versions in groups.items():
            ordered = sorted(
                versions,
                key=lambda item: parse_utc_timestamp(
                    item.revision_published_at, "revision_published_at"
                ),
            )
            seen_revision_ids: set[str] = set()
            timestamps = [item.revision_published_at for item in ordered]
            if len(timestamps) != len(set(timestamps)):
                raise _refuse(
                    f"logical event {logical_id} has conflicting same-time revisions"
                )
            baseline_identity = ordered[0].security.to_payload()
            for index, version in enumerate(ordered):
                if version.revision_id in seen_revision_ids:
                    raise _refuse(
                        f"logical event {logical_id} repeats revision_id "
                        f"{version.revision_id!r}"
                    )
                seen_revision_ids.add(version.revision_id)
                if version.security.to_payload() != baseline_identity:
                    raise _refuse(
                        f"logical event {logical_id} changes stable identity in a revision"
                    )
                if index == 0:
                    if version.supersedes_event_id is not None:
                        raise _refuse(
                            f"first revision for logical event {logical_id} must not supersede"
                        )
                elif version.supersedes_event_id != ordered[index - 1].event_id:
                    raise _refuse(
                        f"revision {version.revision_id!r} does not supersede the "
                        "immediately preceding immutable event"
                    )

    def _validate_prior_links(
        self,
        range_start: Any,
        release_settlements: Sequence[str],
    ) -> None:
        settlement_ordinal = _build_settlement_ordinal(release_settlements)
        prior_revision_index = _build_prior_revision_index(self.snapshots)

        for snapshot in self.snapshots:
            previous_date = _canonical_date(
                snapshot.previous_settlement_date, "previous_settlement_date"
            )
            current_index = settlement_ordinal.get(snapshot.settlement_date)
            if current_index is None:
                raise _refuse(
                    "snapshot settlement is absent from the release calendar"
                )
            if current_index == 0 and previous_date < range_start:
                if _canonical_date(
                    snapshot.settlement_date, "settlement_date"
                ) == range_start:
                    continue
                raise _refuse(
                    "pre-window warmup is allowed only for a security present "
                    "at manifest settlement_start"
                )
            if current_index > 0:
                expected_previous = release_settlements[current_index - 1]
                if snapshot.previous_settlement_date != expected_previous:
                    raise _refuse(
                        "later snapshot must link to the immediately preceding "
                        "release-calendar settlement for the same stable security_id"
                    )
            previous = _latest_visible_prior(
                prior_revision_index.get(
                    (
                        snapshot.security.security_id,
                        snapshot.previous_settlement_date,
                    )
                ),
                parse_utc_timestamp(
                    snapshot.revision_published_at,
                    "snapshot.revision_published_at",
                ),
            )
            if previous is None:
                raise _refuse(
                    "missing prior snapshot for stable security_id "
                    f"{snapshot.security.security_id!r} at "
                    f"{snapshot.previous_settlement_date}; ticker is not a join key"
                )
            if snapshot.previous_short_shares != previous.current_short_shares:
                raise _refuse(
                    "previous_short_shares does not match the latest prior revision "
                    f"visible to {snapshot.revision_id!r}"
                )


def build_vintage(
    manifest: CollectionManifest,
    release_calendar: Sequence[ReleaseCalendarEntry],
    snapshots: Sequence[ShortInterestSnapshot],
    refusals: Sequence[SnapshotRefusal] = (),
) -> ShortInterestVintage:
    return ShortInterestVintage(
        manifest=manifest,
        release_calendar=tuple(release_calendar),
        snapshots=tuple(snapshots),
        refusals=tuple(refusals),
    )


def _content(vintage: ShortInterestVintage) -> tuple[dict[str, Any], dict[str, bytes]]:
    if type(vintage) is not ShortInterestVintage:
        raise _refuse("vintage must be the exact ShortInterestVintage type")
    blobs = {
        "source_manifest.json": _manifest_bytes(vintage.manifest),
        "release_calendar.jsonl": _jsonl_bytes(
            [item.to_payload() for item in vintage.release_calendar]
        ),
        "snapshots.jsonl": _jsonl_bytes(
            [item.to_payload() for item in vintage.snapshots]
        ),
        "refusals.jsonl": _jsonl_bytes(
            [item.to_payload() for item in vintage.refusals]
        ),
    }
    lineage = {
        "kind": DATASET_KIND,
        "contract_version": DATASET_CONTRACT_VERSION,
        "preregistration_sha256": PREREGISTRATION.sha256,
        "source_manifest_sha256": hash_bytes(blobs["source_manifest.json"]),
        "release_count": len(vintage.release_calendar),
        "snapshot_count": len(vintage.snapshots),
        "refusal_count": len(vintage.refusals),
        "release_calendar_sha256": hash_bytes(blobs["release_calendar.jsonl"]),
        "snapshots_sha256": hash_bytes(blobs["snapshots.jsonl"]),
        "refusals_sha256": hash_bytes(blobs["refusals.jsonl"]),
    }
    content_hash = hash_payload(lineage)
    identity = {
        **lineage,
        "content_hash": content_hash,
        "dataset_id": f"short-interest-vintage-{content_hash[:16]}",
    }
    return identity, blobs


def build_identity(vintage: ShortInterestVintage) -> dict[str, Any]:
    identity, _ = _content(vintage)
    return identity


def write_vintage(vintage: ShortInterestVintage, out_root: str | Path) -> dict[str, Any]:
    """Publish all authenticated parts without replacing an existing byte."""
    if type(vintage) is not ShortInterestVintage:
        raise _refuse("vintage must be the exact ShortInterestVintage type")
    identity, blobs = _content(vintage)
    target = Path(out_root) / identity["dataset_id"]
    identity_bytes = (canonical_json(identity) + "\n").encode("utf-8")
    if target.exists():
        try:
            existing_entries = tuple(target.iterdir())
        except OSError as exc:
            raise _refuse(f"immutable vintage target is unreadable: {exc}") from exc
        unknown = {entry.name for entry in existing_entries} - _ALL_ARTIFACT_FILES
        if unknown:
            raise _refuse(
                f"immutable vintage target contains unauthorized files: {sorted(unknown)}"
            )
        if any(entry.is_symlink() or not entry.is_file() for entry in existing_entries):
            raise _refuse("immutable vintage target contains a non-regular entry")
    try:
        for filename in _DATA_FILES:
            publish_immutable_bytes(target / filename, blobs[filename])
        publish_immutable_bytes(target / "dataset.json", identity_bytes)
    except ImmutableFileConflictError as exc:
        raise _refuse(f"immutable vintage conflict at {target}: {exc}") from exc
    authenticated_identity, authenticated_blobs = _authenticate_identity(target)
    if authenticated_identity != identity or authenticated_blobs != blobs:
        raise _refuse("published vintage does not authenticate to the requested content")
    return identity


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        raise _refuse(f"{path} is missing or invalid JSON: {exc}") from exc


def _parse_json_bytes(blob: bytes, label: str) -> Any:
    try:
        return json.loads(blob)
    except (TypeError, ValueError) as exc:
        raise _refuse(f"{label} is invalid JSON: {exc}") from exc


def _parse_jsonl_bytes(blob: bytes, label: str) -> list[Any]:
    if blob and not blob.endswith(b"\n"):
        raise _refuse(f"{label} is not canonical newline-terminated JSONL")
    values: list[Any] = []
    for line_number, line in enumerate(blob.splitlines(), start=1):
        try:
            values.append(json.loads(line))
        except (TypeError, ValueError) as exc:
            raise _refuse(f"{label}:{line_number} is invalid JSON: {exc}") from exc
    return values


def _authenticate_identity(dataset_dir: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    try:
        entries = tuple(dataset_dir.iterdir())
    except OSError as exc:
        raise _refuse(f"{dataset_dir} is missing or unreadable: {exc}") from exc
    entry_names = {entry.name for entry in entries}
    if entry_names != _ALL_ARTIFACT_FILES:
        raise _refuse(
            "immutable vintage file set mismatch; "
            f"missing={sorted(_ALL_ARTIFACT_FILES - entry_names)}, "
            f"unknown={sorted(entry_names - _ALL_ARTIFACT_FILES)}"
        )
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise _refuse(f"immutable vintage entry is not a regular file: {entry}")

    identity_path = dataset_dir / "dataset.json"
    try:
        identity_bytes = identity_path.read_bytes()
    except OSError as exc:
        raise _refuse(f"{identity_path} is missing or unreadable: {exc}") from exc
    identity = _parse_json_bytes(identity_bytes, "dataset.json")
    if not isinstance(identity, dict):
        raise _refuse(f"{identity_path} must contain one JSON object")
    expected_keys = {*_LINEAGE_KEYS, "content_hash", "dataset_id"}
    if set(identity) != expected_keys:
        raise _refuse(
            f"{identity_path} identity fields mismatch; "
            f"missing={sorted(expected_keys - set(identity))}, "
            f"unknown={sorted(set(identity) - expected_keys)}"
        )
    lineage = {key: identity[key] for key in _LINEAGE_KEYS}
    if lineage["kind"] != DATASET_KIND:
        raise _refuse("unknown short-interest dataset kind")
    if lineage["contract_version"] != DATASET_CONTRACT_VERSION:
        raise _refuse("unsupported short-interest dataset contract version")
    if lineage["preregistration_sha256"] != PREREGISTRATION.sha256:
        raise _refuse("dataset is not bound to the current preregistration")
    for count_name in ("release_count", "snapshot_count", "refusal_count"):
        count = lineage[count_name]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise _refuse(f"identity has invalid {count_name}")
    expected_hash = hash_payload(lineage)
    expected_id = f"short-interest-vintage-{expected_hash[:16]}"
    if identity["content_hash"] != expected_hash:
        raise _refuse("dataset content_hash does not authenticate lineage")
    if identity["dataset_id"] != expected_id or dataset_dir.name != expected_id:
        raise _refuse("dataset_id does not match content or directory name")
    canonical_identity_bytes = (canonical_json(identity) + "\n").encode("utf-8")
    if identity_bytes != canonical_identity_bytes:
        raise _refuse("dataset.json bytes are not canonical and immutable")

    blobs: dict[str, bytes] = {}
    hash_keys = {
        "source_manifest.json": "source_manifest_sha256",
        "release_calendar.jsonl": "release_calendar_sha256",
        "snapshots.jsonl": "snapshots_sha256",
        "refusals.jsonl": "refusals_sha256",
    }
    for filename, hash_key in hash_keys.items():
        path = dataset_dir / filename
        try:
            blob = path.read_bytes()
        except OSError as exc:
            raise _refuse(f"{path} is missing or unreadable: {exc}") from exc
        if hash_bytes(blob) != lineage[hash_key]:
            raise _refuse(f"{path} does not match {hash_key}")
        blobs[filename] = blob
    return identity, blobs


def load_vintage(dataset_dir: str | Path) -> ShortInterestVintage:
    directory = Path(dataset_dir)
    identity, blobs = _authenticate_identity(directory)
    manifest_payload = _parse_json_bytes(
        blobs["source_manifest.json"], "source_manifest.json"
    )
    releases_payload = _parse_jsonl_bytes(
        blobs["release_calendar.jsonl"], "release_calendar.jsonl"
    )
    snapshots_payload = _parse_jsonl_bytes(
        blobs["snapshots.jsonl"], "snapshots.jsonl"
    )
    refusals_payload = _parse_jsonl_bytes(
        blobs["refusals.jsonl"], "refusals.jsonl"
    )
    try:
        vintage = build_vintage(
            CollectionManifest.from_payload(manifest_payload),
            [ReleaseCalendarEntry.from_payload(item) for item in releases_payload],
            [ShortInterestSnapshot.from_payload(item) for item in snapshots_payload],
            [SnapshotRefusal.from_payload(item) for item in refusals_payload],
        )
    except (ShortInterestContractError, TypeError, ValueError) as exc:
        if isinstance(exc, ShortInterestDatasetError):
            raise
        raise _refuse(f"dataset content violates its contracts: {exc}") from exc
    rebuilt_identity, rebuilt_blobs = _content(vintage)
    if rebuilt_identity != identity or rebuilt_blobs != blobs:
        raise _refuse("dataset bytes are not canonical for their parsed contracts")
    return vintage


def load_synthetic_fixture(path: str | Path) -> ShortInterestVintage:
    """Load a Git-tracked synthetic official-style fixture; never a provider."""
    fixture_path = Path(path)
    payload = _load_json(fixture_path)
    expected_fields = {
        "fixture_kind",
        "manifest",
        "release_calendar",
        "snapshot_rows",
    }
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        actual = set(payload) if isinstance(payload, dict) else set()
        raise _refuse(
            "synthetic fixture fields mismatch; "
            f"missing={sorted(expected_fields - actual)}, "
            f"unknown={sorted(actual - expected_fields)}"
        )
    if payload["fixture_kind"] != SYNTHETIC_FIXTURE_KIND:
        raise _refuse("unknown synthetic fixture kind")
    if not isinstance(payload["release_calendar"], list) or not isinstance(
        payload["snapshot_rows"], list
    ):
        raise _refuse("release_calendar and snapshot_rows must be JSON arrays")
    try:
        manifest = CollectionManifest.from_payload(payload["manifest"])
        releases = tuple(
            ReleaseCalendarEntry.from_payload(item)
            for item in payload["release_calendar"]
        )
    except (ShortInterestContractError, TypeError, ValueError) as exc:
        raise _refuse(f"synthetic fixture contract failed: {exc}") from exc
    if manifest.entitlement is not SourceEntitlement.SYNTHETIC_FIXTURE_ONLY:
        raise _refuse("fixture loader accepts synthetic_fixture_only entitlement")
    expected_source_hash = fixture_source_payload_sha256(
        payload["release_calendar"], payload["snapshot_rows"]
    )
    if manifest.raw_artifact_sha256 != expected_source_hash:
        raise _refuse("fixture source body does not match raw_artifact_sha256")
    snapshots, refusals = normalize_snapshot_payloads(payload["snapshot_rows"])
    return build_vintage(manifest, releases, snapshots, refusals)


@dataclass(frozen=True)
class _SnapshotExecutionSelection:
    """Canonical source selection at one snapshot's authenticated open."""

    cohort: ExecutionCohort
    is_visible: bool
    is_delta_eligible: bool
    prior_snapshot: ShortInterestSnapshot | None


class _SourceVisibilitySweep:
    """One canonical latest-visible-revision sweep over an immutable vintage."""

    def __init__(self, vintage: ShortInterestVintage) -> None:
        release_by_key = {item.key: item for item in vintage.release_calendar}
        events: list[
            tuple[datetime, datetime, str, str, ShortInterestSnapshot]
        ] = []
        cohort_by_event: dict[str, ExecutionCohort] = {}
        for snapshot in vintage.snapshots:
            cohort = snapshot_execution_cohort(
                snapshot,
                release_by_key[snapshot.release_calendar_key],
            )
            cohort_by_event[snapshot.event_id] = cohort
            events.append(
                (
                    parse_utc_timestamp(cohort.opens_at, "cohort.opens_at"),
                    parse_utc_timestamp(
                        snapshot.revision_published_at,
                        "snapshot.revision_published_at",
                    ),
                    snapshot.logical_id,
                    snapshot.event_id,
                    snapshot,
                )
            )
        self.cohort_by_event: dict[str, ExecutionCohort] = cohort_by_event
        self._events = sorted(events)
        self._event_index = 0
        self._cutoff: datetime | None = None
        self._selected_by_logical: dict[
            str,
            tuple[datetime, ShortInterestSnapshot],
        ] = {}
        self._selected_by_identity: dict[
            tuple[str, str],
            tuple[str, ShortInterestSnapshot],
        ] = {}

    def _apply_visible_event(
        self,
        event: tuple[datetime, datetime, str, str, ShortInterestSnapshot],
    ) -> None:
        _, revision_at, logical_id, _, snapshot = event
        previous = self._selected_by_logical.get(logical_id)
        if previous is None or revision_at > previous[0]:
            if previous is not None:
                previous_identity = _snapshot_prior_identity(previous[1])
                selected = self._selected_by_identity.get(previous_identity)
                if selected is not None and selected[0] == logical_id:
                    self._selected_by_identity.pop(previous_identity)
            identity = _snapshot_prior_identity(snapshot)
            conflict = self._selected_by_identity.get(identity)
            if conflict is not None and conflict[0] != logical_id:
                raise _refuse(
                    "execution-visible source snapshot identity is ambiguous"
                )
            self._selected_by_logical[logical_id] = (
                revision_at,
                snapshot,
            )
            self._selected_by_identity[identity] = (logical_id, snapshot)

    def advance(self, cutoff: datetime) -> None:
        if self._cutoff is not None and cutoff < self._cutoff:
            raise _refuse("source visibility sweep cutoffs must be nondecreasing")
        self._cutoff = cutoff
        while (
            self._event_index < len(self._events)
            and self._events[self._event_index][0] <= cutoff
        ):
            self._apply_visible_event(self._events[self._event_index])
            self._event_index += 1

    def selected_for_logical(
        self, logical_id: str
    ) -> ShortInterestSnapshot | None:
        selected = self._selected_by_logical.get(logical_id)
        return selected[1] if selected is not None else None

    def selected_for_identity(
        self, security_id: str, settlement_date: str
    ) -> ShortInterestSnapshot | None:
        selected = self._selected_by_identity.get(
            (security_id, settlement_date)
        )
        return selected[1] if selected is not None else None

    def visible_snapshots(self) -> tuple[ShortInterestSnapshot, ...]:
        return tuple(
            sorted(
                (item[1] for item in self._selected_by_logical.values()),
                key=lambda item: (
                    item.settlement_date,
                    item.security.security_id,
                ),
            )
        )


def _snapshot_execution_selection_index(
    vintage: ShortInterestVintage,
) -> dict[str, _SnapshotExecutionSelection]:
    """Index visibility, immediate prior, and delta eligibility for all rows."""
    if type(vintage) is not ShortInterestVintage:
        raise _refuse("vintage must be the exact ShortInterestVintage type")
    sweep = _SourceVisibilitySweep(vintage)
    queries = sorted(
        (
            parse_utc_timestamp(
                sweep.cohort_by_event[snapshot.event_id].opens_at,
                "cohort.opens_at",
            ),
            snapshot.event_id,
            snapshot,
        )
        for snapshot in vintage.snapshots
    )
    selections: dict[str, _SnapshotExecutionSelection] = {}
    for execution_at, event_id, snapshot in queries:
        sweep.advance(execution_at)
        visible = sweep.selected_for_logical(snapshot.logical_id)
        prior = sweep.selected_for_identity(
            snapshot.security.security_id,
            snapshot.previous_settlement_date,
        )
        is_visible = visible is not None and visible.event_id == event_id
        selections[event_id] = _SnapshotExecutionSelection(
            cohort=sweep.cohort_by_event[event_id],
            is_visible=is_visible,
            is_delta_eligible=(
                is_visible
                and prior is not None
                and prior.current_short_shares == snapshot.previous_short_shares
            ),
            prior_snapshot=prior,
        )
    if len(selections) != len(vintage.snapshots):
        raise _refuse("execution selection index does not cover every source event")
    return selections


def visible_source_snapshots_as_of(
    vintage: ShortInterestVintage,
    cutoff: datetime,
) -> tuple[ShortInterestSnapshot, ...]:
    """Latest source revisions usable by ``cutoff``, including warm-up rows.

    This is a data-lineage view, not a delta-signal boundary. Call
    ``delta_eligible_snapshots_as_of`` before any future ratio-change work.
    """
    if type(vintage) is not ShortInterestVintage:
        raise _refuse("vintage must be the exact ShortInterestVintage type")
    if (
        not isinstance(cutoff, datetime)
        or cutoff.tzinfo is None
        or cutoff.utcoffset() is None
    ):
        raise _refuse("cutoff must be a timezone-aware datetime")
    sweep = _SourceVisibilitySweep(vintage)
    sweep.advance(cutoff.astimezone(timezone.utc))
    return sweep.visible_snapshots()


def delta_eligible_snapshots_as_of(
    vintage: ShortInterestVintage,
    cutoff: datetime,
) -> tuple[ShortInterestSnapshot, ...]:
    """Visible rows whose immediately prior cycle is authenticated and visible."""
    visible = visible_source_snapshots_as_of(vintage, cutoff)
    prior_by_identity = {
        (item.security.security_id, item.settlement_date): item for item in visible
    }
    eligible = []
    for snapshot in visible:
        prior = prior_by_identity.get(
            (snapshot.security.security_id, snapshot.previous_settlement_date)
        )
        if prior is None:
            continue
        if prior.current_short_shares != snapshot.previous_short_shares:
            continue
        eligible.append(snapshot)
    return tuple(eligible)
