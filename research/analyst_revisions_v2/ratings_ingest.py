"""Massive/Benzinga structural ingest for Analyst Revisions V2.

This layer is deliberately outcome-free.  It authenticates a complete V2
snapshot, validates the documented provider row shape, records exactly one
accepted structural row or named refusal per source row, and derives stable
provider-version lineage.  Firm ordering is supplied only by a separately
reviewed ontology; the ingest never guesses that Buy, Outperform, Positive,
or any other label has a universal meaning.
"""
from __future__ import annotations

import dataclasses
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import Any, Mapping

from .canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    format_utc_timestamp,
    parse_date,
    parse_utc_timestamp,
    require_identifier,
    require_int,
    require_sha256,
    require_text,
    require_ticker,
    sha256_bytes,
)
from .evidence import SourceRowLocator
from .firm_ontology import (
    RatingMapping,
    RatingMappingRefusal,
    ReviewedFirmRatingOntology,
    revalidate_firm_rating_ontology,
    resolve_firm_rating,
)
from .snapshot import VerifiedSnapshot, VerifiedSourceRow, revalidate_verified_snapshot


BENZINGA_PROVIDER_CONTRACT_SCHEMA = "arv2-benzinga-rating-provider-contract-v1"
BENZINGA_PROVIDER_CONTRACT_ID = "massive-benzinga-analyst-ratings-v1"
BENZINGA_INGEST_AUDIT_SCHEMA = "arv2-benzinga-ingest-audit-v1"
BENZINGA_LINEAGE_SCHEMA = "arv2-benzinga-version-lineage-v1"
FIRM_NORMALIZATION_SCHEMA = "arv2-firm-rating-normalization-v1"
DAILY_DEDUPE_SCHEMA = "arv2-daily-rating-dedupe-v1"

_PROVIDER_FIELDS = frozenset(
    {
        "adjusted_price_target",
        "analyst",
        "benzinga_analyst_id",
        "benzinga_calendar_url",
        "benzinga_firm_id",
        "benzinga_id",
        "benzinga_news_url",
        "company_name",
        "currency",
        "date",
        "firm",
        "importance",
        "last_updated",
        "notes",
        "previous_adjusted_price_target",
        "previous_price_target",
        "previous_rating",
        "price_percent_change",
        "price_target",
        "price_target_action",
        "rating",
        "rating_action",
        "ticker",
        "time",
    }
)
_ROW_FIELDS = _PROVIDER_FIELDS | {"event_year"}
_NUMERIC_FIELDS = frozenset(
    {
        "adjusted_price_target",
        "previous_adjusted_price_target",
        "previous_price_target",
        "price_percent_change",
        "price_target",
    }
)
_TEXT_FIELDS = _PROVIDER_FIELDS - _NUMERIC_FIELDS - {"importance"}
_TIME_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d")


class RatingsIngestError(CanonicalEvidenceError):
    """The provider contract, ingest audit, or structural lineage is invalid."""


class RatingAction(str, Enum):
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    INITIATION = "initiation"
    RESUMPTION = "resumption"
    REITERATION = "reiteration"
    MAINTAIN = "maintain"
    TARGET_ONLY = "target_only"
    COVERAGE_TERMINATION = "coverage_termination"


_ACTION_MAP = {
    "upgrades": RatingAction.UPGRADE,
    "downgrades": RatingAction.DOWNGRADE,
    "initiates_coverage_on": RatingAction.INITIATION,
    "reinstates": RatingAction.RESUMPTION,
    "reiterates": RatingAction.REITERATION,
    "maintains": RatingAction.MAINTAIN,
    "terminates_coverage_on": RatingAction.COVERAGE_TERMINATION,
    "removes": RatingAction.COVERAGE_TERMINATION,
    "suspends": RatingAction.COVERAGE_TERMINATION,
    "firm_dissolved": RatingAction.COVERAGE_TERMINATION,
}
_UNSUPPORTED_DOCUMENTED_ACTIONS = frozenset({"assumes"})


def benzinga_provider_contract_record() -> dict[str, Any]:
    """Return the exact public provider/capture semantics pinned by ARV2-1."""
    return {
        "schema": BENZINGA_PROVIDER_CONTRACT_SCHEMA,
        "provider_contract_id": BENZINGA_PROVIDER_CONTRACT_ID,
        "endpoint": "/benzinga/v1/ratings",
        "documentation_urls": [
            "https://massive.com/docs/rest/partners/benzinga/analyst-ratings",
            "https://www.benzinga.com/apis/cloud-product/analyst-ratings-api/",
        ],
        "documentation_as_of": "2026-08-28",
        "snapshot_row_shape": "event_year_plus_documented_provider_fields",
        "provider_fields": sorted(_PROVIDER_FIELDS),
        "unknown_field_policy": "refuse_row",
        "rating_action_map": {
            raw_action: action.value for raw_action, action in sorted(_ACTION_MAP.items())
        },
        "unsupported_documented_actions": sorted(_UNSUPPORTED_DOCUMENTED_ACTIONS),
        "target_only_rule": "missing_rating_action_with_present_price_target_action",
        "clock_policy": "date_only_later_of_action_date_and_last_updated_date",
        "intraday_time_policy": "preserve_but_do_not_use_until_clock_semantics_reviewed",
        "pre_2013_policy": "provider_backfill_semantics_unverified_pre_2013",
        "correction_policy": "immutable_snapshot_comparison_by_benzinga_id_and_raw_hash",
        "deletion_policy": "missing_from_later_snapshot_is_not_a_withdrawal",
    }


BENZINGA_PROVIDER_CONTRACT_SHA256 = sha256_bytes(
    canonical_json_bytes(benzinga_provider_contract_record())
)


class RatingsIngestRefusalReason(str, Enum):
    PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013 = (
        "provider_backfill_semantics_unverified_pre_2013"
    )
    UNSUPPORTED_PROVIDER_SCHEMA = "unsupported_provider_schema"
    INVALID_PROVIDER_FIELD = "invalid_provider_field"
    MISSING_PROVIDER_EVENT_ID = "missing_provider_event_id"
    MISSING_PROVIDER_FIRM_ID = "missing_provider_firm_id"
    MISSING_FIRM_NAME = "missing_firm_name"
    INVALID_ACTION_DATE = "invalid_action_date"
    INVALID_LAST_UPDATED = "invalid_last_updated"
    LAST_UPDATED_BEFORE_ACTION = "last_updated_before_action"
    INVALID_TICKER = "invalid_ticker"
    MISSING_RATING_ACTION = "missing_rating_action"
    UNSUPPORTED_RATING_ACTION = "unsupported_rating_action"
    MISSING_CURRENT_RATING = "missing_current_rating"
    MISSING_PREVIOUS_RATING = "missing_previous_rating"
    INCONSISTENT_RATING_TRANSITION = "inconsistent_rating_transition"
    DUPLICATE_PROVIDER_EVENT_ID = "duplicate_provider_event_id"
    CONFLICTING_PROVIDER_EVENT_VERSION = "conflicting_provider_event_version"


