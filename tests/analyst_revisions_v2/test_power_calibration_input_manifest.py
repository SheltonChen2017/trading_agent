from __future__ import annotations

import ast
import copy
import dataclasses
import gc
import hashlib
import inspect
import json
import os
import pickle
import shutil
import textwrap
import weakref
from pathlib import Path
from types import MappingProxyType

import pytest

import research.analyst_revisions_v2.artifact_io as artifact_io_module
import research.analyst_revisions_v2.power_calibration_input_manifest as module
from research.analyst_revisions_v2.four_family_multiplicity import (
    FourFamilyMultiplicityOverlay,
    load_four_family_multiplicity_overlay,
)
from research.analyst_revisions_v2.power_calibration_input_manifest import (
    ADMISSION_CONTRACT_ARTIFACT_SHA256,
    B1_SCHEMA_HASH,
    B1_SCHEMA_ID,
    EVIDENCE_BUNDLE_AUTHORITY,
    EVIDENCE_BUNDLE_ID_PREFIX,
    EVIDENCE_BUNDLE_SCHEMA,
    EVIDENCE_BUNDLE_STATUS,
    FIRST_TEST_SESSION_OPEN_UTC,
    FOUR_FAMILY_OVERLAY_HASH,
    FOUR_FAMILY_OVERLAY_ID,
    MASSIVE_BENZINGA_ASSUMPTION_SCOPE_ID,
    NO_SOURCE_PROCESSING_AUTHORITY_SCOPE_ID,
    OWNER_DECISION_ID,
    OWNER_DECISION_SCOPE,
    OWNER_DECISION_SOURCE,
    OWNER_RIGHTS_BASIS,
    OWNER_ASSUMPTION_PURPOSE,
    PRODUCTION_CANDIDATE_AUTHORITY,
    PRODUCTION_CANDIDATE_STATUS,
    REQUIRED_EXTERNAL_SOURCE_ROLE_INPUTS,
    REPRESENTATION_SCOPES,
    RIGHTS_RECEIPT_SCHEMA,
    PowerCalibrationInputManifestError,
    PowerCalibrationManifestAdmission,
    ProductionCalibrationInputManifestCandidate,
    load_power_calibration_manifest_admission,
    load_production_calibration_input_manifest_candidate,
    render_expected_power_calibration_manifest_admission,
    require_loaded_power_calibration_manifest_admission,
    require_loaded_production_calibration_input_manifest_candidate,
)
from research.analyst_revisions_v2.power_calibration_input_schema import (
    CALIBRATION_AXIS_SHA256,
    CALIBRATION_END_EXCLUSIVE,
    CALIBRATION_FOLD_HASH,
    CALIBRATION_FOLD_ID,
    CALIBRATION_LAST_OUTCOME_SESSION,
    CALIBRATION_LAST_SESSION,
    CALIBRATION_SESSION_COUNT,
    CALIBRATION_START,
    CAPABILITIES,
    EVALUATION_ID,
    FIRST_TEST_SESSION,
    INPUT_ROLES,
    INPUT_SCHEMAS,
    MANIFEST_EXTERNAL_AUTHORITIES,
    MANIFEST_ID_PREFIX,
    MANIFEST_SCHEMA,
    POWER_PROTOCOL_ARTIFACT_SHA256,
    POWER_PROTOCOL_HASH,
    POWER_PROTOCOL_ID,
    PRODUCTION_MODE,
    SCHEMA_CONTRACT_ARTIFACT_SHA256,
    PowerCalibrationInputSchema,
    load_power_calibration_input_schema,
)
from research.analyst_revisions_v2.power_calibration_protocol import (
    load_power_calibration_protocol,
)


