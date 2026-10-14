"""Concrete prospective cache composition; no actual execution by this draft.

Main registers the writer protocol before its single offline preflight. The
reader stays disabled until Main independently registers the five-file cache
closure/creator pins. Creator evidence is distinct from later runtime code.
"""
from contextlib import contextmanager
from pathlib import Path
import os
import re
import stat
import subprocess

from data.hashing import canonical_json, hash_bytes, hash_payload
import research.short_interest_etf.native_reported_anchor_cache as contract
import research.short_interest_etf.native_parallel_count_contract as parallel
from scripts import short_interest_reported_anchor_cache as adapter
from scripts import short_interest_lane_batch_guard as lane
from scripts import continue_short_interest_native_identity as capture
from scripts import finalize_short_interest_master_offline as finalizer
from scripts import build_short_interest_native_master_offline as native_builder
from scripts import load_short_interest_native_class_matrix as matrix_reader
from scripts import preflight_short_interest_native_reported_anchors as source_preflight
from scripts.qualify_finra_short_interest import _prepare_capture_directory, _require_capture_platform
from scripts.qualify_sharadar_companion import _utc_now

TARGET = Path("artifacts/short_interest/native_anchor_cache/cache-d58-v1")
WRITER_PROTOCOL_SHA256 = "cc673c635e19050f0dd0c0fddf8b9b446f53cbcd70fe535746ea84ea4e51d087"
REGISTERED_CACHE_PATH = "artifacts/short_interest/native_anchor_cache/cache-d58-v1"
REGISTERED_CREATOR_HEAD = "91f4158b6c9a9b4bf0099e60e5a50d2d9727587b"
REGISTERED_CREATOR_CODE_SHA256 = "f0d6d86dabadac5455223600d96920e5522783c1631655674ce71b0ff42a28bc"
MODULE_PATH = "scripts/capture_short_interest_native_anchor_cache.py"
WRITER_CODE_FILES = tuple(dict.fromkeys((*capture.CODE_FILES, *native_builder._CODE_FILES,
    "data/hashing.py", "research/short_interest_etf/contracts.py",
    "data/__init__.py", "ml/__init__.py", "research/__init__.py", "research/short_interest_etf/__init__.py",
    "data/financial_primitives.py", "research/short_interest_etf/availability.py",
    "research/short_interest_etf/preregistration.py", "research/short_interest_etf/finra_source_qualification.py",
    "research/short_interest_etf/sharadar_actual_input_binding.py",
    "research/short_interest_etf/massive_action_supplement.py",
    "research/short_interest_etf/massive_class_denominator.py",
    "research/short_interest_etf/native_parallel_count_contract.py",
    "research/short_interest_etf/native_population_class_matrix.py",
    "research/short_interest_etf/native_dated_class_reference.py",
    "research/short_interest_etf/native_dated_identity.py",
    "research/short_interest_etf/native_listed_venue_namespace.py",
    "research/short_interest_etf/native_reported_anchor_plan.py",
    "research/short_interest_etf/native_reported_anchor_cache.py",
    "scripts/short_interest_reported_anchor_cache.py",
    "scripts/short_interest_lane_batch_guard.py",
    "scripts/load_short_interest_native_class_matrix.py",
    "scripts/load_short_interest_native_identity_continuation.py",
    "scripts/verify_short_interest_native_identity_continuation.py",
    "scripts/stream_short_interest_native_identity_continuation.py",
    "scripts/read_short_interest_native_identity_continuation.py",
    "scripts/preflight_short_interest_native_reported_anchors.py", MODULE_PATH)))
COUNT_CODE_FILES = tuple(dict.fromkeys((*WRITER_CODE_FILES,
    "research/short_interest_etf/native_parallel_count_contract.py",
    "research/short_interest_etf/massive_class_denominator.py",
    "scripts/capture_short_interest_native_parallel_counts.py",
    "scripts/capture_short_interest_native_reported_count_round.py",
    "scripts/capture_short_interest_native_grouped_market.py",
    "research/short_interest_etf/native_grouped_market_source.py",
    "scripts/short_interest_keychain.py")))
NAMES = (*adapter.PHYSICAL_NAMES, "closure.private.json")


def require(condition, reason):
    contract.require(condition, reason)


