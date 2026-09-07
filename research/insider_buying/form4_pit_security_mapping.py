"""Offline, zero-authority point-in-time security mapping for bounded IB-2C.

The factory consumes one exact, process-sealed IB-2B SEC-entity grouping plus
caller-supplied security, exact-title, and ticker intervals.  Security/title
validity is evaluated on the transaction date.  The as-filed issuer symbol is
evaluated on the filing's America/New_York acceptance date.  Only facts and
interval closures available by the exact filing-acceptance instant influence
resolution; an unavailable closure is treated as still open at that cutoff.

The output is exhaustive and structural.  It resolves no official security
master, grants no canonical or ordinary-equity status, accesses no provider or
outcome, and exposes no QC, execution, deployment, or trading authority.
"""
from __future__ import annotations

import re
import threading
import weakref
from dataclasses import InitVar, dataclass, fields
from datetime import date, datetime, timezone
from enum import Enum
from zoneinfo import ZoneInfo

from data.hashing import hash_payload
from research.insider_buying.form4_observed_identity_inventory import (
    MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
    Form4ObservedIdentityDisposition,
)
from research.insider_buying.form4_provisional_disposition_report import (
    Form4ProvisionalDisposition,
)
from research.insider_buying.form4_sec_entity_grouping import (
    Form4OwnerAttributionOutcome,
    Form4SecEntityGrouping,
    _grouping_provenance_fingerprint,
    _grouping_provenance_payload,
    _is_factory_created_sec_entity_grouping,
    _matches_factory_created_sec_entity_grouping_fingerprint,
)


FORM4_PIT_SECURITY_MAPPING_VERSION = (
    "INSETF-IB2C-FORM4-PIT-SECURITY-MAPPING-v1"
)
MAX_FORM4_PIT_SECURITY_RECORDS = 4_096
MAX_FORM4_SECURITY_TITLE_INTERVALS = 16_384
MAX_FORM4_TICKER_INTERVALS = 16_384
MAX_FORM4_PIT_SECURITY_MAPPING_TEXT_CHARACTERS = 64_000_000
MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_NODES = 4_000_000
MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_DEPTH = 32
MAX_FORM4_PIT_SECURITY_MAPPING_RESOLUTION_OPERATIONS = 5_000_000

_CIK_RE = re.compile(r"^[0-9]{10}$")
_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,31}$")
_VENUE_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,15}$")
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_MAPPING_ID_RE = re.compile(
    r"^form4-pit-security-mapping-(?P<hash_prefix>[0-9a-f]{16})$"
)
_EASTERN = ZoneInfo("America/New_York")

_ROW_FACTORY_TOKEN = object()
_IDENTITY_FACTORY_TOKEN = object()
_MAPPING_FACTORY_TOKEN = object()


class Form4PitSecurityMappingError(ValueError):
    """The bounded IB-2C mapping contract failed closed."""


class Form4SecurityClass(str, Enum):
    """Caller-supplied structural class label; never canonical eligibility."""

    COMMON_STOCK = "common_stock"
    COMMON_SHARES = "common_shares"
    ORDINARY_SHARES = "ordinary_shares"
    AMERICAN_DEPOSITARY_RECEIPT = "american_depositary_receipt"
    PREFERRED_STOCK = "preferred_stock"
    OTHER = "other"


class Form4SecurityTitleMappingKind(str, Enum):
    """How one exact, dated title mapping entered the supplied reference."""

    DETERMINISTIC_EXACT = "deterministic_exact"
    MANUAL_EXCEPTION = "manual_exception"


class Form4PitSecurityMappingOutcome(str, Enum):
    """Named structural resolution or quarantine outcome for one transaction."""

    MAPPED_STRUCTURALLY = "mapped_structurally"
    MISSING_TRANSACTION_DATE_QUARANTINED = (
        "missing_transaction_date_quarantined"
    )
    MISSING_SECURITY_TITLE_QUARANTINED = (
        "missing_security_title_quarantined"
    )
    MISSING_ISSUER_SYMBOL_QUARANTINED = (
        "missing_issuer_symbol_quarantined"
    )
    TRANSACTION_AFTER_FILING_DATE_QUARANTINED = (
        "transaction_after_filing_date_quarantined"
    )
    NO_ACTIVE_SECURITY_TITLE_MAPPING_QUARANTINED = (
        "no_active_security_title_mapping_quarantined"
    )
    AMBIGUOUS_SECURITY_TITLE_MAPPING_QUARANTINED = (
        "ambiguous_security_title_mapping_quarantined"
    )
    NO_ACTIVE_TICKER_QUARANTINED = "no_active_ticker_quarantined"
    AMBIGUOUS_TICKER_QUARANTINED = "ambiguous_ticker_quarantined"
    ISSUER_SYMBOL_MISMATCH_QUARANTINED = (
        "issuer_symbol_mismatch_quarantined"
    )


def _required_text(value: object, *, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 4_096
    ):
        raise Form4PitSecurityMappingError(
            f"REFUSED: {label} must be bounded exact non-empty text"
        )
    return value


def _optional_text(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, label=label)


def _sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise Form4PitSecurityMappingError(
            f"REFUSED: {label} must be lowercase SHA-256"
        )
    return value


def _opaque_id(value: object, *, label: str) -> str:
    if type(value) is not str or _OPAQUE_ID_RE.fullmatch(value) is None:
        raise Form4PitSecurityMappingError(
            f"REFUSED: {label} must be a bounded opaque ID"
        )
    return value


def _cik(value: object, *, label: str) -> str:
    if type(value) is not str or _CIK_RE.fullmatch(value) is None:
        raise Form4PitSecurityMappingError(
            f"REFUSED: {label} must be a ten-digit SEC CIK"
        )
    return value


def _accession(value: object, *, label: str) -> str:
    if type(value) is not str or _ACCESSION_RE.fullmatch(value) is None:
        raise Form4PitSecurityMappingError(
            f"REFUSED: {label} must be a canonical accession"
        )
    return value


def _canonical_utc(value: object, *, label: str) -> datetime:
    if type(value) is not str:
        raise Form4PitSecurityMappingError(
            f"REFUSED: {label} must be canonical UTC text"
        )
    try:
        parsed = datetime.fromisoformat(value)
        canonical = parsed.astimezone(timezone.utc).isoformat(
            timespec="seconds"
        )
    except (OverflowError, TypeError, ValueError) as exc:
        raise Form4PitSecurityMappingError(
            f"REFUSED: {label} must be canonical UTC text"
        ) from exc
    if (
        parsed.utcoffset() is None
        or parsed.microsecond != 0
        or canonical != value
    ):
        raise Form4PitSecurityMappingError(
            f"REFUSED: {label} must be canonical UTC text"
        )
    return parsed


def _exact_date(value: object, *, label: str) -> date:
    if type(value) is not date:
        raise Form4PitSecurityMappingError(
            f"REFUSED: {label} must be an exact date"
        )
    return value


def _validate_interval(
    *,
    valid_from: object,
    valid_to: object,
    available_at_utc: object,
    valid_to_available_at_utc: object,
    valid_to_evidence_id: object,
    valid_to_evidence_sha256: object,
    label: str,
) -> None:
    start = _exact_date(valid_from, label=f"{label} valid-from")
    if valid_to is not None:
        end = _exact_date(valid_to, label=f"{label} valid-to")
        if end <= start:
            raise Form4PitSecurityMappingError(
                f"REFUSED: {label} interval must be non-empty and half-open"
            )
    base_available = _canonical_utc(
        available_at_utc,
        label=f"{label} availability",
    )
    closure_values = (
        valid_to_available_at_utc,
        valid_to_evidence_id,
        valid_to_evidence_sha256,
    )
    if (
        valid_to is None
        and any(value is not None for value in closure_values)
    ) or (
        valid_to is not None
        and any(value is None for value in closure_values)
    ):
        raise Form4PitSecurityMappingError(
            f"REFUSED: {label} closure evidence is inconsistent"
        )
    if valid_to_available_at_utc is not None:
        closure_available = _canonical_utc(
            valid_to_available_at_utc,
            label=f"{label} closure availability",
        )
        if closure_available < base_available:
            raise Form4PitSecurityMappingError(
                f"REFUSED: {label} closure predates base availability"
            )
        _opaque_id(
            valid_to_evidence_id,
            label=f"{label} closure evidence ID",
        )
        _sha256(
            valid_to_evidence_sha256,
            label=f"{label} closure evidence hash",
        )


@dataclass(frozen=True)
class Form4PitSecurityRecord:
    """One supplied permanent-security/share-class validity interval."""

    security_id: str
    share_class_id: str
    issuer_cik: str
    security_class_normalized: Form4SecurityClass
    valid_from: date
    valid_to: date | None
    available_at_utc: str
    valid_to_available_at_utc: str | None
    valid_to_evidence_id: str | None
    valid_to_evidence_sha256: str | None
    evidence_id: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        _opaque_id(self.security_id, label="security ID")
        _opaque_id(self.share_class_id, label="share-class ID")
        _cik(self.issuer_cik, label="security issuer CIK")
        if type(self.security_class_normalized) is not Form4SecurityClass:
            raise Form4PitSecurityMappingError(
                "REFUSED: security class must be an exact declared enum"
            )
        _validate_interval(
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            available_at_utc=self.available_at_utc,
            valid_to_available_at_utc=self.valid_to_available_at_utc,
            valid_to_evidence_id=self.valid_to_evidence_id,
            valid_to_evidence_sha256=self.valid_to_evidence_sha256,
            label="security",
        )
        _opaque_id(self.evidence_id, label="security evidence ID")
        _sha256(self.evidence_sha256, label="security evidence hash")

    @property
    def security_record_id(self) -> str:
        return hash_payload(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "issuer_cik": self.issuer_cik,
            "security_class_normalized": self.security_class_normalized.value,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": (
                None if self.valid_to is None else self.valid_to.isoformat()
            ),
            "available_at_utc": self.available_at_utc,
            "valid_to_available_at_utc": self.valid_to_available_at_utc,
            "valid_to_evidence_id": self.valid_to_evidence_id,
            "valid_to_evidence_sha256": self.valid_to_evidence_sha256,
            "evidence_id": self.evidence_id,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True)
