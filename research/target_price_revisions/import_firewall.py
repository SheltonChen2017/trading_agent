"""Static transitive dependency guard for the outcome-free TPR package.

This guard constrains Python import dependencies and obvious runtime-import
indirection. It is not an operating-system I/O sandbox: allowed standard-library
modules such as :mod:`pathlib` and :mod:`subprocess` remain capable of I/O if
called. Their presence grants no provider, outcome, QC, broker, or trading
authority; those capabilities remain separately absent and authorization-gated.
"""

# TPR-CCR5-001: tracked LF migration marker for existing Windows worktrees.
from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import Iterable


# This is deliberately an allowlist rather than a copy of ``sys.stdlib_module_names``.
# TPR-0 may use only the standard-library surfaces its frozen implementation needs.
DEFAULT_ALLOWED_STDLIB_ROOTS = frozenset(
    {
        "__future__",
        "ast",
        "base64",
        "binascii",
        "collections",
        "ctypes",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "re",
        "subprocess",
        "threading",
        "types",
        "typing",
        "unicodedata",
        "weakref",
    }
)


# The narrow TPR package has no legitimate need to obtain import/evaluation
# primitives as values. Rejecting the references themselves closes alias forms
# such as ``load = __import__`` rather than trying to infer later call targets.
_FORBIDDEN_RUNTIME_NAMES = frozenset(
    {
        "__builtins__",
        "__import__",
        "builtins",
        "compile",
        "eval",
        "exec",
        "globals",
        "import_module",
        "importlib",
        "locals",
        "vars",
    }
)
_FORBIDDEN_RUNTIME_ATTRIBUTES = frozenset(
    {"__getattribute__", "__import__", "import_module"}
)
_FORBIDDEN_GETATTR_NAMES = frozenset(
    {"__getattribute__", "__import__", "compile", "eval", "exec", "import_module"}
)


# Prefixes are checked before repository-local resolution. A pleasant-looking
# local facade therefore cannot make an authority-bearing dependency acceptable.
DEFAULT_FORBIDDEN_IMPORT_PREFIXES = frozenset(
    {
        # Target outcomes, backtests, QuantConnect, and shared/legacy research.
        "backtest",
        "data",
        "research.acer",
        "research.analyst_revisions_v2",
        "research.assistant_results",
        "research.lean",
        "research.ml_specs",
        "research.quantconnect",
        "AlgorithmImports",
        "QuantConnect",
        "lean",
        "qc",
        "quantconnect",
        # Execution, broker, assistant, ML, UI, and legacy strategy surfaces.
        "assistant",
        "baskets",
        "broker",
        "brokers",
        "config",
        "execution",
        "market_analytics",
        "ml",
        "risk",
        "scripts",
        "signals",
        "strategies",
        "dashboard",
        "dash",
        "frontend",
        "gradio",
        "streamlit",
        "ui",
        "webapp",
        # Network and provider clients. Unlisted third-party modules are also
        # rejected by the standard-library allowlist below.
        "aiohttp",
        "alpaca",
        "alpaca_trade_api",
        "benzinga",
        "ccxt",
        "finnhub",
        "ftplib",
        "http",
        "httpx",
        "ib_insync",
        "massive",
        "network",
        "networking",
        "outcome",
        "outcomes",
        "pandas_datareader",
        "polygon",
        "polygon_api_client",
        "provider",
        "providers",
        "requests",
        "smtplib",
        "socket",
        "ssl",
        "telnetlib",
        "urllib",
        "urllib3",
        "websocket",
        "websockets",
        "xmlrpc",
        "yfinance",
    }
)


class ImportBoundaryError(ValueError):
    """A forbidden, unapproved, dynamic, or path-unsafe import was found."""


@dataclasses.dataclass(frozen=True)
class _LocalModule:
    name: str
    path: Path
    is_package: bool


def _is_canonical_module_name(value: str) -> bool:
    return bool(value) and all(part.isidentifier() for part in value.split("."))


def _is_forbidden(module: str, forbidden: frozenset[str]) -> bool:
    return any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in forbidden
    )


