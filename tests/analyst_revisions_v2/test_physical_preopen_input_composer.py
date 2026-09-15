"""Offline physical-source tests for the ARV2 pre-open input composer."""
from __future__ import annotations

import dataclasses
import inspect
import json
from datetime import datetime, timezone

import pytest

from research.analyst_revisions_v2.accepted_risk_input_pair import (
    MassiveSourceRole,
)
from research.analyst_revisions_v2.canonical import sha256_bytes
from scripts.build_arv2_massive_input_pair import (
    _build_massive_accepted_risk_input_pair_for_test,
)
from scripts.build_arv2_preopen_input import (
    FUNDAMENTAL_SEED_AVAILABILITY,
    FIRM_ONTOLOGY_REFUSAL,
    FULL_PIT_UNIVERSE_REFUSAL,
    STATUS_BLOCKED,
    PhysicalPreopenInputError,
    build_physical_preopen_input_candidate,
    require_physical_preopen_input_candidate,
)
from scripts.capture_arv2_massive import (
    ENDPOINT_PATHS,
    _capture_massive_history_for_test,
)
from scripts.capture_arv2_sharadar import (
    SharadarDataset,
    _capture_sharadar_history_for_test,
)
from tests.analyst_revisions_v2.test_massive_capture_adapter import (
    FakeResponse as MassiveResponse,
    FakeSession as MassiveSession,
    _payload as massive_payload,
)
from tests.analyst_revisions_v2.test_sharadar_capture_adapter import (
    FakeResponse as SharadarResponse,
    FakeSession as SharadarSession,
    _zip_bytes,
)


NOW = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
MASSIVE_KEY = "offline-test-key-physical-preopen-NEVER-REAL"
SHARADAR_KEY = "offline-test-sharadar-physical-preopen-NEVER-REAL"

TICKERS = (
    b"table,ticker,permaticker,isdelisted,name,category,exchange,sector,industry,"
    b"firstpricedate,lastpricedate,figi,cusips\n"
    b"SF1,AAA,100001,N,Active Corp,Domestic Common Stock,NASDAQ,"
    b"Technology,Software,2010-01-04,,BBG001AAA111,000000AA0\n"
    b"SF1,OLD,100002,Y,Old Corp,Domestic Common Stock,NYSE,"
    b"Industrials,Machinery,2000-01-03,2020-12-31,BBG001OLD222,000000BB8\n"
)
ACTIONS = (
    b"date,action,ticker,name,value,contraticker,contraname\n"
    b"2020-12-31,delisted,OLD,Old Corp,,,\n"
)
FUNDAMENTALS = (
    b"ticker,dimension,calendardate,date,reportperiod,lastupdated,"
    b"sharesbas,equityusd,revenueusd\n"
    b"AAA,ART,2019-12-31,2020-02-10,2019-12-31,2020-02-10,"
    b"900000,4500000,8000000\n"
    b"AAA,ART,2020-12-31,2021-02-10,2020-12-31,2021-02-10,"
    b"1000000,5000000,9000000\n"
)


def _massive_row(identifier: str, role: MassiveSourceRole) -> dict[str, object]:
    common: dict[str, object] = {
        "benzinga_id": identifier,
        "date": "2021-01-04",
        "time": "08:30:00",
        "ticker": "AAA",
    }
    if role is MassiveSourceRole.CORPORATE_GUIDANCE:
        common.update(
            {
                "last_updated": "2021-01-04 09:30:00",
                "guidance_type": "Revenue",
            }
        )
    else:
        common["last_updated"] = "2021-01-04T12:00:00Z"
    if role is MassiveSourceRole.ANALYST_RATINGS:
        common.update(
            {
                "benzinga_firm_id": "firm-1",
                "benzinga_analyst_id": "analyst-1",
                "firm": "Example Firm",
                "rating_action": "upgrades",
                "rating": "Buy",
                "previous_rating": "Hold",
            }
        )
    return common


