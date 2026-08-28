"""Dangerous-direction tests for the offline Insider Buying IB-0/IB-1 slice."""
from __future__ import annotations

import ast
import hashlib
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from research.insider_buying import (
    CANONICAL_SPEC,
    ClassificationOutcome,
    build_filing_corpus,
    parse_form4_xml,
)
from research.insider_buying.contracts import (
    AvailabilityPrecision,
    ContractError,
    ExecutionRule,
)
from research.insider_buying.form4_xml import Form4ParseError


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "insider_buying"
PACKAGE = REPO_ROOT / "research" / "insider_buying"
ORIGINAL_ACCESSION = "0000123456-26-000001"
AMENDMENT_ACCESSION = "0000123456-26-000002"
ACCEPTED = datetime(2026, 8, 20, 17, 30, tzinfo=timezone.utc)


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _parse_original(
    payload: bytes | None = None,
    *,
    acceptance: datetime | date = ACCEPTED,
):
    return parse_form4_xml(
        payload if payload is not None else _fixture("form4_original.xml"),
        accession_number=ORIGINAL_ACCESSION,
        acceptance=acceptance,
        source_name="synthetic/form4_original.xml",
    )


def _replace_once(payload: bytes, old: bytes, new: bytes) -> bytes:
    assert payload.count(old) == 1
    return payload.replace(old, new, 1)


def test_preregistered_constants_are_frozen_before_any_outcome_access():
    assert CANONICAL_SPEC.version == "INSETF-IB0-v1"
    assert CANONICAL_SPEC.allowed_forms == ("4", "4/A")
    assert CANONICAL_SPEC.minimum_purchase_value_usd == Decimal("50000")
    assert CANONICAL_SPEC.score_formula == "ln(1 + purchase_value_usd / 50000)"
    assert CANONICAL_SPEC.decay_half_life_trading_days == 20
    assert CANONICAL_SPEC.lookback_trading_days == 30
    assert CANONICAL_SPEC.event_study_horizons_trading_days == (
        1,
        5,
        10,
        20,
        40,
        60,
        120,
    )
    assert CANONICAL_SPEC.primary_horizons_trading_days == (5, 20, 60)
    assert CANONICAL_SPEC.cost_grid_bps_per_side == (0, 5, 10, 20)
    assert CANONICAL_SPEC.outcomes_authorized is False
    assert CANONICAL_SPEC.authorized_outcome_looks == 0
    with pytest.raises(FrozenInstanceError):
        CANONICAL_SPEC.lookback_trading_days = 20  # type: ignore[misc]


def test_canonical_fixture_includes_exactly_one_hashed_decimal_row():
    payload = _fixture("form4_original.xml")
    filing = _parse_original(payload)

    assert filing.envelope.issuer_cik == "0000123456"
    assert filing.envelope.source_sha256 == hashlib.sha256(payload).hexdigest()
    assert len(filing.reporting_owners) == 1
    assert len(filing.transactions) == 1
    transaction = filing.transactions[0]
    assert transaction.included
    assert transaction.outcomes == (
        ClassificationOutcome.INCLUDE_CANONICAL_PURCHASE,
    )
    assert transaction.shares == Decimal("5000")
    assert transaction.price_per_share == Decimal("12.50")
    assert transaction.purchase_value_usd == Decimal("62500.00")
    assert transaction.event_id == _parse_original(payload).transactions[0].event_id


def test_transaction_date_never_becomes_public_availability():
    filing = _parse_original()
    transaction = filing.transactions[0]
    availability = filing.envelope.availability

    assert transaction.transaction_date == date(2026, 8, 18)
    assert availability.accepted_at == ACCEPTED
    assert availability.accepted_date == date(2026, 8, 20)
    assert availability.precision is AvailabilityPrecision.ACCEPTANCE_TIMESTAMP
    assert (
        availability.execution_rule
        is ExecutionRule.NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE
    )
    assert availability.accepted_date != transaction.transaction_date


def test_exact_acceptance_does_not_authorize_same_instant_execution():
    filing = _parse_original()
    availability = filing.envelope.availability
    assert availability.execution_rule.value.startswith("next_regular_open_after_")
    assert "same" not in availability.execution_rule.value


def test_date_only_acceptance_preserves_uncertainty_and_next_open_rule():
    filing = _parse_original(acceptance=date(2026, 8, 20))
    availability = filing.envelope.availability
    assert availability.accepted_at is None
    assert availability.precision is AvailabilityPrecision.ACCEPTANCE_DATE_ONLY
    assert (
        availability.execution_rule
        is ExecutionRule.NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE_DATE
    )


