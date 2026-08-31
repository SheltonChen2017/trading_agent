"""Point-in-time issuer, security, share-class, and listing identity for ARV2.

The provider's historical ticker is only an observation, never a permanent
identity.  This module resolves it through half-open, availability-dated
reference records and gives every structurally accepted rating event one
mapping or one named refusal.  It does not load prices, returns, or outcomes.
"""
from __future__ import annotations

import dataclasses
import re
import threading
import weakref
from collections import Counter, defaultdict
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    parse_date,
    parse_utc_timestamp,
    require_canonical_json_bytes,
    require_exact_keys,
    require_identifier,
    require_sha256,
    require_text,
    require_ticker,
    sha256_bytes,
)
from .firm_ontology import (
    ReviewedFirmRatingOntology,
    revalidate_firm_rating_ontology,
)
from .production_registry import require_production_registry_entry
from .ratings_ingest import (
    BenzingaIngestAudit,
    BenzingaRatingRecord,
    FirmNormalizationRefusal,
    FirmNormalizedRatingEvent,
    FirmRatingNormalizationResult,
    revalidate_benzinga_ingest_audit,
    revalidate_firm_rating_normalization,
)


PIT_SECURITY_MASTER_SCHEMA = "arv2-pit-security-master-v1"
SECURITY_IDENTITY_AUDIT_SCHEMA = "arv2-security-identity-audit-v1"
IDENTITY_RESOLVED_FIRM_RESULT_SCHEMA = "arv2-identity-firm-result-v1"
TERMINAL_OUTCOME_REQUIREMENT_SCHEMA = "arv2-terminal-outcome-requirement-v1"
SECURITY_MASTER_REGISTRY_SCHEMA = "arv2-security-master-registry-v2"
SECURITY_MASTER_REGISTRY_PATH = (
    Path(__file__).resolve().parent / "specs" / "security_master_registry.json"
)

ELIGIBLE_ISSUER_COUNTRY = "US"
ELIGIBLE_LISTING_EXCHANGES = frozenset({"XASE", "XNAS", "XNYS"})

_MASTER_KEYS = frozenset(
    {
        "schema",
        "security_master_id",
        "version",
        "created_at",
        "source_id",
        "source_sha256",
        "issuers",
        "securities",
        "listings",
        "lineage_events",
    }
)
_ISSUER_KEYS = frozenset(
    {
        "issuer_id",
        "cik",
        "incorporation_country",
        "valid_from",
        "valid_to",
        "valid_to_available_at",
        "available_at",
        "evidence_id",
        "evidence_sha256",
    }
)
_VENDOR_ID_KEYS = frozenset(
    {
        "provider",
        "value",
        "valid_from",
        "valid_to",
        "valid_to_available_at",
        "available_at",
        "evidence_id",
        "evidence_sha256",
    }
)
_SECURITY_KEYS = frozenset(
    {
        "security_id",
        "issuer_id",
        "share_class_id",
        "security_type",
        "isin",
        "figi",
        "vendor_ids",
        "valid_from",
        "valid_to",
        "valid_to_available_at",
        "available_at",
        "evidence_id",
        "evidence_sha256",
    }
)
_LISTING_KEYS = frozenset(
    {
        "listing_id",
        "security_id",
        "ticker",
        "exchange",
        "country",
        "valid_from",
        "valid_to",
        "valid_to_available_at",
        "available_at",
        "evidence_id",
        "evidence_sha256",
    }
)
_LINEAGE_KEYS = frozenset(
    {
        "lineage_event_id",
        "kind",
        "security_id",
        "effective_date",
        "available_at",
        "successor_security_id",
        "evidence_id",
        "evidence_sha256",
    }
)
_COUNTRY_RE = re.compile(r"[A-Z]{2}")
_CIK_RE = re.compile(r"[0-9]{10}")


class SecurityMasterError(CanonicalEvidenceError):
    """A PIT security master or identity result is not admissible."""


class SecurityType(str, Enum):
    COMMON_STOCK = "common_stock"
    ADR = "adr"
    BDC = "bdc"
    CLOSED_END_FUND = "closed_end_fund"
    ETF = "etf"
    FOREIGN_ORDINARY = "foreign_ordinary"
    LIMITED_PARTNERSHIP = "limited_partnership"
    PREFERRED_STOCK = "preferred_stock"
    REIT = "reit"
    RIGHT = "right"
    TRUST = "trust"
    UNIT = "unit"
    WARRANT = "warrant"


class LineageKind(str, Enum):
    SYMBOL_CHANGE = "symbol_change"
    LISTING_CHANGE = "listing_change"
    MERGER = "merger"
    DELISTING = "delisting"


class IdentityRefusalReason(str, Enum):
    NO_ACTIVE_TICKER_MAPPING = "no_active_ticker_mapping"
    AMBIGUOUS_ACTIVE_TICKER_MAPPING = "ambiguous_active_ticker_mapping"
    IDENTITY_NOT_AVAILABLE_BY_EVENT = "identity_not_available_by_event"
    INELIGIBLE_ISSUER_COUNTRY = "ineligible_issuer_country"
    INELIGIBLE_LISTING_COUNTRY = "ineligible_listing_country"
    INELIGIBLE_EXCHANGE = "ineligible_exchange"
    INELIGIBLE_SECURITY_TYPE = "ineligible_security_type"
    SECURITY_TERMINATED_BEFORE_EVENT = "security_terminated_before_event"


class CombinedRefusalStage(str, Enum):
    IDENTITY = "identity"
    FIRM_ONTOLOGY = "firm_ontology"


def _enum(value: object, enum_type: type[Enum], name: str):
    if not isinstance(value, str):
        raise SecurityMasterError(f"{name} must be a string enum")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise SecurityMasterError(f"unknown {name}: {value!r}") from exc


def _country(value: object, name: str) -> str:
    if not isinstance(value, str) or _COUNTRY_RE.fullmatch(value) is None:
        raise SecurityMasterError(f"{name} must be an uppercase ISO alpha-2 code")
    return value


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else require_text(value, name)


def _interval(value_from: str, value_to: str | None, name: str) -> tuple[date, date | None]:
    start = parse_date(value_from, f"{name}.valid_from")
    end = None if value_to is None else parse_date(value_to, f"{name}.valid_to")
    if end is not None and end <= start:
        raise SecurityMasterError(f"{name} validity interval is empty/reversed")
    return start, end


def _validate_closure_availability(
    *,
    valid_to: str | None,
    valid_to_available_at: str | None,
    available_at: str,
    name: str,
) -> None:
    if (valid_to is None) != (valid_to_available_at is None):
        raise SecurityMasterError(
            f"{name} valid_to and valid_to_available_at must both be null or present"
        )
    base = parse_utc_timestamp(available_at, f"{name}.available_at")
    if valid_to_available_at is None:
        return
    closure = parse_utc_timestamp(
        valid_to_available_at, f"{name}.valid_to_available_at"
    )
    if closure < base:
        raise SecurityMasterError(
            f"{name} closure cannot be available before the base mapping"
        )


def _visible_valid_to(
    *, valid_to: str | None, valid_to_available_at: str | None, cutoff
) -> str | None:
    if valid_to is None or valid_to_available_at is None:
        return None
    return (
        valid_to
        if parse_utc_timestamp(valid_to_available_at, "valid_to_available_at")
        <= cutoff
        else None
    )


def _contains(start: date, end: date | None, when: date) -> bool:
    return start <= when and (end is None or when < end)


def _end_key(end: date | None) -> date:
    return date.max if end is None else end


def _within(
    child: tuple[date, date | None], parent: tuple[date, date | None]
) -> bool:
    return child[0] >= parent[0] and _end_key(child[1]) <= _end_key(parent[1])


def _overlaps(
    first: tuple[date, date | None], second: tuple[date, date | None]
) -> bool:
    return first[0] < _end_key(second[1]) and second[0] < _end_key(first[1])


