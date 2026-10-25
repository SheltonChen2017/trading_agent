"""Offline custody and replay of the fixed, refused count-recovery child.

This loader does not restart a claim, interpret provider rows, or turn a
negative child into a completed source.  Every retained body is authenticated
without printing it.  Only one member is opened at a time; directory stamps
detect namespace replacement and each read rechecks its original file stamp.
"""
from __future__ import annotations

from contextlib import contextmanager
from itertools import islice
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType

from data.hashing import canonical_json, hash_bytes, hash_payload
from scripts import capture_short_interest_count_recovery as old
from scripts import short_interest_lane_batch_guard as lane

SOURCE_HEAD = "99417837467f98b0ed02a3272b0980f4efa2d243"
SOURCE_CODE_SHA256 = "254b457da17190cba7986a21e9fff98dc415f329cee15e5fe64ace016dde022e"
SOURCE_CODE_FILES = 51
SOURCE_STARTS = 13_944
SOURCE_RAW_BODIES = 13_943
SOURCE_CHARGED_BYTES = 21_293_349
SOURCE_MEMBER_COUNT = 41_835
SOURCE_CLAIM_SHA256 = "cdc0d80751c01189afe75a8ed59ca90bb66c76a3c5ed3871ef7d0f433d8bc398"
SOURCE_REFUSAL_SHA256 = "b688011e116271dcfb6e3d905103b04785e752794210c69338b12c7771243ddc"
SOURCE_FAILURE_RECEIPT_SHA256 = "afed64453cc56f55b7a13a1ce6f91a68057bf3fd62ae8a5789b621a039f9fcec"
SOURCE_DIAGNOSTIC_SHA256 = "91d7d010dd9adef9607cd589dcdf77d6a02937d9ad37a7e9b20fbbd571509851"
MAXIMUM_MEMBER_BYTES = 2 * 1024 ** 2
MAXIMUM_OFFLINE_READ_BATCH = 64


class RefusedSnapshotError(ValueError):
    """Fixed diagnostic codes contain no paths, source rows, or exceptions."""


def require(value, code):
    if not value:
        raise RefusedSnapshotError("REFUSED: " + code)


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def expected_names():
    names = {"protocol.private.json", "started.json", "run.refused.json"}
    for number in range(1, SOURCE_STARTS + 1):
        prefix = f"query-{number:08d}"
        names.update((prefix + ".started.json", prefix + ".received.json"))
        names.add(prefix + (".raw" if number <= SOURCE_RAW_BODIES else ".diagnostic.private.json"))
    require(SOURCE_RAW_BODIES + 1 == SOURCE_STARTS and len(names) == SOURCE_MEMBER_COUNT,
            "fixed_refused_inventory_shape_changed")
    return tuple(sorted(names))


def _directory_stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode),
            info.st_mtime_ns, info.st_ctime_ns)


