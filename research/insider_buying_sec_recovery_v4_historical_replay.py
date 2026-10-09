"""Isolated, source-only historical v3 custody replay; never acquisition.

The four captured validator modules execute exact Git blob bytes. Later
read-only verifiers and their dependencies execute separately inventoried
current source bytes. This is not an exact historical Python environment and
does not remove the old validator's current-file binding or authorize thawing
the four frozen files. The worker cannot publish artifacts or launch requests.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
import hashlib
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time


VERSION = "INSETF-IB1B-HISTORICAL-CUSTODY-REPLAY-v4"
LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
HISTORICAL_COMMIT = "aa0d635d00b64825bf8003289e0a60279bd52e73"
HISTORICAL_FILES = (
    ("research/insider_buying_sec_all_form4_parent_recovery_union.py", "67a72b5cfd3be3ae9b1fc938a241da74df0a57979ca1a114d13122b675848a48"),
    ("research/insider_buying_sec_all_form4_parent_campaign.py", "33f2a54944b8f5674ae92c77c4a17ff03e6455ffcf7c0d07d377945e8dbad551"),
    ("research/insider_buying/sec_complete_submission.py", "d15ed661d32f13fd1f3644106bd6a21c428605b1a001d58ea5fc6a3319af63a6"),
    ("research/insider_buying/sec_raw_parent_projection.py", "d5631b6a2684e30061be1753e00e7f50f56690643537a9d67e34e228dd20578b"),
)
HISTORICAL_VALIDATOR_SHA256 = "e47d595ee62fe30c1b9823d9db4d2219160af5e182aa16d8a9ed4b658eb7f0ee"
EXECUTOR_PATH = "research/insider_buying_sec_all_form4_parent_recovery_executor.py"
EXECUTOR_SHA256 = "6305c604e78df1eed14eeb8d269cbcc07a881405e16611abf8f46e5a07be986d"
DIAGNOSTIC_CAPTURE_COMMIT = "b5a140816eeaa05c6178fa544d00fa7028e4a9d9"
DIAGNOSTIC_CAPTURE_PATH = "research/insider_buying_sec_all_form4_parent_ambiguous_diagnostic.py"
DIAGNOSTIC_REPORT_SHA256 = "206e6db9677fb169455f62357ce966384926080b6eba582094e9536e88d705b7"
DIAGNOSTIC_BODY_SHA256 = "61c9b1bee6d9b365cb7f5363b30969382def65f5e652f2f63722348db465ce1c"
_BASE = LANE_ROOT.parent
_PILOT = _BASE / "insider_buying_ib1b_pilot_2022q4_2023q1_bd2c65c"
SOURCE_ROOTS = (
    _PILOT / "ib1a/sec-insider-bulk-2022q4-e34b743e2bee3381",
    _PILOT / "ib1b/sec-insider-parsed-2022q4-277084d85445a25d",
    _PILOT / "ib1a/sec-insider-bulk-2023q1-c8c35e859ab09342",
    _PILOT / "ib1b/sec-insider-parsed-2023q1-5afb03260f879c6d",
    _BASE / "insider_buying_sec_complete_16_9ab2ed0",
    _BASE / "insider-source-20260929.hP4utF/selected-parents-v2",
    _BASE / "insider-source-allparents-20260929.3Nut2i/all-form4-parents",
    _BASE / "insider-source-allparents-20260929.3Nut2i/refused-parent-diagnostic-v1",
)
V3_ROOT = SOURCE_ROOTS[6].parent / "all-form4-parents-recovery-v3"
DIAGNOSTIC_ROOT = V3_ROOT.parent / "all-form4-parents-v3-ambiguous-diagnostic-v1"
_WORKER_PATH = "research/insider_buying_sec_recovery_v4_historical_replay.py"
_MAX_BLOB_BYTES = 2 * 1024 * 1024
_MAX_INPUT_BYTES = 32 * 1024 * 1024
_MAX_OUTPUT_BYTES = 64 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_TOKEN = object()
_AUTHORITY = {
    "source_authenticated": False, "official_acceptance_verified": False,
    "publication_time_verified": False, "point_in_time_data": False,
    "rights_verified": False, "canonical_evidence": False,
    "complete_corpus": False, "qc_authorized": False,
    "backtest_authorized": False, "execution_authorized": False,
    "dispatch_enabled": False, "output_written": False,
    "sec_dispatches": 0, "outcome_looks": 0, "qc_jobs": 0, "backtests": 0,
}
_COUNTS = {
    "prior_completed": 9539, "offline_corrected_diagnostic": 1,
    "remaining_selected_reuse": 8139, "v3_completed": 1846,
    "accepted_ambiguous_diagnostic": 1, "originally_unattempted": 79868,
}


class HistoricalReplayError(ValueError):
    """The offline historical replay could not prove its bounded contract."""


def _refuse(reason: str) -> None:
    raise HistoricalReplayError("REFUSED: " + reason)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(payload: object) -> str:
    return _sha(_canonical(payload))


def _is_sha(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _validate_historical_blobs(blobs: object) -> tuple[tuple[str, bytes], ...]:
    if type(blobs) is not tuple or len(blobs) != len(HISTORICAL_FILES):
        _refuse("historical blob inventory differs")
    for item, (path, digest) in zip(blobs, HISTORICAL_FILES, strict=True):
        if (type(item) is not tuple or len(item) != 2 or item[0] != path
                or type(item[0]) is not str or type(item[1]) is not bytes
                or not 0 < len(item[1]) <= _MAX_BLOB_BYTES
                or _sha(item[1]) != digest):
            _refuse("historical blob identity differs")
    return blobs


def _audit_event(event: str, args: tuple[object, ...]) -> None:
    """Defence in depth, not a replacement for the inherited OS sandbox."""
    if (event.startswith("socket.") or event.startswith("subprocess.")
            or event in {"os.system", "os.fork", "os.forkpty", "os.exec",
                         "os.posix_spawn", "os.spawn", "ctypes.dlopen",
                         "os.remove", "os.rmdir", "os.mkdir", "os.rename",
                         "os.link", "os.symlink", "os.chmod", "os.chown",
                         "os.truncate", "os.utime", "shutil.copyfile",
                         "shutil.copymode", "shutil.copystat"}):
        _refuse("worker attempted forbidden network, process or mutation operation")
    if event == "open":
        if len(args) < 3:
            _refuse("worker file-open audit is malformed")
        mode, flags = args[1], args[2]
        writable = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        if ((isinstance(mode, str) and any(c in mode for c in "wax+"))
                or type(flags) is int and flags & writable):
            _refuse("worker attempted a writable file open")


def _worker_policy(python: str | None = None) -> str:
    executable = Path(python or sys.executable).resolve()
    targets = [executable]
    # Section 130 (Claude review): a macOS framework interpreter's bin stub
    # re-executes Resources/Python.app/Contents/MacOS/Python in place. With a
    # literal allow for the stub alone that exec is refused and the worker
    # never starts, so the replay could not run on the lane's venv interpreter.
    if len(executable.parents) > 1:
        relaunch = executable.parents[1] / "Resources/Python.app/Contents/MacOS/Python"
        if relaunch.is_file():
            targets.append(relaunch.resolve())
    for target in targets:
        if not target.is_absolute() or '"' in str(target) or "\\" in str(target):
            _refuse("worker interpreter path is unsafe")
    return ("(version 1)(allow default)(deny network*)(deny file-write*)"
            "(deny process-fork)(deny process-exec)"
            + "".join(f'(allow process-exec (literal "{target}"))' for target in targets))


def _module_name(path: str) -> tuple[str, bool]:
    if not path.endswith(".py") or ".." in Path(path).parts or Path(path).is_absolute():
        _refuse("source-only module path differs")
    package = path.endswith("/__init__.py")
    name = path[:-12] if package else path[:-3]
    name = name.replace("/", ".")
    if not re.fullmatch(r"(?:data|research|ml)(?:\.[A-Za-z_][A-Za-z_0-9]*)*", name):
        _refuse("source-only module name is outside the lane inventory")
    return name, package


class _HistoricalBlobFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Never delegates a lane import to current .py/.pyc fallback."""

    def __init__(self, blobs: tuple[tuple[str, bytes], ...],
                 current_sources: tuple[tuple[str, bytes], ...] = ()) -> None:
        _validate_historical_blobs(blobs)
        historical = dict(blobs)
        self.sources: dict[str, tuple[str, bytes, bool, str]] = {}
        for path, raw in (*current_sources, *blobs):
            name, package = _module_name(path)
            if type(raw) is not bytes or len(raw) > _MAX_BLOB_BYTES or (not raw and not package):
                _refuse("source-only module byte image differs")
            kind = "historical_git_blob" if path in historical else "current_source_snapshot"
            self.sources[name] = (path, historical.get(path, raw), package, kind)
        self.executed: list[dict[str, str]] = []
        self.called: set[str] = set()
        self._historical_filenames = {str(LANE_ROOT / path): path for path, _ in HISTORICAL_FILES}

    def find_spec(self, fullname: str, path: object = None,
                  target: object = None):
        if fullname not in self.sources:
            if fullname.split(".")[0] in {"data", "research", "ml", "assistant", "backtest", "execution", "risk", "scripts", "signals", "strategies", "config", "baskets", "market_analytics"}:
                _refuse("lane import is outside the source-only inventory")
            return None
        relative, _, package, kind = self.sources[fullname]
        origin = f"git:{HISTORICAL_COMMIT}:{relative}" if kind == "historical_git_blob" else f"snapshot:{relative}"
        return importlib.util.spec_from_loader(fullname, self, origin=origin,
                                               is_package=package)

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        relative, raw, package, kind = self.sources[module.__name__]
        module.__file__ = str(LANE_ROOT / relative)
        module.__cached__ = None
        if package:
            module.__path__ = [str((LANE_ROOT / relative).parent)]
        exec(compile(raw, module.__file__, "exec", dont_inherit=True), module.__dict__)
        self.executed.append({"path": relative, "sha256": _sha(raw), "source_kind": kind})

    def profile(self, frame, event: str, arg: object) -> None:
        if event == "call":
            path = self._historical_filenames.get(frame.f_code.co_filename)
            if path is not None and frame.f_code.co_name != "<module>":
                self.called.add(path)
                if len(self.called) == len(HISTORICAL_FILES):
                    sys.setprofile(None)


