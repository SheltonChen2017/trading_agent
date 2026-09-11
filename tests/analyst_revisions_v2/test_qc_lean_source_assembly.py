"""Offline contract tests for ARV2-4F-B5B LEAN source assembly."""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import json
import linecache
from pathlib import Path
import sys
import types

import pytest

from research.analyst_revisions_v2_qc import lean_source_assembly as assembly_module
from research.analyst_revisions_v2_qc import (
    object_store_read_contract as b4_module,
)
from research.analyst_revisions_v2_qc import synthetic_input_transport as b3_module
from research.analyst_revisions_v2_qc.lean_source_assembly import (
    ASSEMBLY_PUBLIC_FIELD_NAMES,
    ASSEMBLY_TRUTH_FIELD_VALUES,
    AUTHORITY,
    CAPABILITIES,
    DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
    ENTRY_CLASS_NAME,
    ENTRY_PROJECT_PATH,
    EXPECTED_OBJECT_STORE_CALL_COUNT,
    EXPECTED_SOURCE_FILES,
    EXTERNAL_BINDINGS,
    FORMAL_PRIMARY_FOLD_IDS,
    ExpectedLeanSource,
    LeanObjectStoreCallBinding,
    LeanSourceInput,
    QcLeanSourceAssemblyError,
    SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID,
    SCHEMA_SHA256,
    STATUS,
    SyntheticLeanProjectAssembly,
    SyntheticLeanProjectFile,
    build_synthetic_qc_lean_source_assembly,
    render_qc_lean_source_assembly_schema_bytes,
    require_synthetic_qc_lean_source_assembly,
)
from research.analyst_revisions_v2_qc.object_store_read_contract import (
    CAPABILITIES as B4_CAPABILITIES,
    EXTERNAL_BINDINGS as B4_EXTERNAL_BINDINGS,
    SCHEMA_ARTIFACT_SHA256 as B4_SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID as B4_SCHEMA_ID,
    SCHEMA_SHA256 as B4_SCHEMA_SHA256,
)
from research.analyst_revisions_v2_qc.synthetic_input_transport import (
    FALSE_PROPERTY_NAMES,
)
from tests.analyst_revisions_v2.test_qc_object_store_read_contract import (
    _no_io_violations,
    _plan,
)


ROOT = Path(__file__).resolve().parents[2]
MODULE = (
    ROOT
    / "research"
    / "analyst_revisions_v2_qc"
    / "lean_source_assembly.py"
)
EXPECTED_CALL_SURFACE = (
    464,
    "f67d1c44bd7ce16ddba3cc52a5d141bf7081dd9a26ded7b418955eadcd9bdb41",
)
EXPECTED_MODULE_AST_SHA256 = (
    "4a693c3ae78e7536b98deeb66aa3cf03273e015953b4f0321eea29507f4722f9"
)
EXPECTED_SOURCE_LOCATIONS = (
    (
        "lean_entry",
        "research/lean/analyst_revisions_v2_scaffold.py",
        "main.py",
    ),
    ("research_package_marker", "research/__init__.py", "research/__init__.py"),
    (
        "qc_package_marker",
        "research/analyst_revisions_v2_qc/__init__.py",
        "research/analyst_revisions_v2_qc/__init__.py",
    ),
    (
        "event_study_core",
        "research/analyst_revisions_v2_qc/event_study.py",
        "research/analyst_revisions_v2_qc/event_study.py",
    ),
    (
        "global_input_bundle",
        "research/analyst_revisions_v2_qc/global_input_bundle.py",
        "research/analyst_revisions_v2_qc/global_input_bundle.py",
    ),
    (
        "global_input_schema",
        "research/analyst_revisions_v2_qc/global_input_schema.py",
        "research/analyst_revisions_v2_qc/global_input_schema.py",
    ),
    (
        "object_store_read_contract",
        "research/analyst_revisions_v2_qc/object_store_read_contract.py",
        "research/analyst_revisions_v2_qc/object_store_read_contract.py",
    ),
    (
        "run_contract",
        "research/analyst_revisions_v2_qc/run_contract.py",
        "research/analyst_revisions_v2_qc/run_contract.py",
    ),
    (
        "synthetic_input_transport",
        "research/analyst_revisions_v2_qc/synthetic_input_transport.py",
        "research/analyst_revisions_v2_qc/synthetic_input_transport.py",
    ),
    ("data_package_marker", "data/__init__.py", "data/__init__.py"),
    (
        "exchange_calendar",
        "data/exchange_calendar.py",
        "data/exchange_calendar.py",
    ),
)
EXPECTED_ASSEMBLY_PUBLIC_FIELD_NAMES = (
    "assembly_id",
    "assembly_hash",
    "assembly_artifact_sha256",
    "entry_project_path",
    "entry_class_name",
    "files",
    "object_store_calls",
    "plan_id",
    "plan_hash",
    "plan_artifact_sha256",
    "run_candidate_id",
    "run_candidate_hash",
    "total_source_byte_count",
    "largest_project_file_byte_count",
    "source_only",
    "adapter_call_contract_present",
    "physical_adapter_present",
    "real_qc_object_store_access_performed",
    "project_created",
    "cloud_compile_performed",
    "backtest_performed",
    "external_bindings",
    "capabilities",
)
EXPECTED_DATACLASS_FIELDS = {
    ExpectedLeanSource: (
        "role",
        "repository_path",
        "project_path",
        "byte_count",
        "sha256",
    ),
    LeanSourceInput: (
        "role",
        "repository_path",
        "project_path",
        "source_bytes",
    ),
    LeanObjectStoreCallBinding: (
        "ordinal",
        "operation",
        "method_name",
        "object_store_key",
        "expected_found",
        "expected_byte_count",
        "expected_sha256",
    ),
    SyntheticLeanProjectFile: (
        "role",
        "repository_path",
        "project_path",
        "source_bytes",
        "byte_count",
        "sha256",
    ),
    SyntheticLeanProjectAssembly: (
        *EXPECTED_ASSEMBLY_PUBLIC_FIELD_NAMES,
        "_plan",
        "_run_candidate",
        "_canonical_document",
    ),
}
EXPECTED_DATACLASS_FIELD_TYPES = {
    ExpectedLeanSource: {
        "role": str,
        "repository_path": str,
        "project_path": str,
        "byte_count": int,
        "sha256": str,
    },
    LeanSourceInput: {
        "role": str,
        "repository_path": str,
        "project_path": str,
        "source_bytes": bytes,
    },
    LeanObjectStoreCallBinding: {
        "ordinal": int,
        "operation": str,
        "method_name": str,
        "object_store_key": str,
        "expected_found": bool | None,
        "expected_byte_count": int | None,
        "expected_sha256": str | None,
    },
    SyntheticLeanProjectFile: {
        "role": str,
        "repository_path": str,
        "project_path": str,
        "source_bytes": bytes,
        "byte_count": int,
        "sha256": str,
    },
    SyntheticLeanProjectAssembly: {
        "assembly_id": str,
        "assembly_hash": str,
        "assembly_artifact_sha256": str,
        "entry_project_path": str,
        "entry_class_name": str,
        "files": tuple[SyntheticLeanProjectFile, ...],
        "object_store_calls": tuple[LeanObjectStoreCallBinding, ...],
        "plan_id": str,
        "plan_hash": str,
        "plan_artifact_sha256": str,
        "run_candidate_id": str,
        "run_candidate_hash": str,
        "total_source_byte_count": int,
        "largest_project_file_byte_count": int,
        "source_only": bool,
        "adapter_call_contract_present": bool,
        "physical_adapter_present": bool,
        "real_qc_object_store_access_performed": bool,
        "project_created": bool,
        "cloud_compile_performed": bool,
        "backtest_performed": bool,
        "external_bindings": tuple[tuple[str, None], ...],
        "capabilities": tuple[tuple[str, bool], ...],
        "_plan": assembly_module.SyntheticQcObjectStoreReadPlan,
        "_run_candidate": assembly_module.SyntheticQcRunCandidate,
        "_canonical_document": bytes,
    },
}


