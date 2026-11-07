"""Distinct finite code windows around unchanged external-byte custody.

Only committed public Python code is bootstrapped into a private RAM graph.
No external archive opens before the original five-code window has CLOSED.
There is no continuous shared-ancestor timestamp claim between code windows.
Old reader/model code and every external-data check remain unchanged.
"""
from __future__ import annotations

import builtins
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from types import CodeType, FrameType, FunctionType, ModuleType


ROOT = Path("/Users/sheltonchen/Documents/Codex/2026-09-03/f/trading_agent__short_interest")
USB = Path("/Volumes/SANDISK/firstrate")
DRIVER = "scripts/inspect_short_interest_usb_code_snapshot.py"
READER = "scripts/inspect_short_interest_usb_archive.py"
MODEL = "research/short_interest_etf/firstrate_short_interest_inspection.py"
CODE_FILES = ("data/__init__.py", "data/hashing.py", MODEL, READER, DRIVER)
INPUTS = (
    ("full", "fundamentals/Short_Interest/Full_Dataset.zip", 34319601, "08f019c20384bde811b10d1674dc5067cfded4e4c0097fc8c383649c528429c8"),
    ("year", "fundamentals/Short_Interest/2026_data_only.zip", 9660009, "3a8a07dec5c91f4e54cda396d9b1483895769d6ecac1a8d1a15a64e873fa191a"),
    ("manifest", "manifest.json", 327907, "c681af584244d38e3f9dea2ff765cc2c991cb383107a3e542115a4338ee4cdf8"),
    ("readme", "fundamentals/Short_Interest/Read_Me_Documentation.txt", 1051, "bbcddf477ba3ffacb4b0116e9d3f6c2c2a864576ae748abc8daa825602a16ecf"),
)
MAX_SECONDS, MAX_CODE_BYTES, MAX_FAILURES = 180, 1024 ** 2, 32
PROFILE_SHA256 = "592c05adc1691030eb5aa3d93660f060248aaa25909bd3503781a446f292c43f"
_ALIASES = ("_si_usb_window_data_v1", "_si_usb_window_hashing_v1", "_si_usb_window_reader_v1", "_si_usb_window_model_v1")
_STDLIB = frozenset(("__future__", "collections", "collections.abc", "contextlib", "csv", "dataclasses", "datetime", "decimal", "fractions", "hashlib", "io", "json", "math", "os", "pathlib", "re", "stat", "struct", "subprocess", "sys", "time", "types", "typing", "zlib", "builtins"))
_CODES = frozenset("arguments registration root_changed lane_changed remote_changed git_refused code_changed code_bound runtime_changed graph_changed import_refused namespace_occupied namespace_changed snapshot_factory snapshot_changed snapshot_failed window_failed attempt_spent clock_failed input_changed inspection_refused".split())
_PHASES = frozenset("unknown bootstrap initial_code source_open model source_audit source_close source_after_close terminal_code final_guard namespace_cleanup final_format".split())
_RUNS, _CLOCKS, _CLOCK_LAST, _COMMITS, _WINDOWS, _SNAPSHOTS = [], {}, {}, {}, {}, {}
_SNAPSHOT_FAILED, _NEGATIVES = set(), {}


class CodeSnapshotRefusal(ValueError):
    pass


