"""Fabricated source-only transport checks, never protected actual inputs."""
from __future__ import annotations

import io
import json
import os
from types import SimpleNamespace
import urllib.error

import pytest
from short_interest_capture_fixtures import portable_capture_platform

from data.hashing import canonical_json, hash_bytes, hash_payload
import scripts.qualify_short_interest_class_denominator as capture
import scripts.qualify_finra_short_interest as base_capture

_POSIX_CAPTURE_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason="protected capture requires POSIX ownership/mode/no-follow semantics; SI-CR-WIN-20261012-002",
)
KEY = "fabricated-only-key-for-offline-tests"
HEAD, REMOTE = "a" * 40, "b" * 40
NOW = "2026-10-13T22:00:12.123456Z"


class Response:
    def __init__(self, raw=b'{"status":"OK","results":null}', status=200, content_type="application/json"):
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


@pytest.fixture
def offline(monkeypatch):
    guards = []
    monkeypatch.setattr(capture, "_guard", lambda *args: guards.append(args))
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    return guards


def run(tmp_path, opener):
    return capture._capture(tmp_path, tmp_path, KEY, opener, head=HEAD, remote=REMOTE, started_at=NOW)


@_POSIX_CAPTURE_ONLY
def test_thirty_frozen_attempts_before_transport_header_only_secret_and_private_outputs(tmp_path, offline):
    ordinal = 0
    def before(request):
        nonlocal ordinal
        ordinal += 1
        record = json.loads((tmp_path / f"attempt-{ordinal:02d}.started.json").read_bytes())
        spec = capture.contract.massive_request(capture.contract.REQUEST_IDS[ordinal - 1])
        assert record["attempt"] == ordinal
        assert record["request"] == spec
        assert record["request_sha256"] == hash_payload(spec)
        assert len(offline) == 5 * (ordinal - 1) + 3
        assert request.get_header("Authorization") == "Bearer " + KEY
        assert KEY not in request.full_url
    opener = Opener([Response() for _ in range(30)], before)
    result = run(tmp_path, opener)
    assert len(opener.requests) == 30
    assert len(offline) == 152
    report_bytes = (tmp_path / "qualification.private.json").read_bytes()
    report = json.loads(report_bytes)
    assert len(report["responses"]) == 30
    assert result["private_report_sha256"] == report["report_sha256"]
    assert result["private_report_bytes_sha256"] == hash_bytes(report_bytes)
    assert result["outcome_looks"] == result["qc_attempts"] == 0
    assert result["backtest_result_exists"] is False
    assert not {"http_attempts", "rows", "coverage", "responses", "source_fitness"} & set(result)
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in tmp_path.iterdir())
    assert not any(KEY.encode() in path.read_bytes() for path in tmp_path.iterdir())


@_POSIX_CAPTURE_ONLY
def test_404_retains_status_only_does_not_read_error_body_or_relabel_as_empty_provider_body(tmp_path, offline):
    error_body = io.BytesIO(("private-body-" + KEY).encode())
    missing = urllib.error.HTTPError("https://unused.invalid", 404, "ignored", {}, error_body)
    opener = Opener([missing] + [Response() for _ in range(29)])
    result = run(tmp_path, opener)
    assert result["status"] == "capture_complete" and len(opener.requests) == 30
    assert error_body.tell() == 0
    receipt = json.loads((tmp_path / "attempt-01.received.json").read_bytes())
    assert receipt["http_status"] == 404 and receipt["body_observed"] is False
    assert receipt["error_body_read"] is False
    assert receipt["raw_path"] is receipt["raw_bytes"] is receipt["raw_sha256"] is None
    assert not (tmp_path / "attempt-01.raw").exists()
    response = json.loads((tmp_path / "qualification.private.json").read_bytes())["responses"][0]
    assert response["body_observed"] is False and response["source_file_sha256"] is None
    assert response["placeholder_byte_sha256"] == hash_bytes(b"")


