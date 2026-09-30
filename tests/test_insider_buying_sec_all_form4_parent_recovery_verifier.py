"""Read-only v3 replay tests use invented parents and injected transport only."""
from __future__ import annotations

import fcntl
import json
import os

import pytest

from research.insider_buying_sec_complete_acquisition import SecHttpResult
from data.hashing import canonical_json, hash_bytes
import research.insider_buying_sec_all_form4_parent_recovery_executor as executor
import research.insider_buying_sec_all_form4_parent_recovery_verifier as verifier
from test_insider_buying_sec_all_form4_parent_recovery_union import (
    _body, _stopped_source,
)


@pytest.fixture
def source(tmp_path, monkeypatch):
    return _stopped_source(tmp_path, monkeypatch)


def _run(source, output, transport):
    plan, prior, diagnostic, selected, expectation, report_sha, _ = source
    return executor.run_synthetic_recovery_continuation(
        plan, prior, diagnostic, selected, output,
        prior_expectation=expectation,
        diagnostic_capture_git_commit="e" * 40,
        expected_diagnostic_report_sha256=report_sha,
        diagnostic_mode="originally_accepted",
        capture_git_commit="f" * 40,
        transport=transport, contact_email="invented@example.test",
    )


def _verify(source, output):
    plan, prior, diagnostic, selected, expectation, report_sha, _ = source
    return verifier.verify_completed_synthetic_recovery_v3(
        plan, prior, diagnostic, selected, output,
        prior_expectation=expectation,
        diagnostic_capture_git_commit="e" * 40,
        expected_diagnostic_report_sha256=report_sha,
        diagnostic_mode="originally_accepted",
        capture_git_commit="f" * 40,
    )


def _success(source):
    request = source[0].requests[-1]
    raw = _body(request)

    def transport(url, _headers, _cap):
        assert url == request.url
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)

    return transport


def test_independent_v3_replay_accepts_complete_invented_union(source, tmp_path):
    output = tmp_path / "v3"
    _run(source, output, _success(source))
    receipt = _verify(source, output)
    assert receipt["total_parents"] == 7
    assert receipt["prior_completed_count"] == 4
    assert receipt["accepted_diagnostic_count"] == 1
    assert receipt["remaining_selected_reuse_count"] == 1
    assert receipt["later_acquired_count"] == 1
    assert receipt["new_attempt_count"] == 1
    assert receipt["shard_count"] == 3
    assert receipt["complete_parent_bytes_acquired"] is True
    assert receipt["source_authenticated"] is False
    assert receipt["point_in_time_data"] is False
    assert receipt["research_looks"] == receipt["qc_jobs"] == 0


def test_independent_v3_replay_accepts_only_durable_503_then_200(source, tmp_path):
    output = tmp_path / "retried"
    calls = [0]
    good = _success(source)

    def transport(url, headers, cap):
        calls[0] += 1
        if calls[0] == 1:
            return SecHttpResult(503, (), b"")
        return good(url, headers, cap)

    _run(source, output, transport)
    assert _verify(source, output)["new_attempt_count"] == 2
    assert calls[0] == 2


def test_independent_v3_replay_refuses_durable_unresolved_start(source, tmp_path):
    output = tmp_path / "pending"

    def interrupted(_url, _headers, _cap):
        raise OSError("invented ambiguous stop")

    with pytest.raises(executor.RecoveryExecutorError, match="ambiguous"):
        _run(source, output, interrupted)
    with pytest.raises(verifier.RecoveryVerificationError, match="REFUSED"):
        _verify(source, output)


def test_independent_v3_replay_refuses_missing_new_object(source, tmp_path):
    output = tmp_path / "missing-object"
    _run(source, output, _success(source))
    object_path = next((output / "shard-0002" / "objects").glob("*.bin"))
    object_path.unlink()
    with pytest.raises(verifier.RecoveryVerificationError, match="REFUSED"):
        _verify(source, output)


def test_independent_v3_replay_refuses_extra_private_member(source, tmp_path):
    output = tmp_path / "extra-member"
    _run(source, output, _success(source))
    extra = output / "shard-0001" / "orphan.tmp"
    extra.write_bytes(b"invented")
    extra.chmod(0o600)
    with pytest.raises(verifier.RecoveryVerificationError, match="extra or missing"):
        _verify(source, output)


def test_independent_v3_replay_refuses_public_object_directory(source, tmp_path):
    output = tmp_path / "public-objects"
    _run(source, output, _success(source))
    objects = output / "shard-0002" / "objects"
    objects.chmod(0o755)
    with pytest.raises(verifier.RecoveryVerificationError, match="private"):
        _verify(source, output)


def test_independent_v3_replay_refuses_source_drift(source, tmp_path):
    output = tmp_path / "source-drift"
    _run(source, output, _success(source))
    selected_object = next((source[3] / "objects").glob("*.bin"))
    selected_object.write_bytes(b"changed after complete v3 commit")
    with pytest.raises(ValueError, match="REFUSED"):
        _verify(source, output)


