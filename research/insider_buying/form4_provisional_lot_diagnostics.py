"""Evidence-bound, zero-authority provisional Form 4 lot diagnostics.

IB-2D joins one exact process-sealed IB-2C mapping back through the exact
IB-2B grouping and IB-2A inventory to the original IB-1E evidence.  It rebuilds
the IB-1G report from those evidence bytes and copies transaction economics
only from that rebuild.  The result retains one diagnostic row per mapping row
and groups only provisional candidates by owner CIK, owner-candidate ID,
security ID, share-class ID, and transaction date.

Any supplied amendment quarantines its complete supplied amendment family,
including when the amendment contains no transaction rows.  Upstream parser,
identity, owner-attribution, and security-mapping quarantine is never promoted.
The groups are diagnostics only: they do not deduplicate or supersede rows, and
the exact comparison to USD 50,000 is not an authorized value gate.  All
official, point-in-time, ordinary-equity, canonical, aggregation, outcome, QC,
deployment, and trading authority remains false, with zero outcome looks.
"""
from __future__ import annotations

import re
import threading
import weakref
from dataclasses import InitVar, dataclass, fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from hashlib import sha256

from data.financial_primitives import (
    decimal_text,
    exact_decimal_multiply,
    exact_decimal_sum,
)
from data.hashing import hash_payload
from research.insider_buying.contracts import (
    ClassificationOutcome,
    TransactionDiagnostic,
)
from research.insider_buying.form4_multi_period_amendment_evidence import (
    ProfileBoundForm4AmendmentEvidence,
)
from research.insider_buying.form4_observed_identity_inventory import (
    MAX_FORM4_OBSERVED_IDENTITY_FILINGS,
    MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS,
    MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS,
    Form4ObservedIdentityDisposition,
    Form4ObservedIdentityInventory,
    _contract_payload as _observed_contract_payload,
    _evidence_observation_hash,
    _inventory_provenance_fingerprint,
    _inventory_provenance_payload,
    _is_factory_created_observed_identity_inventory,
    _matches_factory_created_observed_identity_inventory_fingerprint,
    _preflight_evidence,
    _validate_rebuilt_report,
    _VERIFIED_INVENTORY_FACTORY_TOKEN as _UPSTREAM_INVENTORY_FACTORY_TOKEN,
)
from research.insider_buying.form4_pit_security_mapping import (
    MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_DEPTH,
    MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_NODES,
    Form4PitSecurityMapping,
    Form4PitSecurityMappingOutcome,
    Form4SecurityClass,
    Form4SecurityTitleMappingKind,
    _is_factory_created_form4_pit_security_mapping,
    _mapping_provenance_fingerprint,
    _mapping_provenance_payload,
    _matches_factory_created_form4_pit_security_mapping_fingerprint,
    _MAPPING_FACTORY_TOKEN as _UPSTREAM_MAPPING_FACTORY_TOKEN,
)
from research.insider_buying.form4_provisional_disposition_report import (
    Form4ProvisionalDisposition,
    Form4ProvisionalDispositionRow,
    build_form4_provisional_disposition_report,
)
from research.insider_buying.form4_sec_entity_grouping import (
    Form4OwnerAttributionOutcome,
    Form4SecEntityGrouping,
    _grouping_provenance_fingerprint,
    _grouping_provenance_payload,
    _is_factory_created_sec_entity_grouping,
    _matches_factory_created_sec_entity_grouping_fingerprint,
    _GROUPING_FACTORY_TOKEN as _UPSTREAM_GROUPING_FACTORY_TOKEN,
)


FORM4_PROVISIONAL_LOT_DIAGNOSTICS_VERSION = (
    "INSETF-IB2D-FORM4-PROVISIONAL-LOT-DIAGNOSTICS-v1"
)
FORM4_PROVISIONAL_LOT_THRESHOLD_USD = Decimal("50000")
MAX_FORM4_PROVISIONAL_LOT_GROUPS = MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
MAX_FORM4_PROVISIONAL_LOT_PROJECTION_NODES = (
    MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_NODES
)
MAX_FORM4_PROVISIONAL_LOT_PROJECTION_DEPTH = (
    MAX_FORM4_PIT_SECURITY_MAPPING_PROJECTION_DEPTH
)
_MAX_FORM4_PROVISIONAL_LOT_DECIMAL_DIGITS = 256
_MAX_FORM4_PROVISIONAL_LOT_DECIMAL_ABS_EXPONENT = 256

_ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_CIK_RE = re.compile(r"^[0-9]{10}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DIAGNOSTICS_ID_RE = re.compile(
    r"^form4-provisional-lot-diagnostics-(?P<hash_prefix>[0-9a-f]{16})$"
)

_ROW_FACTORY_TOKEN = object()
_GROUP_FACTORY_TOKEN = object()
_IDENTITY_FACTORY_TOKEN = object()
_RESULT_FACTORY_TOKEN = object()


class Form4ProvisionalLotDiagnosticsError(ValueError):
    """The bounded IB-2D diagnostic contract failed closed."""


class Form4ProvisionalLotDisposition(str, Enum):
    """Non-authoritative disposition for one exhaustive mapping row."""

    PROVISIONAL_GROUPING_CANDIDATE = "provisional_grouping_candidate"
    PROVISIONAL_QUARANTINE = "provisional_quarantine"


class Form4ProvisionalLotQuarantineReason(str, Enum):
    """Why one row cannot enter even the provisional diagnostic grouping."""

    AMENDMENT_FAMILY_REQUIRES_SUPERSESSION = (
        "amendment_family_requires_supersession"
    )
    UPSTREAM_PARSER_QUARANTINED = "upstream_parser_quarantined"
    UPSTREAM_IDENTITY_QUARANTINED = "upstream_identity_quarantined"
    OWNER_ATTRIBUTION_QUARANTINED = "owner_attribution_quarantined"
    SECURITY_MAPPING_QUARANTINED = "security_mapping_quarantined"
    ECONOMICS_UNAVAILABLE_QUARANTINED = "economics_unavailable_quarantined"
    NON_ORDINARY_EQUITY_CLASS_QUARANTINED = (
        "non_ordinary_equity_class_quarantined"
    )


class Form4ProvisionalLotThresholdDiagnostic(str, Enum):
    """Exact, non-authoritative USD 50,000 comparison for one group."""

    AT_OR_ABOVE_PROVISIONAL_MINIMUM = "at_or_above_provisional_minimum"
    BELOW_PROVISIONAL_MINIMUM = "below_provisional_minimum"


def _sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise Form4ProvisionalLotDiagnosticsError(
            f"REFUSED: {label} must be lowercase SHA-256"
        )
    return value


def _accession(value: object, *, label: str) -> str:
    if type(value) is not str or _ACCESSION_RE.fullmatch(value) is None:
        raise Form4ProvisionalLotDiagnosticsError(
            f"REFUSED: {label} must be a canonical accession"
        )
    return value


def _cik(value: object, *, label: str) -> str:
    if type(value) is not str or _CIK_RE.fullmatch(value) is None:
        raise Form4ProvisionalLotDiagnosticsError(
            f"REFUSED: {label} must be a ten-digit SEC CIK"
        )
    return value


def _canonical_utc_text(value: object, *, label: str) -> str:
    if type(value) is not str:
        raise Form4ProvisionalLotDiagnosticsError(
            f"REFUSED: {label} must be canonical UTC text"
        )
    try:
        parsed = datetime.fromisoformat(value)
        canonical = parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (OverflowError, TypeError, ValueError) as exc:
        raise Form4ProvisionalLotDiagnosticsError(
            f"REFUSED: {label} must be canonical UTC text"
        ) from exc
    if parsed.utcoffset() is None or parsed.microsecond != 0 or canonical != value:
        raise Form4ProvisionalLotDiagnosticsError(
            f"REFUSED: {label} must be canonical UTC text"
        )
    return value


def _decimal(value: object, *, label: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise Form4ProvisionalLotDiagnosticsError(
            f"REFUSED: {label} must be an exact finite Decimal"
        )
    decimal_tuple = value.as_tuple()
    if (
        len(decimal_tuple.digits) > _MAX_FORM4_PROVISIONAL_LOT_DECIMAL_DIGITS
        or abs(int(decimal_tuple.exponent))
        > _MAX_FORM4_PROVISIONAL_LOT_DECIMAL_ABS_EXPONENT
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            f"REFUSED: {label} exceeds the diagnostic Decimal bound"
        )
    try:
        decimal_text(value)
    except ValueError as exc:
        raise Form4ProvisionalLotDiagnosticsError(
            f"REFUSED: {label} exceeds exact Decimal bounds"
        ) from exc
    return value


def _optional_decimal(value: object, *, label: str) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value, label=label)