def _physical_sources(
    tmp_path,
    *,
    rating_overrides=None,
    empty_role=None,
    requested_first="2013-01-02",
    requested_last="2025-12-31",
    fundamentals=FUNDAMENTALS,
    tickers=TICKERS,
):
    base = "https://api.massive.com"
    rows = []
    for role in MassiveSourceRole:
        row = _massive_row(f"{role.value}-1", role)
        if role is MassiveSourceRole.ANALYST_RATINGS and rating_overrides:
            row.update(rating_overrides)
        rows.append((role, row))
    massive_responses = [
        MassiveResponse(
            massive_payload([] if role is empty_role else [row]),
            base + ENDPOINT_PATHS[role],
        )
        for role, row in rows
    ]
    massive = _capture_massive_history_for_test(
        requested_first_event_date=requested_first,
        requested_last_event_date=requested_last,
        artifact_root=tmp_path / "massive",
        session=MassiveSession(massive_responses),
        clock=lambda: NOW,
        api_key=MASSIVE_KEY,
    )
    bridge = _build_massive_accepted_risk_input_pair_for_test(
        massive.artifact_path
    )
    sharadar = _capture_sharadar_history_for_test(
        artifact_root=tmp_path / "sharadar",
        session=SharadarSession(
            [
                SharadarResponse(
                    _zip_bytes(SharadarDataset.TICKERS, csv_bytes=tickers)
                ),
                SharadarResponse(
                    _zip_bytes(SharadarDataset.ACTIONS, csv_bytes=ACTIONS)
                ),
                SharadarResponse(
                    _zip_bytes(
                        SharadarDataset.FUNDAMENTALS, csv_bytes=fundamentals
                    )
                ),
            ]
        ),
        clock=lambda: NOW,
        api_key=SHARADAR_KEY,
    )
    return bridge, sharadar


def test_ticker_universe_admits_only_documented_sf1_fundamentals_alias(tmp_path):
    mixed = TICKERS.replace(b"SF1,OLD", b"SEP,OLD")
    candidate = build_physical_preopen_input_candidate(
        *_physical_sources(tmp_path, tickers=mixed)
    )
    universe = json.loads(candidate.eligible_universe_artifact_bytes)
    report = json.loads(candidate.composition_report_bytes)

    assert universe["candidate_security_count"] == 1
    assert universe["candidate_security_rows"][0][
        "current_snapshot_ticker_display"
    ] == "AAA"
    assert report["ticker_candidate_refusal_counts"] == {
        "ticker row is outside the documented Sharadar SF1 fundamentals table": 1
    }


def test_physical_sources_produce_authenticated_hard_refusal_candidate(tmp_path):
    bridge, sharadar = _physical_sources(tmp_path)
    candidate = build_physical_preopen_input_candidate(bridge, sharadar)
    repeated = build_physical_preopen_input_candidate(bridge, sharadar)

    assert require_physical_preopen_input_candidate(candidate) is candidate
    assert require_physical_preopen_input_candidate(repeated) is repeated
    assert repeated == candidate
    assert candidate.status == STATUS_BLOCKED
    assert candidate.first_session == "2013-01-02"
    assert candidate.last_session == "2025-12-31"
    assert candidate.calculation_session == "2026-01-02"
    assert candidate.blocking_refusals[:2] == (
        FULL_PIT_UNIVERSE_REFUSAL,
        FIRM_ONTOLOGY_REFUSAL,
    )
    assert candidate.closed_input_manifest_bytes is None
    assert candidate.run_authority_candidate_bytes is None
    assert candidate.six_preopen_roles_produced is False
    assert candidate.production_preopen_input_available is False
    assert candidate.full_pit_universe_established is False
    assert candidate.full_market_peer_census_established is False

    report = json.loads(candidate.composition_report_bytes)
    assert set(report["preopen_role_status"]) == {
        "universe",
        "sid_mapping",
        "fundamentals",
        "earnings",
        "guidance",
        "ratings",
    }
    assert report["closed_input_manifest_constructed"] is False
    assert report["run_authority_candidate_constructed"] is False
    assert report["qc_sid_values_present"] is False


