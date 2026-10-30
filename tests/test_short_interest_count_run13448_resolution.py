"""Fabricated forensic boundaries; never opens an operational artifact/image.

Pure chronology dictionaries, ordinary temporary directories, explicit fake
native/owner/flag observations, and genuine small typed B3 models are separate
seams. They prove refusal/closure software, not exec13448 history or custody.
"""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import socket
import stat
import sys
from types import SimpleNamespace

import pytest

# The registered resolver reaches POSIX capture helpers during import; guard
# collection before loading that immutable runtime on unsupported hosts.
pytest.importorskip("fcntl", reason="the registered resolver imports POSIX descriptor custody")
pytest.importorskip("resource", reason="the registered resolver imports POSIX capture limits")

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import resolve_short_interest_count_run13448 as resolution

spec = importlib.util.spec_from_file_location("run13448_resolution_exposure_support",
    Path(__file__).with_name("test_short_interest_count_run13448_exposure.py"))
support = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = support
spec.loader.exec_module(support)


@pytest.fixture(autouse=True)
def isolated_and_external_operations_denied(monkeypatch):
    monkeypatch.setattr(resolution, "_ISSUED", {})
    monkeypatch.setattr(resolution, "_FAILED", set())
    for name, value in (("_MINTS", {}), ("_KEYS", set()), ("_FAILED", set())):
        monkeypatch.setattr(resolution.exposure_model, name, value)
    def denied(*args, **kwargs): raise AssertionError("real source/native/subprocess forbidden")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(resolution.subprocess, "run", denied)
    monkeypatch.setattr(resolution.subprocess, "check_output", denied)
    monkeypatch.setattr(resolution.volume.ctypes, "CDLL", denied)


def chronology_facts():
    """Fixed synthetic projection of registered stamp relationships only."""
    names = ("", "mount", "mount/capture", "mount/claim", *resolution.CONTAINERS, resolution.CLAIM)
    facts = {name: {"dev": 2, "ino": 1, "uid": 501, "gid": 20, "mode": stat.S_IFDIR | 0o700,
        "links": 2, "size": 64, "birth": 1, "mtime": 1, "ctime": 2, "flags": 0} for name in names}
    facts[""].update(dev=1, ino=46599617, mtime=1793115450631577606, ctime=1793115450631577606)
    facts["mount/capture"].update(ino=18, ctime=1793115453257582943)
    facts["mount/claim"].update(ino=22, ctime=1793115455474687356)
    for name, (inode, mtime, ctime) in resolution.LEAF_PINS:
        facts[name].update(ino=inode, birth=mtime, mtime=mtime, ctime=ctime)
    facts[resolution.CLAIM].update(birth=1793115455346106368, mode=stat.S_IFREG | 0o600,
        links=1, size=534, flags=2)
    return facts


def test_full_registered_chronology_is_negative_evidence_only():
    facts = chronology_facts()
    assert resolution.check_chronology(facts) is None
    assert facts["mount/claim"]["ctime"] > facts[resolution.CLAIM]["birth"]
    assert not resolution.authority()["source_dispatch_authority"]
    assert not resolution.authority()["historical_actual_counts_known"]


def test_frozen_resolution_registration_is_not_a_dispatch_or_pending_bypass(monkeypatch):
    assert resolution.PROTOCOL_SHA256 == hash_payload(resolution.policy())
    resolution.registered()
    monkeypatch.setattr(resolution, "PROTOCOL_SHA256", "PENDING")
    monkeypatch.setattr(resolution.lane, "LaneGuard", lambda *a, **k: pytest.fail("pending policy reached IO"))
    with pytest.raises(resolution.CountResolutionRefusal, match="registration_pending"):
        resolution.resolve_registered(None, runtime_head="a" * 40, actual_remote="b" * 40)
    assert resolution.authority()["source_dispatch_authority"] is False


