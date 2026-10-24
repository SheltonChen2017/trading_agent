"""Synthetic controls only; public reconstruction is not an actual export."""
import ast
import copy
import dataclasses
import inspect
import json

import pytest

from scripts import arv2_r298_recovery_evidence as e
from research.analyst_revisions_v2_qc import newrule_comparison_submission as old


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    violations = []
    def forbidden(*_args, **_kwargs):
        violations.append("operation")
        pytest.fail("operational call forbidden")
    for owner, names in ((old, ("_Directory", "_client", "prepare_family", "load_family")),
        (old.october, ("load_october_order_input_package",)),
        (old.compact, ("load_accepted_risk_preliminary_package",)),
        (old.coverage, ("production_client", "_bounded_transport"))):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    yield violations
    assert violations == []


@pytest.fixture(scope="module")
def projected():
    return e.reconstruct_projection()


@pytest.fixture
def evidence(monkeypatch, projected):
    organization = "a" * 32
    family = {"cells": [{"candidate_id": "R298", "project_name": e.PROJECT_NAME,
        "projection_sha256": e.PROJECTION, "profile_sha256": e.PROFILE,
        "evaluation_geometry_sha256": "b" * 64,
        "source_files": projected.to_record()["source_files"]}]}
    admission = {"synthetic_only": True, "not_real_admission": True}
    monkeypatch.setattr(e, "FAMILY", e.sha(e.canonical(family)))
    monkeypatch.setattr(e, "ADMISSION", e.sha(e.canonical(admission)))
    monkeypatch.setattr(e, "ORGANIZATION", e.sha(organization.encode("ascii")))
    binding = {"family_sha256": e.FAMILY, "reference_project_id": e.REFERENCE}
    docs = {
        "family.json": family, "storage-recovery-v4-admission.json": admission,
        "organization-claim.json": binding,
        "organization.json": {**binding, "organization_id": organization, "organization_sha256": e.ORGANIZATION},
        "continuation-v5-family.json": e._binding(),
        e.MARKER + "-batch-claim.json": {**e._binding(), "operation": "begin", "candidate_id": "R298",
            "attempt": 1, "ordinal": 1, "epoch": 100, "allowed_outputs": sorted(e.OUTPUT_NAMES)},
        "R298-A1-claim.json": {**e._identity(), "prior_failure_sha256": None, "retry_justification_sha256": None},
        "R298-project.json": {"family_sha256": e.FAMILY, "candidate_id": "R298", "project_id": e.PROJECT},
        e.MARKER + "-capacity-valid.json": {"family_sha256": e.FAMILY, "node_count": 2,
            "busy_count": 0, "selected_count": 0, "auto_select": True, "available_count": 2},
    }
    requests = [
        ("capacity-reference", "projects/read", {"projectId": e.REFERENCE}),
        ("capacity", "projects/nodes/read", {"projectId": e.REFERENCE}),
        ("create-project", "projects/create", {"name": e.PROJECT_NAME, "language": "Py", "organizationId": organization}),
        ("owned-project", "projects/read", {"projectId": e.PROJECT}),
        ("prior-runs", "backtests/list", {"projectId": e.PROJECT, "includeStatistics": False}),
        ("initial-files", "files/read", {"projectId": e.PROJECT}),
        ("delete-default-notebook", "files/delete", {"projectId": e.PROJECT, "name": "research.ipynb"}),
    ]
    for index, item in enumerate(projected.source_files):
        requests.append((f"source-{index:02d}", "files/update" if item.project_path == "main.py" else "files/create",
            {"projectId": e.PROJECT, "name": item.project_path, "content": item.source_bytes.decode("ascii")}))
    requests.append(("source-readback", "files/read", {"projectId": e.PROJECT}))
    def prefix(failure="source-02", *, notebook=True):
        result = copy.deepcopy(docs)
        for index, (suffix, endpoint, payload) in enumerate(requests):
            if not notebook and suffix == "delete-default-notebook":
                continue
            marker = e.MARKER + "-" + suffix
            result[marker + "-intent.json"] = {"family_sha256": e.FAMILY, "endpoint": endpoint,
                "request_sha256": e.sha(e.canonical(payload)), "epoch": 101 + index * 2}
            if suffix == failure:
                return result
            result[marker + "-observed.json"] = {"family_sha256": e.FAMILY,
                "response_sha256": "c" * 64, "epoch": 102 + index * 2}
        raise AssertionError("unknown synthetic failure")
    return prefix


