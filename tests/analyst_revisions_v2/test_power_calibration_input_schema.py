from __future__ import annotations

import ast
import copy
import dataclasses
import gc
import hashlib
import inspect
import json
import pickle
import shutil
import textwrap
import weakref
from pathlib import Path

import pytest

import research.analyst_revisions_v2.power_calibration_input_schema as module
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
    EXTERNAL_BINDINGS,
    FIRST_TEST_SESSION,
    INPUT_ROLES,
    MANIFEST_ID_PREFIX,
    MANIFEST_SCHEMA,
    POWER_PROTOCOL_ARTIFACT_SHA256,
    POWER_PROTOCOL_HASH,
    POWER_PROTOCOL_ID,
    PRODUCTION_MODE,
    SCHEMA_CONTRACT_AUTHORITY,
    SCHEMA_CONTRACT_ID_PREFIX,
    SCHEMA_CONTRACT_SCHEMA,
    SCHEMA_CONTRACT_STATUS,
    SYNTHETIC_MODE,
    PowerCalibrationInputSchema,
    PowerCalibrationInputSchemaError,
    SyntheticCalibrationInputManifestSummary,
    load_power_calibration_input_schema,
    render_expected_power_calibration_input_schema,
    require_loaded_power_calibration_input_schema,
    validate_synthetic_calibration_input_manifest_fixture,
)
from research.analyst_revisions_v2.power_calibration_protocol import (
    PowerCalibrationProtocol,
    load_power_calibration_protocol,
)


SPEC_ROOT = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "analyst_revisions_v2"
    / "specs"
)
FILENAMES = {
    "schema": "arv2_stock_power_calibration_input_manifest_schema.structural.json",
    "protocol": "arv2_stock_power_calibration_protocol.structural.json",
    "map": "arv2_global_rating_map.structural.json",
    "matched": "arv2_global_matched_comparison.structural.json",
    "successor": "arv2_stock_historical_successor.structural.json",
    "stock": "arv2_stock_historical.structural.json",
    "folds": "arv2_stock_walk_forward_folds.structural.json",
    "plan": "arv2_qc_first.draft.json",
    "base": "arv2_round0.draft.json",
}

EXPECTED_SCHEMA_ACTION_ACCESSORS = (
    "production_manifest_acceptance_available",
    "calibration_input_access_available",
    "source_access_available",
    "outcome_access_available",
    "nuisance_calibration_available",
    "authoritative_receipt_available",
    "qc_action_available",
    "deployment_available",
    "orders_available",
)
EXPECTED_SUMMARY_FALSE_ACCESSORS = (
    "production_authorized",
    "input_access_available",
    "calibration_available",
    "authoritative_receipt_available",
)
EXPECTED_CAPABILITY_FIELDS = (
    "production_manifest_acceptance",
    "calibration_input_access",
    "source_access",
    "outcome_access",
    "nuisance_calibration_compute",
    "authoritative_power_receipt",
    "power_plan_binding",
    "qc_upload",
    "qc_compile",
    "qc_launch",
    "result_disposition",
    "paper_deployment",
    "funded_deployment",
    "orders",
)
EXPECTED_SCHEMA_BINDING_FIELDS = (
    "independent_review_commit",
    "counter_review_commit",
    "production_manifest_id",
    "production_manifest_artifact_sha256",
    "data_entitlement_audit_id",
    "source_rights_receipt_id",
    "owner_calibration_input_access_authority_id",
    "owner_nuisance_calibration_authority_id",
    "numeric_power_receipt_sha256",
    "stock_successor_v3_sha256",
    "outcome_artifact_sha256",
    "qc_project_id",
    "qc_run_id",
    "evaluation_receipt_id",
)
EXPECTED_FIXTURE_AUTHORITY_FIELDS = (
    "production_registry_entry_id",
    "data_entitlement_audit_id",
    "source_rights_authority_id",
    "owner_calibration_input_access_authority_id",
    "owner_nuisance_calibration_authority_id",
    "numeric_power_receipt_sha256",
    "stock_successor_v3_sha256",
    "outcome_artifact_sha256",
    "qc_project_id",
    "qc_run_id",
    "evaluation_receipt_id",
)
EXPECTED_SCHEMA_ID = "arv2-stock-power-calibration-input-schema-4032405d1773236e"
EXPECTED_SCHEMA_CONTENT_SHA256 = (
    "4032405d1773236e61938a88c6ec77e62bbbd71ff8e24eb615565023c07f8e24"
)
EXPECTED_SCHEMA_ARTIFACT_SHA256 = (
    "e642d06531b6ca024c3ee438ee88a113eef1483f2f6fca9d0e120afcfc5ed2f1"
)


def _paths(root: Path = SPEC_ROOT) -> dict[str, Path]:
    return {name: root / filename for name, filename in FILENAMES.items()}


def _load_protocol(root: Path = SPEC_ROOT) -> PowerCalibrationProtocol:
    paths = _paths(root)
    return load_power_calibration_protocol(
        paths["protocol"],
        map_path=paths["map"],
        matched_contract_path=paths["matched"],
        successor_spec_path=paths["successor"],
        parent_stock_spec_path=paths["stock"],
        fold_manifest_path=paths["folds"],
        qc_first_plan_path=paths["plan"],
    )


def _load_schema(root: Path = SPEC_ROOT) -> PowerCalibrationInputSchema:
    return load_power_calibration_input_schema(
        _paths(root)["schema"], power_protocol=_load_protocol(root)
    )


def _clone(tmp_path: Path) -> Path:
    root = tmp_path / "specs"
    root.mkdir(parents=True)
    for filename in FILENAMES.values():
        shutil.copyfile(SPEC_ROOT / filename, root / filename)
    return root


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
) -> bytes:
    raw[id_field] = None
    raw[hash_field] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()
    raw[hash_field] = digest
    raw[id_field] = prefix + digest[:16]
    return _render(raw)


