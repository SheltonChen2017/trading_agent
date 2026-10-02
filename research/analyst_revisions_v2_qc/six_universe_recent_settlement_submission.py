"""Exact recent-window input upload and composition of the order launcher.

This adapter never changes the historical launcher registry or its globals.
Independent literal pins must be installed before any new-window authority
exists. The input activation is published last; results remain two bounded
custom statistics, with R203 as this window's only comparison anchor.
"""

import dataclasses
import hashlib
import json
from pathlib import Path

from research.quantconnect import API_BASE, build_auth_headers

from . import accepted_risk_latest_order_package as latest_builder
from . import accepted_risk_preliminary_package as package_builder
from . import formal_qc_transport as transport
from . import formal_submission_adapter as formal
from . import six_universe_coverage_submission as coverage
from . import six_universe_settlement_submission as common


# Independently frozen authenticated successor and ordered upload inventory.
# The source registry must also be complete before launch authority exists.
PINNED_PACKAGE_SHA256 = "2649577ac55ac39de37a4a70ab4337274f1887e1a113f0972beefab615121be1"
PINNED_LINEAGE_SHA256 = "c39b6fe27782a7776891aab67c82d816fcd2109b12928cc84643073d140b2dbb"
PINNED_ACTIVATION_MANIFEST_SHA256 = "9ee1013f429ed87e7b7a262cf352c5604cd532ce4eb3e9defffe23be31c39b35"
UPLOAD_MANIFEST_SHA256 = "7d4e031e6dfdc531e9e0954a741009fa5995ec62c5297032714882fa1343e0a7"
UPLOAD_OBJECT_COUNT = 6
MATCHED_BASELINE_PROFILE_SHA256 = "440c7a683efe7476d88aaab730d87955efcbeb31aac4b559b330ad32f39c4fc6"
PROJECTION_ID_PREFIXES = {
    100: "arv2-six-universe-order-tilt100-recent-qc-projection-",
    120: "arv2-six-universe-order-tilt120-recent-qc-projection-",
    140: "arv2-six-universe-order-tilt140-recent-qc-projection-",
    160: "arv2-six-universe-order-tilt160-recent-qc-projection-",
    180: "arv2-six-universe-order-tilt180-recent-qc-projection-",
    200: "arv2-six-universe-order-tilt200-recent-qc-projection-",
}
TRUSTED_CANDIDATES = {
    "R203": common._Candidate(
        "R203", "125 ARV2 SIX CAP90 SETTLED TILT100 R203 202508 NOW",
        "matched_revision_tilt100_recent", "cap90_matched_revision_tilt100_recent_v1",
        "arv2-six-universe-order-qc-projection-tilt100-recent-v1",
        "39793ae7247bae5282f93edfbaa5f6828bd4e49332f5b7909cf07baf92557b21",
        "2a14727e763e5cbcbb6c32b08b1e051cf24af210761eacabc288f8e8ae140410",
        "f8f706628fc6aefb5756cdaeb382bccdf97231f816fb5367e8d74ffbe1f72911",
        16, 425_165, "arv2-six-universe-order-tilt100-recent-summary-v1",
        "ARV2-OWNER-2026-09-25-R203A1-TILT100-RECENT-EXPLORATORY-SIGNATURE-WAIVER"),
    "R204": common._Candidate(
        "R204", "126 ARV2 SIX CAP90 SETTLED TILT120 R204 202508 NOW",
        "matched_revision_tilt120_recent", "cap90_matched_revision_tilt120_recent_v1",
        "arv2-six-universe-order-qc-projection-tilt120-recent-v1",
        "dd8eb43587ea2b893992f40ce3b33af4da65415cd3515fed3130e5a2e294fedb",
        "9e4d7a788e594834433ec34f957db25caf4f2847598fc8b3423957170195ccb9",
        "724fbcf56108f2a5d7478f3067c43f4e232ea1ea063c39678684d6a9e52ab501",
        16, 425_165, "arv2-six-universe-order-tilt120-recent-summary-v1",
        "ARV2-OWNER-2026-09-25-R204A1-TILT120-RECENT-EXPLORATORY-SIGNATURE-WAIVER"),
    "R205": common._Candidate(
        "R205", "127 ARV2 SIX CAP90 SETTLED TILT140 R205 202508 NOW",
        "matched_revision_tilt140_recent", "cap90_matched_revision_tilt140_recent_v1",
        "arv2-six-universe-order-qc-projection-tilt140-recent-v1",
        "78b52a953782257f5fbef2d5dbeaafec2533a5f853e41da1b8ce7117493a8b66",
        "f8e641731f322c67420c82ccf463cbb5e513fb08961330132855e667daacf271",
        "18be41789db4fbfc33daf41daf433713027bb71455774bb416a94624ce8d2b70",
        16, 425_165, "arv2-six-universe-order-tilt140-recent-summary-v1",
        "ARV2-OWNER-2026-09-25-R205A1-TILT140-RECENT-EXPLORATORY-SIGNATURE-WAIVER"),
    "R206": common._Candidate(
        "R206", "128 ARV2 SIX CAP90 SETTLED TILT160 R206 202508 NOW",
        "matched_revision_tilt160_recent", "cap90_matched_revision_tilt160_recent_v1",
        "arv2-six-universe-order-qc-projection-tilt160-recent-v1",
        "d70d5b314f409c70fb16fbbe19171bcb29819fdff0716ca4620657b0775d7f9a",
        "3ff5c516323b945eea28bd1104f3ebaa215ebfb3a70c1ab76f778ec033ada2c5",
        "4cf2518306e18589a193646a320d25a80585fbb5d3a387bad735d50a9a184824",
        16, 425_165, "arv2-six-universe-order-tilt160-recent-summary-v1",
        "ARV2-OWNER-2026-09-25-R206A1-TILT160-RECENT-EXPLORATORY-SIGNATURE-WAIVER"),
    "R207": common._Candidate(
        "R207", "129 ARV2 SIX CAP90 SETTLED TILT180 R207 202508 NOW",
        "matched_revision_tilt180_recent", "cap90_matched_revision_tilt180_recent_v1",
        "arv2-six-universe-order-qc-projection-tilt180-recent-v1",
        "7d344126844c46642f52be74daa8f5a702e65e50d8979ee7df78e25f1b3ca7b1",
        "cbfc4c7ad196f50b0dfdd221572b4f26a3fddef6e3cd87781d03e192e2d7a214",
        "e2a11a2c90ae496e64daa1c9d3ce5cdd6248c1110acbdadbd3c7d1886dcd1cdd",
        16, 425_165, "arv2-six-universe-order-tilt180-recent-summary-v1",
        "ARV2-OWNER-2026-09-25-R207A1-TILT180-RECENT-EXPLORATORY-SIGNATURE-WAIVER"),
    "R208": common._Candidate(
        "R208", "130 ARV2 SIX CAP90 SETTLED TILT200 R208 202508 NOW",
        "matched_revision_tilt200_recent", "cap90_matched_revision_tilt200_recent_v1",
        "arv2-six-universe-order-qc-projection-tilt200-recent-v1",
        "9f4df0c75eda0e6aa27ee69351ee044263bfe0f1d79312f0b40a62034a26e85f",
        "c84a1a17d23e504044baf63807a83135b4d098062b7a2b98a041336234f1809a",
        "563f3de21000c4588610f7c43904091d1dafbbfff930f50d1cd193261b954b43",
        16, 425_165, "arv2-six-universe-order-tilt200-recent-summary-v1",
        "ARV2-OWNER-2026-09-25-R208A1-TILT200-RECENT-EXPLORATORY-SIGNATURE-WAIVER"),
}
_INPUT_WAIVER_ID = "ARV2-OWNER-2026-09-25-RECENT-INPUTS-EXPLORATORY"
_A2_WAIVER_ID = "ARV2-OWNER-2026-09-26-R203A2-SAME-SOURCE-VISIBILITY-HYPOTHESIS-SIGNATURE-WAIVER"
_A2_PROJECT_ID = 36978919
_A1_BACKTEST_ID = "61b3faad153e52b02cca15349924b594"