def require(value, code):
    if not value:
        raise CodeSnapshotRefusal(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return _sha(_canonical(value))


def policy():
    return {"schema": "si-usb-code-window-policy-v1", "root": str(ROOT), "usb": str(USB),
        "code_files": list(CODE_FILES), "inputs": [list(row) for row in INPUTS],
        "maximum_seconds": MAX_SECONDS, "maximum_code_bytes": MAX_CODE_BYTES,
        "maximum_failure_facts": MAX_FAILURES, "aliases": list(_ALIASES),
        "code": "five_committed_blobs_fixed_RAM_import_graph_initial_original10_window_all_closed_before_snapshot_and_USB",
        "terminal": "source_all_closed_then_distinct_original10_code_window_bytes_equal_RAM_and_Git_each_file10_equal_INITIAL",
        "ancestors": "full10_inside_each_window_independent_observations_no_continuous_shared_ancestor_timestamp_claim",
        "execution": "original_bootstrap_codes_globals_producers_bound_to_committed_fifth_then_original_snapshot_graph_only",
        "failures": "first_caught_at_owned_boundary_before_own_unwind_contexts_separate_observations_bounded_cleanup_safe_original_comparisons_no_text_values_paths",
        "authority": authority()}


def authority():
    return {"external_byte_inspection_only": True, "source_admitted": False,
        "protected_source_custody_verified": False, "denominator_admitted": False,
        "actual_input_admitted": False, "ready_for_backtest": False,
        "provider_HTTP": 0, "credential_reads": 0, "new_claims": 0, "new_STARTs": 0,
        "new_charged_bytes": 0, "outcome_looks": 0, "qc_attempts": 0, "QC_or_Safari": False}


def _registered():
    require(type(PROFILE_SHA256) is str and re.fullmatch(r"[0-9a-f]{64}", PROFILE_SHA256)
        and _hash(policy()) == PROFILE_SHA256 and len(CODE_FILES) == len(set(CODE_FILES)) == 5
        and type(MAX_SECONDS) is int and MAX_SECONDS == 180, "registration")


def _root_pin():
    require(ROOT.resolve() == ROOT and Path.cwd().resolve() == ROOT, "root_changed")
    info = ROOT.lstat()
    require(stat.S_ISDIR(info.st_mode), "root_changed")
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode, info.st_nlink


def _stdlib_bindings():
    subjects = ((hashlib, ("sha256",)), (json, ("dumps", "loads")),
        (os, ("open", "close", "read", "lseek", "fstat", "stat", "lstat")),
        (subprocess, ("run",)), (time, ("monotonic",)), (builtins, ("__import__",)),
        (Path, ("resolve", "lstat", "cwd")))
    rows = []
    for owner, names in subjects:
        for name in names:
            value = getattr(owner, name); value = getattr(value, "__func__", value)
            rows.append((owner, name, value, getattr(value, "__code__", None)))
    return tuple(rows)


class _Clock:
    def __init__(self):
        began = time.monotonic()
        require(type(began) in (int, float) and math.isfinite(began) and began >= 0, "clock_failed")
        origin = self, began, time.monotonic, getattr(time.monotonic, "__code__", None), sys._getframe(), _stdlib_bindings()
        self._origin = origin; self.failed = False; self.root = self.graph = self.runtime = None
        _CLOCKS[self] = origin; _CLOCK_LAST[self] = began
    def check(self):
        try:
            row = _CLOCKS.get(self)
            require(not self.failed and row is self._origin and row[0] is self, "clock_failed")
            frame = row[4]
            require(frame.f_code is _Clock.__init__.__code__ and frame.f_globals is globals()
                and frame.f_locals.get("origin") is row and frame.f_locals.get("self") is self
                and time.monotonic is row[2] and getattr(time.monotonic, "__code__", None) is row[3], "clock_failed")
            for owner, name, original, code in row[5]:
                value = getattr(owner, name); value = getattr(value, "__func__", value)
                require(value is original and getattr(value, "__code__", None) is code, "runtime_changed")
            now = row[2]()
            require(type(now) in (int, float) and math.isfinite(now)
                and row[1] <= _CLOCK_LAST[self] <= now and now - row[1] <= MAX_SECONDS, "clock_failed")
            _CLOCK_LAST[self] = now
            if self.runtime is not None: self.runtime.original_runtime(self.runtime)
            if self.root is not None: require(_root_pin() == self.root, "root_changed")
            if self.graph is not None: self.graph.original_validate(self.graph)
            return MAX_SECONDS - (now - row[1])
        except BaseException:
            self.failed = True
            raise


def _git(clock, *arguments):
    remaining = clock.check()
    result = subprocess.run(["git", *arguments], cwd=ROOT, env={"PATH": "/usr/bin:/bin", "GIT_OPTIONAL_LOCKS": "0"},
        stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=max(0.001, min(20, remaining)), check=False)
    clock.check()
    require(type(result.returncode) is int and result.returncode == 0 and type(result.stdout) is bytes, "git_refused")
    return result.stdout


def _guard(clock, head, remote):
    clock.check()
    require(type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head)
        and type(remote) is str and re.fullmatch(r"[0-9a-f]{40}", remote), "arguments")
    require(_root_pin() == clock.root, "root_changed")
    require(_git(clock, "rev-parse", "--show-toplevel").decode().strip() == str(ROOT)
        and _git(clock, "branch", "--show-current").decode().strip() == "codex/strategy-short-interest"
        and _git(clock, "rev-parse", "HEAD").decode().strip() == head
        and not _git(clock, "status", "--porcelain=v1", "-z", "--untracked-files=all").strip(), "lane_changed")
    require(_git(clock, "rev-parse", "refs/remotes/origin/codex/strategy-short-interest").decode().strip() == remote
        and _git(clock, "ls-remote", "--exit-code", "--refs", "origin", "refs/heads/codex/strategy-short-interest").decode().split()
            == [remote, "refs/heads/codex/strategy-short-interest"], "remote_changed")
    clock.check()


