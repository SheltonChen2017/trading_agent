"""Offline multi-period Form 4 supplied-link-evidence boundary.

IB-1E composes two or more contiguous, independently verified IB-1C
acceptance snapshots.  It reparses two extra fields from the exact metadata
bytes already retained and hash-bound by IB-1C: an asserted original
accession and an asserted primary-document SHA-256.  No fourth source is
introduced and no network, discovery, outcome, normalization, publication,
or execution surface exists here.

The extra fields are evidence supplied under a caller-defined, explicitly
non-official profile.  They prove internal byte and link consistency only;
they do not authenticate SEC provenance or prove that every amendment was
supplied.  Every supplied as-filed version is retained, amendments stay quarantined,
and official-link, complete-coverage, and canonical-filter authority remain
literal false values protected by the identity and result constructors.
"""
from __future__ import annotations

import re
from dataclasses import InitVar, dataclass
from datetime import datetime
from pathlib import Path

from data.hashing import hash_bytes, hash_payload
from research.insider_buying import sec_edgar_acceptance_snapshot as acceptance_module
from research.insider_buying.contracts import (
    ClassificationOutcome,
    ContractError,
    FilingCorpus,
    ParsedFiling,
    build_filing_corpus,
)
from research.insider_buying.form4_amendment_reconciliation import (
    MAX_FOOTNOTES_PER_FILING,
    MAX_REPORTING_OWNERS_PER_FILING,
    MAX_TOTAL_FOOTNOTES,
    MAX_TOTAL_REPORTING_OWNERS,
    MAX_TOTAL_TRANSACTIONS,
    MAX_TRANSACTIONS_PER_FILING,
    Form4AmendmentLineage,
    Form4AmendmentReconciliationError,
    Form4ObservedState,
    SecForm4XmlSource,
    SecForm4XmlSourceIdentity,
    _build_lineages,
    _canonical_utc,
    _issuer_cik_from_verified_primary_url,
    _parsed_corpus_hash,
    _source_identity,
)
from research.insider_buying.form4_xml import MAX_XML_BYTES, parse_form4_xml
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    LoadedSecEdgarAcceptanceSnapshot,
    MAX_METADATA_FIELD_NAME_CHARACTERS,
    MAX_METADATA_FIELDS,
    MAX_METADATA_SOURCE_BYTES,
    SecEdgarAcceptanceSnapshotIdentity,
    SecEdgarAcceptanceSnapshotError,
    SecEdgarAvailabilityRecord,
    SecEdgarAvailabilityTier,
    SecEdgarMetadataSchemaProfile,
    SecEdgarMetadataSource,
    SecEdgarMetadataSourceIdentity,
    _parse_exact_metadata_object,
)


FORM4_MULTI_PERIOD_EVIDENCE_VERSION = (
    "INSETF-IB1E-FORM4-MULTI-PERIOD-SUPPLIED-LINK-EVIDENCE-v1"
)
MAX_FORM4_EVIDENCE_PERIODS = 16
MAX_FORM4_EVIDENCE_RECORDS = 2_000_000
MAX_FORM4_EVIDENCE_METADATA_BYTES = 64 * 1024 * 1024
MAX_FORM4_EVIDENCE_XML_SOURCES = 256
MAX_FORM4_EVIDENCE_XML_BYTES = 64 * 1024 * 1024

_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_ACCEPTANCE_SNAPSHOT_ID_RE = re.compile(
    r"^sec-edgar-acceptance-(?P<year>[0-9]{4})q(?P<quarter>[1-4])-"
    r"(?P<hash_prefix>[0-9a-f]{16})$"
)
_EVIDENCE_ID_RE = re.compile(
    r"^form4-multi-period-evidence-(?P<start_year>[0-9]{4})q"
    r"(?P<start_quarter>[1-4])-(?P<end_year>[0-9]{4})q"
    r"(?P<end_quarter>[1-4])-(?P<hash_prefix>[0-9a-f]{16})$"
)
_VERIFIED_IDENTITY_FACTORY_TOKEN = object()
_VERIFIED_RESULT_FACTORY_TOKEN = object()


class Form4MultiPeriodEvidenceError(ContractError):
    """The offline IB-1E supplied-link-evidence contract failed closed."""


def _period_index(year: object, quarter: object, *, label: str) -> int:
    if (
        type(year) is not int
        or not 1900 <= year <= 9999
        or type(quarter) is not int
        or quarter not in {1, 2, 3, 4}
    ):
        raise Form4MultiPeriodEvidenceError(
            f"REFUSED: {label} must be a valid calendar quarter"
        )
    return year * 4 + quarter - 1


def _bounded_path(value: str | Path, *, label: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise Form4MultiPeriodEvidenceError(
            f"REFUSED: {label} must be a filesystem path"
        )
    try:
        path = Path(value)
    except (OSError, TypeError, ValueError) as exc:
        raise Form4MultiPeriodEvidenceError(
            f"REFUSED: {label} is invalid"
        ) from exc
    if not str(path) or len(str(path)) > 32_768:
        raise Form4MultiPeriodEvidenceError(
            f"REFUSED: {label} is invalid"
        )
    return path


@dataclass(frozen=True)
class SecEdgarAcceptancePeriodInput:
    """Paths needed to rebuild one IB-1C quarter through its verified loader."""

    acceptance_snapshot_path: str | Path
    parsed_snapshot_directory: str | Path
    raw_snapshot_directory: str | Path

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "acceptance_snapshot_path",
            _bounded_path(
                self.acceptance_snapshot_path,
                label="acceptance snapshot path",
            ),
        )
        object.__setattr__(
            self,
            "parsed_snapshot_directory",
            _bounded_path(
                self.parsed_snapshot_directory,
                label="parsed snapshot directory",
            ),
        )
        object.__setattr__(
            self,
            "raw_snapshot_directory",
            _bounded_path(
                self.raw_snapshot_directory,
                label="raw snapshot directory",
            ),
        )