def writer_protocol():
    return {"schema": "si-exact-anchor-cache-writer-v1", "target": str(TARGET),
        "observed_source": dict(contract.KNOWN), "master_capture_inventory_sha256": finalizer.SOURCE_INVENTORY_SHA256,
        "master_capture_budget_sha256": finalizer.BUDGET_SHA256,
        "code_files": list(WRITER_CODE_FILES), "names": list(NAMES),
        "source": "canonical_full_112_date_preflight_once_no_saved_completion_flag",
        "custody": "exclusive_owned0700_five0600_single_link_files;committed_code_FDs_and_source_byte_identity",
        "code_identity": "current_committed_head_and_complete_manifest_in_closure_not_self_referential_protocol",
        "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0,
        "source_admitted": False, "backtest_result_exists": False}


def _stamp(value):
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


class HeldFiles:
    """Read-only retained FDs. Whole-file Git boundaries; stat checks per chunk."""
    __slots__ = ("_anchor", "_identity", "_closed")

    def __init__(self, paths, *, protected, boundary):
        _require_capture_platform()
        require(type(paths) is tuple and 1 <= len(paths) <= 256 and type(protected) is bool,
                "finite_exact_custody_file_list")
        boundary()
        directories, entries, by_parent, created_fds = [], [], {}, []
        self._closed = False
        try:
            for path in paths:
                require(isinstance(path, Path) and path.is_absolute() and path.resolve() == path,
                        "custody_path_symlink_or_relative")
                if path.parent not in by_parent:
                    info = path.parent.lstat()
                    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                            and (stat.S_IMODE(info.st_mode) == 0o700 if protected else not info.st_mode & 0o022),
                            "custody_parent_protection")
                    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    created_fds.append(fd)
                    require(_stamp(os.fstat(fd))[:2] == _stamp(info)[:2], "custody_parent_open_identity")
                    by_parent[path.parent] = len(directories)
                    directories.append((path.parent, fd, (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))))
                parent = by_parent[path.parent]
                fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directories[parent][1])
                created_fds.append(fd)
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                        and (stat.S_IMODE(info.st_mode) == 0o600 if protected else not info.st_mode & 0o022),
                        "custody_file_protection")
                entries.append((path, parent, fd, _stamp(info), info.st_uid, stat.S_IMODE(info.st_mode)))
            anchor = tuple(directories), tuple(entries), protected, boundary
            self._anchor = self._identity = anchor
            self.check()
            boundary()
        except BaseException:
            for fd in reversed(created_fds):
                os.close(fd)
            self._closed = True
            raise

    def _binding(self):
        require(type(self) is HeldFiles and self._anchor is self._identity and self._closed is False
                and type(self._anchor) is tuple and len(self._anchor) == 4, "held_custody_binding_changed")
        return self._anchor

    def _entry_check(self, entry):
        directories, _, protected, boundary = self._binding()
        path, parent, fd, original, uid, mode = entry
        directory, directory_fd, directory_stamp = directories[parent]
        require(directory.resolve() == directory, "held_custody_parent_symlink")
        for value in (directory.lstat(), os.fstat(directory_fd)):
            require(stat.S_ISDIR(value.st_mode) and (value.st_dev, value.st_ino, value.st_uid,
                    stat.S_IMODE(value.st_mode)) == directory_stamp, "held_custody_parent_changed")
        for value in (os.fstat(fd), os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)):
            require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and _stamp(value) == original
                    and value.st_uid == uid == os.getuid() and stat.S_IMODE(value.st_mode) == mode,
                    "held_custody_file_changed")

    def check(self):
        directories, entries, protected, boundary = self._binding()
        for entry in entries:
            self._entry_check(entry)

    def read(self, path, maximum):
        directories, entries, protected, boundary = self._binding()
        entry = next((entry for entry in entries if entry[0] == path), None)
        require(entry is not None and type(maximum) is int and 0 < maximum <= 512 * 1024 * 1024
                and entry[3][2] <= maximum, "held_read_exact_bound_file")
        boundary()
        try:
            self._entry_check(entry)
            os.lseek(entry[2], 0, os.SEEK_SET)
            chunks, length = [], 0
            while True:
                self._entry_check(entry)
                raw = os.read(entry[2], min(65536, maximum + 1 - length))
                if not raw:
                    break
                chunks.append(raw)
                length += len(raw)
                require(length <= maximum, "held_read_limit")
            self._entry_check(entry)
            require(length == entry[3][2], "held_read_original_length")
            return b"".join(chunks)
        finally:
            boundary()

    def close(self):
        if self._closed is False:
            self._closed = True
            for entry in self._anchor[1]:
                os.close(entry[2])
            for entry in self._anchor[0]:
                os.close(entry[1])

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, *unused):
        self.close()