SPEC_ROOT = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "analyst_revisions_v2"
    / "specs"
)
ADMISSION_FILENAME = (
    "arv2_stock_power_calibration_production_manifest_admission.structural.json"
)
PARENT_FILENAMES = {
    "schema": "arv2_stock_power_calibration_input_manifest_schema.structural.json",
    "protocol": "arv2_stock_power_calibration_protocol.structural.json",
    "map": "arv2_global_rating_map.structural.json",
    "matched": "arv2_global_matched_comparison.structural.json",
    "successor": "arv2_stock_historical_successor.structural.json",
    "stock": "arv2_stock_historical.structural.json",
    "folds": "arv2_stock_walk_forward_folds.structural.json",
    "plan": "arv2_qc_first.draft.json",
    "base": "arv2_round0.draft.json",
    "overlay": "arv2_four_family_multiplicity.structural.json",
    "look_authority": "permanent_look_authority.json",
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _render(value: object) -> bytes:
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


def _content_identity(
    raw: dict[str, object], *, id_field: str, hash_field: str, prefix: str
) -> None:
    raw[id_field] = None
    raw[hash_field] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()
    raw[hash_field] = digest
    raw[id_field] = prefix + digest[:16]


def _load_input_schema() -> PowerCalibrationInputSchema:
    protocol = load_power_calibration_protocol(
        SPEC_ROOT / PARENT_FILENAMES["protocol"],
        map_path=SPEC_ROOT / PARENT_FILENAMES["map"],
        matched_contract_path=SPEC_ROOT / PARENT_FILENAMES["matched"],
        successor_spec_path=SPEC_ROOT / PARENT_FILENAMES["successor"],
        parent_stock_spec_path=SPEC_ROOT / PARENT_FILENAMES["stock"],
        fold_manifest_path=SPEC_ROOT / PARENT_FILENAMES["folds"],
        qc_first_plan_path=SPEC_ROOT / PARENT_FILENAMES["plan"],
    )
    return load_power_calibration_input_schema(
        SPEC_ROOT / PARENT_FILENAMES["schema"], power_protocol=protocol
    )


def _load_overlay() -> FourFamilyMultiplicityOverlay:
    return load_four_family_multiplicity_overlay(
        SPEC_ROOT / PARENT_FILENAMES["overlay"],
        look_authority_path=SPEC_ROOT / PARENT_FILENAMES["look_authority"],
        qc_first_plan_path=SPEC_ROOT / PARENT_FILENAMES["plan"],
    )


def _input_artifacts(sessions: tuple[str, ...]) -> list[dict[str, object]]:
    beta_states = [
        {
            "session": session,
            "state": "missing" if index == 0 else "refused" if index == 1 else "valid",
        }
        for index, session in enumerate(sessions)
    ]
    component_counts = [
        {"session": session, "connected_component_count": 1 + index % 4}
        for index, session in enumerate(sessions)
    ]
    return [
        {
            "role": INPUT_ROLES[0],
            "artifact_id": "prod-date-beta-input-2018-2019-v1",
            "artifact_schema": INPUT_SCHEMAS[INPUT_ROLES[0]],
            "content_sha256": "1" * 64,
            "artifact_sha256": "2" * 64,
            "byte_count": 10_001,
            "record_count": CALIBRATION_SESSION_COUNT,
            "session_key_field": "decision_session",
            "session_axis_sha256": CALIBRATION_AXIS_SHA256,
            "session_state_inventory": beta_states,
            "valid_beta_date_count": CALIBRATION_SESSION_COUNT - 2,
            "missing_beta_date_count": 1,
            "refused_beta_date_count": 1,
            "state_census_sha256": hashlib.sha256(
                _canonical(beta_states)
            ).hexdigest(),
            "rights_binding_ids": [
                "binding-01-massive-ratings",
                "binding-02-reference-sources",
            ],
            "lineage_node_id": "lineage-beta-terminal-v1",
        },
        {
            "role": INPUT_ROLES[1],
            "artifact_id": "prod-component-census-2018-2019-v1",
            "artifact_schema": INPUT_SCHEMAS[INPUT_ROLES[1]],
            "content_sha256": "3" * 64,
            "artifact_sha256": "4" * 64,
            "byte_count": 8_001,
            "record_count": CALIBRATION_SESSION_COUNT,
            "session_key_field": "decision_session",
            "session_axis_sha256": CALIBRATION_AXIS_SHA256,
            "session_count_inventory": component_counts,
            "component_count_census_sha256": hashlib.sha256(
                _canonical(component_counts)
            ).hexdigest(),
            "component_count_census_session_count": CALIBRATION_SESSION_COUNT,
            "missing_session_count": 0,
            "rights_binding_ids": [
                "binding-01-massive-ratings",
                "binding-02-reference-sources",
            ],
            "lineage_node_id": "lineage-component-terminal-v1",
        },
    ]


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


def _evidence_bundle(inputs: list[dict[str, object]]) -> dict[str, object]:
    other_roles = sorted(
        set(REQUIRED_EXTERNAL_SOURCE_ROLE_INPUTS) - {"analyst_ratings_events"}
    )
    audits = [
        {
            "audit_id": "audit-01-massive-ratings",
            "source_roles": ["analyst_ratings_events"],
            "source_artifact_id": "source-01-massive-ratings",
            "source_content_sha256": "5" * 64,
            "source_artifact_sha256": "6" * 64,
            "provider_id": "massive",
            "product_id": "benzinga-analyst-ratings",
            "endpoint_id": "benzinga-v1-ratings",
            "account_scope_sha256": "7" * 64,
            "observed_at_utc": "2020-01-31T13:00:00.000000Z",
            "endpoint_access_observed": True,
            "historical_access_observed": True,
            "credential_material_present": False,
            "applies_to_input_roles": list(INPUT_ROLES),
        },
        {
            "audit_id": "audit-02-reference-sources",
            "source_roles": other_roles,
            "source_artifact_id": "source-02-reference-sources",
            "source_content_sha256": "d" * 64,
            "source_artifact_sha256": "e" * 64,
            "provider_id": "quantconnect",
            "product_id": "qc-reference-source-bundle",
            "endpoint_id": "immutable-local-export",
            "account_scope_sha256": "f" * 64,
            "observed_at_utc": "2020-01-31T13:05:00.000000Z",
            "endpoint_access_observed": True,
            "historical_access_observed": True,
            "credential_material_present": False,
            "applies_to_input_roles": list(INPUT_ROLES),
        },
    ]
    source_assumptions = [
        {
            "binding_id": "binding-01-massive-ratings",
            "source_artifact_id": audits[0]["source_artifact_id"],
            "data_entitlement_audit_id": audits[0]["audit_id"],
            "processing_scope_id": MASSIVE_BENZINGA_ASSUMPTION_SCOPE_ID,
            "owner_working_assumption_applicable": True,
            "applies_to_input_roles": list(INPUT_ROLES),
        },
        {
            "binding_id": "binding-02-reference-sources",
            "source_artifact_id": audits[1]["source_artifact_id"],
            "data_entitlement_audit_id": audits[1]["audit_id"],
            "processing_scope_id": NO_SOURCE_PROCESSING_AUTHORITY_SCOPE_ID,
            "owner_working_assumption_applicable": False,
            "applies_to_input_roles": list(INPUT_ROLES),
        },
    ]
    source_snapshots = [
        {
            "source_roles": audit["source_roles"],
            "artifact_id": audit["source_artifact_id"],
            "schema_id": f"source-snapshot-metadata-v{index}",
            "content_sha256": audit["source_content_sha256"],
            "artifact_sha256": audit["source_artifact_sha256"],
            "data_entitlement_audit_id": audit["audit_id"],
            "rights_binding_id": assumption["binding_id"],
        }
        for index, (audit, assumption) in enumerate(
            zip(audits, source_assumptions, strict=True), start=1
        )
    ]
    raw: dict[str, object] = {
        "schema": EVIDENCE_BUNDLE_SCHEMA,
        "status": EVIDENCE_BUNDLE_STATUS,
        "authority": EVIDENCE_BUNDLE_AUTHORITY,
        "bundle_id": None,
        "bundle_hash": None,
        "owner_decision": _owner_decision(),
        "data_entitlement_evidence": audits,
        "processing_rights_evidence": {
            "working_assumption_id": OWNER_DECISION_ID,
            "evidence_basis": OWNER_RIGHTS_BASIS,
            "owner_assumption_processing_scope_id": (
                MASSIVE_BENZINGA_ASSUMPTION_SCOPE_ID
            ),
            "representation_scopes": list(REPRESENTATION_SCOPES),
            "owner_assumption_permitted_purpose": OWNER_ASSUMPTION_PURPOSE,
            "candidate_input_metadata_bindings": [
                {
                    "role": item["role"],
                    "artifact_id": item["artifact_id"],
                    "content_sha256": item["content_sha256"],
                    "artifact_sha256": item["artifact_sha256"],
                }
                for item in inputs
            ],
            "source_assumption_bindings": source_assumptions,
            "quantconnect_project_visibility": "private_owner_only",
            "personal_noncommercial_use_only": True,
            "massive_benzinga_private_qc_processing_under_owner_assumption": True,
            "all_other_source_processing_authorized": False,
            "redistribution_permitted": False,
            "input_read_authorized": False,
            "vendor_written_permission_obtained": False,
            "independent_web_verification_performed": False,
            "legal_conclusion": False,
        },
        "vintage_evidence": {
            "evidence_epoch_id": "power-calibration-epoch-2020-01-31-v1",
            "evidence_epoch_artifact_id": "power-calibration-epoch-artifact-v1",
            "evidence_epoch_semantic_sha256": "8" * 64,
            "evidence_epoch_artifact_sha256": "9" * 64,
            "source_snapshot_capture_instant_utc": "2020-01-31T14:00:00.000000Z",
            "evidence_recorded_instant_utc": "2020-01-31T14:20:00.000000Z",
            "vintage_method": "contemporaneous_immutable_snapshot",
            "first_test_session_open_utc": FIRST_TEST_SESSION_OPEN_UTC,
            "max_included_availability_or_correction_instant_utc": (
                "2020-01-30T23:59:59.999999Z"
            ),
            "source_snapshot_bindings": source_snapshots,
            "external_vintage_attestation": {
                "attestation_schema": None,
                "attestation_id": None,
                "attestation_content_sha256": None,
                "attestation_artifact_sha256": None,
                "attested_information_cutoff_exclusive_utc": None,
                "source_snapshot_inventory_sha256": None,
                "correction_inventory_artifact_id": None,
                "correction_inventory_content_sha256": None,
                "correction_inventory_artifact_sha256": None,
                "cutoff_filter_recipe_id": None,
                "cutoff_filter_recipe_sha256": None,
            },
            "calibration_information_cutoff_session": (
                CALIBRATION_LAST_OUTCOME_SESSION
            ),
            "first_excluded_session": FIRST_TEST_SESSION,
            "correction_inventory_artifact_id": "correction-inventory-cutoff-v1",
            "correction_inventory_content_sha256": "a" * 64,
            "correction_inventory_artifact_sha256": "b" * 64,
            "correction_inventory_record_count": 0,
            "cutoff_filter_recipe_id": "cutoff-filter-recipe-v1",
            "cutoff_filter_recipe_sha256": "c" * 64,
            "correction_inventory_complete": True,
            "included_post_cutoff_correction_count": 0,
            "immutable_snapshot": True,
        },
        "capabilities": dict(CAPABILITIES),
    }
    return raw


def _manifest(
    admission: PowerCalibrationManifestAdmission,
    inputs: list[dict[str, object]],
    evidence: dict[str, object],
    evidence_payload: bytes,
) -> dict[str, object]:
    assumptions = evidence.get("processing_rights_evidence", {}).get(
        "source_assumption_bindings", []
    )
    rights = [
        {
            "binding_id": assumption["binding_id"],
            "receipt_id": evidence["bundle_id"],
            "receipt_schema": RIGHTS_RECEIPT_SCHEMA,
            "receipt_content_sha256": evidence["bundle_hash"],
            "receipt_artifact_sha256": hashlib.sha256(evidence_payload).hexdigest(),
            "data_entitlement_audit_id": assumption["data_entitlement_audit_id"],
            "processing_scope_id": assumption["processing_scope_id"],
            "applies_to_input_roles": assumption["applies_to_input_roles"],
        }
        for assumption in assumptions
    ]
    epoch_id = evidence["vintage_evidence"]["evidence_epoch_id"]
    snapshots = evidence["vintage_evidence"].get("source_snapshot_bindings", [])
    if not snapshots:
        snapshots = [
            {
                "source_roles": ["analyst_ratings_events"],
                "artifact_id": "invalid-evidence-shell-source",
                "schema_id": "invalid-evidence-shell-schema",
                "content_sha256": "5" * 64,
                "artifact_sha256": "6" * 64,
                "data_entitlement_audit_id": "invalid-evidence-shell-audit",
                "rights_binding_id": "invalid-evidence-shell-right",
            }
        ]
    root_nodes = [
        {
            "node_id": f"lineage-source-root-{index:02d}",
            "role": "source_artifact",
            "artifact_id": snapshot["artifact_id"],
            "schema_id": snapshot["schema_id"],
            "content_sha256": snapshot["content_sha256"],
            "artifact_sha256": snapshot["artifact_sha256"],
            "evidence_epoch_id": epoch_id,
            "parent_node_ids": [],
            "rights_binding_ids": [snapshot["rights_binding_id"]],
        }
        for index, snapshot in enumerate(snapshots, start=1)
    ]
    inherited_rights = sorted(
        {snapshot["rights_binding_id"] for snapshot in snapshots}
    )
    for item in inputs:
        item["rights_binding_ids"] = list(inherited_rights)
    nodes = [
        *root_nodes,
        {
            "node_id": "lineage-transform-v1",
            "role": "transformation",
            "artifact_id": "calibration-input-build-intermediate-v1",
            "schema_id": "arv2-calibration-input-build-v1",
            "content_sha256": "d" * 64,
            "artifact_sha256": "e" * 64,
            "evidence_epoch_id": epoch_id,
            "parent_node_ids": [item["node_id"] for item in root_nodes],
            "rights_binding_ids": inherited_rights,
        },
        *[
            {
                "node_id": item["lineage_node_id"],
                "role": item["role"],
                "artifact_id": item["artifact_id"],
                "schema_id": item["artifact_schema"],
                "content_sha256": item["content_sha256"],
                "artifact_sha256": item["artifact_sha256"],
                "evidence_epoch_id": epoch_id,
                "parent_node_ids": ["lineage-transform-v1"],
                "rights_binding_ids": inherited_rights,
            }
            for item in inputs
        ],
    ]
    external_authorities = dict(MANIFEST_EXTERNAL_AUTHORITIES)
    raw: dict[str, object] = {
        "schema": MANIFEST_SCHEMA,
        "manifest_mode": PRODUCTION_MODE,
        "status": PRODUCTION_CANDIDATE_STATUS,
        "authority": PRODUCTION_CANDIDATE_AUTHORITY,
        "manifest_id": None,
        "manifest_hash": None,
        "schema_contract_binding": {
            "artifact_id": B1_SCHEMA_ID,
            "content_sha256": B1_SCHEMA_HASH,
            "artifact_sha256": SCHEMA_CONTRACT_ARTIFACT_SHA256,
        },
        "power_protocol_binding": {
            "artifact_id": POWER_PROTOCOL_ID,
            "content_sha256": POWER_PROTOCOL_HASH,
            "artifact_sha256": POWER_PROTOCOL_ARTIFACT_SHA256,
        },
        "evaluation_id": EVALUATION_ID,
        "calibration_fold": {
            "fold_id": CALIBRATION_FOLD_ID,
            "structural_fold_sha256": CALIBRATION_FOLD_HASH,
            "horizon_sessions": 20,
            "validation_start_inclusive": CALIBRATION_START,
            "validation_end_exclusive": CALIBRATION_END_EXCLUSIVE,
            "last_included_decision_session": CALIBRATION_LAST_SESSION,
            "last_included_h20_outcome_session": CALIBRATION_LAST_OUTCOME_SESSION,
            "first_test_session": FIRST_TEST_SESSION,
        },
        "evidence_epoch_binding": {
            "evidence_epoch_id": epoch_id,
            "artifact_id": evidence["vintage_evidence"][
                "evidence_epoch_artifact_id"
            ],
            "semantic_sha256": evidence["vintage_evidence"][
                "evidence_epoch_semantic_sha256"
            ],
            "artifact_sha256": evidence["vintage_evidence"][
                "evidence_epoch_artifact_sha256"
            ],
            "capture_instant_utc": evidence["vintage_evidence"][
                "source_snapshot_capture_instant_utc"
            ],
            "calibration_information_cutoff_session": (
                CALIBRATION_LAST_OUTCOME_SESSION
            ),
            "first_excluded_session": FIRST_TEST_SESSION,
            "post_cutoff_corrections_included": False,
        },
        "producing_lineage": {
            "producing_commit": "1" * 40,
            "producing_tree": "2" * 40,
            "producer_code_sha256": "f" * 64,
            "build_recipe_id": "production-calibration-input-build-v1",
            "build_recipe_sha256": "0" * 64,
            "config_sha256": "1" * 64,
            "ordered_nodes": nodes,
            "lineage_sha256": hashlib.sha256(_canonical(nodes)).hexdigest(),
        },
        "complete_session_axis": {
            "exchange": "XNYS",
            "key_field": "decision_session",
            "key_format": "YYYY-MM-DD",
            "ordered_session_keys": list(admission.calibration_session_axis),
            "session_count": CALIBRATION_SESSION_COUNT,
            "session_axis_sha256": CALIBRATION_AXIS_SHA256,
            "first_session": CALIBRATION_START,
            "last_session": CALIBRATION_LAST_SESSION,
        },
        "input_artifacts": inputs,
        "rights_bindings": rights,
        "manifest_counts": {
            "input_artifact_count": len(inputs),
            "rights_binding_count": len(rights),
            "lineage_node_count": len(nodes),
            "session_key_count": CALIBRATION_SESSION_COUNT,
        },
        "external_authorities": external_authorities,
        "capabilities": dict(CAPABILITIES),
    }
    return raw


def _rehash_lineage(raw: dict[str, object]) -> None:
    nodes = raw["producing_lineage"]["ordered_nodes"]
    raw["producing_lineage"]["lineage_sha256"] = hashlib.sha256(
        _canonical(nodes)
    ).hexdigest()


def _write_candidate(
    tmp_path: Path,
    admission: PowerCalibrationManifestAdmission,
    *,
    evidence_mutate=None,
    manifest_mutate=None,
    post_evidence_mutate=None,
    post_manifest_mutate=None,
) -> tuple[Path, Path, dict[str, object], dict[str, object], bytes, bytes]:
    inputs = _input_artifacts(admission.calibration_session_axis)
    evidence = _evidence_bundle(inputs)
    if evidence_mutate is not None:
        evidence_mutate(evidence)
    _content_identity(
        evidence,
        id_field="bundle_id",
        hash_field="bundle_hash",
        prefix=EVIDENCE_BUNDLE_ID_PREFIX,
    )
    evidence_payload = _render(evidence)
    manifest = _manifest(admission, inputs, evidence, evidence_payload)
    if manifest_mutate is not None:
        manifest_mutate(manifest)
    _content_identity(
        manifest,
        id_field="manifest_id",
        hash_field="manifest_hash",
        prefix=MANIFEST_ID_PREFIX,
    )
    if post_evidence_mutate is not None:
        post_evidence_mutate(evidence)
        evidence_payload = _render(evidence)
    if post_manifest_mutate is not None:
        post_manifest_mutate(manifest)
    manifest_payload = _render(manifest)
    evidence_path = tmp_path / "evidence.json"
    manifest_path = tmp_path / "manifest.json"
    evidence_path.write_bytes(evidence_payload)
    manifest_path.write_bytes(manifest_payload)
    return (
        manifest_path,
        evidence_path,
        manifest,
        evidence,
        manifest_payload,
        evidence_payload,
    )


def _load_candidate(
    admission: PowerCalibrationManifestAdmission,
    paths: tuple[Path, Path, object, object, bytes, bytes],
) -> ProductionCalibrationInputManifestCandidate:
    return load_production_calibration_input_manifest_candidate(
        admission, paths[0], evidence_bundle_path=paths[1]
    )


@pytest.fixture(scope="module")
def parents() -> tuple[PowerCalibrationInputSchema, FourFamilyMultiplicityOverlay]:
    return _load_input_schema(), _load_overlay()


@pytest.fixture(scope="module")
def admission(
    parents: tuple[PowerCalibrationInputSchema, FourFamilyMultiplicityOverlay],
):
    path = SPEC_ROOT / ADMISSION_FILENAME
    return load_power_calibration_manifest_admission(
        path, input_schema=parents[0], multiplicity_overlay=parents[1]
    )


def test_admission_authenticates_exact_b1_and_four_family_parents(admission):
    assert require_loaded_power_calibration_manifest_admission(admission) is admission
    assert admission.definition["bound_parents"] == {
        "calibration_input_schema": {
            "artifact_id": B1_SCHEMA_ID,
            "content_sha256": B1_SCHEMA_HASH,
            "artifact_sha256": SCHEMA_CONTRACT_ARTIFACT_SHA256,
        },
        "four_family_multiplicity_overlay": {
            "artifact_id": FOUR_FAMILY_OVERLAY_ID,
            "content_sha256": FOUR_FAMILY_OVERLAY_HASH,
            "artifact_sha256": module.OVERLAY_ARTIFACT_SHA256,
        },
    }
    assert len(admission.calibration_session_axis) == CALIBRATION_SESSION_COUNT
    assert admission.calibration_session_axis[0] == CALIBRATION_START
    assert admission.calibration_session_axis[-1] == CALIBRATION_LAST_SESSION


def test_owner_decision_is_a_provisional_assumption_not_vendor_permission(admission):
    decision = admission.definition["owner_decision"]
    assert decision == _owner_decision()
    assert decision["reported_evidence_basis"] == (
        "owner_reported_multiple_public_user_cases"
    )
    assert decision["authorized_scope"].endswith("no_input_read_or_qc_action")
    assert decision["vendor_written_permission_obtained"] is False
    assert decision["independent_web_verification_performed"] is False
    assert decision["legal_conclusion"] is False
    rights = admission.definition["rights_contract"]
    assert rights["quantconnect_project_visibility"] == "private_owner_only"
    assert rights["personal_noncommercial_use_only"] is True
    assert rights["vendor_written_permission_obtained"] is False
    assert rights["qc_transfer_or_action_authority"] is False
    assert rights["input_read_authority"] is False
    assert rights["working_assumption_applies_only_to_massive_benzinga_source"] is True
    assert rights["all_other_source_processing_authorized"] is False
    evidence = admission.definition["evidence_bundle_contract"]
    assert evidence["owner_assumption_is_not_vendor_permission"] is True
    assert evidence["structural_validation_is_not_rights_authorization"] is True
    assert evidence["structural_validation_is_not_vintage_proof"] is True


def test_admission_and_later_stage_gates_are_exactly_closed(admission):
    assert admission.production_metadata_candidate_loader_available is True
    assert admission.massive_benzinga_working_assumption_accepted is True
    for name in (
        "production_manifest_acceptance_available",
        "calibration_input_access_available",
        "input_access_available",
        "source_access_available",
        "nuisance_calibration_available",
        "authoritative_receipt_available",
        "qc_action_available",
        "outcome_access_available",
        "deployment_available",
        "orders_available",
    ):
        assert getattr(admission, name) is False
    assert all(value is False for value in admission.capabilities.values())
    assert all(
        value is None for value in admission.definition["external_bindings"].values()
    )
    gate = admission.definition["later_stage_gate"]
    assert gate["input_artifact_loader_implemented"] is False
    assert gate["nuisance_calibration_implemented"] is False
    assert gate["numeric_receipt_implemented"] is False
    assert gate["stock_successor_v3_implemented"] is False


def test_admission_pins_frozen_resource_bounds(admission):
    assert admission.definition["resource_bounds"] == {
        "B2_owned_metadata_artifact_bytes_maximum": (
            module.MAX_METADATA_ARTIFACT_BYTES
        ),
        "already_loaded_parent_reauthentication_artifact_bytes_maximum": (
            module.MAX_METADATA_ARTIFACT_BYTES
        ),
        "cold_parent_construction_is_outside_B2_loader_scope": True,
        "descriptor_nofollow_nonblock_fstat_regular_and_path_identity_required": True,
        "entitlement_audits_maximum": module.MAX_ENTITLEMENT_AUDITS,
        "rights_bindings_maximum": module.MAX_RIGHTS_BINDINGS,
        "lineage_nodes_maximum": module.MAX_LINEAGE_NODES,
        "integer_maximum": module.MAX_SAFE_COUNT,
        "initial_and_revalidation_reads_bounded_to_maximum_plus_one": True,
    }


@pytest.mark.parametrize(
    ("owner", "name"),
    [
        *[
            (PowerCalibrationManifestAdmission, name)
            for name in (
                "production_manifest_acceptance_available",
                "calibration_input_access_available",
                "input_access_available",
                "source_access_available",
                "nuisance_calibration_available",
                "authoritative_receipt_available",
                "qc_action_available",
                "outcome_access_available",
                "deployment_available",
                "orders_available",
            )
        ],
        *[
            (ProductionCalibrationInputManifestCandidate, name)
            for name in (
                "production_authorized",
                "rights_authorized",
                "vintage_proven",
                "input_artifacts_authenticated",
                "entitlement_truth_authenticated",
                "production_lineage_complete",
                "input_access_available",
                "source_access_available",
                "calibration_available",
                "authoritative_receipt_available",
                "qc_action_available",
                "outcome_access_available",
                "deployment_available",
                "orders_available",
                "order_submission_available",
                "trading_available",
            )
        ],
    ],
)
def test_every_false_authority_accessor_is_a_literal_false_constant(owner, name):
    function = inspect.getattr_static(owner, name).fget
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    returns = [node for node in ast.walk(tree) if isinstance(node, ast.Return)]
    assert len(returns) == 1
    assert isinstance(returns[0].value, ast.Constant)
    assert returns[0].value.value is False


def test_valid_candidate_authenticates_metadata_without_opening_inputs(
    tmp_path, admission
):
    paths = _write_candidate(tmp_path, admission)
    candidate = _load_candidate(admission, paths)
    manifest = paths[2]
    evidence = paths[3]
    assert candidate.manifest_id == manifest["manifest_id"]
    assert candidate.manifest_content_sha256 == manifest["manifest_hash"]
    assert candidate.manifest_artifact_sha256 == hashlib.sha256(paths[4]).hexdigest()
    assert candidate.evidence_bundle_id == evidence["bundle_id"]
    assert candidate.evidence_bundle_content_sha256 == evidence["bundle_hash"]
    assert candidate.evidence_bundle_artifact_sha256 == hashlib.sha256(paths[5]).hexdigest()
    assert candidate.metadata_authenticated is True
    assert candidate.massive_benzinga_working_assumption_accepted is True
    assert candidate.data_entitlement_audit_ids == (
        "audit-01-massive-ratings",
        "audit-02-reference-sources",
    )
    assert candidate.massive_benzinga_working_assumption_id == OWNER_DECISION_ID
    assert candidate.session_count == CALIBRATION_SESSION_COUNT
    assert candidate.input_roles == INPUT_ROLES
    assert isinstance(candidate.definition, MappingProxyType)
    assert not (tmp_path / "prod-date-beta-input-2018-2019-v1").exists()
    assert not (tmp_path / "prod-component-census-2018-2019-v1").exists()
    assert require_loaded_production_calibration_input_manifest_candidate(candidate) is candidate


def test_valid_reconstructed_vintage_requires_and_accepts_external_attestation(
    tmp_path, admission
):
    def mutate(raw):
        vintage = raw["vintage_evidence"]
        vintage["source_snapshot_capture_instant_utc"] = (
            "2026-09-06T12:00:00.000000Z"
        )
        vintage["evidence_recorded_instant_utc"] = "2026-09-06T12:10:00.000000Z"
        vintage["vintage_method"] = "externally_attested_as_of_reconstruction"
        vintage["external_vintage_attestation"] = {
            "attestation_schema": module.VINTAGE_ATTESTATION_SCHEMA,
            "attestation_id": "external-vintage-attestation-v1",
            "attestation_content_sha256": "2" * 64,
            "attestation_artifact_sha256": "3" * 64,
            "attested_information_cutoff_exclusive_utc": (
                "2020-01-31T00:00:00.000000Z"
            ),
            "source_snapshot_inventory_sha256": hashlib.sha256(
                _canonical(vintage["source_snapshot_bindings"])
            ).hexdigest(),
            "correction_inventory_artifact_id": vintage[
                "correction_inventory_artifact_id"
            ],
            "correction_inventory_content_sha256": vintage[
                "correction_inventory_content_sha256"
            ],
            "correction_inventory_artifact_sha256": vintage[
                "correction_inventory_artifact_sha256"
            ],
            "cutoff_filter_recipe_id": vintage["cutoff_filter_recipe_id"],
            "cutoff_filter_recipe_sha256": vintage[
                "cutoff_filter_recipe_sha256"
            ],
        }

    paths = _write_candidate(tmp_path, admission, evidence_mutate=mutate)
    assert _load_candidate(admission, paths).metadata_authenticated is True


def test_candidate_grants_no_production_rights_input_compute_qc_or_action(
    tmp_path, admission
):
    candidate = _load_candidate(admission, _write_candidate(tmp_path, admission))
    assert candidate.production_authorized is False
    assert candidate.rights_authorized is False
    assert candidate.vintage_proven is False
    assert candidate.input_artifacts_authenticated is False
    for name in (
        "entitlement_truth_authenticated",
        "production_lineage_complete",
        "input_access_available",
        "source_access_available",
        "calibration_available",
        "authoritative_receipt_available",
        "qc_action_available",
        "outcome_access_available",
        "deployment_available",
        "orders_available",
        "order_submission_available",
        "trading_available",
    ):
        assert getattr(candidate, name) is False
    assert all(
        value is False for value in candidate.definition["capabilities"].values()
    )


def _set_path(raw: dict[str, object], path: tuple[object, ...], value: object) -> None:
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def _delete_path(raw: dict[str, object], path: tuple[object, ...]) -> None:
    target = raw
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]


