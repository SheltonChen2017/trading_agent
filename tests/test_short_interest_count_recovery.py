"""Fabricated, network-denied tests for the one-claim count recovery kernel."""
from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import threading

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload

# The runtime under test imports POSIX-only stdlib modules at import time, so
# this module cannot even be collected on the supported Windows host; see the
# lane record SI-CR18-001. Portable contract logic stays covered on POSIX.
pytest.importorskip(
    "resource",
    reason=(
        "the protected-capture runtime imports the POSIX-only module "
        "resource at import time; it cannot execute on this host, see the "
        "lane record SI-CR18-001"
    ),
)

from scripts import capture_short_interest_count_recovery as recovery


spec = importlib.util.spec_from_file_location(
    "fabricated_count_recovery_anchor_fixture",
    Path(__file__).with_name("test_short_interest_native_reported_anchor_plan.py"),
)
fabricated = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fabricated
spec.loader.exec_module(fabricated)


def stamp(second):
    return (datetime(2026, 10, 21, tzinfo=timezone.utc)
            + timedelta(seconds=second)).isoformat().replace("+00:00", "Z")


class Clock:
    def __init__(self):
        self.value = 100
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            self.value += 1
            return stamp(self.value)


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def refused(*unused, **kwargs):
        raise AssertionError("fabricated tests must not reach the network")
    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(socket.socket, "connect_ex", refused)


