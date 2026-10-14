"""Source-only, write-confined launcher for one offline affected quarter.

Only this stdlib-only entry runs in the parent. Repository modules execute
captured, committed Python source in a fresh process with no network, extra
processes, or writes outside a new private output leaf. Failure never deletes
that leaf: incomplete artifacts remain visibly incomplete for owner review.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import time


LANE_ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__insider_buying")
LANE_BRANCH = "codex/strategy-insider-buying"
_WORKER_PATH = "research/insider_buying_affected_quarter_isolation.py"
_CORE_PATH = "research/insider_buying_ib1c_v2_affected_quarter_runner.py"
_CORE_MODULE = "research.insider_buying_ib1c_v2_affected_quarter_runner"
_CONSUMER_PATH = "research/insider_buying_ib1c_v2_downstream_runner.py"
_CONSUMER_MODULE = "research.insider_buying_ib1c_v2_downstream_runner"
_PRODUCER_COMMIT = "b0efb31262d0eca6c972673ca36403fee20a34cb"
_PRODUCER_INVENTORY_SHA256 = "7b34fdfe67d408d4435ff610d9fc672bc181f7b257c6a487b64df546053fe3e0"
_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_MAX_INPUT_BYTES = 32 * 1024 * 1024
_MAX_OUTPUT_BYTES = 64 * 1024
_MAX_RUNTIME_SECONDS = 1800
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_BLOCKED_ROOTS = {
    "data", "research", "ml", "assistant", "backtest", "execution", "risk",
    "scripts", "signals", "strategies", "config", "baskets", "market_analytics",
}
_RESULT_FIELDS = {
    "worker_source_sha256", "worker_bootstrap_sha256",
    "executed_source_inventory_sha256", "executed_source_count",
    "os_network_denied", "os_output_write_confined", "os_process_fork_denied",
    "audit_additional_processes_denied", "source_only_lane_imports",
}
_AUTHORITY = {
    "source_authenticated": False, "index_membership_verified": False,
    "official_acceptance_verified": False, "publication_time_verified": False,
    "point_in_time_data": False, "rights_verified": False,
    "canonical_evidence": False, "signal_authorized": False,
    "direct_ib1c_ingest_authorized": False, "scale_promotion_authorized": False,
    "pilot_ingest_authorized": False, "qc_authorized": False,
    "backtest_authorized": False, "execution_authorized": False,
    "research_looks": 0, "qc_jobs": 0, "sec_dispatches": 0,
}
_RECEIPT_HASHES = {
    "manifest_sha256", "zip_sha256", "schema_profile_sha256",
    "header_receipt_sha256", "census_quarter_sha256", "source_inventory_sha256",
    "assessment_sha256", "assessment_envelope_sha256",
}
_RECEIPT_COUNTS = {
    "assessment_envelope_bytes", "submission_count", "corroborated_count",
    "quarantined_count", "accession_year_mismatch_count", "short_cik_count",
    "supplied_parent_count", "quarters_assessed",
}
_RECEIPT_KEYS = {
    "kind", "period", "parser_commit", "raw_snapshot_id", "parsed_snapshot_id",
    "whole_quarter_identity_sha256", *_AUTHORITY, *_RECEIPT_HASHES, *_RECEIPT_COUNTS,
}


class AffectedQuarterIsolationError(ValueError):
    """A code, path, process, or receipt boundary refused without raw data."""


def _refuse(reason: str) -> None:
    raise AffectedQuarterIsolationError("REFUSED: " + reason)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: object) -> str:
    return _sha(_canonical(value))


def _module_name(relative: str) -> tuple[str, bool]:
    if (type(relative) is not str or not relative.endswith(".py")
            or Path(relative).is_absolute() or ".." in Path(relative).parts):
        _refuse("captured module path is malformed")
    package = relative.endswith("/__init__.py")
    name = (relative[:-12] if package else relative[:-3]).replace("/", ".")
    if re.fullmatch(r"(?:data|research|ml)(?:\.[A-Za-z_][A-Za-z_0-9]*)*", name) is None:
        _refuse("captured module is outside the source-only lane inventory")
    return name, package


def _read_source(relative: str) -> bytes:
    _module_name(relative)
    path = LANE_ROOT / relative
    if path.is_symlink() or path.resolve() != path:
        _refuse("captured source path is redirected")
    try:
        named = path.lstat()
        if not stat.S_ISREG(named.st_mode) or named.st_size > _MAX_SOURCE_BYTES:
            _refuse("captured source is not a bounded regular file")
        leaf = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(leaf)
            chunks, remaining = [], _MAX_SOURCE_BYTES + 1
            while remaining:
                chunk = os.read(leaf, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(leaf)
        finally:
            os.close(leaf)
        named_after = path.lstat()
    except OSError as exc:
        raise AffectedQuarterIsolationError("REFUSED: captured source is unreadable") from exc
    versions = [(item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
                for item in (named, opened, after, named_after)]
    if (any(item != versions[0] for item in versions)
            or not stat.S_ISREG(named_after.st_mode)
            or len(raw) != after.st_size or len(raw) > _MAX_SOURCE_BYTES
            or (not raw and path.name != "__init__.py")):
        _refuse("captured source changed during its bounded read")
    return raw


def _source_snapshot() -> tuple[tuple[str, bytes], ...]:
    """The established current-source inventory, without a parent lane import."""
    paths = set((LANE_ROOT / "data").glob("*.py"))
    paths.update((LANE_ROOT / "research").glob("insider_buying*.py"))
    paths.update((LANE_ROOT / "research/insider_buying").glob("*.py"))
    paths.update(LANE_ROOT / "ml" / name for name in ("__init__.py", "immutable_io.py"))
    if (LANE_ROOT / "research/__init__.py").exists():
        paths.add(LANE_ROOT / "research/__init__.py")
    if not 1 <= len(paths) <= 512:
        _refuse("captured source inventory exceeds its cap")
    return tuple((str(path.relative_to(LANE_ROOT)),
                  _read_source(str(path.relative_to(LANE_ROOT))))
                 for path in sorted(paths))


def _inventory(sources: tuple[tuple[str, bytes], ...]) -> list[dict[str, str]]:
    return [{"path": relative, "sha256": _sha(raw)} for relative, raw in sources]


def _assert_sources_unchanged(sources: tuple[tuple[str, bytes], ...]) -> None:
    if _source_snapshot() != sources:
        _refuse("current source inventory changed during preparation")


def _git(*args: str) -> bytes:
    try:
        result = subprocess.run(("/usr/bin/git", "--no-optional-locks", "-c",
                                 "core.fsmonitor=false", *args), cwd=LANE_ROOT,
                                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AffectedQuarterIsolationError("REFUSED: exact lane Git check failed") from exc
    if result.returncode != 0 or len(result.stdout) > _MAX_SOURCE_BYTES:
        _refuse("exact lane Git result is unavailable or oversized")
    return result.stdout


def _repository_snapshot(expected_commit: str) -> tuple[str, str, str]:
    if type(expected_commit) is not str or _COMMIT.fullmatch(expected_commit) is None:
        _refuse("expected commit must be a full lowercase Git SHA")
    if Path(__file__).resolve() != LANE_ROOT / _WORKER_PATH:
        _refuse("launcher is outside the designated lane")
    root = _git("rev-parse", "--show-toplevel").decode("utf-8").strip()
    branch = _git("branch", "--show-current").decode("utf-8").strip()
    head = _git("rev-parse", "HEAD").decode("ascii").strip()
    if (root != str(LANE_ROOT) or branch != LANE_BRANCH or head != expected_commit
            or _git("status", "--porcelain=v1", "--untracked-files=all")):
        _refuse("exact clean designated lane HEAD is required")
    return root, branch, head


def _verify_committed_sources(sources: tuple[tuple[str, bytes], ...], commit: str) -> None:
    for relative, raw in sources:
        if _git("cat-file", "blob", f"{commit}:{relative}") != raw:
            _refuse("captured source differs from its exact committed blob")


def _plain_directory(value: Path, *, must_exist: bool) -> Path:
    if (type(value) is not type(LANE_ROOT) or not value.is_absolute()
            or ".." in value.parts or len(str(value)) > 4096
            or any(ord(char) < 32 for char in str(value))
            or any(char in str(value) for char in ('"', "\\"))):
        _refuse("input or output path is not an absolute plain directory")
    for path in (*reversed(value.parents), value):
        try:
            info = path.lstat()
        except FileNotFoundError:
            if path != value or must_exist:
                _refuse("input or output parent directory is unavailable")
            continue
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            _refuse("input or output path traverses a redirect or non-directory")
    return value


def _directory_identity(path: Path) -> tuple[int, int] | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    return info.st_dev, info.st_ino


def _overlap(first: Path, second: Path) -> bool:
    if first == second or first in second.parents or second in first.parents:
        return True
    a, b = _directory_identity(first), _directory_identity(second)
    return ((a is not None and a in {_directory_identity(p) for p in (second, *second.parents)})
            or (b is not None and b in {_directory_identity(p) for p in (first, *first.parents)}))


def _validate_paths(input_root: Path, output_root: Path) -> None:
    _plain_directory(input_root, must_exist=True)
    _plain_directory(output_root, must_exist=False)
    if _overlap(input_root, output_root) or _overlap(LANE_ROOT, output_root):
        _refuse("output overlaps the retained input or repository")
    if output_root.exists() or output_root.is_symlink():
        _refuse("output must be a fresh, non-existing private leaf")


def _check_output(output_root: Path, identity: tuple[int, int]) -> None:
    _plain_directory(output_root, must_exist=True)
    info = output_root.lstat()
    if (identity != (info.st_dev, info.st_ino) or stat.S_IMODE(info.st_mode) & 0o077):
        _refuse("private output directory identity or mode changed")


def _worker_policy(output_root: Path, python: str | None = None, *, readonly: bool = False) -> str:
    if type(readonly) is not bool:
        _refuse("read-only sandbox mode must be an exact boolean")
    executable = Path(python or sys.executable).resolve()
    targets = [executable]
    if len(executable.parents) > 1:
        relaunch = executable.parents[1] / "Resources/Python.app/Contents/MacOS/Python"
        if relaunch.is_file():
            targets.append(relaunch.resolve())
    for path in (*targets, output_root):
        if (not path.is_absolute() or any(char in str(path) for char in ('"', "\\"))
                or any(ord(char) < 32 for char in str(path))):
            _refuse("sandbox interpreter or output path is unsafe")
    return ("(version 1)(allow default)(deny network*)(deny file-write*)"
            + ("" if readonly else f'(allow file-write* (subpath "{output_root}"))')
            +
            "(deny process-fork)(deny process-exec)"
            + "".join(f'(allow process-exec (literal "{path}"))' for path in targets))


def _audit_event(event: str, args: tuple[object, ...]) -> None:
    if (event.startswith("socket.") or event.startswith("subprocess.")
            or event in {"os.system", "os.fork", "os.forkpty", "os.exec",
                         "os.posix_spawn", "os.spawn", "ctypes.dlopen", "ctypes.dlsym"}):
        _refuse("worker attempted a forbidden network or process operation")


class _SourceFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Serve captured lane sources only; missing lane modules never fall back."""

    def __init__(self, sources: tuple[tuple[str, bytes], ...]) -> None:
        self.sources = {}
        self.namespaces: set[str] = set()
        self.executed: list[dict[str, str]] = []
        for relative, raw in sources:
            name, package = _module_name(relative)
            if name in self.sources or type(raw) is not bytes:
                _refuse("source-only inventory repeats or changes a module")
            self.sources[name] = (relative, raw, package)
            parts = name.split(".")
            self.namespaces.update(".".join(parts[:offset]) for offset in range(1, len(parts)))
        self.namespaces.difference_update(self.sources)

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.sources:
            relative, _, package = self.sources[fullname]
            return importlib.util.spec_from_loader(fullname, self,
                origin="captured:" + relative, is_package=package)
        if fullname in self.namespaces:
            return importlib.util.spec_from_loader(fullname, self, is_package=True)
        if fullname.split(".")[0] in _BLOCKED_ROOTS:
            _refuse("repository import is outside the captured source inventory")
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        if module.__name__ in self.namespaces:
            module.__path__ = [str(LANE_ROOT / module.__name__.replace(".", "/"))]
            return
        relative, raw, package = self.sources[module.__name__]
        module.__file__ = str(LANE_ROOT / relative)
        module.__cached__ = None
        if package:
            module.__path__ = [str((LANE_ROOT / relative).parent)]
        exec(compile(raw, module.__file__, "exec", dont_inherit=True), module.__dict__)
        self.executed.append({"path": relative, "sha256": _sha(raw)})