@pytest.mark.parametrize("name,field,value", [
    ("", "ctime", 1793115455346106369),
    ("mount/capture", "ino", 99),
    ("mount/capture", "ctime", 1793115455346106369),
    ("mount/claim", "ctime", 1793115456838350716),
    ("mount/capture/starts", "ctime", 1793115452569366317),
    ("mount/capture/received", "birth", 1793115452905830000),
    ("mount/capture/responses", "links", 3),
    (resolution.CLAIM, "flags", 0), (resolution.CLAIM, "size", 533)])
def test_chronology_rejects_ancestry_leaf_and_claim_drift(name, field, value):
    facts = chronology_facts(); facts[name][field] = value
    with pytest.raises(resolution.CountResolutionRefusal): resolution.check_chronology(facts)


class _StatProjection:
    """Explicit fixture metadata observations, never real flags/ownership."""
    def __init__(self, original, **overrides): self.original, self.overrides = original, overrides
    def __getattr__(self, name): return self.overrides.get(name, getattr(self.original, name))


@pytest.fixture
def physical(monkeypatch, tmp_path):
    root = tmp_path / "root"; root.mkdir(mode=0o700)
    base = root / "fabricated-footprint"; base.mkdir(mode=0o700)
    for name in ("mount", "mount/capture", "mount/claim", *resolution.CONTAINERS, "mount/.fseventsd"):
        (base / name).mkdir(mode=0o700)
    claim = base / resolution.CLAIM; claim.write_bytes(b"X" * 534); claim.chmod(0o600)
    backing = base / "backing.sparseimage"; backing.write_bytes(b"FABRICATED_NOT_AN_IMAGE"); backing.chmod(0o600)
    claim_inode, backing_inode = claim.lstat().st_ino, backing.lstat().st_ino
    system_inodes = {(base / "mount/.fseventsd").lstat().st_ino}
    mount_inodes = {(base / "mount").lstat().st_ino,
        *(path.lstat().st_ino for path in (base / "mount").rglob("*"))}
    real_stat, real_fstat, real_open, real_close, real_read, real_listdir = os.stat, os.fstat, os.open, os.close, os.read, os.listdir
    opened, attempts, reads = set(), [], []
    def projected(info, path=None):
        leaf = os.fspath(path).rsplit("/", 1)[-1] if path is not None else ""
        if leaf == ".fseventsd": system_inodes.add(info.st_ino)
        overrides = {"st_dev": info.st_dev + 1} if info.st_ino in mount_inodes else {}
        if info.st_ino in system_inodes: overrides["st_uid"] = 0
        if info.st_ino == claim_inode: overrides["st_flags"] = 2
        if info.st_ino == backing_inode: overrides["st_flags"] = 64
        return _StatProjection(info, **overrides) if overrides else info
    def read_stat(path, **kwargs):
        info = real_stat(path, **kwargs)
        parent = kwargs.get("dir_fd")
        if (parent is not None and real_fstat(parent).st_ino in mount_inodes) or str(path).startswith(str(base / "mount") + "/"):
            mount_inodes.add(info.st_ino)
        return projected(info, path)
    def read_fstat(fd): return projected(real_fstat(fd))
    def open_fd(path, flags, *args, **kwargs):
        attempts.append((os.fspath(path), flags))
        if os.fspath(path).rsplit("/", 1)[-1] == "claim.spent.json":
            info = real_stat(path, dir_fd=kwargs.get("dir_fd"), follow_symlinks=False)
            assert not stat.S_ISFIFO(info.st_mode), "FIFO must be refused BEFORE opening"
        fd = real_open(path, flags, *args, **kwargs); opened.add(fd); return fd
    def close_fd(fd):
        result = real_close(fd); opened.discard(fd); return result
    def read_fd(fd, amount):
        reads.append((real_fstat(fd).st_ino, amount)); return real_read(fd, amount)
    def list_names(path):
        inode = real_fstat(path).st_ino if type(path) is int else real_stat(path, follow_symlinks=False).st_ino
        assert inode not in system_inodes, "System directory contents must never be listed"
        return real_listdir(path)
    monkeypatch.chdir(root)
    monkeypatch.setattr(resolution, "ROOT", root)
    monkeypatch.setattr(resolution, "NAMESPACE", Path("fabricated-footprint"))
    monkeypatch.setattr(resolution, "check_chronology", lambda facts: None)  # Named temp-clock seam.
    monkeypatch.setattr(resolution, "_native_association", lambda *args: ("EXPLICIT_FAKE_NATIVE",))
    monkeypatch.setattr(resolution.os, "stat", read_stat)
    monkeypatch.setattr(resolution.os, "fstat", read_fstat)
    monkeypatch.setattr(resolution.os, "open", open_fd)
    monkeypatch.setattr(resolution.os, "close", close_fd)
    monkeypatch.setattr(resolution.os, "read", read_fd)
    monkeypatch.setattr(resolution.os, "listdir", list_names)
    value = SimpleNamespace(root=root, base=base, claim=claim, backing=backing, opened=opened,
        attempts=attempts, reads=reads)
    try: yield value
    finally:
        leaked = tuple(opened)
        for fd in leaked:
            try: real_close(fd)
            except OSError: pass
        assert not leaked, "Reader leaked owned descriptors"


