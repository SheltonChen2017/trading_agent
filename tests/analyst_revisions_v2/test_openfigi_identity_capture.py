from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

import scripts.capture_arv2_openfigi_identity as adapter
from research.analyst_revisions_v2.canonical import canonical_json_bytes, sha256_bytes


def figi(number):
    stem = f"BBG{number:08d}"
    values = [int(character, 36) * (1 if index % 2 == 0 else 2)
              for index, character in enumerate(stem)]
    check = (10 - sum(value // 10 + value % 10 for value in values) % 10) % 10
    return stem + str(check)


def row(ticker):
    index = adapter.TICKERS.index(ticker) + 1
    return {"figi": figi(index), "compositeFIGI": figi(index + 10),
            "shareClassFIGI": figi(index + 20), "ticker": ticker,
            "securityType": "Common Stock" if ticker == "QCOM" else "ETP",
            "marketSector": "Equity", "exchCode": "US", "name": "PUBLIC NAME",
            "securityType2": "Common Stock" if ticker == "QCOM" else "Mutual Fund",
            "securityDescription": ticker}


def response_bytes(batch):
    return json.dumps([{"data": [row(ticker)]} for ticker in batch]).encode()


class Response:
    def __init__(self, body, **changes):
        self.body = body
        self.status_code = 200
        self.history = []
        self.url = adapter.ENDPOINT
        self.headers = {"Content-Type": "application/json"}
        self.close_count = 0
        self.__dict__.update(changes)

    @property
    def content(self):
        raise AssertionError("bounded streaming is required")

    def iter_content(self, *, chunk_size):
        for start in range(0, len(self.body), 7):
            yield self.body[start:start + 7]

    def close(self):
        self.close_count += 1


class Session:
    def __init__(self, responses=None):
        self.responses = responses or [Response(response_bytes(batch)) for batch in adapter.BATCHES]
        self.calls = []
        self.close_count = 0

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if not hasattr(response, "request"):
            response.request = SimpleNamespace(url=url, method="POST", body=kwargs["data"], headers=kwargs["headers"])
        return response

    def close(self):
        self.close_count += 1


def clock(backwards=False):
    instants = iter((datetime(2026, 10, 7, 21, 0, 0, 1, tzinfo=timezone.utc),
                     datetime(2026, 10, 7, 20 if backwards else 21, 0, 1, 2, tzinfo=timezone.utc)))
    return lambda: next(instants)


def capture(tmp_path, session=None, **options):
    return adapter._capture_openfigi_identities_for_test(
        artifact_root=tmp_path / "public", session=session or Session(),
        clock=options.pop("clock", clock()), **options)


def load(loaded, digest=None):
    return adapter.load_openfigi_identity_capture(loaded.artifact_path,
        expected_manifest_sha256=digest or loaded.manifest_sha256)


def manifest(loaded):
    return json.loads((loaded.artifact_path / "manifest.json").read_bytes())


def replace_manifest(loaded, document):
    payload = canonical_json_bytes(document)
    (loaded.artifact_path / "manifest.json").write_bytes(payload)
    digest = sha256_bytes(payload)
    (loaded.artifact_path / "manifest.sha256").write_bytes((digest + "\n").encode())
    return digest


def test_two_unauthenticated_batches_public_rows_private_evidence_and_inert_flags(tmp_path):
    session = Session()
    loaded = capture(tmp_path, session)
    assert load(loaded) == loaded
    assert [len(binding.tickers) for binding in loaded.responses] == [5, 2]
    assert session.close_count == 0
    assert len(session.calls) == 2
    assert tuple(identity.ticker for identity in loaded.identities) == adapter.TICKERS
    for batch, (url, options) in zip(adapter.BATCHES, session.calls, strict=True):
        assert url == adapter.ENDPOINT
        assert options == {"data": canonical_json_bytes(adapter._jobs(batch)), "timeout": 60,
            "allow_redirects": False, "stream": True, "verify": True,
            "headers": {"Content-Type": "application/json", "Accept": "application/json", "Accept-Encoding": "identity"}}
        assert all(job == {"idType": "TICKER", "idValue": ticker, "exchCode": "US", "currency": "USD",
                          "marketSecDes": "Equity", "includeUnlistedEquities": False}
                   for job, ticker in zip(json.loads(options["data"]), batch, strict=True))
    assert loaded.artifact_path.stat().st_mode & 0o777 == 0o700
    for path in loaded.artifact_path.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.stat().st_nlink == 1
    document = manifest(loaded)
    assert all(document[name] is False for name in adapter.FALSE_FLAGS)
    assert document["current_public_reference_only"] is True
    assert figi(11) not in repr(loaded)


def test_figi_checksum_matches_official_example_not_fixture_algorithm_only():
    # https://www.openfigi.com/docs/figi-check-digit.pdf
    assert adapter._valid_figi("BBG000BLNQ16")
    assert not adapter._valid_figi("BBG000BLNQ15")
    assert not adapter._valid_figi("12G000000019")


@pytest.mark.parametrize("mutation", [
    lambda value: value.pop(),
    lambda value: value.append(value[0]),
    lambda value: value.reverse(),
    lambda value: value[0].update(error="SECRET"),
    lambda value: value[0].update(warning="SECRET"),
    lambda value: value[0].update(metadata="Metadata N/A"),
    lambda value: value[0].update(data=[]),
    lambda value: value[0]["data"].append(value[0]["data"][0]),
    lambda value: value[0]["data"][0].update(compositeFIGI=None),
    lambda value: value[0]["data"][0].update(compositeFIGI="BBG000000000"),
    lambda value: value[0]["data"][0].update(shareClassFIGI=None),
    lambda value: value[0]["data"][0].update(figi="INVALID"),
    lambda value: value[0]["data"][0].update(exchCode="LN"),
    lambda value: value[0]["data"][0].update(marketSector="Govt"),
    lambda value: value[0]["data"][0].update(securityType="ETP"),
    lambda value: value[1]["data"][0].update(securityType="Common Stock"),
    lambda value: value[0]["data"][0].update(currency="USD"),
    lambda value: value[0]["data"][0].update(name="PRIVATE\nROW"),
    lambda value: value[0]["data"][0].update(name="x" * 1025),
])
def test_refuses_malformed_or_ambiguous_provider_mapping(tmp_path, mutation):
    document = json.loads(response_bytes(adapter.BATCHES[0]))
    mutation(document)
    response = Response(json.dumps(document).encode())
    session = Session([response, Response(response_bytes(adapter.BATCHES[1]))])
    with pytest.raises(adapter.OpenFigiIdentityCaptureError) as error:
        capture(tmp_path, session)
    assert "SECRET" not in str(error.value)
    assert len(session.calls) == 1
    assert response.close_count == 1
    assert not list((tmp_path / "public").glob("*/manifest.json"))


@pytest.mark.parametrize("payload", [b"", b"null", b"{}", b"\xff", b"[NaN]", b"[Infinity]",
    b'[{"data":[],"data":[]}]', b"[" * 2000, b" " * (adapter.MAX_RESPONSE_BYTES + 1)])
def test_bounded_strict_json_refusals(tmp_path, payload):
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        capture(tmp_path, Session([Response(payload), Response(response_bytes(adapter.BATCHES[1]))]))
    assert not list((tmp_path / "public").glob("*/manifest.json"))


@pytest.mark.parametrize("field", ["compositeFIGI", "shareClassFIGI"])
def test_collision_across_batches_is_refused_before_publication(tmp_path, field):
    document = json.loads(response_bytes(adapter.BATCHES[1]))
    document[0]["data"][0][field] = row("QCOM")[field]
    with pytest.raises(adapter.OpenFigiIdentityCaptureError, match="collision"):
        capture(tmp_path, Session([Response(response_bytes(adapter.BATCHES[0])), Response(json.dumps(document).encode())]))
    assert not list((tmp_path / "public").glob("*/manifest.json"))


@pytest.mark.parametrize("changes", [
    {"status_code": 429}, {"status_code": True}, {"history": [object()]},
    {"url": adapter.ENDPOINT + "?key=SECRET"},
    {"headers": {"Content-Encoding": "gzip"}},
    {"headers": {"Content-Type": "text/html"}},
    {"headers": {"Content-Length": "0"}}, {"headers": {"Content-Length": "-1"}},
    {"headers": {"Content-Length": str(adapter.MAX_RESPONSE_BYTES + 1)}},
    {"headers": {"Content-Length": "1"}}, {"headers": {"Content-Length": "１"}},
])
def test_http_refusals_no_retry_no_leak(tmp_path, changes):
    session = Session([Response(response_bytes(adapter.BATCHES[0]), **changes), Response(response_bytes(adapter.BATCHES[1]))])
    with pytest.raises(adapter.OpenFigiIdentityCaptureError) as error:
        capture(tmp_path, session)
    assert "SECRET" not in str(error.value)
    assert len(session.calls) == 1


@pytest.mark.parametrize("field,value", [("method", "GET"), ("url", adapter.ENDPOINT + "/extra"),
    ("body", b"[]"), ("headers", {"X-OPENFIGI-APIKEY": "SECRET"}),
    ("headers", {"Authorization": "SECRET"}), ("headers", {"Cookie": "SECRET"})])
def test_prepared_request_identity_and_no_credentials(tmp_path, field, value):
    request = SimpleNamespace(method="POST", url=adapter.ENDPOINT,
        body=canonical_json_bytes(adapter._jobs(adapter.BATCHES[0])), headers={})
    setattr(request, field, value)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError) as error:
        capture(tmp_path, Session([Response(response_bytes(adapter.BATCHES[0]), request=request)]))
    assert "SECRET" not in str(error.value)


def test_provider_and_close_failures_are_sanitized(tmp_path):
    for session in (Session([RuntimeError("PRIVATE SECRET")]), Session()):
        if session.responses and isinstance(session.responses[0], Response):
            session.responses[0].close = lambda: (_ for _ in ()).throw(RuntimeError("PRIVATE SECRET"))
        with pytest.raises(adapter.OpenFigiIdentityCaptureError) as error:
            capture(tmp_path / str(id(session)), session)
        assert "PRIVATE SECRET" not in str(error.value)


def test_backwards_clock_and_exclusive_capture_collision(tmp_path):
    with pytest.raises(adapter.OpenFigiIdentityCaptureError, match="backwards"):
        capture(tmp_path, clock=clock(True))
    assert not list((tmp_path / "public").glob("*/manifest.json"))
    # A failed exact identity is not silently replaced by a new capture.
    session = Session()
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        capture(tmp_path, session)
    assert not session.calls


@pytest.mark.parametrize("filename", ["batch01.json", "batch02.json", "manifest.json", "manifest.sha256"])
def test_loader_refuses_changed_bytes_external_pins_permissions_and_links(tmp_path, filename):
    loaded = capture(tmp_path)
    target = loaded.artifact_path / filename
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        load(loaded)
    loaded = capture(tmp_path / "second")
    target = loaded.artifact_path / filename
    target.chmod(0o644)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        load(loaded)
    target.chmod(0o600)
    os.link(target, loaded.artifact_path / "extra-link")
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        load(loaded)


@pytest.mark.parametrize("change", [lambda doc: doc.update(decision_ready=True),
    lambda doc: doc.update(request_count=1), lambda doc: doc["identities"][0].update(composite_figi=figi(99)),
    lambda doc: doc["responses"][0]["request_jobs"][0].update(idValue="OTHER"),
    lambda doc: doc.update(capture_transport="unknown")])
def test_loader_rebuilds_all_manifest_claims_from_response_bytes(tmp_path, change):
    loaded = capture(tmp_path)
    document = manifest(loaded)
    change(document)
    digest = replace_manifest(loaded, document)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        load(loaded, digest)


def test_post_link_failure_revokes_only_own_completion_marker(tmp_path, monkeypatch):
    real = adapter.os.link
    def interrupted(*args, **options):
        real(*args, **options)
        raise OSError("PRIVATE ERROR")
    monkeypatch.setattr(adapter.os, "link", interrupted)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        capture(tmp_path)
    assert not list((tmp_path / "public").glob("*/manifest.json"))


def test_foreign_marker_is_preserved_on_ambiguous_publication(tmp_path, monkeypatch):
    def foreign(_old, new, **options):
        descriptor = os.open(new, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=options["dst_dir_fd"])
        os.write(descriptor, b"foreign")
        os.close(descriptor)
        raise OSError("PRIVATE ERROR")
    monkeypatch.setattr(adapter.os, "link", foreign)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError, match="ambiguous"):
        capture(tmp_path)
    assert list((tmp_path / "public").glob("*/manifest.json"))[0].read_bytes() == b"foreign"