def _builtin_io_escape_violations(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    violations: list[str] = []
    forbidden_names = {
        "__import__",
        "breakpoint",
        "eval",
        "exec",
        "input",
        "open",
    }
    forbidden_attributes = {
        "get_data",
        "open",
        "read",
        "read_bytes",
        "read_text",
        "write",
        "write_bytes",
        "write_text",
    }
    forbidden_literals = forbidden_names | {
        "__import__",
        "get_data",
    }
    parent_by_child = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and type(node.value) is str
            and node.value in forbidden_literals
        ):
            violations.append(f"literal:{node.value}")
        if isinstance(node, ast.Name) and node.id == "__builtins__":
            parent = parent_by_child.get(node)
            grandparent = parent_by_child.get(parent) if parent else None
            if not (
                isinstance(parent, ast.Assign)
                and len(parent.targets) == 1
                and isinstance(parent.targets[0], ast.Name)
                and parent.targets[0].id == "_PINNED_BUILTINS_DICT"
                and parent.value is node
                and isinstance(grandparent, ast.Module)
            ):
                violations.append("name:__builtins__")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in forbidden_names
        ):
            violations.append(f"call:{node.func.id}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in forbidden_attributes
        ):
            violations.append(f"attribute-call:{node.func.attr}")
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "__builtins__"
        ):
            violations.append("subscript:__builtins__")
    return tuple(violations)


def _call_surface_fingerprint(source: str) -> tuple[int, str]:
    tree = ast.parse(source)
    calls: list[str] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope = ["<module>"]

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_Call(self, node: ast.Call) -> None:
            calls.append(
                f"{self.scope[-1]}\x00"
                + ast.dump(node, include_attributes=False)
            )
            self.generic_visit(node)

    Visitor().visit(tree)
    payload = "\n".join(sorted(calls)).encode("utf-8")
    return len(calls), hashlib.sha256(payload).hexdigest()


