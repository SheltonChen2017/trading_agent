"""Distinct read-only negative evidence; never revive or qualify exec13448.

Owner operational-history attestation is a registered prerequisite. Current
original read-only FDs, full ancestry, exact claim/code reconstruction and
native backing association support a conservative eight-reservation exposure.
Actual old spending/exit remain unknown; no old capture capability is minted.
"""
from contextlib import ExitStack
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import time

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import short_interest_lane_batch_guard as lane
from scripts import short_interest_count_response_volume as volume
from scripts import load_short_interest_count_epoch_ledger as archive
from research.short_interest_etf import native_count_run13448_exposure as exposure_model
from research.short_interest_etf import native_count_recovery_budget as plans

ROOT = lane.ROOT
DRIVER = "scripts/resolve_short_interest_count_run13448.py"
PROTOCOL_SHA256 = "d38e077d78ea5249f90d2669d165a6a6238ddac4b1947d422b570c7029b30919"
OLD_HEAD = "e7567635cea6e921d6cecef15e67517a1689c5f6"
OLD_REMOTE = "d6af672b3c8198712228bbd7b5eef35777283b1a"
OLD_PLAN = "2aa15b2fae72b6421a75702ea961af530a3b0901de342f670c21e1caaa328cd0"
OLD_OPERATOR = "660af15547c1d518df352f563adde4da1ebc4e4b88bbf5a75b06b271343906d9"
OLD_MANIFEST_SHA256 = "662615638960744fe8c67e9e5cc47093370bfaf201181f8098d7d672660c21d6"
OLD_PATH_LIST_SHA256 = "590904dc5a48401a4bea9704198143de77ffbfa37c73ca8e6fa59a94b327b621"
HISTORICAL_PATHS = ('data/__init__.py', 'data/exchange_calendar.py', 'data/financial_primitives.py', 'data/hashing.py', 'ml/__init__.py', 'ml/immutable_io.py', 'research/__init__.py', 'research/short_interest_etf/__init__.py', 'research/short_interest_etf/availability.py', 'research/short_interest_etf/contracts.py', 'research/short_interest_etf/finra_source_qualification.py', 'research/short_interest_etf/massive_action_supplement.py', 'research/short_interest_etf/massive_class_denominator.py', 'research/short_interest_etf/native_count_epoch_ledger.py', 'research/short_interest_etf/native_count_recovery_budget.py', 'research/short_interest_etf/native_dated_class_reference.py', 'research/short_interest_etf/native_dated_identity.py', 'research/short_interest_etf/native_grouped_market_source.py', 'research/short_interest_etf/native_listed_venue_namespace.py', 'research/short_interest_etf/native_parallel_count_contract.py', 'research/short_interest_etf/native_population_class_matrix.py', 'research/short_interest_etf/native_reported_anchor_cache.py', 'research/short_interest_etf/native_reported_anchor_plan.py', 'research/short_interest_etf/preregistration.py', 'research/short_interest_etf/sharadar_actual_input_binding.py', 'research/short_interest_etf/sharadar_companion_qualification.py', 'research/short_interest_etf/sharadar_master_segments.py', 'research/short_interest_etf/sharadar_native_master_index.py', 'research/short_interest_etf/sharadar_native_observations.py', 'research/short_interest_etf/sharadar_securities_master.py', 'scripts/build_short_interest_native_master_offline.py', 'scripts/capture_short_interest_bounded_count_chunk.py', 'scripts/capture_short_interest_count_recovery.py', 'scripts/capture_short_interest_durable_counts.py', 'scripts/capture_short_interest_native_anchor_cache.py', 'scripts/capture_short_interest_native_grouped_market.py', 'scripts/capture_short_interest_native_identity.py', 'scripts/capture_short_interest_native_parallel_counts.py', 'scripts/capture_short_interest_native_population.py', 'scripts/capture_short_interest_native_reported_count_round.py', 'scripts/capture_short_interest_securities_master.py', 'scripts/continue_short_interest_native_identity.py', 'scripts/diagnose_short_interest_body_receipt_custody.py', 'scripts/diagnose_short_interest_count_custody.py', 'scripts/diagnose_short_interest_immutable_metadata.py', 'scripts/diagnose_short_interest_isolated_immutable_metadata.py', 'scripts/diagnose_short_interest_new_metadata_custody.py', 'scripts/finalize_short_interest_master_offline.py', 'scripts/load_short_interest_count_epoch_ledger.py', 'scripts/load_short_interest_native_class_matrix.py', 'scripts/load_short_interest_native_identity_continuation.py', 'scripts/preflight_short_interest_native_reported_anchors.py', 'scripts/qualify_finra_short_interest.py', 'scripts/qualify_sharadar_companion.py', 'scripts/qualify_short_interest_action_supplement.py', 'scripts/read_short_interest_native_identity_continuation.py', 'scripts/run_short_interest_body_receipt_offline.py', 'scripts/run_short_interest_isolated_custody_offline.py', 'scripts/short_interest_body_receipt_custody.py', 'scripts/short_interest_body_receipt_monitor.py', 'scripts/short_interest_body_receipt_volume.py', 'scripts/short_interest_closed_count_chunk.py', 'scripts/short_interest_count_checkpoint.py', 'scripts/short_interest_count_control_custody.py', 'scripts/short_interest_count_durable_budget.py', 'scripts/short_interest_count_durable_transport.py', 'scripts/short_interest_count_negative_custody.py', 'scripts/short_interest_count_response_custody.py', 'scripts/short_interest_count_response_volume.py', 'scripts/short_interest_count_source_authority.py', 'scripts/short_interest_count_transport_union.py', 'scripts/short_interest_immutable_metadata.py', 'scripts/short_interest_immutable_transition_diagnostics.py', 'scripts/short_interest_isolated_custody_volume.py', 'scripts/short_interest_keychain.py', 'scripts/short_interest_lane_batch_guard.py', 'scripts/short_interest_new_metadata_custody.py', 'scripts/short_interest_recovery_diagnostics.py', 'scripts/short_interest_recovery_transport.py', 'scripts/short_interest_refused_count_snapshot.py', 'scripts/short_interest_reported_anchor_cache.py', 'scripts/short_interest_targeted_immutable_monitor.py', 'scripts/stream_short_interest_native_identity_continuation.py', 'scripts/verify_short_interest_native_identity_continuation.py')
NAMESPACE = Path("artifacts/short_interest/native_reported_counts/count-response-20261027-v1-" + OLD_PLAN + "-chunk001")
CLAIM = "mount/claim/claim.spent.json"
CONTAINERS = ("mount/capture/starts", "mount/capture/received", "mount/capture/responses")
LEAF_PINS = ((CONTAINERS[0], (19, 1793115452569302191, 1793115452569366316)),
    (CONTAINERS[1], (20, 1793115452905836532, 1793115452905944324)),
    (CONTAINERS[2], (21, 1793115453257575693, 1793115453257656443)),
    (CLAIM, (23, 1793115455606139543, 1793115456838350715)))
