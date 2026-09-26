"""Three separately pinned, backtest-only tilt sensitivities after R186's refusal.

R187=70%, R188=60%, R189=50%. Each starts from the exact R185 40% cloud
source and changes only the target, runtime, and entry point. These are
parameter looks on the already observed 2021--2025 period, not confirmation.
"""

import dataclasses
import hashlib
import json
from types import MappingProxyType

from . import accepted_risk_six_universe_order_qc_projection as _base
from . import accepted_risk_six_universe_order_tilt40_qc_projection as _r185


class SixUniverseTiltLadderQcProjectionError(ValueError):
    """A candidate, predecessor, or source identity changed from its pin."""


PERCENTS = (70, 60, 50)
_R185_PROJECTION_SHA256 = (
    "2a9f9a2175e2765c1136d4aca3d86d617bbee970769eecae6dcab2e0f1127c7d"
)
_R185_PROFILE_SHA256 = (
    "a76cead2de5fef1176803f77b2a7efd3cc11fa24734dcdcf91a047f4ae552539"
)
_R185_TOTAL_SOURCE_BYTES = 422_758
_CHANGED_PATHS = frozenset({
    "accepted_risk_six_universe_order_tilt_targets.py",
    "accepted_risk_six_universe_order_tilt_qc_runtime.py",
    "main.py",
})

# Derived from _build_unchecked and frozen before any successor QC mutation.
PINNED_PROFILES = MappingProxyType({
    70: "6189373282c0e5652bda0317d0133e1ccc52057116035ed6a51428788d8e31f2",
    60: "82592bb4c82078496899f2e225c31f6c47a759b93997f464fac731eff99ed875",
    50: "5314cab14e8f50e38998c07dead583eb38b57eefcb0e2ad8768d5681adec116e",
})
PINNED_PROJECTIONS = MappingProxyType({
    70: "3203481571307cbad000153542ac9529cb1e4a3ac1bac030f18150b6a22dcbe0",
    60: "3eed978da51ef82b0de3f44b2f3bb30311e27a8f628ed3f9b6663d902f78fc55",
    50: "e1f417b2a7e785e558ec0af83297083fa07c0bbc22c930447bb6e0e99a25f2d3",
})
PINNED_SOURCE_SHA256S = MappingProxyType({
    70: MappingProxyType({
        "accepted_risk_six_universe_order_tilt_qc_runtime.py":
            "341e161f5d5965faddeead64aa3993128feb6cf4bafce45868c82929481a5407",
        "accepted_risk_six_universe_order_tilt_targets.py":
            "145f0ef69113143876e516955194d6d98334d7c9d60793bcb68b5b1a132830e2",
        "main.py":
            "bc4358bbaea66ec75abc071ac1aee66ef9784be61d6916a029a528c14a8abcf5",
    }),
    60: MappingProxyType({
        "accepted_risk_six_universe_order_tilt_qc_runtime.py":
            "3c291acc5d8a9dbae07bc51502c584388b4d9802209cdf1756653f83724fdc23",
        "accepted_risk_six_universe_order_tilt_targets.py":
            "5aeb6b97af2b9759960321e21f0612cdb4b710efdb28307a4f15bd3311192b94",
        "main.py":
            "c76eac189a653afe0aa9a52214487f9f387333121d47b82ca4026ccf27a1ab4e",
    }),
    50: MappingProxyType({
        "accepted_risk_six_universe_order_tilt_qc_runtime.py":
            "aff0e9a6d6c204757fc070347c674a34ba6a7a588b7e117ad04ab6250305fee9",
        "accepted_risk_six_universe_order_tilt_targets.py":
            "f01d0baad9b2bc9b8808c01740f8e3da926d42d8f03fcb56ad01b210163507d2",
        "main.py":
            "270db49a2c48a6ea4a94ad432ef4b42232e2298ff94a9214d1893c94a1375a1a",
    }),
})
PINNED_TOTAL_SOURCE_BYTES = 422_758


def _error(message):
    raise SixUniverseTiltLadderQcProjectionError(message)


def _require_percent(percent):
    if type(percent) is not int or percent not in PERCENTS:
        _error("unsupported tilt ladder percent")
    return percent


def _identity(percent):
    percent = _require_percent(percent)
    stem = f"arv2-six-universe-order-tilt{percent}"
    return {
        "role": f"matched_revision_tilt{percent}",
        "variant": f"cap90_matched_revision_tilt{percent}_admission_bridge_v1",
        "profile_schema": f"{stem}-bridge-profile-v1",
        "profile_id": (
            f"arv2-six-universe-order-matched-revision-tilt{percent}-bridge-v1"
        ),
        "summary_schema": f"{stem}-bridge-summary-v1",
        "decision_target_schema": f"{stem}-decision-target-v1",
        "target_path_schema": f"{stem}-target-path-v1",
        "projection_schema": f"{stem}-qc-projection-bridge-v1",
    }


