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

# Only repository-owned source belongs in the first-party graph.  Walking the
# entire checkout also descends into .venv/site-packages and makes the result
# depend on whichever environment happens to be installed beside the source.
_FIRST_PARTY_PATHS = (
    REPO_ROOT / "assistant",
    REPO_ROOT / "backtest",
    REPO_ROOT / "data",
    REPO_ROOT / "execution",
    REPO_ROOT / "ml",
    REPO_ROOT / "risk",
    REPO_ROOT / "scripts",
    REPO_ROOT / "signals",
    REPO_ROOT / "strategies",
    REPO_ROOT / "baskets.py",
    REPO_ROOT / "config.py",
    REPO_ROOT / "market_analytics.py",
)

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


def _first_party_python_files():
    for path in _FIRST_PARTY_PATHS:
        if path.is_dir():
            yield from path.rglob("*.py")
        elif path.exists():
            yield path


def _absolute_from_import(path: Path, node: ast.ImportFrom) -> str | None:
    """Resolve one ImportFrom target using Python's relative-import rules."""
    if node.level == 0:
        return node.module
    module_parts = _module_name(path).split(".")
    package_parts = module_parts if path.name == "__init__.py" else module_parts[:-1]
    parents_to_remove = node.level - 1
    if parents_to_remove >= len(package_parts):
        return None
    base = package_parts[: len(package_parts) - parents_to_remove]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base) or None


def _internal_import_graph() -> tuple[dict[str, set[str]], list[str]]:
    """Map every non-test first-party module to the modules it imports.

    Returns the graph plus any import forms this walker cannot resolve.
    Unresolvable forms are returned rather than skipped: a boundary test
    that silently stops seeing part of the codebase is worse than one that
    refuses, because it keeps reporting success while going blind.
    """
    graph: dict[str, set[str]] = {}
    unresolved: list[str] = []
    for path in _first_party_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError) as exc:
            unresolved.append(f"{path.relative_to(REPO_ROOT)}: cannot parse: {exc}")
            continue
        dependencies: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                dependencies.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_from = _absolute_from_import(path, node)
                if imported_from is None:
                    unresolved.append(
                        f"{_module_name(path)}: invalid relative import "
                        f"(level={node.level}, module={node.module!r})"
                    )
                    continue
                dependencies.add(imported_from)
                # `from data import helper` binds a submodule, not just the
                # package. Recording only `data` loses the edge that
                # actually carries the dependency, which would make this
                # whole test pass while an indirect path existed.
                dependencies.update(
                    f"{imported_from}.{alias.name}" for alias in node.names
                    if alias.name != "*"
                )
            elif isinstance(node, ast.Call):
                # Literal dynamic imports are still statically knowable. For
                # a computed target, fail closed only if traversal reaches
                # this module; unrelated tooling must not invalidate the
                # execution boundary.
                function = node.func
                name = getattr(function, "attr", None) or getattr(
                    function, "id", None
                )
                if name in {"import_module", "__import__"}:
                    if (
                        node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                        and not node.args[0].value.startswith(".")
                    ):
                        dependencies.add(node.args[0].value)
                    else:
                        dependencies.add(f"<unresolved dynamic import via {name}()>")
        graph[_module_name(path)] = dependencies
    return graph, unresolved


def test_relative_imports_resolve_to_first_party_module_names():
    module_path = REPO_ROOT / "assistant" / "nested" / "worker.py"
    sibling = ast.parse("from .helper import build").body[0]
    parent = ast.parse("from ..shared import value").body[0]

    assert isinstance(sibling, ast.ImportFrom)
    assert isinstance(parent, ast.ImportFrom)
    assert _absolute_from_import(module_path, sibling) == "assistant.nested.helper"
    assert _absolute_from_import(module_path, parent) == "assistant.shared"


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
                if dependency.startswith("<unresolved "):
                    offending_chains.append(" -> ".join(chain + (dependency,)))
                    continue
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