def _is_redirect(path: Path) -> bool:
    """Return whether a path is a symlink or Windows junction."""
    try:
        return path.is_symlink() or (
            path.is_junction() if hasattr(path, "is_junction") else False
        )
    except OSError as exc:
        raise ImportBoundaryError(f"path-redirection audit failed: {path}") from exc


def _assert_contained_without_symlinks(path: Path, repository_root: Path) -> None:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(repository_root)
    except (OSError, ValueError) as exc:
        raise ImportBoundaryError(f"module path escapes repository root: {path}") from exc
    cursor = path
    while cursor != repository_root:
        if _is_redirect(cursor):
            raise ImportBoundaryError(
                f"import closure cannot contain a symlink or junction: {path}"
            )
        parent = cursor.parent
        if parent == cursor:
            raise ImportBoundaryError(f"module path escapes repository root: {path}")
        cursor = parent
    if resolved != path.resolve():
        raise ImportBoundaryError(f"module path is not canonical: {path}")


def _module_at(repository_root: Path, module: str) -> _LocalModule | None:
    if not _is_canonical_module_name(module):
        return None
    relative = Path(*module.split("."))
    source = repository_root / relative.with_suffix(".py")
    package = repository_root / relative / "__init__.py"
    extension_forms = (
        repository_root / relative.with_suffix(".pyd"),
        repository_root / relative.with_suffix(".so"),
        repository_root / relative / "__init__.pyd",
        repository_root / relative / "__init__.so",
    )
    if any(
        candidate.exists() or _is_redirect(candidate) for candidate in extension_forms
    ):
        raise ImportBoundaryError(
            f"local module must use reviewed Python source, not an extension: {module}"
        )
    bytecode_forms = (
        repository_root / relative.with_suffix(".pyc"),
        repository_root / relative / "__init__.pyc",
    )
    if not source.is_file() and not package.is_file() and any(
        candidate.exists() or _is_redirect(candidate) for candidate in bytecode_forms
    ):
        raise ImportBoundaryError(
            f"local module must use reviewed Python source, not bytecode only: {module}"
        )
    if source.is_file() and package.is_file():
        raise ImportBoundaryError(f"ambiguous local module/package: {module}")
    for candidate in (source, package):
        if _is_redirect(candidate):
            raise ImportBoundaryError(
                f"local module cannot be a symlink or junction: {module} ({candidate})"
            )
    if source.is_file():
        _assert_contained_without_symlinks(source, repository_root)
        return _LocalModule(module, source, False)
    if package.is_file():
        _assert_contained_without_symlinks(package, repository_root)
        return _LocalModule(module, package, True)
    return None


def _is_local_namespace(repository_root: Path, module: str) -> bool:
    if not _is_canonical_module_name(module):
        return False
    directory = repository_root / Path(*module.split("."))
    if not directory.is_dir():
        return False
    _assert_contained_without_symlinks(directory, repository_root)
    return not (directory / "__init__.py").is_file()


def _module_name(repository_root: Path, path: Path) -> _LocalModule:
    try:
        relative = path.relative_to(repository_root)
    except ValueError as exc:
        raise ImportBoundaryError(f"module path escapes repository root: {path}") from exc
    if path.name == "__init__.py":
        parts = relative.parent.parts
        is_package = True
    else:
        parts = relative.with_suffix("").parts
        is_package = False
    if not parts or any(not part.isidentifier() for part in parts):
        raise ImportBoundaryError(f"non-canonical Python module path: {path}")
    if _is_redirect(path) or not path.is_file():
        raise ImportBoundaryError(f"module must be a regular source file: {path}")
    _assert_contained_without_symlinks(path, repository_root)
    return _LocalModule(".".join(parts), path, is_package)