def _replacements(percent):
    identity = _identity(percent)
    pct = str(percent)
    fraction = f"0.{percent:02d}"
    role = identity["role"]
    return {
        "accepted_risk_six_universe_order_tilt_targets.py": (
            ('TILT_ROLE = "matched_revision_tilt40"',
             f'TILT_ROLE = "{role}"', 1),
            ('MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("0.40")',
             f'MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("{fraction}")', 1),
            ('DECISION_TARGET_SCHEMA = "arv2-six-universe-order-tilt40-decision-target-v1"',
             f'DECISION_TARGET_SCHEMA = "{identity["decision_target_schema"]}"', 1),
            ('TARGET_PATH_SCHEMA = "arv2-six-universe-order-tilt40-target-path-v1"',
             f'TARGET_PATH_SCHEMA = "{identity["target_path_schema"]}"', 1),
            ('bounded by 40% of its own post-cap',
             f'bounded by {pct}% of its own post-cap', 1),
            ('"maximum_stock_weight_change_fraction": "0.40"',
             f'"maximum_stock_weight_change_fraction": "{fraction}"', 1),
            ('"arv2-six-universe-order-tilt40-target-path-"',
             f'"arv2-six-universe-order-tilt{pct}-target-path-"', 1),
        ),
        "accepted_risk_six_universe_order_tilt_qc_runtime.py": (
            ('TILT_VARIANT = "cap90_matched_revision_tilt40_admission_bridge_v1"',
             f'TILT_VARIANT = "{identity["variant"]}"', 1),
            ('TILT_PROFILE_SCHEMA = "arv2-six-universe-order-tilt40-bridge-profile-v1"',
             f'TILT_PROFILE_SCHEMA = "{identity["profile_schema"]}"', 1),
            ('TILT_SUMMARY_SCHEMA = "arv2-six-universe-order-tilt40-bridge-summary-v1"',
             f'TILT_SUMMARY_SCHEMA = "{identity["summary_schema"]}"', 1),
            ('"profile_id": "arv2-six-universe-order-matched-revision-tilt40-bridge-v1"',
             f'"profile_id": "{identity["profile_id"]}"', 1),
            ('"maximum_stock_weight_change_fraction": "0.40"',
             f'"maximum_stock_weight_change_fraction": "{fraction}"', 2),
        ),
        "main.py": (
            ('class ARV2SixUniverseOrderTilt40Algorithm(QCAlgorithm):',
             f'class ARV2SixUniverseOrderTilt{pct}Algorithm(QCAlgorithm):', 1),
            ("role='matched_revision_tilt40',", f"role='{role}',", 1),
            ("variant='cap90_matched_revision_tilt40_admission_bridge_v1',",
             f"variant='{identity['variant']}',", 1),
        ),
    }


def _replace_exact(source_bytes, replacements):
    if type(source_bytes) is not bytes or type(replacements) is not tuple:
        _error("tilt ladder source replacement contract changed")
    try:
        source = source_bytes.decode("ascii")
    except UnicodeError as exc:
        raise SixUniverseTiltLadderQcProjectionError(
            "R185 projected source is not ASCII"
        ) from exc
    for old, new, count in replacements:
        if (
            type(old) is not str or type(new) is not str
            or type(count) is not int or count < 1
            or old == new or source.count(old) != count
        ):
            _error("tilt ladder projected source lost an exact replacement point")
        source = source.replace(old, new, count)
    return source.encode("ascii")


def _render_profile(percent):
    identity = _identity(percent)
    baseline = _r185.require_tilt40_profile()
    if (
        baseline["profile_sha256"] != _R185_PROFILE_SHA256
        or baseline["role"] != _r185.TILT40_ROLE
        or baseline["maximum_stock_weight_change_fraction"] != "0.40"
    ):
        _error("R185 tilt profile changed from its pin")
    seed = {key: value for key, value in baseline.items() if key != "profile_sha256"}
    seed.update({
        "schema": identity["profile_schema"],
        "profile_id": identity["profile_id"],
        "role": identity["role"],
        "target_path_schema": identity["target_path_schema"],
        "decision_target_schema": identity["decision_target_schema"],
        "maximum_stock_weight_change_fraction": f"0.{percent:02d}",
    })
    return json.loads(_base._canonical({
        **seed,
        "profile_sha256": hashlib.sha256(_base._canonical(seed)).hexdigest(),
    }).decode("ascii"))