def _committed_code(clock, head):
    rows = []
    for name in CODE_FILES:
        raw = _git(clock, "show", head + ":" + name)
        require(type(raw) is bytes and len(raw) <= MAX_CODE_BYTES, "code_bound")
        rows.append((name, raw, _sha(raw)))
    committed = tuple(rows)
    row = committed, clock, head, sys._getframe()
    _COMMITS[id(committed)] = row
    return committed


def _function_pin(value):
    return (value, value.__code__, _constant(value.__defaults__), _constant(value.__kwdefaults__),
        tuple((cell, _constant(cell.cell_contents)) for cell in (value.__closure__ or ())))


def _audit_function(value, pin):
    require(type(value) is FunctionType and value is pin[0] and value.__code__ is pin[1]
        and _constant(value.__defaults__) == pin[2] and _constant(value.__kwdefaults__) == pin[3]
        and len(value.__closure__ or ()) == len(pin[4])
        and all(cell is original and _constant(cell.cell_contents) == content
                for cell, (original, content) in zip(value.__closure__ or (), pin[4])), "graph_changed")


def _constant(value):
    if type(value) in (str, int, bool, float, bytes, type(None)): return type(value), value
    if isinstance(value, Path): return type(value), str(value)
    if type(value) in (tuple, list): return type(value), tuple(_constant(x) for x in value)
    if type(value) in (dict,): return type(value), tuple((key, _constant(item)) for key, item in value.items())
    if type(value) in (set, frozenset): return type(value), frozenset(_constant(x) for x in value)
    return type(value), id(value)


def _module_pin(module, mutable=()):
    rows = []
    for name, value in module.__dict__.items():
        if name in mutable:
            rows.append((name, "mutable", value)); continue
        if type(value) is FunctionType:
            rows.append((name, "function", _function_pin(value))); continue
        if type(value) is type and value.__module__ == module.__name__:
            attrs = tuple((key, "function", _function_pin(item)) if type(item) is FunctionType else
                (key, "property", (item, _function_pin(item.fget))) if type(item) is property and item.fget is not None
                else (key, "constant", (item, _constant(item))) for key, item in value.__dict__.items())
            rows.append((name, "class", (value, attrs))); continue
        rows.append((name, "constant", (value, _constant(value))))
    return tuple(rows)


def _audit_module(module, rows):
    require(tuple(module.__dict__) == tuple(row[0] for row in rows), "graph_changed")
    for name, kind, pin in rows:
        value = module.__dict__[name]
        if kind == "mutable": require(value is pin, "graph_changed")
        elif kind == "function":
            _audit_function(value, pin)
        elif kind == "class":
            require(value is pin[0], "graph_changed")
            require(tuple(value.__dict__) == tuple(row[0] for row in pin[1]), "graph_changed")
            for key, member_kind, member_pin in pin[1]:
                member = value.__dict__[key]
                if member_kind == "function": _audit_function(member, member_pin)
                elif member_kind == "property":
                    require(member is member_pin[0], "graph_changed"); _audit_function(member.fget, member_pin[1])
                else: require(member is member_pin[0] and _constant(member) == member_pin[1], "graph_changed")
        else: require(value is pin[0] and _constant(value) == pin[1], "graph_changed")


