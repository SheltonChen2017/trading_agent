"""Deterministic, zero-authority SEC entity grouping for bounded IB-2B.

This module consumes an exact, factory-created IB-2A observed inventory.  It
groups issuer and reporting-owner observations only by the exact SEC CIK that
was present in that inventory.  Every raw alias and relationship occurrence is
retained, and every upstream transaction produces exactly one attribution row.

The result is structural research plumbing, not resolved market identity.  It
does not select an amendment, map a ticker or share class, classify a security,
deduplicate transactions, aggregate lots, apply a value threshold, access an
outcome, or expose portfolio, QC, broker, scheduler, deployment, or trading
authority.  Ambiguous owner sets are named and quarantined without fan-out.
"""
from __future__ import annotations

import re
import threading
import weakref
from dataclasses import InitVar, dataclass, fields
from datetime import date, datetime, timezone
from enum import Enum

from data.hashing import hash_payload
from research.insider_buying.form4_amendment_reconciliation import (
    Form4VersionDisposition,
)
from research.insider_buying.form4_observed_identity_inventory import (
    FORM4_OBSERVED_IDENTITY_INVENTORY_VERSION,
    MAX_FORM4_OBSERVED_IDENTITY_FILINGS,
    MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS,
    MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS,
    MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
    Form4ObservedFilingIdentityRow,
    Form4ObservedIdentityDisposition,
    Form4ObservedIdentityInventory,
    Form4ObservedIdentityInventoryIdentity,
    Form4ObservedOwnerSetOutcome,
    Form4ObservedReportingOwnerIdentityRow,
    Form4ObservedTransactionIdentityRow,
    _is_factory_created_observed_identity_inventory,
    _matches_factory_created_observed_identity_inventory_fingerprint,
)
from research.insider_buying.form4_provisional_disposition_report import (
    Form4ProvisionalDisposition,
)


FORM4_SEC_ENTITY_GROUPING_VERSION = (
    "INSETF-IB2B-FORM4-SEC-ENTITY-GROUPING-v1"
)
MAX_FORM4_SEC_ENTITY_GROUPING_ISSUER_CANDIDATES = (
    MAX_FORM4_OBSERVED_IDENTITY_FILINGS
)
MAX_FORM4_SEC_ENTITY_GROUPING_OWNER_CANDIDATES = (
    MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS
)
MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_NODES = 4_000_000
MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_DEPTH = 32

_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_CIK_RE = re.compile(r"^[0-9]{10}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GROUPING_ID_RE = re.compile(
    r"^form4-sec-entity-grouping-(?P<hash_prefix>[0-9a-f]{16})$"
)

_ROW_FACTORY_TOKEN = object()
_CANDIDATE_FACTORY_TOKEN = object()
_IDENTITY_FACTORY_TOKEN = object()
_GROUPING_FACTORY_TOKEN = object()

_INVENTORY_FIELDS = (
    "identity",
    "filings",
    "reporting_owners",
    "transactions",
)
_INVENTORY_IDENTITY_FIELDS = (
    "contract_version",
    "builder_git_commit",
    "upstream_evidence_id",
    "upstream_evidence_identity_hash",
    "upstream_parsed_corpus_hash",
    "upstream_source_inventory_hash",
    "upstream_report_id",
    "upstream_report_identity_hash",
    "upstream_report_row_inventory_hash",
    "filing_inventory_hash",
    "reporting_owner_inventory_hash",
    "transaction_inventory_hash",
    "filing_count",
    "amendment_count",
    "reporting_owner_count",
    "non_single_owner_filing_count",
    "transaction_count",
    "provisional_candidate_count",
    "quarantine_count",
    "official_profile_compatibility_verified",
    "official_amendment_link_verified",
    "complete_amendment_coverage_verified",
    "point_in_time_issuer_identity_verified",
    "point_in_time_reporting_owner_identity_verified",
    "point_in_time_security_identity_verified",
    "point_in_time_transaction_identity_verified",
    "ordinary_equity_classification_verified",
    "canonical_filter_authorized",
    "lot_aggregation_authorized",
    "outcomes_authorized",
    "qc_execution_authorized",
    "deployment_authorized",
    "trading_authorized",
    "authorized_outcome_looks",
    "consumed_outcome_looks",
    "inventory_id",
)
_FILING_FIELDS = (
    "accession_number",
    "source_sha256",
    "document_type",
    "accepted_at_utc",
    "original_accession",
    "amends_accession",
    "primary_document_url",
    "issuer_cik",
    "issuer_name",
    "issuer_symbol_raw",
    "reporting_owner_count",
    "all_owner_relationships_complete",
    "owner_set_outcomes",
    "reporting_owner_observation_ids",
    "reporting_owner_inventory_hash",
    "version_disposition",
    "filing_observation_id",
)
_OWNER_FIELDS = (
    "accession_number",
    "source_sha256",
    "reporting_owner_index",
    "owner_cik",
    "owner_name",
    "is_director",
    "is_officer",
    "is_ten_percent_owner",
    "is_other",
    "officer_title",
    "relationship_complete",
    "owner_observation_id",
)
_TRANSACTION_FIELDS = (
    "accession_number",
    "source_sha256",
    "row_index",
    "event_id",
    "upstream_report_row_id",
    "transaction_payload_hash",
    "filing_observation_id",
    "security_title_raw",
    "transaction_date",
    "upstream_disposition",
    "identity_disposition",
    "resolved_security_identity",
    "point_in_time_security_identity_verified",
    "canonical_filter_authorized",
    "lot_aggregation_authorized",
    "transaction_observation_id",
)
_UPSTREAM_FIELD_MAP = {
    Form4ObservedIdentityInventory: _INVENTORY_FIELDS,
    Form4ObservedIdentityInventoryIdentity: _INVENTORY_IDENTITY_FIELDS,
    Form4ObservedFilingIdentityRow: _FILING_FIELDS,
    Form4ObservedReportingOwnerIdentityRow: _OWNER_FIELDS,
    Form4ObservedTransactionIdentityRow: _TRANSACTION_FIELDS,
}
_UPSTREAM_ENUM_TYPES = (
    Form4ObservedIdentityDisposition,
    Form4ObservedOwnerSetOutcome,
    Form4ProvisionalDisposition,
    Form4VersionDisposition,
)


class Form4SecEntityGroupingError(ValueError):
    """The bounded IB-2B grouping contract failed closed."""


class Form4OwnerAttributionOutcome(str, Enum):
    """Named owner attribution or quarantine reasons for one transaction."""

    SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED = (
        "single_complete_owner_cik_attributed"
    )
    MISSING_OWNER_SET_QUARANTINED = "missing_owner_set_quarantined"
    MULTIPLE_OWNER_SET_QUARANTINED = "multiple_owner_set_quarantined"
    DUPLICATE_OWNER_CIK_QUARANTINED = "duplicate_owner_cik_quarantined"
    INCOMPLETE_OWNER_RELATIONSHIP_QUARANTINED = (
        "incomplete_owner_relationship_quarantined"
    )


def _required_text(value: object, *, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise Form4SecEntityGroupingError(
            f"REFUSED: {label} must be exact non-empty text"
        )
    return value


def _optional_text(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, label=label)


def _sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise Form4SecEntityGroupingError(
            f"REFUSED: {label} must be lowercase SHA-256"
        )
    return value


def _accession(value: object, *, label: str) -> str:
    if type(value) is not str or _ACCESSION_RE.fullmatch(value) is None:
        raise Form4SecEntityGroupingError(
            f"REFUSED: {label} must be a canonical accession"
        )
    return value


def _cik(value: object, *, label: str) -> str:
    if type(value) is not str or _CIK_RE.fullmatch(value) is None:
        raise Form4SecEntityGroupingError(
            f"REFUSED: {label} must be a ten-digit SEC CIK"
        )
    return value


def _canonical_utc_text(value: object, *, label: str) -> str:
    if type(value) is not str:
        raise Form4SecEntityGroupingError(
            f"REFUSED: {label} must be canonical UTC text"
        )
    try:
        parsed = datetime.fromisoformat(value)
        canonical = parsed.astimezone(timezone.utc).isoformat(
            timespec="seconds"
        )
    except (OverflowError, TypeError, ValueError) as exc:
        raise Form4SecEntityGroupingError(
            f"REFUSED: {label} must be canonical UTC text"
        ) from exc
    if (
        parsed.utcoffset() is None
        or parsed.microsecond != 0
        or canonical != value
    ):
        raise Form4SecEntityGroupingError(
            f"REFUSED: {label} must be canonical UTC text"
        )
    return value


def _exact_state(value: object, expected_type: type, names: tuple[str, ...]) -> dict:
    if type(value) is not expected_type:
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory contains a non-exact contract type"
        )
    try:
        state = object.__getattribute__(value, "__dict__")
    except (AttributeError, TypeError) as exc:
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream contract state cannot be observed"
        ) from exc
    if type(state) is not dict or set(state) != set(names):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream dataclass instance state is not exact"
        )
    return state


@dataclass
class _ProjectionBudget:
    text_characters: int = 0
    nodes: int = 0
    active_ids: set[int] | None = None

    def __post_init__(self) -> None:
        if self.active_ids is None:
            self.active_ids = set()


def _project_upstream(
    value: object,
    *,
    budget: _ProjectionBudget | None = None,
    depth: int = 0,
) -> object:
    """Callback-free projection of the exact upstream IB-2A contract."""

    if budget is None:
        budget = _ProjectionBudget()
    if depth > MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_DEPTH:
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory exceeds the depth bound"
        )
    budget.nodes += 1
    if budget.nodes > MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_NODES:
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory exceeds the node bound"
        )
    value_type = type(value)
    if any(value_type is enum_type for enum_type in _UPSTREAM_ENUM_TYPES):
        return _project_upstream(value.value, budget=budget, depth=depth + 1)
    if value_type is date:
        return value.isoformat()
    if value_type is str:
        budget.text_characters += len(value)
        if budget.text_characters > MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS:
            raise Form4SecEntityGroupingError(
                "REFUSED: upstream inventory exceeds the text bound"
            )
        return value
    if value is None or value_type is bool or value_type is int:
        return value
    names = next(
        (
            field_names
            for contract_type, field_names in _UPSTREAM_FIELD_MAP.items()
            if value_type is contract_type
        ),
        None,
    )
    if value_type is tuple or names is not None:
        active_ids = budget.active_ids
        assert active_ids is not None
        value_id = id(value)
        if value_id in active_ids:
            raise Form4SecEntityGroupingError(
                "REFUSED: upstream inventory contains a cycle"
            )
        active_ids.add(value_id)
        try:
            if value_type is tuple:
                return [
                    _project_upstream(
                        item,
                        budget=budget,
                        depth=depth + 1,
                    )
                    for item in value
                ]
            state = _exact_state(value, value_type, names)
            return {
                name: _project_upstream(
                    state[name],
                    budget=budget,
                    depth=depth + 1,
                )
                for name in names
            }
        finally:
            active_ids.remove(value_id)
    raise Form4SecEntityGroupingError(
        "REFUSED: upstream inventory contains an unsupported value"
    )