def _decimal_payload(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return decimal_text(_decimal(value, label="diagnostic decimal"))


def _group_key_payload(
    *,
    attributed_owner_cik: str,
    attributed_owner_candidate_id: str,
    security_id: str,
    share_class_id: str,
    transaction_date: date,
) -> dict[str, object]:
    return {
        "attributed_owner_cik": attributed_owner_cik,
        "attributed_owner_candidate_id": attributed_owner_candidate_id,
        "security_id": security_id,
        "share_class_id": share_class_id,
        "transaction_date": transaction_date.isoformat(),
    }


def _quarantine_reasons_from_state(
    *,
    amendment_family_has_supplied_amendment: bool,
    upstream_disposition: Form4ProvisionalDisposition,
    identity_disposition: Form4ObservedIdentityDisposition,
    owner_attribution_outcomes: tuple[Form4OwnerAttributionOutcome, ...],
    security_mapping_outcomes: tuple[Form4PitSecurityMappingOutcome, ...],
    attributed_owner_cik: str | None,
    attributed_owner_candidate_id: str | None,
    security_id: str | None,
    share_class_id: str | None,
    security_class_normalized: Form4SecurityClass | None,
    transaction_date: date | None,
    shares: Decimal | None,
    price_per_share: Decimal | None,
    purchase_value_usd: Decimal | None,
) -> tuple[Form4ProvisionalLotQuarantineReason, ...]:
    reasons: list[Form4ProvisionalLotQuarantineReason] = []
    if amendment_family_has_supplied_amendment:
        reasons.append(
            Form4ProvisionalLotQuarantineReason.AMENDMENT_FAMILY_REQUIRES_SUPERSESSION
        )
    if upstream_disposition is not (
        Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
    ):
        reasons.append(
            Form4ProvisionalLotQuarantineReason.UPSTREAM_PARSER_QUARANTINED
        )
    if identity_disposition is not (
        Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE
    ):
        reasons.append(
            Form4ProvisionalLotQuarantineReason.UPSTREAM_IDENTITY_QUARANTINED
        )
    if (
        owner_attribution_outcomes
        != (Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,)
        or attributed_owner_cik is None
        or attributed_owner_candidate_id is None
    ):
        reasons.append(
            Form4ProvisionalLotQuarantineReason.OWNER_ATTRIBUTION_QUARANTINED
        )
    if (
        security_mapping_outcomes
        != (Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY,)
        or security_id is None
        or share_class_id is None
        or transaction_date is None
    ):
        reasons.append(
            Form4ProvisionalLotQuarantineReason.SECURITY_MAPPING_QUARANTINED
        )
    if (
        security_class_normalized is not None
        and security_class_normalized
        not in {
            Form4SecurityClass.COMMON_STOCK,
            Form4SecurityClass.COMMON_SHARES,
            Form4SecurityClass.ORDINARY_SHARES,
        }
    ):
        reasons.append(
            Form4ProvisionalLotQuarantineReason.NON_ORDINARY_EQUITY_CLASS_QUARANTINED
        )
    if (
        shares is None
        or price_per_share is None
        or purchase_value_usd is None
        or shares <= 0
        or price_per_share <= 0
        or purchase_value_usd <= 0
    ):
        reasons.append(
            Form4ProvisionalLotQuarantineReason.ECONOMICS_UNAVAILABLE_QUARANTINED
        )
    return tuple(reasons)


@dataclass(frozen=True)
class Form4ProvisionalLotDiagnosticRow:
    """One exhaustive, reason-coded mapping-row diagnostic."""

    mapping_row_id: str
    transaction_attribution_id: str
    upstream_transaction_observation_id: str
    upstream_report_row_id: str
    transaction_payload_hash: str
    accession_number: str
    source_sha256: str
    row_index: int
    event_id: str
    accepted_at_utc: str
    document_type: str
    original_accession: str
    amends_accession: str | None
    amendment_family_has_supplied_amendment: bool
    issuer_cik: str
    attributed_owner_cik: str | None
    attributed_owner_candidate_id: str | None
    security_id: str | None
    share_class_id: str | None
    security_class_normalized: Form4SecurityClass | None
    transaction_date: date | None
    title_mapping_kind: Form4SecurityTitleMappingKind | None
    upstream_disposition: Form4ProvisionalDisposition
    identity_disposition: Form4ObservedIdentityDisposition
    owner_attribution_outcomes: tuple[Form4OwnerAttributionOutcome, ...]
    security_mapping_outcomes: tuple[Form4PitSecurityMappingOutcome, ...]
    parser_outcomes: tuple[ClassificationOutcome, ...]
    parser_diagnostics: tuple[TransactionDiagnostic, ...]
    shares: Decimal | None
    price_per_share: Decimal | None
    purchase_value_usd: Decimal | None
    provisional_group_key: str | None
    disposition: Form4ProvisionalLotDisposition
    quarantine_reasons: tuple[Form4ProvisionalLotQuarantineReason, ...]
    official_profile_compatibility_verified: bool
    official_amendment_link_verified: bool
    complete_amendment_coverage_verified: bool
    official_security_master_compatibility_verified: bool
    authenticated_amendment_supersession_verified: bool
    point_in_time_issuer_identity_verified: bool
    point_in_time_reporting_owner_identity_verified: bool
    point_in_time_security_identity_verified: bool
    point_in_time_transaction_identity_verified: bool
    ordinary_equity_classification_verified: bool
    deduplication_authorized: bool
    canonical_filter_authorized: bool
    lot_aggregation_authorized: bool
    post_aggregation_minimum_gate_authorized: bool
    sec_access_authorized: bool
    provider_access_authorized: bool
    outcomes_authorized: bool
    qc_execution_authorized: bool
    deployment_authorized: bool
    trading_authorized: bool
    authorized_outcome_looks: int
    consumed_outcome_looks: int
    diagnostic_row_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _ROW_FACTORY_TOKEN:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic row must be factory-created"
            )
        for label, value in (
            ("mapping row ID", self.mapping_row_id),
            ("transaction attribution ID", self.transaction_attribution_id),
            (
                "upstream transaction observation ID",
                self.upstream_transaction_observation_id,
            ),
            ("upstream report row ID", self.upstream_report_row_id),
            ("transaction payload hash", self.transaction_payload_hash),
            ("source hash", self.source_sha256),
            ("event ID", self.event_id),
            ("diagnostic row ID", self.diagnostic_row_id),
        ):
            _sha256(value, label=label)
        _accession(self.accession_number, label="diagnostic accession")
        _accession(self.original_accession, label="diagnostic original accession")
        if self.amends_accession is not None:
            _accession(self.amends_accession, label="diagnostic amended accession")
        if type(self.row_index) is not int or self.row_index < 0:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic row index is invalid"
            )
        _canonical_utc_text(self.accepted_at_utc, label="diagnostic acceptance")
        if type(self.document_type) is not str or self.document_type not in {
            "4",
            "4/A",
        }:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic document type is invalid"
            )
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
        if (
            not valid_lineage
            or type(self.amendment_family_has_supplied_amendment) is not bool
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic amendment lineage is invalid"
            )
        _cik(self.issuer_cik, label="diagnostic issuer CIK")
        if self.attributed_owner_cik is not None:
            _cik(self.attributed_owner_cik, label="diagnostic owner CIK")
        if self.attributed_owner_candidate_id is not None:
            _sha256(
                self.attributed_owner_candidate_id,
                label="diagnostic owner candidate ID",
            )
        for label, value in (
            ("diagnostic security ID", self.security_id),
            ("diagnostic share-class ID", self.share_class_id),
        ):
            if value is not None and (
                type(value) is not str
                or not value
                or value != value.strip()
                or len(value) > 128
            ):
                raise Form4ProvisionalLotDiagnosticsError(
                    f"REFUSED: {label} is invalid"
                )
        if (
            self.transaction_date is not None
            and type(self.transaction_date) is not date
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic transaction date is invalid"
            )
        if (
            self.security_class_normalized is not None
            and type(self.security_class_normalized) is not Form4SecurityClass
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic security class is invalid"
            )
        if (
            self.title_mapping_kind is not None
            and type(self.title_mapping_kind)
            is not Form4SecurityTitleMappingKind
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic title mapping kind is invalid"
            )
        if (
            type(self.upstream_disposition) is not Form4ProvisionalDisposition
            or type(self.identity_disposition) is not Form4ObservedIdentityDisposition
            or type(self.owner_attribution_outcomes) is not tuple
            or not self.owner_attribution_outcomes
            or len(self.owner_attribution_outcomes) > len(Form4OwnerAttributionOutcome)
            or any(
                type(item) is not Form4OwnerAttributionOutcome
                for item in self.owner_attribution_outcomes
            )
            or len(set(self.owner_attribution_outcomes))
            != len(self.owner_attribution_outcomes)
            or type(self.security_mapping_outcomes) is not tuple
            or not self.security_mapping_outcomes
            or len(self.security_mapping_outcomes) > len(Form4PitSecurityMappingOutcome)
            or any(
                type(item) is not Form4PitSecurityMappingOutcome
                for item in self.security_mapping_outcomes
            )
            or len(set(self.security_mapping_outcomes))
            != len(self.security_mapping_outcomes)
            or type(self.parser_outcomes) is not tuple
            or not self.parser_outcomes
            or len(self.parser_outcomes) > len(ClassificationOutcome)
            or any(
                type(item) is not ClassificationOutcome
                for item in self.parser_outcomes
            )
            or len(set(self.parser_outcomes)) != len(self.parser_outcomes)
            or type(self.parser_diagnostics) is not tuple
            or len(self.parser_diagnostics) > len(TransactionDiagnostic)
            or any(
                type(item) is not TransactionDiagnostic
                for item in self.parser_diagnostics
            )
            or len(set(self.parser_diagnostics)) != len(self.parser_diagnostics)
            or type(self.disposition) is not Form4ProvisionalLotDisposition
            or type(self.quarantine_reasons) is not tuple
            or len(self.quarantine_reasons) > len(Form4ProvisionalLotQuarantineReason)
            or any(
                type(item) is not Form4ProvisionalLotQuarantineReason
                for item in self.quarantine_reasons
            )
            or len(set(self.quarantine_reasons)) != len(self.quarantine_reasons)
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic dispositions are invalid"
            )
        owner_is_attributed = self.owner_attribution_outcomes == (
            Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED,
        )
        if owner_is_attributed:
            if (
                self.attributed_owner_cik is None
                or self.attributed_owner_candidate_id is None
            ):
                raise Form4ProvisionalLotDiagnosticsError(
                    "REFUSED: attributed owner state is incomplete"
                )
        elif (
            self.attributed_owner_cik is not None
            or self.attributed_owner_candidate_id is not None
            or Form4OwnerAttributionOutcome.SINGLE_COMPLETE_OWNER_CIK_ATTRIBUTED
            in self.owner_attribution_outcomes
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: upstream owner quarantine was promoted"
            )
        mapping_is_resolved = self.security_mapping_outcomes == (
            Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY,
        )
        retained_mapping_fields = (
            self.security_id,
            self.share_class_id,
            self.security_class_normalized,
            self.title_mapping_kind,
        )
        if mapping_is_resolved:
            if (
                any(value is None for value in retained_mapping_fields)
                or self.transaction_date is None
            ):
                raise Form4ProvisionalLotDiagnosticsError(
                    "REFUSED: mapped diagnostic state is incomplete"
                )
        elif (
            any(value is not None for value in retained_mapping_fields)
            or Form4PitSecurityMappingOutcome.MAPPED_STRUCTURALLY
            in self.security_mapping_outcomes
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: upstream mapping quarantine was promoted"
            )
        expected_identity_disposition = (
            Form4ObservedIdentityDisposition.UNRESOLVED_PROVISIONAL_CANDIDATE
            if self.upstream_disposition
            is Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
            else Form4ObservedIdentityDisposition.UNRESOLVED_QUARANTINE
        )
        parser_is_candidate = self.parser_outcomes == (
            ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,
        )
        if (
            self.identity_disposition is not expected_identity_disposition
            or parser_is_candidate
            != (
                self.upstream_disposition
                is Form4ProvisionalDisposition.PROVISIONAL_PRE_AGGREGATION_CANDIDATE
            )
            or (
                ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION
                in self.parser_outcomes
                and not parser_is_candidate
            )
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic parser and identity dispositions disagree"
            )
        authority = (
            self.official_profile_compatibility_verified,
            self.official_amendment_link_verified,
            self.complete_amendment_coverage_verified,
            self.official_security_master_compatibility_verified,
            self.authenticated_amendment_supersession_verified,
            self.point_in_time_issuer_identity_verified,
            self.point_in_time_reporting_owner_identity_verified,
            self.point_in_time_security_identity_verified,
            self.point_in_time_transaction_identity_verified,
            self.ordinary_equity_classification_verified,
            self.deduplication_authorized,
            self.canonical_filter_authorized,
            self.lot_aggregation_authorized,
            self.post_aggregation_minimum_gate_authorized,
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
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic row claims authority"
            )
        _optional_decimal(self.shares, label="diagnostic shares")
        _optional_decimal(self.price_per_share, label="diagnostic price")
        _optional_decimal(self.purchase_value_usd, label="diagnostic purchase value")
        if self.shares is None or self.price_per_share is None:
            if self.purchase_value_usd is not None:
                raise Form4ProvisionalLotDiagnosticsError(
                    "REFUSED: diagnostic economics are inconsistent"
                )
        else:
            try:
                expected_value = exact_decimal_multiply(
                    self.shares,
                    self.price_per_share,
                    name="Form 4 diagnostic purchase value",
                )
            except ValueError as exc:
                raise Form4ProvisionalLotDiagnosticsError(
                    "REFUSED: diagnostic economics exceed exact bounds"
                ) from exc
            if self.purchase_value_usd != expected_value:
                raise Form4ProvisionalLotDiagnosticsError(
                    "REFUSED: diagnostic economics are inconsistent"
                )
        expected_reasons = _quarantine_reasons_from_state(
            amendment_family_has_supplied_amendment=(
                self.amendment_family_has_supplied_amendment
            ),
            upstream_disposition=self.upstream_disposition,
            identity_disposition=self.identity_disposition,
            owner_attribution_outcomes=self.owner_attribution_outcomes,
            security_mapping_outcomes=self.security_mapping_outcomes,
            attributed_owner_cik=self.attributed_owner_cik,
            attributed_owner_candidate_id=self.attributed_owner_candidate_id,
            security_id=self.security_id,
            share_class_id=self.share_class_id,
            security_class_normalized=self.security_class_normalized,
            transaction_date=self.transaction_date,
            shares=self.shares,
            price_per_share=self.price_per_share,
            purchase_value_usd=self.purchase_value_usd,
        )
        expected_disposition = (
            Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
            if not expected_reasons
            else Form4ProvisionalLotDisposition.PROVISIONAL_QUARANTINE
        )
        if (
            self.quarantine_reasons != expected_reasons
            or self.disposition is not expected_disposition
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic routing is inconsistent"
            )
        if expected_disposition is (
            Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
        ):
            assert self.attributed_owner_cik is not None
            assert self.attributed_owner_candidate_id is not None
            assert self.security_id is not None
            assert self.share_class_id is not None
            assert self.transaction_date is not None
            expected_group_key = hash_payload(
                _group_key_payload(
                    attributed_owner_cik=self.attributed_owner_cik,
                    attributed_owner_candidate_id=self.attributed_owner_candidate_id,
                    security_id=self.security_id,
                    share_class_id=self.share_class_id,
                    transaction_date=self.transaction_date,
                )
            )
        else:
            expected_group_key = None
        if self.provisional_group_key != expected_group_key:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic group key is inconsistent"
            )
        if self.diagnostic_row_id != hash_payload(self.lineage_payload()):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostic row ID is invalid"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "mapping_row_id": self.mapping_row_id,
            "transaction_attribution_id": self.transaction_attribution_id,
            "upstream_transaction_observation_id": (
                self.upstream_transaction_observation_id
            ),
            "upstream_report_row_id": self.upstream_report_row_id,
            "transaction_payload_hash": self.transaction_payload_hash,
            "accession_number": self.accession_number,
            "source_sha256": self.source_sha256,
            "row_index": self.row_index,
            "event_id": self.event_id,
            "accepted_at_utc": self.accepted_at_utc,
            "document_type": self.document_type,
            "original_accession": self.original_accession,
            "amends_accession": self.amends_accession,
            "amendment_family_has_supplied_amendment": (
                self.amendment_family_has_supplied_amendment
            ),
            "issuer_cik": self.issuer_cik,
            "attributed_owner_cik": self.attributed_owner_cik,
            "attributed_owner_candidate_id": self.attributed_owner_candidate_id,
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "security_class_normalized": (
                None
                if self.security_class_normalized is None
                else self.security_class_normalized.value
            ),
            "transaction_date": (
                None
                if self.transaction_date is None
                else self.transaction_date.isoformat()
            ),
            "title_mapping_kind": (
                None
                if self.title_mapping_kind is None
                else self.title_mapping_kind.value
            ),
            "upstream_disposition": self.upstream_disposition.value,
            "identity_disposition": self.identity_disposition.value,
            "owner_attribution_outcomes": [
                item.value for item in self.owner_attribution_outcomes
            ],
            "security_mapping_outcomes": [
                item.value for item in self.security_mapping_outcomes
            ],
            "parser_outcomes": [item.value for item in self.parser_outcomes],
            "parser_diagnostics": [item.value for item in self.parser_diagnostics],
            "shares": _decimal_payload(self.shares),
            "price_per_share": _decimal_payload(self.price_per_share),
            "purchase_value_usd": _decimal_payload(self.purchase_value_usd),
            "provisional_group_key": self.provisional_group_key,
            "disposition": self.disposition.value,
            "quarantine_reasons": [item.value for item in self.quarantine_reasons],
            "official_profile_compatibility_verified": False,
            "official_amendment_link_verified": False,
            "complete_amendment_coverage_verified": False,
            "official_security_master_compatibility_verified": False,
            "authenticated_amendment_supersession_verified": False,
            "point_in_time_issuer_identity_verified": False,
            "point_in_time_reporting_owner_identity_verified": False,
            "point_in_time_security_identity_verified": False,
            "point_in_time_transaction_identity_verified": False,
            "ordinary_equity_classification_verified": False,
            "deduplication_authorized": False,
            "canonical_filter_authorized": False,
            "lot_aggregation_authorized": False,
            "post_aggregation_minimum_gate_authorized": False,
            "sec_access_authorized": False,
            "provider_access_authorized": False,
            "outcomes_authorized": False,
            "qc_execution_authorized": False,
            "deployment_authorized": False,
            "trading_authorized": False,
            "authorized_outcome_looks": 0,
            "consumed_outcome_looks": 0,
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.lineage_payload(), "diagnostic_row_id": self.diagnostic_row_id}


