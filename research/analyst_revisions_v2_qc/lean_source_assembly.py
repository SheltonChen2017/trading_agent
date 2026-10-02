"""Pure ARV2-4F-B5B LEAN source-tree and adapter-call contract.

This module authenticates caller-supplied source bytes and derives the exact
``contains_key``/``read_bytes`` sequence a later physical adapter must honor.
It accepts no path opener, client, callback, credential, account, project,
Object Store, or QuantConnect object and performs no I/O, compilation, source
execution, upload, backtest, or result access.

The assembled ``main.py`` remains the B5B scaffold whose ``initialize``
raises before touching a LEAN service.  The call bindings are data, not calls.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import re

from .object_store_read_contract import (
    CAPABILITIES as B4_CAPABILITIES,
    EXTERNAL_BINDINGS as B4_EXTERNAL_BINDINGS,
    EXPECTED_EVENT_COUNT as B4_EXPECTED_EVENT_COUNT,
    SCHEMA_ARTIFACT_SHA256 as B4_SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID as B4_SCHEMA_ID,
    SCHEMA_SHA256 as B4_SCHEMA_SHA256,
    QcObjectStoreReadContractError,
    SyntheticQcObjectStoreReadPlan,
    build_synthetic_qc_object_store_read_plan,
    render_qc_object_store_read_contract_schema_bytes,
    require_synthetic_qc_object_store_read_plan,
)
from .run_contract import (
    QcRunContractError,
    SyntheticQcRunCandidate,
    build_synthetic_qc_run_candidate,
    require_synthetic_qc_run_candidate,
)
from .synthetic_input_transport import FALSE_PROPERTY_NAMES


_PINNED_AST_MODULE = ast
_PINNED_AST_PARSE = ast.parse
_PINNED_DATACLASSES_MODULE = dataclasses
_PINNED_DATACLASSES_FIELDS = dataclasses.fields
_PINNED_HASHLIB_MODULE = hashlib
_PINNED_SHA256 = hashlib.sha256
_PINNED_JSON_MODULE = json
_PINNED_JSON_DUMPS = json.dumps
_PINNED_RE_MODULE = re
_PINNED_RE_COMPILE = re.compile
_PINNED_MODULE_BINDINGS = (
    ("ast", _PINNED_AST_MODULE),
    ("dataclasses", _PINNED_DATACLASSES_MODULE),
    ("hashlib", _PINNED_HASHLIB_MODULE),
    ("json", _PINNED_JSON_MODULE),
    ("re", _PINNED_RE_MODULE),
)
_PINNED_DEPENDENCY_CALLABLES = (
    (_PINNED_AST_MODULE, "parse", _PINNED_AST_PARSE),
    (_PINNED_DATACLASSES_MODULE, "fields", _PINNED_DATACLASSES_FIELDS),
    (_PINNED_HASHLIB_MODULE, "sha256", _PINNED_SHA256),
    (_PINNED_JSON_MODULE, "dumps", _PINNED_JSON_DUMPS),
    (_PINNED_RE_MODULE, "compile", _PINNED_RE_COMPILE),
)

_PINNED_ALL = all
_PINNED_ANY = any
_PINNED_ATTRIBUTE_ERROR = AttributeError
_PINNED_BOOL = bool
_PINNED_BYTES = bytes
_PINNED_DICT = dict
_PINNED_GETATTR = getattr
_PINNED_GLOBALS = globals
_PINNED_HASH = hash
_PINNED_ID = id
_PINNED_INT = int
_PINNED_LEN = len
_PINNED_LIST = list
_PINNED_MAX = max
_PINNED_NOT_IMPLEMENTED = NotImplemented
_PINNED_OBJECT = object
_PINNED_PROPERTY = property
_PINNED_RANGE = range
_PINNED_RECURSION_ERROR = RecursionError
_PINNED_SET = set
_PINNED_STR = str
_PINNED_SUM = sum
_PINNED_SUPER = super
_PINNED_SYNTAX_ERROR = SyntaxError
_PINNED_TUPLE = tuple
_PINNED_TYPE = type
_PINNED_TYPE_ERROR = TypeError
_PINNED_UNICODE_DECODE_ERROR = UnicodeDecodeError
_PINNED_UNICODE_ERROR = UnicodeError
_PINNED_VALUE_ERROR = ValueError
_PINNED_VARS = vars
_PINNED_ZIP = zip
_PINNED_FUNCTION_TYPE = type(lambda: None)
_PINNED_CODE_TYPE = type((lambda: None).__code__)
_PINNED_BUILTINS_DICT = __builtins__
_PINNED_BUILTIN_BINDINGS = (
    ("all", _PINNED_ALL),
    ("any", _PINNED_ANY),
    ("AttributeError", _PINNED_ATTRIBUTE_ERROR),
    ("bool", _PINNED_BOOL),
    ("bytes", _PINNED_BYTES),
    ("dict", _PINNED_DICT),
    ("getattr", _PINNED_GETATTR),
    ("globals", _PINNED_GLOBALS),
    ("hash", _PINNED_HASH),
    ("id", _PINNED_ID),
    ("int", _PINNED_INT),
    ("len", _PINNED_LEN),
    ("list", _PINNED_LIST),
    ("max", _PINNED_MAX),
    ("NotImplemented", _PINNED_NOT_IMPLEMENTED),
    ("object", _PINNED_OBJECT),
    ("property", _PINNED_PROPERTY),
    ("range", _PINNED_RANGE),
    ("RecursionError", _PINNED_RECURSION_ERROR),
    ("set", _PINNED_SET),
    ("str", _PINNED_STR),
    ("sum", _PINNED_SUM),
    ("super", _PINNED_SUPER),
    ("SyntaxError", _PINNED_SYNTAX_ERROR),
    ("tuple", _PINNED_TUPLE),
    ("type", _PINNED_TYPE),
    ("TypeError", _PINNED_TYPE_ERROR),
    ("UnicodeDecodeError", _PINNED_UNICODE_DECODE_ERROR),
    ("UnicodeError", _PINNED_UNICODE_ERROR),
    ("ValueError", _PINNED_VALUE_ERROR),
    ("vars", _PINNED_VARS),
    ("zip", _PINNED_ZIP),
)

_PINNED_REQUIRE_READ_PLAN = require_synthetic_qc_object_store_read_plan
_PINNED_REQUIRE_RUN_CANDIDATE = require_synthetic_qc_run_candidate
_PINNED_BUILD_RUN_CANDIDATE = build_synthetic_qc_run_candidate
_PINNED_RENDER_B4_SCHEMA = render_qc_object_store_read_contract_schema_bytes
_PINNED_B4_ERROR_CLASS = QcObjectStoreReadContractError
_PINNED_RUN_CANDIDATE_ERROR_CLASS = QcRunContractError
_PINNED_BUILD_READ_PLAN = build_synthetic_qc_object_store_read_plan
_PINNED_READ_PLAN_CLASS = SyntheticQcObjectStoreReadPlan
_PINNED_RUN_CANDIDATE_CLASS = SyntheticQcRunCandidate
_MODULE_GLOBALS = _PINNED_GLOBALS()
_PINNED_IMPORTED_BINDINGS = (
    ("B4_CAPABILITIES", B4_CAPABILITIES),
    ("B4_EXTERNAL_BINDINGS", B4_EXTERNAL_BINDINGS),
    ("B4_EXPECTED_EVENT_COUNT", B4_EXPECTED_EVENT_COUNT),
    ("B4_SCHEMA_ARTIFACT_SHA256", B4_SCHEMA_ARTIFACT_SHA256),
    ("B4_SCHEMA_ID", B4_SCHEMA_ID),
    ("B4_SCHEMA_SHA256", B4_SCHEMA_SHA256),
    ("FALSE_PROPERTY_NAMES", FALSE_PROPERTY_NAMES),
    (
        "require_synthetic_qc_object_store_read_plan",
        _PINNED_REQUIRE_READ_PLAN,
    ),
    (
        "render_qc_object_store_read_contract_schema_bytes",
        _PINNED_RENDER_B4_SCHEMA,
    ),
    ("build_synthetic_qc_object_store_read_plan", _PINNED_BUILD_READ_PLAN),
    ("build_synthetic_qc_run_candidate", _PINNED_BUILD_RUN_CANDIDATE),
    ("require_synthetic_qc_run_candidate", _PINNED_REQUIRE_RUN_CANDIDATE),
    ("QcObjectStoreReadContractError", _PINNED_B4_ERROR_CLASS),
    ("QcRunContractError", _PINNED_RUN_CANDIDATE_ERROR_CLASS),
    ("SyntheticQcObjectStoreReadPlan", _PINNED_READ_PLAN_CLASS),
    ("SyntheticQcRunCandidate", _PINNED_RUN_CANDIDATE_CLASS),
)


class QcLeanSourceAssemblyError(ValueError):
    """A B5B source input, call contract, or assembly is not authentic."""


_PINNED_ERROR_CLASS = QcLeanSourceAssemblyError


SCHEMA = "arv2-qc-lean-source-assembly-schema-v1"
STATUS = "offline_source_inventory_authenticated_runtime_refuses"
AUTHORITY = (
    "offline_values_only_no_client_callback_filesystem_environment_provider_"
    "credential_account_project_object_store_upload_compile_launch_result_"
    "deployment_order_or_trading_authority"
)
HASH_DOMAIN = "arv2-qc-lean-source-assembly-v1"
ENTRY_PROJECT_PATH = "main.py"
ENTRY_CLASS_NAME = "AnalystRevisionsV2StockEventStudyScaffold"
SCAFFOLD_SCHEMA = "arv2-qc-lean-entry-scaffold-v2"
SCAFFOLD_SOURCE_SHA256 = (
    "327f126311c12e9f37297f229a3946a6cb1f2bbe26ed6c746cf140b26c2e6bf9"
)
SCAFFOLD_SOURCE_BYTE_COUNT = 3_328
B4_SOURCE_SHA256 = (
    "bf370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3"
)
B4_SOURCE_BYTE_COUNT = 57_361
EXPECTED_SOURCE_FILE_COUNT = 11
EXPECTED_OBJECT_STORE_CALL_COUNT = 18

FORMAL_PRIMARY_FOLD_IDS = (
    "arv2-wf-test-2020",
    "arv2-wf-test-2021",
    "arv2-wf-test-2022",
    "arv2-wf-test-2023",
    "arv2-wf-test-2024",
    "arv2-wf-test-2025",
)
DESCRIPTIVE_SENSITIVITY_FOLD_IDS = (
    "arv2-wf-test-2021",
    "arv2-wf-test-2022",
    "arv2-wf-test-2023",
    "arv2-wf-test-2024",
    "arv2-wf-test-2025",
)
ASSEMBLY_PUBLIC_FIELD_NAMES = (
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
ASSEMBLY_TRUTH_FIELD_VALUES = (
    ("source_only", True),
    ("adapter_call_contract_present", True),
    ("physical_adapter_present", False),
    ("real_qc_object_store_access_performed", False),
    ("project_created", False),
    ("cloud_compile_performed", False),
    ("backtest_performed", False),
)

_HEX_64 = _PINNED_RE_COMPILE(r"[0-9a-f]{64}\Z")
_SAFE_PROJECT_PATH = _PINNED_RE_COMPILE(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_PINNED_HEX_64 = _HEX_64
_PINNED_SAFE_PROJECT_PATH = _SAFE_PROJECT_PATH


@dataclasses.dataclass(frozen=True, slots=True)
class ExpectedLeanSource:
    role: str
    repository_path: str
    project_path: str
    byte_count: int
    sha256: str


def _expected_source_files() -> tuple[ExpectedLeanSource, ...]:
    return (
        ExpectedLeanSource(
            role="lean_entry",
            repository_path="research/lean/analyst_revisions_v2_scaffold.py",
            project_path="main.py",
            byte_count=3_328,
            sha256=SCAFFOLD_SOURCE_SHA256,
        ),
        ExpectedLeanSource(
            role="research_package_marker",
            repository_path="research/__init__.py",
            project_path="research/__init__.py",
            byte_count=0,
            sha256=(
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            ),
        ),
        ExpectedLeanSource(
            role="qc_package_marker",
            repository_path="research/analyst_revisions_v2_qc/__init__.py",
            project_path="research/analyst_revisions_v2_qc/__init__.py",
            byte_count=487,
            sha256=(
                "ce8f07aeab0358f5eb3241190169d4f967a5423dc88719f0783a83d010d43dcc"
            ),
        ),
        ExpectedLeanSource(
            role="event_study_core",
            repository_path="research/analyst_revisions_v2_qc/event_study.py",
            project_path="research/analyst_revisions_v2_qc/event_study.py",
            byte_count=109_226,
            sha256=(
                "0f1e6f69c4bde56bb42a49d24d42b0a27cb2417d3c7bf8f1ea196e15fa0628fe"
            ),
        ),
        ExpectedLeanSource(
            role="global_input_bundle",
            repository_path=(
                "research/analyst_revisions_v2_qc/global_input_bundle.py"
            ),
            project_path="research/analyst_revisions_v2_qc/global_input_bundle.py",
            byte_count=140_983,
            sha256=(
                "cdf24e6bdf3bf63e4635d7524e213f9db25abe308c3973999c1215fb5a4cec18"
            ),
        ),
        ExpectedLeanSource(
            role="global_input_schema",
            repository_path=(
                "research/analyst_revisions_v2_qc/global_input_schema.py"
            ),
            project_path="research/analyst_revisions_v2_qc/global_input_schema.py",
            byte_count=94_959,
            sha256=(
                "f0da3f016cdd794514146a7811d3606b3c8be9d94ffca80e1c28790af519016a"
            ),
        ),
        ExpectedLeanSource(
            role="object_store_read_contract",
            repository_path=(
                "research/analyst_revisions_v2_qc/object_store_read_contract.py"
            ),
            project_path=(
                "research/analyst_revisions_v2_qc/object_store_read_contract.py"
            ),
            byte_count=57_361,
            sha256=(
                "bf370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3"
            ),
        ),
        ExpectedLeanSource(
            role="run_contract",
            repository_path="research/analyst_revisions_v2_qc/run_contract.py",
            project_path="research/analyst_revisions_v2_qc/run_contract.py",
            byte_count=28_825,
            sha256=(
                "a72aa500a5c2d2fe68cfe9a00e6531a8c1a241e212cb8df8e2a7a56dba3d77d5"
            ),
        ),
        ExpectedLeanSource(
            role="synthetic_input_transport",
            repository_path=(
                "research/analyst_revisions_v2_qc/synthetic_input_transport.py"
            ),
            project_path=(
                "research/analyst_revisions_v2_qc/synthetic_input_transport.py"
            ),
            byte_count=65_144,
            sha256=(
                "c473bf91a99fd5207ab10407ea85971db9e24e75f7d29ccf64b38c628538ebe9"
            ),
        ),
        ExpectedLeanSource(
            role="data_package_marker",
            repository_path="data/__init__.py",
            project_path="data/__init__.py",
            byte_count=0,
            sha256=(
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            ),
        ),
        ExpectedLeanSource(
            role="exchange_calendar",
            repository_path="data/exchange_calendar.py",
            project_path="data/exchange_calendar.py",
            byte_count=8_796,
            sha256=(
                "174a032efce4082b8661eabe84b0cf6094048e937722bdf1659c8cb6c7decb89"
            ),
        ),
    )


EXPECTED_SOURCE_FILES = _expected_source_files()
EXTERNAL_BINDINGS = (
    *B4_EXTERNAL_BINDINGS,
    ("source_assembly_review_commit", None),
    ("source_assembly_counter_review_commit", None),
    ("authenticated_qc_project_file_quota_evidence_id", None),
    ("authenticated_qc_runtime_dependency_receipt_id", None),
    ("physical_adapter_source_sha256", None),
)
CAPABILITIES = B4_CAPABILITIES
_PINNED_EXPECTED_SOURCE_FILES = EXPECTED_SOURCE_FILES
_PINNED_EXTERNAL_BINDINGS = EXTERNAL_BINDINGS
_PINNED_CAPABILITIES = CAPABILITIES
_PINNED_FORMAL_PRIMARY_FOLD_IDS = FORMAL_PRIMARY_FOLD_IDS
_PINNED_DESCRIPTIVE_SENSITIVITY_FOLD_IDS = DESCRIPTIVE_SENSITIVITY_FOLD_IDS
_PINNED_ASSEMBLY_PUBLIC_FIELD_NAMES = ASSEMBLY_PUBLIC_FIELD_NAMES
_PINNED_ASSEMBLY_TRUTH_FIELD_VALUES = ASSEMBLY_TRUTH_FIELD_VALUES
_PINNED_FALSE_PROPERTY_NAMES = FALSE_PROPERTY_NAMES


@dataclasses.dataclass(frozen=True, slots=True)
class LeanSourceInput:
    """One caller-supplied canonical-LF source file; never opened here."""

    role: str
    repository_path: str
    project_path: str
    source_bytes: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class LeanObjectStoreCallBinding:
    """One future call expectation derived from an authenticated B4 plan."""

    ordinal: int
    operation: str
    method_name: str
    object_store_key: str
    expected_found: bool | None
    expected_byte_count: int | None
    expected_sha256: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticLeanProjectFile:
    role: str
    repository_path: str
    project_path: str
    source_bytes: bytes = dataclasses.field(repr=False)
    byte_count: int
    sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticLeanProjectAssembly:
    assembly_id: str
    assembly_hash: str
    assembly_artifact_sha256: str
    entry_project_path: str
    entry_class_name: str
    files: tuple[SyntheticLeanProjectFile, ...]
    object_store_calls: tuple[LeanObjectStoreCallBinding, ...]
    plan_id: str
    plan_hash: str
    plan_artifact_sha256: str
    run_candidate_id: str
    run_candidate_hash: str
    total_source_byte_count: int
    largest_project_file_byte_count: int
    source_only: bool
    adapter_call_contract_present: bool
    physical_adapter_present: bool
    real_qc_object_store_access_performed: bool
    project_created: bool
    cloud_compile_performed: bool
    backtest_performed: bool
    external_bindings: tuple[tuple[str, None], ...]
    capabilities: tuple[tuple[str, bool], ...]
    _plan: SyntheticQcObjectStoreReadPlan = dataclasses.field(repr=False)
    _run_candidate: SyntheticQcRunCandidate = dataclasses.field(repr=False)
    _canonical_document: bytes = dataclasses.field(repr=False)

    @property
    def filesystem_read_available(self) -> bool:
        return False

    @property
    def environment_read_available(self) -> bool:
        return False

    @property
    def provider_access_available(self) -> bool:
        return False

    @property
    def licensed_input_read_available(self) -> bool:
        return False

    @property
    def production_manifest_available(self) -> bool:
        return False

    @property
    def production_input_read_available(self) -> bool:
        return False

    @property
    def real_outcome_access_available(self) -> bool:
        return False

    @property
    def runtime_code_authenticated(self) -> bool:
        return False

    @property
    def qc_object_store_read_available(self) -> bool:
        return False

    @property
    def qc_object_store_write_available(self) -> bool:
        return False

    @property
    def qc_project_create_available(self) -> bool:
        return False

    @property
    def upload_available(self) -> bool:
        return False

    @property
    def compile_available(self) -> bool:
        return False

    @property
    def launch_available(self) -> bool:
        return False

    @property
    def result_access_available(self) -> bool:
        return False

    @property
    def result_disposition_available(self) -> bool:
        return False

    @property
    def deployment_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False

    @property
    def trading_available(self) -> bool:
        return False


def _expected_source_snapshot(
) -> tuple[tuple[str, str, str, int, str], ...]:
    """Return the hardcoded immutable source oracle used by the builder."""

    return (
        (
            "lean_entry",
            "research/lean/analyst_revisions_v2_scaffold.py",
            "main.py",
            3_328,
            "327f126311c12e9f37297f229a3946a6cb1f2bbe26ed6c746cf140b26c2e6bf9",
        ),
        (
            "research_package_marker",
            "research/__init__.py",
            "research/__init__.py",
            0,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        (
            "qc_package_marker",
            "research/analyst_revisions_v2_qc/__init__.py",
            "research/analyst_revisions_v2_qc/__init__.py",
            487,
            "ce8f07aeab0358f5eb3241190169d4f967a5423dc88719f0783a83d010d43dcc",
        ),
        (
            "event_study_core",
            "research/analyst_revisions_v2_qc/event_study.py",
            "research/analyst_revisions_v2_qc/event_study.py",
            109_226,
            "0f1e6f69c4bde56bb42a49d24d42b0a27cb2417d3c7bf8f1ea196e15fa0628fe",
        ),
        (
            "global_input_bundle",
            "research/analyst_revisions_v2_qc/global_input_bundle.py",
            "research/analyst_revisions_v2_qc/global_input_bundle.py",
            140_983,
            "cdf24e6bdf3bf63e4635d7524e213f9db25abe308c3973999c1215fb5a4cec18",
        ),
        (
            "global_input_schema",
            "research/analyst_revisions_v2_qc/global_input_schema.py",
            "research/analyst_revisions_v2_qc/global_input_schema.py",
            94_959,
            "f0da3f016cdd794514146a7811d3606b3c8be9d94ffca80e1c28790af519016a",
        ),
        (
            "object_store_read_contract",
            "research/analyst_revisions_v2_qc/object_store_read_contract.py",
            "research/analyst_revisions_v2_qc/object_store_read_contract.py",
            57_361,
            "bf370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3",
        ),
        (
            "run_contract",
            "research/analyst_revisions_v2_qc/run_contract.py",
            "research/analyst_revisions_v2_qc/run_contract.py",
            28_825,
            "a72aa500a5c2d2fe68cfe9a00e6531a8c1a241e212cb8df8e2a7a56dba3d77d5",
        ),
        (
            "synthetic_input_transport",
            "research/analyst_revisions_v2_qc/synthetic_input_transport.py",
            "research/analyst_revisions_v2_qc/synthetic_input_transport.py",
            65_144,
            "c473bf91a99fd5207ab10407ea85971db9e24e75f7d29ccf64b38c628538ebe9",
        ),
        (
            "data_package_marker",
            "data/__init__.py",
            "data/__init__.py",
            0,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        (
            "exchange_calendar",
            "data/exchange_calendar.py",
            "data/exchange_calendar.py",
            8_796,
            "174a032efce4082b8661eabe84b0cf6094048e937722bdf1659c8cb6c7decb89",
        ),
    )


def _canonical_bytes(value: object) -> bytes:
    try:
        return (
            _PINNED_JSON_DUMPS(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise _PINNED_ERROR_CLASS(
            "source assembly is not canonical JSON"
        ) from exc


def _source_descriptor_document(value: ExpectedLeanSource) -> dict[str, object]:
    return {
        "role": value.role,
        "repository_path": value.repository_path,
        "project_path": value.project_path,
        "byte_count": value.byte_count,
        "sha256": value.sha256,
    }


def _schema_seed_document() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "schema_id": None,
        "schema_sha256": None,
        "parents": {
            "b4_schema_id": B4_SCHEMA_ID,
            "b4_schema_sha256": B4_SCHEMA_SHA256,
            "b4_schema_artifact_sha256": B4_SCHEMA_ARTIFACT_SHA256,
            "b4_source_sha256": B4_SOURCE_SHA256,
            "b4_source_byte_count": B4_SOURCE_BYTE_COUNT,
            "scaffold_schema": SCAFFOLD_SCHEMA,
            "scaffold_source_sha256": SCAFFOLD_SOURCE_SHA256,
            "scaffold_source_byte_count": SCAFFOLD_SOURCE_BYTE_COUNT,
        },
        "entry": {
            "project_path": ENTRY_PROJECT_PATH,
            "class_name": ENTRY_CLASS_NAME,
            "initialize_refuses_before_service_access": True,
        },
        "source_files": [
            _source_descriptor_document(item) for item in EXPECTED_SOURCE_FILES
        ],
        "object_store_call_contract": {
            "event_count": EXPECTED_OBJECT_STORE_CALL_COUNT,
            "alternating_methods": ["contains_key", "read_bytes"],
            "derived_from_authenticated_b4_plan": True,
            "operations_performed": False,
        },
        "evaluation_windows": {
            "formal_primary_fold_ids": list(FORMAL_PRIMARY_FOLD_IDS),
            "descriptive_sensitivity_fold_ids": list(
                DESCRIPTIVE_SENSITIVITY_FOLD_IDS
            ),
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
        "residuals": {
            "flat_event_study_upload_name_reconciled": False,
            "qc_nested_project_paths_authenticated": False,
            "qc_python_dependency_set_authenticated": False,
            "qc_project_file_quota_authenticated": False,
            "b4_production_input_capable": False,
        },
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
    }


def _identity_document(
    document: dict[str, object],
    *,
    id_key: str,
    hash_key: str,
    prefix: str,
    hash_domain: str = HASH_DOMAIN,
) -> tuple[dict[str, object], str]:
    seed = dict(document)
    seed[id_key] = None
    seed[hash_key] = None
    digest = _PINNED_SHA256(
        hash_domain.encode("ascii") + b"\x00" + _canonical_bytes(seed)
    ).hexdigest()
    final = dict(seed)
    final[hash_key] = digest
    final[id_key] = f"{prefix}-{digest[:16]}"
    return final, digest


_SCHEMA_IDENTITY_DOCUMENT, SCHEMA_SHA256 = _identity_document(
    _schema_seed_document(),
    id_key="schema_id",
    hash_key="schema_sha256",
    prefix="arv2-qc-lean-source-assembly",
)
SCHEMA_ID = str(_SCHEMA_IDENTITY_DOCUMENT["schema_id"])
_SCHEMA_DOCUMENT_BYTES = _canonical_bytes(_SCHEMA_IDENTITY_DOCUMENT)
SCHEMA_ARTIFACT_SHA256 = _PINNED_SHA256(
    _SCHEMA_DOCUMENT_BYTES
).hexdigest()
_PINNED_SCHEMA_IDENTITY_DOCUMENT = _SCHEMA_IDENTITY_DOCUMENT
_PINNED_SCHEMA_DOCUMENT_BYTES = _SCHEMA_DOCUMENT_BYTES


def _is_safe_path(value: object) -> bool:
    return (
        type(value) is str
        and value == value.strip()
        and _PINNED_SAFE_PROJECT_PATH.fullmatch(value) is not None
        and not value.startswith("/")
        and not value.endswith("/")
        and "\\" not in value
        and all(part not in ("", ".", "..") for part in value.split("/"))
    )


def _require_canonical_python_source(value: object, *, role: str) -> bytes:
    if type(value) is not bytes:
        raise _PINNED_ERROR_CLASS(f"{role} source must be exact bytes")
    if value.startswith(b"\xef\xbb\xbf"):
        raise _PINNED_ERROR_CLASS(f"{role} source has a UTF-8 BOM")
    if b"\r" in value:
        raise _PINNED_ERROR_CLASS(f"{role} source is not canonical LF")
    if b"\x00" in value:
        raise _PINNED_ERROR_CLASS(f"{role} source contains NUL")
    try:
        text = value.decode("utf-8", errors="strict")
        _PINNED_AST_PARSE(text)
    except (UnicodeDecodeError, SyntaxError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS(
            f"{role} source is not strict UTF-8 Python"
        ) from exc
    return value


def _require_expected_sources(
) -> tuple[tuple[str, str, str, int, str], ...]:
    expected = _PINNED_EXPECTED_SOURCE_SNAPSHOT_FACTORY()
    if (
        type(EXPECTED_SOURCE_FILES) is not tuple
        or len(EXPECTED_SOURCE_FILES) != len(expected)
        or len(expected) != EXPECTED_SOURCE_FILE_COUNT
    ):
        raise _PINNED_ERROR_CLASS("expected source inventory changed")
    seen_project_paths: set[str] = set()
    seen_casefold_paths: set[str] = set()
    for item, required in zip(EXPECTED_SOURCE_FILES, expected, strict=True):
        if (
            type(item) is not _PINNED_EXPECTED_SOURCE_CLASS
            or type(item.role) is not str
            or type(item.repository_path) is not str
            or type(item.project_path) is not str
            or type(item.byte_count) is not int
            or type(item.sha256) is not str
        ):
            raise _PINNED_ERROR_CLASS("expected source descriptor changed")
        if (
            (
                item.role,
                item.repository_path,
                item.project_path,
                item.byte_count,
                item.sha256,
            )
            != required
            or not _is_safe_path(item.repository_path)
            or not _is_safe_path(item.project_path)
            or item.byte_count < 0
            or _PINNED_HEX_64.fullmatch(item.sha256) is None
        ):
            raise _PINNED_ERROR_CLASS("expected source descriptor changed")
        folded = item.project_path.casefold()
        if item.project_path in seen_project_paths or folded in seen_casefold_paths:
            raise _PINNED_ERROR_CLASS("project source paths collide")
        seen_project_paths.add(item.project_path)
        seen_casefold_paths.add(folded)
    if (
        EXPECTED_SOURCE_FILES[0].project_path != "main.py"
        or EXPECTED_SOURCE_FILES[0].sha256
        != "327f126311c12e9f37297f229a3946a6cb1f2bbe26ed6c746cf140b26c2e6bf9"
        or EXPECTED_SOURCE_FILES[0].byte_count != 3_328
    ):
        raise _PINNED_ERROR_CLASS("entry source identity changed")
    return expected


def _require_static_contract(
) -> tuple[tuple[str, str, str, int, str], ...]:
    if _PINNED_GLOBALS() is not _MODULE_GLOBALS:
        raise _PINNED_ERROR_CLASS("source assembly module globals changed")
    for name, expected in _PINNED_STATIC_SNAPSHOT_BINDINGS:
        if _MODULE_GLOBALS.get(name) is not expected:
            raise _PINNED_ERROR_CLASS(
                "source assembly static snapshot changed"
            )
    for name, expected in _PINNED_ALIAS_BINDINGS:
        if _MODULE_GLOBALS.get(name) is not expected:
            raise _PINNED_ERROR_CLASS(
                "source assembly pinned binding changed"
            )
    if (
        _PINNED_TYPE(_PINNED_MODULE_BINDINGS) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_DEPENDENCY_CALLABLES) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_IMPORTED_BINDINGS) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_BUILTIN_BINDINGS) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_LOCAL_FUNCTION_STATES) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_PARENT_FUNCTION_STATES) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_CLASS_BINDINGS) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_CLASS_STATES) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_CLASS_FUNCTION_STATES)
        is not _PINNED_TUPLE
    ):
        raise _PINNED_ERROR_CLASS("source assembly static topology changed")
    for name, expected in _PINNED_MODULE_BINDINGS:
        if _MODULE_GLOBALS.get(name) is not expected:
            raise _PINNED_ERROR_CLASS(
                "source assembly dependency module changed"
            )
    for module, name, expected in _PINNED_DEPENDENCY_CALLABLES:
        if _PINNED_GETATTR(module, name) is not expected:
            raise _PINNED_ERROR_CLASS(
                "source assembly dependency callable changed"
            )
    for name, expected in _PINNED_IMPORTED_BINDINGS:
        if _MODULE_GLOBALS.get(name) is not expected:
            raise _PINNED_ERROR_CLASS(
                "source assembly parent binding changed"
            )
    if (
        _PINNED_TYPE(_PINNED_BUILTINS_DICT) is not _PINNED_DICT
        or _MODULE_GLOBALS.get("__builtins__") is not _PINNED_BUILTINS_DICT
    ):
        raise _PINNED_ERROR_CLASS("source assembly builtins root changed")
    for name, expected in _PINNED_BUILTIN_BINDINGS:
        if (
            name in _MODULE_GLOBALS
            or _PINNED_BUILTINS_DICT.get(name) is not expected
        ):
            raise _PINNED_ERROR_CLASS(
                "source assembly builtin resolution changed"
            )
    for implementation, code, defaults, kwdefaults, closure, cells in (
        _PINNED_PARENT_FUNCTION_STATES
    ):
        if (
            implementation.__code__ is not code
            or implementation.__defaults__ is not defaults
            or implementation.__kwdefaults__ is not kwdefaults
            or implementation.__closure__ is not closure
        ):
            raise _PINNED_ERROR_CLASS(
                "source assembly parent function changed"
            )
        for cell, content_type, content in cells:
            try:
                current_content = cell.cell_contents
            except _PINNED_VALUE_ERROR as exc:
                raise _PINNED_ERROR_CLASS(
                    "source assembly parent closure changed"
                ) from exc
            if (
                _PINNED_TYPE(current_content) is not content_type
                or current_content is not content
            ):
                raise _PINNED_ERROR_CLASS(
                    "source assembly parent closure changed"
                )
    try:
        parent_schema = _PINNED_RENDER_B4_SCHEMA()
    except (
        _PINNED_B4_ERROR_CLASS,
        _PINNED_TYPE_ERROR,
        _PINNED_VALUE_ERROR,
    ) as exc:
        raise _PINNED_ERROR_CLASS(
            "B4 static preflight refused this runtime"
        ) from exc
    if (
        _PINNED_TYPE(parent_schema) is not _PINNED_BYTES
        or _PINNED_SHA256(parent_schema).hexdigest()
        != B4_SCHEMA_ARTIFACT_SHA256
    ):
        raise _PINNED_ERROR_CLASS("B4 schema artifact identity changed")
    for name, expected, code, defaults, kwdefaults, closure, cells in (
        _PINNED_LOCAL_FUNCTION_STATES
    ):
        current = _MODULE_GLOBALS.get(name)
        if (
            current is not expected
            or expected.__code__ is not code
            or expected.__defaults__ is not defaults
            or expected.__kwdefaults__ is not kwdefaults
            or expected.__closure__ is not closure
        ):
            raise _PINNED_ERROR_CLASS(
                "source assembly function identity changed"
            )
        for cell, content_type, content in cells:
            try:
                current_content = cell.cell_contents
            except _PINNED_VALUE_ERROR as exc:
                raise _PINNED_ERROR_CLASS(
                    "source assembly function closure changed"
                ) from exc
            if (
                _PINNED_TYPE(current_content) is not content_type
                or current_content is not content
            ):
                raise _PINNED_ERROR_CLASS(
                    "source assembly function closure changed"
                )
    for name, expected in _PINNED_CLASS_BINDINGS:
        if _MODULE_GLOBALS.get(name) is not expected:
            raise _PINNED_ERROR_CLASS(
                "source assembly class identity changed"
            )
    for (
        accepted_class,
        expected_metaclass,
        expected_bases,
        expected_mro,
        expected_members,
    ) in _PINNED_CLASS_STATES:
        current_bases = accepted_class.__bases__
        current_mro = accepted_class.__mro__
        if (
            _PINNED_TYPE(accepted_class) is not expected_metaclass
            or _PINNED_TYPE(current_bases) is not _PINNED_TUPLE
            or _PINNED_LEN(current_bases) != _PINNED_LEN(expected_bases)
            or _PINNED_ANY(
                current is not expected
                for current, expected in _PINNED_ZIP(
                    current_bases, expected_bases, strict=True
                )
            )
            or _PINNED_TYPE(current_mro) is not _PINNED_TUPLE
            or _PINNED_LEN(current_mro) != _PINNED_LEN(expected_mro)
            or _PINNED_ANY(
                current is not expected
                for current, expected in _PINNED_ZIP(
                    current_mro, expected_mro, strict=True
                )
            )
        ):
            raise _PINNED_ERROR_CLASS(
                "source assembly class ancestry changed"
            )
        current_members = _PINNED_TUPLE(
            _PINNED_VARS(accepted_class).items()
        )
        if _PINNED_LEN(current_members) != _PINNED_LEN(expected_members):
            raise _PINNED_ERROR_CLASS(
                "source assembly class topology changed"
            )
        for current, expected in _PINNED_ZIP(
            current_members, expected_members, strict=True
        ):
            if (
                _PINNED_TYPE(current[0]) is not _PINNED_STR
                or current[0] != expected[0]
                or current[1] is not expected[1]
            ):
                raise _PINNED_ERROR_CLASS(
                    "source assembly class topology changed"
                )
    for implementation, code, defaults, kwdefaults, closure, cells in (
        _PINNED_CLASS_FUNCTION_STATES
    ):
        if (
            implementation.__code__ is not code
            or implementation.__defaults__ is not defaults
            or implementation.__kwdefaults__ is not kwdefaults
            or implementation.__closure__ is not closure
        ):
            raise _PINNED_ERROR_CLASS(
                "source assembly class function changed"
            )
        for cell, content_type, content in cells:
            try:
                current_content = cell.cell_contents
            except _PINNED_VALUE_ERROR as exc:
                raise _PINNED_ERROR_CLASS(
                    "source assembly class closure changed"
                ) from exc
            if (
                _PINNED_TYPE(current_content) is not content_type
                or current_content is not content
            ):
                raise _PINNED_ERROR_CLASS(
                    "source assembly class closure changed"
                )
    if (
        EXPECTED_SOURCE_FILES is not _PINNED_EXPECTED_SOURCE_FILES
        or EXTERNAL_BINDINGS is not _PINNED_EXTERNAL_BINDINGS
        or CAPABILITIES is not _PINNED_CAPABILITIES
        or FORMAL_PRIMARY_FOLD_IDS is not _PINNED_FORMAL_PRIMARY_FOLD_IDS
        or DESCRIPTIVE_SENSITIVITY_FOLD_IDS
        is not _PINNED_DESCRIPTIVE_SENSITIVITY_FOLD_IDS
        or ASSEMBLY_PUBLIC_FIELD_NAMES
        is not _PINNED_ASSEMBLY_PUBLIC_FIELD_NAMES
        or ASSEMBLY_TRUTH_FIELD_VALUES
        is not _PINNED_ASSEMBLY_TRUTH_FIELD_VALUES
        or FALSE_PROPERTY_NAMES is not _PINNED_FALSE_PROPERTY_NAMES
        or _HEX_64 is not _PINNED_HEX_64
        or _SAFE_PROJECT_PATH is not _PINNED_SAFE_PROJECT_PATH
        or _SCHEMA_IDENTITY_DOCUMENT
        is not _PINNED_SCHEMA_IDENTITY_DOCUMENT
        or _PINNED_TYPE(_SCHEMA_IDENTITY_DOCUMENT) is not _PINNED_DICT
        or _SCHEMA_DOCUMENT_BYTES is not _PINNED_SCHEMA_DOCUMENT_BYTES
        or _PINNED_TYPE(_SCHEMA_DOCUMENT_BYTES) is not _PINNED_BYTES
    ):
        raise _PINNED_ERROR_CLASS("source assembly registry changed")
    scalar_contract = (
        (SCHEMA, "arv2-qc-lean-source-assembly-schema-v1"),
        (STATUS, "offline_source_inventory_authenticated_runtime_refuses"),
        (
            AUTHORITY,
            "offline_values_only_no_client_callback_filesystem_environment_"
            "provider_credential_account_project_object_store_upload_compile_"
            "launch_result_deployment_order_or_trading_authority",
        ),
        (HASH_DOMAIN, "arv2-qc-lean-source-assembly-v1"),
        (ENTRY_PROJECT_PATH, "main.py"),
        (ENTRY_CLASS_NAME, "AnalystRevisionsV2StockEventStudyScaffold"),
        (SCAFFOLD_SCHEMA, "arv2-qc-lean-entry-scaffold-v2"),
        (SCHEMA_ID, "arv2-qc-lean-source-assembly-ae4c1324f36cc6fc"),
        (
            SCHEMA_SHA256,
            "ae4c1324f36cc6fca0218f474bdc091bf82862e8f21ada35e01a09b022bb77a5",
        ),
        (
            SCHEMA_ARTIFACT_SHA256,
            "532aeb471fed96c525f8be9db84694c546c1cccc6008347a43efadfac678ac20",
        ),
        (B4_SCHEMA_ID, "arv2-qc-object-store-read-contract-5dcb6cffb8f9688b"),
        (
            B4_SCHEMA_SHA256,
            "5dcb6cffb8f9688b1a63a0ea452fd7f4c3e706df7941691ede58c95e0f055dd2",
        ),
        (
            B4_SCHEMA_ARTIFACT_SHA256,
            "95c3242405dddaaec40af01113a6823235fa74fcf405ab7b30ab5c6a45a8e987",
        ),
        (
            SCAFFOLD_SOURCE_SHA256,
            "327f126311c12e9f37297f229a3946a6cb1f2bbe26ed6c746cf140b26c2e6bf9",
        ),
        (
            B4_SOURCE_SHA256,
            "bf370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3",
        ),
    )
    if _PINNED_ANY(
        _PINNED_TYPE(actual) is not _PINNED_STR or actual != expected
        for actual, expected in scalar_contract
    ):
        raise _PINNED_ERROR_CLASS("source assembly scalar identity changed")
    if (
        _PINNED_TYPE(SCAFFOLD_SOURCE_BYTE_COUNT) is not _PINNED_INT
        or SCAFFOLD_SOURCE_BYTE_COUNT != 3_328
        or _PINNED_TYPE(B4_SOURCE_BYTE_COUNT) is not _PINNED_INT
        or B4_SOURCE_BYTE_COUNT != 57_361
        or _PINNED_TYPE(EXPECTED_SOURCE_FILE_COUNT) is not _PINNED_INT
        or EXPECTED_SOURCE_FILE_COUNT != 11
        or _PINNED_TYPE(EXPECTED_OBJECT_STORE_CALL_COUNT) is not _PINNED_INT
        or EXPECTED_OBJECT_STORE_CALL_COUNT != B4_EXPECTED_EVENT_COUNT == 18
    ):
        raise _PINNED_ERROR_CLASS("source assembly numeric identity changed")
    if (
        _PINNED_TYPE(FORMAL_PRIMARY_FOLD_IDS) is not _PINNED_TUPLE
        or FORMAL_PRIMARY_FOLD_IDS != _PINNED_TUPLE(
            f"arv2-wf-test-{year}" for year in _PINNED_RANGE(2020, 2026)
        )
        or _PINNED_TYPE(DESCRIPTIVE_SENSITIVITY_FOLD_IDS)
        is not _PINNED_TUPLE
        or DESCRIPTIVE_SENSITIVITY_FOLD_IDS != _PINNED_TUPLE(
            f"arv2-wf-test-{year}" for year in _PINNED_RANGE(2021, 2026)
        )
    ):
        raise _PINNED_ERROR_CLASS("evaluation window identity changed")
    if (
        _PINNED_TYPE(EXTERNAL_BINDINGS) is not _PINNED_TUPLE
        or _PINNED_ANY(
            _PINNED_TYPE(item) is not _PINNED_TUPLE
            or _PINNED_LEN(item) != 2
            or _PINNED_TYPE(item[0]) is not _PINNED_STR
            or item[1] is not None
            for item in EXTERNAL_BINDINGS
        )
        or _PINNED_TYPE(CAPABILITIES) is not _PINNED_TUPLE
        or _PINNED_ANY(
            _PINNED_TYPE(item) is not _PINNED_TUPLE
            or _PINNED_LEN(item) != 2
            or _PINNED_TYPE(item[0]) is not _PINNED_STR
            or item[1] is not False
            for item in CAPABILITIES
        )
    ):
        raise _PINNED_ERROR_CLASS("source assembly gained authority")
    expected = _PINNED_REQUIRE_EXPECTED_SOURCES()
    seed_document = _PINNED_SCHEMA_SEED_DOCUMENT()
    rebuilt_document, rebuilt_hash = _PINNED_IDENTITY_DOCUMENT(
        seed_document,
        id_key="schema_id",
        hash_key="schema_sha256",
        prefix="arv2-qc-lean-source-assembly",
    )
    rebuilt_bytes = _PINNED_CANONICAL_BYTES(rebuilt_document)
    if (
        rebuilt_hash != SCHEMA_SHA256
        or SCHEMA_ID != f"arv2-qc-lean-source-assembly-{rebuilt_hash[:16]}"
        or rebuilt_bytes != _PINNED_SCHEMA_DOCUMENT_BYTES
        or _PINNED_CANONICAL_BYTES(_SCHEMA_IDENTITY_DOCUMENT)
        != _PINNED_SCHEMA_DOCUMENT_BYTES
        or _PINNED_SHA256(rebuilt_bytes).hexdigest()
        != SCHEMA_ARTIFACT_SHA256
    ):
        raise _PINNED_ERROR_CLASS("source assembly schema identity changed")
    return expected


def render_qc_lean_source_assembly_schema_bytes() -> bytes:
    """Render the content-addressed B5B schema without opening a source."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    return _PINNED_SCHEMA_DOCUMENT_BYTES