def _upstream_fingerprint(inventory: Form4ObservedIdentityInventory) -> str:
    try:
        return hash_payload(_project_upstream(inventory))
    except Form4SecEntityGroupingError:
        raise
    except (AttributeError, OverflowError, TypeError, ValueError) as exc:
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory fingerprint failed"
        ) from exc


def _owner_set_outcomes(
    owner_count: int,
    all_complete: bool,
) -> tuple[Form4ObservedOwnerSetOutcome, ...]:
    if owner_count == 1 and all_complete:
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
    if owner_count > 0 and not all_complete:
        outcomes.append(
            Form4ObservedOwnerSetOutcome.INCOMPLETE_OWNER_RELATIONSHIP_QUARANTINED
        )
    return tuple(outcomes)


def _identity_disposition(
    upstream: Form4ProvisionalDisposition,
) -> Form4ObservedIdentityDisposition:
    if upstream is Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE:
        return Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE
    if upstream is Form4ProvisionalDisposition.PROVISIONAL_QUARANTINE:
        return Form4ObservedIdentityDisposition.UNRESOLVED_QUARANTINE
    raise Form4SecEntityGroupingError(
        "REFUSED: upstream transaction disposition is unsupported"
    )


@dataclass(frozen=True)
class Form4SecIssuerObservation:
    """One as-filed issuer alias observation; amendments remain distinct."""

    accession_number: str
    source_sha256: str
    filing_observation_id: str
    document_type: str
    accepted_at_utc: str
    original_accession: str
    amends_accession: str | None
    primary_document_url: str
    issuer_cik: str
    issuer_name: str
    issuer_symbol_raw: str | None
    issuer_observation_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _ROW_FACTORY_TOKEN:
            raise Form4SecEntityGroupingError(
                "REFUSED: issuer observation must be factory-created"
            )
        _accession(self.accession_number, label="issuer accession")
        _sha256(self.source_sha256, label="issuer source hash")
        _sha256(self.filing_observation_id, label="filing observation ID")
        if type(self.document_type) is not str or self.document_type not in {"4", "4/A"}:
            raise Form4SecEntityGroupingError(
                "REFUSED: issuer observation document type is invalid"
            )
        _canonical_utc_text(self.accepted_at_utc, label="issuer acceptance")
        _accession(self.original_accession, label="issuer original accession")
        if self.amends_accession is not None:
            _accession(self.amends_accession, label="issuer amended accession")
        _required_text(self.primary_document_url, label="primary document URL")
        if any(character.isspace() for character in self.primary_document_url):
            raise Form4SecEntityGroupingError(
                "REFUSED: primary document URL contains whitespace"
            )
        _cik(self.issuer_cik, label="issuer CIK")
        _required_text(self.issuer_name, label="issuer name")
        _optional_text(self.issuer_symbol_raw, label="issuer symbol")
        if self.document_type == "4":
            valid_lineage = (
                self.amends_accession is None
                and self.original_accession == self.accession_number
            )
        else:
            valid_lineage = (
                self.amends_accession is not None
                and self.original_accession == self.amends_accession
                and self.original_accession != self.accession_number
            )
        if not valid_lineage:
            raise Form4SecEntityGroupingError(
                "REFUSED: issuer observation lineage is inconsistent"
            )
        _sha256(self.issuer_observation_id, label="issuer observation ID")
        if self.issuer_observation_id != hash_payload(
            _issuer_observation_payload(self)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: issuer observation ID is invalid"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            **_issuer_observation_payload(self),
            "issuer_observation_id": self.issuer_observation_id,
        }


def _issuer_observation_payload(
    item: Form4SecIssuerObservation,
) -> dict[str, object]:
    return {
        "accession_number": item.accession_number,
        "source_sha256": item.source_sha256,
        "filing_observation_id": item.filing_observation_id,
        "document_type": item.document_type,
        "accepted_at_utc": item.accepted_at_utc,
        "original_accession": item.original_accession,
        "amends_accession": item.amends_accession,
        "primary_document_url": item.primary_document_url,
        "issuer_cik": item.issuer_cik,
        "issuer_name": item.issuer_name,
        "issuer_symbol_raw": item.issuer_symbol_raw,
    }


@dataclass(frozen=True)
class Form4SecIssuerIdentityCandidate:
    """SEC-CIK grouping candidate retaining every issuer observation."""

    issuer_cik: str
    observations: tuple[Form4SecIssuerObservation, ...]
    observation_inventory_hash: str
    issuer_candidate_id: str
    point_in_time_issuer_identity_verified: bool
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _CANDIDATE_FACTORY_TOKEN:
            raise Form4SecEntityGroupingError(
                "REFUSED: issuer candidate must be factory-created"
            )
        _cik(self.issuer_cik, label="issuer candidate CIK")
        if (
            type(self.observations) is not tuple
            or not self.observations
            or len(self.observations) > MAX_FORM4_OBSERVED_IDENTITY_FILINGS
            or any(type(item) is not Form4SecIssuerObservation for item in self.observations)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: issuer candidate observations are invalid"
            )
        for item in self.observations:
            Form4SecIssuerObservation.__post_init__(item, _ROW_FACTORY_TOKEN)
        keys = tuple(
            (
                item.accepted_at_utc,
                item.accession_number,
                item.source_sha256,
            )
            for item in self.observations
        )
        if (
            any(item.issuer_cik != self.issuer_cik for item in self.observations)
            or keys != tuple(sorted(keys))
            or len(set(keys)) != len(keys)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: issuer candidate grouping is inconsistent"
            )
        _sha256(self.observation_inventory_hash, label="issuer observation hash")
        expected_hash = hash_payload(
            [item.to_payload() for item in self.observations]
        )
        if (
            self.observation_inventory_hash != expected_hash
            or self.point_in_time_issuer_identity_verified is not False
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: issuer candidate claims invalid identity"
            )
        _sha256(self.issuer_candidate_id, label="issuer candidate ID")
        if self.issuer_candidate_id != hash_payload(
            _issuer_candidate_payload(self)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: issuer candidate ID is invalid"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            **_issuer_candidate_payload(self),
            "issuer_candidate_id": self.issuer_candidate_id,
        }


def _issuer_candidate_payload(
    item: Form4SecIssuerIdentityCandidate,
) -> dict[str, object]:
    return {
        "issuer_cik": item.issuer_cik,
        "observations": [observation.to_payload() for observation in item.observations],
        "observation_inventory_hash": item.observation_inventory_hash,
        "point_in_time_issuer_identity_verified": False,
    }


@dataclass(frozen=True)
class Form4SecReportingOwnerObservation:
    """One raw reporting-owner alias and relationship occurrence."""

    accession_number: str
    source_sha256: str
    filing_observation_id: str
    accepted_at_utc: str
    reporting_owner_index: int
    upstream_owner_observation_id: str
    owner_cik: str
    owner_name: str
    is_director: bool | None
    is_officer: bool | None
    is_ten_percent_owner: bool | None
    is_other: bool | None
    officer_title: str | None
    relationship_complete: bool
    owner_observation_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _ROW_FACTORY_TOKEN:
            raise Form4SecEntityGroupingError(
                "REFUSED: owner observation must be factory-created"
            )
        _accession(self.accession_number, label="owner accession")
        _sha256(self.source_sha256, label="owner source hash")
        _sha256(self.filing_observation_id, label="filing observation ID")
        _canonical_utc_text(self.accepted_at_utc, label="owner acceptance")
        if type(self.reporting_owner_index) is not int or self.reporting_owner_index < 0:
            raise Form4SecEntityGroupingError(
                "REFUSED: owner observation index is invalid"
            )
        _sha256(
            self.upstream_owner_observation_id,
            label="upstream owner observation ID",
        )
        _cik(self.owner_cik, label="owner CIK")
        _required_text(self.owner_name, label="owner name")
        _optional_text(self.officer_title, label="officer title")
        flags = (
            self.is_director,
            self.is_officer,
            self.is_ten_percent_owner,
            self.is_other,
        )
        if any(value is not None and type(value) is not bool for value in flags):
            raise Form4SecEntityGroupingError(
                "REFUSED: owner relationship flags are invalid"
            )
        if (
            type(self.relationship_complete) is not bool
            or self.relationship_complete != all(value is not None for value in flags)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: owner relationship completeness is inconsistent"
            )
        _sha256(self.owner_observation_id, label="owner observation ID")
        if self.owner_observation_id != hash_payload(
            _owner_observation_payload(self)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: owner observation ID is invalid"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            **_owner_observation_payload(self),
            "owner_observation_id": self.owner_observation_id,
        }


def _owner_observation_payload(
    item: Form4SecReportingOwnerObservation,
) -> dict[str, object]:
    return {
        "accession_number": item.accession_number,
        "source_sha256": item.source_sha256,
        "filing_observation_id": item.filing_observation_id,
        "accepted_at_utc": item.accepted_at_utc,
        "reporting_owner_index": item.reporting_owner_index,
        "upstream_owner_observation_id": item.upstream_owner_observation_id,
        "owner_cik": item.owner_cik,
        "owner_name": item.owner_name,
        "is_director": item.is_director,
        "is_officer": item.is_officer,
        "is_ten_percent_owner": item.is_ten_percent_owner,
        "is_other": item.is_other,
        "officer_title": item.officer_title,
        "relationship_complete": item.relationship_complete,
    }


@dataclass(frozen=True)
class Form4SecReportingOwnerIdentityCandidate:
    """Exact-owner-CIK candidate retaining every raw observation."""

    owner_cik: str
    observations: tuple[Form4SecReportingOwnerObservation, ...]
    observation_inventory_hash: str
    owner_candidate_id: str
    point_in_time_reporting_owner_identity_verified: bool
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _CANDIDATE_FACTORY_TOKEN:
            raise Form4SecEntityGroupingError(
                "REFUSED: owner candidate must be factory-created"
            )
        _cik(self.owner_cik, label="owner candidate CIK")
        if (
            type(self.observations) is not tuple
            or not self.observations
            or len(self.observations) > MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS
            or any(type(item) is not Form4SecReportingOwnerObservation for item in self.observations)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: owner candidate observations are invalid"
            )
        for item in self.observations:
            Form4SecReportingOwnerObservation.__post_init__(item, _ROW_FACTORY_TOKEN)
        keys = tuple(
            (
                item.accepted_at_utc,
                item.accession_number,
                item.source_sha256,
                item.reporting_owner_index,
            )
            for item in self.observations
        )
        if (
            any(item.owner_cik != self.owner_cik for item in self.observations)
            or keys != tuple(sorted(keys))
            or len(set(keys)) != len(keys)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: owner candidate grouping is inconsistent"
            )
        _sha256(self.observation_inventory_hash, label="owner observation hash")
        expected_hash = hash_payload(
            [item.to_payload() for item in self.observations]
        )
        if (
            self.observation_inventory_hash != expected_hash
            or self.point_in_time_reporting_owner_identity_verified is not False
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: owner candidate claims invalid identity"
            )
        _sha256(self.owner_candidate_id, label="owner candidate ID")
        if self.owner_candidate_id != hash_payload(
            _owner_candidate_payload(self)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: owner candidate ID is invalid"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            **_owner_candidate_payload(self),
            "owner_candidate_id": self.owner_candidate_id,
        }