@dataclasses.dataclass(frozen=True)
class IssuerRecord:
    issuer_id: str
    cik: str | None
    incorporation_country: str
    valid_from: str
    valid_to: str | None
    valid_to_available_at: str | None
    available_at: str
    evidence_id: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.issuer_id, "issuer_id")
        if self.cik is not None and (
            not isinstance(self.cik, str) or _CIK_RE.fullmatch(self.cik) is None
        ):
            raise SecurityMasterError("cik must be null or exactly ten digits")
        _country(self.incorporation_country, "incorporation_country")
        _interval(self.valid_from, self.valid_to, "issuer")
        _validate_closure_availability(
            valid_to=self.valid_to,
            valid_to_available_at=self.valid_to_available_at,
            available_at=self.available_at,
            name="issuer",
        )
        require_identifier(self.evidence_id, "issuer.evidence_id")
        require_sha256(self.evidence_sha256, "issuer.evidence_sha256")

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "IssuerRecord":
        require_exact_keys(record, _ISSUER_KEYS, "issuer record")
        return cls(**dict(record))

    def to_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class VendorIdentifier:
    provider: str
    value: str
    valid_from: str
    valid_to: str | None
    valid_to_available_at: str | None
    available_at: str
    evidence_id: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.provider, "vendor.provider")
        require_text(self.value, "vendor.value")
        _interval(self.valid_from, self.valid_to, "vendor identifier")
        _validate_closure_availability(
            valid_to=self.valid_to,
            valid_to_available_at=self.valid_to_available_at,
            available_at=self.available_at,
            name="vendor identifier",
        )
        require_identifier(self.evidence_id, "vendor.evidence_id")
        require_sha256(self.evidence_sha256, "vendor.evidence_sha256")

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "VendorIdentifier":
        require_exact_keys(record, _VENDOR_ID_KEYS, "vendor identifier")
        return cls(**dict(record))

    def to_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SecurityRecord:
    security_id: str
    issuer_id: str
    share_class_id: str
    security_type: SecurityType
    isin: str | None
    figi: str | None
    vendor_ids: tuple[VendorIdentifier, ...]
    valid_from: str
    valid_to: str | None
    valid_to_available_at: str | None
    available_at: str
    evidence_id: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.security_id, "security_id")
        require_identifier(self.issuer_id, "security.issuer_id")
        require_identifier(self.share_class_id, "share_class_id")
        if not isinstance(self.security_type, SecurityType):
            raise SecurityMasterError("security_type must be a SecurityType")
        _optional_text(self.isin, "isin")
        _optional_text(self.figi, "figi")
        if type(self.vendor_ids) is not tuple or any(
            type(item) is not VendorIdentifier for item in self.vendor_ids
        ):
            raise SecurityMasterError("vendor_ids must be an exact tuple")
        vendor_order = tuple(
            sorted(
                self.vendor_ids,
                key=lambda item: (item.provider, item.valid_from, item.value),
            )
        )
        if self.vendor_ids != vendor_order:
            raise SecurityMasterError("vendor identifiers are not canonical-sorted")
        provider_intervals: dict[str, list[tuple[date, date | None]]] = defaultdict(list)
        for item in self.vendor_ids:
            interval = _interval(item.valid_from, item.valid_to, "vendor identifier")
            for prior in provider_intervals[item.provider]:
                if _overlaps(prior, interval):
                    raise SecurityMasterError(
                        "one provider has overlapping identifiers for a security"
                    )
            provider_intervals[item.provider].append(interval)
        _interval(self.valid_from, self.valid_to, "security")
        _validate_closure_availability(
            valid_to=self.valid_to,
            valid_to_available_at=self.valid_to_available_at,
            available_at=self.available_at,
            name="security",
        )
        require_identifier(self.evidence_id, "security.evidence_id")
        require_sha256(self.evidence_sha256, "security.evidence_sha256")

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "SecurityRecord":
        require_exact_keys(record, _SECURITY_KEYS, "security record")
        raw_vendor_ids = record["vendor_ids"]
        if not isinstance(raw_vendor_ids, list):
            raise SecurityMasterError("vendor_ids must be an array")
        fields = dict(record)
        fields["security_type"] = _enum(
            fields["security_type"], SecurityType, "security_type"
        )
        fields["vendor_ids"] = tuple(
            VendorIdentifier.from_record(item) for item in raw_vendor_ids
        )
        return cls(**fields)

    def to_record(self) -> dict[str, Any]:
        return {
            "security_id": self.security_id,
            "issuer_id": self.issuer_id,
            "share_class_id": self.share_class_id,
            "security_type": self.security_type.value,
            "isin": self.isin,
            "figi": self.figi,
            "vendor_ids": [item.to_record() for item in self.vendor_ids],
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "valid_to_available_at": self.valid_to_available_at,
            "available_at": self.available_at,
            "evidence_id": self.evidence_id,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclasses.dataclass(frozen=True)
class ListingInterval:
    listing_id: str
    security_id: str
    ticker: str
    exchange: str
    country: str
    valid_from: str
    valid_to: str | None
    valid_to_available_at: str | None
    available_at: str
    evidence_id: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.listing_id, "listing_id")
        require_identifier(self.security_id, "listing.security_id")
        require_ticker(self.ticker)
        require_identifier(self.exchange, "exchange")
        _country(self.country, "listing.country")
        _interval(self.valid_from, self.valid_to, "listing")
        _validate_closure_availability(
            valid_to=self.valid_to,
            valid_to_available_at=self.valid_to_available_at,
            available_at=self.available_at,
            name="listing",
        )
        require_identifier(self.evidence_id, "listing.evidence_id")
        require_sha256(self.evidence_sha256, "listing.evidence_sha256")

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "ListingInterval":
        require_exact_keys(record, _LISTING_KEYS, "listing interval")
        return cls(**dict(record))

    def to_record(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class SecurityLineageEvent:
    lineage_event_id: str
    kind: LineageKind
    security_id: str
    effective_date: str
    available_at: str
    successor_security_id: str | None
    evidence_id: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.lineage_event_id, "lineage_event_id")
        if not isinstance(self.kind, LineageKind):
            raise SecurityMasterError("lineage kind must be a LineageKind")
        require_identifier(self.security_id, "lineage.security_id")
        parse_date(self.effective_date, "lineage.effective_date")
        parse_utc_timestamp(self.available_at, "lineage.available_at")
        if self.successor_security_id is not None:
            require_identifier(self.successor_security_id, "successor_security_id")
        if self.kind is LineageKind.MERGER:
            if (
                self.successor_security_id is None
                or self.successor_security_id == self.security_id
            ):
                raise SecurityMasterError(
                    "merger lineage requires a distinct successor security"
                )
        elif self.successor_security_id is not None:
            raise SecurityMasterError(
                "only merger lineage may carry a successor security"
            )
        require_identifier(self.evidence_id, "lineage.evidence_id")
        require_sha256(self.evidence_sha256, "lineage.evidence_sha256")

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "SecurityLineageEvent":
        require_exact_keys(record, _LINEAGE_KEYS, "security lineage event")
        fields = dict(record)
        fields["kind"] = _enum(fields["kind"], LineageKind, "lineage kind")
        return cls(**fields)

    def to_record(self) -> dict[str, Any]:
        return {
            "lineage_event_id": self.lineage_event_id,
            "kind": self.kind.value,
            "security_id": self.security_id,
            "effective_date": self.effective_date,
            "available_at": self.available_at,
            "successor_security_id": self.successor_security_id,
            "evidence_id": self.evidence_id,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclasses.dataclass(frozen=True, init=False)
class PointInTimeSecurityMaster:
    schema: str
    security_master_id: str
    version: str
    created_at: str
    source_id: str
    source_sha256: str
    issuers: tuple[IssuerRecord, ...]
    securities: tuple[SecurityRecord, ...]
    listings: tuple[ListingInterval, ...]
    lineage_events: tuple[SecurityLineageEvent, ...]
    payload_sha256: str
    source_path: str


_SECURITY_MASTER_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[PointInTimeSecurityMaster],
        Path,
        tuple[object, ...],
    ],
] = {}
_SECURITY_MASTER_AUTHORITIES_LOCK = threading.RLock()


def _master_fingerprint(master: PointInTimeSecurityMaster) -> tuple[object, ...]:
    return (
        master.schema,
        master.security_master_id,
        master.version,
        master.created_at,
        master.source_id,
        master.source_sha256,
        master.issuers,
        master.securities,
        master.listings,
        master.lineage_events,
        master.payload_sha256,
        master.source_path,
    )


def _forget_master_authority(
    identity: int, reference: weakref.ReferenceType[PointInTimeSecurityMaster]
) -> None:
    with _SECURITY_MASTER_AUTHORITIES_LOCK:
        current = _SECURITY_MASTER_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _SECURITY_MASTER_AUTHORITIES.pop(identity, None)


def _canonical_sequence(
    values: tuple[Any, ...], *, key, name: str, require_nonempty: bool = True
) -> None:
    if require_nonempty and not values:
        raise SecurityMasterError(f"security master {name} cannot be empty")
    if values != tuple(sorted(values, key=key)):
        raise SecurityMasterError(f"security master {name} are not canonical-sorted")


