"""Synthetic-only resource arithmetic for the prospective 82-quarter corpus."""

from dataclasses import replace
import hashlib

import pytest

from research.insider_buying.sec_corpus_scale_preflight import (
    SecCorpusScalePreflightError,
    SecQuarterScaleDescriptor,
    build_sec_corpus_scale_preflight,
)


PERIODS = tuple(
    f"{year}Q{quarter}"
    for year in range(2006, 2027)
    for quarter in range(1, 5)
    if (year, quarter) <= (2026, 2)
)


def _descriptors() -> tuple[SecQuarterScaleDescriptor, ...]:
    return tuple(
        SecQuarterScaleDescriptor(
            period=period,
            zip_sha256=hashlib.sha256(period.encode()).hexdigest(),
            zip_size_bytes=1_048_576,
            submission_accession_count=100,
            form4_accession_count=70,
            form4a_accession_count=3,
            multi_owner_target_count=2,
        )
        for period in PERIODS
    )


def test_exact_82_quarter_arithmetic_is_only_a_noncanonical_planning_cap() -> None:
    result = build_sec_corpus_scale_preflight(_descriptors())
    assert len(result.quarters) == 82
    assert result.quarters[0].period == "2006Q1"
    assert result.quarters[-1].period == "2026Q2"
    assert result.existing_zip_bytes == 82 * 1_048_576
    assert result.declared_submission_accessions == 8_200
    assert result.declared_form4_accessions == 82 * 70
    assert result.declared_form4a_accessions == 82 * 3
    assert result.declared_target_accessions == 82 * 73
    assert result.declared_multi_owner_targets == 82 * 2
    assert result.multi_owner_unknown_quarters == 0
    assert result.planned_distinct_artifacts_without_cache == 82 + 82 * 73
    assert result.maximum_attempts_at_three_per_artifact == 3 * (82 + 82 * 73)
    assert result.ideal_minimum_dispatch_span_ms == (82 + 82 * 73 - 1) * 500
    assert result.successful_raw_parent_cap_bytes == (82 + 82 * 73) * 8_388_608
    assert result.existing_zip_plus_successful_parent_cap_bytes == (
        82 * 1_048_576 + (82 + 82 * 73) * 8_388_608
    )
    payload = result.to_payload()
    assert payload["scope"] == "caller_declared_unverified_82_quarter_plan"
    assert payload["assumptions"] == {
        "master_gzip_per_quarter": 1,
        "complete_submission_per_form4_or_4a": 1,
        "internal_request_starts_per_second": 2,
        "maximum_attempts_per_artifact": 3,
        "successful_raw_parent_cap_bytes_per_artifact": 8_388_608,
    }
    assert payload["authority"] == {
        "zip_bytes_verified": False,
        "accession_counts_verified": False,
        "master_index_membership_verified": False,
        "source_authenticated": False,
        "canonical_evidence": False,
        "point_in_time_data": False,
        "outcome_access_authorized": False,
        "qc_job_authorized": False,
        "broker_or_trading_authorized": False,
        "research_looks": 0,
        "authorized_outcome_looks": 0,
        "consumed_outcome_looks": 0,
    }
    assert "forecast" not in payload["resource_arithmetic"]


@pytest.mark.parametrize("mutation", [
    lambda rows: rows[1:],
    lambda rows: rows + (rows[-1],),
    lambda rows: (rows[1], rows[0]) + rows[2:],
    lambda rows: rows[:17] + (rows[16],) + rows[18:],
    lambda rows: (replace(rows[0], period="2005Q4"),) + rows[1:],
    lambda rows: rows[:-1] + (replace(rows[-1], period="2026Q3"),),
])
def test_missing_extra_reordered_duplicate_and_outside_quarters_refuse(mutation) -> None:
    with pytest.raises(SecCorpusScalePreflightError, match="REFUSED:.*82.*quarter"):
        build_sec_corpus_scale_preflight(mutation(_descriptors()))


@pytest.mark.parametrize("field,value", [
    ("zip_sha256", "not-a-hash"),
    ("zip_size_bytes", 0),
    ("zip_size_bytes", 512 * 1024 * 1024 + 1),
    ("zip_size_bytes", True),
    ("submission_accession_count", -1),
    ("submission_accession_count", True),
    ("submission_accession_count", 5_000_001),
    ("form4_accession_count", 101),
    ("form4a_accession_count", -1),
    ("multi_owner_target_count", 74),
])
def test_invalid_descriptor_or_incoherent_counts_refuse(field: str, value: object) -> None:
    original = _descriptors()[0]
    with pytest.raises(SecCorpusScalePreflightError, match="REFUSED"):
        replace(original, **{field: value})


def test_unknown_multi_owner_counts_are_not_silently_zero() -> None:
    rows = _descriptors()
    rows = (replace(rows[0], multi_owner_target_count=None),) + rows[1:]
    result = build_sec_corpus_scale_preflight(rows)
    assert result.multi_owner_unknown_quarters == 1
    assert result.declared_multi_owner_targets is None


def test_one_pass_iterable_and_caller_mutation_do_not_change_report() -> None:
    rows = list(_descriptors())
    report = build_sec_corpus_scale_preflight(iter(rows))
    original_payload = report.to_payload()
    object.__setattr__(rows[0], "form4_accession_count", 101)
    assert report.to_payload() == original_payload
    with pytest.raises(SecCorpusScalePreflightError, match="REFUSED"):
        build_sec_corpus_scale_preflight(iter(rows))


def test_reject_non_exact_descriptor_and_non_iterable() -> None:
    rows = _descriptors()
    with pytest.raises(SecCorpusScalePreflightError, match="REFUSED"):
        build_sec_corpus_scale_preflight(0)
    with pytest.raises(SecCorpusScalePreflightError, match="REFUSED"):
        build_sec_corpus_scale_preflight((object(),) + rows[1:])