@contextmanager
def held(physical, boundary=lambda: None):
    value = resolution._HeldFootprint(boundary)
    try: yield value
    finally: value.close()


def test_readonly_original_descriptors_are_closed_without_touching_source(physical):
    with held(physical) as value:
        assert value.read_claim() == b"X" * 534
        assert physical.opened
    assert not physical.opened
    assert physical.reads and all(inode == physical.claim.lstat().st_ino for inode, unused in physical.reads)
    assert all(flags & os.O_ACCMODE == os.O_RDONLY for unused, flags in physical.attempts)


@pytest.mark.parametrize("change", ["mode", "hardlink", "symlink", "fifo"])
def test_invalid_claim_metadata_is_refused_before_any_claim_open_or_raw_read(physical, change):
    if change == "mode": physical.claim.chmod(0o644)
    elif change == "hardlink": os.link(physical.claim, physical.root.parent / "claim-link")
    else:
        original = physical.root.parent / "retained-original-claim"; physical.claim.rename(original)
        if change == "symlink": physical.claim.symlink_to(original)
        else: os.mkfifo(physical.claim, 0o600)
    value = None
    try:
        with pytest.raises((resolution.CountResolutionRefusal, OSError)):
            value = resolution._HeldFootprint(lambda: None)
    finally:
        if value is not None: value.close()
    assert not physical.reads
    assert not any(path.rsplit("/", 1)[-1] == "claim.spent.json" for path, unused in physical.attempts)
    assert not physical.opened


@pytest.mark.parametrize("change", ["extra", "claim_inode", "ancestor_symlink"])
def test_membership_replacement_or_symlink_refuses_before_claim_bytes(physical, change):
    if change == "ancestor_symlink":
        original = physical.root.parent / "saved-capture"; (physical.base / "mount/capture").rename(original)
        (physical.base / "mount/capture").symlink_to(original, target_is_directory=True)
        with pytest.raises((resolution.CountResolutionRefusal, OSError)):
            resolution._HeldFootprint(lambda: None)
        assert not physical.reads and not physical.opened
        return
    with held(physical) as value:
        if change == "extra": (physical.base / "mount/capture/FOREIGN").write_bytes(b"SYNTHETIC_NOT_TO_READ")
        else:
            original = physical.root.parent / "retained-claim"; physical.claim.rename(original)
            physical.claim.write_bytes(b"Y" * 534); physical.claim.chmod(0o600)
        with pytest.raises((resolution.CountResolutionRefusal, OSError)): value.read_claim()
        assert not physical.reads


