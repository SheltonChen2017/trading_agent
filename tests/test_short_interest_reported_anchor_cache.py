"""Owned disposable cache custody; no actual sources, keys or provider I/O."""
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

from data.hashing import hash_bytes
import scripts.continue_short_interest_native_identity as capture
import scripts.short_interest_reported_anchor_cache as m

SPEC = importlib.util.spec_from_file_location("owned_anchor_cache_fixtures", Path(__file__).with_name("test_short_interest_native_reported_anchor_cache.py"))
f = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = f
SPEC.loader.exec_module(f)
HEAD, CODE = "d" * 40, "e" * 64


def prepared(monkeypatch):
    source = f.fixture(monkeypatch, events=("2023-02-01,split,SYN,Source split,2,,\n",))
    value = m.prepare_cache(source[0], runtime_head=HEAD, cache_code_identity_sha256=CODE,
            completed_at="2026-10-14T04:00:00Z")
    monkeypatch.setattr(m.contract, "REGISTERED_CLOSURE_SHA256", value.closure_sha256)
    return source, value


def directory(tmp_path):
    parent = tmp_path.resolve() / "owned"
    parent.mkdir(mode=0o700)
    target = parent / "cache"
    target.mkdir(mode=0o700)
    return target


def test_fixed_four_physical_files_keep_every_logical_event_bytes_and_digest(monkeypatch):
    source, candidate = prepared(monkeypatch)
    files = dict(candidate.iter_files())
    assert len(files) == 5 and set(files) == {*m.PHYSICAL_NAMES, "closure.private.json"}
    events = m.unpack_events(files["events.private.bin"])
    assert events == source[2][3:]
    proof = m.contract.verify_closure(files["closure.private.json"])
    rebuilt = m.contract.rebuild_anchor_plan(source[1], *(files[name] for name in m.PHYSICAL_NAMES[:3]),
            events, source[3], source[4], closure=proof)
    assert rebuilt.sha256 == source[0].sha256


@pytest.mark.parametrize("raw", [b"", b"bad", m.MAGIC, m.MAGIC + b"\x01" * 8,
        m.pack_events(()) + b"extra", m.MAGIC + b"\x01\x00\x00\x00\x00\x00\x00\x00"])
def test_event_frame_magic_length_count_and_trailing_bytes_refuse(raw):
    with pytest.raises(m.contract.AnchorCacheRefusal):
        m.unpack_events(raw)


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="physical POSIX cache custody")
def test_exclusive_owned_cache_roundtrip_reloads_without_original_identity_reports(monkeypatch, tmp_path):
    source, candidate = prepared(monkeypatch)
    target, checks = directory(tmp_path), []
    with capture._OwnedOutput(target, lambda: None) as owned:
        m.publish_owned_cache(candidate, owned, boundary=lambda: checks.append("whole_file_boundary"))
        rebuilt = m.reload_owned_cache(owned, source[1], source[3], source[4], boundary=lambda: checks.append("whole_file_boundary"),
                expected_runtime_head=HEAD, expected_cache_code_identity_sha256=CODE)
        assert rebuilt.sha256 == source[0].sha256 and rebuilt._matrix is source[1]
        assert checks and all(path.stat().st_mode & 0o777 == 0o600 for path in target.iterdir())
        before = {path.name: hash_bytes(path.read_bytes()) for path in target.iterdir()}
        with pytest.raises(m.contract.AnchorCacheRefusal, match="empty_new"):
            m.publish_owned_cache(candidate, owned, boundary=lambda: None)
        assert before == {path.name: hash_bytes(path.read_bytes()) for path in target.iterdir()}


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"), reason="physical POSIX cache custody")
@pytest.mark.parametrize("drift", ["part", "mode", "symlink", "extra", "wrong_code", "wrong_head"])
def test_cache_custody_code_or_inventory_mutation_refuses_before_sealed_plan(monkeypatch, tmp_path, drift):
    source, candidate = prepared(monkeypatch)
    target = directory(tmp_path)
    with capture._OwnedOutput(target, lambda: None) as owned:
        m.publish_owned_cache(candidate, owned, boundary=lambda: None)
        selected = target / "cells.private.bin"
        if drift == "part":
            selected.write_bytes(selected.read_bytes() + b"x")
        elif drift == "mode":
            selected.chmod(0o644)
        elif drift == "symlink":
            selected.rename(target / "original.bin")
            selected.symlink_to(target / "original.bin")
        elif drift == "extra":
            (target / "extra.json").write_bytes(b"{}")
        with pytest.raises((m.contract.AnchorCacheRefusal, capture.ContinuationRefusal,
                m.protected.replay.CompletedIdentityRefusal, OSError)):
            m.reload_owned_cache(owned, source[1], source[3], source[4], boundary=lambda: None,
                    expected_runtime_head="f" * 40 if drift == "wrong_head" else HEAD,
                    expected_cache_code_identity_sha256="f" * 64 if drift == "wrong_code" else CODE)


def test_bool_plan_candidate_or_completion_flag_cannot_bypass_prepare_or_reload(monkeypatch):
    source, candidate = prepared(monkeypatch)
    with pytest.raises(m.contract.AnchorCacheRefusal):
        m.prepare_cache(True, runtime_head=HEAD, cache_code_identity_sha256=CODE, completed_at="2026-10-14T04:00:00Z")
    with pytest.raises(m.contract.AnchorCacheRefusal):
        m.publish_owned_cache(candidate, True, boundary=lambda: None)


def test_candidate_reflection_cannot_replace_observed_plan_or_private_part_bytes(monkeypatch):
    source, candidate = prepared(monkeypatch)
    object.__setattr__(candidate, "_closure", b"{}")
    with pytest.raises(m.contract.AnchorCacheRefusal):
        tuple(candidate.iter_files())
