"""Disposable fabricated POSIX custody, never an actual source artifact."""
import importlib.util
import os
from pathlib import Path
import sys

import pytest

from data.hashing import hash_bytes, hash_payload
import scripts.continue_short_interest_native_identity as capture

import scripts.load_short_interest_native_identity_continuation as m
FIXTURE_SPEC = importlib.util.spec_from_file_location("completed_identity_protected_loader_fixtures",
        Path(__file__).with_name("test_short_interest_completed_identity_continuation.py"))
f = importlib.util.module_from_spec(FIXTURE_SPEC)
sys.modules[FIXTURE_SPEC.name] = f
FIXTURE_SPEC.loader.exec_module(f)


def directory(tmp_path):
    parent = tmp_path.resolve() / "owned"
    parent.mkdir(mode=0o700)
    child = parent / "run"
    child.mkdir(mode=0o700)
    return parent, child


def write(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="physical POSIX FD custody")
def test_retained_directoryFD_reads_bound0600_child_and_parent_only(tmp_path):
    parent, child = directory(tmp_path)
    write(child / "sample.raw", b"fabricated")
    write(parent / "budget.json", b"{}")
    with capture._OwnedOutput(child, lambda: None) as owned:
        assert m.read_owned_source(owned, "sample.raw", 32) == b"fabricated"
        assert m.read_owned_source(owned, "budget.json", 32, parent=True) == b"{}"
        with pytest.raises(m.replay.CompletedIdentityRefusal):
            m.read_owned_source(owned, "../budget.json", 32)


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="physical POSIX FD custody")
@pytest.mark.parametrize("change", ["mode", "symlink", "hardlink", "size", "directory_mode", "directory_swap"])
def test_protected_reader_refuses_symlinks_links_bounds_and_directory_drift(tmp_path, change):
    parent, child = directory(tmp_path)
    target = child / "sample.raw"
    write(target, b"fabricated")
    with capture._OwnedOutput(child, lambda: None) as owned:
        if change == "mode":
            target.chmod(0o644)
        elif change == "symlink":
            target.rename(child / "original.raw")
            target.symlink_to(child / "original.raw")
        elif change == "hardlink":
            os.link(target, child / "another.raw")
        elif change == "directory_mode":
            child.chmod(0o755)
        elif change == "directory_swap":
            child.rename(parent / "old")
            child.mkdir(mode=0o700)
            write(child / "sample.raw", b"replacement")
        with pytest.raises((m.replay.CompletedIdentityRefusal, capture.ContinuationRefusal, OSError)):
            m.read_owned_source(owned, "sample.raw", 2 if change == "size" else 32)


def test_unsupported_host_is_first_before_lane_private_metadata_or_parent(monkeypatch):
    events = []
    def unsupported():
        events.append("host")
        raise capture.ContinuationRefusal("unsupported_host")
    monkeypatch.setattr(capture, "_require_capture_platform", unsupported)
    monkeypatch.setattr(capture, "load_parent", lambda *args, **kwargs: events.append("private"))
    with pytest.raises(capture.ContinuationRefusal):
        with m.load_protected_completed(m.ROOT, head=m.HEAD, remote=m.REMOTE):
            pass
    assert events == ["host"]


def test_pending_registration_refuses_before_private_parent_or_remote(monkeypatch):
    events = []
    monkeypatch.setattr(capture, "_require_capture_platform", lambda: events.append("host"))
    monkeypatch.setattr(capture, "_local", lambda *args: events.append("local"))
    monkeypatch.setattr(capture, "load_parent", lambda *args, **kwargs: events.append("private"))
    monkeypatch.setattr(capture, "_guard_remote", lambda *args: events.append("remote"))
    monkeypatch.setattr(m, "ANCHORS", {name: "PENDING" for name in m.ANCHORS})
    with pytest.raises(m.replay.CompletedIdentityRefusal):
        with m.load_protected_completed(m.ROOT, head=m.HEAD, remote=m.REMOTE):
            pass
    assert events == ["host", "local"]


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="physical POSIX FD custody")
def test_protected_adapter_replays_only_fabricated_registered_child_and_code(tmp_path, monkeypatch):
    h, args = f.fixture()
    parent, child = directory(tmp_path)
    for name, raw in h.saved.items():
        write(child / name, raw)
    state = h.source.payload()
    claim_id = hash_payload({"source_inventory_sha256": state["source_inventory_sha256"],
            "failed_request_sha256": state["failed_request_sha256"],
            "failed_start_bytes_sha256": state["failed_start_bytes_sha256"],
            "purpose": "single_explicit_native_identity_manual_continuation"})
    write(parent / ("budget-" + claim_id + ".json"), args["budget_raw"])
    anchors = {"aggregate_inventory_sha256": args["inventory_sha256"], "budget_bytes_sha256": args["budget_sha256"],
            "code_identity_sha256": args["expected_code_identity_sha256"],
            "protocol_bytes_sha256": hash_bytes(h.saved["protocol.private.json"]),
            "started_bytes_sha256": hash_bytes(h.saved["started.json"]),
            "completed_bytes_sha256": hash_bytes(h.saved["completed.json"]),
            "inventory_bytes_sha256": hash_bytes(h.saved["inventory.private.json"])}
    monkeypatch.setattr(m, "ROOT", tmp_path.resolve())
    monkeypatch.setattr(m, "CHILD", child.relative_to(tmp_path.resolve()))
    monkeypatch.setattr(m, "HEAD", args["expected_head"])
    monkeypatch.setattr(m, "REMOTE", args["expected_remote_head"])
    monkeypatch.setattr(m, "RUN_ID", args["expected_run_id"])
    monkeypatch.setattr(m, "FILE_COUNT", len(h.saved))
    monkeypatch.setattr(m, "ANCHORS", anchors)
    monkeypatch.setattr(capture, "EXPECTED_PROTOCOL_SHA256", args["expected_protocol_sha256"])
    events, commands = [], []
    monkeypatch.setattr(capture, "_local", lambda *args: events.append("local"))
    monkeypatch.setattr(capture, "_guard_remote", lambda *args: events.append("remote"))
    monkeypatch.setattr(capture, "load_parent", lambda *args, **kwargs: h.source)
    def code(command, **kwargs):
        commands.append(command)
        commit, name = command[-1].split(":", 1)
        return type("Result", (), {"returncode": 0, "stdout": args["historical_code"](commit, name)})()
    monkeypatch.setattr(m.subprocess, "run", code)
    with m.load_protected_completed(m.ROOT, head=m.HEAD, remote=m.REMOTE) as result:
        assert result.payload()["new_attempts"] == 4
        assert len(list(result.iter_new_reports())) == 2
    assert len(commands) == len(capture.CODE_FILES)
    assert all(call[:2] == ["git", "show"] and call[-1].startswith(m.HEAD + ":") for call in commands)
    assert events.count("remote") == 2
