"""Synthetic QC Object Store read-plan and transcript contract.

This module models the value boundary a later LEAN shell must satisfy.  It
never accepts a client, callback, path, credential, environment value, or
QuantConnect object.  The only positive path consumes the already reviewed
B3 in-memory fixture, constructs an exact synthetic read transcript, and
delegates reconstructed bytes back to B3's public loader.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import re

from .run_contract import SyntheticQcRunCandidate
from .synthetic_input_transport import (
    BUNDLE_SOURCE_BYTE_COUNT as B3_PARENT_SOURCE_BYTE_COUNT,
    BUNDLE_SOURCE_SHA256 as B3_PARENT_SOURCE_SHA256,
    CAPABILITIES as B3_CAPABILITIES,
    EXPECTED_OBJECT_COUNT,
    EXTERNAL_BINDINGS as B3_EXTERNAL_BINDINGS,
    FALSE_PROPERTY_NAMES,
    MAX_OBJECT_BYTES,
    QcSyntheticInputTransportError,
    SCHEMA_ARTIFACT_SHA256 as B3_SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID as B3_SCHEMA_ID,
    SCHEMA_SHA256 as B3_SCHEMA_SHA256,
    SyntheticObjectStoreEntry,
    SyntheticObjectStoreFixture,
    SyntheticQcTransportLoad,
    load_synthetic_qc_global_input_bundle_from_object_store_fixture,
    render_qc_synthetic_input_transport_schema_bytes,
    require_synthetic_qc_transport_load,
)


class QcObjectStoreReadContractError(ValueError):
    """A synthetic Object Store read plan, transcript, or receipt is invalid."""


_PINNED_ERROR_CLASS = QcObjectStoreReadContractError


SCHEMA = "arv2-qc-object-store-read-contract-schema-v1"
STATUS = "synthetic_value_transcript_only_not_real_qc_object_store_access"
AUTHORITY = (
    "synthetic_fixture_read_plan_only_no_account_quota_object_store_"
    "result_deployment_order_or_trading_authority"
)
HASH_DOMAIN = "arv2-qc-object-store-read-contract-v1"
TRANSCRIPT_HASH_DOMAIN = "arv2-qc-object-store-read-transcript-v1"
SYNTHETIC_PROJECT_NAMESPACE = "synthetic-project-id-not-real"
PROJECT_NAMESPACE_SEPARATOR = "/"
CONTAINS_KEY_OPERATION = "contains_key"
READ_BYTES_OPERATION = "read_bytes"
EXPECTED_EVENT_COUNT = EXPECTED_OBJECT_COUNT * 2
MAX_KEY_CHARS = 512

# Reviewed B3 source identity.  Runtime authentication is performed through
# B3's public renderer and loader; no source file is opened here.
B3_SOURCE_SHA256 = (
    "c473bf91a99fd5207ab10407ea85971db9e24e75f7d29ccf64b38c628538ebe9"
)
B3_SOURCE_BYTE_COUNT = 65_144

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,511}\Z")

_PINNED_ALL = all
_PINNED_ANY = any
_PINNED_ATTRIBUTE_ERROR = AttributeError
_PINNED_BOOL = bool
_PINNED_BYTES = bytes
_PINNED_DICT = dict
_PINNED_ENUMERATE = enumerate
_PINNED_GETATTR = getattr
_PINNED_GLOBALS = globals
_PINNED_HASH = hash
_PINNED_ID = id
_PINNED_ISINSTANCE = isinstance
_PINNED_INT = int
_PINNED_LEN = len
_PINNED_LIST = list
_PINNED_OBJECT = object
_PINNED_NOT_IMPLEMENTED = NotImplemented
_PINNED_OVERFLOW_ERROR = OverflowError
_PINNED_PROPERTY = property
_PINNED_RANGE = range
_PINNED_RECURSION_ERROR = RecursionError
_PINNED_STR = str
_PINNED_SUM = sum
_PINNED_SUPER = super
_PINNED_TUPLE = tuple
_PINNED_TYPE = type
_PINNED_TYPE_ERROR = TypeError
_PINNED_VALUE_ERROR = ValueError
_PINNED_VARS = vars
_PINNED_ZIP = zip
_PINNED_BUILTINS_DICT = __builtins__
_PINNED_CODE_TYPE = type((lambda: None).__code__)
_PINNED_BUILTIN_BINDINGS = (
    ("all", _PINNED_ALL),
    ("any", _PINNED_ANY),
    ("AttributeError", _PINNED_ATTRIBUTE_ERROR),
    ("bool", _PINNED_BOOL),
    ("bytes", _PINNED_BYTES),
    ("dict", _PINNED_DICT),
    ("enumerate", _PINNED_ENUMERATE),
    ("getattr", _PINNED_GETATTR),
    ("globals", _PINNED_GLOBALS),
    ("hash", _PINNED_HASH),
    ("id", _PINNED_ID),
    ("isinstance", _PINNED_ISINSTANCE),
    ("int", _PINNED_INT),
    ("len", _PINNED_LEN),
    ("list", _PINNED_LIST),
    ("object", _PINNED_OBJECT),
    ("NotImplemented", _PINNED_NOT_IMPLEMENTED),
    ("OverflowError", _PINNED_OVERFLOW_ERROR),
    ("property", _PINNED_PROPERTY),
    ("range", _PINNED_RANGE),
    ("RecursionError", _PINNED_RECURSION_ERROR),
    ("str", _PINNED_STR),
    ("sum", _PINNED_SUM),
    ("super", _PINNED_SUPER),
    ("tuple", _PINNED_TUPLE),
    ("type", _PINNED_TYPE),
    ("TypeError", _PINNED_TYPE_ERROR),
    ("ValueError", _PINNED_VALUE_ERROR),
    ("vars", _PINNED_VARS),
    ("zip", _PINNED_ZIP),
)

EXTERNAL_BINDINGS = (
    *B3_EXTERNAL_BINDINGS,
    ("owner_qc_object_store_read_authority_id", None),
    ("authenticated_qc_project_namespace", None),
    ("authenticated_qc_project_id", None),
    ("authenticated_qc_account_quota_evidence_id", None),
    ("runtime_code_binding_id", None),
)
CAPABILITIES = B3_CAPABILITIES
_PINNED_EXTERNAL_BINDINGS = EXTERNAL_BINDINGS
_PINNED_CAPABILITIES = CAPABILITIES


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticObjectStoreReadDescriptor:
    ordinal: int
    logical_key: str
    object_store_key: str
    byte_count: int
    artifact_sha256: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticQcObjectStoreReadPlan:
    plan_id: str
    plan_hash: str
    plan_artifact_sha256: str
    project_namespace: str
    synthetic_max_size: int
    synthetic_max_files: int
    transport_id: str
    transport_hash: str
    transport_artifact_sha256: str
    transport_index_key: str
    objects: tuple[SyntheticObjectStoreReadDescriptor, ...]
    total_object_count: int
    total_byte_count: int
    total_row_count: int
    synthetic_quota_observation: bool
    real_account_quota_authenticated: bool
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


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticObjectStoreReadEvent:
    ordinal: int
    operation: str
    object_store_key: str
    found: bool | None
    payload: bytes | None


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticQcObjectStoreReadTranscript:
    transcript_id: str
    transcript_hash: str
    transcript_artifact_sha256: str
    plan_id: str
    plan_hash: str
    events: tuple[SyntheticObjectStoreReadEvent, ...]
    synthetic_fixture_transcript: bool
    real_qc_object_store_access_performed: bool
    external_bindings: tuple[tuple[str, None], ...]
    capabilities: tuple[tuple[str, bool], ...]
    _canonical_document: bytes = dataclasses.field(repr=False)

    @property
    def qc_object_store_read_available(self) -> bool:
        return False

    @property
    def qc_object_store_write_available(self) -> bool:
        return False


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticQcObjectStoreReadReceipt:
    receipt_id: str
    receipt_hash: str
    plan_id: str
    plan_hash: str
    transcript_id: str
    transcript_hash: str
    object_store_keys: tuple[str, ...]
    transport_load: SyntheticQcTransportLoad
    total_object_count: int
    total_byte_count: int
    total_row_count: int
    synthetic_read_contract_validated: bool
    real_account_quota_authenticated: bool
    real_qc_object_store_access_performed: bool
    external_bindings: tuple[tuple[str, None], ...]
    capabilities: tuple[tuple[str, bool], ...]
    _plan: SyntheticQcObjectStoreReadPlan = dataclasses.field(repr=False)
    _transcript: SyntheticQcObjectStoreReadTranscript = dataclasses.field(
        repr=False
    )

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
        raise _PINNED_ERROR_CLASS(
            "Object Store read contract is not canonical JSON"
        ) from exc


def _schema_seed_document() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "parent": {
            "schema_id": B3_SCHEMA_ID,
            "schema_sha256": B3_SCHEMA_SHA256,
            "schema_artifact_sha256": B3_SCHEMA_ARTIFACT_SHA256,
            "source_sha256": B3_SOURCE_SHA256,
            "source_byte_count": B3_SOURCE_BYTE_COUNT,
            "parent_source_sha256": B3_PARENT_SOURCE_SHA256,
            "parent_source_byte_count": B3_PARENT_SOURCE_BYTE_COUNT,
        },
        "namespace": {
            "synthetic_project_namespace": SYNTHETIC_PROJECT_NAMESPACE,
            "separator": PROJECT_NAMESPACE_SEPARATOR,
            "applied_exactly_once": True,
            "real_project_id": None,
        },
        "quota": {
            "caller_supplied_positive_synthetic_max_size": True,
            "caller_supplied_positive_synthetic_max_files": True,
            "account_quota_authenticated": False,
            "per_object_parser_bound": MAX_OBJECT_BYTES,
        },
        "inventory": {
            "object_count": EXPECTED_OBJECT_COUNT,
            "event_count": EXPECTED_EVENT_COUNT,
            "event_order": [CONTAINS_KEY_OPERATION, READ_BYTES_OPERATION],
        },
        "truth": {
            "synthetic_value_plan": True,
            "synthetic_fixture_transcript": True,
            "real_object_store_access": False,
            "callbacks": False,
            "qc_imports": False,
        },
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
    }


SCHEMA_SHA256 = (
    "5dcb6cffb8f9688b1a63a0ea452fd7f4c3e706df7941691ede58c95e0f055dd2"
)
SCHEMA_ID = "arv2-qc-object-store-read-contract-5dcb6cffb8f9688b"


def _schema_document() -> dict[str, object]:
    value = _schema_seed_document()
    value["schema_id"] = SCHEMA_ID
    value["schema_sha256"] = SCHEMA_SHA256
    return value


SCHEMA_ARTIFACT_SHA256 = (
    "95c3242405dddaaec40af01113a6823235fa74fcf405ab7b30ab5c6a45a8e987"
)

_PINNED_DATACLASSES_MODULE = dataclasses
_PINNED_HASHLIB_MODULE = hashlib
_PINNED_INSPECT_MODULE = inspect
_PINNED_JSON_MODULE = json
_PINNED_RE_MODULE = re
_PINNED_DATACLASSES_FIELDS = dataclasses.fields
_PINNED_SHA256 = hashlib.sha256
_PINNED_JSON_DUMPS = json.dumps
_PINNED_RENDER_B3_SCHEMA = render_qc_synthetic_input_transport_schema_bytes
_PINNED_LOAD_B3 = (
    load_synthetic_qc_global_input_bundle_from_object_store_fixture
)
_PINNED_REQUIRE_B3 = require_synthetic_qc_transport_load
_PINNED_ENTRY_CLASS = SyntheticObjectStoreEntry
_PINNED_FIXTURE_CLASS = SyntheticObjectStoreFixture
_PINNED_TRANSPORT_LOAD_CLASS = SyntheticQcTransportLoad
_PINNED_RUN_CANDIDATE_CLASS = SyntheticQcRunCandidate
_PINNED_B3_ERROR_CLASS = QcSyntheticInputTransportError
_PINNED_HEX_64 = _HEX_64
_PINNED_SAFE_KEY = _SAFE_KEY
_PINNED_FALSE_PROPERTY_NAMES = FALSE_PROPERTY_NAMES

_MODULE_GLOBALS = globals()
_PINNED_MODULE_GLOBALS = _MODULE_GLOBALS
_PINNED_SCALARS = (
    ("SCHEMA", str, SCHEMA),
    ("STATUS", str, STATUS),
    ("AUTHORITY", str, AUTHORITY),
    ("HASH_DOMAIN", str, HASH_DOMAIN),
    ("TRANSCRIPT_HASH_DOMAIN", str, TRANSCRIPT_HASH_DOMAIN),
    ("SYNTHETIC_PROJECT_NAMESPACE", str, SYNTHETIC_PROJECT_NAMESPACE),
    ("PROJECT_NAMESPACE_SEPARATOR", str, PROJECT_NAMESPACE_SEPARATOR),
    ("CONTAINS_KEY_OPERATION", str, CONTAINS_KEY_OPERATION),
    ("READ_BYTES_OPERATION", str, READ_BYTES_OPERATION),
    ("EXPECTED_OBJECT_COUNT", int, EXPECTED_OBJECT_COUNT),
    ("EXPECTED_EVENT_COUNT", int, EXPECTED_EVENT_COUNT),
    ("MAX_KEY_CHARS", int, MAX_KEY_CHARS),
    ("MAX_OBJECT_BYTES", int, MAX_OBJECT_BYTES),
    ("B3_SOURCE_SHA256", str, B3_SOURCE_SHA256),
    ("B3_SOURCE_BYTE_COUNT", int, B3_SOURCE_BYTE_COUNT),
    ("B3_PARENT_SOURCE_SHA256", str, B3_PARENT_SOURCE_SHA256),
    ("B3_PARENT_SOURCE_BYTE_COUNT", int, B3_PARENT_SOURCE_BYTE_COUNT),
    ("B3_SCHEMA_ID", str, B3_SCHEMA_ID),
    ("B3_SCHEMA_SHA256", str, B3_SCHEMA_SHA256),
    ("B3_SCHEMA_ARTIFACT_SHA256", str, B3_SCHEMA_ARTIFACT_SHA256),
    ("SCHEMA_ID", str, SCHEMA_ID),
    ("SCHEMA_SHA256", str, SCHEMA_SHA256),
    ("SCHEMA_ARTIFACT_SHA256", str, SCHEMA_ARTIFACT_SHA256),
)
_PINNED_CLASSES = (
    ("QcObjectStoreReadContractError", QcObjectStoreReadContractError),
    ("SyntheticObjectStoreReadDescriptor", SyntheticObjectStoreReadDescriptor),
    ("SyntheticQcObjectStoreReadPlan", SyntheticQcObjectStoreReadPlan),
    ("SyntheticObjectStoreReadEvent", SyntheticObjectStoreReadEvent),
    (
        "SyntheticQcObjectStoreReadTranscript",
        SyntheticQcObjectStoreReadTranscript,
    ),
    ("SyntheticQcObjectStoreReadReceipt", SyntheticQcObjectStoreReadReceipt),
)


def _preflight_b3() -> None:
    """Authenticate B3 before inspecting caller values.

    B3 intentionally snapshots its imported builtins dictionary.  A runtime
    that injects names into ``builtins`` after B3 import is therefore refused
    here, before this layer examines a fixture, plan, or transcript.
    """

    try:
        payload = _PINNED_RENDER_B3_SCHEMA()
    except (
        _PINNED_B3_ERROR_CLASS,
        _PINNED_TYPE_ERROR,
        _PINNED_VALUE_ERROR,
    ) as exc:
        raise _PINNED_ERROR_CLASS(
            "B3 static preflight refused this runtime; use an unchanged "
            "post-import builtins topology"
        ) from exc
    if _PINNED_SHA256(payload).hexdigest() != B3_SCHEMA_ARTIFACT_SHA256:
        raise _PINNED_ERROR_CLASS("B3 schema artifact identity changed")
    if (
        dataclasses is not _PINNED_DATACLASSES_MODULE
        or hashlib is not _PINNED_HASHLIB_MODULE
        or inspect is not _PINNED_INSPECT_MODULE
        or json is not _PINNED_JSON_MODULE
        or re is not _PINNED_RE_MODULE
        or dataclasses.fields is not _PINNED_DATACLASSES_FIELDS
        or hashlib.sha256 is not _PINNED_SHA256
        or json.dumps is not _PINNED_JSON_DUMPS
        or render_qc_synthetic_input_transport_schema_bytes
        is not _PINNED_RENDER_B3_SCHEMA
        or load_synthetic_qc_global_input_bundle_from_object_store_fixture
        is not _PINNED_LOAD_B3
        or require_synthetic_qc_transport_load is not _PINNED_REQUIRE_B3
        or SyntheticObjectStoreEntry is not _PINNED_ENTRY_CLASS
        or SyntheticObjectStoreFixture is not _PINNED_FIXTURE_CLASS
        or SyntheticQcTransportLoad is not _PINNED_TRANSPORT_LOAD_CLASS
        or SyntheticQcRunCandidate is not _PINNED_RUN_CANDIDATE_CLASS
        or QcSyntheticInputTransportError is not _PINNED_B3_ERROR_CLASS
        or _HEX_64 is not _PINNED_HEX_64
        or _SAFE_KEY is not _PINNED_SAFE_KEY
        or FALSE_PROPERTY_NAMES is not _PINNED_FALSE_PROPERTY_NAMES
    ):
        raise _PINNED_ERROR_CLASS("B4 dependency identity changed")


_PINNED_PREFLIGHT_B3 = _preflight_b3


def _registry_topology_is_exact(
    bindings: object,
    capabilities: object,
) -> bool:
    if (
        _PINNED_TYPE(bindings) is not _PINNED_TUPLE
        or _PINNED_TYPE(capabilities) is not _PINNED_TUPLE
        or _PINNED_LEN(bindings) != _PINNED_LEN(EXTERNAL_BINDINGS)
        or _PINNED_LEN(capabilities) != _PINNED_LEN(CAPABILITIES)
    ):
        return False
    for current, expected in _PINNED_ZIP(
        bindings, EXTERNAL_BINDINGS, strict=True
    ):
        if (
            _PINNED_TYPE(current) is not _PINNED_TUPLE
            or _PINNED_LEN(current) != 2
            or _PINNED_TYPE(current[0]) is not _PINNED_STR
            or current[0] != expected[0]
            or current[1] is not None
        ):
            return False
    for current, expected in _PINNED_ZIP(
        capabilities, CAPABILITIES, strict=True
    ):
        if (
            _PINNED_TYPE(current) is not _PINNED_TUPLE
            or _PINNED_LEN(current) != 2
            or _PINNED_TYPE(current[0]) is not _PINNED_STR
            or current[0] != expected[0]
            or _PINNED_TYPE(current[1]) is not bool
            or current[1] is not False
        ):
            return False
    return True


def _plan_topology_is_exact(value: object) -> bool:
    if _PINNED_TYPE(value) is not SyntheticQcObjectStoreReadPlan:
        return False
    try:
        scalars = (
            (value.plan_id, str),
            (value.plan_hash, str),
            (value.plan_artifact_sha256, str),
            (value.project_namespace, str),
            (value.synthetic_max_size, int),
            (value.synthetic_max_files, int),
            (value.transport_id, str),
            (value.transport_hash, str),
            (value.transport_artifact_sha256, str),
            (value.transport_index_key, str),
            (value.objects, tuple),
            (value.total_object_count, int),
            (value.total_byte_count, int),
            (value.total_row_count, int),
            (value.synthetic_quota_observation, bool),
            (value.real_account_quota_authenticated, bool),
            (value.real_qc_object_store_access_performed, bool),
            (value.external_bindings, tuple),
            (value.capabilities, tuple),
            (value._run_candidate, SyntheticQcRunCandidate),
            (value._fixture, SyntheticObjectStoreFixture),
            (value._canonical_document, bytes),
        )
    except AttributeError:
        return False
    if any(type(item) is not expected for item, expected in scalars):
        return False
    if not _registry_topology_is_exact(
        value.external_bindings, value.capabilities
    ):
        return False
    for item in value.objects:
        if type(item) is not SyntheticObjectStoreReadDescriptor:
            return False
        try:
            descriptor_scalars = (
                (item.ordinal, int),
                (item.logical_key, str),
                (item.object_store_key, str),
                (item.byte_count, int),
                (item.artifact_sha256, str),
            )
        except AttributeError:
            return False
        if (
            any(
                type(field) is not expected
                for field, expected in descriptor_scalars
            )
        ):
            return False
    return True


def _transcript_topology_is_exact(value: object) -> bool:
    if _PINNED_TYPE(value) is not SyntheticQcObjectStoreReadTranscript:
        return False
    try:
        scalars = (
            (value.transcript_id, str),
            (value.transcript_hash, str),
            (value.transcript_artifact_sha256, str),
            (value.plan_id, str),
            (value.plan_hash, str),
            (value.events, tuple),
            (value.synthetic_fixture_transcript, bool),
            (value.real_qc_object_store_access_performed, bool),
            (value.external_bindings, tuple),
            (value.capabilities, tuple),
            (value._canonical_document, bytes),
        )
    except AttributeError:
        return False
    if any(type(item) is not expected for item, expected in scalars):
        return False
    if not _registry_topology_is_exact(
        value.external_bindings, value.capabilities
    ):
        return False
    for item in value.events:
        if type(item) is not SyntheticObjectStoreReadEvent:
            return False
        try:
            if (
                type(item.ordinal) is not int
                or type(item.operation) is not str
                or type(item.object_store_key) is not str
                or (item.found is not None and type(item.found) is not bool)
                or (item.payload is not None and type(item.payload) is not bytes)
            ):
                return False
        except AttributeError:
            return False
    return True


def _receipt_topology_is_exact(value: object) -> bool:
    if _PINNED_TYPE(value) is not SyntheticQcObjectStoreReadReceipt:
        return False
    try:
        scalars = (
            (value.receipt_id, str),
            (value.receipt_hash, str),
            (value.plan_id, str),
            (value.plan_hash, str),
            (value.transcript_id, str),
            (value.transcript_hash, str),
            (value.object_store_keys, tuple),
            (value.transport_load, SyntheticQcTransportLoad),
            (value.total_object_count, int),
            (value.total_byte_count, int),
            (value.total_row_count, int),
            (value.synthetic_read_contract_validated, bool),
            (value.real_account_quota_authenticated, bool),
            (value.real_qc_object_store_access_performed, bool),
            (value.external_bindings, tuple),
            (value.capabilities, tuple),
            (value._plan, SyntheticQcObjectStoreReadPlan),
            (value._transcript, SyntheticQcObjectStoreReadTranscript),
        )
    except AttributeError:
        return False
    if any(type(item) is not expected for item, expected in scalars):
        return False
    if any(type(key) is not str for key in value.object_store_keys):
        return False
    return _registry_topology_is_exact(
        value.external_bindings, value.capabilities
    )


def _require_static_contract() -> None:
    """Refuse B3, dependency, constant, class, or helper substitution."""

    _PINNED_PREFLIGHT_B3()
    if (
        globals is not _PINNED_GLOBALS
        or _MODULE_GLOBALS is not _PINNED_MODULE_GLOBALS
        or EXTERNAL_BINDINGS is not _PINNED_EXTERNAL_BINDINGS
        or CAPABILITIES is not _PINNED_CAPABILITIES
        or _PINNED_TYPE(_PINNED_SCALARS) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_CLASSES) is not _PINNED_TUPLE
    ):
        raise _PINNED_ERROR_CLASS("B4 static topology changed")
    for name, expected_type, expected_value in _PINNED_SCALARS:
        current = _PINNED_MODULE_GLOBALS.get(name)
        if _PINNED_TYPE(current) is not expected_type or current != expected_value:
            raise _PINNED_ERROR_CLASS("B4 scalar contract changed")
    for name, expected_builtin in _PINNED_BUILTIN_BINDINGS:
        if name in _PINNED_MODULE_GLOBALS:
            raise _PINNED_ERROR_CLASS("B4 builtin resolution changed")
        if (
            _PINNED_TYPE(_PINNED_BUILTINS_DICT) is not _PINNED_DICT
            or _PINNED_BUILTINS_DICT.get(name) is not expected_builtin
        ):
            raise _PINNED_ERROR_CLASS("B4 builtin identity changed")
    if not _registry_topology_is_exact(EXTERNAL_BINDINGS, CAPABILITIES):
        raise _PINNED_ERROR_CLASS("B4 authority registries changed")
    for name, expected_class in _PINNED_CLASSES:
        if _PINNED_MODULE_GLOBALS.get(name) is not expected_class:
            raise _PINNED_ERROR_CLASS("B4 class identity changed")
    if (
        _PINNED_TYPE(_PINNED_LOCAL_FUNCTION_STATES) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_CLASS_STATES) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_CLASS_FUNCTION_STATES) is not _PINNED_TUPLE
        or _PINNED_TYPE(_PINNED_BUILTIN_RESOLUTION_BINDINGS)
        is not _PINNED_TUPLE
    ):
        raise _PINNED_ERROR_CLASS("B4 static snapshot changed")
    for function_globals, name, expected_builtin in (
        _PINNED_BUILTIN_RESOLUTION_BINDINGS
    ):
        if (
            _PINNED_TYPE(function_globals) is not _PINNED_DICT
            or name in function_globals
            or _PINNED_BUILTINS_DICT.get(name) is not expected_builtin
        ):
            raise _PINNED_ERROR_CLASS("B4 builtin resolution changed")
    for name, implementation, code, defaults, kwdefaults, closure in (
        _PINNED_LOCAL_FUNCTION_STATES
    ):
        current = _PINNED_MODULE_GLOBALS.get(name)
        if (
            current is not implementation
            or current.__code__ is not code
            or current.__defaults__ is not defaults
            or current.__kwdefaults__ is not kwdefaults
            or current.__closure__ is not closure
        ):
            raise _PINNED_ERROR_CLASS("B4 function identity changed")
    for accepted_class, expected_members in _PINNED_CLASS_STATES:
        current_members = _PINNED_TUPLE(
            _PINNED_VARS(accepted_class).items()
        )
        if _PINNED_LEN(current_members) != _PINNED_LEN(expected_members):
            raise _PINNED_ERROR_CLASS("B4 class topology changed")
        for current, expected in _PINNED_ZIP(
            current_members, expected_members, strict=True
        ):
            if (
                _PINNED_TYPE(current[0]) is not _PINNED_STR
                or current[0] != expected[0]
                or current[1] is not expected[1]
            ):
                raise _PINNED_ERROR_CLASS("B4 class topology changed")
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
                "B4 class function identity changed"
            )
        for cell, content_type, content in cells:
            try:
                current_content = cell.cell_contents
            except ValueError as exc:
                raise _PINNED_ERROR_CLASS(
                    "B4 class closure changed"
                ) from exc
            if (
                _PINNED_TYPE(current_content) is not content_type
                or current_content is not content
            ):
                raise _PINNED_ERROR_CLASS(
                    "B4 class closure changed"
                )


_PINNED_REQUIRE_STATIC_CONTRACT = _require_static_contract


def render_qc_object_store_read_contract_schema_bytes() -> bytes:
    """Render the content-addressed B4 schema after the B3 preflight."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    seed_hash = hashlib.sha256(_canonical_bytes(_schema_seed_document())).hexdigest()
    if seed_hash != SCHEMA_SHA256 or SCHEMA_ID != (
        f"arv2-qc-object-store-read-contract-{seed_hash[:16]}"
    ):
        raise _PINNED_ERROR_CLASS("B4 schema identity changed")
    payload = _canonical_bytes(_schema_document())
    if hashlib.sha256(payload).hexdigest() != SCHEMA_ARTIFACT_SHA256:
        raise _PINNED_ERROR_CLASS("B4 schema artifact identity changed")
    return payload