@pytest.mark.parametrize("change", ["mode", "inode"])
def test_system_directory_metadata_is_pinned_without_reading_contents(physical, change):
    system = physical.base / "mount/.fseventsd"
    if change == "mode":
        system.chmod(0o755); value = None
        try:
            with pytest.raises(resolution.CountResolutionRefusal): value = resolution._HeldFootprint(lambda: None)
        finally:
            if value is not None: value.close()
    else:
        with held(physical) as value:
            system.rename(physical.root.parent / "preserved-system")
            system.mkdir(mode=0o700)
            with pytest.raises(resolution.CountResolutionRefusal): value.audit()
    assert not physical.reads and not physical.opened


def test_constructor_failure_closes_every_previously_opened_descriptor(physical):
    calls = [0]
    def boundary():
        calls[0] += 1
        if calls[0] == 2: raise resolution.CountResolutionRefusal("REFUSED: resolution_deadline")
    with pytest.raises(resolution.CountResolutionRefusal): resolution._HeldFootprint(boundary)
    assert not physical.opened and not physical.reads


@pytest.fixture
def native(monkeypatch, tmp_path):
    image, mount = tmp_path / "synthetic-image", tmp_path / "mount"
    mount.mkdir(); fd = os.open(mount, os.O_RDONLY | os.O_DIRECTORY)
    value = {"fsid": (123, 456), "owner": os.getuid(), "flags": 0x101000, "flags_ext": 0,
        "type": 24, "subtype": 0, "fstype": "apfs", "mounted_on": str(mount), "mounted_from": "/dev/disk77s1"}
    images = [{"image-path": str(image), "system-entities": [{"mount-point": str(mount), "dev-entry": "/dev/disk77s1"}]}]
    monkeypatch.setattr(resolution.volume, "_native_statfs", lambda supplied: dict(value))
    monkeypatch.setattr(resolution.volume, "_node_pin", lambda *args: ("EXPLICIT_FAKE_NODE",))
    monkeypatch.setattr(resolution.subprocess, "run", lambda *args, **kwargs:
        SimpleNamespace(returncode=0, stdout=plistlib.dumps({"images": images})))
    try: yield SimpleNamespace(fd=fd, image=image, mount=mount, facts=value, images=images)
    finally: os.close(fd)


@pytest.mark.parametrize("flags", [0, 0x101001, 0x301000, 0x1000])
def test_native_mount_flags_retain_original_required_masks(native, flags):
    native.facts["flags"] = flags
    with pytest.raises(resolution.CountResolutionRefusal):
        resolution._native_association(native.fd, native.image, native.mount)


def test_other_image_cannot_also_claim_the_same_mount_device(native):
    native.images.append({"image-path": "/synthetic-other-image", "system-entities": [
        {"mount-point": str(native.mount), "dev-entry": "/dev/disk77s1"}]})
    with pytest.raises(resolution.CountResolutionRefusal):
        resolution._native_association(native.fd, native.image, native.mount)


def test_fixed_claim_reconstruction_binds_original_code_manifest():
    with pytest.raises(resolution.CountResolutionRefusal, match="resolution_code_changed"):
        resolution._claim_expected({"wrong.py": "a" * 64}, "2026-10-27T15:37:35.346106Z")


@pytest.mark.parametrize("bad", [False, "working", "committed", "type", "oversize", "held_check"])
def test_current_code_helper_uses_original_held_bytes_and_exact_committed_route(monkeypatch, tmp_path, bad):
    monkeypatch.setattr(resolution, "ROOT", tmp_path)
    monkeypatch.setattr(resolution, "code_paths", lambda: ("synthetic.py",))
    calls = []
    guard = SimpleNamespace(check=lambda: calls.append("guard"))
    class HeldCode:
        def read(self, path, maximum):
            assert path == tmp_path / "synthetic.py" and maximum == 8 * 1024 ** 2
            calls.append("held_read")
            if bad == "working": return b"DIFFERENT"
            if bad == "type": return "SYNTHETIC"
            if bad == "oversize": return b"S" * (8 * 1024 ** 2 + 1)
            return b"SYNTHETIC"
        def check(self):
            calls.append("held_check")
            if bad == "held_check": raise resolution.CountResolutionRefusal("REFUSED: resolution_code_changed")
    def git(root, args, supplied):
        assert root == tmp_path and args == ["show", "a" * 40 + ":synthetic.py"] and supplied is guard
        calls.append("git")
        return b"DIFFERENT" if bad == "committed" else b"SYNTHETIC"
    monkeypatch.setattr(resolution.archive.count.old.cache, "_git", git)
    if bad:
        with pytest.raises(resolution.CountResolutionRefusal, match="resolution_code_changed"):
            resolution._current_code_manifest(guard, "a" * 40, HeldCode())
    else:
        assert resolution._current_code_manifest(guard, "a" * 40, HeldCode()) == {"synthetic.py": hash_bytes(b"SYNTHETIC")}
        assert calls == ["guard", "held_read", "git", "held_check"]


