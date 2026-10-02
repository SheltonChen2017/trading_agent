"""Invented master bytes and injected transport only; no SEC request or real row."""
from __future__ import annotations

from dataclasses import replace
import gzip
import json
import os
from pathlib import Path

import pytest

from data.hashing import hash_bytes
from research import insider_buying_sec_master82_runner as runner
from research.insider_buying.sec_zip_corpus_census import SecZipCensusQuarter, _expected_url
from research.insider_buying_sec_master82_acquisition import _PERIODS, _build_plan


COMMIT = "a" * 40
HEADER = (
    b"Description: Master Index of EDGAR Dissemination Feed\n"
    b"Comments: webmaster@sec.gov\n\n"
    b"CIK|Company Name|Form Type|Date Filed|Filename\n"
    b"--------------------------------------------------------------------------------\n"
)


def _plan():
    quarters = tuple(
        SecZipCensusQuarter(
            period=period, zip_sha256="b" * 64, zip_size_bytes=1,
            source_url_from_retained_manifest=_expected_url(period),
            local_last_write_utc_unverified="2026-09-24T22:52:19.7647157Z",
            submission_member_sha256="c" * 64, submission_member_size_bytes=1,
            submission_header_line_sha256="d" * 64,
            submission_headers=("ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT",
                                "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERNAME",
                                "ISSUERTRADINGSYMBOL"),
            form_counts=(0, 0, 1, 1, 0, 0),
        )
        for period in _PERIODS
    )
    return _build_plan(
        census_scope="synthetic_test_census", census_sha256="e" * 64,
        quarters=quarters, contact_email="private@example.org",
    )


def _images(plan):
    images = {}
    for request in plan.requests:
        year, quarter = int(request.period[:4]), int(request.period[-1])
        filed = f"{year:04d}-{(quarter - 1) * 3 + 1:02d}-02"
        accession = f"0000000001-{year % 100:02d}-000001"
        row = (f"1|Invented Corp|4|{filed}|edgar/data/1/{accession}.txt\n")
        images[request.url] = gzip.compress(HEADER + row.encode("ascii"), mtime=0)
    return images


def _clock(monkeypatch):
    class Clock:
        now = 1_000_000_000

        def monotonic_ns(self):
            self.now += 10_000
            return self.now

        def sleep(self, seconds):
            self.now += int(seconds * 1_000_000_000) + 10_000

    clock = Clock()
    monkeypatch.setattr(runner.time, "monotonic_ns", clock.monotonic_ns)
    monkeypatch.setattr(runner.time, "sleep", clock.sleep)
    return clock


def _transport(images, calls, *, fail_at=None, statuses=None):
    statuses = statuses or {}

    def fetch(url, headers, max_bytes):
        assert url in images
        assert max_bytes == runner.MAX_MASTER_GZIP_BYTES
        assert headers["Accept-Encoding"] == "identity"
        calls.append(url)
        if fail_at == len(calls):
            raise KeyboardInterrupt
        status = statuses.get((url, calls.count(url)), 200)
        raw = images[url] if status == 200 else b""
        return runner.SecHttpResult(status, (("Content-Length", str(len(raw))),), raw)

    return fetch


def _run(plan, output, transport, *, resume=False):
    return runner._run_master82(plan, output, capture_git_commit=COMMIT,
                                transport=transport, resume=resume)


