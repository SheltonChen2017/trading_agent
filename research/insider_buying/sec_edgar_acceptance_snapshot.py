"""Offline EDGAR acceptance-time enrichment for a verified parsed snapshot.

IB-1C consumes only caller-supplied metadata byte images and the public,
raw-bound IB-1B loader.  The repository intentionally supplies no EDGAR JSON
schema profile and this module performs no discovery or network access.  A
metadata source can upgrade one accession to exact acceptance-time evidence;
every upstream accession without such evidence is retained with the
conservative filing-date-only availability tier.  Transaction dates are never
an availability input.

Publication is one canonical, content-addressed JSON bundle.  Cooperative
writers are serialized, redirects and non-regular files are refused, and
verified interrupted publisher temporaries are recoverable.  As in the
earlier snapshot boundaries, adversarial replacement of trusted directory
components during a filesystem operation is outside this local boundary.

The source URL, retrieval instant, capture Git SHA, and parser Git SHA are
caller assertions checked for syntax and internal consistency only.  They do
not authenticate SEC origin, transport, capture time, or repository state.
For cross-host reproducibility, the filing-day guard uses a fixed half-open
05:00Z-to-next-05:00Z window for each SEC filing date, conservatively covering
EST and EDT midnight without an unversioned timezone-database dependency.
This can refuse the first EDT hour even when otherwise valid; it never advances
availability, and it prevents a date-only fallback from preceding supplied
exact evidence on a later day.
This boundary does not fetch or validate filing XML and does not infer Form
4/A original links, supersession, or any amendment semantics.
"""
from __future__ import annotations

import base64
import json
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from data.hashing import canonical_json, hash_bytes, hash_payload
from ml.immutable_io import (
    ImmutableFileConflictError,
    exclusive_file_lock,
    publish_immutable_bytes,
)
from research.insider_buying.sec_bulk_parsed_snapshot import (
    LoadedSecBulkParsedSnapshot,
    SecBulkParsedSnapshotError,
    load_sec_bulk_parsed_snapshot,
)


EDGAR_ACCEPTANCE_SNAPSHOT_KIND = "sec-edgar-acceptance-quarter"
EDGAR_ACCEPTANCE_SNAPSHOT_CONTRACT_VERSION = 1
SEC_EDGAR_METADATA_PARSER_VERSION = "INSETF-IB1C-EDGAR-METADATA-v1"

# IB-1C is deliberately a bounded in-memory boundary.  Raising these limits
# requires a separately reviewed streaming design and real-package capacity
# evidence; a constant-only change is not sufficient.
MAX_METADATA_SOURCE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_METADATA_SOURCE_BYTES = 64 * 1024 * 1024
MAX_METADATA_SOURCES = 250_000
MAX_ACCEPTANCE_RECORDS = 2_000_000
MAX_METADATA_FIELDS = 256
MAX_METADATA_FIELD_NAME_CHARACTERS = 128
MAX_METADATA_FIELD_CHARACTERS = 256 * 1024
MAX_URL_CHARACTERS = 8 * 1024
MAX_ACCEPTANCE_BUNDLE_BYTES = 256 * 1024 * 1024
MAX_SOURCE_JSON_NESTING_DEPTH = 1
MAX_BUNDLE_JSON_NESTING_DEPTH = 8
MAX_PUBLISHER_TEMPORARIES = 1_024
SEC_FILING_DAY_CONSERVATIVE_UTC_HOUR = 5

_LOCK_SUFFIX = ".publication.lock"
_BUNDLE_ID_RE = re.compile(
    r"^sec-edgar-acceptance-[0-9]{4}q[1-4]-[0-9a-f]{16}\.json$"
)
_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_FILING_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_ACCEPTED_AT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}[+-][0-9]{2}:[0-9]{2}$"
)
_SEC_URL_RE = re.compile(
    r"^https://(?P<host>www\.sec\.gov|data\.sec\.gov)"
    r"(?P<path>/[A-Za-z0-9._~!$&'()*+,;=:@/-]*)$"
)

_PROFILE_KEYS = {
    "profile_id",
    "exact_fields",
    "accession_number_field",
    "form_type_field",
    "filing_date_field",
    "accepted_at_field",
    "primary_document_url_field",
    "valid_from_year",
    "valid_from_quarter",
    "valid_through_year",
    "valid_through_quarter",
}
_SOURCE_IDENTITY_KEYS = {
    "accession_number",
    "metadata_sha256",
    "metadata_size_bytes",
    "source_url",
    "retrieved_at_utc",
    "capture_git_commit",
}
_SOURCE_BUNDLE_KEYS = {
    "metadata_bytes_base64",
    "metadata_sha256",
    "metadata_size_bytes",
    "source_url",
    "retrieved_at_utc",
    "capture_git_commit",
}
_RECORD_KEYS = {
    "accession_number",
    "document_type",
    "submission_row_id",
    "filing_date",
    "availability_tier",
    "next_open_rule",
    "accepted_at",
    "primary_document_url",
    "metadata_source_sha256",
}
_IDENTITY_KEYS = {
    "kind",
    "acceptance_contract_version",
    "parser_version",
    "parser_git_commit",
    "year",
    "quarter",
    "parsed_snapshot_id",
    "parsed_lineage_hash",
    "raw_snapshot_id",
    "raw_lineage_hash",
    "raw_archive_sha256",
    "metadata_profile",
    "metadata_profile_hash",
    "source_inventory",
    "source_inventory_hash",
    "record_count",
    "exact_acceptance_count",
    "filing_date_fallback_count",
    "records_hash",
    "lineage_hash",
    "snapshot_id",
}
_BUNDLE_KEYS = {"identity", "records", "sources"}


class SecEdgarAcceptanceSnapshotError(ValueError):
    """The bounded EDGAR acceptance snapshot contract failed closed."""


class SecEdgarAvailabilityTier(str, Enum):
    """Precision of the evidence establishing public availability."""

    EXACT_ACCEPTANCE_TIMESTAMP = "exact_acceptance_timestamp"
    FILING_DATE_FALLBACK = "filing_date_fallback"


class SecEdgarAvailabilityRule(str, Enum):
    """Conservative execution timing attached to one evidence tier."""

    NEXT_OPEN_AFTER_ACCEPTANCE = "next-open-after-acceptance"
    NEXT_OPEN_AFTER_FILING_DATE = "next-open-after-filing-date"


def _period_index(year: object, quarter: object, *, label: str) -> int:
    if type(year) is not int or not 2006 <= year <= 9999:
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} year must be an exact integer from 2006"
        )
    if type(quarter) is not int or quarter not in {1, 2, 3, 4}:
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} quarter must be an exact integer from 1 through 4"
        )
    return year * 4 + quarter - 1


def _canonical_json_bytes(payload: object) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _canonical_utc(value: datetime, *, label: str) -> str:
    if type(value) is not datetime:
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} must be a timezone-aware datetime"
        )
    try:
        offset = value.utcoffset()
        result = value.astimezone(timezone.utc).isoformat()
    except (OverflowError, TypeError, ValueError) as exc:
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} cannot be represented in UTC"
        ) from exc
    if offset is None or value.microsecond != 0:
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} must be an offset-aware second-resolution datetime"
        )
    return result


def _acceptance_outside_sec_filing_day(
    value: datetime, filing_date: date
) -> bool:
    """Apply a reproducible [05:00Z, next-day 05:00Z) filing-day window."""

    try:
        floor = datetime(
            filing_date.year,
            filing_date.month,
            filing_date.day,
            SEC_FILING_DAY_CONSERVATIVE_UTC_HOUR,
            tzinfo=timezone.utc,
        )
        next_date = filing_date + timedelta(days=1)
        ceiling = datetime(
            next_date.year,
            next_date.month,
            next_date.day,
            SEC_FILING_DAY_CONSERVATIVE_UTC_HOUR,
            tzinfo=timezone.utc,
        )
        instant = value.astimezone(timezone.utc)
        return instant < floor or instant >= ceiling
    except (OverflowError, TypeError, ValueError) as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance cannot be compared with the SEC filing-day window"
        ) from exc