@pytest.mark.parametrize("status", [204, 301, 401, 403, 429, 500, True, "external-secret-status"])
@_POSIX_CAPTURE_ONLY
def test_non_404_refusal_stops_no_response_read_no_retry(tmp_path, offline, status):
    response = Response(status=status)
    opener = Opener([response])
    with pytest.raises(capture.ClassDenominatorCaptureRefusal):
        run(tmp_path, opener)
    assert len(opener.requests) == 1 and response.reads == 0
    assert (tmp_path / "attempt-01.started.json").exists()
    assert (tmp_path / "attempt-01.refused.json").exists()
    assert not (tmp_path / "attempt-01.raw").exists()
    assert not (tmp_path / "qualification.private.json").exists()


@pytest.mark.parametrize("error", [urllib.error.URLError("secret-error-text"), TimeoutError("secret-error-text")])
@_POSIX_CAPTURE_ONLY
def test_transport_failure_attempt_is_consumed_and_fixed_code_only(tmp_path, offline, error):
    opener = Opener([error])
    with pytest.raises(capture.ClassDenominatorCaptureRefusal, match="network_failure"):
        run(tmp_path, opener)
    assert len(opener.requests) == 1
    assert b"secret-error-text" not in (tmp_path / "attempt-01.refused.json").read_bytes()
    assert not (tmp_path / "attempt-02.started.json").exists()


@pytest.mark.parametrize("raw,ctype", [
    (KEY.encode(), "application/json"),
    (json.dumps({"k": KEY}).replace("f", "\\u0066").encode(), "application/json"),
    (b'{"status":"OK","results":null}', "application/json; key=" + KEY),
])
@_POSIX_CAPTURE_ONLY
def test_credential_echo_refuses_before_any_response_persistence(tmp_path, offline, raw, ctype):
    with pytest.raises(capture.ClassDenominatorCaptureRefusal, match="credential_echo"):
        run(tmp_path, Opener([Response(raw=raw, content_type=ctype)]))
    assert not (tmp_path / "attempt-01.raw").exists()
    assert not (tmp_path / "attempt-01.received.json").exists()
    assert not any(KEY.encode() in path.read_bytes() for path in tmp_path.iterdir())


@_POSIX_CAPTURE_ONLY
def test_malformed_or_next_url_rows_retained_without_following_response_links(tmp_path, offline):
    raw = b'{"status":"OK","next_url":"https://evil.invalid/secret","results":null}'
    opener = Opener([Response(raw=raw)] + [Response() for _ in range(29)])
    run(tmp_path, opener)
    assert len(opener.requests) == 30
    assert (tmp_path / "attempt-01.raw").read_bytes() == raw
    item = json.loads((tmp_path / "qualification.private.json").read_bytes())["responses"][0]
    assert item["status"] == "malformed" and item["normalized"] is None
    assert all("evil.invalid" not in request.full_url for request in opener.requests)


@_POSIX_CAPTURE_ONLY
def test_guard_recheck_after_attempt_start_stops_before_transport(tmp_path, monkeypatch):
    calls = 0
    def guard(*args):
        nonlocal calls
        calls += 1
        if calls >= 3:
            raise capture.CaptureRefusal("changed")
    monkeypatch.setattr(capture, "_guard", guard)
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    opener = Opener([])
    with pytest.raises(capture.CaptureRefusal):
        run(tmp_path, opener)
    assert (tmp_path / "attempt-01.started.json").exists()
    assert not opener.requests


@pytest.mark.usefixtures("portable_capture_platform")
def test_protocol_tamper_refuses_before_any_publication_or_transport(tmp_path, offline, monkeypatch):
    protocol = capture.contract.denominator_protocol()
    protocol["maximum_requests"] = 31
    monkeypatch.setattr(capture.contract, "denominator_protocol", lambda: protocol)
    opener = Opener([])
    with pytest.raises(capture.ClassDenominatorCaptureRefusal, match="inventory"):
        run(tmp_path, opener)
    assert not list(tmp_path.iterdir()) and not opener.requests


