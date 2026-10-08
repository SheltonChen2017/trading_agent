"""Lane-local import-boundary checks for the Insider Buying research lane.

Section 119 (Claude review). The offline package guard scans the direct
imports of ``research/insider_buying/*.py`` only, and module hygiene does not
scan ``research/``. These checks pin three boundaries no other test names: the
two QuantConnect entry files stay self-contained, the offline package never
reaches them, and importing the whole package never loads a network-capable
lane runner. They read source text and run fresh interpreters; no SEC or
QuantConnect request is made.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
QC_FILES = (
    "insider_buying_qc_order_algorithm.py",
    "insider_buying_qc_stock_order_study.py",
)
_QC_ALLOWED_ROOTS = frozenset({
    "__future__", "AlgorithmImports", "datetime", "decimal", "hashlib", "json",
    "math", "re", "typing",
})
_NETWORK_ROOTS = ("http", "socket", "ssl", "urllib.request", "subprocess")


def _imports(path: Path) -> set[str]:
    """Every imported module name, including ``from package import module``."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{path.name} uses a relative import"
            module = node.module or ""
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return names


def _under(name: str, root: str) -> bool:
    return name == root or name.startswith(root + ".")


def _network_capable_lane_modules() -> tuple[str, ...]:
    found = []
    for path in sorted(RESEARCH.glob("insider_buying_*.py")):
        if any(_under(name, root) for name in _imports(path) for root in _NETWORK_ROOTS):
            found.append(f"research.{path.stem}")
    return tuple(found)


def test_qc_entry_files_import_only_the_lean_entry_point_and_stdlib() -> None:
    for name in QC_FILES:
        roots = {imported.split(".")[0] for imported in _imports(RESEARCH / name)}
        assert "AlgorithmImports" in roots
        assert roots <= _QC_ALLOWED_ROOTS, (name, sorted(roots - _QC_ALLOWED_ROOTS))


def test_offline_package_never_imports_a_qc_entry_file_or_lean() -> None:
    forbidden = ("AlgorithmImports", *(f"research.{name[:-3]}" for name in QC_FILES))
    for path in sorted((RESEARCH / "insider_buying").glob("*.py")):
        offending = sorted(
            name for name in _imports(path) if any(_under(name, root) for root in forbidden)
        )
        assert not offending, (path.name, offending)


def test_importing_the_whole_package_loads_no_network_capable_lane_module() -> None:
    runners = _network_capable_lane_modules()
    # The scan must really find the live SEC runners, or the check below is vacuous.
    assert "research.insider_buying_sec_all_form4_parent_campaign" in runners
    assert "research.insider_buying_sec_all_form4_parent_recovery_executor" in runners
    assert len(runners) >= 8
    blocked = (*runners, *(f"research.{name[:-3]}" for name in QC_FILES),
               "AlgorithmImports", "http.client", "socket", "ssl", "subprocess")
    load_package = (
        "import importlib, pkgutil, sys\n"
        "def deny_external(event, _args):\n"
        "    if event in {'socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system'}:\n"
        "        raise AssertionError('offline package import attempted external I/O: ' + event)\n"
        "sys.addaudithook(deny_external)\n"
        "try:\n"
        "    sys.audit('socket.connect', None, None)\n"
        "except AssertionError as exc:\n"
        "    assert 'offline package import attempted external I/O' in str(exc)\n"
        "else:\n"
        "    raise AssertionError('external-I/O audit hook did not fire')\n"
        "import research.insider_buying as p\n"
        "for m in pkgutil.iter_modules(p.__path__):\n"
        "    importlib.import_module('research.insider_buying.' + m.name)\n"
    )
    scan = (
        f"blocked = {blocked!r}\n"
        "print(','.join(sorted(n for n in sys.modules if n in blocked)))\n"
    )
    clean = subprocess.run(
        [sys.executable, "-B", "-c", load_package + scan],
        cwd=ROOT, capture_output=True, text=True, check=True, timeout=120,
    )
    assert clean.stdout.strip() == ""
    # Positive control: the same scan sees a runner once something imports it.
    control = subprocess.run(
        [sys.executable, "-B", "-c", load_package + f"import {runners[0]}\n" + scan],
        cwd=ROOT, capture_output=True, text=True, check=True, timeout=120,
    )
    assert runners[0] in control.stdout.strip().split(",")