MAXIMUM_SECONDS = 1800
_MONOTONIC = time.monotonic
OWNER_HISTORY = ("SI-AUTH-20261028-02", "No, none of those changes",
    "owner excludes restore replacement detach remount and manual clock changes since original run")
_ISSUED, _FAILED = {}, set()
_STAGE = "registration"
_STAGES = frozenset(("registration", "current_code", "historical_code", "footprint_open",
    "claim_read", "allocation", "context_closure", "terminal_audit"))
_CODES = frozenset("resolution_registration_pending resolution_root_changed resolution_clock_changed resolution_deadline resolution_protection_changed resolution_path_changed resolution_membership_changed resolution_chronology_changed resolution_claim_changed resolution_code_changed resolution_native_changed resolution_factory_required resolution_capability_changed".split())
_CODES = _CODES | frozenset(("resolution_claim_clock_changed",))


class CountResolutionRefusal(ValueError): pass


def require(value, code):
    if not value: raise CountResolutionRefusal("REFUSED: " + code)


def failure_summary(error):
    code = None
    if type(error) is CountResolutionRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
            code = next((v for v in _CODES if args[0] == "REFUSED: " + v), None)
    return {"category": "local_contract_refusal" if code else "unknown_local_error", "contract_code": code,
        "stage": _STAGE if type(_STAGE) is str and _STAGE in _STAGES else "registration"}