def _capture_contract_snapshot() -> tuple[object, ...]:
    """Freeze every authenticated module value used in emitted output."""

    snapshot = (
        SCHEMA_ID,
        SCHEMA_SHA256,
        SCHEMA_ARTIFACT_SHA256,
        STATUS,
        AUTHORITY,
        ENTRY_PROJECT_PATH,
        ENTRY_CLASS_NAME,
        FORMAL_PRIMARY_FOLD_IDS,
        DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
        EXTERNAL_BINDINGS,
        CAPABILITIES,
        HASH_DOMAIN,
    )
    string_contract = (
        (snapshot[0], "arv2-qc-lean-source-assembly-ae4c1324f36cc6fc"),
        (
            snapshot[1],
            "ae4c1324f36cc6fca0218f474bdc091bf82862e8f21ada35e01a09b022bb77a5",
        ),
        (
            snapshot[2],
            "532aeb471fed96c525f8be9db84694c546c1cccc6008347a43efadfac678ac20",
        ),
        (snapshot[3], "offline_source_inventory_authenticated_runtime_refuses"),
        (
            snapshot[4],
            "offline_values_only_no_client_callback_filesystem_environment_"
            "provider_credential_account_project_object_store_upload_compile_"
            "launch_result_deployment_order_or_trading_authority",
        ),
        (snapshot[5], "main.py"),
        (snapshot[6], "AnalystRevisionsV2StockEventStudyScaffold"),
        (snapshot[11], "arv2-qc-lean-source-assembly-v1"),
    )
    if _PINNED_ANY(
        _PINNED_TYPE(actual) is not _PINNED_STR or actual != expected
        for actual, expected in string_contract
    ):
        raise _PINNED_ERROR_CLASS("source assembly output contract changed")
    if (
        snapshot[7] is not _PINNED_FORMAL_PRIMARY_FOLD_IDS
        or snapshot[8] is not _PINNED_DESCRIPTIVE_SENSITIVITY_FOLD_IDS
        or snapshot[9] is not _PINNED_EXTERNAL_BINDINGS
        or snapshot[10] is not _PINNED_CAPABILITIES
    ):
        raise _PINNED_ERROR_CLASS("source assembly output registry changed")
    return snapshot


