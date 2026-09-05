"""Observed-only Form 4 identity inventory for the bounded IB-2A slice.

The inventory normalizes identity claims already present in factory-created
IB-1E evidence.  It independently reparses that evidence, retains every
filing, reporting owner, and transaction as a separate immutable observation,
then rebuilds and binds the public IB-1G provisional disposition report.
Joint owners never fan transactions out.

This module does not resolve issuer, owner, security, or transaction identity.
It does not infer a current ticker or share class, select an amendment, widen
the ordinary-equity grammar, aggregate lots, apply a value threshold, access
outcomes, publish a snapshot, or expose QC, portfolio, broker, scheduler, or
execution authority.  All such gates remain literal false values.
"""
from __future__ import annotations

import re
from dataclasses import InitVar, dataclass, fields
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from data.hashing import hash_bytes, hash_payload
from research.insider_buying.contracts import (
    AvailabilityPrecision,
    ClassificationOutcome,
    ContractError,
    ExecutionRule,
    FilingCorpus,
    FilingEnvelope,
    ParsedFiling,
    ParsedTransaction,
    PublicAvailability,
    ReportingOwner,
    TransactionDiagnostic,
)
from research.insider_buying.form4_amendment_reconciliation import (
    MAX_FOOTNOTES_PER_FILING,
    MAX_REPORTING_OWNERS_PER_FILING,
    MAX_TOTAL_FOOTNOTES,
    MAX_TRANSACTIONS_PER_FILING,
    Form4AmendmentLineage,
    Form4VersionInterval,
    Form4VersionDisposition,
    SecForm4XmlSource,
    SecForm4XmlSourceIdentity,
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
from research.insider_buying.form4_provisional_disposition_report import (
    FORM4_PROVISIONAL_DISPOSITION_REPORT_VERSION,
    Form4ProvisionalDisposition,
    Form4ProvisionalDispositionReport,
    Form4ProvisionalDispositionReportIdentity,
    Form4ProvisionalDispositionRow,
    _reparse_evidence as _reparse_profile_bound_evidence,
    build_form4_provisional_disposition_report,
)
from research.insider_buying.form4_xml import MAX_XML_BYTES
from research.insider_buying.sec_edgar_acceptance_snapshot import (
    MAX_METADATA_FIELD_NAME_CHARACTERS,
    MAX_METADATA_FIELDS,
)


FORM4_OBSERVED_IDENTITY_INVENTORY_VERSION = (
    "INSETF-IB2A-FORM4-OBSERVED-IDENTITY-INVENTORY-v1"
)
MAX_FORM4_OBSERVED_IDENTITY_FILINGS = 256
MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS = 4_096
MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS = 100_000
MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS = 64 * 1024 * 1024
MAX_FORM4_OBSERVED_IDENTITY_PROJECTION_NODES = 4_000_000
MAX_FORM4_OBSERVED_IDENTITY_PROJECTION_DEPTH = 64

_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_CIK_RE = re.compile(r"^[0-9]{10}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INVENTORY_ID_RE = re.compile(
    r"^form4-observed-identity-inventory-(?P<hash_prefix>[0-9a-f]{16})$"
)
_VERIFIED_IDENTITY_FACTORY_TOKEN = object()
_VERIFIED_INVENTORY_FACTORY_TOKEN = object()

_OBSERVED_CONTRACT_DATACLASS_TYPES = (
    FilingCorpus,
    FilingEnvelope,
    Form4AmendmentLineage,
    Form4MultiPeriodEvidenceIdentity,
    Form4ProvisionalDispositionReport,
    Form4ProvisionalDispositionReportIdentity,
    Form4ProvisionalDispositionRow,
    Form4VersionInterval,
    ParsedFiling,
    ParsedTransaction,
    PublicAvailability,
    ReportingOwner,
    SecEdgarAcceptancePeriodIdentity,
    SecForm4AmendmentEvidenceProfile,
    SecForm4XmlSource,
    SecForm4XmlSourceIdentity,
    SuppliedForm4AmendmentLinkEvidence,
)
_OBSERVED_CONTRACT_ENUM_TYPES = (
    AvailabilityPrecision,
    ClassificationOutcome,
    ExecutionRule,
    Form4VersionDisposition,
    Form4ProvisionalDisposition,
    TransactionDiagnostic,
)


class Form4ObservedIdentityInventoryError(ContractError):
    """The bounded IB-2A observed-identity contract failed closed."""


class Form4ObservedOwnerSetOutcome(str, Enum):
    """Named observation-only outcome for one filing's owner set."""

    SINGLE_COMPLETE_OWNER_SET_OBSERVED = (
        "single_complete_owner_set_observed"
    )
    MISSING_OWNER_SET_QUARANTINED = "missing_owner_set_quarantined"
    MULTIPLE_OWNER_SET_QUARANTINED = "multiple_owner_set_quarantined"
    INCOMPLETE_OWNER_RELATIONSHIP_QUARANTINED = (
        "incomplete_owner_relationship_quarantined"
    )


class Form4ObservedIdentityDisposition(str, Enum):
    """Unresolved routing label copied from the upstream IB-1G decision."""

    UNRESOLVED_PROVISIONAL_CANDIDATE = (
        "unresolved_provisional_candidate"
    )
    UNRESOLVED_QUARANTINE = "unresolved_quarantine"


def _required_text(value: object, *, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise Form4ObservedIdentityInventoryError(
            f"REFUSED: {label} must be exact non-empty text"
        )
    return value


def _optional_text(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, label=label)


def _sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise Form4ObservedIdentityInventoryError(
            f"REFUSED: {label} must be lowercase SHA-256"
        )
    return value


def _accession(value: object, *, label: str) -> str:
    if type(value) is not str or _ACCESSION_RE.fullmatch(value) is None:
        raise Form4ObservedIdentityInventoryError(
            f"REFUSED: {label} must be a canonical accession"
        )
    return value


def _canonical_utc_text(value: object, *, label: str) -> str:
    if type(value) is not str:
        raise Form4ObservedIdentityInventoryError(
            f"REFUSED: {label} must be canonical UTC text"
        )
    try:
        parsed = datetime.fromisoformat(value)
        offset = parsed.utcoffset()
        canonical = parsed.astimezone(timezone.utc).isoformat(
            timespec="seconds"
        )
    except (OverflowError, TypeError, ValueError) as exc:
        raise Form4ObservedIdentityInventoryError(
            f"REFUSED: {label} must be canonical UTC text"
        ) from exc
    if offset is None or parsed.microsecond != 0 or canonical != value:
        raise Form4ObservedIdentityInventoryError(
            f"REFUSED: {label} must be canonical UTC text"
        )
    return value


@dataclass
class _ProjectionBudget:
    text_characters: int = 0
    byte_count: int = 0
    node_count: int = 0
    active_object_ids: set[int] | None = None

    def __post_init__(self) -> None:
        if self.active_object_ids is None:
            self.active_object_ids = set()


def _contract_payload(
    value: object,
    *,
    _budget: _ProjectionBudget | None = None,
    _depth: int = 0,
) -> object:
    """Project exact frozen contract state into deterministic JSON values."""

    if _budget is None:
        _budget = _ProjectionBudget()
    if _depth > MAX_FORM4_OBSERVED_IDENTITY_PROJECTION_DEPTH:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: observed contract graph exceeds the depth bound"
        )
    _budget.node_count += 1
    if _budget.node_count > MAX_FORM4_OBSERVED_IDENTITY_PROJECTION_NODES:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: observed contract graph exceeds a resource bound"
        )
    value_type = type(value)
    if value_type in _OBSERVED_CONTRACT_ENUM_TYPES:
        return _contract_payload(
            value.value,
            _budget=_budget,
            _depth=_depth + 1,
        )
    if value_type is datetime:
        if value.tzinfo is not timezone.utc:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed datetime is not exact UTC"
            )
        return _contract_payload(
            value.isoformat(),
            _budget=_budget,
            _depth=_depth + 1,
        )
    if value_type is date:
        return _contract_payload(
            value.isoformat(),
            _budget=_budget,
            _depth=_depth + 1,
        )
    if value_type is Decimal:
        if not value.is_finite():
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed decimal state is not finite"
            )
        return _contract_payload(
            str(value),
            _budget=_budget,
            _depth=_depth + 1,
        )
    if value_type is str:
        _budget.text_characters += len(value)
        if (
            _budget.text_characters
            > MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed contract text exceeds a resource bound"
            )
        return value
    if value_type is bytes:
        _budget.byte_count += len(value)
        if _budget.byte_count > MAX_FORM4_EVIDENCE_XML_BYTES:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed contract bytes exceed a resource bound"
            )
        return {
            "byte_count": len(value),
            "sha256": hash_bytes(value),
        }
    if value is None or value_type is bool or value_type is int:
        return value
    if value_type is tuple or value_type in _OBSERVED_CONTRACT_DATACLASS_TYPES:
        active_object_ids = _budget.active_object_ids
        assert active_object_ids is not None
        object_id = id(value)
        if object_id in active_object_ids:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed contract graph contains a cycle"
            )
        active_object_ids.add(object_id)
        try:
            if value_type is tuple:
                return [
                    _contract_payload(
                        item,
                        _budget=_budget,
                        _depth=_depth + 1,
                    )
                    for item in value
                ]
            declared_fields = {item.name for item in fields(value_type)}
            instance_state = vars(value)
            if (
                type(instance_state) is not dict
                or set(instance_state) != declared_fields
            ):
                raise Form4ObservedIdentityInventoryError(
                    "REFUSED: observed dataclass instance state is not exact"
                )
            return {
                item.name: _contract_payload(
                    getattr(value, item.name),
                    _budget=_budget,
                    _depth=_depth + 1,
                )
                for item in fields(value_type)
            }
        finally:
            active_object_ids.remove(object_id)
    raise Form4ObservedIdentityInventoryError(
        "REFUSED: observed contract state contains an unsupported value"
    )