@_POSIX_CAPTURE_ONLY
def test_existing_attempt_file_cannot_be_overwritten_on_local_restart(tmp_path, offline):
    existing = tmp_path / "attempt-01.started.json"
    existing.write_bytes(b"preserved")
    opener = Opener([])
    with pytest.raises(capture.CaptureRefusal):
        run(tmp_path, opener)
    assert existing.read_bytes() == b"preserved" and not opener.requests


@_POSIX_CAPTURE_ONLY
def test_whole_budget_independent_of_head_time_and_run_directory(tmp_path, offline):
    parent = tmp_path / "protected"
    parent.mkdir(mode=0o700)
    first, second = parent / "first", parent / "second"
    first.mkdir(mode=0o700)
    second.mkdir(mode=0o700)
    capture._claim_budget(tmp_path, first, head=HEAD, remote=REMOTE, started_at=NOW)
    claim = parent / capture._budget_name()
    prior = claim.read_bytes()
    with pytest.raises(capture.ClassDenominatorCaptureRefusal, match="already_claimed"):
        capture._claim_budget(tmp_path, second, head="c" * 40, remote="d" * 40,
                              started_at="2026-10-14T22:00:12Z")
    assert claim.read_bytes() == prior


@pytest.fixture
def fake_run(monkeypatch, offline):
    trace = []
    monkeypatch.setattr(capture, "_source_preflight", lambda root: trace.append("source") or capture._source_pins())
    monkeypatch.setattr(capture, "_code_identity", lambda *args: "c" * 64)
    monkeypatch.setattr(capture, "_existing_key", lambda: trace.append("key") or KEY)
    monkeypatch.setattr(capture, "_git", lambda *args: args[-1])
    monkeypatch.setattr(capture.urllib.request, "build_opener", lambda *args: Opener([Response() for _ in range(30)]))
    return trace


@_POSIX_CAPTURE_ONLY
def test_run_freezes_before_requests_and_rerun_never_mutates_old_owned_output(tmp_path, fake_run):
    capture._run(tmp_path, head=HEAD, remote=REMOTE)
    target = tmp_path / capture.CAPTURE_PARENT / capture._run_id(NOW)
    before = {path.name: path.read_bytes() for path in target.iterdir()}
    assert fake_run == ["source", "key"]
    started = json.loads((target / "started.json").read_bytes())
    assert started["source_pins"] == capture._source_pins()
    assert started["code_identity_sha256"] == "c" * 64
    with pytest.raises(FileExistsError):
        capture._run(tmp_path, head=HEAD, remote=REMOTE)
    assert {path.name: path.read_bytes() for path in target.iterdir()} == before


@_POSIX_CAPTURE_ONLY
def test_new_run_budget_refusal_owned_only_new_directory(tmp_path, fake_run, monkeypatch):
    capture._run(tmp_path, head=HEAD, remote=REMOTE)
    first = tmp_path / capture.CAPTURE_PARENT / capture._run_id(NOW)
    before = {path.name: path.read_bytes() for path in first.iterdir()}
    later = "2026-10-14T22:00:12Z"
    monkeypatch.setattr(capture, "_utc_now", lambda: later)
    with pytest.raises(capture.ClassDenominatorCaptureRefusal, match="already_claimed"):
        capture._run(tmp_path, head="c" * 40, remote=REMOTE)
    second = tmp_path / capture.CAPTURE_PARENT / capture._run_id(later)
    assert {path.name: path.read_bytes() for path in first.iterdir()} == before
    assert set(path.name for path in second.iterdir()) == {"refused.json"}


