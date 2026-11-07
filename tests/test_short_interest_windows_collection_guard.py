"""Every lane test module must be collectable on the supported Windows host.

Static, so it also fails on macOS, where a missing guard is otherwise invisible:
twice a Mac-authored round added modules whose runtime imports `resource` or
`fcntl` at import time, and each one aborted Windows collection (lane record
SI-CR18-001, SI-CR26-001, SI-CR29-001). Only the import graph is read.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSIX_ONLY = frozenset(("resource", "fcntl", "pwd", "grp", "termios"))
_PARSED = {}


def _targets(node):
    """Import targets of one statement; lazy imports inside functions cannot break collection."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
    return []


def _module_file(name):
    path = ROOT.joinpath(*name.split("."))
    for candidate in (path.with_suffix(".py"), path / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _module_targets(path):
    if path not in _PARSED:
        _PARSED[path] = [name for node in ast.parse(path.read_bytes()).body for name in _targets(node)]
    return _PARSED[path]


def _reaches_posix_only(names, seen):
    for name in names:
        if name.split(".")[0] in POSIX_ONLY:
            return True
        target = _module_file(name)
        if target is not None and target not in seen:
            seen.add(target)
            if _reaches_posix_only(_module_targets(target), seen):
                return True
    return False


def _collection_is_safe(tree):
    """No module-level import reaches a POSIX-only module before importorskip has run."""
    for node in tree.body:
        if _reaches_posix_only(_targets(node), set()):
            return False
        call = node.value if isinstance(node, (ast.Expr, ast.Assign)) else None
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "importorskip" and call.args
                and isinstance(call.args[0], ast.Constant) and call.args[0].value in POSIX_ONLY):
            return True
    return True


def test_every_lane_test_reaching_a_posix_only_module_guards_collection():
    unguarded = [path.name for path in sorted((ROOT / "tests").glob("test_short_interest_*.py"))
        if not _collection_is_safe(ast.parse(path.read_bytes()))]
    assert unguarded == [], "add pytest.importorskip before the first scripts import: " + ", ".join(unguarded)


def test_guard_check_detects_a_missing_guard_and_accepts_a_present_one():
    # Failure direction of the check itself, using the same parser on fabricated source.
    recovery = "from scripts import capture_short_interest_count_recovery as r\n"
    immutable = "from scripts import short_interest_immutable_metadata as r\n"
    assert not _collection_is_safe(ast.parse("import pytest\n" + recovery))
    assert not _collection_is_safe(ast.parse("import fcntl\nimport pytest\n"))
    assert not _collection_is_safe(ast.parse("import pytest\n" + immutable + 'pytest.importorskip("fcntl")\n'))
    assert _collection_is_safe(ast.parse('import pytest\npytest.importorskip("resource")\n' + recovery))
    assert _collection_is_safe(ast.parse('import pytest\nfcntl = pytest.importorskip("fcntl")\n' + immutable))
    assert _collection_is_safe(ast.parse("import pytest\nfrom data.hashing import hash_bytes\n"))