@dataclass(frozen=True)
class Form4ProvisionalLotGroup:
    """A non-authoritative exact grouping of retained candidate members."""

    provisional_group_key: str
    issuer_cik: str
    attributed_owner_cik: str
    attributed_owner_candidate_id: str
    security_id: str
    share_class_id: str
    transaction_date: date
    member_row_ids: tuple[str, ...]
    member_count: int
    total_shares: Decimal
    total_purchase_value_usd: Decimal
    latest_member_accepted_at_utc: str
    threshold_usd: Decimal
    threshold_diagnostic: Form4ProvisionalLotThresholdDiagnostic
    meets_provisional_minimum_purchase_value: bool
    official_profile_compatibility_verified: bool
    official_amendment_link_verified: bool
    complete_amendment_coverage_verified: bool
    official_security_master_compatibility_verified: bool
    authenticated_amendment_supersession_verified: bool
    point_in_time_issuer_identity_verified: bool
    point_in_time_reporting_owner_identity_verified: bool
    point_in_time_security_identity_verified: bool
    point_in_time_transaction_identity_verified: bool
    ordinary_equity_classification_verified: bool
    deduplication_authorized: bool
    canonical_filter_authorized: bool
    lot_aggregation_authorized: bool
    post_aggregation_minimum_gate_authorized: bool
    sec_access_authorized: bool
    provider_access_authorized: bool
    outcomes_authorized: bool
    qc_execution_authorized: bool
    deployment_authorized: bool
    trading_authorized: bool
    authorized_outcome_looks: int
    consumed_outcome_looks: int
    provisional_group_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _GROUP_FACTORY_TOKEN:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: provisional group must be factory-created"
            )
        _sha256(self.provisional_group_key, label="provisional group key")
        _cik(self.issuer_cik, label="group issuer CIK")
        _cik(self.attributed_owner_cik, label="group owner CIK")
        _sha256(
            self.attributed_owner_candidate_id,
            label="group owner candidate ID",
        )
        for label, value in (
            ("group security ID", self.security_id),
            ("group share-class ID", self.share_class_id),
        ):
            if (
                type(value) is not str
                or not value
                or value != value.strip()
                or len(value) > 128
            ):
                raise Form4ProvisionalLotDiagnosticsError(
                    f"REFUSED: {label} is invalid"
                )
        if type(self.transaction_date) is not date:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: group transaction date is invalid"
            )
        expected_key = hash_payload(
            _group_key_payload(
                attributed_owner_cik=self.attributed_owner_cik,
                attributed_owner_candidate_id=self.attributed_owner_candidate_id,
                security_id=self.security_id,
                share_class_id=self.share_class_id,
                transaction_date=self.transaction_date,
            )
        )
        if self.provisional_group_key != expected_key:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: provisional group key is invalid"
            )
        if (
            type(self.member_row_ids) is not tuple
            or not self.member_row_ids
            or len(self.member_row_ids) > MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
            or any(
                type(item) is not str or _SHA256_RE.fullmatch(item) is None
                for item in self.member_row_ids
            )
            or self.member_row_ids != tuple(sorted(self.member_row_ids))
            or len(set(self.member_row_ids)) != len(self.member_row_ids)
            or type(self.member_count) is not int
            or self.member_count != len(self.member_row_ids)
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: provisional group member inventory is invalid"
            )
        _decimal(self.total_shares, label="group total shares")
        _decimal(self.total_purchase_value_usd, label="group total purchase value")
        _decimal(self.threshold_usd, label="group threshold")
        if (
            self.total_shares <= 0
            or self.total_purchase_value_usd <= 0
            or self.threshold_usd != FORM4_PROVISIONAL_LOT_THRESHOLD_USD
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: provisional group economics are invalid"
            )
        _canonical_utc_text(
            self.latest_member_accepted_at_utc,
            label="latest group member acceptance",
        )
        expected_met = self.total_purchase_value_usd >= self.threshold_usd
        expected_diagnostic = (
            Form4ProvisionalLotThresholdDiagnostic.AT_OR_ABOVE_PROVISIONAL_MINIMUM
            if expected_met
            else Form4ProvisionalLotThresholdDiagnostic.BELOW_PROVISIONAL_MINIMUM
        )
        if (
            type(self.threshold_diagnostic)
            is not Form4ProvisionalLotThresholdDiagnostic
            or type(self.meets_provisional_minimum_purchase_value) is not bool
            or self.meets_provisional_minimum_purchase_value is not expected_met
            or self.threshold_diagnostic is not expected_diagnostic
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: provisional threshold diagnostic is inconsistent"
            )
        authority = (
            self.official_profile_compatibility_verified,
            self.official_amendment_link_verified,
            self.complete_amendment_coverage_verified,
            self.official_security_master_compatibility_verified,
            self.authenticated_amendment_supersession_verified,
            self.point_in_time_issuer_identity_verified,
            self.point_in_time_reporting_owner_identity_verified,
            self.point_in_time_security_identity_verified,
            self.point_in_time_transaction_identity_verified,
            self.ordinary_equity_classification_verified,
            self.deduplication_authorized,
            self.canonical_filter_authorized,
            self.lot_aggregation_authorized,
            self.post_aggregation_minimum_gate_authorized,
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
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: provisional group claims authority"
            )
        _sha256(self.provisional_group_id, label="provisional group ID")
        if self.provisional_group_id != hash_payload(self.lineage_payload()):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: provisional group ID is invalid"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            "provisional_group_key": self.provisional_group_key,
            "issuer_cik": self.issuer_cik,
            "attributed_owner_cik": self.attributed_owner_cik,
            "attributed_owner_candidate_id": self.attributed_owner_candidate_id,
            "security_id": self.security_id,
            "share_class_id": self.share_class_id,
            "transaction_date": self.transaction_date.isoformat(),
            "member_row_ids": list(self.member_row_ids),
            "member_count": self.member_count,
            "total_shares": decimal_text(self.total_shares),
            "total_purchase_value_usd": decimal_text(
                self.total_purchase_value_usd
            ),
            "latest_member_accepted_at_utc": self.latest_member_accepted_at_utc,
            "threshold_usd": decimal_text(self.threshold_usd),
            "threshold_diagnostic": self.threshold_diagnostic.value,
            "meets_provisional_minimum_purchase_value": (
                self.meets_provisional_minimum_purchase_value
            ),
            "official_profile_compatibility_verified": False,
            "official_amendment_link_verified": False,
            "complete_amendment_coverage_verified": False,
            "official_security_master_compatibility_verified": False,
            "authenticated_amendment_supersession_verified": False,
            "point_in_time_issuer_identity_verified": False,
            "point_in_time_reporting_owner_identity_verified": False,
            "point_in_time_security_identity_verified": False,
            "point_in_time_transaction_identity_verified": False,
            "ordinary_equity_classification_verified": False,
            "deduplication_authorized": False,
            "canonical_filter_authorized": False,
            "lot_aggregation_authorized": False,
            "post_aggregation_minimum_gate_authorized": False,
            "sec_access_authorized": False,
            "provider_access_authorized": False,
            "outcomes_authorized": False,
            "qc_execution_authorized": False,
            "deployment_authorized": False,
            "trading_authorized": False,
            "authorized_outcome_looks": 0,
            "consumed_outcome_looks": 0,
        }

    def to_payload(self) -> dict[str, object]:
        return {
            **self.lineage_payload(),
            "provisional_group_id": self.provisional_group_id,
        }


