"""Fabricated injected runtime tests; no secrets, source rows or network."""
from pathlib import Path
import json
import ssl
import sys
import urllib.request
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from data.hashing import hash_payload
from scripts.short_interest_keychain import KeychainSecret
import scripts.capture_short_interest_native_grouped_market as runtime
import research.short_interest_etf.native_grouped_market_source as source
from test_short_interest_native_grouped_market_source import ROW, envelope, plan, local_midnight_milliseconds

SYNTHETIC_SECRET = "FABRICATED_MASSIVE_ONLY_42"


def setup(monkeypatch, *, raw=None, media="application/json", status=200, clocks=None):
    monkeypatch.setattr(runtime, "_require_capture_platform", lambda: None)
    monkeypatch.setattr(runtime, "_guard", lambda *args: None)
    frozen = plan()
    monkeypatch.setattr(runtime, "PLAN_SHA256", frozen.sha256)
    monkeypatch.setattr(runtime, "CALENDAR_SHA256", frozen.to_payload()["calendar_sha256"])
    monkeypatch.setattr(runtime, "PROTOCOL_SHA256", hash_payload(runtime.protocol()))
    events, stored, calls = [], {}, []
    def verify(value):
        value.sessions()
        events.append("verify")
    def claim(value):
        events.append("claim")
        assert value["maximum_requests"] == 1
    def key(provider):
        events.append("key")
        assert provider == "massive"
        return KeychainSecret(SYNTHETIC_SECRET)
    def publish(directory, name, value):
        assert name not in stored
        stored[name] = value
    def http(opener, request, maximum):
        assert maximum == source.MAXIMUM_RESPONSE_BYTES
        calls.append(request)
        events.append("HTTP")
        return envelope() if raw is None else raw, media, status
    monkeypatch.setattr(runtime, "_http", http)
    clock = iter(clocks or ["2026-10-13T01:00:01Z", "2026-10-13T01:00:02Z", "2026-10-13T01:00:03Z"])
    kwargs = {"head": "a" * 40, "remote": "b" * 40, "started_at": "2026-10-13T01:00:00Z",
              "verify_calendar": verify, "claim_budget": claim, "publish": publish,
              "publish_json": publish, "read_secret": key, "clock": lambda: next(clock)}
    return frozen, kwargs, events, stored, calls


def run(frozen, kwargs, opener=None):
    return runtime.capture_with_seams(Path("/fabricated/root"), Path("/fabricated/capture"), frozen,
                                      runtime.build_protected_opener() if opener is None else opener, **kwargs)


def test_calendar_and_global_claim_precede_key_and_exact_no_symbol_query(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    result = run(frozen, kwargs)
    assert events == ["verify", "claim", "key", "HTTP"]
    assert len(calls) == result["http_attempts"] == 1
    assert parse_qs(urlsplit(calls[0].full_url).query) == {"adjusted": ["false"], "include_otc": ["false"]}
    assert calls[0].get_header("Authorization") == "Bearer " + SYNTHETIC_SECRET
    serialized = json.dumps({name: value.decode() if type(value) is bytes else value for name, value in stored.items()})
    assert SYNTHETIC_SECRET not in serialized
    assert result["source_admitted"] is result["ready_for_empirical_backtest"] is False


@pytest.mark.parametrize("which", ["PLAN_SHA256", "PROTOCOL_SHA256", "CALENDAR_SHA256"])
def test_pending_pin_blocks_claim_key_and_HTTP(monkeypatch, which):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    monkeypatch.setattr(runtime, which, "PENDING")
    with pytest.raises(runtime.GroupedCaptureError, match="pending_or_changed"):
        run(frozen, kwargs)
    assert events == [] and stored == {} and calls == []


@pytest.mark.parametrize("kind", ["object", "default_redirect", "proxy", "TLS", "debug"])
def test_unsafe_transport_blocked_before_claim_and_key(monkeypatch, kind):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    if kind == "object":
        opener = object()
    elif kind == "default_redirect":
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    elif kind == "proxy":
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": "http://outside.invalid"}), runtime._NoRedirect())
    elif kind == "TLS":
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), runtime._NoRedirect(),
                                            urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
    else:
        opener = runtime.build_protected_opener()
        for handler in opener.handlers:
            if type(handler) is urllib.request.HTTPSHandler:
                handler._debuglevel = 1
    with pytest.raises(runtime.GroupedCaptureError, match="protected_transport"):
        run(frozen, kwargs, opener)
    assert events == [] and stored == {} and calls == []


@pytest.mark.parametrize("echo", [SYNTHETIC_SECRET.encode(),
                                   b"".join(f"\\u{ord(c):04x}".encode() for c in SYNTHETIC_SECRET),
                                   b"".join(f"%{ord(c):02X}".encode() for c in SYNTHETIC_SECRET)])
def test_secret_echo_refused_before_hash_or_raw_publication(monkeypatch, echo):
    frozen, kwargs, events, stored, calls = setup(monkeypatch, raw=b'{"error":"' + echo + b'"}')
    hashes = []
    monkeypatch.setattr(runtime, "hash_bytes", lambda value: hashes.append(value) or "a" * 64)
    with pytest.raises(runtime.GroupedCaptureError):
        run(frozen, kwargs)
    assert len(calls) == 1 and hashes == [] and not any(name.endswith(".raw") for name in stored)
    assert "inventory.private.json" not in stored