@dataclass(frozen=True)
class SecForm4AmendmentEvidenceProfile:
    """One non-official mapping over an inclusive multi-quarter range."""

    profile_id: str
    exact_fields: tuple[str, ...]
    amends_accession_field: str
    primary_document_sha256_field: str
    upstream_metadata_profile_hash: str
    valid_from_year: int
    valid_from_quarter: int
    valid_through_year: int
    valid_through_quarter: int
    official_sec_profile_verified: bool = False

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or _IDENTIFIER_RE.fullmatch(self.profile_id) is None
            or type(self.exact_fields) is not tuple
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
            or not isinstance(self.amends_accession_field, str)
            or self.amends_accession_field not in self.exact_fields
            or not isinstance(self.primary_document_sha256_field, str)
            or self.primary_document_sha256_field not in self.exact_fields
            or self.amends_accession_field
            == self.primary_document_sha256_field
            or not isinstance(self.upstream_metadata_profile_hash, str)
            or _SHA256_RE.fullmatch(self.upstream_metadata_profile_hash) is None
            or self.official_sec_profile_verified is not False
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: supplied-link evidence profile is invalid or claims "
                "official authority"
            )
        start = _period_index(
            self.valid_from_year,
            self.valid_from_quarter,
            label="evidence profile start",
        )
        end = _period_index(
            self.valid_through_year,
            self.valid_through_quarter,
            label="evidence profile end",
        )
        if start > end:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: evidence profile quarter range is reversed"
            )

    def covers(self, year: int, quarter: int) -> bool:
        self._validate()
        period = _period_index(year, quarter, label="evidence period")
        start = self.valid_from_year * 4 + self.valid_from_quarter - 1
        end = self.valid_through_year * 4 + self.valid_through_quarter - 1
        return start <= period <= end

    def to_payload(self) -> dict[str, object]:
        self._validate()
        return {
            "profile_id": self.profile_id,
            "exact_fields": list(self.exact_fields),
            "amends_accession_field": self.amends_accession_field,
            "primary_document_sha256_field": (
                self.primary_document_sha256_field
            ),
            "upstream_metadata_profile_hash": (
                self.upstream_metadata_profile_hash
            ),
            "valid_from_year": self.valid_from_year,
            "valid_from_quarter": self.valid_from_quarter,
            "valid_through_year": self.valid_through_year,
            "valid_through_quarter": self.valid_through_quarter,
            "official_sec_profile_verified": False,
        }


@dataclass(frozen=True)
class SecEdgarAcceptancePeriodIdentity:
    year: int
    quarter: int
    acceptance_snapshot_id: str
    acceptance_lineage_hash: str
    parsed_snapshot_id: str
    parsed_lineage_hash: str
    raw_snapshot_id: str
    raw_lineage_hash: str
    raw_archive_sha256: str
    metadata_profile_hash: str
    source_inventory_hash: str
    records_hash: str
    record_count: int
    exact_acceptance_count: int
    filing_date_fallback_count: int

    def __post_init__(self) -> None:
        _period_index(self.year, self.quarter, label="period identity")
        snapshot_match = (
            _ACCEPTANCE_SNAPSHOT_ID_RE.fullmatch(self.acceptance_snapshot_id)
            if isinstance(self.acceptance_snapshot_id, str)
            else None
        )
        hash_fields = (
            self.acceptance_lineage_hash,
            self.parsed_lineage_hash,
            self.raw_lineage_hash,
            self.raw_archive_sha256,
            self.metadata_profile_hash,
            self.source_inventory_hash,
            self.records_hash,
        )
        hashes_valid = all(
            isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None
            for value in hash_fields
        )
        if (
            snapshot_match is None
            or int(snapshot_match.group("year")) != self.year
            or int(snapshot_match.group("quarter")) != self.quarter
            or not hashes_valid
            or (
                hashes_valid
                and snapshot_match.group("hash_prefix")
                != self.acceptance_lineage_hash[:16]
            )
            or not isinstance(self.parsed_snapshot_id, str)
            or not self.parsed_snapshot_id
            or not isinstance(self.raw_snapshot_id, str)
            or not self.raw_snapshot_id
            or type(self.record_count) is not int
            or not 0 <= self.record_count <= MAX_FORM4_EVIDENCE_RECORDS
            or type(self.exact_acceptance_count) is not int
            or type(self.filing_date_fallback_count) is not int
            or self.exact_acceptance_count < 0
            or self.filing_date_fallback_count < 0
            or self.exact_acceptance_count
            + self.filing_date_fallback_count
            != self.record_count
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: acceptance period identity is invalid"
            )

    @property
    def period_index(self) -> int:
        return self.year * 4 + self.quarter - 1

    def to_payload(self) -> dict[str, object]:
        return {
            "year": self.year,
            "quarter": self.quarter,
            "acceptance_snapshot_id": self.acceptance_snapshot_id,
            "acceptance_lineage_hash": self.acceptance_lineage_hash,
            "parsed_snapshot_id": self.parsed_snapshot_id,
            "parsed_lineage_hash": self.parsed_lineage_hash,
            "raw_snapshot_id": self.raw_snapshot_id,
            "raw_lineage_hash": self.raw_lineage_hash,
            "raw_archive_sha256": self.raw_archive_sha256,
            "metadata_profile_hash": self.metadata_profile_hash,
            "source_inventory_hash": self.source_inventory_hash,
            "records_hash": self.records_hash,
            "record_count": self.record_count,
            "exact_acceptance_count": self.exact_acceptance_count,
            "filing_date_fallback_count": self.filing_date_fallback_count,
        }