@dataclass(frozen=True)
class Form4ProvisionalLotDiagnosticsIdentity:
    """Hash-bound lineage and zero-authority status for one IB-2D result."""

    contract_version: str
    builder_git_commit: str
    upstream_mapping_id: str
    upstream_mapping_identity_hash: str
    upstream_mapping_fingerprint: str
    upstream_mapping_runtime_fingerprint: str
    upstream_grouping_id: str
    upstream_grouping_identity_hash: str
    upstream_grouping_fingerprint: str
    upstream_grouping_runtime_fingerprint: str
    upstream_inventory_id: str
    upstream_inventory_identity_hash: str
    upstream_inventory_fingerprint: str
    upstream_inventory_runtime_fingerprint: str
    upstream_evidence_id: str
    upstream_evidence_identity_hash: str
    upstream_evidence_runtime_fingerprint: str
    rebuilt_report_id: str
    rebuilt_report_identity_hash: str
    rebuilt_report_row_inventory_hash: str
    amendment_family_inventory_hash: str
    diagnostic_row_inventory_hash: str
    provisional_group_inventory_hash: str
    mapping_row_count: int
    provisional_candidate_row_count: int
    quarantined_row_count: int
    provisional_group_count: int
    threshold_met_group_count: int
    below_threshold_group_count: int
    amendment_family_quarantined_count: int
    amendment_family_quarantined_row_count: int
    manual_exception_candidate_row_count: int
    official_profile_compatibility_verified: bool
    official_amendment_link_verified: bool
    complete_amendment_coverage_verified: bool
    official_security_master_compatibility_verified: bool
    authenticated_amendment_supersession_verified: bool
    point_in_time_issuer_identity_verified: bool
    point_in_time_reporting_owner_identity_verified: bool
    point_in_time_security_identity_verified: bool
    point_in_time_transaction_identity_verified: bool
    ordinary_equity_classification_verified: bool
    deduplication_authorized: bool
    canonical_filter_authorized: bool
    lot_aggregation_authorized: bool
    post_aggregation_minimum_gate_authorized: bool
    sec_access_authorized: bool
    provider_access_authorized: bool
    outcomes_authorized: bool
    qc_execution_authorized: bool
    deployment_authorized: bool
    trading_authorized: bool
    authorized_outcome_looks: int
    consumed_outcome_looks: int
    diagnostics_id: str
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _IDENTITY_FACTORY_TOKEN:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics identity must be factory-created"
            )
        if (
            self.contract_version != FORM4_PROVISIONAL_LOT_DIAGNOSTICS_VERSION
            or type(self.builder_git_commit) is not str
            or _GIT_COMMIT_RE.fullmatch(self.builder_git_commit) is None
            or type(self.upstream_mapping_id) is not str
            or not self.upstream_mapping_id
            or type(self.upstream_grouping_id) is not str
            or not self.upstream_grouping_id
            or type(self.upstream_inventory_id) is not str
            or not self.upstream_inventory_id
            or type(self.upstream_evidence_id) is not str
            or not self.upstream_evidence_id
            or type(self.rebuilt_report_id) is not str
            or not self.rebuilt_report_id
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics identity lineage is invalid"
            )
        for label, value in (
            ("upstream mapping identity hash", self.upstream_mapping_identity_hash),
            ("upstream mapping fingerprint", self.upstream_mapping_fingerprint),
            (
                "upstream mapping runtime fingerprint",
                self.upstream_mapping_runtime_fingerprint,
            ),
            ("upstream grouping identity hash", self.upstream_grouping_identity_hash),
            ("upstream grouping fingerprint", self.upstream_grouping_fingerprint),
            (
                "upstream grouping runtime fingerprint",
                self.upstream_grouping_runtime_fingerprint,
            ),
            ("upstream inventory identity hash", self.upstream_inventory_identity_hash),
            ("upstream inventory fingerprint", self.upstream_inventory_fingerprint),
            (
                "upstream inventory runtime fingerprint",
                self.upstream_inventory_runtime_fingerprint,
            ),
            ("upstream evidence identity hash", self.upstream_evidence_identity_hash),
            (
                "upstream evidence runtime fingerprint",
                self.upstream_evidence_runtime_fingerprint,
            ),
            ("rebuilt report identity hash", self.rebuilt_report_identity_hash),
            (
                "rebuilt report row inventory hash",
                self.rebuilt_report_row_inventory_hash,
            ),
            ("amendment family inventory hash", self.amendment_family_inventory_hash),
            ("diagnostic row inventory hash", self.diagnostic_row_inventory_hash),
            ("provisional group inventory hash", self.provisional_group_inventory_hash),
        ):
            _sha256(value, label=label)
        counts = (
            self.mapping_row_count,
            self.provisional_candidate_row_count,
            self.quarantined_row_count,
            self.provisional_group_count,
            self.threshold_met_group_count,
            self.below_threshold_group_count,
            self.amendment_family_quarantined_count,
            self.amendment_family_quarantined_row_count,
            self.manual_exception_candidate_row_count,
        )
        if (
            any(
                type(value) is not int
                or not 0 <= value <= MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
                for value in counts
            )
            or self.provisional_candidate_row_count + self.quarantined_row_count
            != self.mapping_row_count
            or self.threshold_met_group_count + self.below_threshold_group_count
            != self.provisional_group_count
            or self.provisional_group_count > self.provisional_candidate_row_count
            or self.amendment_family_quarantined_row_count > self.quarantined_row_count
            or self.amendment_family_quarantined_count
            > MAX_FORM4_OBSERVED_IDENTITY_FILINGS
            or self.manual_exception_candidate_row_count
            > self.provisional_candidate_row_count
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics identity counts are invalid"
            )
        authority = (
            self.official_profile_compatibility_verified,
            self.official_amendment_link_verified,
            self.complete_amendment_coverage_verified,
            self.official_security_master_compatibility_verified,
            self.authenticated_amendment_supersession_verified,
            self.point_in_time_issuer_identity_verified,
            self.point_in_time_reporting_owner_identity_verified,
            self.point_in_time_security_identity_verified,
            self.point_in_time_transaction_identity_verified,
            self.ordinary_equity_classification_verified,
            self.deduplication_authorized,
            self.canonical_filter_authorized,
            self.lot_aggregation_authorized,
            self.post_aggregation_minimum_gate_authorized,
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
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics identity claims authority"
            )
        match = (
            _DIAGNOSTICS_ID_RE.fullmatch(self.diagnostics_id)
            if type(self.diagnostics_id) is str
            else None
        )
        if (
            match is None
            or match.group("hash_prefix")
            != hash_payload(self.lineage_payload())[:16]
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics ID is invalid"
            )

    def lineage_payload(self) -> dict[str, object]:
        return {
            item.name: (
                False
                if item.name.endswith("_verified")
                or item.name.endswith("_authorized")
                else 0
                if item.name in {"authorized_outcome_looks", "consumed_outcome_looks"}
                else getattr(self, item.name)
            )
            for item in fields(type(self))
            if item.name != "diagnostics_id"
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.lineage_payload(), "diagnostics_id": self.diagnostics_id}


@dataclass(frozen=True)
class Form4ProvisionalLotDiagnostics:
    """One exhaustive row inventory and its provisional diagnostic groups."""

    identity: Form4ProvisionalLotDiagnosticsIdentity
    amendment_family_original_accessions: tuple[str, ...]
    rows: tuple[Form4ProvisionalLotDiagnosticRow, ...]
    groups: tuple[Form4ProvisionalLotGroup, ...]
    _verified_factory_token: InitVar[object] = None

    def __post_init__(self, _verified_factory_token: object) -> None:
        if _verified_factory_token is not _RESULT_FACTORY_TOKEN:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics result must be factory-created"
            )
        if (
            type(self.identity) is not Form4ProvisionalLotDiagnosticsIdentity
            or type(self.amendment_family_original_accessions) is not tuple
            or type(self.rows) is not tuple
            or type(self.groups) is not tuple
            or len(self.amendment_family_original_accessions)
            > MAX_FORM4_OBSERVED_IDENTITY_FILINGS
            or len(self.rows) > MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
            or len(self.groups) > MAX_FORM4_PROVISIONAL_LOT_GROUPS
            or any(
                type(item) is not Form4ProvisionalLotDiagnosticRow
                for item in self.rows
            )
            or any(type(item) is not Form4ProvisionalLotGroup for item in self.groups)
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics result state is invalid"
            )
        if (
            any(
                type(item) is not str or _ACCESSION_RE.fullmatch(item) is None
                for item in self.amendment_family_original_accessions
            )
            or self.amendment_family_original_accessions
            != tuple(sorted(set(self.amendment_family_original_accessions)))
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: amendment family quarantine inventory is invalid"
            )
        Form4ProvisionalLotDiagnosticsIdentity.__post_init__(
            self.identity,
            _IDENTITY_FACTORY_TOKEN,
        )
        for item in self.rows:
            Form4ProvisionalLotDiagnosticRow.__post_init__(item, _ROW_FACTORY_TOKEN)
        for item in self.groups:
            Form4ProvisionalLotGroup.__post_init__(item, _GROUP_FACTORY_TOKEN)
        row_keys = tuple(_diagnostic_row_sort_key(item) for item in self.rows)
        group_keys = tuple(_provisional_group_sort_key(item) for item in self.groups)
        if (
            row_keys != tuple(sorted(row_keys))
            or group_keys != tuple(sorted(group_keys))
            or len({item.mapping_row_id for item in self.rows}) != len(self.rows)
            or len({item.diagnostic_row_id for item in self.rows}) != len(self.rows)
            or len({item.provisional_group_key for item in self.groups})
            != len(self.groups)
            or len({item.provisional_group_id for item in self.groups})
            != len(self.groups)
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics order or uniqueness is invalid"
            )
        replayed_groups = _aggregate_provisional_groups(self.rows)
        if [item.to_payload() for item in replayed_groups] != [
            item.to_payload() for item in self.groups
        ]:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: provisional groups do not replay from rows"
            )
        candidate_count = sum(
            item.disposition
            is Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
            for item in self.rows
        )
        threshold_met_count = sum(
            item.meets_provisional_minimum_purchase_value for item in self.groups
        )
        amended_family_set = set(self.amendment_family_original_accessions)
        amendment_row_count = sum(
            item.amendment_family_has_supplied_amendment for item in self.rows
        )
        manual_count = sum(
            item.disposition
            is Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
            and item.title_mapping_kind
            is Form4SecurityTitleMappingKind.MANUAL_EXCEPTION
            for item in self.rows
        )
        identity = self.identity
        if (
            identity.mapping_row_count != len(self.rows)
            or identity.provisional_candidate_row_count != candidate_count
            or identity.quarantined_row_count != len(self.rows) - candidate_count
            or identity.provisional_group_count != len(self.groups)
            or identity.threshold_met_group_count != threshold_met_count
            or identity.below_threshold_group_count
            != len(self.groups) - threshold_met_count
            or identity.amendment_family_quarantined_count
            != len(self.amendment_family_original_accessions)
            or identity.amendment_family_quarantined_row_count != amendment_row_count
            or identity.manual_exception_candidate_row_count != manual_count
            or identity.diagnostic_row_inventory_hash
            != hash_payload([item.to_payload() for item in self.rows])
            or identity.amendment_family_inventory_hash
            != hash_payload(list(self.amendment_family_original_accessions))
            or identity.provisional_group_inventory_hash
            != hash_payload([item.to_payload() for item in self.groups])
            or any(
                item.amendment_family_has_supplied_amendment
                is not (item.original_accession in amended_family_set)
                for item in self.rows
            )
            or any(
                item.document_type == "4/A"
                and item.original_accession not in amended_family_set
                for item in self.rows
            )
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics counts or hashes are inconsistent"
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
    def official_security_master_compatibility_verified(self) -> bool:
        return False

    @property
    def authenticated_amendment_supersession_verified(self) -> bool:
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
    def deduplication_authorized(self) -> bool:
        return False

    @property
    def canonical_filter_authorized(self) -> bool:
        return False

    @property
    def lot_aggregation_authorized(self) -> bool:
        return False

    @property
    def post_aggregation_minimum_gate_authorized(self) -> bool:
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
            "amendment_family_original_accessions": list(
                self.amendment_family_original_accessions
            ),
            "rows": [item.to_payload() for item in self.rows],
            "groups": [item.to_payload() for item in self.groups],
        }


