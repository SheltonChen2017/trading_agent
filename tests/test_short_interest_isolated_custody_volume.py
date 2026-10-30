"""Fabricated hdiutil and native mount observations; no actual image or mount."""
from copy import deepcopy
import ctypes
import errno
import json
import os
from pathlib import Path
import plistlib
import socket
import stat
import subprocess
from types import SimpleNamespace

import pytest

from data.hashing import canonical_json, hash_payload
from scripts import short_interest_isolated_custody_volume as volume

REAL_RUN, REAL_NATIVE = volume._run, volume._native_statfs
REAL_STAT, REAL_FSTAT = os.stat, os.fstat
REAL_FCHMOD = os.fchmod if hasattr(os, "fchmod") else None
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
    for name in ("_ORIGIN_ISSUED", "_STATE_ORIGINS", "_ASSOCIATION_ISSUED", "_ROOT_ENFORCEMENTS"):
        monkeypatch.setattr(volume, name, {})
    monkeypatch.setattr(volume, "_LAST_ASSOCIATION", None)


class Harness:
    def __init__(self, tmp_path, monkeypatch):
        self.root = tmp_path / "lane"; self.root.mkdir(mode=0o700)
        self.parent = self.root / volume.PARENT; self.parent.mkdir(mode=0o700, parents=True)
        self.namespace = self.parent / volume.NAMESPACE
        self.image = self.namespace / volume.IMAGE_NAME
        self.mount = self.namespace / volume.MOUNT_NAME
        self.clock, self.calls, self.boundaries = Clock(), [], 0
        self.attached, self.mount_inode, self.info_change = False, None, None
        self.attach_entities, self.created_root_mode = None, 0o700
        self.root_chmod_calls, self.node_reads, self.native_reads = [], [], []
        self.node_change = lambda value: value
        self.root_change = lambda value: value
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
        monkeypatch.setattr(volume, "_device_node_stat", self.node_stat, raising=False)
        def fchmod(fd, mode):
            if self.mount_inode is not None and REAL_FSTAT(fd).st_ino == self.mount_inode:
                self.root_chmod_calls.append((mode, len(self.native_reads), len(self.node_reads)))
            return REAL_FCHMOD(fd, mode)
        monkeypatch.setattr(os, "fchmod", fchmod)
        def changed(info):
            if self.mount_inode is not None and info.st_ino == self.mount_inode:
                values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
                values["st_dev"] = self.host_device + 101
                return SimpleNamespace(**self.root_change(values))
            return info
        monkeypatch.setattr(os, "stat", lambda *args, **kwargs: changed(REAL_STAT(*args, **kwargs)))
        monkeypatch.setattr(os, "fstat", lambda fd: changed(REAL_FSTAT(fd)))

    def boundary(self): self.boundaries += 1; self.hook()

    def native(self, fd):
        self.native_reads.append(fd)
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

    def node_stat(self, device):
        assert device == "/dev/disk999s1"
        self.node_reads.append(device)
        return SimpleNamespace(**self.node_change({"st_dev": 77, "st_ino": 888,
            "st_rdev": self.host_device + 101, "st_mode": stat.S_IFBLK | 0o660,
            "st_uid": 0, "st_gid": 5}))

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
                "-volname", "SI_OFFLINE_CUSTODY_V6", "-nospotlight", "-plist", str(self.image)]
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
            self.mount.mkdir(mode=self.created_root_mode); self.mount.chmod(self.created_root_mode)
            self.mount_inode = REAL_STAT(self.mount).st_ino
            self.attached = True
            payload = {"system-entities": deepcopy(self.current_entities if self.attach_entities is None else self.attach_entities)}
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


@pytest.mark.parametrize("attach_hint,info_hint", [("Apple_APFS", "41504653-0000-11AA-AA11-00306543ECAC"),
    ("41504653-0000-11aa-aa11-00306543ecac", "Apple_APFS_Volume")])
def test_distinct_original_descriptor_origins_require_same_stronger_native_identity(h, attach_hint, info_hint):
    h.attach_entities = deepcopy(h.current_entities)
    h.attach_entities[-1]["content-hint"] = attach_hint
    h.current_entities[-1] = {"dev-entry": "/dev/disk999s1", "content-hint": info_hint,
        "mount-point": str(h.mount)}
    with h.prepare() as cap:
        assert cap.observation()["authority"]["source_admitted"] is False
        report = volume.association_diagnostic()
        assert report["vendor_text_equal"] is False and report["mounted_devices_equal"] is True
        assert report["mount_points_equal"] is report["attach_devices_subset"] is True
        assert report["mismatching_field_names"] == ["content-hint", "volume-kind"]
        assert report["attach_raw_sha256"] != report["info_raw_sha256"]
        assert report["attach_parsed_sha256"] != report["info_parsed_sha256"]
        assert cap.observation()["device_node_original_identity_sha256"]
        assert str(h.root) not in canonical_json(report) and "/dev/" not in canonical_json(report)
        report["authority"]["source_admitted"] = True
        assert volume.association_diagnostic()["authority"]["source_admitted"] is False
    assert cap.closed_summary()["authority"]["source_admitted"] is False


