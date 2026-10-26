"""The lane's tooling must never import the production dispatch fence.

Section 301 (`ARV2R301-010`). The shared `tests/conftest.py` imports
`assistant.dispatch_fence` in an autouse fixture for every test, so the former
check `"assistant.dispatch_fence" not in sys.modules` was false under the
repository's standard pytest invocation and true only under `--noconftest`.
This helper checks the static import closure of lane modules loaded by the
test process, including implicit package initializers and function-level
imports. This is not equivalent to the former runtime observation: dynamic
imports and external-package internals are outside the static graph. Retain
the runtime absence check when the shared conftest is not loaded. Under the
shared harness, fence coexistence is allowed and no attribution of dynamic
imports is claimed. Neither check is an execution sandbox.
"""
from __future__ import annotations

import ast
import functools
from pathlib import Path
import sys
from types import ModuleType

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


def _imports(name):
    path = _file(name)
    if path is None:
        return frozenset()
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    return _parse_imports(package, str(path), path.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=512)
def _parse_imports(package, filename, source):
    """Cache parsed content, never a mutable module-name-to-source mapping."""
    found = set()
    for node in ast.walk(ast.parse(source, filename)):
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


def _package_initializers(name):
    parts = name.split(".")
    for end in range(1, len(parts)):
        parent = ".".join(parts[:end])
        path = _file(parent)
        if path is not None and path.name == "__init__.py":
            yield parent


def fence_path(start_names):
    """Return one import chain from `start_names` to the fence, or None."""
    seen, stack = set(), [(name, (name,)) for name in sorted(start_names)]
    while stack:
        name, chain = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        if name == FENCE or name.startswith(FENCE + "."):
            return chain
        for imported in sorted(_imports(name) | frozenset(_package_initializers(name))):
            if imported == FENCE or imported.startswith(FENCE + "."):
                return chain + (imported,)
            # Even an external/missing leaf can execute a local parent package.
            if imported and imported not in seen:
                stack.append((imported, chain + (imported,)))
    return None


def lane_modules():
    return frozenset(name for name in tuple(sys.modules)
                     if name.startswith(LANE_PREFIXES) and _file(name) is not None)


def assert_lane_closure_excludes_dispatch_fence():
    shared_harness = ROOT / "tests" / "conftest.py"
    harness_loaded = any(
        isinstance(module := sys.modules.get(name), ModuleType)
        and vars(module).get("__file__") == str(shared_harness)
        for name in ("conftest", "tests.conftest")
    )
    if not harness_loaded:
        assert FENCE not in sys.modules, "dispatch fence loaded without the shared test harness"
    chain = fence_path(lane_modules())
    assert chain is None, "lane import closure reaches the dispatch fence: " + " -> ".join(chain)
