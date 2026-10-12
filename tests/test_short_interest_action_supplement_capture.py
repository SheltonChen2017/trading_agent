"""Fabricated-only transport checks; no inherited credentials or provider access."""
from __future__ import annotations

import io
import json
from pathlib import Path
import urllib.error

import pytest
from short_interest_capture_fixtures import portable_capture_platform

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.massive_action_supplement as contract
import scripts.qualify_short_interest_action_supplement as capture
import os

# Only protected-I/O cases require POSIX; pure parsing, transport and early
# refusal checks must remain active on the supported Windows host.
_POSIX_CAPTURE_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason=(
        "the protected-capture runtime requires POSIX ownership and mode "
        "semantics (os.getuid, O_NOFOLLOW, 0o600/0o700, symlinks); it cannot "
        "execute on this host, see the lane record SI-CR17-002"
    ),
)

KEY = "fabricated-only-key-for-offline-tests"
HEAD, REMOTE = "a" * 40, "b" * 40
NOW = "2026-10-11T22:00:12.123456Z"


class Response:
    def __init__(self, raw=b'{"status":"OK","results":[]}', status=200, content_type="application/json"):
        self.raw, self.status = raw, status
        self.headers, self.reads = {"Content-Type": content_type}, 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, maximum):
        self.reads += 1
        return self.raw[:maximum]


class Opener:
    def __init__(self, responses, before=None):
        self.responses, self.requests, self.before = iter(responses), [], before

    def open(self, request, timeout):
        if self.before:
            self.before(request)
        self.requests.append(request)
        assert timeout == 30
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class PrivateReport:
    sha256 = "c" * 64

    def to_payload(self):
        return {"private_fixture_only": True}


@pytest.fixture
def offline(monkeypatch):
    guards = []
    monkeypatch.setattr(capture, "_guard", lambda *args: guards.append(args))
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    monkeypatch.setattr(capture, "bind_sharadar_companion", lambda *args: PrivateReport())
    return guards


def run(tmp_path, opener):
    return capture._capture(tmp_path, tmp_path, KEY, opener, object(),
                            expected_head=HEAD, expected_remote=REMOTE)


@_POSIX_CAPTURE_ONLY
def test_full_capture_has_exact_prospective_inventory_and_header_only_key(tmp_path, offline):
    ordinal = 0
    def before(request):
        nonlocal ordinal
        ordinal += 1
        record = json.loads((tmp_path / f"attempt-{ordinal:02d}.started.json").read_bytes())
        assert record["attempt"] == ordinal
        assert record["request_id"] == contract.REQUEST_IDS[ordinal - 1]
        assert record["request_sha256"] == hash_payload(record["request"])
        assert len(offline) == 2 * ordinal
        assert request.get_header("Authorization") == "Bearer " + KEY
        assert KEY not in request.full_url
    opener = Opener([Response() for _ in range(62)], before)
    result = run(tmp_path, opener)
    assert len(opener.requests) == result["http_attempts"] == 62
    assert result["backtest_result_exists"] is False
    assert len(offline) == 125
    assert (tmp_path / "binding.private.json").exists()
    assert not any(KEY.encode() in f.read_bytes() for f in tmp_path.iterdir() if f.is_file())


@pytest.mark.parametrize("status", [204, 301, 401, 403, 429, 500, True, "secret-shaped-status"])
@_POSIX_CAPTURE_ONLY
def test_non_200_stops_without_read_retry_or_later_request(tmp_path, offline, status):
    response = Response(status=status)
    opener = Opener([response])
    with pytest.raises(capture.ActionSupplementCaptureRefusal):
        run(tmp_path, opener)
    assert len(opener.requests) == 1 and response.reads == 0
    assert (tmp_path / "attempt-01.started.json").exists()
    assert not (tmp_path / "attempt-01.raw").exists()


@pytest.mark.parametrize("raw,ctype", [
    (KEY.encode(), "application/json"),
    (json.dumps({"k": KEY}).replace("f", "\\u0066").encode(), "application/json"),
    (b'{"status":"OK","results":[]}', "application/json; key=" + KEY),
])
@_POSIX_CAPTURE_ONLY
def test_credential_echo_never_persists_in_raw_or_receipts(tmp_path, offline, raw, ctype):
    with pytest.raises(capture.ActionSupplementCaptureRefusal, match="credential_echo"):
        run(tmp_path, Opener([Response(raw=raw, content_type=ctype)]))
    assert not (tmp_path / "attempt-01.raw").exists()
    assert not any(KEY.encode() in f.read_bytes() for f in tmp_path.iterdir())


