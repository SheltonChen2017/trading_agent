from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import ml.databento_authoritative as authority_module
from ml.availability import UniverseMembershipRecord
from ml.databento_authoritative import (
    AdjustmentOptionPolicy,
    DatabentoAuthorityError,
    DatabentoOnlineFeatureProvider,
    DatabentoPointInTimeSource,
    build_authoritative_feature_batch,
    build_historical_universe_snapshot,
    load_historical_universe_snapshot,
    load_authoritative_feature_batch,
    resolve_adjustment_vintage,
    resolve_listing_revision,
    save_historical_universe_snapshot,
    save_authoritative_feature_batch,
)
from ml.databento_pit import (
    CompleteStatisticsCohort,
    NormalizedStatistics,
    StatisticsValueRecord,
    select_complete_statistics_cohorts,
)
from ml.hashing import hash_payload
from scripts import run_databento_ingest


_HASHES = {
    "statistics_snapshot_hash": "a" * 64,
    "security_master_snapshot_hash": "b" * 64,
    "adjustment_snapshot_hash": "c" * 64,
    "universe_snapshot_hash": "d" * 64,
}
_FEATURE_VALUES = {
    "open": 100.0,
    "high": 110.0,
    "low": 90.0,
    "close": 105.0,
    "volume": 1_000,
}


def _cohort() -> CompleteStatisticsCohort:
    records = []
    for sequence, (feature, value) in enumerate(_FEATURE_VALUES.items(), start=1):
        records.append(
            StatisticsValueRecord(
                as_of_session="2026-07-10",
                ticker="NVDA",
                instrument_id=999,
                publisher_id=1,
                channel_id=0,
                feature_name=feature,
                value=value,
                event_at="2026-07-10T20:00:00+00:00",
                reference_at=None,
                available_at=f"2026-07-10T20:01:0{sequence}+00:00",
                summary_flag=1,
                sequence=sequence,
                revision_id=hash_payload({"feature": feature, "sequence": sequence}),
            )
        )
    available = "2026-07-10T20:01:05+00:00"
    return CompleteStatisticsCohort(
        as_of_session="2026-07-10",
        ticker="NVDA",
        summary_flag=1,
        available_at=available,
        observed_at="2026-07-10T20:02:00+00:00",
        cohort_id=hash_payload({"cohort": "NVDA-2026-07-10"}),
        records=tuple(records),
    )


def _security_records(*, include_future_inactive: bool = False):
    records = [
        {
            "ts_effective": "2026-01-01T00:00:00+00:00",
            "ts_record": "2026-01-01T00:00:00+00:00",
            "ts_created": "2026-01-01T00:01:00+00:00",
            "listing_id": "listing-1",
            "security_id": "security-1",
            "listing_status": "A",
            "operating_mic": "XNAS",
            "symbol": "NVDA",
        }
    ]
    if include_future_inactive:
        records.append(
            {
                **records[0],
                "ts_effective": "2027-01-01T00:00:00+00:00",
                "ts_record": "2026-12-15T00:00:00+00:00",
                "ts_created": "2026-12-15T00:01:00+00:00",
                "listing_status": "D",
            }
        )
    return records


def _adjustments(*, include_rescind: bool = False, include_second_option: bool = False):
    records = [
        {
            "ex_date": "2026-07-15",
            "ts_created": "2026-07-14T20:00:00+00:00",
            "event_id": "split-event",
            "security_id": "security-1",
            "status": "A",
            "factor": 0.5,
            "reason": 5,
            "option": 1,
            "operating_mic": "XNAS",
            "symbol": "NVDA",
        }
    ]
    if include_second_option:
        records.append({**records[0], "factor": 0.25, "option": 2})
    if include_rescind:
        records.append(
            {
                **records[0],
                "ts_created": "2026-07-25T12:00:00+00:00",
                "status": "R",
            }
        )
    return records


def _membership() -> UniverseMembershipRecord:
    return UniverseMembershipRecord(
        universe_id="licensed-volatility-universe",
        ticker="NVDA",
        effective_from="2026-01-01",
        effective_to=None,
        announced_at="2025-12-15T00:00:00+00:00",
        available_at="2025-12-15T00:01:00+00:00",
        source_id="licensed-membership",
        source_version="2026.1",
    )