def _owner_candidate_payload(
    item: Form4SecReportingOwnerIdentityCandidate,
) -> dict[str, object]:
    return {
        "owner_cik": item.owner_cik,
        "observations": [observation.to_payload() for observation in item.observations],
        "observation_inventory_hash": item.observation_inventory_hash,
        "point_in_time_reporting_owner_identity_verified": False,
    }


@dataclass(frozen=True)
class Form4SecTransactionAttributionRow:
    """One upstream transaction with a fail-closed SEC-owner attribution."""

    accession_number: str
    source_sha256: str
    row_index: int
    event_id: str
    filing_observation_id: str
    upstream_transaction_observation_id: str
    upstream_report_row_id: str
    transaction_payload_hash: str
    security_title_raw: str | None
    transaction_date: date | None
    upstream_disposition: Form4ProvisionalDisposition
    identity_disposition: Form4ObservedIdentityDisposition
    issuer_candidate_id: str
    attributed_owner_cik: str | None
    attributed_owner_candidate_id: str | None
    owner_attribution_outcomes: tuple[Form4OwnerAttributionOutcome, ...]
    point_in_time_issuer_identity_verified: bool
    point_in_time_reporting_owner_identity_verified: bool
    point_in_time_security_identity_verified: bool
    point_in_time_transaction_identity_verified: bool
    canonical_filter_authorized: bool
    lot_aggregation_authorized: bool
    transaction_attribution_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _ROW_FACTORY_TOKEN:
            raise Form4SecEntityGroupingError(
                "REFUSED: transaction attribution must be factory-created"
            )
        _accession(self.accession_number, label="transaction accession")
        _sha256(self.source_sha256, label="transaction source hash")
        if type(self.row_index) is not int or self.row_index < 0:
            raise Form4SecEntityGroupingError(
                "REFUSED: transaction attribution row index is invalid"
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
            ("issuer candidate ID", self.issuer_candidate_id),
            ("transaction attribution ID", self.transaction_attribution_id),
        ):
            _sha256(value, label=label)
        _optional_text(self.security_title_raw, label="security title")
        if self.transaction_date is not None and type(self.transaction_date) is not date:
            raise Form4SecEntityGroupingError(
                "REFUSED: transaction attribution date is invalid"
            )
        if (
            type(self.upstream_disposition) is not Form4ProvisionalDisposition
            or type(self.identity_disposition) is not Form4ObservedIdentityDisposition
            or self.identity_disposition
            is not _identity_disposition(self.upstream_disposition)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: transaction disposition binding is invalid"
            )
        if (
            type(self.owner_attribution_outcomes) is not tuple
            or not self.owner_attribution_outcomes
            or any(
                type(item) is not Form4OwnerAttributionOutcome
                for item in self.owner_attribution_outcomes
            )
            or len(set(self.owner_attribution_outcomes))
            != len(self.owner_attribution_outcomes)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: owner attribution outcomes are invalid"
            )
        is_attributed = self.owner_attribution_outcomes == (
            Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,
        )
        if is_attributed:
            _cik(self.attributed_owner_cik, label="attributed owner CIK")
            _sha256(
                self.attributed_owner_candidate_id,
                label="attributed owner candidate ID",
            )
        elif (
            self.attributed_owner_cik is not None
            or self.attributed_owner_candidate_id is not None
            or Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED
            in self.owner_attribution_outcomes
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: quarantined transaction carries an owner attribution"
            )
        authority = (
            self.point_in_time_issuer_identity_verified,
            self.point_in_time_reporting_owner_identity_verified,
            self.point_in_time_security_identity_verified,
            self.point_in_time_transaction_identity_verified,
            self.canonical_filter_authorized,
            self.lot_aggregation_authorized,
        )
        if any(value is not False for value in authority):
            raise Form4SecEntityGroupingError(
                "REFUSED: transaction attribution claims downstream authority"
            )
        if self.transaction_attribution_id != hash_payload(
            _transaction_attribution_payload(self)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: transaction attribution ID is invalid"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            **_transaction_attribution_payload(self),
            "transaction_attribution_id": self.transaction_attribution_id,
        }


def _transaction_attribution_payload(
    item: Form4SecTransactionAttributionRow,
) -> dict[str, object]:
    return {
        "accession_number": item.accession_number,
        "source_sha256": item.source_sha256,
        "row_index": item.row_index,
        "event_id": item.event_id,
        "filing_observation_id": item.filing_observation_id,
        "upstream_transaction_observation_id": (
            item.upstream_transaction_observation_id
        ),
        "upstream_report_row_id": item.upstream_report_row_id,
        "transaction_payload_hash": item.transaction_payload_hash,
        "security_title_raw": item.security_title_raw,
        "transaction_date": (
            None
            if item.transaction_date is None
            else item.transaction_date.isoformat()
        ),
        "upstream_disposition": item.upstream_disposition.value,
        "identity_disposition": item.identity_disposition.value,
        "issuer_candidate_id": item.issuer_candidate_id,
        "attributed_owner_cik": item.attributed_owner_cik,
        "attributed_owner_candidate_id": item.attributed_owner_candidate_id,
        "owner_attribution_outcomes": [
            outcome.value for outcome in item.owner_attribution_outcomes
        ],
        "point_in_time_issuer_identity_verified": False,
        "point_in_time_reporting_owner_identity_verified": False,
        "point_in_time_security_identity_verified": False,
        "point_in_time_transaction_identity_verified": False,
        "canonical_filter_authorized": False,
        "lot_aggregation_authorized": False,
    }