def test_original_cleanup_closes_all_descriptors_even_if_one_exit_callback_fails(physical):
    value = resolution._HeldFootprint(lambda: None)
    def failed_exit(): raise resolution.CountResolutionRefusal("REFUSED: resolution_path_changed")
    value.stack.callback(failed_exit)
    with pytest.raises(resolution.CountResolutionRefusal): value.close()
    assert value.closed and not physical.opened


def test_after_close_original_membership_still_vetoes_late_mount_entry(physical):
    value = resolution._HeldFootprint(lambda: None)
    value.audit(callbacks=False); value.close()
    (physical.base / "mount/FOREIGN").write_bytes(b"SYNTHETIC_NOT_TO_READ")
    with pytest.raises(resolution.CountResolutionRefusal): value.audit_after_close()
    assert not physical.opened and not physical.reads


def test_last_named_sweep_cannot_hide_a_late_root_alias(physical, monkeypatch):
    value = resolution._HeldFootprint(lambda: None); value.close()
    final_path = physical.base / "mount/capture/responses"
    real_lstat = Path.lstat; calls = [0]; moved = [False]
    def lstat(path):
        info = real_lstat(path)
        if path == final_path:
            calls[0] += 1
            # Initial named sweep, facts sweep, then LAST named sweep. Mutate
            # only after the last returned original node observation.
            if calls[0] == 3:
                destination = physical.root.parent / "preserved-root"
                physical.root.rename(destination); physical.root.symlink_to(destination, target_is_directory=True)
                moved[0] = True
        return info
    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(resolution.CountResolutionRefusal): value.audit_after_close()
    assert moved[0] and not physical.opened and not physical.reads