@dataclass(frozen=True)
class SuppliedForm4AmendmentLinkEvidence:
    accession_number: str
    document_type: str
    year: int
    quarter: int
    acceptance_snapshot_id: str
    acceptance_lineage_hash: str
    metadata_profile_hash: str
    metadata_source_sha256: str
    accepted_at_utc: str
    primary_document_url: str
    amends_accession: str | None
    primary_document_sha256: str

    def __post_init__(self) -> None:
        _period_index(self.year, self.quarter, label="link-evidence period")
        if (
            not isinstance(self.accession_number, str)
            or _ACCESSION_RE.fullmatch(self.accession_number) is None
            or self.document_type not in {"4", "4/A"}
            or not isinstance(self.acceptance_snapshot_id, str)
            or _ACCEPTANCE_SNAPSHOT_ID_RE.fullmatch(
                self.acceptance_snapshot_id
            )
            is None
            or any(
                not isinstance(value, str)
                or _SHA256_RE.fullmatch(value) is None
                for value in (
                    self.acceptance_lineage_hash,
                    self.metadata_profile_hash,
                    self.metadata_source_sha256,
                    self.primary_document_sha256,
                )
            )
            or not isinstance(self.accepted_at_utc, str)
            or not isinstance(self.primary_document_url, str)
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: supplied amendment-link evidence is invalid"
            )
        snapshot_match = _ACCEPTANCE_SNAPSHOT_ID_RE.fullmatch(
            self.acceptance_snapshot_id
        )
        if (
            snapshot_match is None
            or int(snapshot_match.group("year")) != self.year
            or int(snapshot_match.group("quarter")) != self.quarter
            or snapshot_match.group("hash_prefix")
            != self.acceptance_lineage_hash[:16]
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: supplied amendment-link period binding is invalid"
            )
        try:
            accepted_at = datetime.fromisoformat(self.accepted_at_utc)
            canonical = _canonical_utc(
                accepted_at, label="link-evidence acceptance time"
            ).isoformat(timespec="seconds")
            _issuer_cik_from_verified_primary_url(
                self.primary_document_url,
                accession_number=self.accession_number,
            )
        except (Form4AmendmentReconciliationError, ValueError) as exc:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: supplied amendment-link availability is invalid"
            ) from exc
        if canonical != self.accepted_at_utc:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: supplied amendment-link acceptance is not canonical UTC"
            )
        if self.document_type == "4":
            if self.amends_accession is not None:
                raise Form4MultiPeriodEvidenceError(
                    "REFUSED: original Form 4 link evidence must be empty"
                )
        elif (
            not isinstance(self.amends_accession, str)
            or _ACCESSION_RE.fullmatch(self.amends_accession) is None
            or self.amends_accession == self.accession_number
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: Form 4/A link evidence requires another canonical accession"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "document_type": self.document_type,
            "year": self.year,
            "quarter": self.quarter,
            "acceptance_snapshot_id": self.acceptance_snapshot_id,
            "acceptance_lineage_hash": self.acceptance_lineage_hash,
            "metadata_profile_hash": self.metadata_profile_hash,
            "metadata_source_sha256": self.metadata_source_sha256,
            "accepted_at_utc": self.accepted_at_utc,
            "primary_document_url": self.primary_document_url,
            "amends_accession": self.amends_accession,
            "primary_document_sha256": self.primary_document_sha256,
        }


