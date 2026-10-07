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
        # Only the separately guarded source collectors may use this narrow
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
        "research.target_price_revisions_development.sharadar_diagnostic",
        "research.target_price_revisions_development.sharadar_shape",
        "research.target_price_revisions_development.sharadar_projection",
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
        if path.name in {"source_audit.py", "sharadar_diagnostic.py", "sharadar_shape.py"}:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any(name.split(".")[0] in {"http", "ssl", "urllib"}
                           or set(name.split(".")) & {"source_audit", "sharadar_diagnostic", "sharadar_shape"} for name in names)
            if isinstance(node, ast.ImportFrom) and node.module is None:
                assert all(alias.name not in {"source_audit", "sharadar_diagnostic", "sharadar_shape"} for alias in node.names)


def test_sharadar_diagnostic_can_only_compose_the_frozen_source_primitives() -> None:
    """A separate scoped I/O command is not a facade for pure feature modules."""
    path = ROOT / "research/target_price_revisions_development/sharadar_diagnostic.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    allowed = {"__future__", "json", "os", "re", "stat", "dataclasses", "datetime",
               "decimal", "pathlib", "typing"}
    helper_names = {"AUTHORITY", "LANE_BRANCH", "LANE_ROOT", "PRIVATE_ROOT", "REQUESTS",
                    "SourceAuditError", "_canonical", "_clock", "_digest", "_https_get",
                    "_private_directory", "_production_credential", "_publish", "_reduce_response",
                    "_source_object", "_valid_credential", "_verify_execution_identity"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert node.level == 1 and node.module == "source_audit"
                assert {alias.name for alias in node.names} <= helper_names
            else:
                assert node.module.split(".")[0] in allowed
    for node in tree.body:
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant) and type(node.value.value) is str
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            assert not any(isinstance(child, ast.Call) for child in ast.walk(node))


def test_committed_sharadar_diagnostic_pins_the_observed_shape_without_credentials():
    import hashlib
    import json
    from research.target_price_revisions_development.sharadar_diagnostic import DiagnosticPlan

    plan_sha = "59db4a4bb61d6f24b3127a171e1eeef9d80ff20a7b11b21991db408cc2211ca8"
    report_sha = "a547f0aed14af2cef2ad3bdcbb2e233fb937be417181829552d7219485ff178b"
    plan_payload = (ARTIFACTS / f"tpr-sharadar-diagnostic-plan.{plan_sha}.json").read_bytes()
    report_payload = (ARTIFACTS / f"tpr-sharadar-diagnostic-report.{report_sha}.json").read_bytes()
    assert hashlib.sha256(plan_payload).hexdigest() == plan_sha
    assert hashlib.sha256(report_payload).hexdigest() == report_sha
    plan = DiagnosticPlan(plan_payload, plan_sha).body()
    body = json.loads(report_payload)
    assert body["plan_sha256"] == plan_sha
    assert body["git_sha"] == plan["git_sha"] == "9cc45dd5ca2a4de68d441e0c9871c4d016468889"
    source_sha = hashlib.sha256((ROOT / "research/target_price_revisions_development/sharadar_diagnostic.py").read_bytes()).hexdigest()
    assert body["code_sha256"] == plan["code_sha256"] == source_sha
    assert body["auditor_code_sha256"] == "9f2674a47d0d62bb09e2dd5ba1ce7f37eed3c68dce254e40e0d11d1218f46960"
    assert body["mode"] == "production" and body["status"] == "COMPLETED"
    assert body["provider_requests"] == 1 and body["fixture_transport_calls"] == 0
    assert body["provider"]["http_status"] == 200
    assert body["provider"]["response_bytes"] == 233
    assert body["provider"]["response_bytes_complete"] is True
    assert body["provider"]["response_sha256"] == "f03a9474e80224ccbef720ee7a78c21a259cfe355d17ed6388446f631ea5dd9c"
    diagnosis = body["diagnosis"]
    assert diagnosis["classification"] == "metadata_schema_mismatch"
    assert diagnosis["application_error"] is None
    assert diagnosis["table_literal"] == "lower"
    assert diagnosis["clauses"] == ["unexpected_keys", "missing_modified", "missing_name", "missing_size", "missing_sizeLabel"]
    assert diagnosis["shape"] == {"fields": {"table": "string", **dict.fromkeys(
        ("name", "size", "sizeLabel", "modified", "status", "code", "error", "message"), "absent")},
        "unknown_key_count": 1}
    assert diagnosis["metadata"] == {"metadata_shape_observed": False, "size_bytes": None, "snapshot_utc": None}
    assert body["credential_state"] == "not_proven"
    assert body["license_entitlement"] == body["point_in_time_facts"] == "unestablished"
    assert body["real_development_backtest_ready"] is False
    assert body["d0_renewed"] is False and body["original_audit_renewed"] is False
    assert body["outcome_reads"] == body["qc_attempts"] == body["development_looks"] == 0
    assert all(value is False for value in body["authority"].values())
    assert datetime.fromisoformat(plan["created_utc"]) <= datetime.fromisoformat(body["started_utc"]) < datetime.fromisoformat(plan["expires_utc"])
    assert set(body) == {"schema", "diagnostic_id", "mode", "status", "started_utc", "plan_sha256",
        "code_sha256", "auditor_code_sha256", "git_sha", "owner_instruction_sha256", "provider",
        "diagnosis", "credential_state", "provider_requests", "fixture_transport_calls", "authority",
        "license_entitlement", "point_in_time_facts", "real_development_backtest_ready", "canonical_admission",
        "d0_renewed", "original_audit_renewed", "outcome_reads", "qc_attempts", "development_looks"}