def test_fresh0755_root_is_enforced0700_once_after_identity_and_before_yield(h):
    h.created_root_mode = 0o755
    with h.prepare() as cap:
        assert stat.S_IMODE(REAL_STAT(h.mount).st_mode) == 0o700
        assert len(h.root_chmod_calls) == 1
        mode, native_before, node_before = h.root_chmod_calls[0]
        assert mode == 0o700 and native_before >= 2 and node_before >= 1
    assert cap.closed_summary()["authority"]["ready_for_backtest"] is False


@pytest.mark.parametrize("hint,kind", [("UNKNOWN_PRIVATE", None), ("Apple_HFS", None),
    ("41504653-0000-11AA-AA11-00306543ECAX", "apfs"), (None, "hfs"), ("apple_apfs", "apfs")])
def test_unknown_or_contradictory_mounted_descriptors_refuse_before_root_mode_write(h, hint, kind):
    h.created_root_mode = 0o755
    # Missing plist keys map to None in the strict parser; plistlib has no
    # None/null value, so do not fabricate an impossible producer response.
    row = {"dev-entry": "/dev/disk999s1", "mount-point": str(h.mount)}
    if hint is not None: row["content-hint"] = hint
    if kind is not None: row["volume-kind"] = kind
    h.current_entities[-1] = row
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_descriptor_refused"):
        with h.prepare(): pytest.fail("unknown vendor descriptor admitted")
    assert h.root_chmod_calls == [] and stat.S_IMODE(REAL_STAT(h.mount).st_mode) == 0o755
    report = volume.association_diagnostic()
    assert report["original_shapes_valid"] is True and "UNKNOWN_PRIVATE" not in canonical_json(report)
    assert report["authority"]["source_admitted"] is False


@pytest.mark.parametrize("change", ["rdev", "symlink", "inode", "uid", "gid", "mode"])
def test_original_block_node_identity_drift_refuses_and_permanently_latches(h, change):
    with pytest.raises(volume.IsolatedVolumeRefusal):
        with h.prepare() as cap:
            def changed(value):
                if change == "rdev": value["st_rdev"] += 1
                elif change == "symlink": value["st_mode"] = stat.S_IFLNK | 0o777
                elif change == "inode": value["st_ino"] += 1
                elif change == "uid": value["st_uid"] += 1
                elif change == "gid": value["st_gid"] += 1
                else: value["st_mode"] = stat.S_IFBLK | 0o600
                return value
            h.node_change = changed
            with pytest.raises(volume.IsolatedVolumeRefusal): cap.check()
            h.node_change = lambda value: value
            with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_failure_latched"): cap.check()
    assert len(h.root_chmod_calls) == 1


@pytest.mark.parametrize("change", ["rdev", "symlink"])
def test_no_block_node_binding_means_no_fresh_root_chmod(h, change):
    h.created_root_mode = 0o755
    h.node_change = lambda value: dict(value, **({"st_rdev": value["st_rdev"] + 1}
        if change == "rdev" else {"st_mode": stat.S_IFLNK | 0o777}))
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_device_node_refused"):
        with h.prepare(): pytest.fail("missing block-node witness admitted")
    assert h.root_chmod_calls == [] and stat.S_IMODE(REAL_STAT(h.mount).st_mode) == 0o755


def test_fresh_root_mode_transition_cannot_be_repeated_or_reset(h):
    with h.prepare() as cap:
        state = volume._MINTED[id(cap)][2]
        for unused in range(2):
            with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_new_root_enforcement_repeated"):
                volume._enforce_new_root(state, state["mount_fd"])
        assert len(h.root_chmod_calls) == 1
    assert cap.closed_summary()["root_mode_enforced_before_probe"] is True


def test_later_info_descriptor_text_still_matches_its_own_original_without_rebaseline(h):
    h.current_entities[-1]["content-hint"] = "Apple_APFS"
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_image_association_refused"):
        with h.prepare() as cap:
            h.current_entities[-1]["content-hint"] = "41504653-0000-11AA-AA11-00306543ECAC"
    assert len(h.root_chmod_calls) == 1


