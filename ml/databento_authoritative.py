"""Vintage-correct Databento feature lineage for research and online use.

This module is the reviewed authority boundary missing from the raw snapshot
collectors. It never treats a security-master listing as strategy/index
membership: callers must supply an independently captured historical universe.
The same pure builder is used by historical replay and the online provider.
"""
from __future__ import annotations

import dataclasses
import json
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import pandas as pd

from ml.availability import (
    CoverageResult,
    FeatureAvailabilityRecord,
    UniverseMembershipRecord,
    evaluate_point_in_time_coverage,
    hash_feature_value,
)
from ml.databento_pit import (
    CompleteStatisticsCohort,
    HistoricalClient,
    StatisticsRequest,
    fetch_statistics_snapshot,
    select_complete_statistics_cohorts,
)
from ml.databento_source import DatabentoSourceError, write_immutable_bytes
from ml.hashing import canonical_json, hash_payload


SOURCE_ID = "databento_vintage_adjusted"
SCHEMA_VERSION = "1"
_PRICE_FEATURES = frozenset({"open", "high", "low", "close"})
_FEATURES = ("open", "high", "low", "close", "volume")
_SPLIT_REASONS = frozenset({5, 6})


class DatabentoAuthorityError(DatabentoSourceError):
    pass


def _timestamp(value: Any, name: str) -> datetime:
    if isinstance(value, pd.Timestamp):
        parsed = value.to_pydatetime()
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DatabentoAuthorityError(f"{name} must be an ISO timestamp") from exc
    else:
        raise DatabentoAuthorityError(f"{name} must be an ISO timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DatabentoAuthorityError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _session(value: Any, name: str) -> date:
    if not isinstance(value, str):
        raise DatabentoAuthorityError(f"{name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DatabentoAuthorityError(f"{name} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise DatabentoAuthorityError(f"{name} must be canonical YYYY-MM-DD")
    return parsed


def _sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise DatabentoAuthorityError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _required_text(record: Mapping[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if value in (None, ""):
        raise DatabentoAuthorityError(f"{context}.{key} is missing")
    return str(value)


def _positive_decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise DatabentoAuthorityError(f"{name} must be positive and finite")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DatabentoAuthorityError(f"{name} must be positive and finite") from exc
    if not result.is_finite() or result <= 0:
        raise DatabentoAuthorityError(f"{name} must be positive and finite")
    return result


@dataclasses.dataclass(frozen=True)
class AdjustmentOptionPolicy:
    """Exactly one shareholder option per corporate-action event."""

    default_option: int = 1
    event_options: Mapping[str, int] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            isinstance(self.default_option, bool)
            or not isinstance(self.default_option, int)
            or not 1 <= self.default_option <= 9
        ):
            raise DatabentoAuthorityError("default_option must be 1 through 9")
        options: dict[str, int] = {}
        for event_id, option in self.event_options.items():
            if not isinstance(event_id, str) or not event_id:
                raise DatabentoAuthorityError("event option IDs must be non-empty strings")
            if isinstance(option, bool) or not isinstance(option, int) or not 1 <= option <= 9:
                raise DatabentoAuthorityError(f"event option for {event_id} must be 1 through 9")
            options[event_id] = option
        object.__setattr__(self, "event_options", MappingProxyType(options))

    def option_for(self, event_id: str) -> int:
        return self.event_options.get(event_id, self.default_option)

    @property
    def policy_hash(self) -> str:
        return hash_payload(
            {"default_option": self.default_option, "event_options": dict(self.event_options)}
        )


@dataclasses.dataclass(frozen=True)
class ResolvedListing:
    ticker: str
    listing_id: str
    security_id: str
    operating_mic: str
    listing_status: str
    effective_at: str
    recorded_at: str
    created_at: str
    revision_id: str


@dataclasses.dataclass(frozen=True)
class AppliedAdjustment:
    event_id: str
    security_id: str
    ex_date: str
    created_at: str
    factor: str
    reason: int
    option: int
    status: str
    revision_id: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def resolve_listing_revision(
    records: Sequence[Mapping[str, Any]],
    *,
    ticker: str,
    event_at: str,
    decision_cutoff: str,
) -> ResolvedListing:
    event = _timestamp(event_at, "event_at")
    cutoff = _timestamp(decision_cutoff, "decision_cutoff")
    candidates: list[tuple[datetime, datetime, datetime, str, Mapping[str, Any]]] = []
    for position, record in enumerate(records):
        if str(record.get("symbol") or "") != ticker:
            continue
        effective = _timestamp(record.get("ts_effective"), f"security_master[{position}].ts_effective")
        recorded = _timestamp(record.get("ts_record"), f"security_master[{position}].ts_record")
        created = _timestamp(record.get("ts_created"), f"security_master[{position}].ts_created")
        if created > cutoff or effective > event:
            continue
        digest = hash_payload(dict(record))
        candidates.append((effective, recorded, created, digest, record))
    if not candidates:
        raise DatabentoAuthorityError(
            f"no {ticker} security-master revision was visible and effective by {decision_cutoff}"
        )
    effective, recorded, created, digest, selected = max(candidates, key=lambda item: item[:4])
    status = _required_text(selected, "listing_status", "security_master")
    if status != "A":
        raise DatabentoAuthorityError(
            f"{ticker} listing status at the decision cutoff is {status!r}, not active ('A')"
        )
    return ResolvedListing(
        ticker=ticker,
        listing_id=_required_text(selected, "listing_id", "security_master"),
        security_id=_required_text(selected, "security_id", "security_master"),
        operating_mic=_required_text(selected, "operating_mic", "security_master"),
        listing_status=status,
        effective_at=effective.isoformat(),
        recorded_at=recorded.isoformat(),
        created_at=created.isoformat(),
        revision_id=digest,
    )


def resolve_adjustment_vintage(
    records: Sequence[Mapping[str, Any]],
    *,
    listing: ResolvedListing,
    as_of_session: str,
    decision_cutoff: str,
    option_policy: AdjustmentOptionPolicy,
) -> tuple[AppliedAdjustment, ...]:
    row_session = _session(as_of_session, "as_of_session")
    cutoff = _timestamp(decision_cutoff, "decision_cutoff")
    grouped: dict[tuple[str, str, int], list[tuple[datetime, str, Mapping[str, Any]]]] = {}
    for position, record in enumerate(records):
        if str(record.get("security_id") or "") != listing.security_id:
            continue
        if str(record.get("operating_mic") or "") != listing.operating_mic:
            continue
        ex_date = _session(str(record.get("ex_date")), f"adjustment[{position}].ex_date")
        if ex_date <= row_session:
            continue
        created = _timestamp(record.get("ts_created"), f"adjustment[{position}].ts_created")
        if created > cutoff:
            continue
        event_id = _required_text(record, "event_id", f"adjustment[{position}]")
        try:
            option = int(record.get("option"))
        except (TypeError, ValueError) as exc:
            raise DatabentoAuthorityError(f"adjustment[{position}].option is invalid") from exc
        if option != option_policy.option_for(event_id):
            continue
        digest = hash_payload(dict(record))
        grouped.setdefault((event_id, ex_date.isoformat(), option), []).append(
            (created, digest, record)
        )

    applied: list[AppliedAdjustment] = []
    for (event_id, ex_date, option), revisions in sorted(grouped.items()):
        created, digest, selected = max(revisions, key=lambda item: item[:2])
        status = _required_text(selected, "status", "adjustment")
        if status == "R":
            continue
        if status == "P":
            # Pending is the correct historical vintage but is not final and
            # therefore must not be applied as if it were an A record.
            continue
        if status != "A":
            raise DatabentoAuthorityError(f"unsupported adjustment status {status!r}")
        reason = selected.get("reason")
        if isinstance(reason, bool) or not isinstance(reason, int) or reason <= 0:
            raise DatabentoAuthorityError("adjustment reason must be a positive integer")
        factor = _positive_decimal(selected.get("factor"), "adjustment factor")
        applied.append(
            AppliedAdjustment(
                event_id=event_id,
                security_id=listing.security_id,
                ex_date=ex_date,
                created_at=created.isoformat(),
                factor=format(factor, "f"),
                reason=reason,
                option=option,
                status=status,
                revision_id=digest,
            )
        )
    return tuple(applied)


def _adjust_value(feature_name: str, value: Any, adjustments: Sequence[AppliedAdjustment]) -> float:
    adjusted = _positive_decimal(value, feature_name)
    for item in adjustments:
        factor = _positive_decimal(item.factor, "adjustment factor")
        if feature_name in _PRICE_FEATURES:
            adjusted *= factor
        elif feature_name == "volume" and item.reason in _SPLIT_REASONS:
            adjusted /= factor
    result = float(adjusted)
    if not math.isfinite(result) or result <= 0:  # pragma: no cover - Decimal guards this
        raise DatabentoAuthorityError("adjusted feature is not positive and finite")
    return result


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(json.loads(canonical_json(dict(value))))


@dataclasses.dataclass(frozen=True)
class AuthoritativeFeatureBatch:
    rows: tuple[Mapping[str, Any], ...]
    availability: tuple[FeatureAvailabilityRecord, ...]
    universe: tuple[UniverseMembershipRecord, ...]
    coverage: CoverageResult
    refusals: tuple[Mapping[str, str], ...]
    manifest: Mapping[str, Any]

    def __post_init__(self) -> None:
        rows = tuple(_freeze_mapping(item) for item in self.rows)
        refusals = tuple(_freeze_mapping(item) for item in self.refusals)
        manifest = _freeze_mapping(self.manifest)
        if manifest.get("batch_hash") != hash_payload(
            {key: value for key, value in dict(manifest).items() if key != "batch_hash"}
        ):
            raise DatabentoAuthorityError("authoritative feature batch hash mismatch")
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "availability", tuple(self.availability))
        object.__setattr__(self, "universe", tuple(self.universe))
        object.__setattr__(self, "refusals", refusals)
        object.__setattr__(self, "manifest", manifest)

    @property
    def batch_hash(self) -> str:
        return str(self.manifest["batch_hash"])

    def feature_frame(self) -> pd.DataFrame:
        return pd.DataFrame([dict(row) for row in self.rows]).sort_values(
            ["as_of_session", "ticker"], ignore_index=True
        )


def build_authoritative_feature_batch(
    cohorts: Sequence[CompleteStatisticsCohort],
    *,
    security_master_records: Sequence[Mapping[str, Any]],
    adjustment_factor_records: Sequence[Mapping[str, Any]],
    historical_universe: Sequence[UniverseMembershipRecord],
    universe_id: str,
    decision_cutoffs: Mapping[str, str],
    reference_observed_at: str,
    statistics_snapshot_hash: str,
    security_master_snapshot_hash: str,
    adjustment_snapshot_hash: str,
    universe_snapshot_hash: str,
    option_policy: AdjustmentOptionPolicy | None = None,
) -> AuthoritativeFeatureBatch:
    """Apply the exact reference vintage visible at every decision cutoff."""
    source_hashes = {
        "statistics": _sha256(statistics_snapshot_hash, "statistics_snapshot_hash"),
        "security_master": _sha256(security_master_snapshot_hash, "security_master_snapshot_hash"),
        "adjustments": _sha256(adjustment_snapshot_hash, "adjustment_snapshot_hash"),
        "universe": _sha256(universe_snapshot_hash, "universe_snapshot_hash"),
    }
    if not isinstance(universe_id, str) or not universe_id:
        raise DatabentoAuthorityError("universe_id must be a non-empty string")
    reference_observed = _timestamp(reference_observed_at, "reference_observed_at")
    policy = option_policy or AdjustmentOptionPolicy()
    rows: list[Mapping[str, Any]] = []
    availability: list[FeatureAvailabilityRecord] = []
    refusals: list[Mapping[str, str]] = []
    feature_values: dict[tuple[str, str, str], float] = {}
    seen: set[tuple[str, str]] = set()

    for cohort in sorted(cohorts, key=lambda item: (item.as_of_session, item.ticker)):
        key = (cohort.as_of_session, cohort.ticker)
        if key in seen:
            raise DatabentoAuthorityError(f"duplicate statistics cohort for {key}")
        seen.add(key)
        cutoff_text = decision_cutoffs.get(cohort.as_of_session)
        if cutoff_text is None:
            refusals.append({
                "as_of_session": cohort.as_of_session,
                "ticker": cohort.ticker,
                "reason": "missing decision cutoff",
            })
            continue
        cutoff = _timestamp(cutoff_text, f"decision_cutoffs[{cohort.as_of_session}]")
        try:
            listing = resolve_listing_revision(
                security_master_records,
                ticker=cohort.ticker,
                event_at=max(record.event_at for record in cohort.records),
                decision_cutoff=cutoff.isoformat(),
            )
            adjustments = resolve_adjustment_vintage(
                adjustment_factor_records,
                listing=listing,
                as_of_session=cohort.as_of_session,
                decision_cutoff=cutoff.isoformat(),
                option_policy=policy,
            )
            ingredients_available = max(
                [_timestamp(cohort.available_at, "cohort.available_at"), _timestamp(listing.created_at, "listing.created_at")]
                + [_timestamp(item.created_at, "adjustment.created_at") for item in adjustments]
            )
            observed = max(
                _timestamp(cohort.observed_at, "cohort.observed_at"),
                reference_observed,
            )
            if ingredients_available > cutoff:
                raise DatabentoAuthorityError("a selected input became available after the decision cutoff")
            if ingredients_available > observed:
                raise DatabentoAuthorityError("reference_observed_at precedes selected reference evidence")
            raw_by_feature = {record.feature_name: record for record in cohort.records}
            adjusted_values = {
                feature: _adjust_value(feature, raw_by_feature[feature].value, adjustments)
                for feature in _FEATURES
            }
        except DatabentoAuthorityError as exc:
            refusals.append({
                "as_of_session": cohort.as_of_session,
                "ticker": cohort.ticker,
                "reason": str(exc),
            })
            continue

        row: dict[str, Any] = {
            "as_of_session": cohort.as_of_session,
            "ticker": cohort.ticker,
            **adjusted_values,
            "listing_id": listing.listing_id,
            "security_id": listing.security_id,
            "operating_mic": listing.operating_mic,
            "decision_cutoff": cutoff.isoformat(),
            "cohort_id": cohort.cohort_id,
            "adjustment_revision_count": len(adjustments),
        }
        rows.append(row)
        adjustment_material = [item.to_dict() for item in adjustments]
        for feature in _FEATURES:
            raw = raw_by_feature[feature]
            value = adjusted_values[feature]
            revision_id = hash_payload({
                "cohort_revision": raw.revision_id,
                "listing_revision": listing.revision_id,
                "adjustments": adjustment_material,
                "option_policy_hash": policy.policy_hash,
                "adjusted_value": value,
            })
            availability.append(
                FeatureAvailabilityRecord(
                    as_of_session=cohort.as_of_session,
                    ticker=cohort.ticker,
                    feature_name=feature,
                    event_at=raw.event_at,
                    available_at=ingredients_available.isoformat(),
                    observed_at=observed.isoformat(),
                    source_id=SOURCE_ID,
                    source_version=SCHEMA_VERSION,
                    revision_id=revision_id,
                    raw_value_hash=hash_feature_value(value),
                )
            )
            feature_values[(cohort.as_of_session, cohort.ticker, feature)] = value

    if not rows:
        reasons = "; ".join(item["reason"] for item in refusals) or "no cohorts supplied"
        raise DatabentoAuthorityError(f"no authoritative feature rows were produced: {reasons}")
    feature_keys = [(row["as_of_session"], row["ticker"]) for row in rows]
    coverage = evaluate_point_in_time_coverage(
        feature_keys=feature_keys,
        feature_columns=list(_FEATURES),
        availability=availability,
        universe=historical_universe,
        universe_id=universe_id,
        decision_cutoffs=decision_cutoffs,
        feature_values=feature_values,
    )
    row_material = [dict(row) for row in rows]
    availability_material = [record.to_dict() for record in availability]
    universe_material = [record.to_dict() for record in historical_universe]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_id": SOURCE_ID,
        "source_hashes": source_hashes,
        "option_policy": {
            "default_option": policy.default_option,
            "event_options": dict(policy.event_options),
            "policy_hash": policy.policy_hash,
        },
        "universe_id": universe_id,
        "reference_observed_at": reference_observed.isoformat(),
        "decision_cutoffs": dict(sorted(decision_cutoffs.items())),
        "row_count": len(rows),
        "refusal_count": len(refusals),
        "underfilled": bool(refusals),
        "rows_hash": hash_payload(row_material),
        "availability_hash": hash_payload(availability_material),
        "universe_hash": hash_payload(universe_material),
        "point_in_time_data": coverage.point_in_time_data,
        "coverage": coverage.to_dict(),
    }
    manifest["batch_hash"] = hash_payload(manifest)
    return AuthoritativeFeatureBatch(
        rows=tuple(rows),
        availability=tuple(availability),
        universe=tuple(historical_universe),
        coverage=coverage,
        refusals=tuple(refusals),
        manifest=manifest,
    )


def save_authoritative_feature_batch(
    batch: AuthoritativeFeatureBatch, directory: Path
) -> Path:
    """Persist a content-addressed batch without mutable "latest" files."""
    root = Path(directory) / batch.batch_hash
    artifacts = {
        "features.json": canonical_json([dict(row) for row in batch.rows]).encode("utf-8"),
        "availability.json": canonical_json(
            [record.to_dict() for record in batch.availability]
        ).encode("utf-8"),
        "universe.json": canonical_json(
            [record.to_dict() for record in batch.universe]
        ).encode("utf-8"),
        "refusals.json": canonical_json([dict(item) for item in batch.refusals]).encode("utf-8"),
        "manifest.json": canonical_json(dict(batch.manifest)).encode("utf-8"),
    }
    root.mkdir(parents=True, exist_ok=True)
    for filename, payload in artifacts.items():
        path = root / filename
        if path.exists():
            if path.read_bytes() != payload:
                raise DatabentoAuthorityError(
                    f"authoritative batch artifact conflicts with {path}"
                )
            continue
        write_immutable_bytes(path, payload)
    return root


def load_authoritative_feature_batch(directory: Path) -> AuthoritativeFeatureBatch:
    root = Path(directory)
    def load_canonical(filename: str) -> Any:
        path = root / filename
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
        if raw != canonical_json(value).encode("utf-8"):
            raise DatabentoAuthorityError(
                f"authoritative batch artifact is not canonical: {filename}"
            )
        return value

    try:
        manifest = load_canonical("manifest.json")
        rows = load_canonical("features.json")
        availability_payload = load_canonical("availability.json")
        universe_payload = load_canonical("universe.json")
        refusals = load_canonical("refusals.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatabentoAuthorityError(f"invalid authoritative feature batch: {exc}") from exc
    if root.name != manifest.get("batch_hash"):
        raise DatabentoAuthorityError("authoritative batch directory does not match batch_hash")
    if hash_payload(rows) != manifest.get("rows_hash"):
        raise DatabentoAuthorityError("authoritative feature rows hash mismatch")
    if hash_payload(availability_payload) != manifest.get("availability_hash"):
        raise DatabentoAuthorityError("authoritative availability hash mismatch")
    if hash_payload(universe_payload) != manifest.get("universe_hash"):
        raise DatabentoAuthorityError("authoritative universe hash mismatch")
    try:
        availability = tuple(
            FeatureAvailabilityRecord.from_dict(item) for item in availability_payload
        )
        universe = tuple(UniverseMembershipRecord.from_dict(item) for item in universe_payload)
        coverage = CoverageResult.from_dict(manifest["coverage"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DatabentoAuthorityError(f"invalid authoritative batch contract: {exc}") from exc
    return AuthoritativeFeatureBatch(
        rows=tuple(rows),
        availability=availability,
        universe=universe,
        coverage=coverage,
        refusals=tuple(refusals),
        manifest=manifest,
    )


@dataclasses.dataclass(frozen=True)
class HistoricalUniverseSnapshot:
    universe_id: str
    source_id: str
    source_version: str
    observed_at: str
    source_artifact_hash: str
    records: tuple[UniverseMembershipRecord, ...]
    snapshot_hash: str

    def __post_init__(self) -> None:
        observed = _timestamp(self.observed_at, "observed_at")
        _sha256(self.source_artifact_hash, "source_artifact_hash")
        records = tuple(self.records)
        if not records:
            raise DatabentoAuthorityError("historical universe cannot be empty")
        for record in records:
            if record.universe_id != self.universe_id:
                raise DatabentoAuthorityError("historical universe record has the wrong universe_id")
            if record.source_id != self.source_id or record.source_version != self.source_version:
                raise DatabentoAuthorityError("historical universe record lineage mismatch")
            if _timestamp(record.available_at, "universe.available_at") > observed:
                raise DatabentoAuthorityError("universe record was not available when the snapshot was observed")
        expected = hash_payload({
            "universe_id": self.universe_id,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "observed_at": observed.isoformat(),
            "source_artifact_hash": self.source_artifact_hash,
            "records": [record.to_dict() for record in records],
        })
        if self.snapshot_hash != expected:
            raise DatabentoAuthorityError("historical universe snapshot hash mismatch")
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "observed_at", observed.isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe_id": self.universe_id,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "observed_at": self.observed_at,
            "source_artifact_hash": self.source_artifact_hash,
            "records": [record.to_dict() for record in self.records],
            "snapshot_hash": self.snapshot_hash,
        }


def build_historical_universe_snapshot(
    records: Sequence[UniverseMembershipRecord],
    *,
    universe_id: str,
    source_id: str,
    source_version: str,
    observed_at: str,
    source_artifact_hash: str,
) -> HistoricalUniverseSnapshot:
    observed = _timestamp(observed_at, "observed_at").isoformat()
    material = {
        "universe_id": universe_id,
        "source_id": source_id,
        "source_version": source_version,
        "observed_at": observed,
        "source_artifact_hash": _sha256(source_artifact_hash, "source_artifact_hash"),
        "records": [record.to_dict() for record in records],
    }
    return HistoricalUniverseSnapshot(
        universe_id=universe_id,
        source_id=source_id,
        source_version=source_version,
        observed_at=observed,
        source_artifact_hash=material["source_artifact_hash"],
        records=tuple(records),
        snapshot_hash=hash_payload(material),
    )


def save_historical_universe_snapshot(snapshot: HistoricalUniverseSnapshot, path: Path) -> None:
    path = Path(path)
    payload = canonical_json(snapshot.to_dict()).encode("utf-8")
    if path.exists():
        if path.read_bytes() == payload:
            return
        raise DatabentoAuthorityError(f"refusing to overwrite historical universe snapshot {path}")
    write_immutable_bytes(path, payload)


def load_historical_universe_snapshot(path: Path) -> HistoricalUniverseSnapshot:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        records = tuple(UniverseMembershipRecord.from_dict(item) for item in payload.pop("records"))
        return HistoricalUniverseSnapshot(records=records, **payload)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, DatabentoAuthorityError):
            raise
        raise DatabentoAuthorityError(f"invalid historical universe snapshot: {exc}") from exc


class DatabentoPointInTimeSource:
    """PointInTimeSource facade over one verified authoritative batch."""

    source_id = SOURCE_ID
    provides_point_in_time_lineage = True

    def __init__(self, batch: AuthoritativeFeatureBatch) -> None:
        if not batch.coverage.point_in_time_data:
            raise DatabentoAuthorityError("source requires a batch with complete point-in-time coverage")
        self.batch = batch

    def feature_records(
        self, *, tickers: Sequence[str], start_session: str, end_session: str
    ) -> Sequence[FeatureAvailabilityRecord]:
        requested = set(tickers)
        start = _session(start_session, "start_session")
        end = _session(end_session, "end_session")
        return tuple(
            record for record in self.batch.availability
            if record.ticker in requested and start <= _session(record.as_of_session, "as_of_session") <= end
        )

    def universe_membership(
        self, *, universe_id: str, start_session: str, end_session: str
    ) -> Sequence[UniverseMembershipRecord]:
        start = _session(start_session, "start_session")
        end = _session(end_session, "end_session")
        if universe_id != self.batch.manifest["universe_id"]:
            return ()
        return tuple(
            record for record in self.batch.universe
            if _session(record.effective_from, "effective_from") <= end
            and (record.effective_to is None or _session(record.effective_to, "effective_to") >= start)
        )

    def source_manifest(self) -> Mapping[str, str]:
        return {
            "source_id": SOURCE_ID,
            "source_version": SCHEMA_VERSION,
            "provides_point_in_time_lineage": "true",
            "batch_hash": self.batch.batch_hash,
            "universe_id": str(self.batch.manifest["universe_id"]),
        }


class DatabentoOnlineFeatureProvider:
    """Cost-capped online capture using the same pure historical builder."""

    def __init__(
        self,
        *,
        directory: Path,
        max_cost_usd: float,
        security_master_records: Sequence[Mapping[str, Any]],
        adjustment_factor_records: Sequence[Mapping[str, Any]],
        historical_universe: HistoricalUniverseSnapshot,
        reference_observed_at: str,
        security_master_snapshot_hash: str,
        adjustment_snapshot_hash: str,
        option_policy: AdjustmentOptionPolicy | None = None,
        client: HistoricalClient | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.max_cost_usd = max_cost_usd
        self.security_master_records = tuple(security_master_records)
        self.adjustment_factor_records = tuple(adjustment_factor_records)
        self.historical_universe = historical_universe
        self.reference_observed_at = _timestamp(reference_observed_at, "reference_observed_at").isoformat()
        self.security_master_snapshot_hash = _sha256(
            security_master_snapshot_hash, "security_master_snapshot_hash"
        )
        self.adjustment_snapshot_hash = _sha256(
            adjustment_snapshot_hash, "adjustment_snapshot_hash"
        )
        self.option_policy = option_policy or AdjustmentOptionPolicy()
        self.client = client

    def collect(
        self,
        *,
        tickers: Sequence[str],
        session: str,
        decision_cutoff: str | None = None,
        summary_flag: int = 1,
    ) -> AuthoritativeFeatureBatch:
        session_date = _session(session, "session")
        request = StatisticsRequest(
            tickers=tuple(tickers),
            start=session,
            end=(session_date + timedelta(days=1)).isoformat(),
            summary_flag=summary_flag,
        )
        snapshot = fetch_statistics_snapshot(
            request,
            directory=self.directory,
            max_cost_usd=self.max_cost_usd,
            client=self.client,
        )
        observed = str(snapshot.manifest["observed_at"])
        cutoff = decision_cutoff or observed
        if _timestamp(observed, "statistics observed_at") > _timestamp(cutoff, "decision_cutoff"):
            raise DatabentoAuthorityError(
                "online statistics were observed after the declared decision cutoff"
            )
        cohorts = select_complete_statistics_cohorts(
            snapshot.normalized,
            decision_cutoffs={session: cutoff},
            observed_at=observed,
        )
        return build_authoritative_feature_batch(
            cohorts,
            security_master_records=self.security_master_records,
            adjustment_factor_records=self.adjustment_factor_records,
            historical_universe=self.historical_universe.records,
            universe_id=self.historical_universe.universe_id,
            decision_cutoffs={session: cutoff},
            reference_observed_at=self.reference_observed_at,
            statistics_snapshot_hash=str(snapshot.manifest["raw_sha256"]),
            security_master_snapshot_hash=self.security_master_snapshot_hash,
            adjustment_snapshot_hash=self.adjustment_snapshot_hash,
            universe_snapshot_hash=self.historical_universe.snapshot_hash,
            option_policy=self.option_policy,
        )
