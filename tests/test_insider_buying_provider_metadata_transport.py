"""Invented keys and supplied bytes only; no provider call in this suite."""
from dataclasses import replace
import hashlib
import io
import json
from urllib import error

import pytest

from research import insider_buying_provider_metadata_transport as m

ENV = {"QC_USER_ID": "123", "QC_API_TOKEN": "invented-qc-secret",
       "MASSIVE_API_KEY": "invented-massive-secret", "SHARADAR_API_KEY": "invented-sharadar-secret"}
BODIES = {
    "quantconnect": {"success": True},
    "massive": {"market": "closed", "earlyHours": False, "afterHours": True,
                "serverTime": "2026-10-06T17:37:37-04:00",
                "currencies": {"crypto": "open", "fx": "open"},
                "exchanges": {"nasdaq": "extended-hours", "nyse": "closed", "otc": "closed"}},
    "sharadar": {"table": "tickers", "name": "tickers.csv.zip", "size": 123,
                 "sizeLabel": "123 B", "modified": "2026-07-16T03:57:16.344000+00:00"},
}


def raw(provider):
    return json.dumps(BODIES[provider]).encode()


def probe(provider="quantconnect", response=None, capture=None):
    def transport(item):
        if capture is not None:
            capture.append(item)
        return response or m.ProviderMetadataResponse(200, raw(provider))
    return m.probe_provider_metadata(provider, environ=ENV, transport=transport, clock=lambda: 123456)


@pytest.mark.parametrize("provider", tuple(BODIES))
def test_exact_profile_and_safe_receipt(provider):
    calls = []
    result = probe(provider, capture=calls)
    assert len(calls) == 1
    item = calls[0]
    profile, method, url, body = m._PROFILES[provider]
    assert (item.method, item.url, item.body, item.timeout_seconds) == (method, url, body, 15)
    assert dict(item.headers)["Accept-Encoding"] == "identity"
    assert result.request_profile == profile
    assert result.http_status == 200
    assert result.body_size_bytes == len(raw(provider))
    assert result.body_sha256 == hashlib.sha256(raw(provider)).hexdigest()
    assert result.body_complete is True
    payload = result.to_dict()
    assert payload == result.to_payload()
    assert payload["authentication_observed"] is (provider == "quantconnect")
    for key in ("entitlement_verified", "rights_verified", "historical_coverage_verified",
                "research_ready", "qc_backtest_authorized", "outcome_access_authorized"):
        assert payload[key] is False
    public = repr(item) + repr(result) + repr(m.ProviderMetadataResponse(200, b"secret")) + json.dumps(payload)
    assert "secret" not in public
    assert not hasattr(result, "body")
    detached = result.facts
    detached["injected"] = "secret"
    assert "injected" not in result.facts


def test_provider_specific_header_credentials_and_no_query_keys():
    for provider in BODIES:
        calls = []
        probe(provider, capture=calls)
        headers = dict(calls[0].headers)
        if provider == "quantconnect":
            assert headers["Authorization"].startswith("Basic ")
            assert headers["Timestamp"] == "123456"
            assert ENV["QC_API_TOKEN"] not in str(headers)
        elif provider == "massive":
            assert headers["Authorization"] == "Bearer " + ENV["MASSIVE_API_KEY"]
        else:
            assert headers["x-api-key"] == ENV["SHARADAR_API_KEY"]
        assert all(value not in calls[0].url for value in ENV.values())


@pytest.mark.parametrize("provider,key", [("quantconnect", "QC_USER_ID"), ("quantconnect", "QC_API_TOKEN"),
                                        ("massive", "MASSIVE_API_KEY"), ("sharadar", "SHARADAR_API_KEY")])
@pytest.mark.parametrize("bad", [None, "", " ", "a\r\nInjected: secret", "a\x00b", "é", 12, True, "x" * 4097, "test-api-key"])
def test_credentials_refuse_before_transport(provider, key, bad):
    env = dict(ENV)
    if bad is None:
        del env[key]
    else:
        env[key] = bad
    calls = []
    result = m.probe_provider_metadata(provider, environ=env, transport=lambda item: calls.append(item), clock=lambda: 1)
    assert result.disposition in {"credentials-missing", "credentials-invalid"}
    assert result.http_status is None and result.body_sha256 is None
    assert calls == []
    assert "secret" not in repr(result) + json.dumps(result.to_dict())


def test_sharadar_no_alias_nasdaq_or_sample_fallback():
    env = {"NASDAQ_API_KEY": "secret", "SHARADAR_KEY": "secret", "QUANDL_API_KEY": "secret"}
    result = m.probe_provider_metadata("sharadar", environ=env, transport=lambda item: pytest.fail("request"))
    assert result.disposition == "credentials-missing"


