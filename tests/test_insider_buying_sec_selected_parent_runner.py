"""Invented parent bytes and injected transport only; no SEC request."""
from __future__ import annotations

import http.client
import io
import json
from dataclasses import replace

import pytest

from data.hashing import hash_bytes, hash_payload
import research.insider_buying_sec_selected_parent_runner as runner


COMMIT = "d" * 40
CONTACT = "research@example.test"
_REAL_CAPACITY = runner._capacity


def _request(number: int) -> runner.SelectedParentRequest:
    accession = f"0000000001-23-{number:06d}"
    return runner.SelectedParentRequest(
        period="2023Q1", accession_number=accession, form_type="4",
        filing_date="2023-01-03", issuer_cik="0000000001",
        master_source_sha256="a" * 64, parsed_lineage_hash="b" * 64,
        url=f"https://www.sec.gov/Archives/edgar/data/1/{accession}.txt",
    )


def _plan(*numbers: int, reuse: tuple[runner.SelectedParentReuse, ...] = ()) -> runner.SelectedParentPlan:
    requests = tuple(_request(number) for number in numbers)
    return runner.SelectedParentPlan(
        scope="synthetic_test_manifest", locator_manifest_sha256="c" * 64,
        requests=requests,
        request_inventory_sha256=hash_payload([item.to_payload() for item in requests]),
        reuses=reuse,
    )


def _result(body: bytes, status: int = 200) -> runner.SecHttpResult:
    if status == 200 and not body.startswith(b"<SEC-DOCUMENT>"):
        body = b"<SEC-DOCUMENT>" + body
    return runner.SecHttpResult(status, (("Content-Length", str(len(body))),), body)


def _report(path):
    return json.loads(path.read_bytes())


def _run(plan, output, transport, *, resume=False, reuse=None):
    return runner._run_selected(plan, output, contact_email=CONTACT,
                                capture_git_commit=COMMIT, transport=transport,
                                reused_bytes=reuse, resume=resume)


def _fake_https_wire(monkeypatch, wire: bytes):
    """Exercise the standard library's real HTTP chunk decoder with no socket."""
    state = {"requests": [], "reads": [], "closed": 0}

    class Socket:
        def makefile(self, mode):
            assert mode == "rb"
            return io.BytesIO(wire)

    class Response(http.client.HTTPResponse):
        def read(self, size=None):
            state["reads"].append(size)
            return super().read(size)

    class Connection:
        def __init__(self, host, timeout):
            assert (host, timeout) == ("www.sec.gov", 15)
            self.response = None

        def request(self, method, path, headers):
            state["requests"].append((method, path, headers))

        def getresponse(self):
            self.response = Response(Socket())
            self.response.begin()
            return self.response

        def close(self):
            state["closed"] += 1
            if self.response is not None:
                self.response.close()

    monkeypatch.setattr(runner.http.client, "HTTPSConnection", Connection)
    return state


def _http_wire(status: int, headers: tuple[tuple[str, str], ...], body: bytes) -> bytes:
    reason = "OK" if status == 200 else "Other"
    lines = [f"HTTP/1.1 {status} {reason}\r\n".encode()]
    lines.extend(f"{name}: {value}\r\n".encode() for name, value in headers)
    return b"".join(lines) + b"\r\n" + body


def _chunked(body: bytes) -> bytes:
    return f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n"


@pytest.fixture(autouse=True)
def _quick_capacity(monkeypatch):
    monkeypatch.setattr(runner, "_capacity", lambda *_: True)
    now = [0]

    def monotonic_ns():
        now[0] += 1_000_000
        return now[0]

    def sleep(seconds):
        now[0] += int(seconds * 1_000_000_000) + 1_000_000

    monkeypatch.setattr(runner.time, "monotonic_ns", monotonic_ns)
    monkeypatch.setattr(runner.time, "sleep", sleep)
    return now