@pytest.fixture
def composed(monkeypatch, tmp_path):
    """Public factory with genuine B3 and explicitly fake physical/code issuers.

    This tests ordering/consumer contracts only. None of these fake issuers
    creates an operational negative witness or authenticates historical bytes.
    """
    ledger = support.toy_ledger(monkeypatch)
    support.bind_toy_profile(monkeypatch, ledger)
    root = tmp_path / "composed-root"; root.mkdir()
    monkeypatch.chdir(root)
    current_path = "synthetic-current.py"; current_raw = b"FABRICATED_CURRENT_CODE"
    (root / current_path).write_bytes(current_raw)
    old_path = "synthetic-historical.py"; old_raw = b"FABRICATED_OLD_CODE"
    manifest = {old_path: hash_bytes(old_raw)}
    monkeypatch.setattr(resolution, "ROOT", root)
    monkeypatch.setattr(resolution, "HISTORICAL_PATHS", (old_path,))
    monkeypatch.setattr(resolution, "OLD_MANIFEST_SHA256", hash_payload(manifest))
    monkeypatch.setattr(resolution, "registered", lambda: None)  # Explicit registration/code-domain seam.
    monkeypatch.setattr(resolution, "code_paths", lambda: (current_path,))
    monkeypatch.setattr(resolution.plans, "freeze_count_recovery_plan",
        lambda supplied: SimpleNamespace(sha256=resolution.OLD_PLAN))  # Old-code plan reconstruction seam.
    expected = resolution._claim_expected(manifest, "2026-10-27T15:37:35.346106Z")
    state = SimpleNamespace(raw=canonical_json(expected).encode(), events=[], refreshes=0,
        late_membership=False, mutate_on_refresh=False, fail_close=False, fail_exit=False,
        fail_after_close_clock=False, exposure_ledger=ledger, manifest=manifest, expected=expected)
    class Guard:
        def __init__(self, supplied_root, *, expected_head, expected_remote):
            assert supplied_root == root and expected_head == "a" * 40 and expected_remote == "b" * 40
        def check(self): state.events.append("guard_check")
        def refresh(self):
            state.events.append("guard_refresh"); state.refreshes += 1
            if state.mutate_on_refresh and state.refreshes >= 2: state.late_membership = True
    monkeypatch.setattr(resolution.lane, "LaneGuard", Guard)
    def git_bytes(*args, **kwargs):
        command = next((arg for arg in args if isinstance(arg, (list, tuple)) and "show" in arg), None)
        assert command is not None, args
        target = command[command.index("show") + 1]
        if target == resolution.OLD_HEAD + ":" + old_path: return old_raw
        assert target == "a" * 40 + ":" + current_path, target
        return current_raw
    monkeypatch.setattr(resolution.subprocess, "check_output", git_bytes)
    cache = resolution.archive.count.old.cache
    monkeypatch.setattr(cache, "_git", git_bytes)
    class FakeHeldFiles:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): state.events.append("code_enter"); return self
        def read(self, name):
            assert str(name) in (current_path, str(root / current_path))
            return current_raw
        def check(self): state.events.append("code_check")
        def __exit__(self, *args):
            state.events.append("code_exit")
            if state.fail_exit: raise resolution.CountResolutionRefusal("REFUSED: resolution_code_changed")
    monkeypatch.setattr(cache, "HeldFiles", FakeHeldFiles)
    if hasattr(resolution, "_current_code_manifest"):
        def current_manifest(guard, head, held, *, paths=None):
            assert head == "a" * 40
            guard.check(); held.check()
            return {current_path: hash_bytes(current_raw)}
        monkeypatch.setattr(resolution, "_current_code_manifest", current_manifest)
    facts = chronology_facts()
    class Node:
        def __init__(self, name): self.name = name
        def lstat(self): return facts[self.name]
    class Base:
        def __truediv__(self, name): return Node(name)
    class FakeFootprint:
        def __init__(self, boundary):
            self.boundary, self.facts, self.base = boundary, facts, Base()
            state.events.append("footprint_open")
        def audit(self, *, callbacks=True):
            if callbacks: self.boundary()
            state.events.append("physical_terminal" if not callbacks else "physical_audit")
            if state.late_membership: raise resolution.CountResolutionRefusal("REFUSED: resolution_membership_changed")
        def read_claim(self): self.audit(); return state.raw
        def close(self):
            state.events.append("footprint_close")
            if state.fail_close: raise resolution.CountResolutionRefusal("REFUSED: resolution_path_changed")
        def audit_after_close(self):
            state.events.append("physical_after_close")
            if state.late_membership: raise resolution.CountResolutionRefusal("REFUSED: resolution_membership_changed")
    monkeypatch.setattr(resolution, "_HeldFootprint", FakeFootprint)
    monkeypatch.setattr(resolution, "_fact", lambda info: info)  # Named final-fake-path stat seam.
    def tick():
        return -1 if state.fail_after_close_clock and "footprint_close" in state.events else 1.0
    monkeypatch.setattr(resolution.time, "monotonic", tick)
    if hasattr(resolution, "_MONOTONIC"): monkeypatch.setattr(resolution, "_MONOTONIC", tick)
    state.resolve = lambda: resolution.resolve_registered(ledger, runtime_head="a" * 40, actual_remote="b" * 40)
    return state