@dataclass(frozen=True)
class Form4SecEntityGroupingIdentity:
    """Hash-bound identity for a complete grouping of one IB-2A inventory."""

    contract_version: str
    builder_git_commit: str
    upstream_inventory_id: str
    upstream_inventory_identity_hash: str
    upstream_inventory_observation_hash: str
    upstream_filing_inventory_hash: str
    upstream_reporting_owner_inventory_hash: str
    upstream_transaction_inventory_hash: str
    issuer_candidate_inventory_hash: str
    reporting_owner_candidate_inventory_hash: str
    transaction_attribution_inventory_hash: str
    filing_observation_count: int
    issuer_candidate_count: int
    reporting_owner_observation_count: int
    reporting_owner_candidate_count: int
    transaction_attribution_count: int
    single_complete_owner_attribution_count: int
    quarantined_transaction_count: int
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
    grouping_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _IDENTITY_FACTORY_TOKEN:
            raise Form4SecEntityGroupingError(
                "REFUSED: grouping identity must be factory-created"
            )
        if (
            type(self.contract_version) is not str
            or self.contract_version != FORM4_SEC_ENTITY_GROUPING_VERSION
            or type(self.builder_git_commit) is not str
            or _GIT_COMMIT_RE.fullmatch(self.builder_git_commit) is None
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: grouping identity version or builder is invalid"
            )
        _required_text(self.upstream_inventory_id, label="upstream inventory ID")
        for label, value in (
            ("upstream inventory identity hash", self.upstream_inventory_identity_hash),
            ("upstream inventory observation hash", self.upstream_inventory_observation_hash),
            ("upstream filing inventory hash", self.upstream_filing_inventory_hash),
            (
                "upstream reporting owner inventory hash",
                self.upstream_reporting_owner_inventory_hash,
            ),
            ("upstream transaction inventory hash", self.upstream_transaction_inventory_hash),
            ("issuer candidate inventory hash", self.issuer_candidate_inventory_hash),
            (
                "reporting owner candidate inventory hash",
                self.reporting_owner_candidate_inventory_hash,
            ),
            (
                "transaction attribution inventory hash",
                self.transaction_attribution_inventory_hash,
            ),
        ):
            _sha256(value, label=label)
        counts_and_caps = (
            (self.filing_observation_count, MAX_FORM4_OBSERVED_IDENTITY_FILINGS),
            (
                self.issuer_candidate_count,
                MAX_FORM4_SEC_ENTITY_GROUPING_ISSUER_CANDIDATES,
            ),
            (
                self.reporting_owner_observation_count,
                MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS,
            ),
            (
                self.reporting_owner_candidate_count,
                MAX_FORM4_SEC_ENTITY_GROUPING_OWNER_CANDIDATES,
            ),
            (
                self.transaction_attribution_count,
                MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
            ),
            (
                self.single_complete_owner_attribution_count,
                MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
            ),
            (
                self.quarantined_transaction_count,
                MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
            ),
        )
        if (
            any(
                type(value) is not int or not 0 <= value <= cap
                for value, cap in counts_and_caps
            )
            or self.issuer_candidate_count > self.filing_observation_count
            or self.reporting_owner_candidate_count
            > self.reporting_owner_observation_count
            or self.single_complete_owner_attribution_count
            + self.quarantined_transaction_count
            != self.transaction_attribution_count
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: grouping identity counts are invalid"
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
            raise Form4SecEntityGroupingError(
                "REFUSED: grouping identity claims authority"
            )
        match = (
            _GROUPING_ID_RE.fullmatch(self.grouping_id)
            if type(self.grouping_id) is str
            else None
        )
        if (
            match is None
            or match.group("hash_prefix")
            != hash_payload(_grouping_identity_payload(self))[:16]
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: grouping ID is invalid"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            **_grouping_identity_payload(self),
            "grouping_id": self.grouping_id,
        }


def _grouping_identity_payload(
    identity: Form4SecEntityGroupingIdentity,
) -> dict[str, object]:
    return {
        "contract_version": identity.contract_version,
        "builder_git_commit": identity.builder_git_commit,
        "upstream_inventory_id": identity.upstream_inventory_id,
        "upstream_inventory_identity_hash": (
            identity.upstream_inventory_identity_hash
        ),
        "upstream_inventory_observation_hash": (
            identity.upstream_inventory_observation_hash
        ),
        "upstream_filing_inventory_hash": (
            identity.upstream_filing_inventory_hash
        ),
        "upstream_reporting_owner_inventory_hash": (
            identity.upstream_reporting_owner_inventory_hash
        ),
        "upstream_transaction_inventory_hash": (
            identity.upstream_transaction_inventory_hash
        ),
        "issuer_candidate_inventory_hash": (
            identity.issuer_candidate_inventory_hash
        ),
        "reporting_owner_candidate_inventory_hash": (
            identity.reporting_owner_candidate_inventory_hash
        ),
        "transaction_attribution_inventory_hash": (
            identity.transaction_attribution_inventory_hash
        ),
        "filing_observation_count": identity.filing_observation_count,
        "issuer_candidate_count": identity.issuer_candidate_count,
        "reporting_owner_observation_count": (
            identity.reporting_owner_observation_count
        ),
        "reporting_owner_candidate_count": (
            identity.reporting_owner_candidate_count
        ),
        "transaction_attribution_count": identity.transaction_attribution_count,
        "single_complete_owner_attribution_count": (
            identity.single_complete_owner_attribution_count
        ),
        "quarantined_transaction_count": identity.quarantined_transaction_count,
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


def _owner_attribution_outcomes(
    owner_ciks: tuple[str, ...],
    relationships_complete: tuple[bool, ...],
) -> tuple[Form4OwnerAttributionOutcome, ...]:
    if (
        type(owner_ciks) is not tuple
        or type(relationships_complete) is not tuple
        or len(owner_ciks) != len(relationships_complete)
        or any(type(item) is not str for item in owner_ciks)
        or any(type(item) is not bool for item in relationships_complete)
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: primitive owner state is invalid"
        )
    if len(owner_ciks) == 1 and relationships_complete[0]:
        return (
            Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,
        )
    if not owner_ciks:
        return (Form4OwnerAttributionOutcome.MISSING_OWNER_SET_QUARANTINED,)
    outcomes = [
        Form4OwnerAttributionOutcome.MULTIPLE_OWNER_SET_QUARANTINED
    ] if len(owner_ciks) > 1 else []
    if len(set(owner_ciks)) != len(owner_ciks):
        outcomes.append(
            Form4OwnerAttributionOutcome.DUPLICATE_OWNER_CIK_QUARANTINED
        )
    if any(not item for item in relationships_complete):
        outcomes.append(
            Form4OwnerAttributionOutcome.INCOMPLETE_OWNER_RELATIONSHIP_QUARANTINED
        )
    return tuple(outcomes)


@dataclass(frozen=True)
class Form4SecEntityGrouping:
    """Factory-created grouping exhaustive for one exact IB-2A inventory."""

    identity: Form4SecEntityGroupingIdentity
    issuer_candidates: tuple[Form4SecIssuerIdentityCandidate, ...]
    reporting_owner_candidates: tuple[
        Form4SecReportingOwnerIdentityCandidate, ...
    ]
    transaction_attributions: tuple[Form4SecTransactionAttributionRow, ...]
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _GROUPING_FACTORY_TOKEN:
            raise Form4SecEntityGroupingError(
                "REFUSED: SEC entity grouping must be factory-created"
            )
        if (
            type(self.identity) is not Form4SecEntityGroupingIdentity
            or type(self.issuer_candidates) is not tuple
            or type(self.reporting_owner_candidates) is not tuple
            or type(self.transaction_attributions) is not tuple
            or any(
                type(item) is not Form4SecIssuerIdentityCandidate
                for item in self.issuer_candidates
            )
            or any(
                type(item) is not Form4SecReportingOwnerIdentityCandidate
                for item in self.reporting_owner_candidates
            )
            or any(
                type(item) is not Form4SecTransactionAttributionRow
                for item in self.transaction_attributions
            )
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: SEC entity grouping state is invalid"
            )
        Form4SecEntityGroupingIdentity.__post_init__(
            self.identity,
            _IDENTITY_FACTORY_TOKEN,
        )
        for item in self.issuer_candidates:
            Form4SecIssuerIdentityCandidate.__post_init__(
                item,
                _CANDIDATE_FACTORY_TOKEN,
            )
        for item in self.reporting_owner_candidates:
            Form4SecReportingOwnerIdentityCandidate.__post_init__(
                item,
                _CANDIDATE_FACTORY_TOKEN,
            )
        for item in self.transaction_attributions:
            Form4SecTransactionAttributionRow.__post_init__(
                item,
                _ROW_FACTORY_TOKEN,
            )
        issuer_ciks = tuple(item.issuer_cik for item in self.issuer_candidates)
        owner_ciks = tuple(
            item.owner_cik for item in self.reporting_owner_candidates
        )
        transaction_keys = tuple(
            (
                item.accession_number,
                item.source_sha256,
                item.row_index,
                item.event_id,
            )
            for item in self.transaction_attributions
        )
        transaction_filing_row_keys = tuple(
            (item.accession_number, item.source_sha256, item.row_index)
            for item in self.transaction_attributions
        )
        transaction_source_row_keys = tuple(
            (item.accession_number, item.row_index)
            for item in self.transaction_attributions
        )
        if (
            issuer_ciks != tuple(sorted(issuer_ciks))
            or owner_ciks != tuple(sorted(owner_ciks))
            or len(set(issuer_ciks)) != len(issuer_ciks)
            or len(set(owner_ciks)) != len(owner_ciks)
            or transaction_keys != tuple(sorted(transaction_keys))
            or len(set(transaction_keys)) != len(transaction_keys)
            or len(set(transaction_filing_row_keys))
            != len(transaction_filing_row_keys)
            or len(set(transaction_source_row_keys))
            != len(transaction_source_row_keys)
            or len(
                {
                    item.upstream_transaction_observation_id
                    for item in self.transaction_attributions
                }
            )
            != len(self.transaction_attributions)
            or len(
                {item.upstream_report_row_id for item in self.transaction_attributions}
            )
            != len(self.transaction_attributions)
            or len(
                {item.transaction_payload_hash for item in self.transaction_attributions}
            )
            != len(self.transaction_attributions)
            or len(
                {item.transaction_attribution_id for item in self.transaction_attributions}
            )
            != len(self.transaction_attributions)
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: grouping order or uniqueness is invalid"
            )

        issuer_by_filing: dict[str, Form4SecIssuerIdentityCandidate] = {}
        issuer_observation_by_filing: dict[
            str,
            Form4SecIssuerObservation,
        ] = {}
        issuer_observation_by_accession: dict[
            str,
            Form4SecIssuerObservation,
        ] = {}
        acceptance_by_original: dict[str, set[str]] = {}
        filing_keys_seen: set[tuple[str, str]] = set()
        issuer_observation_count = 0
        for candidate in self.issuer_candidates:
            issuer_observation_count += len(candidate.observations)
            for observation in candidate.observations:
                filing_key = (
                    observation.accession_number,
                    observation.source_sha256,
                )
                if (
                    observation.filing_observation_id in issuer_by_filing
                    or observation.accession_number
                    in issuer_observation_by_accession
                    or filing_key in filing_keys_seen
                ):
                    raise Form4SecEntityGroupingError(
                        "REFUSED: filing appears in multiple issuer candidates"
                    )
                issuer_by_filing[observation.filing_observation_id] = candidate
                issuer_observation_by_filing[
                    observation.filing_observation_id
                ] = observation
                issuer_observation_by_accession[
                    observation.accession_number
                ] = observation
                filing_keys_seen.add(filing_key)
                acceptance_times = acceptance_by_original.setdefault(
                    observation.original_accession,
                    set(),
                )
                if observation.accepted_at_utc in acceptance_times:
                    raise Form4SecEntityGroupingError(
                        "REFUSED: issuer lineage acceptance is ambiguous"
                    )
                acceptance_times.add(observation.accepted_at_utc)
        for observation in issuer_observation_by_filing.values():
            if observation.document_type == "4":
                continue
            original = issuer_observation_by_accession.get(
                observation.original_accession
            )
            if (
                original is None
                or original.document_type != "4"
                or original.amends_accession is not None
                or original.original_accession != original.accession_number
                or original.issuer_cik != observation.issuer_cik
                or original.accepted_at_utc >= observation.accepted_at_utc
            ):
                raise Form4SecEntityGroupingError(
                    "REFUSED: issuer amendment-to-original binding is invalid"
                )

        owners_by_filing: dict[
            str,
            list[Form4SecReportingOwnerObservation],
        ] = {filing_id: [] for filing_id in issuer_by_filing}
        owner_observation_count = 0
        owner_keys_seen: set[tuple[str, str, int]] = set()
        upstream_owner_ids_seen: set[str] = set()
        output_owner_ids_seen: set[str] = set()
        for candidate in self.reporting_owner_candidates:
            owner_observation_count += len(candidate.observations)
            for observation in candidate.observations:
                owner_key = (
                    observation.accession_number,
                    observation.source_sha256,
                    observation.reporting_owner_index,
                )
                owners = owners_by_filing.get(observation.filing_observation_id)
                issuer_observation = issuer_observation_by_filing.get(
                    observation.filing_observation_id
                )
                if (
                    owners is None
                    or issuer_observation is None
                    or observation.accession_number
                    != issuer_observation.accession_number
                    or observation.source_sha256
                    != issuer_observation.source_sha256
                    or observation.accepted_at_utc
                    != issuer_observation.accepted_at_utc
                    or owner_key in owner_keys_seen
                    or observation.upstream_owner_observation_id
                    in upstream_owner_ids_seen
                    or observation.owner_observation_id in output_owner_ids_seen
                ):
                    raise Form4SecEntityGroupingError(
                        "REFUSED: owner observation-to-filing binding is invalid"
                    )
                owners.append(observation)
                owner_keys_seen.add(owner_key)
                upstream_owner_ids_seen.add(
                    observation.upstream_owner_observation_id
                )
                output_owner_ids_seen.add(observation.owner_observation_id)
        normalized_owners_by_filing: dict[
            str,
            tuple[Form4SecReportingOwnerObservation, ...],
        ] = {}
        for filing_id, observations in owners_by_filing.items():
            ordered = tuple(
                sorted(observations, key=lambda item: item.reporting_owner_index)
            )
            if tuple(item.reporting_owner_index for item in ordered) != tuple(
                range(len(ordered))
            ):
                raise Form4SecEntityGroupingError(
                    "REFUSED: owner observations are not contiguous per filing"
                )
            normalized_owners_by_filing[filing_id] = ordered

        owner_candidates_by_cik = {
            item.owner_cik: item for item in self.reporting_owner_candidates
        }
        transactions_by_filing: dict[
            str,
            list[Form4SecTransactionAttributionRow],
        ] = {filing_id: [] for filing_id in issuer_by_filing}
        for transaction in self.transaction_attributions:
            issuer_candidate = issuer_by_filing.get(
                transaction.filing_observation_id
            )
            issuer_observation = issuer_observation_by_filing.get(
                transaction.filing_observation_id
            )
            if (
                issuer_candidate is None
                or issuer_observation is None
                or transaction.issuer_candidate_id
                != issuer_candidate.issuer_candidate_id
                or transaction.accession_number
                != issuer_observation.accession_number
                or transaction.source_sha256
                != issuer_observation.source_sha256
            ):
                raise Form4SecEntityGroupingError(
                    "REFUSED: transaction-to-issuer candidate binding is invalid"
                )
            filing_owners = normalized_owners_by_filing[
                transaction.filing_observation_id
            ]
            expected_outcomes = _owner_attribution_outcomes(
                tuple(item.owner_cik for item in filing_owners),
                tuple(item.relationship_complete for item in filing_owners),
            )
            if transaction.owner_attribution_outcomes != expected_outcomes:
                raise Form4SecEntityGroupingError(
                    "REFUSED: transaction owner attribution is inconsistent"
                )
            if expected_outcomes == (
                Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,
            ):
                owner = normalized_owners_by_filing[
                    transaction.filing_observation_id
                ][0]
                owner_candidate = owner_candidates_by_cik.get(owner.owner_cik)
                if (
                    owner_candidate is None
                    or transaction.attributed_owner_cik != owner.owner_cik
                    or transaction.attributed_owner_candidate_id
                    != owner_candidate.owner_candidate_id
                ):
                    raise Form4SecEntityGroupingError(
                        "REFUSED: single-owner candidate attribution is invalid"
                    )
            transactions_by_filing[transaction.filing_observation_id].append(
                transaction
            )
        if any(
            tuple(item.row_index for item in transactions)
            != tuple(range(len(transactions)))
            for transactions in transactions_by_filing.values()
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: transaction rows are not contiguous per filing"
            )

        single_count = sum(
            item.owner_attribution_outcomes
            == (
                Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,
            )
            for item in self.transaction_attributions
        )
        if (
            self.identity.filing_observation_count != issuer_observation_count
            or self.identity.issuer_candidate_count != len(self.issuer_candidates)
            or self.identity.reporting_owner_observation_count
            != owner_observation_count
            or self.identity.reporting_owner_candidate_count
            != len(self.reporting_owner_candidates)
            or self.identity.transaction_attribution_count
            != len(self.transaction_attributions)
            or self.identity.single_complete_owner_attribution_count
            != single_count
            or self.identity.quarantined_transaction_count
            != len(self.transaction_attributions) - single_count
            or self.identity.issuer_candidate_inventory_hash
            != hash_payload([item.to_payload() for item in self.issuer_candidates])
            or self.identity.reporting_owner_candidate_inventory_hash
            != hash_payload(
                [item.to_payload() for item in self.reporting_owner_candidates]
            )
            or self.identity.transaction_attribution_inventory_hash
            != hash_payload(
                [item.to_payload() for item in self.transaction_attributions]
            )
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: grouping counts or hashes are inconsistent"
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
            "issuer_candidates": [
                item.to_payload() for item in self.issuer_candidates
            ],
            "reporting_owner_candidates": [
                item.to_payload() for item in self.reporting_owner_candidates
            ],
            "transaction_attributions": [
                item.to_payload() for item in self.transaction_attributions
            ],
        }


# IB-2B is an in-memory boundary.  Downstream structural stages must be able
# to distinguish the exact factory result from a coherent object.__new__ clone
# or a later object.__setattr__ mutation.  This process-local weak seal is not
# a signature or persisted/cross-process attestation.
_GROUPING_PROVENANCE_DATACLASS_TYPES = (
    Form4SecEntityGrouping,
    Form4SecEntityGroupingIdentity,
    Form4SecIssuerIdentityCandidate,
    Form4SecIssuerObservation,
    Form4SecReportingOwnerIdentityCandidate,
    Form4SecReportingOwnerObservation,
    Form4SecTransactionAttributionRow,
)
_GROUPING_PROVENANCE_ENUM_TYPES = (
    Form4ObservedIdentityDisposition,
    Form4OwnerAttributionOutcome,
    Form4ProvisionalDisposition,
)
_FACTORY_CREATED_GROUPINGS: dict[
    int,
    tuple[weakref.ReferenceType[Form4SecEntityGrouping], str],
] = {}
_FACTORY_CREATED_GROUPINGS_LOCK = threading.RLock()


def _grouping_provenance_payload(
    value: object,
    *,
    _budget: _ProjectionBudget | None = None,
    _depth: int = 0,
) -> object:
    """Project exact IB-2B output state without invoking object callbacks."""

    if _budget is None:
        _budget = _ProjectionBudget()
    if _depth > MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_DEPTH:
        raise Form4SecEntityGroupingError(
            "REFUSED: grouping provenance exceeds the depth bound"
        )
    _budget.nodes += 1
    if _budget.nodes > MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_NODES:
        raise Form4SecEntityGroupingError(
            "REFUSED: grouping provenance exceeds the node bound"
        )
    value_type = type(value)
    if any(
        value_type is enum_type
        for enum_type in _GROUPING_PROVENANCE_ENUM_TYPES
    ):
        return _grouping_provenance_payload(
            value.value,
            _budget=_budget,
            _depth=_depth + 1,
        )
    if value_type is date:
        return value.isoformat()
    if value_type is str:
        _budget.text_characters += len(value)
        if _budget.text_characters > MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS:
            raise Form4SecEntityGroupingError(
                "REFUSED: grouping provenance exceeds the text bound"
            )
        return value
    if value is None or value_type is bool or value_type is int:
        return value
    is_contract = any(
        value_type is contract_type
        for contract_type in _GROUPING_PROVENANCE_DATACLASS_TYPES
    )
    if value_type is tuple or is_contract:
        active_ids = _budget.active_ids
        assert active_ids is not None
        value_id = id(value)
        if value_id in active_ids:
            raise Form4SecEntityGroupingError(
                "REFUSED: grouping provenance contains a cycle"
            )
        active_ids.add(value_id)
        try:
            if value_type is tuple:
                return [
                    _grouping_provenance_payload(
                        item,
                        _budget=_budget,
                        _depth=_depth + 1,
                    )
                    for item in value
                ]
            declared_fields = {item.name for item in fields(value_type)}
            instance_state = object.__getattribute__(value, "__dict__")
            if (
                type(instance_state) is not dict
                or set(instance_state) != declared_fields
            ):
                raise Form4SecEntityGroupingError(
                    "REFUSED: grouping provenance dataclass state is not exact"
                )
            return {
                item.name: _grouping_provenance_payload(
                    instance_state[item.name],
                    _budget=_budget,
                    _depth=_depth + 1,
                )
                for item in fields(value_type)
            }
        finally:
            active_ids.remove(value_id)
    raise Form4SecEntityGroupingError(
        "REFUSED: grouping provenance contains an unsupported value"
    )


def _grouping_provenance_fingerprint(
    grouping: Form4SecEntityGrouping,
) -> str:
    if type(grouping) is not Form4SecEntityGrouping:
        raise Form4SecEntityGroupingError(
            "REFUSED: provenance input must be an exact SEC entity grouping"
        )
    return hash_payload(_grouping_provenance_payload(grouping))


def _register_factory_created_grouping(
    grouping: Form4SecEntityGrouping,
) -> None:
    fingerprint = _grouping_provenance_fingerprint(grouping)
    object_id = id(grouping)

    def _remove_if_current(
        dead_reference: weakref.ReferenceType[Form4SecEntityGrouping],
    ) -> None:
        with _FACTORY_CREATED_GROUPINGS_LOCK:
            current = _FACTORY_CREATED_GROUPINGS.get(object_id)
            if current is not None and current[0] is dead_reference:
                _FACTORY_CREATED_GROUPINGS.pop(object_id, None)

    grouping_reference = weakref.ref(grouping, _remove_if_current)
    with _FACTORY_CREATED_GROUPINGS_LOCK:
        _FACTORY_CREATED_GROUPINGS[object_id] = (
            grouping_reference,
            fingerprint,
        )


def _matches_factory_created_sec_entity_grouping_fingerprint(
    value: object,
    observed_fingerprint: object,
) -> bool:
    try:
        if (
            type(value) is not Form4SecEntityGrouping
            or type(observed_fingerprint) is not str
            or _SHA256_RE.fullmatch(observed_fingerprint) is None
        ):
            return False
        with _FACTORY_CREATED_GROUPINGS_LOCK:
            current = _FACTORY_CREATED_GROUPINGS.get(id(value))
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


def _is_factory_created_sec_entity_grouping(value: object) -> bool:
    try:
        if type(value) is not Form4SecEntityGrouping:
            return False
        fingerprint = _grouping_provenance_fingerprint(value)
        return _matches_factory_created_sec_entity_grouping_fingerprint(
            value,
            fingerprint,
        )
    except (
        AttributeError,
        Form4SecEntityGroupingError,
        KeyError,
        OverflowError,
        RecursionError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        return False


def _upstream_owner_payload(state: dict) -> dict[str, object]:
    return {
        "accession_number": state["accession_number"],
        "source_sha256": state["source_sha256"],
        "reporting_owner_index": state["reporting_owner_index"],
        "owner_cik": state["owner_cik"],
        "owner_name": state["owner_name"],
        "is_director": state["is_director"],
        "is_officer": state["is_officer"],
        "is_ten_percent_owner": state["is_ten_percent_owner"],
        "is_other": state["is_other"],
        "officer_title": state["officer_title"],
        "relationship_complete": state["relationship_complete"],
    }


def _upstream_owner_full_payload(state: dict) -> dict[str, object]:
    return {
        **_upstream_owner_payload(state),
        "owner_observation_id": state["owner_observation_id"],
    }


def _validate_upstream_owner(
    owner: Form4ObservedReportingOwnerIdentityRow,
) -> dict:
    state = _exact_state(
        owner,
        Form4ObservedReportingOwnerIdentityRow,
        _OWNER_FIELDS,
    )
    _accession(state["accession_number"], label="upstream owner accession")
    _sha256(state["source_sha256"], label="upstream owner source hash")
    if (
        type(state["reporting_owner_index"]) is not int
        or state["reporting_owner_index"] < 0
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream owner index is invalid"
        )
    _cik(state["owner_cik"], label="upstream owner CIK")
    _required_text(state["owner_name"], label="upstream owner name")
    _optional_text(state["officer_title"], label="upstream officer title")
    flags = tuple(
        state[name]
        for name in (
            "is_director",
            "is_officer",
            "is_ten_percent_owner",
            "is_other",
        )
    )
    if any(value is not None and type(value) is not bool for value in flags):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream owner relationship flags are invalid"
        )
    if (
        type(state["relationship_complete"]) is not bool
        or state["relationship_complete"]
        != all(value is not None for value in flags)
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream owner relationship completeness is invalid"
        )
    _sha256(
        state["owner_observation_id"],
        label="upstream owner observation ID",
    )
    if state["owner_observation_id"] != hash_payload(
        _upstream_owner_payload(state)
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream owner observation ID is inconsistent"
        )
    return dict(state)


def _upstream_filing_payload(state: dict) -> dict[str, object]:
    return {
        "accession_number": state["accession_number"],
        "source_sha256": state["source_sha256"],
        "document_type": state["document_type"],
        "accepted_at_utc": state["accepted_at_utc"],
        "original_accession": state["original_accession"],
        "amends_accession": state["amends_accession"],
        "primary_document_url": state["primary_document_url"],
        "issuer_cik": state["issuer_cik"],
        "issuer_name": state["issuer_name"],
        "issuer_symbol_raw": state["issuer_symbol_raw"],
        "reporting_owner_count": state["reporting_owner_count"],
        "all_owner_relationships_complete": (
            state["all_owner_relationships_complete"]
        ),
        "owner_set_outcomes": [
            item.value for item in state["owner_set_outcomes"]
        ],
        "reporting_owner_observation_ids": list(
            state["reporting_owner_observation_ids"]
        ),
        "reporting_owner_inventory_hash": (
            state["reporting_owner_inventory_hash"]
        ),
        "version_disposition": state["version_disposition"].value,
    }


def _upstream_filing_full_payload(state: dict) -> dict[str, object]:
    return {
        **_upstream_filing_payload(state),
        "filing_observation_id": state["filing_observation_id"],
    }


def _validate_upstream_filing(
    filing: Form4ObservedFilingIdentityRow,
) -> dict:
    state = _exact_state(
        filing,
        Form4ObservedFilingIdentityRow,
        _FILING_FIELDS,
    )
    _accession(state["accession_number"], label="upstream filing accession")
    _sha256(state["source_sha256"], label="upstream filing source hash")
    if type(state["document_type"]) is not str or state["document_type"] not in {
        "4",
        "4/A",
    }:
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream filing document type is invalid"
        )
    _canonical_utc_text(
        state["accepted_at_utc"],
        label="upstream filing acceptance",
    )
    _accession(
        state["original_accession"],
        label="upstream original accession",
    )
    if state["amends_accession"] is not None:
        _accession(
            state["amends_accession"],
            label="upstream amends accession",
        )
    _required_text(
        state["primary_document_url"],
        label="upstream primary document URL",
    )
    if any(character.isspace() for character in state["primary_document_url"]):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream primary document URL contains whitespace"
        )
    _cik(state["issuer_cik"], label="upstream issuer CIK")
    _required_text(state["issuer_name"], label="upstream issuer name")
    _optional_text(state["issuer_symbol_raw"], label="upstream issuer symbol")
    owner_count = state["reporting_owner_count"]
    owner_complete = state["all_owner_relationships_complete"]
    outcomes = state["owner_set_outcomes"]
    owner_ids = state["reporting_owner_observation_ids"]
    if (
        type(owner_count) is not int
        or not 0 <= owner_count <= MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS
        or type(owner_complete) is not bool
        or (owner_count == 0 and owner_complete)
        or type(outcomes) is not tuple
        or not outcomes
        or any(type(item) is not Form4ObservedOwnerSetOutcome for item in outcomes)
        or len(set(outcomes)) != len(outcomes)
        or outcomes != _owner_set_outcomes(owner_count, owner_complete)
        or type(owner_ids) is not tuple
        or len(owner_ids) != owner_count
        or len(set(owner_ids)) != len(owner_ids)
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream filing owner-set state is invalid"
        )
    for owner_id in owner_ids:
        _sha256(owner_id, label="upstream filing owner observation ID")
    _sha256(
        state["reporting_owner_inventory_hash"],
        label="upstream filing owner inventory hash",
    )
    disposition = state["version_disposition"]
    if type(disposition) is not Form4VersionDisposition:
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream filing version disposition is invalid"
        )
    if state["document_type"] == "4":
        valid_lineage = (
            state["amends_accession"] is None
            and state["original_accession"] == state["accession_number"]
            and disposition
            is Form4VersionDisposition.ORIGINAL_OBSERVED_IN_SUPPLIED_SAMPLE
        )
    else:
        valid_lineage = (
            state["amends_accession"] is not None
            and state["original_accession"] == state["amends_accession"]
            and state["original_accession"] != state["accession_number"]
            and disposition
            is Form4VersionDisposition.QUARANTINED_UNRESOLVED_AMENDMENT
        )
    if not valid_lineage:
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream filing lineage is inconsistent"
        )
    _sha256(
        state["filing_observation_id"],
        label="upstream filing observation ID",
    )
    if state["filing_observation_id"] != hash_payload(
        _upstream_filing_payload(state)
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream filing observation ID is inconsistent"
        )
    return dict(state)