def small_domain(monkeypatch):
    # Forty-nine changing share classes produce forty-nine exact source tickets.
    # A tiny fabricated page bound keeps the original and child whole-page
    # reservation arithmetic realistic without allocating licensed-size rows.
    monkeypatch.setattr(recovery.parallel, "MAXIMUM_RESPONSE_BYTES", 64)
    dates = tuple((date(2023, 1, 1) + timedelta(days=i)).isoformat() for i in range(49))
    reports = tuple(fabricated.identity(at, class_id=(fabricated.CLASS if i % 2
                    else fabricated.NEXT_CLASS)) for i, at in enumerate(dates))
    source = fabricated.plan(dates, reports=reports)
    assert source.to_payload()["exact_request_budget"] == 49
    page = recovery.parallel.MAXIMUM_RESPONSE_BYTES
    monkeypatch.setattr(recovery, "ORIGINAL_COUNT", 49)
    monkeypatch.setattr(recovery, "NEW_POSITIONS", (47, 49))
    monkeypatch.setattr(recovery, "MAXIMUM_NEW_STARTS", 2)
    monkeypatch.setattr(recovery, "MAXIMUM_CUMULATIVE_STARTS", 50)
    monkeypatch.setattr(recovery, "MAXIMUM_CUMULATIVE_BYTES", 49 * page)
    monkeypatch.setattr(recovery.original, "ANCHOR_PLAN_SHA256", source.sha256)
    monkeypatch.setattr(recovery.original, "MAXIMUM_TOTAL_RESPONSE_BYTES", 49 * page)
    plan = recovery.parallel.freeze_parallel_count_plan(
        source.query_plan, maximum_total_response_bytes=49 * page)
    monkeypatch.setattr(recovery.original, "PARALLEL_PLAN_SHA256", plan.sha256)
    monkeypatch.setattr(recovery.original, "PROTOCOL_SHA256", hash_payload(recovery.original.protocol()))
    old_code = b"fabricated old code only"
    old_code_sha = hash_payload({"git_commit": recovery.PARENT_HEAD,
        "files": [{"path": name, "sha256": hash_bytes(old_code)}
                  for name in recovery.cache.COUNT_CODE_FILES]})
    monkeypatch.setattr(recovery, "PARENT_CODE_SHA256", old_code_sha)
    files = {"protocol.private.json": canonical_json(recovery.original.protocol()).encode(),
             "started.json": canonical_json({"schema": "si-cache-parallel-count-start-v1",
                 "started_at": stamp(0), "code_head": recovery.PARENT_HEAD,
                 "remote_head": recovery.PARENT_HEAD,
                 "protocol_sha256": recovery.original.PROTOCOL_SHA256,
                 "code_identity_sha256": old_code_sha, "outcome_looks": 0,
                 "qc_attempts": 0}).encode(),
             "run.refused.json": canonical_json({"schema": "si-cache-parallel-count-refused-v1",
                 "code": "started_prefix_drained_no_completed_source_capture",
                 "refused_at": stamp(100), "attempts_started": 48,
                 "outcome_looks": 0, "qc_attempts": 0,
                 "backtest_result_exists": False}).encode()}
    raw = b'{"status":"OK"}' + b" " * (page - len(b'{"status":"OK"}'))
    for ordinal, query in zip(range(1, 49), source.query_plan.iter_queries()):
        ticket = query.to_payload()
        name = f"query-{ordinal:08d}"
        files[name + ".started.json"] = canonical_json({
            "schema": "si-parallel-count-request-start-v1", "query_ordinal": ordinal,
            "request": ticket["request"], "request_sha256": ticket["request_sha256"],
            "started_at": stamp(ordinal), "plan_sha256": plan.sha256,
            "code_head": recovery.PARENT_HEAD,
            "whole_page_bytes_reserved": page}).encode()
        observed = ordinal != 47
        body = b"" if ordinal == 48 else raw
        files[name + ".received.json"] = canonical_json({
            "query_ordinal": ordinal, "request_sha256": ticket["request_sha256"],
            "started_at": stamp(ordinal), "received_at": stamp(ordinal + 1),
            "http_attempted": observed, "http_status": 200 if observed else None,
            "body_observed": observed, "raw_path": name + ".raw" if observed else None,
            "raw_sha256": hash_bytes(body) if observed else None,
            "raw_bytes": len(body) if observed else None,
            "content_type": "application/json" if observed else None,
            "code": "received" if observed else "material_request_refused"}).encode()
        if observed:
            files[name + ".raw"] = body
    charged = page + 46 * len(raw)
    monkeypatch.setattr(recovery, "PARENT_CHARGED_BYTES", charged)
    monkeypatch.setattr(recovery, "MAXIMUM_CHILD_BYTES", 49 * page - charged)
    claim = canonical_json({"schema": "si-cache-parallel-count-global-claim-v1",
        "protocol_sha256": recovery.original.PROTOCOL_SHA256,
        "anchor_plan_sha256": source.sha256,
        "cache_closure_sha256": recovery.original.CACHE_CLOSURE_SHA256,
        "parallel_plan_sha256": plan.sha256, "started_at": stamp(0),
        "maximum_attempts": 49, "maximum_total_response_bytes": 49 * page,
        "restart_allowed": False}).encode()
    monkeypatch.setattr(recovery, "PARENT_MANIFEST_SHA256", hash_payload([
        {"name": name, "sha256": hash_bytes(files[name]), "bytes": len(files[name])}
        for name in sorted(files)]))
    monkeypatch.setattr(recovery, "PARENT_CLAIM_SHA256", hash_bytes(claim))
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    monkeypatch.setattr(recovery, "MAPPING_SHA256", hash_payload(
        ((47, selected[46]), (49, selected[48]))))
    monkeypatch.setattr(recovery, "PROTOCOL_SHA256", hash_payload(recovery.protocol()))
    child = recovery.freeze_recovery(source)
    prefix = recovery.verify_prefix(source, child.parent_plan, files, claim,
        lambda head, name: old_code, lambda: None)
    return source, child.parent_plan, files, claim, old_code, prefix, child


def test_exact_child_mapping_budget_and_original_negative(monkeypatch):
    source, parent, files, claim, code, prefix, child = small_domain(monkeypatch)
    assert len(files) == 146
    assert prefix.inventory.to_payload()["attempts_started"] == 48
    assert prefix.inventory.receipt_for_ordinal(47)["http_attempted"] is False
    assert prefix.inventory.to_payload()["charged_response_bytes"] == recovery.PARENT_CHARGED_BYTES
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    assert child.child_plan._queries.to_payload()["selected_query_ordinals"] == [selected[46], selected[48]]
    assert child.child_plan.to_payload()["maximum_total_response_bytes"] + recovery.PARENT_CHARGED_BYTES == recovery.MAXIMUM_CUMULATIVE_BYTES
    assert child.child_plan.to_payload()["maximum_attempts"] == 2


