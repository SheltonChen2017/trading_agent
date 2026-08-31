"""Tests for issuer-identity ambiguity detection.

The dangerous direction throughout is **under-refusal**: a ticker without a
name-based flag can still hide two issuers and silently assign one company's
ratings to another. Every test below therefore drives a case that must produce
a flag, plus the symmetric case that must NOT, so the detector cannot pass by
simply flagging everything.
"""
from __future__ import annotations

import pytest

from research.acer.dataset import build_identity, validate_identity_record

from research.acer.identity import (
    REASON_INTERLEAVED_NAMES,
    REASON_LIKELY_RENAME,
    REASON_LIKELY_REUSE,
    REASON_MISSING_COMPANY_NAME,
    REASON_MULTIPLE_COMPANY_NAMES,
    REASON_NAME_SHARED_WITH_OTHER_TICKER,
    VERDICT_AMBIGUITY_EVIDENCE,
    VERDICT_NO_AMBIGUITY_EVIDENCE,
    assess_identities,
    build_diagnostic_report,
    comparison_name,
    diagnostic_flagged_tickers,
    summarize_identities,
)
from research.acer.normalize import normalize_rows


class _Event:
    """Minimal stand-in carrying only the fields the detector reads."""

    def __init__(self, ticker: str, action_date: str, company_name: str | None):
        self.ticker = ticker
        self.action_date = action_date
        self.company_name = company_name


def _by_ticker(identities):
    return {item.ticker: item for item in identities}


def _validated_dataset_identity(event_count: int):
    rows = [
        {
            "benzinga_id": f"event-{index}",
            "date": "2024-03-14",
            "time": "14:30:00",
            "last_updated": "2024-03-14T18:31:00Z",
            "ticker": f"T{index}",
            "company_name": f"Company {index}",
            "firm": "Example Securities",
            "rating": "Buy",
        }
        for index in range(event_count)
    ]
    events, refusals = normalize_rows(rows)
    identity, events_bytes, refusals_bytes = build_identity(
        events,
        refusals,
        source_snapshot_name="snapshot-a",
        source_manifest_sha256="b" * 64,
    )
    return validate_identity_record(
        identity,
        events_bytes=events_bytes,
        refusals_bytes=refusals_bytes,
    )


# --------------------------------------------------------------------------
# The two hazards the ACER-1 audit named
# --------------------------------------------------------------------------


def test_a_symbol_reused_by_a_second_issuer_is_refused_as_reuse():
    """The BBBY pattern: a dead retailer, silence, then an unrelated reuse."""
    events = [
        _Event("BBBY", "2012-03-20", "Bed Bath & Beyond Inc"),
        _Event("BBBY", "2023-04-01", "Bed Bath & Beyond Inc"),
        _Event("BBBY", "2026-06-23", "Beyond Inc"),
    ]
    item = _by_ticker(assess_identities(events))["BBBY"]
    assert item.verdict == VERDICT_AMBIGUITY_EVIDENCE
    assert REASON_MULTIPLE_COMPANY_NAMES in item.reasons
    assert REASON_LIKELY_REUSE in item.reasons
    assert REASON_LIKELY_RENAME not in item.reasons
    assert item.max_era_gap_days is not None and item.max_era_gap_days >= 365


def test_a_renamed_issuer_is_refused_but_labelled_a_rename_not_a_reuse():
    """The ANTM pattern: continuous coverage, new label, same issuer."""
    events = [
        _Event("ANTM", "2015-01-06", "Anthem Inc"),
        _Event("ANTM", "2022-06-01", "Anthem Inc"),
        _Event("ANTM", "2022-06-22", "Elevance Health Inc"),
    ]
    item = _by_ticker(assess_identities(events))["ANTM"]
    assert item.verdict == VERDICT_AMBIGUITY_EVIDENCE
    assert REASON_LIKELY_RENAME in item.reasons
    assert REASON_LIKELY_REUSE not in item.reasons