def _upstream_transaction_payload(state: dict) -> dict[str, object]:
    return {
        "accession_number": state["accession_number"],
        "source_sha256": state["source_sha256"],
        "row_index": state["row_index"],
        "event_id": state["event_id"],
        "upstream_report_row_id": state["upstream_report_row_id"],
        "transaction_payload_hash": state["transaction_payload_hash"],
        "filing_observation_id": state["filing_observation_id"],
        "security_title_raw": state["security_title_raw"],
        "transaction_date": (
            None
            if state["transaction_date"] is None
            else state["transaction_date"].isoformat()
        ),
        "upstream_disposition": state["upstream_disposition"].value,
        "identity_disposition": state["identity_disposition"].value,
        "resolved_security_identity": None,
        "point_in_time_security_identity_verified": False,
        "canonical_filter_authorized": False,
        "lot_aggregation_authorized": False,
    }


def _upstream_transaction_full_payload(state: dict) -> dict[str, object]:
    return {
        **_upstream_transaction_payload(state),
        "transaction_observation_id": state["transaction_observation_id"],
    }


def _validate_upstream_transaction(
    transaction: Form4ObservedTransactionIdentityRow,
) -> dict:
    state = _exact_state(
        transaction,
        Form4ObservedTransactionIdentityRow,
        _TRANSACTION_FIELDS,
    )
    _accession(
        state["accession_number"],
        label="upstream transaction accession",
    )
    _sha256(
        state["source_sha256"],
        label="upstream transaction source hash",
    )
    if type(state["row_index"]) is not int or state["row_index"] < 0:
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream transaction row index is invalid"
        )
    for label, name in (
        ("upstream event ID", "event_id"),
        ("upstream report row ID", "upstream_report_row_id"),
        ("upstream transaction payload hash", "transaction_payload_hash"),
        ("upstream filing observation ID", "filing_observation_id"),
        ("upstream transaction observation ID", "transaction_observation_id"),
    ):
        _sha256(state[name], label=label)
    _optional_text(
        state["security_title_raw"],
        label="upstream security title",
    )
    if state["transaction_date"] is not None and type(
        state["transaction_date"]
    ) is not date:
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream transaction date is invalid"
        )
    if (
        type(state["upstream_disposition"]) is not Form4ProvisionalDisposition
        or type(state["identity_disposition"])
        is not Form4ObservedIdentityDisposition
        or state["identity_disposition"]
        is not _identity_disposition(state["upstream_disposition"])
        or state["resolved_security_identity"] is not None
        or state["point_in_time_security_identity_verified"] is not False
        or state["canonical_filter_authorized"] is not False
        or state["lot_aggregation_authorized"] is not False
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream transaction state claims invalid authority"
        )
    if state["transaction_observation_id"] != hash_payload(
        _upstream_transaction_payload(state)
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream transaction observation ID is inconsistent"
        )
    return dict(state)