@pytest.mark.parametrize("mutation", ["raw", "claim", "negative", "historical_code"])
def test_parent_byte_control_and_old_code_tamper_refuse(monkeypatch, mutation):
    source, parent, files, claim, code, prefix, child = small_domain(monkeypatch)
    files = dict(files)
    if mutation == "raw":
        files["query-00000001.raw"] += b" "
    elif mutation == "claim":
        claim += b" "
    elif mutation == "negative":
        record = json.loads(files["query-00000047.received.json"])
        record["http_attempted"] = True
        files["query-00000047.received.json"] = canonical_json(record).encode()
        monkeypatch.setattr(recovery, "PARENT_MANIFEST_SHA256", hash_payload([
            {"name": name, "sha256": hash_bytes(files[name]), "bytes": len(files[name])}
            for name in sorted(files)]))
        monkeypatch.setattr(recovery, "PROTOCOL_SHA256", hash_payload(recovery.protocol()))
    else:
        code += b"changed"
    with pytest.raises((recovery.RecoveryRefusal, recovery.parallel.ParallelCountRefusal)):
        recovery.verify_prefix(source, parent, files, claim,
            lambda head, name: code, lambda: None)


def runtime(monkeypatch, tmp_path, *, status=200, remote_drift=False):
    source, parent, files, claim, code, prefix, child = small_domain(monkeypatch)
    root = tmp_path.resolve()
    root.chmod(0o700)
    directory = root / "private" / "child"
    directory.parent.mkdir(mode=0o700)
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(recovery, "OUTPUT", Path("private/child"))
    monkeypatch.setattr(recovery, "PROTOCOL_SHA256", hash_payload(recovery.protocol()))
    monkeypatch.setattr(recovery.lane, "ROOT", root)
    head = "a" * 40
    state = {"remote": head, "http": 0, "key": 0}

    def runner(root, command):
        if command == ["git", "rev-parse", "--show-toplevel"]:
            return (str(root) + "\n").encode()
        if command[:2] == ["git", "status"]:
            return ("# branch.oid " + head + "\n# branch.head codex/strategy-short-interest\n").encode()
        assert command == ["git", "ls-remote", "--exit-code", "origin", recovery.lane.REF]
        return (state["remote"] + "\t" + recovery.lane.REF + "\n").encode()

    guard = recovery.lane.LaneGuard(root, expected_head=head,
        expected_remote=head, runner=runner, physical=lambda root: None)

    def key(provider):
        assert provider == "massive"
        assert (directory.parent / recovery.CLAIM_NAME).exists()
        assert (directory / "started.json").exists()
        state["key"] += 1
        return recovery.KeychainSecret("FABRICATED_COUNT_RECOVERY_TEST_KEY")

    def http(opener, request, maximum):
        assert request.get_header("Authorization") == "Bearer FABRICATED_COUNT_RECOVERY_TEST_KEY"
        state["http"] += 1
        if remote_drift:
            state["remote"] = "b" * 40
        if status != 200:
            raise recovery.SharadarCaptureRefusal("fabricated_non_200", status=status)
        return b'{"status":"OK","results":{}}', "application/json", 200

    kwargs = {"guard": guard, "owned": None, "code_identity_sha256": "c" * 64,
        "source_custody": lambda: None, "code_custody": lambda: None,
        "read_secret": key, "clock": Clock(), "http": http}
    return root, directory, child, prefix, kwargs, state


def execute(value):
    root, directory, child, prefix, kwargs, state = value
    with recovery._OwnedOutput(directory, lambda: None) as owned:
        assert owned._anchor[0] == root / recovery.OUTPUT == directory
        assert prefix._anchor[0] is child.source
        assert prefix._anchor[1] is child.parent_plan
        assert type(kwargs["guard"]) is recovery.lane.LaneGuard
        return recovery.capture_child(root, directory, child, prefix,
            **{**kwargs, "owned": owned})


def test_new_claim_precedes_key_and_two_new_starts_not_original_48(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path)
    result = execute(value)
    directory, state = value[1], value[5]
    assert state["key"] == 1 and state["http"] == 2
    assert result.to_payload()["attempts_started"] == 2
    assert result.to_payload()["complete_frozen_request_sequence"] is True
    assert sorted(p.name for p in directory.glob("query-*.started.json")) == [
        "query-00000001.started.json", "query-00000002.started.json"]
    assert json.loads((directory / "query-00000001.started.json").read_bytes())["original_count_position"] == 47
    assert json.loads((directory / "query-00000002.started.json").read_bytes())["original_count_position"] == 49
    assert json.loads((directory / "child.completed.json").read_bytes())["original_round_complete"] is False
    assert (directory / "round.closed.qualified.json").exists()