class _Graph:
    def __init__(self): raise CodeSnapshotRefusal("snapshot_factory")
    def __setattr__(self, name, value):
        if getattr(self, "sealed", False) and name not in ("failed", "closed"):
            raise CodeSnapshotRefusal("graph_changed")
        object.__setattr__(self, name, value)
    def audit_runtime(self):
        # This retained ORIGINAL method is called even if a public class
        # binding is replaced. Check its helper graph before dispatching it.
        for name, function, code in self.runtime_functions:
            if globals().get(name) is not function or function.__code__ is not code:
                self.failed = True; raise self.error_type("runtime_changed")
        for owner, name, function, code in self.runtime_methods:
            if owner.__dict__.get(name) is not function or function.__code__ is not code:
                self.failed = True; raise self.error_type("runtime_changed")
        if self.runtime_pin is not None:
            require(sys.modules.get(self.runtime_pin[0].__name__) is self.runtime_pin[0], "namespace_changed")
            _audit_module(*self.runtime_pin)
    def validate(self):
        self.original_runtime(self)
        require(not self.failed and not self.closed, "graph_changed")
        try:
            for module, pin in self.pins: _audit_module(module, pin)
            require(type(self.modules) is dict and tuple(self.modules) == tuple(row[0] for row in self.module_originals), "namespace_changed")
            for name, module in self.module_originals:
                require(self.modules[name] is module and sys.modules.get(name) is module, "namespace_changed")
            require(self.importer.__code__ is self.importer_code, "import_refused")
            require(tuple(self.import_table) == tuple(row[0] for row in self.import_table_original)
                and all(self.import_table[name] is module for name, module in self.import_table_original)
                and all(cell.cell_contents is original for cell, original in zip(self.importer.__closure__, self.import_closure)), "import_refused")
        except BaseException:
            self.failed = True; raise
    def cleanup(self):
        first = None
        for name, module in reversed(self.module_originals):
            if sys.modules.get(name) is not module:
                if first is None: first = CodeSnapshotRefusal("namespace_changed")
            else: del sys.modules[name]
        self.closed = True
        if first is not None: raise first