class ProviderVersionChange(str, Enum):
    UNCHANGED = "unchanged"
    ADDED_IN_LATER_SNAPSHOT = "added_in_later_snapshot"
    CORRECTED_IN_LATER_SNAPSHOT = "corrected_in_later_snapshot"
    MISSING_FROM_LATER_SNAPSHOT = "missing_from_later_snapshot_not_withdrawal"


class TransitionRefusalReason(str, Enum):
    NO_ACTIVE_FIRM_SCALE = "no_active_firm_scale"
    UNREVIEWED_RATING_LABEL = "unreviewed_rating_label"
    ACTION_DIRECTION_MISMATCH = "action_direction_mismatch"
    NONCHANGE_ACTION_CHANGED_RATING = "nonchange_action_changed_rating"


class DailyDedupeRefusalReason(str, Enum):
    CONFLICTING_SAME_DAY_ECONOMIC_EVENTS = "conflicting_same_day_economic_events"


@dataclasses.dataclass(frozen=True)
class FirmRatingVocabularyEntry:
    """Non-ordered inventory row for later manual ontology adjudication."""

    provider_firm_id: str
    raw_firm_names: tuple[str, ...]
    raw_label: str
    first_seen: str
    last_seen: str
    current_count: int
    previous_count: int

    def __post_init__(self) -> None:
        require_identifier(self.provider_firm_id, "provider_firm_id")
        if not self.raw_firm_names or tuple(sorted(set(self.raw_firm_names))) != (
            self.raw_firm_names
        ):
            raise RatingsIngestError("raw firm names must be nonempty, unique, sorted")
        for name in self.raw_firm_names:
            require_text(name, "raw_firm_name")
        require_text(self.raw_label, "raw_label")
        first = parse_date(self.first_seen, "first_seen")
        last = parse_date(self.last_seen, "last_seen")
        if last < first:
            raise RatingsIngestError("vocabulary date range is reversed")
        require_int(self.current_count, "current_count", minimum=0)
        require_int(self.previous_count, "previous_count", minimum=0)
        if self.current_count + self.previous_count <= 0:
            raise RatingsIngestError("vocabulary entry must represent an observation")


class _RowRefusal(Exception):
    def __init__(self, reason: RatingsIngestRefusalReason):
        super().__init__(reason.value)
        self.reason = reason


def _provider_version_id(locator: SourceRowLocator) -> str:
    return f"bzv_{locator.raw_row_sha256}"


def _optional_text(
    record: Mapping[str, Any], key: str, *, maximum_length: int = 2048
) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    try:
        return require_text(value, key, maximum_length=maximum_length)
    except CanonicalEvidenceError as exc:
        raise _RowRefusal(RatingsIngestRefusalReason.INVALID_PROVIDER_FIELD) from exc


def _required_identifier(
    record: Mapping[str, Any], key: str, reason: RatingsIngestRefusalReason
) -> str:
    value = record.get(key)
    try:
        return require_identifier(value, key)
    except CanonicalEvidenceError as exc:
        raise _RowRefusal(reason) from exc


def _parse_provider_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _RowRefusal(RatingsIngestRefusalReason.INVALID_LAST_UPDATED)
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise _RowRefusal(RatingsIngestRefusalReason.INVALID_LAST_UPDATED) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _RowRefusal(RatingsIngestRefusalReason.INVALID_LAST_UPDATED)
    return format_utc_timestamp(parsed.astimezone(timezone.utc))


def _validate_optional_provider_fields(record: Mapping[str, Any]) -> None:
    for key in _TEXT_FIELDS:
        maximum = 8192 if key == "notes" else 2048
        _optional_text(record, key, maximum_length=maximum)
    for key in _NUMERIC_FIELDS:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            raise _RowRefusal(RatingsIngestRefusalReason.INVALID_PROVIDER_FIELD)
        if not Decimal(value).is_finite():
            raise _RowRefusal(RatingsIngestRefusalReason.INVALID_PROVIDER_FIELD)
    importance = record.get("importance")
    if importance is not None:
        try:
            require_int(importance, "importance", minimum=0, maximum=5)
        except CanonicalEvidenceError as exc:
            raise _RowRefusal(
                RatingsIngestRefusalReason.INVALID_PROVIDER_FIELD
            ) from exc
    raw_time = record.get("time")
    if raw_time is not None and (
        not isinstance(raw_time, str) or _TIME_RE.fullmatch(raw_time) is None
    ):
        raise _RowRefusal(RatingsIngestRefusalReason.INVALID_PROVIDER_FIELD)


@dataclasses.dataclass(frozen=True)
class BenzingaRatingRecord:
    source_locator: SourceRowLocator
    provider_event_id: str
    provider_version_id: str
    provider_firm_id: str
    provider_analyst_id: str | None
    raw_firm_name: str
    raw_analyst_name: str | None
    action: RatingAction
    action_date: str
    raw_event_time: str | None
    last_updated_at: str
    conservative_public_date: str
    historical_ticker: str
    current_rating: str | None
    previous_rating: str | None
    price_target_action: str | None

    def __post_init__(self) -> None:
        if type(self.source_locator) is not SourceRowLocator:
            raise RatingsIngestError("source_locator must be a SourceRowLocator")
        require_identifier(self.provider_event_id, "provider_event_id")
        if self.provider_version_id != _provider_version_id(self.source_locator):
            raise RatingsIngestError("provider_version_id is not bound to raw bytes")
        require_identifier(self.provider_firm_id, "provider_firm_id")
        if self.provider_analyst_id is not None:
            require_identifier(self.provider_analyst_id, "provider_analyst_id")
        require_text(self.raw_firm_name, "raw_firm_name")
        if self.raw_analyst_name is not None:
            require_text(self.raw_analyst_name, "raw_analyst_name")
        if not isinstance(self.action, RatingAction):
            raise RatingsIngestError("action must be a RatingAction")
        action_date = parse_date(self.action_date, "action_date")
        updated = parse_utc_timestamp(self.last_updated_at, "last_updated_at")
        public_date = parse_date(
            self.conservative_public_date, "conservative_public_date"
        )
        if public_date != max(action_date, updated.date()):
            raise RatingsIngestError("conservative public date is not source-derived")
        if updated.date() < action_date:
            raise RatingsIngestError("last_updated_at precedes action_date")
        require_ticker(self.historical_ticker)
        for name in ("current_rating", "previous_rating", "price_target_action"):
            value = getattr(self, name)
            if value is not None:
                require_text(value, name)
        if self.raw_event_time is not None and _TIME_RE.fullmatch(
            self.raw_event_time
        ) is None:
            raise RatingsIngestError("raw_event_time is not HH:MM:SS")
        current_required = self.action in {
            RatingAction.UPGRADE,
            RatingAction.DOWNGRADE,
            RatingAction.INITIATION,
            RatingAction.RESUMPTION,
            RatingAction.REITERATION,
            RatingAction.MAINTAIN,
        }
        if current_required and self.current_rating is None:
            raise RatingsIngestError("rating action requires current_rating")
        if self.action in {RatingAction.UPGRADE, RatingAction.DOWNGRADE}:
            if self.previous_rating is None:
                raise RatingsIngestError("directional action requires previous_rating")
            if self.current_rating.casefold() == self.previous_rating.casefold():
                raise RatingsIngestError("directional action is a raw self-transition")

    def to_record(self) -> dict[str, Any]:
        return {
            "source_locator": self.source_locator.to_record(),
            "provider_event_id": self.provider_event_id,
            "provider_version_id": self.provider_version_id,
            "provider_firm_id": self.provider_firm_id,
            "provider_analyst_id": self.provider_analyst_id,
            "raw_firm_name": self.raw_firm_name,
            "raw_analyst_name": self.raw_analyst_name,
            "action": self.action.value,
            "action_date": self.action_date,
            "raw_event_time": self.raw_event_time,
            "last_updated_at": self.last_updated_at,
            "conservative_public_date": self.conservative_public_date,
            "historical_ticker": self.historical_ticker,
            "current_rating": self.current_rating,
            "previous_rating": self.previous_rating,
            "price_target_action": self.price_target_action,
        }