@pytest.mark.parametrize("gap", ["enclosing_start", "between_attempts", "request_response", "report", "completion"])
@_POSIX_CAPTURE_ONLY
def test_capture_chronology_binds_enclosing_and_attempt_start_response_report_and_completion(tmp_path, fake_run, monkeypatch, gap):
    earlier = "2026-10-13T22:00:11.123456Z"
    later = "2026-10-13T22:00:13.123456Z"
    clocks = [NOW] * 63  # enclosing start, thirty start/response pairs, report, completion
    if gap == "enclosing_start":
        clocks[1] = earlier
    elif gap == "between_attempts":
        clocks[2:] = [later] * 61
        clocks[3] = NOW
    elif gap == "request_response":
        clocks[1] = later
    elif gap == "report":
        clocks[61] = earlier
    else:
        clocks[61] = later
    values = iter(clocks)
    monkeypatch.setattr(capture, "_utc_now", lambda: next(values, later))
    with pytest.raises(capture.CaptureRefusal):
        capture._run(tmp_path, head=HEAD, remote=REMOTE)
    directory = tmp_path / capture.CAPTURE_PARENT / capture._run_id(NOW)
    assert not (directory / "completed.json").exists()
    assert (directory / "refused.json").exists()
    if gap == "request_response":
        assert (directory / "attempt-01.raw").exists()
        assert (directory / "attempt-01.received.json").exists()


@pytest.mark.parametrize("entry", ["_run", "_capture", "_source_preflight", "_claim_budget", "main"])
def test_unsupported_host_refuses_before_source_secret_transport_or_publication(monkeypatch, tmp_path, entry, capsys):
    class Unsupported:
        name = "nt"
        getuid = None
        O_NOFOLLOW = None
        O_NONBLOCK = None
        def __getattr__(self, name):
            raise AssertionError("host checked unsupported capabilities after first refusal")
    monkeypatch.setattr(base_capture, "os", Unsupported())
    for name in ("_guard", "_source_preflight", "_existing_key", "_publish", "_publish_json"):
        if name != entry:
            monkeypatch.setattr(capture, name, lambda *args, **kwargs: pytest.fail("sensitive boundary reached"))
    monkeypatch.setattr(capture.finalizer, "_reload", lambda *args: pytest.fail("source reloader reached"))
    monkeypatch.setattr(capture.native_builder, "_source_index", lambda *args: pytest.fail("source index reached"))
    if entry == "main":
        monkeypatch.setattr(capture, "_run", lambda *args, **kwargs: pytest.fail("runtime reached before host guard"))
    opener = Opener([])
    if entry == "main":
        assert capture.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 2
        assert json.loads(capsys.readouterr().out)["code"] == "protected_capture_platform_unavailable"
    else:
        with pytest.raises(capture.CapturePlatformRefusal):
            if entry == "_run":
                capture._run(tmp_path, head=HEAD, remote=REMOTE)
            elif entry == "_capture":
                run(tmp_path, opener)
            elif entry == "_claim_budget":
                capture._claim_budget(tmp_path, tmp_path, head=HEAD, remote=REMOTE, started_at=NOW)
            else:
                capture._source_preflight(tmp_path)
    assert not opener.requests and not list(tmp_path.iterdir())


