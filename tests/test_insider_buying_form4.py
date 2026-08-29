"""Dangerous-direction tests for the offline Insider Buying IB-0/IB-1 slice."""
from __future__ import annotations

import ast
import hashlib
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from research.insider_buying import (
    CANONICAL_SPEC,
    ClassificationOutcome,
    TransactionDiagnostic,
    build_filing_corpus,
    parse_form4_xml,
)
from research.insider_buying.contracts import (
    AvailabilityPrecision,
    ContractError,
    ExecutionRule,
    PublicAvailability,
    ReportingOwner,
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


def _with_footnote(text: str) -> bytes:
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionPricePerShare><value>12.50</value></transactionPricePerShare>",
        b'<transactionPricePerShare><value>12.50</value>'
        b'<footnoteId id="F1"/></transactionPricePerShare>',
    )
    return _replace_once(
        payload,
        b"</ownershipDocument>",
        f'<footnotes><footnote id="F1">{text}</footnote></footnotes>'
        f"</ownershipDocument>".encode("utf-8"),
    )


def test_preregistered_constants_are_frozen_before_any_outcome_access():
    assert CANONICAL_SPEC.version == "INSETF-IB0-v1"
    assert CANONICAL_SPEC.allowed_forms == ("4", "4/A")
    assert CANONICAL_SPEC.minimum_purchase_value_usd == Decimal("50000")
    assert CANONICAL_SPEC.lot_aggregation_key == (
        "reporting_owner_identity",
        "security_identity",
        "transaction_date",
    )
    assert CANONICAL_SPEC.minimum_purchase_value_applies_after_aggregation is True
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


def test_canonical_fixture_has_one_structurally_eligible_hashed_decimal_row():
    payload = _fixture("form4_original.xml")
    filing = _parse_original(payload)

    assert filing.envelope.issuer_cik == "0000123456"
    assert filing.envelope.source_sha256 == hashlib.sha256(payload).hexdigest()
    assert len(filing.reporting_owners) == 1
    assert len(filing.transactions) == 1
    transaction = filing.transactions[0]
    assert transaction.eligible_for_lot_aggregation
    assert transaction.outcomes == (
        ClassificationOutcome.ELIGIBLE_FOR_LOT_AGGREGATION,
    )
    assert transaction.shares == Decimal("5000")
    assert transaction.price_per_share == Decimal("12.50")
    assert transaction.purchase_value_usd == Decimal("62500.00")
    assert transaction.aff10b5_one is None
    assert transaction.event_id == _parse_original(payload).transactions[0].event_id


def test_same_date_lots_are_deferred_to_aggregation_before_the_value_gate():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionShares><value>5000</value></transactionShares>",
        b"<transactionShares><value>2400</value></transactionShares>",
    )
    row_start = payload.index(b"<nonDerivativeTransaction>")
    row_end = payload.index(b"</nonDerivativeTransaction>") + len(
        b"</nonDerivativeTransaction>"
    )
    row = payload[row_start:row_end]
    payload = payload[:row_end] + row + payload[row_end:]

    transactions = _parse_original(payload).transactions
    assert len(transactions) == 2
    assert [item.purchase_value_usd for item in transactions] == [
        Decimal("30000.00"),
        Decimal("30000.00"),
    ]
    assert [item.row_index for item in transactions] == [0, 1]
    assert len({item.event_id for item in transactions}) == 2
    assert [item.event_id for item in transactions] == [
        item.event_id for item in _parse_original(payload).transactions
    ]
    assert all(item.eligible_for_lot_aggregation for item in transactions)
    assert sum(item.purchase_value_usd for item in transactions) == Decimal("60000.00")


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
    assert not filing.transactions[0].eligible_for_lot_aggregation


def test_indirect_ownership_is_named_and_excluded():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<directOrIndirectOwnership><value>D</value>",
        b"<directOrIndirectOwnership><value>I</value>",
    )
    transaction = _parse_original(payload).transactions[0]
    assert ClassificationOutcome.EXCLUDE_INDIRECT_OWNERSHIP in transaction.outcomes
    assert not transaction.eligible_for_lot_aggregation


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
    assert not transaction.eligible_for_lot_aggregation


@pytest.mark.parametrize("code", ["p", "s", "g", "a"])
def test_transaction_code_case_is_not_normalized_into_validity(code):
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionCode>P</transactionCode>",
        f"<transactionCode>{code}</transactionCode>".encode(),
    )
    transaction = _parse_original(payload).transactions[0]
    assert transaction.transaction_code == code
    assert transaction.outcomes == (
        ClassificationOutcome.EXCLUDE_NON_PURCHASE_TRANSACTION_CODE,
    )


