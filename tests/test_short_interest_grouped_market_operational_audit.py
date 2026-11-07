"""Independent fabricated audit; edits no grouped source/runtime files."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

import pytest
import scripts.capture_short_interest_native_grouped_market as runtime
from test_short_interest_native_grouped_market_capture import setup, run
from test_short_interest_native_grouped_market_source import ROW, envelope, local_midnight_milliseconds
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal
from scripts.short_interest_keychain import ShortInterestKeychainError


def test_last_response_protocol_drift_refuses_before_raw_or_completion(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    original = runtime._http
    def changed(*args):
        result = original(*args)
        monkeypatch.setattr(runtime, "PROTOCOL_SHA256", "b" * 64)
        return result
    monkeypatch.setattr(runtime, "_http", changed)
    with pytest.raises(runtime.GroupedCaptureError):
        run(frozen, kwargs)
    assert len(calls) == 1 and not any(name.endswith(".raw") for name in stored)
    assert "inventory.private.json" not in stored


def test_recognizable_space_wrapped_protected_timestamp_refuses_before_body_hash(monkeypatch):
    future = local_midnight_milliseconds("2026-09-02T00:00:00")
    raw = envelope(ROW.replace("1641254400000", '" ' + str(future) + ' "'))
    frozen, kwargs, events, stored, calls = setup(monkeypatch, raw=raw)
    hashed = []
    original = runtime.hash_bytes
    monkeypatch.setattr(runtime, "hash_bytes", lambda value: hashed.append(value) or original(value))
    with pytest.raises(runtime.GroupedCaptureError):
        run(frozen, kwargs)
    assert len(calls) == 1 and raw not in hashed
    assert not any(name.endswith(".raw") for name in stored)


def test_HTTP_error_status_is_retained_in_consumed_attempt_receipt(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    def refused(opener, request, maximum):
        calls.append(request)
        raise SharadarCaptureRefusal("http_not_200", status=429)
    monkeypatch.setattr(runtime, "_http", refused)
    with pytest.raises(runtime.GroupedCaptureError):
        run(frozen, kwargs)
    assert len(calls) == 1
    assert stored["session-0001.refused.json"]["http_status"] == 429


def test_consumed_claim_and_unavailable_named_key_keep_owned_zeroHTTP_refusal(monkeypatch):
    frozen, kwargs, events, stored, calls = setup(monkeypatch)
    kwargs["read_secret"] = lambda provider: (_ for _ in ()).throw(ShortInterestKeychainError("named_item_unavailable"))
    with pytest.raises((runtime.GroupedCaptureError, ShortInterestKeychainError)):
        run(frozen, kwargs)
    assert "claim" in events and not calls
    assert "refused.json" in stored
