"""Fabricated-only source/transport tests; no original source or secret read."""
from __future__ import annotations

from pathlib import Path

import pytest

import scripts.qualify_short_interest_terminal_disclosure as capture
from data.hashing import canonical_json


def source():
    return {"retrieved_at": "2026-10-13T22:00:00Z", "responses": [
        {"request": {"url": "https://api.massive.com/v3/reference/tickers/" + ticker},
         "status": "present", "normalized": {"ticker": ticker, "cik": cik}}
        for ticker, cik in (("TWTR", "0001234567"), ("FRC", "0002345678"))]}


def test_protocol_uses_exact_bound_response_issuer_not_current_symbol(monkeypatch):
    monkeypatch.setattr(capture, "CLASS_REPORT_SHA256", "a" * 64)
    protocol = capture._protocol(source())
    assert protocol.request("index-TWTR")["params"]["cik"] == "0001234567"
    assert protocol.request("text-FRC")["params"]["cik"] == "0002345678"
    assert all("ticker" not in protocol.request(rid)["params"] for rid in capture.disclosures.REQUEST_IDS)


@pytest.mark.parametrize("change", ["missing", "conflict", "ambiguous", "malformed"])
def test_missing_or_conflicting_issuer_never_falls_back(monkeypatch, change):
    monkeypatch.setattr(capture, "CLASS_REPORT_SHA256", "a" * 64)
    value = source()
    if change == "missing":
        value["responses"][0]["normalized"]["cik"] = None
    elif change == "conflict":
        value["responses"].append({**value["responses"][0], "normalized": {"ticker": "TWTR", "cik": "0003456789"}})
    else:
        value["responses"][0]["status"] = change
    with pytest.raises(capture.TerminalDisclosureCaptureRefusal, match="issuer_assertion_missing_or_ambiguous"):
        capture._protocol(value)


def test_pending_freeze_refuses_before_any_protected_read(monkeypatch):
    monkeypatch.setattr(capture, "CLASS_SOURCE", Path("artifacts/short_interest/massive_class_denominator/PENDING"))
    monkeypatch.setattr(capture, "_protected_bytes", lambda *args: pytest.fail("must not read source"))
    with pytest.raises(capture.TerminalDisclosureCaptureRefusal, match="source_freeze_pending"):
        capture._source(Path("/fictional-source"))


@pytest.mark.parametrize("entry", ["_source", "_run", "_capture", "main"])
def test_unsupported_host_refuses_before_source_key_or_transport(monkeypatch, entry):
    def deny(*args):
        raise capture.CapturePlatformRefusal()
    monkeypatch.setattr(capture, "_require_capture_platform", deny)
    for name in ("_guard", "_existing_key", "_protected_bytes", "_http", "_prepare_capture_directory"):
        monkeypatch.setattr(capture, name, lambda *args, **kwargs: pytest.fail("sensitive action reached"))
    if entry == "main":
        assert capture.main(["--expected-head", "a" * 40, "--expected-remote", "b" * 40]) == 2
    else:
        with pytest.raises(capture.CapturePlatformRefusal):
            if entry == "_source":
                capture._source(None)
            elif entry == "_run":
                capture._run(None, head=None, remote=None)
            else:
                capture._capture(None, None, None, None, None, head=None, remote=None)


def test_all_four_exact_requests_have_started_receipts_before_transport(monkeypatch):
    protocol = capture.disclosures.freeze_disclosure_protocol(("0001234567", "0002345678"),
                                                               source_class_report_sha256="a" * 64)
    events, published = [], {}
    monkeypatch.setattr(capture, "_guard", lambda *args: events.append("guard"))
    clocks = iter(f"2026-10-13T23:00:{i:02d}Z" for i in range(20))
    monkeypatch.setattr(capture, "_utc_now", lambda: next(clocks))
    def publish(directory, name, value):
        assert name not in published
        published[name] = value
        events.append(name)
    monkeypatch.setattr(capture, "_publish_json", publish)
    monkeypatch.setattr(capture, "_publish", publish)
    def http(opener, request, maximum):
        ordinal = len([e for e in events if e == "http"]) + 1
        assert events[-1] == "guard"
        assert f"attempt-{ordinal:02d}.started.json" in published
        rid = capture.disclosures.REQUEST_IDS[ordinal - 1]
        spec = protocol.request(rid)
        assert request.full_url == spec["url"] + "?" + capture.urllib.parse.urlencode(spec["params"])
        assert request.get_header("Authorization") == "Bearer fictional-placeholder"
        assert maximum == 4 * 1024 * 1024
        events.append("http")
        return canonical_json({"status": "OK", "results": [], "count": 0}).encode(), "application/json", 200
    monkeypatch.setattr(capture, "_http", http)
    result = capture._capture(None, None, protocol, "fictional-placeholder", None, head="b" * 40, remote="c" * 40, started_at="2026-10-13T23:00:00Z")
    assert events.count("http") == result["http_attempts"] == 4
    assert result["outcome_looks"] == result["qc_attempts"] == 0
    assert result["backtest_result_exists"] is False
    assert "evidence.private.json" in published