@dataclass(frozen=True)
class Form4MultiPeriodEvidenceIdentity:
    contract_version: str
    parser_git_commit: str
    period_inventory: tuple[SecEdgarAcceptancePeriodIdentity, ...]
    period_inventory_hash: str
    evidence_profile: SecForm4AmendmentEvidenceProfile
    evidence_profile_hash: str
    supplied_link_evidence: tuple[SuppliedForm4AmendmentLinkEvidence, ...]
    supplied_link_evidence_hash: str
    source_inventory: tuple[SecForm4XmlSourceIdentity, ...]
    source_inventory_hash: str
    filing_count: int
    amendment_count: int
    lineage_count: int
    transaction_count: int
    parsed_corpus_hash: str
    declared_period_set_contiguous: bool
    official_amendment_link_verified: bool
    complete_amendment_coverage_verified: bool
    canonical_filter_authorized: bool
    evidence_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if (
            self.contract_version != FORM4_MULTI_PERIOD_EVIDENCE_VERSION
            or not isinstance(self.parser_git_commit, str)
            or _GIT_COMMIT_RE.fullmatch(self.parser_git_commit) is None
            or type(self.period_inventory) is not tuple
            or not 2 <= len(self.period_inventory) <= MAX_FORM4_EVIDENCE_PERIODS
            or any(
                type(item) is not SecEdgarAcceptancePeriodIdentity
                for item in self.period_inventory
            )
            or not isinstance(self.period_inventory_hash, str)
            or _SHA256_RE.fullmatch(self.period_inventory_hash) is None
            or type(self.evidence_profile)
            is not SecForm4AmendmentEvidenceProfile
            or not isinstance(self.evidence_profile_hash, str)
            or _SHA256_RE.fullmatch(self.evidence_profile_hash) is None
            or type(self.supplied_link_evidence) is not tuple
            or not self.supplied_link_evidence
            or len(self.supplied_link_evidence)
            > MAX_FORM4_EVIDENCE_XML_SOURCES
            or any(
                type(item) is not SuppliedForm4AmendmentLinkEvidence
                for item in self.supplied_link_evidence
            )
            or not isinstance(self.supplied_link_evidence_hash, str)
            or _SHA256_RE.fullmatch(self.supplied_link_evidence_hash) is None
            or type(self.source_inventory) is not tuple
            or not self.source_inventory
            or len(self.source_inventory) > MAX_FORM4_EVIDENCE_XML_SOURCES
            or any(
                type(item) is not SecForm4XmlSourceIdentity
                for item in self.source_inventory
            )
            or not isinstance(self.source_inventory_hash, str)
            or _SHA256_RE.fullmatch(self.source_inventory_hash) is None
            or type(self.filing_count) is not int
            or self.filing_count != len(self.source_inventory)
            or self.filing_count != len(self.supplied_link_evidence)
            or type(self.amendment_count) is not int
            or not 0 <= self.amendment_count <= self.filing_count
            or type(self.lineage_count) is not int
            or not 0 < self.lineage_count <= self.filing_count
            or self.amendment_count != self.filing_count - self.lineage_count
            or type(self.transaction_count) is not int
            or not 0 <= self.transaction_count <= MAX_TOTAL_TRANSACTIONS
            or not isinstance(self.parsed_corpus_hash, str)
            or _SHA256_RE.fullmatch(self.parsed_corpus_hash) is None
            or self.declared_period_set_contiguous is not True
            or self.official_amendment_link_verified is not False
            or self.complete_amendment_coverage_verified is not False
            or self.canonical_filter_authorized is not False
            or not isinstance(self.evidence_id, str)
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: multi-period evidence identity is invalid or claims authority"
            )

        try:
            self.evidence_profile._validate()
        except Form4MultiPeriodEvidenceError:
            raise
        periods = tuple(item.period_index for item in self.period_inventory)
        evidence_accessions = tuple(
            item.accession_number for item in self.supplied_link_evidence
        )
        source_accessions = tuple(
            item.accession_number for item in self.source_inventory
        )
        if (
            periods != tuple(sorted(periods))
            or len(set(periods)) != len(periods)
            or any(
                right != left + 1
                for left, right in zip(periods, periods[1:])
            )
            or hash_payload(
                [item.to_payload() for item in self.period_inventory]
            )
            != self.period_inventory_hash
            or hash_payload(self.evidence_profile.to_payload())
            != self.evidence_profile_hash
            or any(
                item.metadata_profile_hash
                != self.evidence_profile.upstream_metadata_profile_hash
                or not self.evidence_profile.covers(item.year, item.quarter)
                for item in self.period_inventory
            )
            or evidence_accessions != tuple(sorted(evidence_accessions))
            or len(set(evidence_accessions)) != len(evidence_accessions)
            or source_accessions != tuple(sorted(source_accessions))
            or source_accessions != evidence_accessions
            or hash_payload(
                [item.to_payload() for item in self.supplied_link_evidence]
            )
            != self.supplied_link_evidence_hash
            or hash_payload(
                [item.to_payload() for item in self.source_inventory]
            )
            != self.source_inventory_hash
            or self.amendment_count
            != sum(
                item.document_type == "4/A"
                for item in self.supplied_link_evidence
            )
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: multi-period evidence inventories are inconsistent"
            )
        period_by_key = {
            (item.year, item.quarter): item for item in self.period_inventory
        }
        if any(
            (item.year, item.quarter) not in period_by_key
            or item.acceptance_snapshot_id
            != period_by_key[(item.year, item.quarter)].acceptance_snapshot_id
            or item.acceptance_lineage_hash
            != period_by_key[(item.year, item.quarter)].acceptance_lineage_hash
            or item.metadata_profile_hash
            != period_by_key[(item.year, item.quarter)].metadata_profile_hash
            for item in self.supplied_link_evidence
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: supplied link evidence is outside the period inventory"
            )
        source_by_accession = {
            item.accession_number: item for item in self.source_inventory
        }
        if any(
            source_by_accession[item.accession_number].xml_sha256
            != item.primary_document_sha256
            or source_by_accession[item.accession_number].primary_document_url
            != item.primary_document_url
            or source_by_accession[item.accession_number].amends_accession
            != item.amends_accession
            for item in self.supplied_link_evidence
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: link evidence disagrees with the XML source inventory"
            )

        start = self.period_inventory[0]
        end = self.period_inventory[-1]
        match = _EVIDENCE_ID_RE.fullmatch(self.evidence_id)
        if (
            match is None
            or int(match.group("start_year")) != start.year
            or int(match.group("start_quarter")) != start.quarter
            or int(match.group("end_year")) != end.year
            or int(match.group("end_quarter")) != end.quarter
            or match.group("hash_prefix")
            != hash_payload(self.lineage_payload())[:16]
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: multi-period evidence ID is invalid"
            )
        if _verified_factory_token is not _VERIFIED_IDENTITY_FACTORY_TOKEN:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: multi-period evidence identity must be factory-created"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "parser_git_commit": self.parser_git_commit,
            "period_inventory_hash": self.period_inventory_hash,
            "evidence_profile_hash": self.evidence_profile_hash,
            "supplied_link_evidence_hash": self.supplied_link_evidence_hash,
            "source_inventory_hash": self.source_inventory_hash,
            "filing_count": self.filing_count,
            "amendment_count": self.amendment_count,
            "lineage_count": self.lineage_count,
            "transaction_count": self.transaction_count,
            "parsed_corpus_hash": self.parsed_corpus_hash,
            "declared_period_set_contiguous": True,
            "official_amendment_link_verified": False,
            "complete_amendment_coverage_verified": False,
            "canonical_filter_authorized": False,
        }

    def to_payload(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "parser_git_commit": self.parser_git_commit,
            "period_inventory": [
                item.to_payload() for item in self.period_inventory
            ],
            "period_inventory_hash": self.period_inventory_hash,
            "evidence_profile": self.evidence_profile.to_payload(),
            "evidence_profile_hash": self.evidence_profile_hash,
            "supplied_link_evidence": [
                item.to_payload() for item in self.supplied_link_evidence
            ],
            "supplied_link_evidence_hash": self.supplied_link_evidence_hash,
            "source_inventory": [
                item.to_payload() for item in self.source_inventory
            ],
            "source_inventory_hash": self.source_inventory_hash,
            **{
                key: value
                for key, value in self.lineage_payload().items()
                if key
                not in {
                    "contract_version",
                    "parser_git_commit",
                    "period_inventory_hash",
                    "evidence_profile_hash",
                    "supplied_link_evidence_hash",
                    "source_inventory_hash",
                }
            },
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True)
class ProfileBoundForm4AmendmentEvidence:
    """As-filed supplied evidence with permanently disabled authority."""

    identity: Form4MultiPeriodEvidenceIdentity
    xml_sources: tuple[SecForm4XmlSource, ...]
    supplied_link_evidence: tuple[SuppliedForm4AmendmentLinkEvidence, ...]
    as_filed_corpus: FilingCorpus
    lineages: tuple[Form4AmendmentLineage, ...]
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _VERIFIED_RESULT_FACTORY_TOKEN:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: multi-period evidence result must be factory-created"
            )
        if (
            type(self.identity) is not Form4MultiPeriodEvidenceIdentity
            or type(self.xml_sources) is not tuple
            or type(self.supplied_link_evidence) is not tuple
            or type(self.as_filed_corpus) is not FilingCorpus
            or type(self.lineages) is not tuple
            or any(
                type(source) is not SecForm4XmlSource
                for source in self.xml_sources
            )
            or any(
                type(item) is not SuppliedForm4AmendmentLinkEvidence
                for item in self.supplied_link_evidence
            )
            or any(
                type(lineage) is not Form4AmendmentLineage
                for lineage in self.lineages
            )
            or self.identity.official_amendment_link_verified is not False
            or self.identity.complete_amendment_coverage_verified is not False
            or self.identity.canonical_filter_authorized is not False
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: multi-period evidence result is invalid"
            )
        try:
            rebuilt_sources = tuple(
                SecForm4XmlSource(
                    accession_number=source.accession_number,
                    xml_bytes=source.xml_bytes,
                    primary_document_url=source.primary_document_url,
                    retrieved_at=source.retrieved_at,
                    capture_git_commit=source.capture_git_commit,
                    amends_accession=source.amends_accession,
                )
                for source in self.xml_sources
            )
            rebuilt_inventory = tuple(
                _source_identity(source) for source in rebuilt_sources
            )
            rebuilt_corpus = build_filing_corpus(
                list(self.as_filed_corpus.filings)
            )
            rebuilt_lineages = _build_lineages(self.as_filed_corpus)
        except (ContractError, TypeError, ValueError) as exc:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: multi-period evidence result cannot be rebuilt"
            ) from exc
        if (
            rebuilt_sources != self.xml_sources
            or tuple(
                sorted(rebuilt_sources, key=lambda item: item.accession_number)
            )
            != self.xml_sources
            or rebuilt_inventory != self.identity.source_inventory
            or self.supplied_link_evidence
            != self.identity.supplied_link_evidence
            or rebuilt_corpus != self.as_filed_corpus
            or rebuilt_lineages != self.lineages
            or self.identity.filing_count != len(self.as_filed_corpus.filings)
            or self.identity.lineage_count != len(self.lineages)
            or self.identity.amendment_count
            != sum(len(lineage.versions) - 1 for lineage in self.lineages)
            or self.identity.transaction_count
            != sum(
                len(filing.transactions)
                for filing in self.as_filed_corpus.filings
            )
            or _parsed_corpus_hash(self.as_filed_corpus)
            != self.identity.parsed_corpus_hash
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: multi-period result disagrees with its identity"
            )

        sources_by_accession = {
            source.accession_number: source for source in rebuilt_sources
        }
        evidence_by_accession = {
            item.accession_number: item for item in self.supplied_link_evidence
        }
        filings_by_accession = {
            filing.envelope.accession_number: filing
            for filing in self.as_filed_corpus.filings
        }
        if (
            len(sources_by_accession) != len(rebuilt_sources)
            or len(evidence_by_accession) != len(self.supplied_link_evidence)
            or set(sources_by_accession)
            != set(evidence_by_accession)
            or set(sources_by_accession) != set(filings_by_accession)
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: multi-period result accession inventories disagree"
            )
        for accession, filing in filings_by_accession.items():
            source = sources_by_accession[accession]
            evidence = evidence_by_accession[accession]
            accepted_at = filing.envelope.availability.accepted_at
            if (
                accepted_at is None
                or evidence.document_type != filing.envelope.form_type
                or evidence.amends_accession
                != filing.envelope.amends_accession
                or evidence.primary_document_sha256 != source.xml_sha256
                or evidence.primary_document_sha256
                != filing.envelope.source_sha256
                or evidence.primary_document_url
                != filing.envelope.source_name
                or evidence.accepted_at_utc
                != _canonical_utc(
                    accepted_at, label="result filing acceptance time"
                ).isoformat(timespec="seconds")
            ):
                raise Form4MultiPeriodEvidenceError(
                    "REFUSED: supplied evidence disagrees with parsed filing bytes"
                )

    def lineage(self, original_accession: str) -> Form4AmendmentLineage:
        for lineage in self.lineages:
            if lineage.original_accession == original_accession:
                return lineage
        raise KeyError(original_accession)

    @property
    def declared_period_set_contiguous(self) -> bool:
        return True

    @property
    def official_amendment_link_verified(self) -> bool:
        return False

    @property
    def complete_amendment_coverage_verified(self) -> bool:
        return False

    @property
    def canonical_filter_authorized(self) -> bool:
        return False

    def observed_state_at(
        self, original_accession: str, as_of: datetime
    ) -> Form4ObservedState | None:
        return self.lineage(original_accession).observed_state_at(as_of)