def _from_import_candidates(
    node: ast.ImportFrom, current: _LocalModule
) -> tuple[str, ...]:
    if node.level == 0:
        base = node.module or ""
    else:
        package_name = (
            current.name if current.is_package else current.name.rpartition(".")[0]
        )
        package_parts = package_name.split(".") if package_name else []
        parents_to_remove = node.level - 1
        if parents_to_remove >= len(package_parts):
            raise ImportBoundaryError(
                f"relative import escapes top-level package in {current.name} "
                f"({current.path})"
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


def _reject_runtime_import_indirection(
    tree: ast.AST, module: _LocalModule
) -> None:
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    for node in ast.walk(tree):
        primitive: str | None = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_root = alias.name.partition(".")[0]
                if imported_root in {"builtins", "importlib"}:
                    primitive = alias.name
                    break
                if alias.asname in _FORBIDDEN_RUNTIME_NAMES:
                    primitive = alias.asname
                    break
        elif isinstance(node, ast.ImportFrom):
            imported_root = (node.module or "").partition(".")[0]
            if node.level == 0 and imported_root in {"builtins", "importlib"}:
                primitive = node.module or imported_root
            else:
                for alias in node.names:
                    if (
                        alias.name in _FORBIDDEN_RUNTIME_NAMES
                        or alias.asname in _FORBIDDEN_RUNTIME_NAMES
                    ):
                        primitive = alias.asname or alias.name
                        break
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_RUNTIME_NAMES:
            primitive = node.id
        elif isinstance(node, ast.Name) and node.id == "getattr":
            parent = parents.get(node)
            direct_call = (
                isinstance(parent, ast.Call)
                and parent.func is node
                and len(parent.args) >= 2
            )
            attribute = (
                parent.args[1].value
                if direct_call
                and isinstance(parent.args[1], ast.Constant)
                and isinstance(parent.args[1].value, str)
                else None
            )
            if not direct_call or attribute is None or attribute in _FORBIDDEN_GETATTR_NAMES:
                primitive = "getattr"
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in _FORBIDDEN_RUNTIME_ATTRIBUTES
        ):
            primitive = node.attr
        if primitive is not None:
            location = f"line {node.lineno}"
            raise ImportBoundaryError(
                f"runtime import/reflection primitive {primitive!r} is forbidden "
                f"in {module.name} ({module.path}, {location})"
            )


