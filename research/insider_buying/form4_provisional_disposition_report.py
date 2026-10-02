"""Evidence-bound provisional Form 4 disposition and quarantine report.

IB-1G consumes only the factory-created IB-1E supplied-link evidence result.
It reparses every exact XML byte image and compares the rebuilt corpus before
reporting one deterministic row for every supplied transaction.  A row whose
only parser outcome is ``ELIGIBLE_FOR_LOT_AGGREGATION`` is labelled only as a
provisional pre-aggregation candidate.  Every other row is retained in the
quarantine inventory with all parser reason codes.

This is an offline audit artifact, not a canonical filter.  It performs no
download, discovery, publication, security mapping, lot aggregation, minimum-
value gate, signal construction, outcome access, portfolio work, or execution.
Official-profile, official-amendment-link, amendment-completeness, point-in-
time security, canonical-filter, aggregation, and outcome authority remain
literal false values.
"""
from __future__ import annotations

import re
from dataclasses import InitVar, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from data.hashing import hash_payload
from research.insider_buying.contracts import (
    ClassificationOutcome,
    ContractError,
    FilingCorpus,
    ParsedFiling,
    ParsedTransaction,
    TransactionDiagnostic,
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
    SecForm4XmlSource,
    SecForm4XmlSourceIdentity,
    _build_lineages,
    _parsed_corpus_hash,
    _source_identity,
)
from research.insider_buying import (
    form4_multi_period_amendment_evidence as evidence_module,
)
from research.insider_buying.form4_multi_period_amendment_evidence import (
    MAX_FORM4_EVIDENCE_PERIODS,
    MAX_FORM4_EVIDENCE_XML_BYTES,
    MAX_FORM4_EVIDENCE_XML_SOURCES,
    Form4MultiPeriodEvidenceIdentity,
    ProfileBoundForm4AmendmentEvidence,
    SecEdgarAcceptancePeriodIdentity,
    SecForm4AmendmentEvidenceProfile,
    SuppliedForm4AmendmentLinkEvidence,
)
from research.insider_buying.form4_xml import MAX_XML_BYTES, parse_form4_xml


FORM4_PROVISIONAL_DISPOSITION_REPORT_VERSION = (
    "INSETF-IB1G-FORM4-PROVISIONAL-DISPOSITION-REPORT-v1"
)

_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REPORT_ID_RE = re.compile(
    r"^form4-provisional-disposition-report-(?P<hash_prefix>[0-9a-f]{16})$"
)
_VERIFIED_IDENTITY_FACTORY_TOKEN = object()
_VERIFIED_REPORT_FACTORY_TOKEN = object()


class Form4ProvisionalDispositionReportError(ContractError):
    """The bounded IB-1G disposition-report contract failed closed."""


class Form4ProvisionalDisposition(str, Enum):
    """Non-authoritative routing label for one as-filed transaction."""

    PROVISIONAL_PRE_AGGREGATION_CANDIDATE = (
        "provisional_pre_aggregation_candidate"
    )
    PROVISIONAL_QUARANTINE = "provisional_quarantine"


def _decimal_payload(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: transaction decimal state is invalid"
        )
    return str(value)


