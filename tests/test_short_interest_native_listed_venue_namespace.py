"""Fabricated namespace predicates only; no source/API/quantity observations."""
import importlib.util
from pathlib import Path
import sys

import pytest

import research.short_interest_etf.native_listed_venue_namespace as m


def row(mic):
    return {"ticker": "SYN", "primary_exchange": mic, "type": "CS", "locale": "us", "market": "stocks", "active": True,
            "source_origin": {"page_ordinal": 1, "row_index": 0, "source_file_sha256": "a" * 64}}


@pytest.mark.parametrize("active", [False, None, 0, 1, "true"])
def test_venue_name_does_not_admit_inactive_or_unobserved_query_date_listing(active):
    original = {**row("XNYS"), "active": active}
    result = m.qualify_venue_namespace(original)
    assert type(result["active"]) is type(active) and result["active"] == active
    assert result["venue_namespace_assessment"]["source_listing_venue_candidate"] is False
    assert "dated_source_active_listing_assertion_missing_or_inactive" in result["venue_namespace_assessment"]["refusal_reasons"]


@pytest.mark.parametrize("mic", [None, "", " XNYS ", "NYSE", "OTCM", "PINX", "TRFN", "XOFF", "XXXX"])
def test_missing_OTC_reporting_or_unmapped_venue_stays_negative_with_original_origin(mic):
    original = row(mic)
    checked = m.qualify_venue_namespace(original)
    assert checked["source_origin"] == original["source_origin"]
    assert checked["primary_exchange"] == mic
    assert checked["venue_namespace_assessment"]["refusal_reasons"]
    assert checked["venue_namespace_assessment"]["source_listing_venue_candidate"] is False
    assert "venue_namespace_assessment" not in original


@pytest.mark.parametrize("mic", [item[0] for item in m.VENUES])
def test_finite_namespace_match_is_not_historical_listing_or_PIT_admission(mic):
    checked = m.qualify_venue_namespace(row(mic))["venue_namespace_assessment"]
    assert checked["source_listing_venue_candidate"] is True
    assert checked["historical_listing_admitted"] is checked["source_admitted"] is False
    assert checked["historical_effective_intervals"] == [] and checked["historical_available_date"] is None


def test_later_missing_venue_cannot_change_prior_dated_predicate_or_origin():
    earlier = m.qualify_venue_namespace(row("XNYS"))
    later = m.qualify_venue_namespace(row(None))
    assert earlier["venue_namespace_assessment"]["refusal_reasons"] == []
    assert later["venue_namespace_assessment"]["refusal_reasons"] == ["dated_primary_listing_MIC_missing"]


def test_policy_preserves_namespace_date_semantics_and_explicit_partial_coverage():
    value = m.venue_policy()
    assert value["verified_continuous_venue_effective_intervals"] == []
    assert value["mic_creation_is_not_venue_registration_or_security_listing_date"] is True
    assert value["iso_current_active_status_not_backdated"] is True
    assert "not_all_US" in value["coverage"]
    assert value["source_admitted"] is value["historical_listing_admitted"] is False