def _validate_master_records(
    issuers: tuple[IssuerRecord, ...],
    securities: tuple[SecurityRecord, ...],
    listings: tuple[ListingInterval, ...],
    lineage_events: tuple[SecurityLineageEvent, ...],
) -> None:
    _canonical_sequence(issuers, key=lambda item: item.issuer_id, name="issuers")
    _canonical_sequence(
        securities, key=lambda item: item.security_id, name="securities"
    )
    _canonical_sequence(
        listings,
        key=lambda item: (
            item.ticker,
            item.valid_from,
            item.exchange,
            item.security_id,
            item.listing_id,
        ),
        name="listings",
    )
    _canonical_sequence(
        lineage_events,
        key=lambda item: (
            item.effective_date,
            item.security_id,
            item.lineage_event_id,
        ),
        name="lineage events",
        require_nonempty=False,
    )
    for values, name, identity in (
        (issuers, "issuer", lambda item: item.issuer_id),
        (securities, "security", lambda item: item.security_id),
        (listings, "listing", lambda item: item.listing_id),
        (lineage_events, "lineage event", lambda item: item.lineage_event_id),
    ):
        ids = tuple(identity(item) for item in values)
        if len(ids) != len(set(ids)):
            raise SecurityMasterError(f"security master contains duplicate {name} IDs")

    issuer_by_id = {item.issuer_id: item for item in issuers}
    security_by_id = {item.security_id: item for item in securities}
    issuer_by_cik: dict[str, str] = {}
    for issuer in issuers:
        if issuer.cik is None:
            continue
        prior_issuer = issuer_by_cik.setdefault(issuer.cik, issuer.issuer_id)
        if prior_issuer != issuer.issuer_id:
            raise SecurityMasterError(
                "one permanent CIK cannot identify multiple issuers"
            )
    share_classes: dict[str, str] = {}
    security_by_vendor_id: dict[tuple[str, str], str] = {}
    security_by_standard_id: dict[tuple[str, str], str] = {}
    for security in securities:
        issuer = issuer_by_id.get(security.issuer_id)
        if issuer is None:
            raise SecurityMasterError("security references an absent issuer")
        prior_security = share_classes.setdefault(
            security.share_class_id, security.security_id
        )
        if prior_security != security.security_id:
            raise SecurityMasterError(
                "one share_class_id cannot identify multiple securities"
            )
        security_interval = _interval(
            security.valid_from, security.valid_to, "security"
        )
        issuer_interval = _interval(issuer.valid_from, issuer.valid_to, "issuer")
        if not _within(security_interval, issuer_interval):
            raise SecurityMasterError("security validity escapes its issuer validity")
        for vendor_id in security.vendor_ids:
            vendor_interval = _interval(
                vendor_id.valid_from, vendor_id.valid_to, "vendor identifier"
            )
            if not _within(vendor_interval, security_interval):
                raise SecurityMasterError(
                    "vendor identifier validity escapes its security validity"
                )
            vendor_key = (vendor_id.provider, vendor_id.value)
            prior_security = security_by_vendor_id.setdefault(
                vendor_key, security.security_id
            )
            if prior_security != security.security_id:
                raise SecurityMasterError(
                    "one permanent vendor identifier cannot map to multiple securities"
                )
        for kind, value in (("isin", security.isin), ("figi", security.figi)):
            if value is None:
                continue
            standard_key = (kind, value)
            prior_security = security_by_standard_id.setdefault(
                standard_key, security.security_id
            )
            if prior_security != security.security_id:
                raise SecurityMasterError(
                    f"one permanent {kind} cannot map to multiple securities"
                )

    listings_by_security: dict[str, list[ListingInterval]] = defaultdict(list)
    same_market: dict[tuple[str, str], list[ListingInterval]] = defaultdict(list)
    for listing in listings:
        security = security_by_id.get(listing.security_id)
        if security is None:
            raise SecurityMasterError("listing references an absent security")
        if not _within(
            _interval(listing.valid_from, listing.valid_to, "listing"),
            _interval(security.valid_from, security.valid_to, "security"),
        ):
            raise SecurityMasterError("listing validity escapes security validity")
        listings_by_security[listing.security_id].append(listing)
        same_market[(listing.ticker, listing.exchange)].append(listing)
    if set(listings_by_security) != set(security_by_id):
        raise SecurityMasterError("every security must retain listing history")
    for security_listings in listings_by_security.values():
        intervals = [
            _interval(item.valid_from, item.valid_to, "listing")
            for item in security_listings
        ]
        for index, interval in enumerate(intervals):
            if any(_overlaps(interval, other) for other in intervals[index + 1 :]):
                raise SecurityMasterError(
                    "one security cannot have overlapping listing intervals"
                )
    for market_listings in same_market.values():
        for index, listing in enumerate(market_listings):
            interval = _interval(listing.valid_from, listing.valid_to, "listing")
            for other in market_listings[index + 1 :]:
                if _overlaps(
                    interval,
                    _interval(other.valid_from, other.valid_to, "listing"),
                ):
                    raise SecurityMasterError(
                        "one ticker/exchange cannot map to overlapping securities"
                    )

    lineage_by_security: dict[str, list[SecurityLineageEvent]] = defaultdict(list)
    terminal_by_security: dict[str, SecurityLineageEvent] = {}
    successors: dict[str, str] = {}
    for event in lineage_events:
        security = security_by_id.get(event.security_id)
        if security is None:
            raise SecurityMasterError("lineage references an absent security")
        event_available = parse_utc_timestamp(
            event.available_at, "lineage.available_at"
        )
        predecessor_issuer = issuer_by_id[security.issuer_id]
        referenced_identity_times = [
            parse_utc_timestamp(security.available_at, "security.available_at"),
            parse_utc_timestamp(
                predecessor_issuer.available_at, "issuer.available_at"
            ),
        ]
        if event.successor_security_id is not None:
            if event.successor_security_id not in security_by_id:
                raise SecurityMasterError("lineage successor is absent")
            successor = security_by_id[event.successor_security_id]
            if not _contains(
                *_interval(successor.valid_from, successor.valid_to, "successor"),
                parse_date(event.effective_date, "lineage.effective_date"),
            ):
                raise SecurityMasterError(
                    "lineage successor is not active on the effective date"
                )
            successor_issuer = issuer_by_id[successor.issuer_id]
            referenced_identity_times.extend(
                (
                    parse_utc_timestamp(
                        successor.available_at, "successor.available_at"
                    ),
                    parse_utc_timestamp(
                        successor_issuer.available_at,
                        "successor issuer.available_at",
                    ),
                )
            )
            successors[event.security_id] = event.successor_security_id
        if event_available < max(referenced_identity_times):
            raise SecurityMasterError(
                "lineage cannot predate referenced identity evidence"
            )
        lineage_by_security[event.security_id].append(event)
        if event.kind in {LineageKind.MERGER, LineageKind.DELISTING}:
            if event.security_id in terminal_by_security:
                raise SecurityMasterError("one security has multiple terminal events")
            terminal_by_security[event.security_id] = event
            if security.valid_to != event.effective_date:
                raise SecurityMasterError(
                    "terminal lineage must equal the security half-open valid_to"
                )
            if security.valid_to_available_at is None or event_available < (
                parse_utc_timestamp(
                    security.valid_to_available_at,
                    "security.valid_to_available_at",
                )
            ):
                raise SecurityMasterError(
                    "terminal lineage cannot predate security closure evidence"
                )
            if any(
                listing.valid_to is None
                or parse_date(listing.valid_to, "listing.valid_to")
                > parse_date(event.effective_date, "lineage.effective_date")
                for listing in listings_by_security[event.security_id]
            ):
                raise SecurityMasterError(
                    "terminal lineage must end every predecessor listing"
                )
            if any(
                listing.valid_to_available_at is None
                or event_available
                < parse_utc_timestamp(
                    listing.valid_to_available_at,
                    "listing.valid_to_available_at",
                )
                for listing in listings_by_security[event.security_id]
                if listing.valid_to == event.effective_date
            ):
                raise SecurityMasterError(
                    "terminal lineage cannot predate listing closure evidence"
                )
        elif event.kind in {LineageKind.SYMBOL_CHANGE, LineageKind.LISTING_CHANGE}:
            effective = event.effective_date
            before = tuple(
                listing
                for listing in listings_by_security[event.security_id]
                if listing.valid_to == effective
            )
            after = tuple(
                listing
                for listing in listings_by_security[event.security_id]
                if listing.valid_from == effective
            )
            before_tickers = {listing.ticker for listing in before}
            after_tickers = {listing.ticker for listing in after}
            before_markets = {
                (listing.ticker, listing.exchange) for listing in before
            }
            after_markets = {(listing.ticker, listing.exchange) for listing in after}
            invalid_change = (
                event.kind is LineageKind.SYMBOL_CHANGE
                and before_tickers == after_tickers
            ) or (
                event.kind is LineageKind.LISTING_CHANGE
                and (
                    before_tickers != after_tickers
                    or before_markets == after_markets
                )
            )
            if not before or not after or invalid_change:
                raise SecurityMasterError(
                    "listing transition requires abutting intervals and the named change"
                )
            if any(
                listing.valid_to_available_at is None
                or event_available
                < parse_utc_timestamp(
                    listing.valid_to_available_at,
                    "listing.valid_to_available_at",
                )
                for listing in before
            ):
                raise SecurityMasterError(
                    "listing transition cannot predate listing closure evidence"
                )
    for security in securities:
        terminal = terminal_by_security.get(security.security_id)
        if (security.valid_to is None) == (terminal is None):
            continue
        raise SecurityMasterError(
            "every ended security needs exactly one merger/delisting lineage"
        )
    for listing in listings:
        if listing.valid_to is None:
            continue
        terminal = terminal_by_security.get(listing.security_id)
        terminal_date = None if terminal is None else terminal.effective_date
        transition_dates = {
            event.effective_date
            for event in lineage_by_security[listing.security_id]
            if event.kind in {
                LineageKind.SYMBOL_CHANGE,
                LineageKind.LISTING_CHANGE,
            }
        }
        if (
            listing.valid_to != terminal_date
            and listing.valid_to not in transition_dates
        ):
            raise SecurityMasterError(
                "every listing closure needs transition or terminal lineage"
            )
    for origin in successors:
        seen: set[str] = set()
        cursor = origin
        while cursor in successors:
            if cursor in seen:
                raise SecurityMasterError("successor lineage contains a cycle")
            seen.add(cursor)
            cursor = successors[cursor]