def _file_stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode),
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class _Snapshot:
    """Two retained directories, one claim FD, and at most one member FD."""
    def __init__(self, root, guard):
        self._closed = False
        self._directories = {}
        self._entries = {}
        self._pins = {}
        self._claim_fd = None
        self._inventory = None
        self._inventory_binding = None
        self._prefix = None
        self._binding = self._binding_identity = None
        self._anchor = self._identity = (root, guard)
        self._read_count = 0
        self._root, self._guard = root, guard
        self._directory = root / old.OUTPUT
        self._claim = self._directory.parent / old.CLAIM_NAME
        self._manifest_raw = None
        try:
            require(type(guard) is lane.LaneGuard and root == lane.ROOT
                    and root.is_absolute() and root.resolve() == root
                    and guard.binding()[0] == root, "designated_lane_snapshot_required")
            guard.check()
            for directory in (self._directory, self._directory.parent):
                require(directory.resolve() == directory, "snapshot_directory_link_refused")
                info = directory.lstat()
                require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                        and stat.S_IMODE(info.st_mode) == 0o700, "snapshot_directory_protection")
                fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                self._directories[directory] = (fd, self._directory_state(directory, info))
                require(self._directory_state(directory, os.fstat(fd)) == self._directory_state(directory, info),
                        "snapshot_directory_open_identity")
            require(self.names() == expected_names(), "fixed_refused_member_names_required")
            self._claim_fd = os.open(self._claim.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=self._directories[self._claim.parent][0])
            self._claim_stamp = self._protected_file(os.fstat(self._claim_fd))
            for number, name in enumerate(expected_names()):
                if number % MAXIMUM_OFFLINE_READ_BATCH == 0:
                    self.check()
                self._local_check()
                info = os.stat(name, dir_fd=self._directories[self._directory][0], follow_symlinks=False)
                self._entries[name] = self._protected_file(info)
            self._directories = MappingProxyType(dict(self._directories))
            self._entries = MappingProxyType(dict(self._entries))
            self.check()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _protected_file(info):
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and 0 <= info.st_size <= MAXIMUM_MEMBER_BYTES,
                "snapshot_member_protection_or_bound")
        return _file_stamp(info)

    def _directory_state(self, path, info):
        # Only the closed run's namespace is frozen.  Its parent must allow
        # separately claimed future siblings without changing the old run or
        # the retained, individually authenticated spent claim.
        stamp = _directory_stamp(info)
        return stamp if path == self._directory else stamp[:4]

    def _local_check(self):
        require(not self._closed, "snapshot_closed")
        require(type(self) is _Snapshot and self._anchor is self._identity
                and self._anchor == (self._root, self._guard), "snapshot_lane_binding_changed")
        require(self._binding is self._binding_identity, "snapshot_custody_binding_changed")
        if self._binding is not None:
            values = (self._directories, self._entries, self._pins, self._manifest_raw,
                    self._inventory, self._prefix, self._directory, self._claim)
            require(len(self._binding) == len(values)
                    and all(left is right for left, right in zip(self._binding, values)),
                    "snapshot_custody_binding_changed")
        for path, (fd, stamp) in self._directories.items():
            require(path.resolve() == path and self._directory_state(path, path.lstat()) == stamp
                    and self._directory_state(path, os.fstat(fd)) == stamp, "snapshot_directory_changed")
        if self._claim_fd is not None:
            for info in (os.fstat(self._claim_fd), os.stat(self._claim.name,
                    dir_fd=self._directories[self._claim.parent][0], follow_symlinks=False)):
                require(self._protected_file(info) == self._claim_stamp, "snapshot_spent_claim_changed")

    def check(self):
        self._local_check()
        self._guard.check()
        if self._prefix is not None:
            self._prefix.check()
        self._local_check()

    def names(self):
        self.check()
        names = tuple(sorted(os.listdir(self._directories[self._directory][0])))
        self.check()
        return names

    def full_check(self):
        """Close a complete offline pass, including in-place member changes.

        Directory stamps bind names, not contents.  Recheck every originally
        captured file stamp before admitting a replay or leaving custody; this
        is intentionally separate from the O(1) per-member local checks.
        """
        self.check()
        require(self.names() == expected_names(), "snapshot_full_membership_changed")
        directory_fd = self._directories[self._directory][0]
        for number, (name, expected) in enumerate(self._entries.items()):
            if number % MAXIMUM_OFFLINE_READ_BATCH == 0:
                self.check()
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            require(self._protected_file(info) == expected, "snapshot_full_member_stamp_changed")
        self.check()
        require(self.names() == expected_names(), "snapshot_full_membership_changed")

    def _read_fd(self, fd, expected, maximum):
        require(type(maximum) is int and 0 < maximum <= MAXIMUM_MEMBER_BYTES
                and expected[5] <= maximum, "snapshot_bounded_read_required")
        os.lseek(fd, 0, os.SEEK_SET)
        parts, size = [], 0
        while True:
            require(self._protected_file(os.fstat(fd)) == expected, "snapshot_open_member_changed")
            part = os.read(fd, min(65536, maximum + 1 - size))
            if not part:
                break
            size += len(part)
            require(size <= maximum, "snapshot_member_read_bound")
            parts.append(part)
        require(size == expected[5], "snapshot_member_short_read")
        return b"".join(parts)

    def read(self, name, maximum):
        # These are offline reads, not HTTP authorizations.  Exact source-byte
        # checks remain per file; a deterministic batch bounds expensive Git
        # observations.  Full guard/membership checks precede every outward
        # snapshot yield and finish each complete manifest/replay pass.
        if self._read_count % MAXIMUM_OFFLINE_READ_BATCH == 0:
            self.check()
        self._read_count += 1
        self._local_check()
        require(type(name) is str and name in self._entries, "registered_snapshot_member_required")
        directory_fd = self._directories[self._directory][0]
        expected = self._entries[name]
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        try:
            raw = self._read_fd(fd, expected, maximum)
            require(self._protected_file(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) == expected,
                    "snapshot_named_member_changed")
        finally:
            os.close(fd)
        self._local_check()
        if name in self._pins:
            require((len(raw), hash_bytes(raw)) == self._pins[name], "snapshot_original_member_bytes_changed")
        return raw

    def claim_bytes(self):
        self.check()
        raw = self._read_fd(self._claim_fd, self._claim_stamp, MAXIMUM_MEMBER_BYTES)
        self.check()
        require(hash_bytes(raw) == SOURCE_CLAIM_SHA256, "fixed_spent_claim_bytes_changed")
        return raw

    def measure(self):
        require(self._inventory is None, "qualified_snapshot_manifest_cannot_be_rebound")
        entries = []
        for name in expected_names():
            raw = self.read(name, MAXIMUM_MEMBER_BYTES)
            entries.append({"name": name, "bytes": len(raw), "sha256": hash_bytes(raw)})
        self.full_check()
        self._pins = MappingProxyType({row["name"]: (row["bytes"], row["sha256"]) for row in entries})
        self._manifest_raw = canonical_json(entries).encode()
        return self._manifest_raw

    @property
    def manifest_raw(self):
        self.check()
        require(type(self._manifest_raw) is bytes, "snapshot_manifest_not_measured")
        return self._manifest_raw

    @property
    def inventory(self):
        self.check()
        require(type(self._inventory) is old.parallel.ParallelCountInventory,
                "refused_inventory_not_replayed")
        require(self._inventory_binding is self._inventory, "snapshot_typed_inventory_rebound")
        self._inventory.guard()
        return self._inventory

    def close(self):
        if not self._closed:
            self._closed = True
            if self._claim_fd is not None:
                os.close(self._claim_fd)
            for fd, unused in self._directories.values():
                os.close(fd)