def _transaction_payload(transaction: ParsedTransaction) -> dict[str, object]:
    """Project every parser field into a deterministic JSON-safe payload."""

    if type(transaction) is not ParsedTransaction:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: transaction must be exact parser output"
        )
    if (
        type(transaction.event_id) is not str
        or _SHA256_RE.fullmatch(transaction.event_id) is None
        or type(transaction.accession_number) is not str
        or _ACCESSION_RE.fullmatch(transaction.accession_number) is None
        or type(transaction.source_sha256) is not str
        or _SHA256_RE.fullmatch(transaction.source_sha256) is None
        or type(transaction.row_index) is not int
        or transaction.row_index < 0
        or type(transaction.derivative) is not bool
        or (
            transaction.transaction_date is not None
            and type(transaction.transaction_date) is not date
        )
        or type(transaction.footnote_ids) is not tuple
        or any(type(item) is not str or not item for item in transaction.footnote_ids)
        or type(transaction.footnote_texts) is not tuple
        or any(type(item) is not str or not item for item in transaction.footnote_texts)
        or type(transaction.outcomes) is not tuple
        or not transaction.outcomes
        or any(type(item) is not ClassificationOutcome for item in transaction.outcomes)
        or len(set(transaction.outcomes)) != len(transaction.outcomes)
        or type(transaction.diagnostics) is not tuple
        or any(type(item) is not TransactionDiagnostic for item in transaction.diagnostics)
        or len(set(transaction.diagnostics)) != len(transaction.diagnostics)
    ):
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: transaction parser state is invalid"
        )
    for value in (
        transaction.security_title_raw,
        transaction.transaction_code,
        transaction.acquired_disposed_code,
        transaction.direct_indirect,
    ):
        if value is not None and (type(value) is not str or not value):
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: transaction text state is invalid"
            )
    if transaction.aff10b5_one is not None and type(transaction.aff10b5_one) is not bool:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: transaction 10b5-1 state is invalid"
        )
    if (
        ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION
        in transaction.outcomes
        and transaction.outcomes
        != (ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,)
    ):
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: eligible outcome cannot coexist with quarantine reasons"
        )

    return {
        "event_id": transaction.event_id,
        "accession_number": transaction.accession_number,
        "source_sha256": transaction.source_sha256,
        "row_index": transaction.row_index,
        "derivative": transaction.derivative,
        "security_title_raw": transaction.security_title_raw,
        "transaction_date": (
            None
            if transaction.transaction_date is None
            else transaction.transaction_date.isoformat()
        ),
        "transaction_code": transaction.transaction_code,
        "acquired_disposed_code": transaction.acquired_disposed_code,
        "shares": _decimal_payload(transaction.shares),
        "price_per_share": _decimal_payload(transaction.price_per_share),
        "purchase_value_usd": _decimal_payload(transaction.purchase_value_usd),
        "shares_owned_after": _decimal_payload(transaction.shares_owned_after),
        "direct_indirect": transaction.direct_indirect,
        "aff10b5_one": transaction.aff10b5_one,
        "footnote_ids": list(transaction.footnote_ids),
        "footnote_texts": list(transaction.footnote_texts),
        "outcomes": [item.value for item in transaction.outcomes],
        "diagnostics": [item.value for item in transaction.diagnostics],
    }


