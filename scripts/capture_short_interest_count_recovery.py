"""One newly registered, source-only recovery of the refused reported-count round.

This is not a restart of the original claim. Original count position 47 remains
an immutable pre-wire negative; the new child observes that descriptor anew,
then the previously unstarted positions 49..81,875. No historical PIT, class
denominator, outcome, QuantConnect, or backtest authority follows from capture.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from itertools import islice
import json
import os
from pathlib import Path
import re
import resource
import stat

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.short_interest_etf import native_dated_class_reference as references
from research.short_interest_etf import native_parallel_count_contract as parallel
from research.short_interest_etf import native_reported_anchor_plan as anchors
from scripts import capture_short_interest_native_anchor_cache as cache
from scripts import capture_short_interest_native_reported_count_round as original
from scripts import short_interest_lane_batch_guard as lane
from scripts.continue_short_interest_native_identity import _OwnedOutput
from scripts.qualify_finra_short_interest import _prepare_capture_directory, _require_capture_platform
from scripts.qualify_sharadar_companion import SharadarCaptureRefusal, _utc_now
from scripts.short_interest_keychain import KeychainSecret, read_named_keychain


DRIVER_PATH = "scripts/capture_short_interest_count_recovery.py"
PARENT = Path("artifacts/short_interest/native_reported_counts/count-round-45a554213ed8fb12")
OUTPUT = PARENT.parent / "count-recovery-47-and-49-81875-v1"
CLAIM_NAME = "manual-count-recovery-47-and-49-81875-v1.claim.json"
PARENT_HEAD = "f67bbf2fc5ab4c7ce822c7e52b57b560cd670682"
PARENT_MANIFEST_SHA256 = "f6f5baf16c0fac2ffa26f994cf82122bcef9dfa842526530797531bc5c8f55c6"
PARENT_CLAIM_SHA256 = "008e56b20a5dafa1a9f7af71dbe91e79cfc96a282cb9680a1e3488936a189d7c"
PARENT_CODE_SHA256 = "52e988dfd219b378846afea7176d3a9784c1e9bd5118641f3e221b43dd1219f1"
MAPPING_SHA256 = "f36b28e9e4d0ebc76d2e5d8806e413604b5c52c8e443ff828b69f910ac9f2e9d"
PARENT_STARTED = 48
PARENT_HTTP = 47
PARENT_CHARGED_BYTES = 2_159_332
ORIGINAL_COUNT = 81_875
NEW_POSITIONS = (47, *range(49, ORIGINAL_COUNT + 1))
MAXIMUM_NEW_STARTS = 81_828
MAXIMUM_CUMULATIVE_STARTS = 81_876
MAXIMUM_CUMULATIVE_BYTES = 4 * 1024 ** 3
MAXIMUM_CHILD_BYTES = MAXIMUM_CUMULATIVE_BYTES - PARENT_CHARGED_BYTES
PROTOCOL_SHA256 = "5876de333c792b63253390bae32d3dfe58e8f760b215859ffb324afed969219b"


class RecoveryRefusal(ValueError):
    """Fixed, non-secret source-only refusal."""


def require(value, reason):
    if not value:
        raise RecoveryRefusal("REFUSED: " + reason)


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def authority():
    return {"source_only": True, "original_round_halted": True,
            "original_pre_wire_negative_preserved": True, "source_admitted": False,
            "same_class_denominator_admitted": False, "historical_PIT_admitted": False,
            "ready_for_backtest": False, "outcome_looks": 0, "qc_attempts": 0,
            "trading_authority": False}


def protocol():
    return {"schema": "si-manual-count-recovery-v1", "driver_path": DRIVER_PATH,
            "parent": str(PARENT), "parent_head": PARENT_HEAD,
            "parent_manifest_sha256": PARENT_MANIFEST_SHA256,
            "parent_claim_sha256": PARENT_CLAIM_SHA256,
            "parent_code_sha256": PARENT_CODE_SHA256,
            "parent_anchor_plan_sha256": original.ANCHOR_PLAN_SHA256,
            "parent_parallel_plan_sha256": original.PARALLEL_PLAN_SHA256,
            "parent_protocol_sha256": original.PROTOCOL_SHA256,
            "parent_cache_closure_sha256": original.CACHE_CLOSURE_SHA256,
            "parent_started": PARENT_STARTED, "parent_http": PARENT_HTTP,
            "parent_charged_response_bytes": PARENT_CHARGED_BYTES,
            "new_original_count_positions_sha256": MAPPING_SHA256,
            "new_observation_of_original_position": 47,
            "unstarted_original_positions": [49, ORIGINAL_COUNT],
            "maximum_new_starts": MAXIMUM_NEW_STARTS,
            "maximum_cumulative_starts": MAXIMUM_CUMULATIVE_STARTS,
            "maximum_cumulative_response_bytes": MAXIMUM_CUMULATIVE_BYTES,
            "maximum_child_response_bytes": MAXIMUM_CHILD_BYTES,
            "maximum_inflight": parallel.MAXIMUM_INFLIGHT,
            "whole_page_reservation_bytes": parallel.MAXIMUM_RESPONSE_BYTES,
            "output": str(OUTPUT), "one_child_claim": CLAIM_NAME,
            "authentication": "existing_named_Massive_Bearer_memory_only",
            "current_code": "complete_exact_committed_manifest_in_claim_not_self_referential",
            "parent_reader": "held_directory_FDs_exact_146_names_and_one_spent_claim",
            "remote": "matching_lane_ref_per_at_most_eight_HTTP_batch_and_bounded_publications",
            "automatic_retries": 0, "restart": False, "fallback": False,
            "authority": authority()}


def registered():
    require(all(_digest(value) for value in (PARENT_MANIFEST_SHA256, PARENT_CLAIM_SHA256,
            PARENT_CODE_SHA256, MAPPING_SHA256, PROTOCOL_SHA256))
            and hash_payload(protocol()) == PROTOCOL_SHA256
            and MAXIMUM_NEW_STARTS == len(NEW_POSITIONS)
            and MAXIMUM_CUMULATIVE_STARTS == PARENT_STARTED + MAXIMUM_NEW_STARTS
            and MAXIMUM_CHILD_BYTES == MAXIMUM_CUMULATIVE_BYTES - PARENT_CHARGED_BYTES,
            "prospective_recovery_protocol_pending_or_changed")


def parent_names():
    names = {"protocol.private.json", "started.json", "run.refused.json"}
    for ordinal in range(1, PARENT_STARTED + 1):
        prefix = f"query-{ordinal:08d}"
        names.update((prefix + ".started.json", prefix + ".received.json"))
        if ordinal != 47:
            names.add(prefix + ".raw")
    require(len(names) == 146, "fixed_parent_inventory_shape")
    return tuple(sorted(names))


def _parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_control_key")
            result[key] = value
        return result
    require(type(raw) is bytes, "control_bytes_required")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                parse_constant=lambda unused: (_ for _ in ()).throw(RecoveryRefusal("REFUSED: control_nonfinite")))
    except (UnicodeError, ValueError):
        raise RecoveryRefusal("REFUSED: control_JSON_refused") from None


def _exact(actual, expected):
    return canonical_json(actual) == canonical_json(expected)


def _directory_names(path):
    _require_capture_platform()
    before = path.lstat()
    require(stat.S_ISDIR(before.st_mode) and before.st_uid == os.getuid()
            and stat.S_IMODE(before.st_mode) == 0o700 and path.resolve() == path,
            "parent_directory_protection")
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        require((opened.st_dev, opened.st_ino, opened.st_uid, stat.S_IMODE(opened.st_mode)) ==
                (before.st_dev, before.st_ino, before.st_uid, 0o700), "parent_directory_identity")
        names = tuple(sorted(os.listdir(fd)))
        after = path.lstat()
        require((after.st_dev, after.st_ino, after.st_uid, stat.S_IMODE(after.st_mode)) ==
                (before.st_dev, before.st_ino, before.st_uid, 0o700), "parent_directory_changed")
        return names
    finally:
        os.close(fd)


class PrefixSnapshot:
    """Hold two protected directory FDs; open each of 147 files only for reading."""
    def __init__(self, paths, boundary):
        _require_capture_platform()
        require(type(paths) is tuple and len(paths) == 147, "exact_parent_snapshot_paths")
        self._directories, self._entries, self._boundary, self._closed = {}, {}, boundary, False
        try:
            for path in paths:
                boundary()
                require(path.is_absolute() and path.resolve() == path, "parent_snapshot_no_links")
                if path.parent not in self._directories:
                    info = path.parent.lstat()
                    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                            and stat.S_IMODE(info.st_mode) == 0o700, "parent_snapshot_directory_protection")
                    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    try:
                        opened = os.fstat(fd)
                        require(self._directory_stamp(opened) == self._directory_stamp(info),
                                "parent_snapshot_directory_identity")
                    except BaseException:
                        os.close(fd)
                        raise
                    self._directories[path.parent] = (fd, self._directory_stamp(info))
                fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=self._directories[path.parent][0])
                try:
                    info = os.fstat(fd)
                    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1,
                            "parent_snapshot_file_protection")
                    self._entries[path] = self._file_stamp(info)
                finally:
                    os.close(fd)
            require(len(self._directories) == 2, "exact_two_parent_directories")
            self.check()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _directory_stamp(info):
        return info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)

    @staticmethod
    def _file_stamp(info):
        return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode),
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def check(self):
        require(not self._closed, "parent_snapshot_closed")
        for path, (fd, stamp) in self._directories.items():
            require(path.resolve() == path and self._directory_stamp(path.lstat()) == stamp
                    and self._directory_stamp(os.fstat(fd)) == stamp, "parent_snapshot_directory_changed")
        for path, stamp in self._entries.items():
            info = os.stat(path.name, dir_fd=self._directories[path.parent][0], follow_symlinks=False)
            require(stat.S_ISREG(info.st_mode) and self._file_stamp(info) == stamp,
                    "parent_snapshot_named_file_changed")

    def read(self, path, maximum):
        self._boundary(); self.check()
        require(path in self._entries and type(maximum) is int and 0 < maximum <= 2 * 1024 * 1024
                and self._entries[path][5] <= maximum, "bounded_parent_snapshot_read")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self._directories[path.parent][0])
        try:
            chunks, size = [], 0
            while True:
                require(self._file_stamp(os.fstat(fd)) == self._entries[path], "parent_snapshot_open_file_changed")
                raw = os.read(fd, min(65536, maximum + 1 - size))
                if not raw:
                    break
                size += len(raw)
                chunks.append(raw)
                require(size <= maximum, "parent_snapshot_response_bound")
            require(size == self._entries[path][5], "parent_snapshot_original_size")
            self.check(); self._boundary()
            return b"".join(chunks)
        finally:
            os.close(fd)

    def close(self):
        if not self._closed:
            self._closed = True
            for fd, unused in self._directories.values():
                os.close(fd)

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, *unused):
        self.close()


class VerifiedPrefix:
    """Original refusal and held custody; no source-admission authority."""
    def __init__(self, source, plan, inventory, custody):
        self._anchor = self._identity = (source, plan, inventory, custody)

    def check(self):
        require(type(self) is VerifiedPrefix and self._anchor is self._identity,
                "prefix_identity_changed")
        source, plan, inventory, custody = self._anchor
        source._guard(); plan.guard(); inventory.guard(); custody()
        require(plan._queries is source.query_plan and inventory._plan is plan
                and inventory.to_payload()["attempts_started"] == PARENT_STARTED
                and inventory.to_payload()["halted"] is True, "prefix_plan_or_refusal_changed")

    @property
    def inventory(self):
        self.check()
        return self._anchor[2]


def verify_prefix(source, plan, files, claim_raw, historical_code, custody):
    """Strict parent controls; raw provider bodies are hash/length checked only."""
    registered()
    require(type(source) is anchors.NativeReportedAnchorPlan and type(plan) is parallel.ParallelCountPlan
            and plan._queries is source.query_plan and source.sha256 == original.ANCHOR_PLAN_SHA256
            and plan.sha256 == original.PARALLEL_PLAN_SHA256, "exact_original_source_and_parallel_plan")
    source._guard(); plan.guard(); custody()
    require(type(files) is dict and set(files) == set(parent_names()), "exact_146_parent_files")
    entries = []
    for name in parent_names():
        custody()
        require(type(files[name]) is bytes, "original_parent_bytes_required")
        entries.append({"name": name, "sha256": hash_bytes(files[name]), "bytes": len(files[name])})
    require(hash_payload(entries) == PARENT_MANIFEST_SHA256
            and hash_bytes(claim_raw) == PARENT_CLAIM_SHA256, "parent_manifest_or_spent_claim_changed")
    old_protocol, start, refusal = (_parse(files[name]) for name in
            ("protocol.private.json", "started.json", "run.refused.json"))
    require(_exact(old_protocol, original.protocol()) and hash_payload(old_protocol) == original.PROTOCOL_SHA256,
            "original_protocol_changed")
    code_entries = []
    for name in cache.COUNT_CODE_FILES:
        custody()
        raw = historical_code(PARENT_HEAD, name)
        require(type(raw) is bytes, "historical_code_bytes_required")
        code_entries.append({"path": name, "sha256": hash_bytes(raw)})
    require(hash_payload({"git_commit": PARENT_HEAD, "files": code_entries}) == PARENT_CODE_SHA256,
            "original_complete_code_identity_changed")
    require(_exact(start, {"schema": "si-cache-parallel-count-start-v1",
            "started_at": start.get("started_at"), "code_head": PARENT_HEAD,
            "remote_head": PARENT_HEAD, "protocol_sha256": original.PROTOCOL_SHA256,
            "code_identity_sha256": PARENT_CODE_SHA256, "outcome_looks": 0,
            "qc_attempts": 0}), "original_start_binding")
    require(_exact(refusal, {"schema": "si-cache-parallel-count-refused-v1",
            "code": "started_prefix_drained_no_completed_source_capture",
            "refused_at": refusal.get("refused_at"), "attempts_started": PARENT_STARTED,
            "outcome_looks": 0, "qc_attempts": 0, "backtest_result_exists": False}),
            "original_refusal_binding")
    claim = _parse(claim_raw)
    require(_exact(claim, {"schema": "si-cache-parallel-count-global-claim-v1",
            "protocol_sha256": original.PROTOCOL_SHA256,
            "anchor_plan_sha256": source.sha256,
            "cache_closure_sha256": original.CACHE_CLOSURE_SHA256,
            "parallel_plan_sha256": plan.sha256,
            "started_at": start["started_at"], "maximum_attempts": ORIGINAL_COUNT,
            "maximum_total_response_bytes": MAXIMUM_CUMULATIVE_BYTES,
            "restart_allowed": False}), "original_claim_binding")
    receipts = []
    for ordinal, query in enumerate(islice(source.query_plan.iter_queries(), PARENT_STARTED), 1):
        ticket, prefix = query.to_payload(), f"query-{ordinal:08d}"
        began = _parse(files[prefix + ".started.json"])
        receipt = _parse(files[prefix + ".received.json"])
        require(_exact(began, {"schema": "si-parallel-count-request-start-v1",
                "query_ordinal": ordinal, "request": ticket["request"],
                "request_sha256": ticket["request_sha256"],
                "started_at": began.get("started_at"), "plan_sha256": plan.sha256,
                "code_head": PARENT_HEAD,
                "whole_page_bytes_reserved": parallel.MAXIMUM_RESPONSE_BYTES}),
                "original_request_binding")
        require(receipt.get("query_ordinal") == ordinal
                and receipt.get("request_sha256") == ticket["request_sha256"]
                and receipt.get("started_at") == began["started_at"], "original_receipt_binding")
        if ordinal == 47:
            require(receipt.get("http_attempted") is False and receipt.get("http_status") is None
                    and receipt.get("body_observed") is False
                    and receipt.get("code") == "material_request_refused",
                    "original_pre_wire_negative_must_survive")
        else:
            raw = files[prefix + ".raw"]
            require(receipt.get("http_attempted") is True and receipt.get("http_status") == 200
                    and receipt.get("body_observed") is True and receipt.get("code") == "received"
                    and receipt.get("raw_path") == prefix + ".raw"
                    and receipt.get("raw_bytes") == len(raw)
                    and receipt.get("raw_sha256") == hash_bytes(raw), "original_observed_raw_binding")
        receipts.append(receipt)
    inventory = parallel.seal_parallel_inventory(plan, tuple(receipts),
            started_at=start["started_at"], completed_at=refusal["refused_at"], halted=True)
    payload = inventory.to_payload()
    require(payload["attempts_started"] == PARENT_STARTED
            and payload["http_invocations"] == PARENT_HTTP
            and payload["charged_response_bytes"] == PARENT_CHARGED_BYTES
            and payload["complete_frozen_request_sequence"] is False,
            "original_debits_charge_or_refusal_changed")
    value = VerifiedPrefix(source, plan, inventory, custody)
    value.check()
    return value


@contextmanager
def load_verified_prefix(root, source, plan, guard):
    registered(); _require_capture_platform(); guard.refresh()
    directory = root / PARENT
    claim_path = directory.parent / ("budget-" + original.PROTOCOL_SHA256 + ".json")
    require(_directory_names(directory) == parent_names(), "parent_exact_146_names")
    paths = tuple(directory / name for name in parent_names()) + (claim_path,)
    with PrefixSnapshot(paths, guard.check) as held:
        files = {name: held.read(directory / name, parallel.MAXIMUM_RESPONSE_BYTES) for name in parent_names()}
        claim_raw = held.read(claim_path, 65536)
        def custody():
            held.check()
            require(_directory_names(directory) == parent_names(), "parent_names_changed")
        def historical(head, name):
            require(cache._git(root, ["merge-base", "--is-ancestor", head, guard.binding()[1]], guard) == b"",
                    "parent_not_lane_ancestor")
            return cache._git(root, ["show", head + ":" + name], guard)
        prefix = verify_prefix(source, plan, files, claim_raw, historical, custody)
        guard.refresh()
        yield prefix


class RecoveryBinding:
    """Exact source/parent/child plan and original-position map identity."""
    def __init__(self, source, parent_plan, child_queries, child_plan, mapping):
        require(type(mapping) is tuple and len(mapping) == MAXIMUM_NEW_STARTS
                and hash_payload(mapping) == MAPPING_SHA256
                and child_queries.to_payload()["selected_query_ordinals"] == [row[1] for row in mapping]
                and child_plan.to_payload()["maximum_attempts"] == MAXIMUM_NEW_STARTS
                and child_plan.to_payload()["maximum_total_response_bytes"] == MAXIMUM_CHILD_BYTES,
                "prospective_child_position_mapping_or_budget_changed")
        self._anchor = self._identity = (source, parent_plan, child_queries, child_plan, mapping)

    def check(self):
        require(type(self) is RecoveryBinding and self._anchor is self._identity,
                "recovery_binding_changed")
        source, parent_plan, child_queries, child_plan, mapping = self._anchor
        source._guard(); parent_plan.guard(); child_queries._guard(); child_plan.guard()
        require(parent_plan._queries is source.query_plan and child_plan._queries is child_queries
                and type(mapping) is tuple and len(mapping) == MAXIMUM_NEW_STARTS,
                "recovery_selected_plan_changed")

    @property
    def child_plan(self):
        self.check()
        return self._anchor[3]

    @property
    def parent_plan(self):
        self.check()
        return self._anchor[1]

    @property
    def source(self):
        self.check()
        return self._anchor[0]


def freeze_recovery(source):
    registered()
    require(type(source) is anchors.NativeReportedAnchorPlan
            and source.sha256 == original.ANCHOR_PLAN_SHA256,
            "exact_original_anchor_plan_required")
    source._guard()
    selected = source.query_plan.to_payload()["selected_query_ordinals"]
    require(type(selected) is list and len(selected) == ORIGINAL_COUNT
            and type(source._matrix) is child_matrix_type(), "original_selected_matrix_required")
    mapping = tuple((position, selected[position - 1]) for position in NEW_POSITIONS)
    require(hash_payload(mapping) == MAPPING_SHA256, "prospective_original_to_matrix_mapping_changed")
    parent_plan = parallel.freeze_parallel_count_plan(source.query_plan,
            maximum_total_response_bytes=MAXIMUM_CUMULATIVE_BYTES)
    require(parent_plan.sha256 == original.PARALLEL_PLAN_SHA256,
            "original_parallel_plan_changed")
    child_queries = references.freeze_native_class_query_plan(source._matrix,
            mode="explicit_anchors", selected_query_ordinals=tuple(row[1] for row in mapping))
    child_plan = parallel.freeze_parallel_count_plan(child_queries,
            maximum_total_response_bytes=MAXIMUM_CHILD_BYTES)
    value = RecoveryBinding(source, parent_plan, child_queries, child_plan, mapping)
    value.check()
    return value


def child_matrix_type():
    from research.short_interest_etf.native_population_class_matrix import NativePopulationClassMatrix
    return NativePopulationClassMatrix


def expected_code_paths():
    return tuple(sorted(set((*cache.COUNT_CODE_FILES, DRIVER_PATH))))


def require_fd_headroom():
    """Refuse before spending the claim; never modify host/process limits."""
    try:
        soft, unused = resource.getrlimit(resource.RLIMIT_NOFILE)
        opened = len(os.listdir("/dev/fd"))
    except Exception:
        raise RecoveryRefusal("REFUSED: descriptor_headroom_unverifiable") from None
    require(soft == resource.RLIM_INFINITY or soft - opened >= 96,
            "insufficient_preclaim_descriptor_headroom")


def capture_child(root, directory, binding, prefix, *, guard, owned, code_identity_sha256,
        source_custody, code_custody, read_secret=read_named_keychain,
        clock=_utc_now, http=original.transport._http):
    """One new claim, then exact selected child tickets; never the old claim."""
    registered(); _require_capture_platform(); binding.check(); prefix.check()
    require(type(owned) is _OwnedOutput and owned._anchor[0] == root / OUTPUT == directory
            and type(guard) is lane.LaneGuard and _digest(code_identity_sha256)
            and prefix._anchor[0] is binding.source and prefix._anchor[1] is binding.parent_plan,
            "exact_child_parent_output_and_code_required")
    child_plan = binding.child_plan
    gate = lane.BoundedBatchGate(guard, child_plan)
    frozen_protocol = canonical_json(protocol())
    def local():
        guard.check(); registered()
        require(canonical_json(protocol()) == frozen_protocol, "recovery_protocol_changed")
        binding.check(); prefix.check(); source_custody(); code_custody(); owned.check()
    def publish_batch(items, *, drain=False):
        require(type(items) is tuple and 1 <= len(items) <= 24
                and len({name for name, raw in items}) == len(items), "finite_child_publication_batch")
        if not drain:
            gate.open_publication_batch(tuple(name for name, raw in items))
        for name, raw in items:
            require(type(raw) is bytes, "exact_original_publication_bytes_required")
            if drain:
                require(re.fullmatch(r"query-[0-9]{8}\.(raw|received\.json|diagnostic\.private\.json)", name)
                        and int(name[6:14]) in gate._state["started"],
                        "only_started_child_results_may_drain")
            else:
                gate.authorize_publication(name)
            local(); owned.publish(name, raw); local()
        if not drain:
            gate.close_publication_batch()
    def negative(name, payload):
        require(name in {"run.refused.json", "round.closed.refused.json"}, "fixed_refusal_name")
        guard.check(); owned.check()
        owned.publish(name, canonical_json({**payload, "protocol_sha256": PROTOCOL_SHA256,
            "authority": authority()}).encode())
    local(); guard.refresh()
    began = clock()
    parallel.clock(began)
    claim = {"schema": "si-manual-count-recovery-spent-claim-v1",
            "protocol_sha256": PROTOCOL_SHA256, "parent_manifest_sha256": PARENT_MANIFEST_SHA256,
            "parent_claim_sha256": PARENT_CLAIM_SHA256,
            "parent_inventory_sha256": prefix.inventory.sha256,
            "parent_charged_response_bytes": PARENT_CHARGED_BYTES,
            "child_plan_sha256": child_plan.sha256,
            "new_position_mapping_sha256": MAPPING_SHA256,
            "maximum_new_starts": MAXIMUM_NEW_STARTS,
            "maximum_cumulative_starts": MAXIMUM_CUMULATIVE_STARTS,
            "maximum_child_response_bytes": MAXIMUM_CHILD_BYTES,
            "maximum_cumulative_response_bytes": MAXIMUM_CUMULATIVE_BYTES,
            "code_head": guard.binding()[1], "remote_head": guard.binding()[2],
            "code_identity_sha256": code_identity_sha256, "started_at": began,
            "automatic_retries": 0, "restart_allowed": False}
    require_fd_headroom()
    owned.publish(CLAIM_NAME, canonical_json(claim).encode(), parent=True)
    publish_batch((("protocol.private.json", frozen_protocol.encode()),
        ("started.json", canonical_json({"schema": "si-manual-count-recovery-start-v1",
            "started_at": began, "parent_inventory_sha256": prefix.inventory.sha256,
            "child_plan_sha256": child_plan.sha256, "code_head": guard.binding()[1],
            "code_identity_sha256": code_identity_sha256,
            "protocol_sha256": PROTOCOL_SHA256, "authority": authority()}).encode())))
    attempted, charged, fatal, prior_start = 0, 0, False, parallel.clock(began)
    receipts, diagnostics = [], []
    def refuse(code, *, failed_ordinal=None):
        observed = clock()
        try:
            at = observed if prior_start <= parallel.clock(observed) else None
        except (parallel.ParallelCountRefusal, TypeError):
            at = None
        receipted = {entry["query_ordinal"] for entry in receipts}
        missing = set(range(1, attempted + 1)) - receipted
        unreceipted = {entry["query_ordinal"]: entry for entry in diagnostics
                      if entry["query_ordinal"] in missing}
        for ordinal in sorted(missing - set(unreceipted)):
            unreceipted[ordinal] = {"query_ordinal": ordinal,
                "failure_stage": "started_without_usable_receipt",
                "http_attempted": None, "http_status": None,
                "observed_receipt_at": None, "protocol_sha256": PROTOCOL_SHA256}
        # Every START without a usable typed receipt retains its full page
        # reservation, including clock/worker failures and a partially
        # submitted batch. Neither a later ordinal nor an absent receipt
        # erases that debit or the earlier negative diagnostic.
        refused_charge = charged + len(missing) * parallel.MAXIMUM_RESPONSE_BYTES
        known_http = sum(entry["http_attempted"] is True for entry in receipts)
        known_http += sum(entry["http_attempted"] is True for entry in unreceipted.values())
        negative("run.refused.json", {"schema": "si-manual-count-recovery-refused-v1",
            "code": code, "refused_at": at, "child_starts": attempted,
            "cumulative_starts": PARENT_STARTED + attempted,
            "child_charged_response_bytes": refused_charge,
            "cumulative_charged_response_bytes": PARENT_CHARGED_BYTES + refused_charge,
            "child_known_http_invocations": known_http,
            "cumulative_known_http_invocations": PARENT_HTTP + known_http,
            "http_invocation_count_exact": all(type(entry["http_attempted"]) is bool
                                               for entry in unreceipted.values()),
            "first_failed_child_ordinal": failed_ordinal,
            "unreceipted_diagnostics": tuple(unreceipted[ordinal] for ordinal in sorted(unreceipted)),
            "complete_child_capture": False})
    try:
        local(); secret = read_secret("massive")
        require(type(secret) is KeychainSecret, "exact_existing_named_Massive_key_required")
        local()
    except Exception:
        refuse("named_key_or_custody_unavailable_after_claim")
        raise RecoveryRefusal("REFUSED: named_key_or_custody_unavailable_after_claim") from None
    def worker(query, request, started):
        invoked, status, raw, media, code, stage = False, None, None, None, "material_request_refused", "local_scope"
        try:
            local(); stage = "opener_build"
            opener = original.transport.build_protected_opener(); stage = "opener_validation"
            original.transport._opener(opener); stage = "transport"
            invoked = True
            raw, media, status = http(opener, request, parallel.MAXIMUM_RESPONSE_BYTES)
            stage = "response_safety"
            require(type(raw) is bytes and len(raw) <= parallel.MAXIMUM_RESPONSE_BYTES
                    and type(media) is str and not secret.echoed_in(raw)
                    and not secret.echoed_in(media.encode()), "child_response_safety_refused")
            stage = "media"
            require(type(status) is int and status == 200 and original._json_media(media),
                    "child_response_media_refused")
            code = "received"
        except SharadarCaptureRefusal as error:
            status = error.http_status if type(error.http_status) is int and 100 <= error.http_status <= 599 else None
            raw, media = None, None
            if status == 404 and invoked:
                code = "HTTP_404_body_unobserved"
        except Exception:
            raw, media = None, None
        try:
            received = clock()
            valid_clock = parallel.clock(started) <= parallel.clock(received)
        except Exception:
            received, valid_clock = None, False
        if not valid_clock:
            raw, media, code, stage = None, None, "material_request_refused", "receipt_clock"
        ordinal = query.to_payload()["query_ordinal"]
        receipt = {"query_ordinal": ordinal, "request_sha256": query.to_payload()["request_sha256"],
            "started_at": started, "received_at": received, "http_attempted": invoked,
            "http_status": status, "body_observed": raw is not None,
            "raw_path": None, "raw_sha256": None, "raw_bytes": None,
            "content_type": media if raw is not None else None, "code": code}
        diagnostic = None if code == "received" else {"query_ordinal": ordinal,
            "failure_stage": stage, "http_attempted": invoked,
            "http_status": status if type(status) is int else None,
            "observed_receipt_at": received, "protocol_sha256": PROTOCOL_SHA256}
        return receipt, raw, diagnostic
    queries = iter(child_plan._queries.iter_queries())
    with ThreadPoolExecutor(max_workers=parallel.MAXIMUM_INFLIGHT) as pool:
        while attempted < MAXIMUM_NEW_STARTS and not fatal:
            slots = min(parallel.MAXIMUM_INFLIGHT,
                    (MAXIMUM_CHILD_BYTES - charged) // parallel.MAXIMUM_RESPONSE_BYTES)
            if slots == 0:
                fatal = True
                break
            tickets = tuple(islice(queries, slots))
            require(tickets, "exact_child_query_sequence_required")
            ready, pending, starts, results = [], [], [], []
            try:
                gate.open_HTTP_batch(tickets)
                for query in tickets:
                    request = original._wire_request(query, secret)
                    at = clock()
                    require(prior_start <= parallel.clock(at), "child_START_clock_backdated")
                    prior_start = parallel.clock(at)
                    ready.append((query, request, at))
                for query, request, at in ready:
                    gate.authorize_start(query)
                    attempted += 1
                    ticket = query.to_payload()
                    require(ticket["query_ordinal"] == attempted,
                            "only_next_selected_child_ordinal")
                    starts.append((f"query-{attempted:08d}.started.json", canonical_json({
                        "schema": "si-manual-count-recovery-request-start-v1",
                        "query_ordinal": attempted,
                        "original_count_position": NEW_POSITIONS[attempted - 1],
                        "request": ticket["request"],
                        "request_sha256": ticket["request_sha256"],
                        "started_at": at, "child_plan_sha256": child_plan.sha256,
                        "code_head": guard.binding()[1],
                        "whole_page_bytes_reserved": parallel.MAXIMUM_RESPONSE_BYTES}).encode()))
                publish_batch(tuple(starts))
                for query, request, at in ready:
                    pending.append((query, pool.submit(worker, query, request, at)))
            except Exception:
                fatal = True
            for query, future in pending:
                ordinal = query.to_payload()["query_ordinal"]
                try:
                    receipt, raw, diagnostic = future.result()
                except Exception:
                    gate.drain(query)
                    diagnostics.append({"query_ordinal": ordinal,
                        "failure_stage": "worker_result", "http_attempted": None,
                        "http_status": None, "observed_receipt_at": None,
                        "protocol_sha256": PROTOCOL_SHA256})
                    fatal = True
                    continue
                gate.drain(query)
                if receipt["received_at"] is None:
                    diagnostics.append(diagnostic)
                    fatal = True
                    continue
                if raw is not None:
                    receipt.update(raw_path=f"query-{ordinal:08d}.raw",
                            raw_sha256=hash_bytes(raw), raw_bytes=len(raw))
                    charged += len(raw)
                    results.append((receipt["raw_path"], raw))
                elif receipt["code"] == "material_request_refused":
                    charged += parallel.MAXIMUM_RESPONSE_BYTES
                    fatal = True
                receipts.append(receipt)
                results.append((f"query-{ordinal:08d}.received.json",
                    canonical_json(receipt).encode()))
                if diagnostic is not None:
                    diagnostics.append(diagnostic)
                    results.append((f"query-{ordinal:08d}.diagnostic.private.json",
                        canonical_json(diagnostic).encode()))
            try:
                if fatal:
                    gate._state["halted"] = True
                gate.close_HTTP_batch()
            except lane.LaneBatchRefusal:
                fatal = True
            if results:
                try:
                    publish_batch(tuple(results), drain=fatal)
                except Exception:
                    fatal = True
                    if all(not (directory / name).exists() for name, unused in results):
                        publish_batch(tuple(results), drain=True)
                    else:
                        refuse("immutable_child_partial_publication",
                            failed_ordinal=min((entry["query_ordinal"] for entry in diagnostics), default=None))
                        raise RecoveryRefusal("REFUSED: immutable_child_partial_publication") from None
    if fatal or len(receipts) != attempted:
        refuse("child_started_prefix_drained_or_unreceipted_no_restart",
            failed_ordinal=min((entry["query_ordinal"] for entry in diagnostics), default=None))
        return None
    require(attempted == MAXIMUM_NEW_STARTS and next(queries, None) is None,
            "exact_new_selected_child_sequence_not_completed")
    ended = clock()
    child_inventory = parallel.seal_parallel_inventory(child_plan, tuple(receipts),
            started_at=began, completed_at=ended, halted=False)
    gate.completion_evidence()
    marker = {"schema": "si-manual-count-recovery-child-completed-v1",
        "completed_at": ended, "child_inventory_sha256": child_inventory.sha256,
        "child_starts": attempted, "cumulative_starts": PARENT_STARTED + attempted,
        "parent_inventory_sha256": prefix.inventory.sha256,
        "original_position_47_negative_retained": True,
        "child_complete_source_only": True, "original_round_complete": False,
        "provisional_until_postpublication_remote_check": True,
        "authority": authority()}
    try:
        # Closing the publication batch performs a fresh matching-remote
        # observation too. Its failure belongs to the same refused closure
        # path as the subsequent audit: a provisional marker must never be
        # left as apparently final evidence after that boundary fails.
        publish_batch((("child.inventory.private.json", canonical_json(child_inventory.to_payload()).encode()),
            ("diagnostics.inventory.private.json", canonical_json(diagnostics).encode()),
            ("child.completed.json", canonical_json(marker).encode())))
        local(); audit_start = clock(); guard.refresh(); audit_end = clock()
        require(parallel.clock(audit_start) <= parallel.clock(audit_end),
                "postpublication_clock_refused")
    except Exception:
        negative("round.closed.refused.json", {
            "schema": "si-manual-count-recovery-postpublication-refused-v1",
            "code": "postpublication_remote_or_custody_refused",
            "child_inventory_sha256": child_inventory.sha256,
            "child_marker_sha256": hash_payload(marker),
            "complete_child_capture": False})
        raise RecoveryRefusal("REFUSED: postpublication_remote_or_custody_refused") from None
    local()
    owned.publish("round.closed.qualified.json", canonical_json({
        "schema": "si-manual-count-recovery-observed-closure-v1",
        "protocol_sha256": PROTOCOL_SHA256, "audit_started_at": audit_start,
        "audit_ended_at": audit_end, "matching_remote_observed_equal": True,
        "child_marker_sha256": hash_payload(marker),
        "child_inventory_sha256": child_inventory.sha256,
        "original_round_complete": False, "source_admitted": False,
        "ready_for_backtest": False, "authority": authority()}).encode())
    try:
        local(); guard.refresh(); local()
    except Exception:
        negative("round.closed.refused.json", {
            "schema": "si-manual-count-recovery-postpublication-refused-v1",
            "code": "postclosure_remote_or_custody_refused",
            "child_inventory_sha256": child_inventory.sha256,
            "child_marker_sha256": hash_payload(marker),
            "complete_child_capture": False})
        return None
    return child_inventory


def run_registered(root, *, runtime_head, actual_remote, complete_code_manifest):
    """Operational entrypoint, disabled until the exact committed protocol pins."""
    registered(); _require_capture_platform()
    require(root == lane.ROOT and type(complete_code_manifest) is dict,
            "designated_runtime_registration")
    actual_driver = Path(__file__).absolute()
    require(actual_driver == root / DRIVER_PATH and actual_driver.resolve() == actual_driver
            and stat.S_ISREG(actual_driver.lstat().st_mode),
            "actual_controller_driver_path_not_bound_to_manifest")
    guard = lane.LaneGuard(root, expected_head=runtime_head,
            expected_remote=actual_remote)
    guard.refresh()
    names = expected_code_paths()
    require(set(complete_code_manifest) == set(names)
            and all(_digest(value) for value in complete_code_manifest.values()),
            "exact_complete_current_code_manifest_required")
    with cache.HeldFiles(tuple(root / name for name in names), protected=False,
            boundary=guard.check) as current:
        entries, code_sha = cache._code_manifest(root, runtime_head, names, current, guard)
        require({entry["path"]: entry["sha256"] for entry in entries} == complete_code_manifest,
                "current_code_registration_changed")
        with cache.load_registered_cache(root, runtime_head=runtime_head,
                actual_remote=actual_remote, for_counts=True) as saved:
            binding = freeze_recovery(saved.plan)
            with load_verified_prefix(root, binding.source, binding.parent_plan, guard) as prefix:
                target = root / OUTPUT
                require(cache._git(root, ["check-ignore", str(target)], guard).strip() == str(target).encode(),
                        "child_output_not_ignored")
                directory = _prepare_capture_directory(target)
                with _OwnedOutput(directory, guard.check) as owned:
                    return capture_child(root, directory, binding, prefix,
                        guard=guard, owned=owned, code_identity_sha256=code_sha,
                        source_custody=saved.source_custody,
                        code_custody=lambda: (current.check(), saved.code_custody()))
