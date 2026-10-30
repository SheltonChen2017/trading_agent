"""Injected synthetic transport; no real credentials, data or HTTP."""
from pathlib import Path
import json
import ssl
import urllib.request
from urllib.parse import parse_qs, urlsplit

import pytest

from data.hashing import hash_payload
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from scripts.short_interest_keychain import KeychainSecret, ShortInterestKeychainError
import research.short_interest_etf.fmp_company_context as contract
from scripts import capture_short_interest_fmp_company_context as runtime
from test_short_interest_fmp_company_context import ticket, lookup_row
from data.hashing import canonical_json

SECRET = "SYNTHETIC_ONLY_SECRET_42"
ROOT, DIRECTORY = Path("/fabricated/root"), Path("/fabricated/capture")


def setup(monkeypatch, *, lookup=None, cap=None, clocks=None):
    monkeypatch.setattr(runtime, "_require_capture_platform", lambda: None)
    monkeypatch.setattr(runtime, "_guard", lambda *args: None)
    plan = contract.freeze_context_plan((ticket(),))
    monkeypatch.setattr(runtime, "SELECTED_PLAN_SHA256", plan.sha256)
    monkeypatch.setattr(runtime, "PROTOCOL_SHA256", hash_payload(runtime.protocol()))
    bodies = [canonical_json([lookup_row()]).encode() if lookup is None else lookup,
              b'[{"symbol":"SYN","date":"2023-01-13","marketCap":9.25}]' if cap is None else cap]
    events, stored, calls = [], {}, []
    def verify_sources(value):
        assert value is plan
        value.to_bytes()
        events.append("sources")
    def verify_code():
        events.append("code")
    def claim(value):
        assert value["maximum_requests"] == 2
        events.append("claim")
    def key(provider):
        assert provider == "fmp"
        events.append("key")
        return KeychainSecret(SECRET)
    def publish(directory, name, value):
        assert name not in stored
        stored[name] = value
        events.append("publish:" + name)
    def http(opener, request, maximum):
        calls.append(request)
        events.append("HTTP")
        assert maximum == (1024 * 1024 if len(calls) == 1 else 8 * 1024 * 1024)
        return bodies[len(calls) - 1], "application/json", 200
    monkeypatch.setattr(runtime, "_http", http)
    if clocks is None:
        clocks = [f"2026-10-14T00:00:{number:02d}Z" for number in range(1, 12)]
    clocks = iter(clocks)
    kwargs = {"head": "a" * 40, "remote": "b" * 40, "started_at": "2026-10-14T00:00:00Z",
        "verify_sources": verify_sources, "verify_code": verify_code, "claim_budget": claim,
        "publish": publish, "publish_json": publish, "read_secret": key, "clock": lambda: next(clocks)}
    return plan, kwargs, events, stored, calls


def run(plan, kwargs, opener=None):
    return runtime.capture_with_seams(ROOT, DIRECTORY, plan,
        runtime.build_protected_opener() if opener is None else opener, **kwargs)


def serialized(stored):
    return json.dumps({name: value.decode() if type(value) is bytes else value for name, value in stored.items()})


def test_two_exact_header_authenticated_GETs_claim_before_key_no_secret_URL_or_logs(monkeypatch):
    plan, kwargs, events, stored, calls = setup(monkeypatch)
    result = run(plan, kwargs)
    assert events.index("claim") < events.index("key") < events.index("HTTP")
    assert len(calls) == result["http_attempts"] == 2
    assert parse_qs(urlsplit(calls[0].full_url).query) == {"cik": ["0000000001"], "limit": ["50"]}
    assert parse_qs(urlsplit(calls[1].full_url).query) == {
        "symbol": ["SYN"], "from": ["2022-01-03"], "to": ["2026-08-31"], "limit": ["5000"]}
    assert all(request.get_header("Apikey") == SECRET for request in calls)
    assert SECRET not in serialized(stored) and "apikey=" not in serialized(stored)
    assert result["source_admitted"] is result["market_cap_admitted"] is False