def _validate_sec_source_url(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_URL_CHARACTERS
        or any(character.isspace() for character in value)
    ):
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} must be a canonical bounded HTTPS URL"
        )
    match = _SEC_URL_RE.fullmatch(value)
    if match is None:
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} must be a canonical bounded HTTPS URL"
        )
    path = match.group("path")
    if "//" in path or any(
        segment in {".", ".."} for segment in path.split("/")
    ):
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} must be a canonical bounded HTTPS URL"
        )
    return value


def _sec_url_parts(value: str) -> tuple[str, str]:
    match = _SEC_URL_RE.fullmatch(value)
    if match is None:  # Callers validate first; retain a fail-closed guard.
        raise SecEdgarAcceptanceSnapshotError("REFUSED: SEC URL is invalid")
    return match.group("host"), match.group("path")


def _validate_source_url_accession(
    value: str,
    *,
    accession_number: str,
    issuer_cik: str | None = None,
) -> None:
    _validate_sec_source_url(value, label="metadata source URL")
    host, path = _sec_url_parts(value)
    compact_accession = accession_number.replace("-", "")
    if compact_accession not in path.split("/"):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata source URL path does not match its accession"
        )
    segments = path.split("/")
    if (
        issuer_cik is not None
        and segments[1:4] == ["Archives", "edgar", "data"]
        and (
            host != "www.sec.gov"
            or len(segments) != 7
            or not segments[4].isdigit()
            or segments[4] != str(int(issuer_cik))
            or segments[5] != compact_accession
            or not segments[6]
        )
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata source URL path disagrees with upstream issuer lineage"
        )


def _validate_primary_document_url(
    value: object,
    *,
    accession_number: str,
    issuer_cik: str | None = None,
) -> str:
    result = _validate_sec_source_url(value, label="primary document URL")
    host, path = _sec_url_parts(result)
    compact_accession = accession_number.replace("-", "")
    segments = path.split("/")
    if host != "www.sec.gov" or len(segments) != 7 or segments[1:4] != [
        "Archives",
        "edgar",
        "data",
    ] or not segments[4].isdigit() or segments[5] != compact_accession or not (
        segments[6]
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: primary document URL must be a www.sec.gov Archives path "
            "for the evidence accession"
        )
    if issuer_cik is not None and segments[4] != str(int(issuer_cik)):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: primary document URL path does not match the upstream issuer CIK"
        )
    return result


@dataclass(frozen=True)
class SecEdgarMetadataSchemaProfile:
    """Caller-supplied exact JSON schema for one inclusive quarter range.

    This contract is a mapping only; it does not claim that any profile is an
    official SEC schema.  In particular, the acceptance field is explicitly
    prohibited from naming a transaction-date field.
    """

    profile_id: str
    exact_fields: tuple[str, ...]
    accession_number_field: str
    form_type_field: str
    filing_date_field: str
    accepted_at_field: str
    primary_document_url_field: str
    valid_from_year: int
    valid_from_quarter: int
    valid_through_year: int
    valid_through_quarter: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or _IDENTIFIER_RE.fullmatch(self.profile_id) is None
        ):
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: metadata profile ID must be a canonical bounded identifier"
            )
        if (
            type(self.exact_fields) is not tuple
            or not self.exact_fields
            or len(self.exact_fields) > MAX_METADATA_FIELDS
            or any(
                not isinstance(name, str)
                or len(name) > MAX_METADATA_FIELD_NAME_CHARACTERS
                or _FIELD_NAME_RE.fullmatch(name) is None
                for name in self.exact_fields
            )
            or len(self.exact_fields) != len(set(self.exact_fields))
            or len(self.exact_fields)
            != len({name.casefold() for name in self.exact_fields})
        ):
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: exact metadata fields must be a unique immutable tuple"
            )
        mappings = (
            self.accession_number_field,
            self.form_type_field,
            self.filing_date_field,
            self.accepted_at_field,
            self.primary_document_url_field,
        )
        if (
            any(not isinstance(name, str) or name not in self.exact_fields for name in mappings)
            or len(set(mappings)) != len(mappings)
        ):
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: metadata field mappings must be distinct exact-profile members"
            )
        normalized_acceptance_name = re.sub(
            r"[^a-z0-9]", "", self.accepted_at_field.casefold()
        )
        if "transaction" in normalized_acceptance_name:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: a transaction-date field cannot establish availability"
            )
        start = _period_index(
            self.valid_from_year, self.valid_from_quarter, label="profile start"
        )
        end = _period_index(
            self.valid_through_year,
            self.valid_through_quarter,
            label="profile end",
        )
        if start > end:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: metadata profile quarter range is reversed"
            )

    def covers(self, year: int, quarter: int) -> bool:
        period = _period_index(year, quarter, label="upstream snapshot")
        start = self.valid_from_year * 4 + self.valid_from_quarter - 1
        end = self.valid_through_year * 4 + self.valid_through_quarter - 1
        return start <= period <= end

    def to_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "exact_fields": list(self.exact_fields),
            "accession_number_field": self.accession_number_field,
            "form_type_field": self.form_type_field,
            "filing_date_field": self.filing_date_field,
            "accepted_at_field": self.accepted_at_field,
            "primary_document_url_field": self.primary_document_url_field,
            "valid_from_year": self.valid_from_year,
            "valid_from_quarter": self.valid_from_quarter,
            "valid_through_year": self.valid_through_year,
            "valid_through_quarter": self.valid_through_quarter,
        }

    @classmethod
    def from_payload(cls, payload: object) -> "SecEdgarMetadataSchemaProfile":
        if not isinstance(payload, dict) or set(payload) != _PROFILE_KEYS:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: metadata profile payload fields are not exact"
            )
        exact_fields = payload.get("exact_fields")
        if not isinstance(exact_fields, list):
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: metadata profile exact fields are malformed"
            )
        return cls(
            profile_id=payload.get("profile_id"),
            exact_fields=tuple(exact_fields),
            accession_number_field=payload.get("accession_number_field"),
            form_type_field=payload.get("form_type_field"),
            filing_date_field=payload.get("filing_date_field"),
            accepted_at_field=payload.get("accepted_at_field"),
            primary_document_url_field=payload.get("primary_document_url_field"),
            valid_from_year=payload.get("valid_from_year"),
            valid_from_quarter=payload.get("valid_from_quarter"),
            valid_through_year=payload.get("valid_through_year"),
            valid_through_quarter=payload.get("valid_through_quarter"),
        )


@dataclass(frozen=True)
class SecEdgarMetadataSource:
    """Exact bytes plus asserted, syntax-checked capture provenance.

    Construction does not authenticate origin, transport, time, or Git state.
    """

    metadata_bytes: bytes
    source_url: str
    retrieved_at: datetime
    capture_git_commit: str
    _retrieved_at_utc: str = field(init=False, repr=False, compare=False)
    _metadata_sha256: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            type(self.metadata_bytes) is not bytes
            or not self.metadata_bytes
            or len(self.metadata_bytes) > MAX_METADATA_SOURCE_BYTES
        ):
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: metadata source must be a non-empty bounded exact byte image"
            )
        _validate_sec_source_url(self.source_url, label="metadata source URL")
        if (
            not isinstance(self.capture_git_commit, str)
            or _GIT_COMMIT_RE.fullmatch(self.capture_git_commit) is None
        ):
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: capture Git commit must be a full lowercase SHA-1"
            )
        retrieved_at_utc = _canonical_utc(
            self.retrieved_at, label="metadata retrieval time"
        )
        object.__setattr__(self, "retrieved_at", datetime.fromisoformat(retrieved_at_utc))
        object.__setattr__(self, "_retrieved_at_utc", retrieved_at_utc)
        object.__setattr__(self, "_metadata_sha256", hash_bytes(self.metadata_bytes))

    @property
    def retrieved_at_utc(self) -> str:
        return self._retrieved_at_utc

    @property
    def metadata_sha256(self) -> str:
        return self._metadata_sha256


