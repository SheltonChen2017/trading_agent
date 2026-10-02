"""Offline invented-source tests for a read-only, stopped-v3 binding."""
from __future__ import annotations

import fcntl
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.insider_buying_sec_complete_acquisition import SecHttpResult
import research.insider_buying_sec_all_form4_parent_recovery_executor as executor
import research.insider_buying_sec_all_form4_parent_recovery_verifier as completed_verifier
import research.insider_buying_sec_all_form4_parent_recovery_partial_verifier as partial_verifier
from test_insider_buying_sec_all_form4_parent_recovery_union import _body, _stopped_source


def _stopped_v3(tmp_path, monkeypatch):
    source = _stopped_source(tmp_path, monkeypatch, request_count=10)
    plan, prior, diagnostic, selected, expectation, report_sha, _ = source
    output = tmp_path / "stopped-v3"
    seen = []

    def transport(url, _headers, _cap):
        seen.append(url)
        if len(seen) == 3:
            raise OSError("invented ambiguous transport stop")
        request = next(item for item in plan.requests if item.url == url)
        body = _body(request)
        return SecHttpResult(200, (("Content-Length", str(len(body))),), body)

    with pytest.raises(executor.RecoveryExecutorError, match="ambiguous"):
        executor.run_synthetic_recovery_continuation(
            plan, prior, diagnostic, selected, output,
            prior_expectation=expectation,
            diagnostic_capture_git_commit="e" * 40,
            expected_diagnostic_report_sha256=report_sha,
            diagnostic_mode="originally_accepted",
            capture_git_commit="f" * 40,
            transport=transport,
            contact_email="invented@example.test",
        )
    assert len(seen) == 3
    return source, output, seen


def _verify(source, output):
    plan, prior, diagnostic, selected, expectation, report_sha, _ = source
    return partial_verifier.verify_partial_synthetic_recovery_v3(
        plan, prior, diagnostic, selected, output,
        prior_expectation=expectation,
        diagnostic_capture_git_commit="e" * 40,
        expected_diagnostic_report_sha256=report_sha,
        diagnostic_mode="originally_accepted",
        capture_git_commit="f" * 40,
    )


def _all_files(root):
    return {str(path.relative_to(root)): hash_bytes(path.read_bytes())
            for path in root.rglob("*") if path.is_file()}


def test_partial_v3_replays_exact_completed_prefix_and_one_pending_start_read_only(
    tmp_path, monkeypatch,
):
    source, output, seen = _stopped_v3(tmp_path, monkeypatch)
    before = _all_files(output)
    receipt = _verify(source, output)
    assert _all_files(output) == before
    assert receipt.pending_request is source[0].requests[8]
    assert receipt.pending_request_sha256 == hash_payload(
        source[0].requests[8].to_payload(),
    )
    assert receipt.pending_global_index == 8
    assert receipt.pending_attempt_number == 1
    assert receipt.pending_shard_name == "shard-0002"
    assert receipt.v3_root == output
    assert receipt.capture_git_commit == "f" * 40
    assert receipt.completed_new_count == 2
    assert receipt.attempt_count == 3
    assert receipt.root_plan_sha256 == hash_bytes((output / "plan.json").read_bytes())
    inventory = output / "shard-0002" / "inventory.json"
    assert receipt.pending_shard_inventory_sha256 == hash_bytes(inventory.read_bytes())
    event_paths = sorted((output / "shard-0002").glob("event-*.json"))
    assert receipt.pending_attempt_start_sha256 == hash_bytes(event_paths[-1].read_bytes())
    assert receipt.pending_shard_journal_sha256 == hash_bytes(
        b"".join(path.read_bytes() for path in event_paths),
    )
    assert len(seen) == 3
    assert source[0].requests[8].accession_number not in repr(receipt)
    with pytest.raises(completed_verifier.RecoveryVerificationError, match="REFUSED"):
        completed_verifier.verify_completed_synthetic_recovery_v3(
            source[0], source[1], source[2], source[3], output,
            prior_expectation=source[4],
            diagnostic_capture_git_commit="e" * 40,
            expected_diagnostic_report_sha256=source[5],
            diagnostic_mode="originally_accepted",
            capture_git_commit="f" * 40,
        )


def test_partial_v3_refuses_rehashed_wrong_pending_index_even_with_valid_chain(
    tmp_path, monkeypatch,
):
    source, output, seen = _stopped_v3(tmp_path, monkeypatch)
    shard = output / "shard-0002"
    event_path = sorted(shard.glob("event-*.json"))[-1]
    event = json.loads(event_path.read_bytes())
    event["global_index"] = float(event["global_index"])
    raw = (canonical_json(event) + "\n").encode()
    replacement = shard / f"event-000007-{hash_bytes(raw)}.json"
    event_path.rename(replacement)
    replacement.write_bytes(raw)
    with pytest.raises(partial_verifier.PartialV3VerificationError, match="REFUSED"):
        _verify(source, output)
    assert len(seen) == 3