def _mutate_lineage(raw: dict[str, object], mutate) -> None:
    mutate(raw["producing_lineage"]["ordered_nodes"])
    _rehash_lineage(raw)


def _copy_node(node: dict[str, object], **changes: object) -> dict[str, object]:
    result = copy.deepcopy(node)
    result.update(changes)
    return result


def test_checked_in_admission_is_exact_renderer_output_and_content_addressed():
    path = SPEC_ROOT / ADMISSION_FILENAME
    payload = path.read_bytes()
    assert len(payload) == 15_126
    assert payload == render_expected_power_calibration_manifest_admission().encode(
        "utf-8"
    )
    assert hashlib.sha256(payload).hexdigest() == (
        "173d161b80447ee8bc0b28a1e5fef49cd00f1df1a53ef67fe195ebd1d153e811"
    )
    assert module.ADMISSION_CONTRACT_ARTIFACT_SHA256 == (
        "173d161b80447ee8bc0b28a1e5fef49cd00f1df1a53ef67fe195ebd1d153e811"
    )
    raw = json.loads(payload)
    declared_id = raw["admission_contract_id"]
    declared_hash = raw["admission_contract_hash"]
    assert declared_id == (
        "arv2-stock-power-calibration-manifest-admission-ed654e3289185180"
    )
    assert declared_hash == (
        "ed654e32891851806af318ba7baf88f7f5b7ee3a151cecf07b126792755e670c"
    )
    raw["admission_contract_id"] = None
    raw["admission_contract_hash"] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()
    assert declared_hash == digest
    assert declared_id == module.ADMISSION_CONTRACT_ID_PREFIX + digest[:16]