def test_one_issuer_under_two_tickers_refuses_both():
    """The FB/META pattern seen from the other side: neither ticker alone
    identifies the issuer, so refusing only one of them is not enough."""
    events = [
        _Event("FB", "2012-05-18", "Meta Platforms Inc"),
        _Event("META", "2022-06-09", "Meta Platforms Inc"),
    ]
    identities = _by_ticker(assess_identities(events))
    for ticker in ("FB", "META"):
        assert identities[ticker].verdict == VERDICT_AMBIGUITY_EVIDENCE
        assert REASON_NAME_SHARED_WITH_OTHER_TICKER in identities[ticker].reasons
    assert identities["FB"].shared_names_with == ("META",)
    assert identities["META"].shared_names_with == ("FB",)


def test_a_clean_single_issuer_ticker_is_not_refused():
    """Guards against a detector that passes by refusing everything."""
    events = [
        _Event("AAPL", "2012-01-03", "Apple Inc"),
        _Event("AAPL", "2020-06-01", "Apple Inc"),
        _Event("AAPL", "2026-08-20", "Apple Inc"),
    ]
    item = _by_ticker(assess_identities(events))["AAPL"]
    assert item.verdict == VERDICT_NO_AMBIGUITY_EVIDENCE
    assert item.reasons == ()
    assert item.max_era_gap_days is None


def test_a_long_coverage_gap_alone_does_not_refuse():
    """Sparse coverage is not an identity hazard. Refusing on silence alone
    would flag thousands of thinly covered names and make the list useless."""
    events = [
        _Event("THIN", "2013-01-02", "Thinly Covered Corp"),
        _Event("THIN", "2020-01-02", "Thinly Covered Corp"),
    ]
    assert _by_ticker(assess_identities(events))["THIN"].verdict == VERDICT_NO_AMBIGUITY_EVIDENCE


# --------------------------------------------------------------------------
# Name comparison: conservative on purpose
# --------------------------------------------------------------------------


def test_case_and_whitespace_differences_are_not_treated_as_two_issuers():
    events = [
        _Event("XYZ", "2020-01-02", "Example  Holdings Inc"),
        _Event("XYZ", "2021-01-02", "EXAMPLE HOLDINGS INC"),
    ]
    assert _by_ticker(assess_identities(events))["XYZ"].verdict == VERDICT_NO_AMBIGUITY_EVIDENCE


def test_punctuation_and_suffix_variants_refuse_rather_than_silently_merge():
    """Aliasing `Inc` to `Inc.` is a security-master decision, not plumbing.

    Under-merging costs a refusal a human can clear; over-merging would fuse
    two issuers invisibly, so the conservative direction is the correct one.
    """
    events = [
        _Event("ABC", "2020-01-02", "Example Inc"),
        _Event("ABC", "2021-01-02", "Example Inc."),
    ]
    item = _by_ticker(assess_identities(events))["ABC"]
    assert item.verdict == VERDICT_AMBIGUITY_EVIDENCE
    assert REASON_MULTIPLE_COMPANY_NAMES in item.reasons


def test_comparison_name_normalizes_only_case_and_whitespace():
    assert comparison_name("  Apple   Inc ") == comparison_name("APPLE INC")
    assert comparison_name("Apple Inc") != comparison_name("Apple Inc.")
    assert comparison_name(None) is None
    assert comparison_name("   ") is None


# --------------------------------------------------------------------------
# Vendor-inconsistency and missing data
# --------------------------------------------------------------------------


def test_interleaved_names_are_flagged_separately_from_a_clean_succession():
    """A,B,A is the vendor alternating labels, not an issuer changing twice."""
    events = [
        _Event("ZZ", "2020-01-02", "First Name Corp"),
        _Event("ZZ", "2020-02-02", "Second Name Corp"),
        _Event("ZZ", "2020-03-02", "First Name Corp"),
    ]
    item = _by_ticker(assess_identities(events))["ZZ"]
    assert REASON_INTERLEAVED_NAMES in item.reasons
    assert len(item.name_eras) == 3
    assert item.distinct_company_names == 2


def test_an_event_without_a_company_name_is_flagged_not_ignored():
    events = [
        _Event("NN", "2020-01-02", "Named Corp"),
        _Event("NN", "2020-02-02", None),
    ]
    item = _by_ticker(assess_identities(events))["NN"]
    assert item.verdict == VERDICT_AMBIGUITY_EVIDENCE
    assert REASON_MISSING_COMPANY_NAME in item.reasons
    assert item.events_without_company_name == 1
    # The unnamed row must not open or extend an era.
    assert len(item.name_eras) == 1
    assert item.name_eras[0].event_count == 1


