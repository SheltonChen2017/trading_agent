from __future__ import annotations

import inspect
import io
import json
import os
import re
import shutil
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

import scripts.capture_arv2_sharadar as adapter
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes
from scripts.capture_arv2_sharadar import (
    ACTIONS_AVAILABILITY,
    FUNDAMENTALS_ADMITTED_DIMENSION,
    FUNDAMENTALS_AVAILABILITY,
    PRODUCTION_TRANSPORT,
    TEST_TRANSPORT,
    TICKERS_AVAILABILITY,
    REVIEWED_FUNDAMENTAL_DIMENSIONS,
    SharadarCaptureError,
    SharadarDataset,
    _capture_sharadar_history_for_test,
    _visit_authenticated_sharadar_capture_rows_for_bridge,
    capture_sharadar_history,
    load_sharadar_capture_artifact,
)


KEY = "offline-test-sharadar-key-NEVER-REAL"


TICKERS = (
    b"table,ticker,permaticker,isdelisted,name,category,exchange,sector,industry,"
    b"figi,firstpricedate,lastpricedate\n"
    b"fundamentals,AAA,100001,N,Active Corp,Domestic Common Stock,NASDAQ,"
    b"Technology,Software,BBG000AAA111,2010-01-04,\n"
    b"fundamentals,OLD,100002,Y,Old Corp,Domestic Common Stock,NYSE,"
    b"Industrials,Machinery,BBG000OLD222,2000-01-03,2020-12-31\n"
)
ACTIONS = (
    b"date,action,ticker,name,value,contraticker,contraname\n"
    b"2021-06-01,delisted,OLD,Old Corp,,,\n"
)
FUNDAMENTALS = (
    b"ticker,dimension,calendardate,date,reportperiod,lastupdated,"
    b"sharesbas,equityusd,revenueusd\n"
    b"AAA,ART,2021-12-31,2022-02-10,2021-12-31,2022-02-10,"
    b"1000000,5000000,9000000\n"
    b"AAA,ART,2020-12-31,2021-02-10,2020-12-31,2021-02-10,"
    b"900000,4500000,8000000\n"
)


def _zip_bytes(
    dataset: SharadarDataset,
    *,
    csv_bytes: bytes | None = None,
    member_name: str | None = None,
    extras: tuple[tuple[zipfile.ZipInfo | str, bytes], ...] = (),
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    defaults = {
        SharadarDataset.TICKERS: TICKERS,
        SharadarDataset.ACTIONS: ACTIONS,
        SharadarDataset.FUNDAMENTALS: FUNDAMENTALS,
    }
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=compression, allowZip64=True) as archive:
        archive.writestr(member_name or f"SHARADAR_{dataset.value.upper()}.csv", csv_bytes or defaults[dataset])
        for name, content in extras:
            archive.writestr(name, content)
    return payload.getvalue()


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        prepared_url: str | None = None,
        response_url: str | None = None,
        method: str = "GET",
        chunk_sizes: tuple[int, ...] = (),
    ) -> None:
        self.body = body
        self.status_code = status
        self.headers = headers or {}
        self.prepared_url_override = prepared_url
        self.response_url_override = response_url
        self.method = method
        self.chunk_sizes = chunk_sizes
        self.request = None
        self.url = None
        self.close_count = 0

    @property
    def content(self) -> bytes:
        raise AssertionError("capture must not materialize Response.content")

    def iter_content(self, *, chunk_size: int):
        if self.chunk_sizes:
            position = 0
            for size in self.chunk_sizes:
                yield self.body[position : position + size]
                position += size
            if position < len(self.body):
                yield self.body[position:]
            return
        for position in range(0, len(self.body), max(1, chunk_size)):
            yield self.body[position : position + chunk_size]

    def close(self) -> None:
        self.close_count += 1


