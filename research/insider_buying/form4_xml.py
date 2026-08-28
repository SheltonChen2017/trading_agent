"""Small, deterministic, offline Form 4 XML fixture parser.

The parser is not an EDGAR client. Callers must supply accession and public
acceptance metadata from an immutable source boundary. XML rows are never
silently discarded: every non-derivative and derivative transaction becomes
a :class:`ParsedTransaction` with a named include/exclude disposition.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from research.insider_buying.contracts import (
    CANONICAL_SPEC,
    AvailabilityPrecision,
    ClassificationOutcome,
    ContractError,
    ExecutionRule,
    FilingEnvelope,
    PARSED_OWNERSHIP_FORMS,
    ParsedFiling,
    ParsedTransaction,
    PublicAvailability,
    ReportingOwner,
)


MAX_XML_BYTES = 2 * 1024 * 1024
_PRIVATE_WORDS = (
    "private purchase",
    "private transaction",
    "privately negotiated",
)
_RANGE_WORDS = ("price range", "range of prices", "prices ranging")
_PLAN_WORDS = ("10b5-1", "10b5 1")


class Form4ParseError(ContractError):
    """The supplied filing cannot satisfy the pinned offline schema."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ElementTree.Element, name: str):
    return [child for child in element if _local_name(child.tag) == name]


def _descendants(element: ElementTree.Element, name: str):
    return [child for child in element.iter() if _local_name(child.tag) == name]


def _first(element: ElementTree.Element, name: str):
    matches = _descendants(element, name)
    return matches[0] if matches else None


def _text(element: ElementTree.Element | None, name: str) -> str | None:
    if element is None:
        return None
    target = _first(element, name)
    if target is None or target.text is None:
        return None
    value = target.text.strip()
    return value or None


def _value(element: ElementTree.Element, container_name: str) -> str | None:
    container = _first(element, container_name)
    return _text(container, "value")


def _required_text(element: ElementTree.Element, name: str) -> str:
    value = _text(element, name)
    if value is None:
        raise Form4ParseError(f"REFUSED: required XML field is missing: {name}")
    return value


def _parse_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    return None