def _period_identity(
    loaded: LoadedSecEdgarAcceptanceSnapshot,
) -> SecEdgarAcceptancePeriodIdentity:
    identity = loaded.identity
    if (
        type(identity) is not SecEdgarAcceptanceSnapshotIdentity
        or type(identity.metadata_profile) is not SecEdgarMetadataSchemaProfile
        or type(loaded.records) is not tuple
        or any(
            type(record) is not SecEdgarAvailabilityRecord
            for record in loaded.records
        )
        or type(loaded.sources) is not tuple
        or any(
            type(source) is not SecEdgarMetadataSource
            for source in loaded.sources
        )
        or type(identity.source_inventory) is not tuple
        or any(
            type(item) is not SecEdgarMetadataSourceIdentity
            for item in identity.source_inventory
        )
    ):
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: loaded acceptance period has invalid contract types"
        )
    exact_count = sum(
        record.availability_tier
        is SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
        for record in loaded.records
    )
    fallback_count = len(loaded.records) - exact_count
    if (
        len(loaded.records) != identity.record_count
        or exact_count != identity.exact_acceptance_count
        or fallback_count != identity.filing_date_fallback_count
        or tuple(
            sorted(loaded.records, key=lambda item: item.accession_number)
        )
        != loaded.records
        or len({item.accession_number for item in loaded.records})
        != len(loaded.records)
        or hash_payload([item.to_payload() for item in loaded.records])
        != identity.records_hash
        or hash_payload(identity.metadata_profile.to_payload())
        != identity.metadata_profile_hash
        or hash_payload(
            [item.to_payload() for item in identity.source_inventory]
        )
        != identity.source_inventory_hash
    ):
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: loaded acceptance period disagrees with its identity"
        )
    return SecEdgarAcceptancePeriodIdentity(
        year=identity.year,
        quarter=identity.quarter,
        acceptance_snapshot_id=identity.snapshot_id,
        acceptance_lineage_hash=identity.lineage_hash,
        parsed_snapshot_id=identity.parsed_snapshot_id,
        parsed_lineage_hash=identity.parsed_lineage_hash,
        raw_snapshot_id=identity.raw_snapshot_id,
        raw_lineage_hash=identity.raw_lineage_hash,
        raw_archive_sha256=identity.raw_archive_sha256,
        metadata_profile_hash=identity.metadata_profile_hash,
        source_inventory_hash=identity.source_inventory_hash,
        records_hash=identity.records_hash,
        record_count=identity.record_count,
        exact_acceptance_count=identity.exact_acceptance_count,
        filing_date_fallback_count=identity.filing_date_fallback_count,
    )


def _canonical_source(source: SecForm4XmlSource) -> SecForm4XmlSource:
    try:
        rebuilt = SecForm4XmlSource(
            accession_number=source.accession_number,
            xml_bytes=source.xml_bytes,
            primary_document_url=source.primary_document_url,
            retrieved_at=source.retrieved_at,
            capture_git_commit=source.capture_git_commit,
            amends_accession=source.amends_accession,
        )
    except (AttributeError, Form4AmendmentReconciliationError) as exc:
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: XML source is not a valid immutable source"
        ) from exc
    if (
        rebuilt != source
        or rebuilt.xml_sha256 != source.xml_sha256
        or rebuilt.retrieved_at_utc != source.retrieved_at_utc
    ):
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: XML source state is internally inconsistent"
        )
    return rebuilt


