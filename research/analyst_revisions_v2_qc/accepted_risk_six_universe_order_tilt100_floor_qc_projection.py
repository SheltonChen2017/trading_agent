"""R194 positive-residual 100% tilt from the exact frozen R193 source.

This pure host projection changes only target transfer, profile identity, and
main role. It performs no cloud action, reads no outcome, and leaves R193 A1
bytes untouched. The aggregate donor keeps at least one 1e-30 quantum.
"""

import dataclasses
import hashlib
import json

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_tilt100_qc_projection as _r193


class SixUniverseTilt100FloorQcProjectionError(ValueError):
    """The exact predecessor, transfer rule, profile, or output pin changed."""


TILT_ROLE = "matched_revision_tilt100_floor"
TILT_VARIANT = "cap90_matched_revision_tilt100_floor_settlement_v1"
PROFILE_SCHEMA = "arv2-six-universe-order-tilt100-floor-settlement-profile-v1"
PROFILE_ID = "arv2-six-universe-order-matched-revision-tilt100-floor-settlement-v1"
SUMMARY_SCHEMA = "arv2-six-universe-order-tilt100-floor-settlement-summary-v1"
DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt100-floor-decision-target-v1"
TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt100-floor-target-path-v1"
PROJECTION_SCHEMA = "arv2-six-universe-order-qc-projection-tilt100-floor-settlement-v1"
PROJECTION_ID_PREFIX = "arv2-six-universe-order-tilt100-floor-settlement-qc-projection-"
MINIMUM_STOCK_RESIDUAL_WEIGHT = "1e-30"

PINNED_R193_PROJECTION_SHA256 = _r193.PINNED_TILT100_PROJECTION_SHA256
PINNED_R193_PROFILE_SHA256 = _r193.PINNED_TILT100_PROFILE_SHA256
PINNED_R193_SOURCE_MANIFEST_SHA256 = _r193.PINNED_TILT100_SOURCE_MANIFEST_SHA256
PINNED_R193_TOTAL_SOURCE_BYTES = _r193.PINNED_TILT100_TOTAL_SOURCE_BYTES

_TRANSFORMS = {
    "accepted_risk_six_universe_order_tilt_targets.py": (
        ('TILT_ROLE = "matched_revision_tilt100"',
         f'TILT_ROLE = "{TILT_ROLE}"', 1),
        ('DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt100-decision-target-v1"',
         f'DECISION_TARGET_SCHEMA = "{DECISION_TARGET_SCHEMA}"', 1),
        ('TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt100-target-path-v1"',
         f'TARGET_PATH_SCHEMA = "{TARGET_PATH_SCHEMA}"', 1),
        ('"arv2-six-universe-order-tilt100-target-path-"',
         '"arv2-six-universe-order-tilt100-floor-target-path-"', 1),
        ('moved = min(room, available)',
         'moved = min(room, available, stock_totals[donor_id] - WEIGHT_TRANSFER_QUANTUM)', 1),
    ),
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
        ('TILT_VARIANT = "cap90_matched_revision_tilt100_settlement_v1"',
         f'TILT_VARIANT = "{TILT_VARIANT}"', 1),
        ('TILT_PROFILE_SCHEMA = "arv2-six-universe-order-tilt100-settlement-profile-v1"',
         f'TILT_PROFILE_SCHEMA = "{PROFILE_SCHEMA}"', 1),
        ('TILT_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt100-settlement-summary-v1"',
         f'TILT_SUMMARY_SCHEMA = "{SUMMARY_SCHEMA}"', 1),
        ('"profile_id": "arv2-six-universe-order-matched-revision-tilt100-settlement-v1",',
         f'"profile_id": "{PROFILE_ID}",', 1),
        ('"maximum_stock_weight_change_fraction": "1.00",\n'
         '        "weight_transfer_quantum":',
         '"maximum_stock_weight_change_fraction": "1.00",\n'
         f'        "minimum_stock_residual_weight": "{MINIMUM_STOCK_RESIDUAL_WEIGHT}",\n'
         '        "weight_transfer_quantum":', 1),
    ),
    "main.py": (
        ('class ARV2SixUniverseOrderTilt100Algorithm(QCAlgorithm):',
         'class ARV2SixUniverseOrderTilt100FloorAlgorithm(QCAlgorithm):', 1),
        ("role='matched_revision_tilt100',", f"role='{TILT_ROLE}',", 1),
        ("variant='cap90_matched_revision_tilt100_settlement_v1',",
         f"variant='{TILT_VARIANT}',", 1),
    ),
}