def _module_ast_fingerprint(source: str) -> str:
    tree = ast.parse(source)
    payload = ast.dump(tree, include_attributes=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _source_inputs() -> tuple[LeanSourceInput, ...]:
    return tuple(
        LeanSourceInput(
            role=item.role,
            repository_path=item.repository_path,
            project_path=item.project_path,
            source_bytes=(ROOT / item.repository_path).read_bytes(),
        )
        for item in EXPECTED_SOURCE_FILES
    )


def _assembly():
    candidate, fixture, plan = _plan()
    value = build_synthetic_qc_lean_source_assembly(
        run_candidate=candidate,
        read_plan=plan,
        source_files=_source_inputs(),
    )
    return candidate, fixture, plan, value


def test_schema_identity_truth_and_residuals_are_exact() -> None:
    payload = render_qc_lean_source_assembly_schema_bytes()
    assert payload.endswith(b"\n")
    assert hashlib.sha256(payload).hexdigest() == SCHEMA_ARTIFACT_SHA256
    assert SCHEMA_ID == "arv2-qc-lean-source-assembly-ae4c1324f36cc6fc"
    assert SCHEMA_SHA256 == (
        "ae4c1324f36cc6fca0218f474bdc091bf82862e8f21ada35e01a09b022bb77a5"
    )
    assert SCHEMA_ARTIFACT_SHA256 == (
        "532aeb471fed96c525f8be9db84694c546c1cccc6008347a43efadfac678ac20"
    )
    document = json.loads(payload)
    assert set(document) == {
        "schema",
        "status",
        "authority",
        "schema_id",
        "schema_sha256",
        "parents",
        "entry",
        "source_files",
        "object_store_call_contract",
        "evaluation_windows",
        "truth",
        "residuals",
        "external_bindings",
        "capabilities",
    }
    assert document["schema"] == "arv2-qc-lean-source-assembly-schema-v1"
    assert document["status"] == STATUS == (
        "offline_source_inventory_authenticated_runtime_refuses"
    )
    assert document["authority"] == AUTHORITY == (
        "offline_values_only_no_client_callback_filesystem_environment_"
        "provider_credential_account_project_object_store_upload_compile_"
        "launch_result_deployment_order_or_trading_authority"
    )
    assert document["schema_id"] == SCHEMA_ID
    assert document["schema_sha256"] == SCHEMA_SHA256
    b4_source = next(
        item
        for item in EXPECTED_SOURCE_FILES
        if item.role == "object_store_read_contract"
    )
    assert document["parents"] == {
        "b4_schema_id": B4_SCHEMA_ID,
        "b4_schema_sha256": B4_SCHEMA_SHA256,
        "b4_schema_artifact_sha256": B4_SCHEMA_ARTIFACT_SHA256,
        "b4_source_sha256": b4_source.sha256,
        "b4_source_byte_count": b4_source.byte_count,
        "scaffold_schema": "arv2-qc-lean-entry-scaffold-v2",
        "scaffold_source_sha256": EXPECTED_SOURCE_FILES[0].sha256,
        "scaffold_source_byte_count": EXPECTED_SOURCE_FILES[0].byte_count,
    }
    assert document["entry"] == {
        "project_path": "main.py",
        "class_name": "AnalystRevisionsV2StockEventStudyScaffold",
        "initialize_refuses_before_service_access": True,
    }
    assert document["truth"] == {
        "source_only": True,
        "adapter_call_contract_present": True,
        "physical_adapter_present": False,
        "real_qc_object_store_access_performed": False,
        "project_created": False,
        "cloud_compile_performed": False,
        "backtest_performed": False,
    }
    assert document["residuals"] == {
        "flat_event_study_upload_name_reconciled": False,
        "qc_nested_project_paths_authenticated": False,
        "qc_python_dependency_set_authenticated": False,
        "qc_project_file_quota_authenticated": False,
        "b4_production_input_capable": False,
    }
    assert document["source_files"] == [
        {
            "role": item.role,
            "repository_path": item.repository_path,
            "project_path": item.project_path,
            "byte_count": item.byte_count,
            "sha256": item.sha256,
        }
        for item in EXPECTED_SOURCE_FILES
    ]
    assert document["object_store_call_contract"] == {
        "event_count": 18,
        "alternating_methods": ["contains_key", "read_bytes"],
        "derived_from_authenticated_b4_plan": True,
        "operations_performed": False,
    }
    assert document["evaluation_windows"] == {
        "formal_primary_fold_ids": [
            "arv2-wf-test-2020",
            "arv2-wf-test-2021",
            "arv2-wf-test-2022",
            "arv2-wf-test-2023",
            "arv2-wf-test-2024",
            "arv2-wf-test-2025",
        ],
        "descriptive_sensitivity_fold_ids": [
            "arv2-wf-test-2021",
            "arv2-wf-test-2022",
            "arv2-wf-test-2023",
            "arv2-wf-test-2024",
            "arv2-wf-test-2025",
        ],
        "sensitivity_can_replace_or_rescue_primary": False,
    }
    assert EXTERNAL_BINDINGS == (
        *B4_EXTERNAL_BINDINGS,
        ("source_assembly_review_commit", None),
        ("source_assembly_counter_review_commit", None),
        ("authenticated_qc_project_file_quota_evidence_id", None),
        ("authenticated_qc_runtime_dependency_receipt_id", None),
        ("physical_adapter_source_sha256", None),
    )
    assert CAPABILITIES is B4_CAPABILITIES
    assert document["external_bindings"] == dict(EXTERNAL_BINDINGS)
    assert document["capabilities"] == dict(CAPABILITIES)


def test_exact_source_inventory_is_authenticated_and_deterministic() -> None:
    _, _, _, first = _assembly()
    _, _, _, second = _assembly()
    assert first.assembly_id == second.assembly_id
    assert first.assembly_hash == second.assembly_hash
    assert first.assembly_artifact_sha256 == second.assembly_artifact_sha256
    assert first._canonical_document == second._canonical_document
    assert first.entry_project_path == ENTRY_PROJECT_PATH == "main.py"
    assert first.entry_class_name == ENTRY_CLASS_NAME
    assert len(first.files) == len(EXPECTED_SOURCE_FILES) == 11
    assert tuple(item.project_path for item in first.files) == tuple(
        item.project_path for item in EXPECTED_SOURCE_FILES
    )
    assert tuple(item.repository_path for item in first.files) == tuple(
        item.repository_path for item in EXPECTED_SOURCE_FILES
    )
    assert tuple(
        (item.role, item.repository_path, item.project_path)
        for item in first.files
    ) == EXPECTED_SOURCE_LOCATIONS
    assert first.total_source_byte_count == 509_109
    assert first.largest_project_file_byte_count == 140_983
    for item in first.files:
        assert len(item.source_bytes) == item.byte_count
        assert hashlib.sha256(item.source_bytes).hexdigest() == item.sha256


def test_assembly_identity_and_lineage_recompute_independently() -> None:
    candidate, _, plan, value = _assembly()
    document = json.loads(value._canonical_document)
    assert document["assembly_id"] == value.assembly_id
    assert document["assembly_hash"] == value.assembly_hash
    seed = dict(document)
    seed["assembly_id"] = None
    seed["assembly_hash"] = None
    canonical_seed = (
        json.dumps(
            seed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    expected_hash = hashlib.sha256(
        b"arv2-qc-lean-source-assembly-v1\x00" + canonical_seed
    ).hexdigest()
    assert value.assembly_hash == expected_hash
    assert value.assembly_id == f"arv2-qc-lean-source-assembly-{expected_hash[:16]}"
    assert (
        hashlib.sha256(value._canonical_document).hexdigest()
        == value.assembly_artifact_sha256
    )
    assert document["lineage"] == {
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "plan_artifact_sha256": plan.plan_artifact_sha256,
        "run_candidate_id": candidate.candidate_id,
        "run_candidate_hash": candidate.candidate_hash,
    }
    assert value.plan_id == plan.plan_id
    assert value.plan_hash == plan.plan_hash
    assert value.plan_artifact_sha256 == plan.plan_artifact_sha256
    assert value.run_candidate_id == candidate.candidate_id
    assert value.run_candidate_hash == candidate.candidate_hash
    assert document == {
        "schema_id": SCHEMA_ID,
        "schema_sha256": SCHEMA_SHA256,
        "schema_artifact_sha256": SCHEMA_ARTIFACT_SHA256,
        "status": STATUS,
        "authority": AUTHORITY,
        "assembly_id": value.assembly_id,
        "assembly_hash": value.assembly_hash,
        "entry_project_path": ENTRY_PROJECT_PATH,
        "entry_class_name": ENTRY_CLASS_NAME,
        "files": [
            {
                "role": item.role,
                "repository_path": item.repository_path,
                "project_path": item.project_path,
                "byte_count": item.byte_count,
                "sha256": item.sha256,
            }
            for item in value.files
        ],
        "object_store_calls": [
            {
                "ordinal": item.ordinal,
                "operation": item.operation,
                "method_name": item.method_name,
                "object_store_key": item.object_store_key,
                "expected_found": item.expected_found,
                "expected_byte_count": item.expected_byte_count,
                "expected_sha256": item.expected_sha256,
            }
            for item in value.object_store_calls
        ],
        "lineage": {
            "plan_id": plan.plan_id,
            "plan_hash": plan.plan_hash,
            "plan_artifact_sha256": plan.plan_artifact_sha256,
            "run_candidate_id": candidate.candidate_id,
            "run_candidate_hash": candidate.candidate_hash,
        },
        "evaluation_windows": {
            "formal_primary_fold_ids": [
                "arv2-wf-test-2020",
                "arv2-wf-test-2021",
                "arv2-wf-test-2022",
                "arv2-wf-test-2023",
                "arv2-wf-test-2024",
                "arv2-wf-test-2025",
            ],
            "descriptive_sensitivity_fold_ids": [
                "arv2-wf-test-2021",
                "arv2-wf-test-2022",
                "arv2-wf-test-2023",
                "arv2-wf-test-2024",
                "arv2-wf-test-2025",
            ],
            "sensitivity_can_replace_or_rescue_primary": False,
        },
        "truth": {
            "source_only": True,
            "adapter_call_contract_present": True,
            "physical_adapter_present": False,
            "real_qc_object_store_access_performed": False,
            "project_created": False,
            "cloud_compile_performed": False,
            "backtest_performed": False,
        },
        "source_census": {
            "file_count": 11,
            "total_byte_count": 509_109,
            "largest_project_file_byte_count": 140_983,
            "actual_project_file_quota_authenticated": False,
        },
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
    }


@pytest.mark.parametrize(
    "value_class",
    (
        ExpectedLeanSource,
        LeanSourceInput,
        LeanObjectStoreCallBinding,
        SyntheticLeanProjectFile,
        SyntheticLeanProjectAssembly,
    ),
)
def test_value_classes_are_frozen_and_slotted(value_class: type) -> None:
    assert dataclasses.is_dataclass(value_class)
    assert value_class.__dataclass_params__.frozen is True
    assert "__dict__" not in vars(value_class)
    assert type(value_class.__slots__) is tuple
    assert tuple(field.name for field in dataclasses.fields(value_class)) == (
        EXPECTED_DATACLASS_FIELDS[value_class]
    )
    assert inspect.get_annotations(value_class, eval_str=True) == (
        EXPECTED_DATACLASS_FIELD_TYPES[value_class]
    )
    assert tuple(
        (field.name, field.repr) for field in dataclasses.fields(value_class)
    ) == tuple(
        (
            name,
            not (
                (value_class is LeanSourceInput and name == "source_bytes")
                or (
                    value_class is SyntheticLeanProjectFile
                    and name == "source_bytes"
                )
                or (
                    value_class is SyntheticLeanProjectAssembly
                    and name in {"_plan", "_run_candidate", "_canonical_document"}
                )
            ),
        )
        for name in EXPECTED_DATACLASS_FIELDS[value_class]
    )
    assert {
        name
        for name, member in vars(value_class).items()
        if inspect.isfunction(member) and not name.startswith("_")
    } == set()
    properties = {
        name
        for name, member in vars(value_class).items()
        if type(member) is property
    }
    assert properties == (
        set(FALSE_PROPERTY_NAMES)
        if value_class is SyntheticLeanProjectAssembly
        else set()
    )


def test_public_exception_base_is_exact() -> None:
    assert QcLeanSourceAssemblyError.__bases__ == (ValueError,)


def test_static_contract_refuses_exception_base_mutation() -> None:
    original_bases = QcLeanSourceAssemblyError.__bases__
    try:
        QcLeanSourceAssemblyError.__bases__ = (Exception,)
        with pytest.raises(
            QcLeanSourceAssemblyError, match="class ancestry"
        ):
            render_qc_lean_source_assembly_schema_bytes()
    finally:
        QcLeanSourceAssemblyError.__bases__ = original_bases
    assert render_qc_lean_source_assembly_schema_bytes()


def test_public_field_and_truth_censuses_are_exact() -> None:
    assert ASSEMBLY_PUBLIC_FIELD_NAMES == EXPECTED_ASSEMBLY_PUBLIC_FIELD_NAMES
    assert ASSEMBLY_TRUTH_FIELD_VALUES == (
        ("source_only", True),
        ("adapter_call_contract_present", True),
        ("physical_adapter_present", False),
        ("real_qc_object_store_access_performed", False),
        ("project_created", False),
        ("cloud_compile_performed", False),
        ("backtest_performed", False),
    )


def test_topology_validator_field_censuses_are_exact() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_require_assembly_topology"
    )
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in function.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }
    assert assignments["string_fields"] == (
        "assembly_id",
        "assembly_hash",
        "assembly_artifact_sha256",
        "entry_project_path",
        "entry_class_name",
        "plan_id",
        "plan_hash",
        "plan_artifact_sha256",
        "run_candidate_id",
        "run_candidate_hash",
    )
    assert assignments["integer_fields"] == (
        "total_source_byte_count",
        "largest_project_file_byte_count",
    )
    assert assignments["boolean_fields"] == tuple(
        name for name, _ in ASSEMBLY_TRUTH_FIELD_VALUES
    )


def test_source_tree_truth_properties_and_authority_stay_closed() -> None:
    _, _, _, value = _assembly()
    assert value.source_only is True
    assert value.adapter_call_contract_present is True
    assert value.physical_adapter_present is False
    assert value.real_qc_object_store_access_performed is False
    assert value.project_created is False
    assert value.cloud_compile_performed is False
    assert value.backtest_performed is False
    assert value.external_bindings == EXTERNAL_BINDINGS
    assert value.capabilities == CAPABILITIES
    assert all(binding is None for _, binding in value.external_bindings)
    assert all(enabled is False for _, enabled in value.capabilities)
    assert all(getattr(value, name) is False for name in FALSE_PROPERTY_NAMES)
    assert require_synthetic_qc_lean_source_assembly(value) is value
    assert "source_bytes" not in repr(value)


def test_call_contract_is_the_exact_alternating_b4_plan_projection() -> None:
    _, _, plan, value = _assembly()
    assert len(value.object_store_calls) == EXPECTED_OBJECT_STORE_CALL_COUNT == 18
    for index, descriptor in enumerate(plan.objects):
        contains, read = value.object_store_calls[index * 2 : index * 2 + 2]
        assert contains == LeanObjectStoreCallBinding(
            ordinal=index * 2 + 1,
            operation="contains_key",
            method_name="contains_key",
            object_store_key=descriptor.object_store_key,
            expected_found=True,
            expected_byte_count=None,
            expected_sha256=None,
        )
        assert read == LeanObjectStoreCallBinding(
            ordinal=index * 2 + 2,
            operation="read_bytes",
            method_name="read_bytes",
            object_store_key=descriptor.object_store_key,
            expected_found=None,
            expected_byte_count=descriptor.byte_count,
            expected_sha256=descriptor.artifact_sha256,
        )


def test_test_only_fake_replays_call_contract_without_production_io() -> None:
    _, fixture, plan, value = _assembly()
    payloads = {
        descriptor.object_store_key: entry.payload
        for descriptor, entry in zip(plan.objects, fixture.entries, strict=True)
    }

    class FakeObjectStore:
        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        def contains_key(self, key: str) -> bool:
            self.calls.append(("contains_key", key))
            return key in payloads

        def read_bytes(self, key: str) -> bytes:
            self.calls.append(("read_bytes", key))
            return payloads[key]

    fake = FakeObjectStore()
    for call in value.object_store_calls:
        method = getattr(fake, call.method_name)
        result = method(call.object_store_key)
        if call.operation == "contains_key":
            assert result is call.expected_found is True
        else:
            assert type(result) is bytes
            assert len(result) == call.expected_byte_count
            assert hashlib.sha256(result).hexdigest() == call.expected_sha256
    assert tuple(fake.calls) == tuple(
        (item.method_name, item.object_store_key)
        for item in value.object_store_calls
    )


def test_every_assembled_source_is_offline_syntax_valid_and_main_refuses() -> None:
    _, _, _, value = _assembly()
    for item in value.files:
        compile(item.source_bytes, item.project_path, "exec")

    class StubQCAlgorithm:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"main.py touched a LEAN service: {name}")

    fake_imports = types.ModuleType("AlgorithmImports")
    fake_imports.QCAlgorithm = StubQCAlgorithm
    previous = sys.modules.get("AlgorithmImports")
    sys.modules["AlgorithmImports"] = fake_imports
    try:
        main = value.files[0]
        namespace: dict[str, object] = {"__name__": "arv2_b5b_main_test"}
        exec(compile(main.source_bytes, "main.py", "exec"), namespace)
        algorithm = namespace[ENTRY_CLASS_NAME]()
        with pytest.raises(
            RuntimeError, match="^ARV2-4F-B5B SOURCE_ASSEMBLY_ONLY"
        ):
            algorithm.initialize()
        assert algorithm.on_end_of_algorithm() is None
    finally:
        if previous is None:
            sys.modules.pop("AlgorithmImports", None)
        else:
            sys.modules["AlgorithmImports"] = previous