def _synthetic_fixture(schema: PowerCalibrationInputSchema) -> dict[str, object]:
    sessions = list(schema.calibration_session_axis)
    beta_states = [
        {
            "session": session,
            "state": "missing" if index == 0 else "refused" if index == 1 else "valid",
        }
        for index, session in enumerate(sessions)
    ]
    component_counts = [
        {"session": session, "connected_component_count": index % 5}
        for index, session in enumerate(sessions)
    ]
    rights = [
        {
            "binding_id": "synthetic-rights-beta",
            "receipt_id": "synthetic-receipt-beta",
            "receipt_schema": "synthetic-rights-receipt-v1",
            "receipt_content_sha256": "1" * 64,
            "receipt_artifact_sha256": "2" * 64,
            "data_entitlement_audit_id": "synthetic-entitlement-beta",
            "processing_scope_id": "synthetic_fixture_no_legal_or_access_claim",
            "applies_to_input_roles": ["date_level_beta_series"],
        },
        {
            "binding_id": "synthetic-rights-component",
            "receipt_id": "synthetic-receipt-component",
            "receipt_schema": "synthetic-rights-receipt-v1",
            "receipt_content_sha256": "3" * 64,
            "receipt_artifact_sha256": "4" * 64,
            "data_entitlement_audit_id": "synthetic-entitlement-component",
            "processing_scope_id": "synthetic_fixture_no_legal_or_access_claim",
            "applies_to_input_roles": ["component_count_census"],
        },
    ]
    inputs = [
        {
            "role": "date_level_beta_series",
            "artifact_id": "synthetic-beta-artifact",
            "artifact_schema": "arv2-power-calibration-date-beta-input-v1",
            "content_sha256": "5" * 64,
            "artifact_sha256": "6" * 64,
            "byte_count": 101,
            "record_count": CALIBRATION_SESSION_COUNT,
            "session_key_field": "decision_session",
            "session_axis_sha256": CALIBRATION_AXIS_SHA256,
            "session_state_inventory": beta_states,
            "valid_beta_date_count": CALIBRATION_SESSION_COUNT - 2,
            "missing_beta_date_count": 1,
            "refused_beta_date_count": 1,
            "state_census_sha256": hashlib.sha256(_canonical(beta_states)).hexdigest(),
            "rights_binding_ids": ["synthetic-rights-beta"],
            "lineage_node_id": "synthetic-node-beta",
        },
        {
            "role": "component_count_census",
            "artifact_id": "synthetic-component-artifact",
            "artifact_schema": "arv2-power-calibration-component-count-input-v1",
            "content_sha256": "7" * 64,
            "artifact_sha256": "8" * 64,
            "byte_count": 202,
            "record_count": CALIBRATION_SESSION_COUNT,
            "session_key_field": "decision_session",
            "session_axis_sha256": CALIBRATION_AXIS_SHA256,
            "session_count_inventory": component_counts,
            "component_count_census_sha256": hashlib.sha256(
                _canonical(component_counts)
            ).hexdigest(),
            "component_count_census_session_count": CALIBRATION_SESSION_COUNT,
            "missing_session_count": 0,
            "rights_binding_ids": ["synthetic-rights-component"],
            "lineage_node_id": "synthetic-node-component",
        },
    ]
    epoch = "synthetic-evidence-epoch"
    nodes = [
        {
            "node_id": "synthetic-node-root",
            "role": "source_artifact",
            "artifact_id": "synthetic-root-artifact",
            "schema_id": "synthetic-root-schema-v1",
            "content_sha256": "9" * 64,
            "artifact_sha256": "a" * 64,
            "evidence_epoch_id": epoch,
            "parent_node_ids": [],
            "rights_binding_ids": [
                "synthetic-rights-beta",
                "synthetic-rights-component",
            ],
        },
        {
            "node_id": "synthetic-node-beta",
            "role": inputs[0]["role"],
            "artifact_id": inputs[0]["artifact_id"],
            "schema_id": inputs[0]["artifact_schema"],
            "content_sha256": inputs[0]["content_sha256"],
            "artifact_sha256": inputs[0]["artifact_sha256"],
            "evidence_epoch_id": epoch,
            "parent_node_ids": ["synthetic-node-root"],
            "rights_binding_ids": inputs[0]["rights_binding_ids"],
        },
        {
            "node_id": "synthetic-node-component",
            "role": inputs[1]["role"],
            "artifact_id": inputs[1]["artifact_id"],
            "schema_id": inputs[1]["artifact_schema"],
            "content_sha256": inputs[1]["content_sha256"],
            "artifact_sha256": inputs[1]["artifact_sha256"],
            "evidence_epoch_id": epoch,
            "parent_node_ids": ["synthetic-node-root"],
            "rights_binding_ids": inputs[1]["rights_binding_ids"],
        },
    ]
    raw: dict[str, object] = {
        "schema": MANIFEST_SCHEMA,
        "manifest_mode": SYNTHETIC_MODE,
        "status": "synthetic_fixture_only_not_production",
        "authority": "synthetic_metadata_shape_only_no_input_or_outcome_authority",
        "manifest_id": None,
        "manifest_hash": None,
        "schema_contract_binding": {
            "artifact_id": schema.schema_contract_id,
            "content_sha256": schema.schema_contract_hash,
            "artifact_sha256": module.SCHEMA_CONTRACT_ARTIFACT_SHA256,
        },
        "power_protocol_binding": {
            "artifact_id": POWER_PROTOCOL_ID,
            "content_sha256": POWER_PROTOCOL_HASH,
            "artifact_sha256": POWER_PROTOCOL_ARTIFACT_SHA256,
        },
        "evaluation_id": "arv2-eval-stock-historical-qc-001",
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
            "evidence_epoch_id": epoch,
            "artifact_id": "synthetic-evidence-epoch-artifact",
            "semantic_sha256": "0" * 64,
            "artifact_sha256": "1" * 64,
            "capture_instant_utc": "2020-01-31T00:00:00.000000Z",
            "calibration_information_cutoff_session": "2020-01-30",
            "first_excluded_session": "2020-01-31",
            "post_cutoff_corrections_included": False,
        },
        "producing_lineage": {
            "producing_commit": "b" * 40,
            "producing_tree": "c" * 40,
            "producer_code_sha256": "d" * 64,
            "build_recipe_id": "synthetic-build-recipe",
            "build_recipe_sha256": "e" * 64,
            "config_sha256": "f" * 64,
            "ordered_nodes": nodes,
            "lineage_sha256": hashlib.sha256(_canonical(nodes)).hexdigest(),
        },
        "complete_session_axis": {
            "exchange": "XNYS",
            "key_field": "decision_session",
            "key_format": "YYYY-MM-DD",
            "ordered_session_keys": sessions,
            "session_count": CALIBRATION_SESSION_COUNT,
            "session_axis_sha256": CALIBRATION_AXIS_SHA256,
            "first_session": CALIBRATION_START,
            "last_session": CALIBRATION_LAST_SESSION,
        },
        "input_artifacts": inputs,
        "rights_bindings": rights,
        "manifest_counts": {
            "input_artifact_count": 2,
            "rights_binding_count": 2,
            "lineage_node_count": 3,
            "session_key_count": CALIBRATION_SESSION_COUNT,
        },
        "external_authorities": {
            name: None for name in EXPECTED_FIXTURE_AUTHORITY_FIELDS
        },
        "capabilities": {name: False for name in EXPECTED_CAPABILITY_FIELDS},
    }
    _content_identity(
        raw,
        id_field="manifest_id",
        hash_field="manifest_hash",
        prefix=MANIFEST_ID_PREFIX,
    )
    return raw


def _fixture_bytes(
    schema: PowerCalibrationInputSchema, mutate=None
) -> bytes:
    raw = _synthetic_fixture(schema)
    if mutate is not None:
        mutate(raw)
    return _content_identity(
        raw,
        id_field="manifest_id",
        hash_field="manifest_hash",
        prefix=MANIFEST_ID_PREFIX,
    )


def _rehash_fixture_lineage(raw: dict[str, object]) -> None:
    lineage = raw["producing_lineage"]
    lineage["lineage_sha256"] = hashlib.sha256(
        _canonical(lineage["ordered_nodes"])
    ).hexdigest()


