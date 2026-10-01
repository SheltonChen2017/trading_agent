"""Invented-source v3 continuation tests with offline injected callbacks."""
from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_bytes
from research.insider_buying_sec_complete_acquisition import SecHttpResult
import research.insider_buying_sec_all_form4_parent_recovery_executor as executor
from test_insider_buying_sec_all_form4_parent_recovery_union import (
    _body, _stopped_source,
)


@pytest.fixture
def source(tmp_path, monkeypatch):
    return _stopped_source(tmp_path, monkeypatch)


def _run(source, output, transport, *, resume=False):
    plan, prior, diagnostic, selected, expectation, report_sha, _ = source
    return executor.run_synthetic_recovery_continuation(
        plan, prior, diagnostic, selected, output,
        prior_expectation=expectation,
        diagnostic_capture_git_commit="e" * 40,
        expected_diagnostic_report_sha256=report_sha,
        diagnostic_mode="originally_accepted",
        capture_git_commit="f" * 40,
        transport=transport,
        contact_email="invented@example.test",
        resume=resume,
    )


def _success_transport(source, seen):
    request = source[0].requests[-1]
    raw = _body(request)

    def transport(url, headers, cap):
        seen.append(url)
        assert url == request.url
        assert cap >= len(raw)
        assert headers["User-Agent"].endswith("(invented@example.test)")
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)

    return transport


def test_synthetic_v3_reuses_external_sources_and_dispatches_only_later_parent(
    source, tmp_path,
):
    seen = []
    output = tmp_path / "v3"
    report_path = _run(source, output, _success_transport(source, seen))
    assert seen == [source[0].requests[-1].url]
    assert report_path.name.startswith("campaign-report-")
    report = json.loads(report_path.read_text())
    assert report["total_parents"] == 7
    assert report["prior_completed_count"] == 4
    assert report["accepted_diagnostic_count"] == 1
    assert report["remaining_selected_reuse_count"] == 1
    assert report["later_acquired_count"] == 1
    assert report["new_attempt_count"] == 1
    assert report["complete_parent_bytes_acquired"] is True
    assert report["source_authenticated"] is False
    assert report["point_in_time_data"] is False
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o700
               for path in output.glob("shard-*") if path.is_dir())
    assert sum(1 for path in output.glob("shard-*/objects/*.bin")) == 1
    with pytest.raises(executor.RecoveryExecutorError, match="cannot be relaunched"):
        _run(source, output, _success_transport(source, seen), resume=True)
    assert len(seen) == 1


def test_multiple_later_parents_complete_in_order_across_shard_boundary(
    tmp_path, monkeypatch,
):
    source = _stopped_source(tmp_path, monkeypatch, request_count=10)
    requests = source[0].requests
    expected = requests[6:]
    seen = []

    def transport(url, _headers, _cap):
        seen.append(url)
        request = next(request for request in expected if request.url == url)
        raw = _body(request)
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)

    report = json.loads(_run(source, tmp_path / "multi", transport).read_text())
    assert seen == [request.url for request in expected]
    assert report["total_parents"] == 10
    assert report["later_acquired_count"] == 4
    assert report["new_attempt_count"] == 4
    assert [item["new_acquired_count"] for item in report["shards"]] == [0, 0, 3, 1]


def test_ambiguous_durable_start_cannot_redispatch_on_resume(source, tmp_path):
    seen = []

    def interrupted(url, _headers, _cap):
        seen.append(url)
        raise OSError("invented timeout after possible delivery")

    output = tmp_path / "ambiguous"
    with pytest.raises(executor.RecoveryExecutorError, match="ambiguous"):
        _run(source, output, interrupted)
    shard = output / "shard-0002"
    assert len(list(shard.glob("event-*.json"))) == 1
    assert not list(shard.glob("shard-report-*.json"))
    with pytest.raises(executor.RecoveryExecutorError, match="cannot be redispatched"):
        _run(source, output, _success_transport(source, seen), resume=True)
    assert seen == [source[0].requests[-1].url]


