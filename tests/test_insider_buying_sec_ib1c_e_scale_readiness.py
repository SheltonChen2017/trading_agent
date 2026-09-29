"""Synthetic-only guards for the 82-quarter IB-1C..IB-1E scale boundary."""
from __future__ import annotations

from dataclasses import replace

import pytest

from research.insider_buying import sec_ib1c_e_scale_readiness as readiness_module
from research.insider_buying.sec_ib1c_e_scale_readiness import (
    EXPECTED_PERIODS,
    LEGACY_IB1E_MAX_PERIODS,
    LEGACY_IB1E_MAX_XML_SOURCES,
    DeclaredIb1ceFiling,
    DeclaredIb1ceQuarter,
    SecIb1cEScaleReadinessError,
    append_declared_ib1ce_quarter,
    assess_declared_ib1ce_scale_readiness,
)


SHA = "a" * 64


def _accession(index: int) -> str:
    year = EXPECTED_PERIODS[index][:4]
    return f"0000000001-{int(year) % 100:02d}-{index + 1:06d}"


def _acceptance(index: int) -> str:
    year = EXPECTED_PERIODS[index][:4]
    month = 1 + 3 * (int(EXPECTED_PERIODS[index][-1]) - 1)
    return f"{year}-{month:02d}-03T10:00:00+00:00"


def _filing(index: int, **updates: object) -> DeclaredIb1ceFiling:
    values = {
        "accession_number": _accession(index),
        "form_type": "4",
        "issuer_cik": "0000000001",
        "reporting_owner_ciks": ("0000000002",),
        "accepted_at_utc": _acceptance(index),
        "complete_parent_sha256": SHA,
        "complete_xml_sha256": SHA,
        "acceptance_metadata_sha256": SHA,
        "asserted_original_accession": None,
    }
    values.update(updates)
    return DeclaredIb1ceFiling(**values)


def _quarter(index: int, filings: tuple[DeclaredIb1ceFiling, ...] | None = None) -> DeclaredIb1ceQuarter:
    return DeclaredIb1ceQuarter(
        period=EXPECTED_PERIODS[index],
        parsed_ib1b_sha256=SHA,
        filings=(_filing(index),) if filings is None else filings,
    )


def test_exact_82_quarter_append_preserves_every_as_filed_row_but_never_promotes() -> None:
    checkpoint = None
    for index in range(len(EXPECTED_PERIODS)):
        checkpoint = append_declared_ib1ce_quarter(checkpoint, _quarter(index))
    assert checkpoint is not None
    assert len(checkpoint.quarters) == 82
    assert tuple(
        row.accession_number for quarter in checkpoint.quarters for row in quarter.filings
    ) == tuple(_accession(index) for index in range(82))
    report = assess_declared_ib1ce_scale_readiness(checkpoint)
    payload = report.to_payload()
    assert report.filing_count == 82
    assert len(report.quarter_sha256s) == 82
    assert report.unresolved_link_count == 0
    assert report.multi_owner_filing_count == 0
    assert report.missing_owner_identity_count == 0
    assert payload["legacy_ib1e_max_periods"] == LEGACY_IB1E_MAX_PERIODS == 16
    assert payload["legacy_ib1e_max_xml_sources"] == LEGACY_IB1E_MAX_XML_SOURCES == 256
    assert "legacy_ib1e_16_period_cap_requires_streaming_successor" in report.blockers
    for field in (
        "official_sec_source_authenticated",
        "complete_amendment_coverage_verified",
        "official_pit_security_master_verified",
        "trading_calendar_session_mapping_verified",
        "canonical_filter_authorized",
        "point_in_time_mapping_verified",
        "signal_authorized",
        "backtest_ready",
    ):
        assert payload[field] is False
    assert checkpoint.canonical_filter_authorized is False
    assert checkpoint.point_in_time_mapping_verified is False
    assert checkpoint.signal_authorized is False
    assert checkpoint.backtest_ready is False