@dataclass(frozen=True)
class Form4ProvisionalDispositionRow:
    """One immutable reason-coded row in the provisional report."""

    accession_number: str
    source_sha256: str
    row_index: int
    event_id: str
    derivative: bool
    security_title_raw: str | None
    transaction_date: date | None
    transaction_code: str | None
    acquired_disposed_code: str | None
    shares: Decimal | None
    price_per_share: Decimal | None
    purchase_value_usd: Decimal | None
    direct_indirect: str | None
    footnote_ids: tuple[str, ...]
    outcomes: tuple[ClassificationOutcome, ...]
    diagnostics: tuple[TransactionDiagnostic, ...]
    transaction_payload_hash: str
    disposition: Form4ProvisionalDisposition
    row_id: str

    def __post_init__(self) -> None:
        if (
            type(self.accession_number) is not str
            or _ACCESSION_RE.fullmatch(self.accession_number) is None
            or type(self.source_sha256) is not str
            or _SHA256_RE.fullmatch(self.source_sha256) is None
            or type(self.row_index) is not int
            or self.row_index < 0
            or type(self.event_id) is not str
            or _SHA256_RE.fullmatch(self.event_id) is None
            or type(self.derivative) is not bool
            or (
                self.security_title_raw is not None
                and (
                    type(self.security_title_raw) is not str
                    or not self.security_title_raw
                )
            )
            or (
                self.transaction_date is not None
                and type(self.transaction_date) is not date
            )
            or any(
                value is not None and (type(value) is not str or not value)
                for value in (
                    self.transaction_code,
                    self.acquired_disposed_code,
                    self.direct_indirect,
                )
            )
            or type(self.footnote_ids) is not tuple
            or any(type(item) is not str or not item for item in self.footnote_ids)
            or tuple(sorted(set(self.footnote_ids))) != self.footnote_ids
            or type(self.outcomes) is not tuple
            or not self.outcomes
            or any(type(item) is not ClassificationOutcome for item in self.outcomes)
            or len(set(self.outcomes)) != len(self.outcomes)
            or type(self.diagnostics) is not tuple
            or any(type(item) is not TransactionDiagnostic for item in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
            or type(self.transaction_payload_hash) is not str
            or _SHA256_RE.fullmatch(self.transaction_payload_hash) is None
            or type(self.disposition) is not Form4ProvisionalDisposition
            or type(self.row_id) is not str
            or _SHA256_RE.fullmatch(self.row_id) is None
        ):
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: provisional disposition row is invalid"
            )
        for value in (self.shares, self.price_per_share, self.purchase_value_usd):
            _decimal_payload(value)
        eligible = (
            self.outcomes
            == (ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,)
        )
        expected = (
            Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
            if eligible
            else Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE
        )
        if (
            ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION in self.outcomes
            and not eligible
        ) or self.disposition is not expected:
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: provisional disposition contradicts parser outcomes"
            )
        if self.row_id != hash_payload(self.lineage_payload()):
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: provisional disposition row ID is invalid"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "source_sha256": self.source_sha256,
            "row_index": self.row_index,
            "event_id": self.event_id,
            "derivative": self.derivative,
            "security_title_raw": self.security_title_raw,
            "transaction_date": (
                None
                if self.transaction_date is None
                else self.transaction_date.isoformat()
            ),
            "transaction_code": self.transaction_code,
            "acquired_disposed_code": self.acquired_disposed_code,
            "shares": _decimal_payload(self.shares),
            "price_per_share": _decimal_payload(self.price_per_share),
            "purchase_value_usd": _decimal_payload(self.purchase_value_usd),
            "direct_indirect": self.direct_indirect,
            "footnote_ids": list(self.footnote_ids),
            "outcomes": [item.value for item in self.outcomes],
            "diagnostics": [item.value for item in self.diagnostics],
            "transaction_payload_hash": self.transaction_payload_hash,
            "disposition": self.disposition.value,
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.lineage_payload(), "row_id": self.row_id}