def test_only_durable_explicit_503_can_retry(source, tmp_path):
    seen = []
    success = _success_transport(source, seen)

    def transport(url, headers, cap):
        if not seen:
            seen.append(url)
            return SecHttpResult(503, (), b"")
        return success(url, headers, cap)

    output = tmp_path / "retry"
    report = json.loads(_run(source, output, transport).read_text())
    assert seen == [source[0].requests[-1].url] * 2
    assert report["new_attempt_count"] == 2
    events = [json.loads(path.read_text()) for path in sorted(
        (output / "shard-0002").glob("event-*.json"),
    )]
    assert [event["kind"] for event in events] == [
        "attempt-start", "attempt-finish", "attempt-start", "attempt-finish",
        "item-complete",
    ]
    assert events[1]["outcome"] == "http_error"
    assert events[1]["status"] == 503


def test_invalid_200_is_stored_but_never_completes_or_retries(source, tmp_path):
    seen = []
    request = source[0].requests[-1]
    raw = _body(request, wrong=True)

    def transport(url, _headers, _cap):
        seen.append(url)
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)

    output = tmp_path / "bad-200"
    with pytest.raises(executor.RecoveryExecutorError, match="shard ended incomplete"):
        _run(source, output, transport)
    shard = output / "shard-0002"
    assert len(list(shard.glob("objects/*.bin"))) == 1
    report = json.loads(next(shard.glob("shard-report-*.json")).read_text())
    assert report["complete_shard_raw_set_acquired"] is False
    assert report["new_acquired_count"] == 0
    assert report["rows"][-1]["status"] == "refused"
    with pytest.raises(executor.RecoveryExecutorError, match="terminal incomplete"):
        _run(source, output, transport, resume=True)
    assert seen == [request.url]


def test_valid_fsynced_finish_without_completion_resumes_offline_only(
    source, tmp_path, monkeypatch,
):
    seen = []
    original_append = executor._Events.append
    interrupted = [False]

    def interrupt_after_finish(self, payload):
        if payload["kind"] == "item-complete" and not interrupted[0]:
            interrupted[0] = True
            raise KeyboardInterrupt("invented crash after durable HTTP 200 finish")
        return original_append(self, payload)

    output = tmp_path / "finish-only"
    with monkeypatch.context() as patch:
        patch.setattr(executor._Events, "append", interrupt_after_finish)
        with pytest.raises(KeyboardInterrupt):
            _run(source, output, _success_transport(source, seen))
    shard = output / "shard-0002"
    assert [json.loads(path.read_text())["kind"] for path in sorted(
        shard.glob("event-*.json"),
    )] == ["attempt-start", "attempt-finish"]
    report = json.loads(_run(source, output, _success_transport(source, seen),
                             resume=True).read_text())
    assert report["later_acquired_count"] == 1
    assert seen == [source[0].requests[-1].url]


def test_rehashed_finish_clock_before_durable_start_refuses_offline_resume(
    source, tmp_path, monkeypatch,
):
    seen = []
    original_append = executor._Events.append

    def interrupt_after_finish(self, payload):
        if payload["kind"] == "item-complete":
            raise KeyboardInterrupt("invented crash after durable HTTP 200 finish")
        return original_append(self, payload)

    output = tmp_path / "backward-clock"
    with monkeypatch.context() as patch:
        patch.setattr(executor._Events, "append", interrupt_after_finish)
        with pytest.raises(KeyboardInterrupt):
            _run(source, output, _success_transport(source, seen))
    shard = output / "shard-0002"
    event_paths = sorted(shard.glob("event-*.json"))
    assert len(event_paths) == 2
    start = json.loads(event_paths[0].read_text())
    finish = json.loads(event_paths[1].read_text())
    assert finish["finished_utc"] >= start["started_utc"]
    finish["finished_utc"] = "2000-01-01T00:00:00.000000+00:00"
    raw = (canonical_json(finish) + "\n").encode()
    replacement = shard / f"event-000002-{hash_bytes(raw)}.json"
    event_paths[1].rename(replacement)
    replacement.write_bytes(raw)
    with pytest.raises(executor.RecoveryExecutorError, match="clock precedes"):
        _run(source, output, _success_transport(source, seen), resume=True)
    assert seen == [source[0].requests[-1].url]