def _decode_sources(rows: object) -> tuple[tuple[str, bytes], ...]:
    if type(rows) is not list or not 1 <= len(rows) <= 512:
        _refuse("worker source inventory is malformed")
    sources = []
    for row in rows:
        if (type(row) is not dict or set(row) != {"path", "sha256", "source_b64"}
                or type(row["sha256"]) is not str or _SHA.fullmatch(row["sha256"]) is None
                or type(row["source_b64"]) is not str):
            _refuse("worker source row is malformed")
        _module_name(row["path"])
        raw = base64.b64decode(row["source_b64"], validate=True)
        if (len(raw) > _MAX_SOURCE_BYTES or _sha(raw) != row["sha256"]
                or (not raw and not row["path"].endswith("/__init__.py"))):
            _refuse("worker source bytes differ from their captured identity")
        sources.append((row["path"], raw))
    if ([path for path, _ in sources] != sorted(path for path, _ in sources)
            or len({path for path, _ in sources}) != len(sources)):
        _refuse("worker source ordering or uniqueness differs")
    return tuple(sources)


def _scalar_receipt(receipt: object, commit: str, inventory_sha: str) -> dict[str, object]:
    if (type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS
            or receipt.get("kind") != "INSETF-IB1C-RETAINED-AFFECTED-QUARTER-v2"
            or receipt.get("period") != "2006Q1"
            or receipt.get("parser_commit") != commit
            or receipt.get("source_inventory_sha256") != inventory_sha):
        _refuse("worker scalar receipt does not bind the captured context")
    for key, value in receipt.items():
        if (type(key) is not str or re.fullmatch(r"[a-z][a-z_0-9]{0,127}", key) is None
                or type(value) not in {str, int, bool, type(None)}
                or type(value) is str and len(value) > 4096
                or type(value) is int and not 0 <= value < 2**63
                or type(value) is bool and value is not False):
            _refuse("worker receipt is not bounded zero-authority scalar metadata")
    if any(type(receipt[key]) is not type(value) or receipt[key] != value
           for key, value in _AUTHORITY.items()):
        _refuse("worker receipt has missing, malformed or nonzero authority")
    if any(type(receipt[key]) is not str or _SHA.fullmatch(receipt[key]) is None
           for key in _RECEIPT_HASHES):
        _refuse("worker receipt digest is malformed")
    if (any(type(receipt[key]) is not int or receipt[key] < 0 for key in _RECEIPT_COUNTS)
            or receipt["whole_quarter_identity_sha256"] is not None
            or receipt["quarters_assessed"] != 1 or receipt["supplied_parent_count"] != 0
            or receipt["corroborated_count"] != 0
            or receipt["quarantined_count"] != receipt["submission_count"]
            or not 0 < receipt["accession_year_mismatch_count"] <= receipt["submission_count"]
            or receipt["short_cik_count"] > receipt["submission_count"]
            or not 0 < receipt["assessment_envelope_bytes"] <= 128 * 1024 * 1024
            or type(receipt["raw_snapshot_id"]) is not str
            or re.fullmatch(r"sec-insider-bulk-2006q1-[0-9a-f]{16}", receipt["raw_snapshot_id"]) is None
            or type(receipt["parsed_snapshot_id"]) is not str
            or re.fullmatch(r"sec-insider-parsed-2006q1-[0-9a-f]{16}", receipt["parsed_snapshot_id"]) is None):
        _refuse("worker receipt count, snapshot or quarantine accounting differs")
    return receipt