def require_tilt_ladder_profile(percent):
    """Return one exact R187/R188/R189 profile, never a caller-set fraction."""
    profile = _render_profile(percent)
    if profile["profile_sha256"] != PINNED_PROFILES[percent]:
        _error("tilt ladder profile changed from its pin")
    return profile


def _build_unchecked(delta_package, percent):
    identity = _identity(percent)
    try:
        baseline = _r185.build_accepted_risk_six_universe_order_tilt40_qc_projection(
            delta_package
        )
    except _r185.SixUniverseTilt40QcProjectionError as exc:
        raise SixUniverseTiltLadderQcProjectionError(str(exc)) from exc
    if (
        baseline.projection_sha256 != _R185_PROJECTION_SHA256
        or baseline.profile_sha256 != _R185_PROFILE_SHA256
        or baseline.total_source_byte_count != _R185_TOTAL_SOURCE_BYTES
        or len(baseline.source_files) != 16
        or baseline.variant != _r185.TILT40_VARIANT
    ):
        _error("R185 projected source changed from its pin")
    profile = _render_profile(percent)
    transforms = _replacements(percent)
    files = []
    for item in baseline.source_files:
        path = item.project_path
        if (
            item.byte_count != len(item.source_bytes)
            or item.content_sha256 != hashlib.sha256(item.source_bytes).hexdigest()
        ):
            _error("R185 projected file identity changed")
        if path in transforms:
            if (
                item.content_sha256 != _r185._R185_SOURCE_SHA256S[path]
                or item.byte_count != _r185._R185_SOURCE_BYTE_COUNTS[path]
            ):
                _error("R185 transformed source changed from its exact pin")
            try:
                files.append(_base._source_file(
                    path, _replace_exact(item.source_bytes, transforms[path])
                ))
            except _base.AcceptedRiskSixUniverseOrderQcProjectionError as exc:
                raise SixUniverseTiltLadderQcProjectionError(str(exc)) from exc
        else:
            files.append(item)
    files.sort(key=lambda item: item.project_path)
    if (
        len(files) != 16 or len({item.project_path for item in files}) != 16
        or set(transforms) != _CHANGED_PATHS
        or any(
            len(item.source_bytes.decode("ascii")) > _base.MAXIMUM_QC_SOURCE_CHARACTERS
            for item in files
        )
    ):
        _error("tilt ladder projected source closure or QC file bound changed")
    for item in files:
        compile(
            "from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"),
            item.project_path, "exec",
        )
    total = sum(item.byte_count for item in files)
    if total + _base.MINIMUM_REVIEW_MARGIN_BYTES > _base.MAXIMUM_TOTAL_SOURCE_BYTES:
        _error("tilt ladder projected source exceeded reviewed total bound")
    semantic = {
        key: value for key, value in baseline.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    }
    semantic.update({
        "schema": identity["projection_schema"],
        "role": identity["role"],
        "variant": identity["variant"],
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "source_files": [item.to_record() for item in files],
        "total_source_byte_count": total,
    })
    digest = hashlib.sha256(_base._canonical(semantic)).hexdigest()
    value = dataclasses.replace(
        baseline,
        schema=identity["projection_schema"],
        projection_id=(
            f"arv2-six-universe-order-tilt{percent}-qc-projection-" + digest[:24]
        ),
        projection_sha256=digest,
        role=identity["role"],
        variant=identity["variant"],
        profile_id=profile["profile_id"],
        profile_sha256=profile["profile_sha256"],
        source_files=tuple(files),
        total_source_byte_count=total,
    )
    if {
        key: item for key, item in value.to_record().items()
        if key not in ("projection_id", "projection_sha256")
    } != semantic:
        _error("tilt ladder projection did not self-authenticate")
    return value


def build_tilt_ladder_projection(delta_package, percent):
    """Build an independently identified 16-file order source for 70/60/50%."""
    value = _build_unchecked(delta_package, percent)
    if (
        value.profile_sha256 != PINNED_PROFILES[percent]
        or value.projection_sha256 != PINNED_PROJECTIONS[percent]
        or value.total_source_byte_count != PINNED_TOTAL_SOURCE_BYTES
        or any(
            item.content_sha256 != PINNED_SOURCE_SHA256S[percent][item.project_path]
            for item in value.source_files if item.project_path in _CHANGED_PATHS
        )
    ):
        _error("tilt ladder profile, manifest, or source changed from its pin")
    return value


__all__ = (
    "PERCENTS", "PINNED_PROFILES", "PINNED_PROJECTIONS",
    "PINNED_SOURCE_SHA256S", "PINNED_TOTAL_SOURCE_BYTES",
    "SixUniverseTiltLadderQcProjectionError", "build_tilt_ladder_projection",
    "require_tilt_ladder_profile",
)
