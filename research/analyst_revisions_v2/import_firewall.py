"""Static transitive dependency guard for the outcome-free ARV2 package.

This guard constrains Python import dependencies and obvious runtime-import
indirection. It is not an operating-system I/O sandbox: even allowed modules
such as :mod:`pathlib` remain capable of I/O if called. Their presence grants
no provider, outcome, QC, broker, or trading authority; those capabilities
remain separately absent and authorization-gated.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import Iterable


# This is deliberately an allowlist rather than a copy of ``sys.stdlib_module_names``.
# ARV2 may use only the standard-library surfaces its frozen implementation needs.
DEFAULT_ALLOWED_STDLIB_ROOTS = frozenset(
    {
        "__future__",
        "argparse",
        "ast",
        "collections",
        "contextlib",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "fractions",
        "hashlib",
        "json",
        "pathlib",
        "re",
        "statistics",
        "threading",
        "types",
        "typing",
        "unicodedata",
        "weakref",
    }
)


# The narrow ARV2 package has no legitimate need to obtain import/evaluation
# primitives as values. Rejecting the references themselves closes alias forms
# such as ``load = __import__`` rather than trying to infer later call targets.
_FORBIDDEN_RUNTIME_NAMES = frozenset(
    {
        "__builtins__",
        "__import__",
        "builtins",
        "compile",
        "delattr",
        "eval",
        "exec",
        "globals",
        "get_type_hints",
        "import_module",
        "importlib",
        "locals",
        "setattr",
        "vars",
    }
)
_FORBIDDEN_RUNTIME_ATTRIBUTES = frozenset(
    {
        "__builtins__",
        "__base__",
        "__bases__",
        "__class__",
        "__dict__",
        "__globals__",
        "__getattribute__",
        "__import__",
        "__loader__",
        "__module__",
        "__mro__",
        "__self__",
        "__setattr__",
        "__delattr__",
        "__spec__",
        "__subclasses__",
        "_create_fn",
        "_eval_type",
        "_evaluate",
        "builtins",
        "eval",
        "evaluate_forward_ref",
        "exec",
        "exec_module",
        "getattr",
        "get_type_hints",
        "globals",
        "import_module",
        "importlib",
        "load_module",
        "locals",
        "module_from_spec",
        "mcal",
        "pd",
        "popen",
        "spec_from_file_location",
        "startfile",
        "sys",
        "system",
        "vars",
    }
)
_FORBIDDEN_GETATTR_NAMES = _FORBIDDEN_RUNTIME_ATTRIBUTES | frozenset(
    {"compile", "eval", "exec"}
)
_RESTRICTED_CAPABILITY_NAMES = frozenset(
    {"os", "shutil", "subprocess", "sys", "uuid"}
)
_CAPABILITY_IMPORTER = "research.analyst_revisions_v2.dataset"
_FIREWALL_MODULE = "research.analyst_revisions_v2.import_firewall"


# Prefixes are checked before repository-local resolution. A pleasant-looking
# local facade therefore cannot make an authority-bearing dependency acceptable.
DEFAULT_FORBIDDEN_IMPORT_PREFIXES = frozenset(
    {
        # Target outcomes, backtests, QuantConnect, and shared/legacy research.
        "backtest",
        "data.market_data",
        "data.price_source",
        "data.price_target_data",
        "data.research_results",
        "research.acer",
        "research.assistant_results",
        "research.lean",
        "research.ml_specs",
        "research.quantconnect",
        "research.target_price_revisions",
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
        "subprocess",
        "telnetlib",
        "urllib",
        "urllib3",
        "websocket",
        "websockets",
        "xmlrpc",
        "yfinance",
    }
)


# Capability-bearing imports are allowed only at the exact reviewed modules
# that need them. They are not part of the general standard-library allowlist.
_ALLOWED_EXTERNAL_IMPORT_ROOTS = {
    _CAPABILITY_IMPORTER: frozenset({"os", "shutil", "subprocess", "uuid"}),
    "data.exchange_calendar": frozenset({"pandas", "pandas_market_calendars"}),
}

_SAFE_LOCAL_FACADE_EXPORTS = {
    "data.exchange_calendar": frozenset(
        {
            "ExchangeCalendarError",
            "is_trading_session",
            "next_session_open_strictly_after",
            "resolve_nth_session_after",
            "session_open_instant",
            "trading_sessions",
        }
    )
}


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


def _is_explicitly_allowed_external(importer: str, imported: str) -> bool:
    return (
        imported.partition(".")[0]
        in _ALLOWED_EXTERNAL_IMPORT_ROOTS.get(importer, ())
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
    unreviewed_forms: list[Path] = []
    for directory, stem in (
        (repository_root / relative.parent, relative.name),
        (repository_root / relative, "__init__"),
    ):
        if _is_redirect(directory):
            raise ImportBoundaryError(
                f"local module directory cannot be a symlink or junction: {module}"
            )
        if not directory.is_dir():
            continue
        try:
            directory_entries = tuple(directory.iterdir())
        except OSError as exc:
            raise ImportBoundaryError(
                f"local module directory could not be audited: {module}"
            ) from exc
        for candidate in directory_entries:
            lowered = candidate.name.lower()
            extension_or_pyw = (
                lowered == f"{stem.lower()}.pyw"
                or (
                    lowered.startswith(f"{stem.lower()}.")
                    and lowered.endswith((".pyd", ".so"))
                )
            )
            if extension_or_pyw and (candidate.is_file() or _is_redirect(candidate)):
                unreviewed_forms.append(candidate)
    if unreviewed_forms:
        raise ImportBoundaryError(
            "local module must use reviewed .py source, not an extension or .pyw: "
            f"{module}"
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
    string_aliases: dict[str, set[str]] = {}
    string_assignments: list[tuple[tuple[str, ...], ast.AST]] = []
    for candidate in ast.walk(tree):
        if isinstance(candidate, ast.Assign):
            names = tuple(
                target.id for target in candidate.targets if isinstance(target, ast.Name)
            )
            if names:
                string_assignments.append((names, candidate.value))
        elif (
            isinstance(candidate, ast.AnnAssign)
            and isinstance(candidate.target, ast.Name)
            and candidate.value is not None
        ):
            string_assignments.append(((candidate.target.id,), candidate.value))
        elif isinstance(candidate, ast.NamedExpr) and isinstance(
            candidate.target, ast.Name
        ):
            string_assignments.append(((candidate.target.id,), candidate.value))
        elif isinstance(candidate, ast.arguments):
            positional = (*candidate.posonlyargs, *candidate.args)
            if candidate.defaults:
                for argument, default in zip(
                    positional[-len(candidate.defaults) :], candidate.defaults
                ):
                    string_assignments.append(((argument.arg,), default))
            for argument, default in zip(
                candidate.kwonlyargs, candidate.kw_defaults
            ):
                if default is not None:
                    string_assignments.append(((argument.arg,), default))

    def constant_strings(node: ast.AST) -> frozenset[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return frozenset({node.value})
        if isinstance(node, ast.Name):
            return frozenset(string_aliases.get(node.id, ()))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = constant_strings(node.left)
            right = constant_strings(node.right)
            if left and right and len(left) * len(right) <= 256:
                return frozenset(prefix + suffix for prefix in left for suffix in right)
        if isinstance(node, ast.JoinedStr):
            parts = [
                value.value
                for value in node.values
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            ]
            if len(parts) == len(node.values):
                return frozenset({"".join(parts)})
        return frozenset()

    for _iteration in range(len(string_assignments) + 1):
        changed = False
        for names, value_node in string_assignments:
            values = constant_strings(value_node)
            if not values:
                continue
            for name in names:
                known = string_aliases.setdefault(name, set())
                before = len(known)
                known.update(values)
                if len(known) != before:
                    changed = True
        if not changed:
            break

    def forbidden_constant(
        node: ast.AST, forbidden_values: frozenset[str]
    ) -> str | None:
        matches = constant_strings(node) & forbidden_values
        return min(matches) if matches else None

    regex_module_aliases = {
        alias.asname or "re"
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "re"
    }
    rebound_names: set[str] = set()
    has_wildcard_import = False
    for candidate in ast.walk(tree):
        if isinstance(candidate, ast.Name) and isinstance(
            candidate.ctx, (ast.Store, ast.Del)
        ):
            rebound_names.add(candidate.id)
        elif isinstance(candidate, ast.arg):
            rebound_names.add(candidate.arg)
        elif isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            rebound_names.add(candidate.name)
        elif isinstance(candidate, ast.ImportFrom):
            if any(alias.name == "*" for alias in candidate.names):
                has_wildcard_import = True
            rebound_names.update(
                alias.asname or alias.name
                for alias in candidate.names
                if alias.name != "*"
            )
        elif isinstance(candidate, ast.Import):
            rebound_names.update(
                alias.asname or alias.name.partition(".")[0]
                for alias in candidate.names
                if alias.name != "re"
            )
        elif isinstance(candidate, ast.ExceptHandler) and candidate.name:
            rebound_names.add(candidate.name)
        elif isinstance(candidate, (ast.MatchAs, ast.MatchStar)) and candidate.name:
            rebound_names.add(candidate.name)
        elif isinstance(candidate, ast.MatchMapping) and candidate.rest:
            rebound_names.add(candidate.rest)
    safe_regex_module_aliases = (
        frozenset() if has_wildcard_import else regex_module_aliases - rebound_names
    )
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
                if (
                    imported_root in _RESTRICTED_CAPABILITY_NAMES
                    and not _is_explicitly_allowed_external(
                        module.name, imported_root
                    )
                ):
                    primitive = imported_root
                    break
        elif isinstance(node, ast.ImportFrom):
            imported_root = (node.module or "").partition(".")[0]
            from_candidates = _from_import_candidates(node, module)
            imported_base = from_candidates[0] if from_candidates else ""
            safe_exports = _SAFE_LOCAL_FACADE_EXPORTS.get(imported_base)
            if any(alias.name == "*" for alias in node.names):
                primitive = "wildcard import"
            elif safe_exports is not None and any(
                alias.name not in safe_exports for alias in node.names
            ):
                primitive = f"unsafe facade export from {imported_base}"
            elif node.level == 0 and imported_root in {"builtins", "importlib"}:
                primitive = node.module or imported_root
            elif (
                node.level == 0
                and imported_root in _RESTRICTED_CAPABILITY_NAMES
                and not _is_explicitly_allowed_external(
                    module.name, imported_root
                )
            ):
                primitive = imported_root
            else:
                for alias in node.names:
                    if (
                        alias.name in _FORBIDDEN_RUNTIME_NAMES
                        or alias.asname in _FORBIDDEN_RUNTIME_NAMES
                        or alias.name in _RESTRICTED_CAPABILITY_NAMES
                    ):
                        primitive = alias.asname or alias.name
                        break
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and module.name != _FIREWALL_MODULE
            and node.value
            in (
                _FORBIDDEN_RUNTIME_NAMES
                | _FORBIDDEN_RUNTIME_ATTRIBUTES
                | _RESTRICTED_CAPABILITY_NAMES
            )
        ):
            primitive = f"sensitive literal {node.value!r}"
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_RUNTIME_NAMES:
            primitive = node.id
        elif (
            isinstance(node, ast.Name)
            and node.id in _RESTRICTED_CAPABILITY_NAMES
            and not _is_explicitly_allowed_external(module.name, node.id)
        ):
            primitive = node.id
        elif isinstance(node, ast.Name) and node.id == "getattr":
            parent = parents.get(node)
            if not isinstance(parent, ast.Call) or parent.func is not node:
                primitive = "getattr"
        elif isinstance(node, ast.Attribute) and node.attr == "compile":
            if not (
                isinstance(node.value, ast.Name)
                and node.value.id in safe_regex_module_aliases
                and isinstance(node.ctx, ast.Load)
            ):
                primitive = node.attr
        elif isinstance(node, ast.Attribute) and node.attr == "__setattr__":
            if not (
                isinstance(node.value, ast.Name)
                and node.value.id == "object"
                and "object" not in rebound_names
                and isinstance(node.ctx, ast.Load)
            ):
                primitive = node.attr
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in _FORBIDDEN_RUNTIME_ATTRIBUTES
        ):
            primitive = node.attr
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in _RESTRICTED_CAPABILITY_NAMES
        ):
            primitive = node.attr
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and forbidden_constant(
                node.args[1],
                _FORBIDDEN_GETATTR_NAMES | _RESTRICTED_CAPABILITY_NAMES,
            )
            is not None
        ):
            primitive = (
                "getattr(..., "
                f"{forbidden_constant(node.args[1], _FORBIDDEN_GETATTR_NAMES | _RESTRICTED_CAPABILITY_NAMES)!r})"
            )
        elif (
            isinstance(node, ast.Subscript)
            and forbidden_constant(
                node.slice,
                _FORBIDDEN_RUNTIME_NAMES
                | _FORBIDDEN_RUNTIME_ATTRIBUTES
                | _RESTRICTED_CAPABILITY_NAMES,
            )
            is not None
        ):
            primitive = (
                "subscript["
                f"{forbidden_constant(node.slice, _FORBIDDEN_RUNTIME_NAMES | _FORBIDDEN_RUNTIME_ATTRIBUTES | _RESTRICTED_CAPABILITY_NAMES)!r}]"
            )
        if primitive is not None:
            location = f"line {getattr(node, 'lineno', '?')}"
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
            explicitly_allowed = _is_explicitly_allowed_external(
                module.name, imported
            )
            if _is_forbidden(imported, forbidden) and not explicitly_allowed:
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
            if imported in guarded_namespace_packages or explicitly_allowed:
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
    """Validate the fixed authoritative ARV2 dependency boundary.

    This wrapper intentionally exposes no package, forbidden-prefix, standard-
    library, or local-module overrides. Tests for the generic traversal use the
    private helper directly; only this fixed wrapper represents the ARV2 guard.
    """

    return _validate_import_closure(
        repository_root,
        package_name="research.analyst_revisions_v2",
        forbidden_prefixes=DEFAULT_FORBIDDEN_IMPORT_PREFIXES,
        allowed_stdlib_roots=DEFAULT_ALLOWED_STDLIB_ROOTS,
        allowed_local_prefixes=(
            "research.analyst_revisions_v2",
            "data.exchange_calendar",
            "data.financial_primitives",
        ),
    )
