"""Fixed retained monthly-source custody; no capture or input admission.

Only the registered 2026-10-14 run may be opened.  Its original global controls,
spent claim and eight historical code blobs are authenticated before private
bytes escape.  Financial/panel qualification belongs to a separate consumer.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
from types import MappingProxyType

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_market_input_protocol as inputs
from scripts import short_interest_lane_batch_guard as lane
from scripts.qualify_finra_short_interest import _require_capture_platform

DIRECTORY = Path("artifacts/short_interest/native_market_inputs/native-market-inputs-20261014T004232Z")
SOURCE_HEAD = "f61a40bf497747cffdda367d2a20c393383c8232"
SOURCE_REMOTE = "1f90c626328a236c51e78f57e0fe301e0412aabf"
PROTOCOL_SHA256 = "b95ecfeefdc8b0bd01a7cb9fd1ea7b250e777356a2db8f7a026810899e7582b1"
CLAIM_ID = "f72fbde4ecd72650c46ba1455120980868ee2a887420597102801537f57e4f27"
CLAIM_SHA256 = "3d0ace1414f0ebc0e09a3841e9f94418595fdfcbd84ad0576e0486a68b675371"
MANIFEST_SHA256 = "ac6c1d19af27aefbc38d3bdf0aa52ec5460054edd06779fbc81be58029621afa"
CODE_IDENTITY_SHA256 = "700e12c52553920c8f7dad7d17a50d42110e24cbab92ea31d6d50be15f4e4ee4"
CODE_FILES = ("data/hashing.py", "ml/immutable_io.py", "scripts/qualify_finra_short_interest.py",
    "scripts/qualify_sharadar_companion.py", "scripts/qualify_short_interest_action_supplement.py",
    "scripts/short_interest_keychain.py", "research/short_interest_etf/native_market_input_protocol.py",
    "scripts/capture_short_interest_native_market_inputs.py")
CONTROL_PINS = {
    "protocol.json": "d4d8b9d4d5e2c963e689ef45b659185c04e378100833df9de4d91354943fddd5",
    "started.json": "e9705854496b39f2d36da1d5b7f6183fe73e59f97ebbe31f5e6a33842cb5fe9e",
    "inventory.private.json": "65648c794f92e9a65330949e59509b950b8de8b1565cf8eab76721cba3f7b284",
    "completed.json": "9c58ad26813b746e93e89117a226a48215c649bcf3e73661d782085910e4ba0c",
}
ATTEMPTS = 112
MEMBERS = 452
MAXIMUM_BYTES = 8 * 1024 ** 2
READ_BATCH = 64


class MonthlySnapshotRefusal(ValueError):
    """Fixed, non-source-bearing offline custody failures."""


def require(value, code):
    if not value:
        raise MonthlySnapshotRefusal("REFUSED: " + code)


def parsed(raw):
    require(type(raw) is bytes and len(raw) <= MAXIMUM_BYTES, "bounded_control_bytes_required")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_control_key")
            result[key] = value
        return result
    def nonfinite(unused):
        raise MonthlySnapshotRefusal("REFUSED: nonfinite_control")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError):
        raise MonthlySnapshotRefusal("REFUSED: strict_control_JSON_required") from None


def _clock(value):
    require(type(value) is str and value.endswith("Z"), "UTC_control_clock_required")
    try:
        at = datetime.fromisoformat(value[:-1] + "+00:00")
        require(at.utcoffset() == timezone.utc.utcoffset(at), "UTC_control_clock_required")
        return at
    except ValueError:
        raise MonthlySnapshotRefusal("REFUSED: UTC_control_clock_required") from None


def expected_names():
    names = set(CONTROL_PINS)
    for ordinal in range(1, ATTEMPTS + 1):
        names.update(f"attempt-{ordinal:05d}" + suffix for suffix in
            (".started.json", ".received.json", ".raw", ".refusals.private.json"))
    require(len(names) == MEMBERS, "fixed_monthly_member_shape_changed")
    return tuple(sorted(names))


def _file_stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode),
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory_stamp(info, *, closed):
    values = (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))
    return (*values, info.st_mtime_ns, info.st_ctime_ns) if closed else values


def _git(root, arguments, guard):
    guard.check()
    try:
        result = subprocess.run(["git", *arguments], cwd=root, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False)
    finally:
        guard.check()
    require(result.returncode == 0 and type(result.stdout) is bytes
            and len(result.stdout) <= 16 * 1024 ** 2, "historical_Git_blob_required")
    return result.stdout


def _historical_code(root, guard):
    require(len(CODE_FILES) == 8 and len(set(CODE_FILES)) == 8,
            "exact_eight_historical_code_files_required")
    require(_git(root, ["merge-base", "--is-ancestor", SOURCE_HEAD, guard.binding()[1]], guard) == b"",
            "historical_creator_not_lane_ancestor")
    entries = [{"path": name, "sha256": hash_bytes(_git(root,
        ["show", SOURCE_HEAD + ":" + name], guard))} for name in CODE_FILES]
    require(hash_payload({"git_commit": SOURCE_HEAD, "files": entries}) == CODE_IDENTITY_SHA256,
            "historical_creator_code_identity_changed")


def _same(actual, expected):
    return canonical_json(actual) == canonical_json(expected)


def _controls(controls, claim_raw):
    protocol, start, inventory, completed = (parsed(controls[name]) for name in
        ("protocol.json", "started.json", "inventory.private.json", "completed.json"))
    claim = parsed(claim_raw)
    expected_protocol = inputs.market_input_protocol()
    require(_same(protocol, expected_protocol) and hash_payload(protocol) == PROTOCOL_SHA256,
            "original_monthly_protocol_changed")
    require(type(start) is dict and type(claim) is dict
            and _same(start, {"schema": "si-native-market-input-start-v1", "code_head": SOURCE_HEAD,
                "remote_head": SOURCE_REMOTE, "protocol_sha256": PROTOCOL_SHA256,
                "code_identity_sha256": CODE_IDENTITY_SHA256, "started_at": start.get("started_at"),
                "maximum_requests": expected_protocol["maximum_requests"], "outcome_looks": 0, "qc_attempts": 0}),
            "original_monthly_start_changed")
    require(_same(claim, {"schema": "si-native-market-input-budget-v1", "claim_sha256": CLAIM_ID,
        "code_head": SOURCE_HEAD, "remote_head": SOURCE_REMOTE, "run_id": DIRECTORY.name,
        "protocol_sha256": PROTOCOL_SHA256, "maximum_requests": expected_protocol["maximum_requests"],
        "started_at": start["started_at"], "restart_or_resume": False}), "original_spent_budget_changed")
    require(type(inventory) is dict and set(inventory) == {"schema", "code_head", "protocol_sha256",
        "retrieved_at", "panels", "total_raw_bytes", "total_raw_rows", "http_attempts", "source_only",
        "data_or_fitness_admitted", "financial_values_normalized", "signal_or_return_computed",
        "outcome_looks", "qc_attempts", "backtest_result_exists", "report_sha256"},
        "original_inventory_shape_changed")
    require(inventory["schema"] == "si-native-market-input-inventory-v1"
        and inventory["code_head"] == SOURCE_HEAD and inventory["protocol_sha256"] == PROTOCOL_SHA256
        and type(inventory["http_attempts"]) is int and inventory["http_attempts"] == ATTEMPTS
        and type(inventory["panels"]) is list and len(inventory["panels"]) == len(expected_protocol["panels"])
        and type(inventory["total_raw_bytes"]) is int and 0 <= inventory["total_raw_bytes"] <= inputs.MAXIMUM_RAW_BYTES
        and type(inventory["total_raw_rows"]) is int and 0 <= inventory["total_raw_rows"] <= inputs.MAXIMUM_ROWS
        and inventory["source_only"] is True
        and all(inventory[name] is False for name in ("data_or_fitness_admitted", "financial_values_normalized",
            "signal_or_return_computed", "backtest_result_exists"))
        and all(type(inventory[name]) is int and inventory[name] == 0 for name in ("outcome_looks", "qc_attempts"))
        and hash_payload({key: value for key, value in inventory.items() if key != "report_sha256"})
            == inventory["report_sha256"], "original_source_only_inventory_changed")
    require(type(completed) is dict and _same(completed, {
        "schema": "si-native-market-input-complete-v1", "status": "private_market_source_capture_complete",
        "code_head": SOURCE_HEAD, "protocol_sha256": PROTOCOL_SHA256, "http_attempts": ATTEMPTS,
        "private_report_sha256": inventory["report_sha256"], "completed_at": completed.get("completed_at"),
        "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}), "original_completion_changed")
    require(_clock(start["started_at"]) <= _clock(inventory["retrieved_at"])
        <= _clock(completed["completed_at"]), "original_global_clock_order_changed")
    require("native-market-inputs-" + _clock(start["started_at"]).strftime("%Y%m%dT%H%M%SZ") == DIRECTORY.name,
            "original_run_identifier_clock_changed")


class _MonthlySnapshot:
    """Three retained FDs and at most one bounded transient member FD."""
    def __init__(self, root, guard):
        _require_capture_platform()
        self._closed = False
        self._dirs, self._files, self._pins = {}, {}, {}
        self._claim_fd = None
        self._reads = 0
        self._sealed = self._sealed_identity = None
        self._root, self._guard = root, guard
        self._directory = root / DIRECTORY
        self._claim = self._directory.parent / ("budget-" + CLAIM_ID + ".json")
        self._anchor = self._identity = (root, guard, self._directory, self._claim)
        self._manifest_raw = self._controls = self._claim_raw = None
        try:
            require(root == lane.ROOT and type(guard) is lane.LaneGuard
                and root.is_absolute() and root.resolve() == root and guard.binding()[0] == root,
                "designated_monthly_lane_required")
            guard.check()
            for directory in (self._directory, self._directory.parent):
                require(directory.resolve() == directory, "monthly_directory_link_refused")
                info = directory.lstat()
                require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o700, "monthly_directory_protection")
                fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                stamp = _directory_stamp(info, closed=directory == self._directory)
                self._dirs[directory] = (fd, stamp)
                require(_directory_stamp(os.fstat(fd), closed=directory == self._directory) == stamp,
                    "monthly_directory_open_identity")
            require(self.names() == expected_names(), "exact_monthly_closed_membership_required")
            self._claim_fd = os.open(self._claim.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self._dirs[self._claim.parent][0])
            self._claim_stamp = self._protected_file(os.fstat(self._claim_fd))
            for number, name in enumerate(expected_names()):
                if number % READ_BATCH == 0:
                    self.check()
                info = os.stat(name, dir_fd=self._dirs[self._directory][0], follow_symlinks=False)
                self._files[name] = self._protected_file(info)
            self._dirs = MappingProxyType(dict(self._dirs))
            self._files = MappingProxyType(dict(self._files))
            self.full_check()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _protected_file(info):
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
            and 0 <= info.st_size <= MAXIMUM_BYTES, "monthly_file_protection_or_size")
        return _file_stamp(info)

    def _local_check(self):
        require(type(self) is _MonthlySnapshot and not self._closed
            and self._anchor is self._identity
            and self._anchor == (self._root, self._guard, self._directory, self._claim), "monthly_snapshot_binding_changed")
        require(self._sealed is self._sealed_identity, "monthly_snapshot_seal_changed")
        if self._sealed is not None:
            parts = (self._dirs, self._files, self._pins, self._manifest_raw, self._controls, self._claim_raw)
            require(len(parts) == len(self._sealed) and all(a is b for a, b in zip(parts, self._sealed)),
                "monthly_snapshot_seal_changed")
        for path, (fd, stamp) in self._dirs.items():
            require(path.resolve() == path and all(_directory_stamp(info,
                closed=path == self._directory) == stamp for info in (path.lstat(), os.fstat(fd))),
                "monthly_directory_changed")
        if self._claim_fd is not None:
            require(all(self._protected_file(info) == self._claim_stamp for info in (
                os.fstat(self._claim_fd), os.stat(self._claim.name,
                    dir_fd=self._dirs[self._claim.parent][0], follow_symlinks=False))), "monthly_spent_claim_changed")

    def check(self):
        self._local_check(); self._guard.check(); self._local_check()

    def names(self):
        self.check()
        result = tuple(sorted(os.listdir(self._dirs[self._directory][0])))
        self.check()
        return result

    def full_check(self):
        self.check()
        require(self.names() == expected_names(), "monthly_complete_membership_changed")
        for number, (name, stamp) in enumerate(self._files.items()):
            if number % READ_BATCH == 0:
                self.check()
            info = os.stat(name, dir_fd=self._dirs[self._directory][0], follow_symlinks=False)
            require(self._protected_file(info) == stamp, "monthly_earlier_file_changed")
        self.check()
        require(self.names() == expected_names(), "monthly_complete_membership_changed")

    def _read_fd(self, fd, stamp, maximum):
        require(type(maximum) is int and 0 < maximum <= MAXIMUM_BYTES and stamp[5] <= maximum,
            "bounded_monthly_read_required")
        os.lseek(fd, 0, os.SEEK_SET)
        parts, size = [], 0
        while True:
            self._local_check()
            require(self._protected_file(os.fstat(fd)) == stamp, "monthly_open_file_changed")
            part = os.read(fd, min(65536, maximum + 1 - size))
            if not part:
                break
            parts.append(part); size += len(part)
            require(size <= maximum, "monthly_read_ceiling")
        require(size == stamp[5], "monthly_short_read")
        return b"".join(parts)

    def read(self, name, maximum):
        if self._reads % READ_BATCH == 0:
            self.check()
        self._reads += 1
        self._local_check()
        require(type(name) is str and name in self._files, "registered_monthly_member_required")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=self._dirs[self._directory][0])
        try:
            raw = self._read_fd(fd, self._files[name], maximum)
            require(self._protected_file(os.stat(name, dir_fd=self._dirs[self._directory][0],
                follow_symlinks=False)) == self._files[name], "monthly_named_file_changed")
        finally:
            os.close(fd)
        self._local_check()
        if name in self._pins:
            require((len(raw), hash_bytes(raw)) == self._pins[name], "monthly_original_bytes_changed")
        return raw

    def authenticate(self):
        claim = self._read_fd(self._claim_fd, self._claim_stamp, MAXIMUM_BYTES)
        require(hash_bytes(claim) == CLAIM_SHA256, "original_budget_raw_pin_changed")
        controls = {name: self.read(name, MAXIMUM_BYTES) for name in CONTROL_PINS}
        require(all(hash_bytes(controls[name]) == digest for name, digest in CONTROL_PINS.items()),
            "original_global_control_pin_changed")
        _historical_code(self._root, self._guard)
        _controls(controls, claim)
        entries = []
        for name in expected_names():
            raw = self.read(name, MAXIMUM_BYTES)
            entries.append({"name": name, "bytes": len(raw), "sha256": hash_bytes(raw)})
        manifest = canonical_json(entries).encode()
        require(hash_bytes(manifest) == MANIFEST_SHA256, "original_complete_manifest_changed")
        self.full_check()
        self._pins = MappingProxyType({entry["name"]: (entry["bytes"], entry["sha256"]) for entry in entries})
        self._manifest_raw, self._controls, self._claim_raw = manifest, MappingProxyType(controls), claim
        self._sealed = self._sealed_identity = (self._dirs, self._files, self._pins,
            self._manifest_raw, self._controls, self._claim_raw)
        self.full_check()

    @property
    def manifest_raw(self):
        self.check(); require(type(self._manifest_raw) is bytes, "monthly_snapshot_not_authenticated")
        return self._manifest_raw

    @property
    def controls(self):
        self.check(); require(type(self._controls) is MappingProxyType, "monthly_snapshot_not_authenticated")
        return self._controls

    @property
    def claim_raw(self):
        self.check(); require(type(self._claim_raw) is bytes, "monthly_snapshot_not_authenticated")
        return self._claim_raw

    def close(self):
        if not self._closed:
            self._closed = True
            if self._claim_fd is not None:
                os.close(self._claim_fd)
            for fd, unused_stamp in self._dirs.values():
                os.close(fd)


@contextmanager
def load_registered_snapshot(root, guard):
    """A fixed protected snapshot only; caller still owes full panel replay."""
    snapshot = _MonthlySnapshot(root, guard)
    try:
        snapshot.authenticate()
        snapshot.full_check()
        yield snapshot
        snapshot.full_check()
    finally:
        snapshot.close()