def test_production_owns_sanitized_exact_session_and_no_key_access(tmp_path, monkeypatch):
    import requests
    raw = requests.Session()
    raw.trust_env = True
    raw.verify = False
    raw.auth = ("SECRET", "SECRET")
    raw.cert = "PRIVATE CERT"
    raw.headers["Authorization"] = "SECRET"
    raw.params["api_key"] = "SECRET"
    raw.cookies["session"] = "SECRET"
    raw.proxies["https"] = "http://SECRET"
    raw.hooks["response"] = [lambda response, **kwargs: response]
    monkeypatch.setattr(adapter.source, "_api_key", lambda: pytest.fail("public capture must not read keys"))
    monkeypatch.setattr(adapter.source, "_new_session", lambda: raw)
    monkeypatch.setattr(adapter, "DEFAULT_ARTIFACT_ROOT", tmp_path / "owned")
    monkeypatch.setattr(adapter.source, "_require_operational_scope", lambda path: None)
    def observe(**options):
        assert raw.trust_env is False and raw.verify is True and raw.auth is None and raw.cert is None
        assert all(not getattr(raw, key) for key in ("headers", "cookies", "params", "proxies", "hooks"))
        assert list(raw.adapters) == ["https://"]
        assert raw.adapters["https://"].max_retries.total == 0
        assert options["transport"] == adapter.PRODUCTION_TRANSPORT
        assert options["close_owned_session"] is True
        return "captured"
    monkeypatch.setattr(adapter, "_capture_core", observe)
    assert adapter.capture_openfigi_identities() == "captured"
    raw.close()