def test_selected_parent_success_retains_only_bounded_raw_and_false_authority(tmp_path):
    plan = _plan(1, 2)
    calls = []
    bodies = {item.url: (f"invented parent {item.accession_number}").encode()
              for item in plan.requests}

    def transport(url, headers, cap):
        calls.append((url, cap))
        assert headers["User-Agent"].endswith(f"({CONTACT})")
        return _result(bodies[url])

    path = _run(plan, tmp_path / "parents", transport)
    report = _report(path)
    assert calls == [(item.url, runner.MAX_COMPLETE_TXT_BYTES) for item in plan.requests]
    assert report["complete_selected_raw_set_acquired"] is True
    assert report["attempt_count"] == 2
    assert all(row["status"] == "raw_acquired_noncanonical" for row in report["rows"])
    assert all(report[key] is False for key in (
        "canonical_evidence", "point_in_time_data", "source_authenticated",
        "quarter_population_complete", "acceptance_metadata_verified", "qc_job_authorized",
        "outcome_access_authorized", "broker_or_trading_authorized",
    ))
    assert report["research_looks"] == report["consumed_outcome_looks"] == 0
    assert CONTACT.encode() not in path.read_bytes()
    assert CONTACT.encode() not in (path.parent / "inventory.json").read_bytes()
    assert hash_bytes(path.read_bytes()) == json.loads((path.parent / "commit.json").read_text())["report_sha256"]
    for row in report["rows"]:
        descriptor = row["raw_object"]
        assert hash_bytes((path.parent / descriptor["relative_path"]).read_bytes()) == descriptor["sha256"]


def test_interrupted_reservation_consumes_attempt_and_resume_skips_completed(tmp_path):
    plan = _plan(1, 2, 3)
    output = tmp_path / "parents"
    calls = []

    def crash(url, _headers, _cap):
        calls.append(url)
        if url == plan.requests[1].url:
            raise KeyboardInterrupt
        return _result(b"invented parent")

    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, crash)
    assert not (output / "commit.json").exists()

    def transport(url, _headers, _cap):
        calls.append(url)
        return _result(b"invented parent")

    report = _report(_run(plan, output, transport, resume=True))
    assert calls.count(plan.requests[0].url) == 1
    assert calls.count(plan.requests[1].url) == 2
    assert calls.count(plan.requests[2].url) == 1
    assert report["attempt_count"] == 4
    assert report["rows"][1]["attempts"] == 2
    assert report["complete_selected_raw_set_acquired"] is True


def test_resume_refuses_changed_inventory_or_object_before_network(tmp_path):
    plan = _plan(1, 2)
    output = tmp_path / "parents"
    calls = []

    def crash(url, _headers, _cap):
        calls.append(url)
        if url == plan.requests[1].url:
            raise KeyboardInterrupt
        return _result(b"invented parent")

    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, crash)
    with pytest.raises(runner.SecSelectedParentRunnerError, match="inventory"):
        _run(_plan(1, 3), output, lambda *_: calls.append("network"), resume=True)
    assert "network" not in calls
    objects = list((output / "objects").glob("*.bin"))
    assert len(objects) == 1
    objects[0].write_bytes(b"changed")
    with pytest.raises(runner.SecSelectedParentRunnerError, match="hash|size|changed"):
        _run(plan, output, lambda *_: calls.append("network"), resume=True)
    assert "network" not in calls


def test_404_keeps_denominator_and_403_stops_all_later_requests(tmp_path):
    plan = _plan(1, 2, 3)
    calls = []

    def missing(url, _headers, _cap):
        calls.append(url)
        return _result(b"" if url == plan.requests[1].url else b"invented parent",
                       status=404 if url == plan.requests[1].url else 200)

    result = _report(_run(plan, tmp_path / "missing", missing))
    assert len(calls) == 3
    assert [row["status"] for row in result["rows"]] == [
        "raw_acquired_noncanonical", "not_found", "raw_acquired_noncanonical",
    ]
    assert result["complete_selected_raw_set_acquired"] is False

    denied_calls = []

    def denied(url, _headers, _cap):
        denied_calls.append(url)
        return _result(b"", status=403)

    result = _report(_run(plan, tmp_path / "denied", denied))
    assert denied_calls == [plan.requests[0].url]
    assert "403" in result["halted_reason"]
    assert result["rows"][1]["status"] == "not_attempted"