@pytest.mark.parametrize("stamp", [0, -1, True, "123", 1.5, 2**63])
def test_qc_invalid_clock_refuses(stamp):
    result = m.probe_provider_metadata("quantconnect", environ=ENV, clock=lambda: stamp,
                                      transport=lambda item: pytest.fail("request"))
    assert result.disposition == "clock-invalid"


@pytest.mark.parametrize("provider", [None, "QC", "unknown", "https://evil.example", "secret\n"])
def test_unknown_provider_error_never_interpolates_value(provider):
    with pytest.raises(m.ProviderMetadataTransportError, match="^unknown-provider$"):
        m.probe_provider_metadata(provider, environ=ENV)


@pytest.mark.parametrize("change", [
    {"url": "https://evil.example"}, {"url": "https://api.sharadar.com/v1.0/data/tickers?years=full"},
    {"method": "DELETE"}, {"body": b"secret"}, {"timeout_seconds": True}, {"timeout_seconds": 16},
    {"headers": (("Accept", "application/json"), ("x-api-key", "secret\r\nX: bad"))},
    {"headers": (("Accept", "application/json"), ("Accept", "application/json"))},
])
def test_request_profile_refuses_mutation_before_default_transport(monkeypatch, change):
    item = m._build_request("sharadar", ENV, lambda: 1)
    monkeypatch.setattr(m.request, "build_opener", lambda *a: pytest.fail("opener"))
    with pytest.raises(m.ProviderMetadataTransportError, match="invalid-request"):
        m._default_transport(replace(item, **change))
    assert "secret" not in repr(replace(item, **change))


@pytest.mark.parametrize("provider", tuple(BODIES))
def test_duplicate_json_keys_at_any_depth_refuse(provider):
    supplied = b'{"success":true,"success":false}' if provider == "quantconnect" else (
        b'{"market":"open","exchanges":{"nyse":"open","nyse":"closed"}}' if provider == "massive" else
        b'{"table":"tickers","name":"tickers.csv.zip","size":1,"size":2,"sizeLabel":"1 B","modified":"2026-01-01T00:00:00Z"}')
    result = m.parse_provider_metadata(provider, 200, supplied)
    assert result.disposition == "invalid-metadata-schema" and result.facts == {}


@pytest.mark.parametrize("success", [1, 0, "true", None, [], {}])
def test_qc_success_requires_exact_bool(success):
    assert m.parse_provider_metadata("quantconnect", 200, json.dumps({"success": success}).encode()).disposition == "invalid-metadata-schema"


def test_qc_false_and_untrusted_errors_never_echo():
    result = m.parse_provider_metadata("quantconnect", 200, b'{"success":false,"errors":["secret token"]}')
    assert result.disposition == "authentication-refused"
    assert result.facts == {"success": False}
    assert "secret" not in json.dumps(result.to_dict())
    assert m.parse_provider_metadata("quantconnect", 200, b'{"success":true,"errors":["secret"]}').disposition == "invalid-metadata-schema"


@pytest.mark.parametrize("change", [
    {"market": "secret"}, {"market": 1}, {"earlyHours": 1}, {"serverTime": "secret"},
    {"serverTime": "2026-13-01T00:00:00Z"}, {"serverTime": "2026-01-01"},
    {"exchanges": {"nyse": "secret"}}, {"exchanges": {"evil": "open"}},
    {"currencies": []}, {"results": [{"close": 12}]}, {"market": None},
])
def test_massive_only_scalar_whitelist_and_exact_types(change):
    body = dict(BODIES["massive"], **change)
    result = m.parse_provider_metadata("massive", 200, json.dumps(body).encode())
    assert result.disposition == "invalid-metadata-schema" and result.facts == {}


@pytest.mark.parametrize("change", [
    {"table": "stocks"}, {"name": "../../secret.csv"}, {"size": True}, {"size": -1},
    {"size": 1.5}, {"size": "12"}, {"size": 2**63}, {"sizeLabel": "secret"},
    {"modified": "2026-01-01T00:00:00"}, {"modified": "2026-01-01T00:00:00-05:00"},
    {"modified": "2026-02-30T00:00:00Z"}, {"rows": [{"ticker": "secret"}]},
])
def test_sharadar_status_not_rows_and_strict_metadata(change):
    result = m.parse_provider_metadata("sharadar", 200, json.dumps(dict(BODIES["sharadar"], **change)).encode())
    assert result.disposition == "invalid-metadata-schema" and result.facts == {}


