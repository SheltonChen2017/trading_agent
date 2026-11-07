"""Fabricated byte-reader performance/custody; no actual source artifacts."""
import importlib.util
import os
from pathlib import Path
import sys

import pytest

import scripts.continue_short_interest_native_identity as capture
import scripts.read_short_interest_native_identity_continuation as m

SPEC = importlib.util.spec_from_file_location("batched_reader_stream_fixtures",
        Path(__file__).with_name("test_short_interest_completed_identity_qualification_stream.py"))
previous = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = previous
SPEC.loader.exec_module(previous)


def sample(tmp_path):
    parent = tmp_path.resolve() / "owned"
    parent.mkdir(mode=0o700)
    child = parent / "run"
    child.mkdir(mode=0o700)
    raw = b"fabricated-only-byte-payload\n" * 40000
    path = child / "sample.raw"
    path.write_bytes(raw)
    path.chmod(0o600)
    return parent, child, path, raw


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="physical POSIX custody")
def test_file_boundary_batching_keeps_every_chunk_custody_check_without_Git_per_chunk(tmp_path, monkeypatch):
    parent, child, path, raw = sample(tmp_path)
    full, cheap = [], []
    original_check = capture._OwnedOutput.check
    def counted(self):
        cheap.append("fd-custody")
        return original_check(self)
    monkeypatch.setattr(capture._OwnedOutput, "check", counted)
    with capture._OwnedOutput(child, lambda: full.append("full-Git-lane")) as owned:
        full.clear()
        cheap.clear()
        assert m.base.read_owned_source(owned, "sample.raw", len(raw)) == raw
        old_full, old_cheap = len(full), len(cheap)
    with m.ReadOnlyCustody(child, lambda: full.append("full-Git-lane")) as owned:
        full.clear()
        cheap.clear()
        assert owned.read("sample.raw", len(raw)) == raw
        assert len(full) == 2 and old_full > 20
        assert len(cheap) >= old_cheap


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="physical POSIX custody")
@pytest.mark.parametrize("drift", ["file_mode", "file_bytes", "directory_mode", "directory_swap", "file_symlink"])
def test_chunk_custody_still_refuses_mode_inode_link_or_byte_change(tmp_path, monkeypatch, drift):
    parent, child, path, raw = sample(tmp_path)
    original_read, started = os.read, []
    def changed(fd, maximum):
        result = original_read(fd, maximum)
        if not started:
            started.append(True)
            if drift == "file_mode":
                path.chmod(0o644)
            elif drift == "file_bytes":
                with path.open("ab") as file:
                    file.write(b"changed")
            elif drift == "directory_mode":
                child.chmod(0o755)
            elif drift == "directory_swap":
                child.rename(parent / "original")
                child.mkdir(mode=0o700)
            else:
                path.rename(child / "original.raw")
                path.symlink_to(child / "original.raw")
        return result
    with m.ReadOnlyCustody(child, lambda: None) as owned:
        monkeypatch.setattr(os, "read", changed)
        with pytest.raises((m.base.replay.CompletedIdentityRefusal, capture.ContinuationRefusal, OSError)):
            owned.read("sample.raw", len(raw))
    assert started


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="physical POSIX custody")
def test_runtime_HEAD_change_during_read_refuses_at_boundary_before_bytes_escape(tmp_path, monkeypatch):
    parent, child, path, raw = sample(tmp_path)
    state = {"changed": False}
    def guard():
        if state["changed"]:
            raise capture.ContinuationRefusal("head_changed")
    original_read = os.read
    def changed(fd, maximum):
        result = original_read(fd, maximum)
        state["changed"] = True
        return result
    with m.ReadOnlyCustody(child, guard) as owned:
        monkeypatch.setattr(os, "read", changed)
        with pytest.raises(capture.ContinuationRefusal):
            owned.read("sample.raw", len(raw))


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="physical POSIX custody")
def test_full_guard_before_read_refuses_without_opening_source(tmp_path, monkeypatch):
    parent, child, path, raw = sample(tmp_path)
    state, reads = {"changed": False}, []
    def guard():
        if state["changed"]:
            raise capture.ContinuationRefusal("branch_changed")
    with m.ReadOnlyCustody(child, guard) as owned:
        state["changed"] = True
        monkeypatch.setattr(os, "read", lambda *args: reads.append(args))
        with pytest.raises(capture.ContinuationRefusal):
            owned.read("sample.raw", len(raw))
    assert not reads


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="physical POSIX custody")
def test_batched_adapter_keeps_exact_replay_and_current_vs_historical_HEAD_separation(tmp_path, monkeypatch):
    monkeypatch.setattr(previous.m, "load_for_current_runtime", m.load_batched_for_current_runtime)
    previous.test_future_runtime_guard_never_changes_historical_child_head_or_source_budget_remote(tmp_path, monkeypatch)