@pytest.mark.parametrize("raw_flag", ["yes", "no", "TRUE", "FALSE"])
def test_owner_relationship_boolean_requires_exact_xml_schema_lexical_form(
    raw_flag,
):
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<isOfficer>1</isOfficer>",
        f"<isOfficer>{raw_flag}</isOfficer>".encode(),
    )
    filing = _parse_original(payload)
    assert filing.reporting_owners[0].is_officer is None
    assert (
        ClassificationOutcome.EXCLUDE_INCOMPLETE_OWNER_RELATIONSHIP
        in filing.transactions[0].outcomes
    )
    assert not filing.transactions[0].eligible_for_lot_aggregation


@pytest.mark.parametrize("raw_flag", ["yes", "no", "TRUE", "FALSE"])
def test_10b5_boolean_requires_exact_xml_schema_lexical_form(raw_flag):
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionCoding><transactionCode>P</transactionCode>",
        f"<transactionCoding><aff10b5One>{raw_flag}</aff10b5One>"
        f"<transactionCode>P</transactionCode>".encode(),
    )
    transaction = _parse_original(payload).transactions[0]
    assert transaction.eligible_for_lot_aggregation
    assert transaction.aff10b5_one is None
    assert TransactionDiagnostic.TEN_B5_1_PLAN not in transaction.diagnostics


@pytest.mark.parametrize("form_type", ["4/a", "4/a ", "four"])
def test_document_type_case_is_not_normalized_into_validity(form_type):
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<documentType>4</documentType>",
        f"<documentType>{form_type}</documentType>".encode(),
    )
    with pytest.raises(Form4ParseError, match="unsupported ownership-document"):
        _parse_original(payload)


def test_unicode_digit_reporting_owner_cik_is_refused_by_xml_boundary():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<rptOwnerCik>987654</rptOwnerCik>",
        "<rptOwnerCik>٩٨٧٦٥٤</rptOwnerCik>".encode("utf-8"),
    )
    with pytest.raises(Form4ParseError, match="reporting owner CIK"):
        _parse_original(payload)


@pytest.mark.parametrize(
    "overrides",
    [
        {"owner_cik": "٠٠٠٠٩٨٧٦٥٤"},
        {"owner_cik": "987654"},
        {"owner_cik": 987654},
        {"owner_name": " "},
        {"owner_name": 987654},
        {"is_officer": 1},
        {"is_director": "false"},
        {"is_ten_percent_owner": 1},
        {"is_other": "false"},
        {"officer_title": " "},
        {"officer_title": 987654},
    ],
)
def test_reporting_owner_contract_rejects_ambiguous_identity_and_flags(overrides):
    values = {
        "owner_cik": "0000987654",
        "owner_name": "Fixture Officer",
        "is_director": False,
        "is_officer": True,
        "is_ten_percent_owner": False,
        "is_other": False,
        "officer_title": "Chief Financial Officer",
    }
    values.update(overrides)
    with pytest.raises(ContractError, match="REFUSED"):
        ReportingOwner(**values)


def test_officer_or_director_remains_eligible_when_also_ten_percent_owner():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<isTenPercentOwner>0</isTenPercentOwner>",
        b"<isTenPercentOwner>1</isTenPercentOwner>",
    )
    transaction = _parse_original(payload).transactions[0]
    assert transaction.eligible_for_lot_aggregation
    assert transaction.diagnostics == (
        TransactionDiagnostic.TEN_PERCENT_OWNER_WITH_OFFICER_OR_DIRECTOR_ROLE,
    )


def test_director_only_remains_eligible_when_also_ten_percent_owner():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<isOfficer>1</isOfficer>",
        b"<isOfficer>0</isOfficer>",
    )
    payload = _replace_once(
        payload,
        b"<isDirector>0</isDirector>",
        b"<isDirector>1</isDirector>",
    )
    payload = _replace_once(
        payload,
        b"<isTenPercentOwner>0</isTenPercentOwner>",
        b"<isTenPercentOwner>1</isTenPercentOwner>",
    )
    transaction = _parse_original(payload).transactions[0]
    assert transaction.eligible_for_lot_aggregation
    assert transaction.diagnostics == (
        TransactionDiagnostic.TEN_PERCENT_OWNER_WITH_OFFICER_OR_DIRECTOR_ROLE,
    )


