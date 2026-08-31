"""Frozen IB-0 contracts and accession-preserving filing lineage.

The types in this module are intentionally research-inert. They describe
what an as-filed record means and whether it may enter later lot aggregation;
they do not download data, join outcomes, calculate returns, place orders, or
decide a portfolio. Ambiguity is represented by a named exclusion rather
than by dropping the source row.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


ACCESSION_RE = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
PARSED_OWNERSHIP_FORMS = ("4", "4/A", "5")


class ContractError(ValueError):
    """An Insider Buying structural contract was violated."""


class ClassificationOutcome(str, Enum):
    """Named row-level dispositions before event-lot aggregation."""

    ELIGIBLE_FOR_LOT_AGGREGATION = "eligible_for_lot_aggregation"
    EXCLUDE_UNSUPPORTED_FORM = "exclude_unsupported_form"
    EXCLUDE_AMENDED_FILING = "exclude_amended_filing"
    EXCLUDE_DERIVATIVE = "exclude_derivative"
    EXCLUDE_MULTIPLE_REPORTING_OWNERS = "exclude_multiple_reporting_owners"
    EXCLUDE_INCOMPLETE_OWNER_RELATIONSHIP = (
        "exclude_incomplete_owner_relationship"
    )
    EXCLUDE_NO_OFFICER_OR_DIRECTOR = "exclude_no_officer_or_director"
    EXCLUDE_TEN_PERCENT_OWNER = "exclude_ten_percent_owner"
    EXCLUDE_NON_COMMON_STOCK = "exclude_non_common_stock"
    EXCLUDE_SALE = "exclude_sale"
    EXCLUDE_GIFT = "exclude_gift"
    EXCLUDE_AWARD_OR_GRANT = "exclude_award_or_grant"
    EXCLUDE_NON_PURCHASE_TRANSACTION_CODE = (
        "exclude_non_purchase_transaction_code"
    )
    EXCLUDE_NOT_ACQUIRED = "exclude_not_acquired"
    EXCLUDE_INDIRECT_OWNERSHIP = "exclude_indirect_ownership"
    EXCLUDE_MISSING_TRANSACTION_DATE = "exclude_missing_transaction_date"
    EXCLUDE_NONPOSITIVE_SHARES = "exclude_nonpositive_shares"
    EXCLUDE_PRICE_RANGE = "exclude_price_range"
    EXCLUDE_MISSING_OR_NONPOSITIVE_PRICE = (
        "exclude_missing_or_nonpositive_price"
    )
    EXCLUDE_UNREPRESENTABLE_PURCHASE_VALUE = (
        "exclude_unrepresentable_purchase_value"
    )
    EXCLUDE_UNRESOLVED_FOOTNOTE = "exclude_unresolved_footnote"


class TransactionDiagnostic(str, Enum):
    """Retained V1 features that are not canonical exclusion reasons."""

    PRIVATE_PURCHASE_FOOTNOTE_MENTION = "private_purchase_footnote_mention"
    TEN_B5_1_PLAN = "10b5_1_plan"
    TEN_B5_1_FOOTNOTE_MENTION = "10b5_1_footnote_mention"
    TEN_PERCENT_OWNER_WITH_OFFICER_OR_DIRECTOR_ROLE = (
        "ten_percent_owner_with_officer_or_director_role"
    )


class AvailabilityPrecision(str, Enum):
    ACCEPTANCE_TIMESTAMP = "acceptance_timestamp"
    ACCEPTANCE_DATE_ONLY = "acceptance_date_only"


class ExecutionRule(str, Enum):
    NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE = (
        "next_regular_open_after_acceptance_timestamp"
    )
    NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE_DATE = (
        "next_regular_open_after_acceptance_date"
    )


@dataclass(frozen=True)
class CanonicalSpec:
    version: str
    allowed_forms: tuple[str, ...]
    primary_form: str
    transaction_code: str
    acquired_disposed_code: str
    ownership_nature: str
    minimum_purchase_value_usd: Decimal
    lot_aggregation_key: tuple[str, ...]
    minimum_purchase_value_applies_after_aggregation: bool
    score_formula: str
    decay_half_life_trading_days: int
    lookback_trading_days: int
    event_study_horizons_trading_days: tuple[int, ...]
    primary_horizons_trading_days: tuple[int, ...]
    cost_grid_bps_per_side: tuple[int, ...]
    outcomes_authorized: bool
    authorized_outcome_looks: int


CANONICAL_SPEC = CanonicalSpec(
    version="INSETF-IB0-v1",
    allowed_forms=("4", "4/A"),
    primary_form="4",
    transaction_code="P",
    acquired_disposed_code="A",
    ownership_nature="D",
    minimum_purchase_value_usd=Decimal("50000"),
    lot_aggregation_key=(
        "reporting_owner_identity",
        "security_identity",
        "transaction_date",
    ),
    minimum_purchase_value_applies_after_aggregation=True,
    score_formula="ln(1 + purchase_value_usd / 50000)",
    decay_half_life_trading_days=20,
    lookback_trading_days=30,
    event_study_horizons_trading_days=(1, 5, 10, 20, 40, 60, 120),
    primary_horizons_trading_days=(5, 20, 60),
    cost_grid_bps_per_side=(0, 5, 10, 20),
    outcomes_authorized=False,
    authorized_outcome_looks=0,
)


@dataclass(frozen=True)
class PublicAvailability:
    """Public availability without pretending a date is an intraday instant."""

    accepted_at: datetime | None
    accepted_date: date
    precision: AvailabilityPrecision
    execution_rule: ExecutionRule

    def __post_init__(self) -> None:
        if type(self.accepted_date) is not date:
            raise ContractError("REFUSED: accepted_date must be an exact date")
        if not isinstance(self.precision, AvailabilityPrecision):
            raise ContractError("REFUSED: availability precision is unsupported")
        if not isinstance(self.execution_rule, ExecutionRule):
            raise ContractError("REFUSED: availability execution rule is unsupported")
        if self.accepted_at is not None and type(self.accepted_at) is not datetime:
            raise ContractError(
                "REFUSED: accepted_at must be a datetime or absent"
            )
        if self.precision is AvailabilityPrecision.ACCEPTANCE_TIMESTAMP:
            if self.accepted_at is None or self.accepted_at.utcoffset() is None:
                raise ContractError(
                    "REFUSED: timestamp availability requires a timezone-aware instant"
                )
            if self.accepted_date != self.accepted_at.date():
                raise ContractError(
                    "REFUSED: accepted date does not match acceptance timestamp"
                )
            if (
                self.execution_rule
                is not ExecutionRule.NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE
            ):
                raise ContractError("REFUSED: timestamp uses the wrong execution rule")
        else:
            if self.accepted_at is not None:
                raise ContractError("REFUSED: date-only availability contains an instant")
            if (
                self.execution_rule
                is not ExecutionRule.NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE_DATE
            ):
                raise ContractError("REFUSED: date-only value uses the wrong execution rule")


@dataclass(frozen=True)
class FilingEnvelope:
    accession_number: str
    form_type: str
    issuer_cik: str
    issuer_name: str
    issuer_symbol_raw: str | None
    availability: PublicAvailability
    source_name: str
    source_sha256: str
    amends_accession: str | None

    def __post_init__(self) -> None:
        if not ACCESSION_RE.fullmatch(self.accession_number):
            raise ContractError("REFUSED: accession number is not canonical")
        if self.form_type not in PARSED_OWNERSHIP_FORMS:
            raise ContractError("REFUSED: envelope form is outside the pinned schema")
        if not re.fullmatch(r"[0-9]{10}", self.issuer_cik):
            raise ContractError("REFUSED: issuer CIK must be ten digits")
        if not self.issuer_name.strip() or not self.source_name.strip():
            raise ContractError("REFUSED: issuer and source names are required")
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ContractError("REFUSED: source hash is not lowercase SHA-256")
        if self.form_type == "4/A":
            if not self.amends_accession or not ACCESSION_RE.fullmatch(
                self.amends_accession
            ):
                raise ContractError("REFUSED: Form 4/A requires its original accession")
            if self.amends_accession == self.accession_number:
                raise ContractError("REFUSED: an amendment cannot amend itself")
        elif self.amends_accession is not None:
            raise ContractError("REFUSED: original Form 4 cannot amend another filing")


@dataclass(frozen=True)
class ReportingOwner:
    owner_cik: str
    owner_name: str
    is_director: bool | None
    is_officer: bool | None
    is_ten_percent_owner: bool | None
    is_other: bool | None
    officer_title: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.owner_cik, str)
            or re.fullmatch(r"[0-9]{10}", self.owner_cik) is None
        ):
            raise ContractError("REFUSED: reporting-owner CIK must be ten digits")
        if not isinstance(self.owner_name, str) or not self.owner_name.strip():
            raise ContractError("REFUSED: reporting-owner name is required")
        for field_name in (
            "is_director",
            "is_officer",
            "is_ten_percent_owner",
            "is_other",
        ):
            value = getattr(self, field_name)
            if value is not None and type(value) is not bool:
                raise ContractError(
                    f"REFUSED: reporting-owner {field_name} must be bool or absent"
                )
        if self.officer_title is not None and (
            not isinstance(self.officer_title, str)
            or not self.officer_title.strip()
        ):
            raise ContractError(
                "REFUSED: reporting-owner officer title must be text or absent"
            )

    @property
    def relationship_complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.is_director,
                self.is_officer,
                self.is_ten_percent_owner,
                self.is_other,
            )
        )


@dataclass(frozen=True)
class ParsedTransaction:
    event_id: str
    accession_number: str
    source_sha256: str
    row_index: int
    derivative: bool
    security_title_raw: str | None
    transaction_date: date | None
    transaction_code: str | None
    acquired_disposed_code: str | None
    shares: Decimal | None
    price_per_share: Decimal | None
    purchase_value_usd: Decimal | None
    shares_owned_after: Decimal | None
    direct_indirect: str | None
    aff10b5_one: bool | None
    footnote_ids: tuple[str, ...]
    footnote_texts: tuple[str, ...]
    outcomes: tuple[ClassificationOutcome, ...]
    diagnostics: tuple[TransactionDiagnostic, ...] = ()

    @property
    def eligible_for_lot_aggregation(self) -> bool:
        return self.outcomes == (
            ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,
        )


@dataclass(frozen=True)
class ParsedFiling:
    envelope: FilingEnvelope
    reporting_owners: tuple[ReportingOwner, ...]
    footnotes: tuple[tuple[str, str], ...]
    transactions: tuple[ParsedTransaction, ...]


@dataclass(frozen=True)
class FilingCorpus:
    """All as-filed versions plus explicit original-to-amendment lineage."""

    filings: tuple[ParsedFiling, ...]
    superseded_by: tuple[tuple[str, tuple[str, ...]], ...]

    def filing(self, accession_number: str) -> ParsedFiling:
        for filing in self.filings:
            if filing.envelope.accession_number == accession_number:
                return filing
        raise KeyError(accession_number)


def build_filing_corpus(filings: list[ParsedFiling]) -> FilingCorpus:
    """Validate lineage while retaining originals and every amendment."""

    by_accession: dict[str, ParsedFiling] = {}
    for filing in filings:
        accession = filing.envelope.accession_number
        if accession in by_accession:
            raise ContractError(f"REFUSED: duplicate accession {accession}")
        by_accession[accession] = filing

    superseded: dict[str, list[str]] = {}
    for filing in filings:
        envelope = filing.envelope
        if envelope.amends_accession is None:
            continue
        original = by_accession.get(envelope.amends_accession)
        if original is None:
            raise ContractError(
                f"REFUSED: amendment target is absent: {envelope.amends_accession}"
            )
        if original.envelope.form_type != "4":
            raise ContractError("REFUSED: amendment target is not an original Form 4")
        if original.envelope.issuer_cik != envelope.issuer_cik:
            raise ContractError("REFUSED: amendment and original issuer CIK differ")
        amendment_time = envelope.availability.accepted_at
        original_time = original.envelope.availability.accepted_at
        if amendment_time is not None and original_time is not None:
            invalid_order = amendment_time <= original_time
        else:
            invalid_order = (
                envelope.availability.accepted_date
                < original.envelope.availability.accepted_date
            )
        if invalid_order:
            raise ContractError("REFUSED: amendment predates its original filing")
        superseded.setdefault(envelope.amends_accession, []).append(
            envelope.accession_number
        )

    ordered = tuple(
        sorted(
            filings,
            key=lambda item: (
                item.envelope.availability.accepted_date,
                item.envelope.accession_number,
            ),
        )
    )
    lineage = tuple(
        (original, tuple(sorted(amendments)))
        for original, amendments in sorted(superseded.items())
    )
    return FilingCorpus(filings=ordered, superseded_by=lineage)
