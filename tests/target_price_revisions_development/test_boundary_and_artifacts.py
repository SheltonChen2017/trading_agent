"""D0 artifacts and dependency boundaries; no licensed rows are read here."""
from __future__ import annotations

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