def _set_nested(
    raw: dict[str, object], path: tuple[object, ...], value: object
) -> None:
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def _set_input_and_terminal_hash(
    raw: dict[str, object], index: int, field: str, value: object
) -> None:
    input_artifact = raw["input_artifacts"][index]
    input_artifact[field] = value
    node_id = input_artifact["lineage_node_id"]
    node = next(
        item
        for item in raw["producing_lineage"]["ordered_nodes"]
        if item["node_id"] == node_id
    )
    node[field] = value
    _rehash_fixture_lineage(raw)


@pytest.fixture(scope="module")
def schema() -> PowerCalibrationInputSchema:
    return _load_schema()


def test_checked_in_schema_is_exact_content_addressed_renderer_output():
    payload = _paths()["schema"].read_bytes()
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_SCHEMA_ARTIFACT_SHA256
    assert module.SCHEMA_CONTRACT_ARTIFACT_SHA256 == (
        EXPECTED_SCHEMA_ARTIFACT_SHA256
    )
    assert payload == render_expected_power_calibration_input_schema().encode("utf-8")
    raw = json.loads(payload)
    declared_id = raw["schema_contract_id"]
    declared_hash = raw["schema_contract_hash"]
    raw["schema_contract_id"] = None
    raw["schema_contract_hash"] = None
    digest = hashlib.sha256(_canonical(raw)).hexdigest()
    assert declared_hash == digest == EXPECTED_SCHEMA_CONTENT_SHA256
    assert declared_id == EXPECTED_SCHEMA_ID
    assert declared_id == SCHEMA_CONTRACT_ID_PREFIX + digest[:16]
    assert raw["schema"] == SCHEMA_CONTRACT_SCHEMA
    assert raw["status"] == SCHEMA_CONTRACT_STATUS
    assert raw["authority"] == SCHEMA_CONTRACT_AUTHORITY


def test_schema_binds_the_exact_power_protocol_and_complete_axis(schema):
    assert schema.schema_contract_id.startswith(SCHEMA_CONTRACT_ID_PREFIX)
    assert len(schema.schema_contract_hash) == 64
    assert schema.evaluation_id == "arv2-eval-stock-historical-qc-001"
    parent = schema.definition["bound_parent"]
    assert parent == {
        "artifact_id": POWER_PROTOCOL_ID,
        "content_sha256": POWER_PROTOCOL_HASH,
        "artifact_sha256": POWER_PROTOCOL_ARTIFACT_SHA256,
    }
    assert len(schema.calibration_session_axis) == CALIBRATION_SESSION_COUNT == 483
    assert schema.calibration_session_axis[0] == CALIBRATION_START == "2018-01-31"
    assert (
        schema.calibration_session_axis[-1]
        == CALIBRATION_LAST_SESSION
        == "2019-12-31"
    )
    assert hashlib.sha256(_canonical(schema.calibration_session_axis)).hexdigest() == (
        CALIBRATION_AXIS_SHA256
    )
    boundary = schema.definition["calibration_boundary_contract"]
    assert boundary["fold_id"] == CALIBRATION_FOLD_ID
    assert boundary["structural_fold_sha256"] == CALIBRATION_FOLD_HASH
    assert boundary["validation_start_inclusive"] == CALIBRATION_START
    assert boundary["validation_end_exclusive"] == CALIBRATION_END_EXCLUSIVE
    assert boundary["last_included_decision_session"] == CALIBRATION_LAST_SESSION
    assert boundary["last_included_h20_outcome_session"] == (
        CALIBRATION_LAST_OUTCOME_SESSION
    )
    assert boundary["first_test_session"] == FIRST_TEST_SESSION


def test_schema_is_an_additive_non_authoritative_leaf(schema):
    graph = schema.lineage_graph
    assert dict(graph) == {
        "strategy_pdf": (),
        "qc_base": ("strategy_pdf",),
        "qc_plan": ("strategy_pdf", "qc_base"),
        "stock_v1": ("strategy_pdf", "qc_plan"),
        "fold_manifest": ("strategy_pdf", "qc_plan", "stock_v1"),
        "global_map": ("strategy_pdf",),
        "matched_contract": (
            "strategy_pdf",
            "stock_v1",
            "fold_manifest",
            "global_map",
        ),
        "stock_v2": (
            "strategy_pdf",
            "qc_plan",
            "stock_v1",
            "fold_manifest",
            "global_map",
            "matched_contract",
        ),
        "power_protocol": (
            "strategy_pdf",
            "qc_plan",
            "stock_v1",
            "fold_manifest",
            "global_map",
            "matched_contract",
            "stock_v2",
        ),
        "calibration_input_manifest_schema": ("power_protocol",),
    }
    assert not any(
        "calibration_input_manifest_schema" in parents
        for node, parents in graph.items()
        if node != "calibration_input_manifest_schema"
    )
    assert schema.definition["future_production_gate"][
        "production_manifest_loader_implemented"
    ] is False


def test_schema_grants_no_input_outcome_calibration_qc_or_trading_action(schema):
    processing = schema.definition["processing_contract"]
    assert processing["manifest_validation_reads_input_artifacts"] is False
    assert processing["manifest_validation_computes_calibration"] is False
    assert processing["synthetic_fixture_result_is_authoritative"] is False
    gate = schema.definition["future_production_gate"]
    assert gate["production_manifest_loader_implemented"] is False
    assert gate["input_artifact_loader_implemented"] is False
    assert gate["numeric_receipt_implemented"] is False
    assert gate["separate_owner_input_access_authority_required"] is True
    assert gate["separate_authenticated_rights_required"] is True
    assert gate["separate_nuisance_computation_authority_required"] is True


def test_schema_external_bindings_and_capabilities_are_exactly_closed(schema):
    assert tuple(EXTERNAL_BINDINGS) == EXPECTED_SCHEMA_BINDING_FIELDS
    assert tuple(schema.definition["external_bindings"]) == (
        EXPECTED_SCHEMA_BINDING_FIELDS
    )
    assert all(value is None for value in EXTERNAL_BINDINGS.values())
    assert all(
        value is None for value in schema.definition["external_bindings"].values()
    )
    assert tuple(CAPABILITIES) == EXPECTED_CAPABILITY_FIELDS
    assert tuple(schema.capabilities) == EXPECTED_CAPABILITY_FIELDS
    assert all(
        type(value) is bool and value is False for value in CAPABILITIES.values()
    )
    assert all(
        type(value) is bool and value is False
        for value in schema.capabilities.values()
    )
    for name in EXPECTED_SCHEMA_ACTION_ACCESSORS:
        assert getattr(schema, name) is False


def _literal_property_value(owner: type, name: str, expected: object) -> None:
    accessor = getattr(owner, name)
    assert isinstance(accessor, property)
    tree = ast.parse(textwrap.dedent(inspect.getsource(accessor.fget)))
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    body = [
        node
        for node in function.body
        if not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
    ]
    assert len(body) == 1 and isinstance(body[0], ast.Return)
    assert isinstance(body[0].value, ast.Constant)
    assert body[0].value.value is expected