# Preserve R203 A1's original source authority; Mia's second attempt is imported
# separately. The unlaunched R204-R208 receive only the verified byte-reader fix.
ORIGINAL_TRUSTED_CANDIDATES = dict(TRUSTED_CANDIDATES)
_DIRECT_READ_SOURCE_PINS = {
    "R203": (100, "a5fff0112a08ca453fac5b01740a89eeb67bc72a1adecbfb1b9cbe686139ab26", "977023de3f2ad18445d1d5e992417c9ff06e93954085c22f323f4b59f10cea68"),
    "R204": (120, "1aad7dc4b7083dd8d062d08f2ca3d239d142e9c5dc4e93e5fc50fbd6fa5a7b32", "ad7ae57beeb9ed140cd0441228d5ed274639e9cb45db19e8d662a1e41e240e7e"),
    "R205": (140, "91747ad28ccf17784a3d40f4bc374a12c74c7289da7be3659739c7fa899ff4d0", "f787e29374076bb36a2cde5499aa8dabf48bc7fdf126a72112364e3f34e22603"),
    "R206": (160, "d79ca9149f963079cbca4de91fbab670454910dc92d3921b97e28f565a6859ea", "69628fb750f270d4de148e153bb709fdb85ccc0e84713a21451dd9939857e613"),
    "R207": (180, "89461345526643e61be70badf7a9610d664434b092ba353fc7f534f050de4882", "22974f9ffc7ec011381f6a187960ad6ad77387483d7367597d1a018cbc9e5a13"),
    "R208": (200, "8efe09156adddd25dab77f489220cc6a9aeb5e8481516c75fbd9f24bed6d76cc", "ed0d135c1c150c489542c69eb027803b9d448d1cee14842ba27ac83aa233e875"),
}
for _candidate_id, (_capacity, _projection_pin, _source_pin) in _DIRECT_READ_SOURCE_PINS.items():
    _corrected = dataclasses.replace(ORIGINAL_TRUSTED_CANDIDATES[_candidate_id],
        projection_schema=f"arv2-six-universe-order-qc-projection-tilt{_capacity}-recent-direct-read-v2",
        projection_sha256=_projection_pin, source_files_sha256=_source_pin,
        total_source_bytes=424835,
        waiver_id=f"ARV2-OWNER-2026-09-26-{_candidate_id}A1-TILT{_capacity}-RECENT-DIRECT-READ-V2-SIGNATURE-WAIVER")
    if _candidate_id == "R203":
        MIA_R203_CANDIDATE = _corrected
    else:
        TRUSTED_CANDIDATES[_candidate_id] = _corrected
        PROJECTION_ID_PREFIXES[_capacity] = f"arv2-six-universe-order-tilt{_capacity}-recent-direct-read-qc-projection-"


