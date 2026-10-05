"""Synthetic-only SI-5 comparison cohorts retain their authentic full ranks."""
from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

import pytest

from data.hashing import hash_payload
from research.short_interest_etf.dataset import build_vintage
from research.short_interest_etf.si5_offline_protocol import SI5_OFFLINE_PROTOCOL
from research.short_interest_etf.si5_stock_cohort import (
    SI5StockCohortError,
    SI5StockCohortManifest,
    _project_releases,
    build_si5_stock_cohort_manifest,
)
from research.short_interest_etf.stock_eligible_ranking import (
    StockEligibleRankingInventory,
    build_stock_eligible_ranking_inventory,
)
from research.short_interest_etf.stock_eligible_population import (
    build_stock_eligible_population_inventory,
)
from research.short_interest_etf.stock_investability import build_stock_investability
from research.short_interest_etf.stock_population_binding import (
    build_stock_population_binding_inventory,
)
from tests.test_short_interest_stock_eligible_ranking import (
    LOOKBACKS,
    NEXT_OPEN,
    SETTLEMENT,
    _later_only_binding,
    _nineteen_ranking,
    _lookback_split_ranking,
    _small_ranking,
)
from tests.test_short_interest_stock_investability import _inputs


def _release(payload: dict) -> dict:
    return next(row for row in payload["releases"] if row["settlement_date"] == SETTLEMENT)


@lru_cache(maxsize=1)
def _nineteen_manifest():
    return build_si5_stock_cohort_manifest(_nineteen_ranking())


@lru_cache(maxsize=1)
def _nineteen_manifest_payload():
    return _nineteen_manifest().to_payload()


def test_manifest_binds_protocol_and_preserves_four_authentic_full_rankings():
    manifest = _nineteen_manifest()
    payload = _nineteen_manifest_payload()
    assert isinstance(manifest, SI5StockCohortManifest)
    assert len(payload["source_ranking_sha256"]) == 64
    assert payload["si5_protocol_sha256"] == SI5_OFFLINE_PROTOCOL.sha256
    assert payload["manifest_sha256"] == hash_payload({
        key: value for key, value in payload.items() if key != "manifest_sha256"
    })
    assert payload["selected_lookback"] is None
    for flag in (
        "source_rights_verified", "actual_pit_coverage_verified",
        "outcome_authorized", "qc_backtest_authorized", "production_authoritative",
        "trading_authority",
    ):
        assert payload[flag] is False
    release = _release(payload)
    assert release["decision_at"] == NEXT_OPEN
    assert len(release["common_security_identity_sha256s"]) == 19
    assert len(release["common_event_ids"]) == 19
    assert release["cohort_comparable"] is True
    assert release["no_comparison_reasons"] == []
    assert {row["lookback_sessions"] for row in release["lookbacks"]} == set(LOOKBACKS)
    for window in release["lookbacks"]:
        original = window["source_ranking"]
        assert original["ranking_sha256"] == hash_payload({
            key: value for key, value in original.items() if key != "ranking_sha256"
        })
        assert len(window["comparison_rows"]) == 19
        assert window["high_pressure_event_ids"]
        assert window["low_pressure_event_ids"]
        assert not set(window["high_pressure_event_ids"]) & set(window["low_pressure_event_ids"])
        for row in window["comparison_rows"]:
            assert row["event_id"] in original["ranked_event_ids"]
            assert row["pressure_row_sha256"] in {
                item["ranking_row_sha256"] for item in original["rows"]
                if item["role"] == "pressure"
            }


def test_partial_history_uses_common_stable_identity_without_reranking():
    release = _release(build_si5_stock_cohort_manifest(_lookback_split_ranking()).to_payload())
    assert len(release["common_security_identity_sha256s"]) == 19
    windows = {row["lookback_sessions"]: row for row in release["lookbacks"]}
    assert len(windows[20]["source_ranking"]["ranked_event_ids"]) == 20
    assert len(windows[20]["comparison_rows"]) == 19
    assert len(windows[120]["source_ranking"]["ranked_event_ids"]) == 19
    for lookback in LOOKBACKS:
        original = windows[lookback]["source_ranking"]
        assert original["ranking_sha256"] == hash_payload({
            key: value for key, value in original.items() if key != "ranking_sha256"
        })
        for row in windows[lookback]["comparison_rows"]:
            original_pressure = next(item for item in original["rows"] if item["event_id"] == row["event_id"] and item["role"] == "pressure")
            assert row["pressure_percentile"] == original_pressure["role_percentile"]


def test_underfill_and_later_only_releases_are_explicit_no_comparison():
    small = _release(build_si5_stock_cohort_manifest(_small_ranking()).to_payload())
    assert small["cohort_comparable"] is False
    assert "underfilled_full_cohort" in small["no_comparison_reasons"]
    assert all(not row["high_pressure_event_ids"] for row in small["lookbacks"])

    later = build_stock_eligible_ranking_inventory(_later_only_binding())
    empty = _release(build_si5_stock_cohort_manifest(later).to_payload())
    assert empty["cohort_comparable"] is False
    assert "empty_common_intersection" in empty["no_comparison_reasons"]
    assert all(not row["source_ranking"]["release_open_evidence_available"] for row in empty["lookbacks"])
    assert all(row["source_ranking"]["excluded_later_event_ids"] for row in empty["lookbacks"])