def _evidence_observation_hash(
    evidence: ProfileBoundForm4AmendmentEvidence,
) -> str:
    try:
        budget = _ProjectionBudget()
        payload = {
            "identity": _contract_payload(
                evidence.identity,
                _budget=budget,
            ),
            "xml_sources": _contract_payload(
                evidence.xml_sources,
                _budget=budget,
            ),
            "supplied_link_evidence": _contract_payload(
                evidence.supplied_link_evidence,
                _budget=budget,
            ),
            "corpus": _contract_payload(
                evidence.as_filed_corpus,
                _budget=budget,
            ),
            "lineages": _contract_payload(
                evidence.lineages,
                _budget=budget,
            ),
        }
        return hash_payload(payload)
    except Form4ObservedIdentityInventoryError:
        raise
    except (AttributeError, OverflowError, TypeError, ValueError) as exc:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: evidence observation state cannot be hashed"
        ) from exc


def _owner_set_outcomes(
    *, owner_count: int, all_relationships_complete: bool
) -> tuple[Form4ObservedOwnerSetOutcome, ...]:
    if owner_count == 1 and all_relationships_complete:
        return (
            Form4ObservedOwnerSetOutcome.SINGLE_COMPLETE_OWNER_SET_OBSERVED,
        )
    outcomes: list[Form4ObservedOwnerSetOutcome] = []
    if owner_count == 0:
        outcomes.append(
            Form4ObservedOwnerSetOutcome.MISSING_OWNER_SET_QUARANTINED
        )
    elif owner_count > 1:
        outcomes.append(
            Form4ObservedOwnerSetOutcome.MULTIPLE_OWNER_SET_QUARANTINED
        )
    if owner_count > 0 and not all_relationships_complete:
        outcomes.append(
            Form4ObservedOwnerSetOutcome.INCOMPLETE_OWNER_RELATIONSHIP_QUARANTINED
        )
    return tuple(outcomes)


def _identity_disposition(
    upstream: Form4ProvisionalDisposition,
) -> Form4ObservedIdentityDisposition:
    if upstream is (
        Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
    ):
        return Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE
    if upstream is Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE:
        return Form4ObservedIdentityDisposition.UNRESOLVED_QUARANTINE
    raise Form4ObservedIdentityInventoryError(
        "REFUSED: upstream disposition is unsupported"
    )


def _decimal_payload(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: captured transaction decimal state is invalid"
        )
    return str(value)


@dataclass(frozen=True)
class _CapturedTransactionBinding:
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


def _capture_transaction(
    transaction: ParsedTransaction,
) -> _CapturedTransactionBinding:
    transaction_payload = {
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
    disposition = (
        Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
        if transaction.outcomes
        == (ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,)
        else Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE
    )
    return _CapturedTransactionBinding(
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
        transaction_payload_hash=hash_payload(transaction_payload),
        disposition=disposition,
    )


@dataclass(frozen=True)
class Form4ObservedReportingOwnerIdentityRow:
    """One reporting-owner observation, preserving XML order and duplicates."""

    accession_number: str
    source_sha256: str
    reporting_owner_index: int
    owner_cik: str
    owner_name: str
    is_director: bool | None
    is_officer: bool | None
    is_ten_percent_owner: bool | None
    is_other: bool | None
    officer_title: str | None
    relationship_complete: bool
    owner_observation_id: str

    def __post_init__(self) -> None:
        _accession(self.accession_number, label="owner accession")
        _sha256(self.source_sha256, label="owner source hash")
        if (
            type(self.reporting_owner_index) is not int
            or self.reporting_owner_index < 0
            or type(self.owner_cik) is not str
            or _CIK_RE.fullmatch(self.owner_cik) is None
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: owner index or CIK is invalid"
            )
        _required_text(self.owner_name, label="owner name")
        _optional_text(self.officer_title, label="officer title")
        flags = (
            self.is_director,
            self.is_officer,
            self.is_ten_percent_owner,
            self.is_other,
        )
        if any(value is not None and type(value) is not bool for value in flags):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: owner relationship flags are invalid"
            )
        if (
            type(self.relationship_complete) is not bool
            or self.relationship_complete
            != all(value is not None for value in flags)
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: owner relationship completeness is inconsistent"
            )
        _sha256(self.owner_observation_id, label="owner observation ID")
        if self.owner_observation_id != hash_payload(self.lineage_payload()):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: owner observation ID is invalid"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "source_sha256": self.source_sha256,
            "reporting_owner_index": self.reporting_owner_index,
            "owner_cik": self.owner_cik,
            "owner_name": self.owner_name,
            "is_director": self.is_director,
            "is_officer": self.is_officer,
            "is_ten_percent_owner": self.is_ten_percent_owner,
            "is_other": self.is_other,
            "officer_title": self.officer_title,
            "relationship_complete": self.relationship_complete,
        }

    def to_payload(self) -> dict[str, object]:
        return {
            **self.lineage_payload(),
            "owner_observation_id": self.owner_observation_id,
        }