@_POSIX_CAPTURE_ONLY
def test_late_head_change_stops_after_start_receipt_before_http(tmp_path, monkeypatch):
    calls = 0
    def guard(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise capture.CaptureRefusal("head_changed")
    monkeypatch.setattr(capture, "_guard", guard)
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    opener = Opener([])
    with pytest.raises(capture.ActionSupplementCaptureRefusal):
        run(tmp_path, opener)
    assert (tmp_path / "attempt-01.started.json").exists()
    assert not opener.requests


@pytest.mark.parametrize("raw", [
    b'{"status":"OK","results":[],"next_url":"https://evil.invalid/secret"}',
    b'{"status":"NOT_AUTHORIZED","results":[]}',
    b'{"status":"OK","results":[],"count":1}',
    b'{"status":"OK","status":"OK","results":[]}',
    b'{"status":"OK","results":[NaN]}',
])
@_POSIX_CAPTURE_ONLY
def test_invalid_page_is_retained_but_never_followed_or_used_for_complete_report(tmp_path, offline, raw):
    opener = Opener([Response(raw=raw)])
    with pytest.raises(capture.ActionSupplementCaptureRefusal):
        run(tmp_path, opener)
    assert len(opener.requests) == 1
    assert (tmp_path / "attempt-01.raw").read_bytes() == raw
    assert not (tmp_path / "supplement.private.json").exists()


def test_existing_receipt_prevents_budget_restart(tmp_path, offline):
    (tmp_path / "attempt-01.started.json").write_bytes(b"preserved")
    opener = Opener([])
    with pytest.raises(capture.CaptureRefusal):
        run(tmp_path, opener)
    assert not opener.requests
    assert (tmp_path / "attempt-01.started.json").read_bytes() == b"preserved"


@pytest.mark.usefixtures("portable_capture_platform")
def test_protocol_tamper_refuses_before_receipt_or_http(tmp_path, offline, monkeypatch):
    original = contract.supplement_protocol()
    original["maximum_requests"] = 63
    monkeypatch.setattr(contract, "supplement_protocol", lambda: original)
    opener = Opener([])
    with pytest.raises(capture.ActionSupplementCaptureRefusal, match="inventory"):
        run(tmp_path, opener)
    assert not list(tmp_path.iterdir()) and not opener.requests


@pytest.mark.parametrize("clock", ["2026-10-11T22:00:12", "2026-10-11T22:00:12+00:00", "2026-10-11T23:00:12+01:00", None])
def test_run_name_comes_from_canonical_actual_start_clock(clock):
    with pytest.raises(capture.ActionSupplementCaptureRefusal):
        capture._run_id(clock)


def test_run_name_and_start_clock_are_same_second():
    assert capture._run_id(NOW) == "massive-actions-20261011T220012Z"


@pytest.mark.parametrize("key", [None, "", "short", "x" * 513, "long-key-with\nnewline", "long-key-with space"])
@pytest.mark.usefixtures("portable_capture_platform")
def test_only_named_existing_environment_key_can_be_used(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("MASSIVE_API_KEY", key)
    with pytest.raises(capture.ActionSupplementCaptureRefusal, match="unavailable"):
        capture._existing_key()


@pytest.mark.parametrize("mode", [0o644, 0o400, 0o777])
@_POSIX_CAPTURE_ONLY
def test_private_source_reader_refuses_unprotected_file(tmp_path, mode):
    tmp_path.chmod(0o700)
    path = tmp_path / "known.json"
    path.write_bytes(b"{}")
    path.chmod(mode)
    with pytest.raises(capture.ActionSupplementCaptureRefusal, match="protection"):
        capture._protected_bytes(path, 32)


@_POSIX_CAPTURE_ONLY
def test_private_source_reader_refuses_symlink_or_oversize(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / "known.json"
    path.write_bytes(b"{}")
    path.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(capture.ActionSupplementCaptureRefusal, match="symlink"):
        capture._protected_bytes(link, 32)
    with pytest.raises(capture.ActionSupplementCaptureRefusal, match="protection"):
        capture._protected_bytes(path, 1)


def test_failed_cli_guard_never_reads_key_source_or_builds_opener(monkeypatch, capsys):
    def guard(*args):
        raise capture.CaptureRefusal("head_changed")
    monkeypatch.setattr(capture, "_guard", guard)
    monkeypatch.setattr(capture, "_existing_key", lambda: pytest.fail("must not read key"))
    monkeypatch.setattr(capture, "_rebuild_sharadar", lambda *args: pytest.fail("must not read source"))
    assert capture.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 2
    assert "head_changed" not in capsys.readouterr().out


@pytest.fixture
def fabricated_prior(monkeypatch, tmp_path):
    """In-memory receipts only: no private capture or provider rows read."""
    records = {}
    directory = tmp_path / capture.SHARADAR_SOURCE
    start = {"schema": "si-sharadar-qualification-start-v1", "code_head": capture.SHARADAR_CODE_HEAD,
             "protocol_sha256": capture.sharadar.PROTOCOL_SHA256, "started_at": NOW}
    records["started.json"] = start
    records["protocol.json"] = capture.sharadar.qualification_protocol()
    saved = {"retrieved_at": NOW, "fabricated_only": True}
    records["qualification.private.json"] = saved
    for ordinal, rid in enumerate(capture.sharadar.REQUEST_IDS, 1):
        name = f"attempt-{ordinal:02d}"
        raw = b"{}"
        records[name + ".raw"] = raw
        records[name + ".started.json"] = {
            "schema": "si-sharadar-request-start-v1", "attempt": ordinal, "request_id": rid,
            "request": capture.sharadar.sharadar_request(rid), "request_sha256": capture.sharadar.request_sha256(rid),
            "code_head": capture.SHARADAR_CODE_HEAD, "protocol_sha256": capture.sharadar.PROTOCOL_SHA256,
            "started_at": NOW}
        records[name + ".received.json"] = {
            "schema": "si-sharadar-response-receipt-v1", "attempt": ordinal, "request_id": rid,
            "request_sha256": capture.sharadar.request_sha256(rid), "raw_path": name + ".raw",
            "raw_sha256": hash_bytes(raw), "raw_bytes": len(raw), "http_status": 200,
            "content_type": "text/plain" if rid.startswith("schema-") else "application/json", "received_at": NOW}
    def blob(name):
        value = records[name]
        return value if type(value) is bytes else (canonical_json(value) + "\n").encode()
    monkeypatch.setattr(capture, "_protected_bytes", lambda path, maximum: blob(path.relative_to(directory).as_posix()))
    monkeypatch.setattr(capture, "SHARADAR_START_FILE_SHA256", hash_bytes(blob("started.json")))
    monkeypatch.setattr(capture, "SHARADAR_REPORT_FILE_SHA256", hash_bytes(blob("qualification.private.json")))
    class Rebuilt:
        def to_payload(self):
            return saved
    monkeypatch.setattr(capture.sharadar, "qualify_sharadar_companion", lambda *args, **kwargs: Rebuilt())
    return records, tmp_path, blob


@pytest.mark.parametrize("name,field,value", [
    ("attempt-01.started.json", "started_at", "2026-10-11T22:00:13Z"),
    ("attempt-01.received.json", "received_at", "2026-10-11T22:00:11Z"),
    ("qualification.private.json", "retrieved_at", "2026-10-11T22:00:11Z"),
    ("attempt-01.started.json", "schema", "uncommitted-inline-diagnostic"),
    ("attempt-01.received.json", "schema", "unbound-response"),
    ("attempt-01.started.json", "attempt", True),
    ("attempt-01.received.json", "attempt", True),
    ("attempt-02.started.json", "started_at", "2026-10-11T22:00:11Z"),
    ("attempt-01.received.json", "received_at", "2026-10-11T22:00:12"),
])
@pytest.mark.usefixtures("portable_capture_platform")
def test_prior_receipt_chronology_schema_and_exact_ordinal_are_required(fabricated_prior, monkeypatch, name, field, value):
    records, root, blob = fabricated_prior
    records[name][field] = value
    if name == "qualification.private.json":
        monkeypatch.setattr(capture, "SHARADAR_REPORT_FILE_SHA256", hash_bytes(blob(name)))
    with pytest.raises(capture.ActionSupplementCaptureRefusal):
        capture._rebuild_sharadar(root)


@pytest.mark.usefixtures("portable_capture_platform")
def test_fabricated_equal_clocks_are_valid_without_inventing_resolution(fabricated_prior):
    _, root, _ = fabricated_prior
    assert capture._rebuild_sharadar(root).to_payload()["fabricated_only"] is True


@_POSIX_CAPTURE_ONLY
def test_cli_later_directory_cannot_reset_whole_round_budget(tmp_path, monkeypatch, offline):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(capture, "_git", lambda root, *args: args[-1])
    monkeypatch.setattr(capture, "_existing_key", lambda: KEY)
    monkeypatch.setattr(capture, "_rebuild_sharadar", lambda root: object())
    calls = []
    monkeypatch.setattr(capture, "_capture", lambda *args, **kwargs: calls.append(args) or {"status": "fabricated_capture"})
    assert capture.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 0
    monkeypatch.setattr(capture, "_utc_now", lambda: "2026-10-11T22:00:14Z")
    assert capture.main(["--expected-head", "d" * 40, "--expected-remote", REMOTE]) == 2
    assert len(calls) == 1
    claims = list((tmp_path / capture.CAPTURE_PARENT).glob("budget-*.json"))
    assert len(claims) == 1 and claims[0].stat().st_mode & 0o777 == 0o600
    assert json.loads(claims[0].read_bytes())["code_head"] == HEAD


@pytest.mark.usefixtures("portable_capture_platform")
def test_cli_missing_named_key_is_precise_zero_request_preflight(tmp_path, monkeypatch, offline, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(capture, "_git", lambda root, *args: args[-1])
    monkeypatch.setattr(capture, "_rebuild_sharadar", lambda root: object())
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.setattr(capture.urllib.request, "build_opener", lambda *args: pytest.fail("no transport before credential preflight"))
    assert capture.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 2
    public = json.loads(capsys.readouterr().out)
    assert public["code"] == "existing_massive_key_unavailable"
    assert public["http_status"] is None and public["backtest_result_exists"] is False
    assert not (tmp_path / capture.CAPTURE_PARENT).exists()