def test_independent_v3_replay_refuses_non200_terminal_root(source, tmp_path):
    output = tmp_path / "http-refusal"
    with pytest.raises(executor.RecoveryExecutorError, match="incomplete"):
        _run(source, output, lambda *_: SecHttpResult(403, (), b""))
    with pytest.raises(verifier.RecoveryVerificationError, match="REFUSED"):
        _verify(source, output)


def test_independent_v3_replay_refuses_invalid_200_terminal_root(source, tmp_path):
    output = tmp_path / "bad-200"
    raw = _body(source[0].requests[-1], wrong=True)
    with pytest.raises(executor.RecoveryExecutorError, match="incomplete"):
        _run(source, output, lambda *_: SecHttpResult(
            200, (("Content-Length", str(len(raw))),), raw,
        ))
    with pytest.raises(verifier.RecoveryVerificationError, match="REFUSED"):
        _verify(source, output)


def test_independent_v3_replay_refuses_root_moved_inside_source(source, tmp_path):
    output = tmp_path / "v3-original"
    _run(source, output, _success(source))
    copied_location = source[3] / "moved-v3-root"
    output.rename(copied_location)
    with pytest.raises(verifier.RecoveryVerificationError, match="REFUSED"):
        _verify(source, copied_location)


def test_independent_v3_replay_refuses_active_exclusive_writer(source, tmp_path):
    output = tmp_path / "v3-locked"
    _run(source, output, _success(source))
    lock_fd = os.open(output / "run.lock", os.O_RDONLY)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(verifier.RecoveryVerificationError, match="REFUSED"):
            _verify(source, output)
    finally:
        os.close(lock_fd)


def _rewrite_private(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


def _rehashed_event_clock(output, *, reversal=False):
    """Keep every dependent digest valid so only the clock grammar can refuse."""
    shard = output / "shard-0002"
    old_events = sorted(shard.glob("event-*.json"))
    assert len(old_events) == 3
    chain = hash_bytes((shard / "inventory.json").read_bytes())
    event_raw = []
    for index, old in enumerate(old_events, 1):
        event = json.loads(old.read_bytes())
        if index == 1 and not reversal:
            event["started_utc"] = "2023-01-03T10:11:12+00:00"
        elif index == 2 and reversal:
            event["finished_utc"] = "2000-01-01T00:00:00.000000+00:00"
        event["prev_sha256"] = chain
        raw = (canonical_json(event) + "\n").encode()
        chain = hash_bytes(raw)
        old.unlink()
        _rewrite_private(shard / f"event-{index:06d}-{chain}.json", raw)
        event_raw.append(raw)
    journal = b"".join(event_raw)
    _rewrite_private(shard / "attempts.jsonl", journal)
    old_report = next(shard.glob("shard-report-*.json"))
    report = json.loads(old_report.read_bytes())
    report["attempt_journal_sha256"] = hash_bytes(journal)
    report_raw = (canonical_json(report) + "\n").encode()
    report_sha = hash_bytes(report_raw)
    old_report.unlink()
    _rewrite_private(shard / f"shard-report-{report_sha}.json", report_raw)
    shard_commit = json.loads((shard / "commit.json").read_bytes())
    shard_commit["report_name"] = f"shard-report-{report_sha}.json"
    shard_commit["report_sha256"] = report_sha
    shard_commit["attempt_journal_sha256"] = hash_bytes(journal)
    _rewrite_private(
        shard / "commit.json", (canonical_json(shard_commit) + "\n").encode(),
    )
    old_top = next(output.glob("campaign-report-*.json"))
    top = json.loads(old_top.read_bytes())
    top["shards"][2]["report_sha256"] = report_sha
    top_raw = (canonical_json(top) + "\n").encode()
    top_sha = hash_bytes(top_raw)
    old_top.unlink()
    _rewrite_private(output / f"campaign-report-{top_sha}.json", top_raw)
    top_commit = json.loads((output / "commit.json").read_bytes())
    top_commit["report_name"] = f"campaign-report-{top_sha}.json"
    top_commit["report_sha256"] = top_sha
    _rewrite_private(
        output / "commit.json", (canonical_json(top_commit) + "\n").encode(),
    )


def test_independent_v3_replay_refuses_rehashed_noncanonical_event_clock(
    source, tmp_path,
):
    output = tmp_path / "noncanonical-clock"
    _run(source, output, _success(source))
    _rehashed_event_clock(output)
    with pytest.raises(verifier.RecoveryVerificationError, match="timestamp"):
        _verify(source, output)


def test_independent_v3_replay_refuses_rehashed_finish_before_start(
    source, tmp_path,
):
    output = tmp_path / "reversed-clock"
    _run(source, output, _success(source))
    _rehashed_event_clock(output, reversal=True)
    with pytest.raises(verifier.RecoveryVerificationError, match="before its durable start"):
        _verify(source, output)
