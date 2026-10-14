"""The lane's tooling must never import the production dispatch fence.

Section 301 (`ARV2R301-010`). The shared `tests/conftest.py` imports
`assistant.dispatch_fence` in an autouse fixture for every test, so the former
check `"assistant.dispatch_fence" not in sys.modules` was false under the
repository's standard pytest invocation and true only under `--noconftest`.
This helper checks what that assertion was meant to prove, independently of
what the test harness itself imported: no lane module loaded by the test
process reaches the fence through its static import closure inside this
repository. Imports anywhere in a file count, including function-level ones,
so the check is at least as strict as the former import-time observation.
"""
from __future__ import annotations

import ast
import functools
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
FENCE = "assistant.dispatch_fence"
LANE_PREFIXES = ("scripts.", "research.analyst_revisions_v2")


def _file(name):
    """Repository source for a module name, or None outside the repository."""
    base = ROOT.joinpath(*name.split("."))
    for path in (base.with_suffix(".py"), base / "__init__.py"):
        if path.is_file() and "tests" not in path.relative_to(ROOT).parts[:1]:
            return path
    return None


@functools.lru_cache(maxsize=None)
def _imports(name):
    path = _file(name)
    if path is None:
        return frozenset()
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), str(path))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[:len(parts) - node.level + 1]) if node.level <= len(parts) else ""
                module = ".".join(part for part in (base, node.module or "") if part)
            else:
                module = node.module or ""
            found.add(module)
            found.update(f"{module}.{alias.name}" for alias in node.names if alias.name != "*")
    return frozenset(found)


def fence_path(start_names):
    """Return one import chain from `start_names` to the fence, or None."""
    seen, stack = set(), [(name, (name,)) for name in sorted(start_names)]
    while stack:
        name, chain = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        for imported in _imports(name):
            if imported == FENCE or imported.startswith(FENCE + "."):
                return chain + (imported,)
            if _file(imported) is not None and imported not in seen:
                stack.append((imported, chain + (imported,)))
    return None


def lane_modules():
    return frozenset(name for name in tuple(sys.modules)
                     if name.startswith(LANE_PREFIXES) and _file(name) is not None)


def assert_lane_closure_excludes_dispatch_fence():
    chain = fence_path(lane_modules())
    assert chain is None, "lane import closure reaches the dispatch fence: " + " -> ".join(chain)