def test_negative_company_lookup_retained_then_cap_skipped_no_other_symbol_fallback(monkeypatch):
    plan, kwargs, events, stored, calls = setup(monkeypatch, lookup=canonical_json([lookup_row(symbol="OTHER")]).encode())
    result = run(plan, kwargs)
    assert len(calls) == result["http_attempts"] == 1
    assert "target-000001.cap.skipped.json" in stored
    assert stored["target-000001.cap.skipped.json"]["http_attempted"] is False
    assert result["unused_budget_repurposed"] is False


@pytest.mark.parametrize("body", [b'[{"symbol":"SYN","cik":"1","price":1}]',
    b'[{"symbol":"SYN","cik":"1","marketCap":1}]', b'[{"symbol":"SYN","cik":NaN}]',
    b'[{"symbol":"SYN","cik":"1","cik":"1"}]', b'{"next_url":"https://outside.invalid"}'])
def test_bad_lookup_scope_refused_before_body_hash_or_persistence(monkeypatch, body):
    plan, kwargs, events, stored, calls = setup(monkeypatch, lookup=body)
    hashes = []
    monkeypatch.setattr(runtime, "hash_bytes", lambda raw: hashes.append(raw) or "a" * 64)
    with pytest.raises(runtime.FmpContextCaptureError, match="no_retry"):
        run(plan, kwargs)
    assert len(calls) == 1 and hashes == []
    assert not any(name.endswith(".raw") for name in stored)
    assert stored["target-000001.lookup.refused.json"]["body_observed"] is True
    assert stored["target-000001.lookup.refused.json"]["raw_path"] is None


def test_protected_cap_date_is_not_hashed_or_persisted_lookup_receipt_remains(monkeypatch):
    body = b'[{"symbol":"SYN","date":"2026-09-01","marketCap":1}]'
    plan, kwargs, events, stored, calls = setup(monkeypatch, cap=body)
    hashes = []
    real_hash = runtime.hash_bytes
    monkeypatch.setattr(runtime, "hash_bytes", lambda raw: hashes.append(raw) or real_hash(raw))
    with pytest.raises(runtime.FmpContextCaptureError):
        run(plan, kwargs)
    assert len(calls) == 2 and body not in hashes
    assert "target-000001.lookup.raw" in stored and "target-000001.cap.raw" not in stored
    assert "inventory.private.json" not in stored


@pytest.mark.parametrize("echo", [SECRET.encode(), b"".join(f"\\u{ord(c):04x}".encode() for c in SECRET),
                                   b"".join(f"%{ord(c):02X}".encode() for c in SECRET)])
def test_encoded_key_echo_rejected_before_hash_storage_and_diagnostic(monkeypatch, echo):
    plan, kwargs, events, stored, calls = setup(monkeypatch, lookup=b'{"error":"' + echo + b'"}')
    hashes = []
    monkeypatch.setattr(runtime, "hash_bytes", lambda raw: hashes.append(raw) or "a" * 64)
    with pytest.raises(runtime.FmpContextCaptureError) as error:
        run(plan, kwargs)
    assert hashes == [] and SECRET not in str(error.value) and SECRET not in serialized(stored)


@pytest.mark.parametrize("status", [403, 404, 429])
def test_HTTP_status_only_failures_retained_no_error_body_or_retry(monkeypatch, status):
    plan, kwargs, events, stored, calls = setup(monkeypatch)
    def failed(opener, request, maximum):
        calls.append(request)
        raise SharadarCaptureRefusal("http_error", status=status)
    monkeypatch.setattr(runtime, "_http", failed)
    with pytest.raises(runtime.FmpContextCaptureError):
        run(plan, kwargs)
    receipt = stored["target-000001.lookup.refused.json"]
    assert receipt["http_status"] == status and receipt["error_body_read"] is False
    assert receipt["body_observed"] is False and receipt["raw_path"] is None and len(calls) == 1


def test_unexpected_exception_cannot_leak_in_memory_request_header(monkeypatch):
    plan, kwargs, events, stored, calls = setup(monkeypatch)
    def failed(opener, request, maximum):
        calls.append(request)
        raise RuntimeError(request.get_header("Apikey"))
    monkeypatch.setattr(runtime, "_http", failed)
    with pytest.raises(runtime.FmpContextCaptureError) as error:
        run(plan, kwargs)
    assert SECRET not in str(error.value) and SECRET not in serialized(stored)
    assert len(calls) == 1