def _parsed_imports(
    module: _LocalModule, repository_root: Path
) -> tuple[str, ...]:
    try:
        source = module.path.read_text(encoding="utf-8", errors="strict")
        tree = ast.parse(source, filename=str(module.path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ImportBoundaryError(
            f"cannot parse import closure module {module.name} ({module.path})"
        ) from exc

    _reject_runtime_import_indirection(tree, module)
    candidates: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                candidates.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            from_candidates = _from_import_candidates(node, module)
            if from_candidates:
                candidates.append(from_candidates[0])
                candidates.extend(
                    candidate
                    for candidate in from_candidates[1:]
                    if _module_at(repository_root, candidate) is not None
                )
    return tuple(dict.fromkeys(candidates))


def _local_module_for_candidate(
    repository_root: Path, imported: str
) -> _LocalModule | None:
    return _module_at(repository_root, imported)


def _validate_import_closure(
    repository_root: str | Path,
    *,
    package_name: str,
    forbidden_prefixes: Iterable[str] = DEFAULT_FORBIDDEN_IMPORT_PREFIXES,
    allowed_stdlib_roots: Iterable[str] = DEFAULT_ALLOWED_STDLIB_ROOTS,
    allowed_local_prefixes: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Return reached local modules or fail with the full offending path.

    Every source in ``package_name`` is a root. Repository-local facades and
    every existing parent package initializer are followed transitively.
    Non-local imports must belong to the narrow standard-library allowlist.
    This is a dependency check, not an OS-level I/O or capability sandbox.
    """

    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ImportBoundaryError("repository_root must be a directory")
    if not _is_canonical_module_name(package_name):
        raise ImportBoundaryError("package_name must be a canonical dotted name")
    if isinstance(forbidden_prefixes, (str, bytes)):
        raise ImportBoundaryError("forbidden prefixes must be an iterable of names")
    forbidden = frozenset(forbidden_prefixes)
    if not forbidden or any(
        not _is_canonical_module_name(prefix) for prefix in forbidden
    ):
        raise ImportBoundaryError(
            "forbidden prefixes must be canonical dotted names"
        )
    if isinstance(allowed_stdlib_roots, (str, bytes)):
        raise ImportBoundaryError("allowed stdlib roots must be an iterable of names")
    allowed_stdlib = frozenset(allowed_stdlib_roots)
    if not allowed_stdlib or any(
        not root_name.isidentifier() for root_name in allowed_stdlib
    ):
        raise ImportBoundaryError(
            "allowed stdlib roots must be canonical top-level names"
        )
    if allowed_local_prefixes is None:
        allowed_local: frozenset[str] | None = None
    else:
        if isinstance(allowed_local_prefixes, (str, bytes)):
            raise ImportBoundaryError("allowed local prefixes must be an iterable")
        allowed_local = frozenset(allowed_local_prefixes)
        if not allowed_local or any(
            not _is_canonical_module_name(prefix) for prefix in allowed_local
        ):
            raise ImportBoundaryError(
                "allowed local prefixes must be canonical dotted names"
            )

    package_root = root / Path(*package_name.split("."))
    if not package_root.is_dir() or _is_redirect(package_root):
        raise ImportBoundaryError("guarded package must be a regular directory")
    _assert_contained_without_symlinks(package_root, root)
    for path in package_root.rglob("*"):
        if _is_redirect(path):
            raise ImportBoundaryError(
                f"guarded package cannot contain a symlink or junction: {path}"
            )
    roots = [
        _module_name(root, path)
        for path in sorted(package_root.rglob("*.py"))
    ]
    if not roots:
        raise ImportBoundaryError("guarded package has no Python sources")
    package_parts = package_name.split(".")
    guarded_namespace_packages = frozenset(
        prefix
        for length in range(1, len(package_parts) + 1)
        for prefix in [".".join(package_parts[:length])]
        if _is_local_namespace(root, prefix)
    )

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

        for imported in _parsed_imports(module, root):
            if _is_forbidden(imported, forbidden):
                rendered_chain = " -> ".join((*chain, module.name, imported))
                relative_path = module.path.relative_to(root)
                raise ImportBoundaryError(
                    f"forbidden transitive import {imported!r}: {rendered_chain} "
                    f"(source {relative_path})"
                )
            local = _local_module_for_candidate(root, imported)
            if local is not None:
                if allowed_local is not None and not any(
                    local.name == prefix or local.name.startswith(prefix + ".")
                    for prefix in allowed_local
                ):
                    rendered_chain = " -> ".join((*chain, module.name, imported))
                    raise ImportBoundaryError(
                        f"unapproved repository-local import {imported!r}: "
                        f"{rendered_chain}"
                    )
                visit(local, (*chain, module.name))
                continue
            # Only a namespace directory on the guarded package's own path is
            # accepted. An arbitrary empty repository directory must not turn
            # an unapproved installed package into an apparently local import.
            if imported in guarded_namespace_packages:
                continue
            imported_root = imported.partition(".")[0]
            if imported_root not in allowed_stdlib:
                rendered_chain = " -> ".join((*chain, module.name, imported))
                relative_path = module.path.relative_to(root)
                raise ImportBoundaryError(
                    f"unapproved external import {imported!r}: {rendered_chain} "
                    f"(source {relative_path})"
                )

    for root_module in roots:
        visit(root_module, ())
    return tuple(sorted(visited))


def validate_transitive_import_closure(
    repository_root: str | Path,
) -> tuple[str, ...]:
    """Validate the fixed authoritative TPR dependency boundary.

    This wrapper intentionally exposes no package, forbidden-prefix, standard-
    library, or local-module overrides. Tests for the generic traversal use the
    private helper directly; only this fixed wrapper represents the TPR guard.
    """

    return _validate_import_closure(
        repository_root,
        package_name="research.target_price_revisions",
        forbidden_prefixes=DEFAULT_FORBIDDEN_IMPORT_PREFIXES,
        allowed_stdlib_roots=DEFAULT_ALLOWED_STDLIB_ROOTS,
        allowed_local_prefixes=("research.target_price_revisions",),
    )