def require_package_binding(plan):
    if (
        type(plan) is not common.SettlementQcPlan
        or plan.candidate_id not in common._RECENT_PERCENTS
        or type(plan.attempt) is not int
        or plan.attempt not in ((1, 2) if plan.candidate_id == "R203" else (1,))
        or any(type(value) is not str or not common._HEX.fullmatch(value) for value in (
            PINNED_PACKAGE_SHA256, PINNED_LINEAGE_SHA256,
            PINNED_ACTIVATION_MANIFEST_SHA256, UPLOAD_MANIFEST_SHA256,
            MATCHED_BASELINE_PROFILE_SHA256,
        ))
        or plan.package_sha256 != PINNED_PACKAGE_SHA256
        or plan.activation_manifest_sha256 != PINNED_ACTIVATION_MANIFEST_SHA256
        or type(UPLOAD_OBJECT_COUNT) is not int or UPLOAD_OBJECT_COUNT <= 0
        or set(TRUSTED_CANDIDATES) != set(common._RECENT_PERCENTS)
    ):
        common._fail("recent package, activation, or independent pins are not exact")


def build_plan(candidate_id, organization_id, control_directory):
    plan = common.SettlementQcPlan(
        candidate_id, organization_id, PINNED_PACKAGE_SHA256,
        PINNED_ACTIVATION_MANIFEST_SHA256, Path(control_directory),
    )
    common._candidate(plan)
    return plan


def require_profile(percent):
    from . import accepted_risk_six_universe_order_tilt_recent_qc_projection as projection
    profile = projection.require_tilt_recent_profile(percent)
    candidate_id = projection.CANDIDATE_IDS[percent]
    candidate = TRUSTED_CANDIDATES.get(candidate_id)
    if candidate is None or profile.get("profile_sha256") != candidate.profile_sha256:
        common._fail("recent producer profile differs from independent host pin")
    return profile


def _upload_path(plan, suffix):
    anchor = dataclasses.replace(plan, candidate_id="R203", attempt=1)
    return common._control_path(anchor, "inputs-upload-" + suffix)


def _upload_identity(plan):
    require_package_binding(plan)
    return {
        "schema": "arv2-six-recent-exact-input-upload-v1",
        "organization_id_sha256": hashlib.sha256(plan.organization_id.encode("ascii")).hexdigest(),
        "package_sha256": PINNED_PACKAGE_SHA256,
        "lineage_sha256": PINNED_LINEAGE_SHA256,
        "activation_manifest_sha256": PINNED_ACTIVATION_MANIFEST_SHA256,
        "upload_manifest_sha256": UPLOAD_MANIFEST_SHA256,
        "object_count": UPLOAD_OBJECT_COUNT,
        "activation_published_last": True,
        "owner_waiver_id": _INPUT_WAIVER_ID,
    }


def require_uploaded_inputs(plan):
    identity = _upload_identity(plan)
    try:
        complete = (common._read(_upload_path(plan, "claim")) == identity
                    and common._read(_upload_path(plan, "valid")) == identity)
    except common.SixUniverseSettlementSubmissionError:
        complete = False
    if not complete:
        common._fail("recent exact input upload is not authenticated complete")


def _package(value):
    latest_builder.require_latest_order_input_package(value)
    if (
        value.package.package_sha256 != PINNED_PACKAGE_SHA256
        or value.lineage_sha256 != PINNED_LINEAGE_SHA256
        or value.package.upload_objects[-1].content_sha256 != PINNED_ACTIVATION_MANIFEST_SHA256
    ):
        common._fail("recent input wrapper differs from independently frozen package")
    return value.package


def _upload_manifest(package):
    rows = []
    for descriptor, payload in package_builder.iter_accepted_risk_preliminary_upload_objects(package):
        if (
            type(payload) is not bytes or not payload
            or len(payload) > transport.MAX_OBJECT_BYTES
            or descriptor.byte_count != len(payload)
            or descriptor.content_sha256 != hashlib.sha256(payload).hexdigest()
        ):
            common._fail("recent exact input bytes or descriptor changed")
        transport._safe_key(descriptor.object_store_key)
        rows.append((descriptor.object_store_key, descriptor.content_sha256,
                     descriptor.byte_count, descriptor.activation_manifest))
    if (
        len(rows) != UPLOAD_OBJECT_COUNT
        or not rows or rows[-1][3] is not True
        or any(row[3] is not False for row in rows[:-1])
        or len({row[0] for row in rows}) != len(rows)
        or hashlib.sha256(common._canonical(tuple(rows))).hexdigest() != UPLOAD_MANIFEST_SHA256
        or rows[-1][1] != PINNED_ACTIVATION_MANIFEST_SHA256
    ):
        common._fail("recent exact input inventory or activation order changed")
    return tuple(rows)


def _object_request(api, endpoint, body, content_type):
    """Only the two input-upload endpoints use the reviewed HTTP primitive."""
    common._client(api)
    if endpoint not in {"object/set", "object/properties"}:
        common._fail("recent input endpoint is not allowlisted")
    if type(body) is not bytes or len(body) > transport.MAX_OBJECT_BYTES + 4096:
        common._fail("recent input HTTP body exceeded its finite bound")
    headers = build_auth_headers(api._credentials, api._clock())
    headers["Content-Type"] = content_type
    try:
        _status, raw = api._transport(API_BASE + "/" + endpoint, body, headers, api._timeout)
        response = json.loads(raw.decode("utf-8"))
    except Exception:
        common._fail("recent input " + endpoint + " request failed")
    if type(response) is not dict or response.get("success") is not True:
        common._fail("recent input " + endpoint + " response changed")
    return response