def _parse_master_fields(payload: bytes) -> dict[str, object]:
    raw = require_canonical_json_bytes(payload, "PIT security master")
    if not isinstance(raw, dict):
        raise SecurityMasterError("PIT security master must be an object")
    require_exact_keys(raw, _MASTER_KEYS, "PIT security master")
    if raw["schema"] != PIT_SECURITY_MASTER_SCHEMA:
        raise SecurityMasterError("unsupported PIT security master schema")
    require_identifier(raw["security_master_id"], "security_master_id")
    require_identifier(raw["version"], "security master version")
    created_at = parse_utc_timestamp(raw["created_at"], "security master created_at")
    require_identifier(raw["source_id"], "security master source_id")
    require_sha256(raw["source_sha256"], "security master source_sha256")
    parsed: dict[str, tuple[Any, ...]] = {}
    for key, parser in (
        ("issuers", IssuerRecord.from_record),
        ("securities", SecurityRecord.from_record),
        ("listings", ListingInterval.from_record),
        ("lineage_events", SecurityLineageEvent.from_record),
    ):
        values = raw[key]
        if not isinstance(values, list):
            raise SecurityMasterError(f"security master {key} must be an array")
        if any(not isinstance(value, Mapping) for value in values):
            raise SecurityMasterError(f"security master {key} entries must be objects")
        parsed[key] = tuple(parser(value) for value in values)
    _validate_master_records(
        parsed["issuers"],
        parsed["securities"],
        parsed["listings"],
        parsed["lineage_events"],
    )
    evidence_times = [
        parse_utc_timestamp(item.available_at, "issuer.available_at")
        for item in parsed["issuers"]
    ]
    evidence_times.extend(
        parse_utc_timestamp(item.available_at, "security.available_at")
        for item in parsed["securities"]
    )
    evidence_times.extend(
        parse_utc_timestamp(item.available_at, "vendor.available_at")
        for security in parsed["securities"]
        for item in security.vendor_ids
    )
    evidence_times.extend(
        parse_utc_timestamp(item.available_at, "listing.available_at")
        for item in parsed["listings"]
    )
    evidence_times.extend(
        parse_utc_timestamp(item.available_at, "lineage.available_at")
        for item in parsed["lineage_events"]
    )
    evidence_times.extend(
        parse_utc_timestamp(item.valid_to_available_at, "valid_to_available_at")
        for item in (*parsed["issuers"], *parsed["securities"], *parsed["listings"])
        if item.valid_to_available_at is not None
    )
    evidence_times.extend(
        parse_utc_timestamp(
            item.valid_to_available_at, "vendor.valid_to_available_at"
        )
        for security in parsed["securities"]
        for item in security.vendor_ids
        if item.valid_to_available_at is not None
    )
    if any(available > created_at for available in evidence_times):
        raise SecurityMasterError(
            "security master cannot predate included identity evidence"
        )
    return {
        "schema": raw["schema"],
        "security_master_id": raw["security_master_id"],
        "version": raw["version"],
        "created_at": raw["created_at"],
        "source_id": raw["source_id"],
        "source_sha256": raw["source_sha256"],
        **parsed,
    }


def load_pit_security_master(path: str | Path) -> PointInTimeSecurityMaster:
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise SecurityMasterError("PIT security master must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise SecurityMasterError("PIT security master is absent or unreadable") from exc
    if not resolved.is_file() or resolved.is_symlink():
        raise SecurityMasterError("PIT security master must be a regular file")
    try:
        payload = resolved.read_bytes()
        fields = _parse_master_fields(payload)
    except SecurityMasterError:
        raise
    except CanonicalEvidenceError as exc:
        raise SecurityMasterError(str(exc)) from exc
    except OSError as exc:
        raise SecurityMasterError("PIT security master is unreadable") from exc
    value = object.__new__(PointInTimeSecurityMaster)
    fields.update(
        {"payload_sha256": sha256_bytes(payload), "source_path": str(resolved)}
    )
    for name, item in fields.items():
        object.__setattr__(value, name, item)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_master_authority(key, ref)
    )
    with _SECURITY_MASTER_AUTHORITIES_LOCK:
        _SECURITY_MASTER_AUTHORITIES[identity] = (
            reference,
            resolved,
            _master_fingerprint(value),
        )
    return value


def revalidate_pit_security_master(
    master: PointInTimeSecurityMaster,
) -> PointInTimeSecurityMaster:
    if type(master) is not PointInTimeSecurityMaster:
        raise SecurityMasterError(
            "security master authority requires the exact loader type"
        )
    with _SECURITY_MASTER_AUTHORITIES_LOCK:
        authority = _SECURITY_MASTER_AUTHORITIES.get(id(master))
    if authority is None or authority[0]() is not master:
        raise SecurityMasterError("PIT security master is not loader-authenticated")
    if authority[2] != _master_fingerprint(master):
        raise SecurityMasterError("PIT security master changed after authentication")
    path = authority[1]
    if not path.is_file() or path.is_symlink():
        raise SecurityMasterError("PIT security master source changed or disappeared")
    try:
        payload = path.read_bytes()
        fields = _parse_master_fields(payload)
    except SecurityMasterError:
        raise
    except CanonicalEvidenceError as exc:
        raise SecurityMasterError(str(exc)) from exc
    except OSError as exc:
        raise SecurityMasterError("PIT security master source became unreadable") from exc
    if sha256_bytes(payload) != master.payload_sha256:
        raise SecurityMasterError("PIT security master source hash changed")
    for name, expected in fields.items():
        if getattr(master, name) != expected:
            raise SecurityMasterError("PIT security master content changed")
    return master


def require_registered_production_security_master(
    master: PointInTimeSecurityMaster,
) -> PointInTimeSecurityMaster:
    """Require an exact independent review anchor; the catalog is empty now."""
    revalidate_pit_security_master(master)
    require_production_registry_entry(
        artifact_path=Path(master.source_path),
        artifact_id=master.security_master_id,
        artifact_sha256=master.payload_sha256,
        registry_path=SECURITY_MASTER_REGISTRY_PATH,
        registry_schema=SECURITY_MASTER_REGISTRY_SCHEMA,
        artifact_kind="PIT security master",
    )
    return revalidate_pit_security_master(master)


def _mapping_evidence_sha256(
    master: PointInTimeSecurityMaster,
    issuer: IssuerRecord,
    security: SecurityRecord,
    listing: ListingInterval,
    *,
    cutoff,
) -> str:
    def pit_interval_record(item) -> dict[str, Any]:
        record = item.to_record()
        visible_to = _visible_valid_to(
            valid_to=item.valid_to,
            valid_to_available_at=item.valid_to_available_at,
            cutoff=cutoff,
        )
        if visible_to is None:
            record["valid_to"] = None
            record["valid_to_available_at"] = None
        return record

    security_record = pit_interval_record(security)
    security_record["vendor_ids"] = [
        pit_interval_record(item)
        for item in security.vendor_ids
        if parse_utc_timestamp(item.available_at, "vendor.available_at") <= cutoff
    ]
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": "arv2-identity-mapping-evidence-v1",
                "security_master_id": master.security_master_id,
                "security_master_sha256": master.payload_sha256,
                "issuer": pit_interval_record(issuer),
                "security": security_record,
                "listing": pit_interval_record(listing),
            }
        )
    )


@dataclasses.dataclass(frozen=True)
class ResolvedSecurityIdentity:
    security_master_id: str
    security_master_sha256: str
    issuer_id: str
    security_id: str
    share_class_id: str
    historical_ticker: str
    exchange: str
    security_type: SecurityType
    ticker_valid_from: str
    ticker_valid_to: str | None
    identity_mapping_version_id: str
    identity_mapping_valid_from: str
    identity_mapping_valid_to: str | None
    identity_mapping_available_at: str
    identity_mapping_evidence_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.security_master_id, "security_master_id")
        require_sha256(self.security_master_sha256, "security_master_sha256")
        for name in (
            "issuer_id",
            "security_id",
            "share_class_id",
            "exchange",
            "identity_mapping_version_id",
        ):
            require_identifier(getattr(self, name), name)
        require_ticker(self.historical_ticker)
        if not isinstance(self.security_type, SecurityType):
            raise SecurityMasterError("resolved security_type is invalid")
        _interval(self.ticker_valid_from, self.ticker_valid_to, "resolved ticker")
        _interval(
            self.identity_mapping_valid_from,
            self.identity_mapping_valid_to,
            "resolved identity mapping",
        )
        parse_utc_timestamp(
            self.identity_mapping_available_at, "identity_mapping_available_at"
        )
        require_sha256(
            self.identity_mapping_evidence_sha256,
            "identity_mapping_evidence_sha256",
        )

    def to_record(self) -> dict[str, Any]:
        record = dataclasses.asdict(self)
        record["security_type"] = self.security_type.value
        return record