@pytest.mark.parametrize("kind", ["fake", "subclass", "method"])
def test_production_refuses_custom_transport_before_post(tmp_path, monkeypatch, kind):
    import requests
    class Custom(requests.Session):
        pass
    raw = Session() if kind == "fake" else Custom() if kind == "subclass" else requests.Session()
    if kind == "method":
        raw.post = lambda *args, **kwargs: pytest.fail("overridden transport must not execute")
    monkeypatch.setattr(adapter.source, "_new_session", lambda: raw)
    monkeypatch.setattr(adapter, "DEFAULT_ARTIFACT_ROOT", tmp_path / "owned")
    monkeypatch.setattr(adapter.source, "_require_operational_scope", lambda path: None)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError, match="owned"):
        adapter.capture_openfigi_identities()


class GetSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
    def get(self, url, **options):
        response = Response(self.payloads.pop(0), headers={})
        response.url = url + "?" + urlencode(options["params"])
        response.request = SimpleNamespace(method="GET", url=response.url)
        return response


def csv_bytes(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(fields)
    writer.writerows(rows)
    return stream.getvalue().encode()


def bound_fixture(tmp_path, *, mismatch=False, refuse=False):
    price = adapter.prices._capture_sharadar_prices_for_test(close_session="2026-10-06",
        artifact_root=tmp_path / "prices", clock=clock(), api_key="offline-test-price-key",
        session=GetSession([csv_bytes(adapter.prices.FIELDS,
            [(ticker, "2026-10-06", "123.45", "2026-10-07") for ticker in tickers])
            for _role, tickers in adapter.prices.ROLE_TICKERS]))
    payloads = []
    for role, tickers in adapter.identities.ROLE_TICKERS:
        rows = []
        for ticker in tickers:
            index = adapter.TICKERS.index(ticker) + 1
            rows.append((role, ticker, str(index), "PRIVATE VENDOR NAME", "NASDAQ" if role == "stocks" else "NYSE ARCA",
                "N", "ETF" if role == "funds" else "Domestic Common Stock",
                figi(index + 99 if mismatch and ticker == "QCOM" else index + 10), f"{index:09d}", "USD",
                "2020-01-01", "2000-01-01", "2026-10-06", "2026-10-07"))
        if refuse and role == "stocks":
            rows = []
        payloads.append(csv_bytes(adapter.identities.FIELDS, rows))
    vendor = adapter.identities._capture_sharadar_identities_for_test(artifact_root=tmp_path / "vendor",
        price_artifact_path=price.artifact_path, expected_price_manifest_sha256=price.manifest_sha256,
        session=GetSession(payloads), clock=clock(), api_key="offline-test-identity-key")
    public = capture(tmp_path)
    return dict(public_artifact_path=public.artifact_path, expected_public_manifest_sha256=public.manifest_sha256,
        sharadar_identity_artifact_path=vendor.artifact_path, expected_sharadar_identity_manifest_sha256=vendor.manifest_sha256,
        price_artifact_path=price.artifact_path, expected_price_manifest_sha256=price.manifest_sha256)


def test_offline_binder_uses_public_bytes_exact_cross_provider_and_price_pins(tmp_path):
    pins = bound_fixture(tmp_path)
    loaded = adapter._bind_public_identity_input_for_test(output_path=tmp_path / "bound" / "input.json", **pins)
    payload = loaded.input_path.read_bytes()
    document = json.loads(payload)
    assert sha256_bytes(payload) == loaded.input_sha256
    assert payload == canonical_json_bytes(document)
    assert document == {"schema": adapter.INPUT_SCHEMA,
        "rows": [{"ticker": ticker, "role": "stock" if ticker == "QCOM" else "fund",
                  "composite_figi": row(ticker)["compositeFIGI"]} for ticker in adapter.TICKERS],
        "price_manifest_sha256": pins["expected_price_manifest_sha256"],
        "public_reference_sha256": pins["expected_public_manifest_sha256"],
        "sharadar_identity_manifest_sha256": pins["expected_sharadar_identity_manifest_sha256"]}
    assert b"PRIVATE VENDOR NAME" not in payload and b"123.45" not in payload
    assert loaded.input_path.stat().st_mode & 0o777 == 0o600
    assert loaded.input_path.stat().st_nlink == 1
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        adapter._bind_public_identity_input_for_test(output_path=loaded.input_path, **pins)
    assert loaded.input_path.read_bytes() == payload


@pytest.mark.parametrize("stage", ["link_then_error", "post_publication_authentication", "final_readback"])
def test_binder_failed_publication_never_leaves_own_input(tmp_path, monkeypatch, stage):
    pins = bound_fixture(tmp_path)
    output = tmp_path / "bound" / "input.json"
    if stage == "link_then_error":
        real = adapter.os.link
        def failing(*args, **options):
            real(*args, **options)
            raise OSError("PRIVATE FAILURE")
        monkeypatch.setattr(adapter.os, "link", failing)
    elif stage == "post_publication_authentication":
        real = adapter._bound_bytes
        calls = []
        def failing(**options):
            calls.append(1)
            if len(calls) == 3:
                raise adapter.OpenFigiIdentityCaptureError("source changed after publication")
            return real(**options)
        monkeypatch.setattr(adapter, "_bound_bytes", failing)
    else:
        real = adapter.source._read_open_private_regular
        def failing(descriptor, **options):
            if options["label"] == "public identity input":
                raise adapter.OpenFigiIdentityCaptureError("published readback failed")
            return real(descriptor, **options)
        monkeypatch.setattr(adapter.source, "_read_open_private_regular", failing)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        adapter._bind_public_identity_input_for_test(output_path=output, **pins)
    assert not output.exists()


def test_binder_foreign_input_not_deleted_on_publication_race(tmp_path, monkeypatch):
    pins = bound_fixture(tmp_path)
    output = tmp_path / "bound" / "input.json"
    def foreign(_old, new, **options):
        descriptor = os.open(new, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=options["dst_dir_fd"])
        os.write(descriptor, b"foreign")
        os.close(descriptor)
        raise OSError("PRIVATE ERROR")
    monkeypatch.setattr(adapter.os, "link", foreign)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError, match="ambiguous"):
        adapter._bind_public_identity_input_for_test(output_path=output, **pins)
    assert output.read_bytes() == b"foreign"


