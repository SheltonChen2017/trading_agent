"""Import-boundary regression for the overlay shadow layer (POST-002).

Mirrors tests/test_ml_import_boundary.py's AST-walk shape in both
directions: no execution-capable module may import
``assistant.overlay_shadow``, and ``assistant.overlay_shadow`` itself may
import neither ``ml`` nor any execution-capable module. Direct imports
only, like the ml test; green here is not proof of transitive closure.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_EXECUTION_CAPABLE_PATHS = (
    REPO_ROOT / "execution",
    REPO_ROOT / "risk" / "execution_gate.py",
    REPO_ROOT / "assistant" / "execution_service.py",
    REPO_ROOT / "assistant" / "allocation_batch.py",
)
_OVERLAY_MODULE = REPO_ROOT / "assistant" / "overlay_shadow.py"
_FORBIDDEN_FOR_OVERLAY = ("ml", "execution", "assistant.execution_service",
                          "assistant.allocation_batch", "risk.execution_gate")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


def _execution_files():
    for path in _EXECUTION_CAPABLE_PATHS:
        if path.is_dir():
            yield from path.rglob("*.py")
        elif path.exists():
            yield path


def test_no_execution_capable_module_imports_overlay_shadow():
    offenders = []
    for path in _execution_files():
        for name in _imports(path):
            if name == "assistant.overlay_shadow" or name.startswith(
                "assistant.overlay_shadow."
            ):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        "execution-capable modules must not import the overlay shadow "
        f"layer: {sorted(set(offenders))}"
    )


def test_overlay_shadow_imports_no_ml_or_execution_module():
    offenders = [
        name for name in _imports(_OVERLAY_MODULE)
        if any(name == root or name.startswith(root + ".")
               for root in _FORBIDDEN_FOR_OVERLAY)
    ]
    assert not offenders, (
        "assistant/overlay_shadow.py must stay free of ml and execution "
        f"imports: {offenders}"
    )
