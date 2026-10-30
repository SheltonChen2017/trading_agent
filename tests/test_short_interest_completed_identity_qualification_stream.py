"""Verified-byte stream tests; original/child lineage is entirely fabricated."""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_dated_identity as identities
import scripts.continue_short_interest_native_identity as capture
import scripts.stream_short_interest_native_identity_continuation as m
import scripts.preflight_short_interest_native_reported_anchors as preflight

SPEC = importlib.util.spec_from_file_location("completed_stream_fixtures",
        Path(__file__).with_name("test_short_interest_completed_identity_continuation.py"))
f = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = f
SPEC.loader.exec_module(f)
ASPEC = importlib.util.spec_from_file_location("completed_stream_anchor_fixtures",
        Path(__file__).with_name("test_short_interest_native_reported_anchor_plan.py"))
af = importlib.util.module_from_spec(ASPEC)
sys.modules[ASPEC.name] = af
ASPEC.loader.exec_module(af)


def positive_replayed():
    files, parent_args = f.helpers.fixture()
    archive = af.tickers()
    parent_args["index"] = identities.build_composite_native_index(archive)
    row = {"ticker": "SYN", "composite_figi": af.COMPOSITE, "share_class_figi": af.CLASS,
           "locale": "us", "market": "stocks", "type": "CS", "active": True, "primary_exchange": "XNYS"}
    for name in list(files):
        if name.endswith(".raw") and "active-page" in name and "inactive-page" not in name:
            value = json.loads(files[name])
            value["results"] = [row]
            files[name] = canonical_json(value).encode()
            received_name = name.removesuffix(".raw") + ".received.json"
            value = json.loads(files[received_name])
            value.update(raw_sha256=hash_bytes(files[name]), raw_bytes=len(files[name]))
            files[received_name] = canonical_json(value).encode()
    old_pages = tuple(identities.CapturedDatedIdentityPage(f.helpers.DATES[0], active, 1,
            capture.initial_url(f.helpers.DATES[0], active), files[capture.prefix(1, active, 1) + ".raw"],
            f.helpers.NOW, f.helpers.NOW, 200, "application/json") for active in (True, False))
    files["date-001.qualified.private.json"] = identities.qualify_dated_identity(old_pages, parent_args["index"],
            query_date=f.helpers.DATES[0], started_at=f.helpers.NOW, retrieved_at=f.helpers.NOW).to_bytes()
    source = capture.verify_parent(files, **f.helpers.repin(files, parent_args))
    h = f.helpers.Harness(source)
    def reply(call, key, bound):
        # The resumed first date's old partial already contains its exact row.
        selected = [row] if call["url"] == capture.initial_url(f.helpers.DATES[2], True) else []
        return canonical_json({"status": "OK", "results": selected}).encode(), "application/json", 200
    h.reply = reply
    code = hash_payload({"git_commit": f.helpers.NEW_HEAD, "files": [
        {"path": name, "sha256": hash_bytes(f.helpers.historical(f.helpers.NEW_HEAD, name))}
        for name in capture.CODE_FILES]})
    h.run(code_identity_sha256=code)
    state = source.payload()
    budget = {**h.claims[0][1], "schema": "si-native-identity-manual-continuation-budget-v1",
            "run_id": "fabricated-child", "remote_head": "1" * 40,
            "source_inventory_sha256": state["source_inventory_sha256"],
            "failed_start_bytes_sha256": state["failed_start_bytes_sha256"],
            "credential_item": capture.freeze_protocol(source)["credential_item"],
            "unused_parent_slots_repurposable": False}
    args = f.repin(h.saved, dict(budget_raw=canonical_json(budget).encode(),
            budget_sha256=hash_payload(budget), expected_head=f.helpers.NEW_HEAD,
            expected_protocol_sha256=hash_payload(capture.freeze_protocol(source)),
            expected_code_identity_sha256=code, historical_code=f.helpers.historical,
            local_guard=lambda: None, expected_run_id="fabricated-child", expected_remote_head="1" * 40))
    replayed = m.base.replay.verify_completed_continuation(source, h.saved, **args)
    return replayed, files, h, archive