def _worker_main(bundle: object) -> None:
    stage = "capture"
    try:
        sys.dont_write_bytecode = True
        sys.addaudithook(_audit_event)
        if (type(bundle) is not dict or set(bundle) != {
                "sources", "worker_source_b64", "worker_source_sha256",
                "source_inventory_sha256", "expected_commit", "input_root", "output_root"}
                or type(bundle["expected_commit"]) is not str
                or _COMMIT.fullmatch(bundle["expected_commit"]) is None):
            _refuse("worker bundle is malformed")
        sources = _decode_sources(bundle["sources"])
        current = dict(sources)
        if (_sha(current.get(_WORKER_PATH, b"")) != bundle["worker_source_sha256"]
                or current.get(_WORKER_PATH) != base64.b64decode(bundle["worker_source_b64"], validate=True)
                or _CORE_PATH not in current
                or _digest(_inventory(sources)) != bundle["source_inventory_sha256"]):
            _refuse("worker source or inventory image differs")
        if any(name.split(".")[0] in _BLOCKED_ROOTS for name in sys.modules):
            _refuse("worker inherited a repository module")
        _assert_sources_unchanged(sources)
        finder = _SourceFinder(sources)
        finder.executed.append({"path": _WORKER_PATH, "sha256": bundle["worker_source_sha256"]})
        sys.meta_path.insert(0, finder)
        core = importlib.import_module(_CORE_MODULE)
        args = (Path(bundle["input_root"]), Path(bundle["output_root"]),
                bundle["expected_commit"], bundle["source_inventory_sha256"])
        stage = "run"
        receipt = _scalar_receipt(core._run_quarter(*args), args[2], args[3])
        stage = "replay"
        if core._verify_quarter(*args) != receipt:
            _refuse("published quarter differs from its raw-bound independent rederivation")
        stage = "trace"
        _assert_sources_unchanged(sources)
        payload = {"receipt": receipt, "executed_modules": finder.executed}
        raw = _canonical(payload)
        if not 0 < len(raw) + 1 <= _MAX_OUTPUT_BYTES:
            _refuse("worker scalar receipt exceeds its output cap")
        sys.stdout.buffer.write(raw + b"\n")
        sys.stdout.buffer.flush()
    except BaseException as exc:
        name = type(exc).__name__
        if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", name) is None:
            name = "WorkerError"
        # Neither str(exc), a traceback nor any filing/header value is emitted.
        sys.stderr.write(f"REFUSED: isolated affected-quarter stage={stage} error={name}\n")
        raise SystemExit(1) from None


