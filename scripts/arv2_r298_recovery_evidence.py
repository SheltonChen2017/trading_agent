"""Offline reconstruction and bounded evidence for the interrupted R298 A1.

Import performs no collection, export or contact. This does not resume V5,
admit a market-data package, repair a marker or authenticate an HTTP cause.
An independently frozen caller must supply execution authority and isolation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace

ROOT = Path("/Users/sheltonchen/Code/trading_agent__analyst_revisions_v2")
SOURCE_ROOT = ROOT / "research/analyst_revisions_v2_qc"
CONTROL = ROOT / "artifacts/analyst_revisions_v2/newrule_comparison_qc/R298-R303-20261013"
SCHEMA = "arv2-r298-recovery-evidence-v1"
FAMILY = "8b8ee913dcfb5ad37f4748ea70db4fcbd6ff15580e52cd160bccf2b37e10a9e5"
PACKAGE = "411c2734da61c7d4172c4cb3d33c4ffdde650f40336a5e807d26e50cc7de0bad"
LINEAGE = "e4518e06a68a18a3151fe36e5926699624fc68b97c31a8e06917d44103831fd9"
PROFILE = "b27e40dc4ae9e71b308d6eccd0fdaf83220be9157021c265a32c71e6f8b7a09b"
PROJECTION = "f67148cd717e207be9d44f088749c0443bb696d9c4f38f512eb6cbf483fd9662"
ADMISSION = "1a6850a8fbefeeab8dea2fead19b3b5f656ca29987da9ef180be1e7cc59322a3"
ORGANIZATION = "a2d88859373df0f1fd59ede52b9b3945f847091b5fca3286841241536c38e880"
V5_PROFILE = "6010aed3bcdc6c97acc65e2afb52aef85c2bdbe552cd0c400f6fccf4bedfef4b"
V5_SCHEMA = "arv2-newrule-recovery-continuation-v5"
OLD_SCHEMA = "arv2-newrule-six-cell-submission-v1"
PROJECT, REFERENCE = 38364439, 37165262
PROJECT_NAME = "ARV2 R298 NEWRULE SIX OFF 2021 OCT2026"
MARKER = "v5-R298-A1-begin-001"
ACTIVATION = ("arv2/preliminary-rating/27645603c1a6e0fc9fa81655/transport-manifest.json",
              "70f64450a44bedfa8ea371ac74a00e2134045fb79b433b93f0114be652bc6147", 4631)
SOURCE_PINS = {
    "accepted_risk_preliminary_rating_policy.py": "7d45e0c294d03b5775ca6bd911043ea1e9b819e448eb7107fcbf0a2f162e36bd",
    "accepted_risk_preliminary_rating_evaluator.py": "2fb9bc8a8f74e37b57acb97f4d20b5820be04b9ee470fc2f34b3a8ea2c804910",
    "accepted_risk_order_level_core.py": "063ed8fb7024c879a640780c07723c7edfb95665acc711d02fc8be0d964e965f",
    "accepted_risk_order_level_forced_exit.py": "21ef6978d7c26b833b0ec553298584c360f03d602f3c244f2fc8645bd113ec3f",
    "accepted_risk_order_level_input_runtime.py": "a08098648d98a95736471113d48a3e1183f04969d2c2561b1a4f5d6bfc80d7ee",
    "accepted_risk_preliminary_qc_figi.py": "4ee85d92126e31d3bde9acaffb992a54cf44b02efa876157597b876086da7ca9",
    "accepted_risk_six_universe_order_qc_runtime.py": "84e4d69135ff13f592e071574d22b30255088f4df22bd11f33943c652d81a46a",
    "accepted_risk_six_universe_order_qc_projection.py": "5037fdc1153c9ac927a540201fa92cb45db463e8313e0c88e04ddc9f0eb301f6",
    "accepted_risk_october_order_package.py": "655eec765a8b99d489881f7de7ddc339ab6b2c0bb0470feb814c6ef005d03c0a",
    "accepted_risk_preopen_rating_score.py": "67f86ffc696c036c7fbfef64ee00fb1ad1a8599727f5ef36762e329df85a023a",
    "newrule_comparison_targets.py": "30ed05cbc02bb0076d09c82467a32ad840ead87561f3e2a1ae1cc5a9ee65f29d",
    "newrule_comparison_qc_runtime.py": "674415b3179836a613afc6f7bdea23a966db21ab67221472fc5d87b4a742049d",
    "newrule_comparison_projection.py": "4f51d1a9a50293f4fa39be297666c1e6144462abaa82e69e342845580a1a4076",
}
FILE_NAMES = (
    "accepted_risk_order_level_core.py", "accepted_risk_order_level_forced_exit.py",
    "accepted_risk_order_level_input_runtime.py", "accepted_risk_preliminary_qc_figi.py",
    "accepted_risk_preliminary_rating_evaluator.py", "accepted_risk_preliminary_rating_policy.py",
    "accepted_risk_preopen_rating_score.py", "main.py", "newrule_comparison_qc_runtime.py",
    "newrule_comparison_targets.py", "newrule_legacy_primitives.py",
)
BASE_NAMES = frozenset(("family.json", "organization-claim.json", "organization.json",
    "storage-recovery-v4-admission.json", "continuation-v5-family.json",
    MARKER + "-batch-claim.json", "R298-A1-claim.json", "R298-project.json"))
RPC_SUFFIXES = ("capacity-reference", "capacity", "create-project", "owned-project", "prior-runs",
    "initial-files", "delete-default-notebook", *(f"source-{i:02d}" for i in range(11)),
    "source-readback", "compile-create")
OUTPUT_NAMES = frozenset({"R298-A1-claim.json", "R298-project.json", "R298-A1-compile.json",
    MARKER + "-capacity-valid.json"} | {MARKER + "-" + stem + suffix
        for stem in RPC_SUFFIXES for suffix in ("-intent.json", "-observed.json")})
SELECTED_NAMES = BASE_NAMES | OUTPUT_NAMES


class EvidenceRefused(ValueError):
    """Finite refusal; never includes a document, path or underlying exception."""


def require(value, code):
    if not value:
        raise EvidenceRefused(code)


def canonical(value):
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
    except (ValueError, TypeError, UnicodeError):
        raise EvidenceRefused("json") from None


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def same(left, right):
    return type(left) is type(right) and canonical(left) == canonical(right)


def _hash(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def require_projection(projected):
    """Bind rendered bytes, not a caller's success flag or mutable manifest."""
    from research.analyst_revisions_v2_qc import newrule_comparison_projection as projection
    require(type(projected) is projection.Projection, "projection_type")
    try:
        record = projected.to_record()
        profile = json.loads(projected.profile_bytes)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise EvidenceRefused("projection_binding") from None
    require(sha(projected.record_bytes) == PROJECTION and projected.projection_sha256 == PROJECTION,
            "projection_pin")
    require(profile.get("profile_sha256") == PROFILE and record.get("profile_sha256") == PROFILE,
            "profile_pin")
    require(tuple(item.project_path for item in projected.source_files) == FILE_NAMES, "source_inventory")
    require(all(type(item.source_bytes) is bytes and 0 < len(item.source_bytes) <= 64000
                for item in projected.source_files), "source_bound")
    require(sum(len(item.source_bytes) for item in projected.source_files) <= 448 * 1024, "source_bound")
    return record