def test_observed_byte_anchors_refuse_rehashed_pending_start_without_shape_change(
    tmp_path, monkeypatch,
):
    source, output, seen = _stopped_v3(tmp_path, monkeypatch)
    original = _verify(source, output)
    monkeypatch.setattr(
        partial_verifier, "OBSERVED_V3_ROOT_PLAN_SHA256",
        original.root_plan_sha256,
    )
    monkeypatch.setattr(
        partial_verifier, "OBSERVED_V3_ACTIVE_JOURNAL_SHA256",
        original.pending_shard_journal_sha256,
    )
    monkeypatch.setattr(
        partial_verifier, "OBSERVED_V3_PENDING_START_SHA256",
        original.pending_attempt_start_sha256,
    )
    partial_verifier._require_observed_anchors(original)
    with pytest.raises(partial_verifier.PartialV3VerificationError, match="anchors"):
        partial_verifier._require_observed_anchors(
            replace(original, root_plan_sha256="0" * 64),
        )

    shard = output / original.pending_shard_name
    paths = sorted(shard.glob("event-*.json"))
    final = paths[-1]
    event = json.loads(final.read_bytes())
    assert event["kind"] == "attempt-start"
    event["started_utc"] = "2030-01-01T00:00:00.000000+00:00"
    raw = (canonical_json(event) + "\n").encode()
    replacement = shard / f"event-{len(paths):06d}-{hash_bytes(raw)}.json"
    final.rename(replacement)
    replacement.write_bytes(raw)
    changed = _verify(source, output)
    assert changed.completed_new_count == original.completed_new_count
    assert changed.attempt_count == original.attempt_count
    assert changed.pending_request_sha256 == original.pending_request_sha256
    assert changed.pending_shard_journal_sha256 != original.pending_shard_journal_sha256
    assert changed.pending_attempt_start_sha256 != original.pending_attempt_start_sha256
    with pytest.raises(partial_verifier.PartialV3VerificationError, match="anchors"):
        partial_verifier._require_observed_anchors(changed)
    assert len(seen) == 3


def test_partial_v3_refuses_changed_completed_object_without_dispatch(
    tmp_path, monkeypatch,
):
    source, output, seen = _stopped_v3(tmp_path, monkeypatch)
    object_path = next((output / "shard-0002" / "objects").glob("*.bin"))
    object_path.write_bytes(b"changed invented body")
    with pytest.raises(partial_verifier.PartialV3VerificationError, match="REFUSED"):
        _verify(source, output)
    assert len(seen) == 3


def test_partial_v3_refuses_extra_member_and_public_object_directory(
    tmp_path, monkeypatch,
):
    source, output, seen = _stopped_v3(tmp_path, monkeypatch)
    shard = output / "shard-0002"
    extra = shard / "invented-extra"
    extra.write_bytes(b"unused")
    extra.chmod(0o600)
    with pytest.raises(partial_verifier.PartialV3VerificationError, match="REFUSED"):
        _verify(source, output)
    extra.unlink()
    objects = shard / "objects"
    objects.chmod(0o755)
    with pytest.raises(partial_verifier.PartialV3VerificationError, match="REFUSED"):
        _verify(source, output)
    assert len(seen) == 3


def test_partial_v3_refuses_changed_external_source_and_active_writer(
    tmp_path, monkeypatch,
):
    source, output, seen = _stopped_v3(tmp_path, monkeypatch)
    lock_fd = os.open(output / "run.lock", os.O_RDONLY)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(partial_verifier.PartialV3VerificationError, match="REFUSED"):
            _verify(source, output)
    finally:
        os.close(lock_fd)
    selected_object = next((source[3] / "objects").glob("*.bin"))
    selected_object.write_bytes(b"changed external invented source")
    with pytest.raises(partial_verifier.PartialV3VerificationError, match="REFUSED"):
        _verify(source, output)
    assert len(seen) == 3


def test_observed_partial_entry_rejects_alternate_root_before_source_replay(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(
        partial_verifier.source_union,
        "preflight_observed_all_form4_parent_recovery_union",
        lambda *_, **__: pytest.fail("observed source replay reached"),
    )
    with pytest.raises(partial_verifier.PartialV3VerificationError, match="pinned"):
        partial_verifier.load_observed_partial_all_form4_recovery_v3(
            "/invented/raw-q4", "/invented/parsed-q4",
            "/invented/raw-q1", "/invented/parsed-q1", "/invented/pilot",
            partial_verifier.OBSERVED_SELECTED_ROOT,
            partial_verifier.OBSERVED_PRIOR_ROOT,
            partial_verifier.OBSERVED_DIAGNOSTIC_ROOT,
            tmp_path / "not-the-observed-v3-root",
        )
