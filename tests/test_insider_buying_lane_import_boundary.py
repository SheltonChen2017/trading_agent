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
import re
import subprocess
import sys
from pathlib import Path


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


# Section 124 (Claude review). A test that hands a real SEC transport object to
# a runner, or calls one directly, exists to prove a guard stops it. If that
# guard regresses, or a mutation run disables it, the test must fail at a
# mocked connection rather than contact the SEC. The scan covers test
# functions only; a transport passed through a module-level helper is not seen.
_REAL_TRANSPORT = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_.]*\._(?:selected_)?sec_transport\b"
    r"|\b[A-Za-z_][A-Za-z0-9_.]*\._fetch_sec\("
)
_CONNECTION_TRIPWIRE = re.compile(r"HTTPSConnection|_fake_https_wire")
# Kept at module level so the scan below does not flag its own control sample.
_UNSAFE_SAMPLE = "def test_unsafe(tmp_path):\n    run(plan, tmp_path, runner._sec_transport)\n"


def _real_transport_tests_without_tripwire(sources: dict[str, str]) -> tuple[int, list[str]]:
    seen, offenders = 0, []
    for name, text in sorted(sources.items()):
        lines = text.split("\n")
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                body = "\n".join(lines[node.lineno - 1:node.end_lineno])
                if _REAL_TRANSPORT.search(body):
                    seen += 1
                    if not _CONNECTION_TRIPWIRE.search(body):
                        offenders.append(f"{name}::{node.name}")
    return seen, offenders


def test_every_test_touching_a_real_sec_transport_blocks_the_connection() -> None:
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
