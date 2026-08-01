from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import ml.databento_source as databento_source_module
from ml.databento_source import (
    DailyBarsRequest,
    DatabentoDailyBarsSource,
    DatabentoSnapshotRetainedError,
    DatabentoSourceError,
    databento_is_configured,
    databento_source_version,
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
        self._data_source = _FakeDataSource()

    def to_df(self, *, price_type, pretty_ts, map_symbols):
        assert price_type == "float"
        assert pretty_ts is True
        assert map_symbols is True
        return self.frame.copy()


class _FakeReader:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeDataSource:
    def __init__(self):
        self.reader = _FakeReader()


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
        self.store = None

    def get_range(self, **kwargs):
        self.calls.append(kwargs)
        Path(kwargs["path"]).write_bytes(b"immutable-dbn-fixture")
        self.store = _FakeStore(self.frame)
        return self.store


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
    normalized = normalize_daily_bars(_raw_frame(), _request())
    frames = normalized.frames
    assert tuple(frames) == ("NVDA", "MSFT")
    assert frames["NVDA"].index.tz is None
    assert frames["NVDA"].index[0] == pd.Timestamp("2026-07-29")
    assert frames["MSFT"].loc[pd.Timestamp("2026-07-30"), "volume"] == 2_100
    assert normalized.refusals == ()

    # An inconsistent OHLC row is still never accepted -- it is now excluded
    # and recorded rather than discarding the whole paid download.
    broken = _raw_frame()
    broken.loc[broken["symbol"] == "NVDA", "high"] = 1.0
    rejected = normalize_daily_bars(broken, _request())
    assert "NVDA" not in rejected.frames
    assert "MSFT" in rejected.frames
    reasons = {item["reason"] for item in rejected.refusals}
    assert "internally inconsistent OHLC values" in reasons


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
    assert manifest["schema_version"] == "2"
    assert manifest["validation_status"] == "accepted"
    assert manifest["underfilled"] is False
    assert manifest["point_in_time_data"] is False
    assert manifest["provides_point_in_time_lineage"] is False
    assert manifest["adjustment_status"] == "unadjusted"
    assert len(manifest["raw_sha256"]) == 64
    assert "receipt/publication" in manifest["limitation"]
    assert client.timeseries.store._data_source.reader.closed
    with pytest.raises(TypeError):
        snapshot.manifest["request"]["start"] = "mutated"

    with pytest.raises(DatabentoSourceError, match="overwrite"):
        fetch_daily_bars_snapshot(
            _request(),
            directory=tmp_path,
            max_cost_usd=0.10,
            client=client,
            observed_at="2026-08-01T12:00:00+00:00",
        )


def test_snapshot_releases_dbn_file_before_temporary_cleanup(tmp_path, monkeypatch):
    client = _FakeClient(_raw_frame(), cost=0.01)
    real_unlink = Path.unlink

    def guarded_unlink(path, *args, **kwargs):
        if (
            path.name.endswith(".dbn.tmp")
            and path.exists()
            and client.timeseries.store is not None
        ):
            assert client.timeseries.store._data_source.reader.closed
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", guarded_unlink)
    snapshot = fetch_daily_bars_snapshot(
        _request(),
        directory=tmp_path,
        max_cost_usd=0.10,
        client=client,
        observed_at="2026-08-01T12:00:00+00:00",
    )
    assert snapshot.raw_path.is_file()


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
    assert source.source_manifest()["source_version"] == databento_source_version()


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


# --- Fixes to the first ingestion review (2026-08-01) --------------------
#
# Each test below pins a behavior whose absence costs the operator money,
# corrupts lineage, or leaks licensed data.


def _frame_with(overrides: dict[tuple[str, str], dict[str, float]]) -> pd.DataFrame:
    rows = []
    for ticker, base in (("NVDA", 100.0), ("MSFT", 200.0)):
        for session in ("2026-07-29", "2026-07-30"):
            row = {
                "open": base,
                "high": base + 2.0,
                "low": base - 1.0,
                "close": base + 1.0,
                "volume": 1_000.0,
                "symbol": ticker,
                "ts": f"{session}T00:00:00Z",
            }
            row.update(overrides.get((ticker, session), {}))
            rows.append(row)
    frame = pd.DataFrame(rows)
    frame.index = pd.to_datetime(frame.pop("ts"), utc=True)
    return frame


def test_zero_volume_is_a_recorded_refusal_not_a_discarded_download():
    """A halted or untraded name must not void an entire paid request."""
    normalized = normalize_daily_bars(
        _frame_with({("MSFT", "2026-07-30"): {"volume": 0.0}}), _request()
    )
    assert set(normalized.frames) == {"NVDA", "MSFT"}
    assert len(normalized.frames["MSFT"]) == 1
    assert normalized.refusals[0]["reason"] == "zero volume"
    assert normalized.refusals[0]["session"] == "2026-07-30"
    with pytest.raises(TypeError):
        normalized.refusals[0]["reason"] = "mutated"

    negative = normalize_daily_bars(
        _frame_with({("MSFT", "2026-07-30"): {"volume": -5.0}}), _request()
    )
    assert len(negative.frames["MSFT"]) == 1
    assert negative.refusals[0]["reason"] == "negative volume"
    assert negative.refusals[0]["session"] == "2026-07-30"


def test_non_positive_price_is_refused_per_row_with_its_session():
    normalized = normalize_daily_bars(
        _frame_with({("NVDA", "2026-07-29"): {"low": 0.0}}), _request()
    )
    assert len(normalized.frames["NVDA"]) == 1
    assert normalized.refusals[0] == {
        "ticker": "NVDA",
        "session": "2026-07-29",
        "reason": "non-positive price",
    }


def test_a_ticker_absent_from_the_window_does_not_void_the_request():
    """Delisted and not-yet-listed tickers must be fetchable in one request."""
    frame = _frame_with({})
    frame = frame.loc[frame["symbol"] != "MSFT"]
    normalized = normalize_daily_bars(frame, _request())
    assert set(normalized.frames) == {"NVDA"}
    assert normalized.refusals[0]["ticker"] == "MSFT"
    assert "no bars returned" in normalized.refusals[0]["reason"]


def test_a_bar_dated_off_the_nyse_calendar_is_refused_and_counted():
    """A weekend bar is the signature of a timestamp-convention bug."""
    rows = []
    for session in ("2026-07-29", "2026-08-01"):  # 2026-08-01 is a Saturday
        for ticker, base in (("NVDA", 100.0), ("MSFT", 200.0)):
            rows.append(
                {
                    "open": base, "high": base + 2.0, "low": base - 1.0,
                    "close": base + 1.0, "volume": 1_000.0, "symbol": ticker,
                    "ts": f"{session}T00:00:00Z",
                }
            )
    frame = pd.DataFrame(rows)
    frame.index = pd.to_datetime(frame.pop("ts"), utc=True)
    request = DailyBarsRequest(
        tickers=("NVDA", "MSFT"), start="2026-07-29", end="2026-08-02"
    )
    normalized = normalize_daily_bars(frame, request)
    off_calendar = [
        item
        for item in normalized.refusals
        if item["reason"] == "bar is not dated on an NYSE trading session"
    ]
    assert {item["ticker"] for item in off_calendar} == {"NVDA", "MSFT"}
    assert all(item["session"] == "2026-08-01" for item in off_calendar)
    for frame in normalized.frames.values():
        assert [stamp.date().isoformat() for stamp in frame.index] == ["2026-07-29"]


def test_rejected_snapshot_retains_the_paid_download_and_labels_it(tmp_path):
    """The download is billable; a parse failure must not delete it."""
    broken = _raw_frame()
    # Every row invalid for every ticker -> normalization raises.
    broken["high"] = 1.0
    broken["low"] = 9_999.0
    client = _FakeClient(broken, cost=0.01)
    with pytest.raises(DatabentoSnapshotRetainedError) as caught:
        fetch_daily_bars_snapshot(
            _request(),
            directory=tmp_path,
            max_cost_usd=0.10,
            client=client,
            observed_at="2026-08-01T12:00:00+00:00",
        )
    error = caught.value
    assert error.raw_path.is_file(), "the paid snapshot was deleted"
    assert error.raw_path.read_bytes() == b"immutable-dbn-fixture"
    assert "does not need to be downloaded again" in str(error)

    manifest = json.loads(error.manifest_path.read_text(encoding="utf-8"))
    assert manifest["validation_status"] == "rejected"
    assert manifest["rejection_reason"]
    assert manifest["normalized_sha256"] is None
    assert len(manifest["raw_sha256"]) == 64
    assert manifest["point_in_time_data"] is False


def test_dbn_conversion_failure_retains_paid_bytes_before_parsing(tmp_path):
    """A real-client signature/parser error occurs before bar validation."""

    class _BrokenStore(_FakeStore):
        def to_df(self, *, price_type, pretty_ts, map_symbols):
            raise TypeError("simulated Databento conversion incompatibility")

    client = _FakeClient(_raw_frame(), cost=0.01)

    def broken_range(**kwargs):
        client.timeseries.calls.append(kwargs)
        Path(kwargs["path"]).write_bytes(b"paid-dbn-before-parser")
        client.timeseries.store = _BrokenStore(_raw_frame())
        return client.timeseries.store

    client.timeseries.get_range = broken_range
    with pytest.raises(DatabentoSnapshotRetainedError) as caught:
        fetch_daily_bars_snapshot(
            _request(),
            directory=tmp_path,
            max_cost_usd=0.10,
            client=client,
            observed_at="2026-08-01T12:00:00+00:00",
        )
    assert caught.value.raw_path.read_bytes() == b"paid-dbn-before-parser"
    manifest = json.loads(caught.value.manifest_path.read_text(encoding="utf-8"))
    assert manifest["validation_status"] == "rejected"
    assert "conversion failed" in manifest["rejection_reason"]


def test_manifest_write_failure_never_deletes_paid_raw_snapshot(
    tmp_path, monkeypatch
):
    real_atomic_write = databento_source_module._atomic_write

    def fail_manifest(path, data):
        if path.name.endswith(".manifest.json"):
            raise OSError("simulated manifest storage failure")
        return real_atomic_write(path, data)

    monkeypatch.setattr(databento_source_module, "_atomic_write", fail_manifest)
    client = _FakeClient(_raw_frame(), cost=0.01)
    with pytest.raises(DatabentoSnapshotRetainedError) as caught:
        fetch_daily_bars_snapshot(
            _request(),
            directory=tmp_path,
            max_cost_usd=0.10,
            client=client,
            observed_at="2026-08-01T12:00:00+00:00",
        )
    assert caught.value.raw_path.read_bytes() == b"immutable-dbn-fixture"
    assert not caught.value.manifest_path.exists()
    assert "manifest could not be written" in str(caught.value)


def test_raw_persistence_failure_retains_download_temporary_file(
    tmp_path, monkeypatch
):
    def fail_raw_write(_path, _data):
        raise OSError("simulated snapshot storage failure")

    monkeypatch.setattr(databento_source_module, "_atomic_write", fail_raw_write)
    client = _FakeClient(_raw_frame(), cost=0.01)
    with pytest.raises(DatabentoSnapshotRetainedError) as caught:
        fetch_daily_bars_snapshot(
            _request(),
            directory=tmp_path,
            max_cost_usd=0.10,
            client=client,
            observed_at="2026-08-01T12:00:00+00:00",
        )
    assert caught.value.raw_path.name.endswith(".dbn.tmp")
    assert caught.value.raw_path.read_bytes() == b"immutable-dbn-fixture"
    assert "could not be copied" in str(caught.value)


def test_accepted_manifest_records_refusals_and_a_derived_source_version(tmp_path):
    client = _FakeClient(
        _frame_with({("MSFT", "2026-07-30"): {"volume": -1.0}}), cost=0.01
    )
    snapshot = fetch_daily_bars_snapshot(
        _request(),
        directory=tmp_path,
        max_cost_usd=0.10,
        client=client,
        observed_at="2026-08-01T12:00:00+00:00",
    )
    manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "2"
    assert manifest["validation_status"] == "accepted_with_refusals"
    assert manifest["underfilled"] is True
    assert manifest["refusal_count"] == 1
    assert manifest["refusals"][0]["reason"] == "negative volume"
    assert manifest["non_session_refusal_count"] == 0
    # Never a stale literal: the version must describe this process.
    assert manifest["source_version"] == databento_source_version()
    assert "0.81.0" not in manifest["source_version"] or _databento_installed()


def _databento_installed() -> bool:
    try:
        import databento  # noqa: F401
    except ImportError:
        return False
    return True


def test_source_version_is_derived_not_asserted():
    version = databento_source_version()
    if _databento_installed():
        import databento

        assert version == f"databento-python-{databento.__version__}"
    else:
        assert version == "databento-python-not-installed"


def test_download_refuses_an_output_directory_that_git_would_track():
    """Licensed vendor data must not be committable; git history is forever."""
    tracked = Path(__file__).resolve().parent  # tests/ is tracked
    with pytest.raises(DatabentoSourceError, match="not git-ignored"):
        run_databento_ingest.assert_output_dir_is_git_ignored(tracked)

    ignored = Path(__file__).resolve().parent.parent / "artifacts" / "databento"
    run_databento_ingest.assert_output_dir_is_git_ignored(ignored)

    # An outside path may belong to another repository whose rules are
    # unknown, so this repository cannot prove that it is safe.
    outside = run_databento_ingest._REPOSITORY_ROOT.parent / "outside-databento"
    with pytest.raises(DatabentoSourceError, match="cannot prove"):
        run_databento_ingest.assert_output_dir_is_git_ignored(outside)


def test_download_defaults_to_the_ignored_snapshot_directory():
    args = run_databento_ingest.build_parser().parse_args(
        ["download", "--symbols", "NVDA", "--start", "2026-07-29",
         "--end", "2026-07-31", "--max-cost-usd", "1.0"]
    )
    assert args.output_dir.name == "databento"
    run_databento_ingest.assert_output_dir_is_git_ignored(args.output_dir)


def _session_frame(volumes: dict[str, float]) -> pd.DataFrame:
    """One ticker across four consecutive NYSE sessions (Mon..Thu)."""
    rows = []
    for session, volume in volumes.items():
        rows.append(
            {
                "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0,
                "volume": volume, "symbol": "NVDA",
                "ts": f"{session}T00:00:00Z",
            }
        )
    frame = pd.DataFrame(rows)
    frame.index = pd.to_datetime(frame.pop("ts"), utc=True)
    return frame


def test_a_refused_interior_session_becomes_an_explicit_gap_row():
    """A hole must not be absorbed into the neighbouring return.

    ml/features.py computes returns with close.pct_change(), which counts
    rows rather than sessions, so a dropped session would silently relabel a
    two-session move as a one-session move.
    """
    request = DailyBarsRequest(
        tickers=("NVDA",), start="2026-07-27", end="2026-07-31"
    )
    normalized = normalize_daily_bars(
        _session_frame(
            {
                "2026-07-27": 1_000.0,
                "2026-07-28": 0.0,  # refused: zero volume
                "2026-07-29": 1_000.0,
                "2026-07-30": 1_000.0,
            }
        ),
        request,
    )
    frame = normalized.frames["NVDA"]
    # The session is still present, as an explicit hole.
    assert [stamp.date().isoformat() for stamp in frame.index] == [
        "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30",
    ]
    assert pd.isna(frame.loc[pd.Timestamp("2026-07-28"), "close"])
    assert frame["volume"].dtype == "Int64"
    assert pd.isna(frame.loc[pd.Timestamp("2026-07-28"), "volume"])

    # The return spanning the hole is unavailable rather than wrong.
    returns = frame["close"].pct_change(fill_method=None)
    assert pd.isna(returns.loc[pd.Timestamp("2026-07-29")])
    assert not pd.isna(returns.loc[pd.Timestamp("2026-07-30")])

    reasons = [item["reason"] for item in normalized.refusals]
    assert "zero volume" in reasons
    assert any("explicit gap" in reason for reason in reasons)


def test_gaps_are_not_padded_outside_the_ticker_s_own_span():
    """Padding before a listing or after a delisting would fabricate rows."""
    request = DailyBarsRequest(
        tickers=("NVDA",), start="2026-07-27", end="2026-07-31"
    )
    normalized = normalize_daily_bars(
        _session_frame({"2026-07-29": 1_000.0, "2026-07-30": 1_000.0}), request
    )
    assert [
        stamp.date().isoformat() for stamp in normalized.frames["NVDA"].index
    ] == ["2026-07-29", "2026-07-30"]
    assert normalized.refusals == ()


def test_manifest_reports_gap_sessions_and_excludes_them_from_content_identity(tmp_path):
    request = DailyBarsRequest(
        tickers=("NVDA",), start="2026-07-27", end="2026-07-31"
    )
    client = _FakeClient(
        _session_frame(
            {
                "2026-07-27": 1_000.0,
                "2026-07-28": 0.0,
                "2026-07-29": 1_000.0,
                "2026-07-30": 1_000.0,
            }
        ),
        cost=0.01,
    )
    snapshot = fetch_daily_bars_snapshot(
        request,
        directory=tmp_path,
        max_cost_usd=0.10,
        client=client,
        observed_at="2026-08-01T12:00:00+00:00",
    )
    manifest = json.loads(snapshot.manifest_path.read_text(encoding="utf-8"))
    assert manifest["gap_session_count"] == 1
    # The hash covers observed bars only, so it does not depend on padding.
    assert manifest["row_count"] == 3
    assert manifest["session_count"] == 3
    assert manifest["underfilled"] is True
    assert manifest["validation_status"] == "accepted_with_refusals"


def test_freeze_json_is_public_shared_api():
    """Three ml modules import it; a private name across that boundary would
    let a rename in ml/contracts.py break them silently."""
    from ml import contracts

    assert hasattr(contracts, "freeze_json")
    assert not hasattr(contracts, "_freeze_json")
    frozen = contracts.freeze_json({"a": {"b": [1, 2]}}, path="probe")
    with pytest.raises(TypeError):
        frozen["a"]["b"] = "mutated"
    assert databento_source_module.freeze_json is contracts.freeze_json