def test_current_snapshot_universe_is_full_candidate_not_rated_only(tmp_path):
    candidate = build_physical_preopen_input_candidate(*_physical_sources(tmp_path))
    universe = json.loads(candidate.eligible_universe_artifact_bytes)

    assert universe["status"] == STATUS_BLOCKED
    assert universe["blocking_refusal"] == FULL_PIT_UNIVERSE_REFUSAL
    assert universe["candidate_security_count"] == 2
    assert universe["candidate_security_session_terminal_count"] > 2
    assert universe["full_market_peer_census_established"] is False
    assert universe["historical_membership_availability_established"] is False
    assert universe["historical_classification_availability_established"] is False
    assert {row["current_snapshot_ticker_display"] for row in universe[
        "candidate_security_rows"
    ]} == {"AAA", "OLD"}
    assert all(
        row["qc_security_id"] is None
        and row["point_in_time"] is False
        and "share_class_id" not in row
        and row["source_composite_figi"].startswith("BBG")
        and row["membership_status"]
        == "review_required_current_snapshot_not_PIT"
        for row in universe["candidate_security_rows"]
    )
    # OLD is in the proposal through its captured terminal date even though no
    # rating event named OLD.  This protects against a rated-only peer census.
    assert next(
        row
        for row in universe["candidate_security_rows"]
        if row["current_snapshot_ticker_display"] == "OLD"
    )["candidate_last_session"] == "2020-12-31"


def test_firm_vocabulary_is_observed_but_never_ordered_or_reviewed(tmp_path):
    candidate = build_physical_preopen_input_candidate(*_physical_sources(tmp_path))
    firm = json.loads(candidate.firm_review_candidate_bytes)
    assert firm["status"] == "review_required_not_authority"
    assert firm["ontology_reviewed"] is False
    assert firm["ordering_inferred"] is False
    assert firm["production_authority"] is False
    assert firm["firms"][0]["ordered_scale"] is None
    assert {item["raw_label"] for item in firm["firms"][0]["observed_labels"]} == {
        "Buy",
        "Hold",
    }


def test_completeness_and_seed_candidates_are_source_derived(tmp_path):
    candidate = build_physical_preopen_input_candidate(*_physical_sources(tmp_path))
    report = json.loads(candidate.composition_report_bytes)
    sources = json.loads(candidate.source_seed_candidate_bytes)
    fundamentals = json.loads(candidate.fundamental_seed_inventory_bytes)

    assert report["source_completeness"] == {
        "analyst_ratings": True,
        "corporate_guidance": True,
        "earnings": True,
    }
    assert sources["caller_authored_completeness_accepted"] is False
    assert sources["role_candidate_counts"] == {
        "earnings": 1,
        "guidance": 1,
        "ratings": 1,
    }
    assert sources["terminal_count"] == 3
    assert sources["role_candidates"]["ratings"][0]["admitted"] is True
    assert fundamentals["seed_count"] == 1
    assert fundamentals["outcomes_used"] is False
    assert fundamentals["availability_semantics"] == FUNDAMENTAL_SEED_AVAILABILITY
    assert fundamentals["seed_rows"] == [
        {
            "available_at": "2021-02-11T12:00:00.000000Z",
            "book_equity_usd": "5000000",
            "period_end": "2020-12-31",
            "prior_fiscal_year_revenue_ttm_usd": "8000000",
            "revenue_ttm_usd": "9000000",
            "schema": "arv2-preopen-control-fundamental-seed-v1",
            "security_id": "sharadar-composite-figi-BBG001AAA111",
            "shares_outstanding": "1000000",
        }
    ]
    assert sha256_bytes(candidate.quality_policy_bytes) == report[
        "q_data_policy_sha256"
    ]
    assert tuple(inspect.signature(
        build_physical_preopen_input_candidate
    ).parameters) == ("bridge", "sharadar_capture")