class Form4SecurityTitleInterval:
    """One exact raw Form 4 title to security/share-class interval."""

    security_id: str
    share_class_id: str
    security_title_raw: str
    mapping_kind: Form4SecurityTitleMappingKind
    valid_from: date
    valid_to: date | None
    available_at_utc: str
    valid_to_available_at_utc: str | None
    valid_to_evidence_id: str | None
    valid_to_evidence_sha256: str | None
    evidence_id: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        _opaque_id(self.security_id, label="title security ID")
        _opaque_id(self.share_class_id, label="title share-class ID")
        _required_text(self.security_title_raw, label="raw security title")
        if type(self.mapping_kind) is not Form4SecurityTitleMappingKind:
            raise Form4PitSecurityMappingError(
                "REFUSED: title mapping kind must be an exact declared enum"
            )
        _validate_interval(
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            available_at_utc=self.available_at_utc,
            valid_to_available_at_utc=self.valid_to_available_at_utc,
            valid_to_evidence_id=self.valid_to_evidence_id,
            valid_to_evidence_sha256=self.valid_to_evidence_sha256,
            label="title",
        )
        _opaque_id(self.evidence_id, label="title evidence ID")
        _sha256(self.evidence_sha256, label="title evidence hash")

    @property
    def title_interval_id(self) -> str:
        return hash_payload(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "security_title_raw": self.security_title_raw,
            "mapping_kind": self.mapping_kind.value,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": (
                None if self.valid_to is None else self.valid_to.isoformat()
            ),
            "available_at_utc": self.available_at_utc,
            "valid_to_available_at_utc": self.valid_to_available_at_utc,
            "valid_to_evidence_id": self.valid_to_evidence_id,
            "valid_to_evidence_sha256": self.valid_to_evidence_sha256,
            "evidence_id": self.evidence_id,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True)
class Form4TickerInterval:
    """One supplied security-to-ticker/listing interval."""

    security_id: str
    ticker: str
    exchange: str
    country: str
    valid_from: date
    valid_to: date | None
    available_at_utc: str
    valid_to_available_at_utc: str | None
    valid_to_evidence_id: str | None
    valid_to_evidence_sha256: str | None
    evidence_id: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        _opaque_id(self.security_id, label="ticker security ID")
        if type(self.ticker) is not str or _TICKER_RE.fullmatch(self.ticker) is None:
            raise Form4PitSecurityMappingError(
                "REFUSED: ticker must be bounded canonical uppercase text"
            )
        if (
            type(self.exchange) is not str
            or _VENUE_RE.fullmatch(self.exchange) is None
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: exchange must be bounded canonical uppercase text"
            )
        if (
            type(self.country) is not str
            or _COUNTRY_RE.fullmatch(self.country) is None
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: country must be ISO-style uppercase text"
            )
        _validate_interval(
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            available_at_utc=self.available_at_utc,
            valid_to_available_at_utc=self.valid_to_available_at_utc,
            valid_to_evidence_id=self.valid_to_evidence_id,
            valid_to_evidence_sha256=self.valid_to_evidence_sha256,
            label="ticker",
        )
        _opaque_id(self.evidence_id, label="ticker evidence ID")
        _sha256(self.evidence_sha256, label="ticker evidence hash")

    @property
    def ticker_interval_id(self) -> str:
        return hash_payload(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "ticker": self.ticker,
            "exchange": self.exchange,
            "country": self.country,
            "valid_from": self.valid_from.isoformat(),
            "valid_to": (
                None if self.valid_to is None else self.valid_to.isoformat()
            ),
            "available_at_utc": self.available_at_utc,
            "valid_to_available_at_utc": self.valid_to_available_at_utc,
            "valid_to_evidence_id": self.valid_to_evidence_id,
            "valid_to_evidence_sha256": self.valid_to_evidence_sha256,
            "evidence_id": self.evidence_id,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True)
class Form4PitSecurityMappingRow:
    """Exactly one structural mapping disposition for one IB-2B transaction."""

    accession_number: str
    source_sha256: str
    row_index: int
    event_id: str
    filing_observation_id: str
    upstream_transaction_observation_id: str
    upstream_report_row_id: str
    transaction_payload_hash: str
    transaction_attribution_id: str
    issuer_candidate_id: str
    issuer_cik: str
    accepted_at_utc: str
    document_type: str
    original_accession: str
    amends_accession: str | None
    issuer_observation_id: str
    issuer_symbol_raw: str | None
    security_title_raw: str | None
    transaction_date: date | None
    upstream_disposition: Form4ProvisionalDisposition
    identity_disposition: Form4ObservedIdentityDisposition
    attributed_owner_cik: str | None
    attributed_owner_candidate_id: str | None
    owner_attribution_outcomes: tuple[Form4OwnerAttributionOutcome, ...]
    resolution_outcomes: tuple[Form4PitSecurityMappingOutcome, ...]
    security_id: str | None
    share_class_id: str | None
    security_class_normalized: Form4SecurityClass | None
    ticker: str | None
    exchange: str | None
    country: str | None
    security_interval_asof_id: str | None
    title_interval_asof_id: str | None
    ticker_interval_asof_id: str | None
    title_mapping_kind: Form4SecurityTitleMappingKind | None
    point_in_time_mapping_structurally_resolved: bool
    point_in_time_issuer_identity_verified: bool
    point_in_time_reporting_owner_identity_verified: bool
    point_in_time_security_identity_verified: bool
    point_in_time_transaction_identity_verified: bool
    ordinary_equity_classification_verified: bool
    canonical_filter_authorized: bool
    lot_aggregation_authorized: bool
    outcomes_authorized: bool
    qc_execution_authorized: bool
    deployment_authorized: bool
    trading_authorized: bool
    authorized_outcome_looks: int
    consumed_outcome_looks: int
    mapping_row_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _ROW_FACTORY_TOKEN:
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping row must be factory-created"
            )
        _accession(self.accession_number, label="row accession")
        _sha256(self.source_sha256, label="row source hash")
        if type(self.row_index) is not int or self.row_index < 0:
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping row index is invalid"
            )
        for label, value in (
            ("event ID", self.event_id),
            ("filing observation ID", self.filing_observation_id),
            (
                "upstream transaction observation ID",
                self.upstream_transaction_observation_id,
            ),
            ("upstream report row ID", self.upstream_report_row_id),
            ("transaction payload hash", self.transaction_payload_hash),
            ("transaction attribution ID", self.transaction_attribution_id),
            ("issuer candidate ID", self.issuer_candidate_id),
        ):
            _sha256(value, label=label)
        _cik(self.issuer_cik, label="row issuer CIK")
        _canonical_utc(self.accepted_at_utc, label="row acceptance")
        if type(self.document_type) is not str or self.document_type not in {
            "4",
            "4/A",
        }:
            raise Form4PitSecurityMappingError(
                "REFUSED: row document type is invalid"
            )
        _accession(self.original_accession, label="row original accession")
        if self.amends_accession is not None:
            _accession(self.amends_accession, label="row amended accession")
        if self.document_type == "4":
            lineage_valid = (
                self.amends_accession is None
                and self.original_accession == self.accession_number
            )
        else:
            lineage_valid = (
                self.amends_accession is not None
                and self.original_accession == self.amends_accession
                and self.original_accession != self.accession_number
            )
        if not lineage_valid:
            raise Form4PitSecurityMappingError(
                "REFUSED: row amendment lineage is invalid"
            )
        _sha256(self.issuer_observation_id, label="issuer observation ID")
        _optional_text(self.issuer_symbol_raw, label="row issuer symbol")
        _optional_text(self.security_title_raw, label="row security title")
        if self.transaction_date is not None:
            _exact_date(self.transaction_date, label="row transaction date")
        if (
            type(self.upstream_disposition) is not Form4ProvisionalDisposition
            or type(self.identity_disposition)
            is not Form4ObservedIdentityDisposition
            or type(self.owner_attribution_outcomes) is not tuple
            or not self.owner_attribution_outcomes
            or any(
                type(item) is not Form4OwnerAttributionOutcome
                for item in self.owner_attribution_outcomes
            )
            or len(set(self.owner_attribution_outcomes))
            != len(self.owner_attribution_outcomes)
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping row upstream dispositions are invalid"
            )
        is_owner_attributed = self.owner_attribution_outcomes == (
            Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,
        )
        if is_owner_attributed:
            _cik(self.attributed_owner_cik, label="attributed owner CIK")
            _sha256(
                self.attributed_owner_candidate_id,
                label="attributed owner candidate ID",
            )
        elif (
            self.attributed_owner_cik is not None
            or self.attributed_owner_candidate_id is not None
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: upstream owner quarantine was promoted"
            )
        if (
            type(self.resolution_outcomes) is not tuple
            or not self.resolution_outcomes
            or any(
                type(item) is not Form4PitSecurityMappingOutcome
                for item in self.resolution_outcomes
            )
            or len(set(self.resolution_outcomes)) != len(self.resolution_outcomes)
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping row outcomes are invalid"
            )
        mapped = self.resolution_outcomes == (
            Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY,
        )
        resolved_fields = (
            self.security_id,
            self.share_class_id,
            self.security_class_normalized,
            self.ticker,
            self.exchange,
            self.country,
            self.security_interval_asof_id,
            self.title_interval_asof_id,
            self.ticker_interval_asof_id,
            self.title_mapping_kind,
        )
        if mapped:
            if (
                any(value is None for value in resolved_fields)
                or self.point_in_time_mapping_structurally_resolved is not True
                or type(self.security_class_normalized) is not Form4SecurityClass
                or type(self.title_mapping_kind)
                is not Form4SecurityTitleMappingKind
            ):
                raise Form4PitSecurityMappingError(
                    "REFUSED: mapped row lacks a complete structural mapping"
                )
            _opaque_id(self.security_id, label="mapped security ID")
            _opaque_id(self.share_class_id, label="mapped share-class ID")
            for label, value in (
                ("security as-of interval ID", self.security_interval_asof_id),
                ("title as-of interval ID", self.title_interval_asof_id),
                ("ticker as-of interval ID", self.ticker_interval_asof_id),
            ):
                _sha256(value, label=label)
        elif (
            any(value is not None for value in resolved_fields)
            or self.point_in_time_mapping_structurally_resolved is not False
            or Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY
            in self.resolution_outcomes
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: quarantined row carries a partial mapping"
            )
        authority = (
            self.point_in_time_issuer_identity_verified,
            self.point_in_time_reporting_owner_identity_verified,
            self.point_in_time_security_identity_verified,
            self.point_in_time_transaction_identity_verified,
            self.ordinary_equity_classification_verified,
            self.canonical_filter_authorized,
            self.lot_aggregation_authorized,
            self.outcomes_authorized,
            self.qc_execution_authorized,
            self.deployment_authorized,
            self.trading_authorized,
        )
        if (
            any(value is not False for value in authority)
            or type(self.authorized_outcome_looks) is not int
            or self.authorized_outcome_looks != 0
            or type(self.consumed_outcome_looks) is not int
            or self.consumed_outcome_looks != 0
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping row claims downstream authority"
            )
        _sha256(self.mapping_row_id, label="mapping row ID")
        if self.mapping_row_id != hash_payload(_mapping_row_payload(self)):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping row ID is invalid"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            **_mapping_row_payload(self),
            "mapping_row_id": self.mapping_row_id,
        }