def _git(root, arguments, guard):
    guard.check()
    try:
        response = subprocess.run(["git", *arguments], cwd=root, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False)
    finally:
        guard.check()
    require(response.returncode == 0 and type(response.stdout) is bytes, "guarded_cache_Git_refused")
    return response.stdout


def _code_manifest(root, head, names, held, guard):
    entries = []
    for name in names:
        raw = held.read(root / name, 8 * 1024 * 1024)
        committed = _git(root, ["show", head + ":" + name], guard)
        require(raw == committed, "current_code_not_exact_committed_manifest")
        entries.append({"path": name, "sha256": hash_bytes(raw)})
    return tuple(entries), hash_payload({"git_commit": head, "files": entries})


def _summary(plan, summary):
    require(type(plan) is contract.reported.NativeReportedAnchorPlan and type(summary) is dict
            and summary.get("schema") == "si-native-full-identity-anchor-preflight-v1"
            and summary.get("status") == "source_only_plan_preflight"
            and summary.get("plan_sha256") == plan.sha256 == contract.KNOWN["plan_sha256"]
            and type(summary.get("request_budget")) is int and summary["request_budget"] == contract.KNOWN["request_budget"]
            and all(type(summary.get(key)) is int and summary[key] == 0 for key in
                ("provider_requests", "credential_reads", "outcome_looks", "qc_attempts"))
            and summary.get("source_admitted") is False and summary.get("ready_for_empirical_backtest") is False
            and summary.get("backtest_result_exists") is False, "canonical_source_preflight_required")
    pins = summary.get("source_pins")
    require(type(pins) is dict and pins.get("matrix_sha256") == contract.KNOWN["matrix_sha256"]
            and pins.get("parent_inventory_sha256") == contract.KNOWN["parent_inventory_sha256"]
            and pins.get("child_inventory_sha256") == contract.KNOWN["child_inventory_sha256"]
            and pins.get("child_budget_bytes_sha256") == contract.KNOWN["child_budget_sha256"]
            and contract.digest(pins.get("report_inventory_sha256")), "unchanged_completed_source_closure")
    header = plan.header()
    archives = {table: hash_bytes(raw) for archive, raw, table, request in plan._archives}
    source_archives = pins.get("original_archive_sha256")
    require(type(source_archives) is dict and set(source_archives) == {"tickers", "actions", "descriptions"}
            and all(contract.digest(value) for value in source_archives.values())
            and all(source_archives[table] == pin for table, pin in archives.items())
            and len(header["identity_source_pins"]) == contract.KNOWN["date_count"]
            and all(pin["master_archive_sha256"] == source_archives["tickers"] for pin in header["identity_source_pins"]),
            "original_archive_aliases_match_exact_plan")


def _candidate(plan, summary, *, head, code_sha, code_entries, prepared_at):
    _summary(plan, summary)
    value = adapter.prepare_cache(plan, runtime_head=head, cache_code_identity_sha256=code_sha, completed_at=prepared_at)
    closure = contract.parsed(value._closure)
    closure.update(writer_protocol=writer_protocol(), writer_protocol_sha256=WRITER_PROTOCOL_SHA256,
            creator_code_manifest=list(code_entries), source_preflight_summary=summary)
    raw = canonical_json(closure).encode()
    result = object.__new__(adapter.CacheCandidate)
    anchor = value._plan, value._files, raw, value._known
    for name, item in zip(("_plan", "_files", "_closure", "_known"), anchor):
        object.__setattr__(result, name, item)
    object.__setattr__(result, "_anchor", anchor)
    object.__setattr__(result, "_identity", anchor)
    result.guard()
    return result