def test_authority_objects_cannot_be_constructed_or_dataclass_replaced(
    tmp_path, admission
):
    candidate = _load_candidate(admission, _write_candidate(tmp_path, admission))
    with pytest.raises(TypeError):
        PowerCalibrationManifestAdmission()
    with pytest.raises(TypeError):
        ProductionCalibrationInputManifestCandidate()
    with pytest.raises(TypeError):
        dataclasses.replace(admission)
    with pytest.raises(TypeError):
        dataclasses.replace(candidate)


@pytest.mark.parametrize("kind", ["admission", "candidate"])
def test_copied_authority_cannot_claim_its_positive_marker(tmp_path, admission, kind):
    value = (
        admission
        if kind == "admission"
        else _load_candidate(admission, _write_candidate(tmp_path, admission))
    )
    copied = copy.copy(value)
    if kind == "admission":
        with pytest.raises(PowerCalibrationInputManifestError):
            _ = copied.production_metadata_candidate_loader_available
        with pytest.raises(PowerCalibrationInputManifestError):
            _ = copied.massive_benzinga_working_assumption_accepted
        with pytest.raises(PowerCalibrationInputManifestError):
            require_loaded_power_calibration_manifest_admission(copied)
    else:
        with pytest.raises(PowerCalibrationInputManifestError):
            _ = copied.metadata_authenticated
        with pytest.raises(PowerCalibrationInputManifestError):
            _ = copied.massive_benzinga_working_assumption_accepted
        with pytest.raises(PowerCalibrationInputManifestError):
            require_loaded_production_calibration_input_manifest_candidate(copied)


def test_forged_shells_cannot_claim_positive_markers():
    forged_admission = object.__new__(PowerCalibrationManifestAdmission)
    object.__setattr__(forged_admission, "_authority", module._LOADED_ADMISSION_AUTHORITY)
    with pytest.raises(PowerCalibrationInputManifestError):
        _ = forged_admission.production_metadata_candidate_loader_available
    with pytest.raises(PowerCalibrationInputManifestError):
        _ = forged_admission.massive_benzinga_working_assumption_accepted
    forged_candidate = object.__new__(ProductionCalibrationInputManifestCandidate)
    object.__setattr__(forged_candidate, "_authority", module._LOADED_CANDIDATE_AUTHORITY)
    with pytest.raises(PowerCalibrationInputManifestError):
        _ = forged_candidate.metadata_authenticated
    with pytest.raises(PowerCalibrationInputManifestError):
        _ = forged_candidate.massive_benzinga_working_assumption_accepted


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("admission", "admission_contract_id"),
        ("admission", "admission_contract_hash"),
        ("candidate", "manifest_id"),
        ("candidate", "manifest_content_sha256"),
        ("candidate", "evidence_bundle_id"),
        ("candidate", "evidence_bundle_content_sha256"),
    ],
)
def test_equal_comparing_string_subclasses_cannot_spoof_authority(
    tmp_path, admission, kind, field
):
    class SpoofedStr(str):
        pass

    value = (
        admission
        if kind == "admission"
        else _load_candidate(admission, _write_candidate(tmp_path, admission))
    )
    original = getattr(value, field)
    object.__setattr__(value, field, SpoofedStr(original))
    checker = (
        require_loaded_power_calibration_manifest_admission
        if kind == "admission"
        else require_loaded_production_calibration_input_manifest_candidate
    )
    try:
        with pytest.raises(PowerCalibrationInputManifestError):
            checker(value)
    finally:
        object.__setattr__(value, field, original)


def test_mapping_key_string_subclasses_cannot_spoof_candidate_definition(
    tmp_path, admission
):
    class SpoofedStr(str):
        pass

    candidate = _load_candidate(admission, _write_candidate(tmp_path, admission))
    changed = dict(candidate.definition)
    manifest = changed.pop("manifest")
    changed[SpoofedStr("manifest")] = manifest
    object.__setattr__(candidate, "definition", MappingProxyType(changed))
    with pytest.raises(PowerCalibrationInputManifestError):
        require_loaded_production_calibration_input_manifest_candidate(candidate)


