from __future__ import annotations

import dataclasses
import inspect
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

import scripts.capture_arv2_sharadar_prices as adapter
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes


KEY = "offline-test-sharadar-price-key-NEVER-REAL"
SESSION = "2026-10-06"
HEADER = b"ticker,date,closeunadj,lastupdated\n"


def csv_bytes(role, *, override=None):
    return HEADER + b"".join(
        f"{ticker},{SESSION},{override or '123.45'},2026-10-07\n".encode()
        for ticker in dict(adapter.ROLE_TICKERS)[role]
    )


class Response:
    def __init__(self, body, *, status=200, url=None, method="GET", history=None, headers=None):
        self.body = body
        self.status_code = status
        self.override_url = url
        self.method = method
        self.history = history or []
        self.headers = headers or {}
        self.close_count = 0

    @property
    def content(self):
        raise AssertionError("must use bounded byte streaming")

    def iter_content(self, *, chunk_size):
        for start in range(0, len(self.body), 7):
            yield self.body[start:start + 7]

    def close(self):
        self.close_count += 1


class FakeSession:
    def __init__(self, responses=None):
        self.responses = responses or [Response(csv_bytes(role)) for role, _ in adapter.ROLE_TICKERS]
        self.calls = []
        self.close_count = 0

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        full = url + "?" + urlencode(kwargs["params"])
        item.request = SimpleNamespace(method=item.method, url=item.override_url or full)
        item.url = item.override_url or full
        return item

    def close(self):
        self.close_count += 1


def clock(*, backwards=False):
    instants = iter((
        datetime(2026, 10, 7, 20, 0, 0, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 7, 19 if backwards else 20, 0, 1, 2, tzinfo=timezone.utc),
    ))
    return lambda: next(instants)


def capture(tmp_path, session=None, **kwargs):
    session = session or FakeSession()
    loaded = adapter._capture_sharadar_prices_for_test(
        close_session=SESSION, artifact_root=tmp_path / "private-capture", session=session,
        clock=kwargs.pop("clock", clock()), api_key=kwargs.pop("api_key", KEY), **kwargs,
    )
    return loaded, session


def load(loaded, **kwargs):
    return adapter.load_sharadar_price_capture(
        loaded.artifact_path,
        expected_manifest_sha256=kwargs.pop("digest", loaded.manifest_sha256),
        **kwargs,
    )


def manifest(loaded):
    return json.loads((loaded.artifact_path / "manifest.json").read_bytes())


def replace_manifest(loaded, document):
    payload = canonical_json_bytes(document)
    (loaded.artifact_path / "manifest.json").write_bytes(payload)
    digest = sha256_bytes(payload)
    (loaded.artifact_path / "manifest.sha256").write_bytes((digest + "\n").encode())
    return digest


