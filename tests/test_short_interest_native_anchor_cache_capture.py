"""Concrete composition exercised only with fabricated protected files."""
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

from data.hashing import canonical_json, hash_bytes, hash_payload
import scripts.capture_short_interest_native_anchor_cache as m

SPEC = importlib.util.spec_from_file_location("cache_round_source_fixtures",
        Path(__file__).with_name("test_short_interest_native_reported_anchor_plan.py"))
f = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = f
SPEC.loader.exec_module(f)
CREATOR, CURRENT = "a" * 40, "b" * 40
REMOTE = "c" * 40


def protected(path, raw, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)  # Only this test's disposable fabricated parent.
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def source(monkeypatch):
    dates = ("2023-01-13", "2023-04-14", "2023-07-14")
    matrix = f.matrix([("SYN", day) for day in dates])
    archives = f.tickers(), f.actions(), f.dictionary()
    plan = m.contract.reported.build_native_reported_anchor_plan(matrix,
            tuple(f.identity(day) for day in dates), archives[1], archives[2])
    monkeypatch.setattr(m.contract, "KNOWN", {**m.contract.KNOWN, "plan_sha256": plan.sha256,
            "request_budget": plan.header()["exact_request_budget"], "matrix_sha256": matrix.sha256,
            "date_count": len(dates)})
    summary = {"schema": "si-native-full-identity-anchor-preflight-v1", "status": "source_only_plan_preflight",
        "plan_sha256": plan.sha256, "request_budget": plan.header()["exact_request_budget"],
        "source_pins": {"original_archive_sha256": {archive.table: hash_bytes(archive.raw) for archive in archives},
            "matrix_sha256": matrix.sha256, "parent_inventory_sha256": m.contract.KNOWN["parent_inventory_sha256"],
            "child_inventory_sha256": m.contract.KNOWN["child_inventory_sha256"],
            "child_budget_bytes_sha256": m.contract.KNOWN["child_budget_sha256"], "report_inventory_sha256": "e" * 64},
        "capture_code_and_request_protocol": "pending_prospective_freeze", "source_admitted": False,
        "ready_for_empirical_backtest": False, "provider_requests": 0, "credential_reads": 0,
        "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}
    return plan, matrix, archives, summary


class Guard:
    def __init__(self):
        self.checks, self.remotes = 0, 0
    def check(self):
        self.checks += 1
    def refresh(self):
        self.checks += 1
        self.remotes += 1


def fixture(monkeypatch, tmp_path):
    plan, matrix, archives, summary = source(monkeypatch)
    root = tmp_path.resolve()
    guard, calls = Guard(), {"preflight": 0, "matrix": 0, "master": 0, "git": []}
    monkeypatch.setattr(m, "_require_capture_platform", lambda: None)
    monkeypatch.setattr(m.lane, "LaneGuard", lambda *args, **kwargs: guard)
    monkeypatch.setattr(m, "TARGET", Path("cache/cache-draft"))
    monkeypatch.setattr(m, "WRITER_CODE_FILES", ("code.py",))
    monkeypatch.setattr(m, "COUNT_CODE_FILES", ("code.py",))
    monkeypatch.setattr(m.finalizer, "SOURCE", Path("master/original"))
    monkeypatch.setattr(m.finalizer, "_source_names", lambda: ("attempt-08.raw", "attempt-10.raw", "attempt-12.raw"))
    monkeypatch.setattr(m.matrix_reader, "SOURCE", Path("matrix/original"))
    monkeypatch.setattr(m.matrix_reader, "FILE_PINS", {"bound.private.bin": "f" * 64})
    protected(root / "code.py", b"fabricated committed code\n", mode=0o644)
    for name, archive in zip(m.finalizer._source_names(), archives):
        protected(root / m.finalizer.SOURCE / name, archive.raw)
    protected(root / m.finalizer.SOURCE.parent / ("budget-" + m.finalizer.master.PROTOCOL_SHA256 + ".json"), b"{}")
    protected(root / m.matrix_reader.SOURCE / "bound.private.bin", b"fabricated source bytes")
    def git(root, arguments, current_guard):
        calls["git"].append(tuple(arguments))
        assert current_guard is guard
        if arguments[0] == "check-ignore":
            return (arguments[1] + "\n").encode()
        if arguments[:2] == ["merge-base", "--is-ancestor"]:
            return b""
        assert arguments[0] == "show" and arguments[1].endswith(":code.py")
        return b"fabricated committed code\n"
    monkeypatch.setattr(m, "_git", git)
    def preflight(*args, **kwargs):
        calls["preflight"] += 1
        return plan, summary
    def matrix_load(*args, **kwargs):
        calls["matrix"] += 1
        return matrix
    def master_load(*args, **kwargs):
        calls["master"] += 1
        return archives, "2023-01-01T00:00:00Z"
    monkeypatch.setattr(m.source_preflight, "preflight", preflight)
    monkeypatch.setattr(m.matrix_reader, "load_matrix", matrix_load)
    monkeypatch.setattr(m.finalizer, "_reload", master_load)
    monkeypatch.setattr(m, "_utc_now", lambda: "2026-10-14T05:00:00Z")
    monkeypatch.setattr(m, "WRITER_PROTOCOL_SHA256", hash_payload(m.writer_protocol()))
    return root, plan, matrix, archives, summary, calls, guard


def register(monkeypatch, result):
    monkeypatch.setattr(m, "REGISTERED_CACHE_PATH", str(m.TARGET))
    monkeypatch.setattr(m, "REGISTERED_CREATOR_HEAD", result["creator_head"])
    monkeypatch.setattr(m, "REGISTERED_CREATOR_CODE_SHA256", result["creator_code_sha256"])
    monkeypatch.setattr(m.contract, "REGISTERED_CLOSURE_SHA256", result["closure_sha256"])


def test_writer_once_reader_once_retained_fd_checks_do_not_replay_or_rehash_parts(monkeypatch, tmp_path):
    root, plan, matrix, archives, summary, calls, guard = fixture(monkeypatch, tmp_path)
    result = m.write_cache(root, runtime_head=CREATOR, actual_remote=REMOTE)
    assert calls["preflight"] == 1 and calls["matrix"] == calls["master"] == 0
    assert len(list((root / m.TARGET).iterdir())) == 5 and result["provider_requests"] == 0
    register(monkeypatch, result)
    with m.load_registered_cache(root, runtime_head=CURRENT, actual_remote=REMOTE, for_counts=True) as loaded:
        assert loaded.plan.sha256 == plan.sha256 and loaded.plan._matrix is matrix
        assert loaded.current_code_identity_sha256 != result["creator_code_sha256"]
        monkeypatch.setattr(m, "hash_bytes", lambda *args: pytest.fail("per-slot raw hash"))
        monkeypatch.setattr(m.adapter, "reload_owned_cache", lambda *args, **kwargs: pytest.fail("per-slot source replay"))
        for _ in range(50):
            loaded.source_custody()
            loaded.code_custody()
    assert calls["preflight"] == calls["matrix"] == calls["master"] == 1
    assert ("merge-base", "--is-ancestor", CREATOR, CURRENT) in calls["git"]


def test_duplicate_exclusive_target_refuses_before_twenty_minute_preflight(monkeypatch, tmp_path):
    root, plan, matrix, archives, summary, calls, guard = fixture(monkeypatch, tmp_path)
    m.write_cache(root, runtime_head=CREATOR, actual_remote=REMOTE)
    before = {path.name: hash_bytes(path.read_bytes()) for path in (root / m.TARGET).iterdir()}
    with pytest.raises((FileExistsError, ValueError)):
        m.write_cache(root, runtime_head=CREATOR, actual_remote=REMOTE)
    assert calls["preflight"] == 1
    assert before == {path.name: hash_bytes(path.read_bytes()) for path in (root / m.TARGET).iterdir()}


def test_held_cache_inventory_cannot_gain_unbound_sixth_file_between_count_slots(monkeypatch, tmp_path):
    root, plan, matrix, archives, summary, calls, guard = fixture(monkeypatch, tmp_path)
    register(monkeypatch, m.write_cache(root, runtime_head=CREATOR, actual_remote=REMOTE))
    with m.load_registered_cache(root, runtime_head=CURRENT, actual_remote=REMOTE) as loaded:
        protected(root / m.TARGET / "unbound.private.bin", b"fabricated")
        with pytest.raises(m.contract.AnchorCacheRefusal, match="exact_five_file"):
            loaded.source_custody()


@pytest.mark.parametrize("kind", ["cache", "master", "code", "matrix"])
def test_held_file_change_refuses_before_next_slot_without_any_source_reload(monkeypatch, tmp_path, kind):
    root, plan, matrix, archives, summary, calls, guard = fixture(monkeypatch, tmp_path)
    register(monkeypatch, m.write_cache(root, runtime_head=CREATOR, actual_remote=REMOTE))
    with pytest.raises(m.contract.AnchorCacheRefusal, match="held_custody_file_changed"):
        with m.load_registered_cache(root, runtime_head=CURRENT, actual_remote=REMOTE) as loaded:
            path = {"cache": root / m.TARGET / "cells.private.bin", "master": root / m.finalizer.SOURCE / "attempt-10.raw",
                    "code": root / "code.py", "matrix": root / m.matrix_reader.SOURCE / "bound.private.bin"}[kind]
            path.write_bytes(path.read_bytes() + b"changed")
            loaded.source_custody()
            loaded.code_custody()


@pytest.mark.parametrize("kind", ["head", "code", "closure", "path"])
def test_reader_pending_registration_refuses_before_protected_file_access(monkeypatch, kind):
    monkeypatch.setattr(m, "_require_capture_platform", lambda: None)
    # Exercise each individual pending field; do not rely on the live module
    # still having every default pending after its first qualified cache.
    target, name = {
        "head": (m, "REGISTERED_CREATOR_HEAD"),
        "code": (m, "REGISTERED_CREATOR_CODE_SHA256"),
        "closure": (m.contract, "REGISTERED_CLOSURE_SHA256"),
        "path": (m, "REGISTERED_CACHE_PATH"),
    }[kind]
    monkeypatch.setattr(target, name, "PENDING")
    monkeypatch.setattr(m.lane, "LaneGuard", lambda *args, **kwargs: pytest.fail("private preflight reached"))
    with pytest.raises(m.contract.AnchorCacheRefusal, match="registration_pending"):
        with m.load_registered_cache(None, runtime_head=CURRENT, actual_remote=REMOTE):
            pytest.fail("unregistered source yielded")


@pytest.mark.parametrize("mode", ["replace", "symlink", "mode", "hardlink", "parent_mode"])
def test_fd_inode_mode_link_or_directory_swap_is_fixed_refusal(monkeypatch, tmp_path, mode):
    monkeypatch.setattr(m, "_require_capture_platform", lambda: None)
    path = protected(tmp_path.resolve() / "owned" / "bound.bin", b"fabricated")
    with m.HeldFiles((path,), protected=True, boundary=lambda: None) as held:
        if mode == "replace":
            path.rename(path.with_name("old.bin"))
            protected(path, b"fabricated")
        elif mode == "symlink":
            path.rename(path.with_name("old.bin"))
            path.symlink_to(path.with_name("old.bin"))
        elif mode == "mode":
            path.chmod(0o644)
        elif mode == "hardlink":
            os.link(path, path.with_name("alias.bin"))
        else:
            path.parent.chmod(0o755)
        with pytest.raises(m.contract.AnchorCacheRefusal, match="held_custody"):
            held.check()


def test_failed_file_protection_constructor_closes_every_created_fd(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "_require_capture_platform", lambda: None)
    path = protected(tmp_path.resolve() / "owned" / "bound.bin", b"fabricated", mode=0o644)
    original_open, original_close, active = os.open, os.close, set()
    def tracked_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        active.add(fd)
        return fd
    def tracked_close(fd):
        active.discard(fd)
        return original_close(fd)
    monkeypatch.setattr(m.os, "open", tracked_open)
    monkeypatch.setattr(m.os, "close", tracked_close)
    try:
        with pytest.raises(m.contract.AnchorCacheRefusal, match="custody_file_protection"):
            m.HeldFiles((path,), protected=True, boundary=lambda: None)
        remaining = tuple(active)
    finally:
        for fd in tuple(active):
            tracked_close(fd)
    assert not remaining, "failed bounded constructor retained an unowned source FD"