def _diagnostic_row_sort_key(item: Form4ProvisionalLotDiagnosticRow) -> tuple:
    return (
        item.accession_number,
        item.source_sha256,
        item.row_index,
        item.event_id,
        item.mapping_row_id,
    )


def _provisional_group_sort_key(item: Form4ProvisionalLotGroup) -> tuple:
    return (
        item.attributed_owner_cik,
        item.attributed_owner_candidate_id,
        item.security_id,
        item.share_class_id,
        item.transaction_date,
        item.provisional_group_key,
    )


def _zero_authority_payload() -> dict[str, object]:
    return {
        "official_profile_compatibility_verified": False,
        "official_amendment_link_verified": False,
        "complete_amendment_coverage_verified": False,
        "official_security_master_compatibility_verified": False,
        "authenticated_amendment_supersession_verified": False,
        "point_in_time_issuer_identity_verified": False,
        "point_in_time_reporting_owner_identity_verified": False,
        "point_in_time_security_identity_verified": False,
        "point_in_time_transaction_identity_verified": False,
        "ordinary_equity_classification_verified": False,
        "deduplication_authorized": False,
        "canonical_filter_authorized": False,
        "lot_aggregation_authorized": False,
        "post_aggregation_minimum_gate_authorized": False,
        "sec_access_authorized": False,
        "provider_access_authorized": False,
        "outcomes_authorized": False,
        "qc_execution_authorized": False,
        "deployment_authorized": False,
        "trading_authorized": False,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }


@dataclass
class _OutputProjectionBudget:
    nodes: int = 0
    text_characters: int = 0
    active_ids: set[int] | None = None

    def __post_init__(self) -> None:
        if self.active_ids is None:
            self.active_ids = set()


_OUTPUT_CONTRACT_TYPES = (
    Form4ProvisionalLotDiagnosticRow,
    Form4ProvisionalLotGroup,
    Form4ProvisionalLotDiagnosticsIdentity,
    Form4ProvisionalLotDiagnostics,
)


def _project_output(
    value: object,
    *,
    budget: _OutputProjectionBudget | None = None,
    depth: int = 0,
) -> object:
    """Project internally built state without depending on ambient Decimal."""

    if budget is None:
        budget = _OutputProjectionBudget()
    if depth > MAX_FORM4_PROVISIONAL_LOT_PROJECTION_DEPTH:
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: output projection exceeds the depth bound"
        )
    budget.nodes += 1
    if budget.nodes > MAX_FORM4_PROVISIONAL_LOT_PROJECTION_NODES:
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: output projection exceeds the node bound"
        )
    value_type = type(value)
    if value_type in {
        Form4ProvisionalLotDisposition,
        Form4ProvisionalLotQuarantineReason,
        Form4ProvisionalLotThresholdDiagnostic,
        Form4SecurityClass,
        Form4SecurityTitleMappingKind,
        Form4ProvisionalDisposition,
        Form4ObservedIdentityDisposition,
        Form4OwnerAttributionOutcome,
        Form4PitSecurityMappingOutcome,
        ClassificationOutcome,
        TransactionDiagnostic,
    }:
        return _project_output(value.value, budget=budget, depth=depth + 1)
    if value_type is Decimal:
        projected_decimal = decimal_text(
            _decimal(value, label="output projection Decimal")
        )
        budget.text_characters += len(projected_decimal)
        if budget.text_characters > MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: output projection exceeds the text bound"
            )
        return projected_decimal
    if value_type is date:
        return value.isoformat()
    if value_type is str:
        budget.text_characters += len(value)
        if budget.text_characters > MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: output projection exceeds the text bound"
            )
        return value
    if value is None or value_type in {bool, int}:
        return value
    if (
        value_type is tuple
        or value_type is list
        or value_type in _OUTPUT_CONTRACT_TYPES
    ):
        active_ids = budget.active_ids
        assert active_ids is not None
        value_id = id(value)
        if value_id in active_ids:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: output projection contains a cycle"
            )
        active_ids.add(value_id)
        try:
            if value_type is tuple or value_type is list:
                return [
                    _project_output(item, budget=budget, depth=depth + 1)
                    for item in value
                ]
            declared = {item.name for item in fields(value_type)}
            state = object.__getattribute__(value, "__dict__")
            if type(state) is not dict or set(state) != declared:
                raise Form4ProvisionalLotDiagnosticsError(
                    "REFUSED: output contract state is not exact"
                )
            return {
                item.name: _project_output(
                    state[item.name],
                    budget=budget,
                    depth=depth + 1,
                )
                for item in fields(value_type)
            }
        finally:
            active_ids.remove(value_id)
    if value_type is dict:
        if any(type(key) is not str for key in value):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: output projection has a non-text key"
            )
        active_ids = budget.active_ids
        assert active_ids is not None
        value_id = id(value)
        if value_id in active_ids:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: output projection contains a cycle"
            )
        active_ids.add(value_id)
        try:
            return {
                key: _project_output(item, budget=budget, depth=depth + 1)
                for key, item in value.items()
            }
        finally:
            active_ids.remove(value_id)
    raise Form4ProvisionalLotDiagnosticsError(
        "REFUSED: output projection contains an unsupported value"
    )


def _aggregate_provisional_groups(
    rows: tuple[Form4ProvisionalLotDiagnosticRow, ...],
) -> tuple[Form4ProvisionalLotGroup, ...]:
    buckets: dict[str, list[Form4ProvisionalLotDiagnosticRow]] = {}
    for row in rows:
        if row.disposition is Form4ProvisionalLotDisposition.PROVISIONAL_QUARANTINE:
            continue
        if row.provisional_group_key is None:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: candidate row lacks a provisional group key"
            )
        buckets.setdefault(row.provisional_group_key, []).append(row)
    groups: list[Form4ProvisionalLotGroup] = []
    for group_key, members in buckets.items():
        first = members[0]
        if (
            first.attributed_owner_cik is None
            or first.attributed_owner_candidate_id is None
            or first.security_id is None
            or first.share_class_id is None
            or first.transaction_date is None
            or first.shares is None
            or first.purchase_value_usd is None
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: candidate member lacks complete grouping state"
            )
        dimensions = (
            first.issuer_cik,
            first.attributed_owner_cik,
            first.attributed_owner_candidate_id,
            first.security_id,
            first.share_class_id,
            first.transaction_date,
        )
        if any(
            (
                item.issuer_cik,
                item.attributed_owner_cik,
                item.attributed_owner_candidate_id,
                item.security_id,
                item.share_class_id,
                item.transaction_date,
            )
            != dimensions
            for item in members
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: one group key spans inconsistent dimensions"
            )
        try:
            total_shares = exact_decimal_sum(
                (item.shares for item in members if item.shares is not None),
                name="provisional group shares",
            )
            total_purchase_value = exact_decimal_sum(
                (
                    item.purchase_value_usd
                    for item in members
                    if item.purchase_value_usd is not None
                ),
                name="provisional group purchase value",
            )
        except ValueError as exc:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: provisional group exact arithmetic failed"
            ) from exc
        threshold_met = (
            total_purchase_value >= FORM4_PROVISIONAL_LOT_THRESHOLD_USD
        )
        payload = {
            "provisional_group_key": group_key,
            "issuer_cik": first.issuer_cik,
            "attributed_owner_cik": first.attributed_owner_cik,
            "attributed_owner_candidate_id": first.attributed_owner_candidate_id,
            "security_id": first.security_id,
            "share_class_id": first.share_class_id,
            "transaction_date": first.transaction_date,
            "member_row_ids": tuple(
                sorted(item.diagnostic_row_id for item in members)
            ),
            "member_count": len(members),
            "total_shares": total_shares,
            "total_purchase_value_usd": total_purchase_value,
            "latest_member_accepted_at_utc": max(
                item.accepted_at_utc for item in members
            ),
            "threshold_usd": FORM4_PROVISIONAL_LOT_THRESHOLD_USD,
            "threshold_diagnostic": (
                Form4ProvisionalLotThresholdDiagnostic.AT_OR_ABOVE_PROVISIONAL_MINIMUM
                if threshold_met
                else Form4ProvisionalLotThresholdDiagnostic.BELOW_PROVISIONAL_MINIMUM
            ),
            "meets_provisional_minimum_purchase_value": threshold_met,
            **_zero_authority_payload(),
        }
        groups.append(
            Form4ProvisionalLotGroup(
                **payload,
                provisional_group_id=hash_payload(_project_output(payload)),
                _verified_factory_token=_GROUP_FACTORY_TOKEN,
            )
        )
    return tuple(sorted(groups, key=_provisional_group_sort_key))