@dataclass(frozen=True)
class SecEdgarMetadataSourceIdentity:
    accession_number: str
    metadata_sha256: str
    metadata_size_bytes: int
    source_url: str
    retrieved_at_utc: str
    capture_git_commit: str

    def to_payload(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "metadata_sha256": self.metadata_sha256,
            "metadata_size_bytes": self.metadata_size_bytes,
            "source_url": self.source_url,
            "retrieved_at_utc": self.retrieved_at_utc,
            "capture_git_commit": self.capture_git_commit,
        }


@dataclass(frozen=True)
class SecEdgarAvailabilityRecord:
    accession_number: str
    document_type: str
    submission_row_id: str
    filing_date: date
    availability_tier: SecEdgarAvailabilityTier
    next_open_rule: SecEdgarAvailabilityRule
    accepted_at: datetime | None
    primary_document_url: str | None
    metadata_source_sha256: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.accession_number, str)
            or _ACCESSION_RE.fullmatch(self.accession_number) is None
            or not isinstance(self.document_type, str)
            or not self.document_type
            or self.document_type != self.document_type.strip()
            or type(self.filing_date) is not date
            or not isinstance(self.availability_tier, SecEdgarAvailabilityTier)
            or not isinstance(self.next_open_rule, SecEdgarAvailabilityRule)
            or not isinstance(self.submission_row_id, str)
            or _SHA256_RE.fullmatch(self.submission_row_id) is None
        ):
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: acceptance record core fields are invalid"
            )
        if (
            self.availability_tier
            is SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
        ):
            accepted_at_utc = _canonical_utc(
                self.accepted_at, label="exact acceptance timestamp"
            )
            object.__setattr__(
                self, "accepted_at", datetime.fromisoformat(accepted_at_utc)
            )
            if (
                _acceptance_outside_sec_filing_day(
                    self.accepted_at, self.filing_date
                )
                or self.next_open_rule
                is not SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE
                or not isinstance(self.primary_document_url, str)
                or not isinstance(self.metadata_source_sha256, str)
                or _SHA256_RE.fullmatch(self.metadata_source_sha256) is None
            ):
                raise SecEdgarAcceptanceSnapshotError(
                    "REFUSED: exact acceptance availability is internally inconsistent"
                )
            _validate_primary_document_url(
                self.primary_document_url,
                accession_number=self.accession_number,
            )
        else:
            if (
                self.accepted_at is not None
                or self.next_open_rule
                is not SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_FILING_DATE
                or self.primary_document_url is not None
                or self.metadata_source_sha256 is not None
            ):
                raise SecEdgarAcceptanceSnapshotError(
                    "REFUSED: date-only fallback cannot contain exact-source evidence"
                )

    def to_payload(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "document_type": self.document_type,
            "submission_row_id": self.submission_row_id,
            "filing_date": self.filing_date.isoformat(),
            "availability_tier": self.availability_tier.value,
            "next_open_rule": self.next_open_rule.value,
            "accepted_at": (
                self.accepted_at.isoformat(timespec="seconds")
                if self.accepted_at is not None
                else None
            ),
            "primary_document_url": self.primary_document_url,
            "metadata_source_sha256": self.metadata_source_sha256,
        }


@dataclass(frozen=True)
class SecEdgarAcceptanceSnapshotIdentity:
    year: int
    quarter: int
    parser_git_commit: str
    parsed_snapshot_id: str
    parsed_lineage_hash: str
    raw_snapshot_id: str
    raw_lineage_hash: str
    raw_archive_sha256: str
    metadata_profile: SecEdgarMetadataSchemaProfile
    metadata_profile_hash: str
    source_inventory: tuple[SecEdgarMetadataSourceIdentity, ...]
    source_inventory_hash: str
    record_count: int
    exact_acceptance_count: int
    filing_date_fallback_count: int
    records_hash: str
    lineage_hash: str
    snapshot_id: str

    def lineage_payload(self) -> dict[str, object]:
        return {
            "kind": EDGAR_ACCEPTANCE_SNAPSHOT_KIND,
            "acceptance_contract_version": EDGAR_ACCEPTANCE_SNAPSHOT_CONTRACT_VERSION,
            "parser_version": SEC_EDGAR_METADATA_PARSER_VERSION,
            "parser_git_commit": self.parser_git_commit,
            "year": self.year,
            "quarter": self.quarter,
            "parsed_snapshot_id": self.parsed_snapshot_id,
            "parsed_lineage_hash": self.parsed_lineage_hash,
            "raw_snapshot_id": self.raw_snapshot_id,
            "raw_lineage_hash": self.raw_lineage_hash,
            "raw_archive_sha256": self.raw_archive_sha256,
            "metadata_profile": self.metadata_profile.to_payload(),
            "metadata_profile_hash": self.metadata_profile_hash,
            "source_inventory": [
                item.to_payload() for item in self.source_inventory
            ],
            "source_inventory_hash": self.source_inventory_hash,
            "record_count": self.record_count,
            "exact_acceptance_count": self.exact_acceptance_count,
            "filing_date_fallback_count": self.filing_date_fallback_count,
            "records_hash": self.records_hash,
        }

    def to_payload(self) -> dict[str, object]:
        return {
            **self.lineage_payload(),
            "lineage_hash": self.lineage_hash,
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True)
class LoadedSecEdgarAcceptanceSnapshot:
    identity: SecEdgarAcceptanceSnapshotIdentity
    records: tuple[SecEdgarAvailabilityRecord, ...]
    sources: tuple[SecEdgarMetadataSource, ...]


@dataclass(frozen=True)
class _ParsedMetadataSource:
    source: SecEdgarMetadataSource
    accession_number: str
    document_type: str
    filing_date: date
    accepted_at: datetime
    primary_document_url: str

    @property
    def identity(self) -> SecEdgarMetadataSourceIdentity:
        return SecEdgarMetadataSourceIdentity(
            accession_number=self.accession_number,
            metadata_sha256=self.source.metadata_sha256,
            metadata_size_bytes=len(self.source.metadata_bytes),
            source_url=self.source.source_url,
            retrieved_at_utc=self.source.retrieved_at_utc,
            capture_git_commit=self.source.capture_git_commit,
        )

    def bundle_payload(self) -> dict[str, object]:
        return {
            "metadata_bytes_base64": base64.b64encode(
                self.source.metadata_bytes
            ).decode("ascii"),
            "metadata_sha256": self.source.metadata_sha256,
            "metadata_size_bytes": len(self.source.metadata_bytes),
            "source_url": self.source.source_url,
            "retrieved_at_utc": self.source.retrieved_at_utc,
            "capture_git_commit": self.source.capture_git_commit,
        }


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant {value!r}")


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _require_bounded_json_nesting(
    text: str, *, max_depth: int, label: str
) -> None:
    """Reject structural amplification before the recursive JSON decoder runs."""

    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > max_depth:
                raise SecEdgarAcceptanceSnapshotError(
                    f"REFUSED: {label} exceeds its JSON nesting-depth limit"
                )
        elif character in "]}":
            depth -= 1


def _parse_exact_metadata_object(
    metadata_bytes: bytes,
    exact_fields: tuple[str, ...],
    *,
    label: str = "metadata source",
) -> dict[str, str]:
    """Parse one strict, flat JSON object against an exact field vector.

    The helper is package-private so downstream offline contracts can inspect
    extra fields already retained inside an IB-1C-verified byte image without
    creating another evidence source or weakening duplicate-key, UTF-8,
    nesting, and field-size checks.
    """

    if (
        type(metadata_bytes) is not bytes
        or not metadata_bytes
        or len(metadata_bytes) > MAX_METADATA_SOURCE_BYTES
        or type(exact_fields) is not tuple
        or not exact_fields
        or len(exact_fields) > MAX_METADATA_FIELDS
        or any(
            not isinstance(name, str)
            or len(name) > MAX_METADATA_FIELD_NAME_CHARACTERS
            or _FIELD_NAME_RE.fullmatch(name) is None
            for name in exact_fields
        )
        or len(exact_fields) != len(set(exact_fields))
        or len(exact_fields) != len({name.casefold() for name in exact_fields})
    ):
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} exact-field contract is invalid"
        )
    try:
        text = metadata_bytes.decode("utf-8", errors="strict")
        _require_bounded_json_nesting(
            text,
            max_depth=MAX_SOURCE_JSON_NESTING_DEPTH,
            label=label,
        )
        payload = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (RecursionError, UnicodeDecodeError, ValueError) as exc:
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} is not strict duplicate-free UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict) or set(payload) != set(exact_fields):
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} fields do not match the exact profile"
        )
    if any(
        not isinstance(value, str) or len(value) > MAX_METADATA_FIELD_CHARACTERS
        for value in payload.values()
    ):
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} field exceeds its character limit"
        )
    return payload