def test_weakref_cleanup_removes_candidate_authority(tmp_path, admission):
    candidate = _load_candidate(admission, _write_candidate(tmp_path, admission))
    identity = id(candidate)
    reference = weakref.ref(candidate)
    assert identity in module._CANDIDATE_AUTHORITIES
    del candidate
    gc.collect()
    assert reference() is None
    assert identity not in module._CANDIDATE_AUTHORITIES


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema",), "wrong-schema"),
        (("status",), "accepted"),
        (("authority",), "production-authority"),
        (("owner_decision", "decision_id"), "other-owner-decision"),
        (("owner_decision", "decision_date"), "2026-09-07"),
        (("owner_decision", "source"), "vendor-written-letter"),
        (("owner_decision", "reported_evidence_basis"), "vendor-contract"),
        (("owner_decision", "authorized_scope"), "full-calibration-and-qc"),
    ],
)
def test_evidence_scope_and_owner_provenance_are_exact(
    tmp_path, admission, path, value
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=lambda raw: _set_path(raw, path, value),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    "field",
    [
        "vendor_written_permission_obtained",
        "independent_web_verification_performed",
        "legal_conclusion",
        "input_read_authorized",
        "nuisance_compute_authorized",
        "qc_action_authorized",
        "outcome_access_authorized",
    ],
)
def test_owner_decision_cannot_overclaim_any_adjacent_authority(
    tmp_path, admission, field
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=lambda raw: raw["owner_decision"].__setitem__(field, True),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_id", "benzinga"),
        ("product_id", "massive-stocks"),
        ("endpoint_id", "other-endpoint"),
        ("account_scope_sha256", "A" * 64),
        ("observed_at_utc", "2020-01-31T13:00:00Z"),
        ("endpoint_access_observed", False),
        ("endpoint_access_observed", 1),
        ("historical_access_observed", False),
        ("credential_material_present", True),
        ("credential_material_present", 0),
    ],
)
def test_entitlement_evidence_is_exact_and_contains_no_credential_material(
    tmp_path, admission, field, value
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=lambda raw: raw["data_entitlement_evidence"][0].__setitem__(
            field, value
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("working_assumption_id", "vendor-authority"),
        ("evidence_basis", "written-vendor-permission"),
        ("owner_assumption_processing_scope_id", "commercial-redistribution"),
        ("representation_scopes", list(reversed(REPRESENTATION_SCOPES))),
        ("owner_assumption_permitted_purpose", "historical-outcome-research"),
        ("quantconnect_project_visibility", "public"),
        ("personal_noncommercial_use_only", False),
        ("massive_benzinga_private_qc_processing_under_owner_assumption", False),
        ("all_other_source_processing_authorized", True),
        ("redistribution_permitted", True),
        ("input_read_authorized", True),
        ("vendor_written_permission_obtained", True),
        ("independent_web_verification_performed", True),
        ("legal_conclusion", True),
    ],
)
def test_processing_rights_never_exceed_the_owner_working_assumption(
    tmp_path, admission, field, value
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=lambda raw: raw["processing_rights_evidence"].__setitem__(
            field, value
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.update({"unexpected": None}),
        lambda raw: raw.pop("owner_decision"),
        lambda raw: raw["owner_decision"].update({"unexpected": None}),
        lambda raw: raw["data_entitlement_evidence"][0].pop("audit_id"),
        lambda raw: raw["processing_rights_evidence"].update(
            {"vendor_permission": True}
        ),
        lambda raw: raw["vintage_evidence"].pop("cutoff_filter_recipe_id"),
    ],
    ids=[
        "extra-root",
        "missing-owner",
        "extra-owner",
        "missing-entitlement",
        "extra-rights",
        "missing-vintage",
    ],
)
def test_evidence_bundle_and_nested_field_sets_are_closed(
    tmp_path, admission, mutate
):
    paths = _write_candidate(tmp_path, admission, evidence_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


def test_evidence_declared_identity_cannot_be_copied_or_forged(tmp_path, admission):
    paths = _write_candidate(
        tmp_path,
        admission,
        post_evidence_mutate=lambda raw: raw.__setitem__("bundle_hash", "0" * 64),
    )
    with pytest.raises(PowerCalibrationInputManifestError, match="content-derived"):
        _load_candidate(admission, paths)


def test_rights_evidence_must_bind_the_exact_two_input_metadata_records(
    tmp_path, admission
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=lambda raw: raw["processing_rights_evidence"][
            "candidate_input_metadata_bindings"
        ][0].__setitem__("content_sha256", "f" * 64),
    )
    with pytest.raises(PowerCalibrationInputManifestError, match="exact input metadata"):
        _load_candidate(admission, paths)


def test_rights_input_binding_order_and_cardinality_are_exact(tmp_path, admission):
    def mutate(raw):
        raw["processing_rights_evidence"]["candidate_input_metadata_bindings"].reverse()

    paths = _write_candidate(tmp_path, admission, evidence_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


def _add_partitioned_security_source(raw: dict[str, object]) -> None:
    role = "security_identity_and_listing_history"
    audit = {
        "audit_id": "audit-03-security-partition",
        "source_roles": [role],
        "source_artifact_id": "source-03-security-partition",
        "source_content_sha256": "2" * 64,
        "source_artifact_sha256": "3" * 64,
        "provider_id": "security-master-provider",
        "product_id": "security-history-partition",
        "endpoint_id": "immutable-local-export",
        "account_scope_sha256": "4" * 64,
        "observed_at_utc": "2020-01-31T13:10:00.000000Z",
        "endpoint_access_observed": True,
        "historical_access_observed": True,
        "credential_material_present": False,
        "applies_to_input_roles": list(INPUT_ROLES),
    }
    assumption = {
        "binding_id": "binding-03-security-partition",
        "source_artifact_id": audit["source_artifact_id"],
        "data_entitlement_audit_id": audit["audit_id"],
        "processing_scope_id": NO_SOURCE_PROCESSING_AUTHORITY_SCOPE_ID,
        "owner_working_assumption_applicable": False,
        "applies_to_input_roles": list(INPUT_ROLES),
    }
    snapshot = {
        "source_roles": audit["source_roles"],
        "artifact_id": audit["source_artifact_id"],
        "schema_id": "source-snapshot-metadata-v3",
        "content_sha256": audit["source_content_sha256"],
        "artifact_sha256": audit["source_artifact_sha256"],
        "data_entitlement_audit_id": audit["audit_id"],
        "rights_binding_id": assumption["binding_id"],
    }
    raw["data_entitlement_evidence"].append(audit)
    raw["processing_rights_evidence"]["source_assumption_bindings"].append(
        assumption
    )
    raw["vintage_evidence"]["source_snapshot_bindings"].append(snapshot)


def _separate_terminal_returns_source(raw: dict[str, object]) -> None:
    role = "terminal_returns_and_delisting_events"
    reference_audit = raw["data_entitlement_evidence"][1]
    reference_audit["source_roles"].remove(role)
    audit = {
        "audit_id": "audit-03-terminal-returns",
        "source_roles": [role],
        "source_artifact_id": "source-03-terminal-returns",
        "source_content_sha256": "2" * 64,
        "source_artifact_sha256": "3" * 64,
        "provider_id": "terminal-return-provider",
        "product_id": "terminal-return-history",
        "endpoint_id": "immutable-local-export",
        "account_scope_sha256": "4" * 64,
        "observed_at_utc": "2020-01-31T13:10:00.000000Z",
        "endpoint_access_observed": True,
        "historical_access_observed": True,
        "credential_material_present": False,
        "applies_to_input_roles": [INPUT_ROLES[0]],
    }
    assumption = {
        "binding_id": "binding-03-terminal-returns",
        "source_artifact_id": audit["source_artifact_id"],
        "data_entitlement_audit_id": audit["audit_id"],
        "processing_scope_id": NO_SOURCE_PROCESSING_AUTHORITY_SCOPE_ID,
        "owner_working_assumption_applicable": False,
        "applies_to_input_roles": [INPUT_ROLES[0]],
    }
    snapshot = {
        "source_roles": audit["source_roles"],
        "artifact_id": audit["source_artifact_id"],
        "schema_id": "source-snapshot-metadata-v3",
        "content_sha256": audit["source_content_sha256"],
        "artifact_sha256": audit["source_artifact_sha256"],
        "data_entitlement_audit_id": audit["audit_id"],
        "rights_binding_id": assumption["binding_id"],
    }
    raw["data_entitlement_evidence"].append(audit)
    raw["processing_rights_evidence"]["source_assumption_bindings"].append(
        assumption
    )
    raw["vintage_evidence"]["source_snapshot_bindings"].append(snapshot)


def _split_role_specific_lineage(raw: dict[str, object]) -> None:
    nodes = raw["producing_lineage"]["ordered_nodes"]
    roots = nodes[:3]
    beta_terminal = nodes[4]
    component_terminal = nodes[5]
    both_role_rights = [
        "binding-01-massive-ratings",
        "binding-02-reference-sources",
    ]
    beta_rights = [*both_role_rights, "binding-03-terminal-returns"]
    beta_transform = {
        "node_id": "lineage-beta-transform-v1",
        "role": "transformation",
        "artifact_id": "calibration-beta-build-intermediate-v1",
        "schema_id": "arv2-calibration-beta-build-v1",
        "content_sha256": "7" * 64,
        "artifact_sha256": "8" * 64,
        "evidence_epoch_id": roots[0]["evidence_epoch_id"],
        "parent_node_ids": [item["node_id"] for item in roots],
        "rights_binding_ids": list(beta_rights),
    }
    component_transform = {
        "node_id": "lineage-component-transform-v1",
        "role": "transformation",
        "artifact_id": "calibration-component-build-intermediate-v1",
        "schema_id": "arv2-calibration-component-build-v1",
        "content_sha256": "9" * 64,
        "artifact_sha256": "a" * 64,
        "evidence_epoch_id": roots[0]["evidence_epoch_id"],
        "parent_node_ids": [item["node_id"] for item in roots[:2]],
        "rights_binding_ids": list(both_role_rights),
    }
    beta_terminal["parent_node_ids"] = [beta_transform["node_id"]]
    beta_terminal["rights_binding_ids"] = list(beta_rights)
    component_terminal["parent_node_ids"] = [component_transform["node_id"]]
    component_terminal["rights_binding_ids"] = list(both_role_rights)
    raw["input_artifacts"][0]["rights_binding_ids"] = list(beta_rights)
    raw["input_artifacts"][1]["rights_binding_ids"] = list(both_role_rights)
    nodes[:] = [
        *roots,
        beta_transform,
        component_transform,
        beta_terminal,
        component_terminal,
    ]
    raw["manifest_counts"]["lineage_node_count"] = len(nodes)
    _rehash_lineage(raw)


def _omit_reference_source_from_component(raw: dict[str, object]) -> None:
    _split_role_specific_lineage(raw)
    nodes = raw["producing_lineage"]["ordered_nodes"]
    component_transform = nodes[4]
    component_terminal = nodes[6]
    omitted_right = "binding-02-reference-sources"
    component_transform["parent_node_ids"].remove(nodes[1]["node_id"])
    component_transform["rights_binding_ids"].remove(omitted_right)
    component_terminal["rights_binding_ids"].remove(omitted_right)
    raw["input_artifacts"][1]["rights_binding_ids"].remove(omitted_right)
    _rehash_lineage(raw)


def test_valid_source_model_allows_multi_role_artifacts_and_role_partitions(
    tmp_path, admission
):
    paths = _write_candidate(
        tmp_path, admission, evidence_mutate=_add_partitioned_security_source
    )
    candidate = _load_candidate(admission, paths)
    assert candidate.data_entitlement_audit_ids == (
        "audit-01-massive-ratings",
        "audit-02-reference-sources",
        "audit-03-security-partition",
    )
    evidence = candidate.definition["evidence_bundle"]
    audits = evidence["data_entitlement_evidence"]
    assert len(audits[1]["source_roles"]) > 1
    assert sum(
        "security_identity_and_listing_history" in audit["source_roles"]
        for audit in audits
    ) == 2


def test_valid_role_specific_source_rights_and_ancestry(tmp_path, admission):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=_separate_terminal_returns_source,
        manifest_mutate=_split_role_specific_lineage,
    )
    candidate = _load_candidate(admission, paths)
    beta, component = candidate.definition["manifest"]["input_artifacts"]
    assert beta["rights_binding_ids"] == (
        "binding-01-massive-ratings",
        "binding-02-reference-sources",
        "binding-03-terminal-returns",
    )
    assert component["rights_binding_ids"] == (
        "binding-01-massive-ratings",
        "binding-02-reference-sources",
    )


def test_both_role_source_cannot_be_omitted_from_one_input_rights_and_ancestry(
    tmp_path, admission
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=_separate_terminal_returns_source,
        manifest_mutate=_omit_reference_source_from_component,
    )
    with pytest.raises(
        PowerCalibrationInputManifestError, match="rights binding changed"
    ):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw["data_entitlement_evidence"][0]["source_roles"].append(
            "security_identity_and_listing_history"
        ),
        lambda raw: raw["data_entitlement_evidence"][0].__setitem__(
            "provider_id", "other-provider"
        ),
        lambda raw: raw["data_entitlement_evidence"][0].__setitem__(
            "product_id", "other-product"
        ),
        lambda raw: raw["data_entitlement_evidence"][0].__setitem__(
            "endpoint_id", "other-endpoint"
        ),
    ],
    ids=["extra-source-role", "provider", "product", "endpoint"],
)
def test_massive_benzinga_audit_cannot_stand_in_for_other_sources(
    tmp_path, admission, mutate
):
    paths = _write_candidate(tmp_path, admission, evidence_mutate=mutate)
    with pytest.raises(
        PowerCalibrationInputManifestError, match="must bind biconditionally"
    ):
        _load_candidate(admission, paths)


def test_massive_benzinga_endpoint_cannot_bind_nonratings_sources(tmp_path, admission):
    def mutate(raw):
        audit = raw["data_entitlement_evidence"][1]
        audit["provider_id"] = "massive"
        audit["product_id"] = "benzinga-analyst-ratings"
        audit["endpoint_id"] = "benzinga-v1-ratings"

    paths = _write_candidate(tmp_path, admission, evidence_mutate=mutate)
    with pytest.raises(
        PowerCalibrationInputManifestError, match="must bind biconditionally"
    ):
        _load_candidate(admission, paths)


def _extend_owner_assumption_to_nonmassive_multirole_source(
    raw: dict[str, object]
) -> None:
    audits = raw["data_entitlement_evidence"]
    assumptions = raw["processing_rights_evidence"]["source_assumption_bindings"]
    snapshots = raw["vintage_evidence"]["source_snapshot_bindings"]

    audits[1]["source_roles"] = sorted(
        [*audits[1]["source_roles"], "analyst_ratings_events"]
    )
    assumptions[1]["owner_working_assumption_applicable"] = True
    assumptions[1]["processing_scope_id"] = MASSIVE_BENZINGA_ASSUMPTION_SCOPE_ID
    snapshots[1]["source_roles"] = list(audits[1]["source_roles"])


def _move_analyst_role_to_nonmassive_multirole_source(
    raw: dict[str, object]
) -> None:
    audits = raw["data_entitlement_evidence"]
    assumptions = raw["processing_rights_evidence"]["source_assumption_bindings"]
    snapshots = raw["vintage_evidence"]["source_snapshot_bindings"]

    audits[0]["source_roles"] = ["earnings_and_guidance_events"]
    audits[0]["provider_id"] = "alternate-event-provider"
    audits[0]["product_id"] = "alternate-event-history"
    audits[0]["endpoint_id"] = "immutable-local-export"
    audits[1]["source_roles"] = sorted(
        [*audits[1]["source_roles"], "analyst_ratings_events"]
    )
    assumptions[0]["owner_working_assumption_applicable"] = False
    assumptions[0]["processing_scope_id"] = NO_SOURCE_PROCESSING_AUTHORITY_SCOPE_ID
    assumptions[1]["owner_working_assumption_applicable"] = False
    assumptions[1]["processing_scope_id"] = NO_SOURCE_PROCESSING_AUTHORITY_SCOPE_ID
    snapshots[0]["source_roles"] = list(audits[0]["source_roles"])
    snapshots[1]["source_roles"] = list(audits[1]["source_roles"])


def test_owner_assumption_cannot_follow_analyst_role_to_nonmassive_multirole_source(
    tmp_path, admission
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=_extend_owner_assumption_to_nonmassive_multirole_source,
    )
    with pytest.raises(
        PowerCalibrationInputManifestError, match="Massive/Benzinga-only"
    ):
        _load_candidate(admission, paths)