def test_header_echo_refused_before_raw_hash(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch, media=SYNTHETIC_SECRET)
    hashes = []
    monkeypatch.setattr(runtime, "hash_bytes", lambda value: hashes.append(value) or "a" * 64)
    with pytest.raises(runtime.GroupedCaptureError):
        run(frozen, kwargs)
    assert len(calls) == 1 and hashes == []


@pytest.mark.parametrize("raw", [b"[", envelope()[:-1] + b',"next_url":"https://outside.invalid"}',
                                  envelope().replace(b'"resultsCount":1', b'"resultsCount":2')])
def test_malformed_nonsecret_body_retained_with_fixed_refusal_no_retry(monkeypatch, raw):
    frozen, kwargs, events, stored, calls = setup(monkeypatch, raw=raw)
    with pytest.raises(runtime.GroupedCaptureError, match="grouped_request_refused_no_retry"):
        run(frozen, kwargs)
    assert len(calls) == 1
    assert stored["session-0001.raw"] == raw
    assert "session-0001.received.json" in stored and "session-0001.refused.json" in stored
    assert "inventory.private.json" not in stored


def test_transport_diagnostic_discarded_no_retry(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    def fail(opener, request, maximum):
        calls.append(request)
        raise OSError(SYNTHETIC_SECRET + request.full_url)
    monkeypatch.setattr(runtime, "_http", fail)
    with pytest.raises(runtime.GroupedCaptureError) as caught:
        run(frozen, kwargs)
    assert len(calls) == 1 and SYNTHETIC_SECRET not in str(caught.value)
    assert SYNTHETIC_SECRET not in json.dumps(stored)


def test_missing_independent_calendar_or_spent_claim_blocks_key(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    kwargs["verify_calendar"] = lambda value: (_ for _ in ()).throw(ValueError("fabricated_calendar_mismatch"))
    with pytest.raises(ValueError):
        run(frozen, kwargs)
    assert events == [] and calls == []
    kwargs["verify_calendar"] = lambda value: None
    kwargs["claim_budget"] = lambda value: (_ for _ in ()).throw(FileExistsError("spent"))
    with pytest.raises(FileExistsError):
        run(frozen, kwargs)
    assert "key" not in events and calls == []


@pytest.mark.parametrize("clocks", [["2026-10-13T00:59:59Z"],
                                     ["2026-10-13T01:00:01Z", "2026-10-13T01:00:00Z", "2026-10-13T01:00:03Z"]])
def test_request_or_received_clock_backdating_never_stores_raw(monkeypatch, clocks):
    frozen, kwargs, events, stored, calls = setup(monkeypatch, clocks=clocks)
    with pytest.raises(runtime.GroupedCaptureError):
        run(frozen, kwargs)
    assert not any(name.endswith(".raw") for name in stored)


def test_failure_clock_cannot_precede_observed_response_clock(monkeypatch):
    clocks = ["2026-10-13T01:00:01Z", "2026-10-13T01:00:03Z", "2026-10-13T01:00:02Z"]
    frozen, kwargs, events, stored, calls = setup(monkeypatch, raw=b"[", clocks=clocks)
    with pytest.raises(runtime.GroupedCaptureError, match="failure_receipt_chronology"):
        run(frozen, kwargs)
    assert "session-0001.refused.json" not in stored


def test_completion_clock_cannot_precede_received_clock(monkeypatch):
    clocks = ["2026-10-13T01:00:01Z", "2026-10-13T01:00:03Z", "2026-10-13T01:00:02Z"]
    frozen, kwargs, events, stored, calls = setup(monkeypatch, clocks=clocks)
    with pytest.raises(runtime.GroupedCaptureError, match="capture_completion_chronology"):
        run(frozen, kwargs)
    assert "inventory.private.json" not in stored


def test_no_live_entrypoint():
    with pytest.raises(runtime.GroupedCaptureError, match="no_operational_entrypoint"):
        runtime.main()


@pytest.mark.parametrize("timestamp", [local_midnight_milliseconds("2022-01-04T00:00:01"),
                                      local_midnight_milliseconds("2026-09-02T00:00:00")])
def test_known_wrong_or_protected_day_response_refused_before_hash_and_storage(monkeypatch, timestamp):
    raw = envelope(ROW.replace("1641254400000", str(timestamp)))
    frozen, kwargs, events, stored, calls = setup(monkeypatch, raw=raw)
    hashes = []
    monkeypatch.setattr(runtime, "hash_bytes", lambda value: hashes.append(value) or "a" * 64)
    with pytest.raises(runtime.GroupedCaptureError, match="grouped_request_refused_no_retry"):
        run(frozen, kwargs)
    assert len(calls) == 1 and hashes == []
    assert not any(name.endswith(".raw") for name in stored)
    assert "session-0001.received.json" not in stored
    assert "session-0001.refused.json" in stored