@dataclass(frozen=True)
class Form4ProvisionalDispositionReportIdentity:
    contract_version: str
    builder_git_commit: str
    upstream_evidence_id: str
    upstream_evidence_identity_hash: str
    upstream_parsed_corpus_hash: str
    upstream_source_inventory_hash: str
    row_inventory_hash: str
    transaction_count: int
    candidate_count: int
    quarantine_count: int
    official_profile_compatibility_verified: bool
    official_amendment_link_verified: bool
    complete_amendment_coverage_verified: bool
    point_in_time_security_identity_verified: bool
    canonical_filter_authorized: bool
    lot_aggregation_authorized: bool
    outcomes_authorized: bool
    authorized_outcome_looks: int
    report_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if (
            self.contract_version
            != FORM4_PROVISIONAL_DISPOSITION_REPORT_VERSION
            or type(self.builder_git_commit) is not str
            or _GIT_COMMIT_RE.fullmatch(self.builder_git_commit) is None
            or type(self.upstream_evidence_id) is not str
            or not self.upstream_evidence_id
            or any(
                type(value) is not str or _SHA256_RE.fullmatch(value) is None
                for value in (
                    self.upstream_evidence_identity_hash,
                    self.upstream_parsed_corpus_hash,
                    self.upstream_source_inventory_hash,
                    self.row_inventory_hash,
                )
            )
            or type(self.transaction_count) is not int
            or not 0 <= self.transaction_count <= MAX_TOTAL_TRANSACTIONS
            or type(self.candidate_count) is not int
            or self.candidate_count < 0
            or type(self.quarantine_count) is not int
            or self.quarantine_count < 0
            or self.candidate_count + self.quarantine_count
            != self.transaction_count
            or self.official_profile_compatibility_verified is not False
            or self.official_amendment_link_verified is not False
            or self.complete_amendment_coverage_verified is not False
            or self.point_in_time_security_identity_verified is not False
            or self.canonical_filter_authorized is not False
            or self.lot_aggregation_authorized is not False
            or self.outcomes_authorized is not False
            or type(self.authorized_outcome_looks) is not int
            or self.authorized_outcome_looks != 0
        ):
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: report identity is invalid or claims authority"
            )
        match = (
            _REPORT_ID_RE.fullmatch(self.report_id)
            if type(self.report_id) is str
            else None
        )
        if (
            match is None
            or match.group("hash_prefix")
            != hash_payload(self.lineage_payload())[:16]
        ):
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: report identity ID is invalid"
            )
        if _verified_factory_token is not _VERIFIED_IDENTITY_FACTORY_TOKEN:
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: report identity must be factory-created"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "builder_git_commit": self.builder_git_commit,
            "upstream_evidence_id": self.upstream_evidence_id,
            "upstream_evidence_identity_hash": (
                self.upstream_evidence_identity_hash
            ),
            "upstream_parsed_corpus_hash": self.upstream_parsed_corpus_hash,
            "upstream_source_inventory_hash": (
                self.upstream_source_inventory_hash
            ),
            "row_inventory_hash": self.row_inventory_hash,
            "transaction_count": self.transaction_count,
            "candidate_count": self.candidate_count,
            "quarantine_count": self.quarantine_count,
            "official_profile_compatibility_verified": False,
            "official_amendment_link_verified": False,
            "complete_amendment_coverage_verified": False,
            "point_in_time_security_identity_verified": False,
            "canonical_filter_authorized": False,
            "lot_aggregation_authorized": False,
            "outcomes_authorized": False,
            "authorized_outcome_looks": 0,
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.lineage_payload(), "report_id": self.report_id}


@dataclass(frozen=True)
class Form4ProvisionalDispositionReport:
    """Complete one-row-per-transaction provisional audit artifact."""

    identity: Form4ProvisionalDispositionReportIdentity
    rows: tuple[Form4ProvisionalDispositionRow, ...]
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _VERIFIED_REPORT_FACTORY_TOKEN:
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: disposition report must be factory-created"
            )
        if (
            type(self.identity) is not Form4ProvisionalDispositionReportIdentity
            or type(self.rows) is not tuple
            or any(type(row) is not Form4ProvisionalDispositionRow for row in self.rows)
        ):
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: disposition report state is invalid"
            )
        keys = tuple(
            (
                row.accession_number,
                row.source_sha256,
                row.row_index,
                row.event_id,
            )
            for row in self.rows
        )
        source_row_keys = tuple(
            (row.accession_number, row.row_index) for row in self.rows
        )
        candidate_count = sum(
            row.disposition
            is Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
            for row in self.rows
        )
        if (
            keys != tuple(sorted(keys))
            or len(set(keys)) != len(keys)
            or len(set(source_row_keys)) != len(source_row_keys)
            or len({row.row_id for row in self.rows}) != len(self.rows)
            or len({row.transaction_payload_hash for row in self.rows})
            != len(self.rows)
            or self.identity.transaction_count != len(self.rows)
            or self.identity.candidate_count != candidate_count
            or self.identity.quarantine_count != len(self.rows) - candidate_count
        ):
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: disposition report row count or ordering is inconsistent"
            )
        if hash_payload([row.to_payload() for row in self.rows]) != (
            self.identity.row_inventory_hash
        ):
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: disposition report row inventory is inconsistent"
            )

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
    def point_in_time_security_identity_verified(self) -> bool:
        return False

    @property
    def canonical_filter_authorized(self) -> bool:
        return False

    @property
    def lot_aggregation_authorized(self) -> bool:
        return False

    @property
    def outcomes_authorized(self) -> bool:
        return False

    @property
    def authorized_outcome_looks(self) -> int:
        return 0

    def to_payload(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_payload(),
            "rows": [row.to_payload() for row in self.rows],
        }


