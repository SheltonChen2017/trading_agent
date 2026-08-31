"""Offline Form 4/A chronology over a bounded, verified IB-1C sample.

This IB-1D layer composes caller-supplied XML byte images with a publicly
loaded, raw-bound IB-1C acceptance snapshot.  It performs no discovery,
network access, normalized-row merge, outcome join, or publication.  Every
source must bind to exact acceptance evidence for the same accession, form,
primary-document URL, and issuer CIK before the existing Form 4 parser is
called.

The result retains a sample-relative, half-open observation chronology.  A
supplied original is observed from its exact acceptance instant until the next
supplied Form 4/A acceptance.  At that boundary the supplied lineage becomes
quarantined: later amendment versions remain retained and ordered, but no
amended row is activated or inferred.  An absent interval end means only that
the caller supplied no later version; it never proves that the filing remained
canonical.

The amendment target, source URL, retrieval instant, and Git commits remain
caller assertions checked for syntax and internal consistency.  This module
does not authenticate transport, prove that the supplied sample contains every
amendment, or infer an original accession from XML.  Its observation queries
are therefore scoped to the supplied sample.  The returned identity explicitly
records that coverage is incomplete and canonical filtering is unauthorized.
"""
from __future__ import annotations

import re
from dataclasses import InitVar, dataclass, field, fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path

from data.hashing import hash_bytes, hash_payload
from research.insider_buying.contracts import (
    ClassificationOutcome,
    ContractError,
    FilingCorpus,
    ParsedFiling,
    build_filing_corpus,
)
from research.insider_buying.form4_xml import MAX_XML_BYTES, parse_form4_xml
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    SecEdgarAcceptanceSnapshotError,
    SecEdgarAvailabilityTier,
    load_sec_edgar_acceptance_snapshot,
)


FORM4_AMENDMENT_RECONCILIATION_VERSION = (
    "INSETF-IB1D-FORM4-AMENDMENT-RECONCILIATION-v1"
)
MAX_FORM4_XML_SOURCES = 64
MAX_TOTAL_FORM4_XML_BYTES = 64 * 1024 * 1024
MAX_PRIMARY_DOCUMENT_URL_CHARACTERS = 8 * 1024
MAX_REPORTING_OWNERS_PER_FILING = 256
MAX_FOOTNOTES_PER_FILING = 4_096
MAX_TRANSACTIONS_PER_FILING = 10_000
MAX_TOTAL_REPORTING_OWNERS = 4_096
MAX_TOTAL_FOOTNOTES = 65_536
MAX_TOTAL_TRANSACTIONS = 100_000

_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ACCEPTANCE_SNAPSHOT_ID_RE = re.compile(
    r"^sec-edgar-acceptance-(?P<year>[0-9]{4})q(?P<quarter>[1-4])-"
    r"(?P<hash_prefix>[0-9a-f]{16})$"
)
_RECONCILIATION_ID_RE = re.compile(
    r"^form4-amendment-reconciliation-(?P<year>[0-9]{4})q"
    r"(?P<quarter>[1-4])-(?P<hash_prefix>[0-9a-f]{16})$"
)
_VERIFIED_RECONCILIATION_FACTORY_TOKEN = object()


class Form4AmendmentReconciliationError(ContractError):
    """The bounded Form 4/A point-in-time contract failed closed."""


def _canonical_utc(value: datetime, *, label: str) -> datetime:
    if type(value) is not datetime:
        raise Form4AmendmentReconciliationError(
            f"REFUSED: {label} must be a timezone-aware datetime"
        )
    try:
        offset = value.utcoffset()
        result = value.astimezone(timezone.utc)
    except (OverflowError, TypeError, ValueError) as exc:
        raise Form4AmendmentReconciliationError(
            f"REFUSED: {label} cannot be represented in UTC"
        ) from exc
    if offset is None or value.microsecond != 0:
        raise Form4AmendmentReconciliationError(
            f"REFUSED: {label} must be offset-aware and second-resolution"
        )
    return result


def _contract_payload(value: object) -> object:
    """Return a deterministic JSON-safe projection of frozen parser state."""

    if isinstance(value, Enum):
        return value.value
    if type(value) is datetime:
        return value.isoformat(timespec="seconds")
    if type(value) is date:
        return value.isoformat()
    if type(value) is Decimal:
        return str(value)
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is tuple:
        return [_contract_payload(item) for item in value]
    if is_dataclass(value):
        return {
            item.name: _contract_payload(getattr(value, item.name))
            for item in fields(value)
        }
    raise Form4AmendmentReconciliationError(
        "REFUSED: parsed corpus contains unsupported state"
    )