def test_public_composition_requires_exact_claim_and_emits_only_negative_unknowns(composed):
    value = composed.resolve(); row = resolution.resolution_binding(value)
    assert row[0] is value and row[2] is composed.exposure_ledger and len(row) == 6
    report = value.public_summary()
    assert report["old_process_exit"] is report["old_actual_HTTP"] is report["old_actual_STARTs"] is report["old_actual_bytes"] is None
    assert report["negative_exposure_sha256"] == row[1].sha256
    assert report["claim_sha256"] == hash_bytes(composed.raw)
    assert not report["authority"]["source_dispatch_authority"] and report["authority"]["coverage_contribution"] == 0
    assert "footprint_close" in composed.events


@pytest.mark.parametrize("mutation", ["whitespace", "duplicate", "extra", "wrong_code", "nonfinite", "wrong_date", "nonUTC",
    "stale_same_day", "future_same_day", "space_separator", "missing_microseconds", "UTC_offset"])
def test_claim_json_or_code_drift_cannot_mint_a_negative_resolution(composed, mutation):
    claim = dict(composed.expected)
    if mutation == "whitespace": composed.raw += b"\n"
    elif mutation == "duplicate": composed.raw = composed.raw[:-1] + b',"spent":true}'
    elif mutation == "nonfinite": composed.raw = b'{"started_at":NaN}'
    else:
        if mutation == "extra": claim["complete"] = True
        elif mutation == "wrong_code": claim["registration_sha256"] = "0" * 64
        elif mutation == "wrong_date": claim["started_at"] = "2026-10-28T15:37:35.346106Z"
        elif mutation == "stale_same_day": claim["started_at"] = "2026-10-27T00:00:00.000000Z"
        elif mutation == "future_same_day": claim["started_at"] = "2026-10-27T23:59:59.000000Z"
        elif mutation == "space_separator": claim["started_at"] = "2026-10-27 15:37:35.346106Z"
        elif mutation == "missing_microseconds": claim["started_at"] = "2026-10-27T15:37:35Z"
        elif mutation == "UTC_offset": claim["started_at"] = "2026-10-27T15:37:35.346106+00:00"
        else: claim["started_at"] = "2026-10-27T15:37:35.346106+01:00"
        composed.raw = canonical_json(claim).encode()
    with pytest.raises((resolution.CountResolutionRefusal, ValueError)): composed.resolve()
    assert not resolution._ISSUED and "footprint_close" in composed.events


def test_guard_callback_mutation_cannot_follow_last_physical_audit_before_mint(composed):
    composed.mutate_on_refresh = True
    with pytest.raises(resolution.CountResolutionRefusal): composed.resolve()
    assert not resolution._ISSUED and "footprint_close" in composed.events


@pytest.mark.parametrize("failure", ["fail_close", "fail_exit", "fail_after_close_clock"])
def test_all_context_exit_and_final_clock_failures_veto_issuance(composed, failure):
    setattr(composed, failure, True)
    with pytest.raises(resolution.CountResolutionRefusal): composed.resolve()
    assert not resolution._ISSUED


def test_payload_hash_or_copied_anchor_is_not_an_original_capability(composed):
    value = composed.resolve()
    with pytest.raises(resolution.CountResolutionRefusal): resolution.Run13448Resolution()
    for supplied in (value.public_summary(), hash_payload(value.public_summary()), True, object()):
        with pytest.raises(resolution.CountResolutionRefusal): resolution.resolution_binding(supplied)
    forged = object.__new__(resolution.Run13448Resolution); forged._anchor = value._anchor
    with pytest.raises(resolution.CountResolutionRefusal): resolution.resolution_binding(forged)
    original = value._anchor
    value._anchor = (*original[:3], b"{}", *original[4:])
    with pytest.raises(resolution.CountResolutionRefusal): value.public_summary()
    value._anchor = original
    with pytest.raises(resolution.CountResolutionRefusal): value.public_summary()


def test_terminal_original_physical_audit_follows_every_code_and_guard_callback(composed):
    composed.resolve()
    events = composed.events
    assert "code_exit" in events and "physical_terminal" in events and "physical_after_close" in events
    terminal = events.index("physical_terminal")
    assert terminal > events.index("code_exit")
    assert not any(event.startswith("guard_") or event.startswith("code_") for event in events[terminal + 1:])