@dataclass(frozen=True)
class Form4ObservedFilingIdentityRow:
    """One as-filed issuer and amendment-lineage observation."""

    accession_number: str
    source_sha256: str
    document_type: str
    accepted_at_utc: str
    original_accession: str
    amends_accession: str | None
    primary_document_url: str
    issuer_cik: str
    issuer_name: str
    issuer_symbol_raw: str | None
    reporting_owner_count: int
    all_owner_relationships_complete: bool
    owner_set_outcomes: tuple[Form4ObservedOwnerSetOutcome, ...]
    reporting_owner_observation_ids: tuple[str, ...]
    reporting_owner_inventory_hash: str
    version_disposition: Form4VersionDisposition
    filing_observation_id: str

    def __post_init__(self) -> None:
        _accession(self.accession_number, label="filing accession")
        _sha256(self.source_sha256, label="filing source hash")
        _canonical_utc_text(
            self.accepted_at_utc, label="filing acceptance timestamp"
        )
        _accession(self.original_accession, label="original accession")
        if self.amends_accession is not None:
            _accession(self.amends_accession, label="amends accession")
        _required_text(self.primary_document_url, label="primary document URL")
        if any(character.isspace() for character in self.primary_document_url):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: primary document URL contains whitespace"
            )
        if type(self.issuer_cik) is not str or _CIK_RE.fullmatch(
            self.issuer_cik
        ) is None:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: issuer CIK is invalid"
            )
        _required_text(self.issuer_name, label="issuer name")
        _optional_text(self.issuer_symbol_raw, label="issuer symbol")
        if (
            type(self.document_type) is not str
            or self.document_type not in {"4", "4/A"}
            or type(self.reporting_owner_count) is not int
            or not 0
            <= self.reporting_owner_count
            <= MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS
            or type(self.all_owner_relationships_complete) is not bool
            or (
                self.reporting_owner_count == 0
                and self.all_owner_relationships_complete
            )
            or type(self.owner_set_outcomes) is not tuple
            or not self.owner_set_outcomes
            or any(
                type(item) is not Form4ObservedOwnerSetOutcome
                for item in self.owner_set_outcomes
            )
            or len(set(self.owner_set_outcomes)) != len(self.owner_set_outcomes)
            or self.owner_set_outcomes
            != _owner_set_outcomes(
                owner_count=self.reporting_owner_count,
                all_relationships_complete=(
                    self.all_owner_relationships_complete
                ),
            )
            or type(self.reporting_owner_observation_ids) is not tuple
            or len(self.reporting_owner_observation_ids)
            != self.reporting_owner_count
            or len(set(self.reporting_owner_observation_ids))
            != len(self.reporting_owner_observation_ids)
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: filing owner-set observation is inconsistent"
            )
        for value in self.reporting_owner_observation_ids:
            _sha256(value, label="filing owner observation ID")
        _sha256(
            self.reporting_owner_inventory_hash,
            label="filing owner inventory hash",
        )
        if type(self.version_disposition) is not Form4VersionDisposition:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: filing version disposition is invalid"
            )
        if self.document_type == "4":
            expected_version = (
                Form4VersionDisposition.ORIGINAL_OBSERVED_IN_SUPPLIED_SAMPLE
            )
            valid_lineage = (
                self.amends_accession is None
                and self.original_accession == self.accession_number
            )
        elif self.document_type == "4/A":
            expected_version = (
                Form4VersionDisposition.QUARANTINED_UNRESOLVED_AMENDMENT
            )
            valid_lineage = (
                self.amends_accession is not None
                and self.original_accession == self.amends_accession
                and self.original_accession != self.accession_number
            )
        else:
            expected_version = None
            valid_lineage = False
        if not valid_lineage or self.version_disposition is not expected_version:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: filing version lineage is inconsistent"
            )
        _sha256(self.filing_observation_id, label="filing observation ID")
        if self.filing_observation_id != hash_payload(self.lineage_payload()):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: filing observation ID is invalid"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "source_sha256": self.source_sha256,
            "document_type": self.document_type,
            "accepted_at_utc": self.accepted_at_utc,
            "original_accession": self.original_accession,
            "amends_accession": self.amends_accession,
            "primary_document_url": self.primary_document_url,
            "issuer_cik": self.issuer_cik,
            "issuer_name": self.issuer_name,
            "issuer_symbol_raw": self.issuer_symbol_raw,
            "reporting_owner_count": self.reporting_owner_count,
            "all_owner_relationships_complete": (
                self.all_owner_relationships_complete
            ),
            "owner_set_outcomes": [
                item.value for item in self.owner_set_outcomes
            ],
            "reporting_owner_observation_ids": list(
                self.reporting_owner_observation_ids
            ),
            "reporting_owner_inventory_hash": (
                self.reporting_owner_inventory_hash
            ),
            "version_disposition": self.version_disposition.value,
        }

    def to_payload(self) -> dict[str, object]:
        return {
            **self.lineage_payload(),
            "filing_observation_id": self.filing_observation_id,
        }


@dataclass(frozen=True)
class Form4ObservedTransactionIdentityRow:
    """One transaction observation bound to its filing and IB-1G row."""

    accession_number: str
    source_sha256: str
    row_index: int
    event_id: str
    upstream_report_row_id: str
    transaction_payload_hash: str
    filing_observation_id: str
    security_title_raw: str | None
    transaction_date: date | None
    upstream_disposition: Form4ProvisionalDisposition
    identity_disposition: Form4ObservedIdentityDisposition
    resolved_security_identity: None
    point_in_time_security_identity_verified: bool
    canonical_filter_authorized: bool
    lot_aggregation_authorized: bool
    transaction_observation_id: str

    def __post_init__(self) -> None:
        _accession(self.accession_number, label="transaction accession")
        _sha256(self.source_sha256, label="transaction source hash")
        if type(self.row_index) is not int or self.row_index < 0:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: transaction row index is invalid"
            )
        for label, value in (
            ("transaction event ID", self.event_id),
            ("upstream report row ID", self.upstream_report_row_id),
            ("transaction payload hash", self.transaction_payload_hash),
            ("filing observation ID", self.filing_observation_id),
            ("transaction observation ID", self.transaction_observation_id),
        ):
            _sha256(value, label=label)
        _optional_text(self.security_title_raw, label="security title")
        if self.transaction_date is not None and type(
            self.transaction_date
        ) is not date:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: transaction date is invalid"
            )
        if (
            type(self.upstream_disposition) is not Form4ProvisionalDisposition
            or type(self.identity_disposition)
            is not Form4ObservedIdentityDisposition
            or self.identity_disposition
            is not _identity_disposition(self.upstream_disposition)
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: transaction identity disposition is inconsistent"
            )
        if (
            self.resolved_security_identity is not None
            or self.point_in_time_security_identity_verified is not False
            or self.canonical_filter_authorized is not False
            or self.lot_aggregation_authorized is not False
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: transaction observation claims downstream authority"
            )
        if self.transaction_observation_id != hash_payload(
            self.lineage_payload()
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: transaction observation ID is invalid"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "accession_number": self.accession_number,
            "source_sha256": self.source_sha256,
            "row_index": self.row_index,
            "event_id": self.event_id,
            "upstream_report_row_id": self.upstream_report_row_id,
            "transaction_payload_hash": self.transaction_payload_hash,
            "filing_observation_id": self.filing_observation_id,
            "security_title_raw": self.security_title_raw,
            "transaction_date": (
                None
                if self.transaction_date is None
                else self.transaction_date.isoformat()
            ),
            "upstream_disposition": self.upstream_disposition.value,
            "identity_disposition": self.identity_disposition.value,
            "resolved_security_identity": None,
            "point_in_time_security_identity_verified": False,
            "canonical_filter_authorized": False,
            "lot_aggregation_authorized": False,
        }

    def to_payload(self) -> dict[str, object]:
        return {
            **self.lineage_payload(),
            "transaction_observation_id": self.transaction_observation_id,
        }