def _capture_parent_snapshot(
    run_candidate: SyntheticQcRunCandidate,
    plan: SyntheticQcObjectStoreReadPlan,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    tuple[tuple[int, str, int, str], ...],
]:
    """Detach B2, rebuild B4, then return authenticated exact primitives."""

    try:
        bound_candidate = plan._run_candidate
        candidate_code_files = run_candidate.code_files
        candidate_partitions = run_candidate.synthetic_partitions
        live_candidate_identity = (
            run_candidate.candidate_id,
            run_candidate.candidate_hash,
            run_candidate._canonical_document,
        )
        fixture = plan._fixture
        transport_index_key = plan.transport_index_key
        synthetic_max_size = plan.synthetic_max_size
        synthetic_max_files = plan.synthetic_max_files
        live_identity = (
            plan.plan_id,
            plan.plan_hash,
            plan.plan_artifact_sha256,
            plan._canonical_document,
        )
        live_objects = _PINNED_TUPLE(
            (
                item.ordinal,
                item.object_store_key,
                item.byte_count,
                item.artifact_sha256,
            )
            for item in plan.objects
        )
    except _PINNED_ATTRIBUTE_ERROR as exc:
        raise _PINNED_ERROR_CLASS("B4 lineage topology changed") from exc
    if bound_candidate is not run_candidate:
        raise _PINNED_ERROR_CLASS("B4 lineage topology changed")
    try:
        detached_candidate = _PINNED_BUILD_RUN_CANDIDATE(
            code_files=candidate_code_files,
            synthetic_partitions=candidate_partitions,
        )
        _PINNED_REQUIRE_RUN_CANDIDATE(detached_candidate)
        detached_candidate_identity = (
            detached_candidate.candidate_id,
            detached_candidate.candidate_hash,
            detached_candidate._canonical_document,
        )
        if (
            _PINNED_TYPE(detached_candidate)
            is not _PINNED_RUN_CANDIDATE_CLASS
            or _PINNED_ANY(
                _PINNED_TYPE(value) is not _PINNED_STR
                for value in (
                    *live_candidate_identity[:2],
                    *detached_candidate_identity[:2],
                )
            )
            or _PINNED_TYPE(live_candidate_identity[2])
            is not _PINNED_BYTES
            or _PINNED_TYPE(detached_candidate_identity[2])
            is not _PINNED_BYTES
            or live_candidate_identity != detached_candidate_identity
            or run_candidate.code_files != detached_candidate.code_files
            or run_candidate.synthetic_partitions
            != detached_candidate.synthetic_partitions
        ):
            raise _PINNED_ERROR_CLASS("B2 candidate projection changed")
        rebuilt = _PINNED_BUILD_READ_PLAN(
            run_candidate=detached_candidate,
            object_store=fixture,
            transport_index_key=transport_index_key,
            synthetic_max_size=synthetic_max_size,
            synthetic_max_files=synthetic_max_files,
        )
        _PINNED_REQUIRE_READ_PLAN(rebuilt)
    except (
        _PINNED_ATTRIBUTE_ERROR,
        _PINNED_B4_ERROR_CLASS,
        _PINNED_RUN_CANDIDATE_ERROR_CLASS,
        _PINNED_TYPE_ERROR,
        _PINNED_VALUE_ERROR,
    ) as exc:
        raise _PINNED_ERROR_CLASS("B4 retained state changed") from exc
    try:
        rebuilt_identity = (
            rebuilt.plan_id,
            rebuilt.plan_hash,
            rebuilt.plan_artifact_sha256,
            rebuilt._canonical_document,
        )
        candidate_id = detached_candidate.candidate_id
        candidate_hash = detached_candidate.candidate_hash
        rebuilt_objects = _PINNED_TUPLE(
            (
                item.ordinal,
                item.object_store_key,
                item.byte_count,
                item.artifact_sha256,
            )
            for item in rebuilt.objects
        )
    except _PINNED_ATTRIBUTE_ERROR as exc:
        raise _PINNED_ERROR_CLASS("B4 rebuilt topology changed") from exc
    scalar_values = (
        *live_identity[:3],
        *rebuilt_identity[:3],
        candidate_id,
        candidate_hash,
    )
    if (
        _PINNED_TYPE(rebuilt) is not _PINNED_READ_PLAN_CLASS
        or rebuilt._run_candidate is not detached_candidate
        or _PINNED_ANY(
            _PINNED_TYPE(value) is not _PINNED_STR
            for value in scalar_values
        )
        or _PINNED_TYPE(live_identity[3]) is not _PINNED_BYTES
        or _PINNED_TYPE(rebuilt_identity[3]) is not _PINNED_BYTES
        or _PINNED_ANY(
            _PINNED_TYPE(item) is not _PINNED_TUPLE
            or _PINNED_LEN(item) != 4
            or _PINNED_TYPE(item[0]) is not _PINNED_INT
            or _PINNED_TYPE(item[1]) is not _PINNED_STR
            or _PINNED_TYPE(item[2]) is not _PINNED_INT
            or _PINNED_TYPE(item[3]) is not _PINNED_STR
            for item in (*live_objects, *rebuilt_objects)
        )
        or live_identity != rebuilt_identity
        or live_objects != rebuilt_objects
    ):
        raise _PINNED_ERROR_CLASS("B4 object projection changed")
    return (
        rebuilt_identity[0],
        rebuilt_identity[1],
        rebuilt_identity[2],
        candidate_id,
        candidate_hash,
        rebuilt_objects,
    )