@pytest.mark.parametrize("name", EXPECTED_SCHEMA_ACTION_ACCESSORS)
def test_every_schema_action_accessor_is_literal_false(name):
    _literal_property_value(PowerCalibrationInputSchema, name, False)


@pytest.mark.parametrize("name", EXPECTED_SUMMARY_FALSE_ACCESSORS)
def test_every_synthetic_summary_action_accessor_is_literal_false(name):
    _literal_property_value(SyntheticCalibrationInputManifestSummary, name, False)


def test_synthetic_summary_marker_is_literal_true():
    _literal_property_value(
        SyntheticCalibrationInputManifestSummary, "synthetic_only", True
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: b"\xef\xbb\xbf" + payload,
        lambda payload: payload.replace(b"\n", b"\r\n"),
        lambda payload: b" " + payload,
        lambda payload: payload + b" ",
        lambda payload: payload.replace(b"{\n", b"{  \n", 1),
        lambda payload: payload[:-2] + b"\xff\n",
        lambda payload: b'{"schema":"duplicate",' + payload[1:],
        lambda payload: payload.replace(
            b'"session_count": 483', b'"session_count": 483.0', 1
        ),
        lambda payload: payload.replace(
            b'"session_count": 483', b'"session_count": NaN', 1
        ),
    ),
)
def test_noncanonical_or_malformed_schema_artifact_bytes_refuse(tmp_path, mutate):
    path = tmp_path / FILENAMES["schema"]
    path.write_bytes(mutate(_paths()["schema"].read_bytes()))
    with pytest.raises(PowerCalibrationInputSchemaError):
        load_power_calibration_input_schema(path, power_protocol=_load_protocol())


def test_schema_loader_refuses_unstable_bytes_and_stat_identity(tmp_path, monkeypatch):
    path = tmp_path / FILENAMES["schema"]
    path.write_bytes(_paths()["schema"].read_bytes())
    target = path.absolute()
    original_read = Path.read_bytes
    reads = 0

    def unstable_read(candidate):
        nonlocal reads
        payload = original_read(candidate)
        if candidate.absolute() == target:
            reads += 1
            if reads == 2:
                return payload + b" "
        return payload

    monkeypatch.setattr(Path, "read_bytes", unstable_read)
    with pytest.raises(PowerCalibrationInputSchemaError, match="changed while"):
        load_power_calibration_input_schema(path, power_protocol=_load_protocol())


def test_schema_loader_refuses_stat_identity_change(tmp_path, monkeypatch):
    path = tmp_path / FILENAMES["schema"]
    path.write_bytes(_paths()["schema"].read_bytes())
    target = path.absolute()
    original_read = Path.read_bytes
    original_stat = Path.stat
    reads = 0

    def tracked_read(candidate):
        nonlocal reads
        payload = original_read(candidate)
        if candidate.absolute() == target:
            reads += 1
        return payload

    def changed_stat(candidate, *args, **kwargs):
        value = original_stat(candidate, *args, **kwargs)
        if candidate.absolute() == target and reads >= 2:
            return type(
                "ChangedStat",
                (),
                {
                    "st_dev": value.st_dev,
                    "st_ino": value.st_ino,
                    "st_size": value.st_size,
                    "st_mtime_ns": value.st_mtime_ns + 1,
                },
            )()
        return value

    monkeypatch.setattr(Path, "read_bytes", tracked_read)
    monkeypatch.setattr(Path, "stat", changed_stat)
    with pytest.raises(PowerCalibrationInputSchemaError, match="changed while"):
        load_power_calibration_input_schema(path, power_protocol=_load_protocol())


def _junction(link: Path, target: Path) -> None:
    try:
        import _winapi
    except ImportError:
        pytest.skip("directory junctions are Windows-only")
    try:
        _winapi.CreateJunction(str(target), str(link))
    except OSError as exc:
        pytest.skip(f"host cannot create junction: {exc}")
    assert link.is_junction()


def test_schema_path_refuses_a_leaf_symlink(tmp_path):
    original = _paths()["schema"]
    linked = tmp_path / "linked-schema.json"
    try:
        linked.symlink_to(original)
    except OSError as exc:
        pytest.skip(f"host cannot create symlink: {exc}")
    with pytest.raises(PowerCalibrationInputSchemaError, match="link"):
        load_power_calibration_input_schema(linked, power_protocol=_load_protocol())


def test_schema_path_through_a_symlinked_ancestor_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    shutil.copyfile(_paths()["schema"], real / FILENAMES["schema"])
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"host cannot create directory symlink: {exc}")
    with pytest.raises(PowerCalibrationInputSchemaError, match="link"):
        load_power_calibration_input_schema(
            linked / FILENAMES["schema"], power_protocol=_load_protocol()
        )


def test_schema_path_through_a_junction_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    shutil.copyfile(_paths()["schema"], real / FILENAMES["schema"])
    linked = tmp_path / "linked"
    _junction(linked, real)
    with pytest.raises(PowerCalibrationInputSchemaError, match="link"):
        load_power_calibration_input_schema(
            linked / FILENAMES["schema"], power_protocol=_load_protocol()
        )


def test_schema_revalidates_child_around_parent_authentication(tmp_path, monkeypatch):
    path = tmp_path / FILENAMES["schema"]
    path.write_bytes(_paths()["schema"].read_bytes())
    original = module.require_loaded_power_calibration_protocol
    calls = 0

    def mutate_after_parent_check(parent):
        nonlocal calls
        result = original(parent)
        calls += 1
        if calls == 2:
            path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(
        module, "require_loaded_power_calibration_protocol", mutate_after_parent_check
    )
    with pytest.raises(PowerCalibrationInputSchemaError, match="changed after"):
        load_power_calibration_input_schema(path, power_protocol=_load_protocol())


def test_require_revalidates_child_around_parent_authentication(
    tmp_path, monkeypatch
):
    root = _clone(tmp_path)
    loaded = _load_schema(root)
    path = _paths(root)["schema"]
    original = module.require_loaded_power_calibration_protocol

    def mutate_after_parent_check(parent):
        result = original(parent)
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(
        module, "require_loaded_power_calibration_protocol", mutate_after_parent_check
    )
    with pytest.raises(PowerCalibrationInputSchemaError, match="changed after"):
        require_loaded_power_calibration_input_schema(loaded)


def test_schema_loader_refuses_missing_directory_and_forged_parent(tmp_path):
    parent = _load_protocol()
    with pytest.raises(PowerCalibrationInputSchemaError):
        load_power_calibration_input_schema(
            tmp_path / "missing.json", power_protocol=parent
        )
    with pytest.raises(PowerCalibrationInputSchemaError, match="regular file"):
        load_power_calibration_input_schema(tmp_path, power_protocol=parent)
    with pytest.raises(PowerCalibrationInputSchemaError, match="not authenticated"):
        load_power_calibration_input_schema(
            _paths()["schema"], power_protocol=copy.copy(parent)
        )