def _parsed_corpus_hash(corpus: FilingCorpus) -> str:
    if type(corpus) is not FilingCorpus:
        raise Form4AmendmentReconciliationError(
            "REFUSED: parsed corpus type is invalid"
        )
    return hash_payload(_contract_payload(corpus))


@dataclass(frozen=True)
class SecForm4XmlSource:
    """One exact XML image plus asserted, syntax-checked capture lineage."""

    accession_number: str
    xml_bytes: bytes
    primary_document_url: str
    retrieved_at: datetime
    capture_git_commit: str
    amends_accession: str | None = None
    _retrieved_at_utc: str = field(init=False, repr=False, compare=False)
    _xml_sha256: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.accession_number, str)
            or _ACCESSION_RE.fullmatch(self.accession_number) is None
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML source accession is not canonical"
            )
        if (
            type(self.xml_bytes) is not bytes
            or not self.xml_bytes
            or len(self.xml_bytes) > MAX_XML_BYTES
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML source must be a non-empty bounded exact byte image"
            )
        if (
            not isinstance(self.primary_document_url, str)
            or not self.primary_document_url
            or self.primary_document_url != self.primary_document_url.strip()
            or len(self.primary_document_url)
            > MAX_PRIMARY_DOCUMENT_URL_CHARACTERS
            or any(character.isspace() for character in self.primary_document_url)
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML source URL must be canonical bounded text"
            )
        if (
            not isinstance(self.capture_git_commit, str)
            or _GIT_COMMIT_RE.fullmatch(self.capture_git_commit) is None
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML capture Git commit must be a full lowercase SHA-1"
            )
        if self.amends_accession is not None and (
            not isinstance(self.amends_accession, str)
            or _ACCESSION_RE.fullmatch(self.amends_accession) is None
            or self.amends_accession == self.accession_number
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: amendment target must be a different canonical accession"
            )
        retrieved_at = _canonical_utc(
            self.retrieved_at, label="XML retrieval time"
        )
        object.__setattr__(self, "retrieved_at", retrieved_at)
        object.__setattr__(
            self,
            "_retrieved_at_utc",
            retrieved_at.isoformat(timespec="seconds"),
        )
        object.__setattr__(self, "_xml_sha256", hash_bytes(self.xml_bytes))

    @property
    def retrieved_at_utc(self) -> str:
        return self._retrieved_at_utc

    @property
    def xml_sha256(self) -> str:
        return self._xml_sha256


@dataclass(frozen=True)
class SecForm4XmlSourceIdentity:
    accession_number: str
    xml_sha256: str
    xml_size_bytes: int
    primary_document_url: str
    retrieved_at_utc: str
    capture_git_commit: str
    amends_accession: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.accession_number, str)
            or _ACCESSION_RE.fullmatch(self.accession_number) is None
            or not isinstance(self.xml_sha256, str)
            or _SHA256_RE.fullmatch(self.xml_sha256) is None
            or type(self.xml_size_bytes) is not int
            or not 0 < self.xml_size_bytes <= MAX_XML_BYTES
            or not isinstance(self.primary_document_url, str)
            or not isinstance(self.retrieved_at_utc, str)
            or not isinstance(self.capture_git_commit, str)
            or _GIT_COMMIT_RE.fullmatch(self.capture_git_commit) is None
            or (
                self.amends_accession is not None
                and (
                    not isinstance(self.amends_accession, str)
                    or _ACCESSION_RE.fullmatch(self.amends_accession) is None
                    or self.amends_accession == self.accession_number
                )
            )
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML source identity is invalid"
            )
        try:
            _issuer_cik_from_verified_primary_url(
                self.primary_document_url,
                accession_number=self.accession_number,
            )
            retrieved_at = datetime.fromisoformat(self.retrieved_at_utc)
            canonical_retrieved_at = _canonical_utc(
                retrieved_at, label="XML source identity retrieval time"
            ).isoformat(timespec="seconds")
        except (Form4AmendmentReconciliationError, ValueError) as exc:
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML source identity is invalid"
            ) from exc
        if canonical_retrieved_at != self.retrieved_at_utc:
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML source identity is invalid"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "xml_sha256": self.xml_sha256,
            "xml_size_bytes": self.xml_size_bytes,
            "primary_document_url": self.primary_document_url,
            "retrieved_at_utc": self.retrieved_at_utc,
            "capture_git_commit": self.capture_git_commit,
            "amends_accession": self.amends_accession,
        }