def _parse_source_row(source_row: VerifiedSourceRow) -> BenzingaRatingRecord:
    record = source_row.parsed_record()
    if source_row.locator.partition_year < 2013:
        raise _RowRefusal(
            RatingsIngestRefusalReason.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
        )
    if not set(record).issubset(_ROW_FIELDS) or "event_year" not in record:
        raise _RowRefusal(RatingsIngestRefusalReason.UNSUPPORTED_PROVIDER_SCHEMA)
    _validate_optional_provider_fields(record)
    event_id = _required_identifier(
        record,
        "benzinga_id",
        RatingsIngestRefusalReason.MISSING_PROVIDER_EVENT_ID,
    )
    firm_id = _required_identifier(
        record,
        "benzinga_firm_id",
        RatingsIngestRefusalReason.MISSING_PROVIDER_FIRM_ID,
    )
    # The canonical record enforces a 256-character bound on these text
    # fields, so the per-row screen must use the same bound: a wider
    # screen let an over-long provider value escape the _RowRefusal
    # handler during record construction and halt the whole census.
    firm_name = _optional_text(record, "firm", maximum_length=256)
    if firm_name is None:
        raise _RowRefusal(RatingsIngestRefusalReason.MISSING_FIRM_NAME)
    analyst_id = _optional_text(record, "benzinga_analyst_id")
    if analyst_id is not None:
        try:
            require_identifier(analyst_id, "benzinga_analyst_id")
        except CanonicalEvidenceError as exc:
            raise _RowRefusal(
                RatingsIngestRefusalReason.INVALID_PROVIDER_FIELD
            ) from exc

    raw_date = record.get("date")
    try:
        action_date = parse_date(raw_date, "date")
    except CanonicalEvidenceError as exc:
        raise _RowRefusal(RatingsIngestRefusalReason.INVALID_ACTION_DATE) from exc
    if action_date.year != source_row.locator.partition_year:
        raise _RowRefusal(RatingsIngestRefusalReason.INVALID_ACTION_DATE)
    updated_text = _parse_provider_timestamp(record.get("last_updated"))
    updated = parse_utc_timestamp(updated_text, "last_updated_at")
    if updated.date() < action_date:
        raise _RowRefusal(RatingsIngestRefusalReason.LAST_UPDATED_BEFORE_ACTION)
    try:
        ticker = require_ticker(record.get("ticker"), "ticker")
    except CanonicalEvidenceError as exc:
        raise _RowRefusal(RatingsIngestRefusalReason.INVALID_TICKER) from exc

    raw_action = _optional_text(record, "rating_action")
    price_target_action = _optional_text(
        record, "price_target_action", maximum_length=256
    )
    if raw_action is None:
        if price_target_action is None:
            raise _RowRefusal(RatingsIngestRefusalReason.MISSING_RATING_ACTION)
        action = RatingAction.TARGET_ONLY
    else:
        if raw_action in _UNSUPPORTED_DOCUMENTED_ACTIONS:
            raise _RowRefusal(RatingsIngestRefusalReason.UNSUPPORTED_RATING_ACTION)
        try:
            action = _ACTION_MAP[raw_action]
        except KeyError as exc:
            raise _RowRefusal(
                RatingsIngestRefusalReason.UNSUPPORTED_RATING_ACTION
            ) from exc

    current = _optional_text(record, "rating", maximum_length=256)
    previous = _optional_text(record, "previous_rating", maximum_length=256)
    if action in {
        RatingAction.UPGRADE,
        RatingAction.DOWNGRADE,
        RatingAction.INITIATION,
        RatingAction.RESUMPTION,
        RatingAction.REITERATION,
        RatingAction.MAINTAIN,
    } and current is None:
        raise _RowRefusal(RatingsIngestRefusalReason.MISSING_CURRENT_RATING)
    if action in (RatingAction.UPGRADE, RatingAction.DOWNGRADE):
        if previous is None:
            raise _RowRefusal(RatingsIngestRefusalReason.MISSING_PREVIOUS_RATING)
        if current is not None and current.casefold() == previous.casefold():
            raise _RowRefusal(
                RatingsIngestRefusalReason.INCONSISTENT_RATING_TRANSITION
            )

    return BenzingaRatingRecord(
        source_locator=source_row.locator,
        provider_event_id=event_id,
        provider_version_id=_provider_version_id(source_row.locator),
        provider_firm_id=firm_id,
        provider_analyst_id=analyst_id,
        raw_firm_name=firm_name,
        raw_analyst_name=_optional_text(record, "analyst", maximum_length=256),
        action=action,
        action_date=action_date.isoformat(),
        raw_event_time=_optional_text(record, "time"),
        last_updated_at=updated_text,
        conservative_public_date=max(action_date, updated.date()).isoformat(),
        historical_ticker=ticker,
        current_rating=current,
        previous_rating=previous,
        price_target_action=price_target_action,
    )