# A bounded structural check, not a network sandbox: direct transport tests
# need an unconditional connection patch before their first transport reference.
# Aliased transports, dynamic patch targets and arbitrary helper control flow
# are not proven here. Run tests/mutants with process-tree network denial too.
# Kept at module level so the scan below does not flag its own control sample.
_UNSAFE_SAMPLE = "def test_unsafe(tmp_path):\n    run(plan, tmp_path, runner._sec_transport)\n"
_MISLEADING_TRIPWIRE_SAMPLES = (
    "    # HTTPSConnection is not patched\n",
    '    "HTTPSConnection is not patched"\n',
    "    _fake_https_wire\n",
    "    if False:\n        monkeypatch.setattr('http.client.HTTPSConnection', forbidden)\n",
    "    def unused():\n        monkeypatch.setattr('http.client.HTTPSConnection', forbidden)\n",
    "    monkeypatch.setattr(other, 'HTTPSConnection', forbidden)\n",
)


@pytest.mark.parametrize("marker", _MISLEADING_TRIPWIRE_SAMPLES)
def test_tripwire_scan_rejects_nonblocking_markers(marker: str) -> None:
    source = "def test_unsafe(tmp_path, monkeypatch):\n" + marker + (
        "    run(plan, tmp_path, runner._sec_transport)\n"
    )
    assert _real_transport_tests_without_tripwire({"invented.py": source}) == (
        1, ["invented.py::test_unsafe"],
    )


def test_tripwire_scan_rejects_a_patch_after_transport_use() -> None:
    source = _UNSAFE_SAMPLE + (
        "    monkeypatch.setattr('http.client.HTTPSConnection', forbidden)\n"
    )
    assert _real_transport_tests_without_tripwire({"invented.py": source}) == (
        1, ["invented.py::test_unsafe"],
    )


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted_name(node.value) + "." + node.attr
    return ""


def _statement_call(statement: ast.stmt) -> ast.Call | None:
    if isinstance(statement, (ast.Expr, ast.Assign, ast.AnnAssign)):
        value = statement.value
        if isinstance(value, ast.Call):
            return value
    return None


def _connection_patch(statement: ast.stmt) -> bool:
    call = _statement_call(statement)
    if call is None or _dotted_name(call.func) != "monkeypatch.setattr":
        return False
    args = call.args
    if len(args) == 2:
        return isinstance(args[0], ast.Constant) and args[0].value in _CONNECTION_SEAMS
    if len(args) == 3:
        target = _dotted_name(args[0])
        if ((target == "http.client" or target.endswith(".http.client"))
                and isinstance(args[1], ast.Constant) and args[1].value == "HTTPSConnection"):
            return True
        # Section 153 (Claude review): the provider and earnings transports open
        # through urllib; patching the opener factory is their connection patch.
        return (
            (target == "urllib.request" or target.endswith(".request"))
            and isinstance(args[1], ast.Constant) and args[1].value == "build_opener"
        )
    return False


_CONNECTION_SEAMS = frozenset({"http.client.HTTPSConnection", "urllib.request.build_opener"})
# Section 153 (Claude review): the urllib-based provider and earnings transports
# share the `_default_transport` name; a test that reaches them is a direct test.
_TRANSPORT_NAMES = frozenset({"_sec_transport", "_selected_sec_transport", "_default_transport"})


def _touches_real_transport(statement: ast.stmt) -> bool:
    for node in ast.walk(statement):
        if isinstance(node, ast.Attribute) and node.attr in _TRANSPORT_NAMES:
            return True
        # Section 127 (Claude review): a transport imported by its bare name
        # is the same object as the attribute form.
        if isinstance(node, ast.Name) and node.id in _TRANSPORT_NAMES:
            return True
        if isinstance(node, ast.Call) and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == "_fetch_sec")
            or (isinstance(node.func, ast.Name) and node.func.id == "_fetch_sec")
        ):
            return True
    return False


def _wire_helper_patches(tree: ast.Module) -> bool:
    helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_fake_https_wire"]
    if len(helpers) != 1:
        return False
    for stmt in helpers[0].body:
        if _connection_patch(stmt):
            return True
        if isinstance(stmt, (ast.Return, ast.Raise, ast.If, ast.For, ast.While, ast.Try, ast.With, ast.Match)):
            return False
    return False


