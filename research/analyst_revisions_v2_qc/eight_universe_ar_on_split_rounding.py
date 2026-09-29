"""Prospective split-consistent R269--R275 eight-sleeve order sources.

Each source starts from its immutable, unlaunched AR-on projection and applies
the same LEAN whole-share split overlay as R268 A3. This module has no QC I/O;
the submission adapter owns attempt routing and remote launch authority.
"""

import hashlib
import json
from pathlib import Path

from . import accepted_risk_six_universe_order_qc_projection as source_contract
from . import eight_universe_qcom_admitted_projection as renderer
from . import eight_universe_split_truncation_projection as split
from . import six_universe_relaxed_submission as adapter
from . import six_universe_settlement_submission as common


MANIFEST_SCHEMA = "arv2-eight-ar-on-split-truncation-manifest-v1"
MANIFEST_PATH = Path(__file__).with_name("eight_universe_ar_on_split_rounding.json")
FROZEN_MANIFEST_SHA256 = "abdc0f4bb48b7f463d696c4cc46af9655f63be60677683478b0d4b2880e4abe0"
ORIGINAL_MANIFEST_SHA256 = adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256
BASELINE_A3_MANIFEST_SHA256 = adapter.FROZEN_EIGHT_R268_A3_MANIFEST_SHA256
CANDIDATES = tuple(f"R{number}" for number in range(269, 276))
_ALLOWED_ROW_CHANGES = frozenset({
    "projection_schema", "projection_sha256", "source_files_sha256",
    "source_file_count", "total_source_bytes", "profile_id", "profile_sha256",
    "matched_baseline_profile_sha256",
})


def _fail(message):
    adapter._fail(message)


def _original_manifest():
    return adapter._eight_universe_manifest()


def _baseline_a3_row():
    return adapter._eight_r268_a3_manifest()["candidates"][0]


def _original_rows():
    rows = _original_manifest()["candidates"][1:8]
    if (len(rows) != len(CANDIDATES)
            or tuple(row["candidate_id"] for row in rows) != CANDIDATES):
        _fail("R269--R275 original frozen source inventory changed")
    return dict(zip(CANDIDATES, rows))


def _projection_schema(candidate):
    return f"arv2-eight-{candidate.lower()}-split-truncation-projection-v1"


def build_projection(package, candidate):
    """Return one corrected 17-file source, still without launch authority."""
    if type(candidate) is not str or candidate not in CANDIDATES:
        _fail("eight-universe corrected AR-on candidate is not frozen")
    old = _original_rows()[candidate]
    family = _original_manifest()
    original, old_profile = renderer.build_eight_universe_projection(
        package, old["arm"], candidate)
    if (original.projection_sha256 != old["projection_sha256"]
            or original.profile_id != old["profile_id"]
            or original.profile_sha256 != old["profile_sha256"]
            or old_profile["profile_sha256"] != old["profile_sha256"]
            or original.package_sha256 != family["package_sha256"]
            or original.activation_manifest_sha256 !=
               family["activation_manifest_sha256"]):
        _fail("eight-universe original AR-on source or profile changed")
    corrected, profile = split.correct_projection(
        original, old_profile, schema=_projection_schema(candidate),
        projection_id_prefix=(
            f"arv2-eight-{candidate.lower()}-split-truncation-projection-"))
    baseline = _baseline_a3_row()
    if (not baseline["profile_id"].endswith(split._SUFFIX)
            or profile["matched_baseline_profile_sha256"] ==
               old["matched_baseline_profile_sha256"]
            or profile["overnight_holding_drift_rule"] != split._RULE
            or profile["profile_id"] != old["profile_id"] + split._SUFFIX):
        _fail("eight-universe AR-on split policy differs from R268 A3")
    if (len(corrected.source_files) != 17
            or any(item.byte_count > source_contract.MAXIMUM_QC_SOURCE_CHARACTERS
                   for item in corrected.source_files)):
        _fail("eight-universe corrected AR-on source file budget changed")
    for item in corrected.source_files:
        source_contract._audit_source(item.project_path, item.source_bytes)
    return corrected, profile


def _candidate_row(old, projection, profile):
    files = [[item.project_path, item.content_sha256, item.byte_count]
             for item in projection.source_files]
    return {**old,
            "projection_schema": projection.schema,
            "projection_sha256": projection.projection_sha256,
            "profile_id": projection.profile_id,
            "profile_sha256": projection.profile_sha256,
            "matched_baseline_profile_sha256": profile[
                "matched_baseline_profile_sha256"],
            "source_files_sha256": hashlib.sha256(common._canonical(files)).hexdigest(),
            "source_file_count": len(files),
            "total_source_bytes": projection.total_source_byte_count}