def _new_graph(committed, clock, state):
    origin = _COMMITS.get(id(committed)); caller = sys._getframe(1)
    require(type(origin) is tuple and origin[0] is committed and origin[1] is clock
        and origin[3].f_code is _committed_code.__code__ and origin[3].f_globals is globals()
        and origin[3].f_locals.get("row") is origin
        and caller.f_code is inspect_registered.__code__ and caller.f_globals is globals()
        and caller.f_locals.get("committed") is committed, "snapshot_factory")
    require(all(name not in sys.modules for name in _ALIASES), "namespace_occupied")
    graph = object.__new__(_Graph); graph.failed = graph.closed = False
    graph.modules, graph.pins, graph.module_originals = {}, [], ()
    graph.error_type = CodeSnapshotRefusal
    graph.original_validate = _Graph.validate
    graph.original_runtime = _Graph.audit_runtime; graph.runtime_pin = None
    graph.runtime_functions = tuple((name, value, value.__code__) for name, value in globals().items()
        if type(value) is FunctionType and value.__module__ == __name__)
    graph.runtime_methods = tuple((owner, key, value, value.__code__) for owner in tuple(globals().values())
        if type(owner) is type and owner.__module__ == __name__ for key, value in owner.__dict__.items()
        if type(value) is FunctionType)
    original_import = builtins.__import__; table = {}
    def fixed_import(name, globals=None, locals=None, fromlist=(), level=0):
        require(level == 0, "import_refused")
        if name == "data.hashing": return table[name] if fromlist else table["data"]
        if name == "data": return table[name]
        require(name in _STDLIB, "import_refused")
        return original_import(name, globals, locals, fromlist, level)
    graph.importer, graph.importer_code = fixed_import, fixed_import.__code__
    try:
        raw = {name: body for name, body, unused in committed}
        for alias, path in zip(_ALIASES, (CODE_FILES[0], CODE_FILES[1], READER, MODEL)):
            module = ModuleType(alias); module.__file__ = str(ROOT / path)
            module.__dict__["__builtins__"] = {**vars(builtins), "__import__": fixed_import}
            graph.modules[alias] = module; sys.modules[alias] = module
            graph.module_originals = tuple(graph.modules.items())
            if path == CODE_FILES[0]: table["data"] = module
            if path == CODE_FILES[1]: table["data.hashing"] = module; table["data"].hashing = module
            exec(compile(raw[path], module.__file__, "exec"), module.__dict__)
        graph.reader, graph.model, graph.hashing = (graph.modules[_ALIASES[i]] for i in (2, 3, 1))
        require(graph.reader.INPUTS == INPUTS and graph.reader.CODE_FILES == CODE_FILES[:3] + (READER,), "graph_changed")
        # Compile the fifth committed file as a reference, never a second live
        # orchestrator. Its runtime functions/classes must be this bootstrap.
        expected = ModuleType("_si_usb_expected_bootstrap_v1")
        exec(compile(raw[DRIVER], str(ROOT / DRIVER), "exec"), expected.__dict__)
        actual = sys.modules[__name__]
        for name, value in expected.__dict__.items():
            if type(value) is FunctionType and value.__module__ == expected.__name__:
                current = actual.__dict__.get(name)
                require(type(current) is FunctionType and current.__code__ == value.__code__, "runtime_changed")
            elif type(value) is type and value.__module__ == expected.__name__:
                current = actual.__dict__.get(name)
                require(type(current) is type, "runtime_changed")
                for key, method in value.__dict__.items():
                    if type(method) is FunctionType:
                        require(type(current.__dict__.get(key)) is FunctionType
                            and current.__dict__[key].__code__ == method.__code__, "runtime_changed")
        for key in ("ROOT", "USB", "DRIVER", "READER", "MODEL", "CODE_FILES", "INPUTS", "MAX_SECONDS", "MAX_CODE_BYTES", "MAX_FAILURES", "PROFILE_SHA256", "_ALIASES", "_STDLIB", "_CODES", "_PHASES"):
            require(_constant(actual.__dict__[key]) == _constant(expected.__dict__[key]), "runtime_changed")
        for module in graph.modules.values():
            mutable = ("_STAMP_FAILURES", "_READ_ORIGINS") if module is graph.reader else ("_ISSUED",) if module is graph.model else ()
            graph.pins.append((module, _module_pin(module, mutable)))
        graph.runtime_pin = actual, _module_pin(actual, ("_RUNS", "_CLOCKS", "_CLOCK_LAST", "_COMMITS", "_WINDOWS", "_SNAPSHOTS", "_SNAPSHOT_FAILED", "_NEGATIVES"))
        graph.import_table = table; graph.import_table_original = tuple(table.items())
        graph.import_closure = tuple(cell.cell_contents for cell in fixed_import.__closure__)
        graph.pins = tuple(graph.pins); graph.sealed = True
        graph.original_validate(graph); return graph
    except BaseException as error:
        _remember(state, error, graph, "bootstrap")
        try: graph.cleanup()
        except BaseException as cleanup: _remember(state, cleanup, graph, "namespace_cleanup")
        raise CodeSnapshotRefusal("window_failed") from None


def _fact(error, graph, phase, role, ordinal):
    code = None; detail = None
    if type(error) is CodeSnapshotRefusal:
        args = BaseException.args.__get__(error, BaseException)
        if type(args) is tuple and len(args) == 1 and type(args[0]) is str and args[0] in _CODES: code = args[0]
    if graph is not None and not graph.failed and not graph.closed:
        try:
            graph.validate()
            if type(error) is graph.reader.UsbInspectionRefusal:
                args = BaseException.args.__get__(error, BaseException)
                if type(args) is tuple and len(args) == 1 and type(args[0]) is str and args[0] in graph.reader._CODES: code = args[0]
                detail = graph.reader.comparison_diagnostic(error)
        except BaseException: pass
    return {"phase": phase if phase in _PHASES else "unknown", "role": role if role in ("code", "full", "year", "manifest", "readme") else "unknown",
        "code_ordinal": ordinal if role == "code" and type(ordinal) is int and 1 <= ordinal <= 5 else None,
        "code": code, "original_comparison": detail, "actor": "unknown"}