def write_cache(root, *, runtime_head, actual_remote):
    _require_capture_platform()
    guard = lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote)
    guard.refresh()
    require(contract.digest(WRITER_PROTOCOL_SHA256) and hash_payload(writer_protocol()) == WRITER_PROTOCOL_SHA256,
            "cache_writer_protocol_not_prospectively_registered")
    target = root / TARGET
    require(_git(root, ["check-ignore", str(target)], guard).strip() == str(target).encode(), "cache_target_not_ignored")
    directory = _prepare_capture_directory(target)  # Exclusive before expensive replay; no old-cache overwrite.
    with capture._OwnedOutput(directory, lambda: None) as owned, \
            HeldFiles(tuple(root / name for name in WRITER_CODE_FILES), protected=False, boundary=guard.check) as code:
        entries, code_sha = _code_manifest(root, runtime_head, WRITER_CODE_FILES, code, guard)
        plan, summary = source_preflight.preflight(root, runtime_head=runtime_head, actual_remote=actual_remote)
        guard.refresh()
        code.check()
        candidate = _candidate(plan, summary, head=runtime_head, code_sha=code_sha,
                code_entries=entries, prepared_at=_utc_now())
        adapter.publish_owned_cache(candidate, owned, boundary=guard.check)
        require(tuple(sorted(os.listdir(owned._anchor[2]))) == tuple(sorted(NAMES)), "cache_exact_five_file_inventory")
        for name, raw in candidate.iter_files():
            guard.check()
            received = adapter.protected.read_owned_source(owned, name, max(1, len(raw)))
            guard.check()
            require(received == raw, "new_exclusive_cache_bytes_differ_from_verified_plan")
        guard.refresh()
        code.check()
        return {"status": "private_source_anchor_cache_written_and_verified", "closure_sha256": candidate.closure_sha256,
            "creator_head": runtime_head, "creator_code_sha256": code_sha, "plan_sha256": plan.sha256,
            "provider_requests": 0, "credential_reads": 0, "outcome_looks": 0, "qc_attempts": 0,
            "source_admitted": False, "backtest_result_exists": False}


class RegisteredCache:
    __slots__ = ("_anchor", "_identity")

    def __init__(self):
        raise contract.AnchorCacheRefusal("registered_cache_context_factory_required")

    def source_custody(self):
        require(type(self) is RegisteredCache and self._anchor is self._identity, "registered_cache_context_changed")
        plan, sources, code, code_sha = self._anchor
        plan._guard()
        for source in sources:
            source.check()  # FD/stat/object identity only, not source rehash/replay.
        cache_directories = sources[0]._anchor[0]
        require(len(cache_directories) == 1 and tuple(sorted(os.listdir(cache_directories[0][1]))) == tuple(sorted(NAMES)),
                "held_cache_exact_five_file_inventory_changed")

    def code_custody(self):
        require(type(self) is RegisteredCache and self._anchor is self._identity, "registered_cache_context_changed")
        self._anchor[0]._guard()
        self._anchor[2].check()

    @property
    def plan(self):
        self.source_custody()
        return self._anchor[0]

    @property
    def current_code_identity_sha256(self):
        self.code_custody()
        return self._anchor[3]