def _git(*args: str) -> bytes:
    try:
        result = subprocess.run(("/usr/bin/git", *args), cwd=LANE_ROOT,
                                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        _refuse("trusted lane Git check failed")
    if result.returncode != 0 or len(result.stdout) > _MAX_BLOB_BYTES:
        _refuse("trusted lane Git result is unavailable or oversized")
    return result.stdout


def _repository_snapshot() -> tuple[str, str]:
    root = _git("rev-parse", "--show-toplevel").decode("utf-8").strip()
    branch = _git("branch", "--show-current").decode("utf-8").strip()
    head = _git("rev-parse", "HEAD").decode("ascii").strip()
    status = _git("status", "--porcelain=v1", "--untracked-files=all").decode("utf-8")
    if (root != str(LANE_ROOT) or branch != LANE_BRANCH
            or _COMMIT.fullmatch(head) is None):
        _refuse("designated lane root, branch or HEAD differs")
    return head, status


def _validate_context(snapshot: tuple[str, str], expected_head: str) -> None:
    if (type(expected_head) is not str or _COMMIT.fullmatch(expected_head) is None
            or snapshot[0] != expected_head):
        _refuse("lane HEAD differs from the explicitly reviewed snapshot")
    allowed = {_WORKER_PATH, "tests/test_insider_buying_sec_recovery_v4_historical_replay.py",
               "docs/Strategy Description/INSIDER_BUYING_IMPLEMENTATION_RECORD.md"}
    for line in snapshot[1].splitlines():
        if len(line) < 4 or "R" in line[:2] or "C" in line[:2]:
            _refuse("lane status contains an unexpected change")
        path = line[3:]
        if path.startswith('"'):
            path = json.loads(path)
        if path not in allowed:
            _refuse("lane contains unrelated uncommitted changes")


def _source_snapshot() -> tuple[tuple[str, bytes], ...]:
    paths = set((LANE_ROOT / "data").glob("*.py"))
    paths.update((LANE_ROOT / "research").glob("insider_buying*.py"))
    paths.update((LANE_ROOT / "research/insider_buying").glob("*.py"))
    paths.update((LANE_ROOT / "ml" / name) for name in ("__init__.py", "immutable_io.py"))
    init = LANE_ROOT / "research/__init__.py"
    if init.exists():
        paths.add(init)
    result = []
    for path in sorted(paths):
        if path.is_symlink() or path.resolve() != path:
            _refuse("current source inventory contains a redirected path")
        raw = path.read_bytes()
        if len(raw) > _MAX_BLOB_BYTES or (not raw and path.name != "__init__.py"):
            _refuse("current source inventory contains an empty or oversized module")
        result.append((str(path.relative_to(LANE_ROOT)), raw))
    if len(result) > 512:
        _refuse("current source inventory exceeds its cap")
    return tuple(result)


def _encode_sources(sources: tuple[tuple[str, bytes], ...]) -> list[dict[str, str]]:
    return [{"path": path, "sha256": _sha(raw),
             "source_b64": base64.b64encode(raw).decode("ascii")}
            for path, raw in sources]


def _decode_sources(rows: object) -> tuple[tuple[str, bytes], ...]:
    if type(rows) is not list or not 1 <= len(rows) <= 512:
        _refuse("worker source inventory differs")
    result = []
    for row in rows:
        if (type(row) is not dict or set(row) != {"path", "sha256", "source_b64"}
                or type(row["path"]) is not str or not _is_sha(row["sha256"])
                or type(row["source_b64"]) is not str):
            _refuse("worker source row differs")
        raw = base64.b64decode(row["source_b64"], validate=True)
        if (len(raw) > _MAX_BLOB_BYTES or (not raw and not row["path"].endswith("/__init__.py"))
                or _sha(raw) != row["sha256"]):
            _refuse("worker source byte image differs")
        _module_name(row["path"])
        result.append((row["path"], raw))
    if len({path for path, _ in result}) != len(result):
        _refuse("worker source inventory repeats a path")
    return tuple(result)


def _assert_sources_unchanged(sources: tuple[tuple[str, bytes], ...]) -> None:
    for relative, raw in sources:
        path = LANE_ROOT / relative
        if path.is_symlink() or path.resolve() != path or path.read_bytes() != raw:
            _refuse("captured current code changed during replay")


def _validate_aggregate(payload: object) -> dict[str, object]:
    hashes = ("worker_source_sha256", "current_source_inventory_sha256",
              "source_union_sha256", "partial_descriptor_sha256",
              "diagnostic_descriptor_sha256", "v4_plan_sha256",
              "partition_sha256", "proposed_unattempted_inventory_sha256")
    keys = {"kind", "scope", "repository_head", "historical_commit",
            "historical_validator_sha256", "worker_bootstrap_sha256", "historical_files", "executed_modules",
            "historical_function_paths", "counts", "total_parents", "source_bound_count",
            "v3_attempt_count", "v3_completed_count", "stopped_v3_disposition",
            "diagnostic_report_sha256", "diagnostic_body_sha256", "diagnostic_body_size_bytes",
            "current_byte_binding_required", "historical_environment_recreated",
            "frozen_files_may_be_thawed", "isolation", "authority", *hashes}
    if (type(payload) is not dict or set(payload) != keys
            or payload["kind"] != VERSION or payload["scope"] != "observed_offline_custody_replay"
            or type(payload["repository_head"]) is not str or _COMMIT.fullmatch(payload["repository_head"]) is None
            or payload["historical_commit"] != HISTORICAL_COMMIT
            or payload["historical_validator_sha256"] != HISTORICAL_VALIDATOR_SHA256
            or payload["worker_bootstrap_sha256"] != _sha(_BOOTSTRAP.encode("utf-8"))
            or payload["historical_files"] != [{"path": p, "sha256": s} for p, s in HISTORICAL_FILES]
            or payload["historical_function_paths"] != [p for p, _ in HISTORICAL_FILES]
            or type(payload["counts"]) is not dict or set(payload["counts"]) != set(_COUNTS)
            or any(type(payload["counts"][k]) is not int or payload["counts"][k] != v
                   for k, v in _COUNTS.items())
            or any(type(payload[k]) is not int or payload[k] != value for k, value in (
                ("total_parents", 99394), ("source_bound_count", 19526),
                ("v3_attempt_count", 1847), ("v3_completed_count", 1846),
                ("diagnostic_body_size_bytes", 7373)))
            or payload["stopped_v3_disposition"] != "preserved_unresolved_not_resumable"
            or payload["diagnostic_report_sha256"] != DIAGNOSTIC_REPORT_SHA256
            or payload["diagnostic_body_sha256"] != DIAGNOSTIC_BODY_SHA256
            or payload["current_byte_binding_required"] is not True
            or payload["historical_environment_recreated"] is not False
            or payload["frozen_files_may_be_thawed"] is not False
            or type(payload["isolation"]) is not dict
            or any(value is not True for value in payload["isolation"].values())
            or payload["isolation"] != {"os_network_denied": True, "os_file_writes_denied": True,
                "os_process_fork_denied": True, "audit_additional_processes_denied": True,
                "source_only_lane_imports": True}
            or type(payload["authority"]) is not dict or payload["authority"] != _AUTHORITY
            or any(type(payload["authority"][k]) is not type(v) for k, v in _AUTHORITY.items())
            or any(not _is_sha(payload[k]) for k in hashes)):
        _refuse("worker aggregate schema, anchors or authority differs")
    trace = payload["executed_modules"]
    if type(trace) is not list or not 4 <= len(trace) <= 512:
        _refuse("worker execution inventory differs")
    seen = set()
    historical = {}
    for row in trace:
        if (type(row) is not dict or set(row) != {"path", "sha256", "source_kind"}
                or type(row["path"]) is not str or row["path"] in seen
                or not _is_sha(row["sha256"]) or row["source_kind"] not in {
                    "historical_git_blob", "current_source_snapshot"}):
            _refuse("worker executed-source row differs")
        _module_name(row["path"])
        seen.add(row["path"])
        if row["source_kind"] == "historical_git_blob":
            historical[row["path"]] = row["sha256"]
    if historical != dict(HISTORICAL_FILES):
        _refuse("worker did not execute the exact four historical validators")
    wrapper = next((row for row in trace if row["path"] == _WORKER_PATH), None)
    if (wrapper is None or wrapper["source_kind"] != "current_source_snapshot"
            or wrapper["sha256"] != payload["worker_source_sha256"]):
        _refuse("worker wrapper execution is not bound to its source snapshot")
    return payload


@dataclass(frozen=True, slots=True)
class ReplayReceipt:
    _raw: bytes = field(repr=False)
    _sha256: str
    _token: object = field(repr=False, compare=False)
    _factory_raw: bytes | None = field(default=None, init=False, repr=False, compare=False)

    def to_payload(self) -> dict[str, object]:
        if (type(self) is not ReplayReceipt or self._token is not _TOKEN
                or type(self._raw) is not bytes or self._raw != self._factory_raw
                or _sha(self._raw) != self._sha256):
            _refuse("replay receipt was not built here or was altered")
        return _validate_aggregate(json.loads(self._raw))

    @property
    def sha256(self) -> str:
        self.to_payload()
        return self._sha256


def _seal(payload: dict[str, object]) -> ReplayReceipt:
    _validate_aggregate(payload)
    raw = _canonical(payload)
    result = ReplayReceipt(raw, _sha(raw), _TOKEN)
    object.__setattr__(result, "_factory_raw", raw)
    return result


def _worker_main(bundle: dict[str, object]) -> None:
    """Private stdin worker; every lane import uses the captured source loader."""
    try:
        sys.dont_write_bytecode = True
        sys.addaudithook(_audit_event)
        blobs = _validate_historical_blobs(_decode_sources(bundle["historical_sources"]))
        sources = _decode_sources(bundle["current_sources"])
        if (dict(sources).get(_WORKER_PATH) is None
                or _sha(dict(sources)[_WORKER_PATH]) != bundle["worker_source_sha256"]):
            _refuse("worker wrapper differs from its captured source inventory")
        _assert_sources_unchanged(sources)
        if any(name.split(".")[0] in {"data", "research", "ml"} for name in sys.modules):
            _refuse("worker inherited a preloaded lane module")
        finder = _HistoricalBlobFinder(blobs, sources)
        finder.executed.append({"path": _WORKER_PATH, "sha256": bundle["worker_source_sha256"],
                                "source_kind": "current_source_snapshot"})
        sys.meta_path.insert(0, finder)
        sys.setprofile(finder.profile)
        import research.insider_buying_sec_all_form4_parent_recovery_union as union
        import research.insider_buying_sec_all_form4_parent_campaign as campaign
        import research.insider_buying_sec_all_form4_parent_recovery_preflight as prior
        import research.insider_buying_sec_all_form4_parent_recovery_verifier as completed
        import research.insider_buying_sec_all_form4_parent_recovery_partial_verifier as partial
        import research.insider_buying_sec_all_form4_parent_ambiguous_diagnostic_verifier as diagnostic
        import research.insider_buying.sec_recovery_v4_plan as v4
        from data.hashing import hash_payload

        def source_replay():
            return union.preflight_observed_all_form4_parent_recovery_union(
                *SOURCE_ROOTS, diagnostic_capture_git_commit=union.OBSERVED_DIAGNOSTIC_CAPTURE_COMMIT,
                expected_diagnostic_report_sha256=union.OBSERVED_DIAGNOSTIC_REPORT_SHA256)

        source = source_replay()
        plan = campaign._build_real_plan(*SOURCE_ROOTS[:6])
        expectation = prior.PartialCampaignExpectation(
            capture_git_commit=prior.PRIOR_CAPTURE_GIT_COMMIT,
            shard_report_sha256s=prior.PRIOR_SHARD_REPORT_SHA256S,
            completed_counts=(8192, 1347), reused_counts=(972, 226),
            total_attempt_count=8342)

        def partial_replay():
            result = partial._verify_partial(
                plan, source, SOURCE_ROOTS[6], SOURCE_ROOTS[7], SOURCE_ROOTS[5], V3_ROOT,
                prior_expectation=expectation, capture_git_commit=HISTORICAL_COMMIT,
                capture_code_sha256=EXECUTOR_SHA256)
            partial._require_observed_anchors(result)
            if result.completed_new_count != 1846 or result.attempt_count != 1847:
                _refuse("stopped v3 count anchors differ")
            return result

        stopped = partial_replay()
        accepted = diagnostic.verify_accepted_ambiguity_diagnostic(
            stopped, DIAGNOSTIC_ROOT, capture_git_commit=DIAGNOSTIC_CAPTURE_COMMIT,
            expected_report_sha256=DIAGNOSTIC_REPORT_SHA256)
        classes, _ = completed._source_classes(plan, source)
        p = {key: getattr(stopped, key) for key in (*v4._PARTIAL_HASHES, *v4._PARTIAL_INTS)}
        p["root_plan_sha256"] = stopped.root_plan_sha256
        d = {key: getattr(accepted, key) for key in (
            *v4._DIAGNOSTIC_HASHES, "diagnostic_capture_git_commit", "pending_global_index", "body_size_bytes")}
        binding = v4.bind_v3_historical_validator(HISTORICAL_COMMIT, blobs)
        proposal = v4.build_recovery_v4_offline_plan(
            tuple(request.to_payload() for request in plan.requests), tuple(classes), p, d, binding)
        proposal_body = proposal.to_payload()
        if source_replay() != source or partial_replay() != stopped:
            _refuse("retained source or stopped-v3 state changed during replay")
        again = diagnostic.verify_accepted_ambiguity_diagnostic(
            stopped, DIAGNOSTIC_ROOT, capture_git_commit=DIAGNOSTIC_CAPTURE_COMMIT,
            expected_report_sha256=DIAGNOSTIC_REPORT_SHA256)
        if again != accepted:
            _refuse("separate accepted diagnostic changed during replay")
        _assert_sources_unchanged(sources)
        sys.setprofile(None)
        if finder.called != {path for path, _ in HISTORICAL_FILES}:
            _refuse("historical validator function execution was not observed")
        payload = {
            "kind": VERSION, "scope": "observed_offline_custody_replay",
            "repository_head": bundle["repository_head"], "historical_commit": HISTORICAL_COMMIT,
            "historical_validator_sha256": HISTORICAL_VALIDATOR_SHA256,
            "worker_bootstrap_sha256": _sha(_BOOTSTRAP.encode("utf-8")),
            "worker_source_sha256": bundle["worker_source_sha256"],
            "current_source_inventory_sha256": _digest([
                {"path": path, "sha256": _sha(raw)} for path, raw in sources]),
            "historical_files": [{"path": path, "sha256": sha} for path, sha in HISTORICAL_FILES],
            "executed_modules": finder.executed,
            "historical_function_paths": [path for path, _ in HISTORICAL_FILES],
            "source_union_sha256": hash_payload(source), "partial_descriptor_sha256": hash_payload(p),
            "diagnostic_descriptor_sha256": hash_payload(d), "v4_plan_sha256": proposal.sha256,
            "partition_sha256": proposal_body["partition_sha256"],
            "proposed_unattempted_inventory_sha256": proposal_body["proposed_unattempted_inventory_sha256"],
            "counts": proposal_body["class_counts"], "total_parents": 99394,
            "source_bound_count": 19526, "v3_attempt_count": stopped.attempt_count,
            "v3_completed_count": stopped.completed_new_count,
            "stopped_v3_disposition": proposal_body["stopped_v3_disposition"],
            "diagnostic_report_sha256": accepted.report_sha256,
            "diagnostic_body_sha256": accepted.body_sha256,
            "diagnostic_body_size_bytes": accepted.body_size_bytes,
            "current_byte_binding_required": True, "historical_environment_recreated": False,
            "frozen_files_may_be_thawed": False,
            "isolation": {"os_network_denied": True, "os_file_writes_denied": True,
                "os_process_fork_denied": True, "audit_additional_processes_denied": True,
                "source_only_lane_imports": True}, "authority": dict(_AUTHORITY),
        }
        _validate_aggregate(payload)
        raw = _canonical(payload)
        if len(raw) > _MAX_OUTPUT_BYTES:
            _refuse("worker aggregate exceeds its output cap")
        sys.stdout.buffer.write(raw + b"\n")
        sys.stdout.buffer.flush()
    except BaseException:
        # Do not expose raw parent content, paths from an exception, or headers.
        sys.stderr.write("REFUSED: isolated historical custody replay failed\n")
        raise SystemExit(1) from None


_BOOTSTRAP = """import base64, hashlib, json, sys, types
raw = sys.stdin.buffer.read(33554433)
if len(raw) > 33554432:
    raise SystemExit(2)
b = json.loads(raw)
s = base64.b64decode(b['worker_source_b64'], validate=True)
if hashlib.sha256(s).hexdigest() != b['worker_source_sha256']:
    raise SystemExit(2)
m = types.ModuleType('_insider_historical_worker')
m.__file__ = sys.argv[1]
sys.modules[m.__name__] = m
exec(compile(s, m.__file__, 'exec', dont_inherit=True), m.__dict__)
m._worker_main(b)
"""


def _run_isolated_worker(raw: bytes, timeout_seconds: int) -> subprocess.CompletedProcess:
    """Bound stdin, stdout and wall-clock time without a temporary output file."""
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_INPUT_BYTES:
        _refuse("worker input exceeds its bounded contract")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600:
        _refuse("worker timeout is outside the bounded contract")
    command = ("/usr/bin/sandbox-exec", "-p", _worker_policy(),
               str(Path(sys.executable).resolve()), "-I", "-S", "-B", "-c", _BOOTSTRAP,
               str(LANE_ROOT / _WORKER_PATH))
    deadline = time.monotonic() + timeout_seconds
    proc = subprocess.Popen(command, cwd=LANE_ROOT,
                            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    output = bytearray()
    offset = 0
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
                    _refuse("isolated worker exceeded its bounded timeout")
                for key, event in selector.select(min(remaining, 1.0)):
                    if key.fileobj is proc.stdin:
                        try:
                            written = os.write(proc.stdin.fileno(), raw[offset:offset + 65536])
                        except BrokenPipeError:
                            selector.unregister(proc.stdin)
                            proc.stdin.close()
                            continue
                        offset += written
                        if offset == len(raw):
                            selector.unregister(proc.stdin)
                            proc.stdin.close()
                    else:
                        chunk = os.read(proc.stdout.fileno(), 65536)
                        if not chunk:
                            selector.unregister(proc.stdout)
                            proc.stdout.close()
                        else:
                            if len(output) + len(chunk) > _MAX_OUTPUT_BYTES:
                                _refuse("isolated worker exceeded its bounded output cap")
                            output.extend(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _refuse("isolated worker exceeded its bounded timeout")
        code = proc.wait(timeout=remaining)
        return subprocess.CompletedProcess(command, code, bytes(output))
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        if proc.stdout is not None and not proc.stdout.closed:
            proc.stdout.close()


def run_observed_historical_v3_custody_replay(*, expected_head: str,
                                            timeout_seconds: int = 600) -> ReplayReceipt:
    """Replay retained inputs in a denied worker; no artifacts are created."""
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 600:
        _refuse("worker timeout is outside the bounded contract")
    sandbox = Path("/usr/bin/sandbox-exec")
    if not sandbox.is_file() or not os.access(sandbox, os.X_OK):
        _refuse("required OS worker sandbox is unavailable")
    try:
        before = _repository_snapshot()
        _validate_context(before, expected_head)
        blobs = _validate_historical_blobs(tuple(
            (path, _git("cat-file", "blob", f"{HISTORICAL_COMMIT}:{path}")) for path, _ in HISTORICAL_FILES))
        sources = _source_snapshot()
        current = dict(sources)
        if any(current.get(path) != raw for path, raw in blobs):
            _refuse("frozen current validator differs from the captured historical bytes")
        if _sha(_git("cat-file", "blob", f"{HISTORICAL_COMMIT}:{EXECUTOR_PATH}")) != EXECUTOR_SHA256:
            _refuse("historical executor capture blob differs")
        diagnostic_blob = _git("cat-file", "blob", f"{DIAGNOSTIC_CAPTURE_COMMIT}:{DIAGNOSTIC_CAPTURE_PATH}")
        if current.get(DIAGNOSTIC_CAPTURE_PATH) != diagnostic_blob:
            _refuse("diagnostic capture code differs from the reviewed committed blob")
        worker_source = current.get(_WORKER_PATH)
        if worker_source is None or Path(__file__).resolve() != LANE_ROOT / _WORKER_PATH:
            _refuse("historical worker wrapper is outside the designated lane")
        bundle = {
            "repository_head": before[0], "historical_sources": _encode_sources(blobs),
            "current_sources": _encode_sources(sources),
            "worker_source_b64": base64.b64encode(worker_source).decode("ascii"),
            "worker_source_sha256": _sha(worker_source),
        }
        raw = _canonical(bundle)
        if len(raw) > _MAX_INPUT_BYTES:
            _refuse("worker source bundle exceeds its cap")
        _assert_sources_unchanged(sources)
        if _repository_snapshot() != before:
            _refuse("lane context changed before isolated replay")
        result = _run_isolated_worker(raw, timeout_seconds)
        _assert_sources_unchanged(sources)
        if _repository_snapshot() != before:
            _refuse("lane context changed during isolated replay")
        if result.returncode != 0 or not 0 < len(result.stdout) <= _MAX_OUTPUT_BYTES:
            _refuse("isolated worker refused, timed out or exceeded its output cap")
        payload = _validate_aggregate(json.loads(result.stdout))
        if payload["repository_head"] != before[0]:
            _refuse("worker reported a different lane HEAD")
        if (payload["worker_source_sha256"] != _sha(worker_source)
                or payload["current_source_inventory_sha256"] != _digest([
                    {"path": path, "sha256": _sha(raw)} for path, raw in sources])):
            _refuse("worker current-source manifest differs from captured bytes")
        for row in payload["executed_modules"]:
            expected = dict(blobs).get(row["path"]) if row["source_kind"] == "historical_git_blob" else current.get(row["path"])
            if expected is None or _sha(expected) != row["sha256"]:
                _refuse("worker executed-source trace differs from captured bytes")
        return _seal(payload)
    except HistoricalReplayError:
        raise
    except (OSError, UnicodeError, ValueError, KeyError, subprocess.SubprocessError):
        raise HistoricalReplayError("REFUSED: bounded isolated custody replay failed") from None


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Offline retained historical custody replay")
        parser.add_argument("--expected-head", required=True)
        args = parser.parse_args()
        receipt = run_observed_historical_v3_custody_replay(expected_head=args.expected_head)
        print(_canonical({"receipt_sha256": receipt.sha256, "receipt": receipt.to_payload()}).decode("ascii"))
    except HistoricalReplayError:
        sys.stderr.write("REFUSED: bounded isolated custody replay failed\n")
        raise SystemExit(1) from None
