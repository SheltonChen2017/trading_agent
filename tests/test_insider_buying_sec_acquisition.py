"""Synthetic-only refusal and crash-boundary tests for the fixed SEC pilot.

Every network response and prior-source candidate in this file is invented.
No test reads the approved external ZIPs or connects to SEC.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from data.hashing import hash_bytes, hash_payload
from research import insider_buying_sec_acquisition as pilot


CONTACT = "synthetic-contact@example.invalid"
COMMIT = "c" * 40
ZIP_HASH = "a" * 64
ROW_HASH = "b" * 64
ISSUER_CIK = "0000123456"
INDEX = b'{"directory":{"item":[{"name":"ownership.xml"}]}}'


def _candidates() -> tuple[pilot.SecPilotCandidate, ...]:
    items = []
    for year, quarter, filing_date in (
        (2022, 4, "2022-11-07"), (2023, 1, "2023-03-13"),
    ):
        for ordinal in range(1, 9):
            accession = f"0000999999-{year % 100:02d}-{ordinal:06d}"
            items.append(pilot.SecPilotCandidate(
                period=f"{year}Q{quarter}", accession_number=accession,
                form_type="4" if ordinal <= 6 else "4/A",
                filing_date_raw="07-NOV-2022" if year == 2022 else "13-MAR-2023",
                filing_date=filing_date, issuer_cik=ISSUER_CIK,
                quarterly_zip_sha256=ZIP_HASH, submission_row_id=ROW_HASH,
                raw_snapshot_id="synthetic-only", raw_lineage_sha256="d" * 64,
            ))
    return tuple(items)


def _header(candidate: pilot.SecPilotCandidate, *, wrong_accession: bool = False) -> bytes:
    accession = "0000999999-22-999999" if wrong_accession else candidate.accession_number
    accepted = "20221107101112" if candidate.period == "2022Q4" else "20230313101112"
    return (
        "<SEC-HEADER>\n"
        f"ACCESSION NUMBER: {accession}\n"
        f"CONFORMED SUBMISSION TYPE: {candidate.form_type}\n"
        f"FILED AS OF DATE: {candidate.filing_date.replace('-', '')}\n"
        f"<ACCEPTANCE-DATETIME>{accepted}\n"
        "ISSUER:\n COMPANY DATA:\n  CENTRAL INDEX KEY: 123456\n"
        "REPORTING-OWNER:\n COMPANY DATA:\n  CENTRAL INDEX KEY: 999999\n"
        "</SEC-HEADER>\n"
    ).encode("ascii")


def _xml(candidate: pilot.SecPilotCandidate) -> bytes:
    return (
        "<ownershipDocument>"
        f"<documentType>{candidate.form_type}</documentType>"
        "<issuer><issuerCik>0000123456</issuerCik></issuer>"
        "</ownershipDocument>"
    ).encode("ascii")


def _tag_header(candidate: pilot.SecPilotCandidate) -> bytes:
    return (
        f'<SEC-HEADER>{candidate.accession_number}.hdr.sgml : '
        f'{candidate.filing_date.replace("-", "")}\n'
        '<ACCEPTANCE-DATETIME>' + ('20221107101112' if candidate.period == '2022Q4' else '20230313101112') + '\n'
        f'<ACCESSION-NUMBER>{candidate.accession_number}\n'
        f'<TYPE>{candidate.form_type}\n'
        f'<FILING-DATE>{candidate.filing_date.replace("-", "")}\n'
        '<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>0000999999\n</OWNER-DATA>\n</REPORTING-OWNER>\n'
        '<ISSUER>\n<COMPANY-DATA>\n<CIK>0000123456\n</COMPANY-DATA>\n</ISSUER>\n'
        '</SEC-HEADER>\n'
    ).encode('ascii')


def test_tag_header_compatibility_parses_scoped_identity_without_verifying_timezone():
    candidate = _candidates()[0]
    target = pilot.SecAcquisitionTarget(
        period=candidate.period, accession_number=candidate.accession_number,
        form_type=candidate.form_type, filing_date=candidate.filing_date,
        issuer_cik=candidate.issuer_cik, quarterly_zip_sha256=candidate.quarterly_zip_sha256,
        submission_row_id=candidate.submission_row_id, primary_xml_filename='ownership.xml',
    )
    receipt = pilot._validate_tag_header(_tag_header(candidate), target)
    assert receipt['raw_header_sha256'] == hash_bytes(_tag_header(candidate))
    assert receipt['source_fields']['issuer_cik_raw'] == '0000123456'
    assert receipt['accepted_at_interpretation'].startswith('2022-11-07T10:11:12-05:00')
    assert receipt['timezone_interpretation_verified'] is False
    assert receipt['retrieval_timestamp_unavailable'] is True
    assert receipt['direct_ib1c_ingest_authorized'] is False


@pytest.mark.parametrize('mutator', [
    lambda b: b.replace(b'<ACCESSION-NUMBER>', b'<OWNER-DATA>\n<ACCESSION-NUMBER>', 1),
    lambda b: b.replace(b'<TYPE>4\n', b'<TYPE>4\n<TYPE>4/A\n', 1),
    lambda b: b.replace(b'<COMPANY-DATA>\n<CIK>0000123456', b'<COMPANY-DATA>\n<CIK>0000999999', 1),
    lambda b: b.replace(b'<COMPANY-DATA>\n<CIK>0000123456', b'<COMPANY-DATA>\n<CIK>0000123456\n<CIK>0000123456', 1),
    lambda b: b.replace(b'<ACCEPTANCE-DATETIME>20221107101112', b'<ACCEPTANCE-DATETIME>20221106013000', 1),
    lambda b: b.replace(b'</REPORTING-OWNER>\n', b'', 1),
])
def test_tag_header_refuses_nested_duplicate_wrong_issuer_or_ambiguous_time(mutator):
    candidate = _candidates()[0]
    target = pilot.SecAcquisitionTarget(
        period=candidate.period, accession_number=candidate.accession_number,
        form_type=candidate.form_type, filing_date=candidate.filing_date,
        issuer_cik=candidate.issuer_cik, quarterly_zip_sha256=candidate.quarterly_zip_sha256,
        submission_row_id=candidate.submission_row_id, primary_xml_filename='ownership.xml',
    )
    with pytest.raises(pilot.SecPilotError):
        pilot._validate_tag_header(mutator(_tag_header(candidate)), target)


@pytest.fixture
def synthetic_run(monkeypatch, tmp_path):
    root = tmp_path.resolve()
    source = root / "source"
    prior = root / "prior"
    output = root / "output"
    source.mkdir()
    prior.mkdir()
    candidates = _candidates()
    monkeypatch.setattr(pilot, "select_fixed_pilot", lambda *args: candidates)
    monkeypatch.setattr(pilot, "MIN_REQUEST_INTERVAL_SECONDS", 0)
    return source, prior, output, candidates


def _fake_fetch(candidates, *, wrong_header_for=None):
    called = []

    def fetch(path, user_agent):
        assert path.startswith("/Archives/edgar/data/123456/")
        assert user_agent == f"InsiderBuyingResearch/0.1 ({CONTACT})"
        called.append(path)
        candidate = next(item for item in candidates if path.startswith(item.archive_path))
        if path == candidate.archive_path + "index.json":
            return 200, INDEX
        if path == candidate.archive_path + candidate.accession_number + ".hdr.sgml":
            return 200, _header(candidate, wrong_accession=candidate.accession_number == wrong_header_for)
        if path == candidate.archive_path + "ownership.xml":
            return 200, _xml(candidate)
        pytest.fail(f"unapproved path: {path}")

    return fetch, called


def _run(inputs):
    source, prior, output, _ = inputs
    return pilot.run_fixed_sec_pilot(
        source, prior, output, contact_email=CONTACT, capture_git_commit=COMMIT,
    )


@pytest.fixture
def synthetic_first_pass(monkeypatch, synthetic_run):
    candidates = synthetic_run[3]

    def fetch(path, user_agent):
        candidate = next(item for item in candidates if path.startswith(item.archive_path))
        if path == candidate.archive_path + 'index.json':
            return 200, INDEX
        if path == candidate.archive_path + candidate.accession_number + '.hdr.sgml':
            return 200, _tag_header(candidate)
        pytest.fail('first pass must not fetch XML with incompatible v1 header')

    monkeypatch.setattr(pilot, '_fetch_sec', fetch)
    report = _run(synthetic_run)
    assert json.loads(report.read_bytes())['attempt_count'] == 32
    monkeypatch.setattr(pilot, 'FIRST_PASS_REPORT_SHA256', hash_bytes(report.read_bytes()))
    return synthetic_run, report


def test_offline_first_pass_replay_checks_all_32_receipts_and_tag_headers(synthetic_first_pass):
    inputs, report = synthetic_first_pass
    replay = pilot.replay_first_sec_pass(
        inputs[2], inputs[3], prior_code_commit=pilot.FIRST_PASS_CODE_COMMIT,
    )
    assert replay.report_sha256 == hash_bytes(report.read_bytes())
    assert len(replay.sources) == 16
    assert len(replay.prior_paths) == 32
    assert all(source.tag_receipt['timezone_interpretation_verified'] is False
               for source in replay.sources)
    assert all(source.first_pass_reason.startswith('REFUSED:') for source in replay.sources)


def test_first_pass_replay_refuses_corrupt_object_before_continuation(synthetic_first_pass):
    inputs, report = synthetic_first_pass
    descriptor = json.loads(report.read_bytes())['rows'][0]['artifacts']['header']
    (inputs[2] / descriptor['relative_path']).write_bytes(b'changed synthetic header')
    with pytest.raises(pilot.SecPilotError):
        pilot.replay_first_sec_pass(inputs[2], inputs[3], prior_code_commit=pilot.FIRST_PASS_CODE_COMMIT)


def test_first_pass_replay_refuses_journal_path_drift(synthetic_first_pass):
    inputs, _ = synthetic_first_pass
    journal = inputs[2] / 'attempts.jsonl'
    journal.write_text(journal.read_text().replace('/index.json', '/not-index.json', 1))
    with pytest.raises(pilot.SecPilotError, match='journal'):
        pilot.replay_first_sec_pass(inputs[2], inputs[3], prior_code_commit=pilot.FIRST_PASS_CODE_COMMIT)


def test_xml_continuation_uses_only_sixteen_replayed_index_named_paths(monkeypatch, synthetic_first_pass):
    inputs, first_report = synthetic_first_pass
    source, prior, first, candidates = inputs
    output = first.parent / 'xml-continuation'
    first_report_sha = hash_bytes(first_report.read_bytes())
    first_journal_sha = hash_bytes((first / 'attempts.jsonl').read_bytes())
    calls = []

    def xml_only(path, user_agent):
        assert path.endswith('/ownership.xml')
        assert user_agent == f'InsiderBuyingResearch/0.1 ({CONTACT})'
        calls.append(path)
        candidate = next(item for item in candidates if path.startswith(item.archive_path))
        return 200, _xml(candidate)

    monkeypatch.setattr(pilot, '_fetch_sec', xml_only)
    monkeypatch.setattr(pilot, '_verify_continuation_code_commit', lambda _: None)
    result = pilot.run_fixed_sec_xml_continuation(
        source, prior, first, output, contact_email=CONTACT,
        prior_code_commit=pilot.FIRST_PASS_CODE_COMMIT, continuation_code_commit=COMMIT,
    )
    payload = json.loads(result.read_bytes())
    assert len(calls) == len(set(calls)) == 16
    assert calls == [candidate.archive_path + 'ownership.xml' for candidate in candidates]
    assert payload['new_attempt_count'] == 16
    assert payload['cumulative_attempt_count'] == payload['cumulative_distinct_artifact_count'] == 48
    assert payload['first_pass_report_sha256'] == first_report_sha
    assert payload['first_pass_journal_sha256'] == first_journal_sha
    assert payload['first_pass_code_commit_operator_attested'] == pilot.FIRST_PASS_CODE_COMMIT
    assert payload['prior_code_sha_artifact_verified'] is False
    assert payload['continuation_code_commit_verified'] == COMMIT
    assert payload['acquisition_available'] is True
    assert all(row['status'] == 'acquired_noncanonical' for row in payload['rows'])
    assert all(set(row['artifacts']) == {'index', 'header', 'xml'} for row in payload['rows'])
    assert all(row['tag_header_validation']['direct_ib1c_ingest_authorized'] is False for row in payload['rows'])
    events = [json.loads(line) for line in (output / 'attempts.jsonl').read_text().splitlines()]
    assert events[0]['kind'] == 'verified-first-pass-replayed'
    assert [event['ordinal'] for event in events if event['kind'] == 'attempt-reserved'] == list(range(33, 49))
    assert CONTACT.encode() not in b''.join(path.read_bytes() for path in output.rglob('*') if path.is_file())
    assert hash_bytes(first_report.read_bytes()) == first_report_sha
    assert hash_bytes((first / 'attempts.jsonl').read_bytes()) == first_journal_sha


def test_continuation_refuses_corrupt_prior_object_without_output_or_request(monkeypatch, synthetic_first_pass):
    inputs, first_report = synthetic_first_pass
    source, prior, first, _ = inputs
    object_ref = json.loads(first_report.read_bytes())['rows'][0]['artifacts']['index']['relative_path']
    (first / object_ref).write_bytes(b'corrupt')
    monkeypatch.setattr(pilot, '_verify_continuation_code_commit', lambda _: None)
    monkeypatch.setattr(pilot, '_fetch_sec', lambda *args: pytest.fail('network before replay'))
    output = first.parent / 'must-not-exist'
    with pytest.raises(pilot.SecPilotError):
        pilot.run_fixed_sec_xml_continuation(source, prior, first, output,
            contact_email=CONTACT, prior_code_commit=pilot.FIRST_PASS_CODE_COMMIT,
            continuation_code_commit=COMMIT)
    assert not output.exists()


def test_continuation_output_cannot_overlap_first_root(monkeypatch, synthetic_first_pass):
    inputs, _ = synthetic_first_pass
    source, prior, first, _ = inputs
    monkeypatch.setattr(pilot, '_verify_continuation_code_commit', lambda _: None)
    monkeypatch.setattr(pilot, '_fetch_sec', lambda *args: pytest.fail('network before root guard'))
    with pytest.raises(pilot.SecPilotError, match='overlaps'):
        pilot.run_fixed_sec_xml_continuation(source, prior, first, first / 'nested',
            contact_email=CONTACT, prior_code_commit=pilot.FIRST_PASS_CODE_COMMIT,
            continuation_code_commit=COMMIT)


@pytest.mark.parametrize('dirty', [b' M research/local.py\n', b'?? untracked.local\n'])
def test_continuation_git_binding_refuses_dirty_or_untracked_lane(monkeypatch, dirty):
    root = Path(pilot.__file__).resolve().parents[1]
    source = Path(pilot.__file__).read_bytes()

    def git_output(command, **kwargs):
        assert kwargs['cwd'] == root
        if command == ('git', 'rev-parse', '--show-toplevel'):
            return (str(root) + '\n').encode()
        if command == ('git', 'branch', '--show-current'):
            return b'codex/strategy-insider-buying\n'
        if command == ('git', 'rev-parse', 'HEAD'):
            return (COMMIT + '\n').encode()
        if command == ('git', 'status', '--porcelain=v1', '--untracked-files=all'):
            return dirty
        if command == ('git', 'show', f'{COMMIT}:research/insider_buying_sec_acquisition.py'):
            return source
        pytest.fail(f'unexpected git command {command}')

    monkeypatch.setattr(pilot.subprocess, 'check_output', git_output)
    with pytest.raises(pilot.SecPilotError, match='clean committed lane source'):
        pilot._verify_continuation_code_commit(COMMIT)


def test_synthetic_success_uses_exact_three_routes_per_frozen_candidate_and_zero_authority(
    monkeypatch, synthetic_run,
):
    source, prior, output, candidates = synthetic_run
    fetch, called = _fake_fetch(candidates)
    monkeypatch.setattr(pilot, "_fetch_sec", fetch)
    report = _run(synthetic_run)
    payload = json.loads(report.read_bytes())
    assert payload["kind"] == pilot.PILOT_VERSION
    assert payload["inventory_sha256"] == hash_payload([item.to_payload() for item in candidates])
    assert payload["attempt_count"] == payload["distinct_artifact_count"] == 48
    assert len(called) == 48 == len(set(called))
    assert len(payload["rows"]) == 16
    assert all(row["status"] == "acquired_noncanonical" for row in payload["rows"])
    assert payload["acquisition_available"] is True
    assert all(row["primary_xml_filename"] == "ownership.xml" for row in payload["rows"])
    assert all(row["header_projection"]["authority"]["direct_ib1c_ingest_authorized"] is False
               for row in payload["rows"])
    assert payload["canonical"] is False
    assert payload["point_in_time_data"] is False
    assert payload["direct_ib1c_ingest_authorized"] is False
    assert payload["index_route_version"] == pilot.INDEX_ROUTE_VERSION
    assert payload["research_looks"] == payload["authorized_outcome_looks"] == payload["consumed_outcome_looks"] == 0
    for candidate in candidates:
        assert candidate.archive_path + "index.json" in called
        assert candidate.archive_path + candidate.accession_number + ".hdr.sgml" in called
        assert candidate.archive_path + "ownership.xml" in called
    assert (output / "commit.json").is_file()
    assert CONTACT.encode() not in b"".join(path.read_bytes() for path in output.rglob("*") if path.is_file())
    journal = [json.loads(line) for line in (output / "attempts.jsonl").read_text().splitlines()]
    assert [event["ordinal"] for event in journal if event["kind"] == "attempt-reserved"] == list(range(1, 49))
    assert journal[-1] == {
        "kind": "pilot-finished", "attempts": 48, "distinct_artifacts": 48,
        "inventory_sha256": payload["inventory_sha256"],
    }


def test_inventory_is_persisted_and_hash_bound_before_first_request(monkeypatch, synthetic_run):
    source, prior, output, candidates = synthetic_run

    def interrupt_at_first_request(path, user_agent):
        # This interruption simulates a process death after its first durable
        # attempt reservation. The frozen source inventory must already exist.
        raise KeyboardInterrupt("synthetic crash before network")

    monkeypatch.setattr(pilot, "_fetch_sec", interrupt_at_first_request)
    with pytest.raises(KeyboardInterrupt):
        _run(synthetic_run)
    inventory_path = output / "inventory.json"
    assert inventory_path.is_file()
    inventory = json.loads(inventory_path.read_bytes())
    assert inventory["inventory_sha256"] == hash_payload([item.to_payload() for item in candidates])
    assert inventory["candidates"] == [item.to_payload() for item in candidates]
    assert inventory["index_route_version"] == pilot.INDEX_ROUTE_VERSION
    assert not (output / "commit.json").exists()
    journal = [json.loads(line) for line in (output / "attempts.jsonl").read_text().splitlines()]
    assert journal[0]["kind"] == "attempt-reserved"
    assert journal[0]["ordinal"] == 1


def test_header_identity_refusal_quarantines_only_that_accession(monkeypatch, synthetic_run):
    _, _, output, candidates = synthetic_run
    bad = candidates[0].accession_number
    fetch, called = _fake_fetch(candidates, wrong_header_for=bad)
    monkeypatch.setattr(pilot, "_fetch_sec", fetch)
    report = _run(synthetic_run)
    payload = json.loads(report.read_bytes())
    assert len(payload["rows"]) == 16
    assert payload["rows"][0]["status"] == "quarantined"
    assert payload["rows"][0]["reason"].startswith("REFUSED:")
    assert payload["rows"][0]["artifacts"]["header"]["sha256"] == hash_bytes(
        _header(candidates[0], wrong_accession=True)
    )
    assert "xml" not in payload["rows"][0]["artifacts"]
    assert "header_projection" not in payload["rows"][0]
    assert all(row["status"] == "acquired_noncanonical" for row in payload["rows"][1:])
    assert payload["acquisition_available"] is False
    assert candidates[0].archive_path + "ownership.xml" not in called
    assert len(called) == 47
    assert (output / "commit.json").is_file()


def test_sec_403_stops_all_further_requests_and_retains_unattempted_rows(monkeypatch, synthetic_run):
    _, _, output, candidates = synthetic_run
    called = []

    def denied(path, user_agent):
        called.append(path)
        return 403, b"denied"

    monkeypatch.setattr(pilot, "_fetch_sec", denied)
    report = _run(synthetic_run)
    payload = json.loads(report.read_bytes())
    assert called == [candidates[0].archive_path + "index.json"]
    assert payload["halted_on_sec_access"] is True
    assert payload["attempt_count"] == payload["distinct_artifact_count"] == 1
    assert len(payload["rows"]) == 16
    assert all(row["status"] == "quarantined" for row in payload["rows"])
    assert payload["acquisition_available"] is False
    assert all(row["reason"] == "not attempted after SEC access stop" for row in payload["rows"][1:])
    assert (output / "commit.json").is_file()


def test_exhausted_sec_503_stops_entire_pilot_after_three_attempts(monkeypatch, synthetic_run):
    _, _, _, candidates = synthetic_run
    called = []
    monkeypatch.setattr(pilot, '_fetch_sec', lambda path, agent: (called.append(path) or (503, b'')))
    monkeypatch.setattr(pilot.time, 'sleep', lambda _: None)
    report = _run(synthetic_run)
    payload = json.loads(report.read_bytes())
    assert called == [candidates[0].archive_path + 'index.json'] * 3
    assert payload['halted_on_sec_access'] is True
    assert payload['attempt_count'] == 3
    assert payload['rows'][0]['status'] == 'quarantined'
    assert '503' in payload['rows'][0]['reason']
    assert all(row['reason'] == 'not attempted after SEC access stop' for row in payload['rows'][1:])


def test_first_response_framing_refusal_stops_entire_pilot(monkeypatch, synthetic_run):
    called = []

    class Response:
        status = 200

        def getheaders(self):
            return [('Transfer-Encoding', 'chunked')]

    class Connection:
        def __init__(self, host, timeout):
            assert host == 'www.sec.gov'

        def request(self, method, path, headers):
            called.append(path)

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(pilot.http.client, 'HTTPSConnection', Connection)
    report = _run(synthetic_run)
    payload = json.loads(report.read_bytes())
    assert called == [synthetic_run[3][0].archive_path + 'index.json']
    assert payload['halted_on_sec_access'] is True
    assert payload['attempt_count'] == 1
    assert 'Content-Length' in payload['rows'][0]['reason']
    assert all(row['reason'] == 'not attempted after SEC access stop' for row in payload['rows'][1:])


def test_redirect_has_no_fallback_or_xml_fetch(monkeypatch, synthetic_run):
    _, _, _, candidates = synthetic_run
    called = []

    def redirect(path, user_agent):
        called.append(path)
        return 302, b"redirect"

    monkeypatch.setattr(pilot, "_fetch_sec", redirect)
    report = _run(synthetic_run)
    payload = json.loads(report.read_bytes())
    assert len(called) == 16
    assert set(called) == {item.archive_path + "index.json" for item in candidates}
    assert all(row["status"] == "quarantined" for row in payload["rows"])


def test_attempt_is_fsynced_before_transport_and_network_errors_never_reset_budget(monkeypatch, tmp_path):
    output = tmp_path.resolve()
    journal = pilot._Journal(output)
    monkeypatch.setattr(pilot, "MIN_REQUEST_INTERVAL_SECONDS", 0)
    calls = []
    fsync_calls = []
    real_fsync = os.fsync

    def fsync(fd):
        fsync_calls.append(fd)
        return real_fsync(fd)

    def failing_fetch(path, user_agent):
        calls.append(path)
        rows = [json.loads(line) for line in (output / "attempts.jsonl").read_text().splitlines()]
        assert rows[-1]["kind"] == "attempt-reserved"
        assert rows[-1]["ordinal"] == len(calls)
        assert len(fsync_calls) >= len(calls)
        raise OSError("synthetic transport failure")

    monkeypatch.setattr(pilot.os, "fsync", fsync)
    monkeypatch.setattr(pilot, "_fetch_sec", failing_fetch)
    monkeypatch.setattr(pilot.time, "sleep", lambda _: None)
    try:
        with pytest.raises(pilot.SecPilotError, match="exhausted bounded transport retries"):
            journal.fetch("/Archives/edgar/data/123456/000099999922000001/index.json", "synthetic")
    finally:
        journal.close()
    assert len(calls) == journal.count == 3
    assert len(journal.distinct) == 1
    with pytest.raises(FileExistsError):
        pilot._Journal(output)


def test_attempt_and_distinct_ceiling_refuse_before_transport(monkeypatch, tmp_path):
    journal = pilot._Journal(tmp_path.resolve())
    monkeypatch.setattr(pilot, "_fetch_sec", lambda *args: pytest.fail("transport reached"))
    try:
        journal.count = 144
        with pytest.raises(pilot.SecPilotError, match="144-attempt ceiling"):
            journal.fetch("/Archives/edgar/data/123456/000099999922000001/index.json", "synthetic")
        assert journal.count == 144
        journal.count = 0
        journal.distinct.clear()
        journal.distinct.update(f"synthetic-{index}" for index in range(48))
        with pytest.raises(pilot.SecPilotError, match="48-distinct-artifact ceiling"):
            journal.fetch("/Archives/edgar/data/123456/000099999922000001/index.json", "synthetic")
        assert len(journal.distinct) == 48
    finally:
        journal.close()


def test_same_path_retry_budget_cannot_reset_between_fetch_calls(monkeypatch, tmp_path):
    journal = pilot._Journal(tmp_path.resolve())
    monkeypatch.setattr(pilot, 'MIN_REQUEST_INTERVAL_SECONDS', 0)
    monkeypatch.setattr(pilot.time, 'sleep', lambda _: None)
    called = []

    def unavailable(path, user_agent):
        called.append(path)
        raise OSError('synthetic persistent failure')

    monkeypatch.setattr(pilot, '_fetch_sec', unavailable)
    path = '/Archives/edgar/data/123456/000099999922000001/index.json'
    try:
        with pytest.raises(pilot.SecPilotError):
            journal.fetch(path, 'synthetic')
        with pytest.raises(pilot.SecPilotError):
            journal.fetch(path, 'synthetic')
        assert len(called) == journal.count == 3
        assert journal.distinct == {path}
    finally:
        journal.close()


def test_limiter_spaces_request_starts_including_retry_and_seeded_continuation(monkeypatch, tmp_path):
    journal = pilot._Journal(tmp_path.resolve())
    replay = pilot._FirstPassReplay((), 'a' * 64, 'b' * 64, 'c' * 64,
                                    frozenset(f'prior-{n}' for n in range(32)))
    journal.seed_verified_first_pass(replay)
    clock = [100.0]
    starts = []
    monkeypatch.setattr(pilot.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(pilot.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    paths = [f'/Archives/edgar/data/123456/000099999922000001/file{n}.xml' for n in range(2)]

    def fetch(path, user_agent):
        starts.append(clock[0])
        return (503, b'') if len(starts) == 1 else (200, b'abc')

    monkeypatch.setattr(pilot, '_fetch_sec', fetch)
    try:
        assert journal.fetch(paths[0], 'synthetic') == (200, b'abc')
        assert journal.fetch(paths[1], 'synthetic') == (200, b'abc')
        assert journal.count == 35
        with pytest.raises(pilot.SecPilotError, match='rerequest'):
            journal.fetch('prior-0', 'synthetic')
        assert len(starts) == 3
        assert all(later - earlier >= 0.5 for earlier, later in zip(starts, starts[1:]))
    finally:
        journal.close()


def test_attempt_journal_creation_fsyncs_directory_before_request(monkeypatch, tmp_path):
    synced_modes = []
    original = os.fsync

    def fsync(fd):
        synced_modes.append(os.fstat(fd).st_mode)
        return original(fd)

    monkeypatch.setattr(pilot.os, 'fsync', fsync)
    journal = pilot._Journal(tmp_path.resolve())
    try:
        assert any(__import__('stat').S_ISDIR(mode) for mode in synced_modes)
    finally:
        journal.close()


def test_replaced_output_root_prevents_next_network_attempt(monkeypatch, tmp_path):
    output = tmp_path / 'output'
    output.mkdir()
    journal = pilot._Journal(output)
    moved = tmp_path / 'moved'
    output.rename(moved)
    output.mkdir()
    monkeypatch.setattr(pilot, '_fetch_sec', lambda *args: pytest.fail('network reached after root replacement'))
    try:
        with pytest.raises((pilot.SecPilotError, OSError), match='root|directory|changed'):
            journal.fetch('/Archives/edgar/data/123456/000099999922000001/index.json', 'synthetic')
    finally:
        journal.close()


def test_report_and_commit_final_names_not_visible_before_fsync(monkeypatch, tmp_path):
    output = tmp_path.resolve()
    monkeypatch.setattr(pilot.os, 'fsync', lambda fd: (_ for _ in ()).throw(OSError('synthetic fsync failure')))
    with pytest.raises(OSError, match='synthetic fsync failure'):
        pilot._write_commit_last(output, {'kind': 'synthetic-only'})
    assert not list(output.glob('sec-pilot-report-*.json'))
    assert not (output / 'commit.json').exists()


def test_immutable_object_name_is_not_published_before_successful_fsync(monkeypatch, tmp_path):
    output = tmp_path.resolve()
    (output / "objects").mkdir()
    raw = b"synthetic raw object"
    name = output / "objects" / f"{hash_bytes(raw)}.bin"

    def failed_fsync(fd):
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(pilot.os, "fsync", failed_fsync)
    with pytest.raises(OSError, match="synthetic fsync failure"):
        pilot._store_object(output, raw)
    assert not name.exists()


def test_output_overlap_refuses_case_variant_alias_on_default_mac_volume(tmp_path):
    root = tmp_path.resolve()
    source = root / 'SyntheticSource'
    prior = root / 'SyntheticPrior'
    source.mkdir()
    prior.mkdir()
    alias = root / 'syntheticsource'
    if not alias.exists() or not os.path.samefile(source, alias):
        pytest.skip('test volume is case-sensitive; no case-variant alias exists')
    output = alias / 'new-output'
    with pytest.raises(pilot.SecPilotError, match='overlap'):
        pilot._safe_roots(source, prior, output)
    assert not output.exists()


@pytest.mark.parametrize("raw, expected", [
    ("07-NOV-2022", "2022-11-07"),
    ("13-MAR-2023", "2023-03-13"),
])
def test_source_date_dialect_is_explicit(raw, expected):
    assert pilot._filing_date(raw) == expected


@pytest.mark.parametrize("raw", [
    "2022-11-07", "7-NOV-2022", "07-Nov-2022", "31-FEB-2023",
    "07-XYZ-2022", "07-NOV-2022\n", True,
])
def test_unapproved_source_date_refused(raw):
    with pytest.raises(pilot.SecPilotError):
        pilot._filing_date(raw)


@pytest.mark.parametrize("index", [
    b'{"directory":{"item":[{"name":"a.xml"},{"name":"b.xml"}]}}',
    b'{"directory":{"item":[{"name":"xslF345X05.xml"}]}}',
    b'{"directory":{"item":[{"name":"../ownership.xml"}]}}',
    b'{"directory":{"item":[{"name":"https://evil.invalid/o.xml"}]}}',
    b'{"directory":{"item":[{"name":"ownership.XML"}]}}',
    b'{"directory":{"item":[{"name":"ownership.xml"}]},"directory":{}}',
    b'{"directory":{"item":[{"name":"ownership.xml"},{"name":"ownership.xml"}]}}',
    b'not json',
])
def test_index_refuses_ambiguous_or_unsafe_primary_xml(index):
    with pytest.raises(pilot.SecPilotError):
        pilot._primary_filename(index)


def test_index_accepts_only_one_root_xml_item():
    assert pilot._primary_filename(INDEX) == "ownership.xml"


@pytest.mark.parametrize("raw", [
    b'<ownershipDocument><documentType>4</documentType><documentType>4/A</documentType><issuer><issuerCik>123456</issuerCik></issuer></ownershipDocument>',
    b'<ownershipDocument><documentType>4</documentType><issuer><issuerCik>123456</issuerCik><issuerCik>999999</issuerCik></issuer></ownershipDocument>',
    b'<ownershipDocument><documentType>4</documentType><issuer><issuerCik>1234567890123456789012345678901234567890</issuerCik></issuer></ownershipDocument>',
    b'<!DOCTYPE ownershipDocument [<!ENTITY x "4">]><ownershipDocument><documentType>&x;</documentType></ownershipDocument>',
])
def test_xml_refuses_conflicting_or_unbounded_identity(raw):
    with pytest.raises(pilot.SecPilotError):
        pilot._validate_xml(raw, _candidates()[0])


def test_xml_refuses_utf16_entity_expansion_hidden_from_ascii_scan():
    hostile = (
        '<?xml version="1.0" encoding="utf-16"?>'
        '<!DOCTYPE ownershipDocument [<!ENTITY injected "4">]>'
        '<ownershipDocument><documentType>&injected;</documentType>'
        '<issuer><issuerCik>123456</issuerCik></issuer></ownershipDocument>'
    ).encode('utf-16')
    with pytest.raises(pilot.SecPilotError, match='UTF-8|DTD|encoding'):
        pilot._validate_xml(hostile, _candidates()[0])


@pytest.mark.parametrize("headers, body", [
    ([('Content-Length', str(2 * 1024 * 1024 + 1))], b''),
    ([('Content-Length', '3'), ('content-length', '3')], b'abc'),
    ([('Content-Length', '5')], b'abc'),
    ([('Content-Encoding', 'gzip')], b'abc'),
    ([('Transfer-Encoding', 'chunked')], b'abc'),
    ([], b'abc'),
])
def test_transport_refuses_oversize_duplicate_truncated_or_compressed_body(monkeypatch, headers, body):
    calls = []

    class Response:
        status = 200

        def getheaders(self):
            return headers

        def read(self, limit):
            calls.append(('read', limit))
            return body[:limit]

    class Connection:
        def __init__(self, host, timeout):
            assert host == 'www.sec.gov'
            assert timeout <= 15
            calls.append(('connect', host))

        def request(self, method, path, headers):
            assert method == 'GET'
            assert headers['User-Agent'] == 'synthetic-agent'
            assert headers['Accept-Encoding'] == 'identity'
            calls.append(('request', path))

        def getresponse(self):
            return Response()

        def close(self):
            calls.append(('close',))

    monkeypatch.setattr(pilot.http.client, 'HTTPSConnection', Connection)
    with pytest.raises(pilot.SecPilotError):
        pilot._fetch_sec('/Archives/edgar/data/123456/000099999922000001/index.json', 'synthetic-agent')
    assert [call for call in calls if call[0] == 'request'] == [
        ('request', '/Archives/edgar/data/123456/000099999922000001/index.json')
    ]
    assert all(call[1] <= pilot.MAX_BODY_BYTES for call in calls if call[0] == 'read')
    assert calls[-1] == ('close',)


def test_transport_reads_exact_declared_body_size_not_cap_plus_one(monkeypatch):
    reads = []

    class Response:
        status = 200

        def getheaders(self):
            return [('Content-Length', '3')]

        def read(self, limit):
            reads.append(limit)
            return b'abc'

    class Connection:
        def __init__(self, host, timeout):
            assert host == 'www.sec.gov'

        def request(self, method, path, headers):
            assert method == 'GET'
            assert headers['User-Agent'] == 'synthetic-agent'

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(pilot.http.client, 'HTTPSConnection', Connection)
    status, body = pilot._fetch_sec(
        '/Archives/edgar/data/123456/000099999922000001/index.json',
        'synthetic-agent',
    )
    assert (status, body) == (200, b'abc')
    assert reads == [3]


@pytest.mark.parametrize("path", [
    'https://evil.invalid/Archives/edgar/data/123456/000099999922000001/index.json',
    '/Archives/edgar/data/123456/000099999922000001/../other',
    '/Archives/edgar/data/123456/000099999922000001/ownership.xml?x=1',
    '/Archives/edgar/data/123456/000099999922000001/%2e%2e.xml',
    '/Archives/edgar/data/123456/000099999922000001/xsl/owner.xml',
])
def test_transport_path_cannot_escape_exact_sec_host_or_accession_directory(monkeypatch, path):
    monkeypatch.setattr(pilot.http.client, 'HTTPSConnection', lambda *args, **kwargs: pytest.fail('network object reached'))
    with pytest.raises(pilot.SecPilotError):
        pilot._fetch_sec(path, 'synthetic-agent')


def test_contact_and_capture_validation_precede_any_source_io(monkeypatch, synthetic_run):
    monkeypatch.setattr(pilot, 'select_fixed_pilot', lambda *args: pytest.fail('source I/O reached'))
    source, prior, output, _ = synthetic_run
    with pytest.raises(pilot.SecPilotError, match='identifying contact'):
        pilot.run_fixed_sec_pilot(source, prior, output, contact_email='bad\nHeader: injected', capture_git_commit=COMMIT)
    with pytest.raises(pilot.SecPilotError, match='capture commit'):
        pilot.run_fixed_sec_pilot(source, prior, output, contact_email=CONTACT, capture_git_commit='C' * 40)
    assert not output.exists()


def test_runner_is_outside_provider_free_core_and_has_no_ib1c_promotion_import():
    path = Path(pilot.__file__).resolve()
    assert path.name == 'insider_buying_sec_acquisition.py'
    assert path.parent.name == 'research'
    source = path.read_text()
    assert 'write_sec_edgar_acceptance_snapshot' not in source
    assert 'write_sec_noncanonical_pilot' not in source
    assert 'run_ib1c' not in source


# Isolating pins: each input is otherwise valid, so only the named guard can
# refuse it. Several earlier cases were refused first by a different check.


def _valid_xml(candidate, *, root="ownershipDocument", form=None, issuer="0000123456", prefix=""):
    return (
        prefix + f"<{root}>"
        f"<documentType>{form or candidate.form_type}</documentType>"
        f"<issuer><issuerCik>{issuer}</issuerCik></issuer>"
        f"</{root}>"
    ).encode("utf-8")


def test_xml_utf8_internal_entity_with_complete_identity_is_refused_as_dtd():
    candidate = _candidates()[0]
    hostile = (
        '<!DOCTYPE ownershipDocument [<!ENTITY f "4">]>'
        "<ownershipDocument><documentType>&f;</documentType>"
        "<issuer><issuerCik>0000123456</issuerCik></issuer></ownershipDocument>"
    ).encode("utf-8")
    with pytest.raises(pilot.SecPilotError, match="DTD or entity"):
        pilot._validate_xml(hostile, candidate)


def test_xml_with_utf8_bom_is_refused():
    candidate = _candidates()[0]
    with pytest.raises(pilot.SecPilotError, match="without BOM"):
        pilot._validate_xml(b"\xef\xbb\xbf" + _valid_xml(candidate), candidate)


def test_xml_declaring_a_foreign_encoding_is_a_named_refusal():
    candidate = _candidates()[0]
    raw = _valid_xml(candidate, prefix='<?xml version="1.0" encoding="UTF-16"?>')
    with pytest.raises(pilot.SecPilotError, match="foreign declaration"):
        pilot._validate_xml(raw, candidate)


def test_xml_with_another_root_element_is_refused():
    candidate = _candidates()[0]
    with pytest.raises(pilot.SecPilotError, match="not a Form 4 ownership document"):
        pilot._validate_xml(_valid_xml(candidate, root="otherDocument"), candidate)


@pytest.mark.parametrize("change", ["form", "issuer"])
def test_xml_for_another_form_or_issuer_is_refused(change):
    candidate = _candidates()[0]
    raw = (_valid_xml(candidate, form="4/A") if change == "form"
           else _valid_xml(candidate, issuer="0000777777"))
    with pytest.raises(pilot.SecPilotError, match="disagrees with approved source"):
        pilot._validate_xml(raw, candidate)


def _transport_refusal(monkeypatch, headers, body):
    class Response:
        status = 200

        def getheaders(self):
            return headers

        def read(self, limit):
            return body[:limit]

    class Connection:
        def __init__(self, host, timeout):
            pass

        def request(self, method, path, headers):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(pilot.http.client, "HTTPSConnection", Connection)
    return lambda: pilot._fetch_sec("/Archives/edgar/data/123456/000099999922000001/index.json", "agent")


def test_transport_refuses_compression_even_with_one_bounded_length(monkeypatch):
    fetch = _transport_refusal(monkeypatch, [("Content-Length", "3"), ("Content-Encoding", "gzip")], b"abc")
    with pytest.raises(pilot.SecPilotGlobalStop, match="unsupported compression"):
        fetch()


def test_transport_refuses_chunking_even_with_one_bounded_length(monkeypatch):
    fetch = _transport_refusal(monkeypatch, [("Content-Length", "3"), ("Transfer-Encoding", "chunked")], b"abc")
    with pytest.raises(pilot.SecPilotGlobalStop, match="unbounded transfer encoding"):
        fetch()


def test_index_item_repeating_a_key_is_refused_not_resolved_last_wins():
    index = b'{"directory":{"item":[{"name":"ownership.xml","name":"other.xml"}]}}'
    with pytest.raises(pilot.SecPilotError, match="repeats a JSON key"):
        pilot._primary_filename(index)


def test_index_item_list_above_512_entries_is_refused():
    items = [{"name": "ownership.xml"}] + [{"name": f"f{i}.txt"} for i in range(512)]
    with pytest.raises(pilot.SecPilotError, match="bounded item list"):
        pilot._primary_filename(json.dumps({"directory": {"item": items}}).encode())


def _tag_target(candidate):
    return pilot.SecAcquisitionTarget(
        period=candidate.period, accession_number=candidate.accession_number,
        form_type=candidate.form_type, filing_date=candidate.filing_date,
        issuer_cik=candidate.issuer_cik, quarterly_zip_sha256=candidate.quarterly_zip_sha256,
        submission_row_id=candidate.submission_row_id, primary_xml_filename="ownership.xml",
    )


@pytest.mark.parametrize(("old", "new", "match"), [
    # Envelope names another accession; the ACCESSION-NUMBER field is right.
    (b".hdr.sgml : ", b"X.hdr.sgml : ", "envelope disagrees"),
    # ACCESSION-NUMBER field names another accession; the envelope is right.
    (b"<ACCESSION-NUMBER>0000999999-22-000001", b"<ACCESSION-NUMBER>0000999999-22-000009", "identity disagrees"),
    # A foreign preamble field.
    (b"<TYPE>", b"<FOREIGN-FIELD>x\n<TYPE>", "nested or foreign fields"),
    # ISSUER placed before REPORTING-OWNER; each role still appears once.
    (b"<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>0000999999\n</OWNER-DATA>\n</REPORTING-OWNER>\n<ISSUER>\n<COMPANY-DATA>\n<CIK>0000123456\n</COMPANY-DATA>\n</ISSUER>\n",
     b"<ISSUER>\n<COMPANY-DATA>\n<CIK>0000123456\n</COMPANY-DATA>\n</ISSUER>\n<REPORTING-OWNER>\n<OWNER-DATA>\n<CIK>0000999999\n</OWNER-DATA>\n</REPORTING-OWNER>\n",
     "role topology"),
    # A subsection before COMPANY-DATA inside ISSUER.
    (b"<ISSUER>\n<COMPANY-DATA>", b"<ISSUER>\n<BUSINESS-ADDRESS>\n<CITY>X\n</BUSINESS-ADDRESS>\n<COMPANY-DATA>", "missing or not first"),
    # A second CIK inside ISSUER but outside COMPANY-DATA.
    (b"</COMPANY-DATA>\n</ISSUER>", b"</COMPANY-DATA>\n<FORMER-COMPANY>\n<CIK>0000123456\n</FORMER-COMPANY>\n</ISSUER>", "ambiguous outside COMPANY-DATA"),
])
def test_tag_header_isolated_refusals(old, new, match):
    candidate = _candidates()[0]
    raw = _tag_header(candidate)
    assert old in raw
    with pytest.raises(pilot.SecPilotError, match=match):
        pilot._validate_tag_header(raw.replace(old, new, 1), _tag_target(candidate))


def _continue(inputs, output, **overrides):
    source, prior, first, _ = inputs
    values = dict(contact_email=CONTACT, prior_code_commit=pilot.FIRST_PASS_CODE_COMMIT,
                  continuation_code_commit=COMMIT)
    values.update(overrides)
    return pilot.run_fixed_sec_xml_continuation(source, prior, first, output, **values)


def test_continuation_is_not_available_when_any_xml_is_refused(monkeypatch, synthetic_first_pass):
    inputs, _ = synthetic_first_pass
    candidates = inputs[3]

    def one_bad(path, user_agent):
        candidate = next(item for item in candidates if path.startswith(item.archive_path))
        if candidate is candidates[5]:
            return 200, _valid_xml(candidate, issuer="0000777777")
        return 200, _xml(candidate)

    monkeypatch.setattr(pilot, "_fetch_sec", one_bad)
    monkeypatch.setattr(pilot, "_verify_continuation_code_commit", lambda _: None)
    payload = json.loads(_continue(inputs, inputs[2].parent / "one-bad").read_bytes())
    assert sum(row["status"] == "acquired_noncanonical" for row in payload["rows"]) == 15
    assert payload["acquisition_available"] is False


def test_continuation_stops_all_requests_after_a_global_stop(monkeypatch, synthetic_first_pass):
    inputs, _ = synthetic_first_pass
    calls = []

    def denied(path, user_agent):
        calls.append(path)
        return 403, b""

    monkeypatch.setattr(pilot, "_fetch_sec", denied)
    monkeypatch.setattr(pilot, "_verify_continuation_code_commit", lambda _: None)
    payload = json.loads(_continue(inputs, inputs[2].parent / "denied").read_bytes())
    assert len(calls) == 1
    assert payload["halted_on_sec_access"] is True
    assert sum(row["reason"] == "not attempted after SEC access stop" for row in payload["rows"]) == 15


def test_continuation_refuses_an_xml_path_that_drifts_from_the_frozen_index(monkeypatch, synthetic_first_pass):
    # Drift is injected after a clean replay: the target's XML URL no longer
    # matches the candidate's archive directory plus the index-named file.
    import dataclasses
    from types import SimpleNamespace

    inputs, _ = synthetic_first_pass
    monkeypatch.setattr(pilot, "_verify_continuation_code_commit", lambda _: None)
    monkeypatch.setattr(pilot, "_fetch_sec", lambda *args: pytest.fail("network after path drift"))
    original_replay = pilot.replay_first_sec_pass

    def drifted_replay(*args, **kwargs):
        replay = original_replay(*args, **kwargs)
        sources = tuple(
            dataclasses.replace(item, target=SimpleNamespace(
                primary_xml_filename=item.target.primary_xml_filename,
                primary_xml_url=item.target.primary_xml_url.replace("/123456/", "/999999/"),
            ))
            for item in replay.sources
        )
        return dataclasses.replace(replay, sources=sources)

    monkeypatch.setattr(pilot, "replay_first_sec_pass", drifted_replay)
    with pytest.raises(pilot.SecPilotError, match="drifted from frozen index"):
        _continue(inputs, inputs[2].parent / "drift")


@pytest.mark.parametrize("site", ["continuation", "replay"])
def test_first_pass_code_attestation_must_be_the_exact_operator_value(monkeypatch, synthetic_first_pass, site):
    inputs, _ = synthetic_first_pass
    monkeypatch.setattr(pilot, "_fetch_sec", lambda *args: pytest.fail("network before attestation"))
    monkeypatch.setattr(pilot, "_verify_continuation_code_commit", lambda _: None)
    wrong = "e" * 40
    with pytest.raises(pilot.SecPilotError, match="attestation"):
        if site == "continuation":
            _continue(inputs, inputs[2].parent / "wrong-attestation", prior_code_commit=wrong)
        else:
            pilot.replay_first_sec_pass(inputs[2], inputs[3], prior_code_commit=wrong)


def test_continuation_git_binding_refuses_head_other_than_the_declared_commit(monkeypatch):
    root = Path(pilot.__file__).resolve().parents[1]
    source = Path(pilot.__file__).read_bytes()

    def git_output(command, **kwargs):
        if command == ("git", "rev-parse", "--show-toplevel"):
            return (str(root) + "\n").encode()
        if command == ("git", "branch", "--show-current"):
            return b"codex/strategy-insider-buying\n"
        if command == ("git", "rev-parse", "HEAD"):
            return ("f" * 40 + "\n").encode()
        if command == ("git", "status", "--porcelain=v1", "--untracked-files=all"):
            return b""
        if command == ("git", "show", f"{COMMIT}:research/insider_buying_sec_acquisition.py"):
            return source
        pytest.fail(f"unexpected git command {command}")

    monkeypatch.setattr(pilot.subprocess, "check_output", git_output)
    with pytest.raises(pilot.SecPilotError, match="clean committed lane source"):
        pilot._verify_continuation_code_commit(COMMIT)


def test_lane_package_stays_network_free_through_indirect_imports():
    # The package guard checks direct imports only. This runner lives outside
    # the package and imports http.client, so a lane module importing it would
    # pull networking in without tripping that guard. Import every lane module
    # in a fresh interpreter and require that no networking module loads.
    import subprocess
    import sys

    repository = Path(__file__).resolve().parents[1]
    imports = (
        "import importlib, pkgutil, sys\n"
        "import research.insider_buying as p\n"
        "for m in pkgutil.iter_modules(p.__path__):\n"
        "    importlib.import_module('research.insider_buying.' + m.name)\n"
    )
    scan = (
        "blocked = ('http.client', 'http.server', 'socket', 'socketserver', 'ssl', "
        "'urllib.request', 'urllib3', 'requests', 'httpx', 'aiohttp', 'ftplib', "
        "'smtplib', 'subprocess', 'research.insider_buying_sec_acquisition')\n"
        "bad = sorted(n for n in sys.modules if any("
        "n == root or n.startswith(root + '.') for root in blocked))\n"
        "print(','.join(bad))\n"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", imports + "import urllib.parse\n" + scan],
        cwd=repository, capture_output=True, text=True, check=True, timeout=60,
    )
    assert result.stdout.strip() == ""
    # The harmless parser is allowed, while actual network-capable imports
    # remain visible to this scan on every supported Python version.
    result = subprocess.run(
        [sys.executable, "-B", "-c", imports + "import urllib.request\n" + scan],
        cwd=repository, capture_output=True, text=True, check=True, timeout=60,
    )
    assert "urllib.request" in result.stdout.strip().split(",")
    result = subprocess.run(
        [sys.executable, "-B", "-c", imports + "import research.insider_buying_sec_acquisition\n" + scan],
        cwd=repository, capture_output=True, text=True, check=True, timeout=60,
    )
    assert "research.insider_buying_sec_acquisition" in result.stdout.strip().split(",")
    assert "http.client" in result.stdout.strip().split(",")