def test_missing_fsynced_body_after_finish_halts_without_redispatch(
    source, tmp_path, monkeypatch,
):
    seen = []
    original_append = executor._Events.append

    def interrupt_after_finish(self, payload):
        if payload["kind"] == "item-complete":
            raise KeyboardInterrupt("invented crash")
        return original_append(self, payload)

    output = tmp_path / "missing-body"
    with monkeypatch.context() as patch:
        patch.setattr(executor._Events, "append", interrupt_after_finish)
        with pytest.raises(KeyboardInterrupt):
            _run(source, output, _success_transport(source, seen))
    object_path = next((output / "shard-0002" / "objects").glob("*.bin"))
    object_path.unlink()
    with pytest.raises(executor.RecoveryExecutorError, match="verification failed"):
        _run(source, output, _success_transport(source, seen), resume=True)
    assert seen == [source[0].requests[-1].url]


def test_selected_source_drift_during_run_blocks_top_report(source, tmp_path):
    seen = []
    success = _success_transport(source, seen)
    selected_object = next((source[3] / "objects").glob("*.bin"))

    def transport(url, headers, cap):
        response = success(url, headers, cap)
        selected_object.write_bytes(b"changed external source")
        return response

    output = tmp_path / "source-drift"
    with pytest.raises(executor.RecoveryExecutorError, match="verification failed"):
        _run(source, output, transport)
    assert seen == [source[0].requests[-1].url]
    assert not list(output.glob("campaign-report-*.json"))
    assert not (output / "commit.json").exists()


def test_broadened_private_member_refuses_resume_before_transport(source, tmp_path):
    seen = []

    def interrupted(url, _headers, _cap):
        seen.append(url)
        raise OSError("ambiguous")

    output = tmp_path / "public-member"
    with pytest.raises(executor.RecoveryExecutorError, match="ambiguous"):
        _run(source, output, interrupted)
    inventory = output / "shard-0002" / "inventory.json"
    inventory.chmod(0o644)
    with pytest.raises(executor.RecoveryExecutorError, match="not a private"):
        _run(source, output, _success_transport(source, seen), resume=True)
    assert seen == [source[0].requests[-1].url]


def test_rehashed_float_request_index_cannot_alias_exact_integer(source, tmp_path):
    seen = []

    def interrupted(url, _headers, _cap):
        seen.append(url)
        raise OSError("ambiguous")

    output = tmp_path / "float-event"
    with pytest.raises(executor.RecoveryExecutorError, match="ambiguous"):
        _run(source, output, interrupted)
    shard = output / "shard-0002"
    event_path = next(shard.glob("event-*.json"))
    event = json.loads(event_path.read_text())
    event["global_index"] = float(event["global_index"])
    raw = (canonical_json(event) + "\n").encode()
    replacement = shard / f"event-000001-{hash_bytes(raw)}.json"
    event_path.rename(replacement)
    replacement.write_bytes(raw)
    with pytest.raises(executor.RecoveryExecutorError, match="event differs"):
        _run(source, output, _success_transport(source, seen), resume=True)
    assert seen == [source[0].requests[-1].url]


def test_terminal_finish_without_report_is_finalized_offline_without_retry(
    source, tmp_path, monkeypatch,
):
    seen = []
    request = source[0].requests[-1]
    bad = _body(request, wrong=True)

    def bad_transport(url, _headers, _cap):
        seen.append(url)
        return SecHttpResult(200, (("Content-Length", str(len(bad))),), bad)

    original_publish = executor._publish

    def interrupt_report(root, identity, name, raw, *, cap):
        if root.name == "shard-0002" and name == "attempts.jsonl":
            raise KeyboardInterrupt("invented crash after terminal finish")
        return original_publish(root, identity, name, raw, cap=cap)

    output = tmp_path / "terminal-finish"
    with monkeypatch.context() as patch:
        patch.setattr(executor, "_publish", interrupt_report)
        with pytest.raises(KeyboardInterrupt):
            _run(source, output, bad_transport)
    assert not list((output / "shard-0002").glob("shard-report-*.json"))
    with pytest.raises(executor.RecoveryExecutorError, match="shard ended incomplete"):
        _run(source, output, _success_transport(source, seen), resume=True)
    report = json.loads(next((output / "shard-0002").glob(
        "shard-report-*.json",
    )).read_text())
    assert report["halted_reason"] == "REFUSED: v3 HTTP 200 parent is not validated"
    assert seen == [request.url]