def _accepted_at(value: str) -> datetime:
    if type(value) is not str:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: supplied acceptance evidence is invalid"
        )
    try:
        accepted_at = datetime.fromisoformat(value)
        offset = accepted_at.utcoffset()
    except (OverflowError, TypeError, ValueError) as exc:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: supplied acceptance evidence is invalid"
        ) from exc
    if (
        offset is None
        or accepted_at.microsecond != 0
        or accepted_at.astimezone(timezone.utc).isoformat(timespec="seconds")
        != value
    ):
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: supplied acceptance evidence is not canonical UTC"
        )
    return accepted_at


def _reparse_evidence(
    evidence: ProfileBoundForm4AmendmentEvidence,
) -> tuple[FilingCorpus, str]:
    """Rebuild every filing and reject any forged retained transaction state."""

    if type(evidence) is not ProfileBoundForm4AmendmentEvidence:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: input must be factory-created profile-bound evidence"
        )
    if (
        type(evidence.xml_sources) is not tuple
        or not evidence.xml_sources
        or len(evidence.xml_sources) > MAX_FORM4_EVIDENCE_XML_SOURCES
        or any(
            type(source) is not SecForm4XmlSource
            or type(source.xml_bytes) is not bytes
            or not 0 < len(source.xml_bytes) <= MAX_XML_BYTES
            for source in evidence.xml_sources
        )
        or sum(len(source.xml_bytes) for source in evidence.xml_sources)
        > MAX_FORM4_EVIDENCE_XML_BYTES
        or type(evidence.supplied_link_evidence) is not tuple
        or not evidence.supplied_link_evidence
        or len(evidence.supplied_link_evidence)
        > MAX_FORM4_EVIDENCE_XML_SOURCES
        or any(
            type(item) is not SuppliedForm4AmendmentLinkEvidence
            for item in evidence.supplied_link_evidence
        )
        or type(evidence.as_filed_corpus) is not FilingCorpus
        or type(evidence.as_filed_corpus.filings) is not tuple
        or not evidence.as_filed_corpus.filings
        or len(evidence.as_filed_corpus.filings)
        > MAX_FORM4_EVIDENCE_XML_SOURCES
        or any(
            type(filing) is not ParsedFiling
            or type(filing.reporting_owners) is not tuple
            or len(filing.reporting_owners) > MAX_REPORTING_OWNERS_PER_FILING
            or type(filing.footnotes) is not tuple
            or len(filing.footnotes) > MAX_FOOTNOTES_PER_FILING
            or type(filing.transactions) is not tuple
            or len(filing.transactions) > MAX_TRANSACTIONS_PER_FILING
            for filing in evidence.as_filed_corpus.filings
        )
        or sum(
            len(filing.reporting_owners)
            for filing in evidence.as_filed_corpus.filings
        )
        > MAX_TOTAL_REPORTING_OWNERS
        or sum(
            len(filing.footnotes)
            for filing in evidence.as_filed_corpus.filings
        )
        > MAX_TOTAL_FOOTNOTES
        or sum(
            len(filing.transactions)
            for filing in evidence.as_filed_corpus.filings
        )
        > MAX_TOTAL_TRANSACTIONS
        or type(evidence.lineages) is not tuple
        or not evidence.lineages
        or len(evidence.lineages) > MAX_FORM4_EVIDENCE_XML_SOURCES
        or any(
            type(item) is not Form4AmendmentLineage
            or type(item.versions) is not tuple
            or not item.versions
            or len(item.versions) > MAX_FORM4_EVIDENCE_XML_SOURCES
            for item in evidence.lineages
        )
        or sum(len(item.versions) for item in evidence.lineages)
        > MAX_FORM4_EVIDENCE_XML_SOURCES
    ):
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: upstream evidence shape or resource bound is invalid"
        )
    identity = evidence.identity
    if type(identity) is not Form4MultiPeriodEvidenceIdentity:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: upstream evidence identity type is invalid"
        )
    if (
        type(identity.period_inventory) is not tuple
        or not 2 <= len(identity.period_inventory) <= MAX_FORM4_EVIDENCE_PERIODS
        or any(
            type(item) is not SecEdgarAcceptancePeriodIdentity
            for item in identity.period_inventory
        )
        or type(identity.evidence_profile)
        is not SecForm4AmendmentEvidenceProfile
        or type(identity.supplied_link_evidence) is not tuple
        or not identity.supplied_link_evidence
        or len(identity.supplied_link_evidence)
        > MAX_FORM4_EVIDENCE_XML_SOURCES
        or any(
            type(item) is not SuppliedForm4AmendmentLinkEvidence
            for item in identity.supplied_link_evidence
        )
        or type(identity.source_inventory) is not tuple
        or not identity.source_inventory
        or len(identity.source_inventory) > MAX_FORM4_EVIDENCE_XML_SOURCES
        or any(
            type(item) is not SecForm4XmlSourceIdentity
            for item in identity.source_inventory
        )
        or type(identity.transaction_count) is not int
        or not 0 <= identity.transaction_count <= MAX_TOTAL_TRANSACTIONS
    ):
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: upstream evidence identity children are invalid"
        )
    try:
        for period in identity.period_inventory:
            SecEdgarAcceptancePeriodIdentity.__post_init__(period)
        SecForm4AmendmentEvidenceProfile._validate(
            identity.evidence_profile
        )
        for supplied in identity.supplied_link_evidence:
            SuppliedForm4AmendmentLinkEvidence.__post_init__(supplied)
        for source_identity in identity.source_inventory:
            SecForm4XmlSourceIdentity.__post_init__(source_identity)
        Form4MultiPeriodEvidenceIdentity.__post_init__(
            identity,
            evidence_module._VERIFIED_IDENTITY_FACTORY_TOKEN
        )
    except (AttributeError, ContractError, TypeError, ValueError) as exc:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: upstream evidence revalidation failed"
        ) from exc
    if (
        identity.official_amendment_link_verified is not False
        or identity.complete_amendment_coverage_verified is not False
        or identity.canonical_filter_authorized is not False
        or evidence.official_amendment_link_verified is not False
        or evidence.complete_amendment_coverage_verified is not False
        or evidence.canonical_filter_authorized is not False
        or type(identity.transaction_count) is not int
        or not 0 <= identity.transaction_count <= MAX_TOTAL_TRANSACTIONS
    ):
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: profile-bound evidence is invalid or claims authority"
        )
    if identity.evidence_profile.official_sec_profile_verified is not False:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: evidence profile cannot claim official authority"
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
            for source in evidence.xml_sources
        )
        source_inventory = tuple(
            _source_identity(item) for item in rebuilt_sources
        )
    except ContractError as exc:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: evidence source inventory cannot be rebuilt"
        ) from exc
    evidence_inventory = evidence.supplied_link_evidence
    source_accessions = tuple(
        source.accession_number for source in evidence.xml_sources
    )
    if (
        tuple(sorted(evidence.xml_sources, key=lambda item: item.accession_number))
        != evidence.xml_sources
        or rebuilt_sources != evidence.xml_sources
        or len(set(source_accessions)) != len(source_accessions)
        or source_inventory != identity.source_inventory
        or evidence_inventory != identity.supplied_link_evidence
        or hash_payload([item.to_payload() for item in source_inventory])
        != identity.source_inventory_hash
        or hash_payload([item.to_payload() for item in evidence_inventory])
        != identity.supplied_link_evidence_hash
    ):
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: evidence source inventory is inconsistent"
        )
    start = identity.period_inventory[0]
    end = identity.period_inventory[-1]
    expected_evidence_id = (
        f"form4-multi-period-evidence-{start.year:04d}q{start.quarter}-"
        f"{end.year:04d}q{end.quarter}-"
        f"{hash_payload(identity.lineage_payload())[:16]}"
    )
    if identity.evidence_id != expected_evidence_id:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: evidence identity is inconsistent"
        )

    evidence_by_accession = {
        item.accession_number: item for item in evidence_inventory
    }
    retained_by_accession = {
        filing.envelope.accession_number: filing
        for filing in evidence.as_filed_corpus.filings
    }
    if (
        len(evidence_by_accession) != len(evidence_inventory)
        or len(retained_by_accession) != len(evidence.as_filed_corpus.filings)
        or set(evidence_by_accession)
        != {source.accession_number for source in evidence.xml_sources}
        or set(evidence_by_accession) != set(retained_by_accession)
    ):
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: evidence accession inventory is inconsistent"
        )

    reparsed_filings = []
    for source in rebuilt_sources:
        supplied = evidence_by_accession[source.accession_number]
        if (
            supplied.primary_document_sha256 != source.xml_sha256
            or supplied.primary_document_url != source.primary_document_url
            or supplied.amends_accession != source.amends_accession
        ):
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: supplied evidence disagrees with XML bytes"
            )
        try:
            filing = parse_form4_xml(
                source.xml_bytes,
                accession_number=source.accession_number,
                acceptance=_accepted_at(supplied.accepted_at_utc),
                source_name=source.primary_document_url,
                amends_accession=supplied.amends_accession,
            )
        except ContractError as exc:
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: XML source cannot be reparsed"
            ) from exc
        retained = retained_by_accession[source.accession_number]
        if filing != retained:
            raise Form4ProvisionalDispositionReportError(
                "REFUSED: reparsed corpus disagrees with retained transactions"
            )
        reparsed_filings.append(filing)

    try:
        reparsed_corpus = build_filing_corpus(reparsed_filings)
        reparsed_lineages = _build_lineages(reparsed_corpus)
        parsed_corpus_hash = _parsed_corpus_hash(reparsed_corpus)
    except ContractError as exc:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: reparsed corpus is invalid"
        ) from exc
    transaction_count = sum(
        len(filing.transactions) for filing in reparsed_corpus.filings
    )
    if (
        reparsed_corpus != evidence.as_filed_corpus
        or reparsed_lineages != evidence.lineages
        or parsed_corpus_hash != identity.parsed_corpus_hash
        or identity.filing_count != len(reparsed_corpus.filings)
        or identity.lineage_count != len(reparsed_lineages)
        or identity.transaction_count != transaction_count
    ):
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: reparsed corpus identity is inconsistent"
        )
    try:
        ProfileBoundForm4AmendmentEvidence.__post_init__(
            evidence,
            evidence_module._VERIFIED_RESULT_FACTORY_TOKEN,
        )
    except (AttributeError, ContractError, TypeError, ValueError) as exc:
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: upstream evidence result revalidation failed"
        ) from exc
    return reparsed_corpus, hash_payload(identity.to_payload())