def authority():
    return {"negative_evidence_only": True, "historical_actual_counts_known": False,
        "old_capture_or_source_admitted": False, "source_dispatch_authority": False,
        "refund_authority": False, "coverage_contribution": 0, "ready_for_backtest": False,
        "provider_HTTP": 0, "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0}


def policy():
    return {"schema": "si-count-run13448-negative-resolution-v1", "owner_history": OWNER_HISTORY,
        "root": str(ROOT), "namespace": str(NAMESPACE), "old_head": OLD_HEAD, "old_remote": OLD_REMOTE,
        "old_plan": OLD_PLAN, "old_operator": OLD_OPERATOR, "old_manifest": OLD_MANIFEST_SHA256,
        "historical_path_list": OLD_PATH_LIST_SHA256, "later_leaf_pins": LEAF_PINS,
        "maximum_seconds": MAXIMUM_SECONDS, "escrow_STARTs": 8, "escrow_bytes": 16777216,
        "history": "owner_attested_no_volume_rollback_replacement_reattach_or_manual_clock_change_plus_full_ancestry_chronology",
        "claim": "prestat_regular0600_owner_singlelink_flags2_exact534_then_original_nonblocking_nofollow_ROFD_canonical_E756_UTC_microsecond_Z_after_containers_before_claim_birth",
        "footprint": "original_current_nofollow_ROFD_root_full_ancestry_backing_claim_empty_containers_and_metadata_only_system0700_root_owner_mount_GID_pin",
        "native": "local_APFS_nobrowse_owners_honored_writable_unique_global_image_device_mount_no_shadow",
        "current_code": "original_HeldFiles_working_equals_committed_complete_code_catalogue_initial_exit_and_fresh_context",
        "terminal_order": "all_Git_code_hash_callbacks_contexts_exit_then_original_FD_native_metadata_membership_then_FD_cleanup_named_original_pins_and_pure_captured_clock_no_late_callback",
        "actual_old_counts": "unknown_no_positive_source_or_old_context_closure", "authority": authority()}


def registered():
    require(hash_payload(policy()) == PROTOCOL_SHA256
        and len(HISTORICAL_PATHS) == 84 and hash_payload(list(HISTORICAL_PATHS)) == OLD_PATH_LIST_SHA256
        and OWNER_HISTORY == ("SI-AUTH-20261028-02", "No, none of those changes",
            "owner excludes restore replacement detach remount and manual clock changes since original run")
        and type(MAXIMUM_SECONDS) is int and MAXIMUM_SECONDS == 1800,
        "resolution_registration_pending")


def code_paths():
    # Include current dependencies, not only the old claim's historical84.
    from scripts import capture_short_interest_durable_counts as producer
    return tuple(sorted(set((*producer.code_paths(), DRIVER,
        "research/short_interest_etf/native_count_run13448_exposure.py"))))


def _fact(info):
    return {"dev": info.st_dev, "ino": info.st_ino, "uid": info.st_uid, "gid": info.st_gid,
        "mode": info.st_mode, "links": info.st_nlink, "size": info.st_size,
        "birth": round(info.st_birthtime * 1e9), "mtime": info.st_mtime_ns,
        "ctime": info.st_ctime_ns, "flags": info.st_flags}


def _identity(info):
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)


def _claim_expected(manifest, started):
    require(hash_payload(manifest) == OLD_MANIFEST_SHA256, "resolution_code_changed")
    identity = hash_payload({"git_commit": OLD_HEAD,
        "files": [{"path": p, "sha256": manifest[p]} for p in HISTORICAL_PATHS]})
    registration = hash_payload({"plan_sha256": OLD_PLAN, "chunk": 1, "protocol_sha256": OLD_OPERATOR,
        "head": OLD_HEAD, "remote": OLD_REMOTE, "code_identity_sha256": identity,
        "code_manifest_sha256": hash_payload(manifest)})
    return {"schema": "si-count-spent-claim-v1", "spent": True, "chunk": 1,
        "operator_protocol_sha256": OLD_OPERATOR, "registration_sha256": registration,
        "plan_sha256": OLD_PLAN, "runtime_head": OLD_HEAD, "actual_remote": OLD_REMOTE,
        "started_at": started, "dispatch_authority": False, "source_admitted": False}


