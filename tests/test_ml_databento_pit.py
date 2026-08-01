from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import ml.databento_pit as databento_pit
from ml.availability import FeatureAvailabilityRecord, UniverseMembershipRecord
from ml.databento_pit import (
    CompleteStatisticsCohort,
    NormalizedStatistics,
    ReferenceRequest,
    StatisticsRequest,
    canonical_reference_records,
    estimate_statistics_cost,
    evaluate_databento_pit_prerequisites,
    fetch_reference_snapshot,
    fetch_statistics_snapshot,
    normalize_statistics_frame,
    select_complete_statistics_cohorts,
)
from ml.databento_source import DatabentoSourceError
from scripts import run_databento_ingest


_STAT_TYPES = {"open": 1, "low": 4, "high": 5, "volume": 6, "close": 11}


def _statistics_request(summary_flag: int = 1) -> StatisticsRequest:
    return StatisticsRequest(
        tickers=("NVDA",),
        start="2026-07-29",
        end="2026-07-30",
        summary_flag=summary_flag,
    )


def _statistics_frame(*, include_second: bool = True) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    receive_times: list[str] = []
    sequence = 100
    for flag, base, receive in (
        (1, 100.0, "2026-07-29T20:15:00Z"),
        (2, 101.0, "2026-07-29T21:00:00Z"),
    ):
        if flag == 2 and not include_second:
            continue
        values = {
            "open": base,
            "low": base - 1.0,
            "high": base + 2.0,
            "close": base + 1.0,
            "volume": 10_000 + flag,
        }
        for offset, feature_name in enumerate(("open", "low", "high", "close", "volume")):
            sequence += 1
            rows.append(
                {
                    "ts_event": pd.Timestamp("2026-07-29T20:00:00Z"),
                    "ts_ref": pd.NaT,
                    "symbol": "NVDA",
                    "publisher_id": 1,
                    "instrument_id": 999,
                    "stat_type": _STAT_TYPES[feature_name],
                    "stat_flags": flag,
                    "sequence": sequence,
                    "channel_id": 0,
                    "update_action": 1,
                    "price": values[feature_name] if feature_name != "volume" else 0,
                    "quantity": values[feature_name] if feature_name == "volume" else 0,
                }
            )
            receive_times.append(
                (pd.Timestamp(receive) + pd.Timedelta(milliseconds=offset)).isoformat()
            )
    frame = pd.DataFrame(rows)
    frame.index = pd.to_datetime(receive_times, utc=True, format="mixed")
    frame.index.name = "ts_recv"
    return frame


class _FakeStore:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame

    def to_df(self, *, price_type, pretty_ts, map_symbols):
        assert (price_type, pretty_ts, map_symbols) == ("float", True, True)
        return self.frame.copy()


class _FakeMetadata:
    def __init__(self, cost: float):
        self.cost = cost
        self.calls: list[dict[str, object]] = []

    def get_cost(self, **kwargs):
        self.calls.append(kwargs)
        return self.cost


class _FakeTimeseries:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.calls: list[dict[str, object]] = []

    def get_range(self, **kwargs):
        self.calls.append(kwargs)
        Path(kwargs["path"]).write_bytes(b"statistics-dbn-fixture")
        return _FakeStore(self.frame)


class _FakeHistoricalClient:
    def __init__(self, frame: pd.DataFrame, *, cost: float = 0.01):
        self.metadata = _FakeMetadata(cost)
        self.timeseries = _FakeTimeseries(frame)


class _FakeReferenceService:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.calls: list[dict[str, object]] = []

    def get_range(self, **kwargs):
        self.calls.append(kwargs)
        return self.frame.copy()


class _FakeReferenceClient:
    def __init__(self, security: pd.DataFrame, adjustments: pd.DataFrame):
        self.security_master = _FakeReferenceService(security)
        self.adjustment_factors = _FakeReferenceService(adjustments)


def _security_frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "ts_record": [pd.Timestamp("2026-07-01T00:00:00Z")],
            "ts_created": [pd.Timestamp("2026-07-01T00:01:00Z")],
            "listing_id": ["101"],
            "security_id": ["202"],
            "listing_status": ["A"],
            "operating_mic": ["XNAS"],
            "symbol": ["NVDA"],
        },
        index=pd.to_datetime(["2026-07-01T00:00:00Z"], utc=True),
    )
    frame.index.name = "ts_effective"
    return frame