def _parse_source_json(
    source: SecEdgarMetadataSource,
    profile: SecEdgarMetadataSchemaProfile,
) -> _ParsedMetadataSource:
    payload = _parse_exact_metadata_object(
        source.metadata_bytes,
        profile.exact_fields,
    )

    accession_number = payload[profile.accession_number_field]
    document_type = payload[profile.form_type_field]
    filing_date_text = payload[profile.filing_date_field]
    accepted_at_text = payload[profile.accepted_at_field]
    primary_document_url = payload[profile.primary_document_url_field]
    if (
        _ACCESSION_RE.fullmatch(accession_number) is None
        or not document_type
        or document_type != document_type.strip()
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata accession or form type is invalid"
        )
    if _FILING_DATE_RE.fullmatch(filing_date_text) is None:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata filing date must be canonical ISO date text"
        )
    try:
        filing_date = date.fromisoformat(filing_date_text)
    except ValueError as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata filing date is invalid"
        ) from exc
    if (
        _ACCEPTED_AT_RE.fullmatch(accepted_at_text) is None
        or accepted_at_text.endswith("-00:00")
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance must be an explicit-offset second-resolution timestamp"
        )
    try:
        accepted_at = datetime.fromisoformat(accepted_at_text)
        offset = accepted_at.utcoffset()
    except (OverflowError, TypeError, ValueError) as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance timestamp is invalid"
        ) from exc
    if offset is None or accepted_at.microsecond != 0:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance must be an explicit-offset second-resolution timestamp"
        )
    primary_document_url = _validate_primary_document_url(
        primary_document_url, accession_number=accession_number
    )
    _validate_source_url_accession(
        source.source_url, accession_number=accession_number
    )
    return _ParsedMetadataSource(
        source=source,
        accession_number=accession_number,
        document_type=document_type,
        filing_date=filing_date,
        accepted_at=accepted_at,
        primary_document_url=primary_document_url,
    )


def _submission_rows(
    loaded: LoadedSecBulkParsedSnapshot,
) -> dict[str, tuple[object, str, date, str]]:
    try:
        submission_identity = next(
            table
            for table in loaded.identity.tables
            if table.table_name == "SUBMISSION.tsv"
        )
        accession_index = submission_identity.headers.index("ACCESSION_NUMBER")
        document_type_index = submission_identity.headers.index("DOCUMENT_TYPE")
        filing_date_index = submission_identity.headers.index("FILING_DATE")
        issuer_cik_index = submission_identity.headers.index("ISSUERCIK")
    except (StopIteration, ValueError) as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: parsed snapshot lacks the issuer-neutral submission projection"
        ) from exc
    by_row_id = {
        row.row_id: row
        for row in loaded.rows
        if row.table_name == "SUBMISSION.tsv"
    }
    result: dict[str, tuple[object, str, date, str]] = {}
    for accession in loaded.accessions:
        row = by_row_id.get(accession.submission_row_id)
        if row is None:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: parsed accession lacks its submission source row"
            )
        values = row.values
        if (
            values[accession_index] != accession.accession_number
            or values[document_type_index] != accession.document_type
        ):
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: parsed accession disagrees with its submission source row"
            )
        filing_date_text = values[filing_date_index]
        if _FILING_DATE_RE.fullmatch(filing_date_text) is None:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: upstream SUBMISSION filing date is not canonical ISO text"
            )
        try:
            filing_date = date.fromisoformat(filing_date_text)
        except ValueError as exc:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: upstream SUBMISSION filing date is invalid"
            ) from exc
        filing_quarter = (filing_date.month - 1) // 3 + 1
        accession_year = int(accession.accession_number[11:13])
        if (
            filing_date.year != loaded.identity.year
            or filing_quarter != loaded.identity.quarter
            or filing_date.year % 100 != accession_year
        ):
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: upstream filing date disagrees with snapshot quarter "
                "or accession year"
            )
        issuer_cik = values[issuer_cik_index]
        if re.fullmatch(r"[0-9]{10}", issuer_cik) is None or int(issuer_cik) == 0:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: upstream SUBMISSION issuer CIK is invalid"
            )
        result[accession.accession_number] = (
            row,
            accession.document_type,
            filing_date,
            issuer_cik,
        )
    if len(result) != len(loaded.accessions):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: upstream parsed accessions are not unique"
        )
    return result