class Form4VersionDisposition(str, Enum):
    """Observation-only state of one retained as-filed ownership version."""

    ORIGINAL_OBSERVED_IN_SUPPLIED_SAMPLE = (
        "original_observed_in_supplied_sample"
    )
    QUARANTINED_UNRESOLVED_AMENDMENT = (
        "quarantined_unresolved_amendment"
    )


@dataclass(frozen=True)
class Form4VersionInterval:
    accession_number: str
    original_accession: str
    accepted_at: datetime
    next_supplied_acceptance_at: datetime | None
    disposition: Form4VersionDisposition
    source_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.accession_number, str)
            or _ACCESSION_RE.fullmatch(self.accession_number) is None
            or not isinstance(self.original_accession, str)
            or _ACCESSION_RE.fullmatch(self.original_accession) is None
            or not isinstance(self.source_sha256, str)
            or _SHA256_RE.fullmatch(self.source_sha256) is None
            or not isinstance(self.disposition, Form4VersionDisposition)
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: amendment interval identity is invalid"
            )
        accepted_at = _canonical_utc(
            self.accepted_at, label="version acceptance time"
        )
        object.__setattr__(self, "accepted_at", accepted_at)
        if self.next_supplied_acceptance_at is not None:
            next_supplied_acceptance_at = _canonical_utc(
                self.next_supplied_acceptance_at,
                label="next supplied version acceptance time",
            )
            if next_supplied_acceptance_at <= accepted_at:
                raise Form4AmendmentReconciliationError(
                    "REFUSED: supplied version chronology must be strictly increasing"
                )
            object.__setattr__(
                self,
                "next_supplied_acceptance_at",
                next_supplied_acceptance_at,
            )
        if (
            self.disposition
            is Form4VersionDisposition.ORIGINAL_OBSERVED_IN_SUPPLIED_SAMPLE
        ) != (self.accession_number == self.original_accession):
            raise Form4AmendmentReconciliationError(
                "REFUSED: only the original filing may have original-observation state"
            )

    def contains_observed_instant(self, as_of: datetime) -> bool:
        """Return whether ``as_of`` falls in this supplied-sample interval."""

        instant = _canonical_utc(as_of, label="as-of time")
        return self.accepted_at <= instant and (
            self.next_supplied_acceptance_at is None
            or instant < self.next_supplied_acceptance_at
        )

    def observation_at(self, as_of: datetime) -> Form4ObservedState | None:
        """Return a boundary-free state view when this interval contains ``as_of``."""

        if not self.contains_observed_instant(as_of):
            return None
        return Form4ObservedState(
            accession_number=self.accession_number,
            original_accession=self.original_accession,
            accepted_at=self.accepted_at,
            disposition=self.disposition,
            source_sha256=self.source_sha256,
        )


@dataclass(frozen=True)
class Form4ObservedState:
    """As-of sample state without exposing a future supplied boundary."""

    accession_number: str
    original_accession: str
    accepted_at: datetime
    disposition: Form4VersionDisposition
    source_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.accession_number, str)
            or _ACCESSION_RE.fullmatch(self.accession_number) is None
            or not isinstance(self.original_accession, str)
            or _ACCESSION_RE.fullmatch(self.original_accession) is None
            or not isinstance(self.source_sha256, str)
            or _SHA256_RE.fullmatch(self.source_sha256) is None
            or not isinstance(self.disposition, Form4VersionDisposition)
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: observed amendment state identity is invalid"
            )
        object.__setattr__(
            self,
            "accepted_at",
            _canonical_utc(self.accepted_at, label="observed acceptance time"),
        )


