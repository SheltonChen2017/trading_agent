"""Fabricated hdiutil and native mount observations; no actual image or mount."""
from copy import deepcopy
import ctypes
import errno
import json
import os
from pathlib import Path
import plistlib
import socket
import subprocess
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_payload
from scripts import short_interest_isolated_custody_volume as volume

REAL_RUN, REAL_NATIVE = volume._run, volume._native_statfs
REAL_STAT, REAL_FSTAT = os.stat, os.fstat
_POSIX_CAPTURE_ONLY = pytest.mark.skipif(not hasattr(os, "getuid"),
    reason="protected fixture requires POSIX ownership, mode and dir_fd; SI-CR-WIN-20261012-002")


class Clock:
    def __init__(self): self.value = 10.0
    def __call__(self): self.value += .001; return self.value


@pytest.fixture(autouse=True)
def deny_real_external_operations(monkeypatch):
    def denied(*args, **kwargs): raise AssertionError("real subprocess/native/network forbidden")
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(volume, "_native_statfs", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(volume, "_MINTED", {})
    monkeypatch.setattr(volume, "_ISSUED", {})
    monkeypatch.setattr(volume, "_FAILED", set())
    monkeypatch.setattr(volume, "_USED", False)


class Harness:
    def __init__(self, tmp_path, monkeypatch):
        self.root = tmp_path / "lane"; self.root.mkdir(mode=0o700)
        self.parent = self.root / volume.PARENT; self.parent.mkdir(mode=0o700, parents=True)
        self.namespace = self.parent / volume.NAMESPACE
        self.image = self.namespace / volume.IMAGE_NAME
        self.mount = self.namespace / volume.MOUNT_NAME
        self.clock, self.calls, self.boundaries = Clock(), [], 0
        self.attached, self.mount_inode, self.info_change = False, None, None
        self.hook = lambda: None
        self.command_hook = lambda verb: None
        self.host_device = REAL_STAT(self.parent).st_dev
        self.native_change = lambda value: value
        self.host_change = lambda value: value
        self.current_entities = [{"dev-entry": "/dev/disk999", "content-hint": "GUID_partition_scheme"},
            {"dev-entry": "/dev/disk999s1", "volume-kind": "apfs", "mount-point": str(self.mount)}]
        monkeypatch.setattr(volume, "ROOT", self.root)
        monkeypatch.chdir(self.root)
        monkeypatch.setattr(volume, "sys", SimpleNamespace(platform="darwin"))
        monkeypatch.setattr(subprocess, "run", self.runner)
        monkeypatch.setattr(volume, "_native_statfs", self.native)
        def changed(info):
            if self.mount_inode is not None and info.st_ino == self.mount_inode:
                values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
                values["st_dev"] = self.host_device + 101
                return SimpleNamespace(**values)
            return info
        monkeypatch.setattr(os, "stat", lambda *args, **kwargs: changed(REAL_STAT(*args, **kwargs)))
        monkeypatch.setattr(os, "fstat", lambda fd: changed(REAL_FSTAT(fd)))

    def boundary(self): self.boundaries += 1; self.hook()

    def native(self, fd):
        info = REAL_FSTAT(fd)
        base = {"bsize": 4096, "blocks": volume.VIRTUAL_BYTES // 4096,
            "bavail": 7 * 1024 ** 3 // 4096, "fsid": (111, 222), "owner": os.getuid(),
            "flags": volume.MNT_LOCAL | volume.MNT_DONTBROWSE, "flags_ext": 0,
            "type": 26, "subtype": 0, "fstype": "apfs", "mounted_on": str(self.mount),
            "mounted_from": "/dev/disk999s1"}
        if self.mount_inode is not None and info.st_ino == self.mount_inode:
            return self.native_change(base)
        base.update(bavail=20 * 1024 ** 3 // 4096, fsid=(1, 2), flags=volume.MNT_LOCAL,
            mounted_on="/FAKE-HOST", mounted_from="/dev/diskFAKE")
        return self.host_change(base)

    def runner(self, arguments, **kwargs):
        assert arguments[0] == "/usr/bin/hdiutil" and arguments[1] in ("create", "attach", "info")
        assert kwargs["stdin"] is subprocess.DEVNULL and kwargs["stderr"] is subprocess.DEVNULL
        assert kwargs["stdout"] is subprocess.PIPE and kwargs["check"] is False
        assert 0 < kwargs["timeout"] <= 120 and kwargs["cwd"] == self.root
        assert kwargs["env"] == {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
        verb = arguments[1]; self.calls.append((list(arguments), kwargs)); self.command_hook(verb)
        if verb == "create":
            assert arguments == ["/usr/bin/hdiutil", "create", "-type", "SPARSE", "-size", "8g",
                "-fs", "APFS", "-uid", str(os.getuid()), "-gid", str(os.getgid()), "-mode", "0700",
                "-volname", "SI_OFFLINE_CUSTODY_V1", "-nospotlight", "-plist", str(self.image)]
            with self.image.open("xb") as stream: stream.write(b"FABRICATED SPARSE IMAGE, NO REAL FILESYSTEM")
            self.image.chmod(0o644)
            payload = [str(self.image)]
        elif verb == "attach":
            assert arguments == ["/usr/bin/hdiutil", "attach", "-mountpoint", str(self.mount),
                "-mount", "required", "-nobrowse", "-owners", "on", "-noautoopen",
                "-noautoopenro", "-noautoopenrw", "-plist", str(self.image)]
            # Fake a mounted root without a mount syscall. Retain the original
            # underlying directory separately so its held FD remains authentic.
            self.mount.rename(self.root / "retained-underlying-mount")
            self.mount.mkdir(mode=0o700); self.mount_inode = REAL_STAT(self.mount).st_ino
            self.attached = True
            payload = {"system-entities": deepcopy(self.current_entities)}
        else:
            assert arguments == ["/usr/bin/hdiutil", "info", "-plist"]
            images = [{"image-path": str(self.root / "UNRELATED-PRIVATE-NAME"),
                "system-entities": [{"dev-entry": "/dev/disk123"}]}]
            if self.attached:
                images.append({"image-path": str(self.image), "system-entities": deepcopy(self.current_entities)})
            payload = {"images": images}
            if self.info_change is not None: payload = self.info_change(payload)
        return subprocess.CompletedProcess(arguments, 0, plistlib.dumps(payload), b"SECRET STDERR NOT USED")

    def prepare(self):
        return volume.prepare_registered_volume(self.root, boundary=self.boundary, monotonic=self.clock)


@pytest.fixture
def h(tmp_path, monkeypatch):
    # Only this protected-filesystem fixture skips; policy and fixed-error
    # tests below remain runnable on a host without POSIX ownership semantics.
    if not hasattr(os, "getuid"):
        pytest.skip("protected fixture requires POSIX ownership, mode and dir_fd; SI-CR-WIN-20261012-002")
    return Harness(tmp_path, monkeypatch)


def test_full_original_factory_close_is_redacted_and_preserves_all_artifacts(h):
    with h.prepare() as cap:
        assert cap.mountpoint == h.mount
        cap.check(); observed = cap.observation()
        assert observed["status"] == "live_provisional_synthetic_volume"
        assert observed["owners_honored"] is observed["local_filesystem"] is observed["nobrowse"] is True
        descriptors = [fd for unused, fd, unused_pin in volume._MINTED[id(cap)][2]["directories"]]
        state = volume._MINTED[id(cap)][2]
        descriptors += [state[key] for key in ("backing_fd", "under_mount_fd", "mount_fd")]
    cap.check_after_close(); closed = cap.closed_summary()
    assert closed["status"] == "closed_synthetic_isolated_volume_only"
    assert closed["authority"]["persistent_production_storage_admitted"] is False
    assert closed["authority"]["ready_for_backtest"] is closed["authority"]["source_admitted"] is False
    assert closed["authority"]["source_STARTs"] == closed["authority"]["source_bytes"] == 0
    assert h.image.exists() and h.mount.exists() and h.attached
    assert set(os.listdir(h.namespace)) == {"backing.sparseimage", "mount"}
    assert all("detach" not in command for command, unused in h.calls)
    assert str(h.root) not in canonical_json(closed) and "/dev/" not in canonical_json(closed)
    assert "PRIVATE" not in repr(cap) + canonical_json(closed)
    closed["authority"]["source_admitted"] = True
    assert cap.closed_summary()["authority"]["source_admitted"] is False
    for fd in descriptors:
        with pytest.raises(OSError): REAL_FSTAT(fd)


def test_live_object_phase_mutation_cannot_forge_terminal_issued_closure(h):
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_failure_latched"):
        with h.prepare() as cap:
            state = volume._MINTED[id(cap)][2]; state["phase"] = "CLOSED"
            with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_not_closed"): cap.closed_summary()
            state["phase"] = "LIVE"
            with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_failure_latched"): cap.check()
            with pytest.raises(volume.IsolatedVolumeRefusal): cap.closed_summary()


@pytest.mark.parametrize("change", ["noowners", "remote", "browse", "readonly", "device", "fsid", "fstype", "owner"])
def test_each_postbaseline_native_drift_permanently_refuses(h, change):
    expected = {"noowners": "isolated_mount_ownership_ignored", "remote": "isolated_mount_not_local",
        "browse": "isolated_mount_browse_refused", "readonly": "isolated_mount_readonly",
        "device": "isolated_mount_device_changed", "fsid": "isolated_mount_native_identity_changed",
        "fstype": "isolated_mount_not_apfs", "owner": "isolated_mount_owner_refused"}[change]
    def modify(value):
        if change == "noowners": value["flags"] |= volume.MNT_IGNORE_OWNERSHIP
        elif change == "remote": value["flags"] &= ~volume.MNT_LOCAL
        elif change == "browse": value["flags"] &= ~volume.MNT_DONTBROWSE
        elif change == "readonly": value["flags"] |= volume.MNT_RDONLY
        elif change == "device": value["mounted_from"] = "/dev/disk998s1"
        elif change == "fsid": value["fsid"] = (333, 444)
        elif change == "fstype": value["fstype"] = "hfs"
        else: value["owner"] = os.getuid() + 1
        return value
    with pytest.raises(volume.IsolatedVolumeRefusal):
        with h.prepare() as cap:
            h.native_change = modify
            with pytest.raises(volume.IsolatedVolumeRefusal, match=expected): cap.check()
            h.native_change = lambda value: value
            with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_failure_latched"): cap.check()
    assert h.image.exists() and h.mount.exists()
    with pytest.raises(volume.IsolatedVolumeRefusal): cap.closed_summary()


@pytest.mark.parametrize("change", ["noowners", "remote", "host_capacity", "mount_capacity", "not_apfs"])
def test_actual_native_initial_conditions_not_only_arguments_are_required(h, change):
    if change in ("noowners", "remote", "host_capacity"):
        def changed(value):
            if change == "noowners": value["flags"] |= volume.MNT_IGNORE_OWNERSHIP
            elif change == "remote": value["flags"] &= ~volume.MNT_LOCAL
            else: value["bavail"] = 1
            return value
        h.host_change = changed
    else:
        h.native_change = lambda value: dict(value, **({"bavail": 1} if change == "mount_capacity" else {"fstype": "hfs"}))
    with pytest.raises(volume.IsolatedVolumeRefusal):
        with h.prepare(): pytest.fail("native capability was inferred from arguments")


def test_existing_namespace_is_never_adopted_or_modified(h):
    h.namespace.mkdir(mode=0o700); old = h.namespace / "old-evidence"; old.write_bytes(b"KEEP")
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_namespace_exists"):
        with h.prepare(): pytest.fail("existing namespace adopted")
    assert old.read_bytes() == b"KEEP" and not h.calls


def test_already_attached_matching_image_refuses_before_any_create(h):
    h.info_change = lambda payload: {"images": [{"image-path": str(h.image),
        "system-entities": deepcopy(h.current_entities)}]}
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_image_association_refused"):
        with h.prepare(): pytest.fail("attached image adopted")
    assert [command[1] for command, unused in h.calls] == ["info"] and not h.image.exists()


@pytest.mark.parametrize("change", ["duplicate", "missing", "shadow", "wrong_device"])
def test_final_hdiutil_association_original_pins_are_required(h, change):
    def altered(payload):
        target = payload["images"][-1]
        if change == "duplicate": payload["images"].append(deepcopy(target))
        elif change == "missing": payload["images"].pop()
        elif change == "shadow": target["shadow-path"] = "NO-OVERLAY"
        else: target["system-entities"][-1]["dev-entry"] = "/dev/disk998s1"
        return payload
    with pytest.raises(volume.IsolatedVolumeRefusal):
        with h.prepare() as cap: h.info_change = altered
    assert h.image.exists() and h.attached
    with pytest.raises(volume.IsolatedVolumeRefusal): cap.closed_summary()


@pytest.mark.parametrize("change", ["mode", "hardlink", "inode", "mount_mode", "namespace_extra"])
def test_backing_parent_and_mount_protection_never_rebaseline(h, change):
    with pytest.raises(volume.IsolatedVolumeRefusal):
        with h.prepare() as cap:
            if change == "mode": h.image.chmod(0o644)
            elif change == "hardlink": os.link(h.image, h.root / "retained-link")
            elif change == "inode":
                h.image.rename(h.root / "retained-original-image"); h.image.write_bytes(b"REPLACEMENT"); h.image.chmod(0o600)
            elif change == "mount_mode": h.mount.chmod(0o755)
            else: (h.namespace / "extra").write_bytes(b"KEEP")
            cap.check()
    assert h.image.exists()


def test_backing_legitimate_growth_is_not_an_inner_evidence_stamp_exception(h):
    with h.prepare() as cap:
        with h.image.open("ab") as stream: stream.write(b"CONTAINER METADATA GROWTH")
        cap.check()
    assert cap.closed_summary()["container_is_immutable_evidence"] is False


def test_after_close_replacement_is_checked_against_original_pins_and_latches(h):
    with h.prepare() as cap: pass
    h.image.rename(h.root / "retained-backing"); h.image.write_bytes(b"NEW"); h.image.chmod(0o600)
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_backing_changed"): cap.check_after_close()
    h.image.unlink(); (h.root / "retained-backing").rename(h.image)
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_failure_latched"): cap.closed_summary()


@pytest.mark.parametrize("jump", [float("nan"), float("inf"), -1.0, 301.0])
def test_clock_deadline_and_nonfinite_failures_preserve_image(h, jump):
    with pytest.raises(volume.IsolatedVolumeRefusal):
        with h.prepare() as cap:
            h.clock.value = jump if not 0 < jump < 1000 else h.clock.value + jump
            cap.check()
    assert h.image.exists() and h.attached


def test_boundary_failure_cannot_be_caught_to_obtain_closure(h):
    with pytest.raises(volume.IsolatedVolumeRefusal):
        with h.prepare() as cap:
            def failed(): raise RuntimeError("PRIVATE PATH SECRET")
            h.hook = failed
            with pytest.raises(RuntimeError): cap.check()
            h.hook = lambda: None
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_failure_latched"): cap.closed_summary()


@pytest.mark.parametrize("failure", ["nonzero", "timeout", "badplist", "oversize"])
def test_subprocess_failure_diagnostics_are_bounded_and_never_publish_stderr(h, monkeypatch, failure):
    def runner(arguments, **kwargs):
        if failure == "timeout": raise subprocess.TimeoutExpired(arguments, 120, stderr=b"SECRET")
        return subprocess.CompletedProcess(arguments, 1 if failure == "nonzero" else 0,
            b"not a plist SECRET" if failure == "badplist" else b"x" * (volume.MAXIMUM_PLIST_BYTES + 1),
            b"SECRET STDERR")
    monkeypatch.setattr(subprocess, "run", runner)
    with pytest.raises(volume.IsolatedVolumeRefusal) as caught:
        with h.prepare(): pytest.fail("bad command admitted")
    report = volume.failure_summary(caught.value)
    assert report["category"] == "local_contract_refusal" and "SECRET" not in canonical_json(report)
    assert not h.image.exists()


def test_second_invocation_cannot_reset_or_reuse_claimless_namespace(h):
    with h.prepare() as cap: pass
    count = len(h.calls)
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_already_used"):
        with h.prepare(): pytest.fail("factory repeated")
    assert len(h.calls) == count and cap.closed_summary()["status"] == "closed_synthetic_isolated_volume_only"


@_POSIX_CAPTURE_ONLY
def test_darwin_sdk_struct_layout_and_exact_native_abi(monkeypatch):
    monkeypatch.setattr(volume, "sys", SimpleNamespace(platform="darwin"))
    calls = []
    class Operation:
        def __call__(self, fd, pointer):
            assert self.argtypes == (ctypes.c_int, ctypes.POINTER(volume._StatFS64)) and self.restype is ctypes.c_int
            calls.append(fd); value = pointer._obj
            value.f_bsize, value.f_blocks, value.f_bavail = 4096, 200, 100
            value.f_fsid[:] = (1, -2); value.f_owner = os.getuid()
            value.f_flags = volume.MNT_LOCAL | volume.MNT_DONTBROWSE
            value.f_fstypename = b"apfs"; value.f_mntonname = b"/FAKE-MOUNT"; value.f_mntfromname = b"/dev/disk999s1"
            return 0
    operation = Operation()
    def library(path, **kwargs):
        assert path == "/usr/lib/libSystem.B.dylib" and kwargs == {"use_errno": True}
        return SimpleNamespace(fstatfs64=operation)
    monkeypatch.setattr(volume.ctypes, "CDLL", library)
    result = REAL_NATIVE(77)
    assert ctypes.sizeof(volume._StatFS64) == 2168 and volume._StatFS64.f_flags.offset == 64
    assert result["fsid"] == (1, -2) and result["fstype"] == "apfs" and calls == [77]


@pytest.mark.parametrize("error", [RuntimeError("SECRET"), ValueError("REFUSED: isolated_deadline"),
    volume.IsolatedVolumeRefusal("dynamic SECRET"), volume.IsolatedVolumeRefusal("isolated_deadline", errno.EIO)])
def test_fixed_safe_failure_projection(error):
    value = volume.failure_summary(error)
    assert "SECRET" not in json.dumps(value)
    assert value["contract_code"] in volume._CODES or value["contract_code"] is None
    if type(error) is not volume.IsolatedVolumeRefusal: assert value["category"] == "unknown_local_error"


@pytest.mark.parametrize("name", ["MNT_RDONLY", "MNT_LOCAL", "MNT_DONTBROWSE", "MNT_IGNORE_OWNERSHIP"])
def test_authoritative_mount_masks_are_frozen_before_any_native_or_command_seam(monkeypatch, name):
    monkeypatch.setattr(volume, name, 0)
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_policy_changed"):
        volume.policy()