def _refusal_evidence_sha256(
    *,
    master: PointInTimeSecurityMaster,
    historical_ticker: str,
    effective_date: str,
    known_at: str,
    reason: IdentityRefusalReason,
) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": "arv2-identity-mapping-refusal-evidence-v1",
                "security_master_id": master.security_master_id,
                "security_master_sha256": master.payload_sha256,
                "historical_ticker": historical_ticker,
                "effective_date": effective_date,
                "known_at": known_at,
                "reason": reason.value,
            }
        )
    )


@dataclasses.dataclass(frozen=True)
class IdentityMappingRefusal:
    security_master_id: str
    security_master_sha256: str
    historical_ticker: str
    effective_date: str
    known_at: str
    reason: IdentityRefusalReason
    evidence_sha256: str

    @classmethod
    def create(
        cls,
        *,
        master: PointInTimeSecurityMaster,
        historical_ticker: str,
        effective_date: str,
        known_at: str,
        reason: IdentityRefusalReason,
    ) -> "IdentityMappingRefusal":
        return cls(
            security_master_id=master.security_master_id,
            security_master_sha256=master.payload_sha256,
            historical_ticker=historical_ticker,
            effective_date=effective_date,
            known_at=known_at,
            reason=reason,
            evidence_sha256=_refusal_evidence_sha256(
                master=master,
                historical_ticker=historical_ticker,
                effective_date=effective_date,
                known_at=known_at,
                reason=reason,
            ),
        )

    def __post_init__(self) -> None:
        require_identifier(self.security_master_id, "security_master_id")
        require_sha256(self.security_master_sha256, "security_master_sha256")
        require_ticker(self.historical_ticker)
        parse_date(self.effective_date, "effective_date")
        parse_utc_timestamp(self.known_at, "known_at")
        if not isinstance(self.reason, IdentityRefusalReason):
            raise SecurityMasterError("identity refusal reason has the wrong type")
        require_sha256(self.evidence_sha256, "identity refusal evidence_sha256")

    def to_record(self) -> dict[str, Any]:
        return {
            "security_master_id": self.security_master_id,
            "security_master_sha256": self.security_master_sha256,
            "historical_ticker": self.historical_ticker,
            "effective_date": self.effective_date,
            "known_at": self.known_at,
            "reason": self.reason.value,
            "evidence_sha256": self.evidence_sha256,
        }


def _identity_refusal(
    master: PointInTimeSecurityMaster,
    *,
    historical_ticker: str,
    effective_date: str,
    known_at: str,
    reason: IdentityRefusalReason,
) -> IdentityMappingRefusal:
    return IdentityMappingRefusal.create(
        master=master,
        historical_ticker=historical_ticker,
        effective_date=effective_date,
        known_at=known_at,
        reason=reason,
    )


@dataclasses.dataclass(frozen=True)
class _SecurityMasterIndex:
    listings_by_ticker: dict[str, tuple[ListingInterval, ...]]
    security_by_id: dict[str, SecurityRecord]
    issuer_by_id: dict[str, IssuerRecord]
    terminal_by_security: dict[str, SecurityLineageEvent]


def _index_security_master(master: PointInTimeSecurityMaster) -> _SecurityMasterIndex:
    listings: dict[str, list[ListingInterval]] = defaultdict(list)
    for listing in master.listings:
        listings[listing.ticker].append(listing)
    return _SecurityMasterIndex(
        listings_by_ticker={key: tuple(value) for key, value in listings.items()},
        security_by_id={item.security_id: item for item in master.securities},
        issuer_by_id={item.issuer_id: item for item in master.issuers},
        terminal_by_security={
            event.security_id: event
            for event in master.lineage_events
            if event.kind in {LineageKind.MERGER, LineageKind.DELISTING}
        },
    )


def _resolve_historical_security(
    master: PointInTimeSecurityMaster,
    index: _SecurityMasterIndex,
    *,
    historical_ticker: str,
    effective_date: str,
    known_at: str,
) -> ResolvedSecurityIdentity | IdentityMappingRefusal:
    ticker = require_ticker(historical_ticker)
    when = parse_date(effective_date, "effective_date")
    cutoff = parse_utc_timestamp(known_at, "known_at")
    ticker_listings = index.listings_by_ticker.get(ticker, ())
    security_by_id = index.security_by_id
    issuer_by_id = index.issuer_by_id
    hidden_known_closure = any(
        listing.valid_to is not None
        and parse_date(listing.valid_to, "listing.valid_to") <= when
        and listing.valid_to_available_at is not None
        and parse_utc_timestamp(
            listing.valid_to_available_at, "listing.valid_to_available_at"
        )
        > cutoff
        and max(
            parse_utc_timestamp(listing.available_at, "listing.available_at"),
            parse_utc_timestamp(
                security_by_id[listing.security_id].available_at,
                "security.available_at",
            ),
            parse_utc_timestamp(
                issuer_by_id[
                    security_by_id[listing.security_id].issuer_id
                ].available_at,
                "issuer.available_at",
            ),
        )
        <= cutoff
        for listing in ticker_listings
    )
    if hidden_known_closure:
        return _identity_refusal(
            master,
            historical_ticker=ticker,
            effective_date=effective_date,
            known_at=known_at,
            reason=IdentityRefusalReason.IDENTITY_NOT_AVAILABLE_BY_EVENT,
        )
    active = tuple(
        listing
        for listing in ticker_listings
        if _contains(
            *_interval(listing.valid_from, listing.valid_to, "listing"), when
        )
    )
    if not active:
        terminal_events = {
            security_id: event
            for security_id, event in index.terminal_by_security.items()
            if parse_date(event.effective_date, "lineage.effective_date") <= when
        }
        relevant_terminal_associations = tuple(
            (
                listing,
                security_by_id[listing.security_id],
                issuer_by_id[security_by_id[listing.security_id].issuer_id],
                terminal_events[listing.security_id],
            )
            for listing in ticker_listings
            if listing.security_id in terminal_events
        )
        known_terminal_association = any(
            max(
                parse_utc_timestamp(listing.available_at, "listing.available_at"),
                parse_utc_timestamp(security.available_at, "security.available_at"),
                parse_utc_timestamp(issuer.available_at, "issuer.available_at"),
                parse_utc_timestamp(event.available_at, "lineage.available_at"),
                parse_utc_timestamp(
                    listing.valid_to_available_at,
                    "listing.valid_to_available_at",
                ),
            )
            <= cutoff
            for listing, security, issuer, event in relevant_terminal_associations
        )
        ended_listings = tuple(
            listing
            for listing in ticker_listings
            if listing.valid_to is not None
            and parse_date(listing.valid_to, "listing.valid_to") <= when
        )
        unavailable_ended_mapping = any(
            max(
                parse_utc_timestamp(listing.available_at, "listing.available_at"),
                parse_utc_timestamp(
                    security_by_id[listing.security_id].available_at,
                    "security.available_at",
                ),
                parse_utc_timestamp(
                    issuer_by_id[
                        security_by_id[listing.security_id].issuer_id
                    ].available_at,
                    "issuer.available_at",
                ),
                parse_utc_timestamp(
                    listing.valid_to_available_at,
                    "listing.valid_to_available_at",
                ),
            )
            > cutoff
            for listing in ended_listings
        )
        if known_terminal_association:
            reason = IdentityRefusalReason.SECURITY_TERMINATED_BEFORE_EVENT
        elif relevant_terminal_associations or unavailable_ended_mapping:
            reason = IdentityRefusalReason.IDENTITY_NOT_AVAILABLE_BY_EVENT
        else:
            reason = IdentityRefusalReason.NO_ACTIVE_TICKER_MAPPING
        return _identity_refusal(
            master,
            historical_ticker=ticker,
            effective_date=effective_date,
            known_at=known_at,
            reason=reason,
        )

    candidates: list[tuple[ListingInterval, SecurityRecord, IssuerRecord]] = []
    for listing in active:
        security = security_by_id[listing.security_id]
        issuer = issuer_by_id[security.issuer_id]
        available = max(
            parse_utc_timestamp(listing.available_at, "listing.available_at"),
            parse_utc_timestamp(security.available_at, "security.available_at"),
            parse_utc_timestamp(issuer.available_at, "issuer.available_at"),
        )
        if available <= cutoff:
            candidates.append((listing, security, issuer))
    if not candidates:
        return _identity_refusal(
            master,
            historical_ticker=ticker,
            effective_date=effective_date,
            known_at=known_at,
            reason=IdentityRefusalReason.IDENTITY_NOT_AVAILABLE_BY_EVENT,
        )
    if len(candidates) != 1:
        return _identity_refusal(
            master,
            historical_ticker=ticker,
            effective_date=effective_date,
            known_at=known_at,
            reason=IdentityRefusalReason.AMBIGUOUS_ACTIVE_TICKER_MAPPING,
        )
    listing, security, issuer = candidates[0]
    if issuer.incorporation_country != ELIGIBLE_ISSUER_COUNTRY:
        reason = IdentityRefusalReason.INELIGIBLE_ISSUER_COUNTRY
    elif listing.country != ELIGIBLE_ISSUER_COUNTRY:
        reason = IdentityRefusalReason.INELIGIBLE_LISTING_COUNTRY
    elif listing.exchange not in ELIGIBLE_LISTING_EXCHANGES:
        reason = IdentityRefusalReason.INELIGIBLE_EXCHANGE
    elif security.security_type is not SecurityType.COMMON_STOCK:
        reason = IdentityRefusalReason.INELIGIBLE_SECURITY_TYPE
    else:
        reason = None
    if reason is not None:
        return _identity_refusal(
            master,
            historical_ticker=ticker,
            effective_date=effective_date,
            known_at=known_at,
            reason=reason,
        )

    starts = tuple(
        parse_date(value, "mapping.valid_from")
        for value in (issuer.valid_from, security.valid_from, listing.valid_from)
    )
    visible_ends = tuple(
        _visible_valid_to(
            valid_to=item.valid_to,
            valid_to_available_at=item.valid_to_available_at,
            cutoff=cutoff,
        )
        for item in (issuer, security, listing)
    )
    ends = tuple(
        parse_date(value, "mapping.valid_to")
        for value in visible_ends
        if value is not None
    )
    mapping_from = max(starts).isoformat()
    mapping_to = None if not ends else min(ends).isoformat()
    mapping_available_times = [
        parse_utc_timestamp(issuer.available_at, "issuer.available_at"),
        parse_utc_timestamp(security.available_at, "security.available_at"),
        parse_utc_timestamp(listing.available_at, "listing.available_at"),
    ]
    for item, visible_to in zip(
        (issuer, security, listing), visible_ends, strict=True
    ):
        if visible_to is not None and item.valid_to_available_at is not None:
            mapping_available_times.append(
                parse_utc_timestamp(
                    item.valid_to_available_at, "valid_to_available_at"
                )
            )
    for vendor_id in security.vendor_ids:
        vendor_available = parse_utc_timestamp(
            vendor_id.available_at, "vendor.available_at"
        )
        if vendor_available > cutoff:
            continue
        mapping_available_times.append(vendor_available)
        vendor_visible_to = _visible_valid_to(
            valid_to=vendor_id.valid_to,
            valid_to_available_at=vendor_id.valid_to_available_at,
            cutoff=cutoff,
        )
        if vendor_visible_to is not None and vendor_id.valid_to_available_at is not None:
            mapping_available_times.append(
                parse_utc_timestamp(
                    vendor_id.valid_to_available_at, "vendor.valid_to_available_at"
                )
            )
    mapping_available = max(mapping_available_times)
    evidence_sha256 = _mapping_evidence_sha256(
        master, issuer, security, listing, cutoff=cutoff
    )
    return ResolvedSecurityIdentity(
        security_master_id=master.security_master_id,
        security_master_sha256=master.payload_sha256,
        issuer_id=issuer.issuer_id,
        security_id=security.security_id,
        share_class_id=security.share_class_id,
        historical_ticker=listing.ticker,
        exchange=listing.exchange,
        security_type=security.security_type,
        ticker_valid_from=listing.valid_from,
        ticker_valid_to=_visible_valid_to(
            valid_to=listing.valid_to,
            valid_to_available_at=listing.valid_to_available_at,
            cutoff=cutoff,
        ),
        identity_mapping_version_id=f"arv2-idmap-{evidence_sha256[:24]}",
        identity_mapping_valid_from=mapping_from,
        identity_mapping_valid_to=mapping_to,
        identity_mapping_available_at=mapping_available.strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
        identity_mapping_evidence_sha256=evidence_sha256,
    )


