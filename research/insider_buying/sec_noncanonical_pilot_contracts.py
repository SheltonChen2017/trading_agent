"""Pure contracts for the owner-supplied, non-canonical SEC pilot.

This module performs no filesystem discovery or I/O.  It describes exact
caller-listed byte identities, derived projections, and operational results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Iterable

from data.hashing import canonical_json, hash_bytes, hash_payload


SEC_NONCANONICAL_PILOT_CONTRACT_VERSION = (
    "INSETF-IB2-NONCANONICAL-SEC-PILOT-CONTRACTS-v1"
)
SEC_NONCANONICAL_PILOT_MIN_PERIODS = 2
SEC_NONCANONICAL_PILOT_MAX_PERIODS = 4
SEC_NONCANONICAL_PILOT_MAX_XML_SOURCES = 256
SEC_NONCANONICAL_PILOT_MAX_XML_SOURCE_BYTES = 2 * 1024 * 1024
SEC_NONCANONICAL_PILOT_MAX_TOTAL_XML_BYTES = 64 * 1024 * 1024
SEC_NONCANONICAL_PILOT_MAX_ZIP_BYTES = 512 * 1024 * 1024
SEC_NONCANONICAL_PILOT_MAX_METADATA_SOURCE_BYTES = 2 * 1024 * 1024
SEC_NONCANONICAL_PILOT_MAX_TOTAL_METADATA_BYTES = 64 * 1024 * 1024
SEC_NONCANONICAL_PILOT_DERIVED_JSON_VERSION = (
    "INSETF-IB2-PILOT-DERIVED-FLAT-JSON-v1"
)
SEC_NONCANONICAL_PILOT_DERIVED_PROFILE_VERSION = (
    "INSETF-IB2-PILOT-IB1C-PROFILE-v1"
)
SEC_NONCANONICAL_PILOT_OPTIONAL_EARLY_QUARTER_POLICY = (
    "excluded-from-this-end-to-end-manifest-and-evaluated-separately"
)
SEC_NONCANONICAL_PILOT_DIRECT_IB1C_VERBATIM_CLAIM = False

_PERIOD_RE = re.compile(r"^(?P<year>[0-9]{4})Q(?P<quarter>[1-4])$")
_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_RELATIVE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,1024}$")
_FILING_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_CIK_RE = re.compile(r"^[0-9]{10}$")
_ACCEPTED_AT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"[+-][0-9]{2}:[0-9]{2}$"
)
_SEC_PRIMARY_URL_RE = re.compile(
    r"^https://www\.sec\.gov/Archives/edgar/data/(?P<cik>[0-9]{1,10})/"
    r"(?P<accession>[0-9]{18})/[A-Za-z0-9._-]{1,255}$"
)
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_RETRIEVED_AT_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00$"
)
_SEC_ZIP_URL_RE = re.compile(
    r"^https://(?:www\.)?sec\.gov/"
    r"(?P<prefix>(?:[A-Za-z0-9._~!$&'()*+,;=:@-]+/)*)"
    r"(?P<year>[0-9]{4})q(?P<quarter>[1-4])_form345\.zip$"
)
_SEC_ACCESSION_URL_RE = re.compile(
    r"^https://(?P<host>www\.sec\.gov|data\.sec\.gov)"
    r"(?P<path>/[A-Za-z0-9._~!$&'()*+,;=:@/-]+)$"
)

_CORE_PROJECTION_FIELDS = (
    "accession_number",
    "accepted_at",
    "filing_date",
    "form_type",
    "primary_document_sha256",
    "primary_document_url",
)
_AMENDMENT_LINK_FIELD = "original_accession_number"
_REQUIRED_PROJECTION_FIELDS = tuple(
    sorted((*_CORE_PROJECTION_FIELDS, _AMENDMENT_LINK_FIELD))
)
_IB_STAGES = ("IB-1A", "IB-1B", "IB-1C", "IB-1D", "IB-1E")


class SecNoncanonicalPilotContractError(ValueError):
    """A pilot identity or report failed closed."""


class PilotArtifactKind(str, Enum):
    QUARTERLY_ZIP = "quarterly_zip"
    VERBATIM_METADATA = "verbatim_metadata"
    PRIMARY_FORM4_XML = "primary_form4_xml"


class PilotFieldProvenance(str, Enum):
    SOURCE_FIELD = "source_field"
    EXACT_XML_SHA256 = "exact_xml_sha256"


class PilotFieldTransform(str, Enum):
    ACCESSION_FROM_METADATA = "accession-from-verbatim-metadata-v1"
    ACCEPTED_AT_FROM_METADATA = "accepted-at-from-verbatim-metadata-v1"
    FILING_DATE_FROM_METADATA = "filing-date-from-verbatim-metadata-v1"
    FORM_TYPE_FROM_METADATA = "form-type-from-verbatim-metadata-v1"
    PRIMARY_DOCUMENT_URL_FROM_METADATA = (
        "primary-document-url-from-verbatim-metadata-v1"
    )
    PRIMARY_XML_SHA256_EXACT_BYTES = "sha256-exact-primary-xml-bytes-v1"
    ORIGINAL_ACCESSION_FROM_METADATA = (
        "original-accession-from-verbatim-metadata-v1"
    )
    EMPTY_ORIGINAL_FROM_FORM_TYPE = "empty-original-from-source-form-type-v1"
    MISSING_ORIGINAL_UNAVAILABLE = "missing-original-unavailable-v1"


_FIELD_TRANSFORMS = {
    "accession_number": PilotFieldTransform.ACCESSION_FROM_METADATA,
    "accepted_at": PilotFieldTransform.ACCEPTED_AT_FROM_METADATA,
    "filing_date": PilotFieldTransform.FILING_DATE_FROM_METADATA,
    "form_type": PilotFieldTransform.FORM_TYPE_FROM_METADATA,
    "primary_document_sha256": PilotFieldTransform.PRIMARY_XML_SHA256_EXACT_BYTES,
    "primary_document_url": PilotFieldTransform.PRIMARY_DOCUMENT_URL_FROM_METADATA,
}
_TRANSFORM_LOCATORS = {
    PilotFieldTransform.ACCESSION_FROM_METADATA: "verbatim-metadata.accession_number",
    PilotFieldTransform.ACCEPTED_AT_FROM_METADATA: "verbatim-metadata.accepted_at",
    PilotFieldTransform.FILING_DATE_FROM_METADATA: "verbatim-metadata.filing_date",
    PilotFieldTransform.FORM_TYPE_FROM_METADATA: "verbatim-metadata.form_type",
    PilotFieldTransform.PRIMARY_DOCUMENT_URL_FROM_METADATA: (
        "verbatim-metadata.primary_document_url"
    ),
    PilotFieldTransform.PRIMARY_XML_SHA256_EXACT_BYTES: "exact-primary-xml-bytes",
    PilotFieldTransform.ORIGINAL_ACCESSION_FROM_METADATA: (
        "verbatim-metadata.original_accession_number"
    ),
    PilotFieldTransform.EMPTY_ORIGINAL_FROM_FORM_TYPE: "verbatim-metadata.form_type",
    PilotFieldTransform.MISSING_ORIGINAL_UNAVAILABLE: (
        "verbatim-metadata.original_accession_number-unavailable"
    ),
}

_REQUIRED_RESOURCE_UNITS = {
    "artifact_count": "count",
    "candidate_count": "count",
    "declared_input_bytes": "bytes",
    "metadata_bytes": "bytes",
    "metadata_count": "count",
    "xml_bytes": "bytes",
    "xml_count": "count",
}


class PilotProjectionDisposition(str, Enum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"


class PilotOperationalOutcome(str, Enum):
    ACCEPTED = "accepted"
    REFUSED = "refused"
    QUARANTINED = "quarantined"


class PilotCompatibilityOutcome(str, Enum):
    COMPATIBLE = "compatible"
    PARTIALLY_COMPATIBLE = "partially_compatible"
    INCOMPATIBLE = "incompatible"
    NOT_RUN = "not_run"


def _exact_string(value: object, *, label: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise SecNoncanonicalPilotContractError(
            f"REFUSED: {label} has invalid syntax"
        )
    return value


def _exact_sha256(value: object, *, label: str) -> str:
    return _exact_string(value, label=label, pattern=_SHA256_RE)


def _period_index(value: object, *, label: str = "period") -> int:
    period = _exact_string(value, label=label, pattern=_PERIOD_RE)
    match = _PERIOD_RE.fullmatch(period)
    assert match is not None
    year = int(match.group("year"))
    quarter = int(match.group("quarter"))
    if year < 2006 or (year, quarter) > (2026, 2):
        raise SecNoncanonicalPilotContractError(
            f"REFUSED: {label} is outside 2006Q1 through 2026Q2"
        )
    return year * 4 + quarter - 1


def _canonical_relative_path(value: object, *, label: str) -> str:
    path = _exact_string(value, label=label, pattern=_RELATIVE_PATH_RE)
    if (
        path.startswith("/")
        or path.endswith("/")
        or "//" in path
        or "\\" in path
        or ":" in path
    ):
        raise SecNoncanonicalPilotContractError(
            f"REFUSED: {label} must be a canonical relative path"
        )
    components = path.split("/")
    if any(component in {"", ".", ".."} for component in components):
        raise SecNoncanonicalPilotContractError(
            f"REFUSED: {label} contains traversal or non-canonical components"
        )
    return path


def _exact_nonnegative_int(value: object, *, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SecNoncanonicalPilotContractError(
            f"REFUSED: {label} must be an exact non-negative integer"
        )
    return value


def _enum_member(value: object, enum_type: type[Enum], *, label: str) -> Enum:
    if type(value) is not enum_type:
        raise SecNoncanonicalPilotContractError(
            f"REFUSED: {label} must be an exact {enum_type.__name__}"
        )
    return value


@dataclass(frozen=True)
class PilotVerbatimArtifactIdentity:
    """Exact caller-listed bytes; this object never opens ``relative_path``."""

    relative_path: str
    kind: PilotArtifactKind
    period: str
    sha256: str
    size_bytes: int
    source_url: str
    retrieved_at_utc: str
    capture_git_commit: str
    accession_number: str | None = None
    form_type: str | None = None

    def __post_init__(self) -> None:
        _canonical_relative_path(self.relative_path, label="artifact path")
        _enum_member(self.kind, PilotArtifactKind, label="artifact kind")
        _period_index(self.period, label="artifact period")
        _exact_sha256(self.sha256, label="artifact sha256")
        _exact_string(
            self.capture_git_commit,
            label="artifact capture git commit",
            pattern=_GIT_COMMIT_RE,
        )
        _exact_string(
            self.retrieved_at_utc,
            label="artifact retrieval time",
            pattern=_RETRIEVED_AT_UTC_RE,
        )
        try:
            retrieved_at = datetime.fromisoformat(self.retrieved_at_utc)
        except ValueError as exc:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: artifact retrieval time is not a real timestamp"
            ) from exc
        if (
            retrieved_at.utcoffset() != timedelta(0)
            or retrieved_at.isoformat(timespec="seconds") != self.retrieved_at_utc
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: artifact retrieval time must be canonical UTC seconds"
            )
        size = _exact_nonnegative_int(self.size_bytes, label="artifact size")
        if size == 0:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: listed artifacts must contain at least one byte"
            )

        if self.kind is PilotArtifactKind.QUARTERLY_ZIP:
            if self.accession_number is not None or self.form_type is not None:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: a quarterly ZIP cannot claim accession identity"
                )
            match = (
                _SEC_ZIP_URL_RE.fullmatch(self.source_url)
                if type(self.source_url) is str
                else None
            )
            if match is None or any(
                part in {".", ".."} for part in match.group("prefix").split("/")
            ):
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: quarterly ZIP source URL is not canonical SEC HTTPS"
                )
            expected_period = f"{match.group('year')}Q{match.group('quarter')}"
            if expected_period != self.period:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: quarterly ZIP source URL does not match its period"
                )
            if size > SEC_NONCANONICAL_PILOT_MAX_ZIP_BYTES:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: quarterly ZIP exceeds the 512 MiB pilot boundary"
                )
            return

        _exact_string(
            self.accession_number,
            label="artifact accession number",
            pattern=_ACCESSION_RE,
        )
        if type(self.form_type) is not str or self.form_type not in {"4", "4/A"}:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: accession artifacts must be Form 4 or Form 4/A"
            )
        if (
            self.kind is PilotArtifactKind.PRIMARY_FORM4_XML
            and size > SEC_NONCANONICAL_PILOT_MAX_XML_SOURCE_BYTES
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: one XML source exceeds the 2 MiB pilot boundary"
            )
        if (
            self.kind is PilotArtifactKind.VERBATIM_METADATA
            and size > SEC_NONCANONICAL_PILOT_MAX_METADATA_SOURCE_BYTES
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: one metadata source exceeds the 2 MiB pilot boundary"
            )
        source_match = (
            _SEC_ACCESSION_URL_RE.fullmatch(self.source_url)
            if type(self.source_url) is str
            else None
        )
        accession_digits = self.accession_number.replace("-", "")
        if (
            source_match is None
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: accession artifact source URL must bind its SEC accession"
            )
        path_components = source_match.group("path").split("/")[1:]
        if (
            any(component in {"", ".", ".."} for component in path_components)
            or not any(
                component in {self.accession_number, accession_digits}
                for component in path_components
            )
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: accession artifact URL requires an exact canonical accession segment"
            )
        if self.kind is PilotArtifactKind.PRIMARY_FORM4_XML:
            xml_match = _SEC_PRIMARY_URL_RE.fullmatch(self.source_url)
            if xml_match is None or xml_match.group("accession") != accession_digits:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: primary XML source URL must bind its SEC Archives accession"
                )

    def to_payload(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "kind": self.kind.value,
            "period": self.period,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "source_url": self.source_url,
            "retrieved_at_utc": self.retrieved_at_utc,
            "capture_git_commit": self.capture_git_commit,
            "accession_number": self.accession_number,
            "form_type": self.form_type,
        }

    @property
    def retrieved_datetime(self) -> datetime:
        return datetime.fromisoformat(self.retrieved_at_utc)


@dataclass(frozen=True)
class PilotAccessionCandidateIdentity:
    """One raw SUBMISSION candidate, whether or not enrichment succeeds."""

    period: str
    accession_number: str
    form_type: str
    filing_date: str
    issuer_cik: str
    quarterly_zip_sha256: str
    submission_row_sha256: str
    metadata_relative_path: str | None = None
    xml_relative_path: str | None = None

    def __post_init__(self) -> None:
        _period_index(self.period, label="candidate period")
        _exact_string(
            self.accession_number,
            label="candidate accession number",
            pattern=_ACCESSION_RE,
        )
        if type(self.form_type) is not str or self.form_type not in {"4", "4/A"}:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: candidate form type must be 4 or 4/A"
            )
        _exact_string(
            self.filing_date,
            label="candidate filing date",
            pattern=_FILING_DATE_RE,
        )
        try:
            parsed_filing_date = date.fromisoformat(self.filing_date)
        except ValueError as exc:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: candidate filing date is not a real calendar date"
            ) from exc
        filing_quarter = (parsed_filing_date.month - 1) // 3 + 1
        if (
            f"{parsed_filing_date.year}Q{filing_quarter}" != self.period
            or parsed_filing_date.year % 100
            != int(self.accession_number[11:13])
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: candidate filing date disagrees with period or accession year"
            )
        _exact_string(
            self.issuer_cik,
            label="candidate issuer CIK",
            pattern=_CIK_RE,
        )
        if int(self.issuer_cik) == 0:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: candidate issuer CIK cannot be zero"
            )
        _exact_sha256(self.quarterly_zip_sha256, label="candidate ZIP sha256")
        _exact_sha256(self.submission_row_sha256, label="submission row sha256")
        for label, value in (
            ("candidate metadata path", self.metadata_relative_path),
            ("candidate XML path", self.xml_relative_path),
        ):
            if value is not None:
                _canonical_relative_path(value, label=label)

    @property
    def key(self) -> tuple[str, str]:
        return (self.period, self.accession_number)

    def to_payload(self) -> dict[str, object]:
        return {
            "period": self.period,
            "accession_number": self.accession_number,
            "form_type": self.form_type,
            "filing_date": self.filing_date,
            "issuer_cik": self.issuer_cik,
            "quarterly_zip_sha256": self.quarterly_zip_sha256,
            "submission_row_sha256": self.submission_row_sha256,
            "metadata_relative_path": self.metadata_relative_path,
            "xml_relative_path": self.xml_relative_path,
        }


@dataclass(frozen=True)
class PilotFieldDerivation:
    """One derived flat field with provenance to exact verbatim parent bytes."""

    field_name: str
    value: str
    parent_relative_path: str
    parent_sha256: str
    transform: PilotFieldTransform
    provenance: PilotFieldProvenance
    source_backed: bool = True

    def __post_init__(self) -> None:
        _exact_string(self.field_name, label="field name", pattern=_FIELD_RE)
        if (
            type(self.value) is not str
            or len(self.value) > 262_144
            or (not self.value and self.field_name != _AMENDMENT_LINK_FIELD)
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: derived field value must be a bounded non-empty string"
            )
        _canonical_relative_path(
            self.parent_relative_path,
            label="field parent path",
        )
        _exact_sha256(self.parent_sha256, label="field parent sha256")
        _enum_member(self.transform, PilotFieldTransform, label="field transform")
        _enum_member(self.provenance, PilotFieldProvenance, label="provenance")
        missing_link = self.transform is PilotFieldTransform.MISSING_ORIGINAL_UNAVAILABLE
        if self.source_backed is not (not missing_link):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: source_backed must match the exact reviewed transform"
            )
        if self.provenance is PilotFieldProvenance.EXACT_XML_SHA256:
            if self.field_name != "primary_document_sha256":
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: the exact-byte hash transform is only for the XML hash"
                )
            _exact_sha256(self.value, label="computed XML sha256")
            if self.value != self.parent_sha256:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: computed XML hash must equal the exact parent hash"
                )
            if self.transform is not PilotFieldTransform.PRIMARY_XML_SHA256_EXACT_BYTES:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: XML hashes require the exact-byte SHA-256 transform"
                )
        elif self.transform is PilotFieldTransform.PRIMARY_XML_SHA256_EXACT_BYTES:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: the XML hash transform requires exact-byte provenance"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "field_name": self.field_name,
            "value": self.value,
            "parent_relative_path": self.parent_relative_path,
            "parent_sha256": self.parent_sha256,
            "source_locator": _TRANSFORM_LOCATORS[self.transform],
            "transform": self.transform.value,
            "provenance": self.provenance.value,
            "source_backed": self.source_backed,
        }


def _copy_field_derivation(item: PilotFieldDerivation) -> PilotFieldDerivation:
    if type(item) is not PilotFieldDerivation:
        raise SecNoncanonicalPilotContractError(
            "REFUSED: projection fields must use exact derivation objects"
        )
    return PilotFieldDerivation(
        field_name=item.field_name,
        value=item.value,
        parent_relative_path=item.parent_relative_path,
        parent_sha256=item.parent_sha256,
        transform=item.transform,
        provenance=item.provenance,
        source_backed=item.source_backed,
    )


@dataclass(frozen=True)
class PilotDerivedFlatIb1cProjectionIdentity:
    """Non-verbatim, field-provenanced flat projection for IB-1C compatibility."""

    period: str
    accession_number: str
    form_type: str
    fields: tuple[PilotFieldDerivation, ...]
    direct_ib1c_v1_verbatim_claim: bool = False
    direct_ib1c_v1_ingest_authorized: bool = False
    official_sec_profile_verified: bool = False
    canonical_evidence: bool = False

    def __post_init__(self) -> None:
        _period_index(self.period, label="projection period")
        _exact_string(
            self.accession_number,
            label="projection accession number",
            pattern=_ACCESSION_RE,
        )
        if type(self.form_type) is not str or self.form_type not in {"4", "4/A"}:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: projection form type must be 4 or 4/A"
            )
        if self.direct_ib1c_v1_verbatim_claim is not False:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: a derived projection cannot claim verbatim IB-1C bytes"
            )
        if self.direct_ib1c_v1_ingest_authorized is not False:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: the derived projection is not direct IB-1C v1 input"
            )
        if self.official_sec_profile_verified is not False or self.canonical_evidence is not False:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: the pilot projection has no official or canonical authority"
            )
        try:
            copied = tuple(self.fields)
        except TypeError as exc:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: projection fields must be iterable"
            ) from exc
        ordered = tuple(
            sorted(
                (_copy_field_derivation(item) for item in copied),
                key=lambda item: item.field_name,
            )
        )
        names = tuple(item.field_name for item in ordered)
        if len(names) != len(set(names)) or len(names) != len(set(map(str.casefold, names))):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: projection fields contain duplicate names"
            )
        missing = sorted(set(_REQUIRED_PROJECTION_FIELDS) - set(names))
        extras = sorted(set(names) - set(_REQUIRED_PROJECTION_FIELDS))
        if missing or extras:
            raise SecNoncanonicalPilotContractError(
                f"REFUSED: projection field set mismatch; missing={missing}, extras={extras}"
            )
        object.__setattr__(self, "fields", ordered)

        by_name = {item.field_name: item for item in ordered}
        if by_name["accession_number"].value != self.accession_number:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: projected accession does not match projection identity"
            )
        if by_name["form_type"].value != self.form_type:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: projected form type does not match projection identity"
            )
        for name in _CORE_PROJECTION_FIELDS:
            item = by_name[name]
            expected = (
                PilotFieldProvenance.EXACT_XML_SHA256
                if name == "primary_document_sha256"
                else PilotFieldProvenance.SOURCE_FIELD
            )
            if item.provenance is not expected:
                raise SecNoncanonicalPilotContractError(
                    f"REFUSED: {name} lacks required field-level provenance"
                )
            if item.transform is not _FIELD_TRANSFORMS[name]:
                raise SecNoncanonicalPilotContractError(
                    f"REFUSED: {name} uses an unreviewed field transform"
                )
        filing_date_value = by_name["filing_date"].value
        if _FILING_DATE_RE.fullmatch(filing_date_value) is None:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: filing_date is not canonical YYYY-MM-DD"
            )
        try:
            parsed_filing_date = date.fromisoformat(filing_date_value)
        except ValueError as exc:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: filing_date is not a real calendar date"
            ) from exc
        filing_quarter = (parsed_filing_date.month - 1) // 3 + 1
        if f"{parsed_filing_date.year}Q{filing_quarter}" != self.period:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: filing_date does not belong to the projection period"
            )
        accepted_at_value = by_name["accepted_at"].value
        if _ACCEPTED_AT_RE.fullmatch(accepted_at_value) is None:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: accepted_at must include seconds and an explicit offset"
            )
        if accepted_at_value.endswith("-00:00"):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: accepted_at cannot use the unknown -00:00 offset"
            )
        try:
            parsed_accepted_at = datetime.fromisoformat(accepted_at_value)
        except ValueError as exc:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: accepted_at is not a real timestamp"
            ) from exc
        if parsed_accepted_at.utcoffset() is None or parsed_accepted_at.microsecond != 0:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: accepted_at must be offset-aware at whole-second precision"
            )
        accepted_utc = parsed_accepted_at.astimezone(timezone.utc)
        filing_floor = datetime(
            parsed_filing_date.year,
            parsed_filing_date.month,
            parsed_filing_date.day,
            5,
            tzinfo=timezone.utc,
        )
        if not filing_floor <= accepted_utc < filing_floor + timedelta(days=1):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: accepted_at is outside the conservative SEC filing-day window"
            )
        primary_url = by_name["primary_document_url"].value
        url_match = _SEC_PRIMARY_URL_RE.fullmatch(primary_url)
        if (
            url_match is None
            or url_match.group("accession") != self.accession_number.replace("-", "")
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: primary_document_url must be an SEC Archives URL for the accession"
            )

        link = by_name[_AMENDMENT_LINK_FIELD]
        if link.provenance is not PilotFieldProvenance.SOURCE_FIELD:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: an amendment link field must be source-backed"
            )
        if self.form_type == "4/A" and link.value:
            if (
                link.transform is not PilotFieldTransform.ORIGINAL_ACCESSION_FROM_METADATA
                or link.source_backed is not True
            ):
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: an amendment link must use the reviewed source transform"
                )
            _exact_string(
                link.value,
                label="original accession link",
                pattern=_ACCESSION_RE,
            )
            if link.value == self.accession_number:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: an amendment cannot link to itself"
                )
        if self.form_type == "4" and (
            link.value
            or link.transform is not PilotFieldTransform.EMPTY_ORIGINAL_FROM_FORM_TYPE
            or link.source_backed is not True
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: Form 4 requires a source-backed deterministic empty link"
            )
        if self.form_type == "4/A" and not link.value and (
            link.transform is not PilotFieldTransform.MISSING_ORIGINAL_UNAVAILABLE
            or link.source_backed is not False
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: missing Form 4/A link requires the unavailable transform"
            )

    @property
    def disposition(self) -> PilotProjectionDisposition:
        if self.form_type == "4/A" and not next(
            item.value
            for item in self.fields
            if item.field_name == _AMENDMENT_LINK_FIELD
        ):
            return PilotProjectionDisposition.QUARANTINED
        return PilotProjectionDisposition.ACCEPTED

    @property
    def quarantine_reason(self) -> str | None:
        if self.disposition is PilotProjectionDisposition.QUARANTINED:
            return "form4a_missing_source_backed_original_accession_link"
        return None

    @property
    def ib1e_eligible(self) -> bool:
        # Final eligibility is a manifest-level fact because a Form 4/A must
        # resolve to an in-sample original candidate and projection.
        return False

    def flat_payload(self) -> dict[str, str]:
        return {item.field_name: item.value for item in self.fields}

    def profile_payload(self) -> dict[str, object]:
        return {
            "profile_version": SEC_NONCANONICAL_PILOT_DERIVED_PROFILE_VERSION,
            "profile_id": "noncanonical-pilot-derived-flat-ib1c-v1",
            "exact_fields": list(_REQUIRED_PROJECTION_FIELDS),
            "accession_number_field": "accession_number",
            "form_type_field": "form_type",
            "filing_date_field": "filing_date",
            "accepted_at_field": "accepted_at",
            "primary_document_url_field": "primary_document_url",
            "amends_accession_field": "original_accession_number",
            "primary_document_sha256_field": "primary_document_sha256",
            "official_sec_profile_verified": False,
        }

    @property
    def profile_sha256(self) -> str:
        return hash_payload(self.profile_payload())

    @property
    def derived_json_bytes(self) -> bytes:
        return (canonical_json(self.flat_payload()) + "\n").encode("utf-8")

    @property
    def derived_json_sha256(self) -> str:
        return hash_bytes(self.derived_json_bytes)

    @property
    def derived_json_size_bytes(self) -> int:
        return len(self.derived_json_bytes)

    def to_payload(self) -> dict[str, object]:
        return {
            "period": self.period,
            "accession_number": self.accession_number,
            "form_type": self.form_type,
            "derived_flat_fields": [item.to_payload() for item in self.fields],
            "derived_json": {
                "serialization_version": SEC_NONCANONICAL_PILOT_DERIVED_JSON_VERSION,
                "encoding": "utf-8",
                "terminal_lf_count": 1,
                "flat_payload": self.flat_payload(),
                "sha256": self.derived_json_sha256,
                "size_bytes": self.derived_json_size_bytes,
                "profile": self.profile_payload(),
                "profile_sha256": self.profile_sha256,
            },
            "direct_ib1c_v1_verbatim_claim": False,
            "direct_ib1c_v1_ingest_authorized": False,
            "official_sec_profile_verified": False,
            "canonical_evidence": False,
            "disposition": self.disposition.value,
            "quarantine_reason": self.quarantine_reason,
            "ib1e_eligible": False,
            "ib1e_eligibility_requires_manifest": True,
        }

    @property
    def semantic_sha256(self) -> str:
        return hash_payload(self.to_payload())


def _copy_artifact_identity(
    item: PilotVerbatimArtifactIdentity,
) -> PilotVerbatimArtifactIdentity:
    if type(item) is not PilotVerbatimArtifactIdentity:
        raise SecNoncanonicalPilotContractError(
            "REFUSED: artifact inventory contains an invalid identity"
        )
    return PilotVerbatimArtifactIdentity(
        relative_path=item.relative_path,
        kind=item.kind,
        period=item.period,
        sha256=item.sha256,
        size_bytes=item.size_bytes,
        source_url=item.source_url,
        retrieved_at_utc=item.retrieved_at_utc,
        capture_git_commit=item.capture_git_commit,
        accession_number=item.accession_number,
        form_type=item.form_type,
    )


def _copy_candidate_identity(
    item: PilotAccessionCandidateIdentity,
) -> PilotAccessionCandidateIdentity:
    if type(item) is not PilotAccessionCandidateIdentity:
        raise SecNoncanonicalPilotContractError(
            "REFUSED: candidate inventory contains an invalid identity"
        )
    return PilotAccessionCandidateIdentity(
        period=item.period,
        accession_number=item.accession_number,
        form_type=item.form_type,
        filing_date=item.filing_date,
        issuer_cik=item.issuer_cik,
        quarterly_zip_sha256=item.quarterly_zip_sha256,
        submission_row_sha256=item.submission_row_sha256,
        metadata_relative_path=item.metadata_relative_path,
        xml_relative_path=item.xml_relative_path,
    )


def _copy_projection_identity(
    item: PilotDerivedFlatIb1cProjectionIdentity,
) -> PilotDerivedFlatIb1cProjectionIdentity:
    if type(item) is not PilotDerivedFlatIb1cProjectionIdentity:
        raise SecNoncanonicalPilotContractError(
            "REFUSED: projection inventory contains an invalid identity"
        )
    return PilotDerivedFlatIb1cProjectionIdentity(
        period=item.period,
        accession_number=item.accession_number,
        form_type=item.form_type,
        fields=item.fields,
        direct_ib1c_v1_verbatim_claim=item.direct_ib1c_v1_verbatim_claim,
        direct_ib1c_v1_ingest_authorized=item.direct_ib1c_v1_ingest_authorized,
        official_sec_profile_verified=item.official_sec_profile_verified,
        canonical_evidence=item.canonical_evidence,
    )


def _artifact_sort_key(
    item: PilotVerbatimArtifactIdentity,
) -> tuple[str, str, str, str]:
    return (
        item.period,
        item.kind.value,
        item.accession_number or "",
        item.relative_path,
    )


def _projection_sort_key(
    item: PilotDerivedFlatIb1cProjectionIdentity,
) -> tuple[str, str]:
    return (item.period, item.accession_number)


@dataclass(frozen=True)
class SecNoncanonicalPilotManifest:
    """Listed-only external pilot manifest; construction performs zero I/O."""

    periods: tuple[str, ...]
    candidates: tuple[PilotAccessionCandidateIdentity, ...]
    artifacts: tuple[PilotVerbatimArtifactIdentity, ...]
    projections: tuple[PilotDerivedFlatIb1cProjectionIdentity, ...]
    external_listed_only: bool = True
    discovery_authorized: bool = False
    optional_early_quarter_included: bool = False
    canonical_corpus: bool = False

    def __post_init__(self) -> None:
        try:
            periods = tuple(self.periods)
        except TypeError as exc:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: manifest periods must be iterable"
            ) from exc
        if any(type(item) is not str for item in periods):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: manifest periods must be exact strings"
            )
        if not (
            SEC_NONCANONICAL_PILOT_MIN_PERIODS
            <= len(periods)
            <= SEC_NONCANONICAL_PILOT_MAX_PERIODS
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: end-to-end pilot requires two through four quarters"
            )
        indexes = tuple(
            _period_index(item, label="manifest period") for item in periods
        )
        if (
            len(periods) != len(set(periods))
            or indexes != tuple(sorted(indexes))
            or any(right != left + 1 for left, right in zip(indexes, indexes[1:]))
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: end-to-end pilot periods must be sorted, unique, and contiguous"
            )
        if self.external_listed_only is not True:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: pilot artifacts must be externally supplied and listed"
            )
        for label, value in (
            ("discovery authority", self.discovery_authorized),
            ("optional early-quarter inclusion", self.optional_early_quarter_included),
            ("canonical-corpus claim", self.canonical_corpus),
        ):
            if value is not False:
                raise SecNoncanonicalPilotContractError(
                    f"REFUSED: {label} must remain false"
                )

        try:
            candidates = tuple(self.candidates)
            artifacts = tuple(self.artifacts)
            projections = tuple(self.projections)
        except TypeError as exc:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: manifest inventories must be iterable"
            ) from exc
        artifacts = tuple(_copy_artifact_identity(item) for item in artifacts)
        candidates = tuple(_copy_candidate_identity(item) for item in candidates)
        projections = tuple(_copy_projection_identity(item) for item in projections)
        candidates = tuple(sorted(candidates, key=lambda item: item.key))
        if not candidates:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: pilot manifest requires at least one accession candidate"
            )
        artifacts = tuple(sorted(artifacts, key=_artifact_sort_key))
        projections = tuple(sorted(projections, key=_projection_sort_key))
        object.__setattr__(self, "periods", periods)
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "projections", projections)

        paths = tuple(item.relative_path for item in artifacts)
        if len(paths) != len(set(paths)) or len(paths) != len(set(map(str.casefold, paths))):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: artifact paths contain duplicate or case-colliding names"
            )
        if any(item.period not in periods for item in artifacts):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: every artifact must belong to a listed pilot period"
            )
        candidate_accessions = tuple(item.accession_number for item in candidates)
        if len(candidate_accessions) != len(set(candidate_accessions)):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: candidate inventory contains duplicate accessions across periods"
            )
        if any(item.period not in periods for item in candidates):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: every candidate must belong to a listed pilot period"
            )
        zips = [
            item
            for item in artifacts
            if item.kind is PilotArtifactKind.QUARTERLY_ZIP
        ]
        for period in periods:
            if sum(item.period == period for item in zips) != 1:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: exactly one quarterly ZIP is required per period"
                )
        if len(zips) != len(periods):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: ZIP inventory contains an extra pilot package"
            )

        xml_artifacts = tuple(
            item
            for item in artifacts
            if item.kind is PilotArtifactKind.PRIMARY_FORM4_XML
        )
        if len(xml_artifacts) > SEC_NONCANONICAL_PILOT_MAX_XML_SOURCES:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: XML sample exceeds 256 explicitly listed documents"
            )
        if sum(item.size_bytes for item in xml_artifacts) > (
            SEC_NONCANONICAL_PILOT_MAX_TOTAL_XML_BYTES
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: XML sample exceeds the 64 MiB pilot boundary"
            )
        metadata_artifacts = tuple(
            item
            for item in artifacts
            if item.kind is PilotArtifactKind.VERBATIM_METADATA
        )
        if sum(item.size_bytes for item in metadata_artifacts) > (
            SEC_NONCANONICAL_PILOT_MAX_TOTAL_METADATA_BYTES
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: metadata sample exceeds the 64 MiB pilot boundary"
            )

        projection_accessions = tuple(item.accession_number for item in projections)
        if len(projection_accessions) != len(set(projection_accessions)):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: projection inventory contains duplicate accessions across periods"
            )
        if any(item.period not in periods for item in projections):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: every projection must belong to a listed pilot period"
            )

        candidate_by_key = {item.key: item for item in candidates}
        zip_by_period = {item.period: item for item in zips}
        for candidate in candidates:
            quarter_zip = zip_by_period[candidate.period]
            if candidate.quarterly_zip_sha256 != quarter_zip.sha256:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: candidate is not bound to its quarterly ZIP hash"
                )
        for artifact in (*metadata_artifacts, *xml_artifacts):
            candidate = candidate_by_key.get((artifact.period, artifact.accession_number))
            if candidate is None or candidate.form_type != artifact.form_type:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: accession artifact does not map to one candidate"
                )
            expected_path = (
                candidate.metadata_relative_path
                if artifact.kind is PilotArtifactKind.VERBATIM_METADATA
                else candidate.xml_relative_path
            )
            if expected_path != artifact.relative_path:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: candidate artifact reference does not match the listed path"
                )
        for candidate in candidates:
            for kind, reference in (
                (PilotArtifactKind.VERBATIM_METADATA, candidate.metadata_relative_path),
                (PilotArtifactKind.PRIMARY_FORM4_XML, candidate.xml_relative_path),
            ):
                matches = [
                    item
                    for item in artifacts
                    if item.kind is kind
                    and item.period == candidate.period
                    and item.accession_number == candidate.accession_number
                ]
                if len(matches) != (1 if reference is not None else 0):
                    raise SecNoncanonicalPilotContractError(
                        "REFUSED: candidate artifact kind is missing or duplicated"
                    )

        by_path = {item.relative_path: item for item in artifacts}
        for projection in projections:
            candidate = candidate_by_key.get(
                (projection.period, projection.accession_number)
            )
            if candidate is None or candidate.form_type != projection.form_type:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: projection does not map to one candidate"
                )
            projected_filing_date = next(
                item.value
                for item in projection.fields
                if item.field_name == "filing_date"
            )
            if projected_filing_date != candidate.filing_date:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: projected filing date disagrees with its candidate"
                )
            for derived in projection.fields:
                parent = by_path.get(derived.parent_relative_path)
                if parent is None or parent.sha256 != derived.parent_sha256:
                    raise SecNoncanonicalPilotContractError(
                        "REFUSED: field provenance is not bound to a listed artifact"
                    )
                if (
                    parent.period != projection.period
                    or parent.accession_number != projection.accession_number
                    or parent.form_type != projection.form_type
                ):
                    raise SecNoncanonicalPilotContractError(
                        "REFUSED: field provenance crosses accession identity"
                    )
                expected_kind = (
                    PilotArtifactKind.PRIMARY_FORM4_XML
                    if derived.provenance is PilotFieldProvenance.EXACT_XML_SHA256
                    else PilotArtifactKind.VERBATIM_METADATA
                )
                if parent.kind is not expected_kind:
                    raise SecNoncanonicalPilotContractError(
                        "REFUSED: field provenance points to the wrong artifact kind"
                    )

        for projection in projections:
            candidate = candidate_by_key[
                (projection.period, projection.accession_number)
            ]
            key = (projection.period, projection.accession_number, projection.form_type)
            matching = [
                item
                for item in artifacts
                if (item.period, item.accession_number, item.form_type) == key
            ]
            if sum(
                item.kind is PilotArtifactKind.VERBATIM_METADATA for item in matching
            ) != 1 or sum(
                item.kind is PilotArtifactKind.PRIMARY_FORM4_XML for item in matching
            ) != 1:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: each projection requires one metadata and one XML artifact"
                )
            xml_parent = next(
                item
                for item in matching
                if item.kind is PilotArtifactKind.PRIMARY_FORM4_XML
            )
            projected_url = next(
                item.value
                for item in projection.fields
                if item.field_name == "primary_document_url"
            )
            if projected_url != xml_parent.source_url:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: projected primary URL does not match the listed XML source"
                )
            accepted_at = datetime.fromisoformat(
                next(
                    item.value
                    for item in projection.fields
                    if item.field_name == "accepted_at"
                )
            ).astimezone(timezone.utc)
            metadata_parent = next(
                item
                for item in matching
                if item.kind is PilotArtifactKind.VERBATIM_METADATA
            )
            xml_url_match = _SEC_PRIMARY_URL_RE.fullmatch(xml_parent.source_url)
            assert xml_url_match is not None
            if xml_url_match.group("cik") != str(int(candidate.issuer_cik)):
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: XML source URL disagrees with candidate issuer CIK"
                )
            metadata_source_match = _SEC_ACCESSION_URL_RE.fullmatch(
                metadata_parent.source_url
            )
            assert metadata_source_match is not None
            metadata_components = metadata_source_match.group("path").split("/")[1:]
            if metadata_components[:3] == ["Archives", "edgar", "data"] and (
                metadata_source_match.group("host") != "www.sec.gov"
                or len(metadata_components) != 6
                or not metadata_components[3].isdigit()
                or metadata_components[3] != str(int(candidate.issuer_cik))
                or metadata_components[4]
                != projection.accession_number.replace("-", "")
                or not metadata_components[5]
            ):
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: metadata source URL disagrees with candidate issuer lineage"
                )
            if (
                metadata_parent.retrieved_datetime < accepted_at
                or xml_parent.retrieved_datetime < accepted_at
            ):
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: metadata and XML retrieval cannot precede acceptance"
                )

    @property
    def projection_inventory_sha256(self) -> str:
        return hash_payload(self._projection_manifest_payloads())

    @property
    def candidate_inventory_sha256(self) -> str:
        return hash_payload([item.to_payload() for item in self.candidates])

    def projection_quarantine_reason(
        self,
        projection: PilotDerivedFlatIb1cProjectionIdentity,
    ) -> str | None:
        if (
            type(projection) is not PilotDerivedFlatIb1cProjectionIdentity
            or projection not in self.projections
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: projection eligibility requires an exact manifest member"
            )
        if projection.disposition is PilotProjectionDisposition.QUARANTINED:
            return projection.quarantine_reason
        if projection.form_type != "4/A":
            return None
        original_accession = next(
            item.value
            for item in projection.fields
            if item.field_name == _AMENDMENT_LINK_FIELD
        )
        candidate = next(
            (
                item
                for item in self.candidates
                if item.accession_number == original_accession
            ),
            None,
        )
        original_projection = next(
            (
                item
                for item in self.projections
                if item.accession_number == original_accession
                and item.form_type == "4"
            ),
            None,
        )
        if (
            candidate is None
            or candidate.form_type != "4"
            or original_projection is None
        ):
            return "form4a_original_form4_not_in_sample"
        amendment_candidate = next(
            item
            for item in self.candidates
            if item.accession_number == projection.accession_number
        )
        if candidate.issuer_cik != amendment_candidate.issuer_cik:
            return "form4a_original_issuer_mismatch"
        amendment_accepted_at = datetime.fromisoformat(
            next(
                item.value
                for item in projection.fields
                if item.field_name == "accepted_at"
            )
        ).astimezone(timezone.utc)
        original_accepted_at = datetime.fromisoformat(
            next(
                item.value
                for item in original_projection.fields
                if item.field_name == "accepted_at"
            )
        ).astimezone(timezone.utc)
        if original_accepted_at >= amendment_accepted_at:
            return "form4a_original_acceptance_not_before_amendment"
        return None

    def projection_is_ib1e_eligible(
        self,
        projection: PilotDerivedFlatIb1cProjectionIdentity,
    ) -> bool:
        if (
            type(projection) is not PilotDerivedFlatIb1cProjectionIdentity
            or projection not in self.projections
        ):
            return False
        return self.projection_quarantine_reason(projection) is None

    def _projection_manifest_payloads(self) -> list[dict[str, object]]:
        return [
            {
                "identity": item.to_payload(),
                "manifest_disposition": (
                    PilotProjectionDisposition.QUARANTINED.value
                    if self.projection_quarantine_reason(item)
                    else PilotProjectionDisposition.ACCEPTED.value
                ),
                "manifest_quarantine_reason": self.projection_quarantine_reason(item),
                "ib1e_eligible": self.projection_is_ib1e_eligible(item),
            }
            for item in self.projections
        ]

    @property
    def unprojected_candidate_count(self) -> int:
        projected = {(item.period, item.accession_number) for item in self.projections}
        return sum(item.key not in projected for item in self.candidates)

    @property
    def prequarantined_projection_reasons(self) -> tuple[str, ...]:
        return tuple(
            reason
            for item in self.projections
            if (reason := self.projection_quarantine_reason(item)) is not None
        )

    def required_resource_values(self) -> dict[str, tuple[int, str]]:
        metadata = tuple(
            item
            for item in self.artifacts
            if item.kind is PilotArtifactKind.VERBATIM_METADATA
        )
        xml = tuple(
            item
            for item in self.artifacts
            if item.kind is PilotArtifactKind.PRIMARY_FORM4_XML
        )
        return {
            "artifact_count": (len(self.artifacts), "count"),
            "candidate_count": (len(self.candidates), "count"),
            "declared_input_bytes": (
                sum(item.size_bytes for item in self.artifacts),
                "bytes",
            ),
            "metadata_bytes": (sum(item.size_bytes for item in metadata), "bytes"),
            "metadata_count": (len(metadata), "count"),
            "xml_bytes": (sum(item.size_bytes for item in xml), "bytes"),
            "xml_count": (len(xml), "count"),
        }

    def to_payload(self) -> dict[str, object]:
        return {
            "contract_version": SEC_NONCANONICAL_PILOT_CONTRACT_VERSION,
            "periods": list(self.periods),
            "candidates": [item.to_payload() for item in self.candidates],
            "candidate_inventory_sha256": self.candidate_inventory_sha256,
            "artifacts": [item.to_payload() for item in self.artifacts],
            "projections": self._projection_manifest_payloads(),
            "projection_inventory_sha256": self.projection_inventory_sha256,
            "external_listed_only": True,
            "discovery_authorized": False,
            "optional_early_quarter_policy": (
                SEC_NONCANONICAL_PILOT_OPTIONAL_EARLY_QUARTER_POLICY
            ),
            "optional_early_quarter_included": False,
            "canonical_corpus": False,
        }

    @property
    def semantic_sha256(self) -> str:
        return hash_payload(self.to_payload())

    @property
    def manifest_id(self) -> str:
        return (
            f"sec-noncanonical-pilot-{self.periods[0].lower()}-"
            f"{self.periods[-1].lower()}-{self.semantic_sha256[:16]}"
        )


@dataclass(frozen=True)
class PilotStageIdentity:
    stage: str
    artifact_id: str
    sha256: str

    def __post_init__(self) -> None:
        if type(self.stage) is not str or self.stage not in _IB_STAGES:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: stage identity must name IB-1A through IB-1E"
            )
        _exact_string(self.artifact_id, label="stage artifact id", pattern=_IDENTIFIER_RE)
        _exact_sha256(self.sha256, label="stage artifact sha256")

    def to_payload(self) -> dict[str, str]:
        return {
            "stage": self.stage,
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class PilotReasonCount:
    outcome: PilotOperationalOutcome
    reason: str
    count: int

    def __post_init__(self) -> None:
        _enum_member(self.outcome, PilotOperationalOutcome, label="operational outcome")
        _exact_string(self.reason, label="reason", pattern=_IDENTIFIER_RE)
        if _exact_nonnegative_int(self.count, label="reason count") == 0:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: listed reason counts must be positive"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "count": self.count,
        }


@dataclass(frozen=True)
class PilotResourceMeasurement:
    name: str
    value: int
    unit: str

    def __post_init__(self) -> None:
        _exact_string(self.name, label="resource name", pattern=_IDENTIFIER_RE)
        _exact_nonnegative_int(self.value, label="resource value")
        _exact_string(self.unit, label="resource unit", pattern=_IDENTIFIER_RE)

    def to_payload(self) -> dict[str, object]:
        return {"name": self.name, "value": self.value, "unit": self.unit}


@dataclass(frozen=True)
class PilotZeroAuthority:
    """Exact negative authority carried by every pilot report."""

    canonical_evidence_authorized: bool = False
    canonical_ib2_complete: bool = False
    canonical_filtering_authorized: bool = False
    canonical_deduplication_authorized: bool = False
    canonical_aggregation_authorized: bool = False
    canonical_scoring_authorized: bool = False
    network_access_authorized: bool = False
    sec_access_authorized: bool = False
    provider_access_authorized: bool = False
    credential_access_authorized: bool = False
    licensed_row_access_authorized: bool = False
    outcome_access_authorized: bool = False
    qc_upload_authorized: bool = False
    qc_processing_authorized: bool = False
    qc_job_authorized: bool = False
    qc_backtest_authorized: bool = False
    broker_access_authorized: bool = False
    operator_database_access_authorized: bool = False
    scheduler_access_authorized: bool = False
    paper_trading_authorized: bool = False
    live_trading_authorized: bool = False
    deployment_authorized: bool = False
    capital_authorized: bool = False
    order_authorized: bool = False
    trading_authority: bool = False
    authorized_outcome_looks: int = 0
    consumed_outcome_looks: int = 0
    research_looks: int = 0

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            expected = 0 if item.name.endswith("looks") else False
            if type(value) is not type(expected) or value != expected:
                raise SecNoncanonicalPilotContractError(
                    f"REFUSED: {item.name} must remain {expected!r}"
                )

    def to_payload(self) -> dict[str, object]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


_REPORT_FACTORY_TOKEN = object()


def _report_factory_binding(
    *,
    manifest_id: str,
    manifest_sha256: str,
    candidate_inventory_sha256: str,
    projection_inventory_sha256: str,
    input_count: int,
    resources: Iterable[PilotResourceMeasurement],
    constraints: tuple[object, ...],
) -> tuple[object, ...]:
    return (
        manifest_id,
        manifest_sha256,
        candidate_inventory_sha256,
        projection_inventory_sha256,
        input_count,
        tuple(
            sorted(
                (item.name, item.value, item.unit)
                for item in resources
            )
        ),
        constraints,
    )


def _report_factory_constraints(
    *,
    projection_count: int,
    unprojected_candidate_count: int,
    prequarantined_reasons: Iterable[str],
) -> tuple[object, ...]:
    reasons = tuple(prequarantined_reasons)
    return (
        projection_count,
        unprojected_candidate_count,
        tuple(sorted((reason, reasons.count(reason)) for reason in set(reasons))),
    )


@dataclass(frozen=True)
class _PilotReportFactorySeal:
    binding: tuple[object, ...]
    constraints: tuple[object, ...]
    token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self.token is not _REPORT_FACTORY_TOKEN
            or type(self.binding) is not tuple
            or type(self.constraints) is not tuple
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: report factory seal is invalid"
            )


@dataclass(frozen=True)
class SecNoncanonicalPilotOperationalReport:
    """Hash-bound compatibility/accounting evidence with no research authority."""

    manifest_id: str
    manifest_sha256: str
    candidate_inventory_sha256: str
    projection_inventory_sha256: str
    parser_git_commit: str
    input_count: int
    accepted_count: int
    refused_count: int
    quarantined_count: int
    reason_counts: tuple[PilotReasonCount, ...]
    resource_measurements: tuple[PilotResourceMeasurement, ...]
    compatibility: PilotCompatibilityOutcome
    compatibility_reasons: tuple[str, ...]
    stage_identities: tuple[PilotStageIdentity, ...] = ()
    authority: PilotZeroAuthority = field(default_factory=PilotZeroAuthority)
    operational_evidence_only: bool = True
    noncanonical: bool = True
    _factory_seal: _PilotReportFactorySeal | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _exact_string(self.manifest_id, label="manifest id", pattern=_IDENTIFIER_RE)
        _exact_sha256(self.manifest_sha256, label="manifest sha256")
        _exact_sha256(
            self.candidate_inventory_sha256,
            label="candidate inventory sha256",
        )
        _exact_sha256(
            self.projection_inventory_sha256,
            label="projection inventory sha256",
        )
        _exact_string(
            self.parser_git_commit,
            label="parser git commit",
            pattern=_GIT_COMMIT_RE,
        )
        counts = {
            PilotOperationalOutcome.ACCEPTED: _exact_nonnegative_int(
                self.accepted_count,
                label="accepted count",
            ),
            PilotOperationalOutcome.REFUSED: _exact_nonnegative_int(
                self.refused_count,
                label="refused count",
            ),
            PilotOperationalOutcome.QUARANTINED: _exact_nonnegative_int(
                self.quarantined_count,
                label="quarantined count",
            ),
        }
        total = _exact_nonnegative_int(self.input_count, label="input count")
        if sum(counts.values()) != total:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: accept/refuse/quarantine counts must exactly account for inputs"
            )

        try:
            reasons = tuple(self.reason_counts)
            resources = tuple(self.resource_measurements)
            stages = tuple(self.stage_identities)
            compatibility_reasons = tuple(self.compatibility_reasons)
        except TypeError as exc:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: report inventories must be iterable"
            ) from exc
        if any(type(item) is not PilotReasonCount for item in reasons):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: reason inventory contains an invalid item"
            )
        if any(type(item) is not PilotResourceMeasurement for item in resources):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: resource inventory contains an invalid item"
            )
        if any(type(item) is not PilotStageIdentity for item in stages):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: stage inventory contains an invalid item"
            )
        if any(
            type(item) is not str or _IDENTIFIER_RE.fullmatch(item) is None
            for item in compatibility_reasons
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: compatibility reasons must be named identifiers"
            )

        reasons = tuple(
            PilotReasonCount(
                outcome=item.outcome,
                reason=item.reason,
                count=item.count,
            )
            for item in reasons
        )
        resources = tuple(
            PilotResourceMeasurement(
                name=item.name,
                value=item.value,
                unit=item.unit,
            )
            for item in resources
        )
        stages = tuple(
            PilotStageIdentity(
                stage=item.stage,
                artifact_id=item.artifact_id,
                sha256=item.sha256,
            )
            for item in stages
        )

        reasons = tuple(sorted(reasons, key=lambda item: (item.outcome.value, item.reason)))
        resources = tuple(sorted(resources, key=lambda item: item.name))
        stages = tuple(sorted(stages, key=lambda item: _IB_STAGES.index(item.stage)))
        compatibility_reasons = tuple(sorted(compatibility_reasons))
        object.__setattr__(self, "reason_counts", reasons)
        object.__setattr__(self, "resource_measurements", resources)
        object.__setattr__(self, "stage_identities", stages)
        object.__setattr__(self, "compatibility_reasons", compatibility_reasons)

        if len(compatibility_reasons) != len(set(compatibility_reasons)):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: compatibility reasons must be unique"
            )

        reason_keys = tuple((item.outcome, item.reason) for item in reasons)
        if len(reason_keys) != len(set(reason_keys)):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: outcome reasons must be unique"
            )
        for outcome, expected in counts.items():
            observed = sum(item.count for item in reasons if item.outcome is outcome)
            if observed != expected:
                raise SecNoncanonicalPilotContractError(
                    f"REFUSED: named {outcome.value} reasons do not match its count"
                )

        resource_names = tuple(item.name for item in resources)
        if len(resource_names) != len(set(resource_names)):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: report requires unique named resource measurements"
            )
        if set(resource_names) != set(_REQUIRED_RESOURCE_UNITS) or any(
            item.unit != _REQUIRED_RESOURCE_UNITS[item.name] for item in resources
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: report resource names and units must match the pilot contract"
            )
        stage_names = tuple(item.stage for item in stages)
        if len(stage_names) != len(set(stage_names)):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: each optional IB stage identity may appear once"
            )
        if stage_names != _IB_STAGES[: len(stage_names)]:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: optional IB stage identities must form the IB-1A prefix"
            )
        _enum_member(
            self.compatibility,
            PilotCompatibilityOutcome,
            label="format compatibility",
        )
        if self.compatibility is PilotCompatibilityOutcome.COMPATIBLE and (
            compatibility_reasons
            or stage_names != _IB_STAGES
            or counts[PilotOperationalOutcome.REFUSED] != 0
            or counts[PilotOperationalOutcome.QUARANTINED] != 0
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: COMPATIBLE requires all stages, all inputs accepted, and no reasons"
            )
        if self.compatibility is PilotCompatibilityOutcome.NOT_RUN and (
            stage_names
            or not compatibility_reasons
            or counts[PilotOperationalOutcome.ACCEPTED] != 0
            or counts[PilotOperationalOutcome.QUARANTINED] != 0
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: NOT_RUN requires no completed stage, no accepted or "
                "quarantined inputs, and a named reason"
            )
        if self.compatibility in {
            PilotCompatibilityOutcome.PARTIALLY_COMPATIBLE,
            PilotCompatibilityOutcome.INCOMPATIBLE,
        } and not compatibility_reasons:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: non-compatible outcomes require a named reason"
            )
        if type(self.authority) is not PilotZeroAuthority:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: report requires the exact zero-authority boundary"
            )
        authority = PilotZeroAuthority(
            **{
                item.name: getattr(self.authority, item.name)
                for item in fields(self.authority)
            }
        )
        object.__setattr__(self, "authority", authority)
        if self.operational_evidence_only is not True or self.noncanonical is not True:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: pilot reports must stay operational-only and non-canonical"
            )
        seal = self._factory_seal
        if type(seal) is not _PilotReportFactorySeal:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: reports must be constructed through for_manifest"
            )
        seal.__post_init__()
        observed_binding = _report_factory_binding(
            manifest_id=self.manifest_id,
            manifest_sha256=self.manifest_sha256,
            candidate_inventory_sha256=self.candidate_inventory_sha256,
            projection_inventory_sha256=self.projection_inventory_sha256,
            input_count=self.input_count,
            resources=self.resource_measurements,
            constraints=seal.constraints,
        )
        if seal.binding != observed_binding:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: report factory binding or resource measurements do not "
                "match exact pilot manifest fields"
            )
        constraints = seal.constraints
        if (
            type(constraints) is not tuple
            or len(constraints) != 3
            or type(constraints[0]) is not int
            or constraints[0] < 0
            or type(constraints[1]) is not int
            or constraints[1] < 0
            or type(constraints[2]) is not tuple
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not int
                or item[1] <= 0
                for item in constraints[2]
            )
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: report factory constraints are invalid"
            )
        projection_count = constraints[0]
        unprojected_count = constraints[1]
        prequarantined_counts = dict(constraints[2])
        if self.accepted_count + self.quarantined_count > projection_count:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: accepted and quarantined counts cannot exceed projections"
            )
        observed_unprojected = sum(
            item.count
            for item in self.reason_counts
            if item.outcome is PilotOperationalOutcome.REFUSED
            and item.reason == "unprojected_candidate"
        )
        if observed_unprojected != unprojected_count:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: every unprojected candidate must remain a named refusal"
            )
        for reason, expected in prequarantined_counts.items():
            observed = sum(
                item.count
                for item in self.reason_counts
                if item.outcome is PilotOperationalOutcome.QUARANTINED
                and item.reason == reason
            )
            if observed != expected:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: report must exactly retain manifest-time projection quarantine"
                )

    @classmethod
    def for_manifest(
        cls,
        manifest: SecNoncanonicalPilotManifest,
        **kwargs: object,
    ) -> "SecNoncanonicalPilotOperationalReport":
        if type(manifest) is not SecNoncanonicalPilotManifest:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: report binding requires an exact pilot manifest"
            )
        protected = {
            "manifest_id",
            "manifest_sha256",
            "candidate_inventory_sha256",
            "projection_inventory_sha256",
            "input_count",
            "resource_measurements",
            "_factory_seal",
        }
        if protected.intersection(kwargs):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: manifest-bound report fields are derived, not caller supplied"
            )
        resources = tuple(
            PilotResourceMeasurement(name, value, unit)
            for name, (value, unit) in manifest.required_resource_values().items()
        )
        factory_constraints = _report_factory_constraints(
            projection_count=len(manifest.projections),
            unprojected_candidate_count=manifest.unprojected_candidate_count,
            prequarantined_reasons=manifest.prequarantined_projection_reasons,
        )
        factory_binding = _report_factory_binding(
            manifest_id=manifest.manifest_id,
            manifest_sha256=manifest.semantic_sha256,
            candidate_inventory_sha256=manifest.candidate_inventory_sha256,
            projection_inventory_sha256=manifest.projection_inventory_sha256,
            input_count=len(manifest.candidates),
            resources=resources,
            constraints=factory_constraints,
        )
        factory_seal = _PilotReportFactorySeal(
            binding=factory_binding,
            constraints=factory_constraints,
            token=_REPORT_FACTORY_TOKEN,
        )
        report = cls(
            manifest_id=manifest.manifest_id,
            manifest_sha256=manifest.semantic_sha256,
            candidate_inventory_sha256=manifest.candidate_inventory_sha256,
            projection_inventory_sha256=manifest.projection_inventory_sha256,
            input_count=len(manifest.candidates),
            resource_measurements=resources,
            _factory_seal=factory_seal,
            **kwargs,
        )
        report.verify_manifest(manifest)
        return report

    def verify_manifest(self, manifest: SecNoncanonicalPilotManifest) -> None:
        if (
            type(manifest) is not SecNoncanonicalPilotManifest
            or self.manifest_id != manifest.manifest_id
            or self.manifest_sha256 != manifest.semantic_sha256
            or self.candidate_inventory_sha256
            != manifest.candidate_inventory_sha256
            or self.projection_inventory_sha256
            != manifest.projection_inventory_sha256
            or self.input_count != len(manifest.candidates)
        ):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: report does not match the exact pilot manifest"
            )
        if self.accepted_count + self.quarantined_count > len(manifest.projections):
            raise SecNoncanonicalPilotContractError(
                "REFUSED: accepted and quarantined counts cannot exceed projections"
            )
        unprojected_reason_count = sum(
            item.count
            for item in self.reason_counts
            if item.outcome is PilotOperationalOutcome.REFUSED
            and item.reason == "unprojected_candidate"
        )
        if unprojected_reason_count != manifest.unprojected_candidate_count:
            raise SecNoncanonicalPilotContractError(
                "REFUSED: every unprojected candidate must remain a named refusal"
            )
        for reason in set(manifest.prequarantined_projection_reasons):
            required = manifest.prequarantined_projection_reasons.count(reason)
            retained = sum(
                item.count
                for item in self.reason_counts
                if item.outcome is PilotOperationalOutcome.QUARANTINED
                and item.reason == reason
            )
            if retained != required:
                raise SecNoncanonicalPilotContractError(
                    "REFUSED: report must exactly retain manifest-time projection quarantine"
                )
        observed_resources = {
            item.name: (item.value, item.unit) for item in self.resource_measurements
        }
        if observed_resources != manifest.required_resource_values():
            raise SecNoncanonicalPilotContractError(
                "REFUSED: resource measurements do not match the exact manifest"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "contract_version": SEC_NONCANONICAL_PILOT_CONTRACT_VERSION,
            "manifest_id": self.manifest_id,
            "manifest_sha256": self.manifest_sha256,
            "candidate_inventory_sha256": self.candidate_inventory_sha256,
            "projection_inventory_sha256": self.projection_inventory_sha256,
            "parser_git_commit": self.parser_git_commit,
            "input_unit": "accession_candidate",
            "stage_identities": [item.to_payload() for item in self.stage_identities],
            "accounting": {
                "input_count": self.input_count,
                "accepted_count": self.accepted_count,
                "refused_count": self.refused_count,
                "quarantined_count": self.quarantined_count,
                "reason_counts": [item.to_payload() for item in self.reason_counts],
            },
            "format_compatibility": {
                "outcome": self.compatibility.value,
                "reasons": list(self.compatibility_reasons),
            },
            "resource_measurements": [
                item.to_payload() for item in self.resource_measurements
            ],
            "authority": self.authority.to_payload(),
            "operational_evidence_only": True,
            "noncanonical": True,
        }

    @property
    def semantic_sha256(self) -> str:
        return hash_payload(self.to_payload())


def build_sec_noncanonical_pilot_manifest(
    *,
    periods: Iterable[str],
    candidates: Iterable[PilotAccessionCandidateIdentity],
    artifacts: Iterable[PilotVerbatimArtifactIdentity],
    projections: Iterable[PilotDerivedFlatIb1cProjectionIdentity],
) -> SecNoncanonicalPilotManifest:
    """Copy caller containers into one deterministic, validated manifest."""

    return SecNoncanonicalPilotManifest(
        periods=tuple(periods),
        candidates=tuple(candidates),
        artifacts=tuple(artifacts),
        projections=tuple(projections),
    )


__all__ = [
    "SEC_NONCANONICAL_PILOT_CONTRACT_VERSION",
    "SEC_NONCANONICAL_PILOT_DIRECT_IB1C_VERBATIM_CLAIM",
    "SEC_NONCANONICAL_PILOT_DERIVED_JSON_VERSION",
    "SEC_NONCANONICAL_PILOT_DERIVED_PROFILE_VERSION",
    "SEC_NONCANONICAL_PILOT_MAX_METADATA_SOURCE_BYTES",
    "SEC_NONCANONICAL_PILOT_MAX_PERIODS",
    "SEC_NONCANONICAL_PILOT_MAX_TOTAL_METADATA_BYTES",
    "SEC_NONCANONICAL_PILOT_MAX_TOTAL_XML_BYTES",
    "SEC_NONCANONICAL_PILOT_MAX_XML_SOURCE_BYTES",
    "SEC_NONCANONICAL_PILOT_MAX_XML_SOURCES",
    "SEC_NONCANONICAL_PILOT_MAX_ZIP_BYTES",
    "SEC_NONCANONICAL_PILOT_MIN_PERIODS",
    "SEC_NONCANONICAL_PILOT_OPTIONAL_EARLY_QUARTER_POLICY",
    "PilotArtifactKind",
    "PilotAccessionCandidateIdentity",
    "PilotCompatibilityOutcome",
    "PilotDerivedFlatIb1cProjectionIdentity",
    "PilotFieldDerivation",
    "PilotFieldProvenance",
    "PilotFieldTransform",
    "PilotOperationalOutcome",
    "PilotProjectionDisposition",
    "PilotReasonCount",
    "PilotResourceMeasurement",
    "PilotStageIdentity",
    "PilotVerbatimArtifactIdentity",
    "PilotZeroAuthority",
    "SecNoncanonicalPilotContractError",
    "SecNoncanonicalPilotManifest",
    "SecNoncanonicalPilotOperationalReport",
    "build_sec_noncanonical_pilot_manifest",
]
