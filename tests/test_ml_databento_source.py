from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ml.databento_source import (
    DailyBarsRequest,
    DatabentoDailyBarsSource,
    DatabentoSourceError,
    databento_is_configured,
    estimate_daily_bars_cost,
    fetch_daily_bars_snapshot,
    normalize_daily_bars,
)
from scripts import run_databento_ingest


def _raw_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0, 110.0, 200.0, 210.0],
            "high": [102.0, 112.0, 202.0, 212.0],
            "low": [99.0, 109.0, 199.0, 209.0],
            "close": [101.0, 111.0, 201.0, 211.0],
            "volume": [1_000, 1_100, 2_000, 2_100],
            "symbol": ["NVDA", "NVDA", "MSFT", "MSFT"],
        },
        index=pd.to_datetime(
            [
                "2026-07-29T00:00:00Z",
                "2026-07-30T00:00:00Z",
                "2026-07-29T00:00:00Z",
                "2026-07-30T00:00:00Z",
            ],
            utc=True,
        ),
    )


def _request() -> DailyBarsRequest:
    return DailyBarsRequest(
        tickers=("NVDA", "MSFT"), start="2026-07-29", end="2026-07-31"
    )


class _FakeStore:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame

    def to_df(self, **_kwargs):
        return self.frame.copy()


class _FakeMetadata:
    def __init__(self, cost: float):
        self.cost = cost
        self.calls = []

    def get_cost(self, **kwargs):
        self.calls.append(kwargs)
        return self.cost

    def list_datasets(self):
        return ["EQUS.SUMMARY"]


class _FakeTimeseries:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.calls = []

    def get_range(self, **kwargs):
        self.calls.append(kwargs)
        Path(kwargs["path"]).write_bytes(b"immutable-dbn-fixture")
        return _FakeStore(self.frame)


class _FakeClient:
    def __init__(self, frame: pd.DataFrame, *, cost: float = 0.01):
        self.metadata = _FakeMetadata(cost)
        self.timeseries = _FakeTimeseries(frame)


def test_request_is_strict_and_uses_an_exclusive_end():
    request = _request()
    assert request.api_kwargs() == {
        "dataset": "EQUS.SUMMARY",
        "schema": "ohlcv-1d",
        "stype_in": "raw_symbol",
        "symbols": ["NVDA", "MSFT"],
        "start": "2026-07-29",
        "end": "2026-07-31",
    }
    with pytest.raises(DatabentoSourceError, match="end must be after start"):
        DailyBarsRequest(tickers=("NVDA",), start="2026-07-31", end="2026-07-31")
    with pytest.raises(DatabentoSourceError, match="canonical uppercase"):
        DailyBarsRequest(tickers=("nvda",), start="2026-07-29", end="2026-07-31")
    with pytest.raises(DatabentoSourceError, match="only supports dataset"):
        DailyBarsRequest(
            tickers=("NVDA",),
            start="2026-07-29",
            end="2026-07-31",
            dataset="XNAS.ITCH",
        )


def test_configuration_check_never_needs_to_return_the_secret(monkeypatch):
    monkeypatch.setenv("DATABENTO_API_KEY", "db-process-secret")
    assert not databento_is_configured({})
    assert databento_is_configured({"DATABENTO_API_KEY": "db-secret"})
    result = run_databento_ingest.command_status()
    assert result["secret_printed"] is False


def test_cost_estimate_uses_exactly_the_download_query():
    client = _FakeClient(_raw_frame(), cost=0.0125)
    assert estimate_daily_bars_cost(_request(), client=client) == 0.0125
    assert client.metadata.calls == [_request().api_kwargs()]


def test_cost_cap_refuses_before_any_download(tmp_path):
    client = _FakeClient(_raw_frame(), cost=2.0)
    with pytest.raises(DatabentoSourceError, match="no data was downloaded"):
        fetch_daily_bars_snapshot(
            _request(),
            directory=tmp_path,
            max_cost_usd=1.0,
            client=client,
            observed_at="2026-08-01T12:00:00+00:00",
        )
    assert client.timeseries.calls == []
    assert list(tmp_path.iterdir()) == []


def test_normalization_splits_symbols_and_validates_ohlcv():
    frames = normalize_daily_bars(_raw_frame(), _request())
    assert tuple(frames) == ("NVDA", "MSFT")
    assert frames["NVDA"].index.tz is None
    assert frames["NVDA"].index[0] == pd.Timestamp("2026-07-29")
    assert frames["MSFT"].loc[pd.Timestamp("2026-07-30"), "volume"] == 2_100

    broken = _raw_frame()
    broken.loc[broken["symbol"] == "NVDA", "high"] = 1.0
    with pytest.raises(DatabentoSourceError, match="inconsistent OHLC"):
        normalize_daily_bars(broken, _request())


def test_snapshot_is_immutable_hash_bound_and_fail_closed(tmp_path):
    client = _FakeClient(_raw_frame(), cost=0.01)
    snapshot = fetch_daily_bars_snapshot(
        _request(),
        directory=tmp_path,
        max_cost_usd=0.10,
        client=client,
        observed_at="2026-08-01T12:00:00+00:00",
    )
    assert snapshot.raw_path.read_bytes() == b"immutable-dbn-fixture"
    manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    assert manifest["row_count"] == 4
    assert manifest["session_count"] == 2
    assert manifest["point_in_time_data"] is False
    assert manifest["provides_point_in_time_lineage"] is False
    assert manifest["adjustment_status"] == "unadjusted"
    assert len(manifest["raw_sha256"]) == 64
    assert "receipt/publication" in manifest["limitation"]

    with pytest.raises(DatabentoSourceError, match="overwrite"):
        fetch_daily_bars_snapshot(
            _request(),
            directory=tmp_path,
            max_cost_usd=0.10,
            client=client,
            observed_at="2026-08-01T12:00:00+00:00",
        )


def test_ohlcv_only_source_cannot_fabricate_point_in_time_lineage():
    source = DatabentoDailyBarsSource()
    assert source.provides_point_in_time_lineage is False
    assert source.feature_records(
        tickers=["NVDA"], start_session="2026-01-01", end_session="2026-07-31"
    ) == ()
    assert source.universe_membership(
        universe_id="tech-v1",
        start_session="2026-01-01",
        end_session="2026-07-31",
    ) == ()
    assert source.source_manifest()["provides_point_in_time_lineage"] == "false"


def test_cli_reports_errors_without_leaking_credentials(monkeypatch, capsys):
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    exit_code = run_databento_ingest.main(
        [
            "estimate",
            "--symbols",
            "NVDA",
            "--start",
            "2026-07-29",
            "--end",
            "2026-07-31",
        ]
    )
    output = capsys.readouterr().out
    assert exit_code == 1
    assert "not configured" in output
    assert "db-" not in output