def _row_from_transaction(
    transaction: ParsedTransaction,
) -> Form4ProvisionalDispositionRow:
    transaction_payload = _transaction_payload(transaction)
    transaction_payload_hash = hash_payload(transaction_payload)
    disposition = (
        Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
        if transaction.outcomes
        == (ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,)
        else Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE
    )
    lineage_payload = {
        "accession_number": transaction.accession_number,
        "source_sha256": transaction.source_sha256,
        "row_index": transaction.row_index,
        "event_id": transaction.event_id,
        "derivative": transaction.derivative,
        "security_title_raw": transaction.security_title_raw,
        "transaction_date": (
            None
            if transaction.transaction_date is None
            else transaction.transaction_date.isoformat()
        ),
        "transaction_code": transaction.transaction_code,
        "acquired_disposed_code": transaction.acquired_disposed_code,
        "shares": _decimal_payload(transaction.shares),
        "price_per_share": _decimal_payload(transaction.price_per_share),
        "purchase_value_usd": _decimal_payload(transaction.purchase_value_usd),
        "direct_indirect": transaction.direct_indirect,
        "footnote_ids": list(transaction.footnote_ids),
        "outcomes": [item.value for item in transaction.outcomes],
        "diagnostics": [item.value for item in transaction.diagnostics],
        "transaction_payload_hash": transaction_payload_hash,
        "disposition": disposition.value,
    }
    return Form4ProvisionalDispositionRow(
        accession_number=transaction.accession_number,
        source_sha256=transaction.source_sha256,
        row_index=transaction.row_index,
        event_id=transaction.event_id,
        derivative=transaction.derivative,
        security_title_raw=transaction.security_title_raw,
        transaction_date=transaction.transaction_date,
        transaction_code=transaction.transaction_code,
        acquired_disposed_code=transaction.acquired_disposed_code,
        shares=transaction.shares,
        price_per_share=transaction.price_per_share,
        purchase_value_usd=transaction.purchase_value_usd,
        direct_indirect=transaction.direct_indirect,
        footnote_ids=transaction.footnote_ids,
        outcomes=transaction.outcomes,
        diagnostics=transaction.diagnostics,
        transaction_payload_hash=transaction_payload_hash,
        disposition=disposition,
        row_id=hash_payload(lineage_payload),
    )