def _real_transport_tests_without_tripwire(sources: dict[str, str]) -> tuple[int, list[str]]:
    seen, offenders = 0, []
    for name, text in sorted(sources.items()):
        tree = ast.parse(text)
        # Only this existing, source-audited helper shape is recognized. Merely
        # mentioning its name, or replacing its patch with a comment, is not.
        wire_patches = _wire_helper_patches(tree)
        for node in ast.walk(tree):
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name.startswith("test_")):
                patched = False
                for stmt in node.body:
                    if _touches_real_transport(stmt):
                        seen += 1
                        if not patched:
                            offenders.append(f"{name}::{node.name}")
                        break
                    call = _statement_call(stmt)
                    if call is not None and _dotted_name(call.func) == "monkeypatch.undo":
                        # Undoing every patch restores the real connection.
                        patched = False
                        continue
                    if _connection_patch(stmt) or (
                        wire_patches and call is not None
                        and isinstance(call.func, ast.Name) and call.func.id == "_fake_https_wire"
                        and call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "monkeypatch"
                    ):
                        patched = True
    return seen, offenders


def test_direct_sec_transport_tests_install_a_connection_patch_before_use() -> None:
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in (ROOT / "tests").glob("test_insider_buying*.py")
    }
    seen, offenders = _real_transport_tests_without_tripwire(sources)
    assert seen >= 15  # the scan must really find the transport tests
    assert offenders == []
    # Positive control: the same scan flags a test without a tripwire.
    assert _real_transport_tests_without_tripwire({"invented.py": _UNSAFE_SAMPLE}) == (
        1, ["invented.py::test_unsafe"],
    )


@pytest.mark.parametrize("patch", (
    "    monkeypatch.setattr('http.client.HTTPSConnection', forbidden)\n",
    "    monkeypatch.setattr(runner.http.client, 'HTTPSConnection', forbidden)\n",
))
def test_tripwire_scan_accepts_an_executable_connection_patch(patch: str) -> None:
    source = "def test_safe(tmp_path, monkeypatch):\n" + patch + (
        "    run(plan, tmp_path, runner._sec_transport)\n"
    )
    assert _real_transport_tests_without_tripwire({"invented.py": source}) == (1, [])


@pytest.mark.parametrize("helper_patch,prefix,offending", (
    (True, "", []),
    (False, "", ["invented.py::test_safe"]),
    (True, "    return\n", ["invented.py::test_safe"]),
    (True, "    if wire:\n        return\n", ["invented.py::test_safe"]),
))
def test_tripwire_scan_checks_the_called_wire_helper_body(
    helper_patch: bool, prefix: str, offending: list[str],
) -> None:
    helper = "def _fake_https_wire(monkeypatch, wire):\n" + prefix + (
        "    monkeypatch.setattr(runner.http.client, 'HTTPSConnection', Connection)\n"
        if helper_patch else "    pass  # HTTPSConnection is not patched\n"
    )
    source = helper + (
        "def test_safe(tmp_path, monkeypatch):\n"
        "    state = _fake_https_wire(monkeypatch, b'')\n"
        "    run(plan, tmp_path, runner._sec_transport)\n"
    )
    assert _real_transport_tests_without_tripwire({"invented.py": source}) == (1, offending)


# Section 127 (Claude review). Controls for scanner rules that no earlier case
# reached on its own, and for three forms the scanner did not see: a transport
# imported by bare name, monkeypatch.undo() between the patch and the use, and
# an async test. Each sample must be flagged.
_PATCHED_WIRE_HELPER = (
    "def _fake_https_wire(monkeypatch, wire):\n"
    "    monkeypatch.setattr(runner.http.client, 'HTTPSConnection', Connection)\n"
)
_USE = "    run(plan, tmp_path, runner._sec_transport)\n"