def test_qualified_stream_preserves_original_and_child_dates_bytes_and_receipt_clocks():
    replayed, old, child, archive = positive_replayed()
    reads, guards = [], []
    def original(name):
        reads.append(name)
        return old[name]
    values = list(m.iter_qualified_dates(replayed, read_original=original, guard=lambda: guards.append("guard")))
    assert reads == ["date-001.qualified.private.json"]
    assert [item.to_payload()["query_date"] for item in values] == list(f.helpers.DATES)
    assert all(type(item) is identities.DatedIdentityQualification for item in values)
    assert values[0].to_bytes() == old[reads[0]]
    assert values[1].to_bytes() == child.saved["date-002.qualified.private.json"]
    assert all(item.to_payload()["started_at"] == f.helpers.NOW for item in values)
    assert all(item.to_payload()["authority"]["ready_for_empirical_backtest"] is False for item in values)
    assert guards


@pytest.mark.parametrize("kind", ["old_bytes", "child_bytes", "rogue_entry", "caller_flag", "untyped_replay"])
def test_no_raw_file_or_boolean_can_manufacture_qualification_authority(kind):
    replayed, old, child, archive = positive_replayed()
    if kind == "old_bytes":
        old["date-001.qualified.private.json"] += b" "
    elif kind == "child_bytes":
        child.saved["date-002.qualified.private.json"] += b" "
    elif kind == "rogue_entry":
        entry = replayed.payload()["old_reports"][0]
        entry["retrieved_at"] = "2026-10-14T05:00:00Z"
        with pytest.raises(m.base.replay.CompletedIdentityRefusal):
            m._qualification(replayed, entry, old["date-001.qualified.private.json"])
        return
    else:
        replayed = True if kind == "caller_flag" else replayed.payload()
    with pytest.raises((m.base.replay.CompletedIdentityRefusal, capture.ContinuationRefusal)):
        list(m.iter_qualified_dates(replayed, read_original=lambda name: old[name], guard=lambda: None))


def test_stream_rechecks_runtime_guard_before_each_original_source_read():
    replayed, old, child, archive = positive_replayed()
    calls = []
    def guard():
        raise capture.ContinuationRefusal("runtime_branch_changed")
    with pytest.raises(capture.ContinuationRefusal):
        next(m.iter_qualified_dates(replayed, read_original=lambda name: calls.append(name), guard=guard))
    assert not calls