def _candidate_event_id(source_row: VerifiedSourceRow) -> str | None:
    value = source_row.parsed_record().get("benzinga_id")
    try:
        return require_identifier(value, "benzinga_id")
    except CanonicalEvidenceError:
        return None


def _refusal_evidence_sha256(
    locator: SourceRowLocator,
    reason: RatingsIngestRefusalReason,
    provider_event_id: str | None,
) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": "arv2-benzinga-ingest-refusal-evidence-v1",
                "source_locator": locator.to_record(),
                "reason": reason.value,
                "provider_event_id": provider_event_id,
                "provider_version_id": _provider_version_id(locator),
            }
        )
    )


@dataclasses.dataclass(frozen=True)
class RatingsIngestRefusal:
    source_locator: SourceRowLocator
    provider_event_id: str | None
    provider_version_id: str
    reason: RatingsIngestRefusalReason
    evidence_sha256: str

    @classmethod
    def create(
        cls,
        *,
        source_locator: SourceRowLocator,
        provider_event_id: str | None,
        reason: RatingsIngestRefusalReason,
    ) -> "RatingsIngestRefusal":
        return cls(
            source_locator=source_locator,
            provider_event_id=provider_event_id,
            provider_version_id=_provider_version_id(source_locator),
            reason=reason,
            evidence_sha256=_refusal_evidence_sha256(
                source_locator, reason, provider_event_id
            ),
        )

    def __post_init__(self) -> None:
        if type(self.source_locator) is not SourceRowLocator:
            raise RatingsIngestError("refusal locator must be a SourceRowLocator")
        if self.provider_event_id is not None:
            require_identifier(self.provider_event_id, "provider_event_id")
        if self.provider_version_id != _provider_version_id(self.source_locator):
            raise RatingsIngestError("refusal version is not bound to raw bytes")
        if not isinstance(self.reason, RatingsIngestRefusalReason):
            raise RatingsIngestError("refusal reason has the wrong type")
        expected = _refusal_evidence_sha256(
            self.source_locator, self.reason, self.provider_event_id
        )
        if self.evidence_sha256 != expected:
            raise RatingsIngestError("refusal evidence is not source-bound")


@dataclasses.dataclass(frozen=True)
class BenzingaIngestAudit:
    schema: str
    snapshot: VerifiedSnapshot
    records: tuple[BenzingaRatingRecord, ...]
    refusals: tuple[RatingsIngestRefusal, ...]

    def __post_init__(self) -> None:
        if self.schema != BENZINGA_INGEST_AUDIT_SCHEMA:
            raise RatingsIngestError("unsupported Benzinga ingest audit schema")
        revalidate_verified_snapshot(self.snapshot)
        if self.snapshot.provider_contract_id != BENZINGA_PROVIDER_CONTRACT_ID:
            raise RatingsIngestError("snapshot uses the wrong provider contract ID")
        if (
            self.snapshot.provider_contract_sha256
            != BENZINGA_PROVIDER_CONTRACT_SHA256
        ):
            raise RatingsIngestError("snapshot uses the wrong provider contract hash")
        if type(self.records) is not tuple or any(
            type(record) is not BenzingaRatingRecord for record in self.records
        ):
            raise RatingsIngestError("records must be a tuple of exact ingest records")
        if type(self.refusals) is not tuple or any(
            type(refusal) is not RatingsIngestRefusal for refusal in self.refusals
        ):
            raise RatingsIngestError("refusals must be a tuple of exact refusals")
        record_locators = tuple(record.source_locator for record in self.records)
        refusal_locators = tuple(refusal.source_locator for refusal in self.refusals)
        for locators, name in (
            (record_locators, "records"),
            (refusal_locators, "refusals"),
        ):
            if locators != tuple(sorted(locators, key=lambda item: item.sort_key)):
                raise RatingsIngestError(f"{name} are not canonical source-sorted")
        terminal = record_locators + refusal_locators
        expected = self.snapshot.source_locators
        if len(terminal) != len(set(terminal)) or set(terminal) != set(expected):
            raise RatingsIngestError(
                "ingest must have exactly one terminal disposition per source row"
            )
        event_ids = [record.provider_event_id for record in self.records]
        event_ids.extend(
            refusal.provider_event_id
            for refusal in self.refusals
            if refusal.provider_event_id is not None
        )
        counts = Counter(event_ids)
        duplicated = {event_id for event_id, count in counts.items() if count > 1}
        for record in self.records:
            if record.provider_event_id in duplicated:
                raise RatingsIngestError("duplicate provider ID was accepted")
        for refusal in self.refusals:
            if refusal.provider_event_id in duplicated and refusal.reason not in {
                RatingsIngestRefusalReason.DUPLICATE_PROVIDER_EVENT_ID,
                RatingsIngestRefusalReason.CONFLICTING_PROVIDER_EVENT_VERSION,
                RatingsIngestRefusalReason.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013,
            }:
                raise RatingsIngestError(
                    "every duplicate provider ID occurrence needs a duplicate refusal"
                )

    @property
    def audit_sha256(self) -> str:
        return sha256_bytes(
            canonical_json_bytes(
                {
                    "schema": self.schema,
                    "snapshot_id": self.snapshot.snapshot_id,
                    "snapshot_manifest_sha256": self.snapshot.manifest_sha256,
                    "provider_contract_sha256": (
                        self.snapshot.provider_contract_sha256
                    ),
                    "records": [record.to_record() for record in self.records],
                    "refusals": [
                        {
                            "source_locator": refusal.source_locator.to_record(),
                            "provider_event_id": refusal.provider_event_id,
                            "provider_version_id": refusal.provider_version_id,
                            "reason": refusal.reason.value,
                            "evidence_sha256": refusal.evidence_sha256,
                        }
                        for refusal in self.refusals
                    ],
                }
            )
        )