@contextmanager
def load_registered_cache(root, *, runtime_head, actual_remote, for_counts=False):
    _require_capture_platform()
    require(type(for_counts) is bool and REGISTERED_CACHE_PATH == str(TARGET)
            and type(REGISTERED_CREATOR_HEAD) is str and re.fullmatch(r"[0-9a-f]{40}", REGISTERED_CREATOR_HEAD)
            and contract.digest(REGISTERED_CREATOR_CODE_SHA256) and contract.digest(contract.REGISTERED_CLOSURE_SHA256),
            "cache_path_creator_and_closure_registration_pending")
    guard = lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote)
    guard.refresh()
    for ancestor in (contract.KNOWN["identity_capture_head"], REGISTERED_CREATOR_HEAD):
        require(_git(root, ["merge-base", "--is-ancestor", ancestor, runtime_head], guard) == b"", "cache_creator_not_lane_ancestor")
    directory = root / TARGET
    code_names = COUNT_CODE_FILES if for_counts else WRITER_CODE_FILES
    master_names = tuple(finalizer._source_names())
    source_paths = tuple(root / finalizer.SOURCE / name for name in master_names) + (
            root / finalizer.SOURCE.parent / ("budget-" + finalizer.master.PROTOCOL_SHA256 + ".json"),)
    matrix_paths = tuple(root / matrix_reader.SOURCE / name for name in matrix_reader.FILE_PINS)
    with capture._OwnedOutput(directory, lambda: None) as owned, \
            HeldFiles(tuple(directory / name for name in NAMES), protected=True, boundary=guard.check) as cache_files, \
            HeldFiles(source_paths, protected=True, boundary=guard.check) as master_files, \
            HeldFiles(matrix_paths, protected=True, boundary=guard.check) as matrix_files, \
            HeldFiles(tuple(root / name for name in code_names), protected=False, boundary=guard.check) as code_files:
        raw = cache_files.read(directory / "closure.private.json", 128 * 1024 * 1024)
        closure = contract.verify_closure(raw).payload()
        require(closure.get("cache_runtime_head") == REGISTERED_CREATOR_HEAD
                and closure.get("cache_code_identity_sha256") == REGISTERED_CREATOR_CODE_SHA256
                and closure.get("writer_protocol_sha256") == WRITER_PROTOCOL_SHA256
                and contract.exact(closure.get("writer_protocol"), writer_protocol()), "registered_cache_creator_protocol")
        entries = closure.get("creator_code_manifest")
        require(type(entries) is list and [entry.get("path") for entry in entries if type(entry) is dict] == list(WRITER_CODE_FILES)
                and all(set(entry) == {"path", "sha256"} and contract.digest(entry["sha256"]) for entry in entries)
                and hash_payload({"git_commit": REGISTERED_CREATOR_HEAD, "files": entries}) == REGISTERED_CREATOR_CODE_SHA256,
                "complete_registered_historical_creator_manifest")
        for entry in entries:
            committed = _git(root, ["show", REGISTERED_CREATOR_HEAD + ":" + entry["path"]], guard)
            require(hash_bytes(committed) == entry["sha256"], "historical_creator_blob_changed")
        current_entries, current_sha = _code_manifest(root, runtime_head, code_names, code_files, guard)
        matrix = matrix_reader.load_matrix(root, head=runtime_head, remote=actual_remote)
        originals, original_anchor = finalizer._reload(capture._GuardedSourcePath(root, guard.check))
        by_table = {archive.table: archive for archive in originals}
        require(set(by_table) == {"tickers", "actions", "descriptions"} and len(originals) == 3, "exact_original_archive_aliases")
        plan = adapter.reload_owned_cache(owned, matrix, by_table["actions"], by_table["descriptions"],
            boundary=guard.check, expected_runtime_head=REGISTERED_CREATOR_HEAD,
            expected_cache_code_identity_sha256=REGISTERED_CREATOR_CODE_SHA256)
        _summary(plan, closure.get("source_preflight_summary"))
        require(hash_bytes(by_table["tickers"].raw) == closure["source_preflight_summary"]["source_pins"]["original_archive_sha256"]["tickers"],
                "registered_original_TICKERS_archive_bytes")
        context = object.__new__(RegisteredCache)
        anchor = plan, (cache_files, master_files, matrix_files), code_files, current_sha
        context._anchor = context._identity = anchor
        context.code_custody()
        guard.refresh()
        try:
            yield context
        finally:
            # FDs close even on a material refusal; no source write/retry.
            code_files.check()


def capture_registered_counts(root, *, runtime_head, actual_remote):
    """Concrete composition; requires separately registered count protocol/pins."""
    _require_capture_platform()
    from scripts import capture_short_interest_native_reported_count_round as kernel
    with load_registered_cache(root, runtime_head=runtime_head, actual_remote=actual_remote, for_counts=True) as saved:
        source = saved.plan
        plan = parallel.freeze_parallel_count_plan(source.query_plan,
                maximum_total_response_bytes=kernel.MAXIMUM_TOTAL_RESPONSE_BYTES)
        guard = lane.LaneGuard(root, expected_head=runtime_head, expected_remote=actual_remote)
        guard.refresh()
        target = root / "artifacts/short_interest/native_reported_counts" / ("count-round-" + kernel.PROTOCOL_SHA256[:16])
        require(contract.digest(kernel.PROTOCOL_SHA256), "count_protocol_pending_before_new_output")
        require(_git(root, ["check-ignore", str(target)], guard).strip() == str(target).encode(), "count_output_not_ignored")
        directory = _prepare_capture_directory(target)
        with capture._OwnedOutput(directory, lambda: None) as owned:
            return kernel.capture_loaded_source(root, directory, source, plan, head=runtime_head,
                remote=actual_remote, code_identity_sha256=saved.current_code_identity_sha256,
                source_custody=saved.source_custody, code_custody=saved.code_custody, owned=owned, guard=guard)
