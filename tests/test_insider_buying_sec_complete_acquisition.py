"""Invented SEC transport images only; no live request or real filing read."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
import subprocess
import sys
from dataclasses import replace

import pytest

from data.hashing import hash_bytes, hash_payload
from research import insider_buying_sec_complete_acquisition as runner
from research.insider_buying_sec_acquisition import SecPilotCandidate, _EXPECTED_ACCESSIONS


COMMIT = "a" * 40
_INDEX_HEADER = (
    b"Description: Master Index of EDGAR Dissemination Feed\n"
    b"Last Data Received: March 31, 2023\n"
    b"Comments: webmaster@sec.gov\n\n"
    b"CIK|Company Name|Form Type|Date Filed|Filename\n"
    b"--------------------------------------------------------------------------------\n"
)


def _candidates() -> tuple[SecPilotCandidate, ...]:
    result = []
    for index, accession in enumerate(_EXPECTED_ACCESSIONS):
        year = 2022 if index < 8 else 2023
        form_type = "4" if index % 8 < 6 else "4/A"
        filing_date = "2022-11-07" if year == 2022 else "2023-02-10"
        issuer_cik = "0000123456"
        submission_row_id = "b" * 64
        result.append(SecPilotCandidate(
            period="2022Q4" if year == 2022 else "2023Q1",
            accession_number=accession,
            form_type=form_type, filing_date_raw="INVENTED",
            filing_date=filing_date,
            issuer_cik=issuer_cik, quarterly_zip_sha256=runner._QUARTER_ZIP_SHA256[
                "2022Q4" if year == 2022 else "2023Q1"],
            submission_row_id=submission_row_id, raw_snapshot_id="invented-raw",
            raw_lineage_sha256="c" * 64,
        ))
    return tuple(result)


def _index(candidates: tuple[SecPilotCandidate, ...], period: str) -> bytes:
    return _INDEX_HEADER + b"".join(
        (f"888888|Invented Corp|{item.form_type}|{item.filing_date}|"
         f"edgar/data/{int(item.issuer_cik)}/"
         f"{item.accession_number}.txt\n").encode("ascii")
        for item in candidates if item.period == period
    )


def _complete(item: SecPilotCandidate) -> bytes:
    accession = item.accession_number
    compact = item.filing_date.replace("-", "")
    accepted = compact + "101112"
    return (
        f"<SEC-DOCUMENT>{accession}.txt : {compact}\n"
        f"<SEC-HEADER>{accession}.hdr.sgml : {compact}\n"
        f"<ACCEPTANCE-DATETIME>{accepted}\n"
        f"<ACCESSION-NUMBER>{accession}\n<TYPE>{item.form_type}\n<FILING-DATE>{compact}\n"
        "<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>0000002178\n"
        "<CONFORMED-NAME>Invented Owner\n</OWNER-DATA>\n</REPORTING-OWNER>\n"
        f"<ISSUER>\n<COMPANY-DATA>\n<CIK>{item.issuer_cik}\n"
        "</COMPANY-DATA>\n</ISSUER>\n</SEC-HEADER>\n"
        f"<DOCUMENT>\n<TYPE>{item.form_type}\n<SEQUENCE>1\n<FILENAME>ownership.xml\n"
        "<DESCRIPTION>Invented document\n<TEXT>\n"
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        f"<ownershipDocument><documentType>{item.form_type}</documentType>"
        f"<issuer><issuerCik>{item.issuer_cik}</issuerCik></issuer>"
        "<reportingOwner><reportingOwnerId><rptOwnerCik>0000002178</rptOwnerCik>"
        "</reportingOwnerId></reportingOwner></ownershipDocument>\n"
        "</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
    ).encode("ascii")


def _images() -> dict[str, bytes]:
    candidates = _candidates()
    result = {
        runner._MASTER_URLS[period]: gzip.compress(_index(candidates, period), mtime=0)
        for period in ("2022Q4", "2023Q1")
    }
    for item in candidates:
        url = runner._HOST_PREFIX + (
            f"edgar/data/{int(item.issuer_cik)}/{item.accession_number}.txt"
        )
        result[url] = _complete(item)
    assert len(result) == 18
    return result


def _setup(monkeypatch, tmp_path):
    source = tmp_path / "source"
    prior = tmp_path / "prior"
    source.mkdir()
    prior.mkdir()
    monkeypatch.setattr(runner, "_verify_exact_committed_code", lambda value: None)
    monkeypatch.setattr(runner, "MIN_REQUEST_INTERVAL_NS", 0)
    monkeypatch.setattr(runner, "select_fixed_pilot", lambda _source, _prior: _candidates())
    monkeypatch.setattr(runner, "_APPROVED_SIXTEEN_INVENTORY_SHA256",
                        hash_payload([item.to_payload() for item in _candidates()]))
    return source, prior, tmp_path / "output"


def _transport(images: dict[str, bytes], calls: list[str], *, statuses=None):
    statuses = statuses or {}

    def fetch(url, headers, max_bytes):
        assert "InsiderBuyingResearch" in headers["User-Agent"]
        assert headers["Accept-Encoding"] == "identity"
        calls.append(url)
        status = statuses.get((url, calls.count(url)), 200)
        if type(status) is BaseException or isinstance(status, BaseException):
            raise status
        body = images[url] if status == 200 else b""
        return runner.SecHttpResult(status, (("Content-Length", str(len(body))),), body)

    return fetch


def _run(monkeypatch, tmp_path, transport):
    source, prior, output = _setup(monkeypatch, tmp_path)
    report = runner.run_fixed_complete_submissions(
        source, prior, output, contact_email="pilot@example.org",
        capture_git_commit=COMMIT, transport=transport,
    )
    return report, json.loads(report.read_text(encoding="utf-8"))


def test_exact_synthetic_sixteen_follows_only_master_paths_and_retains_raw(monkeypatch, tmp_path):
    images = _images()
    calls = []
    monkeypatch.setattr(runner.time, "sleep", lambda value: None)
    report, payload = _run(monkeypatch, tmp_path, _transport(images, calls))
    assert len(calls) == 18
    assert calls[:2] == [runner._MASTER_URLS["2022Q4"], runner._MASTER_URLS["2023Q1"]]
    assert all("/123456/" in url for url in calls[2:])
    assert payload["complete_sample_acquired"] is True
    assert payload["attempt_count"] == 18
    assert len(payload["filings"]) == 16
    assert [row["candidate"]["form_type"] for row in payload["filings"]] == (
        ["4"] * 6 + ["4/A"] * 2 + ["4"] * 6 + ["4/A"] * 2)
    assert all(row["status"] == "acquired_noncanonical" for row in payload["filings"])
    assert payload["research_looks"] == 0
    assert payload["direct_ib1c_ingest_authorized"] is False
    assert "pilot@example.org" not in report.read_text(encoding="utf-8")
    assert "pilot@example.org" not in (report.parent / "attempts.jsonl").read_text(encoding="utf-8")
    for url in calls:
        digest = hash_bytes(images[url])
        assert (report.parent / "objects" / f"{digest}.bin").read_bytes() == images[url]
    assert len(payload["master_indexes"][0]["subset"]) == 8
    assert len(payload["master_indexes"][1]["subset"]) == 8
    assert len(payload["master_indexes"][0]["receipt"].get("rows", [])) == 0


def test_alias_paths_keep_issuer_path_selection_from_exact_index(monkeypatch, tmp_path):
    images = _images()
    first = runner._MASTER_URLS["2022Q4"]
    candidate = _candidates()[0]
    alias = (
        f"2178|Invented Owner|{candidate.form_type}|{candidate.filing_date}|"
        f"edgar/data/2178/{candidate.accession_number}.txt\n"
    ).encode("ascii")
    images[first] = gzip.compress(_index(_candidates(), "2022Q4") + alias, mtime=0)
    calls = []
    _, payload = _run(monkeypatch, tmp_path, _transport(images, calls))
    assert payload["complete_sample_acquired"] is True
    assert len(calls) == 18
    assert len(payload["master_indexes"][0]["subset"]) == 8
    assert payload["master_indexes"][0]["receipt"]["form4_or_4a_row_count"] == 9
    assert calls[2] == (
        runner._HOST_PREFIX + f"edgar/data/123456/{candidate.accession_number}.txt"
    )
    assert all("/2178/" not in url for url in calls[2:])


@pytest.mark.parametrize("status", (403, 429, 302, 404))
def test_first_master_denial_refuses_and_makes_no_followup_request(monkeypatch, tmp_path, status):
    images = _images()
    calls = []
    first = runner._MASTER_URLS["2022Q4"]
    _, payload = _run(monkeypatch, tmp_path,
                      _transport(images, calls, statuses={(first, 1): status}))
    assert calls == [first]
    assert payload["complete_sample_acquired"] is False
    assert all(row["status"] == "not_attempted" for row in payload["filings"])


def test_second_master_missing_target_aborts_before_any_submission(monkeypatch, tmp_path):
    images = _images()
    images[runner._MASTER_URLS["2023Q1"]] = gzip.compress(_INDEX_HEADER, mtime=0)
    calls = []
    monkeypatch.setattr(runner.time, "sleep", lambda value: None)
    _, payload = _run(monkeypatch, tmp_path, _transport(images, calls))
    assert calls == [runner._MASTER_URLS["2022Q4"], runner._MASTER_URLS["2023Q1"]]
    assert payload["complete_sample_acquired"] is False
    assert all(row["status"] == "not_attempted" for row in payload["filings"])


def test_unselected_quarter_index_rows_do_not_enter_derived_report(monkeypatch, tmp_path):
    images = _images()
    second = runner._MASTER_URLS["2023Q1"]
    extra = (b"888888|Unselected Invented|4|2023-03-31|edgar/data/888888/"
             b"0099999999-23-000001.txt\n")
    images[second] = gzip.compress(_index(_candidates(), "2023Q1") + extra, mtime=0)
    calls = []
    report, payload = _run(monkeypatch, tmp_path, _transport(images, calls))
    assert payload["complete_sample_acquired"] is True
    assert len(calls) == 18
    assert payload["master_indexes"][1]["receipt"]["form4_or_4a_row_count"] == 9
    assert len(payload["master_indexes"][1]["subset"]) == 8
    assert "0099999999-23-000001" not in report.read_text(encoding="utf-8")


def test_transport_retries_three_times_then_stops_without_next_request(monkeypatch, tmp_path):
    images = _images()
    calls = []
    first = runner._MASTER_URLS["2022Q4"]
    clock = [1_000_000_000]

    def now_ns():
        clock[0] += 1_000
        return clock[0]

    def advance(seconds):
        clock[0] += int(seconds * 1_000_000_000) + 1_000

    monkeypatch.setattr(runner.time, "monotonic_ns", now_ns)
    monkeypatch.setattr(runner.time, "sleep", advance)
    _, payload = _run(monkeypatch, tmp_path, _transport(images, calls,
        statuses={(first, 1): OSError("injected"), (first, 2): OSError("injected"),
                  (first, 3): OSError("injected")}))
    assert calls == [first, first, first]
    assert payload["attempt_count"] == 3
    assert payload["complete_sample_acquired"] is False


def test_gzip_expansion_cap_refuses_before_second_request(monkeypatch, tmp_path):
    images = _images()
    first = runner._MASTER_URLS["2022Q4"]
    images[first] = gzip.compress(b"Z" * 2048, mtime=0)
    monkeypatch.setattr(runner, "MAX_MASTER_INDEX_BYTES", 1024)
    calls = []
    _, payload = _run(monkeypatch, tmp_path, _transport(images, calls))
    assert calls == [first]
    assert "expands" in payload["halted_reason"]


def test_early_sleep_does_not_waive_actual_half_second_spacing(monkeypatch, tmp_path):
    images = _images()
    calls = []
    monkeypatch.setattr(runner.time, "monotonic_ns", lambda: 1_000_000_000)
    monkeypatch.setattr(runner.time, "sleep", lambda value: None)
    source, prior, output = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "MIN_REQUEST_INTERVAL_NS", 500_000_000)
    report = runner.run_fixed_complete_submissions(
        source, prior, output, contact_email="pilot@example.org",
        capture_git_commit=COMMIT, transport=_transport(images, calls),
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert calls == [runner._MASTER_URLS["2022Q4"]]
    assert payload["complete_sample_acquired"] is False
    assert "pacing" in payload["halted_reason"]


def test_journal_fsync_delay_does_not_make_next_dispatch_early(monkeypatch, tmp_path):
    images = _images()
    calls = []
    clock = [1_000_000_000]
    monkeypatch.setattr(runner.time, "monotonic_ns", lambda: clock[0])
    monkeypatch.setattr(runner.time, "sleep",
                        lambda seconds: clock.__setitem__(0, clock[0] + int(seconds * 1_000_000_000)))
    original_event = runner._Journal.event

    def delayed_event(self, payload):
        original_event(self, payload)
        if payload["kind"] == "attempt-start" and payload["ordinal"] == 1:
            clock[0] += 800_000_000  # Synthetic fsync delay after the reservation timestamp.

    monkeypatch.setattr(runner._Journal, "event", delayed_event)
    source, prior, output = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "MIN_REQUEST_INTERVAL_NS", 500_000_000)
    report = runner.run_fixed_complete_submissions(
        source, prior, output, contact_email="pilot@example.org",
        capture_git_commit=COMMIT, transport=_transport(images, calls),
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["complete_sample_acquired"] is True
    events = [json.loads(line) for line in (output / "attempts.jsonl").read_text().splitlines()]
    dispatches = [event["request_start_monotonic_ns"] for event in events
                  if event["kind"] == "attempt-finish"]
    assert len(dispatches) == 18
    assert all(later - earlier >= 500_000_000
               for earlier, later in zip(dispatches, dispatches[1:]))


def test_delayed_first_send_cannot_collapse_next_send_interval(monkeypatch, tmp_path):
    """A slow DNS/TLS phase can put send near the transport's return."""
    images = _images()
    clock = [1_000_000_000]
    sends = []
    monkeypatch.setattr(runner.time, "monotonic_ns", lambda: clock[0])
    monkeypatch.setattr(runner.time, "sleep",
                        lambda seconds: clock.__setitem__(0, clock[0] + int(seconds * 1_000_000_000)))
    source, prior, output = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "MIN_REQUEST_INTERVAL_NS", 500_000_000)

    def delayed_transport(url, headers, max_bytes):
        if not sends:
            clock[0] += 1_000_000_000  # Synthetic delayed DNS/TLS, then immediate response.
        sends.append(clock[0])
        body = images[url]
        return runner.SecHttpResult(200, (("Content-Length", str(len(body))),), body)

    report = runner.run_fixed_complete_submissions(
        source, prior, output, contact_email="pilot@example.org",
        capture_git_commit=COMMIT, transport=delayed_transport,
    )
    assert json.loads(report.read_text(encoding="utf-8"))["complete_sample_acquired"] is True
    assert len(sends) == 18
    assert all(later - earlier >= 500_000_000 for earlier, later in zip(sends, sends[1:]))