def _require_exact_positive_int(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise _PINNED_ERROR_CLASS(f"{name} must be an exact positive int")
    return value


def _require_nonnegative_int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise _PINNED_ERROR_CLASS(
            f"{name} must be an exact nonnegative int"
        )
    return value


def _require_sha256(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise _PINNED_ERROR_CLASS(f"{name} must be lowercase SHA-256")
    return value


def _require_safe_key(value: object, name: str) -> str:
    if (
        type(value) is not str
        or len(value) > MAX_KEY_CHARS
        or _SAFE_KEY.fullmatch(value) is None
        or "//" in value
        or value.startswith("/")
        or value.endswith("/")
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise _PINNED_ERROR_CLASS(f"{name} is not a safe key")
    return value


def _copy_fixture(value: SyntheticObjectStoreFixture) -> SyntheticObjectStoreFixture:
    return SyntheticObjectStoreFixture(
        transport_index_key=str(value.transport_index_key),
        entries=tuple(
            SyntheticObjectStoreEntry(key=str(item.key), payload=bytes(item.payload))
            for item in value.entries
        ),
    )


def _descriptor_document(
    value: SyntheticObjectStoreReadDescriptor,
) -> dict[str, object]:
    return {
        "ordinal": value.ordinal,
        "logical_key": value.logical_key,
        "object_store_key": value.object_store_key,
        "byte_count": value.byte_count,
        "artifact_sha256": value.artifact_sha256,
    }


def _plan_seed_document(
    *,
    transport_load: SyntheticQcTransportLoad,
    synthetic_max_size: int,
    synthetic_max_files: int,
    objects: tuple[SyntheticObjectStoreReadDescriptor, ...],
) -> dict[str, object]:
    return {
        "schema_id": SCHEMA_ID,
        "schema_sha256": SCHEMA_SHA256,
        "schema_artifact_sha256": SCHEMA_ARTIFACT_SHA256,
        "status": STATUS,
        "authority": AUTHORITY,
        "project_namespace": SYNTHETIC_PROJECT_NAMESPACE,
        "synthetic_quota": {
            "max_size": synthetic_max_size,
            "max_files": synthetic_max_files,
            "account_quota_authenticated": False,
        },
        "transport": {
            "transport_id": transport_load.transport_id,
            "transport_hash": transport_load.transport_hash,
            "transport_artifact_sha256": (
                transport_load.transport_artifact_sha256
            ),
            "transport_index_key": transport_load.transport_index_key,
        },
        "objects": [_descriptor_document(item) for item in objects],
        "census": {
            "total_object_count": transport_load.total_object_count,
            "total_byte_count": transport_load.total_byte_count,
            "total_row_count": transport_load.total_row_count,
        },
        "truth": {
            "synthetic_quota_observation": True,
            "real_account_quota_authenticated": False,
            "real_qc_object_store_access_performed": False,
        },
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
        "plan_id": None,
        "plan_hash": None,
    }


def _finalize_identity(
    value: dict[str, object],
    *,
    prefix: str,
    domain: str,
    id_key: str,
    hash_key: str,
) -> tuple[str, str, bytes, str]:
    seed = dict(value)
    identity = dict(seed)
    if id_key not in identity or hash_key not in identity:
        raise _PINNED_ERROR_CLASS("identity fields are incomplete")
    identity[id_key] = None
    identity[hash_key] = None
    semantic_hash = hashlib.sha256(
        domain.encode("ascii") + b"\x00" + _canonical_bytes(identity)
    ).hexdigest()
    artifact_id = f"{prefix}-{semantic_hash[:16]}"
    seed[id_key] = artifact_id
    seed[hash_key] = semantic_hash
    payload = _canonical_bytes(seed)
    return artifact_id, semantic_hash, payload, hashlib.sha256(payload).hexdigest()


def _false_authority(value: object) -> bool:
    try:
        if not _registry_topology_is_exact(
            value.external_bindings, value.capabilities
        ):
            return False
        return all(getattr(value, name) is False for name in FALSE_PROPERTY_NAMES)
    except (AttributeError, TypeError, ValueError):
        return False


def build_synthetic_qc_object_store_read_plan(
    *,
    run_candidate: SyntheticQcRunCandidate,
    object_store: SyntheticObjectStoreFixture,
    transport_index_key: str,
    synthetic_max_size: int,
    synthetic_max_files: int,
) -> SyntheticQcObjectStoreReadPlan:
    """Authenticate B3 and freeze an exact nine-key synthetic read plan."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    max_size = _require_exact_positive_int(synthetic_max_size, "synthetic_max_size")
    max_files = _require_exact_positive_int(
        synthetic_max_files, "synthetic_max_files"
    )
    try:
        transport_load = (
            load_synthetic_qc_global_input_bundle_from_object_store_fixture(
                run_candidate=run_candidate,
                object_store=object_store,
                transport_index_key=transport_index_key,
            )
        )
        require_synthetic_qc_transport_load(transport_load)
    except (QcSyntheticInputTransportError, TypeError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS(
            "B3 fixture is not authenticated"
        ) from exc
    if max_files < transport_load.total_object_count:
        raise _PINNED_ERROR_CLASS(
            "synthetic_max_files is below the authenticated object census"
        )
    if max_size < transport_load.total_byte_count:
        raise _PINNED_ERROR_CLASS(
            "synthetic_max_size is below the authenticated byte census"
        )
    if (
        type(object_store) is not SyntheticObjectStoreFixture
        or type(object_store.entries) is not tuple
        or tuple(item.key for item in object_store.entries)
        != transport_load.resolved_fixture_keys
    ):
        raise _PINNED_ERROR_CLASS(
            "authenticated B3 fixture changed during plan construction"
        )
    objects = tuple(
        SyntheticObjectStoreReadDescriptor(
            ordinal=ordinal,
            logical_key=_require_safe_key(entry.key, "logical_key"),
            object_store_key=_require_safe_key(
                f"{SYNTHETIC_PROJECT_NAMESPACE}/{entry.key}",
                "object_store_key",
            ),
            byte_count=len(entry.payload),
            artifact_sha256=hashlib.sha256(entry.payload).hexdigest(),
        )
        for ordinal, entry in enumerate(object_store.entries, start=1)
    )
    if any(
        item.logical_key.startswith(f"{SYNTHETIC_PROJECT_NAMESPACE}/")
        or not item.object_store_key.startswith(
            f"{SYNTHETIC_PROJECT_NAMESPACE}/"
        )
        for item in objects
    ):
        raise _PINNED_ERROR_CLASS(
            "synthetic project namespace must be applied exactly once"
        )
    seed = _plan_seed_document(
        transport_load=transport_load,
        synthetic_max_size=max_size,
        synthetic_max_files=max_files,
        objects=objects,
    )
    plan_id, plan_hash, canonical, artifact_hash = _finalize_identity(
        seed,
        prefix="arv2-qc-object-store-read-plan",
        domain=HASH_DOMAIN,
        id_key="plan_id",
        hash_key="plan_hash",
    )
    plan = SyntheticQcObjectStoreReadPlan(
        plan_id=plan_id,
        plan_hash=plan_hash,
        plan_artifact_sha256=artifact_hash,
        project_namespace=SYNTHETIC_PROJECT_NAMESPACE,
        synthetic_max_size=max_size,
        synthetic_max_files=max_files,
        transport_id=transport_load.transport_id,
        transport_hash=transport_load.transport_hash,
        transport_artifact_sha256=transport_load.transport_artifact_sha256,
        transport_index_key=transport_load.transport_index_key,
        objects=objects,
        total_object_count=transport_load.total_object_count,
        total_byte_count=transport_load.total_byte_count,
        total_row_count=transport_load.total_row_count,
        synthetic_quota_observation=True,
        real_account_quota_authenticated=False,
        real_qc_object_store_access_performed=False,
        external_bindings=EXTERNAL_BINDINGS,
        capabilities=CAPABILITIES,
        _run_candidate=run_candidate,
        _fixture=_copy_fixture(object_store),
        _canonical_document=canonical,
    )
    if not _false_authority(plan):
        raise _PINNED_ERROR_CLASS("constructed read plan gained authority")
    return plan


def _plan_public_tuple(value: SyntheticQcObjectStoreReadPlan) -> tuple[object, ...]:
    return tuple(
        getattr(value, field.name)
        for field in dataclasses.fields(SyntheticQcObjectStoreReadPlan)
        if not field.name.startswith("_")
    )


def require_synthetic_qc_object_store_read_plan(
    value: SyntheticQcObjectStoreReadPlan,
) -> SyntheticQcObjectStoreReadPlan:
    """Reauthenticate a retained synthetic read plan from its B3 fixture."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    if type(value) is not SyntheticQcObjectStoreReadPlan:
        raise _PINNED_ERROR_CLASS("read plan changed type")
    if not _plan_topology_is_exact(value):
        raise _PINNED_ERROR_CLASS("read plan topology changed")
    try:
        _require_sha256(value.plan_hash, "plan_hash")
        _require_sha256(value.plan_artifact_sha256, "plan_artifact_sha256")
        _require_exact_positive_int(value.synthetic_max_size, "synthetic_max_size")
        _require_exact_positive_int(value.synthetic_max_files, "synthetic_max_files")
        _require_nonnegative_int(value.total_object_count, "total_object_count")
        _require_nonnegative_int(value.total_byte_count, "total_byte_count")
        _require_nonnegative_int(value.total_row_count, "total_row_count")
    except (AttributeError, TypeError) as exc:
        raise _PINNED_ERROR_CLASS("read plan topology changed") from exc
    if (
        value.project_namespace != SYNTHETIC_PROJECT_NAMESPACE
        or type(value.objects) is not tuple
        or len(value.objects) != EXPECTED_OBJECT_COUNT
        or value.total_object_count != EXPECTED_OBJECT_COUNT
        or value.synthetic_quota_observation is not True
        or value.real_account_quota_authenticated is not False
        or value.real_qc_object_store_access_performed is not False
        or not _false_authority(value)
    ):
        raise _PINNED_ERROR_CLASS("read plan contract changed")
    for ordinal, item in enumerate(value.objects, start=1):
        if (
            type(item) is not SyntheticObjectStoreReadDescriptor
            or type(item.ordinal) is not int
            or item.ordinal != ordinal
            or type(item.byte_count) is not int
            or item.byte_count < 0
            or _require_safe_key(item.logical_key, "logical_key")
            != item.logical_key
            or _require_safe_key(item.object_store_key, "object_store_key")
            != item.object_store_key
            or item.object_store_key
            != f"{SYNTHETIC_PROJECT_NAMESPACE}/{item.logical_key}"
            or item.logical_key.startswith(f"{SYNTHETIC_PROJECT_NAMESPACE}/")
            or _require_sha256(item.artifact_sha256, "artifact_sha256")
            != item.artifact_sha256
        ):
            raise _PINNED_ERROR_CLASS("read descriptor changed")
    try:
        rebuilt = build_synthetic_qc_object_store_read_plan(
            run_candidate=value._run_candidate,
            object_store=value._fixture,
            transport_index_key=value.transport_index_key,
            synthetic_max_size=value.synthetic_max_size,
            synthetic_max_files=value.synthetic_max_files,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS("read plan backing state changed") from exc
    if (
        _plan_public_tuple(value) != _plan_public_tuple(rebuilt)
        or type(value._canonical_document) is not bytes
        or value._canonical_document != rebuilt._canonical_document
    ):
        raise _PINNED_ERROR_CLASS("read plan changed after construction")
    return value


def _transcript_seed_document(
    *,
    plan: SyntheticQcObjectStoreReadPlan,
    events: tuple[SyntheticObjectStoreReadEvent, ...],
) -> dict[str, object]:
    return {
        "schema_id": SCHEMA_ID,
        "plan_id": plan.plan_id,
        "plan_hash": plan.plan_hash,
        "events": [
            {
                "ordinal": item.ordinal,
                "operation": item.operation,
                "object_store_key": item.object_store_key,
                "found": item.found,
                "payload_byte_count": (
                    None if item.payload is None else len(item.payload)
                ),
                "payload_sha256": (
                    None
                    if item.payload is None
                    else hashlib.sha256(item.payload).hexdigest()
                ),
            }
            for item in events
        ],
        "truth": {
            "synthetic_fixture_transcript": True,
            "real_qc_object_store_access_performed": False,
        },
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
        "transcript_id": None,
        "transcript_hash": None,
    }


def _new_transcript(
    *,
    plan: SyntheticQcObjectStoreReadPlan,
    events: tuple[SyntheticObjectStoreReadEvent, ...],
) -> SyntheticQcObjectStoreReadTranscript:
    seed = _transcript_seed_document(plan=plan, events=events)
    transcript_id, transcript_hash, canonical, artifact_hash = _finalize_identity(
        seed,
        prefix="arv2-qc-object-store-read-transcript",
        domain=TRANSCRIPT_HASH_DOMAIN,
        id_key="transcript_id",
        hash_key="transcript_hash",
    )
    return SyntheticQcObjectStoreReadTranscript(
        transcript_id=transcript_id,
        transcript_hash=transcript_hash,
        transcript_artifact_sha256=artifact_hash,
        plan_id=plan.plan_id,
        plan_hash=plan.plan_hash,
        events=events,
        synthetic_fixture_transcript=True,
        real_qc_object_store_access_performed=False,
        external_bindings=EXTERNAL_BINDINGS,
        capabilities=CAPABILITIES,
        _canonical_document=canonical,
    )


def build_synthetic_qc_object_store_read_transcript(
    *, plan: SyntheticQcObjectStoreReadPlan
) -> SyntheticQcObjectStoreReadTranscript:
    """Build the exact value-only 18-event transcript for a retained plan."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    require_synthetic_qc_object_store_read_plan(plan)
    events: list[SyntheticObjectStoreReadEvent] = []
    for descriptor, entry in zip(plan.objects, plan._fixture.entries, strict=True):
        events.append(
            SyntheticObjectStoreReadEvent(
                ordinal=len(events) + 1,
                operation=CONTAINS_KEY_OPERATION,
                object_store_key=descriptor.object_store_key,
                found=True,
                payload=None,
            )
        )
        events.append(
            SyntheticObjectStoreReadEvent(
                ordinal=len(events) + 1,
                operation=READ_BYTES_OPERATION,
                object_store_key=descriptor.object_store_key,
                found=None,
                payload=bytes(entry.payload),
            )
        )
    transcript = _new_transcript(plan=plan, events=tuple(events))
    if transcript.real_qc_object_store_access_performed is not False:
        raise _PINNED_ERROR_CLASS(
            "constructed transcript gained Object Store authority"
        )
    return transcript


def _validate_transcript_events(
    *,
    plan: SyntheticQcObjectStoreReadPlan,
    transcript: SyntheticQcObjectStoreReadTranscript,
) -> tuple[bytes, ...]:
    if type(transcript.events) is not tuple or len(transcript.events) != (
        EXPECTED_EVENT_COUNT
    ):
        raise _PINNED_ERROR_CLASS("transcript event census changed")
    payloads: list[bytes] = []
    for object_ordinal, (descriptor, fixture_entry) in enumerate(
        zip(plan.objects, plan._fixture.entries, strict=True), start=1
    ):
        contains_event = transcript.events[(object_ordinal - 1) * 2]
        read_event = transcript.events[(object_ordinal - 1) * 2 + 1]
        if (
            type(contains_event) is not SyntheticObjectStoreReadEvent
            or type(read_event) is not SyntheticObjectStoreReadEvent
            or contains_event.ordinal != (object_ordinal - 1) * 2 + 1
            or read_event.ordinal != (object_ordinal - 1) * 2 + 2
            or contains_event.operation != CONTAINS_KEY_OPERATION
            or read_event.operation != READ_BYTES_OPERATION
            or contains_event.object_store_key != descriptor.object_store_key
            or read_event.object_store_key != descriptor.object_store_key
            or type(contains_event.found) is not bool
            or contains_event.found is not True
            or contains_event.payload is not None
            or read_event.found is not None
            or type(read_event.payload) is not bytes
        ):
            raise _PINNED_ERROR_CLASS(
                "transcript must alternate exact contains_key/read_bytes events"
            )
        payload = read_event.payload
        if (
            len(payload) != descriptor.byte_count
            or hashlib.sha256(payload).hexdigest() != descriptor.artifact_sha256
            or payload != fixture_entry.payload
        ):
            raise _PINNED_ERROR_CLASS(
                "transcript payload does not match the authenticated plan"
            )
        payloads.append(bytes(payload))
    return tuple(payloads)


def require_synthetic_qc_object_store_read_transcript(
    value: SyntheticQcObjectStoreReadTranscript,
    *,
    plan: SyntheticQcObjectStoreReadPlan,
) -> SyntheticQcObjectStoreReadTranscript:
    """Reauthenticate a caller-supplied synthetic transcript against a plan."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    require_synthetic_qc_object_store_read_plan(plan)
    if type(value) is not SyntheticQcObjectStoreReadTranscript:
        raise _PINNED_ERROR_CLASS("read transcript changed type")
    if not _transcript_topology_is_exact(value):
        raise _PINNED_ERROR_CLASS("read transcript topology changed")
    try:
        _require_sha256(value.transcript_hash, "transcript_hash")
        _require_sha256(
            value.transcript_artifact_sha256, "transcript_artifact_sha256"
        )
    except (AttributeError, TypeError) as exc:
        raise _PINNED_ERROR_CLASS("read transcript topology changed") from exc
    if (
        value.plan_id != plan.plan_id
        or value.plan_hash != plan.plan_hash
        or value.synthetic_fixture_transcript is not True
        or value.real_qc_object_store_access_performed is not False
        or value.external_bindings != EXTERNAL_BINDINGS
        or value.capabilities != CAPABILITIES
        or any(binding is not None for _, binding in value.external_bindings)
        or any(enabled is not False for _, enabled in value.capabilities)
    ):
        raise _PINNED_ERROR_CLASS("read transcript contract changed")
    _validate_transcript_events(plan=plan, transcript=value)
    rebuilt = _new_transcript(plan=plan, events=value.events)
    comparable = (
        "transcript_id",
        "transcript_hash",
        "transcript_artifact_sha256",
        "plan_id",
        "plan_hash",
        "events",
        "synthetic_fixture_transcript",
        "real_qc_object_store_access_performed",
        "external_bindings",
        "capabilities",
        "_canonical_document",
    )
    if any(getattr(value, name) != getattr(rebuilt, name) for name in comparable):
        raise _PINNED_ERROR_CLASS(
            "read transcript changed after construction"
        )
    return value


def _receipt_identity(
    *, plan: SyntheticQcObjectStoreReadPlan, transcript: SyntheticQcObjectStoreReadTranscript
) -> tuple[str, str]:
    digest = hashlib.sha256(
        b"arv2-qc-object-store-read-receipt-v1\x00"
        + plan.plan_hash.encode("ascii")
        + b"\x00"
        + transcript.transcript_hash.encode("ascii")
    ).hexdigest()
    return f"arv2-qc-object-store-read-receipt-{digest[:16]}", digest


def load_synthetic_qc_global_input_bundle_from_object_store_transcript(
    *,
    plan: SyntheticQcObjectStoreReadPlan,
    transcript: SyntheticQcObjectStoreReadTranscript,
) -> SyntheticQcObjectStoreReadReceipt:
    """Validate value events, reconstruct B3, and delegate to B3's loader."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    require_synthetic_qc_object_store_read_plan(plan)
    require_synthetic_qc_object_store_read_transcript(transcript, plan=plan)
    payloads = _validate_transcript_events(plan=plan, transcript=transcript)
    reconstructed = SyntheticObjectStoreFixture(
        transport_index_key=plan.transport_index_key,
        entries=tuple(
            SyntheticObjectStoreEntry(key=item.logical_key, payload=payload)
            for item, payload in zip(plan.objects, payloads, strict=True)
        ),
    )
    try:
        transport_load = (
            load_synthetic_qc_global_input_bundle_from_object_store_fixture(
                run_candidate=plan._run_candidate,
                object_store=reconstructed,
                transport_index_key=plan.transport_index_key,
            )
        )
        require_synthetic_qc_transport_load(transport_load)
    except (QcSyntheticInputTransportError, TypeError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS(
            "reconstructed B3 fixture is not authenticated"
        ) from exc
    if (
        transport_load.transport_id != plan.transport_id
        or transport_load.transport_hash != plan.transport_hash
        or transport_load.transport_artifact_sha256
        != plan.transport_artifact_sha256
        or transport_load.resolved_fixture_keys
        != tuple(item.logical_key for item in plan.objects)
    ):
        raise _PINNED_ERROR_CLASS("reconstructed B3 lineage changed")
    receipt_id, receipt_hash = _receipt_identity(plan=plan, transcript=transcript)
    receipt = SyntheticQcObjectStoreReadReceipt(
        receipt_id=receipt_id,
        receipt_hash=receipt_hash,
        plan_id=plan.plan_id,
        plan_hash=plan.plan_hash,
        transcript_id=transcript.transcript_id,
        transcript_hash=transcript.transcript_hash,
        object_store_keys=tuple(item.object_store_key for item in plan.objects),
        transport_load=transport_load,
        total_object_count=plan.total_object_count,
        total_byte_count=plan.total_byte_count,
        total_row_count=plan.total_row_count,
        synthetic_read_contract_validated=True,
        real_account_quota_authenticated=False,
        real_qc_object_store_access_performed=False,
        external_bindings=EXTERNAL_BINDINGS,
        capabilities=CAPABILITIES,
        _plan=plan,
        _transcript=transcript,
    )
    if not _false_authority(receipt):
        raise _PINNED_ERROR_CLASS("constructed receipt gained authority")
    return receipt


def require_synthetic_qc_object_store_read_receipt(
    value: SyntheticQcObjectStoreReadReceipt,
) -> SyntheticQcObjectStoreReadReceipt:
    """Reauthenticate a retained receipt by replaying its retained values."""

    _PINNED_REQUIRE_STATIC_CONTRACT()
    if type(value) is not SyntheticQcObjectStoreReadReceipt:
        raise _PINNED_ERROR_CLASS("read receipt changed type")
    if not _receipt_topology_is_exact(value):
        raise _PINNED_ERROR_CLASS("read receipt topology changed")
    try:
        rebuilt = load_synthetic_qc_global_input_bundle_from_object_store_transcript(
            plan=value._plan,
            transcript=value._transcript,
        )
        require_synthetic_qc_transport_load(value.transport_load)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _PINNED_ERROR_CLASS("read receipt backing state changed") from exc
    comparable = tuple(
        field.name
        for field in dataclasses.fields(SyntheticQcObjectStoreReadReceipt)
        if not field.name.startswith("_") and field.name != "transport_load"
    )
    if (
        any(getattr(value, name) != getattr(rebuilt, name) for name in comparable)
        or value.transport_load.transport_id != rebuilt.transport_load.transport_id
        or value.transport_load.transport_hash != rebuilt.transport_load.transport_hash
        or value.transport_load.transport_artifact_sha256
        != rebuilt.transport_load.transport_artifact_sha256
        or value.synthetic_read_contract_validated is not True
        or value.real_account_quota_authenticated is not False
        or value.real_qc_object_store_access_performed is not False
        or not _false_authority(value)
    ):
        raise _PINNED_ERROR_CLASS(
            "read receipt changed after construction"
        )
    return value


_LOCAL_FUNCTION_STATES = tuple(
    (
        name,
        value,
        value.__code__,
        value.__defaults__,
        value.__kwdefaults__,
        value.__closure__,
    )
    for name, value in tuple(_MODULE_GLOBALS.items())
    if inspect.isfunction(value) and value.__module__ == __name__
)
_PINNED_LOCAL_FUNCTION_STATES = _LOCAL_FUNCTION_STATES

_CLASS_STATES = tuple(
    (accepted_class, tuple(vars(accepted_class).items()))
    for _, accepted_class in _PINNED_CLASSES
)
_PINNED_CLASS_STATES = _CLASS_STATES

_CLASS_FUNCTION_STATES = tuple(
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
    for _, accepted_class in _PINNED_CLASSES
    for member in vars(accepted_class).values()
    for implementation in (
        (member.fget,)
        if type(member) is property and member.fget is not None
        else (member,)
    )
    if inspect.isfunction(implementation)
)
_PINNED_CLASS_FUNCTION_STATES = _CLASS_FUNCTION_STATES

_builtin_resolution_bindings: list[tuple[dict, str, object]] = []
_seen_builtin_resolutions: set[tuple[int, str]] = set()
for _implementation in (
    *(state[1] for state in _LOCAL_FUNCTION_STATES),
    *(state[0] for state in _CLASS_FUNCTION_STATES),
):
    _pending_code = [_implementation.__code__]
    while _pending_code:
        _code = _pending_code.pop()
        for _name in _code.co_names:
            _resolution_identity = (id(_implementation.__globals__), _name)
            if (
                _resolution_identity not in _seen_builtin_resolutions
                and _name not in _implementation.__globals__
                and _name in _PINNED_BUILTINS_DICT
            ):
                _seen_builtin_resolutions.add(_resolution_identity)
                _builtin_resolution_bindings.append(
                    (
                        _implementation.__globals__,
                        _name,
                        _PINNED_BUILTINS_DICT[_name],
                    )
                )
        _pending_code.extend(
            value
            for value in _code.co_consts
            if type(value) is _PINNED_CODE_TYPE
        )
_BUILTIN_RESOLUTION_BINDINGS = tuple(_builtin_resolution_bindings)
_PINNED_BUILTIN_RESOLUTION_BINDINGS = _BUILTIN_RESOLUTION_BINDINGS
del (
    _builtin_resolution_bindings,
    _seen_builtin_resolutions,
    _implementation,
    _pending_code,
    _code,
    _name,
    _resolution_identity,
)
