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


def require_package_binding(plan):
    if (
        type(plan) is not common.SettlementQcPlan
        or plan.candidate_id not in common._RECENT_PERCENTS
        or plan.attempt != 1
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