def test_require_reauthenticates_schema_and_parent_sources(tmp_path):
    root = _clone(tmp_path)
    loaded = _load_schema(root)
    _paths(root)["schema"].write_bytes(_paths(root)["schema"].read_bytes() + b" ")
    with pytest.raises(PowerCalibrationInputSchemaError, match="changed after"):
        require_loaded_power_calibration_input_schema(loaded)

    root = _clone(tmp_path / "parent")
    loaded = _load_schema(root)
    _paths(root)["protocol"].write_bytes(
        _paths(root)["protocol"].read_bytes() + b" "
    )
    with pytest.raises(PowerCalibrationInputSchemaError, match="parent changed"):
        require_loaded_power_calibration_input_schema(loaded)


def test_copy_reconstruction_pickle_and_mutation_never_create_schema_authority():
    loaded = _load_schema()
    for invalid in (None, {}, copy.copy(loaded)):
        with pytest.raises(PowerCalibrationInputSchemaError):
            require_loaded_power_calibration_input_schema(invalid)

    forged = object.__new__(PowerCalibrationInputSchema)
    for field in dataclasses.fields(PowerCalibrationInputSchema):
        object.__setattr__(forged, field.name, getattr(loaded, field.name))
    with pytest.raises(PowerCalibrationInputSchemaError):
        require_loaded_power_calibration_input_schema(forged)

    try:
        round_trip = pickle.loads(pickle.dumps(loaded))
    except (TypeError, pickle.PicklingError):
        round_trip = None
    if round_trip is not None:
        with pytest.raises(PowerCalibrationInputSchemaError):
            require_loaded_power_calibration_input_schema(round_trip)

    with pytest.raises(TypeError):
        dataclasses.replace(loaded, schema_contract_hash="0" * 64)
    object.__setattr__(
        loaded, "schema_contract_id", loaded.schema_contract_id + "x"
    )
    with pytest.raises(PowerCalibrationInputSchemaError, match="changed after"):
        require_loaded_power_calibration_input_schema(loaded)


@pytest.mark.parametrize(
    "field,replacement",
    (
        ("calibration_session_axis", ["2018-01-31"]),
        ("definition", {}),
        ("lineage_graph", {}),
        ("capabilities", {}),
    ),
)
def test_low_level_schema_collection_substitution_is_detected(
    field, replacement
):
    loaded = _load_schema()
    object.__setattr__(loaded, field, replacement)
    with pytest.raises(PowerCalibrationInputSchemaError):
        require_loaded_power_calibration_input_schema(loaded)


def test_equality_spoofed_session_axis_member_is_detected():
    class SpoofedStr(str):
        pass

    loaded = _load_schema()
    axis = list(loaded.calibration_session_axis)
    axis[0] = SpoofedStr(axis[0])
    object.__setattr__(loaded, "calibration_session_axis", tuple(axis))
    with pytest.raises(PowerCalibrationInputSchemaError, match="changed type"):
        require_loaded_power_calibration_input_schema(loaded)


def test_schema_authority_weakref_cleanup():
    schema = _load_schema()
    identity = id(schema)
    reference = weakref.ref(schema)
    assert identity in module._POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITIES
    del schema
    gc.collect()
    assert reference() is None
    assert identity not in module._POWER_CALIBRATION_INPUT_SCHEMA_AUTHORITIES


def test_valid_canonical_synthetic_fixture_is_diagnostic_only(schema):
    raw = _synthetic_fixture(schema)
    summary = validate_synthetic_calibration_input_manifest_fixture(
        schema, _fixture_bytes(schema)
    )
    assert isinstance(summary, SyntheticCalibrationInputManifestSummary)
    assert summary.manifest_id == raw["manifest_id"]
    assert summary.manifest_hash == raw["manifest_hash"]
    assert summary.evidence_epoch_id == "synthetic-evidence-epoch"
    assert summary.session_count == CALIBRATION_SESSION_COUNT
    assert summary.input_roles == INPUT_ROLES == (
        "date_level_beta_series",
        "component_count_census",
    )
    assert summary.input_artifact_count == 2
    assert summary.rights_binding_count == 2
    assert summary.lineage_node_count == 3
    assert summary.synthetic_only is True
    for name in EXPECTED_SUMMARY_FALSE_ACCESSORS:
        assert getattr(summary, name) is False
    assert tuple(summary.definition["external_authorities"]) == (
        EXPECTED_FIXTURE_AUTHORITY_FIELDS
    )
    assert all(
        value is None for value in summary.definition["external_authorities"].values()
    )
    assert all(
        type(value) is bool and value is False
        for value in summary.definition["capabilities"].values()
    )
    beta = summary.definition["input_artifacts"][0]
    beta_census = beta["session_state_inventory"]
    assert len(beta_census) == CALIBRATION_SESSION_COUNT == 483
    assert tuple(item["session"] for item in beta_census) == (
        schema.calibration_session_axis
    )
    assert {
        state: sum(item["state"] == state for item in beta_census)
        for state in ("valid", "missing", "refused")
    } == {
        "valid": beta["valid_beta_date_count"],
        "missing": beta["missing_beta_date_count"],
        "refused": beta["refused_beta_date_count"],
    }
    assert hashlib.sha256(
        _canonical([dict(item) for item in beta_census])
    ).hexdigest() == (
        beta["state_census_sha256"]
    )
    component = summary.definition["input_artifacts"][1]
    component_census = component["session_count_inventory"]
    assert len(component_census) == CALIBRATION_SESSION_COUNT
    assert tuple(item["session"] for item in component_census) == (
        schema.calibration_session_axis
    )
    assert all(
        type(item["connected_component_count"]) is int
        and item["connected_component_count"] >= 0
        for item in component_census
    )
    assert hashlib.sha256(
        _canonical([dict(item) for item in component_census])
    ).hexdigest() == (
        component["component_count_census_sha256"]
    )
    with pytest.raises(TypeError):
        summary.definition["manifest_mode"] = PRODUCTION_MODE
    with pytest.raises(TypeError):
        SyntheticCalibrationInputManifestSummary()


def test_fixture_validation_requires_the_exact_loader_authenticated_schema(schema):
    payload = _fixture_bytes(schema)
    with pytest.raises(PowerCalibrationInputSchemaError):
        validate_synthetic_calibration_input_manifest_fixture(
            copy.copy(schema), payload
        )


def test_fixture_validation_reauthenticates_schema_after_validation(
    tmp_path, monkeypatch
):
    root = _clone(tmp_path)
    loaded = _load_schema(root)
    payload = _fixture_bytes(loaded)
    path = _paths(root)["schema"]
    original = module._validate_producing_lineage

    def mutate_schema_after_fixture_lineage(*args, **kwargs):
        result = original(*args, **kwargs)
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(
        module, "_validate_producing_lineage", mutate_schema_after_fixture_lineage
    )
    with pytest.raises(PowerCalibrationInputSchemaError, match="changed after"):
        validate_synthetic_calibration_input_manifest_fixture(loaded, payload)