def test_candidate_requires_a_massive_benzinga_source_for_its_owner_assumption(
    tmp_path, admission
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=_move_analyst_role_to_nonmassive_multirole_source,
    )
    with pytest.raises(
        PowerCalibrationInputManifestError,
        match="at least one Massive/Benzinga ratings source",
    ):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("index", "applicable", "scope"),
    [
        (0, False, NO_SOURCE_PROCESSING_AUTHORITY_SCOPE_ID),
        (1, True, MASSIVE_BENZINGA_ASSUMPTION_SCOPE_ID),
    ],
)
def test_owner_working_assumption_cannot_be_removed_or_extended_to_other_sources(
    tmp_path, admission, index, applicable, scope
):
    def mutate(raw):
        item = raw["processing_rights_evidence"]["source_assumption_bindings"][
            index
        ]
        item["owner_working_assumption_applicable"] = applicable
        item["processing_scope_id"] = scope

    paths = _write_candidate(tmp_path, admission, evidence_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError, match="Massive/Benzinga-only"):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    "roles",
    [
        [],
        ["unknown-source-role"],
        ["security_identity_and_listing_history", "earnings_and_guidance_events"],
        ["earnings_and_guidance_events", "earnings_and_guidance_events"],
    ],
)
def test_entitlement_source_roles_are_nonempty_closed_sorted_and_unique(
    tmp_path, admission, roles
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=lambda raw: raw["data_entitlement_evidence"][1].__setitem__(
            "source_roles", roles
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


def test_entitlement_audit_inventory_must_be_sorted_and_source_complete(
    tmp_path, admission
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=lambda raw: raw["data_entitlement_evidence"].reverse(),
    )
    with pytest.raises(PowerCalibrationInputManifestError, match="sorted"):
        _load_candidate(admission, paths)


def test_zero_correction_records_are_valid_closed_evidence(tmp_path, admission):
    candidate = _load_candidate(admission, _write_candidate(tmp_path, admission))
    assert (
        candidate.definition["evidence_bundle"]["vintage_evidence"][
            "correction_inventory_record_count"
        ]
        == 0
    )


def _make_reconstructed_vintage(raw: dict[str, object]) -> None:
    vintage = raw["vintage_evidence"]
    vintage["source_snapshot_capture_instant_utc"] = "2026-09-06T12:00:00.000000Z"
    vintage["evidence_recorded_instant_utc"] = "2026-09-06T12:10:00.000000Z"
    vintage["vintage_method"] = "externally_attested_as_of_reconstruction"
    vintage["external_vintage_attestation"] = {
        "attestation_schema": module.VINTAGE_ATTESTATION_SCHEMA,
        "attestation_id": "external-vintage-attestation-v1",
        "attestation_content_sha256": "2" * 64,
        "attestation_artifact_sha256": "3" * 64,
        "attested_information_cutoff_exclusive_utc": (
            "2020-01-31T00:00:00.000000Z"
        ),
        "source_snapshot_inventory_sha256": hashlib.sha256(
            _canonical(vintage["source_snapshot_bindings"])
        ).hexdigest(),
        "correction_inventory_artifact_id": vintage[
            "correction_inventory_artifact_id"
        ],
        "correction_inventory_content_sha256": vintage[
            "correction_inventory_content_sha256"
        ],
        "correction_inventory_artifact_sha256": vintage[
            "correction_inventory_artifact_sha256"
        ],
        "cutoff_filter_recipe_id": vintage["cutoff_filter_recipe_id"],
        "cutoff_filter_recipe_sha256": vintage["cutoff_filter_recipe_sha256"],
    }


@pytest.mark.parametrize(
    "capture",
    [
        "2020-01-31T00:00:00.000000Z",
        "2020-01-31T14:29:59.999999Z",
    ],
)
def test_contemporaneous_capture_window_boundaries_are_accepted(
    tmp_path, admission, capture
):
    def mutate(raw):
        raw["vintage_evidence"]["source_snapshot_capture_instant_utc"] = capture
        raw["vintage_evidence"]["evidence_recorded_instant_utc"] = (
            "2020-01-31T14:29:59.999999Z"
        )

    paths = _write_candidate(tmp_path, admission, evidence_mutate=mutate)
    assert _load_candidate(admission, paths).metadata_authenticated is True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (
            ("vintage_evidence", "source_snapshot_capture_instant_utc"),
            "2020-01-30T23:59:59.999999Z",
        ),
        (
            ("vintage_evidence", "source_snapshot_capture_instant_utc"),
            FIRST_TEST_SESSION_OPEN_UTC,
        ),
        (
            ("vintage_evidence", "max_included_availability_or_correction_instant_utc"),
            "2020-01-31T00:00:00.000000Z",
        ),
        (
            ("vintage_evidence", "first_test_session_open_utc"),
            "2020-01-31T14:30:00.000001Z",
        ),
        (
            ("vintage_evidence", "evidence_recorded_instant_utc"),
            "2020-01-31T13:59:59.999999Z",
        ),
        (("vintage_evidence", "vintage_method"), "self_declared_reconstruction"),
        (
            ("vintage_evidence", "calibration_information_cutoff_session"),
            "2020-01-31",
        ),
        (("vintage_evidence", "first_excluded_session"), "2020-02-03"),
        (("vintage_evidence", "correction_inventory_record_count"), -1),
        (("vintage_evidence", "correction_inventory_record_count"), True),
        (("vintage_evidence", "correction_inventory_complete"), False),
        (("vintage_evidence", "included_post_cutoff_correction_count"), 1),
        (("vintage_evidence", "included_post_cutoff_correction_count"), False),
        (("vintage_evidence", "immutable_snapshot"), False),
        (("vintage_evidence", "cutoff_filter_recipe_sha256"), "F" * 64),
    ],
)
def test_vintage_evidence_refuses_boundary_chronology_and_cutoff_drift(
    tmp_path, admission, path, value
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=lambda raw: _set_path(raw, path, value),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


def test_entitlement_observation_cannot_postdate_the_vintage_record(tmp_path, admission):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=lambda raw: raw["data_entitlement_evidence"][0].__setitem__(
            "observed_at_utc", "2020-01-31T14:20:00.000001Z"
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError, match="chronology"):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw["vintage_evidence"].__setitem__(
            "source_snapshot_bindings", []
        ),
        lambda raw: raw["vintage_evidence"]["source_snapshot_bindings"].append(
            copy.deepcopy(raw["vintage_evidence"]["source_snapshot_bindings"][0])
        ),
        lambda raw: raw["vintage_evidence"]["source_snapshot_bindings"][0].__setitem__(
            "artifact_id", "synthetic-source"
        ),
        lambda raw: raw["vintage_evidence"]["source_snapshot_bindings"][0].__setitem__(
            "content_sha256", "not-a-hash"
        ),
    ],
    ids=["empty", "duplicate", "synthetic-id", "invalid-hash"],
)
def test_source_snapshot_inventory_is_nonempty_unique_production_metadata(
    tmp_path, admission, mutate
):
    paths = _write_candidate(tmp_path, admission, evidence_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


def test_source_snapshot_inventory_must_be_sorted(tmp_path, admission):
    def mutate(raw):
        raw["vintage_evidence"]["source_snapshot_bindings"].reverse()

    paths = _write_candidate(tmp_path, admission, evidence_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError, match="sorted"):
        _load_candidate(admission, paths)


def test_contemporaneous_vintage_refuses_any_external_attestation_claim(
    tmp_path, admission
):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=lambda raw: raw["vintage_evidence"][
            "external_vintage_attestation"
        ].__setitem__("attestation_id", "unexpected-attestation"),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


def test_reconstruction_refuses_an_empty_attestation(tmp_path, admission):
    def mutate(raw):
        vintage = raw["vintage_evidence"]
        vintage["source_snapshot_capture_instant_utc"] = (
            "2026-09-06T12:00:00.000000Z"
        )
        vintage["evidence_recorded_instant_utc"] = "2026-09-06T12:10:00.000000Z"
        vintage["vintage_method"] = "externally_attested_as_of_reconstruction"

    paths = _write_candidate(tmp_path, admission, evidence_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("attestation_schema", "other-schema"),
        ("attested_information_cutoff_exclusive_utc", FIRST_TEST_SESSION_OPEN_UTC),
        ("source_snapshot_inventory_sha256", "0" * 64),
        ("correction_inventory_artifact_id", "other-correction-inventory"),
        ("correction_inventory_content_sha256", "0" * 64),
        ("correction_inventory_artifact_sha256", "0" * 64),
        ("cutoff_filter_recipe_id", "other-cutoff-filter"),
        ("cutoff_filter_recipe_sha256", "0" * 64),
    ],
)
def test_reconstruction_attestation_binds_every_vintage_identity(
    tmp_path, admission, field, value
):
    def mutate(raw):
        _make_reconstructed_vintage(raw)
        raw["vintage_evidence"]["external_vintage_attestation"][field] = value

    paths = _write_candidate(tmp_path, admission, evidence_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema",), "other-manifest-schema"),
        (("manifest_mode",), "synthetic_fixture"),
        (("status",), "accepted-production-manifest"),
        (("authority",), "input-and-qc-authority"),
        (("evaluation_id",), "other-evaluation"),
        (("schema_contract_binding", "artifact_id"), "other-b1"),
        (("schema_contract_binding", "content_sha256"), "0" * 64),
        (("schema_contract_binding", "artifact_sha256"), "0" * 64),
        (("power_protocol_binding", "artifact_id"), "other-protocol"),
        (("power_protocol_binding", "content_sha256"), "0" * 64),
        (("power_protocol_binding", "artifact_sha256"), "0" * 64),
        (("calibration_fold", "fold_id"), "other-fold"),
        (("calibration_fold", "horizon_sessions"), 5),
        (("calibration_fold", "first_test_session"), "2020-02-03"),
        (("evidence_epoch_binding", "post_cutoff_corrections_included"), True),
        (("evidence_epoch_binding", "capture_instant_utc"), FIRST_TEST_SESSION_OPEN_UTC),
    ],
)
def test_manifest_scope_parent_fold_and_epoch_bindings_are_exact(
    tmp_path, admission, path, value
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: _set_path(raw, path, value),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.update({"input_artifact_path": "/secret/input.json"}),
        lambda raw: raw.update({"provider_rows": []}),
        lambda raw: raw.update({"returns": []}),
        lambda raw: raw.update({"p_value": "0.01"}),
        lambda raw: raw.update({"qc_project_id": "project"}),
        lambda raw: raw.pop("capabilities"),
        lambda raw: raw["calibration_fold"].update({"unexpected": None}),
        lambda raw: raw["evidence_epoch_binding"].pop("artifact_sha256"),
    ],
    ids=[
        "path",
        "provider-rows",
        "returns",
        "p-value",
        "qc-project",
        "missing-capabilities",
        "extra-fold-field",
        "missing-epoch-field",
    ],
)
def test_manifest_closed_shapes_refuse_paths_values_outcomes_and_qc_fields(
    tmp_path, admission, mutate
):
    paths = _write_candidate(tmp_path, admission, manifest_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


def test_manifest_declared_identity_must_be_content_derived(tmp_path, admission):
    paths = _write_candidate(
        tmp_path,
        admission,
        post_manifest_mutate=lambda raw: raw.__setitem__("manifest_hash", "0" * 64),
    )
    with pytest.raises(PowerCalibrationInputManifestError, match="content-derived"):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("complete_session_axis", "exchange"), "NASDAQ"),
        (("complete_session_axis", "key_field"), "date"),
        (("complete_session_axis", "key_format"), "ISO8601"),
        (("complete_session_axis", "session_count"), True),
        (("complete_session_axis", "session_count"), CALIBRATION_SESSION_COUNT - 1),
        (("complete_session_axis", "session_axis_sha256"), "0" * 64),
        (("complete_session_axis", "first_session"), "2018-02-01"),
        (("complete_session_axis", "last_session"), "2020-01-02"),
    ],
)
def test_complete_session_axis_metadata_is_exact(tmp_path, admission, path, value):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: _set_path(raw, path, value),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("case", ["missing", "duplicate", "reordered", "extra"])
def test_complete_session_axis_sequence_cannot_change(tmp_path, admission, case):
    def mutate(raw):
        sessions = raw["complete_session_axis"]["ordered_session_keys"]
        if case == "missing":
            sessions.pop()
        elif case == "duplicate":
            sessions[-1] = sessions[-2]
        elif case == "reordered":
            sessions[0], sessions[1] = sessions[1], sessions[0]
        else:
            sessions.append("2020-01-02")

    paths = _write_candidate(tmp_path, admission, manifest_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError, match="session axis"):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("field", tuple(CAPABILITIES))