@dataclass(frozen=True)
class Form4AmendmentLineage:
    original_accession: str
    versions: tuple[Form4VersionInterval, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.original_accession, str)
            or _ACCESSION_RE.fullmatch(self.original_accession) is None
            or type(self.versions) is not tuple
            or not self.versions
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: amendment lineage is invalid"
            )
        for index, version in enumerate(self.versions):
            if (
                type(version) is not Form4VersionInterval
                or version.original_accession != self.original_accession
                or (
                    index == 0
                    and version.disposition
                    is not Form4VersionDisposition.ORIGINAL_OBSERVED_IN_SUPPLIED_SAMPLE
                )
                or (
                    index > 0
                    and version.disposition
                    is not Form4VersionDisposition.QUARANTINED_UNRESOLVED_AMENDMENT
                )
            ):
                raise Form4AmendmentReconciliationError(
                    "REFUSED: amendment lineage version roles are inconsistent"
                )
            next_version = (
                self.versions[index + 1]
                if index + 1 < len(self.versions)
                else None
            )
            expected_end = (
                next_version.accepted_at if next_version is not None else None
            )
            if version.next_supplied_acceptance_at != expected_end:
                raise Form4AmendmentReconciliationError(
                    "REFUSED: supplied amendment chronology is not contiguous"
                )

    def observed_state_at(
        self, as_of: datetime
    ) -> Form4ObservedState | None:
        """Return a boundary-free sample state, never a canonical decision."""

        instant = _canonical_utc(as_of, label="as-of time")
        for version in self.versions:
            state = version.observation_at(instant)
            if state is not None:
                return state
        return None


@dataclass(frozen=True)
class Form4AmendmentReconciliationIdentity:
    contract_version: str
    parser_git_commit: str
    acceptance_snapshot_id: str
    acceptance_lineage_hash: str
    source_inventory: tuple[SecForm4XmlSourceIdentity, ...]
    source_inventory_hash: str
    filing_count: int
    amendment_count: int
    lineage_count: int
    transaction_count: int
    parsed_corpus_hash: str
    complete_amendment_coverage_verified: bool
    canonical_filter_authorized: bool
    reconciliation_id: str

    def __post_init__(self) -> None:
        if (
            self.contract_version != FORM4_AMENDMENT_RECONCILIATION_VERSION
            or not isinstance(self.parser_git_commit, str)
            or _GIT_COMMIT_RE.fullmatch(self.parser_git_commit) is None
            or not isinstance(self.acceptance_snapshot_id, str)
            or not isinstance(self.acceptance_lineage_hash, str)
            or _SHA256_RE.fullmatch(self.acceptance_lineage_hash) is None
            or type(self.source_inventory) is not tuple
            or not self.source_inventory
            or len(self.source_inventory) > MAX_FORM4_XML_SOURCES
            or not isinstance(self.source_inventory_hash, str)
            or _SHA256_RE.fullmatch(self.source_inventory_hash) is None
            or type(self.filing_count) is not int
            or self.filing_count != len(self.source_inventory)
            or type(self.amendment_count) is not int
            or not 0 <= self.amendment_count <= self.filing_count
            or type(self.lineage_count) is not int
            or not 0 < self.lineage_count <= self.filing_count
            or self.amendment_count != self.filing_count - self.lineage_count
            or type(self.transaction_count) is not int
            or not 0 <= self.transaction_count <= MAX_TOTAL_TRANSACTIONS
            or not isinstance(self.parsed_corpus_hash, str)
            or _SHA256_RE.fullmatch(self.parsed_corpus_hash) is None
            or self.complete_amendment_coverage_verified is not False
            or self.canonical_filter_authorized is not False
            or not isinstance(self.reconciliation_id, str)
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: amendment reconciliation identity is invalid and "
                "cannot authorize canonical filtering"
            )

        if any(
            type(item) is not SecForm4XmlSourceIdentity
            for item in self.source_inventory
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: amendment reconciliation source inventory is invalid"
            )
        if (
            tuple(
                sorted(
                    self.source_inventory,
                    key=lambda item: item.accession_number,
                )
            )
            != self.source_inventory
            or len(
                {item.accession_number for item in self.source_inventory}
            )
            != len(self.source_inventory)
            or hash_payload(
                [item.to_payload() for item in self.source_inventory]
            )
            != self.source_inventory_hash
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: amendment reconciliation source inventory is invalid"
            )

        acceptance_match = _ACCEPTANCE_SNAPSHOT_ID_RE.fullmatch(
            self.acceptance_snapshot_id
        )
        reconciliation_match = _RECONCILIATION_ID_RE.fullmatch(
            self.reconciliation_id
        )
        if (
            acceptance_match is None
            or acceptance_match.group("hash_prefix")
            != self.acceptance_lineage_hash[:16]
            or reconciliation_match is None
            or reconciliation_match.group("year")
            != acceptance_match.group("year")
            or reconciliation_match.group("quarter")
            != acceptance_match.group("quarter")
            or self.reconciliation_id
            != (
                "form4-amendment-reconciliation-"
                f"{acceptance_match.group('year')}q"
                f"{acceptance_match.group('quarter')}-"
                f"{hash_payload(self.lineage_payload())[:16]}"
            )
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: amendment reconciliation identity is invalid"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "parser_git_commit": self.parser_git_commit,
            "acceptance_snapshot_id": self.acceptance_snapshot_id,
            "acceptance_lineage_hash": self.acceptance_lineage_hash,
            "source_inventory_hash": self.source_inventory_hash,
            "filing_count": self.filing_count,
            "amendment_count": self.amendment_count,
            "lineage_count": self.lineage_count,
            "transaction_count": self.transaction_count,
            "parsed_corpus_hash": self.parsed_corpus_hash,
            "complete_amendment_coverage_verified": (
                self.complete_amendment_coverage_verified
            ),
            "canonical_filter_authorized": self.canonical_filter_authorized,
        }

    def to_payload(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "parser_git_commit": self.parser_git_commit,
            "acceptance_snapshot_id": self.acceptance_snapshot_id,
            "acceptance_lineage_hash": self.acceptance_lineage_hash,
            "source_inventory": [
                item.to_payload() for item in self.source_inventory
            ],
            "source_inventory_hash": self.source_inventory_hash,
            "filing_count": self.filing_count,
            "amendment_count": self.amendment_count,
            "lineage_count": self.lineage_count,
            "transaction_count": self.transaction_count,
            "parsed_corpus_hash": self.parsed_corpus_hash,
            "complete_amendment_coverage_verified": (
                self.complete_amendment_coverage_verified
            ),
            "canonical_filter_authorized": self.canonical_filter_authorized,
            "reconciliation_id": self.reconciliation_id,
        }


