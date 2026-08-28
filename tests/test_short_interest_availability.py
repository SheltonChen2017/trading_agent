"""Dangerous-direction tests for release-time and next-open cohorting."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from research.short_interest_etf.availability import (
    release_execution_cohort,
    snapshot_execution_cohort,
)
from research.short_interest_etf.contracts import (
    ReleasePrecision,
    ShortInterestContractError,
)
from research.short_interest_etf.dataset import (
    ShortInterestDatasetError,
    delta_eligible_snapshots_as_of,
    load_synthetic_fixture,
    visible_source_snapshots_as_of,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "short_interest_etf"
    / "official_style_v1.json"
)


def _vintage():
    return load_synthetic_fixture(FIXTURE)


def test_exact_after_close_release_enters_only_the_next_open_cohort():
    release = _vintage().release_calendar[0]
    cohort = release_execution_cohort(release)
    assert release.settlement_date == "2024-01-12"
    assert release.public_release_date == "2024-01-25"
    assert cohort.session == "2024-01-26"
    assert cohort.opens_at == "2024-01-26T14:30:00Z"


def test_exact_preopen_release_can_use_that_days_later_open():
    release = replace(
        _vintage().release_calendar[0],
        public_release_at="2024-01-25T13:00:00Z",
        observed_at="2024-01-25T13:01:00Z",
    )
    assert release_execution_cohort(release).session == "2024-01-25"


def test_exact_preopen_release_on_settlement_day_is_refused():
    with pytest.raises(ShortInterestContractError, match="strictly follow"):
        replace(
            _vintage().release_calendar[0],
            public_release_date="2024-01-12",
            public_release_at="2024-01-12T13:00:00Z",
            filing_deadline_date="2024-01-12",
            observed_at="2024-01-12T13:01:00Z",
        )


@pytest.mark.parametrize(
    "published_at",
    ["2024-01-25T14:30:00Z", "2024-01-25T15:00:00Z"],
)
def test_release_at_or_after_open_cannot_trade_that_open(published_at):
    release = replace(
        _vintage().release_calendar[0],
        public_release_at=published_at,
        observed_at="2024-01-25T22:00:00Z",
    )
    assert release_execution_cohort(release).session == "2024-01-26"


def test_date_only_release_uses_next_regular_session_not_same_day_midnight():
    release = _vintage().release_calendar[1]
    assert release.precision is ReleasePrecision.DATE_ONLY
    cohort = release_execution_cohort(release)
    assert cohort.session == "2024-02-13"
    assert cohort.opens_at == "2024-02-13T14:30:00Z"


def test_date_only_release_skips_market_holiday():
    release = replace(
        _vintage().release_calendar[0],
        public_release_date="2024-07-03",
        public_release_at=None,
        precision=ReleasePrecision.DATE_ONLY,
        observed_at="2024-07-03T22:00:00Z",
    )
    assert release_execution_cohort(release).session == "2024-07-05"


def test_later_input_availability_defers_the_whole_snapshot():
    vintage = _vintage()
    snapshot = vintage.snapshots[0]
    delayed_denominator = replace(
        snapshot.denominator,
        available_at="2024-01-26T15:00:00Z",
        observed_at="2024-01-26T15:00:00Z",
    )
    delayed = replace(
        snapshot,
        denominator=delayed_denominator,
        observed_at="2024-01-26T15:00:00Z",
    )
    cohort = snapshot_execution_cohort(delayed, vintage.release_calendar[0])
    assert cohort.session == "2024-01-29"


def test_settlement_date_and_prepublication_time_are_never_visible():
    vintage = _vintage()
    assert visible_source_snapshots_as_of(
        vintage, datetime(2024, 1, 12, 21, tzinfo=timezone.utc)
    ) == ()
    assert visible_source_snapshots_as_of(
        vintage, datetime(2024, 1, 25, 20, 59, tzinfo=timezone.utc)
    ) == ()


def test_snapshot_becomes_visible_at_its_permitted_open_only():
    vintage = _vintage()
    before = visible_source_snapshots_as_of(
        vintage, datetime(2024, 1, 26, 14, 29, 59, tzinfo=timezone.utc)
    )
    at_open = visible_source_snapshots_as_of(
        vintage, datetime(2024, 1, 26, 14, 30, tzinfo=timezone.utc)
    )
    assert before == ()
    assert [item.settlement_date for item in at_open] == ["2024-01-12"]


def test_warmup_is_visible_for_lineage_but_not_delta_eligible():
    vintage = _vintage()
    first_open = datetime(2024, 1, 26, 14, 30, tzinfo=timezone.utc)
    second_open = datetime(2024, 2, 13, 14, 30, tzinfo=timezone.utc)
    assert [
        item.settlement_date
        for item in visible_source_snapshots_as_of(vintage, first_open)
    ] == ["2024-01-12"]
    assert delta_eligible_snapshots_as_of(vintage, first_open) == ()
    assert [
        item.settlement_date
        for item in delta_eligible_snapshots_as_of(vintage, second_open)
    ] == ["2024-01-31"]


def test_naive_as_of_time_is_refused_instead_of_assumed_utc():
    with pytest.raises(ShortInterestDatasetError, match="timezone-aware"):
        visible_source_snapshots_as_of(
            _vintage(), datetime(2024, 1, 26, 14, 30)
        )