def reconstruct_projection():
    """Reconstruct code from public pinned sources only; no artifact/package load.

    Selected hashes are not interpreter integrity. The outer caller must bind
    the transitive source closure and enforce native isolation before imports.
    """
    require(Path.cwd() == ROOT, "root")
    sources = {}
    for name, pin in SOURCE_PINS.items():
        path = SOURCE_ROOT / name
        require(path.is_file() and not path.is_symlink(), "source_path")
        with path.open("rb") as handle:
            raw = handle.read(100001)
        require(0 < len(raw) <= 100000 and sha(raw) == pin, "source_pin")
        sources[name] = raw
    from research.analyst_revisions_v2_qc import newrule_comparison_projection as projection
    axis = projection.october._sessions()
    profile = projection.runtime.make_profile(axis, package_sha256=PACKAGE, lineage_sha256=LINEAGE,
        universe_count=6, ar_percent=0, source_pins=dict(SOURCE_PINS))
    activation = SimpleNamespace(object_store_key=ACTIVATION[0], content_sha256=ACTIVATION[1], byte_count=ACTIVATION[2])
    projected = projection.render_projection(profile=profile, activation=activation, sources=sources)
    require_projection(projected)
    return projected


def _binding():
    return {"schema": V5_SCHEMA, "profile_sha256": V5_PROFILE,
            "family_sha256": FAMILY, "admission_sha256": ADMISSION}


def _identity():
    return {"schema": OLD_SCHEMA, "family_sha256": FAMILY, "attempt_id": "R298-A1",
        "candidate_id": "R298", "projection_sha256": PROJECTION, "profile_sha256": PROFILE,
        "shared_look": 1, "development_look": 1, "infrastructure_look": 0, "result_cell": 0}