@dataclass(frozen=True)
class Form4ObservedIdentityInventoryIdentity:
    """Hash-bound identity exhaustive for the supplied evidence corpus."""

    contract_version: str
    builder_git_commit: str
    upstream_evidence_id: str
    upstream_evidence_identity_hash: str
    upstream_parsed_corpus_hash: str
    upstream_source_inventory_hash: str
    upstream_report_id: str
    upstream_report_identity_hash: str
    upstream_report_row_inventory_hash: str
    filing_inventory_hash: str
    reporting_owner_inventory_hash: str
    transaction_inventory_hash: str
    filing_count: int
    amendment_count: int
    reporting_owner_count: int
    non_single_owner_filing_count: int
    transaction_count: int
    provisional_candidate_count: int
    quarantine_count: int
    official_profile_compatibility_verified: bool
    official_amendment_link_verified: bool
    complete_amendment_coverage_verified: bool
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
    inventory_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _VERIFIED_IDENTITY_FACTORY_TOKEN:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed inventory identity must be factory-created"
            )
        if (
            type(self.contract_version) is not str
            or self.contract_version
            != FORM4_OBSERVED_IDENTITY_INVENTORY_VERSION
            or type(self.builder_git_commit) is not str
            or _GIT_COMMIT_RE.fullmatch(self.builder_git_commit) is None
            or type(self.upstream_evidence_id) is not str
            or not self.upstream_evidence_id
            or type(self.upstream_report_id) is not str
            or not self.upstream_report_id
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed inventory identity is invalid"
            )
        for label, value in (
            ("upstream evidence identity hash", self.upstream_evidence_identity_hash),
            ("upstream parsed corpus hash", self.upstream_parsed_corpus_hash),
            ("upstream source inventory hash", self.upstream_source_inventory_hash),
            ("upstream report identity hash", self.upstream_report_identity_hash),
            ("upstream report row hash", self.upstream_report_row_inventory_hash),
            ("filing inventory hash", self.filing_inventory_hash),
            ("owner inventory hash", self.reporting_owner_inventory_hash),
            ("transaction inventory hash", self.transaction_inventory_hash),
        ):
            _sha256(value, label=label)
        counts_and_caps = (
            (self.filing_count, MAX_FORM4_OBSERVED_IDENTITY_FILINGS),
            (self.amendment_count, MAX_FORM4_OBSERVED_IDENTITY_FILINGS),
            (
                self.reporting_owner_count,
                MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS,
            ),
            (
                self.non_single_owner_filing_count,
                MAX_FORM4_OBSERVED_IDENTITY_FILINGS,
            ),
            (
                self.transaction_count,
                MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
            ),
            (
                self.provisional_candidate_count,
                MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
            ),
            (
                self.quarantine_count,
                MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
            ),
        )
        if any(
            type(value) is not int or not 0 <= value <= cap
            for value, cap in counts_and_caps
        ) or (
            self.amendment_count > self.filing_count
            or self.non_single_owner_filing_count > self.filing_count
            or self.provisional_candidate_count + self.quarantine_count
            != self.transaction_count
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed inventory counts are invalid"
            )
        authority = (
            self.official_profile_compatibility_verified,
            self.official_amendment_link_verified,
            self.complete_amendment_coverage_verified,
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
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed inventory claims authority"
            )
        match = (
            _INVENTORY_ID_RE.fullmatch(self.inventory_id)
            if type(self.inventory_id) is str
            else None
        )
        if (
            match is None
            or match.group("hash_prefix")
            != hash_payload(self.lineage_payload())[:16]
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed inventory ID is invalid"
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
            "upstream_source_inventory_hash": self.upstream_source_inventory_hash,
            "upstream_report_id": self.upstream_report_id,
            "upstream_report_identity_hash": self.upstream_report_identity_hash,
            "upstream_report_row_inventory_hash": (
                self.upstream_report_row_inventory_hash
            ),
            "filing_inventory_hash": self.filing_inventory_hash,
            "reporting_owner_inventory_hash": (
                self.reporting_owner_inventory_hash
            ),
            "transaction_inventory_hash": self.transaction_inventory_hash,
            "filing_count": self.filing_count,
            "amendment_count": self.amendment_count,
            "reporting_owner_count": self.reporting_owner_count,
            "non_single_owner_filing_count": (
                self.non_single_owner_filing_count
            ),
            "transaction_count": self.transaction_count,
            "provisional_candidate_count": self.provisional_candidate_count,
            "quarantine_count": self.quarantine_count,
            "official_profile_compatibility_verified": False,
            "official_amendment_link_verified": False,
            "complete_amendment_coverage_verified": False,
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

    def to_payload(self) -> dict[str, object]:
        return {**self.lineage_payload(), "inventory_id": self.inventory_id}


@dataclass(frozen=True)
class Form4ObservedIdentityInventory:
    """Normalized inventory exhaustive only for supplied, revalidated evidence."""

    identity: Form4ObservedIdentityInventoryIdentity
    filings: tuple[Form4ObservedFilingIdentityRow, ...]
    reporting_owners: tuple[Form4ObservedReportingOwnerIdentityRow, ...]
    transactions: tuple[Form4ObservedTransactionIdentityRow, ...]
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _VERIFIED_INVENTORY_FACTORY_TOKEN:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed identity inventory must be factory-created"
            )
        if (
            type(self.identity) is not Form4ObservedIdentityInventoryIdentity
            or type(self.filings) is not tuple
            or type(self.reporting_owners) is not tuple
            or type(self.transactions) is not tuple
            or any(
                type(item) is not Form4ObservedFilingIdentityRow
                for item in self.filings
            )
            or any(
                type(item) is not Form4ObservedReportingOwnerIdentityRow
                for item in self.reporting_owners
            )
            or any(
                type(item) is not Form4ObservedTransactionIdentityRow
                for item in self.transactions
            )
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed inventory state is invalid"
            )
        try:
            Form4ObservedIdentityInventoryIdentity.__post_init__(
                self.identity,
                _VERIFIED_IDENTITY_FACTORY_TOKEN,
            )
            for item in self.filings:
                Form4ObservedFilingIdentityRow.__post_init__(item)
            for item in self.reporting_owners:
                Form4ObservedReportingOwnerIdentityRow.__post_init__(item)
            for item in self.transactions:
                Form4ObservedTransactionIdentityRow.__post_init__(item)
        except (AttributeError, ContractError, TypeError, ValueError) as exc:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed inventory child revalidation failed"
            ) from exc
        filing_keys = tuple(
            (item.accession_number, item.source_sha256)
            for item in self.filings
        )
        owner_keys = tuple(
            (
                item.accession_number,
                item.source_sha256,
                item.reporting_owner_index,
            )
            for item in self.reporting_owners
        )
        transaction_keys = tuple(
            (
                item.accession_number,
                item.source_sha256,
                item.row_index,
                item.event_id,
            )
            for item in self.transactions
        )
        filing_accessions = tuple(
            item.accession_number for item in self.filings
        )
        transaction_source_row_keys = tuple(
            (item.accession_number, item.row_index)
            for item in self.transactions
        )
        if (
            filing_keys != tuple(sorted(filing_keys))
            or owner_keys != tuple(sorted(owner_keys))
            or transaction_keys != tuple(sorted(transaction_keys))
            or len(set(filing_keys)) != len(filing_keys)
            or len(set(owner_keys)) != len(owner_keys)
            or len(set(transaction_keys)) != len(transaction_keys)
            or len(set(filing_accessions)) != len(filing_accessions)
            or len(set(transaction_source_row_keys))
            != len(transaction_source_row_keys)
            or len({item.filing_observation_id for item in self.filings})
            != len(self.filings)
            or len({item.owner_observation_id for item in self.reporting_owners})
            != len(self.reporting_owners)
            or len(
                {
                    item.transaction_observation_id
                    for item in self.transactions
                }
            )
            != len(self.transactions)
            or len({item.upstream_report_row_id for item in self.transactions})
            != len(self.transactions)
            or len(
                {item.transaction_payload_hash for item in self.transactions}
            )
            != len(self.transactions)
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed inventory order or uniqueness is invalid"
            )
        filings_by_key = {
            (item.accession_number, item.source_sha256): item
            for item in self.filings
        }
        filings_by_accession = {
            item.accession_number: item for item in self.filings
        }
        acceptance_times_by_original: dict[str, set[str]] = {}
        for filing in self.filings:
            lineage_acceptance_times = acceptance_times_by_original.setdefault(
                filing.original_accession,
                set(),
            )
            if filing.accepted_at_utc in lineage_acceptance_times:
                raise Form4ObservedIdentityInventoryError(
                    "REFUSED: filing lineage acceptance times are ambiguous"
                )
            lineage_acceptance_times.add(filing.accepted_at_utc)
            if filing.document_type == "4":
                continue
            original = filings_by_accession.get(filing.original_accession)
            if (
                original is None
                or original.document_type != "4"
                or original.amends_accession is not None
                or original.original_accession != original.accession_number
                or original.issuer_cik != filing.issuer_cik
                or original.accepted_at_utc >= filing.accepted_at_utc
            ):
                raise Form4ObservedIdentityInventoryError(
                    "REFUSED: amendment-to-original filing binding is invalid"
                )
        owners_by_filing: dict[
            tuple[str, str],
            list[Form4ObservedReportingOwnerIdentityRow],
        ] = {key: [] for key in filings_by_key}
        for owner in self.reporting_owners:
            key = (owner.accession_number, owner.source_sha256)
            if key not in owners_by_filing:
                raise Form4ObservedIdentityInventoryError(
                    "REFUSED: owner observation has no filing"
                )
            owners_by_filing[key].append(owner)
        for key, filing in filings_by_key.items():
            owners = owners_by_filing[key]
            if (
                tuple(item.reporting_owner_index for item in owners)
                != tuple(range(len(owners)))
                or tuple(item.owner_observation_id for item in owners)
                != filing.reporting_owner_observation_ids
                or hash_payload([item.to_payload() for item in owners])
                != filing.reporting_owner_inventory_hash
                or len(owners) != filing.reporting_owner_count
                or (
                    bool(owners)
                    and all(item.relationship_complete for item in owners)
                )
                != filing.all_owner_relationships_complete
            ):
                raise Form4ObservedIdentityInventoryError(
                    "REFUSED: filing-to-owner inventory binding is invalid"
                )
        transactions_by_filing: dict[
            tuple[str, str],
            list[Form4ObservedTransactionIdentityRow],
        ] = {key: [] for key in filings_by_key}
        for transaction in self.transactions:
            key = (transaction.accession_number, transaction.source_sha256)
            filing = filings_by_key.get(key)
            if (
                filing is None
                or transaction.filing_observation_id
                != filing.filing_observation_id
            ):
                raise Form4ObservedIdentityInventoryError(
                    "REFUSED: transaction-to-filing binding is invalid"
                )
            transactions_by_filing[key].append(transaction)
            if transaction.identity_disposition is (
                Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE
            ) and (
                filing.version_disposition
                is not Form4VersionDisposition.ORIGINAL_OBSERVED_IN_SUPPLIED_SAMPLE
                or filing.owner_set_outcomes
                != (
                    Form4ObservedOwnerSetOutcome.SINGLE_COMPLETE_OWNER_SET_OBSERVED,
                )
            ):
                raise Form4ObservedIdentityInventoryError(
                    "REFUSED: unresolved candidate contradicts filing quarantine"
                )
        if any(
            tuple(item.row_index for item in transactions)
            != tuple(range(len(transactions)))
            for transactions in transactions_by_filing.values()
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: filing transaction row indexes are not contiguous"
            )
        candidate_count = sum(
            item.identity_disposition
            is Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE
            for item in self.transactions
        )
        if (
            self.identity.filing_count != len(self.filings)
            or self.identity.amendment_count
            != sum(item.document_type == "4/A" for item in self.filings)
            or self.identity.reporting_owner_count
            != len(self.reporting_owners)
            or self.identity.non_single_owner_filing_count
            != sum(item.reporting_owner_count != 1 for item in self.filings)
            or self.identity.transaction_count != len(self.transactions)
            or self.identity.provisional_candidate_count != candidate_count
            or self.identity.quarantine_count
            != len(self.transactions) - candidate_count
            or hash_payload([item.to_payload() for item in self.filings])
            != self.identity.filing_inventory_hash
            or hash_payload(
                [item.to_payload() for item in self.reporting_owners]
            )
            != self.identity.reporting_owner_inventory_hash
            or hash_payload([item.to_payload() for item in self.transactions])
            != self.identity.transaction_inventory_hash
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed inventory counts or hashes are inconsistent"
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
            "filings": [item.to_payload() for item in self.filings],
            "reporting_owners": [
                item.to_payload() for item in self.reporting_owners
            ],
            "transactions": [
                item.to_payload() for item in self.transactions
            ],
        }