def _assemble_acceptance_snapshot(
    parsed_snapshot_directory: str | Path,
    raw_snapshot_directory: str | Path,
    *,
    sources: tuple[SecEdgarMetadataSource, ...],
    metadata_profile: SecEdgarMetadataSchemaProfile,
    parser_git_commit: str,
) -> tuple[
    SecEdgarAcceptanceSnapshotIdentity,
    tuple[SecEdgarAvailabilityRecord, ...],
    tuple[_ParsedMetadataSource, ...],
    bytes,
]:
    if type(metadata_profile) is not SecEdgarMetadataSchemaProfile:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: an explicit immutable EDGAR metadata profile is required"
        )
    if (
        not isinstance(parser_git_commit, str)
        or _GIT_COMMIT_RE.fullmatch(parser_git_commit) is None
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: parser Git commit must be a full lowercase SHA-1"
        )
    if (
        type(sources) is not tuple
        or len(sources) > MAX_METADATA_SOURCES
        or any(type(source) is not SecEdgarMetadataSource for source in sources)
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata sources must be a bounded immutable tuple"
        )
    if sum(len(source.metadata_bytes) for source in sources) > (
        MAX_TOTAL_METADATA_SOURCE_BYTES
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata sources exceed the total byte-size limit"
        )
    try:
        loaded = load_sec_bulk_parsed_snapshot(
            parsed_snapshot_directory,
            raw_snapshot_directory=raw_snapshot_directory,
        )
    except SecBulkParsedSnapshotError as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: parsed SEC snapshot failed raw-bound integrity validation"
        ) from exc
    upstream = loaded.identity
    if not metadata_profile.covers(upstream.year, upstream.quarter):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata profile does not cover the upstream snapshot quarter"
        )
    submission_by_accession = _submission_rows(loaded)
    if len(submission_by_accession) > MAX_ACCEPTANCE_RECORDS:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: upstream accessions exceed the acceptance-record limit"
        )

    parsed_sources = tuple(
        sorted(
            (_parse_source_json(source, metadata_profile) for source in sources),
            key=lambda item: (item.accession_number, item.source.metadata_sha256),
        )
    )
    source_by_accession: dict[str, _ParsedMetadataSource] = {}
    for parsed_source in parsed_sources:
        if parsed_source.accession_number in source_by_accession:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: more than one metadata source names an accession"
            )
        upstream_submission = submission_by_accession.get(
            parsed_source.accession_number
        )
        if upstream_submission is None:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: metadata source accession is absent upstream"
            )
        _, upstream_form, upstream_filing_date, upstream_issuer_cik = (
            upstream_submission
        )
        if (
            parsed_source.document_type != upstream_form
            or parsed_source.filing_date != upstream_filing_date
        ):
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: metadata source form or filing date disagrees upstream"
            )
        if _acceptance_outside_sec_filing_day(
            parsed_source.accepted_at, upstream_filing_date
        ):
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: acceptance timestamp is outside the upstream filing-date window"
            )
        try:
            retrieved_at = datetime.fromisoformat(
                parsed_source.source.retrieved_at_utc
            )
            retrieved_before_acceptance = (
                retrieved_at < parsed_source.accepted_at
            )
        except (OverflowError, TypeError, ValueError) as exc:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: acceptance and retrieval instants cannot be compared"
            ) from exc
        if retrieved_before_acceptance:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: metadata retrieval time precedes its acceptance timestamp"
            )
        _validate_primary_document_url(
            parsed_source.primary_document_url,
            accession_number=parsed_source.accession_number,
            issuer_cik=upstream_issuer_cik,
        )
        _validate_source_url_accession(
            parsed_source.source.source_url,
            accession_number=parsed_source.accession_number,
            issuer_cik=upstream_issuer_cik,
        )
        source_by_accession[parsed_source.accession_number] = parsed_source

    records: list[SecEdgarAvailabilityRecord] = []
    for accession_number in sorted(submission_by_accession):
        submission_row, document_type, filing_date_value, _ = (
            submission_by_accession[accession_number]
        )
        parsed_source = source_by_accession.get(accession_number)
        if parsed_source is None:
            record = SecEdgarAvailabilityRecord(
                accession_number=accession_number,
                document_type=document_type,
                submission_row_id=submission_row.row_id,
                filing_date=filing_date_value,
                availability_tier=SecEdgarAvailabilityTier.FILING_DATE_FALLBACK,
                next_open_rule=SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_FILING_DATE,
                accepted_at=None,
                primary_document_url=None,
                metadata_source_sha256=None,
            )
        else:
            record = SecEdgarAvailabilityRecord(
                accession_number=accession_number,
                document_type=document_type,
                submission_row_id=submission_row.row_id,
                filing_date=filing_date_value,
                availability_tier=(
                    SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
                ),
                next_open_rule=SecEdgarAvailabilityRule.NEXT_OPEN_AFTER_ACCEPTANCE,
                accepted_at=parsed_source.accepted_at,
                primary_document_url=parsed_source.primary_document_url,
                metadata_source_sha256=parsed_source.source.metadata_sha256,
            )
        records.append(record)
    records_tuple = tuple(records)
    source_inventory = tuple(item.identity for item in parsed_sources)
    profile_hash = hash_payload(metadata_profile.to_payload())
    source_inventory_hash = hash_payload(
        [item.to_payload() for item in source_inventory]
    )
    records_hash = hash_payload([item.to_payload() for item in records_tuple])
    partial = SecEdgarAcceptanceSnapshotIdentity(
        year=upstream.year,
        quarter=upstream.quarter,
        parser_git_commit=parser_git_commit,
        parsed_snapshot_id=upstream.snapshot_id,
        parsed_lineage_hash=upstream.lineage_hash,
        raw_snapshot_id=upstream.raw_snapshot_id,
        raw_lineage_hash=upstream.raw_lineage_hash,
        raw_archive_sha256=upstream.raw_archive_sha256,
        metadata_profile=metadata_profile,
        metadata_profile_hash=profile_hash,
        source_inventory=source_inventory,
        source_inventory_hash=source_inventory_hash,
        record_count=len(records_tuple),
        exact_acceptance_count=len(parsed_sources),
        filing_date_fallback_count=len(records_tuple) - len(parsed_sources),
        records_hash=records_hash,
        lineage_hash="",
        snapshot_id="",
    )
    lineage_hash = hash_payload(partial.lineage_payload())
    snapshot_id = (
        f"sec-edgar-acceptance-{upstream.year}q{upstream.quarter}-"
        f"{lineage_hash[:16]}"
    )
    identity = SecEdgarAcceptanceSnapshotIdentity(
        **{
            **partial.__dict__,
            "lineage_hash": lineage_hash,
            "snapshot_id": snapshot_id,
        }
    )
    bundle_bytes = _canonical_json_bytes(
        {
            "identity": identity.to_payload(),
            "records": [item.to_payload() for item in records_tuple],
            "sources": [item.bundle_payload() for item in parsed_sources],
        }
    )
    if len(bundle_bytes) > MAX_ACCEPTANCE_BUNDLE_BYTES:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance snapshot exceeds its canonical bundle-size limit"
        )
    return identity, records_tuple, parsed_sources, bundle_bytes


def _status_is_redirect(value: os.stat_result) -> bool:
    file_attributes = getattr(value, "st_file_attributes", 0)
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(value.st_mode) or bool(file_attributes & reparse_attribute)


def _same_file_identity(first: os.stat_result, second: os.stat_result) -> bool:
    if (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino):
        return True
    return os.name == "nt" and (
        getattr(first, "st_file_attributes", None)
        == getattr(second, "st_file_attributes", None)
        and first.st_size == second.st_size
        and first.st_ctime_ns == second.st_ctime_ns
    )


def _same_file_version(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        _same_file_identity(first, second)
        and first.st_size == second.st_size
        and first.st_mtime_ns == second.st_mtime_ns
    )


def _require_regular_directory(
    path: Path, *, label: str, missing_ok: bool = False
) -> bool:
    try:
        value = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return False
        raise SecEdgarAcceptanceSnapshotError(f"REFUSED: {label} is missing")
    except OSError as exc:
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} is unreadable"
        ) from exc
    if _status_is_redirect(value) or not stat.S_ISDIR(value.st_mode):
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} must be a regular directory"
        )
    return True


def _read_regular_bytes(
    path: Path,
    *,
    label: str,
    max_bytes: int,
    require_single_link: bool = False,
) -> bytes:
    try:
        before = path.lstat()
        if (
            _status_is_redirect(before)
            or not stat.S_ISREG(before.st_mode)
            or (require_single_link and before.st_nlink != 1)
        ):
            raise SecEdgarAcceptanceSnapshotError(
                f"REFUSED: {label} must be a single-link regular immutable file"
            )
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                _status_is_redirect(opened)
                or not stat.S_ISREG(opened.st_mode)
                or not _same_file_identity(before, opened)
                or (require_single_link and opened.st_nlink != 1)
            ):
                raise SecEdgarAcceptanceSnapshotError(
                    f"REFUSED: {label} changed while it was opened"
                )
            if opened.st_size > max_bytes:
                raise SecEdgarAcceptanceSnapshotError(
                    f"REFUSED: {label} exceeds its byte-size limit"
                )
            raw = handle.read(max_bytes + 1)
            after_read = os.fstat(handle.fileno())
        after_path = path.lstat()
        if (
            not _same_file_version(opened, after_read)
            or not _same_file_version(after_read, after_path)
            or (
                require_single_link
                and (after_read.st_nlink != 1 or after_path.st_nlink != 1)
            )
        ):
            raise SecEdgarAcceptanceSnapshotError(
                f"REFUSED: {label} changed while it was read"
            )
        if len(raw) != after_read.st_size:
            raise SecEdgarAcceptanceSnapshotError(
                f"REFUSED: {label} was not read as one complete byte image"
            )
        if len(raw) > max_bytes:
            raise SecEdgarAcceptanceSnapshotError(
                f"REFUSED: {label} exceeds its byte-size limit"
            )
        return raw
    except SecEdgarAcceptanceSnapshotError:
        raise
    except OSError as exc:
        raise SecEdgarAcceptanceSnapshotError(
            f"REFUSED: {label} is missing or unreadable"
        ) from exc


def _prepare_output_root(output_root: str | Path) -> Path:
    try:
        root = Path(output_root)
        if not _require_regular_directory(
            root, label="acceptance output root", missing_ok=True
        ):
            root.mkdir(parents=True, exist_ok=True)
        _require_regular_directory(root, label="acceptance output root")
        canonical_root = root.resolve(strict=True)
        _require_regular_directory(canonical_root, label="acceptance output root")
        return canonical_root
    except SecEdgarAcceptanceSnapshotError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance output root is invalid or unavailable"
        ) from exc


def _require_regular_lock_slot(lock_path: Path) -> None:
    try:
        value = lock_path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance publication lock is unreadable"
        ) from exc
    if (
        _status_is_redirect(value)
        or not stat.S_ISREG(value.st_mode)
        or value.st_nlink != 1
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance publication lock must be a single-link regular file"
        )


class _AcceptancePublicationLock:
    def __init__(self, lock_path: Path) -> None:
        self._manager = exclusive_file_lock(lock_path)

    def __enter__(self):
        try:
            return self._manager.__enter__()
        except OSError as exc:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: acceptance publication lock could not be acquired"
            ) from exc

    def __exit__(self, exc_type, exc, traceback):
        try:
            return self._manager.__exit__(exc_type, exc, traceback)
        except OSError as lock_exc:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: acceptance publication lock could not be released"
            ) from lock_exc