def _adjustment_frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "ts_created": [pd.Timestamp("2026-07-10T12:00:00Z")],
            "event_id": ["303"],
            "security_id": ["202"],
            "status": ["A"],
            "factor": [4.0],
            "reason": [5],
            "option": [1],
            "operating_mic": ["XNAS"],
            "symbol": ["NVDA"],
        },
        index=pd.to_datetime(["2026-07-15"]),
    )
    frame.index.name = "ex_date"
    return frame


def _reference_request(kind: str) -> ReferenceRequest:
    return ReferenceRequest(
        kind=kind,
        tickers=("NVDA",),
        start="2026-07-01",
        end="2026-08-01",
    )


def _membership() -> UniverseMembershipRecord:
    return UniverseMembershipRecord(
        universe_id="volatility_research",
        ticker="NVDA",
        effective_from="2026-01-01",
        effective_to=None,
        announced_at="2025-12-01T00:00:00+00:00",
        available_at="2025-12-01T00:00:00+00:00",
        source_id="licensed_historical_membership_fixture",
        source_version="1",
    )


def test_statistics_request_is_exact_and_cost_estimate_uses_same_query():
    request = _statistics_request()
    assert request.api_kwargs() == {
        "dataset": "EQUS.SUMMARY",
        "schema": "statistics",
        "stype_in": "raw_symbol",
        "symbols": ["NVDA"],
        "start": "2026-07-29T16:05:00-04:00",
        "end": "2026-07-29T16:30:00-04:00",
    }
    client = _FakeHistoricalClient(_statistics_frame(), cost=0.0125)
    assert estimate_statistics_cost(request, client=client) == 0.0125
    assert client.metadata.calls == [request.api_kwargs()]
    with pytest.raises(DatabentoSourceError, match="exactly one calendar day"):
        StatisticsRequest(
            tickers=("NVDA",),
            start="2026-07-29",
            end="2026-07-31",
            summary_flag=2,
        )
    with pytest.raises(DatabentoSourceError, match="NYSE trading session"):
        StatisticsRequest(
            tickers=("NVDA",),
            start="2026-08-01",
            end="2026-08-02",
            summary_flag=2,
        )


def test_statistics_normalization_preserves_exact_receive_times_and_cutoffs():
    first = normalize_statistics_frame(_statistics_frame(), _statistics_request(1))
    second = normalize_statistics_frame(_statistics_frame(), _statistics_request(2))
    normalized = NormalizedStatistics(
        records=first.records + second.records,
        refusals=first.refusals + second.refusals,
        invalid_cohorts=first.invalid_cohorts + second.invalid_cohorts,
    )
    assert len(normalized.records) == 10
    assert normalized.refusals == ()
    assert normalized.invalid_cohorts == ()
    assert normalized.records[0].available_at.endswith("+00:00")

    early = select_complete_statistics_cohorts(
        normalized,
        decision_cutoffs={"2026-07-29": "2026-07-29T20:30:00+00:00"},
        observed_at="2026-07-29T22:00:00+00:00",
    )
    late = select_complete_statistics_cohorts(
        normalized,
        decision_cutoffs={"2026-07-29": "2026-07-29T21:30:00+00:00"},
        observed_at="2026-07-29T22:00:00+00:00",
    )
    assert len(early) == len(late) == 1
    assert early[0].summary_flag == 1
    assert late[0].summary_flag == 2
    assert early[0].available_at == "2026-07-29T20:15:00.004000+00:00"
    assert isinstance(early[0], CompleteStatisticsCohort)
    assert not isinstance(early[0], FeatureAvailabilityRecord)
    assert not hasattr(databento_pit, "select_complete_statistics_lineage")