def check_chronology(facts):
    claim = facts[CLAIM]; born = claim["birth"]
    require((facts[""]["ino"], facts[""]["mtime"], facts[""]["ctime"]) ==
        (46599617, 1793115450631577606, 1793115450631577606), "resolution_chronology_changed")
    require(facts["mount/capture"]["ino"] == 18
        and facts["mount/capture"]["ctime"] < born
        and facts[""]["ctime"] < born
        and facts["mount/claim"]["ctime"] <= claim["ctime"], "resolution_chronology_changed")
    for name, pin in LEAF_PINS:
        row = facts[name]
        require((row["ino"], row["mtime"], row["ctime"]) == pin, "resolution_chronology_changed")
        if name != CLAIM:
            require(row["links"] == 2 and abs(row["birth"] - row["mtime"]) <= 1000
                and row["mtime"] <= row["ctime"] < born, "resolution_chronology_changed")
    require(claim["flags"] == 2 and claim["size"] == 534
        and born <= claim["mtime"] <= claim["ctime"], "resolution_claim_changed")


def _native_association(mount_fd, image, mount):
    native = volume._native_statfs(mount_fd)
    require(native["fstype"] == "apfs" and native["owner"] == os.getuid()
        and native["mounted_on"] == str(mount) and type(native["flags"]) is int
        and native["flags"] & volume.MNT_LOCAL and native["flags"] & volume.MNT_DONTBROWSE
        and not native["flags"] & (volume.MNT_IGNORE_OWNERSHIP | volume.MNT_RDONLY),
        "resolution_native_changed")
    node = volume._node_pin(native["mounted_from"], os.fstat(mount_fd).st_dev)
    result = subprocess.run(["/usr/bin/hdiutil", "info", "-plist"], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, check=False)
    require(result.returncode == 0 and type(result.stdout) is bytes and 0 < len(result.stdout) <= 4 * 1024 ** 2,
        "resolution_native_changed")
    parsed = plistlib.loads(result.stdout)
    require(type(parsed) is dict and type(parsed.get("images")) is list and len(parsed["images"]) <= 64,
        "resolution_native_changed")
    selected = []
    global_devices, global_mounts = [], []
    for row in parsed["images"]:
        require(type(row) is dict and type(row.get("image-path")) is str, "resolution_native_changed")
        if row["image-path"] == str(image): selected.append(row)
        members = row.get("system-entities", [])
        require(type(members) is list and len(members) <= 64 and all(type(member) is dict for member in members),
            "resolution_native_changed")
        for member in members:
            if member.get("dev-entry") == native["mounted_from"]: global_devices.append((row, member))
            if member.get("mount-point") == str(mount): global_mounts.append((row, member))
    require(len(selected) == 1 and not any(k in selected[0] for k in ("shadow-path", "shadow-file")),
        "resolution_native_changed")
    entities = selected[0].get("system-entities")
    require(type(entities) is list and 1 <= len(entities) <= 16, "resolution_native_changed")
    mapped = [e for e in entities if type(e) is dict and e.get("mount-point") == str(mount)]
    require(len(mapped) == len(global_devices) == len(global_mounts) == 1
        and mapped[0].get("dev-entry") == native["mounted_from"]
        and global_devices[0][0] is selected[0] is global_mounts[0][0]
        and global_devices[0][1] is mapped[0] is global_mounts[0][1], "resolution_native_changed")
    return volume._mount_identity(native), node


