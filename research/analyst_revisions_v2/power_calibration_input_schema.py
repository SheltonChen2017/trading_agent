"""Outcome-free ARV2-4D-B1 calibration-input manifest schema.

This module freezes and authenticates only the metadata contract for a future
power-calibration input manifest.  It can validate canonical synthetic fixture
bytes in memory.  It cannot load a production manifest, open calibration
inputs, inspect outcomes, compute a calibration, issue a receipt, use
QuantConnect, deploy, or trade.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import threading
import weakref
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .power_calibration_protocol import (
    CALIBRATION_AXIS_SHA256,
    CALIBRATION_END_EXCLUSIVE,
    CALIBRATION_FOLD_HASH,
    CALIBRATION_FOLD_ID,
    CALIBRATION_LAST_OUTCOME_SESSION,
    CALIBRATION_LAST_SESSION,
    CALIBRATION_SESSION_COUNT,
    CALIBRATION_START,
    EVALUATION_ID,
    FIRST_TEST_SESSION,
    PowerCalibrationProtocol,
    PowerCalibrationProtocolError,
    require_loaded_power_calibration_protocol,
)


class PowerCalibrationInputSchemaError(ValueError):
    """The B1 schema, its parent, or a synthetic fixture is invalid."""


SCHEMA_CONTRACT_SCHEMA = (
    "arv2-stock-power-calibration-input-manifest-schema-structural-v1"
)
SCHEMA_CONTRACT_STATUS = (
    "owner_authorized_schema_only_frozen_outcome_free_pending_independent_review"
)
SCHEMA_CONTRACT_AUTHORITY = (
    "schema_and_synthetic_fixture_validation_only_no_production_manifest_"
    "input_outcome_calibration_receipt_qc_or_deployment_authority"
)
SCHEMA_CONTRACT_ID_PREFIX = "arv2-stock-power-calibration-input-schema-"
SCHEMA_CONTRACT_ARTIFACT_SHA256 = (
    "e642d06531b6ca024c3ee438ee88a113eef1483f2f6fca9d0e120afcfc5ed2f1"
)

MANIFEST_SCHEMA = "arv2-stock-power-calibration-input-manifest-v1"
SYNTHETIC_MODE = "synthetic_fixture"
PRODUCTION_MODE = "production_nuisance_calibration_input"
MANIFEST_ID_PREFIX = "arv2-power-calibration-input-manifest-"
SYNTHETIC_STATUS = "synthetic_fixture_only_not_production"
SYNTHETIC_AUTHORITY = "synthetic_metadata_shape_only_no_input_or_outcome_authority"

POWER_PROTOCOL_ID = "arv2-stock-power-calibration-protocol-0ba6b7d745783796"
POWER_PROTOCOL_HASH = (
    "0ba6b7d7457837967b5b8b7966cc22c2ddd00f4dbf4a7269b9aaa562baac757f"
)
POWER_PROTOCOL_ARTIFACT_SHA256 = (
    "ff16117a258a1864438d11178a2b31af1b04a3f8b27d1f39c9c33552627f4a13"
)
STRATEGY_PDF_SHA256 = (
    "eae7b9954aaf94212108505c52e31a558facd744967fd2526040d5147c616193"
)

INPUT_ROLES = ("date_level_beta_series", "component_count_census")
LINEAGE_ROLES = ("source_artifact", "transformation", *INPUT_ROLES)
INPUT_SCHEMAS = MappingProxyType(
    {
        "date_level_beta_series": "arv2-power-calibration-date-beta-input-v1",
        "component_count_census": (
            "arv2-power-calibration-component-count-input-v1"
        ),
    }
)
SESSION_KEY_FIELD = "decision_session"
SESSION_KEY_FORMAT = "YYYY-MM-DD"
EXCHANGE = "XNYS"
SYNTHETIC_RIGHTS_SCHEMA = "synthetic-rights-receipt-v1"
SYNTHETIC_PROCESSING_SCOPE = "synthetic_fixture_no_legal_or_access_claim"
EVIDENCE_CAPTURE_NOT_BEFORE_UTC = "2020-01-31T00:00:00.000000Z"

EXTERNAL_BINDINGS = MappingProxyType(
    {
        "independent_review_commit": None,
        "counter_review_commit": None,
        "production_manifest_id": None,
        "production_manifest_artifact_sha256": None,
        "data_entitlement_audit_id": None,
        "source_rights_receipt_id": None,
        "owner_calibration_input_access_authority_id": None,
        "owner_nuisance_calibration_authority_id": None,
        "numeric_power_receipt_sha256": None,
        "stock_successor_v3_sha256": None,
        "outcome_artifact_sha256": None,
        "qc_project_id": None,
        "qc_run_id": None,
        "evaluation_receipt_id": None,
    }
)
CAPABILITIES = MappingProxyType(
    {
        "production_manifest_acceptance": False,
        "calibration_input_access": False,
        "source_access": False,
        "outcome_access": False,
        "nuisance_calibration_compute": False,
        "authoritative_power_receipt": False,
        "power_plan_binding": False,
        "qc_upload": False,
        "qc_compile": False,
        "qc_launch": False,
        "result_disposition": False,
        "paper_deployment": False,
        "funded_deployment": False,
        "orders": False,
    }
)
MANIFEST_EXTERNAL_AUTHORITIES = MappingProxyType(
    {
        "production_registry_entry_id": None,
        "data_entitlement_audit_id": None,
        "source_rights_authority_id": None,
        "owner_calibration_input_access_authority_id": None,
        "owner_nuisance_calibration_authority_id": None,
        "numeric_power_receipt_sha256": None,
        "stock_successor_v3_sha256": None,
        "outcome_artifact_sha256": None,
        "qc_project_id": None,
        "qc_run_id": None,
        "evaluation_receipt_id": None,
    }
)

_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,191}\Z")
_UTC_INSTANT = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z"
)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise PowerCalibrationInputSchemaError("noncanonical JSON value") from exc


def _render(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise PowerCalibrationInputSchemaError("noncanonical JSON value") from exc


def _binding(
    *, artifact_id: str, content_sha256: str, artifact_sha256: str
) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "content_sha256": content_sha256,
        "artifact_sha256": artifact_sha256,
    }


def _lineage_nodes() -> list[dict[str, object]]:
    return [
        {"node": "strategy_pdf", "parents": []},
        {"node": "qc_base", "parents": ["strategy_pdf"]},
        {"node": "qc_plan", "parents": ["strategy_pdf", "qc_base"]},
        {"node": "stock_v1", "parents": ["strategy_pdf", "qc_plan"]},
        {
            "node": "fold_manifest",
            "parents": ["strategy_pdf", "qc_plan", "stock_v1"],
        },
        {"node": "global_map", "parents": ["strategy_pdf"]},
        {
            "node": "matched_contract",
            "parents": [
                "strategy_pdf",
                "stock_v1",
                "fold_manifest",
                "global_map",
            ],
        },
        {
            "node": "stock_v2",
            "parents": [
                "strategy_pdf",
                "qc_plan",
                "stock_v1",
                "fold_manifest",
                "global_map",
                "matched_contract",
            ],
        },
        {
            "node": "power_protocol",
            "parents": [
                "strategy_pdf",
                "qc_plan",
                "stock_v1",
                "fold_manifest",
                "global_map",
                "matched_contract",
                "stock_v2",
            ],
        },
        {
            "node": "calibration_input_manifest_schema",
            "parents": ["power_protocol"],
        },
    ]


MANIFEST_ROOT_FIELDS = (
    "schema",
    "manifest_mode",
    "status",
    "authority",
    "manifest_id",
    "manifest_hash",
    "schema_contract_binding",
    "power_protocol_binding",
    "evaluation_id",
    "calibration_fold",
    "evidence_epoch_binding",
    "producing_lineage",
    "complete_session_axis",
    "input_artifacts",
    "rights_bindings",
    "manifest_counts",
    "external_authorities",
    "capabilities",
)
BINDING_FIELDS = ("artifact_id", "content_sha256", "artifact_sha256")
CALIBRATION_FOLD_FIELDS = (
    "fold_id",
    "structural_fold_sha256",
    "horizon_sessions",
    "validation_start_inclusive",
    "validation_end_exclusive",
    "last_included_decision_session",
    "last_included_h20_outcome_session",
    "first_test_session",
)
SESSION_AXIS_FIELDS = (
    "exchange",
    "key_field",
    "key_format",
    "ordered_session_keys",
    "session_count",
    "session_axis_sha256",
    "first_session",
    "last_session",
)
MANIFEST_COUNT_FIELDS = (
    "input_artifact_count",
    "rights_binding_count",
    "lineage_node_count",
    "session_key_count",
)
EVIDENCE_EPOCH_FIELDS = (
    "evidence_epoch_id",
    "artifact_id",
    "semantic_sha256",
    "artifact_sha256",
    "capture_instant_utc",
    "calibration_information_cutoff_session",
    "first_excluded_session",
    "post_cutoff_corrections_included",
)
BETA_INPUT_FIELDS = (
    "role",
    "artifact_id",
    "artifact_schema",
    "content_sha256",
    "artifact_sha256",
    "byte_count",
    "record_count",
    "session_key_field",
    "session_axis_sha256",
    "session_state_inventory",
    "valid_beta_date_count",
    "missing_beta_date_count",
    "refused_beta_date_count",
    "state_census_sha256",
    "rights_binding_ids",
    "lineage_node_id",
)
COMPONENT_INPUT_FIELDS = (
    "role",
    "artifact_id",
    "artifact_schema",
    "content_sha256",
    "artifact_sha256",
    "byte_count",
    "record_count",
    "session_key_field",
    "session_axis_sha256",
    "session_count_inventory",
    "component_count_census_sha256",
    "component_count_census_session_count",
    "missing_session_count",
    "rights_binding_ids",
    "lineage_node_id",
)
RIGHTS_FIELDS = (
    "binding_id",
    "receipt_id",
    "receipt_schema",
    "receipt_content_sha256",
    "receipt_artifact_sha256",
    "data_entitlement_audit_id",
    "processing_scope_id",
    "applies_to_input_roles",
)
LINEAGE_FIELDS = (
    "producing_commit",
    "producing_tree",
    "producer_code_sha256",
    "build_recipe_id",
    "build_recipe_sha256",
    "config_sha256",
    "ordered_nodes",
    "lineage_sha256",
)
LINEAGE_NODE_FIELDS = (
    "node_id",
    "role",
    "artifact_id",
    "schema_id",
    "content_sha256",
    "artifact_sha256",
    "evidence_epoch_id",
    "parent_node_ids",
    "rights_binding_ids",
)


def _schema_document() -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": SCHEMA_CONTRACT_SCHEMA,
        "status": SCHEMA_CONTRACT_STATUS,
        "authority": SCHEMA_CONTRACT_AUTHORITY,
        "schema_contract_id": None,
        "schema_contract_hash": None,
        "strategy_pdf_sha256": STRATEGY_PDF_SHA256,
        "evaluation_id": EVALUATION_ID,
        "bound_parent": _binding(
            artifact_id=POWER_PROTOCOL_ID,
            content_sha256=POWER_PROTOCOL_HASH,
            artifact_sha256=POWER_PROTOCOL_ARTIFACT_SHA256,
        ),
        "manifest_identity_contract": {
            "manifest_schema": MANIFEST_SCHEMA,
            "manifest_id_prefix": MANIFEST_ID_PREFIX,
            "semantic_hash": (
                "SHA256_canonical_compact_UTF8_after_manifest_id_and_"
                "manifest_hash_are_set_to_null"
            ),
            "manifest_id": "prefix_plus_first_16_lower_hex_of_semantic_hash",
            "artifact_sha256": "SHA256_of_exact_canonical_pretty_UTF8_bytes",
            "calibration_input_manifest_sha256_means": "artifact_sha256",
        },
        "manifest_field_contract": {
            "required_exact_root_fields": list(MANIFEST_ROOT_FIELDS),
            "required_exact_binding_fields": list(BINDING_FIELDS),
            "required_exact_calibration_fold_fields": list(
                CALIBRATION_FOLD_FIELDS
            ),
            "required_exact_evidence_epoch_fields": list(EVIDENCE_EPOCH_FIELDS),
            "unknown_or_missing_field": "REFUSED",
            "canonical_encoding": (
                "sorted_keys_indent_2_ensure_ascii_false_allow_nan_false_LF_"
                "terminated_strict_UTF8_no_BOM_no_duplicate_keys_no_floats"
            ),
            "recognized_modes": [SYNTHETIC_MODE, PRODUCTION_MODE],
            "implemented_modes": [SYNTHETIC_MODE],
            "production_mode_current_disposition": (
                "REFUSED_until_separate_input_access_rights_and_processing_"
                "authority_and_independent_review"
            ),
        },
        "calibration_boundary_contract": {
            "fold_id": CALIBRATION_FOLD_ID,
            "structural_fold_sha256": CALIBRATION_FOLD_HASH,
            "horizon_sessions": 20,
            "validation_start_inclusive": CALIBRATION_START,
            "validation_end_exclusive": CALIBRATION_END_EXCLUSIVE,
            "last_included_decision_session": CALIBRATION_LAST_SESSION,
            "last_included_h20_outcome_session": CALIBRATION_LAST_OUTCOME_SESSION,
            "first_test_session": FIRST_TEST_SESSION,
        },
        "session_axis_contract": {
            "required_exact_fields": list(SESSION_AXIS_FIELDS),
            "exchange": EXCHANGE,
            "key_field": SESSION_KEY_FIELD,
            "key_format": SESSION_KEY_FORMAT,
            "session_count": CALIBRATION_SESSION_COUNT,
            "session_axis_sha256": CALIBRATION_AXIS_SHA256,
            "first_session": CALIBRATION_START,
            "last_session": CALIBRATION_LAST_SESSION,
            "manifest_must_carry_all_ordered_session_keys": True,
            "missing_duplicate_extra_or_reordered_key": "REFUSED",
        },
        "input_artifact_contracts": {
            "ordered_roles": list(INPUT_ROLES),
            "date_level_beta_series": {
                "artifact_schema": INPUT_SCHEMAS["date_level_beta_series"],
                "required_exact_fields": list(BETA_INPUT_FIELDS),
                "session_states": ["valid", "missing", "refused"],
                "state_counts_must_sum_to_session_count": True,
                "date_level_beta_values_in_manifest": "FORBIDDEN",
                "state_census_hash_recipe": (
                    "SHA256_canonical_compact_UTF8_session_state_inventory"
                ),
            },
            "component_count_census": {
                "artifact_schema": INPUT_SCHEMAS["component_count_census"],
                "required_exact_fields": list(COMPONENT_INPUT_FIELDS),
                "count_type": "exact_nonnegative_integer_bool_forbidden",
                "all_axis_sessions_required": True,
                "per_session_counts_in_manifest": "PERMITTED_metadata_only",
                "census_hash_recipe": (
                    "SHA256_canonical_compact_UTF8_session_count_inventory"
                ),
            },
        },
        "rights_contract": {
            "required_exact_fields_per_binding": list(RIGHTS_FIELDS),
            "every_input_role_must_be_covered": True,
            "copied_manifest_claim_grants_rights": False,
            "future_production_requirement": (
                "authenticate_exact_receipt_bytes_data_entitlement_and_"
                "independent_approval_before_any_input_read"
            ),
            "required_purpose": (
                "nuisance_only_power_calibration_and_closed_aggregate_receipt"
            ),
            "qc_transfer_redistribution_or_additional_storage": (
                "never_inferred_requires_separate_exact_rights"
            ),
        },
        "processing_contract": {
            "manifest_content_allowlist": (
                "identities_hashes_rights_processing_lineage_exact_session_"
                "keys_and_counts_only"
            ),
            "manifest_validation_reads_input_artifacts": False,
            "manifest_validation_computes_calibration": False,
            "synthetic_fixture_result_is_authoritative": False,
        },
        "lineage_contract": {
            "required_exact_fields": list(LINEAGE_FIELDS),
            "required_exact_node_fields": list(LINEAGE_NODE_FIELDS),
            "allowed_node_roles": list(LINEAGE_ROLES),
            "graph": "ordered_child_to_parent_DAG_parents_must_precede_child",
            "duplicate_unknown_parent_cycle_or_orphan": "REFUSED",
            "all_nodes_share_manifest_evidence_epoch": True,
            "at_least_one_distinct_source_artifact_root": True,
            "every_root_role": "source_artifact",
            "every_source_root_has_nonempty_valid_rights_bindings": True,
            "every_terminal_ancestry_source_root_has_rights_for_terminal_role": True,
            "every_input_terminal_has_nonempty_ancestry": True,
            "every_nonroot_nonterminal_role": "transformation",
            "terminal_nodes_must_exactly_bind_the_two_input_artifacts": True,
            "lineage_hash_recipe": "SHA256_canonical_compact_UTF8_ordered_nodes",
        },
        "count_contract": {
            "required_manifest_count_fields": list(MANIFEST_COUNT_FIELDS),
            "input_artifact_count": 2,
            "session_key_count": CALIBRATION_SESSION_COUNT,
            "all_counts": "exact_nonnegative_integer_bool_forbidden",
            "declared_and_observed_counts_must_match": True,
        },
        "evidence_epoch_contract": {
            "required_exact_fields": list(EVIDENCE_EPOCH_FIELDS),
            "identifier_scope": "synthetic_prefixed_shape_only",
            "hash_scope": "syntactic_only_no_artifact_read_or_authentication",
            "capture_instant_format": "YYYY-MM-DDTHH:MM:SS.ffffffZ_strict_UTC",
            "capture_instant_not_before_utc": EVIDENCE_CAPTURE_NOT_BEFORE_UTC,
            "calibration_information_cutoff_session": (
                CALIBRATION_LAST_OUTCOME_SESSION
            ),
            "first_excluded_session": FIRST_TEST_SESSION,
            "post_cutoff_corrections_included": False,
        },
        "forbidden_content": {
            "manifest_may_not_contain": [
                "provider_rows_or_payloads",
                "security_or_date_returns",
                "date_level_beta_values",
                "beta_mean_or_sign",
                "HAC_intermediate_products_or_autocovariances",
                "information_coefficients_or_p_values",
                "PnL_strategy_performance_or_gate_results",
                "file_paths_URLs_queries_credentials_or_secrets",
            ],
            "closed_root_and_nested_key_sets_enforce_the_allowlist": True,
        },
        "synthetic_fixture_contract": {
            "supported": True,
            "payload_source": "caller_supplied_canonical_bytes_in_memory_only",
            "synthetic_prefixed_identifier_fields": [
                "evidence_epoch_binding.evidence_epoch_id",
                "evidence_epoch_binding.artifact_id",
                "input_artifacts[].artifact_id",
                "rights_bindings[].binding_id",
                "rights_bindings[].receipt_id",
                "rights_bindings[].data_entitlement_audit_id",
                "producing_lineage.build_recipe_id",
                "producing_lineage.ordered_nodes[].node_id",
                "producing_lineage.ordered_nodes[].artifact_id",
            ],
            "rights_scope": SYNTHETIC_PROCESSING_SCOPE,
            "external_authorities": dict(MANIFEST_EXTERNAL_AUTHORITIES),
            "capabilities": dict(CAPABILITIES),
            "production_promotion": "PROHIBITED",
        },
        "future_production_gate": {
            "production_manifest_loader_implemented": False,
            "input_artifact_loader_implemented": False,
            "numeric_receipt_implemented": False,
            "separate_owner_input_access_authority_required": True,
            "separate_authenticated_rights_required": True,
            "separate_nuisance_computation_authority_required": True,
            (
                "first_outcome_bearing_manifest_or_receipt_must_add_"
                "independently_reviewed_four_family_overlay"
            ): True,
            "this_schema_does_not_bind_the_four_family_overlay": True,
        },
        "acyclic_lineage": {
            "edge_direction": "child_to_parent",
            "ordered_nodes": _lineage_nodes(),
            "schema_is_leaf": True,
            "schema_direct_parent": "power_protocol",
            "reviewed_ARV2_4D_A_nodes_and_edges_unchanged": True,
            "four_family_overlay_relationship": (
                "independent_parallel_leaf_not_a_B1_parent"
            ),
        },
        "external_bindings": dict(EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
    }
    return _content_identity(raw, "schema_contract_id", "schema_contract_hash")


def _content_identity(
    raw: Mapping[str, Any], id_field: str, hash_field: str
) -> dict[str, Any]:
    value = dict(raw)
    value[id_field] = None
    value[hash_field] = None
    digest = hashlib.sha256(_canonical(value)).hexdigest()
    value[hash_field] = digest
    prefix = (
        SCHEMA_CONTRACT_ID_PREFIX
        if id_field == "schema_contract_id"
        else MANIFEST_ID_PREFIX
    )
    value[id_field] = f"{prefix}{digest[:16]}"
    return value


def _reject_float(value: str) -> None:
    raise PowerCalibrationInputSchemaError(
        f"binary floating-point is forbidden: {value}"
    )


def _reject_constant(value: str) -> None:
    raise PowerCalibrationInputSchemaError(f"non-finite JSON is forbidden: {value}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PowerCalibrationInputSchemaError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _is_link_like(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(
            getattr(path, "is_junction", lambda: False)()
        )
    except OSError:
        return True


def _read_stable_regular(path: Path, name: str) -> tuple[Path, bytes]:
    candidate = Path(path)
    absolute = candidate.absolute()
    if any(_is_link_like(item) for item in (absolute, *absolute.parents)):
        raise PowerCalibrationInputSchemaError(f"{name} must not traverse a link")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise PowerCalibrationInputSchemaError(f"{name} is unavailable") from exc
    if _is_link_like(resolved) or not resolved.is_file():
        raise PowerCalibrationInputSchemaError(f"{name} must be a regular file")
    try:
        before = resolved.stat()
        first = resolved.read_bytes()
        second = resolved.read_bytes()
        after = resolved.stat()
    except OSError as exc:
        raise PowerCalibrationInputSchemaError(f"{name} is unreadable") from exc
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity or first != second:
        raise PowerCalibrationInputSchemaError(f"{name} changed while being read")
    return resolved, first


def _revalidate(path: Path, payload: bytes, name: str) -> None:
    absolute = path.absolute()
    if (
        any(_is_link_like(item) for item in (absolute, *absolute.parents))
        or not path.is_file()
    ):
        raise PowerCalibrationInputSchemaError(f"{name} changed or disappeared")
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise PowerCalibrationInputSchemaError(
            f"{name} changed or disappeared"
        ) from exc
    if current != payload:
        raise PowerCalibrationInputSchemaError(f"{name} changed after authentication")


def _parse_artifact(payload: bytes, name: str) -> dict[str, Any]:
    if type(payload) is not bytes:
        raise PowerCalibrationInputSchemaError(f"{name} must be bytes")
    if payload.startswith(
        (
            b"\xef\xbb\xbf",
            b"\xff\xfe",
            b"\xfe\xff",
            b"\xff\xfe\x00\x00",
            b"\x00\x00\xfe\xff",
        )
    ):
        raise PowerCalibrationInputSchemaError(f"{name} must not contain a BOM")
    try:
        raw = json.loads(
            payload.decode("utf-8", errors="strict"),
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object,
        )
    except PowerCalibrationInputSchemaError:
        raise
    except UnicodeDecodeError as exc:
        raise PowerCalibrationInputSchemaError(f"{name} is not strict UTF-8") from exc
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise PowerCalibrationInputSchemaError(f"{name} is invalid JSON") from exc
    if type(raw) is not dict:
        raise PowerCalibrationInputSchemaError(f"{name} must be a JSON object")
    if _render(raw) != payload:
        raise PowerCalibrationInputSchemaError(
            f"{name} bytes are not canonical sorted UTF-8 JSON"
        )
    return raw


def _require_exact(actual: object, expected: object, name: str) -> None:
    if type(actual) is not type(expected) or _canonical(actual) != _canonical(expected):
        raise PowerCalibrationInputSchemaError(
            f"{name} changed from the frozen contract"
        )


def _require_keys(value: object, fields: Iterable[str], name: str) -> dict[str, Any]:
    expected = set(fields)
    if type(value) is not dict or set(value) != expected:
        raise PowerCalibrationInputSchemaError(f"{name} fields are not exact")
    return value


def _require_identifier(value: object, name: str, *, synthetic: bool = False) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise PowerCalibrationInputSchemaError(f"{name} is not a valid identifier")
    if synthetic and not value.startswith("synthetic-"):
        raise PowerCalibrationInputSchemaError(f"{name} must be synthetic-prefixed")
    return value


def _require_sha256(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise PowerCalibrationInputSchemaError(f"{name} is not a SHA-256")
    return value


def _require_git_object(value: object, name: str) -> str:
    if type(value) is not str or _HEX_40.fullmatch(value) is None:
        raise PowerCalibrationInputSchemaError(f"{name} is not a Git object")
    return value


def _require_int(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise PowerCalibrationInputSchemaError(f"{name} is not a valid integer")
    return value


def _require_capture_instant(value: object, name: str) -> str:
    if type(value) is not str or _UTC_INSTANT.fullmatch(value) is None:
        raise PowerCalibrationInputSchemaError(
            f"{name} must use strict UTC YYYY-MM-DDTHH:MM:SS.ffffffZ form"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        not_before = datetime.fromisoformat(
            EVIDENCE_CAPTURE_NOT_BEFORE_UTC[:-1] + "+00:00"
        )
    except ValueError as exc:
        raise PowerCalibrationInputSchemaError(f"{name} is not a real instant") from exc
    canonical = (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    if canonical != value or parsed < not_before:
        raise PowerCalibrationInputSchemaError(
            f"{name} is noncanonical or predates the calibration cutoff"
        )
    return value


def _validate_evidence_epoch_binding(raw: object) -> str:
    value = _require_keys(raw, EVIDENCE_EPOCH_FIELDS, "evidence epoch binding")
    evidence_epoch_id = _require_identifier(
        value["evidence_epoch_id"], "evidence epoch ID", synthetic=True
    )
    _require_identifier(
        value["artifact_id"], "evidence epoch artifact ID", synthetic=True
    )
    _require_sha256(value["semantic_sha256"], "evidence epoch semantic hash")
    _require_sha256(value["artifact_sha256"], "evidence epoch artifact hash")
    _require_capture_instant(
        value["capture_instant_utc"], "evidence epoch capture instant"
    )
    if (
        value["calibration_information_cutoff_session"]
        != CALIBRATION_LAST_OUTCOME_SESSION
        or value["first_excluded_session"] != FIRST_TEST_SESSION
        or value["post_cutoff_corrections_included"] is not False
    ):
        raise PowerCalibrationInputSchemaError(
            "evidence epoch cutoff or correction policy changed"
        )
    return evidence_epoch_id


def _validate_identity(
    raw: Mapping[str, Any], id_field: str, hash_field: str, prefix: str, name: str
) -> None:
    declared = _require_sha256(raw.get(hash_field), f"{name} content hash")
    payload = dict(raw)
    payload[id_field] = None
    payload[hash_field] = None
    actual = hashlib.sha256(_canonical(payload)).hexdigest()
    if declared != actual or raw.get(id_field) != f"{prefix}{actual[:16]}":
        raise PowerCalibrationInputSchemaError(f"{name} identity is not content-derived")


def _lineage_graph(raw: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    try:
        nodes = raw["acyclic_lineage"]["ordered_nodes"]
    except (KeyError, TypeError) as exc:
        raise PowerCalibrationInputSchemaError("schema lineage is malformed") from exc
    if type(nodes) is not list:
        raise PowerCalibrationInputSchemaError("schema lineage is malformed")
    graph: dict[str, tuple[str, ...]] = {}
    for item in nodes:
        item = _require_keys(item, ("node", "parents"), "schema lineage node")
        node = item["node"]
        parents = item["parents"]
        if (
            type(node) is not str
            or not node
            or type(parents) is not list
            or any(type(parent) is not str or not parent for parent in parents)
            or len(parents) != len(set(parents))
            or node in graph
            or any(parent not in graph for parent in parents)
        ):
            raise PowerCalibrationInputSchemaError("schema lineage is malformed")
        graph[node] = tuple(parents)
    expected = {
        item["node"]: tuple(item["parents"]) for item in _lineage_nodes()
    }
    if graph != expected:
        raise PowerCalibrationInputSchemaError("schema lineage changed")
    _assert_acyclic(graph, "schema lineage")
    return graph


def _assert_acyclic(graph: Mapping[str, Iterable[str]], name: str) -> None:
    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise PowerCalibrationInputSchemaError(f"{name} contains a cycle")
        if node in complete:
            return
        visiting.add(node)
        for parent in graph[node]:
            visit(parent)
        visiting.remove(node)
        complete.add(node)

    for node in graph:
        visit(node)


def _freeze(value: Any) -> Any:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


@dataclasses.dataclass(frozen=True, init=False)
class PowerCalibrationInputSchema:
    schema_contract_id: str
    schema_contract_hash: str
    evaluation_id: str
    calibration_session_axis: tuple[str, ...]
    definition: Mapping[str, Any]
    lineage_graph: Mapping[str, tuple[str, ...]]
    capabilities: Mapping[str, bool]
    _authority: object = dataclasses.field(repr=False, compare=False)

    @property
    def production_manifest_acceptance_available(self) -> bool:
        return False

    @property
    def calibration_input_access_available(self) -> bool:
        return False

    @property
    def source_access_available(self) -> bool:
        return False

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def nuisance_calibration_available(self) -> bool:
        return False

    @property
    def authoritative_receipt_available(self) -> bool:
        return False

    @property
    def qc_action_available(self) -> bool:
        return False

    @property
    def deployment_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False


@dataclasses.dataclass(frozen=True, init=False)
class SyntheticCalibrationInputManifestSummary:
    manifest_id: str
    manifest_hash: str
    evidence_epoch_id: str
    session_count: int
    input_roles: tuple[str, ...]
    input_artifact_count: int
    rights_binding_count: int
    lineage_node_count: int
    definition: Mapping[str, Any]

    def __init__(self) -> None:
        raise TypeError("synthetic summaries must be produced by fixture validation")

    @property
    def synthetic_only(self) -> bool:
        return True

    @property
    def production_authorized(self) -> bool:
        return False

    @property
    def input_access_available(self) -> bool:
        return False

    @property
    def calibration_available(self) -> bool:
        return False

    @property
    def authoritative_receipt_available(self) -> bool:
        return False


_LOADED_POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITY = object()
_POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[PowerCalibrationInputSchema],
        Path,
        bytes,
        PowerCalibrationProtocol,
        tuple[object, ...],
    ],
] = {}
_POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITIES_LOCK = threading.RLock()


def _fingerprint_value(value: object) -> object:
    if type(value) is MappingProxyType:
        pairs = []
        for key, item in value.items():
            if type(key) is not str:
                raise PowerCalibrationInputSchemaError("schema has a non-string key")
            pairs.append((key, _fingerprint_value(item)))
        return ("mapping", tuple(sorted(pairs)))
    if type(value) is tuple:
        return ("tuple", tuple(_fingerprint_value(item) for item in value))
    if type(value) is str:
        return ("str", value)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if value is None:
        return ("none", None)
    raise PowerCalibrationInputSchemaError("schema has noncanonical authority state")


def _schema_fingerprint(schema: PowerCalibrationInputSchema) -> tuple[object, ...]:
    if (
        type(schema.schema_contract_id) is not str
        or type(schema.schema_contract_hash) is not str
        or type(schema.evaluation_id) is not str
        or type(schema.calibration_session_axis) is not tuple
        or any(type(item) is not str for item in schema.calibration_session_axis)
    ):
        raise PowerCalibrationInputSchemaError("schema identity fields changed type")
    return (
        schema.schema_contract_id,
        schema.schema_contract_hash,
        schema.evaluation_id,
        schema.calibration_session_axis,
        _fingerprint_value(schema.definition),
        _fingerprint_value(schema.lineage_graph),
        _fingerprint_value(schema.capabilities),
    )


def _forget_authority(
    identity: int, reference: weakref.ReferenceType[PowerCalibrationInputSchema]
) -> None:
    with _POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITIES_LOCK:
        current = _POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITIES.pop(identity, None)


def load_power_calibration_input_schema(
    schema_path: Path,
    *,
    power_protocol: PowerCalibrationProtocol,
) -> PowerCalibrationInputSchema:
    """Authenticate the B1 schema and its sole loaded ARV2-4D-A parent."""
    try:
        require_loaded_power_calibration_protocol(power_protocol)
    except PowerCalibrationProtocolError as exc:
        raise PowerCalibrationInputSchemaError(
            "ARV2-4D-A parent is not authenticated"
        ) from exc
    if (
        power_protocol.protocol_id != POWER_PROTOCOL_ID
        or power_protocol.protocol_hash != POWER_PROTOCOL_HASH
        or power_protocol.evaluation_id != EVALUATION_ID
        or len(power_protocol.calibration_session_axis) != CALIBRATION_SESSION_COUNT
        or hashlib.sha256(_canonical(power_protocol.calibration_session_axis)).hexdigest()
        != CALIBRATION_AXIS_SHA256
    ):
        raise PowerCalibrationInputSchemaError("ARV2-4D-A parent identity changed")

    resolved, payload = _read_stable_regular(schema_path, "calibration input schema")
    if hashlib.sha256(payload).hexdigest() != SCHEMA_CONTRACT_ARTIFACT_SHA256:
        raise PowerCalibrationInputSchemaError("calibration input schema bytes changed")
    raw = _parse_artifact(payload, "calibration input schema")
    _validate_identity(
        raw,
        "schema_contract_id",
        "schema_contract_hash",
        SCHEMA_CONTRACT_ID_PREFIX,
        "calibration input schema",
    )
    canonical_definition = _schema_document()
    _require_exact(raw, canonical_definition, "calibration input schema")
    graph = _lineage_graph(raw)
    _revalidate(resolved, payload, "calibration input schema")
    try:
        require_loaded_power_calibration_protocol(power_protocol)
    except PowerCalibrationProtocolError as exc:
        raise PowerCalibrationInputSchemaError(
            "ARV2-4D-A parent changed during authentication"
        ) from exc
    _revalidate(resolved, payload, "calibration input schema")

    value = object.__new__(PowerCalibrationInputSchema)
    for name, item in {
        "schema_contract_id": raw["schema_contract_id"],
        "schema_contract_hash": raw["schema_contract_hash"],
        "evaluation_id": raw["evaluation_id"],
        "calibration_session_axis": power_protocol.calibration_session_axis,
        "definition": _freeze(canonical_definition),
        "lineage_graph": _freeze(graph),
        "capabilities": _freeze(dict(CAPABILITIES)),
        "_authority": _LOADED_POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITY,
    }.items():
        object.__setattr__(value, name, item)
    fingerprint = _schema_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget_authority(key, ref))
    with _POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITIES_LOCK:
        _POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITIES[identity] = (
            reference,
            resolved,
            payload,
            power_protocol,
            fingerprint,
        )
    return value


def require_loaded_power_calibration_input_schema(
    schema: PowerCalibrationInputSchema,
) -> PowerCalibrationInputSchema:
    """Reauthenticate the schema object, bytes, and complete 4D-A parent."""
    if (
        type(schema) is not PowerCalibrationInputSchema
        or getattr(schema, "_authority", None)
        is not _LOADED_POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITY
    ):
        raise PowerCalibrationInputSchemaError(
            "calibration input schema is not loader-authenticated"
        )
    with _POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITIES_LOCK:
        authority = _POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITIES.get(id(schema))
    if authority is None or authority[0]() is not schema:
        raise PowerCalibrationInputSchemaError(
            "calibration input schema loader authority is absent"
        )
    if _schema_fingerprint(schema) != authority[4]:
        raise PowerCalibrationInputSchemaError(
            "calibration input schema changed after authentication"
        )
    _revalidate(authority[1], authority[2], "calibration input schema")
    try:
        require_loaded_power_calibration_protocol(authority[3])
    except PowerCalibrationProtocolError as exc:
        raise PowerCalibrationInputSchemaError(
            "ARV2-4D-A parent changed after authentication"
        ) from exc
    _revalidate(authority[1], authority[2], "calibration input schema")
    return schema


def _validate_rights(raw: object) -> tuple[dict[str, Any], ...]:
    if type(raw) is not list or not raw:
        raise PowerCalibrationInputSchemaError("rights bindings must be nonempty")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    covered: set[str] = set()
    for index, item in enumerate(raw):
        item = _require_keys(item, RIGHTS_FIELDS, f"rights binding {index}")
        binding_id = _require_identifier(
            item["binding_id"], f"rights binding {index} ID", synthetic=True
        )
        if binding_id in seen:
            raise PowerCalibrationInputSchemaError("rights binding IDs are duplicated")
        seen.add(binding_id)
        _require_identifier(
            item["receipt_id"], f"rights binding {index} receipt", synthetic=True
        )
        _require_identifier(
            item["data_entitlement_audit_id"],
            f"rights binding {index} entitlement audit",
            synthetic=True,
        )
        if item["receipt_schema"] != SYNTHETIC_RIGHTS_SCHEMA:
            raise PowerCalibrationInputSchemaError("synthetic rights schema changed")
        if item["processing_scope_id"] != SYNTHETIC_PROCESSING_SCOPE:
            raise PowerCalibrationInputSchemaError(
                "synthetic rights scope cannot make a legal claim"
            )
        _require_sha256(
            item["receipt_content_sha256"], f"rights binding {index} content hash"
        )
        _require_sha256(
            item["receipt_artifact_sha256"], f"rights binding {index} artifact hash"
        )
        roles = item["applies_to_input_roles"]
        if type(roles) is not list or not roles or any(
            type(role) is not str for role in roles
        ):
            raise PowerCalibrationInputSchemaError("rights role inventory is invalid")
        role_set = set(roles)
        if (
            tuple(roles) != tuple(role for role in INPUT_ROLES if role in role_set)
            or len(roles) != len(role_set)
        ):
            raise PowerCalibrationInputSchemaError("rights role inventory is invalid")
        covered.update(roles)
        result.append(item)
    if tuple(item["binding_id"] for item in result) != tuple(sorted(seen)):
        raise PowerCalibrationInputSchemaError("rights bindings must be ID-sorted")
    if covered != set(INPUT_ROLES):
        raise PowerCalibrationInputSchemaError("rights do not cover both input roles")
    return tuple(result)


def _validate_inputs(
    raw: object,
    sessions: tuple[str, ...],
    rights: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    if type(raw) is not list or len(raw) != len(INPUT_ROLES):
        raise PowerCalibrationInputSchemaError("input artifact inventory is not exact")
    rights_by_id = {item["binding_id"]: item for item in rights}
    result: list[dict[str, Any]] = []
    for index, (item, role) in enumerate(zip(raw, INPUT_ROLES, strict=True)):
        fields = BETA_INPUT_FIELDS if role == INPUT_ROLES[0] else COMPONENT_INPUT_FIELDS
        item = _require_keys(item, fields, f"input artifact {index}")
        if item["role"] != role or item["artifact_schema"] != INPUT_SCHEMAS[role]:
            raise PowerCalibrationInputSchemaError("input role or schema changed")
        _require_identifier(item["artifact_id"], f"{role} artifact ID", synthetic=True)
        _require_sha256(item["content_sha256"], f"{role} content hash")
        _require_sha256(item["artifact_sha256"], f"{role} artifact hash")
        _require_int(item["byte_count"], f"{role} byte count", minimum=1)
        if (
            _require_int(item["record_count"], f"{role} record count")
            != CALIBRATION_SESSION_COUNT
            or item["session_key_field"] != SESSION_KEY_FIELD
            or item["session_axis_sha256"] != CALIBRATION_AXIS_SHA256
        ):
            raise PowerCalibrationInputSchemaError(f"{role} session binding changed")
        binding_ids = item["rights_binding_ids"]
        if type(binding_ids) is not list or not binding_ids or any(
            type(binding_id) is not str for binding_id in binding_ids
        ):
            raise PowerCalibrationInputSchemaError(f"{role} rights binding is invalid")
        if (
            tuple(binding_ids) != tuple(sorted(set(binding_ids)))
            or any(
                binding_id not in rights_by_id
                or role not in rights_by_id[binding_id]["applies_to_input_roles"]
                for binding_id in binding_ids
            )
        ):
            raise PowerCalibrationInputSchemaError(f"{role} rights binding is invalid")
        _require_identifier(
            item["lineage_node_id"], f"{role} lineage node", synthetic=True
        )
        if role == "date_level_beta_series":
            inventory = item["session_state_inventory"]
            if type(inventory) is not list or len(inventory) != len(sessions):
                raise PowerCalibrationInputSchemaError("beta state inventory is incomplete")
            states: list[str] = []
            for position, (record, session) in enumerate(
                zip(inventory, sessions, strict=True)
            ):
                record = _require_keys(
                    record, ("session", "state"), f"beta state {position}"
                )
                state = record["state"]
                if (
                    record["session"] != session
                    or type(state) is not str
                    or state not in {"valid", "missing", "refused"}
                ):
                    raise PowerCalibrationInputSchemaError(
                        "beta state inventory changed from the exact axis"
                    )
                states.append(state)
            counts = {
                state: states.count(state) for state in ("valid", "missing", "refused")
            }
            if (
                _require_int(item["valid_beta_date_count"], "valid beta count")
                != counts["valid"]
                or _require_int(item["missing_beta_date_count"], "missing beta count")
                != counts["missing"]
                or _require_int(item["refused_beta_date_count"], "refused beta count")
                != counts["refused"]
                or sum(counts.values()) != CALIBRATION_SESSION_COUNT
                or _require_sha256(item["state_census_sha256"], "state census hash")
                != hashlib.sha256(_canonical(inventory)).hexdigest()
            ):
                raise PowerCalibrationInputSchemaError("beta state census changed")
        else:
            inventory = item["session_count_inventory"]
            if type(inventory) is not list or len(inventory) != len(sessions):
                raise PowerCalibrationInputSchemaError(
                    "component count inventory is incomplete"
                )
            for position, (record, session) in enumerate(
                zip(inventory, sessions, strict=True)
            ):
                record = _require_keys(
                    record,
                    ("session", "connected_component_count"),
                    f"component count {position}",
                )
                if record["session"] != session:
                    raise PowerCalibrationInputSchemaError(
                        "component count inventory changed from the exact axis"
                    )
                _require_int(
                    record["connected_component_count"],
                    f"component count {position}",
                )
            if (
                _require_sha256(
                    item["component_count_census_sha256"],
                    "component count census hash",
                )
                != hashlib.sha256(_canonical(inventory)).hexdigest()
                or _require_int(
                    item["component_count_census_session_count"],
                    "component count census session count",
                )
                != CALIBRATION_SESSION_COUNT
                or _require_int(item["missing_session_count"], "missing session count")
                != 0
            ):
                raise PowerCalibrationInputSchemaError(
                    "component count census changed"
                )
        result.append(item)
    if len({item["artifact_id"] for item in result}) != len(result):
        raise PowerCalibrationInputSchemaError("input artifact IDs are duplicated")
    used_rights = {
        binding_id for item in result for binding_id in item["rights_binding_ids"]
    }
    if used_rights != set(rights_by_id):
        raise PowerCalibrationInputSchemaError("rights bindings contain an orphan")
    return tuple(result)


def _validate_producing_lineage(
    raw: object,
    evidence_epoch_id: str,
    inputs: tuple[dict[str, Any], ...],
    rights: tuple[dict[str, Any], ...],
) -> int:
    value = _require_keys(raw, LINEAGE_FIELDS, "producing lineage")
    _require_git_object(value["producing_commit"], "producing commit")
    _require_git_object(value["producing_tree"], "producing tree")
    _require_sha256(value["producer_code_sha256"], "producer code hash")
    _require_identifier(value["build_recipe_id"], "build recipe", synthetic=True)
    _require_sha256(value["build_recipe_sha256"], "build recipe hash")
    _require_sha256(value["config_sha256"], "config hash")
    nodes = value["ordered_nodes"]
    if type(nodes) is not list or not nodes:
        raise PowerCalibrationInputSchemaError("lineage nodes must be nonempty")
    known_rights = {item["binding_id"] for item in rights}
    rights_roles = {
        item["binding_id"]: set(item["applies_to_input_roles"]) for item in rights
    }
    terminal_roles = {
        item["lineage_node_id"]: item["role"] for item in inputs
    }
    terminals = set(terminal_roles)
    if len(terminals) != len(inputs):
        raise PowerCalibrationInputSchemaError("input terminal lineage is invalid")
    graph: dict[str, tuple[str, ...]] = {}
    records: dict[str, dict[str, Any]] = {}
    artifact_ids: set[str] = set()
    source_roots: set[str] = set()
    for index, item in enumerate(nodes):
        item = _require_keys(item, LINEAGE_NODE_FIELDS, f"lineage node {index}")
        node_id = _require_identifier(
            item["node_id"], f"lineage node {index} ID", synthetic=True
        )
        if node_id in graph:
            raise PowerCalibrationInputSchemaError("lineage node IDs are duplicated")
        role = _require_identifier(item["role"], f"lineage node {index} role")
        if role not in LINEAGE_ROLES:
            raise PowerCalibrationInputSchemaError("lineage node role is not closed")
        artifact_id = _require_identifier(
            item["artifact_id"], f"lineage node {index} artifact", synthetic=True
        )
        if artifact_id in artifact_ids:
            raise PowerCalibrationInputSchemaError(
                "lineage artifact IDs are duplicated"
            )
        artifact_ids.add(artifact_id)
        _require_identifier(item["schema_id"], f"lineage node {index} schema")
        _require_sha256(item["content_sha256"], f"lineage node {index} content hash")
        _require_sha256(item["artifact_sha256"], f"lineage node {index} artifact hash")
        if item["evidence_epoch_id"] != evidence_epoch_id:
            raise PowerCalibrationInputSchemaError("lineage evidence epoch changed")
        parents = item["parent_node_ids"]
        rights_ids = item["rights_binding_ids"]
        if type(parents) is not list or any(
            type(parent) is not str for parent in parents
        ):
            raise PowerCalibrationInputSchemaError(
                "lineage parent or rights inventory is invalid"
            )
        if type(rights_ids) is not list or any(
            type(binding_id) is not str for binding_id in rights_ids
        ):
            raise PowerCalibrationInputSchemaError(
                "lineage parent or rights inventory is invalid"
            )
        if (
            tuple(parents) != tuple(dict.fromkeys(parents))
            or any(parent not in graph for parent in parents)
            or tuple(rights_ids) != tuple(sorted(set(rights_ids)))
            or any(binding_id not in known_rights for binding_id in rights_ids)
        ):
            raise PowerCalibrationInputSchemaError(
                "lineage parent or rights inventory is invalid"
            )
        if not parents:
            if role != "source_artifact" or node_id in terminals or not rights_ids:
                raise PowerCalibrationInputSchemaError(
                    "every lineage root must be a distinct rights-bound source artifact"
                )
            source_roots.add(node_id)
        elif node_id in terminals:
            if role != terminal_roles[node_id]:
                raise PowerCalibrationInputSchemaError(
                    "input terminal lineage role changed"
                )
        elif role != "transformation":
            raise PowerCalibrationInputSchemaError(
                "every nonroot nonterminal lineage node must be a transformation"
            )
        graph[node_id] = tuple(parents)
        records[node_id] = item
    _assert_acyclic(graph, "fixture lineage")
    if not source_roots:
        raise PowerCalibrationInputSchemaError(
            "fixture lineage requires a distinct source artifact root"
        )
    if any(node not in graph or not graph[node] for node in terminals):
        raise PowerCalibrationInputSchemaError("input terminal lineage is invalid")
    if any(terminal in parents for parents in graph.values() for terminal in terminals):
        raise PowerCalibrationInputSchemaError(
            "input terminal lineage nodes must not have children"
        )
    for item in inputs:
        node = records[item["lineage_node_id"]]
        if (
            node["role"] != item["role"]
            or node["artifact_id"] != item["artifact_id"]
            or node["schema_id"] != item["artifact_schema"]
            or node["content_sha256"] != item["content_sha256"]
            or node["artifact_sha256"] != item["artifact_sha256"]
            or tuple(node["rights_binding_ids"])
            != tuple(item["rights_binding_ids"])
        ):
            raise PowerCalibrationInputSchemaError(
                "terminal lineage does not bind its input artifact"
            )
        ancestry = set(graph[item["lineage_node_id"]])
        frontier = list(ancestry)
        while frontier:
            ancestor = frontier.pop()
            for parent in graph[ancestor]:
                if parent not in ancestry:
                    ancestry.add(parent)
                    frontier.append(parent)
        terminal_role = item["role"]
        for root in (ancestor for ancestor in ancestry if not graph[ancestor]):
            if not any(
                terminal_role in rights_roles[binding_id]
                for binding_id in records[root]["rights_binding_ids"]
            ):
                raise PowerCalibrationInputSchemaError(
                    "source rights do not cover the descendant terminal role"
                )
    reachable = set(terminals)
    frontier = list(terminals)
    while frontier:
        node = frontier.pop()
        for parent in graph[node]:
            if parent not in reachable:
                reachable.add(parent)
                frontier.append(parent)
    if reachable != set(graph):
        raise PowerCalibrationInputSchemaError("fixture lineage contains an orphan")
    if (
        _require_sha256(value["lineage_sha256"], "lineage hash")
        != hashlib.sha256(_canonical(nodes)).hexdigest()
    ):
        raise PowerCalibrationInputSchemaError("fixture lineage hash changed")
    return len(nodes)


def validate_synthetic_calibration_input_manifest_fixture(
    schema: PowerCalibrationInputSchema,
    payload: bytes,
) -> SyntheticCalibrationInputManifestSummary:
    """Validate metadata-only synthetic bytes; never load or promote production input."""
    require_loaded_power_calibration_input_schema(schema)
    raw = _parse_artifact(payload, "synthetic calibration input manifest")
    _require_keys(raw, MANIFEST_ROOT_FIELDS, "synthetic manifest")
    if raw["manifest_mode"] == PRODUCTION_MODE:
        raise PowerCalibrationInputSchemaError(
            "production calibration input manifests are not implemented"
        )
    if (
        raw["schema"] != MANIFEST_SCHEMA
        or raw["manifest_mode"] != SYNTHETIC_MODE
        or raw["status"] != SYNTHETIC_STATUS
        or raw["authority"] != SYNTHETIC_AUTHORITY
    ):
        raise PowerCalibrationInputSchemaError("synthetic manifest scope changed")
    _validate_identity(
        raw,
        "manifest_id",
        "manifest_hash",
        MANIFEST_ID_PREFIX,
        "synthetic manifest",
    )
    _require_exact(
        raw["schema_contract_binding"],
        _binding(
            artifact_id=schema.schema_contract_id,
            content_sha256=schema.schema_contract_hash,
            artifact_sha256=SCHEMA_CONTRACT_ARTIFACT_SHA256,
        ),
        "synthetic manifest schema binding",
    )
    _require_exact(
        raw["power_protocol_binding"],
        _binding(
            artifact_id=POWER_PROTOCOL_ID,
            content_sha256=POWER_PROTOCOL_HASH,
            artifact_sha256=POWER_PROTOCOL_ARTIFACT_SHA256,
        ),
        "synthetic manifest power protocol binding",
    )
    if raw["evaluation_id"] != EVALUATION_ID:
        raise PowerCalibrationInputSchemaError("synthetic evaluation identity changed")
    calibration_fold = _require_keys(
        raw["calibration_fold"],
        CALIBRATION_FOLD_FIELDS,
        "synthetic calibration fold",
    )
    _require_exact(
        calibration_fold,
        _schema_document()["calibration_boundary_contract"],
        "synthetic calibration fold",
    )
    evidence_epoch_id = _validate_evidence_epoch_binding(
        raw["evidence_epoch_binding"]
    )
    axis = _require_keys(
        raw["complete_session_axis"],
        SESSION_AXIS_FIELDS,
        "complete session axis",
    )
    sessions = schema.calibration_session_axis
    if (
        axis["exchange"] != EXCHANGE
        or axis["key_field"] != SESSION_KEY_FIELD
        or axis["key_format"] != SESSION_KEY_FORMAT
        or type(axis["ordered_session_keys"]) is not list
        or tuple(axis["ordered_session_keys"]) != sessions
        or len(set(axis["ordered_session_keys"])) != len(sessions)
        or _require_int(axis["session_count"], "axis session count")
        != CALIBRATION_SESSION_COUNT
        or axis["session_axis_sha256"] != CALIBRATION_AXIS_SHA256
        or axis["first_session"] != CALIBRATION_START
        or axis["last_session"] != CALIBRATION_LAST_SESSION
        or hashlib.sha256(_canonical(axis["ordered_session_keys"])).hexdigest()
        != CALIBRATION_AXIS_SHA256
    ):
        raise PowerCalibrationInputSchemaError("complete session axis changed")
    rights = _validate_rights(raw["rights_bindings"])
    inputs = _validate_inputs(raw["input_artifacts"], sessions, rights)
    lineage_count = _validate_producing_lineage(
        raw["producing_lineage"], evidence_epoch_id, inputs, rights
    )
    counts = _require_keys(
        raw["manifest_counts"],
        MANIFEST_COUNT_FIELDS,
        "manifest counts",
    )
    expected_counts = {
        "input_artifact_count": len(inputs),
        "rights_binding_count": len(rights),
        "lineage_node_count": lineage_count,
        "session_key_count": len(sessions),
    }
    for name, expected in expected_counts.items():
        if _require_int(counts[name], name) != expected:
            raise PowerCalibrationInputSchemaError("manifest counts do not close")
    _require_exact(
        raw["external_authorities"],
        dict(MANIFEST_EXTERNAL_AUTHORITIES),
        "synthetic external authorities",
    )
    _require_exact(raw["capabilities"], dict(CAPABILITIES), "synthetic capabilities")
    require_loaded_power_calibration_input_schema(schema)

    summary_definition = dict(raw)
    summary_definition["external_authorities"] = {
        name: raw["external_authorities"][name]
        for name in MANIFEST_EXTERNAL_AUTHORITIES
    }
    summary_definition["capabilities"] = {
        name: raw["capabilities"][name] for name in CAPABILITIES
    }
    value = object.__new__(SyntheticCalibrationInputManifestSummary)
    for name, item in {
        "manifest_id": raw["manifest_id"],
        "manifest_hash": raw["manifest_hash"],
        "evidence_epoch_id": evidence_epoch_id,
        "session_count": len(sessions),
        "input_roles": INPUT_ROLES,
        "input_artifact_count": len(inputs),
        "rights_binding_count": len(rights),
        "lineage_node_count": lineage_count,
        "definition": _freeze(summary_definition),
    }.items():
        object.__setattr__(value, name, item)
    return value


def render_expected_power_calibration_input_schema() -> str:
    """Render the one canonical checked-in ARV2-4D-B1 schema artifact."""
    return _render(_schema_document()).decode("utf-8")