def resolve_historical_security(
    master: PointInTimeSecurityMaster,
    *,
    historical_ticker: str,
    effective_date: str,
    known_at: str,
) -> ResolvedSecurityIdentity | IdentityMappingRefusal:
    """Resolve one historical observation without current-ticker/successor logic."""
    revalidate_pit_security_master(master)
    return _resolve_historical_security(
        master,
        _index_security_master(master),
        historical_ticker=historical_ticker,
        effective_date=effective_date,
        known_at=known_at,
    )


@dataclasses.dataclass(frozen=True)
class IdentityResolvedEvent:
    source_event: BenzingaRatingRecord
    identity: ResolvedSecurityIdentity

    def __post_init__(self) -> None:
        if type(self.source_event) is not BenzingaRatingRecord:
            raise SecurityMasterError("identity event source has the wrong type")
        if type(self.identity) is not ResolvedSecurityIdentity:
            raise SecurityMasterError("identity event mapping has the wrong type")
        if (
            self.identity.historical_ticker != self.source_event.historical_ticker
            or not _contains(
                *_interval(
                    self.identity.identity_mapping_valid_from,
                    self.identity.identity_mapping_valid_to,
                    "resolved identity mapping",
                ),
                parse_date(self.source_event.action_date, "action_date"),
            )
            or parse_utc_timestamp(
                self.identity.identity_mapping_available_at,
                "identity_mapping_available_at",
            )
            > parse_utc_timestamp(self.source_event.last_updated_at, "last_updated_at")
        ):
            raise SecurityMasterError("identity mapping is not event-time-bound")

    def to_record(self) -> dict[str, Any]:
        return {
            "provider_event_id": self.source_event.provider_event_id,
            "provider_version_id": self.source_event.provider_version_id,
            "source_locator": self.source_event.source_locator.to_record(),
            "identity": self.identity.to_record(),
        }


@dataclasses.dataclass(frozen=True)
class IdentityRefusedEvent:
    source_event: BenzingaRatingRecord
    refusal: IdentityMappingRefusal

    def __post_init__(self) -> None:
        if type(self.source_event) is not BenzingaRatingRecord:
            raise SecurityMasterError("identity refusal source has the wrong type")
        if type(self.refusal) is not IdentityMappingRefusal:
            raise SecurityMasterError("identity refusal has the wrong type")
        if (
            self.refusal.historical_ticker != self.source_event.historical_ticker
            or self.refusal.effective_date != self.source_event.action_date
            or self.refusal.known_at != self.source_event.last_updated_at
        ):
            raise SecurityMasterError("identity refusal is not event-time-bound")

    def to_record(self) -> dict[str, Any]:
        return {
            "provider_event_id": self.source_event.provider_event_id,
            "provider_version_id": self.source_event.provider_version_id,
            "source_locator": self.source_event.source_locator.to_record(),
            "refusal": self.refusal.to_record(),
        }


