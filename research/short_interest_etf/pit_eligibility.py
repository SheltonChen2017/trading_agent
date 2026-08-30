"""Outcome-free PIT reference contracts and stock-data readiness for SI-2A.

This module decides only whether the source facts needed for a later stock
signal are structurally ready.  It never imports prices, returns, ETFs,
providers, QuantConnect, brokers, or execution code.  A ready result is not a
claim of predictive value and does not authorize a research outcome look.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from data.exchange_calendar import ExchangeCalendarError, session_open_instant
from data.hashing import hash_payload
from research.short_interest_etf.availability import snapshot_execution_cohort
from research.short_interest_etf.contracts import (
    DenominatorKind,
    SourceEntitlement,
    _canonical_date,
    _enum,
    _git_commit,
    _integer,
    _payload_fields,
    _required_text,
    _sha256,
    format_utc_timestamp,
    parse_utc_timestamp,
)
from research.short_interest_etf.dataset import (
    ShortInterestVintage,
    build_identity,
    delta_eligible_snapshots_as_of,
    visible_source_snapshots_as_of,
)

REFERENCE_SCHEMA_VERSION = "1.0"
REFERENCE_SEMANTIC = "pit_security_lifecycle_and_sector_reference"
SYNTHETIC_REFERENCE_FIXTURE_KIND = "synthetic-short-interest-pit-reference-v1"

REFUSAL_AMBIGUOUS_CLASSIFICATION = "ambiguous_sector_classification"
REFUSAL_AMBIGUOUS_LIFECYCLE = "ambiguous_security_lifecycle"
REFUSAL_IDENTITY_NOT_VALID = "security_identity_not_valid_at_execution"
REFUSAL_MISSING_CLASSIFICATION = "missing_pit_sector_classification"
REFUSAL_MISSING_LIFECYCLE = "missing_pit_security_lifecycle"
REFUSAL_MISSING_PRIOR = "missing_authenticated_prior_cycle"
REFUSAL_NOT_LISTED = "security_not_listed_at_execution"
REFUSAL_STALE_ADV = "adv_window_not_settlement_aligned"
REFUSAL_SUPERSEDED = "superseded_before_execution"
REFUSAL_UNAUDITED_FLOAT = "float_denominator_not_yet_audited"
REFUSAL_UNRESOLVED_ACTION_PREFIX = "unresolved_corporate_action:"


class PitReferenceError(ValueError):
    """A PIT reference contract or readiness boundary failed closed."""


def _refuse(detail: str) -> PitReferenceError:
    return PitReferenceError(f"REFUSED: {detail}")


def _reference_body_sha256(
    lifecycle_rows: Sequence[Mapping[str, Any]],
    classification_rows: Sequence[Mapping[str, Any]],
) -> str:
    canonical_lifecycles = sorted(
        (dict(row) for row in lifecycle_rows), key=hash_payload
    )
    canonical_classifications = sorted(
        (dict(row) for row in classification_rows), key=hash_payload
    )
    return hash_payload(
        {
            "classification_rows": canonical_classifications,
            "lifecycle_rows": canonical_lifecycles,
        }
    )


class ListingStatus(str, Enum):
    LISTED = "listed"
    DELISTED = "delisted"


class CorporateActionIssue(str, Enum):
    MERGER = "merger"
    SHARE_CLASS = "share_class"
    SPLIT = "split"
    TICKER_CHANGE = "ticker_change"


_READINESS_REFUSALS = frozenset(
    {
        REFUSAL_AMBIGUOUS_CLASSIFICATION,
        REFUSAL_AMBIGUOUS_LIFECYCLE,
        REFUSAL_IDENTITY_NOT_VALID,
        REFUSAL_MISSING_CLASSIFICATION,
        REFUSAL_MISSING_LIFECYCLE,
        REFUSAL_MISSING_PRIOR,
        REFUSAL_NOT_LISTED,
        REFUSAL_STALE_ADV,
        REFUSAL_SUPERSEDED,
        REFUSAL_UNAUDITED_FLOAT,
        *(
            f"{REFUSAL_UNRESOLVED_ACTION_PREFIX}{item.value}"
            for item in CorporateActionIssue
        ),
    }
)


@dataclasses.dataclass(frozen=True)
class PitReferenceManifest:
    reference_dataset_id: str
    source_id: str
    source_version: str
    semantic: str
    entitlement: SourceEntitlement
    retrieved_at: str
    lifecycle_record_count: int
    classification_record_count: int
    source_body_sha256: str
    collector_git_commit: str
    schema_version: str = REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("reference_dataset_id", "source_id", "source_version"):
            _required_text(getattr(self, name), name)
        if self.semantic != REFERENCE_SEMANTIC:
            raise _refuse(f"manifest semantic must be {REFERENCE_SEMANTIC!r}")
        if type(self.entitlement) is not SourceEntitlement:
            raise _refuse(
                "manifest entitlement must be the exact SourceEntitlement type"
            )
        parse_utc_timestamp(self.retrieved_at, "reference_manifest.retrieved_at")
        _integer(self.lifecycle_record_count, "lifecycle_record_count")
        _integer(self.classification_record_count, "classification_record_count")
        _sha256(self.source_body_sha256, "source_body_sha256")
        _git_commit(self.collector_git_commit, "collector_git_commit")
        if (
            type(self.schema_version) is not str
            or self.schema_version != REFERENCE_SCHEMA_VERSION
        ):
            raise _refuse(
                f"unsupported PIT reference schema_version {self.schema_version!r}"
            )

    def to_payload(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["entitlement"] = self.entitlement.value
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PitReferenceManifest":
        values = _payload_fields(cls, payload)
        values["entitlement"] = _enum(
            values.get("entitlement"), SourceEntitlement, "entitlement"
        )
        try:
            return cls(**values)
        except PitReferenceError:
            raise
        except (TypeError, ValueError) as exc:
            raise _refuse(f"invalid PIT reference manifest: {exc}") from exc

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


@dataclasses.dataclass(frozen=True)
class SecurityLifecycleObservation:
    security_id: str
    status: ListingStatus
    effective_date: str
    available_at: str
    observed_at: str
    unresolved_actions: tuple[CorporateActionIssue, ...]
    source_id: str
    source_version: str
    raw_record_sha256: str

    def __post_init__(self) -> None:
        _required_text(self.security_id, "lifecycle.security_id")
        if type(self.status) is not ListingStatus:
            raise _refuse("lifecycle status must be the exact ListingStatus type")
        _canonical_date(self.effective_date, "lifecycle.effective_date")
        available = parse_utc_timestamp(
            self.available_at, "lifecycle.available_at"
        )
        observed = parse_utc_timestamp(self.observed_at, "lifecycle.observed_at")
        if observed < available:
            raise _refuse("lifecycle.observed_at must not precede available_at")
        if type(self.unresolved_actions) is not tuple or not all(
            type(item) is CorporateActionIssue for item in self.unresolved_actions
        ):
            raise _refuse(
                "unresolved_actions must be an exact tuple of exact "
                "CorporateActionIssue values"
            )
        canonical_actions = tuple(
            sorted(set(self.unresolved_actions), key=lambda item: item.value)
        )
        if self.unresolved_actions != canonical_actions:
            raise _refuse("unresolved_actions must be unique and canonically ordered")
        for name in ("source_id", "source_version"):
            _required_text(getattr(self, name), f"lifecycle.{name}")
        _sha256(self.raw_record_sha256, "lifecycle.raw_record_sha256")

    def to_payload(self) -> dict[str, Any]:
        return {
            "available_at": self.available_at,
            "effective_date": self.effective_date,
            "observed_at": self.observed_at,
            "raw_record_sha256": self.raw_record_sha256,
            "security_id": self.security_id,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "status": self.status.value,
            "unresolved_actions": [item.value for item in self.unresolved_actions],
        }

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any]
    ) -> "SecurityLifecycleObservation":
        values = _payload_fields(cls, payload)
        values["status"] = _enum(values.get("status"), ListingStatus, "status")
        actions = values.get("unresolved_actions")
        if not isinstance(actions, list):
            raise _refuse("unresolved_actions must be a JSON array")
        values["unresolved_actions"] = tuple(
            _enum(item, CorporateActionIssue, "unresolved_actions")
            for item in actions
        )
        try:
            return cls(**values)
        except PitReferenceError:
            raise
        except (TypeError, ValueError) as exc:
            raise _refuse(f"invalid lifecycle observation: {exc}") from exc

    @property
    def record_id(self) -> str:
        return hash_payload(self.to_payload())


@dataclasses.dataclass(frozen=True)
class SectorClassificationObservation:
    security_id: str
    taxonomy_id: str
    sector_code: str
    industry_code: str
    valid_from: str
    valid_to: str | None
    available_at: str
    observed_at: str
    source_id: str
    source_version: str
    raw_record_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "security_id",
            "taxonomy_id",
            "sector_code",
            "industry_code",
            "source_id",
            "source_version",
        ):
            _required_text(getattr(self, name), f"classification.{name}")
        for name in ("taxonomy_id", "sector_code", "industry_code"):
            if getattr(self, name) != getattr(self, name).upper():
                raise _refuse(f"classification.{name} must be canonical uppercase")
        start = _canonical_date(self.valid_from, "classification.valid_from")
        if self.valid_to is not None:
            end = _canonical_date(self.valid_to, "classification.valid_to")
            if end < start:
                raise _refuse("classification.valid_to must not precede valid_from")
        available = parse_utc_timestamp(
            self.available_at, "classification.available_at"
        )
        observed = parse_utc_timestamp(
            self.observed_at, "classification.observed_at"
        )
        if observed < available:
            raise _refuse("classification.observed_at must not precede available_at")
        _sha256(self.raw_record_sha256, "classification.raw_record_sha256")

    def valid_on(self, session: str) -> bool:
        target = _canonical_date(session, "classification session")
        if target < _canonical_date(self.valid_from, "classification.valid_from"):
            return False
        return self.valid_to is None or target <= _canonical_date(
            self.valid_to, "classification.valid_to"
        )

    def to_payload(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any]
    ) -> "SectorClassificationObservation":
        try:
            return cls(**_payload_fields(cls, payload))
        except PitReferenceError:
            raise
        except (TypeError, ValueError) as exc:
            raise _refuse(f"invalid classification observation: {exc}") from exc

    @property
    def record_id(self) -> str:
        return hash_payload(self.to_payload())


@dataclasses.dataclass(frozen=True)
class PitReferenceBundle:
    manifest: PitReferenceManifest
    lifecycles: tuple[SecurityLifecycleObservation, ...]
    classifications: tuple[SectorClassificationObservation, ...]

    def __post_init__(self) -> None:
        if type(self.manifest) is not PitReferenceManifest:
            raise _refuse("manifest must be the exact PitReferenceManifest type")
        if type(self.lifecycles) is not tuple or not all(
            type(item) is SecurityLifecycleObservation for item in self.lifecycles
        ):
            raise _refuse(
                "lifecycles must be an exact tuple of exact "
                "SecurityLifecycleObservation values"
            )
        if type(self.classifications) is not tuple or not all(
            type(item) is SectorClassificationObservation
            for item in self.classifications
        ):
            raise _refuse(
                "classifications must be an exact tuple of exact "
                "SectorClassificationObservation values"
            )
        lifecycles = tuple(
            sorted(
                self.lifecycles,
                key=lambda item: (
                    item.security_id,
                    item.effective_date,
                    item.available_at,
                    item.record_id,
                ),
            )
        )
        classifications = tuple(
            sorted(
                self.classifications,
                key=lambda item: (
                    item.security_id,
                    item.valid_from,
                    item.available_at,
                    item.record_id,
                ),
            )
        )
        object.__setattr__(self, "lifecycles", lifecycles)
        object.__setattr__(self, "classifications", classifications)
        if self.manifest.lifecycle_record_count != len(lifecycles):
            raise _refuse("manifest lifecycle_record_count does not match records")
        if self.manifest.classification_record_count != len(classifications):
            raise _refuse(
                "manifest classification_record_count does not match records"
            )
        expected_source_hash = _reference_body_sha256(
            [item.to_payload() for item in lifecycles],
            [item.to_payload() for item in classifications],
        )
        if self.manifest.source_body_sha256 != expected_source_hash:
            raise _refuse("reference records do not match manifest source_body_sha256")
        retrieved = parse_utc_timestamp(
            self.manifest.retrieved_at, "reference_manifest.retrieved_at"
        )
        records: tuple[
            SecurityLifecycleObservation | SectorClassificationObservation, ...
        ] = (*lifecycles, *classifications)
        record_ids: set[str] = set()
        for record in records:
            if (
                parse_utc_timestamp(record.observed_at, "record.observed_at")
                > retrieved
            ):
                raise _refuse("reference record was observed after manifest retrieval")
            if record.record_id in record_ids:
                raise _refuse(
                    f"duplicate immutable reference record {record.record_id}"
                )
            record_ids.add(record.record_id)

    def to_payload(self) -> dict[str, Any]:
        return {
            "classifications": [item.to_payload() for item in self.classifications],
            "lifecycles": [item.to_payload() for item in self.lifecycles],
            "manifest": self.manifest.to_payload(),
        }

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


@dataclasses.dataclass(frozen=True)
class StockDataReadiness:
    source_dataset_id: str
    source_vintage_sha256: str
    reference_dataset_id: str
    reference_bundle_sha256: str
    event_id: str
    security_id: str
    settlement_date: str
    execution_session: str
    execution_at: str
    security_identity_sha256: str
    denominator_sha256: str
    volume_basis_sha256: str
    lifecycle_record_id: str | None
    classification_record_id: str | None
    taxonomy_id: str | None
    sector_code: str | None
    industry_code: str | None
    ready: bool
    refusal_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "source_dataset_id",
            "reference_dataset_id",
            "event_id",
            "security_id",
            "execution_session",
            "execution_at",
        ):
            _required_text(getattr(self, name), f"readiness.{name}")
        settlement = _canonical_date(
            self.settlement_date, "readiness.settlement_date"
        )
        execution_session = _canonical_date(
            self.execution_session, "readiness.execution_session"
        )
        if execution_session <= settlement:
            raise _refuse("readiness execution_session must follow settlement_date")
        parse_utc_timestamp(self.execution_at, "readiness.execution_at")
        try:
            expected_execution_at = format_utc_timestamp(
                session_open_instant(self.execution_session)
            )
        except ExchangeCalendarError as exc:
            raise _refuse(
                f"readiness execution_session is not tradable: {exc}"
            ) from exc
        if self.execution_at != expected_execution_at:
            raise _refuse("readiness execution_at must be the XNYS session open")
        for name in (
            "event_id",
            "reference_bundle_sha256",
            "source_vintage_sha256",
            "security_identity_sha256",
            "denominator_sha256",
            "volume_basis_sha256",
        ):
            _sha256(getattr(self, name), f"readiness.{name}")
        expected_source_dataset_id = (
            f"short-interest-vintage-{self.source_vintage_sha256[:16]}"
        )
        if self.source_dataset_id != expected_source_dataset_id:
            raise _refuse(
                "readiness source_dataset_id must match source_vintage_sha256"
            )
        for name in ("lifecycle_record_id", "classification_record_id"):
            value = getattr(self, name)
            if value is not None:
                _sha256(value, f"readiness.{name}")
        for name in ("taxonomy_id", "sector_code", "industry_code"):
            value = getattr(self, name)
            if value is not None:
                _required_text(value, f"readiness.{name}")
                if value != value.upper():
                    raise _refuse(f"readiness.{name} must be canonical uppercase")
        classification_values = (
            self.taxonomy_id,
            self.sector_code,
            self.industry_code,
        )
        if self.classification_record_id is None and any(
            value is not None for value in classification_values
        ):
            raise _refuse(
                "readiness classification values require a classification_record_id"
            )
        if self.classification_record_id is not None and any(
            value is None for value in classification_values
        ):
            raise _refuse(
                "readiness classification_record_id requires sector and industry"
            )
        if type(self.refusal_reasons) is not tuple or not all(
            type(item) is str and item and item == item.strip()
            for item in self.refusal_reasons
        ):
            raise _refuse(
                "readiness refusal_reasons must be an exact tuple of "
                "canonical strings"
            )
        if self.refusal_reasons != tuple(sorted(set(self.refusal_reasons))):
            raise _refuse("readiness refusal_reasons must be unique and sorted")
        unknown_reasons = set(self.refusal_reasons) - _READINESS_REFUSALS
        if unknown_reasons:
            raise _refuse(
                f"readiness has unknown refusal reasons {sorted(unknown_reasons)}"
            )
        reason_set = set(self.refusal_reasons)
        lifecycle_selection_errors = reason_set & {
            REFUSAL_AMBIGUOUS_LIFECYCLE,
            REFUSAL_MISSING_LIFECYCLE,
        }
        if self.lifecycle_record_id is None:
            if len(lifecycle_selection_errors) != 1:
                raise _refuse(
                    "missing lifecycle evidence requires one lifecycle "
                    "selection refusal"
                )
        elif lifecycle_selection_errors:
            raise _refuse(
                "lifecycle evidence conflicts with a lifecycle selection refusal"
            )
        classification_selection_errors = reason_set & {
            REFUSAL_AMBIGUOUS_CLASSIFICATION,
            REFUSAL_MISSING_CLASSIFICATION,
        }
        if self.classification_record_id is None:
            if len(classification_selection_errors) != 1:
                raise _refuse(
                    "missing classification evidence requires one "
                    "classification refusal"
                )
        elif classification_selection_errors:
            raise _refuse(
                "classification evidence conflicts with a classification refusal"
            )
        if len(reason_set & {REFUSAL_MISSING_PRIOR, REFUSAL_SUPERSEDED}) > 1:
            raise _refuse(
                "missing-prior and superseded dispositions are mutually exclusive"
            )
        if not isinstance(self.ready, bool) or self.ready != (not self.refusal_reasons):
            raise _refuse("readiness flag must equal absence of refusal reasons")
        if self.ready and (
            self.lifecycle_record_id is None
            or self.classification_record_id is None
        ):
            raise _refuse("ready data requires lifecycle and classification evidence")

    def to_payload(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["refusal_reasons"] = list(self.refusal_reasons)
        return payload

    @property
    def sha256(self) -> str:
        return hash_payload(self.to_payload())


def reference_fixture_body_sha256(
    lifecycle_rows: Sequence[Mapping[str, Any]],
    classification_rows: Sequence[Mapping[str, Any]],
) -> str:
    return _reference_body_sha256(lifecycle_rows, classification_rows)


def load_synthetic_pit_reference(path: str | Path) -> PitReferenceBundle:
    fixture_path = Path(path)
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        raise _refuse(
            f"PIT reference fixture is missing or invalid JSON: {exc}"
        ) from exc
    expected_fields = {
        "fixture_kind",
        "manifest",
        "lifecycle_rows",
        "classification_rows",
    }
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        actual = set(payload) if isinstance(payload, dict) else set()
        raise _refuse(
            "PIT reference fixture fields mismatch; "
            f"missing={sorted(expected_fields - actual)}, "
            f"unknown={sorted(actual - expected_fields)}"
        )
    if payload["fixture_kind"] != SYNTHETIC_REFERENCE_FIXTURE_KIND:
        raise _refuse("unknown PIT reference fixture kind")
    if not isinstance(payload["lifecycle_rows"], list) or not isinstance(
        payload["classification_rows"], list
    ):
        raise _refuse("PIT reference rows must be JSON arrays")
    manifest = PitReferenceManifest.from_payload(payload["manifest"])
    if manifest.entitlement is not SourceEntitlement.SYNTHETIC_FIXTURE_ONLY:
        raise _refuse("PIT fixture loader accepts synthetic_fixture_only entitlement")
    expected_hash = reference_fixture_body_sha256(
        payload["lifecycle_rows"], payload["classification_rows"]
    )
    if manifest.source_body_sha256 != expected_hash:
        raise _refuse("PIT reference body does not match source_body_sha256")
    return PitReferenceBundle(
        manifest=manifest,
        lifecycles=tuple(
            SecurityLifecycleObservation.from_payload(item)
            for item in payload["lifecycle_rows"]
        ),
        classifications=tuple(
            SectorClassificationObservation.from_payload(item)
            for item in payload["classification_rows"]
        ),
    )


def _select_lifecycle(
    bundle: PitReferenceBundle,
    security_id: str,
    execution_session: str,
    execution_at: datetime,
) -> tuple[SecurityLifecycleObservation | None, str | None]:
    candidates = [
        item
        for item in bundle.lifecycles
        if item.security_id == security_id
        and _canonical_date(item.effective_date, "lifecycle.effective_date")
        <= _canonical_date(execution_session, "execution_session")
        and parse_utc_timestamp(item.available_at, "lifecycle.available_at")
        <= execution_at
    ]
    if not candidates:
        return None, REFUSAL_MISSING_LIFECYCLE
    latest_date = max(item.effective_date for item in candidates)
    latest = [item for item in candidates if item.effective_date == latest_date]
    if len(latest) != 1:
        return None, REFUSAL_AMBIGUOUS_LIFECYCLE
    return latest[0], None


def _select_classification(
    bundle: PitReferenceBundle,
    security_id: str,
    execution_session: str,
    execution_at: datetime,
) -> tuple[SectorClassificationObservation | None, str | None]:
    candidates = [
        item
        for item in bundle.classifications
        if item.security_id == security_id
        and item.valid_on(execution_session)
        and parse_utc_timestamp(item.available_at, "classification.available_at")
        <= execution_at
    ]
    if not candidates:
        return None, REFUSAL_MISSING_CLASSIFICATION
    if len(candidates) != 1:
        return None, REFUSAL_AMBIGUOUS_CLASSIFICATION
    return candidates[0], None


def build_stock_data_readiness(
    vintage: ShortInterestVintage,
    references: PitReferenceBundle,
) -> tuple[StockDataReadiness, ...]:
    """Disposition every source snapshot without reading any market outcome."""
    if type(vintage) is not ShortInterestVintage:
        raise _refuse("vintage must be the exact ShortInterestVintage type")
    if type(references) is not PitReferenceBundle:
        raise _refuse("references must be the exact PitReferenceBundle type")
    source_identity = build_identity(vintage)
    source_dataset_id = source_identity["dataset_id"]
    reference_bundle_sha256 = references.sha256
    release_by_key = {item.key: item for item in vintage.release_calendar}
    availability_cache: dict[datetime, tuple[set[str], set[str]]] = {}
    results: list[StockDataReadiness] = []

    for snapshot in vintage.snapshots:
        cohort = snapshot_execution_cohort(
            snapshot, release_by_key[snapshot.release_calendar_key]
        )
        execution_at = parse_utc_timestamp(cohort.opens_at, "execution_at")
        reasons: list[str] = []
        cached_availability = availability_cache.get(execution_at)
        if cached_availability is None:
            visible_ids = {
                item.event_id
                for item in visible_source_snapshots_as_of(vintage, execution_at)
            }
            eligible_ids = {
                item.event_id
                for item in delta_eligible_snapshots_as_of(vintage, execution_at)
            }
            availability_cache[execution_at] = (visible_ids, eligible_ids)
        else:
            visible_ids, eligible_ids = cached_availability
        if snapshot.event_id not in visible_ids:
            reasons.append(REFUSAL_SUPERSEDED)
        elif snapshot.event_id not in eligible_ids:
            reasons.append(REFUSAL_MISSING_PRIOR)
        if not snapshot.security.valid_on(cohort.session):
            reasons.append(REFUSAL_IDENTITY_NOT_VALID)
        lifecycle, lifecycle_error = _select_lifecycle(
            references,
            snapshot.security.security_id,
            cohort.session,
            execution_at,
        )
        if lifecycle_error is not None:
            reasons.append(lifecycle_error)
        elif lifecycle is not None:
            if lifecycle.status is ListingStatus.DELISTED:
                reasons.append(REFUSAL_NOT_LISTED)
            reasons.extend(
                f"{REFUSAL_UNRESOLVED_ACTION_PREFIX}{item.value}"
                for item in lifecycle.unresolved_actions
            )

        classification, classification_error = _select_classification(
            references,
            snapshot.security.security_id,
            cohort.session,
            execution_at,
        )
        if classification_error is not None:
            reasons.append(classification_error)

        if snapshot.denominator.kind is DenominatorKind.POINT_IN_TIME_FLOAT:
            reasons.append(REFUSAL_UNAUDITED_FLOAT)
        if snapshot.volume_basis.window_end_date != snapshot.settlement_date:
            reasons.append(REFUSAL_STALE_ADV)

        results.append(
            StockDataReadiness(
                source_dataset_id=source_dataset_id,
                source_vintage_sha256=source_identity["content_hash"],
                reference_dataset_id=references.manifest.reference_dataset_id,
                reference_bundle_sha256=reference_bundle_sha256,
                event_id=snapshot.event_id,
                security_id=snapshot.security.security_id,
                settlement_date=snapshot.settlement_date,
                execution_session=cohort.session,
                execution_at=cohort.opens_at,
                security_identity_sha256=hash_payload(snapshot.security.to_payload()),
                denominator_sha256=hash_payload(snapshot.denominator.to_payload()),
                volume_basis_sha256=hash_payload(snapshot.volume_basis.to_payload()),
                lifecycle_record_id=(
                    lifecycle.record_id if lifecycle is not None else None
                ),
                classification_record_id=(
                    classification.record_id
                    if classification is not None
                    else None
                ),
                taxonomy_id=(
                    classification.taxonomy_id
                    if classification is not None
                    else None
                ),
                sector_code=(
                    classification.sector_code
                    if classification is not None
                    else None
                ),
                industry_code=(
                    classification.industry_code
                    if classification is not None
                    else None
                ),
                ready=not reasons,
                refusal_reasons=tuple(sorted(set(reasons))),
            )
        )

    return tuple(
        sorted(
            results,
            key=lambda item: (
                item.settlement_date,
                item.security_id,
                item.event_id,
            ),
        )
    )
