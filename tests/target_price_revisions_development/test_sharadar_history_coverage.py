"""Synthetic access aggregates; no provider, private row, account or QC reads."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest

from research.target_price_revisions_development import sharadar_history_coverage as coverage


def sample(day="2020-09-01", *, count=0, table="DAILY", cohort=0, style="operators"):
    return {"kind": "table_rows", "table": table, "filter_style": style, "cohort": cohort,
        "request_start": day, "request_end": day, "row_count": count,
        "observed_start": day if count else None, "observed_end": day if count else None,
        "http_status": 200}


def gate(years=5, status=302, table="DAILY"):
    return {"kind": "bulk_gate", "table": table, "history_years": years,
        "http_status": status, "no_follow": True,
        "gate_status": {302: "redirect", 403: "forbidden"}.get(status, "not_observed")}


def contrast():
    return [sample(style="from_to"), sample(), sample("2021-10-22"),
        sample("2021-10-25", count=1), sample("2022-01-03", count=1),
        sample("2026-10-09", count=1, cohort=1), gate(), gate(10, 403), gate("full", 403)]


def diagnose(observations=None, **kwargs):
    return coverage.diagnose_sharadar_history(contrast() if observations is None else observations,
        as_of_date=kwargs.pop("as_of_date", "2026-10-24"),
        required_start=kwargs.pop("required_start", "2020-09-01"),
        required_end=kwargs.pop("required_end", "2026-10-09"), **kwargs)


def test_paired_boundary_and_bulk_pattern_is_not_account_or_coverage_attestation():
    result = diagnose()
    assert result.effective_history_restriction == "five_year_restriction_pattern_observed"
    assert result.restriction_evidence == ("DAILY:dated_boundary_and_bulk_gate_contrast",)
    assert result.account_subscription == "invoiced_tier_unverified"
    assert result.next_action == "confirm_or_repair_existing_entitlement_before_purchase"
    assert result.smallest_history_option_if_change_required == "ten_years_cover_requested_start"
    assert result.sampled_requested_history == ("DAILY",)
    assert result.empty_historical_samples == ("DAILY",)
    assert all(value is False for key, value in asdict(result).items() if key.endswith(
        ("_proved", "_ready", "_followed", "_verified")))


@pytest.mark.parametrize("observations", [
    [sample(), sample("2021-01-04")],
    [gate()], [gate(), gate(10, 403)],
    [sample(), sample("2022-01-03", count=1)],
    [sample(), sample("2022-01-03", count=1), gate()],
    [sample(), sample("2022-01-03", count=1), gate(10, 403)],
    [{"kind": "bulk_metadata", "table": "DAILY", "available": True, "http_status": 200}],
])
def test_partial_evidence_never_infers_a_five_year_restriction(observations):
    result = diagnose(observations)
    assert result.effective_history_restriction == "inconclusive"
    assert result.restriction_evidence == ()
    assert result.account_subscription == "invoiced_tier_unverified"
    assert not result.full_requested_coverage_proved


@pytest.mark.parametrize("change", [
    lambda rows: rows[1].update(cohort=3),
    lambda rows: [row.update(table="ACTIONS") for row in rows if row["kind"] == "bulk_gate"],
    lambda rows: rows[0].update(http_status=403),
])
def test_cross_cohort_table_or_failed_empty_cannot_make_boundary_claim(change):
    rows = [sample("2021-10-22"), sample("2021-10-25", count=1),
            gate(), gate(10, 403)]
    change(rows)
    assert diagnose(rows).effective_history_restriction == "inconclusive"


def test_positive_older_access_contradicts_the_table_wide_five_year_pattern():
    result = diagnose(contrast() + [sample("2020-09-02", count=1, cohort=2)])
    assert result.effective_history_restriction == "inconclusive"
    assert result.restriction_evidence == ()


@pytest.mark.parametrize("extra", [gate(10), gate("full"), gate(10, 429), gate(5, 403)])
def test_conflicting_or_unresolved_gate_observations_never_assert_current_restriction(extra):
    result = diagnose(contrast() + [extra])
    assert result.effective_history_restriction == "inconclusive"
    assert result.restriction_evidence == ()
    assert not result.real_backtest_ready


def test_current_master_and_advertised_availability_are_not_historical_access():
    current = {"kind": "table_rows", "table": "TICKERS", "filter_style": "none",
        "cohort": 0, "request_start": None, "request_end": None,
        "observed_start": None, "observed_end": None, "row_count": 1, "http_status": 200}
    result = diagnose([current, {"kind": "bulk_metadata", "table": "DAILY",
        "available": True, "http_status": 200}])
    assert result.sampled_table_access == ("TICKERS",)
    assert result.sampled_requested_history == ()
    assert result.metadata_available == ("DAILY",)
    assert result.effective_history_restriction == "inconclusive"


def test_unknown_metadata_field_is_rejected_below_the_container_size_limit():
    metadata = {"kind": "bulk_metadata", "table": "DAILY", "available": True,
                "http_status": 200, "private_detail": "synthetic-secret"}
    with pytest.raises(coverage.HistoryCoverageError) as caught:
        diagnose([metadata])
    assert "synthetic-secret" not in str(caught.value)


@pytest.mark.parametrize("edit", [
    lambda row: row.update(extra="secret"), lambda row: row.update(url="https://example.invalid"),
    lambda row: row.update(rows=[]), lambda row: row.update(row_count=True),
    lambda row: row.update(row_count=-1), lambda row: row.update(row_count=129),
    lambda row: row.update(cohort=True), lambda row: row.update(cohort=4),
    lambda row: row.update(http_status=True), lambda row: row.update(http_status=302),
    lambda row: row.update(filter_style="unknown"), lambda row: row.update(table="unknown"),
    lambda row: row.update(kind=[[]]), lambda row: row.update(observed_start="2020-09-01"),
    lambda row: row.update(request_start="20200901"), lambda row: row.update(request_start="2020-9-01"),
    lambda row: row.update(request_end="2020-08-31"), lambda row: row.update(request_end="2026-10-25"),
    lambda row: row.update(row_count=1), lambda row: row.pop("observed_end"),
])
def test_malformed_or_extra_fields_refuse_without_repeating_input(edit):
    row = sample()
    edit(row)
    with pytest.raises(coverage.HistoryCoverageError) as caught:
        diagnose([row])
    assert "secret" not in str(caught.value) and "https" not in str(caught.value)


@pytest.mark.parametrize("edit", [
    lambda row: row.update(observed_start="2020-08-31"),
    lambda row: row.update(observed_end="2020-09-02"),
    lambda row: row.update(http_status=403),
])
def test_rows_outside_exact_request_or_unsuccessful_status_refuse(edit):
    row = sample(count=1)
    edit(row)
    with pytest.raises(coverage.HistoryCoverageError):
        diagnose([row])


@pytest.mark.parametrize("edit", [
    lambda row: row.update(no_follow=False), lambda row: row.update(no_follow=1),
    lambda row: row.update(history_years=True), lambda row: row.update(history_years="5"),
    lambda row: row.update(history_years=20), lambda row: row.update(http_status=True),
    lambda row: row.update(gate_status="forbidden"), lambda row: row.update(location="secret"),
])
def test_bulk_claims_are_bounded_and_downloads_are_refused(edit):
    row = gate()
    edit(row)
    with pytest.raises(coverage.HistoryCoverageError):
        diagnose([row])


@pytest.mark.parametrize("observations", [None, {}, [], [sample()] * 65, [[sample()]],
    [{"kind": "table_rows", 1: "bad"}],
    [{"kind": "bulk_metadata", "table": "DAILY", "available": 1, "http_status": 200}],
])
def test_input_size_types_and_depth_are_closed(observations):
    with pytest.raises(coverage.HistoryCoverageError):
        coverage.diagnose_sharadar_history(observations, as_of_date="2026-10-24",
            required_start="2020-09-01", required_end="2026-10-09")


@pytest.mark.parametrize("start, expected", [
    ("2021-10-24", "five_years_may_cover_requested_start"),
    ("2021-10-23", "ten_years_cover_requested_start"),
    ("2016-10-24", "ten_years_cover_requested_start"),
    ("2016-10-23", "more_than_ten_years_required_for_requested_start"),
])
def test_history_option_is_conditional_on_requested_window_not_purchase_authority(start, expected):
    result = diagnose([sample()], required_start=start)
    assert result.smallest_history_option_if_change_required == expected
    assert result.next_action == "confirm_or_repair_existing_entitlement_before_purchase"


@pytest.mark.parametrize("kwargs", [
    {"as_of_date": True}, {"as_of_date": "2026-02-30"},
    {"required_start": "1899-12-31"}, {"required_start": "2026-10-10"},
    {"required_end": "2026-10-25"}, {"required_start": "2020-09-01T00:00:00Z"},
])
def test_study_window_cannot_be_reversed_future_noncanonical_or_unbounded(kwargs):
    with pytest.raises(coverage.HistoryCoverageError):
        diagnose([sample()], **kwargs)


def test_leap_day_boundary_is_explicit_and_report_is_immutable_and_detached():
    rows = [sample("2021-02-27"), sample("2021-02-28", count=1), gate(), gate(10, 403)]
    result = diagnose(rows, as_of_date="2026-02-28", required_end="2026-02-28")
    assert result.effective_history_restriction == "five_year_restriction_pattern_observed"
    rows[0]["row_count"] = 100
    assert result.empty_historical_samples == ("DAILY",)
    with pytest.raises(FrozenInstanceError):
        result.real_backtest_ready = True
    leap = diagnose([sample()], as_of_date="2024-02-29", required_start="2019-02-28",
                    required_end="2024-02-28")
    assert leap.smallest_history_option_if_change_required == "five_years_may_cover_requested_start"
    before_leap = diagnose([sample()], as_of_date="2024-02-29", required_start="2019-02-27",
                           required_end="2024-02-28")
    assert before_leap.smallest_history_option_if_change_required == "ten_years_cover_requested_start"


def test_samples_outside_study_window_are_access_not_requested_history():
    result = diagnose([sample("2020-08-31", count=1)])
    assert result.sampled_table_access == ("DAILY",)
    assert result.sampled_requested_history == ()


def test_output_is_deterministic_bounded_and_does_not_retain_observations():
    rows = contrast()
    assert diagnose(rows) == diagnose(list(reversed(rows)))
    assert all(type(value) in (str, tuple, bool) for value in asdict(diagnose(rows)).values())
    assert len(str(asdict(diagnose(rows)))) < 2048