def _batch(*, cutoff="2026-07-20T21:00:00+00:00", adjustments=None, universe=None, security=None):
    return build_authoritative_feature_batch(
        [_cohort()],
        security_master_records=security or _security_records(),
        adjustment_factor_records=_adjustments() if adjustments is None else adjustments,
        historical_universe=[_membership()] if universe is None else universe,
        universe_id="licensed-volatility-universe",
        decision_cutoffs={"2026-07-10": cutoff},
        reference_observed_at=cutoff,
        **_HASHES,
    )


def test_visible_listing_revision_is_selected_without_future_state_leakage():
    listing = resolve_listing_revision(
        _security_records(include_future_inactive=True),
        ticker="NVDA",
        event_at="2026-07-10T20:00:00+00:00",
        decision_cutoff="2026-07-20T21:00:00+00:00",
    )
    assert listing.listing_status == "A"
    assert listing.security_id == "security-1"


def test_one_adjustment_option_is_applied_and_split_volume_is_inverted():
    batch = _batch(adjustments=_adjustments(include_second_option=True))
    row = batch.rows[0]
    assert row["open"] == 50.0
    assert row["close"] == 52.5
    assert row["volume"] == 2_000.0
    assert row["adjustment_revision_count"] == 1
    assert batch.coverage.point_in_time_data is True
    assert batch.manifest["point_in_time_data"] is True


def test_later_rescind_does_not_rewrite_the_earlier_vintage():
    records = _adjustments(include_rescind=True)
    historical = _batch(adjustments=records)
    after_rescind = _batch(
        cutoff="2026-07-30T21:00:00+00:00",
        adjustments=records,
    )
    assert historical.rows[0]["close"] == 52.5
    assert after_rescind.rows[0]["close"] == 105.0
    assert historical.batch_hash != after_rescind.batch_hash


def test_appending_future_reference_revisions_preserves_the_feature_prefix():
    original = _batch()
    extended = _batch(
        adjustments=_adjustments(include_rescind=True),
        security=_security_records(include_future_inactive=True),
    )
    assert original.rows == extended.rows
    assert [record.raw_value_hash for record in original.availability] == [
        record.raw_value_hash for record in extended.availability
    ]
    assert original.manifest["rows_hash"] == extended.manifest["rows_hash"]
    assert original.manifest["availability_hash"] == extended.manifest["availability_hash"]


def test_missing_independent_universe_remains_promotion_blocked():
    batch = _batch(universe=[])
    assert batch.coverage.point_in_time_data is False
    assert "no_universe_membership_records" in batch.coverage.failures
    with pytest.raises(DatabentoAuthorityError, match="complete point-in-time coverage"):
        DatabentoPointInTimeSource(batch)


def test_point_in_time_source_exposes_only_verified_batch_lineage():
    batch = _batch()
    source = DatabentoPointInTimeSource(batch)
    records = source.feature_records(
        tickers=["NVDA"], start_session="2026-07-10", end_session="2026-07-10"
    )
    assert len(records) == 5
    assert source.source_manifest()["batch_hash"] == batch.batch_hash
    assert source.source_manifest()["provides_point_in_time_lineage"] == "true"
    assert source.universe_membership(
        universe_id="wrong", start_session="2026-01-01", end_session="2026-12-31"
    ) == ()


def test_authoritative_batch_persistence_is_content_addressed_and_verified(tmp_path):
    batch = _batch()
    directory = save_authoritative_feature_batch(batch, tmp_path)
    assert directory.name == batch.batch_hash
    assert save_authoritative_feature_batch(batch, tmp_path) == directory
    loaded = load_authoritative_feature_batch(directory)
    assert loaded.batch_hash == batch.batch_hash
    assert loaded.rows == batch.rows

    features_path = directory / "features.json"
    features_path.write_bytes(features_path.read_bytes() + b" ")
    with pytest.raises(DatabentoAuthorityError, match="not canonical"):
        load_authoritative_feature_batch(directory)


def test_historical_universe_snapshot_is_hash_verified_and_immutable(tmp_path):
    snapshot = build_historical_universe_snapshot(
        [_membership()],
        universe_id="licensed-volatility-universe",
        source_id="licensed-membership",
        source_version="2026.1",
        observed_at="2026-07-20T21:00:00+00:00",
        source_artifact_hash="e" * 64,
    )
    path = tmp_path / "universe.json"
    save_historical_universe_snapshot(snapshot, path)
    save_historical_universe_snapshot(snapshot, path)
    loaded = load_historical_universe_snapshot(path)
    assert loaded == snapshot

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["records"][0]["ticker"] = "MSFT"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(DatabentoAuthorityError, match="lineage mismatch|hash mismatch"):
        load_historical_universe_snapshot(path)