class _HeldFootprint:
    """Own current reader FDs; none is an old capture/source capability."""
    def __init__(self, boundary):
        self.boundary, self.fds, self.facts = boundary, {}, {}
        self.base = ROOT / NAMESPACE
        self.stack, self.closed, self.nodes = ExitStack(), False, []
        try:
            require(ROOT.resolve() == ROOT and Path.cwd().resolve() == ROOT,
                "resolution_root_changed")
            root_info = ROOT.lstat(); self.root_pin = self._directory(root_info, private=False)
            self.root = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.stack.callback(os.close, self.root)
            require(self._directory(os.fstat(self.root), private=False) == self.root_pin, "resolution_path_changed")
            parent = self.root; prefix = Path()
            require(not NAMESPACE.is_absolute() and bool(NAMESPACE.parts) and ".." not in NAMESPACE.parts,
                "resolution_path_changed")
            for part in NAMESPACE.parts:
                self.boundary(); prefix /= part
                before = os.stat(part, dir_fd=parent, follow_symlinks=False)
                pin = self._directory(before, private=prefix == NAMESPACE)
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.stack.callback(os.close, fd)
                require(pin == self._directory(os.fstat(fd), private=prefix == NAMESPACE), "resolution_path_changed")
                key = "@" + str(prefix)
                self.nodes.append((key, parent, part, fd, pin, prefix == NAMESPACE))
                self.fds[key] = fd; parent = fd
            self.fds[""] = parent
            for name in ("mount", "mount/capture", "mount/claim", *CONTAINERS):
                parent_name, leaf = name.rsplit("/", 1) if "/" in name else ("", name)
                parent = self.fds[parent_name]
                before = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                pin = self._directory(before)
                fd = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.stack.callback(os.close, fd)
                require(pin == self._directory(os.fstat(fd)), "resolution_path_changed")
                self.nodes.append((name, parent, leaf, fd, pin, True))
                self.fds[name] = fd
            require(os.fstat(self.fds["mount"]).st_dev != os.fstat(self.fds[""]).st_dev,
                "resolution_native_changed")
            before = os.stat("claim.spent.json", dir_fd=self.fds["mount/claim"], follow_symlinks=False)
            self.claim_pin = self._claim(before)
            self.claim_fd = os.open("claim.spent.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self.fds["mount/claim"])
            self.stack.callback(os.close, self.claim_fd)
            require(self._claim(os.fstat(self.claim_fd)) == self.claim_pin
                == self._claim(os.stat("claim.spent.json", dir_fd=self.fds["mount/claim"], follow_symlinks=False)),
                "resolution_path_changed")
            self.pins = {name: _identity(os.fstat(fd)) for name, fd in self.fds.items()}
            before = os.stat("backing.sparseimage", dir_fd=self.fds[""], follow_symlinks=False)
            self.backing = self._backing(before)
            self.backing_fd = os.open("backing.sparseimage", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self.fds[""])
            self.stack.callback(os.close, self.backing_fd)
            require(self._backing(os.fstat(self.backing_fd)) == self.backing, "resolution_path_changed")
            self.mount_gid = os.fstat(self.fds["mount"]).st_gid
            self.system = self._system(os.stat(".fseventsd", dir_fd=self.fds["mount"], follow_symlinks=False))
            self.native = _native_association(self.fds["mount"], self.base / "backing.sparseimage", self.base / "mount")
            self.facts = self.observe()
            check_chronology(self.facts); self.audit()
        except BaseException:
            self.stack.close(); raise

    def _directory(self, info, *, private=True):
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and (stat.S_IMODE(info.st_mode) == 0o700 if private else not stat.S_IMODE(info.st_mode) & 0o022),
            "resolution_protection_changed")
        return _identity(info)

    def _claim(self, info):
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
            and info.st_dev == os.fstat(self.fds["mount"]).st_dev and info.st_size == 534
            and info.st_flags == 2, "resolution_protection_changed")
        return _fact(info)

    def _backing(self, info):
        require(info.st_flags in (0, 64), "resolution_protection_changed")
        return volume._backing(info), info.st_gid, info.st_flags

    def _system(self, info):
        require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
            and info.st_uid == 0 and info.st_gid == self.mount_gid
            and info.st_dev == os.fstat(self.fds["mount"]).st_dev, "resolution_protection_changed")
        return _identity(info), info.st_flags

    def observe(self):
        facts = {name: _fact(os.fstat(self.fds[name])) for name in ("", "mount", "mount/capture", "mount/claim", *CONTAINERS)}
        info = os.fstat(self.claim_fd)
        require(self._claim(info) == self.claim_pin, "resolution_path_changed")
        facts[CLAIM] = _fact(info)
        return facts

    def audit(self, *, callbacks=True):
        require(not self.closed, "resolution_capability_changed")
        if callbacks: self.boundary()
        require(ROOT.resolve() == ROOT and self._directory(ROOT.lstat(), private=False)
            == self._directory(os.fstat(self.root), private=False) == self.root_pin, "resolution_path_changed")
        for name, parent, leaf, fd, pin, private in self.nodes:
            path = ROOT / name[1:] if name.startswith("@") else self.base / name
            require(self._directory(os.fstat(fd), private=private) == pin
                == self._directory(os.stat(leaf, dir_fd=parent, follow_symlinks=False), private=private)
                == self._directory(path.lstat(), private=private), "resolution_path_changed")
        require(self._backing(os.fstat(self.backing_fd)) == self.backing
            == self._backing(os.stat("backing.sparseimage", dir_fd=self.fds[""], follow_symlinks=False)),
            "resolution_path_changed")
        require(_native_association(self.fds["mount"], self.base / "backing.sparseimage", self.base / "mount") == self.native,
            "resolution_native_changed")
        required = {"": {"backing.sparseimage", "mount"}, "mount": {".fseventsd", "capture", "claim"},
            "mount/capture": {"starts", "received", "responses"}, "mount/claim": {"claim.spent.json"},
            **{name: set() for name in CONTAINERS}}
        for name, names in required.items():
            require(set(os.listdir(self.fds[name])) == names, "resolution_membership_changed")
        require(self._system(os.stat(".fseventsd", dir_fd=self.fds["mount"], follow_symlinks=False)) == self.system,
            "resolution_membership_changed")
        now = self.observe()
        require(all(now[name] == old for name, old in self.facts.items() if name != "mount"),
            "resolution_path_changed")
        require(_fact((self.base / CLAIM).lstat()) == self.facts[CLAIM], "resolution_path_changed")
        check_chronology(now)

    def read_claim(self):
        self.audit(); os.lseek(self.claim_fd, 0, os.SEEK_SET)
        raw = os.read(self.claim_fd, 534)
        require(type(raw) is bytes and len(raw) == 534, "resolution_claim_changed")
        self.audit(); return raw

    def close(self):
        try: self.stack.close()
        finally: self.closed = True

    def audit_after_close(self):
        """Terminal named observations against ORIGINAL pins, no callback or adoption."""
        require(self.closed and ROOT.resolve() == ROOT
            and self._directory(ROOT.lstat(), private=False) == self.root_pin, "resolution_path_changed")
        for name, unused_parent, unused_leaf, unused_fd, pin, private in self.nodes:
            path = ROOT / name[1:] if name.startswith("@") else self.base / name
            require(self._directory(path.lstat(), private=private) == pin, "resolution_path_changed")
        require(ROOT.resolve() == ROOT and self.base.resolve() == self.base
            and self._directory(ROOT.lstat(), private=False) == self.root_pin, "resolution_path_changed")
        require(self._backing((self.base / "backing.sparseimage").lstat()) == self.backing,
            "resolution_path_changed")
        required = {"": {"backing.sparseimage", "mount"}, "mount": {".fseventsd", "capture", "claim"},
            "mount/capture": {"starts", "received", "responses"}, "mount/claim": {"claim.spent.json"},
            **{name: set() for name in CONTAINERS}}
        for name, names in required.items():
            path = self.base / name
            require(path.resolve() == path and set(os.listdir(path)) == names, "resolution_membership_changed")
        # No system contents are opened/listed, including after descriptor cleanup.
        system = (self.base / "mount/.fseventsd").lstat()
        require(stat.S_ISDIR(system.st_mode) and _identity(system) == self.system[0]
            and system.st_flags == self.system[1], "resolution_membership_changed")
        for name, original in self.facts.items():
            current = (self.base / name).lstat()
            if name == "mount": require(_identity(current) == self.pins[name], "resolution_path_changed")
            else: require(_fact(current) == original, "resolution_path_changed")
        for name, unused_parent, unused_leaf, unused_fd, pin, private in self.nodes:
            path = ROOT / name[1:] if name.startswith("@") else self.base / name
            require(self._directory(path.lstat(), private=private) == pin, "resolution_path_changed")
        require(ROOT.resolve() == ROOT and self.base.resolve() == self.base
            and self._directory(ROOT.lstat(), private=False) == self.root_pin, "resolution_path_changed")