def audit_benzinga_snapshot(snapshot: VerifiedSnapshot) -> BenzingaIngestAudit:
    """Produce an exhaustive structural audit without accessing outcomes."""
    if type(snapshot) is not VerifiedSnapshot:
        raise RatingsIngestError("Benzinga ingest requires a VerifiedSnapshot")
    revalidate_verified_snapshot(snapshot)
    if snapshot.provider_contract_id != BENZINGA_PROVIDER_CONTRACT_ID:
        raise RatingsIngestError("snapshot uses the wrong provider contract ID")
    if snapshot.provider_contract_sha256 != BENZINGA_PROVIDER_CONTRACT_SHA256:
        raise RatingsIngestError("snapshot uses the wrong provider contract hash")

    parsed: dict[SourceRowLocator, BenzingaRatingRecord] = {}
    refused: dict[SourceRowLocator, RatingsIngestRefusal] = {}
    candidate_ids: dict[SourceRowLocator, str | None] = {}
    for source_row in snapshot.rows:
        candidate_id = _candidate_event_id(source_row)
        candidate_ids[source_row.locator] = candidate_id
        try:
            parsed[source_row.locator] = _parse_source_row(source_row)
        except _RowRefusal as exc:
            refused[source_row.locator] = RatingsIngestRefusal.create(
                source_locator=source_row.locator,
                provider_event_id=candidate_id,
                reason=exc.reason,
            )

    locators_by_event: dict[str, list[SourceRowLocator]] = defaultdict(list)
    for locator, event_id in candidate_ids.items():
        if event_id is not None:
            locators_by_event[event_id].append(locator)
    for event_id, locators in locators_by_event.items():
        if len(locators) <= 1:
            continue
        versions = {_provider_version_id(locator) for locator in locators}
        reason = (
            RatingsIngestRefusalReason.DUPLICATE_PROVIDER_EVENT_ID
            if len(versions) == 1
            else RatingsIngestRefusalReason.CONFLICTING_PROVIDER_EVENT_VERSION
        )
        for locator in locators:
            existing = refused.get(locator)
            if existing is not None and existing.reason is (
                RatingsIngestRefusalReason.PROVIDER_BACKFILL_SEMANTICS_UNVERIFIED_PRE_2013
            ):
                continue
            parsed.pop(locator, None)
            refused[locator] = RatingsIngestRefusal.create(
                source_locator=locator,
                provider_event_id=event_id,
                reason=reason,
            )

    return BenzingaIngestAudit(
        schema=BENZINGA_INGEST_AUDIT_SCHEMA,
        snapshot=snapshot,
        records=tuple(
            parsed[locator]
            for locator in sorted(parsed, key=lambda item: item.sort_key)
        ),
        refusals=tuple(
            refused[locator]
            for locator in sorted(refused, key=lambda item: item.sort_key)
        ),
    )


def revalidate_benzinga_ingest_audit(
    audit: BenzingaIngestAudit,
) -> BenzingaIngestAudit:
    if type(audit) is not BenzingaIngestAudit:
        raise RatingsIngestError("ingest authority requires a BenzingaIngestAudit")
    rebuilt = audit_benzinga_snapshot(audit.snapshot)
    if rebuilt != audit:
        raise RatingsIngestError("Benzinga ingest audit is not source-derived")
    return audit


def build_firm_rating_vocabulary(
    audit: BenzingaIngestAudit,
) -> tuple[FirmRatingVocabularyEntry, ...]:
    """Inventory observed labels without assigning ranks or merging firm IDs."""
    revalidate_benzinga_ingest_audit(audit)
    observations: dict[tuple[str, str], dict[str, object]] = {}
    for record in audit.records:
        for position, label in (
            ("current", record.current_rating),
            ("previous", record.previous_rating),
        ):
            if label is None:
                continue
            key = (record.provider_firm_id, label)
            state = observations.setdefault(
                key,
                {
                    "firm_names": set(),
                    "dates": [],
                    "current": 0,
                    "previous": 0,
                },
            )
            names = state["firm_names"]
            dates = state["dates"]
            if not isinstance(names, set) or not isinstance(dates, list):
                raise AssertionError("vocabulary accumulator changed type")
            names.add(record.raw_firm_name)
            dates.append(record.action_date)
            state[position] = int(state[position]) + 1
    return tuple(
        FirmRatingVocabularyEntry(
            provider_firm_id=firm_id,
            raw_firm_names=tuple(sorted(state["firm_names"])),
            raw_label=label,
            first_seen=min(state["dates"]),
            last_seen=max(state["dates"]),
            current_count=int(state["current"]),
            previous_count=int(state["previous"]),
        )
        for (firm_id, label), state in sorted(
            observations.items(),
            key=lambda item: (item[0][0], item[0][1].casefold(), item[0][1]),
        )
    )


@dataclasses.dataclass(frozen=True)
class ProviderVersionLineageEntry:
    provider_event_id: str
    older_version_id: str | None
    newer_version_id: str | None
    change: ProviderVersionChange

    def __post_init__(self) -> None:
        require_identifier(self.provider_event_id, "provider_event_id")
        for name in ("older_version_id", "newer_version_id"):
            value = getattr(self, name)
            if value is not None:
                require_identifier(value, name)
        if not isinstance(self.change, ProviderVersionChange):
            raise RatingsIngestError("lineage change has the wrong type")
        expected_presence = {
            ProviderVersionChange.UNCHANGED: (True, True),
            ProviderVersionChange.ADDED_IN_LATER_SNAPSHOT: (False, True),
            ProviderVersionChange.CORRECTED_IN_LATER_SNAPSHOT: (True, True),
            ProviderVersionChange.MISSING_FROM_LATER_SNAPSHOT: (True, False),
        }[self.change]
        if (
            self.older_version_id is not None,
            self.newer_version_id is not None,
        ) != expected_presence:
            raise RatingsIngestError("lineage versions disagree with change kind")
        if self.change is ProviderVersionChange.UNCHANGED and (
            self.older_version_id != self.newer_version_id
        ):
            raise RatingsIngestError("unchanged lineage has different versions")
        if self.change is ProviderVersionChange.CORRECTED_IN_LATER_SNAPSHOT and (
            self.older_version_id == self.newer_version_id
        ):
            raise RatingsIngestError("corrected lineage has identical versions")


@dataclasses.dataclass(frozen=True)
class BenzingaVersionLineage:
    schema: str
    older_snapshot_id: str
    older_snapshot_sha256: str
    newer_snapshot_id: str
    newer_snapshot_sha256: str
    entries: tuple[ProviderVersionLineageEntry, ...]

    def __post_init__(self) -> None:
        if self.schema != BENZINGA_LINEAGE_SCHEMA:
            raise RatingsIngestError("unsupported Benzinga lineage schema")
        require_identifier(self.older_snapshot_id, "older_snapshot_id")
        require_sha256(self.older_snapshot_sha256, "older_snapshot_sha256")
        require_identifier(self.newer_snapshot_id, "newer_snapshot_id")
        require_sha256(self.newer_snapshot_sha256, "newer_snapshot_sha256")
        if self.older_snapshot_id == self.newer_snapshot_id:
            raise RatingsIngestError("lineage snapshot IDs must be distinct")
        if type(self.entries) is not tuple or any(
            type(entry) is not ProviderVersionLineageEntry for entry in self.entries
        ):
            raise RatingsIngestError("lineage entries must be an exact tuple")
        ids = tuple(entry.provider_event_id for entry in self.entries)
        if ids != tuple(sorted(set(ids))):
            raise RatingsIngestError("lineage event IDs must be unique and sorted")

    @property
    def lineage_sha256(self) -> str:
        return sha256_bytes(
            canonical_json_bytes(
                {
                    "schema": self.schema,
                    "older_snapshot_id": self.older_snapshot_id,
                    "older_snapshot_sha256": self.older_snapshot_sha256,
                    "newer_snapshot_id": self.newer_snapshot_id,
                    "newer_snapshot_sha256": self.newer_snapshot_sha256,
                    "entries": [
                        {
                            "provider_event_id": entry.provider_event_id,
                            "older_version_id": entry.older_version_id,
                            "newer_version_id": entry.newer_version_id,
                            "change": entry.change.value,
                        }
                        for entry in self.entries
                    ],
                }
            )
        )