def test_online_provider_uses_the_same_cutoff_builder(monkeypatch, tmp_path):
    normalized = NormalizedStatistics(records=_cohort().records, refusals=())

    def fake_fetch(request, **kwargs):
        assert request.tickers == ("NVDA",)
        return SimpleNamespace(
            normalized=normalized,
            manifest={
                "observed_at": "2026-07-20T21:00:00+00:00",
                "raw_sha256": "a" * 64,
            },
        )

    monkeypatch.setattr(authority_module, "fetch_statistics_snapshot", fake_fetch)
    universe = build_historical_universe_snapshot(
        [_membership()],
        universe_id="licensed-volatility-universe",
        source_id="licensed-membership",
        source_version="2026.1",
        observed_at="2026-07-20T21:00:00+00:00",
        source_artifact_hash="e" * 64,
    )
    provider = DatabentoOnlineFeatureProvider(
        directory=tmp_path,
        max_cost_usd=0.10,
        security_master_records=_security_records(),
        adjustment_factor_records=_adjustments(),
        historical_universe=universe,
        reference_observed_at="2026-07-20T21:00:00+00:00",
        security_master_snapshot_hash="b" * 64,
        adjustment_snapshot_hash="c" * 64,
    )
    online = provider.collect(
        tickers=["NVDA"],
        session="2026-07-10",
        decision_cutoff="2026-07-20T21:00:00+00:00",
    )
    research_cohorts = select_complete_statistics_cohorts(
        normalized,
        decision_cutoffs={"2026-07-10": "2026-07-20T21:00:00+00:00"},
        observed_at="2026-07-20T21:00:00+00:00",
    )
    research = build_authoritative_feature_batch(
        research_cohorts,
        security_master_records=_security_records(),
        adjustment_factor_records=_adjustments(),
        historical_universe=universe.records,
        universe_id=universe.universe_id,
        decision_cutoffs={"2026-07-10": "2026-07-20T21:00:00+00:00"},
        reference_observed_at="2026-07-20T21:00:00+00:00",
        **_HASHES,
    )
    assert online.rows == research.rows
    assert online.manifest["rows_hash"] == research.manifest["rows_hash"]


def test_online_provider_refuses_capture_after_declared_cutoff(monkeypatch, tmp_path):
    normalized = NormalizedStatistics(records=_cohort().records, refusals=())
    monkeypatch.setattr(
        authority_module,
        "fetch_statistics_snapshot",
        lambda *args, **kwargs: SimpleNamespace(
            normalized=normalized,
            manifest={"observed_at": "2026-07-20T21:00:01+00:00", "raw_sha256": "a" * 64},
        ),
    )
    universe = build_historical_universe_snapshot(
        [_membership()],
        universe_id="licensed-volatility-universe",
        source_id="licensed-membership",
        source_version="2026.1",
        observed_at="2026-07-20T21:00:00+00:00",
        source_artifact_hash="e" * 64,
    )
    provider = DatabentoOnlineFeatureProvider(
        directory=tmp_path,
        max_cost_usd=0.10,
        security_master_records=_security_records(),
        adjustment_factor_records=_adjustments(),
        historical_universe=universe,
        reference_observed_at="2026-07-20T21:00:00+00:00",
        security_master_snapshot_hash="b" * 64,
        adjustment_snapshot_hash="c" * 64,
    )
    with pytest.raises(DatabentoAuthorityError, match="observed after"):
        provider.collect(
            tickers=["NVDA"],
            session="2026-07-10",
            decision_cutoff="2026-07-20T21:00:00+00:00",
        )


def test_authoritative_replay_cli_requires_all_independent_evidence_inputs():
    args = run_databento_ingest.build_parser().parse_args(
        [
            "build-authoritative",
            "--statistics-manifest", "stats.manifest.json",
            "--security-master-manifest", "security.manifest.json",
            "--adjustment-factors-manifest", "adjustments.manifest.json",
            "--universe-snapshot", "universe.json",
            "--decision-cutoffs-json", "cutoffs.json",
        ]
    )
    assert args.command == "build-authoritative"
    assert [path.name for path in args.statistics_manifest] == ["stats.manifest.json"]