def _remember(state, error, graph, phase, role="unknown", ordinal=None):
    for identifier, record in tuple(_SNAPSHOTS.items()):
        if type(record) is tuple and len(record) == 8 and record[1] is graph:
            _SNAPSHOT_FAILED.add(identifier)
    chain = []; current = error
    while isinstance(current, BaseException) and not any(current is item for item in chain) and len(chain) < MAX_FAILURES:
        chain.append(current)
        current = BaseException.__context__.__get__(current, BaseException)
    if current is not None and not any(current is item for item in chain): state["truncated"] = True
    # First means first caught at OUR boundary, not a reconstructed chronology
    # inside the unchanged reader. Context objects are separate observations;
    # their own original-comparison proof may carry fields, never an inferred
    # outer role/phase or a claim that they were the historical root cause.
    for item in chain:
        fact = _fact(item, graph, phase, role, ordinal) if item is error else _fact(item, graph, "unknown", "unknown", None)
        if item is not error: fact = {**fact, "exception_context_observation": True}
        if state["first"] is None: state["first"] = fact
        elif len(state["later"]) < MAX_FAILURES: state["later"].append(fact)
        else: state["truncated"] = True
        if len(state["errors"]) < MAX_FAILURES: state["errors"].append(item)


def _close_reads(items, graph, state, phase):
    closed = []
    for role, ordinal, item in reversed(items):
        try: item.close(); closed.append((role, ordinal, item))
        except BaseException as error: _remember(state, error, graph, phase, role, ordinal)
    return closed


def _after_reads(items, graph, state, phase):
    for role, ordinal, item in items:
        if item.failed: continue
        try: item.after_close()
        except BaseException as error: _remember(state, error, graph, phase, role, ordinal)


def _code_window(graph, committed, clock, head, remote, state, name, initial=None):
    items = []; rows = []; phase = "initial_code" if name == "initial" else "terminal_code"
    before = state["first"]
    try:
        _guard(clock, head, remote)
        for ordinal, (path, raw, digest) in enumerate(committed, 1):
            try:
                item = graph.reader._Read(ROOT / path, MAX_CODE_BYTES, clock, minimum=0,
                    component=("code", ordinal) if ordinal <= 4 else None)
                items.append(("code", ordinal, item))
                require(item.raw == raw and item.digest == digest
                    and item.raw == _git(clock, "show", head + ":" + path), "code_changed")
                if initial is not None: require(item.original == initial[ordinal - 1][1], "code_changed")
                rows.append((path, item.original, item.root_original, tuple(row[3] for row in item.directories)))
            except BaseException as error:
                _remember(state, error, graph, phase, "code", ordinal); break
        for role, ordinal, item in items:
            try: item.audit()
            except BaseException as error: _remember(state, error, graph, phase, role, ordinal)
    except BaseException as error: _remember(state, error, graph, phase)
    finally:
        _close_reads(items, graph, state, phase)
    _after_reads(items, graph, state, phase)
    if state["first"] is not before or state["first"] is not None: raise CodeSnapshotRefusal("window_failed")
    _guard(clock, head, remote); clock.check()
    window = tuple(rows)
    receipt = window, graph, committed, name, sys._getframe(), object()
    _WINDOWS[id(window)] = receipt
    return window