def _mapping_row_payload(
    row: Form4PitSecurityMappingRow,
) -> dict[str, object]:
    return {
        "accession_number": row.accession_number,
        "source_sha256": row.source_sha256,
        "row_index": row.row_index,
        "event_id": row.event_id,
        "filing_observation_id": row.filing_observation_id,
        "upstream_transaction_observation_id": (
            row.upstream_transaction_observation_id
        ),
        "upstream_report_row_id": row.upstream_report_row_id,
        "transaction_payload_hash": row.transaction_payload_hash,
        "transaction_attribution_id": row.transaction_attribution_id,
        "issuer_candidate_id": row.issuer_candidate_id,
        "issuer_cik": row.issuer_cik,
        "accepted_at_utc": row.accepted_at_utc,
        "document_type": row.document_type,
        "original_accession": row.original_accession,
        "amends_accession": row.amends_accession,
        "issuer_observation_id": row.issuer_observation_id,
        "issuer_symbol_raw": row.issuer_symbol_raw,
        "security_title_raw": row.security_title_raw,
        "transaction_date": (
            None
            if row.transaction_date is None
            else row.transaction_date.isoformat()
        ),
        "upstream_disposition": row.upstream_disposition.value,
        "identity_disposition": row.identity_disposition.value,
        "attributed_owner_cik": row.attributed_owner_cik,
        "attributed_owner_candidate_id": row.attributed_owner_candidate_id,
        "owner_attribution_outcomes": [
            item.value for item in row.owner_attribution_outcomes
        ],
        "resolution_outcomes": [
            item.value for item in row.resolution_outcomes
        ],
        "security_id": row.security_id,
        "share_class_id": row.share_class_id,
        "security_class_normalized": (
            None
            if row.security_class_normalized is None
            else row.security_class_normalized.value
        ),
        "ticker": row.ticker,
        "exchange": row.exchange,
        "country": row.country,
        "security_interval_asof_id": row.security_interval_asof_id,
        "title_interval_asof_id": row.title_interval_asof_id,
        "ticker_interval_asof_id": row.ticker_interval_asof_id,
        "title_mapping_kind": (
            None
            if row.title_mapping_kind is None
            else row.title_mapping_kind.value
        ),
        "point_in_time_mapping_structurally_resolved": (
            row.point_in_time_mapping_structurally_resolved
        ),
        "point_in_time_issuer_identity_verified": False,
        "point_in_time_reporting_owner_identity_verified": False,
        "point_in_time_security_identity_verified": False,
        "point_in_time_transaction_identity_verified": False,
        "ordinary_equity_classification_verified": False,
        "canonical_filter_authorized": False,
        "lot_aggregation_authorized": False,
        "outcomes_authorized": False,
        "qc_execution_authorized": False,
        "deployment_authorized": False,
        "trading_authorized": False,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }


@dataclass(frozen=True)
class Form4PitSecurityMappingIdentity:
    """Hash-bound identity for one exhaustive IB-2C result."""

    contract_version: str
    builder_git_commit: str
    upstream_grouping_id: str
    upstream_grouping_identity_hash: str
    upstream_grouping_fingerprint: str
    reference_id: str
    reference_version: str
    reference_sha256: str
    security_record_inventory_hash: str
    title_interval_inventory_hash: str
    ticker_interval_inventory_hash: str
    mapping_row_inventory_hash: str
    security_record_count: int
    title_interval_count: int
    ticker_interval_count: int
    mapping_row_count: int
    structurally_mapped_count: int
    security_mapping_quarantined_count: int
    manual_exception_resolution_count: int
    official_profile_compatibility_verified: bool
    official_amendment_link_verified: bool
    complete_amendment_coverage_verified: bool
    official_security_master_compatibility_verified: bool
    point_in_time_issuer_identity_verified: bool
    point_in_time_reporting_owner_identity_verified: bool
    point_in_time_security_identity_verified: bool
    point_in_time_transaction_identity_verified: bool
    ordinary_equity_classification_verified: bool
    canonical_filter_authorized: bool
    lot_aggregation_authorized: bool
    sec_access_authorized: bool
    provider_access_authorized: bool
    outcomes_authorized: bool
    qc_execution_authorized: bool
    deployment_authorized: bool
    trading_authorized: bool
    authorized_outcome_looks: int
    consumed_outcome_looks: int
    mapping_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _IDENTITY_FACTORY_TOKEN:
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping identity must be factory-created"
            )
        if (
            type(self.contract_version) is not str
            or self.contract_version != FORM4_PIT_SECURITY_MAPPING_VERSION
            or type(self.builder_git_commit) is not str
            or _GIT_COMMIT_RE.fullmatch(self.builder_git_commit) is None
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping version or builder commit is invalid"
            )
        _required_text(self.upstream_grouping_id, label="upstream grouping ID")
        _opaque_id(self.reference_id, label="reference ID")
        _opaque_id(self.reference_version, label="reference version")
        for label, value in (
            ("upstream grouping identity hash", self.upstream_grouping_identity_hash),
            ("upstream grouping fingerprint", self.upstream_grouping_fingerprint),
            ("reference hash", self.reference_sha256),
            ("security record inventory hash", self.security_record_inventory_hash),
            ("title interval inventory hash", self.title_interval_inventory_hash),
            ("ticker interval inventory hash", self.ticker_interval_inventory_hash),
            ("mapping row inventory hash", self.mapping_row_inventory_hash),
        ):
            _sha256(value, label=label)
        counts = (
            (self.security_record_count, MAX_FORM4_PIT_SECURITY_RECORDS),
            (self.title_interval_count, MAX_FORM4_SECURITY_TITLE_INTERVALS),
            (self.ticker_interval_count, MAX_FORM4_TICKER_INTERVALS),
            (
                self.mapping_row_count,
                MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
            ),
            (
                self.structurally_mapped_count,
                MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
            ),
            (
                self.security_mapping_quarantined_count,
                MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
            ),
            (
                self.manual_exception_resolution_count,
                MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
            ),
        )
        if (
            any(
                type(value) is not int or not 0 <= value <= cap
                for value, cap in counts
            )
            or self.structurally_mapped_count
            + self.security_mapping_quarantined_count
            != self.mapping_row_count
            or self.manual_exception_resolution_count
            > self.structurally_mapped_count
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping identity counts are invalid"
            )
        authority = (
            self.official_profile_compatibility_verified,
            self.official_amendment_link_verified,
            self.complete_amendment_coverage_verified,
            self.official_security_master_compatibility_verified,
            self.point_in_time_issuer_identity_verified,
            self.point_in_time_reporting_owner_identity_verified,
            self.point_in_time_security_identity_verified,
            self.point_in_time_transaction_identity_verified,
            self.ordinary_equity_classification_verified,
            self.canonical_filter_authorized,
            self.lot_aggregation_authorized,
            self.sec_access_authorized,
            self.provider_access_authorized,
            self.outcomes_authorized,
            self.qc_execution_authorized,
            self.deployment_authorized,
            self.trading_authorized,
        )
        if (
            any(value is not False for value in authority)
            or type(self.authorized_outcome_looks) is not int
            or self.authorized_outcome_looks != 0
            or type(self.consumed_outcome_looks) is not int
            or self.consumed_outcome_looks != 0
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping identity claims authority"
            )
        match = (
            _MAPPING_ID_RE.fullmatch(self.mapping_id)
            if type(self.mapping_id) is str
            else None
        )
        if (
            match is None
            or match.group("hash_prefix")
            != hash_payload(_mapping_identity_payload(self))[:16]
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping ID is invalid"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            **_mapping_identity_payload(self),
            "mapping_id": self.mapping_id,
        }


def _mapping_identity_payload(
    identity: Form4PitSecurityMappingIdentity,
) -> dict[str, object]:
    return {
        "contract_version": identity.contract_version,
        "builder_git_commit": identity.builder_git_commit,
        "upstream_grouping_id": identity.upstream_grouping_id,
        "upstream_grouping_identity_hash": (
            identity.upstream_grouping_identity_hash
        ),
        "upstream_grouping_fingerprint": identity.upstream_grouping_fingerprint,
        "reference_id": identity.reference_id,
        "reference_version": identity.reference_version,
        "reference_sha256": identity.reference_sha256,
        "security_record_inventory_hash": (
            identity.security_record_inventory_hash
        ),
        "title_interval_inventory_hash": identity.title_interval_inventory_hash,
        "ticker_interval_inventory_hash": (
            identity.ticker_interval_inventory_hash
        ),
        "mapping_row_inventory_hash": identity.mapping_row_inventory_hash,
        "security_record_count": identity.security_record_count,
        "title_interval_count": identity.title_interval_count,
        "ticker_interval_count": identity.ticker_interval_count,
        "mapping_row_count": identity.mapping_row_count,
        "structurally_mapped_count": identity.structurally_mapped_count,
        "security_mapping_quarantined_count": (
            identity.security_mapping_quarantined_count
        ),
        "manual_exception_resolution_count": (
            identity.manual_exception_resolution_count
        ),
        "official_profile_compatibility_verified": False,
        "official_amendment_link_verified": False,
        "complete_amendment_coverage_verified": False,
        "official_security_master_compatibility_verified": False,
        "point_in_time_issuer_identity_verified": False,
        "point_in_time_reporting_owner_identity_verified": False,
        "point_in_time_security_identity_verified": False,
        "point_in_time_transaction_identity_verified": False,
        "ordinary_equity_classification_verified": False,
        "canonical_filter_authorized": False,
        "lot_aggregation_authorized": False,
        "sec_access_authorized": False,
        "provider_access_authorized": False,
        "outcomes_authorized": False,
        "qc_execution_authorized": False,
        "deployment_authorized": False,
        "trading_authorized": False,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }


@dataclass(frozen=True)
class Form4PitSecurityMapping:
    """Factory-created, auditable IB-2C reference and row inventory."""

    identity: Form4PitSecurityMappingIdentity
    security_records: tuple[Form4PitSecurityRecord, ...]
    title_intervals: tuple[Form4SecurityTitleInterval, ...]
    ticker_intervals: tuple[Form4TickerInterval, ...]
    rows: tuple[Form4PitSecurityMappingRow, ...]
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _MAPPING_FACTORY_TOKEN:
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping result must be factory-created"
            )
        if (
            type(self.identity) is not Form4PitSecurityMappingIdentity
            or type(self.security_records) is not tuple
            or type(self.title_intervals) is not tuple
            or type(self.ticker_intervals) is not tuple
            or type(self.rows) is not tuple
            or any(
                type(item) is not Form4PitSecurityRecord
                for item in self.security_records
            )
            or any(
                type(item) is not Form4SecurityTitleInterval
                for item in self.title_intervals
            )
            or any(
                type(item) is not Form4TickerInterval
                for item in self.ticker_intervals
            )
            or any(type(item) is not Form4PitSecurityMappingRow for item in self.rows)
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping result state is not exact"
            )
        Form4PitSecurityMappingIdentity.__post_init__(
            self.identity,
            _IDENTITY_FACTORY_TOKEN,
        )
        for item in self.security_records:
            Form4PitSecurityRecord.__post_init__(item)
        for item in self.title_intervals:
            Form4SecurityTitleInterval.__post_init__(item)
        for item in self.ticker_intervals:
            Form4TickerInterval.__post_init__(item)
        for item in self.rows:
            Form4PitSecurityMappingRow.__post_init__(item, _ROW_FACTORY_TOKEN)
        if (
            self.security_records
            != tuple(sorted(self.security_records, key=_security_sort_key))
            or self.title_intervals
            != tuple(sorted(self.title_intervals, key=_title_sort_key))
            or self.ticker_intervals
            != tuple(sorted(self.ticker_intervals, key=_ticker_sort_key))
            or self.rows != tuple(sorted(self.rows, key=_row_sort_key))
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping result order is not canonical"
            )
        _validate_reference_crosslinks(
            self.security_records,
            self.title_intervals,
            self.ticker_intervals,
        )
        reference_index = _reference_index(
            self.security_records,
            self.title_intervals,
            self.ticker_intervals,
        )
        replay_budget = _ResolutionBudget()
        for item in self.rows:
            replayed = _replay_mapping_row(
                item,
                index=reference_index,
                budget=replay_budget,
            )
            if replayed.to_payload() != item.to_payload():
                raise Form4PitSecurityMappingError(
                    "REFUSED: mapping row does not replay its resolved reference"
                )
        row_ids = tuple(item.mapping_row_id for item in self.rows)
        upstream_ids = tuple(
            item.transaction_attribution_id for item in self.rows
        )
        if (
            len(set(row_ids)) != len(row_ids)
            or len(set(upstream_ids)) != len(upstream_ids)
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping row identity is not exhaustive"
            )
        mapped_count = sum(
            item.point_in_time_mapping_structurally_resolved
            for item in self.rows
        )
        manual_count = sum(
            item.title_mapping_kind
            is Form4SecurityTitleMappingKind.MANUAL_EXCEPTION
            for item in self.rows
        )
        identity = self.identity
        if (
            identity.security_record_count != len(self.security_records)
            or identity.title_interval_count != len(self.title_intervals)
            or identity.ticker_interval_count != len(self.ticker_intervals)
            or identity.mapping_row_count != len(self.rows)
            or identity.structurally_mapped_count != mapped_count
            or identity.security_mapping_quarantined_count
            != len(self.rows) - mapped_count
            or identity.manual_exception_resolution_count != manual_count
            or identity.security_record_inventory_hash
            != hash_payload([item.to_payload() for item in self.security_records])
            or identity.title_interval_inventory_hash
            != hash_payload([item.to_payload() for item in self.title_intervals])
            or identity.ticker_interval_inventory_hash
            != hash_payload([item.to_payload() for item in self.ticker_intervals])
            or identity.mapping_row_inventory_hash
            != hash_payload([item.to_payload() for item in self.rows])
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping result counts or hashes are inconsistent"
            )

    @property
    def official_security_master_compatibility_verified(self) -> bool:
        return False

    @property
    def official_profile_compatibility_verified(self) -> bool:
        return False

    @property
    def official_amendment_link_verified(self) -> bool:
        return False

    @property
    def complete_amendment_coverage_verified(self) -> bool:
        return False

    @property
    def point_in_time_issuer_identity_verified(self) -> bool:
        return False

    @property
    def point_in_time_reporting_owner_identity_verified(self) -> bool:
        return False

    @property
    def point_in_time_security_identity_verified(self) -> bool:
        return False

    @property
    def point_in_time_transaction_identity_verified(self) -> bool:
        return False

    @property
    def ordinary_equity_classification_verified(self) -> bool:
        return False

    @property
    def canonical_filter_authorized(self) -> bool:
        return False

    @property
    def lot_aggregation_authorized(self) -> bool:
        return False

    @property
    def sec_access_authorized(self) -> bool:
        return False

    @property
    def provider_access_authorized(self) -> bool:
        return False

    @property
    def outcomes_authorized(self) -> bool:
        return False

    @property
    def qc_execution_authorized(self) -> bool:
        return False

    @property
    def deployment_authorized(self) -> bool:
        return False

    @property
    def trading_authorized(self) -> bool:
        return False

    @property
    def authorized_outcome_looks(self) -> int:
        return 0

    @property
    def consumed_outcome_looks(self) -> int:
        return 0

    def to_payload(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_payload(),
            "security_records": [
                item.to_payload() for item in self.security_records
            ],
            "title_intervals": [
                item.to_payload() for item in self.title_intervals
            ],
            "ticker_intervals": [
                item.to_payload() for item in self.ticker_intervals
            ],
            "rows": [item.to_payload() for item in self.rows],
        }


def _security_sort_key(item: Form4PitSecurityRecord) -> tuple:
    return (
        item.issuer_cik,
        item.security_id,
        item.share_class_id,
        item.valid_from,
        date.max if item.valid_to is None else item.valid_to,
        item.security_record_id,
    )


def _title_sort_key(item: Form4SecurityTitleInterval) -> tuple:
    return (
        item.security_title_raw,
        item.security_id,
        item.share_class_id,
        item.valid_from,
        date.max if item.valid_to is None else item.valid_to,
        item.title_interval_id,
    )


def _ticker_sort_key(item: Form4TickerInterval) -> tuple:
    return (
        item.ticker,
        item.security_id,
        item.exchange,
        item.country,
        item.valid_from,
        date.max if item.valid_to is None else item.valid_to,
        item.ticker_interval_id,
    )


def _row_sort_key(item: Form4PitSecurityMappingRow) -> tuple:
    return (
        item.accession_number,
        item.source_sha256,
        item.row_index,
        item.event_id,
    )


_REFERENCE_TYPES = (
    Form4PitSecurityRecord,
    Form4SecurityTitleInterval,
    Form4TickerInterval,
)
_REFERENCE_ENUM_TYPES = (
    Form4SecurityClass,
    Form4SecurityTitleMappingKind,
)


@dataclass
class _ProjectionBudget:
    nodes: int = 0
    text_characters: int = 0
    active_ids: set[int] | None = None

    def __post_init__(self) -> None:
        if self.active_ids is None:
            self.active_ids = set()


def _project_reference(
    value: object,
    *,
    budget: _ProjectionBudget | None = None,
    depth: int = 0,
) -> object:
    if budget is None:
        budget = _ProjectionBudget()
    if depth > MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_DEPTH:
        raise Form4PitSecurityMappingError(
            "REFUSED: reference input exceeds the depth bound"
        )
    budget.nodes += 1
    if budget.nodes > MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_NODES:
        raise Form4PitSecurityMappingError(
            "REFUSED: reference input exceeds the node bound"
        )
    value_type = type(value)
    if any(value_type is enum_type for enum_type in _REFERENCE_ENUM_TYPES):
        return _project_reference(
            value.value,
            budget=budget,
            depth=depth + 1,
        )
    if value_type is date:
        return value.isoformat()
    if value_type is str:
        budget.text_characters += len(value)
        if (
            budget.text_characters
            > MAX_FORM4_PIT_SECURITY_MAPPING_TEXT_CHARACTERS
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: reference input exceeds the text bound"
            )
        return value
    if value is None or value_type is bool or value_type is int:
        return value
    is_contract = any(value_type is item for item in _REFERENCE_TYPES)
    if value_type is tuple or is_contract:
        active_ids = budget.active_ids
        assert active_ids is not None
        value_id = id(value)
        if value_id in active_ids:
            raise Form4PitSecurityMappingError(
                "REFUSED: reference input contains a cycle"
            )
        active_ids.add(value_id)
        try:
            if value_type is tuple:
                return [
                    _project_reference(
                        item,
                        budget=budget,
                        depth=depth + 1,
                    )
                    for item in value
                ]
            declared = {item.name for item in fields(value_type)}
            state = object.__getattribute__(value, "__dict__")
            if type(state) is not dict or set(state) != declared:
                raise Form4PitSecurityMappingError(
                    "REFUSED: reference dataclass state is not exact"
                )
            return {
                item.name: _project_reference(
                    state[item.name],
                    budget=budget,
                    depth=depth + 1,
                )
                for item in fields(value_type)
            }
        finally:
            active_ids.remove(value_id)
    raise Form4PitSecurityMappingError(
        "REFUSED: reference input contains an unsupported value"
    )