def test_main_source_preserves_fold_separation_and_has_no_service_call() -> None:
    _, _, _, value = _assembly()
    main = value.files[0].source_bytes.decode("utf-8")
    tree = ast.parse(main)
    constants: dict[str, object] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            constants[node.targets[0].id] = ast.literal_eval(node.value)
    assert constants["FORMAL_PRIMARY_FOLD_IDS"] == FORMAL_PRIMARY_FOLD_IDS
    assert (
        constants["DESCRIPTIVE_SENSITIVITY_FOLD_IDS"]
        == DESCRIPTIVE_SENSITIVITY_FOLD_IDS
    )
    assert "NO ALPHA STATISTIC" in ast.get_docstring(tree)
    attributes = [node for node in ast.walk(tree) if isinstance(node, ast.Attribute)]
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert attributes == []
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("missing", "inventory"),
        ("extra", "inventory"),
        ("reordered", "path or role"),
        ("role", "path or role"),
        ("repository-path", "path or role"),
        ("project-path", "path or role"),
        ("traversal", "path or role"),
        ("case-collision", "path or role"),
        ("bom", "byte identity"),
        ("cr", "byte identity"),
        ("nul", "byte identity"),
        ("invalid-utf8", "byte identity"),
        ("trailing-byte", "byte identity"),
    ),
)
def test_source_inventory_refuses_single_boundary_mutations(
    mode: str, message: str
) -> None:
    candidate, _, plan = _plan()
    sources = list(_source_inputs())
    if mode == "missing":
        sources.pop()
    elif mode == "extra":
        sources.append(sources[-1])
    elif mode == "reordered":
        sources[1], sources[2] = sources[2], sources[1]
    elif mode == "role":
        sources[0] = dataclasses.replace(sources[0], role="other")
    elif mode == "repository-path":
        sources[0] = dataclasses.replace(sources[0], repository_path="main.py")
    elif mode == "project-path":
        sources[0] = dataclasses.replace(sources[0], project_path="other.py")
    elif mode == "traversal":
        sources[0] = dataclasses.replace(sources[0], project_path="../main.py")
    elif mode == "case-collision":
        sources[0] = dataclasses.replace(
            sources[0], project_path="Research/__init__.py"
        )
    elif mode == "bom":
        sources[0] = dataclasses.replace(
            sources[0], source_bytes=b"\xef\xbb\xbf" + sources[0].source_bytes
        )
    elif mode == "cr":
        sources[0] = dataclasses.replace(
            sources[0], source_bytes=sources[0].source_bytes.replace(b"\n", b"\r\n", 1)
        )
    elif mode == "nul":
        sources[0] = dataclasses.replace(
            sources[0], source_bytes=sources[0].source_bytes + b"\x00"
        )
    elif mode == "invalid-utf8":
        sources[0] = dataclasses.replace(
            sources[0], source_bytes=sources[0].source_bytes + b"\xff"
        )
    else:
        sources[0] = dataclasses.replace(
            sources[0], source_bytes=sources[0].source_bytes + b"\n"
        )
    with pytest.raises(QcLeanSourceAssemblyError, match=message):
        build_synthetic_qc_lean_source_assembly(
            run_candidate=candidate,
            read_plan=plan,
            source_files=tuple(sources),
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (b"\xef\xbb\xbfpass\n", "BOM"),
        (b"pass\r\n", "canonical LF"),
        (b"pass\x00\n", "contains NUL"),
        (b"# \xff\n", "strict UTF-8"),
        (b"if:\n", "strict UTF-8 Python"),
    ),
)
def test_canonical_source_validator_refuses_noncanonical_bytes(
    payload: bytes, message: str
) -> None:
    with pytest.raises(QcLeanSourceAssemblyError, match=message):
        assembly_module._require_canonical_python_source(payload, role="probe")