def _capture_sealed_inputs(
    mapping: Form4PitSecurityMapping,
    grouping: Form4SecEntityGrouping,
    inventory: Form4ObservedIdentityInventory,
) -> tuple[dict, dict, dict, str, str, str, str, str, str]:
    if (
        type(mapping) is not Form4PitSecurityMapping
        or type(grouping) is not Form4SecEntityGrouping
        or type(inventory) is not Form4ObservedIdentityInventory
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: IB-2D inputs must be exact upstream contract types"
        )
    try:
        mapping_fingerprint = _mapping_provenance_fingerprint(mapping)
        grouping_fingerprint = _grouping_provenance_fingerprint(grouping)
        inventory_fingerprint = _inventory_provenance_fingerprint(inventory)
        if (
            not _matches_factory_created_form4_pit_security_mapping_fingerprint(
                mapping,
                mapping_fingerprint,
            )
            or not _is_factory_created_form4_pit_security_mapping(mapping)
            or not _matches_factory_created_sec_entity_grouping_fingerprint(
                grouping,
                grouping_fingerprint,
            )
            or not _is_factory_created_sec_entity_grouping(grouping)
            or not _matches_factory_created_observed_identity_inventory_fingerprint(
                inventory,
                inventory_fingerprint,
            )
            or not _is_factory_created_observed_identity_inventory(inventory)
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: upstream input lacks unchanged process-local provenance"
            )
        mapping_runtime_fingerprint = _runtime_provenance_fingerprint(mapping)
        grouping_runtime_fingerprint = _runtime_provenance_fingerprint(grouping)
        inventory_runtime_fingerprint = _runtime_provenance_fingerprint(inventory)
        Form4PitSecurityMapping.__post_init__(
            mapping,
            _UPSTREAM_MAPPING_FACTORY_TOKEN,
        )
        Form4SecEntityGrouping.__post_init__(
            grouping,
            _UPSTREAM_GROUPING_FACTORY_TOKEN,
        )
        Form4ObservedIdentityInventory.__post_init__(
            inventory,
            _UPSTREAM_INVENTORY_FACTORY_TOKEN,
        )
        mapping_snapshot = _mapping_provenance_payload(mapping)
        grouping_snapshot = _grouping_provenance_payload(grouping)
        inventory_snapshot = _inventory_provenance_payload(inventory)
        Form4PitSecurityMapping.__post_init__(
            mapping,
            _UPSTREAM_MAPPING_FACTORY_TOKEN,
        )
        Form4SecEntityGrouping.__post_init__(
            grouping,
            _UPSTREAM_GROUPING_FACTORY_TOKEN,
        )
        Form4ObservedIdentityInventory.__post_init__(
            inventory,
            _UPSTREAM_INVENTORY_FACTORY_TOKEN,
        )
    except Form4ProvisionalLotDiagnosticsError:
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
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: upstream input could not be captured"
        ) from exc
    if (
        type(mapping_snapshot) is not dict
        or type(grouping_snapshot) is not dict
        or type(inventory_snapshot) is not dict
        or hash_payload(mapping_snapshot) != mapping_fingerprint
        or hash_payload(grouping_snapshot) != grouping_fingerprint
        or hash_payload(inventory_snapshot) != inventory_fingerprint
        or _runtime_provenance_fingerprint(mapping)
        != mapping_runtime_fingerprint
        or _runtime_provenance_fingerprint(grouping)
        != grouping_runtime_fingerprint
        or _runtime_provenance_fingerprint(inventory)
        != inventory_runtime_fingerprint
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: captured upstream snapshot is inconsistent"
        )
    return (
        mapping_snapshot,
        grouping_snapshot,
        inventory_snapshot,
        mapping_fingerprint,
        grouping_fingerprint,
        inventory_fingerprint,
        mapping_runtime_fingerprint,
        grouping_runtime_fingerprint,
        inventory_runtime_fingerprint,
    )


def _validate_upstream_chain(
    mapping_snapshot: dict,
    grouping_snapshot: dict,
    inventory_snapshot: dict,
    *,
    grouping_fingerprint: str,
    inventory_fingerprint: str,
) -> tuple[tuple[str, ...], dict[str, dict], dict[str, dict], dict[str, dict]]:
    mapping_identity = mapping_snapshot.get("identity")
    grouping_identity = grouping_snapshot.get("identity")
    inventory_identity = inventory_snapshot.get("identity")
    mapping_rows = mapping_snapshot.get("rows")
    attributions = grouping_snapshot.get("transaction_attributions")
    inventory_transactions = inventory_snapshot.get("transactions")
    issuer_candidates = grouping_snapshot.get("issuer_candidates")
    if (
        type(mapping_identity) is not dict
        or type(grouping_identity) is not dict
        or type(inventory_identity) is not dict
        or type(mapping_rows) is not list
        or type(attributions) is not list
        or type(inventory_transactions) is not list
        or type(issuer_candidates) is not list
        or len(mapping_rows) > MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
        or len(attributions) > MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
        or len(inventory_transactions) > MAX_FORM4_OBSERVED_IDENTITY_TRANSACTIONS
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: upstream snapshot shape exceeds a resource bound"
        )
    if (
        mapping_identity.get("upstream_grouping_id")
        != grouping_identity.get("grouping_id")
        or mapping_identity.get("upstream_grouping_identity_hash")
        != hash_payload(grouping_identity)
        or mapping_identity.get("upstream_grouping_fingerprint")
        != grouping_fingerprint
        or grouping_identity.get("upstream_inventory_id")
        != inventory_identity.get("inventory_id")
        or grouping_identity.get("upstream_inventory_identity_hash")
        != hash_payload(inventory_identity)
        or grouping_identity.get("upstream_inventory_observation_hash")
        != inventory_fingerprint
        or len(mapping_rows) != len(attributions)
        or len(attributions) != len(inventory_transactions)
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: upstream mapping/grouping/inventory chain is inconsistent"
        )
    attribution_by_id: dict[str, dict] = {}
    for item in attributions:
        if type(item) is not dict:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: grouping attribution snapshot is malformed"
            )
        item_id = item.get("transaction_attribution_id")
        if type(item_id) is not str or item_id in attribution_by_id:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: grouping attribution inventory is not unique"
            )
        attribution_by_id[item_id] = item
    inventory_by_id: dict[str, dict] = {}
    for item in inventory_transactions:
        if type(item) is not dict:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: inventory transaction snapshot is malformed"
            )
        item_id = item.get("transaction_observation_id")
        if type(item_id) is not str or item_id in inventory_by_id:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: inventory transaction inventory is not unique"
            )
        inventory_by_id[item_id] = item
    issuer_by_filing: dict[str, dict] = {}
    amended_families: set[str] = set()
    for candidate in issuer_candidates:
        if (
            type(candidate) is not dict
            or type(candidate.get("observations")) is not list
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: issuer candidate snapshot is malformed"
            )
        for observation in candidate["observations"]:
            if type(observation) is not dict:
                raise Form4ProvisionalLotDiagnosticsError(
                    "REFUSED: issuer observation snapshot is malformed"
                )
            filing_id = observation.get("filing_observation_id")
            if type(filing_id) is not str or filing_id in issuer_by_filing:
                raise Form4ProvisionalLotDiagnosticsError(
                    "REFUSED: issuer observation inventory is not unique"
                )
            issuer_by_filing[filing_id] = observation
            if observation.get("document_type") == "4/A":
                original = observation.get("original_accession")
                _accession(original, label="amended family original accession")
                amended_families.add(original)
    if (
        len(issuer_by_filing) != inventory_identity.get("filing_count")
        or set(attribution_by_id)
        != {item.get("transaction_attribution_id") for item in mapping_rows}
        or set(inventory_by_id)
        != {
            item.get("upstream_transaction_observation_id")
            for item in attributions
        }
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: upstream row joins are not exhaustive"
        )
    return (
        tuple(sorted(amended_families)),
        issuer_by_filing,
        attribution_by_id,
        inventory_by_id,
    )


def _build_diagnostic_row(
    mapping_state: dict,
    *,
    attribution: dict,
    inventory_transaction: dict,
    issuer_observation: dict,
    report_row: Form4ProvisionalDispositionRow,
    amended_families: frozenset[str],
) -> Form4ProvisionalLotDiagnosticRow:
    mapping_attribution_fields = (
        "accession_number",
        "source_sha256",
        "row_index",
        "event_id",
        "filing_observation_id",
        "upstream_transaction_observation_id",
        "upstream_report_row_id",
        "transaction_payload_hash",
        "issuer_candidate_id",
        "security_title_raw",
        "transaction_date",
        "upstream_disposition",
        "identity_disposition",
        "attributed_owner_cik",
        "attributed_owner_candidate_id",
        "owner_attribution_outcomes",
        "transaction_attribution_id",
    )
    if any(
        mapping_state.get(name) != attribution.get(name)
        for name in mapping_attribution_fields
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: mapping row disagrees with its grouping attribution"
        )
    attribution_inventory_fields = (
        "accession_number",
        "source_sha256",
        "row_index",
        "event_id",
        "filing_observation_id",
        "upstream_report_row_id",
        "transaction_payload_hash",
        "security_title_raw",
        "transaction_date",
        "upstream_disposition",
        "identity_disposition",
    )
    if any(
        attribution.get(name) != inventory_transaction.get(name)
        for name in attribution_inventory_fields
    ) or attribution.get("upstream_transaction_observation_id") != (
        inventory_transaction.get("transaction_observation_id")
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: grouping attribution disagrees with inventory transaction"
        )
    if (
        mapping_state.get("filing_observation_id")
        != issuer_observation.get("filing_observation_id")
        or mapping_state.get("accession_number")
        != issuer_observation.get("accession_number")
        or mapping_state.get("source_sha256")
        != issuer_observation.get("source_sha256")
        or mapping_state.get("issuer_cik") != issuer_observation.get("issuer_cik")
        or mapping_state.get("accepted_at_utc")
        != issuer_observation.get("accepted_at_utc")
        or mapping_state.get("document_type")
        != issuer_observation.get("document_type")
        or mapping_state.get("original_accession")
        != issuer_observation.get("original_accession")
        or mapping_state.get("amends_accession")
        != issuer_observation.get("amends_accession")
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: mapping row disagrees with its filing observation"
        )
    if (
        mapping_state.get("upstream_report_row_id") != report_row.row_id
        or mapping_state.get("transaction_payload_hash")
        != report_row.transaction_payload_hash
        or mapping_state.get("accession_number") != report_row.accession_number
        or mapping_state.get("source_sha256") != report_row.source_sha256
        or mapping_state.get("row_index") != report_row.row_index
        or mapping_state.get("event_id") != report_row.event_id
        or mapping_state.get("security_title_raw")
        != report_row.security_title_raw
        or mapping_state.get("transaction_date")
        != (
            None
            if report_row.transaction_date is None
            else report_row.transaction_date.isoformat()
        )
        or mapping_state.get("upstream_disposition")
        != report_row.disposition.value
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: mapping row disagrees with rebuilt IB-1G report"
        )
    try:
        upstream_disposition = Form4ProvisionalDisposition(
            mapping_state["upstream_disposition"]
        )
        identity_disposition = Form4ObservedIdentityDisposition(
            mapping_state["identity_disposition"]
        )
        owner_outcomes = tuple(
            Form4OwnerAttributionOutcome(item)
            for item in mapping_state["owner_attribution_outcomes"]
        )
        mapping_outcomes = tuple(
            Form4PitSecurityMappingOutcome(item)
            for item in mapping_state["resolution_outcomes"]
        )
        security_class = (
            None
            if mapping_state["security_class_normalized"] is None
            else Form4SecurityClass(mapping_state["security_class_normalized"])
        )
        title_mapping_kind = (
            None
            if mapping_state["title_mapping_kind"] is None
            else Form4SecurityTitleMappingKind(mapping_state["title_mapping_kind"])
        )
        transaction_date = (
            None
            if mapping_state["transaction_date"] is None
            else date.fromisoformat(mapping_state["transaction_date"])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: mapping row enum or date state is malformed"
        ) from exc
    original_accession = mapping_state["original_accession"]
    family_has_amendment = original_accession in amended_families
    reasons = _quarantine_reasons_from_state(
        amendment_family_has_supplied_amendment=family_has_amendment,
        upstream_disposition=upstream_disposition,
        identity_disposition=identity_disposition,
        owner_attribution_outcomes=owner_outcomes,
        security_mapping_outcomes=mapping_outcomes,
        attributed_owner_cik=mapping_state["attributed_owner_cik"],
        attributed_owner_candidate_id=mapping_state[
            "attributed_owner_candidate_id"
        ],
        security_id=mapping_state["security_id"],
        share_class_id=mapping_state["share_class_id"],
        security_class_normalized=security_class,
        transaction_date=transaction_date,
        shares=report_row.shares,
        price_per_share=report_row.price_per_share,
        purchase_value_usd=report_row.purchase_value_usd,
    )
    disposition = (
        Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
        if not reasons
        else Form4ProvisionalLotDisposition.PROVISIONAL_QUARANTINE
    )
    if disposition is Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE:
        group_key = hash_payload(
            _group_key_payload(
                attributed_owner_cik=mapping_state["attributed_owner_cik"],
                attributed_owner_candidate_id=mapping_state[
                    "attributed_owner_candidate_id"
                ],
                security_id=mapping_state["security_id"],
                share_class_id=mapping_state["share_class_id"],
                transaction_date=transaction_date,
            )
        )
    else:
        group_key = None
    payload = {
        "mapping_row_id": mapping_state["mapping_row_id"],
        "transaction_attribution_id": mapping_state[
            "transaction_attribution_id"
        ],
        "upstream_transaction_observation_id": mapping_state[
            "upstream_transaction_observation_id"
        ],
        "upstream_report_row_id": mapping_state["upstream_report_row_id"],
        "transaction_payload_hash": mapping_state["transaction_payload_hash"],
        "accession_number": mapping_state["accession_number"],
        "source_sha256": mapping_state["source_sha256"],
        "row_index": mapping_state["row_index"],
        "event_id": mapping_state["event_id"],
        "accepted_at_utc": mapping_state["accepted_at_utc"],
        "document_type": mapping_state["document_type"],
        "original_accession": original_accession,
        "amends_accession": mapping_state["amends_accession"],
        "amendment_family_has_supplied_amendment": family_has_amendment,
        "issuer_cik": mapping_state["issuer_cik"],
        "attributed_owner_cik": mapping_state["attributed_owner_cik"],
        "attributed_owner_candidate_id": mapping_state[
            "attributed_owner_candidate_id"
        ],
        "security_id": mapping_state["security_id"],
        "share_class_id": mapping_state["share_class_id"],
        "security_class_normalized": security_class,
        "transaction_date": transaction_date,
        "title_mapping_kind": title_mapping_kind,
        "upstream_disposition": upstream_disposition,
        "identity_disposition": identity_disposition,
        "owner_attribution_outcomes": owner_outcomes,
        "security_mapping_outcomes": mapping_outcomes,
        "parser_outcomes": report_row.outcomes,
        "parser_diagnostics": report_row.diagnostics,
        "shares": report_row.shares,
        "price_per_share": report_row.price_per_share,
        "purchase_value_usd": report_row.purchase_value_usd,
        "provisional_group_key": group_key,
        "disposition": disposition,
        "quarantine_reasons": reasons,
        **_zero_authority_payload(),
    }
    return Form4ProvisionalLotDiagnosticRow(
        **payload,
        diagnostic_row_id=hash_payload(_project_output(payload)),
        _verified_factory_token=_ROW_FACTORY_TOKEN,
    )