def _capture_reference(
    security_records: object,
    title_intervals: object,
    ticker_intervals: object,
) -> tuple[dict[str, object], str]:
    budget = _ProjectionBudget()
    payload = {
        "security_records": _project_reference(
            security_records,
            budget=budget,
        ),
        "title_intervals": _project_reference(
            title_intervals,
            budget=budget,
        ),
        "ticker_intervals": _project_reference(
            ticker_intervals,
            budget=budget,
        ),
    }
    return payload, hash_payload(payload)


def _preflight_reference_inputs(
    security_records: object,
    title_intervals: object,
    ticker_intervals: object,
) -> None:
    declarations = (
        (
            security_records,
            Form4PitSecurityRecord,
            MAX_FORM4_PIT_SECURITY_RECORDS,
        ),
        (
            title_intervals,
            Form4SecurityTitleInterval,
            MAX_FORM4_SECURITY_TITLE_INTERVALS,
        ),
        (
            ticker_intervals,
            Form4TickerInterval,
            MAX_FORM4_TICKER_INTERVALS,
        ),
    )
    if any(type(values) is not tuple for values, _, _ in declarations):
        raise Form4PitSecurityMappingError(
            "REFUSED: reference inputs must be exact tuples"
        )
    if any(len(values) > cap for values, _, cap in declarations):
        raise Form4PitSecurityMappingError(
            "REFUSED: reference preflight count exceeds a bound"
        )
    if any(
        type(item) is not expected_type
        for values, expected_type, _ in declarations
        for item in values
    ):
        raise Form4PitSecurityMappingError(
            "REFUSED: reference inputs contain a non-exact record type"
        )


def _records_from_snapshot(
    payload: dict[str, object],
) -> tuple[
    tuple[Form4PitSecurityRecord, ...],
    tuple[Form4SecurityTitleInterval, ...],
    tuple[Form4TickerInterval, ...],
]:
    raw_security = payload["security_records"]
    raw_titles = payload["title_intervals"]
    raw_tickers = payload["ticker_intervals"]
    if (
        type(raw_security) is not list
        or type(raw_titles) is not list
        or type(raw_tickers) is not list
        or len(raw_security) > MAX_FORM4_PIT_SECURITY_RECORDS
        or len(raw_titles) > MAX_FORM4_SECURITY_TITLE_INTERVALS
        or len(raw_tickers) > MAX_FORM4_TICKER_INTERVALS
    ):
        raise Form4PitSecurityMappingError(
            "REFUSED: reference inventory count exceeds a bound"
        )
    securities = tuple(
        Form4PitSecurityRecord(
            security_id=item["security_id"],
            share_class_id=item["share_class_id"],
            issuer_cik=item["issuer_cik"],
            security_class_normalized=Form4SecurityClass(
                item["security_class_normalized"]
            ),
            valid_from=date.fromisoformat(item["valid_from"]),
            valid_to=(
                None
                if item["valid_to"] is None
                else date.fromisoformat(item["valid_to"])
            ),
            available_at_utc=item["available_at_utc"],
            valid_to_available_at_utc=item["valid_to_available_at_utc"],
            valid_to_evidence_id=item["valid_to_evidence_id"],
            valid_to_evidence_sha256=item["valid_to_evidence_sha256"],
            evidence_id=item["evidence_id"],
            evidence_sha256=item["evidence_sha256"],
        )
        for item in raw_security
    )
    titles = tuple(
        Form4SecurityTitleInterval(
            security_id=item["security_id"],
            share_class_id=item["share_class_id"],
            security_title_raw=item["security_title_raw"],
            mapping_kind=Form4SecurityTitleMappingKind(item["mapping_kind"]),
            valid_from=date.fromisoformat(item["valid_from"]),
            valid_to=(
                None
                if item["valid_to"] is None
                else date.fromisoformat(item["valid_to"])
            ),
            available_at_utc=item["available_at_utc"],
            valid_to_available_at_utc=item["valid_to_available_at_utc"],
            valid_to_evidence_id=item["valid_to_evidence_id"],
            valid_to_evidence_sha256=item["valid_to_evidence_sha256"],
            evidence_id=item["evidence_id"],
            evidence_sha256=item["evidence_sha256"],
        )
        for item in raw_titles
    )
    tickers = tuple(
        Form4TickerInterval(
            security_id=item["security_id"],
            ticker=item["ticker"],
            exchange=item["exchange"],
            country=item["country"],
            valid_from=date.fromisoformat(item["valid_from"]),
            valid_to=(
                None
                if item["valid_to"] is None
                else date.fromisoformat(item["valid_to"])
            ),
            available_at_utc=item["available_at_utc"],
            valid_to_available_at_utc=item["valid_to_available_at_utc"],
            valid_to_evidence_id=item["valid_to_evidence_id"],
            valid_to_evidence_sha256=item["valid_to_evidence_sha256"],
            evidence_id=item["evidence_id"],
            evidence_sha256=item["evidence_sha256"],
        )
        for item in raw_tickers
    )
    return (
        tuple(sorted(securities, key=_security_sort_key)),
        tuple(sorted(titles, key=_title_sort_key)),
        tuple(sorted(tickers, key=_ticker_sort_key)),
    )


def _validate_reference_crosslinks(
    securities: tuple[Form4PitSecurityRecord, ...],
    titles: tuple[Form4SecurityTitleInterval, ...],
    tickers: tuple[Form4TickerInterval, ...],
) -> None:
    containment_operations = 0
    security_ids = tuple(item.security_record_id for item in securities)
    title_ids = tuple(item.title_interval_id for item in titles)
    ticker_ids = tuple(item.ticker_interval_id for item in tickers)
    if (
        len(set(security_ids)) != len(security_ids)
        or len(set(title_ids)) != len(title_ids)
        or len(set(ticker_ids)) != len(ticker_ids)
    ):
        raise Form4PitSecurityMappingError(
            "REFUSED: reference inventory contains a duplicate interval"
        )
    immutable_by_security: dict[str, tuple[str, str, Form4SecurityClass]] = {}
    security_by_share_class: dict[str, str] = {}
    records_by_security: dict[str, list[Form4PitSecurityRecord]] = {}
    for item in securities:
        identity = (
            item.issuer_cik,
            item.share_class_id,
            item.security_class_normalized,
        )
        prior = immutable_by_security.setdefault(item.security_id, identity)
        if prior != identity:
            raise Form4PitSecurityMappingError(
                "REFUSED: permanent security identity is inconsistent"
            )
        prior_security = security_by_share_class.setdefault(
            item.share_class_id,
            item.security_id,
        )
        if prior_security != item.security_id:
            raise Form4PitSecurityMappingError(
                "REFUSED: share-class ID identifies multiple securities"
            )
        records_by_security.setdefault(item.security_id, []).append(item)
    for item in titles:
        identity = immutable_by_security.get(item.security_id)
        if identity is None or identity[1] != item.share_class_id:
            raise Form4PitSecurityMappingError(
                "REFUSED: title interval has no exact security/share-class"
            )
        parents = records_by_security[item.security_id]
        containment_operations += len(parents)
        if (
            containment_operations
            > MAX_FORM4_PIT_SECURITY_MAPPING_RESOLUTION_OPERATIONS
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: reference validation exceeds the operation bound"
            )
        if not any(
            _interval_contains(parent, item)
            for parent in parents
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: title interval exceeds permanent-security validity"
            )
    for item in tickers:
        if item.security_id not in immutable_by_security:
            raise Form4PitSecurityMappingError(
                "REFUSED: ticker interval has no exact permanent security"
            )
        parents = records_by_security[item.security_id]
        containment_operations += len(parents)
        if (
            containment_operations
            > MAX_FORM4_PIT_SECURITY_MAPPING_RESOLUTION_OPERATIONS
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: reference validation exceeds the operation bound"
            )
        if not any(
            _interval_contains(parent, item)
            for parent in parents
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: ticker interval exceeds permanent-security validity"
            )
    _validate_listing_reuse(tickers)


def _interval_contains(
    parent: Form4PitSecurityRecord,
    child: Form4SecurityTitleInterval | Form4TickerInterval,
) -> bool:
    if parent.valid_from > child.valid_from:
        return False
    if parent.valid_to is None:
        return True
    return child.valid_to is not None and child.valid_to <= parent.valid_to


def _validate_listing_reuse(
    tickers: tuple[Form4TickerInterval, ...],
) -> None:
    by_listing: dict[
        tuple[str, str, str],
        list[Form4TickerInterval],
    ] = {}
    for item in tickers:
        by_listing.setdefault(
            (item.ticker, item.exchange, item.country),
            [],
        ).append(item)
    for intervals in by_listing.values():
        top_one: tuple[str, int] | None = None
        top_two: tuple[str, int] | None = None
        max_end_by_security: dict[str, int] = {}
        for item in sorted(
            intervals,
            key=lambda value: (
                value.valid_from,
                value.security_id,
                date.max if value.valid_to is None else value.valid_to,
            ),
        ):
            competing = (
                top_one
                if top_one is not None and top_one[0] != item.security_id
                else top_two
            )
            start_ordinal = item.valid_from.toordinal()
            if competing is not None and competing[1] > start_ordinal:
                raise Form4PitSecurityMappingError(
                    "REFUSED: one listing overlaps multiple permanent securities"
                )
            end_ordinal = (
                date.max.toordinal() + 1
                if item.valid_to is None
                else item.valid_to.toordinal()
            )
            prior_end = max_end_by_security.get(item.security_id)
            if prior_end is not None and prior_end >= end_ordinal:
                continue
            max_end_by_security[item.security_id] = end_ordinal
            updated = (item.security_id, end_ordinal)
            if top_one is None:
                top_one = updated
            elif top_one[0] == item.security_id:
                top_one = updated
            elif top_two is not None and top_two[0] == item.security_id:
                top_two = updated
            elif end_ordinal > top_one[1]:
                top_two = top_one
                top_one = updated
            elif top_two is None or end_ordinal > top_two[1]:
                top_two = updated
            if top_two is not None and top_two[1] > top_one[1]:
                top_one, top_two = top_two, top_one


