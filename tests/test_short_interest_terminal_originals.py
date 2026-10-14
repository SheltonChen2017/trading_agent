"""Fabricated SEC-original selection/custody only; no provider or secrets."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import urllib.error

import pytest
from short_interest_capture_fixtures import portable_capture_platform

from data.hashing import canonical_json, hash_bytes, hash_payload
import scripts.verify_short_interest_terminal_originals as capture

_POSIX_CAPTURE_ONLY = pytest.mark.skipif(not hasattr(os, "getuid"),
    reason="protected storage requires POSIX ownership/mode/no-follow; SI-CR-WIN-20261012-002")
HEAD, REMOTE = "a" * 40, "b" * 40
NOW = "2026-10-13T23:00:12Z"
BEFORE = "2026-10-13T23:00:00Z"


def source_value():
    protocol = capture.terminal_reader.disclosures.freeze_disclosure_protocol(
        ("0001234567", "0002345678"), source_class_report_sha256=capture.terminal_reader.CLASS_REPORT_SHA256)
    responses = []
    for rid in capture.terminal_reader.disclosures.REQUEST_IDS:
        kind, case = rid.split("-", 1)
        cik, date = ("0001234567", "2022-10-27") if case == "TWTR" else ("0002345678", "2023-05-01")
        accession = cik + "-22-000001" if case == "TWTR" else cik + "-23-000001"
        row = {"accession_number": accession, "cik": cik, "filing_date": date, "form_type": "8-K",
               "filing_url": "https://www.sec.gov/Archives/edgar/data/" + str(int(cik)) + "/" + accession.replace("-", "") + "/original.htm"}
        if kind == "text":
            row["items_text"] = "Item 2.01 Completion of merger or receivership. Fabricated testing only."
        raw = canonical_json({"status": "OK", "results": [row], "count": 1}).encode()
        responses.append(capture.terminal_reader.disclosures.CapturedDisclosureResponse(rid, protocol.request_sha256(rid), raw, BEFORE))
    report = capture.terminal_reader.disclosures.qualify_terminal_disclosure(protocol, tuple(responses), retrieved_at=BEFORE)
    return {"report": report.to_payload(), "protocol": protocol, "completed_at": BEFORE}, tuple(responses)


@pytest.fixture
def frozen(monkeypatch):
    source, _ = source_value()
    monkeypatch.setattr(capture, "SOURCE_PROTOCOL_SHA256", source["protocol"].sha256)
    monkeypatch.setattr(capture, "SOURCE_REPORT_SHA256", source["report"]["report_sha256"])
    return source


def test_selects_only_observed_core_text_exact_urls_and_declares_no_economics(frozen):
    protocol = capture.build_protocol(frozen)
    assert [row["request_id"] for row in protocol["requests"]] == ["original-TWTR", "original-FRC"]
    assert protocol["maximum_attempts"] == 2 and protocol["missing_cases"] == []
    assert all(row["headers"] == {"Accept": capture.ACCEPT, "User-Agent": capture.USER_AGENT} for row in protocol["requests"])
    assert protocol["outcome_looks"] == protocol["qc_attempts"] == 0
    assert protocol["backtest_result_exists"] is False


def test_mutated_report_cannot_redirect_to_different_SEC_document_after_old_hash(frozen):
    # The replacement stays on SEC so an origin-only check is insufficient.
    table = next(t for t in frozen["report"]["tables"] if t["request_id"] == "text-TWTR")
    table["records"][0]["metadata"]["filing_url"] = "https://www.sec.gov/Archives/edgar/data/999999/other.htm"
    with pytest.raises(capture.TerminalOriginalCaptureRefusal):
        capture.build_protocol(frozen)


@pytest.mark.parametrize("url", [
    "http://www.sec.gov/Archives/edgar/data/123/one.htm", "https://evil.invalid/Archives/one.htm",
    "https://www.sec.gov:443/Archives/one.htm", "https://user@www.sec.gov/Archives/one.htm",
    "https://www.sec.gov/Archives/../one.htm", "https://www.sec.gov/Archives//one.htm",
    "https://www.sec.gov/Archives/%2e%2e/one.htm", "https://www.sec.gov/Archives/one.htm?follow=1",
    "https://www.sec.gov/Archives/one.htm#section",
])
def test_only_exact_safe_HTTPS_SEC_Archives_url_is_eligible(url):
    with pytest.raises(capture.TerminalOriginalCaptureRefusal):
        capture._safe_url(url)


def test_user_agent_must_be_exact_honest_frozen_value(frozen, monkeypatch):
    monkeypatch.setattr(capture, "USER_AGENT", "invented-contact-or-browser-impersonation")
    with pytest.raises(capture.TerminalOriginalCaptureRefusal, match="user_agent_changed"):
        capture.build_protocol(frozen)


def reseal(frozen, monkeypatch):
    report = frozen["report"]
    digest = hash_payload({name: value for name, value in report.items() if name != "report_sha256"})
    report["report_sha256"] = digest
    monkeypatch.setattr(capture, "SOURCE_REPORT_SHA256", digest)


def test_deterministic_earliest_date_accession_not_first_page_order(frozen, monkeypatch):
    table = next(t for t in frozen["report"]["tables"] if t["request_id"] == "text-TWTR")
    original = table["records"][0]
    earlier = json.loads(canonical_json(original))
    earlier["metadata"].update(filing_date="2022-10-26", accession_number="0001234567-22-000000",
                               filing_url="https://www.sec.gov/Archives/edgar/data/1234567/earlier.htm")
    table["records"].append(earlier)
    reseal(frozen, monkeypatch)
    target = capture.build_protocol(frozen)["requests"][0]
    assert target["filing_date"] == "2022-10-26" and target["url"].endswith("/earlier.htm")


def test_one_missing_case_is_retained_without_current_symbol_or_document_fallback(frozen, monkeypatch):
    table = next(t for t in frozen["report"]["tables"] if t["request_id"] == "text-FRC")
    table["records"][0]["items_text"] = "Fabricated ordinary report with no selected item or event."
    reseal(frozen, monkeypatch)
    protocol = capture.build_protocol(frozen)
    assert [item["request_id"] for item in protocol["requests"]] == ["original-TWTR"]
    assert protocol["missing_cases"] == [{"case": "FRC", "code": "terminal_original_candidate_unavailable"}]
    assert protocol["maximum_attempts"] == 1
    next(t for t in frozen["report"]["tables"] if t["request_id"] == "text-TWTR")["records"][0]["items_text"] = "No eligible item."
    reseal(frozen, monkeypatch)
    with pytest.raises(capture.CaptureRefusal, match="candidate_unavailable"):
        capture.build_protocol(frozen)


@pytest.fixture
def offline(frozen, monkeypatch):
    protocol = capture.build_protocol(frozen)
    monkeypatch.setattr(capture, "EXPECTED_PROTOCOL_SHA256", hash_payload(protocol))
    guards = []
    monkeypatch.setattr(capture, "_guard", lambda *args: guards.append(args))
    monkeypatch.setattr(capture, "_utc_now", lambda: NOW)
    return protocol, guards


class Response:
    def __init__(self, raw=b"<html>Fabricated original source</html>", status=200, media="text/html"):
        self.raw, self.status, self.headers, self.reads = raw, status, {"Content-Type": media}, 0
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, maximum):
        self.reads += 1
        return self.raw[:maximum]


class Opener:
    def __init__(self, responses, before=None):
        self.responses, self.before, self.requests = iter(responses), before, []
    def open(self, request, timeout):
        if self.before:
            self.before(request)
        self.requests.append(request)
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def run(tmp_path, protocol, opener):
    return capture._capture(tmp_path, tmp_path, protocol, opener, head=HEAD, remote=REMOTE, started_at=NOW)


@_POSIX_CAPTURE_ONLY
def test_exact_anonymous_requests_have_durable_started_receipts_and_only_private_evidence(tmp_path, offline):
    protocol, _ = offline
    def before(request):
        ordinal = len(opener.requests) + 1
        started = json.loads((tmp_path / f"attempt-{ordinal:02d}.started.json").read_bytes())
        assert started["request_sha256"] == hash_payload(protocol["requests"][ordinal - 1])
        assert request.full_url == protocol["requests"][ordinal - 1]["url"]
        assert request.get_header("Authorization") is None
        assert request.get_header("User-agent") == capture.USER_AGENT
        assert request.get_header("Accept") == capture.ACCEPT
    opener = Opener([Response(), Response()], before)
    result = run(tmp_path, protocol, opener)
    assert result["status"] == "capture_complete" and result["http_attempts"] == 2
    assert "documents" not in result and "issuer_CIK" not in result and "url" not in result
    evidence = json.loads((tmp_path / "originals.private.json").read_bytes())
    assert evidence["terminal_economics_admitted"] is False
    assert evidence["payment_cash_settlement_verified"] is False
    assert evidence["outcome_looks"] == evidence["qc_attempts"] == 0
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in tmp_path.iterdir())


@_POSIX_CAPTURE_ONLY
def test_caller_mutation_during_first_transport_cannot_change_frozen_second_descriptor(tmp_path, offline):
    protocol, _ = offline
    original_urls = [request["url"] for request in protocol["requests"]]
    def before(request):
        if not opener.requests:
            protocol["requests"][1]["url"] = "https://www.sec.gov/Archives/edgar/data/999999/other.htm"
    opener = Opener([Response(), Response()], before)
    run(tmp_path, protocol, opener)
    assert [request.full_url for request in opener.requests] == original_urls


@pytest.mark.parametrize("error", [
    urllib.error.HTTPError("https://unused.invalid", 403, "never log", {}, io.BytesIO(b"unread-block-page")),
    urllib.error.URLError("private-external-error"), TimeoutError("private-external-error"),
])
@_POSIX_CAPTURE_ONLY
def test_403_or_transport_failure_consumes_attempt_and_stops_without_bypass(tmp_path, offline, error):
    protocol, _ = offline
    opener = Opener([error])
    with pytest.raises(capture.CaptureRefusal):
        run(tmp_path, protocol, opener)
    assert len(opener.requests) == 1
    assert set(path.name for path in tmp_path.iterdir()) == {"attempt-01.started.json", "attempt-01.refused.json"}
    assert b"private-external-error" not in (tmp_path / "attempt-01.refused.json").read_bytes()
    if isinstance(error, urllib.error.HTTPError):
        assert error.fp.tell() == 0


@pytest.mark.parametrize("raw,media", [(b"", "text/html"), (b"{}", "application/json")])
@_POSIX_CAPTURE_ONLY
def test_empty_or_unexpected_media_is_retained_and_refused_not_original_evidence(tmp_path, offline, raw, media):
    protocol, _ = offline
    with pytest.raises(capture.CaptureRefusal, match="original_body_or_media_refused"):
        run(tmp_path, protocol, Opener([Response(raw=raw, media=media)]))
    assert (tmp_path / "attempt-01.raw").read_bytes() == raw
    assert not (tmp_path / "completed.json").exists()


@pytest.mark.parametrize("gap", ["enclosing", "response", "between", "report", "completion"])
@_POSIX_CAPTURE_ONLY
def test_all_capture_clock_edges_fail_closed(tmp_path, offline, monkeypatch, gap):
    protocol, _ = offline
    earlier, later = "2026-10-13T23:00:11Z", "2026-10-13T23:00:13Z"
    clocks = [NOW] * 6
    if gap == "enclosing":
        clocks[0] = earlier
    elif gap == "response":
        clocks[0] = later
    elif gap == "between":
        clocks[1:] = [later] * 5
        clocks[2] = NOW
    elif gap == "report":
        clocks[4] = earlier
    else:
        clocks[4] = later
    values = iter(clocks)
    monkeypatch.setattr(capture, "_utc_now", lambda: next(values, later))
    with pytest.raises(capture.CaptureRefusal, match="chronology"):
        run(tmp_path, protocol, Opener([Response(), Response()]))
    assert not (tmp_path / "completed.json").exists()


@pytest.mark.usefixtures("portable_capture_platform")
def test_pending_protocol_refuses_before_any_source_transport_publication(tmp_path, frozen, monkeypatch):
    monkeypatch.setattr(capture, "_source", lambda *args, **kwargs: frozen)
    monkeypatch.setattr(capture, "_guard", lambda *args: None)
    monkeypatch.setattr(capture, "EXPECTED_PROTOCOL_SHA256", "PENDING")
    monkeypatch.setattr(capture, "_prepare_capture_directory", lambda *args: pytest.fail("output before freeze"))
    with pytest.raises(capture.CaptureRefusal, match="freeze_pending"):
        capture._run(tmp_path, head=HEAD, remote=REMOTE)


@pytest.fixture
def fake_run(frozen, offline, monkeypatch):
    monkeypatch.setattr(capture, "_source", lambda *args, **kwargs: frozen)
    monkeypatch.setattr(capture, "_git", lambda *args: args[-1])
    monkeypatch.setattr(capture, "_CODE_FILES", ())
    monkeypatch.setattr(capture.urllib.request, "build_opener", lambda *args: Opener([Response(), Response()]))


@_POSIX_CAPTURE_ONLY
def test_exclusive_output_and_global_budget_cannot_reopen_at_new_time_or_head(tmp_path, fake_run, monkeypatch):
    capture._run(tmp_path, head=HEAD, remote=REMOTE)
    parent = tmp_path / capture.CAPTURE_PARENT
    first = next(path for path in parent.iterdir() if path.is_dir())
    before = {path.name: path.read_bytes() for path in first.iterdir()}
    with pytest.raises(FileExistsError):
        capture._run(tmp_path, head=HEAD, remote=REMOTE)
    assert before == {path.name: path.read_bytes() for path in first.iterdir()}
    monkeypatch.setattr(capture, "_utc_now", lambda: "2026-10-14T23:00:12Z")
    with pytest.raises(capture.CaptureRefusal):
        capture._run(tmp_path, head="c" * 40, remote=REMOTE)
    second = next(path for path in parent.iterdir() if path.is_dir() and path != first)
    assert set(path.name for path in second.iterdir()) == {"refused.json"}
    assert before == {path.name: path.read_bytes() for path in first.iterdir()}


@pytest.mark.parametrize("entry", ["_source", "_historical_source_identity", "_read", "_publish_guarded", "_run", "_capture", "main"])
def test_unsupported_host_refuses_before_any_sensitive_entry(monkeypatch, tmp_path, entry):
    def deny():
        raise capture.CapturePlatformRefusal()
    monkeypatch.setattr(capture, "_require_capture_platform", deny)
    for name in ("_guard", "_protected_bytes", "_http", "_prepare_capture_directory"):
        monkeypatch.setattr(capture, name, lambda *args, **kwargs: pytest.fail("sensitive action reached"))
    if entry == "main":
        assert capture.main(["--expected-head", HEAD, "--expected-remote", REMOTE]) == 2
    else:
        with pytest.raises(capture.CapturePlatformRefusal):
            if entry == "_source":
                capture._source(tmp_path, head=HEAD, remote=REMOTE)
            elif entry == "_historical_source_identity":
                capture._historical_source_identity(tmp_path, head=HEAD, remote=REMOTE)
            elif entry == "_read":
                capture._read(tmp_path, tmp_path / "ignored", 1, head=HEAD, remote=REMOTE)
            elif entry == "_publish_guarded":
                capture._publish_guarded(tmp_path, tmp_path, "ignored", {}, head=HEAD, remote=REMOTE)
            elif entry == "_run":
                capture._run(tmp_path, head=HEAD, remote=REMOTE)
            else:
                capture._capture(tmp_path, tmp_path, {}, None, head=HEAD, remote=REMOTE, started_at=NOW)
    assert not list(tmp_path.iterdir())


@pytest.fixture
def stored_source(tmp_path, monkeypatch):
    value, responses = source_value()
    protocol = value["protocol"]
    report_raw = (canonical_json(value["report"]) + "\n").encode()
    monkeypatch.setattr(capture, "SOURCE_PROTOCOL_SHA256", protocol.sha256)
    monkeypatch.setattr(capture, "SOURCE_REPORT_SHA256", value["report"]["report_sha256"])
    monkeypatch.setattr(capture, "SOURCE_REPORT_BYTES_SHA256", hash_bytes(report_raw))
    guards = []
    monkeypatch.setattr(capture, "_guard", lambda *args: guards.append(args))
    monkeypatch.setattr(capture, "_historical_source_identity", lambda *args, **kwargs: "e" * 64)
    monkeypatch.setattr(capture.terminal_reader, "_source", lambda root: {"retrieved_at": "2026-10-13T22:59:58Z"})
    monkeypatch.setattr(capture.terminal_reader, "_protocol", lambda source: protocol)
    directory = capture._prepare_capture_directory(tmp_path / capture.SOURCE)
    began = "2026-10-13T22:59:59Z"
    capture._publish_json(directory, "protocol.private.json", protocol.to_payload())
    capture._publish_json(directory, "started.json", {
        "schema": "si-terminal-disclosure-start-v1", "code_head": capture.SOURCE_HEAD,
        "remote_head": REMOTE, "code_identity_sha256": "e" * 64,
        "protocol_sha256": protocol.sha256, "source_class_report_sha256": capture.terminal_reader.CLASS_REPORT_SHA256,
        "started_at": began, "maximum_attempts": 4, "outcome_looks": 0, "qc_attempts": 0})
    capture._publish_json(directory, "completed.json", {
        "schema": "si-terminal-disclosure-completion-v1", "status": "capture_complete",
        "code_head": capture.SOURCE_HEAD, "protocol_sha256": protocol.sha256, "http_attempts": 4,
        "private_report_sha256": value["report"]["report_sha256"], "completed_at": BEFORE,
        "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False})
    capture._publish_json(directory.parent, "budget-" + protocol.sha256 + ".json", {
        "schema": "si-terminal-disclosure-budget-v1", "code_head": capture.SOURCE_HEAD,
        "remote_head": REMOTE, "run_id": directory.name, "protocol_sha256": protocol.sha256,
        "maximum_attempts": 4, "started_at": began, "resumption_or_restart_allowed": False})
    for ordinal, response in enumerate(responses, 1):
        prefix, rid = f"attempt-{ordinal:02d}", response.request_id
        capture._publish_json(directory, prefix + ".started.json", {
            "schema": "si-terminal-disclosure-request-start-v1", "attempt": ordinal,
            "request_id": rid, "request": protocol.request(rid), "request_sha256": response.request_sha256,
            "code_head": capture.SOURCE_HEAD, "protocol_sha256": protocol.sha256,
            "started_at": began if ordinal == 1 else BEFORE})
        capture._publish(directory, prefix + ".raw", response.raw)
        capture._publish_json(directory, prefix + ".received.json", {
            "schema": "si-terminal-disclosure-response-v1", "attempt": ordinal,
            "request_id": rid, "request_sha256": response.request_sha256,
            "http_status": 200, "content_type": response.content_type,
            "raw_path": prefix + ".raw", "raw_sha256": hash_bytes(response.raw),
            "raw_bytes": len(response.raw), "received_at": BEFORE})
    capture._publish(directory, "evidence.private.json", report_raw)
    return directory, guards


@_POSIX_CAPTURE_ONLY
def test_four_original_spent_disclosure_receipts_rebuild_byte_exact_before_new_protocol(tmp_path, stored_source):
    directory, guards = stored_source
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    source = capture._source(tmp_path, head=HEAD, remote=REMOTE)
    assert source["report"]["report_sha256"] == capture.SOURCE_REPORT_SHA256
    assert capture.build_protocol(source)["maximum_attempts"] == 2
    assert before == {path.name: path.read_bytes() for path in directory.iterdir()}
    assert len(guards) >= 19  # class replay before/after and every protected C read


@pytest.mark.parametrize("change", ["raw", "report", "budget", "boolean_counter", "clock", "extra"])
@_POSIX_CAPTURE_ONLY
def test_original_source_hash_budget_types_inventory_and_chronology_refuse_before_any_new_capture(tmp_path, stored_source, change):
    directory, _ = stored_source
    if change in {"raw", "report"}:
        path = directory / ("attempt-01.raw" if change == "raw" else "evidence.private.json")
        path.write_bytes(path.read_bytes() + b" ")
    elif change == "extra":
        capture._publish_json(directory, "extra.json", {})
    else:
        path = (directory.parent / ("budget-" + capture.SOURCE_PROTOCOL_SHA256 + ".json")
                if change == "budget" else directory / "completed.json")
        receipt = json.loads(path.read_bytes())
        field, new = (("resumption_or_restart_allowed", True) if change == "budget"
                      else ("qc_attempts", False) if change == "boolean_counter"
                      else ("completed_at", "2026-10-13T22:59:59Z"))
        receipt[field] = new
        path.write_bytes((canonical_json(receipt) + "\n").encode())
    with pytest.raises(capture.CaptureRefusal):
        capture._source(tmp_path, head=HEAD, remote=REMOTE)
    assert not (tmp_path / capture.CAPTURE_PARENT).exists()


@pytest.mark.usefixtures("portable_capture_platform")
def test_historical_disclosure_code_uses_exact_binary_git_blobs_and_rechecks_lane(monkeypatch):
    files = ("scripts/fake-one.py", "scripts/fake-two.py", "scripts/verify_short_interest_terminal_originals.py")
    monkeypatch.setattr(capture, "_CODE_FILES", files)
    seen = []
    monkeypatch.setattr(capture, "_guard", lambda *args: seen.append("guard"))
    def run(command, **kwargs):
        assert seen[-1] == "guard"
        assert command[:2] == ["git", "show"] and command[2].startswith(capture.SOURCE_HEAD + ":")
        name = command[2].split(":", 1)[1]
        seen.append(name)
        return SimpleNamespace(returncode=0, stdout=("frozen-" + name + "\n").encode())
    monkeypatch.setattr(capture, "subprocess", SimpleNamespace(run=run))
    digest = capture._historical_source_identity(Path("/fabricated"), head=HEAD, remote=REMOTE)
    assert digest == hash_payload({"git_commit": capture.SOURCE_HEAD, "files": [
        {"path": name, "sha256": hash_bytes(("frozen-" + name + "\n").encode())} for name in files[:-1]]})