def test_non_ten_percent_owner_without_officer_or_director_role_is_excluded():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<isOfficer>1</isOfficer>",
        b"<isOfficer>0</isOfficer>",
    )
    transaction = _parse_original(payload).transactions[0]
    assert ClassificationOutcome.EXCLUDE_NO_OFFICER_OR_DIRECTOR in transaction.outcomes
    assert ClassificationOutcome.EXCLUDE_TEN_PERCENT_OWNER not in transaction.outcomes
    assert transaction.diagnostics == ()
    assert not transaction.eligible_for_lot_aggregation


def test_pure_ten_percent_owner_without_officer_or_director_role_is_excluded():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<isOfficer>1</isOfficer>",
        b"<isOfficer>0</isOfficer>",
    )
    payload = _replace_once(
        payload,
        b"<isTenPercentOwner>0</isTenPercentOwner>",
        b"<isTenPercentOwner>1</isTenPercentOwner>",
    )
    transaction = _parse_original(payload).transactions[0]
    assert ClassificationOutcome.EXCLUDE_TEN_PERCENT_OWNER in transaction.outcomes
    assert ClassificationOutcome.EXCLUDE_NO_OFFICER_OR_DIRECTOR in transaction.outcomes
    assert (
        TransactionDiagnostic.TEN_PERCENT_OWNER_WITH_OFFICER_OR_DIRECTOR_ROLE
        not in transaction.diagnostics
    )
    assert not transaction.eligible_for_lot_aggregation


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
    assert transaction.diagnostics == (
        TransactionDiagnostic.PRIVATE_PURCHASE_FOOTNOTE_MENTION,
        TransactionDiagnostic.TEN_B5_1_FOOTNOTE_MENTION,
    )
    assert transaction.footnote_ids == ("F1",)


def test_private_and_10b5_1_purchases_are_retained_as_features_not_excluded():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionCoding><transactionCode>P</transactionCode>",
        b"<transactionCoding><aff10b5One>1</aff10b5One><transactionCode>P</transactionCode>",
    )
    payload = _replace_once(
        payload,
        b"<transactionPricePerShare><value>12.50</value></transactionPricePerShare>",
        b'<transactionPricePerShare><value>12.50</value><footnoteId id="F1"/></transactionPricePerShare>',
    )
    payload = _replace_once(
        payload,
        b"</ownershipDocument>",
        b'<footnotes><footnote id="F1">Privately negotiated purchase.</footnote></footnotes></ownershipDocument>',
    )
    transaction = _parse_original(payload).transactions[0]
    assert transaction.eligible_for_lot_aggregation
    assert transaction.aff10b5_one is True
    assert transaction.diagnostics == (
        TransactionDiagnostic.PRIVATE_PURCHASE_FOOTNOTE_MENTION,
        TransactionDiagnostic.TEN_B5_1_PLAN,
    )


@pytest.mark.parametrize("raw_date", ["20260818", "2026-W34-2"])
def test_transaction_date_requires_exact_sec_xml_lexical_form(raw_date):
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionDate><value>2026-08-18</value></transactionDate>",
        f"<transactionDate><value>{raw_date}</value></transactionDate>".encode(),
    )
    transaction = _parse_original(payload).transactions[0]
    assert transaction.transaction_date is None
    assert ClassificationOutcome.EXCLUDE_MISSING_TRANSACTION_DATE in transaction.outcomes


@pytest.mark.parametrize("raw_shares", ["1e2", "1e999999", "9" * 65, "1,2"])
def test_malformed_or_unbounded_decimal_text_fails_closed(raw_shares):
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionShares><value>5000</value></transactionShares>",
        f"<transactionShares><value>{raw_shares}</value></transactionShares>".encode(),
    )
    transaction = _parse_original(payload).transactions[0]
    assert transaction.shares is None
    assert transaction.purchase_value_usd is None
    assert ClassificationOutcome.EXCLUDE_NONPOSITIVE_SHARES in transaction.outcomes