def test_loader_rejects_held_response_replacement_after_parse(tmp_path, monkeypatch):
    loaded = capture(tmp_path)
    real = adapter._manifest
    def replace(*args, **options):
        rebuilt = real(*args, **options)
        target = loaded.artifact_path / "batch01.json"
        payload = target.read_bytes()
        target.unlink()
        target.write_bytes(payload)
        target.chmod(0o600)
        return rebuilt
    monkeypatch.setattr(adapter, "_manifest", replace)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        load(loaded)


def test_loader_rechecks_directory_path_after_final_parse(tmp_path, monkeypatch):
    loaded = capture(tmp_path)
    real = adapter._parse_response
    calls = []
    def moved(*args, **options):
        result = real(*args, **options)
        calls.append(1)
        if len(calls) == 4:
            loaded.artifact_path.rename(loaded.artifact_path.parent / "moved")
            loaded.artifact_path.mkdir(mode=0o700)
        return result
    monkeypatch.setattr(adapter, "_parse_response", moved)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError, match="pathname"):
        load(loaded)


def test_binder_rechecks_parent_path_and_preserves_foreign_replacement(tmp_path, monkeypatch):
    pins = bound_fixture(tmp_path)
    output = tmp_path / "bound" / "input.json"
    real = adapter._bound_bytes
    calls = []
    def moved(**options):
        result = real(**options)
        calls.append(1)
        if len(calls) == 3:
            output.parent.rename(tmp_path / "moved")
            output.parent.mkdir(mode=0o700)
            output.write_bytes(b"foreign")
            output.chmod(0o600)
        return result
    monkeypatch.setattr(adapter, "_bound_bytes", moved)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError, match="pathname"):
        adapter._bind_public_identity_input_for_test(output_path=output, **pins)
    assert output.read_bytes() == b"foreign"
    assert not (tmp_path / "moved" / "input.json").exists()