def _require_source_snapshot(
    snapshot: object,
    expected: tuple[tuple[str, str, str, int, str], ...],
) -> tuple[tuple[str, str, str, bytes, int, str], ...]:
    """Authenticate an immutable primitive copy of every supplied source."""

    if (
        _PINNED_TYPE(snapshot) is not _PINNED_TUPLE
        or _PINNED_LEN(snapshot) != _PINNED_LEN(expected)
    ):
        raise _PINNED_ERROR_CLASS("source snapshot topology changed")
    for item, required in _PINNED_ZIP(snapshot, expected, strict=True):
        if (
            _PINNED_TYPE(item) is not _PINNED_TUPLE
            or _PINNED_LEN(item) != 6
            or _PINNED_TYPE(item[0]) is not _PINNED_STR
            or _PINNED_TYPE(item[1]) is not _PINNED_STR
            or _PINNED_TYPE(item[2]) is not _PINNED_STR
            or _PINNED_TYPE(item[3]) is not _PINNED_BYTES
            or _PINNED_TYPE(item[4]) is not _PINNED_INT
            or _PINNED_TYPE(item[5]) is not _PINNED_STR
        ):
            raise _PINNED_ERROR_CLASS("source snapshot topology changed")
        if (
            (item[0], item[1], item[2], item[4], item[5]) != required
            or _PINNED_LEN(item[3]) != item[4]
            or _PINNED_SHA256(item[3]).hexdigest() != item[5]
            or _PINNED_REQUIRE_CANONICAL_SOURCE(item[3], role=item[0])
            is not item[3]
        ):
            raise _PINNED_ERROR_CLASS("source snapshot identity changed")
    return snapshot