def _historical_identity(root, guard):
    names = old.expected_code_paths()
    require(len(names) == SOURCE_CODE_FILES and names == tuple(sorted(set(names))),
            "fixed_historical_code_membership_changed")
    require(old.cache._git(root, ["merge-base", "--is-ancestor", SOURCE_HEAD, guard.binding()[1]], guard) == b"",
            "refused_child_code_not_lane_ancestor")
    entries = [{"path": name, "sha256": hash_bytes(old.cache._git(root,
        ["show", SOURCE_HEAD + ":" + name], guard))} for name in names]
    require(hash_payload({"git_commit": SOURCE_HEAD, "files": entries}) == SOURCE_CODE_SHA256,
            "fixed_historical_complete_code_identity_changed")


@contextmanager
def _load_parent_prefix(root, source, parent_plan, guard):
    """Reuse original proofs without the live wrapper's remote refreshes."""
    directory = root / old.PARENT
    claim_path = directory.parent / ("budget-" + old.original.PROTOCOL_SHA256 + ".json")
    require(old._directory_names(directory) == old.parent_names(), "original_parent_exact_membership")
    paths = tuple(directory / name for name in old.parent_names()) + (claim_path,)
    with old.PrefixSnapshot(paths, guard.check) as held:
        files = {name: held.read(directory / name, MAXIMUM_MEMBER_BYTES) for name in old.parent_names()}
        claim_raw = held.read(claim_path, MAXIMUM_MEMBER_BYTES)
        def custody():
            held.check()
            require(old._directory_names(directory) == old.parent_names(), "original_parent_membership_changed")
        def historical(head, name):
            require(head == old.PARENT_HEAD and name in old.cache.COUNT_CODE_FILES,
                    "only_fixed_original_historical_code")
            require(old.cache._git(root, ["merge-base", "--is-ancestor", head, guard.binding()[1]], guard) == b"",
                    "original_parent_code_not_lane_ancestor")
            return old.cache._git(root, ["show", head + ":" + name], guard)
        prefix = old.verify_prefix(source, parent_plan, files, claim_raw, historical, custody)
        guard.check()
        yield prefix
        prefix.check(); guard.check()