def test_authenticated_calendar_release_without_snapshot_cannot_disappear():
    vintage, references, history = _inputs()
    empty_release = replace(
        vintage.release_calendar[-1],
        settlement_date="2024-02-15",
        filing_deadline_date="2024-02-23",
        public_release_date="2024-02-26",
        public_release_at=None,
        observed_at="2024-02-27T21:00:00Z",
        evidence_sha256=hash_payload({"synthetic_empty_release": "2024-02-15"}),
    )
    source = build_vintage(
        replace(
            vintage.manifest,
            settlement_end="2024-02-15",
            retrieved_at="2024-02-28T21:00:00Z",
            raw_artifact_sha256=hash_payload({"synthetic_extended_calendar": "2024-02-15"}),
        ),
        (*vintage.release_calendar, empty_release),
        vintage.snapshots,
    )
    ranking = build_stock_eligible_ranking_inventory(
        build_stock_population_binding_inventory(
            build_stock_eligible_population_inventory(
                build_stock_investability(source, references, history)
            )
        )
    )
    assert {row.settlement_date for row in source.release_calendar} == {
        "2024-01-12", "2024-01-31", "2024-02-15"
    }
    assert {row["settlement_date"] for row in ranking.to_payload()["rankings"]} == {
        "2024-01-12", "2024-01-31"
    }
    with pytest.raises(SI5StockCohortError, match="missing or duplicate cohort"):
        build_si5_stock_cohort_manifest(ranking)


def test_pure_projection_preserves_full_tails_when_common_intersection_loses_them():
    """A nine-name common view cannot become a freshly reranked ten-name tail."""
    summary = {
        "settlement_date": SETTLEMENT,
        "decision_at": NEXT_OPEN,
        "release_sha256": "release",
        "normalization_cohort_sha256": "cohort",
    }
    bindings, rankings = [], []
    for lookback in LOOKBACKS:
        securities = list(range(10)) if lookback != 252 else list(range(1, 11))
        binding_hash = hash_payload({"synthetic_binding": lookback})
        bindings.append({
            "settlement_date": SETTLEMENT,
            "lookback_sessions": lookback,
            "cutoff_relation": "same_open",
            "binding_sha256": binding_hash,
            "members": [
                {
                    "event_id": f"event-{index}",
                    "security_id": f"security-{index}",
                    "security_identity_sha256": f"identity-{index}",
                }
                for index in securities
            ],
        })
        rows = []
        for index in securities:
            for role in ("pressure", "covering"):
                rows.append({
                    "event_id": f"event-{index}",
                    "security_id": f"security-{index}",
                    "role": role,
                    "ranking_row_sha256": hash_payload({"window": lookback, "index": index, "role": role}),
                    "role_percentile": {"numerator": 2 * index + 1, "denominator": 22},
                    "threshold_candidate": (
                        index == max(securities) if role == "pressure"
                        else index == min(securities)
                    ),
                })
        rankings.append({
            "settlement_date": SETTLEMENT,
            "decision_at": NEXT_OPEN,
            "lookback_sessions": lookback,
            "normalization_cohort_sha256": "cohort",
            "source_binding_cohort_sha256": binding_hash,
            "release_open_evidence_available": True,
            "ranked_event_ids": [f"event-{index}" for index in securities],
            "rows": rows,
            "underfill_reasons": [],
        })
    release = _project_releases(
        {"rankings": rankings},
        {"normalization_cohorts": [summary], "bindings": bindings},
        (SETTLEMENT,),
    )[0]
    assert release["cohort_comparable"] is False
    assert release["no_comparison_reasons"] == [
        "missing_common_high_pressure_tail",
        "missing_common_low_pressure_tail",
        "underfilled_common_intersection",
    ]
    assert release["common_event_ids"] == [f"event-{index}" for index in range(1, 10)]
    assert all(len(window["source_ranking"]["ranked_event_ids"]) == 10 for window in release["lookbacks"])
    assert all(len(window["comparison_rows"]) == 9 for window in release["lookbacks"])
    last = release["lookbacks"][-1]
    assert last["source_ranking"]["rows"][-2]["threshold_candidate"] is True
    assert last["high_pressure_event_ids"] == []
    assert all(row["pressure_percentile"] == next(
        original["role_percentile"] for original in last["source_ranking"]["rows"]
        if original["event_id"] == row["event_id"] and original["role"] == "pressure"
    ) for row in last["comparison_rows"])


def test_returned_payload_is_detached_from_authenticated_source():
    manifest = build_si5_stock_cohort_manifest(_small_ranking())
    baseline = manifest.to_payload()
    altered = manifest.to_payload()
    _release(altered)["lookbacks"][0]["source_ranking"]["ranked_event_ids"].append("forged")
    assert manifest.to_payload() == baseline
    assert manifest.to_payload() != altered


def test_untrusted_source_or_protocol_and_postconstruction_tamper_refuse():
    with pytest.raises(SI5StockCohortError, match="REFUSED"):
        build_si5_stock_cohort_manifest(None)
    with pytest.raises(SI5StockCohortError, match="REFUSED"):
        build_si5_stock_cohort_manifest(_small_ranking(), object())
    forged = StockEligibleRankingInventory(_small_ranking().binding)
    object.__setattr__(forged, "_source_binding_sha256", "0" * 64)
    with pytest.raises(SI5StockCohortError, match="REFUSED"):
        build_si5_stock_cohort_manifest(forged)
    manifest = build_si5_stock_cohort_manifest(_small_ranking())
    object.__setattr__(manifest, "_source_ranking_sha256", "0" * 64)
    with pytest.raises(SI5StockCohortError, match="REFUSED"):
        manifest.to_payload()


def test_cannot_inject_outcome_or_lookback_winner_into_manifest():
    manifest = build_si5_stock_cohort_manifest(_small_ranking())
    with pytest.raises((TypeError, SI5StockCohortError)):
        replace(manifest, selected_lookback=20)
    with pytest.raises(SI5StockCohortError, match="REFUSED"):
        SI5StockCohortManifest.to_payload(object())