def _require_constructed_files(
    files: object,
    snapshot: tuple[tuple[str, str, str, bytes, int, str], ...],
) -> None:
    """Refuse mutation of constructed DTOs before returning an assembly."""

    if (
        _PINNED_TYPE(files) is not _PINNED_TUPLE
        or _PINNED_LEN(files) != _PINNED_LEN(snapshot)
    ):
        raise _PINNED_ERROR_CLASS("constructed source files changed")
    for item, required in _PINNED_ZIP(files, snapshot, strict=True):
        if _PINNED_TYPE(item) is not _PINNED_PROJECT_FILE_CLASS:
            raise _PINNED_ERROR_CLASS("constructed source files changed")
        try:
            current = (
                item.role,
                item.repository_path,
                item.project_path,
                item.source_bytes,
                item.byte_count,
                item.sha256,
            )
        except _PINNED_ATTRIBUTE_ERROR as exc:
            raise _PINNED_ERROR_CLASS(
                "constructed source files changed"
            ) from exc
        if _PINNED_ANY(
            _PINNED_TYPE(value) is not expected_type
            for value, expected_type in _PINNED_ZIP(
                current,
                (
                    _PINNED_STR,
                    _PINNED_STR,
                    _PINNED_STR,
                    _PINNED_BYTES,
                    _PINNED_INT,
                    _PINNED_STR,
                ),
                strict=True,
            )
        ) or _PINNED_ANY(
            value is not required_value
            for value, required_value in _PINNED_ZIP(
                current, required, strict=True
            )
        ):
            raise _PINNED_ERROR_CLASS("constructed source files changed")


def _derive_object_store_calls(
    parent_snapshot: tuple[
        str,
        str,
        str,
        str,
        str,
        tuple[tuple[int, str, int, str], ...],
    ],
) -> tuple[LeanObjectStoreCallBinding, ...]:
    calls: list[LeanObjectStoreCallBinding] = []
    for ordinal, object_store_key, byte_count, artifact_sha256 in (
        parent_snapshot[5]
    ):
        calls.append(
            _PINNED_CALL_BINDING_CLASS(
                ordinal=len(calls) + 1,
                operation="contains_key",
                method_name="contains_key",
                object_store_key=object_store_key,
                expected_found=True,
                expected_byte_count=None,
                expected_sha256=None,
            )
        )
        calls.append(
            _PINNED_CALL_BINDING_CLASS(
                ordinal=len(calls) + 1,
                operation="read_bytes",
                method_name="read_bytes",
                object_store_key=object_store_key,
                expected_found=None,
                expected_byte_count=byte_count,
                expected_sha256=artifact_sha256,
            )
        )
    if len(calls) != EXPECTED_OBJECT_STORE_CALL_COUNT:
        raise _PINNED_ERROR_CLASS("Object Store call census changed")
    return tuple(calls)


def _assembly_seed_document(
    *,
    contract_snapshot: tuple[object, ...],
    parent_snapshot: tuple[
        str,
        str,
        str,
        str,
        str,
        tuple[tuple[int, str, int, str], ...],
    ],
    source_snapshot: tuple[tuple[str, str, str, bytes, int, str], ...],
    calls: tuple[LeanObjectStoreCallBinding, ...],
) -> dict[str, object]:
    (
        schema_id,
        schema_sha256,
        schema_artifact_sha256,
        status,
        authority,
        entry_project_path,
        entry_class_name,
        formal_fold_ids,
        sensitivity_fold_ids,
        external_bindings,
        capabilities,
        _hash_domain,
    ) = contract_snapshot
    (
        plan_id,
        plan_hash,
        plan_artifact_sha256,
        candidate_id,
        candidate_hash,
        _plan_objects,
    ) = parent_snapshot
    return {
        "schema_id": schema_id,
        "schema_sha256": schema_sha256,
        "schema_artifact_sha256": schema_artifact_sha256,
        "status": status,
        "authority": authority,
        "assembly_id": None,
        "assembly_hash": None,
        "entry_project_path": entry_project_path,
        "entry_class_name": entry_class_name,
        "files": [
            {
                "role": item[0],
                "repository_path": item[1],
                "project_path": item[2],
                "byte_count": item[4],
                "sha256": item[5],
            }
            for item in source_snapshot
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
            for item in calls
        ],
        "lineage": {
            "plan_id": plan_id,
            "plan_hash": plan_hash,
            "plan_artifact_sha256": plan_artifact_sha256,
            "run_candidate_id": candidate_id,
            "run_candidate_hash": candidate_hash,
        },
        "evaluation_windows": {
            "formal_primary_fold_ids": list(formal_fold_ids),
            "descriptive_sensitivity_fold_ids": list(
                sensitivity_fold_ids
            ),
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
            "file_count": len(source_snapshot),
            "total_byte_count": sum(item[4] for item in source_snapshot),
            "largest_project_file_byte_count": max(
                item[4] for item in source_snapshot
            ),
            "actual_project_file_quota_authenticated": False,
        },
        "external_bindings": dict(external_bindings),
        "capabilities": dict(capabilities),
    }