def test_loader_rejects_extra_inventory_and_symlink_root_or_evidence(tmp_path):
    loaded = capture(tmp_path)
    (loaded.artifact_path / "unexpected").write_bytes(b"x")
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        load(loaded)
    (loaded.artifact_path / "unexpected").unlink()
    target = loaded.artifact_path / "batch01.json"
    saved = loaded.artifact_path / "outside.json"
    target.rename(saved)
    target.symlink_to(saved)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        load(loaded)
    link = tmp_path / "linked-root"
    link.symlink_to(loaded.artifact_path, target_is_directory=True)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        adapter.load_openfigi_identity_capture(link, expected_manifest_sha256=loaded.manifest_sha256)


@pytest.mark.parametrize("option", ["mismatch", "refuse"])
def test_binder_refuses_mismatch_or_vendor_refusal_without_public_fallback(tmp_path, option):
    pins = bound_fixture(tmp_path, **{option: True})
    output = tmp_path / "bound" / "input.json"
    with pytest.raises(adapter.OpenFigiIdentityCaptureError, match="refused"):
        adapter._bind_public_identity_input_for_test(output_path=output, **pins)
    assert not output.exists()


@pytest.mark.parametrize("pin", ["expected_price_manifest_sha256", "expected_public_manifest_sha256",
                                 "expected_sharadar_identity_manifest_sha256"])