def test_unknown_exception_status_property_is_never_invoked_or_exposed(monkeypatch):
    plan, kwargs, events, stored, calls = setup(monkeypatch)
    class UntrustedFailure(Exception):
        @property
        def http_status(self):
            raise RuntimeError(SECRET)
    def failed(opener, request, maximum):
        calls.append(request)
        raise UntrustedFailure()
    monkeypatch.setattr(runtime, "_http", failed)
    with pytest.raises(runtime.FmpContextCaptureError) as error:
        run(plan, kwargs)
    assert SECRET not in str(error.value) and SECRET not in serialized(stored)
    assert stored["target-000001.lookup.refused.json"]["http_status"] is None


def test_exclusive_claim_then_key_failure_retains_owned_zero_HTTP_receipt(monkeypatch):
    plan, kwargs, events, stored, calls = setup(monkeypatch)
    def no_key(provider):
        events.append("key")
        raise ShortInterestKeychainError("named_item_unavailable")
    kwargs["read_secret"] = no_key
    with pytest.raises(runtime.FmpContextCaptureError, match="key_unavailable"):
        run(plan, kwargs)
    assert events.index("claim") < events.index("key") and calls == []
    assert stored["key.refused.private.json"]["http_attempts"] == 0


def test_pending_protocol_blocks_claim_key_or_HTTP(monkeypatch):
    plan, kwargs, events, stored, calls = setup(monkeypatch)
    monkeypatch.setattr(runtime, "PROTOCOL_SHA256", "PENDING")
    with pytest.raises(runtime.FmpContextCaptureError, match="pending_or_changed"):
        run(plan, kwargs)
    assert "claim" not in events and "key" not in events and calls == [] and stored == {}


def test_custody_or_code_failure_prevents_claim_and_key(monkeypatch):
    plan, kwargs, events, stored, calls = setup(monkeypatch)
    def no_code():
        raise runtime.FmpContextCaptureError("source_code_changed")
    kwargs["verify_code"] = no_code
    with pytest.raises(runtime.FmpContextCaptureError):
        run(plan, kwargs)
    assert "claim" not in events and "key" not in events and calls == []


def test_protocol_mutation_during_response_refuses_before_body_hash_or_completion(monkeypatch):
    plan, kwargs, events, stored, calls = setup(monkeypatch)
    def changed(opener, request, maximum):
        calls.append(request)
        monkeypatch.setattr(runtime, "PROTOCOL_SHA256", "c" * 64)
        return canonical_json([lookup_row()]).encode(), "application/json", 200
    monkeypatch.setattr(runtime, "_http", changed)
    hashes = []
    monkeypatch.setattr(runtime, "hash_bytes", lambda raw: hashes.append(raw) or "a" * 64)
    with pytest.raises(runtime.FmpContextCaptureError, match="pending_or_changed"):
        run(plan, kwargs)
    assert hashes == [] and not any(name.endswith(".raw") for name in stored)
    assert "inventory.private.json" not in stored


@pytest.mark.parametrize("kind", ["redirect", "proxy", "unverified", "debug"])
def test_unsafe_opener_refused_before_claim_key_or_HTTP(monkeypatch, kind):
    plan, kwargs, events, stored, calls = setup(monkeypatch)
    if kind == "redirect":
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    elif kind == "proxy":
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": "https://outside.invalid"}), runtime._NoRedirect())
    elif kind == "unverified":
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), runtime._NoRedirect(),
                                           urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
    else:
        opener = runtime.build_protected_opener()
        for handler in opener.handlers:
            if type(handler) is urllib.request.HTTPSHandler:
                handler._debuglevel = 1
    with pytest.raises(runtime.FmpContextCaptureError, match="protected_no_proxy_no_redirect"):
        run(plan, kwargs, opener)
    assert "claim" not in events and "key" not in events and calls == []


def test_no_operational_entrypoint():
    with pytest.raises(runtime.FmpContextCaptureError, match="no_operational_entrypoint"):
        runtime.main()
