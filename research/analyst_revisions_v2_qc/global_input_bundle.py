"""Strict in-memory admission of synthetic ARV2 QC input partitions.

This module is the offline bridge between the reviewed global-input wire
schema and the reviewed deterministic event-study core.  It accepts only
caller-supplied exact bytes for the seven synthetic partitions, authenticates
them against the synthetic manifest and run candidate, decodes their exact
tagged-JSONL row contracts, and exposes one pure composition function.

It has no filesystem, environment, provider, Object Store, QuantConnect,
result, deployment, order, or trading surface.  In particular, accepting a
synthetic payload proves neither production truth nor rights, point-in-time
provenance, runtime code identity, real-outcome authority, or permission to
start or inspect a backtest.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from types import MappingProxyType, ModuleType

from .event_study import (
    BenchmarkOpenValue,
    DecisionRow,
    EventStudyBatch,
    EventStudyObservation,
    EventStudyRefusal,
    EventStudyInputError,
    SecurityLifecycleCoverage,
    SecurityOpenValue,
    TerminalLifecycle,
    TerminalRequirement,
    TerminalShareholderPayoff,
    build_synthetic_partition_binding,
    collect_synthetic_event_study,
    require_synthetic_event_study_batch,
)
from .global_input_schema import (
    GlobalInputPartitionDescriptor,
    ROLE_ORDER,
    ROW_CONTRACTS,
    SCHEMA_ARTIFACT_SHA256 as GLOBAL_INPUT_SCHEMA_ARTIFACT_SHA256,
    SCHEMA_ID as GLOBAL_INPUT_SCHEMA_ID,
    SCHEMA_SHA256 as GLOBAL_INPUT_SCHEMA_SHA256,
    TERMINAL_LIFECYCLE_FIELDS,
    TERMINAL_LIFECYCLE_WIRE_TYPES,
    QcGlobalInputSchemaError,
    RowContract,
    SyntheticQcGlobalInputManifest,
    load_synthetic_qc_global_input_manifest_bytes,
    render_qc_global_input_schema_bytes,
)
from .run_contract import (
    CodeFileBinding,
    QcRunContractError,
    EvaluationWindow,
    ParentArtifact,
    SyntheticPartitionBinding,
    SyntheticQcRunCandidate,
    require_synthetic_qc_run_candidate,
)


class QcGlobalInputBundleError(ValueError):
    """A synthetic payload bundle is malformed, changed, or unauthorized."""


_PINNED_BUNDLE_ERROR = QcGlobalInputBundleError
_PINNED_DATACLASSES_MODULE = dataclasses
_PINNED_HASHLIB_MODULE = hashlib
_PINNED_JSON_MODULE = json
_PINNED_RE_MODULE = re
_PINNED_ANY = any
_PINNED_DICT_ITEMS = dict.items
_PINNED_LEN = len
_PINNED_STR = str
_PINNED_TYPE = type
_PINNED_OBJECT = object
_PINNED_OBJECT_GETATTRIBUTE = object.__getattribute__
_PINNED_TUPLE = tuple
_PINNED_TUPLE_GETITEM = tuple.__getitem__
_PINNED_TUPLE_LEN = tuple.__len__
_PINNED_ZIP = zip


SCHEMA = "arv2-qc-global-input-bundle-schema-v1"
SCHEMA_ID = "arv2-qc-global-input-bundle-schema-78e279a8b81c5be4"
SCHEMA_SHA256 = (
    "78e279a8b81c5be484b93f20600aba5c45f0c4524e06eaed60c378a53b085a90"
)
SCHEMA_ARTIFACT_SHA256 = (
    "a3211d2a24a033d7dc70904414a9767b8430c590e29ab435729a894455116d6f"
)
STATUS = "offline_synthetic_fixture_payloads_only_not_production_admission"
AUTHORITY = (
    "exact_in_memory_synthetic_payload_decode_and_pure_core_composition_only_"
    "no_production_truth_rights_outcome_qc_result_or_trading_authority"
)
BUNDLE_HASH_DOMAIN = "arv2-qc-global-input-bundle-v1"
ENCODING = "canonical_tagged_jsonl_strict_utf8_lf-v1"
GLOBAL_INPUT_SCHEMA_SOURCE_SHA256 = (
    "f0da3f016cdd794514146a7811d3606b3c8be9d94ffca80e1c28790af519016a"
)
GLOBAL_INPUT_SCHEMA_SOURCE_BYTE_COUNT = 94_959
MAX_SYNTHETIC_PARTITION_BYTES = 67_108_864
MAX_SYNTHETIC_BUNDLE_BYTES = 268_435_456
MAX_SYNTHETIC_PARTITION_ROWS = 2_000_000
MAX_SYNTHETIC_BUNDLE_ROWS = 5_000_000
MAX_SYNTHETIC_ROW_BYTES = 1_048_576
MAX_JSON_DEPTH = 16
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")

PARTITION_PAYLOAD_FIELDS = ("role", "payload")
RUN_CANDIDATE_FIELDS = (
    "candidate_id",
    "candidate_hash",
    "code_files",
    "synthetic_partitions",
    "external_bindings",
    "capabilities",
    "_canonical_document",
)
EVENT_STUDY_BATCH_FIELDS = (
    "observations",
    "refusals",
    "security_lifecycle_coverages",
    "expected_decision_horizons",
    "candidate_declaration_hash",
    "terminal_payoff_reinvestment_policy_id",
    "input_partition_set_sha256",
    "batch_hash",
)
EVENT_STUDY_OBSERVATION_FIELDS = tuple(
    field.name for field in dataclasses.fields(EventStudyObservation)
)
EVENT_STUDY_REFUSAL_FIELDS = tuple(
    field.name for field in dataclasses.fields(EventStudyRefusal)
)
SECURITY_LIFECYCLE_COVERAGE_FIELDS = tuple(
    field.name for field in dataclasses.fields(SecurityLifecycleCoverage)
)
TERMINAL_LIFECYCLE_OUTPUT_FIELDS = tuple(
    field.name for field in dataclasses.fields(TerminalLifecycle)
)
EVENT_STUDY_BATCH_METHOD_NAMES = ("aggregate_census",)
BUNDLE_FIELDS = (
    "bundle_id",
    "bundle_hash",
    "bundle_artifact_sha256",
    "schema_id",
    "schema_sha256",
    "schema_artifact_sha256",
    "manifest_id",
    "manifest_sha256",
    "manifest_artifact_sha256",
    "run_candidate_id",
    "run_candidate_hash",
    "session_axis",
    "decisions",
    "security_opens",
    "benchmark_opens",
    "security_lifecycle_coverages",
    "terminal_requirements",
    "terminal_payoffs",
    "partition_payloads",
    "total_byte_count",
    "total_row_count",
    "caller_declared_synthetic_bytes_match_manifest",
    "row_contracts_validated",
    "external_bindings",
    "capabilities",
    "_manifest_bytes",
    "_run_candidate",
    "_canonical_document",
)
BUNDLE_DOCUMENT_ROOT_FIELDS = (
    "schema",
    "status",
    "authority",
    "bundle_id",
    "bundle_hash",
    "schema_binding",
    "manifest_binding",
    "run_candidate_binding",
    "payload_validation",
    "partitions",
    "partition_census",
    "external_bindings",
    "capabilities",
)
BUNDLE_DOCUMENT_NESTED_FIELDS = (
    ("schema_binding", ("schema_id", "schema_sha256", "schema_artifact_sha256")),
    (
        "manifest_binding",
        ("manifest_id", "manifest_sha256", "manifest_artifact_sha256"),
    ),
    (
        "run_candidate_binding",
        ("candidate_id", "candidate_hash", "runtime_code_authenticated"),
    ),
    (
        "payload_validation",
        (
            "caller_declared_synthetic_bytes_match_manifest",
            "row_wire_contracts_validated",
            "canonical_order_validated",
            "canonical_rerender_validated",
            "production_truth_authenticated",
            "rights_authenticated",
            "point_in_time_provenance_authenticated",
            "row_source_provenance_authenticated",
            "real_outcome_authority",
            "synthetic_provenance_authenticated",
        ),
    ),
    (
        "partition_census",
        ("role_count", "total_byte_count", "total_row_count"),
    ),
)
BUNDLE_PARTITION_DOCUMENT_FIELDS = (
    "ordinal",
    "role",
    "partition_id",
    "row_schema",
    "immutable_artifact_id",
    "byte_count",
    "row_count",
    "artifact_sha256",
)
BUNDLE_FALSE_PROPERTY_NAMES = (
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
EVENT_STUDY_FALSE_PROPERTY_NAMES = (
    "result_publication_available",
    "execution_code_authenticated",
    "orders_available",
    "trading_available",
)
RUN_CANDIDATE_FALSE_PROPERTY_NAMES = (
    "upload_available",
    "execution_code_authenticated",
    "compile_available",
    "launch_available",
    "result_access_available",
    "deployment_available",
    "orders_available",
    "trading_available",
)
CLASS_TOPOLOGY_MEMBER_NAMES = (
    "__qualname__",
    "__dataclass_fields__",
    "__new__",
    "__init__",
    "__getattribute__",
    "__setattr__",
    "__delattr__",
    "__eq__",
)

_EXPECTED_ROLE_ORDER = (
    "session_axis",
    "decision_rows",
    "security_open_values",
    "benchmark_open_values",
    "security_lifecycle_coverages",
    "terminal_requirements",
    "terminal_shareholder_payoffs",
)

_EXPECTED_ROW_CONTRACTS = tuple(
    (
        item.role,
        item.row_schema,
        item.record_type,
        item.root_envelope,
        tuple(item.fields),
        tuple(item.wire_types),
        tuple(item.canonical_order),
    )
    for item in ROW_CONTRACTS
)

_EXPECTED_TERMINAL_LIFECYCLE = (
    tuple(TERMINAL_LIFECYCLE_FIELDS),
    tuple(TERMINAL_LIFECYCLE_WIRE_TYPES),
)

_PINNED_EXPECTED_ROLE_ORDER = _EXPECTED_ROLE_ORDER
_PINNED_EXPECTED_ROW_CONTRACTS = _EXPECTED_ROW_CONTRACTS
_PINNED_EXPECTED_TERMINAL_LIFECYCLE = _EXPECTED_TERMINAL_LIFECYCLE
_PINNED_ROLE_ORDER_ROOT = ROLE_ORDER
_PINNED_ROW_CONTRACTS_ROOT = ROW_CONTRACTS
_PINNED_TERMINAL_LIFECYCLE_FIELDS_ROOT = TERMINAL_LIFECYCLE_FIELDS
_PINNED_TERMINAL_LIFECYCLE_WIRE_TYPES_ROOT = TERMINAL_LIFECYCLE_WIRE_TYPES
_PINNED_HEX_64 = _HEX_64
_PINNED_PARTITION_PAYLOAD_FIELDS = PARTITION_PAYLOAD_FIELDS
_PINNED_RUN_CANDIDATE_FIELDS = RUN_CANDIDATE_FIELDS
_PINNED_EVENT_STUDY_BATCH_FIELDS = EVENT_STUDY_BATCH_FIELDS
_PINNED_EVENT_STUDY_OBSERVATION_FIELDS = EVENT_STUDY_OBSERVATION_FIELDS
_PINNED_EVENT_STUDY_REFUSAL_FIELDS = EVENT_STUDY_REFUSAL_FIELDS
_PINNED_SECURITY_LIFECYCLE_COVERAGE_FIELDS = (
    SECURITY_LIFECYCLE_COVERAGE_FIELDS
)
_PINNED_TERMINAL_LIFECYCLE_OUTPUT_FIELDS = TERMINAL_LIFECYCLE_OUTPUT_FIELDS
_PINNED_EVENT_STUDY_BATCH_METHOD_NAMES = EVENT_STUDY_BATCH_METHOD_NAMES
_PINNED_BUNDLE_FIELDS = BUNDLE_FIELDS
_PINNED_BUNDLE_DOCUMENT_ROOT_FIELDS = BUNDLE_DOCUMENT_ROOT_FIELDS
_PINNED_BUNDLE_DOCUMENT_NESTED_FIELDS = BUNDLE_DOCUMENT_NESTED_FIELDS
_PINNED_BUNDLE_PARTITION_DOCUMENT_FIELDS = BUNDLE_PARTITION_DOCUMENT_FIELDS
_PINNED_BUNDLE_FALSE_PROPERTY_NAMES = BUNDLE_FALSE_PROPERTY_NAMES
_PINNED_EVENT_STUDY_FALSE_PROPERTY_NAMES = EVENT_STUDY_FALSE_PROPERTY_NAMES
_PINNED_RUN_CANDIDATE_FALSE_PROPERTY_NAMES = (
    RUN_CANDIDATE_FALSE_PROPERTY_NAMES
)
_PINNED_CLASS_TOPOLOGY_MEMBER_NAMES = CLASS_TOPOLOGY_MEMBER_NAMES
_PINNED_DATE = date
_PINNED_DECIMAL = Decimal
_PINNED_DECISION_ROW = DecisionRow
_PINNED_SECURITY_OPEN_VALUE = SecurityOpenValue
_PINNED_BENCHMARK_OPEN_VALUE = BenchmarkOpenValue
_PINNED_SECURITY_LIFECYCLE_COVERAGE = SecurityLifecycleCoverage
_PINNED_TERMINAL_LIFECYCLE = TerminalLifecycle
_PINNED_TERMINAL_REQUIREMENT = TerminalRequirement
_PINNED_TERMINAL_SHAREHOLDER_PAYOFF = TerminalShareholderPayoff
_PINNED_EVENT_STUDY_BATCH = EventStudyBatch
_PINNED_EVENT_STUDY_OBSERVATION = EventStudyObservation
_PINNED_EVENT_STUDY_REFUSAL = EventStudyRefusal
_PINNED_ROW_CONTRACT = RowContract
_PINNED_PARENT_ARTIFACT = ParentArtifact
_PINNED_CODE_FILE_BINDING = CodeFileBinding
_PINNED_PARTITION_BINDING = SyntheticPartitionBinding
_PINNED_EVALUATION_WINDOW = EvaluationWindow
_PINNED_RUN_CANDIDATE = SyntheticQcRunCandidate
_PINNED_MANIFEST_CLASS = SyntheticQcGlobalInputManifest
_PINNED_DESCRIPTOR_CLASS = GlobalInputPartitionDescriptor
_PINNED_LOAD_MANIFEST = load_synthetic_qc_global_input_manifest_bytes
_PINNED_RENDER_GLOBAL_INPUT_SCHEMA = render_qc_global_input_schema_bytes
_PINNED_REQUIRE_CANDIDATE = require_synthetic_qc_run_candidate
_PINNED_BUILD_PARTITION_BINDING = build_synthetic_partition_binding
_PINNED_COLLECT_EVENT_STUDY = collect_synthetic_event_study
_PINNED_REQUIRE_EVENT_STUDY_BATCH = require_synthetic_event_study_batch
_PINNED_SHA256 = hashlib.sha256
_PINNED_JSON_DUMPS = json.dumps
_PINNED_JSON_LOADS = json.loads
_PINNED_JSON_DECODER_CLASS = json.JSONDecoder
_PINNED_JSON_ENCODER_CLASS = json.JSONEncoder
_PINNED_COUNTER_CLASS = Counter
_PINNED_DATACLASS_FIELDS = dataclasses.fields
_PINNED_DATACLASS_FIELD_CLASS = dataclasses.Field
_PINNED_DATACLASS_FIELD_NAME_DESCRIPTOR = type.__getattribute__(
    dataclasses.Field,
    "__dict__",
)["name"]
_PINNED_DATACLASS_FIELD_TYPE_DESCRIPTOR = type.__getattribute__(
    dataclasses.Field,
    "__dict__",
)["_field_type"]
_PINNED_PROPERTY_TYPE = property
_PINNED_FUNCTION_TYPE = type(lambda: None)
_PINNED_MAPPING_PROXY_TYPE = MappingProxyType
_PINNED_MODULE_TYPE = ModuleType
_PINNED_INVALID_OPERATION = InvalidOperation
_PINNED_JSON_DECODE_ERROR = json.JSONDecodeError
_PINNED_GLOBAL_INPUT_SCHEMA_ERROR = QcGlobalInputSchemaError
_PINNED_RUN_CONTRACT_ERROR = QcRunContractError
_PINNED_EVENT_STUDY_INPUT_ERROR = EventStudyInputError
_PINNED_TYPE_ERROR = TypeError
_PINNED_VALUE_ERROR = ValueError
_PINNED_UNICODE_ERROR = UnicodeError
_PINNED_UNICODE_DECODE_ERROR = UnicodeDecodeError
_PINNED_RECURSION_ERROR = RecursionError
_PINNED_ATTRIBUTE_ERROR = AttributeError


def _schema_contract_document(
    *, schema_id: str | None, schema_sha256: str | None
) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "authority": AUTHORITY,
        "schema_id": schema_id,
        "schema_sha256": schema_sha256,
        "identity_recipe": {
            "schema_sha256": (
                "sha256(canonical_compact_json_with_schema_id_and_"
                "schema_sha256_null)"
            ),
            "schema_id": (
                "arv2-qc-global-input-bundle-schema-<first16_schema_sha256>"
            ),
            "artifact_sha256": "sha256(exact_rendered_schema_bytes)",
        },
        "accepted_parent": {
            "schema_id": GLOBAL_INPUT_SCHEMA_ID,
            "schema_sha256": GLOBAL_INPUT_SCHEMA_SHA256,
            "schema_artifact_sha256": GLOBAL_INPUT_SCHEMA_ARTIFACT_SHA256,
            "source_byte_count": GLOBAL_INPUT_SCHEMA_SOURCE_BYTE_COUNT,
            "source_sha256": GLOBAL_INPUT_SCHEMA_SOURCE_SHA256,
            "runtime_source_authenticated": False,
        },
        "payload_contract": {
            "role_order": list(_EXPECTED_ROLE_ORDER),
            "encoding": ENCODING,
            "exact_bytes_only": True,
            "manifest_bound": True,
            "candidate_bound": True,
            "descriptor_bound": True,
            "canonical_rerender_required": True,
            "row_contract_validation_required": True,
            "canonical_order_required": True,
            "complete_role_inventory_required": True,
        },
        "row_contracts": [
            {
                "role": role,
                "row_schema": row_schema,
                "record_type": record_type,
                "root_envelope": root_envelope,
                "fields": list(fields),
                "wire_types": list(wire_types),
                "canonical_order": list(canonical_order),
            }
            for (
                role,
                row_schema,
                record_type,
                root_envelope,
                fields,
                wire_types,
                canonical_order,
            ) in _EXPECTED_ROW_CONTRACTS
        ],
        "terminal_lifecycle_contract": {
            "record_type": "TerminalLifecycle",
            "fields": list(_EXPECTED_TERMINAL_LIFECYCLE[0]),
            "wire_types": list(_EXPECTED_TERMINAL_LIFECYCLE[1]),
        },
        "bundle_wire_contract": {
            "partition_payload_dataclass_fields": list(PARTITION_PAYLOAD_FIELDS),
            "bundle_dataclass_fields": list(BUNDLE_FIELDS),
            "root_fields": list(BUNDLE_DOCUMENT_ROOT_FIELDS),
            "nested_field_inventories": {
                name: list(fields)
                for name, fields in BUNDLE_DOCUMENT_NESTED_FIELDS
            },
            "partition_fields": list(BUNDLE_PARTITION_DOCUMENT_FIELDS),
            "identity_recipe": {
                "bundle_hash": (
                    "sha256(canonical_compact_json_with_bundle_id_and_"
                    "bundle_hash_null)"
                ),
                "bundle_id": (
                    "synthetic-arv2-qc-global-input-bundle-"
                    "<first16_bundle_hash>"
                ),
                "artifact_sha256": (
                    "sha256(exact_canonical_bundle_document_with_one_lf)"
                ),
            },
            "root_fixed_values": {
                "schema": BUNDLE_HASH_DOMAIN,
                "status": STATUS,
                "authority": AUTHORITY,
            },
            "payload_validation_fixed_values": {
                "caller_declared_synthetic_bytes_match_manifest": True,
                "row_wire_contracts_validated": True,
                "canonical_order_validated": True,
                "canonical_rerender_validated": True,
                "production_truth_authenticated": False,
                "rights_authenticated": False,
                "point_in_time_provenance_authenticated": False,
                "row_source_provenance_authenticated": False,
                "real_outcome_authority": False,
                "synthetic_provenance_authenticated": False,
            },
        },
        "resource_bounds": {
            "maximum_partition_bytes": MAX_SYNTHETIC_PARTITION_BYTES,
            "maximum_bundle_bytes": MAX_SYNTHETIC_BUNDLE_BYTES,
            "maximum_partition_rows": MAX_SYNTHETIC_PARTITION_ROWS,
            "maximum_bundle_rows": MAX_SYNTHETIC_BUNDLE_ROWS,
            "maximum_row_bytes": MAX_SYNTHETIC_ROW_BYTES,
            "maximum_json_depth": MAX_JSON_DEPTH,
        },
        "admitted_truth": {
            "caller_declared_synthetic_bytes_match_manifest": True,
            "row_wire_contracts_validated": True,
            "production_truth_authenticated": False,
            "rights_authenticated": False,
            "point_in_time_provenance_authenticated": False,
            "row_source_provenance_authenticated": False,
            "runtime_code_authenticated": False,
            "real_outcome_authority": False,
            "quantconnect_operation_authority": False,
            "result_access_authority": False,
            "synthetic_provenance_authenticated": False,
        },
        "transport": {
            "physical_transport": None,
            "filesystem_path": None,
            "qc_object_store_key": None,
            "qc_project_file_path": None,
            "lean_adapter": None,
            "qc_algorithm": None,
        },
    }


def _try_canonical_bytes(value: object, *, newline: bool = False) -> bytes | None:
    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        if newline:
            rendered += "\n"
        return rendered.encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return None


def _canonical_bytes(value: object, *, newline: bool = False) -> bytes:
    rendered = _try_canonical_bytes(value, newline=newline)
    if rendered is None:
        raise QcGlobalInputBundleError(
            "bundle value is not canonical JSON"
        ) from None
    return rendered


def _capture_dependency_value_authority(
    roots: tuple[object, ...],
) -> tuple[tuple[object, ...], tuple[tuple[object, type, tuple], ...]]:
    """Retain exact mutable dependency graphs without value equality."""

    retained_roots = tuple(roots)
    graph: list[tuple[object, type, tuple]] = []
    pending = list(reversed(retained_roots))
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        value_type = type(value)
        if (
            value_type not in _PINNED_DEPENDENCY_GRAPH_CONTAINER_TYPES
            and value_type not in _PINNED_DEPENDENCY_GRAPH_RECORD_TYPES
        ):
            continue
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        if value_type in (dict, _PINNED_MAPPING_PROXY_TYPE):
            edges = tuple(value.items())
            for key, item in edges:
                pending.append(key)
                pending.append(item)
        elif value_type in (tuple, list, set, frozenset):
            edges = tuple(value)
            pending.extend(edges)
        else:
            registry = type.__getattribute__(value_type, "__dict__")[
                "__dataclass_fields__"
            ]
            edges = tuple(
                (name, object.__getattribute__(value, name))
                for name in registry
            )
            pending.extend(item for _, item in edges)
        graph.append((value, value_type, edges))
    return retained_roots, tuple(graph)


def _dependency_value_authority_is_current(
    current_roots: tuple[object, ...],
    authority: tuple[tuple[object, ...], tuple[tuple[object, type, tuple], ...]],
) -> bool:
    """Authenticate exact container and frozen-record descendants by identity."""

    try:
        expected_roots, expected_graph = authority
        if (
            type(current_roots) is not tuple
            or type(expected_roots) is not tuple
            or type(expected_graph) is not tuple
            or len(current_roots) != len(expected_roots)
            or any(
                actual is not expected
                for actual, expected in zip(
                    current_roots,
                    expected_roots,
                    strict=True,
                )
            )
        ):
            return False
        expected_by_identity: dict[int, tuple[object, type, tuple]] = {}
        for value, value_type, edges in expected_graph:
            identity = id(value)
            if (
                identity in expected_by_identity
                or type(value) is not value_type
                or type(edges) is not tuple
            ):
                return False
            expected_by_identity[identity] = (value, value_type, edges)

        pending = list(reversed(expected_roots))
        seen: set[int] = set()
        while pending:
            value = pending.pop()
            value_type = type(value)
            if (
                value_type not in _PINNED_DEPENDENCY_GRAPH_CONTAINER_TYPES
                and value_type not in _PINNED_DEPENDENCY_GRAPH_RECORD_TYPES
            ):
                continue
            identity = id(value)
            expected = expected_by_identity.get(identity)
            if (
                expected is None
                or expected[0] is not value
                or expected[1] is not value_type
            ):
                return False
            if identity in seen:
                continue
            seen.add(identity)
            expected_edges = expected[2]
            if value_type in (dict, _PINNED_MAPPING_PROXY_TYPE):
                observed_edges = tuple(value.items())
                if len(observed_edges) != len(expected_edges):
                    return False
                for observed, expected_edge in zip(
                    observed_edges,
                    expected_edges,
                    strict=True,
                ):
                    if (
                        type(observed) is not tuple
                        or len(observed) != 2
                        or type(expected_edge) is not tuple
                        or len(expected_edge) != 2
                        or observed[0] is not expected_edge[0]
                        or observed[1] is not expected_edge[1]
                    ):
                        return False
                    pending.extend(observed)
            elif value_type in (tuple, list):
                observed_edges = tuple(value)
                if len(observed_edges) != len(expected_edges) or any(
                    observed is not expected_edge
                    for observed, expected_edge in zip(
                        observed_edges,
                        expected_edges,
                        strict=True,
                    )
                ):
                    return False
                pending.extend(observed_edges)
            elif value_type in (set, frozenset):
                observed_edges = tuple(value)
                if len(observed_edges) != len(expected_edges):
                    return False
                for observed in observed_edges:
                    if sum(
                        observed is expected_edge
                        for expected_edge in expected_edges
                    ) != 1:
                        return False
                pending.extend(observed_edges)
            else:
                if value_type not in _PINNED_DEPENDENCY_GRAPH_RECORD_TYPES:
                    return False
                observed_edges = tuple(
                    (
                        expected_edge[0],
                        object.__getattribute__(value, expected_edge[0]),
                    )
                    for expected_edge in expected_edges
                )
                if any(
                    observed[0] is not expected_edge[0]
                    or observed[1] is not expected_edge[1]
                    for observed, expected_edge in zip(
                        observed_edges,
                        expected_edges,
                        strict=True,
                    )
                ):
                    return False
                pending.extend(item for _, item in observed_edges)
        return len(seen) == len(expected_by_identity)
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
        return False


def _schema_identity_document() -> dict[str, object]:
    seed = _schema_contract_document(schema_id=None, schema_sha256=None)
    digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    return _schema_contract_document(
        schema_id=f"arv2-qc-global-input-bundle-schema-{digest[:16]}",
        schema_sha256=digest,
    )


_PINNED_SCHEMA_CONTRACT_DOCUMENT = _schema_contract_document
_PINNED_TRY_CANONICAL_BYTES = _try_canonical_bytes
_PINNED_CANONICAL_BYTES = _canonical_bytes
_PINNED_SCHEMA_IDENTITY_DOCUMENT = _schema_identity_document


def _require_static_contract() -> None:
    if (
        _BUILTIN_GLOBALS is not _PINNED_BUILTIN_GLOBALS
        or _BUILTIN_GLOBAL_ENTRIES
        is not _PINNED_BUILTIN_GLOBAL_ENTRIES
    ):
        raise _PINNED_BUNDLE_ERROR("bundle builtin topology changed")
    builtin_entry_count = 0
    for actual_entry in _PINNED_BUILTIN_GLOBALS.items():
        builtin_entry_count += 1
        matched_entry = False
        for expected_entry in _PINNED_BUILTIN_GLOBAL_ENTRIES:
            if actual_entry[0] is expected_entry[0]:
                matched_entry = actual_entry[1] is expected_entry[1]
                break
        if not matched_entry:
            raise _PINNED_BUNDLE_ERROR("bundle builtin topology changed")
    expected_builtin_entry_count = 0
    for _ in _PINNED_BUILTIN_GLOBAL_ENTRIES:
        expected_builtin_entry_count += 1
    if builtin_entry_count != expected_builtin_entry_count:
        raise _PINNED_BUNDLE_ERROR("bundle builtin topology changed")
    if (
        _BUILTIN_GLOBALS is not _PINNED_BUILTIN_GLOBALS
        or _PINNED_BUILTIN_GLOBALS.get("any") is not _PINNED_ANY
        or _PINNED_BUILTIN_GLOBALS.get("len") is not _PINNED_LEN
        or _PINNED_BUILTIN_GLOBALS.get("str") is not _PINNED_STR
        or _PINNED_BUILTIN_GLOBALS.get("type") is not _PINNED_TYPE
        or _PINNED_BUILTIN_GLOBALS.get("object") is not _PINNED_OBJECT
        or _PINNED_BUILTIN_GLOBALS.get("tuple") is not _PINNED_TUPLE
        or _PINNED_BUILTIN_GLOBALS.get("zip") is not _PINNED_ZIP
        or _PINNED_BUILTIN_GLOBALS.get("dict").items
        is not _PINNED_DICT_ITEMS
        or _PINNED_OBJECT_GETATTRIBUTE
        is not _PINNED_OBJECT.__getattribute__
        or _PINNED_TUPLE_GETITEM is not _PINNED_TUPLE.__getitem__
        or _PINNED_TUPLE_LEN is not _PINNED_TUPLE.__len__
        or ModuleType is not _PINNED_MODULE_TYPE
    ):
        raise _PINNED_BUNDLE_ERROR("bundle primitive topology changed")
    if (
        dataclasses is not _PINNED_DATACLASSES_MODULE
        or hashlib is not _PINNED_HASHLIB_MODULE
        or json is not _PINNED_JSON_MODULE
        or re is not _PINNED_RE_MODULE
        or _PINNED_OBJECT_GETATTRIBUTE(dataclasses, "__class__")
        is not _PINNED_MODULE_TYPE
        or _PINNED_OBJECT_GETATTRIBUTE(hashlib, "__class__")
        is not _PINNED_MODULE_TYPE
        or _PINNED_OBJECT_GETATTRIBUTE(json, "__class__")
        is not _PINNED_MODULE_TYPE
        or _PINNED_OBJECT_GETATTRIBUTE(re, "__class__")
        is not _PINNED_MODULE_TYPE
    ):
        raise _PINNED_BUNDLE_ERROR("bundle module binding changed")
    if (
        _BOOTSTRAP_MODULE_AUTHORITIES
        is not _PINNED_BOOTSTRAP_MODULE_AUTHORITIES
        or _PINNED_TYPE(_PINNED_BOOTSTRAP_MODULE_AUTHORITIES)
        is not _PINNED_TUPLE
    ):
        raise _PINNED_BUNDLE_ERROR("bundle module binding changed")
    for module, expected_dict, expected_entries in (
        _PINNED_BOOTSTRAP_MODULE_AUTHORITIES
    ):
        module_dict = _PINNED_OBJECT_GETATTRIBUTE(module, "__dict__")
        live_entries = _PINNED_TUPLE(
            item
            for item in _PINNED_DICT_ITEMS(module_dict)
            if not (
                _PINNED_TYPE(_PINNED_TUPLE_GETITEM(item, 0))
                is _PINNED_STR
                and _PINNED_TUPLE_GETITEM(item, 0)
                == "__warningregistry__"
            )
        )
        if (
            module_dict is not expected_dict
            or _PINNED_TUPLE_LEN(live_entries)
            != _PINNED_TUPLE_LEN(expected_entries)
            or _PINNED_ANY(
                _PINNED_TUPLE_GETITEM(actual, 0)
                is not _PINNED_TUPLE_GETITEM(expected, 0)
                or _PINNED_TUPLE_GETITEM(actual, 1)
                is not _PINNED_TUPLE_GETITEM(expected, 1)
                for actual, expected in _PINNED_ZIP(
                    live_entries,
                    expected_entries,
                    strict=True,
                )
            )
        ):
            raise _PINNED_BUNDLE_ERROR("bundle module binding changed")
    if (
        _RUNTIME_DEPENDENCY_MODULES
        is not _PINNED_RUNTIME_DEPENDENCY_MODULES
        or _PINNED_TYPE(_PINNED_RUNTIME_DEPENDENCY_MODULES)
        is not _PINNED_TUPLE
        or _PINNED_ANY(
            _PINNED_OBJECT_GETATTRIBUTE(module, "__class__")
            is not _PINNED_MODULE_TYPE
            for module in _PINNED_RUNTIME_DEPENDENCY_MODULES
        )
    ):
        raise _PINNED_BUNDLE_ERROR("bundle dependency module changed")
    collections_abc_module_dict = _PINNED_OBJECT_GETATTRIBUTE(
        _PINNED_COUNTER_COLLECTIONS_ABC_MODULE,
        "__dict__",
    )
    collections_abc_module_entries = _PINNED_TUPLE(
        collections_abc_module_dict.items()
    )
    if (
        _COUNTER_COLLECTIONS_ABC_MODULE
        is not _PINNED_COUNTER_COLLECTIONS_ABC_MODULE
        or collections_abc_module_dict
        is not _PINNED_COUNTER_COLLECTIONS_ABC_MODULE_DICT
        or _PINNED_LEN(collections_abc_module_entries)
        != _PINNED_LEN(_PINNED_COUNTER_COLLECTIONS_ABC_MODULE_ENTRIES)
        or _PINNED_ANY(
            actual[0] is not expected[0] or actual[1] is not expected[1]
            for actual, expected in _PINNED_ZIP(
                collections_abc_module_entries,
                _PINNED_COUNTER_COLLECTIONS_ABC_MODULE_ENTRIES,
                strict=True,
            )
        )
        or _COLLECTIONS_ABC_MAPPING_CLASS
        is not _PINNED_COLLECTIONS_ABC_MAPPING_CLASS
        or _PINNED_TYPE(_PINNED_COLLECTIONS_ABC_MAPPING_CLASS)
        is not _PINNED_ABC_META_CLASS
        or _ABC_META_CLASS is not _PINNED_ABC_META_CLASS
    ):
        raise _PINNED_BUNDLE_ERROR("bundle aggregate topology changed")
    if (
        _BUILTIN_RESOLUTION_BINDINGS
        is not _PINNED_BUILTIN_RESOLUTION_BINDINGS
        or _LOCAL_MODULE_GLOBALS is not _PINNED_LOCAL_MODULE_GLOBALS
        or _BUILTIN_GLOBALS is not _PINNED_BUILTIN_GLOBALS
    ):
        raise _PINNED_BUNDLE_ERROR("bundle builtin topology changed")
    if (
        _PINNED_BUILTIN_GLOBALS.get("any") is not _PINNED_ANY
        or _PINNED_BUILTIN_GLOBALS.get("str") is not _PINNED_STR
        or _PINNED_BUILTIN_GLOBALS.get("type") is not _PINNED_TYPE
        or _PINNED_BUILTIN_GLOBALS.get("object") is not _PINNED_OBJECT
        or _PINNED_BUILTIN_GLOBALS.get("tuple") is not _PINNED_TUPLE
        or _PINNED_OBJECT_GETATTRIBUTE
        is not _PINNED_OBJECT.__getattribute__
        or _PINNED_TUPLE_GETITEM is not _PINNED_TUPLE.__getitem__
        or _PINNED_TUPLE_LEN is not _PINNED_TUPLE.__len__
    ):
        raise _PINNED_BUNDLE_ERROR("bundle builtin topology changed")
    if _PINNED_ANY(
        _PINNED_TYPE(name) is not _PINNED_STR
        for name in _PINNED_BUILTIN_GLOBALS
    ):
        raise _PINNED_BUNDLE_ERROR("bundle builtin topology changed")
    for function_globals, name, expected in _PINNED_BUILTIN_RESOLUTION_BINDINGS:
        if _PINNED_ANY(
            _PINNED_TYPE(actual_name) is not _PINNED_STR
            or actual_name is name
            or actual_name == name
            for actual_name in function_globals
        ) or _PINNED_BUILTIN_GLOBALS.get(name) is not expected:
            raise _PINNED_BUNDLE_ERROR("bundle builtin topology changed")
    if (
        QcGlobalInputBundleError is not _PINNED_BUNDLE_ERROR
        or DecisionRow is not _PINNED_DECISION_ROW
        or SecurityOpenValue is not _PINNED_SECURITY_OPEN_VALUE
        or BenchmarkOpenValue is not _PINNED_BENCHMARK_OPEN_VALUE
        or SecurityLifecycleCoverage is not _PINNED_SECURITY_LIFECYCLE_COVERAGE
        or TerminalLifecycle is not _PINNED_TERMINAL_LIFECYCLE
        or TerminalRequirement is not _PINNED_TERMINAL_REQUIREMENT
        or TerminalShareholderPayoff is not _PINNED_TERMINAL_SHAREHOLDER_PAYOFF
        or EventStudyBatch is not _PINNED_EVENT_STUDY_BATCH
        or EventStudyObservation is not _PINNED_EVENT_STUDY_OBSERVATION
        or EventStudyRefusal is not _PINNED_EVENT_STUDY_REFUSAL
        or RowContract is not _PINNED_ROW_CONTRACT
        or ParentArtifact is not _PINNED_PARENT_ARTIFACT
        or CodeFileBinding is not _PINNED_CODE_FILE_BINDING
        or SyntheticPartitionBinding is not _PINNED_PARTITION_BINDING
        or EvaluationWindow is not _PINNED_EVALUATION_WINDOW
        or SyntheticQcRunCandidate is not _PINNED_RUN_CANDIDATE
        or SyntheticQcGlobalInputManifest is not _PINNED_MANIFEST_CLASS
        or GlobalInputPartitionDescriptor is not _PINNED_DESCRIPTOR_CLASS
        or SyntheticGlobalInputPartitionPayload
        is not _PINNED_PARTITION_PAYLOAD_CLASS
        or SyntheticQcGlobalInputBundle is not _PINNED_BUNDLE_CLASS
    ):
        raise _PINNED_BUNDLE_ERROR("accepted class identity changed")
    if (
        dataclasses.fields is not _PINNED_DATACLASS_FIELDS
        or dataclasses.Field is not _PINNED_DATACLASS_FIELD_CLASS
        or json.JSONDecoder is not _PINNED_JSON_DECODER_CLASS
        or json.JSONEncoder is not _PINNED_JSON_ENCODER_CLASS
        or Counter is not _PINNED_COUNTER_CLASS
        or type.__getattribute__(dataclasses.Field, "__dict__")["name"]
        is not _PINNED_DATACLASS_FIELD_NAME_DESCRIPTOR
        or type.__getattribute__(dataclasses.Field, "__dict__")["_field_type"]
        is not _PINNED_DATACLASS_FIELD_TYPE_DESCRIPTOR
        or property is not _PINNED_PROPERTY_TYPE
        or MappingProxyType is not _PINNED_MAPPING_PROXY_TYPE
        or ModuleType is not _PINNED_MODULE_TYPE
        or type(_require_static_contract) is not _PINNED_FUNCTION_TYPE
        or InvalidOperation is not _PINNED_INVALID_OPERATION
        or json.JSONDecodeError is not _PINNED_JSON_DECODE_ERROR
        or QcGlobalInputSchemaError is not _PINNED_GLOBAL_INPUT_SCHEMA_ERROR
        or QcRunContractError is not _PINNED_RUN_CONTRACT_ERROR
        or EventStudyInputError is not _PINNED_EVENT_STUDY_INPUT_ERROR
        or TypeError is not _PINNED_TYPE_ERROR
        or ValueError is not _PINNED_VALUE_ERROR
        or UnicodeError is not _PINNED_UNICODE_ERROR
        or UnicodeDecodeError is not _PINNED_UNICODE_DECODE_ERROR
        or RecursionError is not _PINNED_RECURSION_ERROR
    ):
        raise _PINNED_BUNDLE_ERROR("bundle primitive topology changed")

    def function_state_is_current(
        implementation: object,
        expected_state: tuple,
    ) -> bool:
        if type(implementation) is not _PINNED_FUNCTION_TYPE:
            return False
        (
            expected_code,
            expected_defaults,
            expected_default_values,
            expected_kwdefaults,
            expected_kwdefault_entries,
            expected_closure,
            expected_closure_entries,
        ) = expected_state
        if (
            implementation.__code__ is not expected_code
            or implementation.__defaults__ is not expected_defaults
            or implementation.__kwdefaults__ is not expected_kwdefaults
            or implementation.__closure__ is not expected_closure
        ):
            return False
        actual_defaults = implementation.__defaults__
        if actual_defaults is not None and (
            type(actual_defaults) is not tuple
            or len(actual_defaults) != len(expected_default_values)
            or any(
                actual is not expected
                for actual, expected in zip(
                    actual_defaults,
                    expected_default_values,
                )
            )
        ):
            return False
        actual_kwdefaults = implementation.__kwdefaults__
        if actual_kwdefaults is not None:
            if type(actual_kwdefaults) is not dict:
                return False
            actual_entries = tuple(actual_kwdefaults.items())
            if len(actual_entries) != len(expected_kwdefault_entries):
                return False
            for actual_entry, expected_entry in zip(
                actual_entries,
                expected_kwdefault_entries,
            ):
                if (
                    type(actual_entry[0]) is not str
                    or actual_entry[0] is not expected_entry[0]
                    or actual_entry[1] is not expected_entry[1]
                ):
                    return False
        actual_closure = implementation.__closure__
        if actual_closure is not None:
            if (
                type(actual_closure) is not tuple
                or len(actual_closure) != len(expected_closure_entries)
            ):
                return False
            for actual_cell, expected_entry in zip(
                actual_closure,
                expected_closure_entries,
            ):
                try:
                    actual_cell_contents = actual_cell.cell_contents
                except ValueError:
                    return False
                if (
                    actual_cell is not expected_entry[0]
                    or actual_cell_contents is not expected_entry[1]
                ):
                    return False
        return True
    live_helpers = (
        _capture_dependency_value_authority,
        _dependency_value_authority_is_current,
        _call_parent_schema_renderer,
        _decode_utf8,
        _reject_pairs,
        _reject_number,
        _parse_json,
        _json_tree_is_exact,
        _parse_date_value,
        _parse_decimal_value,
        _decode_terminal_lifecycle,
        _decode_wire_value,
        _decode_dataclass_envelope,
        _decoded_wire_value_is_exact,
        _decoded_dataclass_shell_is_exact,
        _class_for_role,
        _decode_row,
        _encoded_value,
        _render_decoded_partition,
        _decode_partition,
        _call_manifest_loader,
        _call_partition_builder,
        _bundle_document,
        _require_bundle_document_contract,
        _load_bundle,
        require_synthetic_qc_global_input_bundle,
        _call_event_study,
        _event_study_batch_is_valid,
    )
    if (
        _INTERNAL_HELPERS is not _PINNED_INTERNAL_HELPERS
        or type(_PINNED_INTERNAL_HELPERS) is not tuple
        or len(live_helpers) != len(_PINNED_INTERNAL_HELPERS)
        or any(
            actual is not expected
            for actual, expected in zip(live_helpers, _PINNED_INTERNAL_HELPERS)
        )
        or SyntheticGlobalInputPartitionPayload
        is not _PINNED_PARTITION_PAYLOAD_CLASS
        or SyntheticQcGlobalInputBundle is not _PINNED_BUNDLE_CLASS
        or _require_static_contract is not _PINNED_REQUIRE_STATIC_CONTRACT
        or _load_bundle is not _PINNED_LOAD_BUNDLE
        or require_synthetic_qc_global_input_bundle
        is not _PINNED_PUBLIC_REQUIRE_BUNDLE
        or _call_event_study is not _PINNED_CALL_EVENT_STUDY
        or _event_study_batch_is_valid
        is not _PINNED_EVENT_STUDY_BATCH_IS_VALID
        or _decode_partition is not _PINNED_DECODE_PARTITION
        or _bundle_document is not _PINNED_BUNDLE_DOCUMENT
        or _require_bundle_document_contract
        is not _PINNED_REQUIRE_BUNDLE_DOCUMENT
        or _render_decoded_partition
        is not _PINNED_RENDER_DECODED_PARTITION
        or _call_parent_schema_renderer
        is not _PINNED_CALL_PARENT_SCHEMA_RENDERER
        or render_qc_global_input_bundle_schema_bytes
        is not _PINNED_PUBLIC_SCHEMA_RENDERER
        or load_synthetic_qc_global_input_bundle
        is not _PINNED_PUBLIC_LOADER
        or _SCHEMA_RENDERER_IMPLEMENTATION
        is not _PINNED_SCHEMA_RENDERER_IMPLEMENTATION
        or _BUNDLE_VALIDATOR_IMPLEMENTATION
        is not _PINNED_BUNDLE_VALIDATOR_IMPLEMENTATION
        or _COMPOSER_IMPLEMENTATION is not _PINNED_COMPOSER_IMPLEMENTATION
        or collect_synthetic_event_study_from_global_input_bundle
        is not _PINNED_PUBLIC_COMPOSER
    ):
        raise _PINNED_BUNDLE_ERROR("bundle callable topology changed")
    if (
        _FUNCTION_TOPOLOGIES is not _PINNED_FUNCTION_TOPOLOGIES
        or type(_PINNED_FUNCTION_TOPOLOGIES) is not tuple
        or any(
            not function_state_is_current(implementation, expected_state)
            for implementation, expected_state in _PINNED_FUNCTION_TOPOLOGIES
        )
    ):
        raise _PINNED_BUNDLE_ERROR("bundle function topology changed")
    if (
        _DEPENDENCY_GLOBAL_BINDINGS is not _PINNED_DEPENDENCY_GLOBAL_BINDINGS
        or type(_PINNED_DEPENDENCY_GLOBAL_BINDINGS) is not tuple
    ):
        raise _PINNED_BUNDLE_ERROR("bundle dependency topology changed")
    for dependency_globals, expected_bindings in (
        _PINNED_DEPENDENCY_GLOBAL_BINDINGS
    ):
        if (
            type(dependency_globals) is not dict
            or type(expected_bindings) is not tuple
        ):
            raise _PINNED_BUNDLE_ERROR("bundle dependency topology changed")
        live_items = tuple(
            item
            for item in dependency_globals.items()
            if not (
                type(item[0]) is str
                and item[0] == "__warningregistry__"
            )
        )
        if len(live_items) != len(expected_bindings):
            raise _PINNED_BUNDLE_ERROR("bundle dependency topology changed")
        for live_entry, expected_entry in zip(
            live_items,
            expected_bindings,
            strict=True,
        ):
            if (
                live_entry[0] is not expected_entry[0]
                or live_entry[1] is not expected_entry[1]
            ):
                raise _PINNED_BUNDLE_ERROR("bundle dependency topology changed")
    axis_wrapper_dict = _PINNED_OBJECT_GETATTRIBUTE(
        _PINNED_REVIEWED_SESSION_AXIS_WRAPPER,
        "__dict__",
    )
    index_wrapper_dict = _PINNED_OBJECT_GETATTRIBUTE(
        _PINNED_REVIEWED_SESSION_INDEX_WRAPPER,
        "__dict__",
    )
    axis_wrapper_entries = tuple(axis_wrapper_dict.items())
    index_wrapper_entries = tuple(index_wrapper_dict.items())
    if (
        _REVIEWED_SESSION_AXIS_WRAPPER
        is not _PINNED_REVIEWED_SESSION_AXIS_WRAPPER
        or _REVIEWED_SESSION_INDEX_WRAPPER
        is not _PINNED_REVIEWED_SESSION_INDEX_WRAPPER
        or axis_wrapper_dict
        is not _PINNED_REVIEWED_SESSION_AXIS_WRAPPER_DICT
        or index_wrapper_dict
        is not _PINNED_REVIEWED_SESSION_INDEX_WRAPPER_DICT
        or len(axis_wrapper_entries)
        != len(_PINNED_REVIEWED_SESSION_AXIS_WRAPPER_ENTRIES)
        or len(index_wrapper_entries)
        != len(_PINNED_REVIEWED_SESSION_INDEX_WRAPPER_ENTRIES)
        or any(
            actual[0] is not expected[0] or actual[1] is not expected[1]
            for actual, expected in zip(
                axis_wrapper_entries,
                _PINNED_REVIEWED_SESSION_AXIS_WRAPPER_ENTRIES,
                strict=True,
            )
        )
        or any(
            actual[0] is not expected[0] or actual[1] is not expected[1]
            for actual, expected in zip(
                index_wrapper_entries,
                _PINNED_REVIEWED_SESSION_INDEX_WRAPPER_ENTRIES,
                strict=True,
            )
        )
    ):
        raise _PINNED_BUNDLE_ERROR("reviewed session cache topology changed")
    if (
        _PLAIN_CLASS_TOPOLOGIES is not _PINNED_PLAIN_CLASS_TOPOLOGIES
        or type(_PINNED_PLAIN_CLASS_TOPOLOGIES) is not tuple
    ):
        raise _PINNED_BUNDLE_ERROR("bundle dependency class topology changed")
    for accepted_class, expected_entries in (
        _PINNED_PLAIN_CLASS_TOPOLOGIES
    ):
        class_dict = type.__getattribute__(accepted_class, "__dict__")
        actual_entries = tuple(class_dict.items())
        if len(actual_entries) != len(expected_entries):
            raise _PINNED_BUNDLE_ERROR(
                "bundle dependency class topology changed"
            )
        for actual_entry, expected_entry in zip(
            actual_entries,
            expected_entries,
            strict=True,
        ):
            expected_name, expected_member, expected_function_state = (
                expected_entry
            )
            if (
                actual_entry[0] is not expected_name
                or actual_entry[1] is not expected_member
                or (
                    expected_function_state is not None
                    and not function_state_is_current(
                        actual_entry[1],
                        expected_function_state,
                    )
                )
            ):
                raise _PINNED_BUNDLE_ERROR(
                    "bundle dependency class topology changed"
                )
    axis_cache_info = _PINNED_REVIEWED_SESSION_AXIS_WRAPPER.cache_info()
    index_cache_info = _PINNED_REVIEWED_SESSION_INDEX_WRAPPER.cache_info()
    if (
        _CACHE_INFO_CLASS is not _PINNED_CACHE_INFO_CLASS
        or type(axis_cache_info) is not _PINNED_CACHE_INFO_CLASS
        or type(index_cache_info) is not _PINNED_CACHE_INFO_CLASS
        or _PINNED_TUPLE_LEN(axis_cache_info) != 4
        or _PINNED_TUPLE_LEN(index_cache_info) != 4
        or type(_PINNED_TUPLE_GETITEM(axis_cache_info, 2)) is not int
        or type(_PINNED_TUPLE_GETITEM(axis_cache_info, 3)) is not int
        or type(_PINNED_TUPLE_GETITEM(index_cache_info, 2)) is not int
        or type(_PINNED_TUPLE_GETITEM(index_cache_info, 3)) is not int
        or _PINNED_TUPLE_GETITEM(axis_cache_info, 2) != 1
        or _PINNED_TUPLE_GETITEM(axis_cache_info, 3) != 1
        or _PINNED_TUPLE_GETITEM(index_cache_info, 2) != 1
        or _PINNED_TUPLE_GETITEM(index_cache_info, 3) != 1
        or _PINNED_REVIEWED_SESSION_AXIS_WRAPPER()
        is not _PINNED_REVIEWED_SESSION_AXIS
        or _PINNED_REVIEWED_SESSION_INDEX_WRAPPER()
        is not _PINNED_REVIEWED_SESSION_INDEX
    ):
        raise _PINNED_BUNDLE_ERROR("reviewed session cache topology changed")
    if (
        _CLASS_TOPOLOGIES is not _PINNED_CLASS_TOPOLOGIES
        or type(_PINNED_CLASS_TOPOLOGIES) is not tuple
    ):
        raise _PINNED_BUNDLE_ERROR("bundle class topology changed")
    for (
        accepted_class,
        expected_field_names,
        expected_members,
        expected_properties,
        expected_field_registry,
        expected_field_entries,
    ) in _PINNED_CLASS_TOPOLOGIES:
        class_dict = type.__getattribute__(accepted_class, "__dict__")
        if (
            type(expected_field_names) is not tuple
            or type(expected_members) is not tuple
            or type(expected_properties) is not tuple
            or type(expected_field_entries) is not tuple
            or tuple(item[2] for item in expected_field_entries)
            != expected_field_names
        ):
            raise _PINNED_BUNDLE_ERROR("bundle dataclass topology changed")
        for (
            name,
            was_present,
            expected_member,
            expected_function_state,
        ) in expected_members:
            is_present = name in class_dict
            if is_present is not was_present:
                message = (
                    "bundle row equality topology changed"
                    if name == "__eq__"
                    else "bundle class topology changed"
                )
                raise _PINNED_BUNDLE_ERROR(message)
            if not is_present:
                continue
            actual_member = class_dict[name]
            if actual_member is not expected_member or (
                expected_function_state is not None
                and not function_state_is_current(
                    actual_member,
                    expected_function_state,
                )
            ):
                message = (
                    "bundle row equality topology changed"
                    if name == "__eq__"
                    else "bundle class topology changed"
                )
                raise _PINNED_BUNDLE_ERROR(message)
        if (
            "__dataclass_fields__" not in class_dict
            or class_dict["__dataclass_fields__"] is not expected_field_registry
            or type(expected_field_registry) is not dict
        ):
            raise _PINNED_BUNDLE_ERROR("bundle dataclass registry changed")
        actual_field_entries = tuple(expected_field_registry.items())
        if len(actual_field_entries) != len(expected_field_entries):
            raise _PINNED_BUNDLE_ERROR("bundle dataclass registry changed")
        for actual_entry, expected_entry in zip(
            actual_field_entries,
            expected_field_entries,
        ):
            actual_name, actual_field = actual_entry
            (
                expected_name,
                expected_field,
                expected_field_name,
                expected_field_type,
            ) = expected_entry
            if (
                type(actual_name) is not str
                or actual_name is not expected_name
                or type(actual_field) is not _PINNED_DATACLASS_FIELD_CLASS
                or actual_field is not expected_field
                or _PINNED_DATACLASS_FIELD_NAME_DESCRIPTOR.__get__(
                    actual_field,
                    _PINNED_DATACLASS_FIELD_CLASS,
                )
                is not expected_field_name
                or _PINNED_DATACLASS_FIELD_TYPE_DESCRIPTOR.__get__(
                    actual_field,
                    _PINNED_DATACLASS_FIELD_CLASS,
                )
                is not expected_field_type
            ):
                raise _PINNED_BUNDLE_ERROR("bundle dataclass registry changed")
        for name, expected_property, expected_fget, expected_fget_state in (
            expected_properties
        ):
            if name not in class_dict:
                raise _PINNED_BUNDLE_ERROR("bundle authority topology changed")
            actual_property = class_dict[name]
            if (
                type(actual_property) is not _PINNED_PROPERTY_TYPE
                or actual_property is not expected_property
                or actual_property.fget is not expected_fget
                or not function_state_is_current(
                    actual_property.fget,
                    expected_fget_state,
                )
            ):
                raise _PINNED_BUNDLE_ERROR("bundle authority topology changed")
    if (
        _DEPENDENCY_GRAPH_CONTAINER_TYPES
        is not _PINNED_DEPENDENCY_GRAPH_CONTAINER_TYPES
        or _DEPENDENCY_GRAPH_RECORD_TYPES
        is not _PINNED_DEPENDENCY_GRAPH_RECORD_TYPES
        or _DEPENDENCY_VALUE_ROOTS is not _PINNED_DEPENDENCY_VALUE_ROOTS
        or _DEPENDENCY_VALUE_AUTHORITY
        is not _PINNED_DEPENDENCY_VALUE_AUTHORITY
        or _PINNED_DEPENDENCY_VALUE_AUTHORITY_IS_CURRENT
        is not _dependency_value_authority_is_current
        or not _PINNED_DEPENDENCY_VALUE_AUTHORITY_IS_CURRENT(
            _PINNED_DEPENDENCY_VALUE_ROOTS,
            _PINNED_DEPENDENCY_VALUE_AUTHORITY,
        )
    ):
        raise _PINNED_BUNDLE_ERROR("bundle dependency value graph changed")
    if (
        _EXPECTED_ROLE_ORDER is not _PINNED_EXPECTED_ROLE_ORDER
        or _EXPECTED_ROW_CONTRACTS is not _PINNED_EXPECTED_ROW_CONTRACTS
        or _EXPECTED_TERMINAL_LIFECYCLE
        is not _PINNED_EXPECTED_TERMINAL_LIFECYCLE
        or ROLE_ORDER is not _PINNED_ROLE_ORDER_ROOT
        or ROW_CONTRACTS is not _PINNED_ROW_CONTRACTS_ROOT
        or TERMINAL_LIFECYCLE_FIELDS
        is not _PINNED_TERMINAL_LIFECYCLE_FIELDS_ROOT
        or TERMINAL_LIFECYCLE_WIRE_TYPES
        is not _PINNED_TERMINAL_LIFECYCLE_WIRE_TYPES_ROOT
        or _HEX_64 is not _PINNED_HEX_64
        or PARTITION_PAYLOAD_FIELDS is not _PINNED_PARTITION_PAYLOAD_FIELDS
        or RUN_CANDIDATE_FIELDS is not _PINNED_RUN_CANDIDATE_FIELDS
        or EVENT_STUDY_BATCH_FIELDS is not _PINNED_EVENT_STUDY_BATCH_FIELDS
        or EVENT_STUDY_OBSERVATION_FIELDS
        is not _PINNED_EVENT_STUDY_OBSERVATION_FIELDS
        or EVENT_STUDY_REFUSAL_FIELDS
        is not _PINNED_EVENT_STUDY_REFUSAL_FIELDS
        or SECURITY_LIFECYCLE_COVERAGE_FIELDS
        is not _PINNED_SECURITY_LIFECYCLE_COVERAGE_FIELDS
        or TERMINAL_LIFECYCLE_OUTPUT_FIELDS
        is not _PINNED_TERMINAL_LIFECYCLE_OUTPUT_FIELDS
        or EVENT_STUDY_BATCH_METHOD_NAMES
        is not _PINNED_EVENT_STUDY_BATCH_METHOD_NAMES
        or BUNDLE_FIELDS is not _PINNED_BUNDLE_FIELDS
        or BUNDLE_DOCUMENT_ROOT_FIELDS
        is not _PINNED_BUNDLE_DOCUMENT_ROOT_FIELDS
        or BUNDLE_DOCUMENT_NESTED_FIELDS
        is not _PINNED_BUNDLE_DOCUMENT_NESTED_FIELDS
        or BUNDLE_PARTITION_DOCUMENT_FIELDS
        is not _PINNED_BUNDLE_PARTITION_DOCUMENT_FIELDS
        or BUNDLE_FALSE_PROPERTY_NAMES
        is not _PINNED_BUNDLE_FALSE_PROPERTY_NAMES
        or EVENT_STUDY_FALSE_PROPERTY_NAMES
        is not _PINNED_EVENT_STUDY_FALSE_PROPERTY_NAMES
        or RUN_CANDIDATE_FALSE_PROPERTY_NAMES
        is not _PINNED_RUN_CANDIDATE_FALSE_PROPERTY_NAMES
        or CLASS_TOPOLOGY_MEMBER_NAMES
        is not _PINNED_CLASS_TOPOLOGY_MEMBER_NAMES
        or _INVALID is not _PINNED_INVALID_SENTINEL
        or _schema_contract_document is not _PINNED_SCHEMA_CONTRACT_DOCUMENT
        or _try_canonical_bytes is not _PINNED_TRY_CANONICAL_BYTES
        or _canonical_bytes is not _PINNED_CANONICAL_BYTES
        or _schema_identity_document is not _PINNED_SCHEMA_IDENTITY_DOCUMENT
        or hashlib.sha256 is not _PINNED_SHA256
        or json.dumps is not _PINNED_JSON_DUMPS
        or json.loads is not _PINNED_JSON_LOADS
        or json.JSONDecoder is not _PINNED_JSON_DECODER_CLASS
        or json.JSONEncoder is not _PINNED_JSON_ENCODER_CLASS
        or Counter is not _PINNED_COUNTER_CLASS
        or dataclasses.fields is not _PINNED_DATACLASS_FIELDS
        or property is not _PINNED_PROPERTY_TYPE
        or InvalidOperation is not _PINNED_INVALID_OPERATION
        or json.JSONDecodeError is not _PINNED_JSON_DECODE_ERROR
        or QcGlobalInputSchemaError is not _PINNED_GLOBAL_INPUT_SCHEMA_ERROR
        or QcRunContractError is not _PINNED_RUN_CONTRACT_ERROR
        or EventStudyInputError is not _PINNED_EVENT_STUDY_INPUT_ERROR
        or TypeError is not _PINNED_TYPE_ERROR
        or ValueError is not _PINNED_VALUE_ERROR
        or UnicodeError is not _PINNED_UNICODE_ERROR
        or UnicodeDecodeError is not _PINNED_UNICODE_DECODE_ERROR
        or RecursionError is not _PINNED_RECURSION_ERROR
        or AttributeError is not _PINNED_ATTRIBUTE_ERROR
    ):
        raise _PINNED_BUNDLE_ERROR("bundle static topology changed")
    scalar_expectations = (
        (SCHEMA, "arv2-qc-global-input-bundle-schema-v1"),
        (SCHEMA_ID, "arv2-qc-global-input-bundle-schema-78e279a8b81c5be4"),
        (
            SCHEMA_SHA256,
            "78e279a8b81c5be484b93f20600aba5c45f0c4524e06eaed60c378a53b085a90",
        ),
        (
            SCHEMA_ARTIFACT_SHA256,
            "a3211d2a24a033d7dc70904414a9767b8430c590e29ab435729a894455116d6f",
        ),
        (STATUS, "offline_synthetic_fixture_payloads_only_not_production_admission"),
        (
            AUTHORITY,
            "exact_in_memory_synthetic_payload_decode_and_pure_core_composition_only_"
            "no_production_truth_rights_outcome_qc_result_or_trading_authority",
        ),
        (BUNDLE_HASH_DOMAIN, "arv2-qc-global-input-bundle-v1"),
        (ENCODING, "canonical_tagged_jsonl_strict_utf8_lf-v1"),
        (
            GLOBAL_INPUT_SCHEMA_ID,
            "arv2-qc-global-input-schema-d56e2b5ec26d4068",
        ),
        (
            GLOBAL_INPUT_SCHEMA_SHA256,
            "d56e2b5ec26d4068876bff3b549c1f9c7a83014c1372403d7bf33e511bd8e640",
        ),
        (
            GLOBAL_INPUT_SCHEMA_ARTIFACT_SHA256,
            "0f60cb3badec36fa9589b220cf91aee43a965865244c7c2726d16da71f6ae3d2",
        ),
        (
            GLOBAL_INPUT_SCHEMA_SOURCE_SHA256,
            "f0da3f016cdd794514146a7811d3606b3c8be9d94ffca80e1c28790af519016a",
        ),
    )
    if any(type(actual) is not str for actual, _ in scalar_expectations):
        raise QcGlobalInputBundleError("bundle static scalar type changed")
    if any(actual != expected for actual, expected in scalar_expectations):
        raise QcGlobalInputBundleError("bundle static contract changed")
    integer_expectations = (
        (GLOBAL_INPUT_SCHEMA_SOURCE_BYTE_COUNT, 94_959),
        (MAX_SYNTHETIC_PARTITION_BYTES, 67_108_864),
        (MAX_SYNTHETIC_BUNDLE_BYTES, 268_435_456),
        (MAX_SYNTHETIC_PARTITION_ROWS, 2_000_000),
        (MAX_SYNTHETIC_BUNDLE_ROWS, 5_000_000),
        (MAX_SYNTHETIC_ROW_BYTES, 1_048_576),
        (MAX_JSON_DEPTH, 16),
    )
    if any(type(actual) is not int for actual, _ in integer_expectations):
        raise QcGlobalInputBundleError("bundle static bound type changed")
    if any(actual != expected for actual, expected in integer_expectations):
        raise QcGlobalInputBundleError("bundle static resource bound changed")
    if (
        tuple(
            field.name
            for field in _PINNED_DATACLASS_FIELDS(
                _PINNED_PARTITION_PAYLOAD_CLASS
            )
        )
        != PARTITION_PAYLOAD_FIELDS
        or tuple(
            field.name
            for field in _PINNED_DATACLASS_FIELDS(_PINNED_BUNDLE_CLASS)
        )
        != BUNDLE_FIELDS
        or tuple(
            field.name
            for field in _PINNED_DATACLASS_FIELDS(
                _PINNED_EVENT_STUDY_OBSERVATION
            )
        )
        != EVENT_STUDY_OBSERVATION_FIELDS
        or tuple(
            field.name
            for field in _PINNED_DATACLASS_FIELDS(_PINNED_EVENT_STUDY_REFUSAL)
        )
        != EVENT_STUDY_REFUSAL_FIELDS
        or tuple(
            field.name
            for field in _PINNED_DATACLASS_FIELDS(
                _PINNED_SECURITY_LIFECYCLE_COVERAGE
            )
        )
        != SECURITY_LIFECYCLE_COVERAGE_FIELDS
        or tuple(
            field.name
            for field in _PINNED_DATACLASS_FIELDS(_PINNED_TERMINAL_LIFECYCLE)
        )
        != TERMINAL_LIFECYCLE_OUTPUT_FIELDS
    ):
        raise QcGlobalInputBundleError("bundle dataclass field inventory changed")
    if type(ROLE_ORDER) is not tuple or any(
        type(item) is not str for item in ROLE_ORDER
    ):
        raise QcGlobalInputBundleError("accepted role contract type changed")
    if ROLE_ORDER != _EXPECTED_ROLE_ORDER or type(ROW_CONTRACTS) is not tuple:
        raise QcGlobalInputBundleError("accepted row contract changed")
    live_row_contracts: list[tuple] = []
    for item in ROW_CONTRACTS:
        if (
            type(item) is not _PINNED_ROW_CONTRACT
            or type(item.role) is not str
            or type(item.row_schema) is not str
            or type(item.record_type) is not str
            or type(item.root_envelope) is not str
            or type(item.fields) is not tuple
            or type(item.wire_types) is not tuple
            or type(item.canonical_order) is not tuple
            or any(type(value) is not str for value in item.fields)
            or any(type(value) is not str for value in item.wire_types)
            or any(type(value) is not str for value in item.canonical_order)
        ):
            raise QcGlobalInputBundleError("accepted row contract type changed")
        live_row_contracts.append(
            (
                item.role,
                item.row_schema,
                item.record_type,
                item.root_envelope,
                item.fields,
                item.wire_types,
                item.canonical_order,
            )
        )
    if tuple(live_row_contracts) != _EXPECTED_ROW_CONTRACTS:
        raise QcGlobalInputBundleError("accepted row contract changed")
    if (
        type(TERMINAL_LIFECYCLE_FIELDS) is not tuple
        or type(TERMINAL_LIFECYCLE_WIRE_TYPES) is not tuple
        or any(type(item) is not str for item in TERMINAL_LIFECYCLE_FIELDS)
        or any(type(item) is not str for item in TERMINAL_LIFECYCLE_WIRE_TYPES)
        or (TERMINAL_LIFECYCLE_FIELDS, TERMINAL_LIFECYCLE_WIRE_TYPES)
        != _EXPECTED_TERMINAL_LIFECYCLE
    ):
        raise QcGlobalInputBundleError("accepted row contract changed")
    if (
        date is not _PINNED_DATE
        or Decimal is not _PINNED_DECIMAL
        or DecisionRow is not _PINNED_DECISION_ROW
        or SecurityOpenValue is not _PINNED_SECURITY_OPEN_VALUE
        or BenchmarkOpenValue is not _PINNED_BENCHMARK_OPEN_VALUE
        or SecurityLifecycleCoverage is not _PINNED_SECURITY_LIFECYCLE_COVERAGE
        or TerminalLifecycle is not _PINNED_TERMINAL_LIFECYCLE
        or TerminalRequirement is not _PINNED_TERMINAL_REQUIREMENT
        or TerminalShareholderPayoff is not _PINNED_TERMINAL_SHAREHOLDER_PAYOFF
        or EventStudyBatch is not _PINNED_EVENT_STUDY_BATCH
        or RowContract is not _PINNED_ROW_CONTRACT
        or load_synthetic_qc_global_input_manifest_bytes
        is not _PINNED_LOAD_MANIFEST
        or render_qc_global_input_schema_bytes
        is not _PINNED_RENDER_GLOBAL_INPUT_SCHEMA
        or require_synthetic_qc_run_candidate is not _PINNED_REQUIRE_CANDIDATE
        or build_synthetic_partition_binding
        is not _PINNED_BUILD_PARTITION_BINDING
        or collect_synthetic_event_study is not _PINNED_COLLECT_EVENT_STUDY
        or require_synthetic_event_study_batch
        is not _PINNED_REQUIRE_EVENT_STUDY_BATCH
    ):
        raise QcGlobalInputBundleError("accepted dependency identity changed")
    parent_payload = _PINNED_CALL_PARENT_SCHEMA_RENDERER()
    if (
        parent_payload is None
        or _PINNED_SHA256(parent_payload).hexdigest()
        != GLOBAL_INPUT_SCHEMA_ARTIFACT_SHA256
    ):
        raise QcGlobalInputBundleError("accepted parent schema changed")
    identity = _PINNED_SCHEMA_IDENTITY_DOCUMENT()
    if (
        identity.get("schema_id") != SCHEMA_ID
        or identity.get("schema_sha256") != SCHEMA_SHA256
        or _PINNED_SHA256(
            _PINNED_CANONICAL_BYTES(identity, newline=True)
        ).hexdigest()
        != SCHEMA_ARTIFACT_SHA256
    ):
        raise QcGlobalInputBundleError("bundle schema identity changed")


def _call_parent_schema_renderer() -> bytes | None:
    try:
        return _PINNED_RENDER_GLOBAL_INPUT_SCHEMA()
    except (QcGlobalInputSchemaError, TypeError, ValueError, UnicodeError):
        return None


def render_qc_global_input_bundle_schema_bytes(
    *,
    _static_check: object = _require_static_contract,
) -> bytes:
    """Return the content-addressed offline bundle contract."""

    _static_check()
    return _PINNED_CANONICAL_BYTES(
        _PINNED_SCHEMA_IDENTITY_DOCUMENT(),
        newline=True,
    )


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticGlobalInputPartitionPayload:
    role: str
    payload: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True, slots=True)
class SyntheticQcGlobalInputBundle:
    bundle_id: str
    bundle_hash: str
    bundle_artifact_sha256: str
    schema_id: str
    schema_sha256: str
    schema_artifact_sha256: str
    manifest_id: str
    manifest_sha256: str
    manifest_artifact_sha256: str
    run_candidate_id: str
    run_candidate_hash: str
    session_axis: tuple[date, ...]
    decisions: tuple[DecisionRow, ...]
    security_opens: tuple[SecurityOpenValue, ...]
    benchmark_opens: tuple[BenchmarkOpenValue, ...]
    security_lifecycle_coverages: tuple[SecurityLifecycleCoverage, ...]
    terminal_requirements: tuple[TerminalRequirement, ...]
    terminal_payoffs: tuple[TerminalShareholderPayoff, ...]
    partition_payloads: tuple[SyntheticGlobalInputPartitionPayload, ...]
    total_byte_count: int
    total_row_count: int
    caller_declared_synthetic_bytes_match_manifest: bool
    row_contracts_validated: bool
    external_bindings: tuple[tuple[str, None], ...]
    capabilities: tuple[tuple[str, bool], ...]
    _manifest_bytes: bytes = dataclasses.field(repr=False)
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


_INVALID = object()
_PINNED_INVALID_SENTINEL = _INVALID


def _decode_utf8(payload: bytes) -> str | object:
    try:
        return payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _INVALID


def _reject_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def _reject_number(_: str) -> object:
    raise ValueError("number")


def _parse_json(text: str) -> object:
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_pairs,
            parse_int=_reject_number,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (json.JSONDecodeError, ValueError, TypeError, RecursionError):
        return _INVALID


def _json_tree_is_exact(
    value: object,
    *,
    depth: int = 0,
    allow_integers: bool = False,
) -> bool:
    if depth > MAX_JSON_DEPTH:
        return False
    if value is None or type(value) in (str, bool):
        return True
    if allow_integers and type(value) is int:
        return True
    if type(value) is list:
        return all(
            _json_tree_is_exact(
                item,
                depth=depth + 1,
                allow_integers=allow_integers,
            )
            for item in value
        )
    if type(value) is dict:
        return all(
            type(key) is str
            and _json_tree_is_exact(
                item,
                depth=depth + 1,
                allow_integers=allow_integers,
            )
            for key, item in value.items()
        )
    return False


def _parse_date_value(value: object) -> date | object:
    if type(value) is not dict or tuple(value) != ("$date",):
        return _INVALID
    raw = value["$date"]
    if type(raw) is not str or len(raw) != 10:
        return _INVALID
    try:
        parsed = _PINNED_DATE.fromisoformat(raw)
    except ValueError:
        return _INVALID
    if parsed.isoformat() != raw:
        return _INVALID
    return parsed


def _parse_decimal_value(value: object) -> Decimal | object:
    if type(value) is not dict or tuple(value) != ("$decimal",):
        return _INVALID
    raw = value["$decimal"]
    if type(raw) is not str or not raw or len(raw) > 1024:
        return _INVALID
    try:
        parsed = _PINNED_DECIMAL(raw)
    except (InvalidOperation, ValueError):
        return _INVALID
    if not parsed.is_finite() or str(parsed) != raw:
        return _INVALID
    return parsed


def _decode_terminal_lifecycle(value: object) -> TerminalLifecycle | object:
    fields, wire_types = _EXPECTED_TERMINAL_LIFECYCLE
    decoded = _decode_dataclass_envelope(
        value,
        record_type="TerminalLifecycle",
        fields=fields,
        wire_types=wire_types,
    )
    if decoded is _INVALID:
        return _INVALID
    return _PINNED_TERMINAL_LIFECYCLE(**decoded)


def _decode_wire_value(wire_type: str, value: object) -> object:
    if wire_type == "string":
        return value if type(value) is str else _INVALID
    if wire_type == "optional_string":
        return value if value is None or type(value) is str else _INVALID
    if wire_type == "lowercase_sha256_string":
        return (
            value
            if type(value) is str and _PINNED_HEX_64.fullmatch(value) is not None
            else _INVALID
        )
    if wire_type == "date_tag":
        return _parse_date_value(value)
    if wire_type == "decimal_tag":
        return _parse_decimal_value(value)
    if wire_type == "terminal_lifecycle_dataclass_or_null":
        return None if value is None else _decode_terminal_lifecycle(value)
    return _INVALID


def _decode_dataclass_envelope(
    value: object,
    *,
    record_type: str,
    fields: tuple[str, ...],
    wire_types: tuple[str, ...],
) -> dict[str, object] | object:
    if (
        type(value) is not dict
        or tuple(value) != ("$dataclass", "$fields")
        or value["$dataclass"] != record_type
        or type(value["$dataclass"]) is not str
        or type(value["$fields"]) is not dict
        or set(value["$fields"]) != set(fields)
        or len(value["$fields"]) != len(fields)
    ):
        return _INVALID
    decoded: dict[str, object] = {}
    for field, wire_type in zip(fields, wire_types):
        item = _decode_wire_value(wire_type, value["$fields"][field])
        if item is _INVALID:
            return _INVALID
        decoded[field] = item
    return decoded


def _decoded_wire_value_is_exact(wire_type: str, value: object) -> bool:
    if wire_type == "string":
        return type(value) is str
    if wire_type == "optional_string":
        return value is None or type(value) is str
    if wire_type == "lowercase_sha256_string":
        return (
            type(value) is str
            and _PINNED_HEX_64.fullmatch(value) is not None
        )
    if wire_type == "date_tag":
        return type(value) is _PINNED_DATE
    if wire_type == "decimal_tag":
        return type(value) is _PINNED_DECIMAL and value.is_finite()
    if wire_type == "terminal_lifecycle_dataclass_or_null":
        return value is None or _decoded_dataclass_shell_is_exact(
            value,
            accepted_class=_PINNED_TERMINAL_LIFECYCLE,
            fields=_EXPECTED_TERMINAL_LIFECYCLE[0],
            wire_types=_EXPECTED_TERMINAL_LIFECYCLE[1],
        )
    return False


def _decoded_dataclass_shell_is_exact(
    value: object,
    *,
    accepted_class: type,
    fields: tuple[str, ...],
    wire_types: tuple[str, ...],
) -> bool:
    if type(value) is not accepted_class:
        return False
    try:
        values = tuple(getattr(value, name) for name in fields)
    except AttributeError:
        return False
    return all(
        _decoded_wire_value_is_exact(wire_type, item)
        for wire_type, item in zip(wire_types, values, strict=True)
    )


def _class_for_role(role: str) -> type:
    if role == "decision_rows":
        return _PINNED_DECISION_ROW
    if role == "security_open_values":
        return _PINNED_SECURITY_OPEN_VALUE
    if role == "benchmark_open_values":
        return _PINNED_BENCHMARK_OPEN_VALUE
    if role == "security_lifecycle_coverages":
        return _PINNED_SECURITY_LIFECYCLE_COVERAGE
    if role == "terminal_requirements":
        return _PINNED_TERMINAL_REQUIREMENT
    if role == "terminal_shareholder_payoffs":
        return _PINNED_TERMINAL_SHAREHOLDER_PAYOFF
    raise QcGlobalInputBundleError("partition role has no row class")


def _decode_row(role: str, value: object, contract: tuple) -> object:
    (
        contract_role,
        _row_schema,
        record_type,
        root_envelope,
        fields,
        wire_types,
        _canonical_order,
    ) = contract
    if role != contract_role:
        return _INVALID
    if role == "session_axis":
        if (
            root_envelope != "$object"
            or type(value) is not dict
            or tuple(value) != ("$object",)
            or type(value["$object"]) is not dict
            or tuple(value["$object"]) != ("session",)
        ):
            return _INVALID
        return _parse_date_value(value["$object"]["session"])
    decoded = _decode_dataclass_envelope(
        value,
        record_type=record_type,
        fields=fields,
        wire_types=wire_types,
    )
    if decoded is _INVALID:
        return _INVALID
    row_class = _class_for_role(role)
    try:
        return row_class(**decoded)
    except TypeError:
        return _INVALID


def _encoded_value(value: object) -> object:
    if type(value) is _PINNED_DATE:
        return {"$date": value.isoformat()}
    if type(value) is _PINNED_DECIMAL:
        if not value.is_finite():
            raise QcGlobalInputBundleError("decoded row contains a nonfinite Decimal")
        return {"$decimal": str(value)}
    if value is None or type(value) in (str, bool):
        return value
    value_type = type(value)
    if value_type is _PINNED_DECISION_ROW:
        record_type = _EXPECTED_ROW_CONTRACTS[1][2]
        field_names = _EXPECTED_ROW_CONTRACTS[1][4]
    elif value_type is _PINNED_SECURITY_OPEN_VALUE:
        record_type = _EXPECTED_ROW_CONTRACTS[2][2]
        field_names = _EXPECTED_ROW_CONTRACTS[2][4]
    elif value_type is _PINNED_BENCHMARK_OPEN_VALUE:
        record_type = _EXPECTED_ROW_CONTRACTS[3][2]
        field_names = _EXPECTED_ROW_CONTRACTS[3][4]
    elif value_type is _PINNED_SECURITY_LIFECYCLE_COVERAGE:
        record_type = _EXPECTED_ROW_CONTRACTS[4][2]
        field_names = _EXPECTED_ROW_CONTRACTS[4][4]
    elif value_type is _PINNED_TERMINAL_LIFECYCLE:
        record_type = "TerminalLifecycle"
        field_names = _EXPECTED_TERMINAL_LIFECYCLE[0]
    elif value_type is _PINNED_TERMINAL_REQUIREMENT:
        record_type = _EXPECTED_ROW_CONTRACTS[5][2]
        field_names = _EXPECTED_ROW_CONTRACTS[5][4]
    elif value_type is _PINNED_TERMINAL_SHAREHOLDER_PAYOFF:
        record_type = _EXPECTED_ROW_CONTRACTS[6][2]
        field_names = _EXPECTED_ROW_CONTRACTS[6][4]
    else:
        raise QcGlobalInputBundleError("decoded row contains an unknown value")
    return {
        "$dataclass": record_type,
        "$fields": {
            name: _encoded_value(getattr(value, name)) for name in field_names
        },
    }


def _render_decoded_partition(role: str, rows: tuple) -> bytes:
    rendered: list[bytes] = []
    for row in rows:
        value = (
            {"$object": {"session": _encoded_value(row)}}
            if role == "session_axis"
            else _encoded_value(row)
        )
        rendered.append(_canonical_bytes(value, newline=True))
    return b"".join(rendered)


def _decode_partition(
    *, role: str, payload: bytes, expected_row_count: int, contract: tuple
) -> tuple | None:
    if expected_row_count == 0:
        return () if payload == b"" else None
    if (
        not payload
        or payload.startswith(b"\xef\xbb\xbf")
        or b"\r" in payload
        or not payload.endswith(b"\n")
        or payload.count(b"\n") != expected_row_count
    ):
        return None
    raw_lines = payload[:-1].split(b"\n")
    if len(raw_lines) != expected_row_count or any(not item for item in raw_lines):
        return None
    rows: list[object] = []
    for raw_line in raw_lines:
        if len(raw_line) > MAX_SYNTHETIC_ROW_BYTES:
            return None
        text = _decode_utf8(raw_line)
        if text is _INVALID:
            return None
        value = _parse_json(text)
        if value is _INVALID or not _json_tree_is_exact(value):
            return None
        canonical_line = _try_canonical_bytes(value)
        if canonical_line is None or canonical_line != raw_line:
            return None
        row = _decode_row(role, value, contract)
        if row is _INVALID:
            return None
        rows.append(row)
    result = tuple(rows)
    canonical_order = contract[6]
    if role == "session_axis":
        keys = result
    else:
        keys = tuple(
            tuple(getattr(row, field) for field in canonical_order)
            for row in result
        )
    try:
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            return None
    except TypeError:
        return None
    if _render_decoded_partition(role, result) != payload:
        return None
    return result


def _call_manifest_loader(
    manifest_bytes: bytes, run_candidate: SyntheticQcRunCandidate
) -> SyntheticQcGlobalInputManifest | None:
    try:
        return _PINNED_LOAD_MANIFEST(
            manifest_bytes,
            run_candidate=run_candidate,
        )
    except (
        QcGlobalInputSchemaError,
        QcRunContractError,
        AttributeError,
        TypeError,
        ValueError,
    ):
        return None


def _call_partition_builder(
    *, role: str, partition_id: str, rows: tuple
) -> SyntheticPartitionBinding | None:
    try:
        return _PINNED_BUILD_PARTITION_BINDING(
            role=role,
            partition_id=partition_id,
            rows=rows,
        )
    except (
        EventStudyInputError,
        QcRunContractError,
        AttributeError,
        TypeError,
        ValueError,
    ):
        return None


def _bundle_document(
    *,
    manifest: SyntheticQcGlobalInputManifest,
    payloads: tuple[SyntheticGlobalInputPartitionPayload, ...],
    bundle_id: str | None,
    bundle_hash: str | None,
) -> dict[str, object]:
    return {
        "schema": BUNDLE_HASH_DOMAIN,
        "status": STATUS,
        "authority": AUTHORITY,
        "bundle_id": bundle_id,
        "bundle_hash": bundle_hash,
        "schema_binding": {
            "schema_id": SCHEMA_ID,
            "schema_sha256": SCHEMA_SHA256,
            "schema_artifact_sha256": SCHEMA_ARTIFACT_SHA256,
        },
        "manifest_binding": {
            "manifest_id": manifest.manifest_id,
            "manifest_sha256": manifest.manifest_sha256,
            "manifest_artifact_sha256": manifest.manifest_artifact_sha256,
        },
        "run_candidate_binding": {
            "candidate_id": manifest.run_candidate_id,
            "candidate_hash": manifest.run_candidate_hash,
            "runtime_code_authenticated": False,
        },
        "payload_validation": {
            "caller_declared_synthetic_bytes_match_manifest": True,
            "row_wire_contracts_validated": True,
            "canonical_order_validated": True,
            "canonical_rerender_validated": True,
            "production_truth_authenticated": False,
            "rights_authenticated": False,
            "point_in_time_provenance_authenticated": False,
            "row_source_provenance_authenticated": False,
            "real_outcome_authority": False,
            "synthetic_provenance_authenticated": False,
        },
        "partitions": [
            {
                "ordinal": descriptor.ordinal,
                "role": descriptor.role,
                "partition_id": descriptor.partition_id,
                "row_schema": descriptor.row_schema,
                "immutable_artifact_id": descriptor.immutable_artifact_id,
                "byte_count": len(payload.payload),
                "row_count": descriptor.row_count,
                "artifact_sha256": hashlib.sha256(payload.payload).hexdigest(),
            }
            for descriptor, payload in zip(manifest.partitions, payloads)
        ],
        "partition_census": {
            "role_count": len(payloads),
            "total_byte_count": sum(len(item.payload) for item in payloads),
            "total_row_count": manifest.total_row_count,
        },
        "external_bindings": dict(manifest.external_bindings),
        "capabilities": dict(manifest.capabilities),
    }


def _require_bundle_document_contract(
    value: object,
    *,
    manifest: SyntheticQcGlobalInputManifest,
    payloads: tuple[SyntheticGlobalInputPartitionPayload, ...],
    bundle_id: str | None,
    bundle_hash: str | None,
) -> dict[str, object]:
    """Validate a bundle document without trusting its construction helper."""

    if (
        type(value) is not dict
        or tuple(value) != BUNDLE_DOCUMENT_ROOT_FIELDS
        or not _json_tree_is_exact(value, allow_integers=True)
    ):
        raise QcGlobalInputBundleError("bundle document root contract changed")
    for name, fields in BUNDLE_DOCUMENT_NESTED_FIELDS:
        nested = value[name]
        if type(nested) is not dict or tuple(nested) != fields:
            raise QcGlobalInputBundleError(
                "bundle document nested field inventory changed"
            )
    partitions = value["partitions"]
    if (
        type(partitions) is not list
        or len(partitions) != len(payloads)
        or any(
            type(item) is not dict
            or tuple(item) != BUNDLE_PARTITION_DOCUMENT_FIELDS
            for item in partitions
        )
    ):
        raise QcGlobalInputBundleError(
            "bundle document partition field inventory changed"
        )
    expected = {
        "schema": "arv2-qc-global-input-bundle-v1",
        "status": "offline_synthetic_fixture_payloads_only_not_production_admission",
        "authority": (
            "exact_in_memory_synthetic_payload_decode_and_pure_core_"
            "composition_only_no_production_truth_rights_outcome_qc_result_"
            "or_trading_authority"
        ),
        "bundle_id": bundle_id,
        "bundle_hash": bundle_hash,
        "schema_binding": {
            "schema_id": SCHEMA_ID,
            "schema_sha256": SCHEMA_SHA256,
            "schema_artifact_sha256": SCHEMA_ARTIFACT_SHA256,
        },
        "manifest_binding": {
            "manifest_id": manifest.manifest_id,
            "manifest_sha256": manifest.manifest_sha256,
            "manifest_artifact_sha256": manifest.manifest_artifact_sha256,
        },
        "run_candidate_binding": {
            "candidate_id": manifest.run_candidate_id,
            "candidate_hash": manifest.run_candidate_hash,
            "runtime_code_authenticated": False,
        },
        "payload_validation": {
            "caller_declared_synthetic_bytes_match_manifest": True,
            "row_wire_contracts_validated": True,
            "canonical_order_validated": True,
            "canonical_rerender_validated": True,
            "production_truth_authenticated": False,
            "rights_authenticated": False,
            "point_in_time_provenance_authenticated": False,
            "row_source_provenance_authenticated": False,
            "real_outcome_authority": False,
            "synthetic_provenance_authenticated": False,
        },
        "partitions": [
            {
                "ordinal": descriptor.ordinal,
                "role": descriptor.role,
                "partition_id": descriptor.partition_id,
                "row_schema": descriptor.row_schema,
                "immutable_artifact_id": descriptor.immutable_artifact_id,
                "byte_count": len(payload.payload),
                "row_count": descriptor.row_count,
                "artifact_sha256": hashlib.sha256(payload.payload).hexdigest(),
            }
            for descriptor, payload in zip(manifest.partitions, payloads)
        ],
        "partition_census": {
            "role_count": len(payloads),
            "total_byte_count": sum(len(item.payload) for item in payloads),
            "total_row_count": manifest.total_row_count,
        },
        "external_bindings": dict(manifest.external_bindings),
        "capabilities": dict(manifest.capabilities),
    }
    actual_bytes = _try_canonical_bytes(value)
    expected_bytes = _try_canonical_bytes(expected)
    if (
        actual_bytes is None
        or expected_bytes is None
        or actual_bytes != expected_bytes
    ):
        raise QcGlobalInputBundleError("bundle document values changed")
    return value


def _load_bundle(
    *,
    run_candidate: SyntheticQcRunCandidate,
    manifest_bytes: bytes,
    partition_payloads: tuple[SyntheticGlobalInputPartitionPayload, ...],
    _static_check: object = _require_static_contract,
) -> SyntheticQcGlobalInputBundle:
    _static_check()
    if type(run_candidate) is not SyntheticQcRunCandidate:
        raise QcGlobalInputBundleError("run candidate type changed")
    try:
        candidate_values = tuple(
            getattr(run_candidate, name) for name in RUN_CANDIDATE_FIELDS
        )
    except AttributeError:
        raise QcGlobalInputBundleError("run candidate is missing retained state") from None
    if (
        type(candidate_values[0]) is not str
        or type(candidate_values[1]) is not str
        or any(type(value) is not tuple for value in candidate_values[2:6])
        or type(candidate_values[6]) is not bytes
    ):
        raise QcGlobalInputBundleError("run candidate retained state changed")
    if any(
        getattr(run_candidate, name) is not False
        for name in _PINNED_RUN_CANDIDATE_FALSE_PROPERTY_NAMES
    ):
        raise QcGlobalInputBundleError("run candidate acquired action authority")
    if type(manifest_bytes) is not bytes:
        raise QcGlobalInputBundleError("manifest must be exact bytes")
    if type(partition_payloads) is not tuple:
        raise QcGlobalInputBundleError("partition payloads must be an exact tuple")
    if len(partition_payloads) != len(_EXPECTED_ROLE_ORDER) or any(
        type(item) is not _PINNED_PARTITION_PAYLOAD_CLASS
        for item in partition_payloads
    ):
        raise QcGlobalInputBundleError("partition payload inventory is not exact")
    try:
        payload_values = tuple(
            (item.role, item.payload) for item in partition_payloads
        )
    except AttributeError:
        raise QcGlobalInputBundleError("partition payload is missing state") from None
    if any(
        type(role) is not str or type(payload) is not bytes
        for role, payload in payload_values
    ):
        raise QcGlobalInputBundleError("partition payload scalar type changed")
    if tuple(role for role, _ in payload_values) != _EXPECTED_ROLE_ORDER:
        raise QcGlobalInputBundleError("partition payload roles or order changed")
    manifest = _call_manifest_loader(manifest_bytes, run_candidate)
    if type(manifest) is not _PINNED_MANIFEST_CLASS:
        raise QcGlobalInputBundleError("synthetic manifest is not authenticated")
    if (
        type(manifest.partitions) is not tuple
        or any(
            type(descriptor) is not _PINNED_DESCRIPTOR_CLASS
            for descriptor in manifest.partitions
        )
    ):
        raise QcGlobalInputBundleError("manifest descriptor topology changed")
    if (
        manifest.total_byte_count > MAX_SYNTHETIC_BUNDLE_BYTES
        or manifest.total_row_count > MAX_SYNTHETIC_BUNDLE_ROWS
        or any(
            item.byte_count > MAX_SYNTHETIC_PARTITION_BYTES
            or item.row_count > MAX_SYNTHETIC_PARTITION_ROWS
            for item in manifest.partitions
        )
    ):
        raise QcGlobalInputBundleError("bundle exceeds synthetic resource bounds")
    copied_payloads: list[SyntheticGlobalInputPartitionPayload] = []
    total_bytes = 0
    total_rows = 0
    for item, descriptor in zip(partition_payloads, manifest.partitions):
        if item.role != descriptor.role:
            raise QcGlobalInputBundleError("partition payload role changed")
        if (
            descriptor.byte_count > MAX_SYNTHETIC_PARTITION_BYTES
            or descriptor.row_count > MAX_SYNTHETIC_PARTITION_ROWS
        ):
            raise QcGlobalInputBundleError("partition exceeds synthetic resource bounds")
        total_bytes += descriptor.byte_count
        total_rows += descriptor.row_count
        if (
            total_bytes > MAX_SYNTHETIC_BUNDLE_BYTES
            or total_rows > MAX_SYNTHETIC_BUNDLE_ROWS
        ):
            raise QcGlobalInputBundleError("bundle exceeds synthetic resource bounds")
        if (
            len(item.payload) != descriptor.byte_count
            or hashlib.sha256(item.payload).hexdigest() != descriptor.artifact_sha256
        ):
            raise QcGlobalInputBundleError("partition bytes do not match the manifest")
        copied_payloads.append(
            _PINNED_PARTITION_PAYLOAD_CLASS(
                role=str(item.role),
                payload=bytes(item.payload),
            )
        )
    if (
        total_bytes != manifest.total_byte_count
        or total_rows != manifest.total_row_count
    ):
        raise QcGlobalInputBundleError("bundle census does not match the manifest")
    candidate_by_role = {
        item.role: item for item in manifest._run_candidate.synthetic_partitions
    }
    decoded_by_role: dict[str, tuple] = {}
    for item, descriptor, contract in zip(
        copied_payloads,
        manifest.partitions,
        _EXPECTED_ROW_CONTRACTS,
    ):
        rows = _PINNED_DECODE_PARTITION(
            role=item.role,
            payload=item.payload,
            expected_row_count=descriptor.row_count,
            contract=contract,
        )
        if rows is None:
            raise QcGlobalInputBundleError(
                "partition is not canonical tagged JSONL for its row contract"
            )
        binding = _call_partition_builder(
            role=item.role,
            partition_id=descriptor.partition_id,
            rows=rows,
        )
        expected_binding = candidate_by_role.get(item.role)
        binding_values = None
        expected_binding_values = None
        if type(binding) is _PINNED_PARTITION_BINDING:
            values = (
                binding.role,
                binding.partition_id,
                binding.schema,
                binding.byte_count,
                binding.row_count,
                binding.sha256,
                binding.synthetic_fixture,
                binding.contains_licensed_rows,
                binding.contains_real_outcomes,
            )
            if (
                all(type(value) is str for value in values[:3])
                and type(values[3]) is int
                and type(values[4]) is int
                and type(values[5]) is str
                and values[6] is True
                and values[7] is False
                and values[8] is False
            ):
                binding_values = values
        if type(expected_binding) is _PINNED_PARTITION_BINDING:
            values = (
                expected_binding.role,
                expected_binding.partition_id,
                expected_binding.schema,
                expected_binding.byte_count,
                expected_binding.row_count,
                expected_binding.sha256,
                expected_binding.synthetic_fixture,
                expected_binding.contains_licensed_rows,
                expected_binding.contains_real_outcomes,
            )
            if (
                all(type(value) is str for value in values[:3])
                and type(values[3]) is int
                and type(values[4]) is int
                and type(values[5]) is str
                and values[6] is True
                and values[7] is False
                and values[8] is False
            ):
                expected_binding_values = values
        if (
            binding_values is None
            or expected_binding_values is None
            or binding_values != expected_binding_values
            or binding_values[3] != descriptor.byte_count
            or binding_values[4] != descriptor.row_count
            or binding_values[5] != descriptor.artifact_sha256
        ):
            raise QcGlobalInputBundleError(
                "decoded partition does not reproduce its candidate binding"
            )
        decoded_by_role[item.role] = rows
    payload_tuple = tuple(copied_payloads)
    seed = _PINNED_BUNDLE_DOCUMENT(
        manifest=manifest,
        payloads=payload_tuple,
        bundle_id=None,
        bundle_hash=None,
    )
    _PINNED_REQUIRE_BUNDLE_DOCUMENT(
        seed,
        manifest=manifest,
        payloads=payload_tuple,
        bundle_id=None,
        bundle_hash=None,
    )
    digest = hashlib.sha256(_canonical_bytes(seed)).hexdigest()
    bundle_id = f"synthetic-arv2-qc-global-input-bundle-{digest[:16]}"
    document = _PINNED_BUNDLE_DOCUMENT(
        manifest=manifest,
        payloads=payload_tuple,
        bundle_id=bundle_id,
        bundle_hash=digest,
    )
    _PINNED_REQUIRE_BUNDLE_DOCUMENT(
        document,
        manifest=manifest,
        payloads=payload_tuple,
        bundle_id=bundle_id,
        bundle_hash=digest,
    )
    canonical_document = _canonical_bytes(document, newline=True)
    bundle = _PINNED_BUNDLE_CLASS(
        bundle_id=bundle_id,
        bundle_hash=digest,
        bundle_artifact_sha256=hashlib.sha256(canonical_document).hexdigest(),
        schema_id=SCHEMA_ID,
        schema_sha256=SCHEMA_SHA256,
        schema_artifact_sha256=SCHEMA_ARTIFACT_SHA256,
        manifest_id=manifest.manifest_id,
        manifest_sha256=manifest.manifest_sha256,
        manifest_artifact_sha256=manifest.manifest_artifact_sha256,
        run_candidate_id=manifest.run_candidate_id,
        run_candidate_hash=manifest.run_candidate_hash,
        session_axis=decoded_by_role["session_axis"],
        decisions=decoded_by_role["decision_rows"],
        security_opens=decoded_by_role["security_open_values"],
        benchmark_opens=decoded_by_role["benchmark_open_values"],
        security_lifecycle_coverages=decoded_by_role[
            "security_lifecycle_coverages"
        ],
        terminal_requirements=decoded_by_role["terminal_requirements"],
        terminal_payoffs=decoded_by_role["terminal_shareholder_payoffs"],
        partition_payloads=payload_tuple,
        total_byte_count=total_bytes,
        total_row_count=total_rows,
        caller_declared_synthetic_bytes_match_manifest=True,
        row_contracts_validated=True,
        external_bindings=tuple(manifest.external_bindings),
        capabilities=tuple(manifest.capabilities),
        _manifest_bytes=bytes(manifest_bytes),
        _run_candidate=manifest._run_candidate,
        _canonical_document=canonical_document,
    )
    if any(
        getattr(bundle, name) is not False
        for name in _PINNED_BUNDLE_FALSE_PROPERTY_NAMES
    ):
        raise QcGlobalInputBundleError("bundle acquired action authority")
    return bundle


def load_synthetic_qc_global_input_bundle(
    *,
    run_candidate: SyntheticQcRunCandidate,
    manifest_bytes: bytes,
    partition_payloads: tuple[SyntheticGlobalInputPartitionPayload, ...],
) -> SyntheticQcGlobalInputBundle:
    """Authenticate and decode seven exact synthetic partition payloads."""

    return _PINNED_LOAD_BUNDLE(
        run_candidate=run_candidate,
        manifest_bytes=manifest_bytes,
        partition_payloads=partition_payloads,
    )


def require_synthetic_qc_global_input_bundle(
    bundle: SyntheticQcGlobalInputBundle,
    *,
    _static_check: object = _require_static_contract,
    _loader: object = _load_bundle,
) -> SyntheticQcGlobalInputBundle:
    """Rebuild a bundle from retained bytes and refuse changed state."""

    _static_check()
    if type(bundle) is not _PINNED_BUNDLE_CLASS:
        raise QcGlobalInputBundleError("bundle was not built by this contract")
    try:
        tuple(getattr(bundle, name) for name in _PINNED_BUNDLE_FIELDS)
    except AttributeError:
        raise QcGlobalInputBundleError("bundle state is incomplete") from None
    if any(
        getattr(bundle, name) is not False
        for name in _PINNED_BUNDLE_FALSE_PROPERTY_NAMES
    ):
        raise QcGlobalInputBundleError("bundle acquired action authority")
    string_fields = (
        "bundle_id",
        "bundle_hash",
        "bundle_artifact_sha256",
        "schema_id",
        "schema_sha256",
        "schema_artifact_sha256",
        "manifest_id",
        "manifest_sha256",
        "manifest_artifact_sha256",
        "run_candidate_id",
        "run_candidate_hash",
    )
    if any(type(getattr(bundle, name)) is not str for name in string_fields):
        raise QcGlobalInputBundleError("bundle scalar type changed")
    if any(
        _PINNED_HEX_64.fullmatch(getattr(bundle, name)) is None
        for name in (
            "bundle_hash",
            "bundle_artifact_sha256",
            "schema_sha256",
            "schema_artifact_sha256",
            "manifest_sha256",
            "manifest_artifact_sha256",
            "run_candidate_hash",
        )
    ):
        raise QcGlobalInputBundleError("bundle hash shape changed")
    tuple_fields = (
        "session_axis",
        "decisions",
        "security_opens",
        "benchmark_opens",
        "security_lifecycle_coverages",
        "terminal_requirements",
        "terminal_payoffs",
        "partition_payloads",
        "external_bindings",
        "capabilities",
    )
    if any(type(getattr(bundle, name)) is not tuple for name in tuple_fields):
        raise QcGlobalInputBundleError("bundle container type changed")
    if (
        type(bundle.total_byte_count) is not int
        or type(bundle.total_row_count) is not int
        or bundle.caller_declared_synthetic_bytes_match_manifest is not True
        or bundle.row_contracts_validated is not True
        or type(bundle._manifest_bytes) is not bytes
        or type(bundle._run_candidate) is not SyntheticQcRunCandidate
        or type(bundle._canonical_document) is not bytes
    ):
        raise QcGlobalInputBundleError("bundle authority or retained state changed")
    if (
        any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or item[1] is not None
            for item in bundle.external_bindings
        )
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or item[1] is not False
            for item in bundle.capabilities
        )
    ):
        raise QcGlobalInputBundleError("bundle acquired external authority")
    rows_by_role = (
        bundle.session_axis,
        bundle.decisions,
        bundle.security_opens,
        bundle.benchmark_opens,
        bundle.security_lifecycle_coverages,
        bundle.terminal_requirements,
        bundle.terminal_payoffs,
    )
    if len(bundle.partition_payloads) != len(rows_by_role):
        raise QcGlobalInputBundleError("bundle partition inventory changed")
    row_counts = tuple(len(rows) for rows in rows_by_role)
    if (
        any(count > MAX_SYNTHETIC_PARTITION_ROWS for count in row_counts)
        or sum(row_counts) > MAX_SYNTHETIC_BUNDLE_ROWS
        or bundle.total_row_count != sum(row_counts)
    ):
        raise QcGlobalInputBundleError("bundle row census changed")
    payload_values = []
    for role, payload in zip(
        _EXPECTED_ROLE_ORDER,
        bundle.partition_payloads,
        strict=True,
    ):
        if type(payload) is not _PINNED_PARTITION_PAYLOAD_CLASS:
            raise QcGlobalInputBundleError("bundle partition payload changed")
        try:
            payload_role = payload.role
            payload_bytes = payload.payload
        except AttributeError:
            raise QcGlobalInputBundleError(
                "bundle partition payload changed"
            ) from None
        if (
            type(payload_role) is not str
            or type(payload_bytes) is not bytes
            or payload_role != role
            or len(payload_bytes) > MAX_SYNTHETIC_PARTITION_BYTES
        ):
            raise QcGlobalInputBundleError("bundle partition payload changed")
        payload_values.append((payload_role, payload_bytes))
    if (
        sum(len(value[1]) for value in payload_values)
        > MAX_SYNTHETIC_BUNDLE_BYTES
        or bundle.total_byte_count
        != sum(len(value[1]) for value in payload_values)
    ):
        raise QcGlobalInputBundleError("bundle payload census changed")
    for role, rows, payload_value, contract in zip(
        _EXPECTED_ROLE_ORDER,
        rows_by_role,
        payload_values,
        _EXPECTED_ROW_CONTRACTS,
        strict=True,
    ):
        payload_role, payload_bytes = payload_value
        if role == "session_axis":
            rows_are_exact = all(type(row) is _PINNED_DATE for row in rows)
        else:
            accepted_class = _class_for_role(role)
            rows_are_exact = all(
                _decoded_dataclass_shell_is_exact(
                    row,
                    accepted_class=accepted_class,
                    fields=contract[4],
                    wire_types=contract[5],
                )
                for row in rows
            )
        if not rows_are_exact:
            raise QcGlobalInputBundleError("bundle decoded row shell changed")
        try:
            rendered_rows = _PINNED_RENDER_DECODED_PARTITION(role, rows)
        except (
            QcGlobalInputBundleError,
            AttributeError,
            RecursionError,
            TypeError,
            ValueError,
        ):
            raise QcGlobalInputBundleError("bundle decoded rows changed") from None
        if rendered_rows != payload_bytes:
            raise QcGlobalInputBundleError("bundle decoded rows changed")
    rebuilt = _loader(
        run_candidate=bundle._run_candidate,
        manifest_bytes=bundle._manifest_bytes,
        partition_payloads=bundle.partition_payloads,
    )
    scalar_fields = (
        "bundle_id",
        "bundle_hash",
        "bundle_artifact_sha256",
        "schema_id",
        "schema_sha256",
        "schema_artifact_sha256",
        "manifest_id",
        "manifest_sha256",
        "manifest_artifact_sha256",
        "run_candidate_id",
        "run_candidate_hash",
        "total_byte_count",
        "total_row_count",
        "caller_declared_synthetic_bytes_match_manifest",
        "row_contracts_validated",
        "external_bindings",
        "capabilities",
    )
    if any(
        getattr(bundle, name) != getattr(rebuilt, name)
        for name in scalar_fields
    ) or bundle._canonical_document != rebuilt._canonical_document:
        raise QcGlobalInputBundleError("bundle changed after construction")
    return bundle


def _call_event_study(bundle: SyntheticQcGlobalInputBundle) -> EventStudyBatch | None:
    try:
        batch = _PINNED_COLLECT_EVENT_STUDY(
            run_candidate=bundle._run_candidate,
            session_axis=bundle.session_axis,
            decisions=bundle.decisions,
            security_opens=bundle.security_opens,
            benchmark_opens=bundle.benchmark_opens,
            security_lifecycle_coverages=bundle.security_lifecycle_coverages,
            terminal_requirements=bundle.terminal_requirements,
            terminal_payoffs=bundle.terminal_payoffs,
        )
        return _PINNED_REQUIRE_EVENT_STUDY_BATCH(batch)
    except (
        EventStudyInputError,
        QcRunContractError,
        TypeError,
        ValueError,
        AttributeError,
    ):
        return None


def _event_study_batch_is_valid(value: object) -> bool:
    try:
        return _PINNED_REQUIRE_EVENT_STUDY_BATCH(value) is value
    except (
        EventStudyInputError,
        QcRunContractError,
        TypeError,
        ValueError,
        AttributeError,
    ):
        return False


def collect_synthetic_event_study_from_global_input_bundle(
    bundle: SyntheticQcGlobalInputBundle,
    *,
    _require_bundle: object = require_synthetic_qc_global_input_bundle,
    _call_core: object = _call_event_study,
    _validate_batch: object = _event_study_batch_is_valid,
) -> EventStudyBatch:
    """Run only the reviewed pure core over an authenticated synthetic bundle."""

    _require_bundle(bundle)
    batch = _call_core(bundle)
    if type(batch) is not _PINNED_EVENT_STUDY_BATCH:
        raise QcGlobalInputBundleError(
            "synthetic bundle is not a valid event-study input census"
        )
    try:
        tuple(getattr(batch, name) for name in _PINNED_EVENT_STUDY_BATCH_FIELDS)
    except AttributeError:
        raise QcGlobalInputBundleError(
            "synthetic bundle is not a valid event-study input census"
        ) from None
    if (
        type(batch.observations) is not tuple
        or type(batch.refusals) is not tuple
        or type(batch.security_lifecycle_coverages) is not tuple
        or type(batch.expected_decision_horizons) is not int
        or type(batch.candidate_declaration_hash) is not str
        or type(batch.terminal_payoff_reinvestment_policy_id) is not str
        or type(batch.input_partition_set_sha256) is not str
        or type(batch.batch_hash) is not str
        or any(
            type(item) is not _PINNED_EVENT_STUDY_OBSERVATION
            for item in batch.observations
        )
        or any(
            type(item) is not _PINNED_EVENT_STUDY_REFUSAL
            for item in batch.refusals
        )
        or any(
            type(item) is not _PINNED_SECURITY_LIFECYCLE_COVERAGE
            for item in batch.security_lifecycle_coverages
        )
    ):
        raise QcGlobalInputBundleError("event-study output topology changed")
    output_rows = (*batch.observations, *batch.refusals)
    try:
        tuple(
            tuple(
                getattr(item, name)
                for name in _PINNED_EVENT_STUDY_OBSERVATION_FIELDS
            )
            for item in batch.observations
        )
        tuple(
            tuple(
                getattr(item, name)
                for name in _PINNED_EVENT_STUDY_REFUSAL_FIELDS
            )
            for item in batch.refusals
        )
        tuple(
            tuple(
                getattr(item, name)
                for name in _PINNED_SECURITY_LIFECYCLE_COVERAGE_FIELDS
            )
            for item in batch.security_lifecycle_coverages
        )
        output_projection = tuple(
            (item.row_id, item.horizon_sessions)
            for item in output_rows
        )
        lifecycle_projection = tuple(
            item.terminal_lifecycle
            for item in batch.security_lifecycle_coverages
        )
    except AttributeError:
        raise QcGlobalInputBundleError(
            "event-study output state is incomplete"
        ) from None
    if any(
        type(row_id) is not str or type(horizon) is not int
        for row_id, horizon in output_projection
    ):
        raise QcGlobalInputBundleError("event-study output scalar type changed")
    if any(
        item is not None and type(item) is not _PINNED_TERMINAL_LIFECYCLE
        for item in lifecycle_projection
    ):
        raise QcGlobalInputBundleError("event-study output topology changed")
    try:
        tuple(
            tuple(
                getattr(item, name)
                for name in _PINNED_TERMINAL_LIFECYCLE_OUTPUT_FIELDS
            )
            for item in lifecycle_projection
            if item is not None
        )
    except AttributeError:
        raise QcGlobalInputBundleError(
            "event-study output state is incomplete"
        ) from None
    if not _validate_batch(batch):
        raise QcGlobalInputBundleError(
            "synthetic bundle is not a valid event-study input census"
        )
    if any(
        getattr(batch, name) is not False
        for name in _PINNED_EVENT_STUDY_FALSE_PROPERTY_NAMES
    ):
        raise QcGlobalInputBundleError("event-study output acquired action authority")
    if batch.candidate_declaration_hash != bundle.run_candidate_hash:
        raise QcGlobalInputBundleError("event-study output lineage changed")
    expected_output_count = len(bundle.decisions) * 4
    if (
        batch.expected_decision_horizons != expected_output_count
        or len(output_rows) != expected_output_count
        or batch.terminal_payoff_reinvestment_policy_id
        != "arv2-terminal-payoff-benchmark-splice-v1"
        or any(
            type(item.horizon_sessions) is not int
            or item.horizon_sessions not in (1, 5, 20, 60)
            for item in output_rows
        )
        or {
            (row_id, horizon)
            for row_id, horizon in output_projection
        }
        != {
            (decision.row_id, horizon)
            for decision in bundle.decisions
            for horizon in (1, 5, 20, 60)
        }
    ):
        raise QcGlobalInputBundleError("event-study output census changed")
    return batch


_SCHEMA_RENDERER_IMPLEMENTATION = render_qc_global_input_bundle_schema_bytes
_BUNDLE_VALIDATOR_IMPLEMENTATION = require_synthetic_qc_global_input_bundle
_COMPOSER_IMPLEMENTATION = collect_synthetic_event_study_from_global_input_bundle


def _seal_schema_renderer(implementation: object, static_check: object) -> object:
    implementation_a = implementation
    implementation_b = implementation
    implementation_c = implementation
    static_check_a = static_check
    static_check_b = static_check
    static_check_c = static_check
    static_guard = (static_check, static_check.__code__)
    static_guard_a = static_guard
    static_guard_b = static_guard
    static_guard_c = static_guard

    def sealed() -> bytes:
        try:
            checker = (
                static_check_a
                if static_check_a is static_check_b
                or static_check_a is static_check_c
                else static_check_b
            )
            guard = (
                static_guard_a
                if static_guard_a is static_guard_b
                or static_guard_a is static_guard_c
                else static_guard_b
            )
            if (
                static_guard_a is not static_guard_b
                or static_guard_a is not static_guard_c
                or checker is not guard[0]
                or checker.__code__ is not guard[1]
            ):
                raise _PINNED_BUNDLE_ERROR(
                    "bundle wrapper topology changed"
                )
        except:
            raise _PINNED_BUNDLE_ERROR(
                "bundle wrapper topology changed"
            ) from None
        checker()
        if (
            implementation_a is not implementation_b
            or implementation_a is not implementation_c
            or static_check_a is not static_check_b
            or static_check_a is not static_check_c
        ):
            raise _PINNED_BUNDLE_ERROR("bundle wrapper topology changed")
        return implementation_a()

    sealed.__name__ = "render_qc_global_input_bundle_schema_bytes"
    sealed.__doc__ = render_qc_global_input_bundle_schema_bytes.__doc__
    return sealed


def _seal_loader(implementation: object, static_check: object) -> object:
    implementation_a = implementation
    implementation_b = implementation
    implementation_c = implementation
    static_check_a = static_check
    static_check_b = static_check
    static_check_c = static_check
    static_guard = (static_check, static_check.__code__)
    static_guard_a = static_guard
    static_guard_b = static_guard
    static_guard_c = static_guard

    def sealed(
        *,
        run_candidate: SyntheticQcRunCandidate,
        manifest_bytes: bytes,
        partition_payloads: tuple[SyntheticGlobalInputPartitionPayload, ...],
    ) -> SyntheticQcGlobalInputBundle:
        try:
            checker = (
                static_check_a
                if static_check_a is static_check_b
                or static_check_a is static_check_c
                else static_check_b
            )
            guard = (
                static_guard_a
                if static_guard_a is static_guard_b
                or static_guard_a is static_guard_c
                else static_guard_b
            )
            if (
                static_guard_a is not static_guard_b
                or static_guard_a is not static_guard_c
                or checker is not guard[0]
                or checker.__code__ is not guard[1]
            ):
                raise _PINNED_BUNDLE_ERROR(
                    "bundle wrapper topology changed"
                )
        except:
            raise _PINNED_BUNDLE_ERROR(
                "bundle wrapper topology changed"
            ) from None
        checker()
        if (
            implementation_a is not implementation_b
            or implementation_a is not implementation_c
            or static_check_a is not static_check_b
            or static_check_a is not static_check_c
        ):
            raise _PINNED_BUNDLE_ERROR("bundle wrapper topology changed")
        return implementation_a(
            run_candidate=run_candidate,
            manifest_bytes=manifest_bytes,
            partition_payloads=partition_payloads,
        )

    sealed.__name__ = "load_synthetic_qc_global_input_bundle"
    sealed.__doc__ = load_synthetic_qc_global_input_bundle.__doc__
    return sealed


def _seal_bundle_validator(implementation: object, static_check: object) -> object:
    implementation_a = implementation
    implementation_b = implementation
    implementation_c = implementation
    static_check_a = static_check
    static_check_b = static_check
    static_check_c = static_check
    static_guard = (static_check, static_check.__code__)
    static_guard_a = static_guard
    static_guard_b = static_guard
    static_guard_c = static_guard

    def sealed(
        bundle: SyntheticQcGlobalInputBundle,
    ) -> SyntheticQcGlobalInputBundle:
        try:
            checker = (
                static_check_a
                if static_check_a is static_check_b
                or static_check_a is static_check_c
                else static_check_b
            )
            guard = (
                static_guard_a
                if static_guard_a is static_guard_b
                or static_guard_a is static_guard_c
                else static_guard_b
            )
            if (
                static_guard_a is not static_guard_b
                or static_guard_a is not static_guard_c
                or checker is not guard[0]
                or checker.__code__ is not guard[1]
            ):
                raise _PINNED_BUNDLE_ERROR(
                    "bundle wrapper topology changed"
                )
        except:
            raise _PINNED_BUNDLE_ERROR(
                "bundle wrapper topology changed"
            ) from None
        checker()
        if (
            implementation_a is not implementation_b
            or implementation_a is not implementation_c
            or static_check_a is not static_check_b
            or static_check_a is not static_check_c
        ):
            raise _PINNED_BUNDLE_ERROR("bundle wrapper topology changed")
        return implementation_a(bundle)

    sealed.__name__ = "require_synthetic_qc_global_input_bundle"
    sealed.__doc__ = require_synthetic_qc_global_input_bundle.__doc__
    return sealed


def _seal_composer(implementation: object, static_check: object) -> object:
    implementation_a = implementation
    implementation_b = implementation
    implementation_c = implementation
    static_check_a = static_check
    static_check_b = static_check
    static_check_c = static_check
    static_guard = (static_check, static_check.__code__)
    static_guard_a = static_guard
    static_guard_b = static_guard
    static_guard_c = static_guard

    def sealed(bundle: SyntheticQcGlobalInputBundle) -> EventStudyBatch:
        try:
            checker = (
                static_check_a
                if static_check_a is static_check_b
                or static_check_a is static_check_c
                else static_check_b
            )
            guard = (
                static_guard_a
                if static_guard_a is static_guard_b
                or static_guard_a is static_guard_c
                else static_guard_b
            )
            if (
                static_guard_a is not static_guard_b
                or static_guard_a is not static_guard_c
                or checker is not guard[0]
                or checker.__code__ is not guard[1]
            ):
                raise _PINNED_BUNDLE_ERROR(
                    "bundle wrapper topology changed"
                )
        except:
            raise _PINNED_BUNDLE_ERROR(
                "bundle wrapper topology changed"
            ) from None
        checker()
        if (
            implementation_a is not implementation_b
            or implementation_a is not implementation_c
            or static_check_a is not static_check_b
            or static_check_a is not static_check_c
        ):
            raise _PINNED_BUNDLE_ERROR("bundle wrapper topology changed")
        return implementation_a(bundle)

    sealed.__name__ = "collect_synthetic_event_study_from_global_input_bundle"
    sealed.__doc__ = collect_synthetic_event_study_from_global_input_bundle.__doc__
    return sealed


render_qc_global_input_bundle_schema_bytes = _seal_schema_renderer(
    _SCHEMA_RENDERER_IMPLEMENTATION,
    _require_static_contract,
)
load_synthetic_qc_global_input_bundle = _seal_loader(
    _load_bundle,
    _require_static_contract,
)
require_synthetic_qc_global_input_bundle = _seal_bundle_validator(
    _BUNDLE_VALIDATOR_IMPLEMENTATION,
    _require_static_contract,
)
collect_synthetic_event_study_from_global_input_bundle = _seal_composer(
    _COMPOSER_IMPLEMENTATION,
    _require_static_contract,
)


_PINNED_PARTITION_PAYLOAD_CLASS = SyntheticGlobalInputPartitionPayload
_PINNED_BUNDLE_CLASS = SyntheticQcGlobalInputBundle
_PINNED_PUBLIC_SCHEMA_RENDERER = render_qc_global_input_bundle_schema_bytes
_PINNED_PUBLIC_LOADER = load_synthetic_qc_global_input_bundle
_PINNED_SCHEMA_RENDERER_IMPLEMENTATION = _SCHEMA_RENDERER_IMPLEMENTATION
_PINNED_BUNDLE_VALIDATOR_IMPLEMENTATION = _BUNDLE_VALIDATOR_IMPLEMENTATION
_PINNED_COMPOSER_IMPLEMENTATION = _COMPOSER_IMPLEMENTATION
_PINNED_REQUIRE_STATIC_CONTRACT = _require_static_contract
_PINNED_LOAD_BUNDLE = _load_bundle
_PINNED_PUBLIC_REQUIRE_BUNDLE = require_synthetic_qc_global_input_bundle
_PINNED_CALL_EVENT_STUDY = _call_event_study
_PINNED_EVENT_STUDY_BATCH_IS_VALID = _event_study_batch_is_valid
_PINNED_DEPENDENCY_VALUE_AUTHORITY_IS_CURRENT = (
    _dependency_value_authority_is_current
)
_PINNED_PUBLIC_COMPOSER = (
    collect_synthetic_event_study_from_global_input_bundle
)
_PINNED_DECODE_PARTITION = _decode_partition
_PINNED_BUNDLE_DOCUMENT = _bundle_document
_PINNED_REQUIRE_BUNDLE_DOCUMENT = _require_bundle_document_contract
_PINNED_RENDER_DECODED_PARTITION = _render_decoded_partition
_PINNED_CALL_PARENT_SCHEMA_RENDERER = _call_parent_schema_renderer
_INTERNAL_HELPERS = (
    _capture_dependency_value_authority,
    _dependency_value_authority_is_current,
    _call_parent_schema_renderer,
    _decode_utf8,
    _reject_pairs,
    _reject_number,
    _parse_json,
    _json_tree_is_exact,
    _parse_date_value,
    _parse_decimal_value,
    _decode_terminal_lifecycle,
    _decode_wire_value,
    _decode_dataclass_envelope,
    _decoded_wire_value_is_exact,
    _decoded_dataclass_shell_is_exact,
    _class_for_role,
    _decode_row,
    _encoded_value,
    _render_decoded_partition,
    _decode_partition,
    _call_manifest_loader,
    _call_partition_builder,
    _bundle_document,
    _require_bundle_document_contract,
    _load_bundle,
    require_synthetic_qc_global_input_bundle,
    _call_event_study,
    _event_study_batch_is_valid,
)
_PINNED_INTERNAL_HELPERS = _INTERNAL_HELPERS


def _capture_function_state(implementation: object) -> tuple:
    if type(implementation) is not _PINNED_FUNCTION_TYPE:
        raise RuntimeError("expected an exact function at topology capture")
    defaults = implementation.__defaults__
    kwdefaults = implementation.__kwdefaults__
    closure = implementation.__closure__
    return (
        implementation.__code__,
        defaults,
        () if defaults is None else tuple(defaults),
        kwdefaults,
        () if kwdefaults is None else tuple(kwdefaults.items()),
        closure,
        (
            ()
            if closure is None
            else tuple((cell, cell.cell_contents) for cell in closure)
        ),
    )


def _capture_plain_class_topology(accepted_class: type) -> tuple:
    class_dict = type.__getattribute__(accepted_class, "__dict__")
    entries = tuple(
        (
            name,
            member,
            (
                _capture_function_state(member)
                if type(member) is _PINNED_FUNCTION_TYPE
                else None
            ),
        )
        for name, member in class_dict.items()
    )
    return accepted_class, entries


def _capture_class_topology(
    accepted_class: type,
    property_names: tuple[str, ...] = (),
    extra_member_names: tuple[str, ...] = (),
) -> tuple:
    class_dict = type.__getattribute__(accepted_class, "__dict__")
    field_registry = class_dict["__dataclass_fields__"]
    field_names = tuple(
        field.name for field in _PINNED_DATACLASS_FIELDS(accepted_class)
    )
    member_names = (
        *_PINNED_CLASS_TOPOLOGY_MEMBER_NAMES,
        *field_names,
        *extra_member_names,
    )
    members = []
    for name in member_names:
        present = name in class_dict
        member = class_dict[name] if present else None
        function_state = (
            _capture_function_state(member)
            if type(member) is _PINNED_FUNCTION_TYPE
            else None
        )
        members.append((name, present, member, function_state))
    properties = []
    for name in property_names:
        descriptor = class_dict[name]
        if type(descriptor) is not _PINNED_PROPERTY_TYPE:
            raise RuntimeError("expected an exact property at topology capture")
        fget = descriptor.fget
        if type(fget) is not _PINNED_FUNCTION_TYPE:
            raise RuntimeError("expected an exact property getter at topology capture")
        properties.append(
            (name, descriptor, fget, _capture_function_state(fget))
        )
    field_entries = tuple(
        (
            name,
            field,
            _PINNED_DATACLASS_FIELD_NAME_DESCRIPTOR.__get__(
                field,
                _PINNED_DATACLASS_FIELD_CLASS,
            ),
            _PINNED_DATACLASS_FIELD_TYPE_DESCRIPTOR.__get__(
                field,
                _PINNED_DATACLASS_FIELD_CLASS,
            ),
        )
        for name, field in field_registry.items()
    )
    return (
        accepted_class,
        field_names,
        tuple(members),
        tuple(properties),
        field_registry,
        field_entries,
    )


_CLASS_TOPOLOGIES = (
    _capture_class_topology(DecisionRow),
    _capture_class_topology(SecurityOpenValue),
    _capture_class_topology(BenchmarkOpenValue),
    _capture_class_topology(SecurityLifecycleCoverage),
    _capture_class_topology(TerminalLifecycle),
    _capture_class_topology(TerminalRequirement),
    _capture_class_topology(TerminalShareholderPayoff),
    _capture_class_topology(EventStudyObservation),
    _capture_class_topology(EventStudyRefusal),
    _capture_class_topology(
        EventStudyBatch,
        EVENT_STUDY_FALSE_PROPERTY_NAMES,
        EVENT_STUDY_BATCH_METHOD_NAMES,
    ),
    _capture_class_topology(RowContract),
    _capture_class_topology(ParentArtifact),
    _capture_class_topology(CodeFileBinding),
    _capture_class_topology(SyntheticPartitionBinding),
    _capture_class_topology(EvaluationWindow),
    _capture_class_topology(
        SyntheticQcRunCandidate,
        RUN_CANDIDATE_FALSE_PROPERTY_NAMES,
    ),
    _capture_class_topology(GlobalInputPartitionDescriptor),
    _capture_class_topology(SyntheticQcGlobalInputManifest),
    _capture_class_topology(SyntheticGlobalInputPartitionPayload),
    _capture_class_topology(
        SyntheticQcGlobalInputBundle,
        BUNDLE_FALSE_PROPERTY_NAMES,
    ),
)
_PINNED_CLASS_TOPOLOGIES = _CLASS_TOPOLOGIES


_PARENT_MODULE_GLOBALS = (
    load_synthetic_qc_global_input_manifest_bytes.__globals__,
    require_synthetic_qc_run_candidate.__globals__,
    collect_synthetic_event_study.__globals__,
)
_STDLIB_MODULE_GLOBALS = (
    json.loads.__globals__,
    json.JSONDecoder.__init__.__globals__,
    json.JSONEncoder.__init__.__globals__,
    dataclasses.fields.__globals__,
    json.JSONDecoder.__init__.__globals__["scanner"].py_make_scanner.__globals__,
    Counter.__init__.__globals__,
)
_runtime_dependency_globals: list[dict[str, object]] = []
_pending_dependency_globals = [
    *_PARENT_MODULE_GLOBALS,
    *_STDLIB_MODULE_GLOBALS,
]
while _pending_dependency_globals:
    _candidate_globals = _pending_dependency_globals.pop()
    if any(
        _candidate_globals is existing
        for existing in _runtime_dependency_globals
    ):
        continue
    _runtime_dependency_globals.append(_candidate_globals)
    for _candidate_value in _candidate_globals.values():
        if (
            type(_candidate_value) is _PINNED_FUNCTION_TYPE
            and not any(
                _candidate_value.__globals__ is existing
                for existing in _runtime_dependency_globals
            )
            and not any(
                _candidate_value.__globals__ is pending
                for pending in _pending_dependency_globals
            )
        ):
            _pending_dependency_globals.append(_candidate_value.__globals__)
_RUNTIME_DEPENDENCY_GLOBALS = tuple(_runtime_dependency_globals)
del _candidate_globals
del _candidate_value
del _pending_dependency_globals
del _runtime_dependency_globals

_runtime_dependency_modules: list[ModuleType] = []
for _dependency_globals in _RUNTIME_DEPENDENCY_GLOBALS:
    for _candidate_value in _dependency_globals.values():
        if (
            type(_candidate_value) is _PINNED_MODULE_TYPE
            and not any(
                _candidate_value is existing
                for existing in _runtime_dependency_modules
            )
        ):
            _runtime_dependency_modules.append(_candidate_value)
_RUNTIME_DEPENDENCY_MODULES = tuple(_runtime_dependency_modules)
_PINNED_RUNTIME_DEPENDENCY_MODULES = _RUNTIME_DEPENDENCY_MODULES
del _candidate_value
del _dependency_globals
del _runtime_dependency_modules

_BOOTSTRAP_MODULE_AUTHORITIES = tuple(
    (
        module,
        _PINNED_OBJECT_GETATTRIBUTE(module, "__dict__"),
        tuple(
            item
            for item in _PINNED_DICT_ITEMS(
                _PINNED_OBJECT_GETATTRIBUTE(module, "__dict__")
            )
            if not (
                type(item[0]) is str
                and item[0] == "__warningregistry__"
            )
        ),
    )
    for module in (
        _PINNED_DATACLASSES_MODULE,
        _PINNED_HASHLIB_MODULE,
        _PINNED_JSON_MODULE,
        _PINNED_RE_MODULE,
    )
)
_PINNED_BOOTSTRAP_MODULE_AUTHORITIES = _BOOTSTRAP_MODULE_AUTHORITIES

_parent_module_functions: list[object] = []
for _dependency_globals in _RUNTIME_DEPENDENCY_GLOBALS:
    for _candidate_value in _dependency_globals.values():
        if (
            type(_candidate_value) is _PINNED_FUNCTION_TYPE
            and not any(
                _candidate_value is existing
                for existing in _parent_module_functions
            )
        ):
            _parent_module_functions.append(_candidate_value)
_PARENT_MODULE_FUNCTIONS = tuple(_parent_module_functions)
del _candidate_value
del _dependency_globals
del _parent_module_functions

_EVENT_STUDY_GLOBALS = collect_synthetic_event_study.__globals__
_REVIEWED_SESSION_AXIS_WRAPPER = _EVENT_STUDY_GLOBALS[
    "_reviewed_session_axis"
]
_REVIEWED_SESSION_INDEX_WRAPPER = _EVENT_STUDY_GLOBALS[
    "_reviewed_session_index"
]
_PINNED_REVIEWED_SESSION_AXIS_WRAPPER = _REVIEWED_SESSION_AXIS_WRAPPER
_PINNED_REVIEWED_SESSION_INDEX_WRAPPER = _REVIEWED_SESSION_INDEX_WRAPPER
_PINNED_REVIEWED_SESSION_AXIS = _REVIEWED_SESSION_AXIS_WRAPPER()
_PINNED_REVIEWED_SESSION_INDEX = _REVIEWED_SESSION_INDEX_WRAPPER()
_CACHE_INFO_CLASS = type(
    _REVIEWED_SESSION_AXIS_WRAPPER.cache_info()
)
_PINNED_CACHE_INFO_CLASS = _CACHE_INFO_CLASS
_COUNTER_COLLECTIONS_ABC_MODULE = _PINNED_COUNTER_CLASS.update.__globals__[
    "_collections_abc"
]
_PINNED_COUNTER_COLLECTIONS_ABC_MODULE = _COUNTER_COLLECTIONS_ABC_MODULE
_COUNTER_COLLECTIONS_ABC_MODULE_DICT = _PINNED_OBJECT_GETATTRIBUTE(
    _COUNTER_COLLECTIONS_ABC_MODULE,
    "__dict__",
)
_PINNED_COUNTER_COLLECTIONS_ABC_MODULE_DICT = (
    _COUNTER_COLLECTIONS_ABC_MODULE_DICT
)
_PINNED_COUNTER_COLLECTIONS_ABC_MODULE_ENTRIES = tuple(
    _COUNTER_COLLECTIONS_ABC_MODULE_DICT.items()
)
_COLLECTIONS_ABC_MAPPING_CLASS = _COUNTER_COLLECTIONS_ABC_MODULE_DICT[
    "Mapping"
]
_PINNED_COLLECTIONS_ABC_MAPPING_CLASS = _COLLECTIONS_ABC_MAPPING_CLASS
_ABC_META_CLASS = type(_COLLECTIONS_ABC_MAPPING_CLASS)
_PINNED_ABC_META_CLASS = _ABC_META_CLASS
_PLAIN_CLASS_TOPOLOGIES = (
    _capture_plain_class_topology(json.JSONDecoder),
    _capture_plain_class_topology(json.JSONEncoder),
    _capture_plain_class_topology(json.JSONDecodeError),
    _capture_plain_class_topology(Counter),
    _capture_plain_class_topology(_CACHE_INFO_CLASS),
    _capture_plain_class_topology(_COLLECTIONS_ABC_MAPPING_CLASS),
    _capture_plain_class_topology(_ABC_META_CLASS),
)
_PINNED_PLAIN_CLASS_TOPOLOGIES = _PLAIN_CLASS_TOPOLOGIES
_REVIEWED_SESSION_AXIS_WRAPPER_DICT = _PINNED_OBJECT_GETATTRIBUTE(
    _REVIEWED_SESSION_AXIS_WRAPPER,
    "__dict__",
)
_REVIEWED_SESSION_INDEX_WRAPPER_DICT = _PINNED_OBJECT_GETATTRIBUTE(
    _REVIEWED_SESSION_INDEX_WRAPPER,
    "__dict__",
)
_PINNED_REVIEWED_SESSION_AXIS_WRAPPER_DICT = (
    _REVIEWED_SESSION_AXIS_WRAPPER_DICT
)
_PINNED_REVIEWED_SESSION_INDEX_WRAPPER_DICT = (
    _REVIEWED_SESSION_INDEX_WRAPPER_DICT
)
_PINNED_REVIEWED_SESSION_AXIS_WRAPPER_ENTRIES = tuple(
    _REVIEWED_SESSION_AXIS_WRAPPER_DICT.items()
)
_PINNED_REVIEWED_SESSION_INDEX_WRAPPER_ENTRIES = tuple(
    _REVIEWED_SESSION_INDEX_WRAPPER_DICT.items()
)
_PARENT_WRAPPED_FUNCTIONS = (
    _REVIEWED_SESSION_AXIS_WRAPPER.__wrapped__,
    _REVIEWED_SESSION_INDEX_WRAPPER.__wrapped__,
)
_PLAIN_CLASS_FUNCTIONS = tuple(
    member
    for _, entries in _PLAIN_CLASS_TOPOLOGIES
    for _, member, function_state in entries
    if function_state is not None
)
_LOCAL_RUNTIME_FUNCTIONS = (
    _require_static_contract,
    *_INTERNAL_HELPERS,
    _schema_contract_document,
    _try_canonical_bytes,
    _canonical_bytes,
    _schema_identity_document,
    _SCHEMA_RENDERER_IMPLEMENTATION,
    _BUNDLE_VALIDATOR_IMPLEMENTATION,
    _COMPOSER_IMPLEMENTATION,
    render_qc_global_input_bundle_schema_bytes,
    load_synthetic_qc_global_input_bundle,
    require_synthetic_qc_global_input_bundle,
    collect_synthetic_event_study_from_global_input_bundle,
    json.dumps,
    json.loads,
    dataclasses.fields,
)
_FUNCTION_TOPOLOGIES = tuple(
    (implementation, _capture_function_state(implementation))
    for implementation in (
        *_LOCAL_RUNTIME_FUNCTIONS,
        *_PARENT_MODULE_FUNCTIONS,
        *_PARENT_WRAPPED_FUNCTIONS,
        *_PLAIN_CLASS_FUNCTIONS,
    )
)
_PINNED_FUNCTION_TOPOLOGIES = _FUNCTION_TOPOLOGIES


_DEPENDENCY_GRAPH_CONTAINER_TYPES = (
    dict,
    MappingProxyType,
    tuple,
    list,
    set,
    frozenset,
)
_PINNED_DEPENDENCY_GRAPH_CONTAINER_TYPES = _DEPENDENCY_GRAPH_CONTAINER_TYPES
_DEPENDENCY_GRAPH_RECORD_TYPES = (
    DecisionRow,
    SecurityOpenValue,
    BenchmarkOpenValue,
    SecurityLifecycleCoverage,
    TerminalLifecycle,
    TerminalRequirement,
    TerminalShareholderPayoff,
    EventStudyObservation,
    EventStudyRefusal,
    EventStudyBatch,
    RowContract,
    ParentArtifact,
    CodeFileBinding,
    SyntheticPartitionBinding,
    EvaluationWindow,
    SyntheticQcRunCandidate,
    GlobalInputPartitionDescriptor,
    SyntheticQcGlobalInputManifest,
    SyntheticGlobalInputPartitionPayload,
    SyntheticQcGlobalInputBundle,
)
_PINNED_DEPENDENCY_GRAPH_RECORD_TYPES = _DEPENDENCY_GRAPH_RECORD_TYPES
_DEPENDENCY_VALUE_ROOTS = tuple(
    (
        _PINNED_REVIEWED_SESSION_AXIS,
        _PINNED_REVIEWED_SESSION_INDEX,
        *(
            value
            for dependency_globals in _RUNTIME_DEPENDENCY_GLOBALS
            for name, value in dependency_globals.items()
            if not name.startswith("__")
            and (
                type(value) in _PINNED_DEPENDENCY_GRAPH_CONTAINER_TYPES
                or type(value) in _PINNED_DEPENDENCY_GRAPH_RECORD_TYPES
            )
        ),
    )
)
_PINNED_DEPENDENCY_VALUE_ROOTS = _DEPENDENCY_VALUE_ROOTS
_DEPENDENCY_VALUE_AUTHORITY = _capture_dependency_value_authority(
    _DEPENDENCY_VALUE_ROOTS
)
_PINNED_DEPENDENCY_VALUE_AUTHORITY = _DEPENDENCY_VALUE_AUTHORITY


_DEPENDENCY_GLOBAL_BINDINGS = tuple(
    (
        dependency_globals,
        tuple(
            item
            for item in dependency_globals.items()
            if not (
                type(item[0]) is str
                and item[0] == "__warningregistry__"
            )
        ),
    )
    for dependency_globals in _RUNTIME_DEPENDENCY_GLOBALS
)
_PINNED_DEPENDENCY_GLOBAL_BINDINGS = _DEPENDENCY_GLOBAL_BINDINGS

_BUILTIN_GLOBALS = __builtins__
if type(_BUILTIN_GLOBALS) is not dict:
    raise RuntimeError("expected exact builtins dictionary")
_PINNED_BUILTIN_GLOBALS = _BUILTIN_GLOBALS
_BUILTIN_GLOBAL_ENTRIES = tuple(
    _PINNED_DICT_ITEMS(_BUILTIN_GLOBALS)
)
_PINNED_BUILTIN_GLOBAL_ENTRIES = _BUILTIN_GLOBAL_ENTRIES
_LOCAL_MODULE_GLOBALS = globals()
_PINNED_LOCAL_MODULE_GLOBALS = _LOCAL_MODULE_GLOBALS
_PINNED_CODE_TYPE = type((lambda: None).__code__)
_builtin_resolution_bindings: list[tuple[dict, str, object]] = []
_seen_builtin_resolutions: set[tuple[int, int]] = set()
for _implementation, _ in _FUNCTION_TOPOLOGIES:
    _pending_codes = [_implementation.__code__]
    while _pending_codes:
        _code = _pending_codes.pop()
        for _name in _code.co_names:
            _resolution_identity = (id(_implementation.__globals__), id(_name))
            if (
                _resolution_identity not in _seen_builtin_resolutions
                and _name not in _implementation.__globals__
                and _name in _PINNED_BUILTIN_GLOBALS
            ):
                _seen_builtin_resolutions.add(_resolution_identity)
                _builtin_resolution_bindings.append(
                    (
                        _implementation.__globals__,
                        _name,
                        _PINNED_BUILTIN_GLOBALS[_name],
                    )
                )
        _pending_codes.extend(
            value
            for value in _code.co_consts
            if type(value) is _PINNED_CODE_TYPE
        )
_BUILTIN_RESOLUTION_BINDINGS = tuple(_builtin_resolution_bindings)
_PINNED_BUILTIN_RESOLUTION_BINDINGS = _BUILTIN_RESOLUTION_BINDINGS
del _builtin_resolution_bindings
del _code
del _implementation
del _name
del _pending_codes
del _resolution_identity
del _seen_builtin_resolutions
del _capture_class_topology
del _capture_plain_class_topology
del _capture_function_state