def test_missing_exact_evidence_and_unlinked_amendment_are_retained_but_unavailable() -> None:
    amendment = _filing(
        1,
        form_type="4/A",
        accepted_at_utc=None,
        complete_parent_sha256=None,
        complete_xml_sha256=None,
        acceptance_metadata_sha256=None,
    )
    checkpoint = None
    for index in range(82):
        checkpoint = append_declared_ib1ce_quarter(
            checkpoint, _quarter(index, (amendment,) if index == 1 else None)
        )
    report = assess_declared_ib1ce_scale_readiness(checkpoint)
    assert report.amendment_count == 1
    assert report.unresolved_link_count == 1
    assert report.missing_exact_acceptance_count == 1
    assert report.missing_parent_count == 1
    assert report.missing_xml_count == 1
    assert report.missing_metadata_count == 1
    assert "amendment_links_unresolved" in report.blockers
    assert "exact_acceptance_timestamps_missing" in report.blockers
    assert "complete_parent_declarations_missing" in report.blockers
    assert report.backtest_ready is False
    assert checkpoint.quarters[1].filings == (amendment,)


def test_multi_owner_as_filed_tuple_is_retained_without_attribution_or_pit_promotion() -> None:
    owners = ("0000000002", "0000000003")
    checkpoint = None
    for index in range(82):
        filing = _filing(index, reporting_owner_ciks=owners) if index == 0 else _filing(index)
        checkpoint = append_declared_ib1ce_quarter(checkpoint, _quarter(index, (filing,)))
    assert checkpoint.quarters[0].filings[0].reporting_owner_ciks == owners
    report = assess_declared_ib1ce_scale_readiness(checkpoint)
    assert report.multi_owner_filing_count == 1
    assert "real_multi_owner_header_profile_unverified" in report.blockers
    assert report.canonical_filter_authorized is False
    assert report.point_in_time_mapping_verified is False


def test_omitted_reordered_repeated_and_extra_periods_refuse() -> None:
    with pytest.raises(SecIb1cEScaleReadinessError, match="missing, repeated or reordered"):
        append_declared_ib1ce_quarter(None, _quarter(1))
    checkpoint = append_declared_ib1ce_quarter(None, _quarter(0))
    with pytest.raises(SecIb1cEScaleReadinessError, match="missing, repeated or reordered"):
        append_declared_ib1ce_quarter(checkpoint, _quarter(0))
    with pytest.raises(SecIb1cEScaleReadinessError, match="all 82 quarters"):
        assess_declared_ib1ce_scale_readiness(checkpoint)
    for index in range(1, 82):
        checkpoint = append_declared_ib1ce_quarter(checkpoint, _quarter(index))
    with pytest.raises(SecIb1cEScaleReadinessError, match="missing, repeated or reordered"):
        append_declared_ib1ce_quarter(checkpoint, _quarter(81))


def test_duplicate_accession_across_quarters_refuses() -> None:
    checkpoint = append_declared_ib1ce_quarter(None, _quarter(0))
    repeated = _filing(1, accession_number=_accession(0))
    with pytest.raises(SecIb1cEScaleReadinessError, match="duplicate accession"):
        append_declared_ib1ce_quarter(checkpoint, _quarter(1, (repeated,)))


@pytest.mark.parametrize(
    "amendment_update, reason",
    [
        ({"issuer_cik": "0000000002"}, "crosses issuers"),
        ({"accepted_at_utc": "2006-01-03T10:00:00+00:00"}, "does not follow original"),
    ],
)
def test_contradictory_known_original_links_refuse(amendment_update: dict[str, object], reason: str) -> None:
    checkpoint = append_declared_ib1ce_quarter(None, _quarter(0))
    amendment = _filing(
        1, form_type="4/A", asserted_original_accession=_accession(0), **amendment_update
    )
    with pytest.raises(SecIb1cEScaleReadinessError, match=reason):
        append_declared_ib1ce_quarter(checkpoint, _quarter(1, (amendment,)))