def test_404_is_status_only_and_does_not_synthesize_body_or_source_admission(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path, status=404)
    result = execute(value)
    directory = value[1]
    assert result.to_payload()["http_invocations"] == 2
    assert result.to_payload()["charged_response_bytes"] == 0
    assert all(record["code"] == "HTTP_404_body_unobserved" for record in result.iter_receipts())
    assert list(directory.glob("query-*.raw")) == []
    assert json.loads((directory / "child.completed.json").read_bytes())["authority"]["source_admitted"] is False


def test_remote_drift_drains_started_slots_and_never_completes(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path, remote_drift=True)
    result = execute(value)
    directory = value[1]
    assert result is None and value[5]["http"] == 2
    assert len(list(directory.glob("query-*.received.json"))) == 2
    assert (directory / "run.refused.json").exists()
    assert not (directory / "child.completed.json").exists()


def test_remote_drift_after_child_marker_requires_refused_closure(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path)
    original = recovery._OwnedOutput.publish

    def changed(self, name, raw, **kwargs):
        result = original(self, name, raw, **kwargs)
        if name == "child.completed.json":
            value[5]["remote"] = "b" * 40
        return result

    monkeypatch.setattr(recovery._OwnedOutput, "publish", changed)
    with pytest.raises(Exception):
        execute(value)
    assert value[5]["http"] == 2
    assert not (value[1] / "child.completed.json").exists() or (
        value[1] / "round.closed.refused.json").exists()


def test_remote_drift_during_qualified_closure_cannot_return_success(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path)
    original = recovery._OwnedOutput.publish

    def changed(self, name, raw, **kwargs):
        result = original(self, name, raw, **kwargs)
        if name == "round.closed.qualified.json":
            value[5]["remote"] = "b" * 40
        return result

    monkeypatch.setattr(recovery._OwnedOutput, "publish", changed)
    try:
        result = execute(value)
    except Exception:
        result = None
    assert value[5]["http"] == 2
    assert result is None
    assert (value[1] / "round.closed.refused.json").exists()


def test_exclusive_claim_collision_prevents_key_or_HTTP(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path)
    (value[1].parent / recovery.CLAIM_NAME).write_bytes(b"fabricated-existing-claim")
    with pytest.raises(FileExistsError):
        execute(value)
    assert value[5]["key"] == value[5]["http"] == 0


def test_low_descriptor_headroom_refuses_before_spent_claim_or_key(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path)
    baseline = len(os.listdir("/dev/fd"))
    monkeypatch.setattr(recovery.resource, "getrlimit", lambda unused: (baseline + 95, baseline + 95))
    monkeypatch.setattr(recovery.resource, "setrlimit",
        lambda *unused: pytest.fail("must not mutate the process descriptor limit"))
    with pytest.raises(recovery.RecoveryRefusal, match="insufficient_preclaim_descriptor_headroom"):
        execute(value)
    assert not (value[1].parent / recovery.CLAIM_NAME).exists()
    assert value[5]["key"] == value[5]["http"] == 0


def test_fatal_http_drains_both_starts_and_records_cumulative_charges(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path, status=429)
    assert execute(value) is None
    directory = value[1]
    assert value[5]["http"] == 2
    assert len(list(directory.glob("query-*.started.json"))) == 2
    assert len(list(directory.glob("query-*.received.json"))) == 2
    refusal = json.loads((directory / "run.refused.json").read_bytes())
    assert refusal["child_starts"] == 2 and refusal["cumulative_starts"] == 50
    assert refusal["child_charged_response_bytes"] == 2 * recovery.parallel.MAXIMUM_RESPONSE_BYTES
    assert refusal["cumulative_charged_response_bytes"] == recovery.PARENT_CHARGED_BYTES + 2 * recovery.parallel.MAXIMUM_RESPONSE_BYTES
    assert not (directory / "child.completed.json").exists()