@pytest.mark.parametrize("supplied", [b"", b"secret", b"[]", b"null", b'"secret"', b'{}', b'\xff',
                                     b'{"success":NaN}', b'{"success":Infinity}', b'{"success":1e100}', b"[" * 2000])
def test_malformed_and_nonnumeric_body_sanitized(supplied):
    result = m.parse_provider_metadata("quantconnect", 200, supplied)
    assert result.disposition == "invalid-metadata-schema"
    assert result.body_sha256 == hashlib.sha256(supplied).hexdigest()
    assert "secret" not in repr(result) + json.dumps(result.to_dict())


@pytest.mark.parametrize("status,expected", [(301, "redirect-refused"), (307, "redirect-refused"),
    (401, "authentication-http-refused"), (403, "authentication-http-refused"), (429, "rate-limited"), (500, "http-error")])
def test_http_failure_body_hashed_not_echoed(status, expected):
    result = probe(response=m.ProviderMetadataResponse(status, b"secret"))
    assert result.disposition == expected and result.body_complete is True
    assert result.body_size_bytes == 6 and result.facts == {}
    assert "secret" not in json.dumps(result.to_dict())


class Stream(io.BytesIO):
    def __init__(self, body, *, status=200, headers=None, url=None):
        super().__init__(body)
        self.headers = {} if headers is None else headers
        self.status = status
        self.url = url or m._PROFILES["quantconnect"][2]
        self.read_sizes = []
    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)
    def getcode(self):
        return self.status
    def geturl(self):
        return self.url


def default_with_stream(monkeypatch, stream, *, raised=False, env=None):
    captured = []
    class Opener:
        def open(self, item, timeout):
            captured.append((item, timeout))
            if raised:
                raise stream
            return stream
    def factory(*handlers):
        captured.append(handlers)
        return Opener()
    monkeypatch.setattr(m.request, "build_opener", factory)
    result = m.probe_provider_metadata("quantconnect", environ=ENV if env is None else env, clock=lambda: 1)
    return result, captured