def _version_index(audit: BenzingaIngestAudit) -> dict[str, str]:
    pairs: list[tuple[str, str]] = [
        (record.provider_event_id, record.provider_version_id)
        for record in audit.records
    ]
    pairs.extend(
        (refusal.provider_event_id, refusal.provider_version_id)
        for refusal in audit.refusals
        if refusal.provider_event_id is not None
    )
    counts = Counter(event_id for event_id, _ in pairs)
    if any(count > 1 for count in counts.values()):
        raise RatingsIngestError(
            "version lineage cannot compare a snapshot with duplicate provider IDs"
        )
    return dict(pairs)


def compare_benzinga_snapshot_lineage(
    older: BenzingaIngestAudit,
    newer: BenzingaIngestAudit,
) -> BenzingaVersionLineage:
    """Compare complete, chronologically bound snapshots without inventing deletes."""
    revalidate_benzinga_ingest_audit(older)
    revalidate_benzinga_ingest_audit(newer)
    if older.snapshot.snapshot_id == newer.snapshot.snapshot_id:
        raise RatingsIngestError("lineage snapshots must be distinct")
    if (
        older.snapshot.requested_first_year,
        older.snapshot.requested_last_year,
    ) != (
        newer.snapshot.requested_first_year,
        newer.snapshot.requested_last_year,
    ):
        raise RatingsIngestError("lineage snapshots must have identical year bounds")
    if parse_utc_timestamp(
        older.snapshot.captured_at, "older.captured_at"
    ) >= parse_utc_timestamp(newer.snapshot.captured_at, "newer.captured_at"):
        raise RatingsIngestError("lineage snapshots are not chronologically ordered")
    older_index = _version_index(older)
    newer_index = _version_index(newer)
    entries: list[ProviderVersionLineageEntry] = []
    for event_id in sorted(set(older_index) | set(newer_index)):
        old_version = older_index.get(event_id)
        new_version = newer_index.get(event_id)
        if old_version is None:
            change = ProviderVersionChange.ADDED_IN_LATER_SNAPSHOT
        elif new_version is None:
            change = ProviderVersionChange.MISSING_FROM_LATER_SNAPSHOT
        elif old_version == new_version:
            change = ProviderVersionChange.UNCHANGED
        else:
            change = ProviderVersionChange.CORRECTED_IN_LATER_SNAPSHOT
        entries.append(
            ProviderVersionLineageEntry(
                provider_event_id=event_id,
                older_version_id=old_version,
                newer_version_id=new_version,
                change=change,
            )
        )
    return BenzingaVersionLineage(
        schema=BENZINGA_LINEAGE_SCHEMA,
        older_snapshot_id=older.snapshot.snapshot_id,
        older_snapshot_sha256=older.snapshot.manifest_sha256,
        newer_snapshot_id=newer.snapshot.snapshot_id,
        newer_snapshot_sha256=newer.snapshot.manifest_sha256,
        entries=tuple(entries),
    )


@dataclasses.dataclass(frozen=True)
class FirmNormalizedRatingEvent:
    source_event: BenzingaRatingRecord
    ontology_id: str
    ontology_sha256: str
    current_mapping: RatingMapping | None
    previous_mapping: RatingMapping | None
    rating_change: Fraction | None

    def __post_init__(self) -> None:
        if type(self.source_event) is not BenzingaRatingRecord:
            raise RatingsIngestError("normalized event source has the wrong type")
        require_identifier(self.ontology_id, "ontology_id")
        require_sha256(self.ontology_sha256, "ontology_sha256")
        for name in ("current_mapping", "previous_mapping"):
            mapping = getattr(self, name)
            if mapping is not None and (
                type(mapping) is not RatingMapping
                or mapping.ontology_id != self.ontology_id
                or mapping.ontology_sha256 != self.ontology_sha256
            ):
                raise RatingsIngestError(
                    f"{name} is not bound to the normalized event ontology"
                )
        for mapping, raw_label, name in (
            (self.current_mapping, self.source_event.current_rating, "current_mapping"),
            (
                self.previous_mapping,
                self.source_event.previous_rating,
                "previous_mapping",
            ),
        ):
            if mapping is not None and (
                raw_label is None
                or mapping.entry.provider_firm_id
                != self.source_event.provider_firm_id
                or mapping.entry.raw_label != raw_label
            ):
                raise RatingsIngestError(f"{name} is not source-label-bound")
        if self.rating_change is not None:
            if type(self.rating_change) is not Fraction:
                raise RatingsIngestError("rating_change must be an exact Fraction")
            if self.current_mapping is None or self.previous_mapping is None:
                raise RatingsIngestError("rating change requires both firm mappings")
            expected = self.current_mapping.score - self.previous_mapping.score
            if self.rating_change != expected or self.rating_change == 0:
                raise RatingsIngestError("rating_change is not mapping-derived")
            if self.source_event.action not in {
                RatingAction.UPGRADE,
                RatingAction.DOWNGRADE,
            }:
                raise RatingsIngestError("only directional actions may carry a change")
        elif self.source_event.action in {
            RatingAction.UPGRADE,
            RatingAction.DOWNGRADE,
        }:
            raise RatingsIngestError("directional action is missing rating_change")

    @property
    def contributes_rating_revision(self) -> bool:
        return self.rating_change is not None


@dataclasses.dataclass(frozen=True)
class FirmNormalizationRefusal:
    source_event: BenzingaRatingRecord
    reason: TransitionRefusalReason

    def __post_init__(self) -> None:
        if type(self.source_event) is not BenzingaRatingRecord:
            raise RatingsIngestError("normalization refusal source has the wrong type")
        if not isinstance(self.reason, TransitionRefusalReason):
            raise RatingsIngestError("normalization refusal reason has the wrong type")