@dataclasses.dataclass(frozen=True)
class SecurityIdentityCoverage:
    total_records: int
    mapped_records: int
    refused_records: int
    refusal_counts: tuple[tuple[IdentityRefusalReason, int], ...]

    def __post_init__(self) -> None:
        for name in ("total_records", "mapped_records", "refused_records"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise SecurityMasterError(f"coverage {name} must be a nonnegative integer")
        if self.mapped_records + self.refused_records != self.total_records:
            raise SecurityMasterError("coverage counts are not exhaustive")
        if type(self.refusal_counts) is not tuple or any(
            type(item) is not tuple
            or len(item) != 2
            or not isinstance(item[0], IdentityRefusalReason)
            or type(item[1]) is not int
            or item[1] <= 0
            for item in self.refusal_counts
        ):
            raise SecurityMasterError("coverage refusal counts are invalid")
        if self.refusal_counts != tuple(
            sorted(self.refusal_counts, key=lambda item: item[0].value)
        ) or len({item[0] for item in self.refusal_counts}) != len(
            self.refusal_counts
        ):
            raise SecurityMasterError("coverage refusal counts are not canonical")
        if sum(count for _, count in self.refusal_counts) != self.refused_records:
            raise SecurityMasterError("coverage refusal counts do not sum to refusals")

    def to_record(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "mapped_records": self.mapped_records,
            "refused_records": self.refused_records,
            "refusal_counts": [
                {"reason": reason.value, "count": count}
                for reason, count in self.refusal_counts
            ],
        }


@dataclasses.dataclass(frozen=True)
class SecurityIdentityAudit:
    schema: str
    source_audit_sha256: str
    security_master_id: str
    security_master_sha256: str
    mappings: tuple[IdentityResolvedEvent, ...]
    refusals: tuple[IdentityRefusedEvent, ...]

    def __post_init__(self) -> None:
        if self.schema != SECURITY_IDENTITY_AUDIT_SCHEMA:
            raise SecurityMasterError("unsupported security identity audit schema")
        require_sha256(self.source_audit_sha256, "source_audit_sha256")
        require_identifier(self.security_master_id, "security_master_id")
        require_sha256(self.security_master_sha256, "security_master_sha256")
        if type(self.mappings) is not tuple or any(
            type(item) is not IdentityResolvedEvent for item in self.mappings
        ):
            raise SecurityMasterError("identity mappings must be an exact tuple")
        if type(self.refusals) is not tuple or any(
            type(item) is not IdentityRefusedEvent for item in self.refusals
        ):
            raise SecurityMasterError("identity refusals must be an exact tuple")
        for values, name in ((self.mappings, "mappings"), (self.refusals, "refusals")):
            locators = tuple(item.source_event.source_locator for item in values)
            if locators != tuple(sorted(locators, key=lambda item: item.sort_key)):
                raise SecurityMasterError(f"identity {name} are not source-sorted")
        ids = [item.source_event.provider_event_id for item in self.mappings]
        ids.extend(item.source_event.provider_event_id for item in self.refusals)
        if len(ids) != len(set(ids)):
            raise SecurityMasterError(
                "identity audit has more than one disposition per event"
            )
        for item in self.mappings:
            if (
                item.identity.security_master_id != self.security_master_id
                or item.identity.security_master_sha256
                != self.security_master_sha256
            ):
                raise SecurityMasterError("identity mapping uses another master")
        for item in self.refusals:
            if (
                item.refusal.security_master_id != self.security_master_id
                or item.refusal.security_master_sha256
                != self.security_master_sha256
            ):
                raise SecurityMasterError("identity refusal uses another master")

    @property
    def coverage(self) -> SecurityIdentityCoverage:
        counts = Counter(item.refusal.reason for item in self.refusals)
        return SecurityIdentityCoverage(
            total_records=len(self.mappings) + len(self.refusals),
            mapped_records=len(self.mappings),
            refused_records=len(self.refusals),
            refusal_counts=tuple(sorted(counts.items(), key=lambda item: item[0].value)),
        )

    @property
    def audit_sha256(self) -> str:
        return sha256_bytes(
            canonical_json_bytes(
                {
                    "schema": self.schema,
                    "source_audit_sha256": self.source_audit_sha256,
                    "security_master_id": self.security_master_id,
                    "security_master_sha256": self.security_master_sha256,
                    "mappings": [item.to_record() for item in self.mappings],
                    "refusals": [item.to_record() for item in self.refusals],
                    "coverage": self.coverage.to_record(),
                }
            )
        )


def audit_benzinga_security_identities(
    ingest_audit: BenzingaIngestAudit,
    master: PointInTimeSecurityMaster,
) -> SecurityIdentityAudit:
    """Give every accepted structural rating event one identity disposition."""
    revalidate_benzinga_ingest_audit(ingest_audit)
    revalidate_pit_security_master(master)
    index = _index_security_master(master)
    mappings: list[IdentityResolvedEvent] = []
    refusals: list[IdentityRefusedEvent] = []
    for record in ingest_audit.records:
        decision = _resolve_historical_security(
            master,
            index,
            historical_ticker=record.historical_ticker,
            effective_date=record.action_date,
            known_at=record.last_updated_at,
        )
        if type(decision) is ResolvedSecurityIdentity:
            mappings.append(IdentityResolvedEvent(record, decision))
        else:
            refusals.append(IdentityRefusedEvent(record, decision))
    return SecurityIdentityAudit(
        schema=SECURITY_IDENTITY_AUDIT_SCHEMA,
        source_audit_sha256=ingest_audit.audit_sha256,
        security_master_id=master.security_master_id,
        security_master_sha256=master.payload_sha256,
        mappings=tuple(mappings),
        refusals=tuple(refusals),
    )


def revalidate_security_identity_audit(
    audit: SecurityIdentityAudit,
    *,
    ingest_audit: BenzingaIngestAudit,
    master: PointInTimeSecurityMaster,
) -> SecurityIdentityAudit:
    if type(audit) is not SecurityIdentityAudit:
        raise SecurityMasterError(
            "identity audit authority requires a SecurityIdentityAudit"
        )
    rebuilt = audit_benzinga_security_identities(ingest_audit, master)
    if rebuilt != audit:
        raise SecurityMasterError("security identity audit is not source-derived")
    return audit


@dataclasses.dataclass(frozen=True)
class IdentityResolvedFirmRatingEvent:
    firm_event: FirmNormalizedRatingEvent
    identity: ResolvedSecurityIdentity

    def __post_init__(self) -> None:
        if type(self.firm_event) is not FirmNormalizedRatingEvent:
            raise SecurityMasterError("firm event has the wrong type")
        if type(self.identity) is not ResolvedSecurityIdentity:
            raise SecurityMasterError("firm event identity has the wrong type")
        if self.firm_event.source_event.historical_ticker != self.identity.historical_ticker:
            raise SecurityMasterError("firm event and identity ticker disagree")

    def to_record(self) -> dict[str, Any]:
        event = self.firm_event
        return {
            "provider_event_id": event.source_event.provider_event_id,
            "provider_version_id": event.source_event.provider_version_id,
            "issuer_id": self.identity.issuer_id,
            "security_id": self.identity.security_id,
            "share_class_id": self.identity.share_class_id,
            "identity_mapping_evidence_sha256": (
                self.identity.identity_mapping_evidence_sha256
            ),
            "ontology_id": event.ontology_id,
            "ontology_sha256": event.ontology_sha256,
            "current_score": (
                None
                if event.current_mapping is None
                else [
                    event.current_mapping.score.numerator,
                    event.current_mapping.score.denominator,
                ]
            ),
            "previous_score": (
                None
                if event.previous_mapping is None
                else [
                    event.previous_mapping.score.numerator,
                    event.previous_mapping.score.denominator,
                ]
            ),
            "rating_change": (
                None
                if event.rating_change is None
                else [event.rating_change.numerator, event.rating_change.denominator]
            ),
        }


@dataclasses.dataclass(frozen=True)
class IdentityResolvedFirmRefusal:
    source_event: BenzingaRatingRecord
    stage: CombinedRefusalStage
    reason: str

    def __post_init__(self) -> None:
        if type(self.source_event) is not BenzingaRatingRecord:
            raise SecurityMasterError("combined refusal source has the wrong type")
        if not isinstance(self.stage, CombinedRefusalStage):
            raise SecurityMasterError("combined refusal stage has the wrong type")
        require_identifier(self.reason, "combined refusal reason")

    def to_record(self) -> dict[str, Any]:
        return {
            "provider_event_id": self.source_event.provider_event_id,
            "provider_version_id": self.source_event.provider_version_id,
            "stage": self.stage.value,
            "reason": self.reason,
        }


@dataclasses.dataclass(frozen=True)
class IdentityResolvedFirmRatingResult:
    schema: str
    source_audit_sha256: str
    firm_result_sha256: str
    identity_audit_sha256: str
    ontology_id: str
    ontology_sha256: str
    security_master_id: str
    security_master_sha256: str
    events: tuple[IdentityResolvedFirmRatingEvent, ...]
    refusals: tuple[IdentityResolvedFirmRefusal, ...]

    def __post_init__(self) -> None:
        if self.schema != IDENTITY_RESOLVED_FIRM_RESULT_SCHEMA:
            raise SecurityMasterError("unsupported identity/firm result schema")
        for name in (
            "source_audit_sha256",
            "firm_result_sha256",
            "identity_audit_sha256",
            "ontology_sha256",
            "security_master_sha256",
        ):
            require_sha256(getattr(self, name), name)
        require_identifier(self.ontology_id, "ontology_id")
        require_identifier(self.security_master_id, "security_master_id")
        if type(self.events) is not tuple or any(
            type(item) is not IdentityResolvedFirmRatingEvent for item in self.events
        ):
            raise SecurityMasterError("combined events must be an exact tuple")
        if type(self.refusals) is not tuple or any(
            type(item) is not IdentityResolvedFirmRefusal for item in self.refusals
        ):
            raise SecurityMasterError("combined refusals must be an exact tuple")
        ids = [item.firm_event.source_event.provider_event_id for item in self.events]
        ids.extend(item.source_event.provider_event_id for item in self.refusals)
        if len(ids) != len(set(ids)):
            raise SecurityMasterError(
                "combined result has more than one disposition per event"
            )

    @property
    def result_sha256(self) -> str:
        return sha256_bytes(
            canonical_json_bytes(
                {
                    "schema": self.schema,
                    "source_audit_sha256": self.source_audit_sha256,
                    "firm_result_sha256": self.firm_result_sha256,
                    "identity_audit_sha256": self.identity_audit_sha256,
                    "ontology_id": self.ontology_id,
                    "ontology_sha256": self.ontology_sha256,
                    "security_master_id": self.security_master_id,
                    "security_master_sha256": self.security_master_sha256,
                    "events": [item.to_record() for item in self.events],
                    "refusals": [item.to_record() for item in self.refusals],
                }
            )
        )


def _firm_result_sha256(result: FirmRatingNormalizationResult) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": result.schema,
                "source_audit_sha256": result.source_audit_sha256,
                "ontology_id": result.ontology_id,
                "ontology_sha256": result.ontology_sha256,
                "events": [
                    {
                        "provider_event_id": item.source_event.provider_event_id,
                        "provider_version_id": item.source_event.provider_version_id,
                        "rating_change": (
                            None
                            if item.rating_change is None
                            else [
                                item.rating_change.numerator,
                                item.rating_change.denominator,
                            ]
                        ),
                    }
                    for item in result.events
                ],
                "refusals": [
                    {
                        "provider_event_id": item.source_event.provider_event_id,
                        "provider_version_id": item.source_event.provider_version_id,
                        "reason": item.reason.value,
                    }
                    for item in result.refusals
                ],
            }
        )
    )