@pytest.mark.parametrize(
    "mode", ("different-length", "invalid-utf8", "invalid-syntax")
)
def test_wrong_source_identity_is_refused_before_ast_parse(
    mode: str,
) -> None:
    candidate, _, plan = _plan()
    sources = list(_source_inputs())
    payload = sources[0].source_bytes
    if mode == "different-length":
        changed = payload + b"\n"
    elif mode == "invalid-utf8":
        changed = b"\xff" + payload[1:]
    else:
        changed = b"!" + payload[1:]
    sources[0] = dataclasses.replace(sources[0], source_bytes=changed)
    with pytest.raises(QcLeanSourceAssemblyError, match="byte identity"):
        build_synthetic_qc_lean_source_assembly(
            run_candidate=candidate,
            read_plan=plan,
            source_files=tuple(sources),
        )


def test_exact_types_and_cross_candidate_plan_are_refused() -> None:
    candidate, _, plan = _plan()
    other_candidate, _, other_plan = _plan()
    assert other_candidate is not candidate
    assert other_plan is not plan
    with pytest.raises(QcLeanSourceAssemblyError, match="not bound"):
        build_synthetic_qc_lean_source_assembly(
            run_candidate=candidate,
            read_plan=other_plan,
            source_files=_source_inputs(),
        )

    class HostileStr(str):
        calls = 0

        def __eq__(self, other):
            type(self).calls += 1
            raise AssertionError("hostile equality ran")

    sources = list(_source_inputs())
    sources[0] = dataclasses.replace(sources[0], role=HostileStr(sources[0].role))
    with pytest.raises(QcLeanSourceAssemblyError, match="type changed"):
        build_synthetic_qc_lean_source_assembly(
            run_candidate=candidate,
            read_plan=plan,
            source_files=tuple(sources),
        )
    assert HostileStr.calls == 0