def _metadata_sources_by_accession(
    loaded: LoadedSecEdgarAcceptanceSnapshot,
) -> dict[str, SecEdgarMetadataSource]:
    if (
        len(loaded.sources) != len(loaded.identity.source_inventory)
        or any(
            len(source.metadata_bytes) > MAX_METADATA_SOURCE_BYTES
            for source in loaded.sources
        )
    ):
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: verified metadata source inventory is inconsistent"
        )
    result: dict[str, SecEdgarMetadataSource] = {}
    for identity, source in zip(
        loaded.identity.source_inventory, loaded.sources
    ):
        if (
            identity.accession_number in result
            or source.metadata_sha256 != identity.metadata_sha256
            or len(source.metadata_bytes) != identity.metadata_size_bytes
            or source.source_url != identity.source_url
            or source.retrieved_at_utc != identity.retrieved_at_utc
            or source.capture_git_commit != identity.capture_git_commit
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: verified metadata source identity is inconsistent"
            )
        result[identity.accession_number] = source
    return result


def _profile_matches_upstream(
    evidence_profile: SecForm4AmendmentEvidenceProfile,
    upstream: SecEdgarMetadataSchemaProfile,
    upstream_hash: str,
) -> bool:
    core_fields = {
        upstream.accession_number_field,
        upstream.form_type_field,
        upstream.filing_date_field,
        upstream.accepted_at_field,
        upstream.primary_document_url_field,
    }
    return (
        hash_payload(upstream.to_payload()) == upstream_hash
        and upstream_hash == evidence_profile.upstream_metadata_profile_hash
        and upstream.exact_fields == evidence_profile.exact_fields
        and evidence_profile.amends_accession_field not in core_fields
        and evidence_profile.primary_document_sha256_field not in core_fields
    )


def _validate_metadata_core(
    payload: dict[str, str],
    profile: SecEdgarMetadataSchemaProfile,
    *,
    accession_number: str,
    document_type: str,
    accepted_at: datetime,
    filing_date_text: str,
    primary_document_url: str,
) -> None:
    try:
        payload_accepted = datetime.fromisoformat(
            payload[profile.accepted_at_field]
        )
        canonical_payload_accepted = _canonical_utc(
            payload_accepted, label="profile acceptance time"
        )
    except (KeyError, ValueError, Form4AmendmentReconciliationError) as exc:
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: profile-bound metadata core is invalid"
        ) from exc
    if (
        payload[profile.accession_number_field] != accession_number
        or payload[profile.form_type_field] != document_type
        or payload[profile.filing_date_field] != filing_date_text
        or canonical_payload_accepted != accepted_at
        or payload[profile.primary_document_url_field]
        != primary_document_url
    ):
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: profile-bound metadata disagrees with acceptance evidence"
        )


def _validate_corpus_lineages(
    filings: list[ParsedFiling],
) -> tuple[FilingCorpus, tuple[Form4AmendmentLineage, ...]]:
    try:
        corpus = build_filing_corpus(filings)
        lineages = _build_lineages(corpus)
    except (ContractError, Form4AmendmentReconciliationError) as exc:
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: supplied Form 4 amendment lineage is invalid"
        ) from exc
    lineage_accessions = [
        version.accession_number
        for lineage in lineages
        for version in lineage.versions
    ]
    corpus_accessions = {
        filing.envelope.accession_number for filing in corpus.filings
    }
    corpus_edges = {
        (original, amendment)
        for original, amendments in corpus.superseded_by
        for amendment in amendments
    }
    lineage_edges = {
        (lineage.original_accession, version.accession_number)
        for lineage in lineages
        for version in lineage.versions[1:]
    }
    if (
        sum(len(lineage.versions) for lineage in lineages)
        != len(corpus.filings)
        or len(lineage_accessions) != len(set(lineage_accessions))
        or set(lineage_accessions) != corpus_accessions
        or corpus_edges != lineage_edges
    ):
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: corpus and supplied amendment chronology disagree"
        )
    return corpus, lineages