def bind_firm_normalization_to_security_identities(
    firm_result: FirmRatingNormalizationResult,
    identity_audit: SecurityIdentityAudit,
    *,
    ingest_audit: BenzingaIngestAudit,
    ontology: ReviewedFirmRatingOntology,
    master: PointInTimeSecurityMaster,
) -> IdentityResolvedFirmRatingResult:
    """Bind exact ARV2-1 rational mappings to permanent security identities."""
    revalidate_firm_rating_ontology(ontology)
    revalidate_pit_security_master(master)
    revalidate_firm_rating_normalization(
        firm_result, audit=ingest_audit, ontology=ontology
    )
    revalidate_security_identity_audit(
        identity_audit, ingest_audit=ingest_audit, master=master
    )
    identity_by_id = {
        item.source_event.provider_event_id: item.identity
        for item in identity_audit.mappings
    }
    identity_refusal_by_id = {
        item.source_event.provider_event_id: item.refusal
        for item in identity_audit.refusals
    }
    firm_by_id = {
        item.source_event.provider_event_id: item for item in firm_result.events
    }
    firm_refusal_by_id = {
        item.source_event.provider_event_id: item for item in firm_result.refusals
    }
    events: list[IdentityResolvedFirmRatingEvent] = []
    refusals: list[IdentityResolvedFirmRefusal] = []
    for source_event in ingest_audit.records:
        event_id = source_event.provider_event_id
        identity_refusal = identity_refusal_by_id.get(event_id)
        if identity_refusal is not None:
            refusals.append(
                IdentityResolvedFirmRefusal(
                    source_event,
                    CombinedRefusalStage.IDENTITY,
                    identity_refusal.reason.value,
                )
            )
            continue
        firm_refusal: FirmNormalizationRefusal | None = firm_refusal_by_id.get(event_id)
        if firm_refusal is not None:
            refusals.append(
                IdentityResolvedFirmRefusal(
                    source_event,
                    CombinedRefusalStage.FIRM_ONTOLOGY,
                    firm_refusal.reason.value,
                )
            )
            continue
        firm_event: FirmNormalizedRatingEvent | None = firm_by_id.get(event_id)
        identity = identity_by_id.get(event_id)
        if firm_event is None or identity is None:
            raise SecurityMasterError("combined source event lost a terminal disposition")
        events.append(IdentityResolvedFirmRatingEvent(firm_event, identity))
    return IdentityResolvedFirmRatingResult(
        schema=IDENTITY_RESOLVED_FIRM_RESULT_SCHEMA,
        source_audit_sha256=ingest_audit.audit_sha256,
        firm_result_sha256=_firm_result_sha256(firm_result),
        identity_audit_sha256=identity_audit.audit_sha256,
        ontology_id=ontology.ontology_id,
        ontology_sha256=ontology.payload_sha256,
        security_master_id=master.security_master_id,
        security_master_sha256=master.payload_sha256,
        events=tuple(events),
        refusals=tuple(refusals),
    )


def revalidate_identity_resolved_firm_rating_result(
    result: IdentityResolvedFirmRatingResult,
    *,
    firm_result: FirmRatingNormalizationResult,
    identity_audit: SecurityIdentityAudit,
    ingest_audit: BenzingaIngestAudit,
    ontology: ReviewedFirmRatingOntology,
    master: PointInTimeSecurityMaster,
) -> IdentityResolvedFirmRatingResult:
    if type(result) is not IdentityResolvedFirmRatingResult:
        raise SecurityMasterError(
            "combined authority requires an IdentityResolvedFirmRatingResult"
        )
    rebuilt = bind_firm_normalization_to_security_identities(
        firm_result,
        identity_audit,
        ingest_audit=ingest_audit,
        ontology=ontology,
        master=master,
    )
    if rebuilt != result:
        raise SecurityMasterError(
            "identity-resolved firm result is not source-derived"
        )
    return result


@dataclasses.dataclass(frozen=True)
class TerminalOutcomeRequirement:
    schema: str
    security_master_id: str
    security_master_sha256: str
    lineage_event_id: str
    kind: LineageKind
    security_id: str
    successor_security_id: str | None
    effective_date: str
    available_at: str
    evidence_id: str
    evidence_sha256: str
    missing_policy: str

    def __post_init__(self) -> None:
        if self.schema != TERMINAL_OUTCOME_REQUIREMENT_SCHEMA:
            raise SecurityMasterError("unsupported terminal requirement schema")
        require_identifier(self.security_master_id, "security_master_id")
        require_sha256(self.security_master_sha256, "security_master_sha256")
        require_identifier(self.lineage_event_id, "lineage_event_id")
        if self.kind not in {LineageKind.MERGER, LineageKind.DELISTING}:
            raise SecurityMasterError("terminal requirement kind is not terminal")
        require_identifier(self.security_id, "security_id")
        if self.successor_security_id is not None:
            require_identifier(self.successor_security_id, "successor_security_id")
        parse_date(self.effective_date, "effective_date")
        parse_utc_timestamp(self.available_at, "available_at")
        require_identifier(self.evidence_id, "evidence_id")
        require_sha256(self.evidence_sha256, "evidence_sha256")
        if self.missing_policy != "named_refusal_never_drop":
            raise SecurityMasterError("terminal requirement missing policy is unsafe")


def terminal_outcome_requirements(
    master: PointInTimeSecurityMaster,
    *,
    start_date: str,
    end_date: str,
    known_at: str,
) -> tuple[TerminalOutcomeRequirement, ...]:
    """Inventory required terminal returns without loading any outcome value."""
    revalidate_pit_security_master(master)
    start = parse_date(start_date, "start_date")
    end = parse_date(end_date, "end_date")
    if end <= start:
        raise SecurityMasterError("terminal requirement interval is empty/reversed")
    cutoff = parse_utc_timestamp(known_at, "known_at")
    requirements: list[TerminalOutcomeRequirement] = []
    for event in master.lineage_events:
        effective = parse_date(event.effective_date, "lineage.effective_date")
        available = parse_utc_timestamp(event.available_at, "lineage.available_at")
        if event.kind not in {LineageKind.MERGER, LineageKind.DELISTING} or not (
            start <= effective < end
        ):
            continue
        if available > cutoff:
            raise SecurityMasterError(
                "terminal outcome requirement is unavailable by known_at"
            )
        requirements.append(
            TerminalOutcomeRequirement(
                schema=TERMINAL_OUTCOME_REQUIREMENT_SCHEMA,
                security_master_id=master.security_master_id,
                security_master_sha256=master.payload_sha256,
                lineage_event_id=event.lineage_event_id,
                kind=event.kind,
                security_id=event.security_id,
                successor_security_id=event.successor_security_id,
                effective_date=event.effective_date,
                available_at=event.available_at,
                evidence_id=event.evidence_id,
                evidence_sha256=event.evidence_sha256,
                missing_policy="named_refusal_never_drop",
            )
        )
    return tuple(requirements)


def revalidate_terminal_outcome_requirements(
    requirements: tuple[TerminalOutcomeRequirement, ...],
    *,
    master: PointInTimeSecurityMaster,
    start_date: str,
    end_date: str,
    known_at: str,
) -> tuple[TerminalOutcomeRequirement, ...]:
    if type(requirements) is not tuple or any(
        type(item) is not TerminalOutcomeRequirement for item in requirements
    ):
        raise SecurityMasterError(
            "terminal requirements must be an exact tuple of derived records"
        )
    rebuilt = terminal_outcome_requirements(
        master,
        start_date=start_date,
        end_date=end_date,
        known_at=known_at,
    )
    if rebuilt != requirements:
        raise SecurityMasterError("terminal requirements are not source-derived")
    return requirements