def test_incomplete_or_deleted_statistics_never_become_a_cohort():
    incomplete = _statistics_frame(include_second=False).iloc[:-1]
    normalized = normalize_statistics_frame(incomplete, _statistics_request())
    assert select_complete_statistics_cohorts(
        normalized,
        decision_cutoffs={"2026-07-29": "2026-07-29T21:30:00+00:00"},
        observed_at="2026-07-29T22:00:00+00:00",
    ) == ()

    deleted = _statistics_frame(include_second=False)
    deleted.iloc[0, deleted.columns.get_loc("update_action")] = 2
    normalized = normalize_statistics_frame(deleted, _statistics_request())
    assert normalized.invalid_cohorts == (("2026-07-29", "NVDA", 1),)
    assert select_complete_statistics_cohorts(
        normalized,
        decision_cutoffs={"2026-07-29": "2026-07-29T21:30:00+00:00"},
        observed_at="2026-07-29T22:00:00+00:00",
    ) == ()


def test_statistics_window_is_exclusive_and_structural_errors_fail_closed():
    outside = _statistics_frame(include_second=False)
    outside["ts_event"] = pd.Timestamp("2026-07-30T20:00:00Z")
    with pytest.raises(DatabentoSourceError, match="outside the requested window"):
        normalize_statistics_frame(outside, _statistics_request())

    unknown = _statistics_frame(include_second=False)
    unknown["symbol"] = "MSFT"
    with pytest.raises(DatabentoSourceError, match="unrequested symbol"):
        normalize_statistics_frame(unknown, _statistics_request())


def test_statistics_download_is_cost_capped_and_manifest_cannot_claim_authority(
    tmp_path,
):
    costly = _FakeHistoricalClient(_statistics_frame(), cost=2.0)
    with pytest.raises(DatabentoSourceError, match="no data was downloaded"):
        fetch_statistics_snapshot(
            _statistics_request(),
            directory=tmp_path,
            max_cost_usd=1.0,
            client=costly,
            observed_at="2026-08-01T12:00:00+00:00",
        )
    assert costly.timeseries.calls == []

    client = _FakeHistoricalClient(_statistics_frame())
    snapshot = fetch_statistics_snapshot(
        _statistics_request(),
        directory=tmp_path,
        max_cost_usd=0.10,
        client=client,
        observed_at="2026-08-01T12:00:00+00:00",
    )
    manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    assert snapshot.raw_path.read_bytes() == b"statistics-dbn-fixture"
    assert manifest["validation_status"] == "accepted"
    assert manifest["exact_receive_timestamps"] is True
    assert manifest["point_in_time_data"] is False
    assert manifest["provides_point_in_time_lineage"] is False
    assert manifest["invalid_cohort_count"] == 0
    assert "unadjusted_statistics" in manifest["blockers"]


def test_reference_contract_uses_real_api_shape_and_explicit_acknowledgement(
    tmp_path,
):
    client = _FakeReferenceClient(_security_frame(), _adjustment_frame())
    security_request = _reference_request("security_master")
    assert security_request.api_kwargs()["index"] == "ts_effective"
    with pytest.raises(DatabentoSourceError, match="explicit subscription"):
        fetch_reference_snapshot(
            security_request,
            directory=tmp_path,
            acknowledge_reference_subscription=False,
            client=client,
        )
    assert client.security_master.calls == []

    snapshot = fetch_reference_snapshot(
        security_request,
        directory=tmp_path,
        acknowledge_reference_subscription=True,
        client=client,
        observed_at="2026-08-01T12:00:00+00:00",
    )
    manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    assert manifest["point_in_time_reference"] is True
    assert manifest["point_in_time_data"] is False
    assert manifest["provides_point_in_time_lineage"] is False
    assert snapshot.records[0]["security_id"] == "202"
    with pytest.raises(DatabentoSourceError, match="immutable snapshot"):
        databento_pit.write_immutable_bytes(snapshot.data_path, b"overwrite")


def test_adjustment_ex_date_is_a_date_not_an_invented_timestamp(tmp_path):
    request = _reference_request("adjustment_factors")
    records = canonical_reference_records(_adjustment_frame(), request)
    assert records[0]["ex_date"] == "2026-07-15"
    client = _FakeReferenceClient(_security_frame(), _adjustment_frame())
    snapshot = fetch_reference_snapshot(
        request,
        directory=tmp_path,
        acknowledge_reference_subscription=True,
        client=client,
        observed_at="2026-08-01T12:00:00+00:00",
    )
    assert snapshot.manifest["kind"] == "adjustment_factors"