def test_source_only_anchor_preflight_consumes_all_dates_and_single_matrix_load(monkeypatch):
    replayed, old, child, archive = positive_replayed()
    matrix = af.matrix(tuple(("SYN", at) for at in f.helpers.DATES))
    calls = []
    @contextmanager
    def load(*args, **kwargs):
        yield replayed, m.iter_qualified_dates(replayed, read_original=lambda name: old[name], guard=lambda: None)
    monkeypatch.setattr(preflight, "load_batched_for_current_runtime", load)
    monkeypatch.setattr(capture, "_require_capture_platform", lambda: None)
    monkeypatch.setattr(capture, "_local", lambda *args: calls.append("local"))
    def matrix_once(*args, **kwargs):
        calls.append("matrix")
        return matrix
    monkeypatch.setattr(preflight.matrix_reader, "load_matrix", matrix_once)
    monkeypatch.setattr(preflight.finalizer, "_reload", lambda root: ((archive, af.actions(), af.dictionary()), f.helpers.NOW))
    monkeypatch.setattr(preflight.native_builder, "_source_index", lambda *args: None)
    plan, summary = preflight.preflight(m.base.ROOT, runtime_head="b" * 40, actual_remote="1" * 40)
    assert calls.count("matrix") == 1 and summary["plan_sha256"] == plan.sha256
    assert summary["request_budget"] == 1
    assert len(plan.header()["identity_source_pins"]) == 3
    assert summary["capture_code_and_request_protocol"] == "pending_prospective_freeze"
    assert summary["source_admitted"] is False and summary["ready_for_empirical_backtest"] is False
    assert all(summary[name] == 0 for name in ("provider_requests", "credential_reads", "outcome_looks", "qc_attempts"))
    assert "rows" not in summary and "class_labels" not in summary


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="physical POSIX FD custody")
def test_future_runtime_guard_never_changes_historical_child_head_or_source_budget_remote(tmp_path, monkeypatch):
    replayed, old, h, archive = positive_replayed()
    payload = replayed.payload()
    root = tmp_path.resolve()
    child, original = root / "child" / "run", root / capture.SOURCE
    child.mkdir(parents=True, mode=0o700)
    original.mkdir(parents=True, mode=0o700)
    child.parent.chmod(0o700)
    original.parent.chmod(0o700)
    def write(path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)
    for name, raw in h.saved.items():
        write(child / name, raw)
    for entry in payload["old_reports"]:
        write(original / entry["report_path"], old[entry["report_path"]])
    state = h.source.payload()
    claim_id = hash_payload({"source_inventory_sha256": state["source_inventory_sha256"],
            "failed_request_sha256": state["failed_request_sha256"],
            "failed_start_bytes_sha256": state["failed_start_bytes_sha256"],
            "purpose": "single_explicit_native_identity_manual_continuation"})
    budget = {**h.claims[0][1], "schema": "si-native-identity-manual-continuation-budget-v1",
            "run_id": "fabricated-child", "remote_head": "1" * 40,
            "source_inventory_sha256": state["source_inventory_sha256"],
            "failed_start_bytes_sha256": state["failed_start_bytes_sha256"],
            "credential_item": capture.freeze_protocol(h.source)["credential_item"],
            "unused_parent_slots_repurposable": False}
    write(child.parent / ("budget-" + claim_id + ".json"), canonical_json(budget).encode())
    anchors = {"aggregate_inventory_sha256": payload["child_inventory_sha256"],
            "budget_bytes_sha256": hash_payload(budget), "code_identity_sha256": payload["child_code_identity_sha256"],
            "protocol_bytes_sha256": hash_bytes(h.saved["protocol.private.json"]),
            "started_bytes_sha256": hash_bytes(h.saved["started.json"]),
            "completed_bytes_sha256": hash_bytes(h.saved["completed.json"]),
            "inventory_bytes_sha256": hash_bytes(h.saved["inventory.private.json"])}
    monkeypatch.setattr(m.base, "ROOT", root)
    monkeypatch.setattr(m.base, "HEAD", f.helpers.NEW_HEAD)
    monkeypatch.setattr(m.base, "REMOTE", "1" * 40)
    monkeypatch.setattr(m.base, "RUN_ID", "fabricated-child")
    monkeypatch.setattr(m.base, "CHILD", child.relative_to(root))
    monkeypatch.setattr(m.base, "FILE_COUNT", len(h.saved))
    monkeypatch.setattr(m.base, "ANCHORS", anchors)
    local_heads, remote_heads, git_calls, code_calls = [], [], [], []
    monkeypatch.setattr(capture, "_local", lambda root, head: local_heads.append(head))
    monkeypatch.setattr(capture, "_guard_remote", lambda root, remote: remote_heads.append(remote))
    monkeypatch.setattr(capture, "load_parent", lambda root, head: h.source)
    def git(root, *args):
        git_calls.append(args)
        return ""
    monkeypatch.setattr(capture, "_git", git)
    def historical(command, **kwargs):
        code_calls.append(command)
        commit, name = command[-1].split(":", 1)
        return type("Result", (), {"returncode": 0, "stdout": f.helpers.historical(commit, name)})()
    monkeypatch.setattr(m.subprocess, "run", historical)
    with m.load_for_current_runtime(root, runtime_head="b" * 40, actual_remote="2" * 40) as (verified, dates):
        assert len(list(dates)) == 3
        assert verified.payload()["child_head"] == f.helpers.NEW_HEAD
    assert set(local_heads) == {"b" * 40} and set(remote_heads) == {"2" * 40}
    assert git_calls == [("merge-base", "--is-ancestor", f.helpers.NEW_HEAD, "b" * 40)]
    assert all(command[-1].startswith(f.helpers.NEW_HEAD + ":") for command in code_calls)