def _interval_status(
    item: Form4PitSecurityRecord
    | Form4SecurityTitleInterval
    | Form4TickerInterval,
    *,
    effective_date: date,
    cutoff: datetime,
) -> str:
    if _canonical_utc(
        item.available_at_utc,
        label="interval availability",
    ) > cutoff:
        return "not_visible"
    if effective_date < item.valid_from:
        return "inactive"
    if item.valid_to is None:
        return "active"
    closure = _canonical_utc(
        item.valid_to_available_at_utc,
        label="interval closure availability",
    )
    if closure > cutoff:
        return "active"
    return "active" if effective_date < item.valid_to else "inactive"


def _new_york_filing_date(accepted_at_utc: str) -> date:
    return _canonical_utc(
        accepted_at_utc,
        label="issuer acceptance",
    ).astimezone(_EASTERN).date()


def _interval_asof_id(
    item: Form4PitSecurityRecord
    | Form4SecurityTitleInterval
    | Form4TickerInterval,
    *,
    cutoff: datetime,
) -> str:
    payload = item.to_payload()
    if (
        item.valid_to is not None
        and _canonical_utc(
            item.valid_to_available_at_utc,
            label="interval closure availability",
        )
        > cutoff
    ):
        payload["valid_to"] = None
        payload["valid_to_available_at_utc"] = None
        payload["valid_to_evidence_id"] = None
        payload["valid_to_evidence_sha256"] = None
    return hash_payload(payload)


def _make_row(
    transaction: dict[str, object],
    issuer: dict[str, object],
    *,
    outcomes: tuple[Form4PitSecurityMappingOutcome, ...],
    security: Form4PitSecurityRecord | None = None,
    title: Form4SecurityTitleInterval | None = None,
    ticker: Form4TickerInterval | None = None,
) -> Form4PitSecurityMappingRow:
    mapped = outcomes == (
        Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY,
    )
    cutoff = _canonical_utc(
        issuer["accepted_at_utc"],
        label="issuer acceptance",
    )
    payload = {
        "accession_number": transaction["accession_number"],
        "source_sha256": transaction["source_sha256"],
        "row_index": transaction["row_index"],
        "event_id": transaction["event_id"],
        "filing_observation_id": transaction["filing_observation_id"],
        "upstream_transaction_observation_id": (
            transaction["upstream_transaction_observation_id"]
        ),
        "upstream_report_row_id": transaction["upstream_report_row_id"],
        "transaction_payload_hash": transaction["transaction_payload_hash"],
        "transaction_attribution_id": (
            transaction["transaction_attribution_id"]
        ),
        "issuer_candidate_id": transaction["issuer_candidate_id"],
        "issuer_cik": issuer["issuer_cik"],
        "accepted_at_utc": issuer["accepted_at_utc"],
        "document_type": issuer["document_type"],
        "original_accession": issuer["original_accession"],
        "amends_accession": issuer["amends_accession"],
        "issuer_observation_id": issuer["issuer_observation_id"],
        "issuer_symbol_raw": issuer["issuer_symbol_raw"],
        "security_title_raw": transaction["security_title_raw"],
        "transaction_date": (
            None
            if transaction["transaction_date"] is None
            else date.fromisoformat(transaction["transaction_date"])
        ),
        "upstream_disposition": Form4ProvisionalDisposition(
            transaction["upstream_disposition"]
        ),
        "identity_disposition": Form4ObservedIdentityDisposition(
            transaction["identity_disposition"]
        ),
        "attributed_owner_cik": transaction["attributed_owner_cik"],
        "attributed_owner_candidate_id": (
            transaction["attributed_owner_candidate_id"]
        ),
        "owner_attribution_outcomes": tuple(
            Form4OwnerAttributionOutcome(item)
            for item in transaction["owner_attribution_outcomes"]
        ),
        "resolution_outcomes": outcomes,
        "security_id": security.security_id if mapped else None,
        "share_class_id": security.share_class_id if mapped else None,
        "security_class_normalized": (
            security.security_class_normalized if mapped else None
        ),
        "ticker": ticker.ticker if mapped else None,
        "exchange": ticker.exchange if mapped else None,
        "country": ticker.country if mapped else None,
        "security_interval_asof_id": (
            _interval_asof_id(security, cutoff=cutoff) if mapped else None
        ),
        "title_interval_asof_id": (
            _interval_asof_id(title, cutoff=cutoff) if mapped else None
        ),
        "ticker_interval_asof_id": (
            _interval_asof_id(ticker, cutoff=cutoff) if mapped else None
        ),
        "title_mapping_kind": title.mapping_kind if mapped else None,
        "point_in_time_mapping_structurally_resolved": mapped,
        "point_in_time_issuer_identity_verified": (
            transaction["point_in_time_issuer_identity_verified"]
        ),
        "point_in_time_reporting_owner_identity_verified": (
            transaction["point_in_time_reporting_owner_identity_verified"]
        ),
        "point_in_time_security_identity_verified": (
            transaction["point_in_time_security_identity_verified"]
        ),
        "point_in_time_transaction_identity_verified": (
            transaction["point_in_time_transaction_identity_verified"]
        ),
        "ordinary_equity_classification_verified": False,
        "canonical_filter_authorized": False,
        "lot_aggregation_authorized": False,
        "outcomes_authorized": False,
        "qc_execution_authorized": False,
        "deployment_authorized": False,
        "trading_authorized": False,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }
    provisional = object.__new__(Form4PitSecurityMappingRow)
    for name, value in payload.items():
        object.__setattr__(provisional, name, value)
    row_id = hash_payload(_mapping_row_payload(provisional))
    return Form4PitSecurityMappingRow(
        **payload,
        mapping_row_id=row_id,
        _verified_factory_token=_ROW_FACTORY_TOKEN,
    )


@dataclass(frozen=True)
class _ReferenceIndex:
    securities_by_issuer: dict[str, tuple[Form4PitSecurityRecord, ...]]
    security_issuer_by_id: dict[str, str]
    titles_by_issuer_and_raw: dict[
        tuple[str, str],
        tuple[Form4SecurityTitleInterval, ...],
    ]
    tickers_by_security: dict[str, tuple[Form4TickerInterval, ...]]
    tickers_by_listing: dict[
        tuple[str, str, str],
        tuple[Form4TickerInterval, ...],
    ]


@dataclass
class _ResolutionBudget:
    operations: int = 0

    def charge(self, count: int) -> None:
        if type(count) is not int or count < 0:
            raise Form4PitSecurityMappingError(
                "REFUSED: resolution operation charge is invalid"
            )
        self.operations += count
        if (
            self.operations
            > MAX_FORM4_PIT_SECURITY_MAPPING_RESOLUTION_OPERATIONS
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: security mapping exceeds the resolution operation bound"
            )


def _reference_index(
    securities: tuple[Form4PitSecurityRecord, ...],
    titles: tuple[Form4SecurityTitleInterval, ...],
    tickers: tuple[Form4TickerInterval, ...],
) -> _ReferenceIndex:
    securities_by_issuer: dict[str, list[Form4PitSecurityRecord]] = {}
    security_issuer_by_id: dict[str, str] = {}
    for item in securities:
        securities_by_issuer.setdefault(item.issuer_cik, []).append(item)
        security_issuer_by_id[item.security_id] = item.issuer_cik
    titles_by_issuer_and_raw: dict[
        tuple[str, str],
        list[Form4SecurityTitleInterval],
    ] = {}
    for item in titles:
        issuer_cik = security_issuer_by_id[item.security_id]
        titles_by_issuer_and_raw.setdefault(
            (issuer_cik, item.security_title_raw),
            [],
        ).append(item)
    tickers_by_security: dict[str, list[Form4TickerInterval]] = {}
    tickers_by_listing: dict[
        tuple[str, str, str],
        list[Form4TickerInterval],
    ] = {}
    for item in tickers:
        tickers_by_security.setdefault(item.security_id, []).append(item)
        tickers_by_listing.setdefault(
            (item.ticker, item.exchange, item.country),
            [],
        ).append(item)
    return _ReferenceIndex(
        securities_by_issuer={
            key: tuple(values) for key, values in securities_by_issuer.items()
        },
        security_issuer_by_id=security_issuer_by_id,
        titles_by_issuer_and_raw={
            key: tuple(values)
            for key, values in titles_by_issuer_and_raw.items()
        },
        tickers_by_security={
            key: tuple(values) for key, values in tickers_by_security.items()
        },
        tickers_by_listing={
            key: tuple(values) for key, values in tickers_by_listing.items()
        },
    )


