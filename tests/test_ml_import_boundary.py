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