def freeze_manifest(package):
    """Rebuild and validate all seven corrected rows before any outcome look."""
    original = _original_manifest()
    old_rows = _original_rows()
    rows = []
    for candidate in CANDIDATES:
        projection, profile = build_projection(package, candidate)
        rows.append(_candidate_row(old_rows[candidate], projection, profile))
    return validate_manifest({
        "schema": MANIFEST_SCHEMA,
        "original_manifest_sha256": ORIGINAL_MANIFEST_SHA256,
        "original_candidate_sha256s": {
            candidate: adapter._sha(old_rows[candidate]) for candidate in CANDIDATES},
        "baseline_a3_manifest_sha256": BASELINE_A3_MANIFEST_SHA256,
        "split_rule": split._RULE,
        "package_sha256": original["package_sha256"],
        "activation_manifest_sha256": original["activation_manifest_sha256"],
        "candidates": rows,
    })


def validate_manifest(value):
    """Permit only split-source/profile versioning of the seven old rows."""
    original = _original_manifest()
    old_rows = _original_rows()
    baseline = _baseline_a3_row()
    rows = value.get("candidates") if type(value) is dict else None
    if (type(value) is not dict
            or set(value) != {"schema", "original_manifest_sha256",
                              "original_candidate_sha256s",
                              "baseline_a3_manifest_sha256", "split_rule",
                              "package_sha256", "activation_manifest_sha256",
                              "candidates"}
            or value["schema"] != MANIFEST_SCHEMA
            or value["original_manifest_sha256"] != ORIGINAL_MANIFEST_SHA256
            or value["original_candidate_sha256s"] != {
                candidate: adapter._sha(old_rows[candidate])
                for candidate in CANDIDATES}
            or value["baseline_a3_manifest_sha256"] != BASELINE_A3_MANIFEST_SHA256
            or value["split_rule"] != split._RULE
            or value["package_sha256"] != original["package_sha256"]
            or value["activation_manifest_sha256"] != original["activation_manifest_sha256"]
            or not baseline["profile_id"].endswith(split._SUFFIX)
            or type(rows) is not list or len(rows) != len(CANDIDATES)):
        _fail("eight-universe AR-on correction ancestry or census changed")
    projections, profiles, sources = set(), set(), set()
    for row, candidate in zip(rows, CANDIDATES):
        old = old_rows[candidate]
        if (type(row) is not dict or set(row) != set(old)
                or row["candidate_id"] != candidate
                or any(row[key] != old[key] for key in old
                       if key not in _ALLOWED_ROW_CHANGES)
                or row["projection_schema"] != _projection_schema(candidate)
                or row["profile_id"] != old["profile_id"] + split._SUFFIX
                or row["matched_baseline_profile_sha256"] ==
                   old["matched_baseline_profile_sha256"]
                or row["profile_sha256"] == old["profile_sha256"]
                or row["projection_sha256"] == old["projection_sha256"]
                or row["source_files_sha256"] == old["source_files_sha256"]
                or type(row["source_file_count"]) is not int
                or row["source_file_count"] != old["source_file_count"]
                or type(row["total_source_bytes"]) is not int
                or not 0 < row["total_source_bytes"] +
                   source_contract.MINIMUM_REVIEW_MARGIN_BYTES <=
                   source_contract.MAXIMUM_TOTAL_SOURCE_BYTES
                or any(type(row[key]) is not str
                       or adapter.cap._HEX.fullmatch(row[key]) is None
                       for key in ("projection_sha256", "profile_sha256",
                                   "matched_baseline_profile_sha256",
                                   "source_files_sha256"))
                or row["projection_sha256"] in projections
                or row["profile_sha256"] in profiles
                or row["source_files_sha256"] in sources):
            _fail(f"eight-universe AR-on split source changed economics: {candidate}")
        projections.add(row["projection_sha256"])
        profiles.add(row["profile_sha256"])
        sources.add(row["source_files_sha256"])
    return value


def frozen_manifest():
    """Read the immutable seven-row manifest after its digest has been pinned."""
    if type(FROZEN_MANIFEST_SHA256) is not str:
        _fail("eight-universe AR-on correction is not frozen")
    raw = MANIFEST_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FROZEN_MANIFEST_SHA256:
        _fail("eight-universe AR-on correction manifest changed")
    return validate_manifest(json.loads(raw))