@pytest.mark.parametrize("source", (
    # A patch of some other name, attribute or object is not a connection patch.
    "def test_unsafe(tmp_path, monkeypatch):\n    monkeypatch.setattr('other.module.Connection', forbidden)\n" + _USE,
    "def test_unsafe(tmp_path, monkeypatch):\n    monkeypatch.setattr(runner.http.client, 'HTTPConnection', forbidden)\n" + _USE,
    "def test_unsafe(tmp_path, monkeypatch):\n    print('http.client.HTTPSConnection', forbidden)\n" + _USE,
    "def test_unsafe(tmp_path, monkeypatch):\n    other.setattr(runner.http.client, 'HTTPSConnection', forbidden)\n" + _USE,
    # The wire helper must be the one called, with the test's monkeypatch.
    _PATCHED_WIRE_HELPER + "def test_unsafe(tmp_path, monkeypatch):\n    state = _fake_https_wire(other, b'')\n" + _USE,
    _PATCHED_WIRE_HELPER + "def test_unsafe(tmp_path, monkeypatch):\n    state = unrelated(monkeypatch, b'')\n" + _USE,
    # A second definition replaces the audited helper.
    _PATCHED_WIRE_HELPER + "def _fake_https_wire(monkeypatch, wire):\n    pass\n"
    + "def test_unsafe(tmp_path, monkeypatch):\n    state = _fake_https_wire(monkeypatch, b'')\n" + _USE,
    # The first pilot transport is called, not passed.
    "def test_unsafe(tmp_path):\n    pilot._fetch_sec('/Archives/invented', 'agent')\n",
    # Bare-name imports of a transport.
    "def test_unsafe(tmp_path):\n    run(plan, tmp_path, _sec_transport)\n",
    "def test_unsafe(tmp_path):\n    run(plan, tmp_path, _selected_sec_transport)\n",
    "def test_unsafe(tmp_path):\n    _fetch_sec('/Archives/invented', 'agent')\n",
    # Undoing the patch before the transport is used.
    "def test_unsafe(tmp_path, monkeypatch):\n    monkeypatch.setattr('http.client.HTTPSConnection', forbidden)\n"
    "    monkeypatch.undo()\n" + _USE,
    # Async tests are tests too.
    "async def test_unsafe(tmp_path):\n" + _USE,
))
def test_tripwire_scan_flags_near_misses_and_unseen_forms(source: str) -> None:
    assert _real_transport_tests_without_tripwire({"invented.py": source}) == (
        1, ["invented.py::test_unsafe"],
    )


@pytest.mark.parametrize("source", (
    "def test_safe(tmp_path, monkeypatch):\n    monkeypatch.setattr('http.client.HTTPSConnection', forbidden)\n"
    "    run(plan, tmp_path, _sec_transport)\n",
    "def test_safe(tmp_path, monkeypatch):\n    monkeypatch.undo()\n"
    "    monkeypatch.setattr('http.client.HTTPSConnection', forbidden)\n" + _USE,
    "async def test_safe(tmp_path, monkeypatch):\n    monkeypatch.setattr('http.client.HTTPSConnection', forbidden)\n" + _USE,
))
def test_tripwire_scan_still_accepts_a_patch_in_the_new_forms(source: str) -> None:
    assert _real_transport_tests_without_tripwire({"invented.py": source}) == (1, [])


# Section 153 (Claude review): the urllib transports are direct transports too.
_URLLIB_USE = "    m._default_transport(item)\n"


@pytest.mark.parametrize("source", (
    "def test_unsafe(tmp_path):\n" + _URLLIB_USE,
    "def test_unsafe(tmp_path):\n    _default_transport(item)\n",
    # Patching urlopen does not reach an opener built by build_opener.
    "def test_unsafe(monkeypatch):\n    monkeypatch.setattr(m.request, 'urlopen', opener)\n" + _URLLIB_USE,
    "def test_unsafe(monkeypatch):\n    monkeypatch.setattr(m.other, 'build_opener', opener)\n" + _URLLIB_USE,
    "def test_unsafe(monkeypatch):\n" + _URLLIB_USE + "    monkeypatch.setattr(m.request, 'build_opener', opener)\n",
))
def test_tripwire_scan_flags_an_unpatched_urllib_transport(source: str) -> None:
    assert _real_transport_tests_without_tripwire({"invented.py": source}) == (
        1, ["invented.py::test_unsafe"],
    )


@pytest.mark.parametrize("source", (
    "def test_safe(monkeypatch):\n    monkeypatch.setattr(m.request, 'build_opener', opener)\n" + _URLLIB_USE,
    "def test_safe(monkeypatch):\n    monkeypatch.setattr(urllib.request, 'build_opener', opener)\n" + _URLLIB_USE,
    "def test_safe(monkeypatch):\n    monkeypatch.setattr('urllib.request.build_opener', opener)\n" + _URLLIB_USE,
))
def test_tripwire_scan_accepts_an_opener_patch_before_a_urllib_transport(source: str) -> None:
    assert _real_transport_tests_without_tripwire({"invented.py": source}) == (1, [])