def build_synthetic_qc_lean_source_assembly(
    *,
    run_candidate: SyntheticQcRunCandidate,
    read_plan: SyntheticQcObjectStoreReadPlan,
    source_files: tuple[LeanSourceInput, ...],
) -> SyntheticLeanProjectAssembly:
    """Authenticate supplied bytes and derive an inert synthetic source tree."""

    expected = _PINNED_REQUIRE_STATIC_CONTRACT()
    contract_snapshot = _PINNED_CAPTURE_CONTRACT_SNAPSHOT()
    try:
        _PINNED_REQUIRE_RUN_CANDIDATE(run_candidate)
        _PINNED_REQUIRE_READ_PLAN(read_plan)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS("B4 lineage is not authenticated") from exc
    if read_plan._run_candidate is not run_candidate:
        raise _PINNED_ERROR_CLASS("read plan is not bound to this candidate")
    parent_snapshot = _PINNED_CAPTURE_PARENT_SNAPSHOT(
        run_candidate, read_plan
    )
    try:
        _PINNED_REQUIRE_RUN_CANDIDATE(run_candidate)
        _PINNED_REQUIRE_READ_PLAN(read_plan)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS(
            "B4 lineage changed during source assembly"
        ) from exc
    if parent_snapshot != _PINNED_CAPTURE_PARENT_SNAPSHOT(
        run_candidate, read_plan
    ):
        raise _PINNED_ERROR_CLASS("B4 plan changed during source assembly")
    if type(source_files) is not tuple or len(source_files) != len(expected):
        raise _PINNED_ERROR_CLASS("source file inventory must be exact")

    source_values: list[tuple[str, str, str, bytes, int, str]] = []
    for supplied, required in zip(source_files, expected, strict=True):
        (
            required_role,
            required_repository_path,
            required_project_path,
            required_byte_count,
            required_sha256,
        ) = required
        if (
            type(supplied) is not _PINNED_SOURCE_INPUT_CLASS
            or type(supplied.role) is not str
            or type(supplied.repository_path) is not str
            or type(supplied.project_path) is not str
            or type(supplied.source_bytes) is not bytes
        ):
            raise _PINNED_ERROR_CLASS("source input type changed")
        if (
            supplied.role != required_role
            or supplied.repository_path != required_repository_path
            or supplied.project_path != required_project_path
            or not _PINNED_IS_SAFE_PATH(supplied.repository_path)
            or not _PINNED_IS_SAFE_PATH(supplied.project_path)
        ):
            raise _PINNED_ERROR_CLASS("source path or role changed")
        payload = supplied.source_bytes
        if (
            len(payload) != required_byte_count
            or _PINNED_SHA256(payload).hexdigest() != required_sha256
        ):
            raise _PINNED_ERROR_CLASS("source byte identity changed")
        payload = _PINNED_REQUIRE_CANONICAL_SOURCE(
            payload, role=supplied.role
        )
        source_values.append(
            (
                required_role,
                required_repository_path,
                required_project_path,
                payload,
                required_byte_count,
                required_sha256,
            )
        )

    source_snapshot = _PINNED_REQUIRE_SOURCE_SNAPSHOT(
        _PINNED_TUPLE(source_values), expected
    )
    project_paths = tuple(item[2] for item in source_snapshot)
    if (
        len(set(project_paths)) != len(project_paths)
        or len({item.casefold() for item in project_paths}) != len(project_paths)
        or project_paths.count(contract_snapshot[5]) != 1
    ):
        raise _PINNED_ERROR_CLASS("project paths are not unique and exact")

    try:
        _PINNED_REQUIRE_READ_PLAN(read_plan)
        _PINNED_REQUIRE_RUN_CANDIDATE(run_candidate)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS(
            "B4 lineage changed during source assembly"
        ) from exc
    if parent_snapshot != _PINNED_CAPTURE_PARENT_SNAPSHOT(
        run_candidate, read_plan
    ):
        raise _PINNED_ERROR_CLASS("B4 plan changed during source assembly")

    calls = _PINNED_DERIVE_OBJECT_STORE_CALLS(parent_snapshot)
    seed = _PINNED_ASSEMBLY_SEED_DOCUMENT(
        contract_snapshot=contract_snapshot,
        parent_snapshot=parent_snapshot,
        source_snapshot=source_snapshot,
        calls=calls,
    )
    document, assembly_hash = _PINNED_IDENTITY_DOCUMENT(
        seed,
        id_key="assembly_id",
        hash_key="assembly_hash",
        prefix="arv2-qc-lean-source-assembly",
        hash_domain=contract_snapshot[11],
    )
    canonical = _PINNED_CANONICAL_BYTES(document)
    (
        plan_id,
        plan_hash,
        plan_artifact_sha256,
        candidate_id,
        candidate_hash,
        _plan_objects,
    ) = parent_snapshot
    file_tuple = _PINNED_TUPLE(
        _PINNED_PROJECT_FILE_CLASS(
            role=item[0],
            repository_path=item[1],
            project_path=item[2],
            source_bytes=item[3],
            byte_count=item[4],
            sha256=item[5],
        )
        for item in source_snapshot
    )
    assembly = _PINNED_ASSEMBLY_CLASS(
        assembly_id=str(document["assembly_id"]),
        assembly_hash=assembly_hash,
        assembly_artifact_sha256=_PINNED_SHA256(canonical).hexdigest(),
        entry_project_path=contract_snapshot[5],
        entry_class_name=contract_snapshot[6],
        files=file_tuple,
        object_store_calls=calls,
        plan_id=plan_id,
        plan_hash=plan_hash,
        plan_artifact_sha256=plan_artifact_sha256,
        run_candidate_id=candidate_id,
        run_candidate_hash=candidate_hash,
        total_source_byte_count=sum(item[4] for item in source_snapshot),
        largest_project_file_byte_count=max(
            item[4] for item in source_snapshot
        ),
        source_only=True,
        adapter_call_contract_present=True,
        physical_adapter_present=False,
        real_qc_object_store_access_performed=False,
        project_created=False,
        cloud_compile_performed=False,
        backtest_performed=False,
        external_bindings=contract_snapshot[9],
        capabilities=contract_snapshot[10],
        _plan=read_plan,
        _run_candidate=run_candidate,
        _canonical_document=canonical,
    )
    if (
        _PINNED_ANY(
            binding is not None for _, binding in assembly.external_bindings
        )
        or _PINNED_ANY(
            enabled is not False for _, enabled in assembly.capabilities
        )
        or _PINNED_ANY(
            _PINNED_GETATTR(assembly, name) is not False
            for name in _PINNED_FALSE_PROPERTY_NAMES
        )
    ):
        raise _PINNED_ERROR_CLASS("source assembly gained authority")
    try:
        _PINNED_REQUIRE_READ_PLAN(read_plan)
        _PINNED_REQUIRE_RUN_CANDIDATE(run_candidate)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS(
            "B4 lineage changed during source assembly"
        ) from exc
    if parent_snapshot != _PINNED_CAPTURE_PARENT_SNAPSHOT(
        run_candidate, read_plan
    ):
        raise _PINNED_ERROR_CLASS("B4 plan changed during source assembly")
    _PINNED_REQUIRE_STATIC_CONTRACT()
    _PINNED_REQUIRE_CONSTRUCTED_FILES(assembly.files, source_snapshot)
    return assembly


def _require_assembly_topology(value: SyntheticLeanProjectAssembly) -> None:
    string_fields = (
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
    integer_fields = (
        "total_source_byte_count",
        "largest_project_file_byte_count",
    )
    boolean_fields = (
        "source_only",
        "adapter_call_contract_present",
        "physical_adapter_present",
        "real_qc_object_store_access_performed",
        "project_created",
        "cloud_compile_performed",
        "backtest_performed",
    )
    if any(type(getattr(value, name)) is not str for name in string_fields):
        raise _PINNED_ERROR_CLASS("source assembly scalar type changed")
    if any(type(getattr(value, name)) is not int for name in integer_fields):
        raise _PINNED_ERROR_CLASS("source assembly census type changed")
    if any(type(getattr(value, name)) is not bool for name in boolean_fields):
        raise _PINNED_ERROR_CLASS("source assembly truth type changed")
    if _PINNED_ANY(
        _PINNED_GETATTR(value, name) is not expected
        for name, expected in _PINNED_ASSEMBLY_TRUTH_FIELD_VALUES
    ):
        raise _PINNED_ERROR_CLASS("source assembly truth value changed")
    if _PINNED_ANY(
        _PINNED_GETATTR(value, name) is not False
        for name in _PINNED_FALSE_PROPERTY_NAMES
    ):
        raise _PINNED_ERROR_CLASS("source assembly gained authority")
    if (
        _PINNED_HEX_64.fullmatch(value.assembly_hash) is None
        or _PINNED_HEX_64.fullmatch(value.assembly_artifact_sha256) is None
        or _PINNED_HEX_64.fullmatch(value.plan_hash) is None
        or _PINNED_HEX_64.fullmatch(value.plan_artifact_sha256) is None
        or _PINNED_HEX_64.fullmatch(value.run_candidate_hash) is None
        or value.total_source_byte_count < 0
        or value.largest_project_file_byte_count < 0
    ):
        raise _PINNED_ERROR_CLASS("source assembly scalar value changed")
    if (
        type(value.files) is not tuple
        or type(value.object_store_calls) is not tuple
        or type(value.external_bindings) is not tuple
        or type(value.capabilities) is not tuple
        or type(value._plan) is not _PINNED_READ_PLAN_CLASS
        or type(value._run_candidate) is not _PINNED_RUN_CANDIDATE_CLASS
        or type(value._canonical_document) is not bytes
    ):
        raise _PINNED_ERROR_CLASS("source assembly topology changed")
    for item in value.files:
        if (
            type(item) is not _PINNED_PROJECT_FILE_CLASS
            or type(item.role) is not str
            or type(item.repository_path) is not str
            or type(item.project_path) is not str
            or type(item.source_bytes) is not bytes
            or type(item.byte_count) is not int
            or type(item.sha256) is not str
            or item.byte_count < 0
            or _PINNED_HEX_64.fullmatch(item.sha256) is None
        ):
            raise _PINNED_ERROR_CLASS("source file topology changed")
    for item in value.object_store_calls:
        if (
            type(item) is not _PINNED_CALL_BINDING_CLASS
            or type(item.ordinal) is not int
            or type(item.operation) is not str
            or type(item.method_name) is not str
            or type(item.object_store_key) is not str
            or not (
                item.expected_found is None
                or type(item.expected_found) is bool
            )
            or not (
                item.expected_byte_count is None
                or type(item.expected_byte_count) is int
            )
            or not (
                item.expected_sha256 is None
                or type(item.expected_sha256) is str
            )
        ):
            raise _PINNED_ERROR_CLASS("Object Store call topology changed")
    if any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or item[1] is not None
        for item in value.external_bindings
    ):
        raise _PINNED_ERROR_CLASS("source assembly binding topology changed")
    if any(
        type(item) is not tuple
        or len(item) != 2
        or type(item[0]) is not str
        or item[1] is not False
        for item in value.capabilities
    ):
        raise _PINNED_ERROR_CLASS("source assembly capability topology changed")