class CodeSnapshot:
    __slots__ = ("_anchor",)
    def __init__(self): raise CodeSnapshotRefusal("snapshot_factory")
    def _record(self):
        try:
            require(id(self) not in _SNAPSHOT_FAILED, "snapshot_failed")
            row = _SNAPSHOTS.get(id(self))
            require(type(self) is CodeSnapshot and type(row) is tuple and len(row) == 8
                and row[0] is self and self._anchor is row, "snapshot_factory")
            frame = row[7]
            require(frame.f_code is _issue_snapshot.__code__ and frame.f_globals is globals()
                and frame.f_locals.get("snapshot") is self and frame.f_locals.get("row") is row
                and frame.f_locals.get("graph") is row[1] and frame.f_locals.get("committed") is row[2]
                and frame.f_locals.get("window") is row[3] and frame.f_locals.get("clock") is row[5], "snapshot_factory")
            witness = _WINDOWS.get(id(row[3]))
            require(witness is row[4] and witness[0] is row[3] and witness[1] is row[1]
                and witness[2] is row[2] and witness[3] == "initial"
                and witness[4].f_code is _code_window.__code__ and witness[4].f_globals is globals()
                and witness[4].f_locals.get("receipt") is witness and witness[4].f_locals.get("clock") is row[5]
                and witness[4].f_locals.get("window") is row[3],
                "snapshot_factory")
            row[5].check(); row[1].original_validate(row[1]); return row
        except BaseException:
            if type(self) is CodeSnapshot and id(self) in _SNAPSHOTS: _SNAPSHOT_FAILED.add(id(self))
            raise


def _issue_snapshot(graph, committed, window, clock, root_pin):
    witness = _WINDOWS.get(id(window)); caller = sys._getframe(1)
    require(type(witness) is tuple and witness[0] is window and witness[1] is graph
        and witness[2] is committed and witness[3] == "initial"
        and witness[4].f_code is _code_window.__code__ and witness[4].f_globals is globals()
        and witness[4].f_locals.get("receipt") is witness and witness[4].f_locals.get("clock") is clock
        and caller.f_code is inspect_registered.__code__ and caller.f_globals is globals()
        and caller.f_locals.get("initial") is window and caller.f_locals.get("graph") is graph
        and caller.f_locals.get("committed") is committed and caller.f_locals.get("clock") is clock,
        "snapshot_factory")
    snapshot = object.__new__(CodeSnapshot)
    row = snapshot, graph, committed, window, witness, clock, root_pin, sys._getframe()
    snapshot._anchor = row; _SNAPSHOTS[id(snapshot)] = row; snapshot._record()
    return snapshot


def _inspect_sources(snapshot, clock, state):
    row = snapshot._record(); graph = row[1]; items = []; blobs = {}; inspected = None
    try:
        for role, rel, size, digest in INPUTS:
            try:
                snapshot._record()
                item = graph.reader._Read(USB / rel, size, clock, component=(role, None))
                items.append((role, None, item))
                require(len(item.raw) == size and item.digest == digest, "input_changed")
                blobs[role] = item.raw
            except BaseException as error:
                _remember(state, error, graph, "source_open", role); break
        if state["first"] is None:
            try:
                snapshot._record(); report = graph.model.inspect_registered_pair(**blobs)
                inspected = _hash(report.to_payload()), _hash(graph.model.inspection_policy())
                clock.check(); snapshot._record()
            except BaseException as error: _remember(state, error, graph, "model")
        for role, unused, item in items:
            try: item.audit()
            except BaseException as error: _remember(state, error, graph, "source_audit", role)
    finally:
        _close_reads(items, graph, state, "source_close")
    _after_reads(items, graph, state, "source_after_close")
    if state["first"] is not None: raise CodeSnapshotRefusal("window_failed")
    snapshot._record(); clock.check()
    return inspected, tuple(item.original for unused, unused2, item in items)