def upload_exact_inputs(plan, latest_package, api, *, owner_waiver_id):
    """Upload one exact private input inventory, publishing activation last."""
    identity = _upload_identity(plan)
    package = _package(latest_package)
    manifest = _upload_manifest(package)
    if owner_waiver_id != _INPUT_WAIVER_ID or type(owner_waiver_id) is not str:
        common._fail("recent input waiver does not cover this exact upload")
    claim_path = _upload_path(plan, "claim")
    if claim_path.exists():
        common._fail("recent input upload was already claimed")
    common._client(api)
    common._write(claim_path, identity)
    for index, (descriptor, payload) in enumerate(
        package_builder.iter_accepted_risk_preliminary_upload_objects(package)
    ):
        row = (descriptor.object_store_key, descriptor.content_sha256,
               descriptor.byte_count, descriptor.activation_manifest)
        if row != manifest[index] or hashlib.sha256(payload).hexdigest() != row[1]:
            common._fail("recent input changed during upload")
        boundary = transport._multipart_boundary(payload)
        if ("\r\n--" + boundary).encode("ascii") in payload:
            common._fail("recent input multipart boundary collides")
        parts = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="organizationId"\r\n\r\n{plan.organization_id}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="key"\r\n\r\n{row[0]}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="objectData"; filename="object.bin"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n'
        ).encode("ascii")
        body = parts + payload + f"\r\n--{boundary}--\r\n".encode("ascii")
        _object_request(api, "object/set", body, "multipart/form-data; boundary=" + boundary)
        metadata = _object_request(
            api, "object/properties",
            common._canonical({"organizationId": plan.organization_id, "key": row[0]}),
            "application/json",
        )
        entry = _UploadEntry(row[0], row[2], hashlib.md5(payload, usedforsecurity=False).hexdigest())
        try:
            formal._object_metadata_matches(metadata, entry)
        except formal.FormalQcSubmissionError:
            common._fail("recent uploaded input metadata did not authenticate exact bytes")
    common._write(_upload_path(plan, "valid"), identity)
    return identity


@dataclasses.dataclass(frozen=True)
class _UploadEntry:
    object_store_key: str
    byte_count: int
    content_md5: str


def launch_a1(plan, projection, api, *, owner_waiver_id):
    require_package_binding(plan)
    return common.launch_a1(plan, projection, api, owner_waiver_id=owner_waiver_id)


def preview(plan, projection):
    require_package_binding(plan)
    return common.preview(plan, projection)


def render_owner_waiver_payload(plan, projection):
    require_package_binding(plan)
    return common.render_owner_waiver_payload(plan, projection)


def poll_status(plan, launch, api):
    require_package_binding(plan)
    return common.poll_status(plan, launch, api)


def read_aggregates_once(plan, launch, api):
    require_package_binding(plan)
    return common.read_aggregates_once(plan, launch, api)


def compare_valid_receipts(plan):
    require_package_binding(plan)
    return common.compare_valid_receipts(plan)


def _recovery_binding(plan, evidence_sha256):
    """Bind an unresolved-visibility retry, not a claimed source correction."""
    if plan.candidate_id != "R203" or plan.attempt != 2 or (
        type(evidence_sha256) is not str or not common._HEX.fullmatch(evidence_sha256)
    ):
        common._fail("recent recovery is not the exact R203 second attempt")
    require_uploaded_inputs(plan)
    a1 = dataclasses.replace(plan, attempt=1)
    evidence = common._read(common._control_path(a1, "visibility-evidence"))
    expected = {
        "schema": "arv2-r203-worker-visibility-retry-evidence-v1",
        "candidate_id": "R203", "failed_attempt": 1,
        "project_id": _A2_PROJECT_ID, "backtest_id": _A1_BACKTEST_ID,
        "organization_id_sha256": hashlib.sha256(plan.organization_id.encode("ascii")).hexdigest(),
        "package_sha256": PINNED_PACKAGE_SHA256,
        "activation_manifest_sha256": PINNED_ACTIVATION_MANIFEST_SHA256,
        "source_files_sha256": TRUSTED_CANDIDATES["R203"].source_files_sha256,
        "api_same_org_exact_manifest_metadata_verified": True,
        "project_context_manifest_byte_count": 4523,
        "project_context_evaluator_manifest_readable": True,
        "input_loader_matches_successful_prior_sources": True,
        "initialization_ast_unchanged": True,
        "engine_contains_key_return_unmeasured": True,
        "root_cause_known": False, "source_or_economics_changed": False,
        "retry_hypothesis": "unresolved_transient_worker_visibility",
    }
    if common._canonical(evidence) != common._canonical(expected) or (
        hashlib.sha256(common._canonical(evidence)).hexdigest() != evidence_sha256
    ):
        common._fail("recent visibility evidence differs from its prospective digest")
    launch = common._read(common._control_path(a1, "launch"))
    candidate = common._match_launch(a1, launch)
    claim = common._exact_result_claim(a1, launch, candidate)
    if launch["project_id"] != _A2_PROJECT_ID or launch["backtest_id"] != _A1_BACKTEST_ID or (
        common._read(common._control_path(a1, "terminal")) != {
            "candidate_id": "R203", "status": "Runtime Error",
            "project_id": _A2_PROJECT_ID, "backtest_id": _A1_BACKTEST_ID,
        }
    ) or common._control_path(a1, "result-valid").exists():
        common._fail("recent recovery predecessor is not the exact failed A1")
    return {
        "visibility_evidence_sha256": evidence_sha256,
        "a1_claim_sha256": hashlib.sha256(common._canonical(claim)).hexdigest(),
        "prior_attempts_spent": 1, "recovery_project_id": _A2_PROJECT_ID,
    }