# The 13 unchanged output files inherit the frozen R193 exact per-file pins;
# the three changed files and the complete manifest are independently pinned.
PINNED_PROFILE_SHA256 = (
    "1f338baac6cad9ea0e95661d8320711013435e24d20a2d7ee67496194a430053"
)
PINNED_PROJECTION_SHA256 = (
    "c10b1aa8c6d56104ec6fcdc134a4a335ae648df9be67a75894cf79090b33dd85"
)
PINNED_SOURCE_MANIFEST_SHA256 = (
    "2e51cd6547908ac2c3adbae5430fdb7ce4e2af8e724002281931c59d58b88d5c"
)
PINNED_TOTAL_SOURCE_BYTES = 425_919
PINNED_FILE_SHA256S = {
    **_r193.PINNED_TILT100_FILE_SHA256S,
    "accepted_risk_six_universe_order_tilt_targets.py": (
        "def7996e311d7bd3e0c7ac1dadeb46f8f36a16ae04d8bc833cb247c92664639d"
    ),
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
        "4b0c47a5b51d825831e2c88d5f44d800966c7db9db1656373f26b1c8adbfefc2"
    ),
    "main.py": "c58b48d21b765ff5e2a1a92b904040d0f4cf0de98394154d49b03991d72f4e0f",
}
PINNED_FILE_BYTE_COUNTS = {
    **_r193.PINNED_TILT100_FILE_BYTE_COUNTS,
    "accepted_risk_six_universe_order_tilt_targets.py": 20_828,
    "accepted_risk_six_universe_order_tilt_qc_runtime.py": 7_927,
    "main.py": 6_593,
}


def _error(message):
    raise SixUniverseTilt100FloorQcProjectionError(message)


def _replace_exact(source_bytes, replacements):
    if type(source_bytes) is not bytes or type(replacements) is not tuple:
        _error("R194 replacement contract changed")
    try:
        source = source_bytes.decode("ascii")
    except UnicodeError as exc:
        raise SixUniverseTilt100FloorQcProjectionError(
            "R193 projected source is not ASCII"
        ) from exc
    for old, new, count in replacements:
        if (type(old) is not str or type(new) is not str or type(count) is not int
                or count < 1 or old == new or source.count(old) != count):
            _error("R194 projected source lost an exact replacement point")
        source = source.replace(old, new, count)
    return source.encode("ascii")


def _render_profile():
    baseline = _r193.require_tilt100_profile()
    if (baseline["profile_sha256"] != PINNED_R193_PROFILE_SHA256
            or baseline["maximum_stock_weight_change_fraction"] != "1.00"
            or baseline["weight_transfer_quantum"]
            != "0.000000000000000000000000000001"):
        _error("R193 profile changed from exact pin")
    seed = {key: value for key, value in baseline.items()
            if key != "profile_sha256"}
    seed.update({
        "schema": PROFILE_SCHEMA,
        "profile_id": PROFILE_ID,
        "role": TILT_ROLE,
        "target_path_schema": TARGET_PATH_SCHEMA,
        "decision_target_schema": DECISION_TARGET_SCHEMA,
        "minimum_stock_residual_weight": MINIMUM_STOCK_RESIDUAL_WEIGHT,
    })
    return json.loads(_base._canonical({
        **seed, "profile_sha256": hashlib.sha256(_base._canonical(seed)).hexdigest(),
    }).decode("ascii"))


def require_tilt100_floor_profile():
    """Return the exact R194 profile; refuse any source or rule drift."""
    profile = _render_profile()
    if profile["profile_sha256"] != PINNED_PROFILE_SHA256:
        _error("R194 profile changed from its exact pin")
    return profile