def test_unreceipted_body_observation_charges_full_reserved_pages(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path)

    class InvalidWorkerClock(Clock):
        def __call__(self):
            if threading.current_thread() is not threading.main_thread():
                return "fabricated-invalid-worker-clock"
            return super().__call__()

    value[4]["clock"] = InvalidWorkerClock()
    assert execute(value) is None
    directory = value[1]
    assert value[5]["http"] == 2
    assert len(list(directory.glob("query-*.started.json"))) == 2
    assert not list(directory.glob("query-*.received.json"))
    refusal = json.loads((directory / "run.refused.json").read_bytes())
    assert len(refusal["unreceipted_diagnostics"]) == 2
    assert refusal["child_charged_response_bytes"] == 2 * recovery.parallel.MAXIMUM_RESPONSE_BYTES
    assert refusal["cumulative_charged_response_bytes"] == recovery.PARENT_CHARGED_BYTES + 2 * recovery.parallel.MAXIMUM_RESPONSE_BYTES
    assert not (directory / "child.completed.json").exists()


def test_unreceipted_earlier_ordinal_is_not_lost_behind_later_receipt(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path)
    first = next(value[2].child_plan._queries.iter_queries()).to_payload()["query_asof_date"]
    original_http = value[4]["http"]

    def http(opener, request, maximum):
        threading.current_thread().bad_count_clock = "date=" + first in request.full_url
        return original_http(opener, request, maximum)

    class OneInvalidClock(Clock):
        def __call__(self):
            if getattr(threading.current_thread(), "bad_count_clock", False):
                return "fabricated-invalid-worker-clock"
            return super().__call__()

    value[4].update(clock=OneInvalidClock(), http=http)
    assert execute(value) is None
    refusal = json.loads((value[1] / "run.refused.json").read_bytes())
    assert value[5]["http"] == 2
    assert len(list(value[1].glob("query-*.received.json"))) == 1
    assert any(entry["query_ordinal"] == 1 for entry in refusal["unreceipted_diagnostics"])


def test_partial_raw_publication_cannot_claim_completion(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path)
    original = recovery._OwnedOutput.publish

    def partial(self, name, raw, **kwargs):
        if name == "query-00000001.raw":
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=self._anchor[2])
            try:
                os.write(fd, b"fabricated-partial")
            finally:
                os.close(fd)
            raise OSError("fabricated-partial-publication")
        return original(self, name, raw, **kwargs)

    monkeypatch.setattr(recovery._OwnedOutput, "publish", partial)
    with pytest.raises(recovery.RecoveryRefusal):
        execute(value)
    assert (value[1] / "query-00000001.raw").read_bytes() == b"fabricated-partial"
    assert (value[1] / "run.refused.json").exists()
    assert not (value[1] / "child.completed.json").exists()


def test_output_directory_swap_refuses_without_redirecting_raw(monkeypatch, tmp_path):
    value = runtime(monkeypatch, tmp_path)
    directory = value[1]
    original = recovery._OwnedOutput.publish

    def swapped(self, name, raw, **kwargs):
        if name == "query-00000001.started.json":
            directory.rename(directory.with_name("held-child"))
            directory.mkdir(mode=0o700)
        return original(self, name, raw, **kwargs)

    monkeypatch.setattr(recovery._OwnedOutput, "publish", swapped)
    with pytest.raises(Exception):
        execute(value)
    assert value[5]["http"] == 0
    assert not list(directory.glob("query-*.raw"))


def test_bad_committed_code_manifest_refuses_before_cache_or_key(monkeypatch):
    calls = {"cache": 0}
    monkeypatch.setattr(recovery, "_require_capture_platform", lambda: None)
    fake = type("FakeGuard", (), {"refresh": lambda self: None})
    monkeypatch.setattr(recovery.lane, "LaneGuard", lambda *args, **kwargs: fake())
    with pytest.raises(recovery.RecoveryRefusal, match="complete_current_code_manifest"):
        recovery.run_registered(recovery.lane.ROOT, runtime_head="a" * 40,
            actual_remote="a" * 40, complete_code_manifest={})
    assert recovery.DRIVER_PATH in recovery.expected_code_paths()
    assert set(recovery.cache.COUNT_CODE_FILES) <= set(recovery.expected_code_paths())
    assert calls["cache"] == 0