def _replay(snapshot, source, prefix, binding):
    binding.check(); prefix.check(); snapshot.check()
    parse = old._parse
    claim = parse(snapshot.claim_bytes())
    protocol_raw = snapshot.read("protocol.private.json", MAXIMUM_MEMBER_BYTES)
    require(protocol_raw == canonical_json(old.protocol()).encode()
            and hash_bytes(protocol_raw) == old.PROTOCOL_SHA256, "refused_child_protocol_changed")
    start = parse(snapshot.read("started.json", MAXIMUM_MEMBER_BYTES))
    refusal_raw = snapshot.read("run.refused.json", MAXIMUM_MEMBER_BYTES)
    require(hash_bytes(refusal_raw) == SOURCE_REFUSAL_SHA256, "fixed_refusal_bytes_changed")
    refusal = parse(refusal_raw)
    require(old._exact(start, {"schema": "si-manual-count-recovery-start-v1",
        "started_at": start.get("started_at"), "parent_inventory_sha256": prefix.inventory.sha256,
        "child_plan_sha256": binding.child_plan.sha256, "code_head": SOURCE_HEAD,
        "code_identity_sha256": SOURCE_CODE_SHA256, "protocol_sha256": old.PROTOCOL_SHA256,
        "authority": old.authority()}), "refused_child_start_lineage_changed")
    require(old._exact(claim, {"schema": "si-manual-count-recovery-spent-claim-v1",
        "protocol_sha256": old.PROTOCOL_SHA256, "parent_manifest_sha256": old.PARENT_MANIFEST_SHA256,
        "parent_claim_sha256": old.PARENT_CLAIM_SHA256, "parent_inventory_sha256": prefix.inventory.sha256,
        "parent_charged_response_bytes": old.PARENT_CHARGED_BYTES,
        "child_plan_sha256": binding.child_plan.sha256, "new_position_mapping_sha256": old.MAPPING_SHA256,
        "maximum_new_starts": old.MAXIMUM_NEW_STARTS, "maximum_cumulative_starts": old.MAXIMUM_CUMULATIVE_STARTS,
        "maximum_child_response_bytes": old.MAXIMUM_CHILD_BYTES,
        "maximum_cumulative_response_bytes": old.MAXIMUM_CUMULATIVE_BYTES,
        "code_head": SOURCE_HEAD, "remote_head": "b211db7f81103df9cc3d736a05a4cc82d8efe4b0",
        "code_identity_sha256": SOURCE_CODE_SHA256, "started_at": start["started_at"],
        "automatic_retries": 0, "restart_allowed": False}), "refused_child_spent_claim_lineage_changed")
    receipts = []
    for ordinal, query in enumerate(islice(binding.child_plan._queries.iter_queries(), SOURCE_STARTS), 1):
        if (ordinal - 1) % MAXIMUM_OFFLINE_READ_BATCH == 0:
            prefix.check(); snapshot.check()
        ticket, name = query.to_payload(), f"query-{ordinal:08d}"
        began = parse(snapshot.read(name + ".started.json", MAXIMUM_MEMBER_BYTES))
        receipt_raw = snapshot.read(name + ".received.json", MAXIMUM_MEMBER_BYTES)
        receipt = parse(receipt_raw)
        require(old._exact(began, {"schema": "si-manual-count-recovery-request-start-v1",
            "query_ordinal": ordinal, "original_count_position": old.NEW_POSITIONS[ordinal - 1],
            "request": ticket["request"], "request_sha256": ticket["request_sha256"],
            "started_at": receipt.get("started_at"), "child_plan_sha256": binding.child_plan.sha256,
            "code_head": SOURCE_HEAD, "whole_page_bytes_reserved": old.parallel.MAXIMUM_RESPONSE_BYTES}),
            "refused_child_START_mapping_changed")
        require(receipt.get("query_ordinal") == ordinal
                and receipt.get("request_sha256") == ticket["request_sha256"],
                "refused_child_receipt_descriptor_changed")
        if ordinal <= SOURCE_RAW_BODIES:
            raw = snapshot.read(name + ".raw", MAXIMUM_MEMBER_BYTES)
            require(receipt.get("code") == "received" and receipt.get("http_attempted") is True
                    and receipt.get("http_status") == 200 and receipt.get("body_observed") is True
                    and receipt.get("raw_path") == name + ".raw"
                    and receipt.get("raw_bytes") == len(raw) and receipt.get("raw_sha256") == hash_bytes(raw),
                    "refused_child_observed_body_changed")
        else:
            require(hash_bytes(receipt_raw) == SOURCE_FAILURE_RECEIPT_SHA256
                    and receipt.get("code") == "material_request_refused"
                    and receipt.get("http_attempted") is True and receipt.get("http_status") is None
                    and receipt.get("body_observed") is False, "fixed_child_failure_receipt_changed")
            diagnostic_raw = snapshot.read(name + ".diagnostic.private.json", MAXIMUM_MEMBER_BYTES)
            require(hash_bytes(diagnostic_raw) == SOURCE_DIAGNOSTIC_SHA256
                    and old._exact(parse(diagnostic_raw), {"query_ordinal": ordinal,
                        "failure_stage": "transport", "http_attempted": True, "http_status": None,
                        "observed_receipt_at": receipt.get("received_at"), "protocol_sha256": old.PROTOCOL_SHA256}),
                    "fixed_child_failure_diagnostic_changed")
        receipts.append(receipt)
    require(len(receipts) == SOURCE_STARTS, "fixed_child_started_sequence_required")
    inventory = old.parallel.seal_parallel_inventory(binding.child_plan, tuple(receipts),
        started_at=start["started_at"], completed_at=refusal.get("refused_at"), halted=True)
    values = inventory.to_payload()
    require(old._exact(refusal, {"schema": "si-manual-count-recovery-refused-v1",
        "code": "child_started_prefix_drained_or_unreceipted_no_restart", "refused_at": refusal.get("refused_at"),
        "child_starts": SOURCE_STARTS, "cumulative_starts": old.PARENT_STARTED + SOURCE_STARTS,
        "child_charged_response_bytes": SOURCE_CHARGED_BYTES,
        "cumulative_charged_response_bytes": old.PARENT_CHARGED_BYTES + SOURCE_CHARGED_BYTES,
        "child_known_http_invocations": SOURCE_STARTS,
        "cumulative_known_http_invocations": old.PARENT_HTTP + SOURCE_STARTS,
        "http_invocation_count_exact": True, "first_failed_child_ordinal": SOURCE_STARTS,
        "unreceipted_diagnostics": [], "complete_child_capture": False,
        "protocol_sha256": old.PROTOCOL_SHA256, "authority": old.authority()}),
        "fixed_negative_closure_or_debits_changed")
    require(values["attempts_started"] == values["http_invocations"] == SOURCE_STARTS
            and values["charged_response_bytes"] == SOURCE_CHARGED_BYTES
            and values["retained_raw_bytes"] == SOURCE_CHARGED_BYTES - old.parallel.MAXIMUM_RESPONSE_BYTES
            and values["halted"] is True and values["complete_frozen_request_sequence"] is False,
            "refused_child_inventory_accounting_changed")
    binding.check(); prefix.check(); snapshot.full_check()
    return inventory


