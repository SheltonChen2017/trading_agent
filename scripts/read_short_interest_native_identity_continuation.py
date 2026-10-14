"""Read-only batching: Git guards at file boundaries, custody at every chunk.

The previously released loader remains untouched. All inventory, historical
code, byte, chain, qualification and clock proofs still use its exact verifier.
No keys, provider requests, source writes or empirical/QC authority are added.
"""
from contextlib import contextmanager
import re
import subprocess
from types import MappingProxyType

from data.hashing import hash_bytes, hash_payload
import scripts.continue_short_interest_native_identity as capture
import scripts.stream_short_interest_native_identity_continuation as stream

base = stream.base
require = base.replay.require


class ReadOnlyCustody:
    """Never publishes; only the original source-directory FDs are retained."""
    __slots__ = ("_anchor", "_identity")

    def __init__(self, directory, full_guard):
        capture._require_capture_platform()
        full_guard()
        # OwnedOutput's full filesystem checks stay unchanged. Its callback is
        # deliberately cheap because whole-file boundary() supplies the full
        # root/branch/HEAD/status check, rather than spawning Git per 64KiB.
        owned = capture._OwnedOutput(directory, lambda: None)
        self._anchor = self._identity = (owned, full_guard)
        try:
            self.boundary()
        except BaseException:
            owned.close()
            raise

    def check(self):
        require(type(self) is ReadOnlyCustody and self._anchor is self._identity
                and type(self._anchor) is tuple and len(self._anchor) == 2, "batched_reader_changed")
        self._anchor[0].check()

    def boundary(self):
        self.check()
        self._anchor[1]()
        self.check()

    def read(self, name, maximum, *, parent=False):
        self.boundary()
        try:
            # Every chunk retains FD/device/inode/mode/owner/no-link checks.
            # The unchanged helper cannot resolve an alternate mutable path.
            return base.read_owned_source(self._anchor[0], name, maximum, parent=parent)
        finally:
            self.boundary()

    def names(self):
        self.boundary()
        try:
            return tuple(sorted(base.os.listdir(self._anchor[0]._anchor[2])))
        finally:
            self.boundary()

    def close(self):
        self.check()
        self._anchor[0].close()

    def __enter__(self):
        self.boundary()
        return self

    def __exit__(self, *unused):
        self._anchor[0].close()


@contextmanager
def load_batched_for_current_runtime(root, *, runtime_head, actual_remote):
    capture._require_capture_platform()
    require(root == base.ROOT and type(runtime_head) is str and re.fullmatch(r"[0-9a-f]{40}", runtime_head)
            and type(actual_remote) is str and re.fullmatch(r"[0-9a-f]{40}", actual_remote), "designated_runtime_lane")
    local = lambda: capture._local(root, runtime_head)
    local()
    registered = dict(base.ANCHORS)
    require(all(base.replay.digest(pin) for pin in registered.values()), "registered_historical_child_pins")
    capture._guard_remote(root, actual_remote)
    require(capture._git(root, "merge-base", "--is-ancestor", base.HEAD, runtime_head) == "",
            "historical_child_is_lane_ancestor")
    source = capture.load_parent(root, head=runtime_head)
    local()
    with ReadOnlyCustody(root / base.CHILD, local) as child, ReadOnlyCustody(root / capture.SOURCE, local) as original:
        names = child.names()
        require(len(names) == base.FILE_COUNT, "exact_closed_child_file_count")
        entries = {}
        anchor_names = {"protocol.private.json": "protocol_bytes_sha256", "started.json": "started_bytes_sha256",
                "completed.json": "completed_bytes_sha256", "inventory.private.json": "inventory_bytes_sha256"}
        for name in names:
            raw = child.read(name, base.maximum(name))
            sha = hash_bytes(raw)
            require(name not in anchor_names or sha == registered[anchor_names[name]], "registered_child_anchor_bytes")
            entries[name] = sha, len(raw)
        files = object.__new__(capture._ParentFiles)
        reader = lambda name: child.read(name, base.maximum(name))
        anchor = (MappingProxyType(entries), reader)
        for name, value in (("_entries", anchor[0]), ("_reader", reader), ("_anchor", anchor), ("_anchor_identity", anchor)):
            object.__setattr__(files, name, value)
        require(files.inventory_sha256() == registered["aggregate_inventory_sha256"], "registered_child_all_file_inventory")
        state = source.payload()
        claim_id = hash_payload({"source_inventory_sha256": state["source_inventory_sha256"],
                "failed_request_sha256": state["failed_request_sha256"],
                "failed_start_bytes_sha256": state["failed_start_bytes_sha256"],
                "purpose": "single_explicit_native_identity_manual_continuation"})
        budget = child.read("budget-" + claim_id + ".json", 65536, parent=True)

        def historical(commit, name):
            child.boundary()
            require(commit == base.HEAD and name in capture.CODE_FILES, "exact_historical_child_code_not_runtime_code")
            try:
                response = subprocess.run(["git", "show", commit + ":" + name], cwd=root,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            finally:
                child.boundary()
            require(response.returncode == 0 and type(response.stdout) is bytes, "historical_child_code_unavailable")
            return response.stdout

        # Filesystem/type checks remain at every pure-replay checkpoint. Full
        # lane guards surround every actual source file or Git operation.
        replayed = base.replay.verify_completed_continuation(source, files, byte_pins=files.pins(),
                inventory_sha256=registered["aggregate_inventory_sha256"], budget_raw=budget,
                budget_sha256=registered["budget_bytes_sha256"], expected_head=base.HEAD,
                expected_protocol_sha256=registered["protocol_bytes_sha256"],
                expected_code_identity_sha256=registered["code_identity_sha256"], historical_code=historical,
                local_guard=child.check, expected_run_id=base.RUN_ID, expected_remote_head=base.REMOTE)
        original_refs = {entry["report_path"]: entry for entry in state["completed_reports"]}

        def read_original(name):
            original.check()
            require(name in original_refs, "original_44_registered_report_path_only")
            raw = original.read(name, capture.identity.MAXIMUM_DATE_REPORT_BYTES)
            pin = original_refs[name]
            require(len(raw) == pin["report_bytes"] and hash_bytes(raw) == pin["report_bytes_sha256"],
                    "original_report_custody_unchanged")
            return raw

        def cheap():
            child.check()
            original.check()
            require(base.ANCHORS == registered, "completed_stream_source_pins_changed")

        child.boundary()
        original.boundary()
        require(child.names() == names, "completed_stream_source_inventory_changed")
        capture._guard_remote(root, actual_remote)
        yield replayed, stream.iter_qualified_dates(replayed, read_original=read_original, guard=cheap)
        child.boundary()
        original.boundary()
        require(child.names() == names, "completed_stream_source_inventory_changed")