def test_non_art_source_rows_are_retained_but_never_enter_fundamental_seeds(
    tmp_path,
):
    mixed = FUNDAMENTALS + (
        b"AAA,MRY,2020-12-31,2021-02-10,2020-12-31,2021-02-10,"
        b"7777777,8888888,9999999\n"
    )
    bridge, sharadar = _physical_sources(tmp_path, fundamentals=mixed)
    assert sharadar.archives[2].fundamental_dimension_counts == (
        ("ART", 2),
        ("MRY", 1),
    )

    candidate = build_physical_preopen_input_candidate(bridge, sharadar)
    report = json.loads(candidate.composition_report_bytes)
    fundamentals = json.loads(candidate.fundamental_seed_inventory_bytes)

    assert report["fundamental_refusal_counts"]["non-ART fundamental"] == 1
    assert fundamentals["seed_count"] == 1
    assert fundamentals["seed_rows"][0]["shares_outstanding"] == "1000000"
    assert fundamentals["seed_rows"][0]["book_equity_usd"] == "5000000"
    assert fundamentals["seed_rows"][0]["revenue_ttm_usd"] == "9000000"


def test_potentially_relevant_malformed_rating_downgrades_completeness(tmp_path):
    candidate = build_physical_preopen_input_candidate(
        *_physical_sources(
            tmp_path,
            rating_overrides={"benzinga_analyst_id": ""},
        )
    )
    report = json.loads(candidate.composition_report_bytes)
    sources = json.loads(candidate.source_seed_candidate_bytes)

    assert report["source_completeness"]["analyst_ratings"] is False
    assert any(
        item.startswith("analyst_ratings_source_not_complete")
        for item in candidate.blocking_refusals
    )
    rating = sources["role_candidates"]["ratings"][0]
    assert rating["admitted"] is False
    assert rating["analyst_id"].startswith("refused-analyst-")
    assert any(
        terminal["reason"]
        == (
            "potentially_relevant_rating_missing_or_invalid_stable_"
            "analyst_or_firm_identifier"
        )
        for terminal in sources["composition_terminals"]
    )


def test_empty_successful_provider_role_is_not_claimed_complete(tmp_path):
    candidate = build_physical_preopen_input_candidate(
        *_physical_sources(tmp_path, empty_role=MassiveSourceRole.EARNINGS)
    )
    report = json.loads(candidate.composition_report_bytes)
    sources = json.loads(candidate.source_seed_candidate_bytes)

    assert report["source_completeness"]["earnings"] is False
    assert sources["source_completeness"]["earnings"] is False
    assert sources["role_candidate_counts"]["earnings"] == 0


def test_nonfrozen_capture_range_cannot_claim_role_completeness(tmp_path):
    candidate = build_physical_preopen_input_candidate(
        *_physical_sources(tmp_path, requested_first="2020-01-02")
    )
    report = json.loads(candidate.composition_report_bytes)

    assert report["source_completeness"] == {
        "analyst_ratings": False,
        "corporate_guidance": False,
        "earnings": False,
    }
    assert sum(
        item.endswith(
            "_source_not_complete_for_frozen_query_and_accepted_risk_policy"
        )
        for item in candidate.blocking_refusals
    ) == 3


def test_forged_physical_capture_is_rejected_before_composition(tmp_path):
    bridge, sharadar = _physical_sources(tmp_path)
    archive = sharadar.artifact_path / "01-tickers-years-full.zip"
    forged = dataclasses.replace(sharadar, capture_sha256="a" * 64)
    with pytest.raises(PhysicalPreopenInputError, match="changed after loading"):
        build_physical_preopen_input_candidate(bridge, forged)
    assert archive.exists()


def test_candidate_mutation_loses_builder_authority(tmp_path):
    candidate = build_physical_preopen_input_candidate(*_physical_sources(tmp_path))
    original = candidate.production_preopen_input_available
    object.__setattr__(candidate, "production_preopen_input_available", True)
    try:
        with pytest.raises(PhysicalPreopenInputError, match="lost builder authority"):
            require_physical_preopen_input_candidate(candidate)
    finally:
        object.__setattr__(
            candidate, "production_preopen_input_available", original
        )
    assert require_physical_preopen_input_candidate(candidate) is candidate


def test_module_contains_no_network_qc_or_outcome_entry_point():
    import scripts.build_arv2_preopen_input as module

    assert not hasattr(module, "requests")
    assert not hasattr(module, "capture_massive_history")
    assert not hasattr(module, "capture_sharadar_history")
    assert not hasattr(module, "run_backtest")
    assert not hasattr(module, "read_outcomes")