def validate(docs, projected, *, extra_names=()):
    return e.validate_documents(docs, projected, inventory=tuple(docs) + tuple(extra_names))


def test_public_reconstruction_matches_original_complete_projection(projected):
    assert projected.projection_sha256 == "f67148cd717e207be9d44f088749c0443bb696d9c4f38f512eb6cbf483fd9662"
    assert json.loads(projected.profile_bytes)["profile_sha256"] == e.PROFILE
    assert len(projected.source_files) == 11 and len(e.SOURCE_PINS) == 13
    assert tuple(item.project_path for item in projected.source_files) == e.FILE_NAMES
    assert all(len(item.source_bytes) <= 64000 for item in projected.source_files)


def test_reconstruction_refuses_wrong_selected_source_pin(monkeypatch):
    pins = dict(e.SOURCE_PINS)
    pins["accepted_risk_preliminary_rating_policy.py"] = "0" * 64
    monkeypatch.setattr(e, "SOURCE_PINS", pins)
    with pytest.raises(e.EvidenceRefused, match="source_pin"):
        e.reconstruct_projection()


def test_no_export_or_operational_side_effect_on_import():
    tree = ast.parse(inspect.getsource(e))
    assert not any(isinstance(node, ast.If) and "__name__" in ast.unparse(node.test) for node in tree.body)
    assert not any(isinstance(node, ast.Attribute) and node.attr in {
        "write_bytes", "write_text", "mkdir", "unlink", "replace", "request", "dispatch"}
        for node in ast.walk(tree))


@pytest.mark.parametrize("field", ["source_bytes", "project_path"])
def test_changed_projected_file_rejected(projected, field):
    changed = dataclasses.replace(projected.source_files[0], **{field:
        b"# not pinned\n" if field == "source_bytes" else "wrong.py"})
    candidate = dataclasses.replace(projected, source_files=(changed,) + projected.source_files[1:])
    with pytest.raises(ValueError):
        e.require_projection(candidate)


@pytest.mark.parametrize("failure", ["owned-project", "prior-runs", "initial-files",
    "delete-default-notebook", *(f"source-{i:02d}" for i in range(11)), "source-readback"])
def test_supported_prefixes_do_not_claim_remote_failure_cause(evidence, projected, failure):
    result = validate(evidence(failure), projected)
    assert result["failed_stage"] == failure and result["project_id"] == e.PROJECT
    assert result["attempt_claim_authenticated"] is True
    assert result["shared_look"] == result["development_look"] == 1
    assert result["retained_intent_count"] == result["observed_rpc_count"] + 1
    assert result["provider_request_count"] is None
    assert result["cause_authenticated"] is result["remote_effects_authenticated"] is False
    assert result["continuation_authorized"] is False
    assert result["compile_receipt_present"] is result["launch_receipt_present"] is False
    assert result["batch_complete_present"] is False
    assert "organization_id" not in json.dumps(result)


def test_optional_notebook_absence_and_main_create(evidence, projected):
    docs = evidence("source-07", notebook=False)
    docs[e.MARKER + "-source-07-intent.json"]["endpoint"] = "files/create"
    assert validate(docs, projected)["failed_endpoint"] == "files/create"


@pytest.mark.parametrize("name", ["R298-A1-compile.json", "R298-A1-launch.json",
    "R298-A1-terminal.json", "R298-A2-claim.json", "R299-A1-claim.json", "R299-project.json",
    e.MARKER + "-batch-complete.json", "v5-R298-A1-begin-002-batch-claim.json",
    "v5-R298-A1-launch-001-batch-claim.json"])
def test_later_lifecycle_presence_refuses_without_reading_bytes(evidence, projected, name):
    with pytest.raises(e.EvidenceRefused, match="later_lifecycle"):
        validate(evidence(), projected, extra_names=(name,))


@pytest.mark.parametrize("name", sorted(e.BASE_NAMES))
def test_required_binding_missing(evidence, projected, name):
    docs = evidence()
    del docs[name]
    with pytest.raises(e.EvidenceRefused, match="documents"):
        validate(docs, projected)