def test_cli_requires_private_prompt_not_contact_argument(monkeypatch):
    with pytest.raises(SystemExit):
        runner.main(["--input-root", "/synthetic/source", "--prior-pilot-root", "/synthetic/prior",
                     "--output-root", "/synthetic/output", "--capture-git-commit", COMMIT,
                     "--contact-email", "pilot@example.org"])


def test_journal_reader_uses_checked_regular_byte_reader(monkeypatch, tmp_path):
    images = _images()
    calls = []
    source, prior, output = _setup(monkeypatch, tmp_path)
    seen = []
    real = runner._read_regular_bytes

    def checked(path, **kwargs):
        seen.append(Path(path).name)
        return real(path, **kwargs)

    monkeypatch.setattr(runner, "_read_regular_bytes", checked)
    report = runner.run_fixed_complete_submissions(
        source, prior, output, contact_email="pilot@example.org",
        capture_git_commit=COMMIT, transport=_transport(images, calls,
            statuses={(runner._MASTER_URLS["2022Q4"], 1): 403}),
    )
    assert report.exists()
    assert "attempts.jsonl" in seen


def test_checked_journal_refuses_symlink_and_oversize_before_publication(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "objects").mkdir()
    identity = (output.stat().st_dev, output.stat().st_ino)
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"invented\n")
    journal = output / "attempts.jsonl"
    journal.symlink_to(outside)
    with pytest.raises(runner.SecCompleteAcquisitionError, match="journal"):
        runner._report(output, identity, {"synthetic": True})
    assert not (output / "commit.json").exists()
    journal.unlink()
    journal.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="REFUSED"):
        runner._report(output, identity, {"synthetic": True})
    assert not (output / "commit.json").exists()


