"""Collection guards use real child imports; no custody root is executed.

An absent-fcntl simulation proves the documented unsupported-host treatment.
The child is still required to inherit the test runner's OS network denial.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
PRE_GUARD_COMMIT = "85c7755deb75b5d0c61cc4a63a385d4b87b55110"
GUARDED_FILES = (
    "test_insider_buying_sec_all_form4_parent_ambiguous_diagnostic.py",
    "test_insider_buying_sec_all_form4_parent_ambiguous_diagnostic_verifier.py",
    "test_insider_buying_sec_all_form4_parent_campaign.py",
    "test_insider_buying_sec_all_form4_parent_recovery_campaign.py",
    "test_insider_buying_sec_all_form4_parent_recovery_executor.py",
    "test_insider_buying_sec_all_form4_parent_recovery_partial_verifier.py",
    "test_insider_buying_sec_all_form4_parent_recovery_preflight.py",
    "test_insider_buying_sec_all_form4_parent_recovery_union.py",
    "test_insider_buying_sec_all_form4_parent_recovery_verifier.py",
    "test_insider_buying_sec_parent_refusal_diagnostic.py",
    "test_insider_buying_sec_recovery_v4_capture.py",
    "test_insider_buying_sec_recovery_v4_combined.py",
    "test_insider_buying_sec_recovery_v4_continuation_capture.py",
    "test_insider_buying_sec_recovery_v4_projection.py",
    "test_insider_buying_sec_recovery_v4_reconciliation.py",
    "test_insider_buying_sec_selected_parent_projection_adapter.py",
)
_CHILD = r'''
import importlib.abc
import json
import sys
import pytest

request = json.load(sys.stdin)
sys.path.insert(0, request["root"])
if request["missing_fcntl"]:
    sys.modules.pop("fcntl", None)

class LaneImportReached(RuntimeError):
    pass

class GuardFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if request["missing_fcntl"] and fullname == "fcntl":
            raise ModuleNotFoundError("invented unsupported host: fcntl", name="fcntl")
        if fullname == "research" or fullname.startswith("research."):
            raise LaneImportReached("research import reached: " + fullname)

sys.meta_path.insert(0, GuardFinder())
try:
    exec(compile(request["prefix"], request["filename"], "exec"), {"__name__": "invented_collection_prefix"})
except pytest.skip.Exception as error:
    print(json.dumps({"outcome": "skipped", "reason": str(error)}))
except (ModuleNotFoundError, LaneImportReached) as error:
    print(json.dumps({"outcome": "collection-error", "reason": str(error)}))
else:
    raise AssertionError("collection prefix must reach the poisoned research import or skip")
'''


def _collection_prefix(source: str) -> str:
    """Execute only the header through the first protected import."""
    tree = ast.parse(source)
    for statement in tree.body:
        names = (
            tuple(alias.name for alias in statement.names)
            if isinstance(statement, ast.Import)
            else (statement.module or "",)
            if isinstance(statement, ast.ImportFrom)
            else ()
        )
        if any(name == "research" or name.startswith("research.") for name in names):
            assert statement.end_lineno is not None
            return "\n".join(source.splitlines()[:statement.end_lineno]) + "\n"
    raise AssertionError("guarded test must contain a protected research import")


def _probe(source: str, filename: str, *, missing_fcntl: bool) -> dict[str, str]:
    environment = {
        name: os.environ[name]
        for name in ("PATH", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR")
        if name in os.environ
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", _CHILD],
        input=json.dumps({
            "root": str(ROOT), "prefix": _collection_prefix(source),
            "filename": filename, "missing_fcntl": missing_fcntl,
        }),
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("filename", GUARDED_FILES)
def test_missing_fcntl_skips_before_any_custody_import_and_detects_prior_collection_error(filename):
    path = ROOT / "tests" / filename
    prior = subprocess.run(
        ["git", "show", f"{PRE_GUARD_COMMIT}:tests/{filename}"],
        cwd=ROOT, capture_output=True, text=True, check=True, timeout=20,
    ).stdout
    red = _probe(prior, filename, missing_fcntl=True)
    assert red["outcome"] == "collection-error"
    assert "research import reached" in red["reason"] or "unsupported host: fcntl" in red["reason"]
    green = _probe(path.read_text(encoding="utf-8"), filename, missing_fcntl=True)
    assert green["outcome"] == "skipped"
    assert "IBWIN-CR01" in green["reason"]
    assert "Windows custody port deferred" in green["reason"]


@pytest.mark.parametrize("filename", GUARDED_FILES)
def test_available_fcntl_does_not_skip_supported_host_collection(filename):
    pytest.importorskip("fcntl", reason="IBWIN-CR01: this control needs actual POSIX fcntl")
    source = (ROOT / "tests" / filename).read_text(encoding="utf-8")
    result = _probe(source, filename, missing_fcntl=False)
    assert result["outcome"] == "collection-error"
    assert result["reason"].startswith("research import reached:")


def test_qc_checkout_controls_remain_available_without_custody_platform_guard():
    path = ROOT / "tests" / "test_insider_buying_qc_source_checkout.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"importorskip", "skip"}
        for node in ast.walk(tree)
    )