def _resolve_row(
    transaction: dict[str, object],
    issuer: dict[str, object],
    *,
    index: _ReferenceIndex,
    budget: _ResolutionBudget | None = None,
) -> Form4PitSecurityMappingRow:
    if budget is None:
        budget = _ResolutionBudget()
    missing: list[Form4PitSecurityMappingOutcome] = []
    if transaction["transaction_date"] is None:
        missing.append(
            Form4PitSecurityMappingOutcome.MISSING_TRANSACTION_DATE_QUARANTINED
        )
    if transaction["security_title_raw"] is None:
        missing.append(
            Form4PitSecurityMappingOutcome.MISSING_SECURITY_TITLE_QUARANTINED
        )
    if issuer["issuer_symbol_raw"] is None:
        missing.append(
            Form4PitSecurityMappingOutcome.MISSING_ISSUER_SYMBOL_QUARANTINED
        )
    if missing:
        return _make_row(transaction, issuer, outcomes=tuple(missing))

    transaction_date = date.fromisoformat(transaction["transaction_date"])
    cutoff = _canonical_utc(
        issuer["accepted_at_utc"],
        label="issuer acceptance",
    )
    filing_market_date = _new_york_filing_date(issuer["accepted_at_utc"])
    if transaction_date > filing_market_date:
        return _make_row(
            transaction,
            issuer,
            outcomes=(
                Form4PitSecurityMappingOutcome.TRANSACTION_AFTER_FILING_DATE_QUARANTINED,
            ),
        )
    issuer_cik = issuer["issuer_cik"]
    security_title = transaction["security_title_raw"]

    title_candidates = index.titles_by_issuer_and_raw.get(
        (issuer_cik, security_title),
        (),
    )
    issuer_securities = index.securities_by_issuer.get(issuer_cik, ())
    budget.charge(len(title_candidates) + len(issuer_securities))
    candidate_security_ids = {item.security_id for item in title_candidates}
    relevant_securities = tuple(
        item
        for item in issuer_securities
        if item.security_id in candidate_security_ids
    )
    budget.charge(len(relevant_securities) + len(title_candidates))
    active_securities = tuple(
        item
        for item in relevant_securities
        if _interval_status(
            item,
            effective_date=transaction_date,
            cutoff=cutoff,
        )
        == "active"
    )
    active_titles = tuple(
        item
        for item in title_candidates
        if _interval_status(
            item,
            effective_date=transaction_date,
            cutoff=cutoff,
        )
        == "active"
    )

    budget.charge(len(active_securities) + len(active_titles))
    securities_by_key: dict[
        tuple[str, str],
        list[Form4PitSecurityRecord],
    ] = {}
    for item in active_securities:
        securities_by_key.setdefault(
            (item.security_id, item.share_class_id),
            [],
        ).append(item)
    titles_by_key: dict[
        tuple[str, str],
        list[Form4SecurityTitleInterval],
    ] = {}
    for item in active_titles:
        titles_by_key.setdefault(
            (item.security_id, item.share_class_id),
            [],
        ).append(item)
    budget.charge(len(securities_by_key))
    pair_count = 0
    selected_pair: tuple[
        Form4PitSecurityRecord,
        Form4SecurityTitleInterval,
    ] | None = None
    for key, security_items in securities_by_key.items():
        title_items = titles_by_key.get(key, [])
        matching_count = len(security_items) * len(title_items)
        if matching_count == 1 and pair_count == 0:
            selected_pair = (security_items[0], title_items[0])
        pair_count += matching_count
        if pair_count > 1:
            break
    if pair_count == 0:
        return _make_row(
            transaction,
            issuer,
            outcomes=(
                Form4PitSecurityMappingOutcome.NO_ACTIVE_SECURITY_TITLE_MAPPING_QUARANTINED,
            ),
        )
    if pair_count != 1 or selected_pair is None:
        return _make_row(
            transaction,
            issuer,
            outcomes=(
                Form4PitSecurityMappingOutcome.AMBIGUOUS_SECURITY_TITLE_MAPPING_QUARANTINED,
            ),
        )
    security, title = selected_pair
    security_tickers = index.tickers_by_security.get(security.security_id, ())
    budget.charge(len(security_tickers))
    active_tickers = tuple(
        item
        for item in security_tickers
        if _interval_status(
            item,
            effective_date=filing_market_date,
            cutoff=cutoff,
        )
        == "active"
    )
    if not active_tickers:
        return _make_row(
            transaction,
            issuer,
            outcomes=(
                Form4PitSecurityMappingOutcome.NO_ACTIVE_TICKER_QUARANTINED,
            ),
        )
    if len(active_tickers) != 1:
        return _make_row(
            transaction,
            issuer,
            outcomes=(
                Form4PitSecurityMappingOutcome.AMBIGUOUS_TICKER_QUARANTINED,
            ),
        )
    ticker = active_tickers[0]
    listing_tickers = index.tickers_by_listing[
        (ticker.ticker, ticker.exchange, ticker.country)
    ]
    budget.charge(len(listing_tickers))
    active_listing_tickers = tuple(
        item
        for item in listing_tickers
        if _interval_status(
            item,
            effective_date=filing_market_date,
            cutoff=cutoff,
        )
        == "active"
    )
    if (
        len(active_listing_tickers) != 1
        or active_listing_tickers[0].ticker_interval_id
        != ticker.ticker_interval_id
    ):
        return _make_row(
            transaction,
            issuer,
            outcomes=(
                Form4PitSecurityMappingOutcome.AMBIGUOUS_TICKER_QUARANTINED,
            ),
        )
    if ticker.ticker != issuer["issuer_symbol_raw"]:
        return _make_row(
            transaction,
            issuer,
            outcomes=(
                Form4PitSecurityMappingOutcome.ISSUER_SYMBOL_MISMATCH_QUARANTINED,
            ),
        )
    return _make_row(
        transaction,
        issuer,
        outcomes=(Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY,),
        security=security,
        title=title,
        ticker=ticker,
    )


def _replay_mapping_row(
    row: Form4PitSecurityMappingRow,
    *,
    index: _ReferenceIndex,
    budget: _ResolutionBudget | None = None,
) -> Form4PitSecurityMappingRow:
    transaction = {
        "accession_number": row.accession_number,
        "source_sha256": row.source_sha256,
        "row_index": row.row_index,
        "event_id": row.event_id,
        "filing_observation_id": row.filing_observation_id,
        "upstream_transaction_observation_id": (
            row.upstream_transaction_observation_id
        ),
        "upstream_report_row_id": row.upstream_report_row_id,
        "transaction_payload_hash": row.transaction_payload_hash,
        "transaction_attribution_id": row.transaction_attribution_id,
        "issuer_candidate_id": row.issuer_candidate_id,
        "security_title_raw": row.security_title_raw,
        "transaction_date": (
            None
            if row.transaction_date is None
            else row.transaction_date.isoformat()
        ),
        "upstream_disposition": row.upstream_disposition.value,
        "identity_disposition": row.identity_disposition.value,
        "attributed_owner_cik": row.attributed_owner_cik,
        "attributed_owner_candidate_id": row.attributed_owner_candidate_id,
        "owner_attribution_outcomes": [
            item.value for item in row.owner_attribution_outcomes
        ],
        "point_in_time_issuer_identity_verified": (
            row.point_in_time_issuer_identity_verified
        ),
        "point_in_time_reporting_owner_identity_verified": (
            row.point_in_time_reporting_owner_identity_verified
        ),
        "point_in_time_security_identity_verified": (
            row.point_in_time_security_identity_verified
        ),
        "point_in_time_transaction_identity_verified": (
            row.point_in_time_transaction_identity_verified
        ),
    }
    issuer = {
        "issuer_cik": row.issuer_cik,
        "accepted_at_utc": row.accepted_at_utc,
        "document_type": row.document_type,
        "original_accession": row.original_accession,
        "amends_accession": row.amends_accession,
        "issuer_observation_id": row.issuer_observation_id,
        "issuer_symbol_raw": row.issuer_symbol_raw,
    }
    return _resolve_row(transaction, issuer, index=index, budget=budget)


def _issuer_observations_by_filing(
    grouping_snapshot: dict[str, object],
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for candidate in grouping_snapshot["issuer_candidates"]:
        for observation in candidate["observations"]:
            result[observation["filing_observation_id"]] = observation
    return result


_MAPPING_PROVENANCE_TYPES = (
    Form4PitSecurityMapping,
    Form4PitSecurityMappingIdentity,
    Form4PitSecurityMappingRow,
    Form4PitSecurityRecord,
    Form4SecurityTitleInterval,
    Form4TickerInterval,
)
_MAPPING_PROVENANCE_ENUMS = (
    Form4ObservedIdentityDisposition,
    Form4OwnerAttributionOutcome,
    Form4PitSecurityMappingOutcome,
    Form4ProvisionalDisposition,
    Form4SecurityClass,
    Form4SecurityTitleMappingKind,
)
_FACTORY_CREATED_MAPPINGS: dict[
    int,
    tuple[weakref.ReferenceType[Form4PitSecurityMapping], str],
] = {}
_FACTORY_CREATED_MAPPINGS_LOCK = threading.RLock()


def _mapping_provenance_payload(
    value: object,
    *,
    budget: _ProjectionBudget | None = None,
    depth: int = 0,
) -> object:
    if budget is None:
        budget = _ProjectionBudget()
    if depth > MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_DEPTH:
        raise Form4PitSecurityMappingError(
            "REFUSED: mapping provenance exceeds the depth bound"
        )
    budget.nodes += 1
    if budget.nodes > MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_NODES:
        raise Form4PitSecurityMappingError(
            "REFUSED: mapping provenance exceeds the node bound"
        )
    value_type = type(value)
    if any(value_type is item for item in _MAPPING_PROVENANCE_ENUMS):
        return _mapping_provenance_payload(
            value.value,
            budget=budget,
            depth=depth + 1,
        )
    if value_type is date:
        return value.isoformat()
    if value_type is str:
        budget.text_characters += len(value)
        if (
            budget.text_characters
            > MAX_FORM4_PIT_SECURITY_MAPPING_TEXT_CHARACTERS
        ):
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping provenance exceeds the text bound"
            )
        return value
    if value is None or value_type is bool or value_type is int:
        return value
    is_contract = any(value_type is item for item in _MAPPING_PROVENANCE_TYPES)
    if value_type is tuple or is_contract:
        active_ids = budget.active_ids
        assert active_ids is not None
        value_id = id(value)
        if value_id in active_ids:
            raise Form4PitSecurityMappingError(
                "REFUSED: mapping provenance contains a cycle"
            )
        active_ids.add(value_id)
        try:
            if value_type is tuple:
                return [
                    _mapping_provenance_payload(
                        item,
                        budget=budget,
                        depth=depth + 1,
                    )
                    for item in value
                ]
            declared = {item.name for item in fields(value_type)}
            state = object.__getattribute__(value, "__dict__")
            if type(state) is not dict or set(state) != declared:
                raise Form4PitSecurityMappingError(
                    "REFUSED: mapping provenance state is not exact"
                )
            return {
                item.name: _mapping_provenance_payload(
                    state[item.name],
                    budget=budget,
                    depth=depth + 1,
                )
                for item in fields(value_type)
            }
        finally:
            active_ids.remove(value_id)
    raise Form4PitSecurityMappingError(
        "REFUSED: mapping provenance contains an unsupported value"
    )


def _mapping_provenance_fingerprint(
    mapping: Form4PitSecurityMapping,
) -> str:
    if type(mapping) is not Form4PitSecurityMapping:
        raise Form4PitSecurityMappingError(
            "REFUSED: provenance input must be an exact mapping result"
        )
    return hash_payload(_mapping_provenance_payload(mapping))