def _a2_waiver_payload(plan, identity, target_path):
    binding = _recovery_binding(plan, identity.get("visibility_evidence_sha256"))
    if any(identity.get(key) != value for key, value in binding.items()) or target_path is not None:
        common._fail("recent recovery identity differs from failed-A1 evidence")
    a1 = dataclasses.replace(plan, attempt=1)
    payload = json.loads(common._waiver_payload(a1, identity, None).decode("ascii"))
    payload.update({
        "attempt": 2, "owner_launch_waiver_id": _A2_WAIVER_ID,
        "action": "one_existing_private_project_order_backtest_launch",
        "project_id": _A2_PROJECT_ID, "backtest_name": plan.backtest_name,
        "mutating_endpoint_budget": {"compile/create": 1, "backtests/create": 1},
        **binding,
        "retry_hypothesis": "unresolved_transient_worker_visibility",
        "root_cause_known": False, "source_or_economics_changed": False,
    })
    return common._canonical(payload)


def render_visibility_a2_waiver(plan, projection, *, visibility_evidence_sha256):
    identity = common.preview(plan, projection)
    identity.update(_recovery_binding(plan, visibility_evidence_sha256))
    return _a2_waiver_payload(plan, identity, None)


def _require_a2_launch(plan, launch):
    binding = _recovery_binding(plan, launch.get("visibility_evidence_sha256"))
    if launch.get("project_id") != _A2_PROJECT_ID or (
        any(launch.get(key) != value for key, value in binding.items())
    ):
        common._fail("recent A2 launch differs from the exact failed A1 project")


def _valid_comparison_anchor(plan):
    found = []
    imported = _verified_mia_imported_anchor(plan)
    if imported is not None:
        found.append(imported)
    for attempt in (1, 2):
        anchor = dataclasses.replace(plan, candidate_id="R203", attempt=attempt)
        receipt = common._verified_ladder_result_receipt(anchor)
        if receipt is not None:
            found.append((attempt, receipt["matched_baseline_target_path_sha256"]))
    return found[0] if len(found) == 1 else None