def test_partial_crash_retains_reservation_and_cannot_reuse_output_root(monkeypatch, tmp_path):
    source, prior, output = _setup(monkeypatch, tmp_path)
    calls = []

    def crash(url, headers, max_bytes):
        calls.append(url)
        raise KeyboardInterrupt("synthetic interruption")

    with pytest.raises(KeyboardInterrupt):
        runner.run_fixed_complete_submissions(
            source, prior, output, contact_email="pilot@example.org",
            capture_git_commit=COMMIT, transport=crash,
        )
    journal = (output / "attempts.jsonl").read_text(encoding="utf-8")
    assert "attempt-start" in journal and "attempt-finish" not in journal
    assert not (output / "commit.json").exists()
    with pytest.raises(ValueError, match="output root must not exist"):
        runner.run_fixed_complete_submissions(
            source, prior, output, contact_email="pilot@example.org",
            capture_git_commit=COMMIT, transport=crash,
        )
    assert calls == [runner._MASTER_URLS["2022Q4"]]


@pytest.mark.parametrize("change", ("form", "date", "issuer", "row_sha", "zip_sha", "period"))
def test_changed_fixed_source_tuple_refuses_before_output_or_request(monkeypatch, tmp_path, change):
    source, prior, output = _setup(monkeypatch, tmp_path)
    candidates = list(_candidates())
    replacements = {
        "form": {"form_type": "4/A"},
        "date": {"filing_date": "2022-11-08"},
        "issuer": {"issuer_cik": "0000999999"},
        "row_sha": {"submission_row_id": "e" * 64},
        "zip_sha": {"quarterly_zip_sha256": "f" * 64},
        "period": {"period": "2023Q1"},
    }
    candidates[0] = replace(candidates[0], **replacements[change])
    monkeypatch.setattr(runner, "select_fixed_pilot", lambda a, b: tuple(candidates))
    calls = []
    with pytest.raises(runner.SecCompleteAcquisitionError, match="pinned sixteen"):
        runner.run_fixed_complete_submissions(
            source, prior, output, contact_email="pilot@example.org",
            capture_git_commit=COMMIT, transport=_transport(_images(), calls),
        )
    assert calls == [] and not output.exists()