def _preflight_evidence(evidence: object) -> None:
    """Reject hostile shapes and resource excess before the upstream rebuild."""

    if type(evidence) is not ProfileBoundForm4AmendmentEvidence:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: input must be exact profile-bound Form 4 evidence"
        )
    try:
        identity = evidence.identity
        xml_sources = evidence.xml_sources
        supplied_link_evidence = evidence.supplied_link_evidence
        corpus = evidence.as_filed_corpus
        lineages = evidence.lineages
    except AttributeError as exc:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: profile-bound evidence state is missing"
        ) from exc
    if (
        type(identity) is not Form4MultiPeriodEvidenceIdentity
        or type(identity.period_inventory) is not tuple
        or not 2
        <= len(identity.period_inventory)
        <= MAX_FORM4_EVIDENCE_PERIODS
        or any(
            type(item) is not SecEdgarAcceptancePeriodIdentity
            for item in identity.period_inventory
        )
        or type(identity.evidence_profile)
        is not SecForm4AmendmentEvidenceProfile
        or type(identity.evidence_profile.exact_fields) is not tuple
        or not identity.evidence_profile.exact_fields
        or len(identity.evidence_profile.exact_fields) > MAX_METADATA_FIELDS
        or any(
            type(name) is not str
            or len(name) > MAX_METADATA_FIELD_NAME_CHARACTERS
            for name in identity.evidence_profile.exact_fields
        )
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
        or not 0
        <= identity.transaction_count
        <= MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
        or type(xml_sources) is not tuple
        or not xml_sources
        or len(xml_sources) > MAX_FORM4_EVIDENCE_XML_SOURCES
        or any(
            type(source) is not SecForm4XmlSource
            or type(source.xml_bytes) is not bytes
            or not 0 < len(source.xml_bytes) <= MAX_XML_BYTES
            for source in xml_sources
        )
        or sum(len(source.xml_bytes) for source in xml_sources)
        > MAX_FORM4_EVIDENCE_XML_BYTES
        or type(supplied_link_evidence) is not tuple
        or not supplied_link_evidence
        or len(supplied_link_evidence) > MAX_FORM4_EVIDENCE_XML_SOURCES
        or any(
            type(item) is not SuppliedForm4AmendmentLinkEvidence
            for item in supplied_link_evidence
        )
        or type(corpus) is not FilingCorpus
        or type(corpus.filings) is not tuple
        or not corpus.filings
        or len(corpus.filings) > MAX_FORM4_OBSERVED_IDENTITY_FILINGS
        or any(type(filing) is not ParsedFiling for filing in corpus.filings)
        or type(corpus.superseded_by) is not tuple
        or len(corpus.superseded_by) > MAX_FORM4_OBSERVED_IDENTITY_FILINGS
        or any(
            type(edge) is not tuple
            or len(edge) != 2
            or type(edge[0]) is not str
            or type(edge[1]) is not tuple
            or len(edge[1]) > MAX_FORM4_OBSERVED_IDENTITY_FILINGS
            or any(type(accession) is not str for accession in edge[1])
            for edge in corpus.superseded_by
        )
        or sum(len(edge[1]) for edge in corpus.superseded_by)
        > MAX_FORM4_OBSERVED_IDENTITY_FILINGS
        or type(lineages) is not tuple
        or not lineages
        or len(lineages) > MAX_FORM4_EVIDENCE_XML_SOURCES
        or any(
            type(lineage) is not Form4AmendmentLineage
            or type(lineage.versions) is not tuple
            or not lineage.versions
            or len(lineage.versions) > MAX_FORM4_EVIDENCE_XML_SOURCES
            or any(
                type(version) is not Form4VersionInterval
                for version in lineage.versions
            )
            for lineage in lineages
        )
        or sum(len(lineage.versions) for lineage in lineages)
        > MAX_FORM4_EVIDENCE_XML_SOURCES
    ):
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: filing inventory shape or resource bound is invalid"
        )
    owner_count = 0
    footnote_count = 0
    footnote_id_reference_count = 0
    footnote_text_reference_count = 0
    transaction_count = 0
    for filing in corpus.filings:
        if (
            type(filing.envelope) is not FilingEnvelope
            or type(filing.reporting_owners) is not tuple
            or type(filing.footnotes) is not tuple
            or type(filing.transactions) is not tuple
            or len(filing.reporting_owners)
            > MAX_REPORTING_OWNERS_PER_FILING
            or len(filing.footnotes) > MAX_FOOTNOTES_PER_FILING
            or len(filing.transactions)
            > MAX_TRANSACTIONS_PER_FILING
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: filing children exceed an immutable resource bound"
            )
        owner_count += len(filing.reporting_owners)
        footnote_count += len(filing.footnotes)
        transaction_count += len(filing.transactions)
        if (
            owner_count > MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS
            or footnote_count > MAX_TOTAL_FOOTNOTES
            or transaction_count
            > MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: observed identity inventory exceeds a resource bound"
            )
        if (
            any(
                type(owner) is not ReportingOwner
                for owner in filing.reporting_owners
            )
            or any(
                type(footnote) is not tuple
                or len(footnote) != 2
                or any(type(value) is not str for value in footnote)
                for footnote in filing.footnotes
            )
            or any(
                type(transaction) is not ParsedTransaction
                for transaction in filing.transactions
            )
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: filing children must be exact immutable tuples"
            )
        for transaction in filing.transactions:
            if (
                type(transaction.footnote_ids) is not tuple
                or type(transaction.footnote_texts) is not tuple
                or len(transaction.footnote_ids) > MAX_FOOTNOTES_PER_FILING
                or len(transaction.footnote_texts) > MAX_FOOTNOTES_PER_FILING
                or any(type(item) is not str for item in transaction.footnote_ids)
                or any(
                    type(item) is not str for item in transaction.footnote_texts
                )
                or type(transaction.outcomes) is not tuple
                or len(transaction.outcomes) > len(ClassificationOutcome)
                or any(
                    type(item) is not ClassificationOutcome
                    for item in transaction.outcomes
                )
                or type(transaction.diagnostics) is not tuple
                or len(transaction.diagnostics) > len(TransactionDiagnostic)
                or any(
                    type(item) is not TransactionDiagnostic
                    for item in transaction.diagnostics
                )
            ):
                raise Form4ObservedIdentityInventoryError(
                    "REFUSED: transaction children exceed a resource bound"
                )
            footnote_id_reference_count += len(transaction.footnote_ids)
            footnote_text_reference_count += len(transaction.footnote_texts)
            if (
                footnote_id_reference_count > MAX_TOTAL_FOOTNOTES
                or footnote_text_reference_count > MAX_TOTAL_FOOTNOTES
            ):
                raise Form4ObservedIdentityInventoryError(
                    "REFUSED: transaction footnotes exceed a resource bound"
                )


