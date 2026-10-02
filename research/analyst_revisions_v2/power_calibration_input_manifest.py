"""Outcome-free ARV2-4D-B2 production-manifest admission boundary.

This module authenticates the accepted B1 manifest schema, the effective
four-family multiplicity overlay, one frozen B2 admission contract, and
caller-supplied *metadata* for a prospective production calibration manifest.
It deliberately never opens either calibration-input artifact, computes a
nuisance statistic, issues a numeric receipt, calls QuantConnect, reads an
outcome, deploys, or trades.

The owner's 2026-09-06 direction is represented exactly as a provisional
working assumption for private, personal, non-commercial QuantConnect
research.  It is not represented as vendor-written permission or a legal
conclusion.  A successfully loaded value is therefore an authenticated
metadata candidate only and cannot authorize a later stage.
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

from .artifact_io import (
    ArtifactIOError,
    read_stable_regular as _read_artifact_stable_regular,
    revalidate_regular as _revalidate_artifact_regular,
)
from .canonical import (
    FrozenContainerAuthority,
    capture_frozen_container_authority,
    frozen_container_authority_is_current,
)

from .four_family_multiplicity import (
    ANALYST_LANE_ID,
    FourFamilyMultiplicityError,
    FourFamilyMultiplicityOverlay,
    OVERLAY_ARTIFACT_SHA256,
    require_loaded_four_family_multiplicity_overlay,
)
from .power_calibration_input_schema import (
    BETA_INPUT_FIELDS,
    CALIBRATION_AXIS_SHA256,
    CALIBRATION_END_EXCLUSIVE,
    CALIBRATION_FOLD_FIELDS,
    CALIBRATION_FOLD_HASH,
    CALIBRATION_FOLD_ID,
    CALIBRATION_LAST_OUTCOME_SESSION,
    CALIBRATION_LAST_SESSION,
    CALIBRATION_SESSION_COUNT,
    CALIBRATION_START,
    CAPABILITIES,
    COMPONENT_INPUT_FIELDS,
    EVALUATION_ID,
    EVIDENCE_EPOCH_FIELDS,
    EXCHANGE,
    FIRST_TEST_SESSION,
    INPUT_ROLES,
    INPUT_SCHEMAS,
    LINEAGE_FIELDS,
    LINEAGE_NODE_FIELDS,
    LINEAGE_ROLES,
    MANIFEST_COUNT_FIELDS,
    MANIFEST_EXTERNAL_AUTHORITIES,
    MANIFEST_ID_PREFIX,
    MANIFEST_ROOT_FIELDS,
    MANIFEST_SCHEMA,
    POWER_PROTOCOL_ARTIFACT_SHA256,
    POWER_PROTOCOL_HASH,
    POWER_PROTOCOL_ID,
    PRODUCTION_MODE,
    RIGHTS_FIELDS,
    SCHEMA_CONTRACT_ARTIFACT_SHA256,
    SESSION_AXIS_FIELDS,
    SESSION_KEY_FIELD,
    SESSION_KEY_FORMAT,
    PowerCalibrationInputSchema,
    PowerCalibrationInputSchemaError,
    require_loaded_power_calibration_input_schema,
)


class PowerCalibrationInputManifestError(ValueError):
    """The B2 contract or prospective production metadata is invalid."""


ADMISSION_CONTRACT_SCHEMA = (
    "arv2-stock-power-calibration-production-manifest-admission-structural-v1"
)
ADMISSION_CONTRACT_STATUS = (
    "owner_authorized_outcome_free_candidate_pending_independent_review"
)
ADMISSION_CONTRACT_AUTHORITY = (
    "production_metadata_candidate_validation_only_no_input_outcome_"
    "calibration_receipt_qc_or_deployment_authority"
)
ADMISSION_CONTRACT_ID_PREFIX = (
    "arv2-stock-power-calibration-manifest-admission-"
)
ADMISSION_CONTRACT_ARTIFACT_SHA256 = (
    "173d161b80447ee8bc0b28a1e5fef49cd00f1df1a53ef67fe195ebd1d153e811"
)

B1_SCHEMA_ID = "arv2-stock-power-calibration-input-schema-4032405d1773236e"
B1_SCHEMA_HASH = (
    "4032405d1773236e61938a88c6ec77e62bbbd71ff8e24eb615565023c07f8e24"
)
FOUR_FAMILY_OVERLAY_ID = "arv2-four-family-multiplicity-54ab0bb69fb6fa16"
FOUR_FAMILY_OVERLAY_HASH = (
    "54ab0bb69fb6fa162ca3ba6764864b230136c68c017f1e6b669034dda75b806e"
)

OWNER_DECISION_ID = "arv2-owner-working-rights-assumption-2026-09-06"
OWNER_DECISION_SOURCE = "owner_direction_in_current_analyst_lane_session"
OWNER_DECISION_SCOPE = (
    "arv2_4d_b2_metadata_contract_only_no_input_read_or_qc_action"
)
OWNER_RIGHTS_BASIS = "owner_reported_multiple_public_user_cases"
MASSIVE_BENZINGA_ASSUMPTION_SCOPE_ID = (
    "private_personal_noncommercial_quantconnect_research_massive_benzinga_"
    "working_assumption"
)
NO_SOURCE_PROCESSING_AUTHORITY_SCOPE_ID = (
    "metadata_only_no_source_processing_authority"
)
REPRESENTATION_SCOPES = (
    "raw_analyst_ratings",
    "normalized_analyst_ratings",
    "derived_content_addressed_signals",
    "immutable_historical_snapshots",
)
OWNER_ASSUMPTION_PURPOSE = (
    "nuisance_only_power_calibration_and_closed_aggregate_receipt"
)
FIRST_TEST_SESSION_OPEN_UTC = "2020-01-31T14:30:00.000000Z"
VINTAGE_METHODS = (
    "contemporaneous_immutable_snapshot",
    "externally_attested_as_of_reconstruction",
)
VINTAGE_ATTESTATION_SCHEMA = (
    "arv2-external-as-of-vintage-attestation-receipt-v1"
)

EVIDENCE_BUNDLE_SCHEMA = "arv2-power-calibration-admission-evidence-bundle-v1"
EVIDENCE_BUNDLE_STATUS = "candidate_metadata_evidence_not_production_authority"
EVIDENCE_BUNDLE_AUTHORITY = (
    "owner_assumption_entitlement_and_vintage_metadata_only_no_input_or_qc_authority"
)
EVIDENCE_BUNDLE_ID_PREFIX = "arv2-power-calibration-evidence-bundle-"
RIGHTS_RECEIPT_SCHEMA = EVIDENCE_BUNDLE_SCHEMA

# Ultimate external source categories only.  Internal/derived artifacts belong
# in the producing-lineage DAG as transformation nodes, not as entitlement
# endpoints.  A physical source snapshot may cover several categories, and a
# category may be partitioned across several snapshots.
REQUIRED_EXTERNAL_SOURCE_ROLE_INPUTS = MappingProxyType(
    {
        "analyst_ratings_events": INPUT_ROLES,
        "earnings_and_guidance_events": INPUT_ROLES,
        "market_prices_corporate_actions_and_total_returns": INPUT_ROLES,
        "point_in_time_fundamentals_and_control_inputs": INPUT_ROLES,
        "point_in_time_industry_sector_classification": INPUT_ROLES,
        "security_identity_and_listing_history": INPUT_ROLES,
        "terminal_returns_and_delisting_events": (INPUT_ROLES[0],),
    }
)

PRODUCTION_CANDIDATE_STATUS = (
    "production_metadata_candidate_pending_review_and_input_authority"
)
PRODUCTION_CANDIDATE_AUTHORITY = (
    "metadata_authentication_only_no_input_outcome_calibration_receipt_or_qc_authority"
)

POLICY_BINDING_FIELDS = ("artifact_id", "content_sha256", "artifact_sha256")
EVIDENCE_BUNDLE_FIELDS = (
    "schema",
    "status",
    "authority",
    "bundle_id",
    "bundle_hash",
    "owner_decision",
    "data_entitlement_evidence",
    "processing_rights_evidence",
    "vintage_evidence",
    "capabilities",
)
OWNER_DECISION_FIELDS = (
    "decision_id",
    "decision_date",
    "source",
    "reported_evidence_basis",
    "authorized_scope",
    "vendor_written_permission_obtained",
    "independent_web_verification_performed",
    "legal_conclusion",
    "input_read_authorized",
    "nuisance_compute_authorized",
    "qc_action_authorized",
    "outcome_access_authorized",
)
ENTITLEMENT_FIELDS = (
    "audit_id",
    "source_roles",
    "source_artifact_id",
    "source_content_sha256",
    "source_artifact_sha256",
    "provider_id",
    "product_id",
    "endpoint_id",
    "account_scope_sha256",
    "observed_at_utc",
    "endpoint_access_observed",
    "historical_access_observed",
    "credential_material_present",
    "applies_to_input_roles",
)
PROCESSING_RIGHTS_FIELDS = (
    "working_assumption_id",
    "evidence_basis",
    "owner_assumption_processing_scope_id",
    "representation_scopes",
    "owner_assumption_permitted_purpose",
    "candidate_input_metadata_bindings",
    "source_assumption_bindings",
    "quantconnect_project_visibility",
    "personal_noncommercial_use_only",
    "massive_benzinga_private_qc_processing_under_owner_assumption",
    "all_other_source_processing_authorized",
    "redistribution_permitted",
    "input_read_authorized",
    "vendor_written_permission_obtained",
    "independent_web_verification_performed",
    "legal_conclusion",
)
ROLE_INPUT_BINDING_FIELDS = (
    "role",
    "artifact_id",
    "content_sha256",
    "artifact_sha256",
)
SOURCE_ASSUMPTION_BINDING_FIELDS = (
    "binding_id",
    "source_artifact_id",
    "data_entitlement_audit_id",
    "processing_scope_id",
    "owner_working_assumption_applicable",
    "applies_to_input_roles",
)
SOURCE_SNAPSHOT_FIELDS = (
    "source_roles",
    "artifact_id",
    "schema_id",
    "content_sha256",
    "artifact_sha256",
    "data_entitlement_audit_id",
    "rights_binding_id",
)
ATTESTATION_FIELDS = (
    "attestation_schema",
    "attestation_id",
    "attestation_content_sha256",
    "attestation_artifact_sha256",
    "attested_information_cutoff_exclusive_utc",
    "source_snapshot_inventory_sha256",
    "correction_inventory_artifact_id",
    "correction_inventory_content_sha256",
    "correction_inventory_artifact_sha256",
    "cutoff_filter_recipe_id",
    "cutoff_filter_recipe_sha256",
)
VINTAGE_FIELDS = (
    "evidence_epoch_id",
    "evidence_epoch_artifact_id",
    "evidence_epoch_semantic_sha256",
    "evidence_epoch_artifact_sha256",
    "source_snapshot_capture_instant_utc",
    "evidence_recorded_instant_utc",
    "vintage_method",
    "first_test_session_open_utc",
    "max_included_availability_or_correction_instant_utc",
    "source_snapshot_bindings",
    "external_vintage_attestation",
    "calibration_information_cutoff_session",
    "first_excluded_session",
    "correction_inventory_artifact_id",
    "correction_inventory_content_sha256",
    "correction_inventory_artifact_sha256",
    "correction_inventory_record_count",
    "cutoff_filter_recipe_id",
    "cutoff_filter_recipe_sha256",
    "correction_inventory_complete",
    "included_post_cutoff_correction_count",
    "immutable_snapshot",
)

POLICY_EXTERNAL_BINDINGS = MappingProxyType(
    {
        "independent_review_commit": None,
        "counter_review_commit": None,
        "production_manifest_id": None,
        "production_manifest_artifact_sha256": None,
        "evidence_bundle_id": None,
        "evidence_bundle_artifact_sha256": None,
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


# The B1 axis contains 483 dates and exactly two inventory records per date.
# Four MiB leaves more than an order of magnitude of headroom for those closed
# inventories plus a 4,096-node metadata lineage while preventing an
# unauthenticated path from becoming an unbounded JSON-memory sink.
MAX_METADATA_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_ENTITLEMENT_AUDITS = 32
MAX_RIGHTS_BINDINGS = 32
MAX_LINEAGE_NODES = 4096
MAX_SAFE_COUNT = (1 << 63) - 1

_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,191}\Z")


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
        raise PowerCalibrationInputManifestError("noncanonical JSON value") from exc


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
        raise PowerCalibrationInputManifestError("noncanonical JSON value") from exc


def _binding(
    *, artifact_id: str, content_sha256: str, artifact_sha256: str
) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "content_sha256": content_sha256,
        "artifact_sha256": artifact_sha256,
    }


def _freeze(value: Any) -> Any:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _reject_float(value: str) -> None:
    raise PowerCalibrationInputManifestError(
        f"binary floating-point is forbidden: {value}"
    )


def _reject_constant(value: str) -> None:
    raise PowerCalibrationInputManifestError(
        f"non-finite JSON is forbidden: {value}"
    )


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PowerCalibrationInputManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_stable_regular(path: Path, name: str) -> tuple[Path, bytes]:
    try:
        return _read_artifact_stable_regular(
            Path(path), name=name, maximum_bytes=MAX_METADATA_ARTIFACT_BYTES
        )
    except ArtifactIOError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc


def _revalidate(path: Path, payload: bytes, name: str) -> None:
    try:
        _revalidate_artifact_regular(
            path,
            payload,
            name=name,
            maximum_bytes=MAX_METADATA_ARTIFACT_BYTES,
        )
    except ArtifactIOError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc


def _parse_artifact(payload: bytes, name: str) -> dict[str, Any]:
    if type(payload) is not bytes:
        raise PowerCalibrationInputManifestError(f"{name} must be bytes")
    if len(payload) > MAX_METADATA_ARTIFACT_BYTES:
        raise PowerCalibrationInputManifestError(
            f"{name} exceeds the frozen metadata size limit"
        )
    if payload.startswith(
        (
            b"\xef\xbb\xbf",
            b"\xff\xfe",
            b"\xfe\xff",
            b"\xff\xfe\x00\x00",
            b"\x00\x00\xfe\xff",
        )
    ):
        raise PowerCalibrationInputManifestError(f"{name} must not contain a BOM")
    try:
        raw = json.loads(
            payload.decode("utf-8", errors="strict"),
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_object,
        )
    except PowerCalibrationInputManifestError:
        raise
    except UnicodeDecodeError as exc:
        raise PowerCalibrationInputManifestError(f"{name} is not strict UTF-8") from exc
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise PowerCalibrationInputManifestError(f"{name} is invalid JSON") from exc
    if type(raw) is not dict:
        raise PowerCalibrationInputManifestError(f"{name} must be a JSON object")
    if _render(raw) != payload:
        raise PowerCalibrationInputManifestError(
            f"{name} bytes are not canonical sorted UTF-8 JSON"
        )
    return raw


def _require_exact(actual: object, expected: object, name: str) -> None:
    if type(actual) is not type(expected) or _canonical(actual) != _canonical(expected):
        raise PowerCalibrationInputManifestError(
            f"{name} changed from the frozen contract"
        )


def _require_keys(value: object, fields: Iterable[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(fields):
        raise PowerCalibrationInputManifestError(f"{name} fields are not exact")
    return value


def _require_identifier(value: object, name: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise PowerCalibrationInputManifestError(f"{name} is not a valid identifier")
    return value


def _require_sha256(value: object, name: str) -> str:
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise PowerCalibrationInputManifestError(f"{name} is not a SHA-256")
    return value


def _require_git_object(value: object, name: str) -> str:
    if type(value) is not str or _HEX_40.fullmatch(value) is None:
        raise PowerCalibrationInputManifestError(
            f"{name} is not a lowercase 40-hex Git object"
        )
    return value


def _require_int(
    value: object,
    name: str,
    *,
    minimum: int = 0,
    maximum: int = MAX_SAFE_COUNT,
) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        raise PowerCalibrationInputManifestError(f"{name} is not a valid bounded integer")
    return value


def _content_identity(
    raw: Mapping[str, Any], *, id_field: str, hash_field: str, prefix: str
) -> dict[str, Any]:
    value = dict(raw)
    value[id_field] = None
    value[hash_field] = None
    digest = hashlib.sha256(_canonical(value)).hexdigest()
    value[hash_field] = digest
    value[id_field] = f"{prefix}{digest[:16]}"
    return value


def _owner_decision() -> dict[str, object]:
    return {
        "decision_id": OWNER_DECISION_ID,
        "decision_date": "2026-09-06",
        "source": OWNER_DECISION_SOURCE,
        "reported_evidence_basis": OWNER_RIGHTS_BASIS,
        "authorized_scope": OWNER_DECISION_SCOPE,
        "vendor_written_permission_obtained": False,
        "independent_web_verification_performed": False,
        "legal_conclusion": False,
        "input_read_authorized": False,
        "nuisance_compute_authorized": False,
        "qc_action_authorized": False,
        "outcome_access_authorized": False,
    }


def _admission_document() -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": ADMISSION_CONTRACT_SCHEMA,
        "status": ADMISSION_CONTRACT_STATUS,
        "authority": ADMISSION_CONTRACT_AUTHORITY,
        "admission_contract_id": None,
        "admission_contract_hash": None,
        "lane_id": ANALYST_LANE_ID,
        "owner_decision": _owner_decision(),
        "bound_parents": {
            "calibration_input_schema": _binding(
                artifact_id=B1_SCHEMA_ID,
                content_sha256=B1_SCHEMA_HASH,
                artifact_sha256=SCHEMA_CONTRACT_ARTIFACT_SHA256,
            ),
            "four_family_multiplicity_overlay": _binding(
                artifact_id=FOUR_FAMILY_OVERLAY_ID,
                content_sha256=FOUR_FAMILY_OVERLAY_HASH,
                artifact_sha256=OVERLAY_ARTIFACT_SHA256,
            ),
        },
        "candidate_manifest_contract": {
            "schema": MANIFEST_SCHEMA,
            "mode": PRODUCTION_MODE,
            "status": PRODUCTION_CANDIDATE_STATUS,
            "authority": PRODUCTION_CANDIDATE_AUTHORITY,
            "manifest_payload": "canonical_pretty_sorted_strict_UTF8_metadata_only",
            "input_artifact_paths": "FORBIDDEN",
            "input_artifact_reads": False,
            "production_manifest_acceptance_authority": False,
            "production_metadata_candidate_loader_implemented": True,
            "metadata_authentication_does_not_authenticate_input_artifacts": True,
            "production_lineage_complete": False,
            "numeric_values_permitted": "component_counts_only_as_frozen_by_B1",
        },
        "evidence_bundle_contract": {
            "schema": EVIDENCE_BUNDLE_SCHEMA,
            "status": EVIDENCE_BUNDLE_STATUS,
            "authority": EVIDENCE_BUNDLE_AUTHORITY,
            "required_exact_root_fields": list(EVIDENCE_BUNDLE_FIELDS),
            "required_exact_owner_decision_fields": list(OWNER_DECISION_FIELDS),
            "required_exact_entitlement_fields": list(ENTITLEMENT_FIELDS),
            "required_exact_processing_rights_fields": list(
                PROCESSING_RIGHTS_FIELDS
            ),
            "required_exact_role_input_binding_fields": list(
                ROLE_INPUT_BINDING_FIELDS
            ),
            "required_exact_source_assumption_binding_fields": list(
                SOURCE_ASSUMPTION_BINDING_FIELDS
            ),
            "required_exact_vintage_fields": list(VINTAGE_FIELDS),
            "required_exact_source_snapshot_fields": list(
                SOURCE_SNAPSHOT_FIELDS
            ),
            "required_exact_attestation_fields": list(ATTESTATION_FIELDS),
            "owner_assumption_is_not_vendor_permission": True,
            "copied_or_self_declared_bundle_grants_input_authority": False,
            "structural_validation_is_not_rights_authorization": True,
            "structural_validation_is_not_vintage_proof": True,
        },
        "entitlement_contract": {
            "required_ultimate_external_source_roles_and_input_dependencies": {
                role: list(input_roles)
                for role, input_roles in REQUIRED_EXTERNAL_SOURCE_ROLE_INPUTS.items()
            },
            "source_role_coverage": "closed_nonempty_union_exact",
            "one_snapshot_may_cover_multiple_source_roles": True,
            "one_source_role_may_span_multiple_snapshot_partitions": True,
            "internal_or_derived_artifacts_are_lineage_transformations": True,
            "one_exact_entitlement_audit_per_source_snapshot": True,
            "one_exact_source_snapshot_per_entitlement_audit": True,
            "audit_inventory_order": "audit_id_ASCII_sorted_unique",
            "every_declared_audit_and_source_assumption_binding_is_used": True,
            "analyst_ratings_provider_id": "massive",
            "analyst_ratings_product_id": "benzinga-analyst-ratings",
            "analyst_ratings_endpoint_id": "benzinga-v1-ratings",
            "at_least_one_massive_benzinga_analyst_ratings_source": True,
            "massive_benzinga_audit_may_claim_only_analyst_ratings_role": True,
            "all_other_provider_product_endpoint_ids": (
                "caller_declared_production_identifiers_pending_truth_authentication"
            ),
            "credential_material_permitted": False,
            "entitlement_truth_authenticated": False,
        },
        "vintage_contract": {
            "manifest_capture_must_equal_evidence_capture": True,
            "evidence_recorded_must_not_precede_capture": True,
            "accepted_vintage_methods": list(VINTAGE_METHODS),
            "contemporaneous_capture_window": (
                "capture_at_or_after_2020_01_31_00_00_UTC_and_strictly_before_"
                "first_test_session_open"
            ),
            "reconstructed_vintage_requires_external_attestation": True,
            "max_included_availability_or_correction_must_not_exceed_cutoff": True,
            "first_test_session_open_utc": FIRST_TEST_SESSION_OPEN_UTC,
            "complete_correction_inventory_hash_required": True,
            "cutoff_filter_recipe_hash_required": True,
            "included_post_cutoff_correction_count": 0,
            "calibration_information_cutoff_session": (
                CALIBRATION_LAST_OUTCOME_SESSION
            ),
            "first_excluded_session": FIRST_TEST_SESSION,
            "immutable_snapshot_required": True,
            "bare_post_cutoff_false_flag_is_insufficient": True,
            "complete_empty_correction_inventory_permitted": True,
        },
        "rights_contract": {
            "receipt_schema": RIGHTS_RECEIPT_SCHEMA,
            "massive_benzinga_owner_working_assumption_id": OWNER_DECISION_ID,
            "massive_benzinga_assumption_scope_id": (
                MASSIVE_BENZINGA_ASSUMPTION_SCOPE_ID
            ),
            "all_other_source_scope_id": NO_SOURCE_PROCESSING_AUTHORITY_SCOPE_ID,
            "representation_scopes": list(REPRESENTATION_SCOPES),
            "owner_assumption_permitted_purpose": OWNER_ASSUMPTION_PURPOSE,
            "quantconnect_project_visibility": "private_owner_only",
            "personal_noncommercial_use_only": True,
            "vendor_written_permission_obtained": False,
            "legal_conclusion": False,
            "working_assumption_applies_only_to_massive_benzinga_source": True,
            "all_other_source_processing_authorized": False,
            "qc_transfer_or_action_authority": False,
            "input_read_authority": False,
        },
        "identity_and_canonicalization_contract": {
            "semantic_identity": (
                "SHA256_of_compact_sorted_UTF8_JSON_with_own_id_and_hash_null"
            ),
            "artifact_identity": "SHA256_of_exact_canonical_pretty_sorted_UTF8_bytes",
            "artifact_terminal_newline": "LF",
            "duplicate_keys": "refuse",
            "binary_floats_and_nonfinite_numbers": "refuse",
            "BOM_invalid_UTF8_CRLF_or_whitespace_variants": "refuse",
            "links_nonregular_files_and_unstable_reads": "refuse",
            "semantic_and_artifact_hashes_are_distinct_fields": True,
        },
        "resource_bounds": {
            "B2_owned_metadata_artifact_bytes_maximum": (
                MAX_METADATA_ARTIFACT_BYTES
            ),
            "already_loaded_parent_reauthentication_artifact_bytes_maximum": (
                MAX_METADATA_ARTIFACT_BYTES
            ),
            "cold_parent_construction_is_outside_B2_loader_scope": True,
            "descriptor_nofollow_nonblock_fstat_regular_and_path_identity_required": True,
            "entitlement_audits_maximum": MAX_ENTITLEMENT_AUDITS,
            "rights_bindings_maximum": MAX_RIGHTS_BINDINGS,
            "lineage_nodes_maximum": MAX_LINEAGE_NODES,
            "integer_maximum": MAX_SAFE_COUNT,
            "initial_and_revalidation_reads_bounded_to_maximum_plus_one": True,
        },
        "cross_binding_contract": {
            "rights_receipt_schema_equals_evidence_bundle_schema": True,
            "each_source_snapshot_binds_exactly_one_entitlement_audit": True,
            "each_source_snapshot_binds_exactly_one_source_assumption_binding": True,
            "manifest_rights_equal_evidence_source_assumption_bindings": True,
            "each_input_rights_equal_all_role_applicable_source_bindings": True,
            "lineage_roots_equal_source_snapshot_inventory": True,
            "terminal_rights_equal_ancestor_root_rights": True,
            "orphan_audits_rights_roots_or_nodes": "refuse",
            "B1_manifest_external_authorities": "all_null",
        },
        "lineage_contract": {
            "representation": "exact_direct_parent_bindings_not_copied_ancestry",
            "direct_parents": [
                "calibration_input_schema",
                "four_family_multiplicity_overlay",
            ],
            "each_parent_reauthenticates_its_own_accepted_acyclic_lineage": True,
            "copied_merged_ancestor_DAG": False,
            "declared_candidate_lineage_is_closed": True,
            "production_lineage_complete": False,
        },
        "calibration_boundary": {
            "fold_id": CALIBRATION_FOLD_ID,
            "structural_fold_sha256": CALIBRATION_FOLD_HASH,
            "validation_start_inclusive": CALIBRATION_START,
            "validation_end_exclusive": CALIBRATION_END_EXCLUSIVE,
            "last_included_decision_session": CALIBRATION_LAST_SESSION,
            "last_included_h20_outcome_session": (
                CALIBRATION_LAST_OUTCOME_SESSION
            ),
            "first_test_session": FIRST_TEST_SESSION,
            "session_count": CALIBRATION_SESSION_COUNT,
            "session_axis_sha256": CALIBRATION_AXIS_SHA256,
        },
        "later_stage_gate": {
            "input_artifact_loader_implemented": False,
            "nuisance_calibration_implemented": False,
            "numeric_receipt_implemented": False,
            "stock_successor_v3_implemented": False,
            "separate_owner_input_access_authority_required": True,
            "separate_owner_nuisance_compute_authority_required": True,
            "independent_review_and_codex_counter_review_required": True,
        },
        "external_bindings": dict(POLICY_EXTERNAL_BINDINGS),
        "capabilities": dict(CAPABILITIES),
    }
    return _content_identity(
        raw,
        id_field="admission_contract_id",
        hash_field="admission_contract_hash",
        prefix=ADMISSION_CONTRACT_ID_PREFIX,
    )


def _require_production_identifier(value: object, name: str) -> str:
    result = _require_identifier(value, name)
    if result.startswith("synthetic-"):
        raise PowerCalibrationInputManifestError(f"{name} must not be synthetic")
    return result


def _require_instant(value: object, name: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise PowerCalibrationInputManifestError(f"{name} is not a strict UTC instant")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except (ValueError, TypeError) as exc:
        raise PowerCalibrationInputManifestError(
            f"{name} is not a strict UTC instant"
        ) from exc
    canonical = (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    if canonical != value:
        raise PowerCalibrationInputManifestError(f"{name} is not canonical UTC")
    return parsed


def _require_identity(
    raw: Mapping[str, Any], *, id_field: str, hash_field: str, prefix: str, name: str
) -> None:
    declared = _require_sha256(raw.get(hash_field), f"{name} content hash")
    candidate = dict(raw)
    candidate[id_field] = None
    candidate[hash_field] = None
    actual = hashlib.sha256(_canonical(candidate)).hexdigest()
    if declared != actual or raw.get(id_field) != f"{prefix}{actual[:16]}":
        raise PowerCalibrationInputManifestError(
            f"{name} identity is not content-derived"
        )


def _policy_fingerprint(value: "PowerCalibrationManifestAdmission") -> tuple[object, ...]:
    scalar_values = (
        value.admission_contract_id,
        value.admission_contract_hash,
        value.owner_decision_id,
    )
    if any(type(item) is not str for item in scalar_values):
        raise PowerCalibrationInputManifestError("authority state is noncanonical")
    return (
        *(_fingerprint(item) for item in scalar_values),
        _fingerprint(value.calibration_session_axis),
        _fingerprint(value.definition),
        _fingerprint(value.capabilities),
    )


def _fingerprint(value: object) -> object:
    if type(value) is MappingProxyType:
        pairs: list[tuple[str, object]] = []
        for key, item in value.items():
            if type(key) is not str:
                raise PowerCalibrationInputManifestError(
                    "authority state has a non-string key"
                )
            pairs.append((key, _fingerprint(item)))
        return ("mapping", tuple(sorted(pairs)))
    if type(value) is tuple:
        return ("tuple", tuple(_fingerprint(item) for item in value))
    if type(value) is str:
        return ("str", value)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if value is None:
        return ("NoneType", None)
    raise PowerCalibrationInputManifestError("authority state is noncanonical")


@dataclasses.dataclass(frozen=True, init=False)
class PowerCalibrationManifestAdmission:
    admission_contract_id: str
    admission_contract_hash: str
    owner_decision_id: str
    calibration_session_axis: tuple[str, ...]
    definition: Mapping[str, Any]
    capabilities: Mapping[str, bool]
    _authority: object = dataclasses.field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError("admission contracts must be loader-authenticated")

    @property
    def production_metadata_candidate_loader_available(self) -> bool:
        require_loaded_power_calibration_manifest_admission(self)
        return True

    @property
    def massive_benzinga_working_assumption_accepted(self) -> bool:
        require_loaded_power_calibration_manifest_admission(self)
        return True

    @property
    def production_manifest_acceptance_available(self) -> bool:
        return False

    @property
    def calibration_input_access_available(self) -> bool:
        return False

    @property
    def input_access_available(self) -> bool:
        return False

    @property
    def source_access_available(self) -> bool:
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
    def outcome_access_available(self) -> bool:
        return False

    @property
    def deployment_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False


@dataclasses.dataclass(frozen=True, init=False)
class ProductionCalibrationInputManifestCandidate:
    manifest_id: str
    manifest_content_sha256: str
    manifest_artifact_sha256: str
    evidence_bundle_id: str
    evidence_bundle_content_sha256: str
    evidence_bundle_artifact_sha256: str
    evidence_epoch_id: str
    data_entitlement_audit_ids: tuple[str, ...]
    massive_benzinga_working_assumption_id: str
    session_count: int
    input_roles: tuple[str, ...]
    definition: Mapping[str, Any]
    _authority: object = dataclasses.field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError("manifest candidates must be produced by the B2 loader")

    @property
    def metadata_authenticated(self) -> bool:
        require_loaded_production_calibration_input_manifest_candidate(self)
        return True

    @property
    def massive_benzinga_working_assumption_accepted(self) -> bool:
        require_loaded_production_calibration_input_manifest_candidate(self)
        return True

    @property
    def production_authorized(self) -> bool:
        return False

    @property
    def rights_authorized(self) -> bool:
        return False

    @property
    def vintage_proven(self) -> bool:
        return False

    @property
    def input_artifacts_authenticated(self) -> bool:
        return False

    @property
    def entitlement_truth_authenticated(self) -> bool:
        return False

    @property
    def production_lineage_complete(self) -> bool:
        return False

    @property
    def input_access_available(self) -> bool:
        return False

    @property
    def source_access_available(self) -> bool:
        return False

    @property
    def calibration_available(self) -> bool:
        return False

    @property
    def authoritative_receipt_available(self) -> bool:
        return False

    @property
    def qc_action_available(self) -> bool:
        return False

    @property
    def outcome_access_available(self) -> bool:
        return False

    @property
    def deployment_available(self) -> bool:
        return False

    @property
    def orders_available(self) -> bool:
        return False

    @property
    def order_submission_available(self) -> bool:
        return False

    @property
    def trading_available(self) -> bool:
        return False


_LOADED_ADMISSION_AUTHORITY = object()
_LOADED_CANDIDATE_AUTHORITY = object()
_ADMISSION_CONTAINER_FIELDS = (
    "calibration_session_axis",
    "definition",
    "capabilities",
)
_CANDIDATE_CONTAINER_FIELDS = (
    "data_entitlement_audit_ids",
    "input_roles",
    "definition",
)
_ADMISSION_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[PowerCalibrationManifestAdmission],
        Path,
        bytes,
        PowerCalibrationInputSchema,
        FourFamilyMultiplicityOverlay,
        tuple[object, ...],
        FrozenContainerAuthority,
    ],
] = {}
_ADMISSION_AUTHORITIES_LOCK = threading.RLock()
_CANDIDATE_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[ProductionCalibrationInputManifestCandidate],
        Path,
        bytes,
        Path,
        bytes,
        PowerCalibrationManifestAdmission,
        tuple[object, ...],
        FrozenContainerAuthority,
    ],
] = {}
_CANDIDATE_AUTHORITIES_LOCK = threading.RLock()


def _container_roots(
    value: object, field_names: tuple[str, ...]
) -> tuple[object, ...]:
    return tuple(getattr(value, name) for name in field_names)


def _container_roots_are_current(
    value: object,
    field_names: tuple[str, ...],
    authority: FrozenContainerAuthority,
) -> bool:
    return frozen_container_authority_is_current(
        (getattr(value, name, None) for name in field_names),
        authority,
    )


def _forget_admission(
    identity: int, reference: weakref.ReferenceType[PowerCalibrationManifestAdmission]
) -> None:
    with _ADMISSION_AUTHORITIES_LOCK:
        current = _ADMISSION_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _ADMISSION_AUTHORITIES.pop(identity, None)


def _forget_candidate(
    identity: int,
    reference: weakref.ReferenceType[ProductionCalibrationInputManifestCandidate],
) -> None:
    with _CANDIDATE_AUTHORITIES_LOCK:
        current = _CANDIDATE_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _CANDIDATE_AUTHORITIES.pop(identity, None)


def load_power_calibration_manifest_admission(
    admission_path: Path,
    *,
    input_schema: PowerCalibrationInputSchema,
    multiplicity_overlay: FourFamilyMultiplicityOverlay,
) -> PowerCalibrationManifestAdmission:
    """Authenticate B2 and both accepted, independently reviewed parents."""
    try:
        require_loaded_power_calibration_input_schema(input_schema)
        require_loaded_four_family_multiplicity_overlay(multiplicity_overlay)
    except (PowerCalibrationInputSchemaError, FourFamilyMultiplicityError) as exc:
        raise PowerCalibrationInputManifestError(
            "B2 requires authenticated B1 and four-family parents"
        ) from exc
    if (
        input_schema.schema_contract_id != B1_SCHEMA_ID
        or input_schema.schema_contract_hash != B1_SCHEMA_HASH
        or multiplicity_overlay.overlay_id != FOUR_FAMILY_OVERLAY_ID
        or multiplicity_overlay.overlay_hash != FOUR_FAMILY_OVERLAY_HASH
        or len(input_schema.calibration_session_axis) != CALIBRATION_SESSION_COUNT
    ):
        raise PowerCalibrationInputManifestError("B2 parent identity changed")
    try:
        resolved, payload = _read_stable_regular(admission_path, "B2 admission contract")
        raw = _parse_artifact(payload, "B2 admission contract")
    except PowerCalibrationInputSchemaError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc
    if hashlib.sha256(payload).hexdigest() != ADMISSION_CONTRACT_ARTIFACT_SHA256:
        raise PowerCalibrationInputManifestError("B2 admission contract bytes changed")
    _require_identity(
        raw,
        id_field="admission_contract_id",
        hash_field="admission_contract_hash",
        prefix=ADMISSION_CONTRACT_ID_PREFIX,
        name="B2 admission contract",
    )
    try:
        _require_exact(raw, _admission_document(), "B2 admission contract")
        _revalidate(resolved, payload, "B2 admission contract")
        require_loaded_power_calibration_input_schema(input_schema)
        require_loaded_four_family_multiplicity_overlay(multiplicity_overlay)
        _revalidate(resolved, payload, "B2 admission contract")
    except (PowerCalibrationInputSchemaError, FourFamilyMultiplicityError) as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc

    value = object.__new__(PowerCalibrationManifestAdmission)
    for name, item in {
        "admission_contract_id": raw["admission_contract_id"],
        "admission_contract_hash": raw["admission_contract_hash"],
        "owner_decision_id": OWNER_DECISION_ID,
        "calibration_session_axis": input_schema.calibration_session_axis,
        "definition": _freeze(raw),
        "capabilities": _freeze(dict(CAPABILITIES)),
        "_authority": _LOADED_ADMISSION_AUTHORITY,
    }.items():
        object.__setattr__(value, name, item)
    container_authority = capture_frozen_container_authority(
        _container_roots(value, _ADMISSION_CONTAINER_FIELDS)
    )
    fingerprint = _policy_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_admission(key, ref)
    )
    with _ADMISSION_AUTHORITIES_LOCK:
        _ADMISSION_AUTHORITIES[identity] = (
            reference,
            resolved,
            payload,
            input_schema,
            multiplicity_overlay,
            fingerprint,
            container_authority,
        )
    return value


def require_loaded_power_calibration_manifest_admission(
    admission: PowerCalibrationManifestAdmission,
) -> PowerCalibrationManifestAdmission:
    if (
        type(admission) is not PowerCalibrationManifestAdmission
        or getattr(admission, "_authority", None) is not _LOADED_ADMISSION_AUTHORITY
    ):
        raise PowerCalibrationInputManifestError(
            "B2 admission contract is not loader-authenticated"
        )
    with _ADMISSION_AUTHORITIES_LOCK:
        authority = _ADMISSION_AUTHORITIES.get(id(admission))
    if authority is None or authority[0]() is not admission:
        raise PowerCalibrationInputManifestError("B2 admission authority is absent")
    if not _container_roots_are_current(
        admission, _ADMISSION_CONTAINER_FIELDS, authority[6]
    ):
        raise PowerCalibrationInputManifestError(
            "B2 admission container roots changed"
        )
    try:
        current_fingerprint = _policy_fingerprint(admission)
    except AttributeError as exc:
        raise PowerCalibrationInputManifestError(
            "B2 admission object changed"
        ) from exc
    if current_fingerprint != authority[5]:
        raise PowerCalibrationInputManifestError("B2 admission object changed")
    try:
        _revalidate(authority[1], authority[2], "B2 admission contract")
        require_loaded_power_calibration_input_schema(authority[3])
        require_loaded_four_family_multiplicity_overlay(authority[4])
        _revalidate(authority[1], authority[2], "B2 admission contract")
    except (PowerCalibrationInputSchemaError, FourFamilyMultiplicityError) as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc
    return admission


def _require_input_roles(
    raw: object, expected: tuple[str, ...], name: str
) -> tuple[str, ...]:
    if (
        type(raw) is not list
        or any(type(role) is not str for role in raw)
        or tuple(raw) != expected
    ):
        raise PowerCalibrationInputManifestError(f"{name} changed")
    return tuple(raw)


def _require_external_source_roles(raw: object, name: str) -> tuple[str, ...]:
    if (
        type(raw) is not list
        or not raw
        or len(raw) > len(REQUIRED_EXTERNAL_SOURCE_ROLE_INPUTS)
        or any(type(role) is not str for role in raw)
    ):
        raise PowerCalibrationInputManifestError(f"{name} is not a closed inventory")
    result = tuple(raw)
    if (
        result != tuple(sorted(set(result)))
        or any(role not in REQUIRED_EXTERNAL_SOURCE_ROLE_INPUTS for role in result)
    ):
        raise PowerCalibrationInputManifestError(f"{name} is not a closed inventory")
    return result


def _input_roles_for_external_sources(
    source_roles: tuple[str, ...],
) -> tuple[str, ...]:
    covered = {
        input_role
        for source_role in source_roles
        for input_role in REQUIRED_EXTERNAL_SOURCE_ROLE_INPUTS[source_role]
    }
    return tuple(role for role in INPUT_ROLES if role in covered)


def _validate_evidence_bundle(raw: object) -> dict[str, Any]:
    value = _require_keys(raw, EVIDENCE_BUNDLE_FIELDS, "B2 evidence bundle")
    if (
        value["schema"] != EVIDENCE_BUNDLE_SCHEMA
        or value["status"] != EVIDENCE_BUNDLE_STATUS
        or value["authority"] != EVIDENCE_BUNDLE_AUTHORITY
    ):
        raise PowerCalibrationInputManifestError("B2 evidence bundle scope changed")
    _require_identity(
        value,
        id_field="bundle_id",
        hash_field="bundle_hash",
        prefix=EVIDENCE_BUNDLE_ID_PREFIX,
        name="B2 evidence bundle",
    )
    owner = _require_keys(
        value["owner_decision"], OWNER_DECISION_FIELDS, "owner decision"
    )
    _require_exact(owner, _owner_decision(), "owner decision")

    entitlement_raw = value["data_entitlement_evidence"]
    if (
        type(entitlement_raw) is not list
        or not entitlement_raw
        or len(entitlement_raw) > MAX_ENTITLEMENT_AUDITS
    ):
        raise PowerCalibrationInputManifestError(
            "entitlement audit inventory is not exact"
        )
    entitlements: list[dict[str, Any]] = []
    audit_ids: list[str] = []
    covered_source_roles: set[str] = set()
    source_artifact_ids: list[str] = []
    entitlement_instants: list[datetime] = []
    massive_benzinga_audit_count = 0
    for index, item in enumerate(entitlement_raw):
        item = _require_keys(item, ENTITLEMENT_FIELDS, f"entitlement audit {index}")
        audit_id = _require_production_identifier(
            item["audit_id"], f"entitlement audit {index} ID"
        )
        source_roles = _require_external_source_roles(
            item["source_roles"], f"entitlement audit {index} source roles"
        )
        source_artifact_id = _require_production_identifier(
            item["source_artifact_id"],
            f"entitlement audit {index} source artifact",
        )
        _require_sha256(
            item["source_content_sha256"],
            f"entitlement audit {index} source content hash",
        )
        _require_sha256(
            item["source_artifact_sha256"],
            f"entitlement audit {index} source artifact hash",
        )
        for field in ("provider_id", "product_id", "endpoint_id"):
            _require_production_identifier(
                item[field], f"entitlement audit {index} {field}"
            )
        _require_sha256(
            item["account_scope_sha256"],
            f"entitlement audit {index} account scope hash",
        )
        entitlement_instants.append(
            _require_instant(
                item["observed_at_utc"], f"entitlement audit {index} observation"
            )
        )
        _require_input_roles(
            item["applies_to_input_roles"],
            _input_roles_for_external_sources(source_roles),
            f"entitlement audit {index} input roles",
        )
        if (
            item["endpoint_access_observed"] is not True
            or item["historical_access_observed"] is not True
            or item["credential_material_present"] is not False
        ):
            raise PowerCalibrationInputManifestError(
                "entitlement observation is incomplete or contains credential material"
            )
        is_ratings_role = source_roles == ("analyst_ratings_events",)
        is_massive_benzinga_ratings_endpoint = (
            item["provider_id"],
            item["product_id"],
            item["endpoint_id"],
        ) == ("massive", "benzinga-analyst-ratings", "benzinga-v1-ratings")
        if is_ratings_role is not is_massive_benzinga_ratings_endpoint:
            raise PowerCalibrationInputManifestError(
                "the Massive/Benzinga ratings endpoint and analyst-ratings role must bind biconditionally"
            )
        if is_massive_benzinga_ratings_endpoint:
            massive_benzinga_audit_count += 1
        audit_ids.append(audit_id)
        covered_source_roles.update(source_roles)
        source_artifact_ids.append(source_artifact_id)
        entitlements.append(item)
    if (
        tuple(audit_ids) != tuple(sorted(set(audit_ids)))
        or covered_source_roles != set(REQUIRED_EXTERNAL_SOURCE_ROLE_INPUTS)
        or len(set(source_artifact_ids)) != len(source_artifact_ids)
    ):
        raise PowerCalibrationInputManifestError(
            "entitlement audits must be sorted, unique, and source-complete"
        )
    if massive_benzinga_audit_count < 1:
        raise PowerCalibrationInputManifestError(
            "the owner working assumption requires at least one Massive/Benzinga ratings source"
        )

    rights = _require_keys(
        value["processing_rights_evidence"],
        PROCESSING_RIGHTS_FIELDS,
        "processing rights evidence",
    )
    if (
        rights["working_assumption_id"] != OWNER_DECISION_ID
        or rights["evidence_basis"] != OWNER_RIGHTS_BASIS
        or rights["owner_assumption_processing_scope_id"]
        != MASSIVE_BENZINGA_ASSUMPTION_SCOPE_ID
        or rights["representation_scopes"] != list(REPRESENTATION_SCOPES)
        or rights["owner_assumption_permitted_purpose"]
        != OWNER_ASSUMPTION_PURPOSE
        or rights["quantconnect_project_visibility"] != "private_owner_only"
        or rights["personal_noncommercial_use_only"] is not True
        or rights[
            "massive_benzinga_private_qc_processing_under_owner_assumption"
        ]
        is not True
        or rights["all_other_source_processing_authorized"] is not False
        or rights["redistribution_permitted"] is not False
        or rights["input_read_authorized"] is not False
        or rights["vendor_written_permission_obtained"] is not False
        or rights["independent_web_verification_performed"] is not False
        or rights["legal_conclusion"] is not False
    ):
        raise PowerCalibrationInputManifestError(
            "processing rights evidence exceeds the owner working assumption"
        )
    role_bindings = rights["candidate_input_metadata_bindings"]
    if type(role_bindings) is not list or len(role_bindings) != len(INPUT_ROLES):
        raise PowerCalibrationInputManifestError(
            "rights input-role binding inventory is not exact"
        )
    for index, (binding, role) in enumerate(
        zip(role_bindings, INPUT_ROLES, strict=True)
    ):
        binding = _require_keys(
            binding,
            ROLE_INPUT_BINDING_FIELDS,
            f"rights input binding {index}",
        )
        if binding["role"] != role:
            raise PowerCalibrationInputManifestError(
                "rights input-role binding order changed"
            )
        _require_production_identifier(
            binding["artifact_id"], f"rights {role} artifact ID"
        )
        _require_sha256(binding["content_sha256"], f"rights {role} content hash")
        _require_sha256(binding["artifact_sha256"], f"rights {role} artifact hash")

    source_assumptions_raw = rights["source_assumption_bindings"]
    if (
        type(source_assumptions_raw) is not list
        or len(source_assumptions_raw) != len(entitlements)
        or len(source_assumptions_raw) > MAX_RIGHTS_BINDINGS
    ):
        raise PowerCalibrationInputManifestError(
            "source rights inventory is not exact"
        )
    source_assumptions: list[dict[str, Any]] = []
    source_assumption_ids: list[str] = []
    audits_by_id = {item["audit_id"]: item for item in entitlements}
    for index, item in enumerate(source_assumptions_raw):
        item = _require_keys(
            item,
            SOURCE_ASSUMPTION_BINDING_FIELDS,
            f"source assumption binding {index}",
        )
        binding_id = _require_production_identifier(
            item["binding_id"], f"source right {index} ID"
        )
        _require_production_identifier(
            item["source_artifact_id"], f"source right {index} artifact"
        )
        audit_id = _require_production_identifier(
            item["data_entitlement_audit_id"],
            f"source assumption binding {index} audit",
        )
        audit = audits_by_id.get(audit_id)
        if audit is None or item["source_artifact_id"] != audit["source_artifact_id"]:
            raise PowerCalibrationInputManifestError(
                "source assumption binding is not tied to its exact entitlement audit"
            )
        owner_assumption_applicable = (
            audit["provider_id"],
            audit["product_id"],
            audit["endpoint_id"],
        ) == ("massive", "benzinga-analyst-ratings", "benzinga-v1-ratings")
        expected_scope = (
            MASSIVE_BENZINGA_ASSUMPTION_SCOPE_ID
            if owner_assumption_applicable
            else NO_SOURCE_PROCESSING_AUTHORITY_SCOPE_ID
        )
        if (
            item["owner_working_assumption_applicable"]
            is not owner_assumption_applicable
            or item["processing_scope_id"] != expected_scope
        ):
            raise PowerCalibrationInputManifestError(
                "source assumption binding exceeds the Massive/Benzinga-only owner decision"
            )
        _require_input_roles(
            item["applies_to_input_roles"],
            tuple(audit["applies_to_input_roles"]),
            f"source right {index} input roles",
        )
        source_assumption_ids.append(binding_id)
        source_assumptions.append(item)
    if (
        tuple(source_assumption_ids)
        != tuple(sorted(set(source_assumption_ids)))
        or {item["source_artifact_id"] for item in source_assumptions}
        != set(source_artifact_ids)
        or {
            item["data_entitlement_audit_id"] for item in source_assumptions
        }
        != set(audit_ids)
    ):
        raise PowerCalibrationInputManifestError(
            "source assumption bindings must be sorted, unique, and entitlement-complete"
        )

    vintage = _require_keys(
        value["vintage_evidence"], VINTAGE_FIELDS, "vintage evidence"
    )
    for field in (
        "evidence_epoch_id",
        "evidence_epoch_artifact_id",
        "correction_inventory_artifact_id",
        "cutoff_filter_recipe_id",
    ):
        _require_production_identifier(vintage[field], field)
    for field in (
        "evidence_epoch_semantic_sha256",
        "evidence_epoch_artifact_sha256",
        "correction_inventory_content_sha256",
        "correction_inventory_artifact_sha256",
        "cutoff_filter_recipe_sha256",
    ):
        _require_sha256(vintage[field], field)
    capture = _require_instant(
        vintage["source_snapshot_capture_instant_utc"], "source snapshot capture"
    )
    recorded = _require_instant(
        vintage["evidence_recorded_instant_utc"], "vintage evidence recording"
    )
    if recorded < capture or any(instant > recorded for instant in entitlement_instants):
        raise PowerCalibrationInputManifestError("evidence chronology is impossible")
    first_open = _require_instant(
        vintage["first_test_session_open_utc"], "first test session open"
    )
    max_included = _require_instant(
        vintage["max_included_availability_or_correction_instant_utc"],
        "maximum included availability or correction instant",
    )
    cutoff_end = datetime.fromisoformat("2020-01-31T00:00:00.000000+00:00")
    if first_open != datetime.fromisoformat(
        FIRST_TEST_SESSION_OPEN_UTC[:-1] + "+00:00"
    ) or capture < cutoff_end or max_included >= cutoff_end:
        raise PowerCalibrationInputManifestError(
            "vintage timing crosses the frozen information cutoff"
        )
    method = vintage["vintage_method"]
    if method not in VINTAGE_METHODS:
        raise PowerCalibrationInputManifestError("vintage method is unsupported")
    attestation = _require_keys(
        vintage["external_vintage_attestation"],
        ATTESTATION_FIELDS,
        "external vintage attestation",
    )
    if method == "contemporaneous_immutable_snapshot" and (
        not capture < first_open
        or any(attestation[field] is not None for field in ATTESTATION_FIELDS)
    ):
        raise PowerCalibrationInputManifestError(
            "contemporaneous vintage evidence is outside its frozen window"
        )

    snapshots = vintage["source_snapshot_bindings"]
    if (
        type(snapshots) is not list
        or len(snapshots) != len(entitlements)
        or len(snapshots) > MAX_ENTITLEMENT_AUDITS
    ):
        raise PowerCalibrationInputManifestError(
            "vintage source snapshot inventory is not exact"
        )
    snapshot_ids: list[str] = []
    snapshot_source_roles: set[str] = set()
    source_assumptions_by_id = {
        item["binding_id"]: item for item in source_assumptions
    }
    for index, snapshot in enumerate(snapshots):
        snapshot = _require_keys(
            snapshot, SOURCE_SNAPSHOT_FIELDS, f"source snapshot {index}"
        )
        source_roles = _require_external_source_roles(
            snapshot["source_roles"], f"source snapshot {index} source roles"
        )
        artifact_id = _require_production_identifier(
            snapshot["artifact_id"], f"source snapshot {index} ID"
        )
        _require_production_identifier(
            snapshot["schema_id"], f"source snapshot {index} schema"
        )
        _require_sha256(
            snapshot["content_sha256"], f"source snapshot {index} content hash"
        )
        _require_sha256(
            snapshot["artifact_sha256"], f"source snapshot {index} artifact hash"
        )
        audit_id = _require_production_identifier(
            snapshot["data_entitlement_audit_id"],
            f"source snapshot {index} audit",
        )
        right_id = _require_production_identifier(
            snapshot["rights_binding_id"], f"source snapshot {index} right"
        )
        audit = audits_by_id.get(audit_id)
        source_assumption = source_assumptions_by_id.get(right_id)
        if (
            audit is None
            or source_assumption is None
            or tuple(audit["source_roles"]) != source_roles
            or audit["source_artifact_id"] != artifact_id
            or audit["source_content_sha256"] != snapshot["content_sha256"]
            or audit["source_artifact_sha256"] != snapshot["artifact_sha256"]
            or source_assumption["source_artifact_id"] != artifact_id
            or source_assumption["data_entitlement_audit_id"] != audit_id
            or tuple(source_assumption["applies_to_input_roles"])
            != _input_roles_for_external_sources(source_roles)
        ):
            raise PowerCalibrationInputManifestError(
                "source snapshot is not tied to its exact audit and source right"
            )
        snapshot_ids.append(artifact_id)
        snapshot_source_roles.update(source_roles)
    if (
        tuple(snapshot_ids) != tuple(sorted(set(snapshot_ids)))
        or snapshot_source_roles != set(REQUIRED_EXTERNAL_SOURCE_ROLE_INPUTS)
        or {item["data_entitlement_audit_id"] for item in snapshots}
        != set(audit_ids)
        or {item["rights_binding_id"] for item in snapshots}
        != set(source_assumption_ids)
    ):
        raise PowerCalibrationInputManifestError(
            "source snapshots must be sorted, unique, and evidence-complete"
        )
    if (
        vintage["calibration_information_cutoff_session"]
        != CALIBRATION_LAST_OUTCOME_SESSION
        or vintage["first_excluded_session"] != FIRST_TEST_SESSION
        or vintage["correction_inventory_complete"] is not True
        or _require_int(
            vintage["included_post_cutoff_correction_count"],
            "included post-cutoff correction count",
        )
        != 0
        or vintage["immutable_snapshot"] is not True
    ):
        raise PowerCalibrationInputManifestError(
            "vintage evidence does not prove the frozen cutoff"
        )
    _require_int(
        vintage["correction_inventory_record_count"],
        "correction inventory record count",
    )
    if method == "externally_attested_as_of_reconstruction":
        if attestation["attestation_schema"] != VINTAGE_ATTESTATION_SCHEMA:
            raise PowerCalibrationInputManifestError(
                "external vintage attestation schema changed"
            )
        _require_production_identifier(
            attestation["attestation_id"], "external attestation ID"
        )
        for field in (
            "attestation_content_sha256",
            "attestation_artifact_sha256",
            "source_snapshot_inventory_sha256",
            "correction_inventory_content_sha256",
            "correction_inventory_artifact_sha256",
            "cutoff_filter_recipe_sha256",
        ):
            _require_sha256(attestation[field], field)
        _require_production_identifier(
            attestation["correction_inventory_artifact_id"],
            "attested correction inventory ID",
        )
        _require_production_identifier(
            attestation["cutoff_filter_recipe_id"],
            "attested cutoff recipe ID",
        )
        attested_cutoff = _require_instant(
            attestation["attested_information_cutoff_exclusive_utc"],
            "attested information cutoff",
        )
        if (
            attested_cutoff != cutoff_end
            or attestation["source_snapshot_inventory_sha256"]
            != hashlib.sha256(_canonical(snapshots)).hexdigest()
            or attestation["correction_inventory_artifact_id"]
            != vintage["correction_inventory_artifact_id"]
            or attestation["correction_inventory_content_sha256"]
            != vintage["correction_inventory_content_sha256"]
            or attestation["correction_inventory_artifact_sha256"]
            != vintage["correction_inventory_artifact_sha256"]
            or attestation["cutoff_filter_recipe_id"]
            != vintage["cutoff_filter_recipe_id"]
            or attestation["cutoff_filter_recipe_sha256"]
            != vintage["cutoff_filter_recipe_sha256"]
        ):
            raise PowerCalibrationInputManifestError(
                "external vintage attestation does not bind the exact reconstruction metadata"
            )
    _require_exact(value["capabilities"], dict(CAPABILITIES), "bundle capabilities")
    return {
        "raw": value,
        "audit_ids": tuple(audit_ids),
        "entitlements": tuple(entitlements),
        "rights": rights,
        "source_assumptions": tuple(source_assumptions),
        "vintage": vintage,
    }


def _validate_rights(
    raw: object,
    *,
    bundle_id: str,
    bundle_hash: str,
    bundle_artifact_sha256: str,
    source_assumptions: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    if (
        type(raw) is not list
        or len(raw) != len(source_assumptions)
        or len(raw) > MAX_RIGHTS_BINDINGS
    ):
        raise PowerCalibrationInputManifestError(
            "production rights bindings are not evidence-complete"
        )
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    covered: set[str] = set()
    assumptions_by_id = {
        item["binding_id"]: item for item in source_assumptions
    }
    try:
        for index, item in enumerate(raw):
            item = _require_keys(item, RIGHTS_FIELDS, f"rights binding {index}")
            binding_id = _require_production_identifier(
                item["binding_id"], f"rights binding {index} ID"
            )
            if binding_id in seen:
                raise PowerCalibrationInputManifestError("rights IDs are duplicated")
            seen.add(binding_id)
            assumption = assumptions_by_id.get(binding_id)
            if (
                assumption is None
                or item["receipt_id"] != bundle_id
                or item["receipt_schema"] != RIGHTS_RECEIPT_SCHEMA
                or item["receipt_content_sha256"] != bundle_hash
                or item["receipt_artifact_sha256"] != bundle_artifact_sha256
                or item["data_entitlement_audit_id"]
                != assumption["data_entitlement_audit_id"]
                or item["processing_scope_id"]
                != assumption["processing_scope_id"]
                or item["applies_to_input_roles"]
                != assumption["applies_to_input_roles"]
            ):
                raise PowerCalibrationInputManifestError(
                    "rights binding is not tied to the exact B2 evidence assumption"
                )
            roles = item["applies_to_input_roles"]
            if (
                type(roles) is not list
                or not roles
                or len(roles) > len(INPUT_ROLES)
                or any(type(role) is not str for role in roles)
            ):
                raise PowerCalibrationInputManifestError("rights role inventory is empty")
            role_set = set(roles)
            if (
                tuple(roles) != tuple(role for role in INPUT_ROLES if role in role_set)
                or len(roles) != len(role_set)
            ):
                raise PowerCalibrationInputManifestError("rights role inventory changed")
            covered.update(roles)
            result.append(item)
    except PowerCalibrationInputSchemaError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc
    if (
        tuple(item["binding_id"] for item in result) != tuple(sorted(seen))
        or seen != set(assumptions_by_id)
    ):
        raise PowerCalibrationInputManifestError("rights bindings must be ID-sorted")
    if covered != set(INPUT_ROLES):
        raise PowerCalibrationInputManifestError("rights do not cover both roles")
    return tuple(result)


def _validate_inputs(
    raw: object,
    *,
    sessions: tuple[str, ...],
    rights: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    if type(raw) is not list or len(raw) != len(INPUT_ROLES):
        raise PowerCalibrationInputManifestError("input artifact inventory is not exact")
    rights_by_id = {item["binding_id"]: item for item in rights}
    result: list[dict[str, Any]] = []
    try:
        for index, (item, role) in enumerate(zip(raw, INPUT_ROLES, strict=True)):
            fields = BETA_INPUT_FIELDS if role == INPUT_ROLES[0] else COMPONENT_INPUT_FIELDS
            item = _require_keys(item, fields, f"input artifact {index}")
            if item["role"] != role or item["artifact_schema"] != INPUT_SCHEMAS[role]:
                raise PowerCalibrationInputManifestError("input role or schema changed")
            _require_production_identifier(item["artifact_id"], f"{role} artifact ID")
            _require_sha256(item["content_sha256"], f"{role} content hash")
            _require_sha256(item["artifact_sha256"], f"{role} artifact hash")
            _require_int(item["byte_count"], f"{role} byte count", minimum=1)
            if (
                _require_int(item["record_count"], f"{role} record count")
                != CALIBRATION_SESSION_COUNT
                or item["session_key_field"] != SESSION_KEY_FIELD
                or item["session_axis_sha256"] != CALIBRATION_AXIS_SHA256
            ):
                raise PowerCalibrationInputManifestError(f"{role} session binding changed")
            binding_ids = item["rights_binding_ids"]
            expected_binding_ids = tuple(
                sorted(
                    binding_id
                    for binding_id, binding in rights_by_id.items()
                    if role in binding["applies_to_input_roles"]
                )
            )
            if (
                type(binding_ids) is not list
                or not binding_ids
                or len(binding_ids) > MAX_RIGHTS_BINDINGS
                or any(type(binding_id) is not str for binding_id in binding_ids)
                or tuple(binding_ids) != tuple(sorted(set(binding_ids)))
                or tuple(binding_ids) != expected_binding_ids
                or any(
                    binding_id not in rights_by_id
                    or role not in rights_by_id[binding_id]["applies_to_input_roles"]
                    for binding_id in binding_ids
                )
            ):
                raise PowerCalibrationInputManifestError(f"{role} rights binding changed")
            _require_production_identifier(item["lineage_node_id"], f"{role} lineage node")
            if role == INPUT_ROLES[0]:
                inventory = item["session_state_inventory"]
                if type(inventory) is not list or len(inventory) != len(sessions):
                    raise PowerCalibrationInputManifestError("beta state inventory is incomplete")
                states: list[str] = []
                for position, (record, session) in enumerate(zip(inventory, sessions, strict=True)):
                    record = _require_keys(record, ("session", "state"), f"beta state {position}")
                    if (
                        record["session"] != session
                        or type(record["state"]) is not str
                        or record["state"] not in {"valid", "missing", "refused"}
                    ):
                        raise PowerCalibrationInputManifestError("beta state inventory changed")
                    states.append(record["state"])
                census = {state: states.count(state) for state in ("valid", "missing", "refused")}
                if (
                    _require_int(item["valid_beta_date_count"], "valid beta count") != census["valid"]
                    or _require_int(item["missing_beta_date_count"], "missing beta count") != census["missing"]
                    or _require_int(item["refused_beta_date_count"], "refused beta count") != census["refused"]
                    or item["state_census_sha256"] != hashlib.sha256(_canonical(inventory)).hexdigest()
                ):
                    raise PowerCalibrationInputManifestError("beta state census changed")
            else:
                inventory = item["session_count_inventory"]
                if type(inventory) is not list or len(inventory) != len(sessions):
                    raise PowerCalibrationInputManifestError("component count inventory is incomplete")
                for position, (record, session) in enumerate(zip(inventory, sessions, strict=True)):
                    record = _require_keys(
                        record,
                        ("session", "connected_component_count"),
                        f"component count {position}",
                    )
                    if record["session"] != session:
                        raise PowerCalibrationInputManifestError("component count session changed")
                    _require_int(record["connected_component_count"], f"component count {position}")
                if (
                    item["component_count_census_sha256"]
                    != hashlib.sha256(_canonical(inventory)).hexdigest()
                    or _require_int(
                        item["component_count_census_session_count"],
                        "component count census session count",
                    )
                    != CALIBRATION_SESSION_COUNT
                    or _require_int(item["missing_session_count"], "missing session count") != 0
                ):
                    raise PowerCalibrationInputManifestError("component count census changed")
            result.append(item)
    except PowerCalibrationInputSchemaError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc
    if len({item["artifact_id"] for item in result}) != len(result):
        raise PowerCalibrationInputManifestError("input artifact IDs are duplicated")
    if {binding for item in result for binding in item["rights_binding_ids"]} != set(rights_by_id):
        raise PowerCalibrationInputManifestError("rights bindings contain an orphan")
    return tuple(result)


def _assert_acyclic(graph: Mapping[str, Iterable[str]]) -> None:
    visiting: set[str] = set()
    complete: set[str] = set()
    for start in graph:
        stack: list[tuple[str, bool]] = [(start, False)]
        while stack:
            node, exiting = stack.pop()
            if exiting:
                visiting.discard(node)
                complete.add(node)
                continue
            if node in complete:
                continue
            if node in visiting:
                raise PowerCalibrationInputManifestError("lineage contains a cycle")
            visiting.add(node)
            stack.append((node, True))
            for parent in reversed(tuple(graph[node])):
                if parent in visiting:
                    raise PowerCalibrationInputManifestError(
                        "lineage contains a cycle"
                    )
                if parent not in complete:
                    stack.append((parent, False))


def _validate_lineage(
    raw: object,
    *,
    evidence_epoch_id: str,
    inputs: tuple[dict[str, Any], ...],
    rights: tuple[dict[str, Any], ...],
    source_snapshots: list[dict[str, Any]],
) -> int:
    try:
        value = _require_keys(raw, LINEAGE_FIELDS, "producing lineage")
        _require_git_object(value["producing_commit"], "producing commit")
        _require_git_object(value["producing_tree"], "producing tree")
        _require_sha256(value["producer_code_sha256"], "producer code hash")
        _require_production_identifier(value["build_recipe_id"], "build recipe")
        _require_sha256(value["build_recipe_sha256"], "build recipe hash")
        _require_sha256(value["config_sha256"], "config hash")
        nodes = value["ordered_nodes"]
        if type(nodes) is not list or not nodes or len(nodes) > MAX_LINEAGE_NODES:
            raise PowerCalibrationInputManifestError("lineage nodes are empty")
        known_rights = {item["binding_id"] for item in rights}
        terminal_roles = {item["lineage_node_id"]: item["role"] for item in inputs}
        terminals = set(terminal_roles)
        if len(terminals) != len(inputs):
            raise PowerCalibrationInputManifestError("terminal lineage is not exact")
        graph: dict[str, tuple[str, ...]] = {}
        records: dict[str, dict[str, Any]] = {}
        artifact_ids: set[str] = set()
        roots: set[str] = set()
        for index, item in enumerate(nodes):
            item = _require_keys(item, LINEAGE_NODE_FIELDS, f"lineage node {index}")
            node_id = _require_production_identifier(item["node_id"], f"lineage node {index} ID")
            if node_id in graph:
                raise PowerCalibrationInputManifestError("lineage node IDs are duplicated")
            role = _require_identifier(item["role"], f"lineage node {index} role")
            if role not in LINEAGE_ROLES:
                raise PowerCalibrationInputManifestError("lineage role is not closed")
            artifact_id = _require_production_identifier(
                item["artifact_id"], f"lineage node {index} artifact"
            )
            if artifact_id in artifact_ids:
                raise PowerCalibrationInputManifestError("lineage artifact IDs are duplicated")
            artifact_ids.add(artifact_id)
            _require_identifier(item["schema_id"], f"lineage node {index} schema")
            _require_sha256(item["content_sha256"], f"lineage node {index} content hash")
            _require_sha256(item["artifact_sha256"], f"lineage node {index} artifact hash")
            if item["evidence_epoch_id"] != evidence_epoch_id:
                raise PowerCalibrationInputManifestError("lineage evidence epoch changed")
            parents = item["parent_node_ids"]
            rights_ids = item["rights_binding_ids"]
            if (
                type(parents) is not list
                or type(rights_ids) is not list
                or len(parents) > MAX_LINEAGE_NODES
                or len(rights_ids) > MAX_RIGHTS_BINDINGS
                or any(type(parent) is not str for parent in parents)
                or any(type(binding_id) is not str for binding_id in rights_ids)
                or tuple(parents) != tuple(dict.fromkeys(parents))
                or any(parent not in graph for parent in parents)
                or tuple(rights_ids) != tuple(sorted(set(rights_ids)))
                or any(binding_id not in known_rights for binding_id in rights_ids)
            ):
                raise PowerCalibrationInputManifestError("lineage edge or rights inventory changed")
            if not parents:
                if role != "source_artifact" or node_id in terminals or not rights_ids:
                    raise PowerCalibrationInputManifestError("lineage root is not rights-bound source metadata")
                roots.add(node_id)
            elif node_id in terminals:
                if role != terminal_roles[node_id]:
                    raise PowerCalibrationInputManifestError("terminal role changed")
            elif role != "transformation":
                raise PowerCalibrationInputManifestError("nonterminal lineage role changed")
            graph[node_id] = tuple(parents)
            records[node_id] = item
        _assert_acyclic(graph)
        if not roots or any(node not in graph or not graph[node] for node in terminals):
            raise PowerCalibrationInputManifestError("terminal ancestry is incomplete")
        expected_source_artifacts = {
            item["artifact_id"]: (
                item["schema_id"],
                item["content_sha256"],
                item["artifact_sha256"],
                (item["rights_binding_id"],),
            )
            for item in source_snapshots
        }
        observed_source_artifacts = {
            records[node_id]["artifact_id"]: (
                records[node_id]["schema_id"],
                records[node_id]["content_sha256"],
                records[node_id]["artifact_sha256"],
                tuple(records[node_id]["rights_binding_ids"]),
            )
            for node_id in roots
        }
        if observed_source_artifacts != expected_source_artifacts:
            raise PowerCalibrationInputManifestError(
                "lineage roots do not exactly bind the vintage source snapshots"
            )
        if any(terminal in parents for parents in graph.values() for terminal in terminals):
            raise PowerCalibrationInputManifestError("terminal lineage node has a child")
        inherited_rights: dict[str, tuple[str, ...]] = {}
        for item in nodes:
            node_id = item["node_id"]
            parents = graph[node_id]
            expected_rights = (
                tuple(item["rights_binding_ids"])
                if not parents
                else tuple(
                    sorted(
                        {
                            binding_id
                            for parent in parents
                            for binding_id in inherited_rights[parent]
                        }
                    )
                )
            )
            if tuple(item["rights_binding_ids"]) != expected_rights:
                raise PowerCalibrationInputManifestError(
                    "derived lineage rights do not equal inherited source rights"
                )
            inherited_rights[node_id] = expected_rights
        for input_item in inputs:
            node = records[input_item["lineage_node_id"]]
            if (
                node["role"] != input_item["role"]
                or node["artifact_id"] != input_item["artifact_id"]
                or node["schema_id"] != input_item["artifact_schema"]
                or node["content_sha256"] != input_item["content_sha256"]
                or node["artifact_sha256"] != input_item["artifact_sha256"]
                or tuple(node["rights_binding_ids"])
                != tuple(input_item["rights_binding_ids"])
            ):
                raise PowerCalibrationInputManifestError("terminal does not bind its input metadata")
        reachable = set(terminals)
        frontier = list(terminals)
        while frontier:
            node = frontier.pop()
            for parent in graph[node]:
                if parent not in reachable:
                    reachable.add(parent)
                    frontier.append(parent)
        if reachable != set(graph):
            raise PowerCalibrationInputManifestError("lineage contains an orphan")
        if value["lineage_sha256"] != hashlib.sha256(_canonical(nodes)).hexdigest():
            raise PowerCalibrationInputManifestError("lineage hash changed")
    except PowerCalibrationInputSchemaError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc
    return len(nodes)


def _validate_manifest(
    raw: object,
    *,
    admission: PowerCalibrationManifestAdmission,
    evidence: dict[str, Any],
    evidence_artifact_sha256: str,
) -> dict[str, Any]:
    try:
        value = _require_keys(raw, MANIFEST_ROOT_FIELDS, "production manifest candidate")
    except PowerCalibrationInputSchemaError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc
    if (
        value["schema"] != MANIFEST_SCHEMA
        or value["manifest_mode"] != PRODUCTION_MODE
        or value["status"] != PRODUCTION_CANDIDATE_STATUS
        or value["authority"] != PRODUCTION_CANDIDATE_AUTHORITY
    ):
        raise PowerCalibrationInputManifestError("production manifest candidate scope changed")
    _require_identity(
        value,
        id_field="manifest_id",
        hash_field="manifest_hash",
        prefix=MANIFEST_ID_PREFIX,
        name="production manifest candidate",
    )
    try:
        _require_exact(
            value["schema_contract_binding"],
            _binding(
                artifact_id=B1_SCHEMA_ID,
                content_sha256=B1_SCHEMA_HASH,
                artifact_sha256=SCHEMA_CONTRACT_ARTIFACT_SHA256,
            ),
            "manifest B1 binding",
        )
        _require_exact(
            value["power_protocol_binding"],
            _binding(
                artifact_id=POWER_PROTOCOL_ID,
                content_sha256=POWER_PROTOCOL_HASH,
                artifact_sha256=POWER_PROTOCOL_ARTIFACT_SHA256,
            ),
            "manifest power protocol binding",
        )
        if value["evaluation_id"] != EVALUATION_ID:
            raise PowerCalibrationInputManifestError("evaluation identity changed")
        fold = _require_keys(value["calibration_fold"], CALIBRATION_FOLD_FIELDS, "calibration fold")
        _require_exact(
            fold,
            {
                "fold_id": CALIBRATION_FOLD_ID,
                "structural_fold_sha256": CALIBRATION_FOLD_HASH,
                "horizon_sessions": 20,
                "validation_start_inclusive": CALIBRATION_START,
                "validation_end_exclusive": CALIBRATION_END_EXCLUSIVE,
                "last_included_decision_session": CALIBRATION_LAST_SESSION,
                "last_included_h20_outcome_session": CALIBRATION_LAST_OUTCOME_SESSION,
                "first_test_session": FIRST_TEST_SESSION,
            },
            "calibration fold",
        )
        epoch = _require_keys(value["evidence_epoch_binding"], EVIDENCE_EPOCH_FIELDS, "evidence epoch")
        for field in ("evidence_epoch_id", "artifact_id"):
            _require_production_identifier(epoch[field], field)
        for field in ("semantic_sha256", "artifact_sha256"):
            _require_sha256(epoch[field], field)
        _require_instant(epoch["capture_instant_utc"], "manifest capture instant")
        vintage = evidence["vintage"]
        if (
            epoch["evidence_epoch_id"] != vintage["evidence_epoch_id"]
            or epoch["artifact_id"] != vintage["evidence_epoch_artifact_id"]
            or epoch["semantic_sha256"] != vintage["evidence_epoch_semantic_sha256"]
            or epoch["artifact_sha256"] != vintage["evidence_epoch_artifact_sha256"]
            or epoch["capture_instant_utc"] != vintage["source_snapshot_capture_instant_utc"]
            or epoch["calibration_information_cutoff_session"] != CALIBRATION_LAST_OUTCOME_SESSION
            or epoch["first_excluded_session"] != FIRST_TEST_SESSION
            or epoch["post_cutoff_corrections_included"] is not False
        ):
            raise PowerCalibrationInputManifestError("manifest vintage binding changed")
        axis = _require_keys(value["complete_session_axis"], SESSION_AXIS_FIELDS, "session axis")
        sessions = admission.calibration_session_axis
        if (
            axis["exchange"] != EXCHANGE
            or axis["key_field"] != SESSION_KEY_FIELD
            or axis["key_format"] != SESSION_KEY_FORMAT
            or type(axis["ordered_session_keys"]) is not list
            or tuple(axis["ordered_session_keys"]) != sessions
            or len(set(axis["ordered_session_keys"])) != len(sessions)
            or _require_int(axis["session_count"], "session count") != CALIBRATION_SESSION_COUNT
            or axis["session_axis_sha256"] != CALIBRATION_AXIS_SHA256
            or axis["first_session"] != CALIBRATION_START
            or axis["last_session"] != CALIBRATION_LAST_SESSION
            or hashlib.sha256(_canonical(axis["ordered_session_keys"])).hexdigest()
            != CALIBRATION_AXIS_SHA256
        ):
            raise PowerCalibrationInputManifestError("session axis changed")
    except PowerCalibrationInputSchemaError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc

    evidence_raw = evidence["raw"]
    rights = _validate_rights(
        value["rights_bindings"],
        bundle_id=evidence_raw["bundle_id"],
        bundle_hash=evidence_raw["bundle_hash"],
        bundle_artifact_sha256=evidence_artifact_sha256,
        source_assumptions=evidence["source_assumptions"],
    )
    inputs = _validate_inputs(value["input_artifacts"], sessions=sessions, rights=rights)
    rights_input_bindings = evidence["rights"]["candidate_input_metadata_bindings"]
    for input_item, rights_input in zip(inputs, rights_input_bindings, strict=True):
        if (
            rights_input["role"] != input_item["role"]
            or rights_input["artifact_id"] != input_item["artifact_id"]
            or rights_input["content_sha256"] != input_item["content_sha256"]
            or rights_input["artifact_sha256"] != input_item["artifact_sha256"]
        ):
            raise PowerCalibrationInputManifestError(
                "rights evidence does not bind the exact input metadata"
            )
    lineage_count = _validate_lineage(
        value["producing_lineage"],
        evidence_epoch_id=epoch["evidence_epoch_id"],
        inputs=inputs,
        rights=rights,
        source_snapshots=evidence["vintage"]["source_snapshot_bindings"],
    )
    try:
        counts = _require_keys(value["manifest_counts"], MANIFEST_COUNT_FIELDS, "manifest counts")
        expected_counts = {
            "input_artifact_count": len(inputs),
            "rights_binding_count": len(rights),
            "lineage_node_count": lineage_count,
            "session_key_count": len(sessions),
        }
        if any(_require_int(counts[name], name) != expected for name, expected in expected_counts.items()):
            raise PowerCalibrationInputManifestError("manifest counts do not close")
        _require_exact(
            value["external_authorities"],
            dict(MANIFEST_EXTERNAL_AUTHORITIES),
            "external authorities",
        )
        _require_exact(value["capabilities"], dict(CAPABILITIES), "manifest capabilities")
    except PowerCalibrationInputSchemaError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc
    return {
        "raw": value,
        "evidence_epoch_id": epoch["evidence_epoch_id"],
        "audit_ids": evidence["audit_ids"],
    }


def _candidate_fingerprint(
    value: ProductionCalibrationInputManifestCandidate,
) -> tuple[object, ...]:
    string_values = (
        value.manifest_id,
        value.manifest_content_sha256,
        value.manifest_artifact_sha256,
        value.evidence_bundle_id,
        value.evidence_bundle_content_sha256,
        value.evidence_bundle_artifact_sha256,
        value.evidence_epoch_id,
        value.massive_benzinga_working_assumption_id,
    )
    if any(type(item) is not str for item in string_values) or type(
        value.session_count
    ) is not int:
        raise PowerCalibrationInputManifestError("authority state is noncanonical")
    return (
        *(_fingerprint(item) for item in string_values[:7]),
        _fingerprint(value.data_entitlement_audit_ids),
        _fingerprint(string_values[7]),
        _fingerprint(value.session_count),
        _fingerprint(value.input_roles),
        _fingerprint(value.definition),
    )


def load_production_calibration_input_manifest_candidate(
    admission: PowerCalibrationManifestAdmission,
    manifest_path: Path,
    *,
    evidence_bundle_path: Path,
) -> ProductionCalibrationInputManifestCandidate:
    """Load only manifest/evidence metadata; never resolve or open input artifacts."""
    require_loaded_power_calibration_manifest_admission(admission)
    try:
        evidence_path, evidence_payload = _read_stable_regular(
            evidence_bundle_path, "B2 evidence bundle"
        )
        evidence_raw = _parse_artifact(evidence_payload, "B2 evidence bundle")
        manifest_resolved, manifest_payload = _read_stable_regular(
            manifest_path, "production manifest candidate"
        )
        manifest_raw = _parse_artifact(manifest_payload, "production manifest candidate")
    except PowerCalibrationInputSchemaError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc
    evidence = _validate_evidence_bundle(evidence_raw)
    evidence_artifact_sha256 = hashlib.sha256(evidence_payload).hexdigest()
    manifest = _validate_manifest(
        manifest_raw,
        admission=admission,
        evidence=evidence,
        evidence_artifact_sha256=evidence_artifact_sha256,
    )
    try:
        _revalidate(evidence_path, evidence_payload, "B2 evidence bundle")
        _revalidate(manifest_resolved, manifest_payload, "production manifest candidate")
        require_loaded_power_calibration_manifest_admission(admission)
        _revalidate(evidence_path, evidence_payload, "B2 evidence bundle")
        _revalidate(manifest_resolved, manifest_payload, "production manifest candidate")
    except PowerCalibrationInputSchemaError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc

    value = object.__new__(ProductionCalibrationInputManifestCandidate)
    for name, item in {
        "manifest_id": manifest_raw["manifest_id"],
        "manifest_content_sha256": manifest_raw["manifest_hash"],
        "manifest_artifact_sha256": hashlib.sha256(manifest_payload).hexdigest(),
        "evidence_bundle_id": evidence_raw["bundle_id"],
        "evidence_bundle_content_sha256": evidence_raw["bundle_hash"],
        "evidence_bundle_artifact_sha256": evidence_artifact_sha256,
        "evidence_epoch_id": manifest["evidence_epoch_id"],
        "data_entitlement_audit_ids": manifest["audit_ids"],
        "massive_benzinga_working_assumption_id": OWNER_DECISION_ID,
        "session_count": CALIBRATION_SESSION_COUNT,
        "input_roles": INPUT_ROLES,
        "definition": _freeze(
            {
                "manifest": manifest_raw,
                "evidence_bundle": evidence_raw,
                "capabilities": dict(CAPABILITIES),
            }
        ),
        "_authority": _LOADED_CANDIDATE_AUTHORITY,
    }.items():
        object.__setattr__(value, name, item)
    container_authority = capture_frozen_container_authority(
        _container_roots(value, _CANDIDATE_CONTAINER_FIELDS)
    )
    fingerprint = _candidate_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_candidate(key, ref)
    )
    with _CANDIDATE_AUTHORITIES_LOCK:
        _CANDIDATE_AUTHORITIES[identity] = (
            reference,
            manifest_resolved,
            manifest_payload,
            evidence_path,
            evidence_payload,
            admission,
            fingerprint,
            container_authority,
        )
    return value


def require_loaded_production_calibration_input_manifest_candidate(
    candidate: ProductionCalibrationInputManifestCandidate,
) -> ProductionCalibrationInputManifestCandidate:
    if (
        type(candidate) is not ProductionCalibrationInputManifestCandidate
        or getattr(candidate, "_authority", None) is not _LOADED_CANDIDATE_AUTHORITY
    ):
        raise PowerCalibrationInputManifestError(
            "production manifest candidate is not loader-authenticated"
        )
    with _CANDIDATE_AUTHORITIES_LOCK:
        authority = _CANDIDATE_AUTHORITIES.get(id(candidate))
    if authority is None or authority[0]() is not candidate:
        raise PowerCalibrationInputManifestError("manifest candidate authority is absent")
    if not _container_roots_are_current(
        candidate, _CANDIDATE_CONTAINER_FIELDS, authority[7]
    ):
        raise PowerCalibrationInputManifestError(
            "manifest candidate container roots changed"
        )
    try:
        current_fingerprint = _candidate_fingerprint(candidate)
    except AttributeError as exc:
        raise PowerCalibrationInputManifestError(
            "manifest candidate changed"
        ) from exc
    if current_fingerprint != authority[6]:
        raise PowerCalibrationInputManifestError("manifest candidate changed")
    try:
        _revalidate(authority[1], authority[2], "production manifest candidate")
        _revalidate(authority[3], authority[4], "B2 evidence bundle")
        require_loaded_power_calibration_manifest_admission(authority[5])
        _revalidate(authority[1], authority[2], "production manifest candidate")
        _revalidate(authority[3], authority[4], "B2 evidence bundle")
    except PowerCalibrationInputSchemaError as exc:
        raise PowerCalibrationInputManifestError(str(exc)) from exc
    return candidate


def render_expected_power_calibration_manifest_admission() -> str:
    """Render the one canonical checked-in ARV2-4D-B2 contract."""
    return _render(_admission_document()).decode("utf-8")