def inspect_registered(head, remote):
    """One five-code profile; ONLY exact lane hashes are public inputs."""
    clock = _Clock(); state = {"first": None, "later": [], "truncated": False, "errors": []}
    graph = snapshot = result = None; phase = "bootstrap"
    try:
        require(not _RUNS, "attempt_spent"); _RUNS.append((clock, state, sys._getframe()))
        _registered(); clock.root = _root_pin(); _guard(clock, head, remote)
        committed = _committed_code(clock, head); graph = _new_graph(committed, clock, state); clock.graph = clock.runtime = graph
        phase = "initial_code"; initial = _code_window(graph, committed, clock, head, remote, state, "initial")
        snapshot = _issue_snapshot(graph, committed, initial, clock, clock.root)
        phase = "source_open"; inspected, source_stamps = _inspect_sources(snapshot, clock, state)
        phase = "terminal_code"; terminal = _code_window(graph, committed, clock, head, remote, state, "terminal", initial)
        phase = "final_guard"; snapshot._record(); _guard(clock, head, remote); clock.check()
        result = {"schema": "si-usb-code-window-observation-v1", "status": "closed_finite_code_windows_external_byte_inspection",
            "runtime_head": head, "matching_remote": remote, "profile_sha256": PROFILE_SHA256,
            "code_mapping_sha256": _hash({name: digest for name, unused, digest in committed}),
            "initial_code_file10_sha256": _hash([list(row[1]) for row in initial]),
            "terminal_code_file10_sha256": _hash([list(row[1]) for row in terminal]),
            "code_file_original10_equal": tuple(row[1] for row in initial) == tuple(row[1] for row in terminal),
            "initial_ancestor_observations_sha256": _hash([[list(row[2]), [list(value) for value in row[3]]] for row in initial]),
            "terminal_ancestor_observations_sha256": _hash([[list(row[2]), [list(value) for value in row[3]]] for row in terminal]),
            "continuous_shared_ancestor_timestamp_custody": False,
            "physical_root_identity_sha256": _hash(list(clock.root)),
            "source_original10_sha256": _hash([list(value) for value in source_stamps]),
            "inspection_report_sha256": inspected[0], "model_policy_sha256": inspected[1],
            "all_initial_code_contexts_closed": True, "all_source_contexts_closed": True,
            "all_terminal_code_contexts_closed": True, "executed_verified_RAM": True,
            "authority": authority()}
    except BaseException as error:
        _remember(state, error, graph, phase)
    finally:
        if snapshot is not None: _SNAPSHOT_FAILED.add(id(snapshot))
        if graph is not None:
            # Capture the original failure before namespace cleanup can mask it.
            try: graph.validate()
            except BaseException as error: _remember(state, error, graph, "namespace_cleanup")
            clock.graph = None
            try: graph.cleanup()
            except BaseException as error: _remember(state, error, graph, "namespace_cleanup")
    try:
        clock.check()
        if state["first"] is None:
            require(result is not None and result["code_file_original10_equal"] is True, "inspection_refused")
            result["observation_sha256"] = _hash(result)
            _canonical(result); clock.check(); return result
    except BaseException as error: _remember(state, error, None, "final_format")
    error = CodeSnapshotRefusal("inspection_refused")
    payload = {"schema": "si-usb-code-window-refusal-v1", "status": "refused_finite_code_window_inspection",
        "failure_ordering": "first_caught_at_owned_boundary_contexts_are_observations",
        "first_failure": state["first"], "cleanup_failures": state["later"],
        "later_failures_truncated": state["truncated"], "authority": authority()}
    negative = error, _canonical(payload), state, sys._getframe()
    _NEGATIVES[id(error)] = negative
    raise error


def failure_summary(error):
    record = _NEGATIVES.get(id(error))
    if (type(record) is tuple and len(record) == 4 and record[0] is error
            and record[3].f_code is inspect_registered.__code__ and record[3].f_globals is globals()
            and record[3].f_locals.get("error") is error and record[3].f_locals.get("negative") is record
            and record[3].f_locals.get("state") is record[2]):
        return json.loads(record[1])
    return {"schema": "si-usb-code-window-refusal-v1", "status": "refused_finite_code_window_inspection",
        "failure_ordering": "first_caught_at_owned_boundary_contexts_are_observations",
        "first_failure": {"phase": "bootstrap", "role": "unknown", "code_ordinal": None,
            "code": None, "original_comparison": None, "actor": "unknown"},
        "cleanup_failures": [], "later_failures_truncated": False, "authority": authority()}


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        require(len(args) == 2, "arguments")
        result = inspect_registered(*args)
        print(_canonical(result).decode(), flush=True); return 0
    except BaseException as error:
        print(_canonical(failure_summary(error)).decode(), flush=True); return 2


if __name__ == "__main__":
    raise SystemExit(main())
