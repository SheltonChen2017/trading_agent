"""Prospective R268 A3 correction for LEAN's whole-share split truncation.

The spent A1/A2 source and manifests remain immutable.  The A1-rendered
split quantity comparison and its derived profile identities change; the
authenticated same-session split, cash/price receipt, replan, orders, fees,
targets, and validity rule remain.
"""

import hashlib

from . import eight_universe_qcom_admitted_projection as renderer
from . import eight_universe_split_truncation_projection as split
from . import eight_universe_study as study
from . import six_universe_relaxed_submission as adapter
from . import six_universe_settlement_submission as common


MANIFEST_SCHEMA = "arv2-eight-r268-a3-split-truncation-manifest-v1"
PROJECTION_SCHEMA = "arv2-eight-r268-a3-split-truncation-projection-v1"
_A1_MANIFEST_SHA256 = adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256
_A2_MANIFEST_SHA256 = adapter.FROZEN_EIGHT_R268_A2_MANIFEST_SHA256
_A3_PROFILE_SHA256 = "222928e688aa56018dc5dfd4968a505a63eb8bef4207b38aaf6c37c74841b01d"
_A3_BASELINE_PROFILE_SHA256 = "2ff2ff702c7f4fe24a5ed0f9af421d7d63874768b8fa0f5ff69f483be5509aad"


def _fail(message):
    adapter._fail(message)


def _a1_row():
    return adapter._eight_universe_manifest()["candidates"][0]


def _a2_row():
    return adapter._eight_r268_a2_manifest()["candidates"][0]


def build_projection(package):
    """Render a separate A3 projection from the immutable A1 source."""
    a1, profile = renderer.build_eight_universe_projection(package, "ar_off", "R268")
    a1_row, a2_row = _a1_row(), _a2_row()
    if (a1.projection_sha256 != a1_row["projection_sha256"]
            or a1.profile_sha256 != a1_row["profile_sha256"]
            or profile["profile_sha256"] != a1_row["profile_sha256"]
            or a2_row["profile_sha256"] != a1_row["profile_sha256"]):
        _fail("R268 A3 A1/A2 source or strategy profile changed")
    return split.correct_projection(
        a1, profile, schema=PROJECTION_SCHEMA,
        projection_id_prefix="arv2-eight-r268-a3-split-truncation-projection-")


def freeze_manifest(package):
    """Compute the A3 manifest offline before any QC operation."""
    projection, profile = build_projection(package)
    a1, a2 = _a1_row(), _a2_row()
    files = [[item.project_path, item.content_sha256, item.byte_count]
             for item in projection.source_files]
    row = {**a1,
           "projection_schema": projection.schema,
           "projection_sha256": projection.projection_sha256,
           "profile_id": projection.profile_id,
           "profile_sha256": projection.profile_sha256,
           "matched_baseline_profile_sha256": profile["matched_baseline_profile_sha256"],
           "source_files_sha256": hashlib.sha256(common._canonical(files)).hexdigest(),
           "source_file_count": len(files),
           "total_source_bytes": projection.total_source_byte_count}
    return validate_manifest({
        "schema": MANIFEST_SCHEMA,
        "a1_manifest_sha256": _A1_MANIFEST_SHA256,
        "a1_projection_sha256": a1["projection_sha256"],
        "a2_manifest_sha256": _A2_MANIFEST_SHA256,
        "a2_projection_sha256": a2["projection_sha256"],
        "a1_profile_sha256": a1["profile_sha256"],
        "a2_profile_sha256": a2["profile_sha256"],
        "profile_sha256": profile["profile_sha256"],
        "package_sha256": projection.package_sha256,
        "activation_manifest_sha256": projection.activation_manifest_sha256,
        "candidates": [row],
    })


def validate_manifest(value):
    """A3 may change only the versioned projection and split source bytes."""
    a1, a2 = _a1_row(), _a2_row()
    if (type(value) is not dict
            or set(value) != {"schema", "a1_manifest_sha256",
                              "a1_projection_sha256", "a1_profile_sha256",
                              "a2_manifest_sha256", "a2_projection_sha256",
                              "a2_profile_sha256", "profile_sha256",
                              "package_sha256", "activation_manifest_sha256",
                              "candidates"}
            or value["schema"] != MANIFEST_SCHEMA
            or value["a1_manifest_sha256"] != _A1_MANIFEST_SHA256
            or value["a1_projection_sha256"] != a1["projection_sha256"]
            or value["a1_profile_sha256"] != a1["profile_sha256"]
            or value["a2_manifest_sha256"] != _A2_MANIFEST_SHA256
            or value["a2_projection_sha256"] != a2["projection_sha256"]
            or value["a2_profile_sha256"] != a2["profile_sha256"]
            or type(value["profile_sha256"]) is not str
            or adapter.cap._HEX.fullmatch(value["profile_sha256"]) is None
            or value["profile_sha256"] != _A3_PROFILE_SHA256
            or value["package_sha256"] != adapter._eight_universe_manifest()["package_sha256"]
            or value["activation_manifest_sha256"] !=
               adapter._eight_universe_manifest()["activation_manifest_sha256"]
            or type(value["candidates"]) is not list
            or len(value["candidates"]) != 1
            or type(value["candidates"][0]) is not dict):
        _fail("R268 A3 manifest or A1/A2 ancestry changed")
    row = value["candidates"][0]
    allowed = {"projection_schema", "projection_sha256", "source_files_sha256",
               "source_file_count", "total_source_bytes", "profile_id",
               "profile_sha256", "matched_baseline_profile_sha256"}
    if (set(row) != set(a1) or any(row[key] != a1[key] for key in a1
                                   if key not in allowed)
            or row["projection_schema"] != PROJECTION_SCHEMA
            or row["profile_sha256"] != value["profile_sha256"]
            or row["profile_id"] != a1["profile_id"] + "-lean-int-split-truncation-v1"
            or type(row["matched_baseline_profile_sha256"]) is not str
            or adapter.cap._HEX.fullmatch(row["matched_baseline_profile_sha256"]) is None
            or row["matched_baseline_profile_sha256"] != _A3_BASELINE_PROFILE_SHA256
            or row["statistic_names"] != study.STATISTIC_NAMES
            or type(row["source_file_count"]) is not int
            or row["source_file_count"] != 17
            or type(row["total_source_bytes"]) is not int
            or not 0 < row["total_source_bytes"] + 32_768 <= 448 * 1024
            or any(type(row[key]) is not str or adapter.cap._HEX.fullmatch(row[key]) is None
                   for key in ("projection_sha256", "source_files_sha256"))
            or row["projection_sha256"] in {a1["projection_sha256"],
                                           a2["projection_sha256"]}
            or row["source_files_sha256"] in {a1["source_files_sha256"],
                                              a2["source_files_sha256"]}):
        _fail("R268 A3 split source or original strategy fields changed")
    return value
