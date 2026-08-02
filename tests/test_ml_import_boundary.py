"""Import-boundary regression test for the ML observation layer.

Mirrors tests/test_committee_foundation.py's
test_llm_package_has_no_direct_execution_or_proposal_authority_imports --
same AST-walk shape, opposite direction: nothing under execution/,
risk/execution_gate.py, assistant/execution_service.py, or
assistant/allocation_batch.py may import `ml` (strategy doc section 3.1:
"no module under execution/ or risk/execution_gate.py may import ml").
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_CHECKED_PATHS = (
    REPO_ROOT / "execution",
    REPO_ROOT / "risk" / "execution_gate.py",
    REPO_ROOT / "assistant" / "execution_service.py",
    REPO_ROOT / "assistant" / "allocation_batch.py",
)


def _python_files():
    for path in _CHECKED_PATHS:
        if path.is_dir():
            yield from path.rglob("*.py")
        elif path.exists():
            yield path


def test_no_execution_capable_module_imports_ml():
    offenders = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name == "ml" or name.startswith("ml."):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {name}")
    assert not offenders, offenders


def test_assistant_package_has_no_ml_import_except_the_future_shadow_adapter():
    """Strategy doc 3.1: 'the initial implementation must not add an ml
    import anywhere under assistant/ except a future, separately reviewed
    shadow-observation adapter.' No such adapter exists yet -- this pins
    the current state to zero, not to a fixed allowlist that could quietly
    grow permissive as new assistant/ files are added."""
    offenders = []
    for path in (REPO_ROOT / "assistant").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name == "ml" or name.startswith("ml."):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {name}")
    assert not offenders, (
        f"assistant/ imports ml with no reviewed shadow adapter yet: {offenders}"
    )


def _module_name(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _internal_import_graph() -> tuple[dict[str, set[str]], list[str]]:
    """Map every non-test first-party module to the modules it imports.

    Returns the graph plus any import forms this walker cannot resolve.
    Unresolvable forms are returned rather than skipped: a boundary test
    that silently stops seeing part of the codebase is worse than one that
    refuses, because it keeps reporting success while going blind.
    """
    graph: dict[str, set[str]] = {}
    unresolved: list[str] = []
    for path in REPO_ROOT.rglob("*.py"):
        parts = path.relative_to(REPO_ROOT).parts
        if parts[0] in {"tests", ".git", "__pycache__", ".pytest_cache"}:
            continue
        if "__pycache__" in parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):  # pragma: no cover - unreadable file
            continue
        dependencies: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                dependencies.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    # Relative imports are not resolved to absolute module
                    # names here. There are currently none in non-test code,
                    # so this costs nothing today -- but the first one
                    # written must break this test rather than quietly
                    # become an edge the walker cannot follow.
                    unresolved.append(
                        f"{_module_name(path)}: relative import "
                        f"(level={node.level}, module={node.module!r})"
                    )
                    continue
                if not node.module:
                    continue
                dependencies.add(node.module)
                # `from data import helper` binds a submodule, not just the
                # package. Recording only `data` loses the edge that
                # actually carries the dependency, which would make this
                # whole test pass while an indirect path existed.
                dependencies.update(
                    f"{node.module}.{alias.name}" for alias in node.names
                )
            elif isinstance(node, ast.Call):
                # importlib.import_module("ml.x") is an edge no static walk
                # can follow. Flag the call site instead of pretending the
                # graph is complete.
                function = node.func
                name = getattr(function, "attr", None) or getattr(
                    function, "id", None
                )
                if name in {"import_module", "__import__"}:
                    unresolved.append(
                        f"{_module_name(path)}: dynamic import via {name}()"
                    )
        graph[_module_name(path)] = dependencies
    return graph, unresolved


def test_no_execution_capable_module_reaches_ml_transitively():
    """CLAUDE.md section 4: a green direct-import test is not proof.

    The two tests above walk one file's own import statements. They cannot
    see `assistant -> some_helper -> ml`, which would satisfy them while
    breaking the boundary they exist to protect. This walks the reachable
    first-party import graph from every execution-capable root and reports
    the offending chain, so a future indirect dependency fails loudly
    instead of silently.
    """
    graph, unresolved = _internal_import_graph()
    assert not unresolved, (
        "this test cannot follow these import forms, so it can no longer "
        "prove the boundary holds -- resolve them or teach the walker: "
        + "; ".join(sorted(unresolved))
    )
    roots = sorted(
        name
        for name in graph
        if name.split(".")[0] in {"assistant", "execution", "risk"}
    )
    assert roots, "expected to discover execution-capable modules to check"

    offending_chains: list[str] = []
    for root in roots:
        seen = {root}
        stack = [(root, (root,))]
        while stack:
            current, chain = stack.pop()
            for dependency in sorted(graph.get(current, ())):
                if dependency == "ml" or dependency.startswith("ml."):
                    offending_chains.append(" -> ".join(chain + (dependency,)))
                    continue
                if dependency in graph and dependency not in seen:
                    seen.add(dependency)
                    stack.append((dependency, chain + (dependency,)))

    assert not offending_chains, (
        "execution-capable code reaches ml through an indirect import: "
        + "; ".join(sorted(offending_chains))
    )