def test_a_ticker_whose_events_are_all_unnamed_produces_no_era_and_refuses():
    events = [_Event("QQ", "2020-01-02", None), _Event("QQ", "2020-02-02", "")]
    item = _by_ticker(assess_identities(events))["QQ"]
    assert item.name_eras == ()
    assert item.distinct_company_names == 0
    assert item.verdict == VERDICT_AMBIGUITY_EVIDENCE


# --------------------------------------------------------------------------
# Contract behaviour
# --------------------------------------------------------------------------


def test_eras_are_built_in_date_order_regardless_of_input_order():
    forward = [
        _Event("OD", "2020-01-02", "Old Name Corp"),
        _Event("OD", "2024-01-02", "New Name Corp"),
    ]
    item_forward = _by_ticker(assess_identities(forward))["OD"]
    item_backward = _by_ticker(assess_identities(list(reversed(forward))))["OD"]
    assert item_forward == item_backward
    assert item_forward.name_eras[0].company_name == "Old Name Corp"


def test_same_day_vendor_row_order_cannot_change_identity_evidence():
    """Vendor ids do not establish an order among actions on the same day."""
    first = [
        _Event("SAME", "2024-01-02", "Alpha Corp"),
        _Event("SAME", "2024-01-02", "Beta Corp"),
        _Event("SAME", "2024-01-02", "Alpha Corp"),
    ]
    second = [first[0], first[2], first[1]]
    assert assess_identities(first) == assess_identities(second)


def test_ticker_case_is_not_allowed_to_split_one_symbol_into_two_identities():
    events = [
        _Event("case", "2020-01-02", "First Issuer"),
        _Event("CASE", "2026-01-02", "Second Issuer"),
    ]
    identities = assess_identities(events)
    assert len(identities) == 1
    assert identities[0].ticker == "CASE"
    assert identities[0].verdict == VERDICT_AMBIGUITY_EVIDENCE


def test_output_is_sorted_by_ticker_for_deterministic_reports():
    events = [
        _Event("ZED", "2020-01-02", "Zed Corp"),
        _Event("ACME", "2020-01-02", "Acme Corp"),
        _Event("MID", "2020-01-02", "Mid Corp"),
    ]
    assert [item.ticker for item in assess_identities(events)] == ["ACME", "MID", "ZED"]


def test_identities_are_frozen_against_mutation():
    item = assess_identities([_Event("AA", "2020-01-02", "A Corp")])[0]
    with pytest.raises(Exception):
        item.verdict = VERDICT_AMBIGUITY_EVIDENCE  # type: ignore[misc]


def test_the_diagnostic_flag_set_is_exactly_the_evidence_flagged_tickers():
    events = [
        _Event("GOOD", "2020-01-02", "Good Corp"),
        _Event("BAD", "2020-01-02", "One Corp"),
        _Event("BAD", "2026-01-02", "Two Corp"),
    ]
    identities = assess_identities(events)
    assert diagnostic_flagged_tickers(identities) == ("BAD",)


def test_summary_reports_event_share_not_just_ticker_counts():
    """A handful of ambiguous tickers can carry a large share of events, so
    the ticker count alone understates the exposure."""
    events = [_Event("BIG", f"2020-01-{d:02d}", "One Corp") for d in range(1, 10)]
    events.append(_Event("BIG", "2026-01-02", "Two Corp"))
    events.append(_Event("SMALL", "2020-01-02", "Small Corp"))
    report = summarize_identities(assess_identities(events))
    assert report["tickers"] == 2
    assert report["tickers_with_name_based_ambiguity_evidence"] == 1
    assert report["events_under_name_flagged_tickers"] == 10
    assert report["share_of_events_flagged_by_name_evidence"] == pytest.approx(10 / 11)


def test_summary_of_an_empty_corpus_does_not_divide_by_zero():
    assert summarize_identities([])["share_of_events_flagged_by_name_evidence"] == 0.0