class FakeSession:
    def __init__(self, responses: list[FakeResponse | BaseException]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []
        self.served: list[FakeResponse] = []
        self.close_count = 0

    def get(self, url: str, **kwargs):
        params = kwargs.get("params")
        prepared = url
        if params:
            prepared += ("&" if "?" in prepared else "?") + urlencode(params)
        self.calls.append({"url": url, **kwargs, "prepared": prepared})
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        item.request = SimpleNamespace(
            method=item.method,
            url=item.prepared_url_override or prepared,
        )
        item.url = item.response_url_override or prepared
        self.served.append(item)
        return item

    def close(self) -> None:
        self.close_count += 1


class Clock:
    def __init__(self) -> None:
        self.values = iter(
            (
                datetime(2026, 9, 12, 8, 0, 0, 1, tzinfo=timezone.utc),
                datetime(2026, 9, 12, 8, 0, 1, 2, tzinfo=timezone.utc),
            )
        )

    def __call__(self) -> datetime:
        return next(self.values)


def _valid_responses() -> list[FakeResponse]:
    return [
        FakeResponse(_zip_bytes(dataset), chunk_sizes=(7, 11, 13))
        for dataset in adapter.DATASET_ORDER
    ]


def _capture(tmp_path: Path, session: FakeSession | None = None):
    session = session or FakeSession(_valid_responses())
    result = _capture_sharadar_history_for_test(
        artifact_root=tmp_path / "capture",
        session=session,
        clock=Clock(),
        api_key=KEY,
    )
    return result, session


def _manifest(result) -> dict[str, object]:
    return json.loads((result.artifact_path / adapter.MANIFEST_FILENAME).read_text())


def _exact_error(message: str) -> str:
    return f"^{re.escape(message)}$"


def test_streaming_bridge_visitor_authenticates_and_visits_every_row(tmp_path):
    result, _ = _capture(tmp_path)
    observed: list[tuple[SharadarDataset, str, int, dict[str, str]]] = []

    def visit(dataset, member, ordinal, row):
        assert type(row) is dict
        observed.append((dataset, member.name, ordinal, row))

    summary = _visit_authenticated_sharadar_capture_rows_for_bridge(
        result.artifact_path,
        expected_transport=adapter.TEST_TRANSPORT,
        visit_row=visit,
    )

    assert summary == result
    assert [(dataset, ordinal) for dataset, _member, ordinal, _row in observed] == [
        (SharadarDataset.TICKERS, 0),
        (SharadarDataset.TICKERS, 1),
        (SharadarDataset.ACTIONS, 0),
        (SharadarDataset.FUNDAMENTALS, 0),
        (SharadarDataset.FUNDAMENTALS, 1),
    ]
    assert observed[0][3]["ticker"] == "AAA"
    assert observed[-1][3]["dimension"] == "ART"


def test_streaming_bridge_visitor_rejects_arguments_before_filesystem(tmp_path):
    missing = tmp_path / "never-opened"
    with pytest.raises(
        SharadarCaptureError,
        match=_exact_error("expected capture transport is not reviewed"),
    ):
        _visit_authenticated_sharadar_capture_rows_for_bridge(
            missing,
            expected_transport="unreviewed",
            visit_row=lambda *_args: None,
        )
    with pytest.raises(
        SharadarCaptureError,
        match=_exact_error("capture row visitor must be callable"),
    ):
        _visit_authenticated_sharadar_capture_rows_for_bridge(
            missing,
            expected_transport=adapter.TEST_TRANSPORT,
            visit_row=None,
        )
    assert not missing.exists()


def test_streaming_bridge_visitor_authenticates_all_archives_before_callback(
    tmp_path,
):
    result, _ = _capture(tmp_path)
    actions = result.artifact_path / result.archives[1].archive_file
    corrupted = bytearray(actions.read_bytes())
    corrupted[len(corrupted) // 2] ^= 1
    actions.write_bytes(corrupted)
    callbacks = 0

    def visit(*_args):
        nonlocal callbacks
        callbacks += 1

    with pytest.raises(
        SharadarCaptureError,
        match=_exact_error(
            "archive bytes do not match manifest before visitation"
        ),
    ):
        _visit_authenticated_sharadar_capture_rows_for_bridge(
            result.artifact_path,
            expected_transport=adapter.TEST_TRANSPORT,
            visit_row=visit,
        )
    assert callbacks == 0


def test_streaming_bridge_visitor_propagates_callback_failure_unchanged(tmp_path):
    result, _ = _capture(tmp_path)
    failure = RuntimeError("consumer refused a Sharadar row")
    callbacks = 0

    def visit(*_args):
        nonlocal callbacks
        callbacks += 1
        raise failure

    with pytest.raises(RuntimeError) as captured:
        _visit_authenticated_sharadar_capture_rows_for_bridge(
            result.artifact_path,
            expected_transport=adapter.TEST_TRANSPORT,
            visit_row=visit,
        )
    assert captured.value is failure
    assert callbacks == 1


def test_streaming_bridge_visitor_does_not_reclassify_callback_oserror(tmp_path):
    result, _ = _capture(tmp_path)
    failure = OSError("consumer-owned output failed")

    def visit(*_args):
        raise failure

    with pytest.raises(OSError) as captured:
        _visit_authenticated_sharadar_capture_rows_for_bridge(
            result.artifact_path,
            expected_transport=adapter.TEST_TRANSPORT,
            visit_row=visit,
        )
    assert captured.value is failure


def test_streaming_bridge_visitor_never_delivers_post_auth_source_mutation(
    tmp_path,
):
    session = FakeSession(
        [
            FakeResponse(
                _zip_bytes(dataset, compression=zipfile.ZIP_STORED)
            )
            for dataset in adapter.DATASET_ORDER
        ]
    )
    result, _ = _capture(tmp_path, session)
    actions = result.artifact_path / result.archives[1].archive_file
    callbacks = 0
    action_tickers: list[str] = []

    def visit(dataset, _member, _ordinal, row):
        nonlocal callbacks
        callbacks += 1
        if callbacks == 1:
            payload = actions.read_bytes()
            assert b",OLD," in payload
            with actions.open("r+b") as target:
                target.write(payload.replace(b",OLD,", b",BAD,", 1))
                target.flush()
                os.fsync(target.fileno())
        if dataset is SharadarDataset.ACTIONS:
            action_tickers.append(row["ticker"])

    with pytest.raises(
        SharadarCaptureError,
        match=_exact_error(
            "Sharadar actions archive identity changed after visitation"
        ),
    ):
        _visit_authenticated_sharadar_capture_rows_for_bridge(
            result.artifact_path,
            expected_transport=adapter.TEST_TRANSPORT,
            visit_row=visit,
        )
    assert callbacks == 5
    assert action_tickers == ["OLD"]


def test_streaming_bridge_visitor_rechecks_visited_leaf_identity(tmp_path):
    result, _ = _capture(tmp_path)
    target = result.artifact_path / result.archives[0].archive_file
    moved = result.artifact_path.parent / (target.name + ".moved")
    callbacks = 0

    def visit(*_args):
        nonlocal callbacks
        callbacks += 1
        if callbacks == 1:
            target.rename(moved)
            shutil.copyfile(moved, target)
            target.chmod(0o600)

    with pytest.raises(
        SharadarCaptureError,
        match=_exact_error(
            "Sharadar tickers archive identity changed after visitation"
        ),
    ):
        _visit_authenticated_sharadar_capture_rows_for_bridge(
            result.artifact_path,
            expected_transport=adapter.TEST_TRANSPORT,
            visit_row=visit,
        )
    assert callbacks == 5


def test_streaming_bridge_visitor_rechecks_artifact_path_identity(tmp_path):
    result, _ = _capture(tmp_path)
    original = result.artifact_path
    moved = original.with_name(original.name + ".moved")
    callbacks = 0

    def visit(*_args):
        nonlocal callbacks
        callbacks += 1
        if callbacks == 1:
            original.rename(moved)
            original.mkdir(mode=0o700)
            original.chmod(0o700)

    with pytest.raises(
        SharadarCaptureError,
        match=_exact_error(
            "capture artifact path identity changed during visitation"
        ),
    ):
        _visit_authenticated_sharadar_capture_rows_for_bridge(
            original,
            expected_transport=adapter.TEST_TRANSPORT,
            visit_row=visit,
        )
    assert callbacks == 5


def _rewrite_manifest(path: Path, mutator) -> None:
    manifest_path = path / adapter.MANIFEST_FILENAME
    value = json.loads(manifest_path.read_text())
    mutator(value)
    payload = canonical_json_bytes(value)
    manifest_path.write_bytes(payload)
    (path / adapter.MANIFEST_DIGEST_FILENAME).write_text(sha256_bytes(payload) + "\n")


def test_success_streams_three_full_exports_and_reloads_deterministically(tmp_path):
    result, session = _capture(tmp_path)
    reloaded = load_sharadar_capture_artifact(result.artifact_path)

    assert result == reloaded
    assert result.capture_transport == TEST_TRANSPORT
    assert [item.dataset for item in result.archives] == list(adapter.DATASET_ORDER)
    assert [item.row_count for item in result.archives] == [2, 1, 2]
    assert all(call["stream"] is True for call in session.calls)
    assert all(call["allow_redirects"] is False for call in session.calls)
    assert all(response.close_count == 1 for response in session.served)
    assert session.close_count == 0
    assert all(call["params"]["years"] == "full" for call in session.calls)
    assert "dimension" not in session.calls[2]["params"]
    assert result.archives[2].fundamental_dimension_counts == (("ART", 2),)


def test_manifest_is_honest_about_snapshot_and_nonconstruction_boundaries(tmp_path):
    result, _ = _capture(tmp_path)
    manifest = _manifest(result)

    assert manifest["tickers_availability_semantics"] == TICKERS_AVAILABILITY
    assert manifest["actions_availability_semantics"] == ACTIONS_AVAILABILITY
    assert manifest["fundamentals_availability_semantics"] == FUNDAMENTALS_AVAILABILITY
    assert manifest["fundamentals_archive_dimensions"] == ["ART"]
    assert manifest["fundamentals_bulk_request_unfiltered_by_dimension"] is True
    assert (
        manifest["fundamentals_downstream_admitted_dimension"]
        == FUNDAMENTALS_ADMITTED_DIMENSION
    )
    assert manifest["fundamentals_non_admitted_dimensions_retained"] is False
    assert manifest["tickers_contains_active_and_delisted"] is True
    assert manifest["tickers_unknown_delisting_flag_row_count"] == 0
    assert manifest["pit_security_master_constructed"] is False
    assert manifest["terminal_payoff_constructed"] is False
    assert manifest["backtest_input_constructed"] is False
    assert manifest["provider_io_read_only"] is False


def test_key_and_request_or_redirect_urls_are_not_persisted(tmp_path):
    redirect = "https://bucket.s3.amazonaws.com/arv2/tickers.zip?X-Amz-Signature=secret"
    responses = [
        FakeResponse(b"", status=302, headers={"Location": redirect}),
        FakeResponse(_zip_bytes(SharadarDataset.TICKERS)),
        FakeResponse(_zip_bytes(SharadarDataset.ACTIONS)),
        FakeResponse(_zip_bytes(SharadarDataset.FUNDAMENTALS)),
    ]
    result, _ = _capture(tmp_path, FakeSession(responses))
    all_bytes = b"".join(
        item.read_bytes()
        for item in result.artifact_path.iterdir()
        if item.is_file()
    )
    assert KEY.encode() not in all_bytes
    assert redirect.encode() not in all_bytes
    assert b"X-Amz-Signature" not in all_bytes
    assert _manifest(result)["api_key_persisted"] is False
    assert _manifest(result)["redirect_url_persisted"] is False
    assert result.archives[0].redirect_used is True


def test_current_sharadar_bulk_redirect_host_is_exactly_allowlisted():
    url = (
        "https://static-sharadar.nyc3.digitaloceanspaces.com/"
        "exports/tickers.zip?signature=fixture"
    )
    assert adapter._validate_redirect_url(url, KEY) == url
    with pytest.raises(SharadarCaptureError, match="host is not reviewed"):
        adapter._validate_redirect_url(
            "https://lookalike-static-sharadar.nyc3.digitaloceanspaces.com/"
            "exports/tickers.zip?signature=fixture",
            KEY,
        )


def test_public_signature_has_no_session_clock_or_key_injection():
    parameters = inspect.signature(capture_sharadar_history).parameters
    assert set(parameters) == {"artifact_root"}
    assert "_capture_sharadar_history_for_test" not in adapter.__all__


def test_public_missing_credential_refuses_before_session_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "REPOSITORY_ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(
        adapter,
        "_api_key",
        lambda: (_ for _ in ()).throw(SharadarCaptureError("missing")),
    )
    monkeypatch.setattr(
        adapter,
        "_new_session",
        lambda: (_ for _ in ()).throw(AssertionError("session must not be created")),
    )
    with pytest.raises(SharadarCaptureError, match="missing"):
        capture_sharadar_history(artifact_root=tmp_path / "capture")


def test_public_owned_session_closes_before_production_publication(tmp_path, monkeypatch):
    session = FakeSession(_valid_responses())
    monkeypatch.setattr(adapter, "REPOSITORY_ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(adapter, "_api_key", lambda: "real-looking-key-not-a-secret")
    monkeypatch.setattr(adapter, "_new_session", lambda: session)

    result = capture_sharadar_history(artifact_root=tmp_path / "capture")

    assert session.close_count == 1
    assert result.capture_transport == PRODUCTION_TRANSPORT
    assert _manifest(result)["provider_io_read_only"] is True


def test_public_refuses_outside_repository_artifacts_before_credential(monkeypatch, tmp_path):
    monkeypatch.setattr(
        adapter,
        "_api_key",
        lambda: (_ for _ in ()).throw(AssertionError("credential must not be read")),
    )
    with pytest.raises(SharadarCaptureError, match="beneath repository artifacts"):
        capture_sharadar_history(artifact_root=tmp_path)


def test_initial_prepared_request_must_preserve_key_and_full_query(tmp_path):
    bad = FakeResponse(
        _zip_bytes(SharadarDataset.TICKERS),
        prepared_url="https://api.sharadar.com/v1.0/data/tickers?years=full",
    )
    session = FakeSession([bad, *_valid_responses()[1:]])
    with pytest.raises(SharadarCaptureError, match="frozen query"):
        _capture(tmp_path, session)
    assert bad.close_count == 1
    assert KEY not in str(pytest.ExceptionInfo)


def test_response_url_must_match_prepared_query(tmp_path):
    bad = FakeResponse(
        _zip_bytes(SharadarDataset.TICKERS),
        response_url="https://api.sharadar.com/v1.0/data/tickers?years=10",
    )
    with pytest.raises(SharadarCaptureError, match="frozen query"):
        _capture(tmp_path, FakeSession([bad, *_valid_responses()[1:]]))


@pytest.mark.parametrize(
    "location, message",
    (
        ("http://bucket.s3.amazonaws.com/file.zip", "HTTPS"),
        ("https://127.0.0.1/file.zip", "IP literal"),
        ("https://evil.example/file.zip", "host is not reviewed"),
        (f"https://bucket.s3.amazonaws.com/file.zip?token={KEY}", "echoed the API key"),
    ),
)
def test_unsafe_redirects_refuse_without_second_request(tmp_path, location, message):
    first = FakeResponse(b"", status=302, headers={"Location": location})
    session = FakeSession([first])
    with pytest.raises(SharadarCaptureError, match=message):
        _capture(tmp_path, session)
    assert len(session.calls) == 1
    assert first.close_count == 1


def test_redirected_prepared_request_must_preserve_signed_url(tmp_path):
    location = "https://bucket.s3.amazonaws.com/file.zip?X-Amz-Signature=signed"
    first = FakeResponse(b"", status=302, headers={"Location": location})
    final = FakeResponse(
        _zip_bytes(SharadarDataset.TICKERS),
        prepared_url="https://bucket.s3.amazonaws.com/file.zip",
    )
    with pytest.raises(SharadarCaptureError, match="signed URL semantics"):
        _capture(tmp_path, FakeSession([first, final]))
    assert first.close_count == final.close_count == 1


def test_provider_exception_is_redacted_and_closes_owned_session(tmp_path, monkeypatch):
    session = FakeSession([RuntimeError(f"request URL included api_key={KEY}")])
    monkeypatch.setattr(adapter, "REPOSITORY_ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(adapter, "_api_key", lambda: "real-looking-key-not-a-secret")
    monkeypatch.setattr(adapter, "_new_session", lambda: session)
    with pytest.raises(SharadarCaptureError) as caught:
        capture_sharadar_history(artifact_root=tmp_path / "capture")
    assert "real-looking" not in str(caught.value)
    assert "details redacted" in str(caught.value)
    assert session.close_count == 1


def test_stream_cap_applies_before_complete_response_is_accumulated(tmp_path, monkeypatch):
    archive = _zip_bytes(SharadarDataset.TICKERS)
    monkeypatch.setattr(adapter, "MAX_ARCHIVE_BYTES", len(archive) - 1)
    response = FakeResponse(archive, chunk_sizes=(1, len(archive) - 1))
    with pytest.raises(SharadarCaptureError, match="byte limit"):
        _capture(tmp_path, FakeSession([response]))
    assert response.close_count == 1


def test_aggregate_archive_cap_refuses_second_archive(tmp_path, monkeypatch):
    responses = _valid_responses()
    first_size = len(responses[0].body)
    monkeypatch.setattr(adapter, "MAX_TOTAL_ARCHIVE_BYTES", first_size + 1)
    with pytest.raises(SharadarCaptureError, match="byte limit"):
        _capture(tmp_path, FakeSession(responses))


def test_aggregate_member_cap_applies_across_archives(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "MAX_TOTAL_ZIP_MEMBERS", 2)
    with pytest.raises(SharadarCaptureError, match="member inventory"):
        _capture(tmp_path)


def test_credential_echo_across_stream_chunks_refuses(tmp_path):
    body = b"PK" + KEY.encode() + b"not-a-zip"
    split = 2 + len(KEY) // 2
    response = FakeResponse(body, chunk_sizes=(split, len(body) - split))
    with pytest.raises(SharadarCaptureError, match="echoed the API key"):
        _capture(tmp_path, FakeSession([response]))


def test_stream_exception_does_not_retain_secret_bearing_cause(tmp_path):
    class BrokenResponse(FakeResponse):
        def iter_content(self, *, chunk_size: int):
            raise RuntimeError(f"stream failed for api_key={KEY}")
            yield b""  # pragma: no cover

    with pytest.raises(SharadarCaptureError) as caught:
        _capture(tmp_path, FakeSession([BrokenResponse(b"")]))
    assert caught.value.__cause__ is None
    assert KEY not in str(caught.value)


@pytest.mark.parametrize("member", ("../escape.csv", "/absolute.csv", "dir/data.csv", "dir\\data.csv"))
def test_unsafe_zip_member_paths_refuse(tmp_path, member):
    archive = _zip_bytes(SharadarDataset.TICKERS, member_name=member)
    with pytest.raises(SharadarCaptureError, match="unsafe or unsupported"):
        _capture(tmp_path, FakeSession([FakeResponse(archive)]))


def test_zip_symlink_member_refuses(tmp_path):
    info = zipfile.ZipInfo("SHARADAR_TICKERS.csv")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    archive = _zip_bytes(
        SharadarDataset.TICKERS,
        member_name="base.csv",
        extras=((info, b"target.csv"),),
    )
    with pytest.raises(SharadarCaptureError, match="unsafe or unsupported"):
        _capture(tmp_path, FakeSession([FakeResponse(archive)]))


def test_zip_expansion_ratio_refuses_bomb_like_member(tmp_path, monkeypatch):
    archive = _zip_bytes(SharadarDataset.TICKERS, csv_bytes=TICKERS + b"x" * 500_000)
    monkeypatch.setattr(adapter, "MAX_COMPRESSION_RATIO", 2)
    with pytest.raises(SharadarCaptureError, match="expansion"):
        _capture(tmp_path, FakeSession([FakeResponse(archive)]))


def test_zip_member_limit_refuses(tmp_path, monkeypatch):
    extras = tuple((f"part-{index}.csv", TICKERS) for index in range(3))
    archive = _zip_bytes(SharadarDataset.TICKERS, extras=extras)
    monkeypatch.setattr(adapter, "MAX_ZIP_MEMBERS", 2)
    with pytest.raises(SharadarCaptureError, match="inventory"):
        _capture(tmp_path, FakeSession([FakeResponse(archive)]))


def test_csv_missing_required_field_refuses(tmp_path):
    archive = _zip_bytes(
        SharadarDataset.TICKERS,
        csv_bytes=b"ticker,isdelisted\nAAA,N\nOLD,Y\n",
    )
    with pytest.raises(SharadarCaptureError, match="required Sharadar fields"):
        _capture(tmp_path, FakeSession([FakeResponse(archive)]))


def test_tickers_must_demonstrate_active_and_delisted_coverage(tmp_path):
    archive = _zip_bytes(
        SharadarDataset.TICKERS,
        csv_bytes=TICKERS.split(b"fundamentals,OLD", 1)[0],
    )
    with pytest.raises(SharadarCaptureError, match="active and delisted"):
        _capture(tmp_path, FakeSession([FakeResponse(archive)]))


def test_blank_tickers_delisting_flag_is_retained_as_authenticated_unknown(tmp_path):
    tickers = TICKERS + (
        b"fundamentals,UNK,100003,,Unknown State Corp,Domestic Common Stock,NYSE,"
        b"Industrials,Machinery,BBG000UNK333,2015-01-02,\n"
    )
    responses = [
        FakeResponse(_zip_bytes(SharadarDataset.TICKERS, csv_bytes=tickers)),
        *_valid_responses()[1:],
    ]
    result, _ = _capture(tmp_path, FakeSession(responses))
    reloaded = load_sharadar_capture_artifact(result.artifact_path)
    tickers_archive = reloaded.archives[0]

    assert tickers_archive.active_ticker_row_count == 1
    assert tickers_archive.delisted_ticker_row_count == 1
    assert tickers_archive.unknown_ticker_delisting_flag_row_count == 1
    assert _manifest(result)["tickers_unknown_delisting_flag_row_count"] == 1


def test_nonblank_unreviewed_tickers_delisting_flag_still_refuses(tmp_path):
    tickers = TICKERS.replace(b",AAA,100001,N,", b",AAA,100001,MAYBE,")
    with pytest.raises(SharadarCaptureError, match="delisting flag is unreviewed"):
        _capture(
            tmp_path,
            FakeSession(
                [FakeResponse(_zip_bytes(SharadarDataset.TICKERS, csv_bytes=tickers))]
            ),
        )


def test_fundamentals_refuse_an_unreviewed_dimension(tmp_path):
    bad = FUNDAMENTALS.replace(b",ART,", b",BAD,")
    responses = _valid_responses()[:2] + [
        FakeResponse(_zip_bytes(SharadarDataset.FUNDAMENTALS, csv_bytes=bad))
    ]
    with pytest.raises(SharadarCaptureError, match="unreviewed dimension"):
        _capture(tmp_path, FakeSession(responses))


def test_fundamentals_require_the_admitted_art_dimension(tmp_path):
    non_art = FUNDAMENTALS.replace(b",ART,", b",MRY,")
    responses = _valid_responses()[:2] + [
        FakeResponse(_zip_bytes(SharadarDataset.FUNDAMENTALS, csv_bytes=non_art))
    ]
    with pytest.raises(
        SharadarCaptureError,
        match=re.escape(
            "FUNDAMENTALS archive does not contain the admitted ART dimension"
        ),
    ):
        _capture(tmp_path, FakeSession(responses))


def test_fundamentals_retain_and_authenticate_all_reviewed_dimensions(tmp_path):
    extra_dimensions = b"".join(
        (
            f"AAA,{dimension},2021-12-31,2022-02-10,2021-12-31,"
            "2022-02-10,1000000,5000000,9000000\n"
        ).encode("ascii")
        for dimension in REVIEWED_FUNDAMENTAL_DIMENSIONS
        if dimension != FUNDAMENTALS_ADMITTED_DIMENSION
    )
    mixed = FUNDAMENTALS + extra_dimensions
    responses = _valid_responses()[:2] + [
        FakeResponse(_zip_bytes(SharadarDataset.FUNDAMENTALS, csv_bytes=mixed))
    ]

    result, _ = _capture(tmp_path, FakeSession(responses))
    reloaded = load_sharadar_capture_artifact(result.artifact_path)
    manifest = _manifest(result)

    assert result == reloaded
    assert REVIEWED_FUNDAMENTAL_DIMENSIONS == (
        "ARQ",
        "ART",
        "ARY",
        "MRQ",
        "MRT",
        "MRY",
    )
    assert reloaded.archives[2].fundamental_dimension_counts == tuple(
        (dimension, 2 if dimension == "ART" else 1)
        for dimension in REVIEWED_FUNDAMENTAL_DIMENSIONS
    )
    assert manifest["fundamentals_archive_dimensions"] == list(
        REVIEWED_FUNDAMENTAL_DIMENSIONS
    )
    assert manifest["fundamentals_non_admitted_dimensions_retained"] is True


def test_reload_recomputes_the_fundamental_dimension_census(tmp_path):
    mixed = FUNDAMENTALS + (
        b"AAA,MRY,2021-12-31,2022-02-10,2021-12-31,2022-02-10,"
        b"1000000,5000000,9000000\n"
    )
    responses = _valid_responses()[:2] + [
        FakeResponse(_zip_bytes(SharadarDataset.FUNDAMENTALS, csv_bytes=mixed))
    ]
    result, _ = _capture(tmp_path, FakeSession(responses))

    def forge_dimension_counts(value):
        value["archives"][2]["fundamental_dimension_counts"] = [
            {"dimension": "ART", "row_count": 1},
            {"dimension": "MRY", "row_count": 2},
        ]
        identity = adapter._capture_identity_document(
            value["capture_started_at"],
            value["capture_completed_at"],
            value["capture_transport"],
            tuple(
                adapter._parse_archive(raw, role)
                for raw, role in zip(
                    value["archives"], adapter.DATASET_ORDER, strict=True
                )
            ),
        )
        capture_sha256 = sha256_bytes(canonical_json_bytes(identity))
        value["capture_sha256"] = capture_sha256
        value["capture_id"] = f"arv2-sharadar-source-{capture_sha256[:16]}"

    _rewrite_manifest(result.artifact_path, forge_dimension_counts)

    with pytest.raises(SharadarCaptureError, match="member census differs"):
        load_sharadar_capture_artifact(result.artifact_path)


@pytest.mark.parametrize(
    "field, replacement, message",
    (
        ("fundamentals_archive_dimensions", ["ART"], "dimension inventory"),
        (
            "fundamentals_bulk_request_unfiltered_by_dimension",
            False,
            "boundary changed",
        ),
        (
            "fundamentals_downstream_admitted_dimension",
            "MRY",
            "changed",
        ),
        (
            "fundamentals_non_admitted_dimensions_retained",
            False,
            "boundary changed",
        ),
    ),
)
def test_reload_refuses_rehashed_fundamental_dimension_claims(
    tmp_path, field, replacement, message
):
    mixed = FUNDAMENTALS + (
        b"AAA,MRY,2021-12-31,2022-02-10,2021-12-31,2022-02-10,"
        b"1000000,5000000,9000000\n"
    )
    responses = _valid_responses()[:2] + [
        FakeResponse(_zip_bytes(SharadarDataset.FUNDAMENTALS, csv_bytes=mixed))
    ]
    result, _ = _capture(tmp_path, FakeSession(responses))
    _rewrite_manifest(
        result.artifact_path,
        lambda value: value.__setitem__(field, replacement),
    )

    with pytest.raises(SharadarCaptureError, match=message):
        load_sharadar_capture_artifact(result.artifact_path)


def test_legacy_fundamental_field_names_cannot_masquerade_as_current_schema(
    tmp_path,
):
    legacy = FUNDAMENTALS.replace(
        b"calendardate,date,reportperiod", b"calendardate,datekey,reportperiod"
    ).replace(b"equityusd,revenueusd", b"equity,revenue")
    responses = _valid_responses()[:2] + [
        FakeResponse(_zip_bytes(SharadarDataset.FUNDAMENTALS, csv_bytes=legacy))
    ]
    with pytest.raises(SharadarCaptureError, match="required Sharadar fields"):
        _capture(tmp_path, FakeSession(responses))


def test_global_row_ceiling_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "MAX_TOTAL_ROWS", 2)
    with pytest.raises(SharadarCaptureError, match="row limit"):
        _capture(tmp_path)


def test_symlink_artifact_root_refuses_before_provider_call(tmp_path):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    session = FakeSession(_valid_responses())
    with pytest.raises(SharadarCaptureError, match="traversed a link"):
        _capture_sharadar_history_for_test(
            artifact_root=link,
            session=session,
            clock=Clock(),
            api_key=KEY,
        )
    assert not session.calls


def test_interruption_leaves_only_hidden_partial_staging(tmp_path):
    first = FakeResponse(_zip_bytes(SharadarDataset.TICKERS))
    session = FakeSession([first, RuntimeError("offline interruption")])
    with pytest.raises(SharadarCaptureError, match="details redacted"):
        _capture(tmp_path, session)
    root = tmp_path / "capture"
    entries = list(root.iterdir())
    assert len(entries) == 1
    assert entries[0].name.startswith(".") and entries[0].name.endswith(".incomplete")
    assert not (entries[0] / adapter.MANIFEST_FILENAME).exists()
    assert first.close_count == 1


def test_archive_file_creation_failure_still_closes_response(tmp_path, monkeypatch):
    response = FakeResponse(_zip_bytes(SharadarDataset.TICKERS))
    monkeypatch.setattr(
        adapter,
        "_new_private_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SharadarCaptureError("offline file-open failure")
        ),
    )
    with pytest.raises(SharadarCaptureError, match="file-open failure"):
        _capture(tmp_path, FakeSession([response]))
    assert response.close_count == 1


def test_root_sync_failure_rolls_publication_back_to_hidden_staging(tmp_path, monkeypatch):
    original = adapter._fsync

    def fail_publication(descriptor, label):
        if label == "capture publication":
            raise SharadarCaptureError("capture publication sync failed")
        return original(descriptor, label)

    monkeypatch.setattr(adapter, "_fsync", fail_publication)
    with pytest.raises(SharadarCaptureError, match="publication sync failed"):
        _capture(tmp_path)
    names = [item.name for item in (tmp_path / "capture").iterdir()]
    assert len(names) == 1 and names[0].endswith(".incomplete")
    assert not any(adapter._ARTIFACT_ID_RE.fullmatch(name) for name in names)


def test_parent_swap_cannot_redirect_archive_writes(tmp_path, monkeypatch):
    root = tmp_path / "capture"
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    original = adapter._capture_one_archive
    swapped = False

    def swap_after_first(stage_fd, session, dataset, key, **kwargs):
        nonlocal swapped
        result = original(stage_fd, session, dataset, key, **kwargs)
        if not swapped:
            staging = next(root.iterdir())
            displaced = root / ".displaced"
            staging.rename(displaced)
            staging.symlink_to(outside, target_is_directory=True)
            swapped = True
        return result

    monkeypatch.setattr(adapter, "_capture_one_archive", swap_after_first)
    with pytest.raises(SharadarCaptureError, match="capture staging"):
        _capture(tmp_path)
    assert list(outside.iterdir()) == []


def test_reload_refuses_archive_tamper(tmp_path):
    result, _ = _capture(tmp_path)
    archive = result.artifact_path / result.archives[0].archive_file
    payload = bytearray(archive.read_bytes())
    payload[len(payload) // 2] ^= 1
    archive.write_bytes(payload)
    with pytest.raises(SharadarCaptureError, match="archive bytes"):
        load_sharadar_capture_artifact(result.artifact_path)


def test_reload_refuses_extra_file_and_nonprivate_mode(tmp_path):
    result, _ = _capture(tmp_path)
    extra = result.artifact_path / "extra"
    extra.write_bytes(b"x")
    extra.chmod(0o600)
    with pytest.raises(SharadarCaptureError, match="inventory"):
        load_sharadar_capture_artifact(result.artifact_path)
    extra.unlink()
    archive = result.artifact_path / result.archives[0].archive_file
    archive.chmod(0o644)
    with pytest.raises(SharadarCaptureError, match="0600"):
        load_sharadar_capture_artifact(result.artifact_path)


def test_reload_refuses_rehashed_semantic_weakening(tmp_path):
    result, _ = _capture(tmp_path)
    _rewrite_manifest(
        result.artifact_path,
        lambda value: value.__setitem__("pit_security_master_constructed", True),
    )
    with pytest.raises(SharadarCaptureError, match="boundary changed"):
        load_sharadar_capture_artifact(result.artifact_path)


def test_reload_refuses_artifact_symlink(tmp_path):
    result, _ = _capture(tmp_path)
    link = tmp_path / "artifact-link"
    link.symlink_to(result.artifact_path, target_is_directory=True)
    with pytest.raises(SharadarCaptureError, match="traversed a link"):
        load_sharadar_capture_artifact(link)


def test_capture_identity_separates_test_and_production_transport(tmp_path):
    result, _ = _capture(tmp_path)
    test_manifest = adapter._manifest(
        "unused",
        result.capture_started_at,
        result.capture_completed_at,
        TEST_TRANSPORT,
        result.archives,
    )
    production_manifest = adapter._manifest(
        "unused",
        result.capture_started_at,
        result.capture_completed_at,
        PRODUCTION_TRANSPORT,
        result.archives,
    )
    assert test_manifest["capture_sha256"] != production_manifest["capture_sha256"]
    assert test_manifest["capture_id"] != production_manifest["capture_id"]


def test_module_import_does_not_eagerly_import_requests_or_read_key():
    source = Path(adapter.__file__).read_text()
    assert "import requests" in source
    assert source.index("def _new_session") < source.index("        import requests")
    assert adapter.PRODUCTION_TRANSPORT != adapter.TEST_TRANSPORT