def require_synthetic_qc_lean_source_assembly(
    value: SyntheticLeanProjectAssembly,
) -> SyntheticLeanProjectAssembly:
    """Rebuild an assembly from retained exact values and refuse mutation."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    if type(value) is not _PINNED_ASSEMBLY_CLASS:
        raise _PINNED_ERROR_CLASS("source assembly changed type")
    try:
        _PINNED_REQUIRE_ASSEMBLY_TOPOLOGY(value)
        source_inputs = tuple(
            _PINNED_SOURCE_INPUT_CLASS(
                role=item.role,
                repository_path=item.repository_path,
                project_path=item.project_path,
                source_bytes=item.source_bytes,
            )
            for item in value.files
        )
        rebuilt = _PINNED_BUILD_ASSEMBLY(
            run_candidate=value._run_candidate,
            read_plan=value._plan,
            source_files=source_inputs,
        )
    except _PINNED_ERROR_CLASS:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS("source assembly topology changed") from exc

    if _PINNED_ANY(
        _PINNED_GETATTR(value, name) != _PINNED_GETATTR(rebuilt, name)
        for name in _PINNED_ASSEMBLY_PUBLIC_FIELD_NAMES
    ):
        raise _PINNED_ERROR_CLASS(
            "source assembly changed after construction"
        )
    if value._canonical_document != rebuilt._canonical_document:
        raise _PINNED_ERROR_CLASS("source assembly manifest changed")
    return value


def _make_bootstrap_wrappers(
    *,
    error_class,
    module_globals,
    render_impl,
    build_impl,
    require_impl,
):
    """Bind public entry points to registry roots outside global rebinding."""

    holder: list[object] = []

    def seal(*, static_snapshot_bindings, alias_bindings, static_validator):
        if holder:
            raise error_class("source assembly bootstrap already sealed")
        public_bindings = (
            (
                "render_qc_lean_source_assembly_schema_bytes",
                guarded_render,
            ),
            ("build_synthetic_qc_lean_source_assembly", guarded_build),
            ("require_synthetic_qc_lean_source_assembly", guarded_require),
        )
        holder.append(
            (
                static_snapshot_bindings,
                alias_bindings,
                static_validator,
                public_bindings,
            )
        )

    def check() -> None:
        if not holder:
            raise error_class("source assembly bootstrap is not sealed")
        (
            static_snapshot_bindings,
            alias_bindings,
            static_validator,
            public_bindings,
        ) = holder[0]
        if (
            module_globals.get("_PINNED_STATIC_SNAPSHOT_BINDINGS")
            is not static_snapshot_bindings
            or module_globals.get("_PINNED_ALIAS_BINDINGS")
            is not alias_bindings
            or module_globals.get("_PINNED_REQUIRE_STATIC_CONTRACT")
            is not static_validator
        ):
            raise error_class("source assembly bootstrap registry changed")
        for name, expected in static_snapshot_bindings:
            if module_globals.get(name) is not expected:
                raise error_class("source assembly bootstrap snapshot changed")
        for name, expected in alias_bindings:
            if module_globals.get(name) is not expected:
                raise error_class("source assembly bootstrap alias changed")
        for name, expected in public_bindings:
            if module_globals.get(name) is not expected:
                raise error_class("source assembly public binding changed")
        static_validator()

    def guarded_render() -> bytes:
        check()
        return render_impl()

    def guarded_build(
        *,
        run_candidate: SyntheticQcRunCandidate,
        read_plan: SyntheticQcObjectStoreReadPlan,
        source_files: tuple[LeanSourceInput, ...],
    ) -> SyntheticLeanProjectAssembly:
        check()
        return build_impl(
            run_candidate=run_candidate,
            read_plan=read_plan,
            source_files=source_files,
        )

    def guarded_require(
        value: SyntheticLeanProjectAssembly,
    ) -> SyntheticLeanProjectAssembly:
        check()
        return require_impl(value)

    guarded_render.__name__ = "render_qc_lean_source_assembly_schema_bytes"
    guarded_render.__qualname__ = "render_qc_lean_source_assembly_schema_bytes"
    guarded_render.__doc__ = render_impl.__doc__
    guarded_build.__name__ = "build_synthetic_qc_lean_source_assembly"
    guarded_build.__qualname__ = "build_synthetic_qc_lean_source_assembly"
    guarded_build.__doc__ = build_impl.__doc__
    guarded_require.__name__ = "require_synthetic_qc_lean_source_assembly"
    guarded_require.__qualname__ = "require_synthetic_qc_lean_source_assembly"
    guarded_require.__doc__ = require_impl.__doc__
    return guarded_render, guarded_build, guarded_require, seal


_PINNED_RENDER_SCHEMA_IMPL = render_qc_lean_source_assembly_schema_bytes
_PINNED_BUILD_ASSEMBLY_IMPL = build_synthetic_qc_lean_source_assembly
_PINNED_REQUIRE_ASSEMBLY_IMPL = require_synthetic_qc_lean_source_assembly
(
    render_qc_lean_source_assembly_schema_bytes,
    build_synthetic_qc_lean_source_assembly,
    require_synthetic_qc_lean_source_assembly,
    _BOOTSTRAP_SEAL,
) = _make_bootstrap_wrappers(
    error_class=QcLeanSourceAssemblyError,
    module_globals=_MODULE_GLOBALS,
    render_impl=_PINNED_RENDER_SCHEMA_IMPL,
    build_impl=_PINNED_BUILD_ASSEMBLY_IMPL,
    require_impl=_PINNED_REQUIRE_ASSEMBLY_IMPL,
)


_PINNED_EXPECTED_SOURCE_CLASS = ExpectedLeanSource
_PINNED_SOURCE_INPUT_CLASS = LeanSourceInput
_PINNED_CALL_BINDING_CLASS = LeanObjectStoreCallBinding
_PINNED_PROJECT_FILE_CLASS = SyntheticLeanProjectFile
_PINNED_ASSEMBLY_CLASS = SyntheticLeanProjectAssembly

_PINNED_EXPECTED_SOURCE_FACTORY = _expected_source_files
_PINNED_EXPECTED_SOURCE_SNAPSHOT_FACTORY = _expected_source_snapshot
_PINNED_CANONICAL_BYTES = _canonical_bytes
_PINNED_SOURCE_DESCRIPTOR_DOCUMENT = _source_descriptor_document
_PINNED_SCHEMA_SEED_DOCUMENT = _schema_seed_document
_PINNED_IDENTITY_DOCUMENT = _identity_document
_PINNED_IS_SAFE_PATH = _is_safe_path
_PINNED_REQUIRE_CANONICAL_SOURCE = _require_canonical_python_source
_PINNED_REQUIRE_EXPECTED_SOURCES = _require_expected_sources
_PINNED_REQUIRE_STATIC_CONTRACT = _require_static_contract
_PINNED_RENDER_SCHEMA = render_qc_lean_source_assembly_schema_bytes
_PINNED_CAPTURE_CONTRACT_SNAPSHOT = _capture_contract_snapshot
_PINNED_CAPTURE_PARENT_SNAPSHOT = _capture_parent_snapshot
_PINNED_REQUIRE_SOURCE_SNAPSHOT = _require_source_snapshot
_PINNED_REQUIRE_CONSTRUCTED_FILES = _require_constructed_files
_PINNED_DERIVE_OBJECT_STORE_CALLS = _derive_object_store_calls
_PINNED_ASSEMBLY_SEED_DOCUMENT = _assembly_seed_document
_PINNED_BUILD_ASSEMBLY = build_synthetic_qc_lean_source_assembly
_PINNED_REQUIRE_ASSEMBLY_TOPOLOGY = _require_assembly_topology
_PINNED_REQUIRE_ASSEMBLY = require_synthetic_qc_lean_source_assembly

_PINNED_LOCAL_FUNCTION_STATES = tuple(
    (
        name,
        implementation,
        implementation.__code__,
        implementation.__defaults__,
        implementation.__kwdefaults__,
        implementation.__closure__,
        tuple(
            (cell, type(cell.cell_contents), cell.cell_contents)
            for cell in (implementation.__closure__ or ())
        ),
    )
    for name, implementation in (
        ("_expected_source_files", _PINNED_EXPECTED_SOURCE_FACTORY),
        (
            "_expected_source_snapshot",
            _PINNED_EXPECTED_SOURCE_SNAPSHOT_FACTORY,
        ),
        ("_canonical_bytes", _PINNED_CANONICAL_BYTES),
        ("_source_descriptor_document", _PINNED_SOURCE_DESCRIPTOR_DOCUMENT),
        ("_schema_seed_document", _PINNED_SCHEMA_SEED_DOCUMENT),
        ("_identity_document", _PINNED_IDENTITY_DOCUMENT),
        ("_is_safe_path", _PINNED_IS_SAFE_PATH),
        ("_require_canonical_python_source", _PINNED_REQUIRE_CANONICAL_SOURCE),
        ("_require_expected_sources", _PINNED_REQUIRE_EXPECTED_SOURCES),
        ("_require_static_contract", _PINNED_REQUIRE_STATIC_CONTRACT),
        (
            "render_qc_lean_source_assembly_schema_bytes",
            _PINNED_RENDER_SCHEMA,
        ),
        ("_capture_contract_snapshot", _PINNED_CAPTURE_CONTRACT_SNAPSHOT),
        ("_capture_parent_snapshot", _PINNED_CAPTURE_PARENT_SNAPSHOT),
        ("_require_source_snapshot", _PINNED_REQUIRE_SOURCE_SNAPSHOT),
        (
            "_require_constructed_files",
            _PINNED_REQUIRE_CONSTRUCTED_FILES,
        ),
        ("_derive_object_store_calls", _PINNED_DERIVE_OBJECT_STORE_CALLS),
        ("_assembly_seed_document", _PINNED_ASSEMBLY_SEED_DOCUMENT),
        ("build_synthetic_qc_lean_source_assembly", _PINNED_BUILD_ASSEMBLY),
        ("_require_assembly_topology", _PINNED_REQUIRE_ASSEMBLY_TOPOLOGY),
        (
            "require_synthetic_qc_lean_source_assembly",
            _PINNED_REQUIRE_ASSEMBLY,
        ),
        ("_make_bootstrap_wrappers", _make_bootstrap_wrappers),
        ("_PINNED_RENDER_SCHEMA_IMPL", _PINNED_RENDER_SCHEMA_IMPL),
        ("_PINNED_BUILD_ASSEMBLY_IMPL", _PINNED_BUILD_ASSEMBLY_IMPL),
        ("_PINNED_REQUIRE_ASSEMBLY_IMPL", _PINNED_REQUIRE_ASSEMBLY_IMPL),
    )
)
_PINNED_CLASS_BINDINGS = (
    ("QcLeanSourceAssemblyError", QcLeanSourceAssemblyError),
    ("ExpectedLeanSource", _PINNED_EXPECTED_SOURCE_CLASS),
    ("LeanSourceInput", _PINNED_SOURCE_INPUT_CLASS),
    ("LeanObjectStoreCallBinding", _PINNED_CALL_BINDING_CLASS),
    ("SyntheticLeanProjectFile", _PINNED_PROJECT_FILE_CLASS),
    ("SyntheticLeanProjectAssembly", _PINNED_ASSEMBLY_CLASS),
)
_PINNED_CLASS_STATES = tuple(
    (
        accepted_class,
        type(accepted_class),
        tuple(accepted_class.__bases__),
        tuple(accepted_class.__mro__),
        tuple(vars(accepted_class).items()),
    )
    for _, accepted_class in _PINNED_CLASS_BINDINGS
)
_PINNED_CLASS_FUNCTION_STATES = tuple(
    (
        implementation,
        implementation.__code__,
        implementation.__defaults__,
        implementation.__kwdefaults__,
        implementation.__closure__,
        tuple(
            (cell, type(cell.cell_contents), cell.cell_contents)
            for cell in (implementation.__closure__ or ())
        ),
    )
    for _, accepted_class in _PINNED_CLASS_BINDINGS
    for member in vars(accepted_class).values()
    for implementation in (
        (member.fget,)
        if type(member) is property and member.fget is not None
        else (member,)
    )
    if type(implementation) is _PINNED_FUNCTION_TYPE
)
_PINNED_PARENT_FUNCTION_STATES = tuple(
    (
        implementation,
        implementation.__code__,
        implementation.__defaults__,
        implementation.__kwdefaults__,
        implementation.__closure__,
        tuple(
            (cell, type(cell.cell_contents), cell.cell_contents)
            for cell in (implementation.__closure__ or ())
        ),
    )
    for implementation in (
        _PINNED_RENDER_B4_SCHEMA,
        _PINNED_BUILD_RUN_CANDIDATE,
        _PINNED_BUILD_READ_PLAN,
        _PINNED_REQUIRE_READ_PLAN,
        _PINNED_REQUIRE_RUN_CANDIDATE,
    )
)
_PINNED_ALIAS_BINDINGS = (
    ("_PINNED_AST_MODULE", _PINNED_AST_MODULE),
    ("_PINNED_AST_PARSE", _PINNED_AST_PARSE),
    ("_PINNED_DATACLASSES_MODULE", _PINNED_DATACLASSES_MODULE),
    ("_PINNED_DATACLASSES_FIELDS", _PINNED_DATACLASSES_FIELDS),
    ("_PINNED_HASHLIB_MODULE", _PINNED_HASHLIB_MODULE),
    ("_PINNED_SHA256", _PINNED_SHA256),
    ("_PINNED_JSON_MODULE", _PINNED_JSON_MODULE),
    ("_PINNED_JSON_DUMPS", _PINNED_JSON_DUMPS),
    ("_PINNED_RE_MODULE", _PINNED_RE_MODULE),
    ("_PINNED_RE_COMPILE", _PINNED_RE_COMPILE),
    ("_PINNED_MODULE_BINDINGS", _PINNED_MODULE_BINDINGS),
    ("_PINNED_DEPENDENCY_CALLABLES", _PINNED_DEPENDENCY_CALLABLES),
    ("_PINNED_ALL", _PINNED_ALL),
    ("_PINNED_ANY", _PINNED_ANY),
    ("_PINNED_ATTRIBUTE_ERROR", _PINNED_ATTRIBUTE_ERROR),
    ("_PINNED_BOOL", _PINNED_BOOL),
    ("_PINNED_BYTES", _PINNED_BYTES),
    ("_PINNED_DICT", _PINNED_DICT),
    ("_PINNED_GETATTR", _PINNED_GETATTR),
    ("_PINNED_HASH", _PINNED_HASH),
    ("_PINNED_ID", _PINNED_ID),
    ("_PINNED_INT", _PINNED_INT),
    ("_PINNED_LEN", _PINNED_LEN),
    ("_PINNED_LIST", _PINNED_LIST),
    ("_PINNED_MAX", _PINNED_MAX),
    ("_PINNED_NOT_IMPLEMENTED", _PINNED_NOT_IMPLEMENTED),
    ("_PINNED_OBJECT", _PINNED_OBJECT),
    ("_PINNED_PROPERTY", _PINNED_PROPERTY),
    ("_PINNED_RANGE", _PINNED_RANGE),
    ("_PINNED_RECURSION_ERROR", _PINNED_RECURSION_ERROR),
    ("_PINNED_SET", _PINNED_SET),
    ("_PINNED_STR", _PINNED_STR),
    ("_PINNED_SUM", _PINNED_SUM),
    ("_PINNED_SUPER", _PINNED_SUPER),
    ("_PINNED_SYNTAX_ERROR", _PINNED_SYNTAX_ERROR),
    ("_PINNED_TUPLE", _PINNED_TUPLE),
    ("_PINNED_TYPE", _PINNED_TYPE),
    ("_PINNED_TYPE_ERROR", _PINNED_TYPE_ERROR),
    ("_PINNED_UNICODE_DECODE_ERROR", _PINNED_UNICODE_DECODE_ERROR),
    ("_PINNED_UNICODE_ERROR", _PINNED_UNICODE_ERROR),
    ("_PINNED_VALUE_ERROR", _PINNED_VALUE_ERROR),
    ("_PINNED_VARS", _PINNED_VARS),
    ("_PINNED_ZIP", _PINNED_ZIP),
    ("_PINNED_FUNCTION_TYPE", _PINNED_FUNCTION_TYPE),
    ("_PINNED_CODE_TYPE", _PINNED_CODE_TYPE),
    ("_PINNED_BUILTINS_DICT", _PINNED_BUILTINS_DICT),
    ("_PINNED_BUILTIN_BINDINGS", _PINNED_BUILTIN_BINDINGS),
    ("_PINNED_REQUIRE_READ_PLAN", _PINNED_REQUIRE_READ_PLAN),
    ("_PINNED_REQUIRE_RUN_CANDIDATE", _PINNED_REQUIRE_RUN_CANDIDATE),
    ("_PINNED_BUILD_RUN_CANDIDATE", _PINNED_BUILD_RUN_CANDIDATE),
    ("_PINNED_RENDER_B4_SCHEMA", _PINNED_RENDER_B4_SCHEMA),
    ("_PINNED_B4_ERROR_CLASS", _PINNED_B4_ERROR_CLASS),
    (
        "_PINNED_RUN_CANDIDATE_ERROR_CLASS",
        _PINNED_RUN_CANDIDATE_ERROR_CLASS,
    ),
    ("_PINNED_BUILD_READ_PLAN", _PINNED_BUILD_READ_PLAN),
    ("_PINNED_READ_PLAN_CLASS", _PINNED_READ_PLAN_CLASS),
    ("_PINNED_RUN_CANDIDATE_CLASS", _PINNED_RUN_CANDIDATE_CLASS),
    ("_PINNED_GLOBALS", _PINNED_GLOBALS),
    ("_MODULE_GLOBALS", _MODULE_GLOBALS),
    ("_PINNED_IMPORTED_BINDINGS", _PINNED_IMPORTED_BINDINGS),
    ("_PINNED_ERROR_CLASS", _PINNED_ERROR_CLASS),
    ("_PINNED_HEX_64", _PINNED_HEX_64),
    ("_PINNED_SAFE_PROJECT_PATH", _PINNED_SAFE_PROJECT_PATH),
    ("_PINNED_EXPECTED_SOURCE_FILES", _PINNED_EXPECTED_SOURCE_FILES),
    ("_PINNED_EXTERNAL_BINDINGS", _PINNED_EXTERNAL_BINDINGS),
    ("_PINNED_CAPABILITIES", _PINNED_CAPABILITIES),
    ("_PINNED_FORMAL_PRIMARY_FOLD_IDS", _PINNED_FORMAL_PRIMARY_FOLD_IDS),
    (
        "_PINNED_DESCRIPTIVE_SENSITIVITY_FOLD_IDS",
        _PINNED_DESCRIPTIVE_SENSITIVITY_FOLD_IDS,
    ),
    (
        "_PINNED_ASSEMBLY_PUBLIC_FIELD_NAMES",
        _PINNED_ASSEMBLY_PUBLIC_FIELD_NAMES,
    ),
    (
        "_PINNED_ASSEMBLY_TRUTH_FIELD_VALUES",
        _PINNED_ASSEMBLY_TRUTH_FIELD_VALUES,
    ),
    ("_PINNED_FALSE_PROPERTY_NAMES", _PINNED_FALSE_PROPERTY_NAMES),
    (
        "_PINNED_SCHEMA_IDENTITY_DOCUMENT",
        _PINNED_SCHEMA_IDENTITY_DOCUMENT,
    ),
    ("_PINNED_SCHEMA_DOCUMENT_BYTES", _PINNED_SCHEMA_DOCUMENT_BYTES),
    ("_PINNED_EXPECTED_SOURCE_CLASS", _PINNED_EXPECTED_SOURCE_CLASS),
    ("_PINNED_SOURCE_INPUT_CLASS", _PINNED_SOURCE_INPUT_CLASS),
    ("_PINNED_CALL_BINDING_CLASS", _PINNED_CALL_BINDING_CLASS),
    ("_PINNED_PROJECT_FILE_CLASS", _PINNED_PROJECT_FILE_CLASS),
    ("_PINNED_ASSEMBLY_CLASS", _PINNED_ASSEMBLY_CLASS),
    ("_PINNED_EXPECTED_SOURCE_FACTORY", _PINNED_EXPECTED_SOURCE_FACTORY),
    (
        "_PINNED_EXPECTED_SOURCE_SNAPSHOT_FACTORY",
        _PINNED_EXPECTED_SOURCE_SNAPSHOT_FACTORY,
    ),
    ("_PINNED_CANONICAL_BYTES", _PINNED_CANONICAL_BYTES),
    ("_PINNED_SOURCE_DESCRIPTOR_DOCUMENT", _PINNED_SOURCE_DESCRIPTOR_DOCUMENT),
    ("_PINNED_SCHEMA_SEED_DOCUMENT", _PINNED_SCHEMA_SEED_DOCUMENT),
    ("_PINNED_IDENTITY_DOCUMENT", _PINNED_IDENTITY_DOCUMENT),
    ("_PINNED_IS_SAFE_PATH", _PINNED_IS_SAFE_PATH),
    ("_PINNED_REQUIRE_CANONICAL_SOURCE", _PINNED_REQUIRE_CANONICAL_SOURCE),
    ("_PINNED_REQUIRE_EXPECTED_SOURCES", _PINNED_REQUIRE_EXPECTED_SOURCES),
    ("_PINNED_REQUIRE_STATIC_CONTRACT", _PINNED_REQUIRE_STATIC_CONTRACT),
    ("_PINNED_RENDER_SCHEMA", _PINNED_RENDER_SCHEMA),
    (
        "_PINNED_CAPTURE_CONTRACT_SNAPSHOT",
        _PINNED_CAPTURE_CONTRACT_SNAPSHOT,
    ),
    ("_PINNED_CAPTURE_PARENT_SNAPSHOT", _PINNED_CAPTURE_PARENT_SNAPSHOT),
    ("_PINNED_REQUIRE_SOURCE_SNAPSHOT", _PINNED_REQUIRE_SOURCE_SNAPSHOT),
    (
        "_PINNED_REQUIRE_CONSTRUCTED_FILES",
        _PINNED_REQUIRE_CONSTRUCTED_FILES,
    ),
    ("_PINNED_DERIVE_OBJECT_STORE_CALLS", _PINNED_DERIVE_OBJECT_STORE_CALLS),
    ("_PINNED_ASSEMBLY_SEED_DOCUMENT", _PINNED_ASSEMBLY_SEED_DOCUMENT),
    ("_PINNED_BUILD_ASSEMBLY", _PINNED_BUILD_ASSEMBLY),
    ("_PINNED_REQUIRE_ASSEMBLY_TOPOLOGY", _PINNED_REQUIRE_ASSEMBLY_TOPOLOGY),
    ("_PINNED_REQUIRE_ASSEMBLY", _PINNED_REQUIRE_ASSEMBLY),
    ("_PINNED_RENDER_SCHEMA_IMPL", _PINNED_RENDER_SCHEMA_IMPL),
    ("_PINNED_BUILD_ASSEMBLY_IMPL", _PINNED_BUILD_ASSEMBLY_IMPL),
    ("_PINNED_REQUIRE_ASSEMBLY_IMPL", _PINNED_REQUIRE_ASSEMBLY_IMPL),
    ("_PINNED_CLASS_BINDINGS", _PINNED_CLASS_BINDINGS),
    ("_PINNED_CLASS_STATES", _PINNED_CLASS_STATES),
    ("_PINNED_CLASS_FUNCTION_STATES", _PINNED_CLASS_FUNCTION_STATES),
)
_PINNED_STATIC_SNAPSHOT_BINDINGS = (
    ("_PINNED_MODULE_BINDINGS", _PINNED_MODULE_BINDINGS),
    ("_PINNED_DEPENDENCY_CALLABLES", _PINNED_DEPENDENCY_CALLABLES),
    ("_PINNED_IMPORTED_BINDINGS", _PINNED_IMPORTED_BINDINGS),
    ("_PINNED_BUILTIN_BINDINGS", _PINNED_BUILTIN_BINDINGS),
    ("_PINNED_LOCAL_FUNCTION_STATES", _PINNED_LOCAL_FUNCTION_STATES),
    ("_PINNED_PARENT_FUNCTION_STATES", _PINNED_PARENT_FUNCTION_STATES),
    ("_PINNED_CLASS_BINDINGS", _PINNED_CLASS_BINDINGS),
    ("_PINNED_CLASS_STATES", _PINNED_CLASS_STATES),
    ("_PINNED_CLASS_FUNCTION_STATES", _PINNED_CLASS_FUNCTION_STATES),
    ("_PINNED_ALIAS_BINDINGS", _PINNED_ALIAS_BINDINGS),
)
_BOOTSTRAP_SEAL(
    static_snapshot_bindings=_PINNED_STATIC_SNAPSHOT_BINDINGS,
    alias_bindings=_PINNED_ALIAS_BINDINGS,
    static_validator=_PINNED_REQUIRE_STATIC_CONTRACT,
)
del _BOOTSTRAP_SEAL