def test_prior_object_reuse_is_hash_bound_and_does_not_dispatch(tmp_path):
    raw = b"invented reusable parent"
    item = runner.SelectedParentReuse(_request(1).accession_number, hash_bytes(raw),
                                      len(raw), "e" * 64)
    plan = _plan(1, 2, reuse=(item,))
    calls = []

    def transport(url, _headers, _cap):
        calls.append(url)
        return _result(b"invented new parent")

    with pytest.raises(runner.SecSelectedParentRunnerError, match="prior bytes"):
        _run(plan, tmp_path / "bad", transport, reuse={item.accession_number: b"wrong"})
    assert not calls
    result = _report(_run(plan, tmp_path / "good", transport,
                          reuse={item.accession_number: raw}))
    assert calls == [plan.requests[1].url]
    assert result["rows"][0]["source"] == "reused"
    assert result["rows"][0]["prior_report_sha256"] == "e" * 64
    assert result["attempt_count"] == 1


def test_capacity_pause_occurs_before_request_and_is_resumable(monkeypatch, tmp_path):
    plan = _plan(1)
    calls = []
    monkeypatch.setattr(runner, "_capacity", lambda *_: False)
    with pytest.raises(runner.SecSelectedParentRunnerError, match="capacity pause"):
        _run(plan, tmp_path / "parents", lambda *_: calls.append("network"))
    assert not calls
    assert not (tmp_path / "parents" / "commit.json").exists()
    monkeypatch.setattr(runner, "_capacity", lambda *_: True)
    result = _report(_run(plan, tmp_path / "parents", lambda *_: _result(b"parent"),
                          resume=True))
    assert result["complete_selected_raw_set_acquired"] is True


def test_synthetic_plan_cannot_use_real_transport_and_real_scope_cannot_be_forged(tmp_path):
    with pytest.raises(runner.SecSelectedParentRunnerError, match="real SEC transport"):
        _run(_plan(1), tmp_path / "never", runner._sec_transport)
    with pytest.raises(runner.SecSelectedParentRunnerError, match="real SEC transport"):
        _run(_plan(1), tmp_path / "never-selected", runner._selected_sec_transport)
    forged = runner.SelectedParentPlan(
        scope="ib1b_observed_noncanonical", locator_manifest_sha256="c" * 64,
        requests=(_request(1),),
        request_inventory_sha256=hash_payload([_request(1).to_payload()]),
    )
    with pytest.raises(runner.SecSelectedParentRunnerError, match="real plan"):
        forged.to_payload()


def test_exact_clean_commit_gate_refuses_uncommitted_runner_before_any_source(tmp_path):
    with pytest.raises(runner.SecSelectedParentRunnerError, match="clean committed"):
        runner._verify_exact_committed_code("d" * 40)


def test_cross_quarter_repeated_accession_cannot_alias_attempt_or_reuse_state():
    first = replace(_request(1), period="2022Q4", filing_date="2022-12-30")
    second = _request(1)
    plan = runner.SelectedParentPlan(
        scope="synthetic_test_manifest", locator_manifest_sha256="c" * 64,
        requests=(first, second),
        request_inventory_sha256=hash_payload([first.to_payload(), second.to_payload()]),
    )
    with pytest.raises(runner.SecSelectedParentRunnerError, match="uniqueness"):
        plan.to_payload()