def _owner_row(
    filing: ParsedFiling,
    index: int,
) -> Form4ObservedReportingOwnerIdentityRow:
    owner = filing.reporting_owners[index]
    payload = {
        "accession_number": filing.envelope.accession_number,
        "source_sha256": filing.envelope.source_sha256,
        "reporting_owner_index": index,
        "owner_cik": owner.owner_cik,
        "owner_name": owner.owner_name,
        "is_director": owner.is_director,
        "is_officer": owner.is_officer,
        "is_ten_percent_owner": owner.is_ten_percent_owner,
        "is_other": owner.is_other,
        "officer_title": owner.officer_title,
        "relationship_complete": owner.relationship_complete,
    }
    return Form4ObservedReportingOwnerIdentityRow(
        **payload,
        owner_observation_id=hash_payload(payload),
    )


def _filing_row(
    filing: ParsedFiling,
    owners: tuple[Form4ObservedReportingOwnerIdentityRow, ...],
) -> Form4ObservedFilingIdentityRow:
    envelope = filing.envelope
    accepted_at = envelope.availability.accepted_at
    if type(accepted_at) is not datetime:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: observed filing lacks an exact acceptance timestamp"
        )
    accepted_at_utc = accepted_at.astimezone(timezone.utc).isoformat(
        timespec="seconds"
    )
    owner_ids = tuple(item.owner_observation_id for item in owners)
    owner_inventory_hash = hash_payload([item.to_payload() for item in owners])
    all_complete = bool(owners) and all(
        item.relationship_complete for item in owners
    )
    if envelope.form_type == "4":
        original_accession = envelope.accession_number
        version_disposition = (
            Form4VersionDisposition.ORIGINAL_OBSERVED_IN_SUPPLIED_SAMPLE
        )
    elif envelope.form_type == "4/A" and envelope.amends_accession is not None:
        original_accession = envelope.amends_accession
        version_disposition = (
            Form4VersionDisposition.QUARANTINED_UNRESOLVED_AMENDMENT
        )
    else:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: observed filing version lineage is invalid"
        )
    payload = {
        "accession_number": envelope.accession_number,
        "source_sha256": envelope.source_sha256,
        "document_type": envelope.form_type,
        "accepted_at_utc": accepted_at_utc,
        "original_accession": original_accession,
        "amends_accession": envelope.amends_accession,
        "primary_document_url": envelope.source_name,
        "issuer_cik": envelope.issuer_cik,
        "issuer_name": envelope.issuer_name,
        "issuer_symbol_raw": envelope.issuer_symbol_raw,
        "reporting_owner_count": len(owners),
        "all_owner_relationships_complete": all_complete,
        "owner_set_outcomes": _owner_set_outcomes(
            owner_count=len(owners),
            all_relationships_complete=all_complete,
        ),
        "reporting_owner_observation_ids": owner_ids,
        "reporting_owner_inventory_hash": owner_inventory_hash,
        "version_disposition": version_disposition,
    }
    lineage_payload = {
        **payload,
        "owner_set_outcomes": [
            item.value for item in payload["owner_set_outcomes"]
        ],
        "reporting_owner_observation_ids": list(owner_ids),
        "version_disposition": version_disposition.value,
    }
    return Form4ObservedFilingIdentityRow(
        **payload,
        filing_observation_id=hash_payload(lineage_payload),
    )