def test_synthetic_fixture_honestly_preserves_zero_component_counts(schema):
    summary = validate_synthetic_calibration_input_manifest_fixture(
        schema, _fixture_bytes(schema)
    )
    census = summary.definition["input_artifacts"][1]["session_count_inventory"]
    assert len(census) == CALIBRATION_SESSION_COUNT
    assert census[0]["connected_component_count"] == 0
    assert any(item["connected_component_count"] > 0 for item in census)


@pytest.mark.parametrize(
    "name,mutate,match",
    (
        ("bom", lambda value: b"\xef\xbb\xbf" + value, "BOM"),
        ("crlf", lambda value: value.replace(b"\n", b"\r\n"), "canonical"),
        ("leading", lambda value: b" " + value, "canonical"),
        ("trailing", lambda value: value + b" ", "canonical"),
        ("indent", lambda value: value.replace(b"{\n", b"{  \n", 1), "canonical"),
        ("invalid_utf8", lambda value: value[:-2] + b"\xff\n", "UTF-8"),
        (
            "duplicate",
            lambda value: b'{"schema":"duplicate",' + value[1:],
            "duplicate JSON key",
        ),
        (
            "float",
            lambda value: value.replace(
                b'"byte_count": 101', b'"byte_count": 101.0', 1
            ),
            "floating-point",
        ),
        (
            "nonfinite",
            lambda value: value.replace(b'"byte_count": 101', b'"byte_count": NaN', 1),
            "non-finite",
        ),
        ("top_level_list", lambda value: b"[]\n", "JSON object"),
    ),
)
def test_synthetic_fixture_requires_strict_canonical_json_bytes(
    schema, name, mutate, match
):
    del name
    with pytest.raises(PowerCalibrationInputSchemaError, match=match):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, mutate(_fixture_bytes(schema))
        )


@pytest.mark.parametrize("payload", (None, "{}", bytearray(b"{}"), memoryview(b"{}")))
def test_synthetic_fixture_requires_exact_bytes(schema, payload):
    with pytest.raises(PowerCalibrationInputSchemaError, match="must be bytes"):
        validate_synthetic_calibration_input_manifest_fixture(schema, payload)


def test_pathological_json_errors_are_normalized_to_the_schema_domain(schema):
    huge = _fixture_bytes(schema).replace(
        b'"byte_count": 101', b'"byte_count": ' + b"1" * 5000, 1
    )
    with pytest.raises(PowerCalibrationInputSchemaError, match="invalid JSON"):
        validate_synthetic_calibration_input_manifest_fixture(schema, huge)
    deeply_nested = b"[" * 2000 + b"0" + b"]" * 2000
    with pytest.raises(PowerCalibrationInputSchemaError):
        validate_synthetic_calibration_input_manifest_fixture(schema, deeply_nested)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: raw.__setitem__("date_level_beta_values", []),
        lambda raw: raw["input_artifacts"][0].__setitem__("beta_values", []),
        lambda raw: raw["input_artifacts"][1].__setitem__("security_returns", []),
        lambda raw: raw["producing_lineage"].__setitem__("p_value", "0.01"),
    ),
)
def test_forbidden_values_cannot_be_smuggled_into_closed_fields(schema, mutate):
    with pytest.raises(PowerCalibrationInputSchemaError, match="fields are not exact"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


def test_production_mode_is_explicitly_unimplemented(schema):
    def mutate(raw):
        raw["manifest_mode"] = PRODUCTION_MODE

    with pytest.raises(PowerCalibrationInputSchemaError, match="not implemented"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize(
    "field,value",
    (
        ("status", "synthetic_fixture_only_pending_review"),
        ("authority", "synthetic_fixture_with_input_access_authority"),
    ),
)
def test_synthetic_status_and_authority_are_independently_exact(
    schema, field, value
):
    def mutate(raw):
        raw[field] = value

    with pytest.raises(PowerCalibrationInputSchemaError, match="scope changed"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: raw["schema_contract_binding"].__setitem__(
            "content_sha256", "0" * 64
        ),
        lambda raw: raw["power_protocol_binding"].__setitem__(
            "artifact_sha256", "0" * 64
        ),
        lambda raw: raw.__setitem__("evaluation_id", "synthetic-other-evaluation"),
        lambda raw: raw["calibration_fold"].__setitem__("horizon_sessions", 5),
    ),
)
def test_fixture_exactly_binds_schema_protocol_evaluation_and_fold(schema, mutate):
    with pytest.raises(PowerCalibrationInputSchemaError):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize(
    "field,value,match",
    (
        ("evidence_epoch_id", "production-evidence-epoch", "synthetic-prefixed"),
        ("artifact_id", "production-evidence-artifact", "synthetic-prefixed"),
        ("semantic_sha256", "not-a-sha256", "SHA-256"),
        ("artifact_sha256", "not-a-sha256", "SHA-256"),
        ("capture_instant_utc", "2020-01-31T00:00:00Z", "capture"),
        ("capture_instant_utc", "2020-01-30T23:59:59.999999Z", "capture"),
        (
            "calibration_information_cutoff_session",
            "2020-01-29",
            "cutoff",
        ),
        ("first_excluded_session", "2020-02-03", "cutoff|correction"),
        ("post_cutoff_corrections_included", True, "cutoff|correction"),
        ("post_cutoff_corrections_included", 0, "cutoff|correction"),
        ("post_cutoff_corrections_included", None, "cutoff|correction"),
    ),
)
def test_evidence_epoch_binding_is_exact_and_cutoff_bound(
    schema, field, value, match
):
    def mutate(raw):
        raw["evidence_epoch_binding"][field] = value

    with pytest.raises(PowerCalibrationInputSchemaError, match=match):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


def test_lineage_epoch_must_match_the_bound_evidence_epoch(schema):
    def mutate(raw):
        raw["producing_lineage"]["ordered_nodes"][0][
            "evidence_epoch_id"
        ] = "synthetic-drifted-evidence-epoch"
        _rehash_fixture_lineage(raw)

    with pytest.raises(PowerCalibrationInputSchemaError, match="evidence epoch"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: raw.__setitem__("manifest_id", "wrong"),
        lambda raw: raw.__setitem__("manifest_hash", "0" * 64),
    ),
)
def test_fixture_declared_identity_must_be_content_derived(schema, mutate):
    raw = _synthetic_fixture(schema)
    mutate(raw)
    with pytest.raises(PowerCalibrationInputSchemaError, match="identity"):
        validate_synthetic_calibration_input_manifest_fixture(schema, _render(raw))


def test_fixture_manifest_hash_requires_lowercase_sha256_syntax(schema):
    raw = _synthetic_fixture(schema)
    raw["manifest_hash"] = "not-a-sha256"
    with pytest.raises(PowerCalibrationInputSchemaError, match="SHA-256"):
        validate_synthetic_calibration_input_manifest_fixture(schema, _render(raw))