_BOOTSTRAP = """import base64, hashlib, json, sys, types
try:
    raw = sys.stdin.buffer.read(33554433)
    if not 0 < len(raw) <= 33554432:
        raise ValueError()
    b = json.loads(raw)
    s = base64.b64decode(b['worker_source_b64'], validate=True)
    if hashlib.sha256(s).hexdigest() != b['worker_source_sha256']:
        raise ValueError()
    m = types.ModuleType('_insider_affected_quarter_worker')
    m.__file__ = sys.argv[1]
    sys.modules[m.__name__] = m
    exec(compile(s, m.__file__, 'exec', dont_inherit=True), m.__dict__)
    m._worker_main(b)
except SystemExit:
    raise
except BaseException:
    sys.stderr.write('REFUSED: isolated affected-quarter bootstrap failed\\n')
    raise SystemExit(1) from None
"""


def _worker_failure(stderr: bytes) -> str:
    """Only the fixed-stage/class protocol can influence a parent diagnostic."""
    if stderr == b"REFUSED: isolated affected-quarter bootstrap failed\n":
        return "isolated preparation refused during bootstrap"
    match = re.fullmatch(
        rb"REFUSED: isolated affected-quarter stage=(capture|run|replay|trace) "
        rb"error=([A-Za-z_][A-Za-z_0-9]{0,79})\n", stderr,
    )
    if match is not None:
        return ("isolated preparation refused at " + match[1].decode("ascii")
                + " (" + match[2].decode("ascii") + ")")
    return "isolated preparation refused without a valid redacted diagnostic"


