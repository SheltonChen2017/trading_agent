"""Regression guards for the owner-directed product separation.

SEP-0 does not pretend the current monorepo is already separated.  It records
every direct import crossing between the two future products and refuses any
new crossing.  The listed edges are migration debt, not an approved permanent
API.  Execution-authority modules get the stricter rule now: they may not
reach strategy-research code through any first-party import chain.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
BOUNDARY_FILE = REPO_ROOT / "architecture" / "project_boundaries.json"


def _manifest() -> dict:
    return json.loads(BOUNDARY_FILE.read_text(encoding="utf-8"))


def _root_path(root: str) -> Path:
    return REPO_ROOT / root


def _python_files(root: str):
    path = _root_path(root)
    if path.is_dir():
        yield from path.rglob("*.py")
    elif path.suffix == ".py" and path.is_file():
        yield path


def _module_name(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _absolute_from_import(path: Path, node: ast.ImportFrom) -> str | None:
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


def _owned_roots(manifest: dict) -> list[str]:
    roots: list[str] = []
    for product in manifest["products"].values():
        roots.extend(product["owned_roots"])
    roots.extend(manifest["shared_roots"])
    return roots


def _module_graph(manifest: dict) -> tuple[dict[str, set[str]], list[str]]:
    paths = [path for root in _owned_roots(manifest) for path in _python_files(root)]
    known_modules = {_module_name(path) for path in paths}
    graph: dict[str, set[str]] = {}
    unresolved: list[str] = []

    for path in paths:
        source = _module_name(path)
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
                        f"{source}: invalid relative import "
                        f"(level={node.level}, module={node.module!r})"
                    )
                    continue
                imported_submodules = {
                    f"{imported_from}.{alias.name}"
                    for alias in node.names
                    if alias.name != "*" and f"{imported_from}.{alias.name}" in known_modules
                }
                dependencies.update(imported_submodules or {imported_from})
            elif isinstance(node, ast.Call):
                function = node.func
                name = getattr(function, "attr", None) or getattr(function, "id", None)
                if name not in {"import_module", "__import__"}:
                    continue
                if (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and not node.args[0].value.startswith(".")
                ):
                    dependencies.add(node.args[0].value)
                else:
                    dependencies.add(f"<unresolved dynamic import via {name}()>")
        graph[source] = dependencies
    return graph, unresolved


def _product_roots(manifest: dict) -> dict[str, set[str]]:
    return {
        name: {
            Path(root).with_suffix("").as_posix().replace("/", ".")
            for root in product["owned_roots"]
        }
        for name, product in manifest["products"].items()
    }


def _product_for(module: str, roots: dict[str, set[str]]) -> str | None:
    for product, candidates in roots.items():
        if any(module == root or module.startswith(f"{root}.") for root in candidates):
            return product
    return None


def _cross_product_edges(manifest: dict, graph: dict[str, set[str]]) -> set[tuple[str, str]]:
    roots = _product_roots(manifest)
    edges: set[tuple[str, str]] = set()
    for source, dependencies in graph.items():
        source_product = _product_for(source, roots)
        if source_product is None:
            continue
        for dependency in dependencies:
            target_product = _product_for(dependency, roots)
            if target_product is not None and target_product != source_product:
                edges.add((source, dependency))
    return edges


def test_separation_manifest_is_narrow_complete_and_well_formed():
    manifest = _manifest()
    assert manifest["schema_version"] == 1
    roots = _owned_roots(manifest) + manifest["mixed_roots_pending_classification"]
    assert len(roots) == len(set(roots)), "a path cannot belong to two separation groups"
    missing = sorted(root for root in roots if not _root_path(root).exists())
    assert not missing, f"separation manifest names missing roots: {missing}"

    declared = manifest["allowed_direct_cross_product_imports"]
    pairs = [(entry["source"], entry["target"]) for entry in declared]
    assert len(pairs) == len(set(pairs)), "cross-product migration edges must be unique"
    assert all(entry["reason"].strip() for entry in declared)
    authority_paths = manifest["allowed_authority_research_paths"]
    path_tuples = [tuple(entry["path"]) for entry in authority_paths]
    assert len(path_tuples) == len(set(path_tuples))
    assert all(len(path) >= 2 for path in path_tuples)
    assert all(entry["reason"].strip() for entry in authority_paths)


def test_no_unledgered_direct_cross_product_imports():
    manifest = _manifest()
    graph, unresolved = _module_graph(manifest)
    assert not unresolved, (
        "the separation audit cannot prove the import boundary: "
        + "; ".join(sorted(unresolved))
    )
    actual = _cross_product_edges(manifest, graph)
    declared = {
        (entry["source"], entry["target"])
        for entry in manifest["allowed_direct_cross_product_imports"]
    }
    assert actual == declared, (
        "cross-product imports changed; remove the dependency or update the reviewed "
        f"migration ledger. unexpected={sorted(actual - declared)}, "
        f"stale={sorted(declared - actual)}"
    )


def test_execution_authority_research_reachability_cannot_expand():
    manifest = _manifest()
    graph, unresolved = _module_graph(manifest)
    assert not unresolved, (
        "the separation audit cannot prove the authority boundary: "
        + "; ".join(sorted(unresolved))
    )
    roots = _product_roots(manifest)
    authority = manifest["authority_roots"]
    starting_modules = sorted(
        module
        for module in graph
        if any(module == root or module.startswith(f"{root}.") for root in authority)
    )
    assert starting_modules, "the manifest did not resolve any execution-authority modules"

    offenders: list[str] = []
    for start in starting_modules:
        seen = {start}
        stack = [(start, (start,))]
        while stack:
            current, chain = stack.pop()
            for dependency in sorted(graph.get(current, ())):
                next_chain = chain + (dependency,)
                if dependency.startswith("<unresolved "):
                    offenders.append(" -> ".join(next_chain))
                    continue
                if _product_for(dependency, roots) == "strategy_research":
                    offenders.append(" -> ".join(next_chain))
                    continue
                if dependency in graph and dependency not in seen:
                    seen.add(dependency)
                    stack.append((dependency, next_chain))

    actual = set(offenders)
    declared = {
        " -> ".join(entry["path"])
        for entry in manifest["allowed_authority_research_paths"]
    }
    assert actual == declared, (
        "execution-authority reachability changed; remove the dependency or "
        "update the reviewed migration ledger. "
        f"unexpected={sorted(actual - declared)}, stale={sorted(declared - actual)}"
    )