def measure_manifest(root, guard):
    """Read-only fixed-directory metadata; never yields source admission."""
    snapshot = _Snapshot(root, guard)
    try:
        snapshot.claim_bytes()
        return snapshot.measure()
    finally:
        snapshot.close()


@contextmanager
def load_refused_child(root, source, guard, expected_manifest_sha256):
    """Require an externally frozen manifest digest, then replay under custody."""
    require(_digest(expected_manifest_sha256), "prospectively_bound_manifest_digest_required")
    old.registered()
    binding = old.freeze_recovery(source)
    snapshot = _Snapshot(root, guard)
    try:
        require(hash_bytes(snapshot.measure()) == expected_manifest_sha256,
                "prospectively_bound_manifest_changed")
        _historical_identity(root, guard)
        with _load_parent_prefix(root, source, binding.parent_plan, guard) as prefix:
            snapshot._prefix = prefix
            snapshot._inventory = _replay(snapshot, source, prefix, binding)
            snapshot._inventory_binding = snapshot._inventory
            snapshot.full_check()
            snapshot._binding = snapshot._binding_identity = (snapshot._directories,
                snapshot._entries, snapshot._pins, snapshot._manifest_raw, snapshot._inventory,
                snapshot._prefix, snapshot._directory, snapshot._claim)
            yield snapshot
            snapshot.check(); prefix.check()
            snapshot.full_check()
    finally:
        snapshot.close()