def test_every_manifest_capability_is_independently_pinned_false(
    tmp_path, admission, field
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["capabilities"].__setitem__(field, True),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("field", tuple(CAPABILITIES))
def test_false_capabilities_cannot_be_spoofed_with_numeric_zero(
    tmp_path, admission, field
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["capabilities"].__setitem__(field, 0),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("field", tuple(MANIFEST_EXTERNAL_AUTHORITIES))
def test_every_manifest_external_authority_is_exact(tmp_path, admission, field):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["external_authorities"].__setitem__(
            field, "unexpected-authority"
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


def test_evidence_bundle_capabilities_are_also_exactly_false(tmp_path, admission):
    paths = _write_candidate(
        tmp_path,
        admission,
        evidence_mutate=lambda raw: raw["capabilities"].__setitem__(
            "qc_upload", True
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("receipt_id", "other-evidence-bundle"),
        ("receipt_schema", "vendor-permission-receipt-v1"),
        ("receipt_content_sha256", "0" * 64),
        ("receipt_artifact_sha256", "0" * 64),
        ("data_entitlement_audit_id", "other-entitlement-audit"),
        ("processing_scope_id", "qc-upload-and-redistribution"),
        ("binding_id", "synthetic-rights-binding"),
    ],
)
def test_manifest_rights_bind_the_exact_evidence_bundle_and_scope(
    tmp_path, admission, field, value
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["rights_bindings"][0].__setitem__(
            field, value
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("roles", [[], [INPUT_ROLES[0]], list(reversed(INPUT_ROLES)), ["other"]])
def test_rights_role_coverage_is_complete_ordered_and_closed(
    tmp_path, admission, roles
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["rights_bindings"][0].__setitem__(
            "applies_to_input_roles", roles
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("case", ["empty", "duplicate", "unsorted", "extra-field"])
def test_rights_binding_inventory_is_nonempty_unique_sorted_and_closed(
    tmp_path, admission, case
):
    def mutate(raw):
        rights = raw["rights_bindings"]
        if case == "empty":
            rights.clear()
        elif case == "duplicate":
            rights.append(copy.deepcopy(rights[0]))
        elif case == "unsorted":
            rights.reverse()
        else:
            rights[0]["vendor_permission"] = True

    paths = _write_candidate(tmp_path, admission, manifest_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("index", "field", "value"),
    [
        (0, "role", INPUT_ROLES[1]),
        (0, "artifact_schema", INPUT_SCHEMAS[INPUT_ROLES[1]]),
        (0, "artifact_id", "synthetic-beta-input"),
        (0, "content_sha256", "invalid"),
        (0, "artifact_sha256", "A" * 64),
        (0, "byte_count", 0),
        (0, "byte_count", True),
        (0, "record_count", CALIBRATION_SESSION_COUNT - 1),
        (0, "record_count", True),
        (0, "session_key_field", "date"),
        (0, "session_axis_sha256", "0" * 64),
        (0, "lineage_node_id", "synthetic-terminal"),
        (1, "role", INPUT_ROLES[0]),
        (1, "artifact_schema", INPUT_SCHEMAS[INPUT_ROLES[0]]),
        (1, "byte_count", -1),
    ],
)
def test_input_artifact_identity_shape_counts_and_axis_are_exact(
    tmp_path, admission, index, field, value
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["input_artifacts"][index].__setitem__(
            field, value
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw["input_artifacts"].reverse(),
        lambda raw: raw["input_artifacts"].pop(),
        lambda raw: raw["input_artifacts"][0].update({"beta_values": ["0.1"]}),
        lambda raw: raw["input_artifacts"][1].update({"component_means": ["2"]}),
    ],
    ids=["reordered", "missing", "beta-values", "component-means"],
)
def test_input_inventory_is_exact_and_cannot_smuggle_calibration_values(
    tmp_path, admission, mutate
):
    paths = _write_candidate(tmp_path, admission, manifest_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("case", ["missing", "reordered", "wrong-session", "wrong-state", "extra-field"])
def test_beta_state_inventory_covers_the_exact_axis_without_values(
    tmp_path, admission, case
):
    def mutate(raw):
        inventory = raw["input_artifacts"][0]["session_state_inventory"]
        if case == "missing":
            inventory.pop()
        elif case == "reordered":
            inventory[0], inventory[1] = inventory[1], inventory[0]
        elif case == "wrong-session":
            inventory[0]["session"] = "2018-01-30"
        elif case == "wrong-state":
            inventory[0]["state"] = "estimated"
        else:
            inventory[0]["beta"] = "0.1"

    paths = _write_candidate(tmp_path, admission, manifest_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("valid_beta_date_count", CALIBRATION_SESSION_COUNT - 1),
        ("missing_beta_date_count", 0),
        ("refused_beta_date_count", False),
        ("state_census_sha256", "0" * 64),
    ],
)
def test_beta_state_census_is_recomputed_from_the_inventory(
    tmp_path, admission, field, value
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["input_artifacts"][0].__setitem__(
            field, value
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("case", ["missing", "reordered", "wrong-session", "negative", "bool", "extra-field"])
def test_component_count_inventory_is_complete_and_exact_integer_metadata(
    tmp_path, admission, case
):
    def mutate(raw):
        inventory = raw["input_artifacts"][1]["session_count_inventory"]
        if case == "missing":
            inventory.pop()
        elif case == "reordered":
            inventory[0], inventory[1] = inventory[1], inventory[0]
        elif case == "wrong-session":
            inventory[0]["session"] = "2018-01-30"
        elif case == "negative":
            inventory[0]["connected_component_count"] = -1
        elif case == "bool":
            inventory[0]["connected_component_count"] = True
        else:
            inventory[0]["component_ids"] = []

    paths = _write_candidate(tmp_path, admission, manifest_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("component_count_census_sha256", "0" * 64),
        ("component_count_census_session_count", CALIBRATION_SESSION_COUNT - 1),
        ("missing_session_count", 1),
        ("missing_session_count", False),
    ],
)
def test_component_count_census_hash_and_counts_are_exact(
    tmp_path, admission, field, value
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["input_artifacts"][1].__setitem__(
            field, value
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    "binding_ids",
    [
        [],
        ["unknown-rights"],
        ["binding-01-massive-ratings", "binding-01-massive-ratings"],
        ["binding-02-reference-sources", "binding-01-massive-ratings"],
    ],
)
def test_each_input_requires_sorted_known_role_covering_rights(
    tmp_path, admission, binding_ids
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["input_artifacts"][0].__setitem__(
            "rights_binding_ids", binding_ids
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("producing_commit", "A" * 40),
        ("producing_tree", "1" * 39),
        ("producer_code_sha256", "not-a-hash"),
        ("build_recipe_id", "synthetic-build"),
        ("build_recipe_sha256", "A" * 64),
        ("config_sha256", "0" * 63),
    ],
)
def test_lineage_build_identity_fields_are_strict_production_metadata(
    tmp_path, admission, field, value
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["producing_lineage"].__setitem__(
            field, value
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda nodes: nodes[0].__setitem__("role", "transformation"),
        lambda nodes: nodes[0].__setitem__("rights_binding_ids", []),
        lambda nodes: nodes[0].__setitem__("artifact_sha256", "0" * 64),
        lambda nodes: nodes[2].__setitem__("role", "source_artifact"),
        lambda nodes: nodes[2].__setitem__("evidence_epoch_id", "other-epoch"),
        lambda nodes: nodes[3].__setitem__("role", INPUT_ROLES[1]),
        lambda nodes: nodes[3].__setitem__("content_sha256", "0" * 64),
        lambda nodes: nodes[3].__setitem__("parent_node_ids", []),
        lambda nodes: nodes[0].__setitem__(
            "parent_node_ids", ["lineage-transform-v1"]
        ),
        lambda nodes: nodes[2].__setitem__(
            "parent_node_ids", ["lineage-source-root-01", "lineage-source-root-01"]
        ),
        lambda nodes: nodes[2].__setitem__("rights_binding_ids", ["unknown-rights"]),
        lambda nodes: nodes[2].update({"unexpected": None}),
    ],
    ids=[
        "root-role",
        "root-rights",
        "root-snapshot-hash",
        "nonterminal-role",
        "epoch",
        "terminal-role",
        "terminal-content",
        "terminal-parent",
        "forward-parent",
        "duplicate-parent",
        "unknown-rights",
        "closed-node-fields",
    ],
)
def test_lineage_roles_edges_epoch_terminals_and_snapshot_roots_are_exact(
    tmp_path, admission, mutate
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: _mutate_lineage(raw, mutate),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


def test_lineage_node_ids_must_be_unique(tmp_path, admission):
    def mutate(nodes):
        nodes[1]["node_id"] = nodes[0]["node_id"]

    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: _mutate_lineage(raw, mutate),
    )
    with pytest.raises(PowerCalibrationInputManifestError, match="node IDs"):
        _load_candidate(admission, paths)


def test_lineage_artifact_ids_must_be_unique(tmp_path, admission):
    def mutate(nodes):
        nodes[1]["artifact_id"] = nodes[0]["artifact_id"]

    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: _mutate_lineage(raw, mutate),
    )
    with pytest.raises(PowerCalibrationInputManifestError, match="artifact IDs"):
        _load_candidate(admission, paths)


def test_lineage_cannot_contain_an_orphan(tmp_path, admission):
    def mutate(nodes):
        nodes.append(
            _copy_node(
                nodes[2],
                node_id="lineage-orphan-transform-v1",
                artifact_id="orphan-intermediate-v1",
            )
        )

    def mutate_manifest(raw):
        _mutate_lineage(raw, mutate)
        raw["manifest_counts"]["lineage_node_count"] += 1

    paths = _write_candidate(tmp_path, admission, manifest_mutate=mutate_manifest)
    with pytest.raises(PowerCalibrationInputManifestError, match="orphan"):
        _load_candidate(admission, paths)


def test_terminal_lineage_node_cannot_parent_another_terminal(tmp_path, admission):
    def mutate(nodes):
        nodes[4]["parent_node_ids"] = [nodes[3]["node_id"]]

    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: _mutate_lineage(raw, mutate),
    )
    with pytest.raises(PowerCalibrationInputManifestError, match="child"):
        _load_candidate(admission, paths)


def test_derived_lineage_rights_must_equal_the_union_inherited_from_roots(
    tmp_path, admission
):
    def mutate(raw):
        nodes = raw["producing_lineage"]["ordered_nodes"]
        nodes[2]["rights_binding_ids"] = ["binding-01-massive-ratings"]
        _rehash_lineage(raw)

    paths = _write_candidate(tmp_path, admission, manifest_mutate=mutate)
    with pytest.raises(PowerCalibrationInputManifestError, match="inherited source rights"):
        _load_candidate(admission, paths)


def test_lineage_declared_hash_is_recomputed(tmp_path, admission):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["producing_lineage"].__setitem__(
            "lineage_sha256", "0" * 64
        ),
    )
    with pytest.raises(PowerCalibrationInputManifestError, match="lineage hash"):
        _load_candidate(admission, paths)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_artifact_count", 1),
        ("rights_binding_count", 1),
        ("lineage_node_count", 3),
        ("session_key_count", CALIBRATION_SESSION_COUNT - 1),
        ("session_key_count", True),
    ],
)
def test_manifest_censuses_close_over_validated_metadata(
    tmp_path, admission, field, value
):
    paths = _write_candidate(
        tmp_path,
        admission,
        manifest_mutate=lambda raw: raw["manifest_counts"].__setitem__(field, value),
    )
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


def _noncanonical_bytes(payload: bytes, case: str) -> bytes:
    if case == "missing-newline":
        return payload.rstrip(b"\n")
    if case == "crlf":
        return payload.replace(b"\n", b"\r\n")
    if case == "bom":
        return b"\xef\xbb\xbf" + payload
    if case == "compact":
        return _canonical(json.loads(payload))
    if case == "duplicate-key":
        return payload.replace(
            b'  "authority": ',
            b'  "authority": "duplicate",\n  "authority": ',
            1,
        )
    if case == "float":
        return payload.replace(b"false", b"1.25", 1)
    if case == "nan":
        return payload.replace(b"false", b"NaN", 1)
    if case == "invalid-utf8":
        return b"\xff" + payload
    if case == "top-level-list":
        return b"[]\n"
    raise AssertionError(case)


@pytest.mark.parametrize("target", ["manifest", "evidence"])
@pytest.mark.parametrize(
    "case",
    [
        "missing-newline",
        "crlf",
        "bom",
        "compact",
        "duplicate-key",
        "float",
        "nan",
        "invalid-utf8",
        "top-level-list",
    ],
)
def test_variable_artifacts_require_strict_canonical_bounded_json_bytes(
    tmp_path, admission, target, case
):
    paths = _write_candidate(tmp_path, admission)
    index = 0 if target == "manifest" else 1
    payload_index = 4 if target == "manifest" else 5
    paths[index].write_bytes(_noncanonical_bytes(paths[payload_index], case))
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("target", ["manifest", "evidence"])
def test_variable_artifacts_refuse_the_frozen_size_limit_plus_one(
    tmp_path, admission, target
):
    paths = _write_candidate(tmp_path, admission)
    index = 0 if target == "manifest" else 1
    paths[index].write_bytes(b" " * (module.MAX_METADATA_ARTIFACT_BYTES + 1))
    with pytest.raises(PowerCalibrationInputManifestError, match="size limit"):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("target", ["manifest", "evidence"])
def test_leaf_symlink_paths_are_refused(tmp_path, admission, target):
    paths = _write_candidate(tmp_path, admission)
    index = 0 if target == "manifest" else 1
    link = tmp_path / f"linked-{target}.json"
    try:
        link.symlink_to(paths[index])
    except OSError as exc:
        pytest.skip(f"host cannot create a symlink: {exc}")
    supplied = list(paths)
    supplied[index] = link
    with pytest.raises(PowerCalibrationInputManifestError, match="link"):
        _load_candidate(admission, tuple(supplied))


@pytest.mark.parametrize("target", ["manifest", "evidence"])
def test_ancestor_symlink_paths_are_refused(tmp_path, admission, target):
    paths = _write_candidate(tmp_path, admission)
    real = tmp_path / "real"
    real.mkdir()
    index = 0 if target == "manifest" else 1
    relocated = real / paths[index].name
    shutil.copyfile(paths[index], relocated)
    link = tmp_path / "linked-parent"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host cannot create a directory symlink: {exc}")
    supplied = list(paths)
    supplied[index] = link / relocated.name
    with pytest.raises(PowerCalibrationInputManifestError, match="link"):
        _load_candidate(admission, tuple(supplied))


@pytest.mark.parametrize("target", ["manifest", "evidence"])
def test_missing_and_nonregular_variable_artifact_paths_refuse(
    tmp_path, admission, target
):
    paths = _write_candidate(tmp_path, admission)
    index = 0 if target == "manifest" else 1
    supplied = list(paths)
    supplied[index] = tmp_path / "missing.json"
    with pytest.raises(PowerCalibrationInputManifestError):
        _load_candidate(admission, tuple(supplied))
    supplied[index] = tmp_path
    with pytest.raises(PowerCalibrationInputManifestError, match="regular file"):
        _load_candidate(admission, tuple(supplied))


@pytest.mark.parametrize("target", ["manifest", "evidence"])
def test_fifo_final_components_refuse_without_blocking(tmp_path, admission, target):
    if not hasattr(os, "mkfifo"):
        pytest.skip("host does not expose POSIX FIFO creation")
    paths = _write_candidate(tmp_path, admission)
    fifo = tmp_path / f"{target}.fifo"
    try:
        os.mkfifo(fifo)
    except OSError as exc:
        pytest.skip(f"host cannot create a FIFO: {exc}")
    supplied = list(paths)
    supplied[0 if target == "manifest" else 1] = fifo
    with pytest.raises(PowerCalibrationInputManifestError, match="regular file"):
        _load_candidate(admission, tuple(supplied))


def test_admission_leaf_symlink_and_forged_parent_objects_refuse(
    tmp_path,
    parents: tuple[PowerCalibrationInputSchema, FourFamilyMultiplicityOverlay],
):
    admission_path = SPEC_ROOT / ADMISSION_FILENAME
    link = tmp_path / "admission-link.json"
    try:
        link.symlink_to(admission_path)
    except OSError as exc:
        pytest.skip(f"host cannot create a symlink: {exc}")
    with pytest.raises(PowerCalibrationInputManifestError, match="link"):
        load_power_calibration_manifest_admission(
            link, input_schema=parents[0], multiplicity_overlay=parents[1]
        )
    with pytest.raises(PowerCalibrationInputManifestError, match="parents"):
        load_power_calibration_manifest_admission(
            admission_path,
            input_schema=copy.copy(parents[0]),
            multiplicity_overlay=parents[1],
        )
    with pytest.raises(PowerCalibrationInputManifestError, match="parents"):
        load_power_calibration_manifest_admission(
            admission_path,
            input_schema=parents[0],
            multiplicity_overlay=copy.copy(parents[1]),
        )


@pytest.mark.parametrize("target", ["manifest", "evidence"])
def test_unstable_double_read_of_each_variable_artifact_refuses(
    tmp_path, admission, monkeypatch, target
):
    paths = _write_candidate(tmp_path, admission)
    watched_name = (
        "production manifest candidate" if target == "manifest" else "B2 evidence bundle"
    )
    original = artifact_io_module._bounded_descriptor_read
    calls = 0

    def unstable(descriptor, *, name, maximum_bytes):
        nonlocal calls
        payload = original(
            descriptor, name=name, maximum_bytes=maximum_bytes
        )
        if name == watched_name:
            calls += 1
            if calls == 2:
                return payload + b" "
        return payload

    monkeypatch.setattr(artifact_io_module, "_bounded_descriptor_read", unstable)
    with pytest.raises(PowerCalibrationInputManifestError, match="changed while being read"):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("target", ["manifest", "evidence"])
def test_nested_admission_reauthentication_catches_child_toctou(
    tmp_path, admission, monkeypatch, target
):
    paths = _write_candidate(tmp_path, admission)
    watched = paths[0 if target == "manifest" else 1]
    original = module.require_loaded_power_calibration_manifest_admission
    calls = 0

    def mutate_between_checks(value):
        nonlocal calls
        result = original(value)
        calls += 1
        if calls == 2:
            watched.write_bytes(watched.read_bytes() + b" ")
        return result

    monkeypatch.setattr(
        module,
        "require_loaded_power_calibration_manifest_admission",
        mutate_between_checks,
    )
    with pytest.raises(PowerCalibrationInputManifestError, match="changed"):
        _load_candidate(admission, paths)


@pytest.mark.parametrize("target", ["manifest", "evidence"])
def test_post_load_artifact_drift_revokes_candidate_authority(
    tmp_path, admission, target
):
    paths = _write_candidate(tmp_path, admission)
    candidate = _load_candidate(admission, paths)
    watched = paths[0 if target == "manifest" else 1]
    watched.write_bytes(watched.read_bytes() + b" ")
    with pytest.raises(PowerCalibrationInputManifestError, match="changed"):
        require_loaded_production_calibration_input_manifest_candidate(candidate)
    with pytest.raises(PowerCalibrationInputManifestError, match="changed"):
        _ = candidate.metadata_authenticated


def test_candidate_loader_reads_only_admission_manifest_and_evidence_metadata(
    tmp_path, admission, monkeypatch
):
    paths = _write_candidate(tmp_path, admission)
    original = module._read_stable_regular
    observed: list[tuple[Path, str]] = []

    def observe(path, name):
        observed.append((Path(path), name))
        return original(path, name)

    monkeypatch.setattr(module, "_read_stable_regular", observe)
    candidate = _load_candidate(admission, paths)
    assert candidate.metadata_authenticated is True
    assert observed == [
        (paths[1], "B2 evidence bundle"),
        (paths[0], "production manifest candidate"),
    ]
    assert all("input" not in path.name for path, _ in observed)


def test_candidate_definition_is_recursively_immutable(tmp_path, admission):
    candidate = _load_candidate(admission, _write_candidate(tmp_path, admission))
    with pytest.raises(TypeError):
        candidate.definition["manifest"] = None
    with pytest.raises(TypeError):
        candidate.definition["manifest"]["manifest_id"] = "changed"
    with pytest.raises(TypeError):
        candidate.definition["manifest"]["input_artifacts"][0]["role"] = "changed"
    with pytest.raises((TypeError, pickle.PicklingError)):
        pickle.dumps(candidate)


def test_admission_exact_contract_mutation_refuses_even_when_rehashed_and_repinning_bytes(
    tmp_path,
    monkeypatch,
    parents: tuple[PowerCalibrationInputSchema, FourFamilyMultiplicityOverlay],
):
    raw = json.loads(render_expected_power_calibration_manifest_admission())
    raw["rights_contract"]["vendor_written_permission_obtained"] = True
    _content_identity(
        raw,
        id_field="admission_contract_id",
        hash_field="admission_contract_hash",
        prefix=module.ADMISSION_CONTRACT_ID_PREFIX,
    )
    payload = _render(raw)
    path = tmp_path / ADMISSION_FILENAME
    path.write_bytes(payload)
    monkeypatch.setattr(
        module,
        "ADMISSION_CONTRACT_ARTIFACT_SHA256",
        hashlib.sha256(payload).hexdigest(),
    )
    with pytest.raises(PowerCalibrationInputManifestError, match="frozen contract"):
        load_power_calibration_manifest_admission(
            path, input_schema=parents[0], multiplicity_overlay=parents[1]
        )