def test_naive_acceptance_timestamp_is_refused():
    with pytest.raises(Form4ParseError, match="timezone"):
        _parse_original(acceptance=datetime(2026, 8, 20, 17, 30))


def test_form5_can_never_enter_the_canonical_family():
    filing = parse_form4_xml(
        _fixture("form5.xml"),
        accession_number="0000123456-26-000005",
        acceptance=ACCEPTED,
        source_name="synthetic/form5.xml",
    )
    assert len(filing.transactions) == 1
    assert filing.transactions[0].outcomes == (
        ClassificationOutcome.EXCLUDE_UNSUPPORTED_FORM,
    )
    assert not filing.transactions[0].included


def test_indirect_ownership_is_named_and_excluded():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<directOrIndirectOwnership><value>D</value>",
        b"<directOrIndirectOwnership><value>I</value>",
    )
    transaction = _parse_original(payload).transactions[0]
    assert ClassificationOutcome.EXCLUDE_INDIRECT_OWNERSHIP in transaction.outcomes
    assert not transaction.included


def test_missing_price_is_retained_as_a_named_exclusion():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionPricePerShare><value>12.50</value></transactionPricePerShare>",
        b"<transactionPricePerShare/>",
    )
    transaction = _parse_original(payload).transactions[0]
    assert transaction.price_per_share is None
    assert transaction.purchase_value_usd is None
    assert (
        ClassificationOutcome.EXCLUDE_MISSING_OR_NONPOSITIVE_PRICE
        in transaction.outcomes
    )


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("S", ClassificationOutcome.EXCLUDE_SALE),
        ("G", ClassificationOutcome.EXCLUDE_GIFT),
        ("A", ClassificationOutcome.EXCLUDE_AWARD_OR_GRANT),
        ("M", ClassificationOutcome.EXCLUDE_NON_PURCHASE_TRANSACTION_CODE),
    ],
)
def test_non_purchase_codes_receive_specific_named_outcomes(code, expected):
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionCode>P</transactionCode>",
        f"<transactionCode>{code}</transactionCode>".encode(),
    )
    transaction = _parse_original(payload).transactions[0]
    assert expected in transaction.outcomes
    assert not transaction.included


def test_ten_percent_owner_is_separate_even_when_also_an_officer():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<isTenPercentOwner>0</isTenPercentOwner>",
        b"<isTenPercentOwner>1</isTenPercentOwner>",
    )
    transaction = _parse_original(payload).transactions[0]
    assert ClassificationOutcome.EXCLUDE_TEN_PERCENT_OWNER in transaction.outcomes
    assert not transaction.included


def test_joint_owner_filing_emits_one_event_and_excludes_duplication():
    filing = parse_form4_xml(
        _fixture("form4_joint_owners.xml"),
        accession_number="0000123456-26-000003",
        acceptance=ACCEPTED,
        source_name="synthetic/form4_joint_owners.xml",
    )
    assert len(filing.reporting_owners) == 2
    assert len(filing.transactions) == 1
    assert (
        ClassificationOutcome.EXCLUDE_MULTIPLE_REPORTING_OWNERS
        in filing.transactions[0].outcomes
    )


def test_original_and_amendment_lineage_retains_both_as_filed_versions():
    original = _parse_original()
    amendment = parse_form4_xml(
        _fixture("form4_amendment.xml"),
        accession_number=AMENDMENT_ACCESSION,
        acceptance=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
        source_name="synthetic/form4_amendment.xml",
        amends_accession=ORIGINAL_ACCESSION,
    )
    corpus = build_filing_corpus([amendment, original])

    assert len(corpus.filings) == 2
    assert corpus.filing(ORIGINAL_ACCESSION).transactions[0].shares == Decimal("5000")
    assert corpus.filing(AMENDMENT_ACCESSION).transactions[0].shares == Decimal("6000")
    assert corpus.superseded_by == (
        (ORIGINAL_ACCESSION, (AMENDMENT_ACCESSION,)),
    )
    assert amendment.transactions[0].outcomes == (
        ClassificationOutcome.EXCLUDE_AMENDED_FILING,
    )


def test_amendment_without_original_is_refused_without_deleting_it():
    amendment = parse_form4_xml(
        _fixture("form4_amendment.xml"),
        accession_number=AMENDMENT_ACCESSION,
        acceptance=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
        source_name="synthetic/form4_amendment.xml",
        amends_accession=ORIGINAL_ACCESSION,
    )
    with pytest.raises(ContractError, match="target is absent"):
        build_filing_corpus([amendment])
    assert amendment.envelope.accession_number == AMENDMENT_ACCESSION