@pytest.mark.parametrize(
    "path",
    (
        ("evidence_epoch_binding", "semantic_sha256"),
        ("evidence_epoch_binding", "artifact_sha256"),
        ("rights_bindings", 0, "receipt_content_sha256"),
        ("rights_bindings", 0, "receipt_artifact_sha256"),
        ("rights_bindings", 1, "receipt_content_sha256"),
        ("rights_bindings", 1, "receipt_artifact_sha256"),
        ("producing_lineage", "producer_code_sha256"),
        ("producing_lineage", "build_recipe_sha256"),
        ("producing_lineage", "config_sha256"),
        ("producing_lineage", "ordered_nodes", 0, "content_sha256"),
        ("producing_lineage", "ordered_nodes", 0, "artifact_sha256"),
    ),
)
def test_every_free_manifest_hash_requires_lowercase_sha256_syntax(
    schema, path
):
    def mutate(raw):
        _set_nested(raw, path, "NOT-A-LOWERCASE-SHA256")
        if path[:2] == ("producing_lineage", "ordered_nodes"):
            _rehash_fixture_lineage(raw)

    with pytest.raises(PowerCalibrationInputSchemaError, match="SHA-256"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize("index", (0, 1))
@pytest.mark.parametrize("field", ("content_sha256", "artifact_sha256"))
def test_cross_bound_input_and_terminal_hashes_require_sha256_syntax(
    schema, index, field
):
    def mutate(raw):
        _set_input_and_terminal_hash(raw, index, field, "not-a-sha256")

    with pytest.raises(PowerCalibrationInputSchemaError, match="SHA-256"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize("field", ("producing_commit", "producing_tree"))
@pytest.mark.parametrize("value", ("f" * 39, "F" * 40, False))
def test_producing_git_objects_require_exact_lowercase_40_hex(
    schema, field, value
):
    def mutate(raw):
        raw["producing_lineage"][field] = value

    with pytest.raises(PowerCalibrationInputSchemaError, match="Git object"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize(
    "mutate,match",
    (
        (
            lambda raw: raw["rights_bindings"][0].__setitem__(
                "binding_id", "rights-beta"
            ),
            "synthetic-prefixed",
        ),
        (
            lambda raw: raw["rights_bindings"][0].__setitem__(
                "receipt_id", "production-receipt"
            ),
            "synthetic-prefixed",
        ),
        (
            lambda raw: raw["rights_bindings"][0].__setitem__(
                "receipt_schema", "production-rights-receipt-v1"
            ),
            "rights schema",
        ),
        (
            lambda raw: raw["rights_bindings"][0].__setitem__(
                "processing_scope_id", "legal_rights_confirmed"
            ),
            "legal claim",
        ),
        (
            lambda raw: raw["rights_bindings"][0].__setitem__(
                "applies_to_input_roles", []
            ),
            "role inventory",
        ),
        (
            lambda raw: raw["rights_bindings"].reverse(),
            "ID-sorted",
        ),
        (
            lambda raw: raw["rights_bindings"].pop(),
            "cover both",
        ),
        (
            lambda raw: raw["input_artifacts"][0].__setitem__(
                "rights_binding_ids", ["synthetic-rights-component"]
            ),
            "rights binding",
        ),
    ),
)
def test_synthetic_rights_are_exact_metadata_not_access_authority(
    schema, mutate, match
):
    with pytest.raises(PowerCalibrationInputSchemaError, match=match):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize("target", EXPECTED_FIXTURE_AUTHORITY_FIELDS)
def test_no_synthetic_external_authority_can_be_asserted(schema, target):
    def mutate(raw):
        raw["external_authorities"][target] = "synthetic-forged-authority"

    with pytest.raises(PowerCalibrationInputSchemaError, match="authorities"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize("field", EXPECTED_CAPABILITY_FIELDS)
@pytest.mark.parametrize("value", (True, 0, 1, None))
def test_every_synthetic_capability_is_independently_exact_false(
    schema, field, value
):
    def mutate(raw):
        raw["capabilities"][field] = value

    if value is False:  # pragma: no cover - parameter inventory excludes it
        raise AssertionError("mutation must differ")
    with pytest.raises(PowerCalibrationInputSchemaError, match="capabilities"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: raw["complete_session_axis"]["ordered_session_keys"].pop(),
        lambda raw: raw["complete_session_axis"]["ordered_session_keys"].append(
            "2020-01-02"
        ),
        lambda raw: raw["complete_session_axis"]["ordered_session_keys"].__setitem__(
            100, raw["complete_session_axis"]["ordered_session_keys"][99]
        ),
        lambda raw: raw["complete_session_axis"]["ordered_session_keys"].__setitem__(
            100, "2018-07-04"
        ),
        lambda raw: raw["complete_session_axis"].__setitem__("session_count", 482),
        lambda raw: raw["complete_session_axis"].__setitem__(
            "session_axis_sha256", "0" * 64
        ),
        lambda raw: raw["complete_session_axis"].__setitem__(
            "first_session", "2018-02-01"
        ),
        lambda raw: raw["complete_session_axis"].__setitem__(
            "last_session", "2019-12-30"
        ),
    ),
)
def test_complete_axis_refuses_missing_extra_duplicate_reordered_or_drifted_keys(
    schema, mutate
):
    with pytest.raises(PowerCalibrationInputSchemaError, match="session axis"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


def _swap_first_two(records):
    records[0], records[1] = records[1], records[0]


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: raw["input_artifacts"][0]["session_state_inventory"].pop(),
        lambda raw: _swap_first_two(
            raw["input_artifacts"][0]["session_state_inventory"]
        ),
        lambda raw: raw["input_artifacts"][0]["session_state_inventory"][0].__setitem__(
            "session", "2018-02-01"
        ),
        lambda raw: raw["input_artifacts"][0]["session_state_inventory"][0].__setitem__(
            "state", "zero_filled"
        ),
        lambda raw: raw["input_artifacts"][0]["session_state_inventory"][0].__setitem__(
            "state", []
        ),
        lambda raw: raw["input_artifacts"][0].__setitem__(
            "valid_beta_date_count", 482
        ),
        lambda raw: raw["input_artifacts"][0].__setitem__(
            "missing_beta_date_count", True
        ),
        lambda raw: raw["input_artifacts"][0].__setitem__(
            "refused_beta_date_count", -1
        ),
        lambda raw: raw["input_artifacts"][0].__setitem__(
            "state_census_sha256", "0" * 64
        ),
    ),
)
def test_beta_state_census_preserves_every_axis_position_and_exact_counts(
    schema, mutate
):
    with pytest.raises(PowerCalibrationInputSchemaError):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: raw["input_artifacts"][1]["session_count_inventory"].pop(),
        lambda raw: _swap_first_two(
            raw["input_artifacts"][1]["session_count_inventory"]
        ),
        lambda raw: raw["input_artifacts"][1]["session_count_inventory"][0].__setitem__(
            "session", "2018-02-01"
        ),
        lambda raw: raw["input_artifacts"][1]["session_count_inventory"][0].__setitem__(
            "connected_component_count", True
        ),
        lambda raw: raw["input_artifacts"][1]["session_count_inventory"][0].__setitem__(
            "connected_component_count", -1
        ),
        lambda raw: raw["input_artifacts"][1]["session_count_inventory"][0].__setitem__(
            "connected_component_count", "0"
        ),
        lambda raw: raw["input_artifacts"][1].__setitem__(
            "component_count_census_sha256", "0" * 64
        ),
        lambda raw: raw["input_artifacts"][1].__setitem__(
            "component_count_census_session_count", 482
        ),
        lambda raw: raw["input_artifacts"][1].__setitem__(
            "missing_session_count", 1
        ),
    ),
)
def test_component_census_requires_all_483_ordered_nonnegative_integer_counts(
    schema, mutate
):
    with pytest.raises(PowerCalibrationInputSchemaError):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize(
    "field,value",
    (
        ("byte_count", 0),
        ("byte_count", False),
        ("record_count", 482),
        ("record_count", True),
        ("record_count", "483"),
        ("session_key_field", "date"),
        ("session_axis_sha256", "0" * 64),
    ),
)
@pytest.mark.parametrize("index", (0, 1))
def test_input_artifact_types_counts_and_session_binding_are_exact(
    schema, index, field, value
):
    def mutate(raw):
        raw["input_artifacts"][index][field] = value

    with pytest.raises(PowerCalibrationInputSchemaError):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


