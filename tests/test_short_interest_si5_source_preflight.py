"""Synthetic-only tests for the non-authoritative SI-5 source preflight."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from data.hashing import hash_payload
from research.short_interest_etf.contracts import ReleasePrecision
from research.short_interest_etf.dataset import load_synthetic_fixture
from research.short_interest_etf.si5_offline_protocol import (
    SI5_OFFLINE_PROTOCOL_SHA256,
)
from research.short_interest_etf.si5_source_preflight import (
    ScheduleDateClaim,
    SI5SourcePreflightError,
    SI5SourcePreflightReceipt,
    build_si5_source_preflight,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "short_interest_etf"
    / "official_style_v1.json"
)


def _releases_and_claims():
    releases = load_synthetic_fixture(FIXTURE).release_calendar
    claims = tuple(
        ScheduleDateClaim(
            settlement_date=release.settlement_date,
            public_release_date=release.public_release_date,
            evidence_sha256=release.evidence_sha256,
        )
        for release in releases
    )
    return releases, claims


def test_matching_schedule_dates_bind_to_conservative_next_opens_without_authority():
    releases, claims = _releases_and_claims()
    receipt = build_si5_source_preflight(releases, claims)
    payload = receipt.to_payload()

    assert receipt.sha256 == hash_payload(payload)
    assert payload["offline_protocol_sha256"] == SI5_OFFLINE_PROTOCOL_SHA256
    assert [row["settlement_date"] for row in payload["release_bindings"]] == [
        "2024-01-12", "2024-01-31"
    ]
    assert [row["execution_session"] for row in payload["release_bindings"]] == [
        "2024-01-26", "2024-02-13"
    ]
    assert all(
        row["bound_release"]["precision"] == ReleasePrecision.DATE_ONLY.value
        and row["bound_release"]["public_release_at"] is None
        for row in payload["release_bindings"]
    )
    assert payload["candidate_lookbacks"] == [20, 60, 120, 252]
    assert payload["separate_coverage_audit_target_sessions"] == 60
    assert payload["coverage_audit_does_not_change_candidate_eligibility"] is True
    assert payload["source_admitted"] is False
    assert payload["outcome_access_authorized"] is False
    assert payload["qc_backtest_authorized"] is False
    assert payload["authorized_outcome_looks"] == 0
    assert "original_and_revision_vintages_unverified" in payload["blockers"]
    assert "actual_price_volume_coverage_unverified" in payload["blockers"]


def test_schedule_only_evidence_never_uses_a_claimed_preopen_exact_time():
    releases, claims = _releases_and_claims()
    preopen = replace(
        releases[0],
        public_release_at="2024-01-25T13:00:00Z",
        observed_at="2024-01-25T13:01:00Z",
    )
    receipt = build_si5_source_preflight((preopen,), (claims[0],))
    binding = receipt.to_payload()["release_bindings"][0]
    assert binding["execution_session"] == "2024-01-26"
    assert binding["bound_release"]["public_release_at"] is None
    assert binding["bound_release"]["precision"] == "date_only"


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "wrong_date", "wrong_hash"])
def test_incomplete_or_conflicting_schedule_claim_is_refused(mutation):
    releases, claims = _releases_and_claims()
    if mutation == "missing":
        claims = claims[:1]
    elif mutation == "extra":
        claims = (*claims, replace(claims[0], settlement_date="2024-01-15"))
    elif mutation == "duplicate":
        claims = (*claims, claims[0])
    elif mutation == "wrong_date":
        claims = (replace(claims[0], public_release_date="2024-01-26"), claims[1])
    else:
        claims = (replace(claims[0], evidence_sha256="f" * 64), claims[1])
    with pytest.raises(SI5SourcePreflightError, match="REFUSED"):
        build_si5_source_preflight(releases, claims)


def test_receipt_detaches_caller_release_and_payload():
    releases, claims = _releases_and_claims()
    receipt = build_si5_source_preflight(releases, claims)
    original = receipt.sha256
    object.__setattr__(releases[0], "public_release_date", "2024-01-26")
    payload = receipt.to_payload()
    payload["release_bindings"].clear()
    payload["blockers"].clear()
    assert receipt.sha256 == original
    assert len(receipt.to_payload()["release_bindings"]) == 2
    assert receipt.to_payload()["blockers"]


def test_daily_volume_or_arbitrary_object_cannot_be_schedule_release():
    _, claims = _releases_and_claims()
    with pytest.raises(SI5SourcePreflightError, match="exact ReleaseCalendarEntry"):
        build_si5_source_preflight((object(),), (claims[0],))


def test_direct_receipt_cannot_claim_schedule_match_without_a_matching_claim():
    releases, claims = _releases_and_claims()
    bound = build_si5_source_preflight(releases, claims).bound_releases
    with pytest.raises(SI5SourcePreflightError, match="schedule"):
        SI5SourcePreflightReceipt(bound_releases=bound, schedule_claims=())
    with pytest.raises(SI5SourcePreflightError, match="schedule"):
        SI5SourcePreflightReceipt(
            bound_releases=bound,
            schedule_claims=(replace(claims[0], evidence_sha256="f" * 64), claims[1]),
        )


def test_direct_receipt_detaches_mutable_caller_owned_contracts():
    releases, claims = _releases_and_claims()
    bound = build_si5_source_preflight(releases, claims).bound_releases
    receipt = SI5SourcePreflightReceipt(bound_releases=bound, schedule_claims=claims)
    original = receipt.sha256
    object.__setattr__(bound[0], "public_release_date", "2024-01-26")
    object.__setattr__(claims[0], "public_release_date", "2024-01-26")
    assert receipt.sha256 == original


def test_fabricated_matching_claims_remain_explicitly_blocked():
    releases, claims = _releases_and_claims()
    receipt = build_si5_source_preflight(releases, claims)
    payload = receipt.to_payload()
    assert payload["calendar_check"] == "date_and_digest_structural_match_only"
    assert "schedule_extract_origin_and_bytes_unverified" in payload["blockers"]
    assert payload["point_in_time_data_verified"] is False
    assert payload["source_admitted"] is False


@pytest.mark.parametrize("which", ["release", "claim"])
def test_missing_postconstruction_source_field_gets_named_refusal(which):
    releases, claims = _releases_and_claims()
    if which == "release":
        object.__delattr__(releases[0], "public_release_date")
    else:
        object.__delattr__(claims[0], "public_release_date")
    with pytest.raises(SI5SourcePreflightError, match="REFUSED"):
        build_si5_source_preflight(releases, claims)
