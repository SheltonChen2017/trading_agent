"""Versioned offline replay using an exact historical validator source view.

Only the captured union's four source-identity reads see the immutable Git
image that executes. Ordinary artifact reads use their original paths. This
adapter grants no permission to change a frozen file or resume acquisition.
The earlier replay adapter and its receipt contract are unchanged.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
import hashlib
import importlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import types


VERSION = "INSETF-IB1B-HISTORICAL-SOURCE-VIEW-REPLAY-v4.1"
SOURCE_VIEW_VERSION = VERSION + "/source-view"
_WORKER_PATH = "research/insider_buying_sec_recovery_v4_source_view.py"
_BASE_PATH = "research/insider_buying_sec_recovery_v4_historical_replay.py"
_TOKEN = object()
_CAPTURED_BASE = None
_MAX_READ_CYCLES = 512
_REPLAY_HASHES = {
    "source_union_sha256": "e7d45dbcb41a027d9986fc94ce760301bd4c5f918dc7fa63bbbc02e0f38f8cc5",
    "partial_descriptor_sha256": "44e6bb22b9175c6db91a0faf25862ffa6e34b43268dddd81d0b9ff6338abb876",
    "diagnostic_descriptor_sha256": "5ddc9f04b16fe07a0a8c44b9693cff0410a555cc1aa745b7eb12dedd136e300f",
    "v4_plan_sha256": "2dd336cf00f822a0b798687c4c1f68cc52dddec57537bca74e4db9f9ed4a7f2a",
    "partition_sha256": "f1f5cc2cf797978e026801b30e2fe5990740adb47adfd2aeabf965311137d974",
    "proposed_unattempted_inventory_sha256": "472e33f1213484caf8d218896f1c6161feda414dbf2e3e8c86b7487354d64d1a",
}


class HistoricalSourceViewError(ValueError):
    """Historical source identity or bounded replay could not be proved."""


def _refuse(reason: str) -> None:
    raise HistoricalSourceViewError("REFUSED: " + reason)


def _base():
    # In the worker this is the already hash-checked captured byte image, never
    # a filesystem import. The trusted parent imports only a stdlib-only module.
    if _CAPTURED_BASE is not None:
        return _CAPTURED_BASE
    return importlib.import_module("research.insider_buying_sec_recovery_v4_historical_replay")


def _source_read_trace_digest(cycles: int) -> str:
    base = _base()
    digest = hashlib.sha256()
    for cycle in range(cycles):
        for relative, sha in base.HISTORICAL_FILES:
            digest.update(base._canonical({"cycle": cycle, "path": relative,
                "sha256": sha, "source_kind": "historical_git_blob"}) + b"\n")
    return digest.hexdigest()


class _DiagnosticFacade:
    __slots__ = ("_original", "_root")

    def __init__(self, original, root):
        self._original, self._root = original, root

    def __getattr__(self, name):
        if name == "_LANE_ROOT":
            return self._root
        return getattr(self._original, name)


class _SourceRootView:
    __slots__ = ("_view", "_root")

    def __init__(self, view, root):
        self._view, self._root = view, root

    def __truediv__(self, relative):
        caller = sys._getframe(1)
        if not self._view._is_caller(caller):
            return self._root / relative
        self._view._require_call(caller, relative)
        return _SourcePathView(self._view, relative, self._root / relative)

    def __fspath__(self):
        return os.fspath(self._root)

    def __str__(self):
        return str(self._root)


class _SourcePathView:
    __slots__ = ("_view", "_relative", "_path")

    def __init__(self, view, relative, path):
        self._view, self._relative, self._path = view, relative, path

    def resolve(self):
        self._view._require_call(sys._getframe(1), self._relative)
        if self._path.resolve() != self._path:
            _refuse("historical source path is redirected")
        return self

    def read_bytes(self):
        caller = sys._getframe(1)
        self._view._require_call(caller, self._relative)
        if caller.f_locals.get("path") is not self:
            _refuse("historical source read does not use the bound loop path")
        return self._view._read(caller, self._relative)

    def __fspath__(self):
        return os.fspath(self._path)

    def __eq__(self, other):
        try:
            return self._path == Path(os.fspath(other))
        except TypeError:
            return NotImplemented

    def __ne__(self, other):
        equal = self.__eq__(other)
        return NotImplemented if equal is NotImplemented else not equal


class HistoricalSourceView:
    """One-use, callsite-bound view of the exact four executing source blobs.

