"""Static transitive import-closure guard for the outcome-free ARV2 layer."""
from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import Iterable


DEFAULT_FORBIDDEN_IMPORT_PREFIXES = frozenset(
    {
        "research.acer",
        "research.assistant_results",
        "data.market_data",
        "data.price_source",
        "data.price_target_data",
        "data.research_results",
        "backtest",
        "execution",
        "assistant",
        "risk",
        "signals",
        "strategies",
        "ml",
        "scripts",
        "alpaca",
        "alpaca_trade_api",
        "aiohttp",
        "httpx",
        "http",
        "ftplib",
        "smtplib",
        "ssl",
        "subprocess",
        "telnetlib",
        "urllib3",
        "websocket",
        "websockets",
        "xmlrpc.client",
        "pandas_datareader",
        "requests",
        "socket",
        "urllib",
        "yfinance",
    }
)

_ALLOWED_FORBIDDEN_IMPORTS = {
    "research.analyst_revisions_v2.dataset": frozenset({"subprocess"}),
}


class ImportBoundaryError(ValueError):
    """A direct or facade-mediated forbidden dependency crossed the boundary."""


@dataclasses.dataclass(frozen=True)
class _LocalModule:
    name: str
    path: Path
    is_package: bool


def _is_forbidden(module: str, forbidden: frozenset[str]) -> bool:
    return any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden)


def _is_explicitly_allowed(importer: str, imported: str) -> bool:
    return any(
        imported == prefix or imported.startswith(prefix + ".")
        for prefix in _ALLOWED_FORBIDDEN_IMPORTS.get(importer, ())
    )


def _assert_regular_contained(path: Path, repository_root: Path) -> None:
    try:
        path.resolve(strict=True).relative_to(repository_root)
    except (OSError, ValueError) as exc:
        raise ImportBoundaryError(f"module escapes repository root: {path}") from exc
    cursor = path
    while cursor != repository_root:
        if cursor.is_symlink():
            raise ImportBoundaryError(f"module closure cannot contain symlinks: {path}")
        cursor = cursor.parent


def _module_at(repository_root: Path, module: str) -> _LocalModule | None:
    if not module or any(not part.isidentifier() for part in module.split(".")):
        return None
    relative = Path(*module.split("."))
    source = repository_root / relative.with_suffix(".py")
    package = repository_root / relative / "__init__.py"
    if source.is_file() and package.is_file():
        raise ImportBoundaryError(f"ambiguous local module/package: {module}")
    if source.is_symlink() or package.is_symlink():
        raise ImportBoundaryError(f"local module cannot be a symlink: {module}")
    if source.is_file():
        _assert_regular_contained(source, repository_root)
        return _LocalModule(module, source, False)
    if package.is_file():
        _assert_regular_contained(package, repository_root)
        return _LocalModule(module, package, True)
    return None


def _module_name(
    repository_root: Path, path: Path, *, package_root: Path
) -> _LocalModule:
    relative = path.relative_to(repository_root)
    if path.name == "__init__.py":
        parts = relative.parent.parts
        is_package = True
    else:
        parts = relative.with_suffix("").parts
        is_package = False
    if not parts or any(not part.isidentifier() for part in parts):
        raise ImportBoundaryError(f"non-canonical Python module path: {path}")
    if path.is_symlink() or not path.is_file():
        raise ImportBoundaryError(f"module must be a regular source file: {path}")
    _assert_regular_contained(path, repository_root.resolve(strict=True))
    return _LocalModule(".".join(parts), path, is_package)


def _from_import_candidates(
    node: ast.ImportFrom, current: _LocalModule
) -> tuple[str, ...]:
    if node.level == 0:
        base = node.module or ""
    else:
        package_name = current.name if current.is_package else current.name.rpartition(".")[0]
        package_parts = package_name.split(".") if package_name else []
        parents_to_remove = node.level - 1
        if parents_to_remove >= len(package_parts):
            raise ImportBoundaryError(
                f"relative import escapes top-level package in {current.name}"
            )
        base_parts = package_parts[: len(package_parts) - parents_to_remove]
        if node.module:
            base_parts.extend(node.module.split("."))
        base = ".".join(base_parts)
    candidates: list[str] = []
    if base:
        candidates.append(base)
    for alias in node.names:
        if alias.name == "*":
            continue
        candidates.append(f"{base}.{alias.name}" if base else alias.name)
    return tuple(dict.fromkeys(candidates))