def build_form4_provisional_disposition_report(
    evidence: ProfileBoundForm4AmendmentEvidence,
    *,
    builder_git_commit: str,
) -> Form4ProvisionalDispositionReport:
    """Build one deterministic, non-authoritative row for every transaction."""

    if (
        type(builder_git_commit) is not str
        or _GIT_COMMIT_RE.fullmatch(builder_git_commit) is None
    ):
        raise Form4ProvisionalDispositionReportError(
            "REFUSED: builder Git commit must be a full lowercase SHA-1"
        )
    corpus, evidence_identity_hash = _reparse_evidence(evidence)
    rows = tuple(
        sorted(
            (
                _row_from_transaction(transaction)
                for filing in corpus.filings
                for transaction in filing.transactions
            ),
            key=lambda item: (
                item.accession_number,
                item.source_sha256,
                item.row_index,
                item.event_id,
            ),
        )
    )
    row_inventory_hash = hash_payload([row.to_payload() for row in rows])
    candidate_count = sum(
        row.disposition
        is Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
        for row in rows
    )
    identity_payload = {
        "contract_version": FORM4_PROVISIONAL_DISPOSITION_REPORT_VERSION,
        "builder_git_commit": builder_git_commit,
        "upstream_evidence_id": evidence.identity.evidence_id,
        "upstream_evidence_identity_hash": evidence_identity_hash,
        "upstream_parsed_corpus_hash": evidence.identity.parsed_corpus_hash,
        "upstream_source_inventory_hash": evidence.identity.source_inventory_hash,
        "row_inventory_hash": row_inventory_hash,
        "transaction_count": len(rows),
        "candidate_count": candidate_count,
        "quarantine_count": len(rows) - candidate_count,
        "official_profile_compatibility_verified": False,
        "official_amendment_link_verified": False,
        "complete_amendment_coverage_verified": False,
        "point_in_time_security_identity_verified": False,
        "canonical_filter_authorized": False,
        "lot_aggregation_authorized": False,
        "outcomes_authorized": False,
        "authorized_outcome_looks": 0,
    }
    identity = Form4ProvisionalDispositionReportIdentity(
        **identity_payload,
        report_id=(
            "form4-provisional-disposition-report-"
            f"{hash_payload(identity_payload)[:16]}"
        ),
        _verified_factory_token=_VERIFIED_IDENTITY_FACTORY_TOKEN,
    )
    return Form4ProvisionalDispositionReport(
        identity=identity,
        rows=rows,
        _verified_factory_token=_VERIFIED_REPORT_FACTORY_TOKEN,
    )


__all__ = [
    "FORM4_PROVISIONAL_DISPOSITION_REPORT_VERSION",
    "Form4ProvisionalDisposition",
    "Form4ProvisionalDispositionReport",
    "Form4ProvisionalDispositionReportError",
    "Form4ProvisionalDispositionReportIdentity",
    "Form4ProvisionalDispositionRow",
    "build_form4_provisional_disposition_report",
]