@pytest.mark.parametrize(
    "name",
    (
        "require_synthetic_qc_object_store_read_plan",
        "require_synthetic_qc_run_candidate",
        "build_synthetic_qc_run_candidate",
        "render_qc_object_store_read_contract_schema_bytes",
        "QcObjectStoreReadContractError",
        "QcRunContractError",
        "_derive_object_store_calls",
        "build_synthetic_qc_lean_source_assembly",
        "LeanSourceInput",
        "_PINNED_REQUIRE_READ_PLAN",
        "_PINNED_REQUIRE_RUN_CANDIDATE",
        "_PINNED_BUILD_RUN_CANDIDATE",
        "_PINNED_RENDER_B4_SCHEMA",
        "_PINNED_B4_ERROR_CLASS",
        "_PINNED_AST_PARSE",
        "_PINNED_DATACLASSES_FIELDS",
        "_PINNED_SHA256",
        "_PINNED_JSON_DUMPS",
        "_SCHEMA_DOCUMENT_BYTES",
        "_PINNED_SCHEMA_DOCUMENT_BYTES",
        "_PINNED_BUILD_ASSEMBLY",
    ),
)
def test_static_contract_refuses_dependency_function_class_and_pin_rebinding(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(assembly_module, name, lambda *_args, **_kwargs: None)
    with pytest.raises(
        QcLeanSourceAssemblyError,
        match="alias|binding|function|class|snapshot|registry",
    ):
        render_qc_lean_source_assembly_schema_bytes()


@pytest.mark.parametrize(
    ("module_name", "attribute"),
    (
        ("ast", "parse"),
        ("dataclasses", "fields"),
        ("hashlib", "sha256"),
        ("json", "dumps"),
        ("re", "compile"),
    ),
)
def test_static_contract_refuses_dependency_callable_substitution(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    attribute: str,
) -> None:
    dependency = getattr(assembly_module, module_name)
    monkeypatch.setattr(dependency, attribute, lambda *_args, **_kwargs: None)
    with pytest.raises(QcLeanSourceAssemblyError, match="dependency callable"):
        render_qc_lean_source_assembly_schema_bytes()


def test_public_bootstrap_refuses_static_registry_rebinding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(assembly_module, "_PINNED_STATIC_SNAPSHOT_BINDINGS", ())
    with pytest.raises(QcLeanSourceAssemblyError, match="bootstrap registry"):
        render_qc_lean_source_assembly_schema_bytes()


def test_public_bootstrap_refuses_coordinated_source_oracle_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, _, plan = _plan()
    evil = b"pass\n"
    sources = list(_source_inputs())
    sources[0] = dataclasses.replace(sources[0], source_bytes=evil)
    expected = tuple(
        (
            item.role,
            item.repository_path,
            item.project_path,
            len(evil) if index == 0 else item.byte_count,
            hashlib.sha256(evil).hexdigest() if index == 0 else item.sha256,
        )
        for index, item in enumerate(EXPECTED_SOURCE_FILES)
    )
    monkeypatch.setattr(assembly_module, "_PINNED_STATIC_SNAPSHOT_BINDINGS", ())
    monkeypatch.setattr(assembly_module, "_PINNED_ALIAS_BINDINGS", ())
    monkeypatch.setattr(
        assembly_module,
        "_PINNED_REQUIRE_STATIC_CONTRACT",
        lambda: expected,
    )
    with pytest.raises(QcLeanSourceAssemblyError, match="bootstrap registry"):
        build_synthetic_qc_lean_source_assembly(
            run_candidate=candidate,
            read_plan=plan,
            source_files=tuple(sources),
        )


def test_public_bootstrap_refuses_hostile_alias_before_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HostileGlobals:
        calls = 0

        def __call__(self):
            type(self).calls += 1
            raise AssertionError("hostile globals callback ran")

    monkeypatch.setattr(assembly_module, "_PINNED_GLOBALS", HostileGlobals())
    with pytest.raises(QcLeanSourceAssemblyError, match="bootstrap alias"):
        render_qc_lean_source_assembly_schema_bytes()
    assert HostileGlobals.calls == 0


def test_static_contract_authenticates_transitive_b4_and_b3_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(b3_module, "STATUS", "corrupted-parent")
    with pytest.raises(
        QcLeanSourceAssemblyError,
        match="B4 static preflight",
    ) as caught:
        render_qc_lean_source_assembly_schema_bytes()
    assert isinstance(
        caught.value.__cause__, b4_module.QcObjectStoreReadContractError
    )


def test_static_contract_refuses_mutated_parent_renderer_before_call() -> None:
    renderer = b4_module.render_qc_object_store_read_contract_schema_bytes
    original_code = renderer.__code__

    def hostile_renderer():
        raise AssertionError("mutated parent renderer executed")

    try:
        renderer.__code__ = hostile_renderer.__code__
        with pytest.raises(QcLeanSourceAssemblyError, match="parent function"):
            render_qc_lean_source_assembly_schema_bytes()
    finally:
        renderer.__code__ = original_code


@pytest.mark.parametrize(
    "name",
    ("SCHEMA_ID", "SCHEMA_SHA256", "SCHEMA_ARTIFACT_SHA256"),
)
def test_derived_schema_scalars_require_exact_str_before_comparison(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    class HostileStr(str):
        calls = 0

        def __eq__(self, other):
            type(self).calls += 1
            return True

        def __ne__(self, other):
            type(self).calls += 1
            return False

    monkeypatch.setattr(assembly_module, name, HostileStr("forged"))
    with pytest.raises(QcLeanSourceAssemblyError, match="scalar identity"):
        render_qc_lean_source_assembly_schema_bytes()
    assert HostileStr.calls == 0


def test_schema_document_reflected_equality_cannot_emit_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hostile_document = dict(assembly_module._SCHEMA_IDENTITY_DOCUMENT)
    hostile_truth = dict(hostile_document["truth"])
    hostile_truth["physical_adapter_present"] = True
    hostile_truth["backtest_performed"] = True
    hostile_document["truth"] = hostile_truth

    class LyingDict(dict):
        calls = 0

        def __eq__(self, other):
            type(self).calls += 1
            return True

        def __ne__(self, other):
            type(self).calls += 1
            return False

    forged = LyingDict(hostile_document)
    monkeypatch.setattr(assembly_module, "_SCHEMA_IDENTITY_DOCUMENT", forged)
    with pytest.raises(QcLeanSourceAssemblyError, match="registry"):
        render_qc_lean_source_assembly_schema_bytes()
    assert LyingDict.calls == 0


def test_static_contract_refuses_both_parent_validator_aliases_rebound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, _, plan = _plan()
    forged_descriptor = dataclasses.replace(
        plan.objects[0], object_store_key="production/secret"
    )
    forged_plan = dataclasses.replace(
        plan, objects=(forged_descriptor, *plan.objects[1:])
    )
    monkeypatch.setattr(
        assembly_module,
        "_PINNED_REQUIRE_READ_PLAN",
        lambda value: value,
    )
    monkeypatch.setattr(
        assembly_module,
        "_PINNED_REQUIRE_RUN_CANDIDATE",
        lambda value: value,
    )
    with pytest.raises(
        QcLeanSourceAssemblyError,
        match="pinned binding|bootstrap alias",
    ):
        build_synthetic_qc_lean_source_assembly(
            run_candidate=candidate,
            read_plan=forged_plan,
            source_files=_source_inputs(),
        )


def test_static_contract_refuses_false_authority_property_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        SyntheticLeanProjectAssembly,
        "trading_available",
        property(lambda _self: True),
    )
    with pytest.raises(QcLeanSourceAssemblyError, match="class topology"):
        render_qc_lean_source_assembly_schema_bytes()


def test_static_contract_refuses_false_authority_property_code_mutation() -> None:
    authority_property = vars(SyntheticLeanProjectAssembly)["trading_available"]
    implementation = authority_property.fget
    assert implementation is not None
    original_code = implementation.__code__

    def replacement(_self):
        return True

    implementation.__code__ = replacement.__code__
    try:
        with pytest.raises(QcLeanSourceAssemblyError, match="class function"):
            render_qc_lean_source_assembly_schema_bytes()
    finally:
        implementation.__code__ = original_code
    assert render_qc_lean_source_assembly_schema_bytes()


@pytest.mark.parametrize(
    "function_name",
    ("_derive_object_store_calls", "_PINNED_REQUIRE_READ_PLAN"),
)
def test_static_contract_refuses_in_place_function_code_mutation(
    function_name: str,
) -> None:
    function = getattr(assembly_module, function_name)
    original_code = function.__code__

    def replacement(_value):
        return None

    function.__code__ = replacement.__code__
    try:
        with pytest.raises(QcLeanSourceAssemblyError, match="function"):
            render_qc_lean_source_assembly_schema_bytes()
    finally:
        function.__code__ = original_code
    assert render_qc_lean_source_assembly_schema_bytes()


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: dataclasses.replace(value, source_only=False),
        lambda value: dataclasses.replace(value, physical_adapter_present=True),
        lambda value: dataclasses.replace(
            value, real_qc_object_store_access_performed=True
        ),
        lambda value: dataclasses.replace(value, project_created=True),
        lambda value: dataclasses.replace(value, cloud_compile_performed=True),
        lambda value: dataclasses.replace(value, backtest_performed=True),
        lambda value: dataclasses.replace(
            value,
            capabilities=(
                (value.capabilities[0][0], True),
                *value.capabilities[1:],
            ),
        ),
        lambda value: dataclasses.replace(
            value,
            external_bindings=(
                (value.external_bindings[0][0], "forged"),
                *value.external_bindings[1:],
            ),
        ),
        lambda value: dataclasses.replace(
            value, object_store_calls=value.object_store_calls[::-1]
        ),
        lambda value: dataclasses.replace(
            value,
            files=(
                dataclasses.replace(value.files[0], source_bytes=b"pass\n"),
                *value.files[1:],
            ),
        ),
        lambda value: dataclasses.replace(value, plan_hash="0" * 64),
        lambda value: dataclasses.replace(value, _canonical_document=b"{}\n"),
    ),
    ids=(
        "source-only",
        "physical-adapter",
        "real-object-store",
        "project-created",
        "cloud-compile",
        "backtest",
        "capability",
        "external-binding",
        "call-order",
        "source-bytes",
        "plan-hash",
        "canonical-document",
    ),
)
def test_retained_assembly_rejects_single_invariant_mutations(mutate) -> None:
    _, _, _, value = _assembly()
    changed = mutate(value)
    with pytest.raises(QcLeanSourceAssemblyError):
        require_synthetic_qc_lean_source_assembly(changed)


def test_builder_retains_only_caller_supplied_source_bytes() -> None:
    candidate, _, plan = _plan()
    sources = _source_inputs()
    value = build_synthetic_qc_lean_source_assembly(
        run_candidate=candidate,
        read_plan=plan,
        source_files=sources,
    )
    assert tuple(item.source_bytes for item in value.files) == tuple(
        item.source_bytes for item in sources
    )
    assert all(
        retained.source_bytes is supplied.source_bytes
        for retained, supplied in zip(value.files, sources, strict=True)
    )


def test_builder_derives_calls_from_authenticated_primitive_snapshot() -> None:
    candidate, _, plan = _plan()
    original_objects = plan.objects
    forged_objects = (
        dataclasses.replace(
            original_objects[0], object_store_key="production/secret"
        ),
        *original_objects[1:],
    )
    builder_impl = assembly_module._PINNED_BUILD_ASSEMBLY_IMPL
    source = inspect.getsource(builder_impl)
    assert "calls = _PINNED_DERIVE_OBJECT_STORE_CALLS(parent_snapshot)" in source
    assert "seed = _PINNED_ASSEMBLY_SEED_DOCUMENT(" in source
    trace_events: list[str] = []

    def tracer(frame, event, _arg):
        if (
            frame.f_code is builder_impl.__code__
            and event == "line"
        ):
            line = linecache.getline(
                frame.f_code.co_filename, frame.f_lineno
            ).strip()
            if line == "calls = _PINNED_DERIVE_OBJECT_STORE_CALLS(parent_snapshot)":
                object.__setattr__(plan, "objects", forged_objects)
                trace_events.append("forged")
            elif (
                line == "seed = _PINNED_ASSEMBLY_SEED_DOCUMENT("
                and trace_events == ["forged"]
            ):
                object.__setattr__(plan, "objects", original_objects)
                trace_events.append("restored")
        return tracer

    sys.settrace(tracer)
    try:
        value = build_synthetic_qc_lean_source_assembly(
            run_candidate=candidate,
            read_plan=plan,
            source_files=_source_inputs(),
        )
    finally:
        sys.settrace(None)
        object.__setattr__(plan, "objects", original_objects)
    assert trace_events == ["forged", "restored"]
    expected_keys = tuple(
        descriptor.object_store_key
        for descriptor in original_objects
        for _operation in range(2)
    )
    assert tuple(call.object_store_key for call in value.object_store_calls) == (
        expected_keys
    )
    assert "production/secret" not in expected_keys
    assert require_synthetic_qc_lean_source_assembly(value) is value