@dataclass(frozen=True)
class ReconciledForm4Amendments:
    """Bounded audit chronology with permanently disabled filter authority.

    ``as_filed_corpus`` retains parser classifications from the exact supplied
    XML bytes.  Its ``amends_accession`` and ``superseded_by`` edges incorporate
    caller-asserted lineage metadata; they are not authenticated from the XML.
    A transaction's provisional parser eligibility therefore cannot be treated
    as canonical amendment resolution.
    """

    identity: Form4AmendmentReconciliationIdentity
    as_filed_corpus: FilingCorpus
    lineages: tuple[Form4AmendmentLineage, ...]
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _VERIFIED_RECONCILIATION_FACTORY_TOKEN:
            raise Form4AmendmentReconciliationError(
                "REFUSED: reconciliation result boundary must be factory-created"
            )
        if (
            type(self.identity) is not Form4AmendmentReconciliationIdentity
            or type(self.as_filed_corpus) is not FilingCorpus
            or type(self.lineages) is not tuple
            or any(type(lineage) is not Form4AmendmentLineage for lineage in self.lineages)
            or self.identity.complete_amendment_coverage_verified is not False
            or self.identity.canonical_filter_authorized is not False
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: reconciliation result boundary is invalid"
            )
        try:
            rebuilt_corpus = build_filing_corpus(
                list(self.as_filed_corpus.filings)
            )
            rebuilt_lineages = _build_lineages(self.as_filed_corpus)
        except (AttributeError, ContractError, TypeError, ValueError) as exc:
            raise Form4AmendmentReconciliationError(
                "REFUSED: reconciliation result cannot be rebuilt"
            ) from exc
        if (
            rebuilt_corpus != self.as_filed_corpus
            or rebuilt_lineages != self.lineages
            or self.identity.filing_count
            != len(self.as_filed_corpus.filings)
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
            raise Form4AmendmentReconciliationError(
                "REFUSED: reconciliation parsed corpus disagrees with its identity"
            )
        inventory_by_accession = {
            item.accession_number: item
            for item in self.identity.source_inventory
        }
        if (
            len(inventory_by_accession) != len(self.identity.source_inventory)
            or set(inventory_by_accession)
            != {
                filing.envelope.accession_number
                for filing in self.as_filed_corpus.filings
            }
            or any(
                inventory_by_accession[
                    filing.envelope.accession_number
                ].xml_sha256
                != filing.envelope.source_sha256
                or inventory_by_accession[
                    filing.envelope.accession_number
                ].primary_document_url
                != filing.envelope.source_name
                or inventory_by_accession[
                    filing.envelope.accession_number
                ].amends_accession
                != filing.envelope.amends_accession
                for filing in self.as_filed_corpus.filings
            )
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: reconciliation sources disagree with parsed filings"
            )

    def lineage(self, original_accession: str) -> Form4AmendmentLineage:
        for lineage in self.lineages:
            if lineage.original_accession == original_accession:
                return lineage
        raise KeyError(original_accession)

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


def _build_verified_reconciliation_result(
    *,
    identity: Form4AmendmentReconciliationIdentity,
    as_filed_corpus: FilingCorpus,
    lineages: tuple[Form4AmendmentLineage, ...],
) -> ReconciledForm4Amendments:
    """Create a result only from the module's verified parsing path."""

    return ReconciledForm4Amendments(
        identity=identity,
        as_filed_corpus=as_filed_corpus,
        lineages=lineages,
        _verified_factory_token=_VERIFIED_RECONCILIATION_FACTORY_TOKEN,
    )


def _source_identity(source: SecForm4XmlSource) -> SecForm4XmlSourceIdentity:
    return SecForm4XmlSourceIdentity(
        accession_number=source.accession_number,
        xml_sha256=source.xml_sha256,
        xml_size_bytes=len(source.xml_bytes),
        primary_document_url=source.primary_document_url,
        retrieved_at_utc=source.retrieved_at_utc,
        capture_git_commit=source.capture_git_commit,
        amends_accession=source.amends_accession,
    )


def _issuer_cik_from_verified_primary_url(
    primary_document_url: str, *, accession_number: str
) -> str:
    segments = primary_document_url.split("/")
    if (
        len(segments) != 9
        or segments[:6]
        != ["https:", "", "www.sec.gov", "Archives", "edgar", "data"]
        or not segments[6].isdigit()
        or segments[7] != accession_number.replace("-", "")
        or not segments[8]
    ):
        raise Form4AmendmentReconciliationError(
            "REFUSED: verified primary-document URL is not accession-addressed"
        )
    return segments[6].zfill(10)


def _build_lineages(corpus: FilingCorpus) -> tuple[Form4AmendmentLineage, ...]:
    originals = {
        filing.envelope.accession_number: filing
        for filing in corpus.filings
        if filing.envelope.amends_accession is None
    }
    amendments: dict[str, list[ParsedFiling]] = {
        accession: [] for accession in originals
    }
    for filing in corpus.filings:
        target = filing.envelope.amends_accession
        if target is not None:
            amendments.setdefault(target, []).append(filing)

    lineages: list[Form4AmendmentLineage] = []
    for original_accession, original in sorted(originals.items()):
        original_time = original.envelope.availability.accepted_at
        if original_time is None:
            raise Form4AmendmentReconciliationError(
                "REFUSED: reconciled Form 4 sources require exact acceptance times"
            )
        ordered_amendments = sorted(
            amendments.get(original_accession, ()),
            key=lambda filing: filing.envelope.availability.accepted_at,
        )
        version_filings = [original, *ordered_amendments]
        version_times: list[datetime] = []
        for filing in version_filings:
            accepted_at = filing.envelope.availability.accepted_at
            if accepted_at is None:
                raise Form4AmendmentReconciliationError(
                    "REFUSED: an amended lineage requires exact acceptance times"
                )
            version_times.append(
                _canonical_utc(accepted_at, label="filing acceptance time")
            )
        if len(set(version_times)) != len(version_times):
            raise Form4AmendmentReconciliationError(
                "REFUSED: amendment acceptance order is ambiguous"
            )

        intervals = tuple(
            Form4VersionInterval(
                accession_number=filing.envelope.accession_number,
                original_accession=original_accession,
                accepted_at=version_times[index],
                next_supplied_acceptance_at=(
                    version_times[index + 1]
                    if index + 1 < len(version_times)
                    else None
                ),
                disposition=(
                    Form4VersionDisposition.ORIGINAL_OBSERVED_IN_SUPPLIED_SAMPLE
                    if index == 0
                    else Form4VersionDisposition.QUARANTINED_UNRESOLVED_AMENDMENT
                ),
                source_sha256=filing.envelope.source_sha256,
            )
            for index, filing in enumerate(version_filings)
        )
        lineages.append(
            Form4AmendmentLineage(
                original_accession=original_accession,
                versions=intervals,
            )
        )
    return tuple(lineages)


def reconcile_sec_form4_amendments(
    acceptance_snapshot_path: str | Path,
    *,
    parsed_snapshot_directory: str | Path,
    raw_snapshot_directory: str | Path,
    sources: tuple[SecForm4XmlSource, ...],
    parser_git_commit: str,
) -> ReconciledForm4Amendments:
    """Reconcile one bounded exact-timestamp Form 4/4-A XML sample."""

    if (
        not isinstance(parser_git_commit, str)
        or _GIT_COMMIT_RE.fullmatch(parser_git_commit) is None
    ):
        raise Form4AmendmentReconciliationError(
            "REFUSED: parser Git commit must be a full lowercase SHA-1"
        )
    if (
        type(sources) is not tuple
        or not sources
        or len(sources) > MAX_FORM4_XML_SOURCES
        or any(type(source) is not SecForm4XmlSource for source in sources)
        or sum(len(source.xml_bytes) for source in sources)
        > MAX_TOTAL_FORM4_XML_BYTES
    ):
        raise Form4AmendmentReconciliationError(
            "REFUSED: XML sources must be a non-empty bounded immutable tuple"
        )
    try:
        loaded = load_sec_edgar_acceptance_snapshot(
            acceptance_snapshot_path,
            parsed_snapshot_directory=parsed_snapshot_directory,
            raw_snapshot_directory=raw_snapshot_directory,
        )
    except SecEdgarAcceptanceSnapshotError as exc:
        raise Form4AmendmentReconciliationError(
            "REFUSED: acceptance snapshot is not a verified IB-1C boundary"
        ) from exc

    records_by_accession = {
        record.accession_number: record for record in loaded.records
    }
    if len(records_by_accession) != len(loaded.records):
        raise Form4AmendmentReconciliationError(
            "REFUSED: acceptance records are not unique"
        )

    filings: list[ParsedFiling] = []
    source_identities: list[SecForm4XmlSourceIdentity] = []
    seen_accessions: set[str] = set()
    total_reporting_owners = 0
    total_footnotes = 0
    total_transactions = 0
    for source in sorted(sources, key=lambda item: item.accession_number):
        if source.accession_number in seen_accessions:
            raise Form4AmendmentReconciliationError(
                f"REFUSED: duplicate XML accession {source.accession_number}"
            )
        seen_accessions.add(source.accession_number)
        record = records_by_accession.get(source.accession_number)
        if record is None:
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML source accession is absent from acceptance evidence"
            )
        if record.document_type not in {"4", "4/A"}:
            raise Form4AmendmentReconciliationError(
                "REFUSED: amendment reconciliation accepts only Form 4/4-A"
            )
        if (
            record.availability_tier
            is not SecEdgarAvailabilityTier.EXACT_ACCEPTANCE_TIMESTAMP
            or record.accepted_at is None
            or record.primary_document_url is None
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: reconciled XML requires exact acceptance evidence"
            )
        if source.primary_document_url != record.primary_document_url:
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML source URL disagrees with acceptance evidence"
            )
        if source.retrieved_at < record.accepted_at:
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML retrieval time precedes public acceptance"
            )
        try:
            filing = parse_form4_xml(
                source.xml_bytes,
                accession_number=source.accession_number,
                acceptance=record.accepted_at,
                source_name=source.primary_document_url,
                amends_accession=source.amends_accession,
            )
        except ContractError as exc:
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML source violates the pinned Form 4 contract"
            ) from exc
        if filing.envelope.form_type != record.document_type:
            raise Form4AmendmentReconciliationError(
                "REFUSED: XML form type disagrees with acceptance evidence"
            )
        if record.document_type == "4/A" and any(
            transaction.outcomes
            != (ClassificationOutcome.EXCLUDE_AMENDED_FILING,)
            for transaction in filing.transactions
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: Form 4/A rows must remain explicitly excluded"
            )
        expected_issuer_cik = _issuer_cik_from_verified_primary_url(
            record.primary_document_url,
            accession_number=record.accession_number,
        )
        if filing.envelope.issuer_cik != expected_issuer_cik:
            raise Form4AmendmentReconciliationError(
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
            raise Form4AmendmentReconciliationError(
                "REFUSED: parsed Form 4 filing exceeds a per-filing resource cap"
            )
        total_reporting_owners += reporting_owner_count
        total_footnotes += footnote_count
        total_transactions += transaction_count
        if (
            total_reporting_owners > MAX_TOTAL_REPORTING_OWNERS
            or total_footnotes > MAX_TOTAL_FOOTNOTES
            or total_transactions > MAX_TOTAL_TRANSACTIONS
        ):
            raise Form4AmendmentReconciliationError(
                "REFUSED: parsed Form 4 sample exceeds an aggregate resource cap"
            )
        filings.append(filing)
        source_identities.append(_source_identity(source))

    try:
        corpus = build_filing_corpus(filings)
    except ContractError as exc:
        raise Form4AmendmentReconciliationError(
            "REFUSED: Form 4/A accession lineage is invalid"
        ) from exc
    lineages = _build_lineages(corpus)
    if sum(len(lineage.versions) for lineage in lineages) != len(corpus.filings):
        raise Form4AmendmentReconciliationError(
            "REFUSED: not every filing belongs to one amendment lineage"
        )
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
    corpus_accessions = {
        filing.envelope.accession_number for filing in corpus.filings
    }
    lineage_accessions = [
        version.accession_number
        for lineage in lineages
        for version in lineage.versions
    ]
    if (
        corpus_edges != lineage_edges
        or len(lineage_accessions) != len(set(lineage_accessions))
        or set(lineage_accessions) != corpus_accessions
    ):
        raise Form4AmendmentReconciliationError(
            "REFUSED: corpus and observed amendment lineage disagree"
        )

    source_inventory = tuple(source_identities)
    source_inventory_hash = hash_payload(
        [item.to_payload() for item in source_inventory]
    )
    amendment_count = sum(
        len(lineage.versions) - 1 for lineage in lineages
    )
    parsed_corpus_hash = _parsed_corpus_hash(corpus)
    identity_payload = {
        "contract_version": FORM4_AMENDMENT_RECONCILIATION_VERSION,
        "parser_git_commit": parser_git_commit,
        "acceptance_snapshot_id": loaded.identity.snapshot_id,
        "acceptance_lineage_hash": loaded.identity.lineage_hash,
        "source_inventory_hash": source_inventory_hash,
        "filing_count": len(corpus.filings),
        "amendment_count": amendment_count,
        "lineage_count": len(lineages),
        "transaction_count": total_transactions,
        "parsed_corpus_hash": parsed_corpus_hash,
        "complete_amendment_coverage_verified": False,
        "canonical_filter_authorized": False,
    }
    reconciliation_hash = hash_payload(identity_payload)
    identity = Form4AmendmentReconciliationIdentity(
        contract_version=FORM4_AMENDMENT_RECONCILIATION_VERSION,
        parser_git_commit=parser_git_commit,
        acceptance_snapshot_id=loaded.identity.snapshot_id,
        acceptance_lineage_hash=loaded.identity.lineage_hash,
        source_inventory=source_inventory,
        source_inventory_hash=source_inventory_hash,
        filing_count=len(corpus.filings),
        amendment_count=amendment_count,
        lineage_count=len(lineages),
        transaction_count=total_transactions,
        parsed_corpus_hash=parsed_corpus_hash,
        complete_amendment_coverage_verified=False,
        canonical_filter_authorized=False,
        reconciliation_id=(
            f"form4-amendment-reconciliation-{loaded.identity.year:04d}"
            f"q{loaded.identity.quarter}-{reconciliation_hash[:16]}"
        ),
    )
    return _build_verified_reconciliation_result(
        identity=identity,
        as_filed_corpus=corpus,
        lineages=lineages,
    )


__all__ = [
    "FORM4_AMENDMENT_RECONCILIATION_VERSION",
    "Form4AmendmentLineage",
    "Form4AmendmentReconciliationError",
    "Form4AmendmentReconciliationIdentity",
    "Form4ObservedState",
    "Form4VersionDisposition",
    "Form4VersionInterval",
    "MAX_FORM4_XML_SOURCES",
    "MAX_FOOTNOTES_PER_FILING",
    "MAX_REPORTING_OWNERS_PER_FILING",
    "MAX_TOTAL_FOOTNOTES",
    "MAX_TOTAL_REPORTING_OWNERS",
    "MAX_TOTAL_FORM4_XML_BYTES",
    "MAX_TOTAL_TRANSACTIONS",
    "MAX_TRANSACTIONS_PER_FILING",
    "ReconciledForm4Amendments",
    "SecForm4XmlSource",
    "SecForm4XmlSourceIdentity",
    "reconcile_sec_form4_amendments",
]