@pytest.mark.parametrize("change", ["owner", "remote", "browse", "noowners", "readonly", "device", "root_uid"])
def test_every_native_or_UID_precondition_refuses_before_any_new_root_mode_operation(h, change):
    h.created_root_mode = 0o755
    if change == "root_uid":
        h.root_change = lambda value: dict(value, st_uid=os.getuid() + 1)
    else:
        def changed(value):
            if change == "owner": value["owner"] += 1
            elif change == "remote": value["flags"] &= ~volume.MNT_LOCAL
            elif change == "browse": value["flags"] &= ~volume.MNT_DONTBROWSE
            elif change == "noowners": value["flags"] |= volume.MNT_IGNORE_OWNERSHIP
            elif change == "readonly": value["flags"] |= volume.MNT_RDONLY
            else: value["mounted_from"] = "/dev/disk998s1"
            return value
        h.native_change = changed
    with pytest.raises(volume.IsolatedVolumeRefusal):
        with h.prepare(): pytest.fail("unqualified native root identity admitted")
    assert h.root_chmod_calls == [] and stat.S_IMODE(REAL_STAT(h.mount).st_mode) == 0o755


def test_selected_info_unknown_field_drift_refuses_original_canonical_identity(h):
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_image_association_refused"):
        with h.prepare() as cap:
            def changed(payload):
                payload["images"][-1]["unexpected-vendor-metadata"] = "PRIVATE_NOT_A_NEW_BASELINE"
                return payload
            h.info_change = changed
    assert len(h.root_chmod_calls) == 1


def test_terminal_node_drift_cannot_use_new_snapshot_as_original(h):
    with h.prepare() as cap: pass
    h.node_change = lambda value: dict(value, st_ino=value["st_ino"] + 1)
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_device_node_changed"):
        cap.check_after_close()
    h.node_change = lambda value: value
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_failure_latched"): cap.closed_summary()


def test_original_root_GID_cannot_drift_after700_seal_or_reset_failure(h):
    with pytest.raises(volume.IsolatedVolumeRefusal):
        with h.prepare() as cap:
            h.root_change = lambda value: dict(value, st_gid=value["st_gid"] + 1)
            with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_new_root_identity_changed"):
                cap.check()
            h.root_change = lambda value: value
            with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_failure_latched"): cap.check()
    assert len(h.root_chmod_calls) == 1


def test_no_original_command_means_no_association_diagnostic_or_authority():
    value = volume.association_diagnostic()
    assert value["status"] == "not_observed" and value["authority"]["source_admitted"] is False
    value["authority"]["source_admitted"] = True
    assert volume.association_diagnostic()["authority"]["source_admitted"] is False


def test_device_node_witness_uses_nofollow_metadata_never_a_raw_device_open(monkeypatch):
    sentinel, opened = object(), []
    def forbidden(*args, **kwargs):
        opened.append(True)
        raise AssertionError("raw device open is forbidden")
    with monkeypatch.context() as patch:
        patch.setattr(os, "open", forbidden)
        patch.setattr(Path, "lstat", lambda unused: sentinel)
        observed = volume._device_node_stat("/dev/disk999s1")
    assert observed is sentinel and opened == []


def test_association_mismatch_snapshot_survives_refusal_without_private_values(h):
    h.attach_entities = deepcopy(h.current_entities)
    h.attach_entities[-1]["mount-point"] = "/FABRICATED_WRONG_MOUNT_PRIVATE"
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_attach_association_refused"):
        with h.prepare(): pytest.fail("wrong original attach mount admitted")
    report = volume.association_diagnostic()
    assert report["attach_raw_sha256"] and report["info_raw_sha256"] is None
    assert report["authority"]["ready_for_backtest"] is False
    assert "PRIVATE" not in canonical_json(report) and "/dev/" not in canonical_json(report)


def test_original_info_device_or_mount_mismatch_is_projected_before_abort(h):
    h.attach_entities = deepcopy(h.current_entities)
    h.current_entities[-1]["dev-entry"] = "/dev/disk998s1"
    with pytest.raises(volume.IsolatedVolumeRefusal, match="isolated_image_association_refused"):
        with h.prepare(): pytest.fail("different mounted device admitted")
    report = volume.association_diagnostic()
    assert report["mismatching_field_names"] == ["dev-entry"]
    assert report["mounted_devices_equal"] is False and report["mount_points_equal"] is True
    assert not h.root_chmod_calls


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