def test_prerequisite_report_never_grants_authority_even_when_capture_is_complete(
    tmp_path,
):
    stats = fetch_statistics_snapshot(
        _statistics_request(),
        directory=tmp_path,
        max_cost_usd=0.10,
        client=_FakeHistoricalClient(_statistics_frame()),
        observed_at="2026-08-01T12:00:00+00:00",
    )
    reference_client = _FakeReferenceClient(_security_frame(), _adjustment_frame())
    security = fetch_reference_snapshot(
        _reference_request("security_master"),
        directory=tmp_path,
        acknowledge_reference_subscription=True,
        client=reference_client,
        observed_at="2026-08-01T12:00:01+00:00",
    )
    adjustments = fetch_reference_snapshot(
        _reference_request("adjustment_factors"),
        directory=tmp_path,
        acknowledge_reference_subscription=True,
        client=reference_client,
        observed_at="2026-08-01T12:00:02+00:00",
    )
    incomplete = evaluate_databento_pit_prerequisites(
        statistics_manifest=stats.manifest,
        security_master_manifest=security.manifest,
        adjustment_factors_manifest=adjustments.manifest,
        historical_universe=(),
        vintage_adjustment_application_complete=False,
    )
    assert "missing_historical_universe_membership" in incomplete.failures
    assert "missing_vintage_adjustment_application" in incomplete.failures

    complete = evaluate_databento_pit_prerequisites(
        statistics_manifest=stats.manifest,
        security_master_manifest=security.manifest,
        adjustment_factors_manifest=adjustments.manifest,
        historical_universe=(_membership(),),
        vintage_adjustment_application_complete=True,
    )
    assert complete.capture_prerequisites_complete is True
    assert complete.failures == ()
    assert complete.point_in_time_data is False
    assert complete.to_dict()["point_in_time_data"] is False

    forged_statistics = dict(stats.manifest)
    forged_statistics["source_id"] = "trusted_because_caller_said_so"
    forged_statistics["point_in_time_data"] = True
    refused = evaluate_databento_pit_prerequisites(
        statistics_manifest=forged_statistics,
        security_master_manifest=security.manifest,
        adjustment_factors_manifest=adjustments.manifest,
        historical_universe=(_membership(),),
        vintage_adjustment_application_complete=True,
    )
    assert "unexpected_statistics_source" in refused.failures
    assert "unsafe_statistics_authority_claim" in refused.failures
    assert refused.point_in_time_data is False


def test_listing_status_cannot_be_substituted_for_universe_membership():
    request = _reference_request("security_master")
    security_records = canonical_reference_records(_security_frame(), request)
    report = evaluate_databento_pit_prerequisites(
        statistics_manifest=None,
        security_master_manifest=None,
        adjustment_factors_manifest=None,
        historical_universe=security_records,
        vintage_adjustment_application_complete=False,
    )
    assert "invalid_historical_universe_membership" in report.failures
    assert report.point_in_time_data is False


def test_cli_keeps_statistics_cost_cap_and_reference_acknowledgement_separate():
    statistics = run_databento_ingest.build_parser().parse_args(
        [
            "download-statistics",
            "--symbols",
            "NVDA",
            "--start",
            "2026-07-29",
            "--end",
            "2026-07-30",
            "--max-cost-usd",
            "0.10",
            "--summary-flag",
            "2",
        ]
    )
    assert statistics.max_cost_usd == 0.10
    assert statistics.summary_flag == 2
    assert statistics.output_dir.name == "databento"

    reference = run_databento_ingest.build_parser().parse_args(
        [
            "download-reference",
            "--kind",
            "security_master",
            "--symbols",
            "NVDA",
            "--start",
            "2026-07-01",
            "--end",
            "2026-08-01",
        ]
    )
    assert reference.acknowledge_reference_subscription is False
    acknowledged = run_databento_ingest.build_parser().parse_args(
        [
            "download-reference",
            "--kind",
            "adjustment_factors",
            "--symbols",
            "NVDA",
            "--start",
            "2026-07-01",
            "--end",
            "2026-08-01",
            "--acknowledge-reference-subscription",
        ]
    )
    assert acknowledged.acknowledge_reference_subscription is True