def _recheck_inputs(
    mapping: Form4PitSecurityMapping,
    grouping: Form4SecEntityGrouping,
    inventory: Form4ObservedIdentityInventory,
    *,
    mapping_fingerprint: str,
    grouping_fingerprint: str,
    inventory_fingerprint: str,
    mapping_runtime_fingerprint: str,
    grouping_runtime_fingerprint: str,
    inventory_runtime_fingerprint: str,
) -> None:
    try:
        current_mapping = _mapping_provenance_fingerprint(mapping)
        current_grouping = _grouping_provenance_fingerprint(grouping)
        current_inventory = _inventory_provenance_fingerprint(inventory)
        current_mapping_runtime = _runtime_provenance_fingerprint(mapping)
        current_grouping_runtime = _runtime_provenance_fingerprint(grouping)
        current_inventory_runtime = _runtime_provenance_fingerprint(inventory)
        Form4PitSecurityMapping.__post_init__(
            mapping,
            _UPSTREAM_MAPPING_FACTORY_TOKEN,
        )
        Form4SecEntityGrouping.__post_init__(
            grouping,
            _UPSTREAM_GROUPING_FACTORY_TOKEN,
        )
        Form4ObservedIdentityInventory.__post_init__(
            inventory,
            _UPSTREAM_INVENTORY_FACTORY_TOKEN,
        )
    except (
        AttributeError,
        KeyError,
        OverflowError,
        RecursionError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: upstream input changed during diagnostics"
        ) from exc
    if (
        current_mapping != mapping_fingerprint
        or current_grouping != grouping_fingerprint
        or current_inventory != inventory_fingerprint
        or current_mapping_runtime != mapping_runtime_fingerprint
        or current_grouping_runtime != grouping_runtime_fingerprint
        or current_inventory_runtime != inventory_runtime_fingerprint
        or not _matches_factory_created_form4_pit_security_mapping_fingerprint(
            mapping,
            current_mapping,
        )
        or not _matches_factory_created_sec_entity_grouping_fingerprint(
            grouping,
            current_grouping,
        )
        or not _matches_factory_created_observed_identity_inventory_fingerprint(
            inventory,
            current_inventory,
        )
        or not _is_factory_created_form4_pit_security_mapping(mapping)
        or not _is_factory_created_sec_entity_grouping(grouping)
        or not _is_factory_created_observed_identity_inventory(inventory)
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: upstream input changed or lost its process-local seal"
        )


def _build_form4_provisional_lot_diagnostics(
    mapping: Form4PitSecurityMapping,
    grouping: Form4SecEntityGrouping,
    inventory: Form4ObservedIdentityInventory,
    evidence: ProfileBoundForm4AmendmentEvidence,
    *,
    builder_git_commit: str,
) -> Form4ProvisionalLotDiagnostics:
    if (
        type(builder_git_commit) is not str
        or _GIT_COMMIT_RE.fullmatch(builder_git_commit) is None
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: builder Git commit must be a full lowercase SHA-1"
        )
    if type(evidence) is not ProfileBoundForm4AmendmentEvidence:
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: evidence must be the exact profile-bound result"
        )
    (
        mapping_snapshot,
        grouping_snapshot,
        inventory_snapshot,
        mapping_fingerprint,
        grouping_fingerprint,
        inventory_fingerprint,
        mapping_runtime_fingerprint,
        grouping_runtime_fingerprint,
        inventory_runtime_fingerprint,
    ) = _capture_sealed_inputs(mapping, grouping, inventory)
    (
        amended_families,
        issuer_by_filing,
        attribution_by_id,
        inventory_by_id,
    ) = _validate_upstream_chain(
        mapping_snapshot,
        grouping_snapshot,
        inventory_snapshot,
        grouping_fingerprint=grouping_fingerprint,
        inventory_fingerprint=inventory_fingerprint,
    )
    inventory_identity = inventory_snapshot["identity"]
    try:
        _preflight_evidence(evidence)
        evidence_runtime_fingerprint = _runtime_provenance_fingerprint(evidence)
        evidence_observation_hash = _evidence_observation_hash(evidence)
        report = build_form4_provisional_disposition_report(
            evidence,
            builder_git_commit=inventory_identity["builder_git_commit"],
        )
        report = _validate_rebuilt_report(
            report,
            builder_git_commit=inventory_identity["builder_git_commit"],
            upstream_evidence_id=inventory_identity["upstream_evidence_id"],
            upstream_evidence_identity_hash=inventory_identity[
                "upstream_evidence_identity_hash"
            ],
            upstream_parsed_corpus_hash=inventory_identity[
                "upstream_parsed_corpus_hash"
            ],
            upstream_source_inventory_hash=inventory_identity[
                "upstream_source_inventory_hash"
            ],
        )
        report_identity_payload = _observed_contract_payload(report.identity)
    except Form4ProvisionalLotDiagnosticsError:
        raise
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: IB-1G report could not be rebuilt from evidence"
        ) from exc
    if (
        type(report_identity_payload) is not dict
        or inventory_identity["upstream_evidence_id"]
        != report.identity.upstream_evidence_id
        or inventory_identity["upstream_evidence_identity_hash"]
        != report.identity.upstream_evidence_identity_hash
        or inventory_identity["upstream_report_id"] != report.identity.report_id
        or inventory_identity["upstream_report_identity_hash"]
        != hash_payload(report_identity_payload)
        or inventory_identity["upstream_report_row_inventory_hash"]
        != report.identity.row_inventory_hash
        or inventory_identity["transaction_count"] != len(report.rows)
        or _evidence_observation_hash(evidence) != evidence_observation_hash
        or _runtime_provenance_fingerprint(evidence)
        != evidence_runtime_fingerprint
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: inventory and rebuilt evidence report disagree"
        )
    report_by_id: dict[str, Form4ProvisionalDispositionRow] = {}
    for item in report.rows:
        if item.row_id in report_by_id:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: rebuilt report row inventory is not unique"
            )
        report_by_id[item.row_id] = item
    mapping_rows = mapping_snapshot["rows"]
    if (
        len(report_by_id) != len(mapping_rows)
        or set(report_by_id)
        != {item.get("upstream_report_row_id") for item in mapping_rows}
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: rebuilt report join is not exhaustive"
        )
    amended_set = frozenset(amended_families)
    rows: list[Form4ProvisionalLotDiagnosticRow] = []
    for mapping_state in mapping_rows:
        if type(mapping_state) is not dict:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: mapping row snapshot is malformed"
            )
        attribution = attribution_by_id.get(
            mapping_state.get("transaction_attribution_id")
        )
        if attribution is None:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: mapping row has no grouping attribution"
            )
        inventory_transaction = inventory_by_id.get(
            mapping_state.get("upstream_transaction_observation_id")
        )
        issuer_observation = issuer_by_filing.get(
            mapping_state.get("filing_observation_id")
        )
        report_row = report_by_id.get(mapping_state.get("upstream_report_row_id"))
        if (
            inventory_transaction is None
            or issuer_observation is None
            or report_row is None
        ):
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: mapping row has an incomplete upstream join"
            )
        rows.append(
            _build_diagnostic_row(
                mapping_state,
                attribution=attribution,
                inventory_transaction=inventory_transaction,
                issuer_observation=issuer_observation,
                report_row=report_row,
                amended_families=amended_set,
            )
        )
    sorted_rows = tuple(sorted(rows, key=_diagnostic_row_sort_key))
    if (
        len(sorted_rows) != len(mapping_rows)
        or {item.mapping_row_id for item in sorted_rows}
        != {item["mapping_row_id"] for item in mapping_rows}
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: diagnostic row output is not exhaustive"
        )
    groups = _aggregate_provisional_groups(sorted_rows)
    candidate_count = sum(
        item.disposition
        is Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
        for item in sorted_rows
    )
    threshold_met_count = sum(
        item.meets_provisional_minimum_purchase_value for item in groups
    )
    amendment_row_count = sum(
        item.amendment_family_has_supplied_amendment for item in sorted_rows
    )
    manual_count = sum(
        item.disposition
        is Form4ProvisionalLotDisposition.PROVISIONAL_GROUPING_CANDIDATE
        and item.title_mapping_kind is Form4SecurityTitleMappingKind.MANUAL_EXCEPTION
        for item in sorted_rows
    )
    mapping_identity = mapping_snapshot["identity"]
    grouping_identity = grouping_snapshot["identity"]
    identity_payload = {
        "contract_version": FORM4_PROVISIONAL_LOT_DIAGNOSTICS_VERSION,
        "builder_git_commit": builder_git_commit,
        "upstream_mapping_id": mapping_identity["mapping_id"],
        "upstream_mapping_identity_hash": hash_payload(mapping_identity),
        "upstream_mapping_fingerprint": mapping_fingerprint,
        "upstream_mapping_runtime_fingerprint": mapping_runtime_fingerprint,
        "upstream_grouping_id": grouping_identity["grouping_id"],
        "upstream_grouping_identity_hash": hash_payload(grouping_identity),
        "upstream_grouping_fingerprint": grouping_fingerprint,
        "upstream_grouping_runtime_fingerprint": grouping_runtime_fingerprint,
        "upstream_inventory_id": inventory_identity["inventory_id"],
        "upstream_inventory_identity_hash": hash_payload(inventory_identity),
        "upstream_inventory_fingerprint": inventory_fingerprint,
        "upstream_inventory_runtime_fingerprint": inventory_runtime_fingerprint,
        "upstream_evidence_id": inventory_identity["upstream_evidence_id"],
        "upstream_evidence_identity_hash": inventory_identity[
            "upstream_evidence_identity_hash"
        ],
        "upstream_evidence_runtime_fingerprint": evidence_runtime_fingerprint,
        "rebuilt_report_id": report.identity.report_id,
        "rebuilt_report_identity_hash": hash_payload(report_identity_payload),
        "rebuilt_report_row_inventory_hash": report.identity.row_inventory_hash,
        "amendment_family_inventory_hash": hash_payload(list(amended_families)),
        "diagnostic_row_inventory_hash": hash_payload(
            [item.to_payload() for item in sorted_rows]
        ),
        "provisional_group_inventory_hash": hash_payload(
            [item.to_payload() for item in groups]
        ),
        "mapping_row_count": len(sorted_rows),
        "provisional_candidate_row_count": candidate_count,
        "quarantined_row_count": len(sorted_rows) - candidate_count,
        "provisional_group_count": len(groups),
        "threshold_met_group_count": threshold_met_count,
        "below_threshold_group_count": len(groups) - threshold_met_count,
        "amendment_family_quarantined_count": len(amended_families),
        "amendment_family_quarantined_row_count": amendment_row_count,
        "manual_exception_candidate_row_count": manual_count,
        **_zero_authority_payload(),
    }
    identity = Form4ProvisionalLotDiagnosticsIdentity(
        **identity_payload,
        diagnostics_id=(
            "form4-provisional-lot-diagnostics-"
            f"{hash_payload(_project_output(identity_payload))[:16]}"
        ),
        _verified_factory_token=_IDENTITY_FACTORY_TOKEN,
    )
    result = Form4ProvisionalLotDiagnostics(
        identity=identity,
        amendment_family_original_accessions=amended_families,
        rows=sorted_rows,
        groups=groups,
        _verified_factory_token=_RESULT_FACTORY_TOKEN,
    )
    _recheck_inputs(
        mapping,
        grouping,
        inventory,
        mapping_fingerprint=mapping_fingerprint,
        grouping_fingerprint=grouping_fingerprint,
        inventory_fingerprint=inventory_fingerprint,
        mapping_runtime_fingerprint=mapping_runtime_fingerprint,
        grouping_runtime_fingerprint=grouping_runtime_fingerprint,
        inventory_runtime_fingerprint=inventory_runtime_fingerprint,
    )
    if _evidence_observation_hash(evidence) != evidence_observation_hash:
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: evidence changed during diagnostics"
        )
    if (
        _runtime_provenance_fingerprint(evidence)
        != evidence_runtime_fingerprint
    ):
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: evidence runtime types changed during diagnostics"
        )
    return result