@pytest.fixture
def protected_source(tmp_path, monkeypatch):
    anchor = "2026-10-12T06:00:38.129298Z"
    archives = [{"table": "fixture", "archive_sha256": "e" * 64}]
    source = SimpleNamespace(capture_identity_sha256=hash_payload(archives), report_payload_sha256="f" * 64)
    trace = []
    monkeypatch.setattr(capture.finalizer, "_reload", lambda root: trace.append("master") or ((), anchor))
    monkeypatch.setattr(capture.native_builder, "_source_index", lambda *args: trace.append("parts") or (source, "d" * 64))
    monkeypatch.setattr(capture.native_builder, "_archives", lambda *args: archives)
    monkeypatch.setattr(capture.companion_reader, "_rebuild_sharadar", lambda *args: trace.append("companion"))
    native = {"source_report_sha256": source.report_payload_sha256,
              "source_capture_identity_sha256": source.capture_identity_sha256,
              "source_retrieved_at": anchor}
    native["index_sha256"] = hash_payload(native)
    observations = {"native_index_sha256": native["index_sha256"]}
    observations["binding_sha256"] = hash_payload(observations)
    native_raw, observations_raw = (canonical_json(value).encode() for value in (native, observations))
    monkeypatch.setattr(capture, "NATIVE_INDEX_PAYLOAD_SHA256", native["index_sha256"])
    monkeypatch.setattr(capture, "OBSERVATION_PAYLOAD_SHA256", observations["binding_sha256"])
    monkeypatch.setattr(capture, "NATIVE_INDEX_BYTES_SHA256", hash_bytes(native_raw))
    monkeypatch.setattr(capture, "OBSERVATION_BYTES_SHA256", hash_bytes(observations_raw))
    directory = capture._prepare_capture_directory(tmp_path / capture.native_builder.OUTPUT)
    capture._publish(directory, "native.index.private.json", native_raw)
    capture._publish(directory, "observations.private.json", observations_raw)
    fixed = {
        "code_head": capture.NATIVE_SOURCE_HEAD,
        "source_index_sha256": capture.native_builder.SOURCE_INDEX_SHA256,
        "source_index_bytes_sha256": "d" * 64,
        "source_capture_inventory_sha256": capture.finalizer.SOURCE_INVENTORY_SHA256,
        "source_capture_budget_sha256": capture.finalizer.BUDGET_SHA256,
        "source_report_payload_sha256": source.report_payload_sha256,
        "source_capture_identity_sha256": source.capture_identity_sha256,
        "source_reconstruction_anchor": anchor, "source_archive_pins": archives,
        "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0,
        "qc_attempts": 0, "backtest_result_exists": False,
        "started_at": capture.NATIVE_STARTED_AT,
    }
    capture._publish_json(directory, "started.json", {**fixed, "schema": "si-native-master-offline-start-v1"})
    capture._publish_json(directory, "completed.json", {
        **fixed, "schema": "si-native-master-offline-complete-v1", "status": "native_master_offline_complete",
        "native_index_bytes_sha256": hash_bytes(native_raw), "native_observation_bytes_sha256": hash_bytes(observations_raw),
        "completed_at": capture.NATIVE_COMPLETED_AT,
    })
    return directory, trace


@_POSIX_CAPTURE_ONLY
def test_original_spent_master_parts_native_byte_pins_and_companion_before_secret(tmp_path, protected_source):
    directory, trace = protected_source
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    assert capture._source_preflight(tmp_path) == capture._source_pins()
    assert trace == ["master", "parts", "companion"]
    assert before == {path.name: path.read_bytes() for path in directory.iterdir()}


@pytest.mark.parametrize("change", ["bytes", "native_pin", "observation_pin", "extra", "mode", "clock", "counter_type"])
@_POSIX_CAPTURE_ONLY
def test_source_changed_or_unprotected_refuses_before_key_or_new_output(tmp_path, protected_source, monkeypatch, change):
    directory, trace = protected_source
    if change == "bytes":
        path = directory / "native.index.private.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif change == "native_pin":
        monkeypatch.setattr(capture, "NATIVE_INDEX_BYTES_SHA256", "e" * 64)
    elif change == "observation_pin":
        monkeypatch.setattr(capture, "OBSERVATION_BYTES_SHA256", "e" * 64)
    elif change == "extra":
        capture._publish_json(directory, "unknown.json", {})
    elif change == "mode":
        (directory / "observations.private.json").chmod(0o644)
    else:
        path = directory / "completed.json"
        record = json.loads(path.read_bytes())
        record["completed_at" if change == "clock" else "qc_attempts"] = (
            "2026-10-12T07:24:30Z" if change == "clock" else False)
        path.write_bytes((canonical_json(record) + "\n").encode())
    monkeypatch.setattr(capture, "_existing_key", lambda: pytest.fail("key read before custody verification"))
    with pytest.raises(capture.CaptureRefusal):
        capture._source_preflight(tmp_path)
    assert trace == ["master", "parts"]
    assert not (tmp_path / capture.CAPTURE_PARENT).exists()