def _parse_decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        value = Decimal(raw.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None
    return value if value.is_finite() else None


def _parse_date(raw: str | None) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _normalize_cik(raw: str, field: str) -> str:
    if not raw.isdigit() or len(raw) > 10:
        raise Form4ParseError(f"REFUSED: {field} is not a numeric CIK")
    return raw.zfill(10)


def _availability(value: datetime | date) -> PublicAvailability:
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise Form4ParseError(
                "REFUSED: acceptance timestamp must include a timezone"
            )
        return PublicAvailability(
            accepted_at=value,
            accepted_date=value.date(),
            precision=AvailabilityPrecision.ACCEPTANCE_TIMESTAMP,
            execution_rule=ExecutionRule.NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE,
        )
    if isinstance(value, date):
        return PublicAvailability(
            accepted_at=None,
            accepted_date=value,
            precision=AvailabilityPrecision.ACCEPTANCE_DATE_ONLY,
            execution_rule=ExecutionRule.NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE_DATE,
        )
    raise Form4ParseError("REFUSED: acceptance metadata must be a date or datetime")


def _common_stock(title: str | None) -> bool:
    if title is None:
        return False
    normalized = re.sub(r"\s+", " ", title.strip().lower())
    if "common stock" not in normalized:
        return False
    return not any(
        word in normalized
        for word in ("preferred", "option", "warrant", "unit", "phantom")
    )


def _footnote_references(element: ElementTree.Element) -> tuple[str, ...]:
    ids = {
        node.attrib.get("id", "").strip()
        for node in element.iter()
        if _local_name(node.tag) == "footnoteId"
    }
    return tuple(sorted(item for item in ids if item))


def _classify(
    *,
    form_type: str,
    owners: tuple[ReportingOwner, ...],
    derivative: bool,
    security_title: str | None,
    transaction_date: date | None,
    transaction_code: str | None,
    acquired_disposed: str | None,
    shares: Decimal | None,
    price: Decimal | None,
    direct_indirect: str | None,
    footnote_texts: tuple[str, ...],
    unresolved_footnote: bool,
    aff10b5_one: bool,
) -> tuple[ClassificationOutcome, ...]:
    reasons: list[ClassificationOutcome] = []

    def add(outcome: ClassificationOutcome) -> None:
        if outcome not in reasons:
            reasons.append(outcome)

    if form_type not in CANONICAL_SPEC.allowed_forms:
        add(ClassificationOutcome.EXCLUDE_UNSUPPORTED_FORM)
    elif form_type != CANONICAL_SPEC.primary_form:
        add(ClassificationOutcome.EXCLUDE_AMENDED_FILING)
    if derivative:
        add(ClassificationOutcome.EXCLUDE_DERIVATIVE)
    if len(owners) != 1:
        add(ClassificationOutcome.EXCLUDE_MULTIPLE_REPORTING_OWNERS)
    if not owners or any(not owner.relationship_complete for owner in owners):
        add(ClassificationOutcome.EXCLUDE_INCOMPLETE_OWNER_RELATIONSHIP)
    has_ten_percent_owner = any(owner.is_ten_percent_owner for owner in owners)
    if has_ten_percent_owner:
        add(ClassificationOutcome.EXCLUDE_TEN_PERCENT_OWNER)
    if (
        owners
        and not has_ten_percent_owner
        and all(not owner.is_director and not owner.is_officer for owner in owners)
    ):
        add(ClassificationOutcome.EXCLUDE_NO_OFFICER_OR_DIRECTOR)
    if not _common_stock(security_title):
        add(ClassificationOutcome.EXCLUDE_NON_COMMON_STOCK)
    code = transaction_code.upper() if transaction_code else None
    if code == "S":
        add(ClassificationOutcome.EXCLUDE_SALE)
    elif code == "G":
        add(ClassificationOutcome.EXCLUDE_GIFT)
    elif code == "A":
        add(ClassificationOutcome.EXCLUDE_AWARD_OR_GRANT)
    elif code != CANONICAL_SPEC.transaction_code:
        add(ClassificationOutcome.EXCLUDE_NON_PURCHASE_TRANSACTION_CODE)
    if acquired_disposed != CANONICAL_SPEC.acquired_disposed_code:
        add(ClassificationOutcome.EXCLUDE_NOT_ACQUIRED)
    if direct_indirect != CANONICAL_SPEC.ownership_nature:
        add(ClassificationOutcome.EXCLUDE_INDIRECT_OWNERSHIP)
    if transaction_date is None:
        add(ClassificationOutcome.EXCLUDE_MISSING_TRANSACTION_DATE)
    if shares is None or shares <= 0:
        add(ClassificationOutcome.EXCLUDE_NONPOSITIVE_SHARES)

    combined_footnotes = " ".join(footnote_texts).lower()
    if any(word in combined_footnotes for word in _RANGE_WORDS):
        add(ClassificationOutcome.EXCLUDE_PRICE_RANGE)
    if price is None or price <= 0:
        add(ClassificationOutcome.EXCLUDE_MISSING_OR_NONPOSITIVE_PRICE)
    if any(word in combined_footnotes for word in _PRIVATE_WORDS):
        add(ClassificationOutcome.EXCLUDE_PRIVATE_PURCHASE)
    if aff10b5_one or any(word in combined_footnotes for word in _PLAN_WORDS):
        add(ClassificationOutcome.EXCLUDE_10B5_1)
    if unresolved_footnote:
        add(ClassificationOutcome.EXCLUDE_UNRESOLVED_FOOTNOTE)

    purchase_value = shares * price if shares is not None and price is not None else None
    if (
        purchase_value is not None
        and purchase_value < CANONICAL_SPEC.minimum_purchase_value_usd
    ):
        add(ClassificationOutcome.EXCLUDE_BELOW_MINIMUM_VALUE)
    if not reasons:
        return (ClassificationOutcome.INCLUDE_CANONICAL_PURCHASE,)
    return tuple(reasons)


def parse_form4_xml(
    xml_bytes: bytes,
    *,
    accession_number: str,
    acceptance: datetime | date,
    source_name: str,
    amends_accession: str | None = None,
) -> ParsedFiling:
    """Parse one trusted byte image without performing any external access."""

    if not isinstance(xml_bytes, bytes):
        raise Form4ParseError("REFUSED: XML source must be bytes")
    if not xml_bytes or len(xml_bytes) > MAX_XML_BYTES:
        raise Form4ParseError("REFUSED: XML source is empty or exceeds 2 MiB")
    upper_source = xml_bytes.upper()
    if b"<!DOCTYPE" in upper_source or b"<!ENTITY" in upper_source:
        raise Form4ParseError("REFUSED: DTD/entity declarations are prohibited")
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise Form4ParseError(f"REFUSED: malformed Form 4 XML: {exc}") from exc
    if _local_name(root.tag) != "ownershipDocument":
        raise Form4ParseError("REFUSED: root element is not ownershipDocument")

    form_type = _required_text(root, "documentType").upper()
    if form_type not in PARSED_OWNERSHIP_FORMS:
        raise Form4ParseError(
            f"REFUSED: unsupported ownership-document form {form_type}"
        )
    if (form_type == "4/A") != (amends_accession is not None):
        raise Form4ParseError(
            "REFUSED: form type and amendment-lineage metadata disagree"
        )

    issuer = _first(root, "issuer")
    if issuer is None:
        raise Form4ParseError("REFUSED: issuer block is missing")
    issuer_cik = _normalize_cik(_required_text(issuer, "issuerCik"), "issuer CIK")
    issuer_name = _required_text(issuer, "issuerName")
    issuer_symbol = _text(issuer, "issuerTradingSymbol")

    owners: list[ReportingOwner] = []
    for block in _descendants(root, "reportingOwner"):
        owner_id = _first(block, "reportingOwnerId")
        relationship = _first(block, "reportingOwnerRelationship")
        if owner_id is None:
            raise Form4ParseError("REFUSED: reporting owner identity is missing")
        owners.append(
            ReportingOwner(
                owner_cik=_normalize_cik(
                    _required_text(owner_id, "rptOwnerCik"), "reporting owner CIK"
                ),
                owner_name=_required_text(owner_id, "rptOwnerName"),
                is_director=_parse_bool(_text(relationship, "isDirector")),
                is_officer=_parse_bool(_text(relationship, "isOfficer")),
                is_ten_percent_owner=_parse_bool(
                    _text(relationship, "isTenPercentOwner")
                ),
                is_other=_parse_bool(_text(relationship, "isOther")),
                officer_title=_text(relationship, "officerTitle"),
            )
        )
    owner_tuple = tuple(owners)

    footnote_map: dict[str, str] = {}
    for node in _descendants(root, "footnote"):
        footnote_id = node.attrib.get("id", "").strip()
        text = " ".join(part.strip() for part in node.itertext() if part.strip())
        if not footnote_id or not text:
            raise Form4ParseError("REFUSED: footnote id/text is incomplete")
        if footnote_id in footnote_map:
            raise Form4ParseError(f"REFUSED: duplicate footnote id {footnote_id}")
        footnote_map[footnote_id] = text

    source_sha256 = hashlib.sha256(xml_bytes).hexdigest()
    envelope = FilingEnvelope(
        accession_number=accession_number,
        form_type=form_type,
        issuer_cik=issuer_cik,
        issuer_name=issuer_name,
        issuer_symbol_raw=issuer_symbol,
        availability=_availability(acceptance),
        source_name=source_name,
        source_sha256=source_sha256,
        amends_accession=amends_accession,
    )

    transaction_nodes: list[tuple[ElementTree.Element, bool]] = []
    for table_name, row_name, derivative in (
        ("nonDerivativeTable", "nonDerivativeTransaction", False),
        ("derivativeTable", "derivativeTransaction", True),
    ):
        for table in _descendants(root, table_name):
            transaction_nodes.extend(
                (row, derivative) for row in _children(table, row_name)
            )

    transactions: list[ParsedTransaction] = []
    for row_index, (row, derivative) in enumerate(transaction_nodes):
        security_title = _value(row, "securityTitle")
        transaction_date = _parse_date(_value(row, "transactionDate"))
        transaction_code = _text(row, "transactionCode")
        acquired_disposed = _value(row, "transactionAcquiredDisposedCode")
        shares = _parse_decimal(_value(row, "transactionShares"))
        price = _parse_decimal(_value(row, "transactionPricePerShare"))
        shares_owned_after = _parse_decimal(
            _value(row, "sharesOwnedFollowingTransaction")
        )
        direct_indirect = _value(row, "directOrIndirectOwnership")
        references = _footnote_references(row)
        unresolved = any(reference not in footnote_map for reference in references)
        texts = tuple(footnote_map[item] for item in references if item in footnote_map)
        aff10b5_one = _parse_bool(_text(row, "aff10b5One")) is True
        outcomes = _classify(
            form_type=form_type,
            owners=owner_tuple,
            derivative=derivative,
            security_title=security_title,
            transaction_date=transaction_date,
            transaction_code=transaction_code,
            acquired_disposed=acquired_disposed,
            shares=shares,
            price=price,
            direct_indirect=direct_indirect,
            footnote_texts=texts,
            unresolved_footnote=unresolved,
            aff10b5_one=aff10b5_one,
        )
        purchase_value = (
            shares * price if shares is not None and price is not None else None
        )
        event_id = hashlib.sha256(
            f"{accession_number}:{source_sha256}:{row_index}:{int(derivative)}".encode()
        ).hexdigest()
        transactions.append(
            ParsedTransaction(
                event_id=event_id,
                accession_number=accession_number,
                source_sha256=source_sha256,
                row_index=row_index,
                derivative=derivative,
                security_title_raw=security_title,
                transaction_date=transaction_date,
                transaction_code=transaction_code,
                acquired_disposed_code=acquired_disposed,
                shares=shares,
                price_per_share=price,
                purchase_value_usd=purchase_value,
                shares_owned_after=shares_owned_after,
                direct_indirect=direct_indirect,
                footnote_ids=references,
                footnote_texts=texts,
                outcomes=outcomes,
            )
        )

    return ParsedFiling(
        envelope=envelope,
        reporting_owners=owner_tuple,
        footnotes=tuple(sorted(footnote_map.items())),
        transactions=tuple(transactions),
    )