def _publisher_temporaries(root: Path, target_name: str) -> tuple[Path, ...]:
    matching: list[Path] = []
    try:
        for path in root.iterdir():
            if not (
                path.name.startswith(f".{target_name}.")
                and path.name.endswith(".tmp")
            ):
                continue
            if len(matching) >= MAX_PUBLISHER_TEMPORARIES:
                raise SecEdgarAcceptanceSnapshotError(
                    "REFUSED: acceptance publisher temporary count exceeds its limit"
                )
            matching.append(path)
    except SecEdgarAcceptanceSnapshotError:
        raise
    except OSError as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance output root is unreadable"
        ) from exc
    return tuple(matching)


def _clean_verified_temporaries(
    root: Path,
    target_name: str,
    expected: bytes,
    *,
    allow_prefix: bool,
) -> None:
    """Classify all matching residue before deleting any of it."""

    failures: list[str] = []
    verified: list[Path] = []
    for path in _publisher_temporaries(root, target_name):
        try:
            actual = _read_regular_bytes(
                path,
                label=f"acceptance publisher temporary {path.name}",
                max_bytes=len(expected),
            )
            if actual != expected and not (allow_prefix and expected.startswith(actual)):
                failures.append(path.name)
            else:
                verified.append(path)
        except SecEdgarAcceptanceSnapshotError:
            failures.append(path.name)
    if failures:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance publication left unverified files: "
            + ", ".join(sorted(set(failures)))
        )
    unlink_failures: list[str] = []
    for path in verified:
        try:
            path.unlink()
        except OSError:
            unlink_failures.append(path.name)
    if unlink_failures:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance publication left unverified files: "
            + ", ".join(sorted(set(unlink_failures)))
        )


def _parse_canonical_bundle(raw: bytes) -> dict[str, object]:
    try:
        text = raw.decode("utf-8", errors="strict")
        _require_bounded_json_nesting(
            text,
            max_depth=MAX_BUNDLE_JSON_NESTING_DEPTH,
            label="acceptance bundle",
        )
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
        canonical = _canonical_json_bytes(value)
    except (RecursionError, UnicodeDecodeError, TypeError, ValueError) as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance bundle is not valid canonical JSON"
        ) from exc
    if not isinstance(value, dict) or raw != canonical or set(value) != _BUNDLE_KEYS:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance bundle fields or canonical encoding are invalid"
        )
    return value


def _parse_canonical_date(value: object, *, label: str) -> date:
    if not isinstance(value, str) or _FILING_DATE_RE.fullmatch(value) is None:
        raise SecEdgarAcceptanceSnapshotError(f"REFUSED: {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SecEdgarAcceptanceSnapshotError(f"REFUSED: {label} is invalid") from exc


def _declared_source_size(payload: object) -> int:
    if not isinstance(payload, dict) or set(payload) != _SOURCE_BUNDLE_KEYS:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: bundled metadata source fields are not exact"
        )
    encoded = payload.get("metadata_bytes_base64")
    declared_size = payload.get("metadata_size_bytes")
    if (
        not isinstance(encoded, str)
        or type(declared_size) is not int
        or not 0 < declared_size <= MAX_METADATA_SOURCE_BYTES
        or len(encoded) != 4 * ((declared_size + 2) // 3)
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: bundled metadata source exceeds its declared byte limit"
        )
    return declared_size


def _source_from_bundle_payload(payload: object) -> SecEdgarMetadataSource:
    declared_size = _declared_source_size(payload)
    encoded = payload.get("metadata_bytes_base64")
    if not isinstance(encoded, str):  # Retain explicit type narrowing.
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: bundled metadata source base64 is invalid"
        )
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: bundled metadata source base64 is invalid"
        ) from exc
    if base64.b64encode(raw).decode("ascii") != encoded:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: bundled metadata source base64 is not canonical"
        )
    retrieved_at = payload.get("retrieved_at_utc")
    if not isinstance(retrieved_at, str):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: bundled metadata retrieval time is invalid"
        )
    try:
        retrieved = datetime.fromisoformat(retrieved_at)
    except ValueError as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: bundled metadata retrieval time is invalid"
        ) from exc
    source = SecEdgarMetadataSource(
        metadata_bytes=raw,
        source_url=payload.get("source_url"),
        retrieved_at=retrieved,
        capture_git_commit=payload.get("capture_git_commit"),
    )
    if (
        source.retrieved_at_utc != retrieved_at
        or payload.get("metadata_sha256") != source.metadata_sha256
        or declared_size != len(source.metadata_bytes)
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: bundled metadata source identity is invalid"
        )
    return source


def _record_from_payload(payload: object) -> SecEdgarAvailabilityRecord:
    if not isinstance(payload, dict) or set(payload) != _RECORD_KEYS:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance record fields are not exact"
        )
    tier_value = payload.get("availability_tier")
    try:
        tier = SecEdgarAvailabilityTier(tier_value)
    except (TypeError, ValueError) as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance availability tier is invalid"
        ) from exc
    accepted_text = payload.get("accepted_at")
    accepted_at: datetime | None
    if accepted_text is None:
        accepted_at = None
    elif (
        isinstance(accepted_text, str)
        and _ACCEPTED_AT_RE.fullmatch(accepted_text)
        and not accepted_text.endswith("-00:00")
    ):
        try:
            accepted_at = datetime.fromisoformat(accepted_text)
        except ValueError as exc:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: acceptance record timestamp is invalid"
            ) from exc
    else:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance record timestamp is invalid"
        )
    rule_value = payload.get("next_open_rule")
    try:
        rule = SecEdgarAvailabilityRule(rule_value)
    except (TypeError, ValueError) as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance next-open rule is invalid"
        ) from exc
    return SecEdgarAvailabilityRecord(
        accession_number=payload.get("accession_number"),
        document_type=payload.get("document_type"),
        submission_row_id=payload.get("submission_row_id"),
        filing_date=_parse_canonical_date(
            payload.get("filing_date"), label="acceptance record filing date"
        ),
        availability_tier=tier,
        next_open_rule=rule,
        accepted_at=accepted_at,
        primary_document_url=payload.get("primary_document_url"),
        metadata_source_sha256=payload.get("metadata_source_sha256"),
    )


def _source_identity_from_payload(payload: object) -> SecEdgarMetadataSourceIdentity:
    if not isinstance(payload, dict) or set(payload) != _SOURCE_IDENTITY_KEYS:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata source identity fields are not exact"
        )
    item = SecEdgarMetadataSourceIdentity(
        accession_number=payload.get("accession_number"),
        metadata_sha256=payload.get("metadata_sha256"),
        metadata_size_bytes=payload.get("metadata_size_bytes"),
        source_url=payload.get("source_url"),
        retrieved_at_utc=payload.get("retrieved_at_utc"),
        capture_git_commit=payload.get("capture_git_commit"),
    )
    if (
        not isinstance(item.accession_number, str)
        or _ACCESSION_RE.fullmatch(item.accession_number) is None
        or not isinstance(item.metadata_sha256, str)
        or _SHA256_RE.fullmatch(item.metadata_sha256) is None
        or type(item.metadata_size_bytes) is not int
        or not 0 < item.metadata_size_bytes <= MAX_METADATA_SOURCE_BYTES
        or not isinstance(item.retrieved_at_utc, str)
        or not isinstance(item.capture_git_commit, str)
        or _GIT_COMMIT_RE.fullmatch(item.capture_git_commit) is None
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata source identity is invalid"
        )
    _validate_sec_source_url(item.source_url, label="metadata source identity URL")
    try:
        retrieved = datetime.fromisoformat(item.retrieved_at_utc)
    except ValueError as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata source identity retrieval time is invalid"
        ) from exc
    if _canonical_utc(retrieved, label="metadata source identity retrieval time") != (
        item.retrieved_at_utc
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: metadata source identity retrieval time is not UTC canonical"
        )
    return item


