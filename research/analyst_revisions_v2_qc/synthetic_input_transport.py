"""Synthetic Object-Store layout and resolution contract for ARV2 QC inputs.

This module models the logical object layout that a later QuantConnect adapter
may consume, but it deliberately accepts only an exact in-memory fixture.  It
does not import QuantConnect, inspect the environment, touch a filesystem,
contact a provider, or read real outcomes.  A real Object Store adapter remains
a separately reviewed and explicitly authorized milestone.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import re

from .global_input_bundle import (
    SCHEMA_ARTIFACT_SHA256 as BUNDLE_SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID as BUNDLE_SCHEMA_ID,
    SCHEMA_SHA256 as BUNDLE_SCHEMA_SHA256,
    QcGlobalInputBundleError,
    SyntheticGlobalInputPartitionPayload,
    SyntheticQcGlobalInputBundle,
    load_synthetic_qc_global_input_bundle,
    require_synthetic_qc_global_input_bundle,
)
from .global_input_schema import (
    ROLE_ORDER,
    QcGlobalInputSchemaError,
    SyntheticQcGlobalInputManifest,
    load_synthetic_qc_global_input_manifest_bytes,
)
from .run_contract import (
    QcRunContractError,
    SyntheticQcRunCandidate,
    require_synthetic_qc_run_candidate,
)


_PINNED_ANY = any
_PINNED_DICT = dict
_PINNED_DICT_GET = dict.get
_PINNED_DICT_ITEMS = dict.items
_PINNED_ID = id
_PINNED_LEN = len
_PINNED_LIST = list
_PINNED_OBJECT = object
_PINNED_SET = set
_PINNED_STR = str
_PINNED_TUPLE = tuple
_PINNED_TYPE = type
_PINNED_ZIP = zip


class QcSyntheticInputTransportError(ValueError):
    """A synthetic transport index, fixture, or load receipt is invalid."""


SCHEMA = "arv2-qc-synthetic-input-transport-schema-v1"
STATUS = "synthetic_object_store_fixture_only_not_real_qc_transport"
AUTHORITY = (
    "in_memory_synthetic_transport_contract_only_no_production_input_"
    "outcome_qc_result_deployment_or_trading_authority"
)
INDEX_ENCODING = "canonical_json_strict_utf8_lf-v1"
KEY_PREFIX = "arv2/synthetic/global-input/v1"
TRANSPORT_HASH_DOMAIN = "arv2-qc-synthetic-input-transport-v1"
MAX_KEY_CHARS = 512
MAX_INDEX_BYTES = 1_048_576
MAX_OBJECT_BYTES = 49_000_000
MAX_TOTAL_BYTES = 268_435_456
MAX_JSON_DEPTH = 16
EXPECTED_OBJECT_COUNT = 9
BUNDLE_SOURCE_SHA256 = (
    "cdf24e6bdf3bf63e4635d7524e213f9db25abe308c3973999c1215fb5a4cec18"
)
BUNDLE_SOURCE_BYTE_COUNT = 140_983

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,511}\Z")

EXTERNAL_BINDINGS = (
    ("schema_review_commit", None),
    ("schema_counter_review_commit", None),
    ("data_entitlement_audit_id", None),
    ("vendor_to_qc_processing_rights_receipt_id", None),
    ("production_truth_approval_id", None),
    ("production_global_input_manifest_id", None),
    ("production_global_input_manifest_sha256", None),
    ("owner_production_input_read_authority_id", None),
    ("owner_real_outcome_read_authority_id", None),
    ("owner_qc_object_store_write_authority_id", None),
    ("owner_qc_project_create_authority_id", None),
    ("qc_project_id", None),
    ("qc_object_store_manifest_key", None),
    ("owner_qc_upload_authority_id", None),
    ("qc_upload_receipt_id", None),
    ("owner_qc_compile_authority_id", None),
    ("qc_compile_id", None),
    ("compile_receipt_id", None),
    ("owner_backtest_launch_authority_id", None),
    ("external_evaluation_authority_id", None),
    ("atomic_evaluation_receipt_id", None),
    ("qc_backtest_id_or_ambiguous_submission_lock", None),
    ("result_access_authority_id", None),
    ("result_disposition_authority_id", None),
    ("deployment_authority_id", None),
    ("order_authority_id", None),
    ("trading_authority_id", None),
)

CAPABILITIES = (
    ("filesystem_read", False),
    ("environment_read", False),
    ("provider_access", False),
    ("licensed_input_read", False),
    ("production_input_read", False),
    ("real_outcome_access", False),
    ("qc_object_store_read", False),
    ("qc_object_store_write", False),
    ("qc_project_create", False),
    ("qc_upload", False),
    ("qc_compile", False),
    ("qc_launch", False),
    ("result_access", False),
    ("result_disposition", False),
    ("deployment", False),
    ("orders", False),
    ("trading", False),
)

FALSE_PROPERTY_NAMES = (
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
)


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticObjectStoreEntry:
    key: str
    payload: bytes


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticObjectStoreFixture:
    transport_index_key: str
    entries: tuple[SyntheticObjectStoreEntry, ...]

    @property
    def qc_object_store_read_available(self) -> bool:
        return False

    @property
    def qc_object_store_write_available(self) -> bool:
        return False


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticTransportPartitionBinding:
    ordinal: int
    role: str
    key: str
    byte_count: int
    row_count: int
    artifact_sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticQcTransportLoad:
    transport_id: str
    transport_hash: str
    transport_artifact_sha256: str
    transport_index_key: str
    resolved_fixture_keys: tuple[str, ...]
    bundle: SyntheticQcGlobalInputBundle
    total_object_count: int
    total_byte_count: int
    total_row_count: int
    synthetic_fixture_transport_validated: bool
    real_qc_object_store_access_performed: bool
    external_bindings: tuple[tuple[str, None], ...]
    capabilities: tuple[tuple[str, bool], ...]
    _run_candidate: SyntheticQcRunCandidate = dataclasses.field(repr=False)
    _fixture: SyntheticObjectStoreFixture = dataclasses.field(repr=False)
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


def _canonical_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise QcSyntheticInputTransportError(
            "transport document is not canonical JSON"
        ) from exc


def _schema_seed_document() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "index_encoding": INDEX_ENCODING,
        "key_prefix": KEY_PREFIX,
        "transport_hash_domain": TRANSPORT_HASH_DOMAIN,
        "object_order": (
            "transport_index",
            "global_input_manifest",
            *ROLE_ORDER,
        ),
        "object_count": EXPECTED_OBJECT_COUNT,
        "key_rules": {
            "scope": "logical_relative_suffix_not_a_direct_qc_object_store_key",
            "authorized_adapter_project_namespace_required": True,
            "relative_only": True,
            "unique": True,
            "max_characters": MAX_KEY_CHARS,
            "forbidden_segments": ("", ".", ".."),
            "backslash_forbidden": True,
            "drive_or_uri_syntax_forbidden": True,
            "index_template": (
                "<key_prefix>/<transport_schema_sha256>/<candidate_sha256>/"
                "<bundle_sha256>/"
                "transport-index.json"
            ),
            "manifest_template": (
                "<key_prefix>/<transport_schema_sha256>/<candidate_sha256>/"
                "<bundle_sha256>/manifest/"
                "<manifest_artifact_sha256>.json"
            ),
            "partition_template": (
                "<key_prefix>/<transport_schema_sha256>/<candidate_sha256>/"
                "<bundle_sha256>/partitions/"
                "<two_digit_zero_padded_ordinal>-<hyphenated_role>-"
                "<artifact_sha256>.jsonl"
            ),
        },
        "resource_limits": {
            "scope": "synthetic_fixture_parser_bounds_not_authenticated_qc_quota",
            "max_index_bytes": MAX_INDEX_BYTES,
            "max_object_bytes": MAX_OBJECT_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "max_json_depth": MAX_JSON_DEPTH,
        },
        "parent_bundle": {
            "schema_id": BUNDLE_SCHEMA_ID,
            "schema_sha256": BUNDLE_SCHEMA_SHA256,
            "schema_artifact_sha256": BUNDLE_SCHEMA_ARTIFACT_SHA256,
            "source_sha256": BUNDLE_SOURCE_SHA256,
            "source_byte_count": BUNDLE_SOURCE_BYTE_COUNT,
        },
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
    }


_SCHEMA_SEMANTIC_BYTES = _canonical_bytes(_schema_seed_document())
SCHEMA_SHA256 = (
    "dc34a225af704e3b2a4632108f936a7812d3119ce7b3ce95a3e0f3ea8483c439"
)
SCHEMA_ID = "arv2-qc-synthetic-input-transport-schema-dc34a225af704e3b"
if hashlib.sha256(_SCHEMA_SEMANTIC_BYTES).hexdigest() != SCHEMA_SHA256:
    raise RuntimeError("synthetic transport semantic schema identity changed")


def _schema_document() -> dict[str, object]:
    document = _schema_seed_document()
    document["schema_id"] = SCHEMA_ID
    document["schema_sha256"] = SCHEMA_SHA256
    return document


_SCHEMA_ARTIFACT_BYTES = _canonical_bytes(_schema_document())
SCHEMA_ARTIFACT_SHA256 = (
    "ff0eed2e87de06729b6a2b3d4a35b2cbecaaab2194d4f4d7e84cda0bb48ebe10"
)
if hashlib.sha256(_SCHEMA_ARTIFACT_BYTES).hexdigest() != SCHEMA_ARTIFACT_SHA256:
    raise RuntimeError("synthetic transport schema artifact identity changed")


_PINNED_EXTERNAL_BINDINGS = EXTERNAL_BINDINGS
_PINNED_CAPABILITIES = CAPABILITIES
_PINNED_FALSE_PROPERTY_NAMES = FALSE_PROPERTY_NAMES
_PINNED_ROLE_ORDER = ROLE_ORDER
_PINNED_ENTRY_CLASS = SyntheticObjectStoreEntry
_PINNED_FIXTURE_CLASS = SyntheticObjectStoreFixture
_PINNED_PARTITION_BINDING_CLASS = SyntheticTransportPartitionBinding
_PINNED_RECEIPT_CLASS = SyntheticQcTransportLoad
_PINNED_ERROR_CLASS = QcSyntheticInputTransportError
_PINNED_CANONICAL_BYTES = _canonical_bytes
_PINNED_SCHEMA_SEED_DOCUMENT = _schema_seed_document
_PINNED_SCHEMA_DOCUMENT = _schema_document
_PINNED_SHA256 = hashlib.sha256
_PINNED_JSON_DUMPS = json.dumps
_PINNED_JSON_LOADS = json.loads
_PINNED_REQUIRE_RUN_CANDIDATE = require_synthetic_qc_run_candidate
_PINNED_LOAD_MANIFEST = load_synthetic_qc_global_input_manifest_bytes
_PINNED_LOAD_BUNDLE = load_synthetic_qc_global_input_bundle
_PINNED_REQUIRE_BUNDLE = require_synthetic_qc_global_input_bundle
_PINNED_DATACLASS_FIELDS = dataclasses.fields
_PINNED_DATACLASSES_MODULE = dataclasses
_PINNED_HASHLIB_MODULE = hashlib
_PINNED_INSPECT_MODULE = inspect
_PINNED_JSON_MODULE = json
_PINNED_RE_MODULE = re
_PINNED_HEX_64 = _HEX_64
_PINNED_SAFE_KEY = _SAFE_KEY
_PINNED_PATTERN_TYPE = type(_HEX_64)
_CLASS_MEMBERS = tuple(
    (accepted_class, tuple(vars(accepted_class).items()))
    for accepted_class in (
        SyntheticObjectStoreEntry,
        SyntheticObjectStoreFixture,
        SyntheticTransportPartitionBinding,
        SyntheticQcTransportLoad,
    )
)
_PINNED_CLASS_MEMBERS = _CLASS_MEMBERS
_CLASS_FUNCTION_STATES = tuple(
    (
        accepted_class,
        name,
        value,
        value.__code__,
        value.__defaults__,
        value.__kwdefaults__,
        value.__closure__,
        tuple(
            (cell, type(cell.cell_contents), cell.cell_contents)
            for cell in (value.__closure__ or ())
        ),
    )
    for accepted_class, members in _CLASS_MEMBERS
    for name, value in members
    if inspect.isfunction(value)
)
_PINNED_CLASS_FUNCTION_STATES = _CLASS_FUNCTION_STATES
_FALSE_PROPERTY_TOPOLOGY = tuple(
    (
        accepted_class,
        name,
        vars(accepted_class)[name],
        vars(accepted_class)[name].fget,
        vars(accepted_class)[name].fget.__code__,
    )
    for accepted_class, names in (
        (
            SyntheticObjectStoreFixture,
            (
                "qc_object_store_read_available",
                "qc_object_store_write_available",
            ),
        ),
        (SyntheticQcTransportLoad, FALSE_PROPERTY_NAMES),
    )
    for name in names
)
_PINNED_FALSE_PROPERTY_TOPOLOGY = _FALSE_PROPERTY_TOPOLOGY


def _require_static_contract() -> None:
    if (
        _BUILTIN_RESOLUTION_BINDINGS
        is not _PINNED_BUILTIN_RESOLUTION_BINDINGS
        or _BUILTIN_GLOBALS is not _PINNED_BUILTIN_GLOBALS
        or _BUILTIN_GLOBAL_ENTRIES is not _PINNED_BUILTIN_GLOBAL_ENTRIES
        or _LOCAL_MODULE_GLOBALS is not _PINNED_LOCAL_MODULE_GLOBALS
    ):
        raise _PINNED_ERROR_CLASS("synthetic transport builtin topology changed")
    builtin_entry_count = 0
    for actual_key, actual_value in _PINNED_BUILTIN_GLOBALS.items():
        builtin_entry_count += 1
        matched = False
        for expected_key, expected_value in _PINNED_BUILTIN_GLOBAL_ENTRIES:
            if actual_key is expected_key:
                matched = actual_value is expected_value
                break
        if not matched:
            raise _PINNED_ERROR_CLASS(
                "synthetic transport builtin topology changed"
            )
    expected_builtin_entry_count = 0
    for _ in _PINNED_BUILTIN_GLOBAL_ENTRIES:
        expected_builtin_entry_count += 1
    if builtin_entry_count != expected_builtin_entry_count:
        raise _PINNED_ERROR_CLASS("synthetic transport builtin topology changed")
    if (
        _PINNED_BUILTIN_GLOBALS.get("any") is not _PINNED_ANY
        or _PINNED_BUILTIN_GLOBALS.get("dict") is not _PINNED_DICT
        or _PINNED_BUILTIN_GLOBALS.get("dict").get is not _PINNED_DICT_GET
        or _PINNED_BUILTIN_GLOBALS.get("dict").items is not _PINNED_DICT_ITEMS
        or _PINNED_BUILTIN_GLOBALS.get("id") is not _PINNED_ID
        or _PINNED_BUILTIN_GLOBALS.get("len") is not _PINNED_LEN
        or _PINNED_BUILTIN_GLOBALS.get("list") is not _PINNED_LIST
        or _PINNED_BUILTIN_GLOBALS.get("object") is not _PINNED_OBJECT
        or _PINNED_BUILTIN_GLOBALS.get("set") is not _PINNED_SET
        or _PINNED_BUILTIN_GLOBALS.get("str") is not _PINNED_STR
        or _PINNED_BUILTIN_GLOBALS.get("tuple") is not _PINNED_TUPLE
        or _PINNED_BUILTIN_GLOBALS.get("type") is not _PINNED_TYPE
        or _PINNED_BUILTIN_GLOBALS.get("zip") is not _PINNED_ZIP
    ):
        raise _PINNED_ERROR_CLASS("synthetic transport builtin topology changed")
    for function_globals, name, expected in _BUILTIN_RESOLUTION_BINDINGS:
        if _PINNED_ANY(
            _PINNED_TYPE(actual_name) is not _PINNED_STR
            or actual_name is name
            or actual_name == name
            for actual_name in function_globals
        ) or _PINNED_DICT_GET(_PINNED_BUILTIN_GLOBALS, name) is not expected:
            raise _PINNED_ERROR_CLASS(
                "synthetic transport builtin topology changed"
            )
    scalar_expectations = (
        (SCHEMA, "arv2-qc-synthetic-input-transport-schema-v1"),
        (STATUS, "synthetic_object_store_fixture_only_not_real_qc_transport"),
        (
            AUTHORITY,
            "in_memory_synthetic_transport_contract_only_no_production_input_"
            "outcome_qc_result_deployment_or_trading_authority",
        ),
        (INDEX_ENCODING, "canonical_json_strict_utf8_lf-v1"),
        (KEY_PREFIX, "arv2/synthetic/global-input/v1"),
        (TRANSPORT_HASH_DOMAIN, "arv2-qc-synthetic-input-transport-v1"),
        (
            BUNDLE_SOURCE_SHA256,
            "cdf24e6bdf3bf63e4635d7524e213f9db25abe308c3973999c1215fb5a4cec18",
        ),
        (
            SCHEMA_SHA256,
            "dc34a225af704e3b2a4632108f936a7812d3119ce7b3ce95a3e0f3ea8483c439",
        ),
        (SCHEMA_ID, "arv2-qc-synthetic-input-transport-schema-dc34a225af704e3b"),
        (
            SCHEMA_ARTIFACT_SHA256,
            "ff0eed2e87de06729b6a2b3d4a35b2cbecaaab2194d4f4d7e84cda0bb48ebe10",
        ),
    )
    integer_expectations = (
        (MAX_KEY_CHARS, 512),
        (MAX_INDEX_BYTES, 1_048_576),
        (MAX_OBJECT_BYTES, 49_000_000),
        (MAX_TOTAL_BYTES, 268_435_456),
        (MAX_JSON_DEPTH, 16),
        (EXPECTED_OBJECT_COUNT, 9),
        (BUNDLE_SOURCE_BYTE_COUNT, 140_983),
    )
    if any(
        type(actual) is not str or actual != expected
        for actual, expected in scalar_expectations
    ):
        raise _PINNED_ERROR_CLASS("synthetic transport static contract changed")
    if any(
        type(actual) is not int or actual != expected
        for actual, expected in integer_expectations
    ):
        raise _PINNED_ERROR_CLASS("synthetic transport resource contract changed")
    if (
        EXTERNAL_BINDINGS is not _PINNED_EXTERNAL_BINDINGS
        or CAPABILITIES is not _PINNED_CAPABILITIES
        or FALSE_PROPERTY_NAMES is not _PINNED_FALSE_PROPERTY_NAMES
        or ROLE_ORDER is not _PINNED_ROLE_ORDER
        or SyntheticObjectStoreEntry is not _PINNED_ENTRY_CLASS
        or SyntheticObjectStoreFixture is not _PINNED_FIXTURE_CLASS
        or SyntheticTransportPartitionBinding is not _PINNED_PARTITION_BINDING_CLASS
        or SyntheticQcTransportLoad is not _PINNED_RECEIPT_CLASS
        or QcSyntheticInputTransportError is not _PINNED_ERROR_CLASS
        or dataclasses is not _PINNED_DATACLASSES_MODULE
        or hashlib is not _PINNED_HASHLIB_MODULE
        or inspect is not _PINNED_INSPECT_MODULE
        or json is not _PINNED_JSON_MODULE
        or re is not _PINNED_RE_MODULE
        or _canonical_bytes is not _PINNED_CANONICAL_BYTES
        or _schema_seed_document is not _PINNED_SCHEMA_SEED_DOCUMENT
        or _schema_document is not _PINNED_SCHEMA_DOCUMENT
        or hashlib.sha256 is not _PINNED_SHA256
        or json.dumps is not _PINNED_JSON_DUMPS
        or json.loads is not _PINNED_JSON_LOADS
        or require_synthetic_qc_run_candidate is not _PINNED_REQUIRE_RUN_CANDIDATE
        or load_synthetic_qc_global_input_manifest_bytes is not _PINNED_LOAD_MANIFEST
        or load_synthetic_qc_global_input_bundle is not _PINNED_LOAD_BUNDLE
        or require_synthetic_qc_global_input_bundle is not _PINNED_REQUIRE_BUNDLE
        or dataclasses.fields is not _PINNED_DATACLASS_FIELDS
        or _HEX_64 is not _PINNED_HEX_64
        or _SAFE_KEY is not _PINNED_SAFE_KEY
        or type(_HEX_64) is not _PINNED_PATTERN_TYPE
        or type(_SAFE_KEY) is not _PINNED_PATTERN_TYPE
        or _HEX_64.pattern != r"[0-9a-f]{64}\Z"
        or _SAFE_KEY.pattern != r"[A-Za-z0-9][A-Za-z0-9._/-]{0,511}\Z"
        or _HEX_64.flags != 32
        or _SAFE_KEY.flags != 32
        or _CLASS_MEMBERS is not _PINNED_CLASS_MEMBERS
        or _CLASS_FUNCTION_STATES is not _PINNED_CLASS_FUNCTION_STATES
        or _FALSE_PROPERTY_TOPOLOGY is not _PINNED_FALSE_PROPERTY_TOPOLOGY
    ):
        raise _PINNED_ERROR_CLASS("synthetic transport static topology changed")
    for accepted_class, expected_members in _CLASS_MEMBERS:
        actual_members = vars(accepted_class)
        if len(actual_members) != len(expected_members) or any(
            actual_members.get(name) is not expected
            for name, expected in expected_members
        ):
            raise _PINNED_ERROR_CLASS("synthetic transport class topology changed")
    for (
        accepted_class,
        name,
        expected_function,
        expected_code,
        expected_defaults,
        expected_kwdefaults,
        expected_closure,
        expected_closure_state,
    ) in _CLASS_FUNCTION_STATES:
        actual_function = vars(accepted_class).get(name)
        try:
            closure_state_changed = len(expected_closure_state) != len(
                actual_function.__closure__ or ()
            ) or any(
                actual_cell is not expected_cell
                or type(actual_cell.cell_contents) is not expected_type
                or actual_cell.cell_contents is not expected_contents
                for actual_cell, (
                    expected_cell,
                    expected_type,
                    expected_contents,
                ) in zip(
                    actual_function.__closure__ or (),
                    expected_closure_state,
                    strict=True,
                )
            )
        except (AttributeError, TypeError, ValueError):
            closure_state_changed = True
        if (
            actual_function is not expected_function
            or actual_function.__code__ is not expected_code
            or actual_function.__defaults__ is not expected_defaults
            or actual_function.__kwdefaults__ is not expected_kwdefaults
            or actual_function.__closure__ is not expected_closure
            or closure_state_changed
        ):
            raise _PINNED_ERROR_CLASS(
                "synthetic transport class function state changed"
            )
    for accepted_class, name, expected_property, expected_fget, expected_code in (
        _FALSE_PROPERTY_TOPOLOGY
    ):
        actual_property = vars(accepted_class).get(name)
        if (
            type(actual_property) is not property
            or actual_property is not expected_property
            or actual_property.fget is not expected_fget
            or actual_property.fget.__code__ is not expected_code
        ):
            raise _PINNED_ERROR_CLASS("synthetic transport authority topology changed")
    expected_field_names = (
        (SyntheticObjectStoreEntry, ("key", "payload")),
        (SyntheticObjectStoreFixture, ("transport_index_key", "entries")),
        (
            SyntheticTransportPartitionBinding,
            ("ordinal", "role", "key", "byte_count", "row_count", "artifact_sha256"),
        ),
        (
            SyntheticQcTransportLoad,
            (
                "transport_id",
                "transport_hash",
                "transport_artifact_sha256",
                "transport_index_key",
                "resolved_fixture_keys",
                "bundle",
                "total_object_count",
                "total_byte_count",
                "total_row_count",
                "synthetic_fixture_transport_validated",
                "real_qc_object_store_access_performed",
                "external_bindings",
                "capabilities",
                "_run_candidate",
                "_fixture",
                "_canonical_document",
            ),
        ),
    )
    if any(
        tuple(field.name for field in _PINNED_DATACLASS_FIELDS(accepted_class))
        != field_names
        for accepted_class, field_names in expected_field_names
    ):
        raise _PINNED_ERROR_CLASS("synthetic transport dataclass topology changed")
    if (
        type(EXTERNAL_BINDINGS) is not tuple
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or item[1] is not None
            for item in EXTERNAL_BINDINGS
        )
        or type(CAPABILITIES) is not tuple
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or item[1] is not False
            for item in CAPABILITIES
        )
        or type(FALSE_PROPERTY_NAMES) is not tuple
        or any(type(item) is not str for item in FALSE_PROPERTY_NAMES)
        or ROLE_ORDER
        != (
            "session_axis",
            "decision_rows",
            "security_open_values",
            "benchmark_open_values",
            "security_lifecycle_coverages",
            "terminal_requirements",
            "terminal_shareholder_payoffs",
        )
    ):
        raise _PINNED_ERROR_CLASS("synthetic transport registry changed")
    semantic = _PINNED_CANONICAL_BYTES(_PINNED_SCHEMA_SEED_DOCUMENT())
    artifact = _PINNED_CANONICAL_BYTES(_PINNED_SCHEMA_DOCUMENT())
    if (
        _PINNED_SHA256(semantic).hexdigest() != SCHEMA_SHA256
        or _PINNED_SHA256(artifact).hexdigest() != SCHEMA_ARTIFACT_SHA256
    ):
        raise _PINNED_ERROR_CLASS("synthetic transport schema identity changed")
    if (
        _LOCAL_MODULE_GLOBALS is not _PINNED_LOCAL_MODULE_GLOBALS
        or _LOCAL_FUNCTION_STATES is not _PINNED_LOCAL_FUNCTION_STATES
    ):
        raise _PINNED_ERROR_CLASS("synthetic transport callable graph changed")
    for (
        name,
        expected_function,
        expected_code,
        expected_defaults,
        expected_kwdefaults,
        expected_closure,
        expected_closure_state,
    ) in _LOCAL_FUNCTION_STATES:
        actual_function = _PINNED_LOCAL_MODULE_GLOBALS.get(name)
        try:
            closure_state_changed = len(expected_closure_state) != len(
                actual_function.__closure__ or ()
            ) or any(
                actual_cell is not expected_cell
                or type(actual_cell.cell_contents) is not expected_type
                or actual_cell.cell_contents is not expected_contents
                for actual_cell, (
                    expected_cell,
                    expected_type,
                    expected_contents,
                ) in zip(
                    actual_function.__closure__ or (),
                    expected_closure_state,
                    strict=True,
                )
            )
        except (AttributeError, TypeError, ValueError):
            closure_state_changed = True
        if (
            actual_function is not expected_function
            or actual_function.__code__ is not expected_code
            or actual_function.__defaults__ is not expected_defaults
            or actual_function.__kwdefaults__ is not expected_kwdefaults
            or actual_function.__closure__ is not expected_closure
            or closure_state_changed
        ):
            raise _PINNED_ERROR_CLASS(
                "synthetic transport callable graph changed"
            )


def render_qc_synthetic_input_transport_schema_bytes() -> bytes:
    """Return the canonical synthetic transport schema declaration."""

    _require_static_contract()
    payload = _canonical_bytes(_schema_document())
    if (
        hashlib.sha256(_canonical_bytes(_schema_seed_document())).hexdigest()
        != SCHEMA_SHA256
        or hashlib.sha256(payload).hexdigest() != SCHEMA_ARTIFACT_SHA256
    ):
        raise QcSyntheticInputTransportError(
            "synthetic transport schema identity changed"
        )
    return payload


def _require_sha256(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise QcSyntheticInputTransportError(
            f"{name} must be a lowercase SHA-256"
        )
    return value


def _require_nonempty_string(value: object, name: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise QcSyntheticInputTransportError(
            f"{name} must be a nonempty canonical string"
        )
    return value


def _require_nonnegative_int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise QcSyntheticInputTransportError(
            f"{name} must be a nonnegative exact integer"
        )
    return value


def _require_safe_key(value: object, name: str) -> str:
    if type(value) is not str or _SAFE_KEY.fullmatch(value) is None:
        raise QcSyntheticInputTransportError(
            f"{name} is not a safe relative object key"
        )
    if (
        "\\" in value
        or ":" in value
        or value.startswith("/")
        or value.endswith("/")
        or any(segment in ("", ".", "..") for segment in value.split("/"))
    ):
        raise QcSyntheticInputTransportError(
            f"{name} is not a safe relative object key"
        )
    return value


def _reject_duplicate_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise QcSyntheticInputTransportError(
                "transport index contains a duplicate key"
            )
        value[key] = item
    return value


def _reject_number(_: str) -> object:
    raise QcSyntheticInputTransportError(
        "transport index numbers must be exact integers"
    )


def _require_exact_json_tree(value: object, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise QcSyntheticInputTransportError(
            "transport index exceeds the maximum JSON depth"
        )
    if value is None or type(value) in (str, int, bool):
        return
    if type(value) is list:
        for item in value:
            _require_exact_json_tree(item, depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise QcSyntheticInputTransportError(
                    "transport index keys must be exact strings"
                )
            _require_exact_json_tree(item, depth + 1)
        return
    raise QcSyntheticInputTransportError(
        "transport index contains a noncanonical value"
    )


def _parse_index(payload: object) -> dict[str, object]:
    if type(payload) is not bytes:
        raise QcSyntheticInputTransportError(
            "transport index payload must be exact bytes"
        )
    if len(payload) > MAX_INDEX_BYTES:
        raise QcSyntheticInputTransportError("transport index is too large")
    if (
        payload.startswith(b"\xef\xbb\xbf")
        or not payload.endswith(b"\n")
        or payload.count(b"\n") != 1
        or b"\r" in payload
    ):
        raise QcSyntheticInputTransportError(
            "transport index must be canonical UTF-8 JSON with one LF"
        )
    try:
        text = payload[:-1].decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
        _require_exact_json_tree(value)
    except QcSyntheticInputTransportError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise QcSyntheticInputTransportError(
            "transport index is not valid bounded canonical JSON"
        ) from exc
    if type(value) is not dict or _canonical_bytes(value) != payload:
        raise QcSyntheticInputTransportError(
            "transport index bytes are not canonical"
        )
    return value


def _require_fields(
    value: object,
    fields: tuple[str, ...],
    name: str,
) -> dict[str, object]:
    if type(value) is not dict or tuple(sorted(value)) != tuple(sorted(fields)):
        raise QcSyntheticInputTransportError(f"{name} fields changed")
    return value


def _partition_document(
    value: SyntheticTransportPartitionBinding,
) -> dict[str, object]:
    return {
        "ordinal": value.ordinal,
        "role": value.role,
        "key": value.key,
        "byte_count": value.byte_count,
        "row_count": value.row_count,
        "artifact_sha256": value.artifact_sha256,
    }


def _transport_seed_document(
    *,
    run_candidate: SyntheticQcRunCandidate,
    manifest: SyntheticQcGlobalInputManifest,
    bundle: SyntheticQcGlobalInputBundle,
    index_key: str,
    manifest_key: str,
    manifest_byte_count: int,
    partitions: tuple[SyntheticTransportPartitionBinding, ...],
) -> dict[str, object]:
    referenced_byte_count = manifest_byte_count + sum(
        item.byte_count for item in partitions
    )
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "transport_id": None,
        "transport_hash": None,
        "schema_binding": {
            "schema_id": SCHEMA_ID,
            "schema_sha256": SCHEMA_SHA256,
            "schema_artifact_sha256": SCHEMA_ARTIFACT_SHA256,
        },
        "bundle_contract_binding": {
            "schema_id": BUNDLE_SCHEMA_ID,
            "schema_sha256": BUNDLE_SCHEMA_SHA256,
            "schema_artifact_sha256": BUNDLE_SCHEMA_ARTIFACT_SHA256,
            "source_sha256": BUNDLE_SOURCE_SHA256,
            "source_byte_count": BUNDLE_SOURCE_BYTE_COUNT,
        },
        "run_candidate_binding": {
            "candidate_id": run_candidate.candidate_id,
            "candidate_hash": run_candidate.candidate_hash,
        },
        "manifest_binding": {
            "manifest_id": manifest.manifest_id,
            "manifest_sha256": manifest.manifest_sha256,
            "manifest_artifact_sha256": manifest.manifest_artifact_sha256,
            "key": manifest_key,
            "byte_count": manifest_byte_count,
        },
        "bundle_binding": {
            "bundle_id": bundle.bundle_id,
            "bundle_hash": bundle.bundle_hash,
            "bundle_artifact_sha256": bundle.bundle_artifact_sha256,
        },
        "layout": {
            "index_key": index_key,
            "object_order": [
                "transport_index",
                "global_input_manifest",
                *ROLE_ORDER,
            ],
        },
        "partitions": [_partition_document(item) for item in partitions],
        "referenced_census": {
            "object_count": 8,
            "partition_count": len(partitions),
            "total_byte_count": referenced_byte_count,
            "total_row_count": bundle.total_row_count,
        },
        "truth_state": {
            "synthetic_fixture_transport": True,
            "real_qc_object_store_access_performed": False,
            "runtime_code_authenticated": False,
            "production_truth_authenticated": False,
            "rights_authenticated": False,
            "point_in_time_provenance_authenticated": False,
            "real_outcome_authority": False,
        },
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
    }


def _finalize_transport_document(seed: dict[str, object]) -> dict[str, object]:
    semantic = _canonical_bytes(seed)
    transport_hash = hashlib.sha256(
        TRANSPORT_HASH_DOMAIN.encode("ascii") + b"\x00" + semantic
    ).hexdigest()
    document = dict(seed)
    document["transport_id"] = f"arv2-qc-synthetic-transport-{transport_hash[:16]}"
    document["transport_hash"] = transport_hash
    return document


def _copy_fixture(value: SyntheticObjectStoreFixture) -> SyntheticObjectStoreFixture:
    return SyntheticObjectStoreFixture(
        transport_index_key=value.transport_index_key,
        entries=tuple(
            SyntheticObjectStoreEntry(key=item.key, payload=bytes(item.payload))
            for item in value.entries
        ),
    )


def _require_fixture_shape(value: object) -> SyntheticObjectStoreFixture:
    if type(value) is not SyntheticObjectStoreFixture:
        raise QcSyntheticInputTransportError(
            "only the exact synthetic Object Store fixture is accepted"
        )
    try:
        transport_index_key = value.transport_index_key
        entries = value.entries
    except AttributeError as exc:
        raise QcSyntheticInputTransportError(
            "synthetic fixture topology changed"
        ) from exc
    if type(transport_index_key) is not str or type(entries) is not tuple:
        raise QcSyntheticInputTransportError("synthetic fixture topology changed")
    _require_safe_key(transport_index_key, "transport_index_key")
    if len(entries) != EXPECTED_OBJECT_COUNT:
        raise QcSyntheticInputTransportError(
            "synthetic fixture must contain exactly nine objects"
        )
    keys: list[str] = []
    total = 0
    for entry in entries:
        if type(entry) is not SyntheticObjectStoreEntry:
            raise QcSyntheticInputTransportError(
                "synthetic fixture entries changed type"
            )
        try:
            entry_key = entry.key
            payload = entry.payload
        except AttributeError as exc:
            raise QcSyntheticInputTransportError(
                "synthetic fixture entry topology changed"
            ) from exc
        key = _require_safe_key(entry_key, "object key")
        if type(payload) is not bytes:
            raise QcSyntheticInputTransportError(
                "synthetic fixture payloads must be exact bytes"
            )
        if len(payload) > MAX_OBJECT_BYTES:
            raise QcSyntheticInputTransportError(
                "synthetic fixture object is too large"
            )
        keys.append(key)
        total += len(payload)
    if len(set(keys)) != EXPECTED_OBJECT_COUNT:
        raise QcSyntheticInputTransportError(
            "synthetic fixture object keys must be unique"
        )
    if total > MAX_TOTAL_BYTES:
        raise QcSyntheticInputTransportError(
            "synthetic fixture exceeds the total byte limit"
        )
    if keys[0] != transport_index_key:
        raise QcSyntheticInputTransportError(
            "transport index must be the first fixture object"
        )
    return value


def build_synthetic_qc_object_store_fixture(
    *,
    run_candidate: SyntheticQcRunCandidate,
    manifest_bytes: bytes,
    partition_payloads: tuple[SyntheticGlobalInputPartitionPayload, ...],
) -> SyntheticObjectStoreFixture:
    """Build the exact nine-object in-memory fixture for one B2 bundle."""

    _require_static_contract()
    try:
        require_synthetic_qc_run_candidate(run_candidate)
        manifest = load_synthetic_qc_global_input_manifest_bytes(
            manifest_bytes,
            run_candidate=run_candidate,
        )
        bundle = load_synthetic_qc_global_input_bundle(
            run_candidate=run_candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )
    except (
        QcRunContractError,
        QcGlobalInputSchemaError,
        QcGlobalInputBundleError,
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:
        raise QcSyntheticInputTransportError(
            "synthetic transport parents are not authenticated"
        ) from exc
    if type(partition_payloads) is not tuple or len(partition_payloads) != len(
        ROLE_ORDER
    ):
        raise QcSyntheticInputTransportError(
            "partition payload inventory is not complete and exact"
        )
    payload_by_role: dict[str, bytes] = {}
    for expected_role, payload in zip(ROLE_ORDER, partition_payloads, strict=True):
        if (
            type(payload) is not SyntheticGlobalInputPartitionPayload
            or payload.role != expected_role
            or type(payload.payload) is not bytes
        ):
            raise QcSyntheticInputTransportError(
                "partition payload inventory is not complete and exact"
            )
        payload_by_role[expected_role] = payload.payload
    base = (
        f"{KEY_PREFIX}/{SCHEMA_SHA256}/{run_candidate.candidate_hash}/"
        f"{bundle.bundle_hash}"
    )
    index_key = f"{base}/transport-index.json"
    manifest_key = (
        f"{base}/manifest/{manifest.manifest_artifact_sha256}.json"
    )
    bindings = tuple(
        SyntheticTransportPartitionBinding(
            ordinal=ordinal,
            role=descriptor.role,
            key=(
                f"{base}/partitions/{ordinal:02d}-"
                f"{descriptor.role.replace('_', '-')}-"
                f"{descriptor.artifact_sha256}.jsonl"
            ),
            byte_count=descriptor.byte_count,
            row_count=descriptor.row_count,
            artifact_sha256=descriptor.artifact_sha256,
        )
        for ordinal, descriptor in enumerate(manifest.partitions, start=1)
    )
    seed = _transport_seed_document(
        run_candidate=run_candidate,
        manifest=manifest,
        bundle=bundle,
        index_key=index_key,
        manifest_key=manifest_key,
        manifest_byte_count=len(manifest_bytes),
        partitions=bindings,
    )
    index_bytes = _canonical_bytes(_finalize_transport_document(seed))
    fixture = SyntheticObjectStoreFixture(
        transport_index_key=index_key,
        entries=(
            SyntheticObjectStoreEntry(key=index_key, payload=index_bytes),
            SyntheticObjectStoreEntry(
                key=manifest_key,
                payload=bytes(manifest_bytes),
            ),
            *tuple(
                SyntheticObjectStoreEntry(
                    key=binding.key,
                    payload=bytes(payload_by_role[binding.role]),
                )
                for binding in bindings
            ),
        ),
    )
    _require_fixture_shape(fixture)
    return fixture


def _parse_transport_contract(
    payload: bytes,
) -> tuple[dict[str, object], tuple[SyntheticTransportPartitionBinding, ...]]:
    value = _parse_index(payload)
    root_fields = (
        "schema",
        "status",
        "authority",
        "transport_id",
        "transport_hash",
        "schema_binding",
        "bundle_contract_binding",
        "run_candidate_binding",
        "manifest_binding",
        "bundle_binding",
        "layout",
        "partitions",
        "referenced_census",
        "truth_state",
        "external_bindings",
        "capabilities",
    )
    _require_fields(value, root_fields, "transport index")
    if (
        value["schema"] != SCHEMA
        or value["status"] != STATUS
        or value["authority"] != AUTHORITY
    ):
        raise QcSyntheticInputTransportError("transport index authority changed")
    schema_binding = _require_fields(
        value["schema_binding"],
        ("schema_id", "schema_sha256", "schema_artifact_sha256"),
        "transport schema binding",
    )
    if schema_binding != {
        "schema_id": SCHEMA_ID,
        "schema_sha256": SCHEMA_SHA256,
        "schema_artifact_sha256": SCHEMA_ARTIFACT_SHA256,
    }:
        raise QcSyntheticInputTransportError("transport schema binding changed")
    bundle_contract = _require_fields(
        value["bundle_contract_binding"],
        (
            "schema_id",
            "schema_sha256",
            "schema_artifact_sha256",
            "source_sha256",
            "source_byte_count",
        ),
        "bundle contract binding",
    )
    if bundle_contract != {
        "schema_id": BUNDLE_SCHEMA_ID,
        "schema_sha256": BUNDLE_SCHEMA_SHA256,
        "schema_artifact_sha256": BUNDLE_SCHEMA_ARTIFACT_SHA256,
        "source_sha256": BUNDLE_SOURCE_SHA256,
        "source_byte_count": BUNDLE_SOURCE_BYTE_COUNT,
    }:
        raise QcSyntheticInputTransportError("bundle contract binding changed")
    run_binding = _require_fields(
        value["run_candidate_binding"],
        ("candidate_id", "candidate_hash"),
        "run candidate binding",
    )
    _require_nonempty_string(run_binding["candidate_id"], "candidate_id")
    _require_sha256(run_binding["candidate_hash"], "candidate_hash")
    manifest_binding = _require_fields(
        value["manifest_binding"],
        (
            "manifest_id",
            "manifest_sha256",
            "manifest_artifact_sha256",
            "key",
            "byte_count",
        ),
        "manifest binding",
    )
    _require_nonempty_string(manifest_binding["manifest_id"], "manifest_id")
    _require_sha256(manifest_binding["manifest_sha256"], "manifest_sha256")
    _require_sha256(
        manifest_binding["manifest_artifact_sha256"],
        "manifest_artifact_sha256",
    )
    _require_safe_key(manifest_binding["key"], "manifest key")
    _require_nonnegative_int(manifest_binding["byte_count"], "manifest byte_count")
    bundle_binding = _require_fields(
        value["bundle_binding"],
        ("bundle_id", "bundle_hash", "bundle_artifact_sha256"),
        "bundle binding",
    )
    _require_nonempty_string(bundle_binding["bundle_id"], "bundle_id")
    _require_sha256(bundle_binding["bundle_hash"], "bundle_hash")
    _require_sha256(
        bundle_binding["bundle_artifact_sha256"],
        "bundle_artifact_sha256",
    )
    layout = _require_fields(
        value["layout"],
        ("index_key", "object_order"),
        "transport layout",
    )
    _require_safe_key(layout["index_key"], "index key")
    if layout["object_order"] != [
        "transport_index",
        "global_input_manifest",
        *ROLE_ORDER,
    ]:
        raise QcSyntheticInputTransportError("transport object order changed")
    raw_partitions = value["partitions"]
    if type(raw_partitions) is not list or len(raw_partitions) != len(ROLE_ORDER):
        raise QcSyntheticInputTransportError("transport partitions are incomplete")
    bindings: list[SyntheticTransportPartitionBinding] = []
    for ordinal, (role, raw) in enumerate(
        zip(ROLE_ORDER, raw_partitions, strict=True),
        start=1,
    ):
        item = _require_fields(
            raw,
            ("ordinal", "role", "key", "byte_count", "row_count", "artifact_sha256"),
            "transport partition",
        )
        if (
            type(item["ordinal"]) is not int
            or item["ordinal"] != ordinal
            or type(item["role"]) is not str
            or item["role"] != role
        ):
            raise QcSyntheticInputTransportError(
                "transport partition role order changed"
            )
        bindings.append(
            SyntheticTransportPartitionBinding(
                ordinal=ordinal,
                role=role,
                key=_require_safe_key(item["key"], "partition key"),
                byte_count=_require_nonnegative_int(
                    item["byte_count"], "partition byte_count"
                ),
                row_count=_require_nonnegative_int(
                    item["row_count"], "partition row_count"
                ),
                artifact_sha256=_require_sha256(
                    item["artifact_sha256"], "partition artifact_sha256"
                ),
            )
        )
    census = _require_fields(
        value["referenced_census"],
        ("object_count", "partition_count", "total_byte_count", "total_row_count"),
        "referenced census",
    )
    object_count = _require_nonnegative_int(
        census["object_count"], "referenced object_count"
    )
    partition_count = _require_nonnegative_int(
        census["partition_count"], "referenced partition_count"
    )
    total_byte_count = _require_nonnegative_int(
        census["total_byte_count"], "referenced total_byte_count"
    )
    total_row_count = _require_nonnegative_int(
        census["total_row_count"], "referenced total_row_count"
    )
    if (
        object_count != 8
        or partition_count != len(ROLE_ORDER)
        or total_byte_count
        != manifest_binding["byte_count"] + sum(item.byte_count for item in bindings)
        or total_row_count != sum(item.row_count for item in bindings)
    ):
        raise QcSyntheticInputTransportError("transport census changed")
    truth = _require_fields(
        value["truth_state"],
        (
            "synthetic_fixture_transport",
            "real_qc_object_store_access_performed",
            "runtime_code_authenticated",
            "production_truth_authenticated",
            "rights_authenticated",
            "point_in_time_provenance_authenticated",
            "real_outcome_authority",
        ),
        "transport truth state",
    )
    if (
        truth["synthetic_fixture_transport"] is not True
        or truth["real_qc_object_store_access_performed"] is not False
        or truth["runtime_code_authenticated"] is not False
        or truth["production_truth_authenticated"] is not False
        or truth["rights_authenticated"] is not False
        or truth["point_in_time_provenance_authenticated"] is not False
        or truth["real_outcome_authority"] is not False
    ):
        raise QcSyntheticInputTransportError("transport truth state changed")
    external_bindings = _require_fields(
        value["external_bindings"],
        tuple(name for name, _ in EXTERNAL_BINDINGS),
        "transport external bindings",
    )
    capabilities = _require_fields(
        value["capabilities"],
        tuple(name for name, _ in CAPABILITIES),
        "transport capabilities",
    )
    if (
        any(external_bindings[name] is not None for name, _ in EXTERNAL_BINDINGS)
        or any(capabilities[name] is not False for name, _ in CAPABILITIES)
    ):
        raise QcSyntheticInputTransportError("transport authority changed")
    transport_id = _require_nonempty_string(value["transport_id"], "transport_id")
    transport_hash = _require_sha256(value["transport_hash"], "transport_hash")
    seed = dict(value)
    seed["transport_id"] = None
    seed["transport_hash"] = None
    expected_hash = hashlib.sha256(
        TRANSPORT_HASH_DOMAIN.encode("ascii")
        + b"\x00"
        + _canonical_bytes(seed)
    ).hexdigest()
    if (
        transport_hash != expected_hash
        or transport_id != f"arv2-qc-synthetic-transport-{expected_hash[:16]}"
    ):
        raise QcSyntheticInputTransportError("transport identity changed")
    expected_base = (
        f"{KEY_PREFIX}/{SCHEMA_SHA256}/{run_binding['candidate_hash']}/"
        f"{bundle_binding['bundle_hash']}"
    )
    expected_index_key = f"{expected_base}/transport-index.json"
    expected_manifest_key = (
        f"{expected_base}/manifest/"
        f"{manifest_binding['manifest_artifact_sha256']}.json"
    )
    expected_partition_keys = tuple(
        f"{expected_base}/partitions/{item.ordinal:02d}-"
        f"{item.role.replace('_', '-')}-{item.artifact_sha256}.jsonl"
        for item in bindings
    )
    if (
        layout["index_key"] != expected_index_key
        or manifest_binding["key"] != expected_manifest_key
        or tuple(item.key for item in bindings) != expected_partition_keys
    ):
        raise QcSyntheticInputTransportError(
            "transport keys do not match the content-addressed layout"
        )
    all_keys = (
        layout["index_key"],
        manifest_binding["key"],
        *(item.key for item in bindings),
    )
    if len(set(all_keys)) != EXPECTED_OBJECT_COUNT:
        raise QcSyntheticInputTransportError("transport keys are not unique")
    return value, tuple(bindings)


def load_synthetic_qc_global_input_bundle_from_object_store_fixture(
    *,
    run_candidate: SyntheticQcRunCandidate,
    object_store: SyntheticObjectStoreFixture,
    transport_index_key: str,
) -> SyntheticQcTransportLoad:
    """Resolve one exact synthetic fixture and feed its bytes to reviewed B2."""

    _require_static_contract()
    fixture = _require_fixture_shape(object_store)
    index_key = _require_safe_key(transport_index_key, "transport_index_key")
    if index_key != fixture.transport_index_key:
        raise QcSyntheticInputTransportError("transport index key changed")
    try:
        require_synthetic_qc_run_candidate(run_candidate)
    except QcRunContractError as exc:
        raise QcSyntheticInputTransportError(
            "run candidate is not authenticated"
        ) from exc
    index_entry = fixture.entries[0]
    document, bindings = _parse_transport_contract(index_entry.payload)
    layout = document["layout"]
    manifest_binding = document["manifest_binding"]
    run_binding = document["run_candidate_binding"]
    bundle_binding = document["bundle_binding"]
    if layout["index_key"] != index_key:
        raise QcSyntheticInputTransportError("transport index layout changed")
    if (
        run_binding["candidate_id"] != run_candidate.candidate_id
        or run_binding["candidate_hash"] != run_candidate.candidate_hash
    ):
        raise QcSyntheticInputTransportError("run candidate lineage changed")
    expected_keys = (
        index_key,
        manifest_binding["key"],
        *(item.key for item in bindings),
    )
    actual_keys = tuple(item.key for item in fixture.entries)
    if actual_keys != expected_keys:
        raise QcSyntheticInputTransportError(
            "synthetic fixture object order or inventory changed"
        )
    manifest_payload = fixture.entries[1].payload
    if (
        len(manifest_payload) != manifest_binding["byte_count"]
        or hashlib.sha256(manifest_payload).hexdigest()
        != manifest_binding["manifest_artifact_sha256"]
    ):
        raise QcSyntheticInputTransportError(
            "global-input manifest bytes do not match the transport index"
        )
    try:
        manifest = load_synthetic_qc_global_input_manifest_bytes(
            manifest_payload,
            run_candidate=run_candidate,
        )
    except (QcGlobalInputSchemaError, TypeError, ValueError, AttributeError) as exc:
        raise QcSyntheticInputTransportError(
            "global-input manifest is not authenticated"
        ) from exc
    if (
        manifest.manifest_id != manifest_binding["manifest_id"]
        or manifest.manifest_sha256 != manifest_binding["manifest_sha256"]
        or manifest.manifest_artifact_sha256
        != manifest_binding["manifest_artifact_sha256"]
    ):
        raise QcSyntheticInputTransportError("global-input manifest lineage changed")
    manifest_partition_contract = tuple(
        (
            item.ordinal,
            item.role,
            item.byte_count,
            item.row_count,
            item.artifact_sha256,
        )
        for item in manifest.partitions
    )
    transport_partition_contract = tuple(
        (
            item.ordinal,
            item.role,
            item.byte_count,
            item.row_count,
            item.artifact_sha256,
        )
        for item in bindings
    )
    if transport_partition_contract != manifest_partition_contract:
        raise QcSyntheticInputTransportError(
            "transport partition census does not match the global-input manifest"
        )
    partition_payloads: list[SyntheticGlobalInputPartitionPayload] = []
    for binding, entry in zip(bindings, fixture.entries[2:], strict=True):
        if (
            len(entry.payload) != binding.byte_count
            or hashlib.sha256(entry.payload).hexdigest()
            != binding.artifact_sha256
        ):
            raise QcSyntheticInputTransportError(
                f"{binding.role} bytes do not match the transport index"
            )
        partition_payloads.append(
            SyntheticGlobalInputPartitionPayload(
                role=binding.role,
                payload=bytes(entry.payload),
            )
        )
    try:
        bundle = load_synthetic_qc_global_input_bundle(
            run_candidate=run_candidate,
            manifest_bytes=manifest_payload,
            partition_payloads=tuple(partition_payloads),
        )
        require_synthetic_qc_global_input_bundle(bundle)
    except (
        QcGlobalInputBundleError,
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:
        raise QcSyntheticInputTransportError(
            "transport payload bundle is not authenticated"
        ) from exc
    if (
        bundle.bundle_id != bundle_binding["bundle_id"]
        or bundle.bundle_hash != bundle_binding["bundle_hash"]
        or bundle.bundle_artifact_sha256
        != bundle_binding["bundle_artifact_sha256"]
        or bundle.total_row_count
        != document["referenced_census"]["total_row_count"]
    ):
        raise QcSyntheticInputTransportError("transport bundle lineage changed")
    copied_fixture = _copy_fixture(fixture)
    receipt = SyntheticQcTransportLoad(
        transport_id=document["transport_id"],
        transport_hash=document["transport_hash"],
        transport_artifact_sha256=hashlib.sha256(index_entry.payload).hexdigest(),
        transport_index_key=index_key,
        resolved_fixture_keys=expected_keys,
        bundle=bundle,
        total_object_count=EXPECTED_OBJECT_COUNT,
        total_byte_count=sum(len(item.payload) for item in fixture.entries),
        total_row_count=bundle.total_row_count,
        synthetic_fixture_transport_validated=True,
        real_qc_object_store_access_performed=False,
        external_bindings=EXTERNAL_BINDINGS,
        capabilities=CAPABILITIES,
        _run_candidate=run_candidate,
        _fixture=copied_fixture,
        _canonical_document=bytes(index_entry.payload),
    )
    if (
        type(receipt) is not _PINNED_RECEIPT_CLASS
        or receipt.synthetic_fixture_transport_validated is not True
        or receipt.real_qc_object_store_access_performed is not False
        or receipt.external_bindings is not EXTERNAL_BINDINGS
        or receipt.capabilities is not CAPABILITIES
        or any(getattr(receipt, name) is not False for name in FALSE_PROPERTY_NAMES)
    ):
        raise QcSyntheticInputTransportError(
            "constructed transport receipt acquired external authority"
        )
    return receipt


def require_synthetic_qc_transport_load(
    value: SyntheticQcTransportLoad,
) -> SyntheticQcTransportLoad:
    """Reauthenticate a retained synthetic transport receipt and its bundle."""

    _require_static_contract()
    if type(value) is not SyntheticQcTransportLoad:
        raise QcSyntheticInputTransportError(
            "transport load receipt changed type"
        )
    try:
        scalar_types = (
            (value.transport_id, str),
            (value.transport_hash, str),
            (value.transport_artifact_sha256, str),
            (value.transport_index_key, str),
            (value.resolved_fixture_keys, tuple),
            (value.bundle, SyntheticQcGlobalInputBundle),
            (value.total_object_count, int),
            (value.total_byte_count, int),
            (value.total_row_count, int),
            (value.synthetic_fixture_transport_validated, bool),
            (value.real_qc_object_store_access_performed, bool),
            (value.external_bindings, tuple),
            (value.capabilities, tuple),
            (value._run_candidate, SyntheticQcRunCandidate),
            (value._fixture, SyntheticObjectStoreFixture),
            (value._canonical_document, bytes),
        )
    except AttributeError as exc:
        raise QcSyntheticInputTransportError(
            "transport load receipt topology changed"
        ) from exc
    if any(type(item) is not expected for item, expected in scalar_types):
        raise QcSyntheticInputTransportError(
            "transport load receipt topology changed"
        )
    if (
        value.total_object_count != EXPECTED_OBJECT_COUNT
        or value.total_byte_count < 0
        or value.total_byte_count > MAX_TOTAL_BYTES
        or value.total_row_count < 0
        or value.synthetic_fixture_transport_validated is not True
        or value.real_qc_object_store_access_performed is not False
        or value.external_bindings != EXTERNAL_BINDINGS
        or value.capabilities != CAPABILITIES
        or any(binding is not None for _, binding in value.external_bindings)
        or any(capability is not False for _, capability in value.capabilities)
        or any(getattr(value, name) is not False for name in FALSE_PROPERTY_NAMES)
    ):
        raise QcSyntheticInputTransportError(
            "transport load receipt acquired external authority"
        )
    _require_sha256(value.transport_hash, "transport_hash")
    _require_sha256(
        value.transport_artifact_sha256,
        "transport_artifact_sha256",
    )
    _require_safe_key(value.transport_index_key, "transport_index_key")
    if (
        len(value.resolved_fixture_keys) != EXPECTED_OBJECT_COUNT
        or any(type(key) is not str for key in value.resolved_fixture_keys)
        or len(set(value.resolved_fixture_keys)) != EXPECTED_OBJECT_COUNT
    ):
        raise QcSyntheticInputTransportError(
            "resolved fixture key census changed"
        )
    try:
        require_synthetic_qc_global_input_bundle(value.bundle)
    except QcGlobalInputBundleError as exc:
        raise QcSyntheticInputTransportError(
            "retained transport bundle changed"
        ) from exc
    rebuilt = load_synthetic_qc_global_input_bundle_from_object_store_fixture(
        run_candidate=value._run_candidate,
        object_store=value._fixture,
        transport_index_key=value.transport_index_key,
    )
    comparable = (
        "transport_id",
        "transport_hash",
        "transport_artifact_sha256",
        "transport_index_key",
        "resolved_fixture_keys",
        "total_object_count",
        "total_byte_count",
        "total_row_count",
        "synthetic_fixture_transport_validated",
        "real_qc_object_store_access_performed",
        "external_bindings",
        "capabilities",
        "_canonical_document",
    )
    if any(getattr(value, name) != getattr(rebuilt, name) for name in comparable):
        raise QcSyntheticInputTransportError(
            "transport load receipt changed after construction"
        )
    if (
        value.bundle.bundle_id != rebuilt.bundle.bundle_id
        or value.bundle.bundle_hash != rebuilt.bundle.bundle_hash
        or value.bundle.bundle_artifact_sha256
        != rebuilt.bundle.bundle_artifact_sha256
    ):
        raise QcSyntheticInputTransportError("retained transport bundle changed")
    return value


_LOCAL_MODULE_GLOBALS = globals()
_PINNED_LOCAL_MODULE_GLOBALS = _LOCAL_MODULE_GLOBALS
_LOCAL_FUNCTION_STATES = tuple(
    (
        name,
        value,
        value.__code__,
        value.__defaults__,
        value.__kwdefaults__,
        value.__closure__,
        tuple(
            (cell, type(cell.cell_contents), cell.cell_contents)
            for cell in (value.__closure__ or ())
        ),
    )
    for name, value in tuple(_LOCAL_MODULE_GLOBALS.items())
    if inspect.isfunction(value) and value.__module__ == __name__
)
_PINNED_LOCAL_FUNCTION_STATES = _LOCAL_FUNCTION_STATES


_BUILTIN_GLOBALS = __builtins__
if _PINNED_TYPE(_BUILTIN_GLOBALS) is not _PINNED_DICT:
    raise RuntimeError("expected exact builtins dictionary")
_PINNED_BUILTIN_GLOBALS = _BUILTIN_GLOBALS
_BUILTIN_GLOBAL_ENTRIES = tuple(_PINNED_DICT_ITEMS(_BUILTIN_GLOBALS))
_PINNED_BUILTIN_GLOBAL_ENTRIES = _BUILTIN_GLOBAL_ENTRIES


def _capture_builtin_resolution_bindings():
    bindings = []
    seen = set()
    code_type = type((lambda: None).__code__)
    function_states = (*_CLASS_FUNCTION_STATES, *_LOCAL_FUNCTION_STATES)
    for state in function_states:
        implementation = state[2] if len(state) == 8 else state[1]
        pending = [implementation.__code__]
        while pending:
            code = pending.pop()
            for name in code.co_names:
                identity = (id(implementation.__globals__), id(name))
                if (
                    identity not in seen
                    and name not in implementation.__globals__
                    and name in _BUILTIN_GLOBALS
                ):
                    seen.add(identity)
                    bindings.append(
                        (implementation.__globals__, name, _BUILTIN_GLOBALS[name])
                    )
            pending.extend(
                value for value in code.co_consts if type(value) is code_type
            )
    return tuple(bindings)


_BUILTIN_RESOLUTION_BINDINGS = _capture_builtin_resolution_bindings()
_PINNED_BUILTIN_RESOLUTION_BINDINGS = _BUILTIN_RESOLUTION_BINDINGS
del _capture_builtin_resolution_bindings