def _build_unpinned(delta_package):
    predecessor = _r193.build_tilt100_settlement_projection(delta_package)
    if (predecessor.projection_sha256 != PINNED_R193_PROJECTION_SHA256
            or predecessor.profile_sha256 != PINNED_R193_PROFILE_SHA256
            or predecessor.total_source_byte_count != PINNED_R193_TOTAL_SOURCE_BYTES
            or len(predecessor.source_files) != 16):
        _error("R193 source changed from exact pin")
    predecessor_manifest = hashlib.sha256(_base._canonical(tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in predecessor.source_files
    ))).hexdigest()
    if predecessor_manifest != PINNED_R193_SOURCE_MANIFEST_SHA256:
        _error("R193 manifest changed from exact pin")
    profile = _render_profile()
    files = []
    for item in predecessor.source_files:
        if (item.byte_count != len(item.source_bytes)
                or item.content_sha256 != hashlib.sha256(item.source_bytes).hexdigest()
                or item.content_sha256 != _r193.PINNED_TILT100_FILE_SHA256S[item.project_path]
                or item.byte_count != _r193.PINNED_TILT100_FILE_BYTE_COUNTS[item.project_path]):
            _error("R193 projected file differs from exact pin")
        files.append(_base._source_file(
            item.project_path,
            _replace_exact(item.source_bytes, _TRANSFORMS[item.project_path])
            if item.project_path in _TRANSFORMS else item.source_bytes,
        ))
    files.sort(key=lambda item: item.project_path)
    if (len(files) != 16 or len({item.project_path for item in files}) != 16
            or any(item.byte_count > _base.MAXIMUM_QC_SOURCE_CHARACTERS
                   for item in files)):
        _error("R194 projected closure or per-file budget changed")
    for item in files:
        compile("from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"),
                item.project_path, "exec")
    total = sum(item.byte_count for item in files)
    if total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES:
        _error("R194 projected source exceeded 425,984-byte review budget")
    semantic = {key: value for key, value in predecessor.to_record().items()
                if key not in ("projection_id", "projection_sha256")}
    semantic.update({
        "schema": PROJECTION_SCHEMA,
        "role": TILT_ROLE,
        "variant": TILT_VARIANT,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
    })
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    value = dataclasses.replace(
        predecessor, schema=PROJECTION_SCHEMA,
        projection_id=PROJECTION_ID_PREFIX + digest[:24],
        projection_sha256=digest, role=TILT_ROLE, variant=TILT_VARIANT,
        profile_id=profile["profile_id"], profile_sha256=profile["profile_sha256"],
        source_files=tuple(files), total_source_byte_count=total,
    )
    if {key: item for key, item in value.to_record().items()
            if key not in ("projection_id", "projection_sha256")} != semantic:
        _error("R194 projected source failed self-authentication")
    return value


def build_tilt100_floor_projection(delta_package):
    """Build only the immutable, order-based R194 QC source closure."""
    value = _build_unpinned(delta_package)
    manifest = hashlib.sha256(_base._canonical(tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in value.source_files
    ))).hexdigest()
    files = {item.project_path: item for item in value.source_files}
    if (value.projection_sha256 != PINNED_PROJECTION_SHA256
            or value.profile_sha256 != PINNED_PROFILE_SHA256
            or manifest != PINNED_SOURCE_MANIFEST_SHA256
            or value.total_source_byte_count != PINNED_TOTAL_SOURCE_BYTES
            or set(files) != set(PINNED_FILE_SHA256S)
            or set(files) != set(PINNED_FILE_BYTE_COUNTS)
            or any(files[path].content_sha256 != PINNED_FILE_SHA256S[path]
                   or files[path].byte_count != PINNED_FILE_BYTE_COUNTS[path]
                   for path in files)):
        _error("R194 projected profile, source, or manifest changed from exact pin")
    return value


__all__ = (
    "DECISION_TARGET_SCHEMA", "MINIMUM_STOCK_RESIDUAL_WEIGHT", "PINNED_FILE_BYTE_COUNTS",
    "PINNED_FILE_SHA256S", "PINNED_PROFILE_SHA256", "PINNED_PROJECTION_SHA256",
    "PINNED_SOURCE_MANIFEST_SHA256", "PINNED_TOTAL_SOURCE_BYTES", "PROFILE_ID",
    "PROFILE_SCHEMA", "PROJECTION_ID_PREFIX", "PROJECTION_SCHEMA", "SUMMARY_SCHEMA",
    "SixUniverseTilt100FloorQcProjectionError", "TARGET_PATH_SCHEMA", "TILT_ROLE",
    "TILT_VARIANT", "build_tilt100_floor_projection", "require_tilt100_floor_profile",
)