def test_a_reuse_the_vendor_never_relabels_is_NOT_detected():
    """The detector's known blind spot, pinned so it cannot be forgotten.

    Measured on Snapshot A: BBBY carries the single company name
    'Bed Bath & Beyond' across all 270 events, from 2012 through 2026 —
    including events after the retailer's 2023 bankruptcy, when the symbol
    was reused by an unrelated issuer. The vendor never relabels, so no
    name-based signal exists and this detector finds *no name-based evidence*.

    That is a false negative on the exact case that motivated the work. It is
    asserted here rather than described in prose so that a future change
    which accidentally 'fixes' it by over-refusing, or a future claim that
    name evidence is sufficient, both collide with a test. Resolving this
    class needs an external security master with delisting dates
    (open item ACER-0A.10), not a better name heuristic.
    """
    events = [
        _Event("BBBY", "2012-03-20", "Bed Bath & Beyond"),
        _Event("BBBY", "2023-04-27", "Bed Bath & Beyond"),
        _Event("BBBY", "2026-06-23", "Bed Bath & Beyond"),
    ]
    item = _by_ticker(assess_identities(events))["BBBY"]
    assert item.verdict == VERDICT_NO_AMBIGUITY_EVIDENCE
    assert item.reasons == ()


def test_absence_of_name_evidence_is_never_labelled_proof_of_unambiguity():
    """A known false negative must not acquire a safety-shaped label."""
    identities = assess_identities(
        [
            _Event("BBBY", "2012-03-20", "Bed Bath & Beyond"),
            _Event("BBBY", "2026-06-23", "Bed Bath & Beyond"),
        ]
    )
    report = summarize_identities(identities)
    assert identities[0].verdict != "unambiguous"
    assert "unambiguous_tickers" not in report


def test_diagnostic_report_binds_source_dataset_code_and_assessment_content():
    identities = assess_identities([_Event("AAPL", "2024-01-02", "Apple Inc")])
    dataset_identity = _validated_dataset_identity(1)
    report = build_diagnostic_report(
        identities,
        code_commit="a" * 40,
        normalized_dataset_identity=dataset_identity,
    )
    assert report["code_commit"] == "a" * 40
    assert report["normalized_dataset_id"] == dataset_identity.dataset_id
    assert report["source_manifest_sha256"] == "b" * 64
    assert report["normalized_content_hash"] == dataset_identity.content_hash
    assert report["normalized_events_sha256"] == dataset_identity.events_sha256
    assert report["normalized_refusals_sha256"] == dataset_identity.refusals_sha256
    assert len(report["identity_assessments_sha256"]) == 64
    assert "not established as unambiguous" in report["warning"]


def test_diagnostic_report_refuses_lineage_that_does_not_cover_all_events():
    identities = assess_identities([_Event("AAPL", "2024-01-02", "Apple Inc")])
    with pytest.raises(ValueError, match="does not cover"):
        build_diagnostic_report(
            identities,
            code_commit="a" * 40,
            normalized_dataset_identity=_validated_dataset_identity(2),
        )


@pytest.mark.parametrize(
    "forged",
    [
        {"dataset_id": "acer-analyst-events-deadbeefdeadbeef"},
        {"dataset_id": "acer-analyst-events-deadbeefdeadbeef", "event_count": 1},
        {
            "dataset_id": "acer-analyst-events-deadbeefdeadbeef",
            "content_hash": "f" * 64,
            "event_count": 1,
        },
    ],
)
def test_diagnostic_report_refuses_dataset_shaped_dictionaries(forged):
    identities = assess_identities([_Event("AAPL", "2024-01-02", "Apple Inc")])
    with pytest.raises(ValueError, match="strict typed loader"):
        build_diagnostic_report(
            identities,
            code_commit="a" * 40,
            normalized_dataset_identity=forged,
        )


def test_the_detector_consumes_normalized_events_directly():
    """It must work on the real contract, not only the test stand-in."""
    rows = [
        {
            "benzinga_id": "1",
            "date": "2024-03-14",
            "time": "14:30:00",
            "last_updated": "2024-03-14T18:31:00Z",
            "ticker": "AAPL",
            "company_name": "Apple Inc",
            "firm": "Example Securities",
            "rating": "Buy",
        }
    ]
    events, _ = normalize_rows(rows)
    item = assess_identities(events)[0]
    assert item.ticker == "AAPL"
    assert item.verdict == VERDICT_NO_AMBIGUITY_EVIDENCE