def _inventory(names):
    require(type(names) in (tuple, list) and len(names) <= 18000
        and all(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]+\.json", name) for name in names)
        and len(set(names)) == len(names), "inventory")
    names = set(names)
    for name in names:
        if name.startswith("v5-"):
            require(name in SELECTED_NAMES or name.startswith("v5-capacity-001-"), "later_lifecycle")
        if re.match(r"R(?:298|299|30[0-3])-A\d+", name):
            require(name == "R298-A1-claim.json", "later_lifecycle")
        if re.fullmatch(r"R(?:299|30[0-3])-project.json", name):
            require(False, "later_lifecycle")
    require("R298-A1-compile.json" not in names and MARKER + "-batch-complete.json" not in names,
            "later_lifecycle")
    return names


def validate_documents(documents, projected, *, inventory):
    """Pure validation of a fixed incomplete, post-project, pre-compile prefix.

    Receipt hashes authenticate retained bytes, not success of a current QC
    observation. Observed RPC hashes cannot recover discarded response bodies.
    """
    projection = require_projection(projected)
    names = _inventory(inventory)
    require(type(documents) is dict and set(documents) == names & SELECTED_NAMES
        and BASE_NAMES <= set(documents), "documents")
    require(all(type(value) is dict and len(canonical(value)) <= 512 * 1024
                for value in documents.values()), "documents")
    documents = json.loads(canonical(documents))  # detach caller-owned mappings
    family = documents["family.json"]
    require(sha(canonical(family)) == FAMILY, "family_pin")
    require(sha(canonical(documents["storage-recovery-v4-admission.json"])) == ADMISSION, "admission_pin")
    org = documents["organization.json"]
    org_id = org.get("organization_id")
    require(type(org_id) is str and re.fullmatch(r"[0-9a-f]{32}", org_id)
        and sha(org_id.encode("ascii")) == ORGANIZATION, "organization_pin")
    org_binding = {"family_sha256": FAMILY, "reference_project_id": REFERENCE}
    require(same(documents["organization-claim.json"], org_binding)
        and same(org, {**org_binding, "organization_id": org_id, "organization_sha256": ORGANIZATION}),
        "organization_binding")
    require(same(documents["continuation-v5-family.json"], _binding()), "v5_binding")
    require(type(family.get("cells")) is list and family["cells"]
        and same(family["cells"][0], {"candidate_id": "R298", "project_name": PROJECT_NAME,
            "projection_sha256": PROJECTION, "profile_sha256": PROFILE,
            "evaluation_geometry_sha256": family["cells"][0].get("evaluation_geometry_sha256"),
            "source_files": projection["source_files"]}), "family_projection")
    batch = documents[MARKER + "-batch-claim.json"]
    epoch = batch.get("epoch")
    require(type(epoch) is int and epoch >= 0 and same(batch, {**_binding(), "operation": "begin",
        "candidate_id": "R298", "attempt": 1, "ordinal": 1, "epoch": epoch,
        "allowed_outputs": sorted(OUTPUT_NAMES)}), "batch_claim")
    require(same(documents["R298-A1-claim.json"], {**_identity(), "prior_failure_sha256": None,
        "retry_justification_sha256": None}), "attempt_claim")
    require(same(documents["R298-project.json"], {"family_sha256": FAMILY,
        "candidate_id": "R298", "project_id": PROJECT}), "project_binding")
    capacity = documents.get(MARKER + "-capacity-valid.json")
    require(type(capacity) is dict and set(capacity) == {"family_sha256", "node_count", "busy_count",
        "selected_count", "auto_select", "available_count"} and capacity["family_sha256"] == FAMILY
        and type(capacity["auto_select"]) is bool
        and all(type(capacity[key]) is int and 0 <= capacity[key] <= 64
                for key in ("node_count", "busy_count", "selected_count", "available_count"))
        and capacity["busy_count"] <= capacity["node_count"]
        and capacity["selected_count"] <= capacity["node_count"]
        and 0 < capacity["available_count"] <= capacity["node_count"] - capacity["busy_count"]
        and (capacity["available_count"] == capacity["node_count"] - capacity["busy_count"]
             if capacity["auto_select"] else max(0, capacity["selected_count"] - capacity["busy_count"])
             <= capacity["available_count"] <= capacity["selected_count"]), "capacity")
    requests = [
        ("capacity-reference", "projects/read", [{"projectId": REFERENCE}]),
        ("capacity", "projects/nodes/read", [{"projectId": REFERENCE}]),
        ("create-project", "projects/create", [{"name": PROJECT_NAME, "language": "Py", "organizationId": org_id}]),
        ("owned-project", "projects/read", [{"projectId": PROJECT}]),
        ("prior-runs", "backtests/list", [{"projectId": PROJECT, "includeStatistics": False}]),
        ("initial-files", "files/read", [{"projectId": PROJECT}]),
    ]
    optional = MARKER + "-delete-default-notebook-intent.json" in documents
    if optional:
        requests.append(("delete-default-notebook", "files/delete", [{"projectId": PROJECT, "name": "research.ipynb"}]))
    for index, item in enumerate(projected.source_files):
        requests.append((f"source-{index:02d}", "files/update" if item.project_path == "main.py" else "files/create",
            [{"projectId": PROJECT, "name": item.project_path, "content": item.source_bytes.decode("ascii")}]))
    requests.extend((("source-readback", "files/read", [{"projectId": PROJECT}]),
                     ("compile-create", "compile/create", [{"projectId": PROJECT}])))
    used, previous, failed = set(), epoch, None
    for suffix, endpoint, payloads in requests:
        intent_name, observed_name = (MARKER + "-" + suffix + end for end in ("-intent.json", "-observed.json"))
        if failed is not None:
            require(intent_name not in documents and observed_name not in documents, "nonsequential_rpc")
            continue
        require(intent_name in documents, "rpc_gap")
        intent = documents[intent_name]
        current = intent.get("epoch")
        # main.py may be absent in the initial inventory; the retained hash
        # still binds exactly one supported endpoint, never arbitrary content.
        endpoints = ("files/update", "files/create") if suffix == "source-07" else (endpoint,)
        require(type(current) is int and current >= previous and set(intent) == {
            "family_sha256", "endpoint", "request_sha256", "epoch"}
            and intent["family_sha256"] == FAMILY and intent["endpoint"] in endpoints
            and intent["request_sha256"] in {sha(canonical(payload)) for payload in payloads}, "rpc_intent")
        used.add(intent_name)
        previous = current
        if observed_name not in documents:
            failed = {"failed_stage": suffix, "failed_endpoint": intent["endpoint"],
                "failed_request_sha256": intent["request_sha256"], "intent_epoch": current}
            require(suffix not in {"capacity-reference", "capacity", "create-project", "compile-create"},
                    "unsupported_failure_stage")
            continue
        observed = documents[observed_name]
        require(set(observed) == {"family_sha256", "response_sha256", "epoch"}
            and observed["family_sha256"] == FAMILY and _hash(observed["response_sha256"])
            and type(observed["epoch"]) is int and observed["epoch"] >= current, "rpc_observation")
        previous = observed["epoch"]
        used.add(observed_name)
    require(failed is not None, "missing_failure")
    require(set(documents) == BASE_NAMES | used | {MARKER + "-capacity-valid.json"}, "extra_evidence")
    return {"schema": SCHEMA, "family_sha256": FAMILY, "projection_sha256": PROJECTION,
        "project_id": PROJECT, "candidate_id": "R298", "attempt_id": "R298-A1",
        "attempt_claim_authenticated": True, "shared_look": 1, "development_look": 1,
        "compile_receipt_present": False, "launch_receipt_present": False, "batch_complete_present": False,
        "observed_rpc_count": sum(name.endswith("-observed.json") for name in used),
        "retained_intent_count": sum(name.endswith("-intent.json") for name in used),
        "document_hashes": {name: sha(canonical(value)) for name, value in sorted(documents.items())},
        "provider_request_count": None, "remote_effects_authenticated": False,
        "cause_authenticated": False, "continuation_authorized": False,
        "point_in_time_proven": False, "formal_forward_ready": False, "paper_or_live_ready": False, **failed}


def collect_documents():
    """Read-only fixed control collector; call only under a separate run freeze.

    Uses the unchanged held/named per-leaf checks. A name census covers this
    control directory only; other leaf contents are not read. Equal snapshots
    are not continuous whole-tree integrity. No operational call happens here.
    """
    from research.analyst_revisions_v2_qc import newrule_comparison_submission as old
    require(Path.cwd() == ROOT and old.ROOT == ROOT and old.CONTROL == CONTROL, "root")
    with old._Directory() as directory:
        before = tuple(sorted(directory.names()))
        selected = _inventory(before) & SELECTED_NAMES
        values = {name: directory.read(name) for name in sorted(selected)}
        require(tuple(sorted(directory.names())) == before, "inventory_changed")
        require(all(same(value, directory.read(name)) for name, value in values.items()), "documents_changed")
        require(tuple(sorted(directory.names())) == before, "inventory_changed")
        directory.verify()
    return values, before