def test_input_artifact_role_order_and_identity_are_closed(schema):
    mutations = (
        lambda raw: raw["input_artifacts"].reverse(),
        lambda raw: raw["input_artifacts"].pop(),
        lambda raw: raw["input_artifacts"][0].__setitem__(
            "role", "component_count_census"
        ),
        lambda raw: raw["input_artifacts"][1].__setitem__(
            "artifact_id", raw["input_artifacts"][0]["artifact_id"]
        ),
        lambda raw: raw["input_artifacts"][0].__setitem__(
            "artifact_schema", "synthetic-wrong-schema"
        ),
    )
    for mutate in mutations:
        with pytest.raises(PowerCalibrationInputSchemaError):
            validate_synthetic_calibration_input_manifest_fixture(
                schema, _fixture_bytes(schema, mutate)
            )


@pytest.mark.parametrize(
    "field",
    (
        "input_artifact_count",
        "rights_binding_count",
        "lineage_node_count",
        "session_key_count",
    ),
)
@pytest.mark.parametrize("value", (False, -1, 999))
def test_manifest_declared_counts_are_exact_and_cross_checked(schema, field, value):
    def mutate(raw):
        raw["manifest_counts"][field] = value

    with pytest.raises(PowerCalibrationInputSchemaError):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: raw["producing_lineage"]["ordered_nodes"][1].__setitem__(
            "parent_node_ids", ["synthetic-unknown-parent"]
        ),
        lambda raw: raw["producing_lineage"]["ordered_nodes"][1].__setitem__(
            "node_id", "synthetic-node-root"
        ),
        lambda raw: raw["producing_lineage"]["ordered_nodes"][1].__setitem__(
            "evidence_epoch_id", "synthetic-other-epoch"
        ),
        lambda raw: raw["producing_lineage"]["ordered_nodes"][1].__setitem__(
            "artifact_sha256", "0" * 64
        ),
        lambda raw: raw["input_artifacts"][0].__setitem__(
            "lineage_node_id", "synthetic-node-root"
        ),
        lambda raw: raw["producing_lineage"].__setitem__(
            "lineage_sha256", "0" * 64
        ),
    ),
)
def test_producing_lineage_refuses_unknown_duplicate_drifted_or_unbound_nodes(
    schema, mutate
):
    with pytest.raises(PowerCalibrationInputSchemaError):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


def test_producing_lineage_refuses_orphan_nodes(schema):
    def mutate(raw):
        root = copy.deepcopy(raw["producing_lineage"]["ordered_nodes"][0])
        root["node_id"] = "synthetic-orphan"
        root["artifact_id"] = "synthetic-orphan-artifact"
        raw["producing_lineage"]["ordered_nodes"].append(root)

    with pytest.raises(PowerCalibrationInputSchemaError, match="orphan"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


def test_producing_lineage_cannot_erase_all_nonterminal_ancestry(schema):
    def mutate(raw):
        nodes = raw["producing_lineage"]["ordered_nodes"]
        terminals = nodes[1:]
        for node in terminals:
            node["parent_node_ids"] = []
        raw["producing_lineage"]["ordered_nodes"] = terminals
        raw["manifest_counts"]["lineage_node_count"] = len(terminals)
        _rehash_fixture_lineage(raw)

    with pytest.raises(PowerCalibrationInputSchemaError, match="root|ancestry"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize(
    "rights_ids",
    (
        [],
        ["synthetic-unknown-rights"],
        ["synthetic-rights-beta"],
    ),
)
def test_source_root_requires_nonempty_known_rights(schema, rights_ids):
    def mutate(raw):
        raw["producing_lineage"]["ordered_nodes"][0][
            "rights_binding_ids"
        ] = rights_ids
        _rehash_fixture_lineage(raw)

    with pytest.raises(PowerCalibrationInputSchemaError, match="root|rights"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


@pytest.mark.parametrize(
    "role",
    (
        "source_root",
        "transformation",
        "date_level_beta_series",
    ),
)
def test_lineage_root_role_is_closed_to_source_artifact(schema, role):
    def mutate(raw):
        raw["producing_lineage"]["ordered_nodes"][0]["role"] = role
        _rehash_fixture_lineage(raw)

    with pytest.raises(PowerCalibrationInputSchemaError, match="role|root"):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


def test_nonroot_nonterminal_lineage_node_must_be_a_transformation(schema):
    def mutate(raw):
        nodes = raw["producing_lineage"]["ordered_nodes"]
        middle = copy.deepcopy(nodes[0])
        middle.update(
            {
                "node_id": "synthetic-node-middle",
                "role": "source_artifact",
                "artifact_id": "synthetic-middle-artifact",
                "content_sha256": "2" * 64,
                "artifact_sha256": "3" * 64,
                "parent_node_ids": ["synthetic-node-root"],
            }
        )
        nodes.insert(1, middle)
        nodes[2]["parent_node_ids"] = ["synthetic-node-middle"]
        raw["manifest_counts"]["lineage_node_count"] = len(nodes)
        _rehash_fixture_lineage(raw)

    with pytest.raises(
        PowerCalibrationInputSchemaError, match="nonroot|transformation"
    ):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )


def test_terminal_lineage_node_cannot_parent_another_node(schema):
    def mutate(raw):
        nodes = raw["producing_lineage"]["ordered_nodes"]
        nodes[2]["parent_node_ids"] = [
            "synthetic-node-root",
            "synthetic-node-beta",
        ]
        _rehash_fixture_lineage(raw)

    with pytest.raises(
        PowerCalibrationInputSchemaError, match="must not have children"
    ):
        validate_synthetic_calibration_input_manifest_fixture(
            schema, _fixture_bytes(schema, mutate)
        )