def _identity_from_payload(
    payload: object, *, file_stem: str
) -> SecEdgarAcceptanceSnapshotIdentity:
    if not isinstance(payload, dict) or set(payload) != _IDENTITY_KEYS:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance snapshot identity fields are not exact"
        )
    profile = SecEdgarMetadataSchemaProfile.from_payload(
        payload.get("metadata_profile")
    )
    inventory_payload = payload.get("source_inventory")
    if not isinstance(inventory_payload, list) or len(inventory_payload) > (
        MAX_METADATA_SOURCES
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance source inventory is invalid"
        )
    inventory = tuple(
        _source_identity_from_payload(item) for item in inventory_payload
    )
    item = SecEdgarAcceptanceSnapshotIdentity(
        year=payload.get("year"),
        quarter=payload.get("quarter"),
        parser_git_commit=payload.get("parser_git_commit"),
        parsed_snapshot_id=payload.get("parsed_snapshot_id"),
        parsed_lineage_hash=payload.get("parsed_lineage_hash"),
        raw_snapshot_id=payload.get("raw_snapshot_id"),
        raw_lineage_hash=payload.get("raw_lineage_hash"),
        raw_archive_sha256=payload.get("raw_archive_sha256"),
        metadata_profile=profile,
        metadata_profile_hash=payload.get("metadata_profile_hash"),
        source_inventory=inventory,
        source_inventory_hash=payload.get("source_inventory_hash"),
        record_count=payload.get("record_count"),
        exact_acceptance_count=payload.get("exact_acceptance_count"),
        filing_date_fallback_count=payload.get("filing_date_fallback_count"),
        records_hash=payload.get("records_hash"),
        lineage_hash=payload.get("lineage_hash"),
        snapshot_id=payload.get("snapshot_id"),
    )
    _period_index(item.year, item.quarter, label="acceptance identity")
    hash_values = (
        item.parsed_lineage_hash,
        item.raw_lineage_hash,
        item.raw_archive_sha256,
        item.metadata_profile_hash,
        item.source_inventory_hash,
        item.records_hash,
        item.lineage_hash,
    )
    if (
        payload.get("kind") != EDGAR_ACCEPTANCE_SNAPSHOT_KIND
        or type(payload.get("acceptance_contract_version")) is not int
        or payload.get("acceptance_contract_version")
        != EDGAR_ACCEPTANCE_SNAPSHOT_CONTRACT_VERSION
        or payload.get("parser_version") != SEC_EDGAR_METADATA_PARSER_VERSION
        or not isinstance(item.parser_git_commit, str)
        or _GIT_COMMIT_RE.fullmatch(item.parser_git_commit) is None
        or not isinstance(item.parsed_snapshot_id, str)
        or not isinstance(item.raw_snapshot_id, str)
        or any(
            not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None
            for value in hash_values
        )
        or type(item.record_count) is not int
        or not 0 <= item.record_count <= MAX_ACCEPTANCE_RECORDS
        or type(item.exact_acceptance_count) is not int
        or not 0 <= item.exact_acceptance_count <= item.record_count
        or type(item.filing_date_fallback_count) is not int
        or item.filing_date_fallback_count
        != item.record_count - item.exact_acceptance_count
        or item.exact_acceptance_count != len(inventory)
        or tuple(
            sorted(
                inventory,
                key=lambda value: (value.accession_number, value.metadata_sha256),
            )
        )
        != inventory
        or len({value.accession_number for value in inventory}) != len(inventory)
        or hash_payload(profile.to_payload()) != item.metadata_profile_hash
        or hash_payload([value.to_payload() for value in inventory])
        != item.source_inventory_hash
        or hash_payload(item.lineage_payload()) != item.lineage_hash
        or item.snapshot_id
        != f"sec-edgar-acceptance-{item.year}q{item.quarter}-{item.lineage_hash[:16]}"
        or file_stem != item.snapshot_id
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance snapshot identity is invalid"
        )
    return item


def _load_self_consistent_bundle(
    snapshot_path: str | Path,
) -> tuple[
    SecEdgarAcceptanceSnapshotIdentity,
    tuple[SecEdgarAvailabilityRecord, ...],
    tuple[SecEdgarMetadataSource, ...],
]:
    path = Path(snapshot_path)
    if _BUNDLE_ID_RE.fullmatch(path.name) is None:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance snapshot filename is invalid"
        )
    _require_regular_directory(path.parent, label="acceptance bundle parent")
    raw = _read_regular_bytes(
        path,
        label="acceptance snapshot bundle",
        max_bytes=MAX_ACCEPTANCE_BUNDLE_BYTES,
        require_single_link=True,
    )
    bundle = _parse_canonical_bundle(raw)
    identity = _identity_from_payload(bundle.get("identity"), file_stem=path.stem)
    records_payload = bundle.get("records")
    sources_payload = bundle.get("sources")
    if (
        not isinstance(records_payload, list)
        or len(records_payload) > MAX_ACCEPTANCE_RECORDS
        or not isinstance(sources_payload, list)
        or len(sources_payload) > MAX_METADATA_SOURCES
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance bundle arrays are invalid"
        )
    declared_source_sizes = tuple(
        _declared_source_size(value) for value in sources_payload
    )
    if sum(declared_source_sizes) > MAX_TOTAL_METADATA_SOURCE_BYTES:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: bundled metadata sources exceed the total byte-size limit"
        )
    records = tuple(_record_from_payload(value) for value in records_payload)
    sources = tuple(_source_from_bundle_payload(value) for value in sources_payload)
    parsed_sources = tuple(
        _parse_source_json(source, identity.metadata_profile) for source in sources
    )
    exact_count = sum(
        value.availability_tier
        is SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
        for value in records
    )
    fallback_count = sum(
        value.availability_tier is SecEdgarAvailabilityTier.FILING_DATE_FALLBACK
        for value in records
    )
    if (
        len(records) != identity.record_count
        or exact_count != identity.exact_acceptance_count
        or fallback_count != identity.filing_date_fallback_count
        or hash_payload([value.to_payload() for value in records]) != identity.records_hash
        or tuple(sorted(records, key=lambda value: value.accession_number)) != records
        or len({value.accession_number for value in records}) != len(records)
        or tuple(value.identity for value in parsed_sources) != identity.source_inventory
        or tuple(
            sorted(
                parsed_sources,
                key=lambda value: (
                    value.accession_number,
                    value.source.metadata_sha256,
                ),
            )
        )
        != parsed_sources
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance bundle content disagrees with its identity"
        )
    return identity, records, sources


def load_sec_edgar_acceptance_snapshot(
    snapshot_path: str | Path,
    *,
    parsed_snapshot_directory: str | Path,
    raw_snapshot_directory: str | Path,
) -> LoadedSecEdgarAcceptanceSnapshot:
    """Load and semantically rebuild one bundle against its verified upstream."""

    identity, records, sources = _load_self_consistent_bundle(snapshot_path)
    rebuilt_identity, rebuilt_records, rebuilt_sources, rebuilt_bytes = (
        _assemble_acceptance_snapshot(
            parsed_snapshot_directory,
            raw_snapshot_directory,
            sources=sources,
            metadata_profile=identity.metadata_profile,
            parser_git_commit=identity.parser_git_commit,
        )
    )
    actual = _read_regular_bytes(
        Path(snapshot_path),
        label="acceptance snapshot bundle",
        max_bytes=MAX_ACCEPTANCE_BUNDLE_BYTES,
        require_single_link=True,
    )
    if (
        identity != rebuilt_identity
        or records != rebuilt_records
        or tuple(item.source for item in rebuilt_sources) != sources
        or actual != rebuilt_bytes
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance snapshot does not match verified upstream semantics"
        )
    return LoadedSecEdgarAcceptanceSnapshot(
        identity=identity, records=records, sources=sources
    )


def _paths_are_contained(
    prospective_root: Path, upstream_directories: tuple[Path, Path]
) -> bool:
    return any(
        prospective_root == upstream or upstream in prospective_root.parents
        for upstream in upstream_directories
    )


def _canonical_source_state(
    source: SecEdgarMetadataSource,
) -> tuple[bytes, str, str, str]:
    """Compare exact bytes and normalized provenance, not datetime wall forms."""

    return (
        source.metadata_bytes,
        source.source_url,
        source.retrieved_at_utc,
        source.capture_git_commit,
    )