def _parsed_imports(module: _LocalModule) -> tuple[str, ...]:
    try:
        source = module.path.read_text(encoding="utf-8", errors="strict")
        tree = ast.parse(source, filename=str(module.path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ImportBoundaryError(f"cannot parse import closure module {module.name}") from exc

    candidates: list[str] = []
    importlib_aliases: set[str] = set()
    import_module_names: set[str] = {"__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                candidates.append(alias.name)
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            candidates.extend(_from_import_candidates(node, module))
            if node.level == 0 and node.module == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        import_module_names.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dynamic_import = False
        if isinstance(node.func, ast.Name) and node.func.id in import_module_names:
            dynamic_import = True
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in importlib_aliases
        ):
            dynamic_import = True
        if not dynamic_import:
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(
            node.args[0].value, str
        ):
            raise ImportBoundaryError(
                f"non-literal dynamic import is forbidden in {module.name}"
            )
        imported = node.args[0].value
        if not imported or any(not part.isidentifier() for part in imported.split(".")):
            raise ImportBoundaryError(
                f"dynamic import must use an absolute canonical module name in {module.name}"
            )
        candidates.append(imported)
    return tuple(dict.fromkeys(candidates))


def validate_transitive_import_closure(
    repository_root: str | Path,
    *,
    package_name: str = "research.analyst_revisions_v2",
    forbidden_prefixes: Iterable[str] = DEFAULT_FORBIDDEN_IMPORT_PREFIXES,
) -> tuple[str, ...]:
    """Return every reached local module or fail with the full offending chain.

    Every source file in ``package_name`` is a root.  Repository-local facade
    modules are followed recursively, so moving a forbidden import behind a
    pleasant-looking helper does not evade the boundary.
    """
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ImportBoundaryError("repository_root must be a directory")
    if not package_name or any(not part.isidentifier() for part in package_name.split(".")):
        raise ImportBoundaryError("package_name must be a canonical dotted name")
    forbidden = frozenset(forbidden_prefixes)
    if not forbidden or any(
        not prefix or any(not part.isidentifier() for part in prefix.split("."))
        for prefix in forbidden
    ):
        raise ImportBoundaryError("forbidden prefixes must be canonical dotted names")

    package_root = root / Path(*package_name.split("."))
    if not package_root.is_dir() or package_root.is_symlink():
        raise ImportBoundaryError("guarded package must be a regular directory")
    for path in package_root.rglob("*"):
        if path.is_symlink():
            raise ImportBoundaryError("guarded package cannot contain symlinks")
    roots: list[_LocalModule] = []
    for path in sorted(package_root.rglob("*.py")):
        roots.append(_module_name(root, path, package_root=package_root))
    if not roots:
        raise ImportBoundaryError("guarded package has no Python sources")

    visited: set[str] = set()

    def visit(module: _LocalModule, chain: tuple[str, ...]) -> None:
        if module.name in visited:
            return
        visited.add(module.name)
        module_parts = module.name.split(".")
        for part_count in range(1, len(module_parts)):
            parent_name = ".".join(module_parts[:part_count])
            parent = _module_at(root, parent_name)
            if parent is not None and parent.is_package:
                visit(parent, (*chain, module.name))
        for imported in _parsed_imports(module):
            local = _module_at(root, imported)
            explicitly_allowed = (
                local is None and _is_explicitly_allowed(module.name, imported)
            )
            if _is_forbidden(imported, forbidden) and not explicitly_allowed:
                rendered_chain = " -> ".join((*chain, module.name, imported))
                raise ImportBoundaryError(
                    f"forbidden transitive import {imported!r}: {rendered_chain}"
                )
            if local is not None:
                visit(local, (*chain, module.name))

    for root_module in roots:
        visit(root_module, ())
    return tuple(sorted(visited))