def test_real_plan_needs_literal_request_digest_not_only_locator_digest_and_counts():
    requests = tuple(
        replace(_request(number), period="2022Q4", filing_date="2022-12-30")
        if number <= 4_613 else _request(number)
        for number in range(1, runner.MAX_SELECTED + 1)
    )
    inventory = hash_payload([item.to_payload() for item in requests])
    invented = runner.SelectedParentPlan(
        scope="ib1b_observed_noncanonical",
        locator_manifest_sha256=runner.PINNED_REAL_LOCATOR_SHA256,
        requests=requests, request_inventory_sha256=inventory,
        _real_token=runner._REAL_TOKEN,
    )
    with pytest.raises(runner.SecSelectedParentRunnerError, match="real plan"):
        invented.to_payload()


def test_real_reuse_inventory_needs_exact_prior_verified_subset():
    fake = runner.SelectedParentReuse(_request(1).accession_number,
                                      "e" * 64, 20, "f" * 64)
    runner._validate_real_reuses([])
    with pytest.raises(runner.SecSelectedParentRunnerError, match="real reuse"):
        runner._validate_real_reuses([fake.to_payload()])


@pytest.mark.parametrize("changes", [
    {"scope": []},
    {"requests": (object(),)},
    {"reuses": (object(),)},
])
def test_malformed_plan_fields_refuse_before_network_or_output(changes):
    malformed = replace(_plan(1), **changes)
    with pytest.raises(runner.SecSelectedParentRunnerError, match="plan identity or size"):
        malformed.to_payload()


def test_unsafe_response_framing_commits_refusal_without_later_request(tmp_path):
    plan = _plan(1, 2)
    calls = []

    def transport(url, _headers, _cap):
        calls.append(url)
        return runner.SecHttpResult(200, (("Content-Length", "999"),), b"short")

    result = _report(_run(plan, tmp_path / "framing", transport))
    assert calls == [plan.requests[0].url]
    assert result["complete_selected_raw_set_acquired"] is False
    assert "framing" in result["halted_reason"]


def test_http_200_html_challenge_refuses_before_parent_object_publication(tmp_path):
    plan = _plan(1, 2)
    calls = []
    body = b"<html>SEC challenge</html>"

    def transport(url, _headers, _cap):
        calls.append(url)
        return runner.SecHttpResult(200, (("Content-Length", str(len(body))),), body)

    output = tmp_path / "html"
    report = _report(_run(plan, output, transport))
    assert calls == [plan.requests[0].url]
    assert report["complete_selected_raw_set_acquired"] is False
    assert "envelope" in report["halted_reason"]
    assert report["rows"][0]["status"] == "refused"
    assert list((output / "objects").iterdir()) == []


def test_selected_transport_accepts_bounded_chunked_and_preserves_header_provenance(monkeypatch):
    body = b"<SEC-DOCUMENT>invented parent"
    state = _fake_https_wire(monkeypatch, _http_wire(
        200, (("Transfer-Encoding", "chunked"), ("Content-Type", "text/plain")),
        _chunked(body)))
    result = runner._selected_sec_transport(_request(1).url, {}, len(body))
    assert runner._strict_selected_response(result, max_bytes=len(body)) == body
    assert ("Transfer-Encoding", "chunked") in result.headers
    assert not any(name.lower() == "content-length" for name, _ in result.headers)
    assert state["requests"] == [("GET", "/Archives/edgar/data/1/0000000001-23-000001.txt", {})]
    assert state["reads"] == [len(body) + 1, 1]
    assert state["closed"] == 1


def test_selected_transport_keeps_strict_content_length_route(monkeypatch):
    body = b"<SEC-DOCUMENT>invented parent"
    state = _fake_https_wire(monkeypatch, _http_wire(
        200, (("Content-Length", str(len(body))),), body))
    result = runner._selected_sec_transport(_request(1).url, {}, len(body))
    assert runner._strict_selected_response(result, max_bytes=len(body)) == body
    assert state["reads"] == [len(body)]
    assert state["closed"] == 1