def _upstream_identity_payload(state: dict) -> dict[str, object]:
    return {name: state[name] for name in _INVENTORY_IDENTITY_FIELDS[:-1]}


def _validate_upstream_identity(
    identity: Form4ObservedIdentityInventoryIdentity,
) -> dict:
    state = _exact_state(
        identity,
        Form4ObservedIdentityInventoryIdentity,
        _INVENTORY_IDENTITY_FIELDS,
    )
    if (
        type(state["contract_version"]) is not str
        or state["contract_version"] != FORM4_OBSERVED_IDENTITY_INVENTORY_VERSION
        or type(state["builder_git_commit"]) is not str
        or _GIT_COMMIT_RE.fullmatch(state["builder_git_commit"]) is None
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory identity version is invalid"
        )
    _required_text(state["upstream_evidence_id"], label="upstream evidence ID")
    _required_text(state["upstream_report_id"], label="upstream report ID")
    for name in (
        "upstream_evidence_identity_hash",
        "upstream_parsed_corpus_hash",
        "upstream_source_inventory_hash",
        "upstream_report_identity_hash",
        "upstream_report_row_inventory_hash",
        "filing_inventory_hash",
        "reporting_owner_inventory_hash",
        "transaction_inventory_hash",
    ):
        _sha256(state[name], label=f"upstream {name}")
    counts_and_caps = (
        (state["filing_count"], MAX_FORM4_OBSERVED_IDENTITY_FILINGS),
        (state["amendment_count"], MAX_FORM4_OBSERVED_IDENTITY_FILINGS),
        (
            state["reporting_owner_count"],
            MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS,
        ),
        (
            state["non_single_owner_filing_count"],
            MAX_FORM4_OBSERVED_IDENTITY_FILINGS,
        ),
        (
            state["transaction_count"],
            MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
        ),
        (
            state["provisional_candidate_count"],
            MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
        ),
        (
            state["quarantine_count"],
            MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
        ),
    )
    if (
        any(
            type(value) is not int or not 0 <= value <= cap
            for value, cap in counts_and_caps
        )
        or state["amendment_count"] > state["filing_count"]
        or state["non_single_owner_filing_count"] > state["filing_count"]
        or state["provisional_candidate_count"] + state["quarantine_count"]
        != state["transaction_count"]
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory identity counts are invalid"
        )
    authority_names = (
        "official_profile_compatibility_verified",
        "official_amendment_link_verified",
        "complete_amendment_coverage_verified",
        "point_in_time_issuer_identity_verified",
        "point_in_time_reporting_owner_identity_verified",
        "point_in_time_security_identity_verified",
        "point_in_time_transaction_identity_verified",
        "ordinary_equity_classification_verified",
        "canonical_filter_authorized",
        "lot_aggregation_authorized",
        "outcomes_authorized",
        "qc_execution_authorized",
        "deployment_authorized",
        "trading_authorized",
    )
    if (
        any(state[name] is not False for name in authority_names)
        or type(state["authorized_outcome_looks"]) is not int
        or state["authorized_outcome_looks"] != 0
        or type(state["consumed_outcome_looks"]) is not int
        or state["consumed_outcome_looks"] != 0
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory claims downstream authority"
        )
    expected_id = (
        "form4-observed-identity-inventory-"
        f"{hash_payload(_upstream_identity_payload(state))[:16]}"
    )
    if type(state["inventory_id"]) is not str or state["inventory_id"] != expected_id:
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory ID is inconsistent"
        )
    return dict(state)


def _project_validated_snapshot(
    value: object,
    *,
    budget: _ProjectionBudget | None = None,
    depth: int = 0,
) -> object:
    """Bound and copy an internally normalized validation snapshot."""

    if budget is None:
        budget = _ProjectionBudget()
    if depth > MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_DEPTH:
        raise Form4SecEntityGroupingError(
            "REFUSED: validated snapshot exceeds the depth bound"
        )
    budget.nodes += 1
    if budget.nodes > MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_NODES:
        raise Form4SecEntityGroupingError(
            "REFUSED: validated snapshot exceeds the node bound"
        )
    value_type = type(value)
    if value_type is str:
        budget.text_characters += len(value)
        if budget.text_characters > MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS:
            raise Form4SecEntityGroupingError(
                "REFUSED: validated snapshot exceeds the text bound"
            )
        return value
    if value is None or value_type is bool or value_type is int:
        return value
    if value_type is dict or value_type is list:
        active_ids = budget.active_ids
        assert active_ids is not None
        value_id = id(value)
        if value_id in active_ids:
            raise Form4SecEntityGroupingError(
                "REFUSED: validated snapshot contains a cycle"
            )
        active_ids.add(value_id)
        try:
            if value_type is list:
                return [
                    _project_validated_snapshot(
                        item,
                        budget=budget,
                        depth=depth + 1,
                    )
                    for item in value
                ]
            if any(type(key) is not str for key in value):
                raise Form4SecEntityGroupingError(
                    "REFUSED: validated snapshot keys are not exact text"
                )
            return {
                key: _project_validated_snapshot(
                    item,
                    budget=budget,
                    depth=depth + 1,
                )
                for key, item in value.items()
            }
        finally:
            active_ids.remove(value_id)
    raise Form4SecEntityGroupingError(
        "REFUSED: validated snapshot contains an unsupported value"
    )


