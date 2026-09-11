"""Pure ARV2-4F-B5C one-file QuantConnect refusal-smoke projection.

The accepted B5B assembly is larger than QuantConnect's empirically observed
64,000-character per-file ceiling.  This child contract authenticates that
complete offline parent, selects its exact direct-source ``main.py`` entry,
and emits one immutable source-file value for a later refusal-only cloud
smoke.

This module accepts no path opener, client, callback, credential, account,
project, Object Store, provider, result, or QuantConnect object.  It performs
no I/O, upload, cloud compile, launch, result access, or evaluation.  A later
physical runner must separately reconcile the cloud project and authenticate
the exact source readback before it can use the owner's bounded authority.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json

from .lean_source_assembly import (
    CAPABILITIES as B5B_CAPABILITIES,
    DESCRIPTIVE_SENSITIVITY_FOLD_IDS as B5B_DESCRIPTIVE_FOLD_IDS,
    ENTRY_CLASS_NAME as B5B_ENTRY_CLASS_NAME,
    ENTRY_PROJECT_PATH as B5B_ENTRY_PROJECT_PATH,
    EXTERNAL_BINDINGS as B5B_EXTERNAL_BINDINGS,
    FORMAL_PRIMARY_FOLD_IDS as B5B_FORMAL_FOLD_IDS,
    SCHEMA_ARTIFACT_SHA256 as B5B_SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID as B5B_SCHEMA_ID,
    SCHEMA_SHA256 as B5B_SCHEMA_SHA256,
    SCAFFOLD_SOURCE_BYTE_COUNT as B5B_ENTRY_SOURCE_BYTE_COUNT,
    SCAFFOLD_SOURCE_SHA256 as B5B_ENTRY_SOURCE_SHA256,
    QcLeanSourceAssemblyError,
    SyntheticLeanProjectAssembly,
    SyntheticLeanProjectFile,
    require_synthetic_qc_lean_source_assembly,
    render_qc_lean_source_assembly_schema_bytes,
)


_PINNED_AST_MODULE = ast
_PINNED_AST_PARSE = ast.parse
_PINNED_AST_LITERAL_EVAL = ast.literal_eval
_PINNED_AST_WALK = ast.walk
_PINNED_DATACLASSES_MODULE = dataclasses
_PINNED_DATACLASSES_FIELD = dataclasses.field
_PINNED_HASHLIB_MODULE = hashlib
_PINNED_SHA256 = hashlib.sha256
_PINNED_JSON_MODULE = json
_PINNED_JSON_DUMPS = json.dumps
_PINNED_MODULE_BINDINGS = (
    ("ast", _PINNED_AST_MODULE),
    ("dataclasses", _PINNED_DATACLASSES_MODULE),
    ("hashlib", _PINNED_HASHLIB_MODULE),
    ("json", _PINNED_JSON_MODULE),
)
_PINNED_DEPENDENCY_BINDINGS = (
    (_PINNED_AST_MODULE, "parse", _PINNED_AST_PARSE),
    (_PINNED_AST_MODULE, "literal_eval", _PINNED_AST_LITERAL_EVAL),
    (_PINNED_AST_MODULE, "walk", _PINNED_AST_WALK),
    (_PINNED_AST_MODULE, "Assign", ast.Assign),
    (_PINNED_AST_MODULE, "AsyncFunctionDef", ast.AsyncFunctionDef),
    (_PINNED_AST_MODULE, "Attribute", ast.Attribute),
    (_PINNED_AST_MODULE, "Call", ast.Call),
    (_PINNED_AST_MODULE, "ClassDef", ast.ClassDef),
    (_PINNED_AST_MODULE, "Constant", ast.Constant),
    (_PINNED_AST_MODULE, "Expr", ast.Expr),
    (_PINNED_AST_MODULE, "FunctionDef", ast.FunctionDef),
    (_PINNED_AST_MODULE, "Import", ast.Import),
    (_PINNED_AST_MODULE, "ImportFrom", ast.ImportFrom),
    (_PINNED_AST_MODULE, "Name", ast.Name),
    (_PINNED_AST_MODULE, "Raise", ast.Raise),
    (_PINNED_AST_MODULE, "Return", ast.Return),
    (_PINNED_DATACLASSES_MODULE, "field", _PINNED_DATACLASSES_FIELD),
    (_PINNED_HASHLIB_MODULE, "sha256", _PINNED_SHA256),
    (_PINNED_JSON_MODULE, "dumps", _PINNED_JSON_DUMPS),
)
_PINNED_ALL = all
_PINNED_ANY = any
_PINNED_BOOL = bool
_PINNED_BYTES = bytes
_PINNED_DICT = dict
_PINNED_GETATTR = getattr
_PINNED_GLOBALS = globals
_PINNED_INT = int
_PINNED_LEN = len
_PINNED_LIST = list
_PINNED_MEMORY_ERROR = MemoryError
_PINNED_PROPERTY = property
_PINNED_RANGE = range
_PINNED_RECURSION_ERROR = RecursionError
_PINNED_STR = str
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
_PINNED_BUILTINS_DICT = __builtins__
_PINNED_BUILTIN_BINDINGS = (
    ("all", _PINNED_ALL),
    ("any", _PINNED_ANY),
    ("bool", _PINNED_BOOL),
    ("bytes", _PINNED_BYTES),
    ("dict", _PINNED_DICT),
    ("getattr", _PINNED_GETATTR),
    ("globals", _PINNED_GLOBALS),
    ("int", _PINNED_INT),
    ("len", _PINNED_LEN),
    ("list", _PINNED_LIST),
    ("MemoryError", _PINNED_MEMORY_ERROR),
    ("property", _PINNED_PROPERTY),
    ("range", _PINNED_RANGE),
    ("RecursionError", _PINNED_RECURSION_ERROR),
    ("str", _PINNED_STR),
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
_PINNED_REQUIRE_PARENT = require_synthetic_qc_lean_source_assembly
_PINNED_RENDER_PARENT_SCHEMA = render_qc_lean_source_assembly_schema_bytes
_PINNED_PARENT_ERROR_CLASS = QcLeanSourceAssemblyError
_PINNED_PARENT_ASSEMBLY_CLASS = SyntheticLeanProjectAssembly
_PINNED_PARENT_FILE_CLASS = SyntheticLeanProjectFile
_MODULE_GLOBALS = _PINNED_GLOBALS()
_PINNED_IMPORTED_BINDINGS = (
    ("B5B_CAPABILITIES", B5B_CAPABILITIES),
    ("B5B_DESCRIPTIVE_FOLD_IDS", B5B_DESCRIPTIVE_FOLD_IDS),
    ("B5B_ENTRY_CLASS_NAME", B5B_ENTRY_CLASS_NAME),
    ("B5B_ENTRY_PROJECT_PATH", B5B_ENTRY_PROJECT_PATH),
    ("B5B_EXTERNAL_BINDINGS", B5B_EXTERNAL_BINDINGS),
    ("B5B_FORMAL_FOLD_IDS", B5B_FORMAL_FOLD_IDS),
    ("B5B_SCHEMA_ARTIFACT_SHA256", B5B_SCHEMA_ARTIFACT_SHA256),
    ("B5B_SCHEMA_ID", B5B_SCHEMA_ID),
    ("B5B_SCHEMA_SHA256", B5B_SCHEMA_SHA256),
    ("B5B_ENTRY_SOURCE_BYTE_COUNT", B5B_ENTRY_SOURCE_BYTE_COUNT),
    ("B5B_ENTRY_SOURCE_SHA256", B5B_ENTRY_SOURCE_SHA256),
    ("QcLeanSourceAssemblyError", QcLeanSourceAssemblyError),
    ("SyntheticLeanProjectAssembly", SyntheticLeanProjectAssembly),
    ("SyntheticLeanProjectFile", SyntheticLeanProjectFile),
    (
        "require_synthetic_qc_lean_source_assembly",
        require_synthetic_qc_lean_source_assembly,
    ),
    (
        "render_qc_lean_source_assembly_schema_bytes",
        render_qc_lean_source_assembly_schema_bytes,
    ),
)


class QcRefusalSmokeProjectionError(ValueError):
    """The B5C parent, source, schema, or projection is not authentic."""


_PINNED_ERROR_CLASS = QcRefusalSmokeProjectionError


SCHEMA = "arv2-qc-refusal-smoke-projection-schema-v1"
STATUS = "offline_one_file_refusal_smoke_projected_cloud_execution_unperformed"
AUTHORITY = (
    "offline_values_only_no_client_callback_filesystem_environment_provider_"
    "credential_account_project_object_store_upload_compile_launch_result_"
    "evaluation_deployment_order_or_trading_authority"
)
HASH_DOMAIN = "arv2-qc-refusal-smoke-projection-v1"
MAX_QC_SOURCE_CHARACTERS = 64_000
EXPECTED_PROJECT_FILE_COUNT = 1
ENTRY_PROJECT_PATH = "main.py"
ENTRY_CLASS_NAME = "AnalystRevisionsV2StockEventStudyScaffold"
SCAFFOLD_ONLY_MARKER = (
    "ARV2-4F-B5B SOURCE_ASSEMBLY_ONLY: QC execution is not authorized"
)
QUOTA_OBSERVATION_ID = "arv2-qc-file-character-limit-observation-20260911"
QUOTA_RECEIPT_SHA256 = (
    "f2c3fd7536100bb4a1e1e9a8f5e4b349ff73196d286de7916c8bed5d9930a7ae"
)
QUOTA_OBSERVATION = (
    "QuantConnect files/create reported a maximum of 64,000 characters; "
    "B5C applies the stricter decoded-source count including the final LF"
)

FORMAL_PRIMARY_FOLD_IDS = B5B_FORMAL_FOLD_IDS
DESCRIPTIVE_SENSITIVITY_FOLD_IDS = B5B_DESCRIPTIVE_FOLD_IDS
OVER_LIMIT_B5B_SOURCE_FILES = (
    (
        "event_study_core",
        "research/analyst_revisions_v2_qc/event_study.py",
        109_226,
    ),
    (
        "global_input_bundle",
        "research/analyst_revisions_v2_qc/global_input_bundle.py",
        140_983,
    ),
    (
        "global_input_schema",
        "research/analyst_revisions_v2_qc/global_input_schema.py",
        94_959,
    ),
    (
        "synthetic_input_transport",
        "research/analyst_revisions_v2_qc/synthetic_input_transport.py",
        65_144,
    ),
)
EXTERNAL_BINDINGS = (
    *B5B_EXTERNAL_BINDINGS,
    ("refusal_smoke_review_commit", None),
    ("refusal_smoke_counter_review_commit", None),
    ("authenticated_cloud_project_inventory_receipt_id", None),
    ("authenticated_cloud_compile_receipt_id", None),
    ("authenticated_cloud_refusal_receipt_id", None),
)
CAPABILITIES = B5B_CAPABILITIES
_EXPECTED_PARENT_ASSEMBLY_ID = (
    "arv2-qc-lean-source-assembly-8303f3323ff16ab7"
)
_EXPECTED_PARENT_ASSEMBLY_SHA256 = (
    "8303f3323ff16ab7da6c03c587bfbbf4a8d8ecb356eb8912307c2c78a75c1266"
)
_EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256 = (
    "56d3f77e731f6a13b5dbfb9bcbfcd8e89261a226400b744cf2c0fa3d3b400bdd"
)
_EXPECTED_PARENT_ASSEMBLY_IDENTITY = (
    _EXPECTED_PARENT_ASSEMBLY_ID,
    _EXPECTED_PARENT_ASSEMBLY_SHA256,
    _EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256,
)

__all__ = (
    "AUTHORITY",
    "CAPABILITIES",
    "DESCRIPTIVE_SENSITIVITY_FOLD_IDS",
    "ENTRY_CLASS_NAME",
    "ENTRY_PROJECT_PATH",
    "EXPECTED_PROJECT_FILE_COUNT",
    "EXTERNAL_BINDINGS",
    "FORMAL_PRIMARY_FOLD_IDS",
    "HASH_DOMAIN",
    "MAX_QC_SOURCE_CHARACTERS",
    "OVER_LIMIT_B5B_SOURCE_FILES",
    "QUOTA_OBSERVATION",
    "QUOTA_OBSERVATION_ID",
    "QUOTA_RECEIPT_SHA256",
    "QcRefusalSmokeProjectFile",
    "QcRefusalSmokeProjectionError",
    "SCAFFOLD_ONLY_MARKER",
    "SCHEMA",
    "SCHEMA_ARTIFACT_SHA256",
    "SCHEMA_ID",
    "SCHEMA_SHA256",
    "STATUS",
    "SyntheticQcRefusalSmokeProjection",
    "build_synthetic_qc_refusal_smoke_projection",
    "render_qc_refusal_smoke_projection_schema_bytes",
    "require_synthetic_qc_refusal_smoke_projection",
)

_EXPECTED_SCAFFOLD_CAPABILITY_FLAGS = (
    ("credential_access", False),
    ("qc_account_access", False),
    ("project_creation", False),
    ("project_configuration", False),
    ("object_store_read", False),
    ("object_store_write", False),
    ("provider_access", False),
    ("production_input_read", False),
    ("outcome_access", False),
    ("upload", False),
    ("cloud_compile", False),
    ("backtest_launch", False),
    ("result_access", False),
    ("result_disposition", False),
    ("deployment", False),
    ("orders", False),
    ("trading", False),
)
_EXPECTED_ENTRY_ASSIGNMENTS = (
    ("SCAFFOLD_SCHEMA", "arv2-qc-lean-entry-scaffold-v2"),
    ("SOURCE_ASSEMBLY_SCHEMA", "arv2-qc-lean-source-assembly-schema-v1"),
    ("STATUS", "offline_source_inventory_authenticated_runtime_refuses"),
    (
        "AUTHORITY",
        "source_structure_only_no_credential_account_project_configuration_"
        "object_store_provider_input_outcome_upload_compile_launch_result_"
        "deployment_order_or_trading_authority",
    ),
    ("QC_CLOUD_ENTRY_NAME", ENTRY_PROJECT_PATH),
    ("SCAFFOLD_ONLY_MARKER", SCAFFOLD_ONLY_MARKER),
    ("PHYSICAL_ADAPTER_PRESENT", False),
    ("REAL_QC_OBJECT_STORE_ACCESS_PERFORMED", False),
    ("CLOUD_COMPILE_PERFORMED", False),
    ("BACKTEST_PERFORMED", False),
    ("EVALUATION_ID", "arv2-eval-stock-historical-qc-001"),
    ("ALGORITHM_ID", "arv2-qc-stock-event-study-core-v2"),
    ("RUN_CONTRACT_SCHEMA", "arv2-qc-stock-event-study-run-candidate-v2"),
    (
        "RUN_CONTRACT_SOURCE_SHA256",
        "a72aa500a5c2d2fe68cfe9a00e6531a8c1a241e212cb8df8e2a7a56dba3d77d5",
    ),
    ("B4_SCHEMA_ID", "arv2-qc-object-store-read-contract-5dcb6cffb8f9688b"),
    (
        "B4_SCHEMA_SHA256",
        "5dcb6cffb8f9688b1a63a0ea452fd7f4c3e706df7941691ede58c95e0f055dd2",
    ),
    (
        "B4_SCHEMA_ARTIFACT_SHA256",
        "95c3242405dddaaec40af01113a6823235fa74fcf405ab7b30ab5c6a45a8e987",
    ),
    (
        "B4_SOURCE_SHA256",
        "bf370a894986cec8ac341ef8f43bce91aeab4568295ab94c281ce5defaa4d2e3",
    ),
    ("B4_SOURCE_CANONICAL_LF_BYTE_COUNT", 57_361),
    ("FORMAL_PRIMARY_FOLD_IDS", FORMAL_PRIMARY_FOLD_IDS),
    ("DESCRIPTIVE_SENSITIVITY_FOLD_IDS", DESCRIPTIVE_SENSITIVITY_FOLD_IDS),
    ("CAPABILITY_FLAGS", _EXPECTED_SCAFFOLD_CAPABILITY_FLAGS),
)

_PINNED_FORMAL_PRIMARY_FOLD_IDS = FORMAL_PRIMARY_FOLD_IDS
_PINNED_DESCRIPTIVE_SENSITIVITY_FOLD_IDS = DESCRIPTIVE_SENSITIVITY_FOLD_IDS
_PINNED_OVER_LIMIT_B5B_SOURCE_FILES = OVER_LIMIT_B5B_SOURCE_FILES
_PINNED_EXTERNAL_BINDINGS = EXTERNAL_BINDINGS
_PINNED_CAPABILITIES = CAPABILITIES
_PINNED_EXPECTED_SCAFFOLD_CAPABILITY_FLAGS = _EXPECTED_SCAFFOLD_CAPABILITY_FLAGS
_PINNED_EXPECTED_ENTRY_ASSIGNMENTS = _EXPECTED_ENTRY_ASSIGNMENTS


@dataclasses.dataclass(frozen=True, slots=True)
class QcRefusalSmokeProjectFile:
    """The one exact source file projected for the refusal-only smoke."""

    role: str
    repository_path: str
    project_path: str
    source_bytes: bytes = dataclasses.field(repr=False)
    byte_count: int
    character_count: int
    sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticQcRefusalSmokeProjection:
    """Immutable offline projection; none of its fields grants an action."""

    projection_id: str
    projection_hash: str
    projection_artifact_sha256: str
    parent_assembly_id: str
    parent_assembly_hash: str
    parent_assembly_artifact_sha256: str
    entry_project_path: str
    entry_class_name: str
    files: tuple[QcRefusalSmokeProjectFile, ...]
    total_source_byte_count: int
    total_source_character_count: int
    largest_project_file_character_count: int
    source_only: bool
    immediate_refusal: bool
    strategy_execution_capable: bool
    evaluation_window_applied: bool
    physical_adapter_present: bool
    project_created: bool
    cloud_compile_performed: bool
    backtest_performed: bool
    result_access_performed: bool
    external_bindings: tuple[tuple[str, None], ...]
    capabilities: tuple[tuple[str, bool], ...]
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
    def production_input_read_available(self) -> bool:
        return False

    @property
    def production_manifest_available(self) -> bool:
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
            "refusal-smoke projection is not canonical JSON"
        ) from exc


def _schema_seed_document() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "schema_id": None,
        "schema_sha256": None,
        "parent": {
            "b5b_schema_id": B5B_SCHEMA_ID,
            "b5b_schema_sha256": B5B_SCHEMA_SHA256,
            "b5b_schema_artifact_sha256": B5B_SCHEMA_ARTIFACT_SHA256,
            "b5b_assembly_id": _EXPECTED_PARENT_ASSEMBLY_ID,
            "b5b_assembly_sha256": _EXPECTED_PARENT_ASSEMBLY_SHA256,
            "b5b_assembly_artifact_sha256": (
                _EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256
            ),
        },
        "entry": {
            "project_path": ENTRY_PROJECT_PATH,
            "class_name": ENTRY_CLASS_NAME,
            "initialize_refuses_before_service_access": True,
        },
        "source_projection": {
            "file_count": EXPECTED_PROJECT_FILE_COUNT,
            "maximum_file_characters": MAX_QC_SOURCE_CHARACTERS,
            "character_count_includes_terminal_lf": True,
            "utf8_byte_count_is_not_the_character_count": True,
            "complete_b5b_inventory_projected": False,
            "runtime_dependency_closure_claimed": False,
        },
        "quota_observation": {
            "observation_id": QUOTA_OBSERVATION_ID,
            "receipt_sha256": QUOTA_RECEIPT_SHA256,
            "description": QUOTA_OBSERVATION,
            "conservative_local_count_includes_final_lf": True,
        },
        "over_limit_b5b_source_files": [
            {
                "role": role,
                "project_path": path,
                "character_count": character_count,
            }
            for role, path, character_count in OVER_LIMIT_B5B_SOURCE_FILES
        ],
        "evaluation_windows": {
            "formal_primary_fold_ids": list(FORMAL_PRIMARY_FOLD_IDS),
            "descriptive_sensitivity_fold_ids": list(
                DESCRIPTIVE_SENSITIVITY_FOLD_IDS
            ),
            "active_in_this_projection": False,
            "strategy_evaluation_performed": False,
        },
        "truth": {
            "source_only": True,
            "immediate_refusal": True,
            "strategy_execution_capable": False,
            "evaluation_window_applied": False,
            "runtime_code_authenticated": False,
            "physical_adapter_present": False,
            "project_created": False,
            "cloud_compile_performed": False,
            "backtest_performed": False,
            "result_access_performed": False,
        },
        "residuals": {
            "full_b5b_source_set_fits_qc_file_limit": False,
            "full_runtime_dependency_closure_authenticated": False,
            "cloud_residual_file_reconciled": False,
            "production_input_package_built": False,
            "strategy_backtest_ready": False,
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
) -> tuple[dict[str, object], str]:
    seed = dict(document)
    seed[id_key] = None
    seed[hash_key] = None
    digest = _PINNED_SHA256(
        HASH_DOMAIN.encode("ascii") + b"\x00" + _canonical_bytes(seed)
    ).hexdigest()
    final = dict(seed)
    final[hash_key] = digest
    final[id_key] = f"{prefix}-{digest[:16]}"
    return final, digest


_SCHEMA_IDENTITY_DOCUMENT, SCHEMA_SHA256 = _identity_document(
    _schema_seed_document(),
    id_key="schema_id",
    hash_key="schema_sha256",
    prefix="arv2-qc-refusal-smoke-projection",
)
SCHEMA_ID = str(_SCHEMA_IDENTITY_DOCUMENT["schema_id"])
_SCHEMA_DOCUMENT_BYTES = _canonical_bytes(_SCHEMA_IDENTITY_DOCUMENT)
SCHEMA_ARTIFACT_SHA256 = _PINNED_SHA256(_SCHEMA_DOCUMENT_BYTES).hexdigest()
_PINNED_SCHEMA_DOCUMENT_BYTES = _SCHEMA_DOCUMENT_BYTES
del _SCHEMA_IDENTITY_DOCUMENT


def _require_qc_source_character_count(source_bytes: bytes) -> int:
    """Return a conservative decoded count or refuse a QC-incompatible file."""

    if type(source_bytes) is not bytes:
        raise _PINNED_ERROR_CLASS("QC source must be exact bytes")
    if source_bytes.startswith(b"\xef\xbb\xbf"):
        raise _PINNED_ERROR_CLASS("QC source has a UTF-8 BOM")
    if b"\r" in source_bytes:
        raise _PINNED_ERROR_CLASS("QC source is not canonical LF")
    if b"\x00" in source_bytes:
        raise _PINNED_ERROR_CLASS("QC source contains NUL")
    try:
        text = source_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _PINNED_ERROR_CLASS("QC source is not strict UTF-8") from exc
    if text.encode("utf-8", errors="strict") != source_bytes:
        raise _PINNED_ERROR_CLASS("QC source does not round-trip as UTF-8")
    character_count = _PINNED_LEN(text)
    if character_count > MAX_QC_SOURCE_CHARACTERS:
        raise _PINNED_ERROR_CLASS(
            "QC source exceeds the 64,000-character safety limit"
        )
    return character_count


def _require_refusal_entry_shape(source_bytes: bytes) -> None:
    """Authenticate the direct-source, service-call-free refusal entry shape."""

    _require_qc_source_character_count(source_bytes)
    try:
        tree = _PINNED_AST_PARSE(source_bytes.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, SyntaxError, ValueError, MemoryError) as exc:
        raise _PINNED_ERROR_CLASS("entry source is not strict Python") from exc

    expected_body_count = 3 + len(_PINNED_EXPECTED_ENTRY_ASSIGNMENTS)
    if (
        tree.type_ignores
        or len(tree.body) != expected_body_count
        or type(tree.body[0]) is not ast.Expr
        or type(tree.body[0].value) is not ast.Constant
        or type(tree.body[0].value.value) is not str
        or type(tree.body[1]) is not ast.ImportFrom
        or type(tree.body[-1]) is not ast.ClassDef
    ):
        raise _PINNED_ERROR_CLASS("entry module grammar changed")
    assignment_nodes = tree.body[2:-1]
    if len(assignment_nodes) != len(_PINNED_EXPECTED_ENTRY_ASSIGNMENTS):
        raise _PINNED_ERROR_CLASS("entry assignment topology changed")
    for statement, (expected_name, expected_value) in zip(
        assignment_nodes,
        _PINNED_EXPECTED_ENTRY_ASSIGNMENTS,
        strict=True,
    ):
        if (
            type(statement) is not ast.Assign
            or statement.type_comment is not None
            or len(statement.targets) != 1
            or type(statement.targets[0]) is not ast.Name
            or statement.targets[0].id != expected_name
        ):
            raise _PINNED_ERROR_CLASS("entry assignment order changed")
        try:
            actual_value = _PINNED_AST_LITERAL_EVAL(statement.value)
        except (ValueError, TypeError, MemoryError, RecursionError) as exc:
            raise _PINNED_ERROR_CLASS(
                f"entry assignment is not a literal: {expected_name}"
            ) from exc
        if (
            type(actual_value) is not type(expected_value)
            or actual_value != expected_value
        ):
            raise _PINNED_ERROR_CLASS(f"entry identity changed: {expected_name}")

    imports = tuple(
        node
        for node in _PINNED_AST_WALK(tree)
        if type(node) in (ast.Import, ast.ImportFrom)
    )
    if (
        _PINNED_LEN(imports) != 1
        or type(imports[0]) is not ast.ImportFrom
        or imports[0].module != "AlgorithmImports"
        or imports[0].level != 0
        or _PINNED_LEN(imports[0].names) != 1
        or imports[0].names[0].name != "*"
        or imports[0].names[0].asname is not None
    ):
        raise _PINNED_ERROR_CLASS("entry import shape changed")

    attributes = tuple(
        node for node in _PINNED_AST_WALK(tree) if type(node) is ast.Attribute
    )
    calls = tuple(
        node for node in _PINNED_AST_WALK(tree) if type(node) is ast.Call
    )
    if attributes:
        raise _PINNED_ERROR_CLASS("entry touches an attribute or service")
    if (
        _PINNED_LEN(calls) != 1
        or type(calls[0].func) is not ast.Name
        or calls[0].func.id != "RuntimeError"
        or calls[0].keywords
        or _PINNED_LEN(calls[0].args) != 1
        or type(calls[0].args[0]) is not ast.Name
        or calls[0].args[0].id != "SCAFFOLD_ONLY_MARKER"
    ):
        raise _PINNED_ERROR_CLASS("entry call surface changed")

    classes = tuple(
        statement for statement in tree.body if type(statement) is ast.ClassDef
    )
    if (
        _PINNED_LEN(classes) != 1
        or classes[0].name != ENTRY_CLASS_NAME
        or classes[0].decorator_list
        or classes[0].keywords
        or getattr(classes[0], "type_params", ())
        or _PINNED_LEN(classes[0].bases) != 1
        or type(classes[0].bases[0]) is not ast.Name
        or classes[0].bases[0].id != "QCAlgorithm"
    ):
        raise _PINNED_ERROR_CLASS("entry class shape changed")
    methods = tuple(
        statement
        for statement in classes[0].body
        if type(statement) in (ast.FunctionDef, ast.AsyncFunctionDef)
    )
    if (
        _PINNED_LEN(methods) != 2
        or len(classes[0].body) != 3
        or type(classes[0].body[0]) is not ast.Expr
        or type(classes[0].body[0].value) is not ast.Constant
        or type(classes[0].body[0].value.value) is not str
        or classes[0].body[1] is not methods[0]
        or classes[0].body[2] is not methods[1]
        or type(methods[0]) is not ast.FunctionDef
        or methods[0].name != "initialize"
        or type(methods[1]) is not ast.FunctionDef
        or methods[1].name != "on_end_of_algorithm"
    ):
        raise _PINNED_ERROR_CLASS("entry method topology changed")
    initialize = methods[0]
    if (
        initialize.decorator_list
        or initialize.returns is not None
        or initialize.type_comment is not None
        or getattr(initialize, "type_params", ())
        or initialize.args.posonlyargs
        or initialize.args.kwonlyargs
        or initialize.args.vararg is not None
        or initialize.args.kwarg is not None
        or initialize.args.defaults
        or initialize.args.kw_defaults
        or _PINNED_LEN(initialize.args.args) != 1
        or initialize.args.args[0].arg != "self"
        or initialize.args.args[0].annotation is not None
        or _PINNED_LEN(initialize.body) != 1
        or type(initialize.body[0]) is not ast.Raise
        or initialize.body[0].exc is not calls[0]
        or initialize.body[0].cause is not None
    ):
        raise _PINNED_ERROR_CLASS("initialize no longer immediately refuses")
    on_end = methods[1]
    if (
        on_end.decorator_list
        or on_end.returns is not None
        or on_end.type_comment is not None
        or getattr(on_end, "type_params", ())
        or on_end.args.posonlyargs
        or on_end.args.kwonlyargs
        or on_end.args.vararg is not None
        or on_end.args.kwarg is not None
        or on_end.args.defaults
        or on_end.args.kw_defaults
        or len(on_end.args.args) != 1
        or on_end.args.args[0].arg != "self"
        or on_end.args.args[0].annotation is not None
        or len(on_end.body) != 1
        or type(on_end.body[0]) is not ast.Return
        or type(on_end.body[0].value) is not ast.Constant
        or on_end.body[0].value.value is not None
    ):
        raise _PINNED_ERROR_CLASS("end callback shape changed")
    if (
        _PINNED_SHA256(source_bytes).hexdigest() != B5B_ENTRY_SOURCE_SHA256
        or _PINNED_LEN(source_bytes) != B5B_ENTRY_SOURCE_BYTE_COUNT
    ):
        raise _PINNED_ERROR_CLASS("entry source identity changed")


def _require_static_contract() -> None:
    if _PINNED_GLOBALS() is not _MODULE_GLOBALS:
        raise _PINNED_ERROR_CLASS("refusal-smoke module globals changed")
    for name, expected in _PINNED_STATIC_SNAPSHOT_BINDINGS:
        if _MODULE_GLOBALS.get(name) is not expected:
            raise _PINNED_ERROR_CLASS("refusal-smoke static snapshot changed")
    for name, expected in _PINNED_ALIAS_BINDINGS:
        if _MODULE_GLOBALS.get(name) is not expected:
            raise _PINNED_ERROR_CLASS("refusal-smoke pinned binding changed")
    if (
        _PINNED_TYPE(_PINNED_MODULE_BINDINGS) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_DEPENDENCY_BINDINGS) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_IMPORTED_BINDINGS) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_BUILTIN_BINDINGS) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_PARENT_FUNCTION_STATES) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_LOCAL_FUNCTION_STATES) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_CLASS_BINDINGS) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_CLASS_STATES) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_CLASS_FUNCTION_STATES)
        is not _PINNED_TUPLE
    ):
        raise _PINNED_ERROR_CLASS("refusal-smoke static topology changed")
    for name, expected in _PINNED_MODULE_BINDINGS:
        if _MODULE_GLOBALS.get(name) is not expected:
            raise _PINNED_ERROR_CLASS("refusal-smoke dependency module changed")
    for module, name, expected in _PINNED_DEPENDENCY_BINDINGS:
        if _PINNED_GETATTR(module, name) is not expected:
            raise _PINNED_ERROR_CLASS(
                "refusal-smoke dependency binding changed"
            )
    for name, expected in _PINNED_IMPORTED_BINDINGS:
        if _MODULE_GLOBALS.get(name) is not expected:
            raise _PINNED_ERROR_CLASS("refusal-smoke parent binding changed")
    if (
        _PINNED_TYPE(_PINNED_BUILTINS_DICT) is not _PINNED_DICT
        or _MODULE_GLOBALS.get("__builtins__") is not _PINNED_BUILTINS_DICT
    ):
        raise _PINNED_ERROR_CLASS("refusal-smoke builtins root changed")
    for name, expected in _PINNED_BUILTIN_BINDINGS:
        if (
            name in _MODULE_GLOBALS
            or _PINNED_BUILTINS_DICT.get(name) is not expected
        ):
            raise _PINNED_ERROR_CLASS("refusal-smoke builtin changed")
    for implementation, code, defaults, kwdefaults, closure, cells in (
        _PINNED_PARENT_FUNCTION_STATES
    ):
        if (
            implementation.__code__ is not code
            or implementation.__defaults__ is not defaults
            or implementation.__kwdefaults__ is not kwdefaults
            or implementation.__closure__ is not closure
        ):
            raise _PINNED_ERROR_CLASS("refusal-smoke parent function changed")
        for cell, content_type, content in cells:
            try:
                current_content = cell.cell_contents
            except _PINNED_VALUE_ERROR as exc:
                raise _PINNED_ERROR_CLASS(
                    "refusal-smoke parent closure changed"
                ) from exc
            if (
                _PINNED_TYPE(current_content) is not content_type
                or current_content is not content
            ):
                raise _PINNED_ERROR_CLASS(
                    "refusal-smoke parent closure changed"
                )
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
            raise _PINNED_ERROR_CLASS("refusal-smoke function changed")
        for cell, content_type, content in cells:
            try:
                current_content = cell.cell_contents
            except _PINNED_VALUE_ERROR as exc:
                raise _PINNED_ERROR_CLASS(
                    "refusal-smoke function closure changed"
                ) from exc
            if (
                _PINNED_TYPE(current_content) is not content_type
                or current_content is not content
            ):
                raise _PINNED_ERROR_CLASS(
                    "refusal-smoke function closure changed"
                )
    for name, expected in _PINNED_CLASS_BINDINGS:
        if _MODULE_GLOBALS.get(name) is not expected:
            raise _PINNED_ERROR_CLASS("refusal-smoke class changed")
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
            raise _PINNED_ERROR_CLASS("refusal-smoke class ancestry changed")
        current_members = _PINNED_TUPLE(_PINNED_VARS(accepted_class).items())
        if _PINNED_LEN(current_members) != _PINNED_LEN(expected_members):
            raise _PINNED_ERROR_CLASS("refusal-smoke class topology changed")
        for current, expected in _PINNED_ZIP(
            current_members, expected_members, strict=True
        ):
            if (
                _PINNED_TYPE(current[0]) is not _PINNED_STR
                or current[0] != expected[0]
                or current[1] is not expected[1]
            ):
                raise _PINNED_ERROR_CLASS(
                    "refusal-smoke class topology changed"
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
                "refusal-smoke class function changed"
            )
        for cell, content_type, content in cells:
            try:
                current_content = cell.cell_contents
            except _PINNED_VALUE_ERROR as exc:
                raise _PINNED_ERROR_CLASS(
                    "refusal-smoke class closure changed"
                ) from exc
            if (
                _PINNED_TYPE(current_content) is not content_type
                or current_content is not content
            ):
                raise _PINNED_ERROR_CLASS(
                    "refusal-smoke class closure changed"
                )
    scalar_contract = (
        (SCHEMA, _PINNED_STR, "arv2-qc-refusal-smoke-projection-schema-v1"),
        (
            STATUS,
            _PINNED_STR,
            "offline_one_file_refusal_smoke_projected_cloud_execution_"
            "unperformed",
        ),
        (
            AUTHORITY,
            _PINNED_STR,
            "offline_values_only_no_client_callback_filesystem_environment_"
            "provider_credential_account_project_object_store_upload_compile_"
            "launch_result_evaluation_deployment_order_or_trading_authority",
        ),
        (HASH_DOMAIN, _PINNED_STR, "arv2-qc-refusal-smoke-projection-v1"),
        (MAX_QC_SOURCE_CHARACTERS, _PINNED_INT, 64_000),
        (EXPECTED_PROJECT_FILE_COUNT, _PINNED_INT, 1),
        (ENTRY_PROJECT_PATH, _PINNED_STR, "main.py"),
        (B5B_ENTRY_PROJECT_PATH, _PINNED_STR, "main.py"),
        (
            ENTRY_CLASS_NAME,
            _PINNED_STR,
            "AnalystRevisionsV2StockEventStudyScaffold",
        ),
        (
            B5B_ENTRY_CLASS_NAME,
            _PINNED_STR,
            "AnalystRevisionsV2StockEventStudyScaffold",
        ),
        (
            SCAFFOLD_ONLY_MARKER,
            _PINNED_STR,
            "ARV2-4F-B5B SOURCE_ASSEMBLY_ONLY: QC execution is not authorized",
        ),
        (
            QUOTA_OBSERVATION_ID,
            _PINNED_STR,
            "arv2-qc-file-character-limit-observation-20260911",
        ),
        (
            QUOTA_RECEIPT_SHA256,
            _PINNED_STR,
            "f2c3fd7536100bb4a1e1e9a8f5e4b349ff73196d286de7916c8bed5d9930a7ae",
        ),
        (
            QUOTA_OBSERVATION,
            _PINNED_STR,
            "QuantConnect files/create reported a maximum of 64,000 "
            "characters; B5C applies the stricter decoded-source count "
            "including the final LF",
        ),
        (
            _EXPECTED_PARENT_ASSEMBLY_ID,
            _PINNED_STR,
            "arv2-qc-lean-source-assembly-8303f3323ff16ab7",
        ),
        (
            _EXPECTED_PARENT_ASSEMBLY_SHA256,
            _PINNED_STR,
            "8303f3323ff16ab7da6c03c587bfbbf4a8d8ecb356eb8912307c2c78a75c1266",
        ),
        (
            _EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256,
            _PINNED_STR,
            "56d3f77e731f6a13b5dbfb9bcbfcd8e89261a226400b744cf2c0fa3d3b400bdd",
        ),
        (
            SCHEMA_ID,
            _PINNED_STR,
            "arv2-qc-refusal-smoke-projection-1fe0201a3ccb8478",
        ),
        (
            SCHEMA_SHA256,
            _PINNED_STR,
            "1fe0201a3ccb847896e14afd20a3729d14811ad2f0b472db08cd319c87ac2deb",
        ),
        (
            SCHEMA_ARTIFACT_SHA256,
            _PINNED_STR,
            "ddb152f64aec2a382ded9009b0dab5c0485d31b03f6eb293af23789a99a3de10",
        ),
    )
    for actual, expected_type, expected in scalar_contract:
        if _PINNED_TYPE(actual) is not expected_type or actual != expected:
            raise _PINNED_ERROR_CLASS("refusal-smoke scalar contract changed")
    if (
        ENTRY_PROJECT_PATH != B5B_ENTRY_PROJECT_PATH
        or ENTRY_CLASS_NAME != B5B_ENTRY_CLASS_NAME
    ):
        raise _PINNED_ERROR_CLASS("refusal-smoke parent scalar changed")
    if (
        FORMAL_PRIMARY_FOLD_IDS is not _PINNED_FORMAL_PRIMARY_FOLD_IDS
        or DESCRIPTIVE_SENSITIVITY_FOLD_IDS
        is not _PINNED_DESCRIPTIVE_SENSITIVITY_FOLD_IDS
        or OVER_LIMIT_B5B_SOURCE_FILES is not _PINNED_OVER_LIMIT_B5B_SOURCE_FILES
        or EXTERNAL_BINDINGS is not _PINNED_EXTERNAL_BINDINGS
        or CAPABILITIES is not _PINNED_CAPABILITIES
        or _EXPECTED_SCAFFOLD_CAPABILITY_FLAGS
        is not _PINNED_EXPECTED_SCAFFOLD_CAPABILITY_FLAGS
        or _EXPECTED_ENTRY_ASSIGNMENTS is not _PINNED_EXPECTED_ENTRY_ASSIGNMENTS
        or _EXPECTED_PARENT_ASSEMBLY_IDENTITY
        is not _PINNED_EXPECTED_PARENT_ASSEMBLY_IDENTITY
        or __all__ is not _PINNED_ALL_EXPORTS
        or _SCHEMA_DOCUMENT_BYTES is not _PINNED_SCHEMA_DOCUMENT_BYTES
    ):
        raise _PINNED_ERROR_CLASS("refusal-smoke registry changed")
    if (
        _PINNED_TYPE(FORMAL_PRIMARY_FOLD_IDS) is not _PINNED_TUPLE
        or FORMAL_PRIMARY_FOLD_IDS
        != _PINNED_TUPLE(
            f"arv2-wf-test-{year}" for year in _PINNED_RANGE(2020, 2026)
        )
        or _PINNED_TYPE(DESCRIPTIVE_SENSITIVITY_FOLD_IDS)
        is not _PINNED_TUPLE
        or DESCRIPTIVE_SENSITIVITY_FOLD_IDS
        != _PINNED_TUPLE(
            f"arv2-wf-test-{year}" for year in _PINNED_RANGE(2021, 2026)
        )
        or _PINNED_TYPE(OVER_LIMIT_B5B_SOURCE_FILES) is not _PINNED_TUPLE
        or OVER_LIMIT_B5B_SOURCE_FILES
        != (
            (
                "event_study_core",
                "research/analyst_revisions_v2_qc/event_study.py",
                109_226,
            ),
            (
                "global_input_bundle",
                "research/analyst_revisions_v2_qc/global_input_bundle.py",
                140_983,
            ),
            (
                "global_input_schema",
                "research/analyst_revisions_v2_qc/global_input_schema.py",
                94_959,
            ),
            (
                "synthetic_input_transport",
                "research/analyst_revisions_v2_qc/synthetic_input_transport.py",
                65_144,
            ),
        )
        or _PINNED_TYPE(_EXPECTED_PARENT_ASSEMBLY_IDENTITY)
        is not _PINNED_TUPLE
        or _EXPECTED_PARENT_ASSEMBLY_IDENTITY
        != (
            _EXPECTED_PARENT_ASSEMBLY_ID,
            _EXPECTED_PARENT_ASSEMBLY_SHA256,
            _EXPECTED_PARENT_ASSEMBLY_ARTIFACT_SHA256,
        )
        or _PINNED_TYPE(__all__) is not _PINNED_TUPLE
        or __all__ != _PINNED_ALL_EXPORTS
        or any(
            _PINNED_TYPE(item) is not _PINNED_TUPLE
            or _PINNED_LEN(item) != 2
            or _PINNED_TYPE(item[0]) is not _PINNED_STR
            or item[1] is not None
            for item in EXTERNAL_BINDINGS
        )
        or any(
            _PINNED_TYPE(item) is not _PINNED_TUPLE
            or _PINNED_LEN(item) != 2
            or _PINNED_TYPE(item[0]) is not _PINNED_STR
            or item[1] is not False
            for item in CAPABILITIES
        )
    ):
        raise _PINNED_ERROR_CLASS("refusal-smoke static topology changed")
    try:
        parent_schema = _PINNED_RENDER_PARENT_SCHEMA()
    except (
        _PINNED_PARENT_ERROR_CLASS,
        _PINNED_TYPE_ERROR,
        _PINNED_VALUE_ERROR,
    ) as exc:
        raise _PINNED_ERROR_CLASS("B5B schema preflight refused") from exc
    if (
        _PINNED_TYPE(parent_schema) is not _PINNED_BYTES
        or _PINNED_SHA256(parent_schema).hexdigest()
        != B5B_SCHEMA_ARTIFACT_SHA256
    ):
        raise _PINNED_ERROR_CLASS("B5B schema identity changed")
    rebuilt, digest = _identity_document(
        _schema_seed_document(),
        id_key="schema_id",
        hash_key="schema_sha256",
        prefix="arv2-qc-refusal-smoke-projection",
    )
    rebuilt_bytes = _canonical_bytes(rebuilt)
    if (
        digest != SCHEMA_SHA256
        or SCHEMA_ID != f"arv2-qc-refusal-smoke-projection-{digest[:16]}"
        or rebuilt_bytes != _SCHEMA_DOCUMENT_BYTES
        or _PINNED_SHA256(rebuilt_bytes).hexdigest()
        != SCHEMA_ARTIFACT_SHA256
    ):
        raise _PINNED_ERROR_CLASS("refusal-smoke schema identity changed")


def render_qc_refusal_smoke_projection_schema_bytes() -> bytes:
    """Render the content-addressed B5C schema without opening any source."""

    _require_static_contract()
    return _SCHEMA_DOCUMENT_BYTES


def _project_file_from_parent(
    source_assembly: SyntheticLeanProjectAssembly,
) -> QcRefusalSmokeProjectFile:
    if (
        type(source_assembly.files) is not tuple
        or len(source_assembly.files) != 11
    ):
        raise _PINNED_ERROR_CLASS("B5B source inventory changed")
    parent_file = source_assembly.files[0]
    if (
        type(parent_file) is not _PINNED_PARENT_FILE_CLASS
        or type(parent_file.role) is not str
        or parent_file.role != "lean_entry"
        or type(parent_file.repository_path) is not str
        or parent_file.repository_path
        != "research/lean/analyst_revisions_v2_scaffold.py"
        or type(parent_file.project_path) is not str
        or parent_file.project_path != ENTRY_PROJECT_PATH
        or type(parent_file.source_bytes) is not bytes
        or type(parent_file.byte_count) is not int
        or parent_file.byte_count != B5B_ENTRY_SOURCE_BYTE_COUNT
        or type(parent_file.sha256) is not str
        or parent_file.sha256 != B5B_ENTRY_SOURCE_SHA256
    ):
        raise _PINNED_ERROR_CLASS("B5B entry descriptor changed")
    character_count = _require_qc_source_character_count(
        parent_file.source_bytes
    )
    _require_refusal_entry_shape(parent_file.source_bytes)
    return QcRefusalSmokeProjectFile(
        role=parent_file.role,
        repository_path=parent_file.repository_path,
        project_path=parent_file.project_path,
        source_bytes=parent_file.source_bytes,
        byte_count=parent_file.byte_count,
        character_count=character_count,
        sha256=parent_file.sha256,
    )


def _projection_seed_document(
    *,
    parent_assembly_id: str,
    parent_assembly_hash: str,
    parent_assembly_artifact_sha256: str,
    project_file: QcRefusalSmokeProjectFile,
) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "schema_id": SCHEMA_ID,
        "schema_sha256": SCHEMA_SHA256,
        "schema_artifact_sha256": SCHEMA_ARTIFACT_SHA256,
        "projection_id": None,
        "projection_hash": None,
        "status": STATUS,
        "authority": AUTHORITY,
        "parent": {
            "assembly_id": parent_assembly_id,
            "assembly_hash": parent_assembly_hash,
            "assembly_artifact_sha256": parent_assembly_artifact_sha256,
            "b5b_schema_id": B5B_SCHEMA_ID,
            "b5b_schema_sha256": B5B_SCHEMA_SHA256,
            "b5b_schema_artifact_sha256": B5B_SCHEMA_ARTIFACT_SHA256,
        },
        "entry_project_path": ENTRY_PROJECT_PATH,
        "entry_class_name": ENTRY_CLASS_NAME,
        "files": [
            {
                "role": project_file.role,
                "repository_path": project_file.repository_path,
                "project_path": project_file.project_path,
                "byte_count": project_file.byte_count,
                "character_count": project_file.character_count,
                "sha256": project_file.sha256,
            }
        ],
        "total_source_byte_count": project_file.byte_count,
        "total_source_character_count": project_file.character_count,
        "largest_project_file_character_count": project_file.character_count,
        "source_only": True,
        "immediate_refusal": True,
        "strategy_execution_capable": False,
        "evaluation_window_applied": False,
        "runtime_code_authenticated": False,
        "physical_adapter_present": False,
        "project_created": False,
        "cloud_compile_performed": False,
        "backtest_performed": False,
        "result_access_performed": False,
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
    }


def build_synthetic_qc_refusal_smoke_projection(
    *,
    source_assembly: SyntheticLeanProjectAssembly,
) -> SyntheticQcRefusalSmokeProjection:
    """Authenticate B5B and select its exact direct-source refusal entry."""

    _require_static_contract()
    try:
        authenticated_parent = _PINNED_REQUIRE_PARENT(source_assembly)
    except (QcLeanSourceAssemblyError, TypeError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS("B5B source assembly refused") from exc
    if authenticated_parent is not source_assembly:
        raise _PINNED_ERROR_CLASS("B5B source assembly identity changed")
    project_file = _project_file_from_parent(authenticated_parent)
    parent_snapshot = (
        authenticated_parent.assembly_id,
        authenticated_parent.assembly_hash,
        authenticated_parent.assembly_artifact_sha256,
        project_file.role,
        project_file.repository_path,
        project_file.project_path,
        project_file.source_bytes,
        project_file.byte_count,
        project_file.character_count,
        project_file.sha256,
    )
    if parent_snapshot[:3] != _EXPECTED_PARENT_ASSEMBLY_IDENTITY:
        raise _PINNED_ERROR_CLASS("B5B parent identity is not the reviewed one")
    try:
        second_authentication = _PINNED_REQUIRE_PARENT(source_assembly)
    except (QcLeanSourceAssemblyError, TypeError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS(
            "B5B source assembly changed during projection"
        ) from exc
    if second_authentication is not source_assembly:
        raise _PINNED_ERROR_CLASS("B5B source assembly identity changed")
    second_file = _project_file_from_parent(second_authentication)
    if parent_snapshot != (
        second_authentication.assembly_id,
        second_authentication.assembly_hash,
        second_authentication.assembly_artifact_sha256,
        second_file.role,
        second_file.repository_path,
        second_file.project_path,
        second_file.source_bytes,
        second_file.byte_count,
        second_file.character_count,
        second_file.sha256,
    ):
        raise _PINNED_ERROR_CLASS("B5B source assembly changed during projection")
    (
        parent_assembly_id,
        parent_assembly_hash,
        parent_assembly_artifact_sha256,
        _role,
        _repository_path,
        _project_path,
        _source_bytes,
        _byte_count,
        _character_count,
        _sha256,
    ) = parent_snapshot
    project_file = second_file
    seed = _projection_seed_document(
        parent_assembly_id=parent_assembly_id,
        parent_assembly_hash=parent_assembly_hash,
        parent_assembly_artifact_sha256=parent_assembly_artifact_sha256,
        project_file=project_file,
    )
    final, digest = _identity_document(
        seed,
        id_key="projection_id",
        hash_key="projection_hash",
        prefix="arv2-qc-refusal-smoke-projection",
    )
    canonical_document = _canonical_bytes(final)
    artifact_sha256 = _PINNED_SHA256(canonical_document).hexdigest()
    return SyntheticQcRefusalSmokeProjection(
        projection_id=str(final["projection_id"]),
        projection_hash=digest,
        projection_artifact_sha256=artifact_sha256,
        parent_assembly_id=parent_assembly_id,
        parent_assembly_hash=parent_assembly_hash,
        parent_assembly_artifact_sha256=parent_assembly_artifact_sha256,
        entry_project_path=ENTRY_PROJECT_PATH,
        entry_class_name=ENTRY_CLASS_NAME,
        files=(project_file,),
        total_source_byte_count=project_file.byte_count,
        total_source_character_count=project_file.character_count,
        largest_project_file_character_count=project_file.character_count,
        source_only=True,
        immediate_refusal=True,
        strategy_execution_capable=False,
        evaluation_window_applied=False,
        physical_adapter_present=False,
        project_created=False,
        cloud_compile_performed=False,
        backtest_performed=False,
        result_access_performed=False,
        external_bindings=EXTERNAL_BINDINGS,
        capabilities=CAPABILITIES,
        _canonical_document=canonical_document,
    )


def require_synthetic_qc_refusal_smoke_projection(
    value: SyntheticQcRefusalSmokeProjection,
) -> SyntheticQcRefusalSmokeProjection:
    """Reauthenticate an immutable detached B5C source projection."""

    _require_static_contract()
    if type(value) is not SyntheticQcRefusalSmokeProjection:
        raise _PINNED_ERROR_CLASS("refusal-smoke projection type changed")
    scalar_types = (
        (value.projection_id, str),
        (value.projection_hash, str),
        (value.projection_artifact_sha256, str),
        (value.parent_assembly_id, str),
        (value.parent_assembly_hash, str),
        (value.parent_assembly_artifact_sha256, str),
        (value.entry_project_path, str),
        (value.entry_class_name, str),
        (value.total_source_byte_count, int),
        (value.total_source_character_count, int),
        (value.largest_project_file_character_count, int),
        (value.source_only, bool),
        (value.immediate_refusal, bool),
        (value.strategy_execution_capable, bool),
        (value.evaluation_window_applied, bool),
        (value.physical_adapter_present, bool),
        (value.project_created, bool),
        (value.cloud_compile_performed, bool),
        (value.backtest_performed, bool),
        (value.result_access_performed, bool),
        (value.files, tuple),
        (value.external_bindings, tuple),
        (value.capabilities, tuple),
        (value._canonical_document, bytes),
    )
    if any(type(actual) is not expected for actual, expected in scalar_types):
        raise _PINNED_ERROR_CLASS("refusal-smoke projection field type changed")
    if (
        (
            value.parent_assembly_id,
            value.parent_assembly_hash,
            value.parent_assembly_artifact_sha256,
        )
        != _EXPECTED_PARENT_ASSEMBLY_IDENTITY
        or len(value.parent_assembly_hash) != 64
        or len(value.parent_assembly_artifact_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in value.parent_assembly_hash
        )
        or any(
            character not in "0123456789abcdef"
            for character in value.parent_assembly_artifact_sha256
        )
        or value.parent_assembly_id
        != f"arv2-qc-lean-source-assembly-{value.parent_assembly_hash[:16]}"
    ):
        raise _PINNED_ERROR_CLASS("B5B parent identity shape changed")
    if len(value.files) != 1:
        raise _PINNED_ERROR_CLASS("refusal-smoke file inventory changed")
    expected_file = value.files[0]
    if (
        type(expected_file) is not QcRefusalSmokeProjectFile
        or type(expected_file.role) is not str
        or expected_file.role != "lean_entry"
        or type(expected_file.repository_path) is not str
        or expected_file.repository_path
        != "research/lean/analyst_revisions_v2_scaffold.py"
        or type(expected_file.project_path) is not str
        or expected_file.project_path != ENTRY_PROJECT_PATH
        or type(expected_file.source_bytes) is not bytes
        or type(expected_file.byte_count) is not int
        or expected_file.byte_count != B5B_ENTRY_SOURCE_BYTE_COUNT
        or len(expected_file.source_bytes) != expected_file.byte_count
        or type(expected_file.character_count) is not int
        or expected_file.character_count
        != _require_qc_source_character_count(expected_file.source_bytes)
        or type(expected_file.sha256) is not str
        or expected_file.sha256 != B5B_ENTRY_SOURCE_SHA256
        or _PINNED_SHA256(expected_file.source_bytes).hexdigest()
        != expected_file.sha256
    ):
        raise _PINNED_ERROR_CLASS("refusal-smoke source file changed")
    _require_refusal_entry_shape(expected_file.source_bytes)
    if (
        value.entry_project_path != ENTRY_PROJECT_PATH
        or value.entry_class_name != ENTRY_CLASS_NAME
        or value.total_source_byte_count != expected_file.byte_count
        or value.total_source_character_count != expected_file.character_count
        or value.largest_project_file_character_count
        != expected_file.character_count
        or value.source_only is not True
        or value.immediate_refusal is not True
        or value.strategy_execution_capable is not False
        or value.evaluation_window_applied is not False
        or value.physical_adapter_present is not False
        or value.project_created is not False
        or value.cloud_compile_performed is not False
        or value.backtest_performed is not False
        or value.result_access_performed is not False
        or value.external_bindings is not EXTERNAL_BINDINGS
        or value.capabilities is not CAPABILITIES
        or any(getattr(value, name) is not False for name in (
            "filesystem_read_available",
            "environment_read_available",
            "provider_access_available",
            "licensed_input_read_available",
            "production_manifest_available",
            "production_input_read_available",
            "real_outcome_access_available",
            "runtime_code_authenticated",
            "qc_object_store_read_available",
            "qc_object_store_write_available",
            "qc_project_create_available",
            "upload_available",
            "compile_available",
            "launch_available",
            "result_access_available",
            "result_disposition_available",
            "deployment_available",
            "orders_available",
            "trading_available",
        ))
    ):
        raise _PINNED_ERROR_CLASS("refusal-smoke projection content changed")
    seed = _projection_seed_document(
        parent_assembly_id=value.parent_assembly_id,
        parent_assembly_hash=value.parent_assembly_hash,
        parent_assembly_artifact_sha256=(
            value.parent_assembly_artifact_sha256
        ),
        project_file=expected_file,
    )
    final, digest = _identity_document(
        seed,
        id_key="projection_id",
        hash_key="projection_hash",
        prefix="arv2-qc-refusal-smoke-projection",
    )
    canonical_document = _canonical_bytes(final)
    artifact_sha256 = _PINNED_SHA256(canonical_document).hexdigest()
    if (
        value.projection_hash != digest
        or value.projection_id
        != f"arv2-qc-refusal-smoke-projection-{digest[:16]}"
        or value.projection_artifact_sha256 != artifact_sha256
        or value._canonical_document != canonical_document
        or _PINNED_SHA256(value._canonical_document).hexdigest()
        != value.projection_artifact_sha256
    ):
        raise _PINNED_ERROR_CLASS("refusal-smoke projection identity changed")
    return value


def _make_bootstrap_wrappers(
    *,
    error_class,
    module_globals,
    render_impl,
    build_impl,
    require_impl,
    pinned_len,
    pinned_type,
    pinned_tuple,
):
    """Keep the public boundary rooted outside mutable module-name lookup."""

    holder: list[object] = []

    def seal(*, static_snapshot_bindings, alias_bindings, static_validator):
        if holder:
            raise error_class("refusal-smoke bootstrap already sealed")
        public_bindings = (
            (
                "render_qc_refusal_smoke_projection_schema_bytes",
                guarded_render,
            ),
            (
                "build_synthetic_qc_refusal_smoke_projection",
                guarded_build,
            ),
            (
                "require_synthetic_qc_refusal_smoke_projection",
                guarded_require,
            ),
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
        if pinned_len(holder) != 1 or pinned_type(holder[0]) is not pinned_tuple:
            raise error_class("refusal-smoke bootstrap is not sealed")
        if pinned_len(holder[0]) != 4:
            raise error_class("refusal-smoke bootstrap topology changed")
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
            raise error_class("refusal-smoke bootstrap registry changed")
        for name, expected in static_snapshot_bindings:
            if module_globals.get(name) is not expected:
                raise error_class("refusal-smoke bootstrap snapshot changed")
        for name, expected in alias_bindings:
            if module_globals.get(name) is not expected:
                raise error_class("refusal-smoke bootstrap alias changed")
        for name, expected in public_bindings:
            if module_globals.get(name) is not expected:
                raise error_class("refusal-smoke public binding changed")
        static_validator()

    def guarded_render() -> bytes:
        check()
        return render_impl()

    def guarded_build(
        *,
        source_assembly: SyntheticLeanProjectAssembly,
    ) -> SyntheticQcRefusalSmokeProjection:
        check()
        return build_impl(source_assembly=source_assembly)

    def guarded_require(
        value: SyntheticQcRefusalSmokeProjection,
    ) -> SyntheticQcRefusalSmokeProjection:
        check()
        return require_impl(value)

    guarded_render.__name__ = "render_qc_refusal_smoke_projection_schema_bytes"
    guarded_render.__qualname__ = (
        "render_qc_refusal_smoke_projection_schema_bytes"
    )
    guarded_render.__doc__ = render_impl.__doc__
    guarded_build.__name__ = "build_synthetic_qc_refusal_smoke_projection"
    guarded_build.__qualname__ = "build_synthetic_qc_refusal_smoke_projection"
    guarded_build.__doc__ = build_impl.__doc__
    guarded_require.__name__ = "require_synthetic_qc_refusal_smoke_projection"
    guarded_require.__qualname__ = (
        "require_synthetic_qc_refusal_smoke_projection"
    )
    guarded_require.__doc__ = require_impl.__doc__
    return guarded_render, guarded_build, guarded_require, seal


_PINNED_RENDER_SCHEMA_IMPL = render_qc_refusal_smoke_projection_schema_bytes
_PINNED_BUILD_PROJECTION_IMPL = build_synthetic_qc_refusal_smoke_projection
_PINNED_REQUIRE_PROJECTION_IMPL = require_synthetic_qc_refusal_smoke_projection
(
    render_qc_refusal_smoke_projection_schema_bytes,
    build_synthetic_qc_refusal_smoke_projection,
    require_synthetic_qc_refusal_smoke_projection,
    _BOOTSTRAP_SEAL,
) = _make_bootstrap_wrappers(
    error_class=QcRefusalSmokeProjectionError,
    module_globals=_MODULE_GLOBALS,
    render_impl=_PINNED_RENDER_SCHEMA_IMPL,
    build_impl=_PINNED_BUILD_PROJECTION_IMPL,
    require_impl=_PINNED_REQUIRE_PROJECTION_IMPL,
    pinned_len=_PINNED_LEN,
    pinned_type=_PINNED_TYPE,
    pinned_tuple=_PINNED_TUPLE,
)

_PINNED_RENDER_SCHEMA = render_qc_refusal_smoke_projection_schema_bytes
_PINNED_BUILD_PROJECTION = build_synthetic_qc_refusal_smoke_projection
_PINNED_REQUIRE_PROJECTION = require_synthetic_qc_refusal_smoke_projection
_PINNED_ERROR_CLASS_BINDING = QcRefusalSmokeProjectionError
_PINNED_PROJECT_FILE_CLASS = QcRefusalSmokeProjectFile
_PINNED_PROJECTION_CLASS = SyntheticQcRefusalSmokeProjection
_PINNED_ALL_EXPORTS = __all__
_PINNED_EXPECTED_PARENT_ASSEMBLY_IDENTITY = (
    _EXPECTED_PARENT_ASSEMBLY_IDENTITY
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
        _PINNED_REQUIRE_PARENT,
        _PINNED_RENDER_PARENT_SCHEMA,
    )
)
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
        ("_canonical_bytes", _canonical_bytes),
        ("_schema_seed_document", _schema_seed_document),
        ("_identity_document", _identity_document),
        (
            "_require_qc_source_character_count",
            _require_qc_source_character_count,
        ),
        ("_require_refusal_entry_shape", _require_refusal_entry_shape),
        ("_require_static_contract", _require_static_contract),
        (
            "render_qc_refusal_smoke_projection_schema_bytes",
            _PINNED_RENDER_SCHEMA,
        ),
        ("_project_file_from_parent", _project_file_from_parent),
        ("_projection_seed_document", _projection_seed_document),
        (
            "build_synthetic_qc_refusal_smoke_projection",
            _PINNED_BUILD_PROJECTION,
        ),
        (
            "require_synthetic_qc_refusal_smoke_projection",
            _PINNED_REQUIRE_PROJECTION,
        ),
        ("_make_bootstrap_wrappers", _make_bootstrap_wrappers),
        ("_PINNED_RENDER_SCHEMA_IMPL", _PINNED_RENDER_SCHEMA_IMPL),
        ("_PINNED_BUILD_PROJECTION_IMPL", _PINNED_BUILD_PROJECTION_IMPL),
        ("_PINNED_REQUIRE_PROJECTION_IMPL", _PINNED_REQUIRE_PROJECTION_IMPL),
    )
)
_PINNED_CLASS_BINDINGS = (
    ("QcRefusalSmokeProjectionError", _PINNED_ERROR_CLASS_BINDING),
    ("QcRefusalSmokeProjectFile", _PINNED_PROJECT_FILE_CLASS),
    ("SyntheticQcRefusalSmokeProjection", _PINNED_PROJECTION_CLASS),
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
_PINNED_ALIAS_BINDINGS = tuple(
    (name, value)
    for name, value in tuple(_MODULE_GLOBALS.items())
    if name.startswith("_PINNED_")
    and name not in {"_PINNED_ALIAS_BINDINGS", "_PINNED_STATIC_SNAPSHOT_BINDINGS"}
)
_PINNED_STATIC_SNAPSHOT_BINDINGS = (
    ("_PINNED_MODULE_BINDINGS", _PINNED_MODULE_BINDINGS),
    ("_PINNED_DEPENDENCY_BINDINGS", _PINNED_DEPENDENCY_BINDINGS),
    ("_PINNED_IMPORTED_BINDINGS", _PINNED_IMPORTED_BINDINGS),
    ("_PINNED_BUILTIN_BINDINGS", _PINNED_BUILTIN_BINDINGS),
    ("_PINNED_PARENT_FUNCTION_STATES", _PINNED_PARENT_FUNCTION_STATES),
    ("_PINNED_LOCAL_FUNCTION_STATES", _PINNED_LOCAL_FUNCTION_STATES),
    ("_PINNED_CLASS_BINDINGS", _PINNED_CLASS_BINDINGS),
    ("_PINNED_CLASS_STATES", _PINNED_CLASS_STATES),
    ("_PINNED_CLASS_FUNCTION_STATES", _PINNED_CLASS_FUNCTION_STATES),
    ("_PINNED_ALIAS_BINDINGS", _PINNED_ALIAS_BINDINGS),
)
_PINNED_REQUIRE_STATIC_CONTRACT = _require_static_contract
_BOOTSTRAP_SEAL(
    static_snapshot_bindings=_PINNED_STATIC_SNAPSHOT_BINDINGS,
    alias_bindings=_PINNED_ALIAS_BINDINGS,
    static_validator=_PINNED_REQUIRE_STATIC_CONTRACT,
)
del _BOOTSTRAP_SEAL
