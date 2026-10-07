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
        # Only the separately guarded source_audit module may use this narrow
        # standard-library network capability; canonical policy is unchanged.
        forbidden_prefixes=(DEFAULT_FORBIDDEN_IMPORT_PREFIXES - {"http", "ssl", "urllib"})
                           | {"research.target_price_revisions"},
        allowed_stdlib_roots=DEFAULT_ALLOWED_STDLIB_ROOTS | {
            "argparse", "collections", "tempfile", "time", "fractions", "http", "ssl",
            "pwd", "stat", "signal", "contextlib", "urllib", "uuid",
        },
        allowed_local_prefixes=("research.target_price_revisions_development",),
    )
    assert set(modules) == {
        "research",
        "research.target_price_revisions_development",
        "research.target_price_revisions_development.__main__",
        "research.target_price_revisions_development.plan",
        "research.target_price_revisions_development.structural",
        "research.target_price_revisions_development.events",
        "research.target_price_revisions_development.scoring",
        "research.target_price_revisions_development.readiness",
        "research.target_price_revisions_development.simulation",
        "research.target_price_revisions_development.backtesting",
        "research.target_price_revisions_development.fixture_backtest",
        "research.target_price_revisions_development.source_audit",
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


@pytest.mark.parametrize("name", ["scoring", "readiness", "simulation", "backtesting", "fixture_backtest"])
def test_continuous_fixture_modules_have_only_pure_closed_dependencies(name) -> None:
    """New software must not reach D0's reader or any external authority path."""
    source = (ROOT / f"research/target_price_revisions_development/{name}.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed = {"__future__", "dataclasses", "datetime", "decimal", "fractions",
               "hashlib", "json", "re", "typing", "collections"}
    if name == "fixture_backtest":
        allowed.add("argparse")  # Fixed built-in demo, no file/path arguments.
    local_dependencies = {
        "scoring": {"events"},
        "readiness": {"events"},
        "simulation": {"scoring"},
        "backtesting": {"simulation", "scoring", "readiness"},
        "fixture_backtest": {"events", "scoring", "simulation", "readiness", "backtesting"},
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # Every pure-module edge is explicit; no D0 I/O facade or
            # canonical/provider/operator/engine authority is reachable.
            local = node.level == 1 and (
                node.module in local_dependencies[name]
                or (node.module is None and all(alias.name in local_dependencies[name] for alias in node.names))
            )
            assert local or (node.level == 0 and node.module.split(".")[0] in allowed)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "__import__", "eval", "exec", "compile", "input"}


def test_readiness_binds_only_the_two_approved_d0_aggregate_identities() -> None:
    from research.target_price_revisions_development import readiness

    assert readiness.D0_PLAN_SHA256 == "15e0b00978d4060ae3d6b827474e320df2003c9ceee529c8a8436b31570b7bcb"
    assert readiness.D0_REPORT_SHA256 == "fbe99ce620689c61052330a220b9f989b29a8ea732a45204d88b02e6f5648148"
    assert digest((ARTIFACTS / f"tpr-d0-plan.{readiness.D0_PLAN_SHA256}.json").read_bytes()) == readiness.D0_PLAN_SHA256
    assert digest((ARTIFACTS / f"tpr-d0-structure.{readiness.D0_REPORT_SHA256}.json").read_bytes()) == readiness.D0_REPORT_SHA256
    assert all(key not in readiness.REQUIREMENTS for key in ("approved_by_owner", "preauthorized"))


def test_source_auditor_is_separate_from_pure_fixtures_and_authority_packages() -> None:
    """Its explicit I/O capability must not widen any pure-module dependencies."""
    source = (ROOT / "research/target_price_revisions_development/source_audit.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    allowed = {"__future__", "hashlib", "http", "json", "os", "pwd", "re", "signal",
               "ssl", "stat", "subprocess", "threading", "time", "uuid", "contextlib",
               "dataclasses", "datetime", "decimal", "pathlib", "typing", "urllib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module.split(".")[0] in allowed
    # Importing constants/type declarations is not permission to activate I/O.
    # All top-level calls are inert constructors of fixed objects, not providers.
    for node in tree.body:
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant) and type(node.value.value) is str
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    assert isinstance(child.func, ast.Name)
                    assert child.func.id in {"Path", "AuditRequest"}
    assert "api.massive.com" in source and "api.sharadar.com" in source
    initializer = ast.parse((ROOT / "research/target_price_revisions_development/__init__.py").read_text(encoding="utf-8"))
    assert all(isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
               and type(node.value.value) is str for node in initializer.body)
    for path in (ROOT / "research/target_price_revisions_development").glob("*.py"):
        if path.name == "source_audit.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any(name.split(".")[0] in {"http", "ssl", "urllib"}
                           or "source_audit" in name.split(".") for name in names)
            if isinstance(node, ast.ImportFrom) and node.module is None:
                assert all(alias.name != "source_audit" for alias in node.names)


