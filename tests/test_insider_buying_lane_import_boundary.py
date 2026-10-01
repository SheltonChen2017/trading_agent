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