def test_richer_shape_collector_is_inert_and_only_composes_frozen_primitives():
    path = ROOT / "research/target_price_revisions_development/sharadar_shape.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    allowed = {"__future__", "os", "re", "stat", "dataclasses", "datetime",
               "decimal", "pathlib", "typing"}
    helper_names = {"AUTHORITY", "LANE_BRANCH", "LANE_ROOT", "PRIVATE_ROOT", "REQUESTS",
                    "SourceAuditError", "_canonical", "_clock", "_digest", "_https_get",
                    "_private_directory", "_production_credential", "_publish", "_reduce_response",
                    "_source_object", "_valid_credential", "_verify_execution_identity"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert node.level == 1 and node.module == "source_audit"
                assert {alias.name for alias in node.names} <= helper_names
            else:
                assert node.module.split(".")[0] in allowed
    for node in tree.body:
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant) and type(node.value.value) is str
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    assert isinstance(child.func, ast.Name) and child.func.id == "frozenset"
                    assert len(child.args) == 1 and not child.keywords
                    assert isinstance(child.args[0], ast.Tuple)
                    assert all(isinstance(item, ast.Constant) and type(item.value) is str
                               for item in child.args[0].elts)


def test_committed_richer_inspection_records_opaque_failure_not_verified_mapping():
    import hashlib
    import json
    from research.target_price_revisions_development.sharadar_shape import ShapePlan

    plan_sha = "5c71dd12612d267d5e16e991c6c3875a9bd27e71f19ad2d51840261914bbe436"
    report_sha = "5912ff27e6da8c4ebf0abe60367e83c7d7158b9490bd3e55541dfcbb1e021f88"
    plan_payload = (ARTIFACTS / f"tpr-sharadar-shape-plan.{plan_sha}.json").read_bytes()
    report_payload = (ARTIFACTS / f"tpr-sharadar-shape-report.{report_sha}.json").read_bytes()
    assert hashlib.sha256(plan_payload).hexdigest() == plan_sha
    assert hashlib.sha256(report_payload).hexdigest() == report_sha
    plan = ShapePlan(plan_payload, plan_sha).body()
    report = json.loads(report_payload)
    source_sha = hashlib.sha256((ROOT / "research/target_price_revisions_development/sharadar_shape.py").read_bytes()).hexdigest()
    assert report["code_sha256"] == plan["code_sha256"] == source_sha
    assert report["plan_sha256"] == plan_sha
    assert report["git_sha"] == plan["git_sha"] == "82461d40aae88fba4f928a94552245c4b9000fed"
    assert report["status"] == "COMPLETED" and report["mode"] == "production"
    assert report["provider_requests"] == 1 and report["fixture_transport_calls"] == 0
    assert report["provider"]["http_status"] == 200
    assert report["provider"]["response_bytes"] == 233
    assert report["provider"]["response_bytes_complete"] is True
    assert report["provider"]["response_sha256"] is None
    diagnosis = report["diagnosis"]
    assert diagnosis["classification"] == "metadata_shape_unmapped"
    assert diagnosis["profile"] == "unmapped" and diagnosis["table_literal"] == "lower"
    assert diagnosis["application_error"] is None and diagnosis["shape_budget_refused"] is False
    assert diagnosis["metadata"] == {"metadata_shape_observed": False, "size_bytes": None, "snapshot_utc": None}
    assert len(diagnosis["nodes"]) == 2
    root, files = diagnosis["nodes"]
    assert root == {"path": "root", "kind": "object", "fields": dict.fromkeys(
        ("code", "downloadUrl", "download_url", "error", "filename", "lastModified", "last_modified",
         "link", "message", "modified", "name", "path", "size", "sizeLabel", "size_label", "status",
         "type", "url", "years"), "absent") | {"table": "string"}, "unknown_key_count": 0,
        "unknown_types": {}, "components": dict.fromkeys(
            ("modified_utc_valid", "name_valid", "size_label_valid", "size_valid"), False), "selector": "not_selector"}
    assert files == {"kind": "array", "length": 1, "opaque": True, "path": "root/files"}
    assert report["credential_state"] == "not_proven"
    assert report["license_entitlement"] == report["point_in_time_facts"] == "unestablished"
    assert report["real_development_backtest_ready"] is False and report["canonical_admission"] is False
    assert report["d0_renewed"] is report["original_audit_renewed"] is report["previous_diagnostic_renewed"] is False
    assert report["outcome_reads"] == report["qc_attempts"] == report["development_looks"] == 0
    assert all(value is False for value in report["authority"].values())
    assert set(report) == {"schema", "shape_id", "mode", "status", "started_utc", "plan_sha256", "code_sha256",
        "auditor_code_sha256", "git_sha", "owner_instruction_sha256", "provider", "diagnosis", "credential_state",
        "provider_requests", "fixture_transport_calls", "authority", "license_entitlement", "point_in_time_facts",
        "real_development_backtest_ready", "canonical_admission", "d0_renewed", "original_audit_renewed",
        "previous_diagnostic_renewed", "outcome_reads", "qc_attempts", "development_looks"}


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