def test_committed_source_probe_is_exact_non_authorizing_aggregate_not_a_retry() -> None:
    """Read only the approved public plan/report; never activate the collector."""
    import hashlib
    import json
    from research.target_price_revisions_development.source_audit import AuditPlan

    plan_sha = "cdee4d603e8d2b232759f8f4e557d8786dea62393b0dc489d449a6970164048b"
    report_sha = "7688106002c12f1460b05fd0aaa39f0d8b5970d73326289774933a137c420cb2"
    plan_payload = (ARTIFACTS / f"tpr-source-audit-plan.{plan_sha}.json").read_bytes()
    report_payload = (ARTIFACTS / f"tpr-source-audit-report.{report_sha}.json").read_bytes()
    assert hashlib.sha256(plan_payload).hexdigest() == plan_sha
    assert hashlib.sha256(report_payload).hexdigest() == report_sha
    plan = AuditPlan(plan_payload, plan_sha).body()
    body = json.loads(report_payload)
    assert body["plan_sha256"] == plan_sha
    source_sha = hashlib.sha256((ROOT / "research/target_price_revisions_development/source_audit.py").read_bytes()).hexdigest()
    assert body["code_sha256"] == plan["code_sha256"] == source_sha
    assert plan["git_sha"] == body["git_sha"] == "683bdc4a21c4374d0091d5958d8ddb98b9f00d3a"
    assert body["mode"] == "production" and body["status"] == "COMPLETED"
    assert body["provider_requests"] == 2 and body["fixture_transport_calls"] == 0
    assert body["response_bytes"] == 1237 and body["response_bytes_complete"] is True
    massive, sharadar = body["providers"]
    assert massive["provider"] == "massive" and massive["http_status"] == 200
    assert massive["rows_observed"] == 1 and massive["disposition"] == "field_presence_observed"
    assert massive["field_presence"]["price_target"] == 1
    assert massive["field_presence"]["price_target_horizon"] == 0
    assert massive["field_presence"]["previous_price_target_horizon"] == 0
    assert set(massive) == {"provider", "http_status", "disposition", "authenticated_access_observed",
                            "response_bytes", "response_bytes_complete", "response_sha256",
                            "rows_observed", "field_presence"}
    assert sharadar["provider"] == "sharadar" and sharadar["http_status"] == 200
    assert sharadar["disposition"] == "body_schema_refused"
    assert sharadar["metadata"] == {"metadata_shape_observed": False, "size_bytes": None, "snapshot_utc": None}
    assert set(sharadar) == {"provider", "http_status", "disposition", "authenticated_access_observed",
                            "response_bytes", "response_bytes_complete", "response_sha256", "metadata"}
    assert all(value is False for value in body["authority"].values())
    assert body["outcome_reads"] == body["qc_attempts"] == body["development_looks"] == 0
    assert body["real_development_backtest_ready"] is False
    assert body["license_entitlement"] == body["point_in_time_facts"] == "unestablished"
    assert body["canonical_admission"] is False and body["d0_renewed"] is False
    assert datetime.fromisoformat(plan["created_utc"]) <= datetime.fromisoformat(body["started_utc"]) < datetime.fromisoformat(plan["expires_utc"])
    assert set(body) == {"schema", "audit_id", "mode", "status", "started_utc", "plan_sha256",
                         "code_sha256", "git_sha", "owner_instruction_sha256", "providers",
                         "provider_requests", "fixture_transport_calls", "response_bytes",
                         "response_bytes_complete", "authority", "license_entitlement",
                         "point_in_time_facts", "working_assumption", "real_development_backtest_ready",
                         "canonical_admission", "d0_renewed", "outcome_reads", "qc_attempts", "development_looks"}