def _transaction_row(
    report_row: Form4ProvisionalDispositionRow,
    filing: Form4ObservedFilingIdentityRow,
) -> Form4ObservedTransactionIdentityRow:
    identity_disposition = _identity_disposition(report_row.disposition)
    payload = {
        "accession_number": report_row.accession_number,
        "source_sha256": report_row.source_sha256,
        "row_index": report_row.row_index,
        "event_id": report_row.event_id,
        "upstream_report_row_id": report_row.row_id,
        "transaction_payload_hash": report_row.transaction_payload_hash,
        "filing_observation_id": filing.filing_observation_id,
        "security_title_raw": report_row.security_title_raw,
        "transaction_date": report_row.transaction_date,
        "upstream_disposition": report_row.disposition,
        "identity_disposition": identity_disposition,
        "resolved_security_identity": None,
        "point_in_time_security_identity_verified": False,
        "canonical_filter_authorized": False,
        "lot_aggregation_authorized": False,
    }
    lineage_payload = {
        **payload,
        "transaction_date": (
            None
            if report_row.transaction_date is None
            else report_row.transaction_date.isoformat()
        ),
        "upstream_disposition": report_row.disposition.value,
        "identity_disposition": identity_disposition.value,
    }
    return Form4ObservedTransactionIdentityRow(
        **payload,
        transaction_observation_id=hash_payload(lineage_payload),
    )


def _validate_rebuilt_report(
    report: object,
    *,
    builder_git_commit: str,
    upstream_evidence_id: str,
    upstream_evidence_identity_hash: str,
    upstream_parsed_corpus_hash: str,
    upstream_source_inventory_hash: str,
) -> Form4ProvisionalDispositionReport:
    """Validate the public IB-1G result without trusting cached fields."""

    if type(report) is not Form4ProvisionalDispositionReport:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: upstream report has the wrong exact type"
        )
    identity = report.identity
    if (
        type(identity) is not Form4ProvisionalDispositionReportIdentity
        or type(report.rows) is not tuple
        or len(report.rows) > MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
        or any(
            type(row) is not Form4ProvisionalDispositionRow
            for row in report.rows
        )
    ):
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: rebuilt upstream report binding is inconsistent"
        )
    try:
        captured_report_observation_hash = hash_payload(
            _contract_payload(report)
        )
    except Form4ObservedIdentityInventoryError:
        raise
    except (AttributeError, OverflowError, TypeError, ValueError) as exc:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: rebuilt upstream report state cannot be observed"
        ) from exc
    if (
        identity.contract_version
        != FORM4_PROVISIONAL_DISPOSITION_REPORT_VERSION
        or identity.builder_git_commit != builder_git_commit
        or identity.upstream_evidence_id != upstream_evidence_id
        or identity.upstream_evidence_identity_hash
        != upstream_evidence_identity_hash
        or identity.upstream_parsed_corpus_hash
        != upstream_parsed_corpus_hash
        or identity.upstream_source_inventory_hash
        != upstream_source_inventory_hash
    ):
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: rebuilt upstream report binding is inconsistent"
        )
    try:
        for row in report.rows:
            Form4ProvisionalDispositionRow.__post_init__(row)
    except (AttributeError, ContractError, TypeError, ValueError) as exc:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: rebuilt upstream report row is invalid"
        ) from exc
    report_keys = tuple(
        (
            row.accession_number,
            row.source_sha256,
            row.row_index,
            row.event_id,
        )
        for row in report.rows
    )
    source_row_keys = tuple(
        (row.accession_number, row.row_index) for row in report.rows
    )
    candidate_count = sum(
        row.disposition
        is Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
        for row in report.rows
    )
    identity_hashes = (
        identity.upstream_evidence_identity_hash,
        identity.upstream_parsed_corpus_hash,
        identity.upstream_source_inventory_hash,
        identity.row_inventory_hash,
    )
    authority = (
        identity.official_profile_compatibility_verified,
        identity.official_amendment_link_verified,
        identity.complete_amendment_coverage_verified,
        identity.point_in_time_security_identity_verified,
        identity.canonical_filter_authorized,
        identity.lot_aggregation_authorized,
        identity.outcomes_authorized,
    )
    if (
        any(type(value) is not str or _SHA256_RE.fullmatch(value) is None
            for value in identity_hashes)
        or report_keys != tuple(sorted(report_keys))
        or len(set(report_keys)) != len(report_keys)
        or len(set(source_row_keys)) != len(source_row_keys)
        or len({row.row_id for row in report.rows}) != len(report.rows)
        or len({row.transaction_payload_hash for row in report.rows})
        != len(report.rows)
        or type(identity.transaction_count) is not int
        or type(identity.candidate_count) is not int
        or type(identity.quarantine_count) is not int
        or not 0
        <= identity.transaction_count
        <= MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
        or not 0
        <= identity.candidate_count
        <= MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
        or not 0
        <= identity.quarantine_count
        <= MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
        or identity.transaction_count != len(report.rows)
        or identity.candidate_count != candidate_count
        or identity.quarantine_count != len(report.rows) - candidate_count
        or hash_payload(_contract_payload(report.rows))
        != identity.row_inventory_hash
        or any(value is not False for value in authority)
        or type(identity.authorized_outcome_looks) is not int
        or identity.authorized_outcome_looks != 0
        or type(identity.report_id) is not str
        or identity.report_id
        != (
            "form4-provisional-disposition-report-"
            f"{hash_payload(identity.lineage_payload())[:16]}"
        )
    ):
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: rebuilt upstream report is inconsistent"
        )
    if (
        hash_payload(_contract_payload(report))
        != captured_report_observation_hash
    ):
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: rebuilt upstream report changed during validation"
        )
    return report