@pytest.mark.parametrize("headers", [
    (("Transfer-Encoding", "chunked"), ("Transfer-Encoding", "chunked")),
    (("Transfer-Encoding", "gzip"),),
    (("Transfer-Encoding", "chunked, gzip"),),
    (("Transfer-Encoding", "chunked "),),
    (("Content-Length", "20"), ("Transfer-Encoding", "chunked")),
    (("Transfer-Encoding", "chunked"), ("Content-Encoding", "gzip")),
    (("Transfer-Encoding", "chunked"), ("Content-Encoding", "identity"),
     ("Content-Encoding", "identity")),
    (),
])
def test_selected_transport_refuses_ambiguous_or_compressed_framing(monkeypatch, headers):
    body = b"<SEC-DOCUMENT>invented parent"
    wire = _http_wire(200, headers, _chunked(body))
    state = _fake_https_wire(monkeypatch, wire)
    with pytest.raises(runner.SecCompleteAcquisitionError, match="framing"):
        runner._selected_sec_transport(_request(1).url, {}, 100)
    assert state["closed"] == 1


def test_selected_transport_refuses_decoded_chunked_body_over_cap(monkeypatch):
    body = b"<SEC-DOCUMENT>" + b"x" * 40
    state = _fake_https_wire(monkeypatch, _http_wire(
        200, (("Transfer-Encoding", "chunked"),), _chunked(body)))
    with pytest.raises(runner.SecCompleteAcquisitionError, match="bound|oversized"):
        runner._selected_sec_transport(_request(1).url, {}, 16)
    assert state["closed"] == 1


def test_selected_transport_refuses_truncated_chunked_body(monkeypatch):
    state = _fake_https_wire(monkeypatch, _http_wire(
        200, (("Transfer-Encoding", "chunked"),),
        b"20\r\n<SEC-DOCUMENT>short"))
    with pytest.raises(runner.SecCompleteAcquisitionError, match="truncated|malformed"):
        runner._selected_sec_transport(_request(1).url, {}, 100)
    assert state["closed"] == 1


def test_selected_transport_refuses_truncated_content_length_body(monkeypatch):
    state = _fake_https_wire(monkeypatch, _http_wire(
        200, (("Content-Length", "100"),), b"<SEC-DOCUMENT>short"))
    with pytest.raises(runner.SecCompleteAcquisitionError, match="truncated"):
        runner._selected_sec_transport(_request(1).url, {}, 100)
    assert state["closed"] == 1


def test_selected_transport_refuses_malformed_http_status_line(monkeypatch):
    state = {"closed": 0}

    class BrokenConnection:
        def __init__(self, host, timeout):
            assert (host, timeout) == ("www.sec.gov", 15)

        def request(self, method, path, headers):
            pass

        def getresponse(self):
            raise http.client.BadStatusLine("malformed")

        def close(self):
            state["closed"] += 1

    monkeypatch.setattr(runner.http.client, "HTTPSConnection", BrokenConnection)
    with pytest.raises(runner.SecCompleteAcquisitionError, match="malformed"):
        runner._selected_sec_transport(_request(1).url, {}, 100)
    assert state["closed"] == 1


def test_selected_runner_uses_chunked_strict_validator_before_publication(tmp_path):
    body = b"<SEC-DOCUMENT>invented parent"
    result = runner.SecHttpResult(200, (("Transfer-Encoding", "chunked"),), body)
    plan = _plan(1)
    report = _report(_run(plan, tmp_path / "chunked", lambda *_: result))
    assert report["complete_selected_raw_set_acquired"] is True
    object_row = report["rows"][0]["raw_object"]
    assert object_row["sha256"] == hash_bytes(body)

    ambiguous = runner.SecHttpResult(
        200, (("Transfer-Encoding", "chunked"), ("Content-Length", str(len(body)))), body)
    refused = _report(_run(plan, tmp_path / "ambiguous", lambda *_: ambiguous))
    assert refused["complete_selected_raw_set_acquired"] is False
    assert "framing" in refused["halted_reason"]
    assert list((tmp_path / "ambiguous" / "objects").iterdir()) == []