@pytest.mark.parametrize("failure", ["network", "echo", "oversize"])
def test_failed_transport_stops_without_retry_or_secret_publication(monkeypatch, failure):
    protocol = capture.disclosures.freeze_disclosure_protocol(("0001234567", "0002345678"),
                                                               source_class_report_sha256="a" * 64)
    published, calls = {}, []
    monkeypatch.setattr(capture, "_guard", lambda *args: None)
    monkeypatch.setattr(capture, "_utc_now", lambda: "2026-10-13T23:00:00Z")
    monkeypatch.setattr(capture, "_publish_json", lambda directory, name, value: published.__setitem__(name, value))
    monkeypatch.setattr(capture, "_publish", lambda directory, name, value: published.__setitem__(name, value))
    def http(*args):
        calls.append(1)
        if failure != "echo":
            raise capture.SharadarCaptureRefusal("network_failure" if failure == "network" else "response_size_limit")
        return b'{"secret":"fictional-placeholder"}', "application/json", 200
    monkeypatch.setattr(capture, "_http", http)
    with pytest.raises(capture.CaptureRefusal):
        capture._capture(None, None, protocol, "fictional-placeholder", None, head="b" * 40, remote="c" * 40, started_at="2026-10-13T23:00:00Z")
    assert len(calls) == 1
    assert set(published) == {"attempt-01.started.json", "attempt-01.refused.json"}
    assert "fictional-placeholder" not in canonical_json(published)


@pytest.mark.parametrize("completed_at", ["2026-10-13T23:00:00Z", "2026-10-13T23:00:08Z"])
def test_completion_clock_cannot_precede_response_or_report_retrieval(monkeypatch, completed_at):
    """Four requests finish; bad closing clock must not mint completion."""
    protocol = capture.disclosures.freeze_disclosure_protocol(("0001234567", "0002345678"),
                                                               source_class_report_sha256="a" * 64)
    clocks = iter([f"2026-10-13T23:00:{i:02d}Z" for i in range(1, 10)] + [completed_at])
    published, calls = {}, []
    monkeypatch.setattr(capture, "_guard", lambda *args: None)
    monkeypatch.setattr(capture, "_utc_now", lambda: next(clocks))
    monkeypatch.setattr(capture, "_publish_json", lambda directory, name, value: published.__setitem__(name, value))
    monkeypatch.setattr(capture, "_publish", lambda directory, name, value: published.__setitem__(name, value))
    def http(*args):
        calls.append(1)
        return b'{"status":"OK","results":[],"count":0}', "application/json", 200
    monkeypatch.setattr(capture, "_http", http)
    with pytest.raises(capture.CaptureRefusal, match="capture_clock_reversed"):
        capture._capture(None, None, protocol, "fictional-placeholder", None, head="b" * 40, remote="c" * 40, started_at="2026-10-13T23:00:00Z")
    assert len(calls) == 4
    assert "attempt-04.received.json" in published
    assert "completed.json" not in published


def test_enclosing_run_start_must_precede_first_request(monkeypatch):
    """Exercise _run composition, not an unsupported keyword/type refusal."""
    protocol = capture.disclosures.freeze_disclosure_protocol(("0001234567", "0002345678"),
                                                               source_class_report_sha256="a" * 64)
    monkeypatch.setattr(capture, "DISCLOSURE_PROTOCOL_SHA256", protocol.sha256)
    monkeypatch.setattr(capture, "_source", lambda root: source())
    monkeypatch.setattr(capture, "_protocol", lambda value: protocol)
    monkeypatch.setattr(capture, "_guard", lambda *args: None)
    monkeypatch.setattr(capture, "_existing_key", lambda: "fictional-placeholder")
    monkeypatch.setattr(capture, "_git", lambda root, command, target: target)
    monkeypatch.setattr(capture, "_prepare_capture_directory", lambda target: target)
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"fabricated-code-bytes")
    monkeypatch.setattr(capture.urllib.request, "build_opener", lambda *args: None)
    clocks = iter(["2026-10-13T23:00:02Z", "2026-10-13T23:00:01Z"] +
                  [f"2026-10-13T23:00:{i:02d}Z" for i in range(3, 20)])
    monkeypatch.setattr(capture, "_utc_now", lambda: next(clocks))
    published, calls = {}, []
    monkeypatch.setattr(capture, "_publish_json", lambda directory, name, value: published.__setitem__(name, value))
    monkeypatch.setattr(capture, "_publish", lambda directory, name, value: published.__setitem__(name, value))
    def http(*args):
        calls.append(1)
        return b'{"status":"OK","results":[],"count":0}', "application/json", 200
    monkeypatch.setattr(capture, "_http", http)
    with pytest.raises(capture.CaptureRefusal, match="capture_clock_reversed"):
        capture._run(Path("/fabricated-source"), head="b" * 40, remote="c" * 40)
    assert not calls
    assert "started.json" in published
    assert "attempt-01.started.json" not in published
    assert "completed.json" not in published