def _build_form4_observed_identity_inventory(
    evidence: ProfileBoundForm4AmendmentEvidence,
    *,
    builder_git_commit: str,
) -> Form4ObservedIdentityInventory:
    """Build a deterministic, normalized inventory from supplied evidence."""

    if (
        type(builder_git_commit) is not str
        or _GIT_COMMIT_RE.fullmatch(builder_git_commit) is None
    ):
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: builder Git commit must be a full lowercase SHA-1"
        )
    _preflight_evidence(evidence)
    try:
        captured_evidence_observation_hash = _evidence_observation_hash(evidence)
        revalidated_corpus, expected_evidence_identity_hash = (
            _reparse_profile_bound_evidence(evidence)
        )
        if (
            _evidence_observation_hash(evidence)
            != captured_evidence_observation_hash
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: evidence changed during independent revalidation"
            )
        expected_evidence_id = evidence.identity.evidence_id
        expected_parsed_corpus_hash = evidence.identity.parsed_corpus_hash
        expected_source_inventory_hash = evidence.identity.source_inventory_hash
    except Form4ObservedIdentityInventoryError:
        raise
    except ContractError as exc:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: upstream evidence failed independent revalidation"
        ) from exc
    except (AttributeError, TypeError, ValueError) as exc:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: upstream evidence identity cannot be captured"
        ) from exc

    owner_rows: list[Form4ObservedReportingOwnerIdentityRow] = []
    filing_rows: list[Form4ObservedFilingIdentityRow] = []
    filing_by_key: dict[tuple[str, str], Form4ObservedFilingIdentityRow] = {}
    retained_transaction_bindings: dict[
        tuple[str, str, int, str],
        _CapturedTransactionBinding,
    ] = {}
    for filing in revalidated_corpus.filings:
        owners = tuple(
            _owner_row(filing, index)
            for index in range(len(filing.reporting_owners))
        )
        filing_row = _filing_row(filing, owners)
        key = (filing_row.accession_number, filing_row.source_sha256)
        if key in filing_by_key:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: duplicate filing observation key"
            )
        filing_by_key[key] = filing_row
        owner_rows.extend(owners)
        filing_rows.append(filing_row)
        for transaction in filing.transactions:
            transaction_key = (
                transaction.accession_number,
                transaction.source_sha256,
                transaction.row_index,
                transaction.event_id,
            )
            if transaction_key in retained_transaction_bindings:
                raise Form4ObservedIdentityInventoryError(
                    "REFUSED: duplicate retained transaction observation"
                )
            retained_transaction_bindings[transaction_key] = (
                _capture_transaction(transaction)
            )

    try:
        report = _validate_rebuilt_report(
            build_form4_provisional_disposition_report(
                evidence,
                builder_git_commit=builder_git_commit,
            ),
            builder_git_commit=builder_git_commit,
            upstream_evidence_id=expected_evidence_id,
            upstream_evidence_identity_hash=expected_evidence_identity_hash,
            upstream_parsed_corpus_hash=expected_parsed_corpus_hash,
            upstream_source_inventory_hash=expected_source_inventory_hash,
        )
    except Form4ObservedIdentityInventoryError:
        raise
    except (ContractError, TypeError, ValueError) as exc:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: upstream provisional report could not be rebuilt"
        ) from exc
    _preflight_evidence(evidence)
    if _evidence_observation_hash(evidence) != captured_evidence_observation_hash:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: evidence changed during upstream report validation"
        )
    sorted_filings = tuple(
        sorted(
            filing_rows,
            key=lambda item: (item.accession_number, item.source_sha256),
        )
    )
    sorted_owners = tuple(
        sorted(
            owner_rows,
            key=lambda item: (
                item.accession_number,
                item.source_sha256,
                item.reporting_owner_index,
            ),
        )
    )
    transaction_rows: list[Form4ObservedTransactionIdentityRow] = []
    report_transaction_keys = {
        (
            row.accession_number,
            row.source_sha256,
            row.row_index,
            row.event_id,
        )
        for row in report.rows
    }
    if (
        len(report_transaction_keys) != len(report.rows)
        or set(retained_transaction_bindings) != report_transaction_keys
    ):
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: retained and rebuilt transaction inventories disagree"
        )
    for report_row in report.rows:
        transaction_key = (
            report_row.accession_number,
            report_row.source_sha256,
            report_row.row_index,
            report_row.event_id,
        )
        retained = retained_transaction_bindings[transaction_key]
        if (
            report_row.derivative is not retained.derivative
            or report_row.security_title_raw != retained.security_title_raw
            or report_row.transaction_date != retained.transaction_date
            or report_row.transaction_code != retained.transaction_code
            or report_row.acquired_disposed_code
            != retained.acquired_disposed_code
            or report_row.shares != retained.shares
            or report_row.price_per_share != retained.price_per_share
            or report_row.purchase_value_usd != retained.purchase_value_usd
            or report_row.direct_indirect != retained.direct_indirect
            or report_row.footnote_ids != retained.footnote_ids
            or report_row.outcomes != retained.outcomes
            or report_row.diagnostics != retained.diagnostics
            or report_row.transaction_payload_hash
            != retained.transaction_payload_hash
            or report_row.disposition is not retained.disposition
        ):
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: rebuilt transaction disagrees with captured evidence"
            )
        filing = filing_by_key.get(
            (report_row.accession_number, report_row.source_sha256)
        )
        if filing is None:
            raise Form4ObservedIdentityInventoryError(
                "REFUSED: upstream transaction row has no observed filing"
            )
        transaction_rows.append(_transaction_row(report_row, filing))
    sorted_transactions = tuple(
        sorted(
            transaction_rows,
            key=lambda item: (
                item.accession_number,
                item.source_sha256,
                item.row_index,
                item.event_id,
            ),
        )
    )
    if len(sorted_transactions) != len(report.rows):
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: transaction inventory is not exhaustive"
        )

    filing_inventory_hash = hash_payload(
        [item.to_payload() for item in sorted_filings]
    )
    owner_inventory_hash = hash_payload(
        [item.to_payload() for item in sorted_owners]
    )
    transaction_inventory_hash = hash_payload(
        [item.to_payload() for item in sorted_transactions]
    )
    identity_payload = {
        "contract_version": FORM4_OBSERVED_IDENTITY_INVENTORY_VERSION,
        "builder_git_commit": builder_git_commit,
        "upstream_evidence_id": report.identity.upstream_evidence_id,
        "upstream_evidence_identity_hash": (
            report.identity.upstream_evidence_identity_hash
        ),
        "upstream_parsed_corpus_hash": (
            report.identity.upstream_parsed_corpus_hash
        ),
        "upstream_source_inventory_hash": (
            report.identity.upstream_source_inventory_hash
        ),
        "upstream_report_id": report.identity.report_id,
        "upstream_report_identity_hash": hash_payload(
            _contract_payload(report.identity)
        ),
        "upstream_report_row_inventory_hash": (
            report.identity.row_inventory_hash
        ),
        "filing_inventory_hash": filing_inventory_hash,
        "reporting_owner_inventory_hash": owner_inventory_hash,
        "transaction_inventory_hash": transaction_inventory_hash,
        "filing_count": len(sorted_filings),
        "amendment_count": sum(
            item.document_type == "4/A" for item in sorted_filings
        ),
        "reporting_owner_count": len(sorted_owners),
        "non_single_owner_filing_count": sum(
            item.reporting_owner_count != 1 for item in sorted_filings
        ),
        "transaction_count": len(sorted_transactions),
        "provisional_candidate_count": report.identity.candidate_count,
        "quarantine_count": report.identity.quarantine_count,
        "official_profile_compatibility_verified": False,
        "official_amendment_link_verified": False,
        "complete_amendment_coverage_verified": False,
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
    identity = Form4ObservedIdentityInventoryIdentity(
        **identity_payload,
        inventory_id=(
            "form4-observed-identity-inventory-"
            f"{hash_payload(identity_payload)[:16]}"
        ),
        _verified_factory_token=_VERIFIED_IDENTITY_FACTORY_TOKEN,
    )
    return Form4ObservedIdentityInventory(
        identity=identity,
        filings=sorted_filings,
        reporting_owners=sorted_owners,
        transactions=sorted_transactions,
        _verified_factory_token=_VERIFIED_INVENTORY_FACTORY_TOKEN,
    )


def build_form4_observed_identity_inventory(
    evidence: ProfileBoundForm4AmendmentEvidence,
    *,
    builder_git_commit: str,
) -> Form4ObservedIdentityInventory:
    """Build a deterministic inventory and normalize malformed-state errors."""

    try:
        return _build_form4_observed_identity_inventory(
            evidence,
            builder_git_commit=builder_git_commit,
        )
    except Form4ObservedIdentityInventoryError:
        raise
    except (
        AttributeError,
        ContractError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise Form4ObservedIdentityInventoryError(
            "REFUSED: observed identity input changed or is malformed"
        ) from exc


__all__ = [
    "FORM4_OBSERVED_IDENTITY_INVENTORY_VERSION",
    "Form4ObservedFilingIdentityRow",
    "Form4ObservedIdentityDisposition",
    "Form4ObservedIdentityInventory",
    "Form4ObservedIdentityInventoryError",
    "Form4ObservedIdentityInventoryIdentity",
    "Form4ObservedOwnerSetOutcome",
    "Form4ObservedReportingOwnerIdentityRow",
    "Form4ObservedTransactionIdentityRow",
    "MAX_FORM4_OBSERVED_IDENTITY_FILINGS",
    "MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS",
    "MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS",
    "MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS",
    "build_form4_observed_identity_inventory",
]