def _recover_existing_bundle(
    target: Path,
    expected: bytes,
    expected_identity: SecEdgarAcceptanceSnapshotIdentity,
    expected_records: tuple[SecEdgarAvailabilityRecord, ...],
    expected_sources: tuple[SecEdgarMetadataSource, ...],
    *,
    parsed_snapshot_directory: str | Path,
    raw_snapshot_directory: str | Path,
) -> LoadedSecEdgarAcceptanceSnapshot:
    actual = _read_regular_bytes(
        target,
        label="committed acceptance snapshot bundle",
        max_bytes=MAX_ACCEPTANCE_BUNDLE_BYTES,
    )
    if actual != expected:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: immutable acceptance snapshot conflicts with attempted publication"
        )
    _clean_verified_temporaries(
        target.parent, target.name, expected, allow_prefix=False
    )
    loaded = load_sec_edgar_acceptance_snapshot(
        target,
        parsed_snapshot_directory=parsed_snapshot_directory,
        raw_snapshot_directory=raw_snapshot_directory,
    )
    if (
        loaded.identity != expected_identity
        or loaded.records != expected_records
        or tuple(_canonical_source_state(source) for source in loaded.sources)
        != tuple(_canonical_source_state(source) for source in expected_sources)
    ):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: committed acceptance snapshot conflicts with attempted publication"
        )
    return loaded


def build_sec_edgar_acceptance_snapshot(
    parsed_snapshot_directory: str | Path,
    raw_snapshot_directory: str | Path,
    output_root: str | Path,
    *,
    sources: tuple[SecEdgarMetadataSource, ...],
    metadata_profile: SecEdgarMetadataSchemaProfile,
    parser_git_commit: str,
) -> SecEdgarAcceptanceSnapshotIdentity:
    """Build and atomically publish one bounded offline acceptance bundle."""

    identity, records, parsed_sources, bundle_bytes = _assemble_acceptance_snapshot(
        parsed_snapshot_directory,
        raw_snapshot_directory,
        sources=sources,
        metadata_profile=metadata_profile,
        parser_git_commit=parser_git_commit,
    )
    expected_sources = tuple(item.source for item in parsed_sources)
    try:
        parsed_directory = Path(parsed_snapshot_directory).resolve(strict=True)
        raw_directory = Path(raw_snapshot_directory).resolve(strict=True)
        prospective_root = Path(output_root).resolve(strict=False)
    except (OSError, TypeError, ValueError) as exc:
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance snapshot paths are invalid"
        ) from exc
    upstream_directories = (parsed_directory, raw_directory)
    if _paths_are_contained(prospective_root, upstream_directories):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance output root cannot equal or descend from upstream"
        )
    root = _prepare_output_root(output_root)
    if _paths_are_contained(root, upstream_directories):
        raise SecEdgarAcceptanceSnapshotError(
            "REFUSED: acceptance output root cannot equal or descend from upstream"
        )
    target = root / f"{identity.snapshot_id}.json"
    lock_path = root / f".{identity.snapshot_id}{_LOCK_SUFFIX}"
    _require_regular_lock_slot(lock_path)
    with _AcceptancePublicationLock(lock_path):
        _require_regular_directory(root, label="acceptance output root")
        _require_regular_lock_slot(lock_path)
        try:
            target_status = target.lstat()
        except FileNotFoundError:
            target_status = None
        except OSError as exc:
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: acceptance snapshot target is unreadable"
            ) from exc
        if target_status is not None:
            if _status_is_redirect(target_status) or not stat.S_ISREG(
                target_status.st_mode
            ):
                raise SecEdgarAcceptanceSnapshotError(
                    "REFUSED: acceptance snapshot target must be a regular file"
                )
            return _recover_existing_bundle(
                target,
                bundle_bytes,
                identity,
                records,
                expected_sources,
                parsed_snapshot_directory=parsed_snapshot_directory,
                raw_snapshot_directory=raw_snapshot_directory,
            ).identity

        _clean_verified_temporaries(
            root, target.name, bundle_bytes, allow_prefix=True
        )
        try:
            publish_immutable_bytes(target, bundle_bytes)
            loaded = _recover_existing_bundle(
                target,
                bundle_bytes,
                identity,
                records,
                expected_sources,
                parsed_snapshot_directory=parsed_snapshot_directory,
                raw_snapshot_directory=raw_snapshot_directory,
            )
        except SecEdgarAcceptanceSnapshotError:
            try:
                target.lstat()
            except FileNotFoundError:
                _clean_verified_temporaries(
                    root, target.name, bundle_bytes, allow_prefix=True
                )
            except OSError as recovery_exc:
                raise SecEdgarAcceptanceSnapshotError(
                    "REFUSED: acceptance publication recovery failed"
                ) from recovery_exc
            else:
                _recover_existing_bundle(
                    target,
                    bundle_bytes,
                    identity,
                    records,
                    expected_sources,
                    parsed_snapshot_directory=parsed_snapshot_directory,
                    raw_snapshot_directory=raw_snapshot_directory,
                )
            raise
        except (ImmutableFileConflictError, OSError) as exc:
            try:
                target.lstat()
            except FileNotFoundError:
                _clean_verified_temporaries(
                    root, target.name, bundle_bytes, allow_prefix=True
                )
            except OSError as recovery_exc:
                raise SecEdgarAcceptanceSnapshotError(
                    "REFUSED: acceptance publication recovery failed"
                ) from recovery_exc
            else:
                recovered = _recover_existing_bundle(
                    target,
                    bundle_bytes,
                    identity,
                    records,
                    expected_sources,
                    parsed_snapshot_directory=parsed_snapshot_directory,
                    raw_snapshot_directory=raw_snapshot_directory,
                )
                return recovered.identity
            raise SecEdgarAcceptanceSnapshotError(
                "REFUSED: immutable acceptance publication conflicted or failed"
            ) from exc
        except BaseException as exc:
            try:
                target.lstat()
            except FileNotFoundError:
                _clean_verified_temporaries(
                    root, target.name, bundle_bytes, allow_prefix=True
                )
            except OSError as recovery_exc:
                raise recovery_exc from exc
            else:
                _recover_existing_bundle(
                    target,
                    bundle_bytes,
                    identity,
                    records,
                    expected_sources,
                    parsed_snapshot_directory=parsed_snapshot_directory,
                    raw_snapshot_directory=raw_snapshot_directory,
                )
            raise
    return loaded.identity


__all__ = [
    "EDGAR_ACCEPTANCE_SNAPSHOT_CONTRACT_VERSION",
    "EDGAR_ACCEPTANCE_SNAPSHOT_KIND",
    "LoadedSecEdgarAcceptanceSnapshot",
    "MAX_ACCEPTANCE_BUNDLE_BYTES",
    "MAX_ACCEPTANCE_RECORDS",
    "MAX_BUNDLE_JSON_NESTING_DEPTH",
    "MAX_METADATA_FIELD_CHARACTERS",
    "MAX_METADATA_FIELD_NAME_CHARACTERS",
    "MAX_METADATA_FIELDS",
    "MAX_METADATA_SOURCE_BYTES",
    "MAX_METADATA_SOURCES",
    "MAX_PUBLISHER_TEMPORARIES",
    "MAX_SOURCE_JSON_NESTING_DEPTH",
    "MAX_TOTAL_METADATA_SOURCE_BYTES",
    "MAX_URL_CHARACTERS",
    "SEC_EDGAR_METADATA_PARSER_VERSION",
    "SEC_FILING_DAY_CONSERVATIVE_UTC_HOUR",
    "SecEdgarAvailabilityRecord",
    "SecEdgarAvailabilityRule",
    "SecEdgarAcceptanceSnapshotError",
    "SecEdgarAcceptanceSnapshotIdentity",
    "SecEdgarAvailabilityTier",
    "SecEdgarMetadataSchemaProfile",
    "SecEdgarMetadataSource",
    "SecEdgarMetadataSourceIdentity",
    "build_sec_edgar_acceptance_snapshot",
    "load_sec_edgar_acceptance_snapshot",
]