class Run13448Resolution:
    __slots__ = ("_anchor",)
    def __init__(self): raise CountResolutionRefusal("REFUSED: resolution_factory_required")
    def public_summary(self): return json.loads(resolution_binding(self)[3])


def resolution_binding(value):
    try:
        row = _ISSUED.get(id(value)) if type(value) is Run13448Resolution else None
        require(type(row) is tuple and len(row) == 6 and row[0] is value and value._anchor is row
            and id(value) not in _FAILED, "resolution_capability_changed")
        exposure_model.exposure_binding(row[1])
        require(type(row[3]) is bytes and hash_bytes(row[3]) == row[4], "resolution_capability_changed")
        return row
    except BaseException:
        if type(value) is Run13448Resolution: _FAILED.add(id(value))
        raise


def _current_code_manifest(guard, head, held, *, paths=None):
    names = code_paths() if paths is None else paths
    manifest = {}
    for path in names:
        guard.check()
        raw = held.read(ROOT / path, 8 * 1024 ** 2)
        committed = archive.count.old.cache._git(ROOT, ["show", head + ":" + path], guard)
        require(type(raw) is bytes and type(committed) is bytes
            and len(raw) <= 8 * 1024 ** 2 and hash_bytes(raw) == hash_bytes(committed),
            "resolution_code_changed")
        manifest[path] = hash_bytes(raw)
    held.check(); return manifest