def test_binder_requires_every_external_pin(tmp_path, pin):
    pins = bound_fixture(tmp_path)
    pins[pin] = "a" * 64
    output = tmp_path / "input.json"
    with pytest.raises(adapter.OpenFigiIdentityCaptureError):
        adapter._bind_public_identity_input_for_test(output_path=output, **pins)
    assert not output.exists()


def test_binder_reauthenticates_sources_before_success_and_rolls_back(tmp_path, monkeypatch):
    pins = bound_fixture(tmp_path)
    real = adapter._bound_bytes
    calls = []
    def changed(**options):
        calls.append(1)
        if len(calls) == 2:
            raise adapter.OpenFigiIdentityCaptureError("source changed")
        return real(**options)
    monkeypatch.setattr(adapter, "_bound_bytes", changed)
    output = tmp_path / "input.json"
    with pytest.raises(adapter.OpenFigiIdentityCaptureError, match="changed"):
        adapter._bind_public_identity_input_for_test(output_path=output, **pins)
    assert not output.exists()


def test_production_binder_cannot_admit_synthetic_evidence(tmp_path, monkeypatch):
    pins = bound_fixture(tmp_path)
    monkeypatch.setattr(adapter.source, "_require_operational_scope", lambda path: None)
    with pytest.raises(adapter.OpenFigiIdentityCaptureError, match="transport"):
        adapter.bind_public_identity_input(output_path=tmp_path / "input.json", **pins)


def test_metadata_cli_redacts_errors_and_never_prints_identifier_rows(tmp_path, monkeypatch, capsys):
    loaded = capture(tmp_path)
    monkeypatch.setattr(adapter, "capture_openfigi_identities", lambda: loaded)
    assert adapter._main(["capture"]) == 0
    output = capsys.readouterr().out
    assert loaded.manifest_sha256 in output and "rows=7" in output
    assert figi(11) not in output and "PUBLIC NAME" not in output
    monkeypatch.setattr(adapter, "capture_openfigi_identities", lambda: (_ for _ in ()).throw(RuntimeError("SECRET")))
    assert adapter._main(["capture"]) == 1
    assert "SECRET" not in capsys.readouterr().err