def test_link_to_an_amendment_or_later_original_refuses() -> None:
    first_amendment = _filing(0, form_type="4/A")
    checkpoint = append_declared_ib1ce_quarter(None, _quarter(0, (first_amendment,)))
    second_amendment = _filing(1, form_type="4/A", asserted_original_accession=_accession(0))
    with pytest.raises(SecIb1cEScaleReadinessError, match="earlier original"):
        append_declared_ib1ce_quarter(checkpoint, _quarter(1, (second_amendment,)))

    later_accession = _accession(1)
    first_amendment = _filing(0, form_type="4/A", asserted_original_accession=later_accession)
    checkpoint = append_declared_ib1ce_quarter(None, _quarter(0, (first_amendment,)))
    with pytest.raises(SecIb1cEScaleReadinessError, match="earlier original"):
        append_declared_ib1ce_quarter(checkpoint, _quarter(1))


@pytest.mark.parametrize(
    "filing_update, reason",
    [
        ({"form_type": "5"}, "only Form 4/4-A"),
        ({"form_type": []}, "only Form 4/4-A"),
        ({"issuer_cik": "0000000000"}, "issuer CIK"),
        ({"reporting_owner_ciks": ("0000000002", "0000000002")}, "reporting-owner CIKs"),
        ({"reporting_owner_ciks": ["0000000002"]}, "reporting-owner CIKs"),
        ({"accepted_at_utc": "2006-01-03T10:00:00"}, "exact second-resolution UTC"),
        ({"accepted_at_utc": "2006-02-30T10:00:00+00:00"}, "invalid"),
        ({"complete_xml_sha256": "A" * 64}, "complete XML"),
        ({"complete_parent_sha256": "A" * 64}, "complete parent"),
        ({"asserted_original_accession": _accession(1)}, "original Form 4"),
    ],
)
def test_malformed_filing_declarations_refuse(filing_update: dict[str, object], reason: str) -> None:
    with pytest.raises(SecIb1cEScaleReadinessError, match=reason):
        _filing(0, **filing_update)


def test_quarter_requires_sorted_unique_accessions_and_matching_year() -> None:
    first = _filing(0)
    another = _filing(0, accession_number="0000000001-06-000002")
    with pytest.raises(SecIb1cEScaleReadinessError, match="repeat or are unordered"):
        _quarter(0, (another, first))
    with pytest.raises(SecIb1cEScaleReadinessError, match="repeat or are unordered"):
        _quarter(0, (first, first))
    with pytest.raises(SecIb1cEScaleReadinessError, match="accession year"):
        _quarter(0, (_filing(0, accession_number="0000000001-07-000001"),))


def test_checkpoint_lineage_tamper_refuses() -> None:
    checkpoint = append_declared_ib1ce_quarter(None, _quarter(0))
    with pytest.raises(SecIb1cEScaleReadinessError, match="lineage hash changed"):
        append_declared_ib1ce_quarter(
            replace(checkpoint, chain_sha256="b" * 64), _quarter(1)
        )


def test_mutated_prior_quarter_rows_cannot_retain_checkpoint_lineage() -> None:
    first = _quarter(0)
    checkpoint = append_declared_ib1ce_quarter(None, first)
    object.__setattr__(first, "filings", ())
    with pytest.raises(SecIb1cEScaleReadinessError, match="quarter lineage hash changed"):
        append_declared_ib1ce_quarter(checkpoint, _quarter(1))


def test_quarter_and_total_filing_caps_refuse_before_composition(monkeypatch) -> None:
    monkeypatch.setattr(readiness_module, "MAX_QUARTER_FILINGS", 0)
    with pytest.raises(SecIb1cEScaleReadinessError, match="quarter filings"):
        _quarter(0)
    monkeypatch.setattr(readiness_module, "MAX_QUARTER_FILINGS", 500_000)
    monkeypatch.setattr(readiness_module, "MAX_TOTAL_FILINGS", 1)
    checkpoint = append_declared_ib1ce_quarter(None, _quarter(0))
    with pytest.raises(SecIb1cEScaleReadinessError, match="total filing cap"):
        append_declared_ib1ce_quarter(checkpoint, _quarter(1))