@dataclasses.dataclass(frozen=True)
class FirmRatingNormalizationResult:
    schema: str
    source_audit_sha256: str
    ontology_id: str
    ontology_sha256: str
    events: tuple[FirmNormalizedRatingEvent, ...]
    refusals: tuple[FirmNormalizationRefusal, ...]
    # Optional so existing callers are unchanged; when supplied it makes this
    # result exhaustive over its source audit the way its sibling result types
    # already are, instead of only format-checking source_audit_sha256.
    source_census: int | None = None

    def __post_init__(self) -> None:
        if self.schema != FIRM_NORMALIZATION_SCHEMA:
            raise RatingsIngestError("unsupported firm normalization schema")
        require_sha256(self.source_audit_sha256, "source_audit_sha256")
        require_identifier(self.ontology_id, "ontology_id")
        require_sha256(self.ontology_sha256, "ontology_sha256")
        if type(self.events) is not tuple or any(
            type(event) is not FirmNormalizedRatingEvent for event in self.events
        ):
            raise RatingsIngestError("normalized events must be an exact tuple")
        if type(self.refusals) is not tuple or any(
            type(refusal) is not FirmNormalizationRefusal
            for refusal in self.refusals
        ):
            raise RatingsIngestError("normalization refusals must be an exact tuple")
        ids = [event.source_event.provider_event_id for event in self.events]
        ids.extend(
            refusal.source_event.provider_event_id for refusal in self.refusals
        )
        if len(ids) != len(set(ids)):
            raise RatingsIngestError(
                "firm normalization has more than one disposition per event"
            )
        if self.source_census is not None:
            require_int(self.source_census, "source_census", minimum=0)
            if len(ids) != self.source_census:
                raise RatingsIngestError(
                    "firm normalization is not exhaustive over its source census"
                )


def _transition_reason(mapping: RatingMappingRefusal) -> TransitionRefusalReason:
    return TransitionRefusalReason(mapping.reason.value)


def _normalize_firm_rating_record(
    record: BenzingaRatingRecord,
    ontology: ReviewedFirmRatingOntology,
) -> FirmNormalizedRatingEvent | FirmNormalizationRefusal:
    """Apply one reviewed firm scale and admit only genuine directional changes."""
    current_mapping: RatingMapping | None = None
    previous_mapping: RatingMapping | None = None
    ontology_required = record.action not in {
        RatingAction.TARGET_ONLY,
        RatingAction.COVERAGE_TERMINATION,
    }
    if ontology_required and record.current_rating is not None:
        current = resolve_firm_rating(
            ontology,
            provider_firm_id=record.provider_firm_id,
            event_date=record.action_date,
            raw_label=record.current_rating,
        )
        if isinstance(current, RatingMappingRefusal):
            return FirmNormalizationRefusal(record, _transition_reason(current))
        current_mapping = current
    if ontology_required and record.previous_rating is not None:
        previous = resolve_firm_rating(
            ontology,
            provider_firm_id=record.provider_firm_id,
            event_date=record.action_date,
            raw_label=record.previous_rating,
        )
        if isinstance(previous, RatingMappingRefusal):
            return FirmNormalizationRefusal(record, _transition_reason(previous))
        previous_mapping = previous

    rating_change: Fraction | None = None
    if record.action in (RatingAction.UPGRADE, RatingAction.DOWNGRADE):
        if current_mapping is None or previous_mapping is None:
            raise RatingsIngestError("directional ingest event lost a required mapping")
        rating_change = current_mapping.score - previous_mapping.score
        if (
            record.action is RatingAction.UPGRADE
            and rating_change <= 0
        ) or (
            record.action is RatingAction.DOWNGRADE
            and rating_change >= 0
        ):
            return FirmNormalizationRefusal(
                record, TransitionRefusalReason.ACTION_DIRECTION_MISMATCH
            )
    elif (
        record.action in (RatingAction.MAINTAIN, RatingAction.REITERATION)
        and current_mapping is not None
        and previous_mapping is not None
        and current_mapping.score != previous_mapping.score
    ):
        return FirmNormalizationRefusal(
            record, TransitionRefusalReason.NONCHANGE_ACTION_CHANGED_RATING
        )

    return FirmNormalizedRatingEvent(
        source_event=record,
        ontology_id=ontology.ontology_id,
        ontology_sha256=ontology.payload_sha256,
        current_mapping=current_mapping,
        previous_mapping=previous_mapping,
        rating_change=rating_change,
    )


def normalize_firm_rating_event(
    audit: BenzingaIngestAudit,
    ontology: ReviewedFirmRatingOntology,
    *,
    provider_event_id: str,
) -> FirmNormalizedRatingEvent | FirmNormalizationRefusal:
    """Normalize one event selected from a reauthenticated structural audit."""
    revalidate_benzinga_ingest_audit(audit)
    revalidate_firm_rating_ontology(ontology)
    require_identifier(provider_event_id, "provider_event_id")
    matches = tuple(
        record
        for record in audit.records
        if record.provider_event_id == provider_event_id
    )
    if len(matches) != 1:
        raise RatingsIngestError(
            "provider event is not exactly one accepted structural audit row"
        )
    return _normalize_firm_rating_record(matches[0], ontology)


def normalize_firm_rating_audit(
    audit: BenzingaIngestAudit,
    ontology: ReviewedFirmRatingOntology,
) -> FirmRatingNormalizationResult:
    """Give every structurally accepted row one ontology disposition."""
    revalidate_benzinga_ingest_audit(audit)
    revalidate_firm_rating_ontology(ontology)
    events: list[FirmNormalizedRatingEvent] = []
    refusals: list[FirmNormalizationRefusal] = []
    for record in audit.records:
        decision = _normalize_firm_rating_record(record, ontology)
        if isinstance(decision, FirmNormalizedRatingEvent):
            events.append(decision)
        else:
            refusals.append(decision)
    return FirmRatingNormalizationResult(
        schema=FIRM_NORMALIZATION_SCHEMA,
        source_audit_sha256=audit.audit_sha256,
        ontology_id=ontology.ontology_id,
        ontology_sha256=ontology.payload_sha256,
        events=tuple(events),
        refusals=tuple(refusals),
        # Bind the exact accepted-row census so the result is provably
        # exhaustive over the audit it claims to normalize.
        source_census=len(audit.records),
    )


def revalidate_firm_rating_normalization(
    result: FirmRatingNormalizationResult,
    *,
    audit: BenzingaIngestAudit,
    ontology: ReviewedFirmRatingOntology,
) -> FirmRatingNormalizationResult:
    if type(result) is not FirmRatingNormalizationResult:
        raise RatingsIngestError(
            "normalization authority requires a FirmRatingNormalizationResult"
        )
    rebuilt = normalize_firm_rating_audit(audit, ontology)
    if rebuilt != result:
        raise RatingsIngestError("firm normalization result is not source-derived")
    return result