def _observed_args(*, selected=None, prior=None, diagnostic=None, output=None):
    return dict(
        raw_q4_directory="/invented/raw-q4", parsed_q4_directory="/invented/parsed-q4",
        raw_q1_directory="/invented/raw-q1", parsed_q1_directory="/invented/parsed-q1",
        exact16_pilot_root="/invented/pilot",
        selected_root=selected or executor._OBSERVED_SELECTED_ROOT,
        prior_campaign_root=prior or executor._OBSERVED_PRIOR_ROOT,
        diagnostic_root=diagnostic or executor._OBSERVED_DIAGNOSTIC_ROOT,
        output_root=output or executor._OBSERVED_OUTPUT_ROOT,
        contact_email="invented@example.test", capture_git_commit="f" * 40,
    )


def test_observed_entry_refuses_copied_roots_and_destination_before_any_source_replay(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(executor, "_verify_exact_committed_code", lambda _: None)
    monkeypatch.setattr(executor.union, "preflight_observed_all_form4_parent_recovery_union",
                        lambda *_, **__: pytest.fail("source replay reached"))
    cases = (
        {"selected": tmp_path / "selected-copy"},
        {"prior": tmp_path / "prior-copy"},
        {"diagnostic": tmp_path / "diagnostic-copy"},
        {"output": tmp_path / "different-output"},
    )
    for overrides in cases:
        with pytest.raises(executor.RecoveryExecutorError, match="pinned|root"):
            executor.run_observed_recovery_continuation(**_observed_args(**overrides))
    assert not (tmp_path / "different-output").exists()


def test_observed_entry_refuses_dirty_or_changed_head_before_transport(monkeypatch):
    real_root = Path(executor.__file__).resolve().parents[1]
    commit = "f" * 40

    def git_dirty(*args):
        if args == ("rev-parse", "--show-toplevel"):
            return (str(real_root) + "\n").encode()
        if args == ("branch", "--show-current"):
            return b"codex/strategy-insider-buying\n"
        if args == ("rev-parse", "HEAD"):
            return (commit + "\n").encode()
        if args == ("status", "--porcelain=v1", "--untracked-files=all"):
            return b" M research/insider_buying_sec_all_form4_parent_recovery_executor.py\n"
        pytest.fail(f"unexpected Git command: {args}")

    monkeypatch.setattr(executor, "_git_output", git_dirty)
    with pytest.raises(executor.RecoveryExecutorError, match="clean committed"):
        executor._verify_exact_committed_code(commit)

    def git_wrong_head(*args):
        if args == ("rev-parse", "HEAD"):
            return ("e" * 40 + "\n").encode()
        return git_dirty(*args)

    monkeypatch.setattr(executor, "_git_output", git_wrong_head)
    with pytest.raises(executor.RecoveryExecutorError, match="clean committed"):
        executor._verify_exact_committed_code(commit)


def test_observed_entry_refuses_changed_committed_dependency(monkeypatch):
    root = Path(executor.__file__).resolve().parents[1]
    commit = "f" * 40
    def git_output(*args):
        if args == ("rev-parse", "--show-toplevel"):
            return (str(root) + "\n").encode()
        if args == ("branch", "--show-current"):
            return b"codex/strategy-insider-buying\n"
        if args == ("rev-parse", "HEAD"):
            return (commit + "\n").encode()
        if args == ("status", "--porcelain=v1", "--untracked-files=all"):
            return b""
        if args == ("show", f"{commit}:{executor._COMMITTED_DEPENDENCIES[0]}"):
            return b"changed executor dependency"
        pytest.fail(f"unexpected Git command: {args}")
    monkeypatch.setattr(executor, "_git_output", git_output)
    with pytest.raises(executor.RecoveryExecutorError, match="dependency differs"):
        executor._verify_exact_committed_code(commit)


def test_observed_runner_refuses_any_injected_nonreviewed_transport_before_output(
    source, tmp_path, monkeypatch,
):
    plan, prior, diagnostic, selected, expectation, report_sha, _ = source
    monkeypatch.setattr(executor, "_verify_exact_committed_code", lambda _: None)
    output = tmp_path / "wrong-transport"
    with pytest.raises(executor.RecoveryExecutorError, match="transport differs"):
        executor._run(
            plan, prior, diagnostic, selected, output,
            prior_expectation=expectation,
            diagnostic_capture_git_commit="e" * 40,
            expected_diagnostic_report_sha256=report_sha,
            diagnostic_mode="originally_accepted", capture_git_commit="f" * 40,
            transport=lambda *_: pytest.fail("transport dispatched"),
            contact_email="invented@example.test", resume=False, observed=True,
        )
    assert not output.exists()


def test_observed_entry_passes_only_frozen_source_partition_to_reviewed_transport(
    source, tmp_path, monkeypatch,
):
    _, prior, diagnostic, selected, _, _, _ = source
    output = tmp_path / "all-form4-parents-recovery-v3"
    monkeypatch.setattr(executor, "_OBSERVED_PRIOR_ROOT", prior)
    monkeypatch.setattr(executor, "_OBSERVED_DIAGNOSTIC_ROOT", diagnostic)
    monkeypatch.setattr(executor, "_OBSERVED_SELECTED_ROOT", selected)
    monkeypatch.setattr(executor, "_OBSERVED_OUTPUT_ROOT", output)
    monkeypatch.setattr(executor.union.diagnostic, "_PRIOR_CAMPAIGN_ROOT", prior)
    monkeypatch.setattr(executor.union, "_DIAGNOSTIC_NAME", diagnostic.name)
    monkeypatch.setattr(executor.recovery, "_OUTPUT_NAME", output.name)
    monkeypatch.setattr(executor, "_verify_exact_committed_code", lambda _: None)
    def forbidden_transport(*_args):
        pytest.fail("observed SEC transport was dispatched")
    monkeypatch.setattr(executor.campaign, "_selected_sec_transport", forbidden_transport)
    receipt = {
        "prior_completed_count": 9_539,
        "offline_corrected_diagnostic_count": 1,
        "accepted_diagnostic_count": 0,
        "remaining_selected_reuse_count": 8_139,
        "source_assignment_sha256": executor._OBSERVED_ASSIGNMENT_SHA256,
        "later_unattempted_request_inventory_sha256":
            executor._OBSERVED_LATER_INVENTORY_SHA256,
    }
    monkeypatch.setattr(
        executor.union, "preflight_observed_all_form4_parent_recovery_union",
        lambda *_, **__: receipt,
    )
    plan = SimpleNamespace(
        scope="ib1b_observed_full_form4_noncanonical",
        manifest_sha256=executor.campaign.REAL_MANIFEST_SHA256,
        shard_size=executor.campaign.SHARD_SIZE,
        requests=range(99_394),
        to_payload=lambda: {
            "request_inventory_sha256": executor.partial.PRIOR_REQUEST_INVENTORY_SHA256,
        },
    )
    monkeypatch.setattr(executor.campaign, "_build_real_plan", lambda *args: plan)
    monkeypatch.setattr(executor.recovery, "_source_layout", lambda *_: (
        ["prior_completed"] * 99_394, range(81_715),
    ))
    seen = []
    def inert_run(*args, **kwargs):
        seen.append((args, kwargs))
        assert args[:5] == (plan, prior, diagnostic, selected, output)
        assert kwargs["transport"] is forbidden_transport
        assert kwargs["observed"] is True
        assert kwargs["diagnostic_mode"] == "offline_corrected"
        assert kwargs["prior_expectation"].total_attempt_count == 8_342
        return output / "inert-report"
    monkeypatch.setattr(executor, "_run", inert_run)
    result = executor.run_observed_recovery_continuation(**_observed_args(
        selected=selected, prior=prior, diagnostic=diagnostic, output=output,
    ))
    assert result == output / "inert-report"
    assert len(seen) == 1
    assert not output.exists()


def test_mid_shard_lane_drift_refuses_before_next_observed_attempt(
    tmp_path, monkeypatch,
):
    source = _stopped_source(tmp_path, monkeypatch, request_count=10)
    plan, prior, diagnostic, selected, expectation, report_sha, _ = source
    original_source_and_plan = executor._source_and_plan
    monkeypatch.setattr(
        executor, "_source_and_plan",
        lambda *args, **kwargs: original_source_and_plan(
            *args, **{**kwargs, "observed": False},
        ),
    )
    monkeypatch.setattr(executor, "_verify_exact_committed_code", lambda _: None)
    seen = []
    def offline_transport(url, _headers, _cap):
        seen.append(url)
        request = next(request for request in plan.requests if request.url == url)
        raw = _body(request)
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)
    monkeypatch.setattr(executor.campaign, "_selected_sec_transport", offline_transport)
    checks = []
    def lane_state(_commit):
        checks.append(True)
        if len(checks) > 1:
            raise executor.RecoveryExecutorError(
                "REFUSED: exact clean committed Insider lane is required"
            )
    monkeypatch.setattr(executor, "_verify_lane_state", lane_state)
    output = tmp_path / "mid-shard"
    with pytest.raises(executor.RecoveryExecutorError, match="clean committed"):
        executor._run(
            plan, prior, diagnostic, selected, output,
            prior_expectation=expectation,
            diagnostic_capture_git_commit="e" * 40,
            expected_diagnostic_report_sha256=report_sha,
            diagnostic_mode="originally_accepted", capture_git_commit="f" * 40,
            transport=offline_transport, contact_email="invented@example.test",
            resume=False, observed=True,
        )
    assert len(checks) == 2
    assert seen == [plan.requests[6].url]
    events = [json.loads(path.read_text()) for path in (
        output / "shard-0002").glob("event-*.json")]
    assert sum(event["kind"] == "attempt-start" for event in events) == 1