def test_parent_snapshot_matches_the_authenticated_b4_canonical_artifact() -> None:
    candidate, _, plan = _plan()
    original_objects = plan.objects
    forged_objects = (
        dataclasses.replace(
            original_objects[0], object_store_key="production/secret"
        ),
        *original_objects[1:],
    )
    capture = assembly_module._capture_parent_snapshot
    source = inspect.getsource(capture)
    assert "live_objects = _PINNED_TUPLE(" in source
    assert "rebuilt = _PINNED_BUILD_READ_PLAN(" in source
    trace_events: list[str] = []

    def tracer(frame, event, _arg):
        if frame.f_code is capture.__code__ and event == "line":
            line = linecache.getline(
                frame.f_code.co_filename, frame.f_lineno
            ).strip()
            if line == "live_objects = _PINNED_TUPLE(" and not trace_events:
                object.__setattr__(plan, "objects", forged_objects)
                trace_events.append("forged")
            elif (
                line == "rebuilt = _PINNED_BUILD_READ_PLAN("
                and trace_events == ["forged"]
            ):
                object.__setattr__(plan, "objects", original_objects)
                trace_events.append("restored")
        return tracer

    sys.settrace(tracer)
    try:
        with pytest.raises(QcLeanSourceAssemblyError, match="object projection"):
            build_synthetic_qc_lean_source_assembly(
                run_candidate=candidate,
                read_plan=plan,
                source_files=_source_inputs(),
            )
    finally:
        sys.settrace(None)
        object.__setattr__(plan, "objects", original_objects)
    assert trace_events == ["forged", "restored"]


def test_parent_snapshot_detaches_candidate_identity_before_emission() -> None:
    candidate, _, plan = _plan()
    original_id = candidate.candidate_id
    original_hash = candidate.candidate_hash
    forged_hash = "f" * 64
    forged_id = f"arv2-qc-stock-run-candidate-{forged_hash[:16]}"
    capture = assembly_module._capture_parent_snapshot
    source = inspect.getsource(capture)
    assert "candidate_id = detached_candidate.candidate_id" in source
    assert "rebuilt_objects = _PINNED_TUPLE(" in source
    trace_events: list[str] = []

    def tracer(frame, event, _arg):
        if frame.f_code is capture.__code__ and event == "line":
            line = linecache.getline(
                frame.f_code.co_filename, frame.f_lineno
            ).strip()
            if (
                line == "candidate_id = detached_candidate.candidate_id"
                and not trace_events
            ):
                object.__setattr__(candidate, "candidate_id", forged_id)
                object.__setattr__(candidate, "candidate_hash", forged_hash)
                trace_events.append("forged")
            elif (
                line == "rebuilt_objects = _PINNED_TUPLE("
                and trace_events == ["forged"]
            ):
                object.__setattr__(candidate, "candidate_id", original_id)
                object.__setattr__(candidate, "candidate_hash", original_hash)
                trace_events.append("restored")
        return tracer

    sys.settrace(tracer)
    try:
        value = build_synthetic_qc_lean_source_assembly(
            run_candidate=candidate,
            read_plan=plan,
            source_files=_source_inputs(),
        )
    finally:
        sys.settrace(None)
        object.__setattr__(candidate, "candidate_id", original_id)
        object.__setattr__(candidate, "candidate_hash", original_hash)
    assert trace_events == ["forged", "restored"]
    assert value.run_candidate_id == original_id
    assert value.run_candidate_hash == original_hash
    assert require_synthetic_qc_lean_source_assembly(value) is value


def test_builder_emits_only_opening_authenticated_contract_snapshot() -> None:
    candidate, _, plan = _plan()
    original_schema_id = assembly_module.SCHEMA_ID
    builder_impl = assembly_module._PINNED_BUILD_ASSEMBLY_IMPL
    source = inspect.getsource(builder_impl)
    assert "seed = _PINNED_ASSEMBLY_SEED_DOCUMENT(" in source
    assert "document, assembly_hash = _PINNED_IDENTITY_DOCUMENT(" in source
    trace_events: list[str] = []

    def tracer(frame, event, _arg):
        if (
            frame.f_code is builder_impl.__code__
            and event == "line"
        ):
            line = linecache.getline(
                frame.f_code.co_filename, frame.f_lineno
            ).strip()
            if (
                line == "seed = _PINNED_ASSEMBLY_SEED_DOCUMENT("
                and not trace_events
            ):
                assembly_module.SCHEMA_ID = "forged-schema-id"
                trace_events.append("forged")
            elif (
                line == "document, assembly_hash = _PINNED_IDENTITY_DOCUMENT("
                and trace_events == ["forged"]
            ):
                assembly_module.SCHEMA_ID = original_schema_id
                trace_events.append("restored")
        return tracer

    sys.settrace(tracer)
    try:
        value = build_synthetic_qc_lean_source_assembly(
            run_candidate=candidate,
            read_plan=plan,
            source_files=_source_inputs(),
        )
    finally:
        sys.settrace(None)
        assembly_module.SCHEMA_ID = original_schema_id
    assert trace_events == ["forged", "restored"]
    assert json.loads(value._canonical_document)["schema_id"] == SCHEMA_ID
    assert require_synthetic_qc_lean_source_assembly(value) is value


def test_builder_uses_opening_hash_domain_snapshot_for_identity() -> None:
    candidate, _, plan = _plan()
    baseline = build_synthetic_qc_lean_source_assembly(
        run_candidate=candidate,
        read_plan=plan,
        source_files=_source_inputs(),
    )
    original_hash_domain = assembly_module.HASH_DOMAIN
    builder_impl = assembly_module._PINNED_BUILD_ASSEMBLY_IMPL
    source = inspect.getsource(builder_impl)
    assert "document, assembly_hash = _PINNED_IDENTITY_DOCUMENT(" in source
    assert "canonical = _PINNED_CANONICAL_BYTES(document)" in source
    trace_events: list[str] = []

    def tracer(frame, event, _arg):
        if (
            frame.f_code is builder_impl.__code__
            and event == "line"
        ):
            line = linecache.getline(
                frame.f_code.co_filename, frame.f_lineno
            ).strip()
            if (
                line == "document, assembly_hash = _PINNED_IDENTITY_DOCUMENT("
                and not trace_events
            ):
                assembly_module.HASH_DOMAIN = "forged-identity-domain"
                trace_events.append("forged")
            elif (
                line == "canonical = _PINNED_CANONICAL_BYTES(document)"
                and trace_events == ["forged"]
            ):
                assembly_module.HASH_DOMAIN = original_hash_domain
                trace_events.append("restored")
        return tracer

    sys.settrace(tracer)
    try:
        value = build_synthetic_qc_lean_source_assembly(
            run_candidate=candidate,
            read_plan=plan,
            source_files=_source_inputs(),
        )
    finally:
        sys.settrace(None)
        assembly_module.HASH_DOMAIN = original_hash_domain
    assert trace_events == ["forged", "restored"]
    assert value.assembly_id == baseline.assembly_id
    assert value.assembly_hash == baseline.assembly_hash
    assert value.assembly_artifact_sha256 == baseline.assembly_artifact_sha256
    assert value._canonical_document == baseline._canonical_document
    assert require_synthetic_qc_lean_source_assembly(value) is value