@dataclasses.dataclass(frozen=True)
class DailyRatingContributionCandidate:
    canonical_event_id: str
    institution_id: str
    security_id: str
    trading_day: str
    previous_score: Fraction
    current_score: Fraction

    def __post_init__(self) -> None:
        require_identifier(self.canonical_event_id, "canonical_event_id")
        require_identifier(self.institution_id, "institution_id")
        require_identifier(self.security_id, "security_id")
        parse_date(self.trading_day, "trading_day")
        if type(self.previous_score) is not Fraction or type(
            self.current_score
        ) is not Fraction:
            raise RatingsIngestError("daily rating scores must be exact Fractions")
        if not (-1 <= self.previous_score <= 1) or not (
            -1 <= self.current_score <= 1
        ):
            raise RatingsIngestError("daily rating scores must be in [-1, 1]")
        if self.previous_score == self.current_score:
            raise RatingsIngestError("daily contribution must be a genuine change")

    @property
    def dedupe_key(self) -> tuple[str, str, str]:
        return (self.institution_id, self.security_id, self.trading_day)

    @property
    def economic_signature(self) -> tuple[Fraction, Fraction]:
        return (self.previous_score, self.current_score)


@dataclasses.dataclass(frozen=True)
class DailyRatingContribution:
    institution_id: str
    security_id: str
    trading_day: str
    contributing_event_id: str
    linked_event_ids: tuple[str, ...]
    rating_change: Fraction

    def __post_init__(self) -> None:
        require_identifier(self.institution_id, "institution_id")
        require_identifier(self.security_id, "security_id")
        parse_date(self.trading_day, "trading_day")
        require_identifier(self.contributing_event_id, "contributing_event_id")
        if (
            not self.linked_event_ids
            or self.linked_event_ids != tuple(sorted(set(self.linked_event_ids)))
        ):
            raise RatingsIngestError("linked event IDs must be nonempty, unique, sorted")
        for event_id in self.linked_event_ids:
            require_identifier(event_id, "linked_event_id")
        if self.contributing_event_id not in self.linked_event_ids:
            raise RatingsIngestError("contributing event is absent from raw lineage")
        if type(self.rating_change) is not Fraction or self.rating_change == 0:
            raise RatingsIngestError("daily rating change must be an exact nonzero Fraction")


@dataclasses.dataclass(frozen=True)
class DailyDedupeRefusal:
    institution_id: str
    security_id: str
    trading_day: str
    linked_event_ids: tuple[str, ...]
    reason: DailyDedupeRefusalReason

    def __post_init__(self) -> None:
        require_identifier(self.institution_id, "institution_id")
        require_identifier(self.security_id, "security_id")
        parse_date(self.trading_day, "trading_day")
        if (
            len(self.linked_event_ids) < 2
            or self.linked_event_ids != tuple(sorted(set(self.linked_event_ids)))
        ):
            raise RatingsIngestError(
                "conflict lineage must contain at least two unique sorted events"
            )
        for event_id in self.linked_event_ids:
            require_identifier(event_id, "linked_event_id")
        if not isinstance(self.reason, DailyDedupeRefusalReason):
            raise RatingsIngestError("daily dedupe refusal reason has the wrong type")


@dataclasses.dataclass(frozen=True)
class DailyDedupeResult:
    schema: str
    contributions: tuple[DailyRatingContribution, ...]
    refusals: tuple[DailyDedupeRefusal, ...]

    def __post_init__(self) -> None:
        if self.schema != DAILY_DEDUPE_SCHEMA:
            raise RatingsIngestError("unsupported daily dedupe schema")
        if type(self.contributions) is not tuple or any(
            type(item) is not DailyRatingContribution for item in self.contributions
        ):
            raise RatingsIngestError("daily contributions must be an exact tuple")
        if type(self.refusals) is not tuple or any(
            type(item) is not DailyDedupeRefusal for item in self.refusals
        ):
            raise RatingsIngestError("daily refusals must be an exact tuple")
        contribution_keys = [
            (item.institution_id, item.security_id, item.trading_day)
            for item in self.contributions
        ]
        refusal_keys = [
            (item.institution_id, item.security_id, item.trading_day)
            for item in self.refusals
        ]
        terminal = contribution_keys + refusal_keys
        if len(terminal) != len(set(terminal)):
            raise RatingsIngestError(
                "institution-security-day has more than one terminal dedupe result"
            )
        if contribution_keys != sorted(contribution_keys) or refusal_keys != sorted(
            refusal_keys
        ):
            raise RatingsIngestError("daily dedupe results are not canonical-sorted")
        linked_ids = [
            event_id
            for item in (*self.contributions, *self.refusals)
            for event_id in item.linked_event_ids
        ]
        if len(linked_ids) != len(set(linked_ids)):
            raise RatingsIngestError("one canonical event appears in multiple dedupe groups")


def deduplicate_daily_rating_contributions(
    candidates: tuple[DailyRatingContributionCandidate, ...],
) -> DailyDedupeResult:
    """Collapse exact duplicates and refuse conflicting same-day economics.

    Permanent institution/security identities are intentionally inputs to this
    pure contract.  ARV2-2 must authenticate those identities before any
    production call; this function never deduplicates on a ticker.
    """
    if type(candidates) is not tuple or any(
        type(candidate) is not DailyRatingContributionCandidate
        for candidate in candidates
    ):
        raise RatingsIngestError("daily dedupe candidates must be an exact tuple")
    ids = [candidate.canonical_event_id for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise RatingsIngestError("canonical event IDs must be unique before dedupe")
    groups: dict[
        tuple[str, str, str], list[DailyRatingContributionCandidate]
    ] = defaultdict(list)
    for candidate in candidates:
        groups[candidate.dedupe_key].append(candidate)

    contributions: list[DailyRatingContribution] = []
    refusals: list[DailyDedupeRefusal] = []
    for key in sorted(groups):
        group = groups[key]
        linked = tuple(sorted(candidate.canonical_event_id for candidate in group))
        signatures = {candidate.economic_signature for candidate in group}
        if len(signatures) != 1:
            refusals.append(
                DailyDedupeRefusal(
                    institution_id=key[0],
                    security_id=key[1],
                    trading_day=key[2],
                    linked_event_ids=linked,
                    reason=(
                        DailyDedupeRefusalReason.CONFLICTING_SAME_DAY_ECONOMIC_EVENTS
                    ),
                )
            )
            continue
        previous, current = next(iter(signatures))
        contributions.append(
            DailyRatingContribution(
                institution_id=key[0],
                security_id=key[1],
                trading_day=key[2],
                contributing_event_id=linked[0],
                linked_event_ids=linked,
                rating_change=current - previous,
            )
        )
    return DailyDedupeResult(
        schema=DAILY_DEDUPE_SCHEMA,
        contributions=tuple(contributions),
        refusals=tuple(refusals),
    )