def test_exact_two_requests_private_bytes_and_offline_authentication(tmp_path):
    loaded, session = capture(tmp_path)
    assert len(session.calls) == 2
    assert session.close_count == 0  # synthetic seam does not own caller session
    assert loaded.capture_transport == adapter.TEST_TRANSPORT
    assert loaded.close_session == SESSION
    assert [binding.row_count for binding in loaded.responses] == [1, 6]
    assert load(loaded) == loaded
    for (role, tickers), (url, options), binding in zip(
        adapter.ROLE_TICKERS, session.calls, loaded.responses, strict=True,
    ):
        assert url == f"https://api.sharadar.com/v1.0/data/{role}"
        assert options == {
            "params": {
                "format": "csv", "from": SESSION, "to": SESSION,
                "fields": "ticker,date,closeunadj,lastupdated", "ticker": ",".join(tickers),
                "sort": "ticker.asc", "skip": "0", "limit": "100", "api_key": KEY,
            },
            "timeout": 60, "allow_redirects": False, "stream": True, "verify": True,
            "headers": {"Accept-Encoding": "identity"},
        }
        assert (loaded.artifact_path / binding.csv_file).read_bytes() == csv_bytes(role)
    assert loaded.artifact_path.stat().st_mode & 0o777 == 0o700
    assert {leaf.name for leaf in loaded.artifact_path.iterdir()} == {
        "stocks.csv", "funds.csv", "manifest.json", "manifest.sha256",
    }
    for leaf in loaded.artifact_path.iterdir():
        assert leaf.stat().st_mode & 0o777 == 0o600
        assert leaf.stat().st_nlink == 1
        assert KEY.encode() not in leaf.read_bytes()
    record = manifest(loaded)
    assert all(record[flag] is False for flag in adapter.FALSE_FLAGS)
    assert record["request_count"] == 2
    assert record["total_row_count"] == 7
    assert "caller_supplied" in record["session_semantics"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        loaded.close_session = "2026-10-07"


@pytest.mark.parametrize("value", [None, True, "2026-1-06", "2026-02-30", "2026-10-06T00:00:00Z", " 2026-10-06"])
def test_bad_session_refuses_before_provider_or_directory(tmp_path, value):
    session = FakeSession()
    with pytest.raises(adapter.SharadarPriceCaptureError):
        adapter._capture_sharadar_prices_for_test(
            close_session=value, artifact_root=tmp_path / "absent", session=session,
            clock=clock(), api_key=KEY,
        )
    assert session.calls == []
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("payload", [
    b"", b"\xff", b"<html>error</html>", b'{"error":"unavailable"}',
    b"ticker,date,close,lastupdated\nQCOM,2026-10-06,123.45,2026-10-07\n",
    HEADER + b"QCOM,2026-10-05,123.45,2026-10-07\n",
    HEADER + b"WRONG,2026-10-06,123.45,2026-10-07\n",
    HEADER + b"QCOM,2026-10-06,123.45,2026-02-30\n",
    HEADER + b"QCOM,2026-10-06,123.45,2026-10-07,extra\n",
    HEADER + b"QCOM,2026-10-06,123.45\n",
    HEADER + b"QCOM,2026-10-06,123.45,2026-10-07\nQCOM,2026-10-06,123.45,2026-10-07\n",
    HEADER + b'QCOM,2026-10-06,"unclosed,2026-10-07\n',
    HEADER + b"QCOM,2026-10-06,123.45,2026-10-07\x00\n",
    HEADER + b"QCOM,2026-10-06, 123.45,2026-10-07\n",
])
def test_invalid_csv_refuses_without_second_call_or_manifest(tmp_path, payload):
    first = Response(payload)
    session = FakeSession([first])
    with pytest.raises(adapter.SharadarPriceCaptureError):
        capture(tmp_path, session)
    assert len(session.calls) == 1
    assert first.close_count == 1
    assert not list((tmp_path / "private-capture").glob("*/manifest.json"))
    assert not list((tmp_path / "private-capture").glob("*/stocks.csv"))


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity", "0", "-0", "-1", "", "1_000", "1/2"])
def test_price_requires_positive_finite_decimal(tmp_path, value):
    body = HEADER + f"QCOM,{SESSION},{value},2026-10-07\n".encode()
    with pytest.raises(adapter.SharadarPriceCaptureError):
        capture(tmp_path, FakeSession([Response(body), Response(csv_bytes("funds"))]))


def test_fund_underfill_refuses_no_committed_manifest(tmp_path):
    session = FakeSession([Response(csv_bytes("stocks")), Response(
        HEADER + f"SPY,{SESSION},123.45,2026-10-07\n".encode()
    )])
    with pytest.raises(adapter.SharadarPriceCaptureError, match="missing required tickers"):
        capture(tmp_path, session)
    assert len(session.calls) == 2
    assert not list((tmp_path / "private-capture").glob("*/manifest.json"))


@pytest.mark.parametrize("status", [302, 303, 307, 308, 401, 429, 500, True, "200"])
def test_non_200_or_malformed_status_never_redirects_or_retries(tmp_path, status):
    session = FakeSession([Response(csv_bytes("stocks"), status=status)])
    with pytest.raises(adapter.SharadarPriceCaptureError):
        capture(tmp_path, session)
    assert len(session.calls) == 1


@pytest.mark.parametrize("mutation", ["host", "path", "query", "duplicate", "fragment", "http", "method", "history"])
def test_prepared_identity_is_exact(tmp_path, mutation):
    endpoint = "https://api.sharadar.com/v1.0/data/stocks"
    params = {**adapter._query("stocks", SESSION), "api_key": KEY}
    full = endpoint + "?" + urlencode(params)
    if mutation == "host":
        full = full.replace("api.sharadar.com", "example.com")
    elif mutation == "path":
        full = full.replace("/stocks?", "/funds?")
    elif mutation == "query":
        full = full.replace("from=2026-10-06", "from=2026-10-05")
    elif mutation == "duplicate":
        full += "&ticker=QCOM"
    elif mutation == "fragment":
        full += "#bad"
    elif mutation == "http":
        full = full.replace("https://", "http://")
    response = Response(csv_bytes("stocks"), url=full,
                        method="POST" if mutation == "method" else "GET",
                        history=[object()] if mutation == "history" else None)
    session = FakeSession([response])
    with pytest.raises(adapter.SharadarPriceCaptureError):
        capture(tmp_path, session)
    assert len(session.calls) == 1
    assert response.close_count == 1


@pytest.mark.parametrize("length", ["0", "-1", "NaN", "1048577", "1", 123, "\u0661"])
def test_declared_length_refuses_invalid_overlimit_or_truncation(tmp_path, length):
    session = FakeSession([
        Response(csv_bytes("stocks"), headers={"Content-Length": length}),
        Response(csv_bytes("funds")),
    ])
    with pytest.raises(adapter.SharadarPriceCaptureError):
        capture(tmp_path, session)


def test_streaming_byte_ceiling(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "MAX_RESPONSE_BYTES", 8)
    with pytest.raises(adapter.SharadarPriceCaptureError, match="byte limit"):
        capture(tmp_path)


def test_request_limit_reached_and_long_field_are_refused(monkeypatch):
    monkeypatch.setattr(adapter, "REQUEST_ROW_LIMIT", 1)
    with pytest.raises(adapter.SharadarPriceCaptureError, match="row limit"):
        adapter._parse_csv(csv_bytes("stocks"), "stocks", SESSION)
    monkeypatch.setattr(adapter, "REQUEST_ROW_LIMIT", 100)
    with pytest.raises(adapter.SharadarPriceCaptureError, match="row shape"):
        adapter._parse_csv(csv_bytes("stocks", override="1" * 129), "stocks", SESSION)


def test_provider_exception_and_key_echo_are_sanitized(tmp_path):
    session = FakeSession([RuntimeError("SECRET " + KEY + " private provider body")])
    with pytest.raises(adapter.SharadarPriceCaptureError) as refusal:
        capture(tmp_path, session)
    assert KEY not in str(refusal.value)
    assert "private provider body" not in str(refusal.value)
    assert refusal.value.__cause__ is None
    echo_session = FakeSession([Response(KEY.encode())])
    with pytest.raises(adapter.SharadarPriceCaptureError, match="echoed a credential"):
        capture(tmp_path / "echo", echo_session)
    assert not list((tmp_path / "echo").glob("**/*.csv"))


@pytest.mark.parametrize("leaf", ["stocks.csv", "funds.csv", "manifest.json", "manifest.sha256"])
def test_tampered_leaf_refuses_exact_pinned_loader(tmp_path, leaf):
    loaded, _ = capture(tmp_path)
    file = loaded.artifact_path / leaf
    file.write_bytes(file.read_bytes() + b" ")
    with pytest.raises(adapter.SharadarPriceCaptureError):
        load(loaded)


@pytest.mark.parametrize("mutation", ["flag", "unknown", "row_count", "query", "transport", "clock"])
def test_rehashed_self_assertions_do_not_bypass_strict_schema(tmp_path, mutation):
    loaded, _ = capture(tmp_path)
    document = manifest(loaded)
    if mutation == "flag":
        document["point_in_time_proven"] = True
    elif mutation == "unknown":
        document["unknown"] = False
    elif mutation == "row_count":
        document["responses"][0]["row_count"] = 2
    elif mutation == "query":
        document["responses"][0]["request_query"]["to"] = "2026-10-05"
    elif mutation == "transport":
        document["capture_transport"] = "unreviewed"
    else:
        document["capture_completed_at"] = "2026-10-07T19:00:01.000002Z"
    digest = replace_manifest(loaded, document)
    with pytest.raises(adapter.SharadarPriceCaptureError):
        load(loaded, digest=digest)


def test_wrong_expected_digest_and_moved_identity_refuse(tmp_path):
    loaded, _ = capture(tmp_path)
    with pytest.raises(adapter.SharadarPriceCaptureError, match="pinned digest"):
        load(loaded, digest="0" * 64)
    changed = loaded.artifact_path.with_name("arv2-sharadar-prices-20261007T210000000001Z")
    loaded.artifact_path.rename(changed)
    with pytest.raises(adapter.SharadarPriceCaptureError, match="path differs"):
        adapter.load_sharadar_price_capture(changed, expected_manifest_sha256=loaded.manifest_sha256)


@pytest.mark.parametrize("mutation", ["symlink", "hardlink", "public_file", "public_dir", "extra"])
def test_private_leaf_and_inventory_boundary(tmp_path, mutation):
    loaded, _ = capture(tmp_path)
    leaf = loaded.artifact_path / "stocks.csv"
    if mutation == "symlink":
        outside = tmp_path / "outside.csv"
        leaf.rename(outside)
        leaf.symlink_to(outside)
    elif mutation == "hardlink":
        os.link(leaf, tmp_path / "other-name.csv")
    elif mutation == "public_file":
        leaf.chmod(0o644)
    elif mutation == "public_dir":
        loaded.artifact_path.chmod(0o755)
    else:
        (loaded.artifact_path / "unexpected").write_bytes(b"extra")
    with pytest.raises(adapter.SharadarPriceCaptureError):
        load(loaded)


def test_collision_and_backwards_clock_never_publish(tmp_path):
    loaded, _ = capture(tmp_path)
    original = (loaded.artifact_path / "manifest.json").read_bytes()
    session = FakeSession()
    with pytest.raises(adapter.SharadarPriceCaptureError, match="already exists"):
        capture(tmp_path, session)
    assert not session.calls
    assert (loaded.artifact_path / "manifest.json").read_bytes() == original
    with pytest.raises(adapter.SharadarPriceCaptureError, match="clock moved backwards"):
        capture(tmp_path / "backwards", clock=clock(backwards=True))
    assert not list((tmp_path / "backwards").glob("**/manifest.json"))


def test_atomic_manifest_publication_is_exclusive(tmp_path, monkeypatch):
    original_link = adapter.os.link
    def collision(src, dst, **kwargs):
        fd = os.open(dst, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600,
                     dir_fd=kwargs["dst_dir_fd"])
        os.write(fd, b"existing concurrent marker")
        os.close(fd)
        return original_link(src, dst, **kwargs)
    monkeypatch.setattr(adapter.os, "link", collision)
    with pytest.raises(adapter.SharadarPriceCaptureError):
        capture(tmp_path)
    marker = next((tmp_path / "private-capture").glob("*/manifest.json"))
    assert marker.read_bytes() == b"existing concurrent marker"


def test_test_seam_rejects_production_credentials(tmp_path):
    session = FakeSession()
    with pytest.raises(adapter.SharadarPriceCaptureError, match="synthetic test credential"):
        capture(tmp_path, session, api_key="real-shaped-key-123456")
    assert not session.calls


def test_production_entry_owns_session_key_and_transport(tmp_path, monkeypatch):
    import requests
    raw = requests.Session()
    raw.trust_env = True
    raw.verify = False
    raw.proxies["https"] = "https://untrusted.invalid"
    raw.params["unreviewed"] = "value"
    raw.auth = ("should", "clear")
    raw.cert = ("untrusted-client-cert", "untrusted-key")
    raw.cookies.set("session", "untrusted")
    raw.hooks["response"].append(lambda response, **_kwargs: response)
    raw.mount("https://api.sharadar.com", requests.adapters.HTTPAdapter(max_retries=3))
    observed = {}
    monkeypatch.setattr(adapter.source, "_api_key", lambda: "test-production-owned-key")
    monkeypatch.setattr(adapter.source, "_new_session", lambda: raw)
    monkeypatch.setattr(adapter, "DEFAULT_ARTIFACT_ROOT", tmp_path / "private")
    def core(**kwargs):
        observed.update(kwargs)
        assert raw.trust_env is False and raw.verify is True
        assert raw.auth is None and raw.cert is None
        assert not raw.proxies and not raw.params and not raw.cookies
        assert not raw.headers
        assert not raw.hooks
        assert set(raw.adapters) == {"https://"}
        assert raw.get_adapter("https://api.sharadar.com").max_retries.total == 0
        kwargs["session"].close()
        return "synthetic returned sentinel, not an actual capture"
    monkeypatch.setattr(adapter, "_capture_core", core)
    returned = adapter.capture_sharadar_prices(close_session=SESSION)
    assert returned.startswith("synthetic")
    assert observed["key"] == "test-production-owned-key"
    assert observed["transport"] == adapter.PRODUCTION_TRANSPORT
    assert observed["close_owned_session"] is True
    assert "session" not in inspect.signature(adapter.capture_sharadar_prices).parameters
    assert "api_key" not in inspect.signature(adapter.capture_sharadar_prices).parameters
    assert "transport" not in inspect.signature(adapter._capture_sharadar_prices_for_test).parameters


def test_cli_prints_only_counts_hashes_paths_and_false_flags(tmp_path, monkeypatch, capsys):
    loaded, _ = capture(tmp_path)
    monkeypatch.setattr(adapter, "capture_sharadar_prices", lambda **_kwargs: loaded)
    assert adapter._main(["--close-session", SESSION]) == 0
    result = capsys.readouterr()
    assert "rows=7" in result.out and "point_in_time_proven=false" in result.out
    assert "123.45" not in result.out and KEY not in result.out
    assert result.err == ""


def test_unique_reordered_headers_and_utf8_bom_preserve_received_bytes(tmp_path):
    stock = b"\xef\xbb\xbflastupdated,closeunadj,date,ticker\r\n2026-10-07,123.45,2026-10-06,QCOM\r\n"
    loaded, _ = capture(tmp_path, FakeSession([Response(stock), Response(csv_bytes("funds"))]))
    assert (loaded.artifact_path / "stocks.csv").read_bytes() == stock
    assert loaded.responses[0].csv_sha256 == sha256_bytes(stock)
    assert load(loaded) == loaded
    with pytest.raises(adapter.SharadarPriceCaptureError, match="header"):
        adapter._parse_csv(b"ticker,date,closeunadj,ticker\n", "stocks", SESSION)


@pytest.mark.parametrize("encoding", ["gzip", "br", "deflate", "", True])
def test_nonidentity_response_encoding_is_refused(tmp_path, encoding):
    with pytest.raises(adapter.SharadarPriceCaptureError, match="content encoding"):
        capture(tmp_path, FakeSession([
            Response(csv_bytes("stocks"), headers={"Content-Encoding": encoding}),
            Response(csv_bytes("funds")),
        ]))


@pytest.mark.parametrize("stage", ["publication_sync", "loader", "reauthentication"])
def test_failed_postlink_completion_revokes_only_owned_manifest(tmp_path, monkeypatch, stage):
    if stage == "publication_sync":
        original = adapter.source._fsync
        def fail(fd, label):
            if label == "price capture publication":
                raise adapter.SharadarPriceCaptureError("simulated sync failure")
            return original(fd, label)
        monkeypatch.setattr(adapter.source, "_fsync", fail)
    elif stage == "loader":
        def fail(*_args, **_kwargs):
            raise adapter.SharadarPriceCaptureError("simulated loader failure")
        monkeypatch.setattr(adapter, "load_sharadar_price_capture", fail)
    else:
        original = adapter.source._pinned_child
        def fail(parent, name, child, label):
            if label == "reauthenticated price capture":
                raise adapter.SharadarPriceCaptureError("simulated postread pin failure")
            return original(parent, name, child, label)
        monkeypatch.setattr(adapter.source, "_pinned_child", fail)
    with pytest.raises(adapter.SharadarPriceCaptureError):
        capture(tmp_path)
    children = list((tmp_path / "private-capture").iterdir())
    assert len(children) == 1
    assert not (children[0] / "manifest.json").exists()
    assert (children[0] / "stocks.csv").exists()


def test_completion_failure_does_not_remove_other_process_marker(tmp_path, monkeypatch):
    replacement = b"another process's replacement"
    def fail(path, **_kwargs):
        marker = path / "manifest.json"
        marker.rename(path / "owned-manifest-withheld.json")
        marker.write_bytes(replacement)
        marker.chmod(0o600)
        raise adapter.SharadarPriceCaptureError("simulated failure after replacement")
    monkeypatch.setattr(adapter, "load_sharadar_price_capture", fail)
    with pytest.raises(adapter.SharadarPriceCaptureError, match="state is ambiguous"):
        capture(tmp_path)
    marker = next((tmp_path / "private-capture").glob("*/manifest.json"))
    assert marker.read_bytes() == replacement


def test_ambiguous_link_failure_revokes_owned_completion_marker(tmp_path, monkeypatch):
    original = adapter.os.link
    def linked_then_failed(src, dst, **kwargs):
        original(src, dst, **kwargs)
        raise OSError("simulated ambiguous publication failure")
    monkeypatch.setattr(adapter.os, "link", linked_then_failed)
    with pytest.raises(adapter.SharadarPriceCaptureError):
        capture(tmp_path)
    assert not list((tmp_path / "private-capture").glob("*/manifest.json"))


def test_close_failure_is_redacted_and_no_manifest_is_published(tmp_path):
    session = FakeSession()
    def bad_close():
        raise RuntimeError("private body " + KEY)
    session.close = bad_close
    with pytest.raises(adapter.SharadarPriceCaptureError) as refusal:
        adapter._capture_core(
            close_session=SESSION, artifact_root=tmp_path / "capture", session=session,
            key=KEY, clock=clock(), transport=adapter.TEST_TRANSPORT, close_owned_session=True,
        )
    assert "closure failed" in str(refusal.value)
    assert KEY not in str(refusal.value) and "private body" not in str(refusal.value)
    assert not list((tmp_path / "capture").glob("*/manifest.json"))


@pytest.mark.parametrize("method", ["get", "send", "get_adapter", "mount", "resolve_redirects"])
def test_production_refuses_instance_method_override_before_provider(tmp_path, monkeypatch, method):
    import requests
    raw = requests.Session()
    setattr(raw, method, lambda *_args, **_kwargs: pytest.fail("no request allowed"))
    monkeypatch.setattr(adapter.source, "_api_key", lambda: "test-production-owned-key")
    monkeypatch.setattr(adapter.source, "_new_session", lambda: raw)
    monkeypatch.setattr(adapter, "DEFAULT_ARTIFACT_ROOT", tmp_path / "private")
    with pytest.raises(adapter.SharadarPriceCaptureError, match="overridden transport methods"):
        adapter.capture_sharadar_prices(close_session=SESSION)


def test_loader_rechecks_leaf_identity_after_all_parses(tmp_path, monkeypatch):
    loaded, _ = capture(tmp_path)
    original = adapter._binding
    def replace_during_parse(payload, role, session):
        binding = original(payload, role, session)
        if role == "funds":
            leaf = loaded.artifact_path / "stocks.csv"
            replacement = loaded.artifact_path / "replacement.csv"
            replacement.write_bytes(leaf.read_bytes())
            replacement.chmod(0o600)
            replacement.replace(leaf)
        return binding
    monkeypatch.setattr(adapter, "_binding", replace_during_parse)
    with pytest.raises(adapter.SharadarPriceCaptureError, match="identity changed|single-link file"):
        load(loaded)


def test_cli_refusal_does_not_print_sensitive_exception_context(monkeypatch, capsys):
    def refused(**_kwargs):
        raise adapter.SharadarPriceCaptureError("provider request failed; details redacted")
    monkeypatch.setattr(adapter, "capture_sharadar_prices", refused)
    assert adapter._main(["--close-session", SESSION]) == 1
    result = capsys.readouterr()
    assert result.out == ""
    assert "details redacted" in result.err
    assert KEY not in result.err and "123.45" not in result.err