def test_amendment_must_have_a_later_exact_acceptance_instant():
    original = _parse_original()
    amendment = parse_form4_xml(
        _fixture("form4_amendment.xml"),
        accession_number=AMENDMENT_ACCESSION,
        acceptance=ACCEPTED,
        source_name="synthetic/form4_amendment.xml",
        amends_accession=ORIGINAL_ACCESSION,
    )
    with pytest.raises(ContractError, match="predates"):
        build_filing_corpus([original, amendment])


def test_duplicate_accession_is_refused_even_for_identical_bytes():
    original = _parse_original()
    with pytest.raises(ContractError, match="duplicate accession"):
        build_filing_corpus([original, original])


def test_form_type_and_amendment_metadata_must_agree():
    with pytest.raises(Form4ParseError, match="lineage metadata disagree"):
        parse_form4_xml(
            _fixture("form4_amendment.xml"),
            accession_number=AMENDMENT_ACCESSION,
            acceptance=ACCEPTED,
            source_name="synthetic/form4_amendment.xml",
        )
    with pytest.raises(Form4ParseError, match="lineage metadata disagree"):
        parse_form4_xml(
            _fixture("form4_original.xml"),
            accession_number=ORIGINAL_ACCESSION,
            acceptance=ACCEPTED,
            source_name="synthetic/form4_original.xml",
            amends_accession="0000123456-26-000099",
        )


def test_all_transaction_rows_are_retained_including_derivatives():
    original = _fixture("form4_original.xml")
    derivative = b"""
  <derivativeTable>
    <derivativeTransaction>
      <securityTitle><value>Employee Option</value></securityTitle>
      <transactionDate><value>2026-08-18</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>50</value></transactionShares><transactionPricePerShare><value>1000</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </derivativeTransaction>
  </derivativeTable>
"""
    payload = _replace_once(
        original,
        b"</ownershipDocument>",
        derivative + b"</ownershipDocument>",
    )
    filing = _parse_original(payload)
    assert len(filing.transactions) == 2
    assert filing.transactions[0].row_index == 0
    assert filing.transactions[1].row_index == 1
    assert ClassificationOutcome.EXCLUDE_DERIVATIVE in filing.transactions[1].outcomes


def test_ambiguous_footnote_semantics_are_named_not_suppressed():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionPricePerShare><value>12.50</value></transactionPricePerShare>",
        b'<transactionPricePerShare><value>12.50</value><footnoteId id="F1"/></transactionPricePerShare>',
    )
    payload = _replace_once(
        payload,
        b"</ownershipDocument>",
        b'<footnotes><footnote id="F1">Price range in a privately negotiated purchase under a 10b5-1 plan.</footnote></footnotes></ownershipDocument>',
    )
    transaction = _parse_original(payload).transactions[0]
    assert ClassificationOutcome.EXCLUDE_PRICE_RANGE in transaction.outcomes
    assert ClassificationOutcome.EXCLUDE_PRIVATE_PURCHASE in transaction.outcomes
    assert ClassificationOutcome.EXCLUDE_10B5_1 in transaction.outcomes
    assert transaction.footnote_ids == ("F1",)


def test_unknown_footnote_reference_is_retained_as_an_exclusion():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionShares><value>5000</value></transactionShares>",
        b'<transactionShares><value>5000</value><footnoteId id="MISSING"/></transactionShares>',
    )
    transaction = _parse_original(payload).transactions[0]
    assert transaction.footnote_ids == ("MISSING",)
    assert ClassificationOutcome.EXCLUDE_UNRESOLVED_FOOTNOTE in transaction.outcomes


def test_dtd_entity_and_oversize_inputs_fail_closed():
    entity = b'<!DOCTYPE x [<!ENTITY e "boom">]><ownershipDocument/>'
    with pytest.raises(Form4ParseError, match="DTD/entity"):
        _parse_original(entity)
    with pytest.raises(Form4ParseError, match="exceeds"):
        _parse_original(b"x" * (2 * 1024 * 1024 + 1))

    padded_entity = (
        b" " * 5000
        + b'<!DOCTYPE x [<!ENTITY e "boom">]><ownershipDocument/>'
    )
    with pytest.raises(Form4ParseError, match="DTD/entity"):
        _parse_original(padded_entity)


def test_package_has_no_provider_outcome_execution_or_scheduler_imports():
    forbidden_roots = {
        "alpaca",
        "assistant",
        "backtest",
        "execution",
        "httpx",
        "qc",
        "quantconnect",
        "requests",
        "scheduler",
        "urllib",
        "yfinance",
    }
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        assert imported.isdisjoint(forbidden_roots), (path, imported & forbidden_roots)