def _validated_upstream_state_fingerprint(
    identity: dict,
    filings: tuple[dict, ...],
    owners: tuple[dict, ...],
    transactions: tuple[dict, ...],
) -> str:
    payload = {
        "identity": dict(identity),
        "filings": [
            _upstream_filing_full_payload(item) for item in filings
        ],
        "reporting_owners": [
            _upstream_owner_full_payload(item) for item in owners
        ],
        "transactions": [
            _upstream_transaction_full_payload(item)
            for item in transactions
        ],
    }
    return hash_payload(_project_validated_snapshot(payload))


def _validate_upstream_inventory(
    inventory: Form4ObservedIdentityInventory,
) -> tuple[
    dict,
    tuple[dict, ...],
    tuple[dict, ...],
    tuple[dict, ...],
    str,
]:
    """Independently revalidate IB-2A without invoking upstream callbacks."""

    state = _exact_state(
        inventory,
        Form4ObservedIdentityInventory,
        _INVENTORY_FIELDS,
    )
    if (
        type(state["filings"]) is not tuple
        or type(state["reporting_owners"]) is not tuple
        or type(state["transactions"]) is not tuple
        or len(state["filings"]) > MAX_FORM4_OBSERVED_IDENTITY_FILINGS
        or len(state["reporting_owners"])
        > MAX_FORM4_OBSERVED_IDENTITY_REPORTING_OWNERS
        or len(state["transactions"])
        > MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory shape exceeds a resource bound"
        )
    identity = _validate_upstream_identity(state["identity"])
    filings = tuple(_validate_upstream_filing(item) for item in state["filings"])
    owners = tuple(
        _validate_upstream_owner(item) for item in state["reporting_owners"]
    )
    transactions = tuple(
        _validate_upstream_transaction(item) for item in state["transactions"]
    )

    filing_keys = tuple(
        (item["accession_number"], item["source_sha256"])
        for item in filings
    )
    owner_keys = tuple(
        (
            item["accession_number"],
            item["source_sha256"],
            item["reporting_owner_index"],
        )
        for item in owners
    )
    transaction_keys = tuple(
        (
            item["accession_number"],
            item["source_sha256"],
            item["row_index"],
            item["event_id"],
        )
        for item in transactions
    )
    filing_accessions = tuple(item["accession_number"] for item in filings)
    source_row_keys = tuple(
        (item["accession_number"], item["row_index"])
        for item in transactions
    )
    if (
        filing_keys != tuple(sorted(filing_keys))
        or owner_keys != tuple(sorted(owner_keys))
        or transaction_keys != tuple(sorted(transaction_keys))
        or len(set(filing_keys)) != len(filing_keys)
        or len(set(owner_keys)) != len(owner_keys)
        or len(set(transaction_keys)) != len(transaction_keys)
        or len(set(filing_accessions)) != len(filing_accessions)
        or len(set(source_row_keys)) != len(source_row_keys)
        or len({item["filing_observation_id"] for item in filings})
        != len(filings)
        or len({item["owner_observation_id"] for item in owners})
        != len(owners)
        or len({item["transaction_observation_id"] for item in transactions})
        != len(transactions)
        or len({item["upstream_report_row_id"] for item in transactions})
        != len(transactions)
        or len({item["transaction_payload_hash"] for item in transactions})
        != len(transactions)
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory order or uniqueness is invalid"
        )

    filings_by_key = {
        (item["accession_number"], item["source_sha256"]): item
        for item in filings
    }
    filings_by_accession = {
        item["accession_number"]: item for item in filings
    }
    acceptance_by_original: dict[str, set[str]] = {}
    for filing in filings:
        accepted = acceptance_by_original.setdefault(
            filing["original_accession"],
            set(),
        )
        if filing["accepted_at_utc"] in accepted:
            raise Form4SecEntityGroupingError(
                "REFUSED: upstream filing lineage acceptance is ambiguous"
            )
        accepted.add(filing["accepted_at_utc"])
        if filing["document_type"] == "4":
            continue
        original = filings_by_accession.get(filing["original_accession"])
        if (
            original is None
            or original["document_type"] != "4"
            or original["amends_accession"] is not None
            or original["original_accession"] != original["accession_number"]
            or original["issuer_cik"] != filing["issuer_cik"]
            or original["accepted_at_utc"] >= filing["accepted_at_utc"]
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: upstream amendment binding is invalid"
            )

    owners_by_filing: dict[tuple[str, str], list[dict]] = {
        key: [] for key in filings_by_key
    }
    for owner in owners:
        key = (owner["accession_number"], owner["source_sha256"])
        if key not in owners_by_filing:
            raise Form4SecEntityGroupingError(
                "REFUSED: upstream owner has no filing"
            )
        owners_by_filing[key].append(owner)
    for key, filing in filings_by_key.items():
        filing_owners = owners_by_filing[key]
        if (
            tuple(item["reporting_owner_index"] for item in filing_owners)
            != tuple(range(len(filing_owners)))
            or tuple(item["owner_observation_id"] for item in filing_owners)
            != filing["reporting_owner_observation_ids"]
            or hash_payload(
                [_upstream_owner_full_payload(item) for item in filing_owners]
            )
            != filing["reporting_owner_inventory_hash"]
            or len(filing_owners) != filing["reporting_owner_count"]
            or (
                bool(filing_owners)
                and all(item["relationship_complete"] for item in filing_owners)
            )
            != filing["all_owner_relationships_complete"]
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: upstream filing-to-owner binding is invalid"
            )

    transactions_by_filing: dict[tuple[str, str], list[dict]] = {
        key: [] for key in filings_by_key
    }
    for transaction in transactions:
        key = (
            transaction["accession_number"],
            transaction["source_sha256"],
        )
        filing = filings_by_key.get(key)
        if (
            filing is None
            or transaction["filing_observation_id"]
            != filing["filing_observation_id"]
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: upstream transaction-to-filing binding is invalid"
            )
        transactions_by_filing[key].append(transaction)
        if transaction["identity_disposition"] is (
            Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE
        ) and (
            filing["version_disposition"]
            is not Form4VersionDisposition.ORIGINAL_OBSERVED_IN_SUPPLIED_SAMPLE
            or filing["owner_set_outcomes"]
            != (
                Form4ObservedOwnerSetOutcome.SINGLE_COMPLETE_OWNER_SET_OBSERVED,
            )
        ):
            raise Form4SecEntityGroupingError(
                "REFUSED: upstream candidate contradicts filing quarantine"
            )
    if any(
        tuple(item["row_index"] for item in filing_transactions)
        != tuple(range(len(filing_transactions)))
        for filing_transactions in transactions_by_filing.values()
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream transaction indexes are not contiguous"
        )

    candidate_count = sum(
        item["identity_disposition"]
        is Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE
        for item in transactions
    )
    if (
        identity["filing_count"] != len(filings)
        or identity["amendment_count"]
        != sum(item["document_type"] == "4/A" for item in filings)
        or identity["reporting_owner_count"] != len(owners)
        or identity["non_single_owner_filing_count"]
        != sum(item["reporting_owner_count"] != 1 for item in filings)
        or identity["transaction_count"] != len(transactions)
        or identity["provisional_candidate_count"] != candidate_count
        or identity["quarantine_count"] != len(transactions) - candidate_count
        or identity["filing_inventory_hash"]
        != hash_payload([_upstream_filing_full_payload(item) for item in filings])
        or identity["reporting_owner_inventory_hash"]
        != hash_payload([_upstream_owner_full_payload(item) for item in owners])
        or identity["transaction_inventory_hash"]
        != hash_payload(
            [_upstream_transaction_full_payload(item) for item in transactions]
        )
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory counts or hashes are inconsistent"
        )
    state_fingerprint = _validated_upstream_state_fingerprint(
        identity,
        filings,
        owners,
        transactions,
    )
    return identity, filings, owners, transactions, state_fingerprint