def resolve_registered(ledger, *, runtime_head, actual_remote):
    """No source operation. Fresh independent evidence closes before issuance."""
    global _STAGE
    _STAGE = "registration"
    registered()
    require(ROOT.resolve() == ROOT and Path.cwd().resolve() == ROOT
        and all(type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value)
            for value in (runtime_head, actual_remote)), "resolution_root_changed")
    guard = lane.LaneGuard(ROOT, expected_head=runtime_head, expected_remote=actual_remote)
    clock = _MONOTONIC; began = previous = clock()
    require(type(began) in (int, float) and 0 <= began <= 2 ** 53, "resolution_clock_changed")
    def tick():
        nonlocal previous
        now = clock()
        require(type(now) in (int, float) and 0 <= previous <= now <= 2 ** 53, "resolution_clock_changed")
        require(now - began <= MAXIMUM_SECONDS, "resolution_deadline")
        previous = now
    def boundary(): tick(); guard.check()
    guard.refresh(); tick()
    # Original pure plan reconstruction binds all query/chunk semantics before
    # assigning possible tries. No ticket or source operation is opened.
    old_plan = plans.freeze_count_recovery_plan(ledger)
    require(old_plan.sha256 == OLD_PLAN, "resolution_claim_changed")
    _STAGE = "historical_code"; manifest = {}
    for path in HISTORICAL_PATHS:
        boundary()
        raw = archive.count.old.cache._git(ROOT, ["show", OLD_HEAD + ":" + path], guard)
        require(type(raw) is bytes and len(raw) <= 8 * 1024 ** 2, "resolution_code_changed")
        manifest[path] = hash_bytes(raw)
    require(hash_payload(manifest) == OLD_MANIFEST_SHA256, "resolution_code_changed")
    footprint = None
    try:
        _STAGE = "current_code"
        with archive.count.old.cache.HeldFiles(tuple(ROOT / name for name in code_paths()),
                protected=False, boundary=boundary) as code:
            current_manifest = _current_code_manifest(guard, runtime_head, code)
            _STAGE = "footprint_open"; footprint = _HeldFootprint(boundary)
            _STAGE = "claim_read"; raw = footprint.read_claim()
            def pairs(items):
                d = {}
                for k, v in items:
                    require(type(k) is str and k not in d, "resolution_claim_changed"); d[k] = v
                return d
            claim = json.loads(raw, object_pairs_hook=pairs,
                parse_constant=lambda x: (_ for _ in ()).throw(CountResolutionRefusal("REFUSED: resolution_claim_changed")))
            require(type(claim) is dict and type(claim.get("started_at")) is str, "resolution_claim_changed")
            try: stamp = datetime.fromisoformat(claim["started_at"].replace("Z", "+00:00"))
            except (ValueError, TypeError): raise CountResolutionRefusal("REFUSED: resolution_claim_clock_changed") from None
            require(stamp.tzinfo is not None and stamp.utcoffset() == timezone.utc.utcoffset(stamp)
                and stamp.date().isoformat() == "2026-10-27", "resolution_claim_clock_changed")
            require(claim["started_at"] == stamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "resolution_claim_changed")
            delta = stamp - datetime(1970, 1, 1, tzinfo=timezone.utc)
            started_ns = (delta.days * 86400 + delta.seconds) * 1000000000 + delta.microseconds * 1000
            require(started_ns <= footprint.facts[CLAIM]["birth"] + 1000
                and max(footprint.facts[name]["ctime"] for name in CONTAINERS) <= started_ns + 1000,
                "resolution_claim_clock_changed")
            require(raw == canonical_json(_claim_expected(manifest, claim["started_at"])).encode(), "resolution_claim_changed")
            _STAGE = "allocation"; exposure = exposure_model.freeze_run13448_exposure(ledger)
            report = {"schema": "si-count-run13448-negative-resolution-observation-v1",
                "status": "negative_evidence_closed_only", "old_process_exit": None, "old_actual_HTTP": None,
                "old_actual_STARTs": None, "old_actual_bytes": None, "owner_history_sha256": hash_payload(OWNER_HISTORY),
                "protocol_sha256": PROTOCOL_SHA256, "claim_sha256": hash_bytes(raw),
                "footprint_sha256": hash_payload(footprint.facts), "historical_code_manifest_sha256": hash_payload(manifest),
                "current_code_manifest_sha256": hash_payload(current_manifest),
                "negative_exposure_sha256": exposure.sha256, "authority": authority()}
            footprint.audit(); guard.refresh()
            require(_current_code_manifest(guard, runtime_head, code) == current_manifest, "resolution_code_changed")
            _STAGE = "context_closure"
        with archive.count.old.cache.HeldFiles(tuple(ROOT / name for name in code_paths()),
                protected=False, boundary=boundary) as final_code:
            require(_current_code_manifest(guard, runtime_head, final_code) == current_manifest, "resolution_code_changed")
        # Every Git/code/context callback completes BEFORE the original physical evidence sweep.
        guard.refresh(); tick()
        raw_report = canonical_json(report).encode(); value = object.__new__(Run13448Resolution)
        row = value, exposure, ledger, raw_report, hash_bytes(raw_report), object()
        _STAGE = "terminal_audit"; footprint.audit(callbacks=False)
    finally:
        if footprint is not None: footprint.close()
    footprint.audit_after_close()
    tick()  # Original captured pure clock follows all original cleanup and named metadata.
    value._anchor = row; _ISSUED[id(value)] = row
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description="Registered read-only negative count accounting evidence")
    parser.add_argument("command", choices=("run_registered",))
    parser.add_argument("--runtime-head", required=True); parser.add_argument("--actual-remote", required=True)
    args = parser.parse_args(argv)
    try:
        registered()
        require(all(type(v) is str and re.fullmatch(r"[0-9a-f]{40}", v)
            for v in (args.runtime_head, args.actual_remote)), "resolution_registration_pending")
        guard = lane.LaneGuard(ROOT, expected_head=args.runtime_head, expected_remote=args.actual_remote)
        guard.refresh()
        paths = archive.code_paths()
        with archive.count.old.cache.HeldFiles(tuple(ROOT / name for name in paths),
                protected=False, boundary=guard.check) as code:
            manifest = _current_code_manifest(guard, args.runtime_head, code, paths=paths)
        guard.refresh()
        print(canonical_json({"schema": "si-count-negative-resolution-start-v1", "stage": "old_archive_replay",
            "runtime_head": args.runtime_head, "protocol_sha256": PROTOCOL_SHA256, "authority": authority()}), flush=True)
        with archive.load_registered_count_epoch_ledger(ROOT, runtime_head=args.runtime_head,
                actual_remote=args.actual_remote, complete_code_manifest=manifest) as loaded:
            pass
        original = loaded.closed_summary()
        ledger = loaded._anchor[0]
        require(original["model_ledger_sha256"] == ledger.sha256, "resolution_capability_changed")
        result = resolve_registered(ledger, runtime_head=args.runtime_head, actual_remote=args.actual_remote)
        print(canonical_json(result.public_summary()), flush=True)
        return 0
    except BaseException as error:
        print(canonical_json({"status": "refused", "fixed_diagnostic": failure_summary(error),
            "authority": authority()}), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