def launch_visibility_a2(plan, projection, api, *, owner_waiver_id, visibility_evidence_sha256):
    """Spend one same-source/same-project retry of an unresolved hypothesis."""
    identity = common.preview(plan, projection)
    binding = _recovery_binding(plan, visibility_evidence_sha256)
    identity.update(binding)
    payload = _a2_waiver_payload(plan, identity, None)
    if owner_waiver_id != _A2_WAIVER_ID or type(owner_waiver_id) is not str:
        common._fail("recent A2 waiver does not cover this exact retry")
    claim_path = common._control_path(plan, "claim")
    if claim_path.exists():
        common._fail("recent A2 attempt was already claimed")
    common._client(api)
    common._post(api, "authenticate", {})
    rows = common._post(api, "projects/read", {"projectId": _A2_PROJECT_ID}).get("projects")
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        common._fail("recent A2 existing project is unavailable")
    row = rows[0]
    collaborators = row.get("collaborators")
    if (row.get("projectId") != _A2_PROJECT_ID or row.get("name") != plan.project_name
            or row.get("organizationId") != plan.organization_id or row.get("language") != "Py"
            or row.get("owner") is not True or row.get("codeRunning") is not False
            or type(collaborators) is not list or len(collaborators) > 1
            or any(type(item) is not dict or item.get("owner") is not True for item in collaborators)):
        common._fail("recent A2 project is not exact, private, and idle")
    common._check_uploaded_source(_A2_PROJECT_ID, identity, api)
    inventory = common._post(api, "backtests/list", {
        "projectId": _A2_PROJECT_ID, "includeStatistics": False})
    runs = inventory.get("backtests")
    if type(runs) is not list or len(runs) != 1 or inventory.get("count") != 1 or (
        type(runs[0]) is not dict or runs[0].get("backtestId") != _A1_BACKTEST_ID
        or runs[0].get("name") != dataclasses.replace(plan, attempt=1).backtest_name
        or runs[0].get("status") != "Runtime Error"
        or ("projectId" in runs[0] and runs[0]["projectId"] != _A2_PROJECT_ID)
    ):
        common._fail("recent A2 project does not contain exactly the one failed A1")
    authority = {
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": "arv2-six-universe-r203-settlement-waiver-v1",
        "owner_launch_waiver_id": _A2_WAIVER_ID,
        "owner_waived_payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    common._write(claim_path, {**identity, **authority, "matched_baseline_target_path_sha256": None})
    compile_id = common._post(api, "compile/create", {"projectId": _A2_PROJECT_ID}).get("compileId")
    if type(compile_id) is not str or not common._ID.fullmatch(compile_id):
        common._fail("recent A2 compile identity changed; attempt remains spent")
    for poll in range(120):
        state = common._post(api, "compile/read", {"projectId": _A2_PROJECT_ID, "compileId": compile_id})
        if state.get("compileId") != compile_id or state.get("state") not in {
            "InQueue", "Building", "BuildSuccess", "BuildError"}:
            common._fail("recent A2 compile state changed; attempt remains spent")
        if state["state"] in {"BuildSuccess", "BuildError"}:
            break
        if poll < 119:
            common.time.sleep(2)
    else:
        common._fail("recent A2 compile poll exhausted; attempt remains spent")
    if state["state"] == "BuildError":
        common._write(common._control_path(plan, "terminal"), {
            "candidate_id": "R203", "attempt": 2, "status": "BuildError",
            "project_id": _A2_PROJECT_ID, "compile_id": compile_id})
        common._fail("recent A2 compile failed; attempt remains spent")
    run = common._post(api, "backtests/create", {
        "projectId": _A2_PROJECT_ID, "compileId": compile_id,
        "backtestName": plan.backtest_name}).get("backtest")
    if type(run) is not dict or type(run.get("backtestId")) is not str or (
        not common._ID.fullmatch(run["backtestId"]) or run.get("projectId") != _A2_PROJECT_ID
        or run.get("name") != plan.backtest_name or run.get("status") not in {"In Queue...", "In Progress..."}
    ):
        common._fail("recent A2 launch identity changed; attempt remains spent")
    receipt = {**{key: value for key, value in identity.items() if key != "source_files"},
        **authority, "matched_baseline_target_path_sha256": None,
        "project_id": _A2_PROJECT_ID, "project_name": plan.project_name,
        "compile_id": compile_id, "backtest_id": run["backtestId"],
        "backtest_name": plan.backtest_name}
    common._write(common._control_path(plan, "launch"), receipt)
    return receipt


# Import an owner/Mia run, never manufacture a Codex launch or waiver for it.
_MIA_BACKTEST_ID = "10769b9d9b285c5413823cd8dda3d64c"
_MIA_SNAPSHOT_ID = 36980748
_MIA_RUN_NAME = "R203 A1 contains-key-fix rerun"
_MIA_CREATED_AT = "2026-09-26 08:02:36"
_MIA_MODIFIED_AT = "2026-09-26 08:02:34"
_MIA_INPUT_PATH = "accepted_risk_order_level_input_runtime.py"
_MIA_INPUT_SHA256 = "66e441f73d624e63464561ba725d30e751d575785abd2aef9b126ad16364aa12"
_MIA_INPUT_BYTES = 24307
_MIA_COLLABORATOR_PUBLIC_ID = "A-8cc95e2e99f67eb81724ea5d40e4b4d2"


def _mia_control_path(plan, name):
    if name not in {"mia-result-read-claim", "mia-result-valid", "mia-authorized-aggregate"}:
        common._fail("recent Mia control name is not allowlisted")
    anchor = dataclasses.replace(plan, candidate_id="R203", attempt=1)
    root = common._control_path(anchor, "claim").parent
    return root / ("R203-MIA-A2-" + name + ".json")


def _mia_predecessor(plan):
    anchor = dataclasses.replace(plan, candidate_id="R203", attempt=1)
    require_uploaded_inputs(anchor)
    launch = common._read(common._control_path(anchor, "launch"))
    candidate = common._match_launch(anchor, launch)
    claim = common._exact_result_claim(anchor, launch, candidate)
    terminal = {"candidate_id": "R203", "status": "Runtime Error",
                "project_id": _A2_PROJECT_ID, "backtest_id": _A1_BACKTEST_ID}
    if (launch["project_id"] != _A2_PROJECT_ID or launch["backtest_id"] != _A1_BACKTEST_ID
            or common._read(common._control_path(anchor, "terminal")) != terminal
            or common._control_path(anchor, "result-valid").exists()
            or common._control_path(dataclasses.replace(anchor, attempt=2), "claim").exists()):
        common._fail("recent Mia import predecessor or attempt census changed")
    return claim


def _mia_static_identity(plan):
    require_package_binding(plan)
    candidate = MIA_R203_CANDIDATE
    prior = TRUSTED_CANDIDATES["R203"]
    profile = require_profile(100)
    if (type(candidate) is not common._Candidate or candidate.candidate_id != "R203"
            or any(getattr(candidate, key) != getattr(prior, key) for key in (
                "role", "variant", "profile_sha256", "summary_schema", "source_count"))
            or candidate.source_count != 16):
        common._fail("recent Mia import changed the frozen economic identity")
    claim = _mia_predecessor(plan)
    return {
        "schema": "arv2-r203-mia-import-read-v1", "candidate_id": "R203", "attempt": 2,
        "organization_id_sha256": hashlib.sha256(plan.organization_id.encode("ascii")).hexdigest(),
        "project_id": _A2_PROJECT_ID, "backtest_id": _MIA_BACKTEST_ID,
        "snapshot_id": _MIA_SNAPSHOT_ID, "created_at": _MIA_CREATED_AT,
        "source_modified_at": _MIA_MODIFIED_AT,
        "projection_sha256": candidate.projection_sha256,
        "source_files_sha256": candidate.source_files_sha256,
        "profile_id": profile["profile_id"], "profile_sha256": candidate.profile_sha256,
        "package_sha256": PINNED_PACKAGE_SHA256,
        "activation_manifest_sha256": PINNED_ACTIVATION_MANIFEST_SHA256,
        "a1_claim_sha256": hashlib.sha256(common._canonical(claim)).hexdigest(),
        "prior_attempts_spent": 1, "attempts_spent_including_mia": 2,
        "provenance": "owner_Mia_run_with_exact_current_source_verified_before_result_read",
        "historical_snapshot_bytes_verified": False,
        "codex_launch_or_waiver_claimed": False,
    }


def _mia_projection_identity(plan, projection):
    identity = _mia_static_identity(plan)
    candidate = MIA_R203_CANDIDATE
    if (plan.candidate_id != "R203" or plan.attempt != 1
            or type(projection) is not common.base_projection.AcceptedRiskSixUniverseOrderQcProjection
            or any(getattr(projection, key) != getattr(candidate, key) for key in (
                "role", "variant", "projection_sha256", "profile_sha256"))
            or projection.schema != candidate.projection_schema
            or projection.package_sha256 != plan.package_sha256
            or projection.activation_manifest_sha256 != plan.activation_manifest_sha256
            or projection.profile_id != identity["profile_id"]):
        common._fail("recent Mia corrected projection identity changed")
    manifest = common._source_manifest(projection, candidate)
    semantic = {key: value for key, value in projection.to_record().items()
                if key not in {"projection_id", "projection_sha256"}}
    if (hashlib.sha256(common._canonical(semantic)).hexdigest() != candidate.projection_sha256
            or projection.projection_id != (
                "arv2-six-universe-order-tilt100-recent-direct-read-qc-projection-"
                + candidate.projection_sha256[:24])):
        common._fail("recent Mia corrected projection is not self-authenticating")
    prior = {row[0]: tuple(row) for row in _mia_predecessor(plan)["source_files"]}
    changed = [row[0] for row in manifest if prior.get(row[0]) != row]
    if (set(prior) != {row[0] for row in manifest} or changed != [_MIA_INPUT_PATH]
            or next(row for row in manifest if row[0] == _MIA_INPUT_PATH)
            != (_MIA_INPUT_PATH, _MIA_INPUT_SHA256, _MIA_INPUT_BYTES)):
        common._fail("recent Mia correction changed more than the exact input transport")
    return identity


def _parse_mia_statistics(plan, statistics):
    candidate = MIA_R203_CANDIDATE
    if (type(statistics) is not dict or tuple(sorted(key for key in statistics
            if type(key) is str and key.startswith("ARV2_SIX_GATE_ORDER_"))) != common._CUSTOM_NAMES):
        common._fail("recent Mia custom statistic inventory changed")
    try:
        _text, meta = common.cap90._statistic(statistics[common.base_runtime.META_STATISTIC_NAME])
        aggregate_text, aggregate = common.cap90._statistic(
            statistics[common.base_runtime.AGGREGATES_STATISTIC_NAME])
    except (KeyError, common.cap90.Cap90QcSubmissionError):
        common._fail("recent Mia statistics are not bounded canonical JSON")
    expected_meta = {
        "schema": common.base_runtime.META_SCHEMA, "role": candidate.role,
        "profile_id": require_profile(100)["profile_id"],
        "profile_sha256": candidate.profile_sha256, "package_sha256": plan.package_sha256,
        "activation_manifest_sha256": plan.activation_manifest_sha256,
        "result_transport": "two_bounded_custom_summary_statistics",
        "aggregate_schema": candidate.summary_schema,
        "aggregate_sha256": hashlib.sha256(aggregate_text.encode("ascii")).hexdigest(),
        "raw_provider_rows": False, "raw_price_rows": False, "raw_order_rows": False,
        "backtest_only": True, "preliminary": True, "formal": False, "trading": False,
    }
    if (set(meta) != common.cap90._META_FIELDS
            or any(type(meta.get(key)) is not type(value) or meta.get(key) != value
                   for key, value in expected_meta.items())
            or any(type(meta.get(key)) is not str or not common._ID.fullmatch(meta[key])
                   for key in ("package_id", "symbol_resolution_id"))
            or type(meta.get("symbol_resolution_sha256")) is not str
            or not common._HEX.fullmatch(meta["symbol_resolution_sha256"])
            or any(type(aggregate.get(key)) is not type(value) or aggregate.get(key) != value
                   for key, value in {"profile_id": expected_meta["profile_id"],
                       "profile_sha256": candidate.profile_sha256, "backtest_only": True,
                       "preliminary": True, "formal": False, "live_orders": False,
                       "paper_orders": False, "funded_orders": False,
                       "deployment": False, "trading": False}.items())):
        common._fail("recent Mia result lineage, digest, or safety flags changed")
    common._settlement_aggregate(aggregate, candidate, matched_target_path=None)
    # Keep the validated canonical artifact itself so its raw-text digest can
    # be rechecked offline; do not double-encode or re-project before hashing.
    return {"meta": meta, "aggregates": aggregate, "run_valid": aggregate["run_valid"],
            "comparison_valid": False}


def read_imported_r203_once(plan, projection, api):
    """Consume two bounded custom statistics from the exact second Mia run.

    File readback proves current bytes and their pre-run modification times;
    QC does not expose historical snapshot bytes. Nothing here launches,
    edits, retries, reads logs/orders, or invents a Codex permit.
    """
    identity = _mia_projection_identity(plan, projection)
    claim_path = _mia_control_path(plan, "mia-result-read-claim")
    if claim_path.exists():
        common._fail("recent Mia imported result read was already claimed")
    common._client(api)
    rows = common._post(api, "projects/read", {"projectId": _A2_PROJECT_ID}).get("projects")
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        common._fail("recent Mia exact project is unavailable")
    owner = rows[0]
    collaborators = owner.get("collaborators")
    if (owner.get("projectId") != _A2_PROJECT_ID or owner.get("name") != plan.project_name
            or owner.get("organizationId") != plan.organization_id or owner.get("language") != "Py"
            or owner.get("owner") is not True or type(owner.get("codeRunning")) is not bool
            or type(collaborators) is not list or not 1 <= len(collaborators) <= 2
            or any(type(item) is not dict for item in collaborators)
            or sum(item.get("owner") is True for item in collaborators) != 1
            or any(item.get("owner") is not False
                   or item.get("publicId") != _MIA_COLLABORATOR_PUBLIC_ID
                   for item in collaborators if item.get("owner") is not True)):
        common._fail("recent Mia project or collaborator identity changed")
    files = common._post(api, "files/read", {"projectId": _A2_PROJECT_ID}).get("files")
    expected = {item.project_path: item.source_bytes.decode("ascii") for item in projection.source_files}
    if type(files) is not list or len(files) != len(expected):
        common._fail("recent Mia source inventory changed")
    observed = {}
    for row in files:
        if (type(row) is not dict or row.get("projectId") != _A2_PROJECT_ID
                or type(row.get("name")) is not str or row["name"] in observed
                or type(row.get("content")) is not str or row.get("modified") != _MIA_MODIFIED_AT):
            common._fail("recent Mia source identity or pre-run modification time changed")
        observed[row["name"]] = row["content"]
    if observed != expected:
        common._fail("recent Mia source bytes changed")
    listing = common._post(api, "backtests/list", {
        "projectId": _A2_PROJECT_ID, "includeStatistics": False})
    runs = listing.get("backtests")
    if (type(runs) is not list or len(runs) != 2 or listing.get("count") != 2
            or any(type(row) is not dict for row in runs)
            or {row.get("backtestId") for row in runs} != {_A1_BACKTEST_ID, _MIA_BACKTEST_ID}):
        common._fail("recent Mia exact two-attempt run inventory changed")
    run = next(row for row in runs if row["backtestId"] == _MIA_BACKTEST_ID)
    prior_run = next(row for row in runs if row["backtestId"] == _A1_BACKTEST_ID)
    if (prior_run.get("status") != "Runtime Error"
            or prior_run.get("name") != plan.backtest_name
            or prior_run.get("projectId") != _A2_PROJECT_ID
            or any(run.get(key) != value for key, value in {
                "projectId": _A2_PROJECT_ID, "name": _MIA_RUN_NAME,
                "status": "Completed.", "snapshotId": _MIA_SNAPSHOT_ID,
                "created": _MIA_CREATED_AT}.items())):
        common._fail("recent Mia run identity, snapshot, or completion changed")
    common._write(claim_path, identity)  # Durable before the only outcome read.
    response = common._post(api, "backtests/read", {
        "projectId": _A2_PROJECT_ID, "backtestId": _MIA_BACKTEST_ID})
    run = response.get("backtest")
    if (type(run) is not dict or any(run.get(key) != value for key, value in {
            "projectId": _A2_PROJECT_ID, "backtestId": _MIA_BACKTEST_ID,
            "name": _MIA_RUN_NAME, "status": "Completed.",
            "snapshotId": _MIA_SNAPSHOT_ID, "created": _MIA_CREATED_AT}.items())):
        common._fail("recent Mia returned result identity changed; read remains spent")
    result = _parse_mia_statistics(plan, run.get("statistics"))
    common._write(_mia_control_path(plan, "mia-authorized-aggregate"), result)
    if result["run_valid"] is True:
        common._write(_mia_control_path(plan, "mia-result-valid"), {
            **identity, "run_valid": True,
            "aggregate_sha256": result["meta"]["aggregate_sha256"],
            "stored_result_sha256": hashlib.sha256(common._canonical(result)).hexdigest(),
            "matched_baseline_target_path_sha256": result["aggregates"]["matched_baseline_target_path_sha256"],
            "matched_baseline_profile_sha256": MATCHED_BASELINE_PROFILE_SHA256,
            "comparison_valid": False,
        })
    return result


def _verified_mia_imported_anchor(plan):
    """Authenticate the locally retained imported result, without QC I/O."""
    anchor = dataclasses.replace(plan, candidate_id="R203", attempt=1)
    path = _mia_control_path(anchor, "mia-result-valid")
    if not path.exists():
        return None
    try:
        identity = _mia_static_identity(anchor)
        if common._read(_mia_control_path(anchor, "mia-result-read-claim")) != identity:
            return None
        result = common._read(_mia_control_path(anchor, "mia-authorized-aggregate"))
        if set(result) != {"meta", "aggregates", "run_valid", "comparison_valid"}:
            return None
        statistics = {common.base_runtime.META_STATISTIC_NAME: common._canonical(result["meta"]).decode("ascii"),
                      common.base_runtime.AGGREGATES_STATISTIC_NAME: common._canonical(result["aggregates"]).decode("ascii")}
        parsed = _parse_mia_statistics(anchor, statistics)
        if parsed != result or result["run_valid"] is not True or result["comparison_valid"] is not False:
            return None
        expected = {**identity, "run_valid": True,
            "aggregate_sha256": result["meta"]["aggregate_sha256"],
            "stored_result_sha256": hashlib.sha256(common._canonical(result)).hexdigest(),
            "matched_baseline_target_path_sha256": result["aggregates"]["matched_baseline_target_path_sha256"],
            "matched_baseline_profile_sha256": MATCHED_BASELINE_PROFILE_SHA256,
            "comparison_valid": False}
        if common._read(path) != expected:
            return None
    except (common.SixUniverseSettlementSubmissionError, KeyError, TypeError, ValueError):
        return None
    return (2, expected["matched_baseline_target_path_sha256"])