def test_interactive_backtest_cannot_reach_authority_or_ml_transitively():
    """UI-3 is research-only across its full reachable dependency graph.

    A direct source check on ``backtest.interactive`` would miss a future
    ``interactive -> helper -> assistant/execution/risk/ml`` dependency.
    Walk the same fail-closed first-party graph used for the execution/ML
    boundary so an indirect authority path is rejected too.
    """
    graph, unresolved = _internal_import_graph()
    assert not unresolved, (
        "this test cannot follow these import forms, so it can no longer "
        "prove the UI-3 boundary holds -- resolve them or teach the walker: "
        + "; ".join(sorted(unresolved))
    )
    root = "backtest.interactive"
    assert root in graph, f"expected to discover {root} in the import graph"

    forbidden_roots = {"assistant", "execution", "risk", "ml"}
    offending_chains: list[str] = []
    seen = {root}
    stack = [(root, (root,))]
    while stack:
        current, chain = stack.pop()
        for dependency in sorted(graph.get(current, ())):
            if dependency.startswith("<unresolved "):
                offending_chains.append(" -> ".join(chain + (dependency,)))
                continue
            if dependency.split(".")[0] in forbidden_roots:
                offending_chains.append(" -> ".join(chain + (dependency,)))
                continue
            if dependency in graph and dependency not in seen:
                seen.add(dependency)
                stack.append((dependency, chain + (dependency,)))

    assert not offending_chains, (
        "interactive Backtest research code reaches authority or ML code "
        "through an indirect import: " + "; ".join(sorted(offending_chains))
    )


_PROPOSAL_GENERATION_MODULES = frozenset(
    {
        "assistant.proposals",
        "assistant.allocation_proposals",
        "assistant.strategy_proposals",
        "assistant.allocation_batch",
        "assistant.ai_advisor",
        "assistant.recommended_stocks",
    }
)


def _is_proposal_generation_module(module: str) -> bool:
    return any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for forbidden in _PROPOSAL_GENERATION_MODULES
    )


def _forbidden_dependency_chains(
    graph: dict[str, set[str]], roots: list[str]
) -> list[str]:
    """Return direct or transitive kernel paths into proposal generation."""
    offending: list[str] = []
    for root in roots:
        seen = {root}
        stack = [(root, (root,))]
        while stack:
            current, chain = stack.pop()
            for dependency in sorted(graph.get(current, ())):
                next_chain = chain + (dependency,)
                if dependency.startswith("<unresolved "):
                    offending.append(" -> ".join(next_chain))
                    continue
                if _is_proposal_generation_module(dependency):
                    offending.append(" -> ".join(next_chain))
                    continue
                if dependency in graph and dependency not in seen:
                    seen.add(dependency)
                    stack.append((dependency, next_chain))
    return offending


def test_kernel_boundary_walker_detects_indirect_and_submodule_imports():
    """Keep the guard itself from becoming a green but bypassable test."""
    graph = {
        "assistant.execution_kernel.submit": {"assistant.context_builder"},
        "assistant.context_builder": {"assistant.proposals.builders"},
    }
    assert _forbidden_dependency_chains(
        graph, ["assistant.execution_kernel.submit"]
    ) == [
        "assistant.execution_kernel.submit -> assistant.context_builder -> "
        "assistant.proposals.builders"
    ]


def test_execution_kernel_never_reaches_proposal_generation():
    """GR-1 section 6.2: the seams must be real.

    A kernel module that could import proposal generation would let the
    submission path reach back into the code that decides WHAT to trade.
    The kernel interprets and executes decisions; it must never make them.
    """
    graph, unresolved = _internal_import_graph()
    assert not unresolved, (
        "the execution-kernel boundary cannot be proved while imports are "
        "unresolved: " + "; ".join(sorted(unresolved))
    )
    roots = sorted(
        module
        for module in graph
        if module == "assistant.execution_kernel"
        or module.startswith("assistant.execution_kernel.")
    )
    assert roots, "expected assistant.execution_kernel modules to exist"
    offenders = _forbidden_dependency_chains(graph, roots)
    assert not offenders, (
        "execution kernel reaches proposal-generation code: "
        + "; ".join(sorted(offenders))
    )


def test_execution_kernel_modules_do_not_import_private_peer_names():
    """GR-1 section 6.2: kernel seams cannot depend on peer internals."""
    kernel_root = REPO_ROOT / "assistant" / "execution_kernel"
    offenders: list[str] = []
    for path in kernel_root.glob("*.py"):
        current_module = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            imported_from = _absolute_from_import(path, node)
            if (
                imported_from is None
                or imported_from == current_module
                or not imported_from.startswith("assistant.execution_kernel.")
            ):
                continue
            for alias in node.names:
                if alias.name.startswith("_"):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)} imports private peer "
                        f"{imported_from}.{alias.name}"
                    )
    assert not offenders, offenders