def test_large_bounded_decimal_product_is_computed_without_context_rounding():
    shares = "123456789012345678901234567890"
    price = "987654321098765432109876543210"
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionShares><value>5000</value></transactionShares>",
        f"<transactionShares><value>{shares}</value></transactionShares>".encode(),
    )
    payload = _replace_once(
        payload,
        b"<transactionPricePerShare><value>12.50</value></transactionPricePerShare>",
        f"<transactionPricePerShare><value>{price}</value>"
        f"</transactionPricePerShare>".encode(),
    )
    transaction = _parse_original(payload).transactions[0]
    with localcontext() as context:
        context.prec = 60
        expected = Decimal(shares) * Decimal(price)
    assert transaction.purchase_value_usd == expected
    assert transaction.eligible_for_lot_aggregation


@pytest.mark.parametrize(
    "private_text",
    ["Private purchase.", "Private transaction.", "Privately negotiated purchase."],
)
def test_each_frozen_private_purchase_phrase_emits_the_diagnostic(private_text):
    transaction = _parse_original(_with_footnote(private_text)).transactions[0]
    assert transaction.eligible_for_lot_aggregation
    assert transaction.diagnostics == (
        TransactionDiagnostic.PRIVATE_PURCHASE_FOOTNOTE_MENTION,
    )


@pytest.mark.parametrize("plan_text", ["10b5-1 plan.", "10b5 1 plan."])
def test_each_frozen_10b5_1_phrase_emits_the_diagnostic(plan_text):
    transaction = _parse_original(_with_footnote(plan_text)).transactions[0]
    assert transaction.eligible_for_lot_aggregation
    assert transaction.aff10b5_one is None
    assert transaction.diagnostics == (
        TransactionDiagnostic.TEN_B5_1_FOOTNOTE_MENTION,
    )


@pytest.mark.parametrize(
    "footnote_text",
    [
        "This was not a private purchase and was not made under a 10b5-1 plan.",
        "Private purchase under a 10b5-1 plan.",
    ],
)
def test_footnote_tokens_remain_mentions_when_structured_10b5_value_is_false(
    footnote_text,
):
    payload = _with_footnote(footnote_text)
    payload = _replace_once(
        payload,
        b"<transactionCoding><transactionCode>P</transactionCode>",
        b"<transactionCoding><aff10b5One>0</aff10b5One>"
        b"<transactionCode>P</transactionCode>",
    )
    transaction = _parse_original(payload).transactions[0]
    assert transaction.eligible_for_lot_aggregation
    assert transaction.aff10b5_one is False
    assert transaction.diagnostics == (
        TransactionDiagnostic.PRIVATE_PURCHASE_FOOTNOTE_MENTION,
        TransactionDiagnostic.TEN_B5_1_FOOTNOTE_MENTION,
    )
    assert TransactionDiagnostic.TEN_B5_1_PLAN not in transaction.diagnostics


def test_unknown_footnote_reference_is_retained_as_an_exclusion():
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"<transactionShares><value>5000</value></transactionShares>",
        b'<transactionShares><value>5000</value><footnoteId id="MISSING"/></transactionShares>',
    )
    transaction = _parse_original(payload).transactions[0]
    assert transaction.footnote_ids == ("MISSING",)
    assert ClassificationOutcome.EXCLUDE_UNRESOLVED_FOOTNOTE in transaction.outcomes


@pytest.mark.parametrize(
    "reference",
    [b"<footnoteId/>", b'<footnoteId id=" "/>'],
)
def test_blank_or_missing_transaction_footnote_reference_id_is_refused(reference):
    payload = _replace_once(
        _fixture("form4_original.xml"),
        b"</transactionShares>",
        reference + b"</transactionShares>",
    )
    with pytest.raises(Form4ParseError, match="footnote reference id is missing"):
        _parse_original(payload)


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
        "http",
        "qc",
        "quantconnect",
        "requests",
        "scheduler",
        "socket",
        "ftplib",
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


# ---------------------------------------------------------------------------
# Direct PublicAvailability contract guards.
#
# The tests above reach availability semantics through parse_form4_xml(), so
# they exercise the parser's refusals rather than the contract's own. A
# mutation sweep of PublicAvailability.__post_init__ showed all five guards
# surviving with the suite green, which means the object that encodes the
# look-ahead invariant was unprotected on any path that does not go through
# the XML parser. The blueprint's IB-1 bulk-dataset ingest is exactly such a
# path: it constructs availability from the SEC quarterly tables directly.
# These tests pin each guard at the contract boundary.
# ---------------------------------------------------------------------------


def _timestamp_availability(**overrides):
    kwargs = {
        "accepted_at": ACCEPTED,
        "accepted_date": ACCEPTED.date(),
        "precision": AvailabilityPrecision.ACCEPTANCE_TIMESTAMP,
        "execution_rule": ExecutionRule.NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE,
    }
    kwargs.update(overrides)
    return PublicAvailability(**kwargs)