def test_builder_does_not_retain_public_expected_source_descriptors() -> None:
    candidate, _, plan = _plan()
    public_descriptor = EXPECTED_SOURCE_FILES[0]
    original_count = public_descriptor.byte_count
    original_sha256 = public_descriptor.sha256
    evil = b"pass\n"
    sources = list(_source_inputs())
    sources[0] = dataclasses.replace(sources[0], source_bytes=evil)
    builder_impl = assembly_module._PINNED_BUILD_ASSEMBLY_IMPL
    source = inspect.getsource(builder_impl)
    assert "source_values: list[tuple[str, str, str, bytes, int, str]] = []" in source
    trace_events: list[str] = []

    def tracer(frame, event, _arg):
        if (
            frame.f_code is builder_impl.__code__
            and event == "line"
        ):
            line = linecache.getline(
                frame.f_code.co_filename, frame.f_lineno
            ).strip()
            if line == (
                "source_values: list[tuple[str, str, str, bytes, int, str]] = []"
            ):
                object.__setattr__(public_descriptor, "byte_count", len(evil))
                object.__setattr__(
                    public_descriptor,
                    "sha256",
                    hashlib.sha256(evil).hexdigest(),
                )
                trace_events.append("forged")
        return tracer

    sys.settrace(tracer)
    try:
        with pytest.raises(QcLeanSourceAssemblyError, match="source byte identity"):
            build_synthetic_qc_lean_source_assembly(
                run_candidate=candidate,
                read_plan=plan,
                source_files=tuple(sources),
            )
    finally:
        sys.settrace(None)
        object.__setattr__(public_descriptor, "byte_count", original_count)
        object.__setattr__(public_descriptor, "sha256", original_sha256)
    assert trace_events == ["forged"]


def test_source_oracle_is_hardcoded_under_public_registry_race() -> None:
    candidate, _, plan = _plan()
    descriptor = EXPECTED_SOURCE_FILES[0]
    original_public_sha256 = assembly_module.SCAFFOLD_SOURCE_SHA256
    original_descriptor_sha256 = descriptor.sha256
    evil = b"pass\n" + (b"#" * (3_328 - 6)) + b"\n"
    assert len(evil) == 3_328
    evil_sha256 = hashlib.sha256(evil).hexdigest()
    sources = list(_source_inputs())
    sources[0] = dataclasses.replace(sources[0], source_bytes=evil)
    validator = assembly_module._require_expected_sources
    source = inspect.getsource(validator)
    anchor = "expected = _PINNED_EXPECTED_SOURCE_SNAPSHOT_FACTORY()"
    assert anchor in source
    trace_events: list[str] = []

    def tracer(frame, event, _arg):
        if frame.f_code is validator.__code__ and event == "line":
            line = linecache.getline(
                frame.f_code.co_filename, frame.f_lineno
            ).strip()
            if line == anchor and not trace_events:
                assembly_module.SCAFFOLD_SOURCE_SHA256 = evil_sha256
                object.__setattr__(descriptor, "sha256", evil_sha256)
                trace_events.append("forged")
        return tracer

    sys.settrace(tracer)
    try:
        with pytest.raises(
            QcLeanSourceAssemblyError, match="expected source descriptor"
        ):
            build_synthetic_qc_lean_source_assembly(
                run_candidate=candidate,
                read_plan=plan,
                source_files=tuple(sources),
            )
    finally:
        sys.settrace(None)
        assembly_module.SCAFFOLD_SOURCE_SHA256 = original_public_sha256
        object.__setattr__(descriptor, "sha256", original_descriptor_sha256)
    assert trace_events == ["forged"]


def test_no_io_guard_catches_subscripted_builtin_open_mutant() -> None:
    source = MODULE.read_text(encoding="utf-8")
    assert _builtin_io_escape_violations(source) == ()
    mutant = source.replace(
        "                payload,\n",
        '                __builtins__["open"]('
        'supplied.repository_path, "rb").read(),\n',
        1,
    )
    assert mutant != source
    assert _builtin_io_escape_violations(mutant)


@pytest.mark.parametrize(
    "replacement",
    (
        '(b"".join(_PINNED_BUILTINS_DICT["open"]('
        'supplied.repository_path, "rb")), required_byte_count)[1],',
        '(b"".join(__builtins__.get("open")('
        'supplied.repository_path, "rb")), required_byte_count)[1],',
        '(b"".join(_MODULE_GLOBALS["__builtins__"].get("open")('
        'supplied.repository_path, "rb")), required_byte_count)[1],',
        '(b"".join(_PINNED_GETATTR(_PINNED_BUILTINS_DICT, "open")('
        'supplied.repository_path, "rb")), required_byte_count)[1],',
        '(__loader__.get_data(supplied.repository_path), '
        'required_byte_count)[1],',
    ),
)
def test_no_io_guard_catches_dynamic_capability_retrieval_mutants(
    replacement: str,
) -> None:
    source = MODULE.read_text(encoding="utf-8")
    mutant = source.replace(
        "                required_byte_count,\n",
        f"                {replacement}\n",
        1,
    )
    assert mutant != source
    assert _builtin_io_escape_violations(mutant)
    assert _call_surface_fingerprint(mutant) != EXPECTED_CALL_SURFACE


def test_production_module_has_only_pure_value_assembly_surface() -> None:
    source = MODULE.read_text(encoding="utf-8")
    assert _no_io_violations(source) == ()
    assert _builtin_io_escape_violations(source) == ()
    assert _call_surface_fingerprint(source) == EXPECTED_CALL_SURFACE
    assert _module_ast_fingerprint(source) == EXPECTED_MODULE_AST_SHA256
    tree = ast.parse(source)
    imports = {
        alias.name.split(".", 1)[0]
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imports == {"ast", "dataclasses", "hashlib", "json", "re"}
    public_functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    assert set(public_functions) == {
        "render_qc_lean_source_assembly_schema_bytes",
        "build_synthetic_qc_lean_source_assembly",
        "require_synthetic_qc_lean_source_assembly",
    }
    expected_parameters = {
        "render_qc_lean_source_assembly_schema_bytes": (),
        "build_synthetic_qc_lean_source_assembly": (
            "run_candidate",
            "read_plan",
            "source_files",
        ),
        "require_synthetic_qc_lean_source_assembly": ("value",),
    }
    for name, parameters in expected_parameters.items():
        function = getattr(assembly_module, name)
        signature = inspect.signature(function)
        assert tuple(signature.parameters) == parameters
        assert tuple(
            (parameter.kind, parameter.default)
            for parameter in signature.parameters.values()
        ) == tuple(
            (
                (
                    inspect.Parameter.KEYWORD_ONLY
                    if name == "build_synthetic_qc_lean_source_assembly"
                    else inspect.Parameter.POSITIONAL_OR_KEYWORD
                ),
                inspect.Parameter.empty,
            )
            for _parameter in parameters
        )
        assert set(parameters).isdisjoint(
            {
                "path",
                "client",
                "callback",
                "credentials",
                "account",
                "project",
                "object_store",
                "algorithm",
            }
        )


def test_flat_core_upload_binding_is_not_relabelled_as_the_project_path() -> None:
    _, _, _, value = _assembly()
    core = next(item for item in value.files if item.role == "event_study_core")
    assert core.project_path == "research/analyst_revisions_v2_qc/event_study.py"
    assert core.project_path != "event_study.py"
    schema = json.loads(render_qc_lean_source_assembly_schema_bytes())
    assert schema["residuals"]["flat_event_study_upload_name_reconciled"] is False