@pytest.mark.parametrize("name,field,value", [
    ("family.json", "unexpected", True),
    ("storage-recovery-v4-admission.json", "unexpected", True),
    ("organization.json", "organization_id", "b" * 32),
    ("organization-claim.json", "reference_project_id", 1),
    ("continuation-v5-family.json", "admission_sha256", "d" * 64),
    ("R298-project.json", "project_id", 38364440), ("R298-project.json", "project_id", True),
    ("R298-A1-claim.json", "shared_look", True), ("R298-A1-claim.json", "attempt_id", "R298-A2"),
    (e.MARKER + "-batch-claim.json", "attempt", True), (e.MARKER + "-batch-claim.json", "epoch", True),
    (e.MARKER + "-capacity-valid.json", "available_count", 0),
    (e.MARKER + "-capacity-valid.json", "node_count", True),
    (e.MARKER + "-capacity-valid.json", "busy_count", 3),
    (e.MARKER + "-capacity-valid.json", "selected_count", 3),
    (e.MARKER + "-capacity-valid.json", "auto_select", False),
    (e.MARKER + "-source-02-intent.json", "request_sha256", "d" * 64),
    (e.MARKER + "-source-02-intent.json", "endpoint", "backtests/create"),
    (e.MARKER + "-source-02-intent.json", "endpoint", "files/update"),
    (e.MARKER + "-source-02-intent.json", "epoch", 1),
    (e.MARKER + "-source-01-observed.json", "response_sha256", "invalid"),
    (e.MARKER + "-source-01-observed.json", "epoch", 0),
])
def test_binding_and_type_corruption_refuses(evidence, projected, name, field, value):
    docs = evidence()
    docs[name][field] = value
    with pytest.raises(e.EvidenceRefused):
        validate(docs, projected)


def test_earlier_unmatched_intent_with_later_work_refuses(evidence, projected):
    docs = evidence()
    del docs[e.MARKER + "-source-00-observed.json"]
    with pytest.raises(e.EvidenceRefused, match="nonsequential_rpc"):
        validate(docs, projected)


def test_gap_before_failure_refuses(evidence, projected):
    docs = evidence()
    del docs[e.MARKER + "-source-00-intent.json"]
    with pytest.raises(e.EvidenceRefused, match="rpc_gap"):
        validate(docs, projected)


def test_actual_failed_request_payload_is_byte_bound(evidence, projected):
    docs = evidence()
    payload = {"projectId": e.PROJECT, "name": e.FILE_NAMES[2], "content": "#"}
    docs[e.MARKER + "-source-02-intent.json"]["request_sha256"] = e.sha(e.canonical(payload))
    with pytest.raises(e.EvidenceRefused, match="rpc_intent"):
        validate(docs, projected)


def test_observed_response_hash_is_not_response_body(evidence, projected):
    result = validate(evidence(), projected)
    assert result["failed_endpoint"] == "files/create" and result["failed_stage"] == "source-02"
    assert result["observed_rpc_count"] == 9 and result["retained_intent_count"] == 10
    assert all(key not in result for key in ("http_status", "root_cause", "api_error", "response_body"))


def test_result_detaches_caller_mapping(evidence, projected):
    docs = evidence()
    result = validate(docs, projected)
    before = copy.deepcopy(result)
    docs["R298-project.json"]["project_id"] = 123
    assert result == before


def test_unselected_private_contents_never_read(monkeypatch, evidence):
    docs = evidence()
    names = tuple(docs) + ("unrelated-retained-private.json",)
    reads = []
    class Directory:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def names(self): return names
        def read(self, name):
            reads.append(name)
            assert name in docs
            return copy.deepcopy(docs[name])
        def verify(self): pass
    monkeypatch.setattr(old, "_Directory", Directory)
    result, observed_names = e.collect_documents()
    assert result == docs and observed_names == tuple(sorted(names))
    assert set(reads) == set(docs) and len(reads) == 2 * len(docs)


@pytest.mark.parametrize("change", ["names", "bytes", "late_names"])
def test_collection_refuses_endpoint_snapshot_changes(monkeypatch, evidence, change):
    docs, visits = evidence(), {}
    class Directory:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def names(self):
            visits["names"] = visits.get("names", 0) + 1
            changed = (change == "names" and visits["names"] == 2) or (change == "late_names" and visits["names"] == 3)
            return tuple(docs) + (("different.json",) if changed else ())
        def read(self, name):
            visits[name] = visits.get(name, 0) + 1
            value = copy.deepcopy(docs[name])
            if change == "bytes" and visits[name] == 2:
                value["unexpected"] = True
            return value
        def verify(self): pass
    monkeypatch.setattr(old, "_Directory", Directory)
    with pytest.raises(e.EvidenceRefused, match="inventory_changed|documents_changed"):
        e.collect_documents()


def test_canonical_rejects_nonfinite():
    with pytest.raises(e.EvidenceRefused, match="json"):
        e.canonical({"value": float("nan")})