The module-global diagnostic reference alone is temporarily replaced. Its
classes, helpers and artifact roots remain those of the original module.
The real diagnostic module, pathlib and ordinary file operations are intact.
"""

    def __init__(self, blobs, union, modules=None):
        base = _base()
        try:
            self._blobs = base._validate_historical_blobs(blobs)
            self._files = base.HISTORICAL_FILES
            self._commit = base.HISTORICAL_COMMIT
            self._validator_sha = base.HISTORICAL_VALIDATOR_SHA256
            if type(union) is not types.ModuleType:
                _refuse("historical union module is required")
            if modules is None:
                modules = (union, union.campaign, union.complete_submission, union.raw_projection)
            if type(modules) is not tuple or len(modules) != 4 or modules[0] is not union:
                _refuse("historical module inventory differs")
            expected = (union, union.campaign, union.complete_submission, union.raw_projection)
            if any(actual is not wanted for actual, wanted in zip(modules, expected, strict=True)):
                _refuse("historical module references differ")
            self._modules = dict(zip((p for p, _ in base.HISTORICAL_FILES), modules, strict=True))
            self._union = union
            self._function = union._validator_source_sha256
            if (type(self._function) is not types.FunctionType
                    or self._function.__globals__ is not union.__dict__):
                _refuse("historical validator function globals differ")
            self._code = self._function.__code__
            compiled = compile(blobs[0][1], str(base.LANE_ROOT / base.HISTORICAL_FILES[0][0]),
                               "exec", dont_inherit=True)
            codes = [item for item in compiled.co_consts if type(item) is types.CodeType
                     and item.co_name == "_validator_source_sha256"]
            if (len(codes) != 1 or self._code != codes[0]
                    or self._code.co_filename != str(base.LANE_ROOT / base.HISTORICAL_FILES[0][0])
                    or self._function.__name__ != "_validator_source_sha256"
                    or self._function.__qualname__ != "_validator_source_sha256"):
                _refuse("historical validator function code differs from its Git image")
            hashing = sys.modules.get("data.hashing")
            if (type(hashing) is not types.ModuleType or union.Path is not Path or union.sys is not sys
                    or type(hashing.hash_bytes) is not types.FunctionType
                    or type(hashing.hash_payload) is not types.FunctionType
                    or union.hash_bytes is not hashing.hash_bytes or union.hash_payload is not hashing.hash_payload
                    or self._function.__defaults__ is not None or self._function.__kwdefaults__ is not None
                    or self._function.__closure__ is not None):
                _refuse("historical validator critical globals or function shape differ")
            self._hashing = hashing
            self._hash_bytes, self._hash_payload = hashing.hash_bytes, hashing.hash_payload
            self._hash_codes = (hashing.hash_bytes.__code__, hashing.hash_payload.__code__)
            self._original = union.diagnostic
            if type(self._original) is not types.ModuleType:
                _refuse("original diagnostic module differs")
            root = self._original._LANE_ROOT
            if not isinstance(root, Path) or root != base.LANE_ROOT or root.resolve() != root:
                _refuse("historical source root differs from the designated lane")
            self._root = root
            self._root_view = _SourceRootView(self, root)
            self._facade = _DiagnosticFacade(self._original, self._root_view)
            self._entered = False
            self._installed = False
            self._clean_exit = False
            self._index = 0
            self._frame_id = None
            self._cycles = 0
            self._trace = hashlib.sha256()
            self._assert_binding(installed=False)
        except HistoricalSourceViewError:
            raise
        except (base.HistoricalReplayError, AttributeError, KeyError, TypeError, ValueError, OSError, SyntaxError):
            raise HistoricalSourceViewError("REFUSED: historical source view inputs differ") from None

    def _assert_binding(self, *, installed):
        base = _base()
        values = self._union.__dict__
        if (base.HISTORICAL_FILES != self._files or base.HISTORICAL_COMMIT != self._commit
                or base.HISTORICAL_VALIDATOR_SHA256 != self._validator_sha
                or values.get("_validator_source_sha256") is not self._function
                or self._function.__code__ is not self._code
                or self._function.__globals__ is not self._union.__dict__
                or self._function.__name__ != "_validator_source_sha256"
                or self._function.__qualname__ != "_validator_source_sha256"
                or self._function.__defaults__ is not None or self._function.__kwdefaults__ is not None
                or self._function.__closure__ is not None
                or values.get("diagnostic") is not (self._facade if installed else self._original)
                or values.get("Path") is not Path or values.get("sys") is not sys
                or sys.modules.get("data.hashing") is not self._hashing
                or values.get("hash_bytes") is not self._hash_bytes or values.get("hash_payload") is not self._hash_payload
                or self._hashing.__dict__.get("hash_bytes") is not self._hash_bytes
                or self._hashing.__dict__.get("hash_payload") is not self._hash_payload
                or self._hash_bytes.__code__ is not self._hash_codes[0]
                or self._hash_payload.__code__ is not self._hash_codes[1]
                or self._original.__dict__.get("_LANE_ROOT") is not self._root
                or self._facade._original is not self._original or self._facade._root is not self._root_view
                or self._root_view._view is not self or self._root_view._root is not self._root):
            _refuse("historical validator or diagnostic binding changed")
        expected = (self._union, values.get("campaign"), values.get("complete_submission"), values.get("raw_projection"))
        for (relative, _), module in zip(self._files, expected, strict=True):
            name, _ = base._module_name(relative)
            path = base.LANE_ROOT / relative
            if (module is not self._modules[relative] or type(module) is not types.ModuleType
                    or module.__name__ != name or sys.modules.get(name) is not module
                    or type(module.__dict__.get("__file__")) is not str
                    or Path(module.__file__) != path or path.resolve() != path):
                _refuse("historical module origin or identity differs")

    def _is_caller(self, caller):
        return caller.f_code is self._code and caller.f_globals is self._union.__dict__

    def _require_call(self, caller, relative):
        if not self._installed or not self._is_caller(caller):
            _refuse("historical source path used outside the bound validator callsite")
        self._assert_binding(installed=True)
        if (type(relative) is not str or relative not in self._modules
                or caller.f_locals.get("relative") != relative
                or caller.f_locals.get("module") is not self._modules[relative]):
            _refuse("historical source loop identity differs")

    def _read(self, caller, relative):
        self._require_call(caller, relative)
        files = _base().HISTORICAL_FILES
        if relative != files[self._index][0]:
            _refuse("historical source reads are missing, repeated or reordered")
        if self._index == 0:
            if self._cycles >= _MAX_READ_CYCLES:
                _refuse("historical source read cycles exceed their cap")
            self._frame_id = id(caller)
        elif self._frame_id != id(caller):
            _refuse("historical source read cycle crossed validator calls")
        raw = self._blobs[self._index][1]
        sha = _base()._sha(raw)
        if sha != files[self._index][1]:
            _refuse("historical source view bytes changed")
        self._trace.update(_base()._canonical({"cycle": self._cycles, "path": relative,
            "sha256": sha, "source_kind": "historical_git_blob"}) + b"\n")
        self._index += 1
        if self._index == len(files):
            self._index, self._frame_id = 0, None
            self._cycles += 1
        return raw

    def __enter__(self):
        if self._entered:
            _refuse("historical source view cannot be reused or nested")
        self._assert_binding(installed=False)
        self._entered = self._installed = True
        self._union.diagnostic = self._facade
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self._assert_binding(installed=True)
            if exc_type is None and (self._index or not self._cycles):
                _refuse("historical source view did not complete an ordered read cycle")
            self._clean_exit = exc_type is None
        finally:
            self._union.diagnostic = self._original
            self._installed = False
        return False

    def proof(self):
        if (not self._installed and not self._clean_exit) or self._index or not self._cycles:
            _refuse("historical source view has no complete read proof")
        self._assert_binding(installed=self._installed)
        base = _base()
        return {"kind": SOURCE_VIEW_VERSION, "historical_commit": base.HISTORICAL_COMMIT,
            "historical_validator_sha256": base.HISTORICAL_VALIDATOR_SHA256,
            "files": [{"path": p, "sha256": sha} for p, sha in base.HISTORICAL_FILES],
            "validator_function_name": "_validator_source_sha256",
            "ordered_read_cycles": self._cycles, "source_read_count": self._cycles * 4,
            "source_read_trace_sha256": self._trace.hexdigest(), "callsite_bound": True}


def _validate_receipt(payload):
    base = _base()
    hashes = ("worker_source_sha256", "base_source_sha256", "current_source_inventory_sha256",
              "source_union_sha256", "partial_descriptor_sha256", "diagnostic_descriptor_sha256",
              "v4_plan_sha256", "partition_sha256", "proposed_unattempted_inventory_sha256")
    keys = {"kind", "scope", "repository_head", "historical_commit", "historical_validator_sha256",
        "historical_files", "worker_bootstrap_sha256", "executed_modules", "historical_function_paths",
        "source_view", "counts", "total_parents", "source_bound_count", "v3_attempt_count", "v3_completed_count",
        "stopped_v3_disposition", "diagnostic_report_sha256", "diagnostic_body_sha256", "diagnostic_body_size_bytes",
        "current_validator_equality_required", "historical_environment_recreated", "frozen_files_may_be_thawed",
        "isolation", "authority", *hashes}
    if (type(payload) is not dict or set(payload) != keys or payload["kind"] != VERSION
            or payload["scope"] != "observed_offline_historical_source_view_replay"
            or type(payload["repository_head"]) is not str or base._COMMIT.fullmatch(payload["repository_head"]) is None
            or payload["historical_commit"] != base.HISTORICAL_COMMIT
            or payload["historical_validator_sha256"] != base.HISTORICAL_VALIDATOR_SHA256
            or payload["historical_files"] != [{"path": p, "sha256": s} for p, s in base.HISTORICAL_FILES]
            or payload["worker_bootstrap_sha256"] != base._sha(_BOOTSTRAP.encode("utf-8"))
            or payload["historical_function_paths"] != [p for p, _ in base.HISTORICAL_FILES]
            or any(not base._is_sha(payload[k]) for k in hashes)
            or any(payload[k] != expected for k, expected in _REPLAY_HASHES.items())
            or type(payload["counts"]) is not dict or set(payload["counts"]) != set(base._COUNTS)
            or any(type(payload["counts"][k]) is not int or payload["counts"][k] != v for k, v in base._COUNTS.items())
            or any(type(payload[k]) is not int or payload[k] != v for k, v in (
                ("total_parents", 99394), ("source_bound_count", 19526), ("v3_attempt_count", 1847),
                ("v3_completed_count", 1846), ("diagnostic_body_size_bytes", 7373)))
            or payload["stopped_v3_disposition"] != "preserved_unresolved_not_resumable"
            or payload["diagnostic_report_sha256"] != base.DIAGNOSTIC_REPORT_SHA256
            or payload["diagnostic_body_sha256"] != base.DIAGNOSTIC_BODY_SHA256
            or any(payload[k] is not False for k in ("current_validator_equality_required",
                "historical_environment_recreated", "frozen_files_may_be_thawed"))
            or type(payload["authority"]) is not dict or payload["authority"] != base._AUTHORITY
            or any(type(payload["authority"][k]) is not type(v) for k, v in base._AUTHORITY.items())
            or type(payload["isolation"]) is not dict or payload["isolation"] != {
                "os_network_denied": True, "os_file_writes_denied": True, "os_process_fork_denied": True,
                "audit_additional_processes_denied": True, "source_only_lane_imports": True}
            or any(v is not True for v in payload["isolation"].values())):
        _refuse("source-view receipt schema, anchors or authority differs")
    proof = payload["source_view"]
    proof_keys = {"kind", "historical_commit", "historical_validator_sha256", "files", "validator_function_name",
                  "ordered_read_cycles", "source_read_count", "source_read_trace_sha256", "callsite_bound"}
    if (type(proof) is not dict or set(proof) != proof_keys or proof["kind"] != SOURCE_VIEW_VERSION
            or proof["historical_commit"] != base.HISTORICAL_COMMIT
            or proof["historical_validator_sha256"] != base.HISTORICAL_VALIDATOR_SHA256
            or proof["files"] != payload["historical_files"]
            or proof["validator_function_name"] != "_validator_source_sha256"
            or type(proof["ordered_read_cycles"]) is not int or not 1 <= proof["ordered_read_cycles"] <= _MAX_READ_CYCLES
            or type(proof["source_read_count"]) is not int or proof["source_read_count"] != proof["ordered_read_cycles"] * 4
            or proof["source_read_trace_sha256"] != _source_read_trace_digest(proof["ordered_read_cycles"])
            or proof["callsite_bound"] is not True):
        _refuse("historical source read proof differs")
    trace = payload["executed_modules"]
    if type(trace) is not list or not 6 <= len(trace) <= 512:
        _refuse("source-view execution inventory differs")
    seen, historical = set(), {}
    for row in trace:
        if (type(row) is not dict or set(row) != {"path", "sha256", "source_kind"}
                or type(row["path"]) is not str or row["path"] in seen or not base._is_sha(row["sha256"])
                or row["source_kind"] not in {"historical_git_blob", "current_source_snapshot"}):
            _refuse("source-view executed-source row differs")
        try:
            base._module_name(row["path"])
        except base.HistoricalReplayError:
            _refuse("source-view executed path is outside the lane inventory")
        seen.add(row["path"])
        if row["source_kind"] == "historical_git_blob":
            historical[row["path"]] = row["sha256"]
    if historical != dict(base.HISTORICAL_FILES):
        _refuse("source-view worker did not execute the exact historical validators")
    for path, key in ((_WORKER_PATH, "worker_source_sha256"), (_BASE_PATH, "base_source_sha256")):
        row = next((r for r in trace if r["path"] == path), None)
        if row is None or row["source_kind"] != "current_source_snapshot" or row["sha256"] != payload[key]:
            _refuse("source-view worker or base execution is not source-bound")
    return payload


@dataclass(frozen=True, slots=True)
class SourceViewReplayReceipt:
    _raw: bytes = field(repr=False)
    _sha256: str
    _token: object = field(repr=False, compare=False)
    _factory_raw: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def to_payload(self):
        base = _base()
        if (type(self) is not SourceViewReplayReceipt or self._token is not _TOKEN
                or type(self._raw) is not bytes or self._raw != self._factory_raw
                or base._sha(self._raw) != self._sha256):
            _refuse("source-view receipt was not built here or was altered")
        return _validate_receipt(json.loads(self._raw))

    @property
    def sha256(self):
        self.to_payload()
        return self._sha256


def _seal(payload):
    base = _base()
    _validate_receipt(payload)
    raw = base._canonical(payload)
    receipt = SourceViewReplayReceipt(raw, base._sha(raw), _TOKEN)
    object.__setattr__(receipt, "_factory_raw", raw)
    return receipt


def _worker_main(bundle):
    base = _base()
    finder = None
    previous_profile = sys.getprofile()
    try:
        sys.dont_write_bytecode = True
        blobs = base._validate_historical_blobs(base._decode_sources(bundle["historical_sources"]))
        sources = base._decode_sources(bundle["current_sources"])
        current = dict(sources)
        if (base._sha(current[_WORKER_PATH]) != bundle["worker_source_sha256"]
                or base._sha(current[_BASE_PATH]) != bundle["base_source_sha256"]):
            _refuse("worker or base differs from its captured image")
        base._assert_sources_unchanged(sources)
        if any(n.split(".")[0] in {"research", "data", "ml"} for n in sys.modules):
            _refuse("source-view worker inherited repository modules")
        finder = base._HistoricalBlobFinder(blobs, sources)
        finder.executed.extend({"path": p, "sha256": base._sha(current[p]),
                                "source_kind": "current_source_snapshot"} for p in (_BASE_PATH, _WORKER_PATH))
        sys.meta_path.insert(0, finder)
        sys.setprofile(finder.profile)
        union = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_union")
        campaign = importlib.import_module("research.insider_buying_sec_all_form4_parent_campaign")
        prior = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_preflight")
        completed = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_verifier")
        partial = importlib.import_module("research.insider_buying_sec_all_form4_parent_recovery_partial_verifier")
        diagnostic = importlib.import_module("research.insider_buying_sec_all_form4_parent_ambiguous_diagnostic_verifier")
        v4 = importlib.import_module("research.insider_buying.sec_recovery_v4_plan")
        hash_payload = importlib.import_module("data.hashing").hash_payload
        with HistoricalSourceView(blobs, union) as view:
            def source_replay():
                return union.preflight_observed_all_form4_parent_recovery_union(*base.SOURCE_ROOTS,
                    diagnostic_capture_git_commit=union.OBSERVED_DIAGNOSTIC_CAPTURE_COMMIT,
                    expected_diagnostic_report_sha256=union.OBSERVED_DIAGNOSTIC_REPORT_SHA256)
            source = source_replay()
            plan = campaign._build_real_plan(*base.SOURCE_ROOTS[:6])
            expectation = prior.PartialCampaignExpectation(capture_git_commit=prior.PRIOR_CAPTURE_GIT_COMMIT,
                shard_report_sha256s=prior.PRIOR_SHARD_REPORT_SHA256S, completed_counts=(8192, 1347),
                reused_counts=(972, 226), total_attempt_count=8342)
            def partial_replay():
                result = partial._verify_partial(plan, source, base.SOURCE_ROOTS[6], base.SOURCE_ROOTS[7],
                    base.SOURCE_ROOTS[5], base.V3_ROOT, prior_expectation=expectation,
                    capture_git_commit=base.HISTORICAL_COMMIT, capture_code_sha256=base.EXECUTOR_SHA256)
                partial._require_observed_anchors(result)
                if result.completed_new_count != 1846 or result.attempt_count != 1847:
                    _refuse("stopped v3 count anchors differ")
                return result
            stopped = partial_replay()
            accepted = diagnostic.verify_accepted_ambiguity_diagnostic(stopped, base.DIAGNOSTIC_ROOT,
                capture_git_commit=base.DIAGNOSTIC_CAPTURE_COMMIT, expected_report_sha256=base.DIAGNOSTIC_REPORT_SHA256)
            classes, _ = completed._source_classes(plan, source)
            p = {key: getattr(stopped, key) for key in (*v4._PARTIAL_HASHES, *v4._PARTIAL_INTS)}
            d = {key: getattr(accepted, key) for key in (*v4._DIAGNOSTIC_HASHES,
                "diagnostic_capture_git_commit", "pending_global_index", "body_size_bytes")}
            proposal = v4.build_recovery_v4_offline_plan(tuple(r.to_payload() for r in plan.requests),
                tuple(classes), p, d, v4.bind_v3_historical_validator(base.HISTORICAL_COMMIT, blobs))
            body = proposal.to_payload()
            if source_replay() != source or partial_replay() != stopped:
                _refuse("retained source or stopped v3 state changed")
            if diagnostic.verify_accepted_ambiguity_diagnostic(stopped, base.DIAGNOSTIC_ROOT,
                    capture_git_commit=base.DIAGNOSTIC_CAPTURE_COMMIT,
                    expected_report_sha256=base.DIAGNOSTIC_REPORT_SHA256) != accepted:
                _refuse("separate accepted diagnostic changed")
        proof = view.proof()
        base._assert_sources_unchanged(sources)
        if finder.called != {path for path, _ in base.HISTORICAL_FILES}:
            _refuse("historical validator function execution was not observed")
        payload = {"kind": VERSION, "scope": "observed_offline_historical_source_view_replay",
            "repository_head": bundle["repository_head"], "historical_commit": base.HISTORICAL_COMMIT,
            "historical_validator_sha256": base.HISTORICAL_VALIDATOR_SHA256,
            "historical_files": [{"path": p, "sha256": s} for p, s in base.HISTORICAL_FILES],
            "worker_bootstrap_sha256": base._sha(_BOOTSTRAP.encode("utf-8")),
            "worker_source_sha256": bundle["worker_source_sha256"], "base_source_sha256": bundle["base_source_sha256"],
            "current_source_inventory_sha256": base._digest([{"path": p, "sha256": base._sha(r)} for p, r in sources]),
            "executed_modules": finder.executed, "historical_function_paths": [p for p, _ in base.HISTORICAL_FILES],
            "source_view": proof, "source_union_sha256": hash_payload(source),
            "partial_descriptor_sha256": hash_payload(p), "diagnostic_descriptor_sha256": hash_payload(d),
            "v4_plan_sha256": proposal.sha256, "partition_sha256": body["partition_sha256"],
            "proposed_unattempted_inventory_sha256": body["proposed_unattempted_inventory_sha256"],
            "counts": body["class_counts"], "total_parents": 99394, "source_bound_count": 19526,
            "v3_attempt_count": stopped.attempt_count, "v3_completed_count": stopped.completed_new_count,
            "stopped_v3_disposition": body["stopped_v3_disposition"], "diagnostic_report_sha256": accepted.report_sha256,
            "diagnostic_body_sha256": accepted.body_sha256, "diagnostic_body_size_bytes": accepted.body_size_bytes,
            "current_validator_equality_required": False, "historical_environment_recreated": False,
            "frozen_files_may_be_thawed": False, "authority": dict(base._AUTHORITY), "isolation": {
                "os_network_denied": True, "os_file_writes_denied": True, "os_process_fork_denied": True,
                "audit_additional_processes_denied": True, "source_only_lane_imports": True}}
        _validate_receipt(payload)
        raw = base._canonical(payload)
        if len(raw) > base._MAX_OUTPUT_BYTES:
            _refuse("source-view worker aggregate exceeds its cap")
        sys.stdout.buffer.write(raw + b"\n")
        sys.stdout.buffer.flush()
    except BaseException:
        sys.stderr.write("REFUSED: isolated historical source-view replay failed\n")
        raise SystemExit(1) from None
    finally:
        sys.setprofile(previous_profile)
        if finder is not None and finder in sys.meta_path:
            sys.meta_path.remove(finder)


_BOOTSTRAP = """import base64, hashlib, json, sys, types
raw = sys.stdin.buffer.read(33554433)
if len(raw) > 33554432:
    raise SystemExit(2)