@pytest.mark.parametrize("status", [302, 403, 429, 503])
def test_selected_transport_never_follows_or_reads_non_200(monkeypatch, status):
    state = _fake_https_wire(monkeypatch, _http_wire(
        status, (("Location", "https://example.invalid/redirect"),), b"do not read"))
    result = runner._selected_sec_transport(_request(1).url, {}, 100)
    assert result.status == status and result.body == b""
    assert state["reads"] == []
    assert len(state["requests"]) == 1 and state["closed"] == 1


@pytest.mark.parametrize("url", [
    "https://example.invalid/Archives/edgar/data/1/f.txt",
    "https://www.sec.gov/Archives/edgar/data/1/f.txt?redirect=1",
    "https://www.sec.gov/Archives/edgar/data/1/%2e%2e/f.txt",
])
def test_selected_transport_refuses_escaped_url_before_connection(monkeypatch, url):
    state = _fake_https_wire(monkeypatch, b"")
    with pytest.raises(runner.SecCompleteAcquisitionError, match="host"):
        runner._selected_sec_transport(url, {}, 100)
    assert state["requests"] == [] and state["closed"] == 0


def test_retry_ceiling_and_completion_to_dispatch_spacing(tmp_path, _quick_capacity):
    plan = _plan(1, 2)
    attempts = []

    def transport(url, _headers, _cap):
        attempts.append((url, _quick_capacity[0]))
        if url == plan.requests[0].url and sum(item[0] == url for item in attempts) < 3:
            return _result(b"", status=503)
        return _result(b"invented parent")

    result = _report(_run(plan, tmp_path / "retried", transport))
    assert [item[0] for item in attempts] == [plan.requests[0].url] * 3 + [plan.requests[1].url]
    assert all(later[1] - prior[1] >= runner.MIN_REQUEST_INTERVAL_NS
               for prior, later in zip(attempts, attempts[1:]))
    assert result["rows"][0]["attempts"] == 3
    assert result["complete_selected_raw_set_acquired"] is True

    exhausted = []

    def unavailable(url, _headers, _cap):
        exhausted.append(url)
        return _result(b"", status=503)

    result = _report(_run(plan, tmp_path / "exhausted", unavailable))
    assert exhausted == [plan.requests[0].url] * 3
    assert "attempt ceiling" in result["halted_reason"]
    assert result["rows"][1]["status"] == "not_attempted"


def test_crash_after_saved_response_recovers_object_without_re_request(monkeypatch, tmp_path):
    plan = _plan(1, 2)
    output = tmp_path / "parents"
    real_append = runner._Events.append
    interrupted = [False]
    calls = []

    def interrupt(self, payload):
        if payload["kind"] == "item-complete" and not interrupted[0]:
            interrupted[0] = True
            raise KeyboardInterrupt
        return real_append(self, payload)

    monkeypatch.setattr(runner._Events, "append", interrupt)

    def transport(url, _headers, _cap):
        calls.append(url)
        return _result(b"invented parent")

    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, transport)
    monkeypatch.setattr(runner._Events, "append", real_append)
    result = _report(_run(plan, output, transport, resume=True))
    assert calls == [item.url for item in plan.requests]
    assert result["attempt_count"] == 2


def test_capacity_uses_actual_free_space_and_cumulative_run_budget(monkeypatch, tmp_path):
    info = tmp_path.stat()
    monkeypatch.setattr(runner, "_capacity", _REAL_CAPACITY)

    class Fs:
        f_frsize = 1
        f_bavail = runner.MIN_FREE_BYTES + runner.MAX_COMPLETE_TXT_BYTES + 4 * runner._MAX_EVENT_BYTES - 1

    monkeypatch.setattr(runner.os, "statvfs", lambda _: Fs())
    assert not runner._capacity(tmp_path, (info.st_dev, info.st_ino), 0)
    Fs.f_bavail += 1
    assert runner._capacity(tmp_path, (info.st_dev, info.st_ino), 0)
    assert not runner._capacity(tmp_path, (info.st_dev, info.st_ino),
                                runner.MAX_RUN_OBJECT_BYTES)