def test_default_no_proxy_no_redirect_tls_identity_and_fixed_timeout(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://secret.proxy:9999")
    monkeypatch.setenv("HTTP_PROXY", "http://secret.proxy:9999")
    stream = Stream(b'{"success":true}', headers={"Content-Length": "16"})
    result, captured = default_with_stream(monkeypatch, stream)
    handlers = captured[0]
    assert handlers[0].proxies == {}
    assert isinstance(handlers[1], m._DenyRedirect)
    assert isinstance(handlers[2], m.request.HTTPSHandler)
    assert handlers[2]._context.verify_mode == m.ssl.CERT_REQUIRED
    assert handlers[2]._context.check_hostname is True
    req, timeout = captured[1]
    assert req.full_url == m._PROFILES["quantconnect"][2]
    assert req.get_method() == "POST" and req.data == b"{}" and timeout == 15
    assert req.get_header("Accept-encoding") == "identity"
    assert result.disposition == "qc-authentication-observed"
    assert stream.closed and all(size > 0 for size in stream.read_sizes)


def test_redirect_handler_does_not_return_followup_request():
    assert m._DenyRedirect().redirect_request(None, None, 302, "secret", {}, "https://evil.example") is None


@pytest.mark.parametrize("headers,body,expected", [
    ({"Content-Length": str(m.MAX_BODY_BYTES + 1)}, b"secret", "oversized-response"),
    ({}, b"x" * (m.MAX_BODY_BYTES + 1), "oversized-response"),
    ({"Content-Length": "100"}, b'{"success":true}', "truncated-response"),
    ({"Content-Length": "-1"}, b"secret", "invalid-content-length"),
    ({"Content-Length": "abc"}, b"secret", "invalid-content-length"),
    ({"Content-Encoding": "gzip"}, b"secret", "unsupported-content-encoding"),
])
def test_bounded_default_reads_and_length_encoding_classifications(monkeypatch, headers, body, expected):
    stream = Stream(body, headers=headers)
    result, _ = default_with_stream(monkeypatch, stream)
    assert result.disposition == expected and result.body_complete is False
    assert result.body_size_bytes <= m.MAX_BODY_BYTES + 1
    assert result.facts == {} and stream.closed
    assert "secret" not in json.dumps(result.to_dict())


def test_exact_body_bound_positive(monkeypatch):
    body = b'{"success":true}' + b" " * (m.MAX_BODY_BYTES - 16)
    result, _ = default_with_stream(monkeypatch, Stream(body, headers={"Content-Length": str(m.MAX_BODY_BYTES)}))
    assert result.disposition == "qc-authentication-observed"
    assert result.body_size_bytes == m.MAX_BODY_BYTES


def test_http_error_body_is_bounded_and_no_redirect_followed(monkeypatch):
    url = m._PROFILES["quantconnect"][2]
    failure = error.HTTPError(url, 302, "secret", {"Location": "https://evil.example"}, io.BytesIO(b"secret"))
    result, captured = default_with_stream(monkeypatch, failure, raised=True)
    assert result.disposition == "redirect-refused" and result.body_size_bytes == 6
    assert len(captured) == 2
    failure = error.HTTPError(url, 403, "secret", {}, io.BytesIO(b"x" * (m.MAX_BODY_BYTES + 2)))
    result, _ = default_with_stream(monkeypatch, failure, raised=True)
    assert result.disposition == "oversized-response" and result.body_complete is False


def test_partial_read_hashes_only_received_prefix_and_never_retries(monkeypatch):
    class Partial(Stream):
        def read(self, size=-1):
            if self.tell():
                raise OSError("secret key in wire exception")
            return super().read(4)
    result, captured = default_with_stream(monkeypatch, Partial(b"partial secret"))
    assert result.disposition == "partial-read" and result.body_complete is False
    assert result.body_size_bytes == 4 and result.body_sha256 == hashlib.sha256(b"part").hexdigest()
    assert len(captured) == 2 and "secret" not in repr(result) + json.dumps(result.to_dict())


@pytest.mark.parametrize("exception,expected", [(TimeoutError("secret"), "transport-timeout"),
    (error.URLError(TimeoutError("secret")), "transport-timeout"), (error.URLError("secret"), "transport-error"),
    (OSError("secret"), "transport-error")])
def test_default_failures_no_exception_details_or_retry(monkeypatch, exception, expected):
    class Opener:
        calls = 0
        def open(self, req, timeout):
            self.calls += 1
            raise exception
    opener = Opener()
    monkeypatch.setattr(m.request, "build_opener", lambda *a: opener)
    result = m.probe_provider_metadata("quantconnect", environ=ENV, clock=lambda: 1)
    assert result.disposition == expected and opener.calls == 1
    assert "secret" not in repr(result) + json.dumps(result.to_dict())


def test_injected_exception_and_bad_result_are_sanitized():
    def broken(item):
        raise ValueError("secret bearer key")
    result = m.probe_provider_metadata("massive", environ=ENV, transport=broken)
    assert result.disposition == "transport-error" and "secret" not in json.dumps(result.to_dict())
    for response in (None, {}, (200, b"secret"), m.ProviderMetadataResponse(True, b"secret"),
                     m.ProviderMetadataResponse(200, bytearray(b"secret")),
                     m.ProviderMetadataResponse(200, b"secret", body_complete=1),
                     m.ProviderMetadataResponse(200, b"secret", disposition="secret")):
        result = m.probe_provider_metadata("massive", environ=ENV, transport=lambda item: response)
        assert result.disposition == "invalid-transport-result"
        assert "secret" not in json.dumps(result.to_dict())


@pytest.mark.parametrize("bad", [{"secret": "token"}, ["secret"]])
def test_unhashable_injected_disposition_is_sanitized(bad):
    result = m.probe_provider_metadata("massive", environ=ENV,
        transport=lambda item: m.ProviderMetadataResponse(200, b"secret", disposition=bad))
    assert result.disposition == "invalid-transport-result"
    assert "secret" not in json.dumps(result.to_dict())


def test_wrong_response_origin_refuses_without_retaining_body(monkeypatch):
    stream = Stream(b"secret", url="https://evil.example")
    result, _ = default_with_stream(monkeypatch, stream)
    assert result.disposition == "response-origin-mismatch"
    assert result.body_size_bytes == 0 and result.facts == {} and stream.closed


def test_import_inert_no_credentials_or_transport(monkeypatch):
    import importlib.util
    import sys
    monkeypatch.setattr(m, "_default_transport", lambda *a: pytest.fail("transport"))
    monkeypatch.setattr(m.QuantConnectCredentials, "from_env", lambda *a: pytest.fail("env"))
    class NoCredentialRead(dict):
        def get(self, *args):
            pytest.fail("credential read")
    monkeypatch.setattr(m.os, "environ", NoCredentialRead())
    spec = importlib.util.spec_from_file_location("metadata_inert_fixture", m.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert module.MAX_BODY_BYTES == 1024 * 1024
