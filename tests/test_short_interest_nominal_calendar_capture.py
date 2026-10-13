"""Fabricated five-PDF transport/custody only; all real network denied."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import pytest

from data.hashing import hash_bytes, hash_payload
import scripts.capture_short_interest_nominal_calendar as capture

HEAD, REMOTE = "a" * 40, "b" * 40
START = "2026-10-14T00:00:00Z"
_POSIX = pytest.mark.skipif(not hasattr(os, "getuid"), reason="protected0700/0600 publication requiresPOSIX")


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "_guard", lambda *args: None)
    monkeypatch.setattr(capture, "_git", lambda root, command, path: path)
    calls = []
    def http(opener, request, maximum):
        assert request.method == "GET" and maximum == 4 * 1024 * 1024
        assert request.get_header("Authorization") is None
        calls.append(request.full_url)
        return b"%PDF-1.7\nfabricated source only", "application/pdf", 200
    monkeypatch.setattr(capture, "_http", http)
    base = datetime(2026, 10, 14, tzinfo=timezone.utc)
    ticks = iter(range(100))
    monkeypatch.setattr(capture, "_utc_now", lambda: (base + timedelta(seconds=next(ticks))).isoformat().replace("+00:00", "Z"))
    for name in capture.CODE_FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# fabricated code identity, not repository source\n")
    return tmp_path, calls


@_POSIX
def test_five_gets_protected_raw_receipts_no_credentials_and_visual_work_pending(runtime):
    root, calls = runtime
    result = capture.run(root, head=HEAD, remote=REMOTE)
    directory = root / result["capture_path"]
    assert calls == [capture.calendar.calendar_request(item)["url"] for item in capture.calendar.REQUEST_IDS]
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in directory.iterdir())
    inventory = json.loads((directory / "inventory.private.json").read_bytes())
    assert len(inventory["captures"]) == 5
    assert inventory["visual_transcriptions_pending"] is True
    assert inventory["nominal_schedule_qualified"] is False
    for receipt in inventory["captures"]:
        assert receipt["raw_sha256"] == hash_bytes((directory / receipt["raw_path"]).read_bytes())
        assert receipt["http_status"] == 200
    assert result["credential_reads"] == result["market_row_requests"] == result["outcome_looks"] == result["qc_attempts"] == 0
    assert result["backtest_result_exists"] is False
    assert (directory.parent / ("budget-" + capture.PROTOCOL_SHA256 + ".json")).exists()


@_POSIX
def test_global_spent_budget_blocks_timestamp_restart_without_more_requests(runtime):
    root, calls = runtime
    result = capture.run(root, head=HEAD, remote=REMOTE)
    directory = root / result["capture_path"]
    old = {path.name: path.read_bytes() for path in directory.iterdir()}
    with pytest.raises(capture.CaptureRefusal):
        capture.run(root, head=HEAD, remote=REMOTE)
    assert len(calls) == 5
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == old


@_POSIX
def test_malformed_source_retains_raw_and_failure_without_retry_or_completion(runtime, monkeypatch):
    root, calls = runtime
    def malformed(opener, request, maximum):
        calls.append(request.full_url)
        return b"<html>public503 page</html>", "text/html", 200
    monkeypatch.setattr(capture, "_http", malformed)
    with pytest.raises(ValueError):
        capture.run(root, head=HEAD, remote=REMOTE)
    directory = next((root / capture.PARENT).glob("nominal-calendar-*"))
    assert len(calls) == 1
    assert (directory / "request-01.raw.pdf").read_bytes().startswith(b"<html>")
    assert (directory / "request-01.received.json").exists()
    assert (directory / "request-01.refused.json").exists() and (directory / "refused.json").exists()
    assert not (directory / "completed.json").exists()


@_POSIX
def test_failed_second_http_keeps_first_and_spent_claim(runtime, monkeypatch):
    root, calls = runtime
    def failure(opener, request, maximum):
        calls.append(request.full_url)
        if len(calls) == 2:
            raise OSError("fabricated external failure text must not be persisted")
        return b"%PDF-1.7\nfabricated", "application/pdf", 200
    monkeypatch.setattr(capture, "_http", failure)
    with pytest.raises(OSError):
        capture.run(root, head=HEAD, remote=REMOTE)
    directory = next((root / capture.PARENT).glob("nominal-calendar-*"))
    assert len(calls) == 2
    assert (directory / "request-01.raw.pdf").exists()
    assert (directory / "request-02.started.json").exists() and (directory / "request-02.refused.json").exists()
    assert not (directory / "request-02.raw.pdf").exists()
    assert all(b"external failure text" not in path.read_bytes() for path in directory.glob("*.json"))


@pytest.mark.parametrize("entry", ["run", "capture_pdfs", "main"])
def test_unsupported_host_before_source_read_or_output(monkeypatch, entry):
    def deny(): raise capture.CapturePlatformRefusal()
    monkeypatch.setattr(capture, "_require_capture_platform", deny)
    for name in ("_guard", "_prepare_capture_directory", "_publish", "_publish_json", "_http"):
        monkeypatch.setattr(capture, name, lambda *a, **k: pytest.fail("sensitive action before platform refusal"))
    if entry == "main":
        assert capture.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 2
    else:
        with pytest.raises(capture.CapturePlatformRefusal):
            if entry == "run": capture.run(None, head=HEAD, remote=REMOTE)
            else: capture.capture_pdfs(None, None, None, head=HEAD, remote=REMOTE, started_at=START)


def test_pending_or_changed_protocol_refuses_before_output(runtime, monkeypatch):
    root, calls = runtime
    monkeypatch.setattr(capture, "PROTOCOL_SHA256", "0" * 64)
    with pytest.raises(capture.NominalCalendarCaptureRefusal, match="protocol"):
        capture.run(root, head=HEAD, remote=REMOTE)
    assert not calls and not (root / capture.PARENT).exists()


@_POSIX
def test_changed_next_request_url_refuses_before_next_fetch(runtime, monkeypatch):
    root, calls = runtime
    original = capture._http
    def change(opener, request, maximum):
        result = original(opener, request, maximum)
        monkeypatch.setattr(capture.calendar, "_URLS", ("https://not-nyse.example/changed.pdf",) + capture.calendar._URLS[1:])
        return result
    monkeypatch.setattr(capture, "_http", change)
    with pytest.raises(ValueError):
        capture.run(root, head=HEAD, remote=REMOTE)
    assert len(calls) == 1


@_POSIX
def test_backwards_first_request_clock_refuses_before_fetch(runtime, monkeypatch):
    root, calls = runtime
    clocks = iter([START, "2026-10-13T23:59:59Z", "2026-10-14T00:00:01Z"])
    monkeypatch.setattr(capture, "_utc_now", lambda: next(clocks))
    with pytest.raises(capture.NominalCalendarCaptureRefusal, match="chronology"):
        capture.run(root, head=HEAD, remote=REMOTE)
    assert not calls


@_POSIX
def test_guard_rechecked_immediately_before_every_publication(runtime, monkeypatch):
    root, calls = runtime
    state = {"guarded": False}
    original_publish, original_json = capture._publish, capture._publish_json
    def guard(*args): state["guarded"] = True
    def publish(directory, name, payload):
        assert state.pop("guarded", False), "publication lacks fresh lane/root/remote guard"
        state["guarded"] = False
        original_json(directory, name, payload)
    def raw(directory, name, payload):
        assert state.pop("guarded", False), "raw publication lacks fresh guard"
        state["guarded"] = False
        original_publish(directory, name, payload)
    monkeypatch.setattr(capture, "_guard", guard)
    monkeypatch.setattr(capture, "_publish_json", publish)
    monkeypatch.setattr(capture, "_publish", raw)
    capture.run(root, head=HEAD, remote=REMOTE)
    assert len(calls) == 5


def test_no_secret_reader_or_credential_wrapper_and_frozen_code_inventory():
    for name in ("_read_key", "_read_credentials", "KeychainSecret", "read_owner_keychain"):
        assert not hasattr(capture, name)
    assert hash_payload(capture.protocol()) == capture.PROTOCOL_SHA256
    assert capture.protocol()["code_files"] == list(capture.CODE_FILES)