# Section 119 (Claude review): the v3 executor made 1,847 real requests, yet no
# test asserted its 500 ms completion-to-dispatch rule, the dispatch-time
# recheck, or that the synthetic entry cannot reach the SEC client.
def _multi_parent_transport(source, stamps):
    expected = source[0].requests[6:]

    def transport(url, _headers, _cap):
        stamps.append(executor.campaign.time.monotonic_ns())
        request = next(request for request in expected if request.url == url)
        raw = _body(request)
        return SecHttpResult(200, (("Content-Length", str(len(raw))),), raw)

    return transport


def test_v3_requests_keep_completion_to_dispatch_spacing(tmp_path, monkeypatch):
    source = _stopped_source(tmp_path, monkeypatch, request_count=10)
    stamps = []
    _run(source, tmp_path / "paced", _multi_parent_transport(source, stamps))
    assert len(stamps) == 4
    assert all(later - prior >= executor.campaign.MIN_REQUEST_INTERVAL_NS
               for prior, later in zip(stamps, stamps[1:]))


def test_v3_dispatch_refuses_when_the_pacing_sleep_returns_early(tmp_path, monkeypatch):
    source = _stopped_source(tmp_path, monkeypatch, request_count=10)
    monkeypatch.setattr(executor.campaign.time, "sleep", lambda _seconds: None)
    stamps = []
    with pytest.raises(executor.RecoveryExecutorError) as refused:
        _run(source, tmp_path / "early", _multi_parent_transport(source, stamps))
    reasons = []
    current: BaseException | None = refused.value
    while current is not None:
        reasons.append(str(current))
        current = current.__cause__
    assert any("dispatch pacing was too early" in reason for reason in reasons)
    assert len(stamps) == 1


def test_synthetic_v3_entry_cannot_use_the_reviewed_sec_client(source, tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("a connection was attempted")

    monkeypatch.setattr("http.client.HTTPSConnection", forbidden)
    with pytest.raises(executor.RecoveryExecutorError,
                       match="synthetic v3 transport cannot use the SEC client"):
        _run(source, tmp_path / "real-client", executor.campaign._selected_sec_transport)