def assemble_sec_form4_multi_period_evidence(
    periods: tuple[SecEdgarAcceptancePeriodInput, ...],
    *,
    sources: tuple[SecForm4XmlSource, ...],
    evidence_profile: SecForm4AmendmentEvidenceProfile,
    parser_git_commit: str,
) -> ProfileBoundForm4AmendmentEvidence:
    """Compose a bounded contiguous sample without granting canonical authority."""

    if (
        not isinstance(parser_git_commit, str)
        or _GIT_COMMIT_RE.fullmatch(parser_git_commit) is None
    ):
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: parser Git commit must be a full lowercase SHA-1"
        )
    if (
        type(periods) is not tuple
        or not 2 <= len(periods) <= MAX_FORM4_EVIDENCE_PERIODS
        or any(type(item) is not SecEdgarAcceptancePeriodInput for item in periods)
    ):
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: period inputs must be a bounded immutable tuple"
        )
    try:
        canonical_periods = tuple(
            SecEdgarAcceptancePeriodInput(
                acceptance_snapshot_path=item.acceptance_snapshot_path,
                parsed_snapshot_directory=item.parsed_snapshot_directory,
                raw_snapshot_directory=item.raw_snapshot_directory,
            )
            for item in periods
        )
    except (AttributeError, Form4MultiPeriodEvidenceError) as exc:
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: period input state is internally inconsistent"
        ) from exc
    if (
        type(sources) is not tuple
        or not sources
        or len(sources) > MAX_FORM4_EVIDENCE_XML_SOURCES
        or any(type(source) is not SecForm4XmlSource for source in sources)
        or any(
            type(source.xml_bytes) is not bytes
            or not 0 < len(source.xml_bytes) <= MAX_XML_BYTES
            for source in sources
        )
        or sum(len(source.xml_bytes) for source in sources)
        > MAX_FORM4_EVIDENCE_XML_BYTES
    ):
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: XML sources must be a non-empty bounded immutable tuple"
        )
    if type(evidence_profile) is not SecForm4AmendmentEvidenceProfile:
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: a supplied-link evidence profile is required"
        )
    evidence_profile._validate()
    evidence_profile_hash = hash_payload(evidence_profile.to_payload())
    canonical_sources = tuple(
        sorted(
            (_canonical_source(source) for source in sources),
            key=lambda item: item.accession_number,
        )
    )
    if len({source.accession_number for source in canonical_sources}) != len(
        canonical_sources
    ):
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: duplicate XML accession in supplied evidence"
        )

    loaded_with_identity: list[
        tuple[LoadedSecEdgarAcceptanceSnapshot, SecEdgarAcceptancePeriodIdentity]
    ] = []
    prevalidated_record_count = 0
    prevalidated_metadata_bytes = 0
    for period in canonical_periods:
        try:
            loaded = acceptance_module.load_sec_edgar_acceptance_snapshot(
                period.acceptance_snapshot_path,
                parsed_snapshot_directory=period.parsed_snapshot_directory,
                raw_snapshot_directory=period.raw_snapshot_directory,
            )
        except SecEdgarAcceptanceSnapshotError as exc:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: period is not a verified IB-1C boundary"
            ) from exc
        if type(loaded) is not LoadedSecEdgarAcceptanceSnapshot:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: period loader returned an invalid boundary"
            )
        period_identity = _period_identity(loaded)
        prevalidated_record_count += period_identity.record_count
        prevalidated_metadata_bytes += sum(
            len(source.metadata_bytes) for source in loaded.sources
        )
        if (
            prevalidated_record_count > MAX_FORM4_EVIDENCE_RECORDS
            or prevalidated_metadata_bytes
            > MAX_FORM4_EVIDENCE_METADATA_BYTES
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: multi-period evidence exceeds an aggregate resource cap"
            )
        loaded_with_identity.append((loaded, period_identity))
    loaded_with_identity.sort(
        key=lambda item: (item[1].year, item[1].quarter)
    )
    loaded_periods = [item[0] for item in loaded_with_identity]
    period_identities = tuple(item[1] for item in loaded_with_identity)
    period_indexes = tuple(item.period_index for item in period_identities)
    if (
        len(set(period_indexes)) != len(period_indexes)
        or any(
            right != left + 1
            for left, right in zip(period_indexes, period_indexes[1:])
        )
    ):
        raise Form4MultiPeriodEvidenceError(
            "REFUSED: period set contains an overlap or gap"
        )

    first_upstream_payload: dict[str, object] | None = None
    records_by_accession: dict[
        str, tuple[SecEdgarAvailabilityRecord, LoadedSecEdgarAcceptanceSnapshot]
    ] = {}
    metadata_by_accession: dict[str, SecEdgarMetadataSource] = {}
    for loaded in loaded_periods:
        identity = loaded.identity
        upstream_profile = identity.metadata_profile
        upstream_payload = upstream_profile.to_payload()
        if first_upstream_payload is None:
            first_upstream_payload = upstream_payload
        if (
            upstream_payload != first_upstream_payload
            or not _profile_matches_upstream(
                evidence_profile,
                upstream_profile,
                identity.metadata_profile_hash,
            )
            or not evidence_profile.covers(identity.year, identity.quarter)
            or not upstream_profile.covers(identity.year, identity.quarter)
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: evidence profile does not exactly bind every period profile"
            )
        if (
            len(loaded.records) != identity.record_count
            or len({record.accession_number for record in loaded.records})
            != len(loaded.records)
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: verified period record inventory is inconsistent"
            )
        period_metadata = _metadata_sources_by_accession(loaded)
        for record in loaded.records:
            if record.accession_number in records_by_accession:
                raise Form4MultiPeriodEvidenceError(
                    "REFUSED: duplicate accession across verified periods"
                )
            records_by_accession[record.accession_number] = (record, loaded)
        for accession, source in period_metadata.items():
            if accession in metadata_by_accession:
                raise Form4MultiPeriodEvidenceError(
                    "REFUSED: duplicate metadata accession across periods"
                )
            metadata_by_accession[accession] = source

    filings: list[ParsedFiling] = []
    link_evidence: list[SuppliedForm4AmendmentLinkEvidence] = []
    total_reporting_owners = 0
    total_footnotes = 0
    total_transactions = 0
    for source in canonical_sources:
        record_context = records_by_accession.get(source.accession_number)
        if record_context is None:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: XML source accession is absent from period evidence"
            )
        record, loaded = record_context
        if record.document_type not in {"4", "4/A"}:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: supplied-link evidence accepts only Form 4/4-A"
            )
        if (
            record.availability_tier
            is not SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
            or record.accepted_at is None
            or record.primary_document_url is None
            or record.metadata_source_sha256 is None
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: supplied XML requires exact acceptance evidence"
            )
        if source.primary_document_url != record.primary_document_url:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: XML source URL disagrees with acceptance evidence"
            )
        if source.retrieved_at < record.accepted_at:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: XML retrieval precedes public acceptance"
            )
        metadata_source = metadata_by_accession.get(source.accession_number)
        if (
            metadata_source is None
            or metadata_source.metadata_sha256
            != record.metadata_source_sha256
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: exact metadata source is absent or hash-mismatched"
            )
        try:
            payload = _parse_exact_metadata_object(
                metadata_source.metadata_bytes,
                evidence_profile.exact_fields,
                label="profile-bound amendment evidence",
            )
        except SecEdgarAcceptanceSnapshotError as exc:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: profile-bound amendment evidence is malformed"
            ) from exc
        upstream_profile = loaded.identity.metadata_profile
        _validate_metadata_core(
            payload,
            upstream_profile,
            accession_number=record.accession_number,
            document_type=record.document_type,
            accepted_at=record.accepted_at,
            filing_date_text=record.filing_date.isoformat(),
            primary_document_url=record.primary_document_url,
        )
        asserted_link = payload[evidence_profile.amends_accession_field]
        asserted_document_hash = payload[
            evidence_profile.primary_document_sha256_field
        ]
        if record.document_type == "4":
            if asserted_link != "":
                raise Form4MultiPeriodEvidenceError(
                    "REFUSED: original Form 4 link evidence must be empty"
                )
            profile_link: str | None = None
        else:
            if (
                _ACCESSION_RE.fullmatch(asserted_link) is None
                or asserted_link == record.accession_number
            ):
                raise Form4MultiPeriodEvidenceError(
                    "REFUSED: Form 4/A link evidence is not canonical"
                )
            profile_link = asserted_link
        if source.amends_accession != profile_link:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: caller link disagrees with profile-bound link evidence"
            )
        if (
            _SHA256_RE.fullmatch(asserted_document_hash) is None
            or asserted_document_hash != hash_bytes(source.xml_bytes)
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: profile-bound primary-document hash disagrees with XML"
            )
        try:
            filing = parse_form4_xml(
                source.xml_bytes,
                accession_number=source.accession_number,
                acceptance=record.accepted_at,
                source_name=source.primary_document_url,
                amends_accession=profile_link,
            )
        except ContractError as exc:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: XML source violates the pinned Form 4 contract"
            ) from exc
        if filing.envelope.form_type != record.document_type:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: XML form type disagrees with acceptance evidence"
            )
        if record.document_type == "4/A" and any(
            transaction.outcomes
            != (ClassificationOutcome.EXCLUDE_AMENDED_FILING,)
            for transaction in filing.transactions
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: Form 4/A rows must remain explicitly excluded"
            )
        expected_issuer_cik = _issuer_cik_from_verified_primary_url(
            record.primary_document_url,
            accession_number=record.accession_number,
        )
        if filing.envelope.issuer_cik != expected_issuer_cik:
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: XML issuer CIK disagrees with acceptance evidence"
            )
        reporting_owner_count = len(filing.reporting_owners)
        footnote_count = len(filing.footnotes)
        transaction_count = len(filing.transactions)
        if (
            reporting_owner_count > MAX_REPORTING_OWNERS_PER_FILING
            or footnote_count > MAX_FOOTNOTES_PER_FILING
            or transaction_count > MAX_TRANSACTIONS_PER_FILING
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: parsed filing exceeds a per-filing resource cap"
            )
        total_reporting_owners += reporting_owner_count
        total_footnotes += footnote_count
        total_transactions += transaction_count
        if (
            total_reporting_owners > MAX_TOTAL_REPORTING_OWNERS
            or total_footnotes > MAX_TOTAL_FOOTNOTES
            or total_transactions > MAX_TOTAL_TRANSACTIONS
        ):
            raise Form4MultiPeriodEvidenceError(
                "REFUSED: parsed sample exceeds an aggregate resource cap"
            )
        filings.append(filing)
        link_evidence.append(
            SuppliedForm4AmendmentLinkEvidence(
                accession_number=record.accession_number,
                document_type=record.document_type,
                year=loaded.identity.year,
                quarter=loaded.identity.quarter,
                acceptance_snapshot_id=loaded.identity.snapshot_id,
                acceptance_lineage_hash=loaded.identity.lineage_hash,
                metadata_profile_hash=loaded.identity.metadata_profile_hash,
                metadata_source_sha256=record.metadata_source_sha256,
                accepted_at_utc=_canonical_utc(
                    record.accepted_at, label="evidence acceptance time"
                ).isoformat(timespec="seconds"),
                primary_document_url=record.primary_document_url,
                amends_accession=profile_link,
                primary_document_sha256=asserted_document_hash,
            )
        )

    corpus, lineages = _validate_corpus_lineages(filings)
    source_inventory = tuple(_source_identity(item) for item in canonical_sources)
    evidence_inventory = tuple(link_evidence)
    period_inventory_hash = hash_payload(
        [item.to_payload() for item in period_identities]
    )
    evidence_inventory_hash = hash_payload(
        [item.to_payload() for item in evidence_inventory]
    )
    source_inventory_hash = hash_payload(
        [item.to_payload() for item in source_inventory]
    )
    amendment_count = sum(
        item.document_type == "4/A" for item in evidence_inventory
    )
    parsed_corpus_hash = _parsed_corpus_hash(corpus)
    identity_payload = {
        "contract_version": FORM4_MULTI_PERIOD_EVIDENCE_VERSION,
        "parser_git_commit": parser_git_commit,
        "period_inventory_hash": period_inventory_hash,
        "evidence_profile_hash": evidence_profile_hash,
        "supplied_link_evidence_hash": evidence_inventory_hash,
        "source_inventory_hash": source_inventory_hash,
        "filing_count": len(corpus.filings),
        "amendment_count": amendment_count,
        "lineage_count": len(lineages),
        "transaction_count": total_transactions,
        "parsed_corpus_hash": parsed_corpus_hash,
        "declared_period_set_contiguous": True,
        "official_amendment_link_verified": False,
        "complete_amendment_coverage_verified": False,
        "canonical_filter_authorized": False,
    }
    identity_hash = hash_payload(identity_payload)
    start = period_identities[0]
    end = period_identities[-1]
    identity = Form4MultiPeriodEvidenceIdentity(
        contract_version=FORM4_MULTI_PERIOD_EVIDENCE_VERSION,
        parser_git_commit=parser_git_commit,
        period_inventory=period_identities,
        period_inventory_hash=period_inventory_hash,
        evidence_profile=evidence_profile,
        evidence_profile_hash=evidence_profile_hash,
        supplied_link_evidence=evidence_inventory,
        supplied_link_evidence_hash=evidence_inventory_hash,
        source_inventory=source_inventory,
        source_inventory_hash=source_inventory_hash,
        filing_count=len(corpus.filings),
        amendment_count=amendment_count,
        lineage_count=len(lineages),
        transaction_count=total_transactions,
        parsed_corpus_hash=parsed_corpus_hash,
        declared_period_set_contiguous=True,
        official_amendment_link_verified=False,
        complete_amendment_coverage_verified=False,
        canonical_filter_authorized=False,
        evidence_id=(
            f"form4-multi-period-evidence-{start.year:04d}q{start.quarter}-"
            f"{end.year:04d}q{end.quarter}-{identity_hash[:16]}"
        ),
        _verified_factory_token=_VERIFIED_IDENTITY_FACTORY_TOKEN,
    )
    return ProfileBoundForm4AmendmentEvidence(
        identity=identity,
        xml_sources=canonical_sources,
        supplied_link_evidence=evidence_inventory,
        as_filed_corpus=corpus,
        lineages=lineages,
        _verified_factory_token=_VERIFIED_RESULT_FACTORY_TOKEN,
    )


__all__ = [
    "FORM4_MULTI_PERIOD_EVIDENCE_VERSION",
    "Form4MultiPeriodEvidenceError",
    "Form4MultiPeriodEvidenceIdentity",
    "MAX_FORM4_EVIDENCE_METADATA_BYTES",
    "MAX_FORM4_EVIDENCE_PERIODS",
    "MAX_FORM4_EVIDENCE_RECORDS",
    "MAX_FORM4_EVIDENCE_XML_BYTES",
    "MAX_FORM4_EVIDENCE_XML_SOURCES",
    "ProfileBoundForm4AmendmentEvidence",
    "SecEdgarAcceptancePeriodIdentity",
    "SecEdgarAcceptancePeriodInput",
    "SecForm4AmendmentEvidenceProfile",
    "SuppliedForm4AmendmentLinkEvidence",
    "assemble_sec_form4_multi_period_evidence",
]
