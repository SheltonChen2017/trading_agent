"""D0 artifacts and dependency boundaries; no licensed rows are read here."""
from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import pytest

from research.target_price_revisions.import_firewall import (
    DEFAULT_ALLOWED_STDLIB_ROOTS, DEFAULT_FORBIDDEN_IMPORT_PREFIXES, ImportBoundaryError,
    _validate_import_closure,
)
from research.target_price_revisions_development.plan import (
    CANONICAL_HASHES, SOURCE_PROFILE, digest, load_plan, strict_artifact,
)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "research/target_price_revisions_development/artifacts"


def test_development_import_closure_cannot_reach_canonical_or_other_authority() -> None:
    modules = _validate_import_closure(
        ROOT, package_name="research.target_price_revisions_development",
        forbidden_prefixes=DEFAULT_FORBIDDEN_IMPORT_PREFIXES | {"research.target_price_revisions"},
        allowed_stdlib_roots=DEFAULT_ALLOWED_STDLIB_ROOTS | {"argparse", "collections", "tempfile", "time"},
        allowed_local_prefixes=("research.target_price_revisions_development",),
    )
    assert set(modules) == {
        "research",
        "research.target_price_revisions_development",
        "research.target_price_revisions_development.__main__",
        "research.target_price_revisions_development.plan",
        "research.target_price_revisions_development.structural",
        "research.target_price_revisions_development.events",
    }
    assert (ROOT / "research/__init__.py").read_bytes() == b""


@pytest.mark.parametrize("forbidden", ["data", "research.target_price_revisions", "research.analyst_revisions_v2",
                                       "research.quantconnect", "requests", "assistant", "execution", "ml"])
def test_transitive_development_import_escape_refuses(tmp_path, forbidden) -> None:
    package = tmp_path / "research/target_price_revisions_development"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("from .module import value\n", encoding="utf-8")
    (package / "module.py").write_text("from .facade import value\n", encoding="utf-8")
    (package / "facade.py").write_text(f"import {forbidden}\nvalue = 1\n", encoding="utf-8")
    with pytest.raises(ImportBoundaryError):
        _validate_import_closure(
            tmp_path, package_name="research.target_price_revisions_development",
            forbidden_prefixes=DEFAULT_FORBIDDEN_IMPORT_PREFIXES | {"research.target_price_revisions"},
            allowed_stdlib_roots=DEFAULT_ALLOWED_STDLIB_ROOTS | {"argparse", "collections", "tempfile", "time"},
            allowed_local_prefixes=("research.target_price_revisions_development",),
        )


def test_recorded_real_audit_binds_current_code_and_zero_outcome_contract(aggregate_only) -> None:
    plans = list(ARTIFACTS.glob("tpr-d0-plan.*.json"))
    reports = list(ARTIFACTS.glob("tpr-d0-structure.*.json"))
    assert len(plans) == len(reports) == 1
    plan_bytes = plans[0].read_bytes()
    plan = load_plan(plan_bytes, digest(plan_bytes))
    assert plans[0].name == f"tpr-d0-plan.{plan.sha256}.json"
    report_bytes = reports[0].read_bytes()
    report = strict_artifact(report_bytes)
    # TPR-CR16-001: the pushed report itself must satisfy the closed contract.
    aggregate_only(report)
    assert reports[0].name == f"tpr-d0-structure.{digest(report_bytes)}.json"
    assert report["plan_sha256"] == plan.sha256
    assert report["source_manifest_sha256"] == SOURCE_PROFILE["manifest_sha256"]
    assert report["input"] == {"pages": SOURCE_PROFILE["pages"], "rows": SOURCE_PROFILE["rows"], "bytes": SOURCE_PROFILE["bytes"]}
    assert sum(bucket["rows"] for bucket in report["years"].values()) == SOURCE_PROFILE["rows"]
    assert set(report["auditor_code_sha256"]) == {
        "research/target_price_revisions_development/" + name
        for name in ("__init__.py", "plan.py", "structural.py", "__main__.py")
    }
    for relative, expected in report["auditor_code_sha256"].items():
        assert digest((ROOT / relative).read_bytes()) == expected
    for relative, expected in CANONICAL_HASHES.items():
        assert digest((ROOT / relative).read_bytes()) == expected
    clock = datetime.fromisoformat(report["audit_as_of_utc"])
    assert clock.tzinfo is not None
    assert plan.body()["created_on"] <= clock.date().isoformat() <= SOURCE_PROFILE["expires_on"]
    for field in ("provider_requests", "outcome_reads", "qc_attempts", "development_looks"):
        assert type(report[field]) is int
        assert report[field] == 0
    for field in ("point_in_time_data", "canonical_admission", "trading_authority"):
        assert report[field] is False
    assert report["confirmatory_alpha"] == "0"


def test_d1_fixture_module_has_no_io_or_authority_dependencies() -> None:
    """D1 stays independent of D0's retained-reader and publication helpers."""
    source = (ROOT / "research/target_price_revisions_development/events.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed = {"__future__", "dataclasses", "datetime", "decimal", "re", "typing"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module.split(".")[0] in allowed
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "__import__", "eval", "exec", "compile", "input"}
    # The imported ancestor initializers are deliberately inert; the package
    # does not expose D0's I/O by executing a facade at import time.
    assert (ROOT / "research/__init__.py").read_bytes() == b""
    initializer = ast.parse((ROOT / "research/target_price_revisions_development/__init__.py").read_text(encoding="utf-8"))
    assert all(isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
               and type(node.value.value) is str for node in initializer.body)


def test_d0_aggregate_defects_are_context_not_new_source_evidence(aggregate_only) -> None:
    """Use only the approved committed report; never reconstruct/read rows."""
    path = ARTIFACTS / "tpr-d0-structure.fbe99ce620689c61052330a220b9f989b29a8ea732a45204d88b02e6f5648148.json"
    payload = path.read_bytes()
    assert digest(payload) == "fbe99ce620689c61052330a220b9f989b29a8ea732a45204d88b02e6f5648148"
    report = strict_artifact(payload)
    aggregate_only(report)
    buckets = tuple(report["years"].values())
    for name, expected in (("direction_disagrees", 225), ("raise_action_conflict", 307),
                           ("lower_action_conflict", 404), ("maintain_action_conflict", 24)):
        assert sum(bucket["pairs"][name] for bucket in buckets) == expected
    assert report["point_in_time_data"] is False and report["canonical_admission"] is False
    assert report["interpretation"]["horizon"] == "presence probes do not prove explicit comparable prior/new horizons"