def _register_factory_created_mapping(
    mapping: Form4PitSecurityMapping,
) -> None:
    fingerprint = _mapping_provenance_fingerprint(mapping)
    object_id = id(mapping)

    def _remove_if_current(
        dead_reference: weakref.ReferenceType[Form4PitSecurityMapping],
    ) -> None:
        with _FACTORY_CREATED_MAPPINGS_LOCK:
            current = _FACTORY_CREATED_MAPPINGS.get(object_id)
            if current is not None and current[0] is dead_reference:
                _FACTORY_CREATED_MAPPINGS.pop(object_id, None)

    reference = weakref.ref(mapping, _remove_if_current)
    with _FACTORY_CREATED_MAPPINGS_LOCK:
        _FACTORY_CREATED_MAPPINGS[object_id] = (reference, fingerprint)


def _is_factory_created_form4_pit_security_mapping(value: object) -> bool:
    try:
        if type(value) is not Form4PitSecurityMapping:
            return False
        fingerprint = _mapping_provenance_fingerprint(value)
        return _matches_factory_created_form4_pit_security_mapping_fingerprint(
            value,
            fingerprint,
        )
    except (
        AttributeError,
        Form4PitSecurityMappingError,
        KeyError,
        OverflowError,
        RecursionError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        return False


def _matches_factory_created_form4_pit_security_mapping_fingerprint(
    value: object,
    observed_fingerprint: object,
) -> bool:
    try:
        if (
            type(value) is not Form4PitSecurityMapping
            or type(observed_fingerprint) is not str
            or _SHA256_RE.fullmatch(observed_fingerprint) is None
        ):
            return False
        with _FACTORY_CREATED_MAPPINGS_LOCK:
            current = _FACTORY_CREATED_MAPPINGS.get(id(value))
            return (
                current is not None
                and current[0]() is value
                and current[1] == observed_fingerprint
            )
    except (
        AttributeError,
        KeyError,
        OverflowError,
        RecursionError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        return False


def _build_form4_pit_security_mapping(
    grouping: Form4SecEntityGrouping,
    *,
    security_records: tuple[Form4PitSecurityRecord, ...],
    title_intervals: tuple[Form4SecurityTitleInterval, ...],
    ticker_intervals: tuple[Form4TickerInterval, ...],
    reference_id: str,
    reference_version: str,
    reference_sha256: str,
    builder_git_commit: str,
) -> Form4PitSecurityMapping:
    if type(grouping) is not Form4SecEntityGrouping:
        raise Form4PitSecurityMappingError(
            "REFUSED: input must be an exact IB-2B grouping"
        )
    if (
        type(builder_git_commit) is not str
        or _GIT_COMMIT_RE.fullmatch(builder_git_commit) is None
    ):
        raise Form4PitSecurityMappingError(
            "REFUSED: builder commit must be full lowercase SHA-1"
        )
    _opaque_id(reference_id, label="reference ID")
    _opaque_id(reference_version, label="reference version")
    _sha256(reference_sha256, label="reference hash")
    _preflight_reference_inputs(
        security_records,
        title_intervals,
        ticker_intervals,
    )

    grouping_fingerprint = _grouping_provenance_fingerprint(grouping)
    if (
        not _matches_factory_created_sec_entity_grouping_fingerprint(
            grouping,
            grouping_fingerprint,
        )
        or not _is_factory_created_sec_entity_grouping(grouping)
    ):
        raise Form4PitSecurityMappingError(
            "REFUSED: input grouping lacks exact factory provenance"
        )
    grouping_snapshot = _grouping_provenance_payload(grouping)
    if (
        type(grouping_snapshot) is not dict
        or hash_payload(grouping_snapshot) != grouping_fingerprint
        or not _matches_factory_created_sec_entity_grouping_fingerprint(
            grouping,
            grouping_fingerprint,
        )
    ):
        raise Form4PitSecurityMappingError(
            "REFUSED: consumed grouping snapshot does not match its factory seal"
        )
    captured_reference, reference_input_fingerprint = _capture_reference(
        security_records,
        title_intervals,
        ticker_intervals,
    )
    securities, titles, tickers = _records_from_snapshot(captured_reference)
    _validate_reference_crosslinks(securities, titles, tickers)
    reference_index = _reference_index(securities, titles, tickers)

    issuer_by_filing = _issuer_observations_by_filing(grouping_snapshot)
    transactions = grouping_snapshot["transaction_attributions"]
    if (
        type(transactions) is not list
        or len(transactions) > MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
    ):
        raise Form4PitSecurityMappingError(
            "REFUSED: upstream transaction count exceeds a bound"
        )
    resolution_budget = _ResolutionBudget()
    rows = tuple(
        sorted(
            (
                _resolve_row(
                    transaction,
                    issuer_by_filing[transaction["filing_observation_id"]],
                    index=reference_index,
                    budget=resolution_budget,
                )
                for transaction in transactions
            ),
            key=_row_sort_key,
        )
    )
    if (
        len(rows) != len(transactions)
        or {
            item.transaction_attribution_id for item in rows
        }
        != {
            transaction["transaction_attribution_id"]
            for transaction in transactions
        }
    ):
        raise Form4PitSecurityMappingError(
            "REFUSED: mapping output is not exhaustive"
        )
    recaptured_reference, final_reference_fingerprint = _capture_reference(
        security_records,
        title_intervals,
        ticker_intervals,
    )
    if (
        final_reference_fingerprint != reference_input_fingerprint
        or recaptured_reference != captured_reference
    ):
        raise Form4PitSecurityMappingError(
            "REFUSED: reference input changed during mapping"
        )

    mapped_count = sum(
        item.point_in_time_mapping_structurally_resolved for item in rows
    )
    manual_count = sum(
        item.title_mapping_kind
        is Form4SecurityTitleMappingKind.MANUAL_EXCEPTION
        for item in rows
    )
    upstream_identity = grouping_snapshot["identity"]
    identity_payload = {
        "contract_version": FORM4_PIT_SECURITY_MAPPING_VERSION,
        "builder_git_commit": builder_git_commit,
        "upstream_grouping_id": upstream_identity["grouping_id"],
        "upstream_grouping_identity_hash": hash_payload(upstream_identity),
        "upstream_grouping_fingerprint": grouping_fingerprint,
        "reference_id": reference_id,
        "reference_version": reference_version,
        "reference_sha256": reference_sha256,
        "security_record_inventory_hash": hash_payload(
            [item.to_payload() for item in securities]
        ),
        "title_interval_inventory_hash": hash_payload(
            [item.to_payload() for item in titles]
        ),
        "ticker_interval_inventory_hash": hash_payload(
            [item.to_payload() for item in tickers]
        ),
        "mapping_row_inventory_hash": hash_payload(
            [item.to_payload() for item in rows]
        ),
        "security_record_count": len(securities),
        "title_interval_count": len(titles),
        "ticker_interval_count": len(tickers),
        "mapping_row_count": len(rows),
        "structurally_mapped_count": mapped_count,
        "security_mapping_quarantined_count": len(rows) - mapped_count,
        "manual_exception_resolution_count": manual_count,
        "official_profile_compatibility_verified": (
            upstream_identity["official_profile_compatibility_verified"]
        ),
        "official_amendment_link_verified": (
            upstream_identity["official_amendment_link_verified"]
        ),
        "complete_amendment_coverage_verified": (
            upstream_identity["complete_amendment_coverage_verified"]
        ),
        "official_security_master_compatibility_verified": False,
        "point_in_time_issuer_identity_verified": (
            upstream_identity["point_in_time_issuer_identity_verified"]
        ),
        "point_in_time_reporting_owner_identity_verified": (
            upstream_identity[
                "point_in_time_reporting_owner_identity_verified"
            ]
        ),
        "point_in_time_security_identity_verified": (
            upstream_identity["point_in_time_security_identity_verified"]
        ),
        "point_in_time_transaction_identity_verified": (
            upstream_identity["point_in_time_transaction_identity_verified"]
        ),
        "ordinary_equity_classification_verified": False,
        "canonical_filter_authorized": False,
        "lot_aggregation_authorized": False,
        "sec_access_authorized": False,
        "provider_access_authorized": False,
        "outcomes_authorized": False,
        "qc_execution_authorized": False,
        "deployment_authorized": False,
        "trading_authorized": False,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }
    identity = Form4PitSecurityMappingIdentity(
        **identity_payload,
        mapping_id=(
            "form4-pit-security-mapping-"
            f"{hash_payload(identity_payload)[:16]}"
        ),
        _verified_factory_token=_IDENTITY_FACTORY_TOKEN,
    )
    result = Form4PitSecurityMapping(
        identity=identity,
        security_records=securities,
        title_intervals=titles,
        ticker_intervals=tickers,
        rows=rows,
        _verified_factory_token=_MAPPING_FACTORY_TOKEN,
    )
    final_grouping_fingerprint = _grouping_provenance_fingerprint(grouping)
    if (
        final_grouping_fingerprint != grouping_fingerprint
        or not _matches_factory_created_sec_entity_grouping_fingerprint(
            grouping,
            final_grouping_fingerprint,
        )
        or not _is_factory_created_sec_entity_grouping(grouping)
    ):
        raise Form4PitSecurityMappingError(
            "REFUSED: input grouping changed during mapping"
        )
    _register_factory_created_mapping(result)
    return result


def build_form4_pit_security_mapping(
    grouping: Form4SecEntityGrouping,
    *,
    security_records: tuple[Form4PitSecurityRecord, ...],
    title_intervals: tuple[Form4SecurityTitleInterval, ...],
    ticker_intervals: tuple[Form4TickerInterval, ...],
    reference_id: str,
    reference_version: str,
    reference_sha256: str,
    builder_git_commit: str,
) -> Form4PitSecurityMapping:
    """Build one exhaustive structural mapping and normalize malformed state."""

    try:
        return _build_form4_pit_security_mapping(
            grouping,
            security_records=security_records,
            title_intervals=title_intervals,
            ticker_intervals=ticker_intervals,
            reference_id=reference_id,
            reference_version=reference_version,
            reference_sha256=reference_sha256,
            builder_git_commit=builder_git_commit,
        )
    except Form4PitSecurityMappingError:
        raise
    except (
        AttributeError,
        KeyError,
        OverflowError,
        RecursionError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise Form4PitSecurityMappingError(
            "REFUSED: malformed point-in-time security mapping input"
        ) from exc