@pytest.mark.parametrize("defect", ("valid", "dirty", "head", "dependency"))
def test_exact_committed_code_gate_refuses_changed_tree(monkeypatch, defect):
    root = Path(runner.__file__).resolve().parents[1]

    def git_output(command, **kwargs):
        if command == ("git", "rev-parse", "--show-toplevel"):
            return (str(root) + "\n").encode()
        if command == ("git", "branch", "--show-current"):
            return b"codex/strategy-insider-buying\n"
        if command == ("git", "rev-parse", "HEAD"):
            return (("f" * 40 if defect == "head" else COMMIT) + "\n").encode()
        if command == ("git", "status", "--porcelain=v1", "--untracked-files=all"):
            return b" M research/insider_buying_sec_complete_acquisition.py\n" if defect == "dirty" else b""
        if command[:2] == ("git", "show"):
            relative = command[2].split(":", 1)[1]
            raw = (root / relative).read_bytes()
            return raw + b"altered" if defect == "dependency" and relative.endswith("sec_complete_submission.py") else raw
        pytest.fail(f"unexpected command: {command!r}")

    monkeypatch.setattr(runner.subprocess, "check_output", git_output)
    if defect == "valid":
        runner._verify_exact_committed_code(COMMIT)
    else:
        with pytest.raises(runner.SecCompleteAcquisitionError, match="REFUSED"):
            runner._verify_exact_committed_code(COMMIT)