def build_form4_provisional_lot_diagnostics(
    mapping: Form4PitSecurityMapping,
    grouping: Form4SecEntityGrouping,
    inventory: Form4ObservedIdentityInventory,
    evidence: ProfileBoundForm4AmendmentEvidence,
    *,
    builder_git_commit: str,
) -> Form4ProvisionalLotDiagnostics:
    """Build exhaustive, non-authoritative provisional lot diagnostics."""

    try:
        result = _build_form4_provisional_lot_diagnostics(
            mapping,
            grouping,
            inventory,
            evidence,
            builder_git_commit=builder_git_commit,
        )
        _register_factory_created_diagnostics(result)
        return result
    except Form4ProvisionalLotDiagnosticsError:
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
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: malformed provisional lot diagnostics input"
        ) from exc


# The seal proves only unchanged process-local factory origin.  It is neither
# persisted provenance nor an authentication mechanism.
_FACTORY_CREATED_DIAGNOSTICS: dict[
    int,
    tuple[weakref.ReferenceType[Form4ProvisionalLotDiagnostics], str],
] = {}
_FACTORY_CREATED_DIAGNOSTICS_LOCK = threading.RLock()


def _project_diagnostics_provenance(
    value: object,
    *,
    budget: _OutputProjectionBudget | None = None,
    depth: int = 0,
) -> object:
    """Project exact runtime types for the process-local factory seal."""

    if budget is None:
        budget = _OutputProjectionBudget()
    if depth > MAX_FORM4_PROVISIONAL_LOT_PROJECTION_DEPTH:
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: diagnostics provenance exceeds the depth bound"
        )
    budget.nodes += 1
    if budget.nodes > MAX_FORM4_PROVISIONAL_LOT_PROJECTION_NODES:
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: diagnostics provenance exceeds the node bound"
        )
    value_type = type(value)
    if isinstance(value, Enum):
        return {
            "type": (
                f"enum:{value_type.__module__}.{value_type.__qualname__}"
            ),
            "value": _project_diagnostics_provenance(
                value.value,
                budget=budget,
                depth=depth + 1,
            ),
        }
    if value_type is Decimal:
        projected_decimal = decimal_text(
            _decimal(value, label="diagnostics provenance Decimal")
        )
        decimal_tuple = value.as_tuple()
        budget.text_characters += len(projected_decimal)
        if budget.text_characters > MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics provenance exceeds the text bound"
            )
        return {
            "type": "Decimal",
            "canonical_value": projected_decimal,
            "sign": decimal_tuple.sign,
            "digits": list(decimal_tuple.digits),
            "exponent": int(decimal_tuple.exponent),
        }
    if value_type is datetime:
        return {"type": "datetime", "value": value.isoformat()}
    if value_type is date:
        return {"type": "date", "value": value.isoformat()}
    if value_type is bytes:
        return {
            "type": "bytes",
            "length": len(value),
            "sha256": sha256(value).hexdigest(),
        }
    if value_type is str:
        budget.text_characters += len(value)
        if budget.text_characters > MAX_FORM4_OBSERVED_IDENTITY_TEXT_CHARACTERS:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics provenance exceeds the text bound"
            )
        return {"type": "str", "value": value}
    if value is None:
        return {"type": "NoneType"}
    if value_type is bool:
        return {"type": "bool", "value": value}
    if value_type is int:
        return {"type": "int", "value": value}
    is_contract = is_dataclass(value) and not isinstance(value, type)
    if value_type is tuple or value_type is list or is_contract:
        active_ids = budget.active_ids
        assert active_ids is not None
        value_id = id(value)
        if value_id in active_ids:
            raise Form4ProvisionalLotDiagnosticsError(
                "REFUSED: diagnostics provenance contains a cycle"
            )
        active_ids.add(value_id)
        try:
            if value_type is tuple or value_type is list:
                return {
                    "type": "tuple" if value_type is tuple else "list",
                    "items": [
                        _project_diagnostics_provenance(
                            item,
                            budget=budget,
                            depth=depth + 1,
                        )
                        for item in value
                    ],
                }
            declared = {item.name for item in fields(value_type)}
            state = object.__getattribute__(value, "__dict__")
            if type(state) is not dict or set(state) != declared:
                raise Form4ProvisionalLotDiagnosticsError(
                    "REFUSED: diagnostics provenance state is not exact"
                )
            return {
                "type": (
                    f"contract:{value_type.__module__}.{value_type.__qualname__}"
                ),
                "fields": [
                    [
                        item.name,
                        _project_diagnostics_provenance(
                            state[item.name],
                            budget=budget,
                            depth=depth + 1,
                        ),
                    ]
                    for item in fields(value_type)
                ],
            }
        finally:
            active_ids.remove(value_id)
    raise Form4ProvisionalLotDiagnosticsError(
        "REFUSED: diagnostics provenance contains an unsupported value"
    )


def _diagnostics_provenance_fingerprint(
    value: Form4ProvisionalLotDiagnostics,
) -> str:
    if type(value) is not Form4ProvisionalLotDiagnostics:
        raise Form4ProvisionalLotDiagnosticsError(
            "REFUSED: provenance input must be exact diagnostics"
        )
    return _runtime_provenance_fingerprint(value)


def _runtime_provenance_fingerprint(value: object) -> str:
    """Hash one callback-free, runtime-type-preserving state projection."""

    return hash_payload(_project_diagnostics_provenance(value))


def _register_factory_created_diagnostics(
    value: Form4ProvisionalLotDiagnostics,
) -> None:
    fingerprint = _diagnostics_provenance_fingerprint(value)
    object_id = id(value)

    def _remove_if_current(
        dead_reference: weakref.ReferenceType[Form4ProvisionalLotDiagnostics],
    ) -> None:
        with _FACTORY_CREATED_DIAGNOSTICS_LOCK:
            current = _FACTORY_CREATED_DIAGNOSTICS.get(object_id)
            if current is not None and current[0] is dead_reference:
                _FACTORY_CREATED_DIAGNOSTICS.pop(object_id, None)

    reference = weakref.ref(value, _remove_if_current)
    with _FACTORY_CREATED_DIAGNOSTICS_LOCK:
        _FACTORY_CREATED_DIAGNOSTICS[object_id] = (reference, fingerprint)


def _matches_factory_created_diagnostics_fingerprint(
    value: object,
    fingerprint: object,
) -> bool:
    try:
        if (
            type(value) is not Form4ProvisionalLotDiagnostics
            or type(fingerprint) is not str
            or _SHA256_RE.fullmatch(fingerprint) is None
        ):
            return False
        with _FACTORY_CREATED_DIAGNOSTICS_LOCK:
            current = _FACTORY_CREATED_DIAGNOSTICS.get(id(value))
            return (
                current is not None
                and current[0]() is value
                and current[1] == fingerprint
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


def _is_factory_created_form4_provisional_lot_diagnostics(
    value: object,
) -> bool:
    try:
        if type(value) is not Form4ProvisionalLotDiagnostics:
            return False
        fingerprint = _diagnostics_provenance_fingerprint(value)
        return _matches_factory_created_diagnostics_fingerprint(
            value,
            fingerprint,
        )
    except (
        AttributeError,
        Form4ProvisionalLotDiagnosticsError,
        KeyError,
        OverflowError,
        RecursionError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        return False


__all__ = [
    "FORM4_PROVISIONAL_LOT_DIAGNOSTICS_VERSION",
    "FORM4_PROVISIONAL_LOT_THRESHOLD_USD",
    "Form4ProvisionalLotDiagnosticRow",
    "Form4ProvisionalLotDiagnostics",
    "Form4ProvisionalLotDiagnosticsError",
    "Form4ProvisionalLotDiagnosticsIdentity",
    "Form4ProvisionalLotDisposition",
    "Form4ProvisionalLotGroup",
    "Form4ProvisionalLotQuarantineReason",
    "Form4ProvisionalLotThresholdDiagnostic",
    "MAX_FORM4_PROVISIONAL_LOT_GROUPS",
    "MAX_FORM4_PROVISIONAL_LOT_PROJECTION_DEPTH",
    "MAX_FORM4_PROVISIONAL_LOT_PROJECTION_NODES",
    "build_form4_provisional_lot_diagnostics",
]