def _build_form4_sec_entity_grouping(
    inventory: Form4ObservedIdentityInventory,
    *,
    builder_git_commit: str,
) -> Form4SecEntityGrouping:
    if (
        type(builder_git_commit) is not str
        or _GIT_COMMIT_RE.fullmatch(builder_git_commit) is None
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: builder Git commit must be a full lowercase SHA-1"
        )
    captured_fingerprint = _upstream_fingerprint(inventory)
    if not _matches_factory_created_observed_identity_inventory_fingerprint(
        inventory,
        captured_fingerprint,
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory is not an unchanged factory-created result"
        )
    (
        identity_state,
        filings,
        owners,
        transactions,
        validated_state_fingerprint,
    ) = _validate_upstream_inventory(inventory)
    if (
        validated_state_fingerprint != captured_fingerprint
        or not _matches_factory_created_observed_identity_inventory_fingerprint(
            inventory,
            validated_state_fingerprint,
        )
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: validated snapshot does not match factory provenance"
        )

    issuer_observations_by_cik: dict[
        str,
        list[Form4SecIssuerObservation],
    ] = {}
    issuer_observation_by_filing: dict[
        tuple[str, str],
        Form4SecIssuerObservation,
    ] = {}
    for filing in filings:
        payload = {
            "accession_number": filing["accession_number"],
            "source_sha256": filing["source_sha256"],
            "filing_observation_id": filing["filing_observation_id"],
            "document_type": filing["document_type"],
            "accepted_at_utc": filing["accepted_at_utc"],
            "original_accession": filing["original_accession"],
            "amends_accession": filing["amends_accession"],
            "primary_document_url": filing["primary_document_url"],
            "issuer_cik": filing["issuer_cik"],
            "issuer_name": filing["issuer_name"],
            "issuer_symbol_raw": filing["issuer_symbol_raw"],
        }
        observation = Form4SecIssuerObservation(
            **payload,
            issuer_observation_id=hash_payload(payload),
            _verified_factory_token=_ROW_FACTORY_TOKEN,
        )
        key = (observation.accession_number, observation.source_sha256)
        if key in issuer_observation_by_filing:
            raise Form4SecEntityGroupingError(
                "REFUSED: duplicate issuer filing observation"
            )
        issuer_observation_by_filing[key] = observation
        issuer_observations_by_cik.setdefault(
            observation.issuer_cik,
            [],
        ).append(observation)

    issuer_candidates: list[Form4SecIssuerIdentityCandidate] = []
    for issuer_cik, candidate_observations in issuer_observations_by_cik.items():
        observations = tuple(
            sorted(
                candidate_observations,
                key=lambda item: (
                    item.accepted_at_utc,
                    item.accession_number,
                    item.source_sha256,
                ),
            )
        )
        observation_hash = hash_payload(
            [item.to_payload() for item in observations]
        )
        candidate_payload = {
            "issuer_cik": issuer_cik,
            "observations": [item.to_payload() for item in observations],
            "observation_inventory_hash": observation_hash,
            "point_in_time_issuer_identity_verified": False,
        }
        issuer_candidates.append(
            Form4SecIssuerIdentityCandidate(
                issuer_cik=issuer_cik,
                observations=observations,
                observation_inventory_hash=observation_hash,
                issuer_candidate_id=hash_payload(candidate_payload),
                point_in_time_issuer_identity_verified=False,
                _verified_factory_token=_CANDIDATE_FACTORY_TOKEN,
            )
        )
    sorted_issuer_candidates = tuple(
        sorted(issuer_candidates, key=lambda item: item.issuer_cik)
    )
    issuer_candidate_by_cik = {
        item.issuer_cik: item for item in sorted_issuer_candidates
    }

    owner_observations_by_cik: dict[
        str,
        list[Form4SecReportingOwnerObservation],
    ] = {}
    owner_states_by_filing: dict[tuple[str, str], list[dict]] = {
        key: [] for key in issuer_observation_by_filing
    }
    for owner in owners:
        filing_key = (owner["accession_number"], owner["source_sha256"])
        issuer_observation = issuer_observation_by_filing.get(filing_key)
        if issuer_observation is None:
            raise Form4SecEntityGroupingError(
                "REFUSED: retained owner has no issuer observation"
            )
        payload = {
            "accession_number": owner["accession_number"],
            "source_sha256": owner["source_sha256"],
            "filing_observation_id": issuer_observation.filing_observation_id,
            "accepted_at_utc": issuer_observation.accepted_at_utc,
            "reporting_owner_index": owner["reporting_owner_index"],
            "upstream_owner_observation_id": owner["owner_observation_id"],
            "owner_cik": owner["owner_cik"],
            "owner_name": owner["owner_name"],
            "is_director": owner["is_director"],
            "is_officer": owner["is_officer"],
            "is_ten_percent_owner": owner["is_ten_percent_owner"],
            "is_other": owner["is_other"],
            "officer_title": owner["officer_title"],
            "relationship_complete": owner["relationship_complete"],
        }
        observation = Form4SecReportingOwnerObservation(
            **payload,
            owner_observation_id=hash_payload(payload),
            _verified_factory_token=_ROW_FACTORY_TOKEN,
        )
        owner_states_by_filing[filing_key].append(owner)
        owner_observations_by_cik.setdefault(
            observation.owner_cik,
            [],
        ).append(observation)

    owner_candidates: list[Form4SecReportingOwnerIdentityCandidate] = []
    for owner_cik, candidate_observations in owner_observations_by_cik.items():
        observations = tuple(
            sorted(
                candidate_observations,
                key=lambda item: (
                    item.accepted_at_utc,
                    item.accession_number,
                    item.source_sha256,
                    item.reporting_owner_index,
                ),
            )
        )
        observation_hash = hash_payload(
            [item.to_payload() for item in observations]
        )
        candidate_payload = {
            "owner_cik": owner_cik,
            "observations": [item.to_payload() for item in observations],
            "observation_inventory_hash": observation_hash,
            "point_in_time_reporting_owner_identity_verified": False,
        }
        owner_candidates.append(
            Form4SecReportingOwnerIdentityCandidate(
                owner_cik=owner_cik,
                observations=observations,
                observation_inventory_hash=observation_hash,
                owner_candidate_id=hash_payload(candidate_payload),
                point_in_time_reporting_owner_identity_verified=False,
                _verified_factory_token=_CANDIDATE_FACTORY_TOKEN,
            )
        )
    sorted_owner_candidates = tuple(
        sorted(owner_candidates, key=lambda item: item.owner_cik)
    )
    owner_candidate_by_cik = {
        item.owner_cik: item for item in sorted_owner_candidates
    }

    transaction_attributions: list[Form4SecTransactionAttributionRow] = []
    for transaction in transactions:
        filing_key = (
            transaction["accession_number"],
            transaction["source_sha256"],
        )
        issuer_observation = issuer_observation_by_filing.get(filing_key)
        if issuer_observation is None:
            raise Form4SecEntityGroupingError(
                "REFUSED: retained transaction has no issuer observation"
            )
        issuer_candidate = issuer_candidate_by_cik[issuer_observation.issuer_cik]
        filing_owner_states = tuple(owner_states_by_filing[filing_key])
        outcomes = _owner_attribution_outcomes(
            tuple(owner["owner_cik"] for owner in filing_owner_states),
            tuple(
                owner["relationship_complete"] is True
                for owner in filing_owner_states
            ),
        )
        if outcomes == (
            Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,
        ):
            attributed_owner_cik = filing_owner_states[0]["owner_cik"]
            attributed_owner_candidate_id = owner_candidate_by_cik[
                attributed_owner_cik
            ].owner_candidate_id
        else:
            attributed_owner_cik = None
            attributed_owner_candidate_id = None
        payload = {
            "accession_number": transaction["accession_number"],
            "source_sha256": transaction["source_sha256"],
            "row_index": transaction["row_index"],
            "event_id": transaction["event_id"],
            "filing_observation_id": transaction["filing_observation_id"],
            "upstream_transaction_observation_id": (
                transaction["transaction_observation_id"]
            ),
            "upstream_report_row_id": transaction["upstream_report_row_id"],
            "transaction_payload_hash": transaction["transaction_payload_hash"],
            "security_title_raw": transaction["security_title_raw"],
            "transaction_date": transaction["transaction_date"],
            "upstream_disposition": transaction["upstream_disposition"],
            "identity_disposition": transaction["identity_disposition"],
            "issuer_candidate_id": issuer_candidate.issuer_candidate_id,
            "attributed_owner_cik": attributed_owner_cik,
            "attributed_owner_candidate_id": attributed_owner_candidate_id,
            "owner_attribution_outcomes": outcomes,
            "point_in_time_issuer_identity_verified": False,
            "point_in_time_reporting_owner_identity_verified": False,
            "point_in_time_security_identity_verified": False,
            "point_in_time_transaction_identity_verified": False,
            "canonical_filter_authorized": False,
            "lot_aggregation_authorized": False,
        }
        lineage_payload = {
            **payload,
            "transaction_date": (
                None
                if payload["transaction_date"] is None
                else payload["transaction_date"].isoformat()
            ),
            "upstream_disposition": payload["upstream_disposition"].value,
            "identity_disposition": payload["identity_disposition"].value,
            "owner_attribution_outcomes": [
                item.value for item in outcomes
            ],
        }
        transaction_attributions.append(
            Form4SecTransactionAttributionRow(
                **payload,
                transaction_attribution_id=hash_payload(lineage_payload),
                _verified_factory_token=_ROW_FACTORY_TOKEN,
            )
        )
    sorted_attributions = tuple(
        sorted(
            transaction_attributions,
            key=lambda item: (
                item.accession_number,
                item.source_sha256,
                item.row_index,
                item.event_id,
            ),
        )
    )

    issuer_hash = hash_payload(
        [item.to_payload() for item in sorted_issuer_candidates]
    )
    owner_hash = hash_payload(
        [item.to_payload() for item in sorted_owner_candidates]
    )
    transaction_hash = hash_payload(
        [item.to_payload() for item in sorted_attributions]
    )
    single_count = sum(
        item.owner_attribution_outcomes
        == (
            Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,
        )
        for item in sorted_attributions
    )
    identity_payload = {
        "contract_version": FORM4_SEC_ENTITY_GROUPING_VERSION,
        "builder_git_commit": builder_git_commit,
        "upstream_inventory_id": identity_state["inventory_id"],
        "upstream_inventory_identity_hash": hash_payload(identity_state),
        "upstream_inventory_observation_hash": validated_state_fingerprint,
        "upstream_filing_inventory_hash": identity_state["filing_inventory_hash"],
        "upstream_reporting_owner_inventory_hash": (
            identity_state["reporting_owner_inventory_hash"]
        ),
        "upstream_transaction_inventory_hash": (
            identity_state["transaction_inventory_hash"]
        ),
        "issuer_candidate_inventory_hash": issuer_hash,
        "reporting_owner_candidate_inventory_hash": owner_hash,
        "transaction_attribution_inventory_hash": transaction_hash,
        "filing_observation_count": len(filings),
        "issuer_candidate_count": len(sorted_issuer_candidates),
        "reporting_owner_observation_count": len(owners),
        "reporting_owner_candidate_count": len(sorted_owner_candidates),
        "transaction_attribution_count": len(sorted_attributions),
        "single_complete_owner_attribution_count": single_count,
        "quarantined_transaction_count": len(sorted_attributions) - single_count,
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
    grouping_identity = Form4SecEntityGroupingIdentity(
        **identity_payload,
        grouping_id=(
            "form4-sec-entity-grouping-"
            f"{hash_payload(identity_payload)[:16]}"
        ),
        _verified_factory_token=_IDENTITY_FACTORY_TOKEN,
    )
    grouping = Form4SecEntityGrouping(
        identity=grouping_identity,
        issuer_candidates=sorted_issuer_candidates,
        reporting_owner_candidates=sorted_owner_candidates,
        transaction_attributions=sorted_attributions,
        _verified_factory_token=_GROUPING_FACTORY_TOKEN,
    )
    final_fingerprint = _upstream_fingerprint(inventory)
    if (
        final_fingerprint != validated_state_fingerprint
        or not _matches_factory_created_observed_identity_inventory_fingerprint(
            inventory,
            final_fingerprint,
        )
        or not _is_factory_created_observed_identity_inventory(inventory)
    ):
        raise Form4SecEntityGroupingError(
            "REFUSED: upstream inventory changed during grouping"
        )
    _register_factory_created_grouping(grouping)
    return grouping


def build_form4_sec_entity_grouping(
    inventory: Form4ObservedIdentityInventory,
    *,
    builder_git_commit: str,
) -> Form4SecEntityGrouping:
    """Group exact SEC CIK observations and normalize malformed-state errors."""

    try:
        return _build_form4_sec_entity_grouping(
            inventory,
            builder_git_commit=builder_git_commit,
        )
    except Form4SecEntityGroupingError:
        raise
    except (
        AttributeError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise Form4SecEntityGroupingError(
            "REFUSED: observed inventory changed or is malformed"
        ) from exc


__all__ = [
    "FORM4_SEC_ENTITY_GROUPING_VERSION",
    "Form4OwnerAttributionOutcome",
    "Form4SecEntityGrouping",
    "Form4SecEntityGroupingError",
    "Form4SecEntityGroupingIdentity",
    "Form4SecIssuerIdentityCandidate",
    "Form4SecIssuerObservation",
    "Form4SecReportingOwnerIdentityCandidate",
    "Form4SecReportingOwnerObservation",
    "Form4SecTransactionAttributionRow",
    "MAX_FORM4_SEC_ENTITY_GROUPING_ISSUER_CANDIDATES",
    "MAX_FORM4_SEC_ENTITY_GROUPING_OWNER_CANDIDATES",
    "MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_DEPTH",
    "MAX_FORM4_SEC_ENTITY_GROUPING_PROJECTION_NODES",
    "build_form4_sec_entity_grouping",
]