def test_exact_synthetic_82_request_success_is_raw_only(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    plan = _plan()
    images = _images(plan)
    calls = []
    report = _run(plan, tmp_path / "masters", _transport(images, calls))
    payload = json.loads(report.read_text())
    assert calls == [request.url for request in plan.requests]
    assert payload["source_scope"] == "synthetic_test_census"
    assert payload["capture_git_commit_verified"] is None
    assert payload["complete_82_master_indexes_acquired"] is True
    assert payload["attempt_count"] == 82
    assert payload["attempt_event_count"] == 82 * 3
    assert all(row["status"] == "acquired_noncanonical" for row in payload["master_indexes"])
    assert all(row["receipt"]["form4_or_4a_path_rows"] == 1 for row in payload["master_indexes"])
    assert payload["source_authenticated"] is False
    assert payload["outcome_access_authorized"] is False
    assert payload["qc_job_authorized"] is False
    assert payload["research_looks"] == 0
    assert "private@example.org" not in report.read_text()
    assert "private@example.org" not in (report.parent / "inventory.json").read_text()
    assert "private@example.org" not in (report.parent / "attempts.jsonl").read_text()
    assert len(list((report.parent / "objects").glob("*.bin"))) == 82
    assert json.loads((report.parent / "commit.json").read_text())["report_sha256"] == hash_bytes(report.read_bytes())


def test_interrupted_request_resumes_without_repeating_completed_quarters(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    plan = _plan()
    images = _images(plan)
    calls = []
    output = tmp_path / "masters"
    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, _transport(images, calls, fail_at=4))
    assert not (output / "commit.json").exists()
    assert calls == [request.url for request in plan.requests[:4]]
    report = _run(plan, output, _transport(images, calls), resume=True)
    payload = json.loads(report.read_text())
    assert payload["complete_82_master_indexes_acquired"] is True
    assert calls.count(plan.requests[0].url) == 1
    assert calls.count(plan.requests[1].url) == 1
    assert calls.count(plan.requests[2].url) == 1
    assert calls.count(plan.requests[3].url) == 2
    assert payload["attempt_count"] == 83
    assert any('"kind":"attempt-abandoned"' in line
               for line in (output / "attempts.jsonl").read_text().splitlines())


def test_resume_recovers_saved_valid_response_without_second_request(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    plan = _plan()
    images = _images(plan)
    calls = []
    output = tmp_path / "masters"
    actual = runner._summary
    crashed = False

    def interrupt_once(raw, *, period):
        nonlocal crashed
        if not crashed:
            crashed = True
            raise KeyboardInterrupt
        return actual(raw, period=period)

    monkeypatch.setattr(runner, "_summary", interrupt_once)
    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, _transport(images, calls))
    monkeypatch.setattr(runner, "_summary", actual)
    report = _run(plan, output, _transport(images, calls), resume=True)
    assert json.loads(report.read_text())["complete_82_master_indexes_acquired"] is True
    assert calls.count(plan.requests[0].url) == 1


def test_resume_refuses_changed_plan_or_completed_object_before_request(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    plan = _plan()
    images = _images(plan)
    output = tmp_path / "masters"
    calls = []
    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, _transport(images, calls, fail_at=2))
    changed = replace(plan, census_sha256="f" * 64)
    later = []
    with pytest.raises(runner.SecMaster82RunnerError, match="inventory hash or bytes changed"):
        _run(changed, output, _transport(images, later), resume=True)
    assert later == []
    digest = hash_bytes(images[plan.requests[0].url])
    (output / "objects" / f"{digest}.bin").write_bytes(b"changed")
    with pytest.raises(runner.SecMaster82RunnerError, match="raw object hash or bytes changed"):
        _run(plan, output, _transport(images, later), resume=True)
    assert later == []


@pytest.mark.parametrize("status", [403, 429, 404])
def test_denial_stops_all_later_requests_and_publishes_refusal(monkeypatch, tmp_path, status) -> None:
    _clock(monkeypatch)
    plan = _plan()
    images = _images(plan)
    calls = []
    first = plan.requests[0].url
    report = _run(plan, tmp_path / "masters",
                  _transport(images, calls, statuses={(first, 1): status}))
    payload = json.loads(report.read_text())
    assert calls == [first]
    assert payload["complete_82_master_indexes_acquired"] is False
    assert payload["master_indexes"][0]["status"] == "refused"
    assert all(row["status"] == "not_attempted" for row in payload["master_indexes"][1:])


def test_three_retry_limit_and_existing_completed_root_refusal(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    plan = _plan()
    images = _images(plan)
    calls = []
    first = plan.requests[0].url
    output = tmp_path / "masters"
    report = _run(plan, output, _transport(images, calls, statuses={
        (first, 1): 500, (first, 2): 500, (first, 3): 500,
    }))
    assert calls == [first] * 3
    assert json.loads(report.read_text())["attempt_count"] == 3
    with pytest.raises(runner.SecMaster82RunnerError, match="committed"):
        _run(plan, output, _transport(images, []), resume=True)


def test_resume_recovers_linked_publisher_temporaries(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    plan = _plan()
    images = _images(plan)
    calls = []
    output = tmp_path / "masters"
    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, _transport(images, calls, fail_at=2))
    digest = hash_bytes(images[plan.requests[0].url])
    obj = output / "objects" / f"{digest}.bin"
    obj_temp = obj.parent / (".sec-object-" + "1" * 32 + ".tmp")
    os.link(obj, obj_temp)
    event = sorted(output.glob("event-*.json"))[0]
    event_temp = output / (".sec-publish-" + "2" * 32 + ".tmp")
    os.link(event, event_temp)
    report = _run(plan, output, _transport(images, calls), resume=True)
    assert json.loads(report.read_text())["complete_82_master_indexes_acquired"] is True
    assert calls.count(plan.requests[0].url) == 1
    assert obj.stat().st_nlink == 1
    assert event.stat().st_nlink == 1
    assert not obj_temp.exists() and not event_temp.exists()


def test_resume_after_report_before_commit_finishes_without_requests(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    plan = _plan()
    images = _images(plan)
    calls = []
    output = tmp_path / "masters"
    publish = runner._publish_same_or_new

    def interrupt_commit(root, name, raw, identity):
        if name == "commit.json":
            raise KeyboardInterrupt
        return publish(root, name, raw, identity)

    monkeypatch.setattr(runner, "_publish_same_or_new", interrupt_commit)
    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, _transport(images, calls))
    assert len(calls) == 82
    assert list(output.glob("sec-master82-report-*.json"))
    monkeypatch.setattr(runner, "_publish_same_or_new", publish)
    report = _run(plan, output, _transport(images, calls), resume=True)
    assert json.loads(report.read_text())["complete_82_master_indexes_acquired"] is True
    assert len(calls) == 82


def test_changed_journal_event_refuses_before_new_request(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    plan = _plan()
    images = _images(plan)
    output = tmp_path / "masters"
    with pytest.raises(KeyboardInterrupt):
        _run(plan, output, _transport(images, [], fail_at=2))
    event = sorted(output.glob("event-*.json"))[0]
    event.write_bytes(event.read_bytes() + b" ")
    later = []
    with pytest.raises(runner.SecMaster82RunnerError, match="event.*changed|event.*canonical"):
        _run(plan, output, _transport(images, later), resume=True)
    assert later == []


def test_unsafe_200_framing_is_recorded_and_stops(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    plan = _plan()
    images = _images(plan)
    calls = []

    def bad(url, headers, max_bytes):
        calls.append(url)
        return runner.SecHttpResult(200, (("Content-Length", "1"),), images[url])

    report = _run(plan, tmp_path / "masters", bad)
    payload = json.loads(report.read_text())
    assert calls == [plan.requests[0].url]
    assert payload["complete_82_master_indexes_acquired"] is False
    assert "framing" in payload["halted_reason"]


def test_transport_refusal_is_terminal_without_claiming_an_http_status(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    plan = _plan()
    calls = []
    output = tmp_path / "masters"

    def refused(url, headers, max_bytes):
        calls.append(url)
        raise runner.SecCompleteAcquisitionError("REFUSED: unsafe transport framing")

    report = _run(plan, output, refused)
    payload = json.loads(report.read_text())
    assert calls == [plan.requests[0].url]
    assert payload["complete_82_master_indexes_acquired"] is False
    events = [json.loads(line) for line in (output / "attempts.jsonl").read_text().splitlines()]
    assert events[-1]["outcome"] == "transport_refusal"
    assert events[-1]["status"] is None
    with pytest.raises(runner.SecMaster82RunnerError, match="committed"):
        _run(plan, output, refused, resume=True)
    assert calls == [plan.requests[0].url]


def test_malformed_transport_result_has_no_fictitious_http_200(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    plan = _plan()
    calls = []

    def malformed(url, headers, max_bytes):
        calls.append(url)
        return object()

    report = _run(plan, tmp_path / "masters", malformed)
    events = [json.loads(line) for line in (report.parent / "attempts.jsonl").read_text().splitlines()]
    assert calls == [plan.requests[0].url]
    assert events[-1]["outcome"] == "transport_refusal"
    assert events[-1]["status"] is None


def test_module_has_no_platform_lock_import_at_import_time() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "\nimport fcntl\n" not in source


def test_unsupported_host_refuses_before_root_or_transport(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runner, "_host_kind", lambda: "nt")
    calls = []
    with pytest.raises(runner.SecMaster82RunnerError, match="POSIX directory handles"):
        _run(_plan(), tmp_path / "unused", lambda *_: calls.append("network"))
    assert calls == []
    assert not (tmp_path / "unused").exists()


def test_synthetic_plan_cannot_reach_real_transport(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "http.client.HTTPSConnection",
        lambda *_args, **_kwargs: pytest.fail("synthetic master plan attempted a real SEC connection"),
    )
    output = tmp_path / "unused"
    with pytest.raises(runner.SecMaster82RunnerError, match="synthetic plan"):
        runner._run_master82(_plan(), output, capture_git_commit=COMMIT,
                             transport=runner._sec_transport)
    assert not output.exists()


def test_public_entry_requires_a_committed_clean_lane_before_source_or_network(monkeypatch, tmp_path) -> None:
    calls = []
    monkeypatch.setattr(runner, "census_retained_sec_zip_corpus", lambda _: calls.append("source"))
    with pytest.raises(runner.SecMaster82RunnerError, match="full lowercase Git SHA"):
        runner.run_retained_master82_acquisition(
            tmp_path, tmp_path / "out", contact_email="private@example.org",
            capture_git_commit="short", transport=lambda *_: calls.append("network"),
        )
    assert calls == []


# Section 119 (Claude review): the 500 ms completion-to-dispatch rule and its
# dispatch-time recheck had no test in this runner.
def test_master_requests_keep_completion_to_dispatch_spacing(monkeypatch, tmp_path) -> None:
    clock = _clock(monkeypatch)
    plan = _plan()
    inner = _transport(_images(plan), [])
    entries = []
    completions = []

    def fetch(url, headers, max_bytes):
        entries.append(clock.now)
        result = inner(url, headers, max_bytes)
        clock.sleep(0.75)
        completions.append(clock.now)
        return result

    _run(plan, tmp_path / "paced", fetch)
    assert len(entries) == len(completions) == 82
    assert all(later_entry - prior_completion >= runner.MIN_REQUEST_INTERVAL_NS
               for prior_completion, later_entry in zip(completions, entries[1:]))


def test_master_dispatch_refuses_when_the_pacing_sleep_returns_early(monkeypatch, tmp_path) -> None:
    _clock(monkeypatch)
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    plan = _plan()
    calls = []
    with pytest.raises(runner.SecMaster82RunnerError, match="dispatch pacing was too early"):
        _run(plan, tmp_path / "early", _transport(_images(plan), calls))
    assert calls == [plan.requests[0].url]


def test_dirty_lane_is_not_an_exact_committed_code_state(monkeypatch) -> None:
    root = str(Path(runner.__file__).resolve().parents[1])

    def git_output(command, **_kwargs):
        if command == ("git", "rev-parse", "--show-toplevel"):
            return (root + "\n").encode()
        if command == ("git", "branch", "--show-current"):
            return b"codex/strategy-insider-buying\n"
        if command == ("git", "rev-parse", "HEAD"):
            return (COMMIT + "\n").encode()
        if command == ("git", "status", "--porcelain=v1", "--untracked-files=all"):
            return b"?? invented-untracked-file\n"
        pytest.fail(f"dependency blobs were read on a dirty lane: {command!r}")

    monkeypatch.setattr(runner.subprocess, "check_output", git_output)
    with pytest.raises(runner.SecMaster82RunnerError, match="exact clean committed Insider lane"):
        runner._verify_exact_committed_code(COMMIT)