def test_importing_lane_package_does_not_import_standalone_transport_runner():
    code = (
        "import importlib,pkgutil,sys\n"
        "import research.insider_buying as p\n"
        "for m in pkgutil.iter_modules(p.__path__):\n"
        " importlib.import_module('research.insider_buying.'+m.name)\n"
        "blocked=('research.insider_buying_sec_complete_acquisition','http.client','socket','ssl','subprocess')\n"
        "bad=[n for n in sys.modules if any(n==x or n.startswith(x+'.') for x in blocked)]\n"
        "print(','.join(sorted(bad)))\n"
    )
    result = subprocess.run([sys.executable, "-B", "-c", code],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, check=True, timeout=60)
    assert result.stdout.strip() == ""


def test_plain_runner_import_has_no_network_call(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("import attempted network connection")
    monkeypatch.setattr(runner.http.client, "HTTPSConnection", forbidden)
    assert runner.COMPLETE_ACQUISITION_VERSION.endswith("-v1")


def test_fresh_runner_import_does_not_invoke_sec_transport():
    code = (
        "import http.client\n"
        "def forbidden(*args, **kwargs): raise AssertionError('import connected')\n"
        "http.client.HTTPSConnection=forbidden\n"
        "import research.insider_buying_sec_complete_acquisition as runner\n"
        "print(runner.COMPLETE_ACQUISITION_VERSION)\n"
    )
    result = subprocess.run([sys.executable, "-B", "-c", code],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, check=True, timeout=60)
    assert result.stdout.strip() == runner.COMPLETE_ACQUISITION_VERSION