@pytest.mark.parametrize("redirect", ["symlink", "hardlink"])
def test_resume_refuses_redirected_lock_without_touching_other_file(monkeypatch, tmp_path, redirect):
    plan = _plan(1)
    output = tmp_path / "parents"
    monkeypatch.setattr(runner, "_capacity", lambda *_: False)
    with pytest.raises(runner.SecSelectedParentRunnerError, match="capacity pause"):
        _run(plan, output, lambda *_: pytest.fail("network was called"))
    (output / "run.lock").unlink()
    victim = tmp_path / "other"
    victim.write_bytes(b"untouched")
    if redirect == "symlink":
        (output / "run.lock").symlink_to(victim)
    else:
        import os
        os.link(victim, output / "run.lock")
    with pytest.raises(runner.SecSelectedParentRunnerError, match="lock|symbolic|loop"):
        _run(plan, output, lambda *_: pytest.fail("network was called"), resume=True)
    assert victim.read_bytes() == b"untouched"


def test_changed_hash_chain_event_refuses_resume_before_network(tmp_path):
    plan = _plan(1, 2)
    output = tmp_path / "parents"
    with pytest.raises(KeyboardInterrupt):
        _run(plan, output,
             lambda url, *_: (_ for _ in ()).throw(KeyboardInterrupt)
             if url == plan.requests[1].url else _result(b"invented parent"))
    first = sorted(output.glob("event-*.json"))[0]
    first.write_bytes(first.read_bytes().replace(b"attempt-start", b"attempt-started"))
    with pytest.raises(runner.SecSelectedParentRunnerError, match="hash"):
        _run(plan, output, lambda *_: pytest.fail("network was called"), resume=True)


def test_report_publication_crash_resumes_without_repeating_sec_request(monkeypatch, tmp_path):
    plan = _plan(1, 2)
    output = tmp_path / "parents"
    real_publish = runner._publish_same_or_new
    interrupted = [False]
    calls = []

    def interrupt(root, name, raw, identity, *, max_bytes):
        if name.startswith("sec-selected-parents-report-") and not interrupted[0]:
            interrupted[0] = True
            raise KeyboardInterrupt
        return real_publish(root, name, raw, identity, max_bytes=max_bytes)

    monkeypatch.setattr(runner, "_publish_same_or_new", interrupt)

    def transport(url, _headers, _cap):
        calls.append(url)
        return _result(b"invented parent")

    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, transport)
    assert (output / "attempts.jsonl").is_file()
    assert not (output / "commit.json").exists()
    monkeypatch.setattr(runner, "_publish_same_or_new", real_publish)
    result = _report(_run(plan, output, transport, resume=True))
    assert calls == [item.url for item in plan.requests]
    assert result["complete_selected_raw_set_acquired"] is True


def test_crash_after_404_response_resumes_as_not_found_without_retry(monkeypatch, tmp_path):
    plan = _plan(1, 2)
    output = tmp_path / "parents"
    real_append = runner._Events.append
    interrupted = [False]
    calls = []

    def interrupt(self, payload):
        if payload["kind"] == "item-not-found" and not interrupted[0]:
            interrupted[0] = True
            raise KeyboardInterrupt
        return real_append(self, payload)

    monkeypatch.setattr(runner._Events, "append", interrupt)

    def transport(url, _headers, _cap):
        calls.append(url)
        return _result(b"", status=404) if url == plan.requests[0].url else _result(b"parent")

    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, transport)
    monkeypatch.setattr(runner._Events, "append", real_append)
    result = _report(_run(plan, output, transport, resume=True))
    assert calls == [item.url for item in plan.requests]
    assert [row["status"] for row in result["rows"]] == ["not_found", "raw_acquired_noncanonical"]