def _run_worker(raw: bytes, output_root: Path, timeout_seconds: int = _MAX_RUNTIME_SECONDS,
                *, readonly: bool = False):
    if (type(raw) is not bytes or not 0 < len(raw) <= _MAX_INPUT_BYTES
            or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= _MAX_RUNTIME_SECONDS):
        _refuse("worker input or runtime bound is malformed")
    bootstrap = _READONLY_BOOTSTRAP if readonly else _BOOTSTRAP
    command = ("/usr/bin/sandbox-exec", "-p", _worker_policy(output_root, readonly=readonly),
               str(Path(sys.executable).resolve()), "-I", "-S", "-B", "-c", bootstrap,
               str(LANE_ROOT / _WORKER_PATH))
    deadline = time.monotonic() + timeout_seconds
    proc = subprocess.Popen(command, cwd=LANE_ROOT, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, errors, offset = bytearray(), bytearray(), 0
    try:
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        for handle in (proc.stdin, proc.stdout, proc.stderr):
            os.set_blocking(handle.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdin, selectors.EVENT_WRITE)
            selector.register(proc.stdout, selectors.EVENT_READ)
            selector.register(proc.stderr, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _refuse("isolated preparation exceeded its runtime bound")
                for key, _ in selector.select(min(remaining, 1.0)):
                    handle = key.fileobj
                    if handle is proc.stdin:
                        try:
                            offset += os.write(handle.fileno(), raw[offset:offset + 65536])
                        except BrokenPipeError:
                            selector.unregister(handle)
                            handle.close()
                            continue
                        if offset == len(raw):
                            selector.unregister(handle)
                            handle.close()
                    else:
                        chunk = os.read(handle.fileno(), 65536)
                        if not chunk:
                            selector.unregister(handle)
                            handle.close()
                            continue
                        target = output if handle is proc.stdout else errors
                        if len(target) + len(chunk) > _MAX_OUTPUT_BYTES:
                            _refuse("isolated preparation exceeded its output bound")
                        target.extend(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _refuse("isolated preparation exceeded its runtime bound")
        return subprocess.CompletedProcess(command, proc.wait(timeout=remaining), bytes(output), bytes(errors))
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        for handle in (proc.stdin, proc.stdout, proc.stderr):
            if handle is not None and not handle.closed:
                handle.close()


_READONLY_BOOTSTRAP = _BOOTSTRAP.replace("m._worker_main(b)", "m._readonly_worker_main(b)")


def _producer_inventory(sources: tuple[tuple[str, bytes], ...]) -> list[dict[str, str]]:
    """Capture original producer inventory; do not rename today's added files as it."""
    names = _git("ls-tree", "-r", "--name-only", _PRODUCER_COMMIT).decode("utf-8").splitlines()
    paths = sorted(name for name in names if (
        name.startswith("data/") and name.count("/") == 1 and name.endswith(".py")
        or name.startswith("research/insider_buying") and name.count("/") == 1 and name.endswith(".py")
        or name.startswith("research/insider_buying/") and name.count("/") == 2 and name.endswith(".py")
        or name in {"ml/__init__.py", "ml/immutable_io.py", "research/__init__.py"}))
    inventory = [{"path": path, "sha256": _sha(_git("cat-file", "blob", f"{_PRODUCER_COMMIT}:{path}"))}
                 for path in paths]
    _compatible_producer_sources(sources, inventory)
    return inventory


def _compatible_producer_sources(sources, inventory) -> None:
    current = dict(sources)
    if (type(inventory) is not list or len(inventory) != 96
            or any(type(row) is not dict or set(row) != {"path", "sha256"}
                   or type(row["path"]) is not str or type(row["sha256"]) is not str
                   or _SHA.fullmatch(row["sha256"]) is None for row in inventory)
            or [row["path"] for row in inventory] != sorted({row["path"] for row in inventory})
            or _digest(inventory) != _PRODUCER_INVENTORY_SHA256):
        _refuse("original producer inventory differs from its observed 96-source identity")
    for row in inventory:
        _module_name(row["path"])
        if row["path"] not in current:
            _refuse("an original producer dependency is missing from the consumer capture")
        # The revised launcher is explicitly inventoried as new consumer code.
        # All other original parsing/assessment dependencies remain byte-exact.
        if row["path"] != _WORKER_PATH and _sha(current[row["path"]]) != row["sha256"]:
            _refuse("an original producer dependency differs from its committed bytes")


def _readonly_paths(input_root: Path, preparation_root: Path) -> tuple[tuple[int, int], tuple[int, int]]:
    _plain_directory(input_root, must_exist=True)
    _plain_directory(preparation_root, must_exist=True)
    if _overlap(input_root, preparation_root) or _overlap(LANE_ROOT, preparation_root):
        _refuse("retained preparation overlaps input or repository")
    identities = (_directory_identity(input_root), _directory_identity(preparation_root))
    if any(identity is None for identity in identities):
        _refuse("read-only input identity is unavailable")
    return identities


def _readonly_worker_main(bundle: object) -> None:
    stage = "capture"
    try:
        sys.dont_write_bytecode = True
        sys.addaudithook(_audit_event)
        if (type(bundle) is not dict or set(bundle) != {
                "sources", "worker_source_b64", "worker_source_sha256",
                "source_inventory_sha256", "expected_commit", "input_root",
                "preparation_root", "producer_inventory"}
                or type(bundle["expected_commit"]) is not str
                or _COMMIT.fullmatch(bundle["expected_commit"]) is None):
            _refuse("read-only consumer bundle is malformed")
        sources = _decode_sources(bundle["sources"])
        current = dict(sources)
        if (_sha(current.get(_WORKER_PATH, b"")) != bundle["worker_source_sha256"]
                or current.get(_WORKER_PATH) != base64.b64decode(bundle["worker_source_b64"], validate=True)
                or _CONSUMER_PATH not in current
                or _digest(_inventory(sources)) != bundle["source_inventory_sha256"]):
            _refuse("read-only source or inventory image differs")
        _compatible_producer_sources(sources, bundle["producer_inventory"])
        if any(name.split(".")[0] in _BLOCKED_ROOTS for name in sys.modules):
            _refuse("read-only worker inherited repository code")
        paths = (Path(bundle["input_root"]), Path(bundle["preparation_root"]))
        before = _readonly_paths(*paths)
        _assert_sources_unchanged(sources)
        finder = _SourceFinder(sources)
        finder.executed.append({"path": _WORKER_PATH, "sha256": bundle["worker_source_sha256"]})
        sys.meta_path.insert(0, finder)
        stage = "replay"
        core = importlib.import_module(_CONSUMER_MODULE)
        receipt = core.build_retained_2006_handoff(*paths)
        stage = "trace"
        if _readonly_paths(*paths) != before:
            _refuse("read-only directory identities changed")
        _assert_sources_unchanged(sources)
        raw = _canonical({"receipt": receipt, "executed_modules": finder.executed})
        if not 0 < len(raw) + 1 <= _MAX_OUTPUT_BYTES:
            _refuse("read-only receipt exceeds its output cap")
        sys.stdout.buffer.write(raw + b"\n")
        sys.stdout.buffer.flush()
    except BaseException as exc:
        name = type(exc).__name__
        if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", name) is None:
            name = "WorkerError"
        sys.stderr.write(f"REFUSED: isolated affected-quarter stage={stage} error={name}\n")
        raise SystemExit(1) from None


def _consumer_receipt(value: object) -> dict[str, object]:
    if (type(value) is not dict or set(value) != {
            "kind", "quarter", "selected_scope", "retained_82_partial_scope", "pilot",
            "artifact_validation", "authority", "backtest_pipeline"}
            or value["kind"] != "INSETF-IB1C-V2-RETAINED-DOWNSTREAM-READBACK-v1"):
        _refuse("read-only downstream receipt shape differs")
    for body in (value, value["quarter"], value["selected_scope"], value["retained_82_partial_scope"]):
        if (type(body) is not dict or type(body.get("authority")) is not dict
                or set(body["authority"]) != set(_AUTHORITY)
                or any(type(body["authority"][key]) is not type(expected)
                       or body["authority"][key] != expected for key, expected in _AUTHORITY.items())):
            _refuse("downstream receipt has missing or nonzero financial authority")
    quarter, selected, partial, pilot = (value[key] for key in (
        "quarter", "selected_scope", "retained_82_partial_scope", "pilot"))
    binding = quarter.get("preparation_binding")
    if (type(binding) is not dict or binding.get("producer_commit") != _PRODUCER_COMMIT
            or binding.get("producer_source_inventory_sha256") != _PRODUCER_INVENTORY_SHA256
            or binding.get("assessment_envelope_sha256") != "402fa1860bd9549f6d0eadcf7dc9a956cc0dc006d91f038290c294c102083ad5"
            or binding.get("completion_envelope_sha256") != "d05e0345124b96599fbbd82a81828452ea63d39a90b3be28b599ef1e462bbfd0"
            or type(binding.get("assessment_envelope_bytes")) is not int
            or binding["assessment_envelope_bytes"] != 63_409_968
            or quarter.get("artifact_loading_verified_here") is not False
            or quarter.get("source_identity_complete") is not False
            or quarter.get("source_identity_sha256") is not None
            or type(quarter.get("submission_count")) is not int or quarter["submission_count"] != 83_657
            or type(quarter.get("quarantined_count")) is not int or quarter["quarantined_count"] != 83_657
            or type(quarter.get("corroborated_count")) is not int or quarter["corroborated_count"] != 0
            or type(quarter.get("accession_year_mismatch_count")) is not int or quarter["accession_year_mismatch_count"] != 1
            or selected.get("loaded_scope_complete") is not True
            or selected.get("missing_periods") != []
            or selected.get("expected_periods") != ["2006Q1"]
            or selected.get("loaded_periods") != ["2006Q1"]
            or partial.get("loaded_scope_complete") is not False
            or partial.get("loaded_periods") != ["2006Q1"]
            or type(partial.get("missing_periods")) is not list or len(partial["missing_periods"]) != 81
            or type(pilot) is not dict or pilot.get("event_eligibility") != "not_evaluated"
            or pilot.get("candidate_signal_count") is not None
            or type(pilot.get("row_count")) is not int or pilot["row_count"] != 83_657
            or type(pilot.get("quarantined_count")) is not int or pilot["quarantined_count"] != 83_657
            or type(pilot.get("source_only_admitted_count")) is not int or pilot["source_only_admitted_count"] != 0
            or pilot.get("ledger_sha256") != quarter.get("rows_sha256")
            or type(pilot.get("ledger_sha256")) is not str or _SHA.fullmatch(pilot["ledger_sha256"]) is None):
        _refuse("observed retained all-row quarantine or producer binding differs")
    for body in (selected, partial):
        if body.get("source_identity_complete") is not False or body.get("source_identity_sha256") is not None:
            _refuse("incomplete downstream source identity was promoted")
    expected_validation = {
        "public_raw_bound_parsed_reload": True, "complete_assessment_rederived": True,
        "complete_completion_rederived": True, "producer_lineage_preserved": True,
        "source_only": True, "publisher_or_recovery_called": False,
    }
    if (type(value["artifact_validation"]) is not dict
            or set(value["artifact_validation"]) != set(expected_validation)
            or any(value["artifact_validation"][key] is not flag for key, flag in expected_validation.items())):
        _refuse("read-only artifact replay validation differs")
    # Every nested scalar is part of the wire protocol. Reject unknown fields,
    # bool/int substitution, dropped scope accounting and any inferred authority
    # even though the source-only consumer itself is independently captured.
    expected_binding = {
        "period": "2006Q1", "producer_commit": _PRODUCER_COMMIT,
        "producer_source_inventory_sha256": _PRODUCER_INVENTORY_SHA256,
        "completion_envelope_sha256": "d05e0345124b96599fbbd82a81828452ea63d39a90b3be28b599ef1e462bbfd0",
        "assessment_envelope_sha256": "402fa1860bd9549f6d0eadcf7dc9a956cc0dc006d91f038290c294c102083ad5",
        "assessment_envelope_bytes": 63_409_968,
        "raw_snapshot_id": "sec-insider-bulk-2006q1-afe9a4b0bd20acce",
        "raw_lineage_sha256": "afe9a4b0bd20acce459c2f0fe7989b20c5422f333395ec03e0a737feac357f23",
        "parsed_snapshot_id": "sec-insider-parsed-2006q1-777136638dc6a1e5",
        "parsed_lineage_sha256": "777136638dc6a1e5794bdd7878672ac9c08e33226b09306ccd262c6511c6de84",
        "profile_sha256": "ee2f201362d4002a70819e4d7123eea300aafddb8820c6a0ab9761b0ed8cdd41",
        "census_quarter_sha256": "047b92bdcd8fe82b21d76cddc05c8cca1ec31d7dec6e9c5186a1312e4cd4c5a2",
    }
    if _canonical(binding) != _canonical(expected_binding):
        _refuse("downstream producer binding fields or exact original identities differ")
    policy = {"evidence_epoch": "INSETF-IB1C-V2-DOWNSTREAM-SOURCE-ONLY-v1",
              "policy_version": "INSETF-IB1C-SUPPLIED-SOURCE-IDENTITY-v2",
              "policy_epoch": "INSETF-IB1C-SUPPLIED-SOURCE-IDENTITY-v2-candidate"}
    counts = {"submission_count": 83_657, "corroborated_count": 0, "quarantined_count": 83_657,
              "short_cik_count": 0, "accession_year_mismatch_count": 1}
    forms = {"3": 5694, "3/A": 534, "4": 68520, "4/A": 3159, "5": 5539, "5/A": 211}
    reasons = {"complete_parent_identity_conflict": 0, "complete_parent_corroboration_missing": 71_679,
               "unsupported_parent_corroboration_form": 11_978}
    expected_quarter = {
        "kind": "INSETF-IB1C-V2-DOWNSTREAM-QUARTER-v1", **policy,
        "period": "2006Q1", "preparation_binding": expected_binding,
        "assessment_sha256": "3000a184944aa1718854dba90842ec774032c269fc36740dc46ddbe90c1f1525",
        "rows_sha256": pilot["ledger_sha256"], **counts,
        "form_counts": forms, "quarantine_reason_counts": reasons,
        "source_identity_complete": False, "source_identity_sha256": None,
        "artifact_loading_verified_here": False, "binding_is_external_attestation": False,
        "authority": _AUTHORITY,
    }
    if _canonical(quarter) != _canonical(expected_quarter):
        _refuse("downstream quarter accounting protocol differs")
    periods = [f"{year}Q{part}" for year in range(2006, 2027) for part in range(1, 5)
               if (year, part) <= (2026, 2)]
    for body, expected_periods in ((selected, ["2006Q1"]), (partial, periods)):
        expected_scope = {
            "kind": "INSETF-IB1C-V2-DOWNSTREAM-SCOPE-v1", **policy,
            "expected_periods": expected_periods, "loaded_periods": ["2006Q1"],
            "missing_periods": expected_periods[1:], "loaded_scope_complete": len(expected_periods) == 1,
            "source_identity_complete": False, "source_identity_sha256": None,
            "quarter_bindings": [{"period": "2006Q1", "coverage_sha256": _digest(quarter),
                                  "source_identity_sha256": None}], **counts,
            "form_counts": forms, "quarantine_reason_counts": reasons,
            "artifact_loading_verified_here": False, "authority": _AUTHORITY,
        }
        if _canonical(body) != _canonical(expected_scope):
            _refuse("downstream scope accounting protocol differs")
    if _canonical(pilot) != _canonical({
            "row_count": 83_657, "ledger_sha256": quarter["rows_sha256"],
            "source_only_admitted_count": 0, "quarantined_count": 83_657,
            "event_eligibility": "not_evaluated", "candidate_signal_count": None}):
        _refuse("downstream pilot accounting protocol differs")
    expected_pipeline = {
        "kind": "INSETF-IB-BACKTEST-EVIDENCE-PIPELINE-v1-coverage-handoff",
        "coverage_sha256": _digest(quarter), "period": "2006Q1", **{
            key: counts[key] for key in ("submission_count", "corroborated_count", "quarantined_count")},
        "form_counts": forms, "quarantine_reason_counts": reasons,
        "source_identity_complete": False, "source_identity_sha256": None,
        "relevant_form4_count": 71_679, "relevant_form4_identity_complete": False,
        "eligible_events_evaluated": False, "admitted_event_count": 0,
        "backtesting_ready": False,
        "missing_evidence": [
            "externally_anchored_complete_source_manifest_and_original_parents",
            "externally_anchored_point_in_time_security_master",
            "externally_anchored_regular_session_open_close_calendar",
            "externally_anchored_single_study_authorization_and_rights"],
        "source_authenticated": False, "qc_jobs": 0, "research_looks": 0,
    }
    if _canonical(value["backtest_pipeline"]) != _canonical(expected_pipeline):
        _refuse("unresolved actual source coverage was dropped or promoted in the backtest pipeline")
    return value


def run_readonly_consumer(input_root: Path, preparation_root: Path,
                          expected_commit: str) -> dict[str, object]:
    """Replay retained preparation with all worker file writes and network denied."""
    try:
        before = _repository_snapshot(expected_commit)
        identities = _readonly_paths(input_root, preparation_root)
        if not Path("/usr/bin/sandbox-exec").is_file():
            _refuse("required OS process sandbox is unavailable")
        sources = _source_snapshot()
        current = dict(sources)
        if not {_WORKER_PATH, _CORE_PATH, _CONSUMER_PATH} <= set(current):
            _refuse("read-only consumer sources are missing")
        _verify_committed_sources(sources, expected_commit)
        producer_inventory = _producer_inventory(sources)
        inventory_sha = _digest(_inventory(sources))
        bundle = {"sources": [{"path": path, "sha256": _sha(raw),
                    "source_b64": base64.b64encode(raw).decode("ascii")} for path, raw in sources],
                  "worker_source_b64": base64.b64encode(current[_WORKER_PATH]).decode("ascii"),
                  "worker_source_sha256": _sha(current[_WORKER_PATH]),
                  "source_inventory_sha256": inventory_sha, "expected_commit": expected_commit,
                  "input_root": str(input_root), "preparation_root": str(preparation_root),
                  "producer_inventory": producer_inventory}
        _assert_sources_unchanged(sources)
        if _repository_snapshot(expected_commit) != before:
            _refuse("lane context changed before read-only replay")
        result = _run_worker(_canonical(bundle), preparation_root, readonly=True)
        if (_readonly_paths(input_root, preparation_root) != identities
                or _repository_snapshot(expected_commit) != before):
            _refuse("lane or retained directory identity changed during replay")
        _assert_sources_unchanged(sources)
        if result.returncode != 0:
            _refuse(_worker_failure(result.stderr))
        if result.stderr or not 0 < len(result.stdout) <= _MAX_OUTPUT_BYTES:
            _refuse("read-only worker output is unavailable or oversized")
        payload = json.loads(result.stdout)
        if (type(payload) is not dict or set(payload) != {"receipt", "executed_modules"}
                or result.stdout != _canonical(payload) + b"\n"):
            _refuse("read-only worker returned a noncanonical receipt")
        receipt = _consumer_receipt(payload["receipt"])
        trace, seen = payload["executed_modules"], set()
        if type(trace) is not list or not 3 <= len(trace) <= len(sources):
            _refuse("read-only executed source inventory is malformed")
        for row in trace:
            if (type(row) is not dict or set(row) != {"path", "sha256"}
                    or type(row["path"]) is not str or row["path"] in seen
                    or row["path"] not in current or row["sha256"] != _sha(current[row["path"]])):
                _refuse("read-only executed source differs from its capture")
            seen.add(row["path"])
        if not {_WORKER_PATH, _CORE_PATH, _CONSUMER_PATH} <= seen:
            _refuse("required read-only consumer execution was not observed")
        return {"receipt": receipt, "consumer_commit": expected_commit,
                "consumer_source_inventory_sha256": inventory_sha,
                "consumer_source_count": len(sources),
                "producer_dependency_compatibility_count": 95,
                "producer_inventory_sha256": _PRODUCER_INVENTORY_SHA256,
                "worker_source_sha256": _sha(current[_WORKER_PATH]),
                "worker_bootstrap_sha256": _sha(_READONLY_BOOTSTRAP.encode("utf-8")),
                "executed_source_inventory_sha256": _digest(trace), "executed_source_count": len(trace),
                "os_network_denied": True, "os_all_file_writes_denied": True,
                "os_process_fork_denied": True, "audit_additional_processes_denied": True,
                "source_only_lane_imports": True}
    except AffectedQuarterIsolationError:
        raise
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, RecursionError,
            subprocess.SubprocessError) as exc:
        raise AffectedQuarterIsolationError("REFUSED: read-only downstream boundary failed") from exc


def run_isolated(input_root: Path, output_root: Path, expected_commit: str) -> dict[str, object]:
    """Prepare exactly one quarter, returning small verified scalar metadata."""
    try:
        before = _repository_snapshot(expected_commit)
        _validate_paths(input_root, output_root)
        sandbox = Path("/usr/bin/sandbox-exec")
        if not sandbox.is_file() or not os.access(sandbox, os.X_OK):
            _refuse("required OS process sandbox is unavailable")
        sources = _source_snapshot()
        current = dict(sources)
        if _WORKER_PATH not in current or _CORE_PATH not in current:
            _refuse("committed launcher or core source is missing")
        _verify_committed_sources(sources, expected_commit)
        if _repository_snapshot(expected_commit) != before:
            _refuse("lane context changed before isolated preparation")
        inventory_sha = _digest(_inventory(sources))
        bundle = {"sources": [{"path": path, "sha256": _sha(raw),
                    "source_b64": base64.b64encode(raw).decode("ascii")} for path, raw in sources],
                  "worker_source_b64": base64.b64encode(current[_WORKER_PATH]).decode("ascii"),
                  "worker_source_sha256": _sha(current[_WORKER_PATH]),
                  "source_inventory_sha256": inventory_sha, "expected_commit": expected_commit,
                  "input_root": str(input_root), "output_root": str(output_root)}
        raw = _canonical(bundle)
        if len(raw) > _MAX_INPUT_BYTES:
            _refuse("captured source bundle exceeds its byte cap")
        _validate_paths(input_root, output_root)
        output_root.mkdir(mode=0o700)
        identity = _directory_identity(output_root)
        assert identity is not None
        _check_output(output_root, identity)
        _assert_sources_unchanged(sources)
        result = _run_worker(raw, output_root)
        _check_output(output_root, identity)
        _assert_sources_unchanged(sources)
        if _repository_snapshot(expected_commit) != before:
            _refuse("lane context changed during isolated preparation")
        if result.returncode != 0:
            _refuse(_worker_failure(result.stderr) + "; incomplete output, if any, is retained")
        if result.stderr or not 0 < len(result.stdout) <= _MAX_OUTPUT_BYTES:
            _refuse("isolated preparation returned invalid output; incomplete output, if any, is retained")
        payload = json.loads(result.stdout)
        if (type(payload) is not dict or set(payload) != {"receipt", "executed_modules"}
                or result.stdout != _canonical(payload) + b"\n"):
            _refuse("isolated preparation returned a noncanonical receipt")
        receipt = _scalar_receipt(payload["receipt"], expected_commit, inventory_sha)
        trace = payload["executed_modules"]
        if type(trace) is not list or not 2 <= len(trace) <= len(sources):
            _refuse("executed source inventory is malformed")
        seen = set()
        for row in trace:
            if (type(row) is not dict or set(row) != {"path", "sha256"}
                    or type(row["path"]) is not str or row["path"] in seen
                    or row["path"] not in current or row["sha256"] != _sha(current[row["path"]])):
                _refuse("executed source differs from the committed capture")
            seen.add(row["path"])
        if not {_WORKER_PATH, _CORE_PATH} <= seen:
            _refuse("launcher or core execution was not observed")
        return {**receipt, "worker_source_sha256": _sha(current[_WORKER_PATH]),
                "worker_bootstrap_sha256": _sha(_BOOTSTRAP.encode("utf-8")),
                "executed_source_inventory_sha256": _digest(trace), "executed_source_count": len(trace),
                "os_network_denied": True, "os_output_write_confined": True,
                "os_process_fork_denied": True, "audit_additional_processes_denied": True,
                "source_only_lane_imports": True}
    except AffectedQuarterIsolationError:
        raise
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, RecursionError,
            subprocess.SubprocessError) as exc:
        raise AffectedQuarterIsolationError("REFUSED: isolated affected-quarter boundary failed") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-root", type=Path)
    mode.add_argument("--preparation-root", type=Path)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    try:
        result = (run_readonly_consumer(args.input_root, args.preparation_root, args.expected_commit)
                  if args.preparation_root is not None else
                  run_isolated(args.input_root, args.output_root, args.expected_commit))
    except AffectedQuarterIsolationError as exc:
        sys.stderr.write(str(exc) + "\n")
        raise SystemExit(1) from None
    print(_canonical(result).decode("utf-8"))


if __name__ == "__main__":
    main()