def _date_only_availability(**overrides):
    kwargs = {
        "accepted_at": None,
        "accepted_date": ACCEPTED.date(),
        "precision": AvailabilityPrecision.ACCEPTANCE_DATE_ONLY,
        "execution_rule": ExecutionRule.NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE_DATE,
    }
    kwargs.update(overrides)
    return PublicAvailability(**kwargs)


def test_valid_availability_values_are_accepted_at_the_contract_boundary():
    """The guards below must refuse bad input without refusing good input."""
    timestamped = _timestamp_availability()
    assert timestamped.accepted_at == ACCEPTED
    date_only = _date_only_availability()
    assert date_only.accepted_at is None


def test_contract_refuses_naive_acceptance_instant_without_the_parser():
    with pytest.raises(ContractError, match="timezone-aware"):
        _timestamp_availability(accepted_at=datetime(2026, 8, 20, 17, 30))


def test_contract_refuses_missing_instant_for_timestamp_precision():
    with pytest.raises(ContractError, match="timezone-aware"):
        _timestamp_availability(accepted_at=None)


def test_contract_refuses_accepted_date_disagreeing_with_the_instant():
    """A disagreeing date could advance availability by a whole session."""
    with pytest.raises(ContractError, match="accepted date"):
        _timestamp_availability(accepted_date=date(2026, 8, 19))


def test_contract_refuses_timestamp_precision_with_the_date_only_rule():
    with pytest.raises(ContractError, match="wrong execution rule"):
        _timestamp_availability(
            execution_rule=ExecutionRule.NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE_DATE
        )


def test_contract_refuses_date_only_precision_carrying_an_instant():
    """Date-only evidence must not be upgraded into an intraday instant."""
    with pytest.raises(ContractError, match="contains an instant"):
        _date_only_availability(accepted_at=ACCEPTED)


def test_contract_refuses_date_only_precision_with_the_timestamp_rule():
    with pytest.raises(ContractError, match="wrong execution rule"):
        _date_only_availability(
            execution_rule=ExecutionRule.NEXT_REGULAR_OPEN_AFTER_ACCEPTANCE
        )


@pytest.mark.parametrize("accepted_date", [None, "2026-08-20", ACCEPTED])
def test_contract_refuses_non_date_accepted_date_values(accepted_date):
    with pytest.raises(ContractError, match="exact date"):
        _date_only_availability(accepted_date=accepted_date)


def test_contract_refuses_unknown_precision_instead_of_treating_it_as_date_only():
    with pytest.raises(ContractError, match="precision"):
        _date_only_availability(precision="unknown")


def test_contract_refuses_unknown_execution_rule_type():
    with pytest.raises(ContractError, match="execution rule"):
        _date_only_availability(execution_rule="next_regular_open")


def test_contract_refuses_non_datetime_acceptance_instant():
    with pytest.raises(ContractError, match="must be a datetime"):
        _timestamp_availability(accepted_at=ACCEPTED.date())


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
def test_utf16_dtd_and_entity_declarations_cannot_bypass_the_guard(encoding):
    source = _fixture("form4_original.xml").decode("utf-8")
    source = source.replace(
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<!DOCTYPE ownershipDocument [<!ENTITY expanded "ENTITY_EXPANDED">]>',
        1,
    ).replace("Fixture Manufacturing, Inc.", "&expanded;", 1)
    with pytest.raises(Form4ParseError, match="UTF-8|DTD/entity"):
        _parse_original(source.encode(encoding))


def test_nul_free_latin1_xml_is_refused_instead_of_silently_redecoded():
    source = _fixture("form4_original.xml").decode("utf-8")
    source = source.replace("Fixture Manufacturing, Inc.", "Café, Inc.", 1)
    with pytest.raises(Form4ParseError, match="UTF-8"):
        _parse_original(source.encode("iso-8859-1"))


def test_conflicting_xml_encoding_declaration_cannot_corrupt_utf8_text():
    source = _fixture("form4_original.xml").decode("utf-8")
    source = source.replace('encoding="UTF-8"', 'encoding="ISO-8859-1"', 1)
    source = source.replace("Fixture Manufacturing, Inc.", "Café, Inc.", 1)
    with pytest.raises(Form4ParseError, match="declaration.*UTF-8"):
        _parse_original(source.encode("utf-8"))