b = json.loads(raw)
rows = [r for r in b['current_sources'] if r['path'] == 'research/insider_buying_sec_recovery_v4_historical_replay.py']
if len(rows) != 1:
    raise SystemExit(2)
old = base64.b64decode(rows[0]['source_b64'], validate=True)
if hashlib.sha256(old).hexdigest() != rows[0]['sha256'] or rows[0]['sha256'] != b['base_source_sha256']:
    raise SystemExit(2)
base = types.ModuleType('_insider_source_view_base')
base.__file__ = sys.argv[2]
sys.modules[base.__name__] = base
exec(compile(old, base.__file__, 'exec', dont_inherit=True), base.__dict__)
sys.addaudithook(base._audit_event)
s = base64.b64decode(b['worker_source_b64'], validate=True)
if hashlib.sha256(s).hexdigest() != b['worker_source_sha256']:
    raise SystemExit(2)
m = types.ModuleType('_insider_source_view_worker')
m.__file__ = sys.argv[1]
sys.modules[m.__name__] = m
exec(compile(s, m.__file__, 'exec', dont_inherit=True), m.__dict__)
m._CAPTURED_BASE = base
m._worker_main(b)
"""


def _run_isolated_worker(raw, timeout_seconds):
    """Same bounded pipe protocol; a distinct bootstrap binds both wrappers."""
    base = _base()
    if type(raw) is not bytes or not 0 < len(raw) <= base._MAX_INPUT_BYTES:
        _refuse("source-view worker input exceeds its cap")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600:
        _refuse("source-view worker timeout differs")
    command = ("/usr/bin/sandbox-exec", "-p", base._worker_policy(),
        str(Path(sys.executable).resolve()), "-I", "-S", "-B", "-c", _BOOTSTRAP,
        str(base.LANE_ROOT / _WORKER_PATH), str(base.LANE_ROOT / _BASE_PATH))
    deadline = time.monotonic() + timeout_seconds
    proc = subprocess.Popen(command, cwd=base.LANE_ROOT, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    output, offset = bytearray(), 0
    try:
        assert proc.stdin is not None and proc.stdout is not None
        os.set_blocking(proc.stdin.fileno(), False)
        os.set_blocking(proc.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdin, selectors.EVENT_WRITE)
            selector.register(proc.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _refuse("source-view worker exceeded its timeout")
                for key, _ in selector.select(min(remaining, 1.0)):
                    if key.fileobj is proc.stdin:
                        try:
                            offset += os.write(proc.stdin.fileno(), raw[offset:offset + 65536])
                        except BrokenPipeError:
                            selector.unregister(proc.stdin)
                            proc.stdin.close()
                            continue
                        if offset == len(raw):
                            selector.unregister(proc.stdin)
                            proc.stdin.close()
                    else:
                        chunk = os.read(proc.stdout.fileno(), 65536)
                        if not chunk:
                            selector.unregister(proc.stdout)
                            proc.stdout.close()
                        else:
                            if len(output) + len(chunk) > base._MAX_OUTPUT_BYTES:
                                _refuse("source-view worker exceeded its output cap")
                            output.extend(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _refuse("source-view worker exceeded its timeout")
        return subprocess.CompletedProcess(command, proc.wait(timeout=remaining), bytes(output))
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        if proc.stdout is not None and not proc.stdout.closed:
            proc.stdout.close()


def _validate_context(snapshot, expected_head):
    base = _base()
    if (type(expected_head) is not str or base._COMMIT.fullmatch(expected_head) is None
            or snapshot[0] != expected_head):
        _refuse("lane HEAD differs from the explicitly reviewed snapshot")
    allowed = {_WORKER_PATH, "tests/test_insider_buying_sec_recovery_v4_source_view.py",
               "tests/test_insider_buying_sec_recovery_v4_historical_replay.py",
               "docs/Strategy Description/INSIDER_BUYING_IMPLEMENTATION_RECORD.md"}
    for line in snapshot[1].splitlines():
        if len(line) < 4 or "R" in line[:2] or "C" in line[:2]:
            _refuse("lane status contains an unexpected change")
        path = line[3:]
        if path.startswith('"'):
            path = json.loads(path)
        if path not in allowed:
            _refuse("lane contains unrelated uncommitted changes")


def run_observed_historical_source_view_replay(*, expected_head, timeout_seconds=600):
    """Fixed-root offline replay; no caller roots, output directory or transport."""
    base = _base()
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600:
        _refuse("source-view worker timeout differs")
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.is_file() or not os.access(sandbox, os.X_OK):
        _refuse("required OS worker sandbox is unavailable")
    try:
        before = base._repository_snapshot()
        _validate_context(before, expected_head)
        blobs = base._validate_historical_blobs(tuple((p, base._git("cat-file", "blob",
            f"{base.HISTORICAL_COMMIT}:{p}")) for p, _ in base.HISTORICAL_FILES))
        sources = base._source_snapshot()
        current = dict(sources)
        if base._sha(base._git("cat-file", "blob", f"{base.HISTORICAL_COMMIT}:{base.EXECUTOR_PATH}")) != base.EXECUTOR_SHA256:
            _refuse("historical executor capture blob differs")
        diagnostic_blob = base._git("cat-file", "blob", f"{base.DIAGNOSTIC_CAPTURE_COMMIT}:{base.DIAGNOSTIC_CAPTURE_PATH}")
        if current.get(base.DIAGNOSTIC_CAPTURE_PATH) != diagnostic_blob:
            _refuse("diagnostic capture code differs")
        worker, base_source = current.get(_WORKER_PATH), current.get(_BASE_PATH)
        if (worker is None or base_source is None or Path(__file__).resolve() != base.LANE_ROOT / _WORKER_PATH
                or Path(base.__file__).resolve() != base.LANE_ROOT / _BASE_PATH):
            _refuse("source-view worker or base is outside the designated lane")
        bundle = {"repository_head": before[0], "historical_sources": base._encode_sources(blobs),
            "current_sources": base._encode_sources(sources), "worker_source_b64": base64.b64encode(worker).decode("ascii"),
            "worker_source_sha256": base._sha(worker), "base_source_sha256": base._sha(base_source)}
        raw = base._canonical(bundle)
        if len(raw) > base._MAX_INPUT_BYTES:
            _refuse("source-view worker bundle exceeds its cap")
        base._assert_sources_unchanged(sources)
        if base._repository_snapshot() != before:
            _refuse("lane context changed before source-view replay")
        result = _run_isolated_worker(raw, timeout_seconds)
        base._assert_sources_unchanged(sources)
        if base._repository_snapshot() != before:
            _refuse("lane context changed during source-view replay")
        if result.returncode != 0 or not 0 < len(result.stdout) <= base._MAX_OUTPUT_BYTES:
            _refuse("isolated source-view worker refused, timed out or overflowed")
        payload = _validate_receipt(json.loads(result.stdout))
        if (payload["repository_head"] != before[0] or payload["worker_source_sha256"] != base._sha(worker)
                or payload["base_source_sha256"] != base._sha(base_source)
                or payload["current_source_inventory_sha256"] != base._digest([
                    {"path": p, "sha256": base._sha(r)} for p, r in sources])):
            _refuse("source-view worker context or source inventory differs")
        historical = dict(blobs)
        for row in payload["executed_modules"]:
            expected = historical.get(row["path"]) if row["source_kind"] == "historical_git_blob" else current.get(row["path"])
            if expected is None or base._sha(expected) != row["sha256"]:
                _refuse("source-view executed source differs from captured bytes")
        return _seal(payload)
    except HistoricalSourceViewError:
        raise
    except (base.HistoricalReplayError, OSError, UnicodeError, ValueError, KeyError, TypeError,
            RecursionError, subprocess.SubprocessError):
        raise HistoricalSourceViewError("REFUSED: bounded historical source-view replay failed") from None


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Offline historical source-view custody replay")
        parser.add_argument("--expected-head", required=True)
        args = parser.parse_args()
        receipt = run_observed_historical_source_view_replay(expected_head=args.expected_head)
        print(_base()._canonical({"receipt_sha256": receipt.sha256, "receipt": receipt.to_payload()}).decode("ascii"))
    except HistoricalSourceViewError:
        sys.stderr.write("REFUSED: bounded historical source-view replay failed\n")
        raise SystemExit(1) from None
